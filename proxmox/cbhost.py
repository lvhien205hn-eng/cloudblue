#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cbhost.py — CloudBlue · phần mềm chạy trên MÁY CHỦ PROXMOX VE cho "VPS ảo hoá" (SQL v56).
#   · Tự lên web (vm_host_hello) → hiện ở Quản trị › VPS ảo hoá › Máy chủ dạng "chờ duyệt" → admin bấm Duyệt.
#   · 10 giây / lần hỏi việc (vm_host_poll) bằng khoá CÔNG KHAI của web + mã riêng của máy này (sinh 1 lần, chỉ nằm trên máy, 0600).
#   · Mỗi VPS = 1 máy ảo nhân bản từ MÁY MẪU Windows (tên đặt ở web, vd tpl-win10-22h2) có sẵn phần mềm CloudBlue PC (chưa đăng ký):
#       tạo: qm clone → đặt CPU / RAM / ổ → bật → sinh VÉ 1 lần, báo dấu băm của vé lên web (web mở cửa đăng ký đúng dòng máy) →
#            ghi C:\CloudBluePC\seed.json {hw, ticket} vào máy ảo qua QEMU guest agent → agent trong máy tự đăng ký (pc_enroll)
#            → khách thấy máy trong web / app CloudBlue, bấm là vào màn hình (không IP, không mở cổng).
#       tắt / bật / khởi động cứng / cài lại (xoá máy ảo, nhân bản lại) / xoá — theo đúng trạng thái web muốn.
#   · BẢNG ĐIỀU KHIỂN MÁY MẪU (SQL v57): web gửi việc "dựng máy mẫu" (từ file ISO máy mẫu đã đưa lên Proxmox, hoặc nhân bản máy mẫu đang có
#     để sửa) → máy ảo tạm cbmau-<số> → Windows tự cài (ISO ghép bằng proxmox/tao-iso-may-mau.ps1) → đưa vé → agent đăng ký → admin
#     ▶ điều khiển trên web → "Lưu": xoá mã máy trong máy (identity / seed / rent = {}), tắt, gỡ ISO, đổi máy mẫu cũ thành <tên>-cu,
#     đặt tên <tên> + chuyển thành máy mẫu. "Huỷ": xoá máy ảo tạm. Báo danh sách file ISO trên máy chủ để admin chọn.
#   · KHÔNG chạy lệnh nào do web gửi xuống: chỉ các việc ghi sẵn ở đây, số / tên đều kiểm kỹ.
#   · TỰ CẬP NHẬT (chạy bằng dịch vụ cloudblue-cbhost): 1 giờ / lần xem bản trên GitHub của CloudBlue — khác bản đang chạy → kiểm biên dịch
#     được → thay file → thoát để dịch vụ tự bật lại bản mới (chỉ lúc không có máy ảo nào đang dựng / xoá). Tắt: "auto_update": false.
#   · TỰ SỬA MẠNG (26/11c, máy cài bằng ISO CloudBlue-Proxmox): lúc cài mà mạng không cấp IPv4 (DHCP không trả lời) thì bộ cài Proxmox chỉ đặt
#     IPv6 + DNS mặc định 192.168.100.1 (không có thật) → máy lên nhưng không gọi được web. Khi KHÔNG gọi được web, cbhost tự: bật dịch vụ
#     cloudblue-dhcp4 (dhclient xin IPv4 cho vmbr0 — ngay, mỗi lần bật máy, mạng chưa cấp thì tự thử lại mãi) và đặt lại máy chủ tên (DNS)
#     công cộng hợp với đường ra đang có (IPv4 / IPv6; lưu bản gốc resolv.conf.cb-goc). KHÔNG sửa /etc/network/interfaces của Proxmox
#     (ifupdown2 không cho 1 cầu vừa "inet dhcp" vừa "inet6 static"); cầu đã được đặt IPv4 thì dịch vụ tự gỡ. Tắt: "net_heal": false.
#     Máy cài bằng ISO còn BÁO RA MÀN HÌNH gắn vào máy chủ (tty1, chữ không dấu): "DA LEN WEB …" / "CHUA goi duoc web … IPv4 … IPv6 … DNS …"
#     → người ở chỗ máy chỉ cần chụp màn hình, không phải đăng nhập gõ lệnh.
#   · VPS NVMe LINUX (27/11a): máy mẫu tpl-ubuntu2404 = Ubuntu 24.04 + XFCE + CloudBlue (điều khiển trong web / app như Windows) + OpenClaw.
#     TỰ DỰNG (auto_tpl): tải ảnh Ubuntu cloud CHÍNH CHỦ (kiểm SHA256SUMS) → máy ảo cbmau-ubuntu2404 + cloud-init (ghi cb.json, chạy
#     proxmox/vm/linux-vm.sh) → xong (/var/lib/cloudblue/maymau.done) → dừng agent, xoá mã máy, tắt cloud-init, xoá machine-id → máy mẫu.
#     VPS Linux: vé đăng ký ghi vào /opt/cloudblue/seed.json; nới ổ / bằng growpart + resize2fs. Tắt: "linux_tpl": [].
#     27/11b: admin bật bản Ubuntu trên web (vm_images có tpl-ubuntu2404) → MỌI máy chủ (cả máy cài tay) tự dựng máy mẫu đó,
#     trừ máy ghi rõ "linux_tpl" trong cấu hình (vd [] = không bao giờ dựng).
#   · 27/11d: CÁCH LY VPS KHÁCH (nftables, bảng bridge cloudblue_vps): VPS không vào được CHÍNH máy chủ Proxmox (trang 8006, SSH…),
#     không nói chuyện với VPS khác, không vào trang quản trị modem (cổng 22/23/80/443/8080/8443 của cổng mạng mặc định) và cổng quản trị
#     của máy khác trong mạng nhà (SSH, SMB, RDP, WinRM, 8006). Internet, DNS, DHCP và đường điều khiển từ xa (máy chủ phát hình trong
#     mạng nhà, cổng khác) giữ nguyên. Tắt: "vps_iso": false.
#   · 27/11c: VPS Linux đặt mạng DHCP không gắn MAC máy mẫu (NET_LIN_SH) — trước đây VPS nhân ra có card mạng TẮT.
#   · 27/11e: KHO PROXY NHIỀU IP (cbpool, mã nguồn cbpool/): tự tải proxmox/cbpool-x86_64 (md5 ghim ở POOL_FILE), chạy dịch vụ cloudblue-pool
#     (cổng 8899, chỉ máy trong mạng nhà dùng được; VPS khách bị chặn sẵn bởi cách ly ở trên). Mỗi ô proxy 1 IPv6 riêng trong dải /64 của mạng
#     + IPv4 riêng khi có tài khoản PPPoE (admin gõ "cbpool ppp-set" trong Shell của Proxmox — mật khẩu chỉ nằm trên máy này).
#     Báo danh sách ô (IP:cổng:user:mật khẩu, IP đang ra) lên web trong số đo (px) → Quản trị › VPS ảo hoá › Máy chủ. Tắt: "pool": false.
#   · 27/11g: BÁN PROXY CHO KHÁCH (web: Proxy dân cư, share 1–5). Mỗi phút gọi px_host_sync (SQL v63) → ghi tài khoản khách vào
#     /etc/cloudblue/cbpool-users.json (600) cho cbpool 27.11c (khách vào được từ Internet qua cổng modem; ô IPv6 bán riêng; IPv4 = phiên
#     PPPoE đã bán) · báo lại IP đang ra của từng ô bán + khoá công khai của máy. Tài khoản PPPoE admin nhập trên web được TRÌNH DUYỆT mã hoá
#     bằng khoá công khai đó → cbhost chỉ chuyển chuỗi mã hoá cho "cbpool ppp-import" (giải bằng khoá riêng của máy, qua stdin).
#     Web chưa chạy SQL v63 → bỏ qua im lặng.
#   · 27/11f: kho proxy báo thêm kết quả TỰ DÒ PPPoE (cbpool 27.11b gửi gói dò PADI — không mật khẩu, không xin phiên — khi chưa có phiên
#     nào lên) → web hiện "modem có cho PPPoE từ mạng nhà đi qua không" mà admin khỏi vào Shell gõ cbpool ppp-test.
#     Tự cập nhật cbhost 15 phút / lần (trước 1 giờ) để bản sửa tới máy chủ nhanh hơn.
#   · 27/11c: VPS bị huỷ mà máy ảo ĐANG CHẠY → tắt hẳn rồi mới xoá (Proxmox không cho xoá máy đang chạy: trước đây thử xoá mãi 10 giây / lần
#     → 2 lượt xoá hỏng chiếm hết max_builds → VPS mới mua đứng "Đang tạo" mãi). Việc nhẹ (xoá) không còn tính vào max_builds.
#   Lệnh:  python3 cbhost.py run | status | once | update | net | version
#   Cấu hình: /etc/cloudblue/cbhost.conf (JSON): sb_url, sb_key (khoá công khai của web), storage (để trống = cùng ổ với máy mẫu),
#             full_clone (true = nhân bản đầy đủ, false = nhân bản liên kết — nhanh, cần ổ hỗ trợ), vmid_base (mặc định 100000), auto_update,
#             bridge (card mạng máy mẫu, mặc định vmbr0), tpl_vmid_from (số máy ảo tạm của máy mẫu, mặc định 99000)
CBHOST_VER = "27/11g"

import base64, hashlib, json, os, re, secrets, shutil, socket, subprocess, sys, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request

CONF_F = os.environ.get("CBHOST_CONF") or "/etc/cloudblue/cbhost.conf"
SECRET_F = os.environ.get("CBHOST_SECRET") or "/etc/cloudblue/cbhost.secret"
STATE_F = os.environ.get("CBHOST_STATE") or "/var/lib/cloudblue/cbhost-state.json"
QM = os.environ.get("CBHOST_QM") or "qm"
PVESH = os.environ.get("CBHOST_PVESH") or "pvesh"
PVESM = os.environ.get("CBHOST_PVESM") or "pvesm"
NFT = os.environ.get("CBHOST_NFT") or "nft"
ISO_TABLE = "cloudblue_vps"
ISO_TCP_GW = (22, 23, 80, 443, 8080, 8443)                    # trang quản trị modem / router (cổng mạng mặc định)
ISO_TCP_LAN = (22, 139, 445, 3389, 5985, 5986, 8006)          # quản trị máy khác trong mạng nhà: SSH, SMB, RDP, WinRM, Proxmox
ISO_LAN = "10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10"
ISO_EVERY = 600                                               # đặt lại luật mỗi 10 phút dù không đổi (máy chủ khởi động lại / ai xoá luật)
DEFAULTS = {"sb_url": "https://nprftgodswlpzomcttal.supabase.co", "sb_key": "sb_publishable_qfNcnOMv70nq5LIlYXDJzg_UtdWHVze",
            "storage": "", "full_clone": True, "vmid_base": 100000, "seed_path": "C:\\CloudBluePC\\seed.json", "max_builds": 2, "auto_update": True,
            "bridge": "vmbr0", "tpl_vmid_from": 99000, "auto_tpl": False, "host_name": "", "net_heal": None, "linux_tpl": None, "vps_iso": None,
            "pool": None}
UPD_URL = os.environ.get("CBHOST_UPD_URL") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/cbhost.py"   # chỉ nhận bản từ kho này
UPD_EVERY_S = 900                                               # 27/11f · 15 phút / lần xem bản mới (trước 1 giờ)
RX_TPL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,40}$")
RX_HW = re.compile(r"^[0-9a-f]{64}$")
RX_STORE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}$")
RX_ISO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}:iso/[A-Za-z0-9][A-Za-z0-9_.+-]{0,120}\.iso$")
RX_BRIDGE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,14}$")
ISO_EVERY_S = 60                # danh sách file ISO trên máy chủ: 1 phút đọc lại 1 lần
RX_AUTO_ISO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}:iso/CloudBlue-MayMau-([a-z0-9]{3,24})\.iso$")    # ISO máy mẫu do tao-iso-may-mau.ps1 ghép
RX_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
AUTO_DONE_F = "C:\\CloudBluePC\\vm\\maymau.done"      # maymau.ps1 ghi file này khi máy mẫu cài xong
AUTO_WAIT_S = 3 * 3600          # tự dựng máy mẫu: Windows tự cài tối đa 3 giờ
AUTO_TRIES = 2                  # tự dựng máy mẫu: thử tối đa 2 lần / bản
AUTO_CHK_S = 45                 # tự dựng máy mẫu: hỏi máy ảo "cài xong chưa" 45 giây / lần
RETRY_S = 60                    # việc lỗi → 1 phút sau thử lại
# 26/11e · web v59: khách nâng cấp vCPU / RAM / ổ (hoặc mua kèm ổ lớn hơn máy mẫu). Nới ổ ở Proxmox xong còn phải NỚI Ổ C TRONG WINDOWS — lệnh cố định dưới đây,
# chạy qua QEMU guest agent (viết dạng -EncodedCommand để không vướng dấu nháy). In ra cỡ ổ C (GB) sau khi nới.
GROW_PS = ("$ErrorActionPreference='Stop'; Update-HostStorageCache; $m=(Get-PartitionSupportedSize -DriveLetter C).SizeMax; $p=(Get-Partition -DriveLetter C).Size; "
           "if($m-$p -gt 104857600){Resize-Partition -DriveLetter C -Size $m}; [math]::Floor((Get-Partition -DriveLetter C).Size/1073741824)")
GROW_ARGS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", base64.b64encode(GROW_PS.encode("utf-16-le")).decode("ascii")]
GROW_EVERY_S = 20               # nới ổ C trong Windows: thử lại 20 giây / lần (Windows chưa lên xong thì chưa trả lời)
GROW_TRIES = 6                  # lệnh chạy được mà ổ C vẫn chưa đủ cỡ: thử tối đa 6 lần rồi thôi (khách tự nới bằng Disk Management)
GROW_MAX_S = 30 * 60            # Windows mãi không trả lời (không có QEMU guest agent): 30 phút thì thôi
# 27/11a · VPS NVMe LINUX — máy mẫu tự dựng từ ảnh cloud chính chủ (chỉ tải đúng file có trong SHA256SUMS của nhà phát hành)
LINUX_TPLS = {"ubuntu2404": {"name": "Ubuntu 24.04 + OpenClaw", "base": "https://cloud-images.ubuntu.com/releases/noble/release/",
                             "file": "ubuntu-24.04-server-cloudimg-amd64.img"}}
IMG_DIR = os.environ.get("CBHOST_IMG_DIR") or "/var/lib/cloudblue/img"
SNIP_DIR = os.environ.get("CBHOST_SNIP_DIR") or "/var/lib/vz/snippets"            # ổ "local" của Proxmox, loại nội dung snippets
LIN_BOOT_URL = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/vm/linux-vm.sh"
LIN_BASE = "/opt/cloudblue"
LIN_DONE_F = "/var/lib/cloudblue/maymau.done"
LIN_FAIL_F = "/var/lib/cloudblue/maymau.loi"
LIN_WAIT_S = 2 * 3600           # dựng máy mẫu Linux (cài XFCE + OpenClaw, có mạng): tối đa 2 giờ
LIN_SEAL_SH = ("systemctl stop cloudblue.service; touch /etc/cloud/cloud-init.disabled; cloud-init clean --logs >/dev/null 2>&1; NETFIX "
               "truncate -s 0 /etc/machine-id; rm -f /var/lib/dbus/machine-id /var/lib/cloudblue/maymau.done /opt/cloudblue/logs/*; sync")
# 27/11c · MẠNG VPS LINUX: cloud-init (lúc dựng máy mẫu) ghi netplan GẮN VỚI ĐỊA CHỈ MAC của máy mẫu → VPS nhân ra có MAC mới
# không nhận cấu hình → card mạng tắt, agent không đăng ký được ("Đang tạo" mãi). Lệnh cố định: bỏ file netplan có macaddress,
# đặt 1 cấu hình DHCP cho mọi card "en*", tắt phần mạng của cloud-init, netplan apply. Chạy lại bao nhiêu lần cũng được.
NET_LIN_SH = ("D=/etc/netplan; mkdir -p $D; for f in $D/*.yaml; do [ -f \"$f\" ] && grep -qi macaddress \"$f\" && rm -f \"$f\"; done; "
              "[ -f $D/60-cloudblue.yaml ] || printf 'network:\\n  version: 2\\n  ethernets:\\n    cbnet:\\n      match:\\n        name: \"en*\"\\n"
              "      dhcp4: true\\n      dhcp6: true\\n' > $D/60-cloudblue.yaml; chmod 600 $D/60-cloudblue.yaml; "
              "mkdir -p /etc/cloud/cloud.cfg.d; printf 'network: {config: disabled}\\n' > /etc/cloud/cloud.cfg.d/99-cloudblue-net.cfg; ")
NET_LIN_ARGS = ["sh", "-c", NET_LIN_SH + "netplan apply >/dev/null 2>&1; ip -4 -br addr | grep -c UP"]
LIN_SEAL_SH = LIN_SEAL_SH.replace("NETFIX ", NET_LIN_SH)        # 27/11c: máy mẫu mới lưu sẵn mạng không gắn MAC
GROW_LIN_SH = ('R=$(findmnt -no SOURCE /); P=$(cat /sys/class/block/${R#/dev/}/partition); K=/dev/$(lsblk -no PKNAME "$R" | head -1); '
               'growpart "$K" "$P" >/dev/null 2>&1; resize2fs "$R" >/dev/null 2>&1 || xfs_growfs / >/dev/null 2>&1; df -BG --output=size / | tail -1 | tr -dc 0-9')
GROW_LIN_ARGS = ["sh", "-c", GROW_LIN_SH]


def is_linux_tpl(tpl):
    """Máy mẫu Linux (tên tpl-ubuntu… / tpl-debian… …) — đường dẫn trong máy, cách dừng agent, cách nới ổ khác Windows."""
    return str(tpl or "")[4:].startswith(("ubuntu", "debian", "alma", "rocky", "linux"))


def http_get(url, limit=4 << 20):
    req = urllib.request.Request(url, headers={"User-Agent": "CloudBlue-cbhost/" + CBHOST_VER})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read(limit)


def http_save(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "CloudBlue-cbhost/" + CBHOST_VER})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f: shutil.copyfileobj(r, f, 1 << 20)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
USB_MNT = os.environ.get("CBHOST_USB_MNT") or "/run/cloudblue-usb"            # chỗ gắn tạm (chỉ đọc) USB có ISO máy mẫu
ISO_DIR = os.environ.get("CBHOST_ISO_DIR") or "/var/lib/vz/template/iso"      # kho ISO "local" của Proxmox
NAP_PY = os.environ.get("CBHOST_NAP_PY") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "cb_nap.py")
NAP_CONF_F = os.environ.get("CBHOST_NAP_CONF") or "/etc/cloudblue/nap.json"   # kho của CHÍNH USB cài máy này (dịch vụ cloudblue-nap lo)
RX_MAU_F = re.compile(r"^CloudBlue-MayMau-[a-z0-9]{3,24}\.iso$")
USB_FS = {"exfat": ("exfat", "ro"), "vfat": ("vfat", "ro"), "ntfs": ("ntfs3", "ro"), "ext4": ("ext4", "ro,noload"), "ext3": ("ext3", "ro,noload"), "ext2": ("ext2", "ro")}
USB_EVERY_S = 20                # xem có USB mới cắm: 20 giây / lần
USB_AGAIN_S = 600               # USB đã xem xong (đủ / không có gì): 10 phút sau mới xem lại (rút ra cắm lại = xem ngay)
MAU_MIN = 300 * 2**20           # file ISO máy mẫu thật luôn lớn hơn mức này (USB thường: file nhỏ hơn thì bỏ qua)
KHO_MAGIC = b"CBKHO1\n"
NAP_DONE_F = os.environ.get("CBHOST_NAP_DONE") or "/var/lib/cloudblue/nap-xong.json"
KHO_HDR = 16384
RESOLV_F = os.environ.get("CBHOST_RESOLV") or "/etc/resolv.conf"
IFACES_F = os.environ.get("CBHOST_IFACES") or "/etc/network/interfaces"
TTY_F = os.environ.get("CBHOST_TTY") or "/dev/tty1"            # màn hình gắn vào máy chủ
DHCP_UNIT = "cloudblue-dhcp4.service"
DHCP_UNIT_F = os.environ.get("CBHOST_DHCP_UNIT") or "/etc/systemd/system/" + DHCP_UNIT
DHCP_UNIT_TXT = """[Unit]
Description=CloudBlue - xin IPv4 qua DHCP cho %(br)s (luc cai Proxmox, mang khong cap IPv4)
After=network.target networking.service
ConditionPathExists=/sys/class/net/%(br)s

[Service]
ExecStart=%(dh)s -4 -d -pf /run/dhclient.%(br)s.pid -lf /var/lib/dhcp/dhclient.%(br)s.leases %(br)s
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
"""
DNS4, DNS6 = ("8.8.8.8", "1.1.1.1"), ("2001:4860:4860::8888", "2606:4700:4700::1111")
DNS_BOGUS = ("192.168.100.1",)  # DNS mặc định bộ cài Proxmox tự điền khi lúc cài không xin được gì từ mạng
NET_FAILS = 3                   # gọi web lỗi MẠNG liên tiếp bấy nhiêu vòng (≈ 30 giây) → thử tự sửa mạng
NET_EVERY_S = (120, 900)        # tự sửa mạng: 2 phút / lần trong 10 lần đầu, sau đó 15 phút / lần
DHCP_WAIT_S = 2                 # sau khi bật dịch vụ xin DHCP: 2 giây xem 1 lần (tối đa 15 lần) đã có IPv4 chưa


def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


def load_json(p, dflt=None):
    try:
        with open(p, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else (dflt if dflt is not None else {})
    except Exception:
        return dflt if dflt is not None else {}


def save_json(p, d, mode=0o600):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False)
    os.chmod(tmp, mode); os.replace(tmp, p)


def conf():
    c = dict(DEFAULTS); c.update({k: v for k, v in load_json(CONF_F).items() if k in DEFAULTS})
    if not isinstance(c.get("storage"), str) or (c["storage"] and not RX_STORE.match(c["storage"])): c["storage"] = ""
    try: c["vmid_base"] = max(1000, min(900000000, int(c.get("vmid_base") or 100000)))
    except (TypeError, ValueError): c["vmid_base"] = 100000
    try: c["max_builds"] = max(1, min(8, int(c.get("max_builds") or 2)))
    except (TypeError, ValueError): c["max_builds"] = 2
    c["full_clone"] = c.get("full_clone") is not False
    c["auto_update"] = c.get("auto_update") is not False
    if not isinstance(c.get("bridge"), str) or not RX_BRIDGE.match(c["bridge"]): c["bridge"] = "vmbr0"
    try: c["tpl_vmid_from"] = max(100, min(900000000, int(c.get("tpl_vmid_from") or 99000)))
    except (TypeError, ValueError): c["tpl_vmid_from"] = 99000
    c["auto_tpl"] = c.get("auto_tpl") is True
    c["vps_iso"] = c.get("vps_iso") is not False                  # 27/11d · cách ly VPS khách (mặc định bật)
    c["pool"] = c.get("pool") is not False                        # 27/11e · kho proxy nhiều IP (mặc định bật)
    c["net_heal"] = c["auto_tpl"] if c.get("net_heal") is None else c.get("net_heal") is True      # mặc định: bật trên máy cài bằng ISO CloudBlue-Proxmox
    lt = c.get("linux_tpl")                                                                       # 27/11a · máy mẫu Linux tự dựng (mặc định: máy cài bằng ISO)
    c["linux_tpl"] = (["ubuntu2404"] if c["auto_tpl"] else []) if lt is None else [t for t in lt if t in LINUX_TPLS] if isinstance(lt, list) else []
    c["linux_web"] = lt is None                                                                   # 27/11b · không ghi rõ → web bật bản Linux nào thì dựng bản đó
    if not isinstance(c.get("host_name"), str) or not RX_HOSTNAME.match(c["host_name"]): c["host_name"] = ""
    return c


def secret():
    """Mã riêng của máy chủ này: sinh 1 lần, chỉ nằm ở /etc/cloudblue/cbhost.secret (0600). Web chỉ giữ dấu băm.
       2 tiến trình cùng sinh lần đầu (dịch vụ + lệnh status) → chỉ 1 mã được ghi, cả 2 cùng dùng mã đó."""
    os.makedirs(os.path.dirname(SECRET_F) or ".", exist_ok=True)
    for _ in range(5):
        try:
            s = open(SECRET_F, encoding="utf-8").read().strip()
            if re.fullmatch(r"[0-9a-f]{64}", s): return s
            bad = True                                              # file hỏng → thay
        except FileNotFoundError:
            bad = False
        tmp = "%s.%d.tmp" % (SECRET_F, os.getpid())
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f: f.write(secrets.token_hex(32))
        try:
            if bad: os.replace(tmp, SECRET_F)
            else: os.link(tmp, SECRET_F)                            # chưa có → tạo; đã có (tiến trình kia vừa tạo) → lỗi, đọc lại
        except FileExistsError:
            pass
        finally:
            try: os.remove(tmp)
            except OSError: pass
    raise RuntimeError("không ghi được mã riêng của máy chủ: " + SECRET_F)


def iso_ruleset(ifaces, gw):
    """27/11d · luật nftables cách ly VPS (họ bridge: lọc ngay trên cầu vmbr — không cần br_netfilter). Thay cả bảng trong 1 lần (nguyên tử)."""
    els = ", ".join('"%s"' % i for i in sorted(ifaces) if re.fullmatch(r"(tap|fwpr)\d{1,9}[ip]\d{1,2}", i))
    out = ["table bridge %s" % ISO_TABLE, "delete table bridge %s" % ISO_TABLE, "table bridge %s {" % ISO_TABLE,
           "  set vps { type ifname;%s }" % (" elements = { %s };" % els if els else ""),
           "  chain input { type filter hook input priority -200; policy accept;",
           "    iifname @vps drop",                                         # VPS → CHÍNH máy chủ Proxmox: chặn hết
           "  }",
           "  chain forward { type filter hook forward priority -200; policy accept;",
           "    iifname @vps oifname @vps drop"]                            # VPS ↔ VPS
    if gw and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", gw):
        out.append("    iifname @vps ip daddr %s tcp dport { %s } drop" % (gw, ", ".join(map(str, ISO_TCP_GW))))
    out.append("    iifname @vps ip daddr { %s } tcp dport { %s } drop" % (ISO_LAN, ", ".join(map(str, ISO_TCP_LAN))))
    out += ["  }", "}"]
    return "\n".join(out) + "\n"


def default_gw():
    rc, out = run(["ip", "-4", "route", "show", "default"], 10)
    m = re.search(r"default via (\d{1,3}(?:\.\d{1,3}){3})", out or "") if rc == 0 else None
    return m.group(1) if m else ""


def run_in(cmd, data, timeout=60):
    """Như run() nhưng đưa data vào stdin."""
    try:
        r = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "quá giờ chờ: " + " ".join(cmd[:3])
    except OSError as e:
        return 127, str(e)


def run(cmd, timeout=900):
    """Chạy 1 lệnh Proxmox (danh sách tham số, KHÔNG qua shell) → (mã thoát, chữ in ra)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "quá giờ chờ: " + " ".join(cmd[:3])
    except OSError as e:
        return 127, str(e)


# ---------------------------------------------------------------- gọi web (Supabase RPC, khoá công khai)
class Web:
    def __init__(self, c):
        self.url, self.key, self.err = c["sb_url"].rstrip("/"), c["sb_key"], ""

    def rpc(self, fn, body, timeout=25):
        req = urllib.request.Request(self.url + "/rest/v1/rpc/" + fn, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"apikey": self.key, "Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                                              "User-Agent": "CloudBlue-cbhost/" + CBHOST_VER})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: d = json.loads(r.read().decode("utf-8") or "null")
            self.err = ""
            return d
        except urllib.error.HTTPError as e:
            try: self.err = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
            except Exception: self.err = "HTTP %s" % e.code
        except Exception as e:
            self.err = str(e)[:200]
        return None


# ---------------------------------------------------------------- Proxmox
class Pve:
    def __init__(self, c):
        self.c, self.node = c, socket.gethostname().split(".")[0]

    def vms(self):
        """{vmid: {name, status, template}} của node này (pvesh /cluster/resources — 1 lần gọi, JSON)."""
        rc, out = run([PVESH, "get", "/cluster/resources", "--type", "vm", "--output-format", "json"], 60)
        if rc != 0: raise RuntimeError("không đọc được danh sách máy ảo: " + out[-200:])
        res = {}
        for x in json.loads(out or "[]"):
            if not isinstance(x, dict) or x.get("type") != "qemu" or (x.get("node") and x.get("node") != self.node): continue
            try: vid = int(x.get("vmid"))
            except (TypeError, ValueError): continue
            res[vid] = {"name": str(x.get("name") or ""), "status": str(x.get("status") or ""), "template": bool(x.get("template"))}
        return res

    def config(self, vmid):
        rc, out = run([QM, "config", str(int(vmid))], 60)
        return out if rc == 0 else ""

    def boot_disk(self, vmid):
        """(tên ổ, cỡ GB) ổ hệ thống của máy ảo (bootdisk / boot order / ổ đầu tiên)."""
        cfg = self.config(vmid); disks = {}; order = []
        for ln in cfg.splitlines():
            m = re.match(r"^((?:scsi|virtio|sata|ide)\d+):\s*([^,\s]+)(.*)$", ln.strip())
            if m and "media=cdrom" not in m.group(3):
                sz = re.search(r"size=(\d+(?:\.\d+)?)([KMGT])", m.group(3))
                gb = 0.0
                if sz: gb = float(sz.group(1)) * {"K": 1 / 1048576, "M": 1 / 1024, "G": 1, "T": 1024}[sz.group(2)]
                disks[m.group(1)] = gb
            m2 = re.match(r"^boot:\s*order=(.+)$", ln.strip()) or re.match(r"^bootdisk:\s*(\S+)$", ln.strip())
            if m2: order = [x for x in re.split(r"[;,]", m2.group(1)) if x]
        for k in order:
            if k in disks: return k, disks[k]
        return (sorted(disks)[0], disks[sorted(disks)[0]]) if disks else (None, 0.0)

    def clone(self, tpl_id, vmid, name):
        base = [QM, "clone", str(int(tpl_id)), str(int(vmid)), "--name", name]
        if self.c["full_clone"]:
            cmd = base + ["--full", "1"] + (["--storage", self.c["storage"]] if self.c["storage"] else [])
            return run(cmd, 3600)
        rc, out = run(base + ["--full", "0"], 600)                 # liên kết: vài giây; ổ không hỗ trợ → nhân bản đầy đủ
        if rc == 0: return rc, out
        log("nhân bản liên kết không được (%s) → nhân bản đầy đủ" % out[-120:])
        return run(base + ["--full", "1"] + (["--storage", self.c["storage"]] if self.c["storage"] else []), 3600)

    def hw_now(self, vmid):
        """(vCPU, RAM MB) máy ảo ĐANG CHẠY với (qm config --current: không tính phần đổi còn chờ lần bật nguội kế). Không đọc được → (None, None)."""
        rc, out = run([QM, "config", str(int(vmid)), "--current", "1"], 60)
        if rc != 0: return None, None
        c = re.search(r"^cores:\s*(\d+)\s*$", out, re.M); m = re.search(r"^memory:\s*(?:current=)?(\d+)", out, re.M)
        return (int(c.group(1)) if c else None), (int(m.group(1)) if m else None)

    def set_hw(self, vmid, cores, ram_mb):
        return run([QM, "set", str(int(vmid)), "--cores", str(int(cores)), "--sockets", "1", "--memory", str(int(ram_mb)), "--balloon", "0"], 120)

    def grow_disk(self, vmid, disk_gb):
        """Nới ổ hệ thống lên disk_gb (không bao giờ thu nhỏ) → (mã lỗi, lời báo, có nới không)."""
        dk, gb = self.boot_disk(vmid)
        if not dk or disk_gb <= gb + 0.5: return 0, "", False
        rc, out = run([QM, "resize", str(int(vmid)), dk, "%dG" % int(disk_gb)], 600)
        return rc, out, rc == 0

    def setup(self, vmid, cores, ram_mb, disk_gb, hw):
        rc, out = run([QM, "set", str(vmid), "--cores", str(cores), "--sockets", "1", "--memory", str(ram_mb), "--balloon", "0",
                       "--onboot", "1", "--agent", "enabled=1", "--tags", "cloudblue", "--smbios1", "uuid=" + hw_uuid(hw)], 120)
        if rc != 0: return rc, out
        dk, gb = self.boot_disk(vmid)
        if dk and disk_gb > gb + 0.5:
            rc, out = run([QM, "resize", str(vmid), dk, "%dG" % int(disk_gb)], 600)
            if rc != 0: return rc, "nới ổ lỗi: " + out
        return 0, ""

    def start(self, vmid):
        """Bật máy ảo. Máy ĐÃ đang chạy (vd vừa có lượt khác bật) = được, không báo lỗi (27/11a: khách mua VPS thấy 'bật máy lỗi: … already running')."""
        rc, out = run([QM, "start", str(vmid)], 180)
        if rc != 0 and "already running" in (out or ""): return 0, out
        return rc, out
    def stop(self, vmid): return run([QM, "stop", str(vmid)], 180)
    def shutdown(self, vmid): return run([QM, "shutdown", str(vmid), "--timeout", "90", "--forceStop", "1"], 240)
    def reset(self, vmid): return run([QM, "reset", str(vmid)], 120)
    def destroy(self, vmid):
        """Xoá hẳn máy ảo. 27/11c: Proxmox KHÔNG xoá máy đang chạy ("is running - destroy failed") → tắt hẳn trước
           (dùng cho VPS đã huỷ, cài lại, huỷ máy ảo tạm của máy mẫu — dữ liệu trong máy đó đằng nào cũng bỏ)."""
        vm = self.vms().get(int(vmid))
        if vm and vm["status"] == "running":
            rc, out = self.stop(vmid)
            if rc != 0: return rc, "tắt máy để xoá lỗi: " + (out or "")
        return run([QM, "destroy", str(vmid), "--purge", "1", "--destroy-unreferenced-disks", "1"], 900)
    def ga_ping(self, vmid): return run([QM, "guest", "cmd", str(vmid), "ping"], 30)[0] == 0

    def ga_read(self, vmid, path):
        """Đọc 1 file trong máy ảo qua guest agent → nội dung (None = không có file / không đọc được)."""
        rc, out = run([PVESH, "get", "/nodes/%s/qemu/%d/agent/file-read" % (self.node, int(vmid)), "--file", path, "--output-format", "json"], 60)
        if rc != 0: return None
        try: return str((json.loads(out or "{}") or {}).get("content") or "")
        except Exception: return None

    def ga_write(self, vmid, path, content):
        return run([PVESH, "create", "/nodes/%s/qemu/%d/agent/file-write" % (self.node, int(vmid)), "--file", path, "--content", content], 60)

    def ga_exec(self, vmid, args, timeout=30):
        """Chạy 1 lệnh CỐ ĐỊNH (ghi sẵn trong file này) trong máy ảo qua guest agent."""
        return run([QM, "guest", "exec", str(int(vmid)), "--timeout", str(int(timeout)), "--"] + list(args), int(timeout) + 60)

    # ---- máy mẫu
    def isos(self):
        """[{volid, size}] file ISO trên các ổ chứa ISO của node này (tối đa 60 file)."""
        res = []
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--content", "iso", "--output-format", "json"], 60)
        try: sts = [x for x in json.loads(out or "[]") if isinstance(x, dict) and x.get("active") and "iso" in str(x.get("content") or "")] if rc == 0 else []
        except Exception: sts = []
        for st in sts:
            name = str(st.get("storage") or "")
            if not RX_STORE.match(name): continue
            rc, out = run([PVESH, "get", "/nodes/%s/storage/%s/content" % (self.node, name), "--content", "iso", "--output-format", "json"], 60)
            try: items = json.loads(out or "[]") if rc == 0 else []
            except Exception: items = []
            for x in items if isinstance(items, list) else []:
                v = str((x or {}).get("volid") or "")
                if RX_ISO.match(v) and len(res) < 60:
                    try: sz = int((x or {}).get("size") or 0)
                    except (TypeError, ValueError): sz = 0
                    res.append({"volid": v, "size": sz})
        return sorted(res, key=lambda x: x["volid"])

    def image_storage(self):
        """Ổ để tạo ổ đĩa máy mẫu: cấu hình storage → local-lvm → local-zfs → ổ chứa máy ảo đầu tiên đang chạy."""
        if self.c["storage"]: return self.c["storage"]
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--content", "images", "--output-format", "json"], 60)
        try: names = [str(x.get("storage")) for x in json.loads(out or "[]") if isinstance(x, dict) and x.get("active")
                      and "images" in str(x.get("content") or "") and RX_STORE.match(str(x.get("storage") or ""))] if rc == 0 else []
        except Exception: names = []
        for pref in ("local-lvm", "local-zfs"):
            if pref in names: return pref
        return names[0] if names else ""

    def create_tpl_vm(self, vmid, name, it, storage):
        """Máy ảo trống + gắn ISO máy mẫu: BIOS thường (SeaBIOS), ổ SCSI VirtIO, card mạng VirtIO, có QEMU agent, màn hình thường (không VGA riêng)."""
        t = str(it["tpl"]).lower()
        ost = "win8" if "2012" in t else ("win11" if ("2022" in t or "2025" in t) else "win10")
        return run([QM, "create", str(int(vmid)), "--name", name, "--ostype", ost, "--machine", "pc", "--bios", "seabios",
                    "--scsihw", "virtio-scsi-single", "--scsi0", "%s:%d,discard=on,iothread=1" % (storage, int(it["disk_gb"])),
                    "--ide2", "%s,media=cdrom" % it["iso"], "--boot", "order=scsi0;ide2", "--net0", "virtio,bridge=%s" % self.c["bridge"],
                    "--cores", str(int(it["cores"])), "--sockets", "1", "--cpu", "host", "--memory", str(int(it["ram_mb"])), "--balloon", "0",
                    "--agent", "enabled=1", "--onboot", "0", "--vga", "std", "--tags", "cloudblue-mau", "--smbios1", "uuid=" + hw_uuid(it["hw"])], 600)

    def setup_tpl_vm(self, vmid, it):
        return run([QM, "set", str(int(vmid)), "--cores", str(int(it["cores"])), "--sockets", "1", "--memory", str(int(it["ram_mb"])), "--balloon", "0",
                    "--onboot", "0", "--agent", "enabled=1", "--tags", "cloudblue-mau", "--smbios1", "uuid=" + hw_uuid(it["hw"])], 120)

    def cdroms(self, vmid):
        """Ổ CD đang gắn file (ide2 / sata0 …) → để gỡ ISO trước khi thành máy mẫu."""
        res = []
        for ln in self.config(vmid).splitlines():
            m = re.match(r"^((?:ide|sata|scsi)\d+):\s*([^,\s]+)(.*)$", ln.strip())
            if m and "media=cdrom" in m.group(3) and m.group(2) != "none": res.append(m.group(1))
        return res

    def set_name(self, vmid, name): return run([QM, "set", str(int(vmid)), "--name", name], 120)
    def drop_ci(self, vmid): return run([QM, "set", str(int(vmid)), "--delete", "ide2,cicustom,ipconfig0"], 120)   # 27/11a · gỡ ổ cloud-init của máy mẫu Linux

    def snippets_ready(self):
        """Ổ "local" nhận loại nội dung snippets (file cloud-init riêng) — chưa thì bật thêm (giữ các loại đang có)."""
        rc, out = run([PVESH, "get", "/storage/local", "--output-format", "json"], 60)
        try: cur = [x for x in str((json.loads(out or "{}") or {}).get("content") or "").split(",") if x] if rc == 0 else []
        except ValueError: cur = []
        if "snippets" in cur: return 0, ""
        return run([PVESM, "set", "local", "--content", ",".join(cur + ["snippets"])], 60)

    def create_lin_vm(self, vmid, name, storage, img, hw, snip):
        """27/11a · máy ảo dựng máy mẫu Linux: ổ = ảnh cloud vừa tải (import-from), nới 20 GB, ổ cloud-init + file cloud-init riêng (snippets),
        4 nhân / 4 GB cho cài nhanh (VPS nhân ra đặt lại theo gói), có QEMU agent, màn hình thường."""
        steps = [[QM, "create", str(int(vmid)), "--name", name, "--ostype", "l26", "--machine", "pc", "--bios", "seabios", "--scsihw", "virtio-scsi-single",
                  "--net0", "virtio,bridge=%s" % self.c["bridge"], "--cores", "4", "--sockets", "1", "--cpu", "host", "--memory", "4096", "--balloon", "0",
                  "--agent", "enabled=1", "--onboot", "0", "--vga", "std", "--serial0", "socket", "--tags", "cloudblue-mau", "--smbios1", "uuid=" + hw_uuid(hw)],
                 [QM, "set", str(int(vmid)), "--scsi0", "%s:0,import-from=%s,discard=on,iothread=1" % (storage, img)],
                 [QM, "resize", str(int(vmid)), "scsi0", "20G"],
                 [QM, "set", str(int(vmid)), "--ide2", "%s:cloudinit" % storage, "--boot", "order=scsi0", "--cicustom", "user=local:snippets/" + snip, "--ipconfig0", "ip=dhcp"]]
        for st in steps:
            rc, out = run(st, 1800)
            if rc != 0: return rc, out
        return 0, ""
    def eject(self, vmid, dev): return run([QM, "set", str(int(vmid)), "--" + dev, "none,media=cdrom"], 120)
    def make_template(self, vmid): return run([QM, "template", str(int(vmid))], 600)

    def info(self):
        def first(cmd, rx, dflt=""):
            rc, out = run(cmd, 30)
            m = re.search(rx, out or "", re.M) if rc == 0 else None
            return m.group(1).strip() if m else dflt
        mem = meminfo()
        return {"host": self.c.get("host_name") or self.node, "pve": first(["pveversion"], r"pve-manager/([0-9.]+)"), "cpu": first(["lscpu"], r"^Model name:\s*(.+)$")[:80],
                "threads": os.cpu_count() or 1, "ram_mb": int(mem.get("MemTotal", 0) / 1024), "disk_gb": self.disk_total(),
                "kvm": os.path.exists("/dev/kvm"), "ver": CBHOST_VER, "lan_ip": lan_ip(), "ip6_only": ip6_only()}

    def disk_total(self):
        """Tổng GB các ổ chứa máy ảo (images) đang chạy — hoặc riêng ổ đặt ở cấu hình."""
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--output-format", "json"], 60)
        tot = 0.0
        try:
            for s in json.loads(out or "[]") if rc == 0 else []:
                if not isinstance(s, dict) or not s.get("active") or "images" not in str(s.get("content") or ""): continue
                if self.c["storage"] and s.get("storage") != self.c["storage"]: continue
                tot += float(s.get("total") or 0) / 1073741824
        except Exception:
            pass
        return int(tot)


def hw_uuid(hw):
    """Mã máy (SMBIOS) riêng cho từng máy ảo, suy từ dấu máy web cấp."""
    return hw[:8] + "-" + hw[8:12] + "-4" + hw[13:16] + "-a" + hw[17:20] + "-" + hw[20:32]


def has_identity(txt):
    """identity.json trong máy ảo có mã máy thật (id + token)? ("{}" do lúc lưu máy mẫu xoá = không có)."""
    try: d = json.loads(txt or "")
    except Exception: return bool((txt or "").strip())
    return isinstance(d, dict) and bool(d.get("id")) and bool(d.get("token"))


def meminfo():
    d = {}
    try:
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":", 1); d[k] = float(v.split()[0])
    except Exception:
        pass
    return d


def lan_ip():
    """Địa chỉ của máy chủ trên đường ra Internet: IPv4 nếu có, không thì IPv6 (máy chỉ có IPv6). Không gửi gói nào (UDP connect chỉ chọn đường)."""
    for fam, dst in ((socket.AF_INET, DNS4[1]), (socket.AF_INET6, DNS6[1])):
        try:
            s = socket.socket(fam, socket.SOCK_DGRAM); s.connect((dst, 53)); ip = s.getsockname()[0]; s.close()
            if ip and not ip.lower().startswith(("fe80:", "::", "0.", "127.")): return ip
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------- tự sửa mạng (26/11c) — xem phần đầu file
def default_routes():
    """→ (có đường ra Internet IPv4, có đường ra Internet IPv6)"""
    def has(fam):
        rc, out = run(["ip", fam, "route", "show", "default"], 15)
        return rc == 0 and bool(re.search(r"^default\s", out or "", re.M))
    return has("-4"), has("-6")


def ip6_only():
    try:
        v4, v6 = default_routes()
        return bool(v6 and not v4)
    except Exception:
        return False


def can_resolve(host, secs=8):
    """Phân giải được tên miền không (chạy ở luồng riêng: getaddrinfo không có giờ chờ)."""
    res = []
    def go():
        try: socket.getaddrinfo(host, 443); res.append(True)
        except Exception: res.append(False)
    t = threading.Thread(target=go, daemon=True); t.start(); t.join(secs)
    return bool(res and res[0])


def resolv_servers(txt):
    return re.findall(r"^[ \t]*nameserver[ \t]+(\S+)", txt or "", re.M)


def keep_once(path, old):
    """Lưu bản gốc 1 lần (<file>.cb-goc) trước khi cbhost sửa file cấu hình mạng."""
    bak = path + ".cb-goc"
    if old and not os.path.exists(bak):
        with open(bak, "w", encoding="utf-8") as f: f.write(old)


def fix_dns(v4, v6, force=False):
    """Không phân giải được tên miền → ghi máy chủ tên công cộng hợp với đường ra đang có vào resolv.conf (giữ dòng search / domain / options).
       Chỉ sửa khi máy chủ tên đang đặt RÕ RÀNG không dùng được (trống · 192.168.100.1 của bộ cài · khác họ địa chỉ với đường ra đang có);
       trường hợp còn lại chỉ sửa khi force (đã hỏng nhiều lần liền). → True nếu có ghi."""
    want = [DNS4[0], DNS6[0], DNS4[1]] if (v4 and v6) else list(DNS4) if v4 else list(DNS6) if v6 else []
    if not want: return False
    try: old = open(RESOLV_F, encoding="utf-8", errors="replace").read()
    except OSError: old = ""
    cur = resolv_servers(old)
    if cur == want: return False
    usable = [x for x in cur if x not in DNS_BOGUS and ((":" in x and v6) or (":" not in x and v4))]
    if usable and not force: return False
    keep = [ln.strip() for ln in old.splitlines() if re.match(r"^[ \t]*(search|domain|options)[ \t]", ln)]
    new = "\n".join(["# CloudBlue (cbhost): may chu ten (DNS) cu khong dung duoc -> dat may chu ten cong cong. Ban goc: %s.cb-goc" % RESOLV_F]
                    + keep + ["nameserver " + x for x in want]) + "\n"
    keep_once(RESOLV_F, old)
    with open(RESOLV_F, "w", encoding="utf-8") as f: f.write(new)      # ghi thẳng (không đổi tên file): giữ nguyên nếu file là liên kết
    return True


def bridge_ipv4(bridge):
    """Cấu hình mạng của Proxmox (/etc/network/interfaces) về cầu này: 'v6' = bộ cài chỉ đặt IPv6 · 'v4' = đã có dòng IPv4 · '' = không có cầu / không đọc được."""
    try: txt = open(IFACES_F, encoding="utf-8", errors="replace").read()
    except OSError: return ""
    b = re.escape(bridge)
    if re.search(r"^[ \t]*iface[ \t]+%s[ \t]+inet[ \t]" % b, txt, re.M): return "v4"
    return "v6" if re.search(r"^[ \t]*iface[ \t]+%s[ \t]+inet6[ \t]" % b, txt, re.M) else ""


def ensure_dhcp4(bridge):
    """Cầu mạng của máy chủ CHƯA có cấu hình IPv4 nào (bộ cài chỉ đặt IPv6) → bật dịch vụ cloudblue-dhcp4: dhclient xin IPv4 cho cầu đó ngay,
       mỗi lần bật máy, mạng chưa cấp thì tự thử lại mãi. KHÔNG sửa /etc/network/interfaces. Cầu đã có IPv4 trong cấu hình → không làm (và gỡ
       dịch vụ nếu trước đây đã bật). → chữ mô tả việc vừa làm ("" = không làm gì mới)."""
    dh = shutil.which("dhclient")
    if not RX_BRIDGE.match(bridge or "") or not dh or not shutil.which("systemctl"): return ""
    kind = bridge_ipv4(bridge)
    if kind == "v4":
        if os.path.exists(DHCP_UNIT_F):                            # admin đã đặt IPv4 cho cầu (trang Proxmox) → không xin DHCP song song nữa
            run(["systemctl", "disable", "--now", DHCP_UNIT], 60)
            try: os.remove(DHCP_UNIT_F)
            except OSError: pass
            run(["systemctl", "daemon-reload"], 60)
            return "cầu %s đã được đặt IPv4 trong cấu hình Proxmox → gỡ dịch vụ xin DHCP tạm (cloudblue-dhcp4)" % bridge
        return ""
    if kind != "v6": return ""
    want = DHCP_UNIT_TXT % {"br": bridge, "dh": dh}
    try: have = open(DHCP_UNIT_F, encoding="utf-8").read()
    except OSError: have = ""
    if have == want and run(["systemctl", "is-active", DHCP_UNIT], 30)[0] == 0: return ""      # đang chạy rồi (mạng chưa cấp thì dhclient tự thử lại)
    tmp = DHCP_UNIT_F + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(want)
    os.chmod(tmp, 0o644); os.replace(tmp, DHCP_UNIT_F)
    run(["systemctl", "daemon-reload"], 60)
    rc, out = run(["systemctl", "enable", "--now", DHCP_UNIT], 90)
    got = False
    for _ in range(15):                                             # chờ tối đa ~30 giây xem mạng có cấp IPv4 không
        if default_routes()[0]: got = True; break
        time.sleep(DHCP_WAIT_S)
    return "bật dịch vụ xin IPv4 qua DHCP cho %s (cloudblue-dhcp4, mã %d%s): %s" % (
        bridge, rc, "" if rc == 0 else " " + (out or "")[-120:].replace("\n", " | "), "ĐÃ có IPv4" if got else "mạng chưa cấp IPv4 — dịch vụ tự thử lại mãi")


def web_host(c):
    try: return urllib.parse.urlsplit(c["sb_url"]).hostname or ""
    except Exception: return ""


def is_ip(host):
    for fam in (socket.AF_INET, socket.AF_INET6):
        try: socket.inet_pton(fam, host); return True
        except (OSError, ValueError): pass
    return False


def net_heal(c, n=1):
    """1 lượt tự sửa mạng (gọi khi KHÔNG tới được web). n = lượt thứ mấy. → danh sách việc đã làm."""
    did = []
    v4, v6 = default_routes()
    if not v4 or os.path.exists(DHCP_UNIT_F):
        r = ensure_dhcp4(c["bridge"])
        if r:
            did.append(r)
            v4, v6 = default_routes()
    host = web_host(c)
    if host and not is_ip(host) and not can_resolve(host):
        if fix_dns(v4, v6, force=n >= 3): did.append("đặt lại máy chủ tên (DNS): %s" % ", ".join(resolv_servers(open(RESOLV_F, encoding="utf-8", errors="replace").read())))
    return did


def ascii_vn(s):
    """Chữ Việt → không dấu (màn hình chữ của máy chủ không có phông tiếng Việt)."""
    s = str(s)
    for a, b in (("đ", "d"), ("Đ", "D"), (" · ", " | "), ("·", "|"), ("—", "-"), ("–", "-"), ("›", ">"), ("→", "->"), ("…", "...")): s = s.replace(a, b)
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").encode("ascii", "replace").decode("ascii")


def tty_say(msg):
    """In 1 dòng ra màn hình gắn vào máy chủ (không có màn hình / không ghi được thì thôi)."""
    try:
        with open(TTY_F, "w") as f: f.write("\r\n[CloudBlue %s] %s\r\n" % (time.strftime("%H:%M"), ascii_vn(msg)[:400]))
    except Exception:
        pass


class Screen:
    """Báo ra màn hình máy chủ: lên web được chưa (1 lần khi đổi trạng thái) · chưa được thì 5 phút / lần kèm tình trạng mạng."""
    def __init__(self, c, say=None, now=time.time, report=None):
        self.on, self.c, self.say, self.now, self.report = bool(c.get("net_heal")), c, say or tty_say, now, report or net_report
        self.state, self.fails, self.last = None, 0, 0.0

    def step(self, ok, h):
        if not self.on: return
        if ok:
            if self.state != "ok":
                self.say("DA LEN WEB: may chu '%s'%s" % (h.name, " - CHO DUYET: vao web CloudBlue > Quan tri > May cho thue > VPS ao hoa > May chu, bam DUYET" if h.status == "new" else " (%s)" % h.status))
            self.state, self.fails = "ok", 0
            return
        if ok is not False: return
        self.fails += 1
        if self.fails >= NET_FAILS and self.now() - self.last >= 300:
            self.last, self.state = self.now(), "fail"
            try: rep = self.report(self.c)
            except Exception as e: rep = "khong doc duoc tinh trang mang (%s)" % str(e)[:60]
            self.say("CHUA goi duoc web CloudBlue (%s) | %s" % (str(h.web.err or "web tu choi")[:120], rep))

    def healed(self, n, what):
        if self.on: self.say("tu sua mang (luot %d): %s" % (n, what))


class NetWatch:
    """Đếm số vòng liền không TỚI ĐƯỢC web (lỗi mạng, không phải web trả lỗi) → đến lúc thì gọi net_heal."""
    def __init__(self, c, heal=None, now=time.time):
        self.c, self.heal, self.now = c, heal or net_heal, now
        self.fails = self.heals = 0; self.last = 0.0

    def step(self, ok, err):
        """Gọi sau mỗi vòng hỏi web. → danh sách việc vừa tự sửa (thường rỗng)."""
        if ok: self.fails = 0; return []
        if ok is not False or not err or str(err).startswith("HTTP "): return []      # web có trả lời (kể cả báo lỗi) → mạng không sao
        self.fails += 1
        if not self.c.get("net_heal") or self.fails < NET_FAILS: return []
        if self.now() - self.last < NET_EVERY_S[0 if self.heals < 10 else 1]: return []
        self.last = self.now(); self.heals += 1
        try: return self.heal(self.c, self.heals) or []
        except Exception as e: return ["lỗi: %s" % str(e)[:160]]


_cpu = {"t": None}
def cpu_pct():
    try:
        v = [float(x) for x in open("/proc/stat").readline().split()[1:]]
        idle, tot = v[3] + (v[4] if len(v) > 4 else 0), sum(v)
        prev, _cpu["t"] = _cpu["t"], (idle, tot)
        if not prev or tot <= prev[1]: return 0.0
        return round(100 * (1 - (idle - prev[0]) / (tot - prev[1])), 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- 1 việc máy mẫu: kiểm dữ liệu web gửi xuống
def job_ok(it):
    try:
        return (isinstance(it, dict) and re.fullmatch(r"[0-9]{1,12}", str(it.get("id"))) and it.get("want") in ("running", "save", "cancel")
                and it.get("src") in ("iso", "tpl") and (it.get("src") == "tpl" or RX_ISO.match(str(it.get("iso") or "")))
                and 1 <= int(it.get("cores")) <= 16 and 1024 <= int(it.get("ram_mb")) <= 32768 and 16 <= int(it.get("disk_gb")) <= 200
                and RX_TPL.match(str(it.get("tpl") or "")) and len(str(it.get("tpl"))) <= 36 and RX_HW.match(str(it.get("hw") or "")))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- 1 VPS: kiểm dữ liệu web gửi xuống
def item_ok(it):
    try:
        return (isinstance(it, dict) and re.fullmatch(r"[0-9]{1,12}", str(it.get("id"))) and it.get("want") in ("running", "stopped", "deleted")
                and 1 <= int(it.get("cores")) <= 64 and 512 <= int(it.get("ram_mb")) <= 262144 and 10 <= int(it.get("disk_gb")) <= 4000
                and 1 <= int(it.get("inst")) and 0 <= int(it.get("boot")) and RX_TPL.match(str(it.get("tpl") or "")) and RX_HW.match(str(it.get("hw") or ""))
                and (it.get("cfg") is None or (not isinstance(it.get("cfg"), bool) and 0 <= int(it.get("cfg")) <= 999999)))
    except (TypeError, ValueError):
        return False



# ---------------------------------------------------------------- 27/11e · KHO PROXY NHIỀU IP (cbpool) — xem phần đầu file
POOL_FILE = ("cbpool-x86_64", "e250a05b91935c343a4104a131a06fe0")                   # md5 ghim: file lạ / sai bản không bao giờ chạy
POOL_RAW = os.environ.get("CBHOST_POOL_RAW") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/"
POOL_BIN = os.environ.get("CBHOST_POOL_BIN") or "/usr/local/bin/cbpool"
POOL_CONF_F = os.environ.get("CBHOST_POOL_CONF") or "/etc/cloudblue/cbpool.json"
POOL_CTL = os.environ.get("CBHOST_POOL_CTL") or "/run/cbpool/ctl.sock"
POOL_UNIT = "cloudblue-pool.service"
POOL_UNIT_F = os.environ.get("CBHOST_POOL_UNIT") or "/etc/systemd/system/" + POOL_UNIT
SYSTEMCTL = os.environ.get("CBHOST_SYSTEMCTL") or "systemctl"
POOL_EVERY_S = 60                # kiểm file + dịch vụ 1 phút / lần (số đo thì đọc mỗi vòng hỏi web)
POOL_USERS_F = os.environ.get("CBHOST_POOL_USERS") or "/etc/cloudblue/cbpool-users.json"     # 27/11g · tài khoản khách mua proxy
RX_PX_USER = re.compile(r"^px[a-z0-9]{6,30}$")
RX_PX_UNIT = re.compile(r"^(s[0-9]{1,5}|[0-9]{1,2})$")
POOL_DL_RETRY_S = 600            # tải hỏng → 10 phút sau mới tải lại
POOL_UNIT_TXT = """[Unit]
Description=CloudBlue cbpool - kho proxy nhieu IP (IPv6 + PPPoE)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%s run -c %s
Restart=always
RestartSec=5
LimitNOFILE=65536
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full

[Install]
WantedBy=multi-user.target
""" % (POOL_BIN, POOL_CONF_F)


def md5_path(p):
    try:
        h = hashlib.md5()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
        return h.hexdigest()
    except OSError:
        return ""


def pool_conf_default(c):
    """Cấu hình đầu tiên (chỉ ghi khi chưa có — admin sửa tay thì giữ nguyên)."""
    return {"listen": "0.0.0.0:8899", "iface6": c.get("bridge") or "vmbr0", "slots": 30, "bw_kbps": 30000}


def pool_ask(req, timeout=4):
    """Hỏi cbpool qua ổ cắm điều khiển (chỉ root) → dict, hoặc None."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(timeout); s.connect(POOL_CTL)
        s.sendall((json.dumps(req) + "\n").encode()); buf = b""
        while not buf.endswith(b"\n") and len(buf) < 2 << 20:
            b = s.recv(65536)
            if not b: break
            buf += b
        s.close()
        return json.loads(buf.decode("utf-8") or "null")
    except Exception:
        return None


class PoolMgr:
    def __init__(self, c, web=None, sec=None):
        self.c = c; self.t = 0.0; self.dl_fail_t = 0.0; self.err = ""; self.restart = False
        self.web, self.sec = web, sec; self.users_txt = None; self.ppp_done = 0; self.ppp_err = ""; self.sync_err = ""   # 27/11g · bán proxy

    def step(self, act=True):
        """Mỗi vòng hỏi web: (1 phút / lần) giữ file + dịch vụ đúng; trả số đo gọn cho web (None = tắt / chưa chạy)."""
        if act and time.time() - self.t >= POOL_EVERY_S:
            self.t = time.time()
            try:
                if self.c.get("pool"): self.ensure()
                else: self.disable()
            except Exception as e:
                if self.err != str(e)[:160]: log("kho proxy: %s" % str(e)[:160])
                self.err = str(e)[:160]
            if self.c.get("pool") and not self.err:
                try: self.sync()
                except Exception as e:
                    if self.sync_err != str(e)[:160]: log("bán proxy: %s" % str(e)[:160])
                    self.sync_err = str(e)[:160]
        if not self.c.get("pool"): return None
        return self.report(pool_ask({"cmd": "status"}))

    def ensure(self):
        if len(POOL_FILE[1]) != 32: raise RuntimeError("bản cbhost này chưa ghim md5 cbpool")
        if md5_path(POOL_BIN) != POOL_FILE[1]:
            if time.time() - self.dl_fail_t < POOL_DL_RETRY_S: raise RuntimeError("chưa tải được cbpool đúng bản (thử lại sau)")
            try: data = http_get(POOL_RAW + POOL_FILE[0] + ("" if POOL_RAW.startswith("file:") else "?t=%d" % int(time.time())), limit=32 << 20)
            except Exception as e:
                self.dl_fail_t = time.time(); raise RuntimeError("tải cbpool lỗi: %s" % str(e)[:120])
            if hashlib.md5(data).hexdigest() != POOL_FILE[1]:
                self.dl_fail_t = time.time(); raise RuntimeError("tải cbpool sai md5 (GitHub chưa có bản %s)" % POOL_FILE[1][:8])
            os.makedirs(os.path.dirname(POOL_BIN) or ".", exist_ok=True)
            tmp = POOL_BIN + ".new"
            with open(tmp, "wb") as f: f.write(data)
            os.chmod(tmp, 0o755); os.replace(tmp, POOL_BIN)
            self.restart = True
            log("kho proxy: đã tải cbpool %s (%d byte)" % (POOL_FILE[1][:8], len(data)))
        if not os.path.exists(POOL_CONF_F):
            os.makedirs(os.path.dirname(POOL_CONF_F) or ".", exist_ok=True)
            save_json(POOL_CONF_F, pool_conf_default(self.c), 0o644)
        try: cur = open(POOL_UNIT_F, encoding="utf-8").read()
        except OSError: cur = ""
        if cur != POOL_UNIT_TXT:
            with open(POOL_UNIT_F, "w", encoding="utf-8") as f: f.write(POOL_UNIT_TXT)
            run([SYSTEMCTL, "daemon-reload"], 60); self.restart = True
        rc, out = run([SYSTEMCTL, "is-active", POOL_UNIT], 15)
        if rc != 0 or out.strip() != "active":
            rc, out = run([SYSTEMCTL, "enable", "--now", POOL_UNIT], 60)
            if rc != 0: raise RuntimeError("bật dịch vụ cloudblue-pool lỗi: %s" % out[-160:])
            log("kho proxy: đã bật dịch vụ cloudblue-pool (cổng 8899)")
        elif self.restart:
            run([SYSTEMCTL, "restart", POOL_UNIT], 60); log("kho proxy: chạy lại cloudblue-pool (bản / dịch vụ mới)")
        self.restart = False; self.err = ""

    def sync(self):
        """27/11g · bán proxy: px_host_sync (SQL v63) → tài khoản khách cho cbpool + tài khoản PPPoE đã mã hoá; báo lại IP từng ô bán + khoá công khai."""
        if not self.web or not self.sec: return
        cs = pool_ask({"cmd": "cust"})
        rep = {"ver": CBHOST_VER}
        if isinstance(cs, dict) and cs.get("ok"):
            rep["pk"] = str(cs.get("pk") or "")[:200]
            u = cs.get("units") if isinstance(cs.get("units"), dict) else {}
            rep["units"] = {str(k)[:8]: str(v)[:64] for k, v in list(u.items())[:3000] if RX_PX_UNIT.match(str(k))}
        if self.ppp_done: rep["ppp_ok"] = self.ppp_done
        if self.ppp_err: rep["ppp_err"] = self.ppp_err[:200]
        r = self.web.rpc("px_host_sync", {"p_secret": self.sec, "p_report": rep}, timeout=20)
        if not isinstance(r, dict) or not r.get("ok"):
            e = (self.web.err or str((r or {}).get("err") if isinstance(r, dict) else "") or "")[:160]
            if "px_host_sync" in e or "PGRST202" in e or "404" in e: e = ""            # web chưa chạy SQL v63: chưa bán proxy
            self.sync_err = e
            return
        self.sync_err = ""
        if isinstance(r.get("users"), list):
            users = []
            for x in r["users"][:5000]:
                if not isinstance(x, dict) or not RX_PX_USER.match(str(x.get("u") or "")) or str(x.get("k")) not in ("v6", "v4") or not RX_PX_UNIT.match(str(x.get("n") or "")): continue
                try: row = {"u": str(x["u"]), "p": str(x.get("p") or "")[:64], "k": str(x["k"]), "n": str(x["n"]), "x": int(x.get("x") or 0), "s": max(1, min(5, int(x.get("s") or 1)))}
                except (TypeError, ValueError): continue
                if len(row["p"]) < 8 or row["x"] <= time.time(): continue
                if isinstance(x.get("r"), str) and 16 <= len(x["r"]) <= 64 and row["s"] == 1: row["r"] = x["r"]
                users.append(row)
            num = lambda k, d=0: int(r.get(k)) if isinstance(r.get(k), (int, float)) else d
            uf = {"v": 1, "bw": num("bw"), "fb4": bool(r.get("fb4")), "sale4": bool(r.get("sale4")), "maxc": num("maxc"),
                  "self": [str(x)[:64] for x in (r.get("self") or []) if isinstance(x, str)][:8], "users": users}
            txt = json.dumps(uf, sort_keys=True, ensure_ascii=False)
            if txt != self.users_txt:
                os.makedirs(os.path.dirname(POOL_USERS_F) or ".", exist_ok=True)
                tmp = POOL_USERS_F + ".tmp"
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(txt)
                os.chmod(tmp, 0o600); os.replace(tmp, POOL_USERS_F)
                a = pool_ask({"cmd": "users"}, timeout=10)
                if isinstance(a, dict) and a.get("ok") is not False:
                    if self.users_txt is None or len(users) != len(json.loads(self.users_txt).get("users") or []): log("bán proxy: %d tài khoản khách" % len(users))
                    self.users_txt = txt
        pp = r.get("ppp")
        if isinstance(pp, dict) and isinstance(pp.get("enc"), str) and isinstance(pp.get("gen"), int) and pp["gen"] != self.ppp_done and len(pp["enc"]) < 8000:
            rc, out = run_in([POOL_BIN, "ppp-import", "-c", POOL_CONF_F], pp["enc"], 180)
            try: j = json.loads(out[out.find("{"):]) if "{" in out else {}
            except Exception: j = {}
            if rc == 0 and j.get("ok"):
                self.ppp_done, self.ppp_err = pp["gen"], ""
                log("bán proxy: đã nhận tài khoản PPPoE từ web (%s, %s phiên)" % (j.get("user"), j.get("sessions")))
            else:
                self.ppp_err = str(j.get("err") or out[-160:] or "ppp-import lỗi")[:200]
                log("bán proxy: tài khoản PPPoE từ web chưa dùng được — %s" % self.ppp_err)

    def disable(self):
        if os.path.exists(POOL_UNIT_F):
            rc, out = run([SYSTEMCTL, "is-active", POOL_UNIT], 15)
            if rc == 0 and out.strip() == "active":
                run([SYSTEMCTL, "disable", "--now", POOL_UNIT], 60); log("kho proxy: đã tắt (cấu hình pool=false)")

    def report(self, st):
        """Số đo gọn cho web: ô = [id, mật khẩu, đuôi IPv6, IPv4, số kết nối, khoá đổi IP]."""
        if not isinstance(st, dict) or not isinstance(st.get("slots"), list):
            return {"ok": False, "err": self.err or "cbpool chưa chạy"}
        v6, pp = st.get("v6") or {}, st.get("ppp") or {}
        port = 8899
        try: port = int(str(st.get("listen") or ":8899").rsplit(":", 1)[1])
        except (ValueError, IndexError): pass
        pfx = str(v6.get("prefix") or "")
        head = pfx.split("::/")[0] + ":" if "::/" in pfx else ""
        sl = []
        for x in st["slots"][:200]:
            if not isinstance(x, dict): continue
            ip6 = str(x.get("ip6") or "")
            sl.append([str(x.get("id") or "")[:8], str(x.get("pass") or "")[:40], ip6[len(head):] if head and ip6.startswith(head) else ip6,
                       str(x.get("ip4") or ""), int(x.get("conns") or 0), str(x.get("rot") or "")[:40]])
        r = {"ok": True, "ver": str(st.get("ver") or "")[:16], "host": lan_ip(), "port": port, "v6": pfx, "s": sl,
             "ppp": {"want": int(pp.get("want") or 0), "up": int(pp.get("up") or 0), "acct": bool(pp.get("account")),
                     "ip": [str(y.get("ip")) for y in (pp.get("sess") or []) if isinstance(y, dict) and y.get("ip")][:64],
                     "k": [int(y.get("k")) for y in (pp.get("sess") or []) if isinstance(y, dict) and y.get("up") and isinstance(y.get("k"), int)][:64]}}   # 27/11g · phiên đang lên (bán IPv4)
        if isinstance(st.get("pk"), str) and 60 <= len(st["pk"]) <= 200: r["pk"] = st["pk"]                  # 27/11g · khoá công khai: web mã hoá tài khoản PPPoE
        if isinstance(st.get("pub4"), str) and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", st["pub4"]): r["pub4"] = st["pub4"]   # IPv4 công khai: khách nối vào đây
        cu = st.get("cust") if isinstance(st.get("cust"), dict) else {}
        if cu: r["cust"] = {"n": int(cu.get("n") or 0), "conns": int(cu.get("conns") or 0)}
        if self.sync_err: r["sync_err"] = self.sync_err[:160]
        if self.ppp_err: r["ppp"]["enc_err"] = self.ppp_err[:160]
        if v6.get("err"): r["v6err"] = str(v6["err"])[:160]
        if pp.get("err"): r["ppp"]["err"] = str(pp["err"])[:160]
        dc = pp.get("disc")                                          # 27/11f · tự dò PPPoE: modem có cho đi qua không
        if isinstance(dc, dict):
            d = {"t": int(dc.get("t") or 0) if str(dc.get("t") or "0").isdigit() else 0}
            if dc.get("err"): d["err"] = str(dc["err"])[:120]
            else: d["ok"] = dc.get("ok") is True; d["ac"] = [str(a)[:40] for a in (dc.get("ac") or []) if isinstance(a, str)][:3]
            r["ppp"]["disc"] = d
        if self.err: r["err"] = self.err
        return r


class Host:
    def __init__(self, c=None, web=None, pve=None):
        self.c = c or conf(); self.web = web or Web(self.c); self.pve = pve or Pve(self.c)
        self.sec = secret(); self.st = load_json(STATE_F, {}); self.status = "?"; self.name = ""
        self.lock = threading.Lock(); self.busy = {}; self.poll_s = 10; self.want = []; self.tpl_need = []
        self.light = set()                                          # 27/11c · việc nhẹ (xoá máy ảo): không tính vào max_builds
        self.iso_key = None; self.iso_at = 0.0; self.iso_state = {}  # 27/11d · cách ly VPS
        self.soft = set()                                           # việc nền KHÔNG phải tạo / xoá máy (đổi cấu hình, nới ổ C): vẫn báo web máy đang chạy / tắt như thường
        self.info_t = 0.0; self.hello_ok = False
        self.jobs = []; self.jobs_ok = False; self.iso_t = 0.0; self.iso_list = []; self.auto = []      # việc máy mẫu (web v57) · file ISO trên máy chủ
        self.usb = None                                                                                  # luồng nạp ISO máy mẫu từ USB (cmd_run bật)
        self.pool = PoolMgr(self.c, self.web, self.sec)                                                  # 27/11e · kho proxy nhiều IP (27/11g: bán proxy)

    def save(self):
        with self.lock: save_json(STATE_F, self.st)

    def vmid(self, vid): return self.c["vmid_base"] + int(vid)

    def gpath(self, tpl, name):
        """Đường dẫn file của CloudBlue trong máy ảo theo loại máy mẫu: Linux /opt/cloudblue/<tên> · Windows C:\\CloudBluePC\\<tên>."""
        return LIN_BASE + "/" + name if is_linux_tpl(tpl) else self.c["seed_path"].rsplit("\\", 1)[0] + "\\" + name

    # ---- việc chạy lâu (nhân bản, xoá) ở luồng riêng: vẫn hỏi web đều 10 giây / lần
    def bg(self, vid, fn, *a, soft=False, light=False):
        """Chạy fn ở luồng riêng. Việc nặng (dựng / nhân bản) tối đa max_builds cùng lúc; việc nhẹ (light: xoá) không bị giới hạn
           và không chiếm chỗ của việc nặng (27/11c)."""
        if vid in self.busy: return False
        if not light and sum(1 for k in self.busy if k not in self.light) >= self.c["max_builds"]: return False
        def go():
            try: fn(*a)
            except Exception as e:
                self.fail(vid, "lỗi: %s" % e)
            finally:
                self.busy.pop(vid, None); self.soft.discard(vid); self.light.discard(vid)
        if soft: self.soft.add(vid)
        if light: self.light.add(vid)
        th = threading.Thread(target=go, daemon=True); self.busy[vid] = th; th.start()
        return True

    def fail(self, vid, msg):
        with self.lock:
            s = self.st.setdefault(str(vid), {}); s["err"] = str(msg)[:280]; s["t_err"] = time.time()
        log("%s: %s" % (("MẪU-" + str(vid)[1:]) if str(vid)[:1] in ("t", "a", "l") else ("VPS-%s" % vid), msg)); self.save()

    def build(self, it, tpl_id):
        vid, vmid = int(it["id"]), self.vmid(it["id"])
        log("VPS-%s: tạo máy ảo %d từ máy mẫu %s (bản cài %s)" % (vid, vmid, it["tpl"], it["inst"]))
        if vmid in self.pve.vms():
            rc, out = self.pve.destroy(vmid)
            if rc != 0: return self.fail(vid, "xoá máy ảo cũ lỗi: " + out[-200:])
        rc, out = self.pve.clone(tpl_id, vmid, "vps-%d" % vid)
        if rc != 0: return self.fail(vid, "nhân bản lỗi: " + out[-200:])
        gb0 = self.pve.boot_disk(vmid)[1]                          # cỡ ổ của máy mẫu
        rc, out = self.pve.setup(vmid, int(it["cores"]), int(it["ram_mb"]), int(it["disk_gb"]), it["hw"])
        if rc != 0: return self.fail(vid, "đặt cấu hình lỗi: " + out[-200:])
        with self.lock:
            self.st[str(vid)] = {"inst": int(it["inst"]), "boot": int(it["boot"]), "ticket": secrets.token_hex(24), "sent": False, "seeded": False,
                                 "t_build": time.time(), "cfg": int(it.get("cfg") or 0), "lin": is_linux_tpl(it["tpl"])}
            if int(it["disk_gb"]) > gb0 + 0.5:                      # ổ lớn hơn máy mẫu → Windows lên xong phải nới ổ C (26/11e)
                self.st[str(vid)]["grow"] = {"gb": int(it["disk_gb"]), "n": 0, "t": 0, "t0": time.time()}
        self.save()
        if it["want"] == "running":
            rc, out = self.pve.start(vmid)
            if rc != 0: return self.fail(vid, "bật máy lỗi: " + out[-200:])
        log("VPS-%s: tạo xong, chờ Windows lên để đưa vé đăng ký" % vid)

    def recfg(self, it):
        """26/11e · web đổi cấu hình (khách nâng cấp / admin sửa): đặt vCPU + RAM, nới ổ. Máy đang chạy mà vCPU / RAM khác → TẮT HẲN rồi bật lại
           (Proxmox chỉ nhận vCPU / RAM mới khi bật nguội; khởi động lại từ trong Windows không đủ). Dữ liệu trong ổ giữ nguyên. Chạy lại bao nhiêu lần cũng được."""
        vid, vmid = int(it["id"]), self.vmid(it["id"]); cores, ram, disk, cfg = int(it["cores"]), int(it["ram_mb"]), int(it["disk_gb"]), int(it["cfg"])
        c0, m0 = self.pve.hw_now(vmid)
        log("VPS-%s: đổi cấu hình lần %d → %d vCPU · %d MB RAM · %d GB (đang chạy với %s vCPU · %s MB)" % (vid, cfg, cores, ram, disk, c0, m0))
        rc, out = self.pve.set_hw(vmid, cores, ram)
        if rc != 0: return self.fail(vid, "đặt vCPU / RAM lỗi: " + out[-200:])
        rc, out, grew = self.pve.grow_disk(vmid, disk)
        if rc != 0: return self.fail(vid, "nới ổ lỗi: " + out[-200:])
        vm = self.pve.vms().get(vmid)
        if vm and vm["status"] == "running" and (c0, m0) != (cores, ram):
            rc, out = self.pve.shutdown(vmid)
            if rc != 0: return self.fail(vid, "tắt máy để nhận cấu hình mới lỗi: " + out[-200:])
            if it["want"] == "running":
                rc, out = self.pve.start(vmid)
                if rc != 0: return self.fail(vid, "bật lại máy sau khi đổi cấu hình lỗi: " + out[-200:])
            log("VPS-%s: đã tắt hẳn + bật lại để nhận cấu hình mới" % vid)
        with self.lock:
            s = self.st.setdefault(str(vid), {}); s["cfg"] = cfg; s.pop("err", None)
            if grew: s["grow"] = {"gb": disk, "n": 0, "t": 0, "t0": time.time()}
        self.save()

    def grow(self, vid):
        """Nới ổ C trong Windows cho bằng ổ vừa nới ở Proxmox (lệnh cố định GROW_PS qua QEMU guest agent). Windows chưa lên → lần sau thử lại."""
        s = self.st.get(str(vid)) or {}; g = s.get("grow"); vmid = self.vmid(vid)
        if not g: return
        with self.lock: g["t"] = time.time()
        done = why = None
        if not self.pve.ga_ping(vmid):
            if time.time() - float(g.get("t0") or 0) > GROW_MAX_S: why = "Windows không trả lời (QEMU guest agent) suốt %d phút" % (GROW_MAX_S // 60)
        else:
            rc, out = self.pve.ga_exec(vmid, GROW_LIN_ARGS if s.get("lin") else GROW_ARGS, 60)
            gb = None
            try:
                j = json.loads(out or "{}")
                if rc == 0 and isinstance(j, dict) and j.get("exited") and int(j.get("exitcode") or 0) == 0:
                    m = re.findall(r"\d+", str(j.get("out-data") or "")); gb = int(m[-1]) if m else None
            except Exception: gb = None
            if gb is not None and gb >= int(g["gb"]) - 2: done = gb
            else:
                with self.lock: g["n"] = int(g.get("n") or 0) + 1
                if g["n"] >= GROW_TRIES: why = "lệnh nới ổ trong Windows không được (%s)" % (str(out or "")[-120:].replace("\n", " "))
        if done is not None or why:
            with self.lock: s.pop("grow", None)
            log(("VPS-%s: ổ C trong Windows đã nới lên %d GB" % (vid, done)) if done is not None
                else ("VPS-%s: KHÔNG tự nới được ổ C (%s) — ổ ở Proxmox đã đủ %s GB, khách tự nới bằng Disk Management › Extend Volume" % (vid, why, g["gb"])))
        self.save()

    def rep_now(self, vid, vm, s):
        """Dòng báo cáo khi đang có việc nền nhẹ (đổi cấu hình / nới ổ): máy đang chạy hay tắt thì báo vậy — không báo 'đang tạo'."""
        return {"id": vid, "state": "running" if (vm and vm["status"] == "running") else "stopped", "inst": int((s or {}).get("inst") or 0), "boot": int((s or {}).get("boot") or 0)}

    def remove(self, vid):
        vmid = self.vmid(vid)
        if vmid in self.pve.vms():
            log("VPS-%s: xoá máy ảo %d" % (vid, vmid))
            rc, out = self.pve.destroy(vmid)                         # 27/11c: máy đang chạy → destroy tự tắt hẳn trước
            if rc != 0: return self.fail(vid, "xoá máy ảo lỗi: " + out[-200:])
        with self.lock: self.st.pop(str(vid), None)
        self.save()

    def seed(self, vid, it):
        """Windows đã lên (guest agent trả lời) + web đã nhận dấu băm của vé → ghi seed.json {hw, ticket} vào máy ảo."""
        s = self.st.get(str(vid)) or {}
        vmid = self.vmid(vid)
        if not s.get("ticket") or not s.get("sent") or s.get("seeded") or not self.pve.ga_ping(vmid): return
        idf = self.gpath(it["tpl"], "identity.json")
        if has_identity(self.pve.ga_read(vmid, idf)):             # máy mẫu lỡ ĐÃ ĐĂNG KÝ → mọi bản nhân ra sẽ mang chung 1 mã máy → dừng, báo làm lại máy mẫu
            return self.fail(vid, "máy mẫu %s đã đăng ký CloudBlue (có %s) — làm lại máy mẫu theo hướng dẫn (cài CloudBlue PC KHÔNG nhập mã)" % (it["tpl"], idf))
        if s.get("lin") and not s.get("net"):                      # 27/11c: mạng Linux không gắn MAC máy mẫu (xem NET_LIN_SH)
            rc, out = self.pve.ga_exec(vmid, NET_LIN_ARGS, 90)
            log("VPS-%s: đặt mạng DHCP cho Linux (%s)" % (vid, "được" if rc == 0 else "lỗi: " + str(out or "")[-120:]))
            with self.lock: s["net"] = True
        rc, out = self.pve.ga_write(vmid, self.gpath(it["tpl"], "seed.json"), json.dumps({"hw": it["hw"], "ticket": s["ticket"]}))
        if rc != 0: return self.fail(vid, "ghi vé vào máy ảo lỗi (QEMU guest agent): " + out[-200:])
        with self.lock: s["seeded"] = True; s["t_seed"] = time.time(); s.pop("err", None)
        log("VPS-%s: đã đưa vé vào máy ảo → agent CloudBlue tự đăng ký" % vid); self.save()

    # ---- MÁY MẪU (bảng điều khiển máy mẫu trên web)
    def job_vmid(self, jid, vms):
        s = self.st.get("t%d" % jid) or {}
        if s.get("vmid") in vms or (s.get("vmid") and s.get("made")): return int(s["vmid"])
        for k, v in vms.items():
            if v["name"] == "cbmau-%d" % jid: return k
        return None

    def job_create(self, it, tpl_id):
        jid = int(it["id"]); key = "t%d" % jid
        vms = self.pve.vms()
        with self.lock:                                                # chọn số máy ảo + ghi sổ trong 1 lần khoá: 2 việc cùng lúc không trùng số
            vmid = self.c["tpl_vmid_from"]
            while vmid in vms or vmid in [int((x or {}).get("vmid") or 0) for k, x in self.st.items() if k[:1] in ("t", "a", "l") and k != key]: vmid += 1
            self.st[key] = {"vmid": vmid, "made": False, "ticket": secrets.token_hex(24), "sent": False, "seeded": False, "t_build": time.time()}
        self.save()
        if it["src"] == "iso":
            stg = self.pve.image_storage()
            if not stg: return self.fail(key, "máy chủ không có ổ chứa máy ảo (images)")
            log("MẪU-%d: tạo máy ảo %d (%s) từ ISO %s" % (jid, vmid, it["tpl"], it["iso"]))
            rc, out = self.pve.create_tpl_vm(vmid, "cbmau-%d" % jid, it, stg)
            if rc != 0: return self.fail(key, "tạo máy ảo lỗi: " + out[-200:])
        else:
            log("MẪU-%d: nhân bản máy mẫu %s → máy ảo %d để sửa" % (jid, it["tpl"], vmid))
            rc, out = self.pve.clone(tpl_id, vmid, "cbmau-%d" % jid)
            if rc != 0: return self.fail(key, "nhân bản lỗi: " + out[-200:])
            rc, out = self.pve.setup_tpl_vm(vmid, it)
            if rc != 0: return self.fail(key, "đặt cấu hình lỗi: " + out[-200:])
        with self.lock: self.st[key]["made"] = True
        self.save()
        rc, out = self.pve.start(vmid)
        if rc != 0: return self.fail(key, "bật máy lỗi: " + out[-200:])
        log("MẪU-%d: đã bật — %s" % (jid, "Windows tự cài từ ISO (20–40 phút)" if it["src"] == "iso" else "chờ Windows lên để đưa vé"))

    def job_wait(self, vmid, cond, secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            if cond(): return True
            time.sleep(3)
        return cond()

    def _seal(self, key, lab, vmid, tpl, uniq):
        """Máy ảo đang chạy → máy mẫu <tpl>: xoá mã máy trong máy (qua guest agent) → tắt → gỡ ISO → máy mẫu cũ thành <tên>-cu → đặt tên → chuyển thành mẫu.
        True = xong; lỗi → ghi lỗi (self.fail) và trả None."""
        vm = self.pve.vms().get(vmid)
        if not vm: return self.fail(key, "không thấy máy ảo %d" % vmid)
        if vm["template"]: return True
        if vm["status"] != "running":
            rc, out = self.pve.start(vmid)
            if rc != 0: return self.fail(key, "bật máy để xoá mã máy lỗi: " + out[-200:])
        if not self.job_wait(vmid, lambda: self.pve.ga_ping(vmid), 600):
            return self.fail(key, "QEMU guest agent trong máy mẫu không trả lời — chưa xoá được mã máy, chưa lưu")
        lin = is_linux_tpl(tpl)
        if lin: self.pve.ga_exec(vmid, ["systemctl", "stop", "cloudblue.service"], 60)     # 27/11a · máy mẫu Linux
        else: self.pve.ga_exec(vmid, ["taskkill", "/f", "/im", "pythonw.exe"])            # dừng agent CloudBlue (để nó không ghi lại mã máy)
        for fn in ("identity.json", "seed.json", "rent.json"):
            rc, out = self.pve.ga_write(vmid, self.gpath(tpl, fn), "{}")
            if rc != 0 and fn == "identity.json": return self.fail(key, "xoá mã máy trong máy mẫu lỗi: " + out[-200:])
        if has_identity(self.pve.ga_read(vmid, self.gpath(tpl, "identity.json"))):
            return self.fail(key, "máy mẫu vẫn còn mã máy sau khi xoá — chưa lưu")
        if lin:                                                                   # tắt cloud-init (VPS nhân ra không chạy lại), xoá machine-id (mỗi VPS tự sinh mã riêng)
            rc, out = self.pve.ga_exec(vmid, ["sh", "-c", LIN_SEAL_SH], 120)
            if rc != 0: return self.fail(key, "dọn máy mẫu Linux lỗi: " + out[-200:])
        log("%s: đã xoá mã máy trong máy, tắt máy" % lab)
        rc, out = self.pve.shutdown(vmid)
        if not self.job_wait(vmid, lambda: (self.pve.vms().get(vmid) or {}).get("status") == "stopped", 300):
            rc, out = self.pve.stop(vmid)
            if not self.job_wait(vmid, lambda: (self.pve.vms().get(vmid) or {}).get("status") == "stopped", 60):
                return self.fail(key, "không tắt được máy mẫu: " + out[-200:])
        if lin:
            rc, out = self.pve.drop_ci(vmid)
            if rc != 0: return self.fail(key, "gỡ ổ cloud-init lỗi: " + out[-200:])
        for dev in self.pve.cdroms(vmid):
            rc, out = self.pve.eject(vmid, dev)
            if rc != 0: return self.fail(key, "gỡ ISO lỗi: " + out[-200:])
        vms = self.pve.vms()
        old = [k for k, v in vms.items() if v["name"] == tpl and k != vmid]
        if old:
            bak = tpl + "-cu"
            for k, v in vms.items():
                if v["name"] == bak and v["template"] and k != vmid:
                    rc, out = self.pve.destroy(k)                                   # bỏ bản lưu cũ hơn (còn VPS nhân bản liên kết thì đổi tên)
                    if rc != 0: self.pve.set_name(k, "%s-cu%s" % (tpl, uniq))
            for k in old:
                rc, out = self.pve.set_name(k, bak)
                if rc != 0: return self.fail(key, "đổi tên máy mẫu cũ lỗi: " + out[-200:])
            log("%s: máy mẫu cũ %s → %s (giữ 1 bản dự phòng)" % (lab, tpl, bak))
        rc, out = self.pve.set_name(vmid, tpl)
        if rc != 0: return self.fail(key, "đặt tên máy mẫu lỗi: " + out[-200:])
        rc, out = self.pve.make_template(vmid)
        if rc != 0: return self.fail(key, "chuyển thành máy mẫu lỗi: " + out[-200:])
        return True

    def job_save(self, it, vmid):
        """Lưu máy ảo tạm thành máy mẫu (việc từ bảng điều khiển máy mẫu trên web)."""
        jid = int(it["id"]); key = "t%d" % jid; tpl = it["tpl"]
        if not self._seal(key, "MẪU-%d" % jid, vmid, tpl, "%d" % jid): return
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "saved": True}
        self.save()
        log("MẪU-%d: ĐÃ LƯU máy mẫu %s (máy ảo %d)" % (jid, tpl, vmid))

    def job_cancel(self, jid, vmid):
        key = "t%d" % jid
        if vmid and vmid in self.pve.vms() and not self.pve.vms()[vmid]["template"]:
            log("MẪU-%d: huỷ — xoá máy ảo tạm %d" % (jid, vmid))
            rc, out = self.pve.destroy(vmid)
            if rc != 0: return self.fail(key, "xoá máy ảo tạm lỗi: " + out[-200:])
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "cancelled": True}
        self.save()

    def job_seed(self, key, vmid, it):
        s = self.st.get(key) or {}
        if not s.get("ticket") or not s.get("sent") or s.get("seeded") or not self.pve.ga_ping(vmid): return
        if has_identity(self.pve.ga_read(vmid, self.gpath(it["tpl"], "identity.json"))): return     # agent đã có mã máy (đăng ký rồi) → thôi
        rc, out = self.pve.ga_write(vmid, self.gpath(it["tpl"], "seed.json"), json.dumps({"hw": it["hw"], "ticket": s["ticket"]}))
        if rc != 0: return                                                                # Windows còn đang cài (agent chưa có) → lần sau
        with self.lock: s["seeded"] = True; s["t_seed"] = time.time()
        log("MẪU-%s: đã đưa vé vào máy mẫu → agent CloudBlue tự đăng ký" % key[1:]); self.save()

    def reconcile_jobs(self, vms, tpls):
        rep = []
        for it in self.jobs:
            if not job_ok(it): continue
            jid = int(it["id"]); key = "t%d" % jid; s = self.st.get(key)
            vmid = self.job_vmid(jid, vms); vm = vms.get(vmid) if vmid else None
            if key in self.busy: rep.append({"id": jid, "state": "saving" if it["want"] == "save" else "creating"}); continue
            if it["want"] == "cancel":
                if vm and not vm["template"]: self.bg(key, self.job_cancel, jid, vmid); continue
                if s is not None:
                    with self.lock: self.st.pop(key, None)
                    self.save()
                rep.append({"id": jid, "state": "cancelled"}); continue
            if s and s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                rep.append({"id": jid, "state": "error", "err": s["err"]}); continue
            if s and s.get("err"):
                with self.lock: s.pop("err", None)
            if it["want"] == "save":
                if (s or {}).get("saved") or (vm and vm["template"] and vm["name"] == it["tpl"]):
                    rep.append({"id": jid, "state": "saved"}); continue
                if not vm: rep.append({"id": jid, "state": "error", "err": "không thấy máy ảo của máy mẫu này trên máy chủ"}); continue
                self.bg(key, self.job_save, dict(it), vmid); rep.append({"id": jid, "state": "saving"}); continue
            if not vm:
                if (s or {}).get("made"): rep.append({"id": jid, "state": "missing"}); continue
                tid = tpls.get(it["tpl"]) if it["src"] == "tpl" else None
                if it["src"] == "tpl" and tid is None:
                    rep.append({"id": jid, "state": "error", "err": "máy chủ không có máy mẫu " + it["tpl"]}); continue
                self.bg(key, self.job_create, dict(it), tid); rep.append({"id": jid, "state": "creating"}); continue
            if vm["template"]: rep.append({"id": jid, "state": "error", "err": "máy ảo này đã thành máy mẫu"}); continue
            if s is None:                                                    # mất sổ (cài lại cbhost) → nhận lại máy ảo đang có
                s = {"vmid": vmid, "made": True, "ticket": None, "sent": False, "seeded": False}
                with self.lock: self.st[key] = s
                self.save()
            running = vm["status"] == "running"
            if not running:
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(key, "bật máy lỗi: " + out[-200:]); rep.append({"id": jid, "state": "error", "err": "bật máy lỗi"}); continue
                running = True
            r = {"id": jid, "state": "running"}
            if it.get("enrolled") is True:
                if s.get("ticket"):
                    with self.lock: s["ticket"] = None; s["sent"] = False; s["seeded"] = False
                    self.save()
            else:
                if not s.get("ticket"):
                    with self.lock: s["ticket"] = secrets.token_hex(24); s["sent"] = False; s["seeded"] = False
                    self.save()
                r["ticket_hash"] = hashlib.sha256(s["ticket"].encode()).hexdigest()
                if s.get("sent") and not s.get("seeded"): self.job_seed(key, vmid, it)
            rep.append(r)
        return rep

    # ---- TỰ DỰNG máy mẫu từ file ISO máy mẫu có trên máy chủ (cấu hình auto_tpl — ISO CloudBlue-Proxmox đặt sẵn): không cần web, không cần bấm
    def auto_create(self, tag, iso):
        key = "a" + tag; tpl = "tpl-" + tag
        vms = self.pve.vms()
        with self.lock:                                                # chọn số máy ảo + ghi sổ trong 1 lần khoá: 2 bản dựng cùng lúc không trùng số
            vmid = self.c["tpl_vmid_from"] + 500
            used = [int((x or {}).get("vmid") or 0) for k, x in self.st.items() if k[:1] in ("t", "a", "l") and k != key]
            while vmid in vms or vmid in used: vmid += 1
            s = self.st.setdefault(key, {}); s.pop("err", None)
            s.update({"vmid": vmid, "made": False, "t_build": time.time(), "tries": int(s.get("tries") or 0) + 1})
        self.save()
        stg = self.pve.image_storage()
        if not stg: return self.fail(key, "máy chủ không có ổ chứa máy ảo (images)")
        it = {"tpl": tpl, "iso": iso, "cores": 2, "ram_mb": 2048, "disk_gb": 20, "hw": hashlib.sha256(("cbauto|%s|%s" % (tag, self.sec)).encode()).hexdigest()}
        log("MẪU-%s: TỰ DỰNG — tạo máy ảo %d từ ISO %s" % (tag, vmid, iso))
        rc, out = self.pve.create_tpl_vm(vmid, "cbmau-" + tag, it, stg)
        if rc != 0: return self.fail(key, "tạo máy ảo lỗi: " + out[-200:])
        with self.lock: self.st[key]["made"] = True
        self.save()
        rc, out = self.pve.start(vmid)
        if rc != 0: return self.fail(key, "bật máy lỗi: " + out[-200:])
        log("MẪU-%s: đã bật — Windows tự cài từ ISO (20–40 phút), xong sẽ tự thành máy mẫu %s" % (tag, tpl))

    def auto_save(self, tag, vmid):
        key = "a" + tag; tpl = "tpl-" + tag
        if not self._seal(key, "MẪU-" + tag, vmid, tpl, tag): return
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "done": True, "t_done": time.time()}
        self.save()
        log("MẪU-%s: ĐÃ TỰ DỰNG XONG máy mẫu %s (máy ảo %d)" % (tag, tpl, vmid))

    def auto_drop(self, tag, vmid):
        key = "a" + tag
        log("MẪU-%s: quá %d giờ Windows chưa cài xong — xoá máy ảo %d để dựng lại" % (tag, AUTO_WAIT_S // 3600, vmid))
        rc, out = self.pve.stop(vmid)
        rc, out = self.pve.destroy(vmid)
        if rc != 0: return self.fail(key, "xoá máy ảo dựng dở lỗi: " + out[-200:])
        with self.lock: s = self.st.setdefault(key, {}); s["made"] = False; s.pop("vmid", None)
        self.save()

    def reconcile_auto(self, vms, tpls):
        res = []
        if not self.c["auto_tpl"]: return res
        for iso in self.iso_list:
            m = RX_AUTO_ISO.match(str((iso or {}).get("volid") or ""))
            if not m: continue
            tag = m.group(1); tpl = "tpl-" + tag; key = "a" + tag; s = self.st.get(key) or {}
            if key in self.busy: res.append({"tag": tag, "state": "working"}); continue
            if tpl in tpls or any(v["name"] == tpl for v in vms.values()):          # đã có máy mẫu này (hoặc máy ảo trùng tên) → không làm gì
                if s and not s.get("done"):
                    with self.lock: self.st[key] = {"vmid": s.get("vmid"), "made": True, "done": True}
                    self.save()
                continue
            if s.get("done") or s.get("off"):                                       # đã dựng xong 1 lần (máy mẫu bị xoá tay sau đó) / đã bỏ cuộc → không tự làm lại
                if s.get("off"): res.append({"tag": tag, "state": "error", "err": str(s.get("err") or "")[:120]})
                continue
            if any(job_ok(j) and j.get("tpl") == tpl and j.get("want") != "cancel" for j in self.jobs): continue     # admin đang dựng bản này trên web
            if s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                res.append({"tag": tag, "state": "error", "err": str(s["err"])[:120]}); continue
            vmid = s.get("vmid") if s.get("vmid") in vms else next((k for k, v in vms.items() if v["name"] == "cbmau-" + tag and not v["template"]), None)
            vm = vms.get(vmid) if vmid else None
            if not vm:
                if int(s.get("tries") or 0) >= AUTO_TRIES:
                    with self.lock: self.st.setdefault(key, {})["off"] = True
                    self.save(); log("MẪU-%s: tự dựng %d lần chưa được — thôi. Dựng tay ở web › VPS ảo hoá › Bản Windows › Bảng điều khiển máy mẫu." % (tag, AUTO_TRIES))
                    continue
                self.bg(key, self.auto_create, tag, iso["volid"]); res.append({"tag": tag, "state": "creating"}); continue
            if not s.get("vmid") or not s.get("made"):                              # mất sổ (cài lại cbhost) → nhận lại máy ảo đang có
                with self.lock:
                    s = self.st.setdefault(key, {}); s.update({"vmid": vmid, "made": True}); s.setdefault("t_build", time.time()); s.setdefault("tries", 1)
                self.save()
            if s.get("err"):
                with self.lock: s.pop("err", None)
            if vm["status"] != "running":                                           # máy tắt giữa chừng (mất điện …) → bật lại cho cài tiếp
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(key, "bật máy lỗi: " + out[-200:]); res.append({"tag": tag, "state": "error", "err": "bật máy lỗi"}); continue
            mins = int((time.time() - float(s.get("t_build") or time.time())) / 60)
            if time.time() - float(s.get("t_chk") or 0) >= AUTO_CHK_S:
                with self.lock: s["t_chk"] = time.time()
                if self.pve.ga_ping(vmid) and self.pve.ga_read(vmid, AUTO_DONE_F) is not None:
                    self.bg(key, self.auto_save, tag, vmid); res.append({"tag": tag, "state": "saving"}); continue
                if mins * 60 > AUTO_WAIT_S:
                    self.bg(key, self.auto_drop, tag, vmid); res.append({"tag": tag, "state": "working"}); continue
            res.append({"tag": tag, "state": "installing", "min": mins})
        return res

    # ---- 27/11a · TỰ DỰNG máy mẫu LINUX (Ubuntu 24.04 + XFCE + CloudBlue + OpenClaw) từ ảnh cloud chính chủ — không cần ISO, không cần web
    def linux_image(self, tag):
        """Tải ảnh cloud vào IMG_DIR, kiểm SHA-256 theo SHA256SUMS của nhà phát hành (đã có đúng file thì thôi). → đường dẫn. Lỗi → ném lỗi."""
        L = LINUX_TPLS[tag]
        os.makedirs(IMG_DIR, exist_ok=True)
        dst = os.path.join(IMG_DIR, L["file"])
        sums = http_get(L["base"] + "SHA256SUMS", 1 << 20).decode("utf-8", "replace")
        m = re.search(r"^([0-9a-f]{64}) [ *]?" + re.escape(L["file"]) + r"\s*$", sums, re.M)
        if not m: raise RuntimeError("SHA256SUMS không có %s" % L["file"])
        if os.path.isfile(dst) and sha256_file(dst) == m.group(1): return dst
        log("MẪU-%s: tải ảnh %s (%s) …" % (tag, L["file"], L["base"]))
        http_save(L["base"] + L["file"], dst + ".part")
        if sha256_file(dst + ".part") != m.group(1):
            os.remove(dst + ".part"); raise RuntimeError("ảnh %s tải về SAI mã kiểm SHA-256 — bỏ" % L["file"])
        os.replace(dst + ".part", dst)
        return dst

    def linux_userdata(self, tag):
        """cloud-init (file riêng, snippets): ghi /opt/cloudblue/cb.json (địa chỉ web + khoá CÔNG KHAI, chưa có mã đăng ký) rồi chạy linux-vm.sh."""
        cbj = {"ver": "vm-linux-" + CBHOST_VER, "role": "vm", "user": "vps", "sb_url": self.c["sb_url"], "sb_key": self.c["sb_key"], "password": "",
               "timezone": "SE Asia Standard Time", "update_base": "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/", "remote": True}
        b64 = base64.b64encode(json.dumps(cbj).encode()).decode()
        return ("#cloud-config\n# CloudBlue - dung may mau VPS NVMe Linux %s (cbhost %s)\nhostname: cloudblue-vps\ntimezone: Asia/Ho_Chi_Minh\nusers: []\n"
                "write_files:\n  - path: /opt/cloudblue/cb.json\n    permissions: '0600'\n    encoding: b64\n    content: %s\n"
                "runcmd:\n  - [bash, -c, \"curl -fsSL --retry 5 %s -o /root/cb-linux-vm.sh && bash /root/cb-linux-vm.sh\"]\n") % (tag, CBHOST_VER, b64, LIN_BOOT_URL)

    def linux_create(self, tag):
        key = "l" + tag
        vms = self.pve.vms()
        with self.lock:
            vmid = self.c["tpl_vmid_from"] + 600
            used = [int((x or {}).get("vmid") or 0) for k, x in self.st.items() if k[:1] in ("t", "a", "l") and k != key]
            while vmid in vms or vmid in used: vmid += 1
            s = self.st.setdefault(key, {}); s.pop("err", None)
            s.update({"vmid": vmid, "made": False, "t_build": time.time(), "tries": int(s.get("tries") or 0) + 1})
        self.save()
        stg = self.pve.image_storage()
        if not stg: return self.fail(key, "máy chủ không có ổ chứa máy ảo (images)")
        try: img = self.linux_image(tag)
        except Exception as e: return self.fail(key, "tải ảnh Ubuntu lỗi: %s" % str(e)[:200])
        rc, out = self.pve.snippets_ready()
        if rc != 0: return self.fail(key, "bật loại nội dung snippets cho ổ local lỗi: " + out[-200:])
        snip = "cloudblue-%s.yaml" % tag
        try:
            os.makedirs(SNIP_DIR, exist_ok=True)
            with open(os.path.join(SNIP_DIR, snip), "w", encoding="utf-8") as f: f.write(self.linux_userdata(tag))
        except OSError as e: return self.fail(key, "ghi file cloud-init lỗi: %s" % e)
        log("MẪU-%s: TỰ DỰNG — máy ảo %d từ ảnh %s (cloud-init: XFCE + CloudBlue + OpenClaw)" % (tag, vmid, os.path.basename(img)))
        rc, out = self.pve.create_lin_vm(vmid, "cbmau-" + tag, stg, img, hashlib.sha256(("cblin|%s|%s" % (tag, self.sec)).encode()).hexdigest(), snip)
        if rc != 0: return self.fail(key, "tạo máy ảo lỗi: " + out[-200:])
        with self.lock: self.st[key]["made"] = True
        self.save()
        rc, out = self.pve.start(vmid)
        if rc != 0: return self.fail(key, "bật máy lỗi: " + out[-200:])
        log("MẪU-%s: đã bật — tự cài giao diện + CloudBlue + OpenClaw (10–30 phút), xong tự thành máy mẫu tpl-%s" % (tag, tag))

    def linux_save(self, tag, vmid):
        key = "l" + tag
        if not self._seal(key, "MẪU-" + tag, vmid, "tpl-" + tag, tag): return
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "done": True, "t_done": time.time()}
        self.save()
        log("MẪU-%s: ĐÃ TỰ DỰNG XONG máy mẫu Linux tpl-%s (máy ảo %d)" % (tag, tag, vmid))

    def linux_drop(self, tag, vmid, why):
        key = "l" + tag
        log("MẪU-%s: %s — xoá máy ảo %d để dựng lại" % (tag, why, vmid))
        self.pve.stop(vmid)
        rc, out = self.pve.destroy(vmid)
        if rc != 0: return self.fail(key, "xoá máy ảo dựng dở lỗi: " + out[-200:])
        with self.lock: s = self.st.setdefault(key, {}); s["made"] = False; s.pop("vmid", None)
        self.save()

    def linux_tags(self):
        """Máy mẫu Linux cần tự dựng: theo cấu hình + (27/11b) bản Linux admin đã bật trên web (tpl_need) nếu cấu hình không ghi rõ."""
        tags = list(self.c["linux_tpl"])
        if self.c.get("linux_web"): tags += [t for t in LINUX_TPLS if "tpl-" + t in self.tpl_need and t not in tags]
        return tags

    def iso_sync(self, vms):
        """27/11d · đặt luật cách ly cho card mạng của mọi VPS (máy ảo số ≥ vmid_base, không phải máy mẫu). Đổi danh sách VPS / 10 phút → đặt lại."""
        ifs = set()
        for vid_, v in vms.items():
            if v.get("template") or int(vid_) < int(self.c["vmid_base"]): continue
            ifs.update({"tap%di0" % int(vid_), "fwpr%dp0" % int(vid_)})
        gw = default_gw(); key = (tuple(sorted(ifs)), gw)
        if key == self.iso_key and time.time() - self.iso_at < ISO_EVERY: return
        rc, out = run_in([NFT, "-f", "-"], iso_ruleset(ifs, gw), 30)
        self.iso_at = time.time()
        if rc == 0:
            if key != self.iso_key: log("cách ly VPS: đã đặt luật cho %d VPS (cổng mạng %s)" % (len(ifs) // 2, gw or "?"))
            self.iso_key = key; self.iso_state = {"ok": True, "n": len(ifs) // 2}
        else:
            self.iso_key = None; self.iso_state = {"ok": False, "err": (out or "")[-160:]}
            log("cách ly VPS: đặt luật nftables lỗi: %s" % (out or "")[-200:])

    def reconcile_linux(self, vms, tpls):
        res = []
        for tag in self.linux_tags():
            tpl = "tpl-" + tag; key = "l" + tag; s = self.st.get(key) or {}
            if key in self.busy: res.append({"tag": tag, "state": "working"}); continue
            if tpl in tpls or any(v["name"] == tpl for v in vms.values()):
                if s and not s.get("done"):
                    with self.lock: self.st[key] = {"vmid": s.get("vmid"), "made": True, "done": True}
                    self.save()
                continue
            if s.get("done") or s.get("off"):
                if s.get("off"): res.append({"tag": tag, "state": "error", "err": str(s.get("err") or "")[:120]})
                continue
            if any(job_ok(j) and j.get("tpl") == tpl and j.get("want") != "cancel" for j in self.jobs): continue
            if s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                res.append({"tag": tag, "state": "error", "err": str(s["err"])[:120]}); continue
            vmid = s.get("vmid") if s.get("vmid") in vms else next((k for k, v in vms.items() if v["name"] == "cbmau-" + tag and not v["template"]), None)
            vm = vms.get(vmid) if vmid else None
            if not vm:
                if int(s.get("tries") or 0) >= AUTO_TRIES:
                    with self.lock: self.st.setdefault(key, {})["off"] = True
                    self.save(); log("MẪU-%s: tự dựng %d lần chưa được — thôi." % (tag, AUTO_TRIES)); continue
                self.bg(key, self.linux_create, tag); res.append({"tag": tag, "state": "creating"}); continue
            if not s.get("vmid") or not s.get("made"):
                with self.lock:
                    s = self.st.setdefault(key, {}); s.update({"vmid": vmid, "made": True}); s.setdefault("t_build", time.time()); s.setdefault("tries", 1)
                self.save()
            if s.get("err"):
                with self.lock: s.pop("err", None)
            if vm["status"] != "running":
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(key, "bật máy lỗi: " + out[-200:]); res.append({"tag": tag, "state": "error", "err": "bật máy lỗi"}); continue
            mins = int((time.time() - float(s.get("t_build") or time.time())) / 60)
            if time.time() - float(s.get("t_chk") or 0) >= AUTO_CHK_S:
                with self.lock: s["t_chk"] = time.time()
                if self.pve.ga_ping(vmid):
                    if self.pve.ga_read(vmid, LIN_DONE_F) is not None:
                        self.bg(key, self.linux_save, tag, vmid); res.append({"tag": tag, "state": "saving"}); continue
                    bad = self.pve.ga_read(vmid, LIN_FAIL_F)
                    if bad:
                        self.fail(key, "cài máy mẫu Linux lỗi: " + bad.strip()[:200])
                        self.bg(key, self.linux_drop, tag, vmid, "cài lỗi"); res.append({"tag": tag, "state": "error", "err": bad.strip()[:120]}); continue
                if mins * 60 > LIN_WAIT_S:
                    self.bg(key, self.linux_drop, tag, vmid, "quá %d giờ chưa xong" % (LIN_WAIT_S // 3600)); res.append({"tag": tag, "state": "working"}); continue
            res.append({"tag": tag, "state": "installing", "min": mins})
        return res

    # ---- 1 vòng: so trạng thái web muốn với máy ảo thật
    def reconcile(self, vms, tpls):
        rep = []
        for it in self.want:
            if not item_ok(it): continue
            vid = int(it["id"]); vmid = self.vmid(vid); vm = vms.get(vmid); s = self.st.get(str(vid))
            if vid in self.busy:
                if vid in self.soft and vm and s:                   # đổi cấu hình / nới ổ C đang chạy nền: máy vẫn dùng bình thường
                    if it.get("enrolled") is True and s.get("ticket"):
                        with self.lock: s["ticket"] = None; s["sent"] = False; s["seeded"] = False
                        self.save()
                    rep.append(self.rep_now(vid, vm, s))
                else: rep.append({"id": vid, "state": "creating", "inst": (s or {}).get("inst") or 0})
                continue
            if it["want"] == "deleted":
                if vm: self.bg(vid, self.remove, vid, light=True); rep.append({"id": vid, "state": "stopped", "inst": (s or {}).get("inst") or 0})
                else:
                    if s is not None:
                        with self.lock: self.st.pop(str(vid), None)
                        self.save()
                    rep.append({"id": vid, "state": "missing", "inst": int(it["inst"])})
                continue
            if s and s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                rep.append({"id": vid, "state": "error", "inst": s.get("inst") or 0, "err": s["err"]}); continue
            if vm and s is None:                                    # máy ảo có sẵn mà mất sổ (cài lại cbhost) → nhận lại, không tạo lại
                s = {"inst": int(it["inst"]), "boot": int(it["boot"]), "ticket": None, "sent": False, "seeded": False}   # (không ghi "cfg": web có lần đổi cấu hình thì đặt lại cho chắc — không đổi gì thì không tắt máy)
                with self.lock: self.st[str(vid)] = s
                self.save()
            if not vm or int(s.get("inst") or 0) != int(it["inst"]):
                tid = tpls.get(it["tpl"])
                if tid is None:
                    rep.append({"id": vid, "state": "error", "inst": (s or {}).get("inst") or 0, "err": "máy chủ thiếu máy mẫu " + it["tpl"]}); continue
                self.bg(vid, self.build, dict(it), tid)
                rep.append({"id": vid, "state": "creating", "inst": (s or {}).get("inst") or 0}); continue
            if s.get("err"):
                with self.lock: s.pop("err", None)
            running = vm["status"] == "running"
            if it["want"] == "running" and not running:
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(vid, "bật máy lỗi: " + out[-200:])
                else: running = True; log("VPS-%s: bật máy ảo" % vid)
            elif it["want"] == "stopped" and running:
                rc, out = self.pve.shutdown(vmid)
                if rc != 0: self.fail(vid, "tắt máy lỗi: " + out[-200:])
                else: running = False; log("VPS-%s: tắt máy ảo" % vid)
            if int(it["boot"]) != int(s.get("boot") or 0):
                if running:
                    rc, out = self.pve.reset(vmid)
                    if rc != 0: self.fail(vid, "khởi động cứng lỗi: " + out[-200:])
                    else: log("VPS-%s: khởi động cứng" % vid)
                with self.lock: s["boot"] = int(it["boot"])
                self.save()
            cfg_w = int(it.get("cfg") or 0)
            if cfg_w > int(s.get("cfg") or 0):                      # 26/11e: web vừa đổi cấu hình (nâng cấp) → đặt ở luồng riêng; xong mới báo "cfg"
                self.bg(vid, self.recfg, dict(it), soft=True)
                rep.append(self.rep_now(vid, vm, s)); continue
            g = s.get("grow")
            if g and running and (it.get("enrolled") is True or s.get("seeded")) and time.time() - float(g.get("t") or 0) >= GROW_EVERY_S:
                self.bg(vid, self.grow, vid, soft=True)             # (máy mới tạo: đưa vé đăng ký xong mới nới ổ C)
            r = {"id": vid, "state": "running" if running else "stopped", "inst": int(s.get("inst") or 0), "boot": int(s.get("boot") or 0)}
            if not (g and running): r["cfg"] = int(s.get("cfg") or 0)       # ổ C còn đang nới trong Windows → chưa báo xong (web còn hiện "đang đổi cấu hình")
            if it.get("enrolled") is True:
                if s.get("ticket"):
                    with self.lock: s["ticket"] = None; s["sent"] = False; s["seeded"] = False
                    self.save()
            else:
                if not s.get("ticket"):
                    with self.lock: s["ticket"] = secrets.token_hex(24); s["sent"] = False; s["seeded"] = False
                    self.save()
                r["ticket_hash"] = hashlib.sha256(s["ticket"].encode()).hexdigest()
                if running and s.get("sent") and not s.get("seeded"): self.seed(vid, it)
            rep.append(r)
        return rep

    def poll_once(self, act=True):
        vms = self.pve.vms()
        tpls = {}
        for vid_, v in vms.items():
            if v["template"] and RX_TPL.match(v["name"]): tpls.setdefault(v["name"], vid_)
        if time.time() - self.iso_t > ISO_EVERY_S:
            try: self.iso_list = self.pve.isos()
            except Exception as e: log("đọc danh sách ISO lỗi: %s" % e)
            self.iso_t = time.time()
        if act and self.c["vps_iso"]:
            try: self.iso_sync(vms)
            except Exception as e: self.iso_state = {"ok": False, "err": str(e)[:160]}
        self.auto = self.reconcile_auto(vms, tpls) if act else []    # tự dựng máy mẫu: không phụ thuộc web
        if act: self.auto += self.reconcile_linux(vms, tpls)          # 27/11a · máy mẫu Linux (Ubuntu + OpenClaw)
        if not self.hello_ok:
            r = self.web.rpc("vm_host_hello", {"p_secret": self.sec, "p_info": self.pve.info()})
            if not r or not r.get("ok"):
                log("chưa lên web được: %s" % ((r or {}).get("err") or self.web.err)); return False
            self.hello_ok, self.status, self.name, self.info_t = True, r.get("status"), r.get("name"), time.time()
            log("đã lên web: máy chủ %s (%s)%s" % (self.name, r.get("id"), " — CHỜ admin duyệt ở Quản trị › VPS ảo hoá" if self.status == "new" else ""))
        rep = self.reconcile(vms, tpls) if act and self.status != "new" else []
        trep = self.reconcile_jobs(vms, tpls) if act and self.status != "new" and self.jobs_ok else []
        mem = meminfo()
        metrics = {"cpu": cpu_pct(), "ram_used_mb": int((mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) / 1024),
                   "running": sum(1 for x in vms.values() if x["status"] == "running" and not x["template"]),
                   "tpl": sorted(t for t in tpls if t in self.tpl_need or not self.tpl_need), "iso": self.iso_list, "ver": CBHOST_VER}
        if self.auto: metrics["tpl_auto"] = self.auto[:8]
        if self.iso_state: metrics["vps_fw"] = dict(self.iso_state)            # 27/11d · cách ly VPS: đặt được chưa
        if self.usb is not None and self.usb.state: metrics["usb"] = dict(self.usb.state)     # đang chép / đã chép / lỗi chép ISO máy mẫu từ USB
        try: px = self.pool.step(act)                                       # 27/11e · kho proxy nhiều IP
        except Exception as e: px = {"ok": False, "err": str(e)[:160]}
        if px: metrics["px"] = px
        while len(json.dumps(metrics)) > 12000 and (metrics.get("tpl_auto") or metrics["iso"] or len((metrics.get("px") or {}).get("s") or []) > 5):
            if metrics.get("tpl_auto"): metrics.pop("tpl_auto")              # web bỏ CẢ gói số đo nếu quá 16 KB → cắt bớt phần phụ
            elif len((metrics.get("px") or {}).get("s") or []) > 5: metrics["px"]["s"] = metrics["px"]["s"][:len(metrics["px"]["s"]) // 2]; metrics["px"]["cut"] = 1
            else: metrics["iso"] = metrics["iso"][:len(metrics["iso"]) // 2]
        body = {"p_secret": self.sec, "p_metrics": metrics, "p_vps": rep, "p_info": None}
        if self.jobs_ok: body["p_tpl"] = trep                     # web cũ (chưa chạy v57) không có tham số này
        if time.time() - self.info_t > 600: body["p_info"] = self.pve.info(); self.info_t = time.time()
        r = self.web.rpc("vm_host_poll", body)
        if not r or not r.get("ok"):
            if r and r.get("err") == "BAD_SECRET": self.hello_ok = False
            log("hỏi việc lỗi: %s" % ((r or {}).get("err") or self.web.err)); return False
        for x in rep if act else []:                               # web đã nhận dấu băm vé → giờ mới được đưa vé vào máy ảo
            if x.get("ticket_hash"):
                s = self.st.get(str(x["id"]))
                if s and s.get("ticket") and hashlib.sha256(s["ticket"].encode()).hexdigest() == x["ticket_hash"] and not s.get("sent"):
                    with self.lock: s["sent"] = True
                    self.save()
        for x in trep if act else []:                              # vé máy mẫu: như VPS
            if x.get("ticket_hash"):
                s = self.st.get("t%d" % x["id"])
                if s and s.get("ticket") and hashlib.sha256(s["ticket"].encode()).hexdigest() == x["ticket_hash"] and not s.get("sent"):
                    with self.lock: s["sent"] = True
                    self.save()
        for x in trep if act else []:                              # web đã ghi nhận lưu / huỷ xong → quên sổ
            if x.get("state") in ("saved", "cancelled") and not any(int(j.get("id") or 0) == x["id"] for j in (r.get("tpl_jobs") or []) if isinstance(j, dict)):
                with self.lock: self.st.pop("t%d" % x["id"], None)
                self.save()
        self.status, self.name = r.get("status") or self.status, r.get("name") or self.name
        self.want = r.get("vps") if isinstance(r.get("vps"), list) else []
        self.jobs_ok = isinstance(r.get("tpl_jobs"), list)
        self.jobs = r.get("tpl_jobs") if self.jobs_ok else []
        self.tpl_need = [t for t in (r.get("tpl") or []) if isinstance(t, str) and RX_TPL.match(t)]
        try: self.poll_s = max(5, min(120, int(r.get("poll_s") or 10)))
        except (TypeError, ValueError): self.poll_s = 10
        return True


# ---------------------------------------------------------------- nạp ISO máy mẫu từ USB cắm vào máy chủ ĐANG CHẠY (26/11d)
# ISO CloudBlue-Proxmox ghép thiếu ISO máy mẫu (hoặc muốn thêm bản Windows sau) → KHÔNG phải cài lại máy chủ: cắm USB vào là máy chủ tự chép. Nhận 2 kiểu USB:
#   (1) USB cài đặt CloudBlue-Proxmox bản CÓ kèm máy mẫu (Rufus, DD) — kể cả USB ghép sau lần cài máy này: đọc cấu hình kho trong file proxmox-first-boot của USB,
#       rồi nhờ cb_nap.py chép (kiểm SHA-256 từng file);
#   (2) USB thường (exFAT / NTFS / FAT32 / ext) có file CloudBlue-MayMau-*.iso (thư mục gốc hoặc sâu 2 cấp).
# Chỉ ĐỌC ổ USB / ổ tháo rời chưa gắn phần nào, không thuộc LVM / ZFS / RAID. File vào kho ISO xong thì phần tự dựng máy mẫu (auto_tpl) tự chạy.
def _flat(node):
    yield node
    for ch in node.get("children") or []:
        for x in _flat(ch): yield x


def usb_disks():
    """Ổ USB / ổ tháo rời KHÔNG gắn phần nào → [{path, size, nodes: [(đường dẫn, kiểu hệ tệp)]}]"""
    rc, out = run(["lsblk", "-J", "-b", "-o", "NAME,TYPE,FSTYPE,MOUNTPOINT,PATH,TRAN,RM,SIZE"], 30)
    try: devs = (json.loads(out).get("blockdevices") or []) if rc == 0 else []
    except Exception: devs = []
    res = []
    for d in devs:
        if not isinstance(d, dict) or d.get("type") != "disk" or not (d.get("tran") == "usb" or d.get("rm") in (True, 1, "1")) or not d.get("path"): continue
        nodes = [n for n in _flat(d) if isinstance(n, dict)]
        if any(n.get("mountpoint") or (n.get("fstype") or "") in ("LVM2_member", "zfs_member", "linux_raid_member", "swap") for n in nodes): continue
        try: size = int(d.get("size") or 0)
        except (TypeError, ValueError): size = 0
        res.append({"path": str(d["path"]), "size": size, "nodes": [(str(n["path"]), str(n.get("fstype") or "")) for n in nodes if n.get("path")]})
    return res


def usb_mount(dev, fst, opt, mp):
    try: os.makedirs(mp, exist_ok=True)
    except OSError: return False
    return run(["mount", "-t", fst, "-o", opt + ",nosuid,nodev,noexec", dev, mp], 60)[0] == 0


def usb_umount(mp):
    run(["umount", mp], 60)


def usb_kho_conf(mp):
    """Thư mục gốc 1 USB cài đặt CloudBlue-Proxmox (đang gắn ở mp) → cấu hình kho ISO máy mẫu {id, off, size, n}; không phải / không kèm máy mẫu → None"""
    try:
        with open(os.path.join(mp, "proxmox-first-boot"), "r", encoding="utf-8", errors="replace") as f: txt = f.read(4000000)
    except OSError:
        return None
    m = re.search(r"nap\.json\" 600 <<'CB_B64_EOF'\n([A-Za-z0-9+/=\n]{8,4000})\nCB_B64_EOF", txt)
    if not m: return None
    try: c = json.loads(base64.b64decode(m.group(1).replace("\n", "")).decode("utf-8"))
    except Exception: return None
    if not (isinstance(c, dict) and isinstance(c.get("id"), str) and re.fullmatch(r"[0-9A-Za-z_.-]{4,80}", c["id"]) and isinstance(c.get("off"), int) and isinstance(c.get("size"), int)
            and isinstance(c.get("n"), int) and c["n"] > 0 and 0 < c["off"] < c["size"]): return None
    return {"id": c["id"], "off": c["off"], "size": c["size"], "n": c["n"]}


def kho_files(dev, kc):
    """Đầu mục kho trên thiết bị → [{name, size}]; không đọc được / không khớp mã kho → None"""
    try:
        with open(dev, "rb") as f:
            f.seek(kc["off"]); hdr = f.read(KHO_HDR)
    except (OSError, ValueError):
        return None
    if not hdr.startswith(KHO_MAGIC) or b"\n" not in hdr[len(KHO_MAGIC):]: return None
    try: m = json.loads(hdr[len(KHO_MAGIC):hdr.index(b"\n", len(KHO_MAGIC))].decode("utf-8"))
    except (ValueError, UnicodeDecodeError): return None
    if not isinstance(m, dict) or m.get("id") != kc["id"] or not isinstance(m.get("files"), list): return None
    return [{"name": x["name"], "size": x["size"]} for x in m["files"]
            if isinstance(x, dict) and isinstance(x.get("name"), str) and RX_MAU_F.match(x["name"]) and isinstance(x.get("size"), int) and x["size"] > 0]


def iso_have(name, size):
    p = os.path.join(ISO_DIR, name)
    try: return os.path.isfile(p) and os.path.getsize(p) == size
    except OSError: return False


def nap_src(dev, kc):
    """Nhờ cb_nap.py chép kho từ thiết bị (kiểm SHA-256 từng file, file có sẵn thì bỏ qua) → (đủ?, mấy dòng cuối)"""
    os.makedirs(USB_MNT, exist_ok=True)
    cf = os.path.join(USB_MNT, "nap.json")
    with open(cf, "w") as f: json.dump(kc, f)
    env = dict(os.environ, CBNAP_CONF=cf, CBNAP_DONE=os.path.join(USB_MNT, "nap-xong.json"), CBNAP_DEST=ISO_DIR, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        r = subprocess.run([sys.executable or "python3", NAP_PY, "--src", dev], capture_output=True, text=True, timeout=6 * 3600, env=env)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]
    except subprocess.TimeoutExpired:
        return False, "quá giờ chờ (6 giờ)"
    except OSError as e:
        return False, str(e)


def usb_find_files(mp):
    """File CloudBlue-MayMau-*.iso trên phân vùng đang gắn (thư mục gốc + sâu 2 cấp) → [đường dẫn]"""
    res = []
    for base, dirs, names in os.walk(mp):
        if base[len(mp):].count(os.sep) >= 2: dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(("$", ".")) and d.lower() != "system volume information"]
        for nm in names:
            if RX_MAU_F.match(nm): res.append(os.path.join(base, nm))
    return sorted(res)[:20]


def usb_copy_file(src, dst):
    """Chép 1 file ISO máy mẫu vào kho ISO (qua file .part; đủ số byte mới đổi tên)."""
    size = os.path.getsize(src)
    if size < MAU_MIN: raise IOError("file quá nhỏ, không phải ISO máy mẫu")
    free = shutil.disk_usage(os.path.dirname(dst)).free
    if free < size + 2**30: raise IOError("kho ISO không đủ chỗ: cần %.1f GB, còn %.1f GB" % (size / 2**30, free / 2**30))
    part = dst + ".part"
    try:
        n = 0
        with open(src, "rb") as f, open(part, "wb") as o:
            while True:
                b = f.read(4 * 1024 * 1024)
                if not b: break
                o.write(b); n += len(b)
            o.flush(); os.fsync(o.fileno())
        if n != size: raise IOError("đọc USB thiếu dữ liệu (%d / %d byte)" % (n, size))
        os.chmod(part, 0o644); os.replace(part, dst)
    except BaseException:
        try: os.remove(part)
        except OSError: pass
        raise


class UsbNap(threading.Thread):
    """Luồng nền của dịch vụ: USB có ISO máy mẫu cắm vào lúc nào cũng tự chép vào kho ISO (không cần cài lại máy chủ)."""
    def __init__(self, c, say=None):
        threading.Thread.__init__(self, daemon=True)
        self.c, self.say = c, say or tty_say
        self.seen = {}; self.state = {}

    def run(self):
        time.sleep(15)
        while True:
            try: self.step()
            except Exception as e: log("USB máy mẫu: lỗi vòng — %s" % str(e)[:160])
            time.sleep(USB_EVERY_S)

    def step(self):
        live = set()
        for d in usb_disks():
            key = "%s:%d" % (d["path"], d["size"]); live.add(key)
            if self.seen.get(key, 0) > time.time(): continue
            r = self.one(d)
            self.seen[key] = time.time() + (USB_AGAIN_S if r is not False else 60)
        for k in [k for k in self.seen if k not in live]: del self.seen[k]      # rút ra → quên; cắm lại là xem ngay

    def set(self, st, msg):
        self.state = {"s": st, "msg": msg[:200], "t": int(time.time())}
        log("USB máy mẫu: " + msg)
        try: self.say("USB: " + msg)
        except Exception: pass

    def one(self, d):
        """→ True (kho ISO đã đủ mọi file của USB này) | None (USB không có ISO máy mẫu / bên khác đang lo) | False (lỗi — 1 phút sau thử lại)"""
        mp = os.path.join(USB_MNT, "m")
        kc = None
        for path, fst in d["nodes"]:                                            # (1) USB cài đặt CloudBlue-Proxmox ghi kiểu DD
            if fst != "iso9660": continue
            if not usb_mount(path, "iso9660", "ro", mp): continue
            try: kc = usb_kho_conf(mp)
            finally: usb_umount(mp)
            break
        if kc:
            if load_json(NAP_CONF_F, {}).get("id") == kc["id"] and not os.path.exists(NAP_DONE_F): return None      # USB của chính lần cài này: dịch vụ cloudblue-nap đang chép
            files = kho_files(d["path"], kc)
            if not files:
                self.set("err", "USB %s: không đọc được kho ISO máy mẫu (USB ghi lỗi?) — ghi lại USB bằng Rufus (DD Image) rồi cắm lại" % d["path"]); return False
            need = [x for x in files if not iso_have(x["name"], x["size"])]
            if not need: return True
            self.set("copy", "thấy %d ISO máy mẫu trên USB cài đặt — đang chép %d file (%.1f GB) vào máy chủ, ĐỪNG rút USB" % (len(files), len(need), sum(x["size"] for x in need) / 2**30))
            ok, out = nap_src(d["path"], kc)
            if ok and all(iso_have(x["name"], x["size"]) for x in files):
                self.set("done", "đã chép xong %d ISO máy mẫu — máy chủ tự dựng máy mẫu (mỗi bản 20-40 phút), có thể rút USB" % len(files)); return True
            self.set("err", "chép ISO máy mẫu từ USB CHƯA được (%s) — 1 phút sau thử lại" % ((out.splitlines() or ["?"])[-1][:120])); return False
        found = copied = 0
        for path, fst in d["nodes"]:                                            # (2) USB thường có file CloudBlue-MayMau-*.iso
            if fst not in USB_FS: continue
            if not usb_mount(path, USB_FS[fst][0], USB_FS[fst][1], mp): continue
            try:
                for src in usb_find_files(mp):
                    found += 1
                    name = os.path.basename(src); dst = os.path.join(ISO_DIR, name); size = os.path.getsize(src)
                    if iso_have(name, size): continue
                    try:
                        if time.time() - os.path.getmtime(dst + ".part") < 120: return False          # bên khác đang ghi file này
                    except OSError: pass
                    self.set("copy", "đang chép %s (%.1f GB) từ USB vào máy chủ, ĐỪNG rút USB" % (name, size / 2**30))
                    os.makedirs(ISO_DIR, exist_ok=True)
                    usb_copy_file(src, dst); copied += 1
            except (OSError, IOError) as e:
                self.set("err", "chép ISO máy mẫu từ USB lỗi (%s) — 1 phút sau thử lại" % str(e)[:120]); return False
            finally:
                usb_umount(mp)
        if copied: self.set("done", "đã chép xong %d ISO máy mẫu — máy chủ tự dựng máy mẫu (mỗi bản 20-40 phút), có thể rút USB" % copied)
        return True if found else None


# ---------------------------------------------------------------- tự cập nhật
def fetch_update(url=None):
    """Bản cbhost.py trên GitHub → (bản, nội dung) nếu KHÁC bản đang chạy và biên dịch được; không thì None."""
    req = urllib.request.Request((url or UPD_URL) + ("" if (url or UPD_URL).startswith("file:") else "?t=%d" % int(time.time())),
                                 headers={"User-Agent": "CloudBlue-cbhost/" + CBHOST_VER, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r: raw = r.read(2_000_001)
    if not 2000 <= len(raw) <= 2_000_000: return None
    txt = raw.decode("utf-8")
    m = re.search(r'^CBHOST_VER = "([0-9A-Za-z/._-]{1,20})"$', txt, re.M)
    if not m or m.group(1) == CBHOST_VER or "def poll_once" not in txt: return None
    compile(txt, "cbhost.py", "exec")                               # lỗi cú pháp → ném lỗi, giữ bản cũ
    return m.group(1), txt


def apply_update(ver, txt, path=None):
    path = path or os.path.abspath(__file__)
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as f: f.write(txt)
    os.chmod(tmp, 0o755); os.replace(tmp, path)
    log("đã cập nhật cbhost %s → %s" % (CBHOST_VER, ver))


def update_due(h, t_now, last):
    """Đến lúc xem bản mới chưa: dịch vụ systemd (có INVOCATION_ID), bật tự cập nhật, 15 phút / lần, không có máy ảo nào đang dựng / xoá."""
    return (h.c.get("auto_update") and bool(os.environ.get("INVOCATION_ID")) and t_now - last >= UPD_EVERY_S and not h.busy
            and not (h.usb is not None and h.usb.state.get("s") == "copy"))


def cmd_run():
    h = Host()
    log("cbhost %s chạy — node %s, gọi %s mỗi ~10 giây" % (CBHOST_VER, h.pve.node, h.web.url))
    last_upd = time.time() - UPD_EVERY_S + 120                     # bật lên 2 phút sau mới xem bản mới lần đầu
    nw, scr = NetWatch(h.c), Screen(h.c)
    if h.c["auto_tpl"]:                                             # máy cài bằng ISO CloudBlue-Proxmox: USB có ISO máy mẫu cắm lúc nào cũng tự chép
        try: h.usb = UsbNap(h.c); h.usb.start()
        except Exception as e: log("không bật được phần nạp ISO từ USB: %s" % str(e)[:120])
    try:
        if h.c["net_heal"] and os.path.exists(DHCP_UNIT_F) and bridge_ipv4(h.c["bridge"]) == "v4":      # admin đã đặt IPv4 cho cầu → gỡ dịch vụ xin DHCP tạm
            log("mạng: " + ensure_dhcp4(h.c["bridge"]))
    except Exception as e: log("xem dịch vụ cloudblue-dhcp4 lỗi: %s" % str(e)[:120])
    while True:
        ok = None
        try: ok = h.poll_once()
        except Exception as e: log("lỗi vòng:", e)
        try: scr.step(ok, h)
        except Exception: pass
        for x in nw.step(ok, h.web.err):
            log("TỰ SỬA MẠNG (lượt %d): %s" % (nw.heals, x)); scr.healed(nw.heals, x)
        if update_due(h, time.time(), last_upd):
            last_upd = time.time()
            try:
                u = fetch_update()
                if u:
                    apply_update(*u)
                    return 0                                        # dịch vụ (Restart=always) tự bật lại bằng bản mới
            except Exception as e:
                log("xem bản mới lỗi (giữ bản đang chạy): %s" % str(e)[:160])
        time.sleep(h.poll_s)


def cmd_update():
    try: u = fetch_update()
    except Exception as e:
        print("không lấy được bản mới: %s" % str(e)[:200]); return 1
    if not u: print("đang là bản mới nhất (%s)" % CBHOST_VER); return 0
    apply_update(*u)
    print("đã cập nhật %s → %s — bật lại dịch vụ: systemctl restart cloudblue-cbhost" % (CBHOST_VER, u[0])); return 0


def net_report(c):
    v4, v6 = default_routes()
    try: dns = resolv_servers(open(RESOLV_F, encoding="utf-8", errors="replace").read())
    except OSError: dns = []
    host = web_host(c)
    res = "địa chỉ số" if (not host or is_ip(host)) else ("được" if can_resolve(host) else "KHÔNG ĐƯỢC")
    return "mạng: IPv4 %s · IPv6 %s · địa chỉ %s · máy chủ tên (DNS) %s · phân giải tên web: %s · tự sửa mạng: %s" % (
        "có" if v4 else "KHÔNG", "có" if v6 else "không", lan_ip() or "?", ", ".join(dns) or "(trống)", res, "bật" if c.get("net_heal") else "tắt")


def cmd_net():
    """Xem tình trạng mạng + chạy NGAY 1 lượt tự sửa (như dịch vụ làm khi không gọi được web)."""
    c = conf()
    print(net_report(c))
    did = net_heal(c, 3)
    for x in did: print("đã sửa: " + x)
    if did: print(net_report(c))
    else: print("không có gì phải sửa (hoặc không sửa tự động được)")
    return 0


def cmd_status():
    h = Host(); ok = h.poll_once(act=False)                       # chỉ xem: không tạo / xoá gì (dịch vụ đang chạy lo việc đó)
    vms = h.pve.vms()
    tp = sorted(v["name"] for v in vms.values() if v["template"])
    print("cbhost %s · máy chủ: %s · trạng thái web: %s" % (CBHOST_VER, h.name or "?", {"new": "CHỜ DUYỆT (Quản trị › VPS ảo hoá › Máy chủ)", "ready": "đang nhận VPS",
          "maint": "bảo trì (không nhận VPS mới)", "off": "tắt"}.get(h.status, h.status) if ok else "chưa gọi được web (%s)" % h.web.err))
    try: print(net_report(h.c))
    except Exception as e: print("mạng: không đọc được (%s)" % str(e)[:80])
    print("máy mẫu trên Proxmox: %s" % (", ".join(tp) or "CHƯA CÓ — xem hướng dẫn dựng máy mẫu Windows"))
    if h.tpl_need: print("web cần máy mẫu: %s" % ", ".join(("%s ✓" if t in tp else "%s ✗ (thiếu)") % t for t in h.tpl_need))
    print("VPS web giao cho máy chủ này: %d" % len(h.want))
    if h.c["auto_tpl"]:
        au = {k[1:]: v for k, v in h.st.items() if k[:1] == "a" and isinstance(v, dict)}
        print("tự dựng máy mẫu từ ISO: BẬT%s" % ("".join(" · %s: %s" % (t, "xong" if v.get("done") else ("LỖI — " + str(v.get("err"))[:80]) if v.get("err") else
              "đang cài Windows (máy ảo %s)" % v.get("vmid")) for t, v in sorted(au.items())) or " · chưa có ISO máy mẫu nào trong kho ISO"))
    return 0 if ok else 1


def main(argv):
    cmd = argv[0] if argv else "run"
    if cmd == "run": return cmd_run()
    if cmd == "status": return cmd_status()
    if cmd == "once": return 0 if Host().poll_once() else 1
    if cmd == "update": return cmd_update()
    if cmd == "net": return cmd_net()
    if cmd in ("-v", "--version", "version"): print(CBHOST_VER); return 0
    print("Lệnh: run | status | once | update | net | version"); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
