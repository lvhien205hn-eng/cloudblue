# Cài VPS GPU bằng 1 lệnh — từ máy trắng tới bán tự động

Bản **21.11f** (agent) · web **21.11i** · cần SQL **v41 → v44** (đã chạy hết ngày 21/11/2026).
Hướng dẫn đầy đủ từng nút: `HUONG-DAN.md` (cùng thư mục).

| Bước | Làm ở đâu | Bao lâu làm 1 lần |
|---|---|---|
| 1. Trạm trung chuyển | 1 máy chủ cloud phone — lệnh A | 1 lần (**đã bật trên win7**) |
| 2. Tạo ISO | máy tính Windows có sẵn file ISO Windows gốc — **1 lệnh** | 1 lần (làm lại khi đổi driver / thêm bản Windows) |
| 3. Cài máy | USB / ISO, hoặc `CAI-DAT.cmd` trên máy đang chạy Windows | mỗi máy |
| 4. Công bố agent | web › 💻 Máy PC › **⬆ Công bố bản agent** | mỗi khi có bản mới |
| 5. Bật bán | web › 💻 Máy PC › 🛒 Đơn VPS GPU › **⚙ Cài đặt bán** | 1 lần |

Mọi lệnh: chuột phải nút Start › **Windows PowerShell (Admin)** hoặc **Terminal (Admin)** (thanh tiêu đề có chữ *Administrator*). **Không dùng CMD.** Chỉ dán dòng trong khung.

---

## 1. Trạm trung chuyển — đã xong (win7)

Máy PC cho thuê nằm sau modem nên hình + chuột / phím đi nhờ 1 máy chủ cloud phone. **win7 đã bật** (21/11 15:58), không cần làm lại.
Muốn có trạm dự phòng: trên **1 máy chủ cloud phone khác** (có thư mục `C:\blue`) chạy lệnh A:

```
cd C:\blue; $py = 'C:\Program Files\Python312\python.exe'; if (-not (Test-Path $py)) { $py = 'python' }; curl.exe -sSL -H "Accept: application/vnd.github.raw" -o sua-tat-ca.py "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/sua-tat-ca.py?ref=main"; if (-not (Select-String -Path sua-tat-ca.py -Pattern 'cloudblue-sua-tat-ca' -SimpleMatch -Quiet)) { curl.exe -sSL -o sua-tat-ca.py "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/windows/sua-tat-ca.py" }; if (Select-String -Path sua-tat-ca.py -Pattern 'cloudblue-sua-tat-ca' -SimpleMatch -Quiet) { & $py -u sua-tat-ca.py } else { Write-Host 'Chua tai duoc sua-tat-ca.py tu GitHub - thu lai sau 1 phut' -ForegroundColor Red }
```

Đúng khi khung `== TÓM TẮT ==` có dòng **`trạm máy PC cho thuê: BẬT`**. Không chạy lệnh này trên máy riêng / máy PC cho thuê.

---

## 2. Tạo ISO — 1 lệnh

Trên **máy tính Windows 10 / 11** có sẵn file ISO Windows gốc (vd 22H2, 1511), ổ còn trống khoảng **2,5 lần** tổng dung lượng các ISO.

1. Web › Bảng quản trị › 💻 Máy PC › **🔑 Tạo mã đăng ký** › **Copy mã**.
   Mã chỉ hiện 1 lần. **Không gửi mã cho ai** (kể cả hỗ trợ, kể cả Claude). Đã tạo ISO trên máy này rồi thì bỏ qua bước này: tới câu hỏi mã chỉ cần bấm Enter là dùng lại mã cũ.
2. Mở **Windows PowerShell (Admin)**, dán lệnh dưới (giống hệt nút **📀 Lệnh tạo ISO › Copy lệnh** trên web), Enter:

```
$d = "$env:TEMP\cb-tao-iso.ps1"; Remove-Item $d -Force -ErrorAction SilentlyContinue; curl.exe -fsSL -o $d "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/winpc/tao-iso.ps1?t=$(Get-Random)"; if (-not ((Test-Path $d) -and (Select-String -Path $d -Pattern 'cloudblue-tao-iso' -SimpleMatch -Quiet))) { Write-Host 'Chua tai duoc tao-iso.ps1 - thu lai sau 1 phut' -ForegroundColor Red } else { Set-ExecutionPolicy -Scope Process Bypass -Force; & $d }
```

3. Trả lời lần lượt:
   - **File ISO**: kéo thả từng file `.iso` vào cửa sổ, Enter; hết thì **Enter trống**.
   - **Mã đăng ký**: chuột phải để dán (mã không hiện ra màn hình), Enter. Mã sai / cũ → báo đỏ, cho dán lại ngay.
   - Với từng ISO: bản số mấy (**Enter = Pro**) · **driver riêng** cho bản đó (kéo thả `.exe` / `.zip` / thư mục, Enter từng cái; hết thì Enter trống). Bản 1511: nên kèm driver card mạng + VGA (cách lấy driver: `HUONG-DAN.md` mục D).
   - Bản Windows **mặc định** khi cài từ USB (Enter = bản mới nhất).
4. Chờ 5–40 phút → file **`CloudBlue-PC.iso`** + khung **TÓM TẮT**. Có dòng `(!)` hoặc `CHUA DAT` thì chụp cả khung gửi hỗ trợ.

ISO từ bản 21.11d trở lên **không phải tạo lại** khi có agent / bộ cài mới: máy tự lấy bản mới sau khi lên web (bước 4).
File ISO và USB có chứa mã đăng ký → không đưa cho người ngoài. Lộ mã: bấm **🔑 Tạo mã đăng ký** lần nữa (mã cũ hết dùng ngay) rồi tạo lại ISO.

---

## 3. Cài từng máy (máy sẽ bị xoá sạch)

**Cách A — USB / ISO:** ghi `CloudBlue-PC.iso` ra USB bằng **Rufus** (để nguyên mặc định) hoặc chép vào USB **Ventoy** → cắm vào máy → khởi động từ USB.
Màn hình đen **CloudBlue PC** đếm ngược **30 giây** rồi tự cài. Phím: `Enter` cài ngay · `1`–`9` chọn bản Windows khác · `D` đổi ổ · `A` xoá cả ổ khác · `X` huỷ · `C` dòng lệnh.

**Cách B — máy đang chạy Windows (không cần USB):** bấm đúp file ISO › bấm đúp **`CAI-DAT.cmd`** › chọn bản Windows › chọn mức xoá › gõ `XOA`. Trước lúc gõ `XOA` máy chưa bị đổi gì.

Trong lúc cài:
- Ô **`Ten may:`** — gõ tên không dấu (vd `May-01`), Enter. Ô **`So may:`** — vị trí trong dàn (vd `14-85`), Enter. Bỏ qua: Enter trống (hoặc để 2 phút).
- Vào Desktop lần đầu có **cửa sổ đen 5 bước** (phần mềm quản lý → driver card mạng → chờ mạng → driver VGA → khoá tài khoản khách). **Đừng tắt máy** lúc cửa sổ còn mở; xong máy tự khởi động lại 1 lần.

Khoảng 1 phút sau: web › 💻 Máy PC có máy mới **Chờ duyệt** → bấm **Duyệt** (hoặc bật *Tự duyệt máy mới*).
Kiểm nhanh trên thẻ máy: **● online** · cột Cấu hình **✓ đủ driver** (hiện `⚠ thiếu driver` thì có tên + mã phần cứng để tìm driver) · số máy `№ …` đúng.
Máy thử / máy chưa muốn bán: **Sửa › Trạng thái: Bảo trì** — máy Bảo trì không bao giờ bị giao cho khách.

---

## 4. Công bố bản agent (mỗi khi có bản mới)

Web › 💻 Máy PC › **⬆ Công bố bản agent** › hộp hỏi hiện **bản 21.11f** › OK.
Mọi máy online tự tải, kiểm mã, chạy thử rồi chuyển bản trong khoảng **1 phút**; máy đang tắt cập nhật khi bật lên. Thẻ máy hiện số bản agent mới.
**Bản 21.11f bắt buộc cho tự thu hồi** (máy hết hạn được *khoá* chờ gia hạn thay vì tắt hẳn). Máy cài từ ISO cũ cũng tự lên bản đã công bố ngay sau khi lên web.

---

## 5. Bật bán tự động (1 lần)

Web › 💻 Máy PC › 🛒 Đơn VPS GPU › **⚙ Cài đặt bán**:

| Ô | Chọn |
|---|---|
| Sản phẩm bán tự động | **VPS GPU BLUE** |
| Bản Windows bán | ☑ **22H2** ☑ **1511** |
| Khách tự cài lại / đổi Windows | **2** lần / lượt thuê |
| ♻️ Tự thu hồi máy hết hạn | ☑ **Bật** · Chờ khách gia hạn **30** phút · Tự cài sạch ở mốc **60** phút · Cài sẵn **22H2** · ☑ **Cài sạch xong tự tắt máy** |

› **Lưu**. Ô trạng thái đổi thành **Đang bán tự động**. Bỏ chọn sản phẩm = tắt bán tự động (sản phẩm bán tay như cũ).
Tạm ngừng riêng VPS GPU (không đụng cloud phone): 🛠️ Cài đặt › Bảo trì › **Bảo trì riêng VPS GPU** + lời nhắn cho khách.

---

## Hằng ngày — hệ thống tự chạy

- **Khách mua** (web / app điện thoại / app PC): có máy trống online → giao ngay; máy sạch đúng bản Windows thì dùng được luôn, khác bản thì tự cài 15–30 phút (hạn thuê được cộng 30 phút). Khách tự xem tiến độ (thanh % + đồng hồ), bấm **Báo admin** nếu lâu.
- **Không có máy online** → dải đỏ *đơn VPS GPU đang chờ máy* ở đầu Bảng quản trị + 🔔. **Bật 1 máy lên** (đã duyệt, Sẵn sàng, chưa có khách): trong 1 phút hệ thống tự giao + cài đúng bản khách mua. Muốn chọn máy cụ thể: bấm **Bàn giao** ở đơn đó.
- **Khách hết hạn không gia hạn** (đơn bán tự động):
  1. Máy báo khách 60 giây rồi **khoá** (khởi động lại, dừng ở màn hình đăng nhập; khách không mở điều khiển được nữa).
  2. Khách gia hạn trong **30 phút** → máy tự mở lại sau 1–2 phút, **giữ nguyên dữ liệu**.
  3. Quá 30 phút → lượt thuê **tự kết thúc**, máy về kho, 🔔 báo *đã tự thu hồi*.
  4. Tới phút **60** (máy đang online) → tự **xoá sạch mọi ổ + cài 22H2** — máy đang tắt thì bật lên là tự cài.
  5. Cài xong, máy ổn định 3 phút → **tự tắt**, 🔔 báo *máy mới sẵn sàng*.
  6. Có khách mới → **bật máy lên**: đơn đang chờ tự nhận máy trong 1 phút (hoặc bấm **Bàn giao**) — giao ngay, không phải chờ cài.
  Đang có đơn chờ máy lúc thu hồi → máy giao luôn cho đơn đó (xoá sạch + cài đúng bản khách chọn).
- Máy cho thuê tay (cột Hạn thuê › **⏱ Đặt hạn**, không qua đơn VPS GPU) vẫn như cũ: hết hạn **tự tắt**; cho khách khác thì bật máy › **🧼 Bàn giao**.

---

## Khi có trục trặc

| Thấy | Làm |
|---|---|
| Cài xong 5 phút máy chưa lên web | Tại máy: `Windows + R` › `notepad C:\CloudBluePC\os\status.txt` — xem 2 dòng `Card mang:` và `Driver:` |
| `!! CHUA CO MANG` / `!! CARD MANG CHUA CO DRIVER` lúc cài | thiếu driver card mạng đúng loại → thêm driver khi tạo ISO (`HUONG-DAN.md` mục D) |
| Thẻ máy `⚠ thiếu driver` | tên + mã phần cứng ghi ngay trên thẻ → tìm đúng driver đó |
| Cài lại / cài sạch báo lỗi | 🔔 + thẻ máy ghi lý do; máy cài sạch lỗi thì **không tự tắt** để bạn xem. Bấm **🧹 Cài lại** lần nữa |
| Khách không điều khiển được | máy **● online**? trạm win7 đang chạy? Máy PC › **Sửa** › *Cho điều khiển từ xa* đang bật? Đang bật *Bảo trì riêng VPS GPU*? |
| Đơn chờ máy mãi | phải có máy **Sẵn sàng + online + chưa gán khách**; máy *Bảo trì* không được giao |
| Lộ mã đăng ký | **🔑 Tạo mã đăng ký** lần nữa → tạo lại ISO |

**Không gửi cho ai (kể cả Claude):** mã đăng ký `cbpc_…` · khoá Supabase · lệnh Cloudflare · mật khẩu Windows.
