// cbpool — KHO PROXY NHIỀU IP của CloudBlue (27/11). Chạy trên máy chủ Proxmox (cbhost tự cài, tự cập nhật).
//
// Mỗi "ô" proxy (p01, p02, …) có user / mật khẩu riêng và IP ra riêng:
//   - IPv6: 1 địa chỉ ngẫu nhiên trong dải /64 nhà mạng cấp cho mạng nhà (gắn /128 vào card, không làm máy chủ đổi địa chỉ chính).
//     Đổi IP = địa chỉ ngẫu nhiên mới, tức thì.
//   - IPv4: các phiên PPPoE quay thêm bằng tài khoản mạng (macvlan + pppd, mỗi phiên 1 IP công khai). Ô thứ i dùng phiên i % số phiên.
//     Đổi IP = quay lại phiên đó. Chưa có tài khoản / modem không cho PPPoE đi qua → IPv4 ra bằng IP chung của mạng (fallback4).
//   - Đích có IPv6 (tên miền có AAAA) → đi IPv6 của ô; còn lại → IPv4 của ô.
//
// Một cổng nhận cả SOCKS5 và HTTP (CONNECT + http://), bắt buộc user / mật khẩu. Chặn đích mạng nội bộ (không lọt vào mạng nhà),
// chặn cổng gửi thư (25, 465, 587), giới hạn tốc độ từng ô. Chỉ nhận người dùng trong mạng nội bộ (allow_from).
// Đổi IP từ xa: GET http://<máy>:<cổng>/rotate?key=<khoá đổi IP của ô>  ·  xem IP: /ip?key=…
//
// Lệnh:
//
//	cbpool run [-c CONF]               chạy (systemd)
//	cbpool status [-c CONF]            trạng thái JSON (có user / mật khẩu từng ô — chỉ root đọc được qua ổ cắm điều khiển)
//	cbpool rotate ID [v6|v4|all]       đổi IP 1 ô
//	cbpool reload                      đọc lại cấu hình + tài khoản PPPoE
//	cbpool ppp-test [-i CARD] [--dial N]   dò máy chủ PPPoE của nhà mạng (KHÔNG cần mật khẩu); --dial: quay thử N phiên bằng tài khoản đã lưu
//	cbpool ppp-set                     nhập tài khoản PPPoE (mật khẩu gõ ẩn, chỉ lưu trên máy này, quyền 600)
//	cbpool version
package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"math/big"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

const VER = "27.11b"

type PppConf struct {
	Iface    string `json:"iface"`    // card đi PPPoE (mặc định = card IPv6 / vmbr0)
	Sessions int    `json:"sessions"` // số phiên (tài khoản PPPoE ghi đè nếu có "sessions")
	Secret   string `json:"secret"`   // file tài khoản (JSON {user, pass, sessions}) — mặc định /etc/cloudblue/cbpool-ppp.secret
	Mtu      int    `json:"mtu"`
	Pppd     string `json:"pppd"`
	Macvlan  *bool  `json:"macvlan"` // mỗi phiên 1 MAC riêng (mặc định có)
	Unit0    int    `json:"unit0"`   // số giao diện pppd đầu tiên (ppp100…)
	Table0   int    `json:"table0"`  // bảng định tuyến đầu tiên (2100…)
	Probe    *bool  `json:"probe"`   // 27.11b · tự dò modem có cho PPPoE đi qua (gói PADI, không mật khẩu) khi chưa có phiên nào lên (mặc định có)
	MvPrefix string `json:"-"`       // tên macvlan (cbpp0…; lệnh thử dùng cbpt0…)
}

type Conf struct {
	Listen     string   `json:"listen"`
	Iface6     string   `json:"iface6"`
	V6         *bool    `json:"v6"`
	Slots      int      `json:"slots"`
	BwKbps     int      `json:"bw_kbps"`
	MaxConns   int      `json:"max_conns"`
	MaxTotal   int      `json:"max_total"`
	BlockPorts []int    `json:"block_ports"`
	Fallback4  *bool    `json:"fallback4"`
	AllowFrom  []string `json:"allow_from"`
	AllowDst   []string `json:"allow_dst"` // dải riêng được phép làm đích (bộ thử)
	StateDir   string   `json:"state_dir"`
	Ctl        string   `json:"ctl"`
	Ppp        PppConf  `json:"ppp"`

	allowFrom []*net.IPNet
	allowDst  []*net.IPNet
	path      string
}

func bp(b *bool, d bool) bool {
	if b == nil {
		return d
	}
	return *b
}

func defConfPath() string { return envOr("CBPOOL_CONF", "/etc/cloudblue/cbpool.json") }

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func loadConf(path string) (*Conf, error) {
	c := &Conf{path: path}
	if b, err := os.ReadFile(path); err == nil {
		if err := json.Unmarshal(b, c); err != nil {
			return nil, fmt.Errorf("cấu hình %s hỏng: %v", path, err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	if c.Listen == "" {
		c.Listen = "0.0.0.0:8899"
	}
	if c.Slots <= 0 {
		c.Slots = 30
	}
	if c.Slots > 500 {
		c.Slots = 500
	}
	if c.BwKbps < 0 {
		c.BwKbps = 0
	} else if c.BwKbps == 0 {
		c.BwKbps = 30000
	}
	if c.MaxConns <= 0 {
		c.MaxConns = 256
	}
	if c.MaxTotal <= 0 {
		c.MaxTotal = 4096
	}
	if c.BlockPorts == nil {
		c.BlockPorts = []int{25, 465, 587}
	}
	if c.AllowFrom == nil {
		c.AllowFrom = []string{"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "fc00::/7", "fe80::/10", "::1/128"}
	}
	if c.StateDir == "" {
		c.StateDir = "/var/lib/cloudblue/cbpool"
	}
	if c.Ctl == "" {
		c.Ctl = "/run/cbpool/ctl.sock"
	}
	if c.Ppp.Secret == "" {
		c.Ppp.Secret = "/etc/cloudblue/cbpool-ppp.secret"
	}
	if c.Ppp.Mtu <= 0 {
		c.Ppp.Mtu = 1492
	}
	if c.Ppp.Pppd == "" {
		c.Ppp.Pppd = "pppd"
	}
	if c.Ppp.Unit0 <= 0 {
		c.Ppp.Unit0 = 100
	}
	if c.Ppp.Table0 <= 0 {
		c.Ppp.Table0 = 2100
	}
	for _, s := range c.AllowFrom {
		_, n, err := net.ParseCIDR(strings.TrimSpace(s))
		if err != nil {
			return nil, fmt.Errorf("allow_from %q sai: %v", s, err)
		}
		c.allowFrom = append(c.allowFrom, n)
	}
	for _, s := range c.AllowDst {
		_, n, err := net.ParseCIDR(strings.TrimSpace(s))
		if err != nil {
			return nil, fmt.Errorf("allow_dst %q sai: %v", s, err)
		}
		c.allowDst = append(c.allowDst, n)
	}
	return c, nil
}

// ---------------------------------------------------------------- trạng thái lưu (user / mật khẩu từng ô)

type Slot struct {
	ID   string `json:"id"`
	Pass string `json:"pass"`
	Rot  string `json:"rot"` // khoá đổi IP (link /rotate?key=)
	IID  string `json:"iid"` // 16 chữ số hex: phần sau của địa chỉ IPv6
}

type PState struct {
	Slots []*Slot           `json:"slots"`
	Added []string          `json:"added"` // địa chỉ IPv6 cbpool đã gắn (dọn khi đổi dải / bớt ô)
	Macs  map[string]string `json:"macs"`  // MAC riêng từng phiên PPPoE (giữ cố định qua các lần chạy)
}

var stMu sync.Mutex

func statePath(c *Conf) string { return filepath.Join(c.StateDir, "state.json") }

func loadState(c *Conf) *PState {
	st := &PState{Macs: map[string]string{}}
	if b, err := os.ReadFile(statePath(c)); err == nil {
		json.Unmarshal(b, st)
	}
	if st.Macs == nil {
		st.Macs = map[string]string{}
	}
	return st
}

func saveState(c *Conf, st *PState) error {
	stMu.Lock()
	defer stMu.Unlock()
	if err := os.MkdirAll(c.StateDir, 0700); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(st, "", " ")
	tmp := statePath(c) + ".tmp"
	if err := os.WriteFile(tmp, b, 0600); err != nil {
		return err
	}
	return os.Rename(tmp, statePath(c))
}

const pwChars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

func randStr(n int) string {
	b := make([]byte, n)
	for i := range b {
		x, _ := rand.Int(rand.Reader, big.NewInt(int64(len(pwChars))))
		b[i] = pwChars[x.Int64()]
	}
	return string(b)
}

func randIID() string {
	for {
		b := make([]byte, 8)
		rand.Read(b)
		b[0] &^= 0x02                 // bit "u/l" = 0: không trông như địa chỉ sinh từ MAC
		if b[0]|b[1]|b[2]|b[3] != 0 { // tránh ::x nhỏ (dễ trùng địa chỉ đặt tay)
			return hex.EncodeToString(b)
		}
	}
}

func slotID(i int) string { return fmt.Sprintf("p%02d", i+1) }

// ensureSlots: đủ c.Slots ô (ô cũ giữ nguyên mật khẩu), thừa thì bỏ.
func ensureSlots(c *Conf, st *PState) bool {
	ch := false
	for len(st.Slots) < c.Slots {
		st.Slots = append(st.Slots, &Slot{ID: slotID(len(st.Slots)), Pass: randStr(16), Rot: randStr(20), IID: randIID()})
		ch = true
	}
	if len(st.Slots) > c.Slots {
		st.Slots = st.Slots[:c.Slots]
		ch = true
	}
	for i, s := range st.Slots {
		if s.ID != slotID(i) || len(s.Pass) < 12 || len(s.Rot) < 16 || len(s.IID) != 16 {
			if s.ID != slotID(i) {
				s.ID = slotID(i)
			}
			if len(s.Pass) < 12 {
				s.Pass = randStr(16)
			}
			if len(s.Rot) < 16 {
				s.Rot = randStr(20)
			}
			if _, err := hex.DecodeString(s.IID); err != nil || len(s.IID) != 16 {
				s.IID = randIID()
			}
			ch = true
		}
	}
	return ch
}

// ---------------------------------------------------------------- tài khoản PPPoE (chỉ trên máy này)

type PppSecret struct {
	User     string `json:"user"`
	Pass     string `json:"pass"`
	Sessions int    `json:"sessions"`
}

func loadSecret(c *Conf) (*PppSecret, error) {
	b, err := os.ReadFile(c.Ppp.Secret)
	if err != nil {
		return nil, err
	}
	s := &PppSecret{}
	if err := json.Unmarshal(b, s); err != nil {
		return nil, fmt.Errorf("file tài khoản PPPoE hỏng: %v", err)
	}
	if s.User == "" || s.Pass == "" {
		return nil, errors.New("file tài khoản PPPoE thiếu user / mật khẩu")
	}
	return s, nil
}

func logf(f string, a ...interface{}) {
	fmt.Fprintf(os.Stderr, time.Now().Format("01/02 15:04:05 ")+f+"\n", a...)
}

func out(v interface{}) {
	b, _ := json.MarshalIndent(v, "", " ")
	fmt.Println(string(b))
}

// ---------------------------------------------------------------- lệnh

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "dùng: cbpool run|status|rotate|reload|ppp-test|ppp-set|version")
		os.Exit(2)
	}
	cmd := os.Args[1]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	cpath := fs.String("c", defConfPath(), "file cấu hình")
	iface := fs.String("i", "", "card mạng (ppp-test)")
	dial := fs.Int("dial", 0, "ppp-test: quay thử N phiên bằng tài khoản đã lưu")
	wait := fs.Duration("t", 3*time.Second, "ppp-test: chờ trả lời")
	args := os.Args[2:]
	var pos []string
	for len(args) > 0 { // cho phép tham số vị trí xen giữa cờ
		fs.Parse(args)
		args = fs.Args()
		if len(args) > 0 {
			pos = append(pos, args[0])
			args = args[1:]
		}
	}
	switch cmd {
	case "version":
		fmt.Println(VER)
	case "run":
		c, err := loadConf(*cpath)
		if err != nil {
			logf("%v", err)
			os.Exit(1)
		}
		os.Exit(run(c))
	case "status", "rotate", "reload":
		c, err := loadConf(*cpath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		req := map[string]string{"cmd": cmd}
		if cmd == "rotate" {
			if len(pos) < 1 {
				fmt.Fprintln(os.Stderr, "dùng: cbpool rotate ID [v6|v4|all]")
				os.Exit(2)
			}
			req["slot"] = pos[0]
			req["what"] = "all"
			if len(pos) > 1 {
				req["what"] = pos[1]
			}
		}
		r, err := ctlCall(c.Ctl, req, 60*time.Second)
		if err != nil {
			fmt.Fprintln(os.Stderr, "cbpool không chạy / không hỏi được:", err)
			os.Exit(1)
		}
		fmt.Println(string(r))
	case "ppp-test":
		c, err := loadConf(*cpath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(pppTestCmd(c, *iface, *dial, *wait))
	case "ppp-set":
		c, err := loadConf(*cpath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(pppSetCmd(c))
	default:
		fmt.Fprintln(os.Stderr, "lệnh lạ:", cmd)
		os.Exit(2)
	}
}

func run(c *Conf) int {
	logf("cbpool %s: cổng %s · %d ô · IPv6 %v · tốc độ %d kbps/ô", VER, c.Listen, c.Slots, bp(c.V6, true), c.BwKbps)
	p, err := newPool(c)
	if err != nil {
		logf("không khởi động được: %v", err)
		return 1
	}
	ln, err := net.Listen("tcp", c.Listen)
	if err != nil {
		logf("không mở được cổng %s: %v", c.Listen, err)
		return 1
	}
	p.start()
	go p.serve(ln)
	go p.ctlServe()
	sig := make(chan os.Signal, 2)
	signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP)
	for s := range sig {
		if s == syscall.SIGHUP {
			p.reload()
			continue
		}
		break
	}
	logf("dừng")
	ln.Close()
	p.stop()
	return 0
}
