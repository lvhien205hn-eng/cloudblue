# BlueRoblox v2 — Hướng dẫn lên bản mới

Bản v2 chia hệ thống làm 4 phần:

| Phần | Làm gì |
|---|---|
| **Web** cloudblue.vn (trước đây blueroblox.shop) | Chỉ còn: đăng ký, nạp tiền, **mua máy (chọn RAM · CPU · Android 9/12/7)**, danh sách máy, gia hạn, nâng cấp, chia sẻ. Không còn màn điều khiển → web nhẹ, load nhanh. |
| **App PC cho khách** (BlueRobloxPC.exe) | Đăng nhập → thấy máy → bấm **Điều khiển** → cửa sổ máy mượt (mở nhiều máy cùng lúc được). |
| **App Android** (cập nhật) | Màn điều khiển dùng trình phát hình gốc của điện thoại (không còn trang web bên trong). |
| **Máy chủ** (bảng BlueRoblox) | Thêm dịch vụ **phát hình app** (bluestream, cổng 8189). Mỗi máy chủ chọn 1 giả lập: **LDPlayer 9 = Android 9**, **MuMu = Android 12 + 7** (hoặc MEmu = Android 7). Đơn khách tự chạy về đúng máy chủ. |

Đường hình mới: cửa sổ giả lập → card NVIDIA nén → **đi thẳng** tới app khách qua cổng 8189 (không qua Cloudflare, không qua trình duyệt).
Mạng khách yếu thì máy chủ tự hạ chất lượng thay vì để hình trễ dần.

---

## Làm theo thứ tự

### Bước 1 — Supabase: chạy SQL v20
Supabase → SQL Editor → dán toàn bộ `cloud-phones-v20.sql` → **Run**. Chạy lại cũng không sao.

### Bước 2 — Web
Tải lên https://github.com/lvhien205hn-eng/cloudblue/upload/main/blueroblox-site : `index.html`, `vercel.json`
(Vercel tự cập nhật sau ~1 phút.)

### Bước 3 — Tải code lên GitHub
| Link tải lên | File |
|---|---|
| https://github.com/lvhien205hn-eng/cloudblue/upload/main | `cloudphoned.py` |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/windows | `bluestream.py`, `phonectl.py`, `panel.py`, `setup.ps1`, `blueserver.py` |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/pc-client | `bluepc.py`, `brstream.py`, `build.bat`, `requirements.txt`, `icon.png` |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/.github/workflows | `pc-client.yml`, `server-exe.yml` |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/android-app/app/src/main/java/shop/blueroblox/app | **đủ 11 file** `.java`: `Api`, `Brand`, `CloneLaunch`, `ControlActivity`, `ExpiryAlarm`, `LoginActivity`, `MainActivity`, `StreamClient`, `StreamView`, `Ui`, `Updater` (file `MainActivity.java` đang có trên GitHub bị thiếu nửa → phải tải đè) |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/android-app/app/src/main | `AndroidManifest.xml` |
| https://github.com/lvhien205hn-eng/cloudblue/upload/main/docs | `STREAM-PROTOCOL.md`, `HUONG-DAN-V2.md` |

Tải **từng thư mục một**, bị lỗi thì F5 rồi tải lại.
Sau khi tải xong, GitHub tự build: app Android (~5 phút, khách tự được báo cập nhật) và app PC (~10 phút, ở Releases → `pc-latest`).
Vào tab **Actions**: *Build Android app* và *Build PC client* phải có dấu ✅ xanh. Dấu ❌ đỏ → bấm vào, chụp phần chữ đỏ gửi hỗ trợ (bản lỗi **không** được đưa cho khách).

### Bước 4 — Máy chủ 1 (LDPlayer): tải bản mới
PowerShell (Admin):
```powershell
$G = "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents"
foreach ($f in "bluestream.py", "phonectl.py", "panel.py", "setup.ps1", "blueserver.py") { curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o "C:\blue\$f" "$G/windows/$f" }
curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o C:\blue\cloudphoned.py "$G/cloudphoned.py"
python -m pip install --quiet windows-capture numpy cryptography
Select-String -Path C:\blue\bluestream.py, C:\blue\panel.py, C:\blue\phonectl.py, C:\blue\cloudphoned.py -Pattern "BRS2|choose_emu|def create_vm|def android_ok" -List
```
Dòng cuối phải in **4 dòng** (mỗi file 1 dòng). Thiếu dòng nào = file đó chưa lên GitHub.

Rồi tắt hẳn bảng cũ + các dịch vụ cũ và mở lại:
```powershell
Get-Process python, pythonw, mediamtx, ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process "C:\Program Files\Python312\pythonw.exe" '"C:\blue\panel.py"' -WorkingDirectory C:\blue
```
- Bảng hỏi **"Máy chủ này chạy giả lập nào?"** → chọn **LDPlayer 9**.
- Bấm **▶ Bật tất cả**. Đèn mới **Phát hình app :8189** phải xanh.
- Tab **phat-hinh** phải có dòng `đường nối: trực tiếp 192.168.1.6:8189, <IP nhà>:8189`.

Modem đã mở cổng **TCP 8189** về 192.168.1.6 (làm hôm trước) — giữ nguyên. Dòng **UDP 8189** (của bản WebRTC cũ) không cần nữa, xoá đi cho gọn.

### Bước 5 — Thử app PC (trước khi đưa khách)
Trên máy tính bất kỳ (hoặc ngay máy chủ):
```powershell
mkdir C:\bluepc -Force | Out-Null
$G = "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents"
foreach ($f in "bluepc.py", "brstream.py") { curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o "C:\bluepc\$f" "$G/pc-client/$f" }
python -m pip install --quiet av pygame-ce numpy
python C:\bluepc\bluepc.py
```
Đăng nhập tài khoản khách → **Điều khiển**. Phím **F3** hiện thông số (khung/giây, Mbps, trễ mạng, "trực tiếp" hay "Cloudflare").
Bản .exe cho khách: GitHub → **Actions** → *Build PC client* xong → web tự có link tải (`/download/BlueRobloxPC.zip`).

### Bước 6 (nên làm) — Đường dự phòng qua Cloudflare
Cho khách ở mạng chặn cổng lạ:
1. Cloudflare → Zero Trust → Networks → Tunnels → đường hầm của máy 1 → **Public Hostname** → **Add**:
   subdomain `stream`, domain `cloudblue.vn`, Type `HTTP`, URL `localhost:8020` → Save.
2. `python C:\blue\doi-ten-mien.py cloudblue.vn` tự ghi `STREAM_WS=wss://stream.cloudblue.vn/v2/stream` vào `cloudphone.conf`.
3. Tắt/bật dịch vụ **phat-hinh** trong bảng.

---

## Thêm máy chủ MuMu (Android 12 + Android 7)

1. Cài **MuMu Player** bản chính thức từ trang MuMu (mumuplayer.com). Không dùng bản sửa / bản tải lại.
   Cài ở ổ / thư mục nào cũng được: bảng + `phonectl.py` tự dò (thư mục mặc định → khoá gỡ cài đặt trong registry →
   MuMu đang mở → thư mục Netease/MuMu ở mọi ổ cứng). Vẫn không thấy → bảng: 🎛 **Chọn giả lập** → 📂 **Chọn thư mục MuMu**.
2. Cài CloudBlue: `setup.ps1 -Node win3 -PubHost phone3.cloudblue.vn` (máy chỉ có MuMu cũng cài được; tự ghi `EMU=mumu`,
   `ANDROIDS=12,7`, `MEMU_MAX_RAM=16`, `MEMU_MAX_CPU=16`), dán khoá, nối Cloudflare.
   Máy chủ cũ đổi sang MuMu: `python C:\blue\phonectl.py setconf EMU=mumu ANDROIDS=12,7 MEMU_MAX_RAM=16 MEMU_MAX_CPU=16`.
3. **Máy mẫu**: trong MuMu Multi-instance tạo 1 máy **Android 12** đặt tên `tpl_a12` và 1 máy **Android 7** tên `tpl_a7`.
   Máy khách được nhân bản từ máy mẫu. Máy mẫu không bao giờ bị xoá.
4. Modem mở cổng **TCP `8188 + số máy`** (win2 → 8190, win3 → 8191) về máy này. `setup.ps1` đã ghi sẵn `STREAM_PORT` đúng số đó.
5. `python C:\blue\phonectl.py probe` → kiểm tra: dòng đầu **Giả lập: MuMu**, "1 máy tối đa 16GB · 16 nhân", máy mẫu **CÓ ✓**.
6. Bấm 🧪 **Tạo máy thử** → mở bằng app PC thử.

**Giới hạn 1 máy theo bản Android** (SQL v22, bảng `cloudphone_pricing.android_limits`):
Android 9 (LDPlayer) 8GB · 8 nhân — Android 12 và Android 7 (MEmu / MuMu) 16GB · 16 nhân. 16GB · 16 nhân là trần tuyệt đối
(web, app PC, app Android đều chặn ở 16; admin đổi trần từng bản ở ô "Trần 1 máy theo bản Android" trong trang quản trị, không vượt 16).
Web / app PC / app Android chỉ hiện các mức trong giới hạn của bản đang chọn. Khách vẫn chỉ thuê được trong phần **còn trống**
của máy chủ (RAM trống − phần chừa cho Windows; tổng nhân ảo ≤ số luồng × `WIN_VCPU_OVER`).
**CPU dùng chung**: `CPU_OVER=1.8` + `WIN_VCPU_OVER=1.8` trong `cloudphone.conf` → máy 72 luồng bán được ~130 nhân ảo
(máy ảo ít khi dùng hết CPU cùng lúc). CPU thật trung bình 5 phút ≥ `CPU_BUSY_PCT` (85%) → tự ngừng nhận máy mới.
Đổi: `python C:\blue\phonectl.py setconf CPU_OVER=1.8 WIN_VCPU_OVER=1.8` rồi bật lại phần nhận đơn (cloudphoned).
Đổi giới hạn 1 bản (không vượt 16): ô "Trần 1 máy theo bản Android" trong trang quản trị, hoặc SQL
`update cloudphone_pricing set android_limits = android_limits || '{"7": {"ram": 12, "cpu": 8}}' where id = 1;`

**Ảnh nền máy khách**: `windows/wallpaper.png`. Đổi ảnh → máy mới nhận ảnh mới; máy cũ còn ảnh nền cũ của mình được chép
sẵn ảnh mới (không khởi động lại, hiện từ lần bật máy sau); máy khách đã tự đổi ảnh nền thì giữ nguyên. Tắt tự đổi: `WALLPAPER_UPDATE=0`.

MEmu cũng được (chọn **MEmu** trong bảng): Android 7 tạo sẵn; Android 12 cần máy mẫu `tpl_a12`.

---

## Tên miền cloudblue.vn (05/11/2026)
`blueroblox.shop` bị nơi bán khoá (`clientHold`) chiều 04/11 → chuyển web sang **cloudblue.vn** (Tenten → nameserver Cloudflare → Vercel).
Những chỗ phụ thuộc tên miền và đã đổi:

| Chỗ | Tên miền mới |
|---|---|
| Vercel → Domains | `cloudblue.vn` (chính), `www.cloudblue.vn` chuyển về đó. Bản ghi A `@` + CNAME `www` ở Cloudflare để **mây xám** |
| Đường hầm Cloudflare (máy 1) | `phone.cloudblue.vn` → `http://localhost:8010`, `stream.cloudblue.vn` → `http://localhost:8020` (máy 2: `phone2` / `stream2`) |
| `cloudphone.conf` | `python C:\blue\doi-ten-mien.py cloudblue.vn` (máy 2: thêm `phone2`) — tự sửa PUBLIC_BASE, STREAM_WS, CPAPI_ORIGINS, NOTIFY_URL + link máy khách cũ |
| Supabase | Auth → URL Configuration (Site URL + Redirect URLs) · SQL Editor chạy `doi-ten-mien-cloudblue.sql` (settings.data.web + đổi địa chỉ Database Webhooks) |
| SePay webhook | `https://cloudblue.vn/api/sepay-webhook` |
| Bot Telegram | `setWebhook?url=https://cloudblue.vn/api/telegram&secret_token=…` |
| Vercel env | `SITE_URL=https://cloudblue.vn` (nếu có biến này) |

- App PC + app Android (từ v1.37) đọc tên miền web ở Supabase `settings.data.web` → lần sau đổi tên miền chỉ cần sửa dòng đó, không phải cập nhật app.
  App Android tự cập nhật: web hỏng thì lấy `app.json` + APK thẳng trên GitHub.
- Đường điều khiển chính (IP:8189) không phụ thuộc tên miền; tên miền chỉ cho web, nút công cụ dự phòng, báo Telegram.
- `vercel.json`: khi `blueroblox.shop` mở lại sẽ tự chuyển sang `cloudblue.vn` (trừ `/api/…` để webhook cũ vẫn chạy).

## App máy chủ dạng .exe (không cần cài Python) — tuỳ chọn
GitHub → Actions → **Build server exe** → Run workflow → tải `BlueRobloxServer.zip` ở Artifacts (chỉ admin).
Giải nén vào `C:\blue\BlueRobloxServer\` → chạy `BlueRobloxServer.exe` (các file .py vẫn ở `C:\blue`, sửa .py không cần build lại).

## Lỗi hay gặp
| Hiện tượng | Cách sửa |
|---|---|
| App báo "Máy chủ chưa mở đường phát hình" | Chưa chạy SQL v20, hoặc dịch vụ phat-hinh chưa chạy (đèn Phát hình app đỏ) |
| App chỉ nối được "Cloudflare", không "trực tiếp" | Modem chưa mở cổng TCP 8189 về máy chủ |
| Đen màn, tab phat-hinh báo "Không lấy được hình từ cửa sổ máy" | Cửa sổ giả lập bị thu nhỏ — bấm 🙈 Ẩn cửa sổ giả lập (ẩn đúng cách, không thu nhỏ) |
| Chạm không ăn, tab phat-hinh báo "scrcpy lỗi → dùng lệnh input" | Vẫn dùng được (chậm hơn); gửi dòng lỗi cho hỗ trợ |
| Đơn Android 12/7 hoàn tiền "không máy chủ nào nhận" | Chưa có máy chủ MuMu đang chạy |

---

## Điều khiển trên trình duyệt — iPhone / iPad / Mac (05/11/2026)

Khách không có app (iPhone, iPad, Mac, máy tính chưa cài) mở máy ngay trên trình duyệt: **cloudblue.vn/play.html**.
* Web: trên iPhone/iPad/Mac nút ở từng máy là **▶ Mở máy** (vào thẳng `/play.html?id=<mã máy>`); máy khác vẫn "Mở trong app" và có thêm mục "Mở ngay trên trình duyệt".
* `play.html` tự lo: đăng nhập (cùng tài khoản web) → danh sách máy → điều khiển. iPhone: Chia sẻ → **Thêm vào MH chính** → mở như app (toàn màn hình, `play.webmanifest`).
* Cùng giao thức BRS2 với app (client `"web"`), đi đường **WebSocket qua Cloudflare** (`STREAM_WS`, VD `wss://stream2.cloudblue.vn/v2/stream`) — trình duyệt không đi được đường thẳng TLS 8189/8190 (chứng chỉ tự ký).
  Máy chủ không phải sửa gì, chỉ cần đường hầm có `stream…` → `localhost:8020`.
* Giải mã H.264 bằng **WebCodecs**: iPhone/iPad cần **iOS 16.4+**; máy tính dùng Chrome / Edge / Safari mới.
* Có: chạm nhiều ngón, vuốt, cuộn chuột, gõ phím (cả bàn phím iPhone, gõ tiếng Việt), dán chữ, Back/Home/Đa nhiệm, âm lượng, xoay, nút nguồn,
  chất lượng hình (Tự động/Tiết kiệm/Cân bằng/Nét), thông số, cài APK (file / link), khởi động lại máy, tự nối lại khi mất mạng, giữ màn hình sáng.
* Mở máy ở nơi khác → trình duyệt báo "Máy đang được mở ở nơi khác" (bấm **Mở lại ở đây** để giành lại).

## Máy chủ MEmu bán Android 7 + 12

`python C:\blue\phonectl.py setconf EMU=memu ANDROIDS=7,12 MEMU_MAX_RAM=16 MEMU_MAX_CPU=16` + trong Multi-MEmu tạo 1 máy **Android 12** tên `tpl_a12` (để tắt).
Android 7 MEmu tạo sẵn được; Android 12 nhân bản từ `tpl_a12`. Máy chủ chỉ báo lên web bản Android **tạo được thật**
(`phonectl.py engine`: chưa có `tpl_a12` → không bán Android 12 ở máy chủ này). Tạo máy mẫu xong: bảng ■ Tắt tất cả → ▶ Bật tất cả.
Mỗi máy chủ chỉ nhận đơn đúng `ANDROIDS` của nó (máy 1 LDPlayer = 9; máy 2 MEmu = 7, 12).
