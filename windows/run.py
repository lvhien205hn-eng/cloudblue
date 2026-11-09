# -*- coding: utf-8 -*-
# =====================================================================
#  run.py — chạy cloudphoned.py / cpapi.py (viết cho Ubuntu) trên WINDOWS mà không phải sửa 2 file đó.
#   python run.py cloudphoned.py      |      python run.py cpapi.py
#  Lớp "dịch" bên dưới đổi các lệnh Linux sang Windows:
#   • docker exec wsscrcpy adb …  → adb.exe …          (ws-scrcpy chạy thẳng trên Windows)
#   • docker cp FILE wsscrcpy:/tmp/x → chép vào <BLUE>\wstmp\x   (/tmp/… trong lệnh adb cũng trỏ về đó)
#   • docker exec cp_xxx /system/bin/sh -c …  → adb -s 127.0.0.1:<cổng máy> shell …
#   • docker ps / docker inspect → hỏi MEmu máy nào đang chạy
#   • /proc/stat, /proc/meminfo, /proc/uptime → số liệu thật của Windows
# =====================================================================
import builtins, ctypes, io, json, os, runpy, shutil, subprocess, sys, time

BLUE = os.path.dirname(os.path.abspath(__file__))
os.environ["USERPROFILE"] = BLUE; os.environ["HOME"] = BLUE        # ~ = thư mục BlueRoblox → ~/cloudphone.conf, ~/redroid/…
os.environ["BLUE_HOME"] = BLUE
ADB = os.path.join(BLUE, "platform-tools", "adb.exe")
WSTMP = os.path.join(BLUE, "wstmp"); os.makedirs(WSTMP, exist_ok=True)
PHONES = os.path.join(BLUE, "redroid", "phones.json")
PHONECTL = os.path.join(BLUE, "phonectl.py")
os.environ["PATH"] = os.path.join(BLUE, "platform-tools") + os.pathsep + os.environ.get("PATH", "")
try: sys.stdout.reconfigure(encoding="utf-8", line_buffering=True); sys.stderr.reconfigure(encoding="utf-8")
except Exception: pass

def _map(p):
    """/tmp/abc (đường dẫn TRONG container ws-scrcpy cũ) → <BLUE>\\wstmp\\abc"""
    if isinstance(p, str) and p.startswith("/tmp/"): return os.path.join(WSTMP, p[5:].replace("/", os.sep))
    return p

def _phones():
    try: return {p["name"]: p for p in json.load(open(PHONES, encoding="utf-8")).get("phones", [])}
    except Exception: return {}

_vm_cache = [0.0, {}]
def _running_names():
    if time.time() - _vm_cache[0] < 5: return _vm_cache[1]
    r = _orig_run([sys.executable, PHONECTL, "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    names = {ln.split()[0] for ln in (r.stdout or "").splitlines() if ln.strip().endswith("chạy")}
    _vm_cache[:] = [time.time(), names]; return names

def _done(args, code=0, out="", err="", text=True):
    if not text: out, err = out.encode(), err.encode()
    return subprocess.CompletedProcess(args, code, out, err)

def _translate(args, text):
    """Trả về (lệnh mới, None) hoặc (None, kết quả làm sẵn)."""
    if not isinstance(args, (list, tuple)) or not args: return args, None
    a = [str(x) for x in args]
    if a[0] in ("python3", "python"): return [sys.executable] + a[1:], None
    if a[0] == "adb": return [ADB] + [_map(x) for x in a[1:]], None
    if a[0] in ("systemctl", "sudo", "nvidia-smi") and a[0] != "nvidia-smi": return None, _done(a, 1, text=text)
    if a[0] != "docker": return a, None
    sub = a[1] if len(a) > 1 else ""
    if sub == "exec" and len(a) > 3:
        who, rest = a[2], a[3:]
        if who == "wsscrcpy":
            if rest[0] == "adb":
                # adb push/install: tham số /tmp/… là file máy tính → đổi sang wstmp; còn lại giữ nguyên
                return [ADB] + [_map(x) for x in rest[1:]], None
            if rest[0] == "rm":
                for x in rest[1:]:
                    if x.startswith("-"): continue
                    q = _map(x)
                    try: shutil.rmtree(q) if os.path.isdir(q) else os.remove(q)
                    except Exception: pass
                return None, _done(a, 0, text=text)
            return None, _done(a, 1, err="không hỗ trợ", text=text)
        p = _phones().get(who)                         # docker exec cp_xxx /system/bin/sh -c …  → adb shell
        if not p: return None, _done(a, 1, err="không có máy", text=text)
        cmd = rest[-1] if len(rest) >= 3 and rest[-2] == "-c" else " ".join(rest)
        # docker exec chạy bằng root; adb shell của MEmu là người dùng shell → chạy qua su (máy đã bật root)
        import shlex
        return [ADB, "-s", f"127.0.0.1:{p['port']}", "shell", f"su -c {shlex.quote(cmd)} 2>/dev/null || {{ {cmd}; }}"], None
    if sub == "cp" and len(a) >= 4:
        src, dst = a[2], a[3]
        if ":" in dst and dst.split(":", 1)[0] == "wsscrcpy":
            q = _map(dst.split(":", 1)[1]); os.makedirs(os.path.dirname(q), exist_ok=True)
            try:
                if os.path.isdir(src): shutil.copytree(src, q, dirs_exist_ok=True)
                else: shutil.copyfile(src, q)
                return None, _done(a, 0, text=text)
            except Exception as e: return None, _done(a, 1, err=str(e), text=text)
        return None, _done(a, 1, text=text)
    if sub == "ps":
        return None, _done(a, 0, "\n".join(sorted(_running_names())) + "\n", text=text)
    if sub == "inspect":
        name = a[-1]; fmt = " ".join(a)
        if "State.Running" in fmt: return None, _done(a, 0, ("true" if name in _running_names() else "false") + "\n", text=text)
        return None, _done(a, 1, text=text)
    return None, _done(a, 1, err="docker không có trên Windows", text=text)

_orig_run, _orig_popen = subprocess.run, subprocess.Popen
NOWIN = 0x08000000
def _run(args, *k, **kw):
    text = bool(kw.get("text") or kw.get("universal_newlines") or kw.get("encoding"))
    new, ready = _translate(args, text)
    if ready is not None: return ready
    if text and "encoding" not in kw: kw["encoding"] = "utf-8"; kw.setdefault("errors", "replace")
    kw.setdefault("creationflags", NOWIN)
    try: return _orig_run(new, *k, **kw)
    except FileNotFoundError as e: return _done(new, 127, err=str(e), text=text)
class _Popen(_orig_popen):
    def __init__(self, args, *k, **kw):
        new, ready = _translate(args, bool(kw.get("text")))
        if ready is not None: new = [sys.executable, "-c", "pass"]
        kw.setdefault("creationflags", NOWIN)
        super().__init__(new, *k, **kw)
subprocess.run = _run; subprocess.Popen = _Popen

# ---------- /proc/… của Linux → số liệu Windows ----------
class _MEM(ctypes.Structure):
    _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
def _proc(path):
    k32 = ctypes.windll.kernel32
    if path == "/proc/meminfo":
        m = _MEM(); m.l = ctypes.sizeof(_MEM); k32.GlobalMemoryStatusEx(ctypes.byref(m))
        return f"MemTotal: {m.total // 1024} kB\nMemFree: {m.avail // 1024} kB\nMemAvailable: {m.avail // 1024} kB\n"
    if path == "/proc/stat":
        i, k, u = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        idle, busy = i.value // 100000, (k.value + u.value - i.value) // 100000
        return f"cpu {busy} 0 0 {idle} 0 0 0 0 0 0\n"
    if path == "/proc/uptime":
        k32.GetTickCount64.restype = ctypes.c_ulonglong
        return f"{k32.GetTickCount64() / 1000:.2f} 0\n"
    return None
_orig_open = builtins.open
def _open(file, *k, **kw):
    if isinstance(file, str) and file.startswith("/proc/"):
        s = _proc(file)
        if s is None: raise FileNotFoundError(file)
        return io.StringIO(s)
    if isinstance(file, str) and file.startswith("/sys/"): raise FileNotFoundError(file)
    if isinstance(file, str) and "b" not in (k[0] if k else kw.get("mode", "r")) and "encoding" not in kw: kw["encoding"] = "utf-8"
    return _orig_open(file, *k, **kw)
builtins.open = _open
if not hasattr(os, "getloadavg"): os.getloadavg = lambda: (0.0, 0.0, 0.0)
_orig_listdir = os.listdir
def _listdir(p="."):
    if isinstance(p, str) and p.startswith(("/sys/", "/proc/")): raise FileNotFoundError(p)
    return _orig_listdir(p)
os.listdir = _listdir
os.path.expanduser = (lambda f: (lambda p: p.replace("~", BLUE, 1) if isinstance(p, str) and p.startswith("~") else f(p)))(os.path.expanduser)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("python run.py cloudphoned.py | cpapi.py")
    if os.path.basename(sys.argv[1]).lower() == "cloudphoned.py" and os.path.isfile(os.path.join(BLUE, "baomat.py")):
        try:    # canh gác bảo mật (clipboard + thư mục chia sẻ riêng từng máy khách) — đã chạy thì thôi, không chặn cloudphoned
            _orig_popen([sys.executable, os.path.join(BLUE, "baomat.py"), "start"], cwd=BLUE, creationflags=NOWIN,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: pass
    target = os.path.join(BLUE, sys.argv[1]); sys.argv = [target] + sys.argv[2:]
    runpy.run_path(target, run_name="__main__")
