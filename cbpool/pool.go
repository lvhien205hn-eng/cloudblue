package main

import (
	"bufio"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// ---------------------------------------------------------------- giới hạn tốc độ (gầu token dùng chung cho mọi kết nối của 1 ô)

type bucket struct {
	mu     sync.Mutex
	rate   float64 // byte / giây (0 = không giới hạn)
	tokens float64
	last   time.Time
}

func newBucket(kbps int) *bucket {
	if kbps <= 0 {
		return nil
	}
	r := float64(kbps) * 1000 / 8
	return &bucket{rate: r, tokens: math.Max(r/4, 65536), last: time.Now()}
}

func (b *bucket) wait(n int) {
	if b == nil || b.rate <= 0 || n <= 0 {
		return
	}
	b.mu.Lock()
	now := time.Now()
	b.tokens += now.Sub(b.last).Seconds() * b.rate
	if burst := math.Max(b.rate/4, 65536); b.tokens > burst {
		b.tokens = burst
	}
	b.last = now
	b.tokens -= float64(n)
	var d time.Duration
	if b.tokens < 0 {
		d = time.Duration(-b.tokens / b.rate * float64(time.Second))
	}
	b.mu.Unlock()
	if d > 0 {
		time.Sleep(d)
	}
}

// ---------------------------------------------------------------- ô proxy lúc chạy

type oldAddr struct {
	ip  string
	idx int
	at  time.Time // gỡ sau thời điểm này
}

type slotRT struct {
	*Slot
	n        int // số thứ tự (0…)
	ip6      net.IP
	conns    int32
	up, down int64
	bkUp     *bucket
	bkDown   *bucket
	lastRot  time.Time
}

type Pool struct {
	c      *Conf
	mu     sync.RWMutex
	st     *PState
	slots  []*slotRT
	byUser map[string]*slotRT
	byRot  map[string]*slotRT
	v6if   string
	v6idx  int
	prefix *net.IPNet
	v6err  string
	old6   []oldAddr
	ppp    *PppMgr
	total  int32
	stopCh chan struct{}
	wg     sync.WaitGroup
	v6kick chan struct{}
	pppErr string
	v6fail int32 // lần nối IPv6 hỏng liên tiếp (không tính bị từ chối)
	v6skip int64 // tới mốc này (unix nano): đích có IPv4 thì khỏi thử IPv6
}

func newPool(c *Conf) (*Pool, error) {
	st := loadState(c)
	if ensureSlots(c, st) {
		if err := saveState(c, st); err != nil {
			return nil, fmt.Errorf("không ghi được %s: %v", statePath(c), err)
		}
	}
	p := &Pool{c: c, st: st, stopCh: make(chan struct{}), v6kick: make(chan struct{}, 1)}
	p.ppp = newPppMgr(c, st, func() { saveState(c, st) })
	p.rebuild()
	return p, nil
}

func (p *Pool) rebuild() {
	p.mu.Lock()
	defer p.mu.Unlock()
	old := map[string]*slotRT{}
	for _, s := range p.slots {
		old[s.ID] = s
	}
	p.slots = nil
	p.byUser = map[string]*slotRT{}
	p.byRot = map[string]*slotRT{}
	for i, s := range p.st.Slots {
		rt := old[s.ID]
		if rt == nil {
			rt = &slotRT{}
		}
		rt.Slot, rt.n = s, i
		rt.bkUp, rt.bkDown = newBucket(p.c.BwKbps), newBucket(p.c.BwKbps)
		p.slots = append(p.slots, rt)
		p.byUser[s.ID] = rt
		p.byRot[s.Rot] = rt
	}
}

func (p *Pool) start() {
	p.wg.Add(1)
	go p.v6loop()
	p.applyPpp()
}

func (p *Pool) stop() {
	close(p.stopCh)
	p.ppp.stopAll()
	p.wg.Wait()
}

func (p *Pool) reload() map[string]interface{} {
	c, err := loadConf(p.c.path)
	if err != nil {
		logf("đọc lại cấu hình lỗi: %v", err)
	} else {
		c.Listen = p.c.Listen // đổi cổng phải chạy lại dịch vụ
		p.mu.Lock()
		p.c = c
		p.ppp.c = c
		p.mu.Unlock()
		if ensureSlots(c, p.st) {
			saveState(c, p.st)
		}
		p.rebuild()
	}
	p.applyPpp()
	select {
	case p.v6kick <- struct{}{}:
	default:
	}
	time.Sleep(300 * time.Millisecond)
	return p.status()
}

func (p *Pool) applyPpp() {
	sec, err := loadSecret(p.c)
	n := p.c.Ppp.Sessions
	if sec != nil && sec.Sessions > 0 {
		n = sec.Sessions
	}
	if n > 64 {
		n = 64
	}
	switch {
	case n <= 0:
		p.pppErr = ""
		p.ppp.configure(nil, 0, "")
	case err != nil:
		if errors.Is(err, os.ErrNotExist) {
			p.pppErr = "chưa có tài khoản PPPoE (gõ: cbpool ppp-set)"
		} else {
			p.pppErr = err.Error()
		}
		p.ppp.configure(nil, 0, "")
	default:
		p.pppErr = ""
		ifc := p.c.Ppp.Iface
		if ifc == "" {
			ifc = p.v6ifName()
		}
		p.ppp.configure(sec, n, ifc)
	}
}

func (p *Pool) v6ifName() string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	if p.v6if != "" {
		return p.v6if
	}
	if p.c.Iface6 != "" {
		return p.c.Iface6
	}
	if _, err := net.InterfaceByName("vmbr0"); err == nil {
		return "vmbr0"
	}
	return ""
}

// ---------------------------------------------------------------- IPv6: dải /64 + 1 địa chỉ / ô

type inet6 struct {
	ip    net.IP
	idx   int
	plen  int
	scope int
	flags int
	name  string
}

var procInet6 = "/proc/net/if_inet6"

func readInet6() ([]inet6, error) {
	f, err := os.Open(procInet6)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var r []inet6
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fl := strings.Fields(sc.Text())
		if len(fl) < 6 || len(fl[0]) != 32 {
			continue
		}
		b, err := hex.DecodeString(fl[0])
		if err != nil {
			continue
		}
		idx, _ := strconv.ParseInt(fl[1], 16, 32)
		plen, _ := strconv.ParseInt(fl[2], 16, 32)
		scope, _ := strconv.ParseInt(fl[3], 16, 32)
		flags, _ := strconv.ParseInt(fl[4], 16, 32)
		r = append(r, inet6{ip: net.IP(b), idx: int(idx), plen: int(plen), scope: int(scope), flags: int(flags), name: fl[5]})
	}
	return r, sc.Err()
}

const (
	ifaFTemporary  = 0x01
	ifaFDeprecated = 0x20
	ifaFTentative  = 0x40
)

func isULA(ip net.IP) bool { return len(ip) == 16 && ip[0]&0xfe == 0xfc }

// findPrefix: dải /64 công khai trên card (card rỗng → vmbr0 → card đầu tiên có).
func findPrefix(want string) (string, int, *net.IPNet, error) {
	all, err := readInet6()
	if err != nil {
		return "", 0, nil, fmt.Errorf("không đọc được IPv6 của máy: %v", err)
	}
	pick := func(name string) (int, *net.IPNet, bool) {
		var best *inet6
		for i := range all {
			a := &all[i]
			if a.name != name || a.scope != 0 || a.plen != 64 || !a.ip.IsGlobalUnicast() || isULA(a.ip) || a.flags&(ifaFDeprecated|ifaFTentative) != 0 {
				continue
			}
			if best == nil || (best.flags&ifaFTemporary != 0 && a.flags&ifaFTemporary == 0) {
				best = a
			}
		}
		if best == nil {
			return 0, nil, false
		}
		return best.idx, &net.IPNet{IP: best.ip.Mask(net.CIDRMask(64, 128)), Mask: net.CIDRMask(64, 128)}, true
	}
	names := []string{want}
	if want == "" {
		names = []string{"vmbr0"}
		seen := map[string]bool{"vmbr0": true}
		for _, a := range all {
			if !seen[a.name] && a.name != "lo" {
				seen[a.name] = true
				names = append(names, a.name)
			}
		}
	}
	for _, n := range names {
		if idx, pf, ok := pick(n); ok {
			return n, idx, pf, nil
		}
	}
	if want != "" {
		return want, 0, nil, fmt.Errorf("card %s chưa có IPv6 công khai /64 (modem chưa bật IPv6?)", want)
	}
	return "", 0, nil, errors.New("máy chưa có IPv6 công khai /64 (modem chưa bật IPv6?)")
}

func joinIID(pf *net.IPNet, iid string) net.IP {
	b, err := hex.DecodeString(iid)
	if err != nil || len(b) != 8 || pf == nil {
		return nil
	}
	ip := make(net.IP, 16)
	copy(ip, pf.IP.To16()[:8])
	copy(ip[8:], b)
	return ip
}

func (p *Pool) v6loop() {
	defer p.wg.Done()
	for {
		p.v6sync()
		select {
		case <-p.stopCh:
			return
		case <-p.v6kick:
		case <-time.After(20 * time.Second):
		}
	}
}

func (p *Pool) v6sync() {
	p.mu.Lock()
	defer p.mu.Unlock()
	now := time.Now()
	var keep []oldAddr // địa chỉ cũ chờ gỡ (kết nối đang chạy dùng nốt)
	for _, o := range p.old6 {
		if now.After(o.at) {
			addr6Del(o.idx, net.ParseIP(o.ip))
		} else {
			keep = append(keep, o)
		}
	}
	p.old6 = keep
	var name string
	var idx int
	var pf *net.IPNet
	var err error
	if bp(p.c.V6, true) {
		name, idx, pf, err = findPrefix(p.c.Iface6)
	} else {
		err = errors.New("IPv6 đang tắt (cấu hình v6=false)")
	}
	if err != nil {
		if p.v6err != err.Error() {
			logf("IPv6: %v", err)
		}
		p.v6err = err.Error()
	} else {
		if p.v6err != "" || p.prefix == nil || p.prefix.String() != pf.String() || p.v6if != name {
			logf("IPv6: dải %s trên %s", pf, name)
		}
		p.v6err = ""
	}
	changed := p.prefix == nil || pf == nil || p.prefix.String() != pf.String() || p.v6if != name
	oldIdx := p.v6idx
	p.v6if, p.v6idx, p.prefix = name, idx, pf
	have := map[string]bool{}
	if all, e := readInet6(); e == nil {
		for _, a := range all {
			if a.idx == idx && a.plen == 128 {
				have[a.ip.String()] = true
			}
		}
	}
	want := map[string]bool{}
	for _, s := range p.slots {
		s.ip6 = nil
		if pf == nil {
			continue
		}
		ip := joinIID(pf, s.IID)
		if ip == nil {
			continue
		}
		want[ip.String()] = true
		if !have[ip.String()] {
			if e := addr6Add(idx, ip); e != nil {
				logf("IPv6: gắn %s cho %s lỗi: %v", ip, s.ID, e)
				continue
			}
		}
		s.ip6 = ip
	}
	grace := map[string]bool{}
	for _, o := range p.old6 {
		grace[o.ip] = true
	}
	var added []string
	for _, a := range p.st.Added { // địa chỉ do cbpool gắn trước đây mà giờ không dùng (đổi dải / bớt ô) → gỡ
		if want[a] || grace[a] {
			continue
		}
		ix := idx
		if changed && oldIdx != 0 {
			ix = oldIdx
		}
		if ix != 0 {
			addr6Del(ix, net.ParseIP(a))
		}
		if ix != idx && idx != 0 {
			addr6Del(idx, net.ParseIP(a))
		}
	}
	for a := range want {
		added = append(added, a)
	}
	for a := range grace {
		added = append(added, a)
	}
	if !sameSet(added, p.st.Added) {
		p.st.Added = added
		saveState(p.c, p.st)
	}
}

func sameSet(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	m := map[string]bool{}
	for _, x := range a {
		m[x] = true
	}
	for _, x := range b {
		if !m[x] {
			return false
		}
	}
	return true
}

// ---------------------------------------------------------------- chọn đường ra cho 1 kết nối

var (
	errBlocked    = errors.New("đích bị chặn (mạng nội bộ / cổng gửi thư)")
	errNoRoute    = errors.New("ô này không có đường ra cho đích (IPv4 riêng chưa có / đích chỉ có IPv6)")
	errResolve    = errors.New("không phân giải được tên miền")
	errSlotBusy   = errors.New("ô đang quá nhiều kết nối")
	private4Nets  = mustNets("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4")
	private6Nets  = mustNets("::/128", "::1/128", "::ffff:0:0/96", "64:ff9b:1::/48", "100::/64", "fc00::/7", "fe80::/10", "ff00::/8")
	resolveTimout = 5 * time.Second
	rotGrace      = 90 * time.Second // địa chỉ IPv6 cũ giữ thêm chừng này cho kết nối đang chạy rồi mới gỡ
	lookupIPAddr  = net.DefaultResolver.LookupIPAddr
)

func mustNets(cs ...string) []*net.IPNet {
	var r []*net.IPNet
	for _, c := range cs {
		_, n, err := net.ParseCIDR(c)
		if err != nil {
			panic(err)
		}
		r = append(r, n)
	}
	return r
}

func inNets(ip net.IP, ns []*net.IPNet) bool {
	for _, n := range ns {
		if n.Contains(ip) {
			return true
		}
	}
	return false
}

func (p *Pool) dstBlocked(ip net.IP) bool {
	if inNets(ip, p.c.allowDst) {
		return false
	}
	if v4 := ip.To4(); v4 != nil {
		return inNets(v4, private4Nets)
	}
	return inNets(ip, private6Nets)
}

func (p *Pool) portBlocked(port int) bool {
	for _, b := range p.c.BlockPorts {
		if b == port {
			return true
		}
	}
	return port <= 0 || port > 65535
}

func (p *Pool) clientOK(a net.Addr) bool {
	ta, ok := a.(*net.TCPAddr)
	if !ok {
		return false
	}
	ip := ta.IP
	if v4 := ip.To4(); v4 != nil {
		ip = v4
	}
	return inNets(ip, p.c.allowFrom)
}

// dial: mở kết nối tới host:port bằng IP của ô s. Trả về kết nối + đường đã đi ("v6" / "v4ppp" / "v4").
func (p *Pool) dial(s *slotRT, host string, port int) (net.Conn, string, error) {
	if p.portBlocked(port) {
		return nil, "", errBlocked
	}
	var ips []net.IP
	if ip := net.ParseIP(strings.Trim(host, "[]")); ip != nil {
		ips = []net.IP{ip}
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), resolveTimout)
		as, err := lookupIPAddr(ctx, host)
		cancel()
		if err != nil || len(as) == 0 {
			return nil, "", errResolve
		}
		for _, a := range as {
			ips = append(ips, a.IP)
		}
	}
	var v6, v4 []net.IP
	blocked := 0
	for _, ip := range ips {
		if p.dstBlocked(ip) {
			blocked++
			continue
		}
		if ip.To4() != nil {
			v4 = append(v4, ip.To4())
		} else {
			v6 = append(v6, ip)
		}
	}
	if len(v6)+len(v4) == 0 {
		if blocked > 0 {
			return nil, "", errBlocked
		}
		return nil, "", errResolve
	}
	p.mu.RLock()
	src6 := s.ip6
	p.mu.RUnlock()
	var last error = errNoRoute
	if src6 != nil && (len(v4) == 0 || time.Now().UnixNano() > atomic.LoadInt64(&p.v6skip)) {
		tries, to := 1, 2500*time.Millisecond // còn IPv4 dự phòng: thử IPv6 1 lần, ngắn
		if len(v4) == 0 {
			tries, to = 2, 10*time.Second
		}
		for i, ip := range v6 {
			if i >= tries {
				break
			}
			d := net.Dialer{Timeout: to, LocalAddr: &net.TCPAddr{IP: src6}}
			c, err := d.Dial("tcp6", net.JoinHostPort(ip.String(), strconv.Itoa(port)))
			if err == nil {
				atomic.StoreInt32(&p.v6fail, 0)
				return c, "v6", nil
			}
			last = err
			if !errors.Is(err, syscall.ECONNREFUSED) && atomic.AddInt32(&p.v6fail, 1) >= 5 { // đường IPv6 hỏng → 60 giây đi thẳng IPv4
				atomic.StoreInt32(&p.v6fail, 0)
				atomic.StoreInt64(&p.v6skip, time.Now().Add(60*time.Second).UnixNano())
				logf("IPv6: 5 lần nối hỏng liền → 60 giây tới đích có IPv4 thì đi IPv4")
			}
		}
	}
	if len(v4) == 0 {
		return nil, "", last
	}
	src4 := p.ppp.ipFor(s.n)
	how := "v4ppp"
	if src4 == nil {
		if !bp(p.c.Fallback4, true) {
			return nil, "", errNoRoute
		}
		how = "v4"
	}
	for i, ip := range v4 {
		if i >= 2 {
			break
		}
		d := net.Dialer{Timeout: 8 * time.Second}
		if src4 != nil {
			d.LocalAddr = &net.TCPAddr{IP: src4}
		}
		c, err := d.Dial("tcp4", net.JoinHostPort(ip.String(), strconv.Itoa(port)))
		if err == nil {
			return c, how, nil
		}
		last = err
	}
	return nil, "", last
}

// ---------------------------------------------------------------- đổi IP

func (p *Pool) slot(id string) *slotRT {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.byUser[id]
}

func (p *Pool) rotate(s *slotRT, what string) (map[string]interface{}, error) {
	if what == "" {
		what = "all"
	}
	if what != "v6" && what != "v4" && what != "all" {
		return nil, fmt.Errorf("đổi gì? v6 / v4 / all")
	}
	p.mu.Lock()
	if w := 10*time.Second - time.Since(s.lastRot); w > 0 {
		p.mu.Unlock()
		return nil, fmt.Errorf("đổi IP quá nhanh, đợi %d giây", int(w.Seconds())+1)
	}
	s.lastRot = time.Now()
	r := map[string]interface{}{"id": s.ID}
	if what != "v4" && p.prefix != nil {
		old := s.ip6
		var nip net.IP
		var iid string
		for i := 0; i < 4; i++ {
			iid = randIID()
			if nip = joinIID(p.prefix, iid); nip != nil {
				break
			}
		}
		if err := addr6Add(p.v6idx, nip); err != nil {
			p.mu.Unlock()
			return nil, fmt.Errorf("gắn IPv6 mới lỗi: %v", err)
		}
		s.IID, s.ip6 = iid, nip
		if old != nil {
			p.old6 = append(p.old6, oldAddr{ip: old.String(), idx: p.v6idx, at: time.Now().Add(rotGrace)})
		}
		p.st.Added = append(p.st.Added, nip.String())
		saveState(p.c, p.st)
		r["ip6"] = nip.String()
	}
	p.mu.Unlock()
	if what != "v6" {
		if k := p.ppp.sessFor(s.n); k >= 0 {
			ip, err := p.ppp.redial(k, 40*time.Second)
			if err != nil {
				r["err4"] = err.Error()
			} else {
				r["ip4"] = ip.String()
				r["sess"] = k
			}
		} else if what == "v4" {
			return nil, errors.New("chưa có phiên PPPoE nào (IPv4 riêng chưa bật)")
		}
	}
	return r, nil
}

// ---------------------------------------------------------------- trạng thái

type slotStat struct {
	ID    string `json:"id"`
	User  string `json:"user"`
	Pass  string `json:"pass"`
	Rot   string `json:"rot"`
	IP6   string `json:"ip6,omitempty"`
	IP4   string `json:"ip4,omitempty"`
	Sess  int    `json:"sess"`
	Conns int32  `json:"conns"`
	Up    int64  `json:"up"`
	Down  int64  `json:"down"`
}

func (p *Pool) status() map[string]interface{} {
	p.mu.RLock()
	var ss []slotStat
	for _, s := range p.slots {
		x := slotStat{ID: s.ID, User: s.ID, Pass: s.Pass, Rot: s.Rot, Sess: p.ppp.sessFor(s.n), Conns: atomic.LoadInt32(&s.conns),
			Up: atomic.LoadInt64(&s.up), Down: atomic.LoadInt64(&s.down)}
		if s.ip6 != nil {
			x.IP6 = s.ip6.String()
		}
		if ip := p.ppp.ipFor(s.n); ip != nil {
			x.IP4 = ip.String()
		}
		ss = append(ss, x)
	}
	v6 := map[string]interface{}{"on": bp(p.c.V6, true), "iface": p.v6if, "err": p.v6err}
	if p.prefix != nil {
		v6["prefix"] = p.prefix.String()
	}
	listen := p.c.Listen
	p.mu.RUnlock()
	pp := p.ppp.status()
	if p.pppErr != "" {
		pp["err"] = p.pppErr
	}
	return map[string]interface{}{"ver": VER, "listen": listen, "bw_kbps": p.c.BwKbps, "fallback4": bp(p.c.Fallback4, true),
		"conns": atomic.LoadInt32(&p.total), "v6": v6, "ppp": pp, "slots": ss, "t": time.Now().Unix()}
}

// ---------------------------------------------------------------- ổ cắm điều khiển (chỉ root)

func (p *Pool) ctlServe() {
	path := p.c.Ctl
	os.MkdirAll(filepath.Dir(path), 0700)
	os.Remove(path)
	ln, err := net.Listen("unix", path)
	if err != nil {
		logf("không mở được ổ cắm điều khiển %s: %v", path, err)
		return
	}
	os.Chmod(path, 0600)
	go func() { <-p.stopCh; ln.Close(); os.Remove(path) }()
	for {
		c, err := ln.Accept()
		if err != nil {
			return
		}
		go p.ctlOne(c)
	}
}

func (p *Pool) ctlOne(c net.Conn) {
	defer c.Close()
	c.SetDeadline(time.Now().Add(90 * time.Second))
	line, err := bufio.NewReader(c).ReadBytes('\n')
	if err != nil && len(line) == 0 {
		return
	}
	var req map[string]string
	var resp interface{}
	if json.Unmarshal(line, &req) != nil {
		resp = map[string]interface{}{"ok": false, "err": "yêu cầu sai"}
	} else {
		switch req["cmd"] {
		case "status":
			resp = p.status()
		case "reload":
			resp = p.reload()
		case "rotate":
			s := p.slot(req["slot"])
			if s == nil {
				resp = map[string]interface{}{"ok": false, "err": "không có ô " + req["slot"]}
			} else if r, err := p.rotate(s, req["what"]); err != nil {
				resp = map[string]interface{}{"ok": false, "err": err.Error()}
			} else {
				r["ok"] = true
				resp = r
			}
		default:
			resp = map[string]interface{}{"ok": false, "err": "lệnh lạ"}
		}
	}
	b, _ := json.Marshal(resp)
	c.Write(append(b, '\n'))
}

func ctlCall(path string, req interface{}, to time.Duration) ([]byte, error) {
	c, err := net.DialTimeout("unix", path, 3*time.Second)
	if err != nil {
		return nil, err
	}
	defer c.Close()
	c.SetDeadline(time.Now().Add(to))
	b, _ := json.Marshal(req)
	if _, err := c.Write(append(b, '\n')); err != nil {
		return nil, err
	}
	r, err := bufio.NewReader(c).ReadBytes('\n')
	if err != nil && len(r) == 0 {
		return nil, err
	}
	return []byte(strings.TrimSpace(string(r))), nil
}
