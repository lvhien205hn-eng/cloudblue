#!/usr/bin/env python3
"""Thử bộ ghép ISO PROXMOX TỰ CÀI (proxmox/vm/pve_iso.py), bộ nạp kho ISO máy mẫu trên máy chủ (cb_nap.py) và script lần bật đầu (pve_firstboot.sh).
   Dùng 1 ISO 9660 + Rock Ridge GIẢ dựng ngay trong bộ thử (bố cục như ISO Proxmox VE 9: thư mục gốc 2 sector còn chỗ trống, tên 8.3, PX 36 byte).
   ISO Proxmox THẬT + cài thật trong máy ảo: chạy trên CI (proxmox/tests/ci/pve_ci.sh).   python3 proxmox/tests/test_pve_iso.py"""
import base64, hashlib, importlib.util, json, os, re, shutil, stat, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


tmp = tempfile.mkdtemp(prefix="pveiso_")
os.environ.update(CBNAP_CONF=os.path.join(tmp, "nap.json"), CBNAP_DEST=os.path.join(tmp, "kho-iso"), CBNAP_DONE=os.path.join(tmp, "nap-xong.json"),
                  CBNAP_MNT=os.path.join(tmp, "mnt"), CBNAP_SYSBLOCK=os.path.join(tmp, "sysblock"))
pi = load("pve_iso", os.path.join(ROOT, "vm", "pve_iso.py"))
nap = load("cb_nap", os.path.join(ROOT, "vm", "cb_nap.py"))
pi.say = lambda *a: None
nap.log = lambda *a: None
S = 2048
b32, b16 = pi.b32, lambda n: struct.pack("<H", n) + struct.pack(">H", n)
DATE = bytes([126, 11, 25, 12, 34, 37, 0])
PX = lambda mode: b"PX\x24\x01" + b32(mode) + b32(1) + b32(0) + b32(0)
TF = b"TF\x1a\x01\x0e" + DATE * 3


def rec(iso, ext, size, flags, rr=None, mode=0o100444, sp=False):
    su = (b"SP\x07\x01\xbe\xef\x00" if sp else b"") + PX(mode) + TF + ((b"NM" + bytes([5 + len(rr), 1, 0]) + rr.encode()) if rr else b"")
    r = bytes([0, 0]) + b32(ext) + b32(size) + DATE + bytes([flags, 0, 0]) + b16(1) + bytes([len(iso)]) + iso + (b"" if len(iso) % 2 else b"\0") + su
    if len(r) % 2: r += b"\0"
    return bytes([len(r)]) + r[1:]


def pack(recs, sects):
    """Xếp bản ghi vào thư mục cỡ sects sector — bản ghi không vắt qua ranh sector."""
    buf = bytearray(sects * S); o = 0
    for r in recs:
        if o % S + len(r) > S: o = (o // S + 1) * S
        assert o + len(r) <= len(buf), "thư mục giả quá đầy"
        buf[o:o + len(r)] = r; o += len(r)
    return bytes(buf)


def mk_iso(path, release="9.3", fill=14, grub=None, product="pve", capable=True, root_sects=2):
    """ISO giả: / (2 sector) có .cd-info, .pve-cd-id.txt, auto-installer-capable, boot/{linux26, initrd.img, grub/grub.cfg}, pve-installer.squashfs + file độn."""
    grub = GRUB if grub is None else grub
    files = {"_CD_INFO.;1": (".cd-info", ("RELEASE='%s'\nISORELEASE='1'\nISONAME='proxmox-ve'\nARCH='amd64'\nPRODUCT='%s'\nPRODUCTLONG='Proxmox VE'\n" % (release, product)).encode()),
             "_PVE_CD_.TXT;1": (".pve-cd-id.txt", b"01a212ae-abac-7db3-9d92-09149ac34b46\n"), "PVE_INST.SQU;1": ("pve-installer.squashfs", os.urandom(5000))}
    if capable: files["AUTO_INS.;1"] = ("auto-installer-capable", b"")
    for i in range(fill): files["DON%05d.TXT;1" % i] = ("file-don-%05d-ten-dai-cho-ton-cho.txt" % i, b"don %d\n" % i)
    boot = {"LINUX26.;1": ("linux26", os.urandom(3000)), "INITRD.IMG;1": ("initrd.img", os.urandom(4100))}
    gf = {"GRUB.CFG;1": ("grub.cfg", grub.encode())}
    L_ROOT, L_BOOT, L_GRUB = 19, 19 + root_sects + 1, 19 + root_sects + 2          # (1 sector "CE" giả giữa gốc và boot)
    lba = [L_GRUB + 1]
    def place(d):
        out = {}
        for k, (rr, data) in sorted(d.items()):
            out[k] = (rr, data, lba[0] if data else 4676); lba[0] += (len(data) + S - 1) // S
        return out
    files, boot, gf = place(files), place(boot), place(gf)
    def dirbuf(me, parent, kids, sects, sp=False):
        rs = [rec(b"\0", me[0], me[1], 2, None, 0o040555, sp), rec(b"\1", parent[0], parent[1], 2, None, 0o040555)]
        for k in sorted(kids): rs.append(kids[k])
        return pack(rs, sects)
    frec = lambda d: {k.encode(): rec(k.encode(), l, len(data), 0, rr) for k, (rr, data, l) in d.items()}
    rk = frec(files); rk[b"BOOT"] = rec(b"BOOT", L_BOOT, S, 2, "boot", 0o040555)
    bk = frec(boot); bk[b"GRUB"] = rec(b"GRUB", L_GRUB, S, 2, "grub", 0o040555)
    img = bytearray(lba[0] * S + 3 * S)
    img[0:4] = b"MBRX"; img[512:520] = b"EFI PART"
    pvd = bytearray(S); pvd[0:7] = b"\x01CD001\x01"; pvd[40:43] = b"PVE"; pvd[80:88] = b32(len(img) // S); pvd[120:124] = b16(1); pvd[124:128] = b16(1); pvd[128:132] = b16(S)
    pvd[156:190] = rec(b"\0", L_ROOT, root_sects * S, 2)[:34]; pvd[156] = 34
    pvd[813:830] = b"2026112512343700\0"; pvd[830:847] = b"2026112512343700\0"
    img[16 * S:17 * S] = pvd
    img[17 * S:17 * S + 30] = b"\x00CD001\x01EL TORITO SPECIFICATION"
    img[18 * S:18 * S + 7] = b"\xffCD001\x01"
    img[L_ROOT * S:(L_ROOT + root_sects) * S] = dirbuf((L_ROOT, root_sects * S), (L_ROOT, root_sects * S), rk, root_sects, sp=True)
    img[L_BOOT * S:(L_BOOT + 1) * S] = dirbuf((L_BOOT, S), (L_ROOT, root_sects * S), bk, 1)
    img[L_GRUB * S:(L_GRUB + 1) * S] = dirbuf((L_GRUB, S), (L_BOOT, S), frec(gf), 1)
    for d in (files, boot, gf):
        for k, (rr, data, l) in d.items(): img[l * S:l * S + len(data)] = data
    img[-S:-S + 8] = b"EFI PART"                                                         # "GPT dự phòng" ở cuối như ISO thật
    open(path, "wb").write(img)
    return {"files": files, "boot": boot, "grub": gf}


GRUB = """insmod gzio
insmod iso9660
set gfxmode=1024x768,640x480

if [ -f auto-installer-mode.toml ]; then
    set timeout-style=menu
    set timeout=10

    menuentry 'Install Proxmox VE (Automated)' --class debian {
        linux       /boot/linux26 ro ramdisk_size=16777216 rw quiet splash=silent proxmox-start-auto-installer
        initrd      /boot/initrd.img
     }
fi

menuentry 'Install Proxmox VE (Graphical)' --class debian {
    linux	/boot/linux26 ro ramdisk_size=16777216 rw quiet splash=silent
    initrd	/boot/initrd.img
}

submenu 'Advanced Options' {
    menuentry 'Rescue Boot' --class debian {
        insmod lvm
        insmod ext2
        if test -e (lvm/pve-root)/boot/pve/vmlinuz; then
            linux (lvm/pve-root)/boot/pve/vmlinuz ro ramdisk_size=16777216 root=/dev/mapper/pve-root
            initrd (lvm/pve-root)/boot/pve/initrd.img
            boot
        fi
    }
}
"""
HASH = "$6$cbthu2611$f/E0E88wcetQEiEUYlTyWFTUy6Z7TbfRVRumzXvH6Y7PrcDqL/zDnnrZbu/Y3U6C2jgRc7NYkg2APNr17bDyX1"

print("1. Mật khẩu root (SHA-512 crypt) · answer.toml")
ck("băm đúng thuật toán glibc ($6$): khớp 2 mẫu đã biết", pi.sha512_crypt("CbThu-2611!", "cbthu2611") == HASH
   and pi.sha512_crypt("Hello world!", "saltstring") == "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1")
h1, h2 = pi.sha512_crypt("matkhau-thu-1"), pi.sha512_crypt("matkhau-thu-1")
ck("mỗi lần băm 1 muối ngẫu nhiên 16 ký tự (2 lần băm cùng mật khẩu ra khác nhau)", h1 != h2 and re.match(r"^\$6\$[./0-9A-Za-z]{16}\$[./0-9A-Za-z]{86}$", h1), h1)
a = pi.answer_toml(HASH)
ck("mặc định: bàn phím en-us, VN, giờ Việt Nam, mạng DHCP, ổ đĩa đầu tiên (lọc DEVTYPE=disk), ext4, tự khởi động lại, có script lần bật đầu từ ISO, mật khẩu chỉ ở dạng băm",
   all(x in a for x in ('keyboard = "en-us"', 'country = "vn"', 'timezone = "Asia/Ho_Chi_Minh"', 'fqdn = "cbvps.lan"', 'source = "from-dhcp"', 'filter.DEVTYPE = "disk"',
                        'filesystem = "ext4"', 'reboot-mode = "reboot"', 'reboot-on-error = false', '[first-boot]\nsource = "from-iso"\nordering = "fully-up"',
                        'root-password-hashed = "%s"' % HASH)) and "root-password =" not in a and "disk-list" not in a, a)
a2 = pi.answer_toml(HASH, "vps1", "nvme0n1", "192.168.1.50/24", "192.168.1.1", "8.8.8.8", ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyFakeKeyFakeKeyFakeKeyFakeKeyFakeKey thu@ci"], "power-off")
ck("tuỳ chọn: tên máy, ổ chỉ định, IP tĩnh, khoá SSH (chỉ CI dùng), cài xong tắt máy", all(x in a2 for x in ('fqdn = "vps1.lan"', 'disk-list = ["nvme0n1"]', 'source = "from-answer"',
   'cidr = "192.168.1.50/24"', 'gateway = "192.168.1.1"', 'dns = "8.8.8.8"', 'root-ssh-keys = ["ssh-ed25519 ', 'reboot-mode = "power-off"')) and "filter." not in a2, a2)
def bad(fn, *args, **kw):
    try: fn(*args, **kw); return False
    except pi.Loi: return True
ck("từ chối: tên máy lạ, ổ lạ, IP thiếu mục / sai, mã băm lạ (không cho chèn dòng vào answer.toml)", bad(pi.answer_toml, HASH, 'x"\ny = 1') and bad(pi.answer_toml, HASH, "Cb_Vps")
   and bad(pi.answer_toml, HASH, "cbvps", "sda; rm") and bad(pi.answer_toml, HASH, "cbvps", "", "192.168.1.50/24") and bad(pi.answer_toml, HASH, "cbvps", "", "192.168.1.500/24", "192.168.1.1", "8.8.8.8")
   and bad(pi.answer_toml, 'abc"\nroot-password = "x') and bad(pi.answer_toml, HASH, "cbvps", "", "", "", "", ['ssh-rsa AAAA"\nx = 1']))

print("2. Đoạn bảo vệ trong grub.cfg")
g = pi.grub_guard(GRUB)
i_g, i_a = g.index(pi.GUARD_MARK), g.index("if [ -f auto-installer-mode.toml ]; then")
ck("chèn TRƯỚC khối tự cài, phần còn lại của grub.cfg giữ nguyên từng ký tự", i_g < i_a and g[:i_g] + g[g.index("# ---- het doan CloudBlue ----\n\n") + len("# ---- het doan CloudBlue ----\n\n"):] == GRUB, (i_g, i_a))
ck("máy đã có Proxmox (LVM pve) → mục đầu = khởi động từ ổ cứng (đúng lệnh Rescue Boot của Proxmox); máy có Windows → mục đầu chỉ báo, không cài",
   "if test -e (lvm/pve-root)/boot/pve/vmlinuz; then\n    set cb_co=pve" in g and "linux (lvm/pve-root)/boot/pve/vmlinuz ro ramdisk_size=16777216 root=/dev/mapper/pve-root quiet" in g
   and "search --no-floppy --file /Windows/System32/ntoskrnl.exe --set cb_win" in g and "KHONG tu cai" in g and "proxmox-start-auto-installer" not in g[i_g:i_a])
ck("grub.cfg chỉ có chữ ASCII (màn hình GRUB không dấu)", all(ord(c) < 128 for c in g[i_g:i_a]))
ck("grub.cfg khác cấu trúc đã biết / đã có đoạn bảo vệ → không đụng (trả None)", pi.grub_guard(GRUB.replace("if [ -f auto-installer-mode.toml ]", "if [ -f x ]")) is None
   and pi.grub_guard(GRUB.replace("(lvm/pve-root)/boot/pve/vmlinuz", "/vmlinuz")) is None and pi.grub_guard(g) is None)

print("3. Ghép ISO (ISO giả bố cục như Proxmox VE 9)")
src = os.path.join(tmp, "proxmox-ve_9.3-1.iso"); out = os.path.join(tmp, "CloudBlue-Proxmox.iso")
lay = mk_iso(src)
m1 = os.path.join(tmp, "CloudBlue-MayMau-win2012r2.iso"); m2 = os.path.join(tmp, "CloudBlue-MayMau-win2016.iso")
open(m1, "wb").write(os.urandom(1024 * 1024 + 777)); open(m2, "wb").write(os.urandom(3 * 1024 * 1024 + 5))
tmpl = open(os.path.join(ROOT, "vm", "pve_firstboot.sh"), encoding="utf-8").read()
cbhost_b = open(os.path.join(ROOT, "cbhost.py"), "rb").read(); nap_b = open(os.path.join(ROOT, "vm", "cb_nap.py"), "rb").read()
fb_make = lambda nc: pi.first_boot(tmpl, cbhost_b, nap_b, {"auto_tpl": True}, nc)
notes = []
res = pi.build(src, out, a, fb_make, [(os.path.basename(m1), m1), (os.path.basename(m2), m2)], known={}, note=notes.append)
o_b, s_b = open(out, "rb").read(), open(src, "rb").read()
iso = pi.Iso(open(out, "rb"))
ck("ra file · cỡ = bội 2048 · PVD ghi đúng tổng số sector · không còn file .part", len(o_b) == res["size"] and len(o_b) % S == 0 and iso.vol_sectors * S == len(o_b) and not os.path.exists(out + ".part"), res)
changed = sorted({i // S for i in range(0, len(s_b), S) if s_b[i:i + S] != o_b[i:i + S]})
gl = iso.find("boot/grub/grub.cfg")
ck("phần ISO gốc: CHỈ đổi sector 16 (cỡ volume), sector trống cuối thư mục gốc và sector thư mục /boot/grub — MBR / GPT / El Torito / mọi file giữ nguyên từng byte",
   changed == sorted({16, 20, gl[0]}) and o_b[:16 * S] == s_b[:16 * S] and o_b[17 * S:19 * S] == s_b[17 * S:19 * S] and o_b[19 * S:20 * S] == s_b[19 * S:20 * S], changed)
ck("ngày tạo / sửa volume (GRUB EFI tìm ISO theo số này) giữ nguyên", o_b[16 * S + 813:16 * S + 881] == s_b[16 * S + 813:16 * S + 881])
fb = iso.read_file("proxmox-first-boot")
ck("3 file mới đọc được qua hệ tệp ISO, đúng tên Rock Ridge: auto-installer-mode.toml (đúng từng byte bản chính thức), answer.toml, proxmox-first-boot",
   iso.read_file("auto-installer-mode.toml") == b'mode = "iso"\npartition_label = "proxmox-ais"\n\n[http]\n' and iso.read_file("answer.toml") == a.encode() and fb.startswith(b"#!/bin/bash\n")
   and len(fb) < pi.FB_MAX)
root = iso.root(); old_root = pi.Iso(open(src, "rb")).root()
new = [r for r in root if r["name"] in pi.NEW_FILES]
ck("bản ghi cũ của thư mục gốc giữ nguyên · 3 bản ghi mới: tên 8.3 không trùng, file thường, PX / TF như file sẵn có, script lần bật đầu có quyền chạy",
   [r["raw"] for r in root[:len(old_root)]] == [r["raw"] for r in old_root] and len(new) == 3 and len({r["iso"] for r in root}) == len(root)
   and sorted(r["iso"] for r in new) == [b"ANSWER.TOM;1", b"AUTO_INS.TOM;1", b"PROXMOX_.;1"] and all(not r["flags"] and r["len"] % 2 == 0 and r["ext"] * S >= len(s_b) for r in new)
   and all(dict(pi.susp(r["su"]))[b"TF"] == TF for r in new) and pi.le32(dict(pi.susp(next(r for r in new if r["name"] == "proxmox-first-boot")["su"]))[b"PX"][4:8]) == 0o100555,
   [(r["iso"], r["name"]) for r in new])
ck("mọi file cũ đọc lại y nguyên (kernel, initrd, squashfs, .cd-info …)", all(iso.read_file(rr) == data for d, pre in ((lay["files"], ""), (lay["boot"], "boot/")) for k, (rr, data, l) in d.items()
   for rr in [pre + rr]))
gnew = iso.read_file("boot/grub/grub.cfg").decode()
ck("grub.cfg trong ISO = bản có đoạn bảo vệ (dữ liệu mới ở cuối; bản cũ còn nguyên chỗ cũ)", gnew == g and res["guard"] is True and gl[2]["ext"] * S >= len(s_b)
   and GRUB.encode() in o_b[:len(s_b)])
hdr = pi.read_header(o_b[res["off"]:res["off"] + pi.HDR_LEN])
ck("kho ISO máy mẫu nối sau cùng: đầu mục có tên, vị trí, cỡ, SHA-256 đúng từng file; dữ liệu khớp", hdr and hdr["id"] == res["id"] and [x["name"] for x in hdr["files"]] ==
   ["CloudBlue-MayMau-win2012r2.iso", "CloudBlue-MayMau-win2016.iso"] and all(o_b[x["off"]:x["off"] + x["size"]] == open(p, "rb").read() and
   x["sha256"] == hashlib.sha256(open(p, "rb").read()).hexdigest() and x["off"] % S == 0 for x, p in zip(hdr["files"], (m1, m2))) and res["off"] % S == 0, hdr)
ck("ghép lại lên ISO đã ghép → từ chối rõ (phải dùng ISO Proxmox gốc)", bad(pi.build, out, out + "2", a, fb_make) and not os.path.exists(out + "2") and not os.path.exists(out + "2.part"))
out2 = os.path.join(tmp, "khong-kho.iso")
r2 = pi.build(src, out2, a, fb_make, [], known={}, note=notes.append)
i2 = pi.Iso(open(out2, "rb"))
ck("không kèm ISO máy mẫu → vẫn ra ISO tự cài (không có kho, script lần bật đầu biết không có gì để nạp)", r2["off"] == 0 and r2["files"] == [] and i2.read_file("answer.toml") == a.encode()
   and os.path.getsize(out2) == r2["size"] < len(s_b) + 2 * 1024 * 1024 + 4 * S)
ck("mã kiểm ISO gốc: bản đã biết mà sai mã → dừng, không để lại file; đúng mã → ghép", bad(pi.build, src, out + "3", a, fb_make, [], known={"9.3-1": "0" * 64}) and not os.path.exists(out + "3")
   and not os.path.exists(out + "3.part") and pi.build(src, out + "3", a, fb_make, [], known={"9.3-1": hashlib.sha256(s_b).hexdigest()})["release"] == "9.3-1")
for nm, kw in (("Proxmox VE 8 (quá cũ)", {"release": "8.4"}), ("không phải Proxmox VE", {"product": "pbs"}), ("ISO không có dấu hỗ trợ tự cài", {"capable": False})):
    p = os.path.join(tmp, "x.iso"); mk_iso(p, **kw)
    ck("từ chối: " + nm, bad(pi.build, p, p + ".out", a, fb_make, [], known={}) and not os.path.exists(p + ".out"))
p = os.path.join(tmp, "day.iso")
for n in range(26, 10, -1):                       # thư mục gốc giả đầy nhất có thể (còn thừa < 1 bản ghi)
    try: mk_iso(p, fill=n); break
    except AssertionError: continue
ck("thư mục gốc hết chỗ trống → dừng với thông báo rõ (không ghi đè lung tung)", bad(pi.build, p, p + ".out", a, fb_make, [], known={}) and not os.path.exists(p + ".out"))
p = os.path.join(tmp, "grubla.iso"); mk_iso(p, grub=GRUB.replace("if [ -f auto-installer-mode.toml ]", "if [ -f khac ]")); nn = []
r3 = pi.build(p, p + ".out", a, fb_make, [], known={}, note=nn.append)
ck("grub.cfg bản lạ → vẫn ghép, giữ nguyên grub.cfg, có ghi chú 'không thêm được đoạn bảo vệ'", r3["guard"] is False and len(nn) == 1 and "bao ve" in nn[0]
   and pi.Iso(open(p + ".out", "rb")).read_file("boot/grub/grub.cfg") == open(p, "rb").read().split(b"insmod gzio")[0][:0] + GRUB.replace("if [ -f auto-installer-mode.toml ]", "if [ -f khac ]").encode())
ck("tên ISO máy mẫu lạ / file quá nhỏ → từ chối", bad(pi.build, src, out + "4", a, fb_make, [("la.iso", m1)], known={}) and bad(pi.build, src, out + "4", a, fb_make, [("CloudBlue-MayMau-x1y.iso", src[:-4] + ".nho")], known={})
   if not open(src[:-4] + ".nho", "wb").write(b"x" * 100) is None else False)

print("4. Script lần bật đầu (chạy thật trong thư mục tạm, systemctl giả)")
sand = os.path.join(tmp, "may"); os.makedirs(os.path.join(sand, "bin")); os.makedirs(os.path.join(sand, "systemd")); os.makedirs(os.path.join(sand, "net"))
open(os.path.join(sand, "net", "address"), "w").write("bc:24:11:aa:3f:a2\n")
for tool, body in (("systemctl", 'echo "systemctl $*" >> "%s/systemctl.log"' % sand), ("hostname", "echo cbvps")):
    fp = os.path.join(sand, "bin", tool); open(fp, "w").write("#!/bin/sh\n%s\n" % body); os.chmod(fp, 0o755)
sh = fb.decode()
for old, new_ in (("/var/log/cloudblue-firstboot.log", sand + "/firstboot.log"), ("DIR=/opt/cloudblue", "DIR=%s/opt" % sand), ("ETC=/etc/cloudblue", "ETC=%s/etc" % sand),
                  ("VAR=/var/lib/cloudblue", "VAR=%s/var" % sand), ("/etc/systemd/system/", sand + "/systemd/"), ("/sys/class/net/vmbr0/address", sand + "/net/address")):
    assert old in sh, old
    sh = sh.replace(old, new_)
open(os.path.join(sand, "fb.sh"), "w").write(sh)
rc = subprocess.run(["bash", os.path.join(sand, "fb.sh"), "fully-up"], env=dict(os.environ, PATH=os.path.join(sand, "bin") + ":" + os.environ["PATH"]), capture_output=True, text=True)
lg = open(sand + "/firstboot.log").read() if os.path.exists(sand + "/firstboot.log") else ""
ck("chạy xong mã 0, không dòng LOI", rc.returncode == 0 and "LOI" not in lg and "xong first-boot" in lg, (rc.returncode, rc.stderr[-300:], lg[-600:]))
ck("bung đúng cbhost.py + cb_nap.py (từng byte) vào /opt/cloudblue, quyền chạy", open(sand + "/opt/cbhost.py", "rb").read() == cbhost_b and open(sand + "/opt/cb_nap.py", "rb").read() == nap_b
   and os.stat(sand + "/opt/cbhost.py").st_mode & 0o111)
cf = json.load(open(sand + "/etc/cbhost.conf")); nc = json.load(open(sand + "/etc/nap.json"))
ck("cấu hình cbhost: bật tự dựng máy mẫu + tên riêng cbvps-<4 số cuối MAC>; nap.json: đúng mã kho / vị trí / cỡ; file cấu hình chỉ root đọc",
   cf == {"auto_tpl": True, "host_name": "cbvps-3fa2"} and nc == {"id": res["id"], "off": res["off"], "size": res["size"], "n": 2}
   and stat.S_IMODE(os.stat(sand + "/etc/cbhost.conf").st_mode) == 0o600 and stat.S_IMODE(os.stat(sand + "/etc").st_mode) == 0o700, (cf, nc))
u1, u2 = open(sand + "/systemd/cloudblue-cbhost.service").read(), open(sand + "/systemd/cloudblue-nap.service").read()
sl = open(sand + "/systemctl.log").read()
ck("2 dịch vụ: cbhost (tự bật lại, chạy khi bật máy) + nap (thôi khi đã nạp xong); đã bật + chạy, không chặn lần bật đầu", "cbhost.py run" in u1 and "Restart=always" in u1
   and "cb_nap.py run" in u2 and "ConditionPathExists=!%s/var/nap-xong.json" % sand in u2 and "enable cloudblue-cbhost cloudblue-nap" in sl
   and "start --no-block cloudblue-nap" in sl and "restart --no-block cloudblue-cbhost" in sl, sl)
open(sand + "/etc/cbhost.conf", "w").write(json.dumps({"auto_tpl": False, "host_name": "may-rieng"}))
subprocess.run(["bash", os.path.join(sand, "fb.sh")], env=dict(os.environ, PATH=os.path.join(sand, "bin") + ":" + os.environ["PATH"]), capture_output=True)
ck("chạy lại khi đã có cấu hình (cài đè) → giữ nguyên cấu hình cũ", json.load(open(sand + "/etc/cbhost.conf")) == {"auto_tpl": False, "host_name": "may-rieng"})
ck("script không chứa khoá bí mật / mật khẩu (chỉ có khoá công khai của web trong cbhost.py)", HASH not in fb.decode() and "service_role" not in fb.decode() and "cbsv_" not in fb.decode())

print("5. Nạp kho ISO máy mẫu trên máy chủ (cb_nap.py) — đọc thẳng 'USB' = file ISO vừa ghép")
shutil.copy(sand + "/etc/nap.json", os.environ["CBNAP_CONF"])
conf = nap.load_conf(); dest = os.environ["CBNAP_DEST"]
ck("thiết bị khác (ISO Proxmox gốc / ISO ghép lần khác / file ngắn) → không nhận", nap.once(conf, src=src, dest_dir=dest) is None and nap.once(conf, src=out2, dest_dir=dest) is None
   and nap.once(dict(conf, id="0" * 24), src=out, dest_dir=dest) is None and not os.path.exists(dest))
r = nap.once(conf, src=out, dest_dir=dest)
ck("đúng USB → chép 2 ISO vào kho ISO, tên giữ nguyên, nội dung khớp, quyền đọc chung, không còn .part", r is True and sorted(os.listdir(dest)) == ["CloudBlue-MayMau-win2012r2.iso", "CloudBlue-MayMau-win2016.iso"]
   and open(os.path.join(dest, os.path.basename(m2)), "rb").read() == open(m2, "rb").read() and stat.S_IMODE(os.stat(os.path.join(dest, os.path.basename(m1))).st_mode) == 0o644, os.listdir(dest) if os.path.isdir(dest) else None)
t0 = os.stat(os.path.join(dest, os.path.basename(m1))).st_mtime_ns
ck("chạy lại → file có sẵn (mã kiểm khớp) không chép lại", nap.once(conf, src=out, dest_dir=dest) is True and os.stat(os.path.join(dest, os.path.basename(m1))).st_mtime_ns == t0)
hong = os.path.join(tmp, "usb-hong.iso"); bb = bytearray(o_b); bb[hdr["files"][1]["off"] + 1000] ^= 0xFF; open(hong, "wb").write(bb)
os.remove(os.path.join(dest, os.path.basename(m2)))
nap.time.sleep = lambda s: None
ck("USB lỗi 1 byte trong 1 ISO → mã kiểm sai: KHÔNG nhận file đó (không để file hỏng trong kho), báo chưa đủ; file kia vẫn giữ",
   nap.once(conf, src=hong, dest_dir=dest) is False and os.listdir(dest) == ["CloudBlue-MayMau-win2012r2.iso"])
ck("cắm lại USB tốt → chép nốt", nap.once(conf, src=out, dest_dir=dest) is True and len(os.listdir(dest)) == 2)
cut = os.path.join(tmp, "usb-cut.iso"); open(cut, "wb").write(o_b[:hdr["files"][1]["off"] + 5000]); os.remove(os.path.join(dest, os.path.basename(m2)))
ck("USB bị ghi thiếu (cụt) → báo chưa đủ, không nhận file cụt", nap.once(conf, src=cut, dest_dir=dest) is False and os.listdir(dest) == ["CloudBlue-MayMau-win2012r2.iso"])
evil = bytearray(o_b); mh = json.loads(json.dumps(hdr)); mh["files"][0]["name"] = "../../etc/cron.d/x.iso"; mh["files"][1]["name"] = "virus.iso"
hb = pi.MAGIC + json.dumps(mh).encode() + b"\n"; evil[res["off"]:res["off"] + pi.HDR_LEN] = hb + b"\0" * (pi.HDR_LEN - len(hb)); open(hong, "wb").write(evil)
ck("đầu mục kho bị sửa tên file (đường dẫn lạ / tên không phải ISO máy mẫu) → bỏ qua các mục đó", nap.header(hong, conf["off"], conf["id"]) == [])
os.makedirs(os.environ["CBNAP_SYSBLOCK"]); [open(os.path.join(os.environ["CBNAP_SYSBLOCK"], n), "w").close() for n in ("sda", "nvme0n1", "loop0", "dm-1", "sr0", "zram0")]
ck("thiết bị dò: ổ đĩa / USB / ổ CD — bỏ loop, dm, zram", nap.raw_devices() == ["/dev/nvme0n1", "/dev/sda", "/dev/sr0"])
open(os.environ["CBNAP_CONF"], "w").write(json.dumps({"id": "x", "off": 0, "size": 1, "n": 0}))
ck("bản cài không kèm kho → dịch vụ ghi dấu xong rồi thôi (không chờ mãi)", nap.cmd_run() == 0 and os.path.exists(os.environ["CBNAP_DONE"]))

print("6. Tìm file trên máy · dòng lệnh")
d1 = os.path.join(tmp, "tim"); os.makedirs(os.path.join(d1, "con"))
def big(p):
    with open(p, "wb") as f: f.truncate(600 * 1024 * 1024)
for n in ("proxmox-ve_9.2-1.iso", "proxmox-ve_9.3-1.iso", "proxmox-ve_8.4-1.iso", "con/proxmox-ve_9.10-1.iso", "CloudBlue-MayMau-win2016.iso", "con/CloudBlue-MayMau-win2012r2.iso",
          "CloudBlue-MayMau-win2019.iso.part", "virtio-win-0.1.271.iso"): big(os.path.join(d1, n))
open(os.path.join(d1, "CloudBlue-MayMau-nho.iso"), "wb").write(b"x")
fp, fm = pi.find_inputs([d1, os.path.join(d1, "con")])
ck("tự tìm: ISO Proxmox bản MỚI NHẤT (9.10 > 9.3; bỏ bản 8) + mọi ISO máy mẫu đủ cỡ (bỏ .part, bỏ file tí hon, bỏ ISO khác)", fp.endswith("proxmox-ve_9.10-1.iso")
   and sorted(fm) == ["win2012r2", "win2016"], (fp, fm))
env = dict(os.environ, CB_PVE_PW_HASH=HASH)
outc = os.path.join(tmp, "cli.iso")
src99 = os.path.join(tmp, "proxmox-ve_9.9-1.iso"); mk_iso(src99, release="9.9")
rc = subprocess.run([sys.executable, os.path.join(ROOT, "vm", "pve_iso.py"), "--iso", src99, "--mau", m1 + "," + m2, "--out", outc, "--khong-hoi", "--ten", "vps9"], env=env, capture_output=True, text=True)
ic = pi.Iso(open(outc, "rb")) if os.path.exists(outc) else None
ck("dòng lệnh (không hỏi, mã băm qua biến môi trường): mã 0, ra ISO, answer.toml đúng tên máy, in bước tiếp + ghi chú bản chưa thử; chữ in ra toàn ASCII",
   rc.returncode == 0 and ic and b'fqdn = "vps9.lan"' in ic.read_file("answer.toml") and "XONG" in rc.stdout and "Rufus" in rc.stdout and "chua duoc CloudBlue cai thu" in rc.stdout and all(ord(c) < 128 for c in rc.stdout)
   and HASH not in rc.stdout, (rc.returncode, rc.stdout[-700:], rc.stderr[-300:]))
rc = subprocess.run([sys.executable, os.path.join(ROOT, "vm", "pve_iso.py"), "--iso", src99, "--out", outc + "2", "--khong-hoi", "--khong-mau"], env={k: v for k, v in os.environ.items() if k != "CB_PVE_PW_HASH"},
                    capture_output=True, text=True)
ck("không hỏi mà thiếu mã băm mật khẩu → dừng rõ, mã 1, không ra file", rc.returncode == 1 and "DUNG" in rc.stdout and not os.path.exists(outc + "2"), rc.stdout[-300:])
rc = subprocess.run([sys.executable, os.path.join(ROOT, "vm", "pve_iso.py"), "--iso", src, "--out", outc + "3", "--khong-hoi", "--khong-mau"], env=env, capture_output=True, text=True)
ck("ISO mang số bản đã thử (9.3-1) nhưng nội dung khác bản chính thức → dừng 'không khớp mã kiểm', không ra file", rc.returncode == 1 and "KHONG khop ma kiem" in rc.stdout
   and not os.path.exists(outc + "3") and not os.path.exists(outc + "3.part"), rc.stdout[-300:])

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d/%d đạt" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
