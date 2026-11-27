package main

// Bộ thử chạy trong không gian mạng riêng (root):  go test -c -o /tmp/cbpool.test && unshare -n env CBPOOL_NETNS_TEST=1 /tmp/cbpool.test -test.v
// Giả lập: card lo có dải 2001:db8:1::/64 (như SLAAC của modem), máy đích 2001:db8:1::1 + 127.0.0.1 (cho phép làm đích qua allow_dst).

import (
	"bufio"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func hasV6() bool {
	ln, err := net.Listen("tcp6", "[::1]:0")
	if err != nil {
		return false
	}
	ln.Close()
	_, err = os.Stat(procInet6)
	return err == nil
}

func needV6(t *testing.T) {
	needNetns(t)
	if !hasV6() {
		t.Skip("máy thử không có IPv6 (chạy phần IPv6 trên CI)")
	}
}

func needNetns(t *testing.T) {
	if os.Getenv("CBPOOL_NETNS_TEST") != "1" || os.Getuid() != 0 {
		t.Skip("cần root trong không gian mạng riêng (CBPOOL_NETNS_TEST=1)")
	}
}

// máy đích: trả lại "IP:cổng" của người kết nối, rồi đóng. Có thêm HTTP nhỏ ở /who và /big.
func whoServer(t *testing.T, addr string) net.Listener {
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatalf("mở máy đích %s: %v", addr, err)
	}
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				c.SetDeadline(time.Now().Add(20 * time.Second))
				br := bufio.NewReader(c)
				l, err := br.ReadString('\n')
				if err != nil {
					return
				}
				who := c.RemoteAddr().(*net.TCPAddr).IP.String()
				if strings.HasPrefix(l, "GET /big") {
					for {
						h, _ := br.ReadString('\n')
						if strings.TrimSpace(h) == "" {
							break
						}
					}
					body := strings.Repeat("x", 200*1024)
					fmt.Fprintf(c, "HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s", len(body), body)
					return
				}
				if strings.HasPrefix(l, "GET ") {
					for {
						h, _ := br.ReadString('\n')
						if strings.TrimSpace(h) == "" {
							break
						}
					}
					fmt.Fprintf(c, "HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s", len(who), who)
					return
				}
				io.WriteString(c, who)
			}(c)
		}
	}()
	return ln
}

func socksDial(t *testing.T, proxy, user, pass string, atyp byte, host string, port int) (net.Conn, byte) {
	c, err := net.DialTimeout("tcp", proxy, 3*time.Second)
	if err != nil {
		t.Fatalf("nối proxy: %v", err)
	}
	c.SetDeadline(time.Now().Add(20 * time.Second))
	c.Write([]byte{5, 1, 2})
	b := make([]byte, 2)
	if _, err := io.ReadFull(c, b); err != nil || b[1] != 2 {
		c.Close()
		return nil, 0xff
	}
	m := []byte{1, byte(len(user))}
	m = append(m, user...)
	m = append(m, byte(len(pass)))
	m = append(m, pass...)
	c.Write(m)
	if _, err := io.ReadFull(c, b); err != nil || b[1] != 0 {
		c.Close()
		return nil, 0xfe
	}
	req := []byte{5, 1, 0, atyp}
	switch atyp {
	case 1:
		req = append(req, net.ParseIP(host).To4()...)
	case 4:
		req = append(req, net.ParseIP(host).To16()...)
	case 3:
		req = append(req, byte(len(host)))
		req = append(req, host...)
	}
	pb := make([]byte, 2)
	binary.BigEndian.PutUint16(pb, uint16(port))
	req = append(req, pb...)
	c.Write(req)
	h := make([]byte, 4)
	if _, err := io.ReadFull(c, h); err != nil {
		c.Close()
		return nil, 0xfd
	}
	if h[1] != 0 {
		c.Close()
		return nil, h[1]
	}
	skip := 4 + 2
	if h[3] == 4 {
		skip = 16 + 2
	}
	io.ReadFull(c, make([]byte, skip))
	return c, 0
}

func readAll(c net.Conn) string {
	io.WriteString(c, "WHO\n")
	b, _ := io.ReadAll(c)
	c.Close()
	return string(b)
}

func setupPool(t *testing.T, extra map[string]interface{}) (*Pool, string, string) {
	lo, err := net.InterfaceByName("lo")
	if err != nil {
		t.Fatal(err)
	}
	if err := linkUp(lo.Index); err != nil {
		t.Fatalf("bật lo: %v", err)
	}
	addr6AddPlain(lo.Index, net.ParseIP("2001:db8:1::5"), 64) // "SLAAC"
	addr6AddPlain(lo.Index, net.ParseIP("2001:db8:1::1"), 128)
	dir := t.TempDir()
	cf := map[string]interface{}{"listen": "127.0.0.1:0", "iface6": "lo", "slots": 3, "allow_dst": []string{"127.0.0.0/8"},
		"state_dir": filepath.Join(dir, "st"), "ctl": filepath.Join(dir, "ctl.sock"), "bw_kbps": 0}
	for k, v := range extra {
		cf[k] = v
	}
	b, _ := json.Marshal(cf)
	path := filepath.Join(dir, "cbpool.json")
	os.WriteFile(path, b, 0600)
	c, err := loadConf(path)
	if err != nil {
		t.Fatal(err)
	}
	if v, ok := extra["bw_kbps"]; ok && v.(int) < 0 {
		c.BwKbps = 0
	}
	p, err := newPool(c)
	if err != nil {
		t.Fatal(err)
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	p.start()
	go p.serve(ln)
	go p.ctlServe()
	t.Cleanup(func() { ln.Close(); p.stop() })
	for i := 0; i < 50 && hasV6(); i++ { // chờ vòng IPv6 đầu tiên
		p.mu.RLock()
		ok := len(p.slots) > 0 && p.slots[0].ip6 != nil
		p.mu.RUnlock()
		if ok {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	return p, ln.Addr().String(), c.Ctl
}

func TestProxyV6PerSlot(t *testing.T) {
	needV6(t)
	tgt := whoServer(t, "[2001:db8:1::1]:8080")
	defer tgt.Close()
	tgt4 := whoServer(t, "127.0.0.1:8081")
	defer tgt4.Close()
	p, px, ctl := setupPool(t, nil)
	seen := map[string]bool{}
	for _, s := range p.slots {
		c, rep := socksDial(t, px, s.ID, s.Pass, 4, "2001:db8:1::1", 8080)
		if rep != 0 {
			t.Fatalf("%s: SOCKS5 trả %d", s.ID, rep)
		}
		who := readAll(c)
		want := joinIID(&net.IPNet{IP: net.ParseIP("2001:db8:1::"), Mask: net.CIDRMask(64, 128)}, s.IID).String()
		if who != want {
			t.Fatalf("%s: máy đích thấy %q, muốn %q", s.ID, who, want)
		}
		if seen[who] {
			t.Fatalf("2 ô cùng IP %s", who)
		}
		seen[who] = true
	}
	t.Logf("✓ 3 ô → 3 IPv6 riêng: %v", seen)

	s := p.slots[0]
	if _, rep := socksDial(t, px, s.ID, "sai-mat-khau-123", 4, "2001:db8:1::1", 8080); rep != 0xfe {
		t.Fatalf("sai mật khẩu phải bị từ chối, được %d", rep)
	}
	c, err := net.Dial("tcp", px)
	if err != nil {
		t.Fatal(err)
	}
	c.Write([]byte{5, 1, 0})
	b := make([]byte, 2)
	io.ReadFull(c, b)
	c.Close()
	if b[1] != 0xff {
		t.Fatalf("không user/pass phải bị từ chối (0xff), được %x", b[1])
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 1, "10.1.2.3", 80); rep != 2 {
		t.Fatalf("đích 10.x phải bị chặn (2), được %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 1, "192.168.1.1", 80); rep != 2 {
		t.Fatalf("đích 192.168.x phải bị chặn, được %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 4, "2001:db8:1::1", 25); rep != 2 {
		t.Fatalf("cổng 25 phải bị chặn, được %d", rep)
	}
	t.Log("✓ sai mật khẩu / thiếu user / đích nội bộ / cổng 25 bị chặn")

	// tên miền: có AAAA → IPv6 của ô; chỉ A → IPv4 chung (fallback4)
	lookupIPAddr = func(ctx context.Context, h string) ([]net.IPAddr, error) {
		switch h {
		case "dual.test":
			return []net.IPAddr{{IP: net.ParseIP("127.0.0.1")}, {IP: net.ParseIP("2001:db8:1::1")}}, nil
		case "v4only.test":
			return []net.IPAddr{{IP: net.ParseIP("127.0.0.1")}}, nil
		case "lan.test":
			return []net.IPAddr{{IP: net.ParseIP("192.168.1.10")}}, nil
		}
		return nil, fmt.Errorf("không có")
	}
	defer func() { lookupIPAddr = net.DefaultResolver.LookupIPAddr }()
	c2, rep := socksDial(t, px, s.ID, s.Pass, 3, "dual.test", 8080)
	if rep != 0 {
		t.Fatalf("dual.test: %d", rep)
	}
	if who := readAll(c2); who != s.ip6.String() {
		t.Fatalf("dual.test phải đi IPv6 của ô (%s), thấy %s", s.ip6, who)
	}
	c3, rep := socksDial(t, px, s.ID, s.Pass, 3, "v4only.test", 8081)
	if rep != 0 {
		t.Fatalf("v4only.test: %d", rep)
	}
	if who := readAll(c3); who != "127.0.0.1" {
		t.Fatalf("v4only.test phải đi IPv4 chung, thấy %s", who)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 3, "lan.test", 80); rep != 2 {
		t.Fatalf("tên miền trỏ vào mạng nội bộ phải bị chặn, được %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 3, "khong-co.test", 80); rep != 4 {
		t.Fatalf("tên miền không có phải trả 4, được %d", rep)
	}
	t.Log("✓ tên miền: AAAA → IPv6 ô, chỉ A → IPv4 chung, trỏ nội bộ → chặn, không có → 4")

	// HTTP CONNECT + http://
	hc, _ := net.Dial("tcp", px)
	fmt.Fprintf(hc, "CONNECT [2001:db8:1::1]:8080 HTTP/1.1\r\nHost: x\r\n\r\n")
	l, _ := bufio.NewReader(hc).ReadString('\n')
	hc.Close()
	if !strings.Contains(l, "407") {
		t.Fatalf("HTTP không mật khẩu phải 407, được %q", l)
	}
	au := base64.StdEncoding.EncodeToString([]byte(s.ID + ":" + s.Pass))
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "CONNECT [2001:db8:1::1]:8080 HTTP/1.1\r\nHost: x\r\nProxy-Authorization: Basic %s\r\n\r\n", au)
	br := bufio.NewReader(hc)
	l, _ = br.ReadString('\n')
	br.ReadString('\n')
	if !strings.Contains(l, "200") {
		t.Fatalf("CONNECT phải 200, được %q", l)
	}
	io.WriteString(hc, "WHO\n")
	rest, _ := io.ReadAll(br)
	hc.Close()
	if string(rest) != s.ip6.String() {
		t.Fatalf("CONNECT: máy đích thấy %q", rest)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET http://dual.test:8080/who HTTP/1.1\r\nHost: dual.test:8080\r\nProxy-Authorization: Basic %s\r\nProxy-Connection: keep-alive\r\n\r\n", au)
	all, _ := io.ReadAll(hc)
	hc.Close()
	if !strings.HasSuffix(string(all), s.ip6.String()) || !strings.Contains(string(all), "200 OK") {
		t.Fatalf("GET http:// qua proxy: %q", all)
	}
	t.Log("✓ HTTP: 407 khi thiếu mật khẩu, CONNECT + GET http:// đi IPv6 ô")

	// đổi IP bằng link + ổ cắm điều khiển
	rotGrace = 300 * time.Millisecond
	old := s.ip6.String()
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET /rotate?key=%s HTTP/1.1\r\nHost: x\r\n\r\n", s.Rot)
	all, _ = io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), "\"ok\":true") {
		t.Fatalf("link đổi IP: %q", all)
	}
	c4, _ := socksDial(t, px, s.ID, s.Pass, 4, "2001:db8:1::1", 8080)
	nw := readAll(c4)
	if nw == old || nw != s.ip6.String() {
		t.Fatalf("đổi IP: cũ %s, giờ thấy %s (ô %s)", old, nw, s.ip6)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET /rotate?key=%s HTTP/1.1\r\nHost: x\r\n\r\n", s.Rot)
	all, _ = io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), "429") {
		t.Fatalf("đổi IP liên tục phải bị chặn 10 giây, được %q", all)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET /rotate?key=khoa-sai-khong-ton-tai HTTP/1.1\r\nHost: x\r\n\r\n")
	all, _ = io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), "403") {
		t.Fatalf("khoá sai phải 403: %q", all)
	}
	time.Sleep(400 * time.Millisecond)
	p.v6sync()
	all6, _ := readInet6()
	for _, a := range all6 {
		if a.ip.String() == old {
			t.Fatalf("địa chỉ cũ %s chưa được gỡ sau thời gian chờ", old)
		}
	}
	r, err := ctlCall(ctl, map[string]string{"cmd": "status"}, 5*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	var st map[string]interface{}
	json.Unmarshal(r, &st)
	ss := st["slots"].([]interface{})
	if len(ss) != 3 || ss[0].(map[string]interface{})["ip6"] != s.ip6.String() {
		t.Fatalf("status sai: %s", r)
	}
	if st["v6"].(map[string]interface{})["prefix"] != "2001:db8:1::/64" {
		t.Fatalf("dải sai: %v", st["v6"])
	}
	p.slots[1].lastRot = time.Time{}
	r, _ = ctlCall(ctl, map[string]string{"cmd": "rotate", "slot": "p02", "what": "v6"}, 5*time.Second)
	if !strings.Contains(string(r), "\"ok\":true") {
		t.Fatalf("ctl rotate: %s", r)
	}
	t.Log("✓ đổi IP: link /rotate, chặn đổi liên tục, khoá sai 403, địa chỉ cũ gỡ sau thời gian chờ, ổ cắm điều khiển")
}

func TestPrefixChange(t *testing.T) {
	needV6(t)
	p, _, _ := setupPool(t, map[string]interface{}{"slots": 2})
	lo, _ := net.InterfaceByName("lo")
	old := p.slots[0].ip6.String()
	// modem đổi dải: bỏ 2001:db8:1::5/64, có 2001:db8:2::5/64
	nlDo(nlMsg(21, 0, ifaddrmsg(10, 64, 0, lo.Index), rta(2, net.ParseIP("2001:db8:1::5").To16()), rta(1, net.ParseIP("2001:db8:1::5").To16())))
	addr6AddPlain(lo.Index, net.ParseIP("2001:db8:2::5"), 64)
	p.v6sync()
	nw := p.slots[0].ip6
	if nw == nil || !strings.HasPrefix(nw.String(), "2001:db8:2:") {
		t.Fatalf("đổi dải: ô vẫn %v", nw)
	}
	all, _ := readInet6()
	for _, a := range all {
		if a.ip.String() == old {
			t.Fatalf("địa chỉ dải cũ %s chưa gỡ", old)
		}
	}
	t.Logf("✓ đổi dải: %s → %s, địa chỉ cũ đã gỡ", old, nw)
	// state giữ nguyên mật khẩu qua lần chạy sau
	pass := p.slots[0].Pass
	st := loadState(p.c)
	if st.Slots[0].Pass != pass {
		t.Fatal("mật khẩu ô không được lưu")
	}
}

func TestRateLimitAndAllowFrom(t *testing.T) {
	needNetns(t)
	tgt := whoServer(t, "127.0.0.1:8082")
	defer tgt.Close()
	p, px, _ := setupPool(t, map[string]interface{}{"bw_kbps": 800}) // 100 KB/giây
	s := p.slots[0]
	c, rep := socksDial(t, px, s.ID, s.Pass, 1, "127.0.0.1", 8082)
	if rep != 0 {
		t.Fatal(rep)
	}
	t0 := time.Now()
	io.WriteString(c, "GET /big HTTP/1.1\r\nHost: x\r\n\r\n")
	n, _ := io.Copy(io.Discard, c)
	c.Close()
	el := time.Since(t0)
	if n < 200*1024 || el < 1200*time.Millisecond {
		t.Fatalf("giới hạn tốc độ: %d byte trong %v (phải ≥ 1,2 giây ở 100 KB/giây)", n, el)
	}
	if s.down < 200*1024 {
		t.Fatalf("đếm byte xuống sai: %d", s.down)
	}
	t.Logf("✓ giới hạn tốc độ: %d KB trong %v", n/1024, el.Round(time.Millisecond))

	p2, px2, _ := setupPool(t, map[string]interface{}{"allow_from": []string{"10.0.0.0/8"}})
	_ = p2
	cc, err := net.Dial("tcp", px2)
	if err == nil {
		cc.SetDeadline(time.Now().Add(2 * time.Second))
		cc.Write([]byte{5, 1, 2})
		b := make([]byte, 2)
		if _, err := io.ReadFull(cc, b); err == nil {
			t.Fatal("máy ngoài allow_from vẫn dùng được proxy")
		}
		cc.Close()
	}
	t.Log("✓ allow_from: máy ngoài dải bị đóng kết nối")
}

// Phần lõi chỉ IPv4 (chạy được cả ở máy không có IPv6): mật khẩu, chặn đích, HTTP, tên miền, link đổi IP, ổ cắm điều khiển.
func TestProxyCoreV4(t *testing.T) {
	needNetns(t)
	tgt := whoServer(t, "127.0.0.1:8083")
	defer tgt.Close()
	p, px, ctl := setupPool(t, map[string]interface{}{"v6": false})
	s := p.slots[1]
	c, rep := socksDial(t, px, s.ID, s.Pass, 1, "127.0.0.1", 8083)
	if rep != 0 {
		t.Fatalf("SOCKS5 IPv4: %d", rep)
	}
	if who := readAll(c); who != "127.0.0.1" {
		t.Fatalf("máy đích thấy %q", who)
	}
	if _, rep := socksDial(t, px, s.ID, "sai-mat-khau-123", 1, "127.0.0.1", 8083); rep != 0xfe {
		t.Fatalf("sai mật khẩu: %d", rep)
	}
	if _, rep := socksDial(t, px, "p99", s.Pass, 1, "127.0.0.1", 8083); rep != 0xfe {
		t.Fatalf("ô không có: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 1, "10.1.2.3", 80); rep != 2 {
		t.Fatalf("10.x phải bị chặn: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 1, "169.254.169.254", 80); rep != 2 {
		t.Fatalf("169.254 phải bị chặn: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 1, "127.0.0.1", 25); rep != 2 {
		t.Fatalf("cổng 25 phải bị chặn: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 4, "2001:db8:1::1", 80); rep != 4 {
		t.Fatalf("ô không có IPv6 mà đích chỉ IPv6 → 4, được %d", rep)
	}
	lookupIPAddr = func(ctx context.Context, h string) ([]net.IPAddr, error) {
		switch h {
		case "v4only.test":
			return []net.IPAddr{{IP: net.ParseIP("127.0.0.1")}}, nil
		case "lan.test":
			return []net.IPAddr{{IP: net.ParseIP("192.168.1.10")}, {IP: net.ParseIP("fd00::1")}}, nil
		}
		return nil, fmt.Errorf("không có")
	}
	defer func() { lookupIPAddr = net.DefaultResolver.LookupIPAddr }()
	c3, rep := socksDial(t, px, s.ID, s.Pass, 3, "v4only.test", 8083)
	if rep != 0 || readAll(c3) != "127.0.0.1" {
		t.Fatalf("tên miền IPv4: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 3, "lan.test", 80); rep != 2 {
		t.Fatalf("tên miền trỏ nội bộ → chặn: %d", rep)
	}
	if _, rep := socksDial(t, px, s.ID, s.Pass, 3, "khong-co.test", 80); rep != 4 {
		t.Fatalf("tên miền không có → 4: %d", rep)
	}
	au := base64.StdEncoding.EncodeToString([]byte(s.ID + ":" + s.Pass))
	hc, _ := net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET http://v4only.test:8083/who HTTP/1.1\r\nHost: v4only.test:8083\r\n\r\n")
	all, _ := io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), "407") {
		t.Fatalf("thiếu mật khẩu HTTP → 407: %q", all)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET http://v4only.test:8083/who HTTP/1.1\r\nHost: v4only.test:8083\r\nProxy-Authorization: Basic %s\r\n\r\n", au)
	all, _ = io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), "200 OK") || !strings.HasSuffix(string(all), "127.0.0.1") {
		t.Fatalf("GET http://: %q", all)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "CONNECT 127.0.0.1:8083 HTTP/1.1\r\nProxy-Authorization: Basic %s\r\n\r\n", au)
	br := bufio.NewReader(hc)
	l, _ := br.ReadString('\n')
	br.ReadString('\n')
	io.WriteString(hc, "WHO\n")
	rest, _ := io.ReadAll(br)
	hc.Close()
	if !strings.Contains(l, "200") || string(rest) != "127.0.0.1" {
		t.Fatalf("CONNECT: %q %q", l, rest)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "CONNECT 10.0.0.1:443 HTTP/1.1\r\nProxy-Authorization: Basic %s\r\n\r\n", au)
	l, _ = bufio.NewReader(hc).ReadString('\n')
	hc.Close()
	if !strings.Contains(l, "403") {
		t.Fatalf("CONNECT nội bộ → 403: %q", l)
	}
	hc, _ = net.Dial("tcp", px)
	fmt.Fprintf(hc, "GET /ip?key=%s HTTP/1.1\r\nHost: x\r\n\r\n", s.Rot)
	all, _ = io.ReadAll(hc)
	hc.Close()
	if !strings.Contains(string(all), `"id":"p02"`) {
		t.Fatalf("/ip: %q", all)
	}
	r, err := ctlCall(ctl, map[string]string{"cmd": "status"}, 5*time.Second)
	if err != nil || !strings.Contains(string(r), `"slots"`) || !strings.Contains(string(r), s.Pass) {
		t.Fatalf("status: %v %s", err, r)
	}
	r, _ = ctlCall(ctl, map[string]string{"cmd": "rotate", "slot": "p02", "what": "v4"}, 5*time.Second)
	if !strings.Contains(string(r), "PPPoE") {
		t.Fatalf("đổi IPv4 khi chưa có PPPoE phải báo rõ: %s", r)
	}
	r, _ = ctlCall(ctl, map[string]string{"cmd": "rotate", "slot": "p77"}, 5*time.Second)
	if !strings.Contains(string(r), "không có ô") {
		t.Fatalf("ô lạ: %s", r)
	}
	st := p.status()
	if st["ppp"].(map[string]interface{})["want"].(int) != 0 {
		t.Fatalf("ppp phải tắt: %v", st["ppp"])
	}
	t.Log("✓ lõi IPv4: mật khẩu, chặn nội bộ / 169.254 / cổng 25, tên miền, HTTP 407 / GET / CONNECT / 403, /ip, ổ cắm điều khiển")
}
