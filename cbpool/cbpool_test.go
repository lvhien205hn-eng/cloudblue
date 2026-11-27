package main

// Bộ thử chạy trong không gian mạng riêng (root):  go test -c -o /tmp/cbpool.test && unshare -n env CBPOOL_NETNS_TEST=1 /tmp/cbpool.test -test.v
// Giả lập: card lo có dải 2001:db8:1::/64 (như SLAAC của modem), máy đích 2001:db8:1::1 + 127.0.0.1 (cho phép làm đích qua allow_dst).

import (
	"bufio"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func hasV6() bool {
	if lo, err := net.InterfaceByName("lo"); err == nil {
		linkUp(lo.Index) // không gian mạng mới: lo đang tắt → ::1 chưa có
		time.Sleep(50 * time.Millisecond)
	}
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
	p, px, ctl := setupPool(t, nil) // trước máy đích: dựng địa chỉ 2001:db8:1::1 trên lo
	tgt := whoServer(t, "[2001:db8:1::1]:8080")
	defer tgt.Close()
	tgt4 := whoServer(t, "127.0.0.1:8081")
	defer tgt4.Close()
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

// 27.11b · tự dò PPPoE: không cần mạng thật (thay hàm dò bằng hàm giả)
func discTestPool(t *testing.T, extra string) *Pool {
	dir := t.TempDir()
	path := filepath.Join(dir, "cbpool.json")
	cf := fmt.Sprintf(`{"listen":"127.0.0.1:0","iface6":"lo","slots":2,"state_dir":%q,"ctl":%q%s}`, filepath.Join(dir, "st"), filepath.Join(dir, "ctl.sock"), extra)
	if err := os.WriteFile(path, []byte(cf), 0600); err != nil {
		t.Fatal(err)
	}
	c, err := loadConf(path)
	if err != nil {
		t.Fatal(err)
	}
	p, err := newPool(c)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func TestDiscProbe(t *testing.T) {
	var calls int32
	var lastIf atomic.Value
	pppoeDiscoverFn = func(ifc string, w time.Duration) ([]pado, error) {
		atomic.AddInt32(&calls, 1)
		lastIf.Store(ifc)
		return []pado{{Mac: "02:00:00:00:00:01", AC: "cbtest-ac"}, {Mac: "02:00:00:00:00:02", AC: "cbtest-ac"}, {Mac: "02:00:00:00:00:03", AC: ""}}, nil
	}
	oldFirst := discFirst
	defer func() { pppoeDiscoverFn = pppoeDiscover; discFirst = oldFirst }()

	p := discTestPool(t, "")
	if _, ok := p.status()["ppp"].(map[string]interface{})["disc"]; ok {
		t.Fatal("chưa dò mà status đã có disc")
	}
	d := p.discover()
	if d["ok"] != true || d["iface"] != "lo" || fmt.Sprint(d["ac"]) != "[cbtest-ac ?]" || d["err"] != nil {
		t.Fatalf("dò có trả lời: %v", d)
	}
	b, _ := json.Marshal(p.status())
	var st struct {
		Ppp struct {
			Disc struct {
				Ok    bool     `json:"ok"`
				AC    []string `json:"ac"`
				Iface string   `json:"iface"`
				T     int64    `json:"t"`
			} `json:"disc"`
		} `json:"ppp"`
	}
	if json.Unmarshal(b, &st) != nil || !st.Ppp.Disc.Ok || len(st.Ppp.Disc.AC) != 2 || st.Ppp.Disc.Iface != "lo" || st.Ppp.Disc.T == 0 {
		t.Fatalf("status.ppp.disc: %s", b)
	}
	pppoeDiscoverFn = func(string, time.Duration) ([]pado, error) { return nil, nil }
	if d := p.discover(); d["ok"] != false || d["err"] != nil {
		t.Fatalf("không trả lời → ok=false: %v", d)
	}
	pppoeDiscoverFn = func(string, time.Duration) ([]pado, error) {
		return nil, errors.New("mở ổ cắm PPPoE lỗi (cần root)")
	}
	if d := p.discover(); d["err"] != "mở ổ cắm PPPoE lỗi (cần root)" || d["ok"] != nil {
		t.Fatalf("lỗi dò: %v", d)
	}

	// vòng tự dò: bật lên dò 1 lần; probe=false → không dò; card riêng cho PPPoE được ưu tiên
	pppoeDiscoverFn = func(ifc string, w time.Duration) ([]pado, error) {
		atomic.AddInt32(&calls, 1)
		lastIf.Store(ifc)
		return nil, nil
	}
	discFirst = 20 * time.Millisecond
	for _, tc := range []struct {
		extra string
		want  int32
		ifc   string
	}{{"", 1, "lo"}, {`,"ppp":{"probe":false}`, 0, ""}, {`,"ppp":{"iface":"cbtest0"}`, 1, "cbtest0"}} {
		atomic.StoreInt32(&calls, 0)
		lastIf.Store("")
		q := discTestPool(t, tc.extra)
		q.wg.Add(1)
		go q.discLoop()
		time.Sleep(300 * time.Millisecond)
		close(q.stopCh)
		q.wg.Wait()
		if n := atomic.LoadInt32(&calls); n != tc.want || lastIf.Load().(string) != tc.ifc {
			t.Fatalf("%q: dò %d lần trên %q (muốn %d trên %q)", tc.extra, n, lastIf.Load(), tc.want, tc.ifc)
		}
	}

	// lệnh điều khiển "disc" (ổ cắm unix)
	q := discTestPool(t, "")
	go q.ctlServe()
	defer close(q.stopCh)
	var r []byte
	var err error
	for i := 0; i < 50; i++ {
		if r, err = ctlCall(q.c.Ctl, map[string]string{"cmd": "disc"}, 10*time.Second); err == nil {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if err != nil || !strings.Contains(string(r), `"ok":false`) || !strings.Contains(string(r), `"iface":"lo"`) {
		t.Fatalf("ctl disc: %s %v", r, err)
	}
}

// ---------------------------------------------------------------- 27.11c · bán proxy cho khách

// Vector thử tạo bằng WebCrypto (Node, đúng hàm mã hoá của trang Quản trị) với khoá thử ngẫu nhiên — không phải khoá / mật khẩu thật.
const encTestKey = "0RBspaOpwPNKqFgibkOSRRdG/ZnbpBiFp7pcLfsk5X8="
const encTestVec = `{"v":1,"e":"BHMtKcuw42KU86gJzhepdCnh/UKwuV7gG0zzOVMf0Of+Nv/QpUc9qG2+Pvb2lz34iEbNlX55CJOzIx9uHJ/GVyQ=","i":"pBO1WMNOcwVZNWRe","c":"UldmN0a+T4pmiSwU+XAyM9WAJTPABwC29yXzzyGtAlMs11gwskTxY59+EmcbCmQKGT8OEd/8+Y6ljHDtyFhSCUYlmU6TqjtBZRbaxAWxDkUoERA="}`

func TestPppEncInterop(t *testing.T) {
	dir := t.TempDir()
	c := &Conf{StateDir: dir}
	os.WriteFile(keyPath(c), []byte(`{"d":"`+encTestKey+`"}`), 0600)
	priv, err := loadKey(c, false)
	if err != nil {
		t.Fatal(err)
	}
	s, err := decryptPpp(priv, encTestVec)
	if err != nil || s.User != "fpt-test@hn" || s.Pass != "Mật-khẩu thử 123" || s.Sessions != 3 {
		t.Fatalf("giải chuỗi WebCrypto: %+v %v", s, err)
	}
	bad := strings.Replace(encTestVec, `"c":"`, `"c":"A`, 1)
	if _, err := decryptPpp(priv, bad); err == nil {
		t.Fatal("bản mã bị sửa vẫn giải được")
	}
	other, _ := loadKey(&Conf{StateDir: t.TempDir()}, true)
	if _, err := decryptPpp(other, encTestVec); err == nil || !strings.Contains(err.Error(), "máy chủ khác") {
		t.Fatalf("khoá máy khác phải báo không giải được: %v", err)
	}
	k2, _ := loadKey(&Conf{StateDir: dir}, true) // đã có khoá → giữ nguyên, không tạo khoá mới
	if !k2.Equal(priv) {
		t.Fatal("loadKey(create) đã đổi khoá đang có")
	}
	t.Log("✓ WebCrypto (ECDH P-256 + HKDF + AES-GCM) → Go giải đúng; sửa bản mã / khoá khác → từ chối")
}

func writeUsers(t *testing.T, path string, uf usersFile) {
	b, _ := json.Marshal(uf)
	if err := os.WriteFile(path, b, 0600); err != nil {
		t.Fatal(err)
	}
}

// máy đích giữ kết nối mở (để thử cắt kết nối khi khách hết hạn)
func holdServer(t *testing.T, addr string) net.Listener {
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatal(err)
	}
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			go func() { io.Copy(io.Discard, c); c.Close() }()
		}
	}()
	return ln
}

func TestCustAccounts(t *testing.T) {
	needNetns(t)
	dir := t.TempDir()
	uf := filepath.Join(dir, "users.json")
	lf := filepath.Join(dir, "khach.log")
	oldTick := custTick
	custTick = 200 * time.Millisecond
	defer func() { custTick = oldTick }()
	tgt := whoServer(t, "127.0.0.1:8085")
	defer tgt.Close()
	hold := holdServer(t, "127.0.0.1:8086")
	defer hold.Close()
	// 127.0.0.1 KHÔNG nằm trong allow_from → coi như máy ngoài Internet
	p, px, ctl := setupPool(t, map[string]interface{}{"v6": false, "allow_from": []string{"10.0.0.0/8"}, "users_file": uf, "log_file": lf})
	if _, rep := socksDial(t, px, p.slots[0].ID, p.slots[0].Pass, 1, "127.0.0.1", 8085); rep != 0xff {
		t.Fatalf("chưa bán gì: máy ngoài phải bị đóng ngay, được %d", rep)
	}
	now := time.Now().Unix()
	writeUsers(t, uf, usersFile{V: 1, Bw: -1, Fb4: true, Self: []string{"203.0.113.77"}, Users: []custUser{
		{U: "pxtest0001", P: "matkhau-mot", K: "v6", N: "s001", X: now + 3600, S: 1, R: "rotkey-khach-000001"},
		{U: "pxtest0002", P: "matkhau-hai", K: "v4", N: "0", X: now + 3600, S: 2},
		{U: "pxtest0003", P: "matkhau-ba", K: "v6", N: "s002", X: now + 2, S: 3},
		{U: "pxtest0004", P: "ngan", K: "v6", N: "s003", X: now + 3600, S: 1},      // mật khẩu quá ngắn → bỏ
		{U: "pxtest0005", P: "matkhau-nam", K: "v6", N: "x9", X: now + 3600, S: 1}, // ô sai → bỏ
		{U: "pxtest0006", P: "matkhau-sau", K: "v6", N: "s004", X: now - 10, S: 1}, // đã hết hạn → bỏ
	}})
	r, err := ctlCall(ctl, map[string]string{"cmd": "users"}, 10*time.Second)
	if err != nil || !strings.Contains(string(r), `"users":3`) || !strings.Contains(string(r), `"bad":3`) || !strings.Contains(string(r), `"sale4":1`) {
		t.Fatalf("nạp tài khoản khách: %s %v", r, err)
	}
	if k := p.ppp.sessForLocked(0); k != -1 {
		t.Fatalf("chưa có phiên nào → ô nội bộ không có phiên: %d", k)
	}
	if _, rep := socksDial(t, px, p.slots[0].ID, p.slots[0].Pass, 1, "127.0.0.1", 8085); rep != 0xfe {
		t.Fatalf("tài khoản ô nội bộ từ Internet phải bị từ chối: %d", rep)
	}
	c, rep := socksDial(t, px, "pxtest0001", "matkhau-mot", 1, "127.0.0.1", 8085)
	if rep != 0 || readAll(c) != "127.0.0.1" {
		t.Fatalf("khách IPv6 (fb4) từ Internet → đích IPv4: %d", rep)
	}
	if _, rep := socksDial(t, px, "pxtest0002", "matkhau-hai", 1, "127.0.0.1", 8085); rep != 4 {
		t.Fatalf("khách IPv4 mà phiên chưa lên → 4: %d", rep)
	}
	if _, rep := socksDial(t, px, "pxtest0001", "matkhau-mot", 1, "203.0.113.77", 80); rep != 2 {
		t.Fatalf("đích là IP nhà (self) → chặn: %d", rep)
	}
	if _, rep := socksDial(t, px, "pxtest0001", "matkhau-mot", 1, "127.0.0.1", 25); rep != 2 {
		t.Fatalf("cổng 25 → chặn: %d", rep)
	}
	// HTTP CONNECT bằng tài khoản khách
	au := base64.StdEncoding.EncodeToString([]byte("pxtest0001:matkhau-mot"))
	hc, _ := net.Dial("tcp", px)
	fmt.Fprintf(hc, "CONNECT 127.0.0.1:8085 HTTP/1.1\r\nProxy-Authorization: Basic %s\r\n\r\n", au)
	br := bufio.NewReader(hc)
	l, _ := br.ReadString('\n')
	br.ReadString('\n')
	io.WriteString(hc, "WHO\n")
	who, _ := io.ReadAll(br)
	hc.Close()
	if !strings.Contains(l, "200") || string(who) != "127.0.0.1" {
		t.Fatalf("HTTP CONNECT khách: %q %q", l, who)
	}
	// link xem / đổi IP của khách: proxy riêng có khoá; ô chưa có IPv6 → báo lỗi rõ
	get := func(path string) string {
		hc, _ := net.Dial("tcp", px)
		fmt.Fprintf(hc, "GET %s HTTP/1.1\r\nHost: x\r\n\r\n", path)
		b, _ := io.ReadAll(hc)
		hc.Close()
		return string(b)
	}
	if g := get("/ip?key=rotkey-khach-000001"); !strings.Contains(g, `"ok":true`) {
		t.Fatalf("/ip khách: %q", g)
	}
	if g := get("/rotate?key=rotkey-khach-000001"); !strings.Contains(g, "chưa có IPv6") {
		t.Fatalf("/rotate khách khi chưa có IPv6: %q", g)
	}
	if g := get("/rotate?key=" + p.slots[0].Rot); !strings.Contains(g, "403") {
		t.Fatalf("khoá đổi IP ô nội bộ từ Internet phải bị từ chối: %q", g)
	}
	// khách hết hạn → kết nối đang chạy bị cắt
	c3, rep := socksDial(t, px, "pxtest0003", "matkhau-ba", 1, "127.0.0.1", 8086)
	if rep != 0 {
		t.Fatalf("khách sắp hết hạn vẫn vào được lúc còn hạn: %d", rep)
	}
	c3.SetReadDeadline(time.Now().Add(6 * time.Second))
	t0 := time.Now()
	_, e := c3.Read(make([]byte, 1))
	if e == nil || time.Since(t0) > 5900*time.Millisecond {
		t.Fatalf("hết hạn mà kết nối chưa bị cắt: %v", e)
	}
	if _, rep := socksDial(t, px, "pxtest0003", "matkhau-ba", 1, "127.0.0.1", 8085); rep != 0xfe {
		t.Fatalf("khách hết hạn đăng nhập lại phải bị từ chối: %d", rep)
	}
	// nhật ký kết nối khách
	lb, _ := os.ReadFile(lf)
	if !strings.Contains(string(lb), `"u":"pxtest0001"`) || !strings.Contains(string(lb), `"dst":"127.0.0.1:8085"`) || !strings.Contains(string(lb), `"from":"127.0.0.1"`) {
		t.Fatalf("nhật ký khách thiếu: %s", lb)
	}
	// số dùng cho cbhost
	cr, _ := ctlCall(ctl, map[string]string{"cmd": "cust"}, 5*time.Second)
	if !strings.Contains(string(cr), `"u":"pxtest0001"`) || !strings.Contains(string(cr), `"pk":"`) {
		t.Fatalf("ctl cust: %s", cr)
	}
	// dò mật khẩu: 20 lần sai từ 1 IP → IP đó bị chặn (cả mật khẩu đúng)
	for i := 0; i < failMax; i++ {
		socksDial(t, px, "pxtest0001", "sai-mat-khau", 1, "127.0.0.1", 8085)
	}
	if _, rep := socksDial(t, px, "pxtest0001", "matkhau-mot", 1, "127.0.0.1", 8085); rep != 0xff {
		t.Fatalf("IP dò mật khẩu phải bị chặn: %d", rep)
	}
	t.Log("✓ khách: vào từ Internet, ô nội bộ bị chặn từ ngoài, IPv4 chưa có phiên → 4, chặn IP nhà / cổng 25, HTTP CONNECT, /ip /rotate, hết hạn cắt kết nối, nhật ký, chặn dò mật khẩu")
}

func TestCustReserved(t *testing.T) {
	m := &PppMgr{sess: []*sess{{k: 0}, {k: 1}, {k: 2}, {k: 3}}}
	if m.sessForLocked(5) != 1 {
		t.Fatal("không phiên bán: ô 5 → phiên 1")
	}
	m.setReserved(map[int]bool{1: true, 2: true})
	got := []int{m.sessForLocked(0), m.sessForLocked(1), m.sessForLocked(2)}
	if got[0] != 0 || got[1] != 3 || got[2] != 0 {
		t.Fatalf("phiên 1, 2 để bán → ô nội bộ chỉ dùng 0, 3: %v", got)
	}
	m.setReserved(map[int]bool{0: true, 1: true, 2: true, 3: true})
	if m.sessForLocked(0) != -1 {
		t.Fatal("mọi phiên để bán → ô nội bộ không có phiên")
	}
	t.Log("✓ phiên PPPoE để bán không chia cho ô nội bộ")
}
