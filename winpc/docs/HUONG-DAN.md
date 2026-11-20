# CloudBlue PC — máy PC cho thuê tự cài, tự lên web (đợt 1 · bản 20.11a)

Bộ này thay việc "cài Windows tay rồi cài phần mềm điều khiển gửi khách":

1. **1 file ISO** (gộp các bản Windows bạn có, ví dụ 22H2 + 1511). Khởi động máy từ ISO / USB đó → máy **tự chọn ổ, đếm ngược 30 giây, xoá dữ liệu cũ, cài Windows, nạp driver bạn kèm theo, đặt ảnh nền CloudBlue**, không hỏi gì thêm.
2. Windows lên là **tự hiện trong Bảng quản trị › 💻 Máy PC** (tên máy, cấu hình, IP, online / offline).
3. Trên web bấm **🧹 Cài lại**: chọn bản Windows (22H2 / 1511) + mức xoá → máy tự khởi động lại, tự dọn sạch và cài lại, **không cần USB, không cần ra máy**.

> **Chưa có ở đợt này:** điều khiển máy bằng app PC / app điện thoại CloudBlue và bán tự động (khách mua → tự giao máy). Đó là đợt 2.

> **Chưa chạy trên máy thật.** Phần Windows mới được thử trên máy giả lập (hơn 200 phép thử logic) — lần đầu **phải thử trên 1 máy thử hoặc máy ảo**, đừng dùng ngay cho dàn máy đang có khách.

---

## A. Làm 1 lần

### A1. Thêm phần Máy PC vào cơ sở dữ liệu
Supabase › SQL Editor › New query › dán **toàn bộ** file `cloud-pc-v41.sql` › Run.
Dòng cuối phải ra: `v41 xong | t | t | t | t`. Chạy lại nhiều lần không sao; file này chỉ **thêm** bảng / hàm `pc_…`, không đụng phần đang có.

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
   - đường dẫn từng file ISO (kéo thả file vào cửa sổ rồi Enter; xong thì Enter trống);
   - thư mục thêm (driver, ảnh nền riêng… — mục D). Có thư mục tên `cb-them` nằm cạnh file ISO thì script tự lấy, không hỏi;
   - **mã đăng ký** (chuột phải để dán; mã không hiện ra màn hình);
   - nếu ISO có nhiều phiên bản (Home, Pro…): dùng bản số mấy (Enter = bản Pro);
   - bản Windows **mặc định** khi cài từ USB (Enter = bản mới nhất; gõ số để chọn 1511).
4. Chờ 15–40 phút. Cuối cùng hiện khung **TÓM TẮT** và file `CloudBlue-PC.iso`.

Script chỉ **đọc** ISO gốc và tạo thư mục làm việc + file ISO mới; không sửa ISO gốc, không đụng ổ đĩa của máy đang chạy.
Chép cả khung TÓM TẮT gửi hỗ trợ nếu có dòng `(!)` hoặc `CHUA DAT`.

Tuỳ chọn (thêm vào cuối lệnh `& $d`):

| Tham số | Ý nghĩa |
|---|---|
| `-TaiKhoan Khach -MatKhau "abc123"` | tài khoản Windows tạo sẵn (mặc định `PC`, không mật khẩu, tự đăng nhập) |
| `-Out D:\CloudBlue-PC.iso -Work D:\cb-work` | nơi ghi ISO / thư mục làm việc (không có dấu cách) |
| `-Them D:\cb-them` | thư mục thêm: driver, lệnh chạy lần đầu, ảnh nền riêng (xem mục D) |
| `-KhongKhoaChung` | không điền khoá cài đặt chung (xem mục E) |

---

## B. Thử lần đầu (bắt buộc) — trên máy thử hoặc máy ảo

**Máy đó sẽ bị xoá sạch.**

- *Máy ảo* (VMware / VirtualBox / Hyper-V): tạo máy 64-bit, ổ ảo **≥ 100GB** (ổ nhỏ quá sẽ không tạo phân vùng cứu hộ — xem mục E), RAM ≥ 4GB, mạng NAT, gắn `CloudBlue-PC.iso` làm ổ CD, bật máy.
- *Máy thật*: ghi ISO ra USB bằng **Rufus** (để nguyên mọi lựa chọn mặc định, đừng tích các ô "tuỳ biến Windows") hoặc chép ISO vào USB **Ventoy**; cắm vào máy thử, khởi động từ USB.

Điều sẽ thấy:

1. Màn hình đen chữ trắng **CloudBlue PC**: danh sách ổ cứng, ổ sẽ bị xoá, bản Windows sẽ cài, **đếm ngược 30 giây**.
   Phím: `Enter` = cài ngay bản mặc định · `1`–`9` = chọn bản Windows khác (ví dụ 1511) · `D` = đổi ổ đích · `A` = bật / tắt xoá cả các ổ khác · `X` = huỷ, chuyển sang bộ cài Windows thường · `C` = mở dòng lệnh. Bấm phím khác `Enter` thì đếm ngược dừng lại, khi đó phải bấm `Enter` mới cài.
2. Tự chia ổ → bung Windows (5–20 phút) → khởi động lại 1–2 lần → vào thẳng màn hình Desktop.
3. Khoảng 1 phút sau: máy hiện ở web › Máy PC, trạng thái **Chờ duyệt** → bấm **Duyệt**.

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
| **Huỷ lệnh** | gỡ lệnh chưa chạy. Máy đã nhận lệnh và đang cài thì vẫn cài tiếp |
| **⬆ Công bố bản agent** | khi có bản phần mềm mới trên GitHub: mọi máy tự cập nhật trong khoảng 1 phút |

Mức xoá khi cài lại:

- **Dọn sạch cả máy** — xoá mọi ổ cứng gắn trong (dùng khi khách cũ trả máy).
- **Cả ổ hệ thống** — xoá ổ chứa Windows, giữ các ổ cứng khác.
- **Chỉ phân vùng Windows** — chỉ cài lại ổ C:, giữ các phân vùng / ổ khác (đổi bản Windows cho khách đang thuê).

Máy offline lúc ra lệnh: lệnh chờ, máy online lại là chạy.

### C3. Lệnh tại máy
Mở PowerShell (Admin) trên máy cho thuê:

```
C:\CloudBluePC\agent\cbpc.cmd status
C:\CloudBluePC\agent\cbpc.cmd reinstall 1511 all
C:\CloudBluePC\agent\cbpc.cmd log
```

`status` = đã đăng ký chưa, nối máy chủ được không · `reinstall <bản> all|disk|system` = cài lại ngay tại máy · `log` = nhật ký.

---

## D. Driver, ảnh nền, lệnh chạy lần đầu

Tạo thư mục tên **`cb-them`** ngay cạnh các file ISO (script tự tìm thấy). Bên trong:

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

(đổi `D:\drv-1511` thành thư mục bạn muốn; thư mục phải có sẵn). Chép cả thư mục đó vào `cb-them\drivers\1511\`. Cách này lấy đủ card mạng, Wi-Fi, VGA, âm thanh… đúng loại máy, ở đúng dạng bộ cài cần. Dàn có nhiều loại máy thì xuất ở mỗi loại 1 lần, bỏ chung vào `drivers\1511\`.

*Hoặc bỏ thẳng gói driver bạn đang có:*

- **Thư mục có file `.inf`** (gói driver đã giải nén): bỏ vào `drivers\1511\<tên gì cũng được>\`.
- File **`.zip`**: script tự giải nén.
- Gói **VGA NVIDIA `.exe`** (tên kiểu `466.77-notebook-win10-64bit-international-whql.exe`): bỏ nguyên file vào `drivers\1511\`. Gói này không nạp trước được, nên bộ cài sẽ **tự cài im lặng ở lần đăng nhập đầu** (mất vài phút, màn hình nháy 1–2 lần là bình thường).
- File **`.exe` khác** (card mạng, Wi-Fi…): script thử giải nén **nếu máy tạo ISO có cài 7-Zip**. Không giải nén ra được file `.inf` thì script báo ở khung TÓM TẮT — khi đó dùng cách xuất driver ở trên.
- Khung TÓM TẮT ghi `DRIVER 1511: N file .inf`. Ghi **0 file .inf** nghĩa là driver đó không được nạp.
- Driver mạng cho 1511 là **bắt buộc**: thiếu thì máy không có mạng, không lên web được.
- Máy nối mạng bằng **Wi-Fi** thì ngoài driver còn phải có tên mạng + mật khẩu: bộ cài chưa tự làm việc này, hỏi hỗ trợ để thêm lệnh vào `firstboot.d`. Máy cắm dây LAN thì không cần.

**Lệnh chạy lần đầu** (`firstboot.d`) — file `.cmd` / `.bat` / `.ps1`, chạy theo thứ tự tên (`10-…`, `20-…`), mỗi máy 1 lần sau khi cài. Dùng cho driver chỉ có bộ cài `.exe` không giải nén được, cài phần mềm, kích hoạt bản quyền của bạn. Trong lệnh, `%~dp0` là thư mục chứa chính file lệnh đó, `%CB_OS%` là tên bản đang cài (`1511`, `22h2`).

**Ảnh nền** — mặc định là ảnh CloudBlue (cá voi, nền xanh đậm). Muốn ảnh khác: đặt file `wallpaper.jpg` (hoặc `.png`) vào `cb-them`. Ảnh chỉ được đặt lúc máy mới cài; khách tự đổi ảnh khác thì giữ ảnh của khách, cài lại máy thì về ảnh mặc định.

USB ghi bằng Rufus thì bỏ thẳng file vào `cb\drivers\…` và `cb\os\firstboot.d\…` trên USB cũng được (driver phải ở dạng có file `.inf`). Driver càng nặng thì phân vùng cứu hộ càng lớn.

---

## E. Cần biết

- **Phân vùng cứu hộ**: mỗi máy có 1 phân vùng ẩn `CBRECOVERY` chứa bộ cài (cỡ ≈ tổng các bản Windows + 15% + 2GB; khung TÓM TẮT ghi dòng `CUU_HO … GB`). Nhờ nó mới cài lại từ xa được. Ổ đích phải lớn hơn **cỡ cứu hộ + 60GB**, nhỏ hơn thì bộ cài vẫn cài Windows nhưng bỏ phân vùng này. Máy không có phân vùng cứu hộ → web ghi "⚠ không có phân vùng cứu hộ" và muốn cài lại phải dùng USB.
- **Bản quyền Windows**: bộ cài **không kích hoạt** Windows. Khoá sản phẩm nằm sẵn trong bản Windows (nếu người làm bản đó có để) được giữ nguyên. Với bản **gốc của Microsoft** cũ hơn 1703 (như 1511), màn hình cài lần đầu sẽ đứng chờ nhập key nên bộ cài tự điền *khoá cài đặt chung* của Microsoft cho đúng phiên bản (chỉ để qua màn hình, không kích hoạt). Bản tuỳ biến (Lite…) thì không tự điền; nếu cài bản đó mà màn hình dừng hỏi key, tạo lại ISO với `-KhoaChung`. Không muốn đụng tới khoá nào: `-KhongKhoaChung`. Kích hoạt bằng key của bạn: đặt lệnh vào `firstboot.d`.
- **Khách có quyền Admin trên máy** thì về lý thuyết phá được phân vùng cứu hộ / phần mềm CloudBlue. Khi đó máy báo offline hoặc cài lại lỗi → cài lại bằng USB là sạch hoàn toàn. Mã đăng ký không nằm trên máy cho thuê (chỉ nằm trên USB / ISO); mỗi máy chỉ giữ mã riêng của chính nó và mã này đổi sau mỗi lần cài lại.
- **Giữ kỹ USB / file ISO**: trên đó có mã đăng ký. Đừng để khách cầm.
- **Tài khoản Windows mặc định** `PC` không mật khẩu, tự đăng nhập. Tài khoản không mật khẩu không đăng nhập được qua mạng (chặn sẵn của Windows).
- **ISO tuỳ biến** (bản Lite, bản có sẵn phần mềm…): bộ cài chỉ lấy **bản Windows** trong ISO (`install.wim` / `install.esd`). Các file cài thêm mà người làm ISO để riêng bên ngoài (`autounattend.xml`, thư mục `$OEM$`) **không được dùng** — khung TÓM TẮT liệt kê chúng ở dòng "file rieng cua ISO nay". Thiếu thứ gì sau khi cài thì báo hỗ trợ.
- **Chỉ hỗ trợ** Windows 64-bit, ISO chuẩn có `sources\install.wim` hoặc `install.esd`. ISO gộp x86 + x64 chỉ dùng được làm bản Windows phụ (cần thêm 1 ISO 64-bit chuẩn). ISO kiểu Ghost (`.gho`, `.tib`) không dùng được.
- **Ổ đích** được chọn theo thứ tự: ổ gắn trong duy nhất → ổ đang có Windows cũ → ổ SSD nhỏ nhất. Không bao giờ chọn USB / thẻ nhớ / ổ ảo / ổ chứa bộ cài. Màn hình đếm ngược luôn ghi rõ ổ sẽ xoá.
- **Mất điện giữa lúc cài lại**: bật lại máy, bộ cài tự làm tiếp (tối đa 3 lần). Quá 3 lần thì cần USB.

## F. Khi có trục trặc

| Hiện tượng | Xem / làm |
|---|---|
| Tạo ISO dừng ở dòng `!! DUNG:` | chụp từ dòng `== ` gần nhất tới đó, gửi hỗ trợ |
| Khởi động USB vào thẳng bộ cài Windows thường | chèn boot.wim không thành công hoặc USB ghi bằng công cụ sửa file — gửi khung TÓM TẮT |
| Cài xong nhưng không lên web | tại máy: `cbpc.cmd status` và `cbpc.cmd log`; kiểm tra mạng; ISO có nhập mã đăng ký không (TÓM TẮT ghi `Ma dang ky: CO`) |
| Máy báo "cần mã đăng ký" sau khi bạn tự cài lại bằng cách khác | web › Sửa máy › **🔓 Cho đăng ký lại** (mở 6 giờ) |
| Lệnh cài lại báo ✗ | xem dòng lý do ngay dưới lệnh trong bảng Máy PC |

Nhật ký: `C:\CloudBluePC\logs\agent.log`, `provision.log`; bộ cài: `cb\logs\pe-*.log` trên phân vùng cứu hộ (và `X:\cb-pe.log` lúc đang cài).

---

## G. Thành phần (cho người làm kỹ thuật)

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
```

Máy cho thuê chỉ nói chuyện với Supabase bằng **khoá công khai của web** + mã riêng của máy (`pc_enroll`, `pc_poll`, `pc_allow_reenroll`). Mọi việc quản trị đi qua các hàm `pc_admin_…` chỉ admin gọi được.
Sửa bất kỳ file nào trong `winpc/` → tăng số bản trong file đó nếu là agent, chạy lại `tests/mkmanifest.py` để ghi `manifest.json`, rồi mới đưa lên GitHub.
