# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_stage.py — CÀI LẠI MÁY NÀY TỪ TRONG WINDOWS (không cần USB). Gọi bởi CAI-DAT.cmd ở gốc ISO / thư mục bộ cài.
#
#  Việc làm:
#    1. Máy chưa có phân vùng cứu hộ CloudBlue → thu nhỏ ổ C:, tạo phân vùng CBRECOVERY, chép bộ cài (2 bản Windows) vào.
#       Máy đã có → chép đè bản mới của bộ cài vào đó.
#    2. Ghi LỆNH cài lại (bản Windows + kiểu xoá) lên phân vùng cứu hộ, đặt máy khởi động 1 lần vào bộ cài.
#    3. Khởi động lại → bộ cài (cb_pe.py) xoá và cài Windows mới, tự cài agent, tự đăng ký lên web.
#  Chưa bấm xác nhận cuối thì CHƯA xoá gì; phân vùng cứu hộ vừa tạo chỉ chiếm chỗ trống của ổ C:.
# =====================================================================================================
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "..", "lib"), os.path.join(HERE, "..", "agent"), HERE):
    _p = os.path.abspath(_p)
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import cbrec                                                     # noqa: E402
from cbsys import WinSys                                         # noqa: E402

STAGE_VER = "20.11a"
WIPES = (("all", "XOA MOI O CUNG trong may (dung khi doi khach / may moi nhan ve)"),
         ("disk", "xoa ca o he thong (o chua Windows), cac o cung khac giu nguyen"),
         ("system", "chi dinh dang lai phan vung Windows (C:), cac phan vung / o khac giu nguyen"))


def prepare(sysx, media_root, cfg, log, progress=None):
    """Bảo đảm máy có phân vùng cứu hộ chứa đúng bộ cài này. Trả volume cứu hộ."""
    rec = cbrec.find_recovery(sysx)
    if rec is None:
        log("May chua co phan vung cuu ho CloudBlue -> tao moi.")
        return cbrec.create_recovery(sysx, media_root, cfg, log, progress)
    need = sum(int(im.get("bytes") or 0) for im in cfg["images"]) + (sysx.size(media_root + "sources\\boot.wim") or 600 * C.MB) + 400 * C.MB
    have = sysx.free_bytes(rec.root)
    old = C.load_json(sysx, rec.root + "cb\\cb.json") or {}
    for im in old.get("images") or []: have += sysx.size(rec.root + im["file"])
    if have < need:
        raise C.Stop("Phan vung cuu ho cu qua nho cho bo cai nay (can %.1f GB, co %.1f GB). Hay cai bang USB 1 lan." % (need / 1e9, have / 1e9))
    log("May da co phan vung cuu ho -> chep de bo cai moi vao.")
    for im in old.get("images") or []: sysx.remove(rec.root + im["file"])
    cbrec.populate(sysx, media_root, cfg, rec.root, log, progress)
    return rec


def stage(sysx, media_root, os_id, wipe, hostname, now, log, extra=None, progress=None):
    """Toàn bộ phần chuẩn bị (KHÔNG khởi động lại). extra: thêm vào lệnh (ticket / hw khi máy đã đăng ký)."""
    cfg = C.load_json(sysx, media_root + "cb\\cb.json")
    if not cfg: raise C.Stop("Khong doc duoc %scb\\cb.json - day khong phai bo cai CloudBlue." % media_root)
    image = C.find_image(cfg, os_id)
    if wipe not in ("all", "disk", "system"): raise C.Stop("Kieu xoa '%s' khong hop le." % wipe)
    for rel in (image["file"], "sources\\boot.wim", "boot\\boot.sdi"):
        if not sysx.exists(media_root + rel): raise C.Stop("Bo cai thieu file %s" % rel)
    prepare(sysx, media_root, cfg, log, progress)
    job = {"id": "local-%d" % int(now), "os": image["id"], "wipe": wipe}
    try:
        if sysx.exists(media_root + "cb\\enroll.key"):
            k = sysx.read_text(media_root + "cb\\enroll.key").strip()
            if k: job["enroll_key"] = k
    except Exception: pass
    job.update(extra or {})
    cbrec.stage_job(sysx, job, hostname, now)
    return image


def ask(prompt, valid, default):
    while True:
        a = input(prompt).strip().lower() or default
        if a in valid: return a
        print("   -> go mot trong: %s" % ", ".join(valid))


def main(argv):
    media = (argv[0] if argv else os.path.join(HERE, "..", ".."))
    media = os.path.abspath(media).rstrip("\\/") + "\\"
    sysx = WinSys()
    print("=" * 72)
    print("  CloudBlue PC %s - CAI LAI MAY NAY TU TRONG WINDOWS" % STAGE_VER)
    print("=" * 72)
    try:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("  !! Can chay bang quyen Admin (bam chuot phai CAI-DAT.cmd -> Run as administrator)."); return 1
    except Exception: pass
    cfg = C.load_json(sysx, media + "cb\\cb.json")
    if not cfg:
        print("  !! Khong doc duoc %scb\\cb.json - day khong phai bo cai CloudBlue." % media); return 1
    print("  Bo cai: %s" % media)
    print("\n  Chon ban Windows:")
    imgs = cfg["images"]
    for i, im in enumerate(imgs, 1):
        print("     %d = %s (%s)%s" % (i, im.get("name") or im["id"], im["id"], "   <- mac dinh" if im["id"] == cfg.get("default") else ""))
    dflt = str(next((i for i, im in enumerate(imgs, 1) if im["id"] == cfg.get("default")), 1))
    image = imgs[int(ask("  Go so roi Enter [%s]: " % dflt, [str(i) for i in range(1, len(imgs) + 1)], dflt)) - 1]
    print("\n  Xoa nhung gi:")
    for i, (_, d) in enumerate(WIPES, 1): print("     %d = %s" % (i, d))
    wipe = WIPES[int(ask("  Go so roi Enter [1]: ", ["1", "2", "3"], "1")) - 1][0]
    extra, hostname = {}, os.environ.get("COMPUTERNAME", "")
    try:                                                            # máy đã chạy agent CloudBlue → xin vé để giữ đúng máy trên web
        import pcagent
        ident = C.load_json(sysx, "C:\\CloudBluePC\\identity.json") or {}
        acfg = C.load_json(sysx, "C:\\CloudBluePC\\cb.json") or cfg
        if ident.get("id") and ident.get("token"):
            r = pcagent.Net(acfg, "C:\\CloudBluePC").rpc("pc_allow_reenroll", {"p_id": ident["id"], "p_token": ident["token"]})
            if r and r.get("ok"): extra = {"ticket": r["ticket"], "hw": ident.get("hw")}
    except Exception:
        pass
    print("\n  SE CAI: %s   |   XOA: %s" % (image.get("name") or image["id"], dict(WIPES)[wipe]))
    print("  Du lieu bi xoa KHONG lay lai duoc. Truoc buoc xac nhan cuoi, may chua bi xoa gi.")
    if "--yes" not in argv and input("  Go  XOA  roi Enter de bat dau (go khac = huy): ").strip().upper() != "XOA":
        print("  Da huy. Khong doi gi."); return 1
    t0 = time.time()

    def progress(done, total, speed):
        print("      %3d%%  %.1f / %.1f GB  (%.0f MB/giay)   " % (done * 100 // max(1, total), done / 1e9, total / 1e9, speed / 1e6), end="\r", flush=True)
    try:
        stage(sysx, media, image["id"], wipe, hostname, time.time(), lambda *a: print("  " + " ".join(str(x) for x in a), flush=True), extra, progress)
    except C.Stop as e:
        print("\n  !! KHONG LAM DUOC: %s" % e)
        print("     May CHUA bi xoa gi."); return 2
    print("\n  Da chuan bi xong sau %d giay. May se KHOI DONG LAI sau 15 giay de cai Windows moi." % (time.time() - t0))
    print("  (Muon huy ngay bay gio: mo CMD go   shutdown /a   roi   bcdedit /deletevalue {bootmgr} bootsequence )")
    os.system("shutdown /r /t 15 /f /c \"CloudBlue: cai lai Windows\"")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
