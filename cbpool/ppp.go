package main

// IPv4 nhiều IP: mỗi phiên PPPoE (macvlan riêng MAC + pppd) = 1 IP công khai. Bảng định tuyến riêng từng phiên:
//   ip rule from <IP phiên> lookup <bảng> · bảng: default dev pppN → kết nối gắn IP phiên đi đúng phiên đó, máy chủ không đổi đường chính.

import (
	"bufio"
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

type sess struct {
	k      int
	unit   int
	mv     string // macvlan (hoặc card gốc nếu tắt macvlan)
	ip     net.IP
	up     bool
	since  time.Time
	err    string
	kick   chan struct{}
	stop   chan struct{}
	done   chan struct{}
	gen    int // số lần đã lên (đổi IP: chờ gen tăng)
	proc   *os.Process
	pmu    sync.Mutex
	parent *PppMgr
}

type PppMgr struct {
	c     *Conf
	st    *PState
	save  func()
	mu    sync.Mutex
	sec   *PppSecret
	iface string
	sess  []*sess
}

func newPppMgr(c *Conf, st *PState, save func()) *PppMgr { return &PppMgr{c: c, st: st, save: save} }

func (m *PppMgr) configure(sec *PppSecret, n int, iface string) {
	m.mu.Lock()
	same := (sec == nil && m.sec == nil) || (sec != nil && m.sec != nil && sec.User == m.sec.User && sec.Pass == m.sec.Pass)
	if !same || iface != m.iface {
		old := m.sess
		m.sess = nil
		m.sec, m.iface = sec, iface
		m.mu.Unlock()
		for _, s := range old {
			s.shutdown()
		}
		m.mu.Lock()
	}
	if sec == nil {
		n = 0
	}
	var drop []*sess
	if len(m.sess) > n {
		drop = m.sess[n:]
		m.sess = m.sess[:n]
	}
	for len(m.sess) < n {
		k := len(m.sess)
		s := &sess{k: k, unit: m.c.Ppp.Unit0 + k, kick: make(chan struct{}, 1), stop: make(chan struct{}), done: make(chan struct{}), parent: m}
		m.sess = append(m.sess, s)
		go s.loop()
	}
	m.mu.Unlock()
	for _, s := range drop {
		s.shutdown()
	}
	if n > 0 {
		logf("PPPoE: %d phiên trên %s", n, iface)
	}
}

func (m *PppMgr) stopAll() { m.configure(nil, 0, "") }

func (m *PppMgr) sessFor(slot int) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.sess) == 0 {
		return -1
	}
	return slot % len(m.sess)
}

func (m *PppMgr) ipFor(slot int) net.IP {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.sess) == 0 {
		return nil
	}
	s := m.sess[slot%len(m.sess)]
	if !s.up {
		return nil
	}
	return s.ip
}

func (m *PppMgr) redial(k int, wait time.Duration) (net.IP, error) {
	m.mu.Lock()
	if k < 0 || k >= len(m.sess) {
		m.mu.Unlock()
		return nil, errors.New("không có phiên này")
	}
	s := m.sess[k]
	g := s.gen
	m.mu.Unlock()
	select {
	case s.kick <- struct{}{}:
	default:
	}
	end := time.Now().Add(wait)
	for time.Now().Before(end) {
		time.Sleep(300 * time.Millisecond)
		m.mu.Lock()
		up, gen, ip, e := s.up, s.gen, s.ip, s.err
		m.mu.Unlock()
		if up && gen > g {
			return ip, nil
		}
		if e != "" && time.Since(end.Add(-wait)) > 15*time.Second && !up {
			return nil, errors.New(e)
		}
	}
	return nil, errors.New("quay lại chưa xong (quá thời gian)")
}

func (m *PppMgr) status() map[string]interface{} {
	m.mu.Lock()
	defer m.mu.Unlock()
	var ss []map[string]interface{}
	up := 0
	for _, s := range m.sess {
		x := map[string]interface{}{"k": s.k, "up": s.up, "if": fmt.Sprintf("ppp%d", s.unit)}
		if s.up {
			up++
			x["ip"] = s.ip.String()
			x["since"] = s.since.Unix()
		}
		if s.err != "" {
			x["err"] = s.err
		}
		ss = append(ss, x)
	}
	r := map[string]interface{}{"want": len(m.sess), "up": up, "iface": m.iface, "account": m.sec != nil, "sess": ss}
	if m.sec != nil {
		u := m.sec.User
		if len(u) > 3 {
			u = u[:3] + strings.Repeat("*", len(u)-3)
		}
		r["user"] = u
	}
	return r
}

// ---------------------------------------------------------------- 1 phiên

func (s *sess) shutdown() {
	select {
	case <-s.stop:
	default:
		close(s.stop)
	}
	s.pmu.Lock()
	if s.proc != nil {
		s.proc.Signal(syscall.SIGTERM)
	}
	s.pmu.Unlock()
	select {
	case <-s.done:
	case <-time.After(15 * time.Second):
	}
}

func (s *sess) set(f func()) {
	s.parent.mu.Lock()
	f()
	s.parent.mu.Unlock()
}

func (s *sess) loop() {
	defer close(s.done)
	m := s.parent
	fails := 0
	for {
		select {
		case <-s.stop:
			s.cleanup()
			return
		default:
		}
		m.mu.Lock()
		sec, iface, c := m.sec, m.iface, m.c
		m.mu.Unlock()
		if sec == nil {
			return
		}
		t0 := time.Now()
		wasUp, kicked, err := s.once(c, sec, iface)
		s.cleanupRoute(c)
		s.set(func() {
			s.up, s.ip = false, nil
			if err != nil {
				s.err = err.Error()
			}
		})
		if err != nil {
			logf("PPPoE phiên %d: %v", s.k, err)
		}
		wait := 3 * time.Second
		if kicked {
			wait = time.Second // đổi IP: quay lại ngay (pppd đã gửi PADT báo nhà mạng đóng phiên cũ)
			fails = 0
		} else if wasUp && time.Since(t0) > 60*time.Second {
			fails = 0
		} else if !wasUp {
			fails++
			wait = time.Duration(5<<uint(min(fails, 5))) * time.Second // 10 s … 160 s
			if wait > 120*time.Second {
				wait = 120 * time.Second
			}
		}
		select {
		case <-s.stop:
			s.cleanup()
			return
		case <-s.kick: // đang chờ quay lại mà khách bấm đổi IP → quay ngay
		case <-time.After(wait):
		}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func ipCmd(args ...string) error {
	b, err := exec.Command(ipBin(), args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("ip %s: %v %s", strings.Join(args, " "), err, strings.TrimSpace(string(b)))
	}
	return nil
}

func ipBin() string {
	for _, p := range []string{"/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip", "/bin/ip"} {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "ip"
}

func pppPlugin() string {
	for _, n := range []string{"pppoe.so", "rp-pppoe.so"} {
		if g, _ := filepath.Glob("/usr/lib/pppd/*/" + n); len(g) > 0 {
			return n
		}
		if g, _ := filepath.Glob("/usr/lib/*/pppd/*/" + n); len(g) > 0 {
			return n
		}
	}
	return ""
}

func randMAC() string {
	b := make([]byte, 6)
	rand.Read(b)
	b[0] = (b[0] | 0x02) &^ 0x01 // địa chỉ tự đặt, unicast
	return net.HardwareAddr(b).String()
}

func (s *sess) macFor(c *Conf) string {
	m := s.parent
	key := fmt.Sprintf("s%d", s.k)
	stMu.Lock()
	mac := m.st.Macs[key]
	if mac == "" {
		mac = randMAC()
		m.st.Macs[key] = mac
	}
	stMu.Unlock()
	if m.save != nil {
		m.save()
	}
	return mac
}

// once: bật 1 lần pppd, chờ có IP, giữ tới khi pppd thoát / đổi IP / dừng. Trả về (đã lên được chưa, do đổi IP, lỗi).
func (s *sess) once(c *Conf, sec *PppSecret, iface string) (bool, bool, error) {
	if iface == "" {
		return false, false, errors.New("chưa biết card mạng đi PPPoE")
	}
	if _, err := net.InterfaceByName(iface); err != nil {
		return false, false, fmt.Errorf("không có card %s", iface)
	}
	plug := pppPlugin()
	if plug == "" {
		return false, false, errors.New("máy chưa có pppd + plugin PPPoE (apt install ppp)")
	}
	dev := iface
	if bp(c.Ppp.Macvlan, true) {
		pre := c.Ppp.MvPrefix
		if pre == "" {
			pre = "cbpp"
		}
		s.mv = fmt.Sprintf("%s%d", pre, s.k)
		ipCmd("link", "del", s.mv)
		if err := ipCmd("link", "add", "link", iface, "name", s.mv, "address", s.macFor(c), "type", "macvlan", "mode", "private"); err != nil {
			return false, false, err
		}
		if err := ipCmd("link", "set", s.mv, "up"); err != nil {
			return false, false, err
		}
		dev = s.mv
	}
	os.MkdirAll("/run/cbpool", 0700)
	opts := fmt.Sprintf("/run/cbpool/ppp%d.opts", s.k)
	q := func(x string) string { return "\"" + strings.NewReplacer("\\", "\\\\", "\"", "\\\"").Replace(x) + "\"" }
	if err := os.WriteFile(opts, []byte("user "+q(sec.User)+"\npassword "+q(sec.Pass)+"\n"), 0600); err != nil {
		return false, false, err
	}
	defer os.Remove(opts)
	mtu := fmt.Sprint(c.Ppp.Mtu)
	cmd := exec.Command(c.Ppp.Pppd, "plugin", plug, "nic-"+dev, "file", opts, "nodetach", "noauth", "nodefaultroute", "noipdefault",
		"noproxyarp", "nopersist", "maxfail", "1", "holdoff", "0", "unit", fmt.Sprint(s.unit), "mtu", mtu, "mru", mtu,
		"lcp-echo-interval", "15", "lcp-echo-failure", "4", "noccp", "novj", "ipparam", fmt.Sprintf("cbpool%d", s.k))
	pr, pw := io.Pipe()
	cmd.Stdout, cmd.Stderr = pw, pw
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGTERM}
	if err := cmd.Start(); err != nil {
		return false, false, fmt.Errorf("không chạy được pppd: %v", err)
	}
	s.pmu.Lock()
	s.proc = cmd.Process
	s.pmu.Unlock()
	lastLine := ""
	var llMu sync.Mutex
	go func() {
		sc := bufio.NewScanner(pr)
		for sc.Scan() {
			l := strings.TrimSpace(sc.Text())
			if l == "" {
				continue
			}
			llMu.Lock()
			ll := strings.ToLower(l)
			if strings.Contains(ll, "auth") && (strings.Contains(ll, "fail") || strings.Contains(ll, "reject")) {
				lastLine = "nhà mạng từ chối tài khoản PPPoE (sai user / mật khẩu, hoặc đã đủ số phiên): " + l
			} else if strings.Contains(ll, "timeout waiting for pado") || strings.Contains(ll, "unable to complete pppoe discovery") {
				lastLine = "không thấy máy chủ PPPoE của nhà mạng (modem chưa cho PPPoE đi qua)"
			} else if lastLine == "" || !strings.HasPrefix(lastLine, "nhà mạng") {
				lastLine = l
			}
			llMu.Unlock()
		}
	}()
	exit := make(chan error, 1)
	go func() { exit <- cmd.Wait(); pw.Close() }()
	ifn := fmt.Sprintf("ppp%d", s.unit)
	tick := time.NewTicker(500 * time.Millisecond)
	defer tick.Stop()
	upAt := time.Time{}
	kill := func() {
		syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
		select {
		case <-exit:
		case <-time.After(8 * time.Second):
			syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			<-exit
		}
	}
	defer func() {
		s.pmu.Lock()
		s.proc = nil
		s.pmu.Unlock()
	}()
	for {
		select {
		case <-s.stop:
			kill()
			return !upAt.IsZero(), false, nil
		case <-s.kick:
			logf("PPPoE phiên %d: quay lại để đổi IP", s.k)
			kill()
			return !upAt.IsZero(), true, nil
		case err := <-exit:
			llMu.Lock()
			ll := lastLine
			llMu.Unlock()
			if ll == "" && err != nil {
				ll = err.Error()
			}
			if upAt.IsZero() {
				return false, false, fmt.Errorf("pppd thoát: %s", ll)
			}
			return true, false, fmt.Errorf("phiên rớt: %s", ll)
		case <-tick.C:
			ip := ifIPv4(ifn)
			if ip == nil {
				if upAt.IsZero() {
					continue
				}
				kill()
				return true, false, errors.New("mất IP")
			}
			cur := s.curIP()
			if cur == nil || !cur.Equal(ip) {
				if err := s.route(c, ifn, ip); err != nil {
					logf("PPPoE phiên %d: đặt đường đi lỗi: %v", s.k, err)
				}
				if upAt.IsZero() {
					upAt = time.Now()
				}
				s.set(func() { s.ip, s.up, s.since, s.err = ip, true, time.Now(), ""; s.gen++ })
				logf("PPPoE phiên %d: lên %s (%s)", s.k, ip, ifn)
			}
		}
	}
}

func (s *sess) curIP() net.IP {
	s.parent.mu.Lock()
	defer s.parent.mu.Unlock()
	if !s.up {
		return nil
	}
	return s.ip
}

func ifIPv4(name string) net.IP {
	ifc, err := net.InterfaceByName(name)
	if err != nil || ifc.Flags&net.FlagUp == 0 {
		return nil
	}
	as, err := ifc.Addrs()
	if err != nil {
		return nil
	}
	for _, a := range as {
		if n, ok := a.(*net.IPNet); ok {
			if v4 := n.IP.To4(); v4 != nil {
				return v4
			}
		}
	}
	return nil
}

func (s *sess) route(c *Conf, ifn string, ip net.IP) error {
	t := fmt.Sprint(c.Ppp.Table0 + s.k)
	prio := fmt.Sprint(c.Ppp.Table0 + s.k)
	if err := ipCmd("route", "replace", "default", "dev", ifn, "table", t); err != nil {
		return err
	}
	for i := 0; i < 4 && ipCmd("rule", "del", "priority", prio) == nil; i++ {
	}
	return ipCmd("rule", "add", "from", ip.String()+"/32", "lookup", t, "priority", prio)
}

func (s *sess) cleanupRoute(c *Conf) {
	prio := fmt.Sprint(c.Ppp.Table0 + s.k)
	for i := 0; i < 4 && ipCmd("rule", "del", "priority", prio) == nil; i++ {
	}
	ipCmd("route", "flush", "table", fmt.Sprint(c.Ppp.Table0+s.k))
}

func (s *sess) cleanup() {
	m := s.parent
	m.mu.Lock()
	c := m.c
	m.mu.Unlock()
	s.cleanupRoute(c)
	if s.mv != "" {
		ipCmd("link", "del", s.mv)
	}
	s.set(func() { s.up, s.ip = false, nil })
}

// ---------------------------------------------------------------- dò máy chủ PPPoE (PADI → PADO), không cần tài khoản

type pado struct {
	Mac     string `json:"mac"`
	AC      string `json:"ac"`
	Service string `json:"service,omitempty"`
	Err     string `json:"err,omitempty"`
}

func htons(v uint16) uint16 { return v<<8 | v>>8 }

func pppoeDiscover(iface string, wait time.Duration) ([]pado, error) {
	ifc, err := net.InterfaceByName(iface)
	if err != nil {
		return nil, fmt.Errorf("không có card %s", iface)
	}
	const ethDisc = 0x8863
	fd, err := syscall.Socket(syscall.AF_PACKET, syscall.SOCK_DGRAM, int(htons(ethDisc)))
	if err != nil {
		return nil, fmt.Errorf("mở ổ cắm PPPoE lỗi (cần root): %v", err)
	}
	defer syscall.Close(fd)
	if err := syscall.Bind(fd, &syscall.SockaddrLinklayer{Protocol: htons(ethDisc), Ifindex: ifc.Index}); err != nil {
		return nil, err
	}
	hu := make([]byte, 8)
	rand.Read(hu)
	tags := []byte{0x01, 0x01, 0, 0} // Service-Name rỗng (dịch vụ nào cũng được)
	tags = append(tags, 0x01, 0x03, 0, 8)
	tags = append(tags, hu...)
	pkt := []byte{0x11, 0x09, 0, 0, 0, 0}
	binary.BigEndian.PutUint16(pkt[4:], uint16(len(tags)))
	pkt = append(pkt, tags...)
	bc := &syscall.SockaddrLinklayer{Protocol: htons(ethDisc), Ifindex: ifc.Index, Halen: 6}
	copy(bc.Addr[:], []byte{0xff, 0xff, 0xff, 0xff, 0xff, 0xff})
	tv := syscall.Timeval{Usec: 200000}
	syscall.SetsockoptTimeval(fd, syscall.SOL_SOCKET, syscall.SO_RCVTIMEO, &tv)
	seen := map[string]bool{}
	var res []pado
	end := time.Now().Add(wait)
	nextSend := time.Time{}
	buf := make([]byte, 1600)
	for time.Now().Before(end) {
		if time.Now().After(nextSend) {
			syscall.Sendto(fd, pkt, 0, bc)
			nextSend = time.Now().Add(time.Second)
		}
		n, from, err := syscall.Recvfrom(fd, buf, 0)
		if err != nil || n < 6 {
			continue
		}
		b := buf[:n]
		if b[0] != 0x11 || b[1] != 0x07 { // chỉ PADO
			continue
		}
		l := int(binary.BigEndian.Uint16(b[4:6]))
		if 6+l > n {
			l = n - 6
		}
		mac := ""
		if ll, ok := from.(*syscall.SockaddrLinklayer); ok {
			mac = net.HardwareAddr(ll.Addr[:6]).String()
		}
		o := pado{Mac: mac}
		mine := false
		for t := b[6 : 6+l]; len(t) >= 4; {
			tt, tl := binary.BigEndian.Uint16(t[0:2]), int(binary.BigEndian.Uint16(t[2:4]))
			if 4+tl > len(t) {
				break
			}
			v := t[4 : 4+tl]
			switch tt {
			case 0x0102:
				o.AC = string(v)
			case 0x0101:
				if o.Service == "" {
					o.Service = string(v)
				}
			case 0x0103:
				mine = string(v) == string(hu)
			case 0x0201, 0x0202, 0x0203:
				o.Err = string(v)
			}
			t = t[4+tl:]
		}
		if !mine || seen[o.Mac+o.AC] {
			continue
		}
		seen[o.Mac+o.AC] = true
		res = append(res, o)
	}
	return res, nil
}

func defaultIface(c *Conf) string {
	if c.Ppp.Iface != "" {
		return c.Ppp.Iface
	}
	if c.Iface6 != "" {
		return c.Iface6
	}
	if _, err := net.InterfaceByName("vmbr0"); err == nil {
		return "vmbr0"
	}
	if b, err := os.ReadFile("/proc/net/route"); err == nil { // card có đường mặc định
		for _, l := range strings.Split(string(b), "\n")[1:] {
			f := strings.Fields(l)
			if len(f) > 2 && f[1] == "00000000" {
				return f[0]
			}
		}
	}
	return ""
}

func pppTestCmd(c *Conf, iface string, dial int, wait time.Duration) int {
	if iface == "" {
		iface = defaultIface(c)
	}
	fmt.Printf("Dò máy chủ PPPoE của nhà mạng trên card %s (%v, KHÔNG dùng mật khẩu)…\n", iface, wait)
	r, err := pppoeDiscover(iface, wait)
	if err != nil {
		fmt.Println("✗", err)
		return 1
	}
	if len(r) == 0 {
		fmt.Println("✗ Không có trả lời: modem đang KHÔNG cho PPPoE từ mạng nội bộ đi ra (cần bật bridge / PPPoE passthrough).")
		out(map[string]interface{}{"ok": false, "iface": iface, "pado": r})
		return 3
	}
	for _, o := range r {
		fmt.Printf("✓ Máy chủ PPPoE trả lời: %s (MAC %s)%s\n", o.AC, o.Mac, map[bool]string{true: " — lỗi: " + o.Err, false: ""}[o.Err != ""])
	}
	if dial <= 0 {
		fmt.Println("→ Modem cho PPPoE đi qua. Bước tiếp: cbpool ppp-set (nhập tài khoản), rồi cbpool ppp-test --dial 2")
		out(map[string]interface{}{"ok": true, "iface": iface, "pado": r})
		return 0
	}
	sec, err := loadSecret(c)
	if err != nil {
		fmt.Println("✗ Chưa có tài khoản PPPoE:", err, "→ gõ: cbpool ppp-set")
		return 1
	}
	if dial > 8 {
		dial = 8
	}
	fmt.Printf("\n⚠ Sắp quay thử %d phiên bằng tài khoản %s***. Nếu nhà mạng chỉ cho 1 phiên, mạng CHÍNH của modem có thể rớt vài giây.\n", dial, safePrefix(sec.User))
	if isTTY(0) {
		fmt.Print("Gõ co rồi Enter để quay thử: ")
		l, _ := bufio.NewReader(os.Stdin).ReadString('\n')
		if strings.TrimSpace(strings.ToLower(l)) != "co" {
			fmt.Println("Thôi, không quay.")
			return 1
		}
	}
	tc := *c
	tc.Ppp.Unit0, tc.Ppp.Table0, tc.Ppp.MvPrefix = 200, 2300, "cbpt" // khác số / tên với phiên thật đang chạy
	st := &PState{Macs: map[string]string{}}
	m := newPppMgr(&tc, st, nil)
	m.configure(sec, dial, iface)
	defer m.stopAll()
	end := time.Now().Add(45 * time.Second)
	for time.Now().Before(end) {
		if s := m.status(); s["up"].(int) >= dial {
			break
		}
		time.Sleep(time.Second)
	}
	s := m.status()
	ips := map[string]bool{}
	for _, x := range s["sess"].([]map[string]interface{}) {
		if ip, ok := x["ip"].(string); ok {
			pub := publicIP(net.ParseIP(ip))
			if pub != "" {
				x["public"] = pub
			}
			ips[ip] = true
			fmt.Printf("  phiên %v: ✓ IP %s%s\n", x["k"], ip, map[bool]string{true: " · ra Internet bằng " + pub, false: ""}[pub != ""])
		} else {
			fmt.Printf("  phiên %v: ✗ %v\n", x["k"], x["err"])
		}
	}
	fmt.Printf("→ %d/%d phiên lên, %d IP khác nhau.\n", s["up"], dial, len(ips))
	out(s)
	if len(ips) >= 2 {
		return 0
	}
	return 4
}

func safePrefix(u string) string {
	if len(u) > 3 {
		return u[:3]
	}
	return u
}

// publicIP: IP công khai nhìn từ ngoài khi đi bằng IP phiên (hỏi api.ipify.org, cổng 80, gắn đúng IP nguồn).
func publicIP(src net.IP) string {
	if src == nil {
		return ""
	}
	d := net.Dialer{Timeout: 6 * time.Second, LocalAddr: &net.TCPAddr{IP: src}}
	c, err := d.Dial("tcp4", "api.ipify.org:80")
	if err != nil {
		return ""
	}
	defer c.Close()
	c.SetDeadline(time.Now().Add(8 * time.Second))
	io.WriteString(c, "GET / HTTP/1.1\r\nHost: api.ipify.org\r\nUser-Agent: cbpool\r\nConnection: close\r\n\r\n")
	b, _ := io.ReadAll(io.LimitReader(c, 4096))
	parts := strings.SplitN(string(b), "\r\n\r\n", 2)
	if len(parts) != 2 {
		return ""
	}
	ip := strings.TrimSpace(parts[1])
	if net.ParseIP(ip) == nil {
		return ""
	}
	return ip
}

// ---------------------------------------------------------------- nhập tài khoản PPPoE (chỉ lưu trên máy này)

func isTTY(fd int) bool {
	var t syscall.Termios
	_, _, e := syscall.Syscall(syscall.SYS_IOCTL, uintptr(fd), syscall.TCGETS, uintptr(unsafe.Pointer(&t)))
	return e == 0
}

func readHidden() (string, error) {
	var old syscall.Termios
	if _, _, e := syscall.Syscall(syscall.SYS_IOCTL, 0, syscall.TCGETS, uintptr(unsafe.Pointer(&old))); e != 0 {
		l, err := bufio.NewReader(os.Stdin).ReadString('\n')
		return strings.TrimRight(l, "\r\n"), err
	}
	nw := old
	nw.Lflag &^= syscall.ECHO
	syscall.Syscall(syscall.SYS_IOCTL, 0, syscall.TCSETS, uintptr(unsafe.Pointer(&nw)))
	defer syscall.Syscall(syscall.SYS_IOCTL, 0, syscall.TCSETS, uintptr(unsafe.Pointer(&old)))
	l, err := bufio.NewReader(os.Stdin).ReadString('\n')
	fmt.Println()
	return strings.TrimRight(l, "\r\n"), err
}

func pppSetCmd(c *Conf) int {
	in := bufio.NewReader(os.Stdin)
	fmt.Println("Nhập tài khoản PPPoE của đường mạng (FPT cấp). Mật khẩu chỉ lưu trên máy này (" + c.Ppp.Secret + ", quyền 600).")
	fmt.Print("Tên đăng nhập PPPoE: ")
	u, _ := in.ReadString('\n')
	u = strings.TrimSpace(u)
	if u == "" {
		fmt.Println("Thôi (không nhập gì).")
		return 1
	}
	fmt.Print("Mật khẩu PPPoE (gõ không hiện chữ): ")
	pw, err := readHidden()
	if err != nil || pw == "" {
		fmt.Println("Thôi (không có mật khẩu).")
		return 1
	}
	fmt.Print("Số phiên muốn quay (mỗi phiên 1 IPv4, mặc định 4): ")
	ns, _ := in.ReadString('\n')
	n := 4
	fmt.Sscanf(strings.TrimSpace(ns), "%d", &n)
	if n < 0 {
		n = 0
	}
	if n > 64 {
		n = 64
	}
	b, _ := json.Marshal(PppSecret{User: u, Pass: pw, Sessions: n})
	os.MkdirAll(filepath.Dir(c.Ppp.Secret), 0700)
	if err := os.WriteFile(c.Ppp.Secret+".tmp", b, 0600); err != nil {
		fmt.Println("✗ Không ghi được:", err)
		return 1
	}
	os.Rename(c.Ppp.Secret+".tmp", c.Ppp.Secret)
	fmt.Printf("✓ Đã lưu tài khoản %s***, %d phiên.\n", safePrefix(u), n)
	if pppPlugin() == "" {
		fmt.Println("Máy chưa có pppd → cài gói ppp…")
		cmd := exec.Command("apt-get", "install", "-y", "ppp")
		cmd.Env = append(os.Environ(), "DEBIAN_FRONTEND=noninteractive")
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		if err := cmd.Run(); err != nil {
			fmt.Println("✗ Cài ppp lỗi:", err)
		}
	}
	if r, err := ctlCall(c.Ctl, map[string]string{"cmd": "reload"}, 20*time.Second); err == nil {
		var st map[string]interface{}
		json.Unmarshal(r, &st)
		if pp, ok := st["ppp"].(map[string]interface{}); ok {
			fmt.Printf("cbpool đã nhận: %v phiên (đang lên %v). Xem: cbpool status\n", pp["want"], pp["up"])
		}
	} else {
		fmt.Println("(cbpool chưa chạy — lần chạy tới sẽ dùng tài khoản này)")
	}
	fmt.Println("Thử: cbpool ppp-test (dò, không mật khẩu) · cbpool ppp-test --dial 2 (quay thử 2 phiên)")
	return 0
}
