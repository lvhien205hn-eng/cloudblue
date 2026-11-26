// cbproxy — PROXY RIÊNG cho 1 máy Android (Cloud Phone CloudBlue). Chạy ROOT bên trong máy ảo; máy chủ đẩy vào qua adb.
//
// Mọi kết nối TCP của app trong máy → iptables (nat OUTPUT, REDIRECT) → cbproxy (127.0.0.1:PORT) → proxy của khách
// (SOCKS5 hoặc HTTP CONNECT, có user:pass) → đích thật. App không cần biết gì, không cần cài app proxy.
//
//   - Proxy chết / sai mật khẩu → TỰ ĐI MẠNG THƯỜNG (khách chọn): kết nối nào nối proxy hỏng thì nối thẳng; hỏng liên tiếp → cả máy
//     đi thẳng, 15 giây thử lại proxy 1 lần, lành thì quay lại dùng proxy.
//   - Proxy sống nhưng báo không tới được đích (đích chặn / sai cổng) → báo lỗi cho app như mạng thường, KHÔNG đi thẳng (không lộ IP).
//   - UDP không qua proxy; UDP 443 (QUIC) bị chặn để Chrome / YouTube / Google tự chuyển sang TCP → đi qua proxy.
//   - IPv6 TCP bị chặn (app tự dùng IPv4 → qua proxy). Mạng nội bộ / DNS của máy ảo (10.x, 192.168.x…) đi thẳng như cũ.
//   - Kết nối của chính cbproxy mang dấu SO_MARK 0x40000000 → iptables bỏ qua (không vòng lặp). Dấu này không đụng các bit Android
//     dùng để chọn mạng (16 bit thấp) → định tuyến vẫn theo mạng mặc định.
//   - Giám sát: tiến trình "super" chạy tiến trình "worker"; worker chết → gỡ iptables NGAY (máy vẫn có mạng), 2 giây sau bật lại;
//     chết liên tục → gỡ hẳn, đứng đó báo lỗi. Tắt (down) → gỡ sạch iptables.
//
// Lệnh:  cbproxy up -c CONF [-d DIR]     bật (chạy nền) + in trạng thái JSON
//
//	cbproxy down [-d DIR]           tắt + gỡ iptables
//	cbproxy status [-d DIR]         in trạng thái JSON (cũng ghi sẵn ở /data/local/tmp/cbproxy.json cho adb thường đọc)
//	cbproxy test -c CONF            thử proxy: in {"ok", "kind", "ip", "ms", "err"}
//	cbproxy version
//
// CONF (JSON): {"kind": "auto|socks5|http", "host": "…", "ips": ["1.2.3.4"], "port": 1080, "user": "…", "pass": "…"}
package main

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const (
	VER       = "22.11a"
	MARK      = 0x40000000
	DEF_LOCAL = 12081
	PUB_STATE = "/data/local/tmp/cbproxy.json"
	CH_NAT    = "CBPX"
	CH_FIL    = "CBPXF"
	CH_V6     = "CBPX6"
)

var DEF_DIR = "/data/adb/cbproxy"
var PUB = envOr("CBPX_PUB", PUB_STATE) // bộ thử đổi chỗ ghi trạng thái công khai

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

type Conf struct {
	Kind  string   `json:"kind"`
	Host  string   `json:"host"`
	IPs   []string `json:"ips"`
	Port  int      `json:"port"`
	User  string   `json:"user"`
	Pass  string   `json:"pass"`
	Local int      `json:"local"`
	Quic  *bool    `json:"block_quic"`
	Fail  *bool    `json:"failover"`
}

func (c *Conf) blockQuic() bool { return c.Quic == nil || *c.Quic }
func (c *Conf) failover() bool  { return c.Fail == nil || *c.Fail }

type State struct {
	Ver     string `json:"ver"`
	Pid     int    `json:"pid"`
	Mode    string `json:"mode"` // starting | proxy | direct | crashed | off
	Kind    string `json:"kind"`
	Host    string `json:"host"`
	Port    int    `json:"port"`
	IP      string `json:"ip"`
	Ms      int    `json:"ms"`
	OkAt    int64  `json:"ok_at"`
	FailAt  int64  `json:"fail_at"`
	Err     string `json:"err"`
	Since   int64  `json:"since"`
	Beat    int64  `json:"beat"`
	Conns   int64  `json:"conns"`
	Via     int64  `json:"via"`
	Direct  int64  `json:"direct"`
	Refused int64  `json:"refused"`
	Rules   bool   `json:"rules"`
	Running bool   `json:"running"`
	Age     int64  `json:"age"`
}

// ------------------------------------------------------------------ lỗi: proxy hỏng (đi thẳng được) / đích không tới được (không đi thẳng)
type proxyErr struct{ e error }

func (p *proxyErr) Error() string { return p.e.Error() }

type dstErr struct{ e error }

func (d *dstErr) Error() string { return d.e.Error() }

func pErr(f string, a ...interface{}) error { return &proxyErr{fmt.Errorf(f, a...)} }
func dErr(f string, a ...interface{}) error { return &dstErr{fmt.Errorf(f, a...)} }

// ------------------------------------------------------------------ nối ra ngoài (mang dấu → iptables bỏ qua)
var testNoMark = os.Getenv("CBPX_NOMARK") == "1"

func dialer(to time.Duration) *net.Dialer {
	return &net.Dialer{Timeout: to, KeepAlive: 30 * time.Second, Control: func(network, address string, c syscall.RawConn) error {
		if testNoMark {
			return nil
		}
		var serr error
		if err := c.Control(func(fd uintptr) { serr = syscall.SetsockoptInt(int(fd), syscall.SOL_SOCKET, syscall.SO_MARK, MARK) }); err != nil {
			return err
		}
		return serr
	}}
}

// target: đích muốn tới qua proxy — IP (kết nối của app) hoặc tên miền (thử proxy)
type target struct {
	host string
	port int
}

func (t target) String() string { return net.JoinHostPort(t.host, strconv.Itoa(t.port)) }

// socks5: bắt tay + CONNECT. Lỗi kết nối / đăng nhập = proxyErr; proxy báo không tới đích = dstErr.
func socks5(c net.Conn, t target, user, pass string) error {
	methods := []byte{0x00}
	if user != "" || pass != "" {
		methods = []byte{0x02, 0x00}
	}
	if _, err := c.Write(append([]byte{5, byte(len(methods))}, methods...)); err != nil {
		return pErr("gửi tới proxy lỗi: %v", err)
	}
	r := make([]byte, 2)
	if _, err := io.ReadFull(c, r); err != nil {
		return pErr("proxy không trả lời (SOCKS5): %v", err)
	}
	if r[0] != 5 {
		return pErr("không phải proxy SOCKS5")
	}
	switch r[1] {
	case 0x00:
	case 0x02:
		u, p := []byte(user), []byte(pass)
		if len(u) > 255 || len(p) > 255 {
			return pErr("user / mật khẩu quá dài")
		}
		a := append([]byte{1, byte(len(u))}, u...)
		a = append(a, byte(len(p)))
		a = append(a, p...)
		if _, err := c.Write(a); err != nil {
			return pErr("gửi user / mật khẩu lỗi: %v", err)
		}
		if _, err := io.ReadFull(c, r); err != nil {
			return pErr("proxy không trả lời đăng nhập: %v", err)
		}
		if r[1] != 0 {
			return pErr("proxy báo SAI user / mật khẩu")
		}
	case 0xFF:
		if user == "" && pass == "" {
			return pErr("proxy cần user / mật khẩu")
		}
		return pErr("proxy không nhận cách đăng nhập user / mật khẩu")
	default:
		return pErr("proxy SOCKS5 trả lời lạ (%d)", r[1])
	}
	req := []byte{5, 1, 0}
	if ip := net.ParseIP(t.host); ip != nil {
		if ip4 := ip.To4(); ip4 != nil {
			req = append(append(req, 1), ip4...)
		} else {
			req = append(append(req, 4), ip.To16()...)
		}
	} else {
		if len(t.host) > 255 {
			return dErr("tên miền quá dài")
		}
		req = append(append(req, 3, byte(len(t.host))), []byte(t.host)...)
	}
	req = append(req, byte(t.port>>8), byte(t.port))
	if _, err := c.Write(req); err != nil {
		return pErr("gửi lệnh nối lỗi: %v", err)
	}
	h := make([]byte, 4)
	if _, err := io.ReadFull(c, h); err != nil {
		return pErr("proxy không trả lời lệnh nối: %v", err)
	}
	if h[0] != 5 {
		return pErr("proxy SOCKS5 trả lời lạ")
	}
	if h[1] != 0 {
		return dErr("proxy báo không tới được đích (mã SOCKS %d)", h[1])
	}
	var n int
	switch h[3] {
	case 1:
		n = 4
	case 4:
		n = 16
	case 3:
		b := make([]byte, 1)
		if _, err := io.ReadFull(c, b); err != nil {
			return pErr("proxy trả lời thiếu: %v", err)
		}
		n = int(b[0])
	default:
		return pErr("proxy SOCKS5 trả địa chỉ lạ")
	}
	if _, err := io.ReadFull(c, make([]byte, n+2)); err != nil {
		return pErr("proxy trả lời thiếu: %v", err)
	}
	return nil
}

// bufConn: kết nối còn dữ liệu đọc thừa trong bộ đệm (sau trả lời HTTP CONNECT)
type bufConn struct {
	net.Conn
	r *bufio.Reader
}

func (b *bufConn) Read(p []byte) (int, error) { return b.r.Read(p) }
func (b *bufConn) CloseWrite() error {
	if tc, ok := b.Conn.(*net.TCPConn); ok {
		return tc.CloseWrite()
	}
	return b.Conn.Close()
}

func httpConnect(c net.Conn, t target, user, pass string) (net.Conn, error) {
	hp := t.String()
	req := "CONNECT " + hp + " HTTP/1.1\r\nHost: " + hp + "\r\n"
	if user != "" || pass != "" {
		req += "Proxy-Authorization: Basic " + base64.StdEncoding.EncodeToString([]byte(user+":"+pass)) + "\r\n"
	}
	req += "Proxy-Connection: Keep-Alive\r\nUser-Agent: cbproxy/" + VER + "\r\n\r\n"
	if _, err := io.WriteString(c, req); err != nil {
		return nil, pErr("gửi tới proxy lỗi: %v", err)
	}
	br := bufio.NewReaderSize(c, 4096)
	line, err := br.ReadString('\n')
	if err != nil {
		return nil, pErr("proxy không trả lời (HTTP): %v", err)
	}
	f := strings.Fields(line)
	if len(f) < 2 || !strings.HasPrefix(f[0], "HTTP/") {
		return nil, pErr("không phải proxy HTTP")
	}
	code, _ := strconv.Atoi(f[1])
	for i := 0; i < 100; i++ {
		l, err := br.ReadString('\n')
		if err != nil {
			return nil, pErr("proxy trả lời thiếu: %v", err)
		}
		if l == "\r\n" || l == "\n" {
			break
		}
	}
	switch {
	case code == 200:
	case code == 407:
		return nil, pErr("proxy báo SAI user / mật khẩu (407)")
	case code == 502 || code == 503 || code == 504 || code == 403:
		return nil, dErr("proxy báo không tới được đích (HTTP %d)", code)
	default:
		return nil, pErr("proxy HTTP trả lời %d", code)
	}
	if br.Buffered() > 0 {
		return &bufConn{c, br}, nil
	}
	return c, nil
}

// handshake qua proxy theo kiểu đã biết
func viaProxy(c net.Conn, kind string, t target, user, pass string) (net.Conn, error) {
	if kind == "http" {
		return httpConnect(c, t, user, pass)
	}
	if err := socks5(c, t, user, pass); err != nil {
		return nil, err
	}
	return c, nil
}

// ------------------------------------------------------------------ worker
type W struct {
	conf   Conf
	dir    string
	mu     sync.Mutex
	st     State
	kind   atomic.Value // "socks5" | "http"
	direct atomic.Bool  // đang đi thẳng (proxy hỏng)
	fails  atomic.Int32 // lỗi proxy liên tiếp (kết nối của app)
	lastOK atomic.Int64
	wake   chan struct{}
}

func (w *W) Kind() string {
	if k, ok := w.kind.Load().(string); ok && k != "" {
		return k
	}
	if w.conf.Kind == "http" || w.conf.Kind == "socks5" {
		return w.conf.Kind
	}
	return "socks5"
}

func (w *W) dialProxy(t target, to time.Duration) (net.Conn, error) {
	var last error = pErr("chưa có IP proxy")
	for _, ip := range w.conf.IPs {
		c, err := dialer(to).Dial("tcp", net.JoinHostPort(ip, strconv.Itoa(w.conf.Port)))
		if err != nil {
			last = pErr("không nối được proxy %s:%d: %v", ip, w.conf.Port, err)
			continue
		}
		c.SetDeadline(time.Now().Add(to + 2*time.Second))
		cc, err := viaProxy(c, w.Kind(), t, w.conf.User, w.conf.Pass)
		if err != nil {
			c.Close()
			if _, ok := err.(*dstErr); ok {
				return nil, err
			}
			last = err
			continue
		}
		c.SetDeadline(time.Time{})
		return cc, nil
	}
	return nil, last
}

// probe: thử proxy thật — nối qua proxy tới trang báo IP (không cần DNS trong máy: tên miền do proxy tự phân giải).
// Trả (IP ra, kiểu proxy, ms, lỗi). Proxy sống mà mọi trang thử đều không tới được → coi là SỐNG (chỉ không biết IP ra).
func probe(conf Conf, kinds []string) (string, string, int, error) {
	targets := []struct {
		t    target
		path string
		tls  bool
	}{
		{target{"1.1.1.1", 80}, "/cdn-cgi/trace", false},
		{target{"api.ipify.org", 80}, "/", false},
		{target{"ifconfig.me", 80}, "/ip", false},
	}
	var lastErr error = pErr("chưa thử")
	for _, kind := range kinds {
		w := &W{conf: conf}
		w.kind.Store(kind)
		alive := false
		for _, tg := range targets {
			t0 := time.Now()
			c, err := w.dialProxy(tg.t, 5*time.Second)
			if err != nil {
				lastErr = err
				if _, ok := err.(*dstErr); ok {
					alive = true
					continue
				}
				break // proxy hỏng với kiểu này → thử kiểu khác
			}
			alive = true
			ip, err := fetchIP(c, tg.t.host, tg.path, tg.tls)
			c.Close()
			ms := int(time.Since(t0) / time.Millisecond)
			if err == nil && ip != "" {
				return ip, kind, ms, nil
			}
			lastErr = dErr("đọc IP ra lỗi: %v", err)
		}
		if alive {
			return "", kind, 0, nil
		}
	}
	return "", "", 0, lastErr
}

func fetchIP(c net.Conn, host, path string, _ bool) (string, error) {
	c.SetDeadline(time.Now().Add(8 * time.Second))
	var rw io.ReadWriter = c
	if _, err := io.WriteString(rw, "GET "+path+" HTTP/1.1\r\nHost: "+host+"\r\nUser-Agent: cbproxy/"+VER+"\r\nConnection: close\r\n\r\n"); err != nil {
		return "", err
	}
	b, _ := io.ReadAll(io.LimitReader(rw, 16384))
	s := string(b)
	i := strings.Index(s, "\r\n\r\n")
	if i < 0 {
		return "", errors.New("trả lời lạ")
	}
	body := s[i+4:]
	if strings.HasPrefix(path, "/cdn-cgi/trace") {
		for _, l := range strings.Split(body, "\n") {
			if strings.HasPrefix(l, "ip=") {
				return cleanIP(strings.TrimSpace(l[3:])), nil
			}
		}
		return "", errors.New("không thấy ip=")
	}
	return cleanIP(strings.TrimSpace(body)), nil
}

func cleanIP(s string) string {
	if ip := net.ParseIP(s); ip != nil {
		return ip.String()
	}
	return ""
}

func (w *W) kinds() []string {
	switch w.conf.Kind {
	case "http":
		return []string{"http"}
	case "socks5":
		return []string{"socks5"}
	}
	if k, ok := w.kind.Load().(string); ok && k == "http" {
		return []string{"http", "socks5"}
	}
	return []string{"socks5", "http"}
}

func (w *W) doProbe() {
	ip, kind, ms, err := probe(w.conf, w.kinds())
	now := time.Now().Unix()
	w.mu.Lock()
	defer w.mu.Unlock()
	if err == nil {
		w.kind.Store(kind)
		w.direct.Store(false)
		w.fails.Store(0)
		w.lastOK.Store(now)
		w.st.Mode, w.st.Kind, w.st.OkAt, w.st.Err = "proxy", kind, now, ""
		if ip != "" {
			w.st.IP, w.st.Ms = ip, ms
		}
	} else {
		w.direct.Store(true)
		w.st.Mode, w.st.FailAt, w.st.Err = "direct", now, err.Error()
	}
}

func (w *W) connFail(err error) {
	if _, ok := err.(*dstErr); ok {
		return
	}
	if w.fails.Add(1) >= 3 && !w.direct.Load() {
		w.direct.Store(true)
		w.mu.Lock()
		w.st.Mode, w.st.FailAt, w.st.Err = "direct", time.Now().Unix(), err.Error()
		w.mu.Unlock()
		select {
		case w.wake <- struct{}{}:
		default:
		}
	}
}

func (w *W) handle(c net.Conn) {
	defer c.Close()
	atomic.AddInt64(&w.st.Conns, 1)
	dst, err := origDst(c)
	if err != nil {
		return
	}
	if dst.IP.IsLoopback() && dst.Port == w.conf.Local {
		return
	}
	var up net.Conn
	if !w.direct.Load() {
		up, err = w.dialProxy(target{dst.IP.String(), dst.Port}, 8*time.Second)
		if err != nil {
			w.connFail(err)
			if _, ok := err.(*dstErr); ok || !w.conf.failover() {
				atomic.AddInt64(&w.st.Refused, 1)
				return
			}
			up = nil
		} else {
			w.fails.Store(0)
			w.lastOK.Store(time.Now().Unix())
			atomic.AddInt64(&w.st.Via, 1)
		}
	}
	if up == nil {
		if !w.conf.failover() {
			atomic.AddInt64(&w.st.Refused, 1)
			return
		}
		up, err = dialer(10*time.Second).Dial("tcp", dst.String())
		if err != nil {
			return
		}
		atomic.AddInt64(&w.st.Direct, 1)
	}
	defer up.Close()
	relay(c, up)
}

type closeWriter interface{ CloseWrite() error }

func relay(a, b net.Conn) {
	var wg sync.WaitGroup
	wg.Add(2)
	cp := func(dst, src net.Conn) {
		defer wg.Done()
		io.Copy(dst, src)
		if cw, ok := dst.(closeWriter); ok {
			cw.CloseWrite()
		} else {
			dst.Close()
		}
	}
	go cp(a, b)
	go cp(b, a)
	wg.Wait()
}

// SO_ORIGINAL_DST (80): đích thật của kết nối bị iptables REDIRECT
func origDst(c net.Conn) (*net.TCPAddr, error) {
	if s := os.Getenv("CBPX_TEST_DST"); s != "" { // chỉ bộ thử không có iptables
		a, err := net.ResolveTCPAddr("tcp", s)
		return a, err
	}
	tc, ok := c.(*net.TCPConn)
	if !ok {
		return nil, errors.New("không phải TCP")
	}
	rc, err := tc.SyscallConn()
	if err != nil {
		return nil, err
	}
	var addr *net.TCPAddr
	var gerr error
	err = rc.Control(func(fd uintptr) {
		m, e := syscall.GetsockoptIPv6Mreq(int(fd), syscall.IPPROTO_IP, 80)
		if e != nil {
			gerr = e
			return
		}
		b := m.Multiaddr
		addr = &net.TCPAddr{IP: net.IPv4(b[4], b[5], b[6], b[7]), Port: int(b[2])<<8 | int(b[3])}
	})
	if err != nil {
		return nil, err
	}
	return addr, gerr
}

// ------------------------------------------------------------------ iptables
var (
	iptBin  = findBin("iptables")
	ip6tBin = findBin("ip6tables")
	iptWait = []string{"-w"}
)

func findBin(name string) string {
	for _, d := range []string{"/system/bin", "/system/xbin", "/vendor/bin", "/sbin", "/usr/sbin", "/usr/bin", "/bin"} {
		p := filepath.Join(d, name)
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p
		}
	}
	return name
}

func ipt(bin string, args ...string) (string, error) {
	a := append(append([]string{}, iptWait...), args...)
	out, err := exec.Command(bin, a...).CombinedOutput()
	s := string(out)
	if err != nil && len(iptWait) > 0 && (strings.Contains(s, "unknown option") || strings.Contains(s, "invalid option")) {
		iptWait = nil
		out, err = exec.Command(bin, args...).CombinedOutput()
		s = string(out)
	}
	return s, err
}

var private4 = []string{"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
	"192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4"}

func markArg() []string {
	return []string{"-m", "mark", "--mark", fmt.Sprintf("0x%x/0x%x", MARK, MARK), "-j", "RETURN"}
}

func rulesUp(c *Conf) error {
	rulesDown()
	ipt(iptBin, "-t", "nat", "-N", CH_NAT)
	var rules [][]string
	rules = append(rules, markArg())
	for _, n := range private4 {
		rules = append(rules, []string{"-d", n, "-j", "RETURN"})
	}
	for _, ip := range c.IPs {
		if p := net.ParseIP(ip); p != nil && p.To4() != nil {
			rules = append(rules, []string{"-d", p.String() + "/32", "-j", "RETURN"})
		}
	}
	for _, r := range rules {
		if out, err := ipt(iptBin, append([]string{"-t", "nat", "-A", CH_NAT}, r...)...); err != nil {
			rulesDown()
			return fmt.Errorf("iptables nat: %v %s", err, strings.TrimSpace(out))
		}
	}
	// bắt TCP về cổng của cbproxy: REDIRECT; nhân thiếu REDIRECT thì DNAT về 127.0.0.1 (cùng cách lấy đích gốc SO_ORIGINAL_DST)
	if out, err := ipt(iptBin, "-t", "nat", "-A", CH_NAT, "-p", "tcp", "-j", "REDIRECT", "--to-ports", strconv.Itoa(c.Local)); err != nil {
		if out2, err2 := ipt(iptBin, "-t", "nat", "-A", CH_NAT, "-p", "tcp", "-j", "DNAT", "--to-destination", fmt.Sprintf("127.0.0.1:%d", c.Local)); err2 != nil {
			rulesDown()
			return fmt.Errorf("iptables nat: %v %s / %s", err, strings.TrimSpace(out), strings.TrimSpace(out2))
		}
	}
	if out, err := ipt(iptBin, "-t", "nat", "-I", "OUTPUT", "1", "-j", CH_NAT); err != nil {
		rulesDown()
		return fmt.Errorf("iptables nat OUTPUT: %v %s", err, strings.TrimSpace(out))
	}
	if c.blockQuic() { // chặn QUIC (UDP 443) → app chuyển sang TCP qua proxy; lỗi thì bỏ qua
		ipt(iptBin, "-N", CH_FIL)
		ipt(iptBin, append([]string{"-A", CH_FIL}, markArg()...)...)
		if _, err := ipt(iptBin, "-A", CH_FIL, "-p", "udp", "--dport", "443", "-j", "REJECT"); err != nil {
			ipt(iptBin, "-A", CH_FIL, "-p", "udp", "--dport", "443", "-j", "DROP")
		}
		ipt(iptBin, "-I", "OUTPUT", "1", "-j", CH_FIL)
	}
	{ // IPv6: chặn TCP ra ngoài (app tự dùng IPv4 → qua proxy); máy không có ip6tables thì các lệnh này lỗi, bỏ qua
		ipt(ip6tBin, "-N", CH_V6)
		ipt(ip6tBin, append([]string{"-A", CH_V6}, markArg()...)...)
		for _, n := range []string{"::1/128", "fe80::/10", "fc00::/7", "ff00::/8"} {
			ipt(ip6tBin, "-A", CH_V6, "-d", n, "-j", "RETURN")
		}
		if _, err := ipt(ip6tBin, "-A", CH_V6, "-p", "tcp", "-j", "REJECT", "--reject-with", "tcp-reset"); err != nil {
			ipt(ip6tBin, "-A", CH_V6, "-p", "tcp", "-j", "DROP")
		}
		if c.blockQuic() {
			ipt(ip6tBin, "-A", CH_V6, "-p", "udp", "--dport", "443", "-j", "DROP")
		}
		ipt(ip6tBin, "-I", "OUTPUT", "1", "-j", CH_V6)
	}
	return nil
}

func rulesDown() {
	for i := 0; i < 10; i++ {
		if _, err := ipt(iptBin, "-t", "nat", "-D", "OUTPUT", "-j", CH_NAT); err != nil {
			break
		}
	}
	ipt(iptBin, "-t", "nat", "-F", CH_NAT)
	ipt(iptBin, "-t", "nat", "-X", CH_NAT)
	for i := 0; i < 10; i++ {
		if _, err := ipt(iptBin, "-D", "OUTPUT", "-j", CH_FIL); err != nil {
			break
		}
	}
	ipt(iptBin, "-F", CH_FIL)
	ipt(iptBin, "-X", CH_FIL)
	for i := 0; i < 10; i++ {
		if _, err := ipt(ip6tBin, "-D", "OUTPUT", "-j", CH_V6); err != nil {
			break
		}
	}
	ipt(ip6tBin, "-F", CH_V6)
	ipt(ip6tBin, "-X", CH_V6)
}

func rulesOn() bool {
	_, err := ipt(iptBin, "-t", "nat", "-C", "OUTPUT", "-j", CH_NAT)
	return err == nil
}

// ------------------------------------------------------------------ trạng thái
func writeJSON(path string, v interface{}, mode os.FileMode) {
	b, _ := json.Marshal(v)
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, mode); err == nil {
		os.Chmod(tmp, mode)
		os.Rename(tmp, path)
	}
}

func (w *W) save() {
	w.mu.Lock()
	s := w.st
	w.mu.Unlock()
	s.Conns, s.Via, s.Direct, s.Refused = atomic.LoadInt64(&w.st.Conns), atomic.LoadInt64(&w.st.Via), atomic.LoadInt64(&w.st.Direct), atomic.LoadInt64(&w.st.Refused)
	s.Beat = time.Now().Unix()
	writeJSON(filepath.Join(w.dir, "state.json"), s, 0600)
	writeJSON(PUB, s, 0644) // adb thường (không root) đọc được: máy chủ hỏi trạng thái mà không cần root
}

func worker(conf Conf, dir string) int {
	logf := func(f string, a ...interface{}) {
		fmt.Fprintf(os.Stderr, time.Now().Format("01-02 15:04:05 ")+f+"\n", a...)
	}
	noOOM()
	ln, err := net.Listen("tcp4", fmt.Sprintf("127.0.0.1:%d", conf.Local))
	if err != nil {
		logf("không mở được cổng %d: %v", conf.Local, err)
		return 3
	}
	w := &W{conf: conf, dir: dir, wake: make(chan struct{}, 1)}
	now := time.Now().Unix()
	w.st = State{Ver: VER, Pid: os.Getpid(), Mode: "starting", Host: conf.Host, Port: conf.Port, Since: now}
	w.save()
	w.doProbe() // biết proxy sống / chết trước khi bắt app đi qua
	if err := rulesUp(&conf); err != nil {
		logf("%v", err)
		w.mu.Lock()
		w.st.Err = err.Error()
		w.mu.Unlock()
		w.save()
		return 4
	}
	w.mu.Lock()
	w.st.Rules = true
	w.mu.Unlock()
	w.save()
	logf("chạy: proxy %s:%d (%s) · chế độ %s · IP ra %s", conf.Host, conf.Port, w.Kind(), w.st.Mode, w.st.IP)

	sig := make(chan os.Signal, 2)
	signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP)
	go func() {
		<-sig
		rulesDown()
		w.mu.Lock()
		w.st.Mode, w.st.Rules = "off", false
		w.mu.Unlock()
		w.save()
		os.Exit(0)
	}()
	go func() { // canh proxy: đang dùng → 60 giây thử 1 lần (cập nhật IP ra); đang đi thẳng → 15 giây thử lại
		for {
			d := 60 * time.Second
			if w.direct.Load() {
				d = 15 * time.Second
			}
			select {
			case <-time.After(d):
			case <-w.wake:
				time.Sleep(2 * time.Second)
			}
			w.doProbe()
		}
	}()
	go func() { // nhịp sống + iptables bị xoá mất (Android nạp lại) → gắn lại
		n := 0
		for {
			time.Sleep(5 * time.Second)
			n++
			if n%3 == 0 && !rulesOn() {
				if err := rulesUp(&conf); err != nil {
					logf("gắn lại iptables lỗi: %v", err)
				} else {
					logf("iptables bị xoá → đã gắn lại")
				}
			}
			w.save()
		}
	}()
	for {
		c, err := ln.Accept()
		if err != nil {
			time.Sleep(50 * time.Millisecond)
			continue
		}
		go w.handle(c)
	}
}

// ------------------------------------------------------------------ giám sát + bật / tắt
func pidAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	if syscall.Kill(pid, 0) != nil {
		return false
	}
	b, err := os.ReadFile(fmt.Sprintf("/proc/%d/cmdline", pid))
	return err == nil && strings.Contains(string(b), "cbproxy")
}

func readPid(p string) int {
	b, err := os.ReadFile(p)
	if err != nil {
		return 0
	}
	n, _ := strconv.Atoi(strings.TrimSpace(string(b)))
	return n
}

// thoát khỏi nhóm tiến trình của adbd / su: "adb unroot" khởi động lại adbd cũng không giết cbproxy
func escapeCgroup() {
	for _, p := range []string{"/sys/fs/cgroup/cgroup.procs", "/acct/cgroup.procs", "/dev/cpuctl/cgroup.procs"} {
		os.WriteFile(p, []byte("0"), 0644)
	}
}

// không để Android dọn bộ nhớ giết cbproxy (giết giữa chừng = iptables còn, cổng đóng → máy mất mạng tới lần canh sau)
func noOOM() { os.WriteFile("/proc/self/oom_score_adj", []byte("-1000"), 0644) }

func super(confPath, dir string) int {
	escapeCgroup()
	noOOM()
	self, _ := os.Executable()
	os.WriteFile(filepath.Join(dir, "super.pid"), []byte(strconv.Itoa(os.Getpid())), 0600)
	var cur *os.Process
	var curMu sync.Mutex
	stopping := atomic.Bool{}
	sig := make(chan os.Signal, 2)
	signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP)
	go func() {
		<-sig
		stopping.Store(true)
		curMu.Lock()
		if cur != nil {
			cur.Signal(syscall.SIGTERM)
		}
		curMu.Unlock()
		time.Sleep(1500 * time.Millisecond)
		curMu.Lock()
		if cur != nil {
			cur.Kill()
		}
		curMu.Unlock()
		rulesDown()
		os.Remove(filepath.Join(dir, "super.pid"))
		os.Exit(0)
	}()
	var deaths []time.Time
	for !stopping.Load() {
		lf, _ := os.OpenFile(filepath.Join(dir, "log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
		p, err := os.StartProcess(self, []string{self, "worker", "-c", confPath, "-d", dir}, &os.ProcAttr{Files: []*os.File{nil, lf, lf}})
		if lf != nil {
			lf.Close()
		}
		if err != nil {
			time.Sleep(3 * time.Second)
			continue
		}
		curMu.Lock()
		cur = p
		curMu.Unlock()
		os.WriteFile(filepath.Join(dir, "worker.pid"), []byte(strconv.Itoa(p.Pid)), 0600)
		ps, _ := p.Wait()
		curMu.Lock()
		cur = nil
		curMu.Unlock()
		if stopping.Load() {
			break
		}
		rulesDown() // worker chết → app vẫn có mạng (đi thẳng) trong lúc bật lại
		now := time.Now()
		deaths = append(deaths, now)
		k := 0
		for _, t := range deaths {
			if now.Sub(t) < 2*time.Minute {
				deaths[k] = t
				k++
			}
		}
		deaths = deaths[:k]
		code := -1
		if ps != nil {
			code = ps.ExitCode()
		}
		if len(deaths) >= 5 || code == 3 || code == 4 {
			st := State{Ver: VER, Pid: os.Getpid(), Mode: "crashed", Err: fmt.Sprintf("tiến trình proxy dừng (mã %d) — đã gỡ, máy đi mạng thường", code), Beat: now.Unix()}
			if old, err := os.ReadFile(filepath.Join(dir, "state.json")); err == nil {
				var o State
				if json.Unmarshal(old, &o) == nil && o.Err != "" {
					st.Err = o.Err + " — đã gỡ, máy đi mạng thường"
				}
			}
			writeJSON(filepath.Join(dir, "state.json"), st, 0600)
			writeJSON(PUB, st, 0644)
			os.Remove(filepath.Join(dir, "super.pid"))
			return 5
		}
		time.Sleep(2 * time.Second)
	}
	return 0
}

func loadConf(path string) (Conf, error) {
	var c Conf
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, fmt.Errorf("cấu hình hỏng: %v", err)
	}
	if c.Local == 0 {
		c.Local = DEF_LOCAL
	}
	if c.Port < 1 || c.Port > 65535 {
		return c, errors.New("cổng proxy sai")
	}
	ok := false
	for _, s := range c.IPs {
		if net.ParseIP(s) != nil {
			ok = true
		}
	}
	if !ok {
		return c, errors.New("chưa có IP proxy (máy chủ chưa phân giải được tên miền)")
	}
	switch c.Kind {
	case "", "auto", "socks5", "http":
	default:
		return c, errors.New("kiểu proxy sai (auto / socks5 / http)")
	}
	return c, nil
}

func stop(dir string) {
	for _, n := range []string{"super.pid", "worker.pid"} {
		if pid := readPid(filepath.Join(dir, n)); pidAlive(pid) {
			syscall.Kill(pid, syscall.SIGTERM)
		}
	}
	for i := 0; i < 30; i++ {
		if !pidAlive(readPid(filepath.Join(dir, "super.pid"))) && !pidAlive(readPid(filepath.Join(dir, "worker.pid"))) {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	for _, n := range []string{"super.pid", "worker.pid"} {
		if pid := readPid(filepath.Join(dir, n)); pidAlive(pid) {
			syscall.Kill(pid, syscall.SIGKILL)
		}
		os.Remove(filepath.Join(dir, n))
	}
	rulesDown()
}

func status(dir string) State {
	var s State
	b, err := os.ReadFile(filepath.Join(dir, "state.json"))
	if err != nil {
		b, err = os.ReadFile(PUB)
	}
	if err == nil {
		json.Unmarshal(b, &s)
	}
	s.Running = pidAlive(readPid(filepath.Join(dir, "super.pid"))) && pidAlive(readPid(filepath.Join(dir, "worker.pid")))
	if s.Beat > 0 {
		s.Age = time.Now().Unix() - s.Beat
	}
	if !s.Running && s.Mode != "crashed" {
		s.Mode = "off"
	}
	s.Rules = rulesOn()
	return s
}

func out(v interface{}) {
	b, _ := json.Marshal(v)
	fmt.Println(string(b))
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "cbproxy up|down|status|test|version")
		os.Exit(2)
	}
	cmd := os.Args[1]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	confPath := fs.String("c", "", "cấu hình JSON")
	dir := fs.String("d", DEF_DIR, "thư mục làm việc")
	fs.Parse(os.Args[2:])
	switch cmd {
	case "version":
		fmt.Println(VER)
	case "worker":
		c, err := loadConf(*confPath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(4)
		}
		os.Exit(worker(c, *dir))
	case "super":
		os.Exit(super(*confPath, *dir))
	case "test":
		c, err := loadConf(*confPath)
		if err != nil {
			out(map[string]interface{}{"ok": false, "err": err.Error()})
			os.Exit(1)
		}
		w := &W{conf: c}
		t0 := time.Now()
		ip, kind, ms, err := probe(c, w.kinds())
		if err != nil {
			out(map[string]interface{}{"ok": false, "err": err.Error(), "ms": int(time.Since(t0) / time.Millisecond)})
			os.Exit(1)
		}
		out(map[string]interface{}{"ok": true, "kind": kind, "ip": ip, "ms": ms})
	case "up":
		c, err := loadConf(*confPath)
		if err != nil {
			out(map[string]interface{}{"ok": false, "err": err.Error()})
			os.Exit(1)
		}
		os.MkdirAll(*dir, 0700)
		stop(*dir)
		cp := filepath.Join(*dir, "conf.json")
		if abs, _ := filepath.Abs(*confPath); abs != cp {
			b, _ := json.Marshal(c)
			if err := os.WriteFile(cp, b, 0600); err != nil {
				out(map[string]interface{}{"ok": false, "err": "không ghi được cấu hình: " + err.Error()})
				os.Exit(1)
			}
		}
		os.Remove(filepath.Join(*dir, "state.json"))
		if fi, err := os.Stat(filepath.Join(*dir, "log")); err == nil && fi.Size() > 256<<10 {
			os.Remove(filepath.Join(*dir, "log"))
		}
		self, _ := os.Executable()
		devnull, _ := os.OpenFile(os.DevNull, os.O_RDWR, 0)
		p, err := os.StartProcess(self, []string{self, "super", "-c", cp, "-d", *dir},
			&os.ProcAttr{Files: []*os.File{devnull, devnull, devnull}, Sys: &syscall.SysProcAttr{Setsid: true}})
		if err != nil {
			out(map[string]interface{}{"ok": false, "err": "không chạy được: " + err.Error()})
			os.Exit(1)
		}
		p.Release()
		t0 := time.Now()
		for time.Since(t0) < 25*time.Second {
			time.Sleep(250 * time.Millisecond)
			s := status(*dir)
			if s.Mode == "crashed" {
				out(map[string]interface{}{"ok": false, "err": s.Err, "state": s})
				os.Exit(1)
			}
			if s.Running && s.Rules && (s.Mode == "proxy" || s.Mode == "direct") {
				out(map[string]interface{}{"ok": true, "state": s})
				return
			}
		}
		s := status(*dir)
		out(map[string]interface{}{"ok": false, "err": "chưa bật xong sau 25 giây", "state": s})
		os.Exit(1)
	case "down":
		stop(*dir)
		os.Remove(PUB)
		os.Remove(filepath.Join(*dir, "state.json"))
		out(map[string]interface{}{"ok": true, "rules": rulesOn()})
	case "status":
		out(status(*dir))
	default:
		fmt.Fprintln(os.Stderr, "lệnh lạ:", cmd)
		os.Exit(2)
	}
}
