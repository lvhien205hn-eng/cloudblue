# -*- coding: utf-8 -*-
# =====================================================================
#  phonectl.py — BẢN WINDOWS (MEmu Play). Cùng câu lệnh với bản Ubuntu để cloudphoned.py / cpapi.py dùng y nguyên.
#   python phonectl.py create TÊN --ram 4 --cpu 4 --days 7 [--res 720x1280] [--nowait]
#   python phonectl.py list | capacity | delete TÊN | stop TÊN | start TÊN | restart TÊN | renew TÊN --days N
#   python phonectl.py resize TÊN --ram 6 --cpu 6 | waitboot TÊN | connect-all | reap | rootfix --all
#  Máy số N của MEmu ⇄ adb 127.0.0.1:(21503 + 10·N)
# =====================================================================
import argparse, ctypes, datetime, json, os, re, subprocess, sys, time

HOME = os.environ.get("BLUE_HOME") or os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HOME, "redroid", "phones.json")
CONF_F = os.path.join(HOME, "cloudphone.conf")
ADB = os.path.join(HOME, "platform-tools", "adb.exe")
GRACE_MIN = 30
BOOT_WAIT = 300
SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")

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
            tree = ["/T"] if args[0].lower().endswith("memuc.exe") else []      # adb: KHÔNG /T (adb server có thể là "con" → chết theo)
            subprocess.run(["taskkill", "/PID", str(p.pid)] + tree + ["/F"], capture_output=True, creationflags=NOWIN)
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: pass
            code = 124
        fo.seek(0); fe.seek(0); out, err = fo.read(), fe.read()
    if text: out, err = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    if code == 124: err = (err or "") + ("timeout" if text else b"timeout")
    return subprocess.CompletedProcess(args, code, out, err)
def _unstick_memuc():
    """Khoá memuc bị giữ quá lâu (1 lệnh memuc treo) → tắt các memuc.exe đang treo + gỡ khoá, để đơn khách không bị huỷ."""
    run(["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name='memuc.exe'\" | Where-Object { $_.CreationDate -lt (Get-Date).AddSeconds(-45) } | "
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
def memuc(*a, timeout=300):
    """memuc chỉ xử lý 1 lệnh một lúc (chạy chồng → "read failed: 233") → xếp hàng bằng khoá + thử lại."""
    r = None
    for i in range(4):
        lk = _Lock("memuc", wait=min(max(120, timeout), 260))
        try: lk.__enter__()
        except RuntimeError:
            _unstick_memuc(); lk = _Lock("memuc", wait=60); lk.__enter__()
        try:
            r = run([os.path.join(MEMU, "memuc.exe")] + list(a), timeout)
        finally: lk.__exit__()
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
def port_of(idx): return 21503 + 10 * int(idx)

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
    q = urllib.parse.quote; base = CONF.get("PUBLIC_BASE", "https://phone.blueroblox.shop").rstrip("/"); udid = f"127.0.0.1:{port}"
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

HIDE = CONF.get("HIDE_WINDOWS", "1") == "1"      # 1 = cửa sổ MEmu của máy khách chạy ngầm (không hiện, không lên thanh taskbar)
def hide_window(name, show=False):
    """Đẩy cửa sổ MEmu ra ngoài màn hình + bỏ khỏi taskbar. KHÔNG thu nhỏ (thu nhỏ làm MEmu ngừng vẽ → web màn đen)."""
    if not HIDE and not show: return 0
    u = ctypes.windll.user32; found = []
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
            u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW); u.ShowWindow(h, 5)
            u.SetWindowPos(h, 0, 100, 100, 0, 0, 0x0001 | 0x0004)
        else:
            u.ShowWindow(h, 0)                                                   # ẩn tạm để đổi kiểu cửa sổ
            u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
            u.SetWindowPos(h, 0, -32000, -32000, 0, 0, 0x0001 | 0x0004 | 0x0010)  # ra ngoài màn hình, giữ kích thước
            u.ShowWindow(h, 4)                                                   # hiện lại (không lấy focus) → MEmu vẫn vẽ hình
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
        # tắt hẳn hiệu ứng chuyển cảnh → CPU không phải vẽ thêm
        "settings put global window_animation_scale 0; settings put global transition_animation_scale 0; "
        "settings put global animator_duration_scale 0; settings put global package_verifier_enable 0; "
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

def tune(name, port=None):
    try: ashell(name, TUNE, port)
    except Exception: pass
def grant_perms(name):
    try: ashell(name, PERM_SH)
    except Exception: pass
    tune(name)

WP = os.path.join(HOME, "wallpaper.png")
def set_wallpaper(name, port, force=False):
    """Ảnh nền BlueRoblox cho máy (1 lần/máy): chép thẳng vào file ảnh nền của Android (cần root) rồi khởi động lại giao diện ~30 giây."""
    if CONF.get("WALLPAPER", "1") != "1" or not os.path.isfile(WP): return False
    s_ = f"127.0.0.1:{port}"
    if not force and "Y" in (adb("-s", s_, "shell", "[ -f /data/local/tmp/.br_wp ] && echo Y", timeout=15).stdout or ""): return False
    adb("-s", s_, "push", WP, "/data/local/tmp/br_wp.png", timeout=120)
    sc = ("D=/data/system/users/0; for f in wallpaper wallpaper_orig wallpaper_lock wallpaper_lock_orig; do "
          "cp /data/local/tmp/br_wp.png $D/$f; chown system:system $D/$f; chmod 600 $D/$f; done; "
          "rm -f $D/wallpaper_info.xml; restorecon $D/wallpaper* 2>/dev/null; touch /data/local/tmp/.br_wp; stop; sleep 2; start")
    adb("-s", s_, "shell", "su -c '" + sc + "'", timeout=60)
    print(f"   🖼 {name}: đã đặt ảnh nền BlueRoblox", flush=True)
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

MAX_RAM = float(CONF.get("MEMU_MAX_RAM", "16") or 16)     # MEmu KHÔNG khởi động được máy > 16GB (báo "The computer memory is low")
MAX_CPU = int(float(CONF.get("MEMU_MAX_CPU", "8") or 8))       # MEmu: máy > 8 nhân không khởi động được
def configure(idx, ram, cpu, res, dpi):
    w, h = res.lower().split("x")
    if float(ram) > MAX_RAM: print(f"   (gói {float(ram):g}GB → MEmu chỉ chạy tối đa {MAX_RAM:g}GB/máy, đặt {MAX_RAM:g}GB)", flush=True)
    ram = min(float(ram), MAX_RAM); cpu = min(float(cpu), MAX_CPU)
    for k, v in (("memory", int(float(ram) * 1024)), ("cpus", max(1, int(round(float(cpu))))), ("is_customed_resolution", 1),
                 ("resolution_width", w), ("resolution_height", h), ("vbox_dpi", int(dpi or auto_dpi(res))), ("enable_su", 1),
                 ("graphics_render_mode", CONF.get("MEMU_RENDER", "1")),          # 1 = DirectX (nhẹ, ổn định hơn trên Windows)
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
        tune(name, port); grant_perms(name)
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
    sp = take_spare(a.name)
    if sp is not None:
        idx = sp
        print(f"[1/4] ⚡ Dùng máy dựng sẵn (MEmu #{idx}) → đổi tên, RAM, CPU…", flush=True)
        with _Lock("memu"):
            dpi = a.dpi or auto_dpi(a.res)
            configure(idx, a.ram, a.cpu, a.res, dpi)
            memuc("setconfigex", "-i", idx, "fps", clamp_fps(a.fps), timeout=60)
            apply_template(idx)
    else:
        print(f"[1/4] Tạo máy Android 9 trên MEmu…", flush=True)
        with _Lock("memu"):
            for oi, ox in sorted(vms().items(), reverse=True):   # máy trùng tên còn sót trong MEmu (lần tạo trước bị ngắt) → xoá trước
                if ox["name"] == a.name:
                    print(f"   (xoá máy sót cùng tên #{oi})", flush=True); memuc("stop", "-i", oi, timeout=60); memuc("remove", "-i", oi, timeout=180)
            before = set(vms())
            r = memuc("create", "96", timeout=240)                       # 96 = Android 9 64-bit
            m = re.search(r"index\D*(\d+)", r.stdout or "")
            idx = int(m.group(1)) if m else next(iter(sorted(set(vms()) - before)), None)
            if idx is None: print("LỖI tạo máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-300:]); sys.exit(4)
            print(f"[2/4] Đã tạo MEmu #{idx} → đặt tên, RAM, CPU, root…", flush=True)
            memuc("rename", "-i", idx, a.name, timeout=60)
            dpi = a.dpi or auto_dpi(a.res)
            configure(idx, a.ram, a.cpu, a.res, dpi)
            memuc("setconfigex", "-i", idx, "fps", clamp_fps(a.fps), timeout=60)
            apply_template(idx)
    port = port_of(idx); exp = now() + datetime.timedelta(days=a.days)
    row = {"name": a.name, "idx": idx, "port": port, "ram": a.ram, "cpu": a.cpu, "res": a.res, "fps": clamp_fps(a.fps), "dpi": dpi,
           "android": "9", "kind": "memu", "created": fmt(now()), "expires": exp.isoformat()}
    st = load(); st["phones"].append(row); save(st)
    print(f"[3/4] Bật máy…", flush=True)
    s = memu_start(idx)
    if not a.nowait: print(f"[4/4] Chờ Android khởi động (tối đa {BOOT_WAIT // 60} phút)…", flush=True)
    if s.returncode not in (0, None) and "SUCCESS" not in (s.stdout or "").upper():
        print("CẢNH BÁO bật máy:", (s.stdout or s.stderr or "").strip()[-200:])
    ok = True if a.nowait else wait_boot(a.name, port)
    print(f"✅ Đã tạo máy '{a.name}' (MEmu #{idx})  | cổng {port} | RAM {a.ram:g}GB CPU {a.cpu:g} | hết hạn {fmt(exp)}")
    print("   Android đã khởi động xong, sẵn sàng điều khiển." if ok else "   CẢNH BÁO: máy chưa kết nối được trình điều khiển, sẽ tự thử lại.")

def _need(name):
    st = load(); p = rec(name, st)
    if not p: print("Không có máy tên này."); sys.exit(1)
    if IDX(p) is None: print(f"LỖI: không thấy máy '{name}' trong MEmu (đã bị xoá tay?)."); sys.exit(4)
    return load(), rec(name)

def cmd_delete(a):
    st = load(); p = rec(a.name, st)
    if not p: print("Không có máy tên này."); sys.exit(1)
    if IDX(p) is None:                     # máy đã không còn trong MEmu → chỉ xoá khỏi danh sách
        st = load(); st["phones"] = [x for x in st["phones"] if x["name"] != a.name]; save(st)
        print(f"🗑️  '{a.name}' không còn trong MEmu — đã bỏ khỏi danh sách."); return
    adb("disconnect", serial(p), timeout=15)
    with _Lock("memu"):
        memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
        memuc("remove", "-i", IDX(p), timeout=180)
    st = load(); st["phones"] = [x for x in st["phones"] if x["name"] != a.name]; save(st)
    print(f"🗑️  Đã xoá máy '{a.name}' và toàn bộ dữ liệu.")

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
    r = run([os.path.join(MEMU, "memuc.exe"), "listvms", "--running"], 30)
    if r.returncode not in (0, None) or any(ln.strip() and ln[0].isdigit() for ln in (r.stdout or "").splitlines()):
        return False
    for im in ("MEmuConsole.exe", "MEmuHeadless.exe", "MEmu.exe", "MemuService.exe", "MEmuSVC.exe"):
        run(["taskkill", "/F", "/T", "/IM", im], 30)
    time.sleep(5); print("   (MEmu bị kẹt → đã tự khởi động lại phần chạy ngầm của MEmu)", flush=True); return True
def memu_start(idx):
    r = memuc("start", "-i", idx, timeout=150)
    if _start_failed(r):
        time.sleep(8); r = memuc("start", "-i", idx, timeout=150)
    if _start_failed(r) and memu_unstick():
        r = memuc("start", "-i", idx, timeout=150)
    return r
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
    start_phone(p); wait_boot(a.name, p["port"], apps=False)
    st = load(); q = rec(a.name, st); q["ram"], q["cpu"] = ram, cpu; save(st)
    print(f"⬆️ '{a.name}' → {ram:g}GB RAM · {cpu:g} nhân")

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
    print(f"Windows: RAM {tot:.1f} GB (còn trống {av:.1f} GB, chừa {RESERVE:g} GB) · CPU {os.cpu_count()} luồng · MEmu: {MEMU or 'KHÔNG THẤY'}")
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
            print(f"XOA_HONG {nm}: kẹt sau {e['tries']} lần khởi động lại → xoá máy hỏng (máy khách sẽ được tạo lại mới)", flush=True)
            a.name = nm; cmd_delete(a); h.pop(nm, None); continue
        e["tries"] += 1; e["since"] = t
        print(f"KHOI_DONG_LAI {nm}: Android không lên quá {STUCK_MIN} phút → khởi động lại (lần {e['tries']})", flush=True)
        adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3); start_phone(p)
    for k in list(h):
        if k not in seen: h.pop(k, None)
    _hs(h)
    if a.orphans: _cleanup(v, quiet=True)

def _cleanup(v=None, quiet=False, all_=False):
    """Xoá máy trong MEmu KHÔNG thuộc danh sách BlueRoblox (giả lập cũ / thừa / tạo dở). Giữ máy mẫu (MEMU_TEMPLATE)."""
    v = v if v is not None else vms(); mine = {p["name"] for p in load()["phones"]}; tpl = CONF.get("MEMU_TEMPLATE", "")
    gone = 0
    for i in sorted(v, reverse=True):          # xoá từ số lớn xuống → số máy còn lại ít bị đổi
        nm = v[i]["name"]
        if nm == tpl or (nm in mine and not all_) or (nm.startswith("spare_") and not all_): continue
        if quiet and not nm.startswith("cp_"): continue     # tự động: chỉ dọn máy do BlueRoblox tạo (cp_…)
        print(f"XOA_THUA {nm} (MEmu #{i})", flush=True)
        if v[i]["running"]: memuc("stop", "-i", i, timeout=120); time.sleep(3)
        memuc("remove", "-i", i, timeout=180); gone += 1
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
            before = set(vms())
            r = memuc("create", "96", timeout=90)        # bình thường ~10–30 giây; treo → bỏ, không giữ khoá lâu
            m = re.search(r"index\D*(\d+)", r.stdout or "")
            idx = int(m.group(1)) if m else next(iter(sorted(set(vms()) - before)), None)
            if idx is None: print("LỖI dựng máy sẵn:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:]); return
            memuc("rename", "-i", idx, nm, timeout=60)
            d = _pl(); d.setdefault("building", []).append(nm); _ps(d)
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
        if i2 is not None: memuc("stop", "-i", i2, timeout=120)
        if ok:
            d = _pl(); d["ready"].append(nm); d["building"] = [x for x in d.get("building", []) if x != nm]; _ps(d)
            print(f"SAN_SANG {nm}: máy dựng sẵn đã xong ({len(d['ready'])}/{POOL_SIZE})")
        else: print(f"LỖI {nm}: Android không lên — sẽ dựng lại lần sau")
    finally: lk.__exit__()

def cmd_noop(a): print("(bản Windows: không cần lệnh này)")
def cmd_render(a):
    """Đổi chế độ vẽ của 1 máy: opengl | directx (khởi động lại máy ~1 phút)."""
    st, p = _need(a.name); m = {"opengl": 0, "directx": 1}[a.mode]
    adb("disconnect", serial(p), timeout=15); memuc("stop", "-i", IDX(p), timeout=120); time.sleep(3)
    memuc("setconfigex", "-i", IDX(p), "graphics_render_mode", m, timeout=60)
    start_phone(p); ok = wait_boot(a.name, p["port"], apps=False)
    print(f"✅ '{a.name}' → vẽ bằng {a.mode.upper()}" + ("" if ok else " (đang kết nối lại)"))
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
    print(f"Đã cho {n} cửa sổ MEmu chạy ngầm.")

def main():
    ap = argparse.ArgumentParser(); s = ap.add_subparsers(dest="c", required=True)
    c = s.add_parser("create"); c.add_argument("name"); c.add_argument("--ram", type=float, default=2); c.add_argument("--cpu", type=float, default=2)
    c.add_argument("--days", type=int, default=7); c.add_argument("--res", default="720x1280"); c.add_argument("--dpi", type=int, default=0)
    c.add_argument("--fps", type=int, default=30); c.add_argument("--nowait", action="store_true"); c.add_argument("--android", default="9")
    c.add_argument("--nogpu", action="store_true"); c.set_defaults(f=cmd_create)
    for nm, fn in (("delete", cmd_delete), ("stop", cmd_stop), ("start", cmd_start), ("restart", cmd_restart), ("show", cmd_show)):
        x = s.add_parser(nm); x.add_argument("name"); x.set_defaults(f=fn)
    r = s.add_parser("renew"); r.add_argument("name"); r.add_argument("--days", type=int, default=7); r.set_defaults(f=cmd_renew)
    z = s.add_parser("resize"); z.add_argument("name"); z.add_argument("--ram", type=float, default=0); z.add_argument("--cpu", type=float, default=0); z.set_defaults(f=cmd_resize)
    w = s.add_parser("waitboot"); w.add_argument("name"); w.add_argument("--noapps", action="store_true"); w.set_defaults(f=cmd_waitboot)
    g = s.add_parser("reconfig"); g.add_argument("name"); g.add_argument("--fps", type=int, default=0); g.add_argument("--res", default=""); g.set_defaults(f=cmd_reconfig)
    lr = s.add_parser("liveres"); lr.add_argument("name"); lr.add_argument("--res", required=True); lr.set_defaults(f=cmd_liveres)
    pi = s.add_parser("preinstall"); pi.add_argument("name", nargs="?", default=""); pi.add_argument("--all", action="store_true"); pi.add_argument("--force", action="store_true"); pi.set_defaults(f=cmd_preinstall)
    rf = s.add_parser("rootfix"); rf.add_argument("name", nargs="?", default=""); rf.add_argument("--all", action="store_true"); rf.add_argument("--force", action="store_true"); rf.set_defaults(f=cmd_rootfix)
    rd = s.add_parser("render"); rd.add_argument("name"); rd.add_argument("mode", choices=["opengl", "directx"]); rd.set_defaults(f=cmd_render)
    wp = s.add_parser("wallpaper"); wp.add_argument("name", nargs="?", default=""); wp.add_argument("--all", action="store_true"); wp.add_argument("--force", action="store_true"); wp.set_defaults(f=cmd_wallpaper)
    tp = s.add_parser("template"); tp.add_argument("name", nargs="?", default=""); tp.add_argument("--apply", action="store_true"); tp.set_defaults(f=cmd_template)
    hd = s.add_parser("hide"); hd.add_argument("name", nargs="?", default=""); hd.set_defaults(f=cmd_hide)
    he = s.add_parser("heal"); he.add_argument("--orphans", action="store_true"); he.set_defaults(f=cmd_heal)
    cl = s.add_parser("cleanup"); cl.add_argument("--all", action="store_true"); cl.add_argument("--yes", action="store_true"); cl.set_defaults(f=cmd_cleanup)
    s.add_parser("pool").set_defaults(f=cmd_pool)
    ba = s.add_parser("bootall"); ba.add_argument("--quiet", action="store_true"); ba.set_defaults(f=cmd_bootall)
    for nm, fn in (("connect-all", cmd_connect_all), ("reap", cmd_reap), ("perms", cmd_perms), ("capacity", cmd_capacity), ("list", cmd_list),
                   ("memfix", cmd_noop), ("boost", cmd_noop), ("gpuinfo", cmd_noop)):
        s.add_parser(nm).set_defaults(f=fn)
    a = ap.parse_args(); a.f(a)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    main()
