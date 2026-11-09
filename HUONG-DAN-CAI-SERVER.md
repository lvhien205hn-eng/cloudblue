# Hướng dẫn cài máy chủ Điện thoại đám mây (BlueRoblox Cloud)

Tài liệu này dùng cho máy chủ kiểu **Xeon nhiều nhân + RAM lớn + card GTX 1080**, chạy **Ubuntu 22.04**, cho thuê điện thoại Android giống UgPhone.
Mọi file nằm trong repo này (thư mục gốc). **Không bao giờ** đưa khoá bí mật (`SUPABASE_SERVICE_KEY`, mã Cloudflare) lên GitHub.

> **Có 2 trường hợp:**
> - **Máy chủ đầu tiên** (máy chính, đang chạy web): làm **Phần 1 → Phần 3**.
> - **Thêm máy chủ** (máy thứ 2, 3…): chỉ cần **Phần 1** trên máy mới, rồi **Phần 4** (1 lệnh trên máy chính). Máy mới tự có đủ tính năng như máy chính.

---

## Phần 1 — Chuẩn bị phần cứng & Ubuntu 22.04

**Cấu hình tham khảo (máy đang chạy):** 2× Xeon E5-2686 v4 (72 luồng) · RAM 128GB · GTX 1080 8GB · SSD NVMe 512GB · mạng 1Gbps.

1. **BIOS:** bật *Restore on AC Power Loss = Power On* (mất điện có lại tự bật máy). Không cần bật ảo hoá.
2. **Tải Ubuntu 22.04 LTS:** https://releases.ubuntu.com/22.04/ (bản *Server* hoặc *Desktop* đều được), ghi ra USB bằng Rufus: https://rufus.ie
3. **Khi cài:**
   - Chọn dùng **toàn bộ ổ** (*Use an entire disk*). Có hỏi LVM thì để mặc định — script sẽ tự mở rộng hết dung lượng.
   - Đặt tên đăng nhập **giống nhau trên mọi máy** (VD `lehien`) cho dễ quản lý.
   - Bản Server: tick **Install OpenSSH server**.
4. **Sau khi cài xong**, mở Terminal trên máy đó:
   ```bash
   sudo apt update && sudo apt install -y openssh-server && hostname -I
   ```
   Ghi lại số IP hiện ra (VD `192.168.1.30`). Nên vào modem **đặt IP cố định** cho máy này (DHCP reservation).
5. **(Tuỳ chọn) Driver card GTX 1080** — chỉ để trang admin hiện nhiệt độ / VRAM của card:
   ```bash
   sudo ubuntu-drivers install && sudo reboot
   ```

> ℹ️ **Về card GTX 1080:** máy ảo Android (redroid) chỉ dùng chung được card **Intel / AMD**. Card NVIDIA **không** gánh hình cho máy ảo được (thử rồi → màn đen), nên mọi máy vẽ hình bằng CPU — CPU 72 luồng vẫn dư sức. Muốn GPU gánh cho mọi máy: gắn thêm 1 card **AMD** (RX 580 / RX 6600…).

---

## Phần 2 — Cài MÁY CHỦ ĐẦU TIÊN (máy chính)

### 2.1. Chạy SQL trên Supabase (1 lần)
Mở https://supabase.com/dashboard/project/nprftgodswlpzomcttal/sql/new → lần lượt dán từng file `.sql` trong repo → **Run** (chạy lại không sao):
`cloud-phones-v3` … `v17`, `product-english.sql`, `product-restock.sql`.

### 2.2. Cài trọn bộ máy chủ (1 lệnh)
```bash
curl -fsSL -o ~/cloudphone-setup.sh "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/cloudphone-setup.sh?t=$(date +%s)" && sudo bash ~/cloudphone-setup.sh
```
Khi được hỏi:
- **SUPABASE_SERVICE_KEY:** dán khoá (Supabase → Project Settings → API → `service_role`). Không hiện chữ là bình thường.
- **Link điều khiển công khai:** Enter (mặc định `https://phone.blueroblox.shop`).
- **TOKEN tunnel Cloudflare:** vào https://one.dash.cloudflare.com → *Networks* → *Tunnels* → *Create a tunnel* → *Cloudflared* → copy token → dán. Trong tunnel thêm *Public hostname*: `phone` · `blueroblox.shop` · **HTTP** · `localhost:8010`.

Cài xong: **thoát SSH rồi vào lại** (để dùng được docker). Kiểm tra: `cloudphone` → `cpapi`, `cloudphoned`, `watchdog` = **active**, `binder` = **bật**.

### 2.3. Các bản Android (9 / 10 / 11 / 12)
```bash
curl -fsSL -o ~/android-versions.sh "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/android-versions.sh?t=$(date +%s)"
bash ~/android-versions.sh build      # dựng Android 9 + 10 (15–30 phút)
bash ~/android-versions.sh a12h-on    # Android 12 dùng bộ dịch ARM Houdini (Roblox chạy ổn)
```
Rồi vào **Admin → ĐT đám mây → Phiên bản Android đang bán**: nhập `12,11,10,9` → **Lưu tất cả**.

### 2.4. Root cho mọi máy (tool cần root chạy được)
```bash
curl -fsSL -o ~/cloudphone-root.sh "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/cloudphone-root.sh?t=$(date +%s)" && bash ~/cloudphone-root.sh su
```

### 2.5. Kho ứng dụng (Chrome, Firefox… cài 1 chạm)
```bash
curl -fsSL -o ~/cloudphone-apps.sh "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/cloudphone-apps.sh?t=$(date +%s)"
bash ~/cloudphone-apps.sh firefox                 # Firefox chính thức Mozilla
bash ~/cloudphone-apps.sh grab chrome cp_xxxxxxxx  # Chrome: cài từ CH Play trong 1 máy rồi chép vào kho
```

### 2.6. (Tuỳ chọn) Đường thẳng ⚡ ít trễ
`fast-route.sh` — mở cổng **8443** trên modem trỏ về máy chủ (KHÔNG mở 8000, 5555–5585).

### 2.7. Kiểm tra toàn bộ chức năng
```bash
curl -fsSL -H "Accept: application/vnd.github.raw" -o ~/cloudphone-selftest.sh "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/cloudphone-selftest.sh"
bash ~/cloudphone-selftest.sh
```
Đúng khi cuối kết quả là **Lỗi: 0**.

---

## Phần 3 — Tài nguyên DÙNG CHUNG (đã bật sẵn)

Máy ảo **không giữ chết** CPU / RAM / ổ cứng: máy này không dùng thì máy khác dùng. Máy chủ chỉ **ngừng nhận máy mới** khi tài nguyên **thật** chạm ngưỡng:

| Tài nguyên | Cho cấp tối đa | Ngừng nhận máy mới khi |
|---|---|---|
| CPU | ×4 số nhân thật | CPU thật TB 5 phút ≥ **85%** |
| RAM | ×2 RAM thật | RAM thật đang dùng ≥ **85%** |
| Ổ cứng | không giới hạn theo máy | ổ đã dùng ≥ **90%** hoặc còn < 15GB |

Xem nhanh: `python3 ~/phonectl.py capacity` · Đổi mức trong `~/cloudphone.conf` (xem Phần 6) rồi `cloudphone update`.

---

## Phần 4 — THÊM MÁY CHỦ MỚI (chỉ 1 lệnh)

Máy mới (chung xưởng hay ở mạng khác đều được) chỉ cần làm **Phần 1**. Rồi trên **máy chủ chính**:

**Lần đầu tiên** (1 lần):
1. Tải lệnh:
   ```bash
   curl -fsSL -H "Accept: application/vnd.github.raw" -o ~/cloudphone-addnode.sh "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/cloudphone-addnode.sh"
   ```
2. Tạo mã Cloudflare: https://dash.cloudflare.com/profile/api-tokens → *Create Token* → *Create Custom Token*
   - Permissions: `Account · Cloudflare Tunnel · Edit` và `Zone · DNS · Edit`
   - Zone Resources: `Include · Specific zone · blueroblox.shop`
   - *Continue to summary* → *Create Token* → **Copy** (lệnh sẽ hỏi, dán vào).

**Mỗi máy mới:**
```bash
bash ~/cloudphone-addnode.sh 192.168.1.30            # thay bằng IP máy mới
bash ~/cloudphone-addnode.sh 192.168.1.30 tenkhac    # nếu tên đăng nhập máy mới khác máy chính
```
Nhập mật khẩu máy mới khi được hỏi → chờ 15–30 phút → hiện **XONG: đã thêm máy chủ node2**.
Lệnh tự: tạo link riêng `phone2.blueroblox.shop`, chép các bản Android, bộ root, app cài sẵn, cấu hình, rồi cài dịch vụ trên máy mới.

- **Máy ở mạng khác:** dùng IP công khai của mạng bên đó + mở cổng **22** (SSH) trỏ về máy mới trong lúc cài.
- Máy còn trống nhiều hơn tự nhận đơn thuê trước. Admin → *ĐT đám mây* → *Máy chủ* thấy từng máy, bấm **Ngừng nhận máy** để tạm không cho thuê trên máy đó.
- `bash ~/cloudphone-addnode.sh list` — danh sách máy chủ · `bash ~/cloudphone-addnode.sh update` — cập nhật **mọi** máy chủ.
- Lỗi giữa chừng: chạy lại đúng lệnh cũ (phần đã xong tự bỏ qua).

---

## Phần 5 — Lệnh dùng hằng ngày

| Lệnh | Việc |
|---|---|
| `cloudphone` | Trạng thái máy chủ |
| `cloudphone update` | Tải bản mới từ GitHub + khởi động lại dịch vụ |
| `cloudphone restart` | Khởi động lại dịch vụ + phát hình + tunnel |
| `cloudphone logs` / `cloudphone logs cpapi` | Nhật ký |
| `cloudphone list` | Danh sách máy khách |
| `cloudphone apps` | Cài app trong `~/apk-cai-san` cho mọi máy |
| `python3 ~/phonectl.py capacity` | Tài nguyên còn trống |
| `bash ~/cloudphone-selftest.sh` | Kiểm tra mọi chức năng |

> Nếu GitHub vừa cập nhật mà máy chủ vẫn tải bản cũ (GitHub giữ bộ nhớ đệm ~5 phút):
> ```bash
> for f in phonectl.py cloudphoned.py cpapi.py; do curl -fsSL -H "Accept: application/vnd.github.raw" -o ~/$f.new "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/$f" && python3 -m py_compile ~/$f.new && mv ~/$f.new ~/$f && echo "✓ $f"; done; sudo systemctl restart cloudphoned cpapi
> ```

---

## Phần 6 — Cấu hình `~/cloudphone.conf` (KHÔNG đưa lên GitHub)

| Dòng | Ý nghĩa |
|---|---|
| `SUPABASE_URL=` / `SUPABASE_SERVICE_KEY=` | Kết nối Supabase (bí mật) |
| `PUBLIC_BASE=https://phone.blueroblox.shop` | Link điều khiển của máy chủ này |
| `NODE_ID=` | Tên máy chủ (mỗi máy 1 tên) |
| `PRIMARY=0` | Máy chủ phụ (máy chính không cần dòng này) |
| `A12_ARM=houdini` | Android 12 dùng bộ dịch Houdini |
| `ROOT=1` | Root bằng su (mặc định). `0` = tắt root |
| `CPU_OVER=4` · `CPU_BUSY_PCT=85` | CPU dùng chung ×4 · ngừng nhận khi CPU thật ≥ 85% |
| `RAM_OVER=2` · `RAM_BUSY_PCT=85` | RAM dùng chung ×2 · ngừng nhận khi RAM thật ≥ 85% |
| `DISK_BUSY_PCT=90` | Ngừng nhận khi ổ ≥ 90% |
| `LIMIT_PCT=95` | Mức RAM tối đa theo cấu hình (trước khi nhân ×RAM_OVER) |
| `MULTICLONE=1` | Nhiều bản clone / máy (thử nghiệm, xem `cloudphone-multiclone.sh`) |

Sửa xong: `cloudphone update`.

---

## Phần 7 — Xử lý sự cố nhanh

| Hiện tượng | Cách xử lý |
|---|---|
| Máy Android 9/10 màn đen | `cloudphone update` (tự bỏ qua trình cài đặt Google bị lỗi) |
| Web báo hết máy / đơn bị hoàn tiền | `python3 ~/phonectl.py capacity` xem RAM / CPU / ổ thật |
| Khách không thấy hình | `cloudphone restart`; vẫn lỗi → `cloudphone logs cpapi` |
| `binder TẮT` | `sudo modprobe binder_linux devices=binder,hwbinder,vndbinder` |
| Chrome văng | `sudo modprobe ashmem_linux` rồi khởi động lại máy đó |
| Ổ cứng sắp đầy | Xoá máy hết hạn; `docker images` → xoá bản Android không dùng (`docker rmi …_root`) |

Gửi kết quả `bash ~/cloudphone-selftest.sh` cho người hỗ trợ khi cần sửa lỗi.
