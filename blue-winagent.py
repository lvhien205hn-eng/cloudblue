# -*- coding: utf-8 -*-
# =====================================================================
#  blue-winagent.py — CHẠY TRÊN MÁY WINDOWS có MEmu Play (Multiple Instance Manager) hoặc LDPlayer 9
#  Cho server Ubuntu (BlueRoblox) tự tạo / bật / tắt / xoá / đổi RAM máy giả lập qua mạng LAN.
#  Tự nhận MEmu trước (memuc.exe); muốn dùng LDPlayer: set BLUE_EMU=ld
#
#  Cách chạy (chuột phải Command Prompt → Run as administrator):
#     python blue-winagent.py            ← lần đầu in ra MÃ BÍ MẬT, dán vào server
#  Bảo mật: chỉ nhận lệnh từ đúng IP server (SERVER_IP) + đúng mã bí mật; tường lửa chỉ mở cho IP đó.
# =====================================================================
import ctypes, json, os, re, secrets, subprocess, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVER_IP = os.environ.get("BLUE_SERVER_IP", "192.168.1.21")    # IP server Ubuntu
LISTEN_PORT = 8765
EXT_BASE = 26000                       # cổng LAN cho máy số N = 26000 + N  (→ adb LDPlayer 127.0.0.1:5555 + 2N)
LD_DIRS = [os.environ.get("LDPLAYER_DIR", ""), r"C:\LDPlayer\LDPlayer9", r"D:\LDPlayer\LDPlayer9", r"C:\Program Files\LDPlayer\LDPlayer9",
           r"C:\leidian\LDPlayer9", r"D:\leidian\LDPlayer9"]
MEMU_DIRS = [os.environ.get("MEMU_DIR", ""), r"C:\Program Files\Microvirt\MEmu", r"D:\Program Files\Microvirt\MEmu",
             r"C:\Microvirt\MEmu", r"D:\Microvirt\MEmu", r"C:\Program Files (x86)\Microvirt\MEmu"]
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "blue-winagent.token")
LOCK = threading.Lock()

def _find(dirs, exe):
    for d in dirs:
        if d and os.path.isfile(os.path.join(d, exe)): return d
    return ""
MEMU = _find(MEMU_DIRS, "memuc.exe"); LD = _find(LD_DIRS, "ldconsole.exe")
EMU = os.environ.get("BLUE_EMU") or ("memu" if MEMU else "ld" if LD else "")

def run(args, timeout=120):
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=0x08000000)
        out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
        return r.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"

def ld(*a, timeout=120):
    return run([os.path.join(LD, "ldconsole.exe")] + [str(x) for x in a], timeout)
def memuc(*a, timeout=180):
    return run([os.path.join(MEMU, "memuc.exe")] + [str(x) for x in a], timeout)

def emu_list():
    res = []
    if EMU == "memu":      # memuc listvms: index,tên,cửa sổ,đang chạy(1/0),pid,dung lượng
        _, out = memuc("listvms")
        for line in out.splitlines():
            p = line.split(",")
            if len(p) >= 4 and p[0].strip().isdigit():
                res.append({"index": int(p[0]), "name": p[1].strip(), "running": p[3].strip() == "1", "w": 0, "h": 0, "dpi": 0})
        return res
    _, out = ld("list2")    # index, tên, top hwnd, bind hwnd, chạy, pid, vbox pid, w, h, dpi
    for line in out.splitlines():
        p = line.split(",")
        if len(p) >= 10 and p[0].strip().isdigit():
            res.append({"index": int(p[0]), "name": p[1], "running": p[4].strip() == "1",
                        "w": int(p[7] or 0), "h": int(p[8] or 0), "dpi": int(p[9] or 0)})
    return res
ld_list = emu_list

def by_name(name):
    return next((x for x in emu_list() if x["name"] == name), None)

def adb_cmd(idx, cmd, timeout=60):
    if EMU == "memu": return memuc("adb", "-i", idx, cmd, timeout=timeout)
    return ld("adb", "--index", idx, "--command", cmd, timeout=timeout)

def booted(idx):
    _, out = adb_cmd(idx, "shell getprop sys.boot_completed", 20)
    return out.strip().endswith("1")

def inner_port(idx):
    return 21503 + 10 * idx if EMU == "memu" else 5555 + 2 * idx     # cổng adb của giả lập trên Windows

def proxy(idx, on=True):
    ext, inner = EXT_BASE + idx, inner_port(idx)
    run(["netsh", "interface", "portproxy", "delete", "v4tov4", f"listenport={ext}", "listenaddress=0.0.0.0"])
    if on:
        run(["netsh", "interface", "portproxy", "add", "v4tov4", f"listenport={ext}", "listenaddress=0.0.0.0",
             f"connectport={inner}", "connectaddress=127.0.0.1"])
    return ext

def emu_add(name):
    if EMU == "memu":
        before = {x["index"] for x in emu_list()}
        code, out = memuc("create", "96", timeout=600)         # 96 = Android 9 64-bit
        m = re.search(r"index\D*(\d+)", out)
        idx = int(m.group(1)) if m else next(iter(sorted({x["index"] for x in emu_list()} - before)), None)
        if idx is None: return None, out
        memuc("rename", "-i", idx, name)
        return idx, out
    code, out = ld("add", "--name", name)
    p = by_name(name)
    return (p["index"] if p else None), out

def emu_launch(idx): return memuc("start", "-i", idx, timeout=300) if EMU == "memu" else ld("launch", "--index", idx)
def emu_quit(idx): return memuc("stop", "-i", idx) if EMU == "memu" else ld("quit", "--index", idx)
def emu_remove(idx): return memuc("remove", "-i", idx, timeout=300) if EMU == "memu" else ld("remove", "--index", idx)

def mem_info():
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.total / 2**30, 1), round(m.avail / 2**30, 1)

def configure(idx, ram, cpu, res, dpi):
    w, h = (res or "720x1280").lower().split("x")
    dpi = int(dpi or 320); mb = int(float(ram) * 1024)
    if EMU == "memu":
        for k, v in (("memory", mb), ("cpus", int(cpu)), ("is_customed_resolution", 1), ("resolution_width", w),
                     ("resolution_height", h), ("vbox_dpi", dpi), ("enable_su", 1)):
            memuc("setconfigex", "-i", idx, k, v)
        return 0, ""
    return ld("modify", "--index", idx, "--resolution", f"{w},{h},{dpi}", "--cpu", int(cpu), "--memory", mb, "--root", 1)

def wait_boot(idx, secs=300):
    t = time.time()
    while time.time() - t < secs:
        if booted(idx): return True
        time.sleep(3)
    return False

# ---------------- lệnh ----------------
def do_info(j):
    tot, av = mem_info()
    return {"ok": True, "emu": EMU, "ldplayer": (MEMU if EMU == "memu" else LD) or None, "cpu": os.cpu_count(), "ram_total": tot, "ram_free": av, "phones": emu_list()}

def do_create(j):
    name = j["name"]
    if not re.match(r"^[A-Za-z0-9_.-]{1,40}$", name): return {"ok": False, "err": "tên máy không hợp lệ"}
    if by_name(name): return {"ok": False, "err": "đã có máy tên này"}
    tot, av = mem_info()
    if av - float(j.get("ram", 4)) < float(j.get("reserve", 4)): return {"ok": False, "err": f"HẾT RAM: Windows còn {av}GB"}
    idx, out = emu_add(name)
    if idx is None: return {"ok": False, "err": "không tạo được máy: " + out[-300:]}
    configure(idx, j.get("ram", 4), j.get("cpu", 4), j.get("res"), j.get("dpi"))
    emu_launch(idx)
    ok = wait_boot(idx)
    ext = proxy(idx, True)
    return {"ok": ok, "index": idx, "ext_port": ext, "err": "" if ok else "máy chưa khởi động xong (quá 5 phút)"}

def _idx(j):
    p = by_name(j["name"]) if j.get("name") else None
    return p["index"] if p else int(j["index"])

def do_start(j):
    idx = _idx(j); emu_launch(idx); ok = wait_boot(idx); proxy(idx, True)
    return {"ok": ok, "index": idx, "ext_port": EXT_BASE + idx}

def do_stop(j):
    idx = _idx(j); emu_quit(idx); return {"ok": True}

def do_delete(j):
    idx = _idx(j); emu_quit(idx); time.sleep(4); proxy(idx, False)
    code, out = emu_remove(idx)
    return {"ok": True, "out": out[-200:]}

def do_resize(j):
    idx = _idx(j); emu_quit(idx); time.sleep(4)
    configure(idx, j["ram"], j["cpu"], j.get("res"), j.get("dpi"))
    emu_launch(idx); ok = wait_boot(idx); proxy(idx, True)
    return {"ok": ok}

def do_adb(j):
    code, out = adb_cmd(_idx(j), j["cmd"], int(j.get("timeout", 60)))
    return {"ok": code == 0, "out": out[-4000:]}

ACTS = {"info": do_info, "create": do_create, "start": do_start, "stop": do_stop, "delete": do_delete, "resize": do_resize, "adb": do_adb}

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        if self.client_address[0] not in (SERVER_IP, "127.0.0.1"): return self._send(403, {"ok": False, "err": "IP không được phép"})
        if not secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN): return self._send(403, {"ok": False, "err": "sai mã"})
        act = self.path.strip("/")
        try:
            j = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
        except Exception: return self._send(400, {"ok": False, "err": "dữ liệu lỗi"})
        if act not in ACTS: return self._send(404, {"ok": False, "err": "không có lệnh này"})
        try:
            with LOCK if act in ("create", "delete") else _Nop(): r = ACTS[act](j)
            self._send(200, r)
        except Exception as e:
            self._send(500, {"ok": False, "err": str(e)[:300]})
    def log_message(self, f, *a): print(time.strftime("%H:%M:%S"), self.client_address[0], f % a)

class _Nop:
    def __enter__(self): return self
    def __exit__(self, *a): return False

if __name__ == "__main__":
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("!! Hãy chạy bằng quyền Administrator (chuột phải Command Prompt → Run as administrator)."); input(); sys.exit(1)
    if not EMU:
        print("!! Không thấy MEmu (memuc.exe) hay LDPlayer 9 (ldconsole.exe). Đặt biến MEMU_DIR=thư mục cài MEmu."); input(); sys.exit(1)
    if not os.path.isfile(TOKEN_FILE):
        open(TOKEN_FILE, "w").write(secrets.token_hex(24))
    TOKEN = open(TOKEN_FILE).read().strip()
    # tường lửa: chỉ server được vào cổng lệnh + cổng máy
    run(["netsh", "advfirewall", "firewall", "delete", "rule", "name=BlueRoblox agent"])
    run(["netsh", "advfirewall", "firewall", "add", "rule", "name=BlueRoblox agent", "dir=in", "action=allow", "protocol=TCP",
         f"localport={LISTEN_PORT},{EXT_BASE}-{EXT_BASE + 199}", f"remoteip={SERVER_IP}"])
    print("=" * 60)
    print(" BlueRoblox Windows agent —", "MEmu:" if EMU == "memu" else "LDPlayer:", MEMU if EMU == "memu" else LD)
    print(" Chỉ nhận lệnh từ server:", SERVER_IP, " cổng", LISTEN_PORT)
    print(" MÃ BÍ MẬT (dán vào server):", TOKEN)
    print("=" * 60)
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), H).serve_forever()
