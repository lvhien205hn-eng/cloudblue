package main

import (
	"bufio"
	"crypto/subtle"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

const (
	idleTO  = 10 * time.Minute
	shakeTO = 20 * time.Second
)

func (p *Pool) serve(ln net.Listener) {
	for {
		c, err := ln.Accept()
		if err != nil {
			var ne net.Error
			if errors.As(err, &ne) && ne.Timeout() {
				continue
			}
			select {
			case <-p.stopCh:
				return
			default:
			}
			time.Sleep(50 * time.Millisecond)
			continue
		}
		go p.handle(c)
	}
}

func (p *Pool) handle(c net.Conn) {
	defer c.Close()
	pub := !p.clientOK(c.RemoteAddr()) // 27.11c · từ Internet: chỉ tài khoản khách, chỉ khi đang bán
	if pub && (!p.custOn() || p.pubBlocked(ipKey(c.RemoteAddr()))) {
		return
	}
	if n := atomic.AddInt32(&p.total, 1); n > int32(p.c.MaxTotal) {
		atomic.AddInt32(&p.total, -1)
		return
	}
	defer atomic.AddInt32(&p.total, -1)
	c.SetDeadline(time.Now().Add(shakeTO))
	br := bufio.NewReaderSize(c, 4096)
	first, err := br.Peek(1)
	if err != nil {
		return
	}
	if first[0] == 0x05 {
		p.socks5(c, br, pub)
	} else {
		p.httpProxy(c, br, pub)
	}
}

// auth: tài khoản khách (mọi nơi, còn hạn) hoặc ô nội bộ (chỉ trong mạng nhà). Sai từ Internet → đếm để chặn dò mật khẩu.
func (p *Pool) auth(user, pass string, pub bool, from net.Addr) *slotRT {
	p.mu.RLock()
	cs := p.cust[user]
	p.mu.RUnlock()
	if cs != nil {
		if subtle.ConstantTimeCompare([]byte(pass), []byte(cs.cu.P)) == 1 && cs.cu.X > time.Now().Unix() {
			return cs
		}
	} else if s := p.slot(user); s != nil && !pub {
		if subtle.ConstantTimeCompare([]byte(pass), []byte(s.Pass)) == 1 {
			return s
		}
	} else {
		subtle.ConstantTimeCompare([]byte(pass), []byte("xxxxxxxxxxxxxxxx"))
	}
	if pub {
		p.pubFail(ipKey(from))
	}
	return nil
}

// begin: giữ chỗ 1 kết nối cho ô / khách (quá giới hạn → false). Khách: ghi vào danh sách để hết hạn / bị bỏ thì cắt được.
func (p *Pool) begin(s *slotRT, c net.Conn) bool {
	lim := int32(p.c.MaxConns)
	if s.cu != nil {
		p.mu.RLock()
		lim = int32(p.custMax)
		p.mu.RUnlock()
	}
	if n := atomic.AddInt32(&s.conns, 1); n > lim {
		atomic.AddInt32(&s.conns, -1)
		return false
	}
	if s.cu != nil {
		s.cu.add(c)
	}
	return true
}

func (p *Pool) end(s *slotRT, c net.Conn) {
	atomic.AddInt32(&s.conns, -1)
	if s.cu != nil {
		s.cu.del(c)
	}
}

// ---------------------------------------------------------------- SOCKS5 (RFC 1928 + user/pass RFC 1929), chỉ CONNECT

func (p *Pool) socks5(c net.Conn, br *bufio.Reader, pub bool) {
	h := make([]byte, 2)
	if _, err := io.ReadFull(br, h); err != nil || h[0] != 5 {
		return
	}
	ms := make([]byte, h[1])
	if _, err := io.ReadFull(br, ms); err != nil {
		return
	}
	hasUP := false
	for _, m := range ms {
		if m == 2 {
			hasUP = true
		}
	}
	if !hasUP {
		c.Write([]byte{5, 0xff})
		return
	}
	c.Write([]byte{5, 2})
	a := make([]byte, 2)
	if _, err := io.ReadFull(br, a); err != nil || a[0] != 1 {
		return
	}
	u := make([]byte, a[1])
	if _, err := io.ReadFull(br, u); err != nil {
		return
	}
	pl := make([]byte, 1)
	if _, err := io.ReadFull(br, pl); err != nil {
		return
	}
	pw := make([]byte, pl[0])
	if _, err := io.ReadFull(br, pw); err != nil {
		return
	}
	s := p.auth(string(u), string(pw), pub, c.RemoteAddr())
	if s == nil {
		c.Write([]byte{1, 1})
		return
	}
	c.Write([]byte{1, 0})
	r := make([]byte, 4)
	if _, err := io.ReadFull(br, r); err != nil || r[0] != 5 {
		return
	}
	var host string
	switch r[3] {
	case 1:
		b := make([]byte, 4)
		if _, err := io.ReadFull(br, b); err != nil {
			return
		}
		host = net.IP(b).String()
	case 4:
		b := make([]byte, 16)
		if _, err := io.ReadFull(br, b); err != nil {
			return
		}
		host = net.IP(b).String()
	case 3:
		l := make([]byte, 1)
		if _, err := io.ReadFull(br, l); err != nil {
			return
		}
		b := make([]byte, l[0])
		if _, err := io.ReadFull(br, b); err != nil {
			return
		}
		host = string(b)
	default:
		c.Write([]byte{5, 8, 0, 1, 0, 0, 0, 0, 0, 0})
		return
	}
	pb := make([]byte, 2)
	if _, err := io.ReadFull(br, pb); err != nil {
		return
	}
	port := int(binary.BigEndian.Uint16(pb))
	if r[1] != 1 { // chỉ CONNECT
		c.Write([]byte{5, 7, 0, 1, 0, 0, 0, 0, 0, 0})
		return
	}
	if !p.begin(s, c) {
		c.Write([]byte{5, 1, 0, 1, 0, 0, 0, 0, 0, 0})
		return
	}
	defer p.end(s, c)
	t0 := time.Now()
	up, how, err := p.dial(s, host, port)
	if err != nil {
		if s.cu != nil {
			p.clog(s.cu, c.RemoteAddr(), host, port, how, 0, 0, t0, err)
		}
		c.Write([]byte{5, socksRep(err), 0, 1, 0, 0, 0, 0, 0, 0})
		return
	}
	defer up.Close()
	rep := []byte{5, 0, 0, 1, 0, 0, 0, 0, 0, 0}
	if la, ok := up.LocalAddr().(*net.TCPAddr); ok {
		if v4 := la.IP.To4(); v4 != nil {
			copy(rep[4:8], v4)
		} else {
			rep = append([]byte{5, 0, 0, 4}, la.IP.To16()...)
			rep = append(rep, 0, 0)
		}
		binary.BigEndian.PutUint16(rep[len(rep)-2:], uint16(la.Port))
	}
	c.Write(rep)
	c.SetDeadline(time.Time{})
	p.relayLog(s, c, br, up, host, port, how, t0)
}

// relayLog: chuyển dữ liệu; kết nối của khách thì ghi 1 dòng nhật ký lúc xong (byte lên / xuống của riêng kết nối này).
func (p *Pool) relayLog(s *slotRT, c net.Conn, br *bufio.Reader, up net.Conn, host string, port int, how string, t0 time.Time) {
	if s.cu == nil {
		p.relay(s, c, br, up)
		return
	}
	u0, d0 := atomic.LoadInt64(&s.up), atomic.LoadInt64(&s.down)
	p.relay(s, c, br, up)
	p.clog(s.cu, c.RemoteAddr(), host, port, how, atomic.LoadInt64(&s.up)-u0, atomic.LoadInt64(&s.down)-d0, t0, nil)
}

func socksRep(err error) byte {
	switch {
	case errors.Is(err, errBlocked):
		return 2
	case errors.Is(err, errResolve), errors.Is(err, errNoRoute):
		return 4
	case errors.Is(err, syscall.ECONNREFUSED):
		return 5
	case errors.Is(err, syscall.ENETUNREACH):
		return 3
	case errors.Is(err, syscall.EHOSTUNREACH):
		return 4
	}
	var ne net.Error
	if errors.As(err, &ne) && ne.Timeout() {
		return 6
	}
	return 1
}

// ---------------------------------------------------------------- HTTP: CONNECT, http://…, và /rotate /ip (link đổi IP)

func (p *Pool) httpProxy(c net.Conn, br *bufio.Reader, pub bool) {
	line, err := readLine(br)
	if err != nil {
		return
	}
	parts := strings.SplitN(line, " ", 3)
	if len(parts) != 3 || !strings.HasPrefix(parts[2], "HTTP/1.") {
		return
	}
	method, target := parts[0], parts[1]
	var hdr []string
	auth := ""
	for {
		l, err := readLine(br)
		if err != nil {
			return
		}
		if l == "" {
			break
		}
		if len(hdr) > 100 {
			return
		}
		k := strings.ToLower(strings.TrimSpace(strings.SplitN(l, ":", 2)[0]))
		if k == "proxy-authorization" {
			auth = strings.TrimSpace(l[strings.Index(l, ":")+1:])
			continue
		}
		if k == "proxy-connection" {
			continue
		}
		hdr = append(hdr, l)
	}
	if strings.HasPrefix(target, "/") { // không phải yêu cầu proxy → trang nhỏ của cbpool
		p.api(c, method, target, pub)
		return
	}
	s := p.basicAuth(auth, pub, c.RemoteAddr())
	if s == nil {
		io.WriteString(c, "HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"cbpool\"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
		return
	}
	if !p.begin(s, c) {
		io.WriteString(c, "HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
		return
	}
	defer p.end(s, c)
	t0 := time.Now()
	if method == "CONNECT" {
		host, ps, err := net.SplitHostPort(target)
		port, _ := strconv.Atoi(ps)
		if err != nil || port <= 0 {
			io.WriteString(c, "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
			return
		}
		up, how, err := p.dial(s, host, port)
		if err != nil {
			if s.cu != nil {
				p.clog(s.cu, c.RemoteAddr(), host, port, how, 0, 0, t0, err)
			}
			httpErr(c, err)
			return
		}
		defer up.Close()
		io.WriteString(c, "HTTP/1.1 200 Connection established\r\n\r\n")
		c.SetDeadline(time.Time{})
		p.relayLog(s, c, br, up, host, port, how, t0)
		return
	}
	u, err := url.Parse(target)
	if err != nil || u.Scheme != "http" || u.Host == "" {
		io.WriteString(c, "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
		return
	}
	port := 80
	if u.Port() != "" {
		port, _ = strconv.Atoi(u.Port())
	}
	up, how, err := p.dial(s, u.Hostname(), port)
	if err != nil {
		if s.cu != nil {
			p.clog(s.cu, c.RemoteAddr(), u.Hostname(), port, how, 0, 0, t0, err)
		}
		httpErr(c, err)
		return
	}
	defer up.Close()
	path := u.RequestURI()
	var b strings.Builder
	fmt.Fprintf(&b, "%s %s %s\r\n", method, path, parts[2])
	hasHost := false
	for _, l := range hdr {
		k := strings.ToLower(strings.TrimSpace(strings.SplitN(l, ":", 2)[0]))
		if k == "connection" || k == "keep-alive" {
			continue
		}
		if k == "host" {
			hasHost = true
		}
		b.WriteString(l + "\r\n")
	}
	if !hasHost {
		b.WriteString("Host: " + u.Host + "\r\n")
	}
	b.WriteString("Connection: close\r\n\r\n") // mỗi kết nối khách 1 yêu cầu (yêu cầu sau có thể tới máy khác)
	if _, err := io.WriteString(up, b.String()); err != nil {
		return
	}
	c.SetDeadline(time.Time{})
	p.relayLog(s, c, br, up, u.Hostname(), port, how, t0)
}

func readLine(br *bufio.Reader) (string, error) {
	var b []byte
	for {
		l, pre, err := br.ReadLine()
		if err != nil {
			return "", err
		}
		b = append(b, l...)
		if len(b) > 8192 {
			return "", errors.New("dòng quá dài")
		}
		if !pre {
			return string(b), nil
		}
	}
}

func (p *Pool) basicAuth(h string, pub bool, from net.Addr) *slotRT {
	if !strings.HasPrefix(strings.ToLower(h), "basic ") {
		return nil
	}
	d, err := base64.StdEncoding.DecodeString(strings.TrimSpace(h[6:]))
	if err != nil {
		return nil
	}
	up := strings.SplitN(string(d), ":", 2)
	if len(up) != 2 {
		return nil
	}
	return p.auth(up[0], up[1], pub, from)
}

func httpErr(c net.Conn, err error) {
	code := "502 Bad Gateway"
	if errors.Is(err, errBlocked) {
		code = "403 Forbidden"
	} else if errors.Is(err, errResolve) || errors.Is(err, errNoRoute) {
		code = "504 Gateway Timeout"
	}
	msg := err.Error()
	fmt.Fprintf(c, "HTTP/1.1 %s\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s", code, len(msg), msg)
}

// api: GET /rotate?key=K[&what=v6|v4|all] · GET /ip?key=K — khoá đổi IP riêng từng ô (không lộ mật khẩu proxy).
// 27.11c: khoá của khách (proxy riêng) dùng được từ mọi nơi; khoá ô nội bộ chỉ trong mạng nhà.
func (p *Pool) api(c net.Conn, method, target string, pub bool) {
	reply := func(code string, v interface{}) {
		b, _ := json.Marshal(v)
		fmt.Fprintf(c, "HTTP/1.1 %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n%s", code, len(b), b)
	}
	u, err := url.Parse(target)
	if err != nil || (method != "GET" && method != "POST") {
		reply("400 Bad Request", map[string]interface{}{"ok": false})
		return
	}
	q := u.Query()
	p.mu.RLock()
	s := p.byRot[q.Get("key")]
	cs := p.custRot[q.Get("key")]
	p.mu.RUnlock()
	if pub {
		s = nil
	}
	if cs != nil && len(q.Get("key")) >= 16 && cs.cu.X > time.Now().Unix() {
		switch u.Path {
		case "/ip":
			reply("200 OK", map[string]interface{}{"ok": true, "ip": p.custIP(cs)})
		case "/rotate":
			r, err := p.custRotate(cs)
			if err != nil {
				reply("429 Too Many Requests", map[string]interface{}{"ok": false, "err": err.Error()})
				return
			}
			r["ok"] = true
			reply("200 OK", r)
		default:
			reply("404 Not Found", map[string]interface{}{"ok": false})
		}
		return
	}
	if s == nil || len(q.Get("key")) < 16 {
		if pub {
			p.pubFail(ipKey(c.RemoteAddr()))
		}
		time.Sleep(300 * time.Millisecond)
		reply("403 Forbidden", map[string]interface{}{"ok": false, "err": "khoá sai"})
		return
	}
	switch u.Path {
	case "/ip":
		p.mu.RLock()
		r := map[string]interface{}{"ok": true, "id": s.ID}
		if s.ip6 != nil {
			r["ip6"] = s.ip6.String()
		}
		p.mu.RUnlock()
		if ip := p.ppp.ipFor(s.n); ip != nil {
			r["ip4"] = ip.String()
		}
		reply("200 OK", r)
	case "/rotate":
		r, err := p.rotate(s, q.Get("what"))
		if err != nil {
			reply("429 Too Many Requests", map[string]interface{}{"ok": false, "err": err.Error()})
			return
		}
		r["ok"] = true
		reply("200 OK", r)
	default:
		reply("404 Not Found", map[string]interface{}{"ok": false})
	}
}

// ---------------------------------------------------------------- chuyển dữ liệu 2 chiều (giới hạn tốc độ + đếm byte theo ô)

type closeWriter interface{ CloseWrite() error }

func (p *Pool) relay(s *slotRT, c net.Conn, br *bufio.Reader, up net.Conn) {
	done := make(chan struct{}, 2)
	cp := func(dst net.Conn, src io.Reader, srcConn net.Conn, bk *bucket, ctr *int64) {
		buf := make([]byte, 32*1024)
		for {
			srcConn.SetReadDeadline(time.Now().Add(idleTO))
			n, err := src.Read(buf)
			if n > 0 {
				bk.wait(n)
				if _, werr := dst.Write(buf[:n]); werr != nil {
					break
				}
				atomic.AddInt64(ctr, int64(n))
			}
			if err != nil {
				break
			}
		}
		if cw, ok := dst.(closeWriter); ok {
			cw.CloseWrite()
		} else {
			dst.Close()
		}
		done <- struct{}{}
	}
	go cp(up, br, c, s.bkUp, &s.up)
	go cp(c, up, up, s.bkDown, &s.down)
	<-done
	<-done // chiều còn lại tự kết thúc khi đầu kia đóng hoặc im quá idleTO
	c.Close()
	up.Close()
}
