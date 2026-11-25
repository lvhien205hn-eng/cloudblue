# VPS ảo hoá (Proxmox VE) — hướng dẫn

Mỗi VPS là 1 máy ảo Windows trên máy chủ Proxmox, có sẵn phần mềm CloudBlue PC. Khách bấm là vào màn hình trên web, app điện thoại, app máy tính — như VPS GPU. Không cần IP riêng, không mở cổng modem.

| Bước | Làm ở đâu | Làm mấy lần |
|---|---|---|
| 1. Chạy SQL v56 | Supabase › SQL Editor › snippet **CloudBlue v56 VPS ao hoa - bam Run** › Run | 1 lần |
| 2. Cài Proxmox VE | máy chủ riêng (không dùng chung máy chạy giả lập Cloud Phone) | mỗi máy chủ |
| 3. Cài cbhost — 1 lệnh | Shell của Proxmox | mỗi máy chủ |
| 4. Duyệt máy chủ | web › Quản trị › Máy cho thuê › 🧩 VPS ảo hoá › 🖥 Máy chủ | mỗi máy chủ |
| 5. Dựng máy mẫu Windows | trên từng máy chủ Proxmox | mỗi bản Windows |
| 6. Nhập giá + bật bán | web › 🧩 VPS ảo hoá › 💲 Gói & giá · ⚙ Cài đặt | 1 lần |

---

## 1. Tải về

| Tệp | Link chính thức | Ghi chú |
|---|---|---|
| Proxmox VE (ISO) | https://www.proxmox.com/en/downloads | ghi USB bằng Rufus (chọn **DD image**) hoặc chép vào USB Ventoy |
| Windows Server 2012 R2 (dùng thử) | https://www.microsoft.com/en-us/evalcenter/download-windows-server-2012-r2 | nhẹ nhất, chạy được gói 1 GB RAM |
| Windows 10 Enterprise LTSC 2021 (dùng thử) | https://www.microsoft.com/en-us/evalcenter/download-windows-10-enterprise | chọn bản **ISO – Enterprise LTSC** |
| Windows Server 2016 (dùng thử, tải thẳng ISO tiếng Anh) | https://go.microsoft.com/fwlink/p/?LinkID=2195174&clcid=0x409&culture=en-us&country=US | trang gốc: https://www.microsoft.com/en-us/evalcenter/download-windows-server-2016 |
| Windows Server 2019 (dùng thử, tải thẳng ISO) | https://go.microsoft.com/fwlink/p/?LinkID=2195167&clcid=0x409&culture=en-us&country=US | trang gốc: …/download-windows-server-2019 |
| Windows Server 2022 (dùng thử, tải thẳng ISO) | https://go.microsoft.com/fwlink/p/?LinkID=2195280&clcid=0x409&culture=en-us&country=US | trang gốc: …/download-windows-server-2022 |
| Driver VirtIO cho **2012 R2** (tải thẳng) | https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.240-1/virtio-win-0.1.240.iso | 0.1.240 là bản cuối còn hỗ trợ 2012 / 2012 R2 |
| Driver VirtIO cho **Win10 LTSC / 2016 / 2019 / 2022** (tải thẳng) | https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.271-1/virtio-win-0.1.271.iso | bản ổn định — **đừng dùng 0.1.285** (lỗi ổ đĩa + mạng) **và 0.1.302** (lỗi sao lưu VSS của QEMU agent, Proxmox chưa khuyên dùng) |

Không cần tải gì thêm: lệnh ghép ISO tự tải + tự kiểm chữ ký Python, ffmpeg, bản vá UCRT (2012 R2), oscdimg — thiếu / sai là **DỪNG** và báo rõ thiếu gì. ISO virtio cũng có thể bỏ trống (bấm Enter) để lệnh tự tải đúng bản.

Bản dùng thử (Evaluation) của Microsoft có hạn dùng (Server: 180 ngày). Giấy phép Windows cho VPS bán cho khách là việc chủ shop tự lo.
Linux (Ubuntu / Debian …): làm ở bản sau.

ISO tải về: đưa lên Proxmox ở **Datacenter › tên máy › local › ISO Images › Upload** (hoặc **Download from URL** — dán link tải trực tiếp).

## 2. Cài Proxmox VE

- BIOS: bật **Intel VT-x / AMD-V** (Virtualization) — thiếu thì máy ảo chạy rất chậm, web báo "không có KVM".
- Cài từ USB như cài Windows: chọn ổ, đặt mật khẩu root, đặt **IP LAN tĩnh** (vd `192.168.1.50`).
- Nên ≥ 64 GB RAM + ổ NVMe. Mỗi VPS 20 GB ổ (máy ảo dùng ổ kiểu cấp dần).
- Vào trang Proxmox: `https://<IP LAN>:8006` (cùng mạng LAN), đăng nhập `root`.

## 3. Cài cbhost — 1 lệnh

Trang Proxmox › tên máy (cột trái) › **Shell** → dán lệnh, Enter:

```
bash <(curl -fsSL https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/cai-cbhost.sh)
```

- Lệnh không hỏi khoá bí mật nào: máy tự sinh mã riêng (chỉ nằm trên máy, file `/etc/cloudblue/cbhost.secret`), web chỉ giữ dấu băm.
- cbhost chạy thành dịch vụ `cloudblue-cbhost`: tự chạy khi bật máy, tự bật lại khi lỗi, **tự cập nhật 1 giờ / lần** từ kho này.
- Chạy lại lệnh lúc nào cũng được (= cập nhật ngay), giữ nguyên mã riêng + sổ máy ảo.
- Xem trạng thái: `python3 /opt/cloudblue/cbhost.py status` · nhật ký: `journalctl -u cloudblue-cbhost -f`

## 4. Duyệt máy chủ

Khoảng 1 phút sau lệnh cài, web › Quản trị › Máy cho thuê › **🧩 VPS ảo hoá** › **🖥 Máy chủ** có máy mới **Chờ duyệt** → bấm **✅ Duyệt máy này** (hoặc bật *Máy chủ Proxmox mới tự được duyệt* ở ⚙ Cài đặt).
Thẻ máy chủ cho thấy: CPU / RAM / ổ, số VPS / số chỗ, máy mẫu có / thiếu, IP, doanh thu tháng (💰 rải theo thời gian VPS chạy · 💵 tiền khách trả).
Nút **🔧 Trang Proxmox** mở `https://<IP LAN>:8006` — dùng được khi máy bạn cùng mạng LAN với máy chủ. Ở ngoài: tạo 1 VPS cho chính mình (⚙ Cài đặt › Tạo VPS cho 1 tài khoản) rồi mở trang Proxmox từ trong VPS đó.

## 5. Máy mẫu Windows

Mỗi bản Windows bán cho khách = 1 **máy mẫu** (template) trên Proxmox, đặt **đúng tên** ở web › 🧩 VPS ảo hoá › 🪟 Bản Windows:

| Bản | Tên máy mẫu | RAM tối thiểu |
|---|---|---|
| Windows Server 2012 R2 | `tpl-win2012r2` | 1 GB |
| Windows 10 LTSC 2021 | `tpl-win10ltsc` | 2 GB |
| Windows Server 2016 / 2019 / 2022 | `tpl-win2016` · `tpl-win2019` · `tpl-win2022` | 2 GB |

Dựng 1 máy mẫu = **ghép 1 file ISO rồi cài** (tự làm hết, như ISO CloudBlue PC):

**a. Ghép ISO máy mẫu** — trên máy Windows 10 / 11 có file ISO Windows, mở **Windows PowerShell (Admin)**, dán lệnh, Enter:

```
$d = "$env:TEMP\cb-iso-may-mau.ps1"; Remove-Item $d -Force -ErrorAction SilentlyContinue; curl.exe -fsSL -o $d "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/tao-iso-may-mau.ps1?t=$(Get-Random)"; if (-not ((Test-Path $d) -and (Select-String -Path $d -Pattern 'cloudblue-iso-may-mau' -SimpleMatch -Quiet))) { Write-Host 'Chua tai duoc - thu lai sau 1 phut' -ForegroundColor Red } else { Set-ExecutionPolicy -Scope Process Bypass -Force; & $d }
```

- Kéo thả file **ISO Windows** vào cửa sổ → Enter. Kéo thả **ISO virtio-win** (2012 R2: 0.1.240 · bản khác: 0.1.271) → Enter — hoặc bấm Enter luôn để lệnh tự tải đúng bản.
- ISO có nhiều bản (Standard / Datacenter / Core…): lệnh tự chọn bản **Standard có giao diện**, muốn bản khác thì gõ số.
- 10–20 phút → ra `CloudBlue-MayMau-win2012r2.iso` (ở gốc ổ còn nhiều chỗ nhất). Không chứa khoá bí mật nào.
- ISO này **xoá sạch ổ đĩa** máy cài nó — chỉ gắn vào máy ảo mẫu mới tạo.

**b. Cài máy mẫu trên Proxmox**
1. Đưa ISO lên: **local › ISO Images › Upload**.
2. **Create VM**: VM ID dưới 100000 (vd 9001), Name = tên máy mẫu ở bảng trên. OS: chọn ISO vừa ghép, Type *Microsoft Windows* đúng bản. System: *Qemu Agent* ✓ (BIOS để mặc định). Disk: **SCSI**, controller *VirtIO SCSI single*, **20 GB**, *Discard* ✓. CPU: 2 core, type *host*. RAM: 2048. Network: **VirtIO**. Không cần gắn thêm ổ CD driver.
3. **Start** → mở Console xem: máy tự chia ổ, cài Windows, tự khởi động lại 1–2 lần, tự đăng nhập tài khoản **VPS**; 20–40 phút sau hiện hộp **MAY MAU DA XONG**. (Máy UEFI/OVMF: thấy *Press any key to boot from CD* thì bấm 1 phím.)
4. Muốn thì cài thêm phần mềm / chỉnh tuỳ ý trong máy mẫu.
5. **Shutdown** → Hardware › CD/DVD Drive › *Do not use any media* → chuột phải › **Convert to template**.

Máy mẫu tự làm: driver VirtIO (ổ đĩa, mạng, cổng QEMU agent — **không cài VGA**), QEMU guest agent, bản vá Universal C Runtime (2012 R2), tài khoản **VPS** (Admin, không mật khẩu, tự đăng nhập), giờ Việt Nam, phần mềm CloudBlue PC (**chưa đăng ký**), khoá mọi tài khoản khác (mật khẩu ngẫu nhiên + tắt) để các VPS không chung mật khẩu quản trị. Nhật ký: `C:\CloudBluePC\logs\maymau.log`.

**Cách nhanh hơn — bảng điều khiển máy mẫu trên web** (SQL v57): chỉ cần làm bước **a** + đưa ISO lên Proxmox (local › ISO Images › Upload), rồi vào web › Quản trị › 🧩 VPS ảo hoá › 🪟 Bản Windows › **🧰 Bảng điều khiển máy mẫu**:
1. **➕ Dựng / sửa máy mẫu** → chọn máy chủ + bản Windows + file ISO → **Bắt đầu**: máy chủ tự tạo máy ảo tạm `cbmau-<số>` (số từ 99000), Windows tự cài (20–40 phút).
2. Xong hiện **Sẵn sàng** → **▶ Điều khiển** vào màn hình máy mẫu, cài thêm phần mềm / chỉnh tuỳ ý.
3. **💾 Lưu thành máy mẫu**: máy chủ tự xoá mã máy trong máy, tắt, gỡ ISO, đổi máy mẫu cũ thành `<tên>-cu` (giữ 1 bản dự phòng), đặt tên + chuyển thành máy mẫu. VPS đang chạy không bị ảnh hưởng.
4. Sau này muốn sửa: **➕ Dựng / sửa máy mẫu** → **✏️ Sửa máy mẫu đang có** (nhân bản máy mẫu ra máy ảo tạm) → chỉnh → Lưu. **✖ Huỷ** = xoá máy ảo tạm, máy mẫu cũ giữ nguyên.

Máy mẫu không bao giờ tự lên web (chưa có mã đăng ký). Mỗi VPS nhân ra nhận 1 vé đăng ký riêng → tự hiện trong "VPS ảo hoá của bạn" của đúng khách.
Thử: ⚙ Cài đặt › **Tạo VPS cho 1 tài khoản** (không trừ tiền) → cho chính bạn → vào ▶ Điều khiển xem có lên màn hình không.

## 6. Nhập giá + bật bán

- **💲 Gói & giá**: 8 cấu hình có sẵn (1-1 … 8-16, 20 GB) **chưa có giá** → bấm ✏️ Sửa từng gói nhập giá theo số ngày (mức 30 ngày = giá / tháng). Gói chưa có giá thì khách không thấy. Thêm / tắt gói tuỳ ý.
- **⚙ Cài đặt**: bật **Bán cho khách**; giữ dữ liệu bao nhiêu ngày khi hết hạn; số lần khách tự cài lại; chia tài nguyên máy chủ.
- Khách mua ở ô **🧩 VPS ảo hoá** trên trang chủ (ngay trên mục Sản phẩm): chọn gói → chọn Windows → số ngày → thanh toán. Máy chủ hết chỗ thì không trừ tiền.
