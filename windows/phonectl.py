# -*- coding: utf-8 -*-
# =====================================================================
#  phonectl.py — BẢN WINDOWS: LDPlayer 9 (Android 9) · MuMu (Android 12 / 7) · MEmu. Mỗi máy chủ chạy 1 loại (cloudphone.conf EMU=).
#   Cùng câu lệnh với bản Ubuntu để cloudphoned.py / cpapi.py dùng y nguyên.
#   python phonectl.py probe        ← in thông tin giả lập (gửi hỗ trợ khi cài máy chủ MuMu/MEmu mới)
#   python phonectl.py create TÊN --ram 4 --cpu 4 --days 7 [--res 720x1280] [--nowait]
#   python phonectl.py list | capacity | delete TÊN | stop TÊN | start TÊN | restart TÊN | renew TÊN --days N
#   python phonectl.py resize TÊN --ram 6 --cpu 6 | waitboot TÊN | connect-all | reap | rootfix --all
#  Máy số N của MEmu ⇄ adb 127.0.0.1:(21503 + 10·N)
# =====================================================================
import argparse, ctypes, datetime, glob, hashlib, json, os, re, shutil, subprocess, sys, time

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
def _unstick_memuc():
    """Khoá memuc bị giữ quá lâu (1 lệnh memuc treo) → tắt các memuc.exe đang treo + gỡ khoá, để đơn khách không bị huỷ."""
    if _long_busy():          # đang nhân bản / tạo máy cho khách (hợp lệ, vài phút) → CHỜ, không tắt (tắt giữa chừng = máy hỏng + đơn lỗi)
        t0 = time.time()
        while _long_busy() and time.time() - t0 < 600: time.sleep(3)
        return
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
def _mumu_perf(idx):
    """Ghi MUMU_PERF cho 1 máy MuMu (máy phải đang tắt). Trả số khoá vừa ghi (0 = đã đúng sẵn)."""
    cur = _mumu_json(_mumurun(["setting", "-v", idx, "-a"], 60).stdout) or {}
    want = {k: val for k, val in MUMU_PERF.items() if k in cur and str(cur.get(k)).strip().lower() != val}
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
        ver = a[1] if len(a) > 1 else DEF_ANDROID
        L0 = _mumu_list()
        if not L0:                                        # không đọc được danh sách → KHÔNG tạo (đọc sau sẽ tưởng mọi máy có sẵn là máy mới → nhận nhầm máy của chủ)
            return subprocess.CompletedProcess([], 1, "", "không đọc được danh sách máy MuMu — chưa tạo máy")
        before = set(L0); tpl = next((i for i, x in L0.items() if x["name"] == tpl_name(ver)), None)
        r = _mumurun(["clone", "-v", tpl], timeout) if tpl is not None else _mumurun(["create"], timeout)
        new = []
        for _ in range(40):                               # máy mới có thể hiện trễ vài giây
            L1 = _mumu_list()
            new = sorted(set(L1) - before) if L1 else []
            if new: break
            time.sleep(3)
        if len(new) != 1:                                 # 0 hoặc nhiều hơn 1 máy "mới" → không chắc máy nào là của mình → không dùng
            return subprocess.CompletedProcess([], 1, r.stdout, (r.stderr or "") + f" MuMu không tạo được đúng 1 máy (thấy {len(new)} máy mới)")
        got = _mumu_major(_mumu_info().get(new[0]))      # MuMu 6 tạo mới mặc định Android 15 → khách mua bản khác phải nhân bản máy mẫu đúng bản
        if got and got != str(ver):
            _mumurun(["delete", "-v", new[0]], timeout)  # đúng 1 máy vừa tạo (đã kiểm ở trên) → xoá, không giao nhầm bản cho khách
            return subprocess.CompletedProcess([], 1, r.stdout, f"MuMu tạo ra Android {got}, không phải Android {ver} — cần máy mẫu {tpl_name(ver)} (Android {ver})")
        return _ok(f"index: {new[0]}")
    if c == "rename":
        r = _mumurun(["rename", "-v", ix(), "-n", a[-1]], timeout)
        if (_mumu_list().get(int(ix())) or {}).get("name") != a[-1]: r = _mumurun(["rename", "--vmindex", ix(), "--name", a[-1]], timeout)
        return r
    if c == "start":
        if MUMU_PERF and not running(ix()):
            try: _mumu_perf(ix())                         # giữ app chạy nền / không tự hạ FPS / card rời — ghi lúc máy đang tắt
            except Exception: pass
        r = _mumurun(["control", "-v", ix(), "launch"], timeout)
        for _ in range(15):
            if running(ix()): return _ok("start ok")
            time.sleep(2)
        return subprocess.CompletedProcess([], 1, r.stdout, "start vm failed")
    if c == "stop":
        _mumurun(["control", "-v", ix(), "shutdown"], timeout)
        for _ in range(20):
            if not running(ix()): break
            time.sleep(2)
        return _ok("stop ok")
    if c == "stopall": return _mumurun(["control", "-v", "all", "shutdown"], timeout)
    if c == "remove":
        if int(ix()) not in _mumu_list(): return subprocess.CompletedProcess([], 1, "", f"MuMu không có máy #{ix()} — không xoá")
        r = _mumurun(["delete", "-v", ix()], timeout)
        return _ok("remove ok") if int(ix()) not in _mumu_list() else subprocess.CompletedProcess([], 1, r.stdout, "remove failed")
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
def memuc(*a, timeout=300):
    """memuc chỉ xử lý 1 lệnh một lúc (chạy chồng → "read failed: 233") → xếp hàng bằng khoá + thử lại.
       memuc gặp số máy KHÔNG CÓ (VD "-i 7" khi không có máy 7, hay "-i None") thì làm NHẦM SANG MÁY #0 (đã thấy: rename -i 7 đổi tên máy #0)
       → chặn số máy sai ở đây; remove / rename còn kiểm tra máy số đó đang có trong listvms ngay trước khi chạy."""
    iv = None
    if "-i" in a:
        k = a.index("-i"); iv = str(a[k + 1]).strip() if k + 1 < len(a) else ""
        if not iv.isdigit():
            return subprocess.CompletedProcess([], 1, "", f"bỏ lệnh {a[0]}: số máy không hợp lệ ({iv or 'trống'}) — không chạy để khỏi làm nhầm máy #0")
    if EMU == "mumu":
        lk = _Lock("memuc", wait=min(max(120, timeout), 260))
        try: lk.__enter__()
        except RuntimeError: _unstick_memuc(); lk = _Lock("memuc", wait=60); lk.__enter__()
        try: return _mumu(a, timeout)
        finally: lk.__exit__()
    if EMU == "ld":
        lk = _Lock("memuc", wait=min(max(120, timeout), 260))
        try: lk.__enter__()
        except RuntimeError: _unstick_memuc(); lk = _Lock("memuc", wait=60); lk.__enter__()
        try: return _ld(a, timeout)
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
def load():
    try:
        with open(STATE, encoding="utf-8") as f: return json.load(f)
    except Exception: return {"phones": []}
def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
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
        adb("-s", s_, "shell", "su -c '" + sc + "; stop; sleep 2; start'", timeout=60)
    print(f"   🖼 {name}: đã đặt ảnh nền CloudBlue", flush=True)
    time.sleep(8)
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
    "app_keptlive": "false", "dynamic_adjust_frame_rate": "false", "force_discrete_graphics": "true", "vertical_sync": "false", "prevent_sleep": "true"}
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

def wait_boot(name, port, apps=True):
    t0 = time.time(); ok = False
    while time.time() - t0 < BOOT_WAIT:
        adb_connect(port)
        if booted(port): ok = True; break
        time.sleep(3)
    if ok:
        try: set_wallpaper(name, port)
        except Exception as e: print("   (ảnh nền lỗi:", e, ")")
        try: hide_window(name)
        except Exception: pass
        tune(name, port); grant_perms(name, port)
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
    tot, av = mem()
    need = min(float(a.ram), MAX_RAM)                     # MEmu chạy tối đa 16GB/máy → chỉ cần đủ RAM cho phần thật sự cấp
    if av - (need + 1) < RESERVE:
        print(f"HẾT HÀNG: RAM Windows còn {av:.1f}GB, máy {need:g}GB cần thêm {need + 1:g}GB và chừa {RESERVE:g}GB."); sys.exit(2)
    try: open(os.path.join(HOME, "redroid", f"creating_{os.getpid()}.flag"), "w").write(a.name)   # báo "đang tạo máy khách" → dựng máy sẵn nhường đường
    except OSError: pass
    ver = norm_android(a.android)
    sp = take_spare(a.name) if ver == DEF_ANDROID else None          # máy dựng sẵn là bản Android mặc định của máy chủ
    if sp is not None:
        idx = sp
        print(f"[1/4] ⚡ Dùng máy dựng sẵn (MEmu #{idx}) → đổi tên, RAM, CPU…", flush=True)
        with _Lock("memu"):
            dpi = a.dpi or auto_dpi(a.res)
            configure(idx, a.ram, a.cpu, a.res, dpi)
            memuc("setconfigex", "-i", idx, "fps", clamp_fps(a.fps), timeout=60)
            apply_template(idx)
    else:
        print(f"[1/4] Tạo máy Android {ver} trên {EMU_NAME}…", flush=True)
        with _Lock("memu"):
            for oi, ox in sorted(vms().items(), reverse=True):   # máy trùng tên còn sót trong MEmu (lần tạo trước bị ngắt) → xoá trước
                if ox["name"] == a.name:
                    print(f"   (xoá máy sót cùng tên #{oi})", flush=True); memuc("stop", "-i", oi, timeout=60); memuc("remove", "-i", oi, timeout=180)
            r, idx = create_vm(ver, a.name)
            if idx is None: print("LỖI tạo máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-300:]); sys.exit(4)
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
    st = load(); st["phones"].append(row); save(st)
    print(f"[3/4] Bật máy…", flush=True)
    s = memu_start(idx)
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
    return load(), rec(name)

def cmd_delete(a):
    st = load(); p = rec(a.name, st)
    if not p: print("Không có máy tên này."); sys.exit(1)
    v = vms_sure()
    if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME} — thử lại sau."); sys.exit(4)
    i = IDX(p, v)
    if i is None:                          # máy đã không còn trong MEmu → chỉ xoá khỏi danh sách
        st = load(); st["phones"] = [x for x in st["phones"] if x["name"] != a.name]; save(st)
        print(f"🗑️  '{a.name}' không còn trong MEmu — đã bỏ khỏi danh sách."); return
    adb("disconnect", serial(p), timeout=15)
    with _Lock("memu"):
        if EMU == "memu": i = IDX(p, vms_sure())        # số máy đọc lại NGAY trước khi xoá, dùng 1 số cho cả tắt + xoá
        r = None
        if i is not None:
            memuc("stop", "-i", i, timeout=120); time.sleep(3)
            r = memuc("remove", "-i", i, timeout=180)
    v2 = vms_sure()
    left = i is None or bool(v2 and any(x["name"] == a.name for x in v2.values()))
    st = load(); st["phones"] = [x for x in st["phones"] if x["name"] != a.name]; save(st)
    if left:                                         # không xoá được → báo, KHÔNG thử số máy khác
        why = "chưa đọc được số máy" if i is None else ((r.stdout or "") + (r.stderr or "")).strip()[-160:]
        print(f"⚠ Chưa xoá được '{a.name}' trong {EMU_NAME} ({why}) — máy còn lại sẽ hiện THỪA, xoá bằng: phonectl strays --remove")
    else:
        _vmdata_rm_if_gone(a.name)
        print(f"🗑️  Đã xoá máy '{a.name}' và toàn bộ dữ liệu.")

def cmd_forget(a):
    """forget TÊN: bỏ máy khỏi danh sách CHỈ KHI giả lập chắc chắn không còn máy đó (máy "ma") — không bao giờ xoá máy thật."""
    st = load(); p = rec(a.name, st)
    if not p: print("Không có máy tên này trong danh sách."); return
    v = vms_sure()
    if not v: print(f"LỖI: không đọc được danh sách máy của {EMU_NAME} — thử lại sau."); sys.exit(4)
    if any(x["name"] == a.name for x in v.values()): print(f"LỖI: '{a.name}' vẫn còn trong {EMU_NAME} — không bỏ khỏi danh sách."); sys.exit(3)
    st["phones"] = [x for x in st["phones"] if x["name"] != a.name]; save(st); _vmdata_rm(a.name)
    print(f"Đã bỏ '{a.name}' khỏi danh sách ({EMU_NAME} không còn máy này).")

def set_hold(name, on):
    """hold = máy CỐ Ý tắt (admin khoá / hết hạn) → bộ tự bật lại không đụng vào. Tắt ngoài ý muốn (bấm Close trong MEmu, MEmu văng) → tự bật lại."""
    st = load(); p = rec(name, st)
    if p and bool(p.get("hold")) != on: p["hold"] = on; save(st)
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
def start_phone(p):
    r = memu_start(IDX(p)); adb_connect(p["port"])
    if not _start_failed(r): set_hold(p["name"], False)
    return r
def cmd_start(a):
    st, p = _need(a.name); r = start_phone(p)
    if _start_failed(r): print("❌ MEmu không bật được máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); sys.exit(5)
    print("✅ Đã bật")
def cmd_restart(a):
    st, p = _need(a.name); adb("disconnect", serial(p), timeout=15)
    memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3); r = start_phone(p)
    if _start_failed(r): print("❌ MEmu không bật được máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); sys.exit(5)
    print("✅ Đã khởi động lại")

def cmd_waitboot(a):
    st, p = _need(a.name)
    if not is_running(a.name, p): start_phone(p)          # máy đang tắt (lần bật trước bị ngắt) → bật lại rồi mới chờ
    ok = wait_boot(a.name, p["port"], apps=not a.noapps)
    print("Android đã khởi động xong." if ok else "Chưa kết nối được, sẽ tự thử lại."); sys.exit(0 if ok else 5)

def cmd_renew(a):
    st, p = _need(a.name)
    base = parse_dt(p["expires"]); base = max(base, now()) + datetime.timedelta(days=a.days)
    p["expires"] = base.isoformat(); save(st)
    if not is_running(a.name, p): start_phone(p); wait_boot(a.name, p["port"], apps=False)
    print(f"🔄 '{a.name}' gia hạn +{a.days} ngày → hết hạn {fmt(base)}")

def cmd_resize(a):
    st, p = _need(a.name)
    ram = a.ram if a.ram > 0 else float(p["ram"]); cpu = a.cpu if a.cpu > 0 else float(p["cpu"])
    tot, av = mem()
    if ram > float(p["ram"]) and av - (ram - float(p["ram"])) < RESERVE: print("LỖI: RAM Windows không đủ để nâng."); sys.exit(4)
    adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
    configure(IDX(p), ram, cpu, p.get("res", "720x1280"), p.get("dpi"))
    fl = _fails()
    if fl.pop(a.name, None) is not None: _fails_put(fl)          # cấu hình mới → bỏ lịch "tạm không bật" do lỗi bật với cấu hình cũ
    start_phone(p); wait_boot(a.name, p["port"], apps=False)
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
        if was:
            adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", i, timeout=120); time.sleep(3)
        ok, msg = _mumu_hw(str(i), c, m)
        if not ok and was:                                       # máy bị bật lại giữa chừng (vòng tự bật của cloudphoned) → tắt lại, thử lần nữa
            memuc("stop", "-i", i, timeout=120); time.sleep(3); ok, msg = _mumu_hw(str(i), c, m)
        print(f"   {'✓' if ok else '✗'} {msg}", flush=True)
        if was:
            start_phone(p); wait_boot(name, p["port"], apps=False)
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
    adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
    configure(IDX(p), p["ram"], p["cpu"], res, dpi); start_phone(p); ok = wait_boot(a.name, p["port"], apps=False)
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

def cmd_rootfix(a):
    v = vms()
    for p in load()["phones"]:
        if not (a.all or p["name"] == a.name): continue
        if not is_running(p["name"], p, v): print(f"ROOT_SKIP {p['name']}: máy đang tắt"); continue
        o = (ashell(p["name"], "command -v su").stdout or "")
        if "su" not in o:
            memuc("setconfigex", "-i", IDX(p), "enable_su", 1, timeout=60)
            print(f"ROOT_WAIT {p['name']}: vừa bật root, khởi động lại máy để có hiệu lực")
        else: print(f"ROOT_OK {p['name']}: đã root — tool gọi su là chạy bằng quyền root")

def cmd_capacity(a):
    st = load(); tot, av = mem()
    print(f"Windows: RAM {tot:.1f} GB (còn trống {av:.1f} GB, chừa {RESERVE:g} GB) · CPU {os.cpu_count()} luồng · {EMU_NAME}: {MEMU or 'KHÔNG THẤY'}"
          f" · 1 máy tối đa {MAX_RAM:g}GB · {MAX_CPU} nhân")
    print(f"Đã cấp:  RAM {sum(float(p['ram']) for p in st['phones']):.1f} GB  ({len(st['phones'])} máy)")

def cmd_list(a):
    st = load(); v = vms()
    if not st["phones"]: print("(chưa có máy nào)"); return
    for p in st["phones"]:
        i = IDX(p, v); print(f"{p['name']:<16} #{'?' if i is None else i:<3} cổng {p['port']:<6} {p['ram']}G/{p['cpu']}  hết hạn {fmt(parse_dt(p['expires']))}  {'chạy' if is_running(p['name'], p, v) else 'tắt'}")

def cmd_bootall(a):
    """Sau khi Windows khởi động lại: bật lần lượt mọi máy khách CÒN HẠN đang tắt → chờ Android lên → nối điều khiển."""
    st = load(); v = vms(); todo = []
    for p in st["phones"]:
        if parse_dt(p["expires"]) < now() or p.get("hold"): continue
        if IDX(p, v) is None: print(f"⚠ {p['name']}: không còn trong MEmu (bấm ♻ Làm mới máy khách)"); continue
        if is_running(p["name"], p, v):
            if not a.quiet: adb_connect(p["port"]); print(f"✓ {p['name']}: đang chạy")
            continue
        todo.append(p)
    if a.quiet and not todo: return
    print(f"Cần bật {len(todo)} máy khách…", flush=True); bad = 0
    for p in todo:
        print(f"▶ Bật {p['name']}…", flush=True)
        r = start_phone(p)
        if _start_failed(r): print(f"✗ {p['name']}: MEmu không bật được"); bad += 1; continue
        ok = False; t0 = time.time()
        while time.time() - t0 < BOOT_WAIT:
            adb_connect(p["port"])
            if booted(p["port"]): ok = True; break
            time.sleep(3)
        if ok:
            tune(p["name"], p["port"]); grant_perms(p["name"])
            try: hide_window(p["name"])
            except Exception: pass
        print(f"✅ {p['name']}: sẵn sàng" if ok else f"✗ {p['name']}: Android chưa lên sau {BOOT_WAIT // 60} phút"); bad += 0 if ok else 1
    print(f"BOOTALL xong: {len(todo) - bad}/{len(todo)} máy bật thành công" + ("" if not bad else f", {bad} máy lỗi"))
    if bad: sys.exit(6)

# ---------- CHỐNG KẸT: máy chạy mà Android không lên (kẹt 99%, màn đen, adb offline) ----------
HEAL_F = os.path.join(HOME, "redroid", "heal.json")
STUCK_MIN = 6          # chạy quá 6 phút mà Android chưa lên → coi là kẹt
# Kẹt sau 2 lần khởi động lại → XOÁ máy + tạo lại máy mới (MẤT dữ liệu khách). MEmu mặc định TẮT (lỗi chung của giả lập —
# VD màn đen do cấu hình — sẽ xoá hàng loạt máy khách); bật lại: HEAL_DELETE=1 trong cloudphone.conf.
HEAL_DELETE = (CONF.get("HEAL_DELETE") or ("0" if EMU == "memu" else "1")).strip() == "1"
def _hl():
    try: return json.load(open(HEAL_F, encoding="utf-8"))
    except Exception: return {}
def _hs(d):
    os.makedirs(os.path.dirname(HEAL_F), exist_ok=True); json.dump(d, open(HEAL_F, "w", encoding="utf-8"))
def cmd_heal(a):
    """Gọi định kỳ (bảng BlueRoblox ~2 phút/lần): máy kẹt → khởi động lại; kẹt 3 lần liền → XOÁ máy hỏng (máy khách sẽ được tạo lại)."""
    st = load(); v = vms(); h = _hl(); t = time.time(); seen = set()
    for p in st["phones"]:
        nm = p["name"]; seen.add(nm)
        if p.get("hold") or IDX(p, v) is None or not is_running(nm, p, v): h.pop(nm, None); continue
        adb_connect(p["port"])
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
        e["tries"] += 1; e["since"] = t
        print(f"KHOI_DONG_LAI {nm}: Android không lên quá {STUCK_MIN} phút → khởi động lại (lần {e['tries']})", flush=True)
        adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3); start_phone(p)
    for k in list(h):
        if k not in seen: h.pop(k, None)
    _hs(h)
    if a.orphans: _cleanup(v, quiet=True)

def _ours(nm):
    """Máy do CloudBlue tạo? MuMu hay cài chung máy có sẵn máy riêng của chủ máy → chỉ đụng máy cp_… / spare_….
       LDPlayer / MEmu: máy chủ riêng → như cũ (mọi máy)."""
    return EMU != "mumu" or str(nm).startswith(("cp_", "spare_"))
def _cleanup(v=None, quiet=False, all_=False):
    """Xoá máy trong MEmu KHÔNG thuộc danh sách BlueRoblox (giả lập cũ / thừa / tạo dở). Giữ máy mẫu (MEMU_TEMPLATE)."""
    if quiet and _creating_now(): return                 # đang tạo máy khách → để lần sau
    v = v if v is not None else vms(); mine = {p["name"] for p in load()["phones"]}; tpl = CONF.get("MEMU_TEMPLATE", "")
    gone = 0
    for i in sorted(v, reverse=True):          # xoá từ số lớn xuống → số máy còn lại ít bị đổi
        nm = v[i]["name"]
        if nm == tpl or (nm in mine and not all_) or (nm.startswith("spare_") and not all_): continue
        if nm.startswith("tpl_") or nm in {tpl_name(x) for x in ANDROIDS}: continue      # máy MẪU từng bản Android — không bao giờ xoá
        if EMU in ("ld", "mumu") and i == 0: continue        # LDPlayer / MuMu: giữ máy gốc số 0 (giả lập cần)
        if not _ours(nm): continue                            # máy riêng của chủ máy (MuMu dùng chung máy) — không bao giờ đụng
        if quiet and not nm.startswith("cp_"): continue     # tự động: chỉ dọn máy do BlueRoblox tạo (cp_…)
        if quiet and (_creating_now() or nm in {p["name"] for p in load()["phones"]}): continue   # kiểm lại ngay trước khi xoá
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
        st = load(); st["phones"] = []; save(st)
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
        if _start_failed(memu_start(idx)): print(f"LỖI {nm}: không bật được"); return
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
    adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
    memuc("setconfigex", "-i", IDX(p), "graphics_render_mode", m, timeout=60)
    start_phone(p); ok = wait_boot(a.name, p["port"], apps=False)
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
    c.add_argument("--nogpu", action="store_true"); c.add_argument("--until", default=""); c.set_defaults(f=cmd_create)
    for nm, fn in (("delete", cmd_delete), ("forget", cmd_forget), ("stop", cmd_stop), ("start", cmd_start), ("restart", cmd_restart), ("show", cmd_show)):
        x = s.add_parser(nm); x.add_argument("name"); x.set_defaults(f=fn)
    r = s.add_parser("renew"); r.add_argument("name"); r.add_argument("--days", type=int, default=7); r.set_defaults(f=cmd_renew)
    z = s.add_parser("resize"); z.add_argument("name"); z.add_argument("--ram", type=float, default=0); z.add_argument("--cpu", type=float, default=0); z.set_defaults(f=cmd_resize)
    w = s.add_parser("waitboot"); w.add_argument("name"); w.add_argument("--noapps", action="store_true"); w.set_defaults(f=cmd_waitboot)
    g = s.add_parser("reconfig"); g.add_argument("name"); g.add_argument("--fps", type=int, default=0); g.add_argument("--res", default=""); g.set_defaults(f=cmd_reconfig)
    lr = s.add_parser("liveres"); lr.add_argument("name"); lr.add_argument("--res", required=True); lr.set_defaults(f=cmd_liveres)
    pi = s.add_parser("preinstall"); pi.add_argument("name", nargs="?", default=""); pi.add_argument("--all", action="store_true"); pi.add_argument("--force", action="store_true"); pi.set_defaults(f=cmd_preinstall)
    rf = s.add_parser("rootfix"); rf.add_argument("name", nargs="?", default=""); rf.add_argument("--all", action="store_true"); rf.add_argument("--force", action="store_true"); rf.set_defaults(f=cmd_rootfix)
    gg = s.add_parser("gfxget"); gg.add_argument("name"); gg.set_defaults(f=cmd_gfxget)
    rd = s.add_parser("render"); rd.add_argument("name"); rd.add_argument("mode", choices=["opengl", "directx"]); rd.set_defaults(f=cmd_render)
    wp = s.add_parser("wallpaper"); wp.add_argument("name", nargs="?", default=""); wp.add_argument("--all", action="store_true"); wp.add_argument("--force", action="store_true"); wp.set_defaults(f=cmd_wallpaper)
    tp = s.add_parser("template"); tp.add_argument("name", nargs="?", default=""); tp.add_argument("--apply", action="store_true"); tp.set_defaults(f=cmd_template)
    hd = s.add_parser("hide"); hd.add_argument("name", nargs="?", default=""); hd.set_defaults(f=cmd_hide)
    he = s.add_parser("heal"); he.add_argument("--orphans", action="store_true"); he.set_defaults(f=cmd_heal)
    cl = s.add_parser("cleanup"); cl.add_argument("--all", action="store_true"); cl.add_argument("--yes", action="store_true"); cl.set_defaults(f=cmd_cleanup)
    s.add_parser("pool").set_defaults(f=cmd_pool)
    s.add_parser("probe").set_defaults(f=cmd_probe)
    sy = s.add_parser("strays"); sy.add_argument("--remove", action="store_true"); sy.set_defaults(f=cmd_strays)
    s.add_parser("engine").set_defaults(f=cmd_engine)
    s.add_parser("perfset").set_defaults(f=cmd_perfset)
    s.add_parser("ramcheck").set_defaults(f=cmd_ramcheck)
    rf = s.add_parser("ramfix"); rf.add_argument("names", nargs="*"); rf.add_argument("--all", action="store_true"); rf.set_defaults(f=cmd_ramfix)
    mt = s.add_parser("mktpl"); mt.add_argument("android"); mt.set_defaults(f=cmd_mktpl)
    s.add_parser("tuneall").set_defaults(f=cmd_tuneall)
    s.add_parser("vmlist").set_defaults(f=cmd_vmlist)
    ba = s.add_parser("bootall"); ba.add_argument("--quiet", action="store_true"); ba.set_defaults(f=cmd_bootall)
    for nm, fn in (("connect-all", cmd_connect_all), ("reap", cmd_reap), ("perms", cmd_perms), ("capacity", cmd_capacity), ("list", cmd_list),
                   ("memfix", cmd_noop), ("boost", cmd_noop), ("gpuinfo", cmd_noop)):
        s.add_parser(nm).set_defaults(f=fn)
    a = ap.parse_args(); a.f(a)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
