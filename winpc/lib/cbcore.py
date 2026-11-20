# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbcore.py — phần TÍNH TOÁN của bộ cài máy PC CloudBlue (không đụng Windows trực tiếp → thử được trên máy nào cũng được)
#    · chọn ổ đích          · kịch bản chia ổ (diskpart) cho cài mới / cài lại      · lệnh tạo mục khởi động "cài lại" (BCD)
#    · file trả lời (unattend.xml) cho Windows mới                               · file lệnh (job.json) trên phân vùng cứu hộ
#  Mọi việc đụng máy thật đi qua đối tượng `sysx` (cbsys.WinSys hoặc lớp giả của bộ thử).
# =====================================================================================================
import json, re

from cbsys import (BUS_EXTERNAL, BUS_NOT_REAL, GPT_ATTR_NO_LETTER, GPT_ATTR_REQUIRED, GPT_DATA, GPT_ESP, GPT_MSR,
                   MBR_HIDDEN_NTFS)

CORE_VER = "21.11a"
PE_GUID = "{cb1e0001-b10e-4c0d-9a11-c10d0b10e001}"        # mục khởi động "CloudBlue cài lại Windows" (nạp boot.wim vào RAM)
RD_GUID = "{cb1e0002-b10e-4c0d-9a11-c10d0b10e002}"        # tuỳ chọn ramdisk của mục đó (boot.sdi)
REC_LABEL = "CBRECOVERY"
MB = 1024 * 1024
GB = 1024 * MB

# Khoá cài đặt CHUNG do Microsoft công bố (chỉ để bộ cài không hỏi khoá — KHÔNG kích hoạt Windows).
GENERIC_KEYS = {
    "professional": "VK7JG-NPHTM-C97JM-9MPGT-3V66T", "core": "YTMG3-N6DKC-DKB77-7M9GH-8HVX7",
    "coresinglelanguage": "BT79Q-G7N6G-PGBYW-4YWX6-6F4BT", "education": "YNMGQ-8RYV3-4PGQ3-C8XTP-7CFBY",
    "enterprise": "XGVPP-NMH47-7TTHJ-W3FW7-8HV2C", "professionalworkstation": "DXG7C-N36C4-C4HTG-X4T3X-2YV77",
    "professionaleducation": "8PTT6-RNW4C-6V7J2-C2D3X-MHBPB",
}
BUILD_IDS = {10240: "1507", 10586: "1511", 14393: "1607", 15063: "1703", 16299: "1709", 17134: "1803", 17763: "1809", 18362: "1903",
             18363: "1909", 19041: "2004", 19042: "20h2", 19043: "21h1", 19044: "21h2", 19045: "22h2", 22000: "w11-21h2",
             22621: "w11-22h2", 22631: "w11-23h2", 26100: "w11-24h2", 26200: "w11-25h2"}


class Stop(Exception):
    """Dừng có chủ ý, kèm lời nhắn cho người đứng trước máy."""


def os_id(version):
    """'10.0.19045.3803' → '22h2' · bản lạ → 'b<số build>'."""
    m = re.match(r"^\d+\.\d+\.(\d+)", str(version or ""))
    if not m: return "win"
    b = int(m.group(1))
    return BUILD_IDS.get(b, "b%d" % b)


def find_image(cfg, want=None):
    """Bản Windows cần cài trong cấu hình. want = '1511' / '22h2'… (None = mặc định)."""
    imgs = cfg.get("images") or []
    if not imgs: raise Stop("Bo cai khong co ban Windows nao (cb.json thieu images).")
    want = want or cfg.get("default") or imgs[0]["id"]
    for im in imgs:
        if im["id"] == want: return im
    raise Stop("Khong co ban Windows '%s' trong bo cai (dang co: %s)." % (want, ", ".join(i["id"] for i in imgs)))


# ====================================================================================== chọn ổ
def is_internal(d):
    return not d.removable and d.bus not in BUS_EXTERNAL and d.bus not in BUS_NOT_REAL


def candidates(disks, exclude=(), min_bytes=30 * GB):
    """Ổ có thể cài Windows: ổ gắn trong, không phải USB / thẻ nhớ / ổ ảo, không phải ổ chứa bộ cài, đủ lớn."""
    return [d for d in disks if is_internal(d) and d.index not in exclude and d.size >= min_bytes]


def pick_target(disks, exclude=(), cfg=None, old_system=()):
    """Chọn ổ đích. old_system = số các ổ đang có Windows cũ / phân vùng cứu hộ CloudBlue.
       Trả (ổ | None, lý do, danh sách ứng viên)."""
    cfg = cfg or {}
    cands = candidates(disks, exclude, int(float(cfg.get("min_disk_gb") or 30) * GB))
    if not cands: return None, "khong thay o cung gan trong nao du lon", cands
    rule = cfg.get("disk") or {}
    if rule:                                               # chủ shop ghim ổ trong cấu hình (theo tên / số serial)
        hit = [d for d in cands if (not rule.get("model") or rule["model"].lower() in (d.model or "").lower())
               and (not rule.get("serial") or rule["serial"].lower() == (d.serial or "").lower())]
        if len(hit) == 1: return hit[0], "theo cau hinh (disk)", cands
        return None, "cau hinh 'disk' khop %d o" % len(hit), cands
    if len(cands) == 1: return cands[0], "o gan trong duy nhat", cands
    olds = [d for d in cands if d.index in set(old_system)]
    if len(olds) == 1: return olds[0], "o dang chua Windows cu", cands
    pool = olds or cands
    ssds = [d for d in pool if d.ssd]
    if ssds: return min(ssds, key=lambda d: (d.size, d.index)), "o SSD nho nhat", cands
    return min(pool, key=lambda d: (d.size, d.index)), "o nho nhat", cands


def pick_letters(used, want=("W", "S", "R")):
    """3 chữ ổ còn trống cho Windows / khởi động / cứu hộ (ưu tiên W, S, R)."""
    used = {u.upper() for u in used} | {"X", "A", "B"}
    out, pool = [], [c for c in "VUTQPONMLKJIHGFEDZY" if c not in used and c not in want]
    for w in want:
        c = w if (w not in used and w not in out) else next((p for p in pool if p not in out), None)
        if c is None: raise Stop("Het chu o trong de gan tam.")
        out.append(c)
    return out


def recovery_bytes(cfg, boot_wim_bytes=600 * MB, extra_bytes=0):
    """Cỡ phân vùng cứu hộ: tổng các bản Windows + boot.wim + phần mềm (+ driver kèm theo), dư 15 % + 1GB, làm tròn lên GB, tối thiểu 6GB."""
    total = sum(int(im.get("bytes") or 0) for im in cfg.get("images") or []) + boot_wim_bytes + 400 * MB + max(0, int(extra_bytes or 0))
    need = int(total * 1.15) + GB
    return max(6 * GB, -(-need // GB) * GB)


# ====================================================================================== chia ổ: CÀI MỚI (xoá cả ổ)
def plan_fresh(disk, fw, rec_bytes, letters):
    """Kịch bản diskpart xoá sạch `disk` và chia lại. letters = (W, S, R).
       UEFI → GPT: 1 EFI 260MB · 2 MSR 16MB · 3 CBRECOVERY · 4 Windows (phần còn lại)
       BIOS → MBR: 1 System 500MB (khởi động) · 2 CBRECOVERY · 3 Windows (phần còn lại)
       Trả {"lines", "rec_part", "win_part", "sys_part"}; rec_bytes = 0 → không tạo phân vùng cứu hộ."""
    W, S, R = letters
    need = (rec_bytes or 0) + 25 * GB
    if disk.size < need: raise Stop("O %d qua nho (%.0f GB) - can it nhat %.0f GB." % (disk.index, disk.size / 1e9, need / 1e9))
    L = ["select disk %d" % disk.index, "online disk noerr", "attributes disk clear readonly noerr", "clean"]
    n = 0
    if fw == "uefi":
        L += ["convert gpt", "create partition efi size=260", 'format quick fs=fat32 label="System"', "assign letter=%s" % S,
              "create partition msr size=16"]
        sys_part, n = 1, 2
    else:
        L += ["convert mbr", "create partition primary size=500", 'format quick fs=ntfs label="System"', "assign letter=%s" % S, "active"]
        sys_part, n = 1, 1
    rec_part = None
    if rec_bytes:
        n += 1; rec_part = n
        L += ["create partition primary size=%d" % (rec_bytes // MB), 'format quick fs=ntfs label="%s"' % REC_LABEL, "assign letter=%s" % R]
    n += 1
    L += ["create partition primary", 'format quick fs=ntfs label="Windows"', "assign letter=%s" % W]
    return {"lines": L, "rec_part": rec_part, "win_part": n, "sys_part": sys_part}


def plan_hide_recovery(disk_index, rec_part, fw, letter):
    """Sau khi chép xong: bỏ chữ ổ + ẩn phân vùng cứu hộ (Windows không tự gán chữ ổ, không xoá nhầm trong Disk Management)."""
    L = ["select disk %d" % disk_index, "select partition %d" % rec_part, "remove letter=%s noerr" % letter]
    if fw == "uefi": L.append("gpt attributes=0x%016x" % (GPT_ATTR_REQUIRED | GPT_ATTR_NO_LETTER))
    else: L.append("set id=%02x override" % MBR_HIDDEN_NTFS)
    return L


def plan_data_disk(disk, fw):
    """Xoá sạch 1 ổ phụ và tạo 1 phân vùng NTFS trống (Windows mới sẽ tự gán chữ ổ D, E…)."""
    return ["select disk %d" % disk.index, "online disk noerr", "attributes disk clear readonly noerr", "clean",
            "convert gpt" if (fw == "uefi" or disk.size > 2000 * GB) else "convert mbr",
            "create partition primary", 'format quick fs=ntfs label="DATA"']


# ====================================================================================== chia ổ: CÀI LẠI (giữ phân vùng khởi động + cứu hộ)
def _free_gaps(disk, keep):
    """Các khoảng trống trên ổ nếu chỉ giữ lại các phân vùng `keep`. Trả [(bắt đầu, dài)…] đã căn 1MB."""
    lo = MB                                                    # 1MB đầu ổ: bảng phân vùng
    hi = disk.size - (MB if disk.style == "gpt" else 0) - MB   # GPT: bảng dự phòng cuối ổ
    if disk.style == "mbr": hi = min(hi, 2 ** 32 * 512 - MB)   # MBR chỉ địa chỉ hoá được 2TB
    gaps, cur = [], lo
    for p in sorted(keep, key=lambda p: p.offset):
        if p.offset > cur: gaps.append((cur, p.offset - cur))
        cur = max(cur, p.offset + p.size)
    if hi > cur: gaps.append((cur, hi - cur))
    out = []
    for s, n in gaps:
        s2 = -(-s // MB) * MB
        n2 = ((s + n - s2) // MB) * MB
        if n2 >= MB: out.append((s2, n2))
    return out


def plan_job(disk, fw, rec_off, wipe, win_hint, letters):
    """Kịch bản cài lại trên ổ đang có phân vùng cứu hộ (rec_off = vị trí bắt đầu của phân vùng cứu hộ).
       wipe='all'    → xoá MỌI phân vùng trừ khởi động (EFI / phân vùng active nhỏ riêng), MSR và cứu hộ; tạo phân vùng Windows mới
                       ở khoảng trống lớn nhất.
       wipe='system' → chỉ định dạng lại ĐÚNG phân vùng Windows cũ (win_hint = {"offset","size"} do agent ghi trước khi khởi động lại),
                       các phân vùng khác của khách trên ổ này giữ nguyên.
       SỐ phân vùng đổi sau khi xoá → kịch bản xoá theo số GIẢM DẦN; các bước sau đó phải tìm lại phân vùng theo VỊ TRÍ (sys_off…).
       Trả {"lines", "sys_off", "sys_is_win", "win_new", "deleted": [số phân vùng]}"""
    W = letters[0]
    parts = list(disk.parts)
    rec = next((p for p in parts if p.offset == rec_off), None)
    if rec is None: raise Stop("Khong thay phan vung cuu ho tren o %d." % disk.index)
    if fw == "uefi":
        if disk.style != "gpt": raise Stop("May khoi dong kieu UEFI nhung o %d khong phai GPT - can cai moi tu USB." % disk.index)
        sysp = next((p for p in parts if p.type == GPT_ESP), None)
        if sysp is None: raise Stop("O %d khong co phan vung EFI - can cai moi tu USB." % disk.index)
    else:
        if disk.style != "mbr": raise Stop("May khoi dong kieu BIOS nhung o %d khong phai MBR - can cai moi tu USB." % disk.index)
        sysp = next((p for p in parts if p.active), None)
        if sysp is None: raise Stop("O %d khong co phan vung khoi dong (active) - can cai moi tu USB." % disk.index)
    if sysp.number == rec.number: raise Stop("Phan vung cuu ho dang bi danh dau khoi dong - can cai moi tu USB.")
    L = ["select disk %d" % disk.index]
    deleted, sys_is_win = [], False
    if wipe == "system":
        if not win_hint: raise Stop("Lenh cai lai kieu 'system' thieu vi tri phan vung Windows cu.")
        try: woff = int(win_hint.get("offset", -1))
        except (TypeError, ValueError, AttributeError): woff = -1
        win = next((p for p in parts if p.offset == woff), None)
        if win is None or win.number == rec.number or (fw == "uefi" and win.type in (GPT_ESP, GPT_MSR)):
            raise Stop("Khong tim thay dung phan vung Windows cu (vi tri da doi) - dung lai de khong xoa nham.")
        if win.size < 25 * GB: raise Stop("Phan vung Windows cu qua nho (%.0f GB)." % (win.size / 1e9))
        sys_is_win = (win.number == sysp.number)
        L += ["select partition %d" % win.number, 'format quick fs=ntfs label="Windows" override', "assign letter=%s" % W]
        if sys_is_win: L.append("active")
        win_new = False
    elif wipe == "all":
        keep = [p for p in parts if p.number == rec.number or (fw == "uefi" and p.type in (GPT_ESP, GPT_MSR))
                or (fw != "uefi" and p.number == sysp.number and p.size <= 2 * GB)]          # BIOS: giữ phân vùng khởi động NHỎ riêng
        sys_is_win = sysp not in keep                              # phân vùng active chính là phân vùng Windows cũ → tạo lại + active
        gaps = _free_gaps(disk, keep)
        if not gaps: raise Stop("O %d khong con cho trong de tao phan vung Windows." % disk.index)
        s, n = max(gaps, key=lambda g: g[1])
        if n < 25 * GB: raise Stop("Khoang trong lon nhat tren o %d chi %.0f GB - khong du cai Windows." % (disk.index, n / 1e9))
        if fw != "uefi" and len(keep) >= 4: raise Stop("O MBR da du 4 phan vung chinh.")
        for p in sorted(parts, key=lambda p: -p.number):           # số lớn trước → số của các phân vùng còn lại không đổi giữa chừng
            if p in keep: continue
            L += ["select partition %d" % p.number, "delete partition override"]
            deleted.append(p.number)
        L += ["create partition primary offset=%d size=%d" % (s // 1024, n // MB), 'format quick fs=ntfs label="Windows"',
              "assign letter=%s" % W]
        if sys_is_win: L.append("active")
        win_new = True
    else:
        raise Stop("Kieu xoa '%s' khong hop le." % wipe)
    return {"lines": L, "sys_off": sysp.offset, "sys_is_win": sys_is_win, "win_new": win_new, "deleted": deleted}


# ====================================================================================== BCD
def bcd_store(fw, sys_letter):
    return ("%s:\\EFI\\Microsoft\\Boot\\BCD" if fw == "uefi" else "%s:\\Boot\\BCD") % sys_letter


def bcd_pe_cmds(fw, rec_dev, store=None):
    """Các lệnh bcdedit tạo (lại) mục khởi động cài lại: nạp \\cb\\boot\\boot.wim trên phân vùng cứu hộ vào RAM.
       rec_dev = chữ ổ 'R' / 'R:' (trong WinPE) hoặc tên thiết bị '\\Device\\HarddiskVolumeN' (trong Windows, không cần chữ ổ).
       Trả [(argv, bỏ_qua_lỗi)…]. store=None → kho BCD của Windows đang chạy."""
    rec_dev = str(rec_dev)
    if len(rec_dev) == 1: rec_dev += ":"
    st = ["/store", store] if store else []
    winload = "\\windows\\system32\\boot\\winload.efi" if fw == "uefi" else "\\windows\\system32\\boot\\winload.exe"
    dev = "ramdisk=[%s]\\cb\\boot\\boot.wim,%s" % (rec_dev, RD_GUID)
    B = ["bcdedit"] + st
    return [
        (B + ["/delete", PE_GUID, "/f"], True),
        (B + ["/delete", RD_GUID, "/f"], True),
        (B + ["/create", RD_GUID, "/d", "CloudBlue ramdisk", "/device"], False),
        (B + ["/set", RD_GUID, "ramdisksdidevice", "partition=%s" % rec_dev], False),
        (B + ["/set", RD_GUID, "ramdisksdipath", "\\cb\\boot\\boot.sdi"], False),
        (B + ["/create", PE_GUID, "/d", "CloudBlue cai lai Windows", "/application", "osloader"], False),
        (B + ["/set", PE_GUID, "device", dev], False),
        (B + ["/set", PE_GUID, "osdevice", dev], False),
        (B + ["/set", PE_GUID, "path", winload], False),
        (B + ["/set", PE_GUID, "systemroot", "\\windows"], False),
        (B + ["/set", PE_GUID, "winpe", "yes"], False),
        (B + ["/set", PE_GUID, "detecthal", "yes"], False),
    ]


def run_cmds(sysx, cmds, what):
    for argv, soft in cmds:
        rc, out = sysx.run(argv, timeout=120)
        if rc != 0 and not soft:
            raise Stop("%s loi (ma %s): %s\n%s" % (what, rc, " ".join(argv), (out or "").strip()[-400:]))


# ====================================================================================== file trả lời cho Windows mới
_XML_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def xml_esc(s):
    return "".join(_XML_ESC.get(c, c) for c in str(s))


def clean_name(s, fallback="CB-PC"):
    """Tên máy Windows hợp lệ: chữ / số / gạch nối, tối đa 15 ký tự, không toàn số."""
    s = re.sub(r"[^A-Za-z0-9-]", "", str(s or ""))[:15].strip("-")
    if not s or s.isdigit(): return fallback
    return s


def os_tag_base(tag):
    """'22h2-2' → '22h2' (ISO có 2 bản cùng build thì bản sau mang đuôi -2, -3…)."""
    return re.sub(r"-\d+$", "", str(tag or "").lower())


def is_os_tag(name):
    """Tên thư mục là tên 1 bản Windows (1511, 22h2, w11-23h2, b19045, 22h2-2…)?"""
    n = os_tag_base(name)
    return n in set(BUILD_IDS.values()) or re.fullmatch(r"b\d{4,6}", n) is not None


def folder_applies(name, image_id):
    """Thư mục con trong cb\\drivers (hoặc os\\firstboot.d) có dùng cho bản Windows đang cài không?
       Tên là 1 bản Windows (vd '1511') → chỉ dùng cho đúng bản đó; tên khác → dùng cho mọi bản."""
    if not is_os_tag(name): return True
    n, i = str(name).lower(), str(image_id or "").lower()
    return n == i or n == os_tag_base(i)


def key_mode(cfg):
    """Mục generic_key của cb.json → 'auto' (mặc định) · 'on' · 'off'. Nhận cả true / false."""
    v = (cfg or {}).get("generic_key", "auto")
    if v is True: return "on"
    if v is False or v is None: return "off"
    v = str(v).strip().lower()
    return v if v in ("auto", "on", "off") else "auto"


def build_no(version):
    """'10.0.10586.0' → 10586 · không đọc được → 0."""
    m = re.match(r"^\s*\d+\.\d+\.(\d+)", str(version or ""))
    return int(m.group(1)) if m else 0


STOCK_WORDS = {"home", "pro", "education", "enterprise", "n", "single", "language", "for", "workstations", "s", "ltsb", "ltsc", "iot", "core", "country", "specific"}


def is_stock_name(name):
    """Tên ảnh đúng kiểu Microsoft phát hành ('Windows 10 Pro', 'Windows 10 Home Single Language'…)?
       Bản tuỳ biến (Lite, Premium, có tên người làm…) → False: không tự điền khoá cho các bản đó."""
    w = str(name or "").strip().lower().split()
    return len(w) >= 3 and w[0] == "windows" and w[1] in ("10", "11") and all(x in STOCK_WORDS for x in w[2:])


def generic_key_for(image, cfg):
    """Khoá CÀI ĐẶT CHUNG của Microsoft cho đúng phiên bản (edition) — chỉ để màn hình cài lần đầu không dừng lại hỏi key, KHÔNG kích hoạt bản quyền.
       auto: chỉ điền cho bản GỐC của Microsoft (tên ảnh chuẩn) trước 1703 (1507 / 1511 / 1607: không có key thì lần khởi động đầu đứng chờ người bấm
       'Do this later'). Bản tuỳ biến (Lite…) không tự điền — người làm bản đó thường đã lo sẵn; cần thì bật hẳn bằng mode on."""
    key = GENERIC_KEYS.get(str((image or {}).get("edition") or "").lower())
    mode = key_mode(cfg)
    if not key or mode == "off": return ""
    if mode == "on": return key
    return key if (0 < build_no((image or {}).get("version")) < 15063 and is_stock_name((image or {}).get("name"))) else ""


KEY_RE = re.compile(r"<ProductKey>\s*(?:<Key>\s*)?([A-Za-z0-9]{5}(?:-[A-Za-z0-9]{5}){4})\s*(?:</Key>)?", re.S)


def find_unattend_key(xml_text):
    """Khoá sản phẩm nằm sẵn trong 1 file trả lời (của người làm bản Windows tuỳ biến) — để giữ lại khi ghi file trả lời của CloudBlue. Không có → ''."""
    m = KEY_RE.search(str(xml_text or ""))
    return m.group(1).upper() if m else ""


def make_unattend(tpl, image, cfg, name, own_key=""):
    """Điền mẫu unattend (specialize + oobeSystem). own_key = khoá nằm sẵn trong file trả lời cũ của chính bản Windows đó (giữ lại, trừ khi tắt hẳn);
       không có thì khoá cài đặt chung chỉ điền khi biết đúng phiên bản (edition) — xem generic_key_for."""
    own_key = own_key if (key_mode(cfg) != "off" and re.fullmatch(r"[A-Z0-9]{5}(-[A-Z0-9]{5}){4}", str(own_key or ""))) else ""
    key = own_key or generic_key_for(image, cfg)
    vals = {
        "COMPUTERNAME": "*" if name == "*" else clean_name(name),           # "*" = Windows tự đặt tên ngẫu nhiên
        "PRODUCTKEY": ("<ProductKey>%s</ProductKey>" % key) if key else "",
        "TIMEZONE": cfg.get("timezone") or "SE Asia Standard Time",
        "USER": cfg.get("user") or "PC",
        "PASSWORD": cfg.get("password") or "",
        "LANG": image.get("lang") or "en-US",
        "LOCALE": cfg.get("locale") or "en-US",
    }
    out = tpl
    for k, v in vals.items():
        out = out.replace("{{%s}}" % k, v if k == "PRODUCTKEY" else xml_esc(v))
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left: raise Stop("Mau unattend con cho chua dien: %s" % ", ".join(sorted(set(left))))
    return out


# ====================================================================================== lệnh cài lại (job.json trên phân vùng cứu hộ)
def job_valid(job):
    """Lệnh đang chờ làm? (queued / running, chưa quá 3 lần thử)"""
    return (isinstance(job, dict) and job.get("state") in ("queued", "running") and int(job.get("attempts") or 0) < 3
            and re.fullmatch(r"[a-z0-9-]{2,12}", str(job.get("os") or "")) is not None and job.get("wipe") in ("all", "disk", "system"))


def load_json(sysx, path, default=None):
    try:
        if sysx.exists(path): return json.loads(sysx.read_text(path))
    except Exception:
        pass
    return default


def save_json(sysx, path, obj):
    sysx.write_text(path, json.dumps(obj, ensure_ascii=True, indent=1))


def recovery_cfg(cfg):
    """Cấu hình ghi vào phân vùng cứu hộ: mọi bản Windows nằm ở cb\\images\\<id>.<đuôi>; không mang theo bí mật nào."""
    out = {k: v for k, v in cfg.items() if k not in ("enroll_key",)}
    imgs = []
    for im in cfg.get("images") or []:
        ext = "." + str(im["file"]).rsplit(".", 1)[-1].lower()
        j = dict(im); j["file"] = "cb\\images\\%s%s" % (im["id"], ext)
        imgs.append(j)
    out["images"] = imgs
    return out


# ====================================================================================== khoá quyền thư mục / phân vùng (icacls)
SID_SYSTEM, SID_ADMINS, SID_USERS, SID_AUTH, SID_EVERYONE, SID_CREATOR = "*S-1-5-18", "*S-1-5-32-544", "*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0", "*S-1-3-0"
ACL_FULL = [SID_SYSTEM + ":(OI)(CI)F", SID_ADMINS + ":(OI)(CI)F"]
ACL_WEAK = [SID_USERS, SID_AUTH, SID_EVERYONE, SID_CREATOR]    # các dòng quyền phải gỡ khỏi gốc; CREATOR OWNER: để lại thì file do tài khoản thường tạo từ trước vẫn thuộc quyền họ


BOOT_SVC = "CloudBluePCBoot"


def boot_service_cmds(root, cs=1, base="C:\\CloudBluePC"):
    """Các lệnh `reg add` ghi 1 DỊCH VỤ TỰ CHẠY lúc khởi động vào kho registry SYSTEM của Windows vừa bung (kho đã được nạp tại `root`, vd HKLM\\CB_OFFSYS;
       cs = số ControlSet đang dùng). Mỗi lần máy bật, Windows chạy bằng SYSTEM:  cb_provision.py boot  → nếu chưa có tác vụ agent thì tự dựng + bật agent,
       xong thì tự gỡ dịch vụ. Đây là lưới an toàn thứ 3 (sau file trả lời + SetupComplete.cmd): bản Windows tuỳ biến không chạy 2 thứ kia thì agent vẫn lên.
       Lệnh không phải dịch vụ thật nên Windows ghi 1 dòng lỗi "dịch vụ không trả lời" — vô hại (ErrorControl = 0), tiến trình con vẫn chạy tiếp."""
    k = "%s\\ControlSet%03d\\Services\\%s" % (root, int(cs), BOOT_SVC)
    img = '%%SystemRoot%%\\System32\\cmd.exe /c start "" /b "%s\\py\\pythonw.exe" -I -B "%s\\os\\cb_provision.py" boot' % (base, base)
    add = lambda name, typ, val: ["reg", "add", k, "/v", name, "/t", typ, "/d", str(val), "/f"]
    return [add("Type", "REG_DWORD", 16), add("Start", "REG_DWORD", 2), add("ErrorControl", "REG_DWORD", 0), add("ImagePath", "REG_EXPAND_SZ", img),
            add("ObjectName", "REG_SZ", "LocalSystem"), add("DisplayName", "REG_SZ", "CloudBlue PC boot")]


def setup_state(reg_text):
    """Chữ in ra của `reg query <kho SYSTEM>\\Setup` → Windows đó có đang ở trạng thái "cài đặt lần đầu" không:
       True = sẽ chạy bước cài lần đầu (dùng file trả lời) · False = bản đã cài xong / kiểu ghost (khởi động thẳng vào Windows có sẵn) · None = không đọc được."""
    v = dict((k.lower(), val.strip().lower()) for k, val in re.findall(r"^\s+(\w+)\s+REG_\w+\s*(.*?)\s*$", reg_text or "", re.M))
    if "systemsetupinprogress" not in v and "setuptype" not in v: return None
    num = lambda s: int(s, 16) if re.fullmatch(r"0x[0-9a-f]+", s or "") else 0
    return num(v.get("systemsetupinprogress")) == 1 or num(v.get("setuptype")) in (1, 2) or "windeploy" in v.get("cmdline", "")


def acl_lock_cmds(base):
    """Các lệnh icacls khoá thư mục phần mềm CloudBlue trên máy cho thuê (base = C:\\CloudBluePC):
       - gốc + mọi thứ bên trong: CHỈ SYSTEM và Administrators (identity.json = mã máy, seed.json = mã đăng ký / vé, logs, agent, lib…)
       - riêng py\\ và os\\: tài khoản thường được ĐỌC + CHẠY (phần chạy lúc đăng nhập để đặt ảnh nền) — không được ghi
       - os\\firstboot.d (script riêng của chủ shop, có thể chứa khoá bản quyền…): lại chỉ SYSTEM + Administrators
       Không khoá thì thư mục thừa hưởng quyền của C:\\ (Authenticated Users sửa được) → tài khoản thường sửa được file agent chạy quyền SYSTEM."""
    b = base.rstrip("\\")
    return [["icacls", b, "/inheritance:r", "/grant:r"] + ACL_FULL,
            ["icacls", b, "/remove:g"] + ACL_WEAK,
            ["icacls", b, "/setowner", SID_ADMINS, "/T", "/C", "/Q"],      # file nào do tài khoản khác tạo từ trước cũng về tay Administrators
            ["icacls", b + "\\*", "/reset", "/T", "/C", "/Q"],
            ["icacls", b + "\\py", "/grant:r", SID_USERS + ":(OI)(CI)RX"],
            ["icacls", b + "\\os", "/grant:r", SID_USERS + ":(OI)(CI)RX"],
            ["icacls", b + "\\os\\firstboot.d", "/inheritance:r", "/grant:r"] + ACL_FULL]


def acl_vol_cmds(root):
    """Các lệnh icacls khoá GỐC phân vùng cứu hộ (root = 'R:\\' hoặc '\\\\?\\Volume{…}\\'): chỉ SYSTEM + Administrators.
       Phân vùng NTFS mới định dạng cho Authenticated Users quyền sửa, và phân vùng không có chữ ổ vẫn mở được qua đường \\\\?\\Volume{…}\\
       → không khoá thì tài khoản thường sửa được bộ cài (thứ sẽ chạy quyền SYSTEM ở lần cài lại sau)."""
    r = root if root.endswith("\\") else root + "\\"
    return [["icacls", r, "/inheritance:r", "/grant:r"] + ACL_FULL,
            ["icacls", r, "/remove:g"] + ACL_WEAK,
            ["icacls", r + "*", "/setowner", SID_ADMINS, "/T", "/C", "/Q"],
            ["icacls", r + "*", "/reset", "/T", "/C", "/Q"]]
