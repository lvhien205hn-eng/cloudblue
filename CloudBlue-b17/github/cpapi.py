#!/usr/bin/env python3
# cpapi.py — CỔNG BẢO VỆ + API điều khiển điện thoại đám mây.
#  • Đứng TRƯỚC ws-scrcpy (cổng 8000): khách chỉ mở được máy CỦA MÌNH, admin mở được tất cả.
#  • API /cpapi/...: phím Home/Back/Đa nhiệm/âm lượng, tải file & APK lên, cài từ link,
#    chụp màn hình, mở link, quản lý ứng dụng, khởi động lại máy.
# Cloudflare tunnel: phone.cloudblue.vn → http://localhost:8010   (KHÔNG trỏ thẳng 8000 nữa)
# Cấu hình đọc chung ~/cloudphone.conf (SUPABASE_URL, SUPABASE_SERVICE_KEY, PUBLIC_BASE).
import base64, hashlib, hmac, http.client, ipaddress, json, os, re, secrets, shlex, shutil, socket
import subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
SHOTS = {}          # (cổng, cỡ) → (lúc chụp, ảnh, loại) — ảnh màn hình nhỏ cho danh sách máy
LIVE = {}           # cổng → số người ĐANG điều khiển/xem trực tiếp (luồng hình) — máy đó KHÔNG chụp ảnh nhỏ để luồng hình không bị giật
import threading as _th
SHOT_SEM = _th.Semaphore(2)   # cả máy chủ chỉ chụp 2 ảnh cùng lúc — tránh dồn ảnh thô (~3.7MB/ảnh) làm nghẽn adb của mọi máy

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, "cloudphone.conf")
LISTEN = ("127.0.0.1", 8010)
UPSTREAM = ("127.0.0.1", 8000)          # ws-scrcpy
WSNAME = "wsscrcpy"
UP_DIR = os.path.join(HOME, "redroid", "_uploads")
SECRET_FILE = os.path.join(HOME, ".cpapi_secret")
COOKIE = "cpauth"
COOKIE_TTL = 12 * 3600
REAUTH_S = 20                     # phiên xem đang mở: kiểm lại quyền mỗi 20 giây
MAX_CHUNK = 60 * 1024 * 1024            # Cloudflare giới hạn 100MB/lần gửi → chia nhỏ
MAX_FILE = 4 * 1024 ** 3                # tối đa 4GB / file
KEYS = {3: "Home", 4: "Back", 66: "Enter", 67: "Xoá", 187: "Đa nhiệm", 24: "Tăng âm", 25: "Giảm âm", 164: "Tắt tiếng",
        26: "Nguồn", 82: "Menu", 279: "Dán", 278: "Copy", 277: "Cắt", 224: "Đánh thức", 223: "Ngủ", 220: "Giảm sáng", 221: "Tăng sáng"}
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PKG = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")


def load_conf():
    c = {}
    try:
        for line in open(CONF, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); c[k.strip()] = v.strip()
    except FileNotFoundError:
        print("THIẾU file cấu hình:", CONF); sys.exit(1)
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "PUBLIC_BASE"):
        if not c.get(k): print("THIẾU", k, "trong", CONF); sys.exit(1)
    return c


CFG = load_conf()
SB = CFG["SUPABASE_URL"].rstrip("/")
KEY = CFG["SUPABASE_SERVICE_KEY"]
PUBLIC_HOST = urllib.parse.urlparse(CFG["PUBLIC_BASE"]).netloc or "phone.cloudblue.vn"
SELF_ORIGIN = "https://" + PUBLIC_HOST
# Đường thẳng (không qua Cloudflare): FAST_BASE=https://fast.blueroblox.shop:8443 trong ~/cloudphone.conf (do fast-route.sh ghi)
FAST_ORIGIN = (CFG.get("FAST_BASE") or "").strip().rstrip("/")
NODE_ID = CFG.get("NODE_ID") or socket.gethostname()      # nhiều server: mỗi server chỉ phục vụ máy của mình
PRIMARY = CFG.get("PRIMARY", "1") == "1"
def on_node(p):
    n = (p or {}).get("node")
    return n == NODE_ID or (not n and PRIMARY)
SELF_ORIGINS = {SELF_ORIGIN} | ({FAST_ORIGIN} if FAST_ORIGIN else set())
# Trang web được gọi cpapi: tên miền mới cloudblue.vn + tên miền cũ (vẫn chạy khi được mở lại) + CPAPI_ORIGINS trong cloudphone.conf
ORIGINS = {"https://cloudblue.vn", "https://www.cloudblue.vn", "https://blueroblox.shop", "https://www.blueroblox.shop"} | \
          {o.strip().rstrip("/") for o in CFG.get("CPAPI_ORIGINS", "").split(",") if o.strip()}


def load_secret():
    try:
        s = open(SECRET_FILE, "rb").read().strip()
        if len(s) >= 32: return s
    except FileNotFoundError:
        pass
    s = secrets.token_hex(32).encode()
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, s); os.close(fd)
    return s


SECRET = load_secret()
os.makedirs(UP_DIR, exist_ok=True)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------- Supabase ----------------
def sb_get(path, token=None):
    req = urllib.request.Request(SB + path, headers={"apikey": KEY, "Authorization": "Bearer " + (token or KEY)})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode()
        return json.loads(t) if t else None


def sb_patch(path, body):
    req = urllib.request.Request(SB + path, data=json.dumps(body).encode(), method="PATCH",
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=15) as r: r.read()


def fps_limits():
    try:
        p = (sb_get("/rest/v1/cloudphone_pricing?id=eq.1&select=min_fps,max_fps") or [{}])[0]
        return int(p.get("min_fps") or 10), int(p.get("max_fps") or 120)
    except Exception:
        return 10, 120


_mcache = {"t": 0, "v": {"maint": False}}
def maint():
    """Trạng thái bảo trì (đọc lại mỗi 20 giây)."""
    if time.time() - _mcache["t"] > 20:
        try:
            req = urllib.request.Request(SB + "/rest/v1/rpc/cloudphone_status", data=b"{}", method="POST",
                                         headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r: _mcache["v"] = json.loads(r.read().decode() or "{}")
        except Exception:
            pass
        _mcache["t"] = time.time()
    return _mcache["v"]


def maint_text():
    m = maint()
    return "Hệ thống đang bảo trì" + (": " + m["maint_msg"] if m.get("maint_msg") else "") + ". Vui lòng quay lại sau."


_ucache, _pcache = {}, {}
_busy = set()          # máy đang khởi động lại / đổi cấu hình
_rootbusy = set()      # máy đang lưu cấu hình root theo app (1 việc / máy)
_REBOOT = {"t": 0}     # lúc admin bấm khởi động lại CẢ máy chủ (chặn bấm 2 lần)
_DONSACH = {"t": 0}   # admin đang bấm 🧹 dọn máy cũ trên máy chủ này (chặn bấm chồng)
IS_WIN = os.name == "nt"


def whoami(token):
    """Kiểm tra token đăng nhập của khách (do Supabase cấp) → {uid, admin}."""
    if not token or len(token) > 4096: return None
    now = time.time(); c = _ucache.get(token)
    if c and c[1] > now: return c[0]
    try:
        u = sb_get("/auth/v1/user", token)
    except Exception:
        return None
    uid = u.get("id") if isinstance(u, dict) else None
    if not uid or not UUID.match(uid): return None
    try:
        rows = sb_get(f"/rest/v1/profiles?id=eq.{uid}&select=role,locked") or []
        p = rows[0] if rows else {}
    except Exception:
        p = {}
    if p.get("locked"): return None
    me = {"uid": uid, "admin": p.get("role") == "admin"}
    if len(_ucache) > 5000: _ucache.clear()
    _ucache[token] = (me, now + 300)
    return me


def is_locked(p):
    if not p.get("locked"): return False
    u = p.get("locked_until")
    if not u: return True
    try:
        return datetime_parse(u) > time.time()
    except Exception:
        return True


def datetime_parse(s):
    import datetime as _dt
    return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def lock_text(p):
    u = p.get("locked_until")
    when = ""
    if u:
        import datetime as _dt
        vn = _dt.timezone(_dt.timedelta(hours=7))          # giờ Việt Nam (server chạy giờ UTC)
        when = " đến " + _dt.datetime.fromtimestamp(datetime_parse(u), vn).strftime("%H:%M %d/%m/%Y")
    return "Máy đang bị khoá" + (when or " vĩnh viễn") + (": " + p["lock_reason"] if p.get("lock_reason") else "") + ". Liên hệ hỗ trợ nếu cần."


_scache = {}
def share_users(pid):
    """Người đang được chủ máy chia sẻ quyền điều khiển (bảng cloud_phone_shares, SQL v9). Chưa chạy v9 → rỗng."""
    now = time.time(); c = _scache.get(pid)
    if c and c[1] > now: return c[0]
    try:
        rows = sb_get(f"/rest/v1/cloud_phone_shares?phone_id=eq.{pid}&kind=eq.share&revoked=is.false&grantee_id=not.is.null"
                      f"&select=grantee_id,expires_at") or []
        users = {r["grantee_id"] for r in rows if not r.get("expires_at") or datetime_parse(r["expires_at"]) > now}
    except Exception:
        users = set()
    if len(_scache) > 5000: _scache.clear()
    _scache[pid] = (users, now + 20)
    return users


def phone_of(me, pid):
    if not UUID.match(pid or ""): return None
    rows = sb_get(f"/rest/v1/cloud_phones?id=eq.{pid}&select=*") or []
    if not rows: return None
    p = rows[0]
    if not me["admin"] and p.get("user_id") != me["uid"] and me["uid"] not in share_users(pid): return None
    if not on_node(p): return None                  # máy nằm ở server khác (cổng trùng số) → không được đụng vào máy ở đây
    return p


def port_owners(port):
    now = time.time(); c = _pcache.get(port)
    if c and c[1] > now: return c[0]
    rows = [r for r in (sb_get(f"/rest/v1/cloud_phones?port=eq.{int(port)}&status=eq.active&locked=is.false&select=id,user_id,node") or []) if on_node(r)]
    owners = {r["user_id"] for r in rows}
    for r in rows: owners |= share_users(r["id"])          # người được chia sẻ cũng xem/điều khiển được
    _pcache[port] = (owners, now + 20)
    return owners


# ---------------- Cookie ký HMAC (cho trình điều khiển) ----------------
def _mac(raw):
    return hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()[:40]


def sign(d):
    raw = base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")
    return raw + "." + _mac(raw)


def verify(v):
    try:
        raw, mac = v.rsplit(".", 1)
        if not hmac.compare_digest(mac, _mac(raw)): return None
        d = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return d if d.get("exp", 0) > time.time() else None
    except Exception:
        return None


# ---------------- ADB ----------------
def adb(port, args, timeout=60):
    serial = f"127.0.0.1:{int(port)}"
    cmd = ["docker", "exec", WSNAME, "adb", "-s", serial] + args
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    err = (r.stderr or b"").decode(errors="ignore")
    if r.returncode != 0 and ("not found" in err or "offline" in err):
        subprocess.run(["docker", "exec", WSNAME, "adb", "connect", serial], capture_output=True, timeout=20)
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r


def shell(port, cmd, timeout=60):
    return adb(port, ["shell", cmd], timeout)


# Đầu lệnh shell: Android 10+ → biến $W = "--windowingMode 1 --display 0" (mở app TOÀN MÀN, không thành cửa sổ nổi, và luôn ở MÀN CHÍNH:
# Android 14/15 mỗi luồng hình scrcpy là 1 màn ảo — mở bằng lệnh có thể rơi lên màn ảo, khách không thấy); Android cũ → $W rỗng
FULLSCREEN_SH = "W=; [ \"$(getprop ro.build.version.sdk)\" -ge 29 ] 2>/dev/null && W='--windowingMode 1 --display 0'; "
# Mở link / trang Play: chỉ thêm "--display 0" (Android 10+), không ép toàn màn
MAIN_SH = "D=; [ \"$(getprop ro.build.version.sdk)\" -ge 29 ] 2>/dev/null && D='--display 0'; "
# Mở app y như bấm biểu tượng trên màn hình chính (MAIN + LAUNCHER + NEW_TASK|RESET_TASK_IF_NEEDED): app đang chạy → chỉ đưa lên trước,
# KHÔNG mở thêm 1 màn khởi động nữa (am start -n trơn sẽ chồng thêm màn mở đầu lên app đang chạy)
AS_ICON = "-a android.intent.action.MAIN -c android.intent.category.LAUNCHER -f 0x10200000"


def out(r):
    return ((r.stdout or b"") + (r.stderr or b"")).decode(errors="ignore").strip()


# ---------------- Việc chạy nền (cài APK, tải link, khởi động lại) ----------------
JOBS, JLOCK = {}, threading.Lock()
VIEWERS, VLOCK = {}, threading.Lock()      # cổng máy → nơi đang xem (mã trang cpv)


def new_job(owner, title):
    jid = secrets.token_hex(8)
    with JLOCK:
        for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 3600]: JOBS.pop(k, None)
        JOBS[jid] = {"owner": owner, "state": "running", "title": title, "msg": "Đang xử lý…", "t": time.time()}
    return jid


def run_job(jid, fn):
    def go():
        try:
            JOBS[jid].update(state="done", msg=fn(jid))
        except Exception as e:
            JOBS[jid].update(state="error", msg=str(e)[:400])
            log("job lỗi:", e)
    threading.Thread(target=go, daemon=True).start()



# ---------- Biểu tượng "Clone 1/2/3/4" trên màn hình chính máy MEmu (màn hình chính MEmu không có tab Công việc) ----------
BR_PKG = "shop.blueroblox.app"
# Nơi tải app Android: web trước, web hỏng (tên miền bị khoá…) thì lấy thẳng file trên GitHub
APP_SRC = [b.rstrip("/") for b in (CFG.get("APP_DOWNLOAD") or "https://cloudblue.vn/download").split(",") if b.strip()] + \
          ["https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/blueroblox-site/download"]
def clone_icons(port):
    """Cài app BlueRoblox (có ô mở clone) vào máy — CHỈ cho người dùng chính, rồi bật đúng số biểu tượng Clone N + làm mới màn hình chính."""
    try:
        apk = os.path.join(HOME, "blueroblox-cloud.apk")
        vc = re.search(r"versionCode=(\d+)", out(shell(port, f"dumpsys package {BR_PKG} | grep -m1 versionCode", 20)))
        latest, src = 24, APP_SRC[-1]
        for b in APP_SRC:      # bản app mới nhất (cài lại nếu máy đang có bản cũ hơn → luôn có đủ biểu tượng Clone)
            try:
                latest = int(json.loads(urllib.request.urlopen(b + "/app.json?t=" + str(int(time.time())), timeout=15).read()).get("code") or 0); src = b; break
            except Exception: pass
        has = bool(vc and int(vc.group(1)) >= max(latest, 21))
        if not has:
            got = False
            for b in [src] + [x for x in APP_SRC if x != src]:
                try:
                    urllib.request.urlretrieve(b + "/blueroblox-cloud.apk?t=" + str(int(time.time())), apk + ".part"); got = True; break
                except Exception as e: log("tải app BlueRoblox lỗi:", b, e)
            if not got: raise RuntimeError("không tải được app BlueRoblox (web + GitHub)")
            os.replace(apk + ".part", apk)
            adb(port, ["install", "-r", "--user", "0", apk], timeout=300)
            shell(port, f"pm disable {BR_PKG}/.LoginActivity >/dev/null 2>&1 || su -c 'pm disable {BR_PKG}/.LoginActivity' >/dev/null 2>&1", 20)
        LU = "pm list users | sed -n 's/.*UserInfo{\\([0-9]*\\):CloneTab[0-9]*:.*/\\1/p'"
        n = 0
        for u in out(shell(port, LU, 20)).split():
            shell(port, f"pm uninstall --user {u} {BR_PKG} >/dev/null 2>&1", 30)          # app BlueRoblox không nằm trong bản clone
            if any(l.startswith("package:") and l.split(":", 1)[1].strip() != BR_PKG
                   for l in out(shell(port, f"pm list packages -3 --user {u}", 20)).splitlines()): n += 1
        cmds = "; ".join(f"pm {'enable' if i <= n else 'disable'} {BR_PKG}/.Clone{i} >/dev/null 2>&1 || su -c 'pm {'enable' if i <= n else 'disable'} {BR_PKG}/.Clone{i}' >/dev/null 2>&1" for i in range(1, 5))
        # màn hình chính MEmu chỉ quét app lúc mở → khởi động lại màn hình chính để hiện biểu tượng mới
        shell(port, cmds + "; L=$(cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME | tail -n 1 | cut -d/ -f1); "
                    "[ -n \"$L\" ] && am force-stop $L; " + MAIN_SH + "am start $D -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1", 40)
        return n
    except Exception as e:
        log("clone_icons lỗi:", repr(e)); return -1

def safe_name(n):
    n = os.path.basename((n or "").replace("\\", "/")).strip()
    n = re.sub(r"[^\w.\-() \[\]+]", "_", n)[:120].strip(" .")
    return n or ("file_" + secrets.token_hex(3))


INSTALL_ERR = [   # lỗi cài APK thường gặp → lời báo dễ hiểu
    ("OLDER_SDK", "App này cần bản Android mới hơn máy của bạn — chọn máy Android mới hơn, hoặc tìm bản cũ hơn của app."),
    ("NO_MATCHING_ABIS", "File APK này không hợp với máy (sai loại chip). Hãy tải bản \"universal\" hoặc bản arm64/x86_64 của app."),
    ("INSUFFICIENT_STORAGE", "Máy hết bộ nhớ — gỡ bớt app hoặc xoá file trong Download rồi thử lại."),
    ("UPDATE_INCOMPATIBLE", "Máy đã có app này nhưng khác chữ ký (bản mod / bản khác nguồn). Gỡ app cũ trong \"Ứng dụng\" rồi cài lại."),
    ("VERSION_DOWNGRADE", "Máy đang có bản MỚI hơn file này. Gỡ app cũ trước nếu muốn cài bản cũ."),
    ("INVALID_APK", "File APK bị hỏng hoặc tải chưa hết — tải lại file rồi thử lại."),
    ("NOT_APK", "File APK bị hỏng hoặc tải chưa hết — tải lại file rồi thử lại."),
    ("MISSING_SPLIT", "App này phải cài kèm các phần khác — dùng file .apks / .xapk đầy đủ thay vì chỉ 1 file .apk."),
    ("DUPLICATE_PERMISSION", "App này trùng quyền với 1 app đã cài (thường là bản mod/bản sao). Gỡ app kia rồi thử lại."),
    ("TEST_ONLY", "File này là bản thử nghiệm (test-only), Android không cho cài."),
]
def install_err(o):
    for k, msg in INSTALL_ERR:
        if k in o: return msg
    return "Cài APK lỗi: " + o[-300:]

# ---------- MÁY THỬ GPU (Android Emulator chạy bằng GTX 1080, tạo bằng ~/gpu-phone-test.sh) ----------
GPU_SCRIPT = os.path.join(HOME, "gpu-phone-test.sh")
GPU_PORT = 5601               # adb của máy thử (console 5600)
GPU_IMGS = {"9": "system-images;android-28;google_apis_playstore;x86", "10": "system-images;android-29;google_apis_playstore;x86",
            "11": "system-images;android-30;google_apis_playstore;x86_64", "12": "system-images;android-31;google_apis_playstore;x86_64"}

def gpu_adb(cmd, timeout=20):
    e = dict(os.environ); e["ANDROID_ADB_SERVER_PORT"] = "5038"
    r = subprocess.run([os.path.join(HOME, "android-sdk", "platform-tools", "adb"), "-s", "emulator-5600", "shell", cmd],
                       capture_output=True, text=True, timeout=timeout, env=e)
    return (r.stdout or "") if r.returncode == 0 else ""

def gpu_status():
    d = {"installed": os.path.isfile(GPU_SCRIPT) and os.path.isdir(os.path.join(HOME, "android-sdk", "emulator")), "running": False}
    pr = subprocess.run(["pgrep", "-f", "-o", "--", "-avd gputest"], capture_output=True, text=True)
    pid = (pr.stdout or "").strip()
    d["running"] = bool(pid)
    if pid:
        try:
            ps = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", pid], capture_output=True, text=True).stdout.split()
            d["cpu"] = float(ps[0]); d["ram_gb"] = round(int(ps[1]) / 1048576, 1)
        except Exception: pass
        try:
            ls = [l.strip() for l in gpu_adb("getprop sys.boot_completed; getprop ro.build.version.release; getprop ro.product.cpu.abilist; dumpsys SurfaceFlinger | grep -m1 GLES:").splitlines()]
            if ls and ls[0] not in ("0", "1", ""): ls = []        # máy chưa sẵn sàng / adb báo lỗi → bỏ qua
            d["booted"] = bool(ls and ls[0] == "1")
            if len(ls) > 1: d["android"] = ls[1]
            if len(ls) > 2: d["abi"] = ls[2]
            if len(ls) > 3: d["gles"] = ls[3].replace("GLES:", "").strip()
        except Exception: pass
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10).stdout.strip().split(",")
        d["gpu"] = {"name": g[0].strip(), "util": int(g[1]), "mem": int(g[2]), "total": int(g[3])}
    except Exception: pass
    gl = (d.get("gles") or "").lower()
    d["on_gpu"] = "nvidia" in gl or "geforce" in gl
    d["stream_url"] = stream_url_of(GPU_PORT) if d.get("booted") else None
    return d

def stream_url_of(port):
    q = urllib.parse.quote; base = "https://" + PUBLIC_HOST; udid = f"127.0.0.1:{port}"
    ws = base.replace("https://", "wss://") + "/?action=proxy-adb&remote=" + q("tcp:8886", safe="") + "&udid=" + q(udid, safe="")
    # máy GPU (máy ảo Google): dùng trình phát tinyh264 (giải mã bằng JS/WASM) — webcodecs của Chrome có thể từ chối loại hình máy GPU gửi ra
    return f"{base}/#!action=stream&udid={q(udid, safe='')}&player=tinyh264&ws={q(ws, safe='')}"

def gpu_run(args, env=None, timeout=1800):
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(["bash", GPU_SCRIPT] + args, capture_output=True, text=True, timeout=timeout, env=e, stdin=subprocess.DEVNULL)
    txt = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))
    return r.returncode, txt

def sniff_apk(path):
    """File không có đuôi nhưng thật ra là APK / gói APK → trả về đuôi đúng."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            ns = z.namelist()
            if "AndroidManifest.xml" in ns: return "apk"
            if any(n.lower().endswith(".apk") for n in ns): return "xapk" if "manifest.json" in ns else "apks"
    except Exception: pass
    return ""

def deliver(port, path, name, jid=None):
    """File đã nằm trên server → đưa vào máy: APK / gói APK (.apks .xapk .apkm) thì cài, file khác vào thư mục Download."""
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    ext = re.sub(r"[^a-z0-9]", "", ext)[:10]
    if ext not in ("apk", "apks", "xapk", "apkm"):
        e2 = sniff_apk(path)
        if e2 and ext in ("", "bin", "zip", "tmp", "download"): name = (name.rsplit(".", 1)[0] if ext else name) + "." + e2; ext = e2
    tmp = "/tmp/cpup_" + secrets.token_hex(6) + ("." + ext if ext else "")   # adb install bắt buộc tên file đuôi .apk
    try:
        if ext in ("apks", "xapk", "apkm"):              # gói nhiều phần (game tải từ APKPure… hay dùng .xapk)
            if jid: JOBS[jid]["msg"] = "Đang giải nén gói ứng dụng…"
            files, dst = stage_pkg(path, name)
            try:
                if jid: JOBS[jid]["msg"] = "Đang cài ứng dụng…"
                args = (["install", "-r", "-g", files[0]] if len(files) == 1 else ["install-multiple", "-r", "-g"] + files)
                o = out(adb(port, args, timeout=1200))
                if "Success" not in o: raise RuntimeError(install_err(o))
            finally:
                subprocess.run(["docker", "exec", WSNAME, "rm", "-rf", dst], capture_output=True, timeout=60)
            obb = push_obb(port, path, jid)
            return f"Đã cài xong {name}" + (f" (kèm {obb} file dữ liệu game)" if obb else "")
        if jid: JOBS[jid]["msg"] = "Đang chép vào máy…"
        r = subprocess.run(["docker", "cp", path, f"{WSNAME}:{tmp}"], capture_output=True, timeout=900)
        if r.returncode: raise RuntimeError("Không chép được file: " + out(r)[-200:])
        if ext == "apk":
            if jid: JOBS[jid]["msg"] = "Đang cài ứng dụng…"
            r = adb(port, ["install", "-r", "-g", tmp], timeout=1200)
            o = out(r)
            if "Success" not in o: raise RuntimeError(install_err(o))
            return f"Đã cài xong {name}"
        dest = "/sdcard/Download/" + name
        r = push_sd(port, tmp, dest, timeout=1200)
        if not pushed_ok(r):
            if "No space" in out(r): raise RuntimeError("Máy hết bộ nhớ — xoá bớt file / gỡ bớt app rồi thử lại.")
            raise RuntimeError("Không chép được file vào máy: " + out(r)[-200:])
        shell(port, "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d " + shlex.quote("file://" + dest), 30)
        return f"Đã lưu vào thư mục Download: {name}"
    finally:
        subprocess.run(["docker", "exec", WSNAME, "rm", "-f", tmp], capture_output=True, timeout=60)
        try: os.remove(path)
        except OSError: pass

def push_sd(port, src, dest, timeout=1800):
    """Chép file (đang nằm trong ws-scrcpy) vào bộ nhớ máy /sdcard/…
    adb push thẳng vào /sdcard lỗi trên Android 9/10 ("remote fchown failed") → chép vào /data/local/tmp rồi cp sang."""
    tmp = "/data/local/tmp/.cpin_" + secrets.token_hex(5)
    r = adb(port, ["push", src, tmp], timeout=timeout)
    if r.returncode: return r
    d = shlex.quote(dest)
    return adb(port, ["shell", f"mkdir -p {shlex.quote(os.path.dirname(dest))}; cp {tmp} {d} && echo CPOK; rm -f {tmp}"], timeout=timeout)

def pushed_ok(r):
    return r.returncode == 0 and "CPOK" in out(r)

def push_obb(port, path, jid=None):
    """Gói .xapk có dữ liệu game (Android/obb/…) → chép vào /sdcard/Android/obb của máy. Trả về số file đã chép."""
    import zipfile, tempfile
    try:
        with zipfile.ZipFile(path) as z:
            obbs = [n for n in z.namelist() if re.match(r"^Android/obb/[\w.]+/[^/]+\.obb$", n)]
            if not obbs: return 0
            d = tempfile.mkdtemp(prefix="obb_", dir=UP_DIR)
            try:
                n = 0
                for f in obbs:
                    if jid: JOBS[jid]["msg"] = f"Đang chép dữ liệu game {n + 1}/{len(obbs)}…"
                    z.extract(f, d); tag = "/tmp/obb_" + secrets.token_hex(5)
                    subprocess.run(["docker", "cp", os.path.join(d, f), f"{WSNAME}:{tag}"], capture_output=True, timeout=1200)
                    r = push_sd(port, tag, "/sdcard/" + f, timeout=1800)
                    subprocess.run(["docker", "exec", WSNAME, "rm", "-f", tag], capture_output=True, timeout=60)
                    os.remove(os.path.join(d, f)); n += 1 if pushed_ok(r) else 0
                return n
            finally: shutil.rmtree(d, ignore_errors=True)
    except zipfile.BadZipFile:
        return 0


# ---------------- Admin: cài 1 APK vào nhiều máy cùng lúc ----------------
APK_EXT = (".apk", ".apks", ".apkm", ".xapk")
ADMIN_FILES = {}          # mã file → (đường dẫn, tên)
CLONE_MAX = 4             # tối đa số bản clone / app / máy (cần gói chỉnh cloudphone-multiclone.sh; không có thì Android chỉ cho 1)


def apk_min_sdk(path):
    """Đọc minSdkVersion (bản Android thấp nhất app cần) từ file .apk / gói .apks. Không đọc được → 0 (coi như cài được)."""
    import zipfile, struct
    try:
        with zipfile.ZipFile(path) as z:
            data = None
            if "AndroidManifest.xml" in z.namelist(): data = z.read("AndroidManifest.xml")
            else:
                ns = [n for n in z.namelist() if n.lower().endswith(".apk") and "/" not in n.strip("/")]
                ns.sort(key=lambda n: (0 if n.lower() in ("base.apk",) else 1 if "split" not in n.lower() else 2, n))
                if ns:
                    import io
                    with zipfile.ZipFile(io.BytesIO(z.read(ns[0]))) as b: data = b.read("AndroidManifest.xml")
        if not data: return 0
        strs, resmap, off = [], [], 8
        while off + 8 <= len(data):
            typ, hsz, sz = struct.unpack_from("<HHI", data, off)
            if sz < 8: break
            if typ == 0x0001:                                  # bảng chữ
                cnt, _, flags, sstart = struct.unpack_from("<IIII", data, off + 8)
                utf8 = flags & 0x100
                for i in range(cnt):
                    p = off + struct.unpack_from("<I", data, off + hsz + i * 4)[0] + sstart
                    if utf8:
                        n = data[p]; p += 2 if n & 0x80 else 1
                        n = data[p]; q = p + (2 if n & 0x80 else 1)
                        if n & 0x80: n = ((n & 0x7f) << 8) | data[p + 1]
                        strs.append(data[q:q + n].decode("utf-8", "replace"))
                    else:
                        n = struct.unpack_from("<H", data, p)[0]
                        strs.append(data[p + 2:p + 2 + n * 2].decode("utf-16le", "replace"))
            elif typ == 0x0180:
                resmap = list(struct.unpack_from("<%dI" % ((sz - 8) // 4), data, off + 8))
            elif typ == 0x0102:                                # thẻ mở
                name = struct.unpack_from("<I", data, off + 20)[0]
                if 0 <= name < len(strs) and strs[name] == "uses-sdk":
                    astart, asize, acnt = struct.unpack_from("<HHH", data, off + 24)
                    for i in range(acnt):
                        a = off + 16 + astart + i * asize
                        an = struct.unpack_from("<I", data, a + 4)[0]
                        dtype, val = data[a + 15], struct.unpack_from("<I", data, a + 16)[0]
                        if (an < len(resmap) and resmap[an] == 0x0101020c) or (an < len(strs) and strs[an] == "minSdkVersion"):
                            return val if dtype in (0x10, 0x11) else int(strs[val]) if dtype == 0x03 and strs[val].isdigit() else 0
                    return 1
            off += sz
    except Exception:
        return 0
    return 0

_MINSDK = {}
def min_sdk(path):
    k = (path, os.path.getmtime(path))
    if k not in _MINSDK: _MINSDK[k] = apk_min_sdk(path)
    return _MINSDK[k]

def for_sdk(fname, path, sdk):
    """App trong kho có chạy được trên máy SDK này không. File tên có '-sdkNN-' (lấy riêng cho Android cũ) chỉ dành cho đúng máy SDK đó;
    file thường bị ẩn trên máy cũ nếu cần Android mới hơn, và nhường chỗ cho bản '-sdkNN-' cùng tên nếu có."""
    if not sdk: return True
    m = re.search(r"-sdk(\d+)-", fname)
    if m: return int(m.group(1)) == sdk
    return min_sdk(path) <= sdk

# ---------- 🛍 KHO APP: app hay dùng (Termux, MT Manager, ZArchiver…) — máy chủ tự tải TỪ TRANG CHÍNH CHỦ, lưu ở ~/kho-app, khách cài 1 chạm ----------
# KHÔNG lấy ở trang mirror. Mỗi app: nguồn chính chủ + tên gói phải khớp (file tải về mà tên gói khác → bỏ, không cài).
# Tải lần đầu (vài giây – 1 phút), máy sau cài ngay từ bản đã lưu; 12 giờ xem lại nguồn 1 lần để lấy bản mới. Admin vẫn bỏ thêm app riêng vào ~/apk-cai-san.
KHO_APPS = [
    {"id": "termux", "name": "Termux", "pkg": "com.termux", "icon": "⌨️",
     "desc": "Dòng lệnh Linux: pkg, python, git, ssh… (dùng chung với Root)", "desc_en": "Linux terminal: pkg, python, git, ssh…",
     "src": "github", "repo": "termux/termux-app", "asset": r"^termux-app_v[\w.\-]+\+(?:apt-android-7-)?github-debug_({abi})\.apk$", "sums": r"sha256sums$",
     "home": "https://github.com/termux/termux-app"},
    {"id": "mt", "name": "MT Manager", "pkg": "bin.mt.plus", "icon": "🗂️",
     "desc": "Quản lý file 2 cửa sổ, sửa file, giải nén, xem APK", "desc_en": "Dual-pane file manager, editor, archives",
     "src": "page", "page": "https://mt.cc/download/", "link": r"https://pan\.mt2\.cn/apk/(\d+)(?![\w/])", "home": "https://mt.cc"},
    {"id": "zarchiver", "name": "ZArchiver", "pkg": "ru.zdevs.zarchiver", "icon": "🗜️",
     "desc": "Giải nén / nén zip, rar, 7z, cài file .xapk / .apks", "desc_en": "Extract / create zip, rar, 7z; install .xapk / .apks",
     "src": "page", "page": "https://zdevs.ru/en/za/apk.html", "link": r"https://zdevs\.ru/files/za/ZArchiver_(\d+(?:_\d+)*)_({abi})_release\.apk",
     "home": "https://zdevs.ru"},
]
KHO_ABI_ALIAS = {"x86_64": ["x86_64"], "x86": ["x86"], "arm64-v8a": ["arm64-v8a", "arm64"], "armeabi-v7a": ["armeabi-v7a", "armeabi"]}
KHO_MAX = 300 * 1024 * 1024
KHO_RECHECK = 12 * 3600
_KHO_LOCK = {a["id"]: threading.Lock() for a in KHO_APPS}

def kho_dir():
    d = os.path.join(HOME, "kho-app"); os.makedirs(d, exist_ok=True); return d

def _kho_get(url, accept=None, limit=4 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CloudBlue-Kho", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        if not r.geturl().lower().startswith("https://"): raise RuntimeError("nguồn chuyển sang http không an toàn")
        return r.read(limit + 1)[:limit]

def _kho_abis(port):
    """Loại chip máy hỗ trợ, theo thứ tự ưu tiên (x86_64 trước — chạy thẳng, không qua dịch ARM)."""
    l = out(shell(port, "getprop ro.product.cpu.abilist", 15)).strip() or out(shell(port, "getprop ro.product.cpu.abi", 15)).strip()
    abis = [x.strip() for x in l.split(",") if x.strip()] or ["x86_64", "x86", "arm64-v8a"]
    return abis + ["universal"]

def _kho_resolve(app, abis):
    """Tìm bản mới nhất ở nguồn chính chủ cho đúng loại chip → (phiên bản, link tải, sha256 hoặc '', loại chip)."""
    if app["src"] == "github":
        j = json.loads(_kho_get(f"https://api.github.com/repos/{app['repo']}/releases/latest", "application/vnd.github+json").decode())
        assets = j.get("assets") or []
        for abi in abis:
            for a in assets:
                if re.match(app["asset"].replace("{abi}", re.escape(abi)), a.get("name") or ""):
                    sha = (a.get("digest") or "").split("sha256:", 1)[-1] if str(a.get("digest") or "").startswith("sha256:") else ""
                    for sm in ([] if sha else [x for x in assets if re.search(app.get("sums") or "^$", x.get("name") or "")]):
                        for ln in _kho_get(sm["browser_download_url"]).decode(errors="ignore").splitlines():   # file tổng sha256 đi kèm bản phát hành
                            if ln.strip().endswith(a["name"]): sha = ln.split()[0].lower(); break
                        if sha: break
                    return str(j.get("tag_name") or "?"), a["browser_download_url"], sha, abi
        raise RuntimeError("bản phát hành mới nhất không có file hợp loại chip máy")
    html = _kho_get(app["page"]).decode(errors="ignore")
    if app["id"] == "mt":
        m = re.search(app["link"], html)
        if not m: raise RuntimeError("trang tải không còn link như cũ")
        return m.group(1), m.group(0), "", "universal"
    found = {}
    for m in re.finditer(app["link"].replace("{abi}", r"[\w\-]+"), html):
        ver = tuple(int(x) for x in m.group(1).split("_")); abi = m.group(2)
        if ver > found.get(abi, ((), ""))[0]: found[abi] = (ver, m.group(0))
    for abi in abis:
        for a2, alias in KHO_ABI_ALIAS.items():
            if abi in alias and a2 in found: return ".".join(map(str, found[a2][0])), found[a2][1], "", a2
    raise RuntimeError("trang tải không có bản hợp loại chip máy")

def apk_package(path):
    """Tên gói (package) trong AndroidManifest.xml của file .apk · không đọc được → ''."""
    import zipfile, struct
    try:
        with zipfile.ZipFile(path) as z: data = z.read("AndroidManifest.xml")
        strs, off = [], 8
        while off + 8 <= len(data):
            typ, hsz, sz = struct.unpack_from("<HHI", data, off)
            if sz < 8: break
            if typ == 0x0001:
                cnt, _, flags, sstart = struct.unpack_from("<IIII", data, off + 8)
                utf8 = flags & 0x100
                for i in range(cnt):
                    p_ = off + struct.unpack_from("<I", data, off + hsz + i * 4)[0] + sstart
                    if utf8:
                        n = data[p_]; p_ += 2 if n & 0x80 else 1
                        n = data[p_]; q = p_ + (2 if n & 0x80 else 1)
                        if n & 0x80: n = ((n & 0x7f) << 8) | data[p_ + 1]
                        strs.append(data[q:q + n].decode("utf-8", "replace"))
                    else:
                        n = struct.unpack_from("<H", data, p_)[0]
                        strs.append(data[p_ + 2:p_ + 2 + n * 2].decode("utf-16le", "replace"))
            elif typ == 0x0102:
                name = struct.unpack_from("<I", data, off + 20)[0]
                if 0 <= name < len(strs) and strs[name] == "manifest":
                    astart, asize, acnt = struct.unpack_from("<HHH", data, off + 24)
                    for i in range(acnt):
                        a = off + 16 + astart + i * asize
                        an, raw = struct.unpack_from("<II", data, a + 4)
                        if an < len(strs) and strs[an] == "package":
                            if raw < len(strs): return strs[raw]
                            dtype, val = data[a + 15], struct.unpack_from("<I", data, a + 16)[0]
                            return strs[val] if dtype == 0x03 and val < len(strs) else ""
                    return ""
            off += sz
    except Exception:
        return ""
    return ""

def kho_meta(app_id):
    try: return json.load(open(os.path.join(kho_dir(), app_id + ".json"), encoding="utf-8"))
    except Exception: return {}

def kho_fetch(app, abis, say=None):
    """Bản đã lưu còn mới (≤ 12 giờ, đúng loại chip) → dùng luôn; không thì hỏi nguồn chính chủ, có bản mới thì tải về + kiểm tra.
       Nguồn lỗi mà đã có bản lưu → dùng bản lưu. Trả đường dẫn file .apk."""
    d = kho_dir()
    with _KHO_LOCK[app["id"]]:
        m = kho_meta(app["id"]); fp = os.path.join(d, m.get("file") or "_")
        have = bool(m.get("file")) and os.path.isfile(fp) and (m.get("abi") in abis)
        if have and time.time() - float(m.get("checked") or 0) < KHO_RECHECK: return fp
        try:
            ver, url, sha, abi = _kho_resolve(app, abis)
        except Exception as e:
            if have: return fp
            raise RuntimeError(f"Không lấy được {app['name']} từ trang chính chủ ({e}). Thử lại sau ít phút.")
        if have and m.get("ver") == ver and m.get("abi") == abi:
            m["checked"] = time.time(); json.dump(m, open(os.path.join(d, app["id"] + ".json"), "w", encoding="utf-8")); return fp
        if say: say(f"Đang tải {app['name']} {ver} từ trang chính chủ (lần đầu ~vài chục giây)…")
        fn = f"{app['id']}-{re.sub(r'[^0-9A-Za-z.]+', '_', ver)}-{abi}.apk"; tmp = os.path.join(d, fn + ".part")
        h = hashlib.sha256(); n = 0
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CloudBlue-Kho"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            if not r.geturl().lower().startswith("https://"): raise RuntimeError("nguồn chuyển sang http không an toàn — không tải")
            while True:
                b = r.read(1 << 20)
                if not b: break
                n += len(b)
                if n > KHO_MAX: raise RuntimeError("file quá lớn, không giống app")
                h.update(b); f.write(b)
        try:
            if sha and h.hexdigest() != sha.lower(): raise RuntimeError("file tải về sai mã kiểm tra sha256 — không cài")
            pk = apk_package(tmp)
            if pk != app["pkg"]: raise RuntimeError(f"file tải về không phải {app['name']} (gói {pk or '?'}) — không cài")
            os.replace(tmp, os.path.join(d, fn))
        finally:
            if os.path.exists(tmp): os.remove(tmp)
        old = m.get("file")
        json.dump({"file": fn, "ver": ver, "abi": abi, "sha256": h.hexdigest(), "size": n, "url": url, "checked": time.time()},
                  open(os.path.join(d, app["id"] + ".json"), "w", encoding="utf-8"))
        if old and old != fn:
            try: os.remove(os.path.join(d, old))
            except OSError: pass
        log(f"kho: tải {app['name']} {ver} ({abi}, {n // 1024} KB, sha256 {h.hexdigest()[:16]}…) từ {url}")
        return os.path.join(d, fn)

def pre_dir():
    import glob
    for d in [os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk-cai-san"), os.path.join(HOME, "apk-cai-san")] + sorted(glob.glob("/home/*/apk-cai-san")):
        if os.path.isdir(d): return d
    d = os.path.join(HOME, "apk-cai-san"); os.makedirs(d, exist_ok=True); return d


def stage_pkg(path, name):
    """Chép gói vào container điều khiển 1 lần → trả về danh sách file .apk bên trong (để cài cho nhiều máy)."""
    import zipfile, tempfile
    tag = secrets.token_hex(5)
    if name.lower().endswith(".apk"):
        dst = f"/tmp/bulk_{tag}.apk"
        r = subprocess.run(["docker", "cp", path, f"{WSNAME}:{dst}"], capture_output=True, timeout=900)
        if r.returncode: raise RuntimeError("Không chép được file: " + out(r)[-200:])
        return [dst], dst
    d = tempfile.mkdtemp(prefix="bulk_", dir=UP_DIR)
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".apk") and "/" not in n.strip("/")]
            if not names: raise RuntimeError("Gói không có file .apk bên trong.")
            for n in names: z.extract(n, d)
        dst = f"/tmp/bulk_{tag}"
        r = subprocess.run(["docker", "cp", d, f"{WSNAME}:{dst}"], capture_output=True, timeout=900)
        if r.returncode: raise RuntimeError("Không chép được file: " + out(r)[-200:])
        return [f"{dst}/{n}" for n in names], dst
    except zipfile.BadZipFile:
        raise RuntimeError("File gói hỏng hoặc bị mã hoá.")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def bulk_install(jid, fid, ids, every, keep):
    path, name = ADMIN_FILES.get(fid, (None, None))
    if not path or not os.path.exists(path): raise RuntimeError("File đã hết hạn, tải lên lại.")
    q = "cloud_phones?status=eq.active&select=id,name,port,container,node" + ("" if every else "&id=in.(" + ",".join(ids) + ")")
    rows = [r for r in (sb_get("/rest/v1/" + q) or []) if r.get("port") and on_node(r)]
    if not rows:
        if keep: shutil.copy(path, os.path.join(pre_dir(), name))
        return "Server này chưa có máy nào cần cài" + (" · đã lưu cài sẵn cho máy mới" if keep else "")
    if keep:
        shutil.copy(path, os.path.join(pre_dir(), name)); JOBS[jid]["msg"] = "Đã thêm vào app cài sẵn cho máy mới…"
    files, dst = stage_pkg(path, name)
    ok, bad, lock = [], [], threading.Lock()
    def one(r):
        args = (["install", "-r", "-g", files[0]] if len(files) == 1 else ["install-multiple", "-r", "-g"] + files)
        try:
            res = adb(r["port"], args, timeout=900); o = out(res)
            good = "Success" in o
        except Exception as e:
            good, o = False, str(e)
        if good and keep:                                    # đánh dấu "đã cài sẵn" (qua adb: chạy được cả máy thường lẫn máy GPU)
            try: adb(r["port"], ["shell", "touch /data/local/tmp/.cp_pre_" + re.sub(r"[^\w.-]", "_", name)], timeout=60)
            except Exception: pass
        with lock:
            (ok if good else bad).append(r["name"] if good else f"{r['name']}: {install_err(o)[:140]}")
            JOBS[jid]["msg"] = f"Đang cài {len(ok) + len(bad)}/{len(rows)} máy… (lỗi {len(bad)})"
            JOBS[jid]["done"], JOBS[jid]["total"] = len(ok) + len(bad), len(rows)
    try:
        ths = []
        for r in rows:                                        # cài song song tối đa 4 máy
            while sum(t.is_alive() for t in ths) >= 4: time.sleep(0.3)
            t = threading.Thread(target=one, args=(r,), daemon=True); t.start(); ths.append(t)
        for t in ths: t.join()
    finally:
        subprocess.run(["docker", "exec", WSNAME, "rm", "-rf", dst], capture_output=True, timeout=60)
    JOBS[jid]["fails"] = bad[:50]
    return f"Đã cài {name} cho {len(ok)}/{len(rows)} máy" + (f" · lỗi {len(bad)} máy" if bad else "") + (" · máy mới tạo sẽ tự có" if keep else "")

def public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme not in ("http", "https") or not public_host(u.hostname or ""):
            raise urllib.error.URLError("Link chuyển hướng tới địa chỉ không hợp lệ")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def direct_link(url):
    """Đổi link trang chia sẻ thành link tải thẳng (Google Drive, Dropbox)."""
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:[^#]*&)?id=)([\w-]{20,})", url)
    if m: return "https://drive.usercontent.google.com/download?id=" + m.group(1) + "&export=download&confirm=t"
    if re.match(r"^https?://(www\.)?dropbox\.com/", url): return re.sub(r"([?&])dl=0", r"\1dl=1", url) if "dl=0" in url else url + ("&" if "?" in url else "?") + "dl=1"
    return url

def download(url, jid, _hop=0):
    url = direct_link(url)
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or not public_host(u.hostname):
        raise RuntimeError("Link không hợp lệ (chỉ nhận link http/https công khai).")
    opener = urllib.request.build_opener(SafeRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 11) CloudPhone"})
    with opener.open(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if total > MAX_FILE: raise RuntimeError("File quá lớn (tối đa 4GB).")
        cd = r.headers.get("Content-Disposition") or ""
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
        name = safe_name(urllib.parse.unquote(m.group(1)) if m else urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(r.geturl()).path)))
        if "android.package-archive" in (r.headers.get("Content-Type") or "") and not name.lower().endswith(".apk"):
            name += ".apk"
        if "text/html" in (r.headers.get("Content-Type") or ""):      # link trang web chứ không phải file
            page = r.read(3 * 1024 * 1024).decode("utf-8", "replace")
            m2 = re.search(r'href="(https?://download[^"]*\.mediafire\.com/[^"]+)"', page) or re.search(r'id="downloadButton"[^>]*href="(https?://[^"]+)"', page)
            if m2 and _hop < 2: return download(m2.group(1).replace("&amp;", "&"), jid, _hop + 1)
            if "drive.usercontent.google.com" in url or "accounts.google.com" in r.geturl():
                raise RuntimeError("Không tải được từ Google Drive — hãy chia sẻ file ở chế độ \"Bất kỳ ai có đường liên kết\".")
            raise RuntimeError("Link này là TRANG WEB, không phải link tải file. Mở link trên máy tính, bấm nút Tải xuống, rồi copy link tải thật (thường kết thúc bằng .apk) dán vào đây — hoặc tải file về rồi dùng nút \"Tải file / APK\".")
        path = os.path.join(UP_DIR, "dl_" + secrets.token_hex(6))
        got = 0
        with open(path, "wb") as f:
            while True:
                b = r.read(1024 * 1024)
                if not b: break
                got += len(b)
                if got > MAX_FILE: f.close(); os.remove(path); raise RuntimeError("File quá lớn (tối đa 4GB).")
                f.write(b)
                JOBS[jid]["msg"] = f"Đang tải về server… {got // 1048576}MB" + (f"/{total // 1048576}MB" if total else "")
    return path, name


def wait_ready(container, port):
    t0 = time.time()
    while time.time() - t0 < 300:             # hỏi qua adb → dùng được cho cả máy thường (redroid) lẫn máy GPU
        try:
            subprocess.run(["docker", "exec", WSNAME, "adb", "connect", f"127.0.0.1:{port}"], capture_output=True, timeout=20)
            r = adb(port, ["shell", "getprop", "sys.boot_completed"], 20)
            if (r.stdout or b"").strip() == b"1": break
        except Exception: pass
        time.sleep(5)
    for _ in range(6):
        subprocess.run(["docker", "exec", WSNAME, "adb", "connect", f"127.0.0.1:{port}"], capture_output=True, timeout=20)
        r = adb(port, ["get-state"], 20)
        if (r.stdout or b"").strip() == b"device": return True
        time.sleep(4)
    return False


# Đoạn chèn vào trang ws-scrcpy: hình khít khung + độ nét/FPS + báo trạng thái + nhận lệnh phím
INJECT_JS = '/* Chèn vào trang ws-scrcpy (qua cpapi): hình khít khung, độ nét/FPS theo máy, báo trạng thái, nhận lệnh phím từ trang blueroblox. */\n(function () {\n  "use strict";\n  var PARENTS = ["https://blueroblox.shop", "https://www.blueroblox.shop"];\n  var H = new URLSearchParams(location.hash.replace(/^#!?/, ""));\n  if (H.get("action") !== "stream") return;\n  var Q = H.get("cpq") || "bal";\n  var FPS = Math.max(10, Math.min(120, +H.get("cpfps") || 30));\n  var RW = +H.get("cpw") || 720, RH = +H.get("cph") || 1280;\n  //            cạnh dài tối đa, bitrate, FPS tối đa\n  // Máy ảo nén video bằng CPU → hình càng to / FPS càng cao càng trễ. Mặc định (bal) ưu tiên ÍT TRỄ như UgPhone.\n  var CO;   // tuỳ chọn bộ nén (LDPlayer: ưu tiên thời gian thực → ít trễ)\n  var PRE = { eco: [720, 1200000, 24], bal: [960, 2500000, 30], hd: [1280, 5000000, 60] }[Q] || [960, 2500000, 30];\n  // Máy MEmu (Windows, cổng 21503+): Siêu nét = 1280 · 4 Mbps · 30 FPS (MEmu nén hình bằng CPU: 60 FPS/8 Mbps làm bộ nén không theo kịp → giật); Tiết kiệm / Ít trễ gửi hình nhỏ cho mượt\n  if (/127\\.0\\.0\\.1:2\\d{4}$/.test(H.get("udid") || "")) PRE = Q === "hd" ? [1280, 4000000, 30] : [Math.min(PRE[0], 720), Math.min(PRE[1], 1800000), Math.min(PRE[2], 30)];\n  // Máy LDPlayer (cổng 5555+): 60 FPS · 2 Mbps (nhiều khung nhỏ → hình bám theo tay nhanh hơn; 3,5 Mbps làm nghẽn) + bộ nén ưu tiên thời gian thực\n  else if (/127\\.0\\.0\\.1:5[5-9]\\d\\d$/.test(H.get("udid") || "")) { PRE = Q === "hd" ? [1280, 4000000, 30] : [Math.min(PRE[0], 720), Math.min(PRE[1], 1800000), Math.min(PRE[2], 30)]; FPS = 120; }   /* LDPlayer: dùng Y HỆT mức của MEmu (720 · 1,8 Mbps · 30) — mức MEmu chạy mượt */\n  var M = Math.min(PRE[0], Math.max(RW, RH)); M -= M % 8;\n  var F = Math.min(FPS, PRE[2]);\n  var VS = JSON.stringify({ bitrate: PRE[1], maxFps: F, frameRate: F, iFrameInterval: 2, codecOptions: CO, bounds: { width: M, height: M },\n    maxSize: M, sendFrameMeta: false, lockedVideoOrientation: -1, displayId: 0, crop: null });\n  var KEY = /^\\w+:127\\.0\\.0\\.1:\\d+/;\n  try {   // cài đặt hình do trang blueroblox quyết định (ws-scrcpy mặc định chỉ 480px · 24 FPS · 0.5 Mbps)\n    var gi = Storage.prototype.getItem, si = Storage.prototype.setItem;\n    Storage.prototype.getItem = function (k) { if (typeof k === "string" && KEY.test(k)) return /:fit$/.test(k) ? "false" : VS; return gi.apply(this, arguments); };\n    Storage.prototype.setItem = function (k) { if (typeof k === "string" && KEY.test(k)) return; return si.apply(this, arguments); };\n  } catch (e) {}\n  if (H.get("cpraw") === "1") {          // chế độ gốc (vẫn giữ độ nét đã chọn — ws-scrcpy gốc chỉ 480px, rất mờ): chỉ báo "trang đã tải xong", không đụng gì vào ws-scrcpy\n    if (parent !== window) for (var j = 0; j < PARENTS.length; j++) { try { parent.postMessage({ cp: 1, n: H.get("cpn") || "", t: "boot", raw: 1 }, PARENTS[j]); } catch (e) {} }\n    return;\n  }\n\n  document.documentElement.classList.add("cp-embed");\n  var SID = H.get("cpn") || "";\n  function post(m) {\n    m.cp = 1; m.n = SID;\n    try { if (window.BRApp && BRApp.onEvent) BRApp.onEvent(JSON.stringify(m)); } catch (e) {}   // app Android BlueRoblox\n    if (parent === window) return;\n    for (var i = 0; i < PARENTS.length; i++) { try { parent.postMessage(m, PARENTS[i]); } catch (e) {} }\n  }\n\n  // Theo dõi luồng hình: có dữ liệu → báo "ok"; rớt → báo "closed" để trang ngoài tự nối lại\n  var NWS = window.WebSocket, bytes = 0, last = 0, okSent = false;\n  function W(url, proto) {\n    var ws = arguments.length > 1 ? new NWS(url, proto) : new NWS(url);\n    if (/action=proxy-adb/.test(String(url))) {\n      ws.addEventListener("open", function () { post({ t: "open" }); });\n      ws.addEventListener("message", function (e) {\n        var d = e.data; bytes += (d && (d.byteLength || d.size || d.length)) || 0;\n        if (!okSent && bytes > 30000) { okSent = true; post({ t: "ok" }); }\n      });\n      ws.addEventListener("close", function (e) { post({ t: "closed", code: e.code, ok: okSent }); });\n    }\n    return ws;\n  }\n  W.prototype = NWS.prototype; W.CONNECTING = 0; W.OPEN = 1; W.CLOSING = 2; W.CLOSED = 3;\n  window.WebSocket = W;\n  setInterval(function () { var kb = (bytes - last) * 8 / 2000; last = bytes; post({ t: "stat", kbps: Math.round(kb) }); }, 2000);\n\n  // Hình luôn khít khung, đúng tỉ lệ (không viền đen thừa → chạm chính xác)\n  var lw = 0, lh = 0;\n  function layout() {\n    var v = document.querySelector(".video"), c = document.querySelector(".touch-layer");\n    if (!v || !c || !c.width || !c.height) return;\n    if (!okSent) return;          // chưa có hình thật → canvas còn kích thước mặc định (300x150), đừng báo sai khung\n    var W0 = innerWidth, H0 = innerHeight, r = c.width / c.height, w = W0, h = w / r;\n    if (h > H0) { h = H0; w = h * r; }\n    var L = Math.round((W0 - w) / 2) + "px", T = Math.round((H0 - h) / 2) + "px", WW = Math.round(w) + "px", HH = Math.round(h) + "px";\n    if (v.style.width !== WW || v.style.height !== HH || v.style.left !== L || v.style.top !== T) {\n      var st = { position: "fixed", left: L, top: T, width: WW, height: HH, margin: "0", flex: "none" };\n      for (var k in st) v.style.setProperty(k, st[k], "important");\n    }\n    if (c.width !== lw || c.height !== lh) { lw = c.width; lh = c.height; post({ t: "size", w: lw, h: lh }); }\n  }\n  setInterval(layout, 300); addEventListener("resize", layout);\n\n  // Bộ nhớ copy (clipboard) giữa máy ảo và máy khách — dùng ô "clipboard" có sẵn của ws-scrcpy (đã ẩn)\n  function clipEls() {\n    var m = document.querySelector(".more-box"); if (!m) return null;\n    var ta = m.querySelector("textarea"), bs = m.querySelectorAll("button"), set = null, get = null;\n    for (var i = 0; i < bs.length; i++) {\n      var t = (bs[i].textContent || "").trim().toLowerCase();\n      if (t === "set clipboard") set = bs[i]; else if (t === "get clipboard") get = bs[i];\n    }\n    return ta && set ? { ta: ta, set: set, get: get } : null;\n  }\n  var lastClip = null, clipCap = false;\n  setInterval(function () {\n    var e = clipEls(); if (!e) return;\n    if (!clipCap) { clipCap = true; lastClip = e.ta.value; post({ t: "clipcap" }); return; }\n    var v = e.ta.value;\n    if (v !== lastClip) { lastClip = v; if (v) post({ t: "clip", text: v }); }   // máy ảo vừa copy chữ → gửi ra ngoài\n  }, 400);\n  function clipSet(text) {\n    var e = clipEls(); if (!e) return false;\n    lastClip = String(text); e.ta.value = lastClip; e.set.click(); return true;\n  }\n  function clipGet() {\n    var e = clipEls(); if (!e || !e.get) return false;\n    lastClip = ""; e.ta.value = ""; e.get.click(); return true;\n  }\n  window.__cp = { clipSet: clipSet, clipGet: clipGet, clipCap: function () { return !!clipEls(); } };\n  // Ctrl+V khi đang bấm vào màn hình máy: dán chữ của máy khách (có dấu) thay vì bộ nhớ copy cũ của máy ảo\n  addEventListener("keydown", function (e) {\n    if ((e.ctrlKey || e.metaKey) && (e.key === "v" || e.key === "V") && clipEls()) e.stopImmediatePropagation();\n  }, true);\n  document.addEventListener("paste", function (e) {\n    var t = e.clipboardData && e.clipboardData.getData("text/plain");\n    if (!t || !clipSet(t)) return;\n    e.preventDefault();\n    setTimeout(function () { post({ t: "pasteKey" }); }, 200);\n  }, true);\n\n  // Lệnh từ trang blueroblox: bấm phím qua đường hình (tức thì)\n  var TITLES = { back: "Back", home: "Home", recents: "Overview", volup: "Volume up", voldown: "Volume down", power: "Power" };\n  addEventListener("message", function (e) {\n    if (PARENTS.indexOf(e.origin) < 0 || !e.data || !e.data.cpcmd) return;\n    var d = e.data;\n    if (d.cpcmd === "key") {\n      var b = document.querySelector(\'button[title="\' + TITLES[d.key] + \'"]\');\n      if (!b) return post({ t: "nokey", key: d.key, id: d.id });\n      b.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));\n      setTimeout(function () { b.dispatchEvent(new MouseEvent("mouseup", { bubbles: true })); }, 50);\n      post({ t: "keyok", id: d.id });\n    } else if (d.cpcmd === "clipset") {\n      post({ t: "clipset", id: d.id, ok: clipSet(d.text || "") });\n    } else if (d.cpcmd === "clipget") {\n      post({ t: "clipget", id: d.id, ok: clipGet() });\n    }\n  });\n  // Bàn phím máy tính: tự bật "Capture keyboard" của ws-scrcpy (khách gõ phím thật, khỏi bấm bàn phím ảo)\n  //   + bấm vào màn hình máy là khung hình nhận phím ngay\n  var kbTry = 0, kbT = setInterval(function () {\n    var cb = document.querySelector(\'input[id^="input_capture_keyboard_"]\');\n    if (cb) { if (!cb.checked) cb.click(); if (cb.checked) { clearInterval(kbT); post({ t: "kb" }); } }\n    if (++kbTry > 120) clearInterval(kbT);\n  }, 500);\n  function grab() { try { window.focus(); if (document.activeElement && document.activeElement !== document.body && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) document.activeElement.blur(); } catch (e) {} }\n  addEventListener("mousedown", grab, true); addEventListener("touchstart", grab, true);\n  // ===== Thao tác nâng cao (giống LDPlayer / Multi): ĐỒNG BỘ nhiều máy · GHI MACRO · GÁN PHÍM CHƠI GAME =====\n  var REC = false, SYNC = false, KMEDIT = false, KM = null, lastMv = 0;\n  function layer() { return document.querySelector(".touch-layer"); }\n  function relp(cx, cy) { var c = layer(); if (!c) return null; var r = c.getBoundingClientRect(); if (!r.width || !r.height) return null; return { x: (cx - r.left) / r.width, y: (cy - r.top) / r.height }; }\n  function capture(e) {                     // thao tác THẬT của người dùng → báo trang ngoài (để đồng bộ / ghi macro / chọn vị trí phím)\n    if (!e.isTrusted || !(REC || SYNC || KMEDIT)) return;\n    var c = layer(); if (!c || e.target !== c) return;\n    var p, k;\n    if (e.type.indexOf("touch") === 0) { var t = e.changedTouches[0]; if (!t) return; p = relp(t.clientX, t.clientY); k = { touchstart: "down", touchmove: "move", touchend: "up", touchcancel: "up" }[e.type]; }\n    else { if (e.type === "mousemove" && !(e.buttons & 1)) return; p = relp(e.clientX, e.clientY); k = { mousedown: "down", mousemove: "move", mouseup: "up" }[e.type]; }\n    if (!p || !k) return;\n    if (KMEDIT) { if (k === "down") post({ t: "kmpick", x: p.x, y: p.y }); e.preventDefault(); e.stopImmediatePropagation(); return; }\n    if (k === "move") { var now = Date.now(); if (now - lastMv < 30) return; lastMv = now; }\n    post({ t: "in", k: k, x: p.x, y: p.y, id: 0 });\n  }\n  ["mousedown", "mousemove", "mouseup", "touchstart", "touchmove", "touchend", "touchcancel"].forEach(function (n) { addEventListener(n, capture, true); });\n  var TT = {};\n  function fire(k, x, y, id) {              // tạo thao tác chạm giả (nhiều ngón) đúng vị trí tương đối trên màn hình máy\n    var c = layer(); if (!c) return; var r = c.getBoundingClientRect(); var cx = r.left + x * r.width, cy = r.top + y * r.height; id = id || 0;\n    if (window.TouchEvent && window.Touch) {\n      try {\n        var t = new Touch({ identifier: id + 1, target: c, clientX: cx, clientY: cy, pageX: cx, pageY: cy, screenX: cx, screenY: cy, radiusX: 2, radiusY: 2, force: 1 });\n        if (k === "up") delete TT[id]; else TT[id] = t;\n        var all = Object.keys(TT).map(function (i) { return TT[i]; });\n        c.dispatchEvent(new TouchEvent({ down: "touchstart", move: "touchmove", up: "touchend" }[k], { touches: all, targetTouches: all, changedTouches: [t], bubbles: true, cancelable: true }));\n        return;\n      } catch (er) {}\n    }\n    c.dispatchEvent(new MouseEvent({ down: "mousedown", move: "mousemove", up: "mouseup" }[k], { clientX: cx, clientY: cy, bubbles: true, cancelable: true, button: 0, buttons: k === "up" ? 0 : 1 }));\n  }\n  // Gán phím: KM = { "KeyJ": {x,y}, ..., __joy: {x,y,r, keys:{KeyW:[0,-1],...}} }\n  var held = {}, slot = {}, joyOn = false;\n  function joyUpdate() {\n    var j = KM && KM.__joy; if (!j) return; var dx = 0, dy = 0;\n    for (var kk in j.keys) if (held[kk]) { dx += j.keys[kk][0]; dy += j.keys[kk][1]; }\n    if (!dx && !dy) { if (joyOn) { fire("up", j.x, j.y, 9); joyOn = false; } return; }\n    var c = layer(), ar = 1; if (c) { var r = c.getBoundingClientRect(); ar = r.width / (r.height || 1); }\n    var l = Math.sqrt(dx * dx + dy * dy), tx = j.x + dx / l * j.r, ty = j.y + dy / l * j.r * ar;\n    if (!joyOn) { fire("down", j.x, j.y, 9); joyOn = true; }\n    fire("move", tx, ty, 9);\n  }\n  addEventListener("keydown", function (e) {\n    if (!KM) return; var j = KM.__joy, m = KM[e.code];\n    if (!(m || (j && j.keys[e.code]))) return;\n    e.preventDefault(); e.stopImmediatePropagation(); if (e.repeat) return;\n    if (j && j.keys[e.code]) { held[e.code] = true; joyUpdate(); return; }\n    var id = 1; while (Object.keys(slot).some(function (s) { return slot[s] === id; })) id++;\n    slot[e.code] = id; fire("down", m.x, m.y, id);\n  }, true);\n  addEventListener("keyup", function (e) {\n    if (!KM) return; var j = KM.__joy, m = KM[e.code];\n    if (!(m || (j && j.keys[e.code]))) return;\n    e.preventDefault(); e.stopImmediatePropagation();\n    if (j && j.keys[e.code]) { held[e.code] = false; joyUpdate(); return; }\n    if (slot[e.code]) { fire("up", m.x, m.y, slot[e.code]); delete slot[e.code]; }\n  }, true);\n  addEventListener("blur", function () { held = {}; joyUpdate(); for (var s in slot) { var m = KM && KM[s]; if (m) fire("up", m.x, m.y, slot[s]); } slot = {}; });\n  addEventListener("message", function (e) {\n    if (PARENTS.indexOf(e.origin) < 0 || !e.data || !e.data.cpcmd) return;\n    var d = e.data;\n    if (d.cpcmd === "in") fire(d.k, +d.x, +d.y, +d.id || 0);\n    else if (d.cpcmd === "sync") SYNC = !!d.on;\n    else if (d.cpcmd === "rec") REC = !!d.on;\n    else if (d.cpcmd === "kmedit") KMEDIT = !!d.on;\n    else if (d.cpcmd === "km") { KM = d.map && Object.keys(d.map).length ? d.map : null; held = {}; slot = {}; }\n  });\n  post({ t: "boot" });\n})();\n'.encode()
# Trang ngoài được nhận/gửi tin với khung hình = đúng các tên miền web ở ORIGINS (gồm CPAPI_ORIGINS trong cloudphone.conf)
INJECT_JS = INJECT_JS.replace(b'var PARENTS = ["https://blueroblox.shop", "https://www.blueroblox.shop"];',
                              ("var PARENTS = " + json.dumps(sorted(ORIGINS)) + ";").encode())
INJECT_CSS = 'html.cp-embed,html.cp-embed body{margin:0!important;padding:0!important;width:100%!important;height:100%!important;overflow:hidden!important;background:#000!important}html.cp-embed .control-buttons-list,html.cp-embed .more-box{display:none!important}html.cp-embed .device-view{position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;background:#000!important}html.cp-embed .video{position:relative;flex:1 1 auto;min-width:0;min-height:0;width:100%;height:100%;background:#000}html.cp-embed .video-layer,html.cp-embed .touch-layer{position:absolute!important;left:0!important;top:0!important;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;object-fit:contain!important}'
INJECT_TAG = ("<style>" + INJECT_CSS + "</style><script src=\"/__cp/inject.js?v=11\"></script>").encode()

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 120
    server_version = "cpapi"

    def log_message(self, fmt, *args):
        pass

    # ---------- tiện ích ----------
    def cors(self):
        o = self.headers.get("Origin", "")
        if o in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def send_json(self, code, obj, extra=None):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or []): self.send_header(k, v)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def deny(self, code, msg):
        b = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b)
        self.close_connection = True

    def body(self, limit):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit: raise ValueError("Dữ liệu quá lớn")
        return self.rfile.read(n) if n else b""

    def jbody(self):
        try:
            return json.loads(self.body(65536) or b"{}")
        except Exception:
            return {}

    def cookie_auth(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE: return verify(v)
        return None

    # ---------- định tuyến ----------
    def do_OPTIONS(self):
        if self.path.startswith("/cpapi/"):
            self.send_response(204)
            self.cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.proxy()

    def do_GET(self):
        if self.path.startswith("/__cp/inject.js"):
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(INJECT_JS)))
            self.end_headers()
            return self.wfile.write(INJECT_JS)
        self.api() if self.path.startswith("/cpapi/") else self.proxy()

    def do_HEAD(self):
        self.proxy()

    def do_POST(self):
        self.api() if self.path.startswith("/cpapi/") else self.proxy()

    # ---------- API ----------
    def api(self):
        try:
            self._api()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "Máy phản hồi quá lâu, thử lại."})
        except Exception as e:
            log("API lỗi:", repr(e))
            self.send_json(500, {"error": "Lỗi máy chủ: " + str(e)[:200]})

    def _api(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        parts = [p for p in u.path.split("/") if p][1:]
        if self.headers.get("Origin") and self.headers.get("Origin") not in ORIGINS:
            return self.send_json(403, {"error": "Nguồn không được phép."})
        tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        me = whoami(tok)
        if not me: return self.send_json(401, {"error": "Phiên đăng nhập hết hạn — tải lại trang và đăng nhập lại."})

        if parts == ["session"] and self.command == "POST":
            val = sign({"u": me["uid"], "a": me["admin"], "exp": int(time.time()) + COOKIE_TTL})
            ck = f"{COOKIE}={val}; Path=/; Max-Age={COOKIE_TTL}; Secure; HttpOnly; SameSite=None"
            return self.send_json(200, {"ok": True, "admin": me["admin"]}, [("Set-Cookie", ck)])

        if parts and parts[0] == "job":
            j = JOBS.get(q.get("id", ""))
            if not j or (j["owner"] != me["uid"] and not me["admin"]): return self.send_json(404, {"error": "Không có việc này."})
            return self.send_json(200, {k: j[k] for k in ("state", "msg", "title", "file", "done", "total", "fails") if k in j})

        if parts and parts[0] == "admin":
            if not me["admin"]: return self.send_json(403, {"error": "Chỉ admin."})
            act = parts[1] if len(parts) > 1 else ""
            if act == "upload" and self.command == "POST":
                upid = q.get("id", ""); name = safe_name(q.get("name", ""))
                if not re.match(r"^[a-z0-9]{8,40}$", upid): return self.send_json(400, {"error": "Mã tải lên không hợp lệ."})
                if not name.lower().endswith(APK_EXT): return self.send_json(400, {"error": "Chỉ nhận file .apk / .apks / .apkm / .xapk"})
                total, off = int(q.get("total") or 0), int(q.get("off") or 0)
                if total <= 0 or total > MAX_FILE: return self.send_json(400, {"error": "File rỗng hoặc lớn hơn 4GB."})
                path = os.path.join(UP_DIR, f"admin_{upid}.part")
                have = os.path.getsize(path) if os.path.exists(path) else 0
                if off != have: return self.send_json(409, {"error": "Lệch vị trí", "size": have})
                data = self.body(MAX_CHUNK)
                if have + len(data) > total: return self.send_json(400, {"error": "Dữ liệu vượt kích thước file."})
                with open(path, "ab") as f: f.write(data)
                have += len(data)
                if have < total: return self.send_json(200, {"size": have})
                ADMIN_FILES[upid] = (path, name)
                return self.send_json(200, {"size": have, "file": upid})
            if act == "fromurl" and self.command == "POST":
                link = str(self.jbody().get("url") or "").strip()
                if not re.match(r"^https?://\S+$", link) or len(link) > 2000: return self.send_json(400, {"error": "Link phải bắt đầu bằng http:// hoặc https://"})
                jid = new_job(me["uid"], link[-60:])
                def work(j):
                    path, name = download(link, j)
                    if not name.lower().endswith(APK_EXT): os.remove(path); raise RuntimeError("Link không phải file APK.")
                    fid = secrets.token_hex(8); ADMIN_FILES[fid] = (path, name); JOBS[j]["file"] = fid; JOBS[j]["title"] = name
                    return "Đã tải " + name
                run_job(jid, work)
                return self.send_json(200, {"job": jid})
            if act == "install" and self.command == "POST":
                b = self.jbody(); fid = str(b.get("file") or "")
                ids = [i for i in (b.get("ids") or []) if UUID.match(str(i))][:500]
                every = bool(b.get("all"))
                if fid not in ADMIN_FILES: return self.send_json(400, {"error": "File đã hết hạn, tải lên lại."})
                if not every and not ids: return self.send_json(400, {"error": "Chưa chọn máy nào."})
                jid = new_job(me["uid"], ADMIN_FILES[fid][1])
                run_job(jid, lambda j: bulk_install(j, fid, ids, every, bool(b.get("keep"))))
                return self.send_json(200, {"job": jid})
            if act == "rootall" and self.command == "POST":       # admin: root lại toàn bộ máy chưa root
                jid = new_job(me["uid"], "Root tất cả máy")
                def work(j):
                    JOBS[j]["msg"] = "Đang root các máy chưa root (mỗi máy khởi động lại ~1 phút)…"
                    r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "rootfix", "--all", "--force"], capture_output=True, text=True, timeout=7200)
                    ls = [l for l in (r.stdout or "").splitlines() if l.startswith("ROOT_")]
                    ok = sum(l.startswith("ROOT_OK") for l in ls); bad = [l.split(" ", 1)[1] for l in ls if l.startswith(("ROOT_NO", "ROOT_WAIT"))]
                    return f"Đã root {ok} máy." + (" Chưa được: " + "; ".join(bad[:8]) if bad else "")
                run_job(jid, work)
                return self.send_json(200, {"job": jid})
            if act == "donsach" and self.command == "POST":        # admin 🧹: xoá máy khách web đã HUỶ nhưng còn sót trên máy chủ này (máy cũ đổi Android…)
                if _DONSACH.get("t") and time.time() - _DONSACH["t"] < 120: return self.send_json(409, {"error": "Máy chủ này đang dọn — chờ 1–2 phút."})
                _DONSACH["t"] = time.time()
                jid = new_job(me["uid"], "Dọn máy cũ trên " + NODE_ID)
                log("admin dọn máy đã huỷ còn sót:", me["uid"])
                def work(j):
                    try:
                        JOBS[j]["msg"] = "Đang xoá máy cũ còn sót (mỗi máy khoảng 30 giây)…"
                        r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "dondep", "--xoa"], capture_output=True, timeout=3600)
                        o = out(r); m = re.search(r"DONDEP (\{.*\})", o)
                        if not m:
                            raise RuntimeError("Máy chủ chưa có phonectl.py bản mới — chạy lệnh cập nhật máy chủ rồi bấm lại." if r.returncode in (0, 2)
                                               else "Chưa dọn được: " + o[-300:])
                        d = json.loads(m.group(1))
                        t = f"xoá {d.get('deleted', 0)}/{d.get('dead', 0)} máy cũ"
                        if d.get("fail"): t += f" ({d['fail']} máy chưa xoá được — bấm lại sau ít phút)"
                        if d.get("unknown"): t += f" · {d['unknown']} máy không có trên web: giữ nguyên"
                        return t
                    finally:
                        _DONSACH["t"] = 0
                run_job(jid, work)
                return self.send_json(200, {"job": jid})
            if act == "server" and self.command == "GET":           # admin: tình trạng máy chủ trước khi khởi động lại cả máy chủ
                if not IS_WIN: return self.send_json(400, {"error": "Chỉ khởi động lại được máy chủ Windows."})
                r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "serverinfo"], capture_output=True, timeout=120)
                m = re.search(r"SERVERINFO (\{.*\})", out(r))
                if not m:
                    return self.send_json(409, {"error": "Máy chủ chưa có phonectl.py mới — tải bản mới về máy chủ rồi thử lại."} if r.returncode == 2
                                          else {"error": "Không đọc được tình trạng máy chủ: " + out(r)[-200:]})
                j = json.loads(m.group(1)); j["node"] = NODE_ID; j["rebooting"] = bool(_REBOOT.get("t") and time.time() - _REBOOT["t"] < 600)
                return self.send_json(200, j)
            if act == "reboot-server" and self.command == "POST":   # admin: ÉP KHỞI ĐỘNG LẠI CẢ MÁY CHỦ — tắt êm máy khách → Windows khởi động lại
                if not IS_WIN: return self.send_json(400, {"error": "Chỉ khởi động lại được máy chủ Windows."})
                b = self.jbody()
                if str(b.get("confirm") or "").strip().lower() != str(NODE_ID).strip().lower():
                    return self.send_json(400, {"error": f"Gõ đúng mã máy chủ ({NODE_ID}) để xác nhận."})
                if _REBOOT.get("t") and time.time() - _REBOOT["t"] < 600: return self.send_json(409, {"error": "Máy chủ này đang khởi động lại rồi."})
                _REBOOT["t"] = time.time()
                jid = new_job(me["uid"], "Khởi động lại máy chủ " + NODE_ID)
                log("admin khởi động lại máy chủ:", me["uid"])
                def work(j):
                    try:
                        JOBS[j]["msg"] = "Đang tắt êm các máy khách (tối đa ~2 phút)…"
                        r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "rebootserver"] + (["--anyway"] if b.get("anyway") else []),
                                           capture_output=True, timeout=420)
                        o = out(r)
                        if r.returncode == 7: raise RuntimeError("NO_AUTOLOGON: Windows của máy chủ chưa bật tự đăng nhập (bảng CloudBlue → 🔑 Tự đăng nhập + tự chạy). Khởi động lại sẽ dừng ở màn hình mật khẩu.")
                        if r.returncode: raise RuntimeError("Chưa khởi động lại được: " + o[-300:])
                        m = re.search(r"REBOOT_OK (.*)", o)
                        return m.group(1).strip() if m else "Máy chủ đang khởi động lại."
                    except Exception:
                        _REBOOT["t"] = 0; raise
                run_job(jid, work)
                return self.send_json(200, {"job": jid})
            if act == "gputest" and self.command == "GET":          # máy thử GPU: trạng thái
                return self.send_json(200, gpu_status())
            if act == "gputest" and self.command == "POST":
                b = self.jbody(); do = str(b.get("do") or "")
                if not os.path.isfile(GPU_SCRIPT): return self.send_json(400, {"error": "Chưa có ~/gpu-phone-test.sh trên server."})
                if do not in ("start", "stop", "chrome", "android"): return self.send_json(400, {"error": "Lệnh không hợp lệ."})
                ver = str(b.get("v") or "")
                if do == "android" and ver not in GPU_IMGS: return self.send_json(400, {"error": "Chỉ có Android 9, 10, 11, 12."})
                jid = new_job(me["uid"], "Máy thử GPU: " + do)
                def work(j):
                    if do == "stop": gpu_run(["stop"], timeout=120); return "Đã tắt máy thử."
                    if do == "chrome":
                        gpu_adb("am start -W -a android.intent.action.VIEW -d https://www.google.com com.android.chrome", 40)
                        time.sleep(15)
                        alive = gpu_adb("pidof com.android.chrome").strip()
                        return "✅ Chrome đang chạy." if alive else "❌ Chrome không chạy — xem màn hình máy thử."
                    if do == "android":
                        JOBS[j]["msg"] = f"Đang tắt máy cũ và tải Android {ver} (5–15 phút)…"
                        gpu_run(["stop"], timeout=120)
                        rc, t = gpu_run(["image"], {"GPU_IMG": GPU_IMGS[ver]}, timeout=3600)
                        if rc != 0 and ver in ("9", "10"):
                            rc, t = gpu_run(["image"], {"GPU_IMG": GPU_IMGS[ver].replace(";x86", ";x86_64")}, timeout=3600)
                        if rc != 0: raise RuntimeError("Cài Android " + ver + " lỗi: " + ((t.strip().splitlines() or ["?"])[-1][:200]))
                    JOBS[j]["msg"] = "Đang bật máy thử (1–3 phút)…"
                    rc, t = gpu_run(["start"], timeout=600)
                    if rc != 0: raise RuntimeError((t.strip().splitlines() or ["Bật máy lỗi"])[-1][:240])
                    st = gpu_status()
                    return f"Máy thử Android {st.get('android', '?')} đã bật · " + ("đang dùng GTX 1080 ✅" if st.get("on_gpu") else "CHƯA dùng GPU ⚠")
                run_job(jid, work)
                return self.send_json(200, {"job": jid})
            if act == "preset" and self.command == "GET":
                d = pre_dir(); fs = sorted(f for f in os.listdir(d) if f.lower().endswith(APK_EXT))
                return self.send_json(200, {"files": [{"name": f, "size": os.path.getsize(os.path.join(d, f))} for f in fs]})
            if act == "preset-del" and self.command == "POST":
                n = safe_name(self.jbody().get("name") or ""); fp = os.path.join(pre_dir(), n)
                if n.lower().endswith(APK_EXT) and os.path.isfile(fp): os.remove(fp); return self.send_json(200, {"ok": True})
                return self.send_json(404, {"error": "Không có file này."})
            return self.send_json(404, {"error": "Không có chức năng này."})

        if len(parts) != 2: return self.send_json(404, {"error": "Không có chức năng này."})
        under = bool(maint().get("maint")) and not me["admin"]
        if under and parts[1] != "info": return self.send_json(503, {"error": maint_text(), "maint": True})
        pid, act = parts
        p = phone_of(me, pid)
        if not p: return self.send_json(404, {"error": "Không tìm thấy máy của bạn."})
        port, cont = p.get("port"), p.get("container")
        locked = is_locked(p) and not me["admin"]
        if locked and act != "info": return self.send_json(423, {"error": lock_text(p), "locked": True})
        if act == "info":
            st = out(adb(port, ["get-state"], 15)) if port and p["status"] == "active" else ""
            booting = False
            if st == "device":                    # Android đang khởi động lại (VD vừa hết RAM) → báo khách
                try: booting = out(shell(port, "getprop sys.boot_completed", 8)).strip() != "1"
                except Exception: booting = False
            return self.send_json(200, {"name": p["name"], "ram": p["ram"], "cpu": p["cpu"], "res": p.get("res"),
                                        "status": p["status"], "expires_at": p.get("expires_at"), "online": st == "device", "booting": booting,
                                        "viewer": (VIEWERS.get(int(port)) or {}).get("viewer") if port else None,
                                        "fps": p.get("fps") or 30, "fps_range": fps_limits(), "busy": pid in _busy,
                                        "maint": under, "maint_msg": maint_text() if under else None,
                                        "locked": locked, "lock_msg": lock_text(p) if locked else None})
        if p["status"] != "active" or not port:
            return self.send_json(409, {"error": "Máy chưa chạy (đang tạo, tạm dừng hoặc đã huỷ)."})

        if act == "key" and self.command == "POST":
            code = int(self.jbody().get("code") or 0)
            if code not in KEYS: return self.send_json(400, {"error": "Phím không hợp lệ."})
            shell(port, f"input keyevent {code}", 15)
            return self.send_json(200, {"ok": True})

        if act == "ime" and self.command == "GET":           # máy đang mở bàn phím (khách bấm vào ô nhập)? → app điện thoại tự bật bàn phím
            o = out(shell(port, "dumpsys input_method | grep -m2 -E 'mInputShown|mShowRequested'", 10))
            return self.send_json(200, {"shown": "mInputShown=true" in o or "mShowRequested=true" in o})

        if act == "text" and self.command == "POST":
            t = str(self.jbody().get("text") or "")[:2000]
            if not t: return self.send_json(400, {"error": "Chưa nhập chữ."})
            if any(ord(ch) > 126 or (ord(ch) < 32 and ch != "\n") for ch in t):
                return self.send_json(400, {"error": "Chỉ dán được chữ KHÔNG DẤU. Chữ có dấu hãy gõ trực tiếp trên màn hình máy."})
            for i, line in enumerate(t.split("\n")):
                if i: shell(port, "input keyevent 66", 10)
                if line: shell(port, "input text " + shlex.quote(line.replace("%", "").replace(" ", "%s")), 30)
            return self.send_json(200, {"ok": True})

        if act == "url" and self.command == "POST":
            link = str(self.jbody().get("url") or "").strip()
            if not re.match(r"^https?://\S+$", link) or len(link) > 2000: return self.send_json(400, {"error": "Link phải bắt đầu bằng http:// hoặc https://"})
            r = shell(port, MAIN_SH + "am start $D -a android.intent.action.VIEW -d " + shlex.quote(link), 20)
            return self.send_json(200, {"ok": True, "out": out(r)[-200:]})

        if act == "rotate" and self.command == "POST":       # XOAY MÀN: khoá ngang / dọc (tắt tự xoay của Android + đặt hướng). Game cần màn ngang vẫn tự xoay.
            b = self.jbody(); to = str(b.get("to") or "")
            d = 1 if to == "land" or (to != "port" and b.get("dir")) else 0
            r = shell(port, f"settings put system accelerometer_rotation 0 && settings put system user_rotation {d} && echo ROT_OK; "
                            f"wm user-rotation lock {d} >/dev/null 2>&1; true", 15)      # wm user-rotation: Android 10+ (máy cũ báo lỗi → bỏ qua)
            if "ROT_OK" not in out(r): return self.send_json(500, {"error": "Chưa xoay được — máy chưa sẵn sàng, thử lại sau giây lát."})
            return self.send_json(200, {"ok": True, "to": "land" if d else "port",
                                        "msg": "Đã khoá màn NGANG." if d else "Đã khoá màn DỌC."})

        if act == "density":                                  # ĐỘ RỘNG NHỎ NHẤT (Smallest width): số dp càng lớn → chữ / biểu tượng càng nhỏ, màn chứa được nhiều hơn
            def screen_now():
                o = out(shell(port, "wm size; wm density", 15))
                size = {k: (int(a), int(b)) for k, a, b in re.findall(r"(Physical|Override) size:\s*(\d+)x(\d+)", o)}
                den = {k: int(v) for k, v in re.findall(r"(Physical|Override) density:\s*(\d+)", o)}
                w, h = size.get("Override") or size.get("Physical") or (0, 0)
                pd = den.get("Physical") or 0; d = den.get("Override") or pd; short = min(w, h)
                # đổi độ phân giải không khởi động lại (phonectl liveres) đặt wm size + wm density theo cỡ mới → mặc định = mật độ đó,
                # KHÔNG phải mật độ lúc tạo máy (wm density reset lúc đó làm chữ / biểu tượng bé tí)
                dd = max(160, min(640, round(short / 2.25))) if ("Override" in size and short) else pd
                return {"w": w, "h": h, "density": d, "physical": pd, "default": dd, "size_override": "Override" in size, "override": d != dd,
                        "sw": round(short * 160 / d) if d and short else 0, "sw_default": round(short * 160 / dd) if dd and short else 0}
            c = screen_now()
            if not c["density"] or not min(c["w"], c["h"]): return self.send_json(500, {"error": "Chưa đọc được màn hình máy — thử lại sau giây lát."})
            if self.command == "GET": return self.send_json(200, c)
            b = self.jbody()
            if b.get("reset"):
                shell(port, f"wm density {c['default']}" if c["size_override"] else "wm density reset", 15)
            else:
                try: sw = int(b.get("sw"))
                except (TypeError, ValueError): return self.send_json(400, {"error": "Độ rộng nhỏ nhất không hợp lệ."})
                if not 240 <= sw <= 1600: return self.send_json(400, {"error": "Độ rộng nhỏ nhất phải từ 240 đến 1600 dp."})
                shell(port, f"wm density {max(72, min(640, round(min(c['w'], c['h']) * 160 / sw)))}", 15)
            n = screen_now()
            msg = (f"Đã trả về mặc định: {n['sw']} dp." if b.get("reset")
                   else f"Đã đặt độ rộng nhỏ nhất {n['sw']} dp. App đang mở sẽ tự vẽ lại giao diện (game có thể tải lại).")
            return self.send_json(200, dict(n, ok=True, msg=msg))

        if act == "shot":          # ảnh màn hình; ?w=270 → ẢNH NHỎ (JPEG) cho "màn hình trực tiếp" / "xem tất cả máy"
            try: w = max(0, min(720, int(q.get("w") or 0)))
            except ValueError: w = 0
            key = (int(port), w); c = SHOTS.get(key)
            if q.get("fresh") == "1": c = None                     # nút "Chụp màn" của app: luôn chụp MỚI (không trả ảnh cũ trong bộ nhớ đệm)
            ttl = 1.0 if w > 300 else 5.0                          # ảnh nhỏ: 5 giây/ảnh là đủ cho danh sách
            if LIVE.get(int(port)): ttl = 30.0                     # máy đang được điều khiển → hầu như không chụp (giữ luồng hình mượt)
            busy = c is not None and not SHOT_SEM.acquire(blocking=False)   # đang có 2 ảnh khác chụp → trả ảnh cũ ngay
            if busy or (c and time.time() - c[0] < ttl):
                if not busy: SHOT_SEM.release()
                data, ctype = c[1], c[2]
            else:
              got = True if c is not None else SHOT_SEM.acquire(timeout=25)
              try:
                  data, ctype = None, "image/png"
                  if w:
                      try:                                            # NHANH: ảnh thô (không nén PNG trong máy ảo) → thu nhỏ + JPEG trên Windows
                          import io
                          from PIL import Image
                          r = adb(port, ["exec-out", "screencap"], 20)
                          raw = r.stdout or b""
                          if not r.returncode and len(raw) > 16:
                              W, H = int.from_bytes(raw[0:4], "little"), int.from_bytes(raw[4:8], "little")
                              n = W * H * 4
                              if 0 < W <= 4096 and 0 < H <= 4096 and len(raw) >= n + 12:
                                  im = Image.frombuffer("RGBA", (W, H), raw[len(raw) - n:], "raw", "RGBA", 0, 1).convert("RGB")
                                  im = im.resize((w, max(1, round(H * w / W))), Image.BILINEAR)
                                  b = io.BytesIO(); im.save(b, "JPEG", quality=65); data, ctype = b.getvalue(), "image/jpeg"
                      except Exception: data = None
                  if data is None:
                      r = adb(port, ["exec-out", "screencap", "-p"], 30)
                      if r.returncode or not r.stdout.startswith(b"\x89PNG"): return self.send_json(500, {"error": "Không chụp được màn hình."})
                      data, ctype = r.stdout, "image/png"
                      if w:
                          try:
                              import io
                              from PIL import Image
                              im = Image.open(io.BytesIO(data)).convert("RGB")
                              im = im.resize((w, max(1, round(im.height * w / im.width))))
                              b = io.BytesIO(); im.save(b, "JPEG", quality=62); data, ctype = b.getvalue(), "image/jpeg"
                          except Exception: pass
                  SHOTS[key] = (time.time(), data, ctype)
                  if len(SHOTS) > 200: SHOTS.clear()
              finally:
                if got: SHOT_SEM.release()
            self.send_response(200)
            self.cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)

        if act == "gsf":          # mã thiết bị Google (GSF ID) → khách đăng ký ở google.com/android/uncertified để đăng nhập Google được
            r = shell(port, "content query --uri content://com.google.android.gsf.gservices --where \"name='android_id'\"", 20)
            m = re.search(r"value=(\d{6,25})", out(r))
            if not m: return self.send_json(409, {"error": "Chưa lấy được mã — mở Cửa hàng Play 1 lần, đợi 1 phút rồi thử lại."})
            return self.send_json(200, {"gsf": m.group(1)})

        if act == "gfix" and self.command == "POST":      # sau khi đăng ký mã: xoá dữ liệu Google Play để nhận chứng nhận mới
            r = shell(port, "pm clear com.android.vending; pm clear com.google.android.gms", 60)
            return self.send_json(200, {"ok": True, "out": out(r)[-200:]})

        if act == "store" and self.command == "GET":          # KHO ỨNG DỤNG: app có sẵn trên server (admin bỏ vào ~/apk-cai-san) + trạng thái đã cài
            d = pre_dir()
            try: fs = sorted(f for f in os.listdir(d) if f.lower().endswith(APK_EXT))
            except OSError: fs = []
            inst = set(l.split(":", 1)[1].strip() for l in out(shell(port, "pm list packages", 30)).splitlines() if l.startswith("package:"))
            try: sdk = int(out(shell(port, "getprop ro.build.version.sdk", 15)).strip() or 0)
            except ValueError: sdk = 0
            fs = [f for f in fs if for_sdk(f, os.path.join(d, f), sdk)]   # ẩn app không chạy được trên bản Android của máy này
            en = (self.headers.get("Accept-Language") or "").lower().startswith("en")
            apps = []
            for a in KHO_APPS:
                m = kho_meta(a["id"])
                apps.append({"id": a["id"], "name": a["name"], "icon": a["icon"], "pkg": a["pkg"], "desc": a["desc_en"] if en else a["desc"],
                             "installed": a["pkg"] in inst, "ver": m.get("ver") or "", "size": m.get("size") or 0, "home": a["home"]})
            return self.send_json(200, {"apps": apps, "files": [{"name": f, "size": os.path.getsize(os.path.join(d, f))} for f in fs], "installed": sorted(inst)})
        sbody = self.jbody() if act == "store" and self.command == "POST" else {}          # đọc thân yêu cầu 1 lần (đọc lần 2 sẽ rỗng)
        if act == "store" and self.command == "POST" and isinstance(sbody.get("id"), str):   # 🛍 KHO APP: tải chính chủ (lần đầu) + cài
            app = next((a for a in KHO_APPS if a["id"] == sbody.get("id")), None)
            if not app: return self.send_json(404, {"error": "Không có app này trong kho."})
            jid = new_job(me["uid"], "Cài " + app["name"])
            def work(j):
                def say(m): JOBS[j]["msg"] = m
                say(f"Đang chuẩn bị {app['name']}…")
                fp = kho_fetch(app, _kho_abis(port), say)
                say(f"Đang cài {app['name']} vào máy…")
                files, dst = stage_pkg(fp, os.path.basename(fp))
                try: o = out(adb(port, ["install", "-r", "-g", files[0]], timeout=900))
                finally: subprocess.run(["docker", "exec", WSNAME, "rm", "-rf", dst], capture_output=True, timeout=60)
                if "Success" not in o: raise RuntimeError(install_err(o))
                return f"✅ Đã cài {app['name']} — mở trên màn hình chính của máy."
            run_job(jid, work)
            return self.send_json(200, {"job": jid})
        if act == "store" and self.command == "POST":          # cài 1 app trong kho vào máy này (file admin bỏ vào ~/apk-cai-san)
            n = safe_name(str(sbody.get("name") or "")); fp = os.path.join(pre_dir(), n)
            if not n.lower().endswith(APK_EXT) or not os.path.isfile(fp): return self.send_json(404, {"error": "Không có app này trong kho."})
            jid = new_job(me["uid"], "Cài " + n)
            def work(j):
                JOBS[j]["msg"] = "Đang cài " + n + "…"
                files, dst = stage_pkg(fp, n)
                try:
                    args = (["install", "-r", "-g", files[0]] if len(files) == 1 else ["install-multiple", "-r", "-g"] + files)
                    o = out(adb(port, args, timeout=900))
                finally:
                    subprocess.run(["docker", "exec", WSNAME, "rm", "-rf", dst], capture_output=True, timeout=60)
                if "Success" not in o: raise RuntimeError(install_err(o))
                return "✅ Đã cài " + n
            run_job(jid, work)
            return self.send_json(200, {"job": jid})
        if act == "play" and self.command == "POST":           # mở trang app trên Google Play trong máy (Chrome, Firefox…)
            pkg = str(self.jbody().get("pkg") or "")
            if not re.match(r"^[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+$", pkg): return self.send_json(400, {"error": "Tên app không hợp lệ."})
            r = shell(port, MAIN_SH + "am start $D -a android.intent.action.VIEW -d " + shlex.quote("market://details?id=" + pkg), 20)
            return self.send_json(200, {"ok": True})

        if act == "gps" and self.command == "POST":           # ĐỔI VỊ TRÍ GPS (vị trí giả) — Android 12+ (lệnh "cmd location providers" của Android)
            b = self.jbody()
            if b.get("off"):
                shell(port, "for P in gps network fused; do cmd location providers remove-test-provider $P >/dev/null 2>&1; done; true", 30)
                return self.send_json(200, {"ok": True, "msg": "Đã tắt vị trí giả."})
            try: lat, lng = float(b.get("lat")), float(b.get("lng"))
            except (TypeError, ValueError): return self.send_json(400, {"error": "Toạ độ không hợp lệ."})
            if not (-90 <= lat <= 90 and -180 <= lng <= 180): return self.send_json(400, {"error": "Toạ độ không hợp lệ."})
            try: sdk = int(out(shell(port, "getprop ro.build.version.sdk", 15)).strip() or 0)
            except ValueError: sdk = 0
            if sdk < 31: return self.send_json(400, {"error": "Đổi vị trí GPS cần máy Android 12 trở lên."})
            loc = f"{lat:.6f},{lng:.6f}"
            o = out(shell(port, "appops set com.android.shell android:mock_location allow; cmd location set-location-enabled true >/dev/null 2>&1; "
                                "for P in gps network fused; do cmd location providers add-test-provider $P >/dev/null 2>&1; "
                                "cmd location providers set-test-provider-enabled $P true >/dev/null 2>&1; "
                                f"cmd location providers set-test-provider-location $P --location {loc} --accuracy 3 2>&1; done; echo DONE", 40))
            if "DONE" not in o or "Exception" in o: return self.send_json(500, {"error": "Chưa đặt được vị trí: " + o[-160:]})
            return self.send_json(200, {"ok": True, "msg": f"Đã đặt vị trí {loc}. Mở lại app cần vị trí để nhận vị trí mới."})

        if act == "clone":                                     # CLONE TAB: chạy thêm bản thứ 2, 3… của app (VD Roblox chính thức), mỗi bản trong 1 "hồ sơ Công việc"
            LU = "pm list users | sed -n 's/.*UserInfo{\\([0-9]*\\):\\(CloneTab[0-9]*\\):.*/\\2 \\1/p'"
            if self.command == "GET":
                rows = [l.split() for l in out(shell(port, LU, 20)).splitlines() if len(l.split()) == 2]
                cnt = {}
                for nm, u in rows:
                    for l in out(shell(port, f"pm list packages -3 --user {u}", 30)).splitlines():
                        if l.startswith("package:"):
                            k = l.split(":", 1)[1].strip()
                            if k != BR_PKG: cnt[k] = cnt.get(k, 0) + 1
                if int(port) >= 21500 and cnt: threading.Thread(target=clone_icons, args=(port,), daemon=True).start()   # máy cũ đã clone → thêm biểu tượng
                return self.send_json(200, {"profile": rows[0][1] if rows else None, "cloned": sorted(cnt), "counts": cnt, "max": CLONE_MAX})
            b = self.jbody(); pkg = str(b.get("pkg") or "")
            if not PKG.match(pkg): return self.send_json(400, {"error": "Tên ứng dụng không hợp lệ."})
            if b.get("remove"):
                for l in out(shell(port, LU, 20)).splitlines():
                    if len(l.split()) == 2: shell(port, f"pm uninstall --user {l.split()[1]} {shlex.quote(pkg)}", 60)
                if int(port) >= 21500: clone_icons(port)
                return self.send_json(200, {"ok": True, "msg": "Đã bỏ các bản clone."})
            if b.get("open"):                  # MỞ bản clone số i (màn hình chính của máy có thể không có tab Công việc)
                try: i = max(1, int(b.get("open")))
                except (TypeError, ValueError): i = 1
                q = shlex.quote(pkg); us = []
                for l in out(shell(port, LU, 20)).splitlines():
                    if len(l.split()) != 2: continue
                    nm, u = l.split()
                    if f"package:{pkg}" in out(shell(port, f"pm list packages --user {u} {q}", 20)).split():
                        us.append((int(re.sub(r"\D", "", nm) or 1), u))
                us.sort()
                if len(us) < i: return self.send_json(404, {"error": "Chưa có bản clone này — bấm Clone trước."})
                u = us[i - 1][1]
                o = out(shell(port, f"am start-user {u} >/dev/null 2>&1; C=$(cmd package resolve-activity --brief --user {u} {q} | tail -n 1); "
                                    f"{FULLSCREEN_SH}am start $W --user {u} {AS_ICON} -n \"$C\" 2>&1", 40))   # mở TOÀN MÀN (không cửa sổ nổi) → game tự xoay ngang
                if "Error" in o or "Exception" in o: return self.send_json(500, {"error": "Chưa mở được bản clone: " + o[-160:]})
                return self.send_json(200, {"ok": True, "msg": f"Đã mở bản clone {i} của {pkg}."})
            memu_cap = None
            if int(port) >= 21500:          # máy MEmu (Windows): mỗi Roblox chạy song song cần ~3GB RAM + 2 nhân riêng
                ram, cpu = float(p.get("ram") or 0), float(p.get("cpu") or 0)
                memu_cap = int(min((ram - 3) // 3, (cpu - 2) // 2))
                if memu_cap < 1:
                    return self.send_json(400, {"error": f"Máy {ram:g}GB / {cpu:g} nhân chưa đủ để chạy thêm Roblox (máy sẽ bị đứng). "
                                                         "Clone tab cần tối thiểu 6GB RAM + 4 nhân cho 1 bản clone (mỗi bản thêm cần +3GB, +2 nhân) — "
                                                         "bấm Nâng cấp RAM/CPU rồi clone lại. Hoặc thuê thêm máy và dùng Nhiều máy + Đồng bộ."})
            try: n = max(1, min(CLONE_MAX, int(b.get("n") or 1)))
            except (TypeError, ValueError): return self.send_json(400, {"error": "Số bản clone không hợp lệ."})
            if memu_cap is not None and n > memu_cap:
                return self.send_json(400, {"error": f"Máy này chỉ đủ chạy {memu_cap} bản clone cho mượt (mỗi bản cần +3GB RAM, +2 nhân). "
                                                     "Chọn ít bản hơn, hoặc bấm Nâng cấp RAM/CPU."})
            jid = new_job(me["uid"], f"Clone {pkg} ×{n}")
            def work(j):
                JOBS[j]["msg"] = f"Đang tạo {n} bản clone (mỗi bản ~20 giây)…"
                if cont and not str(cont).startswith("cloudgpu"):   # máy ảo mặc định chỉ cho 1 người dùng → mở thêm (cần quyền root của server)
                    subprocess.run(["docker", "exec", cont, "/system/bin/sh", "-c", "setprop fw.max_users 10"], capture_output=True, timeout=20)
                q = shlex.quote(pkg)
                o = out(shell(port, f"pm path {q} >/dev/null 2>&1 || {{ echo NOPKG; exit 0; }}; "
                                    f"i=1; while [ $i -le {n} ]; do NM=CloneTab; [ $i -gt 1 ] && NM=CloneTab$i; "
                                    f"U=$(pm list users | sed -n \"s/.*UserInfo{{\\([0-9]*\\):$NM:.*/\\1/p\" | head -1); "
                                    f"[ -n \"$U\" ] || U=$(pm create-user --profileOf 0 --managed $NM 2>&1 | sed -n 's/.*created user id \\([0-9]*\\).*/\\1/p'); "
                                    f"[ -n \"$U\" ] || {{ echo LIMIT$i; break; }}; am start-user $U >/dev/null 2>&1; "
                                    f"pm install-existing --user $U {q} >/dev/null 2>&1; i=$((i+1)); done; "
                                    f"settings put global package_verifier_enable 0; "
                                    f"C=0; for U in $(pm list users | sed -n 's/.*UserInfo{{\\([0-9]*\\):CloneTab[0-9]*:.*/\\1/p'); do "
                                    f"pm list packages --user $U | grep -qx package:{q} && C=$((C+1)); done; echo DONE$C", 60 + 60 * n))
                if "NOPKG" in o: raise RuntimeError("Máy chưa cài app này — cài bản chính trước rồi mới clone.")
                m = re.search(r"DONE(\d+)", o); done = int(m.group(1)) if m else 0
                lim = re.search(r"LIMIT(\d+)", o)
                if lim and done < n:
                    if done == 0: raise RuntimeError("Android trong máy không cho tạo hồ sơ clone.")
                    mc = cont and subprocess.run(["docker", "exec", cont, "/system/bin/sh", "-c", "[ -f /system/overlay/BlueRobloxMultiClone.apk ] && echo Y"],
                                                 capture_output=True, text=True, timeout=20).stdout.strip() == "Y"
                    if mc: raise RuntimeError(f"Đã có {done} bản clone. Máy cần KHỞI ĐỘNG LẠI 1 lần để mở thêm bản clone — bấm \"Khởi động lại\" rồi clone lại.")
                    raise RuntimeError(f"Đã có {done} bản clone — máy này chỉ cho tối đa {done} bản. Cần thêm acc thì thuê thêm máy và dùng Nhiều máy + Đồng bộ.")
                if done < 1: raise RuntimeError("Chưa clone được: " + o[-150:])
                if int(port) >= 21500 and clone_icons(port) > 0:
                    return f"✅ Đã có {done} bản clone! Trên màn hình chính máy có biểu tượng cá voi \"Clone 1\", \"Clone 2\"… — bấm vào là mở bản clone."
                return f"✅ Đã có {done} bản clone! Mở lại Clone tab → bấm ▶ Mở bản 1, 2… để chạy bản clone (hoặc tab Công việc/Work trong danh sách ứng dụng)."
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "apps":
            r = shell(port, "pm list packages -3", 30)
            pk = sorted(l.split(":", 1)[1].strip() for l in out(r).splitlines() if l.startswith("package:") and l.split(":", 1)[1].strip() != BR_PKG)
            return self.send_json(200, {"apps": pk})

        if act in ("launch", "stop", "uninstall", "clear") and self.command == "POST":
            pkg = str(self.jbody().get("pkg") or "")
            if not PKG.match(pkg): return self.send_json(400, {"error": "Tên ứng dụng không hợp lệ."})
            if act == "launch":                               # mở TOÀN MÀN (Android 10+: không bật thành cửa sổ nổi) → game cần ngang tự xoay ngang
                r = shell(port, f"{FULLSCREEN_SH}C=$(cmd package resolve-activity --brief {pkg} 2>/dev/null | tail -n 1); "   # android/… = hộp chọn (app có 2 màn mở) → monkey
                                f"case \"$C\" in android/*) monkey -p {pkg} -c android.intent.category.LAUNCHER 1 ;; */*) am start $W {AS_ICON} -n \"$C\" ;; "
                                f"*) monkey -p {pkg} -c android.intent.category.LAUNCHER 1 ;; esac", 20)
            elif act == "stop": r = shell(port, f"am force-stop {pkg}", 15)
            elif act == "clear": r = shell(port, f"pm clear {pkg}", 30)
            else: r = adb(port, ["uninstall", pkg], 60)
            return self.send_json(200, {"ok": True, "out": out(r)[-200:]})

        if act == "upload" and self.command == "POST":
            upid = q.get("id", "")
            if not re.match(r"^[a-z0-9]{8,40}$", upid): return self.send_json(400, {"error": "Mã tải lên không hợp lệ."})
            name = safe_name(q.get("name", ""))
            total, off = int(q.get("total") or 0), int(q.get("off") or 0)
            if total <= 0 or total > MAX_FILE: return self.send_json(400, {"error": "File rỗng hoặc lớn hơn 4GB."})
            path = os.path.join(UP_DIR, f"{pid}_{upid}.part")
            if off == 0:                         # dọn file tải dở bị bỏ quá 6 giờ
                for f in os.listdir(UP_DIR):
                    fp = os.path.join(UP_DIR, f)
                    try:
                        if time.time() - os.path.getmtime(fp) > 6 * 3600: os.remove(fp)
                    except OSError: pass
            have = os.path.getsize(path) if os.path.exists(path) else 0
            if off == 0 and have == 0 and shutil.disk_usage(UP_DIR).free < total + 3 * 1024 ** 3:
                return self.send_json(507, {"error": "Server tạm hết dung lượng, thử lại sau."})
            if off != have: return self.send_json(409, {"error": "Lệch vị trí", "size": have})
            data = self.body(MAX_CHUNK)
            if have + len(data) > total: return self.send_json(400, {"error": "Dữ liệu vượt kích thước file."})
            with open(path, "ab") as f: f.write(data)
            have += len(data)
            if have < total: return self.send_json(200, {"size": have})
            jid = new_job(me["uid"], name)
            run_job(jid, lambda j: deliver(port, path, name, j))
            return self.send_json(200, {"size": have, "job": jid})

        if act == "fromurl" and self.command == "POST":
            link = str(self.jbody().get("url") or "").strip()
            if not re.match(r"^https?://\S+$", link) or len(link) > 2000: return self.send_json(400, {"error": "Link phải bắt đầu bằng http:// hoặc https://"})
            jid = new_job(me["uid"], link[-60:])
            def work(j):
                path, name = download(link, j)
                JOBS[j]["title"] = name
                return deliver(port, path, name, j)
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "display" and self.command == "POST":
            b = self.jbody(); lo, hi = fps_limits()
            try: fps = int(b.get("fps") or p.get("fps") or 30)
            except Exception: return self.send_json(400, {"error": "FPS không hợp lệ."})
            res = re.sub(r"\s", "", str(b.get("res") or p.get("res") or "720x1280")).lower().replace("*", "x").replace("×", "x")
            m = re.match(r"^(\d{3,4})x(\d{3,4})$", res)
            if not (lo <= fps <= hi): return self.send_json(400, {"error": f"FPS phải từ {lo} đến {hi}."})
            if fps > 60 and float(p.get("cpu") or 0) < 4:      # máy nhỏ chạy FPS cao → quá tải, giật, xám màn hình
                return self.send_json(400, {"error": "Máy dưới 4 nhân chỉ chọn tối đa 60 FPS (treo game nên để 30 FPS cho mượt)."})
            if not m or not all(320 <= int(v) <= 4096 for v in m.groups()): return self.send_json(400, {"error": "Độ phân giải phải dạng rộng x cao, VD 1080x1920."})
            if pid in _busy: return self.send_json(409, {"error": "Máy đang được đổi cấu hình, đợi chút."})
            jid = new_job(me["uid"], f"{res} · {fps} FPS")
            same_fps = fps == int(p.get("fps") or 30)
            def work(j):
                _busy.add(pid)
                try:
                    if same_fps:                      # chỉ đổi kích thước → đổi ngay, app đang mở KHÔNG bị tắt
                        JOBS[j]["msg"] = "Đang đổi kích thước màn hình…"
                        r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "liveres", cont, "--res", res],
                                           capture_output=True, text=True, timeout=120)
                        if r.returncode == 0:
                            sb_patch(f"/rest/v1/cloud_phones?id=eq.{pid}", {"res": res})
                            return f"Đã đổi sang {res} — app đang chạy vẫn giữ nguyên."
                    JOBS[j]["msg"] = "Đang áp dụng và khởi động lại máy (1–3 phút)…"
                    r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "reconfig", cont, "--fps", str(fps), "--res", res],
                                       capture_output=True, text=True, timeout=600)
                    if r.returncode: raise RuntimeError("Đổi cấu hình lỗi: " + (r.stdout + r.stderr)[-300:])
                    sb_patch(f"/rest/v1/cloud_phones?id=eq.{pid}", {"fps": fps, "res": res})
                    return f"Đã đổi sang {res} · {fps} FPS. Dữ liệu vẫn giữ nguyên."
                finally:
                    _busy.discard(pid)
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "root" and self.command == "POST":        # khách bấm "Root máy": kiểm tra + bật root (su) cho máy
            if not cont: return self.send_json(409, {"error": "Không xác định được máy."})
            jid = new_job(me["uid"], "Root máy")
            def work(j):
                JOBS[j]["msg"] = "Đang kiểm tra / bật root (máy có thể khởi động lại ~1 phút)…"
                r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "rootfix", cont, "--force"], capture_output=True, text=True, timeout=600)
                line = next((l for l in (r.stdout or "").splitlines() if l.startswith("ROOT_")), "")
                msg = line.split(":", 1)[1].strip() if ":" in line else "Không kiểm tra được, thử lại sau."
                if line.startswith("ROOT_OK"): return "✅ Máy đã ROOT. Tool cần root (gọi lệnh su) dùng được ngay, không cần khởi động lại."
                if line.startswith("ROOT_WAIT"): return "⏳ Máy đang bật root, chờ 1 phút rồi bấm lại."
                raise RuntimeError("Chưa root được: " + msg)
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "rootcfg":                                 # ROOT THEO TỪNG APP (🔓 Root trong bảng Công cụ): công tắc + danh sách app được dùng su
            if not cont: return self.send_json(409, {"error": "Không xác định được máy."})
            pc_ = os.path.join(HOME, "phonectl.py")
            if self.command == "GET":
                r = subprocess.run(["python3", pc_, "rootcfg", cont, "--get"], capture_output=True, text=True, timeout=90)
                m = re.search(r"^ROOTCFG (\{.*\})\s*$", r.stdout or "", re.M)
                if not m:
                    if r.returncode == 2 and "rootcfg" in (r.stderr or ""):
                        return self.send_json(409, {"error": "Máy chủ chưa cập nhật bản có Root theo app — báo admin cập nhật.", "old": True})
                    return self.send_json(500, {"error": "Không đọc được cấu hình root: " + ((r.stdout or "") + (r.stderr or "")).strip()[-200:]})
                try: return self.send_json(200, json.loads(m.group(1)))
                except ValueError: return self.send_json(500, {"error": "Cấu hình root đọc được bị lỗi."})
            if self.command != "POST": return self.send_json(405, {"error": "Chỉ GET hoặc POST."})
            b = self.jbody(); on = b.get("on"); apps = b.get("apps") if b.get("apps") is not None else []
            if not isinstance(on, bool): return self.send_json(400, {"error": "Thiếu bật / tắt root."})
            if not isinstance(apps, list) or len(apps) > 300 or any(not isinstance(x, str) or not PKG.match(x) for x in apps):
                return self.send_json(400, {"error": "Danh sách app không hợp lệ."})
            if pid in _rootbusy: return self.send_json(409, {"error": "Đang lưu cấu hình root của máy này, đợi vài giây."})
            _rootbusy.add(pid)
            jid = new_job(me["uid"], "Root theo app")
            def work(j):
                try:
                    JOBS[j]["msg"] = ("Đang bật root cho app đã chọn… (máy chưa có root gốc sẽ tự khởi động lại ~1 phút)" if on else "Đang tắt root…")
                    r = subprocess.run(["python3", pc_, "rootcfg", cont, "--set", "--on" if on else "--off", "--apps", ",".join(dict.fromkeys(apps))],
                                       capture_output=True, text=True, timeout=600)
                    line = next((l for l in reversed((r.stdout or "").splitlines()) if l.startswith("ROOTCFG_")), "")
                    if line.startswith("ROOTCFG_OK"): return line.split(" ", 1)[1].strip() if " " in line else "Đã lưu."
                    if not line and r.returncode == 2 and "rootcfg" in (r.stderr or ""):
                        raise RuntimeError("Máy chủ chưa cập nhật bản có Root theo app — báo admin cập nhật.")
                    raise RuntimeError(line.split(" ", 1)[1].strip() if " " in line else "Không lưu được cấu hình root, thử lại sau.")
                finally: _rootbusy.discard(pid)
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "gfx" and self.command == "GET":           # CHẾ ĐỘ HÌNH (máy MEmu): mượt (DirectX) hay hiện 3D (OpenGL)
            if not cont: return self.send_json(409, {"error": "Không xác định được máy."})
            r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "gfxget", cont], capture_output=True, timeout=60)
            m = re.search(r"GFX=(\w+)", out(r))
            return self.send_json(200, {"mode": m.group(1) if m else "unknown"})
        if act == "gfx" and self.command == "POST":
            mode = str(self.jbody().get("mode") or "")
            if mode not in ("opengl", "directx"): return self.send_json(400, {"error": "Chế độ không hợp lệ."})
            if not cont: return self.send_json(409, {"error": "Không xác định được máy."})
            jid = new_job(me["uid"], "Đổi chế độ hình")
            def work(j):
                JOBS[j]["msg"] = "Máy đang khởi động lại với chế độ mới (khoảng 1–2 phút)…"
                r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "render", cont, mode], capture_output=True, timeout=600)
                if r.returncode: raise RuntimeError("Không đổi được: " + out(r)[-200:])
                return ("Đã chuyển sang MƯỢT." if mode == "directx" else "Đã chuyển sang HIỆN 3D.") if wait_ready(cont, port) else "Đã đổi, đang kết nối lại…"
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        if act == "reboot" and self.command == "POST":
            if not cont: return self.send_json(409, {"error": "Không xác định được máy."})
            force = bool(self.jbody().get("force")) and me["admin"]    # admin ÉP khởi động lại: tắt hẳn (máy treo → tắt cưỡng bức) rồi bật
            if force and is_locked(p): return self.send_json(409, {"error": "Máy đang bị khoá — mở khoá trước rồi hãy ép khởi động lại."})
            if force and pid in _busy: return self.send_json(409, {"error": "Máy đang khởi động lại / đổi cấu hình — đợi xong rồi thử lại."})
            jid = new_job(me["uid"], "Ép khởi động lại" if force else "Khởi động lại")
            if force: _busy.add(pid)                                  # giữ chỗ ngay: bấm 2 lần liền không chạy chồng
            def work(j):
                if not force:
                    r = subprocess.run(["python3", os.path.join(HOME, "phonectl.py"), "restart", cont], capture_output=True, timeout=120)
                    if r.returncode: raise RuntimeError("Không khởi động lại được: " + out(r)[-200:])
                    JOBS[j]["msg"] = "Đang khởi động Android (1–3 phút)…"
                    return "Máy đã khởi động lại xong." if wait_ready(cont, port) else "Máy đã khởi động, đang kết nối lại…"
                try:
                    JOBS[j]["msg"] = "Đang tắt hẳn máy (máy treo thì tắt cưỡng bức)…"
                    cmd = ["python3", os.path.join(HOME, "phonectl.py"), "restart", cont]
                    r = subprocess.run(cmd + ["--force"], capture_output=True, timeout=420)
                    if r.returncode == 2 and b"--force" in (r.stderr or b""):     # phonectl cũ chưa có --force → khởi động lại thường
                        r = subprocess.run(cmd, capture_output=True, timeout=180)
                    if r.returncode: raise RuntimeError("Không ép khởi động lại được: " + out(r)[-300:])
                    hard = "cưỡng bức" in out(r)
                    JOBS[j]["msg"] = "Đang khởi động Android (1–3 phút)…"
                    if not wait_ready(cont, port): return "Máy đã bật lại, đang kết nối…" + (" (máy treo — đã tắt cưỡng bức)" if hard else "")
                    return "Đã ép khởi động lại xong" + (" (máy treo — đã tắt cưỡng bức)." if hard else ".")
                finally:
                    _busy.discard(pid)
            run_job(jid, work)
            return self.send_json(200, {"job": jid})

        return self.send_json(404, {"error": "Không có chức năng này."})

    # ---------- Cổng bảo vệ trước ws-scrcpy ----------
    def proxy(self):
        try:
            self._proxy()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log("proxy lỗi:", repr(e))
            try: self.deny(502, "Trình điều khiển tạm thời không phản hồi.")
            except Exception: pass

    def _proxy(self):
        auth = self.cookie_auth()
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if (self.headers.get("Upgrade") or "").lower() == "websocket":
            origin = self.headers.get("Origin", "")
            if origin and origin not in SELF_ORIGINS: return self.deny(403, "Nguồn không được phép.")
            if not auth: return self.deny(401, "Hãy mở máy từ app hoặc trang web.")
            if not auth.get("a"):
                if maint().get("maint"): return self.deny(503, "Đang bảo trì.")
                if q.get("action") != "proxy-adb" or q.get("remote") != "tcp:8886": return self.deny(403, "Không được phép.")
                m = re.match(r"^127\.0\.0\.1:(\d{4,5})$", q.get("udid", ""))
                if not m or auth.get("u") not in port_owners(int(m.group(1))): return self.deny(403, "Đây không phải máy của bạn.")
            m2 = re.match(r"^127\.0\.0\.1:(\d{4,5})$", q.get("udid", ""))
            viewer = re.sub(r"[^\w-]", "", q.get("cpv", ""))[:40]
            key = (int(m2.group(1)) if m2 and q.get("action") == "proxy-adb" else None)
            return self.pipe_ws(key if key and viewer and not auth.get("a") else None, viewer, live=key,
                                uid=None if auth.get("a") or not key else auth.get("u"))
        if self.command not in ("GET", "HEAD") and not (auth and auth.get("a")):
            return self.deny(403, "Không được phép.")
        return self.pipe_http()

    def pipe_http(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else None
        hdr = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {"cookie", "host", "content-length", "accept-encoding", "if-none-match", "if-modified-since"}}
        hdr["Host"] = "%s:%d" % UPSTREAM
        c = http.client.HTTPConnection(*UPSTREAM, timeout=60)
        c.request(self.command, self.path, body=data, headers=hdr)
        r = c.getresponse()
        body = r.read()
        c.close()
        self.send_response(r.status, r.reason)
        html = "text/html" in (r.getheader("Content-Type") or "")
        for k, v in r.getheaders():
            if k.lower() not in HOP | {"content-length"} and not (html and k.lower() in ("cache-control", "etag", "last-modified")): self.send_header(k, v)
        if html:
            self.send_header("Content-Security-Policy", "frame-ancestors " + " ".join(sorted(ORIGINS | SELF_ORIGINS)))
            self.send_header("Cache-Control", "no-store")
            if r.status == 200:
                m = re.search(rb"<head[^>]*>", body, re.I)
                body = (body[:m.end()] + INJECT_TAG + body[m.end():]) if m else (INJECT_TAG + body)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)

    def pipe_ws(self, port=None, viewer="", live=None, uid=None):
        if live:
            with VLOCK: LIVE[live] = LIVE.get(live, 0) + 1
        up = socket.create_connection(UPSTREAM, timeout=10)
        me = {"viewer": viewer, "close": None}
        if port:                                  # mỗi máy chỉ 1 nơi xem (khách): nơi mở sau thay nơi cũ → không giành luồng hình
            with VLOCK:
                old = VIEWERS.get(port)
                VIEWERS[port] = me
            if old and old["viewer"] != viewer and old["close"]:
                try: old["close"]()
                except Exception: pass
        for s_ in (up, self.connection):          # gửi ngay từng gói nhỏ (chạm, phím) — không chờ gom
            try: s_.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError: pass
        lines = [f"{self.command} {self.path} HTTP/1.1"]
        for k, v in self.headers.items():
            if k.lower() == "cookie": continue
            lines.append(f"{k}: {'%s:%d' % UPSTREAM if k.lower() == 'host' else v}")
        up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        up.settimeout(None)
        cli = self.connection
        cli.settimeout(None)
        self.close_connection = True

        def kick():
            for s_ in (up, cli):
                try: s_.shutdown(socket.SHUT_RDWR)
                except Exception: pass
        me["close"] = kick

        if uid and live:                          # phiên đang mở: chủ máy TẮT CHIA SẺ / chuyển máy / admin khoá máy → ngắt (≤ ~40 giây)
            def guard():
                while not me.get("done"):
                    time.sleep(REAUTH_S)
                    if me.get("done"): break
                    try: ok = uid in port_owners(live)
                    except Exception: ok = True       # Supabase lỗi mạng → không ngắt oan
                    if not ok:
                        log(f"ngắt phiên web {str(uid)[:8]} cổng {live}: hết quyền (tắt chia sẻ / chuyển máy / khoá máy)")
                        kick(); break
            threading.Thread(target=guard, daemon=True).start()

        def client_to_up():
            try:
                while True:
                    d = self.rfile.read1(262144)
                    if not d: break
                    up.sendall(d)
            except Exception:
                pass
            finally:
                try: up.shutdown(socket.SHUT_WR)
                except Exception: pass

        t = threading.Thread(target=client_to_up, daemon=True)
        t.start()
        try:
            while True:
                d = up.recv(262144)
                if not d: break
                cli.sendall(d)
        except Exception:
            pass
        finally:
            me["done"] = True
            try: up.close()
            except Exception: pass
            try: cli.shutdown(socket.SHUT_RDWR)
            except Exception: pass
            with VLOCK:
                if port and VIEWERS.get(port) is me: VIEWERS.pop(port, None)
                if live:
                    LIVE[live] = LIVE.get(live, 1) - 1
                    if LIVE[live] <= 0: LIVE.pop(live, None)
        t.join(timeout=3)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    for f in os.listdir(UP_DIR):          # dọn file tải dở từ lần chạy trước
        try: os.remove(os.path.join(UP_DIR, f))
        except OSError: pass
    log(f"cpapi chạy ở {LISTEN[0]}:{LISTEN[1]} → bảo vệ ws-scrcpy {UPSTREAM[1]}, trang chủ {SELF_ORIGIN}" + (f", đường thẳng {FAST_ORIGIN}" if FAST_ORIGIN else ""))
    Server(LISTEN, H).serve_forever()
