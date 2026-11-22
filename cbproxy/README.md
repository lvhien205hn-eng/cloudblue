# cbproxy — proxy riêng cho từng Cloud Phone (22/11)

Khách dán proxy `IP:Port:User:Pass` (web: Công cụ › 🌐 Proxy hoặc nút 🌐 Proxy trên thẻ máy · app máy tính: Công cụ › Proxy ·
app Android bản tải từ web: Công cụ › Proxy). Mọi kết nối TCP của app trong máy Android đi qua proxy đó. **Chỉ Cloud Phone** —
máy PC (VPS GPU) không có.

## Đường đi

```
web / app ──POST /cpapi/<máy>/proxy {do:set, url, kind}──▶ cpapi.py (chỉ chủ máy / admin; proxy đi qua stdin, không nằm trên dòng lệnh)
   └─▶ phonectl.py proxy TÊN --set --url-stdin   (lưu vào phones.json của máy chủ → áp dụng)
          └─▶ adb (root: su / adb là root / "adb root" 1 lần rồi "adb unroot" với máy KernelSU)
                 /data/adb/cbproxy/{cbproxy, conf.json (600), state.json, log}
                 cbproxy up → super (thoát nhóm tiến trình của adbd, oom -1000) → worker
                     iptables nat OUTPUT → chuỗi CBPX: bỏ qua mạng nội bộ + IP proxy + gói có dấu 0x40000000 (của chính cbproxy)
                     còn lại: TCP → REDIRECT (thiếu REDIRECT thì DNAT) → 127.0.0.1:12081 → SOCKS5 / HTTP CONNECT có user/pass
                     CBPXF: chặn UDP 443 (QUIC) để app chuyển sang TCP · CBPX6: chặn TCP IPv6 ra ngoài (app tự dùng IPv4)
```

- **Proxy chết / sai mật khẩu** → máy tự đi mạng thường (không mất mạng), 15 giây thử lại 1 lần, sống lại thì dùng lại.
  Proxy báo không tới được đích (đích chết) → không đi thẳng (đúng như đích chết thật).
- **Trạng thái** `/data/local/tmp/cbproxy.json` (adb thường đọc được, không có user / mật khẩu): chế độ proxy / direct / crashed,
  IP ra (đo qua 1.1.1.1/cdn-cgi/trace, api.ipify.org, ifconfig.me), độ trễ, lỗi, nhịp sống 5 giây.
- **Tự bật lại**: máy bật (wait_boot / _wake_one — trước khi khách vào), khách bấm Khởi động lại (proxykeep --wait), vòng 5 phút
  (`rootfix --all` của cloudphoned). Hỏng hẳn (máy thiếu iptables…) → 30 phút mới thử lại.
- **Không qua proxy**: UDP (gọi video, game dùng UDP), DNS (Android hỏi qua UDP 53). Đổi Android = máy mới → nhập lại proxy.

## Lệnh trên máy chủ

```powershell
python phonectl.py proxy TÊN --get                      # trạng thái (che mật khẩu)
python phonectl.py proxy TÊN --set --url "1.2.3.4:8080:user:pass" [--kind auto|socks5|http]
python phonectl.py proxy TÊN --again                    # áp dụng lại
python phonectl.py proxy TÊN --off
python phonectl.py proxykeep --all                      # bật lại proxy cho máy nào đang có proxy mà tiến trình không chạy
```

File `windows/cbproxy-x86_64` tự tải từ GitHub lần đầu dùng (md5 ghim trong `phonectl.py` → `CBPX_FILE`).

## Dựng lại file chạy (phải ra đúng md5 đã ghim)

```bash
cd cbproxy
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -buildvcs=false -ldflags "-s -w -buildid=" -o cbproxy-x86_64 .   # Go 1.24.7
md5sum cbproxy-x86_64      # = CBPX_FILE trong windows/phonectl.py → chép sang windows/cbproxy-x86_64
```

## Bộ thử

- `sudo python3 cbproxy/test_cbproxy.py <bản cbproxy có quyền chạy>` — Linux thật, iptables thật, trong 1 không gian mạng riêng
  (`unshare -n`): SOCKS5 / HTTP có mật khẩu, proxy chết → đi thẳng → sống lại, sai mật khẩu, đích chết, iptables bị xoá tự gắn lại,
  đổi proxy, tắt sạch.
- `python3 cbproxy/test_proxy_server.py` — phonectl (đọc chuỗi proxy, lệnh proxy, đẩy vào máy bằng adb giả, adb root của KernelSU,
  tự bật lại) + cpapi (chỉ chủ máy, mật khẩu qua stdin, 1 việc / máy, máy chủ cũ).
- `python3 winpc/tests/web/test_play_proxy.py blueroblox-site/play.html` — hộp 🌐 Proxy trên web (trình duyệt thật, tiếng Việt + English).
