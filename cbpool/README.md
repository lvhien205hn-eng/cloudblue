# cbpool — kho proxy nhiều IP (27/11)

Chạy trên **máy chủ Proxmox** (cbhost tự tải `proxmox/cbpool-x86_64` đúng md5 ghim, tự chạy dịch vụ `cloudblue-pool`). Mỗi **ô**
proxy (`p01`, `p02`, …) có user / mật khẩu riêng và **IP ra riêng**:

- **IPv6**: 1 địa chỉ ngẫu nhiên trong dải /64 nhà mạng cấp cho mạng nhà (gắn `/128` lên `vmbr0`, cờ "hết hạn ưu tiên" → máy chủ
  không tự dùng cho kết nối của nó). Đổi IP = địa chỉ mới, tức thì. Nhà mạng đổi dải → tự gắn lại theo dải mới.
- **IPv4**: mỗi phiên PPPoE quay thêm bằng tài khoản mạng (macvlan riêng MAC + `pppd`) = 1 IP công khai. Ô thứ *i* dùng phiên
  *i* % số phiên. Đổi IP = quay lại phiên đó. Chưa có PPPoE → IPv4 ra bằng IP chung của mạng.
- Đích có IPv6 (tên miền có AAAA) → đi IPv6 của ô; đích chỉ có IPv4 → IPv4 của ô.

Một cổng (mặc định `8899`) nhận cả **SOCKS5** và **HTTP** (CONNECT + `http://`), bắt buộc user / mật khẩu. Chặn đích mạng nội bộ,
cổng gửi thư (25, 465, 587); giới hạn tốc độ từng ô (mặc định 30 Mbit/s mỗi chiều); chỉ nhận máy trong mạng nội bộ (`allow_from`).
VPS khách trên cùng máy Proxmox bị cách ly sẵn (cbhost, nftables) nên không dùng được.

## Dùng

Quản trị › VPS ảo hoá › Máy chủ › **🌐 Kho proxy nhiều IP**: danh sách `IP:8899:pNN:mật khẩu` → dán vào 🌐 Proxy của Cloud Phone.
Đổi IP từ xa: `http://<IP máy chủ>:8899/rotate?key=<khoá đổi IP>` (`&what=v6|v4|all`) · xem IP: `/ip?key=…`.

Shell của Proxmox:

```
cbpool status                 # trạng thái JSON (có mật khẩu từng ô)
cbpool rotate p03 [v6|v4|all] # đổi IP 1 ô
cbpool ppp-test               # dò máy chủ PPPoE của nhà mạng qua modem — KHÔNG cần mật khẩu
cbpool ppp-set                # nhập tài khoản PPPoE (mật khẩu gõ ẩn, chỉ lưu /etc/cloudblue/cbpool-ppp.secret, quyền 600) + số phiên
cbpool ppp-test --dial 2      # quay thử 2 phiên bằng tài khoản đã lưu (không đụng phiên đang chạy), in IP từng phiên
```

⚠ Nếu nhà mạng chỉ cho 1 phiên / tài khoản, quay thêm có thể làm rớt mạng chính của modem vài giây — thử lúc vắng khách.

**Tự dò PPPoE (27.11b):** khi chưa có phiên PPPoE nào lên, dịch vụ tự gửi gói dò PADI (như `cbpool ppp-test`, KHÔNG mật khẩu, không xin
phiên) lúc bật và 6 giờ / lần → `status.ppp.disc = {ok, ac, iface, t}` (hoặc `err`) → trang Quản trị hiện ngay "modem có cho PPPoE đi qua
không". Tắt: `"ppp": {"probe": false}`. Dò lại ngay: `cbpool ppp-test` (hoặc lệnh điều khiển `{"cmd":"disc"}`).

## Bán proxy cho khách (27.11c · web: Proxy dân cư, SQL v63)

- Web bán (IPv6 / IPv4, riêng hoặc share 2–5 người) → cbhost 27/11g mỗi phút gọi `px_host_sync` → ghi `/etc/cloudblue/cbpool-users.json`
  (quyền 600: `{"bw","fb4","sale4","maxc","self":[IP nhà],"users":[{"u","p","k":"v6|v4","n":"s007|3","x":hết hạn,"s":share,"r"?}]}`)
  → `cbpool users` (cbhost tự gọi qua ổ cắm điều khiển) nạp lại, khách bị bỏ / hết hạn bị cắt kết nối ngay.
- Tài khoản khách đăng nhập được từ **Internet** (modem chuyển cổng ngoài → máy chủ cổng 8899); tài khoản ô nội bộ `pNN` vẫn chỉ trong mạng nhà;
  khi chưa bán gì, máy ngoài bị đóng kết nối ngay như cũ. Dò sai mật khẩu 20 lần / 10 phút → chặn IP đó 15 phút.
- `v6`: ô bán `s001…` (IPv6 riêng, tách khỏi `pNN`), chỉ đi IPv6 (`fb4` = cho đích chỉ có IPv4 đi IPv4 chung). `v4`: đúng phiên PPPoE `k`;
  phiên đã bán (hoặc mọi phiên khi `sale4`) không chia cho ô nội bộ. Đổi IP (`/rotate?key=`, từ mọi nơi) chỉ cho proxy riêng (ô có 1 khách).
- Cấm đích là chính nhà: dải /64 IPv6 của máy, IP công khai (`self` + tự hỏi 30 phút / lần), IP các phiên PPPoE.
- Nhật ký kết nối của khách: `/var/log/cloudblue/cbpool-khach.log` (JSON 1 dòng / kết nối, xoay vòng 20 MB) — để xử lý khi bị lạm dụng.
- **Tài khoản PPPoE nhập trên web**: máy tạo khoá P-256 (`state_dir/key.json`, 600) → `status.pk`; trình duyệt mã hoá
  (ECDH P-256 → HKDF-SHA256, muối = khoá tạm, info `cbpool-ppp-v1` → AES-256-GCM) → cbhost đưa chuỗi qua stdin cho `cbpool ppp-import`.

Cấu hình `/etc/cloudblue/cbpool.json` (cbhost chỉ ghi lần đầu): `listen`, `iface6`, `slots`, `bw_kbps`, `max_conns`, `block_ports`,
`fallback4`, `allow_from`, `ppp: {iface, sessions, mtu, probe}`, `users_file`, `log_file` (`"-"` = tắt nhật ký khách). Sửa xong: `systemctl restart cloudblue-pool` (hoặc `cbpool reload`).
Tắt hẳn: `"pool": false` trong `/etc/cloudblue/cbhost.conf`.

## Dựng lại (phải ra đúng md5 ghim ở `POOL_FILE` trong `proxmox/cbhost.py`)

```bash
cd cbpool
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -buildvcs=false -ldflags "-s -w -buildid=" -o ../proxmox/cbpool-x86_64 .   # Go 1.24.7
md5sum ../proxmox/cbpool-x86_64
```

## Bộ thử

- `go test -c -o /tmp/cbpool.test . && sudo unshare -n env CBPOOL_NETNS_TEST=1 /tmp/cbpool.test -test.v` — mật khẩu, chặn đích, HTTP,
  tên miền, giới hạn tốc độ, link đổi IP, ổ cắm điều khiển; máy có IPv6: mỗi ô 1 IPv6, đổi IP, đổi dải.
- `sudo python3 .github/cbpool-check/test_pool_net.py ./cbpool-x86_64` — thử thật: cầu `vmbr0` + macvlan + `pppd` ↔ `pppoe-server`
  (nhiều phiên, mỗi phiên 1 IPv4, đổi IP, phiên bị cắt tự quay lại), IPv6 qua NDP thật. CI: `.github/workflows/cbpool-check.yml`.
