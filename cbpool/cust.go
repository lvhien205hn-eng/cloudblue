package main

// 27.11c · BÁN PROXY CHO KHÁCH (web bán → cbhost ghi /etc/cloudblue/cbpool-users.json, quyền 600 → cbpool đọc).
//   · Tài khoản khách đăng nhập được từ MỌI NƠI (Internet, qua cổng modem chuyển về máy chủ). Tài khoản ô nội bộ p01… vẫn CHỈ
//     trong mạng nhà; từ Internet chỉ tài khoản khách đăng nhập được, và chỉ khi đang có tài khoản khách.
//   · Loại v6: ô bán s001… (IPv6 riêng, tách khỏi ô nội bộ p01…), chỉ đi IPv6 ("fb4": đích chỉ có IPv4 thì đi IPv4 chung của máy).
//   · Loại v4: 1 phiên PPPoE (IP công khai riêng của phiên). Phiên đã bán ("sale4" = mọi phiên) không chia cho ô nội bộ.
//   · share k: web xếp tối đa k khách cùng 1 ô. Đổi IP chỉ cho proxy RIÊNG (ô đó chỉ có 1 khách).
//   · Hết hạn → từ chối đăng nhập + cắt kết nối đang chạy. Dò mật khẩu từ Internet → chặn IP đó 15 phút.
//   · Không cho đi tới chính mạng nhà: dải IPv6 /64 của máy, IP công khai của nhà ("self"), IP các phiên PPPoE.
//   · Nhật ký kết nối của khách (giờ, tài khoản, IP khách, đích, byte) → /var/log/cloudblue/cbpool-khach.log (xoay vòng 20 MB).
//   · Khoá P-256 riêng của máy (state_dir/key.json): web mã hoá tài khoản PPPoE bằng khoá công khai → chỉ máy này giải được
//     (cbpool ppp-import, cbhost gọi) — web, Supabase, người khác không đọc được mật khẩu.

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/hkdf"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type custUser struct {
	U string `json:"u"`           // tên đăng nhập (web sinh: px + 10 chữ)
	P string `json:"p"`           // mật khẩu
	K string `json:"k"`           // "v6" | "v4"
	N string `json:"n"`           // ô: "s007" (v6) · "3" (v4: số phiên PPPoE)
	X int64  `json:"x"`           // hết hạn (unix giây)
	R string `json:"r,omitempty"` // khoá đổi IP (chỉ proxy riêng)
	S int    `json:"s"`           // share: tối đa bao nhiêu khách cùng ô
	B int    `json:"b,omitempty"` // tốc độ riêng (kbps, 0 = theo "bw")
}

type usersFile struct {
	V     int        `json:"v"`
	T     int64      `json:"t"`
	Bw    int        `json:"bw"`    // kbps mỗi khách (0 = 20000, <0 = không giới hạn)
	Fb4   bool       `json:"fb4"`   // khách IPv6: đích chỉ có IPv4 → đi IPv4 chung của máy
	Sale4 bool       `json:"sale4"` // mọi phiên PPPoE để bán (ô nội bộ đi IPv4 chung)
	MaxC  int        `json:"maxc"`  // kết nối cùng lúc tối đa mỗi khách (0 = 64)
	Self  []string   `json:"self"`  // IP công khai của nhà (cấm làm đích)
	Users []custUser `json:"users"`
}

type custRT struct {
	custUser
	sess  int     // v4: số phiên; v6: -1
	unit  *slotRT // v6: ô bán (địa chỉ IPv6)
	mu    sync.Mutex
	conns map[net.Conn]struct{}
}

func (cu *custRT) add(c net.Conn) {
	cu.mu.Lock()
	if cu.conns == nil {
		cu.conns = map[net.Conn]struct{}{}
	}
	cu.conns[c] = struct{}{}
	cu.mu.Unlock()
}

func (cu *custRT) del(c net.Conn) {
	cu.mu.Lock()
	delete(cu.conns, c)
	cu.mu.Unlock()
}

func (cu *custRT) closeAll() int {
	cu.mu.Lock()
	n := len(cu.conns)
	for c := range cu.conns {
		c.Close()
	}
	cu.conns = map[net.Conn]struct{}{}
	cu.mu.Unlock()
	return n
}

// okCustUser: ^px[a-z0-9]{6,30}$ · okUnit6: ^s[0-9]{1,5}$ (không dùng regexp cho file chạy nhỏ)
func okCustUser(u string) bool {
	if len(u) < 8 || len(u) > 32 || !strings.HasPrefix(u, "px") {
		return false
	}
	for _, c := range u[2:] {
		if !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9') {
			return false
		}
	}
	return true
}

func okUnit6(n string) bool {
	if len(n) < 2 || len(n) > 6 || n[0] != 's' {
		return false
	}
	for _, c := range n[1:] {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// loadUsers: đọc file tài khoản khách (không có file = chưa bán gì) → bảng khách / ô bán / phiên để bán. Khách bị bỏ / hết hạn /
// đổi ô → cắt kết nối đang chạy.
func (p *Pool) loadUsers() (map[string]interface{}, error) {
	var uf usersFile
	if b, err := os.ReadFile(p.c.UsersFile); err == nil {
		if err := json.Unmarshal(b, &uf); err != nil {
			return nil, fmt.Errorf("file tài khoản khách hỏng: %v", err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	now := time.Now().Unix()
	bw := uf.Bw
	if bw == 0 {
		bw = 20000
	}
	maxc := uf.MaxC
	if maxc <= 0 {
		maxc = 64
	}
	var self []net.IP
	for _, s := range uf.Self {
		if ip := net.ParseIP(strings.TrimSpace(s)); ip != nil {
			self = append(self, ip)
		}
	}
	p.mu.Lock()
	if p.st.Sale == nil {
		p.st.Sale = map[string]string{}
	}
	oldCust, oldSale := p.cust, p.sale
	cust, rot, sale := map[string]*slotRT{}, map[string]*slotRT{}, map[string]*slotRT{}
	reserved := map[int]bool{}
	stCh, bad := false, 0
	for _, u := range uf.Users {
		if !okCustUser(u.U) || len(u.P) < 8 || len(u.P) > 64 || u.X <= now || cust[u.U] != nil {
			bad++
			continue
		}
		if u.S < 1 {
			u.S = 1
		}
		cu := &custRT{custUser: u, sess: -1}
		switch u.K {
		case "v6":
			if !okUnit6(u.N) {
				bad++
				continue
			}
			us := sale[u.N]
			if us == nil {
				us = oldSale[u.N]
				if us == nil {
					us = &slotRT{Slot: &Slot{ID: u.N}, n: -1, sale: true}
				}
				if iid := p.st.Sale[u.N]; len(iid) == 16 {
					us.IID = iid
				} else {
					us.IID = randIID()
					p.st.Sale[u.N] = us.IID
					stCh = true
				}
				sale[u.N] = us
			}
			cu.unit = us
		case "v4":
			k, err := strconv.Atoi(u.N)
			if err != nil || k < 0 || k > 63 {
				bad++
				continue
			}
			cu.sess = k
			reserved[k] = true
		default:
			bad++
			continue
		}
		rt := oldCust[u.U]
		if rt == nil || rt.cu == nil || rt.cu.K != u.K || rt.cu.N != u.N {
			kb := u.B
			if kb == 0 {
				kb = bw
			}
			rt = &slotRT{Slot: &Slot{ID: u.U}, n: -1, bkUp: newBucket(kb), bkDown: newBucket(kb)}
		} else {
			cu.conns = rt.cu.conns // giữ kết nối đang chạy (đổi mật khẩu / gia hạn không cắt)
		}
		rt.cu = cu
		cust[u.U] = rt
		if len(u.R) >= 16 && u.S == 1 {
			rot[u.R] = rt
		}
	}
	if uf.Sale4 {
		for k := 0; k < 64; k++ {
			reserved[k] = true
		}
	}
	p.cust, p.custRot, p.sale = cust, rot, sale
	p.custBw, p.custFb4, p.custMax, p.self = bw, uf.Fb4, maxc, self
	p.mu.Unlock()
	p.ppp.setReserved(reserved)
	if stCh {
		saveState(p.c, p.st)
	}
	cut := 0
	for name, rt := range oldCust {
		if n := cust[name]; n != rt {
			cut += rt.cu.closeAll()
		}
	}
	select {
	case p.v6kick <- struct{}{}:
	default:
	}
	if len(cust) > 0 || len(oldCust) > 0 {
		logf("khách: %d tài khoản · %d ô IPv6 bán · %d phiên PPPoE để bán%s%s", len(cust), len(sale), len(reserved),
			map[bool]string{true: fmt.Sprintf(" · bỏ %d dòng sai / hết hạn", bad), false: ""}[bad > 0],
			map[bool]string{true: fmt.Sprintf(" · cắt %d kết nối", cut), false: ""}[cut > 0])
	}
	return map[string]interface{}{"ok": true, "users": len(cust), "units6": len(sale), "sale4": len(reserved), "bad": bad, "cut": cut}, nil
}

func (p *Pool) custOn() bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return len(p.cust) > 0
}

var custTick = 30 * time.Second

// custLoop: 30 giây / lần cắt kết nối của khách vừa hết hạn, dọn bảng chặn dò mật khẩu.
func (p *Pool) custLoop() {
	defer p.wg.Done()
	for {
		select {
		case <-p.stopCh:
			return
		case <-time.After(custTick):
		}
		now := time.Now().Unix()
		var gone []*slotRT
		p.mu.Lock()
		for name, rt := range p.cust {
			if rt.cu.X <= now {
				gone = append(gone, rt)
				delete(p.cust, name)
				if rt.cu.R != "" {
					delete(p.custRot, rt.cu.R)
				}
			}
		}
		p.mu.Unlock()
		for _, rt := range gone {
			n := rt.cu.closeAll()
			logf("khách %s hết hạn → cắt %d kết nối", rt.cu.U, n)
		}
		p.mu.RLock()
		due := time.Since(p.pub4At) > 30*time.Minute
		p.mu.RUnlock()
		if due {
			p.mu.Lock()
			p.pub4At = time.Now()
			p.mu.Unlock()
			go func() {
				if ip := publicIP(nil); ip != "" && net.ParseIP(ip).To4() != nil {
					p.mu.Lock()
					if p.pub4 != ip {
						logf("IPv4 công khai của máy: %s", ip)
					}
					p.pub4 = ip
					p.mu.Unlock()
				}
			}()
		}
		p.failMu.Lock()
		for ip, f := range p.fails {
			if time.Now().After(f.until) && time.Since(f.first) > failWin {
				delete(p.fails, ip)
			}
		}
		p.failMu.Unlock()
	}
}

// ---------------------------------------------------------------- chặn dò mật khẩu từ Internet

type failRec struct {
	n     int
	first time.Time
	until time.Time
}

var (
	failWin   = 10 * time.Minute
	failMax   = 20
	failBlock = 15 * time.Minute
)

func ipKey(a net.Addr) string {
	if ta, ok := a.(*net.TCPAddr); ok {
		return ta.IP.String()
	}
	h, _, _ := net.SplitHostPort(a.String())
	return h
}

func (p *Pool) pubBlocked(ip string) bool {
	p.failMu.Lock()
	defer p.failMu.Unlock()
	f := p.fails[ip]
	return f != nil && time.Now().Before(f.until)
}

func (p *Pool) pubFail(ip string) {
	p.failMu.Lock()
	defer p.failMu.Unlock()
	if p.fails == nil {
		p.fails = map[string]*failRec{}
	}
	f := p.fails[ip]
	if f == nil || time.Since(f.first) > failWin {
		if len(p.fails) > 20000 { // bảng quá to (bị dò dồn dập từ rất nhiều IP) → làm lại từ đầu
			p.fails = map[string]*failRec{}
		}
		f = &failRec{first: time.Now()}
		p.fails[ip] = f
	}
	f.n++
	if f.n >= failMax && time.Now().After(f.until) {
		f.until = time.Now().Add(failBlock)
		logf("IP %s dò sai mật khẩu %d lần / %v → chặn %v", ip, f.n, failWin, failBlock)
	}
}

// ---------------------------------------------------------------- đích cấm: chính mạng nhà

func (p *Pool) isSelf(ip net.IP) bool {
	p.mu.RLock()
	pf, self, pub4 := p.prefix, p.self, p.pub4
	p.mu.RUnlock()
	if pf != nil && pf.Contains(ip) {
		return true
	}
	if pub4 != "" && ip.Equal(net.ParseIP(pub4)) {
		return true
	}
	for _, s := range self {
		if s.Equal(ip) {
			return true
		}
	}
	return p.ppp.hasIP(ip)
}

// ---------------------------------------------------------------- nhật ký kết nối của khách (để xử lý khi bị lạm dụng)

var custLogMax int64 = 20 << 20

func (p *Pool) clog(cu *custRT, from net.Addr, host string, port int, how string, up, down int64, t0 time.Time, err error) {
	if p.c.LogFile == "" || p.c.LogFile == "-" {
		return
	}
	e := map[string]interface{}{"t": t0.Format(time.RFC3339), "u": cu.U, "from": ipKey(from), "dst": net.JoinHostPort(host, strconv.Itoa(port)),
		"via": how, "up": up, "down": down, "s": int(time.Since(t0).Seconds())}
	if err != nil {
		e["err"] = err.Error()
	}
	b, _ := json.Marshal(e)
	p.logMu.Lock()
	defer p.logMu.Unlock()
	if p.logF == nil {
		os.MkdirAll(filepath.Dir(p.c.LogFile), 0750)
		f, e2 := os.OpenFile(p.c.LogFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0640)
		if e2 != nil {
			return
		}
		p.logF = f
	}
	if fi, e2 := p.logF.Stat(); e2 == nil && fi.Size() > custLogMax {
		p.logF.Close()
		os.Rename(p.c.LogFile, p.c.LogFile+".1")
		f, e3 := os.OpenFile(p.c.LogFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0640)
		if e3 != nil {
			p.logF = nil
			return
		}
		p.logF = f
	}
	p.logF.Write(append(b, '\n'))
}

// ---------------------------------------------------------------- đổi IP / xem IP của khách

func (p *Pool) custIP(rt *slotRT) string {
	cu := rt.cu
	if cu.K == "v4" {
		if ip := p.ppp.sessIP(cu.sess); ip != nil {
			return ip.String()
		}
		return ""
	}
	p.mu.RLock()
	defer p.mu.RUnlock()
	if cu.unit != nil && cu.unit.ip6 != nil {
		return cu.unit.ip6.String()
	}
	return ""
}

func (p *Pool) custRotate(rt *slotRT) (map[string]interface{}, error) {
	cu := rt.cu
	p.mu.RLock()
	sharers := 0
	for _, o := range p.cust {
		if o.cu.K == cu.K && o.cu.N == cu.N {
			sharers++
		}
	}
	p.mu.RUnlock()
	if cu.S != 1 || sharers != 1 {
		return nil, errors.New("proxy dùng chung (share) không tự đổi IP được")
	}
	if cu.K == "v4" {
		p.mu.Lock()
		if p.rot4 == nil {
			p.rot4 = map[int]time.Time{}
		}
		if w := 10*time.Second - time.Since(p.rot4[cu.sess]); w > 0 {
			p.mu.Unlock()
			return nil, fmt.Errorf("đổi IP quá nhanh, đợi %d giây", int(w.Seconds())+1)
		}
		p.rot4[cu.sess] = time.Now()
		p.mu.Unlock()
		ip, err := p.ppp.redial(cu.sess, 40*time.Second)
		if err != nil {
			return nil, err
		}
		return map[string]interface{}{"ip": ip.String()}, nil
	}
	p.mu.RLock()
	nopf := p.prefix == nil
	p.mu.RUnlock()
	if cu.unit == nil || nopf {
		return nil, errors.New("ô này chưa có IPv6")
	}
	r, err := p.rotate(cu.unit, "v6")
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{"ip": r["ip6"]}, nil
}

// custStat: cho cbhost báo web — IP đang ra của từng ô bán + số dùng từng khách.
func (p *Pool) custStat() map[string]interface{} {
	units := map[string]string{}
	var users []map[string]interface{}
	p.mu.RLock()
	for id, s := range p.sale {
		if s.ip6 != nil {
			units[id] = s.ip6.String()
		}
	}
	type row struct {
		u        string
		conns    int32
		up, down int64
	}
	var rows []row
	for _, rt := range p.cust {
		rows = append(rows, row{rt.cu.U, atomic.LoadInt32(&rt.conns), atomic.LoadInt64(&rt.up), atomic.LoadInt64(&rt.down)})
	}
	p.mu.RUnlock()
	for k, ip := range p.ppp.sessIPs() {
		units[strconv.Itoa(k)] = ip
	}
	for _, r := range rows {
		users = append(users, map[string]interface{}{"u": r.u, "c": r.conns, "up": r.up, "down": r.down})
	}
	return map[string]interface{}{"ok": true, "units": units, "users": users, "pk": p.pubKey}
}

// ---------------------------------------------------------------- khoá P-256 của máy + nhận tài khoản PPPoE đã mã hoá

const pppEncInfo = "cbpool-ppp-v1"

func keyPath(c *Conf) string { return filepath.Join(c.StateDir, "key.json") }

func loadKey(c *Conf, create bool) (*ecdh.PrivateKey, error) {
	if b, err := os.ReadFile(keyPath(c)); err == nil {
		var k struct {
			D string `json:"d"`
		}
		if json.Unmarshal(b, &k) == nil {
			if raw, err := base64.StdEncoding.DecodeString(k.D); err == nil {
				if pk, err := ecdh.P256().NewPrivateKey(raw); err == nil {
					return pk, nil
				}
			}
		}
		if !create {
			return nil, errors.New("file khoá hỏng")
		}
	} else if !create {
		return nil, err
	}
	pk, err := ecdh.P256().GenerateKey(rand.Reader)
	if err != nil {
		return nil, err
	}
	os.MkdirAll(c.StateDir, 0700)
	b, _ := json.Marshal(map[string]string{"d": base64.StdEncoding.EncodeToString(pk.Bytes())})
	tmp := keyPath(c) + ".tmp"
	if err := os.WriteFile(tmp, b, 0600); err != nil {
		return nil, err
	}
	if err := os.Rename(tmp, keyPath(c)); err != nil {
		return nil, err
	}
	return pk, nil
}

// decryptPpp: {"v":1,"e": khoá tạm (65 byte), "i": iv 12 byte, "c": bản mã AES-GCM} — ECDH P-256 → HKDF-SHA256(muối = khoá tạm,
// info "cbpool-ppp-v1") → AES-256-GCM. Giống hệt WebCrypto trên trang Quản trị.
func decryptPpp(priv *ecdh.PrivateKey, enc string) (*PppSecret, error) {
	var e struct {
		V int    `json:"v"`
		E string `json:"e"`
		I string `json:"i"`
		C string `json:"c"`
	}
	if err := json.Unmarshal([]byte(enc), &e); err != nil || e.V != 1 {
		return nil, errors.New("chuỗi mã hoá sai dạng")
	}
	eph, err1 := base64.StdEncoding.DecodeString(e.E)
	iv, err2 := base64.StdEncoding.DecodeString(e.I)
	ct, err3 := base64.StdEncoding.DecodeString(e.C)
	if err1 != nil || err2 != nil || err3 != nil || len(iv) != 12 || len(ct) < 17 || len(ct) > 4096 {
		return nil, errors.New("chuỗi mã hoá sai dạng")
	}
	pub, err := ecdh.P256().NewPublicKey(eph)
	if err != nil {
		return nil, errors.New("khoá tạm sai")
	}
	shared, err := priv.ECDH(pub)
	if err != nil {
		return nil, err
	}
	key, err := hkdf.Key(sha256.New, shared, eph, pppEncInfo, 32)
	if err != nil {
		return nil, err
	}
	blk, _ := aes.NewCipher(key)
	gcm, _ := cipher.NewGCM(blk)
	pt, err := gcm.Open(nil, iv, ct, nil)
	if err != nil {
		return nil, errors.New("không giải mã được (mã hoá cho máy chủ khác, hoặc máy chủ đã đổi khoá)")
	}
	var s PppSecret
	if err := json.Unmarshal(pt, &s); err != nil {
		return nil, errors.New("nội dung sai dạng")
	}
	s.User, s.Pass = strings.TrimSpace(s.User), strings.TrimRight(s.Pass, "\r\n")
	if s.User == "" || s.Pass == "" || len(s.User) > 128 || len(s.Pass) > 128 || strings.ContainsAny(s.User+s.Pass, "\n\r\"\\") {
		return nil, errors.New("tài khoản / mật khẩu PPPoE không hợp lệ")
	}
	if s.Sessions < 0 || s.Sessions > 64 {
		return nil, errors.New("số phiên phải từ 0 tới 64")
	}
	return &s, nil
}

func writeSecret(c *Conf, s *PppSecret) error {
	b, _ := json.Marshal(s)
	os.MkdirAll(filepath.Dir(c.Ppp.Secret), 0700)
	if err := os.WriteFile(c.Ppp.Secret+".tmp", b, 0600); err != nil {
		return err
	}
	return os.Rename(c.Ppp.Secret+".tmp", c.Ppp.Secret)
}

// pppImportCmd: cbhost đưa chuỗi mã hoá qua stdin (không lên dòng lệnh) → giải bằng khoá của máy → ghi file tài khoản → cbpool nạp lại.
func pppImportCmd(c *Conf) int {
	b, _ := io.ReadAll(io.LimitReader(os.Stdin, 64<<10))
	priv, err := loadKey(c, false)
	if err != nil {
		out(map[string]interface{}{"ok": false, "err": "chưa có khoá của máy (cbpool chưa chạy lần nào?): " + err.Error()})
		return 1
	}
	s, err := decryptPpp(priv, strings.TrimSpace(string(b)))
	if err != nil {
		out(map[string]interface{}{"ok": false, "err": err.Error()})
		return 1
	}
	if err := writeSecret(c, s); err != nil {
		out(map[string]interface{}{"ok": false, "err": "không ghi được: " + err.Error()})
		return 1
	}
	if s.Sessions > 0 && pppPlugin() == "" {
		installPpp(io.Discard)
	}
	r := map[string]interface{}{"ok": true, "user": safePrefix(s.User) + "***", "sessions": s.Sessions}
	if _, err := ctlCall(c.Ctl, map[string]string{"cmd": "reload"}, 20*time.Second); err != nil {
		r["note"] = "cbpool chưa chạy — lần chạy tới sẽ dùng tài khoản này"
	}
	out(r)
	return 0
}

func (p *Pool) pubIP4() string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.pub4
}
