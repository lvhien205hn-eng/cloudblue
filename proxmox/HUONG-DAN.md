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
| Windows Server 2016 / 2019 / 2022 (dùng thử) | https://www.microsoft.com/en-us/evalcenter/download-windows-server-2016 · …-2019 · …-2022 | |
| Driver VirtIO (mọi bản trừ 2012 R2) | https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso | ổ đĩa + card mạng + QEMU guest agent |
| Driver VirtIO cho **2012 R2** | https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/ › thư mục **virtio-win-0.1.240-1** › `virtio-win-0.1.240.iso` | 0.1.240 là bản cuối còn hỗ trợ 2012 / 2012 R2 |

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

Dựng 1 máy mẫu:
1. **Create VM**: VM ID dưới 100000 (vd 9001), Name = tên máy mẫu ở bảng trên. OS: ISO Windows, Type *Microsoft Windows*. System: *Qemu Agent* ✓. Disk: **SCSI**, controller *VirtIO SCSI single*, **20 GB**, *Discard* ✓. CPU: 2 core, type *host*. RAM: 2048. Network: **VirtIO**.
2. Hardware › **Add › CD/DVD Drive** → ISO driver VirtIO (2012 R2 dùng bản 0.1.240).
3. Cài Windows: tới bước chọn ổ bấm **Load driver** → ổ VirtIO › `vioscsi\<bản>\amd64` (2k12R2 / w10 / 2k16 / 2k19 / 2k22).
4. Vào Windows: chạy `virtio-win-guest-tools.exe` trên ổ VirtIO (2012 R2: `virtio-win-gt-x64.msi` + `guest-agent\qemu-ga-x86_64.msi`) — cài driver mạng + **QEMU guest agent** (bắt buộc: máy chủ đưa vé đăng ký vào máy ảo qua đường này).
5. Cài phần mềm CloudBlue PC cho máy mẫu (**không** nhập mã đăng ký): lệnh 1 dòng đang hoàn thiện — có lệnh sẽ ghi vào đây.
6. Tắt máy mẫu → chuột phải › **Convert to template**.

Máy mẫu không bao giờ tự lên web (chưa có mã đăng ký). Mỗi VPS nhân ra nhận 1 vé đăng ký riêng → tự hiện trong "VPS ảo hoá của bạn" của đúng khách.
Thử: ⚙ Cài đặt › **Tạo VPS cho 1 tài khoản** (không trừ tiền) → cho chính bạn → vào ▶ Điều khiển xem có lên màn hình không.

## 6. Nhập giá + bật bán

- **💲 Gói & giá**: 8 cấu hình có sẵn (1-1 … 8-16, 20 GB) **chưa có giá** → bấm ✏️ Sửa từng gói nhập giá theo số ngày (mức 30 ngày = giá / tháng). Gói chưa có giá thì khách không thấy. Thêm / tắt gói tuỳ ý.
- **⚙ Cài đặt**: bật **Bán cho khách**; giữ dữ liệu bao nhiêu ngày khi hết hạn; số lần khách tự cài lại; chia tài nguyên máy chủ.
- Khách mua ở ô **🧩 VPS ảo hoá** trên trang chủ (ngay trên mục Sản phẩm): chọn gói → chọn Windows → số ngày → thanh toán. Máy chủ hết chỗ thì không trừ tiền.
