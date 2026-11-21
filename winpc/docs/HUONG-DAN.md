# CloudBlue PC — máy PC cho thuê tự cài, tự lên web (đợt 1 · bản 21.11b)

Bộ này thay việc "cài Windows tay rồi cài phần mềm điều khiển gửi khách":

1. **1 file ISO** (gộp các bản Windows bạn có, ví dụ 22H2 + 1511). Khởi động máy từ ISO / USB đó → máy **tự chọn ổ, đếm ngược 30 giây, xoá dữ liệu cũ, cài Windows, nạp driver bạn kèm theo, đặt ảnh nền CloudBlue**, không hỏi gì thêm.
2. Windows lên là **tự hiện trong Bảng quản trị › 💻 Máy PC** (tên máy, cấu hình, IP, online / offline). Cài xong, màn hình bộ cài hiện **1 ô gõ SỐ MÁY** (vị trí máy trong dàn) — số này hiện trên web và trên màn hình máy để khách báo lỗi đúng máy.
3. Trên web bấm **🧹 Cài lại** / **🧼 Bàn giao**: chọn bản Windows (22H2 / 1511) + mức xoá → máy tự khởi động lại, tự dọn sạch và cài lại, **không cần USB, không cần ra máy**.
4. Đặt **hạn thuê** cho từng máy: từ **2 ngày trước hạn** máy tự nhắc khách liên tục và **đầu Bảng quản trị luôn hiện dải báo** máy sắp hết hạn; hết hạn mà chưa gia hạn thì máy **tự tắt** (bật lại cũng tự tắt). Việc lạ trên máy hiện ở tab 🛡️ Bảo mật; gửi thêm về mail / Telegram là tuỳ chọn (mục C4)

> **Chưa có ở đợt này:** điều khiển máy bằng app PC / app điện thoại CloudBlue và bán tự động (khách mua → tự giao máy). Đó là đợt 2.

> **Đã cài thật trên máy ảo (bản 22H2, ngày 21/11).** Bản 1511 của shop là **bản kiểu ghost** (có sẵn tài khoản + tên máy) — từ bản 21.11b bộ cài tự xử lý kiểu này (mục E). Bản 1511 và driver riêng (card mạng, VGA) chỉ thử trọn được trên **máy thật** — hãy thử trên **1 máy thật** trước khi dùng cho cả dàn.

---

## A. Làm 1 lần

### A1. Thêm phần Máy PC vào cơ sở dữ liệu
Supabase › SQL Editor › New query › dán **toàn bộ** file `cloud-pc-v41.sql` › Run. Dòng cuối phải ra: `v41 xong | t | t | t | t`.
Rồi làm y như vậy với file **`cloud-pc-v42.sql`** (hạn thuê + nhắc hết hạn). Dòng cuối phải ra: `v42 xong | t | t | t | t | t`.
Chạy lại nhiều lần không sao; 2 file này chỉ **thêm** bảng / cột / hàm `pc_…`, không đụng phần đang có. Chưa chạy v42 thì web vẫn dùng được, chỉ thiếu phần hạn thuê.

### A2. Tạo mã đăng ký
Web › Bảng quản trị › **💻 Máy PC** › **🔑 Tạo mã đăng ký** › **Copy mã**.

- Mã chỉ hiện **1 lần**. Hệ thống chỉ giữ bản băm, không xem lại được.
- **Không gửi mã này cho ai** (kể cả hỗ trợ). Ai có mã là đăng ký được máy vào kho của bạn.
- Lộ mã → bấm **Tạo mã đăng ký** lần nữa (mã cũ hết dùng ngay) rồi tạo lại ISO.

### A3. Tạo file ISO
Trên **máy tính Windows 10 / 11 đang có các file ISO Windows gốc** (ổ còn trống khoảng 2,5 lần tổng dung lượng ISO):

1. Web › Máy PC › **📀 Lệnh tạo ISO** › **Copy lệnh**.
2. Chuột phải nút Start › **Windows PowerShell (Admin)** hoặc **Terminal (Admin)** — *không dùng CMD*.
3. Dán lệnh, Enter. Script sẽ hỏi lần lượt:
   - đường dẫn từng file ISO (kéo thả file vào cửa sổ rồi Enter; xong thì Enter trống) — **chỉ file `.iso`**, driver hỏi sau;
   - **mã đăng ký** (chuột phải để dán; mã không hiện ra màn hình). Từ lần chạy thứ 2 trên cùng máy: **bấm Enter là dùng lại mã lần trước**.
     Script **hỏi máy chủ ngay** xem mã còn hiệu lực không: mã cũ (trên web đã bấm "Tạo mã đăng ký" lần nữa) thì báo đỏ và cho dán mã mới luôn — khỏi mất công tạo ISO rồi cài xong máy không lên web;
   - với **từng ISO**: nếu ISO có nhiều phiên bản (Home, Pro…) thì dùng bản số mấy (Enter = bản Pro); rồi **driver riêng cho bản Windows đó** —
     kéo thả file driver (`.exe`, `.zip`) hoặc thư mục driver vào cửa sổ rồi Enter, từng cái một; bản không cần driver / đã kéo hết thì **Enter trống** (xem mục D);
   - bản Windows **mặc định** khi cài từ USB (Enter = bản mới nhất; gõ số để chọn 1511).
4. Chờ 5–40 phút tuỳ máy. Cuối cùng hiện khung **TÓM TẮT** và file `CloudBlue-PC.iso`.

Script chỉ **đọc** ISO gốc và tạo thư mục làm việc + file ISO mới; không sửa ISO gốc, không đụng ổ đĩa của máy đang chạy.
Chép cả khung TÓM TẮT gửi hỗ trợ nếu có dòng `(!)` hoặc `CHUA DAT`.

Tuỳ chọn (thêm vào cuối lệnh `& $d`):

| Tham số | Ý nghĩa |
|---|---|
| `-TaiKhoan Khach -MatKhau "abc123"` | tài khoản Windows tạo sẵn cho khách (mặc định `PC`, không mật khẩu, tự đăng nhập). Là **tài khoản thường** — xem mục F |
| `-KhachAdmin` | để tài khoản khách có quyền Admin (khách tự cài được mọi phần mềm, nhưng cũng phá được phần mềm quản lý trên máy đó) |
| `-Out D:\CloudBlue-PC.iso -Work D:\cb-work` | nơi ghi ISO / thư mục làm việc (không có dấu cách) |
| `-Them D:\cb-them` | thư mục thêm: driver chung, lệnh chạy lần đầu, ảnh nền riêng (xem mục D) |
| `-Driver "2=D:\drv\lan.zip","2=D:\drv\vga.exe"` | driver riêng cho bản Windows của **ISO thứ 2** mà không cần kéo thả (số = thứ tự ISO) |
| `-KhongHoi` | không hỏi gì: mọi lựa chọn lấy mặc định, mã đăng ký lấy của lần chạy trước (dùng khi chạy tự động) |
| `-KhongKhoaChung` | không điền khoá cài đặt chung (xem mục E) |
| `-KhongKiemMa` | không hỏi máy chủ về mã đăng ký (dùng khi máy tạo ISO không ra được mạng tới Supabase) |

---

## B. Thử lần đầu (bắt buộc) — trên máy thử hoặc máy ảo

**Máy đó sẽ bị xoá sạch.**

- *Máy ảo* (VMware / VirtualBox / Hyper-V): tạo máy 64-bit, ổ ảo **≥ 100GB** (ổ nhỏ quá sẽ không tạo phân vùng cứu hộ — xem mục E), RAM ≥ 4GB, mạng NAT, gắn `CloudBlue-PC.iso` làm ổ CD, bật máy.
- *Máy thật*: ghi ISO ra USB bằng **Rufus** (để nguyên mọi lựa chọn mặc định, đừng tích các ô "tuỳ biến Windows") hoặc chép ISO vào USB **Ventoy**; cắm vào máy thử, khởi động từ USB.

Điều sẽ thấy:

1. Màn hình đen chữ trắng **CloudBlue PC**: danh sách ổ cứng, ổ sẽ bị xoá, bản Windows sẽ cài, **đếm ngược 30 giây**.
   Phím: `Enter` = cài ngay bản mặc định · `1`–`9` = chọn bản Windows khác (ví dụ 1511) · `D` = đổi ổ đích · `A` = bật / tắt xoá cả các ổ khác · `X` = huỷ, chuyển sang bộ cài Windows thường · `C` = mở dòng lệnh. Bấm phím khác `Enter` thì đếm ngược dừng lại, khi đó phải bấm `Enter` mới cài.
2. Tự chia ổ → bung Windows (5–20 phút) → khởi động lại 1–2 lần → vào thẳng màn hình Desktop.
3. Vào Desktop lần đầu sẽ có **cửa sổ đen "CloudBlue PC - dang hoan tat cai dat"** in tiến độ 5 bước:
   `[1/5]` phần mềm quản lý · `[2/5]` lệnh riêng của bạn (`firstboot.d`) · `[3/5]` **chờ máy có mạng** (driver card mạng) · `[4/5]` **driver VGA NVIDIA** (chỉ cài sau khi đã có mạng) · `[5/5]` khoá tài khoản khách.
   Xong máy **tự khởi động lại 1 lần** (bước khoá bảo mật, mục F). **Đừng tắt máy lúc cửa sổ này còn mở.**
   Dòng `!! CHUA CO MANG` = máy chưa ra được mạng (dây mạng / driver card mạng) — máy sẽ chưa hiện trên web cho tới khi có mạng; driver VGA sẽ tự cài sau khi có mạng.
4. Khoảng 1 phút sau: máy hiện ở web › Máy PC, trạng thái **Chờ duyệt** → bấm **Duyệt**.

Sau đó thử tiếp trên web: **🧹 Cài lại** → chọn bản kia (ví dụ 1511) → máy tự khởi động lại, cài xong lại hiện online với đúng tên cũ.

**Thử xong hãy gửi lại:** khung TÓM TẮT lúc tạo ISO + 1 ảnh màn hình đếm ngược + kết quả (lên web hay không, cài lại được không). Nếu màn hình dừng ở dòng đỏ `!!` thì chụp nguyên màn hình đó.

---

## C. Dùng hằng ngày

### C1. Cài 1 máy mới
- **Bằng USB / ISO**: khởi động từ USB như mục B.
- **Máy đang chạy Windows sẵn (không cần USB)**: mở file ISO (bấm đúp) › bấm đúp **`CAI-DAT.cmd`** › chọn bản Windows › chọn mức xoá › gõ `XOA` › máy tự khởi động lại và cài. Trước lúc gõ `XOA` máy chưa bị đổi gì.

### C2. Trên web (Bảng quản trị › 💻 Máy PC)
| Nút | Việc |
|---|---|
| **Duyệt** | nhận máy mới vào kho (bật "Tự duyệt máy mới" nếu không muốn bấm từng máy) |
| **Sửa** | tên hiển thị, mã riêng của shop, ghi chú, trạng thái (Sẵn sàng / Đang cho thuê / Bảo trì) · Khởi động lại · Tắt máy · Xoá khỏi danh sách |
| **🧹 Cài lại** | chọn bản Windows + mức xoá, máy tự làm trong 15–30 phút |
| **🧼 Bàn giao** | khách cũ trả máy: xoá sạch MỌI ổ cứng + cài Windows mới cho khách mới; hạn thuê + tên khách cũ cũng được xoá |
| **⏱ Đặt hạn / Gia hạn** (cột Hạn thuê) | đặt, gia hạn, bỏ hạn thuê của máy + ghi tên khách (mục C4) |
| **🔔 Cảnh báo** | bật / tắt gửi mail, số phút báo trước, **Gửi thư thử** (mục C4) |
| **Huỷ lệnh** | gỡ lệnh chưa chạy. Máy đã nhận lệnh và đang cài thì vẫn cài tiếp |
| **⬆ Công bố bản agent** | khi có bản phần mềm mới trên GitHub: mọi máy tự cập nhật trong khoảng 1 phút |

Mức xoá khi cài lại:

- **Dọn sạch cả máy** — xoá mọi ổ cứng gắn trong (dùng khi khách cũ trả máy).
- **Cả ổ hệ thống** — xoá ổ chứa Windows, giữ các ổ cứng khác.
- **Chỉ phân vùng Windows** — chỉ cài lại ổ C:, giữ các phân vùng / ổ khác (đổi bản Windows cho khách đang thuê).

Máy offline lúc ra lệnh: lệnh chờ, máy online lại là chạy.

### C2b. Số máy
Mỗi máy có 1 **số máy** (vị trí trong dàn: `14-85`, `A07`, `KHU B 3`…) để bạn và khách cùng gọi đúng 1 máy khi có lỗi.

- **Lúc cài bằng USB / ISO**: Windows bung xong, màn hình bộ cài hiện ô `So may:` — gõ số rồi Enter. Bỏ qua thì bấm Enter trống, hoặc để 2 phút máy tự đi tiếp.
- **Trên web**: nút **Sửa** của máy › ô **Số máy** (đặt mới / sửa / xoá). Bảng hiện nhãn `№ 14-85` cạnh tên máy; ô tìm kiếm tìm được theo số máy.
- **Trên máy của khách**: màn hình nền có file **`May so 14-85 (CloudBlue).txt`** (khách không xoá / sửa được), các hộp nhắc hết hạn ghi `CloudBlue PC [may so 14-85]`. Sửa số trên web → khoảng 30 giây sau máy đổi theo.
- Cài lại từ xa (**Cài lại** / **Bàn giao**) không hỏi lại — số máy do web giữ.

### C3. Xem tình trạng / lệnh tại máy
Mở file **`C:\CloudBluePC\os\status.txt`** bằng Notepad (tài khoản khách cũng mở được): ghi máy đã đăng ký với hệ thống chưa, có nối được máy chủ không.

Các lệnh dưới đây cần quyền Admin — chỉ dùng được khi tạo ISO với `-KhachAdmin` (mặc định trên máy không còn tài khoản quản trị nào, xem mục F):

```
C:\CloudBluePC\agent\cbpc.cmd status
C:\CloudBluePC\agent\cbpc.cmd reinstall 1511 all
C:\CloudBluePC\agent\cbpc.cmd log
```

`status` = đã đăng ký chưa, nối máy chủ được không · `reinstall <bản> all|disk|system` = cài lại ngay tại máy · `log` = nhật ký.

### C4. Hạn thuê + nhắc hết hạn (cần SQL v42)
**Đặt hạn**: cột **Hạn thuê** › **⏱ Đặt hạn / Gia hạn** › bấm `+1 giờ … +30 ngày`, hoặc gõ số khác, hoặc chọn hẳn 1 thời điểm › **Lưu**. Gia hạn thì **nối vào hạn đang có**; máy đã hết hạn / chưa đặt thì tính từ bây giờ. **Bỏ hạn** = máy không tự tắt nữa.

**Nhắc hết hạn — cho cả bạn và khách, lặp lại tới khi gia hạn:**

- **Bạn (web)**: máy còn trong khoảng nhắc (mặc định **2 ngày**) hoặc đã hết hạn thì **đầu Bảng quản trị luôn có dải báo** — vàng: `⏳ Máy PC … còn 1 ngày 3 giờ là hết hạn`, đỏ: `⛔ … đã HẾT HẠN` — ở mọi tab, kèm nút **⏱ Gia hạn** bấm là mở đúng máy đó. Số trên nút **💻 Máy PC** đếm cả các máy này. Gia hạn / bỏ hạn / bàn giao thì dòng đó mới mất.
- **Khách (trên máy)**: hộp thông báo hiện khi vào khoảng nhắc, **lặp lại mỗi 4 giờ và mỗi lần bật máy**, giờ cuối nhắc ở 60 · 30 · 10 · 5 · 1 phút. Hộp nằm trên màn hình tới lần nhắc kế hoặc tới khi khách bấm OK; ghi rõ còn bao lâu + giờ hết hạn.
- Thuê ngắn thì chỉ nhắc ở **1/4 thời gian cuối** (thuê 1 ngày → 6 giờ cuối, thuê 1 giờ → 15 phút cuối) để khỏi nhắc suốt buổi thuê.
- Đổi 2 con số ở web › Máy PC › **🔔 Cảnh báo**: *Bắt đầu nhắc khi còn … giờ* (0 = không nhắc trước, máy vẫn báo 10 phút + 1 phút trước khi tắt) và *Nhắc khách lại mỗi … giờ* (0 = chỉ nhắc ở các mốc).

Máy làm gì:

- Nhận hạn mới trong khoảng 30 giây (máy đang tắt thì lúc bật lên). **Mất mạng máy vẫn tự đếm**, giờ tính theo máy chủ nên chỉnh đồng hồ trên máy không lách được.
- **Hết hạn**: báo khách, Windows đếm ngược 60 giây rồi **tắt máy**. Gia hạn kịp trong 60 giây đó thì lệnh tắt được huỷ.
- Máy đã hết hạn mà bị **bật lại**: chờ hỏi máy chủ (tối đa 3 phút, phòng khi bạn vừa gia hạn) rồi tự tắt lại. Gia hạn lúc máy đang tắt → bật máy lên là dùng tiếp, không nhắc nữa.
- **🧼 Bàn giao** xoá luôn hạn thuê cũ; đặt hạn cho khách mới sau khi máy cài xong.

Các cảnh báo khác hiện ở tab **🛡️ Bảo mật**: máy đang thuê mất kết nối quá 15 phút · có máy mới đăng ký chờ duyệt · đồng hồ trên máy bị chỉnh lùi · bảo mật trên máy bị đổi (khách có lại quyền Admin, có tài khoản quản trị mới…) · phần cứng thay đổi (RAM, ổ cứng, CPU) · lệnh cài lại thất bại.

**Gửi thêm về mail / Telegram — không bắt buộc.** Muốn dùng thì đặt biến trên Vercel (project › **Environment Variables** › **Add Environment Variable**) rồi Deployments › `⋯` › **Redeploy**:

| Biến | Giá trị |
|---|---|
| `ADMIN_EMAIL` | địa chỉ mail nhận cảnh báo |
| `RESEND_API_KEY` | khoá API của dịch vụ gửi thư Resend (resend.com › API Keys › Create API Key › quyền *Sending access*; gói miễn phí đủ dùng) |
| `MAIL_FROM` | người gửi. Chưa xác minh tên miền trong Resend: đặt `CloudBlue <onboarding@resend.dev>` và `ADMIN_EMAIL` = **đúng mail đăng ký Resend** (Resend chỉ cho gửi tới mail đó). Đã xác minh tên miền: `CloudBlue <no-reply@cloudblue.vn>` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | nếu muốn nhận qua Telegram (bot của bạn + mã phòng chat) |

Kiểm tra: web › Máy PC › **🔔 Cảnh báo** › **Gửi thư thử** — dòng kết quả ghi rõ kênh nào được, kênh nào thiếu gì. Các khoá này **tự bạn dán vào Vercel, không gửi cho ai**.

---

## D. Driver, ảnh nền, lệnh chạy lần đầu

**Cách nhanh nhất — kéo thả lúc tạo ISO.** Ở bước 5 script hỏi riêng cho từng bản Windows (`DRIVER rieng cho ban WINDOWS 1511 nay…`):
kéo file driver (`.exe`, `.zip`, `.7z`, `.rar`, `.cab`) hoặc cả thư mục driver vào cửa sổ PowerShell rồi Enter, từng cái một; hết thì Enter trống.
Driver kéo ở bản nào thì **chỉ nạp khi cài bản đó** (kéo ở 1511 thì cài 22H2 không dính). Ví dụ bản 1511: kéo gói VGA NVIDIA `.exe`, Enter, kéo gói driver mạng, Enter, Enter trống.

**Cách cho người dùng lâu dài — thư mục `cb-them`** (driver dùng chung nhiều bản, lệnh chạy lần đầu, ảnh nền riêng). Tạo thư mục tên **`cb-them`** ngay cạnh các file ISO (script tự tìm thấy). Bên trong:

```
cb-them\
  drivers\              driver cho MỌI bản Windows
  drivers\1511\         driver CHỈ cho bản 1511 (ví dụ LAN + VGA)
  drivers\22h2\         driver chỉ cho bản 22H2
  firstboot.d\          lệnh chạy 1 lần ở lần đăng nhập đầu (mọi bản)
  firstboot.d\1511\     lệnh chỉ chạy trên bản 1511
  wallpaper.jpg         ảnh nền riêng (không có thì dùng ảnh nền CloudBlue)
```

**Driver** — bộ cài nạp thẳng vào Windows lúc cài (kể cả khi cài lại từ xa), nên máy có mạng ngay lần khởi động đầu.

*Cách chắc nhất — xuất driver từ 1 máy đang chạy ngon.* Trên 1 máy cùng loại đang chạy đúng bản Windows đó (ví dụ 1511) và đã cài đủ driver, mở **Windows PowerShell (Admin)**, dán:

```
dism /online /export-driver /destination:D:\drv-1511
```

(đổi `D:\drv-1511` thành thư mục bạn muốn; thư mục phải có sẵn). Lúc tạo ISO **kéo cả thư mục đó** vào câu hỏi driver của bản 1511 (hoặc chép vào `cb-them\drivers\1511\`). Cách này lấy đủ card mạng, Wi-Fi, VGA, âm thanh… đúng loại máy, ở đúng dạng bộ cài cần. Dàn có nhiều loại máy thì xuất ở mỗi loại 1 lần, bỏ chung vào `drivers\1511\`.

*Hoặc đưa thẳng gói driver bạn đang có* (kéo thả lúc tạo ISO, hoặc bỏ vào `cb-them\drivers\1511\`):

- **Thư mục có file `.inf`** (gói driver đã giải nén): dùng được ngay.
- File **`.zip`, `.cab`**: script tự giải nén.
- Gói **VGA NVIDIA `.exe`** (tên kiểu `466.77-notebook-win10-64bit-international-whql.exe`): đưa nguyên file. Gói này không nạp trước được, nên bộ cài **tự cài im lặng ở lần đăng nhập đầu, SAU KHI máy đã có mạng** — driver card mạng luôn xong trước (bản 1511 phải có mạng thì bộ cài NVIDIA mới chạy được). Mất 5–15 phút, màn hình nháy 1–2 lần là bình thường. Máy **không có card NVIDIA** (máy ảo, máy dùng card khác) thì tự bỏ qua. Lúc đó **chưa có mạng** thì phần mềm trên máy tự cài sau, ngay khi máy có mạng. Khung TÓM TẮT ghi dòng `VGA NVIDIA …`.
- File **`.exe`, `.7z`, `.rar` khác** (card mạng, Wi-Fi…): script thử giải nén bằng **7-Zip** (nếu máy tạo ISO có cài) rồi bằng công cụ có sẵn của Windows. Lấy ra được file `.inf` thì dùng; **không lấy ra được thì script bỏ gói đó và báo dòng `(!) Goi driver …` ở khung TÓM TẮT** — khi đó cài 7-Zip rồi chạy lại, hoặc dùng cách xuất driver ở trên.
- Khung TÓM TẮT ghi mỗi thư mục driver 1 dòng, ví dụ `DRIVER 1511: 12 file .inf [card mang: 3 (rt640x64.inf Realtek; …) | VGA: 1 | khac: 8] - chi nap khi cai ban 1511` — phần trong ngoặc vuông cho biết gói có **driver card mạng** hay không (`card mang: 0` = không có: bản Windows đó phải tự có sẵn driver mạng, không thì máy không lên web). **Không có dòng `DRIVER` nào cho bản đó** nghĩa là không driver nào được nạp.
- Driver mạng cho 1511 là **bắt buộc**: thiếu thì máy không có mạng, không lên web được.
- Máy nối mạng bằng **Wi-Fi** thì ngoài driver còn phải có tên mạng + mật khẩu: bộ cài chưa tự làm việc này, hỏi hỗ trợ để thêm lệnh vào `firstboot.d`. Máy cắm dây LAN thì không cần.

**Lệnh chạy lần đầu** (`firstboot.d`) — file `.cmd` / `.bat` / `.ps1`, chạy theo thứ tự tên (`10-…`, `20-…`), mỗi máy 1 lần sau khi cài. Dùng cho driver chỉ có bộ cài `.exe` không giải nén được, cài phần mềm, kích hoạt bản quyền của bạn. Trong lệnh, `%~dp0` là thư mục chứa chính file lệnh đó, `%CB_OS%` là tên bản đang cài (`1511`, `22h2`).

**Ảnh nền** — mặc định là ảnh CloudBlue (cá voi, nền xanh đậm). Muốn ảnh khác: đặt file `wallpaper.jpg` (hoặc `.png`) vào `cb-them`. Ảnh chỉ được đặt lúc máy mới cài; khách tự đổi ảnh khác thì giữ ảnh của khách, cài lại máy thì về ảnh mặc định.

USB ghi bằng Rufus thì bỏ thẳng file vào `cb\drivers\…` và `cb\os\firstboot.d\…` trên USB cũng được (driver phải ở dạng có file `.inf`). Driver càng nặng thì phân vùng cứu hộ càng lớn.

---

## E. Cần biết

- **Phân vùng cứu hộ**: mỗi máy có 1 phân vùng ẩn `CBRECOVERY` chứa bộ cài (cỡ ≈ tổng các bản Windows + 15% + 2GB; khung TÓM TẮT ghi dòng `CUU_HO … GB`). Nhờ nó mới cài lại từ xa được. Ổ đích phải lớn hơn **cỡ cứu hộ + 60GB**, nhỏ hơn thì bộ cài vẫn cài Windows nhưng bỏ phân vùng này. Máy không có phân vùng cứu hộ → web ghi "⚠ không có phân vùng cứu hộ" và muốn cài lại phải dùng USB.
- **Bản quyền Windows**: bộ cài **không kích hoạt** Windows. Khoá sản phẩm nằm sẵn trong bản Windows (nếu người làm bản đó có để) được giữ nguyên. Với bản **gốc của Microsoft** cũ hơn 1703 (như 1511), màn hình cài lần đầu sẽ đứng chờ nhập key nên bộ cài tự điền *khoá cài đặt chung* của Microsoft cho đúng phiên bản (chỉ để qua màn hình, không kích hoạt). Bản tuỳ biến (Lite…) thì không tự điền; nếu cài bản đó mà màn hình dừng hỏi key, tạo lại ISO với `-KhoaChung`. Không muốn đụng tới khoá nào: `-KhongKhoaChung`. Kích hoạt bằng key của bạn: đặt lệnh vào `firstboot.d`.
- **Nếu bạn tạo ISO với `-KhachAdmin`** (khách có quyền Admin trên máy) thì khách phá được phân vùng cứu hộ / phần mềm CloudBlue trên máy đó. Khi đó máy báo offline hoặc cài lại lỗi → cài lại bằng USB là sạch hoàn toàn. Mã đăng ký không nằm trên máy cho thuê (chỉ nằm trên USB / ISO); mỗi máy chỉ giữ mã riêng của chính nó và mã này đổi sau mỗi lần cài lại.
- **Giữ kỹ USB / file ISO**: trên đó có mã đăng ký. Đừng để khách cầm.
- **Tài khoản Windows mặc định** `PC` không mật khẩu, tự đăng nhập, là **tài khoản thường** (không có quyền Admin). Tài khoản không mật khẩu không đăng nhập được qua mạng (chặn sẵn của Windows).
- **ISO tuỳ biến** (bản Lite, bản có sẵn phần mềm…): bộ cài chỉ lấy **bản Windows** trong ISO (`install.wim` / `install.esd`). Các file cài thêm mà người làm ISO để riêng bên ngoài (`autounattend.xml`, thư mục `$OEM$`) **không được dùng** — khung TÓM TẮT liệt kê chúng ở dòng "file rieng cua ISO nay". Thiếu thứ gì sau khi cài thì báo hỗ trợ.
- **Chỉ hỗ trợ** Windows 64-bit, ISO chuẩn có `sources\install.wim` hoặc `install.esd`. ISO gộp x86 + x64 chỉ dùng được làm bản Windows phụ (cần thêm 1 ISO 64-bit chuẩn). ISO kiểu Ghost (`.gho`, `.tib`) không dùng được.
- **Ổ đích** được chọn theo thứ tự: ổ gắn trong duy nhất → ổ đang có Windows cũ → ổ SSD nhỏ nhất. Không bao giờ chọn USB / thẻ nhớ / ổ ảo / ổ chứa bộ cài. Màn hình đếm ngược luôn ghi rõ ổ sẽ xoá.
- **Mất điện giữa lúc cài lại**: bật lại máy, bộ cài tự làm tiếp (tối đa 3 lần). Quá 3 lần thì cần USB.
- **Đồng hồ**: bộ cài đặt múi giờ Việt Nam ngay trong Windows mới (không còn cảnh bản tuỳ biến lệch 1 giờ sau khi cài); phần mềm trên máy tự chỉnh đồng hồ theo máy chủ khi lệch quá 2 phút.
- **Bản Windows kiểu "ghost"** (ảnh chụp từ 1 máy đã cài sẵn: khởi động thẳng vào tài khoản có sẵn, không qua bước cài đặt lần đầu — bản 1511 Lite của shop là kiểu này): màn hình bộ cài ghi `Ban Windows nay la kieu GHOST`. Ở lần khởi động đầu, phần mềm CloudBlue **tự làm thay** bước cài: **nhận tài khoản ảnh đang dùng làm tài khoản khách** (đổi tên thành `PC` — hoặc tên bạn đặt bằng `-TaiKhoan` —, giữ nguyên màn hình nền + phần mềm cài sẵn), tắt các tài khoản khác, **đổi tên máy** theo tên trên web, chạy `firstboot.d`, chờ mạng, cài VGA, hạ tài khoản khách xuống tài khoản thường rồi **tự khởi động lại 1 lần** (vài phút sau khi vào Desktop; màn hình có hộp báo `KHONG tat may`). Ảnh dùng thẳng tài khoản `Administrator` có sẵn thì bộ cài tạo tài khoản khách mới (hồ sơ mới).
- **Mật khẩu không hết hạn**: Windows mặc định bắt đổi mật khẩu sau 42 ngày (kể cả tài khoản không mật khẩu) — bộ cài tắt hạn này trên mọi máy, không thì tới ngày đó tài khoản khách kẹt ở màn hình đăng nhập.

## F. Bảo mật — máy cho thuê được khoá thế nào

Mặc định (không dùng `-KhachAdmin`) mỗi máy cài từ ISO này:

- **Khách dùng tài khoản thường.** Lúc cài, tài khoản `PC` tạm là Admin để chạy driver / script của bạn; cuối lần đăng nhập đầu bộ cài **hạ nó xuống tài khoản thường rồi tự khởi động lại 1 lần**. Từ đó khách không cài được phần mềm đòi quyền quản trị, không gỡ / sửa được phần mềm CloudBlue, không đụng được phân vùng cứu hộ, không tự đổi được mật khẩu Windows.
- **Trên máy không còn tài khoản quản trị nào dùng được.** Tài khoản `Administrator` có sẵn của Windows bị tắt và đặt mật khẩu ngẫu nhiên không ai biết (kể cả vào Safe Mode cũng không dùng được). Mọi việc quản trị đi qua web (cài lại, khởi động lại…). Phần mềm cần quyền Admin thì cài sẵn trong bản Windows hoặc bỏ vào `firstboot.d` (mục D).
- **Thư mục `C:\CloudBluePC` bị khoá**: chỉ hệ thống (SYSTEM) và nhóm Administrators vào được. Mã riêng của máy, nhật ký, script `firstboot.d` của bạn — tài khoản khách không đọc được. Khách chỉ đọc được 2 thư mục `py` và `os` (để ảnh nền tự đặt lúc đăng nhập) và không ghi được vào đâu.
- **Phân vùng cứu hộ bị khoá** tương tự: tài khoản thường không đọc, không sửa được bộ cài nằm trong đó → lần "Dọn sạch cả máy" kế tiếp luôn chạy đúng bộ cài gốc của bạn.
- Phần mềm trên máy tự kiểm lại các khoá này mỗi lần khởi động và vài giờ một lần. Lần đăng nhập đầu bị dở (mất điện) thì 1 giờ sau máy tự hạ quyền tài khoản khách.
- Trên web, **thông tin do máy gửi lên luôn được coi là dữ liệu lạ** (chỉ in ra dạng chữ) — khách không thể qua máy thuê mà chèn mã vào trang quản trị. Mỗi máy chỉ có 1 mã riêng, lộ mã đó cũng không đụng được máy khác hay tài khoản admin.

Phần chỉ bạn làm được (bộ cài không làm thay):

- Đặt **mật khẩu BIOS** và để máy chỉ khởi động từ ổ cứng (không cho khởi động USB) — nếu khách ngồi trực tiếp tại máy.
- Bật **xác minh 2 bước** cho tài khoản GitHub, Supabase, Vercel, Cloudflare. Ai chiếm được 1 trong các tài khoản đó là điều khiển được cả hệ thống.
- Giữ kỹ USB / file ISO (trên đó có mã đăng ký). Nghi lộ → web › Máy PC › **Tạo mã đăng ký** lại (mã cũ hết dùng ngay) rồi tạo lại ISO.
- Khách cũ trả máy: bấm **🧼 Bàn giao** (xoá sạch mọi ổ + cài lại + xoá hạn thuê cũ) trước khi giao cho khách mới.

## G. Khi có trục trặc

| Hiện tượng | Xem / làm |
|---|---|
| Tạo ISO dừng ở dòng `!! DUNG:` | chụp từ dòng `== ` gần nhất tới đó, gửi hỗ trợ |
| Khung TÓM TẮT ghi `ISO: CHUA dong` | chưa lấy được công cụ đóng ISO (`oscdimg`) của Microsoft — dòng `(!)` ghi lý do; gửi cả khung cho hỗ trợ rồi chạy lại lệnh |
| Khung TÓM TẮT có `(!) File ISO cu dang bi chuong trinh khac giu` | máy ảo đang gắn file ISO cũ nên không ghi đè được → lần này ISO mới mang tên `…-2.iso` (dòng `ISO:` cuối khung ghi đúng tên). Gắn **file mới** đó vào máy ảo, hoặc tắt máy ảo / tháo ISO rồi chạy lại để ghi đè tên cũ |
| Khung TÓM TẮT có `(!) Goi driver …` | gói driver đó không dùng được (xem mục D) — các phần khác vẫn bình thường |
| Khởi động USB vào thẳng bộ cài Windows thường | chèn boot.wim không thành công hoặc USB ghi bằng công cụ sửa file — gửi khung TÓM TẮT |
| Cài xong nhưng không lên web | cửa sổ lúc đăng nhập đầu có dòng `!! CHUA CO MANG`? Sau 2–3 phút máy cũng hiện hộp báo `CHUA CO MANG`. Tại máy: bấm `Windows + R`, gõ `notepad C:\CloudBluePC\os\status.txt` — dòng `Mang LAN:` ghi máy có địa chỉ IP chưa, dòng `Ket noi may chu:` ghi lý do. Kiểm tra dây mạng / driver card mạng; ISO có nhập mã đăng ký không (TÓM TẮT ghi `Ma dang ky: CO … con hieu luc`) |
| **Máy ảo** cài bản 1511 (bản Lite) không có mạng | bản Lite thường không kèm driver card mạng ảo, driver bạn đưa là của máy thật → thử bản 1511 trên **máy thật**. Muốn thử tiếp trên Hyper-V: tắt máy ảo › Settings › Add Hardware › **Legacy Network Adapter** › chọn cùng Virtual Switch |
| Máy tự tắt, bật lại vài phút lại tắt | hết hạn thuê — xem cột **Hạn thuê** trên web; **⏱ Gia hạn** rồi bật máy lên |
| Không nhận được mail cảnh báo | mail là phần tuỳ chọn (mục C4): web › Máy PC › **🔔 Cảnh báo** › **Gửi thư thử**; dòng dưới nút ghi lý do (thiếu `ADMIN_EMAIL` / `RESEND_API_KEY` trên Vercel…). Không có mail thì dải báo đầu Bảng quản trị + tab 🛡️ Bảo mật vẫn đủ |
| Driver VGA không lên dù đã kèm gói | máy phải ra được mạng thì gói mới cài; card chưa nhận driver thì phần mềm tự chạy lại gói tối đa 3 lần (sau mỗi lần khởi động). Web › cột Cấu hình ghi tên card đang nhận |
| Máy tự khởi động lại 1 lần ngay sau khi vào Desktop lần đầu | bình thường — bước hạ tài khoản khách xuống tài khoản thường (mục F). Bản kiểu ghost: khởi động lại sau vài phút, kèm đổi tên máy + tên tài khoản |
| Cài bản ghost xong vẫn thấy tài khoản cũ (vd `admin`) có quyền Admin, tên máy cũ | chờ vài phút cho máy tự khởi động lại. Quá 10 phút: xem `C:\CloudBluePC\logs\provision.log` (dòng `ghost`); bộ cài bản cũ hơn 21.11b không làm bước này → tạo lại ISO |
| Máy báo "cần mã đăng ký" sau khi bạn tự cài lại bằng cách khác | web › Sửa máy › **🔓 Cho đăng ký lại** (mở 6 giờ) |
| Lệnh cài lại báo ✗ | xem dòng lý do ngay dưới lệnh trong bảng Máy PC |

Nhật ký: `C:\CloudBluePC\logs\agent.log`, `provision.log`; bộ cài: `cb\logs\pe-*.log` trên phân vùng cứu hộ (và `X:\cb-pe.log` lúc đang cài).

---

## H. Thành phần (cho người làm kỹ thuật)

```
winpc/
  tao-iso.ps1          tạo ISO (chạy trên máy có ISO gốc)
  cb_build.py          sắp xếp cây ISO, autounattend.xml, $OEM$
  CAI-DAT.cmd          cài lại ngay từ trong Windows (nằm ở gốc ISO)
  boot/winpeshl.ini    móc gọi bộ cài trong boot.wim
  pe/start.cmd, cb_pe.py     bộ cài chạy trong WinPE (Python nhúng)
  lib/cbsys.py, cbcore.py, cbrec.py   đọc ổ đĩa · tính toán chia ổ · phân vùng cứu hộ
  os/unattend.tpl.xml, provision.cmd, cb_provision.py, cb_stage.py
  agent/pcagent.py, watch.cmd, cbpc.cmd   agent chạy bằng SYSTEM trên máy cho thuê
  manifest.json        mã kiểm sha256 (tao-iso.ps1 kiểm khi tải; web đọc khi "Công bố bản agent")
  tests/               bộ thử (máy Windows giả) · tests/ci/ chạy trên Windows thật của GitHub Actions · tests/web/ thử trang quản trị + API
blueroblox-site/api/pc-notify.js   gửi cảnh báo máy PC về mail + Telegram (cơ sở dữ liệu tự gọi mỗi phút khi có cảnh báo chờ)
```

Máy cho thuê chỉ nói chuyện với Supabase bằng **khoá công khai của web** + mã riêng của máy (`pc_enroll`, `pc_poll`, `pc_allow_reenroll`); bộ tạo ISO gọi `pc_key_check`. Mọi việc quản trị đi qua các hàm `pc_admin_…` chỉ admin gọi được (`pc_admin_rent` = hạn thuê); hàng chờ cảnh báo (`pc_alerts_take` / `pc_alerts_unsend`) chỉ máy chủ web gọi được.
Ba đường để phần mềm tự chạy trong Windows mới: file trả lời (`unattend.xml`) → `SetupComplete.cmd` → dịch vụ khởi động `CloudBluePCBoot` (bộ cài ghi thẳng vào registry của Windows vừa bung; chạy xong tự gỡ).
Sửa bất kỳ file nào trong `winpc/` → tăng số bản trong file đó nếu là agent, chạy lại `tests/mkmanifest.py` để ghi `manifest.json`, rồi mới đưa lên GitHub.
