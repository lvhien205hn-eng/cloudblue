#!/usr/bin/env python3
"""CloudBlue — ghép ISO PROXMOX TỰ CÀI (máy chủ VPS ảo hoá). Gọi từ proxmox/tao-iso-proxmox.ps1 (Windows) hoặc chạy thẳng (Linux / CI).

   ISO Proxmox VE gốc (bản chính thức) + trả lời tự cài (answer.toml) + script lần bật đầu (tự cài cbhost) + kho ISO máy mẫu Windows
   → 1 file ISO. Khởi động máy chủ từ ISO này: Proxmox tự cài → tự lên web → tự dựng máy mẫu.

   Không cần xorriso: 3 file nhỏ được thêm thẳng vào chỗ trống sẵn có của thư mục gốc ISO 9660, dữ liệu nối vào cuối file; bản ghi khởi động
   (El Torito / MBR / GPT) giữ nguyên từng byte — như công cụ chính thức của Proxmox làm (xorriso -boot_image any keep). Kho ISO máy mẫu nối thô
   sau cùng (ngoài hệ tệp ISO), có đầu mục + mã kiểm SHA-256; trên máy chủ, cb_nap.py đọc thẳng từ USB.
   Chữ in ra màn hình không dấu (cửa sổ PowerShell 5 của Windows không hiện được dấu)."""
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import sys
import time

VER = "26.11a"
SECT = 2048
MAGIC = b"CBKHO1\n"
HDR_LEN = 16384                       # đầu mục kho (JSON) — 8 sector
FB_MAX = 1024 * 1024                  # Proxmox: script lần bật đầu tối đa 1 MiB
MIN_ISO = 500 * 1024 * 1024           # file nhỏ hơn thế này không phải ISO Proxmox / ISO máy mẫu thật (bỏ qua khi tự tìm)
PVE_URL = "https://enterprise.proxmox.com/iso/proxmox-ve_%s.iso"
PVE_DEFAULT = "9.3-1"
# Bản ISO Proxmox VE đã thử cài thật (CI): mã SHA-256 của file chính thức. Bản khác: vẫn ghép (kiểm cấu trúc), có ghi chú "chưa thử".
KNOWN = {"9.3-1": "cc4fc97b9ac3a5712ad5b665195753571923a18e11f5c2ebb113fdc29a50bd36"}
RX_MAU = re.compile(r"^CloudBlue-MayMau-([a-z0-9]{3,24})\.iso$")
RX_PVE = re.compile(r"^proxmox-ve_(\d+)\.(\d+)-(\d+)\.iso$", re.I)
RX_HOST = re.compile(r"^[a-z][a-z0-9-]{0,30}[a-z0-9]$|^[a-z]$")
RX_DISK = re.compile(r"^[a-z][a-z0-9]{1,15}$")
RX_CIDR = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,2})$")
RX_IP = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
NEW_FILES = ("auto-installer-mode.toml", "answer.toml", "proxmox-first-boot")
GUARD_MARK = "# ---- CloudBlue: khong tu cai de len may da co Proxmox / Windows ----"
GUARD_END = "# ---- het doan CloudBlue ----\n\n"
GUARD_TMO = '    # CloudBlue: may dang co Windows -> khong dem nguoc, cho nguoi chon\n    if [ "$cb_co" = "win" ]; then\n        set timeout=-1\n    fi\n'


class Loi(Exception):
    pass


def say(*a):
    s = " ".join(str(x) for x in a)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:                 # đường dẫn có dấu trên cửa sổ PowerShell 5 (cp1252 / cp437)
        print(s.encode("ascii", "replace").decode("ascii"), flush=True)


def b32(n):
    return struct.pack("<I", n) + struct.pack(">I", n)


def le32(b):
    return struct.unpack("<I", b[:4])[0]


# ---------------------------------------------------------------- mật khẩu root: băm SHA-512 crypt ($6$) — đúng thuật toán của glibc
def sha512_crypt(password, salt=None, rounds=5000):
    pw = password.encode("utf-8")
    b64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    if salt is None:
        salt = "".join(b64[secrets.randbelow(64)] for _ in range(16))
    if not re.match(r"^[./0-9A-Za-z]{1,16}$", salt):
        raise Loi("salt khong hop le")
    sl = salt.encode()
    n = len(pw)
    B = hashlib.sha512(pw + sl + pw).digest()
    ctx = hashlib.sha512(pw + sl)
    ctx.update((B * (n // 64 + 1))[:n])
    i = n
    while i > 0:
        ctx.update(B if i & 1 else pw)
        i >>= 1
    A = ctx.digest()
    P = (hashlib.sha512(pw * n).digest() * (n // 64 + 1))[:n]
    S = (hashlib.sha512(sl * (16 + A[0])).digest() * (len(sl) // 64 + 1))[:len(sl)]
    C = A
    for r in range(rounds):
        c = hashlib.sha512(P if r & 1 else C)
        if r % 3:
            c.update(S)
        if r % 7:
            c.update(P)
        c.update(C if r & 1 else P)
        C = c.digest()
    out = []
    for a, b, c in ((0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26), (6, 27, 48), (28, 49, 7), (50, 8, 29), (9, 30, 51),
                    (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57), (37, 58, 16), (59, 17, 38), (18, 39, 60),
                    (40, 61, 19), (62, 20, 41)):
        v = (C[a] << 16) | (C[b] << 8) | C[c]
        for _ in range(4):
            out.append(b64[v & 63])
            v >>= 6
    v = C[63]
    for _ in range(2):
        out.append(b64[v & 63])
        v >>= 6
    return "$6$%s$%s" % (salt, "".join(out))


# ---------------------------------------------------------------- ISO 9660 (đọc + vá tại chỗ)
def susp(su):
    """Các mục SUSP / Rock Ridge trong phần System Use của 1 bản ghi → [(ký hiệu, nguyên mục)]"""
    res = []
    k = 0
    while k + 4 <= len(su):
        ln = su[k + 2]
        if su[k] == 0 or ln < 4 or k + ln > len(su):
            break
        res.append((bytes(su[k:k + 2]), bytes(su[k:k + ln])))
        k += ln
    return res


def rr_name(su, iso):
    nm = b""
    for sig, e in susp(su):
        if sig == b"NM":
            if e[4] & 2:
                return "."
            if e[4] & 4:
                return ".."
            nm += e[5:]
    if nm:
        return nm.decode("utf-8", "replace")
    if iso == b"\0":
        return "."
    if iso == b"\1":
        return ".."
    return iso.split(b";")[0].decode("latin-1").lower().rstrip(".")


def parse_dir(buf):
    """Các bản ghi của 1 thư mục → [{off, len, ext, size, flags, iso, name, su, raw}]"""
    res = []
    o = 0
    while o < len(buf):
        ln = buf[o]
        if ln == 0:
            o = (o // SECT + 1) * SECT
            continue
        r = bytes(buf[o:o + ln])
        if ln < 34 or len(r) < ln or o // SECT != (o + ln - 1) // SECT:
            raise Loi("thu muc trong ISO hong (ban ghi lech o vi tri %d)" % o)
        nl = r[32]
        iso = r[33:33 + nl]
        su = r[33 + nl + (1 - nl % 2):]
        res.append({"off": o, "len": ln, "ext": le32(r[2:6]), "size": le32(r[10:14]), "flags": r[25], "iso": iso, "name": rr_name(su, iso), "su": su, "raw": r})
        o += ln
    return res


class Iso:
    def __init__(self, f):
        self.f = f
        self.pvd = self.read(16 * SECT, SECT)
        if self.pvd[:7] != b"\x01CD001\x01":
            raise Loi("day khong phai file ISO 9660")
        if struct.unpack("<H", self.pvd[128:130])[0] != SECT:
            raise Loi("ISO co co khoi khac 2048 - khong ho tro")
        i = 17
        while True:
            d = self.read(i * SECT, SECT)
            if d[1:6] != b"CD001" or i > 64:
                raise Loi("ISO hong (thieu dau ket thuc danh sach volume descriptor)")
            if d[0] == 255:
                break
            if d[0] == 2:
                raise Loi("ISO nay co cay ten Joliet / ISO 9660:1999 - khac cau truc ISO Proxmox VE da biet, chua ho tro")
            i += 1
        self.root_lba, self.root_size = le32(self.pvd[158:162]), le32(self.pvd[166:170])
        self.vol_sectors = le32(self.pvd[80:84])
        if self.root_size % SECT or not 0 < self.root_size <= 64 * SECT:
            raise Loi("thu muc goc cua ISO co co la (%d)" % self.root_size)

    def read(self, off, n):
        self.f.seek(off)
        d = self.f.read(n)
        if len(d) != n:
            raise Loi("doc ISO thieu du lieu (vi tri %d)" % off)
        return d

    def dir(self, lba, size):
        return parse_dir(self.read(lba * SECT, size))

    def root(self):
        return self.dir(self.root_lba, self.root_size)

    def find(self, path):
        """→ (LBA thư mục chứa, cỡ thư mục chứa, bản ghi) của 1 đường dẫn (tên Rock Ridge, phân biệt hoa thường); không có → None"""
        lba, size = self.root_lba, self.root_size
        parts = [x for x in path.split("/") if x]
        for n, part in enumerate(parts):
            r = next((x for x in self.dir(lba, size) if x["name"] == part), None)
            if r is None:
                return None
            if n == len(parts) - 1:
                return lba, size, r
            if not r["flags"] & 2:
                return None
            lba, size = r["ext"], r["size"]
        return None

    def read_file(self, path):
        hit = self.find(path)
        if hit is None or hit[2]["flags"] & 0x82:
            return None
        return self.read(hit[2]["ext"] * SECT, hit[2]["size"]) if hit[2]["size"] else b""


def iso_name(rr, taken):
    """Tên ISO 9660 kiểu 8.3 (như các file sẵn có trong ISO Proxmox) cho 1 file mới — không trùng tên đã có."""
    base, _, ext = rr.rpartition(".") if "." in rr.strip(".") else (rr, "", "")
    clean = lambda t: re.sub(r"[^A-Z0-9_]", "_", t.upper())
    b, e = clean(base)[:8] or "_", clean(ext)[:3]
    n = 0
    while True:
        cand = ("%s.%s;1" % (b, e)).encode()
        if cand not in taken:
            return cand
        n += 1
        tail = "%d" % n
        b = b[:8 - len(tail)] + tail
        if n > 999:
            raise Loi("khong dat duoc ten ISO cho " + rr)


def new_record(tmpl, name_iso, rr, ext, size, mode):
    """Bản ghi thư mục cho 1 file mới: lấy khuôn từ bản ghi 1 file thường sẵn có (ngày giờ, PX, TF) — đổi tên, vị trí, cỡ, quyền."""
    head = bytearray(tmpl["raw"][:33])
    head[1] = 0
    head[2:10] = b32(ext)
    head[10:18] = b32(size)
    head[25] = 0
    head[32] = len(name_iso)
    su = b""
    for sig, e in susp(tmpl["su"]):
        if sig == b"PX":
            e = bytearray(e)
            e[4:12] = b32(mode)
            su += bytes(e)
        elif sig == b"TF":
            su += e
    nm = rr.encode("ascii")
    su += b"NM" + bytes([5 + len(nm), 1, 0]) + nm
    rec = bytes(head) + name_iso + (b"" if len(name_iso) % 2 else b"\0") + su
    if len(rec) % 2:
        rec += b"\0"
    if len(rec) > 254:
        raise Loi("ten file qua dai: " + rr)
    return bytes([len(rec)]) + rec[1:]


def grub_guard(cfg):
    """grub.cfg của ISO Proxmox + đoạn BẢO VỆ: máy đã có Proxmox (LVM pve) → mặc định khởi động từ ổ cứng (không cài lại, không lặp cài khi USB còn cắm);
    máy đang có Windows → không tự cài (phải tự chọn dòng 'Install Proxmox VE (Automated)'). Không khớp cấu trúc đã biết → None (giữ nguyên grub.cfg)."""
    key = "if [ -f auto-installer-mode.toml ]; then"
    if cfg.count("\n" + key) != 1 or "(lvm/pve-root)/boot/pve/vmlinuz" not in cfg or "'Install Proxmox VE (Automated)'" not in cfg or GUARD_MARK in cfg:
        return None
    blk = GUARD_MARK + """
insmod part_gpt
insmod part_msdos
insmod lvm
insmod ext2
set cb_co=
if test -e (lvm/pve-root)/boot/pve/vmlinuz; then
    set cb_co=pve
fi
if [ -z "$cb_co" ]; then
    insmod ntfs
    search --no-floppy --file /Windows/System32/ntoskrnl.exe --set cb_win
    if [ -n "$cb_win" ]; then
        set cb_co=win
    fi
fi
if [ "$cb_co" = "pve" ]; then
    menuentry 'CloudBlue: may nay DA CO Proxmox - khoi dong tu o cung' --class debian --class gnu-linux --class gnu --class os {
        insmod lvm
        insmod ext2
        echo 'CloudBlue: khoi dong Proxmox da cai tren o cung ...'
        linux (lvm/pve-root)/boot/pve/vmlinuz ro ramdisk_size=16777216 root=/dev/mapper/pve-root quiet
        initrd (lvm/pve-root)/boot/pve/initrd.img
    }
fi
if [ "$cb_co" = "win" ]; then
    menuentry 'CloudBlue: may dang co WINDOWS - KHONG tu cai (Enter: xem)' {
        echo ''
        echo 'May nay dang co Windows. De tranh xoa nham, ISO KHONG tu cai len may nay.'
        echo 'Muon cai Proxmox len may nay (XOA SACH o dia): quay lai menu, chon dong'
        echo '    Install Proxmox VE (Automated)'
        echo 'roi bam Enter.'
        echo ''
        echo 'Tu quay lai menu sau 30 giay (bam Esc de quay lai ngay) ...'
        sleep --interruptible 30
    }
fi
"""
    blk += GUARD_END
    i = cfg.index("\n" + key) + 1
    rest = cfg[i:]
    tmo = "\n    set timeout=10\n"
    if cfg.count(tmo) == 1 and tmo in rest[:200]:                       # ngay trong khối tự cài: máy có Windows thì không đếm ngược
        j = rest.index(tmo) + len(tmo)
        rest = rest[:j] + GUARD_TMO + rest[j:]
    return cfg[:i] + blk + rest


def answer_toml(pw_hash, host="cbvps", disk="", cidr="", gw="", dns="", ssh_keys=(), reboot="reboot"):
    if not re.match(r"^\$[0-9a-z]{1,2}\$[./0-9A-Za-z$=,]{20,200}$", pw_hash):
        raise Loi("ma bam mat khau root khong hop le")
    if not RX_HOST.match(host):
        raise Loi("ten may chu chi gom chu thuong, so, dau - (bat dau bang chu): " + host)
    if disk and not RX_DISK.match(disk):
        raise Loi("ten o dia khong hop le (vi du: sda, nvme0n1): " + disk)
    L = ["# CloudBlue - tra loi tu cai Proxmox VE (do pve_iso.py %s tao)" % VER, "[global]", 'keyboard = "en-us"', 'country = "vn"',
         'fqdn = "%s.lan"' % host, 'mailto = "root@%s.lan"' % host, 'timezone = "Asia/Ho_Chi_Minh"', 'root-password-hashed = "%s"' % pw_hash]
    if ssh_keys:
        for k in ssh_keys:
            if not re.match(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256) [A-Za-z0-9+/=]{40,1200}( [A-Za-z0-9@._-]{1,60})?$", k):
                raise Loi("khoa SSH khong hop le")
        L.append("root-ssh-keys = [%s]" % ", ".join('"%s"' % k for k in ssh_keys))
    L += ["reboot-on-error = false", 'reboot-mode = "%s"' % ("power-off" if reboot == "power-off" else "reboot"), "", "[network]"]
    if cidr or gw or dns:
        mc, mg, md = RX_CIDR.match(cidr or ""), RX_IP.match(gw or ""), RX_IP.match(dns or "")
        nums = (mc.groups()[:4] + mg.groups() + md.groups()) if (mc and mg and md) else ("999",)
        if any(int(x) > 255 for x in nums) or not 8 <= int(mc.group(5)) <= 30:
            raise Loi("IP tinh can du 3 muc dung dang: -Ip 192.168.1.50/24 -Gateway 192.168.1.1 -Dns 8.8.8.8")
        L += ['source = "from-answer"', 'cidr = "%s"' % cidr, 'dns = "%s"' % dns, 'gateway = "%s"' % gw]
    else:
        L.append('source = "from-dhcp"')
    L += ["", "[disk-setup]", 'filesystem = "ext4"']
    L.append('disk-list = ["%s"]' % disk if disk else 'filter.DEVTYPE = "disk"')
    L += ["", "[first-boot]", 'source = "from-iso"', 'ordering = "fully-up"', ""]
    return "\n".join(L)


def b64wrap(data):
    t = base64.b64encode(data).decode()
    return "\n".join(t[i:i + 76] for i in range(0, len(t), 76))


def first_boot(tmpl, cbhost, nap, conf, nap_conf):
    """Script lần bật đầu: khuôn pve_firstboot.sh + cbhost.py + cb_nap.py + cấu hình (đều nhúng base64)."""
    out = tmpl
    for k, v in (("@@VER@@", VER.encode()), ("@@CBHOST_B64@@", cbhost), ("@@NAP_B64@@", nap), ("@@CONF_B64@@", json.dumps(conf, sort_keys=True).encode()),
                 ("@@NAPCONF_B64@@", json.dumps(nap_conf, sort_keys=True).encode())):
        if out.count(k) < 1 or (k != "@@VER@@" and out.count(k) != 1):
            raise Loi("khuon pve_firstboot.sh thieu / thua cho %s" % k)
        out = out.replace(k, v.decode() if k == "@@VER@@" else b64wrap(v))
    data = out.replace("\r\n", "\n").encode("utf-8")
    if len(data) > FB_MAX:
        raise Loi("script lan bat dau qua 1 MiB")
    return data


def sectors(n):
    return (n + SECT - 1) // SECT


def copy_stream(src, dst, total, label, sha=None, chunk=4 * 1024 * 1024):
    done = 0
    t0 = time.time()
    nxt = 10
    while done < total:
        b = src.read(min(chunk, total - done))
        if not b:
            raise Loi("doc thieu du lieu: " + label)
        dst.write(b)
        if sha is not None:
            sha.update(b)
        done += len(b)
        if total > 200 * 1024 * 1024 and done * 100 // total >= nxt:
            say("      %s: %d%% (%d MB / %d MB, %d giay)" % (label, done * 100 // total, done >> 20, total >> 20, time.time() - t0))
            nxt = (done * 100 // total // 10 + 1) * 10


def pad(f):
    pos = f.tell()
    if pos % SECT:
        f.write(b"\0" * (SECT - pos % SECT))
    return f.tell()


def build(iso_path, out_path, answer, fb_make, payload=(), guard=True, known=None, note=None):
    """Ghép. fb_make(nap_conf) → nội dung script lần bật đầu (biết vị trí kho rồi mới tạo). payload: [(tên trong kho, đường dẫn file)].
    → {size, off, id, files, guard, release}"""
    note = note or (lambda m: say("   (!) " + m))
    src_size = os.path.getsize(iso_path)
    if src_size % SECT or src_size < 20 * SECT:
        raise Loi("file ISO Proxmox co co la (%d byte) - tai lai" % src_size)
    with open(iso_path, "rb") as f:
        iso = Iso(f)
        root = iso.root()
        names = {r["name"] for r in root}
        if any(n in names for n in NEW_FILES):
            raise Loi("ISO nay da duoc ghep tu cai roi - hay dung file ISO Proxmox VE GOC (proxmox-ve_x.y-z.iso tai tu proxmox.com)")
        info = (iso.read_file(".cd-info") or b"").decode("latin-1")
        rel = re.search(r"^RELEASE='(\d+)\.(\d+)'", info, re.M)
        isorel = re.search(r"^ISORELEASE='(\d+)'", info, re.M)
        if "PRODUCT='pve'" not in info or not rel or "auto-installer-capable" not in names or ".pve-cd-id.txt" not in names:
            raise Loi("day khong phai ISO cai dat Proxmox VE (ban 9 tro len) - tai file proxmox-ve_x.y-z.iso tu proxmox.com")
        if int(rel.group(1)) < 9:
            raise Loi("ISO Proxmox VE %s.%s qua cu - can ban 9.0 tro len" % rel.groups())
        release = "%s.%s-%s" % (rel.group(1), rel.group(2), isorel.group(1) if isorel else "?")
        known_sha = (KNOWN if known is None else known).get(release)
        if not any(sig == b"SP" for sig, _ in susp(root[0]["su"])):
            raise Loi("ISO khong co Rock Ridge - khac cau truc ISO Proxmox VE da biet")
        tmpl = next((r for r in root if not r["flags"] and r["size"] > 0 and any(s == b"PX" and le32(e[4:8]) & 0o170000 == 0o100000 for s, e in susp(r["su"]))
                     and any(s == b"TF" for s, _ in susp(r["su"]))), None)
        if tmpl is None:
            raise Loi("khong tim thay ban ghi mau trong thu muc goc cua ISO")
        end = root[-1]["off"] + root[-1]["len"]
        grub_old = iso.read_file("boot/grub/grub.cfg")
        grub_hit = iso.find("boot/grub/grub.cfg")
    grub_new = None
    if guard and grub_old is not None:
        g = grub_guard(grub_old.decode("utf-8", "replace"))
        if g is None:
            note("grub.cfg cua ban ISO nay khac ban da biet - KHONG them duoc doan bao ve (may da co Proxmox / Windows van se bi tu cai sau 10 giay).")
        else:
            grub_new = g.encode("utf-8")
    aim = b'mode = "iso"\npartition_label = "proxmox-ais"\n\n[http]\n'           # đúng từng byte như proxmox-auto-install-assistant 9.x ghi
    ans = answer.encode("utf-8")
    base = sectors(src_size)
    lba_aim = base
    lba_ans = lba_aim + sectors(len(aim))
    lba_grub = lba_ans + sectors(len(ans))
    lba_fb = lba_grub + (sectors(len(grub_new)) if grub_new else 0)
    off_kho = (lba_fb + sectors(FB_MAX)) * SECT if payload else 0
    files = []
    pos = off_kho + HDR_LEN
    for name, path in payload:
        if not RX_MAU.match(name):
            raise Loi("ten ISO may mau phai co dang CloudBlue-MayMau-<ten>.iso: " + name)
        sz = os.path.getsize(path)
        if sz < 1024 * 1024:
            raise Loi("ISO may mau qua nho / hong: " + path)
        files.append({"name": name, "off": pos, "size": sz})
        pos += sectors(sz) * SECT
    total = pos if payload else (lba_fb + sectors(FB_MAX)) * SECT
    kho_id = os.environ.get("CB_PVE_KHO_ID") or ""                     # chỉ CI đặt (để 2 máy ghép ra file giống nhau từng byte)
    if not re.match(r"^[0-9a-f]{24}$", kho_id):
        kho_id = secrets.token_hex(12)
    nap_conf = {"id": kho_id, "off": off_kho, "size": total, "n": len(files)}
    fb = fb_make(nap_conf)
    if len(fb) > FB_MAX:
        raise Loi("script lan bat dau qua 1 MiB")
    taken = {r["iso"] for r in root}
    recs = []
    for rr, lba, data, mode in (("auto-installer-mode.toml", lba_aim, aim, 0o100444), ("answer.toml", lba_ans, ans, 0o100444), ("proxmox-first-boot", lba_fb, fb, 0o100555)):
        nm = iso_name(rr, taken)
        taken.add(nm)
        recs.append(new_record(tmpl, nm, rr, lba, len(data), mode))
    rootbuf_len = iso.root_size
    places = []
    for rec in recs:
        if end % SECT + len(rec) > SECT:
            end = (end // SECT + 1) * SECT
        if end + len(rec) > rootbuf_len:
            raise Loi("thu muc goc cua ban ISO Proxmox nay het cho trong - bao lai CloudBlue (can ban pve_iso.py moi)")
        places.append((end, rec))
        end += len(rec)
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(out_path)) or ".").free
    if free < total + 64 * 1024 * 1024:
        raise Loi("o dia chua file ISO moi khong du cho: can %.1f GB, con %.1f GB" % (total / 2**30, free / 2**30))
    part = out_path + ".part"
    sha = hashlib.sha256()
    try:
        with open(part, "wb") as o:
            say("   chep ISO Proxmox VE %s (%d MB) ..." % (release, src_size >> 20))
            with open(iso_path, "rb") as f:
                copy_stream(f, o, src_size, "ISO Proxmox", sha)
            if known_sha and sha.hexdigest() != known_sha:
                raise Loi("file ISO Proxmox VE %s KHONG khop ma kiem cua ban chinh thuc (tai loi / bi sua) - xoa file, tai lai tu proxmox.com" % release)
            for lba, data in ((lba_aim, aim), (lba_ans, ans), (lba_grub, grub_new), (lba_fb, fb)):
                if data is None:
                    continue
                if o.tell() != lba * SECT:
                    raise Loi("loi noi bo: lech vi tri ghi (%d / %d)" % (o.tell(), lba * SECT))
                o.write(data)
                pad(o)
            o.write(b"\0" * ((lba_fb + sectors(FB_MAX)) * SECT - o.tell()))
            if payload:
                o.write(b"\0" * HDR_LEN)
                for it, (name, path) in zip(files, payload):
                    if o.tell() != it["off"]:
                        raise Loi("loi noi bo: lech vi tri kho")
                    h = hashlib.sha256()
                    say("   them ISO may mau %s (%.2f GB) ..." % (name, it["size"] / 2**30))
                    with open(path, "rb") as f:
                        copy_stream(f, o, it["size"], name, h)
                    it["sha256"] = h.hexdigest()
                    pad(o)
                hdr = MAGIC + json.dumps({"v": 1, "id": kho_id, "size": total, "files": files}, sort_keys=True).encode() + b"\n"
                if len(hdr) > HDR_LEN:
                    raise Loi("qua nhieu ISO may mau cho 1 kho")
                o.seek(off_kho)
                o.write(hdr)
            o.flush()
            os.fsync(o.fileno())
        with open(part, "r+b") as o:
            if os.path.getsize(part) != total:
                raise Loi("loi noi bo: co file ra khac du tinh")
            o.seek(iso.root_lba * SECT)
            buf = bytearray(o.read(rootbuf_len))
            for at, rec in places:
                if any(buf[at:at + len(rec)]):
                    raise Loi("loi noi bo: cho trong cua thu muc goc khong trong")
                buf[at:at + len(rec)] = rec
            parse_dir(buf)
            o.seek(iso.root_lba * SECT)
            o.write(buf)
            if grub_new is not None:
                dlba, dsize, r = grub_hit
                o.seek(dlba * SECT + r["off"] + 2)
                o.write(b32(lba_grub) + b32(len(grub_new)))
            o.seek(16 * SECT + 80)
            o.write(b32(total // SECT))
            o.flush()
            os.fsync(o.fileno())
        check(part, {"auto-installer-mode.toml": aim, "answer.toml": ans, "proxmox-first-boot": fb}, grub_new, nap_conf if payload else None, files)
        if os.path.exists(out_path):
            os.remove(out_path)
        os.rename(part, out_path)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return {"size": total, "off": off_kho, "id": kho_id, "files": files, "guard": grub_new is not None, "release": release, "sha256_goc": sha.hexdigest()}


def check(path, want, grub_new, nap_conf, files):
    """Mở lại file vừa ghép: đọc lại 3 file mới + grub.cfg qua hệ tệp ISO, đầu mục kho — khác là dừng."""
    with open(path, "rb") as f:
        iso = Iso(f)
        if iso.vol_sectors * SECT != os.path.getsize(path):
            raise Loi("tu kiem: co volume khac co file")
        for name, data in want.items():
            if iso.read_file(name) != data:
                raise Loi("tu kiem: doc lai %s khong khop" % name)
        for must in (".pve-cd-id.txt", ".cd-info", "boot/grub/grub.cfg", "boot/linux26", "boot/initrd.img", "pve-installer.squashfs"):
            if iso.find(must) is None:
                raise Loi("tu kiem: mat %s" % must)
        if grub_new is not None and iso.read_file("boot/grub/grub.cfg") != grub_new:
            raise Loi("tu kiem: grub.cfg doc lai khong khop")
        if nap_conf:
            hdr = iso.read(nap_conf["off"], HDR_LEN)
            m = read_header(hdr)
            if not m or m.get("id") != nap_conf["id"] or [x["name"] for x in m["files"]] != [x["name"] for x in files]:
                raise Loi("tu kiem: dau muc kho ISO may mau khong khop")


def read_header(hdr):
    if not hdr.startswith(MAGIC):
        return None
    try:
        m = json.loads(hdr[len(MAGIC):hdr.index(b"\n", len(MAGIC))].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return m if isinstance(m, dict) and isinstance(m.get("files"), list) else None


# ---------------------------------------------------------------- tìm file, hỏi mật khẩu, lệnh
def drives():
    if os.name != "nt":
        return []
    res = []
    for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if os.path.isdir(c + ":\\"):
            res.append(c + ":\\")
    return res


def look_dirs():
    home = os.path.expanduser("~")
    ds = [os.path.join(home, x) for x in ("Downloads", "Desktop", "Documents")] + drives()
    if os.name != "nt":
        ds.append(os.getcwd())
    out = []
    for d in ds:
        if os.path.isdir(d) and d not in out:
            out.append(d)
            try:
                for e in os.scandir(d):
                    if e.is_dir(follow_symlinks=False) and not e.name.startswith(("$", ".")) and e.name.lower() not in ("windows", "program files", "program files (x86)", "programdata"):
                        out.append(e.path)
            except OSError:
                pass
    return out


def find_inputs(dirs):
    """→ ([(bản, đường dẫn) ISO Proxmox VE ≥ 9, mới nhất trước], {tag: đường dẫn ISO máy mẫu mới nhất})"""
    pve, mau = {}, {}
    for d in dirs:
        try:
            ents = list(os.scandir(d))
        except OSError:
            continue
        for e in ents:
            try:
                if not e.is_file() or e.name.endswith(".part"):
                    continue
                m = RX_PVE.match(e.name)
                if m and e.stat().st_size > MIN_ISO:
                    v = tuple(int(x) for x in m.groups())
                    if v[0] >= 9 and (v not in pve or e.stat().st_mtime > pve[v][0]):
                        pve[v] = (e.stat().st_mtime, e.path)
                m = RX_MAU.match(e.name)
                if m and e.stat().st_size > MIN_ISO:
                    if m.group(1) not in mau or e.stat().st_mtime > mau[m.group(1)][0]:
                        mau[m.group(1)] = (e.stat().st_mtime, e.path)
            except OSError:
                continue
    return [("%d.%d-%d" % v, pve[v][1]) for v in sorted(pve, reverse=True)], {k: v[1] for k, v in sorted(mau.items())}


def download(url, dst):
    import urllib.request
    say("   tai %s ..." % url)
    req = urllib.request.Request(url, headers={"User-Agent": "cloudblue-pve-iso/" + VER})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst + ".part", "wb") as o:
        total = int(r.headers.get("Content-Length") or 0)
        if total < 500 * 1024 * 1024:
            raise Loi("may chu tra ve file la (co %d)" % total)
        copy_stream(r, o, total, "ISO Proxmox")
    os.replace(dst + ".part", dst)


def ask_password():
    say("")
    say("   Dat MAT KHAU root cho may chu Proxmox (dung de vao trang quan ly https://<IP>:8006).")
    say("   Go mat khau roi Enter (chu KHONG hien ra khi go). It nhat 8 ky tu, khong dau. Nho ky - khong gui cho ai.")
    for _ in range(5):
        a = getpass.getpass("   Mat khau root: ")
        if len(a) < 8 or not all(33 <= ord(c) <= 126 for c in a):
            say("   -> can it nhat 8 ky tu, chi chu / so / ky hieu khong dau, khong co dau cach. Go lai.")
            continue
        b = getpass.getpass("   Go lai lan nua: ")
        if a != b:
            say("   -> hai lan go khac nhau. Go lai.")
            continue
        return a
    raise Loi("chua dat duoc mat khau root")


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="pve_iso.py")
    ap.add_argument("--iso", default="")
    ap.add_argument("--mau", action="append", default=[])
    ap.add_argument("--khong-mau", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--work", default="")
    ap.add_argument("--nguon", default="", help="thu muc co pve_firstboot.sh, cb_nap.py (mac dinh: canh file nay) va cbhost.py (thu muc cha)")
    ap.add_argument("--ten", default="cbvps")
    ap.add_argument("--o", default="")
    ap.add_argument("--ip", default="")
    ap.add_argument("--gateway", default="")
    ap.add_argument("--dns", default="")
    ap.add_argument("--pw-hash-env", default="CB_PVE_PW_HASH")
    ap.add_argument("--ssh-key", action="append", default=[])
    ap.add_argument("--conf", default="", help="JSON ghi de cau hinh cbhost (chi dung khi thu)")
    ap.add_argument("--tat-may", action="store_true", help="cai xong thi tat may (mac dinh: tu khoi dong lai)")
    ap.add_argument("--khong-bao-ve", action="store_true")
    ap.add_argument("--khong-hoi", action="store_true")
    a = ap.parse_args(argv)
    here = os.path.dirname(os.path.abspath(__file__))
    src = a.nguon or here
    need = {"fb": os.path.join(src, "pve_firstboot.sh"), "nap": os.path.join(src, "cb_nap.py"),
            "cbhost": next((p for p in (os.path.join(src, "cbhost.py"), os.path.join(os.path.dirname(src), "cbhost.py")) if os.path.isfile(p)), "")}
    for k, p in need.items():
        if not p or not os.path.isfile(p):
            raise Loi("thieu file nguon (%s)" % k)
    say("  CloudBlue - GHEP ISO PROXMOX TU CAI (ban %s)" % VER)
    dirs = look_dirs() + ([os.path.join(a.work, "dl")] if a.work else [])
    f_pve, f_mau = find_inputs(dirs)
    say("== 1/4  File ISO Proxmox VE goc")
    iso = a.iso.strip().strip('"')
    if not iso:
        iso = next((p for v, p in f_pve if v in KNOWN), "")                 # ưu tiên bản ĐÃ THỬ cài thật
        la = f_pve[0] if f_pve else None
        if not iso and a.work:
            dl = os.path.join(a.work, "dl", "proxmox-ve_%s.iso" % PVE_DEFAULT)
            os.makedirs(os.path.dirname(dl), exist_ok=True)
            if la:
                say("   thay %s nhung ban %s chua duoc CloudBlue cai thu -> dung ban da thu %s" % (la[1], la[0], PVE_DEFAULT))
            else:
                say("   khong thay file proxmox-ve_*.iso tren may")
            say("   -> tu tai ban %s (1,8 GB) tu may chu chinh thuc cua Proxmox" % PVE_DEFAULT)
            try:
                download(PVE_URL % PVE_DEFAULT, dl)
                iso = dl
            except Exception as e:
                if not la:
                    raise Loi("khong tu tai duoc ISO Proxmox (%s). Tai bang Chrome: %s  -> de trong Downloads roi chay lai lenh." % (str(e)[:120], PVE_URL % PVE_DEFAULT))
                say("   (!) khong tai duoc (%s) -> dung tam ban %s dang co" % (str(e)[:100], la[0]))
        if not iso and la:
            iso = la[1]
        if not iso:
            raise Loi("khong thay file proxmox-ve_*.iso - tai tu https://www.proxmox.com/en/downloads roi chay lai (hoac dung --iso)")
    if not os.path.isfile(iso):
        raise Loi("khong thay file: " + iso)
    say("   " + iso)
    say("== 2/4  ISO may mau Windows (kem vao de may chu TU dung may mau)")
    payload = []
    if not a.khong_mau:
        paths = [p.strip().strip('"') for x in a.mau for p in x.split(",") if p.strip()] or list(f_mau.values())
        for p in paths:
            if not os.path.isfile(p):
                raise Loi("khong thay file: " + p)
            if not RX_MAU.match(os.path.basename(p)):
                raise Loi("ISO may mau phai la file do lenh ghep ISO may mau tao ra (CloudBlue-MayMau-<ten>.iso): " + p)
            if os.path.basename(p) in [n for n, _ in payload]:
                raise Loi("trung ISO may mau: " + os.path.basename(p))
            payload.append((os.path.basename(p), p))
            say("   + %s  (%.2f GB)" % (p, os.path.getsize(p) / 2**30))
    if not payload:
        say("   (!) KHONG kem ISO may mau nao -> may chu cai xong chua co may mau; dung sau bang bang dieu khien may mau tren web.")
    say("== 3/4  Mat khau root + cau hinh")
    pw_hash = os.environ.get(a.pw_hash_env) or ""
    if not pw_hash:
        if a.khong_hoi:
            raise Loi("che do khong hoi can bien moi truong %s (ma bam mat khau root)" % a.pw_hash_env)
        pw_hash = sha512_crypt(ask_password())
    answer = answer_toml(pw_hash, a.ten, a.o, a.ip, a.gateway, a.dns, a.ssh_key, "power-off" if a.tat_may else "reboot")
    conf = {"auto_tpl": True}
    if a.conf:
        conf.update(json.loads(a.conf))
    say("   ten may chu: %s | mang: %s | o cai: %s | may mau kem: %d" % (a.ten, a.ip or "tu nhan (DHCP)", a.o or "o dia dau tien (khong tinh USB)", len(payload)))
    read = lambda p, mode="rb": open(p, mode).read()
    tmpl = open(need["fb"], encoding="utf-8").read()
    fb_make = lambda nap_conf: first_boot(tmpl, read(need["cbhost"]), read(need["nap"]), conf, nap_conf)
    out = a.out.strip().strip('"')
    if not out:
        base = a.work or os.path.dirname(os.path.abspath(iso))
        out = os.path.join(os.path.splitdrive(os.path.abspath(base))[0] + os.sep if os.name == "nt" else base, "CloudBlue-Proxmox.iso")
    say("== 4/4  Ghep -> " + out)
    notes = []
    t0 = time.time()
    res = build(iso, out, answer, fb_make, payload, guard=not a.khong_bao_ve, note=lambda mm: (notes.append(mm), say("   (!) " + mm)))
    if res["release"] not in KNOWN:
        notes.append("Ban Proxmox VE %s chua duoc CloudBlue cai thu (da thu: %s). Thuong van chay; loi thi dung ban da thu." % (res["release"], ", ".join(sorted(KNOWN))))
    say("")
    say("  ======================================================")
    say("  XONG (%.1f phut): %s  (%.2f GB)" % ((time.time() - t0) / 60, out, res["size"] / 2**30))
    say("  Proxmox VE %s | may chu '%s' | %s | may mau kem: %s" % (res["release"], a.ten, "bao ve may da co Proxmox / Windows: CO" if res["guard"] else "bao ve: KHONG",
                                                                   ", ".join(RX_MAU.match(n).group(1) for n, _ in payload) or "khong"))
    say("  ======================================================")
    say("  Buoc tiep:")
    say("   1. Ghi file ISO nay ra USB (tu %d GB tro len) bang Rufus: chon file -> START -> hoi thi chon 'Write in DD Image mode'." % (16 if res["size"] > 7 * 2**30 else 8))
    say("   2. Cam USB vao MAY CHU (da bat Virtualization trong BIOS, co cap mang), khoi dong tu USB. Sau 10 giay may TU CAI Proxmox (5-15 phut),")
    say("      tu khoi dong lai. DE NGUYEN USB den khi web bao may mau da co (may chu chep ISO may mau tu USB).")
    say("   3. Web CloudBlue > Quan tri > VPS ao hoa > May chu: bam DUYET may moi. May chu tu dung may mau (moi ban 20-40 phut).")
    say("   ISO nay XOA SACH o dia dau tien cua may khoi dong tu no (tru may dang co Windows / da co Proxmox: khong tu cai). Giu USB can than.")
    for n in notes:
        say("   (!) " + n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Loi as e:
        say("")
        say("!! DUNG: %s" % e)
        sys.exit(1)
    except KeyboardInterrupt:
        say("")
        say("!! Da dung theo yeu cau (Ctrl + C).")
        sys.exit(1)
