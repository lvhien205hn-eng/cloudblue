# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbrec.py — PHÂN VÙNG CỨU HỘ CloudBlue (CBRECOVERY): tìm, chép bộ cài vào, ghi LỆNH cài lại, đặt máy khởi động 1 lần vào bộ cài.
#  Dùng trong Windows đang chạy (agent pcagent.py, CAI-DAT.cmd → cb_stage.py) và trong WinPE (cb_pe.py dùng phần chép).
#
#  Trên phân vùng cứu hộ:
#    \cb\recovery.tag            dấu nhận biết
#    \cb\cb.json                 cấu hình (danh sách bản Windows) — KHÔNG có bí mật
#    \cb\boot\boot.wim, boot.sdi môi trường cài đặt (đã chèn bộ cài CloudBlue)
#    \cb\images\<bản>.wim|esd    các bản Windows
#    \cb\linux\                 22.11c · CachyOS: cachyos.iso + grubx64.efi + grub.cfg + cb-install.sh (+ job.cfg / installed.json lúc cài)
#    \cb\lib, pe, os, agent, py  phần mềm CloudBlue + Python nhúng
#    \cb\job.json                LỆNH đang chờ (agent ghi → bộ cài đọc)      \cb\job-result.json  kết quả (bộ cài ghi → agent báo web)
#    \cb\identity.json           tên máy / mã số máy (không có mã bí mật)
# =====================================================================================================
import cbcore as C

REC_VER = "22.11f"
SUBDIRS = ("lib", "pe", "os", "agent", "py", "drivers", "linux")   # "drivers": driver chủ shop bỏ thêm — cài lại từ xa cũng nạp · "linux": CachyOS (22.11c)


def tree_bytes(sysx, root, depth=12):
    """Tổng dung lượng 1 thư mục (để tính cỡ phân vùng cứu hộ). Không có thư mục → 0."""
    if depth <= 0 or not sysx.isdir(root): return 0
    total = 0
    for n in sysx.listdir(root)[:20000]:
        p = root.rstrip("\\") + "\\" + n
        total += tree_bytes(sysx, p, depth - 1) if sysx.isdir(p) else sysx.size(p)
    return total


def extra_bytes(sysx, src_root):
    """Phần chủ shop bỏ thêm vào bộ cài mà phân vùng cứu hộ phải chứa: cb\\drivers + cb\\os\\firstboot.d (gói cài VGA .exe có thể nặng cả GB)."""
    return tree_bytes(sysx, src_root + "cb\\drivers") + tree_bytes(sysx, src_root + "cb\\os\\firstboot.d")


def find_recovery(sysx):
    """Volume cứu hộ (có \\cb\\recovery.tag) trên ổ cứng gắn trong. Không có → None."""
    for v in sysx.volumes():
        if v.kind != 3 or v.disk is None: continue
        try:
            if sysx.exists(v.root + "cb\\recovery.tag"): return v
        except OSError:
            pass
    return None


def system_volume(sysx, letter="C"):
    return next((v for v in sysx.volumes() if letter in v.letters), None)


def status(sysx):
    """Tóm tắt cho web: có phân vùng cứu hộ không, đổi được sang bản Windows nào."""
    v = find_recovery(sysx)
    if not v: return {"ok": False, "images": []}
    cfg = C.load_json(sysx, v.root + "cb\\cb.json") or {}
    lin_ok = None

    def linux_ok():                                             # 22.11f · CachyOS chỉ cài được trên máy UEFI đang TẮT Secure Boot
        try: return sysx.firmware() == "uefi" and not C.secure_boot_on(sysx)
        except Exception: return False
    imgs = []
    for im in cfg.get("images") or []:
        if not sysx.exists(v.root + im["file"]): continue
        if C.is_linux(im):                                      # CachyOS: thiếu GRUB / kịch bản cài / agent / điều khiển từ xa → không cho chọn
            if lin_ok is None: lin_ok = linux_ok()
            if not lin_ok or not all(sysx.exists(v.root + rel) for rel in C.LINUX_FILES): continue
        imgs.append(im["id"])
    ok = bool(imgs) and sysx.exists(v.root + "cb\\boot\\boot.wim") and sysx.exists(v.root + "cb\\boot\\boot.sdi")
    return {"ok": ok, "images": imgs, "ver": cfg.get("ver") or ""}


def populate(sysx, src_root, cfg, rec_root, log=None, progress=None):
    """Chép bộ cài từ USB / ISO (src_root) sang phân vùng cứu hộ (rec_root, có dấu \\ ở cuối). Trả cấu hình đã ghi."""
    log = log or (lambda *a: None)
    base = rec_root + "cb"
    for d in ("boot", "images", "logs"): sysx.makedirs(base + "\\" + d)
    for rel, to in (("sources\\boot.wim", "boot\\boot.wim"), ("boot\\boot.sdi", "boot\\boot.sdi")):
        if not sysx.dry and not sysx.exists(src_root + rel): raise C.Stop("Bo cai thieu file %s" % rel)
        sysx.copy_file(src_root + rel, base + "\\" + to)
    rcfg = C.recovery_cfg(cfg)
    for im, rim in zip(cfg["images"], rcfg["images"]):
        log("  ban %s (%.1f GB)..." % (im["id"], int(im.get("bytes") or 0) / 1e9))
        if not sysx.dry and not sysx.exists(src_root + im["file"]): raise C.Stop("Bo cai thieu file %s" % im["file"])
        if C.is_linux(im) and im["file"].lower().replace("/", "\\").startswith("cb\\linux\\"): continue    # ISO CachyOS nằm trong cb\linux → chép cùng thư mục đó (1 lần)
        sysx.copy_file(src_root + im["file"], rec_root + rim["file"], show=progress)
    for sub in SUBDIRS:
        if sysx.dry or sysx.isdir(src_root + "cb\\" + sub): sysx.copy_tree(src_root + "cb\\" + sub, base + "\\" + sub)
    C.save_json(sysx, base + "\\cb.json", rcfg)
    sysx.write_text(base + "\\recovery.tag", "CloudBlue PC recovery %s\r\n" % REC_VER)
    return rcfg


def arm_boot(sysx, rec_vol):
    """Tạo (lại) mục khởi động cài lại trong kho BCD của Windows đang chạy + đặt khởi động 1 LẦN vào đó."""
    fw = sysx.firmware()
    dev, letter = sysx.nt_device(rec_vol.path), None
    if not dev:                                                # không lấy được tên thiết bị → gán chữ ổ tạm
        letter = C.pick_letters(sysx.used_letters())[2]
        if not sysx.mount(rec_vol.path, letter): raise C.Stop("Khong gan duoc chu o tam cho phan vung cuu ho.")
        dev = letter + ":"
    try:
        C.run_cmds(sysx, C.bcd_pe_cmds(fw, dev), "Tao muc khoi dong cai lai")
        rc, out = sysx.run(["bcdedit", "/bootsequence", C.PE_GUID], timeout=60)
        if rc != 0: raise C.Stop("Dat khoi dong 1 lan vao bo cai lai loi: %s" % (out or "").strip()[-200:])
    finally:
        if letter: sysx.unmount(letter)


def disarm_boot(sysx):
    sysx.run(["bcdedit", "/deletevalue", "{bootmgr}", "bootsequence"], timeout=60)


def stage_job(sysx, job, hostname, now):
    """Ghi lệnh cài lại lên phân vùng cứu hộ + đặt khởi động 1 lần vào bộ cài. KHÔNG tự khởi động lại.
       job = {"id", "os", "wipe": all|disk|system, "ticket"?, "enroll_key"?, "hw"?}. Trả thông tin bản Windows sẽ cài."""
    rec = find_recovery(sysx)
    if not rec: raise C.Stop("May nay chua co phan vung cuu ho CloudBlue - can cai bang USB / ISO CloudBlue 1 lan.")
    cfg = C.load_json(sysx, rec.root + "cb\\cb.json") or {}
    image = C.find_image(cfg, job.get("os"))
    need = [image["file"], "cb\\boot\\boot.wim", "cb\\boot\\boot.sdi"] + (list(C.LINUX_FILES) if C.is_linux(image) else [])
    for rel in need:
        if not sysx.exists(rec.root + rel): raise C.Stop("Phan vung cuu ho thieu file %s" % rel)
    if C.is_linux(image):                                       # 22.11c · CachyOS: báo NGAY những máy không cài được (đỡ khởi động lại vào bộ cài rồi mới biết)
        if sysx.firmware() != "uefi": raise C.Stop("CachyOS chi cai duoc tren may khoi dong kieu UEFI (may nay dang khoi dong kieu BIOS).")
        try: sb = C.secure_boot_on(sysx)
        except Exception: sb = False
        if sb: raise C.Stop("May dang BAT Secure Boot - CachyOS can TAT Secure Boot trong BIOS truoc.")
    if job.get("wipe") not in ("all", "disk", "system"): raise C.Stop("Kieu xoa '%s' khong hop le." % job.get("wipe"))
    win = system_volume(sysx)
    if win is None or win.disk is None: raise C.Stop("Khong xac dinh duoc o C: cua Windows dang chay.")
    if win.disk != rec.disk: raise C.Stop("Windows (o %s) va phan vung cuu ho (o %s) khong nam cung 1 o cung." % (win.disk, rec.disk))
    j = {k: v for k, v in job.items() if k in ("id", "os", "wipe", "ticket", "enroll_key", "hw", "tries")}
    j.update(win={"offset": win.offset, "size": win.size}, name=hostname, state="queued", attempts=0, ts=int(now))
    C.save_json(sysx, rec.root + "cb\\job.json", j)
    sysx.remove(rec.root + "cb\\job-result.json")
    arm_boot(sysx, rec)
    return image


def pending_job(sysx):
    rec = find_recovery(sysx)
    return (C.load_json(sysx, rec.root + "cb\\job.json") if rec else None)


def drop_job(sysx):
    rec = find_recovery(sysx)
    if rec: sysx.remove(rec.root + "cb\\job.json")
    disarm_boot(sysx)


def take_result(sysx, clear=False):
    """Kết quả lệnh cài lại do bộ cài ghi (None nếu không có). clear=True: xoá sau khi đã báo về web."""
    rec = find_recovery(sysx)
    if not rec: return None
    p = rec.root + "cb\\job-result.json"
    if clear: sysx.remove(p); return None
    return C.load_json(sysx, p)


def lock_volume(sysx, root):
    """Khoá gốc phân vùng cứu hộ: chỉ SYSTEM + Administrators (xem cbcore.acl_vol_cmds). Trả số lệnh báo lỗi (0 = xong)."""
    bad = 0
    for argv in C.acl_vol_cmds(root):
        try: rc, out = sysx.run(argv, timeout=900)
        except Exception: rc = 127
        if rc != 0: bad += 1
    return bad


def save_identity(sysx, ident):
    """Ghi tên máy / mã số máy lên phân vùng cứu hộ (KHÔNG ghi mã bí mật) để cài lại vẫn giữ đúng máy."""
    rec = find_recovery(sysx)
    if not rec: return False
    C.save_json(sysx, rec.root + "cb\\identity.json", {k: ident[k] for k in ("id", "hw", "name") if ident.get(k)})
    return True


# ====================================================================================== tạo phân vùng cứu hộ từ Windows đang chạy
def create_recovery(sysx, src_root, cfg, log=None, progress=None):
    """Máy đang chạy Windows thường (chưa có phân vùng cứu hộ): thu nhỏ ổ C:, tạo CBRECOVERY, chép bộ cài vào. Trả volume cứu hộ."""
    log = log or (lambda *a: None)
    fw = sysx.firmware()
    win = system_volume(sysx)
    if win is None or win.disk is None: raise C.Stop("Khong xac dinh duoc o C:.")
    disk = next((d for d in sysx.disks() if d.index == win.disk), None)
    if disk is None: raise C.Stop("Khong doc duoc o cung chua C:.")
    if (fw == "uefi") != (disk.style == "gpt"):
        raise C.Stop("May khoi dong kieu %s nhung o C: la %s - khong chuyen tai cho duoc, hay cai bang USB." % (fw.upper(), disk.style.upper()))
    if disk.style == "mbr" and len(disk.parts) >= 4: raise C.Stop("O cung kieu MBR da du 4 phan vung - hay cai bang USB.")
    need = C.recovery_bytes(cfg, sysx.size(src_root + "sources\\boot.wim") or 600 * C.MB, extra_bytes(sysx, src_root))
    free = sysx.free_bytes(win.root)
    if free < need + 12 * C.GB:
        raise C.Stop("O C: chi con trong %.0f GB - can it nhat %.0f GB de tao phan vung cuu ho. Don bot hoac cai bang USB." % (free / 1e9, (need + 12 * C.GB) / 1e9))
    R = C.pick_letters(sysx.used_letters())[2]
    mb = need // C.MB
    log("Thu nho o C: %d MB va tao phan vung cuu ho..." % mb)
    rc, out = sysx.diskpart(["select volume %s" % win.letters[0], "shrink desired=%d minimum=%d" % (mb, mb),
                             "select disk %d" % disk.index, "create partition primary size=%d" % (mb - 2),
                             'format quick fs=ntfs label="%s"' % C.REC_LABEL, "assign letter=%s" % R])
    if rc != 0: raise C.Stop("Khong thu nho / tao duoc phan vung (diskpart ma %s). Hay cai bang USB.\n%s" % (rc, (out or "").strip()[-300:]))
    rv = next((v for v in sysx.volumes() if R in v.letters), None)
    if rv is None: raise C.Stop("Tao xong nhung khong thay o %s:" % R)
    log("Chep bo cai sang phan vung cuu ho (%s:)..." % R)
    populate(sysx, src_root, cfg, R + ":\\", log, progress)
    lock_volume(sysx, R + ":\\")
    part = next((p for d in sysx.disks() if d.index == disk.index for p in d.parts if p.offset == rv.offset), None)
    if part is None: raise C.Stop("Khong thay phan vung cuu ho vua tao trong bang phan vung.")
    rc, out = sysx.diskpart(C.plan_hide_recovery(disk.index, part.number, fw, R))
    if rc != 0: log("  (chua an duoc phan vung cuu ho - khong sao, bo cai se an lai)")
    return next((v for v in sysx.volumes() if v.disk == disk.index and v.offset == rv.offset), rv)
