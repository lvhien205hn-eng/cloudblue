# Hướng dẫn thêm MÁY CHỦ mới (máy 2, 3, 4…) cho BlueRoblox Cloud Phone

Giả lập dùng: **LDPlayer 9** (Android 9 · tối đa **8 nhân / 8GB** mỗi máy ảo · tạo máy ~1 phút). Tool vẫn chạy được MEmu nếu máy chỉ có MEmu.

Mỗi máy Windows là **một máy chủ độc lập**: tự chạy máy ảo LDPlayer của khách, tự nối internet qua đường hầm Cloudflare riêng.
Các máy **không nối với nhau** — cùng đọc đơn hàng trên Supabase. Có đơn mới: **máy nào còn trống nhiều nhất nhận**;
máy đầy thì nhường máy khác; tất cả đầy thì web báo hết chỗ. Máy khách đã tạo nằm yên ở máy đã tạo ra nó.

| Máy | NODE | Tên miền | Đường hầm Cloudflare |
|---|---|---|---|
| Máy 1 (máy chính) | `win1` | `phone.blueroblox.shop` | `phone` |
| Máy 2 | `win2` | `phone2.blueroblox.shop` | `phone2` |
| Máy 3 | `win3` | `phone3.blueroblox.shop` | `phone3` |
| Máy 4 | `win4` | `phone4.blueroblox.shop` | `phone4` |

> ⚠️ Không gửi khoá Supabase / mã Cloudflare (`eyJ…`) vào chat hay lên GitHub — chỉ dán vào bảng BlueRoblox trên máy.

---

## Bước 0 — Chuẩn bị máy mới
1. Bật **ảo hoá (VT-x / Intel Virtualization)** trong BIOS.
2. Cài **LDPlayer 9** bản chính thức từ **ldplayer.net** (để thư mục mặc định `C:\LDPlayer\LDPlayer9`). Mở 1 lần cho nó tạo máy số 0 rồi tắt.
   KHÔNG cài chung MEmu trên cùng máy (2 giả lập tranh ảo hoá → lag/lỗi).
   Không cần chỉnh gì trong Settings của LDPlayer — tool tự bật ADB, Root, 60 FPS, tắt âm thanh, cấu hình từng máy.
3. **Cắm dây mạng (LAN)**, không dùng wifi. **Không cần** vào router 192.168.1.1, không cần mở cổng.

## Bước 1 — Tạo đường hầm Cloudflare (trên trình duyệt)
1. Vào https://one.dash.cloudflare.com/ → **Networks → Tunnels** → **Create a tunnel** → **Cloudflared**.
2. Đặt tên theo bảng trên (máy 2: `phone2`) → **Save tunnel**.
3. Chọn **Windows** → bấm nút **copy** ở dòng `cloudflared.exe service install eyJ…` → giữ lại (dán ở Bước 3).
   Không cần tải file .msi hay mở Command Prompt như trang hướng dẫn — tool tự cài.
4. **Next** → **Public Hostname**: Subdomain `phone2` · Domain `blueroblox.shop` · Type **HTTP** · URL `localhost:8010` → **Save**.
   (URL luôn là `localhost:8010`, KHÔNG ghi IP.)
5. Đường hầm cũ `phone` của máy 1: **không sửa**.

## Bước 2 — Cài tool trên máy mới
Bấm chuột phải nút **Start** → **Windows PowerShell (Admin)** (dấu nhắc phải có chữ **PS** — nếu là `C:\Windows\system32>` thì gõ `powershell` rồi Enter).
Dán lệnh (máy 2 — máy 3/4 đổi `win2`/`phone2` thành `win3`/`phone3`, `win4`/`phone4`):

```
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; New-Item -ItemType Directory -Force C:\blue | Out-Null; Invoke-WebRequest -UseBasicParsing -UserAgent "BlueRoblox" -Headers @{Accept = "application/vnd.github.raw"} -Uri "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/setup.ps1" -OutFile C:\blue\setup.ps1; Set-ExecutionPolicy -Scope Process Bypass -Force; & C:\blue\setup.ps1 -Node win2 -PubHost phone2.blueroblox.shop
```

Mất 10–15 phút. Tự cài: curl (nếu Windows cũ chưa có), Python 3.12, Node.js, adb, cloudflared, trình phát hình ws-scrcpy, toàn bộ tool BlueRoblox,
file cài đặt `C:\blue\cloudphone.conf` đã tối ưu sẵn. Dòng cuối phải hiện `NODE_ID=win2  PUBLIC_BASE=https://phone2.blueroblox.shop`.

## Bước 3 — Mở bảng BlueRoblox (biểu tượng trên Desktop máy mới) và bấm lần lượt
1. **②** Khoá Supabase — lấy tại https://supabase.com/dashboard/project/nprftgodswlpzomcttal/settings/api-keys
   → khoá **service_role / secret** (`eyJ…` hoặc `sb_secret_…`) → Reveal → Copy → dán. (Cùng khoá với máy 1.)
2. **③** Dán lệnh Cloudflare `eyJ…` đã copy ở Bước 1 → trang Cloudflare đổi thành **Connected**.
3. **🔑** Tự đăng nhập + tự chạy (nhập mật khẩu Windows vào hộp thoại — chỉ lưu trong máy).
4. **🚀** Tự động A→Z → chờ đủ đèn xanh.

## Bước 4 — Kiểm tra
- Web → **Bảng quản trị → Máy chủ**: thấy máy mới (`win2`…) đang chạy.
- Trên máy mới: `& "C:\Program Files\Python312\python.exe" C:\blue\kiemtra.py` → không có MÁY THỪA / MẤT MÁY THẬT.

---

## Cài đặt sẵn trên mỗi máy (trong `C:\blue\cloudphone.conf`)
| Dòng | Ý nghĩa |
|---|---|
| `MEMU_MAX_RAM=8` `MEMU_MAX_CPU=8` | Giới hạn mỗi máy ảo (LDPlayer 9: 8GB / 8 nhân; gói lớn hơn vẫn nhận, chạy ở mức tối đa) |
| `LD_FPS=60` (mặc định) | FPS của LDPlayer (chung mọi máy) — 60 cho kéo/lướt mượt |
| `EMU=ld` / `EMU=memu` | Ép dùng giả lập nào (bỏ trống = tự nhận: có LDPlayer thì dùng LDPlayer) |
| `MEMU_RENDER=1` | (chỉ MEmu) DirectX — mượt. OpenGL `0` làm máy vẽ chậm — đừng đổi |
| `WIN_VCPU_OVER=1` | Tổng nhân ảo ≤ số luồng thật (lag thì đổi `0.9` = chừa 10%) |
| `WIN_RAM_RESERVE=3` `RAM_BUSY_PCT=98` | Nhận máy tới khi RAM thật gần đầy, chừa 3GB cho Windows |
| `POOL_SIZE=1` | Giữ sẵn 1 máy dựng trước (đang tắt) → khách mua có máy ~1 phút |
| `NODE_ID` `PUBLIC_BASE` `PRIMARY` | Tên máy chủ / tên miền / máy chính (chỉ máy 1 là `PRIMARY=1`) |

Sửa conf xong → khởi động lại phần nhận đơn:
```
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run.py cloudphoned.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## Lệnh hay dùng (chạy trên máy chủ cần làm, PowerShell Admin, trong `C:\blue`)
| Việc | Lệnh |
|---|---|
| Xem máy (MEmu ↔ danh sách ↔ web, tổng nhân) | `& "C:\Program Files\Python312\python.exe" kiemtra.py` |
| Tối ưu lại mọi máy đang chạy | `& "C:\Program Files\Python312\python.exe" phonectl.py tuneall` |
| Xoá máy thừa (không thuộc khách) | `& "C:\Program Files\Python312\python.exe" phonectl.py cleanup` |
| Làm mới máy khách bị mất máy thật | `& "C:\Program Files\Python312\python.exe" run.py remake.py list` rồi `… remake.py all` |
| Dọn đơn kẹt trên web (chỉ xem / làm thật) | `… donweb.py` / `… donweb.py --yes` |
| Đổi chế độ hình 1 máy (chỉ MEmu) | `… phonectl.py render TÊN_MÁY directx` |
| Danh sách máy trong giả lập | `… phonectl.py vmlist` |

Mỗi máy chủ chỉ làm mới / dọn **máy của chính nó** — không đụng máy chủ khác.

## Cập nhật tool (sau khi tải file mới lên GitHub)
Chạy trên **từng** máy chủ:
```
foreach ($f in "phonectl.py","panel.py","remake.py","donweb.py","kiemtra.py","setup.ps1","suachua.ps1") { curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o "C:\blue\$f" "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/$f" }
foreach ($f in "cloudphoned.py","cpapi.py") { curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o "C:\blue\$f" "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/$f" }
Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run.py cloudphoned.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
Không cập nhật khi đang có máy "Đang tạo…".

## Cổng adb
- LDPlayer: máy số N ⇄ `127.0.0.1:5555 + 2·N` (máy 1 = 5557, máy 2 = 5559…). Máy số 0 (`LDPlayer`) là máy gốc — tool giữ lại, không xoá.
- MEmu: máy số N ⇄ `127.0.0.1:21503 + 10·N`.

## Chất lượng hình (cpapi)
| Chế độ | LDPlayer | MEmu |
|---|---|---|
| Tiết kiệm | 720 · 1,5 Mbps · 30 FPS | 720 · ≤1,2 Mbps · 24 FPS |
| Ít trễ (mặc định) | 720 · 2,5 Mbps · 40 FPS | 720 · 1,8 Mbps · 30 FPS |
| Siêu nét | 1280 · 4 Mbps · 45 FPS | 1280 · 4 Mbps · 30 FPS |
Đặt cao hơn (60 FPS / 3,5 Mbps) → bộ nén nghẽn → hình đứng vài giây. Thử web thì đừng xem qua Chrome Remote Desktop (nén 2 lần → giựt).

## Lưu ý
- **Không tắt máy chủ đang có khách** — khách ở máy đó mất máy tới khi bật lại (bật lại tự đăng nhập → tự bật máy khách, 10–20 phút).
- Các máy cùng 1 đường mạng **chia nhau upload** (hiện 30 Mbps ≈ 15–20 khách xem cùng lúc). Đông khách → nâng gói mạng / đặt máy ở mạng khác.
- App điện thoại hiện lấy ảnh màn hình nhỏ từ máy 1 → máy ảo ở máy 2+ không có ảnh nhỏ trong app (vẫn điều khiển được). Cần build lại app để sửa.

## Lỗi thường gặp
| Báo | Cách xử lý |
|---|---|
| `'New-Item' is not recognized` | Đang ở cmd → gõ `powershell` rồi dán lại |
| `curl.exe is not recognized` | Windows cũ → dùng đúng lệnh `Invoke-WebRequest` ở Bước 2 (setup tự cài curl) |
| Đèn `phoneN.blueroblox.shop` đỏ, `curl` báo `Could not resolve host` | DNS modem nhớ kết quả cũ → setup đã tự đặt DNS 1.1.1.1/8.8.8.8; chạy lại: `Get-NetAdapter \| Where-Object Status -eq Up \| ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ("1.1.1.1","8.8.8.8","2606:4700:4700::1111","2001:4860:4860::8888") }; ipconfig /flushdns` |
| Cloudflare: đường hầm Healthy nhưng **Routes = 0** | Tunnel → **+ Add route** → Published application → `phoneN` · `blueroblox.shop` · Service URL **`http://localhost:8010`** |
| `Khong thay gia lap` | Cài LDPlayer 9 trước rồi chạy lại lệnh Bước 2 |
| adb `offline` với máy LDPlayer | Tool tự bật ADB khi bật máy; máy tạo tay trong LDPlayer → Settings → Other → ADB debugging = Open local connection |
| Bảng vẫn ghi "MEmu" / đèn đỏ sau cập nhật | ⏻ Thoát hẳn → mở lại biểu tượng BlueRoblox → 🚀 |
| Máy khách "Đang tạo…" mãi | Web → Bảng quản trị → Máy chủ → máy đó có đang **Ngừng nhận máy** không |
| MEmu `connect console failed` / máy không tạo được | Khởi động lại Windows |
| Lag cả máy | `kiemtra.py` xem tổng nhân (> số luồng = quá tải) · máy thừa → `cleanup` · chế độ hình phải DirectX |

---

## Hình kiểu Parsec (WebRTC) — mượt, ít trễ

Bảng BlueRoblox có thêm dịch vụ **phat-hinh**. Lần đầu bật, nó tự tải FFmpeg 6.1 và MediaMTX (khoảng 2 phút) rồi tự mở tường lửa.
Khi khách mở máy trên web hoặc app, hình được quay thẳng từ cửa sổ LDPlayer, nén bằng card NVIDIA và gửi qua UDP. Nếu không nối được, nó tự quay về hình cũ.

**Bắt buộc: mở cổng trên modem/router (192.168.1.1) → NAT / Port Forwarding / Virtual Server**

| Máy chủ | Cổng ngoài | Cổng trong | Giao thức | IP trong |
|---|---|---|---|---|
| Máy 1 | 8189 | 8189 | UDP **và** TCP (hoặc "Both") | 192.168.1.6 |
| Máy 2 | 8190 | 8190 | UDP và TCP | IP máy 2 |
| Máy 3 | 8191 | 8191 | UDP và TCP | IP máy 3 |

Từ máy 2 trở đi phải thêm dòng `RTC_UDP_PORT=8190` (máy 3 đặt 8191…) vào `C:\blue\cloudphone.conf`, rồi bấm Tắt rồi Bật dịch vụ phat-hinh trong bảng.

**Cài đặt thêm trong cloudphone.conf (không bắt buộc)**

| Dòng | Ý nghĩa |
|---|---|
| `RTC=0` | Tắt hình kiểu mới, dùng hình cũ |
| `RTC_FPS=60` | Số khung hình mỗi giây |
| `RTC_MBPS=4` | Băng thông mỗi máy (đặt 3 nếu mạng nhà upload yếu) |
| `RTC_CPU=1` | Nén bằng CPU thay vì card |
| `RTC_PUBLIC_IP=` | IP mạng nhà; để trống thì tự dò |

**Kiểm tra**
- Nhật ký từng máy nằm ở `C:\blue\rtc\log\<tên máy>.txt`. Dòng "gửi 60 khung/giây · cửa sổ vẽ 60/giây" là tốt.
- Xem hình cũ để so sánh: thêm `&cprtc=0` vào cuối địa chỉ trang điều khiển.
