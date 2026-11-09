# -*- coding: utf-8 -*-
# =====================================================================================================
#  bluestream.py — PHÁT HÌNH v2 cho APP PC + APP ANDROID (web không phát hình nữa)
#
#  Đường hình:  cửa sổ giả lập trên Windows (quay bằng Windows Graphics Capture, chạy ngầm vẫn quay được)
#               → nén bằng card NVIDIA (NVENC; card hết phiên → CPU x264) → mỗi khung 1 gói → app giải mã bằng phần cứng
#               Windows không quay được cửa sổ (Windows 10 trước 1903, VD 1511) → hình lấy THẲNG từ Android: scrcpy-server 2.4
#               (video=true) mã hoá H.264 ngay trong máy → không cần quay cửa sổ / ffmpeg (CAPTURE=scrcpy | gdi | wgc để ép)
#  Đường chạm:  app → máy chủ → scrcpy-server 2.4 (chỉ điều khiển, không phát hình) chạy trong máy Android
#  Kết nối:     TRỰC TIẾP  TLS cổng STREAM_PORT (8189, modem phải mở cổng TCP về máy này)   ← nhanh nhất
#               DỰ PHÒNG   WebSocket 127.0.0.1:STREAM_WS_PORT (8020) qua đường hầm Cloudflare (STREAM_WS=wss://…)
#  Giao thức:   BRS2 — docs/STREAM-PROTOCOL.md
#
#  Mở cổng:     máy chủ TỰ mở cổng TCP STREAM_PORT trên modem bằng UPnP-IGD (lúc chạy + mỗi 30 phút) — modem tắt UPnP thì mở tay
#  Chạy:  python bluestream.py            (bảng BlueRoblox tự chạy — dịch vụ "phat-hinh")
#         python bluestream.py --selftest (máy Linux/thử: nguồn hình giả, không cần đăng nhập)
#         python bluestream.py --upnp     (thử mở cổng trên modem bằng UPnP 1 lần, in kết quả — không chạy máy chủ)
#  cloudphone.conf:  STREAM_PORT=8189 · STREAM_WS_PORT=8020 · STREAM_WS=wss://stream.blueroblox.shop/v2/stream
#                    STREAM_PUBLIC_IP= (trống = tự dò) · STREAM_CPU=1 (luôn nén CPU) · NVENC_MAX=5 · UPNP=0 (không tự mở cổng)
# =====================================================================================================
import asyncio, base64, collections, ctypes, datetime, hashlib, json, os, queue, random, re, socket, ssl, struct, subprocess, sys, threading, time
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

WIN = os.name == "nt"
B = os.path.dirname(os.path.abspath(__file__))
RTC = os.path.join(B, "rtc"); os.makedirs(RTC, exist_ok=True)
NOWIN = 0x08000000 if WIN else 0
SELFTEST = "--selftest" in sys.argv


def log(*a):
    try: print(time.strftime("%H:%M:%S"), *a, flush=True)
    except Exception: pass


def load_conf():
    c = {}
    for f in (os.path.join(B, "cloudphone.conf"), os.path.expanduser("~/cloudphone.conf")):
        try:
            for line in open(f, encoding="utf-8-sig"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1); c.setdefault(k.strip(), v.strip())
        except FileNotFoundError:
            pass
    return c


C = load_conf()
SB = (C.get("SUPABASE_URL") or "").rstrip("/")
KEY = C.get("SUPABASE_SERVICE_KEY") or ""
NODE_ID = C.get("NODE_ID") or socket.gethostname()
PRIMARY = C.get("PRIMARY", "1") == "1"
PORT = int(C.get("STREAM_PORT") or 8189)
WS_PORT = int(C.get("STREAM_WS_PORT") or 8020)
WS_URL = (C.get("STREAM_WS") or "").strip()
API_BASE = (C.get("PUBLIC_BASE") or "https://phone.blueroblox.shop").rstrip("/")
ALWAYS_CPU = C.get("STREAM_CPU", "0") == "1"
NVENC_MAX = int(C.get("NVENC_MAX") or 5)
FF_URL = "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip"   # 6.1: hợp driver NVENC 12.x (GTX 10xx)
FF = next((p for p in (os.path.join(RTC, "ffmpeg.exe"), os.path.join(RTC, "ffmpeg")) if os.path.isfile(p)), None) or ("ffmpeg" if not WIN else os.path.join(RTC, "ffmpeg.exe"))


def ensure_ffmpeg():
    """Tải FFmpeg 6.1.1 (bản chính thức của Gyan trên GitHub) vào rtc\\ffmpeg.exe nếu chưa có."""
    global FF
    if not WIN or (os.path.isfile(os.path.join(RTC, "ffmpeg.exe")) and os.path.isfile(os.path.join(RTC, "ff61.ok"))): return
    import io, zipfile
    try:
        log("tải FFmpeg 6.1.1 (~80MB, 1 lần)…")
        data = urllib.request.urlopen(urllib.request.Request(FF_URL, headers={"User-Agent": "BlueRoblox"}), timeout=600).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        tmp = os.path.join(RTC, "ffmpeg.exe.tmp")
        open(tmp, "wb").write(z.read(next(x for x in z.namelist() if x.endswith("/bin/ffmpeg.exe"))))
        os.replace(tmp, os.path.join(RTC, "ffmpeg.exe")); open(os.path.join(RTC, "ff61.ok"), "w").write("1")
        FF = os.path.join(RTC, "ffmpeg.exe"); log("✓ đã có FFmpeg")
    except Exception as e:
        log("không tải được FFmpeg:", e)
ADB = next((p for p in (os.path.join(B, "platform-tools", "adb.exe"),) if os.path.isfile(p)), None) or "adb"
JAR = os.path.join(RTC, "scrcpy-server-v2.4")
JAR_URL = "https://github.com/Genymobile/scrcpy/releases/download/v2.4/scrcpy-server-v2.4"
JAR_DEV = "/data/local/tmp/br-scrcpy-2.4.jar"
CERT, CKEY = os.path.join(RTC, "stream-cert.pem"), os.path.join(RTC, "stream-key.pem")
PHONES_JSON = os.path.join(B, "redroid", "phones.json")

PRESETS = {"eco": (960, 30, 1500), "bal": (1280, 60, 3000), "hd": (1600, 60, 6000)}     # cạnh dài tối đa, FPS, kbps
# Chế độ TỰ ĐỘNG: bitrate tự hạ / tự tăng theo tốc độ app nhận thật (ACK). Bitrate thấp → giảm luôn độ nét + khung/giây
# (ít điểm ảnh = ít dữ liệu, máy ảo mã hoá + điện thoại giải mã kịp → hết giật, hết trễ dồn). Mạng khoẻ thì về đủ 1280 · 60 FPS.
AUTO_TIERS = ((450, 640, 20), (800, 854, 24), (1300, 1024, 30), (2000, 1280, 30))      # (dưới kbps, cạnh dài tối đa, FPS tối đa)
AUTO_CELL_KBPS = 1500                     # app báo đang dùng 4G/5G → bắt đầu nhẹ (1280 · 30 FPS), mạng ổn thì tự tăng sau ~20 giây
KEYCODE = {"back": 4, "home": 3, "recents": 187, "power": 26, "volup": 24, "voldown": 25, "menu": 82}

# loại tin nhắn (docs/STREAM-PROTOCOL.md)
C_HELLO, C_TOUCH, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_PING, C_QUALITY, C_KEYFRAME, C_CLIP, C_BYE, C_ACK = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A
S_WELCOME, S_VIDEO, S_SIZE, S_CLIP, S_PONG, S_ERROR, S_STATS = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87


# ================================================================ Supabase (khoá service — chỉ nằm trên máy chủ)
def sb(method, path, body=None, token=None, timeout=15, extra=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + (token or KEY), "Content-Type": "application/json"}
    if extra: h.update(extra)
    req = urllib.request.Request(SB + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip() else None


_ucache, _mcache = {}, {"t": 0, "v": {}}


def whoami(token):
    if not token or len(token) > 4096: return None
    k = hashlib.sha256(token.encode()).hexdigest(); now = time.time(); c = _ucache.get(k)
    if c and c[1] > now: return c[0]
    try: u = sb("GET", "/auth/v1/user", token=token)
    except Exception: return None
    uid = u.get("id") if isinstance(u, dict) else None
    if not uid: return None
    try: p = (sb("GET", f"/rest/v1/profiles?id=eq.{uid}&select=role,locked") or [{}])[0]
    except Exception: p = {}
    if p.get("locked"): return None
    me = {"uid": uid, "admin": p.get("role") == "admin"}
    if len(_ucache) > 5000: _ucache.clear()
    _ucache[k] = (me, now + 120)
    return me


def maint():
    if time.time() - _mcache["t"] > 20:
        try: _mcache["v"] = sb("POST", "/rest/v1/rpc/cloudphone_status", {}) or {}
        except Exception: pass
        _mcache["t"] = time.time()
    return _mcache["v"]


def shared_with(pid, uid):
    try:
        rows = sb("GET", f"/rest/v1/cloud_phone_shares?phone_id=eq.{pid}&grantee_id=eq.{uid}&kind=eq.share&revoked=is.false&select=expires_at") or []
    except Exception:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in rows:
        e = r.get("expires_at")
        if not e: return True
        try:
            if datetime.datetime.fromisoformat(e.replace("Z", "+00:00")) > now: return True
        except Exception: pass
    return False


REAUTH_S = 20            # phiên đang mở: kiểm lại quyền mỗi 20 giây (chủ máy TẮT CHIA SẺ / chuyển máy / admin khoá máy → ngắt ngay)
def _share_now(pid, uid):
    """Còn được chia sẻ không: True / False / None (lỗi mạng — không kết luận, không ngắt oan)."""
    try: rows = sb("GET", f"/rest/v1/cloud_phone_shares?phone_id=eq.{pid}&grantee_id=eq.{uid}&kind=eq.share&revoked=is.false&select=expires_at")
    except Exception: return None
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in rows or []:
        e = r.get("expires_at")
        if not e: return True
        try:
            if datetime.datetime.fromisoformat(e.replace("Z", "+00:00")) > now: return True
        except Exception: return True
    return False


def recheck(pid, me):
    """Phiên đang mở còn quyền không → None (còn) hoặc Deny (ngắt). Admin không bị kiểm."""
    if SELFTEST or not me or me.get("admin"): return None
    try: rows = sb("GET", f"/rest/v1/cloud_phones?id=eq.{pid}&select=user_id,locked,locked_until,lock_reason")
    except Exception: return None
    if rows is None: return None
    if not rows: return Deny("NOT_YOURS", "Máy không còn tồn tại.")
    p = rows[0]
    if p.get("user_id") != me.get("uid") and _share_now(pid, me.get("uid")) is False:
        return Deny("REVOKED", "Chủ máy đã tắt chia sẻ hoặc đã chuyển máy — bạn không còn quyền dùng máy này.")
    if locked(p): return Deny("LOCKED", "Máy đang bị khoá: " + (p.get("lock_reason") or "liên hệ hỗ trợ."))
    return None


def locked(p):
    if not p.get("locked"): return False
    u = p.get("locked_until")
    if not u: return True
    try: return datetime.datetime.fromisoformat(u.replace("Z", "+00:00")) > datetime.datetime.now(datetime.timezone.utc)
    except Exception: return True


def phones_json():
    try: return {p["name"]: p for p in json.load(open(PHONES_JSON, encoding="utf-8")).get("phones", [])}
    except Exception: return {}


class Deny(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code, self.msg = code, msg


class CaptureBlocked(Exception):
    """Windows không cho quay cửa sổ giả lập (hoặc quay mà không ra khung nào) → phiên này lấy hình THẲNG từ Android (scrcpy)."""


def authorize(hello):
    """Kiểm tra quyền xem máy. Trả về (me, phone row)."""
    pid = str(hello.get("phone") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", pid): raise Deny("BAD", "Thiếu mã máy.")
    if SELFTEST: return {"uid": "test", "admin": True}, {"id": pid, "name": "Máy thử", "container": "selftest", "port": 0, "android": "9", "status": "active"}
    me = whoami(hello.get("token") or "")
    if not me: raise Deny("AUTH", "Phiên đăng nhập hết hạn, hãy đăng nhập lại.")
    rows = sb("GET", f"/rest/v1/cloud_phones?id=eq.{pid}&select=id,user_id,name,container,port,node,status,locked,locked_until,lock_reason,android,fps") or []
    if not rows: raise Deny("NOT_YOURS", "Không tìm thấy máy.")
    p = rows[0]
    if not (me["admin"] or p.get("user_id") == me["uid"] or shared_with(pid, me["uid"])): raise Deny("NOT_YOURS", "Đây không phải máy của bạn.")
    n = p.get("node")
    if not (n == NODE_ID or (not n and PRIMARY)): raise Deny("OFFLINE", "Máy nằm ở máy chủ khác — hãy mở lại.")
    if p.get("status") != "active": raise Deny("OFFLINE", "Máy chưa chạy (đang tạo, tạm dừng hoặc đã hết hạn).")
    if locked(p) and not me["admin"]: raise Deny("LOCKED", "Máy đang bị khoá: " + (p.get("lock_reason") or "liên hệ hỗ trợ."))
    if (maint().get("maint")) and not me["admin"]: raise Deny("MAINT", maint().get("maint_msg") or "Hệ thống đang bảo trì, quay lại sau ít phút.")
    ps = phones_json().get(p.get("container") or "")
    if ps and ps.get("port") and str(ps["port"]) != str(p.get("port") or ""):
        p["port"] = ps["port"]          # cổng adb THẬT trên máy này (phonectl sửa khi giả lập đổi số máy) — web có thể chưa kịp cập nhật
    if not p.get("container") or not p.get("port"): raise Deny("OFFLINE", "Máy chưa sẵn sàng, thử lại sau ít giây.")
    return me, p


# ================================================================ Quay cửa sổ (Windows Graphics Capture)
if WIN:
    import ctypes.wintypes as wt
    U32 = ctypes.windll.user32
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)      # toạ độ điểm ảnh thật (không bị phóng to Windows làm lệch)
    except Exception:
        try: U32.SetProcessDPIAware()
        except Exception: pass
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def win_title(h):
        n = U32.GetWindowTextLengthW(h)
        if not n: return ""
        b = ctypes.create_unicode_buffer(n + 1); U32.GetWindowTextW(h, b, n + 1); return b.value

    GWL_STYLE, GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, GW_OWNER = -16, -20, 0x80, 0x40000, 4
    _K32 = ctypes.WinDLL("kernel32")
    _K32.OpenProcess.restype = ctypes.c_void_p; _K32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _K32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    _K32.CloseHandle.argtypes = [ctypes.c_void_p]
    # Cửa sổ có chữ trùng tên máy nhưng KHÔNG phải giả lập (PowerShell đang chạy lệnh, Notepad mở file nhật ký…) → bỏ qua
    NOT_EMU = {"python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe", "windowsterminal.exe", "openconsole.exe",
               "notepad.exe", "notepad++.exe", "explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "code.exe", "taskmgr.exe",
               "mmc.exe", "blueserver.exe", "bluerobloxpc.exe"}

    def proc_of(h):
        """(tên tiến trình viết thường, pid) của cửa sổ."""
        pid = wt.DWORD(); U32.GetWindowThreadProcessId(h, ctypes.byref(pid)); name = ""
        hp = _K32.OpenProcess(0x1000, False, pid.value)                     # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            try:
                buf = ctypes.create_unicode_buffer(520); n = wt.DWORD(520)
                if _K32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)): name = re.split(r"[\\/]", buf.value)[-1].lower()
            finally: _K32.CloseHandle(hp)
        return name, pid.value

    def _same_name(name):
        exact, prefix = [], []
        def cb(h, _):
            t = win_title(h)
            if t == name: exact.append(h)
            elif t and (t.startswith(name) or (name in t and len(name) >= 8)): prefix.append(h)
            return True
        U32.EnumWindows(EnumProc(cb), 0)
        return [h for h in exact if proc_of(h)[0] not in NOT_EMU], [h for h in prefix if proc_of(h)[0] not in NOT_EMU]

    def _rank(h):                 # cửa sổ THẬT của máy: đang hiện, có phần vẽ Android, to nhất (giả lập có thể có cửa sổ ẩn phụ trùng tên)
        l, t, r, b = rect_of(h)
        return (bool(U32.IsWindowVisible(h)), render_child(h) is not None, max(0, r - l) * max(0, b - t))

    def find_window(name):
        for hs in _same_name(name):
            if hs:
                h = max(hs, key=_rank); return h, win_title(h)
        return None, None

    def win_info(h):
        """1 dòng mô tả cửa sổ (ghi nhật ký khi Windows không cho quay)."""
        try:
            cls = ctypes.create_unicode_buffer(256); U32.GetClassNameW(h, cls, 256)
            ex = U32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF; st = U32.GetWindowLongW(h, GWL_STYLE) & 0xFFFFFFFF
            cloak = ctypes.c_int(0); ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloak), 4)    # DWMWA_CLOAKED
            l, t, r, b = rect_of(h); pn, pid = proc_of(h)
            fl = [k for k, on in (("đang hiện", U32.IsWindowVisible(h)), ("thu nhỏ", U32.IsIconic(h)), ("chạy ngầm/tool", ex & WS_EX_TOOLWINDOW),
                                   ("app", ex & WS_EX_APPWINDOW), ("cửa sổ con", st & 0x40000000), ("có cửa sổ chủ", U32.GetWindow(h, GW_OWNER)),
                                   ("bị che (cloaked)", cloak.value)) if on]
            return f"hwnd={int(h):#x} '{win_title(h)}' lớp={cls.value} {pn or '?'}:{pid} {r - l}x{b - t} tại ({l},{t}) [{', '.join(fl) or '-'}]"
        except Exception as e:
            return f"hwnd={h} ({e!r})"

    def rect_of(h):
        r = wt.RECT(); U32.GetWindowRect(h, ctypes.byref(r)); return r.left, r.top, r.right, r.bottom

    # Chỗ đỗ cửa sổ máy khách chạy ngầm — GIỐNG HỆT park_xy trong phonectl.py (phonectl đỗ, bluestream quay).
    # KHÔNG dùng (-32000, -32000) = toạ độ cửa sổ thu nhỏ: Windows Graphics Capture báo "The parameter is incorrect".
    PARK = (C.get("PARK") or "corner").strip().lower()       # corner: góc phải dưới màn hình chính, lộ PARK_SHOW điểm ảnh · screen: nằm hẳn trong màn hình
    PARK_SHOW = max(4, int(C.get("PARK_SHOW") or 24))
    KEEP_PROP = "CloudBlueKeep"                              # cửa sổ phải nằm hẳn trong màn hình mới quay được → phonectl không dời đi

    def park_xy(rc, mode=None):
        sw, sh = U32.GetSystemMetrics(0), U32.GetSystemMetrics(1)
        if (mode or PARK) == "screen": return max(0, sw - (rc[2] - rc[0])), max(0, sh - (rc[3] - rc[1]))
        return sw - PARK_SHOW, sh - PARK_SHOW

    def park(h, mode=None):
        x, y = park_xy(rect_of(h), mode)
        U32.SetWindowPos(h, 1, x, y, 0, 0, 0x0001 | 0x0010)                  # HWND_BOTTOM, giữ kích thước, không lấy focus
        return x, y

    def on_screen(h):
        l, t, r, b = rect_of(h)
        return l >= 0 and t >= 0 and r <= U32.GetSystemMetrics(0) and b <= U32.GetSystemMetrics(1)

    def frame_bounds(h):          # vùng Windows Graphics Capture quay thật (không gồm bóng đổ)
        r = wt.RECT()
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0: return r.left, r.top, r.right, r.bottom
        return rect_of(h)

    def render_child(h):          # cửa sổ con LỚN NHẤT = phần màn hình Android (LDPlayer / MuMu / MEmu đều vậy)
        kids = []
        def cb(c, _):
            if U32.IsWindowVisible(c):
                l, t, r_, b_ = rect_of(c)
                if r_ - l > 50 and b_ - t > 50: kids.append(((r_ - l) * (b_ - t), (l, t, r_, b_)))
            return True
        U32.EnumChildWindows(h, EnumProc(cb), 0)
        return max(kids)[1] if kids else None


class WindowSource:
    """Giữ KHUNG MỚI NHẤT của phần màn hình Android trong cửa sổ giả lập."""
    def __init__(self, name):
        self.name, self.latest, self.n, self.size_change = name, None, 0, None
        self.cond = threading.Condition(); self.stopping = False; self.ctl = None; self.closed = False; self.gen = 0

    def open(self):
        """Tìm cửa sổ máy → quay. Không quay được ở chỗ đỗ hiện tại → thử lại với cửa sổ nằm HẲN trong màn hình (đánh dấu để
           phonectl không dời đi). Vẫn không được → CaptureBlocked (phiên chuyển sang lấy hình thẳng từ Android)."""
        import numpy as np  # noqa: F401  (windows_capture trả numpy)
        from windows_capture import WindowsCapture
        h, title = find_window(self.name)
        if not h: raise Deny("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
        if U32.IsIconic(h): U32.ShowWindow(h, 4); time.sleep(0.6)       # thu nhỏ thì Windows không vẽ → hiện lại (không cướp chuột)
        elif not U32.IsWindowVisible(h): U32.ShowWindow(h, 4); time.sleep(0.4)   # bị ẩn hẳn → Windows không cho quay → hiện lại
        l, t, r, b = rect_of(h)
        if l <= -30000 and t <= -30000:              # chỗ đỗ CŨ = toạ độ cửa sổ thu nhỏ → Windows không quay được → dời về chỗ đỗ mới
            x, y = park(h); time.sleep(0.3)
            log(f"  {self.name}: dời cửa sổ từ ({l},{t}) về chỗ đỗ mới ({x},{y}) — ở (-32000,-32000) Windows không quay được")
        try:
            return self._open_at(h, title, WindowsCapture)
        except CaptureBlocked:
            if self.stopping or on_screen(h): raise
        x, y = park(h, "screen"); U32.SetPropW(h, KEEP_PROP, 1); time.sleep(0.4)
        log(f"  {self.name}: thử lại với cửa sổ nằm hẳn trong màn hình ({x},{y})")
        try:
            wh = self._open_at(h, title, WindowsCapture)
        except CaptureBlocked:
            U32.RemovePropW(h, KEEP_PROP); park(h)   # trong màn hình cũng không quay được → trả về chỗ đỗ cho gọn
            raise
        log(f"  {self.name}: ✓ cửa sổ nằm hẳn trong màn hình thì quay được → giữ ở đó (muốn mọi máy đỗ như vậy: PARK=screen trong cloudphone.conf)")
        return wh

    def _halt(self):
        """Dừng phiên quay đang chạy (khung đến muộn của phiên cũ bị bỏ qua nhờ số thế hệ gen)."""
        self.gen += 1
        ctl, self.ctl = self.ctl, None
        try:
            if ctl is not None and hasattr(ctl, "stop"): ctl.stop()
        except Exception: pass

    def _open_at(self, h, title, WindowsCapture):
        self.latest = None; self.closed = False; self.size_change = None
        fb = frame_bounds(h); ch = render_child(h) or fb
        self.cx, self.cy = max(0, ch[0] - fb[0]), max(0, ch[1] - fb[1])
        self.cw, self.ch = (ch[2] - ch[0]) & ~1, (ch[3] - ch[1]) & ~1
        self.fw, self.fh = fb[2] - fb[0], fb[3] - fb[1]
        if self.cw < 64 or self.ch < 64: raise Deny("OFFLINE", "Cửa sổ máy đang lỗi kích thước — thử lại sau ít giây.")
        src = self; my = self.gen

        def make():
            # Quay theo SỐ CỬA SỔ (hwnd): tìm theo tên thì windows-capture bỏ qua cửa sổ "chạy ngầm" (tool window)
            try: cap = WindowsCapture(cursor_capture=None, draw_border=None, window_hwnd=int(h))
            except TypeError: cap = WindowsCapture(cursor_capture=None, draw_border=None, window_name=title)   # windows-capture bản cũ

            @cap.event
            def on_frame_arrived(frame, ictl):
                if src.stopping or src.gen != my:
                    try: ictl.stop()
                    except Exception: pass
                    return
                a = frame.frame_buffer                       # (cao, rộng, 4) BGRA
                if abs(a.shape[1] - src.fw) > 6 or abs(a.shape[0] - src.fh) > 6:
                    src.size_change = (a.shape[1], a.shape[0], time.time()); return
                src.size_change = None
                sub = a[src.cy:src.cy + src.ch, src.cx:src.cx + src.cw]
                if sub.shape[0] != src.ch or sub.shape[1] != src.cw: return
                buf = sub.copy()                             # thư viện dùng lại bộ nhớ khung → phải chép
                with src.cond:
                    src.latest = buf; src.n += 1; src.cond.notify_all()

            @cap.event
            def on_closed():
                if src.gen != my: return
                src.closed = True
                with src.cond: src.cond.notify_all()
            return cap

        # Windows CHỈ cho quay cửa sổ có trong Alt+Tab (CreateForWindow báo lỗi → "Failed to convert item to GraphicsCaptureItem").
        # Cửa sổ máy khách "chạy ngầm" (phonectl hide: kiểu tool window) → tạm thành cửa sổ thường lúc bắt đầu quay,
        # có hình rồi trả lại kiểu cũ (đổi kiểu SAU khi đã bắt đầu quay không làm dừng quay).
        ex0 = U32.GetWindowLongW(h, GWL_EXSTYLE)
        ex_cap = (ex0 | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        changed = False; errs = []
        try:
            if ex0 != ex_cap and ((ex0 & WS_EX_TOOLWINDOW) or U32.GetWindow(h, GW_OWNER)):
                U32.SetWindowLongW(h, GWL_EXSTYLE, ex_cap); changed = True
            for k in range(2):
                try:
                    self.ctl = make().start_free_threaded(); errs = []; break
                except Exception as e:
                    errs.append(str(e).replace("Capture session threw an exception: ", "")[:110])
                    if k or "GraphicsCaptureItem" not in str(e): break
                    # lần 2: ẩn → đổi kiểu → hiện lại không lấy focus (như phonectl hide) để Windows tính lại cửa sổ có trong Alt+Tab
                    U32.ShowWindow(h, 0); U32.SetWindowLongW(h, GWL_EXSTYLE, ex_cap); U32.ShowWindow(h, 4); changed = True; time.sleep(0.5)
            if not errs:
                t0 = time.time()
                with self.cond:
                    while self.latest is None and time.time() - t0 < 6 and not self.closed and not self.stopping:
                        self.cond.wait(0.2)
        finally:
            if changed: U32.SetWindowLongW(h, GWL_EXSTYLE, ex0)
        if errs:
            log(f"  {self.name}: Windows không cho quay cửa sổ ({' | '.join(errs)})")
            for x in [y for hs in _same_name(self.name) for y in hs][:4]: log(f"    · {win_info(x)}")
            raise CaptureBlocked("Windows không cho quay cửa sổ giả lập")
        if self.latest is None:
            gone, stopping = self.closed, self.stopping
            self._halt()
            if stopping: raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
            if gone: raise Deny("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
            log(f"  {self.name}: cửa sổ không ra khung hình nào sau 6 giây — {win_info(h)}")
            raise CaptureBlocked("cửa sổ giả lập không ra hình")
        # Phải RA HÌNH LIÊN TỤC: giả lập ở cửa sổ khuất / chạy ngầm có thể ngừng vẽ (MuMu: chỉ 1 khung đầu rồi 0 khung/giây)
        # → app thấy hình ĐỨNG. Giả lập đang vẽ thì vẽ đều mỗi khung dù màn hình Android đứng yên.
        n1, t1 = self.n, time.time()
        with self.cond:
            while self.n < n1 + 4 and time.time() - t1 < 2.5 and not self.closed and not self.stopping:
                self.cond.wait(0.2)
        if self.n < n1 + 4:
            k, gone, stopping = self.n - n1, self.closed, self.stopping
            self._halt()
            if stopping: raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
            if gone: raise Deny("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
            log(f"  {self.name}: cửa sổ chỉ ra {k} khung mới trong 2,5 giây (giả lập ngừng vẽ khi cửa sổ khuất?) — {win_info(h)}")
            raise CaptureBlocked("giả lập không vẽ hình liên tục ở cửa sổ này")
        return self.cw, self.ch

    def resized(self):
        s = self.size_change
        return bool(s and time.time() - s[2] < 2 and abs(s[0] - self.fw) + abs(s[1] - self.fh) > 6)

    def stop(self):
        self.stopping = True
        with self.cond: self.cond.notify_all()
        self._halt()


# ================================================================ Quay bằng PrintWindow (Windows 10 bản cũ, VD 1511)
# Windows Graphics Capture (thư viện windows-capture) chỉ có từ Windows 10 bản 1903. Bản cũ hơn → import báo
# "DLL load failed … specified procedure could not be found" → quay bằng PrintWindow(PW_RENDERFULLCONTENT) thay thế:
# chạy từ Windows 8.1, lấy được cả phần vẽ DirectX/OpenGL, cửa sổ đã đẩy ra ngoài màn hình vẫn quay được (chỉ không được thu nhỏ).
_WGC = {"ok": None, "why": ""}
def wgc_ok():
    """Dùng được Windows Graphics Capture? (thử import 1 lần rồi nhớ). Ép quay PrintWindow: CAPTURE=gdi trong cloudphone.conf."""
    if _WGC["ok"] is None:
        if (C.get("CAPTURE") or "").strip().lower() == "gdi": _WGC.update(ok=False, why="CAPTURE=gdi")
        else:
            try:
                import windows_capture  # noqa: F401
                _WGC["ok"] = True
            except Exception as e:
                _WGC.update(ok=False, why=repr(e)[:160])
        if not _WGC["ok"]: log(f"⚠ Windows này không dùng được Windows Graphics Capture ({_WGC['why']})")
    return _WGC["ok"]

if WIN:
    _G32 = ctypes.WinDLL("gdi32"); _U32 = ctypes.WinDLL("user32"); _HP = ctypes.c_void_p
    for _n, _r, _a in (("CreateCompatibleDC", _HP, [_HP]), ("DeleteDC", wt.BOOL, [_HP]), ("SelectObject", _HP, [_HP, _HP]), ("DeleteObject", wt.BOOL, [_HP])):
        _f = getattr(_G32, _n); _f.restype = _r; _f.argtypes = _a
    _G32.CreateDIBSection.restype = _HP
    _G32.CreateDIBSection.argtypes = [_HP, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), _HP, wt.DWORD]
    for _n, _r, _a in (("GetDC", _HP, [_HP]), ("ReleaseDC", ctypes.c_int, [_HP, _HP]), ("PrintWindow", wt.BOOL, [_HP, _HP, wt.UINT]),
                       ("IsWindow", wt.BOOL, [_HP]), ("IsIconic", wt.BOOL, [_HP])):
        _f = getattr(_U32, _n); _f.restype = _r; _f.argtypes = _a

    class _BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class GdiSource:
    """Giữ KHUNG MỚI NHẤT của phần màn hình Android trong cửa sổ giả lập — quay bằng PrintWindow (Windows 10 bản cũ)."""
    def __init__(self, name, fps=60):
        self.name, self.latest, self.n, self.size_change = name, None, 0, None
        self.cond = threading.Condition(); self.stopping = False; self.closed = False
        self.fps = max(10, min(int(fps or 60), 60)); self.h = None

    def open(self):
        import numpy as np
        self.np = np
        h, title = find_window(self.name)
        if not h: raise Deny("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
        if _U32.IsIconic(h): U32.ShowWindow(h, 4); time.sleep(0.6)       # thu nhỏ thì Windows không vẽ → hiện lại
        self.h = h
        wl, wtp, wr, wb = rect_of(h)                                       # PrintWindow vẽ cả cửa sổ, gốc = góc cửa sổ
        rc = render_child(h) or (wl, wtp, wr, wb)
        self.fw, self.fh = wr - wl, wb - wtp
        self.cx, self.cy = max(0, rc[0] - wl), max(0, rc[1] - wtp)
        self.cw = (min(rc[2], wr) - max(rc[0], wl)) & ~1
        self.ch = (min(rc[3], wb) - max(rc[1], wtp)) & ~1
        if self.cw < 64 or self.ch < 64: raise Deny("OFFLINE", "Cửa sổ máy đang lỗi kích thước — thử lại sau ít giây.")
        threading.Thread(target=self._run, daemon=True).start()
        t0 = time.time()
        with self.cond:
            while self.latest is None and time.time() - t0 < 6 and not self.closed and not self.stopping:
                self.cond.wait(0.2)
        if self.latest is None:
            self.stop(); raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
        return self.cw, self.ch

    def _alloc(self, w, h):
        bi = _BIH(); bi.biSize = ctypes.sizeof(_BIH); bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32
        sdc = _U32.GetDC(None)
        mdc = _G32.CreateCompatibleDC(sdc)
        _U32.ReleaseDC(None, sdc)
        bits = ctypes.c_void_p()
        bmp = _G32.CreateDIBSection(mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0) if mdc else None
        if not mdc or not bmp or not bits.value:
            if bmp: _G32.DeleteObject(bmp)
            if mdc: _G32.DeleteDC(mdc)
            raise OSError("không tạo được vùng nhớ hình (CreateDIBSection)")
        old = _G32.SelectObject(mdc, bmp)
        arr = self.np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_ubyte)), shape=(h, w, 4))   # BGRA, hàng trên cùng trước
        return mdc, bmp, old, arr

    def _free(self, g):
        if not g: return
        mdc, bmp, old, _ = g
        try: _G32.SelectObject(mdc, old)
        except Exception: pass
        try: _G32.DeleteObject(bmp); _G32.DeleteDC(mdc)
        except Exception: pass

    def _run(self):
        g = None; size = None; step = 1.0 / self.fps; dark_since = None; warned = False
        try:
            while not self.stopping:
                t0 = time.perf_counter()
                if not _U32.IsWindow(self.h): self.closed = True; break             # cửa sổ máy đã đóng (máy tắt / khởi động lại)
                l, t, r, b = rect_of(self.h); w, hh = r - l, b - t
                if w < 64 or hh < 64 or _U32.IsIconic(self.h): time.sleep(0.2); continue
                if abs(w - self.fw) > 6 or abs(hh - self.fh) > 6:                     # đổi cỡ (xoay máy…) → phiên bật lại bộ quay
                    self.size_change = (w, hh, time.time()); time.sleep(0.1); continue
                self.size_change = None
                if size != (w, hh):
                    self._free(g); g = None
                    g = self._alloc(w, hh); size = (w, hh)
                if _U32.PrintWindow(self.h, g[0], 2):                                 # 2 = PW_RENDERFULLCONTENT
                    sub = g[3][self.cy:self.cy + self.ch, self.cx:self.cx + self.cw]
                    if sub.shape[0] == self.ch and sub.shape[1] == self.cw:
                        buf = sub.copy()
                        if self.n % 30 == 0:                                          # hình đen mãi → ghi nhật ký 1 lần (để đổi chế độ vẽ)
                            if int(buf[::24, ::24, :3].max()) < 8:
                                dark_since = dark_since or time.time()
                                if not warned and time.time() - dark_since > 8:
                                    warned = True
                                    log(f"  ⚠ {self.name}: PrintWindow chỉ lấy được hình ĐEN — đổi chế độ vẽ của máy MEmu (DirectX ↔ OpenGL) rồi thử lại")
                            else: dark_since = None
                        with self.cond:
                            self.latest = buf; self.n += 1; self.cond.notify_all()
                d = step - (time.perf_counter() - t0)
                if d > 0: time.sleep(d)
        except Exception as e:
            if not self.stopping: log("  lỗi quay hình (PrintWindow):", repr(e)); self.closed = True
        finally:
            self._free(g)
            with self.cond: self.cond.notify_all()

    def resized(self):
        s = self.size_change
        return bool(s and time.time() - s[2] < 2 and abs(s[0] - self.fw) + abs(s[1] - self.fh) > 6)

    def stop(self):
        self.stopping = True
        with self.cond: self.cond.notify_all()


_VMODE = {"v": None}
def video_mode():
    """Cách lấy hình: wgc (Windows Graphics Capture, Windows 10 1903+) · scrcpy (lấy THẲNG từ Android) · gdi (PrintWindow) · fake (chạy thử).
       Mặc định: wgc nếu Windows có, không thì scrcpy (PrintWindow chỉ ra màn đen với MEmu). Ép: CAPTURE=scrcpy | gdi | wgc trong cloudphone.conf."""
    if _VMODE["v"] is None:
        c = (C.get("CAPTURE") or "").strip().lower()
        if SELFTEST or not WIN: v = "scrcpy" if c == "scrcpy" else "fake"
        elif c in ("scrcpy", "gdi"): v = c
        else: v = "wgc" if wgc_ok() else "scrcpy"
        _VMODE["v"] = v
        log("cách lấy hình: " + {"wgc": "quay cửa sổ giả lập (Windows Graphics Capture)", "scrcpy": "lấy thẳng từ Android (scrcpy-server mã hoá H.264 trong máy)",
                                  "gdi": "quay cửa sổ bằng PrintWindow", "fake": "hình giả (chạy thử)"}[v])
    return _VMODE["v"]


def make_source(name, fps=60):
    """Bộ quay hình cho 1 máy: Windows Graphics Capture (Windows 10 1903+) · PrintWindow (Windows cũ) · hình giả (chạy thử)."""
    if SELFTEST or not WIN: return FakeSource(name)
    return WindowSource(name) if wgc_ok() else GdiSource(name, fps)


class FakeSource:
    """Nguồn hình giả (chạy thử trên Linux / không có giả lập)."""
    def __init__(self, name, w=540, h=960):
        self.name, self.cw, self.ch, self.latest, self.n, self.closed = name, w, h, None, 0, False
        self.cond = threading.Condition(); self.stopping = False; self.size_change = None

    def open(self):
        import numpy as np
        self.np = np
        threading.Thread(target=self._run, daemon=True).start()
        with self.cond:
            while self.latest is None: self.cond.wait(0.1)
        return self.cw, self.ch

    def _run(self):
        np = self.np; t = 0
        base = np.zeros((self.ch, self.cw, 4), np.uint8)
        base[..., 0] = np.linspace(40, 200, self.cw, dtype=np.uint8)[None, :]
        base[..., 1] = np.linspace(30, 120, self.ch, dtype=np.uint8)[:, None]
        while not self.stopping:
            f = base.copy(); y = (t * 7) % (self.ch - 40)
            f[y:y + 40, :, :3] = 255
            with self.cond:
                self.latest = f; self.n += 1; self.cond.notify_all()
            t += 1; time.sleep(1 / 60)

    def resized(self): return False
    def stop(self): self.stopping = True


# ================================================================ Nén hình: FFmpeg → RTP nội bộ → khung H.264
class _NvencSlots:
    def __init__(self): self.n = 0; self.lock = threading.Lock()
    def take(self):
        with self.lock:
            if self.n >= NVENC_MAX: return False
            self.n += 1; return True
    def give(self):
        with self.lock: self.n = max(0, self.n - 1)


NVENC = _NvencSlots()
_nvenc_broken = {"until": 0}


class Encoder:
    """Mỗi phiên xem 1 bộ nén. Trả từng KHUNG (access unit) qua on_au(bytes|None, key, cfg, pts_us) — None = mất khung (chờ khung khoá)."""
    def __init__(self, src, out_w, out_h, fps, kbps, on_au, cpu=False):
        self.src, self.ow, self.oh, self.fps, self.kbps, self.on_au = src, out_w, out_h, fps, kbps, on_au
        self.cpu = cpu or ALWAYS_CPU or time.time() < _nvenc_broken["until"]
        self.proc = None; self.sock = None; self.alive = False; self.slot = False; self.stopped = False
        self.lock = threading.Lock()
        self.enc = "x264" if self.cpu else "nvenc"; self.frames_in = 0; self.started = 0.0

    def _cmd(self, rtp_port):
        sw, sh, fps, k = self.src.cw, self.src.ch, self.fps, self.kbps
        cmd = [FF, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{sw}x{sh}", "-framerate", str(fps), "-i", "-"]
        vf = []
        if (self.ow, self.oh) != (sw, sh): vf.append(f"scale={self.ow}:{self.oh}:flags=fast_bilinear")
        gop = str(max(fps, 15))                                 # khung khoá mỗi ~1 giây: mạng chập chờn → hình hồi lại ≤ 1 giây
        buf = f"{max(k * 6 // max(fps, 1), 250)}k"               # bộ đệm ~6 khung (~0,1 s) — nhỏ = ít trễ
        if self.enc == "nvenc":
            if vf: cmd += ["-vf", ",".join(vf)]
            cmd += ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ull", "-zerolatency", "1", "-delay", "0", "-rc", "cbr",
                    "-profile:v", "baseline", "-bf", "0", "-g", gop, "-forced-idr", "1", "-strict_gop", "1",
                    "-b:v", f"{k}k", "-maxrate", f"{k}k", "-bufsize", buf]
        else:
            vf.append("format=yuv420p")
            cmd += ["-vf", ",".join(vf), "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-profile:v", "baseline",
                    "-threads", "1", "-x264-params", f"sliced-threads=0:keyint={gop}:min-keyint={gop}:scenecut=0:bframes=0:rc-lookahead=0:sync-lookahead=0:repeat-headers=1",
                    "-b:v", f"{k}k", "-maxrate", f"{k}k", "-bufsize", buf]
        cmd += ["-an", "-bsf:v", "dump_extra=freq=keyframe", "-f", "rtp", "-rtpflags", "skip_rtcp", "-payload_type", "96",
                f"rtp://127.0.0.1:{rtp_port}?pkt_size=1300"]
        return cmd

    def start(self):
        with self.lock:
            if self.stopped: return
            if self.enc == "nvenc":
                if not NVENC.take(): self.enc = "x264"
                else: self.slot = True
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try: self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            except OSError: pass
            self.sock.bind(("127.0.0.1", 0)); self.sock.settimeout(0.5)
            port = self.sock.getsockname()[1]
            self.proc = subprocess.Popen(self._cmd(port), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                         creationflags=NOWIN, bufsize=0)
            self.alive = True; self.started = time.time()
        threading.Thread(target=self._feed, daemon=True).start()
        threading.Thread(target=self._rtp, daemon=True).start()
        threading.Thread(target=self._errlog, daemon=True).start()

    def _errlog(self):
        p = self.proc; lines = []
        try:
            for ln in iter(p.stderr.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s: lines.append(s)
        except Exception: pass
        if not self.stopped and lines: log(f"  [ffmpeg {self.enc}] " + " | ".join(lines[-3:])[:300])

    def _feed(self):
        """Gửi đều đặn KHUNG MỚI NHẤT vào bộ nén (không xếp hàng khung cũ → không trễ dồn)."""
        step = 1.0 / self.fps; nxt = time.perf_counter(); last_n = -1; src = self.src; p = self.proc
        try:
            while self.alive and p.poll() is None:
                with src.cond:
                    if src.n == last_n and not src.stopping: src.cond.wait(step)
                    buf, last_n = src.latest, src.n
                if buf is None or src.stopping: 
                    if src.stopping: break
                    continue
                mv = memoryview(buf).cast("B")
                while mv:
                    n = p.stdin.write(mv)
                    if not n: raise BrokenPipeError
                    mv = mv[n:]
                self.frames_in += 1
                nxt += step; d = nxt - time.perf_counter()
                if d > 0: time.sleep(d)
                elif d < -0.25: nxt = time.perf_counter()
        except (BrokenPipeError, OSError, ValueError, AttributeError):
            pass

    def _rtp(self):
        """Ghép gói RTP (RFC 6184) thành từng khung H.264 Annex-B. Bit marker = hết khung → gửi NGAY (không chờ khung sau)."""
        SC = b"\x00\x00\x00\x01"; au = []; key = cfg = False; bad = False; last_seq = None; fu = None; sock = self.sock
        while self.alive:
            try: pkt, _ = sock.recvfrom(65536)
            except socket.timeout:
                if self.proc and self.proc.poll() is not None: break
                continue
            except OSError: break
            if len(pkt) < 13 or (pkt[0] >> 6) != 2: continue
            cc = pkt[0] & 0x0F; ext = pkt[0] & 0x10; pad = pkt[0] & 0x20
            marker = pkt[1] & 0x80; seq = (pkt[2] << 8) | pkt[3]
            off = 12 + 4 * cc
            if ext and len(pkt) >= off + 4: off += 4 + 4 * struct.unpack(">H", pkt[off + 2:off + 4])[0]
            end = len(pkt) - (pkt[-1] if pad else 0)
            pl = pkt[off:end]
            if last_seq is not None and seq != (last_seq + 1) & 0xFFFF: bad = True       # mất gói (hiếm, nội bộ) → bỏ khung, chờ khung khoá
            last_seq = seq
            if not pl: continue
            t = pl[0] & 0x1F
            if 1 <= t <= 23:
                au.append(SC + pl)
                if t == 5: key = True
                elif t in (7, 8): cfg = True
            elif t == 24:                                   # STAP-A
                i = 1
                while i + 2 <= len(pl):
                    n = (pl[i] << 8) | pl[i + 1]; i += 2
                    nal = pl[i:i + n]; i += n
                    if nal:
                        au.append(SC + nal); nt = nal[0] & 0x1F
                        if nt == 5: key = True
                        elif nt in (7, 8): cfg = True
            elif t == 28 and len(pl) >= 2:                  # FU-A
                s, e, nt = pl[1] & 0x80, pl[1] & 0x40, pl[1] & 0x1F
                if s: fu = bytearray(SC + bytes([(pl[0] & 0xE0) | nt])) + pl[2:]
                elif fu is not None: fu += pl[2:]
                else: bad = True
                if e and fu is not None:
                    au.append(bytes(fu)); fu = None
                    if nt == 5: key = True
            if marker:
                if au and not bad: self.on_au(b"".join(au), key, cfg, int(time.monotonic() * 1e6))
                elif bad: self.on_au(None, False, False, 0)
                au = []; key = cfg = bad = False; fu = None

    def stop(self):
        """Tắt hẳn (an toàn khi gọi nhiều lần / gọi trước khi start chạy xong)."""
        with self.lock:
            self.stopped = True; self.alive = False
            p, s = self.proc, self.sock
        try:
            if p and p.poll() is None: p.kill()                 # tắt TRƯỚC rồi mới đóng ống (Windows: đóng ống đang ghi dở sẽ bị chờ)
        except Exception: pass
        try:
            if p and p.stdin: p.stdin.close()
        except Exception: pass
        try:
            if s: s.close()
        except Exception: pass
        with self.lock:
            if self.slot: NVENC.give(); self.slot = False

    def failed_early(self):
        return self.proc is not None and self.proc.poll() is not None and time.time() - self.started < 6 and not self.stopped


# ================================================================ Điều khiển: scrcpy-server 2.4 (chỉ điều khiển)
def adb(serial, *args, timeout=20):
    try:
        r = subprocess.run([ADB, "-s", serial, *args], capture_output=True, timeout=timeout, creationflags=NOWIN)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace"), (r.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "no adb"


def ensure_jar():
    if os.path.isfile(JAR) and os.path.getsize(JAR) > 50000: return True
    try:
        log("tải scrcpy-server 2.4 (điều khiển chạm)…")
        req = urllib.request.Request(JAR_URL, headers={"User-Agent": "BlueRoblox"})
        data = urllib.request.urlopen(req, timeout=120).read()
        if len(data) < 50000: return False
        open(JAR + ".tmp", "wb").write(data); os.replace(JAR + ".tmp", JAR); return True
    except Exception as e:
        log("không tải được scrcpy-server:", e); return False


_devsize = {}
_devsize_warned = set()


def device_size(serial):
    """Kích thước màn hình Android theo hướng TỰ NHIÊN (wm size)."""
    c = _devsize.get(serial)
    if c and c[1] > time.time(): return c[0]
    code, out, _ = adb(serial, "shell", "wm", "size", timeout=10)
    size = None
    for pat in (r"Override size:\s*(\d+)x(\d+)", r"Physical size:\s*(\d+)x(\d+)"):      # cỡ 0x0 (MEmu Android 12 có lúc báo vậy) → bỏ qua
        m = re.search(pat, out)
        if m and int(m.group(1)) > 0 and int(m.group(2)) > 0: size = (int(m.group(1)), int(m.group(2))); break
    if size: _devsize[serial] = (size, time.time() + 600)
    elif serial not in _devsize_warned:
        _devsize_warned.add(serial); log(f"  [{serial}] wm size không dùng được: {' '.join(out.split())[:120] or '(trống)'}")
    return size


def adb_connect(serial):
    """Nối adb tới máy (giả lập mở adb TCP 127.0.0.1:cổng). Chưa nối thì adb báo "device … not found"."""
    if ":" not in serial: return
    try: subprocess.run([ADB, "connect", serial], capture_output=True, timeout=8, creationflags=NOWIN)
    except Exception: pass


_ADB_GONE = ("offline", "not found", "no devices", "unauthorized", "connection reset", "closed", "protocol fault")


def adb_ready(serial, wait=12.0):
    """Chờ adb thấy máy ở trạng thái "device". Máy vừa khởi động lại giao diện (cài app sẵn, đổi ảnh nền…) hoặc adb vừa nối lại
       → "offline" / "not found" vài giây: lệnh adb chạy lúc đó hỏng (push lỗi → chạm rơi xuống lệnh input chậm, hoặc mất hẳn).
       Quá nửa thời gian vẫn chưa được → ngắt + nối lại 1 lần (adb TCP hay kẹt "offline"). True = sẵn sàng."""
    if SELFTEST: return True
    t0 = time.time(); kicked = False
    while True:
        adb_connect(serial)
        code, out, _ = adb(serial, "get-state", timeout=5)
        if code == 0 and out.strip() == "device": return True
        if time.time() - t0 >= wait: return False
        if not kicked and ":" in serial and time.time() - t0 > wait / 2:
            kicked = True
            try: subprocess.run([ADB, "disconnect", serial], capture_output=True, timeout=8, creationflags=NOWIN)
            except Exception: pass
        time.sleep(0.6)


def push_jar(serial):
    """Chép scrcpy-server vào máy (đã có đúng bản thì thôi). Máy đang "offline" → chờ adb sẵn sàng rồi thử lại 1 lần."""
    for i in range(2):
        code, out, err = adb(serial, "shell", "ls", "-l", JAR_DEV, timeout=10)
        if code == 0 and str(os.path.getsize(JAR)) in out: return
        if code == 0 or not any(w in (err or out).lower() for w in _ADB_GONE):
            code, out, err = adb(serial, "push", JAR, JAR_DEV, timeout=60)
            if code == 0: return
        if i == 0 and any(w in (err or out).lower() for w in _ADB_GONE) and adb_ready(serial, 12): continue
        raise RuntimeError("push: " + (err or out).strip()[-200:])


def _recv_exact(s, n):
    b = bytearray()
    while len(b) < n:
        x = s.recv(n - len(b))
        if not x: raise EOFError
        b += x
    return bytes(b)


class _Bits:
    def __init__(self, b): self.b, self.i = b, 0
    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.i >> 3] >> (7 - (self.i & 7))) & 1); self.i += 1
        return v
    def ue(self):
        z = 0
        while self.u(1) == 0:
            z += 1
            if z > 31: raise ValueError("ue")
        return (1 << z) - 1 + (self.u(z) if z else 0)
    def se(self):
        k = self.ue(); return (k + 1) // 2 if k & 1 else -(k // 2)


def _sps_dims(cfg):
    """(rộng, cao) của hình đọc từ SPS H.264 trong gói cấu hình Annex-B. Không đọc được → None."""
    try:
        sps = next((n.rstrip(b"\x00") for n in re.split(b"\x00\x00\x01", cfg) if n and (n[0] & 0x1F) == 7), None)
        if not sps: return None
        rb = bytearray(); z = 0
        for x in sps[1:]:                                    # bỏ byte chống giả mã bắt đầu (00 00 03)
            if z >= 2 and x == 3: z = 0; continue
            rb.append(x); z = z + 1 if x == 0 else 0
        r = _Bits(bytes(rb)); prof = r.u(8); r.u(16); r.ue(); cf = 1
        if prof in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
            cf = r.ue()
            if cf == 3: r.u(1)
            r.ue(); r.ue(); r.u(1)
            if r.u(1):
                for k in range(8 if cf != 3 else 12):
                    if r.u(1):
                        last = nxt = 8
                        for _ in range(16 if k < 6 else 64):
                            if nxt: nxt = (last + r.se() + 256) % 256
                            last = nxt or last
        r.ue(); t = r.ue()
        if t == 0: r.ue()
        elif t == 1:
            r.u(1); r.se(); r.se()
            for _ in range(r.ue()): r.se()
        r.ue(); r.u(1)
        wm, hm = r.ue() + 1, r.ue() + 1; fmo = r.u(1)
        if not fmo: r.u(1)
        r.u(1)
        w, h = wm * 16, (2 - fmo) * hm * 16
        if r.u(1):
            cl, cr, ct, cb = r.ue(), r.ue(), r.ue(), r.ue()
            cx = 1 if cf in (0, 3) else 2; cy = (2 if cf == 1 else 1) * (2 - fmo)
            w -= (cl + cr) * cx; h -= (ct + cb) * cy
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


class ScrcpySource:
    """Nguồn hình "ảo" khi lấy hình thẳng từ Android: không quay cửa sổ, chỉ giữ kích thước màn hình máy (wm size → độ phân giải đã mua)."""
    def __init__(self, serial, res=None):
        self.serial = serial; self.res = res; self.cw = self.ch = 0; self.closed = False; self.stopping = False

    def open(self):
        adb_connect(self.serial)
        sz = device_size(self.serial)
        if not sz:
            time.sleep(1); adb_connect(self.serial); sz = device_size(self.serial)
        if not sz:
            m = re.match(r"^\s*(\d{3,4})\s*x\s*(\d{3,4})\s*$", str(self.res or ""))
            sz = (int(m.group(1)), int(m.group(2))) if m else None
        self.cw, self.ch = sz or (720, 1280)
        return self.cw, self.ch

    def resized(self): return False
    def stop(self): self.stopping = True


class ScrcpyVideo:
    """Hình lấy THẲNG từ Android: scrcpy-server 2.4 (video=true, control=false) mã hoá H.264 ngay trong máy → từng khung Annex-B → on_au.
       Dùng khi Windows không quay được cửa sổ giả lập (Windows 10 trước 1903: PrintWindow chỉ ra màn ĐEN với MEmu).
       Cùng giao diện với Encoder (start / stop / proc / enc / failed_early). Khung khoá mỗi ~1 giây; máy xoay → on_size(rộng, cao)."""
    def __init__(self, serial, max_size, fps, kbps, on_au, on_size=None):
        self.serial, self.max_size, self.fps, self.kbps, self.on_au, self.on_size = serial, int(max_size), int(fps), int(kbps), on_au, on_size
        self.enc = "scrcpy"; self.proc = None; self.sock = None; self.fport = None; self.stopped = False
        self.lock = threading.Lock(); self.w = self.h = 0; self.frames_in = 0; self.started = 0.0

    def start(self):
        """Bật scrcpy-server + nối socket hình → (rộng, cao) THẬT của hình. Lỗi → RuntimeError."""
        self.started = time.time()
        adb_ready(self.serial, 12)
        if not ensure_jar(): raise RuntimeError("thiếu scrcpy-server")
        push_jar(self.serial)
        scid = random.randint(1, 0x7FFFFFFF)
        cmd = (f"CLASSPATH={JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 scid={scid:08x} log_level=warn "
               "video=true audio=false control=false tunnel_forward=true send_device_meta=false send_dummy_byte=true "
               "send_codec_meta=true send_frame_meta=true cleanup=false power_on=false video_codec=h264 "
               f"max_size={self.max_size} max_fps={self.fps} video_bit_rate={self.kbps * 1000} video_codec_options=i-frame-interval=1")
        with self.lock:
            if self.stopped: raise RuntimeError("đã dừng")
            self.proc = subprocess.Popen([ADB, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=NOWIN)
        threading.Thread(target=self._srvlog, args=(self.proc,), daemon=True).start()
        code, out, err = adb(self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid:08x}", timeout=10)
        with self.lock: self.fport = int(out.strip()) if out.strip().isdigit() else None
        if not self.fport: self._kill(); raise RuntimeError("forward: " + (err or out)[-200:])
        t0 = time.time(); sock = None
        while time.time() - t0 < 10 and not self.stopped:
            if self.proc.poll() is not None: break               # máy chủ scrcpy thoát ngay (VD máy không có bộ mã hoá) → xem nhật ký [scrcpy …]
            try:
                s = socket.create_connection(("127.0.0.1", self.fport), timeout=2); s.settimeout(3)
                if s.recv(1) == b"\x00": sock = s; break
                s.close()
            except OSError: pass
            time.sleep(0.15)
        if not sock: self._kill(); raise RuntimeError("scrcpy (hình) không nối được")
        return self.attach(sock)

    def attach(self, sock):
        """Đọc thông tin hình (mã H.264 + rộng × cao) rồi chạy luồng đọc khung → (rộng, cao)."""
        try:
            sock.settimeout(10)
            codec, w, h = struct.unpack(">III", _recv_exact(sock, 12))
            if codec != 0x68323634: raise RuntimeError(f"scrcpy gửi mã hình lạ {codec:#x}")
            sock.settimeout(None)
            try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError: pass
        except Exception:
            try: sock.close()
            except Exception: pass
            self._kill(); raise
        with self.lock: self.sock = sock; self.w, self.h = w, h
        threading.Thread(target=self._reader, args=(sock,), daemon=True).start()
        return w, h

    def _srvlog(self, p):
        try:
            for ln in iter(p.stdout.readline, b""):
                t = ln.decode("utf-8", "replace").strip()
                if t and not self.stopped: log(f"  [scrcpy hình {self.serial}] {t[:200]}")
        except Exception: pass

    def _reader(self, s):
        cfg = b""
        try:
            while not self.stopped:
                pf, n = struct.unpack(">QI", _recv_exact(s, 12))
                data = _recv_exact(s, n)
                if pf & (1 << 63):                                   # gói cấu hình (SPS/PPS) → ghép trước mỗi khung khoá
                    cfg = data
                    d = _sps_dims(cfg)
                    if d and d != (self.w, self.h):                  # máy xoay / đổi cỡ → báo app cỡ mới TRƯỚC khung khoá mới
                        self.w, self.h = d
                        if self.on_size: self.on_size(*d)
                    continue
                key = bool(pf & (1 << 62)); self.frames_in += 1
                self.on_au(cfg + data if key and cfg else data, key, key and bool(cfg), int(time.monotonic() * 1e6))
        except Exception:
            pass
        if not self.stopped:
            log(f"  [hình {self.serial}] scrcpy ngừng gửi hình → bật lại")
            self._kill()                                             # tiến trình dừng → phiên xem tự bật lại hình

    def _kill(self):
        with self.lock:
            s, p, fp = self.sock, self.proc, self.fport
            self.sock = None; self.fport = None
        try:
            if s: s.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        try:
            if s: s.close()
        except Exception: pass
        try:
            if p and p.poll() is None: p.kill()
        except Exception: pass
        if fp: threading.Thread(target=adb, args=(self.serial, "forward", "--remove", f"tcp:{fp}"), daemon=True).start()

    def stop(self):
        with self.lock: self.stopped = True
        self._kill()

    def failed_early(self): return False


class Control:
    """Chạm / phím / chữ → máy Android qua scrcpy-server 2.4 (chỉ điều khiển). Mọi lệnh đi qua 1 hàng đợi + 1 luồng gửi
       (không bao giờ chặn vòng chính), giữ đúng thứ tự; chữ có dấu dán qua bộ nhớ copy và chờ máy dán xong rồi mới gửi tiếp."""
    def __init__(self, serial, on_clip):
        self.serial, self.on_clip = serial, on_clip
        self.sock = None; self.proc = None; self.fport = None; self.ready = threading.Event(); self.dead = False
        self.q = queue.Queue(maxsize=4000); self.lock = threading.Lock()
        self.nat = None; self.vw = self.vh = 0; self.mode = "scrcpy"; self.down = {}
        self.seq = 1; self.retrying = False; self.nat_t = 0.0

    # ---------- khởi động (luồng nền) ----------
    def start(self):
        threading.Thread(target=self._writer, daemon=True).start()
        if SELFTEST:
            self.mode = "none"; self.ready.set(); return
        try:
            adb_ready(self.serial, 12)                      # máy vừa "offline" (đang cài app sẵn / adb vừa nối lại) → chờ, đừng hỏng ngay
            self.nat = device_size(self.serial); self.nat_t = time.time()
            if self.dead: return self._cleanup()
            self._open_scrcpy()
            self.mode = "scrcpy"; self.ready.set()
        except Exception as e:
            if self.dead: return self._cleanup()
            log(f"  [điều khiển {self.serial}] scrcpy lỗi ({str(e).strip()[:160]}) → tạm dùng lệnh input, đang nối lại scrcpy…")
            self._cleanup(keep_queue=True); self.mode = "input"; self.ready.set()
            self._kick_retry()

    def _open_scrcpy(self):
        """Bật scrcpy-server 2.4 (chỉ điều khiển) trong máy + nối socket điều khiển. Lỗi → RuntimeError (phần dở dang: _cleanup)."""
        if not ensure_jar(): raise RuntimeError("thiếu scrcpy-server")
        push_jar(self.serial)
        if self.dead: raise RuntimeError("đã dừng")
        if True:
            scid = random.randint(1, 0x7FFFFFFF)
            cmd = (f"CLASSPATH={JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 scid={scid:08x} log_level=warn "
                   "video=false audio=false control=true tunnel_forward=true send_device_meta=false cleanup=false "
                   "clipboard_autosync=true power_on=false")
            with self.lock:
                if self.dead: raise RuntimeError("đã dừng")
                self.proc = subprocess.Popen([ADB, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
            threading.Thread(target=self._srvlog, args=(self.proc,), daemon=True).start()
            code, out, err = adb(self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid:08x}", timeout=10)
            with self.lock: self.fport = int(out.strip()) if out.strip().isdigit() else None
            if self.dead: raise RuntimeError("đã dừng")
            if not self.fport: raise RuntimeError("forward: " + (err or out)[-200:])
            t0 = time.time(); sock = None
            while time.time() - t0 < 8 and not self.dead:
                try:
                    s = socket.create_connection(("127.0.0.1", self.fport), timeout=2)
                    s.settimeout(3)
                    if s.recv(1) == b"\x00":
                        s.settimeout(3); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # gửi treo > 3 s → coi như hỏng
                        sock = s; break
                    s.close()
                except OSError:
                    pass
                time.sleep(0.15)
            if self.dead:
                if sock: sock.close()
                raise RuntimeError("đã dừng")
            if not sock: raise RuntimeError("scrcpy không nối được")
            with self.lock: self.sock = sock
            threading.Thread(target=self._reader, args=(sock,), daemon=True).start()

    def _kick_retry(self):
        """Đang chạm bằng lệnh input (chậm, adb hỏng là mất chạm) → luồng nền thử nối lại scrcpy cho tới khi được."""
        with self.lock:
            if self.retrying or self.dead: return
            self.retrying = True
        threading.Thread(target=self._retry_loop, daemon=True).start()

    def _retry_loop(self):
        delay = 2.0
        try:
            while not self.dead and self.mode == "input":
                time.sleep(delay); delay = min(delay * 2, 20.0)
                if self.dead: break
                try:
                    if not adb_ready(self.serial, 10): continue
                    if not self.nat: self.nat = device_size(self.serial); self.nat_t = time.time()
                    self._open_scrcpy()
                    if self.dead: break
                    self.mode = "scrcpy"; self.down.clear()
                    log(f"  [điều khiển {self.serial}] đã nối lại scrcpy → chạm nhanh trở lại")
                    return
                except Exception:
                    self._cleanup(keep_queue=True)
        finally:
            with self.lock: self.retrying = False
            if self.dead: self._cleanup()

    def _srvlog(self, p):
        try:
            for ln in iter(p.stdout.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s and not self.dead: log(f"  [scrcpy {self.serial}] {s[:200]}")
        except Exception: pass

    def _reader(self, s):
        def rd(n):
            b = b""
            while len(b) < n:
                try: x = s.recv(n - len(b))
                except socket.timeout: continue
                if not x: raise EOFError
                b += x
            return b
        try:
            while not self.dead:
                t = rd(1)[0]
                if t == 0:                       # máy vừa copy chữ → gửi về app
                    n = struct.unpack(">I", rd(4))[0]; txt = rd(n).decode("utf-8", "replace")
                    try: self.on_clip(txt)
                    except Exception: pass
                elif t == 1: rd(8)               # xác nhận đã đặt bộ nhớ copy
                elif t == 2:                     # uhid output
                    rd(2); n = struct.unpack(">H", rd(2))[0]; rd(n)
                else: break
        except Exception:
            pass

    def _cleanup(self, keep_queue=False):
        """Dọn scrcpy-server + adb forward + socket ĐANG có (gọi nhiều lần không sao)."""
        with self.lock:
            s, p, fp = self.sock, self.proc, self.fport
            self.sock = None; self.proc = None; self.fport = None
        try:
            if s: s.close()
        except Exception: pass
        try:
            if p and p.poll() is None: p.kill()
        except Exception: pass
        if fp: threading.Thread(target=adb, args=(self.serial, "forward", "--remove", f"tcp:{fp}"), daemon=True).start()

    def stop(self):
        self.dead = True; self.ready.set()
        try: self.q.put_nowait(None)
        except queue.Full: pass
        self._cleanup()

    # ---------- luồng gửi ----------
    def _writer(self):
        carry = None
        while not self.dead:
            it = carry if carry is not None else self.q.get()
            carry = None
            if it is None or self.dead: break
            self.ready.wait()
            if self.dead: break
            kind, val = it
            if kind == "paste":                              # gom chữ gõ liên tiếp trong 40 ms → 1 lần dán
                text = val; t_end = time.time() + 0.04
                while True:
                    try: nx = self.q.get(timeout=max(0.0, t_end - time.time()))
                    except queue.Empty: break
                    if nx is not None and nx[0] == "paste": text += nx[1]; continue
                    carry = nx; break
                b = text.encode("utf-8")[:200000]; self.seq += 1
                self._raw(struct.pack(">BqBI", 9, self.seq, 1, len(b)) + b)
                time.sleep(0.15)                             # chờ app trong máy dán xong (dán là bất đồng bộ) rồi mới gửi lệnh sau
            elif kind == "raw":
                self._raw(val)
            elif kind == "shell":
                cmd, t0 = val if isinstance(val, tuple) else (val, 0.0)
                if t0 and cmd.startswith("input ") and time.time() - t0 > 4: continue      # chạm đã cũ (adb kẹt) → bỏ, khỏi bấm nhầm muộn
                adb(self.serial, "shell", cmd, timeout=8 if cmd.startswith("input ") else 15)

    def _raw(self, b):
        s = self.sock
        if not s or self.mode != "scrcpy": return
        try: s.sendall(b)
        except OSError:
            log(f"  [điều khiển {self.serial}] mất kết nối scrcpy → tạm dùng lệnh input, đang nối lại scrcpy…")
            self._cleanup(keep_queue=True); self.mode = "input"; self._kick_retry()

    def _put(self, kind, val):
        try: self.q.put_nowait((kind, val))
        except queue.Full: pass

    def _send(self, b):
        if self.mode in ("scrcpy",) or not self.ready.is_set(): self._put("raw", b)

    def _shell(self, c): self._put("shell", (c, time.time()))

    # ---------- toạ độ ----------
    def set_view(self, vw, vh):
        self.vw, self.vh = vw, vh

    def screen(self):
        """Kích thước màn hình máy theo hướng HIỆN TẠI (đoán hướng theo tỉ lệ hình đang quay) — scrcpy đòi đúng số này."""
        vw, vh = self.vw or 720, self.vh or 1280
        if not self.nat and time.time() - self.nat_t > 3 and not SELFTEST:
            self.nat_t = time.time(); self.nat = device_size(self.serial)
        w, h = self.nat if self.nat and min(self.nat) > 0 else (vw, vh)
        if (vw > vh) != (w > h): w, h = h, w
        return w & ~7, h & ~7

    def _xy(self, nx, ny):
        w, h = self.screen()
        return min(w - 1, max(0, int(nx * w / 65536))), min(h - 1, max(0, int(ny * h / 65536))), w, h

    # ---------- lệnh ----------
    def touch(self, action, pointer, nx, ny):
        x, y, w, h = self._xy(nx, ny)
        if action == 3: action = 1
        if self.mode == "input":
            if action == 0: self.down[pointer] = (x, y, time.time())
            elif action == 1 and pointer in self.down:
                x0, y0, t0 = self.down.pop(pointer)
                dur = int((time.time() - t0) * 1000)
                if abs(x - x0) + abs(y - y0) < 12 and dur < 400: self._shell(f"input tap {x} {y}")
                else: self._shell(f"input swipe {x0} {y0} {x} {y} {max(80, min(dur, 1500))}")
            return
        pressure = 0 if action == 1 else 0xFFFF
        self._send(struct.pack(">BBqiiHHHii", 2, action, pointer, x, y, w, h, pressure, 0, 0))

    def scroll(self, nx, ny, hv, vv):
        x, y, w, h = self._xy(nx, ny)
        f = lambda v: max(-0x8000, min(0x7FFF, int(max(-1.0, min(1.0, v / 120.0)) * 0x8000)))
        if self.mode == "input":
            if vv: self._shell(f"input swipe {x} {y} {x} {max(0, min(h - 1, y + (300 if vv > 0 else -300)))} 120")
            return
        self._send(struct.pack(">BiiHHhhi", 3, x, y, w, h, f(hv), f(vv), 0))

    def key(self, action, code, meta=0):
        if self.mode == "input":
            if action == 0: self._shell(f"input keyevent {int(code)}")
            return
        self._send(struct.pack(">BBiii", 0, action, int(code), 0, int(meta)))

    def press(self, code):
        if self.mode == "input": self._shell(f"input keyevent {int(code)}"); return
        self.key(0, code); self.key(1, code)

    def text(self, s):
        if not s: return
        if self.mode != "input" and any(ord(ch) > 126 or (ord(ch) < 32 and ch not in "\n\t") for ch in s):
            self._put("paste", s); return                   # chữ có dấu (tiếng Việt…): scrcpy không gõ được → dán qua bộ nhớ copy
        if self.mode == "input":
            safe = re.sub(r"([\\\"'`$&|;<>()* ])", r"\\\1", s.replace("%", "\\%")).replace(" ", "%s")
            self._shell(f"input text {safe}"); return
        b = s.encode("utf-8")
        while b:
            cut = min(len(b), 300)
            part, b = b[:cut], b[cut:]
            self._send(struct.pack(">BI", 1, len(part)) + part)

    def clip_set(self, s, paste):
        if self.mode == "input": self.text(s); return
        if paste: self._put("paste", s); return
        b = s.encode("utf-8")[:200000]; self.seq += 1
        self._send(struct.pack(">BqBI", 9, self.seq, 0, len(b)) + b)

    def rotate(self, to=None):
        """Xoay màn máy: to = "land" (ngang) | "port" (dọc); không ghi → đổi sang hướng kia của hình đang phát.
           Khoá hướng bằng cài đặt Android (tắt tự xoay + user_rotation). Lệnh xoay của scrcpy chỉ đổi rồi TRẢ LẠI hướng cũ
           khi máy đang bật tự xoay → khách bấm "Xoay" mà máy đứng im."""
        if to not in ("land", "port"): to = "port" if (self.vw or 0) > (self.vh or 0) else "land"
        r = 1 if to == "land" else 0
        self._shell(f"settings put system accelerometer_rotation 0; settings put system user_rotation {r}; wm user-rotation lock {r} >/dev/null 2>&1")

    def notif(self):
        if self.mode != "input": self._send(bytes([5]))
        else: self._shell("cmd statusbar expand-notifications")


# ================================================================ Đường truyền: TLS trực tiếp / WebSocket
def _small_buffers(writer):
    """Bộ đệm gửi NHỎ: mạng khách chậm → lộ ra ngay ở máy chủ để BỎ KHUNG, thay vì dồn hàng giây hình cũ trong bộ đệm (trễ dần)."""
    try: writer.transport.set_write_buffer_limits(high=64 * 1024, low=16 * 1024)
    except Exception: pass
    try:
        s = writer.get_extra_info("socket")
        if s is not None:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 128 * 1024)
    except Exception: pass


class Link:
    kind = "?"
    closed = False
    async def recv(self): raise NotImplementedError
    def write(self, t, payload=b""): raise NotImplementedError

    async def send(self, t, payload=b"", timeout=5.0):
        """Gửi + chờ mạng nhận bớt (tối đa `timeout` giây — app treo/không đọc → báo lỗi để đóng phiên)."""
        self.write(t, payload)
        await asyncio.wait_for(self.w.drain(), timeout)

    def send_nowait(self, t, payload=b""):
        """Gói nhỏ (PONG, STATS, chữ copy…): ghi luôn, KHÔNG chờ — không để hình đang nghẽn làm chậm lệnh khác."""
        if self.closed: return
        try: self.write(t, payload)
        except Exception: pass

    async def close(self):
        if self.closed: return
        self.closed = True
        try: self.w.close()
        except Exception: pass


class DirectLink(Link):
    kind = "direct"
    def __init__(self, reader, writer, pre=b""):
        self.r, self.w, self.pre = reader, writer, pre                 # pre: 4 byte đầu đã đọc để phân biệt app ↔ công cụ (HTTP)
        _small_buffers(writer)

    async def _read(self, n):
        if self.pre:
            b, self.pre = self.pre[:n], self.pre[n:]
            return b + (await self.r.readexactly(n - len(b)) if len(b) < n else b"")
        return await self.r.readexactly(n)

    async def recv(self):
        n = struct.unpack(">I", await self._read(4))[0]
        if n < 1 or n > 8 * 1024 * 1024: raise ValueError("bad frame")
        b = await self._read(n)
        return b[0], b[1:]

    def write(self, t, payload=b""):
        if len(payload) < 4096: self.w.write(struct.pack(">IB", 1 + len(payload), t) + payload)
        else: self.w.write(struct.pack(">IB", 1 + len(payload), t)); self.w.write(payload)


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ---- Đẩy app cũ từ Cloudflare về đường thẳng ----
# App (Android ≤ 1.48, PC ≤ 1.102) nhớ đường nối được lần trước và thử nó ĐẦU TIÊN: đã từng đi Cloudflare (lúc modem chưa mở cổng)
# thì mở cổng rồi vẫn đi Cloudflare mãi (trễ ~100 ms, giật). Khi đã có máy ở NGOÀI mạng nhà nối thẳng được vào cổng phát hình
# (= modem đã mở cổng), lần đầu mỗi IP vào bằng WebSocket sẽ nhận 503 trong 20 giây → app tự thử đường thẳng và nhớ nó.
# Sau đó IP đó đi WebSocket bình thường 6 giờ (máy không nối thẳng được chỉ chậm ~20 giây, 6 giờ 1 lần).
# Chỉ đẩy app CloudBlue (User-Agent BlueRobloxApp/ · BlueRobloxPC/) — trình duyệt (play.html) không có đường thẳng, không đụng.
# Tắt: WS_NUDGE=0 trong cloudphone.conf.
WS_NUDGE = str(C.get("WS_NUDGE", "1")).strip() != "0"
NUDGE_WIN, NUDGE_COOL, NUDGE_PROOF = 20, 6 * 3600, 24 * 3600
_direct_ok_t = 0.0                  # lúc gần nhất có máy ở ngoài mạng nhà nối được vào cổng phát hình
_nudge = {}                         # IP khách → (hết trả 503 lúc, hết miễn lúc)


def _global_ip(host):
    try:
        import ipaddress
        ip = ipaddress.ip_address(str(host).split("%")[0])
        if getattr(ip, "ipv4_mapped", None): ip = ip.ipv4_mapped
        return ip.is_global
    except ValueError:
        return False


def note_direct_peer(writer):
    """Có kết nối vào cổng phát hình từ IP công khai → cổng modem chắc chắn đã mở."""
    global _direct_ok_t
    try: host = (writer.get_extra_info("peername") or ("",))[0]
    except Exception: host = ""
    if _global_ip(host): _direct_ok_t = time.time()


def ws_should_nudge(hdr, now=None):
    if not WS_NUDGE: return False
    ua = hdr.get("user-agent", "")
    if not (ua.startswith("BlueRobloxApp/") or ua.startswith("BlueRobloxPC/")): return False
    now = time.time() if now is None else now
    if now - _direct_ok_t > NUDGE_PROOF: return False                 # chưa thấy ai ở ngoài nối thẳng được → cổng có thể chưa mở
    ip = (hdr.get("cf-connecting-ip") or "").strip()
    if not ip: return False
    if len(_nudge) > 50000:
        for k in [k for k, v in _nudge.items() if v[1] < now]: _nudge.pop(k, None)
    until, cool = _nudge.get(ip, (0.0, 0.0))
    if now < until: return True
    if now < cool: return False
    _nudge[ip] = (now + NUDGE_WIN, now + NUDGE_COOL)
    return True


class WSLink(Link):
    kind = "ws"
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer; self.frag = None; self.op = 0
        _small_buffers(writer)

    @staticmethod
    async def accept(reader, writer):
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin-1").split("\r\n")
        hdr = {}
        for ln in lines[1:]:
            if ":" in ln: k, v = ln.split(":", 1); hdr[k.strip().lower()] = v.strip()
        if hdr.get("upgrade", "").lower() != "websocket" or "sec-websocket-key" not in hdr:
            body = b"BlueRoblox stream v2"
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
            await writer.drain(); writer.close(); return None
        if ws_should_nudge(hdr):                                     # app cũ đang dính Cloudflare → bảo nó thử đường thẳng
            writer.write(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain(); writer.close(); return None
        acc = base64.b64encode(hashlib.sha1((hdr["sec-websocket-key"] + WS_GUID).encode()).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode())
        await writer.drain()
        return WSLink(reader, writer)

    async def _frame(self):
        b0, b1 = await self.r.readexactly(2)
        fin, op, masked, n = b0 & 0x80, b0 & 0x0F, b1 & 0x80, b1 & 0x7F
        if n == 126: n = struct.unpack(">H", await self.r.readexactly(2))[0]
        elif n == 127: n = struct.unpack(">Q", await self.r.readexactly(8))[0]
        if n > 8 * 1024 * 1024: raise ValueError("ws frame too big")
        mk = await self.r.readexactly(4) if masked else None
        data = await self.r.readexactly(n) if n else b""
        if mk and n:
            m = (mk * (n // 4 + 1))[:n]
            data = (int.from_bytes(data, "little") ^ int.from_bytes(m, "little")).to_bytes(n, "little")
        return fin, op, data

    async def recv(self):
        while True:
            fin, op, data = await self._frame()
            if op == 8: raise EOFError("ws close")
            if op == 9: self._wframe(10, data); continue
            if op == 10: continue
            if op in (1, 2):
                if fin:
                    if op == 2 and data: return data[0], data[1:]
                    continue
                self.frag, self.op = bytearray(data), op; continue
            if op == 0 and self.frag is not None:
                self.frag += data
                if fin:
                    d, o = bytes(self.frag), self.op; self.frag = None
                    if o == 2 and d: return d[0], d[1:]

    def _wframe(self, op, data):
        n = len(data)
        hdr = bytes([0x80 | op]) + (bytes([n]) if n < 126 else (b"\x7e" + struct.pack(">H", n)) if n < 65536 else (b"\x7f" + struct.pack(">Q", n)))
        self.w.write(hdr)
        if n: self.w.write(data)

    def write(self, t, payload=b""):
        if len(payload) < 4096: self._wframe(2, bytes([t]) + payload)
        else:                                               # khung lớn: ghi đầu khung + dữ liệu riêng (không chép cả khung hình)
            n = 1 + len(payload)
            hdr = b"\x82" + ((b"\x7e" + struct.pack(">H", n)) if n < 65536 else (b"\x7f" + struct.pack(">Q", n)))
            self.w.write(hdr + bytes([t])); self.w.write(payload)

    async def close(self):
        if self.closed: return
        try: self.w.write(b"\x88\x00")
        except Exception: pass
        await Link.close(self)


# ================================================================ Phiên xem 1 máy
SESSIONS = {}


class Closed(Exception):
    pass


class Session:
    def __init__(self, link, me, phone, hello, t_hello):
        self.link, self.me, self.phone, self.hello, self.t_hello = link, me, phone, hello, t_hello
        self.pid = phone["id"]; self.name = phone["container"]; self.serial = f"127.0.0.1:{phone['port']}"
        self.q = hello.get("q") if hello.get("q") in ("eco", "bal", "hd", "auto") else "auto"
        self.cur_q = "bal" if self.q == "auto" else self.q
        try: self.fps_req = int(hello.get("fps") or 0); self.maxh_req = int(hello.get("maxh") or 0)
        except (TypeError, ValueError): self.fps_req = self.maxh_req = 0
        self.kbps_req = 0
        self.loop = asyncio.get_running_loop()
        self.aq = asyncio.Queue(); self.src = None; self.enc = None; self.ctl = None; self.vlock = asyncio.Lock()
        self.closed = False; self.last_rx = time.time()
        self.sent = 0; self.bytes = 0; self.drop = 0; self.wait_key = True; self.last_restart = 0.0; self.last_key_sent = 0.0
        self.congest = collections.deque(maxlen=20); self.calm_since = time.time(); self.restart_req = None
        self.vw = self.vh = 0; self.gen = 0; self.fps = 30; self.kbps = 0
        self.ack_pts = None; self.ack_t = 0.0; self.lag_ms = 0; self.base_ms = 0.0
        self.kbps_cur = None; self.kbps_cap = PRESETS[self.cur_q][2]; self.rate_t = 0.0
        self.net = str(hello.get("net") or "")[:2]           # app điện thoại báo loại mạng: w = wifi · c = 4G/5G
        self.kbps_cur = self._kbps_start()
        self.inflight = collections.deque(); self.delivered = collections.deque(); self.lat = collections.deque()
        self.key_grace = 0.0
        self.from_android = False          # True: Windows không quay được cửa sổ máy này → cả phiên lấy hình thẳng từ Android (scrcpy)
        self.dead = 0                      # số lần scrcpy chết khi CHƯA gửi được khung nào
        self._wn, self._wn_t = -1, time.time()   # số khung cửa sổ lần trước + lúc đổi (canh cửa sổ ngừng ra hình)
        self.t_auth = time.time()          # lần kiểm lại quyền gần nhất (REAUTH_S)

    # ---------- hình ----------
    def _kbps_start(self):
        """Bitrate lúc bắt đầu (None = trần của mức chất lượng). Tự động + 4G/5G → bắt đầu nhẹ, mạng ổn tự tăng dần."""
        return AUTO_CELL_KBPS if self.q == "auto" and self.net == "c" else None

    def _dims(self):
        maxh, fps, kbps = PRESETS[self.cur_q]
        if self.maxh_req: maxh = min(maxh, max(320, self.maxh_req))
        if self.fps_req: fps = max(10, min(fps, self.fps_req))
        try: fps = max(10, min(fps, int(self.phone.get("fps") or 60)))         # không vượt FPS khách đã mua
        except (TypeError, ValueError): pass
        if self.kbps_req: kbps = max(300, min(20000, self.kbps_req))
        self.kbps_cap = kbps
        if self.kbps_cur is None or self.kbps_cur > kbps: self.kbps_cur = kbps
        kbps = self.kbps_cur                                   # tự hạ theo mạng khách (đo bằng ACK)
        if kbps < 700: fps = min(fps, 20)
        elif kbps < 1400: fps = min(fps, 30)
        if self.q == "auto":                                   # Tự động: mạng yếu → giảm cả độ nét
            for lim, mh, mf in AUTO_TIERS:
                if kbps < lim: maxh, fps = min(maxh, mh), min(fps, mf); break
        sw, sh = self.src.cw, self.src.ch
        sc = min(1.0, maxh / max(sw, sh, 1))
        ow, oh = (sw, sh) if sc >= 0.999 else (max(16, int(sw * sc) & ~7), max(16, int(sh * sc) & ~7))
        return ow, oh, fps, kbps

    def _on_au(self, gen, data, key, cfg, pts):                # luồng bộ nén → vòng chính
        if gen != self.gen or self.closed: return
        t = time.monotonic()
        try: self.loop.call_soon_threadsafe(self._enqueue, (gen, data, key, cfg, pts, t))
        except RuntimeError: pass

    def _enqueue(self, it):
        if self.aq.qsize() > 240: self.drop += 1; self.wait_key = True; return     # app không đọc nữa → đừng tích hình vô hạn
        self.aq.put_nowait(it)

    def _start_video_scrcpy(self):
        """Hình lấy thẳng từ Android (scrcpy). Tắt bộ cũ TRƯỚC (máy ảo chỉ nên chạy 1 bộ mã hoá) rồi bật bộ mới → (rộng, cao) thật."""
        if self.closed: raise Closed()
        if not isinstance(self.src, ScrcpySource):
            if self.src: self.src.stop()
            src = ScrcpySource(self.serial, self.phone.get("res")); src.open(); self.src = src
            if self.closed: raise Closed()
        ow, oh, fps, kbps = self._dims()
        self.gen += 1; g = self.gen
        old_enc = self.enc
        enc = ScrcpyVideo(self.serial, max(ow, oh), fps, kbps, lambda d, k, c, p: self._on_au(g, d, k, c, p), lambda w, h: self._on_vsize(g, w, h))
        self.enc = enc
        if old_enc: old_enc.stop()
        if self.closed: enc.stop(); raise Closed()
        w, h = enc.start()
        if self.closed: enc.stop(); raise Closed()
        self.vw, self.vh, self.fps, self.kbps = w, h, fps, kbps
        if self.ctl: self.ctl.set_view(w, h)
        return w, h

    def _on_vsize(self, gen, w, h):                            # luồng đọc hình (scrcpy) → vòng chính: máy xoay → cỡ hình mới
        def apply():
            if gen != self.gen or self.closed or (w, h) == (self.vw, self.vh): return
            self.vw, self.vh = w, h
            if self.ctl: self.ctl.set_view(w, h)
            self.wait_key = True
            self.link.send_nowait(S_SIZE, json.dumps({"w": w, "h": h}).encode())
        try: self.loop.call_soon_threadsafe(apply)
        except RuntimeError: pass

    def _start_video(self, cpu=False):
        """(Bật lại) bộ quay + bộ nén. Chạy trong luồng nền; phiên đã đóng giữa chừng → dọn sạch thứ vừa tạo."""
        if video_mode() == "scrcpy" or self.from_android: return self._start_video_scrcpy()
        if self.closed: raise Closed()
        if self.src is None or self.src.resized() or getattr(self.src, "closed", False):
            old = self.src
            if old: old.stop()
            src = make_source(self.name, int(self.phone.get("fps") or 30))
            self.src = src
            try:
                src.open()
            except CaptureBlocked as e:
                src.stop()
                if self.closed: raise Closed()
                log(f"  {self.name}: {e} → lấy hình thẳng từ Android (scrcpy, {self.serial})")
                self.from_android = True
                try:
                    return self._start_video_scrcpy()
                except (Closed, Deny):
                    raise
                except Exception as e2:
                    log(f"  {self.name}: lấy hình thẳng từ Android cũng lỗi: {e2!r}")
                    raise Deny("OFFLINE", "Máy chủ chưa lấy được hình của máy này — thử mở lại sau ít phút hoặc báo hỗ trợ.")
            if self.closed: src.stop(); raise Closed()
        old_enc = self.enc
        ow, oh, fps, kbps = self._dims()
        self.gen += 1; g = self.gen
        enc = Encoder(self.src, ow, oh, fps, kbps, lambda d, k, c, p: self._on_au(g, d, k, c, p), cpu=cpu)
        self.enc = enc
        if old_enc: old_enc.stop()
        if self.closed: enc.stop(); raise Closed()
        enc.start()
        if self.closed: enc.stop(); raise Closed()
        self.vw, self.vh, self.fps, self.kbps = ow, oh, fps, kbps
        if self.ctl: self.ctl.set_view(ow, oh)
        return ow, oh

    async def restart_video(self, size_msg=False, cpu=False):
        async with self.vlock:
            if self.closed: return
            self.wait_key = True
            old = (self.vw, self.vh)
            w, h = await asyncio.to_thread(self._start_video, cpu)
            self.last_restart = time.time()
            if size_msg or (w, h) != old: self.link.send_nowait(S_SIZE, json.dumps({"w": w, "h": h}).encode())

    # ---------- vòng chính ----------
    async def run(self):
        old = SESSIONS.get(self.pid)
        if old and not old.closed and old.t_hello > self.t_hello:     # HELLO cũ đến muộn → không đá phiên mới hơn
            self.link.send_nowait(S_ERROR, json.dumps({"code": "BUSY", "msg": "Đang mở máy ở kết nối khác."}).encode())
            await self.link.close(); return
        SESSIONS[self.pid] = self
        if old and old is not self: await old.kick()
        log(f"▶ {self.name} ← {self.me['uid'][:8]} ({self.link.kind}, {self.hello.get('client', '?')})")
        self.ctl = Control(self.serial, self._on_clip)
        threading.Thread(target=self.ctl.start, daemon=True).start()
        try:
            async with self.vlock:
                w, h = await asyncio.to_thread(self._start_video)
            self.last_restart = time.time()
        except Closed:
            await self.finish(); return
        except Deny as d:
            self.link.send_nowait(S_ERROR, json.dumps({"code": d.code, "msg": d.msg}, ensure_ascii=False).encode()); await self.finish(); return
        except Exception as e:
            log("  lỗi bật hình:", repr(e))
            self.link.send_nowait(S_ERROR, json.dumps({"code": "INTERNAL", "msg": "Máy chủ chưa bật được hình — thử lại."}, ensure_ascii=False).encode())
            await self.finish(); return
        if self.closed: return
        self.wait_key = True
        self.link.send_nowait(S_WELCOME, json.dumps({"ok": True, "w": w, "h": h, "fps": self.fps, "kbps": self.kbps, "codec": "h264",
                                                      "enc": self.enc.enc, "name": self.phone.get("name") or self.name,
                                                      "android": str(self.phone.get("android") or ""), "q": self.q}, ensure_ascii=False).encode())
        tasks = [asyncio.create_task(x) for x in (self._sender(), self._receiver(), self._monitor())]
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pend: t.cancel()
        for t in done:
            ex = t.exception() if not t.cancelled() else None
            if ex and not isinstance(ex, (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, EOFError, OSError, ssl.SSLError, Closed)):
                log(f"  {self.name}: lỗi phiên {ex!r}")
        await self.finish()

    async def _sender(self):
        while not self.closed:
            it = await self.aq.get()
            if it[0] != self.gen: continue
            if not self.aq.empty():                    # có khung chờ (vừa nghẽn): khung cũ nhất đã đợi > 150 ms → nhảy tới khung khoá mới nhất
                items = [it]
                while not self.aq.empty(): items.append(self.aq.get_nowait())
                items = [x for x in items if x[0] == self.gen]
                if not items: continue
                if time.monotonic() - items[0][5] > 0.15:
                    ki = max((i for i, x in enumerate(items) if x[2] and x[1] is not None), default=None)
                    if ki is None:
                        self.drop += len(items); self.wait_key = True; self._congested(); continue
                    self.drop += ki; items = items[ki:]; self.wait_key = False
                for x in items: await self._consider(x)
                continue
            await self._consider(it)

    async def _consider(self, it):
        gen, data, key, cfg, pts, tp = it
        if gen != self.gen: return
        if data is None: self.wait_key = True; return          # mất khung → chờ khung khoá (tối đa ~1 giây), không hiện hình vỡ
        if self._behind_ms() > (1500 if time.time() < self.key_grace else 350):   # app chậm > 0,35 s → bỏ khung cho kịp (không để trễ dồn)
            if not self.wait_key: self._congested()
            self.drop += 1; self.wait_key = True
            return
        if self.wait_key and not key:
            self.drop += 1; return
        self.wait_key = False
        await self._send_au(it)

    def _behind_ms(self):
        """Khung CŨ NHẤT app chưa báo nhận đã đi bao lâu, trừ độ trễ nền của mạng (ms). App không gửi ACK → 0."""
        if self.ack_pts is None or not self.inflight: return 0
        return max(0.0, (time.time() - self.inflight[0][2]) * 1000 - self.base_ms)

    async def _send_au(self, it):
        gen, data, key, cfg, pts, tp = it
        await self.link.send(S_VIDEO, struct.pack(">BQ", (1 if key else 0) | (2 if cfg else 0), pts) + data, timeout=10)
        self.sent += 1; self.bytes += len(data)
        self.inflight.append((pts, len(data), time.time()))
        if len(self.inflight) > 3000: self.inflight.popleft()
        if key: self.key_grace = time.time() + 1.0; self.last_key_sent = time.time()

    def goodput_kbps(self):
        now = time.time(); b = sum(n for t, n in self.delivered if now - t <= 2.0)
        return b * 8 / 2.0 / 1000

    def _congested(self):
        """Mạng khách không kịp: hạ bitrate theo tốc độ app THẬT SỰ nhận được (đo bằng ACK)."""
        now = time.time(); self.congest.append(now); self.calm_since = now
        if now - self.rate_t > 3 and self.ack_t and now - self.ack_t < 3:
            gp = self.goodput_kbps(); cur = self.kbps_cur or self.kbps_cap
            new = int(max(250, min(cur * 0.7, gp * 0.8 if gp > 50 else cur * 0.5)))
            if new < cur * 0.92:
                self.kbps_cur = new; self.rate_t = now; self.restart_req = "quality"
                log(f"  {self.name}: mạng khách ~{gp:.0f} kbps → hạ còn {new} kbps")

    def _on_ack(self, ack):
        now = time.time(); self.ack_pts = ack; self.ack_t = now
        self.lag_ms = int(time.monotonic() * 1000 - ack / 1000)
        got = 0; last_t = None
        while self.inflight and self.inflight[0][0] <= ack:
            _, n, last_t = self.inflight.popleft(); got += n
        if got: self.delivered.append((now, got))
        while self.delivered and now - self.delivered[0][0] > 3: self.delivered.popleft()
        if last_t is not None:
            self.lat.append((now, (now - last_t) * 1000))
            while self.lat and now - self.lat[0][0] > 10: self.lat.popleft()
            self.base_ms = min(250.0, min(s for _, s in self.lat))     # trễ nền của mạng (tối đa 0,25 s — lớn hơn là đang nghẽn, không phải mạng xa)

    async def _receiver(self):
        c = self.ctl
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), 15)
            self.last_rx = time.time()
            try:
                if t == C_TOUCH and len(p) >= 6:
                    a, ptr, x, y = struct.unpack(">BBHH", p[:6]); c.touch(a, ptr, x, y)
                elif t == C_ACK and len(p) >= 8:
                    self._on_ack(struct.unpack(">Q", p[:8])[0])
                elif t == C_PING:
                    self.link.send_nowait(S_PONG, p[:8])
                elif t == C_KEY and len(p) >= 9:
                    a, code, meta = struct.unpack(">BII", p[:9]); c.key(1 if a else 0, code, meta)
                elif t == C_TEXT:
                    c.text(p.decode("utf-8", "replace"))
                elif t == C_SCROLL and len(p) >= 8:
                    x, y, h, v = struct.unpack(">HHhh", p[:8]); c.scroll(x, y, h, v)
                elif t == C_CMD:
                    jc = json.loads(p.decode() or "{}"); cmd = str(jc.get("cmd") or "")
                    if cmd in KEYCODE: c.press(KEYCODE[cmd])
                    elif cmd == "rotate": c.rotate(jc.get("to"))
                    elif cmd == "notif": c.notif()
                elif t == C_CLIP and len(p) >= 1:
                    c.clip_set(p[1:].decode("utf-8", "replace"), bool(p[0]))
                elif t == C_KEYFRAME:                       # khung khoá tự có mỗi ~1 giây; quá lâu chưa có thì mới bật lại bộ nén
                    if time.time() - self.last_key_sent > 1.5 and time.time() - self.last_restart > 1.5: self.restart_req = "key"
                elif t == C_QUALITY:
                    j = json.loads(p.decode() or "{}")
                    if j.get("q") in PRESETS or j.get("q") == "auto":
                        self.q = j["q"]; self.cur_q = "bal" if self.q == "auto" else self.q
                    self.fps_req = int(j.get("fps") or self.fps_req or 0); self.kbps_req = int(j.get("kbps") or 0)
                    self.kbps_cur = self._kbps_start(); self.restart_req = "quality"
                elif t == C_BYE:
                    return
            except (ValueError, TypeError, struct.error, json.JSONDecodeError, AttributeError):
                pass

    async def _monitor(self):
        t_stat = time.time(); s0 = b0 = 0
        while not self.closed:
            await asyncio.sleep(0.25)
            if time.time() - self.last_rx > 15: return
            try:
                if time.time() - self.t_auth >= REAUTH_S:
                    self.t_auth = time.time()
                    d = await asyncio.to_thread(recheck, self.pid, self.me)
                    if d:
                        log(f"  {self.name}: hết quyền ({d.code}) → ngắt phiên của {str(self.me.get('uid'))[:8]}")
                        raise d
                if self.src and (self.src.resized() or getattr(self.src, "closed", False)):
                    if self.src.resized():
                        await asyncio.sleep(0.35)               # chờ cửa sổ xoay xong
                        log(f"  {self.name}: xoay màn hình → phát lại")
                    else: log(f"  {self.name}: cửa sổ máy đóng/mở lại → quay lại")
                    await self.restart_video(size_msg=True); continue
                if isinstance(self.src, WindowSource):         # cửa sổ ngừng ra hình giữa chừng (giả lập thôi vẽ) → app thấy hình đứng → lấy hình từ Android
                    if self.src.n != self._wn: self._wn, self._wn_t = self.src.n, time.time()
                    elif time.time() - self._wn_t > 5 and time.time() - self.last_restart > 5:
                        log(f"  {self.name}: cửa sổ giả lập ngừng ra hình 5 giây → lấy hình thẳng từ Android (scrcpy)")
                        self.from_android = True; self._wn = -1
                        await self.restart_video(size_msg=True); continue
                if self.enc and self.enc.failed_early() and self.enc.enc == "nvenc":
                    log(f"  {self.name}: card NVIDIA không nén được → CPU x264")
                    _nvenc_broken["until"] = time.time() + 120
                    await self.restart_video(cpu=True); continue
                if self.enc and self.enc.proc and self.enc.proc.poll() is not None and time.time() - self.last_restart > 3:
                    if self.sent == 0 and getattr(self.enc, "enc", "") == "scrcpy":
                        self.dead += 1                          # Android không xuất được hình (VD MEmu Android 12 màn 0x0) → đừng bật lại mãi
                        if self.dead >= 3:
                            log(f"  {self.name}: Android không xuất được hình (scrcpy lỗi {self.dead} lần, 0 khung) → báo app")
                            raise Deny("OFFLINE", "Màn hình Android của máy này đang lỗi (máy chủ không lấy được hình) — báo hỗ trợ để làm lại máy.")
                    log(f"  {self.name}: bộ nén dừng → bật lại"); await self.restart_video(); continue
                if self.restart_req and time.time() - self.last_restart > 1.0:
                    self.restart_req = None; await self.restart_video()
                cur = self.kbps_cur or self.kbps_cap
                if cur < self.kbps_cap and time.time() - self.calm_since > 10 and time.time() - self.rate_t > 10:
                    self.kbps_cur = min(self.kbps_cap, int(cur * 1.3) + 100); self.rate_t = time.time()
                    log(f"  {self.name}: mạng ổn → tăng lên {self.kbps_cur} kbps"); await self.restart_video()
            except Closed:
                return
            except Deny as d:
                self.link.send_nowait(S_ERROR, json.dumps({"code": d.code, "msg": d.msg}, ensure_ascii=False).encode()); return
            if time.time() - t_stat >= 2:
                dt = time.time() - t_stat
                st = {"fps": round((self.sent - s0) / dt, 1), "kbps": int((self.bytes - b0) * 8 / dt / 1000), "drop": self.drop,
                      "enc": self.enc.enc if self.enc else "", "q": self.cur_q, "w": self.vw, "h": self.vh, "lag": self.lag_ms,
                      "ctl": self.ctl.mode if self.ctl and self.ctl.ready.is_set() else "…"}
                self.link.send_nowait(S_STATS, json.dumps(st).encode())
                t_stat = time.time(); s0, b0 = self.sent, self.bytes

    def _on_clip(self, text):                                  # luồng điều khiển → vòng chính
        if not self.closed:
            try: self.loop.call_soon_threadsafe(self.link.send_nowait, S_CLIP, text.encode("utf-8"))
            except RuntimeError: pass

    async def kick(self):
        self.link.send_nowait(S_ERROR, json.dumps({"code": "KICKED", "msg": "Máy đang được mở ở nơi khác."}, ensure_ascii=False).encode())
        await self.finish()

    async def finish(self):
        if self.closed: return
        self.closed = True
        if SESSIONS.get(self.pid) is self: SESSIONS.pop(self.pid, None)
        objs = [x for x in (self.enc, self.src, self.ctl) if x]
        def stop_all():
            for x in objs:
                try: x.stop()
                except Exception: pass
        threading.Thread(target=stop_all, daemon=True).start()    # tắt ffmpeg / quay / scrcpy ở luồng riêng (không chặn máy chủ)
        await self.link.close()
        log(f"■ {self.name} đóng (gửi {self.sent} khung, bỏ {self.drop})")


# ================================================================ XEM TRƯỚC TRỰC TIẾP (ô máy trong danh sách / "Xem tất cả" của app)
PREVIEW_MAX = int(C.get("PREVIEW_MAX") or 40)            # tối đa số ô xem trước cùng lúc trên máy chủ này
PREVIEW_PER_PHONE = 3                                    # mỗi máy tối đa 3 ô (chủ máy + người được chia sẻ trên vài thiết bị)
PREVIEW_FPS = 8
PREVIEWS = {}                                            # mã máy → [Preview…]


class Preview(Session):
    """Hình NHỎ (cạnh dài ≤ 480), 8 khung/giây, ít dữ liệu; KHÔNG điều khiển; KHÔNG đá phiên điều khiển đang mở và không bị
       phiên điều khiển đá (nhiều thiết bị xem cùng lúc). Hình lấy THẲNG từ Android (scrcpy-server nén ngay trong máy): không đụng
       tới cửa sổ giả lập (phiên điều khiển đang quay cửa sổ không bị xê dịch / mất hình) và không tốn ffmpeg của máy chủ."""
    def __init__(self, link, me, phone, hello, t_hello):
        super().__init__(link, me, phone, hello, t_hello)
        try: self.pmax = max(160, min(480, int(hello.get("maxh") or 480)))
        except (TypeError, ValueError): self.pmax = 480
        self.q = self.cur_q = "eco"

    def _dims(self):
        try: fps = max(2, min(PREVIEW_FPS, int(self.phone.get("fps") or 30)))
        except (TypeError, ValueError): fps = PREVIEW_FPS
        sw, sh = self.src.cw, self.src.ch
        sc = min(1.0, self.pmax / max(sw, sh, 1))
        ow, oh = (sw, sh) if sc >= 0.999 else (max(16, int(sw * sc) & ~7), max(16, int(sh * sc) & ~7))
        kbps = max(120, int(320 * (max(ow, oh) / 480) ** 2))
        self.kbps_cap = self.kbps_cur = kbps
        return ow, oh, fps, kbps

    def _start_video(self, cpu=False):
        if video_mode() == "fake": return super()._start_video(cpu=True)     # chạy thử (không có Android) → hình giả
        return self._start_video_scrcpy()

    def _congested(self):                                # mạng chậm → chỉ bỏ khung (không bật lại bộ nén cho ô nhỏ)
        self.calm_since = time.time()

    async def _receiver(self):
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), 15)
            self.last_rx = time.time()
            try:
                if t == C_ACK and len(p) >= 8: self._on_ack(struct.unpack(">Q", p[:8])[0])
                elif t == C_PING: self.link.send_nowait(S_PONG, p[:8])
                elif t == C_KEYFRAME:
                    if time.time() - self.last_key_sent > 1.5 and time.time() - self.last_restart > 1.5: self.restart_req = "key"
                elif t == C_BYE: return
            except (ValueError, TypeError, struct.error):
                pass

    async def run(self):
        if sum(len(v) for v in PREVIEWS.values()) >= PREVIEW_MAX:
            self.link.send_nowait(S_ERROR, json.dumps({"code": "BUSY", "msg": "Máy chủ đang bận — tạm tắt hình xem trước."}, ensure_ascii=False).encode())
            await self.link.close(); return
        lst = PREVIEWS.setdefault(self.pid, [])
        while len(lst) >= PREVIEW_PER_PHONE:                                # ô cũ nhất nhường chỗ — báo để app đó thôi nối lại (không giành qua lại)
            old = lst[0]
            try: old.link.send_nowait(S_ERROR, json.dumps({"code": "PREVIEW_LIMIT", "msg": "Máy đang được xem trước ở nhiều nơi."}, ensure_ascii=False).encode())
            except Exception: pass
            await old.finish()
            if old in lst: lst.remove(old)
        lst = PREVIEWS.setdefault(self.pid, []); lst.append(self)
        log(f"▷ xem trước {self.name} ← {self.me['uid'][:8]} ({self.link.kind})")
        try:
            async with self.vlock:
                w, h = await asyncio.to_thread(self._start_video)
            self.last_restart = time.time()
        except Closed:
            await self.finish(); return
        except Deny as d:
            self.link.send_nowait(S_ERROR, json.dumps({"code": d.code, "msg": d.msg}, ensure_ascii=False).encode()); await self.finish(); return
        except Exception as e:
            log("  lỗi bật hình xem trước:", repr(e))
            self.link.send_nowait(S_ERROR, json.dumps({"code": "INTERNAL", "msg": "Chưa bật được hình xem trước."}, ensure_ascii=False).encode())
            await self.finish(); return
        if self.closed: return
        self.wait_key = True
        self.link.send_nowait(S_WELCOME, json.dumps({"ok": True, "w": w, "h": h, "fps": self.fps, "kbps": self.kbps, "codec": "h264",
                                                      "enc": self.enc.enc, "name": self.phone.get("name") or self.name,
                                                      "android": str(self.phone.get("android") or ""), "q": "preview", "preview": True},
                                                     ensure_ascii=False).encode())
        tasks = [asyncio.create_task(x) for x in (self._sender(), self._receiver(), self._monitor())]
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pend: t.cancel()
        await self.finish()

    async def finish(self):
        if self.closed: return
        self.closed = True
        lst = PREVIEWS.get(self.pid) or []
        if self in lst: lst.remove(self)
        if not lst: PREVIEWS.pop(self.pid, None)
        objs = [x for x in (self.enc, self.src) if x]
        def stop_all():
            for x in objs:
                try: x.stop()
                except Exception: pass
        threading.Thread(target=stop_all, daemon=True).start()
        await self.link.close()
        log(f"▫ xem trước {self.name} đóng ({self.sent} khung)")


async def serve_link(link):
    try:
        t, p = await asyncio.wait_for(link.recv(), 10)
        t_hello = time.monotonic()
        if t != C_HELLO: raise ValueError("no hello")
        hello = json.loads(p.decode("utf-8"))
        try:
            me, phone = await asyncio.to_thread(authorize, hello)
        except Deny as d:
            link.send_nowait(S_ERROR, json.dumps({"code": d.code, "msg": d.msg}, ensure_ascii=False).encode()); await link.close(); return
        if str(hello.get("mode") or "") == "preview": await Preview(link, me, phone, hello, t_hello).run()
        else: await Session(link, me, phone, hello, t_hello).run()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, EOFError, ssl.SSLError, ValueError, OSError):
        await link.close()
    except Exception as e:
        log("lỗi phiên:", repr(e)); await link.close()


CPAPI_LOCAL = ("127.0.0.1", int(C.get("CPAPI_PORT") or 8010))
HTTP_VERBS = (b"GET ", b"POST", b"PUT ", b"HEAD", b"OPTI", b"DELE", b"PATC")


async def http_to_cpapi(head, reader, writer):
    """CÔNG CỤ MÁY qua chính cổng TLS này (cài APK, clone tab, khởi động lại, chụp màn…): chuyển thẳng tới cpapi 127.0.0.1:8010.
       App không cần tên miền / Cloudflare. cpapi tự kiểm phiên đăng nhập + quyền với từng máy như khi đi qua web."""
    uw = None
    try:
        line = head + await asyncio.wait_for(reader.readuntil(b"\r\n"), 15)
        parts = line.split(b" ")
        if len(parts) != 3 or not parts[1].startswith(b"/cpapi/"):
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"); await writer.drain(); return
        ur, uw = await asyncio.wait_for(asyncio.open_connection(*CPAPI_LOCAL), 5)
        uw.write(line)
        async def pipe(r, w):
            while True:
                b = await r.read(256 * 1024)
                if not b: return
                w.write(b); await w.drain()
        tasks = {asyncio.ensure_future(pipe(reader, uw)), asyncio.ensure_future(pipe(ur, writer))}
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)   # 1 chiều xong (cpapi trả lời xong / app đóng) → đóng cả 2
        for t in pend: t.cancel()
        for t in done:
            try: t.exception()
            except BaseException: pass
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
        if uw is None:                                        # cpapi (đèn "Cổng bảo vệ :8010") đang tắt
            try:
                body = json.dumps({"error": "Công cụ máy đang tắt trên máy chủ (cổng bảo vệ :8010) — thử lại sau ít phút."}, ensure_ascii=False).encode()
                writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\nConnection: close\r\n"
                             + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
            except Exception: pass
    except Exception as e:
        log("công cụ (HTTP) lỗi:", repr(e))
    finally:
        for w in (uw, writer):
            if w is None: continue
            try: w.close()
            except Exception: pass


async def on_direct(reader, writer):
    note_direct_peer(writer)
    try: head = await asyncio.wait_for(reader.readexactly(4), 20)
    except Exception:
        try: writer.close()
        except Exception: pass
        return
    if head in HTTP_VERBS: return await http_to_cpapi(head, reader, writer)     # app gọi công cụ máy (HTTP)
    await serve_link(DirectLink(reader, writer, head))                          # app xem / điều khiển (BRS2)


async def on_ws(reader, writer):
    try: link = await WSLink.accept(reader, writer)
    except Exception:
        try: writer.close()
        except Exception: pass
        return
    if link: await serve_link(link)


# ================================================================ Chứng chỉ TLS (tự ký, app kiểm bằng mã SHA-256)
def ensure_cert():
    if not (os.path.isfile(CERT) and os.path.isfile(CKEY)):
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            log("cài thư viện cryptography (tạo chứng chỉ)…")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "cryptography"], creationflags=NOWIN)
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.generate_private_key(ec.SECP256R1())
        nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bluestream " + NODE_ID)])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(k.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650)).sign(k, hashes.SHA256()))
        open(CKEY, "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        open(CERT, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    pem = open(CERT, encoding="ascii").read()
    der = ssl.PEM_cert_to_DER_cert(pem)
    return hashlib.sha256(der).hexdigest()


# ================================================================ Báo đường nối lên Supabase (app đọc qua cloudphone_endpoint)
def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except OSError:
        return None


def public_ip():
    if C.get("STREAM_PUBLIC_IP"): return C["STREAM_PUBLIC_IP"]
    for u in ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"):
        try:
            ip = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "BlueRoblox"}), timeout=8).read().decode().strip()
            if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip): return ip
        except Exception: pass
    return None


def publish_loop(fp):
    warned = False; last = None
    while True:
        try:
            direct = []
            lip, pip_ = lan_ip(), public_ip()
            if lip: direct.append({"host": lip, "port": PORT, "lan": True})
            if pip_ and pip_ != lip: direct.append({"host": pip_, "port": PORT})
            stream = {"direct": direct, "cert": fp, "ws": WS_URL or None, "api": API_BASE, "v": 2,
                      "preview": 1}          # có hình xem trước trực tiếp (app chỉ bật ô xem trước khi máy chủ báo có — máy chủ cũ sẽ đá phiên điều khiển)
            if stream != last:
                log(f"đường nối: trực tiếp {', '.join(d['host'] + ':' + str(d['port']) for d in direct) or '—'}"
                    + (f" · dự phòng {WS_URL}" if WS_URL else " · (chưa có dự phòng Cloudflare STREAM_WS)"))
            sb("PATCH", f"/rest/v1/cloud_nodes?id=eq.{urllib.parse.quote(NODE_ID)}", {"stream": stream}, extra={"Prefer": "return=minimal"})
            last = stream
        except urllib.error.HTTPError as e:
            if not warned: log(f"chưa báo được đường nối lên web (HTTP {e.code}) — đã chạy SQL v20 chưa?"); warned = True
        except Exception as e:
            if not warned: log("chưa báo được đường nối lên web:", e); warned = True
        time.sleep(60)


def firewall():
    if not WIN: return
    nm = "BlueRoblox Stream TCP"
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], capture_output=True, creationflags=NOWIN)
    subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={nm}", "dir=in", "action=allow", "protocol=TCP",
                    f"localport={PORT}"], capture_output=True, creationflags=NOWIN)


# ================================================================ UPnP-IGD: máy chủ TỰ MỞ CỔNG TCP PORT trên modem
# Trước đây admin mỗi máy chủ phải vào trang modem (FPT…) mở cổng bằng tay — máy nào chưa mở thì khách phải đi đường hầm
# Cloudflare (chậm). Giờ máy chủ tự xin modem: SSDP tìm modem → đọc mô tả thiết bị → AddPortMapping TCP PORT → IP LAN:PORT.
# Làm lúc chạy + mỗi 30 phút (gia hạn, modem khởi động lại, máy đổi IP LAN: cổng cũ mang tên "CloudBlue <NODE_ID>" tự xoá rồi mở lại).
# Nhật ký chỉ ghi khi kết quả đổi ("UPnP: ✓ …" / "UPnP: ✗ …"). Tắt: UPNP=0 trong cloudphone.conf.
# Thử tay (không chạy máy chủ):  python bluestream.py --upnp
UPNP = str(C.get("UPNP", "1")).strip().lower() not in ("0", "off", "false", "no")
UPNP_EVERY = 30 * 60                 # mở được → làm lại sau 30 phút
UPNP_RETRY = 120                     # chưa được → thử lại sau 2, 4, 8, 16 phút… (tối đa 30) — mới bật máy, modem đang khởi động lại
UPNP_BUDGET = 18.0                   # 1 lần thử tối đa ~18 giây (mỗi lần gọi modem ≤ 4 giây)
SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_ST = ("urn:schemas-upnp-org:device:InternetGatewayDevice:1", "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
           "urn:schemas-upnp-org:service:WANIPConnection:1", "urn:schemas-upnp-org:service:WANPPPConnection:1")
UPNP_NO_ANSWER = "modem không trả lời UPnP (UPnP đang tắt trên modem hoặc modem không hỗ trợ) — mở cổng bằng tay trong trang modem"
_UPNP_NAT = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
_UPNP_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # nói thẳng với modem: proxy hệ thống không xen vào


class UpnpFault(Exception):
    """Modem báo lỗi / không trả lời. code = mã lỗi UPnP (718 = cổng đã có người giữ, 725…) hoặc None (mạng, HTTP)."""
    def __init__(self, code, desc):
        super().__init__(f"lỗi {code} {desc}" if code else desc); self.code, self.desc = code, desc


def _upnp_why(e):
    r = getattr(e, "reason", None) if isinstance(e, urllib.error.URLError) else None
    if isinstance(e, (socket.timeout, TimeoutError)) or isinstance(r, (socket.timeout, TimeoutError)): return "hết giờ chờ modem"
    if isinstance(e, ConnectionRefusedError) or isinstance(r, ConnectionRefusedError): return "modem từ chối kết nối"
    return str(r or e) or e.__class__.__name__


def _ip4(s):
    """'1.2.3.4' → IPv4Address · rỗng / 0.0.0.0 / sai → None."""
    import ipaddress
    try: a = ipaddress.IPv4Address(str(s or "").strip())
    except ValueError: return None
    return None if a.is_unspecified else a


def _upnp_http(url, deadline, data=None, headers=None):
    """GET (data=None) / POST tới modem → (mã HTTP, nội dung ≤ 256 KB). Mỗi lần chờ ≤ 4 giây và không quá `deadline`.
       HTTP 500 (lỗi SOAP) vẫn trả nội dung để đọc errorCode."""
    left = deadline - time.monotonic()
    if left < 0.1: raise TimeoutError("hết giờ")
    h = {"User-Agent": "CloudBlue UPnP/1.1"}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="GET" if data is None else "POST")
    try:
        with _UPNP_HTTP.open(req, timeout=min(4.0, left)) as r: return r.status, r.read(262144)
    except urllib.error.HTTPError as e:
        try: return e.code, e.read(262144)
        except Exception: return e.code, b""
        finally: e.close()


def _xml_vals(b):
    """Mọi phần tử lá của 1 trả lời XML → {tên bỏ namespace: chữ}. XML hỏng (modem rẻ tiền) → dò bằng regex."""
    b = (b or b"").strip(b" \t\r\n\x00"); out = {}
    if b"<!DOCTYPE" not in b and b"<!ENTITY" not in b:
        try:
            for el in ET.fromstring(b).iter():
                if len(el) == 0 and isinstance(el.tag, str): out.setdefault(el.tag.rsplit("}", 1)[-1], (el.text or "").strip())
            return out
        except ET.ParseError: pass
    for k, v in re.findall(r"<(?:[\w.-]+:)?([\w.-]+)(?:\s[^<>]*)?>([^<]*)</", b.decode("utf-8", "replace")):
        out.setdefault(k, v.strip().replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
    return out


def ssdp_find(lan=None, target=SSDP_ADDR, wait=2.5):
    """Tìm modem UPnP: M-SEARCH (4 loại ST) tới `target` (mặc định nhóm multicast SSDP; thử nghiệm: modem giả unicast), gửi qua
       ĐÚNG card mạng LAN `lan` (máy giả lập có nhiều card ảo), gom các LOCATION (URL mô tả thiết bị) trong `wait` giây."""
    locs = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        if lan:
            try: s.bind((lan, 0))
            except OSError: pass                                  # IP vừa đổi… → để hệ điều hành tự chọn card
            try: s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(lan))
            except OSError: pass
        try: s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        except OSError: pass
        for st in SSDP_ST:
            try: s.sendto(f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: {st}\r\n\r\n'.encode(), target)
            except OSError: pass
        end = time.monotonic() + wait
        while len(locs) < 16:
            left = end - time.monotonic()
            if left <= 0: break
            s.settimeout(left)
            try: data, _ = s.recvfrom(8192)
            except socket.timeout: break
            except ConnectionResetError: continue                 # Windows: ICMP "cổng đóng" của lần gửi trước — bỏ qua
            except OSError: break
            m = re.search(rb"(?im)^location[ \t]*:[ \t]*(\S+)", data)
            loc = m.group(1).decode("latin-1") if m else ""
            if loc.lower().startswith("http://") and loc not in locs: locs.append(loc)
    finally:
        s.close()
    return locs


def igd_services(xml, location):
    """Mô tả thiết bị UPnP → [(serviceType, controlURL tuyệt đối)] các dịch vụ WANIPConnection / WANPPPConnection theo thứ tự trong file
       (không phụ thuộc namespace, thiết bị lồng nhau bao nhiêu tầng cũng được; controlURL tương đối → ghép với URLBase hoặc `location`)."""
    xml = (xml or b"").strip(b" \t\r\n\x00"); base, found = "", []
    try:
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml: raise ET.ParseError("DTD")
        root = ET.fromstring(xml)
        ln = lambda e: e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""
        for e in root:
            if ln(e) == "URLBase": base = (e.text or "").strip()
        for e in root.iter():
            if ln(e) == "service":
                f = {ln(c): (c.text or "").strip() for c in e}
                found.append((f.get("serviceType", ""), f.get("controlURL", "")))
    except ET.ParseError:                                         # XML hỏng (VD dấu "&" trần trong tên modem) → dò bằng regex
        t = xml.decode("utf-8", "replace")
        tag = lambda n: r"<(?:[\w.-]+:)?" + n + r"\b[^>]*>\s*([^<]*?)\s*</"
        m = re.search(tag("URLBase"), t); base = m.group(1) if m else ""
        for blk in re.findall(r"<(?:[\w.-]+:)?service\b[^>]*>(.*?)</(?:[\w.-]+:)?service\s*>", t, re.S):
            a, c = re.search(tag("serviceType"), blk), re.search(tag("controlURL"), blk)
            found.append((a.group(1) if a else "", c.group(1) if c else ""))
    return [(st, urllib.parse.urljoin(base or location, ctl)) for st, ctl in found
            if ctl and ("WANIPConnection" in st or "WANPPPConnection" in st)]


def upnp_soap(ctl, st, action, args=(), deadline=None):
    """Gọi lệnh SOAP `action` của dịch vụ `st` tại `ctl` → {tên: giá trị} modem trả về. Lỗi (HTTP 500 + errorCode / mạng) → UpnpFault."""
    deadline = deadline or time.monotonic() + 4
    x = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    body = ('<?xml version="1.0"?>\r\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{x(st)}">' + "".join(f"<{k}>{x(v)}</{k}>" for k, v in args)
            + f"</u:{action}></s:Body></s:Envelope>\r\n").encode("utf-8")
    try: code, resp = _upnp_http(ctl, deadline, body, {"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{st}#{action}"'})
    except Exception as e: raise UpnpFault(None, _upnp_why(e))
    v = _xml_vals(resp)
    if code == 200 and "errorCode" not in v: return v
    ec = v.get("errorCode", "")
    raise UpnpFault(int(ec) if ec.isdigit() else None, v.get("errorDescription") or f"HTTP {code}")


def _upnp_nat_warn(ext, pub):
    """IP ngoài của modem là IP nội bộ / CGNAT, hoặc khác IP ra Internet → phía trên còn 1 lớp NAT: mở cổng trên modem không đủ."""
    import ipaddress
    a = _ip4(ext)
    if not a: return ""
    if a in ipaddress.IPv4Network("100.64.0.0/10"):
        return (f"⚠ IP modem {a} là IP dùng chung của nhà mạng (CGNAT) — nhà mạng NAT thêm 1 lớp nên mở cổng trên modem KHÔNG giúp "
                "khách nối thẳng được: cần xin nhà mạng IP công khai (IP public / IP tĩnh)")
    if any(a in ipaddress.IPv4Network(n) for n in _UPNP_NAT):
        return (f"⚠ IP modem {a} là IP nội bộ — phía trên còn 1 lớp NAT nữa (nhà mạng, hoặc modem/router khác) nên mở cổng ở đây KHÔNG "
                "giúp khách nối thẳng được: cần IP công khai từ nhà mạng (hoặc chuyển thiết bị phía trên sang bridge)")
    p = _ip4(pub)
    if p and p != a:
        return (f"⚠ IP modem {a} khác IP ra Internet {p} — mạng còn đi qua 1 lớp NAT nữa của nhà mạng nên mở cổng KHÔNG giúp khách "
                "nối thẳng được: cần xin nhà mạng IP công khai")
    return ""


def upnp_open(port=None, lan=None, ssdp=None, wait=2.5, pub=None):
    """Mở cổng TCP `port` (mặc định PORT) trên modem → `lan` (mặc định lan_ip()):port bằng UPnP-IGD → (ok, thông báo tiếng Việt).
       ssdp: nơi gửi M-SEARCH (mặc định 239.255.255.250:1900; thử nghiệm: modem giả) · pub: IP công khai để so với IP modem
       (None = tự hỏi public_ip() song song, "" = không so). KHÔNG BAO GIỜ ném lỗi; cả lần thử ≤ ~18 giây."""
    try:
        return _upnp_open(int(port or PORT), lan or lan_ip(), ssdp or SSDP_ADDR, wait, pub)
    except Exception as e:
        return False, f"lỗi UPnP: {e!r}"


def _upnp_open(port, lan, target, wait, pub):
    if not lan: return False, "không biết IP mạng LAN của máy này (chưa nối mạng?) — chưa mở được cổng bằng UPnP"
    deadline = time.monotonic() + UPNP_BUDGET
    got, th = {"pub": pub}, None
    if pub is None:                                               # hỏi IP công khai song song lúc chờ modem trả lời
        def ask():
            try: got["pub"] = public_ip()
            except Exception: pass
        th = threading.Thread(target=ask, daemon=True); th.start()
    locs = ssdp_find(lan, target, wait)
    if not locs: return False, UPNP_NO_ANSWER
    svcs, errs = [], []
    for loc in locs[:6]:
        if svcs and time.monotonic() > deadline - 8: break         # để dành thời gian cho lệnh mở cổng
        try:
            code, xml = _upnp_http(loc, deadline)
            if code != 200: raise ValueError(f"HTTP {code}")
            svcs += [sv for sv in igd_services(xml, loc) if sv not in svcs]
        except Exception as e:
            errs.append(f"{urllib.parse.urlsplit(loc).netloc}: {_upnp_why(e)}")
    if not svcs:
        why = errs[0] if errs else "không có dịch vụ mở cổng WANIPConnection / WANPPPConnection"
        return False, f"modem trả lời UPnP nhưng không dùng được ({why}) — mở cổng bằng tay trong trang modem"
    # modem nhà mạng hay có nhiều đường WAN (Internet, quản lý TR-069, IPTV…) → chọn đường có IP Internet thật
    best, rank, ext = svcs[0], -1, ""
    for i, sv in enumerate(svcs[:4]):
        if i and time.monotonic() > deadline - 8: break
        try: ip = upnp_soap(sv[1], sv[0], "GetExternalIPAddress", (), deadline).get("NewExternalIPAddress", "")
        except UpnpFault: ip = ""
        a = _ip4(ip); r = 0 if not a else 2 if a.is_global else 1
        if r > rank: best, rank, ext = sv, r, (str(a) if a else "")
        if r == 2: break
    st, ctl = best
    me = f"CloudBlue {NODE_ID}"
    key = (("NewRemoteHost", ""), ("NewExternalPort", port), ("NewProtocol", "TCP"))

    def add():
        """Hạn 0 (vĩnh viễn); modem không nhận (lỗi khác 718) → thử lại 1 lần hạn 7200 giây (vẫn được gia hạn mỗi 30 phút)."""
        f = None
        for lease in (0, 7200):
            try:
                upnp_soap(ctl, st, "AddPortMapping", key + (("NewInternalPort", port), ("NewInternalClient", lan), ("NewEnabled", 1),
                                                           ("NewPortMappingDescription", me), ("NewLeaseDuration", lease)), deadline)
                return None
            except UpnpFault as e:
                f = e
                if e.code == 718: break
        return f

    f = add()
    if f:                                                         # cổng đã có người giữ? → hỏi modem cổng đang chuyển tới đâu
        try: cur = upnp_soap(ctl, st, "GetSpecificPortMappingEntry", key, deadline)
        except UpnpFault: cur = {}
        who, desc = cur.get("NewInternalClient", "").strip(), cur.get("NewPortMappingDescription", "").strip()
        iport, lease = cur.get("NewInternalPort", "").strip(), cur.get("NewLeaseDuration", "").strip()
        on = cur.get("NewEnabled", "1").strip().lower() not in ("0", "false")
        here = bool(who) and (who == lan or _ip4(who) is not None and _ip4(who) == _ip4(lan))
        if here and on and iport in ("", str(port)) and not (desc == me and lease.isdigit() and 0 < int(lease) < UPNP_EVERY + 300):
            f = None                                              # đã chuyển đúng về máy này (mở tay / lần trước) → xong
        elif who and desc == me:                                  # cổng của chính máy chủ này nhưng IP LAN cũ / sắp hết hạn → xoá, mở lại
            try: upnp_soap(ctl, st, "DeletePortMapping", key, deadline)
            except UpnpFault: pass
            f = add()
        elif here:
            return False, (f"cổng TCP {port} trên modem chuyển về máy này nhưng sai ({who}:{iport or '?'}{'' if on else ', đang tắt'}) "
                           f"— sửa trong trang modem: TCP {port} → {lan}:{port}")
        elif who:
            return False, f"cổng TCP {port} trên modem đang chuyển tới máy khác ({who}{' · ' + desc[:40] if desc else ''}) — sửa trong trang modem"
        elif f.code == 718:
            return False, (f"cổng TCP {port} trên modem đã bị chiếm (modem không cho biết chuyển tới máy nào — có thể đã mở tay) "
                           f"— kiểm tra trang modem: TCP {port} phải chuyển tới {lan}:{port}")
    if f: return False, f"không mở được cổng TCP {port} qua UPnP ({f}) — mở cổng bằng tay trong trang modem"
    a = _ip4(ext)
    if th and a and a.is_global: th.join(max(0.0, min(6.0, deadline - time.monotonic())))
    w = _upnp_nat_warn(ext, got.get("pub"))
    return True, f"đã mở cổng TCP {port} → {lan}:{port}" + (f" · IP modem {ext}" if ext else "") + (f" · {w}" if w else "")


def upnp_loop():
    """Luồng nền (main): mở cổng lúc chạy + mỗi 30 phút; chưa được thì thử lại sớm hơn. Nhật ký chỉ ghi khi kết quả đổi. Không bao giờ ném lỗi."""
    last, fails = None, 0
    while True:
        try: ok, msg = upnp_open()
        except Exception as e: ok, msg = False, f"lỗi UPnP: {e!r}"
        if (ok, msg) != last:
            log(("UPnP: ✓ " if ok else "UPnP: ✗ ") + str(msg)); last = (ok, msg)
        fails = 0 if ok else fails + 1
        time.sleep(UPNP_EVERY if ok else min(UPNP_EVERY, UPNP_RETRY * 2 ** min(fails - 1, 10)))


def upnp_cli():
    """python bluestream.py --upnp → thử mở cổng PORT trên modem 1 lần (KHÔNG chạy máy chủ), in kết quả. Trả 0 = mở được."""
    print(f"== UPnP: mở cổng TCP {PORT} trên modem về máy chủ {NODE_ID}" + ("" if UPNP else "   (UPNP=0: máy chủ sẽ KHÔNG tự mở cổng)"))
    lip = lan_ip(); print("  IP LAN máy này:", lip or "? (chưa nối mạng)")
    pip_ = public_ip(); print("  IP công khai:  ", pip_ or "? (không hỏi được)")
    ok, msg = upnp_open(lan=lip, pub=pip_ or "")
    print(("  ✓ " if ok else "  ✗ ") + msg)
    if not ok and lip: print(f"  → mở tay: trang modem (thường http://192.168.1.1) → NAT / Port Forwarding: TCP {PORT} → {lip}:{PORT}")
    return 0 if ok else 1


def _save_png(frame, name):
    if frame is None: return "(không có khung nào)"
    p = os.path.join(B, "logs", "captest_" + re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".png")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        from PIL import Image
        Image.fromarray(frame[:, :, 2::-1].copy()).save(p)          # BGRA → RGB
        return p
    except Exception as e:
        return f"(không lưu được ảnh: {e!r})"


def captest(name, port=None):
    """THỬ LẤY HÌNH 1 máy ngay trên máy chủ — không cần app, không cần đăng nhập, không đụng phiên khách đang xem:
         python bluestream.py --captest cp_xxx [cổng adb]
       Quay cửa sổ giả lập 3 giây → in cỡ + khung/giây + lưu ảnh logs\\captest_<tên>.png. Windows không cho quay / không ra khung
       → thử lấy hình thẳng từ Android (scrcpy) 3 giây. Trả 0 = lấy được hình."""
    print(f"== Thử lấy hình máy {name}")
    ok = False
    if WIN:
        hs = [y for xs in _same_name(name) for y in xs]
        print("  cửa sổ:" if hs else "  ✗ không thấy cửa sổ nào mang tên này (máy đang tắt? sai tên?)")
        for x in hs[:6]: print("   ·", win_info(x))
    if WIN and wgc_ok() and (C.get("CAPTURE") or "").strip().lower() not in ("scrcpy", "gdi"):
        src = WindowSource(name)
        try:
            w, h = src.open(); n0, t0 = src.n, time.time()
            time.sleep(3)
            fps = (src.n - n0) / max(0.1, time.time() - t0); fr = src.latest
            dark = fr is not None and int(fr[::16, ::16, :3].max()) < 8
            print(f"  ✓ quay cửa sổ được: phần Android {w}x{h}, {fps:.0f} khung/giây")
            print(f"    ảnh: {_save_png(fr, name)} — " + ("TOÀN ĐEN (giả lập không vẽ hình?)" if dark else "có hình"))
            hw, _ = find_window(name)
            if hw: print("    cửa sổ giờ ở:", win_info(hw))
            ok = not dark
        except CaptureBlocked as e: print("  ✗ quay cửa sổ:", e)
        except Deny as d: print("  ✗ quay cửa sổ:", d.msg)
        except Exception as e: print("  ✗ quay cửa sổ lỗi:", repr(e))
        finally: src.stop()
    if ok: return 0
    port = port or (phones_json().get(name) or {}).get("port")
    if not port:
        print("  ✗ không biết cổng adb của máy này → thêm cổng: --captest TÊN CỔNG"); return 1
    serial = f"127.0.0.1:{port}"; got = []; sv = None
    print(f"== Thử lấy hình thẳng từ Android (scrcpy) {serial}")
    try:
        print("  màn hình Android: %dx%d" % ScrcpySource(serial).open())
        sv = ScrcpyVideo(serial, 1280, 30, 3000, lambda d, k, c, p: got.append(len(d)))
        w, h = sv.start(); time.sleep(3)
        print(f"  {'✓' if got else '✗'} scrcpy: {w}x{h}, {len(got)} khung trong 3 giây")
        ok = bool(got)
    except Exception as e:
        print("  ✗ scrcpy lỗi:", repr(e))
    finally:
        if sv: sv.stop()
    return 0 if ok else 1


async def main():
    if not SELFTEST and (not SB or not KEY):
        log("THIẾU SUPABASE_URL / SUPABASE_SERVICE_KEY trong cloudphone.conf"); sys.exit(1)
    if WIN:
        try: import numpy, windows_capture  # noqa: F401
        except ModuleNotFoundError:
            log("cài thư viện quay cửa sổ (windows-capture, numpy)…")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "windows-capture", "numpy"], creationflags=NOWIN)
        except ImportError:
            pass                                         # Windows 10 trước bản 1903: không có Windows Graphics Capture → quay bằng PrintWindow
        video_mode()                                     # ghi nhật ký cách lấy hình đang dùng (wgc / scrcpy / gdi)
        await asyncio.to_thread(ensure_ffmpeg)
        threading.Thread(target=ensure_jar, daemon=True).start()
    fp = ensure_cert()
    firewall()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, CKEY)
    srv1 = await asyncio.start_server(on_direct, "0.0.0.0", PORT, ssl=ctx, limit=1 << 20)
    srv2 = await asyncio.start_server(on_ws, "127.0.0.1", WS_PORT, limit=1 << 20)
    log(f"bluestream chạy · trực tiếp TLS :{PORT} (modem mở cổng TCP {PORT} về máy này) · WebSocket 127.0.0.1:{WS_PORT} · máy chủ {NODE_ID}")
    log(f"mã chứng chỉ: {fp[:16]}…  · bộ nén: {'CPU x264' if ALWAYS_CPU else f'NVENC (tối đa {NVENC_MAX}) → x264'} · ffmpeg: {FF}")
    if not SELFTEST: threading.Thread(target=publish_loop, args=(fp,), daemon=True).start()
    if not SELFTEST and UPNP: threading.Thread(target=upnp_loop, daemon=True).start()        # tự mở cổng TCP PORT trên modem (UPnP)
    elif not SELFTEST: log(f"UPnP: tắt (UPNP=0) — nhớ mở cổng TCP {PORT} về máy này bằng tay trong trang modem")
    async with srv1, srv2:
        await asyncio.gather(srv1.serve_forever(), srv2.serve_forever())


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    if "--captest" in sys.argv:
        _a = sys.argv[sys.argv.index("--captest") + 1:]
        if not _a: print("Cách dùng: python bluestream.py --captest TÊN_MÁY [CỔNG_ADB]"); sys.exit(2)
        sys.exit(captest(_a[0], _a[1] if len(_a) > 1 else None))
    if "--upnp" in sys.argv:                                     # thử mở cổng trên modem bằng UPnP (không chạy máy chủ)
        sys.exit(upnp_cli())
    if WIN:
        try: ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000)   # ABOVE_NORMAL (ffmpeg con cũng vậy)
        except Exception: pass
    asyncio.run(main())
