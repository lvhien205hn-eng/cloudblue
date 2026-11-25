#!/usr/bin/env python3
"""CloudBlue — NẠP kho ISO máy mẫu từ USB cài đặt (ISO CloudBlue-Proxmox) vào kho ISO của Proxmox. Chạy trên MÁY CHỦ PROXMOX (dịch vụ cloudblue-nap,
do script lần bật đầu của ISO cài). Kho nằm sau hệ tệp ISO trên USB, có đầu mục (tên, vị trí, cỡ, mã SHA-256 từng file):
  · USB ghi kiểu DD (Rufus "DD Image")  → đọc thẳng thiết bị (/dev/sdX, /dev/sr0)
  · ISO chép vào USB dạng file (Ventoy …) → gắn tạm phân vùng (chỉ đọc), đọc trong file .iso đúng cỡ
Chép xong kiểm SHA-256 từng file; sai thì chép lại. Rút USB sớm: cắm lại lúc nào cũng được, dịch vụ tự chép tiếp.
   cb_nap.py run            vòng chờ (dịch vụ)        cb_nap.py once        1 lượt (0 = đủ hết)
   cb_nap.py --src /dev/sdb  chép từ đúng thiết bị / file này        cb_nap.py status"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

NAP_VER = "26.11a"
MAGIC = b"CBKHO1\n"
HDR_LEN = 16384
CONF_F = os.environ.get("CBNAP_CONF") or "/etc/cloudblue/nap.json"
DEST = os.environ.get("CBNAP_DEST") or "/var/lib/vz/template/iso"
DONE_F = os.environ.get("CBNAP_DONE") or "/var/lib/cloudblue/nap-xong.json"
MNT = os.environ.get("CBNAP_MNT") or "/run/cloudblue-nap"
SYS_BLOCK = os.environ.get("CBNAP_SYSBLOCK") or "/sys/block"
RX_MAU = re.compile(r"^CloudBlue-MayMau-[a-z0-9]{3,24}\.iso$")
RX_SHA = re.compile(r"^[0-9a-f]{64}$")
FS_OK = {"exfat": "exfat", "vfat": "vfat", "ntfs": "ntfs3", "ext4": "ext4", "ext3": "ext3", "ext2": "ext2"}


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_conf():
    try:
        c = json.load(open(CONF_F))
    except (OSError, ValueError):
        return None
    if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("off"), int) or not isinstance(c.get("size"), int):
        return None
    return c


def header(path, off, want_id):
    """Đầu mục kho ở vị trí off của thiết bị / file → danh sách file hợp lệ; không phải kho của bản cài này → None"""
    try:
        with open(path, "rb") as f:
            f.seek(off)
            hdr = f.read(HDR_LEN)
    except (OSError, ValueError):
        return None
    if not hdr.startswith(MAGIC) or b"\n" not in hdr[len(MAGIC):]:
        return None
    try:
        m = json.loads(hdr[len(MAGIC):hdr.index(b"\n", len(MAGIC))].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(m, dict) or m.get("id") != want_id or not isinstance(m.get("files"), list):
        return None
    files = []
    for x in m["files"]:
        if (isinstance(x, dict) and isinstance(x.get("name"), str) and RX_MAU.match(x["name"]) and isinstance(x.get("off"), int) and isinstance(x.get("size"), int)
                and x["off"] >= off + HDR_LEN and 0 < x["size"] < 64 * 2**30 and isinstance(x.get("sha256"), str) and RX_SHA.match(x["sha256"])):
            files.append({"name": x["name"], "off": x["off"], "size": x["size"], "sha256": x["sha256"]})
    return files


def raw_devices():
    try:
        names = sorted(os.listdir(SYS_BLOCK))
    except OSError:
        return []
    return ["/dev/" + n for n in names if not re.match(r"^(loop|ram|zram|dm-|md|nbd|fd)", n)]


def sha_file(path, size):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = size
        while left > 0:
            b = f.read(min(4 * 1024 * 1024, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def copy_one(src, it, dest_dir):
    """1 file từ kho → kho ISO. → 'có sẵn' | 'đã chép'; lỗi → raise"""
    dst = os.path.join(dest_dir, it["name"])
    if os.path.isfile(dst) and os.path.getsize(dst) == it["size"] and sha_file(dst, it["size"]) == it["sha256"]:
        return "có sẵn"
    free = shutil.disk_usage(dest_dir).free
    if free < it["size"] + 2**30:
        raise IOError("kho ISO không đủ chỗ: cần %.1f GB, còn %.1f GB" % (it["size"] / 2**30, free / 2**30))
    part = dst + ".part"
    h = hashlib.sha256()
    t0 = time.time()
    try:
        with open(src, "rb") as f, open(part, "wb") as o:
            f.seek(it["off"])
            left = it["size"]
            nxt = 25
            while left > 0:
                b = f.read(min(4 * 1024 * 1024, left))
                if not b:
                    raise IOError("đọc USB thiếu dữ liệu (còn %d byte)" % left)
                o.write(b)
                h.update(b)
                left -= len(b)
                pct = (it["size"] - left) * 100 // it["size"]
                if pct >= nxt and it["size"] > 256 * 2**20:
                    log("   %s: %d%%" % (it["name"], pct))
                    nxt += 25
            o.flush()
            os.fsync(o.fileno())
        if h.hexdigest() != it["sha256"]:
            raise IOError("mã kiểm SHA-256 không khớp (USB lỗi / chép lỗi)")
        os.chmod(part, 0o644)
        os.replace(part, dst)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    log("   %s: đã chép (%.2f GB, %d giây), mã kiểm khớp" % (it["name"], it["size"] / 2**30, time.time() - t0))
    return "đã chép"


def import_all(src, files, dest_dir):
    """→ True nếu mọi file đã nằm trong kho ISO (mã kiểm khớp)"""
    os.makedirs(dest_dir, exist_ok=True)
    ok = True
    for it in files:
        for lan in (1, 2, 3):
            try:
                copy_one(src, it, dest_dir)
                break
            except (OSError, IOError) as e:
                log("   %s: lỗi lần %d — %s" % (it["name"], lan, e))
                if lan == 3:
                    ok = False
                time.sleep(2)
    return ok


def lsblk():
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,TYPE,FSTYPE,MOUNTPOINT,PATH"], capture_output=True, text=True, timeout=30).stdout
        return json.loads(out).get("blockdevices") or []
    except Exception:
        return []


def flat(node):
    yield node
    for c in node.get("children") or []:
        for x in flat(c):
            yield x


def fs_parts():
    """Phân vùng có hệ tệp đọc được trên các ổ KHÔNG phải ổ hệ thống (ổ hệ thống = có phần đang gắn / LVM / ZFS / RAID) → [(thiết bị, kiểu mount)]"""
    res = []
    for disk in lsblk():
        nodes = list(flat(disk))
        if disk.get("type") not in ("disk",) or any(n.get("mountpoint") or (n.get("fstype") or "") in ("LVM2_member", "zfs_member", "linux_raid_member", "swap") for n in nodes):
            continue
        for n in nodes:
            if (n.get("fstype") or "") in FS_OK and n.get("path"):
                res.append((n["path"], FS_OK[n["fstype"]]))
    return res


def find_in_fs(conf):
    """ISO CloudBlue-Proxmox nằm dạng FILE trên 1 phân vùng (Ventoy …) → generator (đường dẫn file); tự gắn / gỡ."""
    mp = os.path.join(MNT, "m")
    for dev, fst in fs_parts():
        os.makedirs(mp, exist_ok=True)
        if subprocess.run(["mount", "-t", fst, "-o", "ro,nosuid,nodev,noexec", dev, mp], capture_output=True, timeout=60).returncode != 0:
            continue
        try:
            for base, dirs, names in os.walk(mp):
                if base[len(mp):].count(os.sep) >= 2:
                    dirs[:] = []
                for nm in names:
                    p = os.path.join(base, nm)
                    try:
                        if nm.lower().endswith(".iso") and os.path.getsize(p) == conf["size"] and header(p, conf["off"], conf["id"]) is not None:
                            yield p
                    except OSError:
                        continue
        finally:
            subprocess.run(["umount", mp], capture_output=True, timeout=60)


def once(conf, src=None, dest_dir=None):
    """1 lượt: → True (đủ hết) | False (thấy kho nhưng chép lỗi) | None (chưa thấy USB / file ISO cài đặt)"""
    dest_dir = dest_dir or DEST
    for dev in ([src] if src else raw_devices()):
        files = header(dev, conf["off"], conf["id"])
        if files is not None:
            log("thấy kho ISO máy mẫu trên %s (%d file)" % (dev, len(files)))
            return import_all(dev, files, dest_dir)
    if not src:
        for p in find_in_fs(conf):
            files = header(p, conf["off"], conf["id"])
            log("thấy kho ISO máy mẫu trong file %s (%d file)" % (p, len(files or [])))
            return import_all(p, files or [], dest_dir)
    return None


def mark_done(note):
    try:
        os.makedirs(os.path.dirname(DONE_F), exist_ok=True)
        json.dump({"t": int(time.time()), "note": note, "ver": NAP_VER}, open(DONE_F, "w"))
    except OSError as e:
        log("không ghi được dấu xong: %s" % e)


def cmd_run():
    conf = load_conf()
    if os.path.exists(DONE_F):
        return 0
    if not conf or not conf.get("off") or not conf.get("n"):
        log("bản cài này không kèm kho ISO máy mẫu — không có gì để nạp")
        mark_done("không có kho")
        return 0
    log("cb_nap %s: chờ USB cài đặt CloudBlue-Proxmox để chép %d ISO máy mẫu vào %s" % (NAP_VER, conf["n"], DEST))
    n = bad = 0
    while True:
        try:
            r = once(conf)
        except Exception as e:
            log("lỗi vòng: %s" % e)
            r = False
        if r is True:
            log("XONG: đã nạp đủ ISO máy mẫu vào kho ISO. cbhost sẽ tự dựng máy mẫu. Có thể rút USB.")
            mark_done("đủ")
            return 0
        if r is None and n % 40 == 0:
            log("chưa thấy USB cài đặt (đã rút?) — cắm lại USB CloudBlue-Proxmox vào máy chủ, dịch vụ tự chép (đang chờ)")
        if r is False:
            bad += 1
            log("chép chưa đủ (lần %d) — thử lại sau" % bad)
        n += 1
        time.sleep(60 if r is False and bad > 3 else 15)


def cmd_status():
    conf = load_conf()
    print("cb_nap %s · kho ISO: %s" % (NAP_VER, DEST))
    if os.path.exists(DONE_F):
        print("đã nạp xong: %s" % open(DONE_F).read()[:200])
    elif not conf:
        print("không có cấu hình %s" % CONF_F)
    else:
        print("đang chờ USB cài đặt (kho %s, %d file) — xem: journalctl -u cloudblue-nap -n 30" % (conf["id"], conf.get("n") or 0))
    return 0


def main(argv):
    if argv[:1] == ["--src"] and len(argv) >= 2:
        conf = load_conf()
        if not conf:
            print("không có cấu hình %s" % CONF_F)
            return 2
        r = once(conf, src=argv[1])
        if r is True:
            mark_done("đủ (chép tay từ %s)" % argv[1])
        print({True: "đủ", False: "chép lỗi", None: "không phải USB / file ISO cài đặt của máy này"}[r])
        return 0 if r else 1
    cmd = argv[0] if argv else "run"
    if cmd == "run":
        return cmd_run()
    if cmd == "once":
        conf = load_conf()
        r = once(conf) if conf and conf.get("off") else True
        if r is True:
            mark_done("đủ")
        return 0 if r else 1
    if cmd == "status":
        return cmd_status()
    if cmd in ("-v", "--version", "version"):
        print(NAP_VER)
        return 0
    print("Lệnh: run | once | status | --src <thiết bị / file> | version")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
