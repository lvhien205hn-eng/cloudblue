# -*- coding: utf-8 -*-
# =====================================================================
#  phonectl.py — BẢN WINDOWS: LDPlayer 9 (Android 9) · MuMu (Android 12 / 7) · MEmu. Mỗi máy chủ chạy 1 loại (cloudphone.conf EMU=).
#   Cùng câu lệnh với bản Ubuntu để cloudphoned.py / cpapi.py dùng y nguyên.
#   python phonectl.py probe        ← in thông tin giả lập (gửi hỗ trợ khi cài máy chủ MuMu/MEmu mới)
#   python phonectl.py create TÊN --ram 4 --cpu 4 --days 7 [--res 720x1280] [--nowait]
#   python phonectl.py list | capacity | delete TÊN | stop TÊN | start TÊN | restart TÊN | renew TÊN --days N
#   python phonectl.py resize TÊN --ram 6 --cpu 6 | waitboot TÊN | connect-all | reap | rootfix --all | ksuprobe TÊN
#   python phonectl.py idle [--dry -v] | sleep TÊN | wake TÊN | wake --all   ← máy bỏ không 18 giờ tự NGỦ, khách mở máy tự bật lại (IDLE_STOP_H)
#   python phonectl.py bonho [TÊN…] | bonho --sua TÊN… [--gb N]   ← bộ nhớ /data máy khách (chỉ đọc) · --sua: nới ĐÚNG máy ghi tên, không tắt máy
#   python phonectl.py disk TÊN --gb N   ← đặt bộ nhớ 1 máy lên N GB (khách mua thêm — cloudphoned gọi) · chỉ lớn lên, giữ dữ liệu
#                                     (máy MỚI tự nới lúc lên lần đầu theo cấu hình: DISK_TIERS; máy cũ chỉ nới khi khách mua / admin gõ tên)
#  Máy số N của MEmu ⇄ adb 127.0.0.1:(21503 + 10·N)
# =====================================================================
import argparse, atexit, contextlib, ctypes, datetime, glob, hashlib, json, os, re, shutil, subprocess, sys, time

HOME = os.environ.get("BLUE_HOME") or os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HOME, "redroid", "phones.json")
CONF_F = os.path.join(HOME, "cloudphone.conf")
ADB = os.path.join(HOME, "platform-tools", "adb.exe")
os.environ["ADB_LOCAL_TRANSPORT_MAX_PORT"] = "5553"      # adb không tự dò emulator-55xx (LDPlayer hiện trùng máy) — xem panel.py
GRACE_MIN = 30
BOOT_WAIT = 300
SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")
VMDATA = os.path.join(HOME, "vmdata")                     # thư mục RIÊNG từng máy trên Windows (LDPlayer: ảnh / file chia sẻ của máy) — xoá máy là xoá luôn

def _conf():
    c = {}
    try:
        for line in open(CONF_F, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); c[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError: pass
    return c
CONF = _conf()
try: BOOT_WAIT = max(30, int(float(CONF.get("BOOT_WAIT_S") or BOOT_WAIT)))      # 17/11f: BOOT_WAIT_S trong cloudphone.conf (mặc định 300 giây)
except (TypeError, ValueError): pass
RESERVE = float(CONF.get("WIN_RAM_RESERVE", "4") or 4)          # GB RAM Windows luôn chừa lại
MEMU_DIRS = [CONF.get("MEMU_DIR", ""), os.environ.get("MEMU_DIR", ""), r"C:\Program Files\Microvirt\MEmu", r"D:\Program Files\Microvirt\MEmu",
             r"C:\Microvirt\MEmu", r"D:\Microvirt\MEmu", r"C:\Program Files (x86)\Microvirt\MEmu"]
MEMU = next((d for d in MEMU_DIRS if d and os.path.isfile(os.path.join(d, "memuc.exe"))), "")
# ---------- LDPlayer 9 (thay MEmu): có ldconsole.exe mà KHÔNG có MEmu, hoặc conf EMU=ld ----------
LD_DIRS = [CONF.get("LD_DIR", ""), r"C:\LDPlayer\LDPlayer9", r"D:\LDPlayer\LDPlayer9", r"C:\Program Files\LDPlayer\LDPlayer9",
           r"C:\leidian\LDPlayer9", r"D:\leidian\LDPlayer9"]
LD = next((d for d in LD_DIRS if d and os.path.isfile(os.path.join(d, "ldconsole.exe"))), "")
# ---------- MuMu (NetEase, Android 12 / Android 7): MuMuManager.exe / mumu-cli.exe ----------
MUMU_DIRS = [CONF.get("MUMU_DIR", ""), os.environ.get("MUMU_DIR", ""), r"C:\Program Files\Netease\MuMuPlayer-12.0", r"D:\Program Files\Netease\MuMuPlayer-12.0",
             r"C:\Program Files\Netease\MuMu Player 12", r"D:\Program Files\Netease\MuMu Player 12", r"C:\Program Files\Netease\MuMuPlayer",
             r"D:\Program Files\Netease\MuMuPlayer", r"C:\Program Files\MuMuPlayerGlobal-12.0", r"D:\Program Files\MuMuPlayerGlobal-12.0",
             r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0", r"C:\Program Files\Netease\MuMu", r"D:\Program Files\Netease\MuMu"]
MUMU_REL = (r"nx_main\mumu-cli.exe", r"shell\MuMuManager.exe", r"nx_main\MuMuManager.exe", "MuMuManager.exe", "mumu-cli.exe")
MUMU_CACHE = os.path.join(HOME, "redroid", "mumu_dir.txt")      # chỗ cài MuMu dò được lần trước (khỏi dò lại mỗi lệnh)
def _mumu_in(d):
    """File lệnh của MuMu trong thư mục d (tìm cả thư mục con ≤ 3 cấp). Không có → ""."""
    if not d or not os.path.isdir(d): return ""
    for rel in MUMU_REL:
        f = os.path.join(d, rel)
        if os.path.isfile(f): return f
    top = os.path.abspath(d).rstrip("\\/").count(os.sep)
    for root, dirs, files in os.walk(d):
        if root.rstrip("\\/").count(os.sep) - top >= 3: dirs[:] = []
        low = {x.lower(): x for x in files}
        for n in ("mumu-cli.exe", "mumumanager.exe"):
            if n in low: return os.path.join(root, low[n])
    return ""
def _mumu_root(f):
    d = os.path.dirname(f)
    return os.path.dirname(d) if os.path.basename(d).lower() in ("shell", "nx_main") else d
def _reg_dir(v):
    """Thư mục lấy từ 1 giá trị registry: đường dẫn uninstall.exe (có ngoặc kép, có tham số), MuMuPlayer.exe,0 hoặc InstallLocation."""
    v = (v or "").strip()
    if v.startswith('"'): v = v[1:].split('"', 1)[0]
    else:
        m = re.match(r"(.+?\.(?:exe|ico|dll))(?:[\s,].*)?$", v, re.I)
        if m: v = m.group(1)
    v = v.strip().rstrip("\\/")
    if re.search(r"\.(exe|ico|dll)$", v, re.I): v = os.path.dirname(v)
    return v if v and os.path.isdir(v) else ""
def _fixed_drives():
    try:
        k = ctypes.windll.kernel32; m = k.GetLogicalDrives()
        return [chr(65 + i) for i in range(26) if m >> i & 1 and k.GetDriveTypeW(f"{chr(65 + i)}:\\") == 3]
    except Exception: return ["C", "D", "E"]
def _proc_dirs(word):
    """Thư mục của các chương trình ĐANG CHẠY có tên chứa word (MuMu đang mở → biết ngay MuMu cài ở đâu)."""
    out = []
    try:
        k = ctypes.WinDLL("kernel32"); ps = ctypes.WinDLL("psapi"); k.OpenProcess.restype = ctypes.c_void_p
        arr = (ctypes.c_ulong * 8192)(); n = ctypes.c_ulong()
        if not ps.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(n)): return out
        for pid in arr[:n.value // ctypes.sizeof(ctypes.c_ulong)]:
            h = k.OpenProcess(0x1000, False, pid)              # PROCESS_QUERY_LIMITED_INFORMATION
            if not h: continue
            try:
                buf = ctypes.create_unicode_buffer(1024); sz = ctypes.c_ulong(1024)
                if k.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(sz)) and word in os.path.basename(buf.value).lower():
                    out += [os.path.dirname(buf.value), os.path.dirname(os.path.dirname(buf.value))]
            finally: k.CloseHandle(ctypes.c_void_p(h))
    except Exception: pass
    return out
def _mumu_guess():
    """MuMu cài chỗ khác mặc định: khoá gỡ cài đặt trong registry → chương trình MuMu đang chạy → thư mục Netease/MuMu ở mọi ổ cứng."""
    out = []
    try:
        import winreg
        for hv, base in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                         (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                         (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")):
            try: k = winreg.OpenKey(hv, base)
            except OSError: continue
            for i in range(winreg.QueryInfoKey(k)[0]):
                try:
                    sub = winreg.EnumKey(k, i); sk = winreg.OpenKey(k, sub)
                    def val(n):
                        try: return str(winreg.QueryValueEx(sk, n)[0] or "")
                        except OSError: return ""
                    if "mumu" not in (sub + " " + val("DisplayName")).lower(): continue
                    for n in ("InstallLocation", "InstallDir", "DisplayIcon", "UninstallString"):
                        d = _reg_dir(val(n))
                        if d: out += [d, os.path.dirname(d)]
                except OSError: continue
    except Exception: pass
    out += _proc_dirs("mumu")
    for dr in _fixed_drives():
        for pat in (r"\Program Files\Netease\*", r"\Program Files (x86)\Netease\*", r"\Netease\*", r"\Program Files\MuMu*",
                    r"\Program Files (x86)\MuMu*", r"\MuMu*", r"\*\MuMu*", r"\*\Netease\*"):
            out += glob.glob(dr + ":" + pat)
    return out
def _find_mumu(deep=True):
    for d in MUMU_DIRS:
        f = _mumu_in(d)
        if f: return _mumu_root(f), f
    try:
        f = _mumu_in(open(MUMU_CACHE, encoding="utf-8").read().strip())
        if f: return _mumu_root(f), f
    except OSError: pass
    if not deep: return "", ""
    seen = set()
    for d in _mumu_guess():
        key = os.path.normcase(os.path.abspath(d))
        if key in seen: continue
        seen.add(key)
        f = _mumu_in(d)
        if f:
            try: open(MUMU_CACHE, "w", encoding="utf-8").write(_mumu_root(f))
            except OSError: pass
            return _mumu_root(f), f
    return "", ""
_E = CONF.get("EMU", "").lower()
MUMU, MUMU_CLI = _find_mumu(deep=_E == "mumu" or (not _E and not LD and not MEMU))   # máy chủ LDPlayer/MEmu: khỏi dò MuMu sâu
if _E in ("ld", "mumu", "memu"): EMU = _E
elif LD and not MEMU and not MUMU: EMU = "ld"
elif MUMU and not MEMU and not LD: EMU = "mumu"
else: EMU = "ld" if LD and not MEMU else ("memu" if MEMU else ("mumu" if MUMU else "ld"))
if EMU == "ld": MEMU = LD                  # các chỗ kiểm tra "có giả lập chưa" dùng chung biến MEMU
if EMU == "mumu": MEMU = MUMU
EMU_NAME = {"ld": "LDPlayer 9", "mumu": "MuMu", "memu": "MEmu"}[EMU]
# Các bản Android máy chủ này bán (đơn khách chọn bản nào thì tạo bản đó). LDPlayer 9 = Android 9.
ANDROIDS = [x.strip() for x in (CONF.get("ANDROIDS") or {"ld": "9", "mumu": "12,7", "memu": "7"}[EMU]).split(",") if x.strip()]
DEF_ANDROID = ANDROIDS[0] if ANDROIDS else "9"
MEMU_CODES = {"5": "51", "7": "76", "9": "96"}          # memuc create <mã>: 76 = Android 7.1 64-bit · 96 = Android 9 64-bit
def tpl_name(ver):
    """Máy MẪU cho 1 bản Android (admin tạo tay 1 lần trong giả lập, đặt tên tpl_a12 / tpl_a7…) → máy khách được NHÂN BẢN từ máy mẫu."""
    return CONF.get(f"TPL_A{ver}", f"tpl_a{ver}")
def norm_android(v):
    v = str(v or "").strip().split(".")[0]
    if EMU == "ld": return "9"
    return v if v in ANDROIDS else DEF_ANDROID
NOWIN = 0x08000000

def run(args, timeout=180, text=True):
    """Chạy lệnh, ghi kết quả ra FILE tạm (không dùng pipe): memuc hay để lại tiến trình con giữ pipe → Python chờ mãi
       dù đã quá giờ (khoá MEmu bị giữ hàng chục phút, đơn khách bị huỷ). Quá giờ → tắt cả cây tiến trình, trả về ngay."""
    import tempfile
    args = [str(x) for x in args]
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        try: p = subprocess.Popen(args, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, creationflags=NOWIN)
        except OSError as e: return subprocess.CompletedProcess(args, 127, "", str(e))
        try: code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            tree = ["/T"] if args[0].lower().endswith(("memuc.exe", "ldconsole.exe")) else []      # adb: KHÔNG /T (adb server có thể là "con" → chết theo)
            subprocess.run(["taskkill", "/PID", str(p.pid)] + tree + ["/F"], capture_output=True, creationflags=NOWIN)
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: pass
            code = 124
        fo.seek(0); fe.seek(0); out, err = fo.read(), fe.read()
    if text: out, err = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    if code == 124: err = (err or "") + ("timeout" if text else b"timeout")
    return subprocess.CompletedProcess(args, code, out, err)
LONG_F = os.path.join(HOME, "redroid", "memuc_long.flag")
_LONG_OPS = ("clone", "create", "import", "export")
def _long_mark(on):
    """Đánh dấu "đang chạy lệnh MEmu DÀI" (nhân bản / tạo máy, có thể vài phút) → chương trình khác chờ, không coi là treo."""
    try:
        if on: open(LONG_F, "w").write(str(os.getpid()))
        elif open(LONG_F).read().strip() == str(os.getpid()): os.remove(LONG_F)
    except OSError: pass
def _long_busy():
    try:
        pid = open(LONG_F).read().strip()
        return pid.isdigit() and int(pid) != os.getpid() and _pid_alive(pid) and time.time() - os.path.getmtime(LONG_F) < 960
    except OSError: return False
MUMU_CLONE_T = 900          # 15/11: giây tối đa cho 1 lần MuMu nhân bản máy mẫu (máy chủ bận có thể mất nhiều phút)
def _lock_touch(name):
    """15/11: đang giữ khoá LÂU hợp lệ (nhân bản máy mẫu) → làm mới giờ file khoá để lệnh khác thấy khoá còn mới thì CHỜ, không coi là treo."""
    f = os.path.join(HOME, "redroid", name + ".lock")
    try:
        if open(f).read().strip() == str(os.getpid()): os.utime(f, None)
    except OSError: pass
UNSTICK_AGE = 300 if EMU == "mumu" else 420     # khoá giữ CHƯA quá chừng này giây = chương trình giữ khoá còn đang làm việc (mọi lệnh giả lập có giờ chặn riêng trong run())
def _unstick_memuc():
    """Khoá memuc bị giữ quá lâu (1 lệnh memuc treo) → tắt các memuc.exe đang treo + gỡ khoá, để đơn khách không bị huỷ.
       KHÔNG tắt chương trình giữ khoá khi khoá còn MỚI (< UNSTICK_AGE): 12/11 win3 nhiều khách mở máy ngủ cùng lúc → lệnh chờ lâu
       tắt luôn lệnh đang bật máy dở ("mã 1", "lệnh MEmu bị treo") → máy nào cũng bật lỗi. Khoá mới → chỉ chờ tiếp."""
    if _long_busy():          # đang nhân bản / tạo máy cho khách (hợp lệ, vài phút) → CHỜ, không tắt (tắt giữa chừng = máy hỏng + đơn lỗi)
        t0 = time.time()
        while _long_busy() and time.time() - t0 < 600: time.sleep(3)
        return
    try:
        if time.time() - os.path.getmtime(os.path.join(HOME, "redroid", "memuc.lock")) < UNSTICK_AGE: return
    except OSError: return                                # không còn khoá → không có gì để gỡ
    run(["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'memuc.exe','ldconsole.exe' } | Where-Object { $_.CreationDate -lt (Get-Date).AddSeconds(-45) } | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], 60)
    # chương trình đang GIỮ khoá (vd connect-all cũ treo từ lâu) → tắt nó; Windows không cho xoá file khoá khi nó còn mở
    lf = os.path.join(HOME, "redroid", "memuc.lock")
    try:
        pid = open(lf).read().strip()
        if pid.isdigit() and int(pid) != os.getpid():
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=NOWIN)
    except OSError: pass
    time.sleep(2)
    try: os.remove(lf)
    except OSError: pass
    print("   (lệnh MEmu bị treo → đã gỡ, làm tiếp)", flush=True)
def _ld_cfgfile(i): return os.path.join(LD, "vms", "config", f"leidian{int(i)}.config")
def ld_cfg(i, **kv):
    """Ghi thẳng file cài đặt máy LDPlayer (chỉ khi máy đang TẮT): luôn bật ADB nội bộ + root (không có → adb 'offline')."""
    f = _ld_cfgfile(i)
    try: d = json.load(open(f, encoding="utf-8-sig"))
    except Exception: d = {}
    d.update({"basicSettings.adbDebug": 1, "basicSettings.rootMode": True}); d.update(kv)
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fo: json.dump(d, fo, ensure_ascii=False, indent=4)
    except OSError: pass
LD_SHARE_KEYS = ("statusSettings.sharedPictures", "statusSettings.sharedMisc", "statusSettings.sharedApplications")
def _ld_share_kv(i, name):
    """LDPlayer: thư mục chia sẻ của máy (Pictures / Misc / Applications — Android thấy ở /sdcard/Pictures…) → thư mục RIÊNG
       vmdata/TÊN/… của đúng máy đó. Mặc định MỌI máy dùng chung Documents/XuanZhi9/… → khách này thấy ảnh / file của khách kia."""
    if not _vmname_ok(name): return {}
    try: d = json.load(open(_ld_cfgfile(i), encoding="utf-8-sig"))
    except Exception: d = {}
    keys = [k for k, v in d.items() if "shared" in k.lower() and isinstance(v, str)] or list(LD_SHARE_KEYS)
    out = {}
    for k in keys:
        sub = re.sub(r"(?i)^.*shared", "", k.split(".")[-1]) or "Misc"
        p = os.path.join(_vmdir(name), sub)
        try: os.makedirs(p, exist_ok=True)
        except OSError: continue
        out[k] = p.replace("\\", "/")
    return out
def _vmname_ok(name):
    """Tên máy dùng làm tên thư mục được: chữ/số đứng đầu, không chấm/cách cuối (Windows bỏ chấm cuối → 2 tên trùng 1 thư mục)."""
    return bool(name) and bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", str(name))) and not str(name).endswith(".")
def _vmdir(name): return os.path.join(VMDATA, str(name).lower())          # Windows không phân biệt hoa thường → luôn chữ thường
def _vmdata_rm(name):
    """Máy bị xoá → xoá luôn thư mục riêng của máy (ảnh / file chia sẻ của khách đi theo máy, không để sót cho máy sau)."""
    if not _vmname_ok(name): return
    root = os.path.realpath(VMDATA); p = os.path.realpath(_vmdir(name))
    if os.path.dirname(p) != root or not os.path.isdir(p): return            # chỉ đúng 1 thư mục con trực tiếp của vmdata
    shutil.rmtree(p, ignore_errors=True)
def _forget_files(name):
    """14/11: máy đã xoá hẳn → xoá luôn mọi dấu vết nhỏ của nó trên máy chủ (dấu cài app sẵn, lịch chống kẹt / bật lỗi, suất khởi động)."""
    d = os.path.join(HOME, "redroid")
    for fn in os.listdir(d) if os.path.isdir(d) else []:
        if fn.startswith(f"pre_{name}_") and fn.endswith(".ok"):
            try: os.remove(os.path.join(d, fn))
            except OSError: pass
    for f in (os.path.join(d, "heal.json"), os.path.join(d, "startfail.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
            if isinstance(j, dict) and j.pop(name, None) is not None: json.dump(j, open(f, "w", encoding="utf-8"))
        except Exception: pass
    try: _boot_done(name)
    except Exception: pass
def _vmdata_rm_if_gone(name):
    """Chỉ xoá thư mục riêng khi đọc được danh sách máy và CHẮC CHẮN không còn máy nào tên đó."""
    if not _vmname_ok(name): return
    v = vms_sure()
    if v and not any(str(x["name"]).lower() == str(name).lower() for x in v.values()): _vmdata_rm(name)
def _ldrun(args, timeout):
    return run([os.path.join(LD, "ldconsole.exe")] + [str(x) for x in args], timeout)
def _ldlist():
    r = _ldrun(["list2"], 60); out = {}
    for ln in (r.stdout or "").splitlines():
        q = ln.strip().split(",")
        if len(q) >= 5 and q[0].isdigit() and int(q[0]) < 99999:      # 99999 = trình quản lý nhiều máy, không phải máy
            out[int(q[0])] = {"name": q[1].strip(), "running": q[4].strip() == "1", "pid": q[5] if len(q) > 5 else "-1"}
    return out
def _ok(out=""): return subprocess.CompletedProcess([], 0, out, "")
def _ld(a, timeout):
    """Dịch lệnh memuc → ldconsole (LDPlayer 9). Trả kết quả GIỐNG memuc để phần còn lại của tool dùng y nguyên."""
    a = [str(x) for x in a]; c = a[0]
    def ix(): return a[a.index("-i") + 1] if "-i" in a else "0"
    if c == "listvms":
        L = _ldlist(); run_only = "--running" in a
        return _ok("\n".join(f"{i},{x['name']},0,{1 if x['running'] else 0},{x['pid']}" for i, x in sorted(L.items()) if x["running"] or not run_only))
    if c == "ensurebase":
        # 17/11a: LDPlayer vừa cài không có máy nào — list2 chỉ ra dòng "99999,…" (màn hình máy tính, không phải máy). Phần còn lại của tool
        # coi danh sách rỗng là "chưa đọc được" (an toàn cho lệnh xoá) nên không tạo được máy nào. CHỈ khi CHẮC LDPlayer trống (list2 chạy
        # được, không có máy, có dòng 99999 hoặc thư mục vms không có leidianN) mới tạo máy gốc tên LDPlayer. Không chắc → báo lỗi, không tạo.
        r = _ldrun(["list2"], 60)
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        if any(re.match(r"^\d+,", ln) and not ln.startswith("99999,") for ln in lines): return _ok("LDBASE co")
        desk = any(ln.startswith("99999,") for ln in lines)
        try: dirs = [d for d in os.listdir(os.path.join(LD, "vms")) if re.fullmatch(r"leidian\d+", d)]
        except OSError: dirs = None
        if r.returncode not in (0, None) or not (desk or dirs == []):
            return subprocess.CompletedProcess([], 1, r.stdout, ((r.stderr or "").strip() + " chưa chắc LDPlayer trống (lệnh list2 lỗi / không trả lời)").strip())
        r2 = _ldrun(["add", "--name", "LDPlayer"], timeout)
        for _ in range(20):
            if _ldlist(): return _ok("LDBASE da_tao")
            time.sleep(2)
        return subprocess.CompletedProcess([], 1, r2.stdout, ((r2.stderr or "").strip() + " LDPlayer không tạo được máy gốc").strip())
    if c == "create":
        before = set(_ldlist()); tmp = f"new_{int(time.time())}"
        r = _ldrun(["add", "--name", tmp], timeout)
        new = sorted(set(_ldlist()) - before)
        if not new: return subprocess.CompletedProcess([], 1, r.stdout, (r.stderr or "") + " LDPlayer không tạo được máy")
        ld_cfg(new[-1]); return _ok(f"index: {new[-1]}")
    if c == "rename": return _ldrun(["rename", "--index", ix(), "--title", a[-1]], timeout)
    if c == "start":
        cur = _ldlist().get(int(ix())) or {}
        if not cur.get("running"): ld_cfg(ix(), **_ld_share_kv(ix(), cur.get("name")))      # thư mục chia sẻ RIÊNG của máy này
        r = _ldrun(["launch", "--index", ix()], timeout); time.sleep(3)
        if not (_ldlist().get(int(ix())) or {}).get("running"): time.sleep(10)
        if not (_ldlist().get(int(ix())) or {}).get("running"): return subprocess.CompletedProcess([], 1, r.stdout, "start vm failed")
        return _ok("start ok")
    if c == "stop":
        r = _ldrun(["quit", "--index", ix()], timeout)
        for _ in range(20):
            if not (_ldlist().get(int(ix())) or {}).get("running"): break
            time.sleep(2)
        return _ok("stop ok")
    if c == "stopall": return _ldrun(["quitall"], timeout)
    if c == "remove":
        r = _ldrun(["remove", "--index", ix()], timeout)
        return _ok("remove ok") if int(ix()) not in _ldlist() else subprocess.CompletedProcess([], 1, r.stdout, "remove failed")
    if c == "setconfigex":
        k, v = a[-2], a[-1]
        if k == "memory": return _ldrun(["modify", "--index", ix(), "--memory", v], timeout)
        if k == "cpus": return _ldrun(["modify", "--index", ix(), "--cpu", v], timeout)
        if k == "enable_su": return _ldrun(["modify", "--index", ix(), "--root", "1"], timeout)
        if k == "fps": return _ldrun(["globalsetting", "--fps", CONF.get("LD_FPS", "60"), "--audio", "0"], timeout)   # FPS của LDPlayer là CHUNG mọi máy → giữ 60 (kéo/lướt mượt)
        return _ok()                                                     # chế độ vẽ, gmem… LDPlayer không có → bỏ qua
    if c == "getconfigex":
        k = a[-1]
        if k == "cpus":
            try: return _ok("Value: " + str(json.load(open(_ld_cfgfile(ix()), encoding="utf-8-sig")).get("advancedSettings.cpuCount", "?")))
            except Exception: return _ok("Value: ?")
        return _ok("Value: 1")
    return _ok()
# ---------------- MuMu: dịch lệnh memuc → MuMuManager / mumu-cli ----------------
def _mumurun(args, timeout): return run([MUMU_CLI] + [str(x) for x in args], timeout)
def _mumu_json(txt):
    txt = (txt or "").strip()
    i = min([k for k in (txt.find("{"), txt.find("[")) if k >= 0] or [-1])
    if i < 0: return None
    try: return json.loads(txt[i:])
    except Exception:
        try: return json.loads(txt[i:txt.rfind("}") + 1])
        except Exception: return None
_MUMU_INFO = {"t": 0, "v": {}}
def _mumu_info(fresh=True):
    if not fresh and time.time() - _MUMU_INFO["t"] < 5: return _MUMU_INFO["v"]
    j = _mumu_json(_mumurun(["info", "-v", "all"], 60).stdout) or {}
    if isinstance(j, dict) and ("index" in j or "name" in j) and not any(isinstance(v, dict) for v in j.values()): j = {str(j.get("index", 0)): j}
    out = {}
    for k, v in (j.items() if isinstance(j, dict) else enumerate(j or [])):
        if isinstance(v, dict):
            ix = str(v.get("index", k))
            if ix.isdigit(): out[int(ix)] = v
    _MUMU_INFO.update(t=time.time(), v=out)
    return out
def _mumu_major(v): return str((v or {}).get("android_version") or "").split(".")[0].strip()     # "15.0" → "15"
def _mumu_running(v): return bool(v.get("is_process_started") or v.get("is_android_started") or str(v.get("player_state", "")).startswith("start"))
def _mumu_list(): return {i: {"name": str(v.get("name", "")), "running": _mumu_running(v), "pid": v.get("pid", -1)} for i, v in _mumu_info().items()}
_MUMU_KEYS = {}
_MUMU_MODE_KEYS = ("performance_mode", "resolution_mode")
def _mumu_all(idx):
    """Mọi cài đặt HIỆN TẠI của 1 máy MuMu (đọc mới, không dùng bộ nhớ đệm) → dict ({} nếu không đọc được)."""
    j = _mumu_json(_mumurun(["setting", "-v", str(idx), "-a"], 60).stdout)
    if not isinstance(j, dict) or not j: j = _mumu_json(_mumurun(["setting", "--vmindex", str(idx), "--all"], 60).stdout)
    return j if isinstance(j, dict) else {}
def _fnum(x):
    try: return float(str(x).strip())
    except (TypeError, ValueError): return None
def _mumu_hw_eff(allk):
    """(nhân, RAM GB, chế độ) máy MuMu SẼ CHẠY: vm_cpu / vm_mem nếu MuMu có 2 khoá đó, không thì số của chế độ đang chọn."""
    mode = str(allk.get("performance_mode", "")).strip()
    c, m = _fnum(allk.get("vm_cpu")), _fnum(allk.get("vm_mem"))
    if c is None and mode: c = _fnum(allk.get(f"performance_cpu.{mode}"))
    if m is None and mode: m = _fnum(allk.get(f"performance_mem.{mode}"))
    return c, m, mode
def _mumu_hw_ok(allk, cpu, mem):
    c, m, _ = _mumu_hw_eff(allk)
    return c is not None and m is not None and int(round(c)) == int(cpu) and abs(m - float(mem)) < 0.01
def _mumu_hw(idx, cpu, mem):
    """Đặt nhân + RAM THẬT cho 1 máy MuMu (máy phải TẮT) rồi ĐỌC LẠI kiểm tra → (ok, chữ). Thử lần lượt tới khi đúng:
       ① số custom trước, chế độ custom sau · ② đổi chế độ qua middle rồi về custom · ③ ghi thẳng vm_cpu / vm_mem."""
    idx = str(idx); cpu = int(cpu); mem = float(mem)
    _MUMU_KEYS.pop(idx, None)
    allk = _mumu_all(idx)
    if not allk: return False, "không đọc được cài đặt MuMu của máy này"
    if _mumu_hw_ok(allk, cpu, mem): return True, f"đã đúng {cpu} nhân · {mem:g}GB"
    cv, mv = str(cpu), f"{mem:.6f}"
    tries = (("custom trước, chế độ sau", [("performance_cpu.custom", cv), ("performance_mem.custom", mv), ("performance_mode", "custom")]),
             ("đổi chế độ qua lại", [("performance_mode", "middle"), ("performance_mode", "custom")]),
             ("ghi thẳng vm_cpu/vm_mem", [("vm_cpu", cv), ("vm_mem", f"{mem:g}")]))
    done = []
    for name, kv in tries:
        kv = [(k, v) for k, v in kv if k in allk]
        if not kv: continue
        for k, v in kv:
            r = _mumurun(["setting", "-v", idx, "-k", k, "-val", v], 60)
            o = ((r.stdout or "") + (r.stderr or "")).lower()
            if r.returncode not in (0, None) or "error" in o or "invalid" in o:
                _mumurun(["setting", "--vmindex", idx, "--key", k, "--value", v], 60)
        done.append(name)
        allk = _mumu_all(idx) or allk
        if _mumu_hw_ok(allk, cpu, mem): return True, f"đã đặt {cpu} nhân · {mem:g}GB ({name})"
    c, m, mode = _mumu_hw_eff(allk)
    return False, f"MuMu vẫn ghi {c if c is None else int(c)} nhân · {m}GB (chế độ {mode or '?'}) sau khi thử: {', '.join(done) or 'không có khoá nào'}"
def _mumu_set(idx, kv):
    """Ghi cài đặt máy MuMu (máy phải đang TẮT). Tự dò tên khoá (MuMu đổi tên khoá theo bản)."""
    if idx not in _MUMU_KEYS:
        _MUMU_KEYS[idx] = _mumu_json(_mumurun(["setting", "-v", idx, "-a"], 60).stdout) or _mumu_json(_mumurun(["setting", "--vmindex", idx, "--all"], 60).stdout) or {}
    allk = _MUMU_KEYS[idx] if isinstance(_MUMU_KEYS[idx], dict) else {}
    def pick(*names):
        for n in names:
            if n in allk: return n
        for n in names:
            hit = [k for k in allk if k.startswith(n)]
            if hit: return sorted(hit, key=len)[0]
        return names[0]
    want = []
    for k, v in kv.items():
        if k == "cpu": want += [(pick("performance_mode"), "custom"), (pick("performance_cpu.custom", "performance_cpu"), str(v))]
        elif k == "mem": want += [(pick("performance_mode"), "custom"), (pick("performance_mem.custom", "performance_mem"), f"{float(v):.6f}")]
        elif k == "res":
            w, h, d = v
            want += [(pick("resolution_mode"), "custom"), (pick("resolution_width.custom", "resolution_width"), str(w)),
                     (pick("resolution_height.custom", "resolution_height"), str(h)), (pick("resolution_dpi.custom", "resolution_dpi"), str(d))]
        elif k == "root": want.append((pick("root_permission"), "true"))
        elif k == "fps": want.append((pick("max_frame_rate"), str(v)))
        else: want.append((k, str(v)))
    # CHẾ ĐỘ ghi SAU CÙNG: MuMu chép số của chế độ (custom/middle…) sang cấu hình máy ảo (vm_cpu / vm_mem) lúc ĐẶT CHẾ ĐỘ.
    # Ghi chế độ trước rồi mới ghi số "custom" → máy ảo giữ số custom CŨ (mặc định 4 nhân · 6GB) — lỗi "mua 16GB ra 6GB" 09/11.
    want = [x for x in want if x[0] not in _MUMU_MODE_KEYS] + [x for x in want if x[0] in _MUMU_MODE_KEYS]
    seen = set()
    for k, v in want:
        if k in seen or (allk and k not in allk and k not in ("performance_mode", "resolution_mode")): continue
        seen.add(k)
        r = _mumurun(["setting", "-v", idx, "-k", k, "-val", v], 60)
        o = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode not in (0, None) or "error" in o or "invalid" in o:
            _mumurun(["setting", "--vmindex", idx, "--key", k, "--value", v], 60)
# ---- MuMu: bật / tắt 1 máy mà KHÔNG giữ khoá memuc lúc chờ máy lên / xuống (12/11: giữ khoá cả phút → lệnh khác chờ quá lâu) ----
MUMU_START_WAIT = 60        # giây chờ máy MuMu hiện "đang chạy" sau lệnh launch (máy chủ bận có thể quá 30 giây)
MUMU_POLL = 3               # giây giữa 2 lần xem máy đã lên chưa
MUMU_MAIN_SETTLE = 20       # giây chờ MuMuNxMain vừa mở lại nhận lệnh
MUMU_MAIN_F = os.path.join(HOME, "redroid", "mumu_main_fix.txt")      # lúc mở lại MuMuNxMain gần nhất
MUMU_MAIN_FIX = CONF.get("MUMU_MAIN_FIX", "1").strip() != "0"         # 0 = không tự mở lại chương trình chính của MuMu
def _mumu_locked(fn, wait=240, long_op=False):
    """fn() trong khoá memuc (lệnh MuMu không chạy chồng). Chờ lâu → _unstick_memuc (khoá mới thì chỉ chờ tiếp) → chờ thêm.
       long_op (16/11e — nhân bản máy mẫu, vài phút): máy khách đang khởi động lại (đã tắt, chưa bật) → trả khoá, chờ máy đó được bật
       rồi mới nhân bản (tối đa CYC_WAIT giây) — không để máy khách nằm tắt suốt lúc nhân bản."""
    t0 = time.time(); t_c = time.time(); lk = None; said = False
    while lk is None:
        lk = _Lock("memuc", wait=wait)
        try: lk.__enter__()
        except RuntimeError:
            lk = None
            if _long_busy() and time.time() - t0 < MUMU_CLONE_T + 600: continue     # 15/11: lệnh khác đang NHÂN BẢN máy cho khách → chờ tiếp
            _unstick_memuc(); lk = _Lock("memuc", wait=240); lk.__enter__()
        if long_op and time.time() - t_c < CYC_WAIT and _cyc_busy():
            lk.__exit__(); lk = None
            if not said: print("   (máy khách đang khởi động lại → chờ máy đó bật xong rồi mới nhân bản)", flush=True); said = True
            time.sleep(2)
    try: return fn()
    finally: lk.__exit__()
def _mumu_do(args, timeout, why=""):
    """15/11: lệnh MuMu đi qua chương trình chính (xoá máy, đổi tên…). Chương trình chính kẹt ("mainnx request failed") → mở lại nó
       rồi gửi lại lệnh 1 lần. Trước 15/11 chỉ bật / tắt máy có bước này → tạo máy (đổi Android) / xoá máy lỗi mãi tới khi admin mở lại MuMu."""
    r = _mumurun(args, timeout)
    if _mumu_main_bad(r) and _mumu_main_fix(why or str(args[0])): r = _mumurun(args, timeout)
    return r
def _mumu_stable(tries=6, gap=2.0):
    """15/11: danh sách máy MuMu đọc 2 LẦN LIỀN GIỐNG NHAU. MuMu đang xoá / nhân bản máy khác thì 1 lần đọc có thể THIẾU máy
       → máy đang có bị tưởng là "máy mới" → tạo máy báo lỗi oan. Mãi không ổn định → trả lần đọc đủ máy nhất."""
    prev = None; best = {}
    for k in range(tries):
        cur = _mumu_list()
        if cur and len(cur) > len(best): best = cur
        if cur and prev and set(cur) == set(prev) and all(cur[i]["name"] == prev[i]["name"] for i in cur): return cur
        prev = cur
        if k < tries - 1: time.sleep(gap)
    return best
def _mumu_out_err(r):
    """Lỗi MuMu ghi trong kết quả lệnh (errcode khác 0 đầu tiên, kể cả nằm trong khối con) — không có → ''."""
    o = ((r.stdout or "") + " " + (r.stderr or "")) if r is not None else ""
    for m in re.finditer(r'"errcode"\s*:\s*(-?\d+)', o):
        if int(m.group(1)) == 0: continue
        e = re.search(r'"errmsg"\s*:\s*"([^"]*)"', o[m.end():m.end() + 300])
        return (f"mã {m.group(1)}" + (f" · {e.group(1)}" if e and e.group(1) else ""))[:160]
    return ""
def _mumu_out_new(r):
    """Số máy MỚI mà MuMu ghi trong kết quả create / clone, dạng {"7": {"errcode": 0, …}} → [7]. Kết quả không có dạng đó → []."""
    j = _mumu_json((r.stdout or "") if r is not None else "")
    out = []
    if isinstance(j, dict):
        for k, v in j.items():
            try:
                if str(k).isdigit() and isinstance(v, dict) and int(v.get("errcode", 0) or 0) == 0: out.append(int(k))
            except (TypeError, ValueError): pass
    return out
def _fail_reason(r):
    """1 dòng ngắn: vì sao tạo máy lỗi. In ở dòng CUỐI của lệnh create → cloudphoned gửi nguyên vào Telegram cho admin (trước 15/11 tin
       Telegram chỉ thấy danh sách máy, mất hẳn lý do thật)."""
    o = ((r.stdout or "") + " " + (r.stderr or "")) if r is not None else ""
    if EMU == "mumu":
        e = _mumu_out_err(r)
        if _mumu_main_bad(r):
            return (f"chương trình chính MuMu (MuMuNxMain) không trả lời [{e or 'mainnx request failed'}] — "
                    + ("đã tự mở lại 1 lần mà chưa được, đơn sẽ được tạo lại sau" if "đã mở lại MuMuNxMain" in o else "CHƯA tự mở lại (xem MUMU_MAIN_FIX), đơn sẽ được tạo lại sau"))
        if e: return "MuMu báo " + e
    m = re.search(r"(chưa có máy mẫu[^|]*|không đọc được danh sách[^|]*|MuMu tạo ra Android[^|]*|không tạo được đúng 1 máy[^|·]*|không có sẵn Android[^|]*)", o)
    if m: return m.group(1).strip()[:170]
    if r is not None and r.returncode == 124: return "lệnh tạo máy của giả lập quá giờ (máy chủ đang rất bận)"
    return (o.strip().splitlines() or ["không rõ"])[-1].strip()[-170:]
def _mumu_is_on(idx):
    return bool((_mumu_locked(_mumu_list).get(int(idx)) or {}).get("running"))
def _mumu_main_bad(r):
    """Lệnh MuMu báo {"errcode": -502, "errmsg": "mainnx request failed"}: chương trình chính MuMuNxMain treo / không chạy
       → không bật / tắt được máy nào (12/11 win3: 15 máy ngủ không bật lại được)."""
    o = ((r.stdout or "") + " " + (r.stderr or "")) if r is not None else ""
    return "mainnx" in o.lower() or bool(re.search(r'errcode"?\s*[:=]\s*-502\b', o))
def _mumu_main_up(exe):
    """Mở MuMuNxMain tách khỏi phonectl (phonectl thoát / nhóm tiến trình bị tắt thì MuMu vẫn chạy)."""
    for fl in (0x00000008 | 0x00000200 | 0x01000000, 0x00000008 | 0x00000200):     # DETACHED | NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=fl, close_fds=True); return True
        except OSError: continue
    return False
def _mumu_main_fix(why=""):
    """MuMuNxMain không trả lời → tắt nó rồi mở lại (máy khách đang chạy là tiến trình riêng MuMuNxDevice / MuMuVMMHeadless,
       không tắt theo). Nhiều lệnh cùng gặp lỗi → chỉ 1 lệnh mở lại; 3 phút tối đa 1 lần. True = vừa mở lại / lệnh khác vừa mở lại."""
    exe = os.path.join(MUMU or "", "nx_main", "MuMuNxMain.exe")
    if not MUMU_MAIN_FIX or EMU != "mumu" or not os.path.isfile(exe): return False
    try: lk = _Lock("mumu_main", wait=120); lk.__enter__()
    except RuntimeError: return False
    try:
        try: last = float(open(MUMU_MAIN_F).read().strip() or 0)
        except (OSError, ValueError): last = 0.0
        if time.time() - last < 180: return True
        print(f"   ({EMU_NAME}: chương trình chính không trả lời{' khi ' + why if why else ''} → mở lại MuMuNxMain)", flush=True)
        subprocess.run(["taskkill", "/IM", "MuMuNxMain.exe", "/F"], capture_output=True, creationflags=NOWIN)
        time.sleep(3)
        if _WIN and PRIV_GUARD and not _is_admin():     # 17/11e2: còn MuMuNxMain chạy quyền Admin (lệnh này quyền thường không tắt được)
            for _k in range(3):
                left = [p for p in _img_pids(("mumunxmain.exe",)) if _elev(p) is not False]
                if not left: break
                time.sleep(2)
            if left:
                try: open(MUMU_MAIN_F, "w").write(str(time.time()))
                except OSError: pass
                print("   (không tắt được MuMuNxMain — nó chạy quyền Admin còn lệnh này thì không → KHÔNG mở thêm bản thứ 2 (sẽ lẫn quyền, "
                      "không bật được máy nào). Chạy lệnh bằng Terminal (Admin))", flush=True)
                return False
        up = _mumu_main_up(exe)
        try: open(MUMU_MAIN_F, "w").write(str(time.time()))
        except OSError: pass
        time.sleep(MUMU_MAIN_SETTLE)                       # chương trình chính cần ~10–20 giây mới nhận lệnh
        return up
    finally: lk.__exit__()
# 16/11 — KHÁCH TỰ ĐỔI FPS (web / app gọi cloudphone_set_fps → ô fps của cloud_phones). Giả lập chỉ cho ghi "khung/giây tối đa" lúc máy
# TẮT → mỗi lần BẬT máy (start / restart / wake / tự bật lại sau khi văng) đọc FPS khách đang chọn rồi ghi TRƯỚC khi bật.
# Hình phát ra thì đổi ngay ở lần mở máy kế (bluestream đọc ô fps mỗi lần mở); FPS TRONG game đổi sau lần khởi động lại máy.
_FPS_FORCE = {}            # số máy → FPS chính lệnh này vừa đặt (reconfig) — ưu tiên hơn web
def _fps_wanted(idx):
    """(tên máy, FPS khách đang chọn) của máy MuMu số idx · None nếu không phải máy khách cp_… / không biết FPS.
       Đọc web tối đa 6 giây (gọi NGOÀI khoá memuc); không đọc được → theo phones.json. Web khác phones.json → ghi lại phones.json."""
    try:
        if EMU != "mumu": return None
        i = int(idx); st = load()
        p = next((x for x in st["phones"] if str(x.get("idx", "")) == str(i) and str(x.get("name", "")).startswith("cp_")), None)
        if not p: return None
        nm = p["name"]
        if i in _FPS_FORCE: return nm, clamp_fps(_FPS_FORCE[i])
        fps = None
        try:
            import urllib.parse
            rows = _sb_get("cloud_phones?select=fps&container=eq." + urllib.parse.quote(nm)
                           + "&status=in.(active,expired,pending,creating)&order=created_at.desc&limit=1", timeout=6) or []
            if rows and rows[0].get("fps"): fps = clamp_fps(rows[0]["fps"])
        except Exception: pass
        if fps is None: return (nm, clamp_fps(p["fps"])) if p.get("fps") else None
        if not p.get("fps") or clamp_fps(p["fps"]) != fps:
            st = load(); q = rec(nm, st)
            if q: q["fps"] = fps; save(st)
        return nm, fps
    except Exception: return None
def _mumu_start(idx, timeout, locked=False):
    """Bật 1 máy MuMu: khoá memuc CHỈ lúc ghi cài đặt + gửi lệnh launch; chờ máy lên (≤ MUMU_START_WAIT giây) ở NGOÀI khoá.
       MuMu báo mainnx → mở lại chương trình chính rồi gửi launch thêm 1 lần. locked=True: đang trong khoá (gọi từ _mumu)."""
    idx = str(idx)
    want = None if locked else _fps_wanted(idx)           # (tên máy, FPS khách chọn) — đọc web ở NGOÀI khoá
    def launch():
        v = _mumu_list().get(int(idx)) or {}
        if v.get("running"): return None
        fps = want[1] if want and want[0] == str(v.get("name", "")) else None      # đúng máy đó (số máy không bị đổi giữa chừng) mới ghi
        if MUMU_PERF or fps:
            try: _mumu_perf(idx, fps)                     # giữ app chạy nền / không tự hạ FPS / card rời / FPS khách chọn — ghi lúc máy đang tắt
            except Exception: pass
        return _mumurun(["control", "-v", idx, "launch"], timeout)
    if locked:                                            # đường cũ (trong khoá): gửi lệnh rồi chờ ngắn trong khoá
        r = launch()
        if r is None: return _ok("start ok")
        for _ in range(15):
            if (_mumu_list().get(int(idx)) or {}).get("running"): return _ok("start ok")
            time.sleep(2)
        return subprocess.CompletedProcess([], 1, r.stdout, (r.stderr or "") + " start vm failed")
    r = _mumu_locked(launch)
    if r is None: _cyc_clear(); return _ok("start ok (đã chạy sẵn)")
    if _mumu_main_bad(r) and _mumu_main_fix(f"bật máy #{idx}"):
        r = _mumu_locked(launch)
        if r is None: _cyc_clear(); return _ok("start ok")
    _cyc_clear()                                          # 16/11e: đã gửi lệnh bật → lệnh nhân bản đang nhường được chạy tiếp
    t0 = time.time()
    while time.time() - t0 < MUMU_START_WAIT:
        time.sleep(MUMU_POLL)
        if _mumu_is_on(idx): return _ok("start ok")
    return subprocess.CompletedProcess([], 1, r.stdout, (r.stderr or "") + " start vm failed")
def _mumu_stop(idx, timeout, locked=False):
    """Tắt 1 máy MuMu: khoá memuc chỉ lúc gửi lệnh shutdown; chờ máy tắt (≤ 40 giây) ở ngoài khoá. MuMu báo mainnx → mở lại rồi gửi lại."""
    idx = str(idx)
    def shut():
        _stop_marks(idx)                                  # 16/11e: dấu "đang khởi động lại" ghi đúng lúc tắt thật
        _guest_sync(idx)                                  # 16/11k2: Android ghi hết dữ liệu xuống đĩa rồi mới tắt ngang
        return _mumurun(["control", "-v", idx, "shutdown"], timeout)
    if locked:
        shut()
        for _ in range(20):
            if not (_mumu_list().get(int(idx)) or {}).get("running"): break
            time.sleep(2)
        return _ok("stop ok")
    r = _mumu_locked(shut)
    if _mumu_main_bad(r) and _mumu_main_fix(f"tắt máy #{idx}"):
        r = _mumu_locked(lambda: _mumurun(["control", "-v", idx, "shutdown"], timeout))
    for _ in range(20):
        if not _mumu_is_on(idx): break
        time.sleep(2)
    return _ok("stop ok")
def _mumu_perf(idx, fps=None):
    """Ghi MUMU_PERF (+ FPS khách chọn, nếu có) cho 1 máy MuMu (máy phải đang tắt). Trả số khoá vừa ghi (0 = đã đúng sẵn)."""
    cur = _mumu_json(_mumurun(["setting", "-v", idx, "-a"], 60).stdout) or {}
    want = {k: val for k, val in MUMU_PERF.items() if k in cur and str(cur.get(k)).strip().lower() != val}
    if fps and MUMU_FPS_CAP > 0 and int(fps) > MUMU_FPS_CAP:
        print(f"   (máy #{idx}: FPS khách chọn {int(fps)} → ghi {MUMU_FPS_CAP} theo MUMU_FPS_CAP)", flush=True); fps = MUMU_FPS_CAP
    if fps:
        fk = "max_frame_rate" if "max_frame_rate" in cur else next((k for k in sorted(cur, key=len) if k.startswith("max_frame_rate")), None)
        if fk and _fnum(cur.get(fk)) != float(int(fps)):
            want["fps"] = int(fps)
            print(f"   (máy #{idx}: khung/giây trong máy {cur.get(fk)} → {int(fps)} theo lựa chọn của khách)", flush=True)
    if want: _MUMU_KEYS.pop(str(idx), None); _mumu_set(str(idx), want)
    return len(want)
def _mumu(a, timeout):
    """Dịch lệnh memuc → MuMu. Trả kết quả GIỐNG memuc để phần còn lại của tool dùng y nguyên."""
    a = [str(x) for x in a]; c = a[0]
    def ix(): return a[a.index("-i") + 1] if "-i" in a else "0"
    def running(i): return (_mumu_list().get(int(i)) or {}).get("running")
    if c == "listvms":
        L = _mumu_list(); run_only = "--running" in a
        return _ok("\n".join(f"{i},{x['name']},0,{1 if x['running'] else 0},{x['pid']}" for i, x in sorted(L.items()) if x["running"] or not run_only))
    if c == "create":                                     # create <bản android>: có máy mẫu tpl_a<bản> → nhân bản, không thì tạo mới
        # 15/11 — ĐỔI ANDROID lỗi "chưa tạo được máy mới sau 3 lần" (win4): MuMu trả "mainnx request failed" (-502) khi nhân bản =
        # chương trình chính MuMuNxMain kẹt; bản cũ không tự mở lại ở bước này → tạo lần nào lỗi lần đó. Giờ: -502 → mở lại
        # MuMuNxMain → nhân bản lại 1 lần. Thêm: đánh dấu "lệnh dài" (lệnh khác chờ, không tắt lệnh nhân bản giữa chừng), nhân bản
        # được tới 15 phút khi máy chủ bận, đọc danh sách ổn định trước / sau, lỗi thì ghi rõ MuMu báo gì.
        ver = a[1] if len(a) > 1 else DEF_ANDROID
        def keep(): _long_mark(True); _lock_touch("memuc"); _lock_touch("memu")
        _long_mark(True)
        try:
            L0 = _mumu_stable()
            if not L0:                                    # không đọc được danh sách → KHÔNG tạo (đọc sau sẽ tưởng mọi máy có sẵn là máy mới → nhận nhầm máy của chủ)
                return subprocess.CompletedProcess([], 1, "", "không đọc được danh sách máy MuMu — chưa tạo máy")
            before = set(L0); tpl = next((i for i, x in L0.items() if x["name"] == tpl_name(ver)), None)
            fresh = lambda L: sorted(i for i in set(L) - before if not str(L[i]["name"]).startswith(("cp_", "spare_")))   # cp_… / spare_… = máy ĐÃ CÓ (lần đọc trước thiếu)
            if tpl is not None and L0[tpl].get("running"):   # máy mẫu đang BẬT thì MuMu không nhân bản được → tắt máy mẫu trước
                print(f"   (máy mẫu {tpl_name(ver)} đang bật → tắt rồi mới nhân bản)", flush=True)
                _mumu_stop(tpl, 120, locked=True)
            def go(): return _mumurun(["clone", "-v", tpl], max(int(timeout), MUMU_CLONE_T)) if tpl is not None else _mumurun(["create"], timeout)
            vdir = os.path.join(MUMU or "", "vms")       # mỗi máy MuMu là 1 thư mục con ở đây → có thư mục MỚI = MuMu đang / đã chép máy mới
            def vnow():
                try: return {x for x in os.listdir(vdir) if os.path.isdir(os.path.join(vdir, x))}
                except OSError: return None
            d0 = vnow()
            keep(); t0 = time.time(); r = go(); fixed = False; copying = False
            if _mumu_main_bad(r):                         # chương trình chính MuMu báo không trả lời
                time.sleep(3); L1 = _mumu_list(); d1 = vnow()
                copying = d0 is not None and d1 is not None and bool(d1 - d0)
                if L1 and fresh(L1): pass                 # máy mới đã có dù MuMu báo lỗi → dùng luôn
                elif copying:                             # MuMu đang chép máy mới (chỉ là trả lời chậm) → KHÔNG tắt MuMu, chờ máy hiện ra
                    print(f"   (MuMu báo chậm trả lời nhưng đang chép máy mới: {', '.join(sorted(d1 - d0))[:80]} → chờ)", flush=True)
                else:                                     # chưa hề tạo gì = kẹt thật → mở lại MuMuNxMain → nhân bản lại 1 lần
                    keep()
                    if _mumu_main_fix(f"nhân bản máy mẫu Android {ver}"): fixed = True; keep(); r = go()
            keep()
            slow = r.returncode == 124 or copying         # lệnh nhân bản quá giờ / MuMu vẫn đang chép → chờ máy mới lâu hơn
            err = "" if copying else _mumu_out_err(r)
            hint = [i for i in _mumu_out_new(r) if i not in before]
            new = []; seen = None; t_end = time.time() + (600 if slow else 20 if err else 150)
            while time.time() < t_end:                    # máy mới có thể hiện trễ; phải thấy ĐÚNG 1 máy mới 2 lần đọc liền (không tin 1 lần đọc thiếu)
                L1 = _mumu_list()
                if L1:
                    if len(hint) == 1 and hint[0] in L1: new = hint; break
                    cand = fresh(L1)
                    if len(cand) == 1 and cand == seen: new = cand; break
                    seen = cand if len(cand) == 1 else None
                keep(); time.sleep(3)
            if len(new) != 1:                             # 0 hoặc nhiều hơn 1 máy "mới" → không chắc máy nào là của mình → không dùng
                n_new = len(fresh(_mumu_list() or {}))
                why = err or (f"MuMu chép máy mới chưa xong sau {int(time.time() - t0)} giây" if slow else "")
                return subprocess.CompletedProcess([], 1, r.stdout, (r.stderr or "") + f" MuMu không tạo được đúng 1 máy (thấy {n_new} máy mới sau {int(time.time() - t0)} giây)"
                                                   + (f" · MuMu báo: {why}" if why else "") + (" · đã mở lại MuMuNxMain 1 lần" if fixed else ""))
            got = ""
            for _ in range(5):                            # thông tin máy mới có thể chưa đủ ngay
                got = _mumu_major(_mumu_info().get(new[0]))      # MuMu 6 tạo mới mặc định Android 15 → khách mua bản khác phải nhân bản máy mẫu đúng bản
                if got: break
                time.sleep(2)
            if got and got != str(ver):
                _mumu_do(["delete", "-v", new[0]], timeout, "xoá máy sai bản")  # đúng 1 máy vừa tạo (đã kiểm ở trên) → xoá, không giao nhầm bản cho khách
                return subprocess.CompletedProcess([], 1, r.stdout, f"MuMu tạo ra Android {got}, không phải Android {ver} — cần máy mẫu {tpl_name(ver)} (Android {ver})")
            return _ok(f"index: {new[0]}")
        finally: _long_mark(False)
    if c == "rename":
        r = _mumu_do(["rename", "-v", ix(), "-n", a[-1]], timeout, "đổi tên máy")
        if (_mumu_list().get(int(ix())) or {}).get("name") != a[-1]: r = _mumurun(["rename", "--vmindex", ix(), "--name", a[-1]], timeout)
        return r
    if c in ("start", "stop"):                            # memuc() chạy 2 lệnh này bằng _mumu_start / _mumu_stop (không giữ khoá lúc chờ)
        return (_mumu_start if c == "start" else _mumu_stop)(ix(), timeout, locked=True)
    if c == "stopall": return _mumurun(["control", "-v", "all", "shutdown"], timeout)
    if c == "remove":
        if int(ix()) not in _mumu_list(): return subprocess.CompletedProcess([], 1, "", f"MuMu không có máy #{ix()} — không xoá")
        r = _mumu_do(["delete", "-v", ix()], timeout, "xoá máy")
        if int(ix()) not in _mumu_list(): return _ok("remove ok")
        e = _mumu_out_err(r)
        return subprocess.CompletedProcess([], 1, r.stdout, "remove failed" + (f" · MuMu báo: {e}" if e else ""))
    if c == "setconfigex":
        k, v = a[-2], a[-1]
        if k == "memory": _mumu_set(ix(), {"mem": float(v) / 1024})
        elif k == "cpus": _mumu_set(ix(), {"cpu": v})
        elif k == "enable_su": _mumu_set(ix(), {"root": 1})
        elif k == "fps": _mumu_set(ix(), {"fps": v})
        return _ok()
    if c == "getconfigex":
        allk = _mumu_json(_mumurun(["setting", "-v", ix(), "-a"], 60).stdout) or {}
        if a[-1] == "cpus": return _ok("Value: " + str(next((allk[k] for k in allk if k.startswith("performance_cpu")), "?")))
        return _ok("Value: 1")
    if c == "clone": return _mumurun(["clone", "-v", ix()], timeout)
    return _ok()
_IDX_CHECK = ("remove", "rename")                 # lệnh làm mất / đổi máy → phải chắc máy số đó CÓ THẬT trước khi chạy
def _proc_ct(pid):
    """16/11e: giờ (giây, Unix) chương trình số pid được chạy — cùng số PID mà khác giờ chạy = chương trình KHÁC (Windows dùng lại số).
       Không đọc được → None (khi đó chỉ kiểm PID như cũ)."""
    try:
        pid = int(pid)
        if os.name == "nt":
            k = ctypes.windll.kernel32; h = k.OpenProcess(0x1000, False, pid)
            if not h: return None
            try:
                c, e_, kt, ut = (ctypes.c_ulonglong() for _ in range(4))
                if not k.GetProcessTimes(ctypes.c_void_p(h), ctypes.byref(c), ctypes.byref(e_), ctypes.byref(kt), ctypes.byref(ut)): return None
                return c.value / 1e7 - 11644473600.0
            finally: k.CloseHandle(ctypes.c_void_p(h))
        st = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
        bt = next(float(l.split()[1]) for l in open("/proc/stat") if l.startswith("btime"))
        return bt + int(st[19]) / os.sysconf("SC_CLK_TCK")
    except Exception: return None
_ME = {}
def _who():
    """'PID GIỜ_CHẠY' của chính lệnh này — ghi vào dấu để chương trình khác nhận đúng."""
    if "w" not in _ME:
        ct = _proc_ct(os.getpid()); _ME["w"] = f"{os.getpid()} {int(ct)}" if ct else str(os.getpid())
    return _ME["w"]
def _alive_who(s):
    """Dấu 'PID [GIỜ_CHẠY]' còn là chương trình ĐANG CHẠY (không phải số PID đã bị dùng lại)?"""
    p = str(s or "").split()
    if not p or not p[0].isdigit() or not _pid_alive(p[0]): return False
    if len(p) > 1 and p[1].lstrip("-").isdigit():
        ct = _proc_ct(p[0])
        if ct is not None and abs(ct - int(p[1])) > 3: return False
    return True
def _mine_who(s): return str(s or "").split()[:1] == [str(os.getpid())]
_RS_PEND = []                      # tên máy sắp TẮT để bật lại — dấu "đang khởi động lại" ghi lúc tắt thật (_stop_marks)
def _restart_mark(name):
    """16/11c: máy này sắp được TẮT rồi BẬT lại (khởi động lại / nâng cấu hình / đổi độ phân giải-FPS / đổi chế độ vẽ / sửa máy kẹt)
       → ghi redroid/restart_<tên>.json (mốc + mã chương trình). Phát hình (bluestream) thấy dấu: khách mở máy giữa chừng được
       báo "đang khởi động lại, tự vào khi máy lên" thay vì lỗi "không lấy được hình". Dấu tự hết khi Android lên xong / quá 5 phút.
       16/11e: CHỈ GHI LÚC TẮT THẬT (lệnh tắt được gửi). Trước: ghi ngay lúc nhận lệnh → lệnh còn xếp hàng (chờ máy chủ tạo máy khác
       xong, chờ lượt bật) mà máy vẫn chạy, khách đã bị báo "đang khởi động lại" và không vào được máy."""
    if not name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(name)): return
    if name not in _RS_PEND: _RS_PEND.append(name)
def _restart_write(name):
    try:
        os.makedirs(os.path.join(HOME, "redroid"), exist_ok=True)
        ct = _proc_ct(os.getpid())
        with open(os.path.join(HOME, "redroid", f"restart_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(dict({"t": time.time(), "pid": os.getpid()}, **({"ct": int(ct)} if ct else {})), f)
    except (OSError, TypeError, ValueError): pass
def _op_file(iv): return os.path.join(HOME, "redroid", f"op_{iv}.mark")
_OP_MINE = set()
def _op_mark(iv):
    """16/11b: lệnh này vừa TẮT máy số iv (khởi động lại / nâng cấp / đổi cấu hình / root / cho ngủ…) → ghi dấu "đang làm dở" + mã chương trình.
       Lệnh chạy xong (thoát bình thường) → tự gỡ dấu của mình; bị ngắt giữa chừng → dấu của chương trình đã tắt không còn hiệu lực."""
    try:
        os.makedirs(os.path.join(HOME, "redroid"), exist_ok=True)
        with open(_op_file(iv), "w") as f: f.write(_who())
        if not _OP_MINE: atexit.register(lambda: [_op_unmark(x) for x in list(_OP_MINE)])
        _OP_MINE.add(str(iv))
    except OSError: pass
def _op_unmark(iv):
    try:
        f = _op_file(iv)
        if _mine_who(open(f).read()): os.remove(f)
    except OSError: pass
def _op_busy(iv):
    """Có lệnh phonectl KHÁC (còn đang chạy) vừa tắt máy số iv và chưa làm xong? Dấu của chương trình đã tắt / quá 15 phút → không tính."""
    try:
        f = _op_file(iv)
        if time.time() - os.path.getmtime(f) > 900: return False
        w = open(f).read().strip()
        return not _mine_who(w) and _alive_who(w)
    except (OSError, ValueError): return False
# ---------- 16/11e: KHỞI ĐỘNG LẠI GỌN (tắt → bật liền) ----------
# Lệnh nhân bản máy mẫu (tạo máy cho đơn mới) giữ khoá giả lập vài phút. Trước: khách bấm khởi động lại đúng lúc đó → máy bị TẮT rồi
# lệnh BẬT phải chờ nhân bản xong (vài phút, nhiều đơn liền thì lâu hơn) → khách thấy "đang khởi động lại… đã 348 giây".
# Giờ: lúc TẮT máy để bật lại, lệnh ghi redroid/cycle_<pid>.flag → lệnh nhân bản thấy cờ thì nhường (tối đa CYC_WAIT giây) tới khi
# máy đó đã được gửi lệnh bật. Cờ tự gỡ lúc gửi lệnh bật / lệnh thoát / chương trình đã tắt / quá 4 phút.
CYC_WAIT = 300
_CYC = {"on": False}
def _cyc_file(): return os.path.join(HOME, "redroid", f"cycle_{os.getpid()}.flag")
def _cyc_set():
    try:
        os.makedirs(os.path.join(HOME, "redroid"), exist_ok=True)
        with open(_cyc_file(), "w") as f: f.write(_who())
        if not _ME.get("cyc_ax"): _ME["cyc_ax"] = True; atexit.register(_cyc_clear)
    except OSError: pass
def _cyc_clear():
    try: os.remove(_cyc_file())
    except OSError: pass
def _cyc_busy():
    """Có máy khách ĐANG khởi động lại (đã tắt, chưa gửi lệnh bật) của lệnh KHÁC còn chạy?"""
    for f in glob.glob(os.path.join(HOME, "redroid", "cycle_*.flag")):
        try:
            if time.time() - os.path.getmtime(f) > 240: continue
            w = open(f).read().strip()
            if w and not _mine_who(w) and _alive_who(w): return True
        except (OSError, ValueError): pass
    return False
@contextlib.contextmanager
def _cycle():
    """Khối TẮT → BẬT lại 1 máy: lúc tắt thật thì dựng cờ (lệnh nhân bản nhường), gửi lệnh bật xong / ra khỏi khối thì gỡ."""
    _CYC["on"] = True
    try: yield
    finally: _CYC["on"] = False; _cyc_clear()
def _stop_marks(iv):
    """Gọi ĐÚNG LÚC gửi lệnh tắt máy số iv (đã có khoá giả lập): dấu "lệnh đang làm dở" + dấu "đang khởi động lại" của máy chờ
       + cờ khởi động lại gọn (nếu đang trong khối _cycle)."""
    _op_mark(iv)
    while _RS_PEND: _restart_write(_RS_PEND.pop(0))
    if _CYC["on"]: _cyc_set()
# ---------------------------------------------------------------- 17/11e: QUYỀN ADMIN CỦA GIẢ LẬP
# Bảng CloudBlue chạy bằng quyền Admin (tác vụ BlueRoblox, RunLevel Highest) → mọi máy ảo được bật bằng quyền Admin. Bật máy từ cửa
# sổ KHÔNG Admin (lệnh A dán vào PowerShell thường, mở MuMu bằng tay…) → giả lập chạy lẫn 2 quyền → MuMu hiện "Unable to start the
# Android Device — There is currently a conflict, unable to start with administrator privileges" và KHÔNG bật được máy nào nữa (máy ngủ
# không thức, máy mới không lên) tới khi máy chạy sai quyền tắt hết (17/11 sau khi chạy lệnh A). Nay: phonectl KHÔNG Admin mà bảng /
# giả lập đang chạy Admin → không bật máy nào, báo rõ · phonectl Admin mà chương trình chính MuMu chạy quyền thường → mở lại nó ·
# `phonectl quyen` xem quyền từng máy · `phonectl quyen --sua` (Admin) khởi động lại đúng các máy đang chạy sai quyền. Tắt: PRIV_GUARD=0
PRIV_GUARD = str(CONF.get("PRIV_GUARD", "1")).strip() != "0"
PRIV_VER = "17/11e2"          # 17/11e2: chỉ chặn khi người gõ lệnh · thấy cả MuMuVMMSVC · --sua tắt êm cùng lúc, bật theo lượt, kiểm lại
PCTL_SUB = "22/11a"           # 17/11e3: danh sách máy không bao giờ bị ghi đè khi đọc lỗi · đặt lại tên máy bị mất tên · quyen không đếm trùng
                              # 17/11e4: kiểm / sửa lẫn quyền chỉ trên máy chủ MuMu (LDPlayer / MEmu không có lỗi này → không đụng máy)
                              # 17/11f: máy chủ bật lại → bật máy khách SONG SONG, máy có khách đang chờ lên trước, máy treo lúc bật tự bật lại ·
                              #         tắt êm (Android tự tắt) trước khi khởi động lại máy chủ · tự dọn máy khách đã huỷ kể cả máy mất tên
                              # 17/11g: máy chủ bị TẮT NGANG làm hỏng file hệ thống Android (roles.xml rỗng…) → máy không lên: tự đổi tên file
                              #         hỏng, Android tự tạo lại (BOOT_FIX) · lệnh khammay: vì sao máy không lên (chỉ đọc)
                              # 17/11h: tự TẮT TIẾNG loa Windows của máy chủ (HOST_MUTE, 10 phút kiểm 1 lần) · lệnh tattieng
                              # 18/11a: máy khách chỉ TỰ NGỦ khi 18 GIỜ liền không ai mở máy + không thấy máy có việc (IDLE_STOP_H; trước 30 phút)
                              # 18/11b: BỘ NHỚ máy MỚI: MuMu "chế độ ổ nhỏ" → /data chỉ 2,9GB → nới bằng resize2fs lúc lên lần đầu
                              # 19/11a: bộ nhớ MIỄN PHÍ theo cấu hình (RAM < 4GB → 8GB · 4–7GB → 13GB · từ 8GB → 16GB: DISK_TIERS) ·
                              #         create --disk N · lệnh disk TÊN --gb N (khách MUA THÊM bộ nhớ) · máy cũ để nguyên
                              # 22/11a: 🌐 PROXY RIÊNG TỪNG MÁY (khách dán IP:Port:User:Pass) — cbproxy trong máy (root, iptables) · lệnh proxy /
                              #         proxykeep · tự bật lại sau khi máy bật / khởi động lại / mỗi 5 phút · proxy chết → máy tự đi mạng thường
_WIN = os.name == "nt"
EMU_IMGS = {"mumu": ("mumunxmain.exe", "mumunxdevice.exe", "mumuvmmheadless.exe", "mumuplayer.exe", "mumumultiplayer.exe", "mumuvmmsvc.exe"),
            "ld": ("dnplayer.exe", "ld9boxheadless.exe", "ldboxheadless.exe", "dnmultiplayer.exe"),
            "memu": ("memu.exe", "memuheadless.exe", "memuconsole.exe")}
_PRIV = {}
_PNAME = {"mumunxmain.exe": "chương trình chính", "mumuvmmsvc.exe": "dịch vụ máy ảo"}     # tiến trình "chung" của MuMu quyết định quyền bật máy
                                                  # (17/11e4: cửa sổ quản lý nhiều máy do chủ máy mở tay không tính — không gây xung đột)


def _is_admin():
    if not _WIN: return False
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False


def _elev(pid):
    """Tiến trình pid chạy bằng quyền Admin? True · False (quyền thường) · None (đã thoát / không đọc được).
       Không phải Admin mà bị từ chối đọc quyền của tiến trình → coi là Admin (Windows không cho cửa sổ thường đọc tiến trình Admin)."""
    if not _WIN: return None
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True); a = ctypes.WinDLL("advapi32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p; k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        a.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
        a.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
        hp = k.OpenProcess(0x1000, False, int(pid))                      # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp: return None
        try:
            tok = ctypes.c_void_p()
            if not a.OpenProcessToken(hp, 0x0008, ctypes.byref(tok)):    # TOKEN_QUERY
                if ctypes.get_last_error() != 5 or _is_admin(): return None
                sid = ctypes.c_ulong(0)                                     # 17/11e2: dịch vụ Windows (phiên 0, chạy SYSTEM) → không biết
                if k.ProcessIdToSessionId(ctypes.c_ulong(int(pid)), ctypes.byref(sid)) and sid.value == 0: return None
                return True
            try:
                e = ctypes.c_ulong(0); n = ctypes.c_ulong(0)
                if not a.GetTokenInformation(tok, 20, ctypes.byref(e), 4, ctypes.byref(n)): return None   # TokenElevation
                return bool(e.value)
            finally: k.CloseHandle(tok)
        finally: k.CloseHandle(hp)
    except Exception: return None


def _img_pids(imgs):
    """{pid: tên file} các tiến trình có tên (chữ thường) trong imgs — tasklist, không cần quyền Admin."""
    out = {}
    if not _WIN: return out
    try:
        import csv, io
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=30, creationflags=NOWIN)
        for row in csv.reader(io.StringIO((r.stdout or b"").decode("utf-8", "replace"))):
            if len(row) >= 2 and row[0].strip().lower() in imgs and row[1].strip().isdigit(): out[int(row[1])] = row[0].strip()
    except Exception: pass
    return out


def _svc_pids():
    """PID bảng CloudBlue + dịch vụ (panel / cloudphoned / bluestream / cpapi) — dòng lệnh đọc bằng PowerShell."""
    if not _WIN: return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -match "
                            "'(panel|cloudphoned|bluestream|cpapi)\\.py') -or $_.Name -eq 'BlueRobloxServer.exe' } | ForEach-Object { $_.ProcessId }"],
                           capture_output=True, timeout=40, creationflags=NOWIN)
        return [int(x) for x in (r.stdout or b"").decode("ascii", "replace").split() if x.isdigit() and int(x) != os.getpid()]
    except Exception: return []


def _priv_block():
    """'' = bật máy được · câu báo = phonectl KHÔNG Admin mà bảng CloudBlue / giả lập đang chạy bằng quyền Admin (bật từ đây → giả lập
       báo xung đột quyền, không bật được máy nào nữa). Nhớ 60 giây.
       17/11e2: CHỈ chặn khi NGƯỜI gõ lệnh trong cửa sổ PowerShell — bảng / dịch vụ / lệnh A gọi phonectl (không có cửa sổ) → không
       chặn, chạy như trước 17/11e (máy chủ có bảng chạy quyền thường không bao giờ bị chặn oan).
       17/11e4: chỉ máy chủ MuMu (LDPlayer / MEmu không có lỗi xung đột quyền)."""
    if not _WIN or not PRIV_GUARD or EMU != "mumu": return ""
    try: tty = bool(sys.stdout is not None and sys.stdout.isatty())
    except Exception: tty = False
    if not tty: return ""
    now = time.time()
    if now - _PRIV.get("t", 0) < 60: return _PRIV.get("v", "")
    v = ""
    try:
        if not _is_admin():
            hit = next((p for p in _img_pids(EMU_IMGS.get(EMU, ())) if _elev(p)), None) or next((p for p in _svc_pids() if _elev(p)), None)
            if hit:
                v = ("QUYEN: lệnh này đang chạy KHÔNG có quyền Admin mà bảng CloudBlue / giả lập đang chạy bằng quyền Admin — bật máy từ đây "
                     f"{EMU_NAME} sẽ báo xung đột quyền và không bật được máy nào nữa. Mở PowerShell bằng quyền Admin (chuột phải Start → "
                     "Terminal (Admin)) rồi chạy lại.")
    except Exception: v = ""
    _PRIV.update(t=now, v=v)
    return v


def _priv_main_fix():
    """phonectl chạy Admin (dịch vụ bật máy) mà: chương trình chính MuMu (MuMuNxMain) chạy quyền thường (ai đó mở MuMu bằng tay / bật
       từ cửa sổ thường) → mở lại nó bằng quyền Admin TRƯỚC khi bật máy (máy đang chạy không bị tắt) · 17/11e2: dịch vụ máy ảo MuMu
       (MuMuVMMSVC) chạy quyền thường mà KHÔNG máy ảo nào chạy → tắt nó (bật máy kế mở lại bằng quyền Admin) · có máy ảo chạy quyền
       thường → báo rõ 1 dòng (10 phút / lần; sửa = lệnh A bằng Terminal (Admin)) — KHÔNG tự khởi động lại máy khách. Nhớ 60 giây."""
    if not _WIN or not PRIV_GUARD or EMU != "mumu" or not _is_admin(): return False
    now = time.time()
    if now - _PRIV.get("mt", 0) < 60: return False
    _PRIV["mt"] = now
    pr = {p: im.lower() for p, im in _img_pids(("mumunxmain.exe", "mumuvmmsvc.exe", "mumuvmmheadless.exe")).items()}
    wrong = {p: im for p, im in pr.items() if _elev(p) is False}
    if not wrong: return False
    did = False
    if "mumunxmain.exe" in wrong.values():
        did = bool(_mumu_main_fix("chương trình chính MuMu chạy KHÔNG quyền Admin (lẫn quyền → không bật được máy)"))
    hl = [p for p, im in wrong.items() if im == "mumuvmmheadless.exe"]
    if hl:
        if now - _PRIV.get("wt", 0) > 600:
            _PRIV["wt"] = now
            print(f"⚠ QUYEN: {len(hl)} máy ảo đang chạy KHÔNG quyền Admin (bật từ cửa sổ thường) → {EMU_NAME} có thể báo xung đột quyền, "
                  "không bật được máy khác. Sửa: chuột phải Start → Terminal (Admin) → dán lệnh A (bước 4b bật lại đúng quyền).", flush=True)
    elif "mumuvmmsvc.exe" in wrong.values() and "mumuvmmheadless.exe" not in pr.values():
        for p, im in wrong.items():
            if im == "mumuvmmsvc.exe": subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True, creationflags=NOWIN)
        print(f"   ({EMU_NAME}: dịch vụ máy ảo MuMuVMMSVC chạy quyền thường mà không máy nào dùng → đã tắt, bật máy sẽ mở lại bằng quyền Admin)",
              flush=True)
        time.sleep(2); did = True
    return did


def _hl_info(pids):
    """{pid: (số máy | -1, pid cha)} các tiến trình MuMuVMMHeadless trong pids — số máy đọc từ dòng lệnh (--comment
       MuMuPlayer-12.0-<số>). MuMu chạy 2 tiến trình / máy (vỏ + máy thật, cùng dòng lệnh) → dùng để gộp. Không đọc được → {}."""
    out = {}
    if not _WIN or not pids: return out
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'MuMuVMMHeadless.exe' } | ForEach-Object { '{0}|{1}|{2}' -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }"],
                           capture_output=True, timeout=40, creationflags=NOWIN)
        for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines():
            q = ln.strip().split("|", 2)
            if len(q) < 3 or not q[0].isdigit() or int(q[0]) not in pids: continue
            cl = q[2]
            m = re.search(r"--comment\s+\"?[^\s\"]*?-(\d+)\"?(?:\s|$)", cl) or re.search(r"MuMuPlayer[^\s\"\\]*?-(\d+)(?![\d.])", cl)
            out[int(q[0])] = (int(m.group(1)) if m else -1, int(q[1]) if q[1].isdigit() else 0)
    except Exception: pass
    return out
def _hl_idx(pids): return {p: i for p, (i, _) in _hl_info(pids).items() if i >= 0}


def _vm_label(i, nm, pids):
    return f"{nm} (#{i})" if i is not None and int(i) >= 0 else f"{nm} (pid {pids[0] if pids else '?'})"


def _priv_report():
    """(phonectl Admin?, quyền bảng / dịch vụ, [(pid, tên file, quyền)] tiến trình chung của giả lập (chương trình chính, dịch vụ máy
       ảo…), [(số máy, tên, quyền, [pid])] máy đang chạy). Quyền: True / False / None. 17/11e2: MuMu — máy ảo đang chạy mà MuMuManager
       không báo vẫn được thấy qua tiến trình MuMuVMMHeadless (số máy đọc từ dòng lệnh; không đọc được → số -1)."""
    me = _is_admin()
    sv = [_elev(p) for p in _svc_pids()]
    svc = True if any(x is True for x in sv) else (False if any(x is False for x in sv) else None)
    allp = {p: im.lower() for p, im in _img_pids(EMU_IMGS.get(EMU, ())).items()}
    main = [(p, im, _elev(p)) for p, im in sorted(allp.items()) if im in _PNAME]
    vms = []
    try:
        if EMU == "mumu":
            try: info = _mumu_info() or {}
            except Exception: info = {}
            seen = set()
            for i, v in sorted(info.items()):
                pids = [int(x) for x in (v.get("headless_pid"), v.get("pid")) if str(x).strip().lstrip("-").isdigit() and int(x) > 0]
                if not _mumu_running(v): continue
                seen.update(pids)
                e = next((x for x in (_elev(p) for p in pids) if x is not None), None)    # máy ảo (MuMuVMMHeadless) quyết định, không đọc được → cửa sổ
                vms.append((i, str(v.get("name", "")), e, pids))
            extra = sorted(p for p, im in allp.items() if im == "mumuvmmheadless.exe" and p not in seen)
            if extra:
                hi = _hl_info(set(extra)); byidx = {}
                try:
                    for x in load().get("phones", []):
                        if str(x.get("idx", "")).strip().isdigit(): byidx[int(x["idx"])] = str(x.get("name", ""))
                except Exception: pass
                pos = {i: k for k, (i, _, _, _) in enumerate(vms)}                       # số máy → vị trí trong vms
                own = {q: k for k, (_, _, _, pp) in enumerate(vms) for q in pp}         # pid → vị trí
                for p in extra:                                                         # 17/11e3: tiến trình thứ 2 của máy đã biết → gộp
                    i, par = hi.get(p, (-1, 0))
                    k = pos.get(i) if i >= 0 else None
                    if k is None and par in own: k = own[par]
                    if k is None: k = next((own[q] for q, (_, qp) in hi.items() if qp == p and q in own), None)
                    if k is not None:
                        i0, nm0, e0, pp0 = vms[k]; vms[k] = (i0, nm0, e0 if e0 is not None else _elev(p), pp0 + [p]); own[p] = k; continue
                    vms.append((i, str((info.get(i) or {}).get("name") or byidx.get(i) or "máy ?"), _elev(p), [p]))
                    own[p] = len(vms) - 1
                    if i >= 0: pos[i] = len(vms) - 1
        else:
            for i, x in sorted((vms_sure(tries=1) or {}).items()):
                if not x.get("running"): continue
                pids = _vm_pids(i)
                ev = [e for e in (_elev(p) for p in pids) if e is not None]
                if pids: vms.append((int(i), str(x.get("name", "")), (True if any(ev) else False) if ev else None, pids))
    except Exception: pass
    return me, svc, main, vms


def _emu_alive(pid):
    """Tiến trình pid còn chạy VÀ là của giả lập (số PID có thể bị chương trình khác dùng lại)."""
    im = _proc_image(pid).lower()
    return bool(im) and any(k in im for k in _VM_IMAGES.get(EMU, ()))


def _android_off(p):
    """Tắt ÊM bằng Android (reboot -p): Android ghi xong dữ liệu rồi tắt → máy ảo tự thoát. Đi qua adb (không qua giả lập) nên vẫn làm
       được lúc giả lập báo xung đột quyền. Thử quyền shell rồi root."""
    s_ = serial(p)
    try:
        if (adb("-s", s_, "get-state", timeout=10).stdout or "").strip() != "device": adb_connect(p["port"])
        adb("-s", s_, "shell", "reboot -p", timeout=12)
        if (adb("-s", s_, "get-state", timeout=8).stdout or "").strip() == "device": adb("-s", s_, "shell", "su -c 'reboot -p'", timeout=12)
    except Exception: pass


def _kill_pids(pids):
    """Tắt cưỡng bức đúng các tiến trình (chỉ khi là của giả lập) → ['MuMuVMMHeadless.exe #123', …]."""
    out = []
    for pid in pids:
        im = _proc_image(pid)
        if im and any(k in im.lower() for k in _VM_IMAGES.get(EMU, ())):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NOWIN); out.append(f"{im} #{pid}")
    return out


def _priv_leftovers(wait=60):
    """Đã tắt hết máy khách sai quyền: (1) tắt chương trình chính MuMu chạy sai quyền (nó giữ dịch vụ máy ảo sai quyền còn sống) →
       (2) chờ dịch vụ máy ảo MuMuVMMSVC chạy sai quyền tự thoát (≤ wait giây); còn → tắt CHỈ KHI không còn máy ảo nào chạy (còn máy
       đang chạy thì không đụng) → (3) mở lại chương trình chính bằng quyền Admin (lúc này không còn gì sai quyền → không báo xung đột).
       Trả ([tên file còn chạy sai quyền], đã mở lại chương trình chính?)."""
    if not _WIN or EMU != "mumu": return [], False
    imgs = ("mumuvmmsvc.exe", "mumunxmain.exe", "mumuvmmheadless.exe")
    def snap():
        pr = {p: im.lower() for p, im in _img_pids(imgs).items()}
        return pr, {p: im for p, im in pr.items() if _elev(p) is False}
    pr, wrong = snap()
    if not wrong: return [], False
    main_bad = [p for p, im in wrong.items() if im == "mumunxmain.exe"]
    for p in main_bad: subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True, creationflags=NOWIN)
    if main_bad: print("   … chương trình chính MuMu chạy quyền thường → đã tắt (mở lại bằng quyền Admin ở dưới)", flush=True)
    t0 = time.time()
    while "mumuvmmsvc.exe" in wrong.values() and time.time() - t0 < wait:
        time.sleep(3); pr, wrong = snap()
    if "mumuvmmsvc.exe" in wrong.values():
        if "mumuvmmheadless.exe" not in pr.values():
            for p, im in wrong.items():
                if im == "mumuvmmsvc.exe": subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True, creationflags=NOWIN)
            print("   … dịch vụ máy ảo MuMu (MuMuVMMSVC) còn chạy quyền thường, không máy nào dùng → đã tắt (bật máy sẽ mở lại bằng quyền Admin)", flush=True)
            time.sleep(3)
        else:
            print("   ⚠ dịch vụ máy ảo MuMu (MuMuVMMSVC) còn chạy quyền thường mà vẫn có máy ảo đang chạy → không đụng (bật máy có thể còn báo xung đột)", flush=True)
    redone = False
    if main_bad:
        _PRIV["mt"] = 0.0
        try: open(MUMU_MAIN_F, "w").write("0")             # bỏ giới hạn 3 phút: mở lại ngay
        except OSError: pass
        redone = bool(_mumu_main_fix("chạy sai quyền"))
    return sorted({im.lower() for p, im in _img_pids(imgs).items() if _elev(p) is False}), redone


def memuc(*a, timeout=300):
    """memuc chỉ xử lý 1 lệnh một lúc (chạy chồng → "read failed: 233") → xếp hàng bằng khoá + thử lại.
       memuc gặp số máy KHÔNG CÓ (VD "-i 7" khi không có máy 7, hay "-i None") thì làm NHẦM SANG MÁY #0 (đã thấy: rename -i 7 đổi tên máy #0)
       → chặn số máy sai ở đây; remove / rename còn kiểm tra máy số đó đang có trong listvms ngay trước khi chạy."""
    iv = None
    if "-i" in a:
        k = a.index("-i"); iv = str(a[k + 1]).strip() if k + 1 < len(a) else ""
        if not iv.isdigit():
            return subprocess.CompletedProcess([], 1, "", f"bỏ lệnh {a[0]}: số máy không hợp lệ ({iv or 'trống'}) — không chạy để khỏi làm nhầm máy #0")
        # 16/11b: dấu "đang làm dở" (wake không bật chen ngang) — 16/11e: ghi lúc gửi lệnh tắt thật (_stop_marks), không ghi lúc còn chờ khoá
    if a and str(a[0]) == "start":                       # 17/11e: lẫn quyền Admin / quyền thường → giả lập báo xung đột, không bật được máy nào nữa
        pb = _priv_block()
        if pb: print("❌ " + pb, flush=True); return subprocess.CompletedProcess([], 1, "", pb)
        _priv_main_fix()
    if EMU == "mumu":
        c0 = str(a[0]) if a else ""
        if c0 == "start" and iv is not None: return _mumu_start(iv, timeout)     # khoá chỉ lúc gửi lệnh, chờ máy lên ngoài khoá
        if c0 == "stop" and iv is not None: return _mumu_stop(iv, timeout)
        return _mumu_locked(lambda: _mumu(a, timeout), wait=min(max(120, timeout), 260), long_op=c0 in ("create", "clone"))
    if EMU == "ld":
        lk = _Lock("memuc", wait=min(max(120, timeout), 260))
        try: lk.__enter__()
        except RuntimeError: _unstick_memuc(); lk = _Lock("memuc", wait=60); lk.__enter__()
        try:
            if iv is not None and a and str(a[0]) == "stop": _stop_marks(iv)       # 16/11e: ghi dấu lúc tắt thật (đã có khoá)
            return _ld(a, timeout)
        finally: lk.__exit__()
    r = None; long_op = bool(a) and str(a[0]) in _LONG_OPS
    for i in range(4):
        lk = _Lock("memuc", wait=min(max(120, timeout), 260))
        try: lk.__enter__()
        except RuntimeError:
            _unstick_memuc(); lk = _Lock("memuc", wait=60)
            try: lk.__enter__()
            except RuntimeError: return subprocess.CompletedProcess([], 1, "", "MEmu đang bận quá lâu (đợi khoá memuc) — thử lại sau")
        try:
            if iv is not None and str(a[0]) == "stop": _stop_marks(iv)            # 16/11e: ghi dấu lúc tắt thật (đã có khoá)
            if iv is not None and str(a[0]) in _IDX_CHECK:
                lv = run([os.path.join(MEMU, "memuc.exe"), "listvms"], 60)
                have = {ln.split(",")[0].strip() for ln in (lv.stdout or "").splitlines() if ln.strip()[:1].isdigit()}
                if iv not in have:
                    return subprocess.CompletedProcess([], 1, "", f"MEmu không có máy #{iv} (hoặc chưa đọc được danh sách) — không {a[0]}, tránh làm nhầm máy #0")
            if long_op: _long_mark(True)
            r = run([os.path.join(MEMU, "memuc.exe")] + list(a), timeout)
        finally:
            if long_op: _long_mark(False)
            lk.__exit__()
        o = (r.stdout or "") + (r.stderr or "")
        if "read failed" not in o and "connect failed" not in o.lower(): return r
        time.sleep(2 + 2 * i)
    return r
def adb(*a, timeout=60): return run([ADB] + list(a), timeout)

# ---------- trạng thái ----------
STATE_BAK = STATE + ".bak"                        # 17/11e3: bản sao lần ghi thành công gần nhất
STATE_ERR = os.path.join(HOME, "redroid", "phones_errors.log")
def _state_err(msg):
    try:
        os.makedirs(os.path.dirname(STATE_ERR), exist_ok=True)
        if os.path.isfile(STATE_ERR) and os.path.getsize(STATE_ERR) > 200000: os.replace(STATE_ERR, STATE_ERR + ".1")
        with open(STATE_ERR, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{os.getpid()}\t{' '.join(str(x) for x in sys.argv[1:3])}\t{msg}\n")
    except Exception: pass
def _read_list(path):
    """{"phones": [...]} · None = file chưa có · lỗi đọc / sai dạng → raise."""
    try:
        with open(path, "rb") as f: raw = f.read()
    except FileNotFoundError: return None
    if not raw.strip(): raise ValueError("file rỗng (0 byte)")
    d = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(d, dict) or not isinstance(d.get("phones"), list): raise ValueError("sai dạng (không có danh sách phones)")
    return d
def load():
    """Đọc redroid/phones.json. File chưa có (máy chủ mới) → danh sách rỗng.
       17/11e3: đọc lỗi (lệnh khác đang thay file / file hỏng) → thử lại ~2,5 giây → dùng bản sao phones.json.bak → vẫn không được →
       BÁO LỖI, không trả danh sách rỗng giả (trước: rỗng giả → nhận lại máy lạc tưởng mất hết máy → dựng lại danh sách, mất dấu ngủ
       và máy không tìm được theo tên — máy chủ 156 17/11 17:08)."""
    last = None
    for k in range(10):
        try:
            d = _read_list(STATE)
            return d if d is not None else {"phones": []}
        except Exception as e:
            last = e; time.sleep(0.25)
    _state_err(f"đọc phones.json lỗi: {type(last).__name__}: {last}")
    try:
        d = _read_list(STATE_BAK)
        if d is not None:
            print(f"   (phones.json đọc lỗi ({type(last).__name__}) → dùng bản sao phones.json.bak)", flush=True)
            return d
    except Exception: pass
    if isinstance(last, ValueError) and "0 byte" in str(last): return {"phones": []}     # file rỗng, không có bản sao: không còn gì để giữ
    raise RuntimeError(f"không đọc được redroid\\phones.json ({type(last).__name__}: {last}) — dừng, KHÔNG ghi gì để khỏi mất danh sách máy")
_DROPPED = set()          # tên máy CHÍNH lệnh này cố ý bỏ khỏi danh sách (xoá / quên / dọn) — save() không giữ lại
def drop_phone(st, name):
    _DROPPED.add(name); st["phones"] = [x for x in st["phones"] if x["name"] != name]
def save(st):
    # 14/11: nhiều lệnh phonectl chạy cùng lúc (tạo máy, nối lại adb, cho ngủ, chống kẹt…) — lệnh đọc danh sách TRƯỚC khi lệnh khác
    # thêm máy rồi ghi đè → MẤT DÒNG máy vừa tạo → bộ dọn máy thừa tưởng máy khách là máy thừa. Giờ: dòng đang có trên đĩa mà bản
    # sắp ghi không có (và lệnh này không cố ý bỏ) → giữ lại.
    # 17/11e3: 1 lệnh ghi 1 lúc (khoá phones_save) · file tạm RIÊNG mỗi lệnh (trước: chung phones.json.tmp → 2 lệnh ghi cùng lúc làm
    # hỏng file) · đọc file trên đĩa để gộp mà lỗi → load() báo lỗi → KHÔNG ghi · ghi xong giữ bản sao phones.json.bak.
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with _Lock("phones_save", wait=30):
        names = {x.get("name") for x in st.get("phones", [])}
        for x in load().get("phones", []):
            if x.get("name") not in names and x.get("name") not in _DROPPED: st["phones"].append(x)
        data = json.dumps(st, ensure_ascii=False, indent=1)
        tmp = f"{STATE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data); f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        for k in range(20):
            try: os.replace(tmp, STATE); break
            except PermissionError:                     # Windows: lệnh khác đang mở file → chờ chút rồi thay
                if k == 19:
                    try: os.remove(tmp)
                    except OSError: pass
                    _state_err("không thay được phones.json (đang bị giữ)"); raise
                time.sleep(0.15)
        try:
            bt = f"{STATE_BAK}.{os.getpid()}.tmp"
            with open(bt, "w", encoding="utf-8") as f: f.write(data)
            os.replace(bt, STATE_BAK)
        except Exception: pass
def rec(name, st=None): return next((x for x in (st or load())["phones"] if x["name"] == name), None)
def now(): return datetime.datetime.now().astimezone()
def parse_dt(s):
    d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")); return d if d.tzinfo else d.astimezone()
def fmt(dt): return dt.strftime("%d/%m/%Y %H:%M")
def port_of(idx):
    """Cổng adb của máy số idx. LDPlayer: 5555+2N · MEmu: 21503+10N · MuMu: đọc từ MuMu (thường 16384+32N)."""
    if EMU == "ld": return 5555 + 2 * int(idx)
    if EMU == "mumu":
        v = _mumu_info(fresh=False).get(int(idx)) or _mumu_info().get(int(idx)) or {}
        try: return int(v.get("adb_port"))
        except (TypeError, ValueError): return 16384 + 32 * int(idx)
    return 21503 + 10 * int(idx)
def vms_sure(tries=3):
    """vms() nhưng đọc lại khi danh sách rỗng (memuc bận / lỗi) — giả lập luôn có ít nhất 1 máy."""
    for k in range(tries):
        v = vms()
        if v: return v
        if k < tries - 1: time.sleep(2)
    return {}
def _new_vm(before, after, name=None):
    """Số máy VỪA tạo — chỉ nhận máy có TÊN mới xuất hiện thêm (máy cũ bị MEmu đánh lại số vẫn giữ tên → không bao giờ bị nhận nhầm).
       Ưu tiên máy mang tên đặt sẵn (memuc clone -r TÊN). Không có → None (chờ tiếp / đơn lỗi, an toàn)."""
    from collections import Counter
    old = {(i, x["name"]) for i, x in before.items()}
    extra = Counter(x["name"] for x in after.values()) - Counter(x["name"] for x in before.values())
    cand = [i for i, x in sorted(after.items()) if (i, x["name"]) not in old and extra.get(x["name"])]
    if name:
        hit = [i for i in cand if after[i]["name"] == name]
        if hit: return max(hit)
    return max(cand) if cand else None                   # máy mới luôn nằm cuối danh sách
def create_vm(android, name=None):
    """Tạo 1 máy ảo mới ĐÚNG bản Android → (kết quả lệnh, số máy hoặc None). Không tạo được đúng bản → lỗi (đơn được hoàn tiền),
       KHÔNG BAO GIỜ tạo nhầm bản khác (khách trả tiền Android 7 mà nhận Android 12).
       name: tên sẽ đặt cho máy (MEmu nhân bản đặt tên luôn lúc nhân bản → tìm lại máy chắc chắn theo tên)."""
    ver = norm_android(android)
    cur = vms_sure()
    if not cur and EMU == "ld":                            # 17/11a: LDPlayer vừa cài chưa có máy nào → tạo máy gốc rồi tạo tiếp (win8)
        r0 = memuc("ensurebase", timeout=240)
        if r0.returncode != 0:
            why = ((r0.stderr or "").strip() or "không rõ lý do")[-110:]
            return subprocess.CompletedProcess([], 1, "", f"không đọc được danh sách máy của {EMU_NAME} ({why}) — mở LDPlayer 1 lần, thấy có máy trong danh sách rồi thử lại"), None
        if "da_tao" in (r0.stdout or ""): print("   (LDPlayer chưa có máy nào → đã tạo máy gốc 'LDPlayer' — đừng xoá máy này)", flush=True)
        cur = vms_sure()
    if not cur: return subprocess.CompletedProcess([], 1, "", f"không đọc được danh sách máy của {EMU_NAME} — thử lại sau"), None
    has_tpl = any(x["name"] == tpl_name(ver) for x in cur.values())
    clone = False
    if EMU == "ld": r = memuc("create", "96", timeout=240)
    elif EMU == "mumu":
        if not has_tpl and ver != DEF_ANDROID:            # MuMu tạo mới = bản mặc định của MuMu (ANDROIDS[0]); bản khác phải có máy mẫu
            return subprocess.CompletedProcess([], 1, "", f"chưa có máy mẫu {tpl_name(ver)} (Android {ver}) trong MuMu"), None
        r = memuc("create", ver, timeout=300)
    else:
        tpl = next((i for i, x in sorted(cur.items()) if x["name"] == tpl_name(ver)), None)
        if tpl is not None:                               # MEmu: bản không có mã tạo sẵn (VD Android 12) → nhân bản máy mẫu
            clone = True
            if cur[tpl]["running"]:                       # máy mẫu đang bật → tắt hẳn rồi mới nhân bản
                memuc("stop", "-i", tpl, timeout=120)
                for _ in range(20):
                    if not (vms().get(tpl) or {}).get("running"): break
                    time.sleep(3)
            r = memuc(*(["clone", "-i", tpl] + (["-r", name] if name else [])), timeout=900)
            o = ((r.stdout or "") + (r.stderr or "")).lower()
            if name and "success" not in o and re.search(r"invalid|unknown|usage|param|argument|error", o):
                r = memuc("clone", "-i", tpl, timeout=900)       # memuc bản này không nhận "-r TÊN" → nhân bản thường
        elif ver in MEMU_CODES: r = memuc("create", MEMU_CODES[ver], timeout=240)
        else: return subprocess.CompletedProcess([], 1, "", f"MEmu không có sẵn Android {ver} — tạo máy mẫu {tpl_name(ver)}"), None
    o = ((r.stdout or "") + (r.stderr or "")).lower()
    m = None if clone else re.search(r"index\D*(\d+)", r.stdout or "")
    idx = int(m.group(1)) if m else None
    if idx is not None and idx in cur: idx = None          # số máy trong kết quả là máy CŨ → không tin, dò lại
    if idx is None and ("success" in o or r.returncode in (0, None)):
        t_end = time.time() + (240 if clone else 60)       # MEmu báo "clone vm finished" nhưng máy mới hiện trong danh sách có thể trễ
        while idx is None and time.time() < t_end:
            after = vms()
            if after: idx = _new_vm(cur, after, name)
            if idx is None: time.sleep(3)
    if idx is None:                                       # ghi danh sách máy lúc lỗi vào nhật ký → biết MEmu đặt máy mới ra sao
        after = vms()
        lst = " ".join(f"{i}:{x['name']}" for i, x in sorted(after.items()))
        r = subprocess.CompletedProcess(r.args, r.returncode or 1,
                                        (r.stdout or "").strip() + f" | không thấy máy mới trong {EMU_NAME} | máy hiện có: {lst[:170] or '(không đọc được)'}", r.stderr)
    return r, idx

def _pid_alive(pid):
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h: return False
        code = ctypes.c_ulong(); ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)); ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259                                              # STILL_ACTIVE
    except Exception: return True

class _Lock:            # khoá file: các lệnh memuc không chạy chồng nhau. Khoá của chương trình đã tắt → tự gỡ.
    def __init__(self, name, wait=600): self.p = os.path.join(HOME, "redroid", name + ".lock"); self.wait = wait
    def __enter__(self):
        os.makedirs(os.path.dirname(self.p), exist_ok=True)
        for _ in range(int(self.wait * 4)):
            try:
                self.fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(self.fd, str(os.getpid()).encode()); return self
            except FileExistsError:
                try:
                    pid = open(self.p).read().strip()
                    if (pid.isdigit() and not _pid_alive(pid)) or (not pid and time.time() - os.path.getmtime(self.p) > 30) \
                            or time.time() - os.path.getmtime(self.p) > 960: os.remove(self.p)
                except Exception: pass
                time.sleep(0.25)
        raise RuntimeError("đợi khoá quá lâu")
    def __exit__(self, *a):
        try: os.close(self.fd); os.remove(self.p)
        except Exception: pass

def _sb_patch(name, fields):
    """Báo web (Supabase) khi cổng máy đổi — MEmu có thể đánh lại số máy khi xoá máy khác."""
    try:
        import urllib.request, urllib.parse
        url = CONF["SUPABASE_URL"].rstrip("/") + "/rest/v1/cloud_phones?container=eq." + urllib.parse.quote(name)
        k = CONF["SUPABASE_SERVICE_KEY"]
        req = urllib.request.Request(url, data=json.dumps(fields).encode(), method="PATCH",
                                     headers={"apikey": k, "Authorization": "Bearer " + k, "Content-Type": "application/json", "Prefer": "return=minimal"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e: print("   (không báo được web:", e, ")")

def stream_url(port):
    import urllib.parse
    q = urllib.parse.quote; base = CONF.get("PUBLIC_BASE", "https://phone.cloudblue.vn").rstrip("/"); udid = f"127.0.0.1:{port}"
    ws = base.replace("https://", "wss://") + "/?action=proxy-adb&remote=" + q("tcp:8886", safe="") + "&udid=" + q(udid, safe="")
    return f"{base}/#!action=stream&udid={q(udid, safe='')}&player=webcodecs&ws={q(ws, safe='')}"

def IDX(p, _v=None):
    """Số máy MEmu THẬT của máy này — tìm theo TÊN mỗi lần (số máy trong MEmu có thể đổi). Đổi → cập nhật cổng + báo web."""
    v = _v if _v is not None else vms()
    hit = [i for i, x in v.items() if x["name"] == p["name"]]
    if not hit: return None
    i = hit[0]
    if int(p.get("idx", -1)) != i or int(p.get("port", 0)) != port_of(i):
        st = load(); q = rec(p["name"], st)
        if q:
            q["idx"], q["port"] = i, port_of(i); save(st)
            print(f"   ↪ {p['name']}: MEmu đổi số máy → #{i}, cổng {port_of(i)}")
            if p["name"].startswith("cp_"): _sb_patch(p["name"], {"port": port_of(i), "stream_url": stream_url(port_of(i))})
        p["idx"], p["port"] = i, port_of(i)
    return i

def vms():
    """{index: {name, running}} theo memuc listvms (index,tên,cửa sổ,đang chạy,pid,dung lượng)."""
    out = {}
    for line in (memuc("listvms", timeout=60).stdout or "").splitlines():
        p = line.split(",")
        if len(p) >= 4 and p[0].strip().isdigit():
            out[int(p[0])] = {"name": p[1].strip(), "running": p[3].strip() == "1"}
    return out
def is_running(name, p=None, _v=None):
    p = p or rec(name)
    if not p: return False
    v = _v if _v is not None else vms()
    i = IDX(p, v)
    return i is not None and bool(v[i]["running"])

def mem():
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.total / 2**30, m.avail / 2**30

HIDE = CONF.get("HIDE_WINDOWS", "1") == "1"      # 1 = cửa sổ giả lập của máy khách chạy ngầm (không lên thanh taskbar, đỗ gần hết ngoài màn hình)
PARK = (CONF.get("PARK") or "corner").strip().lower()    # corner: góc phải dưới màn hình chính, chỉ lộ PARK_SHOW điểm ảnh · screen: nằm hẳn trong màn hình
PARK_SHOW = max(4, int(CONF.get("PARK_SHOW", "24") or 24))
KEEP_PROP = "CloudBlueKeep"                      # bluestream đánh dấu cửa sổ phải nằm hẳn trong màn hình mới quay được → không dời đi
def park_xy(rc, mode=None):
    """Chỗ đỗ cửa sổ máy khách chạy ngầm (điểm ảnh thật) — GIỐNG HỆT park_xy trong bluestream.py.
       KHÔNG đỗ ở (-32000, -32000): đó là toạ độ Windows dành cho cửa sổ thu nhỏ → Windows Graphics Capture báo
       "The parameter is incorrect", không quay được (app màn đen)."""
    u = ctypes.windll.user32
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    if (mode or PARK) == "screen": return max(0, sw - (rc[2] - rc[0])), max(0, sh - (rc[3] - rc[1]))
    return sw - PARK_SHOW, sh - PARK_SHOW
def hide_window(name, show=False):
    """Cho cửa sổ giả lập của máy khách chạy ngầm: kiểu tool window (không lên taskbar), đỗ ở góc phải dưới màn hình chính chỉ lộ
       PARK_SHOW điểm ảnh (PARK=screen: nằm hẳn trong màn hình), nằm dưới mọi cửa sổ. KHÔNG thu nhỏ (giả lập ngừng vẽ),
       KHÔNG đẩy ra (-32000, -32000) (Windows không cho quay → app màn đen). Cửa sổ ở chỗ đỗ cũ -32000 được dời sang chỗ mới."""
    if not HIDE and not show: return 0
    u = ctypes.windll.user32; found = []
    try: u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))      # toạ độ điểm ảnh thật (như bluestream) dù Windows đặt phóng to 125%…
    except Exception: pass
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1); t = b.value
            if t == name or t.endswith(f"({name})") or t.endswith(f" {name}") or t == f"MEmu_{name}": found.append(h)
        return True
    u.EnumWindows(PROC(cb), 0)
    GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
    for h in found:
        ex = u.GetWindowLongW(h, GWL_EXSTYLE)
        if show:
            u.RemovePropW(h, KEEP_PROP)
            u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW); u.ShowWindow(h, 5)
            u.SetWindowPos(h, 0, 100, 100, 0, 0, 0x0001 | 0x0004)
            continue
        if u.GetPropW(h, KEEP_PROP): continue                                    # bluestream cần cửa sổ nằm trong màn hình → giữ nguyên
        rc = (ctypes.c_long * 4)(); u.GetWindowRect(ctypes.c_void_p(h), rc)
        px, py = park_xy(rc)
        if (ex & WS_EX_TOOLWINDOW) and abs(rc[0] - px) <= 2 and abs(rc[1] - py) <= 2: continue   # đã đỗ đúng chỗ → không đụng (không gián đoạn phát hình)
        if ex & WS_EX_TOOLWINDOW:                                                # đã chạy ngầm (VD chỗ đỗ cũ -32000) → chỉ dời chỗ, không ẩn/hiện
            u.SetWindowPos(h, 1, px, py, 0, 0, 0x0001 | 0x0010)                 # HWND_BOTTOM, giữ kích thước, không lấy focus
            continue
        u.ShowWindow(h, 0)                                                       # ẩn tạm để đổi kiểu cửa sổ (Windows chỉ đổi taskbar khi hiện lại)
        u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        u.SetWindowPos(h, 1, px, py, 0, 0, 0x0001 | 0x0010)
        u.ShowWindow(h, 4)                                                       # hiện lại (không lấy focus) → giả lập vẫn vẽ hình
    return len(found)

def serial(p): return f"127.0.0.1:{p['port']}"
def adb_connect(port): return adb("connect", f"127.0.0.1:{port}", timeout=20)
def ashell(name, script, port=None, timeout=60):
    p = rec(name); s = f"127.0.0.1:{port or p['port']}"
    if (adb("-s", s, "get-state", timeout=15).stdout or "").strip() != "device": adb_connect(port or p["port"])
    return adb("-s", s, "shell", script, timeout=timeout)

BROWSERS = ("com.android.chrome org.mozilla.firefox com.brave.browser com.google.android.gm com.google.android.documentsui "
            "com.android.documentsui com.google.android.apps.nbu.files com.kiwibrowser.browser com.opera.browser "
            "com.microsoft.emmx mark.via.gp com.sec.android.app.sbrowser com.mi.android.globalFileexplorer com.UCMobile.intl")
PERM_SH = ("for p in " + BROWSERS + "; do pm path $p >/dev/null 2>&1 || continue; "
           "case \"$(appops get $p REQUEST_INSTALL_PACKAGES 2>/dev/null)\" in *allow*) ;; "
           "*) appops set $p REQUEST_INSTALL_PACKAGES allow >/dev/null 2>&1;; esac; done; true")

TUNE = (# CLONE TAB cần Android cho phép nhiều người dùng (máy ảo mặc định chỉ 1) — mất khi khởi động lại nên đặt lại mỗi lần
        "[ \"$(getprop fw.max_users)\" = 8 ] || setprop fw.max_users 8; "
        # Trình cài đặt ban đầu của Google bị lỗi trên máy ảo (Android 9/10 kẹt ở MÀN ĐEN) → tắt nó + đánh dấu "đã cài đặt xong"
        "if pm path com.google.android.setupwizard >/dev/null 2>&1 && [ \"$(settings get secure user_setup_complete)\" != 1 ]; then "
        "settings put global device_provisioned 1; settings put secure user_setup_complete 1; "
        "pm disable com.google.android.setupwizard >/dev/null 2>&1; am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1; fi; "
        # MÁY NHẸ: tắt app Google chạy ngầm khách không dùng (chuyển máy, sao lưu, khảo sát, đọc chữ, đồng bộ lịch/danh bạ) — tắt 1 lần, bật lại được
        "[ -f /data/local/tmp/.br_lite ] || { for p in com.google.android.apps.pixelmigrate com.google.android.apps.restore com.google.android.backuptransport "
        "com.google.android.carriersetup com.google.android.feedback com.google.android.partnersetup com.google.android.tts "
        "com.google.android.syncadapters.calendar com.google.android.syncadapters.contacts com.google.android.onetimeinitializer; do "
        "pm disable-user --user 0 $p >/dev/null 2>&1; done; touch /data/local/tmp/.br_lite; }; "
        # hiệu ứng chuyển cảnh NHANH 0,5× (KHÔNG tắt hẳn = 0: launcher Android 12/15 của MuMu (Lawnchair) văng khi bấm nút đa nhiệm
        # và app bấm vào chỉ phóng to icon rồi KHÔNG MỞ — lỗi khách báo 09/11)
        "settings put global window_animation_scale 0.5; settings put global transition_animation_scale 0.5; "
        "settings put global animator_duration_scale 0.5; settings put global package_verifier_enable 0; "
        # cửa sổ nổi: mở nhiều app/tab cùng lúc (có hiệu lực sau lần khởi động lại máy kế tiếp)
        "settings put global enable_freeform_support 1; settings put global force_resizable_activities 1; "
        "settings put global enable_sizecompat_freeform 1; "
        # treo game qua đêm: không ngủ đông (doze), không xếp app vào nhóm hạn chế, không đóng băng app chạy nền
        "dumpsys deviceidle disable >/dev/null 2>&1; settings put global app_standby_enabled 0; "
        "settings put global adaptive_battery_management_enabled 0; settings put global always_finish_activities 0; "
        "device_config put activity_manager_native_boot use_freezer false >/dev/null 2>&1; "
        "settings put global cached_apps_freezer disabled; "
        # Cửa hàng Play KHÔNG tự cập nhật app chạy nền (đỡ lag, đỡ tốn mạng); khách mở Play vẫn tải/cập nhật tay được.
        # Chỉ đặt khi chưa đặt — đổi quyền của app làm Android tắt app đó, đặt lặp lại sẽ văng Play khi đang dùng.
        "case \"$(cmd appops get com.android.vending RUN_ANY_IN_BACKGROUND 2>/dev/null)\" in *ignore*) ;; *) "
        "cmd appops set com.android.vending RUN_ANY_IN_BACKGROUND ignore; am set-standby-bucket com.android.vending restricted;; esac; "
        "settings put global package_verifier_user_consent -1; settings put global upload_apk_enable 0; "
        "settings put global verifier_verify_adb_installs 0; settings put global stay_on_while_plugged_in 7; "
        "settings put system screen_off_timeout 2147483647; svc power stayon true; "
        # Trình duyệt bị MÀN ĐEN (máy ảo không có chip đồ hoạ): Firefox dùng WebRender phần mềm
        # (Chrome trên Android KHÔNG chạy được khi tắt GPU → đã bỏ cờ --disable-gpu cũ, nó làm Chrome văng ngay lúc mở)
        "rm -f /data/local/chrome-command-line /data/local/tmp/chrome-command-line /data/local/tmp/webview-command-line 2>/dev/null; "
        "for d in /data/data/org.mozilla.firefox/files/mozilla/*.default*; do [ -d \"$d\" ] || continue; "
        "grep -q webrender.software \"$d/user.js\" 2>/dev/null || { printf 'user_pref(\"gfx.webrender.software\", true);\\nuser_pref(\"layers.acceleration.disabled\", true);\\nuser_pref(\"gfx.canvas.accelerated\", false);\\n' >> \"$d/user.js\"; "
        "chown $(stat -c %u \"$d\"):$(stat -c %g \"$d\") \"$d/user.js\"; }; done 2>/dev/null; "
        # Cổng VPN: Android mở /dev/tun (docker chỉ có /dev/net/tun) → thiếu thì VPN báo "Failed to connect"
        "[ -c /dev/tun ] || { rm -f /dev/tun; mknod /dev/tun c 10 200; }; chmod 666 /dev/tun")

def android_ready(port, wait=120):
    """Android SẴN SÀNG THẬT (dịch vụ settings + package chạy) — sys.boot_completed vẫn = 1 khi giao diện đang khởi động lại
    (sau đặt ảnh nền) nên không tin được; chạy tối ưu lúc đó là mất hết."""
    t0 = time.time()
    while time.time() - t0 < wait:
        o = (adb("-s", f"127.0.0.1:{port}", "shell", "settings get global device_provisioned; pm path android", timeout=15).stdout or "")
        if "package:" in o and "rror" not in o and "an't find" not in o: return True
        time.sleep(3)
    return False
def tune(name, port=None):
    """Tối ưu máy (máy nhẹ, tắt hiệu ứng, chống ngủ đông…) — KIỂM TRA đã ăn chưa, chưa thì làm lại (tối đa 3 lần)."""
    port = port or (rec(name) or {}).get("port")
    if not port: return False
    for _t in range(3):
        android_ready(port)
        try: adb("-s", f"127.0.0.1:{port}", "shell", TUNE, timeout=120)
        except Exception: pass
        o = (adb("-s", f"127.0.0.1:{port}", "shell", "settings get global animator_duration_scale; [ -f /data/local/tmp/.br_lite ] && echo LITE", timeout=15).stdout or "")
        try: anim_ok = abs(float((o.split() or ["x"])[0]) - 0.5) < 0.01
        except ValueError: anim_ok = False
        if anim_ok and "LITE" in o: return True
        time.sleep(10)
    print(f"   ⚠ {name}: chưa tối ưu được hết (sẽ làm lại lần khởi động sau)", flush=True)
    return False
def grant_perms(name, port=None):
    port = port or (rec(name) or {}).get("port")
    if not port: return
    try: adb("-s", f"127.0.0.1:{port}", "shell", PERM_SH, timeout=60)
    except Exception: pass

WP = os.path.join(HOME, "wallpaper.png")
_WPV = {}
def wp_ver():
    """Mã phiên bản ảnh nền (đổi file wallpaper.png → mã đổi)."""
    try:
        st = os.stat(WP); k = (st.st_size, int(st.st_mtime))
        if _WPV.get("k") != k: _WPV.update(k=k, v=hashlib.md5(open(WP, "rb").read()).hexdigest()[:12])
        return _WPV["v"]
    except OSError: return "0"
def set_wallpaper(name, port, force=False):
    """Ảnh nền CloudBlue cho máy: chép thẳng vào file ảnh nền của Android (cần root) rồi khởi động lại giao diện ~30 giây.
       Mỗi máy chỉ đặt 1 lần cho mỗi phiên bản ảnh. Ra ảnh mới → máy đang dùng ảnh nền cũ của mình được chép sẵn ảnh mới,
       KHÔNG khởi động lại (khách không bị gián đoạn) — ảnh mới hiện từ lần khởi động sau. Khách đã TỰ ĐỔI ảnh nền → giữ ảnh của khách."""
    if CONF.get("WALLPAPER", "1") != "1" or not os.path.isfile(WP): return False
    s_ = f"127.0.0.1:{port}"; ver = wp_ver(); quiet = False
    if not force:
        o = adb("-s", s_, "shell", "[ -f /data/local/tmp/.br_wp ] && echo \"Y:$(cat /data/local/tmp/.br_wp)\"", timeout=15).stdout or ""
        if "Y:" in o:
            if o.split("Y:", 1)[1].strip() == ver: return False
            same = adb("-s", s_, "shell", "su -c 'cmp -s /data/system/users/0/wallpaper_orig /data/local/tmp/br_wp.png && echo SAME'", timeout=30).stdout or ""
            if "SAME" not in same or CONF.get("WALLPAPER_UPDATE", "1") != "1":      # khách đã đổi ảnh nền (hoặc tắt tự đổi) → giữ
                adb("-s", s_, "shell", f"echo {ver} > /data/local/tmp/.br_wp", timeout=15); return False
            quiet = True
    adb("-s", s_, "push", WP, "/data/local/tmp/br_wp.png", timeout=120)
    sc = ("D=/data/system/users/0; for f in wallpaper wallpaper_orig wallpaper_lock wallpaper_lock_orig; do "
          "cp /data/local/tmp/br_wp.png $D/$f; chown system:system $D/$f; chmod 600 $D/$f; done; "
          f"rm -f $D/wallpaper_info.xml; restorecon $D/wallpaper* 2>/dev/null; echo {ver} > /data/local/tmp/.br_wp; sync")
    if quiet:
        adb("-s", s_, "shell", "su -c '" + sc + "'", timeout=60)
        print(f"   🖼 {name}: đã chép ảnh nền CloudBlue mới (hiện từ lần khởi động sau)", flush=True)
        return True
    if EMU == "ld":
        # LDPlayer: "stop; start" giao diện làm adb của máy treo → chép ảnh rồi KHỞI ĐỘNG LẠI CẢ MÁY bằng ldconsole (sạch, an toàn)
        adb("-s", s_, "shell", "su -c '" + sc + "'", timeout=60)
        i = next((k for k, x in vms().items() if x["name"] == name), None)
        if i is not None:
            adb("disconnect", s_, timeout=15)
            _ldrun(["reboot", "--index", i], 60); time.sleep(20)
    else:
        sp = _ss_pid(port)
        adb("-s", s_, "shell", "su -c '" + sc + "; stop; sleep 2; start'", timeout=60)
    print(f"   🖼 {name}: đã đặt ảnh nền CloudBlue", flush=True)
    time.sleep(8)
    if EMU != "ld":
        # 16/11k: "stop; start" chỉ khởi động lại GIAO DIỆN — sys.boot_completed vẫn = 1 → bản cũ tưởng xong ngay, giao máy cho khách
        # lúc giao diện còn đang lên (khách mở máy: "DeadSystemException", màn đen). Giờ chờ system_server mới + màn khởi động tắt.
        if not _fw_wait(port, sp, 180): print(f"   ({name}: giao diện chưa lên lại sau 3 phút — vẫn làm tiếp)", flush=True)
        return True
    t0 = time.time()
    while time.time() - t0 < 180:
        adb_connect(port)
        if booted(port): break
        time.sleep(3)
    return True

def auto_dpi(res):
    w, h = (int(x) for x in res.split("x")); return max(160, min(640, round(min(w, h) / 2.25)))
def clamp_fps(v):
    try: v = int(v)
    except Exception: v = 30
    return min(max(v, 10), 120)

def _host_ram():
    try: return mem()[0]
    except Exception: return 0.0
if EMU == "mumu":
    # MuMu (Android 12 / 15): trần 1 máy 16GB · 32 nhân = mức cao nhất MuMu cho (giống giới hạn bán trên web: bảng giá → android_limits).
    MAX_RAM = float(CONF.get("MEMU_MAX_RAM") or 16)
    MAX_CPU = int(float(CONF.get("MEMU_MAX_CPU") or 32))
else:
    MAX_RAM = float(CONF.get("MEMU_MAX_RAM", "8" if EMU == "ld" else "16") or 16)     # MEmu (Android 7 / 12) tối đa 16GB/máy · LDPlayer 9 (Android 9) tối đa 8GB
    MAX_CPU = int(float(CONF.get("MEMU_MAX_CPU", "8" if EMU == "ld" else "16") or 8))  # MEmu tối đa 16 nhân · LDPlayer 9 tối đa 8 nhân
LD_MEM = (256, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192, 12288, 16384)
# MuMu: máy cloud luôn "chạy nền" (cửa sổ ẩn) → mặc định MuMu TẠM DỪNG app + HẠ FPS khi cửa sổ không ở trước → game tải hình rất chậm.
#   app_keptlive = giữ app chạy nền · dynamic_adjust_frame_rate = tự hạ FPS (tắt) · force_discrete_graphics = bắt dùng card rời (RTX)
#   vertical_sync = chờ màn hình (tắt) · prevent_sleep = không cho Windows ngủ. Tắt cả bộ: MUMU_PERF=0 trong cloudphone.conf
MUMU_PERF = {} if CONF.get("MUMU_PERF", "1") == "0" else {
    # app_keptlive = "giữ app chạy nền" của MuMu: TẮT — MuMu Android 15 mở MỖI APP thành 1 tab = 1 màn hình riêng, luồng hình chỉ thấy
    # màn chính → khách bấm app không thấy mở (lỗi khách báo 09/11, bật từ 08/11). Android tự giữ app chạy nền như bình thường.
    "app_keptlive": "false", "dynamic_adjust_frame_rate": "false", "force_discrete_graphics": "true", "vertical_sync": "false", "prevent_sleep": "true",
    # root_permission = "Enable root" (Developer options) của MuMu: BẬT cho mọi máy — máy nào bật lại (start / ramfix / khoidonglai /
    # perfset lúc tắt) là có root (09/11: nhiều máy bấm "Root máy" không ăn vì MuMu chỉ cho ghi lúc máy TẮT).
    "root_permission": "true"}
# ---------- 18/11 → 19/11: BỘ NHỚ MÁY KHÁCH THEO CẤU HÌNH ----------
# Khách báo máy chỉ còn 3GB. MuMu: máy mẫu tpl_a12 / tpl_a15 tạo ở "chế độ ổ nhỏ" (mini_disk) → máy nhân bản ra đều vậy: /data là ext4
# 2,9GB nằm trên phân vùng đã lớn sẵn (sdc3: 128GB Android 12 · 931GB Android 15). Chỉ tắt mini_disk rồi khởi động lại KHÔNG nới (thử
# trên máy thử win5 18/11). Cách nới: resize2fs <ổ /data> <N>G bằng ROOT ngay lúc máy đang chạy — chỉ LỚN lên (không bao giờ thu nhỏ),
# dữ liệu giữ nguyên, khách không bị ngắt. Thử trên máy thử win5 19/11: 2,9GB → 19,6GB trong 1 giây, khởi động lại 2 lần vẫn giữ (cả
# Android 12 lẫn 15). Root: Android 12 qua "su -c" · Android 15 (KernelSU, không có su cho adb) qua "adb root" đúng 1 lệnh rồi "adb unroot"
# (DISK_ADBROOT=0: không dùng).
# Chủ máy 19/11: CHỈ MÁY MỚI, máy cũ để nguyên · bộ nhớ MIỄN PHÍ theo cấu hình (DISK_TIERS, mặc định RAM < 4GB → 8GB · 4–7GB → 13GB ·
# từ 8GB → 16GB) · khách MUA THÊM được (SQL v40 + web, admin bật / tắt + đặt giá).
#   · create --disk N (cloudphoned truyền cỡ web đã tính) → máy mới có dấu disk_new = N → lần đầu lên (wait_boot) thì nới, xong bỏ dấu.
#   · disk TÊN --gb N (cloudphoned gọi khi khách mua thêm / nâng RAM lên bậc cao hơn) → máy đang chạy: nới ngay · đang tắt / ngủ: hẹn lần bật.
#   · máy cũ (không có dấu) KHÔNG BAO GIỜ bị đụng, trừ khi khách mua thêm hoặc admin gõ đúng tên: `phonectl bonho --sua TÊN`.
#   · ổ máy chủ còn < DISK_HOST_MIN_GB trống → không nới, chỉ báo · không có root → báo, thử lại lần bật sau (tối đa 5 lần).
# Tắt hẳn: DISK_FIX=0 · bậc: DISK_TIERS=0:8,4:13,8:16 · trần 1 máy: DISK_MAX_GB=64.
DISK_TIERS_DEF = "0:8,4:13,8:16"             # 19/11 chủ máy: RAM < 4GB → 8GB · 4–7GB → 13GB · từ 8GB → 16GB (khách mua thêm thì cao hơn)
def _disk_tiers(txt):
    """"RAM_tối_thiểu:GB,…" → [(ram, gb)] tăng dần. Sai dạng → bậc mặc định."""
    out = []
    try:
        for part in str(txt or "").replace(";", ",").split(","):
            if not part.strip(): continue
            r, g = part.split(":"); out.append((max(0.0, float(r)), max(4, min(512, int(float(g))))))
    except (ValueError, TypeError): out = []
    return sorted(out) or _disk_tiers(DISK_TIERS_DEF)
DISK_TIERS = _disk_tiers(CONF.get("DISK_TIERS") or DISK_TIERS_DEF)
try: DISK_MAX = max(8, min(512, int(float(CONF.get("DISK_MAX_GB", "64") or 64))))
except ValueError: DISK_MAX = 64
def disk_tier(ram):
    """Bộ nhớ MIỄN PHÍ (GB) của máy theo RAM — theo DISK_TIERS (cùng bậc với web: cloudphone_pricing.disk_tiers)."""
    try: r = float(ram or 0)
    except (TypeError, ValueError): r = 0.0
    gb = DISK_TIERS[0][1]
    for t, g in DISK_TIERS:
        if r >= t: gb = g
    return min(gb, DISK_MAX)
DISK_FIX = str(CONF.get("DISK_FIX", "1")).strip() != "0"
try: DISK_HOST_MIN = float(CONF.get("DISK_HOST_MIN_GB", "30") or 30)
except ValueError: DISK_HOST_MIN = 30.0
DG_ADBROOT = str(CONF.get("DISK_ADBROOT", "1")).strip() != "0"       # 0 = không dùng "adb root" (khi đó máy Android 15 / KernelSU không nới được)
DG_LOG = os.path.join(HOME, "redroid", "disk_events.log")
_DG_DEV = re.compile(r"^/dev/block/[A-Za-z0-9_.\-/]{1,60}$")
_DG_ROOT = {}                                                  # cổng → cách chạy root được ("su -c" / "su 0 sh -c" / "")
_DG_SAID = set()                                               # (tên máy, mã) đã báo trong lệnh này
_DG_STATE_SH = ("df -k /data 2>/dev/null | tail -n +2 | head -1; echo @@; mount 2>/dev/null | grep ' /data ' | head -1; echo @@; "
                "D=$(mount 2>/dev/null | grep ' /data ' | head -1 | cut -d' ' -f1); [ -n \"$D\" ] && cat /sys/class/block/${D##*/}/size 2>/dev/null")
def _dg_state(port):
    """/data của máy đang chạy (chỉ đọc, không cần root) → {total, avail (byte), dev, fs, part (byte)} — thiếu thì None / ''."""
    out = {"total": None, "avail": None, "dev": "", "fs": "", "part": None}
    try: o = adb("-s", f"127.0.0.1:{port}", "shell", _DG_STATE_SH, timeout=20).stdout or ""
    except Exception: return out
    parts = (o.split("@@") + ["", "", ""])[:3]
    t = parts[0].split()
    if len(t) >= 4 and t[1].isdigit() and t[3].isdigit(): out["total"], out["avail"] = int(t[1]) * 1024, int(t[3]) * 1024
    m = parts[1].split()
    if len(m) >= 5 and m[1] == "on" and m[2] == "/data" and m[3] == "type": out["dev"], out["fs"] = m[0], m[4]
    elif len(m) >= 3 and m[1] == "/data": out["dev"], out["fs"] = m[0], m[2]
    z = parts[2].split()
    if z and z[0].isdigit(): out["part"] = int(z[0]) * 512
    return out
def _dg_root(port, script, timeout=900):
    """Chạy script (KHÔNG có dấu nháy đơn) bằng ROOT trong máy: cách đã nhớ trước, rồi su -c · su 0 sh -c · adb đã là root.
       Trả chữ in ra (script phải in DG_END ở cuối) · None = không có root / adb không nối được."""
    s_ = f"127.0.0.1:{port}"; body = "[ $(id -u) = 0 ] || { echo DG_NOROOT; exit 0; }; " + script
    order = ([_DG_ROOT[port]] if port in _DG_ROOT else []) + [m for m in ("su -c", "su 0 sh -c", "") if m != _DG_ROOT.get(port)]
    for pre in order:
        try: r = adb("-s", s_, "shell", body if pre == "" else f"{pre} '{body}'", timeout=timeout)
        except Exception: return None
        o = ((r.stdout or "") + " " + (r.stderr or "")).strip()
        if "DG_END" in o and "DG_NOROOT" not in o: _DG_ROOT[port] = pre; return o
        if _adb_gone(o) or r.returncode == 124: return None
    _DG_ROOT.pop(port, None)
    if not DG_ADBROOT: return None
    # 19/11 (thử trên máy thử win5): Android 15 của MuMu dùng KernelSU → không có su cho adb, nhưng "adb root" chạy được → dùng adbd quyền
    # root ĐÚNG 1 lệnh rồi trả adbd về quyền thường ngay ("adb unroot"). adbd khởi động lại 2 lần (vài giây) — chỉ xảy ra với máy MỚI lúc
    # lên lần đầu (chưa giao khách), máy khách vừa MUA THÊM bộ nhớ (chạm có thể khựng 1–2 giây, hình vẫn chạy) hoặc máy admin gõ tên.
    def back_up():
        for _ in range(10):
            time.sleep(1.5)
            if _adb_fresh(port): return True
        return False
    rooted = False; o = ""
    try:
        r = adb("-s", s_, "root", timeout=20); o0 = ((r.stdout or "") + " " + (r.stderr or "")).lower()
        if "as root" not in o0 or "cannot" in o0: return None
        rooted = True
        if back_up():
            r = adb("-s", s_, "shell", body, timeout=timeout); o = ((r.stdout or "") + " " + (r.stderr or "")).strip()
    except Exception: o = ""
    finally:
        if rooted:
            try: adb("-s", s_, "unroot", timeout=20); back_up()
            except Exception: pass
    return o if "DG_END" in o and "DG_NOROOT" not in o else None
def _dg_event(name, port, before, after, kq, why=""):
    try:
        os.makedirs(os.path.dirname(DG_LOG), exist_ok=True)
        if os.path.isfile(DG_LOG) and os.path.getsize(DG_LOG) > 200000: os.replace(DG_LOG, DG_LOG + ".1")
        with open(DG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{port}\t{before}\t{after}\t{kq}\t{why}\n")
    except OSError: pass
def _dg_hostfree():
    try: return shutil.disk_usage(os.path.join(MUMU, "vms") if EMU == "mumu" and MUMU else HOME).free / 2**30
    except Exception: return None
DG_OK = 0.95                 # df báo nhỏ hơn cỡ hệ thống tệp ~2% (siêu dữ liệu ext4) → coi là đủ khi ≥ 95% cỡ đích
def disk_grow(port, name="", fix=True, want_gb=None):
    """Bộ nhớ /data của 1 máy đang chạy → (mã, chữ). want_gb = cỡ đích (GB). Mã: ok (đã đủ) · grown (vừa nới) · small (nhỏ, fix=False) ·
       noroot · nopart (phân vùng nhỏ hơn cỡ đích) · notext4 · hostlow (ổ máy chủ sắp đầy) · fail · ? (không đọc được) · skip (không phải MuMu / tắt)."""
    if EMU != "mumu" or not DISK_FIX: return "skip", ""
    if not want_gb:
        p = rec(name) if name else None
        want_gb = int((p or {}).get("disk_gb") or disk_tier((p or {}).get("ram")))
    want_gb = max(4, min(DISK_MAX, int(want_gb)))
    want = want_gb * 2**30; gb = lambda x: f"{x / 2**30:.1f}GB" if x else "?"
    st = _dg_state(port)
    if not st["total"]: return "?", "không đọc được /data (adb chưa nối / Android chưa lên)"
    if st["total"] >= want * DG_OK: return "ok", f"/data {gb(st['total'])}"
    if not fix: return "small", f"/data {gb(st['total'])} (trống {gb(st['avail'])})"
    try:
        with _Lock(f"disk_{int(port)}", wait=240):               # 19/11: 2 lệnh cùng nới 1 máy (mua thêm ↔ máy vừa bật) → lần lượt
            return _dg_grow_locked(port, name, want_gb, want, gb)
    except RuntimeError: return "?", "lệnh khác đang nới bộ nhớ máy này — thử lại sau"
def _dg_grow_locked(port, name, want_gb, want, gb):
    st = _dg_state(port)                                       # đọc lại trong khoá: lệnh khác có thể vừa nới xong
    if not st["total"]: return "?", "không đọc được /data (adb chưa nối / Android chưa lên)"
    if st["total"] >= want * DG_OK: return "ok", f"/data {gb(st['total'])}"
    if not _DG_DEV.match(st["dev"] or ""): return "?", f"không rõ ổ chứa /data ({st['dev'][:40] or 'không thấy'})"
    if st["fs"] != "ext4": return "notext4", f"/data kiểu {st['fs'] or '?'} — chỉ nới được ext4"
    if not st["part"] or st["part"] < want: return "nopart", f"phân vùng /data chỉ {gb(st['part'])} < {want_gb}GB"
    hf = _dg_hostfree()
    if hf is not None and hf < DISK_HOST_MIN:
        return "hostlow", f"ổ máy chủ chỉ còn {hf:.0f}GB trống (< {DISK_HOST_MIN:g}GB) — chưa nới, dọn ổ máy chủ trước"
    o = _dg_root(port, f"resize2fs {st['dev']} {want_gb}G 2>&1 | tail -3; sync; echo DG_END")
    if o is None:
        return "noroot", "máy không cho máy chủ quyền root (su / adb root) — nới tay: MuMu › Cài đặt thiết bị › Ổ đĩa › Dung lượng ổ › Mở rộng"
    st2 = _dg_state(port)
    if st2["total"] and st2["total"] >= want * DG_OK:
        _dg_event(name, port, st["total"], st2["total"], "grown")
        return "grown", f"/data {gb(st['total'])} → {gb(st2['total'])} (trống {gb(st2['avail'])})"
    why = " | ".join(x.strip() for x in o.replace("DG_END", "").splitlines() if x.strip())[-160:]
    _dg_event(name, port, st["total"], st2["total"], "fail", why)
    return "fail", f"resize2fs chưa nới được ({why or 'không rõ'}) · /data {gb(st2['total'] or st['total'])}"
DG_TRIES = 5
def _int0(x):
    try: return int(float(x or 0))
    except (TypeError, ValueError): return 0
def _disk_target(p):
    """Cỡ đích (GB) của 1 máy trong danh sách: dấu disk_new (máy mới / đã hẹn) → disk_gb → bậc theo RAM."""
    for k in ("disk_new", "disk_gb"):
        try:
            v = int(float((p or {}).get(k) or 0))
            if v >= 4: return min(v, DISK_MAX)
        except (TypeError, ValueError): pass
    return disk_tier((p or {}).get("ram"))
def _disk_hook(name, port):
    """Gọi sau khi máy vừa lên (wait_boot). CHỈ máy có dấu disk_new (máy MỚI, hoặc máy khách mua thêm lúc đang tắt / ngủ): /data nhỏ hơn
       cỡ đích → nới. Đã đủ / vừa nới → bỏ dấu, ghi disk_gb. Chưa nới được → giữ dấu, thử lại lần bật sau (tối đa DG_TRIES lần).
       Máy không có dấu → không làm gì. Không bao giờ ném lỗi."""
    try:
        p = rec(name)
        if not p or not p.get("disk_new"): return
        t = _disk_target(p)
        k, msg = disk_grow(port, name, want_gb=t)
        if k == "?": return                                    # chưa đọc được (adb / Android chưa sẵn) → để lần sau, không tính lần thử
        if k == "grown": print(f"   💾 {name}: bộ nhớ {msg}", flush=True)
        elif k not in ("ok", "skip") and (name, k) not in _DG_SAID:
            _DG_SAID.add((name, k)); print(f"   💾 {name}: bộ nhớ chưa đủ {t}GB — {msg}", flush=True)
        st = load(); q = rec(name, st)
        if not q: return
        if k in ("ok", "grown", "skip"):
            for x in ("disk_new", "disk_try", "disk_buy"): q.pop(x, None)
            if k != "skip": q["disk_gb"] = max(t, _int0(q.get("disk_gb")))
        else:
            q["disk_try"] = int(q.get("disk_try") or 0) + 1
            if q["disk_try"] >= DG_TRIES and not q.get("disk_buy"):     # máy khách đã MUA thêm: lần bật nào cũng thử tới khi được
                q.pop("disk_new", None); print(f"   💾 {name}: thôi tự nới bộ nhớ sau {DG_TRIES} lần ({k})", flush=True)
        save(st)
    except Exception as e: print(f"   (nới bộ nhớ lỗi: {e!r})"[:200], flush=True)
# 16/11k: trần "khung/giây tối đa" ghi vào máy MuMu — 0 (mặc định) = đúng FPS khách chọn. Chỉ dùng khi chẩn đoán (bluestream --kiemhinh)
# thấy bộ nén trong máy ra hình hỏng ở FPS cao: phonectl setconf MUMU_FPS_CAP=60 rồi khởi động lại các máy đó.
try: MUMU_FPS_CAP = max(0, int(float(CONF.get("MUMU_FPS_CAP", "0") or 0)))
except ValueError: MUMU_FPS_CAP = 0
def configure(idx, ram, cpu, res, dpi):
    w, h = res.lower().split("x")
    if EMU == "ld":
        if float(ram) > MAX_RAM: print(f"   (gói {float(ram):g}GB → LDPlayer chạy tối đa {MAX_RAM:g}GB/máy, đặt {MAX_RAM:g}GB)", flush=True)
        mb = int(min(float(ram), MAX_RAM) * 1024); mb = max([m for m in LD_MEM if m <= mb] or [1024])
        c = max(1, int(round(min(float(cpu), MAX_CPU))))
        d = int(dpi or auto_dpi(res))
        _ldrun(["modify", "--index", idx, "--resolution", f"{w},{h},{d}", "--cpu", min(c, 4), "--memory", min(mb, 8192), "--root", "1"], 60)
        ld_cfg(idx, **{"advancedSettings.cpuCount": c, "advancedSettings.memorySize": mb,
                       "advancedSettings.resolution": {"width": int(w), "height": int(h)}, "advancedSettings.resolutionDpi": d})
        _ldrun(["globalsetting", "--audio", "0", "--fps", CONF.get("LD_FPS", "60")], 60)
        return
    if EMU == "mumu":
        if float(ram) > MAX_RAM: print(f"   (gói {float(ram):g}GB → MuMu chạy tối đa {MAX_RAM:g}GB/máy, đặt {MAX_RAM:g}GB)", flush=True)
        _mumu_set(str(idx), {"res": (int(w), int(h), int(dpi or auto_dpi(res))), "root": 1, **MUMU_PERF})
        ok, msg = _mumu_hw(str(idx), max(1, int(round(min(float(cpu), MAX_CPU)))), min(float(ram), MAX_RAM))
        print(f"   {'✓' if ok else '⚠'} MuMu #{idx}: {msg}", flush=True)
        return
    if float(ram) > MAX_RAM: print(f"   (gói {float(ram):g}GB → MEmu chỉ chạy tối đa {MAX_RAM:g}GB/máy, đặt {MAX_RAM:g}GB)", flush=True)
    ram = min(float(ram), MAX_RAM); cpu = min(float(cpu), MAX_CPU)
    for k, v in (("memory", int(float(ram) * 1024)), ("cpus", max(1, int(round(float(cpu))))), ("is_customed_resolution", 1),
                 ("resolution_width", w), ("resolution_height", h), ("vbox_dpi", int(dpi or auto_dpi(res))), ("enable_su", 1),
                 ("graphics_render_mode", CONF.get("MEMU_RENDER", "1")),          # 1 = DirectX: MƯỢT (OpenGL 0 thấy 3D trên web nhưng máy vẽ chậm gấp nhiều lần)
                 ("gmem_opt", CONF.get("MEMU_GMEM_OPT", "1")),                    # GPU memory optimization: BẬT (game cần). Tắt: MEMU_GMEM_OPT=0
                 ("enable_audio", 0)):                                            # máy cloud không cần âm thanh → đỡ CPU
        memuc("setconfigex", "-i", idx, k, v, timeout=60)

# ---------- MÁY MẪU: admin chỉnh tay 1 máy trong MEmu (GPU memory optimization, ASTC, chế độ vẽ…) → máy mới chép y cài đặt đó ----------
TPL_KEYS = re.compile(r"gpu|astc|render|graphic|opt|turbo|vulkan|cache|vk_|egl|gles", re.I)
TPL_SKIP = {"memory", "cpus", "fps", "enable_su", "resolution_width", "resolution_height", "vbox_dpi", "is_customed_resolution"}
def memu_file(idx):
    root = os.path.join(MEMU, "MemuHyperv VMs"); nm = "MEmu" if int(idx) == 0 else f"MEmu_{int(idx)}"
    f = os.path.join(root, nm, nm + ".memu")
    return f if os.path.isfile(f) else ""
def memu_props(idx):
    f = memu_file(idx)
    if not f: return {}
    t = open(f, encoding="utf-8", errors="replace").read()
    return {m.group(1): m.group(2) for m in re.finditer(r'GuestProperty\s+name="([^"]+)"\s+value="([^"]*)"', t)}
def template_props():
    name = CONF.get("MEMU_TEMPLATE", "")
    if not name: return {}
    i = next((k for k, x in vms().items() if x["name"] == name), None)
    if i is None: return {}
    return {k: v for k, v in memu_props(i).items() if TPL_KEYS.search(k) and k not in TPL_SKIP}
def apply_template(idx, quiet=False):
    props = template_props()
    for k, v in props.items(): memuc("setconfigex", "-i", idx, k, v, timeout=60)
    if props and not quiet: print(f"   🧩 chép {len(props)} cài đặt từ máy mẫu '{CONF.get('MEMU_TEMPLATE')}'", flush=True)
    return props

def booted(port):
    r = adb("-s", f"127.0.0.1:{port}", "shell", "getprop sys.boot_completed", timeout=15)
    return (r.stdout or "").strip() == "1"

# ---------- 16/11k: SỔ KHOÁ ANDROID (keystore2) HỎNG → Android sập / tự khởi động lại liên tục ----------
# 16/11 (máy chủ 156): máy mới vừa giao 7 giây thì keystore2 văng "Failed to open database ... persistent ... file is not a database
# (Error code 26)" → system_server chết theo (DeadSystemException) → màn đen, adb offline, khách chờ hàng giờ; máy nào tạo ra cũng bị.
# File /data/misc/keystore/persistent.sqlite hỏng (máy mẫu / máy bị tắt ngang lúc đang ghi → đầu file toàn số 0) → mọi máy nhân bản
# từ đó mang file hỏng. Sửa: đầu file KHÔNG phải "SQLite format 3" → xoá file hỏng (Android tự tạo lại file mới; máy mới không mất gì,
# máy đang sập vốn đã không dùng được) → khởi động lại Android 1 lần → chờ lên lại. File tốt / chưa có file → không đụng gì.
KS_DB = "/data/misc/keystore/persistent.sqlite"
KS_FIX = str(CONF.get("KS_FIX", "1")).strip() != "0"         # 0 = chỉ báo, không tự sửa
# 16/11k2 — bản 16/11k chưa cứu được máy 156: máy hỏng sổ khoá KHỞI ĐỘNG LẠI LIÊN TỤC, không bao giờ tới "Android đã lên" (chỗ bản k
# mới kiểm), adb chỉ nối được vài chục giây mỗi vòng rồi "offline" (adb còn giữ đường nối cũ → phải gỡ nối + nối lại). Giờ:
#   · lệnh kiểm + xoá file hỏng gộp trong MỘT lệnh adb (kịp trong lúc adb vừa nối được), không có dấu nháy nào trong lệnh (qua adb + su
#     kiểu gì cũng không vỡ), chỉ chạy tiếp khi ĐANG LÀ ROOT, đọc file lỗi thì KHÔNG xoá;
#   · thử lần lượt 3 cách có quyền root: "su -c" · "su 0 sh -c" · adb đã là root — nhớ cách chạy được;
#   · MỌI chỗ chờ Android lên (tạo máy, khởi động lại, bật máy, khách mở máy) đều canh: adb vừa nối là kiểm + sửa ngay;
#   · chống kẹt (bảng ~2 phút/lần) cũng canh; lệnh ksfix canh tới khi nối được (mặc định 5 phút), không nối được thì khởi động lại máy rồi canh tiếp.
# 17/11g — FILE HỆ THỐNG ANDROID HỎNG. Máy chủ bị tắt ngang (mất điện / bấm reset / sập) lúc máy khách đang chạy → file Android đang ghi
# dở thành file RỖNG → system_server sập ngay lúc khởi động ("Missing <roles> in roles.xml"), zygote bật lại ~7 giây / vòng, Android không
# bao giờ lên, MuMu báo VERR_ROM_START_TIMEOUT, khách thấy quay mãi (18/11 máy chủ 156: 5 lần tắt ngang trong 50 phút). File THIẾU thì
# Android tự tạo lại như lần bật đầu → trong CÙNG lệnh root với kiểm sổ khoá: Android CHƯA lên mà file có đó nhưng rỗng / không chứa tên
# thẻ của chính nó → ĐỔI TÊN sang .hong (không xoá). Máy đã lên (boot_completed = 1) không bao giờ bị đụng. Tắt: BOOT_FIX=0 (chỉ báo).
BOOT_FIX = str(CONF.get("BOOT_FIX", "1")).strip() != "0"
BF_DIR = "/data/misc_de/0/apexdata/com.android.permission"
BF_FILES = ("roles", "runtime-permissions")                    # <tên>.xml — thẻ gốc trong file cùng tên
def _bf_sh(fix):
    act = "elif mv $P $P.hong; then sync; echo BF_FIXED_$X; else echo BF_FAIL_$X; " if fix else "else echo BF_BAD_$X; "
    return ("if [ x$(getprop sys.boot_completed) != x1 ]; then for X in " + " ".join(BF_FILES) + "; do P=" + BF_DIR + "/$X.xml; "
            "if [ -e $P ]; then if [ -s $P ] && grep -q $X $P; then :; " + act + "fi; fi; done; fi; ")
_KS_ROOT_SH = "[ $(id -u) = 0 ] || { echo KS_NOROOT; exit 0; }; "
_KS_BODY = ("F=" + KS_DB + "; if [ ! -e $F ]; then echo KS_NOFILE; elif [ ! -s $F ]; then echo KS_EMPTY; "
            "elif ! H=$(head -c 6 $F); then echo KS_ERR; elif [ x$H = xSQLite ]; then echo KS_OK; else echo KS_BAD $(stat -c %s $F 2>/dev/null); ")
_KS_HEAD = _KS_ROOT_SH + _KS_BODY
_KS_SH = _KS_ROOT_SH + _bf_sh(False) + _KS_BODY + "fi"         # chỉ kiểm (sổ khoá + file hệ thống)
_KS_FIX_SH = (_KS_ROOT_SH + _bf_sh(BOOT_FIX) + _KS_BODY        # kiểm + sửa: đổi tên file hệ thống hỏng (BOOT_FIX) · xoá sổ khoá hỏng (KS_FIX)
              + ("rm -f $F $F-wal $F-shm $F-journal; sync; if [ -e $F ]; then echo KS_RMFAIL; else echo KS_FIXED; fi; " if KS_FIX else "") + "fi")
_BF_HIT = {}                                                   # cổng → {"n": số lần vừa sửa, "t": lúc sửa, "fixed" / "bad" / "fail": [tên file], "said": đã báo}
def _port_name(port):
    try: return next((str(p["name"]) for p in load()["phones"] if str(p.get("port")) == str(port)), f"máy cổng {port}")
    except Exception: return f"máy cổng {port}"
def _bf_parse(port, o):
    """Đọc dấu BF_… trong chữ lệnh root trả về → in 1 dòng + ghi nhật ký cho mỗi phát hiện mới. Không bao giờ ném lỗi."""
    try:
        got = {"FIXED": [], "BAD": [], "FAIL": []}
        for k, f in re.findall(r"BF_(FIXED|BAD|FAIL)_([a-z][a-z-]*)", o or ""):
            if f in BF_FILES and f not in got[k]: got[k].append(f)
        h = _BF_HIT.setdefault(port, {"n": 0, "said": set()})
        h["fixed"], h["bad"], h["fail"] = got["FIXED"], got["BAD"], got["FAIL"]
        if not any(got.values()): return
        nm = _port_name(port); ff = lambda L: ", ".join(x + ".xml" for x in L)
        if got["FIXED"]:
            h["n"] += 1; h["t"] = time.time(); h["last"] = list(got["FIXED"])
            print(f"   📄 {nm}: file hệ thống Android HỎNG do máy chủ bị tắt ngang ({ff(got['FIXED'])}) → đã đổi tên file hỏng, Android tự tạo lại "
                  "và khởi động tiếp (1–2 phút)", flush=True)
            _ks_event(nm, "file hệ thống hỏng: " + ff(got["FIXED"]))
            try: _restart_write(nm)                           # phát hình báo khách "máy đang khởi động lại, tự vào khi xong"
            except Exception: pass
        for k, txt in (("BAD", "→ Android sập liên tục, không lên" + ("" if BOOT_FIX else " (BOOT_FIX=0 → chỉ báo, không tự sửa)")),
                       ("FAIL", "nhưng CHƯA đổi tên được file hỏng")):
            new = [x for x in got[k] if (k, x) not in h["said"]]
            if new:
                h["said"].update((k, x) for x in new)
                print(f"   📄 {nm}: file hệ thống Android HỎNG ({ff(new)}) {txt}", flush=True)
    except Exception: pass
def _sig_of(txt):
    """Dấu hiệu Android sập lúc khởi động: dòng "Caused by" cuối của khối FATAL EXCEPTION (ưu tiên IN SYSTEM PROCESS) gần nhất. '' = không có."""
    L = (txt or "").splitlines()
    k = max((i for i, x in enumerate(L) if "FATAL EXCEPTION IN SYSTEM PROCESS" in x), default=-1)
    if k < 0: k = max((i for i, x in enumerate(L) if "FATAL EXCEPTION" in x), default=-1)
    if k < 0: return ""
    blk = L[k:k + 80]; cb = [x for x in blk if "Caused by:" in x]
    line = cb[-1] if cb else (blk[1] if len(blk) > 1 else blk[0])
    line = re.sub(r"^.*?(?:AndroidRuntime|DEBUG)\s*:\s*", "", line).strip()
    return re.sub(r"^Caused by:\s*", "", line)[:200]
def _bf_sig(port, n=300):
    """Dấu hiệu sập đọc từ logcat của máy (không cần root). '' = không thấy / không nối được."""
    try: return _sig_of(adb("-s", f"127.0.0.1:{port}", "shell", f"logcat -d -b crash -t {int(n)}", timeout=20).stdout or "")
    except Exception: return ""
_KS_METHODS = ("su -c", "su 0 sh -c", "")                     # su kiểu MuMu / Magisk · su kiểu AOSP · adb đã là root (chạy thẳng)
_KS_ROOT = {}                                                  # cổng → cách đã chạy được
_KS_WHY = {}                                                   # cổng → vì sao lần gần nhất chưa kiểm được
_KS_SIZE = {}                                                  # cổng → cỡ file hỏng vừa thấy (ghi nhật ký)
_KS_DONE = {}                                                  # tên máy → số lần đã sửa trong lệnh này (chống vòng lặp)
KS_LOG = os.path.join(HOME, "redroid", "ks_events.log")
def _last(o, n=70): return ((o or "").strip().splitlines() or ["không trả lời"])[-1].strip()[:n]
def _adb_gone(o):
    """Chữ adb trả về cho biết KHÔNG nối được máy (khác với lệnh trong máy báo lỗi)."""
    low = (o or "").lower()
    return ("device offline" in low or ("device '" in low and "not found" in low) or "no devices" in low or "error: closed" in low
            or "cannot connect" in low or "connection reset" in low or "protocol fault" in low or "device unauthorized" in low)
def _ks_exec(port, script, timeout=12):
    """Chạy script bằng ROOT trong máy: thử cách đã nhớ trước rồi tới các cách còn lại. Trả (mã KS_… cuối cùng hoặc "", chữ trả về).
       adb báo offline → gỡ nối + nối lại (lần gọi sau dùng đường nối mới). Không bao giờ ném lỗi."""
    s_ = f"127.0.0.1:{port}"; last = ""
    order = ([_KS_ROOT[port]] if port in _KS_ROOT else []) + [m for m in _KS_METHODS if m != _KS_ROOT.get(port, None)]
    for pre in order:
        try: r = adb("-s", s_, "shell", script if pre == "" else f"{pre} '{script}'", timeout=timeout)
        except Exception as e: _KS_WHY[port] = f"adb lỗi {e}"[:90]; return "", ""
        o = ((r.stdout or "") + " " + (r.stderr or "")).strip(); last = o
        toks = re.findall(r"KS_[A-Z]+", o)
        if toks and toks[-1] != "KS_NOROOT":
            _KS_ROOT[port] = pre; _KS_WHY.pop(port, None)
            m = re.search(r"KS_BAD (\d+)", o)
            if m: _KS_SIZE[port] = int(m.group(1))
            _bf_parse(port, o)                                # 17/11g: file hệ thống Android hỏng (đã đổi tên / chỉ báo)
            return toks[-1], o
        if not toks and (_adb_gone(o) or r.returncode == 124):
            _KS_WHY[port] = "adb chưa nối được máy (" + _last(o, 50) + ")" if r.returncode != 124 else "máy không trả lời lệnh adb (quá giờ)"
            if "offline" in o.lower():                        # adb còn giữ đường nối cũ từ trước khi máy khởi động lại → nối lại từ đầu
                try: adb("disconnect", s_, timeout=10); adb("connect", s_, timeout=15)
                except Exception: pass
            return "", o
    _KS_ROOT.pop(port, None)
    _KS_WHY[port] = "máy chưa cho máy chủ quyền root (" + _last(last, 60) + ")"
    return "", last
_KS_MAP = {"KS_BAD": "bad", "KS_RMFAIL": "bad", "KS_OK": "ok", "KS_NOFILE": "none", "KS_EMPTY": "none", "KS_FIXED": "fixed"}
def keystore_state(port):
    """"ok" · "bad" (hỏng → Android sập liên tục) · "none" (chưa có file / file rỗng — bình thường) · "?" (chưa kiểm được — lý do ở _KS_WHY)."""
    tok, o = _ks_exec(port, _KS_SH)
    if tok == "KS_ERR": _KS_WHY[port] = "không đọc được file sổ khoá (lệnh head lỗi) — không đụng"
    return _KS_MAP.get(tok, "?")
def _ks_fix_now(port):
    """Kiểm + XOÁ file hỏng trong cùng 1 lệnh adb → "fixed" (vừa xoá file hỏng) · "ok" · "none" · "bad" (hỏng mà không xoá được) · "?"."""
    tok, o = _ks_exec(port, _KS_FIX_SH, timeout=20)
    if tok == "KS_ERR": _KS_WHY[port] = "không đọc được file sổ khoá (lệnh head lỗi) — không đụng"
    return _KS_MAP.get(tok, "?")
def _ks_reboot(port, off=False):
    """Khởi động lại (off=True: tắt hẳn) Android bằng root — làm được thì tốt, không được thì máy đang sập cũng tự khởi động lại."""
    pre = _KS_ROOT.get(port, "su -c"); c = "reboot -p" if off else "reboot"
    try: adb("-s", f"127.0.0.1:{port}", "shell", c if pre == "" else f"{pre} '{c}'", timeout=12)
    except Exception: pass
def _ks_noroot(port):
    """Lần kiểm gần nhất: adb NỐI ĐƯỢC nhưng máy không cho máy chủ quyền root (VD máy Android 15 dùng KernelSU giấu su với adb) → không kiểm / sửa được."""
    return "quyền root" in _KS_WHY.get(port, "")
def _ks_event(name, why, port=None):
    """Ghi 1 dòng vào redroid/ks_events.log (lệnh A đọc để báo admin: máy nào bị, lúc nào, lúc đang làm gì)."""
    try:
        os.makedirs(os.path.dirname(KS_LOG), exist_ok=True)
        if os.path.isfile(KS_LOG) and os.path.getsize(KS_LOG) > 200000: os.replace(KS_LOG, KS_LOG + ".1")
        with open(KS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{why or '-'}\t{_KS_SIZE.get(port, '')}\n")
    except OSError: pass
def _boot_id(port):
    o = (adb("-s", f"127.0.0.1:{port}", "shell", "cat /proc/sys/kernel/random/boot_id", timeout=12).stdout or "").strip()
    return o if re.fullmatch(r"[0-9a-fA-F-]{20,40}", o) else ""
def _ss_pid(port):
    """PID của system_server (giao diện Android) — đổi số = giao diện vừa sập / khởi động lại. "" = chưa chạy / không đọc được."""
    o = (adb("-s", f"127.0.0.1:{port}", "shell", "pidof system_server", timeout=12).stdout or "").strip().split()
    return o[0] if o and o[0].isdigit() else ""
def _fw_wait(port, old_pid="", wait=180):
    """Chờ giao diện Android lên THẬT sau "stop; start" (sys.boot_completed vẫn = 1 nên không tin được): system_server chạy với PID
       MỚI + gói android trả lời + màn khởi động (bootanim) đã tắt. Trả True khi xong."""
    t0 = time.time(); s_ = f"127.0.0.1:{port}"
    while time.time() - t0 < wait:
        adb_connect(port)
        pid = _ss_pid(port)
        if pid:
            o = adb("-s", s_, "shell", "getprop init.svc.bootanim; pm path android", timeout=15).stdout or ""
            up = "package:" in o and "running" not in o
            if up and (pid != old_pid or not old_pid or time.time() - t0 > 25): return True   # PID cũ sau 25 giây = giao diện không hề khởi động lại
        time.sleep(3)
    return False
def _adb_fresh(port):
    """adb báo máy "offline" (đường nối cũ từ trước khi máy khởi động lại — `adb connect` chỉ trả "already connected") → gỡ nối + nối lại.
       Trả True nếu máy đang ở trạng thái device."""
    s_ = f"127.0.0.1:{port}"
    try:
        r = adb("-s", s_, "get-state", timeout=10); o = ((r.stdout or "") + " " + (r.stderr or "")).lower().strip()
        if o.startswith("device"): return True
        if "offline" in o: adb("disconnect", s_, timeout=10)
        adb("connect", s_, timeout=15)
    except Exception: pass
    return False
def _wait_reboot(name, port, old_bid, p=None, wait=None):
    """Sau lệnh khởi động lại Android: chờ lên lại ở lần khởi động MỚI (boot_id đổi, hoặc đã thấy máy xuống rồi lên lại).
       Máy ảo lỡ TẮT hẳn (giả lập coi reboot là tắt máy) → bật lại. Không đọc được boot_id cũ mà 90 giây máy vẫn "đã lên" → coi là xong."""
    wait = wait or BOOT_WAIT; t0 = time.time(); started = False; down = False
    while time.time() - t0 < wait:
        time.sleep(4)
        _adb_fresh(port)
        bid = _boot_id(port); up = bool(bid) and booted(port)
        if not bid or not up or (old_bid and bid != old_bid): down = True
        if up and (down or time.time() - t0 > 90): return True
        if not bid and not started and time.time() - t0 > 60:
            try:
                q = p or rec(name)
                if q and not is_running(name, q):
                    print(f"   ({name}: máy ảo tắt hẳn sau lệnh khởi động lại → bật lại)", flush=True)
                    start_phone(q); started = True
            except Exception: pass
    return False
def _ks_after_fix(name, port, p=None, why="", wait=None):
    """Vừa xoá file sổ khoá hỏng → ghi nhật ký, báo "đang khởi động lại", khởi động lại Android, chờ lên lại. True = Android đã lên lại."""
    _KS_DONE[name] = _KS_DONE.get(name, 0) + 1
    sz = _KS_SIZE.get(port)
    print(f"   🔑 {name}: sổ khoá Android (keystore) HỎNG{(' — ' + why) if why else ''}" + (f" (file {sz} byte)" if sz else "")
          + " → đã xoá file hỏng, khởi động lại Android (1–3 phút)…", flush=True)
    _ks_event(name, why, port)
    _restart_write(name)                                      # phát hình báo khách "máy đang khởi động lại, tự vào khi xong"
    bid = _boot_id(port)
    _ks_reboot(port)
    ok = _wait_reboot(name, port, bid, p, wait)
    st_ = keystore_state(port) if ok else "?"
    print(f"      {'✓' if ok and st_ != 'bad' else '✗'} {name}: " + ("Android đã lên lại, sổ khoá " + {"ok": "tốt", "none": "mới (tốt)", "bad": "VẪN HỎNG", "?": "chưa kiểm lại được"}[st_]
                                                if ok else "Android chưa lên lại sau khi sửa (máy chủ bận?) — chống kẹt sẽ canh tiếp"), flush=True)
    return ok and st_ != "bad"
def keystore_heal(name, port, p=None, why="", state=None):
    """Sổ khoá hỏng → xoá file hỏng + khởi động lại Android + chờ lên lại. True = đã sửa xong (Android đã lên lại).
       False = không hỏng / không sửa được (không bao giờ ném lỗi)."""
    try:
        if EMU == "ld": return False                          # Android 9: keystore kiểu cũ (không có file này)
        if not (KS_FIX or BOOT_FIX) or _KS_DONE.get(name, 0) >= 2:
            if keystore_state(port) == "bad":
                print(f"   🔑 {name}: sổ khoá Android (keystore) HỎNG{(' — ' + why) if why else ''} → Android sẽ sập liên tục (màn đen)", flush=True)
                print("      (KS_FIX=0 → chỉ báo, không tự sửa)" if not KS_FIX else "      ✗ đã sửa 2 lần trong lệnh này mà vẫn hỏng → dừng (báo Claude)", flush=True)
            return False
        r = _ks_fix_now(port)                                 # 17/11g: cùng lệnh này cũng đổi tên file hệ thống hỏng (BOOT_FIX), kể cả khi KS_FIX=0
        if r == "bad":
            print(f"   🔑 {name}: sổ khoá Android (keystore) HỎNG{(' — ' + why) if why else ''}"
                  + (" — ✗ chưa xoá được file hỏng" if KS_FIX else " → Android sẽ sập liên tục (màn đen) · KS_FIX=0 → chỉ báo, không tự sửa"), flush=True)
        if r != "fixed": return False
        return _ks_after_fix(name, port, p, why)
    except Exception as e:
        print(f"   (kiểm sổ khoá {name} lỗi: {e})", flush=True); return False
def _wait_android(name, port, p=None, wait=None, step=3, why="lúc chờ Android lên", info=None):
    """Chờ Android lên xong (sys.boot_completed = 1) → True / quá giờ → False. TRONG LÚC CHỜ: adb vừa nối được là kiểm + sửa sổ khoá
       ngay (máy hỏng sổ khoá khởi động lại liên tục, KHÔNG BAO GIỜ tới boot_completed — bản 16/11k chờ tới đó mới kiểm nên không cứu được).
       Sửa xong → khởi động lại Android → chờ lên lại (tính lại đủ giờ chờ)."""
    wait = wait or BOOT_WAIT; t0 = time.time(); ks = None; tp = 0.0; nr = 0
    poke = EMU != "ld" and (KS_FIX or BOOT_FIX)
    bf0 = _BF_HIT.get(port, {}).get("n", 0)
    while time.time() - t0 < wait:
        seen = _adb_fresh(port)
        up = booted(port)
        if info is not None and (seen or up): info["adb"] = True     # 17/11f: adb đã nối được ít nhất 1 lần (máy ảo có chạy, Android đang lên)
        if poke and ks is None and _KS_DONE.get(name, 0) < 2 and (up or time.time() - tp >= 4):
            tp = time.time()
            try: r = _ks_fix_now(port)
            except Exception: r = "?"
            bn = _BF_HIT.get(port, {}).get("n", 0)
            if bn != bf0: bf0 = bn; t0 = time.time()        # 17/11g: vừa đổi tên file hệ thống hỏng → Android khởi động tiếp, tính lại đủ giờ chờ
            if r == "fixed": return _ks_after_fix(name, port, p, why, wait)
            if r in ("ok", "none", "bad"): ks = r
            elif _ks_noroot(port):                            # adb nối được mà không có root (Android 15 / KernelSU) → thôi canh, chờ như cũ
                nr += 1
                if nr >= 2: ks = "noroot"
        if up: return True
        time.sleep(step)
    return False
KS_OK_F = os.path.join(HOME, "redroid", "ks_ok.json")
_KS_OK_VER = "|g"                                              # 17/11g: lệnh kiểm có thêm phần file hệ thống → dấu cũ không còn tính
def _ks_ok_load():
    try:
        with open(KS_OK_F, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def _ks_ok_put(nm, bid):
    try:
        d = _ks_ok_load(); d[nm] = bid
        os.makedirs(os.path.dirname(KS_OK_F), exist_ok=True); tmp = KS_OK_F + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f)
        os.replace(tmp, KS_OK_F)
    except OSError: pass
def _ks_tick(nm, p, tries=3):
    """Chống kẹt (bảng gọi ~2 phút/lần): máy đang chạy → kiểm + sửa sổ khoá. Máy tốt chỉ kiểm 1 LẦN mỗi lần Android khởi động (nhớ boot_id).
       Máy chưa nối được (đang khởi động lại liên tục) → canh vài nhịp. True = vừa xoá file hỏng + đã gửi lệnh khởi động lại (không chờ)."""
    port = p["port"]
    for k in range(max(1, tries)):
        bid = _boot_id(port)
        if bid and _ks_ok_load().get(nm) == bid + _KS_OK_VER: return False
        b0 = _BF_HIT.get(port, {}).get("n", 0)
        r = _ks_fix_now(port)
        hb = _BF_HIT.get(port, {})
        if hb.get("n", 0) != b0 and r in ("ok", "none", "bad"):   # 17/11g: vừa đổi tên file hệ thống hỏng → Android tự khởi động tiếp (không cần lệnh khởi động lại)
            print(f"KHOI_DONG_LAI {nm}: file hệ thống Android hỏng do máy chủ bị tắt ngang (" + ", ".join(x + ".xml" for x in hb.get("last") or [])
                  + ") → đã đổi tên file hỏng, Android tự tạo lại và khởi động tiếp", flush=True)
            return True
        if r in ("ok", "none"):
            if bid: _ks_ok_put(nm, bid + _KS_OK_VER)
            return False
        if r == "fixed":
            _KS_DONE[nm] = _KS_DONE.get(nm, 0) + 1
            print(f"KHOI_DONG_LAI {nm}: sổ khoá Android hỏng (máy sập / khởi động lại liên tục) → đã xoá file hỏng + khởi động lại Android", flush=True)
            _ks_event(nm, "chống kẹt", port); _restart_write(nm); _ks_reboot(port)
            return True
        if r == "bad": return False
        if _ks_noroot(port):                                  # không có root cho máy chủ → nhớ cho lần khởi động này, khỏi thử lại mỗi 2 phút
            if bid: _ks_ok_put(nm, bid + _KS_OK_VER)
            return False
        if k + 1 < tries: time.sleep(3); _adb_fresh(port)
    return False
def _guest_sync(idx):
    """16/11k2: trước khi TẮT máy ảo (giả lập tắt ngang như rút điện) → bảo Android ghi hết dữ liệu đang chờ xuống đĩa. Tắt ngang lúc đang
       ghi dở là 1 đường làm hỏng file (sổ khoá, dữ liệu app). Không nối được adb thì bỏ qua (tối đa 6 giây)."""
    try: adb("-s", f"127.0.0.1:{port_of(idx)}", "shell", "sync", timeout=6)
    except Exception: pass

def wait_boot(name, port, apps=True):
    ok = _wait_android(name, port, why="lúc máy vừa bật")   # 16/11k2: canh + sửa sổ khoá ngay trong lúc chờ (giữ suất khởi động)
    _boot_done(name)                                     # Android lên (hoặc quá giờ) → trả suất khởi động cho máy khác
    if ok:
        try: set_wallpaper(name, port)
        except Exception as e: print("   (ảnh nền lỗi:", e, ")")
        sp0 = _ss_pid(port) if EMU != "ld" else ""
        try: hide_window(name)
        except Exception: pass
        tune(name, port); grant_perms(name, port)
        _root_keep({"name": name}, port)
        _proxy_keep({"name": name}, port)                # 22/11: máy có 🌐 proxy riêng → bật lại (iptables + tiến trình mất khi máy tắt)
        if EMU == "mumu" and DISK_FIX: _disk_hook(name, port)     # 19/11: máy MỚI / máy vừa mua thêm bộ nhớ (có dấu disk_new) → nới tới cỡ đích
        if sp0:                                          # 16/11k: giao diện sập giữa lúc tối ưu (PID đổi) → kiểm sổ khoá lần nữa, chờ lên lại
            sp1 = _ss_pid(port)
            if sp1 != sp0:
                print(f"   ⚠ {name}: giao diện Android vừa sập / khởi động lại giữa chừng → kiểm lại trước khi giao", flush=True)
                if not keystore_heal(name, port, why="giao diện sập"): _fw_wait(port, sp0, 120)
                android_ready(port, 60)
        if apps: preinstall(name, port)
    return ok

# ---------- cài app sẵn: mọi file .apk trong <BLUE>\apk-cai-san ----------
def preinstall(name, port, force=False):
    d = os.path.join(HOME, "apk-cai-san")
    if not os.path.isdir(d): return
    have = adb("-s", f"127.0.0.1:{port}", "shell", "pm list packages -3", timeout=60).stdout or ""
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".apk"): continue
        mark = os.path.join(HOME, "redroid", f"pre_{name}_{f}.ok")
        if os.path.exists(mark) and not force: continue
        r = adb("-s", f"127.0.0.1:{port}", "install", "-r", "-g", os.path.join(d, f), timeout=900)
        print(("+ " if "Success" in (r.stdout or "") else "! ") + f"{name}: {f}")
        if "Success" in (r.stdout or ""): open(mark, "w").close()

# ---------- lệnh ----------
def cmd_create(a):
    st = load()
    if rec(a.name, st): print("LỖI: đã có máy tên này."); sys.exit(1)
    if not SAFE.match(a.name): print("LỖI: tên máy chỉ gồm chữ, số, _ . -"); sys.exit(1)
    if not re.match(r"^\d+x\d+$", a.res): print("LỖI: --res phải dạng 720x1280."); sys.exit(1)
    if not MEMU: print("LỖI: không thấy MEmu (memuc.exe)."); sys.exit(4)
    tot, av = mem(); zz = _sleep_ram(st); av -= zz                # máy đang NGỦ sẽ bật lại khi khách mở → RAM của chúng không bán cho máy mới
    need = min(float(a.ram), MAX_RAM)                     # MEmu chạy tối đa 16GB/máy → chỉ cần đủ RAM cho phần thật sự cấp
    if av - (need + 1) < RESERVE:
        print(f"HẾT HÀNG: RAM Windows còn {av:.1f}GB" + (f" (đã chừa {zz:.1f}GB cho máy đang ngủ)" if zz else "")
              + f", máy {need:g}GB cần thêm {need + 1:g}GB và chừa {RESERVE:g}GB."); sys.exit(2)
    try: open(os.path.join(HOME, "redroid", f"creating_{os.getpid()}.flag"), "w").write(a.name)   # báo "đang tạo máy khách" → dựng máy sẵn nhường đường
    except OSError: pass
    ver = norm_android(a.android)
    sp = take_spare(a.name) if ver == DEF_ANDROID else None          # máy dựng sẵn là bản Android mặc định của máy chủ
    if sp is not None:
        idx = sp
        print(f"[1/4] ⚡ Dùng máy dựng sẵn (MEmu #{idx}) → đổi tên, RAM, CPU…", flush=True)
        with _Lock("memu", wait=1500):
            dpi = a.dpi or auto_dpi(a.res)
            configure(idx, a.ram, a.cpu, a.res, dpi)
            memuc("setconfigex", "-i", idx, "fps", clamp_fps(a.fps), timeout=60)
            apply_template(idx)
    else:
        print(f"[1/4] Tạo máy Android {ver} trên {EMU_NAME}…", flush=True)
        with _Lock("memu", wait=1500):
            for oi, ox in sorted(vms().items(), reverse=True):   # máy trùng tên còn sót trong MEmu (lần tạo trước bị ngắt) → xoá trước
                if ox["name"] == a.name:
                    print(f"   (xoá máy sót cùng tên #{oi})", flush=True); memuc("stop", "-i", oi, timeout=60); memuc("remove", "-i", oi, timeout=180)
            r, idx = create_vm(ver, a.name)
            if idx is None:
                print("LỖI tạo máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-300:])
                print("LÝ DO:", _fail_reason(r), flush=True); sys.exit(4)
            print(f"[2/4] Đã tạo máy #{idx} → đặt tên, RAM, CPU, root…", flush=True)
            for _t in range(4):                                          # đổi tên PHẢI thành công — máy tìm theo TÊN (không thì thành "MEmuNN" mồ côi)
                memuc("rename", "-i", idx, a.name, timeout=60)
                if (vms().get(idx) or {}).get("name") == a.name: break
                time.sleep(3)
            else:
                print(f"LỖI: MEmu không đổi tên được máy #{idx} → xoá máy dở", flush=True)
                memuc("remove", "-i", idx, timeout=180); sys.exit(4)
            dpi = a.dpi or auto_dpi(a.res)
            configure(idx, a.ram, a.cpu, a.res, dpi)
            memuc("setconfigex", "-i", idx, "fps", clamp_fps(a.fps), timeout=60)
            apply_template(idx)
    port = port_of(idx); exp = now() + datetime.timedelta(days=a.days)
    if getattr(a, "until", ""):                     # đổi Android: máy mới giữ ĐÚNG hạn của máy cũ (không làm tròn lên cả ngày)
        try:
            u = parse_dt(a.until)
            if now() < u <= now() + datetime.timedelta(days=a.days + 1): exp = u
        except Exception: pass
    row = {"name": a.name, "idx": idx, "port": port, "ram": a.ram, "cpu": a.cpu, "res": a.res, "fps": clamp_fps(a.fps), "dpi": dpi,
           "android": ver, "kind": EMU, "created": fmt(now()), "expires": exp.isoformat()}
    if EMU == "mumu" and DISK_FIX:                                  # 19/11: máy MỚI → lần đầu lên tự nới bộ nhớ (máy cũ không có dấu)
        dg = _int0(getattr(a, "disk", 0))
        row["disk_new"] = min(dg, DISK_MAX) if dg >= 4 else disk_tier(a.ram)     # web truyền cỡ đã tính (bậc RAM + phần khách mua) · không có → bậc RAM
    st = load(); st["phones"].append(row); save(st)
    print(f"[3/4] Bật máy…", flush=True)
    _boot_take(a.name, True)
    s = memu_start(idx)
    if _start_failed(s): _boot_done(a.name)
    if not a.nowait: print(f"[4/4] Chờ Android khởi động (tối đa {BOOT_WAIT // 60} phút)…", flush=True)
    if s.returncode not in (0, None) and "SUCCESS" not in (s.stdout or "").upper():
        print("CẢNH BÁO bật máy:", (s.stdout or s.stderr or "").strip()[-200:])
    ok = True if a.nowait else wait_boot(a.name, port)
    print(f"✅ Đã tạo máy '{a.name}' (#{idx})  | cổng {port} | RAM {a.ram:g}GB CPU {a.cpu:g} | hết hạn {fmt(exp)}")
    print("   Android đã khởi động xong, sẵn sàng điều khiển." if ok else "   CẢNH BÁO: máy chưa kết nối được trình điều khiển, sẽ tự thử lại.")

def _need(name):
    st = load(); p = rec(name, st)
    if not p: print("Không có máy tên này."); sys.exit(1)
    if IDX(p) is None: print(f"LỖI: không thấy máy '{name}' trong MEmu (đã bị xoá tay?)."); sys.exit(4)
    st = load(); return st, rec(name, st)      # đọc lại 1 lần (IDX có thể vừa ghi cổng mới) — p PHẢI nằm trong st: sửa p rồi save(st) mới ghi được
                                               # (bản cũ trả load(), rec(name) = 2 lần đọc khác nhau → gia hạn / đổi độ phân giải không bao giờ được ghi)

def _kill_named(nm):
    """Tắt + xoá ĐÚNG máy tên nm trong giả lập: đọc lại số máy trước MỖI lệnh, không bao giờ đụng máy khác tên.
       True = chắc chắn đã mất · False = chưa xoá được / không đọc được danh sách máy (KHÔNG kết luận bừa là đã xoá)."""
    def at():
        v = vms_sure()
        if not v: return False, None, None
        k = next((k for k, x in v.items() if x["name"] == nm), None)
        return True, k, (v[k] if k is not None else None)
    for _t in range(3):
        seen, k, x = at()
        if not seen: time.sleep(3); continue
        if k is None: _vmdata_rm_if_gone(nm); return True
        if x["running"]:
            memuc("stop", "-i", k, timeout=120)
            for _w in range(20):
                seen, k, x = at()
                if seen and (k is None or not x["running"]): break
                time.sleep(3)
        seen, k, x = at()
        if not seen: time.sleep(3); continue
        if k is None: _vmdata_rm_if_gone(nm); return True
        r = memuc("remove", "-i", k, timeout=180)
        seen, k2, _x = at()
        if seen and k2 is None: _vmdata_rm_if_gone(nm); return True
        print(f"   (chưa xoá được {nm}, thử lại: {((r.stdout or '') + (r.stderr or '')).strip()[-120:]})", flush=True); time.sleep(5)
    return False

def _kill_locked(nm):
    """_kill_named trong khoá giả lập. Giả lập bận quá lâu (đang tạo máy khác) → False (chưa xoá, lần sau thử lại) — không văng lỗi."""
    try:
        with _Lock("memu", wait=300): return _kill_named(nm)
    except RuntimeError:
        print(f"   ({EMU_NAME} đang bận quá lâu — chưa xoá {nm}, thử lại sau)", flush=True); return False

def cmd_delete(a):
    """delete TÊN — xoá máy + toàn bộ dữ liệu. Chỉ bỏ khỏi danh sách khi giả lập CHẮC CHẮN không còn máy đó.
       Xoá chưa được → GIỮ trong danh sách, thoát mã 5 (cloudphoned giữ "đang huỷ" và thử lại, máy khách không bị hiểu là đã xoá).
       Máy cp_… không còn trong danh sách nhưng vẫn nằm trong giả lập (lần xoá trước lỗi) → xoá đúng máy tên đó."""
    st = load(); p = rec(a.name, st)
    v = vms_sure()
    if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME} — thử lại sau."); sys.exit(4)
    if not p:
        if str(a.name).startswith("cp_") and any(x["name"] == a.name for x in v.values()):
            gone = _kill_locked(a.name)
            if gone: _forget_files(a.name); print(f"🗑️  Đã xoá máy thừa '{a.name}' (không còn trong danh sách) và toàn bộ dữ liệu."); return
            print(f"⚠ Chưa xoá được '{a.name}' trong {EMU_NAME} — sẽ thử lại sau."); sys.exit(5)
        print("Không có máy tên này."); sys.exit(1)
    i = IDX(p, v)
    if i is None:                          # máy đã không còn trong giả lập → chỉ xoá khỏi danh sách
        st = load(); drop_phone(st, a.name); save(st)
        _vmdata_rm_if_gone(a.name); _forget_files(a.name)
        print(f"🗑️  '{a.name}' không còn trong {EMU_NAME} — đã bỏ khỏi danh sách."); return
    adb("disconnect", serial(p), timeout=15)
    gone = _kill_locked(a.name)
    if not gone:                                     # không xoá được → GIỮ trong danh sách (vẫn tính RAM, lần sau thử lại), KHÔNG thử số máy khác
        print(f"⚠ Chưa xoá được '{a.name}' trong {EMU_NAME} — máy vẫn giữ trong danh sách, sẽ thử lại sau."); sys.exit(5)
    st = load(); drop_phone(st, a.name); save(st)
    _forget_files(a.name)
    print(f"🗑️  Đã xoá máy '{a.name}' và toàn bộ dữ liệu.")

def _sb_get(path, timeout=25):
    """Đọc Supabase (khoá máy chủ trong cloudphone.conf) → list/dict. Lỗi → ném lỗi (KHÔNG coi là "không có")."""
    import urllib.request
    url = CONF["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + path; k = CONF["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url, headers={"apikey": k, "Authorization": "Bearer " + k, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8") or "[]")

def _web_rows(names):
    """{tên máy: dòng web} (ưu tiên dòng còn sống khi trùng tên). Đọc lỗi → None (KHÔNG kết luận gì, không xoá gì)."""
    import urllib.parse
    out = {}
    try:
        for i in range(0, len(names), 40):
            part = names[i:i + 40]
            for r in _sb_get("cloud_phones?select=id,container,status,node,ram,cpu,res,fps,android,expires_at&container=in.("
                             + ",".join(urllib.parse.quote(n) for n in part) + ")") or []:
                c = r.get("container")
                if c and (c not in out or out[c].get("status") in ("cancelled", "error")): out[c] = r
    except Exception:
        return None
    return out
ADOPT_ST = ("active", "expired")
def _adopt(v=None, quiet=False):
    """14/11: máy cp_… CÓ trong giả lập mà KHÔNG có trong danh sách (phones.json mất dòng) trong khi web ghi máy đó đang thuê ở
       máy chủ này → NHẬN LẠI vào danh sách (giữ nguyên máy + dữ liệu khách; đang tắt thì bảng / cloudphoned tự bật lại).
       Trả [tên đã nhận lại]."""
    v = v if v is not None else vms_sure()
    if not v: return []
    st = load(); mine = {p["name"] for p in st["phones"]}
    strays = {x["name"]: i for i, x in v.items() if str(x["name"]).startswith("cp_") and x["name"] not in mine}
    if not strays: return []
    web = _web_rows(sorted(strays))
    if web is None:
        if not quiet: print("   (không đọc được web — chưa nhận lại máy nào)", flush=True)
        return []
    me = CONF.get("NODE_ID", ""); got = []
    for nm, i in sorted(strays.items()):
        r = web.get(nm)
        if not r or r.get("status") not in ADOPT_ST or (r.get("node") or me) != me: continue
        res = r.get("res") or "720x1280"
        if not re.match(r"^\d+x\d+$", str(res)): res = "720x1280"
        row = {"name": nm, "idx": i, "port": port_of(i), "ram": float(r.get("ram") or 2), "cpu": float(r.get("cpu") or 2), "res": res,
               "fps": clamp_fps(r.get("fps") or 30), "dpi": auto_dpi(res), "android": norm_android(r.get("android") or DEF_ANDROID),
               "kind": EMU, "created": fmt(now()), "expires": r.get("expires_at") or (now() + datetime.timedelta(days=1)).isoformat(),
               "adopted": int(time.time())}
        st = load()
        if rec(nm, st): continue
        st["phones"].append(row); save(st); got.append(nm)
        print(f"NHAN_LAI {nm} (#{i}, cổng {row['port']}): giả lập còn máy, web đang thuê ở máy chủ này → đã nhận lại vào danh sách (giữ dữ liệu)", flush=True)
    return got
_DEF_VM = re.compile(r"^(Android Device|MuMu安卓设备|MuMu Android Device)(-\d+)?$", re.I)     # tên MuMu tự đặt cho máy mới
def _node_rows():
    """Máy web ghi đang thuê ở máy chủ này (có cổng). Đọc lỗi → None."""
    import urllib.parse
    me = CONF.get("NODE_ID", "")
    if not me: return None
    try:
        return _sb_get("cloud_phones?select=container,port,status,node,ram,cpu,res,fps,android,expires_at&node=eq."
                       + urllib.parse.quote(me) + "&status=in.(" + ",".join(ADOPT_ST) + ")") or []
    except Exception: return None
def _rename_back(v=None):
    """17/11e3 — MÁY BỊ MẤT TÊN trong giả lập (17/11 máy chủ 156: MuMu chạy lẫn quyền → lệnh đổi tên lúc tạo máy không được lưu,
       máy khách cp_147fd67c52 thành "Android Device-13" → tìm theo tên không thấy, khách mở mãi không được, lệnh A báo "máy lạ").
       Máy khách (danh sách, hoặc web ghi đang thuê ở máy chủ này) mà giả lập KHÔNG có máy đúng tên, trong khi ĐÚNG ô của máy đó (cổng
       adb = cổng của máy) là máy mang tên mặc định của MuMu, đang TẮT, không thuộc máy khách nào khác → đặt lại đúng tên (giữ dữ liệu)
       rồi ghi lại cấu hình (RAM / CPU / độ phân giải / FPS). Không xoá, không tạo máy nào. Trả [(tên, số máy)]."""
    if EMU != "mumu": return []
    v = v if v is not None else vms_sure()
    if not v: return []
    names = {x["name"] for x in v.values()}
    st = load(); want = {}
    for p in st["phones"]:
        nm = str(p.get("name", ""))
        if nm.startswith("cp_") and nm not in names and str(p.get("port", "")).isdigit(): want[nm] = dict(p)
    for r in _node_rows() or []:
        nm = str(r.get("container") or "")
        if nm.startswith("cp_") and nm not in names and nm not in want and str(r.get("port") or "").isdigit():
            want[nm] = {"name": nm, "port": int(r["port"]), "ram": r.get("ram"), "cpu": r.get("cpu"), "res": r.get("res"), "fps": r.get("fps")}
    if not want: return []
    held = {int(p["idx"]) for p in st["phones"] if str(p.get("idx", "")).isdigit() and p.get("name") in names}    # ô của máy khách đang có tên
    byport = {}
    for i in v:
        try: byport.setdefault(int(port_of(i)), i)
        except Exception: pass
    done = []
    for nm, p in sorted(want.items()):
        port = int(p["port"]); i = byport.get(port)
        if i is None or i == 0 or i in held: continue
        x = v.get(i) or {}
        if not _DEF_VM.match(str(x.get("name", ""))) or x.get("running"): continue
        if sum(1 for q in want.values() if int(q["port"]) == port) > 1:
            print(f"   ⚠ {nm}: ô #{i} đúng cổng {port} nhưng có 2 máy khách cùng cổng này — không đoán, báo Claude", flush=True); continue
        old = x.get("name")
        for _t in range(3):
            memuc("rename", "-i", i, nm, timeout=60)
            if (vms().get(i) or {}).get("name") == nm: break
            time.sleep(3)
        else:
            print(f"   ⚠ {nm}: ô #{i} ('{old}') đúng cổng {port} nhưng chưa đặt lại tên được — chạy lại lệnh A sau ít phút", flush=True); continue
        try:
            res = str(p.get("res") or "720x1280"); res = res if re.match(r"^\d+x\d+$", res) else "720x1280"
            configure(i, float(p.get("ram") or 2), float(p.get("cpu") or 2), res, p.get("dpi") or auto_dpi(res))
            memuc("setconfigex", "-i", i, "fps", clamp_fps(p.get("fps") or 30), timeout=60)
        except Exception as e: print(f"   (ghi lại cấu hình {nm} lỗi: {repr(e)[:120]})", flush=True)
        st2 = load(); q = rec(nm, st2)
        if q and (q.get("idx") != i or q.get("port") != port): q["idx"], q["port"] = i, port; save(st2)
        done.append((nm, i))
        print(f"NHAN_LAI {nm} (#{i}, cổng {port}): máy bị MẤT TÊN trong giả lập ('{old}') → đã đặt lại tên + ghi lại cấu hình (giữ dữ liệu)", flush=True)
    return done
def cmd_nhanlai(a):
    rb = []
    try: rb = _rename_back()
    except Exception as e: print(f"   (đặt lại tên máy lỗi: {repr(e)[:160]})", flush=True)
    got = _adopt()
    print(f"NHANLAI {json.dumps({'adopted': got, 'renamed': [n for n, _ in rb]}, ensure_ascii=False)}")

LIVE_WEB = ("pending", "creating", "active", "expired", "cancelling")      # web: máy còn "sống" (đang tạo / đang thuê / chờ gia hạn / đang huỷ)
LOST_MIN_AGE = 600                                                          # khách huỷ chưa quá ngần này giây → chưa dọn máy mất tên (chờ mọi việc lắng)
def _vm_dir(i):
    """Thư mục máy ảo MuMu số i (…\\vms\\<tên>-<i>) — đúng 1 thư mục khớp mới trả, không thì None."""
    if EMU != "mumu" or not MUMU: return None
    root = os.path.join(MUMU, "vms")
    try: hit = [d for d in os.listdir(root) if re.search(r"-%d$" % int(i), d) and os.path.isdir(os.path.join(root, d))]
    except OSError: return None
    return os.path.join(root, hit[0]) if len(hit) == 1 else None
def _vm_born(i):
    """Lúc thư mục máy ảo số i được tạo (= lúc máy ảo được tạo / nhân bản) → datetime, không biết → None."""
    d = _vm_dir(i)
    try: return datetime.datetime.fromtimestamp(os.path.getctime(d)).astimezone() if d else None
    except OSError: return None
def _lost_scan(v, st):
    """17/11f — máy MẤT TÊN còn sót: máy MuMu mang tên mặc định ("Android Device-N"), không phải máy gốc #0. Hỏi web theo CỔNG của ô đó
       (cổng adb = 16384 + 32 × số máy; máy khách nào từng nằm ở ô đó đều có dòng trên web):
         · còn dòng đang thuê / đang tạo / đang huỷ, hoặc máy chủ còn ghi máy khách ở cổng đó → máy mất tên của khách ĐANG THUÊ: giữ (chạy
           `phonectl nhanlai` để đặt lại tên) — KHÔNG BAO GIỜ xoá;
         · mọi dòng đều "đã huỷ", lần huỷ gần nhất quá 10 phút, máy đang TẮT và thư mục máy ảo được tạo TRƯỚC lúc khách huỷ (đúng là máy
           của khách đó, không phải máy admin mới tạo tay ở cùng ô) → máy sót của khách đã huỷ: dondep --xoa xoá được;
         · không có dòng nào / không kiểm được ngày tạo → không rõ: chỉ báo, không tự xoá.
       Trả ([(số máy, tên, cổng, tên máy khách đã huỷ)], số máy của khách đang thuê, số máy không rõ). Đọc web lỗi → ném lỗi (nơi gọi không xoá gì)."""
    import urllib.parse
    if EMU != "mumu": return [], 0, 0
    cand = [(i, x) for i, x in sorted(v.items()) if i != 0 and _DEF_VM.match(str(x["name"]))]
    if not cand: return [], 0, 0
    me = CONF.get("NODE_ID", "")
    if not me: return [], 0, len(cand)
    ports = {}
    for i, x in cand:
        try: ports[int(port_of(i))] = i
        except Exception: pass
    try:
        rows = _sb_get("cloud_phones?select=container,port,status,node,updated_at&node=eq." + urllib.parse.quote(me)
                       + "&port=in.(" + ",".join(str(p_) for p_ in sorted(ports)) + ")") or []
    except Exception as e:
        print(f"   (không đọc được web để kiểm máy mất tên: {str(e)[:120]} — không xoá máy mất tên nào)", flush=True); return [], 0, len(cand)
    by = {}
    for r in rows:
        try: by.setdefault(int(r.get("port")), []).append(r)
        except (TypeError, ValueError): pass
    mine = {}
    for p in st["phones"]:
        try: mine[int(p.get("port"))] = p["name"]
        except (TypeError, ValueError, KeyError): pass
    idxs = {str(p.get("idx")) for p in st["phones"]}
    lost = []; keep = unk = 0
    for i, x in cand:
        nm = str(x["name"])
        try: port = int(port_of(i))
        except Exception: unk += 1; continue
        rr = by.get(port, [])
        live = [r for r in rr if r.get("status") != "cancelled"]          # chỉ "đã huỷ" mới tính là hết dùng (LIVE_WEB + mọi trạng thái lạ đều giữ)
        if live or port in mine or str(i) in idxs:
            keep += 1
            print(f"· {nm:<18} #{i} cổng {port} · máy MẤT TÊN của khách đang thuê ({(live[0].get('container') if live else mine.get(port)) or '?'})"
                  " — giữ nguyên; đặt lại tên:  python phonectl.py nhanlai", flush=True); continue
        if not rr:
            unk += 1; print(f"· {nm:<18} #{i} cổng {port} · {'đang chạy' if x['running'] else 'tắt'} · KHÔNG CÓ TRÊN WEB (máy tạo tay / tạo dở) — không tự xoá", flush=True); continue
        last = None
        for r in rr:
            try:
                t_ = parse_dt(r.get("updated_at"))
                if last is None or t_ > last[0]: last = (t_, r)
            except Exception: pass
        born = _vm_born(i)
        why = ""
        if x["running"]: why = "đang chạy"
        elif last is None or born is None: why = "không kiểm được ngày tạo máy ảo / ngày huỷ"
        elif (now() - last[0]).total_seconds() < LOST_MIN_AGE: why = "khách vừa huỷ chưa quá 10 phút"
        elif born >= last[0] - datetime.timedelta(seconds=60): why = "máy ảo được tạo SAU lúc khách ở ô này huỷ (máy khác, không phải máy của khách đó)"
        if why:
            unk += 1; print(f"· {nm:<18} #{i} cổng {port} · web: đã huỷ ({last[1].get('container') if last else '?'}) nhưng {why} — không tự xoá", flush=True); continue
        lost.append((i, nm, port, str(last[1].get("container") or "?")))
        print(f"✗ {nm:<18} #{i} cổng {port} · tắt · máy MẤT TÊN của khách ĐÃ HUỶ ({last[1].get('container')}, huỷ {fmt(last[0])}) — còn sót, chiếm ổ đĩa", flush=True)
    return lost, keep, unk
def _kill_lost(i, nm):
    """Xoá ĐÚNG máy số i đang mang tên mặc định nm (máy mất tên của khách đã huỷ). Kiểm lại TRONG khoá giả lập ngay trước khi xoá: vẫn đúng
       số, đúng tên (chỉ 1 máy mang tên đó), đang tắt, không phải máy gốc, máy chủ không ghi máy khách nào ở ô / cổng đó, giả lập không đang
       nhân bản. Sai 1 điều → không xoá. True = chắc chắn đã mất."""
    try:
        with _Lock("memu", wait=120):
            if _long_busy(): return False
            v = vms_sure(); x = (v or {}).get(i)
            if not v or not x or i == 0 or x["name"] != nm or x["running"] or not _DEF_VM.match(str(nm)): return False
            if sum(1 for y in v.values() if y["name"] == nm) != 1: return False
            try: port = int(port_of(i))
            except Exception: return False
            for p in load()["phones"]:
                if str(p.get("idx")) == str(i) or str(p.get("port")) == str(port): return False
            memuc("remove", "-i", i, timeout=180)
            v2 = vms_sure()
            return bool(v2) and i not in v2
    except RuntimeError: return False
def cmd_dondep(a):
    """dondep [--xoa] — máy khách CÒN SÓT trên máy chủ dù web đã HUỶ (status cancelled): máy cũ đổi Android, đơn huỷ lúc máy chủ
       tắt, lần xoá trước lỗi… → web vẫn thấy "8 máy · đã cấp 48GB" dù không ai thuê. Gồm cả máy cp_… KHÔNG còn trong danh sách
       nhưng vẫn nằm trong giả lập. Không --xoa: chỉ liệt kê. --xoa: xoá hẳn đúng các máy web ghi cancelled (máy ảo + dữ liệu).
       Máy KHÔNG có trên web hoặc web ghi đang dùng: chỉ báo, không bao giờ tự xoá. Dòng cuối: DONDEP {json} (web đọc)."""
    import urllib.parse
    st = load(); listed = [p["name"] for p in st["phones"] if str(p.get("name", "")).startswith("cp_")]
    me = CONF.get("NODE_ID", "") or "máy chủ này"
    v = vms_sure()
    if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME} — KHÔNG xoá gì."); sys.exit(4)
    strays = sorted({x["name"] for x in v.values() if str(x["name"]).startswith("cp_")} - set(listed))
    names = listed + strays
    if not names and not (EMU == "mumu" and any(_DEF_VM.match(str(x["name"])) and i != 0 for i, x in v.items())):
        print(f"{me}: không có máy khách nào — không có gì để dọn.")
        print("DONDEP " + json.dumps({"node": me, "total": 0, "dead": 0, "deleted": 0, "fail": 0, "unknown": 0})); return
    db = {}
    try:
        for i in range(0, len(names), 40):
            part = names[i:i + 40]
            for r in _sb_get("cloud_phones?select=container,status,node&container=in.(" + ",".join(urllib.parse.quote(n) for n in part) + ")") or []:
                if r.get("status") != "cancelled" or r.get("container") not in db: db[r.get("container")] = r    # trùng tên: ưu tiên dòng còn sống
    except Exception as e:
        print(f"LỖI: không đọc được web (Supabase): {e} — KHÔNG xoá gì."); sys.exit(4)
    gone = []; unknown = 0
    for n in names:
        r = db.get(n); p = rec(n, st); stray = n in strays
        i = next((k for k, x in v.items() if x["name"] == n), None); run_ = i is not None and bool(v[i]["running"])
        stt = (r or {}).get("status") or "KHÔNG CÓ TRÊN WEB"; nd = (r or {}).get("node") or ""
        dead = bool(r) and stt == "cancelled"
        if dead: gone.append(n)
        elif not r: unknown += 1
        cfg = f"RAM {p.get('ram')}GB · {p.get('cpu')} nhân" if p else "máy THỪA (không còn trong danh sách)"
        print(f"{'✗' if dead else '·'} {n:<16} {cfg} · {'đang chạy' if run_ else 'tắt'}"
              f" · web: {stt}{(' (máy chủ ' + nd + ')') if nd and nd != CONF.get('NODE_ID', '') else ''}", flush=True)
    keep = len(names) - len(gone)
    print(f"\n{me}: {len(names)} máy khách ({len(strays)} máy thừa) · {len(gone)} máy web đã HUỶ nhưng còn sót trên máy chủ · {keep} máy giữ nguyên")
    lost, lost_keep, lost_unk = _lost_scan(v, st)                # 17/11f: máy MẤT TÊN ("Android Device-N") của khách đã huỷ → cũng dọn
    ok = 0
    if gone and not a.xoa:
        print("→ Xoá hẳn các máy ✗ (máy ảo + dữ liệu, KHÔNG khôi phục được):  python phonectl.py dondep --xoa")
    elif gone:
        for n in gone:
            a.name = n
            try: cmd_delete(a); ok += 1
            except SystemExit: print(f"⚠ {n}: chưa xoá được — chạy lại sau", flush=True)
        print(f"Xong: đã xoá {ok}/{len(gone)} máy đã huỷ. Web cập nhật số máy / RAM đã cấp sau ~30 giây.")
    ok2 = 0
    if lost and not a.xoa:
        print(f"→ Xoá hẳn {len(lost)} máy mất tên của khách đã huỷ (✗ ở trên):  python phonectl.py dondep --xoa")
    elif lost:
        for i, nm, port, who in lost:
            if _kill_lost(i, nm): ok2 += 1; print(f"🗑️  Đã xoá máy mất tên '{nm}' (#{i}, cổng {port}) của khách đã huỷ {who} và toàn bộ dữ liệu.", flush=True)
            else: print(f"⚠ {nm} (#{i}): chưa xoá được (giả lập đang bận / máy vừa đổi) — lần sau thử lại", flush=True)
    print("DONDEP " + json.dumps({"node": me, "total": len(names), "dead": len(gone) + len(lost), "deleted": ok + ok2,
                                  "fail": (len(gone) - ok + len(lost) - ok2) if a.xoa else 0, "unknown": unknown + lost_unk, "lost": len(lost), "lost_live": lost_keep}))

def cmd_forget(a):
    """forget TÊN: bỏ máy khỏi danh sách CHỈ KHI giả lập chắc chắn không còn máy đó (máy "ma") — không bao giờ xoá máy thật."""
    st = load(); p = rec(a.name, st)
    if not p: print("Không có máy tên này trong danh sách."); return
    v = vms_sure()
    if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME} — thử lại sau."); sys.exit(4)
    if any(x["name"] == a.name for x in v.values()): print(f"LỖI: '{a.name}' vẫn còn trong {EMU_NAME} — không bỏ khỏi danh sách."); sys.exit(3)
    drop_phone(st, a.name); save(st); _vmdata_rm(a.name)
    print(f"Đã bỏ '{a.name}' khỏi danh sách ({EMU_NAME} không còn máy này).")

def set_hold(name, on, sleep=False):
    """hold = máy CỐ Ý tắt (admin khoá / hết hạn) → bộ tự bật lại không đụng vào. Tắt ngoài ý muốn (bấm Close trong MEmu, MEmu văng) → tự bật lại.
       sleep = máy NGỦ (tự tắt vì lâu không dùng, khách mở là bật lại) — cũng là hold. Bật lại (on=False) hoặc tạm dừng thật → hết ngủ."""
    st = load(); p = rec(name, st)
    if not p: return
    ch = bool(p.get("hold")) != on
    p["hold"] = on
    if on and sleep: ch = ch or not p.get("sleep"); p["sleep"] = p.get("sleep") or int(time.time())
    elif p.pop("sleep", None) is not None: ch = True
    if ch: save(st)
def cmd_stop(a):
    st, p = _need(a.name); adb("disconnect", serial(p), timeout=15)
    memuc("stop", "-i", IDX(p), timeout=120); set_hold(a.name, True); print(f"⏸  Đã tạm dừng '{a.name}'.")

def _start_failed(r): return "fail" in ((r.stdout or "") + (r.stderr or "")).lower() or r.returncode not in (0, None)
def memu_unstick():
    """MEmu bị kẹt (mọi máy 'start vm failed') → tắt hẳn tiến trình MEmu chạy ngầm. Chỉ làm khi KHÔNG có máy nào đang chạy."""
    if EMU == "mumu": return False
    r = memuc("listvms", "--running", timeout=30) if EMU in ("ld", "mumu") else run([os.path.join(MEMU, "memuc.exe"), "listvms", "--running"], 30)
    if r.returncode not in (0, None) or any(ln.strip() and ln[0].isdigit() for ln in (r.stdout or "").splitlines()):
        return False
    for im in (("dnplayer.exe", "Ld9BoxHeadless.exe", "LdBoxHeadless.exe", "Ld9BoxSVC.exe", "LdBoxSVC.exe", "ldconsole.exe") if EMU == "ld" else
               ("MEmuConsole.exe", "MEmuHeadless.exe", "MEmu.exe", "MemuService.exe", "MEmuSVC.exe")):
        run(["taskkill", "/F", "/T", "/IM", im], 30)
    time.sleep(5); print("   (MEmu bị kẹt → đã tự khởi động lại phần chạy ngầm của MEmu)", flush=True); return True
START_GAP = float(CONF.get("MEMU_START_GAP", "15") or 15)      # MEmu: bật xong 1 máy chờ thêm N giây rồi mới bật máy kế
def _close_memu_errors():
    """Đóng hộp thoại "MEmu start error" (VD "The computer memory is low…"). Để mở thì lệnh bật máy treo tới 2,5 phút
       → phần nhận đơn đứng → web thấy máy chủ mất kết nối. Trả về số hộp thoại đã đóng."""
    if os.name != "nt": return 0
    try:
        u = ctypes.windll.user32; hits = []
        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(h, _):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1); t = b.value.lower()
                if "memu start error" in t or "memory is low" in t: hits.append(h)
            return True
        u.EnumWindows(PROC(cb), 0)
        for h in hits: u.PostMessageW(ctypes.c_void_p(h), 0x0010, 0, 0)        # WM_CLOSE = bấm OK / X
        return len(hits)
    except Exception: return 0
FAIL_F = os.path.join(HOME, "redroid", "startfail.json")
def _fails():
    try: return json.load(open(FAIL_F, encoding="utf-8"))
    except Exception: return {}
def _fails_put(d):
    try: json.dump(d, open(FAIL_F, "w", encoding="utf-8"))
    except Exception: pass
def _memu_front_pids(name):
    """PID cửa sổ MEmu (MEmu.exe) đang mở cho máy tên name — cửa sổ đó giữ hộp thoại lỗi khi máy không bật được."""
    if os.name != "nt" or not name: return set()
    try:
        u = ctypes.windll.user32; k = ctypes.windll.kernel32; pids = set()
        PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(h, _):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1); t = b.value
                if t == name or t.endswith(f"({name})") or t.endswith(f" {name}"):
                    pid = ctypes.c_ulong(); u.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(pid)); pids.add(pid.value)
            return True
        u.EnumWindows(PROC(cb), 0)
        out = set()
        for pid in pids:                                      # chỉ nhận đúng tiến trình MEmu.exe (không đụng chương trình khác trùng tên cửa sổ)
            hp = k.OpenProcess(0x1000, False, pid)
            if not hp: continue
            buf = ctypes.create_unicode_buffer(520); sz = ctypes.c_ulong(520)
            if k.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(sz)) and buf.value.lower().endswith("\\memu.exe"): out.add(pid)
            k.CloseHandle(hp)
        return out
    except Exception: return set()
def _vm_up(idx):
    """Máy ảo MEmu đã CHẠY (tiến trình máy ảo đã lên — Android có thể vẫn đang khởi động, màn đen vài chục giây là bình thường)."""
    r = memuc("isvmrunning", "-i", idx, timeout=30)
    o = ((r.stdout or "") + (r.stderr or "")).strip().lower()
    if "not running" in o: return False
    if "running" in o: return True
    x = vms().get(int(idx)); return bool(x and x["running"])          # bản MEmu không có lệnh isvmrunning
def _try_start(idx, name):
    """1 lần bật máy MEmu: (đã chạy?, kết quả lệnh, lý do lỗi).
       Chỉ coi là LỖI khi MEmu hiện hộp thoại lỗi (VD "memory is low") hoặc sau 90 giây máy ảo vẫn KHÔNG chạy.
       Máy đang khởi động (màn đen) KHÔNG bao giờ bị tắt."""
    import threading
    hit, stop = [], []
    def watch():                                                      # suốt lúc bật + chờ: hộp thoại lỗi hiện ra là đóng ngay
        while not stop:
            if _close_memu_errors(): hit.append(1)
            time.sleep(2)
    th = threading.Thread(target=watch, daemon=True); th.start()
    up = False; r = None
    try:
        r = memuc("start", "-i", idx, timeout=150)
        if not _start_failed(r):
            t0 = time.time()
            while time.time() - t0 < 90 and not hit:
                if _vm_up(idx): up = True; break
                time.sleep(3)
            if up:
                time.sleep(START_GAP)                                 # MEmu có thể báo lỗi vài giây sau → chờ rồi mới cho máy khác bật
                up = not hit
    finally: stop.append(1); th.join(5)
    if up: return True, r, ""
    why = "MEmu báo thiếu RAM (memory is low)" if hit else ("lệnh bật lỗi" if _start_failed(r) else "máy ảo không chạy sau 90 giây")
    if hit or not _vm_up(idx):                                        # chỉ dọn khi máy THẬT SỰ không chạy / có hộp thoại lỗi
        for pid in _memu_front_pids(name):                            # cửa sổ MEmu của máy này (đang giữ hộp thoại lỗi) → đóng
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)
        memuc("stop", "-i", idx, timeout=60)
    else:
        return True, r, ""                                            # máy vẫn chạy (khởi động chậm) → coi là bật được
    return False, subprocess.CompletedProcess(getattr(r, "args", []), 1, (getattr(r, "stdout", "") or "") + f" | {why}", getattr(r, "stderr", "") or ""), why
def memu_start(idx):
    """Bật 1 máy. MEmu: MỖI LẦN CHỈ BẬT 1 MÁY (khoá "vmstart", mọi chương trình dùng chung) — 2 máy bật cùng lúc MEmu hay báo
       "The computer memory is low" dù RAM còn nhiều. Máy không lên → đóng cửa sổ MEmu của máy đó + tắt hẳn → thử lại 1 lần;
       vẫn lỗi → tạm không bật máy đó 10 phút (không giữ lượt bật của máy khác)."""
    if EMU != "memu":
        r = memuc("start", "-i", idx, timeout=150)
        if _start_failed(r):
            time.sleep(8); r = memuc("start", "-i", idx, timeout=150)
        if _start_failed(r) and memu_unstick():
            r = memuc("start", "-i", idx, timeout=150)
        return r
    lk = _Lock("vmstart", wait=900)
    try: lk.__enter__(); got = True
    except RuntimeError: got = False                          # chờ quá 15 phút → vẫn bật (không để khách chờ mãi)
    try:
        x = vms().get(int(idx))
        if x and x["running"]: return _ok("SUCCESS: vm is already running")
        name = (x or {}).get("name") or ""
        fl = _fails(); f = fl.get(name) or {}
        if name and f.get("n", 0) >= 2 and time.time() - f.get("t", 0) < 600:
            return subprocess.CompletedProcess([], 1, "", f"{name}: MEmu bật lỗi {f['n']} lần liền — tạm không thử, {int((600 - time.time() + f['t']) // 60) + 1} phút nữa thử lại")
        r = None
        for k in range(2):
            up, r, why = _try_start(idx, name)
            if up:
                if name in fl: fl.pop(name, None); _fails_put(fl)
                return r
            print(f"   (MEmu chưa bật được {name or '#' + str(idx)}: {why} → " + ("thử lại sau 20 giây)" if k == 0 else "tạm dừng máy này 10 phút)"), flush=True)
            if k == 0: time.sleep(20)
        if memu_unstick():                                    # không máy nào chạy mà vẫn lỗi → MEmu chạy ngầm bị kẹt → khởi động lại MEmu, thử lần cuối
            up, r, why = _try_start(idx, name)
            if up:
                if name in fl: fl.pop(name, None); _fails_put(fl)
                return r
        if name:
            f = fl.get(name) or {"n": 0}; f["n"] = f.get("n", 0) + 1; f["t"] = time.time(); fl[name] = f; _fails_put(fl)
        return r
    finally:
        if got: lk.__exit__()
# ---------- GIÃN CÁCH BẬT MÁY (14/11) ----------
# Máy chủ "sập" khi nhiều máy khách KHỞI ĐỘNG cùng lúc (đơn mới dồn, khách mở nhiều máy ngủ, giả lập văng rồi bật lại hết): lúc khởi
# động là lúc 1 máy ngốn CPU + ổ cứng nhiều nhất. Giờ mọi lệnh bật máy (tạo, bật lại, đánh thức, khởi động lại…) xin "suất khởi
# động": tối đa BOOT_PARALLEL máy cùng khởi động, 2 lần bật cách nhau ≥ BOOT_GAP_S giây, CPU thật ≥ BOOT_CPU_PCT% thì chờ dịu bớt.
# Việc khách đang chờ (tạo máy, mở máy ngủ, khởi động lại) được thêm 1 suất + nửa khoảng cách. Android lên → trả suất ngay; lệnh
# không chờ Android lên thì suất tự hết sau BOOT_HOLD_S giây. Chờ quá 15 phút → vẫn bật (không để khách chờ mãi).
def _cfn(k, d):
    try: return float(CONF.get(k, d) or d)
    except (TypeError, ValueError): return float(d)
BOOT_PAR = max(1, int(_cfn("BOOT_PARALLEL", 2)))
BOOT_GAP = max(0.0, _cfn("BOOT_GAP_S", 20))
BOOT_HOLD = max(30.0, _cfn("BOOT_HOLD_S", 150))
BOOT_CPU = max(50.0, min(101.0, _cfn("BOOT_CPU_PCT", 90)))
BOOT_MAXWAIT = 900
BOOT_F = os.path.join(HOME, "redroid", "bootslots.json")
PRIO = False                                   # lệnh hiện tại là việc khách đang chờ (main() đặt)
# 17/11f — ĐỢT BẬT HÀNG LOẠT (máy chủ vừa khởi động lại): trước đây bootall bật TỪNG MÁY MỘT, mỗi máy chờ Android tới 5 phút mới sang
# máy sau → máy chủ 30 máy mất cả giờ, 1 máy treo là cả hàng đứng; khách mở máy thì lệnh bật của khách đụng lệnh đang xếp hàng → quay mãi.
# Giờ: bootall chia việc cho nhiều lệnh con (boot1) chạy cùng lúc theo SUẤT (BOOTALL_PARALLEL), máy có khách vừa dùng lên trước, khách mở
# máy nào thì máy đó được CHEN lên (dấu redroid/prio_<tên>.flag), máy ảo treo lúc bật được tắt hẳn + bật lại 1 lần (BOOT_RESCUE_S).
def _bootall_par():
    """Số máy bật CÙNG LÚC trong đợt bật hàng loạt: BOOTALL_PARALLEL (cloudphone.conf); không ghi → BOOT_PARALLEL nếu admin đã tự ghi
       (máy chủ yếu), không thì theo số luồng CPU: ≥ 48 luồng 4 máy · ≥ 24 luồng 3 máy · còn lại theo BOOT_PARALLEL."""
    v = int(_cfn("BOOTALL_PARALLEL", 0))
    if v > 0: return min(v, 8)
    if str(CONF.get("BOOT_PARALLEL", "") or "").strip(): return BOOT_PAR
    n = os.cpu_count() or 8
    return max(BOOT_PAR, 4 if n >= 48 else 3 if n >= 24 else 2)
BOOT_RESCUE_S = max(0.0, _cfn("BOOT_RESCUE_S", 150))     # máy vừa bật mà ngần này giây adb chưa nối được lần nào → tắt hẳn + bật lại 1 lần · 0 = tắt
BOOT_NOWAIT_S = 75                                       # lệnh bật KHÔNG chờ Android (start): suất tự hết sau ngần này giây
_NAME_OK = re.compile(r"[A-Za-z0-9_.-]{1,80}")
def _prio_f(key): return os.path.join(HOME, "redroid", f"prio_{key}.flag")
def _prio_ask(key):
    """Khách vừa mở máy `key` mà lệnh khác (đợt bật hàng loạt) đang giữ máy đó trong hàng chờ → đánh dấu cho máy đó lên trước."""
    if not _NAME_OK.fullmatch(str(key)): return
    try:
        os.makedirs(os.path.join(HOME, "redroid"), exist_ok=True)
        with open(_prio_f(key), "w") as f: f.write(str(int(time.time())))
    except OSError: pass
def _prio_on(key):
    try: return 0 <= time.time() - os.path.getmtime(_prio_f(key)) < 900
    except (OSError, ValueError): return False
def _prio_clear(key):
    try: os.remove(_prio_f(key))
    except (OSError, ValueError): pass
def _bs_load():
    try:
        d = json.load(open(BOOT_F, encoding="utf-8"))
        return {"slots": {str(k): float(v) for k, v in (d.get("slots") or {}).items()}, "last": float(d.get("last") or 0)}
    except Exception: return {"slots": {}, "last": 0.0}
def _bs_save(d):
    try:
        os.makedirs(os.path.dirname(BOOT_F), exist_ok=True); tmp = BOOT_F + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f)
        os.replace(tmp, BOOT_F)
    except Exception: pass
def _cpu_pct(dt=1.0):
    """% CPU thật của cả máy chủ (đo dt giây). Không đo được → 0 (không chặn)."""
    if os.name != "nt": return 0.0
    try:
        class FT(ctypes.Structure): _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]
        def get():
            i, k, u = FT(), FT(), FT(); ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
            return [(x.hi << 32) | x.lo for x in (i, k, u)]
        a = get(); time.sleep(dt); b = get()
        tot = (b[1] - a[1]) + (b[2] - a[2])                      # thời gian nhân (kernel) đã gồm thời gian rảnh
        return max(0.0, min(100.0, 100.0 * (1 - (b[0] - a[0]) / tot))) if tot > 0 else 0.0
    except Exception: return 0.0
def _boot_take(key, prio=None, maxwait=None, par=None):
    """Chờ tới lượt được bật 1 máy (xem trên). Trả số giây đã chờ. maxwait (16/11e): chờ quá chừng đó giây → None (KHÔNG giữ lượt).
       17/11f: par = số suất riêng của đợt bật hàng loạt · đang chờ mà khách mở đúng máy này (_prio_ask) → thành việc ưu tiên ngay."""
    prio0 = PRIO if prio is None else prio
    t0 = time.time(); said = t0 - 55                       # chờ quá 5 giây mới báo, sau đó 1 phút / lần
    while True:
        if maxwait is not None and time.time() - t0 > maxwait: return None
        prio = prio0 or _prio_on(key)
        cap = (par or BOOT_PAR) + (1 if prio else 0); gap = BOOT_GAP / 2 if prio else BOOT_GAP
        late = time.time() - t0 > BOOT_MAXWAIT
        hot = 0.0 if late or prio else _cpu_pct()           # khách đang chờ → không chờ CPU dịu (chỉ giới hạn số máy + giãn cách)
        if par and not prio and hot < 60: gap = BOOT_GAP / 2        # đợt bật hàng loạt lúc máy chủ còn rảnh → giãn cách một nửa
        why = ""
        try:
            with _Lock("bootslot", wait=60):
                d = _bs_load(); now = time.time()
                d["slots"] = {k: t for k, t in d["slots"].items() if now - t < BOOT_HOLD and k != key}
                if late or (len(d["slots"]) < cap and now - d["last"] >= gap and (prio or hot < BOOT_CPU)):
                    d["slots"][key] = now; d["last"] = now; _bs_save(d); return now - t0
                why = (f"{len(d['slots'])} máy đang khởi động" if len(d["slots"]) >= cap else
                       f"CPU đang {hot:.0f}%" if hot >= BOOT_CPU else f"giãn cách {gap:.0f} giây giữa 2 lần bật")
        except RuntimeError:
            if late: return time.time() - t0
        if time.time() - said > 60:
            print(f"   (chờ lượt bật {key}: {why or 'đang bận'} — giãn cách để máy chủ không quá tải)", flush=True); said = time.time()
        time.sleep(2)
_PRE = set()                                   # 16/11e: máy đã xin lượt bật TRƯỚC khi tắt (start_phone dùng luôn lượt đó)
PRE_CLONE_S = 600                              # 16/11e: MuMu đang nhân bản máy mẫu → máy khách (vẫn chạy) chờ tối đa chừng này giây rồi mới tắt
def _boot_touch(key):
    """Đã có lượt (xin trước khi tắt) → tính lại giờ giữ lượt từ lúc bật thật."""
    try:
        with _Lock("bootslot", wait=60):
            d = _bs_load(); now = time.time(); d["slots"][str(key)] = now; d["last"] = max(d["last"], now); _bs_save(d)
    except Exception: pass
def _pre_release():
    for k in list(_PRE): _PRE.discard(k); _boot_done(k)
def _pre_slot(p, prio=None, maxwait=None):
    """16/11e: máy ĐANG CHẠY sắp bị tắt để bật lại → xin lượt bật NGAY BÂY GIỜ (máy vẫn chạy, khách vẫn dùng trong lúc chờ),
       có lượt rồi mới tắt → bật liền sau khi tắt. Trước: tắt trước rồi mới xếp hàng → máy nằm TẮT cả lúc chờ (máy chủ bận: nhiều phút).
       MuMu đang nhân bản máy mẫu → chờ xong rồi mới xin lượt (tắt lúc đó thì lệnh bật phải chờ nhân bản xong).
       False = chờ quá maxwait giây mà chưa có lượt (KHÔNG tắt máy)."""
    nm = p["name"]
    try: on = is_running(nm, p)
    except Exception: on = False
    if not on: return True                                 # máy đang tắt sẵn → start_phone xin lượt như cũ
    t0 = time.time()
    if EMU == "mumu":
        while _long_busy() and time.time() - t0 < min(PRE_CLONE_S, maxwait if maxwait is not None else PRE_CLONE_S): time.sleep(2)
    w = _boot_take(nm, prio, None if maxwait is None else max(1.0, maxwait - (time.time() - t0)))
    if w is None: return False
    if not _PRE: atexit.register(_pre_release)
    _PRE.add(nm); return True
def _boot_done(key):
    """Máy đã lên (hoặc bật lỗi) → trả suất khởi động cho máy khác."""
    _prio_clear(key)
    try:
        with _Lock("bootslot", wait=60):
            d = _bs_load()
            if d["slots"].pop(str(key), None) is not None: _bs_save(d)
    except Exception: pass
def _boot_short(key):
    """17/11f: lệnh bật KHÔNG chờ Android lên (start — cloudphoned tự bật lại máy tắt ngoài ý muốn) không bao giờ trả suất sớm → mỗi máy
       giữ suất đủ BOOT_HOLD_S (150 giây), đợt bật sau khi máy chủ khởi động lại chậm hẳn. Giờ: suất của lệnh đó tự hết sau BOOT_NOWAIT_S giây."""
    try:
        with _Lock("bootslot", wait=60):
            d = _bs_load(); k = str(key)
            if k in d["slots"]:
                d["slots"][k] = min(d["slots"][k], time.time() - max(0.0, BOOT_HOLD - BOOT_NOWAIT_S)); _bs_save(d)
    except Exception: pass
def start_phone(p, guard=None, par=None):
    """guard (16/11b, chỉ wake dùng): hàm kiểm "có nên thôi không bật nữa" gọi SAU khi chờ tới lượt — trả True thì trả suất, trả None.
       par (17/11f): số suất của đợt bật hàng loạt (boot1)."""
    took = False
    try: on = is_running(p["name"], p)
    except Exception: on = False
    if not on:
        if p["name"] in _PRE: _PRE.discard(p["name"]); _boot_touch(p["name"])     # 16/11e: đã xin lượt trước khi tắt
        else: _boot_take(p["name"], par=par)
        took = True                                       # máy đang chạy sẵn → không giành suất của máy khác
    if guard is not None and not on and guard():
        if took: _boot_done(p["name"])
        return None
    r = memu_start(IDX(p)); adb_connect(p["port"])
    if not _start_failed(r): set_hold(p["name"], False)
    elif took: _boot_done(p["name"])
    return r
def cmd_start(a):
    st, p = _need(a.name); r = start_phone(p)
    if _start_failed(r): print("❌ MEmu không bật được máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); sys.exit(5)
    _boot_short(a.name)                                   # 17/11f: lệnh này không chờ Android → suất tự hết sớm (không giữ đủ 150 giây)
    print("✅ Đã bật")
def _proc_image(pid):
    """Tên file chạy của tiến trình (VD MuMuVMMHeadless.exe); '' nếu tiến trình không còn / không đọc được."""
    if os.name != "nt": return ""
    try:
        k = ctypes.windll.kernel32; hp = k.OpenProcess(0x1000, False, int(pid))       # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp: return ""
        try:
            buf = ctypes.create_unicode_buffer(520); sz = ctypes.c_ulong(520)
            return os.path.basename(buf.value) if k.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(sz)) else ""
        finally: k.CloseHandle(hp)
    except Exception: return ""
_VM_IMAGES = {"mumu": ("mumu",), "ld": ("dnplayer", "ldbox", "ld9box"), "memu": ("memu",)}   # chỉ tắt tiến trình CỦA giả lập (số PID có thể bị chương trình khác dùng lại)
def _vm_pids(idx):
    """PID máy ảo chạy ngầm + cửa sổ của ĐÚNG 1 máy (MuMu: info · LDPlayer: list2). MEmu không có → []."""
    out = []
    try:
        if EMU == "mumu":
            v = _mumu_info().get(int(idx)) or {}; out = [v.get("headless_pid"), v.get("pid")]
        elif EMU == "ld":
            for ln in (_ldrun(["list2"], 60).stdout or "").splitlines():
                q = ln.strip().split(",")
                if len(q) >= 7 and q[0].strip() == str(idx): out = [q[6], q[5]]       # pid máy ảo (Ld9BoxHeadless), pid cửa sổ (dnplayer)
    except Exception: pass
    return [int(x) for x in out if str(x).strip().isdigit() and int(x) > 0]
def force_stop(p, graceful=True):
    """TẮT HẲN 1 máy: tắt bình thường trước; ~40 giây vẫn chạy (máy treo, giả lập không tắt được) → tắt cưỡng bức đúng tiến trình
       của máy đó (kiểm tên file chạy là của giả lập). Không đụng máy khác. Trả về (đã tắt?, cách tắt).
       graceful=False: nơi gọi vừa tắt bình thường rồi mà máy vẫn chạy → vào thẳng bước tắt cưỡng bức."""
    i = IDX(p)
    if i is None: return False, f"không thấy máy trong {EMU_NAME}"
    if not graceful: _stop_marks(str(i))                  # 16/11e: tắt thẳng bằng tiến trình → vẫn ghi dấu đang khởi động lại
    if graceful:
        memuc("stop", "-i", i, timeout=90)
        if not is_running(p["name"], p): return True, "tắt bình thường"
    killed = []
    pids = _vm_pids(i) + (sorted(_memu_front_pids(p["name"])) if EMU == "memu" else [])
    for pid in pids:
        im = _proc_image(pid)
        if im and any(k in im.lower() for k in _VM_IMAGES.get(EMU, ())):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NOWIN); killed.append(f"{im} #{pid}")
    how = "máy treo → tắt cưỡng bức " + (", ".join(killed) if killed else "(không thấy tiến trình của máy)")
    for k in range(20):
        if k == 10: memuc("stop", "-i", i, timeout=60)        # giả lập vẫn ghi "đang chạy" → nhắc tắt lần nữa
        if not is_running(p["name"], p): return True, how
        time.sleep(2)
    return False, how
def cmd_restart(a):
    st, p = _need(a.name)
    _pre_slot(p)                                              # 16/11e: xin lượt bật trước (máy còn chạy) → tắt xong bật liền
    with _cycle():
        hard, force = _restart_body(a, p)
    if p.get("proxy"): _proxy_later(p["name"])                   # 22/11: máy có 🌐 proxy → bật lại proxy ngay khi Android lên (không chờ vòng 5 phút)
    print("✅ Đã khởi động lại (máy treo — đã tắt hẳn rồi bật)" if hard else "✅ Đã ép khởi động lại" if force else "✅ Đã khởi động lại")
def _restart_body(a, p):
    _restart_mark(a.name); adb("disconnect", serial(p), timeout=15)
    force = bool(getattr(a, "force", False)); hard = False
    if force:                                                 # admin ÉP khởi động lại (máy treo): tắt hẳn rồi mới bật
        ok, how = force_stop(p); print(("   ✓ " if ok else "   ⚠ ") + how, flush=True)
        if not ok: print(f"❌ Chưa tắt được máy ({EMU_NAME} không trả lời) — đợi 1 phút rồi thử lại, hoặc ■ Tắt tất cả → ▶ Bật tất cả."); sys.exit(6)
    else:
        memuc("stop", "-i", IDX(p), timeout=120)
        # 16/11: khách / admin bấm "Khởi động lại" mà máy TREO (tắt êm không được) → trước đây máy vẫn chạy, lệnh bật không làm gì,
        # máy treo mãi tới khi admin ép. Chờ thêm 15 giây (máy chủ bận tắt chậm); vẫn chạy → tắt hẳn ĐÚNG máy đó rồi bật.
        t_w = time.time()
        while time.time() - t_w < 15 and is_running(a.name, p): time.sleep(3)
        if is_running(a.name, p):
            ok, how = force_stop(p, graceful=False); print(("   ✓ " if ok else "   ⚠ ") + how, flush=True)
            if not ok: print("❌ Chưa tắt được máy (máy đang treo) — đợi 1 phút rồi bấm khởi động lại lần nữa, hoặc báo hỗ trợ."); sys.exit(6)
            force = True                                      # vừa tắt cưỡng bức → bật lỗi thì thử lại 1 lần (như ép khởi động lại)
            hard = True
    time.sleep(3); r = start_phone(p)
    if _start_failed(r) and force:
        time.sleep(10); r = start_phone(p)                    # vừa tắt cưỡng bức: giả lập có thể cần vài giây mới bật lại được
    if _start_failed(r): print(f"❌ {EMU_NAME} không bật được máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); sys.exit(5)
    return hard, force

def _ks_kick(p):
    """Máy ảo treo cứng (canh mãi adb không nối được): tắt hẳn rồi bật lại — như ép khởi động lại, KHÔNG chờ Android (lệnh gọi sẽ canh tiếp)."""
    nm = p["name"]; i = IDX(p)
    if i is None or _op_busy(i): return False              # lệnh khác đang tắt / bật máy này → không chen
    _pre_slot(p)
    with _cycle():
        _restart_mark(nm); adb("disconnect", serial(p), timeout=15)
        ok, how = force_stop(p); print(("     ✓ " if ok else "     ⚠ ") + how, flush=True)
        if not ok: return False
        time.sleep(3); r = start_phone(p)
        if r is None or _start_failed(r): time.sleep(10); r = start_phone(p)
    return not (r is None or _start_failed(r))
def cmd_ksfix(a):
    """16/11k2: SỔ KHOÁ Android (keystore) hỏng → máy sập / khởi động lại liên tục (màn đen, khách chờ mãi). Lệnh này CANH từng máy tới lúc
       adb nối được rồi kiểm + xoá file hỏng + khởi động lại Android, chờ lên lại.
         phonectl ksfix TÊN [TÊN …]   ·   phonectl ksfix --all (mọi máy khách đang chạy)
         --chi-kiem: chỉ báo, không sửa · --cho GIÂY: canh tối đa (mặc định 300) · --bat: máy đang tắt thì bật lên để kiểm
       17/11g: cùng lúc kiểm + sửa FILE HỆ THỐNG Android hỏng do máy chủ bị tắt ngang (roles.xml… rỗng → Android không bao giờ lên): đổi tên
       file hỏng, Android tự tạo lại, chờ máy lên. Dòng cuối "KSFIX: … hỏng N · đã sửa M" tính cả 2 loại."""
    if EMU == "ld": print("KSFIX: máy chủ LDPlayer (Android 9) không dùng sổ khoá kiểu mới — không cần kiểm."); return
    st = load(); names = list(a.names or [])
    if a.all: names = [str(p["name"]) for p in st["phones"] if str(p.get("name", "")).startswith(("cp_", "spare_"))]
    if not names: print("Cách dùng: phonectl ksfix TÊN_MÁY  ·  phonectl ksfix --all  (thêm --chi-kiem để chỉ kiểm, --cho GIÂY để canh lâu hơn)"); sys.exit(1)
    cho = max(10, int(getattr(a, "cho", 300) or 300)); fixing = not a.chi_kiem and (KS_FIX or BOOT_FIX)
    bfix = {}; bbad = {}                                    # 17/11g: tên máy → [file hệ thống vừa đổi tên] / [file hỏng chưa sửa]
    v = vms(); pend = {}; off = err = 0
    for nm in names:
        p = rec(nm, st)
        if not p: print(f"   - {nm}: không có trong danh sách máy chủ này"); continue
        try: on = is_running(nm, p, v)
        except Exception: on = False
        if not on:
            if fixing and (getattr(a, "bat", False) or (not a.all and not p.get("hold"))):
                print(f"   ▶ {nm}: máy đang tắt → bật lên để kiểm", flush=True)
                r = start_phone(p)
                if r is None or _start_failed(r): print(f"   ✗ {nm}: {EMU_NAME} không bật được máy"); err += 1; continue
            else:
                off += 1; print(f"   - {nm}: máy đang tắt / ngủ — bỏ qua (lần bật sau tự kiểm)"); continue
        pend[nm] = p
    n = len(pend); res = {}; bids = {}; t0 = time.time(); said = False; kicked = set(); nr = {}
    while pend and time.time() - t0 < cho:
        for nm, p in list(pend.items()):
            port = p["port"]; _adb_fresh(port)
            b0 = _BF_HIT.get(port, {}).get("n", 0)
            r = _ks_fix_now(port) if fixing else keystore_state(port)
            hb = _BF_HIT.get(port, {})
            if hb.get("n", 0) != b0: bfix[nm] = list(hb.get("last") or [])
            if r != "?" and (hb.get("bad") or hb.get("fail")): bbad[nm] = list(hb.get("bad") or []) + list(hb.get("fail") or [])
            if r == "?" and _ks_noroot(port):                 # adb nối được nhưng không có root (Android 15 / KernelSU) → không kiểm được, bỏ qua
                nr[nm] = nr.get(nm, 0) + 1
                if nr[nm] >= 2:
                    pend.pop(nm); res[nm] = "noroot"
                    print(f"   - {nm}: máy không cho máy chủ quyền root (Android 15 / KernelSU) — không kiểm được sổ khoá, bỏ qua", flush=True)
                continue
            if r == "?":
                # canh lâu mà adb chưa nối được lần nào → máy ảo treo cứng: tắt hẳn + bật lại 1 lần rồi canh tiếp (đầu lần khởi động adb nối được)
                if fixing and nm not in kicked and time.time() - t0 > min(90, cho / 2):
                    kicked.add(nm)
                    print(f"   ↻ {nm}: canh {int(time.time() - t0)} giây chưa nối được adb → tắt hẳn + bật lại máy ảo rồi canh tiếp", flush=True)
                    try: _ks_kick(p)
                    except SystemExit: pass
                    except Exception as e: print(f"     (bật lại lỗi: {e})", flush=True)
                continue
            res[nm] = r; pend.pop(nm)
            if r == "fixed":
                sz = _KS_SIZE.get(port)
                print(f"   🔑 {nm}: sổ khoá HỎNG" + (f" (file {sz} byte)" if sz else "") + " → đã xoá file hỏng, khởi động lại Android…", flush=True)
                _ks_event(nm, "lệnh ksfix", port); _restart_write(nm); bids[nm] = _boot_id(port); _ks_reboot(port)
            elif r == "bad":
                print(f"   ✗ {nm}: sổ khoá HỎNG" + (" (chạy lại không kèm --chi-kiem để sửa)" if not fixing else " — chưa xoá được file hỏng" if KS_FIX
                                                     else " (KS_FIX=0 → chỉ báo, không tự sửa)"), flush=True)
            else: print(f"   ✓ {nm}: sổ khoá " + ("tốt" if r == "ok" else "chưa có (bình thường)"), flush=True)
        if pend:
            if not said and time.time() - t0 > 8:
                said = True; print(f"   … còn {len(pend)} máy chưa nối được (đang khởi động / sập liên tục) — canh tối đa {cho} giây", flush=True)
            time.sleep(2)
    for nm, p in pend.items():
        err += 1; print(f"   ✗ {nm}: chưa kiểm được — {_KS_WHY.get(p['port'], 'adb chưa nối được máy')}", flush=True)
    fixed = [nm for nm, r in res.items() if r == "fixed"]; okf = 0
    if fixed:
        print(f"   Chờ {len(fixed)} máy vừa sửa lên lại (tối đa {BOOT_WAIT // 60} phút)…", flush=True)
        for nm in fixed:
            p = rec(nm) or {}; port = p.get("port")
            ok = bool(port) and _wait_reboot(nm, port, bids.get(nm, ""), p)
            k = keystore_state(port) if ok else "?"
            if ok and k != "bad":
                okf += 1; res[nm] = "fixed_ok"; print(f"   ✓ {nm}: Android đã lên lại, sổ khoá " + {"ok": "tốt", "none": "mới (tốt)", "?": "chưa kiểm lại được"}[k], flush=True)
                try: set_hold(nm, False)
                except Exception: pass
            else: print(f"   ✗ {nm}: " + ("sổ khoá VẪN HỎNG sau khi sửa" if ok else "Android chưa lên lại sau khi sửa — chống kẹt sẽ canh tiếp"), flush=True)
    # 17/11g: máy vừa đổi tên file hệ thống hỏng → Android tự khởi động tiếp: chờ lên (máy vừa sửa cả sổ khoá đã chờ ở trên)
    bok = set(); bno = set(); bw = [nm for nm in bfix if nm not in fixed]
    if bw:
        print(f"   Chờ {len(bw)} máy vừa sửa file hệ thống lên (tối đa {BOOT_WAIT // 60} phút)…", flush=True)
        for nm in bw:
            p = rec(nm) or {}; port = p.get("port")
            ok = bool(port) and _wait_android(nm, port, p, why="sau khi sửa file hệ thống")
            if ok:
                bok.add(nm); print(f"   ✓ {nm}: Android đã lên sau khi sửa file hệ thống", flush=True)
                try: set_hold(nm, False)
                except Exception: pass
            else:
                bno.add(nm); print(f"   ✗ {nm}: Android CHƯA lên sau khi sửa file hệ thống — xem vì sao: phonectl khammay {nm}", flush=True)
    def _rep_ok(nm):
        r = res.get(nm)
        if r in ("bad", "fixed"): return False                 # sổ khoá hỏng chưa xoá được / xoá rồi mà Android chưa lên lại
        if nm in bbad and nm not in bfix: return False         # file hệ thống hỏng chưa đổi tên (chỉ kiểm / đổi tên lỗi)
        if nm in bfix and r != "fixed_ok" and nm not in bok: return False
        return True
    broken = {nm for nm, r in res.items() if r in ("fixed", "fixed_ok", "bad")} | set(bfix) | set(bbad)
    repaired = {nm for nm in broken if _rep_ok(nm)}
    nnr = sum(1 for r in res.values() if r == "noroot"); nbf = len(set(bfix) | set(bbad))
    print(f"KSFIX: kiểm {n} máy đang chạy · hỏng {len(broken)} · đã sửa {len(repaired)} · lỗi {err + (len(fixed) - okf) + len(bno)}"
          + (f" · {off} máy tắt (bỏ qua)" if off else "") + (f" · {nnr} máy không có root cho máy chủ (bỏ qua)" if nnr else "")
          + (f" · trong đó file hệ thống hỏng {nbf}" if nbf else ""))
    if fixing and len(broken) > len(repaired): sys.exit(2)
    if fixing and err: sys.exit(3)

# ---------- 17/11g: KHÁM MÁY — vì sao máy không lên (chỉ ĐỌC) ----------
def _kh_tail(path, n=300000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); z = f.tell(); f.seek(max(0, z - n)); return f.read().decode("utf-8", "replace")
    except OSError: return ""
def _kh_host(i):
    """Dấu vết phía máy chủ của máy ảo MuMu số i (không cần adb): bước khởi động cuối Android báo về, mã lỗi VBox gần nhất, cỡ ổ dữ liệu."""
    out = []
    try:
        d = _vm_dir(i)
        if not d: return out
        st_ = re.findall(r"android_boot_status\W{1,8}([A-Za-z_]{3,40})", _kh_tail(os.path.join(d, "logs", "shell.log")))
        if st_:
            seq = []
            for x in st_[-40:]:
                if not seq or seq[-1] != x: seq.append(x)
            out.append("bước khởi động Android gần nhất (shell.log): " + " → ".join(seq[-4:]) + (f" · lặp lại {st_.count(st_[0])} vòng" if len(st_) > 8 and st_.count(st_[0]) > 2 else ""))
        ve = re.findall(r"VERR_[A-Z0-9_]{3,40}", _kh_tail(os.path.join(d, "logs", "VBox.log"), 120000))
        if ve: out.append("mã lỗi máy ảo gần nhất (VBox.log): " + ", ".join(dict.fromkeys(ve[-6:])))
        f = os.path.join(d, "data.vdi")
        if os.path.isfile(f): out.append(f"ổ dữ liệu máy: {os.path.getsize(f) / 2**20:.0f} MB")
        fr = shutil.disk_usage(d).free / 2**30
        if fr < 10: out.append(f"⚠ ổ đĩa máy chủ chỉ còn {fr:.1f} GB trống")
    except Exception: pass
    return out
def _kham_one(nm, p, v, inf):
    """Khám 1 máy → (mã, câu kết luận); in các dòng chi tiết. Chỉ đọc: không sửa, không tắt / bật gì."""
    i = IDX(p, v); port = p.get("port"); s_ = f"127.0.0.1:{port}"
    print(f"--- {nm} · máy số {i if i is not None else '?'} · cổng {port} · Android {p.get('android') or '?'}"
          + (" · đang NGỦ" if p.get("sleep") else " · đang GIỮ (khoá / tạm dừng)" if p.get("hold") else ""), flush=True)
    if i is None: return "MAT", f"{EMU_NAME} không còn máy tên này (máy \"ma\") — chạy lệnh A để xử lý"
    m = inf.get(i, {}) if isinstance(inf, dict) else {}
    ec = m.get("launch_err_code"); em = str(m.get("launch_err_msg") or "").strip()[:100]
    err_txt = f"{ec} {em}".strip() if ec not in (None, 0, "0", "") else ""
    if m:
        print(f"   {EMU_NAME}: tiến trình {'chạy' if m.get('is_process_started') else 'tắt'} · Android {'đã lên' if m.get('is_android_started') else 'chưa lên'}"
              + (f" · trạng thái {m.get('player_state')}" if m.get("player_state") else "") + (f" · lỗi lúc bật: {err_txt}" if err_txt else ""), flush=True)
    if not is_running(nm, p, v):
        return "TAT", "máy đang tắt" + (" (ngủ — khách mở là tự bật)" if p.get("sleep") else " (đang giữ / khoá)" if p.get("hold") else f" — bật: phonectl start {nm}")
    host = _kh_host(i) if EMU == "mumu" else []
    seen = _adb_fresh(port); up = booted(port)
    if up:
        return "OK", "Android ĐÃ LÊN — máy bình thường"
    if not seen:
        for x in host: print("   " + x, flush=True)
        return "ADB", ("máy ảo chạy nhưng adb KHÔNG nối được (Android không mở được cổng adb / máy ảo treo lúc bật)" + (f" · {EMU_NAME} báo {err_txt}" if err_txt else "")
                       + f" — thử: phonectl restart {nm} --force · vẫn vậy thì gửi Claude các dòng trên")
    try: upt = float(((adb("-s", s_, "shell", "cat /proc/uptime", timeout=10).stdout or "").split() or ["0"])[0])
    except Exception: upt = 0.0
    p1 = _ss_pid(port); time.sleep(8); p2 = _ss_pid(port)
    loop = bool(p1 and p2 and p1 != p2)
    sig = _bf_sig(port)
    ks = keystore_state(port)                                 # lệnh root CHỈ KIỂM (in dòng 📄 nếu file hệ thống hỏng)
    bad = list(_BF_HIT.get(port, {}).get("bad") or [])
    print(f"   adb nối được · Android CHƯA lên · máy ảo đã chạy {int(upt)} giây · giao diện (system_server) "
          + ("SẬP / bật lại liên tục" if loop else "chưa chạy" if not (p1 or p2) else "đang chạy") + f" · sổ khoá: "
          + {"ok": "tốt", "none": "chưa có (bình thường)", "bad": "HỎNG", "?": "chưa kiểm được (" + _KS_WHY.get(port, "?") + ")"}[ks], flush=True)
    if sig: print("   dấu hiệu sập: " + sig, flush=True)
    for x in host: print("   " + x, flush=True)
    if bad:
        return "FILE", ("file hệ thống Android HỎNG (" + ", ".join(x + ".xml" for x in bad) + ") do máy chủ bị tắt ngang → sửa (giữ dữ liệu khách): phonectl ksfix " + nm)
    if ks == "bad": return "KS", f"sổ khoá Android HỎNG → sửa: phonectl ksfix {nm}"
    mf = re.search(r"Missing <([a-z-]+)> in ", sig or "")
    if mf and ks == "?" and _ks_noroot(port):
        return "FILE", (f"file hệ thống Android HỎNG ({mf.group(1)}.xml) do máy chủ bị tắt ngang, nhưng máy không cho máy chủ quyền root (Android 15) "
                        "nên CHƯA tự sửa được — gửi Claude dòng này (dữ liệu khách còn nguyên trong ổ máy)")
    if sig: return "SAP", "Android SẬP lúc khởi động vì lý do chưa có cách tự sửa — gửi Claude dòng \"dấu hiệu sập\" ở trên (dữ liệu khách còn nguyên trong ổ máy)"
    if upt and upt < 240: return "DANGLEN", f"Android đang khởi động (máy ảo mới chạy {int(upt)} giây) — chờ thêm 2–3 phút"
    if ks == "?" and _ks_noroot(port):
        return "ROOT", "Android chưa lên; máy không cho máy chủ quyền root (Android 15) nên không kiểm sâu được" + (f" · {EMU_NAME} báo {err_txt}" if err_txt else "")
    return "CHUALEN", f"Android chưa lên sau {int(upt)} giây, không thấy dấu hiệu sập — thử: phonectl restart {nm} --force"
def cmd_khammay(a):
    """17/11g: VÌ SAO MÁY KHÔNG LÊN — chỉ ĐỌC (không sửa, không tắt / bật gì).
         phonectl khammay TÊN [TÊN …]   ·   phonectl khammay --all (mọi máy khách đang chạy mà Android chưa lên)
       Mỗi máy 1 dòng kết luận: KHAMMAY <tên>: [MÃ] <vì sao + làm gì>. MÃ: OK · TAT · MAT · ADB · FILE · KS · SAP · ROOT · DANGLEN · CHUALEN."""
    st = load(); v = vms(); names = list(dict.fromkeys(a.names or [])); inf = {}
    if EMU == "mumu":
        try: inf = _mumu_info()
        except Exception: inf = {}
    if a.all:
        for p in st["phones"]:
            nm = str(p.get("name", ""))
            if not nm.startswith(("cp_", "spare_")) or p.get("hold") or nm in names: continue
            try:
                if is_running(nm, p, v) and not booted(p["port"]): names.append(nm)
            except Exception: pass
        if not names: print("KHAMMAY: mọi máy khách đang chạy đều đã lên Android — không có máy nào cần khám."); return
    if not names: print("Cách dùng: phonectl khammay TÊN_MÁY [TÊN …]  ·  phonectl khammay --all"); sys.exit(1)
    out = {}
    for nm in names:
        p = rec(nm, st)
        if not p: print(f"--- {nm}: không có trong danh sách máy chủ này", flush=True); out[nm] = "KHONGCO"; continue
        try: code, txt = _kham_one(nm, p, v, inf)
        except Exception as e: code, txt = "LOI", f"khám lỗi: {e}"
        out[nm] = code
        print(f"KHAMMAY {nm}: [{code}] {txt}", flush=True)
    print("KHAMMAY xong: " + " · ".join(f"{k} {sum(1 for c in out.values() if c == k)}" for k in sorted(set(out.values()))), flush=True)

def cmd_waitboot(a):
    st, p = _need(a.name)
    if not is_running(a.name, p): start_phone(p)          # máy đang tắt (lần bật trước bị ngắt) → bật lại rồi mới chờ
    ok = wait_boot(a.name, p["port"], apps=not a.noapps)
    print("Android đã khởi động xong." if ok else "Chưa kết nối được, sẽ tự thử lại."); sys.exit(0 if ok else 5)

def cmd_renew(a):
    st, p = _need(a.name)
    base = max(parse_dt(p["expires"]), now())
    if getattr(a, "base", ""):                               # hạn trên web muộn hơn hạn ghi trong máy chủ → cộng từ hạn trên web (khách không thiệt)
        try: base = max(base, parse_dt(a.base))
        except Exception: pass
    base = base + datetime.timedelta(days=a.days)
    st = load(); q = rec(a.name, st)                          # ghi vào đúng bản trạng thái vừa đọc (không ghi đè thay đổi khác)
    if not q: print("Không có máy tên này."); sys.exit(1)
    q["expires"] = base.isoformat(); save(st); p["expires"] = q["expires"]
    if parse_dt(rec(a.name)["expires"]) != base: print("❌ Chưa ghi được hạn mới vào phones.json."); sys.exit(3)
    if not is_running(a.name, p) and not _asleep(q): start_phone(p); wait_boot(a.name, p["port"], apps=False)   # máy đang ngủ: để ngủ tiếp (khách mở là bật)
    print(f"🔄 '{a.name}' gia hạn +{a.days} ngày → hết hạn {fmt(base)}")
    print("RENEW_OK " + base.isoformat())

def cmd_resize(a):
    st, p = _need(a.name)
    ram = a.ram if a.ram > 0 else float(p["ram"]); cpu = a.cpu if a.cpu > 0 else float(p["cpu"])
    tot, av = mem(); av -= _sleep_ram(st)
    if ram > float(p["ram"]) and av - (ram - float(p["ram"])) < RESERVE: print("LỖI: RAM Windows không đủ để nâng."); sys.exit(4)
    _pre_slot(p)                                              # 16/11e
    with _cycle():
        _restart_mark(p.get("name")); adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
        configure(IDX(p), ram, cpu, p.get("res", "720x1280"), p.get("dpi"))
        fl = _fails()
        if fl.pop(a.name, None) is not None: _fails_put(fl)      # cấu hình mới → bỏ lịch "tạm không bật" do lỗi bật với cấu hình cũ
        start_phone(p)
    wait_boot(a.name, p["port"], apps=False)
    st = load(); q = rec(a.name, st); q["ram"], q["cpu"] = ram, cpu; save(st)
    print(f"⬆️ '{a.name}' → {ram:g}GB RAM · {cpu:g} nhân")

# ---------- KIỂM / SỬA RAM + NHÂN THẬT của máy khách (lỗi 09/11: gói 16GB · 8 nhân mà Android chỉ thấy ~6GB) ----------
def _live_hw(p):
    """RAM (GB) + số nhân Android ĐANG THẤY (máy phải chạy) → (gb, nhân); không hỏi được → (None, None)."""
    s = serial(p)
    try:
        if (adb("-s", s, "get-state", timeout=10).stdout or "").strip() != "device": adb_connect(p["port"])
        out = adb("-s", s, "shell", "head -1 /proc/meminfo; nproc", timeout=15).stdout or ""
    except Exception:
        return None, None
    m = re.search(r"MemTotal:\s*(\d+)\s*kB", out); n = re.search(r"^\s*(\d+)\s*$", out, re.M)
    return (int(m.group(1)) / 1048576 if m else None), (int(n.group(1)) if n else None)

def _hw_row(p, v):
    """Kiểm 1 máy: gói đã bán · giả lập đang đặt · Android đang thấy → dict (bad = danh sách chỗ sai)."""
    want_r, want_c = float(p["ram"]), int(round(float(p["cpu"])))
    cap_r, cap_c = min(want_r, MAX_RAM), max(1, min(want_c, MAX_CPU))
    i = IDX(p, v)
    r = {"idx": i, "want": (want_r, want_c), "cap": (cap_r, cap_c), "set": (None, None), "live": (None, None), "run": False, "bad": [], "fix": False}
    if i is None: r["bad"].append("không thấy máy trong giả lập"); return r
    r["run"] = bool(v[i]["running"])
    if EMU == "mumu":
        allk = _mumu_all(i); c, m, _mode = _mumu_hw_eff(allk); r["set"] = (m, c)
        if c is None or m is None: r["bad"].append("không đọc được cài đặt MuMu")
        elif not _mumu_hw_ok(allk, cap_c, cap_r): r["bad"].append(f"MuMu đang đặt {m:g}GB · {int(c)} nhân"); r["fix"] = True
    if r["run"]:
        gb, n = _live_hw(p); r["live"] = (gb, n)
        if gb is not None and gb < cap_r * 0.9: r["bad"].append(f"Android chỉ thấy {gb:.1f}GB"); r["fix"] = True
        if n is not None and n < cap_c: r["bad"].append(f"Android chỉ thấy {n} nhân"); r["fix"] = True
    if (cap_r, cap_c) != (want_r, want_c): r["bad"].append(f"trần máy chủ chỉ cho {cap_r:g}GB · {cap_c} nhân")
    return r

def _hw_cap_warn():
    if EMU == "mumu" and (MAX_RAM < 16 or MAX_CPU < 32):
        print(f"⚠ Trần 1 máy đang là {MAX_RAM:g}GB · {MAX_CPU} nhân — THẤP hơn mức web bán cho MuMu (Android 12/15: 16GB · 32 nhân)\n"
              "  → máy gói lớn bị cắt bớt. Sửa trước:  python phonectl.py setconf MEMU_MAX_RAM=16 MEMU_MAX_CPU=32", flush=True)
        return True
    return False

def cmd_ramcheck(a):
    st = load(); v = vms()
    print(f"{EMU_NAME} · trần 1 máy: {MAX_RAM:g}GB · {MAX_CPU} nhân (MEMU_MAX_RAM / MEMU_MAX_CPU trong cloudphone.conf)", flush=True)
    _hw_cap_warn()
    bad, capped = [], []
    for p in sorted(st["phones"], key=lambda x: x["name"]):
        r = _hw_row(p, v)
        sm, sc = r["set"]; lg, ln = r["live"]
        s_txt = f"{sm:g}GB/{int(sc)}" if sm is not None and sc is not None else "—"
        l_txt = f"{lg:.1f}GB/{ln}" if lg is not None and ln is not None else ("(đang tắt)" if not r["run"] else "?")
        print(f"{'✗' if r['bad'] else '✓'} {p['name']:<15} #{'?' if r['idx'] is None else r['idx']:<3} gói {r['want'][0]:g}GB/{r['want'][1]}"
              f" · giả lập {s_txt} · Android {l_txt}" + (f"  ← {'; '.join(r['bad'])}" if r["bad"] else ""), flush=True)
        if r["fix"]: bad.append(p["name"])
        elif r["bad"] and r["cap"] != r["want"]: capped.append(p["name"])
    print(f"\n{len(st['phones'])} máy · {len(bad)} máy cần sửa RAM/CPU" + (f": {' '.join(bad)}" if bad else "")
          + (f" · {len(capped)} máy bị trần máy chủ cắt" if capped else ""))
    if bad: print("→ Sửa (máy đang chạy tự tắt + bật lại ~1–2 phút):  python phonectl.py ramfix --all   ·   1 máy:  python phonectl.py ramfix TÊN")

def cmd_ramfix(a):
    if EMU != "mumu": print("ramfix chỉ dùng cho máy chủ MuMu (LDPlayer / MEmu: dùng resize)."); sys.exit(1)
    st = load(); names = [p["name"] for p in st["phones"]] if a.all else list(a.names)
    if not names: print("Cách dùng: python phonectl.py ramfix TÊN [TÊN…]   hoặc   python phonectl.py ramfix --all"); sys.exit(1)
    capw = _hw_cap_warn(); ok_n = fail_n = skip_n = 0
    for name in names:
        p = rec(name)
        if not p: print(f"✗ {name}: không có trong danh sách máy của máy chủ này", flush=True); fail_n += 1; continue
        r = _hw_row(p, vms())
        if r["idx"] is None: print(f"✗ {name}: không thấy trong MuMu", flush=True); fail_n += 1; continue
        if not r["fix"]:
            skip_n += 1
            if not a.all: print(f"✓ {name}: đã đúng {r['cap'][0]:g}GB · {r['cap'][1]} nhân" + (" (trần máy chủ cắt bớt — xem cảnh báo trên)" if r["cap"] != r["want"] else ""), flush=True)
            continue
        i = r["idx"]; m, c = r["cap"]; was = r["run"]
        print(f"→ {name} (#{i}): {'; '.join(r['bad'])} → đặt {m:g}GB · {c} nhân{' (tắt máy…)' if was else ''}", flush=True)
        if was: _pre_slot(p)                                     # 16/11e
        with _cycle():
            if was:
                adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", i, timeout=120); time.sleep(3)
            ok, msg = _mumu_hw(str(i), c, m)
            if not ok and was:                                   # máy bị bật lại giữa chừng (vòng tự bật của cloudphoned) → tắt lại, thử lần nữa
                memuc("stop", "-i", i, timeout=120); time.sleep(3); ok, msg = _mumu_hw(str(i), c, m)
            print(f"   {'✓' if ok else '✗'} {msg}", flush=True)
            if was: start_phone(p)
        if was:
            wait_boot(name, p["port"], apps=False)
            gb, n = _live_hw(p)
            good = gb is not None and gb >= m * 0.9 and (n is None or n >= c)
            print(f"   {'✓' if good else '✗'} Android đang thấy: {'?' if gb is None else f'{gb:.1f}GB'} · {'?' if n is None else n} nhân", flush=True)
            ok = ok and good
        else:
            print("   (máy đang tắt — lần bật sau chạy cấu hình mới)", flush=True)
        if ok: ok_n += 1
        else: fail_n += 1
    print(f"\nXong: sửa được {ok_n} · lỗi {fail_n} · đã đúng sẵn {skip_n}" + (" · nhớ sửa trần máy chủ (cảnh báo ở trên)" if capw else ""))
    if fail_n: sys.exit(2)

def cmd_reconfig(a):
    st, p = _need(a.name)
    res = a.res or p.get("res") or "720x1280"; fps = clamp_fps(a.fps or p.get("fps", 30)); dpi = auto_dpi(res)
    _pre_slot(p)                                              # 16/11e
    with _cycle():
        _restart_mark(p.get("name")); adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
        configure(IDX(p), p["ram"], p["cpu"], res, dpi)
        if EMU == "mumu": _FPS_FORCE[int(IDX(p))] = fps    # 16/11: trước đây đổi FPS chỉ ghi vào danh sách, máy vẫn chạy FPS cũ → ghi lúc bật (start)
        elif EMU == "memu": memuc("setconfigex", "-i", IDX(p), "fps", fps, timeout=60)
        start_phone(p)
    ok = wait_boot(a.name, p["port"], apps=False)
    st = load(); q = rec(a.name, st); q["res"], q["fps"], q["dpi"] = res, fps, dpi; save(st)
    print(f"✅ '{a.name}' → {res} · {fps} FPS" + ("" if ok else " (đang kết nối lại)"))

def cmd_liveres(a):
    st, p = _need(a.name)
    if not re.match(r"^\d{3,4}x\d{3,4}$", a.res): print("LỖI: --res phải dạng 720x1280."); sys.exit(1)
    dpi = auto_dpi(a.res)
    adb("-s", serial(p), "shell", "wm", "size", a.res); adb("-s", serial(p), "shell", "wm", "density", str(dpi))
    p["res"], p["dpi"] = a.res, dpi; save(st); print(f"✅ '{a.name}' → {a.res} (dpi {dpi}) — không khởi động lại")

def cmd_connect_all(a):
    st = load(); v = vms()
    held = _bs_load()["slots"]
    for p in st["phones"]:
        if p["name"] in held and booted(p["port"]): _boot_done(p["name"])
    online = {l.split()[0] for l in (adb("devices", timeout=20).stdout or "").splitlines()[1:] if l.strip().endswith("device")}
    n = 0
    for p in st["phones"]:
        if serial(p) in online or not is_running(p["name"], p, v): continue
        adb_connect(p["port"]); n += 1; print("🔌 nối lại", p["name"], serial(p))
    if n == 0: print("Tất cả máy đã kết nối.")
    if HIDE:
        for p in st["phones"]:
            if is_running(p["name"], p, v):
                try: hide_window(p["name"])
                except Exception: pass

def cmd_reap(a):
    st = load(); n = 0
    for p in list(st["phones"]):
        exp = parse_dt(p["expires"])
        if exp + datetime.timedelta(minutes=GRACE_MIN) < now():
            a.name = p["name"]; cmd_delete(a); n += 1
        elif exp < now() and is_running(p["name"], p):
            memuc("stop", "-i", IDX(p), timeout=120); print(f"⏸  Hết hạn → tạm dừng '{p['name']}'")
    print(f"Xong. Đã xoá {n} máy.")

def cmd_preinstall(a):
    st = load(); v = vms()
    for p in st["phones"]:
        if (a.all and is_running(p["name"], p, v)) or p["name"] == a.name:
            adb_connect(p["port"]); preinstall(p["name"], p["port"], a.force); grant_perms(p["name"])

def cmd_perms(a):
    v = vms()
    for p in load()["phones"]:
        if is_running(p["name"], p, v): grant_perms(p["name"])

def cmd_quyen(a):
    """17/11e: xem quyền Admin của bảng CloudBlue, tiến trình chung của giả lập và từng máy đang chạy. --sua (phải chạy Admin): mở lại
       chương trình chính chạy sai quyền + tắt êm rồi bật lại ĐÚNG các máy khách đang chạy sai quyền. Dòng cuối (lệnh A đọc):
       QUYEN_KQ dung | khong_biet | khong_can | sai=N | khong_admin | bang_thuong | da_sua=N chua_sua=N [main=da_mo_lai] [con_sai=N].
       Không xoá / tạo máy nào. 17/11e4: máy chủ LDPlayer / MEmu → chỉ báo (khong_can), không tắt / bật lại máy nào."""
    if EMU != "mumu":
        me = _is_admin(); sv = [_elev(p) for p in _svc_pids()]
        svc = True if any(x is True for x in sv) else (False if any(x is False for x in sv) else None)
        W = lambda e: "Admin" if e else ("quyền thường" if e is False else "?")
        print(f"== Quyền chạy — máy chủ {CONF.get('NODE_ID') or '?'} ({EMU_NAME}) · phonectl {PCTL_SUB}")
        print(f"   lệnh này: {W(me)} · bảng / dịch vụ CloudBlue: {W(svc) if svc is not None else 'không thấy'}")
        print(f"   ✓ {EMU_NAME} không có lỗi xung đột quyền như MuMu → không cần tắt / bật lại máy nào")
        print("QUYEN_KQ khong_can"); return
    me, svc, main, vms = _priv_report()
    want = svc if svc is not None else (True if any(e for _, _, e, _ in vms) else (me if not vms else None))
    W = lambda e: "Admin" if e else ("quyền thường" if e is False else "?")
    print(f"== Quyền chạy — máy chủ {CONF.get('NODE_ID') or '?'} ({EMU_NAME}) · phonectl {PCTL_SUB}")
    print(f"   lệnh này: {W(me)} · bảng / dịch vụ CloudBlue: {W(svc) if svc is not None else 'không thấy'}"
          + "".join(f" · {_PNAME.get(im, im)}: {W(e)}" for _, im, e in main))
    bad = [(i, nm, pids) for i, nm, e, pids in vms if want is not None and e is not None and e != want]
    badm = [(p, im) for p, im, e in main if want is not None and e is not None and e != want]
    print(f"   máy đang chạy: {len(vms)} · đúng quyền: {sum(1 for _, _, e, _ in vms if e == want)}"
          + (f" · SAI QUYỀN: {', '.join(_vm_label(*x) for x in bad)}" if bad else "")
          + (f" · tiến trình chung sai quyền: {', '.join(_PNAME.get(im, im) for _, im in badm)}" if badm else ""))
    if want is None: print("QUYEN_KQ khong_biet"); return
    if not bad and not badm: print("   ✓ mọi máy cùng quyền " + W(want)); print("QUYEN_KQ dung"); return
    if not getattr(a, "sua", False):
        print("   ✗ lẫn quyền → giả lập báo xung đột, không bật được máy. Sửa: PowerShell (Admin) / Terminal (Admin) → phonectl.py quyen --sua")
        print(f"QUYEN_KQ sai={len(bad) + len(badm)}"); return
    if want is False:
        print("   ✗ bảng CloudBlue chạy quyền THƯỜNG mà có máy / chương trình giả lập chạy quyền Admin (bật từ cửa sổ Admin) → lẫn quyền.\n"
              "     Sửa: khởi động lại Windows lúc vắng khách (bảng tự chạy lại, mọi máy bật lại cùng 1 quyền)")
        print("QUYEN_KQ bang_thuong"); sys.exit(3)
    if not me:
        print("   ✗ phải chạy bằng PowerShell (Admin) / Terminal (Admin) — bảng CloudBlue chạy bằng quyền Admin"); print("QUYEN_KQ khong_admin"); sys.exit(3)
    ours = [(i, nm, pids) for i, nm, pids in bad if re.match(r"^(cp|spare)_", nm or "") and i is not None and int(i) >= 0]
    other = [x for x in bad if x not in ours]
    for i, nm, pids in other:
        print(f"   ⚠ {_vm_label(i, nm, pids)} chạy sai quyền nhưng không phải máy khách → không đụng: tắt tay máy này trong {EMU_NAME} "
              "(còn chạy là bật máy khác vẫn bị xung đột)")
    done, left = [], [nm for _, nm, _ in other]
    st0 = load(); todo = []; seen_nm = set()
    for i, nm, pids in ours:
        if nm in seen_nm: continue                         # 17/11e3: 1 máy chỉ tắt / bật 1 lần
        seen_nm.add(nm)
        p = rec(nm, st0)
        if not p: print(f"   ⚠ {nm} (#{i}): không có trong danh sách máy khách của máy chủ — không đụng"); left.append(nm); continue
        todo.append((i, nm, pids, p))
    # 1) TẮT HẾT máy sai quyền trước rồi mới BẬT lại (còn 1 máy chạy quyền thường là máy bật bằng Admin vẫn bị MuMu báo xung đột).
    #    Tắt êm bằng Android cho MỌI máy cùng lúc (đi qua adb, không qua giả lập đang báo xung đột) → chờ ≤ 60 giây
    import threading
    for i, nm, pids, p in todo:
        print(f"   … {nm} (#{i}) chạy quyền thường → tắt êm rồi bật lại bằng quyền Admin (khách đang xem bị ngắt ~1–3 phút)", flush=True)
        _restart_mark(nm); _stop_marks(str(i))            # dấu "đang khởi động lại" (khách mở máy được báo chờ) + dịch vụ không bật chen
    th = [threading.Thread(target=_android_off, args=(p,), daemon=True) for _, _, _, p in todo]
    for t in th: t.start()
    for t in th: t.join(30)
    alive = lambda pids: bool(pids) and _emu_alive(pids[0])
    run_ = list(todo); t_w = time.time()
    while run_ and time.time() - t_w < 60:
        time.sleep(3); run_ = [x for x in run_ if alive(x[2])]
    # 2) còn chạy → lệnh tắt của giả lập → chờ ≤ 25 giây
    for i, nm, pids, p in run_: memuc("stop", "-i", str(i), timeout=90)
    t_w = time.time()
    while run_ and time.time() - t_w < 25:
        time.sleep(3); run_ = [x for x in run_ if alive(x[2])]
    # 3) còn chạy (máy treo) → tắt cưỡng bức đúng tiến trình của máy đó
    for i, nm, pids, p in run_:
        k = _kill_pids([x for x in pids if _emu_alive(x)])
        print(("   ✓ " if k else "   ⚠ ") + f"{nm}: không tự tắt → tắt cưỡng bức " + (", ".join(k) if k else "(không tắt được)"), flush=True)
    if run_: time.sleep(4)
    gone = []
    for x in todo:
        if alive(x[2]): left.append(x[1]); print(f"   ✗ {x[1]}: chưa tắt được — không bật lại (chạy lại lệnh sau 1 phút)", flush=True)
        else: gone.append(x); adb("disconnect", serial(x[3]), timeout=15)
    # 4) tiến trình chung của MuMu chạy sai quyền: tắt chương trình chính sai quyền → chờ dịch vụ máy ảo sai quyền thoát → mở lại
    #    chương trình chính bằng quyền Admin (sau khi máy sai quyền đã tắt hết → MuMu không báo xung đột nữa)
    main_fixed = False
    if gone or badm: _lo, main_fixed = _priv_leftovers(60 if gone else 30)
    # 5) bật lại bằng quyền Admin THEO LƯỢT (tối đa vài máy cùng khởi động), trả lượt ngay khi Android lên
    queue = list(gone); booting = {}; t_end = time.time() + 1500
    while (queue or booting) and time.time() < t_end:
        for nm in list(booting):
            p, t1 = booting[nm]
            if time.time() - t1 > 240 or booted(p["port"]): _boot_done(nm); del booting[nm]
        if queue and _boot_take(queue[0][1], prio=True, maxwait=2) is not None:
            i, nm, pids, p = queue.pop(0); _PRE.add(nm)
            r = start_phone(p)
            if r is None or _start_failed(r):
                _PRE.discard(nm); _boot_done(nm); left.append(nm)
                print(f"   ✗ {nm}: chưa bật lại được — " + ((((r.stdout or "") + (r.stderr or "")).strip()[-160:]) if r is not None else "?")
                      + " (bảng sẽ tự bật lại)", flush=True)
            else:
                done.append(nm); booting[nm] = (p, time.time()); print(f"   ✓ {nm}: đã bật lại bằng quyền Admin", flush=True)
            continue
        time.sleep(3)
    for x in queue: left.append(x[1]); print(f"   ✗ {x[1]}: hết giờ chờ lượt bật — bảng sẽ tự bật lại máy này", flush=True)
    # 6) kiểm lại
    me2, svc2, main2, vms2 = _priv_report()
    nb = sum(1 for _, _, e, _ in vms2 if e is False) + sum(1 for _, _, e in main2 if e is False)
    print(f"   sau khi sửa: máy đang chạy {len(vms2)} · còn sai quyền {nb}", flush=True)
    print(f"QUYEN_KQ da_sua={len(done)} chua_sua={len(left)}" + (" main=da_mo_lai" if main_fixed else "") + (f" con_sai={nb}" if nb else ""))

def cmd_ldbase(a):
    """17/11a: máy chủ LDPlayer phải có ít nhất 1 máy trong LDPlayer (máy gốc) thì tool mới đọc được danh sách + tạo được máy khách.
       LDPlayer vừa cài chưa có máy nào → tạo máy gốc 'LDPlayer' (không bao giờ xoá máy này).
       In 1 dòng: LDBASE co · LDBASE da_tao · LDBASE bo_qua (không phải máy chủ LDPlayer) · LDBASE loi <lý do> (mã 4)."""
    if EMU != "ld" or not LD: print("LDBASE bo_qua (máy chủ này không chạy LDPlayer)"); return
    if vms_sure(tries=2): print("LDBASE co"); return
    r = memuc("ensurebase", timeout=240)
    if r.returncode == 0: print((r.stdout or "").strip() or "LDBASE co"); return
    print("LDBASE loi " + (((r.stderr or "") + " " + (r.stdout or "")).strip()[-160:] or "không rõ lý do")); sys.exit(4)

def cmd_vmlist(a):
    """In mọi máy trong giả lập (MEmu hoặc LDPlayer): số,tên,đang chạy(1/0),số nhân — cho kiemtra.py / donweb.py."""
    for i, x in sorted(vms().items()):
        o = memuc("getconfigex", "-i", i, "cpus", timeout=30).stdout or ""
        m = re.search(r"Value:\s*(\S+)", o)
        print(f"{i},{x['name']},{1 if x['running'] else 0},{m.group(1) if m else '?'}")

def cmd_tuneall(a):
    """Tối ưu lại MỌI máy đang chạy (máy nhẹ, tắt hiệu ứng…) + in kết quả từng máy."""
    v = vms()
    for p in load()["phones"]:
        if not is_running(p["name"], p, v): continue
        adb_connect(p["port"]); ok = tune(p["name"], p["port"]); grant_perms(p["name"], p["port"])
        print(("✅ " if ok else "⚠ ") + p["name"], flush=True)

def _has_su(p):
    """Máy (đang chạy) có lệnh su chưa — có su thì tool cần root chạy được."""
    try: o = (ashell(p["name"], "command -v su 2>/dev/null; ls /system/xbin/su /system/bin/su /sbin/su 2>/dev/null", timeout=20).stdout or "")
    except Exception: return False
    return bool(re.search(r"(^|/)su\s*$", o, re.M))

def _su_ready(p):
    """Máy (đang chạy) đã dùng được quyền root chưa: adb là root, hoặc có lệnh su (MuMu "Enable root" / LDPlayer root đã bật)."""
    try:
        s_ = serial(p)
        if (adb("-s", s_, "get-state", timeout=15).stdout or "").strip() != "device": adb_connect(p["port"])
        if (adb("-s", s_, "shell", "id -u", timeout=15).stdout or "").strip() == "0": return True
    except Exception:
        pass
    return _has_su(p)

def _root_enable_restart(p):
    """Bật root GỐC của giả lập cho máy đang chạy mà chưa có su: tắt máy → bật root (MuMu chỉ cho ghi lúc máy TẮT) → bật lại → chờ khởi động.
       Dùng chung cho "Root máy" (rootfix --force) và "Root theo app" (rootcfg --set --on). Trả True nếu xong đã có su."""
    v = vms(); i = IDX(p, v)
    if i is None: return False
    print(f"   {p['name']} (#{i}): bật root → khởi động lại máy (~1 phút)…", flush=True)
    _pre_slot(p)                                              # 16/11e
    with _cycle():
        _restart_mark(p.get("name")); adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", i, timeout=120); time.sleep(3)
        if EMU == "mumu":
            _MUMU_KEYS.pop(str(i), None); _mumu_set(str(i), {"root": 1})
            if not _mumu_root_on(i):                           # máy bị bật lại giữa chừng (vòng tự bật của cloudphoned) → tắt lại, ghi lại
                memuc("stop", "-i", i, timeout=120); time.sleep(3); _MUMU_KEYS.pop(str(i), None); _mumu_set(str(i), {"root": 1})
        else:
            memuc("setconfigex", "-i", i, "enable_su", 1, timeout=60)
        start_phone(p)
    wait_boot(p["name"], p["port"], apps=False)
    return _su_ready(p)

def _mumu_root_on(i):
    """MuMu: "Enable root" (root_permission) của máy đã BẬT trong cài đặt chưa · None = không phải MuMu / không đọc được."""
    if EMU != "mumu": return None
    allk = _mumu_all(i)
    if "root_permission" not in allk: return None
    return str(allk.get("root_permission")).strip().lower() == "true"

def cmd_rootfix(a):
    """rootfix TÊN | --all [--force] — bật root cho máy khách.
       MuMu chỉ cho ghi "Enable root" lúc máy TẮT và root có hiệu lực sau khi BẬT LẠI (trước 09/11 ghi lúc máy đang chạy → không ăn,
       nút "Root máy" báo chờ mãi). Máy tắt → bật sẵn root (lần bật sau có). Máy chạy chưa có su: --force (khách / admin bấm Root)
       → tắt → bật root → bật lại → kiểm su; không --force (vòng 5 phút của cloudphoned) → chỉ báo, KHÔNG tự khởi động lại máy khách
       (máy nào bật lại lúc nào cũng tự có root nhờ MUMU_PERF)."""
    v = vms(); ok = setn = wait = bad = 0
    for p in load()["phones"]:
        if not (a.all or p["name"] == a.name): continue
        i = IDX(p, v)
        if i is None: print(f"ROOT_NO {p['name']}: không thấy máy trong {EMU_NAME}", flush=True); bad += 1; continue
        on = _mumu_root_on(i)
        if not v[i]["running"]:
            if on is False:
                _MUMU_KEYS.pop(str(i), None); _mumu_set(str(i), {"root": 1})
                if _mumu_root_on(i): print(f"ROOT_SET {p['name']}: máy đang tắt — đã bật root, lần bật sau có root", flush=True); setn += 1
                else: print(f"ROOT_NO {p['name']}: MuMu chưa nhận bật root (máy đang tắt)", flush=True); bad += 1
            else: print(f"ROOT_SKIP {p['name']}: máy đang tắt", flush=True)
            continue
        if _has_su(p):
            print(f"ROOT_OK {p['name']}: đã root — tool gọi su là chạy bằng quyền root", flush=True); ok += 1; continue
        if on is not False and _ksu_pkg(p):
            print(f"ROOT_OK {p['name']}: đã root kiểu KernelSU — app cần root phải được bật Superuser (🔓 Root trong Công cụ, hoặc {KSU_HOWTO})", flush=True)
            ok += 1; continue
        if not a.force:
            if EMU != "mumu": memuc("setconfigex", "-i", i, "enable_su", 1, timeout=60)   # LDPlayer / MEmu: ghi sẵn, có hiệu lực khi bật lại
            print(f"ROOT_WAIT {p['name']}: chưa có root — bấm Root máy (máy khởi động lại ~1 phút) hoặc chờ lần bật lại sau", flush=True); wait += 1
            continue
        if _root_enable_restart(p): print(f"ROOT_OK {p['name']}: đã root xong — tool gọi su là chạy bằng quyền root", flush=True); ok += 1
        elif _ksu_pkg(p):
            print(f"ROOT_OK {p['name']}: đã root kiểu KernelSU — app cần root phải được bật Superuser (🔓 Root trong Công cụ, hoặc {KSU_HOWTO})", flush=True); ok += 1
        else: print(f"ROOT_NO {p['name']}: đã bật root + khởi động lại nhưng chưa thấy lệnh su", flush=True); bad += 1
    if a.all and not a.force:                                       # vòng 5 phút: máy bật root theo app mà daemon không chạy → cài lại
        for p in load()["phones"]:
            if p.get("root_on") and is_running(p["name"], p): _root_keep(p)
        for p in load()["phones"]:                                  # 22/11: máy có 🌐 proxy mà tiến trình proxy không chạy → bật lại
            if p.get("proxy") and is_running(p["name"], p): _proxy_keep(p)
    print(f"Root: {ok} máy có root · {setn} máy tắt đã bật sẵn · {wait} máy chờ bật lại · {bad} máy lỗi")

# ---------- ROOT THEO TỪNG APP (cpsu: lệnh su riêng + daemon, chỉ app trong danh sách mới lấy được root) ----------
# Máy chủ giữ 2 file: cpsu-x86_64 (daemon + install/uninstall/status — chạy root trong máy ảo, ngoài sandbox app) và
# cpsu-su-x86_64 (lệnh "su" KHÔNG libc — chạy bên trong app như Termux). Thiếu / sai md5 → tự tải từ GitHub (windows/…).
# Trong máy: /data/adb/cpsu/{cpsu, su, allow, log}; "cpsu install" chép su vào /debug_ramdisk/su (Termux tìm ở đó trước),
# adb là root thì gắn đè thêm lên /system/xbin/su, /system/bin/su. Tắt root = "cpsu uninstall". KHÔNG giấu root với app khác.
CPSU_DIR = os.path.join(HOME, "cpsu")
CPSU_FILES = {"cpsu": ("cpsu-x86_64", "e22c12e19f45f11ffeedc8d2d9bbefa8"), "su": ("cpsu-su-x86_64", "510c22af304ad95f6e733da4d60ce250")}
CPSU_RAW = (CONF.get("REPO_RAW") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main").rstrip("/") + "/windows/"
CPSU_API = (CONF.get("REPO_API") or "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents").rstrip("/") + "/windows/"
CPSU_DEV = "/data/adb/cpsu"
CPSU_BINDS = "/system/xbin/su,/system/bin/su"
_PKG_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")

def _fmd5(fp):
    try:
        with open(fp, "rb") as f: return hashlib.md5(f.read()).hexdigest()
    except OSError: return ""
def _cpsu_local():
    """Đường dẫn 2 file cpsu trên máy chủ (tải từ GitHub nếu thiếu / sai md5 — md5 ghim trong phonectl, file lạ không dùng)."""
    import urllib.request
    os.makedirs(CPSU_DIR, exist_ok=True); out = {}
    for key, (fn, want) in CPSU_FILES.items():
        fp = os.path.join(CPSU_DIR, fn)
        if _fmd5(fp) != want:
            data = None
            for url, hdr in ((CPSU_API + fn, {"Accept": "application/vnd.github.raw", "User-Agent": "BlueRoblox"}),
                             (CPSU_RAW + fn + f"?t={int(time.time())}", {"User-Agent": "BlueRoblox", "Cache-Control": "no-cache"})):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=90) as r: d = r.read()
                    if hashlib.md5(d).hexdigest() == want: data = d; break
                except Exception: pass
            if data is None: raise RuntimeError(f"máy chủ chưa có file {fn} đúng bản — tải windows/{fn} lên GitHub rồi thử lại")
            with open(fp + ".tmp", "wb") as f: f.write(data)
            os.replace(fp + ".tmp", fp)
        out[key] = fp
    return out

def _root_sh(p, script, timeout=120, files=()):
    """Chạy script bằng quyền ROOT trong máy. Script + file kèm (files = [(file trên máy chủ, tên)]) đẩy vào thư mục tạm RIÊNG
       của lần chạy này ($T, tránh 2 việc cùng lúc ghi đè nhau) → adb là root thì chạy thẳng, không thì qua su -c. Trả (kết quả, adb_root?)."""
    import secrets, tempfile
    s_ = serial(p)
    if (adb("-s", s_, "get-state", timeout=15).stdout or "").strip() != "device": adb_connect(p["port"])
    is_root = (adb("-s", s_, "shell", "id -u", timeout=15).stdout or "").strip() == "0"
    T = f"/data/local/tmp/cpsu_{secrets.token_hex(4)}"
    adb("-s", s_, "shell", f"mkdir -p {T}", timeout=15)
    fd, fp = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f: f.write(f"T={T}\n" + script.replace("\r", "") + "\n")
    try:
        adb("-s", s_, "push", fp, f"{T}/run.sh", timeout=60)
        for local, name in files: adb("-s", s_, "push", local, f"{T}/{name}", timeout=180)
    finally:
        try: os.remove(fp)
        except OSError: pass
    cmd = f"sh {T}/run.sh" if is_root else f"su -c 'sh {T}/run.sh'"
    r = adb("-s", s_, "shell", f"{cmd}; rm -rf {T}", timeout=timeout)
    return r, is_root

# ---------- ROOT KIỂU KernelSU (MuMu: máy Android 15 bật "Enable root" = KernelSU) ----------
# KernelSU GIẤU lệnh su với mọi app — kể cả adb shell của máy chủ — cho tới khi app được bật "Superuser" trong app KernelSU.
# → máy chủ không có su để cài cpsu, nút 🔓 Root cũ khởi động lại máy mà vẫn báo "chưa có lệnh su".
# Cách làm: công tắc 🔓 Root → máy chủ tự mở app KernelSU trong máy, bật / tắt "Superuser" cho ĐÚNG các app khách chọn (y như khách tự bấm),
# rồi đóng app KernelSU. KernelSU tự giữ quyền sau khi máy khởi động lại. KHÔNG cấp root cho adb shell, KHÔNG giấu root với app khác.
KSU_PKGS = ("me.weishu.kernelsu", "com.rifsxd.ksunext")
KSU_SU_WORDS = ("superuser", "siêu người dùng", "超级用户", "超級使用者", "суперпользователь", "superusuario", "pengguna super")
KSU_SKIP = set(KSU_PKGS) | {"shop.blueroblox.app"}
KSU_HOWTO = "mở app KernelSU › thẻ Superuser › bấm app cần root › bật công tắc Superuser, rồi tắt hẳn app đó và mở lại"

def _pkgs(p, third=False):
    """Gói app cài trong máy (third=True: chỉ app khách cài)."""
    try: o = ashell(p["name"], "pm list packages" + (" -3" if third else "") + " 2>/dev/null", port=p.get("port"), timeout=60).stdout or ""
    except Exception: return set()
    return {l.split(":", 1)[1].strip() for l in o.splitlines() if l.startswith("package:")}

def _ksu_pkg(p, have=None):
    """Gói app KernelSU của máy ('' = máy không dùng KernelSU)."""
    have = _pkgs(p) if have is None else have
    return next((k for k in KSU_PKGS if k in have), "")

def _root_flag(p):
    """MuMu "Enable root" của máy đang bật? None = không đọc được / không phải MuMu."""
    try:
        i = IDX(p, vms())
        return None if i is None else _mumu_root_on(i)
    except Exception: return None

def _ui_nodes(p):
    """Màn hình hiện tại của máy (uiautomator dump) → danh sách nút {i, par, text, desc, pkg, rid, click, check, checked, sel, b}."""
    import xml.etree.ElementTree as ET
    f = "/data/local/tmp/cb_ui.xml"
    for _ in range(3):
        try: o = ashell(p["name"], f"rm -f {f}; uiautomator dump {f} >/dev/null 2>&1; cat {f} 2>/dev/null; rm -f {f}", port=p.get("port"), timeout=45).stdout or ""
        except Exception: o = ""
        a, z = o.find("<hierarchy"), o.rfind("</hierarchy>")
        if a >= 0 and z > a:
            try: root = ET.fromstring(o[a:z + len("</hierarchy>")]); break
            except ET.ParseError: pass
        time.sleep(1)
    else: return []
    out = []
    def walk(el, par):
        for c in el:
            if c.tag != "node": continue
            m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", c.get("bounds") or "")
            b = tuple(int(x) for x in m.groups()) if m else (0, 0, 0, 0)
            n = {"i": len(out), "par": par, "text": (c.get("text") or "").strip(), "desc": (c.get("content-desc") or "").strip(),
                 "pkg": c.get("package") or "", "rid": c.get("resource-id") or "", "click": c.get("clickable") == "true",
                 "check": c.get("checkable") == "true", "checked": c.get("checked") == "true", "sel": c.get("selected") == "true", "b": b}
            out.append(n); walk(c, n["i"])
    walk(root, None)
    return out

def _ui_tap(p, n):
    x1, y1, x2, y2 = n["b"]
    ashell(p["name"], f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}", port=p.get("port"), timeout=30)

def _ui_clickable(ns, n):
    """Nút bấm được chứa n (n hoặc cha gần nhất bấm được)."""
    k = n
    while k is not None:
        if k["click"]: return k
        k = ns[k["par"]] if k["par"] is not None else None
    return n

def _ui_words(ns, n):
    """Chữ của n + mọi nút con (công tắc Compose: chữ nằm ở nút con)."""
    kids = {n["i"]}; out = [n["text"], n["desc"]]
    for k in ns[n["i"] + 1:]:
        if k["par"] in kids: kids.add(k["i"]); out += [k["text"], k["desc"]]
    return " ".join(x for x in out if x).lower()

def _is_su_word(s): return (s or "").strip().lower() in KSU_SU_WORDS
def _has_tok(n, word):
    """Nút có chữ đúng bằng word, kể cả khi Compose gộp chữ các nút con (vd "Termux, com.termux, ROOT")."""
    return any(word in re.split(r"[\s,;|·]+", x.strip()) for x in (n["text"], n["desc"]) if x)

def _ksu_switch(ns):
    """Công tắc "Superuser" trên trang 1 app của KernelSU (None = không phải trang đó)."""
    for n in ns:
        if n["check"] and any(w in _ui_words(ns, n) for w in KSU_SU_WORDS): return n
    for l in ns:                                   # công tắc không mang chữ: lấy công tắc nằm CÙNG HÀNG với chữ "Superuser"
        if l["check"] or not (_is_su_word(l["text"]) or _is_su_word(l["desc"])): continue
        cy = (l["b"][1] + l["b"][3]) // 2
        for n in ns:
            if n["check"] and n["b"][1] <= cy <= n["b"][3]: return n
    return None

def _ksu_dump_save(p, ns, why):
    """Lưu màn hình lúc KernelSU bấm không được (để admin gửi cho người sửa) — chỉ chữ trên màn hình, không có mật khẩu."""
    try:
        fp = os.path.join(HOME, f"ksu-{p['name']}.txt")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(f"{now().isoformat(timespec='seconds')} {why}\n")
            for n in ns:
                if n["text"] or n["desc"] or n["check"] or n["click"]:
                    f.write(f"{n['i']}<{n['par']} {n['pkg']} {n['rid']} t={n['text']!r} d={n['desc']!r} click={int(n['click'])} "
                            f"check={int(n['check'])}/{int(n['checked'])} sel={int(n['sel'])} {n['b']}\n")
        return fp
    except Exception: return ""

def _ksu_toggle(p, ksu, app, want):
    """Trong máy: mở app KernelSU → thẻ Superuser → app → bật (want=True) / tắt công tắc Superuser. Trả (ok, câu báo)."""
    sh = lambda c, t=40: ashell(p["name"], c, port=p.get("port"), timeout=t)
    launch = f"am force-stop {ksu}; monkey -p {ksu} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
    sh(launch); time.sleep(3)
    ns, scrolls, taps, last = [], 0, 0, ""
    for step in range(30):
        ns = _ui_nodes(p)
        if not ns: time.sleep(1); continue
        W = max(n["b"][2] for n in ns) or 720; H = max(n["b"][3] for n in ns) or 1280
        perm = [n for n in ns if "permissioncontroller" in n["pkg"] and re.search(r"(deny|allow)(_foreground_only)?_button$", n["rid"])]
        if perm:                                                    # hộp xin quyền của Android (vd. thông báo) → "Không cho phép"
            _ui_tap(p, next((n for n in perm if "deny" in n["rid"]), perm[0])); time.sleep(1.5); continue
        mine = sum(1 for n in ns if n["pkg"] == ksu)
        if mine * 2 < len(ns):                                      # app KernelSU chưa hiện / bị đóng → mở lại (lần 2: mở thẳng màn hình chính của app)
            if step in (6, 18): sh(launch)
            elif step == 12: sh(f"am start -n {ksu}/.ui.MainActivity >/dev/null 2>&1")
            time.sleep(1.5); continue
        sw = _ksu_switch(ns)
        if sw is not None:
            if not any(_has_tok(n, app) for n in ns):              # trang của app khác → quay lại danh sách
                sh("input keyevent 4"); time.sleep(1.5); continue
            if sw["checked"] == want:
                return True, ("đã bật" if want else "đã tắt")
            if taps >= 3: break
            _ui_tap(p, _ui_clickable(ns, sw)); taps += 1; time.sleep(1.5); continue
        row = next((n for n in ns if _has_tok(n, app) and n["b"][1] < H * 0.9), None)
        if row is not None:                                         # danh sách Superuser: dòng có tên gói của app
            _ui_tap(p, _ui_clickable(ns, row)); time.sleep(2); continue
        navs = [n for n in ns if _is_su_word(n["text"]) or _is_su_word(n["desc"])]
        bottom = [n for n in navs if n["b"][1] > H * 0.75]
        title = [n for n in navs if n["b"][3] < H * 0.15]
        in_list = any(_ui_clickable(ns, n)["sel"] or n["sel"] for n in bottom) or bool(title and bottom)
        if not in_list and bottom:                                  # thanh dưới: thẻ "Superuser"
            _ui_tap(p, _ui_clickable(ns, bottom[0])); time.sleep(2); continue
        if not navs: last = "không thấy thẻ Superuser (KernelSU chưa chạy?)"; break
        sig = "|".join(n["text"] for n in ns if n["text"])[:4000]
        if scrolls >= 12 or (scrolls and sig == last): last = f"không thấy app {app} trong danh sách Superuser"; break
        last = sig; scrolls += 1                                    # chưa thấy app → cuộn xuống
        sh(f"input swipe {W // 2} {int(H * 0.72)} {W // 2} {int(H * 0.38)} 300"); time.sleep(1.2)
    fp = _ksu_dump_save(p, ns, f"{app} want={want}: {last}")
    return False, (last if last and "|" not in last else "không bấm được trong app KernelSU") + (f" (đã lưu màn hình: {os.path.basename(fp)})" if fp else "")

def _ksu_note(p, apps):
    """Nhớ các app máy chủ đã bật trong KernelSU (để lần sau tắt đúng app) — đọc lại phones.json mới nhất rồi chỉ sửa máy này."""
    p["ksu_apps"] = sorted(set(apps))
    try:
        st = load(); r = rec(p["name"], st)
        if r is not None: r["ksu_apps"] = p["ksu_apps"]; save(st)
    except Exception: pass

def _ksu_sync(p, ksu, apps, quiet=False):
    """Đưa quyền Superuser trong KernelSU về đúng danh sách app (apps=[] → tắt hết app máy chủ từng bật). Trả (ok, câu báo)."""
    want = [a for a in dict.fromkeys(apps) if _PKG_RE.match(str(a)) and a not in KSU_SKIP]
    had = [a for a in (p.get("ksu_apps") or []) if _PKG_RE.match(str(a))]
    inst = _pkgs(p, third=True)
    todo = [(a, True) for a in want if a in inst] + [(a, False) for a in had if a not in want and a in inst]
    gone = [a for a in want if a not in inst]
    on_ok, off_ok, fail = set(), set(), []
    try:
        for a, w in todo:
            ok_, why = _ksu_toggle(p, ksu, a, w)
            if ok_: (on_ok if w else off_ok).add(a)
            else: fail.append(f"{a} ({why})")
    finally:
        try: ashell(p["name"], f"am force-stop {ksu}", port=p.get("port"), timeout=30)
        except Exception: pass
    _ksu_note(p, ((set(had) | on_ok) - off_ok) & inst)
    if fail:
        msg = "Chưa bật / tắt được root trong KernelSU cho: " + "; ".join(fail[:3]) + f". Làm tay: {KSU_HOWTO}."
        if not quiet: print(f"   🔓 {p['name']}: {msg}", flush=True)
        return False, msg
    if want:
        msg = (f"Đã BẬT root (KernelSU) cho {len(on_ok)} app: {', '.join(sorted(on_ok)[:5])}{'…' if len(on_ok) > 5 else ''}"
               " — tắt hẳn app đó rồi mở lại là dùng được lệnh su")
    else: msg = "Đã TẮT root — đã tắt quyền Superuser trong KernelSU của các app đã bật"
    if gone: msg += f" · app chưa cài trong máy: {', '.join(gone[:5])}"
    if not quiet: print(f"   🔓 {p['name']}: {msg}", flush=True)
    return True, msg

def cmd_ksuprobe(a):
    """ksuprobe TÊN — xem màn hình app KernelSU (mở app + thẻ Superuser, KHÔNG bật / tắt gì) để kiểm tra khi tự bấm không được."""
    st, p = _need(a.name)
    ksu = _ksu_pkg(p)
    print(f"KernelSU: {ksu or 'KHÔNG CÓ'} · MuMu Enable root: {_root_flag(p)} · su cho máy chủ: {_su_ready(p)}")
    if not ksu: return
    ashell(p["name"], f"am force-stop {ksu}; monkey -p {ksu} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1", port=p.get("port")); time.sleep(3)
    for lap in range(2):
        ns = _ui_nodes(p)
        print(f"--- màn hình {lap + 1}: {len(ns)} nút")
        for n in ns:
            if n["text"] or n["desc"] or n["check"]:
                print(f"  {n['pkg']} t={n['text']!r} d={n['desc']!r} click={int(n['click'])} check={int(n['check'])}/{int(n['checked'])} sel={int(n['sel'])} {n['b']}")
        nav = [n for n in ns if _is_su_word(n["text"]) or _is_su_word(n["desc"])]
        if lap == 0 and nav: _ui_tap(p, _ui_clickable(ns, nav[-1])); time.sleep(2)
    ashell(p["name"], f"am force-stop {ksu}", port=p.get("port"))

def _root_state(p):
    """Đọc trong máy: daemon chạy chưa, SELinux, app vừa xin root (bị từ chối), danh sách app khách cài.
       Máy chưa có root gốc (chưa có su) → vẫn đọc danh sách app bằng adb thường + su=False (bấm Lưu sẽ tự khởi động lại để bật root)."""
    if not _su_ready(p):
        o = (ashell(p["name"], "echo SELINUX=$(getenforce 2>/dev/null); pm list packages -3 2>/dev/null", port=p.get("port"), timeout=60).stdout or "")
        st = {"running": False, "selinux": "?", "asked": [], "installed": [], "su": False}
        for ln in o.splitlines():
            ln = ln.strip()
            if ln.startswith("SELINUX="): st["selinux"] = ln.split("=", 1)[1] or "?"
            elif ln.startswith("package:"):
                pk = ln.split(":", 1)[1].strip()
                if _PKG_RE.match(pk) and pk != "shop.blueroblox.app": st["installed"].append(pk)
        ksu = _ksu_pkg(p)
        st["installed"] = sorted(set(st["installed"]) - (KSU_SKIP if ksu else set()))
        if ksu and _root_flag(p) is not False:    # root KernelSU: quyền theo app do KernelSU giữ — máy chủ bật hộ trong app KernelSU khi bấm Lưu
            want = sorted({a for a in (p.get("root_apps") or []) if a not in KSU_SKIP})
            st.update(su=True, ksu=ksu, selinux="KernelSU",
                      running=bool(p.get("root_on")) and want == sorted(p.get("ksu_apps") or []))
        return st
    r, _ = _root_sh(p, f"D={CPSU_DEV}\n"
                       "if [ -x $D/cpsu ]; then $D/cpsu status --dir $D; else echo NOCPSU; fi\n"
                       "echo SELINUX=$(getenforce 2>/dev/null)\n"
                       "echo ---ASKED\n[ -f $D/log ] && tail -n 300 $D/log | grep ' DENY'\n"
                       "echo ---APPS\npm list packages -3 2>/dev/null\n", timeout=60)
    o = (r.stdout or "") + (r.stderr or ""); sec = ""; st = {"running": False, "selinux": "?", "asked": [], "installed": []}
    seen = set()
    for ln in o.splitlines():
        ln = ln.strip()
        if ln.startswith("---"): sec = ln[3:]; continue
        if not sec:
            if ln.startswith("RUNNING"): st["running"] = True
            elif ln.startswith("SELINUX="): st["selinux"] = ln.split("=", 1)[1] or "?"
        elif sec == "ASKED":
            m = re.match(r"^(\S+) uid=(\d+) pkgs=(\S+) DENY$", ln)
            if m: st["asked"].append((m.group(1), [x for x in m.group(3).split(",") if _PKG_RE.match(x)]))
        elif sec == "APPS" and ln.startswith("package:"):
            pk = ln.split(":", 1)[1].strip()
            if _PKG_RE.match(pk) and pk != "shop.blueroblox.app": st["installed"].append(pk)
    asked = []
    for t, pks in reversed(st["asked"]):                       # mới nhất trước, mỗi app 1 lần
        try: t = datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S%z").astimezone().isoformat(timespec="seconds")   # daemon ghi giờ UTC → giờ máy chủ
        except ValueError: pass
        for pk in pks:
            if pk not in seen: seen.add(pk); asked.append({"pkg": pk, "t": t})
    st["asked"] = asked[:30]; st["installed"] = sorted(set(st["installed"])); st["su"] = True
    return st

def _root_apply(p, quiet=False, restart=False):
    """Đưa máy về đúng cấu hình root đã lưu (p["root_on"], p["root_apps"]). Trả (ok, câu báo).
       restart=True (khách bấm Lưu trong 🔓 Root): máy chưa có root gốc → tự tắt → bật root → bật lại (~1 phút) rồi mới cài.
       restart=False (tự giữ root lúc máy vừa bật): chưa có root gốc thì chỉ báo — KHÔNG tự khởi động lại máy khách."""
    on, apps = bool(p.get("root_on")), [x for x in (p.get("root_apps") or []) if _PKG_RE.match(str(x))]
    ready = _su_ready(p)
    if not ready:                                 # máy chủ chưa có su: máy dùng KernelSU → bật / tắt quyền ngay trong app KernelSU, không khởi động lại
        ksu = _ksu_pkg(p)
        if ksu and (not on or _root_flag(p) is not False):
            if not restart: return True, "Máy dùng KernelSU — quyền root theo app do KernelSU giữ sau khi khởi động lại."
            return _ksu_sync(p, ksu, apps if on else [], quiet)
    if not on:
        r, _ = _root_sh(p, f"D={CPSU_DEV}\n[ -x $D/cpsu ] && $D/cpsu uninstall --dir $D\nrm -f $D/allow\necho ROOT_OFF_DONE\n", timeout=90)
        ok = "ROOT_OFF_DONE" in (r.stdout or "")
        return ok, ("Đã TẮT root — không app nào dùng được lệnh su." if ok else "Chưa tắt được root: " + ((r.stdout or "") + (r.stderr or "")).strip()[-160:])
    import tempfile
    files = _cpsu_local()
    if not ready:
        if not restart:
            return False, "Máy chưa bật root gốc — mở 🔓 Root rồi bấm Lưu (máy tự khởi động lại ~1 phút để bật root)."
        if not _root_enable_restart(p):
            ksu = _ksu_pkg(p)                     # bật root xong máy dùng KernelSU (MuMu Android 15) → bật quyền cho app ngay trong KernelSU
            if ksu: return _ksu_sync(p, ksu, apps, quiet)
            return False, "Đã khởi động lại máy để bật root nhưng máy vẫn chưa có lệnh su — báo admin kiểm tra máy này."
    r, is_root = _root_sh(p, f"md5sum {CPSU_DEV}/cpsu {CPSU_DEV}/su 2>/dev/null", timeout=30)
    have = r.stdout or ""
    push = [(fp, f"up_{key}") for key, fp in files.items() if CPSU_FILES[key][1] not in have]      # chỉ đẩy file khác bản
    fd, af = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f: f.write("".join(x + "\n" for x in apps))
    # adb chưa phải root (đi qua su của giả lập) → KHÔNG gắn đè su hệ thống (daemon tắt thì vẫn còn su gốc để quản lý máy)
    binds = f" --bind {CPSU_BINDS}" if is_root else ""
    sc = (f"D={CPSU_DEV}\nmkdir -p $D; chmod 700 $D\nNEW=0\n"
          "for f in cpsu su; do if [ -f $T/up_$f ]; then cp $T/up_$f $D/$f.new && chmod 755 $D/$f.new && mv -f $D/$f.new $D/$f && NEW=1; fi; done\n"
          "cp $T/allow $D/allow.new && chmod 600 $D/allow.new && mv -f $D/allow.new $D/allow\n"
          "[ \"$NEW\" = 1 ] && $D/cpsu uninstall --dir $D >/dev/null 2>&1\n"
          f"$D/cpsu install --dir $D{binds} --notify\n$D/cpsu status --dir $D\n")
    try: r, _ = _root_sh(p, sc, timeout=180, files=push + [(af, "allow")])
    finally:
        try: os.remove(af)
        except OSError: pass
    o = ((r.stdout or "") + (r.stderr or "")).strip()
    if "INSTALL_OK" not in o or "RUNNING" not in o:
        return False, "Chưa bật được root: " + (o.splitlines()[-1] if o else "máy không trả lời")[-200:]
    se = (re.search(r"selinux=(\w+)", o) or [None, "?"])[1]
    msg = f"Đã BẬT root cho {len(apps)} app" + (f": {', '.join(apps[:5])}{'…' if len(apps) > 5 else ''}" if apps else " (chưa chọn app nào — app xin root sẽ bị từ chối)")
    if se == "Enforcing": msg += " · ⚠ máy đang bật SELinux Enforcing — app có thể vẫn chưa dùng được su"
    if not quiet: print(f"   🔓 {p['name']}: {msg}", flush=True)
    return True, msg

def cmd_rootcfg(a):
    """rootcfg TÊN --get | --set --on/--off [--apps a,b,c] — công tắc root + danh sách app được dùng su (giao diện 🔓 Root)."""
    st, p = _need(a.name)
    if a.set:
        if a.on == a.off: print("ROOTCFG_FAIL chọn --on hoặc --off"); sys.exit(2)
        apps = []
        for x in (a.apps or "").split(","):
            x = x.strip()
            if not x: continue
            if not _PKG_RE.match(x): print(f"ROOTCFG_FAIL tên app không hợp lệ: {x[:60]}"); sys.exit(2)
            if x not in apps: apps.append(x)
        if len(apps) > 300: print("ROOTCFG_FAIL quá 300 app"); sys.exit(2)
        p["root_on"] = bool(a.on); p["root_apps"] = apps; save(st)        # lưu TRƯỚC: máy tắt / khởi động lại vẫn áp dụng đúng
        if not is_running(p["name"], p):
            print("ROOTCFG_OK Đã lưu — máy đang tắt, cấu hình root áp dụng khi máy bật."); return
        try: ok, msg = _root_apply(p, quiet=True, restart=True)
        except Exception as e: ok, msg = False, f"Chưa áp dụng được: {e}"
        print(("ROOTCFG_OK " if ok else "ROOTCFG_FAIL ") + msg)
        if not ok: sys.exit(1)
        return
    info = {"on": bool(p.get("root_on")), "apps": list(p.get("root_apps") or []), "running": False, "selinux": "?",
            "asked": [], "installed": [], "online": False, "su": None}
    if is_running(p["name"], p):
        try: info.update(_root_state(p)); info["online"] = True
        except Exception as e: info["error"] = str(e)[:200]
    if info.get("ksu"): info["apps"] = [x for x in info["apps"] if x not in KSU_SKIP]      # máy KernelSU: không hiện app KernelSU trong danh sách
    info["asked"] = [x for x in info["asked"] if x["pkg"] not in info["apps"]]
    print("ROOTCFG " + json.dumps(info, ensure_ascii=False))

def _root_keep(p, port=None):
    """Sau khi máy bật lại (tmpfs + gắn đè mất hết) / daemon chết: máy đang bật root theo app → cài lại. Không bật → bỏ qua."""
    p = rec(p["name"]) or p
    if not p.get("root_on"): return
    if port: p = dict(p, port=port)
    try:
        if not _su_ready(p) and _ksu_pkg(p): return           # KernelSU tự giữ quyền theo app sau khi máy khởi động lại
        r, _ = _root_sh(p, f"[ -x {CPSU_DEV}/cpsu ] && {CPSU_DEV}/cpsu status --dir {CPSU_DEV}", timeout=30)
        if "RUNNING" in (r.stdout or ""): return
        ok, msg = _root_apply(p, quiet=True)
        print(f"   🔓 {p['name']}: {'bật lại root theo app' if ok else msg}", flush=True)
    except Exception as e: print(f"   ⚠ {p['name']}: root theo app lỗi: {e}", flush=True)

# ---------- 🌐 PROXY RIÊNG TỪNG MÁY (22/11: khách tự điền IP:cổng:user:pass) ----------
# Trong máy: /data/adb/cbproxy/{cbproxy, conf.json, state.json, log} — cbproxy (Go, tĩnh, mã nguồn cbproxy/main.go) chạy ROOT:
# iptables (nat OUTPUT) bắt mọi kết nối TCP của app → proxy SOCKS5 / HTTP của khách. Proxy chết / sai → máy tự đi mạng thường,
# lành thì quay lại. UDP 443 (QUIC) chặn để app chuyển sang TCP. Trạng thái công khai /data/local/tmp/cbproxy.json (adb thường đọc,
# không có mật khẩu). Cấu hình (có mật khẩu) chỉ nằm ở phones.json của máy chủ + trong máy của chính khách — KHÔNG lên web.
CBPX_FILE = ("cbproxy-x86_64", "0cc3647ff0c54ae20ced5acf5907fbca")
CBPX_DEV = "/data/adb/cbproxy"
CBPX_PUB = "/data/local/tmp/cbproxy.json"
_PX_HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_PX_SAFE = re.compile(r"^[^\x00-\x1f\x7f]{0,255}$")

def _px_parse(text, kind="auto"):
    """Chuỗi khách dán → {kind, host, port, user, pass}. Nhận: IP:cổng · IP:cổng:user:pass · user:pass@IP:cổng · socks5://… · http://…
       Lỗi → ValueError (câu báo cho khách)."""
    s = str(text or "").strip()
    kind = str(kind or "auto").strip().lower()
    if kind not in ("auto", "socks5", "http"): raise ValueError("Kiểu proxy phải là Tự nhận / SOCKS5 / HTTP.")
    if not s: raise ValueError("Chưa nhập proxy.")
    if len(s) > 600 or any(ord(ch) < 32 for ch in s): raise ValueError("Proxy có ký tự lạ.")
    m = re.match(r"^(socks5h?|socks|http|https)://(.*)$", s, re.I)
    if m:
        sc = m.group(1).lower()
        if sc == "https": raise ValueError("Chưa hỗ trợ proxy HTTPS (mã hoá tới proxy) — dùng HTTP hoặc SOCKS5.")
        kind = "http" if sc == "http" else "socks5"
        s = m.group(2).rstrip("/")
    user = pw = ""
    if "@" in s:
        cred, _, hp = s.rpartition("@")
        user, _, pw = cred.partition(":")
        s = hp
        if s.startswith("["):                                       # [IPv6]:cổng
            h, _, rest = s[1:].partition("]"); port = rest.lstrip(":")
        else: h, _, port = s.rpartition(":")
    else:
        if s.startswith("["): raise ValueError("Chưa hỗ trợ proxy IPv6 — dùng địa chỉ IPv4 hoặc tên miền.")
        parts = s.split(":")
        if len(parts) < 2: raise ValueError("Thiếu cổng — nhập dạng IP:cổng hoặc IP:cổng:user:pass.")
        if len(parts) == 4 and not parts[1].strip().isdigit() and parts[3].strip().isdigit() and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", parts[2].strip()):
            parts = [parts[2], parts[3], parts[0], parts[1]]           # nơi bán ghi kiểu user:pass:IP:cổng → đảo lại
        h, port = parts[0], parts[1]
        if len(parts) >= 3: user = parts[2]; pw = ":".join(parts[3:])
    h = h.strip().strip("[]")
    try: port = int(str(port).strip())
    except ValueError: raise ValueError("Cổng proxy phải là số (1–65535).")
    if not 1 <= port <= 65535: raise ValueError("Cổng proxy phải từ 1 đến 65535.")
    import ipaddress
    try: ip = ipaddress.ip_address(h)
    except ValueError: ip = None
    if ip is not None:
        if ip.version == 6: raise ValueError("Chưa hỗ trợ proxy IPv6 — dùng địa chỉ IPv4 hoặc tên miền.")
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast: raise ValueError("Địa chỉ proxy không hợp lệ.")
    elif not _PX_HOST.match(h) or re.match(r"^[\d.]+$", h): raise ValueError("Địa chỉ proxy không hợp lệ (IP hoặc tên miền).")
    if not (_PX_SAFE.match(user) and _PX_SAFE.match(pw)): raise ValueError("User / mật khẩu proxy quá dài hoặc có ký tự lạ.")
    return {"kind": kind, "host": h, "port": port, "user": user, "pass": pw}

def _px_mask(px):
    if not px: return ""
    hp = f"[{px['host']}]" if ":" in px["host"] else px["host"]
    return f"{hp}:{px['port']}" + (f":{px['user']}:••••" if px.get("user") or px.get("pass") else "")

def _px_resolve(host):
    """IPv4 của proxy (máy chủ tự phân giải tên miền; trong máy Android không cần DNS)."""
    import socket, ipaddress
    try:
        ip = ipaddress.ip_address(host)
        return [str(ip)] if ip.version == 4 else []
    except ValueError: pass
    out = []
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM):
            if sa[0] not in out: out.append(sa[0])
    except OSError: pass
    return out[:4]

def _px_local():
    """File cbproxy trên máy chủ (tải từ GitHub nếu thiếu / sai md5 — md5 ghim ở đây, file lạ không dùng)."""
    import urllib.request
    os.makedirs(CPSU_DIR, exist_ok=True)
    fn, want = CBPX_FILE; fp = os.path.join(CPSU_DIR, fn)
    if _fmd5(fp) == want: return fp
    for url, hdr in ((CPSU_API + fn, {"Accept": "application/vnd.github.raw", "User-Agent": "BlueRoblox"}),
                     (CPSU_RAW + fn + f"?t={int(time.time())}", {"User-Agent": "BlueRoblox", "Cache-Control": "no-cache"})):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r: d = r.read()
            if hashlib.md5(d).hexdigest() == want:
                with open(fp + ".tmp", "wb") as f: f.write(d)
                os.replace(fp + ".tmp", fp); return fp
        except Exception: pass
    raise RuntimeError(f"máy chủ chưa có file {fn} đúng bản — tải windows/{fn} lên GitHub rồi thử lại")

def _px_root(p, script, files=(), timeout=120):
    """Chạy script bằng ROOT trong máy: adb là root / su (như Root theo app); máy KernelSU (Android 15, adb không có su) → "adb root"
       đúng 1 lần rồi "adb unroot" (như nới bộ nhớ). Script phải in PX_END ở cuối. Trả chữ in ra hoặc None (không có root)."""
    r, _ = _root_sh(p, script, timeout=timeout, files=files)
    o = (r.stdout or "") + (r.stderr or "")
    if "PX_END" in o: return o
    if not DG_ADBROOT: return None
    s_ = serial(p); port = p["port"]; rooted = False; o = ""
    def back_up():
        for _ in range(10):
            time.sleep(1.5)
            if _adb_fresh(port): return True
        return False
    try:
        rr = adb("-s", s_, "root", timeout=20); o0 = ((rr.stdout or "") + " " + (rr.stderr or "")).lower()
        if "as root" not in o0 or "cannot" in o0: return None
        rooted = True
        if back_up():
            r, _ = _root_sh(p, script, timeout=timeout, files=files); o = (r.stdout or "") + (r.stderr or "")
    except Exception: o = ""
    finally:
        if rooted:
            try: adb("-s", s_, "unroot", timeout=20); back_up()
            except Exception: pass
    return o if "PX_END" in o else None

def _px_state(p):
    """Trạng thái proxy trong máy (adb THƯỜNG, không cần root): {mode, ip, ms, err, kind, age…} · None = chưa từng bật / không đọc được."""
    try: o = ashell(p["name"], f"cat {CBPX_PUB} 2>/dev/null; echo; echo NOW=$(date +%s)", port=p.get("port"), timeout=20).stdout or ""
    except Exception: return None
    now = re.search(r"NOW=(\d+)", o); j = None
    for ln in o.splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try: j = json.loads(ln)
            except ValueError: j = None
    if not isinstance(j, dict): return None
    age = (int(now.group(1)) - int(j.get("beat") or 0)) if now and j.get("beat") else None
    j["age"] = age
    j["alive"] = bool(age is not None and age < 30 and j.get("mode") in ("proxy", "direct"))
    return {k: j.get(k) for k in ("mode", "kind", "ip", "ms", "err", "since", "ok_at", "fail_at", "via", "direct", "refused", "rules", "alive", "age", "ver")}

def _px_apply(p, quiet=False):
    """Đưa máy về đúng proxy đã lưu (p["proxy"]): có → đẩy cbproxy + cấu hình, bật; không có → tắt + gỡ iptables. Trả (ok, câu báo, trạng thái)."""
    px = p.get("proxy")
    if not px:
        o = _px_root(p, f"D={CBPX_DEV}\n[ -x $D/cbproxy ] && $D/cbproxy down -d $D\nrm -f $D/conf.json {CBPX_PUB}\necho PX_END\n", timeout=60)
        if o is None: return False, "Máy không cho máy chủ quyền root để tắt proxy — khởi động lại máy là proxy tự tắt.", None
        return True, "Đã TẮT proxy — máy đi mạng thường.", None
    ips = _px_resolve(px["host"])
    if not ips: return False, f"Không tìm được IP của proxy {px['host']} — kiểm tra lại địa chỉ.", None
    import tempfile
    binp = _px_local()
    conf = {"kind": px.get("kind") or "auto", "host": px["host"], "ips": ips, "port": int(px["port"]), "user": px.get("user") or "", "pass": px.get("pass") or ""}
    fd, cf = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(conf, f)
    # 1 lần chạy root duy nhất (máy KernelSU: mỗi lần = adbd khởi động lại 2 lần) — file cbproxy luôn đẩy kèm (2,8MB qua adb nội bộ, < 1 giây),
    # trong máy chỉ thay khi md5 khác bản ghim
    sc = (f"D={CBPX_DEV}\nmkdir -p $D; chmod 700 $D\n"
          f"if [ \"$(md5sum $D/cbproxy 2>/dev/null | cut -d' ' -f1)\" != \"{CBPX_FILE[1]}\" ]; then "
          "cp $T/up_cbproxy $D/cbproxy.new && chmod 755 $D/cbproxy.new && mv -f $D/cbproxy.new $D/cbproxy; fi\n"
          "cp $T/conf.json $D/conf.json && chmod 600 $D/conf.json\n"
          "$D/cbproxy up -c $D/conf.json -d $D\necho PX_END\n")
    try: o = _px_root(p, sc, files=[(binp, "up_cbproxy"), (cf, "conf.json")], timeout=120)
    finally:
        try: os.remove(cf)
        except OSError: pass
    if o is None: return False, "Máy chưa có quyền root cho máy chủ (cần để bật proxy) — bấm 🔓 Root máy rồi thử lại.", None
    j = None
    for ln in o.splitlines():
        ln = ln.strip()
        if ln.startswith("{") and '"ok"' in ln:
            try: j = json.loads(ln)
            except ValueError: pass
    if not isinstance(j, dict): return False, "Chưa bật được proxy: " + (o.replace("PX_END", "").strip().splitlines() or ["máy không trả lời"])[-1][:200], None
    stt = j.get("state") or {}
    if not j.get("ok"): return False, "Chưa bật được proxy: " + str(j.get("err") or stt.get("err") or "lỗi lạ")[:200], stt
    if stt.get("mode") == "proxy":
        msg = f"Đã BẬT proxy — IP ra: {stt.get('ip') or '?'} · {int(stt.get('ms') or 0)} ms"
    else:
        msg = "Đã lưu proxy nhưng proxy CHƯA dùng được (" + str(stt.get("err") or "không nối được")[:160] + ") — máy đang đi mạng thường, tự thử lại mỗi 15 giây."
    if not quiet: print(f"   🌐 {p['name']}: {msg}", flush=True)
    return True, msg, stt

def _proxy_keep(p, port=None):
    """Máy vừa bật lại (iptables + tiến trình trong máy mất hết) / tiến trình proxy chết → bật lại. Máy không đặt proxy → bỏ qua."""
    p = rec(p["name"]) or p
    if not p.get("proxy"): return
    if port: p = dict(p, port=port)
    try:
        s = _px_state(p)
        if s and s.get("alive"): return
        if s and s.get("mode") == "crashed" and (s.get("age") or 0) < 1800: return       # vừa hỏng (VD máy không có iptables) → 30 phút mới thử lại
        ok, msg, _ = _px_apply(p, quiet=True)
        print(f"   🌐 {p['name']}: {'bật lại proxy · ' + msg if ok else msg}", flush=True)
    except Exception as e: print(f"   ⚠ {p['name']}: proxy lỗi: {e}", flush=True)

def cmd_proxy(a):
    """proxy TÊN --get | --set (--url "IP:cổng:user:pass" | --url-stdin) [--kind auto|socks5|http] | --off | --again — proxy riêng của máy (🌐 Proxy).
       cpapi đưa proxy qua stdin (--url-stdin): mật khẩu proxy không nằm trên dòng lệnh."""
    st, p = _need(a.name)
    if a.set or a.off or a.again:
        if a.set:
            url = sys.stdin.buffer.readline().decode("utf-8", "replace").strip() if a.url_stdin else a.url
            try: px = _px_parse(url, a.kind)
            except ValueError as e: print(f"PROXY_FAIL {e}"); sys.exit(2)
            p["proxy"] = px
        elif a.off:
            had = bool(p.pop("proxy", None))
        elif not p.get("proxy"): print("PROXY_FAIL Máy chưa đặt proxy."); sys.exit(2)
        if not a.again: save(st)                                   # lưu TRƯỚC: máy tắt / khởi động lại vẫn áp dụng đúng
        if not is_running(p["name"], p):
            print("PROXY_OK " + ("Đã tắt proxy." if a.off else "Đã lưu — máy đang tắt, proxy tự bật khi máy bật.")); return
        if a.off and not had:
            s = None
            try: s = _px_state(p)
            except Exception: pass
            if not s or (s.get("mode") in ("off", "crashed") or not s.get("alive")):
                print("PROXY_OK Máy không dùng proxy — đang đi mạng thường."); return
        try: ok, msg, _ = _px_apply(p, quiet=True)
        except Exception as e: ok, msg = False, f"Chưa áp dụng được: {e}"
        print(("PROXY_OK " if ok else "PROXY_FAIL ") + msg)
        if not ok: sys.exit(1)
        return
    px = p.get("proxy") or None
    info = {"set": bool(px), "kind": (px or {}).get("kind") or "auto", "show": _px_mask(px), "host": (px or {}).get("host") or "",
            "port": (px or {}).get("port") or 0, "user": (px or {}).get("user") or "", "has_pass": bool((px or {}).get("pass")),
            "online": False, "state": None}
    if is_running(p["name"], p):
        info["online"] = True
        try: info["state"] = _px_state(p)
        except Exception as e: info["error"] = str(e)[:200]
    print("PROXY " + json.dumps(info, ensure_ascii=False))

def _proxy_later(name):
    """Lệnh nền (tách khỏi lệnh đang chạy): chờ Android của máy vừa bật lại lên → bật lại proxy (proxykeep TÊN --wait)."""
    for fl in (0x00000008 | 0x00000200 | NOWIN, 0) if os.name == "nt" else (0,):
        try:
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "proxykeep", name, "--wait"], cwd=HOME, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=fl, close_fds=True)
            return True
        except OSError: continue
    return False

def cmd_proxykeep(a):
    """proxykeep [TÊN | --all] [--wait] — bật lại proxy cho máy đang chạy mà tiến trình proxy chưa chạy (vòng canh của cloudphoned).
       --wait (1 máy, sau khi khởi động lại): chờ Android lên (tối đa BOOT_WAIT) rồi mới kiểm."""
    if a.wait and a.name:
        p = rec(a.name)
        if not p or not p.get("proxy"): return
        t0 = time.time()
        while time.time() - t0 < BOOT_WAIT:
            if is_running(p["name"], p) and android_ready(p["port"], 20): break
            time.sleep(5)
        else: return
        time.sleep(5)                                            # Android vừa lên: chờ dịch vụ mạng ổn định
    v = vms(); n = 0
    for p in load()["phones"]:
        if not p.get("proxy") or not (a.all or p["name"] == a.name): continue
        if not is_running(p["name"], p, v): continue
        _proxy_keep(p); n += 1
    print(f"PROXYKEEP {n} máy có proxy")

def cmd_capacity(a):
    st = load(); tot, av = mem()
    print(f"Windows: RAM {tot:.1f} GB (còn trống {av:.1f} GB, chừa {RESERVE:g} GB) · CPU {os.cpu_count()} luồng · {EMU_NAME}: {MEMU or 'KHÔNG THẤY'}"
          f" · 1 máy tối đa {MAX_RAM:g}GB · {MAX_CPU} nhân")
    nz = sum(1 for p in st["phones"] if _asleep(p))
    print(f"Đã cấp:  RAM {sum(float(p['ram']) for p in st['phones']):.1f} GB  ({len(st['phones'])} máy)"
          + (f" · {nz} máy đang ngủ (chừa {_sleep_ram(st):.1f} GB = {_sleep_factor():.0%} RAM cấp, để bật lại)" if nz else ""))

def cmd_list(a):
    st = load(); v = vms()
    if not st["phones"]: print("(chưa có máy nào)"); return
    for p in st["phones"]:
        i = IDX(p, v); on = is_running(p['name'], p, v)       # chữ cuối dòng "chạy" = đang chạy (run.py đọc) — máy ngủ ghi "ngủ"
        print(f"{p['name']:<16} #{'?' if i is None else i:<3} cổng {p['port']:<6} {p['ram']}G/{p['cpu']}  hết hạn {fmt(parse_dt(p['expires']))}  {'chạy' if on else 'ngủ' if _asleep(p) else 'tắt'}")

# ---------- KHỞI ĐỘNG LẠI CẢ MÁY CHỦ (admin bấm trên web → cpapi → rebootserver) ----------
RB_F = os.path.join(HOME, "redroid", "reboot_hold.json")      # máy khách đang GIỮ (hold) để khởi động lại máy chủ
def _uptime():
    """Số giây từ lúc Windows bật (GetTickCount64 — phải đặt kiểu trả về 64 bit, mặc định ctypes cắt còn 32 bit → sai sau 24 ngày)."""
    try:
        f = ctypes.windll.kernel32.GetTickCount64; f.restype = ctypes.c_uint64; return f() / 1000.0
    except Exception:
        try: return float(open("/proc/uptime").read().split()[0])
        except Exception: return 0.0
def _boot_time(): return time.time() - _uptime()
def _autologon():
    """Windows tự đăng nhập (bảng CloudBlue → 🔑) — không có thì khởi động lại sẽ dừng ở màn hình mật khẩu."""
    if os.name != "nt": return False
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon")
        try: v, _ = winreg.QueryValueEx(k, "AutoAdminLogon")
        finally: winreg.CloseKey(k)
        return str(v).strip() == "1"
    except Exception: return False
def _autostart():
    """Bảng CloudBlue tự mở khi đăng nhập: tác vụ BlueRoblox (nút 🔑) hoặc lối tắt Startup (setup.ps1)."""
    if os.name != "nt": return False
    lnk = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk")
    return os.path.isfile(lnk) or run(["schtasks", "/query", "/tn", "BlueRoblox"], 30).returncode == 0
def _reboot_release(force=False):
    """Trả các máy khách đã giữ để khởi động lại máy chủ: khi Windows ĐÃ khởi động lại, hoặc quá 15 phút vẫn chưa khởi động lại
       (lệnh bị huỷ), hoặc force. Gọi đầu bootall (bảng chạy mỗi phút + lúc Windows vừa lên) → máy bật lại."""
    try: d = json.load(open(RB_F, encoding="utf-8"))
    except Exception: return []
    up = _uptime()
    rebooted = (up > 0 and up + 30 < float(d.get("up") or 0)) or _boot_time() > float(d.get("boot") or 0) + 120
    if not (force or rebooted or time.time() - float(d.get("t") or 0) > 900): return []
    names = [n for n in (d.get("names") or []) if isinstance(n, str)]
    for nm in names: set_hold(nm, False)
    try: os.remove(RB_F)
    except OSError: pass
    if names: print(f"↺ Trả {len(names)} máy khách đã giữ lúc khởi động lại máy chủ → bật lại", flush=True)
    return names
def cmd_serverinfo(a):
    st = load(); v = vms()
    print("SERVERINFO " + json.dumps({"node": CONF.get("NODE_ID", ""), "emu": EMU_NAME, "autologon": _autologon(), "autostart": _autostart(),
          "uptime_h": round(_uptime() / 3600, 1), "running": sum(1 for x in v.values() if x["running"]), "phones": len(st["phones"]),
          "sleeping": sum(1 for p in st["phones"] if _asleep(p)), "pending": os.path.isfile(RB_F),
          "boot_par": _bootall_par(), "boot_gap": BOOT_GAP, "boot_rescue": BOOT_RESCUE_S, "ver": PCTL_SUB,
          "idle_h": IDLE_H if IDLE_H > 0 and IDLE_MIN > 0 else 0, "idle_min": IDLE_MIN}, ensure_ascii=False))
def _soft_off_all(wait=90, quiet=False):
    """17/11f — TẮT ÊM mọi máy đang chạy trước khi khởi động lại / tắt máy chủ (KHÔNG mất dữ liệu): từng máy `sync` (ghi hết dữ liệu đang
       chờ xuống đĩa) rồi cho ANDROID tự tắt (reboot -p: đóng app, gỡ ổ dữ liệu sạch rồi mới tắt) — mọi máy làm CÙNG LÚC. Trước: lệnh tắt
       của giả lập = rút điện ngang → file đang ghi dở có thể hỏng (sổ khoá Android 16/11). Quá `wait` giây còn máy chưa tắt → tắt bằng
       giả lập như cũ. Trả (số máy đang chạy lúc đầu, số máy còn chạy sau cùng)."""
    import threading
    v = vms(); st = load()
    run_ = [(i, x) for i, x in sorted(v.items()) if x.get("running")]
    if not run_: return 0, 0
    byname = {p["name"]: p for p in st["phones"]}
    def off(i, x):
        try:
            p = byname.get(x["name"]) or {"name": x["name"], "port": port_of(i)}
            try: adb("-s", serial(p), "shell", "sync", timeout=8)
            except Exception: pass
            _android_off(p)
        except Exception: pass
    t0 = time.time(); left = len(run_)
    for i, x in run_: threading.Thread(target=off, args=(i, x), daemon=True).start()     # mọi máy cùng lúc; không chờ từng luồng (máy treo không giữ chân)
    time.sleep(3)
    while time.time() - t0 < wait:
        left = sum(1 for x in vms().values() if x["running"])
        if not left: break
        time.sleep(3)
    if left:
        if not quiet: print(f"   ({left} máy chưa tự tắt sau {int(wait)} giây → tắt bằng {EMU_NAME})", flush=True)
        memuc("stopall", timeout=150); t0 = time.time()
        while time.time() - t0 < 60:
            left = sum(1 for x in vms().values() if x["running"])
            if not left: break
            time.sleep(3)
    return len(run_), left
def _reboot_hold():
    """GIỮ (hold) mọi máy chưa bị giữ + ghi reboot_hold.json → bảng / cloudphoned không tự bật lại giữa lúc tắt. Windows lên lại (hoặc quá
       15 phút không khởi động lại) → bootall trả hết (_reboot_release). Trả (tên các máy vừa giữ, số máy đang chạy)."""
    st = load(); v = vms()
    names = [p["name"] for p in st["phones"] if not p.get("hold")]       # giữ MỌI máy chưa bị giữ → bảng (bootall mỗi phút) không bật lại giữa chừng
    nrun = sum(1 for p in st["phones"] if not p.get("hold") and is_running(p["name"], p, v))
    os.makedirs(os.path.dirname(RB_F), exist_ok=True)
    old = []
    try: old = [n for n in (json.load(open(RB_F, encoding="utf-8")).get("names") or []) if isinstance(n, str)]    # lần giữ trước chưa trả → giữ tiếp tên cũ
    except Exception: pass
    json.dump({"names": sorted(set(names) | set(old)), "boot": _boot_time(), "up": _uptime(), "t": time.time()}, open(RB_F, "w", encoding="utf-8"))
    for nm in names: set_hold(nm, True)
    return names, nrun
def cmd_tatem(a):
    """tatem (17/11f): TẮT ÊM mọi máy khách (Android tự ghi dữ liệu rồi tắt) và GIỮ không cho tự bật lại — dùng ngay TRƯỚC khi tự khởi động
       lại / tắt Windows bằng tay, bảo trì máy chủ. Windows lên lại → máy tự bật hết. Không khởi động lại trong 15 phút → máy cũng tự bật lại."""
    names, nrun = _reboot_hold()
    print(f"Tắt êm {nrun} máy khách đang chạy (Android ghi xong dữ liệu rồi mới tắt)…", flush=True)
    n0, left = _soft_off_all(wait=a.wait)
    print(("✓ Đã tắt êm hết " + str(n0) + " máy" if not left else f"⚠ còn {left} máy chưa tắt hẳn") + " — giờ khởi động lại / tắt Windows được, dữ liệu khách an toàn."
          " Windows lên lại → máy tự bật. KHÔNG khởi động lại trong 15 phút → máy cũng tự bật lại.", flush=True)
    print(f"TATEM {json.dumps({'held': len(names), 'running': nrun, 'left': left})}")
def cmd_rebootserver(a):
    """Admin ép KHỞI ĐỘNG LẠI CẢ MÁY CHỦ: giữ các máy khách đang chạy (bảng không tự bật lại giữa chừng) → tắt êm hết → shutdown /r /f.
       Windows lên lại: tự đăng nhập → bảng --auto → bootall trả các máy đã giữ rồi bật lại hết (app, dữ liệu giữ nguyên)."""
    if os.name != "nt": print("❌ Chỉ dùng cho máy chủ Windows."); sys.exit(2)
    if not _autologon() and not a.anyway:
        print("NO_AUTOLOGON Windows chưa bật tự đăng nhập (bảng CloudBlue → 🔑 Tự đăng nhập + tự chạy) — khởi động lại sẽ dừng ở màn hình mật khẩu, máy khách tắt tới khi có người đăng nhập.")
        sys.exit(7)
    names, nrun = _reboot_hold()
    print(f"1/3 Tắt êm {nrun} máy khách đang chạy — Android ghi xong dữ liệu rồi mới tắt (bảng không tự bật lại trong lúc này)…", flush=True)
    n0, left = _soft_off_all(wait=a.wait)
    print("   ✓ đã tắt hết" if not left else f"   ⚠ còn {left} máy chưa tắt hẳn — Windows sẽ tắt nốt", flush=True)
    print(f"2/3 Khởi động lại Windows sau {a.delay} giây…", flush=True)
    r = run(["shutdown", "/r", "/f", "/t", str(a.delay), "/c", "CloudBlue: admin khoi dong lai may chu"], 60)
    if r.returncode not in (0, None):
        _reboot_release(force=True)
        print("❌ Windows không cho khởi động lại: " + ((r.stdout or "") + (r.stderr or "")).strip()[-200:] + " — đã trả lại máy khách (bảng tự bật lại trong ~1 phút).")
        sys.exit(8)
    print(f"REBOOT_OK Windows khởi động lại sau {a.delay} giây · {nrun} máy khách tự bật lại khi Windows lên (khoảng 3–8 phút).")

BOOTALL_F = os.path.join(HOME, "redroid", "bootall.json")     # đợt bật hàng loạt đang chạy: phát hình đọc để báo khách "máy chủ vừa khởi động lại"
BOOT1_MAX = 1800                                               # 1 lệnh con chạy quá 30 phút → thôi theo dõi (tính là lỗi)
def _bootall_note(total, left, t0):
    try:
        tmp = BOOTALL_F + ".%d.tmp" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f: json.dump({"t": time.time(), "t0": t0, "pid": os.getpid(), "total": total, "left": left}, f)
        os.replace(tmp, BOOTALL_F)
    except OSError: pass
def _boot1_spawn(name):
    return subprocess.Popen([sys.executable, os.path.abspath(__file__), "boot1", name], cwd=HOME, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=NOWIN if os.name == "nt" else 0, text=True, encoding="utf-8", errors="replace")
def cmd_bootall(a):
    """Sau khi Windows khởi động lại (và mỗi phút, bảng gọi --quiet): bật mọi máy khách CÒN HẠN đang tắt ngoài ý muốn.
       17/11f: bật SONG SONG theo suất (BOOTALL_PARALLEL), máy có khách vừa dùng lên trước, khách mở máy nào máy đó được chen lên; mỗi lần
       chỉ 1 đợt chạy (đợt thứ 2 thoát ngay)."""
    try: lk = _Lock("bootall", wait=1); lk.__enter__()
    except RuntimeError:
        if not a.quiet: print("BOOTALL: đang có 1 đợt bật máy khác chạy — không chạy chồng (xem tiếp ở đợt đó).")
        return
    try: bad = _bootall(a, lk)
    finally:
        lk.__exit__()
        try:
            if json.load(open(BOOTALL_F, encoding="utf-8")).get("pid") == os.getpid(): os.remove(BOOTALL_F)
        except Exception: pass
    if bad: sys.exit(6)
def _bootall(a, lk=None):
    _reboot_release()                                        # máy giữ lúc admin khởi động lại máy chủ → trả lại (khi Windows đã lên lại)
    st = load(); v = vms(); todo = []
    only = {x for x in re.split(r"[\s,;]+", str(getattr(a, "only", "") or "")) if x}
    for p in st["phones"]:
        if only and p["name"] not in only: continue
        if parse_dt(p["expires"]) < now() or p.get("hold"): continue
        if IDX(p, v) is None: print(f"⚠ {p['name']}: không còn trong MEmu (bấm ♻ Làm mới máy khách)"); continue
        if is_running(p["name"], p, v):
            if not a.quiet: adb_connect(p["port"]); print(f"✓ {p['name']}: đang chạy")
            continue
        todo.append(p)
    if a.quiet and not todo: return 0
    try: seen = _viewers()[1]
    except Exception: seen = {}
    todo.sort(key=lambda p: -float(seen.get(str(p.get("port")), 0) or 0))     # máy có khách vừa dùng gần đây nhất lên trước
    par = _bootall_par(); t0 = time.time(); total = len(todo)
    print(f"Cần bật {total} máy khách — bật {par} máy cùng lúc, máy có khách vừa dùng lên trước, khách mở máy nào máy đó được chen lên…", flush=True)
    pend = list(todo); live = {}; bad = ok_n = skip = 0; last = None; went = set()
    def gone(nm):
        """Lệnh con của máy nm đã tới lượt (có suất / máy đang chạy sẵn / đã thoát)? Chưa → chưa gọi lệnh con kế: mỗi lúc chỉ 1 lệnh con
           đứng chờ suất nên máy được bật ĐÚNG thứ tự đã xếp."""
        if nm in went or nm not in live: return True
        if nm in _bs_load()["slots"] or os.path.isfile(_boot1_f(nm)): went.add(nm); return True
        return False
    while pend or live:
        while pend and len(live) < par + 1 and (last is None or gone(last)):
            p = pend.pop(0); last = p["name"]
            print(f"▶ Bật {p['name']}…", flush=True)
            try: os.remove(_boot1_f(last))
            except OSError: pass
            try: live[p["name"]] = (_boot1_spawn(p["name"]), time.time())
            except OSError as e: print(f"✗ {p['name']}: không chạy được lệnh bật ({e})", flush=True); bad += 1
        _bootall_note(total, [p["name"] for p in pend] + list(live), t0)
        if lk is not None:
            try: os.utime(lk.p, None)                        # đợt bật dài hơn 16 phút → khoá không bị coi là "khoá cũ"
            except OSError: pass
        time.sleep(1)
        for nm, (proc, ts) in list(live.items()):
            rc = proc.poll()
            if rc is None:
                if time.time() - ts > BOOT1_MAX:
                    try: proc.kill()                         # chỉ tắt đúng lệnh con (không /T — không đụng máy ảo)
                    except Exception: pass
                    print(f"✗ {nm}: lệnh bật chạy quá {BOOT1_MAX // 60} phút — thôi chờ (chống kẹt sẽ xử lý tiếp)", flush=True); bad += 1; live.pop(nm)
                    try: os.remove(_boot1_f(nm))
                    except OSError: pass
                continue
            try: out = (proc.communicate(timeout=10)[0] or "")
            except Exception: out = ""
            live.pop(nm)
            try: os.remove(_boot1_f(nm))
            except OSError: pass
            lines = [x.strip() for x in out.splitlines() if x.strip()]
            for x in lines:
                if x.startswith(("   (", "(", "📄", "🔑")): print("   " + x.lstrip(), flush=True)     # 17/11g: + dòng tự sửa file Android hỏng
            last = lines[-1] if lines else ""
            if rc == 0: ok_n += 1; print(f"✅ {nm}: sẵn sàng" + (f" ({last.split('sẵn sàng', 1)[-1].strip()})" if "sẵn sàng" in last else ""), flush=True)
            elif rc in (4, 7): skip += 1; print(f"· {nm}: " + ("khách vừa mở — lệnh của khách đang bật máy này" if rc == 7 else "đang tạm dừng — không bật"), flush=True)
            else: bad += 1; print(f"✗ {nm}: " + (last.replace("WAKE_FAIL ", "") or f"lệnh bật lỗi (mã {rc})"), flush=True)
    print(f"BOOTALL xong: {ok_n}/{total} máy bật thành công" + (f", {skip} máy khách tự mở" if skip else "") + ("" if not bad else f", {bad} máy lỗi")
          + f" · {int(time.time() - t0)} giây", flush=True)
    return bad

# ---------- CHỐNG KẸT: máy chạy mà Android không lên (kẹt 99%, màn đen, adb offline) ----------
HEAL_F = os.path.join(HOME, "redroid", "heal.json")
STUCK_MIN = 10         # chạy quá 10 phút mà Android chưa lên → coi là kẹt (14/11: 6 phút — máy chủ quá tải khởi động chậm bị coi là kẹt)
# Kẹt sau 2 lần khởi động lại → XOÁ máy + tạo lại máy mới (MẤT dữ liệu khách). MEmu mặc định TẮT (lỗi chung của giả lập —
# VD màn đen do cấu hình — sẽ xoá hàng loạt máy khách); bật lại: HEAL_DELETE=1 trong cloudphone.conf.
HEAL_DELETE = (CONF.get("HEAL_DELETE") or "0").strip() == "1"     # 14/11: mặc định KHÔNG tự xoá (win5: máy quá tải bị xoá → web còn, máy chủ mất)
def _hl():
    try: return json.load(open(HEAL_F, encoding="utf-8"))
    except Exception: return {}
def _hs(d):
    os.makedirs(os.path.dirname(HEAL_F), exist_ok=True); json.dump(d, open(HEAL_F, "w", encoding="utf-8"))
HEAL_SLOT_S = 120     # 16/11e: chống kẹt chờ lượt bật tối đa chừng này giây (máy vẫn chạy trong lúc chờ), quá thì để lần sau
def _recent_restart(nm, win=360):
    """Máy vừa được khởi động lại trong win giây (dấu restart_<tên>.json) → có thể đang lên chậm (máy chủ bận)."""
    try:
        d = json.load(open(os.path.join(HOME, "redroid", f"restart_{nm}.json"), encoding="utf-8"))
        return 0 <= time.time() - float(d.get("t") or 0) < win
    except Exception: return False
# ---------- 17/11h: TỰ TẮT TIẾNG WINDOWS CỦA MÁY CHỦ ----------
# Máy khách (giả lập) phát tiếng game ra loa Windows của máy chủ → máy chủ kêu loạn. Khách KHÔNG nghe tiếng từ máy chủ (phát hình không
# gửi tiếng) nên tắt tiếng Windows không ảnh hưởng khách. CHỈ bật nút "tắt tiếng" (mute) của loa mặc định Windows — không đổi mức âm
# lượng, không đụng cài đặt giả lập / máy khách. Chống kẹt (bảng gọi ~2 phút / lần) kiểm 10 phút 1 lần: đang có tiếng thì tắt.
# Thôi tự tắt: HOST_MUTE=0 trong cloudphone.conf (python phonectl.py setconf HOST_MUTE=0). Bật tiếng lại: python phonectl.py tattieng --bat
HOST_MUTE = str(CONF.get("HOST_MUTE", "1")).strip() != "0"
HOST_MUTE_F = os.path.join(HOME, "redroid", "hostmute.json")
HOST_MUTE_EVERY = 600
_HM_CS = ('using System; using System.Runtime.InteropServices; '
          '[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioEndpointVolume { '
          'int f(); int g(); int h(); int i(); int SetMasterVolumeLevelScalar(float fLevel, ref Guid ctx); int j(); '
          'int GetMasterVolumeLevelScalar(out float pfLevel); int k(); int l(); int m(); int n(); '
          '[PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, ref Guid ctx); [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool pbMute); } '
          '[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IMMDevice { '
          '[PreserveSig] int Activate(ref Guid id, int clsCtx, IntPtr activationParams, out IAudioEndpointVolume aev); } '
          '[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IMMDeviceEnumerator { '
          'int f(); [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); } '
          '[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject { } '
          'public class CbAudio { static IAudioEndpointVolume Vol() { var e = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator; IMMDevice dev = null; '
          'Marshal.ThrowExceptionForHR(e.GetDefaultAudioEndpoint(0, 1, out dev)); IAudioEndpointVolume v = null; var id = typeof(IAudioEndpointVolume).GUID; '
          'Marshal.ThrowExceptionForHR(dev.Activate(ref id, 23, IntPtr.Zero, out v)); return v; } '
          'public static bool Mute { get { bool m; Marshal.ThrowExceptionForHR(Vol().GetMute(out m)); return m; } '
          'set { var g = Guid.Empty; Marshal.ThrowExceptionForHR(Vol().SetMute(value, ref g)); } } }')
def _hm_ps(unmute=False):
    """Lệnh PowerShell: nạp lớp CbAudio (Core Audio của Windows) → tắt / bật nút mute của loa mặc định. In đúng 1 dấu HM_…"""
    act = "[CbAudio]::Mute = $false; 'HM_UNMUTED'" if unmute else "if ([CbAudio]::Mute) { 'HM_ALREADY' } else { [CbAudio]::Mute = $true; 'HM_DONE' }"
    return ("$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; try { Add-Type -TypeDefinition '" + _HM_CS + "'; " + act
            + " } catch { 'HM_ERR ' + $_.Exception.Message }")
def _hm_run(unmute=False):
    """→ "done" (vừa tắt) · "already" (đang tắt sẵn) · "unmuted" · "nodev" (máy không có loa / thiết bị âm thanh) · "skip" (không phải Windows) · "err: …"."""
    out = os.environ.get("CB_TEST_HOSTMUTE")
    if out is None:
        if os.name != "nt": return "skip"
        import base64
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
                                base64.b64encode(_hm_ps(unmute).encode("utf-16-le")).decode("ascii")], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=90, creationflags=NOWIN, stdin=subprocess.DEVNULL)
            out = (r.stdout or "") + "\n" + (r.stderr or "")
        except Exception as e: return ("err: " + str(e))[:140]
    m = re.search(r"HM_(DONE|ALREADY|UNMUTED|ERR)([^\r\n]*)", out or "")
    if not m: return "err: PowerShell không trả kết quả"
    if m.group(1) == "ERR":
        t = m.group(2).strip()
        return "nodev" if re.search(r"0x80070490|not found", t, re.I) else ("err: " + t)[:140]
    return {"DONE": "done", "ALREADY": "already", "UNMUTED": "unmuted"}[m.group(1)]
def _host_mute(force=False):
    """Tắt tiếng loa Windows của máy chủ nếu đang bật. Không force: HOST_MUTE=0 thì thôi; tối đa 1 lần / HOST_MUTE_EVERY giây (dấu
       redroid/hostmute.json). Trả kết quả _hm_run, hoặc None (chưa tới lượt / đã tắt tính năng). Không bao giờ ném lỗi."""
    try:
        if not force:
            if not HOST_MUTE: return None
            try:
                with open(HOST_MUTE_F, encoding="utf-8") as f: dt = time.time() - float(json.load(f).get("t") or 0)
                if 0 <= dt < HOST_MUTE_EVERY: return None
            except Exception: pass
        r = _hm_run()
        try:
            os.makedirs(os.path.dirname(HOST_MUTE_F), exist_ok=True)
            with open(HOST_MUTE_F, "w", encoding="utf-8") as f: json.dump({"t": time.time(), "kq": r}, f)
        except OSError: pass
        return r
    except Exception: return None
def cmd_bonho(a):
    """18/11 → 19/11: BỘ NHỚ máy khách ĐANG CHẠY (MuMu). phonectl bonho [TÊN…] → mỗi máy /data bao nhiêu, so với cỡ ĐÍCH của máy (cỡ đã
       nới / bậc theo RAM: DISK_TIERS) — chỉ đọc. phonectl bonho --sua TÊN… [--gb N] → ĐÚNG các máy được ghi tên, nhỏ hơn cỡ đích (hoặc N)
       thì nới lên (resize2fs bằng root, KHÔNG tắt máy, giữ dữ liệu). Không có lệnh nới mọi máy (chủ máy: máy cũ để nguyên).
       Dòng cuối: BONHO {json}."""
    fix = bool(getattr(a, "sua", False)); only = set(getattr(a, "names", None) or []); gbo = _int0(getattr(a, "gb", 0))
    if fix and not only:
        print("BONHO --sua phải ghi TÊN máy (VD: phonectl bonho --sua cp_ab12cd34ef) — máy cũ không tự nới (chủ máy: chỉ máy mới)", flush=True); sys.exit(2)
    if gbo and not (4 <= gbo <= DISK_MAX):
        print(f"BONHO --gb phải từ 4 tới {DISK_MAX}", flush=True); sys.exit(2)
    tiers = ",".join(f"{r:g}:{g}" for r, g in DISK_TIERS)
    res = {"emu": EMU, "tiers": tiers, "max": DISK_MAX, "fix": fix, "on": DISK_FIX, "ok": 0, "grown": 0, "small": 0, "bad": {}, "off": 0,
           "wait": 0, "host_free": None}
    if EMU != "mumu" or not DISK_FIX:
        res["skip"] = True
        print(("BONHO bỏ qua: máy chủ không chạy MuMu" if EMU != "mumu" else "BONHO đang tắt (DISK_FIX=0)"), flush=True)
        print("BONHO " + json.dumps(res, ensure_ascii=False)); return
    hf = _dg_hostfree(); res["host_free"] = round(hf, 1) if hf is not None else None
    st = load(); v = _mumu_list()
    if not v: print("BONHO lỗi: không đọc được danh sách máy MuMu", flush=True); res["err"] = "list"; print("BONHO " + json.dumps(res, ensure_ascii=False)); sys.exit(4)
    seen = set()
    for p in sorted(st["phones"], key=lambda x: str(x.get("name"))):
        nm = str(p.get("name", ""))
        if not nm.startswith(("cp_", "spare_")) or nm in seen or (only and nm not in only): continue
        seen.add(nm)
        if p.get("disk_new"): res["wait"] += 1
        i = next((k for k, x in v.items() if x["name"] == nm), None)
        if i is None or not v[i]["running"] or _asleep(p): res["off"] += 1; continue
        port = port_of(i)
        if not booted(port):
            if not _adb_fresh(port) and not booted(port): res["bad"].setdefault("?", []).append(nm); continue
        t = gbo if (fix and gbo) else _disk_target(p)
        k, msg = disk_grow(port, nm, fix=fix, want_gb=t)
        if k == "ok": res["ok"] += 1; continue
        if k == "grown":
            res["grown"] += 1; print(f"   ✓ {nm} (#{i}): {msg}", flush=True)
            try:
                st2 = load(); q = rec(nm, st2)
                if q:
                    q["disk_gb"] = max(t, _int0(q.get("disk_gb")))
                    if _int0(q.get("disk_new")) <= t:
                        for x in ("disk_new", "disk_try", "disk_buy"): q.pop(x, None)
                    save(st2)
            except Exception: pass
            continue
        if k == "small":
            res["small"] += 1
            print(f"   - {nm} (#{i}): {msg} · đích {t}GB" + (" (máy cũ — để nguyên)" if not (p.get("disk_gb") or p.get("disk_new")) else ""), flush=True); continue
        res["bad"].setdefault(k, []).append(nm); print(f"   ✗ {nm} (#{i}): {msg}", flush=True)
    print(f"BONHO {'nới' if fix else 'xem'} xong: {res['ok']} máy đủ bộ nhớ · {res['grown']} máy vừa nới · "
          + (f"{res['small']} máy nhỏ hơn cỡ đích · " if not fix else "")
          + f"{sum(len(x) for x in res['bad'].values())} máy chưa nới được · {res['off']} máy đang tắt / ngủ"
          + (f" · {res['wait']} máy hẹn nới lúc bật" if res["wait"] else "")
          + (f" · ổ máy chủ trống {hf:.0f}GB" if hf is not None else "") + f" · bậc miễn phí (RAM:GB) {tiers}", flush=True)
    print("BONHO " + json.dumps(res, ensure_ascii=False))
DISK_PERM = ("unsupported", "off", "bad", "noname", "nopart", "notext4")          # lỗi không tự hết → cloudphoned hoàn tiền ngay
def cmd_disk(a):
    """19/11: ĐẶT bộ nhớ /data của 1 máy khách lên --gb N (cloudphoned gọi khi khách MUA THÊM bộ nhớ / nâng RAM lên bậc cao hơn).
       Chỉ LỚN lên, không bao giờ thu nhỏ · giữ dữ liệu · KHÔNG tắt máy. Máy đang chạy → nới ngay · đang tắt / ngủ / đang lên → hẹn,
       lần bật tới tự nới (wait_boot) — cloudphoned gọi lại sau đến khi báo xong.
       Dòng cuối: DISK {json}. k: ok (đã đủ) · grown (vừa nới) · later (đã hẹn) · lỗi: unsupported / off / bad / noname / nopart /
       notext4 (không tự hết) · hostlow / noroot / fail / ? (thử lại sau). Mã thoát: 0 xong · 6 đã hẹn · 4 lỗi không tự hết · 5 thử lại."""
    name = str(a.name or ""); n = _int0(getattr(a, "gb", 0))
    res = {"name": name, "gb": n, "k": "", "msg": ""}
    def out(k, msg="", code=0):
        res.update(k=k, msg=msg); print("DISK " + json.dumps(res, ensure_ascii=False), flush=True); sys.exit(code)
    if EMU != "mumu": out("unsupported", "máy chủ này chưa hỗ trợ đổi bộ nhớ", 4)
    if not DISK_FIX: out("off", "máy chủ đang tắt tính năng bộ nhớ (DISK_FIX=0)", 4)
    if not (4 <= n <= DISK_MAX): out("bad", f"cỡ bộ nhớ phải từ 4 tới {DISK_MAX}GB", 4)
    if not SAFE.match(name) or not name.startswith(("cp_", "spare_")): out("noname", "tên máy không hợp lệ", 4)
    p = rec(name)
    if not p: out("noname", "không có máy tên này trên máy chủ", 4)
    def later(why):
        st = load(); q = rec(name, st)
        if not q: out("noname", "không có máy tên này trên máy chủ", 4)
        q["disk_new"] = max(n, _int0(q.get("disk_new"))); q["disk_buy"] = 1; q.pop("disk_try", None); save(st)
        out("later", why, 6)
    v = _mumu_list()
    if not v: out("?", "không đọc được danh sách máy", 5)
    i = next((k for k, x in v.items() if x["name"] == name), None)
    if i is None: out("noname", "máy không còn trong giả lập", 4)
    if not v[i]["running"] or _asleep(p): later("máy đang tắt / ngủ — tự nới lúc bật")
    port = port_of(i)
    if not booted(port) and not _adb_fresh(port) and not booted(port): later("máy đang khởi động — tự nới khi lên xong")
    k, msg = disk_grow(port, name, want_gb=n)
    if k in ("ok", "grown"):
        st = load(); q = rec(name, st)
        if q:
            q["disk_gb"] = max(n, _int0(q.get("disk_gb")))
            if _int0(q.get("disk_new")) <= n:
                for x in ("disk_new", "disk_try", "disk_buy"): q.pop(x, None)
            save(st)
        if k == "grown": print(f"   💾 {name}: {msg}", flush=True)
        out(k, msg, 0)
    out(k or "?", msg, 4 if k in DISK_PERM else 5)
def cmd_tattieng(a):
    """17/11h: tắt tiếng loa WINDOWS của máy chủ (không đụng giả lập / máy khách; khách không nghe tiếng từ máy chủ nên không ảnh hưởng).
         phonectl tattieng         → tắt tiếng ngay
         phonectl tattieng --bat   → bật tiếng lại (máy chủ sẽ tự tắt lại sau ≤ 10 phút; muốn giữ bật: phonectl setconf HOST_MUTE=0)
       Bình thường KHÔNG cần gọi: chống kẹt tự kiểm 10 phút / lần."""
    if getattr(a, "bat", False):
        r = _hm_run(unmute=True)
        print("TATTIENG " + r + " — " + ("đã BẬT tiếng máy chủ" + (" · máy chủ sẽ tự tắt lại sau ≤ 10 phút — muốn giữ bật: python phonectl.py setconf HOST_MUTE=0" if HOST_MUTE else "")
                                         if r == "unmuted" else "máy chủ không có loa / thiết bị âm thanh" if r == "nodev" else "chưa bật được tiếng: " + r), flush=True)
        return
    r = _host_mute(force=True) or "err: không rõ"
    txt = {"done": "đã TẮT tiếng Windows của máy chủ", "already": "Windows của máy chủ đang tắt tiếng sẵn", "nodev": "máy chủ không có loa / thiết bị âm thanh — không cần tắt",
           "skip": "không phải Windows — bỏ qua"}.get(r, "chưa tắt được tiếng: " + r)
    print(f"TATTIENG {r} — {txt}", flush=True)

def cmd_heal(a):
    """Gọi định kỳ (bảng BlueRoblox ~2 phút/lần): máy kẹt → khởi động lại; kẹt 3 lần liền → XOÁ máy hỏng (máy khách sẽ được tạo lại)."""
    try:
        if _host_mute() == "done": print("   🔇 Windows của máy chủ đang bật tiếng → đã tự tắt (thôi tự tắt: python phonectl.py setconf HOST_MUTE=0)", flush=True)
    except Exception: pass
    st = load(); v = vms(); h = _hl(); t = time.time(); seen = set(); busy_n = 0
    for p in st["phones"]:
        nm = p["name"]; seen.add(nm)
        if p.get("hold") or IDX(p, v) is None or not is_running(nm, p, v): h.pop(nm, None); continue
        _adb_fresh(p["port"])
        # 16/11k2: sổ khoá Android hỏng → máy khởi động lại liên tục (kiểu "kẹt 10 phút" bên dưới chỉ tắt / bật lại, không bao giờ khỏi)
        if EMU != "ld" and (KS_FIX or BOOT_FIX) and str(nm).startswith(("cp_", "spare_")):
            try:
                if _ks_tick(nm, p, tries=3 if time.time() - t < 60 else 1): h.pop(nm, None); continue
            except Exception as e: print(f"   (kiểm sổ khoá {nm} lỗi: {e})", flush=True)
        if booted(p["port"]): h.pop(nm, None); continue
        e = h.setdefault(nm, {"since": t, "tries": 0})
        if t - e["since"] < STUCK_MIN * 60: continue
        if e["tries"] >= 2:
            if not HEAL_DELETE:                          # không tự xoá máy khách → chỉ báo 1 lần, để admin xem tay
                if not e.get("warned"):
                    print(f"KHOI_DONG_LAI {nm}: Android vẫn không lên sau {e['tries']} lần khởi động lại — KHÔNG tự xoá, cần xem tay", flush=True)
                    e["warned"] = 1
                continue
            print(f"XOA_HONG {nm}: kẹt sau {e['tries']} lần khởi động lại → xoá máy hỏng (máy khách sẽ được tạo lại mới)", flush=True)
            a.name = nm; cmd_delete(a); h.pop(nm, None); continue
        if _recent_restart(nm) or _op_busy(IDX(p, v)): continue       # 16/11e: vừa khởi động lại (đang lên chậm) / lệnh khác đang làm → không chen
        if busy_n or not _pre_slot(p, prio=False, maxwait=HEAL_SLOT_S):   # 16/11e: máy chủ bận, chưa có lượt bật → để lần sau, KHÔNG tắt máy rồi chờ
            busy_n += 1
            if busy_n == 1: print(f"   ({nm}: máy chủ đang bận, chưa có lượt bật — chống kẹt để lần sau)", flush=True)
            continue
        e["tries"] += 1; e["since"] = t
        print(f"KHOI_DONG_LAI {nm}: Android không lên quá {STUCK_MIN} phút → khởi động lại (lần {e['tries']})", flush=True)
        with _cycle():
            _restart_mark(p.get("name")); adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3); start_phone(p)
    for k in list(h):
        if k not in seen: h.pop(k, None)
    _hs(h)
    if a.orphans: _cleanup(v, quiet=True)

# ---------- NGỦ KHI KHÔNG DÙNG: máy bỏ không lâu → tự tắt · khách mở máy → bluestream gọi `wake` bật lại ----------
# 18/11a (khách treo máy kêu "máy cứ tự nghỉ"): máy khách ĐANG CHẠY chỉ bị tắt êm cho NGỦ (app, dữ liệu giữ nguyên) khi đủ CẢ 3 điều:
#   (1) IDLE_STOP_H giờ liền (mặc định 18) KHÔNG AI MỞ máy (app / web / PC / ô xem trước — bluestream ghi redroid/viewers.json);
#   (2) cũng ngần ấy giờ liền, lượt đo nào (~2 phút / lần) cũng KHÔNG thấy máy có việc: không game / app nào ở màn trước (kể cả cửa
#       sổ nổi), không app của khách chạy nền có thông báo — và Android đã chạy liền ngần ấy giờ (máy vừa bật / khởi động lại thì chưa);
#   (3) IDLE_STOP_MIN phút gần nhất (mặc định 30) lượt đo nào cũng thấy máy ĐỨNG YÊN hẳn: màn hình chính + CPU trong máy thấp.
# Trước 18/11a chỉ cần (3) + 30 phút không ai xem. Máy treo game (game ở màn trước) KHÔNG BAO GIỜ bị tắt. Đo KHÔNG CHẮC (không đọc được
# màn hình / CPU, CPU cao ở màn hình chính) → lượt đó không cho ngủ, đếm lại (3), giữ mốc (2). Máy tắt / tạm dừng, hoặc máy chủ nghỉ đo
# quá IDLE_GAP_S → không tin mốc cũ: (2) tính lại từ đầu (chưa theo dõi đủ 18 giờ thì chưa ngủ). Giả lập không cho đọc danh sách máy /
# idle.json đang bận → lượt đó KHÔNG đo, giữ nguyên mốc (1 lần giả lập bận không được xoá mất mốc 18 giờ của mọi máy).
# Ngủ = hold + sleep: bootall / heal / cloudphoned không tự bật lại; bật bằng bất cứ đường nào (khách mở máy → wake, admin start /
# restart, đổi cấu hình…) là hết ngủ. RAM của máy ngủ vẫn được CHỪA (create / resize / cloudphoned) → khách mở lúc nào cũng bật lại được.
# Đổi số giờ: python phonectl.py setconf IDLE_STOP_H=12 · tắt hẳn tính năng: IDLE_STOP_MIN=0 (hoặc IDLE_STOP_H=0).
def _cf(k, d):
    try: return float(CONF.get(k, d) or 0)
    except (TypeError, ValueError): return float(d)
IDLE_MIN = _cf("IDLE_STOP_MIN", 30)          # phút ĐỨNG YÊN liền ngay trước lúc cho ngủ · 0 = tắt tính năng
IDLE_H = _cf("IDLE_STOP_H", 18)              # 18/11a: GIỜ liền không ai mở máy + không thấy máy có việc mới cho ngủ · 0 = tắt tính năng
IDLE_GAP_S = 7200                             # idle.json không được ghi quá 2 giờ (máy chủ tắt / nhận đơn dừng) → mốc cũ không còn chắc, tính lại
IDLE_CPU = _cf("IDLE_CPU_PCT", 10)           # CPU trong máy (cộng mọi nhân) từ mức này = máy đang làm gì đó → không cho ngủ
IDLE_SKIP = {x for x in re.split(r"[\s,;]+", CONF.get("IDLE_SKIP", "")) if x}     # tên máy KHÔNG BAO GIỜ cho ngủ: cp_abc,cp_def
IDLE_IGNORE = {x for x in re.split(r"[\s,;]+", CONF.get("IDLE_IGNORE", "")) if x}    # gói (hiện trên màn / chạy nền) KHÔNG tính là máy đang làm việc
IDLE_BATCH = 3                                # mỗi lượt cho ngủ tối đa 3 máy (đo sai → không tắt hàng loạt; 12/11: 6 máy/lượt dồn lệnh tắt vào MuMu)
IDLE_F = os.path.join(HOME, "redroid", "idle.json")
VIEW_F = os.path.join(HOME, "redroid", "viewers.json")
HOMES = {"com.mumu.launcher", "com.android.launcher3", "com.android.launcher", "com.android.launcher2", "com.microvirt.launcher",
         "com.microvirt.launcher2", "com.google.android.apps.nexuslauncher"}
_FG_RE = re.compile(r"\bu\d+\s+([A-Za-z][\w.]*)/")
_HOME_CACHE = {}

def _asleep(p):
    """Máy đang NGỦ thật (dấu ngủ + hold). Dấu ngủ sót lại mà hold đã gỡ (vd quay về bản cũ rồi bản cũ bật máy) → coi như thức."""
    return bool(p and p.get("sleep") and p.get("hold"))
RAM_RATIO_F = os.path.join(HOME, "redroid", "ram_ratio.json")
def _sleep_factor():
    """Máy NGỦ giữ bao nhiêu phần RAM đã cấp của nó: cloudphoned đo RAM THẬT 1 máy đang chạy dùng, chia RAM_OVER, ghi mỗi
       30 giây vào ram_ratio.json (13/11). Không có số mới (cloudphoned bản cũ / tắt quá 15 phút) → giữ đủ 100% như trước."""
    try:
        with open(RAM_RATIO_F, encoding="utf-8") as f: d = json.load(f)
        if 0 <= time.time() - float(d.get("t") or 0) < 900: return max(0.1, min(1.0, float(d["factor"])))
    except Exception: pass
    return 1.0
def _sleep_ram(st=None):
    """RAM (GB) phải CHỪA cho máy đang ngủ — khách mở là bật lại, không bán chỗ này cho máy mới (giữ theo RAM thật: _sleep_factor)."""
    return sum(min(float(p.get("ram") or 0), MAX_RAM) for p in (st or load())["phones"] if _asleep(p)) * _sleep_factor()
def _viewers():
    """(bluestream BIẾT ĐÁNH THỨC máy đang chạy?, {cổng adb: lúc có người xem gần nhất}) — bluestream ghi file mỗi 30 giây."""
    try:
        with open(VIEW_F, encoding="utf-8") as f: d = json.load(f)
        ok = time.time() - float(d.get("t") or 0) < 180 and int(d.get("wake") or 0) >= 1
        return ok, {str(k): float(x) for k, x in (d.get("seen") or {}).items()}
    except Exception: return False, {}
def _idle_load():
    """Mốc từng máy {tên: {"act": lượt đo đầu tiên thấy máy KHÔNG có việc (hoặc lúc Android bật), "since": bắt đầu chuỗi đứng yên liền,
       "busy": lượt gần nhất thấy máy có việc (chỉ để xem)}}.
       {} = chưa có / file hỏng / mốc quá cũ (tính lại từ đầu) · None = file đang bận, không đọc được → lượt này KHÔNG đo (giữ mốc)."""
    for k in range(4):
        try:
            age = time.time() - os.path.getmtime(IDLE_F)
            with open(IDLE_F, encoding="utf-8") as f: d = json.load(f)
            if not isinstance(d, dict) or not (-300 <= age <= IDLE_GAP_S): return {}
            return d
        except FileNotFoundError: return {}
        except ValueError: return {}                   # file hỏng (máy chủ bị tắt ngang lúc đang ghi) → coi như chưa có
        except OSError:                                # Windows: file đang bị lệnh khác thay → đọc lại
            if k < 3: time.sleep(0.3)
    return None
def _idle_save(d):
    """→ True nếu ghi được. Không bao giờ ném lỗi (Windows: file đang bị đọc đúng lúc → thử lại; vẫn không được thì lượt sau ghi)."""
    for k in range(4):
        try:
            os.makedirs(os.path.dirname(IDLE_F), exist_ok=True)
            with open(IDLE_F + ".tmp", "w", encoding="utf-8") as f: json.dump(d, f)
            os.replace(IDLE_F + ".tmp", IDLE_F)
            return True
        except OSError:
            if k < 3: time.sleep(0.3)
    return False
def _fg_pkgs(port):
    """Các gói đang HIỆN trên màn: cửa sổ giữ tiêu điểm + app đang mở (mọi màn hình) + MỌI cửa sổ app đang hiện (cả game ở cửa sổ
       nổi nằm cạnh màn hình chính). Rỗng = không đọc được."""
    r = adb("-s", f"127.0.0.1:{port}", "shell",
            "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'; echo ---; dumpsys window visible | grep -E 'Window[{ ]'", timeout=25)
    foc, _, vis = (r.stdout or "").partition("---")
    pk = lambda t: {m.group(1) for ln in t.splitlines() for m in [_FG_RE.search(ln)] if m}
    f = pk(foc)
    return f | pk(vis) if f else set()
def _home_pkgs(port):
    """Gói màn hình chính của máy: hỏi Android + các launcher quen của MuMu / LDPlayer / MEmu."""
    if port not in _HOME_CACHE:
        r = adb("-s", f"127.0.0.1:{port}", "shell",
                "cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME", timeout=20)
        hs = set(HOMES)
        for ln in (r.stdout or "").splitlines():
            m = re.match(r"^\s*([A-Za-z][\w.]*)/", ln)
            if m and m.group(1) not in ("android", "com.android.settings"): hs.add(m.group(1))   # hộp chọn launcher / màn chờ khởi động: không tính
        _HOME_CACHE[port] = hs
    return _HOME_CACHE[port]
def _fg_services(port):
    """App CỦA KHÁCH (không phải app hệ thống) đang chạy dịch vụ nền có thông báo (bot, tool treo, tải file…) → máy đang làm việc."""
    s = f"127.0.0.1:{port}"; cur, fg = "", set()
    r = adb("-s", s, "shell", "dumpsys activity services | grep -E '\\* ServiceRecord|isForeground=true'", timeout=25)
    for ln in (r.stdout or "").splitlines():
        if "* ServiceRecord{" in ln: m = _FG_RE.search(ln); cur = m.group(1) if m else ""
        elif "isForeground=true" in ln and cur: fg.add(cur)
    if not fg: return set()
    third = {ln.split(":", 1)[1].strip() for ln in (adb("-s", s, "shell", "pm list packages -3", timeout=25).stdout or "").splitlines() if ln.startswith("package:")}
    return {x for x in fg if x in third and x not in IDLE_IGNORE and "launcher" not in x.lower()}
def _guest_cpu_up(port):
    """(% CPU đang dùng TRONG máy — cộng mọi nhân, đo 2 giây · số giây Android đã chạy từ lần bật gần nhất). None = không đo / đọc được."""
    r = adb("-s", f"127.0.0.1:{port}", "shell", "cat /proc/uptime; grep '^cpu ' /proc/stat; sleep 2; grep '^cpu ' /proc/stat", timeout=25)
    lines = (r.stdout or "").splitlines(); up = None
    for ln in lines[:3]:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s+\d+(?:\.\d+)?\s*$", ln)
        if m: up = float(m.group(1)); break
    rows = [ln.split()[1:9] for ln in lines if ln.startswith("cpu ")]
    if len(rows) < 2: return None, up
    try: a0, a1 = [list(map(int, x)) for x in rows[:2]]
    except ValueError: return None, up
    d = [y - x for x, y in zip(a0, a1)]; tot = sum(d)
    if tot <= 0: return None, up
    return round(100.0 * (tot - d[3] - (d[4] if len(d) > 4 else 0)) / tot, 1), up
def _guest_cpu(port):
    """% CPU đang dùng TRONG máy (cộng mọi nhân, đo 2 giây). None = không đo được."""
    return _guest_cpu_up(port)[0]
def _idle_kind(p, seen, t):
    """(loại, lý do, số giây từ lần có người xem, số giây Android đã chạy | None) của 1 máy đang chạy. Loại: "busy" = CHẮC CHẮN máy đang
       có việc (có người xem · game / app ở màn trước · app của khách chạy nền) · "idle" = đứng yên hẳn · "soft" = không chắc (không đọc
       được, CPU cao ở màn hình chính)."""
    port = p["port"]; ago = t - seen.get(str(port), 0.0)
    if ago < 90: return "busy", "đang có người xem", ago, None
    if not booted(port): return "soft", "Android chưa sẵn sàng / mất kết nối", ago, None
    fg = _fg_pkgs(port)
    if not fg: return "soft", "không đọc được màn trước", ago, None
    hs = _home_pkgs(port)
    busy = sorted(x for x in fg if x not in hs and x not in IDLE_IGNORE and "launcher" not in x.lower())
    if busy: return "busy", "đang mở " + ", ".join(busy), ago, None
    bg = _fg_services(port)
    if bg: return "busy", "app chạy nền " + ", ".join(sorted(bg)), ago, None
    c, up = _guest_cpu_up(port)
    if c is None: return "soft", "không đo được CPU", ago, up
    if up is None: return "soft", "không đọc được máy đã chạy bao lâu", ago, None
    if c >= IDLE_CPU: return "soft", f"màn hình chính nhưng CPU trong máy {c:g}%", ago, up
    return "idle", f"màn hình chính · CPU {c:g}%", ago, up
def _idle_probe(p, seen, t):
    """(rảnh?, lý do, số giây từ lần có người xem) của 1 máy đang chạy — kiểu trả cũ."""
    k, why, ago, _up = _idle_kind(p, seen, t)
    return k == "idle", why, ago
def _dur(sec):
    """Số giây → chữ cho người đọc: "17 giờ 05 phút" · "12 phút"."""
    m = max(0, int(sec // 60))
    return f"{m // 60} giờ {m % 60:02d} phút" if m >= 60 else f"{m} phút"
def _sleep_one(p, why="", check_view=True, view_s=120):
    """Cho 1 máy NGỦ: đánh dấu ngủ TRƯỚC (bootall / cloudphoned không bật lại giữa chừng) → tắt êm. Không tắt được → bỏ dấu, chạy tiếp.
       view_s: có người mở máy trong ngần ấy giây gần đây (đọc LẠI viewers.json ngay trước khi tắt) → không tắt."""
    nm = p["name"]
    if check_view:
        ok, seen = _viewers()
        if not ok: return False, "phát hình không báo người xem — để máy chạy"
        if time.time() - seen.get(str(p["port"]), 0.0) < view_s: return False, "vừa có người mở máy — để máy chạy"
    q = rec(nm)
    if not q or q.get("hold"): return False, "máy vừa bị tạm dừng / xoá — bỏ qua"
    set_hold(nm, True, sleep=True)
    adb("disconnect", serial(p), timeout=15)
    i = IDX(p)
    if i is not None: memuc("stop", "-i", i, timeout=120)
    for _ in range(30):
        if not is_running(nm, p):
            if i is not None: _op_unmark(i)                # 16/11b: máy ngủ xong → khách mở là bật lại NGAY (không tính là "lệnh khác đang làm dở")
            return True, why
        time.sleep(2)
    set_hold(nm, False)
    return False, f"{EMU_NAME} chưa tắt được máy — để máy chạy tiếp"

def cmd_idle(a):
    """Gọi định kỳ (cloudphoned ~2 phút/lần). 18/11a: máy chỉ NGỦ khi IDLE_STOP_H giờ (18) liền không ai mở máy + không thấy máy có việc,
       và IDLE_STOP_MIN phút (30) gần nhất lượt đo nào cũng thấy máy đứng yên. --dry: chỉ in, không tắt máy nào, không ghi mốc."""
    mins = IDLE_MIN if a.min is None else a.min
    hrs = IDLE_H if getattr(a, "gio", None) is None else a.gio
    if mins <= 0 or hrs <= 0: print("IDLE_OFF tính năng đang tắt (IDLE_STOP_MIN=0 hoặc IDLE_STOP_H=0)"); return
    need = hrs * 3600.0
    fresh, seen = _viewers()
    if not fresh and not a.dry:
        print("IDLE_SKIP phát hình (bluestream) bản biết đánh thức máy chưa chạy → không cho máy nào ngủ"); return
    st = load(); v = vms_sure(); t = time.time(); old = _idle_load(); new = {}
    if not v:                                              # giả lập đang bận / lỗi → KHÔNG coi là "mọi máy đã tắt" (sẽ xoá hết mốc 18 giờ)
        print(f"IDLE_SKIP không đọc được danh sách máy của {EMU_NAME} (đang bận) → lượt này không đo, giữ nguyên mốc"); return
    if old is None:
        print("IDLE_SKIP không đọc được redroid/idle.json (file đang bận) → lượt này không đo, giữ nguyên mốc"); return
    cands = [p for p in st["phones"] if p["name"] not in IDLE_SKIP and not p.get("hold") and p.get("kind") != "gpu"
             and parse_dt(p["expires"]) > now() and is_running(p["name"], p, v)]
    def probe(p):
        try: return _idle_kind(p, seen, t)
        except Exception as e: return "soft", f"lỗi đo: {e!r}", 0.0, None
    def mark(e, *ks):
        """Mốc đã ghi (không ở tương lai) — chưa có / hỏng → bây giờ."""
        for k in ks:
            try:
                x = float(e.get(k) or 0)
                if 0 < x <= t: return x
            except (TypeError, ValueError): pass
        return t
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex: res = list(ex.map(probe, cands))
    n_idle = n_slept = 0; talk = a.dry or a.verbose
    for p, (kind, why, ago, up) in zip(cands, res):
        nm = p["name"]; e = old.get(nm); e = e if isinstance(e, dict) else {}
        if kind == "busy":                                 # CHẮC CHẮN máy đang có việc → bỏ mốc: 18 giờ sẽ tính từ LƯỢT ĐO ĐẦU TIÊN thấy máy
            new[nm] = {"busy": t}                          # hết việc (việc có thể còn chạy tới sát lượt đó — không tính từ lượt này)
            if talk: print(f"  {nm}: không rảnh — {why}")
            continue
        act = mark(e, "act", "since")                      # bản trước 18/11a chỉ ghi "since" (máy đứng yên từ lúc đó) → lấy làm mốc
        if up is not None and up >= 0: act = max(act, min(t, t - up))      # máy vừa bật / khởi động lại → 18 giờ tính từ lúc Android chạy
        if kind != "idle":                                 # không chắc → lượt này không cho ngủ, đếm lại chuỗi "đứng yên liền"
            new[nm] = {"act": act}
            if talk: print(f"  {nm}: không rảnh — {why}")
            continue
        n_idle += 1
        since = mark(e, "since"); new[nm] = {"act": act, "since": since}
        rest = max(mins * 60 - (t - since), need - ago, need - (t - act))
        if rest > 0:
            if talk:
                print(f"  {nm}: đứng yên {_dur(t - since)} ({why}) · không ai mở máy {_dur(ago) if ago < 3 * 86400 else 'hơn 3 ngày'}"
                      f" · không thấy máy có việc {_dur(t - act)} — còn {_dur(rest + 59)} nữa mới cho ngủ")
            continue
        if a.dry: print(f"NGU_THU {nm}: sẽ cho ngủ ({why}, {hrs:g} giờ không ai mở máy, không có việc)"); continue
        if n_slept >= IDLE_BATCH: continue
        ok, how = _sleep_one(p, f"{hrs:g} giờ không ai mở máy, không có việc · {why}", view_s=max(120.0, need))
        print(("NGU " if ok else "NGU_LOI ") + f"{nm}: {how}", flush=True)
        if ok: n_slept += 1; new.pop(nm, None)
    if not a.dry and not _idle_save(new):
        print("IDLE_SKIP không ghi được redroid/idle.json (file đang bận) → mốc của lượt này chưa lưu, lượt sau ghi lại")
    print(f"IDLE_OK {len(cands)} máy đang chạy · {n_idle} máy rảnh · {n_slept} máy vừa cho ngủ · ngưỡng {hrs:g} giờ không ai mở máy + không có việc, "
          f"{mins:g} phút đứng yên liền, CPU < {IDLE_CPU:g}%")

def cmd_sleep(a):
    """Admin cho 1 máy ngủ NGAY (thử tính năng). Khách mở máy → tự bật lại."""
    st, p = _need(a.name)
    if p.get("hold"):
        print(f"'{a.name}' " + ("đang ngủ sẵn." if _asleep(p) else "đang tạm dừng (admin khoá / hết hạn) — không cho ngủ.")); return
    if not is_running(a.name, p): print(f"'{a.name}' đang tắt — không cần cho ngủ."); return
    if not _viewers()[0] and not a.force:
        print("LỖI: phát hình (bluestream) bản biết đánh thức máy chưa chạy — khách sẽ không tự bật lại được. Cập nhật bluestream trước."); sys.exit(3)
    ok, how = _sleep_one(p, "admin cho ngủ", check_view=False)
    print(f"💤 Đã cho '{a.name}' ngủ — khách mở máy là tự bật lại." if ok else f"❌ Chưa cho ngủ được: {how}"); sys.exit(0 if ok else 5)

BOOT_RESCUE_MAX = max(1, int(_cfn("BOOT_RESCUE_MAX", 3)))      # mỗi 10 phút cả máy chủ chỉ tự bật lại tối đa ngần này máy treo lúc bật
RESCUE_F = os.path.join(HOME, "redroid", "rescue.json")
def _adb_alive():
    """Chương trình adb của máy chủ còn trả lời (adb devices)? Không → mọi máy đều "không nối được" chứ không phải máy ảo treo."""
    try:
        r = adb("devices", timeout=15)
        return r.returncode in (0, None) and "List of devices" in (r.stdout or "")
    except Exception: return False
def _rescue_take():
    """Xin 1 lượt "bật lại máy treo lúc bật" — cả máy chủ tối đa BOOT_RESCUE_MAX lượt / 10 phút (nhiều máy cùng treo = lỗi chung, bật lại
       hàng loạt chỉ làm nặng thêm)."""
    try:
        with _Lock("rescue", wait=15):
            try: ts = [float(x) for x in json.load(open(RESCUE_F, encoding="utf-8"))]
            except Exception: ts = []
            now_ = time.time(); ts = [x for x in ts if 0 <= now_ - x < 600]
            if len(ts) >= BOOT_RESCUE_MAX: return False
            ts.append(now_)
            os.makedirs(os.path.dirname(RESCUE_F), exist_ok=True)
            with open(RESCUE_F, "w", encoding="utf-8") as f: json.dump(ts, f)
            return True
    except Exception: return False
def _boot_rescue(p):
    """17/11f: máy ảo vừa được CHÍNH LỆNH NÀY bật mà suốt BOOT_RESCUE_S giây adb không nối được lần nào = máy ảo treo lúc bật (không phải
       Android lên chậm) → tắt hẳn đúng máy đó rồi bật lại 1 lần (17/11 máy chủ 156: máy chủ vừa khởi động lại, 2 máy "Android chưa lên
       sau 5 phút", khách quay mãi). Máy chủ đang quá tải (CPU ≥ BOOT_CPU_PCT) → không làm, chờ tiếp. KHÔNG dùng cho máy đang chạy sẵn."""
    nm = p["name"]; i = IDX(p)
    if i is None or _op_busy(i): return False
    if _cpu_pct() >= BOOT_CPU:
        print(f"   ({nm}: Android chưa trả lời nhưng máy chủ đang bận (CPU cao) → chờ thêm, không bật lại)", flush=True); return False
    if not _adb_alive():
        print(f"   ({nm}: Android chưa trả lời nhưng chương trình adb của máy chủ không trả lời → lỗi chung, không bật lại máy)", flush=True); return False
    if not _rescue_take():
        print(f"   ({nm}: Android chưa trả lời — 10 phút qua đã bật lại {BOOT_RESCUE_MAX} máy treo rồi: nhiều máy cùng không lên là lỗi chung của máy chủ / giả lập "
              "→ KHÔNG bật lại hàng loạt, chờ tiếp; chạy lệnh A để kiểm)", flush=True); return False
    print(f"   ({nm}: bật đã {int(BOOT_RESCUE_S)} giây mà Android chưa trả lời lần nào → máy ảo treo lúc bật — tắt hẳn rồi bật lại 1 lần)", flush=True)
    try:
        with _cycle():
            _restart_mark(nm); adb("disconnect", serial(p), timeout=15)
            ok, how = force_stop(p); print(("   ✓ " if ok else "   ⚠ ") + how, flush=True)
            if not ok: return False
            time.sleep(3); r = start_phone(p)
            if r is None or _start_failed(r): time.sleep(10); r = start_phone(p)
        return not (r is None or _start_failed(r))
    except Exception as e:
        print("   (bật lại lỗi:", repr(e)[:120], ")", flush=True); return False
def _boot1_f(nm): return os.path.join(HOME, "redroid", f"boot1_{nm}.go")
def _boot1_go(nm):
    """Lệnh con của đợt bật báo "tôi đã tới lượt" (máy đang chạy sẵn / đã gửi lệnh bật) → bootall mới gọi lệnh con kế (giữ ĐÚNG thứ tự)."""
    try:
        if _NAME_OK.fullmatch(str(nm)): open(_boot1_f(nm), "w").close()
    except OSError: pass
def _wake_one(p, boot=False):
    """Bật 1 máy đang ngủ → chờ Android lên → in WAKE_READY (bluestream cho khách vào ngay) → tối ưu / quyền / root / ẩn cửa sổ như bootall.
       boot=True (17/11f): lệnh con của đợt bật hàng loạt (bootall → boot1) — việc nền, dùng số suất của đợt bật."""
    nm = p["name"]; t0 = time.time()
    if p.get("hold") and not _asleep(p): return False, "WAKE_NO máy đang tạm dừng (admin khoá / hết hạn) — không bật"
    try: lk = _Lock("wake_" + nm, wait=1); lk.__enter__()
    except RuntimeError:
        if not boot: _prio_ask(nm)                                   # 17/11f: khách mở đúng máy đang xếp hàng trong đợt bật → cho lên trước
        return False, "WAKE_BUSY lệnh khác đang bật máy này"
    try:
        launched = False
        if is_running(nm, p):                                      # còn chạy (tắt chưa xong / dấu ngủ sót) → chỉ bỏ dấu ngủ
            print(f"WAKE_RUNNING {nm}", flush=True)                # 16/11: phát hình biết máy ĐANG CHẠY mà Android chưa trả lời (không bật gì thêm)
            if boot: _boot1_go(nm)
            set_hold(nm, False)
        else:
            def busy():                                              # 16/11b: lệnh khác vừa tắt máy này và đang làm dở?
                i_ = IDX(p)
                return i_ is not None and _op_busy(i_)
            BUSY = "WAKE_BUSY lệnh khác đang làm việc với máy này (khởi động lại / đổi cấu hình…) — xong sẽ tự bật"
            if busy(): return False, BUSY                            # → KHÔNG bật chen ngang
            r = start_phone(p, guard=busy, par=_bootall_par() if boot else None)   # kiểm lại lần nữa SAU khi chờ tới lượt bật (có thể chờ vài phút)
            if boot: _boot1_go(nm)
            if r is None: return False, BUSY
            if _start_failed(r):                                     # máy kẹt nửa chừng (tiến trình cũ chưa tắt hẳn…) → tắt hẳn rồi bật lại 1 lần
                print(f"   ({nm}: bật lần 1 chưa được — tắt hẳn rồi bật lại)", flush=True)
                try: force_stop(p)
                except Exception as e: print("   (tắt hẳn lỗi:", repr(e)[:120], ")", flush=True)
                time.sleep(5)
                r = start_phone(p)
            if _start_failed(r): return False, f"WAKE_FAIL {EMU_NAME} không bật được: " + ((r.stdout or "") + (r.stderr or "")).strip()[-160:]
            launched = True
        why = "lúc bật lại máy (đợt bật hàng loạt)" if boot else "lúc khách mở máy"
        info = {}; first = int(BOOT_RESCUE_S) if launched and 0 < BOOT_RESCUE_S < BOOT_WAIT else BOOT_WAIT
        ok = _wait_android(nm, p["port"], p, wait=first, step=2, why=why, info=info)   # 16/11k2: khách mở máy đang sập vì sổ khoá hỏng → sửa rồi mới cho vào
        if not ok and first < BOOT_WAIT:                           # 17/11f: chưa lên sau BOOT_RESCUE_S giây
            if not info.get("adb") and _boot_rescue(p): ok = _wait_android(nm, p["port"], p, step=2, why=why)
            else: ok = _wait_android(nm, p["port"], p, wait=BOOT_WAIT - first, step=2, why=why)
        _boot_done(nm)
        if not ok: return False, f"WAKE_FAIL Android chưa lên sau {BOOT_WAIT // 60} phút"
        try: _proxy_keep(p)                                         # 22/11: proxy riêng bật TRƯỚC khi khách vào (app khách không lộ IP máy chủ)
        except Exception as e: print("   (proxy sau khi bật:", repr(e)[:120], ")", flush=True)
        print(f"WAKE_READY {nm} {int(time.time() - t0)}", flush=True)
        for fn in (lambda: _root_keep(p), lambda: grant_perms(nm), lambda: tune(nm, p["port"]), lambda: hide_window(nm)):
            try: fn()
            except Exception as e: print("   (sau khi bật:", repr(e)[:120], ")", flush=True)
        return True, f"WAKE_OK {nm} sẵn sàng sau {int(time.time() - t0)} giây"
    finally: lk.__exit__()
def cmd_boot1(a):
    """boot1 TÊN (bootall gọi, 17/11f): bật 1 máy khách đang TẮT, chờ Android lên, tự cứu máy treo lúc bật. Mã thoát: 0 xong · 7 lệnh
       khác đang bật máy này · 5 lỗi."""
    st, p = _need(a.name)
    ok, msg = _wake_one(p, boot=True); print(msg, flush=True)
    sys.exit(0 if ok else 7 if msg.startswith("WAKE_BUSY") else 4 if msg.startswith("WAKE_NO") else 5)
def cmd_wake(a):
    """wake TÊN | --all: bật lại máy đang NGỦ (bluestream gọi khi khách mở máy)."""
    if not a.all:
        st, p = _need(a.name); ok, msg = _wake_one(p); print(msg, flush=True); sys.exit(0 if ok else 5)
    bad = 0
    for p in [x for x in load()["phones"] if _asleep(x)]:
        ok, msg = _wake_one(p); print(msg, flush=True); bad += 0 if ok else 1
    print("WAKEALL xong" + (f" ({bad} máy lỗi)" if bad else "")); sys.exit(6 if bad else 0)

def _ours(nm):
    """Máy do CloudBlue tạo? MuMu hay cài chung máy có sẵn máy riêng của chủ máy → chỉ đụng máy cp_… / spare_….
       LDPlayer / MEmu: máy chủ riêng → như cũ (mọi máy)."""
    return EMU != "mumu" or str(nm).startswith(("cp_", "spare_"))
def _cleanup(v=None, quiet=False, all_=False):
    """Xoá máy trong MEmu KHÔNG thuộc danh sách BlueRoblox (giả lập cũ / thừa / tạo dở). Giữ máy mẫu (MEMU_TEMPLATE)."""
    if quiet and _creating_now(): return                 # đang tạo máy khách → để lần sau
    v = v if v is not None else vms()
    if quiet and v:
        try: _adopt(v, quiet=True)                       # 14/11: máy khách lạc khỏi danh sách → nhận lại, KHÔNG xoá
        except Exception as e: print("   (nhận lại máy lạc lỗi:", repr(e)[:120], ")", flush=True)
    mine = {p["name"] for p in load()["phones"]}; tpl = CONF.get("MEMU_TEMPLATE", "")
    web = None
    if quiet:                                            # tự động: hỏi web trước khi xoá — web còn ghi máy này (bất kỳ trạng thái nào trừ huỷ / lỗi) → giữ
        cand = [x["name"] for x in v.values() if str(x["name"]).startswith("cp_") and x["name"] not in mine]
        web = _web_rows(cand) if cand else {}
        if web is None: return                           # không đọc được web → không xoá gì
    gone = 0
    for i in sorted(v, reverse=True):          # xoá từ số lớn xuống → số máy còn lại ít bị đổi
        nm = v[i]["name"]
        if nm == tpl or (nm in mine and not all_) or (nm.startswith("spare_") and not all_): continue
        if nm.startswith("tpl_") or nm in {tpl_name(x) for x in ANDROIDS}: continue      # máy MẪU từng bản Android — không bao giờ xoá
        if EMU in ("ld", "mumu") and i == 0: continue        # LDPlayer / MuMu: giữ máy gốc số 0 (giả lập cần)
        if not _ours(nm): continue                            # máy riêng của chủ máy (MuMu dùng chung máy) — không bao giờ đụng
        if quiet and not nm.startswith("cp_"): continue     # tự động: chỉ dọn máy do BlueRoblox tạo (cp_…)
        if quiet and (_creating_now() or nm in {p["name"] for p in load()["phones"]}): continue   # kiểm lại ngay trước khi xoá
        if quiet and web is not None and nm in web and web[nm].get("status") not in ("cancelled", "error"):
            print(f"GIU_LAI {nm}: không có trong danh sách nhưng web còn ghi '{web[nm].get('status')}' (máy chủ {web[nm].get('node') or '?'}) — không xoá", flush=True)
            continue
        print(f"XOA_THUA {nm} (MEmu #{i})", flush=True)
        def _at(n):                                          # số máy HIỆN TẠI của máy tên n (MEmu đổi số khi xoá máy khác) — KHÔNG BAO GIỜ đụng máy khác tên
            return next(((k, x) for k, x in vms().items() if x["name"] == n), (None, None))
        for _t in range(3):                                  # tắt HẲN rồi mới xoá (MEmu không xoá máy đang chạy) → kiểm tra đã mất thật
            k, x = _at(nm)
            if k is None: gone += 1; _vmdata_rm_if_gone(nm); break
            if x["running"]:
                memuc("stop", "-i", k, timeout=120)
                for _w in range(20):
                    k, x = _at(nm)
                    if k is None or not x["running"]: break
                    time.sleep(3)
            k, x = _at(nm)
            if k is None: gone += 1; _vmdata_rm_if_gone(nm); break
            r = memuc("remove", "-i", k, timeout=180)
            if _at(nm)[0] is None: gone += 1; _vmdata_rm_if_gone(nm); break
            print(f"   (chưa xoá được, thử lại: {((r.stdout or '') + (r.stderr or '')).strip()[-120:]})", flush=True); time.sleep(5)
        else: print(f"   ✗ KHÔNG xoá được {nm} — tắt bằng tay trong MEmu Multi-Instance rồi chạy lại", flush=True)
    if all_:
        st = load()
        for x in list(st["phones"]): drop_phone(st, x["name"])
        save(st)
    if not quiet or gone: print(f"Đã xoá {gone} giả lập.")
def cmd_cleanup(a):
    if a.all and not a.yes: print("Thêm --yes để xác nhận XOÁ TẤT CẢ (kể cả máy khách)."); sys.exit(1)
    _cleanup(all_=a.all)

# ---------- MÁY DỰNG SẴN: tạo + khởi động + ảnh nền + cài app TRƯỚC → khách mua là có máy sau ~1 phút ----------
POOL_F = os.path.join(HOME, "redroid", "pool.json")
POOL_SIZE = int(CONF.get("POOL_SIZE", "1") or 0)          # giữ sẵn 1 máy dựng trước (đổi: POOL_SIZE=N trong cloudphone.conf, 0 = tắt)
def _pl():
    try: return json.load(open(POOL_F, encoding="utf-8"))
    except Exception: return {"ready": []}
def _ps(d):
    os.makedirs(os.path.dirname(POOL_F), exist_ok=True); json.dump(d, open(POOL_F, "w", encoding="utf-8"))
def take_spare(new_name):
    """Lấy 1 máy dựng sẵn (đang tắt) → đổi tên thành máy khách. Trả về số máy MEmu, hoặc None nếu không có."""
    if POOL_SIZE <= 0: return None
    try:
        with _Lock("poolstate", wait=20):
            d = _pl(); v = vms()
            while d["ready"]:
                nm = d["ready"].pop(0); d["building"] = [x for x in d.get("building", []) if x != nm]
                i = next((k for k, x in v.items() if x["name"] == nm and not x["running"]), None)
                if i is None: continue
                for _ in range(3):                                           # đổi tên PHẢI thành công (tìm máy theo tên)
                    memuc("rename", "-i", i, new_name, timeout=60)
                    if any(x["name"] == new_name for x in vms().values()): break
                    time.sleep(2)
                else:
                    print("   (không đổi tên được máy dựng sẵn — tạo máy mới)", flush=True); continue
                _vmdata_rm(nm)                                               # thư mục riêng của máy dựng sẵn (máy khách dùng thư mục mới theo tên mới)
                for fn in os.listdir(os.path.join(HOME, "redroid")):          # app đã cài sẵn → khỏi cài lại
                    if fn.startswith(f"pre_{nm}_"):
                        try: os.replace(os.path.join(HOME, "redroid", fn), os.path.join(HOME, "redroid", fn.replace(f"pre_{nm}_", f"pre_{new_name}_", 1)))
                        except OSError: pass
                _ps(d); return i
            _ps(d)
    except Exception as e: print("   (không lấy được máy dựng sẵn:", e, ")")
    return None
def _creating_now():
    """Có đơn máy khách đang được tạo không (để máy dựng sẵn KHÔNG giành lượt MEmu của khách)."""
    d = os.path.join(HOME, "redroid"); busy = False
    for fn in os.listdir(d) if os.path.isdir(d) else []:
        if fn.startswith("creating_") and fn.endswith(".flag"):
            pid = fn[9:-5]
            if pid.isdigit() and _pid_alive(pid): busy = True
            else:
                try: os.remove(os.path.join(d, fn))
                except OSError: pass
    return busy
def cmd_pool(a):
    """Giữ sẵn POOL_SIZE máy dựng sẵn (đang tắt, không tốn RAM — chỉ ~1GB ổ cứng mỗi máy)."""
    if POOL_SIZE <= 0 or _creating_now(): return
    try: lk = _Lock("pool", wait=1); lk.__enter__()
    except Exception: return                       # đang dựng máy khác
    try:
        d = _pl(); v = vms(); d.setdefault("building", [])
        names = {x["name"] for x in v.values()}
        mine = {p["name"] for p in load()["phones"]}
        d["ready"] = [n for n in d["ready"] if n in names]
        # CHỈ xoá máy mà CHÍNH bộ dựng sẵn đang dựng dở (ghi trong "building") — KHÔNG BAO GIỜ đụng máy đã giao cho khách
        for i, x in sorted(v.items(), reverse=True):
            if x["name"] in d["building"] and x["name"] not in d["ready"] and x["name"] not in mine:
                print(f"XOA_DO {x['name']}", flush=True)
                if x["running"]: memuc("stop", "-i", i, timeout=120); time.sleep(3)
                memuc("remove", "-i", i, timeout=180)
        d["building"] = []
        _ps(d)
        if len(d["ready"]) >= POOL_SIZE: return
        import shutil
        if shutil.disk_usage(HOME).free / 2**30 < 20: print("Ổ cứng < 20GB trống — không dựng máy sẵn."); return
        nm = f"spare_{int(time.time())}"
        if _creating_now(): return
        # có máy (khách) vừa bật < 3 phút → để nó khởi động xong đã (2 máy cùng khởi động → MEmu hay báo "memory is low")
        recent = [p for p in load()["phones"] if time.time() - os.path.getmtime(STATE) < 180]
        if recent: return
        print(f"DUNG_SAN {nm}: tạo + khởi động + cài sẵn…", flush=True)
        with _Lock("memu", wait=5):                     # không chờ: đang có việc MEmu khác (máy khách) → để lần sau
            v0 = vms()
            if not v0 and EMU == "ld" and memuc("ensurebase", timeout=240).returncode == 0: v0 = vms()     # 17/11a: LDPlayer chưa có máy nào → tạo máy gốc
            if not v0: print("LỖI dựng máy sẵn: không đọc được danh sách máy — để lần sau"); return    # danh sách rỗng → mọi máy sẽ bị coi là "mới" → không làm
            before = set(v0)
            d = _pl(); d.setdefault("building", []).append(nm); _ps(d)      # ghi trước: chương trình bị ngắt giữa chừng → lần sau tự xoá máy dở
            r, idx = create_vm(DEF_ANDROID, nm)          # bản Android mặc định của máy chủ
            v2 = vms(); new = sorted(set(v2) - before)
            def _drop(ix):                               # máy dở không đặt được tên → XOÁ NGAY (không để thành "MEmuNN" mồ côi ăn CPU)
                print(f"XOA_DO MEmu #{ix} (không đặt tên được)", flush=True)
                if (vms().get(ix) or {}).get("running"): memuc("stop", "-i", ix, timeout=120); time.sleep(3)
                memuc("remove", "-i", ix, timeout=180)
            if idx is None:
                for ix in reversed(new if (EMU != "mumu" or len(new) == 1) else []):     # MuMu: chủ máy có thể vừa tạo máy riêng → chỉ xoá khi chắc đúng 1 máy dở
                    if re.match(r"^(MEmu(_?\d+)?|new_\d+|MuMu.*)$", v2[ix]["name"]) and ix != 0: _drop(ix)
                print("LỖI dựng máy sẵn:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); return
            for _t in range(4):
                memuc("rename", "-i", idx, nm, timeout=60)
                if (vms().get(idx) or {}).get("name") == nm: break
                time.sleep(3)
            else:
                _drop(idx); return
        # chỉnh cài đặt NGOÀI khoá "memu" → đơn máy khách chen vào được bất cứ lúc nào; có đơn khách → dừng, lần sau làm tiếp
        if _creating_now(): print(f"LỖI {nm}: nhường đơn máy khách — dựng lại sau"); return
        configure(idx, 2, 2, "720x1280", auto_dpi("720x1280")); memuc("setconfigex", "-i", idx, "fps", 30, timeout=60); apply_template(idx)
        if _creating_now(): print(f"LỖI {nm}: nhường đơn máy khách — dựng lại sau"); return
        port = port_of(idx)
        _boot_take("spare:" + nm, False)
        if _start_failed(memu_start(idx)): _boot_done("spare:" + nm); print(f"LỖI {nm}: không bật được"); return
        ok = False; t0 = time.time()
        while time.time() - t0 < BOOT_WAIT:
            adb_connect(port)
            if booted(port): ok = True; break
            time.sleep(3)
        if ok:
            try: set_wallpaper(nm, port)
            except Exception: pass
            tune(nm, port); preinstall(nm, port)
        adb("disconnect", f"127.0.0.1:{port}", timeout=15)
        i2 = next((k for k, x in vms().items() if x["name"] == nm), None)
        memuc("stop", "-i", idx if i2 is None else i2, timeout=120)     # LUÔN tắt máy dựng sẵn (không để chạy ngầm ăn CPU)
        if ok:
            d = _pl(); d["ready"].append(nm); d["building"] = [x for x in d.get("building", []) if x != nm]; _ps(d)
            print(f"SAN_SANG {nm}: máy dựng sẵn đã xong ({len(d['ready'])}/{POOL_SIZE})")
        else: print(f"LỖI {nm}: Android không lên — sẽ dựng lại lần sau")
    finally: lk.__exit__()

def _roles(v):
    """Vai trò từng máy trong giả lập → {số: tên vai trò}; None = máy THỪA (VD bản nhân bản hỏng, máy dựng sẵn mồ côi, cp_… không có trong danh sách)."""
    mine = {p["name"] for p in load()["phones"]}; d = _pl(); spares = set(d.get("ready", [])) | set(d.get("building", []))
    tnames = {tpl_name(x) for x in ANDROIDS} | ({CONF.get("MEMU_TEMPLATE", "")} - {""})
    first = {}
    for i, x in sorted(v.items()):
        nm = x["name"]
        if (nm in tnames or nm.startswith("tpl_")) and nm not in first: first[nm] = i      # trùng tên máy mẫu → máy số nhỏ nhất là máy mẫu thật
    out = {}
    for i, x in sorted(v.items()):
        nm = x["name"]
        if nm in mine: out[i] = "máy khách"
        elif first.get(nm) == i: out[i] = "máy mẫu"
        elif nm in spares: out[i] = "máy dựng sẵn"
        elif i == 0: out[i] = "máy gốc"
        elif not _ours(nm): out[i] = "máy riêng (không đụng)"
        else: out[i] = None
    return out
def cmd_strays(a):
    """strays          : liệt kê mọi máy trong giả lập + vai trò; máy THỪA = không phải máy khách / máy mẫu / máy dựng sẵn / máy gốc #0
       strays --remove : xoá các máy THỪA (tắt rồi xoá từng máy, số lớn trước, đọc lại danh sách sau mỗi lần xoá)"""
    lk = _Lock("memu", wait=180)
    try: lk.__enter__()
    except RuntimeError: print(f"{EMU_NAME} đang bận tạo máy — chạy lại sau ít phút."); sys.exit(1)
    try:
        gone, fail = 0, {}
        for rnd in range(40):
            if _creating_now(): print("Đang có đơn tạo máy khách — chạy lại sau ít phút."); sys.exit(1)
            v = vms_sure()
            if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME}."); sys.exit(4)
            ro = _roles(v); bad = [i for i in sorted(v) if ro[i] is None]
            if rnd == 0:
                print(f"{EMU_NAME}: {len(v)} máy · {len(bad)} máy THỪA")
                av_ = {k: _mumu_major(x) for k, x in _mumu_info().items()} if EMU == "mumu" else {}
                for i in sorted(v): print(f"  #{i} {v[i]['name']} — {ro[i] or 'THỪA'}{(' · Android ' + av_[i]) if av_.get(i) else ''}{' · đang chạy' if v[i]['running'] else ''}")
                if not bad: print("✓ Không có máy thừa."); return
                if not a.remove: print("→ Xoá các máy THỪA:  python phonectl.py strays --remove"); return
            if not bad: break
            i = bad[-1]; nm = v[i]["name"]
            if fail.get((i, nm), 0) >= 2: print(f"   ✗ KHÔNG xoá được #{i} {nm} — tắt bằng tay trong {EMU_NAME} rồi chạy lại"); break
            print(f"XOA_THUA #{i} {nm}", flush=True)
            if v[i]["running"]:
                memuc("stop", "-i", i, timeout=120)
                for _ in range(20):
                    x = vms().get(i)
                    if not x or x["name"] != nm or not x["running"]: break
                    time.sleep(3)
            x = vms().get(i)
            if not x or x["name"] != nm: continue                 # số máy đã đổi → đọc lại danh sách, không đụng máy khác
            memuc("remove", "-i", i, timeout=180)
            x = vms().get(i)
            if x and x["name"] == nm: fail[(i, nm)] = fail.get((i, nm), 0) + 1; time.sleep(3)
            else: gone += 1; _vmdata_rm_if_gone(nm)
        print(f"Đã xoá {gone} máy thừa.")
    finally: lk.__exit__()

def cmd_noop(a): print("(bản Windows: không cần lệnh này)")
def cmd_perfset(a):
    """MuMu: bật "giữ app chạy nền", tắt "tự hạ FPS", bắt dùng card rời… (MUMU_PERF) cho máy mẫu + máy dựng sẵn + máy khách ĐANG TẮT
       (MuMu chỉ cho ghi khi máy tắt). Máy đang chạy tự ăn ở lần bật kế tiếp (lệnh start ghi trước khi bật). Máy riêng của chủ máy: không đụng."""
    if EMU != "mumu" or not MUMU_PERF: print("PERFSET bỏ qua (máy chủ không chạy MuMu)"); return
    info = _mumu_info()
    if not info: print("PERFSET lỗi: không đọc được danh sách máy MuMu"); sys.exit(4)
    ok = same = fail = 0; need = []
    for i, v in sorted(info.items()):
        nm = str(v.get("name", ""))
        if not (nm.startswith(("cp_", "spare_", "tpl_")) or nm in {tpl_name(x) for x in ANDROIDS}): continue
        cur = _mumu_json(_mumurun(["setting", "-v", i, "-a"], 60).stdout) or {}
        want = {k: val for k, val in MUMU_PERF.items() if k in cur and str(cur.get(k)).strip().lower() != val}
        if not want: same += 1; continue
        if _mumu_running(v):
            if nm.startswith("cp_"): need.append(nm)
            continue
        try:
            with _Lock("memu", wait=180):                  # không ghi chồng lúc đang nhân bản máy mẫu / dựng máy sẵn
                v2 = _mumu_info().get(i) or {}
                if str(v2.get("name", "")) != nm or _mumu_running(v2): continue
                _mumu_perf(i)
        except RuntimeError: fail += 1; print(f"  ✗ #{i} {nm}: MuMu đang bận — lần sau", flush=True); continue
        cur2 = _mumu_json(_mumurun(["setting", "-v", i, "-a"], 60).stdout) or {}
        bad = [k for k, val in want.items() if str(cur2.get(k)).strip().lower() != val]
        if bad: fail += 1; print(f"  ✗ #{i} {nm}: chưa ghi được {', '.join(bad)}", flush=True)
        else: ok += 1
    print(f"PERFSET sửa {ok} máy đang tắt · {same} máy đúng sẵn · {fail} máy lỗi · {len(need)} máy khách đang chạy sẽ tự ăn khi khởi động lại"
          + (f": {' '.join(need)}" if need else ""))
def cmd_render(a):
    """Đổi chế độ vẽ của 1 máy: opengl | directx (khởi động lại máy ~1 phút)."""
    st, p = _need(a.name); m = {"opengl": 0, "directx": 1}[a.mode]
    _pre_slot(p)                                              # 16/11e
    with _cycle():
        _restart_mark(p.get("name")); adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
        memuc("setconfigex", "-i", IDX(p), "graphics_render_mode", m, timeout=60)
        start_phone(p)
    ok = wait_boot(a.name, p["port"], apps=False)
    print(f"✅ '{a.name}' → vẽ bằng {a.mode.upper()}" + ("" if ok else " (đang kết nối lại)"))
def cmd_gfxget(a):
    """In chế độ vẽ hiện tại của máy: opengl | directx."""
    st, p = _need(a.name)
    o = (memuc("getconfigex", "-i", IDX(p), "graphics_render_mode", timeout=30).stdout or "")
    m = re.search(r"Value:\s*(\d)", o)
    print("GFX=" + ("opengl" if m and m.group(1) == "0" else "directx" if m else "unknown"))
def cmd_wallpaper(a):
    v = vms()
    for p in load()["phones"]:
        if (a.all or p["name"] == a.name) and is_running(p["name"], p, v):
            adb_connect(p["port"]); set_wallpaper(p["name"], p["port"], force=a.force)
    print("Xong.")
def cmd_template(a):
    """template           : xem máy mẫu + các cài đặt sẽ chép
       template TÊN       : đặt máy mẫu (tên máy trong Multiple Instance Manager)
       template --apply   : chép cài đặt máy mẫu cho MỌI máy khách (có hiệu lực sau khi máy khởi động lại)"""
    global CONF
    if a.name:
        if not any(x["name"] == a.name for x in vms().values()): print(f"LỖI: không thấy máy '{a.name}' trong MEmu."); sys.exit(1)
        lines = [l for l in open(CONF_F, encoding="utf-8").read().splitlines() if not l.startswith("MEMU_TEMPLATE=")] if os.path.isfile(CONF_F) else []
        open(CONF_F, "w", encoding="utf-8").write("\n".join(lines + [f"MEMU_TEMPLATE={a.name}"]) + "\n")
        CONF = _conf()
    props = template_props()
    print(f"Máy mẫu: {CONF.get('MEMU_TEMPLATE') or '(chưa đặt)'} — {len(props)} cài đặt sẽ chép cho máy mới:")
    for k, v in sorted(props.items()): print(f"   {k} = {v}")
    if a.apply:
        for p in load()["phones"]:
            i = IDX(p)
            if i is not None: apply_template(i, quiet=True); print(f"   ✓ {p['name']}")
        print("Xong — máy khách nhận cài đặt mới sau lần khởi động lại kế tiếp.")
def cmd_show(a): print(f"Hiện {hide_window(a.name, show=True)} cửa sổ của '{a.name}'.")
def cmd_hide(a):
    n = 0
    for p in load()["phones"]:
        if not a.name or p["name"] == a.name: n += hide_window(p["name"])
    print(f"Đã cho {n} cửa sổ {EMU_NAME} chạy ngầm.")

def cmd_mktpl(a):
    """mktpl 15 : MuMu — tạo máy mẫu tpl_a15 bằng lệnh (khỏi mở giao diện MuMu). MuMu tạo máy mới = bản Android MẶC ĐỊNH của
       MuMu; ra đúng bản thì đổi tên thành máy mẫu (để TẮT), sai bản thì xoá ĐÚNG máy vừa tạo và báo tạo bằng tay."""
    ver = str(a.android or "").split(".")[0].strip()
    if EMU != "mumu" or not MEMU: print("LỖI: lệnh này chỉ dùng cho máy chủ MuMu (EMU=mumu)."); sys.exit(1)
    if not ver.isdigit(): print("LỖI: cách dùng: phonectl.py mktpl 15"); sys.exit(1)
    tn = tpl_name(ver); cur = vms_sure()
    if not cur: print("LỖI: không đọc được danh sách máy MuMu — thử lại sau."); sys.exit(1)
    have = [i for i, x in cur.items() if x["name"] == tn]
    if have:
        got = _mumu_major(_mumu_info().get(have[0]))
        print(f"Đã có máy mẫu {tn} (#{have[0]}, Android {got or '?'}) — không tạo thêm."); return
    print(f"Đang tạo máy Android mới trong MuMu (1–3 phút)…", flush=True)
    r = memuc("create", ver, timeout=600)                     # _mumu: không có máy mẫu → MuMu tạo mới; sai bản → xoá đúng máy đó
    m = re.search(r"index\D*(\d+)", r.stdout or "")
    if r.returncode not in (0, None) or not m:
        print("LỖI: " + ((r.stdout or "") + " " + (r.stderr or "")).strip()[-400:])
        print(f"→ Tạo bằng tay: trong trình quản lý nhiều máy của MuMu tạo 1 máy Android {ver}, đổi tên thành {tn}, để TẮT."); sys.exit(1)
    idx = m.group(1)
    memuc("rename", "-i", idx, tn, timeout=120)
    after = vms()
    if (after.get(int(idx)) or {}).get("name") != tn:
        print(f"LỖI: đã tạo máy #{idx} (Android {ver}) nhưng chưa đổi được tên thành {tn} — đổi tên bằng tay trong MuMu."); sys.exit(1)
    if (after.get(int(idx)) or {}).get("running"): memuc("stop", "-i", idx, timeout=120)
    print(f"✓ Đã tạo máy mẫu {tn} (#{idx}, Android {ver}). Máy mẫu để TẮT — đơn Android {ver} sẽ nhân bản máy này.")

def cmd_engine(a):
    """Cho cloudphoned biết máy chủ này chạy giả lập gì + bán bản Android nào (JSON 1 dòng).
       Chỉ báo bản Android TẠO ĐƯỢC THẬT: MEmu bản có sẵn (5/7/9) hoặc có máy mẫu tpl_aN · MuMu bản mặc định hoặc có máy mẫu.
       (VD khai ANDROIDS=7,12 mà chưa tạo máy mẫu tpl_a12 → chỉ báo 7 → web không bán Android 12 ở máy chủ này, khỏi tạo hỏng rồi hoàn tiền.)"""
    av, miss = list(ANDROIDS), []
    if EMU in ("memu", "mumu") and MEMU:
        try:
            names = {x["name"] for x in vms().values()}
            info = _mumu_info() if EMU == "mumu" else {}
            mdef = _mumu_major(info.get(0))                                      # MuMu: bản Android của máy gốc #0 = bản MuMu tạo mới mặc định
            tver = {str(x.get("name", "")): _mumu_major(x) for x in info.values()}  # MuMu: máy mẫu phải ĐÚNG bản (tpl_a12 mà là Android 15 → không tính)
            ok = [v for v in ANDROIDS if (tpl_name(v) in names and tver.get(tpl_name(v), "") in (v, "")) or (EMU == "memu" and v in MEMU_CODES) or (EMU == "mumu" and v == mdef)]
            miss = [v for v in ANDROIDS if v not in ok]
            if ok or names: av = ok                       # đọc được danh sách → chỉ báo bản tạo được thật (có thể rỗng = chưa bán gì)
        except Exception: pass
    print(json.dumps({"emu": EMU, "androids": av, "default": DEF_ANDROID, "found": bool(MEMU), "missing_tpl": [tpl_name(v) for v in miss]}))

def cmd_probe(a):
    """In thông tin giả lập để kiểm tra / gửi hỗ trợ khi cài máy chủ mới."""
    print(f"Giả lập: {EMU_NAME} (EMU={EMU}) · thư mục: {MEMU or 'KHÔNG THẤY'}" + (f" · lệnh: {MUMU_CLI}" if EMU == "mumu" else ""))
    print(f"Bản Android bán ở máy chủ này: {', '.join(ANDROIDS)} (mặc định {DEF_ANDROID}) · máy mẫu: {', '.join(tpl_name(x) for x in ANDROIDS)}")
    print(f"1 máy tối đa: {MAX_RAM:g}GB RAM · {MAX_CPU} nhân (đổi bằng MEMU_MAX_RAM / MEMU_MAX_CPU trong cloudphone.conf)")
    v = vms(); print(f"Có {len(v)} máy:"); ro = _roles(v)
    for i, x in sorted(v.items()): print(f"  #{i} {x['name']} {'đang chạy' if x['running'] else 'tắt'} · cổng adb {port_of(i)} · {ro[i] or 'THỪA (xoá: phonectl strays)'}")
    names = {x["name"] for x in v.values()}
    if EMU != "ld":
        for ver in ANDROIDS:
            print(f"Máy mẫu Android {ver} ({tpl_name(ver)}): " + ("CÓ ✓" if tpl_name(ver) in names else "CHƯA CÓ ✗ — tạo 1 máy Android " + ver + f" trong {EMU_NAME} rồi đổi tên thành {tpl_name(ver)}"))
    mine = [q["name"] for q in load()["phones"]]
    lost = [n for n in mine if n not in names]
    print(f"Máy khách trong danh sách: {len(mine)}" + (f" · KHÔNG THẤY trong {EMU_NAME}: {', '.join(lost)}" if lost else " · đều thấy trong giả lập ✓"))
    if EMU == "mumu":
        r = _mumurun(["info", "-v", "all"], 60); print("--- MuMu info ---"); print((r.stdout or r.stderr or "")[:3000])
        if v:
            i0 = sorted(v)[0]; r = _mumurun(["setting", "-v", i0, "-a"], 60); print(f"--- MuMu setting máy #{i0} ---"); print((r.stdout or r.stderr or "")[:4000])

SECRET_KEYS = {"SUPABASE_SERVICE_KEY", "CF_DNS_TOKEN", "TELEGRAM_TOKEN", "TG_TOKEN", "SEPAY_API_KEY", "WEBHOOK_SECRET"}
def cmd_setconf(a):
    """setconf KHOÁ=GIÁ_TRỊ …  → sửa / thêm dòng trong cloudphone.conf, giữ nguyên các dòng khác (kể cả khoá bí mật).
       Chép bản cũ ra cloudphone.conf.bak trước khi sửa. Không nhận khoá bí mật (khoá dán bằng nút trong bảng)."""
    want = {}
    for kv in a.pairs:
        if "=" not in kv: print(f"LỖI: '{kv}' phải viết dạng KHOÁ=GIÁ_TRỊ"); sys.exit(1)
        k, v = kv.split("=", 1); k = k.strip().upper(); v = v.strip().strip('"').strip("'")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,40}", k): print(f"LỖI: tên khoá '{k}' không hợp lệ"); sys.exit(1)
        if k in SECRET_KEYS: print(f"LỖI: {k} là khoá bí mật — dán bằng nút trong bảng điều khiển, không gõ ở đây"); sys.exit(1)
        if re.search(r"[\r\n]", v): print(f"LỖI: giá trị của {k} không được xuống dòng"); sys.exit(1)
        want[k] = v
    if not want: print("Cách dùng: python phonectl.py setconf EMU=mumu ANDROIDS=12,15 MEMU_MAX_RAM=16 MEMU_MAX_CPU=32"); sys.exit(1)
    data = open(CONF_F, "rb").read() if os.path.isfile(CONF_F) else b""
    bom = data[:3] == b"\xef\xbb\xbf"; raw = data[3 if bom else 0:].decode("utf-8", errors="replace")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines, done = [], set()
    for l in raw.splitlines():
        k = l.split("=", 1)[0].strip()
        if "=" in l and not l.lstrip().startswith("#") and k in want:
            if k in done: continue                                   # dòng trùng → bỏ (giữ 1 dòng)
            l = f"{k}={want[k]}"; done.add(k)
        lines.append(l)
    lines += [f"{k}={v}" for k, v in want.items() if k not in done]
    out = (b"\xef\xbb\xbf" if bom else b"") + (nl.join(lines) + nl).encode("utf-8")
    if data: open(CONF_F + ".bak", "wb").write(data)
    try:
        open(CONF_F + ".tmp", "wb").write(out); os.replace(CONF_F + ".tmp", CONF_F)
    except PermissionError:                                          # file đang được chương trình khác mở → ghi thẳng
        open(CONF_F, "wb").write(out)
        try: os.remove(CONF_F + ".tmp")
        except OSError: pass
    for k, v in want.items(): print(f"✓ {k}={v}")
    print("Xong. Trong bảng bấm ■ Tắt tất cả → ▶ Bật tất cả để dùng cấu hình mới.")

def main():
    ap = argparse.ArgumentParser(); s = ap.add_subparsers(dest="c", required=True)
    sc = s.add_parser("setconf"); sc.add_argument("pairs", nargs="*"); sc.set_defaults(f=cmd_setconf)
    c = s.add_parser("create"); c.add_argument("name"); c.add_argument("--ram", type=float, default=2); c.add_argument("--cpu", type=float, default=2)
    c.add_argument("--days", type=int, default=7); c.add_argument("--res", default="720x1280"); c.add_argument("--dpi", type=int, default=0)
    c.add_argument("--fps", type=int, default=30); c.add_argument("--nowait", action="store_true"); c.add_argument("--android", default="9")
    c.add_argument("--nogpu", action="store_true"); c.add_argument("--until", default="")
    c.add_argument("--disk", type=int, default=0)                    # 19/11: bộ nhớ /data (GB) web đã tính — 0 = theo bậc RAM (DISK_TIERS)
    c.set_defaults(f=cmd_create)
    for nm, fn in (("delete", cmd_delete), ("forget", cmd_forget), ("stop", cmd_stop), ("start", cmd_start), ("restart", cmd_restart), ("show", cmd_show)):
        x = s.add_parser(nm); x.add_argument("name"); x.set_defaults(f=fn)
        if nm == "restart": x.add_argument("--force", action="store_true")      # tắt hẳn (treo thì tắt cưỡng bức) rồi bật lại
    r = s.add_parser("renew"); r.add_argument("name"); r.add_argument("--days", type=int, default=7)
    r.add_argument("--base", default=""); r.set_defaults(f=cmd_renew)      # --base: hạn hiện tại trên web (ISO) → cộng từ hạn muộn hơn
    z = s.add_parser("resize"); z.add_argument("name"); z.add_argument("--ram", type=float, default=0); z.add_argument("--cpu", type=float, default=0); z.set_defaults(f=cmd_resize)
    w = s.add_parser("waitboot"); w.add_argument("name"); w.add_argument("--noapps", action="store_true"); w.set_defaults(f=cmd_waitboot)
    ks = s.add_parser("ksfix"); ks.add_argument("names", nargs="*"); ks.add_argument("--all", action="store_true")
    ks.add_argument("--chi-kiem", dest="chi_kiem", action="store_true"); ks.add_argument("--cho", type=int, default=300)
    ks.add_argument("--bat", action="store_true"); ks.set_defaults(f=cmd_ksfix)
    kh = s.add_parser("khammay"); kh.add_argument("names", nargs="*"); kh.add_argument("--all", action="store_true"); kh.set_defaults(f=cmd_khammay)   # 17/11g
    tt = s.add_parser("tattieng"); tt.add_argument("--bat", action="store_true"); tt.set_defaults(f=cmd_tattieng)                                     # 17/11h
    bn = s.add_parser("bonho"); bn.add_argument("names", nargs="*"); bn.add_argument("--sua", action="store_true"); bn.add_argument("--gb", type=int, default=0)
    bn.set_defaults(f=cmd_bonho)                                                                                               # 18/11b · 19/11 --gb
    dk = s.add_parser("disk"); dk.add_argument("name"); dk.add_argument("--gb", type=int, required=True); dk.set_defaults(f=cmd_disk)   # 19/11
    g = s.add_parser("reconfig"); g.add_argument("name"); g.add_argument("--fps", type=int, default=0); g.add_argument("--res", default=""); g.set_defaults(f=cmd_reconfig)
    lr = s.add_parser("liveres"); lr.add_argument("name"); lr.add_argument("--res", required=True); lr.set_defaults(f=cmd_liveres)
    pi = s.add_parser("preinstall"); pi.add_argument("name", nargs="?", default=""); pi.add_argument("--all", action="store_true"); pi.add_argument("--force", action="store_true"); pi.set_defaults(f=cmd_preinstall)
    rf = s.add_parser("rootfix"); rf.add_argument("name", nargs="?", default=""); rf.add_argument("--all", action="store_true"); rf.add_argument("--force", action="store_true"); rf.set_defaults(f=cmd_rootfix)
    kp = s.add_parser("ksuprobe"); kp.add_argument("name"); kp.set_defaults(f=cmd_ksuprobe)
    rc = s.add_parser("rootcfg"); rc.add_argument("name"); g_ = rc.add_mutually_exclusive_group(required=True)
    g_.add_argument("--get", action="store_true"); g_.add_argument("--set", action="store_true")
    rc.add_argument("--on", action="store_true"); rc.add_argument("--off", action="store_true"); rc.add_argument("--apps", default=""); rc.set_defaults(f=cmd_rootcfg)
    px = s.add_parser("proxy"); px.add_argument("name"); g_ = px.add_mutually_exclusive_group(required=True)
    for k_ in ("--get", "--set", "--off", "--again"): g_.add_argument(k_, action="store_true")
    px.add_argument("--url", default=""); px.add_argument("--url-stdin", action="store_true")
    px.add_argument("--kind", default="auto", choices=["auto", "socks5", "http"]); px.set_defaults(f=cmd_proxy)
    pk = s.add_parser("proxykeep"); pk.add_argument("name", nargs="?", default=""); pk.add_argument("--all", action="store_true"); pk.add_argument("--wait", action="store_true")
    pk.set_defaults(f=cmd_proxykeep)
    gg = s.add_parser("gfxget"); gg.add_argument("name"); gg.set_defaults(f=cmd_gfxget)
    rd = s.add_parser("render"); rd.add_argument("name"); rd.add_argument("mode", choices=["opengl", "directx"]); rd.set_defaults(f=cmd_render)
    wp = s.add_parser("wallpaper"); wp.add_argument("name", nargs="?", default=""); wp.add_argument("--all", action="store_true"); wp.add_argument("--force", action="store_true"); wp.set_defaults(f=cmd_wallpaper)
    tp = s.add_parser("template"); tp.add_argument("name", nargs="?", default=""); tp.add_argument("--apply", action="store_true"); tp.set_defaults(f=cmd_template)
    hd = s.add_parser("hide"); hd.add_argument("name", nargs="?", default=""); hd.set_defaults(f=cmd_hide)
    he = s.add_parser("heal"); he.add_argument("--orphans", action="store_true"); he.set_defaults(f=cmd_heal)
    il = s.add_parser("idle"); il.add_argument("--min", type=float, default=None); il.add_argument("--dry", action="store_true")
    il.add_argument("--gio", type=float, default=None)          # 18/11a: số giờ không ai mở máy + không có việc (mặc định IDLE_STOP_H = 18)
    il.add_argument("--verbose", "-v", action="store_true"); il.set_defaults(f=cmd_idle)
    sl = s.add_parser("sleep"); sl.add_argument("name"); sl.add_argument("--force", action="store_true"); sl.set_defaults(f=cmd_sleep)
    wk = s.add_parser("wake"); wk.add_argument("name", nargs="?", default=""); wk.add_argument("--all", action="store_true"); wk.set_defaults(f=cmd_wake)
    cl = s.add_parser("cleanup"); cl.add_argument("--all", action="store_true"); cl.add_argument("--yes", action="store_true"); cl.set_defaults(f=cmd_cleanup)
    s.add_parser("pool").set_defaults(f=cmd_pool)
    s.add_parser("probe").set_defaults(f=cmd_probe)
    sy = s.add_parser("strays"); sy.add_argument("--remove", action="store_true"); sy.set_defaults(f=cmd_strays)
    s.add_parser("engine").set_defaults(f=cmd_engine)
    qy = s.add_parser("quyen"); qy.add_argument("--sua", action="store_true"); qy.set_defaults(f=cmd_quyen)      # 17/11e: lẫn quyền Admin
    s.add_parser("perfset").set_defaults(f=cmd_perfset)
    s.add_parser("ramcheck").set_defaults(f=cmd_ramcheck)
    dd = s.add_parser("dondep"); dd.add_argument("--xoa", action="store_true"); dd.set_defaults(f=cmd_dondep)
    s.add_parser("nhanlai").set_defaults(f=cmd_nhanlai)
    rf = s.add_parser("ramfix"); rf.add_argument("names", nargs="*"); rf.add_argument("--all", action="store_true"); rf.set_defaults(f=cmd_ramfix)
    mt = s.add_parser("mktpl"); mt.add_argument("android"); mt.set_defaults(f=cmd_mktpl)
    s.add_parser("tuneall").set_defaults(f=cmd_tuneall)
    s.add_parser("vmlist").set_defaults(f=cmd_vmlist)
    s.add_parser("ldbase").set_defaults(f=cmd_ldbase)
    ba = s.add_parser("bootall"); ba.add_argument("--quiet", action="store_true"); ba.add_argument("--only", default=""); ba.set_defaults(f=cmd_bootall)
    b1 = s.add_parser("boot1"); b1.add_argument("name"); b1.set_defaults(f=cmd_boot1)                   # 17/11f: lệnh con của bootall
    te = s.add_parser("tatem"); te.add_argument("--wait", type=int, default=90); te.set_defaults(f=cmd_tatem)   # 17/11f: tắt êm mọi máy trước khi khởi động lại Windows
    si = s.add_parser("serverinfo"); si.set_defaults(f=cmd_serverinfo)
    rs = s.add_parser("rebootserver"); rs.add_argument("--anyway", action="store_true"); rs.add_argument("--wait", type=int, default=120)
    rs.add_argument("--delay", type=int, default=15); rs.set_defaults(f=cmd_rebootserver)
    for nm, fn in (("connect-all", cmd_connect_all), ("reap", cmd_reap), ("perms", cmd_perms), ("capacity", cmd_capacity), ("list", cmd_list),
                   ("memfix", cmd_noop), ("boost", cmd_noop), ("gpuinfo", cmd_noop)):
        s.add_parser(nm).set_defaults(f=fn)
    a = ap.parse_args()
    global PRIO
    PRIO = a.f in (cmd_create, cmd_wake, cmd_restart, cmd_waitboot, cmd_resize, cmd_reconfig, cmd_ramfix, cmd_renew, cmd_render, cmd_rootcfg) \
        or (a.f is cmd_rootfix and not getattr(a, "all", False))   # khách / admin đang chờ (16/11e: + đổi chế độ vẽ, root theo app, root 1 máy)
    a.f(a)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
