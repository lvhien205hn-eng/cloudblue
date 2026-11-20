# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_pe.py — BỘ CÀI TỰ ĐỘNG máy PC CloudBlue, chạy trong môi trường cài đặt Windows (WinPE) TRƯỚC bộ cài gốc.
#
#  Được gọi bởi \cb\pe\start.cmd (winpeshl.ini trong boot.wim, hoặc autounattend.xml nếu boot.wim chưa được chèn).
#  Hai nguồn:
#    · USB / ISO cài đặt  (\cb\media.tag)      → CÀI MỚI: đếm ngược, XOÁ SẠCH ổ đích, chia ổ, bung Windows, tạo phân vùng cứu hộ
#    · phân vùng cứu hộ   (\cb\recovery.tag)   → chỉ làm khi có LỆNH (\cb\job.json do agent ghi): cài lại / đổi Windows / dọn máy
#                                                không có lệnh → không xoá gì, khởi động lại vào Windows
#  Mã thoát:  0 = đã cài xong (khởi động lại) · 10 = không có gì để làm (khởi động lại) · 3 = chuyển sang bộ cài Windows gốc
#
#  Chữ trên màn hình WinPE viết KHÔNG DẤU (phông chữ WinPE không vẽ được tiếng Việt có dấu).
#  Chạy thử trên Windows thường, KHÔNG đổi gì:   python cb_pe.py --dry-run [thư mục bộ cài]
# =====================================================================================================
import json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "..", "lib"), HERE):
    _p = os.path.abspath(_p)
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import cbrec                                                     # noqa: E402
from cbsys import Vol, WinSys                                    # noqa: E402

PE_VER = "20.11d"
RC_OK, RC_SETUP, RC_REBOOT = 0, 3, 10
LINE = "=" * 72


class Src:
    """1 nguồn bộ cài: vol (cbsys.Vol) + root ('E:\\' hoặc đường Volume{GUID})."""
    def __init__(self, vol, kind):
        self.vol, self.root, self.kind = vol, vol.root, kind

    def p(self, rel): return self.root + rel


class Installer:
    def __init__(self, sysx, log_path=None):
        self.s = sysx
        self.lines = []
        self.log_path = log_path
        self.t0 = sysx.now()

    # ------------------------------------------------------------------ in + nhật ký
    def log(self, msg=""):
        ln = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        self.lines.append(ln)
        self.s.log(msg)
        if self.log_path and not self.s.dry:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f: f.write(ln + "\n")
            except OSError: pass

    def banner(self, title):
        for x in ("", LINE, "  CloudBlue PC %s  -  %s" % (PE_VER, title), LINE): self.log(x)

    # ------------------------------------------------------------------ tìm nguồn
    def sources(self):
        media, recs = [], []
        for v in self.s.volumes():
            if v.kind not in (2, 3, 5) or (not v.fs and not v.letters): continue
            root = v.root
            try:
                if self.s.exists(root + "cb\\media.tag"): media.append(Src(v, "media"))
                elif self.s.exists(root + "cb\\recovery.tag"): recs.append(Src(v, "recovery"))
            except OSError:
                pass
        return media, recs

    def wait_sources(self, secs=40):
        """USB có thể lên chậm vài giây sau khi WinPE chạy → chờ; quá 4 giây chưa thấy gì thì gọi wpeinit 1 lần (nạp thiết bị)."""
        t, inited = self.s.now(), False
        while True:
            media, recs = self.sources()
            if media or recs: return media, recs
            el = self.s.now() - t
            if el > secs: return media, recs
            if el > 4 and not inited:
                inited = True
                self.log("Chua thay bo cai - nap thiet bi (wpeinit)...")
                self.s.run(["wpeinit"], timeout=180, change=False)
            self.s.sleep(1.5)

    # ------------------------------------------------------------------ tiện ích
    def disk_of(self, vol, disks):
        return next((d for d in disks if vol.disk is not None and d.index == vol.disk), None)

    def old_system_disks(self, vols):
        out = set()
        for v in vols:
            if v.disk is None or v.kind != 3: continue
            try:
                if self.s.exists(v.root + "Windows\\System32\\config\\SYSTEM") or self.s.exists(v.root + "cb\\recovery.tag"): out.add(v.disk)
            except OSError: pass
        return out

    def letters_free_after(self, vols, wipe_disks):
        """Chữ ổ đang dùng, KHÔNG tính các ổ sắp bị xoá sạch (chữ của chúng sẽ được trả lại)."""
        used = set(self.s.used_letters())
        for v in vols:
            if v.disk in wipe_disks:
                for c in v.letters: used.discard(c)
        return used

    def must(self, rc_out, what):
        rc, out = rc_out
        if rc != 0: raise C.Stop("%s loi (ma %s).\n%s" % (what, rc, (out or "").strip()[-600:]))
        return out

    def find_vol(self, disk_index, offset):
        """Volume nằm đúng trên phân vùng bắt đầu ở `offset` của ổ `disk_index` (None nếu chưa thấy)."""
        for v in self.s.volumes():
            if v.disk == disk_index and v.offset == offset: return v
        return None

    def part_at(self, disk_index, offset):
        """Phân vùng (số HIỆN TẠI) bắt đầu ở `offset` — số phân vùng đổi sau khi xoá / tạo nên luôn tìm lại theo vị trí."""
        d = next((x for x in self.s.disks() if x.index == disk_index), None)
        p = next((x for x in (d.parts if d else []) if x.offset == offset), None)
        if p is None: raise C.Stop("Khong thay phan vung o vi tri %d MB tren o %s." % (offset // C.MB, disk_index))
        return p

    def ensure_letter(self, disk_index, offset, letter):
        """Gán chữ ổ cho phân vùng bắt đầu ở `offset` (kể cả phân vùng ẩn) rồi kiểm lại là dùng được."""
        v = self.find_vol(disk_index, offset)
        if v and letter in v.letters: return
        if v and v.letters:
            for c in v.letters: self.s.unmount(c)
        ok = bool(v) and self.s.mount(v.path, letter)
        if not ok:
            p = self.part_at(disk_index, offset)
            self.must(self.s.diskpart(["select disk %d" % disk_index, "select partition %d" % p.number, "assign letter=%s" % letter]),
                      "Gan chu o %s:" % letter)
        if not self.s.dry and not self.s.isdir(letter + ":\\"): raise C.Stop("Khong gan duoc chu o %s:" % letter)

    def hide_recovery(self, disk_index, offset, fw, letter, strict=True):
        p = self.part_at(disk_index, offset)
        rc_out = self.s.diskpart(C.plan_hide_recovery(disk_index, p.number, fw, letter))
        if strict: self.must(rc_out, "An phan vung cuu ho")

    # ------------------------------------------------------------------ các bước cài
    def apply_image(self, src, image, W):
        f = src.p(image["file"])
        if not self.s.dry and not self.s.exists(f): raise C.Stop("Thieu file ban Windows: %s" % f)
        self.log("Bung %s (%s, ban so %s) vao %s:\\ ... (5-20 phut)" % (image.get("name") or image["id"], image["id"], image.get("index", 1), W))
        argv = ["dism", "/English", "/Apply-Image", "/ImageFile:" + f, "/Index:%s" % image.get("index", 1), "/ApplyDir:%s:\\" % W]
        if f.lower().endswith(".swm"): argv.append("/SWMFile:" + f[:-4] + "*.swm")
        rc, _ = self.s.run(argv, timeout=4 * 3600, show=True)
        if rc != 0: raise C.Stop("Bung Windows loi (dism ma %s). Xem X:\\Windows\\Logs\\DISM\\dism.log" % rc)
        if not self.s.dry and not self.s.exists(W + ":\\Windows\\System32\\config\\SYSTEM"):
            raise C.Stop("Bung xong nhung khong thay Windows tren %s:\\" % W)

    def make_boot(self, W, S, fw, fresh_store):
        """Ghi file khởi động cho Windows mới. fresh_store=True: xoá kho BCD cũ trước (cài lại) để không còn mục chết."""
        if fresh_store and not self.s.dry:
            store = C.bcd_store(fw, S)
            for ext in ("", ".LOG", ".LOG1", ".LOG2"):
                self.s.remove(store + ext)
        exe = W + ":\\Windows\\System32\\bcdboot.exe"
        if not self.s.dry and not self.s.exists(exe): exe = "bcdboot"
        argv = [exe, W + ":\\Windows", "/s", S + ":", "/f", "UEFI" if fw == "uefi" else "BIOS"]
        rc, out = self.s.run(argv, timeout=300)
        if rc != 0 and exe != "bcdboot":
            rc, out = self.s.run(["bcdboot"] + argv[1:], timeout=300)
        if rc != 0: raise C.Stop("Ghi file khoi dong loi (bcdboot ma %s): %s" % (rc, (out or "").strip()[-300:]))
        if fw != "uefi":
            bs = next((p for p in (W + ":\\Windows\\System32\\bootsect.exe", "X:\\Windows\\System32\\bootsect.exe") if self.s.exists(p)), None)
            if bs: self.s.run([bs, "/nt60", S + ":", "/mbr", "/force"], timeout=120)

    def populate_recovery(self, src, cfg, R):
        """Chép bộ cài sang phân vùng cứu hộ để lần sau cài lại / đổi Windows không cần USB."""
        self.log("Chep bo cai sang phan vung cuu ho (%s:) ..." % R)
        return cbrec.populate(self.s, src.root, cfg, R + ":\\", self.log, self.progress)

    def progress(self, done, total, speed):
        self.s.log("      %3d%%  %.1f / %.1f GB  (%.0f MB/giay)" % (done * 100 // max(1, total), done / 1e9, total / 1e9, speed / 1e6))

    def inject(self, src, W, cfg, image, name, seed):
        """Đưa phần mềm CloudBlue + file trả lời vào Windows vừa bung."""
        base = W + ":\\CloudBluePC"
        self.log("Dua phan mem CloudBlue vao Windows moi ...")
        def other_os(rel):                                   # os\firstboot.d\<tên bản Windows KHÁC> (vd gói VGA 700MB của bản 1511 khi đang cài 22H2) → không chép vào ổ C:
            p = rel.lower().split("\\")
            return len(p) == 2 and p[0] == "firstboot.d" and not C.folder_applies(p[1], (image or {}).get("id"))
        for sub in ("os", "agent", "lib", "py"):
            if self.s.dry or self.s.isdir(src.p("cb\\" + sub)): self.s.copy_tree(src.p("cb\\" + sub), base + "\\" + sub, other_os if sub == "os" else None)
        self.s.makedirs(base + "\\logs")
        C.save_json(self.s, base + "\\cb.json", C.recovery_cfg(cfg))
        C.save_json(self.s, base + "\\seed.json", seed)
        tpl = self.s.read_text(src.p("cb\\os\\unattend.tpl.xml"))
        # Bản Windows tuỳ biến hay kèm sẵn file trả lời riêng: Windows ưu tiên Panther\Unattend\unattend.xml rồi mới tới Panther\unattend.xml
        # → ghi file của CloudBlue vào CẢ HAI chỗ (không thì phần cài agent không chạy). Khoá sản phẩm có sẵn trong file cũ được giữ lại.
        pan = W + ":\\Windows\\Panther"
        own_key = ""
        for old in (pan + "\\Unattend\\unattend.xml", pan + "\\unattend.xml"):
            try:
                if not own_key and not self.s.dry and self.s.exists(old): own_key = C.find_unattend_key(self.s.read_text(old))
            except Exception: pass
        if own_key and C.key_mode(cfg) != "off": self.log("  ban Windows nay co san khoa san pham trong file tra loi cu -> giu lai")
        ua = C.make_unattend(tpl, image, cfg, name, own_key)
        self.s.write_text(pan + "\\unattend.xml", ua)
        self.s.write_text(pan + "\\Unattend\\unattend.xml", ua)
        self.setup_complete(W)
        self.add_drivers(src.p("cb\\drivers"), W, image)
        self.lock_acl(C.acl_lock_cmds(base), "khoa quyen thu muc CloudBluePC")

    def lock_acl(self, cmds, what):
        """Khoá quyền bằng icacls (chỉ SYSTEM + Administrators; xem cbcore.acl_lock_cmds / acl_vol_cmds). Lệnh nào lỗi thì ghi nhật ký rồi đi tiếp:
           Windows mới sẽ tự khoá lại lần nữa lúc khởi động (cb_provision.lockdown)."""
        bad = 0
        for argv in cmds:
            try: rc, out = self.s.run(argv, timeout=900)
            except Exception as e: rc, out = 127, str(e)
            if rc != 0: bad += 1
        self.log("  %s: %s" % (what, "xong" if not bad else "%d / %d lenh bao loi (bo qua - Windows moi se tu khoa lai)" % (bad, len(cmds))))

    def setup_complete(self, W):
        """Lưới an toàn thứ 2: Windows\\Setup\\Scripts\\SetupComplete.cmd (Windows tự chạy sau khi cài xong, không phụ thuộc file trả lời)
           gọi phần cài agent. Bản Windows đã có sẵn file này (bản tuỳ biến) → chèn dòng gọi lên ĐẦU, giữ nguyên phần cũ."""
        path = W + ":\\Windows\\Setup\\Scripts\\SetupComplete.cmd"
        line = b'call "C:\\CloudBluePC\\os\\provision.cmd" setupcomplete\r\n'
        old = b""
        try:
            if not self.s.dry and self.s.exists(path): old = self.s.read_bytes(path)
        except Exception: old = b""
        if b"CloudBluePC\\os\\provision.cmd" in old: return
        if old.startswith(b"\xef\xbb\xbf"): old = old[3:]
        if old: self.log("  ban Windows nay co san SetupComplete.cmd -> giu nguyen, chen them dong goi CloudBlue len dau")
        self.s.write_bytes(path, (line + old) if old else (b"@echo off\r\n" + line))

    def add_drivers(self, drv, W, image):
        """Nạp driver (.inf) chủ shop kèm theo vào Windows vừa bung.
           cb\\drivers\\<tên bản, vd 1511>\\…  chỉ nạp khi cài đúng bản đó; file / thư mục khác trong cb\\drivers nạp cho mọi bản."""
        if not self.s.isdir(drv): return
        names = [n for n in self.s.listdir(drv) if n.lower() != "doc-toi.txt"]
        dirs = [n for n in names if self.s.isdir(drv + "\\" + n)]
        use = [n for n in dirs if C.folder_applies(n, image.get("id"))]
        skip = [n for n in dirs if n not in use]
        jobs = [(drv + "\\" + n, True) for n in use]
        if any(n.lower().endswith(".inf") for n in names if n not in dirs): jobs.insert(0, (drv, False))     # file .inf để lẻ ngay trong cb\drivers
        if skip: self.log("Driver cua ban khac (%s) - khong nap cho ban %s." % (", ".join(skip), image.get("id")))
        if not jobs: return
        self.log("Nap driver kem theo: %s ..." % ", ".join(["(file le)"] * (0 if jobs[0][1] else 1) + use))
        scratch = W + ":\\cb-scratch"                        # WinPE chỉ có ~32MB chỗ tạm trên ổ RAM → cho dism dùng chỗ tạm trên ổ đích
        self.s.makedirs(scratch)
        bad = 0
        for path, recurse in jobs:
            argv = ["dism", "/English", "/Image:%s:\\" % W, "/Add-Driver", "/Driver:" + path] + (["/Recurse"] if recurse else []) + ["/ScratchDir:" + scratch]
            rc, out = self.s.run(argv, timeout=3600)
            if rc != 0:
                bad += 1
                self.log("  !! %s: dism ma %s - bo qua, Windows van cai tiep" % (path.split("\\")[-1], rc))
        try: self.s.run(["cmd", "/c", "rd", "/s", "/q", scratch], timeout=120)
        except Exception: pass
        self.log("  driver: " + ("xong" if not bad else "%d / %d thu muc co loi" % (bad, len(jobs))))

    def wipe_others(self, disks, skip, fw):
        for d in C.candidates(disks, skip, 1):
            self.log("Xoa sach o phu: " + d.label())
            rc, out = self.s.diskpart(C.plan_data_disk(d, fw))
            if rc != 0: self.log("  !! xoa o %d loi (ma %s) - bo qua" % (d.index, rc))

    def save_logs(self, *dirs):
        if self.s.dry: return
        txt = "\r\n".join(self.lines) + "\r\n"
        for d in dirs:
            try: self.s.write_text(d + "\\pe-%s.log" % time.strftime("%Y%m%d-%H%M%S"), txt)
            except Exception: pass

    def new_name(self, cfg):
        import random
        return C.clean_name("%s-%06X" % (cfg.get("name_prefix") or "CB", random.getrandbits(24)))

    # ------------------------------------------------------------------ CÀI MỚI từ USB / ISO
    def do_media(self, src, ui):
        cfg = C.load_json(self.s, src.p("cb\\cb.json"))
        if not cfg: raise C.Stop("Bo cai hong: khong doc duoc cb\\cb.json")
        fw = self.s.firmware()
        disks, vols = self.s.disks(), self.s.volumes()
        exclude = {src.vol.disk} if src.vol.disk is not None else set()
        target, why, cands = C.pick_target(disks, exclude, cfg, self.old_system_disks(vols))
        image = C.find_image(cfg)
        wipe_all = bool(cfg.get("wipe_other_disks"))
        secs, auto = max(3, int(cfg.get("countdown", 30))), True
        while True:
            self.banner("CAI WINDOWS TU DONG")
            self.log("  May khoi dong kieu: %s" % fw.upper())
            self.log("  Se cai: %s  [%s]" % (image.get("name") or image["id"], image["id"]))
            for i, im in enumerate(cfg["images"], 1):
                self.log("      %d = %s (%s)%s" % (i, im.get("name") or im["id"], im["id"], "  <-- dang chon" if im is image else ""))
            self.log("")
            if target:
                self.log("  O DICH - SE BI XOA SACH:  %s   (%s)" % (target.label(), why))
            else:
                self.log("  !! CHUA CHON DUOC O DICH: %s" % why)
            others = [d for d in C.candidates(disks, exclude, 1) if not target or d.index != target.index]
            for d in others:
                self.log("  O khac - %s:  %s" % ("CUNG BI XOA SACH" if wipe_all else "khong dung toi", d.label()))
            self.log("")
            self.log("  [Enter] cai ngay   [1-9] chon ban Windows   [D] doi o dich   [A] xoa ca cac o khac: %s" % ("CO" if wipe_all else "khong"))
            self.log("  [X] huy - chuyen sang bo cai Windows thuong   [C] mo dong lenh")
            if target and auto: k = ui.ask(secs, "Tu dong bat dau sau %d giay - bam phim bat ky de dung dem" % secs)
            else: k = ui.ask(0, "Bam Enter de cai, X de huy" if target else "Bam D de chon o, X de huy")
            if k is None or k in ("\r", "\n"):
                if target: break
                continue
            auto = False                                          # đã bấm phím → thôi đếm ngược, chờ Enter
            if k == "x": self.log("Da huy - chuyen sang bo cai Windows thuong."); return RC_SETUP
            if k == "c": ui.shell(); continue
            if k == "a": wipe_all = not wipe_all
            elif k == "d" and cands:
                i = cands.index(target) if target in cands else -1
                target, why = cands[(i + 1) % len(cands)], "nguoi dung chon"
            elif k.isdigit() and 1 <= int(k) <= len(cfg["images"]): image = cfg["images"][int(k) - 1]
        self.banner("BAT DAU CAI - KHONG TAT MAY")
        boot_wim = self.s.size(src.p("sources\\boot.wim")) or 600 * C.MB
        rec_bytes = C.recovery_bytes(cfg, boot_wim, cbrec.extra_bytes(self.s, src.p(""))) if cfg.get("recovery", True) else 0
        if rec_bytes and target.size < rec_bytes + 60 * C.GB:
            self.log("!! O dich nho (%.0f GB) -> KHONG tao phan vung cuu ho (sau nay cai lai phai dung USB)." % target.gb)
            rec_bytes = 0
        wipe_idx = {target.index} | ({d.index for d in others} if wipe_all else set())
        W, S, R = C.pick_letters(self.letters_free_after(vols, wipe_idx))
        plan = C.plan_fresh(target, fw, rec_bytes, (W, S, R))
        self.log("Chia lai o %d (%s)..." % (target.index, "GPT" if fw == "uefi" else "MBR"))
        self.must(self.s.diskpart(plan["lines"]), "Chia o")
        if not self.s.dry:
            for c in (W, S) + ((R,) if rec_bytes else ()):
                if not self.s.isdir(c + ":\\"): raise C.Stop("Chia o xong nhung khong thay o %s:" % c)
        rec_off = None
        if rec_bytes:
            rv = next((v for v in self.s.volumes() if R in v.letters), None)
            if rv is None and not self.s.dry: raise C.Stop("Khong thay phan vung cuu ho vua tao (%s:)." % R)
            rec_off = rv.offset if rv else 0
            self.populate_recovery(src, cfg, R)
        self.apply_image(src, image, W)
        self.make_boot(W, S, fw, fresh_store=False)
        if rec_bytes:
            C.run_cmds(self.s, C.bcd_pe_cmds(fw, R, C.bcd_store(fw, S)), "Tao muc khoi dong cai lai")
        name = self.new_name(cfg)
        seed = {"name": name, "os": image["id"], "from": "media", "pe": PE_VER, "ts": int(self.s.now())}
        key = ""
        try:
            if self.s.exists(src.p("cb\\enroll.key")): key = self.s.read_text(src.p("cb\\enroll.key")).strip()
        except Exception: pass
        if key: seed["enroll_key"] = key
        self.inject(src, W, cfg, image, name, seed)
        if rec_bytes:
            C.save_json(self.s, R + ":\\cb\\identity.json", {"name": name})
            self.save_logs(R + ":\\cb\\logs", W + ":\\CloudBluePC\\logs")
            self.lock_acl(C.acl_vol_cmds(R + ":\\"), "khoa quyen phan vung cuu ho")
            if self.s.dry: self.s.diskpart(C.plan_hide_recovery(target.index, plan["rec_part"], fw, R))
            else: self.hide_recovery(target.index, rec_off, fw, R)
        else:
            self.save_logs(W + ":\\CloudBluePC\\logs")
        if wipe_all: self.wipe_others(self.s.disks(), exclude | {target.index}, fw)
        self.log("")
        self.log("XONG sau %d phut. May se khoi dong lai vao Windows moi (ten may: %s)." % ((self.s.now() - self.t0) // 60, name))
        return RC_OK

    # ------------------------------------------------------------------ CÀI LẠI theo lệnh (phân vùng cứu hộ)
    def do_job(self, rec, ui):
        jpath, rpath = rec.p("cb\\job.json"), rec.p("cb\\job-result.json")
        job = C.load_json(self.s, jpath)
        cfg = C.load_json(self.s, rec.p("cb\\cb.json")) or {}
        fw = self.s.firmware()
        self.banner("CAI LAI WINDOWS THEO LENH")

        def finish(ok, msg, state):
            job["state"] = state
            done = {k: v for k, v in job.items() if k not in ("ticket", "enroll_key")}
            C.save_json(self.s, rpath, {"id": job.get("id"), "ok": ok, "msg": msg, "os": job.get("os"), "pe": PE_VER,
                                        "secs": int(self.s.now() - self.t0), "ts": int(self.s.now())})
            C.save_json(self.s, rec.p("cb\\job.done.json"), done)
            self.s.remove(jpath)

        try:                                                        # ---- kiểm trước, CHƯA xoá gì: lỗi ở đây thì Windows cũ còn nguyên
            image = C.find_image(cfg, job["os"])
            if not self.s.dry and not self.s.exists(rec.p(image["file"])): raise C.Stop("Phan vung cuu ho thieu file %s" % image["file"])
            disks, vols = self.s.disks(), self.s.volumes()
            disk = self.disk_of(rec.vol, disks)
            if disk is None: raise C.Stop("Khong xac dinh duoc o chua phan vung cuu ho.")
            rp = next((p for p in disk.parts if p.offset == rec.vol.offset), None)
            if rp is None: raise C.Stop("Khong thay phan vung cuu ho trong bang phan vung.")
            rec_off = rp.offset
            wipe = job["wipe"]
            others = [d for d in C.candidates(disks, {disk.index}, 1)] if wipe == "all" else []
            used = self.letters_free_after(vols, {d.index for d in others})
            for v in vols:                                          # chữ ổ của các phân vùng trên ổ hệ thống sẽ được sắp lại
                if v.disk == disk.index:
                    for c in v.letters: used.discard(c)
            W, S, R = C.pick_letters(used)
            if wipe not in ("all", "disk", "system"): raise C.Stop("Kieu xoa '%s' khong hop le." % wipe)
            plan = C.plan_job(disk, fw, rec_off, "all" if wipe in ("all", "disk") else "system", job.get("win"), (W, S, R))
        except (C.Stop, KeyError, ValueError) as e:
            self.log("!! KHONG LAM duoc lenh cai lai: %s" % e)
            self.log("   Windows cu van con nguyen - khoi dong lai vao Windows.")
            finish(False, str(e), "failed")
            return RC_REBOOT
        self.log("  Lenh so: %s   Cai: %s [%s]" % (job.get("id"), image.get("name") or image["id"], image["id"]))
        self.log("  O he thong: %s" % disk.label())
        self.log("  Xoa: %s" % {"system": "CHI phan vung Windows cu (cac phan vung khac giu nguyen)", "disk": "ca o he thong (giu khoi dong + cuu ho)",
                               "all": "ca o he thong + MOI o cung khac trong may"}[wipe])
        for d in others: self.log("      cung xoa sach: " + d.label())
        if int(job.get("attempts") or 0) == 0:                      # lần đầu: cho người đứng trước máy 10 giây để huỷ
            k = ui.ask(int(cfg.get("job_countdown", 10)), "Bat dau sau 10 giay - bam X de HUY")
            if k == "x":
                self.log("Da huy tai may - Windows cu con nguyen.")
                finish(False, "huy tai may", "cancelled")
                return RC_REBOOT
        job["attempts"] = int(job.get("attempts") or 0) + 1; job["state"] = "running"
        C.save_json(self.s, jpath, job)
        try:
            self.banner("BAT DAU CAI LAI (lan %d) - KHONG TAT MAY" % job["attempts"])
            # cứu hộ + khởi động: gán chữ ổ tạm
            self.ensure_letter(disk.index, rec_off, R)
            src = Src(self.find_vol(disk.index, rec_off) or rec.vol, "recovery")
            if not self.s.dry: src.root = R + ":\\"
            if not plan["sys_is_win"]:
                self.ensure_letter(disk.index, plan["sys_off"], S)
                store = C.bcd_store(fw, S)
                if self.s.dry or self.s.exists(store):               # mất điện giữa chừng → máy tự vào lại bộ cài này để làm tiếp
                    C.run_cmds(self.s, C.bcd_pe_cmds(fw, R, store), "Tao muc khoi dong cai lai")
                    self.s.run(["bcdedit", "/store", store, "/default", C.PE_GUID], timeout=60)
                    self.s.run(["bcdedit", "/store", store, "/timeout", "0"], timeout=60)
            self.log("Xoa / dinh dang phan vung Windows ...")
            self.must(self.s.diskpart(plan["lines"]), "Chia o")
            if not self.s.dry and not self.s.isdir(W + ":\\"): raise C.Stop("Khong thay o %s: sau khi dinh dang." % W)
            if not plan["sys_is_win"]: self.ensure_letter(disk.index, plan["sys_off"], S)      # số phân vùng có thể đã đổi → gán lại theo vị trí
            self.ensure_letter(disk.index, rec_off, R)
            Sx = W if plan["sys_is_win"] else S
            self.apply_image(src, image, W)
            self.make_boot(W, Sx, fw, fresh_store=not plan["sys_is_win"])
            C.run_cmds(self.s, C.bcd_pe_cmds(fw, R, C.bcd_store(fw, Sx)), "Tao muc khoi dong cai lai")
            ident = C.load_json(self.s, src.p("cb\\identity.json")) or {}
            name = C.clean_name(job.get("name") or ident.get("name") or "", self.new_name(cfg))
            seed = {"name": name, "os": image["id"], "from": "job", "order": job.get("id"), "pe": PE_VER, "ts": int(self.s.now())}
            for k in ("ticket", "enroll_key", "hw"):
                if job.get(k): seed[k] = job[k]
            if ident.get("id"): seed["id"] = ident["id"]
            self.inject(src, W, cfg, image, name, seed)
            if others: self.wipe_others(self.s.disks(), {disk.index}, fw)
            finish(True, "xong", "done")
            self.save_logs(R + ":\\cb\\logs", W + ":\\CloudBluePC\\logs")
            self.lock_acl(C.acl_vol_cmds(R + ":\\"), "khoa quyen phan vung cuu ho")
            try: self.hide_recovery(disk.index, rec_off, fw, R, strict=False)
            except C.Stop: pass
            self.log("")
            self.log("XONG sau %d phut. May se khoi dong lai vao Windows moi." % ((self.s.now() - self.t0) // 60))
            return RC_OK
        except Exception as e:
            self.log("!! LOI khi cai lai (lan %d): %s" % (job["attempts"], e))
            if not isinstance(e, C.Stop): self.log(traceback.format_exc())
            try:
                C.save_json(self.s, rpath, {"id": job.get("id"), "ok": False, "msg": str(e)[:300], "os": job.get("os"), "pe": PE_VER, "ts": int(self.s.now())})
                self.save_logs(rec.p("cb\\logs"))
            except Exception: pass
            if job["attempts"] >= 3:
                self.log("   Da thu 3 lan khong duoc. May can nguoi xu ly (cai lai bang USB).")
                ui.hold("CAI LAI THAT BAI - chup man hinh nay gui ho tro. [C] dong lenh  [R] khoi dong lai")
                return RC_REBOOT
            self.log("   Se tu thu lai sau khi khoi dong lai (toi da 3 lan).")
            ui.ask(20, "Khoi dong lai sau 20 giay...")
            return RC_REBOOT

    # ------------------------------------------------------------------ phân vùng cứu hộ nhưng không có lệnh
    def idle(self, rec, ui):
        job = C.load_json(self.s, rec.p("cb\\job.json"))
        self.banner("PHAN VUNG CUU HO")
        if isinstance(job, dict) and job.get("state") == "running" and int(job.get("attempts") or 0) >= 3:
            self.log("Lenh cai lai so %s da that bai 3 lan. May can nguoi xu ly." % job.get("id"))
            ui.hold("[C] dong lenh  [R] khoi dong lai")
            return RC_REBOOT
        self.log("Khong co lenh cai lai nao dang cho. KHONG xoa gi.")
        ui.ask(15, "Khoi dong lai vao Windows sau 15 giay...")
        return RC_REBOOT

    # ------------------------------------------------------------------ chạy
    def run(self, ui, media_dir=None):
        """media_dir: (chỉ khi chạy thử trên Windows thường) thư mục bộ cài chưa đóng ISO — coi như USB đang cắm."""
        if media_dir:
            root = media_dir.rstrip("\\/") + "\\"
            if not self.s.exists(root + "cb\\cb.json"): raise C.Stop("Thu muc %s khong phai bo cai CloudBlue (thieu cb\\cb.json)." % media_dir)
            return self.do_media(Src(Vol(root, [], "NTFS", "media", 3, None), "media"), ui)
        media, recs = self.wait_sources(int(os.environ.get("CB_WAIT", "40")))
        for r in recs:
            if C.job_valid(C.load_json(self.s, r.p("cb\\job.json"))): return self.do_job(r, ui)
        if media: return self.do_media(media[0], ui)
        if recs: return self.idle(recs[0], ui)
        self.log("Khong thay bo cai CloudBlue tren o nao - chuyen sang bo cai Windows thuong.")
        return RC_SETUP


class ConsoleUI:
    def __init__(self, sysx): self.s = sysx

    def ask(self, secs, prompt):
        """Hiện lời nhắc; chờ `secs` giây (0 = chờ mãi) → phím đã bấm (chữ thường) hoặc None khi hết giờ."""
        if secs <= 0:
            print("  > " + prompt, flush=True)
            while True:
                k = self.s.key_wait(3600)
                if k: return k
        for left in range(secs, 0, -1):
            print("\r  > %s  (con %2d giay) " % (prompt, left), end="", flush=True)
            k = self.s.key_wait(1)
            if k: print(""); return k
        print("")
        return None

    def shell(self):
        print("\n  Dong lenh - go  exit  de quay lai.\n", flush=True)
        try: os.system("cmd.exe")
        except Exception: pass

    def hold(self, prompt):
        while True:
            k = self.ask(0, prompt)
            if k == "c": self.shell()
            elif k == "r": return


class DryUI:
    """Chạy thử: không chờ phím — coi như hết giờ đếm ngược (đồng ý cài)."""
    def ask(self, secs, prompt):
        print("  > %s  [chay thu: tu dong y]" % prompt, flush=True)
        if secs <= 0: raise C.Stop("Chay thu: buoc nay can nguoi bam phim (chua chon duoc o dich).")
        return None

    def shell(self): pass
    def hold(self, prompt): print("  > " + prompt, flush=True)


def main(argv):
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass
    dry = "--dry-run" in argv
    extra = [a for a in argv if not a.startswith("--")]
    sysx = WinSys()
    sysx.dry = dry
    log_path = None if dry else os.path.join(os.environ.get("SystemDrive", "X:") + "\\", "cb-pe.log")
    inst = Installer(sysx, log_path)
    ui = DryUI() if dry else ConsoleUI(sysx)
    try:
        if dry:
            inst.banner("CHAY THU - KHONG DOI GI TREN MAY NAY")
            os.environ.setdefault("CB_WAIT", "3")
        rc = inst.run(ui, extra[0] if (dry and extra) else None)
    except C.Stop as e:
        inst.log(""); inst.log("!! DUNG: %s" % e)
        rc = RC_SETUP
        if not dry:
            inst.log("   Chup man hinh nay gui ho tro. Chuyen sang bo cai Windows thuong sau 60 giay (bam phim de di ngay).")
            ui.ask(60, "...")
    except Exception:
        inst.log(""); inst.log("!! LOI KHONG NGO TOI:"); inst.log(traceback.format_exc())
        rc = RC_SETUP
        if not dry:
            inst.log("   Chup man hinh nay gui ho tro. Chuyen sang bo cai Windows thuong sau 60 giay (bam phim de di ngay).")
            ui.ask(60, "...")
    if rc in (RC_OK, RC_REBOOT) and not dry:
        ui.ask(8, "Khoi dong lai")
        sysx.reboot()
        time.sleep(120)
    if dry: inst.log("CHAY THU XONG - ma %s (0 = se cai, 3 = se chuyen sang bo cai thuong, 10 = khong co gi de lam)" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
