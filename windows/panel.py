# -*- coding: utf-8 -*-
# =====================================================================
#  panel.py — BẢNG ĐIỀU KHIỂN CloudBlue trên Windows (LDPlayer 9 · MuMu · MEmu)
#  Mở: bấm đúp biểu tượng "BlueRoblox" trên Desktop  (hoặc: pythonw C:\blue\panel.py)
#   • Đèn trạng thái: MEmu, adb, khoá Supabase, trình phát hình, cổng bảo vệ, chương trình nhận đơn, Cloudflare, web
#   • Nút: Cài đặt/Cập nhật · Dán khoá Supabase · Nối Cloudflare · Bật/Tắt tất cả · Tạo/Xoá máy thử · Làm mới máy khách
#   • Nhật ký từng phần, dòng lỗi tô đỏ. Chương trình nào bị tắt → tự bật lại.
# =====================================================================
import ctypes, glob, json, os, queue, re, socket, subprocess, sys, threading, time, tkinter as tk, urllib.parse, urllib.request
from tkinter import filedialog, messagebox, simpledialog, ttk

B = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(os.path.dirname(sys.executable), "python.exe") if sys.executable.lower().endswith("pythonw.exe") else sys.executable
FROZEN = getattr(sys, "frozen", False)           # chạy bằng BlueRobloxServer.exe (không cần cài Python)
if FROZEN: TASK_EXE, TASK_ARG = sys.executable, "--auto"
else: TASK_EXE, TASK_ARG = os.path.join(os.path.dirname(sys.executable), "pythonw.exe"), '"C:\\blue\\panel.py" --auto'
LOGS = os.path.join(B, "logs"); os.makedirs(LOGS, exist_ok=True)
CONF = os.path.join(B, "cloudphone.conf")
RAW = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main"
NOWIN = 0x08000000
HIPRI = NOWIN | 0x00008000   # ABOVE_NORMAL — trình phát hình/cpapi/adb luôn được ưu tiên (Task Scheduler mặc định chạy THẤP → giật hình)
def _boost_self():
    """Bảng chạy từ Task Scheduler bị hạ ưu tiên (CPU 'Below normal', ổ đĩa/RAM 'thấp') và truyền xuống mọi tiến trình con → nâng lại."""
    try:
        k = ctypes.windll.kernel32; h = k.GetCurrentProcess()
        k.SetPriorityClass(h, 0x00000020)                          # NORMAL cho chính bảng
        class MP(ctypes.Structure): _fields_ = [("v", ctypes.c_ulong)]
        k.SetProcessInformation(h, 0, ctypes.byref(MP(5)), 4)       # ProcessMemoryPriority = 5 (bình thường)
        ctypes.windll.ntdll.NtSetInformationProcess(h, 33, ctypes.byref(ctypes.c_ulong(2)), 4)   # IoPriority = bình thường
    except Exception: pass
ENV = dict(os.environ, PATH=os.path.join(B, "platform-tools") + os.pathsep + os.environ.get("PATH", ""), PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1",
           ADB_LOCAL_TRANSPORT_MAX_PORT="5553")   # adb KHÔNG tự dò "emulator-55xx": LDPlayer hiện mỗi máy 2 lần (emulator-5556 + 127.0.0.1:5557)
                                                  # → trình phát hình bật 2 bộ nén trên cùng 1 máy, tranh nhau cổng → hình đứng/giựt

# ---------- màu Cloud Blue ----------
BG, CARD, LINE, FG, MUTED, BLUE, GOOD, BAD, WARN = "#0b1530", "#12204a", "#22356e", "#e8efff", "#93a4cf", "#3d8bff", "#2ecc71", "#ff5d6c", "#ffb547"
ERR = re.compile(r"(LỖI|lỗi|Error|ERROR|Traceback|Exception|✗|HẾT HÀNG|failed|không kết nối)", re.I)

SERVICES = {   # tên: (thư mục chạy, lệnh)
    "ws-scrcpy": (os.path.join(B, "ws-scrcpy", "dist"), [__import__("shutil").which("node") or r"C:\Program Files\nodejs\node.exe", "index.js"]),
    "cpapi": (B, [PY, "-u", "run.py", "cpapi.py"]),
    "cloudphoned": (B, [PY, "-u", "run.py", "cloudphoned.py"]),
    "duong-thang": (B, [os.path.join(B, "caddy.exe"), "run", "--config", os.path.join(B, "Caddyfile"), "--adapter", "caddyfile"]),
    "phat-hinh": (B, [PY, "-u", "bluestream.py"]),                # PHÁT HÌNH v2 cho app PC + app Android (TLS cổng 8189 + WebSocket 8020)
}
FAST_PORT = 8443
CADDY_URL = "https://caddyserver.com/api/download?os=windows&arch=amd64&p=github.com%2Fcaddy-dns%2Fcloudflare"

def pub_host():
    """Tên miền của MÁY CHỦ NÀY (máy 1: phone.cloudblue.vn, máy 2: phone2.cloudblue.vn…) — lấy từ PUBLIC_BASE."""
    try: return urllib.parse.urlparse(conf().get("PUBLIC_BASE", "")).netloc or "phone.cloudblue.vn"
    except Exception: return "phone.cloudblue.vn"

def zone_of(h):
    """Tên miền gốc: phone2.cloudblue.vn → cloudblue.vn (giữ 3 phần cho kiểu x.com.vn)."""
    p = [x for x in (h or "").split(":")[0].split(".") if x]
    n = 3 if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ("com", "net", "org", "edu", "gov", "co", "ac", "info", "biz") else 2
    return ".".join(p[-n:]) if len(p) >= n else ""

def conf():
    d = {}
    try:
        for line in open(CONF, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"): k, v = line.split("=", 1); d[k.strip()] = v.strip()
    except FileNotFoundError: pass
    return d

_FB = ""
try: _FB = urllib.parse.urlparse(conf().get("FAST_BASE", "")).hostname or ""
except Exception: pass
ZONE = zone_of(_FB or pub_host()) or "cloudblue.vn"          # đường thẳng đã bật trước đó thì giữ đúng tên cũ
FAST_HOST = _FB or "fast." + ZONE

def set_conf(key, val):
    lines, done = [], False
    try: lines = open(CONF, encoding="utf-8").read().splitlines()
    except FileNotFoundError: pass
    for i, l in enumerate(lines):
        if l.split("=", 1)[0].strip() == key: lines[i] = f"{key}={val}"; done = True
    if not done: lines.append(f"{key}={val}")
    open(CONF, "w", encoding="utf-8").write("\n".join(lines) + "\n")

EMUS = {"ld": ("LDPlayer 9", "9"), "mumu": ("MuMu", "12,7"), "memu": ("MEmu", "7,12")}
MUMU_DIRS = [r"C:\Program Files\Netease\MuMuPlayer-12.0", r"D:\Program Files\Netease\MuMuPlayer-12.0", r"C:\Program Files\Netease\MuMu Player 12",
             r"D:\Program Files\Netease\MuMu Player 12", r"C:\Program Files\Netease\MuMuPlayer", r"D:\Program Files\Netease\MuMuPlayer",
             r"C:\Program Files\MuMuPlayerGlobal-12.0", r"D:\Program Files\MuMuPlayerGlobal-12.0", r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0",
             r"C:\Program Files\Netease\MuMu", r"D:\Program Files\Netease\MuMu"]
MUMU_REL = (r"nx_main\mumu-cli.exe", r"shell\MuMuManager.exe", r"nx_main\MuMuManager.exe", "MuMuManager.exe", "mumu-cli.exe")
MUMU_CACHE = os.path.join(B, "redroid", "mumu_dir.txt")      # phonectl.py dùng chung file này
_MU = {"t": 0.0, "d": ""}

def mumu_cli(d):
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

def mumu_root(f):
    d = os.path.dirname(f)
    return os.path.dirname(d) if os.path.basename(d).lower() in ("shell", "nx_main") else d

def _reg_dir(v):
    v = (v or "").strip()
    if v.startswith('"'): v = v[1:].split('"', 1)[0]
    else:
        m = re.match(r"(.+?\.(?:exe|ico|dll))(?:[\s,].*)?$", v, re.I)
        if m: v = m.group(1)
    v = v.strip().rstrip("\\/")
    if re.search(r"\.(exe|ico|dll)$", v, re.I): v = os.path.dirname(v)
    return v if v and os.path.isdir(v) else ""

def mumu_guess():
    """MuMu cài chỗ lạ: khoá gỡ cài đặt trong registry → chương trình MuMu đang chạy → thư mục Netease/MuMu ở mọi ổ cứng."""
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
    try:                                                           # MuMu đang mở → lấy đúng chỗ cài từ chương trình đang chạy
        k = ctypes.WinDLL("kernel32"); ps = ctypes.WinDLL("psapi"); k.OpenProcess.restype = ctypes.c_void_p
        arr = (ctypes.c_ulong * 8192)(); n = ctypes.c_ulong()
        if ps.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(n)):
            for pid in arr[:n.value // ctypes.sizeof(ctypes.c_ulong)]:
                h = k.OpenProcess(0x1000, False, pid)
                if not h: continue
                try:
                    buf = ctypes.create_unicode_buffer(1024); sz = ctypes.c_ulong(1024)
                    if k.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(sz)) and "mumu" in os.path.basename(buf.value).lower():
                        out += [os.path.dirname(buf.value), os.path.dirname(os.path.dirname(buf.value))]
                finally: k.CloseHandle(ctypes.c_void_p(h))
    except Exception: pass
    try:
        kk = ctypes.windll.kernel32; m = kk.GetLogicalDrives()
        drives = [chr(65 + i) for i in range(26) if m >> i & 1 and kk.GetDriveTypeW(f"{chr(65 + i)}:\\") == 3]
    except Exception: drives = ["C", "D", "E"]
    for dr in drives:
        for pat in (r"\Program Files\Netease\*", r"\Program Files (x86)\Netease\*", r"\Netease\*", r"\Program Files\MuMu*",
                    r"\Program Files (x86)\MuMu*", r"\MuMu*", r"\*\MuMu*", r"\*\Netease\*"):
            out += glob.glob(dr + ":" + pat)
    return out

def find_mumu(c, deep=True):
    """Thư mục MuMu ("" = chưa thấy). Dò sâu tối đa 2 phút/lần; thấy rồi thì ghi nhớ."""
    for d in [c.get("MUMU_DIR", "")] + MUMU_DIRS:
        f = mumu_cli(d)
        if f: return mumu_root(f)
    try:
        f = mumu_cli(open(MUMU_CACHE, encoding="utf-8").read().strip())
        if f: return mumu_root(f)
    except OSError: pass
    if not deep: return ""
    if time.time() - _MU["t"] < 120: return _MU["d"]
    _MU["t"] = time.time(); _MU["d"] = ""
    seen = set()
    for d in mumu_guess():
        key = os.path.normcase(os.path.abspath(d))
        if key in seen: continue
        seen.add(key)
        f = mumu_cli(d)
        if f:
            _MU["d"] = mumu_root(f)
            try: os.makedirs(os.path.dirname(MUMU_CACHE), exist_ok=True); open(MUMU_CACHE, "w", encoding="utf-8").write(_MU["d"])
            except OSError: pass
            break
    return _MU["d"]

def find_emu(c=None):
    """(thư mục giả lập, chữ hiện trên đèn) theo loại đã chọn ở cloudphone.conf (EMU=ld|mumu|memu)."""
    c = c or conf(); e = (c.get("EMU") or "").lower()
    ld = next((d for d in [c.get("LD_DIR", ""), r"C:\LDPlayer\LDPlayer9", r"D:\LDPlayer\LDPlayer9", r"C:\leidian\LDPlayer9", r"D:\leidian\LDPlayer9"]
               if d and os.path.isfile(os.path.join(d, "ldconsole.exe"))), "")
    mm = next((d for d in [c.get("MEMU_DIR", ""), r"C:\Program Files\Microvirt\MEmu", r"D:\Program Files\Microvirt\MEmu"]
               if d and os.path.isfile(os.path.join(d, "memuc.exe"))), "")
    mu = find_mumu(c, deep=e == "mumu" or (not e and not ld and not mm))
    found = {"ld": ld, "memu": mm, "mumu": mu}
    if e not in found: e = "ld" if ld else ("mumu" if mu else ("memu" if mm else ""))
    if not e: return "", "chưa thấy giả lập — cài LDPlayer 9 hoặc MuMu rồi bấm 🎛 Chọn giả lập"
    name = EMUS[e][0]; av = c.get("ANDROIDS") or EMUS[e][1]
    if found[e]: return found[e], f"{name} · bán Android {av.replace(',', ', ')}"
    if e == "mumu": return "", "chưa thấy MuMu — bấm 🎛 Chọn giả lập → 📂 Chọn thư mục MuMu"
    return "", f"chưa thấy {name} — cài từ trang chính thức"

def port_open(p):
    s = socket.socket(); s.settimeout(0.5)
    try: s.connect(("127.0.0.1", p)); return True
    except Exception: return False
    finally: s.close()

def is_admin():
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

def run_admin(ps_cmd, log, secret=False):
    """Chạy lệnh PowerShell bằng quyền Administrator (Windows hỏi 1 lần); mọi dòng chữ ghi ra file nhật ký (UTF-8).
       secret=True: file lệnh tự xoá ngay khi PowerShell đã đọc xong (có mật khẩu bên trong)."""
    ps1 = os.path.join(LOGS, "_admin_job.ps1")
    body = ("$ErrorActionPreference = 'Continue'\n"
            + ("Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n" if secret else "") +
            f"$LOG = '{log}'\n"
            "& {\n" + ps_cmd + "\n} *>&1 | ForEach-Object { $s = ($_ | Out-String).TrimEnd(); "
            "[IO.File]::AppendAllText($LOG, $s + [Environment]::NewLine, [Text.Encoding]::UTF8); $s }\n"
            "[IO.File]::AppendAllText($LOG, 'XONG_JOB' + [Environment]::NewLine)\n")
    open(ps1, "w", encoding="utf-8-sig").write(body)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -File "{ps1}"', B, 1)

def runq(cmd, timeout=120):
    """Chạy lệnh nền, kết quả ra FILE tạm (không pipe → không bao giờ treo vì tiến trình con giữ pipe). Quá giờ → tắt, trả về phần đã có."""
    import tempfile
    with tempfile.TemporaryFile() as fo:
        try: p = subprocess.Popen(cmd, cwd=B, stdout=fo, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=ENV, creationflags=NOWIN)
        except OSError as e: return str(e)
        try: p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/F"], capture_output=True, creationflags=NOWIN)
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: pass
        fo.seek(0); return fo.read().decode("utf-8", "replace")

def kill_tree(pid):
    """Tắt 1 chương trình + các chương trình con của nó, NHƯNG GIỮ adb server.
       (adb server hay được sinh ra làm "con" của ws-scrcpy / cloudphoned → taskkill /T giết luôn adb → MỌI máy mất kết nối:
        web đen/giật, máy mới treo "Đang tạo…".)"""
    keep = adb_pid()
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId),$($_.ParentProcessId)\" }"],
                         capture_output=True, text=True, creationflags=NOWIN, timeout=60).stdout or ""
    kids = {}
    for ln in out.splitlines():
        a = ln.strip().split(",")
        if len(a) == 2 and a[0].isdigit() and a[1].isdigit(): kids.setdefault(a[1], []).append(a[0])
    todo, seen = [str(pid)], []
    while todo:
        x = todo.pop()
        if x in seen: continue
        seen.append(x); todo += kids.get(x, [])
    for x in reversed(seen):
        if x != keep: subprocess.run(["taskkill", "/PID", x, "/F"], capture_output=True, creationflags=NOWIN)

PORTS = {"ws-scrcpy": 8000, "cpapi": 8010, "duong-thang": 8443, "phat-hinh": int(conf().get("STREAM_PORT") or 8189)}
def free_port(port):
    """Tắt chương trình CŨ còn giữ cổng (vd ws-scrcpy cũ mất kết nối adb → web đen màn, bản mới không mở được cổng: EADDRINUSE)."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
    pids = {ln.split()[-1] for ln in out.splitlines() if "LISTENING" in ln and re.search(rf"[:.]{port}\s", ln)}
    for pid in pids:
        if pid.isdigit() and int(pid) not in (0, os.getpid()):
            kill_tree(pid)
    return len(pids)
def cmd_pids(rx):
    """PID các chương trình python đang chạy có dòng lệnh khớp biểu thức rx (VD bản nhận đơn cloudphoned.py), trừ chính bảng này."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match '%s' } | "
                              "ForEach-Object { $_.ProcessId }" % rx.replace("'", "''")],
                             capture_output=True, text=True, creationflags=NOWIN, timeout=60).stdout or ""
    except Exception: return []
    return [int(x) for x in out.split() if x.strip().isdigit() and int(x) != os.getpid()]

def adb_pid():
    """PID của adb SERVER (tiến trình đang nghe cổng 5037) — KHÔNG phải các lệnh adb chạy thoáng qua
       (bản trước lấy nhầm lệnh adb tạm → tưởng adb khởi động lại → bật lại trình phát hình liên tục → web giật/đứt)."""
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
    for ln in out.splitlines():
        if "LISTENING" in ln and re.search(r"127\.0\.0\.1:5037\s", ln): return ln.split()[-1]
    return ""

class Svc:
    def __init__(self, name, ui):
        self.name, self.ui, self.p, self.want = name, ui, None, False
        self.log = os.path.join(LOGS, name + ".log")
    def start(self):
        self.want = True
        if self.p and self.p.poll() is None: return
        cwd, cmd = SERVICES[self.name]
        if not os.path.isdir(cwd): self.ui.say(self.name, f"✗ Chưa cài ({cwd}) — bấm Cài đặt trước"); return
        if self.name in PORTS and free_port(PORTS[self.name]): self.ui.say(self.name, f"♻ Đã tắt bản cũ còn giữ cổng {PORTS[self.name]}"); time.sleep(1)
        if self.name == "ws-scrcpy": self.ui.adb_seen = adb_pid()
        if self.name == "cloudphoned":                 # 14/11: bảng cũ bị tắt ngang → bản nhận đơn cũ còn chạy → 2 bản cùng nhận đơn
            old = cmd_pids(r"cloudphoned\.py\W*$")
            for pid in old: subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NOWIN)
            if old: self.ui.say(self.name, f"♻ Đã tắt {len(old)} bản nhận đơn cũ còn chạy (tránh 2 bản cùng nhận đơn)"); time.sleep(1)
        try:
            self.p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                      env=ENV, creationflags=HIPRI, bufsize=1, text=True, encoding="utf-8", errors="replace")
        except Exception as e:
            self.ui.say(self.name, f"✗ Không chạy được: {e}"); return
        self.ui.say(self.name, f"▶ Đã bật (pid {self.p.pid})")
        threading.Thread(target=self._pump, args=(self.p,), daemon=True).start()
    def _pump(self, p):
        with open(self.log, "a", encoding="utf-8") as f:
            for line in p.stdout:
                f.write(time.strftime("%H:%M:%S ") + line); f.flush(); self.ui.say(self.name, line.rstrip())
        code = p.wait()
        if self.want:
            self.ui.say(self.name, f"✗ Bị tắt (mã {code}) — tự bật lại sau 5 giây"); time.sleep(5)
            if self.want: self.start()
    def stop(self):
        self.want = False
        if self.p and self.p.poll() is None:
            kill_tree(self.p.pid)
            self.ui.say(self.name, "■ Đã tắt")
    def alive(self): return bool(self.p and self.p.poll() is None)

class App:
    def __init__(self, auto=False):
        self.q = queue.Queue()
        r = self.root = tk.Tk(); r.title("CloudBlue — Bảng điều khiển máy chủ Windows"); r.geometry("1100x720"); r.configure(bg=BG)
        r.minsize(900, 600)
        st = ttk.Style(); st.theme_use("clam")
        st.configure("TNotebook", background=BG, borderwidth=0); st.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", BLUE)], foreground=[("selected", "white")])
        self.svcs = {n: Svc(n, self) for n in SERVICES}
        top = tk.Frame(r, bg=BG); top.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(top, text="🐋 CloudBlue", fg=BLUE, bg=BG, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(top, text="  máy chủ Windows · LDPlayer 9 / MuMu / MEmu", fg=MUTED, bg=BG, font=("Segoe UI", 11)).pack(side="left", pady=(6, 0))
        self.adm = tk.Label(top, text="", bg=BG, font=("Segoe UI", 10)); self.adm.pack(side="right")
        # dòng tổng: đủ đèn xanh = OK
        self.banner = tk.Label(r, text="⏳ Đang kiểm tra…", fg="#1a1300", bg=WARN, font=("Segoe UI", 13, "bold"), anchor="w", padx=14, pady=6)
        self.banner.pack(fill="x", padx=18, pady=(0, 6)); self.state = {}; self.booting = False
        # đèn trạng thái
        self.lights = {}
        grid = tk.Frame(r, bg=BG); grid.pack(fill="x", padx=14)
        items = [("memu", "Giả lập"), ("adb", "adb (Google)"), ("key", "Khoá Supabase"), ("ws", "Trình phát hình :8000"),
                 ("api", "Cổng bảo vệ :8010"), ("daemon", "Nhận đơn (cloudphoned)"), ("cf", "Đường hầm Cloudflare"), ("web", pub_host()),
                 ("st", f"Phát hình app :{PORTS['phat-hinh']}")]
        for i, (k, t) in enumerate(items):
            c = tk.Frame(grid, bg=CARD, highlightbackground=LINE, highlightthickness=1); c.grid(row=i // 4, column=i % 4, sticky="nsew", padx=4, pady=4)
            grid.columnconfigure(i % 4, weight=1)
            dot = tk.Label(c, text="●", fg=MUTED, bg=CARD, font=("Segoe UI", 16)); dot.pack(side="left", padx=(10, 6), pady=6)
            box = tk.Frame(c, bg=CARD); box.pack(side="left", fill="x", expand=True)
            tk.Label(box, text=t, fg=FG, bg=CARD, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
            sub = tk.Label(box, text="đang kiểm tra…", fg=MUTED, bg=CARD, font=("Segoe UI", 9), anchor="w"); sub.pack(fill="x")
            self.lights[k] = (dot, sub)
        # nút
        bar1 = tk.Frame(r, bg=BG); bar1.pack(fill="x", padx=14, pady=(8, 2))
        bar2 = tk.Frame(r, bg=BG); bar2.pack(fill="x", padx=14, pady=2)
        bar3 = tk.Frame(r, bg=BG); bar3.pack(fill="x", padx=14, pady=(2, 8))
        def btn(text, cmd, color=CARD, fg=FG):                 # 3 hàng nút (7 · 6 · còn lại) — cửa sổ nhỏ vẫn thấy đủ nút
            bar = bar1 if len(bar1.winfo_children()) < 7 else (bar2 if len(bar2.winfo_children()) < 6 else bar3)
            b = tk.Button(bar, text=text, command=cmd, bg=color, fg=fg, activebackground=BLUE, activeforeground="white", relief="flat",
                          font=("Segoe UI", 10, "bold"), padx=12, pady=7, cursor="hand2", bd=0)
            b.pack(side="left", padx=3); return b
        btn("🚀 TỰ ĐỘNG A→Z", self.auto, GOOD, "#062012")
        btn("① Cài đặt / Cập nhật", self.install)
        btn("② Dán khoá Supabase", self.set_key)
        btn("③ Nối Cloudflare", self.cloudflare)
        btn("▶ Bật tất cả", self.start_all, BLUE, "white")
        btn("■ Tắt tất cả", self.stop_all, "#3a2030", "#ffb3bb")
        btn("🧪 Tạo máy thử", self.test_phone)
        btn("🎛 Chọn giả lập", self.choose_emu, "#14304a", "#bfe0ff")
        btn("📋 Danh sách máy", lambda: self.job("Danh sách máy", [PY, "phonectl.py", "list"]))
        btn("♻ Làm mới máy khách", self.remake)
        btn("🖼 Ảnh nền cho máy", lambda: self.job("Đặt ảnh nền CloudBlue cho các máy đang chạy (máy chưa có)", [PY, "phonectl.py", "wallpaper", "--all"]))
        btn("🙈 Ẩn cửa sổ giả lập", lambda: self.job("Cho cửa sổ giả lập chạy ngầm", [PY, "phonectl.py", "hide"]))
        btn("🧹 Dọn giả lập thừa", self.cleanup, "#3a2a10", "#ffd9a0")
        btn("⚡ Tối ưu Windows", self.optimize)
        btn("🛣 Đường thẳng (ít trễ)", self.fast_setup)
        btn("🔑 Tự đăng nhập + tự chạy", self.autologon, "#2a2350", "#d9ccff")
        btn("⏻ Thoát hẳn", self.quit_all, "#3a2030", "#ffb3bb")
        # nhật ký
        self.nb = ttk.Notebook(r); self.nb.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.texts = {}
        for n in ["Tổng quan"] + list(SERVICES) + ["Việc đang làm"]:
            f = tk.Frame(self.nb, bg=CARD)
            t = tk.Text(f, bg="#08102a", fg=FG, insertbackground=FG, font=("Consolas", 10), relief="flat", wrap="word")
            sb = tk.Scrollbar(f, command=t.yview); t.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y"); t.pack(fill="both", expand=True)
            t.tag_configure("err", foreground=BAD); t.tag_configure("ok", foreground=GOOD); t.tag_configure("dim", foreground=MUTED)
            self.nb.add(f, text=n); self.texts[n] = t
        self.status = tk.Label(r, text="", fg=MUTED, bg=BG, anchor="w", font=("Segoe UI", 9)); self.status.pack(fill="x", padx=16, pady=(0, 8))
        self.say("Tổng quan", "Chào bạn! Làm lần lượt: ① Cài đặt → ② Dán khoá Supabase → ③ Nối Cloudflare → 🧪 Tạo máy thử → ▶ Bật tất cả.")
        r.after(150, self._drain)
        threading.Thread(target=self._checker, daemon=True).start()
        r.protocol("WM_DELETE_WINDOW", self.on_close)
        if auto: r.after(1500, self.boot_auto)          # Windows khởi động lại → tự bật A→Z
        else: r.after(4000, self._auto_if_idle)         # 14/11: bảng mở KHÔNG kèm --auto mà chưa chạy gì → cũng tự bật A→Z
        if not conf().get("EMU") and not auto: r.after(1200, self.choose_emu)    # lần đầu: hỏi máy chủ này chạy LDPlayer hay MuMu/MEmu

    # ---------- nhật ký ----------
    def say(self, tab, line): self.q.put((tab, line))
    def _drain(self):
        try:
            for _ in range(400):
                tab, line = self.q.get_nowait()
                for t in {tab, "Tổng quan"} if tab in SERVICES and ERR.search(line) else {tab}:
                    w = self.texts.get(t) or self.texts["Tổng quan"]
                    tag = "err" if ERR.search(line) else "ok" if re.search(r"(✓|✅|\[OK\]|Đã bật|sẵn sàng|XONG)", line) else None
                    w.insert("end", (f"[{tab}] " if t != tab else "") + line + "\n", tag)
                    if int(w.index("end-1c").split(".")[0]) > 3000: w.delete("1.0", "500.0")
                    w.see("end")
        except queue.Empty: pass
        self.root.after(150, self._drain)

    NAMES = {"memu": "Giả lập", "adb": "adb", "key": "Khoá Supabase", "ws": "Trình phát hình", "api": "Cổng bảo vệ",
             "daemon": "Nhận đơn", "cf": "Đường hầm Cloudflare", "web": "Web", "st": "Phát hình app"}
    def light(self, k, ok, text):
        dot, sub = self.lights[k]
        dot.configure(fg=GOOD if ok is True else BAD if ok is False else WARN); sub.configure(text=text)
        self.state[k] = ok is True
        good = sum(1 for x in self.NAMES if self.state.get(x)); bad = [self.NAMES[x] for x in self.NAMES if x in self.state and not self.state[x]]
        if good == len(self.NAMES) and not self.booting:
            self.banner.configure(text=f"✅ OK — đủ {good}/{len(self.NAMES)} đèn xanh · hệ thống đang chạy, nhận đơn bình thường", bg=GOOD, fg="#062012")
        elif self.booting:
            self.banner.configure(text=f"⏳ Đang tự khởi động A→Z… ({good}/{len(self.NAMES)} đèn xanh) — {self.boot_step}", bg=WARN, fg="#1a1300")
        else:
            self.banner.configure(text=f"⚠ {good}/{len(self.NAMES)} đèn xanh — lỗi: {', '.join(bad) or 'đang kiểm tra'}", bg=BAD, fg="white")

    # ================= TỰ QUÉT + TỰ SỬA (chạy ngầm, mỗi 4 giây) =================
    def _fix(self, what):
        self.say("Tổng quan", f"🩺 Tự sửa: {what}  ({time.strftime('%H:%M:%S')})")
        try:                                   # 14/11: ghi cả ra file (trước chỉ hiện trong bảng — đóng bảng là mất dấu máy bị chống kẹt xoá)
            with open(os.path.join(LOGS, "bang-tu-sua.log"), "a", encoding="utf-8") as f: f.write(time.strftime("%d/%m %H:%M:%S ") + str(what) + "\n")
        except Exception: pass
    def _bad(self, k, cond):
        """Đếm số lần lỗi liên tiếp của mục k."""
        f = self.__dict__.setdefault("_fails", {}); f[k] = f.get(k, 0) + 1 if cond else 0; return f[k]
    def _restart_svc(self, name):
        sv = self.svcs[name]
        threading.Thread(target=lambda: (sv.stop(), time.sleep(2), sv.start()), daemon=True).start()
    def _heal(self, n, c):
        if self.booting: return
        on = lambda name: self.svcs[name].want
        # hộp thoại lỗi của MEmu ("MEmu start error"…) chặn MEmu tới khi có người bấm OK → tự đóng + ghi lại
        try:
            u = ctypes.windll.user32
            for t in ("MEmu start error", "MEmu error", "Error"):
                h = u.FindWindowW(None, t)
                if h:
                    n_ = u.GetWindowTextLengthW(h); buf = ctypes.create_unicode_buffer(n_ + 1); u.GetWindowTextW(h, buf, n_ + 1)
                    pid = ctypes.c_ulong(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    exe = ""
                    try: exe = subprocess.run(["tasklist", "/FI", f"PID eq {pid.value}", "/FO", "CSV", "/NH"], capture_output=True, text=True, creationflags=NOWIN).stdout.lower()
                    except Exception: pass
                    if "memu" in exe:
                        u.PostMessageW(h, 0x0010, 0, 0); self._fix(f"đóng hộp thoại lỗi MEmu: {buf.value}")
        except Exception: pass
        # adb server do CHÍNH bảng giữ (không làm "con" của dịch vụ nào → tắt/bật dịch vụ không kéo adb chết theo)
        if n % 2 == 0 and on("ws-scrcpy") and not adb_pid():
            subprocess.run([os.path.join(B, "platform-tools", "adb.exe"), "start-server"], capture_output=True, creationflags=HIPRI, env=ENV, timeout=30)
            self._fix("adb bị tắt → bật lại adb")
        # trình phát hình / cổng bảo vệ không mở cổng ~16 giây → bật lại (tự tắt bản cũ giữ cổng)
        if on("ws-scrcpy") and self._bad("ws", not port_open(8000)) == 4: self._fix("trình phát hình :8000 không chạy → bật lại"); self._restart_svc("ws-scrcpy")
        if on("cpapi") and self._bad("api", not port_open(8010)) == 4: self._fix("cổng bảo vệ :8010 không chạy → bật lại"); self._restart_svc("cpapi")
        if on("cloudphoned") and self._bad("daemon", not self.svcs["cloudphoned"].alive()) == 6: self._fix("nhận đơn bị tắt → bật lại"); self._restart_svc("cloudphoned")
        if n % 3 == 0 and on("cpapi"):
            q = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
            if "SERVICE_NAME" in q and self._bad("cf", "RUNNING" not in q) >= 2:
                self._fix("đường hầm Cloudflare tắt → bật lại"); subprocess.run(["sc", "start", "cloudflared"], capture_output=True, creationflags=NOWIN)
            # web 5xx/không vào được 3 lần liền trong khi máy mình vẫn chạy → khởi động lại đường hầm
            web_bad = self.lights and not self.state.get("web", True)
            if self._bad("web", web_bad and port_open(8010)) == 3:
                self._fix("web không vào được → khởi động lại đường hầm Cloudflare")
                subprocess.run(["powershell", "-NoProfile", "-Command", "Restart-Service cloudflared -Force; Start-Sleep 2; Start-Service cloudflared"], capture_output=True, creationflags=NOWIN, timeout=120)
        # ~1 phút: lệnh MEmu treo quá 3 phút → tắt; máy khách mất kết nối điều khiển → nối lại
        if n % 15 == 5 and on("cloudphoned") and not getattr(self, "_stuckjob", False):
            def sj():
                self._stuckjob = True
                try:
                    ps = ("Get-CimInstance Win32_Process -Filter \"name='memuc.exe'\" | Where-Object { $_.CreationDate -lt (Get-Date).AddMinutes(-3) } | "
                          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'X' }; "
                          # lệnh phonectl ngắn (list / connect-all / show…) chạy quá 5 phút = treo → tắt (nó giữ khoá MEmu, chặn đơn khách)
                          "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'phonectl\\.py\" (connect-all|list|show|hide|capacity|perms)|phonectl\\.py (connect-all|list|show|hide|capacity|perms)' "
                          "-and $_.CreationDate -lt (Get-Date).AddMinutes(-5) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'X' }")
                    out = runq(["powershell", "-NoProfile", "-Command", ps], 60)
                    if "X" in out: self._fix(f"tắt {out.count('X')} lệnh MEmu bị treo")
                    r = runq([PY, "phonectl.py", "connect-all"], 180)
                    k = r.count("nối lại")
                    if k: self._fix(f"nối lại điều khiển {k} máy khách")
                except Exception as e: self.say("Tổng quan", f"🩺 gỡ treo lỗi: {e}")
                finally: self._stuckjob = False
            threading.Thread(target=sj, daemon=True).start()
        # ~1 phút: máy khách còn hạn mà đang TẮT ngoài ý muốn (bấm Close trong Multiple Instance Manager, MEmu văng…) → tự bật lại
        if n % 15 == 7 and on("cloudphoned") and not getattr(self, "_bootjob", False):
            def bj():
                self._bootjob = True
                try:
                    r = runq([PY, "phonectl.py", "bootall", "--quiet"], 1800)
                    for ln in r.splitlines():
                        if ln.strip() and ("▶" in ln or "✅" in ln or "✗" in ln or "⚠" in ln): self._fix(ln.strip())
                except Exception as e: self.say("Tổng quan", f"🩺 tự bật máy lỗi: {e}")
                finally: self._bootjob = False
            threading.Thread(target=bj, daemon=True).start()
        # ~2 phút: CHỐNG KẸT — máy chạy mà Android không lên → khởi động lại; kẹt mãi → xoá máy hỏng + tạo lại máy khách; dọn giả lập cp_ thừa
        if n % 30 == 22 and on("cloudphoned") and not getattr(self, "_healjob", False):
            def hj():
                self._healjob = True
                try:
                    r = runq([PY, "phonectl.py", "heal", "--orphans"], 1200)
                    for ln in r.splitlines():
                        if ln.startswith(("KHOI_DONG_LAI", "XOA_HONG", "XOA_THUA", "Đã xoá")): self._fix(ln.split(" ", 1)[-1] if ln.startswith(("KHOI", "XOA")) else ln)
                    if "XOA_HONG" in r:
                        self._fix("tạo lại máy khách vừa xoá (giữ chủ máy, cấu hình, hạn dùng)")
                        runq([PY, "run.py", "remake.py", "all"], 3600)
                except Exception as e: self.say("Tổng quan", f"🩺 chống kẹt lỗi: {e}")
                finally: self._healjob = False
            threading.Thread(target=hj, daemon=True).start()
        # ~1 phút: giữ sẵn máy dựng trước (khách mua → có máy sau ~1 phút thay vì 4–5 phút)
        if n % 15 == 10 and on("cloudphoned") and not getattr(self, "_pooljob", False):
            def pj():
                self._pooljob = True
                try:
                    r = runq([PY, "phonectl.py", "pool"], 1500)
                    for ln in r.splitlines():
                        if ln.startswith(("DUNG_SAN", "SAN_SANG", "LỖI", "XOA_DO")):
                            self.say("Tổng quan", "⚡ Máy dựng sẵn: " + ln.split(" ", 1)[-1] + f"  ({time.strftime('%H:%M:%S')})")
                except Exception as e: self.say("Tổng quan", f"⚡ dựng máy sẵn lỗi: {e}")
                finally: self._pooljob = False
            threading.Thread(target=pj, daemon=True).start()
        # ~5 phút: ổ đĩa sắp đầy → cảnh báo
        if n % 75 == 40:
            import shutil
            free = shutil.disk_usage("C:\\").free / 2**30
            if free < 15: self.say("Tổng quan", f"⚠ Ổ C: chỉ còn {free:.0f} GB trống — máy mới có thể không tạo được. Xoá bớt máy hết hạn / file rác.")

    def cleanup(self):
        if messagebox.askyesno("Dọn giả lập thừa", "XOÁ mọi giả lập trong MEmu KHÔNG thuộc danh sách CloudBlue (giả lập cũ, tạo dở, bị kẹt)?\n"
                               "Máy khách đang thuê và máy test1 được GIỮ NGUYÊN."):
            self.job("Dọn giả lập thừa", [PY, "phonectl.py", "cleanup"])

    # ================= TỰ ĐĂNG NHẬP WINDOWS + TỰ CHẠY QUYỀN ADMIN =================
    def autologon(self):
        user = os.environ.get("USERNAME", ""); dom = os.environ.get("USERDOMAIN", "") or os.environ.get("COMPUTERNAME", "")
        if not messagebox.askyesno("Tự đăng nhập + tự chạy",
                f"Bật 3 thứ để mất điện / khởi động lại là TỰ chạy lại hết, không cần ai bấm:\n\n"
                f"1) Windows tự đăng nhập tài khoản '{user}' (không dừng ở màn hình mật khẩu)\n"
                f"2) Bảng CloudBlue tự mở bằng quyền Admin khi đăng nhập (tự sửa được cả đường hầm Cloudflare)\n"
                f"3) Máy không tự ngủ / tắt màn hình\n\nWindows sẽ hỏi quyền Admin. Tiếp tục?"): return
        pw = simpledialog.askstring("Mật khẩu Windows",
                f"Nhập mật khẩu đăng nhập Windows của tài khoản '{user}'.\n"
                "(Để trống nếu tài khoản không có mật khẩu.)\n"
                "Mật khẩu được Windows cất trong vùng bảo mật (LSA) — giống như netplwiz — không ghi ra file, không gửi đi đâu.",
                show="•", parent=self.root)
        if pw is None: return
        esc = lambda x: x.replace("'", "''")
        log = os.path.join(LOGS, "autologon.log")
        try: os.remove(log)
        except OSError: pass
        lsa = r"""
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class BRLsa {
  [StructLayout(LayoutKind.Sequential)] public struct U { public ushort L; public ushort M; public IntPtr B; }
  [StructLayout(LayoutKind.Sequential)] public struct A { public int Len; public IntPtr R; public IntPtr N; public uint At; public IntPtr S; public IntPtr Q; }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr s, ref A a, int acc, out IntPtr h);
  [DllImport("advapi32.dll")] static extern uint LsaStorePrivateData(IntPtr h, ref U k, ref U d);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr h);
  static U Mk(string s) { var u = new U(); u.B = Marshal.StringToHGlobalUni(s); u.L = (ushort)(s.Length * 2); u.M = (ushort)(u.L + 2); return u; }
  public static uint Store(string key, string val) {
    var a = new A(); IntPtr h; uint r = LsaOpenPolicy(IntPtr.Zero, ref a, 0x00000020 | 0x00000004, out h); if (r != 0) return r;
    var k = Mk(key); var d = Mk(val); r = LsaStorePrivateData(h, ref k, ref d); LsaClose(h); return r; }
}
'@
"""
        cmd = (lsa + rf"""
$U = '{esc(user)}'; $D = '{esc(dom)}'; $P = '{esc(pw)}'
$W = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty $W AutoAdminLogon '1'; Set-ItemProperty $W DefaultUserName $U; Set-ItemProperty $W DefaultDomainName $D
Remove-ItemProperty $W DefaultPassword -ErrorAction SilentlyContinue
Remove-ItemProperty $W AutoLogonCount -ErrorAction SilentlyContinue
$r = [BRLsa]::Store('DefaultPassword', $P); $P = $null
if ($r -eq 0) {{ Write-Host '[OK] Windows tu dang nhap tai khoan' $U }} else {{ Write-Host 'LOI luu mat khau (ma' $r ')' }}
New-Item 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device' -Force | Out-Null
Set-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device' DevicePasswordLessBuildVersion 0 -Type DWord
Write-Host '[OK] Tat bat buoc Windows Hello'
$a = New-ScheduledTaskAction -Execute '{TASK_EXE}' -Argument '{TASK_ARG}' -WorkingDirectory 'C:\blue'
$t = New-ScheduledTaskTrigger -AtLogOn -User "$D\$U"
$pr = New-ScheduledTaskPrincipal -UserId "$D\$U" -LogonType Interactive -RunLevel Highest
$st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -Priority 4
Register-ScheduledTask -TaskName 'BlueRoblox' -Action $a -Trigger $t -Principal $pr -Settings $st -Force | Out-Null
Remove-Item "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk" -ErrorAction SilentlyContinue
Write-Host '[OK] Bang BlueRoblox tu mo bang quyen Admin khi dang nhap'
powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /change monitor-timeout-ac 0
Write-Host '[OK] Khong ngu, khong tat man hinh'
""")
        pw = None
        run_admin(cmd, log, secret=True)
        self.tail(log, "Tự đăng nhập + tự chạy", 180)

    # ================= TỰ BẬT A→Z KHI WINDOWS KHỞI ĐỘNG LẠI =================
    boot_step = ""
    def _auto_if_idle(self):
        """14/11: có máy chủ khởi động lại mà bảng mở KHÔNG kèm --auto (bấm biểu tượng Desktop trước, lối tắt / tác vụ cũ thiếu
           --auto…) → bảng mở ra mà không bật gì: máy khách không chạy, không nhận đơn. Giờ: bảng mở lên, đã cài đủ (adb + khoá
           Supabase) mà CHƯA dịch vụ nào chạy → tự bật A→Z như lúc Windows vừa khởi động. Tắt: PANEL_AUTOSTART=0 trong cloudphone.conf."""
        def chk():
            try:
                c = conf()
                if str(c.get("PANEL_AUTOSTART", "1")).strip() == "0": return
                if not os.path.isfile(os.path.join(B, "platform-tools", "adb.exe")) or len(c.get("SUPABASE_SERVICE_KEY", "")) < 30: return
                if self.booting or any(x.want for x in self.svcs.values()): return
                if port_open(8000) or port_open(8010) or port_open(PORTS["phat-hinh"]) or cmd_pids(r"cloudphoned\.py\W*$"): return
                self.say("Tổng quan", "🔄 Bảng vừa mở mà chưa dịch vụ nào chạy → TỰ BẬT A→Z (dịch vụ + máy khách), khỏi bấm ▶ Bật tất cả")
                self.root.after(0, self.boot_auto)
            except Exception as e:
                self.say("Tổng quan", f"✗ Tự bật lỗi: {e}")
        threading.Thread(target=chk, daemon=True).start()
    def boot_auto(self):
        self.booting = True; threading.Thread(target=self._boot, daemon=True).start()
    def _boot(self):
        S = lambda m: self.say("Tổng quan", m)
        def stepmsg(m): self.boot_step = m; S(m)
        try:
            S("\n🔄 ========== WINDOWS VỪA KHỞI ĐỘNG: tự bật A→Z ==========")
            stepmsg("1/5 Chờ mạng + Windows ổn định…")
            t0 = time.time()
            while time.time() - t0 < 120:
                try: socket.create_connection(("1.1.1.1", 443), 5).close(); break
                except OSError: time.sleep(5)
            time.sleep(15)
            stepmsg("2/5 Dọn lệnh MEmu kẹt từ lần trước…")
            for im in ("memuc.exe",): subprocess.run(["taskkill", "/F", "/IM", im], capture_output=True, creationflags=NOWIN)
            for fn in os.listdir(os.path.join(B, "redroid")) if os.path.isdir(os.path.join(B, "redroid")) else []:
                if fn.endswith(".lock"):
                    try: os.remove(os.path.join(B, "redroid", fn))
                    except OSError: pass
            stepmsg("3/5 Bật trình phát hình + cổng bảo vệ + nhận đơn…")
            self.root.after(0, self.start_all)
            t0 = time.time()
            while time.time() - t0 < 120 and not (port_open(8000) and port_open(8010)): time.sleep(2)
            q = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
            if "SERVICE_NAME" in q and "RUNNING" not in q:
                subprocess.run(["sc", "start", "cloudflared"], capture_output=True, creationflags=NOWIN)
            stepmsg("4/5 Bật lại các máy khách còn hạn (mỗi máy ~1–2 phút)…")
            code, out = self.job("Bật lại máy khách sau khi khởi động", [PY, "phonectl.py", "bootall"], wait=True)
            stepmsg("5/5 Kiểm tra đủ đèn xanh…")
            t0 = time.time()
            while time.time() - t0 < 180 and not all(self.state.get(x) for x in self.NAMES): time.sleep(4)
            ok = all(self.state.get(x) for x in self.NAMES)
            bad = [self.NAMES[x] for x in self.NAMES if not self.state.get(x)]
            S("🎉 ========== XONG: đủ đèn xanh — OK ==========" if ok and code == 0 else
              f"⚠ ========== XONG nhưng còn lỗi: {', '.join(bad) or 'có máy khách chưa bật được (xem tab Việc đang làm)'} ==========")
        except Exception as e:
            S(f"✗ Tự bật bị lỗi: {e}")
        finally:
            self.booting = False

    # ---------- kiểm tra trạng thái (mỗi 4 giây) ----------
    def _checker(self):
        n = 0
        while True:
            c = conf()
            memu, emu_txt = find_emu(c)
            L = self.root.after
            L(0, self.light, "memu", bool(memu), emu_txt)
            sp = PORTS["phat-hinh"]
            L(0, self.light, "st", port_open(sp), "đang chạy · app PC/Android nối vào đây" if port_open(sp) else "tắt")
            adb = os.path.isfile(os.path.join(B, "platform-tools", "adb.exe"))
            L(0, self.light, "adb", adb, "đã có" if adb else "chưa cài — bấm ①")
            key = c.get("SUPABASE_SERVICE_KEY", "")
            L(0, self.light, "key", key.startswith("eyJ") or key.startswith("sb_secret_"), "đã dán" if len(key) > 30 else "chưa dán — bấm ②")
            L(0, self.light, "ws", port_open(8000), "đang chạy" if port_open(8000) else "tắt")
            L(0, self.light, "api", port_open(8010), "đang chạy" if port_open(8010) else "tắt")
            d = self.svcs["cloudphoned"].alive()
            L(0, self.light, "daemon", d, "đang nhận đơn" if d else "tắt")
            if n % 3 == 0:
                q = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
                cf = "RUNNING" in q
                L(0, self.light, "cf", cf if "SERVICE_NAME" in q else False, "đang chạy" if cf else ("đã cài, đang tắt" if "SERVICE_NAME" in q else "chưa nối — bấm ③"))
                try:
                    with urllib.request.urlopen(urllib.request.Request(f"https://{pub_host()}/", headers={"User-Agent": "BlueRoblox-panel"}), timeout=8) as rr:
                        L(0, self.light, "web", True, f"mở được (HTTP {rr.status})")
                except urllib.error.HTTPError as e:
                    L(0, self.light, "web", e.code < 500, f"HTTP {e.code}" + (" — máy chủ chưa chạy" if e.code >= 500 else ""))
                except Exception as e:
                    L(0, self.light, "web", False, "không vào được")
            L(0, self.adm.configure, {"text": "🛡 Đang chạy quyền Admin" if is_admin() else "Quyền thường (nút ①③ sẽ hỏi quyền Admin)",
                                      "fg": GOOD if is_admin() else MUTED})
            try: self._heal(n, c)
            except Exception as e: self.say("Tổng quan", f"🩺 tự quét lỗi: {e}")
            ws = self.svcs["ws-scrcpy"]
            if ws.alive() and n % 5 == 2:          # adb bị tắt/bật lại → ws-scrcpy mất theo dõi máy → web đen màn → tự bật lại ws-scrcpy
                ap = adb_pid()
                if ap and getattr(self, "adb_seen", "") and ap != self.adb_seen and ap == getattr(self, "_adb_new", ""):
                    self.say("ws-scrcpy", "♻ adb vừa khởi động lại → bật lại trình phát hình"); self.adb_seen = ap
                    threading.Thread(target=lambda: (ws.stop(), time.sleep(2), ws.start()), daemon=True).start()
                elif ap and not getattr(self, "adb_seen", ""): self.adb_seen = ap
                self._adb_new = ap
            if n % 150 == 5 and c.get("FAST_BASE") and c.get("CF_DNS_TOKEN"): self.fast_dns(quiet=True)   # ~10 phút: IP nhà mạng đổi → cập nhật
            n += 1; time.sleep(4)

    # ---------- việc chạy 1 lần ----------
    def job(self, title, cmd, cwd=B, done=None, wait=False):
        self.root.after(0, self.nb.select, len(SERVICES) + 1); self.say("Việc đang làm", f"\n===== {title} =====")
        def go():
            out = []
            try:
                p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV, creationflags=NOWIN,
                                     text=True, encoding="utf-8", errors="replace")
                for line in p.stdout: self.say("Việc đang làm", line.rstrip()); out.append(line)
                code = p.wait(); self.say("Việc đang làm", f"===== xong ({'OK' if code == 0 else 'mã ' + str(code)}) =====")
                if done: self.root.after(0, done, code)
                return code, "".join(out)
            except Exception as e:
                self.say("Việc đang làm", f"✗ {e}"); return 99, str(e)
        if wait: return go()
        threading.Thread(target=go, daemon=True).start()

    def tail(self, path, title, secs=3600, wait=False):
        self.root.after(0, self.nb.select, len(SERVICES) + 1); self.say("Việc đang làm", f"\n===== {title} (cửa sổ Admin) =====")
        def go():
            import codecs
            dec = codecs.getincrementaldecoder("utf-8")(errors="replace"); t0, pos, buf = time.time(), 0, ""
            while time.time() - t0 < secs:
                try:
                    with open(path, "rb") as f: f.seek(pos); data = f.read(); pos += len(data)
                    buf += dec.decode(data).lstrip("\ufeff")
                    *lines, buf = buf.split("\n")
                    for line in lines:
                        if line.strip() == "XONG_JOB": self.say("Việc đang làm", f"===== {title}: xong ====="); return True
                        if line.strip(): self.say("Việc đang làm", line.rstrip())
                except FileNotFoundError:
                    if time.time() - t0 > 90: self.say("Việc đang làm", "✗ Cửa sổ Admin chưa chạy (bạn bấm Không / No?)"); return False
                time.sleep(1)
            return False
        if wait: return go()
        threading.Thread(target=go, daemon=True).start()

    def install(self):
        if not messagebox.askyesno("Cài đặt / Cập nhật", "Tải bản mới nhất từ GitHub và cài đủ (Node.js, adb, Cloudflare, trình phát hình)?\n"
                                   "Windows sẽ hỏi quyền Admin. Các dịch vụ sẽ tạm tắt trong lúc cài."): return
        self.stop_all()
        log = os.path.join(LOGS, "setup.log")
        try: os.remove(log)
        except OSError: pass
        run_admin(f"Set-Location C:\\\ncurl.exe -fsSL -H \"Accept: application/vnd.github.raw\" -H \"User-Agent: BlueRoblox\" -o C:\\blue\\setup.ps1 \"https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/setup.ps1\"; if ($LASTEXITCODE -ne 0) {{ curl.exe -fsSL -o C:\\blue\\setup.ps1 \"{RAW}/windows/setup.ps1?t={int(time.time())}\" }}\n& C:\\blue\\setup.ps1", log)
        self.tail(log, "Cài đặt / Cập nhật")

    def choose_emu(self, first=False):
        """Máy chủ này chạy giả lập nào → nhận đơn bản Android nào. Mỗi máy chủ 1 loại; web tự chia đơn đúng máy chủ."""
        w = tk.Toplevel(self.root); w.title("Chọn giả lập cho máy chủ này"); w.configure(bg=BG); w.grab_set(); w.resizable(False, False)
        tk.Label(w, text="Máy chủ này chạy giả lập nào?", fg=FG, bg=BG, font=("Segoe UI", 14, "bold")).pack(padx=24, pady=(18, 4))
        tk.Label(w, text="Khách mua Android 9 → máy chủ LDPlayer · Android 12 / 7 → máy chủ MuMu (hoặc MEmu).\n"
                         "Mỗi máy chủ chỉ cài 1 loại. Chọn sai thì bấm 🎛 Chọn giả lập để đổi.", fg=MUTED, bg=BG, font=("Segoe UI", 10), justify="left").pack(padx=24)
        cur = (conf().get("EMU") or "").lower()
        def pick(e, av):
            set_conf("EMU", e); set_conf("ANDROIDS", av); w.destroy()
            self.say("Tổng quan", f"✓ Máy chủ này: {EMUS[e][0]} · nhận đơn Android {av}. Đang bật lại phần nhận đơn…")
            if e == "mumu":                                    # dò MuMu ở nền (không treo bảng); không thấy → mở hộp chọn thư mục
                threading.Thread(target=lambda: find_mumu(conf()) or self.root.after(0, self.pick_mumu_dir), daemon=True).start()
            if self.svcs["cloudphoned"].alive(): threading.Thread(target=lambda: self._restart_svc("cloudphoned"), daemon=True).start()
        for e, (nm, av), desc in (("ld", EMUS["ld"], "Android 9 · ổn định, nhẹ"), ("mumu", EMUS["mumu"], "Android 12 + Android 7 (cần máy mẫu tpl_a7 nếu MuMu mặc định là 12)"),
                                  ("memu", EMUS["memu"], "Android 7 + Android 12 (Android 12 cần máy mẫu tpl_a12)")):
            b = tk.Button(w, text=f"{nm}  —  {desc}" + ("   ✓ đang dùng" if cur == e else ""), command=lambda e=e, av=av: pick(e, av),
                          bg=BLUE if cur == e else CARD, fg="white" if cur == e else FG, relief="flat", font=("Segoe UI", 11, "bold"),
                          padx=14, pady=10, anchor="w", cursor="hand2", bd=0)
            b.pack(fill="x", padx=24, pady=4)
        tk.Button(w, text="📂 Chọn thư mục MuMu (MuMu cài ở ổ / thư mục khác)", command=lambda: (w.destroy(), self.pick_mumu_dir()),
                  bg=CARD, fg=MUTED, relief="flat", font=("Segoe UI", 10), padx=14, pady=6, anchor="w", cursor="hand2", bd=0).pack(fill="x", padx=24, pady=(10, 4))
        tk.Label(w, text="", bg=BG).pack(pady=4)

    def pick_mumu_dir(self):
        """Chọn tay thư mục cài MuMu (thư mục có MuMuManager.exe / mumu-cli.exe, hoặc thư mục cha của nó)."""
        d = filedialog.askdirectory(parent=self.root, title="Chọn thư mục cài MuMu (VD: D:\\Program Files\\Netease\\MuMuPlayer-12.0)")
        if not d: return
        f = mumu_cli(os.path.normpath(d))
        if not f:
            messagebox.showerror("Không phải thư mục MuMu", "Trong thư mục này không có MuMuManager.exe / mumu-cli.exe.\n"
                                 "Mẹo: chuột phải biểu tượng MuMu trên Desktop → Open file location → chọn thư mục đó (hoặc thư mục cha của nó)."); return
        root = mumu_root(f); set_conf("MUMU_DIR", root)
        try: os.makedirs(os.path.dirname(MUMU_CACHE), exist_ok=True); open(MUMU_CACHE, "w", encoding="utf-8").write(root)
        except OSError: pass
        self.say("Tổng quan", f"✓ Đã chọn MuMu: {root}  (lệnh: {os.path.basename(f)}). Bấm ⏹ Tắt tất cả → ▶ Bật tất cả để dùng.")

    def set_key(self):
        k = simpledialog.askstring("Khoá Supabase", "Mở Supabase → Project Settings → API Keys → khoá service_role (Reveal → Copy)\n"
                                   "rồi dán vào đây. Khoá chỉ lưu trong C:\\blue\\cloudphone.conf, không gửi đi đâu.", show="•", parent=self.root)
        if not k: return False
        k = k.strip()
        if not (k.startswith("eyJ") or k.startswith("sb_secret_")): messagebox.showerror("Sai khoá", "Khoá service_role bắt đầu bằng eyJ… hoặc sb_secret_…"); return False
        set_conf("SUPABASE_SERVICE_KEY", k)
        for x, v in (("SUPABASE_URL", "https://nprftgodswlpzomcttal.supabase.co"), ("PUBLIC_BASE", "https://phone.cloudblue.vn"), ("NODE_ID", "win1")):
            if not conf().get(x): set_conf(x, v)
        self.say("Tổng quan", "✓ Đã lưu khoá Supabase. Bấm ▶ Bật tất cả (hoặc Bật lại) để dùng khoá mới.")
        return True

    def cf_token(self):
        s = simpledialog.askstring("Nối Cloudflare", "Cloudflare → Zero Trust → Networks → Tunnels → chọn đường hầm cũ → Configure\n"
                                   "→ phần Install connector chọn Windows → copy cả lệnh (có chữ eyJ…) rồi dán vào đây.", parent=self.root)
        if not s: return None
        m = re.search(r"(eyJ[A-Za-z0-9_\-=.]{40,})", s)
        if not m: messagebox.showerror("Không thấy mã", "Trong chữ vừa dán không có mã bắt đầu bằng eyJ…"); return None
        return m.group(1)

    def cf_install(self, token, wait=False):
        log = os.path.join(LOGS, "cloudflare.log")
        try: os.remove(log)
        except OSError: pass
        exe = r'$c = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source; if (-not $c) { $c = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }'
        run_admin(f"{exe}\n& $c service uninstall 2>$null\n& $c service install {token}\nStart-Sleep 3\n"
                  + f"Set-Content -Encoding ascii C:\\blue\\cloudflared.yml \"ingress:`n  - hostname: {pub_host()}`n    service: http://localhost:8010`n  - service: http_status:404\"\n"
                  + "$k='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\cloudflared'; $p=(Get-ItemProperty $k).ImagePath\n"
                  + "if ($p -notmatch '--config') { Set-ItemProperty $k ImagePath ($p -replace ' tunnel run', ' tunnel --config C:\\blue\\cloudflared.yml run') }\n"
                  + "Restart-Service cloudflared\nsc.exe start cloudflared\nStart-Sleep 2\nsc.exe query cloudflared", log)
        return self.tail(log, "Nối Cloudflare", 180, wait=wait)

    def cloudflare(self):
        t = self.cf_token()
        if t: self.cf_install(t)

    def start_all(self):
        if not os.path.isfile(os.path.join(B, "platform-tools", "adb.exe")): self.say("Tổng quan", "✗ Chưa cài — bấm ① Cài đặt trước"); return
        if len(conf().get("SUPABASE_SERVICE_KEY", "")) < 30: self.say("Tổng quan", "✗ Chưa có khoá Supabase — bấm ② trước"); return
        subprocess.run([os.path.join(B, "platform-tools", "adb.exe"), "start-server"], capture_output=True, creationflags=HIPRI, env=ENV)
        c = conf(); ENV["CF_API_TOKEN"] = c.get("CF_DNS_TOKEN", "")
        for n in SERVICES:
            if n == "duong-thang" and not (c.get("FAST_BASE") and os.path.isfile(os.path.join(B, "caddy.exe"))): continue   # chưa bật đường thẳng
            self.svcs[n].start(); time.sleep(0.5)
    def stop_all(self):
        for s in self.svcs.values(): s.stop()

    def test_phone(self):
        if not messagebox.askyesno("Tạo máy thử", "Tạo máy MEmu tên 'test1' (4GB RAM, 4 nhân) để thử? Mất 1–3 phút."): return
        self.job("Tạo máy thử test1", [PY, "phonectl.py", "create", "test1", "--ram", "4", "--cpu", "4"])

    def remake(self):
        def ask(code):
            txt = self.texts["Việc đang làm"].get("1.0", "end")
            m = re.findall(r"cần làm mới trên Windows: (\d+)", txt)
            if not m or m[-1] == "0": return
            if messagebox.askyesno("Làm mới máy khách", f"Tạo lại {m[-1]} máy khách trên MEmu (giữ chủ máy, cấu hình, hạn dùng; app/dữ liệu cũ MẤT)?\n"
                                   "Nên báo khách trước. Làm từng máy một, có thể mất khá lâu."):
                self.job("Làm mới máy khách", [PY, "run.py", "remake.py", "all"])
        self.job("Máy khách cần làm mới", [PY, "run.py", "remake.py", "list"], done=ask)

    def optimize(self):
        if not messagebox.askyesno("Tối ưu Windows", "Bật chế độ hiệu năng cao, không cho máy ngủ, cho Windows Defender bỏ qua thư mục MEmu/BlueRoblox "
                                   "(đỡ giật ổ cứng), tắt quay màn hình nền của Xbox Game Bar?\nWindows sẽ hỏi quyền Admin."): return
        log = os.path.join(LOGS, "optimize.log")
        try: os.remove(log)
        except OSError: pass
        run_admin(r"""
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null | Out-Null
$u = (powercfg -list | Select-String 'Ultimate|Hiệu năng tối đa' | Select-Object -First 1)
if ($u) { powercfg -setactive (($u -split '\s+')[3]) } else { powercfg -setactive SCHEME_MIN }
powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /hibernate off
Write-Host '[OK] Che do hieu nang cao, khong ngu'
$M = @('C:\Program Files\Microvirt', 'D:\Program Files\Microvirt', 'C:\blue') | Where-Object { Test-Path $_ }
foreach ($d in $M) { Add-MpPreference -ExclusionPath $d -ErrorAction SilentlyContinue }
foreach ($x in 'MEmuHeadless.exe','MEmu.exe','MEmuConsole.exe','memuc.exe','adb.exe','node.exe') { Add-MpPreference -ExclusionProcess $x -ErrorAction SilentlyContinue }
Write-Host '[OK] Defender bo qua MEmu + BlueRoblox'
reg add HKCU\System\GameConfigStore /v GameDVR_Enabled /t REG_DWORD /d 0 /f | Out-Null
reg add HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR /v AllowGameDVR /t REG_DWORD /d 0 /f | Out-Null
Write-Host '[OK] Tat Xbox Game DVR'
""", log)
        self.tail(log, "Tối ưu Windows", 300)


    # ================= ĐƯỜNG THẲNG: khách nối thẳng về nhà, không vòng qua Cloudflare Hồng Kông =================
    def _cf(self, method, path, token, body=None):
        req = urllib.request.Request("https://api.cloudflare.com/client/v4" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode())

    def fast_dns(self, token=None, quiet=False):
        """Trỏ fast.<tên miền> về IP nhà mạng hiện tại (IP đổi thì tự cập nhật)."""
        token = token or conf().get("CF_DNS_TOKEN", "")
        if not token: return False
        try:
            ip = urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode().strip()
            z = self._cf("GET", f"/zones?name={ZONE}", token)["result"][0]["id"]
            recs = self._cf("GET", f"/zones/{z}/dns_records?type=A&name={FAST_HOST}", token)["result"]
            body = {"type": "A", "name": FAST_HOST, "content": ip, "ttl": 120, "proxied": False}
            if recs and recs[0]["content"] == ip:
                if not quiet: self.say("Việc đang làm", f"✓ {FAST_HOST} đã trỏ đúng IP {ip}")
                return True
            if recs: self._cf("PUT", f"/zones/{z}/dns_records/{recs[0]['id']}", token, body)
            else: self._cf("POST", f"/zones/{z}/dns_records", token, body)
            self.say("Việc đang làm", f"✓ Đã trỏ {FAST_HOST} → {ip}")
            return True
        except Exception as e:
            self.say("Việc đang làm", f"✗ Cập nhật tên miền đường thẳng lỗi: {e}"); return False

    def _lan_ip(self):
        try:
            s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s_.connect(("1.1.1.1", 80)); ip = s_.getsockname()[0]; s_.close(); return ip
        except Exception: return "?"

    def fast_setup(self):
        t = simpledialog.askstring("Đường thẳng (ít trễ)",
            "Cần 1 mã Cloudflare (API Token) quyền sửa tên miền:\n"
            "dash.cloudflare.com → góc phải: My Profile → API Tokens → Create Token → mẫu \"Edit zone DNS\"\n"
            f"→ Permissions bấm \"+ Add more\": Zone · Zone · Read → Zone Resources: chọn {ZONE}\n"
            "→ Continue → Create Token → Copy, rồi dán vào đây.\n"
            "(Mã chỉ lưu trong C:\\blue\\cloudphone.conf, không gửi đi đâu.)", show="•", parent=self.root)
        if not t: return
        t = t.strip()
        threading.Thread(target=self._fast_setup, args=(t,), daemon=True).start()

    def _fast_setup(self, token):
        S = lambda m: self.say("Việc đang làm", m)
        self.root.after(0, self.nb.select, len(SERVICES) + 1)
        S("\n===== Bật ĐƯỜNG THẲNG =====")
        try:
            self._cf("GET", f"/zones?name={ZONE}", token)["result"][0]["id"]
        except Exception as e:
            S(f"✗ Mã Cloudflare không dùng được ({e}). Tạo lại mã theo mẫu \"Edit zone DNS\" cho {ZONE}."); return
        S("✓ Mã Cloudflare dùng được")
        set_conf("CF_DNS_TOKEN", token)
        exe = os.path.join(B, "caddy.exe")
        if not os.path.isfile(exe):
            S("Đang tải Caddy (máy chủ HTTPS, bản chính thức caddyserver.com, ~40MB)…")
            try:
                urllib.request.urlretrieve(CADDY_URL, exe + ".part"); os.replace(exe + ".part", exe); S("✓ Đã tải Caddy")
            except Exception as e: S(f"✗ Tải Caddy lỗi: {e}"); return
        open(os.path.join(B, "Caddyfile"), "w", encoding="utf-8").write(
            "{\n\tadmin off\n}\n" + f"{FAST_HOST}:{FAST_PORT} {{\n\ttls {{\n\t\tdns cloudflare {{env.CF_API_TOKEN}}\n\t}}\n"
            "\treverse_proxy 127.0.0.1:8010 {\n\t\tflush_interval -1\n\t}\n}\n")
        if not self.fast_dns(token): return
        set_conf("FAST_BASE", f"https://{FAST_HOST}:{FAST_PORT}")
        log = os.path.join(LOGS, "fastfw.log")
        run_admin(f"netsh advfirewall firewall delete rule name='BlueRoblox duong thang' | Out-Null\n"
                  f"netsh advfirewall firewall add rule name='BlueRoblox duong thang' dir=in action=allow protocol=TCP localport={FAST_PORT}", log)
        self.tail(log, "Mở cổng 8443 trên tường lửa Windows", 120, wait=True)
        S("Đang bật lại dịch vụ để dùng đường thẳng…")
        self.stop_all(); time.sleep(2); self.root.after(0, self.start_all)
        lan = self._lan_ip()
        S("✅ Máy Windows đã sẵn sàng đường thẳng. VIỆC CUỐI — trên ROUTER (modem nhà mạng):")
        S(f"   Mở/chuyển cổng (Port Forwarding / NAT / Virtual Server): cổng ngoài {FAST_PORT} TCP → máy {lan} cổng {FAST_PORT}")
        S("   (trước đây cổng này trỏ về máy Ubuntu 192.168.1.21 → sửa thành IP máy Windows ở trên)")
        S(f"   Xong thì mở trang điều khiển máy trên web: góc trên hiện \"⚡ trễ mạng … ms\" là đang đi đường thẳng.")

    # ================= TỰ ĐỘNG A→Z =================
    def _ui(self, fn, *a):
        """Gọi hộp thoại trên luồng giao diện rồi chờ kết quả."""
        ev, box = threading.Event(), {}
        def w():
            try: box["r"] = fn(*a)
            finally: ev.set()
        self.root.after(0, w); ev.wait(); return box.get("r")

    def auto(self):
        if getattr(self, "_auto_on", False): return
        self._auto_on = True
        threading.Thread(target=self._auto, daemon=True).start()

    def _auto(self):
        S = lambda m: self.say("Tổng quan", m)
        res = []
        def step(name, ok, note=""):
            res.append((name, ok, note)); S(("✓ " if ok else "✗ ") + name + (f" — {note}" if note else ""))
        try:
            self.root.after(0, self.nb.select, 0)
            S("\n🚀 ========== TỰ ĐỘNG A→Z: bắt đầu ==========")
            # 1) cài đặt
            if not (os.path.isfile(os.path.join(B, "platform-tools", "adb.exe")) and os.path.isfile(os.path.join(B, "ws-scrcpy", "dist", "index.js"))):
                S("1/6 Đang cài đặt (Windows sẽ hỏi quyền Admin → bấm Yes)…")
                self.stop_all(); log = os.path.join(LOGS, "setup.log")
                try: os.remove(log)
                except OSError: pass
                run_admin(f"Set-Location C:\\\ncurl.exe -fsSL -H \"Accept: application/vnd.github.raw\" -H \"User-Agent: BlueRoblox\" -o C:\\blue\\setup.ps1 \"https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/setup.ps1\"; if ($LASTEXITCODE -ne 0) {{ curl.exe -fsSL -o C:\\blue\\setup.ps1 \"{RAW}/windows/setup.ps1?t={int(time.time())}\" }}\n& C:\\blue\\setup.ps1", log)
                self.tail(log, "Cài đặt", 3600, wait=True)
            ok = os.path.isfile(os.path.join(B, "ws-scrcpy", "dist", "index.js"))
            step("1/6 Cài đặt phần mềm", ok, "" if ok else "cài chưa xong — xem tab Việc đang làm")
            if not ok: return
            # 2) khoá Supabase (+ thử khoá)
            c = conf()
            if len(c.get("SUPABASE_SERVICE_KEY", "")) < 30: self._ui(self.set_key)
            c = conf(); okk = False
            try:
                rq = urllib.request.Request(c["SUPABASE_URL"].rstrip("/") + "/rest/v1/cloudphone_pricing?select=id&limit=1",
                                            headers={"apikey": c["SUPABASE_SERVICE_KEY"], "Authorization": "Bearer " + c["SUPABASE_SERVICE_KEY"]})
                okk = urllib.request.urlopen(rq, timeout=15).status == 200
            except Exception as e: S(f"   thử khoá: {e}")
            step("2/6 Khoá Supabase", okk, "" if okk else "khoá sai hoặc chưa dán — bấm ② dán lại")
            if not okk: return
            # 3) Cloudflare
            q = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
            if "SERVICE_NAME" not in q:
                t = self._ui(self.cf_token)
                if t: self.cf_install(t, wait=True)
            elif "RUNNING" not in q:
                run_admin("sc.exe start cloudflared", os.path.join(LOGS, "cfstart.log")); time.sleep(8)
            q = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, creationflags=NOWIN).stdout or ""
            step("3/6 Đường hầm Cloudflare", "RUNNING" in q, "" if "RUNNING" in q else "chưa chạy — bấm ③ dán lại lệnh connector")
            # 4) bật dịch vụ
            self.start_all()
            t0 = time.time()
            while time.time() - t0 < 90 and not (port_open(8000) and port_open(8010)): time.sleep(2)
            okd = port_open(8000) and port_open(8010) and self.svcs["cloudphoned"].alive()
            step("4/6 Bật trình phát hình + cổng bảo vệ + nhận đơn", okd, "" if okd else "xem tab ws-scrcpy / cpapi / cloudphoned")
            # 5) thử MEmu
            code, out = self.job("Danh sách máy", [PY, "phonectl.py", "list"], wait=True)
            if "chưa có máy nào" in out:
                S("5/6 Đang tạo máy thử test1 trên MEmu (1–3 phút)…")
                code, out = self.job("Tạo máy thử test1", [PY, "phonectl.py", "create", "test1", "--ram", "4", "--cpu", "4"], wait=True)
                okm = code == 0 and "✅" in out and "sẵn sàng" in out
                step("5/6 Tạo + điều khiển máy MEmu", okm, "" if okm else "lỗi tạo máy — chụp tab Việc đang làm gửi hỗ trợ")
                if okm: self.job("Xoá máy thử", [PY, "phonectl.py", "delete", "test1"], wait=True)
            else:
                step("5/6 Máy MEmu", True, "đã có máy đang chạy")
            # 6) web
            okw, note = False, ""
            try:
                rr = urllib.request.urlopen(urllib.request.Request(f"https://{pub_host()}/", headers={"User-Agent": "BlueRoblox-panel"}), timeout=15)
                okw = True; note = f"HTTP {rr.status}"
            except urllib.error.HTTPError as e:
                okw = e.code < 500; note = f"HTTP {e.code}" + ("" if okw else " — đường hầm chưa tới được máy này")
            except Exception as e: note = str(e)[:80]
            step(f"6/6 Web {pub_host()}", okw, note)
            bad = [r for r in res if not r[1]]
            S("🎉 ========== XONG: mọi thứ đã chạy! ==========" if not bad else f"⚠ ========== XONG, còn {len(bad)} mục lỗi (dòng ✗ ở trên) ==========")
            if not bad:
                code, out = self.job("Máy khách cần làm mới", [PY, "run.py", "remake.py", "list"], wait=True)
                m = re.findall(r"cần làm mới trên Windows: (\d+)", out)
                if m and m[-1] != "0" and self._ui(messagebox.askyesno, "Làm mới máy khách",
                        f"Có {m[-1]} máy khách cũ (từ server Ubuntu). Tạo lại tất cả trên MEmu ngay?\n(giữ chủ máy, cấu hình, hạn dùng; app/dữ liệu cũ mất)"):
                    self.job("Làm mới máy khách", [PY, "run.py", "remake.py", "all"], wait=True)
        except Exception as e:
            S(f"✗ Tự động bị lỗi: {e}")
        finally:
            self._auto_on = False

    def on_close(self):
        """Bấm X: chỉ THU NHỎ (dịch vụ vẫn chạy, khách vẫn dùng máy). Muốn tắt hẳn: nút ⏻ Thoát hẳn."""
        if any(s.alive() for s in self.svcs.values()):
            self.root.iconify(); self.say("Tổng quan", "ℹ Đã thu nhỏ — dịch vụ vẫn chạy. Muốn tắt hẳn: bấm ⏻ Thoát hẳn."); return
        self.root.destroy()
    def quit_all(self):
        if not messagebox.askyesno("Thoát hẳn", "TẮT toàn bộ dịch vụ (khách không dùng được máy, không nhận đơn mới) và đóng bảng?"): return
        self.stop_all(); self.root.destroy()

if __name__ == "__main__":
    _boost_self()
    try:   # chỉ mở 1 bảng điều khiển
        _lock = socket.socket(); _lock.bind(("127.0.0.1", 47123))
    except OSError:
        if "--auto" not in sys.argv:          # 14/11: bản tự chạy lúc đăng nhập thứ 2 (tác vụ + lối tắt) → thoát êm, không hiện hộp thoại
            ctypes.windll.user32.MessageBoxW(0, "Bảng điều khiển CloudBlue đang mở rồi.", "CloudBlue", 0)
        sys.exit(0)
    App(auto="--auto" in sys.argv).root.mainloop()
