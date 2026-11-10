# CloudBlue b17 — hướng dẫn từng bước (10/11/2026)

**Gói này THAY gói b16** (đã gồm hết b16: 💎 Tích Blue + nhiệm vụ, ô mã khuyến mãi app/PC, 🛍 Kho app, Root tự bật, tự gỡ "máy ma" win5).
Đã làm b16 dở dang cũng không sao — cứ làm đủ 4 bước dưới đây.

Mới trong b17:
- **🤖 Đổi Android: xoá máy cũ TRƯỚC, tạo máy mới SAU.** Khách bấm Đổi → máy cũ biến mất ngay (không mở / điều khiển được nữa),
  máy chủ xoá sạch máy cũ + dữ liệu xong mới tạo máy mới → khách không bao giờ dùng được 2 máy. Máy mới tạo lỗi → tự tạo lại 3 lần;
  vẫn lỗi → báo admin, admin bấm 🔁 Tạo lại (hạn dùng của khách giữ nguyên).
- **🧹 Ô "Máy đổi Android" trong admin** (ĐT đám mây): bấm **Xoá sạch máy cũ** → xoá máy cũ trên máy chủ (máy ảo + dữ liệu) và ẩn luôn trên web.
- Máy chủ chỉ ghi "đã xoá" khi giả lập xoá thật xong (trước đây xoá lỗi vẫn ghi đã xoá → máy cũ nằm lại trên máy chủ ăn RAM).

Trong gói:
```
CloudBlue-b17/
  HUONG-DAN-b17.md       ← file này
  MD5SUMS.txt
  sql/cloud-phones-v28.sql
  github/                ← 12 file, đúng cây thư mục của repo
    cloudphoned.py
    cpapi.py
    windows/phonectl.py
    blueroblox-site/index.html
    blueroblox-site/play.html
    pc-client/bluepc.py
    android-app/app/src/main/java/shop/blueroblox/app/Api.java
    android-app/app/src/main/java/shop/blueroblox/app/MainActivity.java
    android-app/app/src/main/java/shop/blueroblox/app/ControlActivity.java
    android-app/app/src/main/java/shop/blueroblox/app/SwitchAndroid.java
    android-app/app/src/main/java/shop/blueroblox/app/Blue.java      (mới)
    android-app/app/src/main/java/shop/blueroblox/app/Promo.java     (mới)
```

---

## Bước 1 — Supabase: chạy SQL v28

File: `sql/cloud-phones-v28.sql` (đã gồm v27 — KHÔNG cần chạy v27 riêng; đã chạy v27 rồi thì vẫn chạy v28 bình thường).

1. Mở https://supabase.com/dashboard/project/nprftgodswlpzomcttal/sql/new
2. Mở file `cloud-phones-v28.sql` bằng Notepad → Ctrl+A → Ctrl+C → dán vào ô SQL → bấm **Run**.
3. Kết quả đúng (dòng cuối):

```
v28 xong | 1 | 3 | 11 | 6 | 3 | 1
```

Báo lỗi đỏ → chụp màn hình gửi Claude (cả file là 1 giao dịch: lỗi thì không có gì bị đổi).

## Bước 2 — GitHub: tải 12 file lên

1. Giải nén `CloudBlue-b17.zip` → mở thư mục `CloudBlue-b17\github`.
2. Mở https://github.com/lvhien205hn-eng/cloudblue/upload/main
3. Trong thư mục `github`, bấm Ctrl+A (chọn 6 mục: `android-app`, `blueroblox-site`, `pc-client`, `windows`, `cloudphoned.py`, `cpapi.py`)
   → kéo thả vào trang GitHub → chờ hiện đủ 12 file → bấm **Commit changes**.
4. Mở https://github.com/lvhien205hn-eng/cloudblue/actions → chờ **App Android** và **App PC** hiện dấu ✅ xanh (khoảng 5–10 phút).
   Web cloudblue.vn tự cập nhật sau 1–2 phút.

## Bước 3 — Từng máy chủ: cập nhật 3 file (win5 trước, rồi win3, win4, win1)

Trên máy chủ: bấm Start → gõ `PowerShell` → chuột phải **Windows PowerShell** → **Run as administrator** → chỉ dán dòng trong khung → Enter:

```powershell
[Net.ServicePointManager]::SecurityProtocol='Tls12'; $ErrorActionPreference='Stop'; $py='C:\Program Files\Python312\python.exe'; $R='lvhien205hn-eng/cloudblue'; foreach($f in @(@('cloudphoned.py','cloudphoned.py','def release_switch_waits('),@('cpapi.py','cpapi.py','_DONSACH = {'),@('windows/phonectl.py','phonectl.py','def _kill_named('))){ $dst='C:\blue\'+$f[1]; $tmp=$dst+'.new'; try{ Invoke-WebRequest -UseBasicParsing -Headers @{Accept='application/vnd.github.raw';'User-Agent'='CloudBlue'} -Uri ('https://api.github.com/repos/'+$R+'/contents/'+$f[0]) -OutFile $tmp } catch { Invoke-WebRequest -UseBasicParsing -Uri ('https://raw.githubusercontent.com/'+$R+'/main/'+$f[0]+'?t='+(Get-Random)) -OutFile $tmp }; if(-not (Select-String -Path $tmp -SimpleMatch -Pattern $f[2] -Quiet)){ throw ('GitHub CHUA co ban moi cua '+$f[0]+' - lam Buoc 2 truoc') }; & $py -c "import sys;compile(open(sys.argv[1],encoding='utf-8').read(),sys.argv[1],'exec')" $tmp; if($LASTEXITCODE -ne 0){ throw ('LOI CU PHAP '+$f[0]) }; Move-Item -Force $tmp $dst; 'OK '+$f[1] }; Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'cloudphoned\.py|cpapi\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; 'XONG - bang tu bat lai cloudphoned + cpapi trong ~30 giay'
```

Kết quả đúng: `OK cloudphoned.py` · `OK cpapi.py` · `OK phonectl.py` · `XONG …`
- Báo `GitHub CHUA co ban moi` → Bước 2 chưa xong / GitHub chưa kịp cập nhật → chờ 1 phút rồi dán lại.
- Làm lần lượt win5 → win3 → win4 → win1 (mỗi máy chủ dán đúng dòng trên).

## Bước 4 — Kiểm tra

1. Mở https://cloudblue.vn → bấm **Ctrl+F5**.
2. **Ô dọn máy đổi Android:** đăng nhập admin → tab **ĐT đám mây** → ô **🧹 Máy đổi Android** (ngay trên bảng "📋 Máy khách đang thuê")
   → **🔎 Kiểm tra** xem số máy → bấm **🧹 Xoá sạch máy cũ** → OK.
   Đúng: dòng `Web: … máy cũ cho xoá …` và mỗi máy chủ một dòng `win5: xoá N/N máy cũ`.
   Máy chủ nào báo `⚠ máy chủ chưa cập nhật` → làm Bước 3 cho máy chủ đó rồi bấm lại.
3. **Khách kẹt "Đang tạo" 30 phút (Yumi):** làm xong Bước 3 trên win5, chờ 1–2 phút. Vẫn kẹt → ô 🧹 có dòng
   "Kẹt đang tạo" của khách → bấm **🔁 Tạo lại** (máy chủ còn chỗ tạo lại trong 2–5 phút, hạn khách giữ nguyên).
4. **Thử đổi Android 1 máy thử:** bấm Đổi → máy cũ biến mất ngay, thẻ máy mới ghi "Đang xoá máy cũ…" → vài giây sau
   "Máy cũ đã xoá — đang tạo máy Android …" → 2–5 phút sau "Đang chạy".
5. Phần b16: chip 💎 góc trên web, Công cụ → 🛍 Kho app → cài Termux, 🔓 Root → bật cho Termux → Lưu → Termux gõ `su` rồi `id` ra `uid=0`.

## Ghi chú

- Ô 🧹 có dòng **"Lỗi" (khách đang không có máy)** = máy mới tạo lỗi 3 lần sau khi máy cũ đã xoá → bấm **🔁 Tạo lại**;
  vẫn lỗi thì xem máy chủ (Telegram có báo lý do) hoặc hoàn tiền cho khách.
- Máy chủ mất kết nối lúc khách đổi Android → máy mới tạo ngay ở máy chủ khác, máy cũ bị xoá khi máy chủ đó bật lại.
- Giả lập xoá máy cũ bị lỗi quá 10 phút → web tự ghi máy cũ đã xoá để khách có máy mới, Telegram báo → bấm 🧹 Xoá sạch để dọn máy ảo cũ.
- Lệnh tay trên máy chủ (nếu cần): `& 'C:\Program Files\Python312\python.exe' C:\blue\phonectl.py dondep` (chỉ liệt kê),
  thêm `--xoa` để xoá máy web đã huỷ còn sót.
