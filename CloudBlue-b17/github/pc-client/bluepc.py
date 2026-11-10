# -*- coding: utf-8 -*-
# =====================================================================================================
#  CloudBlue PC — app máy tính cho KHÁCH: đăng nhập, xem danh sách máy, điều khiển máy mượt (giải mã phần cứng/CPU)
#
#  Chạy thử:   python bluepc.py                 (cần: pip install av pygame-ce numpy)
#  Đóng gói:   build.bat  → dist\CloudBluePC\CloudBluePC.exe (+ CloudBluePC.zip để đưa lên web)
#  Mở thẳng 1 máy:  CloudBluePC.exe blueroblox://phone/<mã máy>   (web có nút "Mở bằng app máy tính")
#
#  Mỗi cửa sổ máy là 1 tiến trình riêng (mở nhiều máy cùng lúc không giật nhau).
#  Không chứa khoá bí mật nào: chỉ khoá công khai Supabase (giống web/app Android) + phiên đăng nhập của chính khách.
# =====================================================================================================
import datetime, hashlib, json, os, queue, re, secrets, subprocess, sys, threading, time, traceback, urllib.error, urllib.parse, urllib.request, webbrowser

APP_VER = "1.0.0"                                 # GitHub Actions ghi số bản thật (1.<số lần build>) trước khi đóng gói
SB = "https://nprftgodswlpzomcttal.supabase.co"
KEY = "sb_publishable_qfNcnOMv70nq5LIlYXDJzg_UtdWHVze"          # khoá CÔNG KHAI (giống web + app Android)
WEB = "https://cloudblue.vn"                    # web chính; Supabase settings.data.web ghi đè được (đổi tên miền không cần cập nhật app)
PHONE_API = "https://phone.cloudblue.vn"        # chỉ dùng khi máy chủ chưa báo đường cpapi (stream.api)
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
sys.path.insert(0, HERE)
DATA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "BlueRobloxPC")
os.makedirs(DATA, exist_ok=True)
SESS, LOCKF, LOGF, PREFS = (os.path.join(DATA, x) for x in ("session.json", "session.lock", "log.txt", "settings.json"))
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def app_code():
    """Số bản đang chạy (1.57 → 57) để so với download/pc.json trên web; bản chạy thử từ mã nguồn = 0."""
    m = re.match(r"^1\.(\d+)$", APP_VER)
    return int(m.group(1)) if m else 0


def log(*a):
    try:
        with open(LOGF, "a", encoding="utf-8") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
        if os.path.getsize(LOGF) > 2_000_000: os.replace(LOGF, LOGF + ".old")
    except Exception: pass


def prefs(upd=None):
    try:
        with open(PREFS, encoding="utf-8") as f: p = json.load(f)
    except Exception: p = {}
    if upd:
        p.update(upd)
        tmp = f"{PREFS}.{os.getpid()}.tmp"           # ghi file tạm rồi thay 1 lần: cửa sổ khác đang đọc không bao giờ thấy file dở (mất cài đặt)
        try:
            with open(tmp, "w", encoding="utf-8") as f: json.dump(p, f)
            os.replace(tmp, PREFS)
        except Exception:
            try:
                with open(PREFS, "w", encoding="utf-8") as f: json.dump(p, f)
            except Exception: pass
            try: os.remove(tmp)
            except Exception: pass
    return p


# ================================================================ HTTP + Supabase
OUTDATED = {"v": False, "min": ""}               # máy chủ báo app đã cũ (APP_OUTDATED) / admin đặt bản tối thiểu (settings.min_app_pc)


def ver_lt(a, b):
    """'1.13' < '1.14' (so từng số, thiếu số = 0: '1.14' = '1.14.0' — giống máy chủ). Chuỗi lạ → False (không chặn nhầm)."""
    pa, pb = [int(x) for x in re.findall(r"\d+", str(a or ""))], [int(x) for x in re.findall(r"\d+", str(b or ""))]
    if not pa or not pb:
        return False
    n = max(len(pa), len(pb))
    return pa + [0] * (n - len(pa)) < pb + [0] * (n - len(pb))


def must_update():
    """App ĐÓNG GÓI bản thấp hơn mức admin đặt (hoặc máy chủ đã báo APP_OUTDATED) → bắt buộc cập nhật mới dùng tiếp."""
    return FROZEN and (OUTDATED["v"] or (bool(OUTDATED["min"]) and ver_lt(APP_VER, OUTDATED["min"])))


ERRORS = {
    "APP_OUTDATED": "Bản app này đã cũ — phải cập nhật bản mới nhất mới dùng tiếp được (bấm Cập nhật ngay trên danh sách máy).",
    "Invalid login credentials": "Sai email hoặc mật khẩu.", "Email not confirmed": "Email chưa xác nhận — mở hộp thư để xác nhận.",
    "SESSION_EXPIRED": "Phiên đăng nhập hết hạn, hãy đăng nhập lại.", "NOT_LOGGED_IN": "Hãy đăng nhập.",
    "NOT_ALLOWED": "Bạn không có quyền mở máy này.", "NOT_FOUND": "Không tìm thấy máy.", "MAINTENANCE": "Hệ thống đang bảo trì.",
    "SWITCH_EXPIRING": "Máy còn dưới 30 phút — gia hạn trước rồi hãy đổi Android.", "SWITCH_BUSY": "Máy đang nâng cấp / gia hạn — chờ 1–2 phút rồi đổi Android.",
    "SWITCHING": "Máy đang đổi Android — chờ máy mới tạo xong (2–5 phút).", "SWITCH_SAME": "Máy đang chạy bản Android này rồi.",
    "SWITCH_LIMIT": "Mỗi tài khoản đổi Android tối đa 3 lần trong 24 giờ.", "NO_PHONE": "Không tìm thấy máy (hoặc máy không phải của bạn).",
    "PHONE_NOT_ACTIVE": "Máy phải đang chạy mới làm được việc này.", "PHONE_LOCKED": "Máy đang bị khoá.", "BAD_ANDROID": "Bản Android này chưa bán.",
    "SERVER_OFFLINE": "Máy chủ bản Android này đang bảo trì — thử lại sau.", "OUT_OF_CAPACITY": "Máy chủ bản Android này đang hết chỗ — chọn bản khác hoặc thử lại sau.",
}


class ApiError(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code = code


def http(method, url, body=None, headers=None, timeout=25):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    h = {"Accept": "application/json", "User-Agent": f"BlueRobloxPC/{APP_VER}"}
    if isinstance(body, (dict, list)): h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(0, "Không có kết nối mạng.") from e


def err_text(code, raw):
    try:
        j = json.loads(raw.decode("utf-8") or "{}")
        m = next((j.get(k) for k in ("error_description", "msg", "message", "error") if j.get(k)), "") if isinstance(j, dict) else ""
    except Exception:
        m = ""
    if "APP_OUTDATED" in (m or ""): OUTDATED["v"] = True
    best = max((k for k in ERRORS if k in (m or "")), key=len, default=None)       # mã DÀI NHẤT khớp (PROMO_TOO_MANY thắng TOO_MANY)
    return ERRORS[best] if best else (m or f"Lỗi {code}")


def code_text(c):
    """Mã lỗi trong kết quả JSON (VD {"ok": false, "err": "PROMO_EXPIRED"}) → câu dễ hiểu."""
    return err_text(0, json.dumps({"message": str(c or "")}).encode())


class FileLock:
    def __init__(self, path): self.path = path; self.f = None
    def __enter__(self):
        self.f = open(self.path, "a+")
        for _ in range(200):
            try:
                if os.name == "nt":
                    import msvcrt; self.f.seek(0); msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl; fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                time.sleep(0.05)
        return self
    def __exit__(self, *a):
        try:
            if os.name == "nt":
                import msvcrt; self.f.seek(0); msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl; fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        except OSError: pass
        self.f.close()


class Auth:
    """Phiên đăng nhập dùng chung giữa cửa sổ danh sách và các cửa sổ máy (khoá file khi làm mới mã)."""
    def __init__(self): self.s = self._load()

    def _load(self):
        try: return json.load(open(SESS, encoding="utf-8"))
        except Exception: return {}

    def _save(self, j):
        self.s = {"access": j.get("access_token", ""), "refresh": j.get("refresh_token") or self.s.get("refresh", ""),
                  "exp": time.time() + float(j.get("expires_in") or 3600) - 90,
                  "uid": (j.get("user") or {}).get("id") or self.s.get("uid", ""), "email": (j.get("user") or {}).get("email") or self.s.get("email", "")}
        tmp = SESS + ".tmp"; json.dump(self.s, open(tmp, "w", encoding="utf-8")); os.replace(tmp, SESS)

    @property
    def logged_in(self): return bool(self._load().get("refresh"))

    @property
    def email(self): return self.s.get("email", "")

    @property
    def uid(self): return self.s.get("uid", "")

    def login(self, email, pw):
        code, raw = http("POST", SB + "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": pw}, {"apikey": KEY})
        if code != 200: raise ApiError(code, err_text(code, raw))
        with FileLock(LOCKF): self._save(json.loads(raw))

    def logout(self):
        self.s = {}
        try: os.remove(SESS)
        except OSError: pass

    def token(self, force=False):
        with FileLock(LOCKF):
            self.s = self._load()                     # cửa sổ khác có thể vừa làm mới
            if not force and self.s.get("access") and self.s.get("exp", 0) > time.time(): return self.s["access"]
            if not self.s.get("refresh"): raise ApiError(401, "Hãy đăng nhập.")
            code, raw = http("POST", SB + "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.s["refresh"]}, {"apikey": KEY})
            if code != 200:
                if code in (400, 401): self.logout(); raise ApiError(401, "Phiên đăng nhập hết hạn, hãy đăng nhập lại.")
                raise ApiError(code, err_text(code, raw))
            self._save(json.loads(raw))
            return self.s["access"]

    def rest(self, path):
        code, raw = http("GET", SB + "/rest/v1/" + path, headers={"apikey": KEY, "Authorization": "Bearer " + self.token()})
        if code == 401:
            code, raw = http("GET", SB + "/rest/v1/" + path, headers={"apikey": KEY, "Authorization": "Bearer " + self.token(True)})
        if code >= 300: raise ApiError(code, err_text(code, raw))
        return json.loads(raw.decode("utf-8") or "null")

    def rpc(self, fn, args=None):
        code, raw = http("POST", SB + "/rest/v1/rpc/" + fn, args or {}, {"apikey": KEY, "Authorization": "Bearer " + self.token()})
        if code >= 300: raise ApiError(code, err_text(code, raw))
        t = raw.decode("utf-8").strip()
        return json.loads(t) if t else None

    def phones(self):
        own = self.rest(f"cloud_phones?user_id=eq.{self.uid}&status=in.(active,pending,expired,error)&order=created_at.asc&select=*") or []
        try:
            for p in self.rpc("cp_shared_with_me") or []: p["shared"] = True; own.append(p)
        except Exception: pass
        return own

    def cp(self, method, base, path, body=None):
        code, raw = http(method, f"{base}/cpapi/{path}", body if body is not None else ({} if method == "POST" else None),
                         {"Authorization": "Bearer " + self.token()}, timeout=60)
        if code >= 300: raise ApiError(code, err_text(code, raw))
        try: return json.loads(raw.decode("utf-8") or "{}")
        except Exception: return {}


class CpClient:
    """CÔNG CỤ MÁY (cpapi trên máy chủ đang giữ máy: cài APK, clone tab, khởi động lại…).
       Đi THẲNG tới máy chủ qua cổng phát hình (TLS, ghim đúng chứng chỉ như cửa sổ máy) — không cần tên miền / Cloudflare;
       không nối được mới đi qua tên miền của máy chủ (stream.api)."""
    def __init__(self, auth, pid):
        self.auth, self.pid = auth, str(pid); self.ep = None; self.good = None

    def endpoint(self):
        if self.ep is None: self.ep = self.auth.rpc("cloudphone_endpoint", {"p_id": self.pid}) or {}
        return self.ep

    def _routes(self):
        st = self.endpoint().get("stream") or {}; cert = str(st.get("cert") or "").lower().replace(":", "")
        rs = []
        if cert:
            for d in sorted(st.get("direct") or [], key=lambda d: 0 if d.get("lan") else 1):
                if d.get("host") and d.get("port"): rs.append(("d", str(d["host"]), int(d["port"]), cert, 0.8 if d.get("lan") else 4.0))
        api = str(st.get("api") or PHONE_API).rstrip("/")
        rs.append(("w", api if api.startswith("https://") else PHONE_API, 443, "", 12.0))
        if self.good in rs: rs.remove(self.good); rs.insert(0, self.good)
        return rs

    @staticmethod
    def _open(r):
        import http.client, ssl
        kind, host, port, cert, cto = r
        if kind == "w":
            u = urllib.parse.urlparse(host)
            c = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=cto, context=ssl.create_default_context()); c.connect()
            return c, (u.path.rstrip("/")[:-6] if u.path.rstrip("/").endswith("/cpapi") else u.path.rstrip("/"))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        c = http.client.HTTPSConnection(host, port, timeout=cto, context=ctx); c.connect()
        if hashlib.sha256(c.sock.getpeercert(binary_form=True) or b"").hexdigest() != cert:      # không đúng máy chủ → không gửi gì
            c.close(); raise ssl.SSLError("sai chứng chỉ máy chủ")
        return c, ""

    def request(self, method, path, body=None, ctype="application/json", timeout=120):
        """path: 'reboot', 'clone', 'apps', 'upload?…' (theo máy này) hoặc '/job?id=…'. Trả (mã HTTP, bytes)."""
        sub = path.lstrip("/") if path.startswith("/") else f"{self.pid}/{path}"
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        hdr = {"Authorization": "Bearer " + self.auth.token(), "Accept": "application/json", "User-Agent": f"BlueRobloxPC/{APP_VER}", "Connection": "close"}
        if data is not None: hdr["Content-Type"] = ctype
        last = None
        for r in self._routes():
            try: c, prefix = self._open(r)
            except Exception as e:                       # chưa nối được (chưa gửi gì) → thử đường sau
                last = e; continue
            try:
                c.sock.settimeout(timeout)
                c.request(method, f"{prefix}/cpapi/{sub}", body=data, headers=hdr); res = c.getresponse(); raw = res.read()
            except OSError as e:
                raise ApiError(0, "Mất kết nối tới máy chủ, thử lại.") from e
            finally:
                c.close()
            self.good = r
            return res.status, raw
        log("cpapi: không nối được", repr(last))
        raise ApiError(0, "Không nối được tới máy chủ của máy này — kiểm tra mạng rồi thử lại.")

    def json(self, method, path, body=None, ctype="application/json", timeout=120):
        code, raw = self.request(method, path, body, ctype, timeout)
        try: j = json.loads(raw.decode("utf-8") or "{}")
        except Exception: j = {}
        if not isinstance(j, dict): j = {"data": j}
        if code >= 300 and not (code == 409 and "size" in j):
            if code == 401: raise ApiError(401, "Phiên đăng nhập hết hạn, hãy đăng nhập lại.")
            raise ApiError(code, j.get("error") or err_text(code, raw))
        return j

    def wait_job(self, jid, on_msg=None, limit=1800):
        t0 = time.time()
        while time.time() - t0 < limit:
            try: j = self.json("GET", f"/job?id={jid}", timeout=30)
            except ApiError as e:
                if e.code in (0, 502, 503, 504): time.sleep(3); continue
                raise
            if on_msg and j.get("msg") and j.get("state") == "running": on_msg(j["msg"])
            if j.get("state") == "done": return j.get("msg") or "Xong."
            if j.get("state") == "error": raise ApiError(0, j.get("msg") or "Có lỗi.")
            time.sleep(2)
        raise ApiError(0, "Việc chạy quá lâu — kiểm tra lại máy sau ít phút.")

    def upload(self, fpath, on_prog=None):
        """Tải file lên máy chủ từng phần 8MB (đứt mạng thì nối tiếp đúng chỗ) → trả mã việc nền (cài / chép vào máy)."""
        name = os.path.basename(fpath); total = os.path.getsize(fpath); upid = secrets.token_hex(8); off = 0; CH = 8 * 1024 * 1024
        if total <= 0: raise ApiError(0, "File rỗng.")
        with open(fpath, "rb") as f:
            while True:
                f.seek(off); chunk = f.read(min(CH, total - off))
                q = urllib.parse.urlencode({"id": upid, "name": name, "total": total, "off": off})
                for tries in range(4):
                    try: j = self.json("POST", f"upload?{q}", chunk, "application/octet-stream", timeout=300); break
                    except ApiError as e:
                        if e.code not in (0, 502, 503, 504) or tries == 3: raise
                        time.sleep(2 + tries * 2)
                off = int(j.get("size", off + len(chunk)))
                if on_prog: on_prog(min(off, total), total)
                if j.get("job"): return j["job"]
                if off >= total: raise ApiError(0, "Máy chủ chưa nhận đủ file — thử lại.")


# ================================================================ Windows: đăng ký link blueroblox:// + bộ nhớ copy
def register_protocol():
    if os.name != "nt": return
    try:
        import winreg
        cmd = f'"{sys.executable}" "%1"' if FROZEN else f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(__file__)}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\blueroblox") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:CloudBlue"); winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\blueroblox\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    except Exception as e:
        log("register_protocol:", e)


def clip_get():
    if os.name == "nt":
        try:
            import ctypes
            u, k = ctypes.windll.user32, ctypes.windll.kernel32
            u.GetClipboardData.restype = ctypes.c_void_p; k.GlobalLock.restype = ctypes.c_void_p; k.GlobalLock.argtypes = [ctypes.c_void_p]
            k.GlobalUnlock.argtypes = [ctypes.c_void_p]
            if not u.OpenClipboard(None): return ""
            try:
                h = u.GetClipboardData(13)
                if not h: return ""
                p = k.GlobalLock(h)
                try: return ctypes.wstring_at(p) if p else ""
                finally: k.GlobalUnlock(h)
            finally: u.CloseClipboard()
        except Exception: return ""
    try:
        import pygame; return pygame.scrap.get_text() or ""
    except Exception: return ""


def clip_put(text):
    if os.name == "nt":
        try:
            import ctypes
            u, k = ctypes.windll.user32, ctypes.windll.kernel32
            k.GlobalAlloc.restype = ctypes.c_void_p; k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            k.GlobalLock.restype = ctypes.c_void_p; k.GlobalLock.argtypes = [ctypes.c_void_p]; k.GlobalUnlock.argtypes = [ctypes.c_void_p]
            u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]; u.SetClipboardData.restype = ctypes.c_void_p
            data = (text + "\0").encode("utf-16-le")
            h = k.GlobalAlloc(0x0042, len(data))
            p = k.GlobalLock(h); ctypes.memmove(p, data, len(data)); k.GlobalUnlock(h)
            if u.OpenClipboard(None):
                try: u.EmptyClipboard(); u.SetClipboardData(13, h)
                finally: u.CloseClipboard()
            return
        except Exception: pass
    try:
        import pygame; pygame.scrap.put_text(text)
    except Exception: pass


def spawn_viewer(pid, mode="--view"):
    args = [sys.executable, mode, pid] if FROZEN else [sys.executable, os.path.abspath(__file__), mode, pid]
    kw = {}
    if os.name == "nt": kw["creationflags"] = 0x00000008 | 0x00000200       # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(args, close_fds=True, **kw)


def spawn_tools(pid):
    """Cửa sổ Công cụ (xoay màn, độ rộng, cài APK, ứng dụng, clone tab…) của 1 máy — tiến trình riêng, mở từ thanh bên cửa sổ máy."""
    spawn_viewer(pid, "--tools")


def pictures_dir():
    """Thư mục Ảnh (Pictures) của Windows — kể cả khi đã chuyển sang OneDrive / ổ khác — + \\CloudBlue."""
    p = ""
    if os.name == "nt":
        try:
            import ctypes, uuid
            from ctypes import wintypes as wt
            class GUID(ctypes.Structure):
                _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]
            g = GUID(); ctypes.memmove(ctypes.byref(g), uuid.UUID("33E28130-4E1E-4676-835A-98395C3BC3BB").bytes_le, 16)   # FOLDERID_Pictures
            res = ctypes.c_wchar_p(); sh = ctypes.windll.shell32
            sh.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wt.DWORD, wt.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if sh.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(res)) == 0:
                p = res.value or ""; ctypes.windll.ole32.CoTaskMemFree(res)
        except Exception as e:
            log("pictures_dir:", e); p = ""
    d = os.path.join(p or os.path.join(os.path.expanduser("~"), "Pictures"), "CloudBlue")
    os.makedirs(d, exist_ok=True)
    return d


def shot_path():
    t = time.time()
    return os.path.join(pictures_dir(), time.strftime("cloudphone_%Y%m%d_%H%M%S", time.localtime(t)) + f"_{int(t * 1000) % 1000:03d}.png")


def open_folder(fp):
    """Mở thư mục chứa file (Windows: chọn sẵn file trong Explorer)."""
    try:
        if os.name == "nt": subprocess.Popen(["explorer", "/select,", os.path.normpath(fp)])
        else: webbrowser.open("file://" + os.path.dirname(os.path.abspath(fp)))
    except Exception as e: log("open_folder:", e)


def work_area(x=None, y=None):
    """Vùng làm việc (x, y, rộng, cao — đã trừ thanh tác vụ) của màn hình máy tính chứa điểm (x, y); không ghi điểm → màn hình chính."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes as wt
            class MI(ctypes.Structure):
                _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]
            u = ctypes.windll.user32
            u.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]; u.MonitorFromPoint.restype = ctypes.c_void_p
            u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MI)]; u.GetMonitorInfoW.restype = wt.BOOL
            hm = u.MonitorFromPoint(wt.POINT(int(x or 0), int(y or 0)), 1 if x is None else 2)   # 1 = màn hình chính · 2 = màn hình gần nhất
            mi = MI(); mi.cbSize = ctypes.sizeof(MI)
            if hm and u.GetMonitorInfoW(hm, ctypes.byref(mi)):
                r = mi.rcWork
                if r.right > r.left and r.bottom > r.top: return (r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception as e: log("work_area:", e)
    try:
        import pygame
        sw, sh = pygame.display.get_desktop_sizes()[0]
    except Exception: sw, sh = 1280, 800
    return (0, 0, sw, sh - 48)


def orient(wh): return "land" if wh[0] > wh[1] else "port"


def fit_geometry(vw, vh, area, bar, cur=None, prev=None, keep=None):
    """Cỡ + chỗ cửa sổ máy (x, y, rộng, cao — tính cả thanh công cụ) cho hình máy vw×vh.
       area = vùng làm việc của màn hình máy tính (x, y, rộng, cao). cur = cửa sổ hiện tại (x, y, rộng, cao).
       prev = (rộng, cao) hình lúc chỉnh cỡ lần trước — không có → lần đầu: cao ~90% màn hình, đặt giữa màn hình.
       Có prev (máy XOAY dọc ↔ ngang): giữ cạnh dài của hình (cửa sổ xoay theo, hình không to / nhỏ đi) + giữ tâm cửa sổ.
       keep = (rộng, cao) vùng hình đã dùng cho hướng này lần trước → xoay qua lại trả đúng cỡ khách đã kéo."""
    ax, ay, aw, ah = area; TOP = 34                         # chừa thanh tiêu đề cửa sổ
    mw, mh = max(200, aw * 0.97 - bar), max(150, ah - TOP - 8)
    if keep and keep[0] > 0 and keep[1] > 0 and abs(keep[0] / keep[1] - vw / vh) < 0.03 * vw / vh: w, h = keep
    elif cur and prev:
        sc = min(max(1, cur[2] - bar) / prev[0], max(1, cur[3]) / prev[1]); L = max(prev) * sc
        w, h = vw * L / max(vw, vh), vh * L / max(vw, vh)
    else:
        h = min(mh, ah * 0.9); w = h * vw / vh
    k = min(1.0, mw / w, mh / h); w, h = max(160, int(w * k)), max(120, int(h * k))
    W, H = w + bar, h
    if cur and prev: x, y = int(cur[0] + cur[2] / 2 - W / 2), int(cur[1] + cur[3] / 2 - H / 2)
    else: x, y = ax + (aw - W) // 2, ay + TOP + (ah - TOP - H) // 2
    x = max(ax, min(x, ax + aw - W)); y = max(ay + TOP, min(y, ay + ah - H))
    return x, y, W, H


def wrap_text(font, text, maxw):
    """Cắt chữ thành nhiều dòng vừa maxw điểm ảnh (font pygame)."""
    out = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split(" "):
            t = (cur + " " + w).strip()
            if cur and font.size(t)[0] > maxw: out.append(cur); cur = w
            else: cur = t
        out.append(cur)
    return out


# ================================================================ CỬA SỔ MÁY (pygame + PyAV)
AK = {  # phím máy tính → mã phím Android
    "backspace": 67, "delete": 112, "return": 66, "enter": 66, "tab": 61, "escape": 111, "up": 19, "down": 20, "left": 21, "right": 22,
    "home": 122, "end": 123, "page up": 92, "page down": 93, "insert": 124,
}
META_CTRL, META_SHIFT, META_ALT = 0x1000, 0x1, 0x2
QUALITIES = [("auto", "Tự động"), ("hd", "Siêu nét"), ("bal", "Cân bằng"), ("eco", "Tiết kiệm")]
TOOLS = [("back", "Quay lại"), ("home", "Màn chính"), ("recents", "Đa nhiệm"), ("volup", "Âm +"), ("voldown", "Âm −"),
         ("rotate", "Xoay"), ("shot", "Chụp màn"), ("paste", "Dán chữ"), ("tools", "Công cụ"), ("quality", "Chất lượng"),
         ("full", "Toàn màn"), ("hide", "Ẩn thanh"), ("info", "Thông số")]
BAR, BAR_MIN = 72, 14              # thanh công cụ bên phải · khi ẩn còn dải mỏng (bấm để hiện lại)
C_BG, C_BAR, C_ICON, C_HOT, C_TXT, C_DIM, C_ACC = (8, 12, 22), (17, 24, 39), (210, 220, 235), (47, 123, 255), (235, 240, 248), (130, 142, 160), (47, 123, 255)


class Viewer:
    def __init__(self, pid):
        self.pid = pid; self.auth = Auth()
        self.lock = threading.Lock(); self.frame = None; self.vw = self.vh = 0
        self.state = ("connecting", "Đang kết nối…"); self.stats = {}; self.ping = 0; self.path = ""
        self.show_info = bool(prefs().get("info")); self.q = prefs().get("q", "auto")
        self.name = "CloudBlue"; self.dec = None; self.need_key = True; self.last_kf_req = 0
        self.dec_errors = 0; self.mouse_down = False; self.kicked = False; self.cli = None; self.hover = None
        self.fps_n = 0; self.fps_t = time.time(); self.fps_show = 0.0
        self._ui_key = None; self._ui_surf = None; self._ui_tex = None
        self.bar_on = not prefs().get("bar_hidden")     # "Ẩn thanh" (F10): thanh công cụ thu thành dải mỏng bên phải, bấm dải để hiện lại
        self.full = False; self.fit = None; self.geo = {}  # fit = (rộng, cao) hình lúc chỉnh cỡ cửa sổ lần trước · geo = cỡ hình đã dùng cho từng hướng
        self.notice = None; self.notice_rect = None       # (chữ, hết hạn lúc, việc khi bấm vào) — thông báo nhỏ trên hình
        self.cp = None; self.gen = 0                      # cp = cổng công cụ máy (xoay, chụp màn…) · gen: tải lại hình thì bỏ sự kiện của luồng cũ

    # ---------- mạng ----------
    def connect(self):
        import brstream
        g0 = self.gen                                    # trong lúc hỏi máy chủ mà khách bấm F5 → lượt nối này bỏ (lượt mới lo)
        ep = self.auth.rpc("cloudphone_endpoint", {"p_id": self.pid}) or {}
        if g0 != self.gen: return
        self.name = ep.get("name") or self.name
        if ep.get("status") and ep.get("status") != "active":
            raise ApiError(0, "Máy chưa chạy (đang tạo, tạm dừng hoặc đã hết hạn).")
        if self.cp is None: self.cp = CpClient(self.auth, self.pid); self.cp.ep = ep
        pref = prefs().get("path_" + str(ep.get("node")))
        self.gen += 1; g = self.gen
        cli = brstream.StreamClient(ep, lambda force=False: self.auth.token(force), self.pid,
                                    lambda k, d, g=g: self.on_event(k, d) if g == self.gen else None, q=self.q, client="pc",
                                    prefer=tuple(pref) if pref else None)
        self.node = ep.get("node")
        old, self.cli = self.cli, cli                    # luôn chỉ 1 luồng hình: luồng cũ (nếu có) đóng hẳn, không chạy ngầm đá phiên mới
        if old is not None and old is not cli: threading.Thread(target=old.close, daemon=True).start()
        cli.start()

    def _cp(self):
        if self.cp is None: self.cp = CpClient(self.auth, self.pid)
        return self.cp

    def on_event(self, k, d):
        if k == "video": self._decode(*d)
        elif k == "welcome":
            self.name = d.get("name") or self.name; self._reset_decoder(); self._post()
        elif k == "size": self._reset_decoder(); self._post()        # máy xoay / đổi cỡ: cửa sổ tự xoay theo khi có khung hình mới (run)
        elif k == "clip": clip_put(d)
        elif k == "stats": self.stats = d; self._post()
        elif k == "ping": self.ping = d
        elif k == "state":
            if d[0] == "closed" and self.state[0] in ("kicked", "error"): return      # giữ thông báo lỗi / "mở ở nơi khác"
            self.state = d
            if d[0] == "connected":
                self.path = d[1]
                if self.cli and self.cli.prefer: prefs({"path_" + str(self.node): list(self.cli.prefer)})
                if not getattr(self, "_blue_tried", False):            # 💎 nhiệm vụ "mở máy đám mây" (SQL v27) — mỗi ngày 1 lần
                    self._blue_tried = True
                    threading.Thread(target=blue_play_task, args=(self.auth, lambda t: self._say(t, 5.0)), daemon=True).start()
            if d[0] in ("reconnecting", "connecting"): self.need_key = True
            if d[0] == "kicked": self.kicked = True
            self._post()

    # ---------- giải mã ----------
    def _reset_decoder(self):
        import av
        ctx = av.CodecContext.create("h264", "r")
        try: ctx.thread_count = 1
        except Exception: pass
        try: ctx.thread_type = "SLICE"
        except Exception: pass
        try: ctx.options = {"flags": "+low_delay", "flags2": "+fast"}
        except Exception: pass
        self.dec = ctx; self.need_key = True

    def _decode(self, flags, pts, data):
        import av
        if self.dec is None: self._reset_decoder()
        if self.need_key and not (flags & 1): return self._ask_key()
        try:
            frames = self.dec.decode(av.Packet(data))
        except Exception as e:
            self.dec_errors += 1; log("decode:", e); self._reset_decoder(); return self._ask_key()
        self.need_key = False
        for fr in frames:
            arr = fr.to_ndarray(format="rgb24")
            with self.lock: self.frame = arr; self.vw, self.vh = fr.width, fr.height
            self.fps_n += 1
            self._post(new_frame=True)

    def _ask_key(self):
        if time.time() - self.last_kf_req > 1.0 and self.cli:
            self.last_kf_req = time.time(); self.cli.keyframe()

    def _post(self, new_frame=False):
        try:
            import pygame
            pygame.event.post(pygame.event.Event(self.EV_FRAME if new_frame else self.EV_UI))
        except Exception: pass

    # ---------- vòng chính ----------
    def run(self):
        import pygame
        pygame.init()
        self.EV_FRAME = pygame.event.custom_type(); self.EV_UI = pygame.event.custom_type()
        try: pygame.scrap.init()
        except Exception: pass
        self.font = pygame.font.SysFont("segoeui,arial", 15); self.font_s = pygame.font.SysFont("segoeui,arial", 12); self.font_b = pygame.font.SysFont("segoeui,arial", 18, bold=True)
        sw, sh = (pygame.display.get_desktop_sizes() or [(1280, 800)])[0]
        vh = int(sh * 0.82); vw = int(vh * 9 / 16)
        self.gpu = False
        try:
            from pygame._sdl2.video import Window, Renderer, Texture
            self.Texture = Texture
            self.win = Window("CloudBlue", size=(vw + self._bw(), vh), resizable=True)
            self.ren = Renderer(self.win, vsync=False, accelerated=1)
            self.gpu = True
        except Exception as e:
            log("GPU renderer không dùng được, dùng CPU:", e)
            self.screen = pygame.display.set_mode((vw + self._bw(), vh), pygame.RESIZABLE)
        pygame.key.start_text_input()
        threading.Thread(target=self._connect_bg, daemon=True).start()
        clock = pygame.time.Clock(); running = True; dirty = True
        while running:
            evs = [pygame.event.wait(250)] + pygame.event.get()
            for e in evs:
                if e.type in (pygame.QUIT, getattr(pygame, "WINDOWCLOSE", -1)): running = False
                elif e.type == self.EV_FRAME: dirty = True
                elif e.type == self.EV_UI: dirty = True
                elif e.type in (getattr(pygame, "WINDOWRESIZED", -1), getattr(pygame, "VIDEORESIZE", -1), getattr(pygame, "WINDOWEXPOSED", -1)): dirty = True
                else:
                    dirty |= self._input(e, pygame)
            if self.vw and self._need_fit(): self._fit_window(pygame); dirty = True
            n = self.notice                                   # thông báo do luồng khác đặt / xoá → đọc 1 lần
            if n and time.time() >= n[1]: self.notice = None; dirty = True
            if dirty: self._draw(pygame); dirty = False
            clock.tick(500)
        if self.cli: self.cli.close()
        pygame.quit()

    def _connect_bg(self):
        try: self.connect()
        except Exception as e:
            self.state = ("error", str(e)); log("connect:", traceback.format_exc()); self._post()

    def _need_fit(self):
        """Chưa chỉnh cỡ lần nào, hoặc hình đổi tỉ lệ (máy XOAY dọc ↔ ngang: bấm Xoay, mở game / bản clone cần màn ngang…)."""
        if self.fit is None: return True
        if self.full or not self.vh or not self.fit[1]: return False      # toàn màn hình: hình tự vừa; thoát toàn màn mới chỉnh cửa sổ
        a0, a1 = self.fit[0] / self.fit[1], self.vw / self.vh
        return abs(a0 - a1) > 0.03 * a1

    def _fit_window(self, pygame):
        """Chỉnh cỡ cửa sổ theo hình máy. Lần đầu: to gần hết màn hình. Máy xoay dọc ↔ ngang: cửa sổ XOAY THEO, giữ độ to của hình
           (không phải tự kéo lại cửa sổ, không phải nghiêng đầu); xoay về hướng cũ → trả đúng cỡ khách đã kéo cho hướng đó."""
        vw, vh = self.vw, self.vh
        if not vw or not vh: return
        prev, self.fit = self.fit, (vw, vh)
        try:
            bw = self._bw()
            if self.gpu: (x, y), (W, H) = self.win.position, self.win.size
            else: (x, y), (W, H) = (0, 0), self.screen.get_size()
            cur = (x, y, W, H)
            if prev:                                            # nhớ cỡ hình của hướng cũ (khách có thể đã kéo cửa sổ)
                sc = min(max(1, W - bw) / prev[0], max(1, H) / prev[1])
                self.geo[orient(prev)] = (int(prev[0] * sc), int(prev[1] * sc))
            area = work_area(x + W // 2, y + H // 2) if (self.gpu and prev) else work_area()
            nx, ny, nW, nH = fit_geometry(vw, vh, area, bw, cur if prev else None, prev, self.geo.get(orient((vw, vh))))
            title = f"{self.name} — CloudBlue"
            if self.gpu:
                self.win.size = (nW, nH); self.win.position = (nx, ny); self.win.title = title
            else:
                self.screen = pygame.display.set_mode((nW, nH), pygame.RESIZABLE); pygame.display.set_caption(title)
        except Exception as e: log("fit:", e)

    def _bw(self): return BAR if self.bar_on else BAR_MIN

    def _size(self):
        if self.gpu: return self.win.size
        return self.screen.get_size()

    def _video_rect(self):
        W, H = self._size(); aw = max(1, W - self._bw())
        if not self.vw: return (0, 0, aw, H)
        sc = min(aw / self.vw, H / self.vh); w, h = int(self.vw * sc), int(self.vh * sc)
        return ((aw - w) // 2, (H - h) // 2, w, h)

    # ---------- vẽ ----------
    def _draw(self, pygame):
        W, H = self._size()
        with self.lock: arr = self.frame
        surf_v = pygame.image.frombuffer(arr if arr.flags["C_CONTIGUOUS"] else arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGB") if arr is not None else None
        key = (W, H, self.hover, self.q, tuple(self.state[:2]), self.show_info, surf_v is not None,
               int(self.fps_show) if self.show_info else 0, self.stats.get("kbps") if self.show_info else 0, self.ping if self.show_info else 0, self.path,
               self.bar_on, (self.notice or ("",))[0])
        if key != self._ui_key:                          # lớp nút / chữ chỉ vẽ lại khi có thay đổi (đỡ tốn CPU mỗi khung)
            ui = pygame.Surface((W, H), pygame.SRCALPHA); ui.fill((0, 0, 0, 0))
            self._draw_bar(pygame, ui, W, H)
            self._draw_overlay(pygame, ui, W, H, surf_v is not None)
            self._ui_surf = ui; self._ui_key = key
            self._ui_tex = self.Texture.from_surface(self.ren, ui) if self.gpu else None
        x, y, w, h = self._video_rect()
        if self.gpu:
            r = self.ren; r.draw_color = C_BG; r.clear()
            if surf_v is not None: self.Texture.from_surface(r, surf_v).draw(dstrect=(x, y, w, h))
            self._ui_tex.draw(dstrect=(0, 0, W, H))
            r.present()
        else:
            s = self.screen; s.fill(C_BG)
            if surf_v is not None: s.blit(pygame.transform.smoothscale(surf_v, (w, h)) if (w, h) != surf_v.get_size() else surf_v, (x, y))
            s.blit(self._ui_surf, (0, 0)); pygame.display.flip()
        if time.time() - self.fps_t >= 1:
            self.fps_show = self.fps_n / (time.time() - self.fps_t); self.fps_n = 0; self.fps_t = time.time()

    def _tool_rects(self, W, H):
        if not self.bar_on: return []
        n = len(TOOLS); step = max(22, min(64, (H - 16) // n)); top = max(6, (H - step * n) // 2)
        return [(name, label, (W - BAR + 6, top + i * step, BAR - 12, step - 6)) for i, (name, label) in enumerate(TOOLS)]

    def _draw_bar(self, pygame, s, W, H):
        if not self.bar_on:                              # thanh đang ẩn: dải mỏng có mũi tên ‹ — bấm vào để hiện lại
            hot = self.hover == "showbar"; x0 = W - BAR_MIN; cy = H // 2
            pygame.draw.rect(s, ((47, 123, 255, 150) if hot else C_BAR + (235,)), (x0, 0, BAR_MIN, H))
            pygame.draw.polygon(s, C_TXT if hot else C_ICON, [(x0 + 10, cy - 8), (x0 + 4, cy), (x0 + 10, cy + 8)])
            return
        pygame.draw.rect(s, C_BAR + (255,), (W - BAR, 0, BAR, H))
        for name, label, (x, y, w, h) in self._tool_rects(W, H):
            hot = self.hover == name; small = h < 38             # cửa sổ thấp: chỉ còn biểu tượng (bỏ chữ dưới nút)
            if hot: pygame.draw.rect(s, (47, 123, 255, 70), (x, y, w, h), border_radius=10)
            cx, cy = x + w // 2, y + (h // 2 if small else int(h * 0.38)); c = C_HOT if hot else C_ICON
            r = max(6, min(9, h // 3)) if small else max(7, min(11, h // 5))
            if name == "back": pygame.draw.polygon(s, c, [(cx + r, cy - r), (cx - r, cy), (cx + r, cy + r)], 2)
            elif name == "home": pygame.draw.circle(s, c, (cx, cy), r, 2)
            elif name == "recents": pygame.draw.rect(s, c, (cx - r, cy - r, 2 * r, 2 * r), 2, border_radius=3)
            elif name in ("volup", "voldown"):
                pygame.draw.polygon(s, c, [(cx - r, cy - 4), (cx - r // 2, cy - 4), (cx + 1, cy - r), (cx + 1, cy + r), (cx - r // 2, cy + 4), (cx - r, cy + 4)], 2)
                pygame.draw.line(s, c, (cx + 5, cy), (cx + r + 3, cy), 2)
                if name == "volup": pygame.draw.line(s, c, (cx + 5 + (r - 2) // 2, cy - (r - 2) // 2), (cx + 5 + (r - 2) // 2, cy + (r - 2) // 2), 2)
            elif name == "rotate":
                pygame.draw.arc(s, c, (cx - r, cy - r, 2 * r, 2 * r), 0.6, 5.6, 2); pygame.draw.polygon(s, c, [(cx + r - 1, cy - 7), (cx + r + 4, cy - 1), (cx + r - 6, cy - 1)])
            elif name == "paste":
                pygame.draw.rect(s, c, (cx - r + 2, cy - r + 2, 2 * r - 4, 2 * r), 2, border_radius=3); pygame.draw.rect(s, c, (cx - 4, cy - r - 1, 8, 5), 0, border_radius=2)
            elif name == "tools":                                  # 4 ô vuông = công cụ (cài APK, clone tab…)
                q = max(3, r - 3)
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    pygame.draw.rect(s, c, (cx + (1 if dx > 0 else -q - 1), cy + (1 if dy > 0 else -q - 1), q, q), 2, border_radius=2)
            elif name == "quality":
                t = self.font_s.render({"auto": "AUTO", "hd": "HD", "bal": "CB", "eco": "TK"}[self.q], True, c); s.blit(t, t.get_rect(center=(cx, cy)))
            elif name == "full":
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    ax, ay = cx + dx * r, cy + dy * r
                    pygame.draw.line(s, c, (ax, ay), (ax - dx * 6, ay), 2); pygame.draw.line(s, c, (ax, ay), (ax, ay - dy * 6), 2)
            elif name == "info":
                pygame.draw.circle(s, c, (cx, cy), r, 2); t = self.font_s.render("i", True, c); s.blit(t, t.get_rect(center=(cx, cy)))
            elif name == "shot":                                   # máy ảnh: thân + ống kính
                pygame.draw.rect(s, c, (cx - r, cy - r + 3, 2 * r, 2 * r - 4), 2, border_radius=3)
                pygame.draw.rect(s, c, (cx - 4, cy - r, 8, 4), 0, border_radius=1)
                pygame.draw.circle(s, c, (cx, cy + 1), max(3, r // 2), 2)
            elif name == "hide":                                   # » = thu thanh sang phải
                for off in (-4, 3):
                    pygame.draw.lines(s, c, False, [(cx + off - 3, cy - r + 2), (cx + off + 3, cy), (cx + off - 3, cy + r - 2)], 2)
            if small: continue
            lb = self.font_s.render(label if name != "quality" else dict(QUALITIES)[self.q], True, C_DIM if not hot else C_TXT)
            s.blit(lb, lb.get_rect(center=(x + w // 2, y + int(h * 0.80))))

    def _draw_overlay(self, pygame, s, W, H, has_video):
        st = self.state[0]; aw = W - self._bw()
        self.notice_rect = None; n = self.notice
        if n:                                            # thông báo nhỏ phía dưới hình (VD "Đang xoay ngang…", "Đã lưu ảnh…")
            lines = [ln for ln in wrap_text(self.font, n[0], max(120, min(aw - 60, 560))) if ln][:3]
            if lines:
                lh = self.font.get_height() + 4; bw_ = max(self.font.size(ln)[0] for ln in lines) + 28; bh = lh * len(lines) + 16
                x0, y0 = max(4, (aw - bw_) // 2), max(4, H - bh - 30)
                pygame.draw.rect(s, (10, 16, 30, 228), (x0, y0, bw_, bh), border_radius=12)
                if n[2]: pygame.draw.rect(s, C_ACC + (200,), (x0, y0, bw_, bh), 1, border_radius=12)   # bấm được → có viền
                for i, ln in enumerate(lines):
                    s.blit(self.font.render(ln, True, C_TXT), (x0 + 14, y0 + 8 + i * lh))
                self.notice_rect = (x0, y0, bw_, bh)
        if st != "connected" or not has_video:
            msg = self.state[1] if len(self.state) > 1 else ""
            if st == "connected" and not has_video: msg = "Đang lấy hình…"
            lines = [msg]
            if st == "kicked": lines = ["Máy đang được mở ở nơi khác.", "Bấm phím R hoặc bấm vào đây để mở lại tại đây."]
            if st == "error": lines = [msg, "Bấm phím R để thử lại."]
            box_h = 30 + 26 * len(lines); bw = min(aw - 40, 520)
            pygame.draw.rect(s, (10, 16, 30, 215), ((aw - bw) // 2, H // 2 - box_h // 2, bw, box_h), border_radius=14)
            for i, ln in enumerate(lines):
                t = (self.font_b if i == 0 else self.font).render(ln[:80], True, C_TXT if i == 0 else C_DIM)
                s.blit(t, t.get_rect(center=(aw // 2, H // 2 - box_h // 2 + 26 + 26 * i)))
        if self.show_info and st == "connected":
            d = self.stats
            txt = f"{self.fps_show:.0f} khung/s · {d.get('kbps', 0) / 1000:.1f} Mbps · trễ mạng {self.ping} ms · {self.path} · {str(d.get('enc', '')).upper()}"
            if d.get("drop"): txt += f" · bỏ {d['drop']}"
            t = self.font_s.render(txt, True, C_TXT)
            pygame.draw.rect(s, (0, 0, 0, 150), (6, 6, t.get_width() + 14, t.get_height() + 8), border_radius=8); s.blit(t, (13, 10))

    # ---------- chuột / bàn phím ----------
    def _norm(self, pos):
        x, y, w, h = self._video_rect()
        if not w or not h: return None
        nx, ny = (pos[0] - x) / w, (pos[1] - y) / h
        return (nx, ny) if 0 <= nx <= 1 and 0 <= ny <= 1 else None

    def _clamp(self, pos):
        x, y, w, h = self._video_rect()
        return (min(1, max(0, (pos[0] - x) / max(1, w))), min(1, max(0, (pos[1] - y) / max(1, h))))

    def _tool_at(self, pos):
        W, H = self._size()
        if not self.bar_on: return "showbar" if pos[0] >= W - BAR_MIN else None
        for name, _, (x, y, w, h) in self._tool_rects(W, H):
            if x <= pos[0] <= x + w and y <= pos[1] <= y + h: return name
        return None

    def _tool(self, name, pygame):
        c = self.cli
        if name in ("back", "home", "recents", "volup", "voldown") and c: c.cmd(name)
        elif name == "rotate": self._rotate()
        elif name == "shot": self._shot()
        elif name == "paste" and c:
            t = clip_get()
            if t: c.clip_set(t, True)
        elif name == "quality":
            i = [q for q, _ in QUALITIES].index(self.q); self.q = QUALITIES[(i + 1) % len(QUALITIES)][0]; prefs({"q": self.q})
            if c: c.quality(self.q)
        elif name == "full": self._toggle_full(pygame)
        elif name in ("hide", "showbar"): self._toggle_bar(pygame)
        elif name == "tools": spawn_tools(self.pid)
        elif name == "info": self.show_info = not self.show_info; prefs({"info": self.show_info})

    def _say(self, text, secs=3.0, action=None):
        self.notice = (str(text), time.time() + secs, action); self._post()

    def _rotate(self, to=None):
        """XOAY: khoá màn máy ngang / dọc qua cổng công cụ (mọi máy chủ đều có, xoay chắc chắn — không tự quay về như lệnh xoay cũ);
           không tới được thì gửi qua luồng hình. Hình đổi hướng → cửa sổ tự xoay theo (_fit_window)."""
        if self.state[0] != "connected" or not self.vw: return
        to = to or ("port" if self.vw > self.vh else "land"); land = to == "land"
        self._say("Đang xoay ngang…" if land else "Đang xoay dọc…", 4)
        def job():
            try: self._cp().json("POST", "rotate", {"to": to, "dir": 1 if land else 0}, timeout=20)
            except Exception as e:
                log("rotate:", e)
                if self.cli: self.cli.rotate(to)
            time.sleep(3.5)                              # 3,5 giây sau hình vẫn chưa đổi hướng → app đang mở chỉ chạy 1 hướng: nói rõ (khỏi tưởng nút hỏng)
            if ((self.vw or 0) > (self.vh or 0)) != land:
                self._say("Đã khoá màn NGANG. App đang mở chỉ chạy màn dọc nên chưa xoay — mở game / app hỗ trợ ngang là tự ngang." if land
                          else "Đã khoá màn DỌC. App đang mở chỉ chạy màn ngang nên chưa xoay.", 7)
            else:
                n = self.notice
                if n and n[0].startswith("Đang xoay"): self.notice = None; self._post()
        threading.Thread(target=job, daemon=True).start()

    def _shot(self):
        """CHỤP MÀN: ảnh gốc từ máy (nét, không nén) → thư mục Ảnh\\CloudBlue; máy chủ không chụp được thì lưu khung hình đang xem."""
        self._say("Đang chụp màn hình…", 10)
        with self.lock: arr = self.frame
        def job():
            fp, err = None, ""
            try:
                code, raw = self._cp().request("GET", "shot?fresh=1", timeout=40)
                if code == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n":
                    fp = shot_path()
                    with open(fp, "wb") as f: f.write(raw)
                else: err = err_text(code, raw)
            except Exception as e:
                err = str(e); log("shot:", e)
            if fp is None and arr is not None:
                try:
                    import pygame
                    fp = shot_path(); pygame.image.save(pygame.image.frombuffer(arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGB"), fp)
                except Exception as e:
                    log("shot local:", e); fp = None
            if fp: self._say(f"Đã lưu ảnh vào {os.path.dirname(fp)} — bấm vào đây để mở thư mục.", 8, lambda: open_folder(fp))
            else: self._say("Không chụp được màn hình" + (f": {err}" if err else "."), 6)
        threading.Thread(target=job, daemon=True).start()

    def _toggle_bar(self, pygame):
        """Ẩn / hiện thanh công cụ (F10). Cửa sổ hẹp / rộng ra đúng bằng phần thanh → hình giữ nguyên cỡ."""
        self.bar_on = not self.bar_on; self.hover = None; prefs({"bar_hidden": not self.bar_on})
        if not self.bar_on: self._say("Đã ẩn thanh công cụ — bấm dải mỏng bên phải hoặc phím F10 để hiện lại.", 4)
        if self.full: return
        d = (BAR - BAR_MIN) * (1 if self.bar_on else -1)
        try:
            if self.gpu: W, H = self.win.size; self.win.size = (max(160, W + d), H)
            else: W, H = self.screen.get_size(); self.screen = pygame.display.set_mode((max(160, W + d), H), pygame.RESIZABLE)
        except Exception as e: log("bar:", e)

    def _toggle_full(self, pygame):
        try:
            self.full = not self.full
            if self.full: self._say("Toàn màn hình — bấm phím F11 (hoặc nút Toàn màn) để thoát.", 3)
            if self.gpu:
                if self.full: self.win.set_fullscreen(True)
                else: self.win.set_windowed()
            else: pygame.display.toggle_fullscreen()
        except Exception as e: log("full:", e)

    def _retry(self):
        if self.state[0] in ("kicked", "error"):
            self.kicked = False; self.state = ("connecting", "Đang kết nối…"); self.need_key = True
            threading.Thread(target=self._connect_bg, daemon=True).start()

    def _reload(self):
        """F5 — TẢI LẠI HÌNH: đóng luồng hình đang có, nối lại từ đầu (hình đứng / mờ lâu)."""
        old, self.cli = self.cli, None; self.gen += 1                    # bỏ mọi sự kiện còn lại của luồng cũ
        if old: threading.Thread(target=old.close, daemon=True).start()
        self.kicked = False; self.state = ("connecting", "Đang tải lại hình…"); self.need_key = True; self._post()
        threading.Thread(target=self._connect_bg, daemon=True).start()

    def _input(self, e, pygame):
        c = self.cli; t = e.type
        if t == pygame.MOUSEMOTION:
            hv = self._tool_at(e.pos)
            ch = hv != self.hover; self.hover = hv
            if self.mouse_down and c: c.touch(2, 0, *self._clamp(e.pos))
            return ch
        if t == pygame.MOUSEBUTTONDOWN and e.button in (1, 2, 3):
            tl = self._tool_at(e.pos)
            if tl and e.button == 1: self._tool(tl, pygame); return True
            nr, n = self.notice_rect, self.notice
            if e.button == 1 and nr and n and n[2] and nr[0] <= e.pos[0] <= nr[0] + nr[2] and nr[1] <= e.pos[1] <= nr[1] + nr[3]:
                act = n[2]; self.notice = None
                try: act()
                except Exception as ex: log("notice:", ex)
                return True
            if self.state[0] in ("kicked", "error") and e.button == 1: self._retry(); return True
            p = self._norm(e.pos)
            if p and c:
                if e.button == 1: self.mouse_down = True; c.touch(0, 0, *p)
                elif e.button == 3: c.cmd("back")
                elif e.button == 2: c.cmd("home")
            return False
        if t == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.mouse_down and c: c.touch(1, 0, *self._clamp(e.pos))
            self.mouse_down = False; return False
        if t == pygame.MOUSEWHEEL and c:
            p = self._norm(pygame.mouse.get_pos())
            if p: c.scroll(p[0], p[1], int(-e.x * 120), int(e.y * 120))
            return False
        if t == pygame.TEXTINPUT and c:
            if e.text and not (pygame.key.get_mods() & pygame.KMOD_CTRL): c.text(e.text)
            return False
        if t in (pygame.KEYDOWN, pygame.KEYUP):
            down = t == pygame.KEYDOWN; mods = pygame.key.get_mods(); name = pygame.key.name(e.key)
            if down and e.key == pygame.K_F11: self._toggle_full(pygame); return True
            if down and e.key == pygame.K_F10: self._toggle_bar(pygame); return True
            if down and e.key == pygame.K_F5: self._reload(); return True
            if down and e.key == pygame.K_F3: self.show_info = not self.show_info; return True
            if down and e.key == pygame.K_r and self.state[0] in ("kicked", "error"): self._retry(); return True
            if not c: return False
            if mods & pygame.KMOD_CTRL and e.key == pygame.K_v:
                if down:
                    txt = clip_get()
                    if txt: c.clip_set(txt, True)
                return False
            meta = (META_CTRL if mods & pygame.KMOD_CTRL else 0) | (META_SHIFT if mods & pygame.KMOD_SHIFT else 0) | (META_ALT if mods & pygame.KMOD_ALT else 0)
            code = AK.get(name)
            if code is None and mods & pygame.KMOD_CTRL and len(name) == 1 and name.isalpha(): code = 29 + ord(name) - ord("a")   # Ctrl+A/C/X/Z…
            if code is not None: c.key(0 if down else 1, code, meta)
            return False
        return False


def run_viewer(pid):
    try:
        Viewer(pid).run()
    except Exception:
        log("viewer:", traceback.format_exc())
        try:
            import tkinter.messagebox as mb
            mb.showerror("CloudBlue", "Không mở được cửa sổ máy. Chi tiết trong:\n" + LOGF)
        except Exception: pass


# ================================================================ CỬA SỔ DANH SÁCH (tkinter)
BG, CARD, LINE, TXT, DIM, ACC, OK, WARN, BAD = "#0b1220", "#121b2f", "#1f2b45", "#eef2f8", "#8b97ad", "#2f7bff", "#22c38e", "#f0b429", "#ef5b5b"
BRAND = "#5aa8ff"          # màu chữ "Blue" trong tên CloudBlue
STATUS = {"active": ("Đang chạy", OK), "pending": ("Đang tạo…", WARN), "expired": ("Hết hạn — chờ gia hạn", BAD), "error": ("Lỗi", BAD)}


def fmt_left(iso):
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        s = (d - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        if s <= 0: return "đã hết hạn"
        dd, hh, mm = int(s // 86400), int(s % 86400 // 3600), int(s % 3600 // 60)
        loc = d.astimezone().strftime("%H:%M %d/%m/%Y")
        return (f"còn {dd} ngày {hh} giờ" if dd else f"còn {hh} giờ {mm} phút") + f" · hết hạn {loc}"
    except Exception:
        return ""


# ================================================================ MUA MÁY · GIA HẠN · NẠP TIỀN (giống hệt web: cùng RPC Supabase, cùng giá)
CP_RAM = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16]
CP_CPU = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 32]
CP_DAYS, CP_FPS, CP_QTY = [7, 15, 30, 60], [30, 60], [1, 2, 5, 10]
CP_RES = [("540x960", "Nhẹ máy"), ("720x1280", "HD"), ("720x1600", "HD+ dài"), ("1080x1920", "Full HD")]
CP_HARD = {"ram": 16, "cpu": 32, "fps": 60}                  # trần tuyệt đối 16GB · 32 nhân (MuMu); trần THẬT mỗi máy theo bản Android ở AND_LIM / bảng giá
AND_LIM = {"9": (8, 8), "12": (16, 32), "15": (16, 32), "7": (16, 16)}   # (RAM GB, nhân) tối đa 1 máy: Android 9 (LDPlayer) · 12 / 15 (MuMu) · 7 (bảng giá android_limits ghi đè)
CP_DEF = {"price_ram_gb_day": 2500, "price_cpu_day": 2000, "min_ram": 1, "max_ram": 16, "min_cpu": 1, "max_cpu": 32,
          "min_days": 1, "max_days": 90, "min_fps": 10, "max_fps": 120}
AND_HINT = {"9": "Ổn định · phổ biến", "12": "Mới", "15": "Mới nhất", "7": "Nhẹ"}
RENEW_DAYS = [1, 3, 7, 15, 30, 60, 90]
TOP_AMTS = [50000, 100000, 200000, 500000, 1000000]
BANKS = {"970422": "MB Bank", "970436": "Vietcombank", "970407": "Techcombank", "970416": "ACB", "970432": "VPBank", "970418": "BIDV",
         "970415": "VietinBank", "970423": "TPBank", "970403": "Sacombank", "970405": "Agribank", "970441": "VIB", "970443": "SHB",
         "970448": "OCB", "970426": "MSB"}
ERRORS.update({                                                  # mã lỗi của SQL → câu dễ hiểu (PHONE_LOCKED phải đứng trước LOCKED)
    "INSUFFICIENT_BALANCE": "Số dư không đủ.", "PHONE_LOCKED": "Máy đang bị khoá, không gia hạn được. Liên hệ hỗ trợ.",
    "LOCKED": "Tài khoản đã bị khoá. Liên hệ hỗ trợ.", "MIN_AMOUNT": "Số tiền thấp hơn mức nạp tối thiểu.",
    "TOO_MANY": "Bạn có quá nhiều lệnh nạp đang chờ. Thử lại sau ít phút.",
    "BAD_RAM": "RAM nằm ngoài giới hạn cho phép.", "BAD_CPU": "Số nhân CPU nằm ngoài giới hạn cho phép.", "BAD_DAYS": "Số ngày nằm ngoài giới hạn cho phép.",
    "BAD_RES": "Độ phân giải không hợp lệ.", "BAD_FPS": "FPS nằm ngoài giới hạn cho phép.", "BAD_QTY": "Số lượng không hợp lệ.",
    "FPS_TOO_HIGH": "Máy dưới 4 nhân chỉ chọn tối đa 60 FPS.", "OUT_OF_STOCK": "Đã hết hàng.",
    "MAX_PER_USER": "Tài khoản đã đủ số máy cho phép — gia hạn máy đang có hoặc xoá máy cũ để thuê máy khác.",
    "FREE_OFF": "Ưu đãi miễn phí đã kết thúc.", "FREE_LIMIT": "Máy miễn phí vượt cấu hình tối đa cho phép.",
    "FREE_USED": "Mỗi tài khoản chỉ được dùng thử 1 máy miễn phí — bạn đã nhận rồi.", "FREE_ONE": "Máy miễn phí chỉ nhận 1 máy mỗi lần.",
    "FREE_NO_RENEW": "Máy miễn phí không gia hạn được — hãy thuê máy mới.",
    "OUT_OF_CAPACITY": "Máy chủ đã hết chỗ cho cấu hình này. Chọn cấu hình nhỏ hơn hoặc quay lại sau.",
    "SERVER_OFFLINE": "Máy chủ bản Android này đang bảo trì — chọn bản khác.", "BAD_ANDROID": "Bản Android này chưa bán — chọn bản khác.",
    "PHONE_GONE": "Máy đã bị xoá vì hết hạn quá 30 phút — hãy thuê máy mới.", "NO_PHONE": "Không tìm thấy máy.",
})


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0


def vnd(v):
    return f"{round(num(v)):,}".replace(",", ".") + "đ"


def parse_iso(s):
    try: return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError): return None


def now_utc(): return datetime.datetime.now(datetime.timezone.utc)


# ---- mã VietQR (chuẩn EMVCo / NAPAS 247) — giống hệt web: app ngân hàng quét là tự điền số tiền + nội dung ----
def _tlv(i, v): return i + str(len(v)).zfill(2) + v


def _crc16(s):
    c = 0xFFFF
    for ch in s:
        c ^= ord(ch) << 8
        for _ in range(8): c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return f"{c:04X}"


def vietqr(bin_, acc, amount, memo):
    cons = _tlv("00", "A000000727") + _tlv("01", _tlv("00", bin_) + _tlv("01", acc)) + _tlv("02", "QRIBFTTA")
    p = (_tlv("00", "01") + _tlv("01", "12") + _tlv("38", cons) + _tlv("53", "704") + _tlv("54", str(int(round(amount))))
         + _tlv("58", "VN") + _tlv("62", _tlv("08", memo)) + "6304")
    return p + _crc16(p)


def notify_admin(text, auth=None):
    """Báo Telegram cho shop (giống web) — không chờ, lỗi thì thôi. Web chỉ nhận khi kèm mã đăng nhập của khách."""
    def job():
        try:
            h = {"Authorization": "Bearer " + auth.token()} if auth else None
            http("POST", WEB + "/api/notify-admin", {"text": text}, h, timeout=8)
        except Exception: pass
    threading.Thread(target=job, daemon=True).start()


class Shop:
    """Đọc giá, chỗ trống, số dư, tài khoản ngân hàng — cùng bảng/RPC với web."""
    def __init__(self, auth): self.auth = auth

    def profile(self):
        rows = self.auth.rest(f"profiles?id=eq.{self.auth.uid}&select=*") or []
        return rows[0] if rows else {}

    def pricing(self):
        p = dict(CP_DEF)
        try:
            rows = self.auth.rest("cloudphone_pricing?id=eq.1&select=*") or []
            if rows: p.update({k: v for k, v in rows[0].items() if v is not None})
        except ApiError as e:
            if e.code == 401: raise
            log("pricing:", e)
        for k, h in (("max_ram", "ram"), ("max_cpu", "cpu"), ("free_max_ram", "ram"), ("free_max_cpu", "cpu"), ("max_fps", "fps")):
            if p.get(k) is not None: p[k] = min(int(num(p[k])) or CP_HARD[h], CP_HARD[h])     # không bán vượt sức máy ảo
        return p

    def status(self):
        try: return self.auth.rpc("cloudphone_status") or {}
        except ApiError as e:
            if e.code == 401: raise
            return {}

    def site(self):
        rows = self.auth.rest("settings?id=eq.1&select=data") or []
        d = (rows[0].get("data") or {}) if rows else {}
        set_web(d.get("web"))
        return d

    def live_count(self):
        try: return len(self.auth.rest(f"cloud_phones?user_id=eq.{self.auth.uid}&status=in.(pending,creating,active,expired,cancelling)&select=id") or [])
        except ApiError: return 0


def set_web(u):
    """Tên miền web do admin đặt trong Supabase (settings.data.web, VD https://cloudblue.vn) — chỉ nhận link https hợp lệ."""
    global WEB
    u = str(u or "").strip().rstrip("/")
    if re.fullmatch(r"https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}", u, re.I): WEB = u


def is_ctv(prof): return prof.get("ctv_status") == "approved" and num(prof.get("ctv_discount")) > 0
def ctv(prof, v): return round(v * (100 - num(prof.get("ctv_discount"))) / 100) if is_ctv(prof) else v
def per_day(pr, ram, cpu): return ram * num(pr.get("price_ram_gb_day")) + cpu * num(pr.get("price_cpu_day"))


def free_live(pr):
    if not pr.get("free_on"): return False
    u = pr.get("free_until")
    if not u: return True
    d = parse_iso(u)
    return bool(d and d > now_utc())


def and_list(pr):
    out = []
    for v in str(pr.get("android_versions") or "9").split(","):
        v = v.strip()
        if re.fullmatch(r"\d{1,2}", v) and v not in out: out.append(v)
    return out or ["9"]


def and_lim(pr, v):
    """Trần 1 máy của bản Android v = min(trần chung trong bảng giá, trần của bản đó) → (RAM GB, nhân)."""
    al = pr.get("android_limits") if isinstance(pr.get("android_limits"), dict) else {}
    x = al.get(str(v)) if isinstance(al.get(str(v)), dict) else {}
    r0, c0 = AND_LIM.get(str(v), AND_LIM["9"])
    r, c = int(num(x.get("ram"))) or r0, int(num(x.get("cpu"))) or c0
    return (max(1, min(int(num(pr.get("max_ram"))) or r, r, CP_HARD["ram"])), max(1, min(int(num(pr.get("max_cpu"))) or c, c, CP_HARD["cpu"])))


def cp_opts(arr, lo, hi):
    """Các mức để bấm chọn trong [lo, hi] (luôn có đúng mức tối đa)."""
    return sorted({v for v in arr if lo <= v <= hi} | ({hi} if hi >= lo else set()))


def and_room(st, v):
    """Chỗ trống của máy chủ bản Android v → (online?, RAM trống, nhân trống) · None = máy chủ chưa báo theo từng bản."""
    m = st.get("android") if isinstance(st.get("android"), dict) else None
    if not m: return None
    a = m.get(v)
    if not isinstance(a, dict) or a.get("online") is False: return (False, 0, 0)
    return (True, num(a.get("free_ram")), num(a.get("free_cpu")))


def and_why(st, v, ram, cpu):
    """'' = còn chỗ · 'off' = máy chủ bản này đang bảo trì / chưa có · 'full' = không đủ RAM/CPU cho cấu hình đang chọn."""
    r = and_room(st, v)
    if r is None: return ""
    if not r[0]: return "off"
    return "full" if r[1] < ram or r[2] < cpu else ""


class Chips:
    """Hàng nút chọn 1 trong nhiều (giống web): bấm → set_(giá trị) → on_change()."""
    def __init__(self, app, parent, items, get, set_, on_change, why=None, wrap=0):
        tk = app.tk; self.get, self.why = get, why
        self.frame = tk.Frame(parent, bg=BG); self.labels = []
        row = None
        for i, (val, text) in enumerate(items):
            if row is None or (wrap and i % wrap == 0):
                row = tk.Frame(self.frame, bg=BG); row.pack(fill="x", anchor="w")
            lb = tk.Label(row, text=text, font=("Segoe UI", 10, "bold"), bg=CARD, fg=TXT, padx=12, pady=6, justify="center",
                          highlightthickness=1, highlightbackground=LINE, cursor="hand2")
            lb.pack(side="left", padx=(0, 6), pady=3)
            def click(_e, v=val):
                if self.why and self.why(v): return
                set_(v); on_change()
            lb.bind("<Button-1>", click)
            self.labels.append((val, lb))
        self.paint()

    def paint(self):
        cur = self.get()
        for v, lb in self.labels:
            off = bool(self.why and self.why(v)); on = (v == cur) and not off
            lb.config(bg=ACC if on else CARD, fg="#55607a" if off else TXT, cursor="arrow" if off else "hand2",
                      highlightbackground=ACC if on else LINE)


class Dlg:
    """Cửa sổ con (mua / gia hạn / nạp): phần trên cuộn được, phần dưới (tổng tiền + nút) đứng yên."""
    def __init__(self, app, title, w=580, h=700):
        tk = app.tk; self.app = app; self.alive = True
        self.win = d = tk.Toplevel(app.root); d.title(title); d.configure(bg=BG)
        if not getattr(app, "tools_only", False): d.transient(app.root)
        app.root.update_idletasks()
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight(); h = min(h, sh - 80)
        x = app.root.winfo_rootx() + (app.root.winfo_width() - w) // 2; y = app.root.winfo_rooty() + 20
        d.geometry(f"{w}x{h}+{max(0, min(x, sw - w))}+{max(0, min(y, sh - h - 40))}"); d.minsize(440, 380)
        d.bind("<Escape>", lambda e: self.close())
        d.protocol("WM_DELETE_WINDOW", self.close)
        d.after(80, self._grab)
        self.foot = tk.Frame(d, bg=CARD, highlightbackground=LINE, highlightthickness=1); self.foot.pack(side="bottom", fill="x")
        wrap = tk.Frame(d, bg=BG); wrap.pack(side="top", fill="both", expand=True)
        cv = tk.Canvas(wrap, bg=BG, highlightthickness=0); sb = tk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        self.body = tk.Frame(cv, bg=BG); win = cv.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set); cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        app.scrollers[str(d)] = cv

    def _grab(self):
        try: self.win.grab_set(); self.win.focus_force()
        except Exception: pass

    def close(self):
        self.alive = False
        self.app.scrollers.pop(str(self.win), None)
        try: self.win.grab_release()
        except Exception: pass
        try: self.win.destroy()
        except Exception: pass

    def clear(self):
        for w in self.body.winfo_children(): w.destroy()
        for w in self.foot.winfo_children(): w.destroy()

    def label(self, parent, text, font=None, fg=TXT, **kw):
        return self.app.tk.Label(parent, text=text, font=font or self.app.f_t, fg=fg, bg=parent["bg"], anchor="w", justify="left", **kw)

    def section(self, title, right="", parent=None):
        tk = self.app.tk
        f = tk.Frame(parent or self.body, bg=BG); f.pack(fill="x", padx=18, pady=(12, 2))
        hr = tk.Frame(f, bg=BG); hr.pack(fill="x")
        self.label(hr, title, ("Segoe UI", 10, "bold"), DIM).pack(side="left")
        if right: self.label(hr, right, self.app.f_s, DIM).pack(side="right")
        return f

    def loading(self, text="Đang tải…"):
        self.clear(); self.label(self.body, text, self.app.f_t, DIM).pack(padx=18, pady=30)

    def bg(self, job, ok, fail=None):
        """Chạy việc mạng ở luồng nền → gọi ok/fail trên luồng giao diện (cửa sổ đã đóng thì thôi)."""
        def run():
            try:
                r = job()
                self.app.ui(lambda: self.alive and ok(r))
            except Exception as e:
                m = str(e) or "Có lỗi, thử lại."; log("shop:", traceback.format_exc())
                if isinstance(e, ApiError) and e.code == 401: self.app.ui(lambda: (self.close(), self.app.show_login(m)))
                elif fail: self.app.ui(lambda: self.alive and fail(m))
        threading.Thread(target=run, daemon=True).start()


# ================= 🏷️ MÃ GIẢM GIÁ khi thanh toán (SQL v23 promo_check · gửi kèm p_promo) — giống web / app điện thoại =================
class PromoBox:
    """Ô mã + nút Áp dụng + dòng kết quả. ctx() = tham số promo_check của ĐƠN ĐANG CHỌN (None = chưa đủ thông tin).
       Đổi đơn → mã đã áp dụng tự kiểm lại sau 0,6 giây; mã sai hẳn không kiểm lại (khỏi bị tính nhập sai); ô có chữ mà mã sai → không cho thanh toán."""
    RECHECK = ("PROMO_MIN_ORDER", "PROMO_CTX", "BAD_PLAN", "NO_PHONE", "NO_MACHINE", "NO_PRODUCT")

    def __init__(self, dlg, parent, scope, ctx, changed):
        tk = dlg.app.tk; self.dlg, self.scope, self.ctx, self.changed = dlg, scope, ctx, changed
        self.code, self.key, self.r, self.busy, self.seq = "", "", None, False, 0
        self.frame = tk.Frame(parent, bg=parent["bg"])
        row = tk.Frame(self.frame, bg=parent["bg"]); row.pack(fill="x")
        tk.Label(row, text="🏷️", font=("Segoe UI Emoji", 12), bg=parent["bg"], fg=TXT).pack(side="left")
        self.ent = tk.Entry(row, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
        self.ent.pack(side="left", fill="x", expand=True, ipady=5, padx=(6, 6))
        dlg.app.btn(row, "Áp dụng", lambda: self.check(), "soft").pack(side="left")
        self.res = dlg.label(self.frame, "Mã giảm giá (nếu có) — nhập rồi bấm Áp dụng.", dlg.app.f_s, DIM, wraplength=520); self.res.pack(fill="x", pady=(3, 0))
        self.ent.bind("<KeyRelease>", self._typed); self.ent.bind("<Return>", lambda *_: self.check())

    @staticmethod
    def norm(v): return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())
    def _keynow(self):
        c = self.ctx()
        return "" if c is None else json.dumps([self.code, self.scope, c], sort_keys=True)
    def live(self):
        return self.r if self.r is not None and not self.busy and self.key and self.key == self._keynow() else None
    @staticmethod
    def use(x): return bool(x and x.get("ok") and x.get("kind") == "discount" and x.get("use_promo"))
    def price(self, normal):
        x = self.live(); return max(0, num(x.get("price"))) if self.use(x) else normal
    def send(self): return self.code if self.use(self.live()) else None

    def _typed(self, _e=None):
        c = self.norm(self.ent.get())
        if c == self.code: return
        self.code, self.r, self.key, self.busy = c, None, "", False; self.seq += 1
        self.paint(); self.changed()

    def order_changed(self):
        if not self.code or self.r is None or self.busy: return
        r = self.r
        if not (r.get("ok") and r.get("kind") == "discount") and not r.get("net") and r.get("err") not in self.RECHECK: return
        if self._keynow() == self.key: return
        self.seq += 1; s = self.seq; self.busy = True; self.paint()
        self.dlg.app.root.after(600, lambda: self.dlg.alive and s == self.seq and (setattr(self, "busy", False), self.check()))

    def check(self, then=None):
        self.code = self.norm(self.ent.get())
        if not self.code: self.r, self.key = None, ""; self.paint(); self.changed(); return then and then()
        c = self.ctx()
        if c is None:
            self.r, self.key = {"ok": False, "err": "PROMO_CTX"}, ""; self.paint(); self.changed(); return then and then()
        k = json.dumps([self.code, self.scope, c], sort_keys=True); self.seq += 1; s = self.seq; self.busy = True; self.paint()
        code, scope = self.code, self.scope
        def job():
            try: return self.dlg.app.auth.rpc("promo_check", {"p_code": code, "p_scope": scope, **c}) or {"ok": False, "err": "PROMO_INVALID"}
            except ApiError as e:
                m = str(e); off = "promo_check" in m or "schema cache" in m or "Could not find" in m
                return {"ok": False, "err": "PROMO_OFF" if off else m, "net": not off}
        def done(r):
            if s != self.seq: return
            self.busy, self.r, self.key = False, (r if isinstance(r, dict) else {"ok": False, "err": "PROMO_INVALID"}), k
            self.paint(); self.changed()
            if then: then()
        self.dlg.bg(job, done)

    def err_of(self, x):
        e = str(x.get("err") or "")
        if x.get("ok") and x.get("kind") == "gift": return code_text("PROMO_IS_GIFT")
        if e == "PROMO_MIN_ORDER" and x.get("min_order") is not None: return f"Mã chỉ dùng cho đơn từ {vnd(x.get('min_order'))} (đơn này {vnd(x.get('base'))})."
        return code_text(e or "PROMO_INVALID")

    def paint(self):
        if not self.dlg.alive or not self.res.winfo_exists(): return
        if self.busy: self.res.config(text="⏳ Đang kiểm tra mã…", fg=DIM); return
        r = self.r
        if not self.code or r is None: self.res.config(text="Mã giảm giá (nếu có) — nhập rồi bấm Áp dụng.", fg=DIM); return
        if self.use(r): self.res.config(text=f"✓ Giảm {vnd(r.get('discount'))} → còn {vnd(r.get('price'))}", fg=OK)
        elif r.get("ok") and r.get("kind") == "discount": self.res.config(text="ℹ Giá CTV của bạn đã rẻ hơn — mã sẽ không được dùng (không mất lượt).", fg=DIM)
        else: self.res.config(text="⚠ " + self.err_of(r), fg=BAD)

    def ensure(self, ok, err_lbl):
        """Trước khi trả tiền: ô trống → mua bình thường; có chữ → phải là mã dùng được cho chính đơn này."""
        if not self.norm(self.ent.get()): self.code = ""; return ok()
        def decide():
            y = self.live()
            if y and y.get("ok") and y.get("kind") == "discount": ok()
            else: err_lbl.config(text=(self.err_of(y) if y else "Chưa kiểm tra được mã, thử lại.") + " Sửa hoặc xoá mã giảm giá để thanh toán.", fg=BAD)
        decide() if self.live() is not None else self.check(decide)

    def fail(self, m):
        """Đơn bị từ chối vì mã → hiện lỗi dưới ô mã."""
        for k in ERRORS:
            if k.startswith("PROMO_") and ERRORS[k] == m:
                self.r, self.key = {"ok": False, "err": k}, self._keynow(); self.paint(); return True
        return False


# ================= 💎 TÍCH BLUE (SQL v27): điểm danh, nhiệm vụ hằng ngày, trả bằng Blue (1 Blue = 1đ) =================
BLUE = {"info": None, "t": 0.0}
def blue_n(v): return f"{int(num(v)):,}".replace(",", ".")
def blue_on(): i = BLUE["info"]; return bool(i and i.get("on"))
def blue_load(auth):
    """Đọc blue_info (gọi ở luồng nền) — chưa chạy SQL v27 / lỗi → None (ẩn mọi thứ, app chạy như cũ)."""
    try: i = auth.rpc("blue_info")
    except ApiError as e:
        if e.code == 401: raise
        i = None
    BLUE["info"] = i if isinstance(i, dict) and "on" in i else None; BLUE["t"] = time.time()
    return BLUE["info"]
def blue_use(pay):
    i = BLUE["info"]
    if not (i and i.get("on") and i.get("can_use")): return 0
    pct = max(0, min(100, int(num((i.get("cfg") or {}).get("max_pct") if (i.get("cfg") or {}).get("max_pct") is not None else 100))))
    return max(0, min(int(num(i.get("blue"))), int(max(0, pay) * pct // 100)))
def blue_todo():
    i = BLUE["info"]
    return sum(1 for t in ((i or {}).get("tasks") or []) if not t.get("done") and t.get("ready")) if blue_on() else 0
def vn_today():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
def blue_play_task(auth, say=None):
    """Nhiệm vụ "mở máy đám mây": cửa sổ máy nối được → nhận (mỗi ngày thử 1 lần / tài khoản; đã nhận / chưa bật thì im lặng)."""
    k, d = "blue_play_" + str(auth.uid or ""), vn_today()
    if not auth.uid or prefs().get(k) == d: return
    try: r = auth.rpc("blue_task", {"p_task": "play"}) or {}
    except ApiError as e:
        if e.code != 0: prefs({k: d})                    # đã nhận / chưa bật / chưa chạy SQL v27 → thôi hôm nay · mất mạng → lần mở sau thử lại
        return
    except Exception: return
    prefs({k: d})
    if say and int(num(r.get("got"))) > 0: say(f"💎 +{blue_n(r.get('got'))} Blue — nhiệm vụ mở máy hôm nay")


class BluePay:
    """Dòng "💎 Trả bằng Blue" trong bảng thuê / gia hạn. use(pay) = số Blue sẽ trừ cho đơn."""
    def __init__(self, dlg, parent, changed, on=False):
        tk = dlg.app.tk; self.dlg = dlg
        self.var = tk.BooleanVar(value=on)
        self.frame = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        self.cb = tk.Checkbutton(self.frame, text="  💎 Trả bằng Blue", variable=self.var, command=changed, font=("Segoe UI", 10, "bold"), fg=TXT, bg=CARD,
                                 selectcolor=BG, activebackground=CARD, activeforeground=TXT, anchor="w", cursor="hand2")
        self.cb.pack(fill="x", padx=8, pady=(6, 0))
        self.sub = dlg.label(self.frame, "", dlg.app.f_s, DIM, wraplength=500); self.sub.pack(fill="x", padx=34, pady=(0, 6))
    def use(self, pay): return blue_use(pay) if self.var.get() else 0
    def paint(self, pay, hide=False):
        if not self.frame.winfo_exists(): return
        if hide or not blue_on(): self.frame.pack_forget(); return
        if not self.frame.winfo_manager(): self.frame.pack(fill="x", pady=(8, 0))
        i = BLUE["info"]; can = bool(i.get("can_use")); have = int(num(i.get("blue"))); u = self.use(pay)
        ok = can and have > 0
        if not ok and self.var.get(): self.var.set(False)
        self.cb.config(state="normal" if ok else "disabled")
        self.sub.config(text="🔒 Nạp tiền lần đầu để dùng Blue (Blue vẫn được tích)." if not can else
                        "Chưa có Blue — điểm danh, làm nhiệm vụ để tích (bấm 💎 Tích Blue trên danh sách máy)." if have <= 0 else
                        f"Trừ {blue_n(u)} Blue (= {vnd(u)}) · còn {blue_n(have - u)} Blue" if u > 0 else f"Bạn có {blue_n(have)} Blue · 1 Blue = 1đ")


class BlueDlg(Dlg):
    """💎 Tích Blue: số Blue, chuỗi điểm danh, nhiệm vụ hôm nay (điểm danh · mở máy · chia sẻ link mời · mời bạn), cách nhận thêm, lịch sử."""
    TASK = {"checkin": ("📅", "Điểm danh hôm nay", "Ngày nào cũng ghé là có Blue"),
            "play": ("📱", "Mở máy đám mây", "Mở 1 máy bất kỳ (app PC, app Android hoặc web) là tự nhận"),
            "share": ("📣", "Chia sẻ link mời", "Copy link CloudBlue của bạn gửi bạn bè / nhóm"),
            "invite": ("🤝", "Mời 1 bạn đăng ký", "Có bạn đăng ký qua link của bạn trong hôm nay")}
    KIND = {"checkin": "Điểm danh", "streak": "Thưởng chuỗi", "task": "Nhiệm vụ", "ref": "Mời bạn", "cashback": "Hoàn đơn",
            "spend": "Đã dùng", "refund": "Hoàn lại", "admin": "Admin", "clawback": "Thu lại"}

    def __init__(self, app):
        super().__init__(app, "💎 Tích Blue", 560, 720)
        self.loading("Đang tải…")
        self.bg(lambda: blue_load(app.auth), self.draw, lambda m: self.loading(m))

    def draw(self, i):
        tk = self.app.tk; self.clear()
        if not i or not i.get("on"):
            self.loading("Tích Blue đang tạm tắt." if i else "Chưa mở được Tích Blue — máy chủ chưa bật tính năng này."); return
        cfg = i.get("cfg") or {}
        hero = tk.Frame(self.body, bg=CARD, highlightbackground=ACC, highlightthickness=1); hero.pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(hero, text=f"💎 {blue_n(i.get('blue'))} Blue", font=("Segoe UI", 20, "bold"), fg=TXT, bg=CARD, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        mp = int(num(cfg.get("max_pct") if cfg.get("max_pct") is not None else 100))
        self.label(hero, "1 Blue = 1đ khi thuê / gia hạn điện thoại đám mây" + (f" (tối đa {mp}% mỗi đơn)" if mp < 100 else "")
                   + " — bật 💎 Trả bằng Blue lúc thanh toán.", self.app.f_s, DIM, wraplength=490).pack(fill="x", padx=14, pady=(0, 10))
        if not i.get("can_use") and i.get("need_topup"):
            self.label(self.body, "🔒 Nạp tiền lần đầu để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.", self.app.f_s, WARN, wraplength=520).pack(fill="x", padx=18, pady=(8, 0))
        sd, st, today = int(num(cfg.get("streak_days"))), int(num(i.get("streak"))), bool(i.get("today"))
        if 0 < sd <= 14 and num(cfg.get("checkin")) > 0:
            f = self.section("Chuỗi điểm danh", f"{st} ngày liền" if st else "bắt đầu hôm nay")
            row = tk.Frame(f, bg=BG); row.pack(fill="x")
            filled = ((st - 1) % sd) + 1 if today else st % sd; now = filled if today else filled + 1
            for k in range(1, sd + 1):
                got, big = k <= filled, k == sd
                c = tk.Frame(row, bg=CARD, highlightbackground=ACC if k == now else (OK if got else LINE), highlightthickness=1)
                c.pack(side="left", fill="x", expand=True, padx=2)
                tk.Label(c, text="Hôm nay" if k == now else f"Ngày {k}", font=self.app.f_s, fg=DIM, bg=CARD).pack()
                tk.Label(c, text="✓" if got else "+" + blue_n(num(cfg.get("checkin")) + (num(cfg.get("streak_bonus")) if big else 0)),
                         font=("Segoe UI", 10, "bold"), fg=OK if got else (ACC if big else TXT), bg=CARD).pack(pady=(0, 4))
        ts = i.get("tasks") or []
        f = self.section("Nhiệm vụ hôm nay", f"{sum(1 for t in ts if t.get('done'))}/{len(ts)} xong")
        self.msg = self.label(f, "", self.app.f_s, OK, wraplength=520)
        for t in ts:
            tid = t.get("id"); ic, name, sub = self.TASK.get(tid, ("⭐", tid, ""))
            if tid == "invite" and t.get("ready"): sub = "Đã có bạn đăng ký qua link của bạn hôm nay 🎉"
            if tid == "play" and not t.get("ready") and not t.get("done"): sub = "Cần có 1 máy đang chạy — thuê máy rồi mở là nhận"
            fr = tk.Frame(f, bg=CARD, highlightbackground=LINE, highlightthickness=1); fr.pack(fill="x", pady=(0, 6))
            tk.Label(fr, text=ic, font=("Segoe UI Emoji", 15), bg=CARD, fg=TXT, width=2).pack(side="left", padx=(10, 6), pady=8)
            if t.get("done"): self.label(fr, "✓ Đã nhận", ("Segoe UI", 10, "bold"), OK).pack(side="right", padx=12)
            else:
                act = {"checkin": ("Điểm danh", self.checkin), "share": ("Chia sẻ", self.share),
                       "invite": ("Nhận", lambda: self.task("invite")) if t.get("ready") else ("Copy link mời", self.share),
                       "play": ("Mở máy", self.close) if t.get("ready") else ("Thuê máy", lambda: (self.close(), self.app.open_order()))}.get(tid)
                if act: self.app.btn(fr, act[0], act[1], "primary" if tid in ("checkin", "share") or t.get("ready") else "soft").pack(side="right", padx=10)
            tx = tk.Frame(fr, bg=CARD); tx.pack(side="left", fill="x", expand=True, pady=6)
            self.label(tx, f"{name}   +{blue_n(t.get('got'))}", ("Segoe UI", 10, "bold"), TXT).pack(fill="x")
            self.label(tx, sub, self.app.f_s, DIM, wraplength=330).pack(fill="x")
        self.msg.pack(fill="x")
        more = []
        if num(cfg.get("ref")) > 0: more.append(f"• Bạn bè bạn mời nạp tiền / mua lần đầu: +{blue_n(cfg.get('ref'))} Blue mỗi bạn")
        if num(cfg.get("cashback")) > 0: more.append(f"• Mỗi đơn trả bằng tiền (thuê, gia hạn, nâng cấp, mua hàng): hoàn {num(cfg.get('cashback')):g}% bằng Blue")
        more.append("• Nhiệm vụ làm mới lúc 0 giờ mỗi ngày (giờ Việt Nam)")
        f = self.section("Nhận thêm Blue"); self.label(f, "\n".join(more), self.app.f_s, DIM, wraplength=520).pack(fill="x")
        items = i.get("items") or []
        if items:
            f = self.section("Lịch sử Blue")
            for x in items[:20]:
                r = tk.Frame(f, bg=BG); r.pack(fill="x")
                d = parse_iso(x.get("t")); dv = int(num(x.get("delta")))
                self.label(r, (d.astimezone().strftime("%d/%m %H:%M") + " · " if d else "") + str(x.get("note") or self.KIND.get(x.get("kind"), x.get("kind"))),
                           self.app.f_s, DIM).pack(side="left")
                self.label(r, ("+" if dv >= 0 else "−") + blue_n(abs(dv)), ("Segoe UI", 9, "bold"), OK if dv >= 0 else BAD).pack(side="right")
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=10)
        self.app.btn(bb, "Đóng", self.close, "soft").pack(side="right")
        self.app.refresh(quiet=True)

    def _after(self, r, okmsg):
        self.bg(lambda: blue_load(self.app.auth), lambda i: (self.draw(i), self.alive and self.msg.config(text=okmsg)))

    def checkin(self):
        def done(r):
            r = r or {}
            self._after(r, f"🎉 +{blue_n(num(r.get('got')) + num(r.get('bonus')))} Blue — đủ chuỗi {r.get('streak')} ngày!" if num(r.get("bonus")) > 0
                        else f"💎 +{blue_n(r.get('got'))} Blue — điểm danh ngày {r.get('streak')}")
        self.bg(lambda: self.app.auth.rpc("blue_checkin"), done, lambda m: (self.msg.config(text=m, fg=BAD) if self.alive else None))

    def task(self, tid):
        name = self.TASK.get(tid, ("", tid))[1]
        self.bg(lambda: self.app.auth.rpc("blue_task", {"p_task": tid}), lambda r: self._after(r, f"💎 +{blue_n((r or {}).get('got'))} Blue · {name}"),
                lambda m: (self.msg.config(text=m, fg=BAD) if self.alive else None))

    def share(self):
        def job():
            try:
                r = self.app.auth.rpc("ref_info") or {}
                return WEB + "/?ref=" + r["code"] if r.get("code") else WEB + "/"
            except Exception: return WEB + "/"
        def done(link):
            text = "Thuê điện thoại Android đám mây chạy 24/7 ở CloudBlue — đăng ký qua link của mình nhé: " + link
            try: self.win.clipboard_clear(); self.win.clipboard_append(text)
            except Exception: pass
            self.task("share")
            self.app.ui(lambda: self.alive and self.msg.config(text="📋 Đã copy link mời — dán gửi bạn bè / nhóm (Zalo, Facebook, Discord…).", fg=OK))
        self.bg(job, done)


class CodeDlg(Dlg):
    """🎟 Nhập mã: mã TẶNG MÁY (12 ký tự — nhận 1 máy miễn phí) hoặc mã CHIA SẺ / CHUYỂN NHƯỢNG máy (8 ký tự) — giống app điện thoại."""
    def __init__(self, app):
        super().__init__(app, "🎟 Nhập mã", 480, 300)
        tk = app.tk
        self.label(self.body, "Mã tặng máy (12 ký tự) → nhận 1 máy miễn phí.\nMã chia sẻ / chuyển nhượng máy (8 ký tự) → máy hiện trong danh sách của bạn.\n"
                              "Mã GIẢM GIÁ thì nhập ở ô 🏷️ khi thuê / gia hạn / nâng cấp.", self.app.f_s, DIM, wraplength=440).pack(fill="x", padx=18, pady=(16, 8))
        self.ent = tk.Entry(self.body, font=("Consolas", 16, "bold"), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat", justify="center")
        self.ent.pack(fill="x", padx=18, ipady=8); self.ent.focus_set(); self.ent.bind("<Return>", lambda *_: self.go())
        self.err = self.label(self.body, "", self.app.f_s, BAD, wraplength=440); self.err.pack(fill="x", padx=18, pady=(6, 0))
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=10)
        self.app.btn(bb, "Đóng", self.close, "soft").pack(side="left")
        self.b = self.app.btn(bb, "Nhận", self.go); self.b.pack(side="right")

    def go(self):
        import tkinter.messagebox as mb
        c = re.sub(r"[^A-Z0-9]", "", self.ent.get().upper())
        if len(c) < 4: self.err.config(text="Nhập mã tặng máy (12 ký tự) hoặc mã chia sẻ / chuyển nhượng (8 ký tự)."); return
        self.b.config(state="disabled", text="Đang kiểm tra…")
        if len(c) != 8:
            def done(r):
                r = r if isinstance(r, dict) else {}
                if not r.get("ok"):
                    e = str(r.get("err") or "PROMO_INVALID")
                    keep = e in ("SERVER_OFFLINE", "MAINTENANCE", "OUT_OF_CAPACITY", "OUT_OF_STOCK", "MAX_PER_USER", "BAD_ANDROID")
                    self.err.config(text=code_text(e) + (" Mã của bạn vẫn còn nguyên — thử lại sau." if keep else "")); self.b.config(state="normal", text="Nhận"); return
                self.close(); self.app.refresh()
                mb.showinfo("CloudBlue", f"🎁 Nhận máy tặng thành công — máy đang được tạo (Android {r.get('android')} · {r.get('ram')}GB · "
                                         f"{r.get('cpu')} nhân · {r.get('days')} ngày).", parent=self.app.root)
            self.bg(lambda: self.app.auth.rpc("promo_redeem_gift", {"p_code": c}), done, lambda m: (self.err.config(text=m), self.b.config(state="normal", text="Nhận")))
            return
        def done2(r):
            r = r if isinstance(r, dict) else {}
            self.close(); self.app.refresh()
            mb.showinfo("CloudBlue", f"🎉 Máy “{r.get('name')}” giờ là của bạn!" if r.get("kind") == "transfer"
                        else f"✓ Đã thêm máy “{r.get('name')}” được chia sẻ cho bạn.", parent=self.app.root)
        self.bg(lambda: self.app.auth.rpc("cp_share_claim", {"p_code": c}), done2, lambda m: (self.err.config(text=m), self.b.config(state="normal", text="Nhận")))


class OrderDlg(Dlg):
    """Thuê máy mới — y như bảng thuê trên web (giá, giới hạn, chỗ trống từng bản Android, máy miễn phí, CTV)."""
    def __init__(self, app):
        super().__init__(app, "Thuê điện thoại đám mây", 600, 760)
        self.loading("Đang tải bảng giá…")
        def load():
            sh = app.shop
            return sh.pricing(), sh.status(), sh.profile(), sh.live_count()
        self.bg(load, self._loaded, lambda m: self.loading(m))

    def _loaded(self, r):
        self.pr, self.st, self.prof, have = r
        p = self.pr; cl = lambda v, lo, hi: max(int(num(lo)), min(int(num(hi)), v))
        mpu = int(num(p.get("max_per_user")))
        self.left = 20 if mpu <= 0 or self.prof.get("role") == "admin" else mpu - have
        if self.left <= 0:
            self.loading(f"Mỗi tài khoản chỉ được thuê tối đa {mpu} máy — bạn đã có {have} máy.\nGia hạn máy đang có, hoặc xoá máy cũ (trên web) để thuê máy khác.")
            return
        if self.st.get("maint") and self.prof.get("role") != "admin":           # admin vẫn thuê được khi bảo trì (giống web) để thử máy
            self.loading("Hệ thống đang bảo trì" + (": " + str(self.st.get("maint_msg")) if self.st.get("maint_msg") else "") + ". Vui lòng quay lại sau."); return
        self.s = {"ram": cl(2, p["min_ram"], p["max_ram"]), "cpu": cl(2, p["min_cpu"], p["max_cpu"]), "days": cl(7, p["min_days"], p["max_days"]),
                  "res": "720x1280", "fps": cl(30, p["min_fps"], p["max_fps"]), "qty": 1, "android": "9", "free": False}
        avs = and_list(p); ok = [v for v in avs if not and_why(self.st, v, *self.fit(v))]
        self.s["android"] = "9" if "9" in ok else (ok[0] if ok else ("9" if "9" in avs else avs[0]))
        self.build()

    # ---------- vẽ ----------
    def build(self):
        tk = self.app.tk; p, s = self.pr, self.s; self.clear(); self.rows = []
        lo = lambda k: int(num(p.get(k)))
        if self.prof.get("role") == "admin" and (self.st.get("maint") or self.st.get("online") is False):
            self.label(self.body, "⚠ Đang bật BẢO TRÌ — khách không thuê được. Tài khoản admin vẫn thuê được (không giới hạn chỗ trống) để thử máy.",
                       ("Segoe UI", 10, "bold"), WARN, wraplength=540).pack(fill="x", padx=18, pady=(14, 0))
        if free_live(p):
            fb = tk.Frame(self.body, bg=CARD, highlightbackground=WARN if s["free"] else LINE, highlightthickness=1); fb.pack(fill="x", padx=18, pady=(14, 0))
            v = tk.BooleanVar(value=s["free"])
            tk.Checkbutton(fb, text=f"  ★ Nhận máy MIỄN PHÍ {lo('free_days') or 1} ngày", variable=v, command=lambda: self.set_free(v.get()),
                           font=("Segoe UI", 11, "bold"), fg=TXT, bg=CARD, selectcolor=BG, activebackground=CARD, activeforeground=TXT,
                           anchor="w", cursor="hand2").pack(fill="x", padx=10, pady=(8, 0))
            self.label(fb, f"Tối đa {lo('free_max_ram')}GB RAM · {lo('free_max_cpu')} nhân · mỗi tài khoản dùng thử 1 máy. Hết hạn máy tự tắt, không gia hạn được.",
                       self.app.f_s, DIM, wraplength=520).pack(fill="x", padx=12, pady=(0, 8))
        ch = lambda key: (lambda v: self.s.__setitem__(key, v))
        get = lambda key: (lambda: self.s[key])
        avs = and_list(p)
        f = self.section("Hệ điều hành")
        self.rows.append(Chips(self.app, f, [(v, f"Android {v}\n{AND_HINT.get(v, '')}".strip()) for v in avs], get("android"), self.set_android, self.upd,
                               why=lambda v: and_why(self.st, v, *self.fit(v)) if self.prof.get("role") != "admin" else ""))
        self.rows[-1].frame.pack(fill="x")
        self.and_note = self.label(f, "", self.app.f_s, DIM); self.and_note.pack(fill="x")
        if "15" in avs:
            self.label(f, "Android 15 không vào được Google / Play Store? Chọn Android 12 — máy đang thuê thì dùng Khác ▾ → Đổi Android (giữ nguyên hạn).",
                       self.app.f_s, DIM, wraplength=520).pack(fill="x")
        ar, ac = and_lim(p, s["android"])                                   # trần theo bản Android đang chọn (Android 9: 8GB · 8 nhân · Android 12 / 15: 16GB · 32 nhân)
        mr = min(ar, lo("free_max_ram") or 999) if s["free"] else ar
        mc = min(ac, lo("free_max_cpu") or 999) if s["free"] else ac
        f = self.section("RAM", f"{lo('min_ram')}–{mr} GB")
        self.rows.append(Chips(self.app, f, [(v, f"{v}GB") for v in cp_opts(CP_RAM, lo("min_ram"), mr)], get("ram"), ch("ram"), self.upd, wrap=8)); self.rows[-1].frame.pack(fill="x")
        f = self.section("CPU (nhân)", f"{lo('min_cpu')}–{mc} nhân")
        self.rows.append(Chips(self.app, f, [(v, str(v)) for v in cp_opts(CP_CPU, lo("min_cpu"), mc)], get("cpu"), ch("cpu"), self.upd, wrap=9)); self.rows[-1].frame.pack(fill="x")
        self.label(f, "💡 Treo 1 tab Roblox: nên chọn từ 4GB RAM · 4 nhân (vào game Roblox đã dùng khoảng 2GB RAM) — 3GB · 2 nhân thường không treo nổi. "
                      "Treo 2–4 tab: 8GB · 8 nhân.", self.app.f_s, DIM, wraplength=520).pack(fill="x", pady=(4, 0))
        if not s["free"]:
            f = self.section("Số ngày", f"{lo('min_days')}–{lo('max_days')} ngày")
            line = tk.Frame(f, bg=BG); line.pack(fill="x")
            self.days_x = tk.Entry(line, width=6, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
            def typed(_e=None):
                try: v = int(self.days_x.get())
                except ValueError: return
                if lo("min_days") <= v <= lo("max_days"): self.s["days"] = v; self.upd()
            self.rows.append(Chips(self.app, line, [(v, f"{v} ngày") for v in CP_DAYS if lo("min_days") <= v <= lo("max_days")], get("days"),
                                   lambda v: (self.s.__setitem__("days", v), self.days_x.delete(0, "end")), self.upd))
            self.rows[-1].frame.pack(side="left")
            self.label(line, "  khác:", self.app.f_s, DIM).pack(side="left"); self.days_x.pack(side="left", ipady=4)
            self.days_x.bind("<KeyRelease>", typed)
        f = self.section("Độ phân giải")
        self.rows.append(Chips(self.app, f, [(r, f"{n}\n{r}") for r, n in CP_RES], get("res"), ch("res"), self.upd)); self.rows[-1].frame.pack(fill="x")
        f = self.section("FPS (khung hình / giây)")
        self.rows.append(Chips(self.app, f, [(v, f"{v} FPS") for v in CP_FPS if lo("min_fps") <= v <= lo("max_fps")], get("fps"), ch("fps"), self.upd)); self.rows[-1].frame.pack(fill="x")
        if not s["free"] and self.left > 1:
            f = self.section("Số lượng máy")
            self.rows.append(Chips(self.app, f, [(v, f"{v} máy") for v in CP_QTY if v <= min(20, self.left)], get("qty"), ch("qty"), self.upd)); self.rows[-1].frame.pack(fill="x")
        self.promo = self.bpay = None
        if not s["free"]:                                    # 🏷️ mã giảm giá + 💎 trả bằng Blue (máy miễn phí không dùng)
            f = self.section("Mã giảm giá · Blue")
            self.promo = PromoBox(self, f, "cp_new", lambda: None if self.s["free"] else {"p_ram": self.s["ram"], "p_cpu": self.s["cpu"],
                                                                                      "p_days": self.s["days"], "p_qty": self.s["qty"]}, self.upd)
            self.promo.frame.pack(fill="x")
            if getattr(self, "_promo_code", ""): self.promo.ent.insert(0, self._promo_code); self.promo.check()
            self.bpay = BluePay(self, f, self.upd, getattr(self, "_blue_on", False))
        note = (p.get("order_note") or "").strip() or ("Máy mới tinh, không dính dữ liệu hay tài khoản Gmail của ai. Hết hạn máy tạm dừng — "
                                                       "gia hạn trong 30 phút, quá thời gian máy và dữ liệu bị xoá.")
        self.label(self.body, note, self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=18, pady=(14, 18))
        # ---- chân: tổng tiền + nút ----
        ft = self.foot
        self.calc = self.label(ft, "", self.app.f_s, DIM); self.calc.pack(fill="x", padx=16, pady=(10, 0))
        r = tk.Frame(ft, bg=CARD); r.pack(fill="x", padx=16)
        self.total = self.label(r, "", ("Segoe UI", 18, "bold"), TXT); self.total.pack(side="left")
        self.bal = self.label(r, "", self.app.f_t, DIM); self.bal.pack(side="right")
        self.err = self.label(ft, "", self.app.f_s, BAD, wraplength=540); self.err.pack(fill="x", padx=16)
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Thuê ngay", self.buy); self.go.pack(side="right")
        self.upd()

    def fit(self, v):
        """RAM / CPU đang chọn sau khi kẹp theo trần của bản Android v (đổi bản thì cấu hình tự kẹp lại)."""
        ar, ac = and_lim(self.pr, v)
        return min(self.s["ram"], ar), min(self.s["cpu"], ac)

    def set_android(self, v):
        """Đổi bản Android → danh sách RAM / CPU đổi theo trần của bản đó → vẽ lại bảng."""
        if v == self.s["android"]: return
        self.s["android"] = v; self.s["ram"], self.s["cpu"] = self.fit(v)
        self.app.root.after_idle(lambda: self.alive and self.build())

    def set_free(self, on):
        p, s = self.pr, self.s; s["free"] = bool(on)
        if on and self.prof.get("role") != "admin":
            s["ram"] = min(s["ram"], int(num(p.get("free_max_ram"))) or s["ram"]); s["cpu"] = min(s["cpu"], int(num(p.get("free_max_cpu"))) or s["cpu"]); s["qty"] = 1
        if on: s["days"] = int(num(p.get("free_days"))) or 1
        self.build()

    def price(self):
        s = self.s
        return 0 if s["free"] else ctv(self.prof, per_day(self.pr, s["ram"], s["cpu"]) * s["days"]) * s["qty"]

    def check(self):
        p, s, st, adm = self.pr, self.s, self.st, self.prof.get("role") == "admin"
        lo = lambda k: num(p.get(k))
        if st.get("maint") and not adm: return "Hệ thống đang bảo trì, vui lòng quay lại sau."
        if st.get("online") is False and not adm: return "Máy chủ điện thoại đang tạm ngưng, vui lòng quay lại sau."
        if s["free"] and not adm:
            if s["ram"] > lo("free_max_ram"): return f"Máy miễn phí tối đa {int(lo('free_max_ram'))}GB RAM."
            if s["cpu"] > lo("free_max_cpu"): return f"Máy miễn phí tối đa {int(lo('free_max_cpu'))} nhân."
        ar, ac = and_lim(p, s["android"])
        if not lo("min_ram") <= s["ram"] <= ar: return f"Android {s['android']}: RAM từ {int(lo('min_ram'))} đến {ar} GB."
        if not lo("min_cpu") <= s["cpu"] <= ac: return f"Android {s['android']}: CPU từ {int(lo('min_cpu'))} đến {ac} nhân."
        if not s["free"] and not lo("min_days") <= s["days"] <= lo("max_days"): return f"Số ngày phải từ {int(lo('min_days'))} đến {int(lo('max_days'))}."
        if not lo("min_fps") <= s["fps"] <= lo("max_fps"): return f"FPS phải từ {int(lo('min_fps'))} đến {int(lo('max_fps'))}."
        if s["cpu"] < 4 and s["fps"] > 60: return "Máy dưới 4 nhân chỉ chọn tối đa 60 FPS."
        if s["qty"] > self.left and not adm: return f"Tài khoản của bạn chỉ còn được thuê thêm {self.left} máy."
        if p.get("stock") is not None and s["qty"] > lo("stock") and not adm:
            return "Đã hết hàng." if lo("stock") <= 0 else f"Chỉ còn {int(lo('stock'))} máy — chọn số lượng nhỏ hơn."
        if s["android"] not in and_list(p): return "Hãy chọn hệ điều hành (bản Android)."
        r = and_room(st, s["android"])
        if r is not None and not adm:
            if not r[0]: return f"Máy chủ Android {s['android']} đang bảo trì — chọn bản khác."
            if s["ram"] * s["qty"] > r[1] or s["cpu"] * s["qty"] > r[2]:
                return (f"Máy chủ Android {s['android']} chỉ còn trống {int(r[1])}GB RAM và {int(r[2])} nhân — chọn ít máy hơn, "
                        "cấu hình nhỏ hơn hoặc bản Android khác.")
        elif st and not adm and (s["ram"] * s["qty"] > num(st.get("free_ram")) or s["cpu"] * s["qty"] > num(st.get("free_cpu"))):
            return f"Máy chủ chỉ còn trống {int(num(st.get('free_ram')))}GB RAM và {int(num(st.get('free_cpu')))} nhân — chọn ít máy hơn hoặc cấu hình nhỏ hơn."
        return ""

    def upd(self):
        if not self.alive: return
        p, s = self.pr, self.s
        if s["android"] not in and_list(p) or (self.prof.get("role") != "admin" and and_why(self.st, s["android"], s["ram"], s["cpu"])):  # hết chỗ → tự đổi bản còn chỗ
            ok = [v for v in and_list(p) if not and_why(self.st, v, s["ram"], s["cpu"])                # chỉ đổi sang bản chứa VỪA cấu hình đang chọn
                  and s["ram"] <= and_lim(p, v)[0] and s["cpu"] <= and_lim(p, v)[1]]
            if ok:
                nv = "9" if "9" in ok else ok[0]
                if nv != s["android"]: s["android"] = nv; self.app.root.after_idle(lambda: self.alive and self.build())
        for r in self.rows: r.paint()
        bad, price, bal = self.check(), self.price(), num(self.prof.get("balance"))
        why = {v: and_why(self.st, v, *self.fit(v)) for v in and_list(p)}                  # giải thích vì sao bản Android bị mờ
        self.and_note.config(text="   ".join(f"Android {v}: " + ("máy chủ đang bảo trì" if w == "off" else "hết chỗ cho cấu hình này")
                                             for v, w in why.items() if w and self.prof.get("role") != "admin"))
        if s["free"]:
            self.calc.config(text=f"Miễn phí {int(num(p.get('free_days'))) or 1} ngày · Android {s['android']} · {s['ram']}GB · {s['cpu']} nhân")
        else:
            self.calc.config(text=f"({s['ram']}GB × {vnd(p.get('price_ram_gb_day'))} + {s['cpu']} nhân × {vnd(p.get('price_cpu_day'))}) × {s['days']} ngày"
                                  + (f" − {int(num(self.prof.get('ctv_discount')))}% CTV" if is_ctv(self.prof) else "") + (f" × {s['qty']} máy" if s["qty"] > 1 else ""))
        pz, bp = getattr(self, "promo", None), getattr(self, "bpay", None)
        if pz: pz.order_changed(); self._promo_code = pz.code
        price0 = price; price = pz.price(price0) if pz and not s["free"] else price0
        bu = bp.use(price) if bp and not s["free"] else 0
        if bp: bp.paint(price, s["free"]); self._blue_on = bool(bp.var.get())
        disc = price0 - price; price = price - bu
        if not s["free"] and (disc > 0 or bu > 0):
            self.calc.config(text=self.calc.cget("text") + (f"  ·  🏷️ −{vnd(disc)}" if disc > 0 else "") + (f"  ·  💎 −{blue_n(bu)} Blue" if bu > 0 else ""))
        self.total.config(text="—" if bad else vnd(price)); self.bal.config(text="Số dư: " + vnd(bal))
        warn = "" if bad else ("Số dư không đủ — cần nạp thêm " + vnd(price - bal) + "." if price > bal
                               else "⚠ Cấu hình này chưa đủ chơi game 3D (cần tối thiểu 4GB · 4 nhân) — hợp treo app, game nhẹ." if s["ram"] < 4 or s["cpu"] < 4 else "")
        self.err.config(text=bad or warn, fg=BAD if bad or price > bal else WARN)
        self.go.config(text="Nhận máy miễn phí" if s["free"] else ("Nạp tiền" if not bad and price > bal else "💎 Thuê bằng Blue" if price <= 0 and bu > 0
                                                                   else "Thuê ngay" + (f" {s['qty']} máy" if s["qty"] > 1 else "")),
                       state="disabled" if bad else "normal", bg=LINE if bad else ACC)

    def buy(self):
        bad = self.check()
        if bad: self.err.config(text=bad, fg=BAD); return
        if self.promo and not self.s["free"]: self.promo.ensure(self._buy, self.err)
        else: self._buy()

    def _buy(self):
        import tkinter.messagebox as mb
        s, price0, bal = self.s, self.price(), num(self.prof.get("balance"))
        pz, bp = (self.promo, self.bpay) if not s["free"] else (None, None)
        pay = pz.price(price0) if pz else price0; bu = bp.use(pay) if bp else 0; price = pay - bu; code = pz.send() if pz else None
        if not s["free"] and price > bal:
            need = price - bal; self.close(); self.app.open_topup(need); return
        what = f"Android {s['android']} · {s['qty']} máy · {s['ram']}GB · {s['cpu']} nhân · " + (f"{s['days']} ngày · " if not s["free"] else "") + f"{s['res']} · {s['fps']} FPS"
        extra = (f"\n🏷️ Mã {code}: −{vnd(price0 - pay)}" if code else "") + (f"\n💎 Trả {blue_n(bu)} Blue" if bu > 0 else "")
        if not mb.askyesno("Xác nhận thuê máy", what + extra + ("\n\nMáy miễn phí — không trừ tiền." if s["free"] else f"\n\nTrừ {vnd(price)} từ số dư?"), parent=self.win): return
        self.go.config(state="disabled", text="Đang tạo đơn…")
        args = {"p_ram": s["ram"], "p_cpu": s["cpu"], "p_days": s["days"], "p_res": s["res"], "p_name": None, "p_fps": s["fps"],
                "p_qty": 1 if s["free"] else s["qty"], "p_android": s["android"]}
        if s["free"]: args["p_free"] = True
        if code: args["p_promo"] = code
        if bu > 0: args["p_blue"] = True
        def done(_r):
            notify_admin(f"📱 <b>Đơn ĐT đám mây mới{' (MIỄN PHÍ)' if s['free'] else ''}</b> — app PC\n{s['qty']} máy × Android {s['android']} · "
                         f"{s['ram']}GB / {s['cpu']} nhân / {s['days']} ngày / {s['res']} / {s['fps']} FPS\nGiá: {vnd(price)}"
                         + (f" (mã {code})" if code else "") + (f" · 💎 {blue_n(bu)} Blue" if bu > 0 else "") + f"\n{self.app.auth.email}", self.app.auth)
            self._promo_code = ""; self._blue_on = False; BLUE["t"] = 0
            self.close(); self.app.refresh()
            mb.showinfo("CloudBlue", ("Đã tạo đơn " + str(s["qty"]) + " máy!" if s["qty"] > 1 else "Đã tạo đơn!") +
                        " Máy đang khởi tạo (khoảng 2–3 phút) — danh sách tự cập nhật khi máy chạy.", parent=self.app.root)
        def fail(m):
            if self.promo: self.promo.fail(m)
            if "Blue" in m: threading.Thread(target=lambda: (blue_load(self.app.auth), self.app.ui(lambda: self.alive and self.upd())), daemon=True).start()
            self.err.config(text=m, fg=BAD); self.upd()
        self.bg(lambda: self.app.auth.rpc("cloudphone_order_custom", args), done, fail)


class RenewDlg(Dlg):
    """Gia hạn 1 máy: chọn số ngày → trừ số dư (giá theo RAM/CPU của máy, có giảm CTV)."""
    def __init__(self, app, phone):
        super().__init__(app, "Gia hạn " + (phone.get("name") or "máy"), 540, 520)
        self.p = phone; self.days = 30
        self.loading("Đang tải giá…")
        self.bg(lambda: (app.shop.pricing(), app.shop.profile()), self._loaded, lambda m: self.loading(m))

    def _loaded(self, r):
        tk = self.app.tk; self.pr, self.prof = r; p = self.p; self.clear()
        mx = int(num(self.pr.get("max_days"))) or 90; self.days = min(30, mx)
        self.label(self.body, p.get("name") or "Máy", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, f"{p.get('ram')}GB RAM · {p.get('cpu')} nhân · Android {p.get('android') or '9'} · {fmt_left(p.get('expires_at'))}",
                   self.app.f_t, DIM, wraplength=490).pack(fill="x", padx=18)
        f = self.section("Gia hạn thêm", f"tối đa {mx} ngày")
        self.ch = Chips(self.app, f, [(d, f"{d} ngày") for d in RENEW_DAYS if d <= mx], lambda: self.days, lambda v: self._set(v, True), self.upd, wrap=4)
        self.ch.frame.pack(fill="x")
        line = tk.Frame(f, bg=BG); line.pack(fill="x", pady=(4, 0))
        self.label(line, "Số ngày khác:", self.app.f_s, DIM).pack(side="left")
        self.x = tk.Entry(line, width=6, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat"); self.x.pack(side="left", padx=6, ipady=4)
        def typed(_e=None):
            try: v = int(self.x.get())
            except ValueError: return
            if 1 <= v <= mx: self._set(v, False); self.upd()
        self.x.bind("<KeyRelease>", typed)
        f = self.section("Mã giảm giá · Blue")                # 🏷️ mã giảm giá (SQL v23) + 💎 trả bằng Blue (SQL v27)
        self.promo = PromoBox(self, f, "cp_renew", lambda: {"p_phone": self.p["id"], "p_days": self.days}, self.upd); self.promo.frame.pack(fill="x")
        self.bpay = BluePay(self, f, self.upd)
        ft = self.foot
        self.sum = self.label(ft, "", self.app.f_t, TXT); self.sum.pack(fill="x", padx=16, pady=(10, 0))
        self.err = self.label(ft, "", self.app.f_s, BAD, wraplength=500); self.err.pack(fill="x", padx=16)
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Gia hạn", self.renew); self.go.pack(side="right")
        self.upd()

    def _set(self, v, clear):
        self.days = v
        if clear: self.x.delete(0, "end")

    def total(self): return ctv(self.prof, per_day(self.pr, int(num(self.p.get("ram"))), int(num(self.p.get("cpu"))))) * self.days

    def pay(self):
        """(giá thường, giá sau mã, số Blue trừ, tiền trừ số dư)."""
        t0 = self.total(); pz, bp = getattr(self, "promo", None), getattr(self, "bpay", None)
        p1 = pz.price(t0) if pz else t0; bu = bp.use(p1) if bp else 0
        return t0, p1, bu, p1 - bu

    def upd(self):
        if not self.alive: return
        self.ch.paint()
        if getattr(self, "promo", None): self.promo.order_changed()
        per = ctv(self.prof, per_day(self.pr, int(num(self.p.get("ram"))), int(num(self.p.get("cpu"))))); bal = num(self.prof.get("balance"))
        t0, p1, bu, tot = self.pay()
        if getattr(self, "bpay", None): self.bpay.paint(p1)
        exp = parse_iso(self.p.get("expires_at")); base = max(now_utc(), exp) if exp else now_utc()
        new = (base + datetime.timedelta(days=self.days)).astimezone().strftime("%H:%M %d/%m/%Y")
        self.sum.config(text=f"Đơn giá {vnd(per)} / ngày" + (f" (CTV −{int(num(self.prof.get('ctv_discount')))}%)" if is_ctv(self.prof) else "")
                        + f"  ·  Hạn mới: {new}\nThanh toán: {vnd(tot)}" + (f" (🏷️ −{vnd(t0 - p1)})" if p1 < t0 else "")
                        + (f" (💎 −{blue_n(bu)} Blue)" if bu > 0 else "") + f"   ·   Số dư: {vnd(bal)}")
        self.err.config(text="" if tot <= bal else "Số dư không đủ — cần nạp thêm " + vnd(tot - bal) + ".")
        self.go.config(text=("💎 " if tot <= 0 and bu > 0 else "") + f"Gia hạn {self.days} ngày" if tot <= bal else "Nạp tiền")

    def renew(self): self.promo.ensure(self._renew, self.err)

    def _renew(self):
        import tkinter.messagebox as mb
        t0, p1, bu, tot = self.pay(); bal = num(self.prof.get("balance")); code = self.promo.send()
        if tot > bal: self.close(); self.app.open_topup(tot - bal); return
        extra = (f"\n🏷️ Mã {code}: −{vnd(t0 - p1)}" if code else "") + (f"\n💎 Trả {blue_n(bu)} Blue" if bu > 0 else "")
        if not mb.askyesno("Gia hạn", f"Gia hạn “{self.p.get('name')}” thêm {self.days} ngày, trừ {vnd(tot)} từ số dư?" + extra, parent=self.win): return
        self.go.config(state="disabled", text="Đang gia hạn…"); d = self.days
        args = {"p_id": self.p["id"], "p_days": d}
        if code: args["p_promo"] = code
        if bu > 0: args["p_blue"] = True
        def done(_r):
            BLUE["t"] = 0; self.close(); self.app.refresh()
            mb.showinfo("CloudBlue", f"Đã gia hạn +{d} ngày.", parent=self.app.root)
        def fail(m):
            self.promo.fail(m); self.err.config(text=m); self.go.config(state="normal"); self.upd()
        self.bg(lambda: self.app.auth.rpc("cloudphone_renew", args), done, fail)


class TopupDlg(Dlg):
    """Nạp tiền bằng chuyển khoản: tạo mã nạp (create_topup) → mã VietQR → tự kiểm tra 5 giây/lần, ngân hàng báo có là cộng số dư."""
    def __init__(self, app, need=0):
        super().__init__(app, "Nạp tiền", 600, 640)
        self.need = need; self.top = None
        self.loading()
        self.bg(lambda: (app.shop.site(), app.shop.profile()), self._loaded, lambda m: self.loading(m))

    def _loaded(self, r):
        tk = self.app.tk; self.site, self.prof = r; self.clear()
        self.min = max(1000, int(num(self.site.get("minTop")) or 10000))
        amt = max(self.min, int(-(-self.need // 1000) * 1000)) if self.need > 0 else max(self.min, 50000)
        self.amt = amt
        self.label(self.body, "Nạp tiền vào tài khoản", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, "Số dư hiện tại: " + vnd(self.prof.get("balance")) + (f"   ·   Cần thêm {vnd(self.need)}" if self.need > 0 else ""),
                   self.app.f_t, DIM).pack(fill="x", padx=18)
        f = self.section("Số tiền nạp", f"tối thiểu {vnd(self.min)}")
        items = sorted(set([a for a in TOP_AMTS if a >= self.min] + ([amt] if self.need > 0 else [])))
        self.ch = Chips(self.app, f, [(a, vnd(a)) for a in items], lambda: self.amt, lambda v: (setattr(self, "amt", v), self.x.delete(0, "end")), self.upd, wrap=3)
        self.ch.frame.pack(fill="x")
        line = tk.Frame(f, bg=BG); line.pack(fill="x", pady=(6, 0))
        self.label(line, "Số khác:", self.app.f_s, DIM).pack(side="left")
        self.x = tk.Entry(line, width=12, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat"); self.x.pack(side="left", padx=6, ipady=4)
        self.label(line, "đ", self.app.f_t, DIM).pack(side="left")
        def typed(_e=None):
            v = int(re.sub(r"\D", "", self.x.get()) or 0)
            if v: self.amt = v; self.upd()
        self.x.bind("<KeyRelease>", typed)
        self.label(self.body, "Chuyển khoản ngân hàng: quét mã QR bằng app ngân hàng bất kỳ, tiền tự cộng vào số dư sau khoảng 1 phút.",
                   self.app.f_s, DIM, wraplength=540).pack(fill="x", padx=18, pady=(14, 4))
        lk = self.label(self.body, "Nạp bằng USDT / LTC trên web ↗", self.app.f_s, ACC, cursor="hand2"); lk.pack(fill="x", padx=18)
        lk.bind("<Button-1>", lambda e: webbrowser.open(WEB + "/?topup=1"))
        ft = self.foot
        self.err = self.label(ft, "", self.app.f_s, BAD, wraplength=540); self.err.pack(fill="x", padx=16, pady=(8, 0))
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(4, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Tạo mã chuyển khoản", self.make); self.go.pack(side="right")
        if not str(self.site.get("bankAcc") or "").strip():
            self.err.config(text="Shop chưa cài tài khoản ngân hàng — tạm thời nạp trên web."); self.go.config(state="disabled", bg=LINE)
        self.upd()

    def upd(self):
        self.ch.paint()
        if self.top is None and hasattr(self, "go") and str(self.site.get("bankAcc") or "").strip():
            ok = self.amt >= self.min
            self.err.config(text="" if ok else "Số tiền tối thiểu là " + vnd(self.min) + ".")
            self.go.config(text=f"Tạo mã chuyển khoản {vnd(self.amt)}", state="normal" if ok else "disabled", bg=ACC if ok else LINE)

    def make(self):
        if self.amt < self.min: return
        self.go.config(state="disabled", text="Đang tạo mã…"); a = self.amt
        def fail(m): self.err.config(text=m); self.upd()
        self.bg(lambda: self.app.auth.rpc("create_topup", {"p_amount": a}), self._pay, fail)

    def _pay(self, t):
        tk = self.app.tk; self.top = t or {}; self.clear(); self.win.title("Chuyển khoản " + vnd(self.top.get("amount")))
        bin_ = str(self.site.get("bankBin") or "970422"); acc = re.sub(r"\D", "", str(self.site.get("bankAcc") or ""))
        name = str(self.site.get("bankName") or ""); amount = int(num(self.top.get("amount"))); memo = str(self.top.get("memo") or "")
        wrap = tk.Frame(self.body, bg=BG); wrap.pack(fill="x", padx=18, pady=16)
        cv = tk.Canvas(wrap, bg="white", highlightthickness=0)
        try:
            import qrcodegen
            q = qrcodegen.QrCode.encode_text(vietqr(bin_, acc, amount, memo), qrcodegen.QrCode.Ecc.MEDIUM)
            n = q.get_size(); sc = max(3, 248 // (n + 8)); side = (n + 8) * sc
            cv.config(width=side, height=side)
            for y in range(n):
                for x in range(n):
                    if q.get_module(x, y): cv.create_rectangle((x + 4) * sc, (y + 4) * sc, (x + 5) * sc, (y + 5) * sc, fill="black", width=0)
        except Exception:
            log("qr:", traceback.format_exc()); cv.config(width=248, height=60, bg=CARD)
            cv.create_text(124, 30, text="Không tạo được mã QR —\nchuyển khoản theo thông tin bên cạnh", fill=TXT, font=self.app.f_s)
        cv.pack(side="left", anchor="n")
        info = tk.Frame(wrap, bg=BG); info.pack(side="left", fill="both", expand=True, padx=(16, 0))
        def row(lab, val, copy=None, big=False, col=TXT):
            r = tk.Frame(info, bg=BG); r.pack(fill="x", pady=3)
            self.label(r, lab, self.app.f_s, DIM).pack(fill="x")
            vr = tk.Frame(r, bg=BG); vr.pack(fill="x")
            self.label(vr, val, ("Segoe UI", 13 if big else 11, "bold"), col).pack(side="left")
            if copy: self.app.btn(vr, "Chép", lambda: self.copy(copy), "soft", padx=8, pady=2).pack(side="right")
        row("Ngân hàng", BANKS.get(bin_, bin_)); row("Số tài khoản", acc, acc); row("Chủ tài khoản", name)
        row("Số tiền", vnd(amount), str(amount)); row("Nội dung chuyển khoản (ghi ĐÚNG)", memo, memo, True, WARN)
        self.label(self.body, "Mở app ngân hàng → Quét mã QR: số tiền và nội dung tự điền. Chuyển tay thì ghi đúng nội dung ở trên, "
                              "nếu không tiền sẽ không tự cộng. Mã có hiệu lực 20 phút.", self.app.f_s, DIM, wraplength=540).pack(fill="x", padx=18)
        ft = self.foot
        self.state = self.label(ft, "⏳ Đang chờ ngân hàng báo có… (tự kiểm tra, không cần bấm gì)", ("Segoe UI", 10, "bold"), WARN, wraplength=540)
        self.state.pack(fill="x", padx=16, pady=(10, 0))
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.done_btn = self.app.btn(bb, "Đóng", self.close, "soft"); self.done_btn.pack(side="right")
        threading.Thread(target=self._poll, daemon=True).start()

    def copy(self, v):
        try: self.app.root.clipboard_clear(); self.app.root.clipboard_append(v)
        except Exception: pass
        if hasattr(self, "state") and self.state.winfo_exists(): self.state.config(text=f"Đã chép: {v}   ·   ⏳ vẫn đang chờ ngân hàng báo có…", fg=WARN)

    def _poll(self):
        t0, tid = time.time(), self.top.get("id")
        while self.alive and time.time() - t0 < 25 * 60:
            time.sleep(5)
            if not self.alive: return
            try: rows = self.app.auth.rest(f"topups?id=eq.{tid}&select=status,amount") or []
            except Exception: continue
            if rows and rows[0].get("status") == "done":
                amt = rows[0].get("amount"); self.app.ui(lambda: self._done(amt)); return
            if not rows and time.time() - t0 > 60:
                self.app.ui(lambda: self.alive and self.state.config(
                    text="Mã nạp này đã hết hạn. Nếu bạn đã chuyển tiền mà chưa được cộng, liên hệ hỗ trợ kèm nội dung chuyển khoản.", fg=BAD)); return
        if self.alive:
            self.app.ui(lambda: self.alive and self.state.config(
                text="Chưa thấy tiền về. Nếu đã chuyển đúng nội dung mà quá 15 phút chưa cộng, liên hệ hỗ trợ kèm nội dung chuyển khoản.", fg=BAD))

    def _done(self, amt):
        if not self.alive: return
        self.state.config(text=f"✓ Đã nhận {vnd(amt)} — số dư đã được cộng.", fg=OK)
        self.done_btn.config(text="Xong", bg=ACC)
        self.app.refresh()


class UpgradeDlg(Dlg):
    """Nâng RAM / CPU cho máy đang chạy: trả thêm cho thời gian còn lại (máy chủ tính giá, có giảm CTV) — app và dữ liệu giữ nguyên."""
    def __init__(self, app, phone):
        super().__init__(app, "Nâng cấp " + (phone.get("name") or "máy"), 560, 560)
        self.p = phone; self.r0, self.c0 = int(num(phone.get("ram"))), int(num(phone.get("cpu"))); self.nr, self.nc = self.r0, self.c0
        self.cost, self.qid = 0, 0
        self.loading("Đang tải giá…")
        self.bg(lambda: (app.shop.pricing(), app.shop.profile()), self._loaded, lambda m: self.loading(m))

    def _loaded(self, r):
        tk = self.app.tk; self.pr, self.prof = r; p = self.p; self.clear()
        mr, mc = and_lim(self.pr, p.get("android") or "9")                 # trần theo bản Android của máy
        self.label(self.body, p.get("name") or "Máy", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, f"Hiện tại {self.r0}GB RAM · {self.c0} nhân · {fmt_left(p.get('expires_at'))}", self.app.f_t, DIM, wraplength=500).pack(fill="x", padx=18)
        rams = sorted({v for v in (2, 3, 4, 6, 8, 10, 12, 16, mr) if self.r0 < v <= mr})
        cpus = sorted({v for v in (2, 3, 4, 6, 8, 10, 12, 16, mc) if self.c0 < v <= mc})
        f = self.section("RAM")
        self.cr = Chips(self.app, f, [(self.r0, f"Giữ {self.r0}GB")] + [(v, f"{v}GB") for v in rams], lambda: self.nr, lambda v: setattr(self, "nr", v), self.upd, wrap=7)
        self.cr.frame.pack(fill="x")
        if not rams: self.label(f, "RAM đã tối đa.", self.app.f_s, DIM).pack(fill="x")
        f = self.section("CPU")
        self.cc = Chips(self.app, f, [(self.c0, f"Giữ {self.c0} nhân")] + [(v, f"{v} nhân") for v in cpus], lambda: self.nc, lambda v: setattr(self, "nc", v), self.upd, wrap=7)
        self.cc.frame.pack(fill="x")
        if not cpus: self.label(f, "CPU đã tối đa.", self.app.f_s, DIM).pack(fill="x")
        f = self.section("Mã giảm giá")                       # 🏷️ mã giảm giá cho nâng cấp (SQL v23)
        self.promo = PromoBox(self, f, "cp_upgrade", lambda: None if (self.nr, self.nc) == (self.r0, self.c0)
                              else {"p_phone": self.p["id"], "p_ram": self.nr, "p_cpu": self.nc}, self._draw); self.promo.frame.pack(fill="x")
        self.label(self.body, "Máy tự khởi động lại khoảng 1 phút để nhận cấu hình mới — app và dữ liệu giữ nguyên. "
                              "Các lần gia hạn sau tính theo cấu hình mới.", self.app.f_s, DIM, wraplength=510).pack(fill="x", padx=18, pady=(14, 10))
        ft = self.foot
        self.sum = self.label(ft, "", self.app.f_t, TXT); self.sum.pack(fill="x", padx=16, pady=(10, 0))
        self.err = self.label(ft, "", self.app.f_s, BAD, wraplength=500); self.err.pack(fill="x", padx=16)
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Nâng cấp ngay", self.upgrade); self.go.pack(side="right")
        self.upd()

    def _local_quote(self):
        """Giá dự tính giống web (máy chủ vẫn tính lại chính xác lúc trừ tiền)."""
        exp = parse_iso(self.p.get("expires_at")); left = max(0.0, (exp - now_utc()).total_seconds() / 86400) if exp else 0.0
        raw = round(((self.nr - self.r0) * num(self.pr.get("price_ram_gb_day")) + (self.nc - self.c0) * num(self.pr.get("price_cpu_day"))) * left)
        pct = num(self.prof.get("ctv_discount")) if is_ctv(self.prof) else 0
        return int(-(-(raw * (100 - pct)) // 100))

    def upd(self):
        self.cr.paint(); self.cc.paint()
        same = self.nr == self.r0 and self.nc == self.c0
        if same: self.cost = 0; self._draw(); return
        self.cost = self._local_quote(); self._draw()
        self.qid += 1; q, nr, nc = self.qid, self.nr, self.nc
        def got(v):
            if q != self.qid: return
            try: self.cost = int(num(v))
            except Exception: pass
            self._draw()
        self.bg(lambda: self.app.auth.rpc("cloudphone_upgrade_quote", {"p_id": self.p["id"], "p_ram": nr, "p_cpu": nc}), got, lambda m: None)

    def _pay(self):
        pz = getattr(self, "promo", None)
        return pz.price(self.cost) if pz and (self.nr, self.nc) != (self.r0, self.c0) else self.cost

    def _draw(self):
        if not self.alive: return
        same = self.nr == self.r0 and self.nc == self.c0; bal = num(self.prof.get("balance"))
        if getattr(self, "promo", None) and not same: self.promo.order_changed()
        pay = self._pay()
        self.sum.config(text="Chọn RAM hoặc CPU muốn nâng." if same else
                        f"Cấu hình mới: {self.nr}GB RAM · {self.nc} nhân\nTrả thêm cho thời gian còn lại: {vnd(pay)}"
                        + (f" (🏷️ −{vnd(self.cost - pay)})" if pay < self.cost else "") + f"   ·   Số dư: {vnd(bal)}")
        self.err.config(text="" if same or pay <= bal else "Số dư không đủ — cần nạp thêm " + vnd(pay - bal) + ".")
        self.go.config(state="disabled" if same else "normal", bg=LINE if same else ACC, text="Nạp tiền" if not same and pay > bal else "Nâng cấp ngay")

    def upgrade(self):
        if self.nr == self.r0 and self.nc == self.c0: return
        self.promo.ensure(self._upgrade, self.err)

    def _upgrade(self):
        import tkinter.messagebox as mb
        bal = num(self.prof.get("balance")); pay = self._pay(); code = self.promo.send()
        if pay > bal: need = pay - bal; self.close(); self.app.open_topup(need); return
        if not mb.askyesno("Nâng cấp", f"Nâng “{self.p.get('name')}” lên {self.nr}GB RAM · {self.nc} nhân, trừ khoảng {vnd(pay)} từ số dư?"
                                       + (f" (mã {code})" if code else "") + "\nMáy sẽ tự khởi động lại khoảng 1 phút.", parent=self.win): return
        self.go.config(state="disabled", text="Đang nâng cấp…"); nr, nc = self.nr, self.nc
        def done(_r):
            self.close(); self.app.refresh()
            mb.showinfo("CloudBlue", f"Đã nâng lên {nr}GB · {nc} nhân — máy nhận cấu hình mới trong khoảng 1 phút.", parent=self.app.root)
        def fail(m):
            self.promo.fail(m); self.err.config(text=m); self.go.config(state="normal"); self._draw()
        args = {"p_id": self.p["id"], "p_ram": nr, "p_cpu": nc}
        if code: args["p_promo"] = code
        self.bg(lambda: self.app.auth.rpc("cloudphone_upgrade", args), done, fail)


class SwitchDlg(Dlg):
    """Đổi Android 9 / 12 / 15 (SQL v24 + v28): máy MỚI miễn phí, giữ nguyên hạn — v28: máy cũ + TOÀN BỘ dữ liệu bị xoá NGAY, xoá xong mới tạo máy mới.
       Bản mới có trần thấp hơn (Android 9: 8GB · 8 nhân) → máy mới tự hạ, không hoàn tiền phần chênh."""
    def __init__(self, app, phone):
        super().__init__(app, "Đổi Android — " + (phone.get("name") or "máy"), 560, 600)
        self.p = phone; self.v = None; self.vers = []
        self.loading("Đang tải…")
        self.bg(lambda: app.shop.pricing(), self._loaded, lambda m: self.loading(m))

    def _loaded(self, pr):
        tk = self.app.tk; self.pr = pr; p = self.p; self.clear()
        cur = str(p.get("android") or "9")
        self.vers = [v for v in dict.fromkeys(x.strip() for x in str(pr.get("android_versions") or "9").split(",")) if v and v != cur]
        self.label(self.body, p.get("name") or "Máy", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, f"Đang dùng Android {cur} · {p.get('ram')}GB · {p.get('cpu')} nhân · {fmt_left(p.get('expires_at'))}",
                   self.app.f_t, DIM, wraplength=500).pack(fill="x", padx=18)
        bb = tk.Frame(self.foot, bg=CARD)
        if not self.vers:
            self.label(self.body, "Chưa có bản Android nào khác để đổi.", self.app.f_t, DIM).pack(fill="x", padx=18, pady=14)
            bb.pack(fill="x", padx=16, pady=12); self.app.btn(bb, "Đóng", self.close, "soft").pack(side="right"); return
        self.v = "12" if "12" in self.vers else self.vers[0]
        f = self.section("Đổi sang")
        self.cv = Chips(self.app, f, [(v, f"Android {v}") for v in self.vers], lambda: self.v, lambda x: setattr(self, "v", x), self.upd, wrap=4)
        self.cv.frame.pack(fill="x")
        self.note = self.label(self.body, "", self.app.f_s, DIM, wraplength=510); self.note.pack(fill="x", padx=18, pady=(8, 0))
        w = tk.Frame(self.body, bg=CARD, highlightbackground=BAD, highlightthickness=1); w.pack(fill="x", padx=18, pady=(12, 4))
        self.label(w, "⚠ Đổi hệ điều hành sẽ XOÁ SẠCH toàn bộ dữ liệu trong máy: app, game, tài khoản đã đăng nhập, ảnh, file — không khôi phục được.",
                   ("Segoe UI", 10, "bold"), BAD, wraplength=500).pack(fill="x", padx=10, pady=(8, 2))
        self.label(w, "Bấm Đổi là máy cũ bị XOÁ NGAY (không mở được nữa), xoá xong mới tạo máy mới — khoảng 2–5 phút. Máy mới miễn phí, giữ nguyên hạn dùng.",
                   self.app.f_s, TXT, wraplength=500).pack(fill="x", padx=10, pady=(0, 8))
        self.okv = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Tôi hiểu, toàn bộ dữ liệu trong máy sẽ bị xoá", variable=self.okv, command=self.upd, font=self.app.f_t,
                       fg=TXT, bg=BG, selectcolor=CARD, activebackground=BG, activeforeground=TXT, anchor="w", cursor="hand2").pack(fill="x", padx=14, pady=(8, 12))
        self.err = self.label(self.foot, "", self.app.f_s, BAD, wraplength=500); self.err.pack(fill="x", padx=16, pady=(8, 0))
        bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Đổi", self.switch); self.go.pack(side="right")
        self.upd()

    def new_cfg(self, v):
        mr, mc = and_lim(self.pr, v); r0, c0 = int(num(self.p.get("ram"))), int(num(self.p.get("cpu")))
        return min(r0, mr), min(c0, mc), mr, mc

    def upd(self):
        if not self.v: return
        self.cv.paint()
        r, c, mr, mc = self.new_cfg(self.v); red = r < int(num(self.p.get("ram"))) or c < int(num(self.p.get("cpu")))
        t = (f"Android {self.v} tối đa {mr}GB · {mc} nhân → máy mới sẽ hạ còn {r}GB · {c} nhân, không hoàn tiền phần chênh." if red
             else f"Máy mới: Android {self.v} · {r}GB · {c} nhân · {self.p.get('res') or ''} · {self.p.get('fps') or 30} FPS")
        if self.v == "15": t += "\nLưu ý: có khách báo Android 15 không vào được Google / Play Store — cần Google thì chọn Android 12."
        self.note.config(text=t, fg=WARN if red else DIM)
        on = bool(self.okv.get())
        self.go.config(text=f"Đổi sang Android {self.v}", state="normal" if on else "disabled", bg=BAD if on else LINE)

    def switch(self):
        import tkinter.messagebox as mb
        if not self.v or not self.okv.get(): return
        v = self.v; self.go.config(state="disabled", text="Đang gửi…"); self.err.config(text="")
        def done(_r):
            self.close(); self.app.refresh()
            mb.showinfo("CloudBlue", f"Đang xoá máy cũ… xoá xong tự tạo máy Android {v} (2–5 phút).", parent=self.app.root)
        def fail(m):
            self.err.config(text=m); self.upd()
        self.bg(lambda: self.app.auth.rpc("cloudphone_switch_android", {"p_id": self.p["id"], "p_android": v}), done, fail)


APP_NAMES = {"com.roblox.client": "Roblox", "com.facebook.katana": "Facebook", "com.zing.zalo": "Zalo", "org.telegram.messenger": "Telegram",
             "com.zhiliaoapp.musically": "TikTok", "com.ss.android.ugc.trill": "TikTok", "com.android.chrome": "Chrome",
             "com.termux": "Termux", "com.termux.api": "Termux:API", "com.termux.boot": "Termux:Boot", "bin.mt.plus": "MT Manager",
             "org.mozilla.firefox": "Firefox", "com.discord": "Discord", "com.whatsapp": "WhatsApp", "com.google.android.youtube": "YouTube"}


def app_label(pkg): return APP_NAMES.get(pkg, pkg)


def missing(m):
    """Máy chủ chưa lên bản có chức năng này → nói rõ thay vì lỗi khó hiểu."""
    return "Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau." if "Không có chức năng" in (m or "") else m


class ToolsDlg(Dlg):
    """CÔNG CỤ của 1 máy — đủ như bảng Công cụ của app điện thoại, chia thẻ:
       Màn hình: xoay ngang / dọc, độ rộng nhỏ nhất · Cài app: file APK / file khác / link · Ứng dụng: mở, dừng, xoá dữ liệu, gỡ
       · Clone tab: chạy thêm bản 2, 3… của 1 app (VD Roblox chính thức), mỗi bản 1 hồ sơ riêng để đăng nhập acc khác
       · Khác: mở link, vị trí GPS, chụp màn, nút nguồn, root, khởi động lại. Gọi cpapi qua đường thẳng tới máy chủ (CpClient)."""
    TABS = [("screen", "Màn hình"), ("install", "Cài app"), ("store", "Kho app"), ("apps", "Ứng dụng"), ("clone", "Clone tab"), ("root", "Root"), ("more", "Khác")]
    SW = [320, 360, 411, 480, 540, 600, 720, 800]

    def __init__(self, app, phone, tab=None):
        super().__init__(app, "Công cụ — " + (phone.get("name") or "máy"), 640, 720)
        self.p = phone; self.cp = CpClient(app.auth, phone["id"]); self.busy = False
        self.pkg, self.n, self.apps, self.counts, self.max = None, 1, [], {}, 4
        self.dens = None; self.dens_busy = False; self.loaded = set(); self.jobs_on = set()
        tk = app.tk; names = dict(self.TABS)
        if tab not in names: tab = prefs().get("tools_tab")
        self.tab = tab if tab in names else "screen"
        hdr = tk.Frame(self.win, bg=BG); hdr.pack(side="top", fill="x", padx=16, pady=(12, 0), before=self.body.master.master)   # thẻ đứng yên, phần dưới cuộn
        self.c_tab = Chips(app, hdr, self.TABS, lambda: self.tab, lambda v: setattr(self, "tab", v), self._show_tab)
        self.c_tab.frame.pack(fill="x")
        self.pages = {k: tk.Frame(self.body, bg=BG) for k in names}
        self._page_screen(); self._page_install(); self._page_store(); self._page_apps(); self._page_clone(); self._page_root(); self._page_more()
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=10)
        self.app.btn(bb, "Làm mới", self.refresh, "soft").pack(side="left")
        self.app.btn(bb, "Đóng", self.close, "soft").pack(side="right")
        self._show_tab()

    def close(self):
        super().close()
        if getattr(self.app, "tools_only", False):
            try: self.app.root.destroy()
            except Exception: pass

    def say(self, lbl, text, col=TXT):
        if self.alive and lbl.winfo_exists(): lbl.config(text=text, fg=col)

    def muted(self, parent, text):
        self.label(parent, text, self.app.f_s, DIM, wraplength=580).pack(fill="x")

    def msg(self, parent, pady=(8, 0)):
        lb = self.label(parent, "", ("Segoe UI", 10, "bold"), TXT, wraplength=580); lb.pack(fill="x", pady=pady)
        return lb

    def _show_tab(self):
        for f in self.pages.values(): f.pack_forget()
        self.pages[self.tab].pack(fill="x", pady=(0, 16))
        self.c_tab.paint(); prefs({"tools_tab": self.tab})
        cv = self.app.scrollers.get(str(self.win))
        if cv is not None:
            try: cv.yview_moveto(0)
            except Exception: pass
        if self.tab not in self.loaded: self.refresh()

    def refresh(self):
        """Đọc lại dữ liệu của thẻ đang mở (màn hình máy / danh sách app)."""
        self.loaded.add(self.tab)
        if self.tab == "screen": self.load_density()
        elif self.tab in ("apps", "clone"): self.loaded.update(("apps", "clone")); self.load()
        elif self.tab == "root": self.load_root()
        elif self.tab == "store": self.load_store()

    def _bgjob(self, lbl, start, first):
        """Việc chạy lâu trên máy chủ (root, khởi động lại…): gửi → theo dõi mã việc → báo kết quả vào lbl."""
        if lbl in self.jobs_on: return
        self.jobs_on.add(lbl); self.say(lbl, first, WARN)
        def job():
            try:
                j = start()
                msg = self.cp.wait_job(j["job"], lambda m: self.app.ui(lambda: self.say(lbl, m, WARN))) if j.get("job") else (j.get("msg") or "Xong.")
                self.app.ui(lambda: self.say(lbl, ("" if msg[:1] in ("✅", "⏳") else "✓ ") + msg, OK))
            except Exception as e:
                m = str(e) or "Có lỗi."; log("tools job:", m); self.app.ui(lambda: self.say(lbl, "✗ " + missing(m), BAD))
            finally:
                self.app.ui(lambda: self.jobs_on.discard(lbl))
        threading.Thread(target=job, daemon=True).start()

    # ================= thẻ MÀN HÌNH: xoay + độ rộng nhỏ nhất =================
    def _page_screen(self):
        tk = self.app.tk; pg = self.pages["screen"]
        f = self.section("Xoay màn", parent=pg)
        self.muted(f, "Khoá màn máy NGANG hoặc DỌC (giữ luôn cả khi tắt app). Game chỉ chạy màn ngang (VD Roblox) vẫn tự xoay ngang. "
                      "Cửa sổ máy trên máy tính tự xoay theo — không phải nghiêng đầu.")
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(8, 0))
        self.app.btn(r, "▭  Màn ngang", lambda: self.rotate("land")).pack(side="left")
        self.app.btn(r, "▯  Màn dọc", lambda: self.rotate("port"), "soft").pack(side="left", padx=(8, 0))
        self.rot_msg = self.msg(f)
        f = self.section("Độ rộng nhỏ nhất (Smallest width)", parent=pg)
        self.muted(f, "Như \"Độ rộng nhỏ nhất\" trong Tuỳ chọn nhà phát triển của Android: số càng LỚN thì chữ, biểu tượng, cửa sổ app càng NHỎ — "
                      "màn chứa được nhiều hơn (VD xếp nhiều tab clone). Số càng nhỏ thì mọi thứ càng to.")
        self.dens_now = self.label(f, "Đang đọc màn hình máy…", ("Segoe UI", 11, "bold"), TXT); self.dens_now.pack(fill="x", pady=(8, 2))
        self.c_sw = Chips(self.app, f, [(v, f"{v} dp") for v in self.SW], lambda: (self.dens or {}).get("sw"), self.set_density, lambda: None, wrap=4)
        self.c_sw.frame.pack(fill="x", pady=(4, 0))
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(8, 0))
        self.label(r, "Số khác (240 – 1600):", self.app.f_t, DIM).pack(side="left")
        self.sw_ent = tk.Entry(r, font=("Segoe UI", 11), width=7, bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
        self.sw_ent.pack(side="left", padx=6, ipady=5); self.sw_ent.bind("<Return>", lambda e: self.custom_density())
        self.app.btn(r, "Đặt", self.custom_density).pack(side="left")
        self.sw_reset = self.app.btn(r, "Trả về mặc định", lambda: self.set_density(0, True), "soft"); self.sw_reset.pack(side="right")
        self.dens_msg = self.msg(f)

    def rotate(self, to):
        land = to == "land"; self.say(self.rot_msg, "Đang xoay ngang…" if land else "Đang xoay dọc…", WARN)
        def ok(j):
            m = j.get("msg") or ("Đã khoá màn NGANG." if land else "Đã khoá màn DỌC.")
            self.say(self.rot_msg, "✓ " + m + (" App / game hỗ trợ ngang sẽ hiện ngang; app chỉ chạy màn dọc thì vẫn dọc." if land else ""), OK)
        self.bg(lambda: self.cp.json("POST", "rotate", {"to": to, "dir": 1 if land else 0}, timeout=30), ok,
                lambda m: self.say(self.rot_msg, "✗ " + missing(m), BAD))

    def _paint_density(self):
        d = self.dens or {}
        if d.get("sw"): self.say(self.dens_now, f"Đang dùng: {d['sw']} dp" + (f"   ·   mặc định của máy: {d['sw_default']} dp" if d.get("sw_default") else ""), TXT)
        if self.sw_reset.winfo_exists(): self.sw_reset.config(text=f"Trả về mặc định ({d['sw_default']} dp)" if d.get("sw_default") else "Trả về mặc định")
        self.c_sw.paint()

    def load_density(self):
        self.say(self.dens_now, "Đang đọc màn hình máy…", DIM)
        def got(j):
            self.dens = j; self._paint_density()
        self.bg(lambda: self.cp.json("GET", "density", timeout=30), got, lambda m: self.say(self.dens_now, "✗ " + missing(m), BAD))

    def custom_density(self):
        try: v = int(self.sw_ent.get().strip())
        except ValueError: v = 0
        if not 240 <= v <= 1600: self.say(self.dens_msg, "Nhập số từ 240 đến 1600 (dp).", BAD); return
        self.set_density(v)

    def set_density(self, sw, reset=False):
        if self.dens_busy: return
        self.dens_busy = True
        self.say(self.dens_msg, "Đang trả về mặc định…" if reset else f"Đang đặt {sw} dp…", WARN)
        def ok(j):
            self.dens_busy = False
            if j.get("sw"): self.dens = j
            self._paint_density(); self.say(self.dens_msg, "✓ " + (j.get("msg") or "Đã đổi."), OK)
        def fail(m):
            self.dens_busy = False; self.say(self.dens_msg, "✗ " + missing(m), BAD)
        self.bg(lambda: self.cp.json("POST", "density", {"reset": True} if reset else {"sw": int(sw)}, timeout=40), ok, fail)

    # ================= thẻ CÀI APP: file APK / file khác / link =================
    def _page_install(self):
        tk = self.app.tk; pg = self.pages["install"]
        f = self.section("Cài app / chép file vào máy", parent=pg)
        self.muted(f, "File .apk / .apks / .xapk / .apkm → cài vào máy. File khác (ảnh, video, tài liệu…) → chép vào thư mục Download của máy.")
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(8, 0))
        self.pick_btn = self.app.btn(r, "Chọn file trên máy tính…", self.pick); self.pick_btn.pack(side="left")
        lr = tk.Frame(f, bg=BG); lr.pack(fill="x", pady=(8, 0))
        self.link = tk.Entry(lr, font=("Segoe UI", 10), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
        self.link.pack(side="left", fill="x", expand=True, ipady=6)
        self.link_btn = self.app.btn(lr, "Cài từ link", self.from_link, "soft"); self.link_btn.pack(side="left", padx=(6, 0))
        self.label(f, "Link tải trực tiếp file (thường kết thúc bằng .apk), không phải link trang web.", self.app.f_s, DIM).pack(fill="x", pady=(2, 0))
        self.up_msg = self.msg(f)

    def pick(self):
        from tkinter import filedialog
        if self.busy: return
        fp = filedialog.askopenfilename(parent=self.win, title="Chọn file để cài / chép vào máy",
                                        filetypes=[("App Android", "*.apk *.apks *.xapk *.apkm"), ("Tất cả file", "*.*")])
        if not fp: return
        mb_ = os.path.getsize(fp) / 1048576
        if mb_ > 4096: self.say(self.up_msg, "File lớn hơn 4GB — không gửi được.", BAD); return
        self._run_upload(lambda prog: self.cp.upload(fp, prog), os.path.basename(fp))

    def from_link(self):
        u = self.link.get().strip()
        if self.busy or not u: return
        if not re.match(r"^https?://\S+$", u): self.say(self.up_msg, "Link phải bắt đầu bằng http:// hoặc https://", BAD); return
        self._run_upload(lambda prog: self.cp.json("POST", "fromurl", {"url": u}).get("job"), u[-60:])

    def _run_upload(self, start, title):
        self.busy = True
        for b in (self.pick_btn, self.link_btn): b.config(state="disabled")
        self.say(self.up_msg, f"Đang gửi {title}…", WARN)
        t0 = [time.time()]
        def prog(done, total):
            sp = done / max(0.5, time.time() - t0[0]) / 1048576
            self.app.ui(lambda: self.say(self.up_msg, f"Đang tải lên {done * 100 // total}%  ({done / 1048576:.1f} / {total / 1048576:.1f} MB · {sp:.1f} MB/s)…", WARN))
        def job():
            try:
                jid = start(prog)
                if not jid: raise ApiError(0, "Máy chủ chưa nhận việc — thử lại.")
                self.app.ui(lambda: self.say(self.up_msg, "Đang cài / chép vào máy…", WARN))
                msg = self.cp.wait_job(jid, lambda m: self.app.ui(lambda: self.say(self.up_msg, m, WARN)))
                self.app.ui(lambda: (self.say(self.up_msg, "✓ " + msg, OK), self.loaded.difference_update(("apps", "clone"))))
            except Exception as e:
                m = str(e) or "Có lỗi."; log("tools upload:", traceback.format_exc())
                self.app.ui(lambda: self.say(self.up_msg, "✗ " + m, BAD))
            finally:
                def done():
                    self.busy = False
                    for b in (self.pick_btn, self.link_btn):
                        if b.winfo_exists(): b.config(state="normal")
                self.app.ui(done)
        threading.Thread(target=job, daemon=True).start()

    # ================= danh sách app (dùng chung cho thẻ Ứng dụng + Clone tab) =================
    def load(self):
        for box in (self.clone_box, self.apps_box):
            for w in box.winfo_children(): w.destroy()
            self.label(box, "Đang đọc danh sách app trong máy…", self.app.f_t, DIM).pack(fill="x")
        def got(r):
            a, c = r
            self.apps = list(a.get("apps") or []); self.counts = dict(c.get("counts") or {}); self.max = int(num(c.get("max")) or 4)
            if self.pkg not in self.apps: self.pkg = "com.roblox.client" if "com.roblox.client" in self.apps else (self.apps[0] if self.apps else None)
            self.n = max(1, min(self.max, self.counts.get(self.pkg, 0) + 1)) if self.pkg else 1
            self.draw(); self.draw_apps()
        def fail(m):
            for box in (self.clone_box, self.apps_box):
                for w in box.winfo_children(): w.destroy()
            self.say(self.cl_msg, "✗ " + m, BAD); self.say(self.ap_msg, "✗ " + m, BAD)
            self.loaded.difference_update(("apps", "clone"))
        self.bg(lambda: (self.cp.json("GET", "apps"), self.cp.json("GET", "clone")), got, fail)

    # ================= thẻ ỨNG DỤNG: mở / dừng / xoá dữ liệu / gỡ =================
    def _page_apps(self):
        pg = self.pages["apps"]
        f = self.section("Ứng dụng trong máy", parent=pg)
        self.muted(f, "App bạn đã cài (không gồm app hệ thống). Mở = mở toàn màn hình (game cần màn ngang tự xoay ngang).")
        self.apps_box = self.app.tk.Frame(f, bg=BG); self.apps_box.pack(fill="x", pady=(8, 0))
        self.ap_msg = self.msg(f)

    def draw_apps(self):
        tk = self.app.tk
        for w in self.apps_box.winfo_children(): w.destroy()
        if not self.apps:
            self.label(self.apps_box, "Máy chưa có app nào do bạn cài. Cài ở thẻ Cài app, hoặc từ CH Play trong máy.", self.app.f_t, DIM, wraplength=580).pack(fill="x")
            return
        for pkg in self.apps:
            row = tk.Frame(self.apps_box, bg=CARD, highlightbackground=LINE, highlightthickness=1); row.pack(fill="x", pady=(0, 6))
            br = tk.Frame(row, bg=CARD); br.pack(side="right", padx=8, pady=6)           # nút đặt trước → tên dài không đẩy mất nút
            for text, act, kind in (("Mở", "launch", "primary"), ("Dừng", "stop", "soft"), ("Xoá dữ liệu", "clear", "soft"), ("Gỡ", "uninstall", "danger")):
                self.app.btn(br, text, lambda a=act, p=pkg: self.app_act(a, p), kind, padx=9, pady=4).pack(side="left", padx=(4, 0))
            lf = tk.Frame(row, bg=CARD); lf.pack(side="left", fill="x", expand=True, padx=10, pady=6)
            k = self.counts.get(pkg, 0)
            self.label(lf, app_label(pkg) + (f"  ·  {k} bản clone" if k else ""), ("Segoe UI", 10, "bold"), TXT).pack(fill="x")
            if app_label(pkg) != pkg: self.label(lf, pkg, self.app.f_s, DIM).pack(fill="x")

    def app_act(self, act, pkg):
        import tkinter.messagebox as mb
        nm = app_label(pkg); k = self.counts.get(pkg, 0)
        if act == "clear" and not mb.askyesno("Xoá dữ liệu app", f"Xoá toàn bộ dữ liệu của {nm}?\n\nApp trở về như mới cài: acc đăng nhập, cài đặt trong app sẽ mất.",
                                              icon="warning", default="no", parent=self.win): return
        if act == "uninstall" and not mb.askyesno("Gỡ app", f"Gỡ {nm} khỏi máy?\n\nDữ liệu của app sẽ bị xoá" + (f", {k} bản clone cũng bị gỡ." if k else "."),
                                                  icon="warning", default="no", parent=self.win): return
        verb = {"launch": "mở", "stop": "dừng", "clear": "xoá dữ liệu", "uninstall": "gỡ"}[act]
        self.say(self.ap_msg, f"Đang {verb} {nm}…", WARN)
        def ok(j):
            o = str(j.get("out") or "")
            if "Failure" in o or "Exception" in o: self.say(self.ap_msg, f"✗ Chưa {verb} được {nm}: {o[-140:]}", BAD); return
            self.say(self.ap_msg, f"✓ Đã {verb} {nm}.", OK)
            if act == "uninstall": self.load()
        self.bg(lambda: self.cp.json("POST", act, {"pkg": pkg}, timeout=90), ok, lambda m: self.say(self.ap_msg, "✗ " + m, BAD))

    # ================= thẻ CLONE TAB =================
    def _page_clone(self):
        pg = self.pages["clone"]
        f = self.section("Clone tab — chạy thêm bản 2, 3… của 1 app để đăng nhập acc khác", parent=pg)
        self.muted(f, "Mỗi bản clone là 1 hồ sơ riêng của Android, dùng đúng app gốc đã cài trong máy. Bản clone hiện thành biểu tượng "
                      "\"Clone 1, 2…\" (hoặc tab Công việc) trên màn hình chính, hoặc bấm Mở bản ở đây — mở toàn màn hình, game ngang tự xoay ngang. "
                      "Mỗi bản cần thêm RAM / CPU.")
        self.clone_box = self.app.tk.Frame(f, bg=BG); self.clone_box.pack(fill="x", pady=(8, 0))
        self.cl_msg = self.msg(f)

    def draw(self):
        tk = self.app.tk
        for w in self.clone_box.winfo_children(): w.destroy()
        if not self.apps:
            self.label(self.clone_box, "Máy chưa có app nào. Cài app trước (VD game từ CH Play trong máy, hoặc file APK ở thẻ Cài app) rồi bấm Làm mới.",
                       self.app.f_t, DIM, wraplength=580).pack(fill="x"); return
        self.label(self.clone_box, "App cần clone", ("Segoe UI", 10, "bold"), DIM).pack(fill="x")
        items = [(k, app_label(k) + (f"  ×{self.counts[k]}" if self.counts.get(k) else "")) for k in self.apps]
        self.c_app = Chips(self.app, self.clone_box, items, lambda: self.pkg, self._pick_app, self.draw, wrap=3); self.c_app.frame.pack(fill="x")
        self.label(self.clone_box, f"Số bản clone muốn có (tổng, tối đa {self.max})", ("Segoe UI", 10, "bold"), DIM).pack(fill="x", pady=(8, 0))
        nr = tk.Frame(self.clone_box, bg=BG); nr.pack(fill="x")
        self.c_n = Chips(self.app, nr, [(i, f"{i} bản") for i in range(1, self.max + 1)], lambda: self.n, lambda v: setattr(self, "n", v), self._paint_n)
        self.c_n.frame.pack(side="left")
        self.go = self.app.btn(nr, "", self.clone); self.go.pack(side="left", padx=(10, 0)); self._paint_n()
        k = self.counts.get(self.pkg, 0)
        if k:
            row = tk.Frame(self.clone_box, bg=CARD, highlightbackground=LINE, highlightthickness=1); row.pack(fill="x", pady=(10, 0))
            self.label(row, f"{app_label(self.pkg)} đang có {k} bản clone", ("Segoe UI", 10, "bold"), TXT).pack(fill="x", padx=10, pady=(8, 2))
            br = tk.Frame(row, bg=CARD); br.pack(fill="x", padx=10, pady=(0, 8))
            for i in range(1, k + 1):
                self.app.btn(br, f"▶ Mở bản {i}", lambda i=i: self.open_clone(i), padx=10, pady=4).pack(side="left", padx=(0, 6))
            self.app.btn(br, "Bỏ clone", self.remove, "danger", padx=10, pady=4).pack(side="right")

    def _pick_app(self, v):
        self.pkg = v; self.n = max(1, min(self.max, self.counts.get(v, 0) + 1))

    def _paint_n(self):
        if hasattr(self, "go") and self.go.winfo_exists():
            k = self.counts.get(self.pkg, 0)
            self.go.config(text=f"Tạo {self.n} bản clone" if self.n > k else f"Đã có {k} bản", state="normal" if self.n > k else "disabled",
                           bg=ACC if self.n > k else LINE)

    def clone(self):
        if self.busy or not self.pkg: return
        pkg, n = self.pkg, self.n; self.busy = True; self.go.config(state="disabled")
        self.say(self.cl_msg, f"Đang tạo {n} bản clone {app_label(pkg)} (mỗi bản ~20 giây)…", WARN)
        def job():
            try:
                j = self.cp.json("POST", "clone", {"pkg": pkg, "n": n})
                msg = self.cp.wait_job(j.get("job"), lambda m: self.app.ui(lambda: self.say(self.cl_msg, m, WARN))) if j.get("job") else (j.get("msg") or "Xong.")
                self.app.ui(lambda: (self.say(self.cl_msg, msg, OK), self.load()))
            except Exception as e:
                m = str(e) or "Có lỗi."; self.app.ui(lambda: self.say(self.cl_msg, "✗ " + m, BAD))
            finally:
                self.app.ui(lambda: setattr(self, "busy", False))
        threading.Thread(target=job, daemon=True).start()

    def open_clone(self, i):
        pkg = self.pkg; self.say(self.cl_msg, f"Đang mở bản clone {i}…", WARN)
        self.bg(lambda: self.cp.json("POST", "clone", {"pkg": pkg, "open": i}),
                lambda j: self.say(self.cl_msg, "✓ " + (j.get("msg") or f"Đã mở bản clone {i}."), OK), lambda m: self.say(self.cl_msg, "✗ " + m, BAD))

    def remove(self):
        import tkinter.messagebox as mb
        pkg = self.pkg
        if not mb.askyesno("Bỏ clone", f"Bỏ tất cả bản clone của {app_label(pkg)}?\n\nAcc đăng nhập trong các bản clone sẽ bị xoá.", icon="warning", default="no", parent=self.win): return
        self.say(self.cl_msg, "Đang bỏ các bản clone…", WARN)
        self.bg(lambda: self.cp.json("POST", "clone", {"pkg": pkg, "remove": True}),
                lambda j: (self.say(self.cl_msg, "✓ " + (j.get("msg") or "Đã bỏ các bản clone."), OK), self.load()), lambda m: self.say(self.cl_msg, "✗ " + m, BAD))

    # ================= thẻ KHÁC: mở link, GPS, chụp màn, nút nguồn, root, khởi động lại =================
    def _page_more(self):
        tk = self.app.tk; pg = self.pages["more"]
        f = self.section("Mở link trên máy", parent=pg)
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(6, 0))
        self.url_ent = tk.Entry(r, font=("Segoe UI", 10), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
        self.url_ent.pack(side="left", fill="x", expand=True, ipady=6); self.url_ent.bind("<Return>", lambda e: self.open_url())
        self.app.btn(r, "Mở trên máy", self.open_url, "soft").pack(side="left", padx=(6, 0))
        self.url_msg = self.msg(f, (4, 0))
        f = self.section("Vị trí GPS giả (máy Android 12 trở lên)", parent=pg)
        self.muted(f, "Nhập toạ độ dạng: vĩ độ, kinh độ — trên Google Maps bấm chuột phải vào 1 điểm rồi bấm dòng số để copy. VD Hà Nội: 21.0285, 105.8542")
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(6, 0))
        self.gps_ent = tk.Entry(r, font=("Segoe UI", 10), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat")
        self.gps_ent.insert(0, str(prefs().get("gps_" + str(self.p["id"])) or ""))
        self.gps_ent.pack(side="left", fill="x", expand=True, ipady=6); self.gps_ent.bind("<Return>", lambda e: self.set_gps())
        self.app.btn(r, "Đặt vị trí", self.set_gps).pack(side="left", padx=(6, 0))
        self.app.btn(r, "Tắt", lambda: self.set_gps(off=True), "soft").pack(side="left", padx=(6, 0))
        self.gps_msg = self.msg(f, (4, 0))
        f = self.section("Máy", parent=pg)
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(6, 0))
        self.app.btn(r, "Chụp màn hình", self.shot, "soft").pack(side="left")
        self.app.btn(r, "Nút nguồn (tắt / mở màn)", self.power, "soft").pack(side="left", padx=(8, 0))
        self.app.btn(r, "Root theo app…", self.go_root, "soft").pack(side="left", padx=(8, 0))
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(8, 0))
        self.app.btn(r, "⟳  Khởi động lại máy", self.reboot, "danger").pack(side="left")
        self.more_msg = self.msg(f)

    def open_url(self):
        u = self.url_ent.get().strip()
        if not u: return
        if not re.match(r"^https?://", u, re.I) and re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", u): u = "https://" + u      # gõ "google.com" cũng mở được
        if not re.match(r"^https?://\S+$", u, re.I): self.say(self.url_msg, "Link phải bắt đầu bằng http:// hoặc https://", BAD); return
        self.say(self.url_msg, "Đang mở…", WARN)
        self.bg(lambda: self.cp.json("POST", "url", {"url": u}, timeout=30), lambda j: self.say(self.url_msg, "✓ Đã mở trên máy.", OK),
                lambda m: self.say(self.url_msg, "✗ " + m, BAD))

    def set_gps(self, off=False):
        if off:
            self.say(self.gps_msg, "Đang tắt vị trí giả…", WARN)
            self.bg(lambda: self.cp.json("POST", "gps", {"off": True}, timeout=40), lambda j: self.say(self.gps_msg, "✓ " + (j.get("msg") or "Đã tắt vị trí giả."), OK),
                    lambda m: self.say(self.gps_msg, "✗ " + m, BAD))
            return
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)", self.gps_ent.get())
        if not m: self.say(self.gps_msg, "Nhập dạng: 21.0285, 105.8542", BAD); return
        lat, lng = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180): self.say(self.gps_msg, "Toạ độ không hợp lệ (vĩ độ −90 … 90, kinh độ −180 … 180).", BAD); return
        prefs({"gps_" + str(self.p["id"]): f"{m.group(1)}, {m.group(2)}"})
        self.say(self.gps_msg, "Đang đặt vị trí…", WARN)
        self.bg(lambda: self.cp.json("POST", "gps", {"lat": lat, "lng": lng}, timeout=60), lambda j: self.say(self.gps_msg, "✓ " + (j.get("msg") or "Đã đặt vị trí."), OK),
                lambda e: self.say(self.gps_msg, "✗ " + e, BAD))

    def shot(self):
        self.say(self.more_msg, "Đang chụp màn hình…", WARN)
        def job():
            code, raw = self.cp.request("GET", "shot?fresh=1", timeout=40)
            if code != 200 or raw[:8] != b"\x89PNG\r\n\x1a\n":
                raise ApiError(code, err_text(code, raw) if code != 200 else "Không chụp được màn hình.")
            fp = shot_path()
            with open(fp, "wb") as f: f.write(raw)
            return fp
        def ok(fp):
            self.say(self.more_msg, f"✓ Đã lưu ảnh: {fp}", OK); open_folder(fp)
        self.bg(job, ok, lambda m: self.say(self.more_msg, "✗ " + m, BAD))

    def power(self):
        self.say(self.more_msg, "Đang bấm nút nguồn…", WARN)
        self.bg(lambda: self.cp.json("POST", "key", {"code": 26}, timeout=20),
                lambda j: self.say(self.more_msg, "✓ Đã bấm nút nguồn — màn đang tắt thì bật lên, đang bật thì tắt.", OK), lambda m: self.say(self.more_msg, "✗ " + m, BAD))

    def go_root(self):
        self.tab = "root"; self.c_tab.paint(); self._show_tab()

    # ================= thẻ KHO APP: Termux, MT Manager, ZArchiver… — máy chủ tải từ trang CHÍNH CHỦ rồi cài 1 chạm (cpapi <máy>/store) =================
    def _page_store(self):
        tk = self.app.tk; pg = self.pages["store"]
        f = self.section("Kho app", parent=pg)
        self.muted(f, "Máy chủ tải từ trang chính chủ (Termux: GitHub · MT Manager: mt.cc · ZArchiver: zdevs.ru) rồi cài vào máy. "
                      "Lần đầu mất vài chục giây, máy sau cài ngay.")
        self.st_box = tk.Frame(f, bg=BG); self.st_box.pack(fill="x", pady=(8, 0))
        self.st_msg = self.msg(f)
        self.muted(f, "Cần root cho Termux / MT Manager → thẻ Root, bật cho app đó.")

    def load_store(self):
        self.loaded.add("store")
        for w in self.st_box.winfo_children(): w.destroy()
        self.label(self.st_box, "Đang tải…", self.app.f_s, DIM).pack(fill="x")
        def fail(m):
            for w in self.st_box.winfo_children(): w.destroy()
            self.say(self.st_msg, "✗ Không mở được kho: " + missing(m), BAD)
        self.bg(lambda: self.cp.json("GET", "store", timeout=60), self.draw_store, fail)

    def draw_store(self, j):
        tk = self.app.tk
        for w in self.st_box.winfo_children(): w.destroy()
        rows = [(a.get("icon") or "📦", a.get("name") or "?", a.get("desc") or "", bool(a.get("installed")), {"id": a["id"]})
                for a in (j.get("apps") or []) if a.get("id")]
        rows += [("📦", re.sub(r"(?i)\.(apk|apks|xapk|apkm)$", "", f["name"]), f"App shop thêm sẵn · {(f.get('size') or 0) / 1048576:.1f} MB", False, {"name": f["name"]})
                 for f in (j.get("files") or []) if f.get("name")]
        if not rows:
            self.label(self.st_box, "Máy chủ chưa cập nhật bản có Kho app — báo admin cập nhật.", self.app.f_t, DIM, wraplength=580).pack(fill="x"); return
        for icon, name, desc, inst, body in rows:
            fr = tk.Frame(self.st_box, bg=CARD, highlightbackground=LINE, highlightthickness=1); fr.pack(fill="x", pady=(0, 6))
            tk.Label(fr, text=icon, font=("Segoe UI Emoji", 16), bg=CARD, fg=TXT, width=2).pack(side="left", padx=(10, 6), pady=8)
            b = self.app.btn(fr, "Cài lại" if inst else "Cài", lambda body=body, name=name: self.store_install(body, name), "soft" if inst else "primary")
            b.pack(side="right", padx=10)
            tx = tk.Frame(fr, bg=CARD); tx.pack(side="left", fill="x", expand=True, pady=6)
            self.label(tx, name, ("Segoe UI", 10, "bold"), TXT).pack(fill="x")
            self.label(tx, desc + ("   ✓ Đã cài" if inst else ""), self.app.f_s, OK if inst else DIM, wraplength=420).pack(fill="x")

    def store_install(self, body, name):
        lbl = self.st_msg
        if lbl in self.jobs_on: self.say(lbl, "Đang cài app khác — đợi xong rồi bấm tiếp.", WARN); return
        self.jobs_on.add(lbl); self.say(lbl, f"Đang chuẩn bị {name}…", WARN)
        def job():
            try:
                j = self.cp.json("POST", "store", body, timeout=60)
                msg = self.cp.wait_job(j["job"], lambda m: self.app.ui(lambda: self.say(lbl, m, WARN))) if j.get("job") else (j.get("msg") or "Xong.")
                self.app.ui(lambda: (self.say(lbl, ("" if msg[:1] == "✅" else "✓ ") + msg, OK), self.load_store()))
            except Exception as e:
                m = str(e) or "Có lỗi."; log("store:", m); self.app.ui(lambda: self.say(lbl, "✗ " + missing(m), BAD))
            finally:
                self.app.ui(lambda: self.jobs_on.discard(lbl))
        threading.Thread(target=job, daemon=True).start()

    # ================= thẻ ROOT: công tắc root của máy + chọn app được dùng lệnh su (cpapi <máy>/rootcfg) =================
    def _page_root(self):
        tk = self.app.tk; pg = self.pages["root"]
        f = self.section("Root theo app", parent=pg)
        self.muted(f, "Chỉ app được bật bên dưới mới dùng được lệnh su (vd Termux). App khác xin root sẽ bị từ chối và hiện ở mục \"Vừa xin root\".")
        sw = tk.Frame(f, bg=CARD, highlightbackground=LINE, highlightthickness=1); sw.pack(fill="x", pady=(8, 0))
        self.rt_on = tk.BooleanVar(value=False)
        self.rt_cb = tk.Checkbutton(sw, text="  Bật root cho máy này", variable=self.rt_on, command=self.paint_root, font=("Segoe UI", 11, "bold"),
                                    fg=TXT, bg=CARD, selectcolor=BG, activebackground=CARD, activeforeground=TXT, anchor="w", cursor="hand2", state="disabled")
        self.rt_cb.pack(fill="x", padx=10, pady=(8, 0))
        self.rt_st = self.label(sw, "Đang đọc…", self.app.f_s, DIM, wraplength=560); self.rt_st.pack(fill="x", padx=36, pady=(0, 8))
        self.rt_warn = self.label(f, "", self.app.f_s, WARN, wraplength=580)
        self.rt_box = tk.Frame(f, bg=BG); self.rt_box.pack(fill="x", pady=(8, 0))
        self.muted(f, "Một số game và app (vd Roblox) có thể phát hiện máy đã root. Chỉ bật cho app thật sự cần.")
        r = tk.Frame(f, bg=BG); r.pack(fill="x", pady=(8, 0))
        self.rt_save = self.app.btn(r, "Lưu", self.save_root); self.rt_save.pack(side="left")
        self.app.btn(r, "Đọc lại", self.load_root, "soft").pack(side="left", padx=(8, 0))
        self.rt_msg = self.msg(f)
        self.rt_cfg = None; self.rt_vars = []

    def load_root(self):
        self.loaded.add("root")
        self.say(self.rt_st, "Đang đọc…", DIM)
        def fail(m):
            if "chưa cập nhật" in m: self.say(self.rt_st, "Máy chủ chưa có tính năng này — báo admin cập nhật.", BAD)
            else: self.say(self.rt_st, "✗ Không đọc được: " + m, BAD)
        self.bg(lambda: self.cp.json("GET", "rootcfg", timeout=90), self.draw_root, fail)

    def draw_root(self, j):
        tk = self.app.tk; self.rt_cfg = j
        allow = list(j.get("apps") or []); aset = set(allow)
        self.rt_on.set(bool(j.get("on"))); self.rt_cb.config(state="normal")
        for w in self.rt_box.winfo_children(): w.destroy()
        self.rt_vars = []
        asked = [a for a in (j.get("asked") or []) if a.get("pkg") not in aset]
        shown = {a.get("pkg") for a in asked}
        apps = [x for x in dict.fromkeys(allow + list(j.get("installed") or [])) if x not in shown]
        apps.sort(key=lambda x: (x not in aset, app_label(x).lower()))
        def row(pkg, on, extra="", ask=False):
            fr = tk.Frame(self.rt_box, bg=CARD, highlightbackground=WARN if ask else LINE, highlightthickness=1); fr.pack(fill="x", pady=(0, 6))
            v = tk.BooleanVar(value=on); self.rt_vars.append((pkg, v))
            tk.Checkbutton(fr, text="  " + app_label(pkg), variable=v, font=("Segoe UI", 10, "bold"), fg=TXT, bg=CARD, selectcolor=BG,
                           activebackground=CARD, activeforeground=TXT, anchor="w", cursor="hand2").pack(fill="x", padx=8, pady=(5, 0))
            if app_label(pkg) != pkg or extra: self.label(fr, pkg + extra, self.app.f_s, DIM).pack(fill="x", padx=34, pady=(0, 5))
            else: tk.Frame(fr, bg=CARD, height=5).pack(fill="x")
        if asked:
            self.label(self.rt_box, "Vừa xin root (chưa được bật)", self.app.f_s, WARN).pack(fill="x", pady=(0, 4))
            for a in asked: row(a["pkg"], False, ("  ·  xin lúc " + str(a.get("t", ""))[11:16]) if len(str(a.get("t", ""))) >= 16 else "", True)
        self.label(self.rt_box, "Ứng dụng trong máy", self.app.f_s, DIM).pack(fill="x", pady=(4, 4))
        if not apps and not asked:
            self.label(self.rt_box, "Chưa có app nào do bạn cài. Cài app (vd Termux) rồi bấm Đọc lại.", self.app.f_t, DIM, wraplength=580).pack(fill="x")
        for x in apps: row(x, x in aset)
        if j.get("selinux") == "Enforcing":
            self.rt_warn.config(text="⚠ Máy đang bật SELinux Enforcing — root theo app có thể chưa dùng được. Báo hỗ trợ nếu app vẫn báo không có su.")
            self.rt_warn.pack(fill="x", pady=(6, 0), before=self.rt_box)
        else: self.rt_warn.pack_forget()
        self.paint_root()

    def paint_root(self):
        j = self.rt_cfg or {}; on = self.rt_on.get()
        if not j.get("online"): t = "Máy đang tắt hoặc mất kết nối — vẫn lưu được, máy bật lên tự áp dụng."
        elif on and j.get("su") is False: t = "Máy chưa bật root gốc — bấm Lưu: máy tự khởi động lại khoảng 1 phút để bật root, rồi cài cho app đã chọn."
        elif on != bool(j.get("on")): t = "Bấm Lưu để bật root." if on else "Bấm Lưu để tắt root."
        elif on: t = (f"Đang bật · {len(j.get('apps') or [])} app được dùng su" if j.get("running") else "Đã bật nhưng chưa chạy — bấm Lưu để chạy lại.")
        else: t = "Đang tắt — không app nào dùng được lệnh su."
        self.say(self.rt_st, t, DIM)

    def save_root(self):
        import tkinter.messagebox as mb
        if self.rt_cfg is None or self.rt_msg in self.jobs_on: return
        on = bool(self.rt_on.get()); apps = [p for p, v in self.rt_vars if v.get()]
        if on and not apps and not mb.askyesno("Root", "Chưa chọn app nào — bật root nhưng mọi app xin root sẽ bị từ chối. Vẫn lưu?", parent=self.win): return
        lbl = self.rt_msg; self.jobs_on.add(lbl); self.say(lbl, "Đang lưu cấu hình root…", WARN)
        def job():
            try:
                if on and (self.rt_cfg or {}).get("su") is False:
                    self.app.ui(lambda: self.say(lbl, "Đang bật root — máy khởi động lại khoảng 1 phút…", WARN))
                j = self.cp.json("POST", "rootcfg", {"on": on, "apps": list(dict.fromkeys(apps))}, timeout=60)
                msg = self.cp.wait_job(j["job"], lambda m: self.app.ui(lambda: self.say(lbl, m, WARN))) if j.get("job") else (j.get("msg") or "Đã lưu.")
                self.app.ui(lambda: (self.say(lbl, "✓ " + msg, OK), self.load_root()))
            except Exception as e:
                m = str(e) or "Có lỗi."; log("root:", m); self.app.ui(lambda: self.say(lbl, "✗ " + missing(m), BAD))
            finally:
                self.app.ui(lambda: self.jobs_on.discard(lbl))
        threading.Thread(target=job, daemon=True).start()

    def reboot(self):
        import tkinter.messagebox as mb
        if not mb.askyesno("Khởi động lại", f"Khởi động lại máy “{self.p.get('name')}”?\n\nMáy tắt khoảng 1 phút rồi tự bật lại. Dữ liệu vẫn giữ.", parent=self.win): return
        self._bgjob(self.more_msg, lambda: self.cp.json("POST", "reboot", {}, timeout=60), "Đang khởi động lại máy (1–3 phút)…")


ERRORS.update({                                                  # 🏷️ mã giảm giá / mã tặng máy (SQL v23) · 💎 Tích Blue (SQL v27)
    "PROMO_INVALID": "Mã không đúng hoặc đã bị tắt.", "PROMO_EXPIRED": "Mã đã hết hạn.", "PROMO_NOT_STARTED": "Mã chưa đến ngày sử dụng.",
    "PROMO_USED_UP": "Mã đã hết lượt sử dụng.", "PROMO_USER_LIMIT": "Bạn đã dùng hết số lượt của mã này.", "PROMO_SCOPE": "Mã này không áp dụng cho loại đơn này.",
    "PROMO_MIN_ORDER": "Đơn chưa đạt giá trị tối thiểu để dùng mã này.", "PROMO_TOO_MANY": "Bạn nhập sai mã quá nhiều lần — thử lại sau 10 phút.",
    "PROMO_IS_GIFT": "Đây là mã TẶNG MÁY — nhập ở nút 🎟 Nhập mã trên danh sách máy (không dùng khi thanh toán).",
    "PROMO_IS_DISCOUNT": "Đây là mã giảm giá — nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn / nâng cấp máy.", "PROMO_NOT_FOR_FREE": "Máy miễn phí không dùng mã giảm giá được.",
    "PROMO_EMPTY": "Hãy nhập mã.", "PROMO_CTX": "Chọn cấu hình / số ngày trước rồi bấm Áp dụng.", "PROMO_OFF": "Tính năng mã giảm giá chưa bật.",
    "BAD_CODE": "Mã không đúng, đã bị huỷ hoặc đã hết hạn.", "CODE_USED": "Mã này đã có người dùng rồi.", "OWN_PHONE": "Đây là máy của chính bạn.",
    "ALREADY_SHARED": "Bạn đã được chia sẻ máy này rồi.",
    "BLUE_DONE": "Hôm nay bạn đã điểm danh rồi — quay lại ngày mai nhé.", "BLUE_IP_LIMIT": "Mạng (wifi / 4G) này đã đủ số tài khoản nhận Blue hôm nay — mai thử lại nhé.",
    "BLUE_NEED_TOPUP": "Nạp tiền ít nhất 1 lần để mở khoá trả bằng Blue (Blue vẫn được tích bình thường).", "BLUE_EMPTY": "Bạn chưa có Blue để trả.",
    "BLUE_NOT_FOR_FREE": "Máy miễn phí không trả bằng Blue được.", "BLUE_OFF": "Tích Blue đang tạm tắt.",
    "TASK_DONE": "Hôm nay bạn đã nhận nhiệm vụ này rồi.", "TASK_NOT_YET": "Chưa xong nhiệm vụ — làm xong rồi bấm nhận nhé.",
    "TASK_OFF": "Nhiệm vụ này đang tạm tắt.", "BAD_TASK": "Nhiệm vụ không hợp lệ.",
})
ERRORS.update({"UPGRADE_PENDING": "Máy đang được nâng cấp, đợi khoảng 1 phút rồi thử lại.", "FREE_NO_UPGRADE": "Máy miễn phí không nâng cấp được — thuê máy trả phí để nâng.",
               "PHONE_NOT_ACTIVE": "Máy phải đang chạy mới làm được việc này.", "BAD_UPGRADE": "Cấu hình nâng cấp không hợp lệ."})


# ================================================================ TỰ CẬP NHẬT app PC (bấm 1 nút như app điện thoại)
# Bản cũ: tải CloudBluePC.zip (kiểm cỡ + SHA-256 trong download/pc.json) → giải nén vào thư mục "<tên>.update" CẠNH thư mục app
# → chạy CloudBluePC.exe MỚI trong đó với --finish-update rồi tự thoát. Bản mới: chờ app cũ tắt (đóng nốt cửa sổ máy) → đổi tên
# thư mục app cũ thành "<tên>.old-<giờ>" → chép bản mới vào đúng chỗ cũ (lỗi thì trả bản cũ) → mở lại app. Lần mở sau dọn thư mục thừa.
# AN TOÀN: chỉ đổi tên / xoá thư mục CHỈ chứa app (CloudBluePC.exe + _internal) — app nằm chung thư mục với file của khách → tải tay.
IS_WIN = os.name == "nt"
EXE_NAME = os.path.basename(sys.executable) if FROZEN else "CloudBluePC.exe"
EXTRA_OK = {"desktop.ini", "thumbs.db"}                # file Windows tự tạo trong thư mục — vẫn coi là thư mục chỉ có app


def app_folder_ok(d):
    """Thư mục CHỈ chứa app (CloudBluePC.exe + _internal) → mới được đổi tên / thay / xoá cả thư mục."""
    try: names = {n.lower() for n in os.listdir(d)}
    except OSError: return False
    return EXE_NAME.lower() in names and names <= {EXE_NAME.lower(), "_internal"} | EXTRA_OK


def find_app_dir(d):
    """Thư mục app trong d: chính d, hoặc thư mục con DUY NHẤT của d (file zip có thư mục gốc CloudBluePC/)."""
    if app_folder_ok(d): return d
    try: subs = os.listdir(d)
    except OSError: return None
    one = os.path.join(d, subs[0]) if len(subs) == 1 else ""
    return one if one and os.path.isdir(one) and app_folder_ok(one) else None


def _no_files(p):
    for _r, _d, files in os.walk(p):
        if files: return False
    return True


def remove_app_tree(p):
    """Xoá thư mục bản app cũ / gói cập nhật (CHỈ khi đúng là bản app, hoặc rỗng): _internal trước, CloudBluePC.exe SAU CÙNG
       → xoá dở (file đang bị giữ, VD trình cập nhật chưa thoát hẳn) thì lần sau vẫn nhận ra là của app để xoá tiếp. False = không phải của app."""
    import shutil
    if not os.path.isdir(p): return False
    a = find_app_dir(p)
    if a is None:
        if not _no_files(p): return False                                      # có file không phải của app → không đụng
        shutil.rmtree(p); return True
    if os.path.isdir(os.path.join(a, "_internal")): shutil.rmtree(os.path.join(a, "_internal"))
    for n in sorted(os.listdir(a), key=lambda n: n.lower() == EXE_NAME.lower()):   # exe sau cùng
        os.remove(os.path.join(a, n))
    os.rmdir(a)
    if a != p: os.rmdir(p)
    return True


def can_self_update(here=None):
    here = os.path.abspath(here or HERE)
    return bool(FROZEN and IS_WIN and os.path.dirname(here) != here and app_folder_ok(here))


def parent_writable(here=None):
    """Ghi được vào thư mục chứa thư mục app không (VD app đặt trong Program Files thì không) — thử tạo rồi xoá 1 thư mục tạm."""
    import tempfile
    try: os.rmdir(tempfile.mkdtemp(prefix=".cb-", dir=os.path.dirname(os.path.abspath(here or HERE)))); return True
    except OSError: return False


def _k32():
    import ctypes
    from ctypes import wintypes as wt
    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]; k.CreateToolhelp32Snapshot.restype = wt.HANDLE
    k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; k.OpenProcess.restype = wt.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]; k.QueryFullProcessImageNameW.restype = wt.BOOL
    k.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]; k.TerminateProcess.restype = wt.BOOL
    k.CloseHandle.argtypes = [wt.HANDLE]; k.CloseHandle.restype = wt.BOOL
    return ctypes, wt, k


def procs_at(exe):
    """PID mọi tiến trình đang chạy ĐÚNG file exe này (trừ chính mình) — Windows."""
    if not IS_WIN: return []
    ctypes, wt, k = _k32()
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PE)]
    k.Process32FirstW.restype = k.Process32NextW.restype = wt.BOOL
    target = os.path.normcase(os.path.abspath(exe)); name = os.path.basename(target); out = []
    snap = k.CreateToolhelp32Snapshot(0x2, 0)                                   # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value: return out
    try:
        e = PE(); e.dwSize = ctypes.sizeof(PE); ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == name and e.th32ProcessID != os.getpid():
                h = k.OpenProcess(0x1000, False, e.th32ProcessID)                # PROCESS_QUERY_LIMITED_INFORMATION
                if h:
                    try:
                        buf = ctypes.create_unicode_buffer(1024); n = wt.DWORD(1024)
                        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and os.path.normcase(buf.value) == target: out.append(int(e.th32ProcessID))
                    finally: k.CloseHandle(h)
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally: k.CloseHandle(snap)
    return out


def kill_pid(pid):
    if not IS_WIN: return False
    ctypes, wt, k = _k32()
    h = k.OpenProcess(0x0001, False, int(pid))                                   # PROCESS_TERMINATE
    if not h: return False
    try: return bool(k.TerminateProcess(h, 1))
    finally: k.CloseHandle(h)


def launch_app(exe, *args):
    """Mở 1 exe tách hẳn khỏi tiến trình này; thư mục làm việc = thư mục của exe (không giữ thư mục app cũ)."""
    kw = {"creationflags": 0x00000008 | 0x00000200} if IS_WIN else {"start_new_session": True}   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([exe, *args], cwd=os.path.dirname(exe), close_fds=True, **kw)


def download_file(url, dest, on_prog=None, cancelled=lambda: False):
    """Tải về file (theo chuyển hướng) → (số byte, SHA-256)."""
    req = urllib.request.Request(url, headers={"User-Agent": f"BlueRobloxPC/{APP_VER}", "Accept": "*/*"})
    h = hashlib.sha256(); done = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            while True:
                if cancelled(): raise ApiError(0, "Đã huỷ cập nhật.")
                b = r.read(262144)
                if not b: break
                f.write(b); h.update(b); done += len(b)
                if on_prog: on_prog(done, total)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, f"Tải bản mới lỗi (HTTP {e.code}) — thử lại sau ít phút.") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise ApiError(0, "Mất mạng khi tải bản mới — kiểm tra mạng rồi thử lại.") from e
    except OSError as e:
        raise ApiError(0, f"Không ghi được file tải về (ổ đĩa đầy?): {e}") from e
    return done, h.hexdigest()


def prepare_update(info, here=None, on_prog=None, cancelled=lambda: False, url=None):
    """Bản cũ: tải + kiểm + giải nén bản mới vào '<thư mục app>.update' → trả thư mục app mới (chứa CloudBluePC.exe)."""
    import shutil, tempfile
    here = os.path.abspath(here or HERE); parent, base = os.path.split(here)
    stage = os.path.join(parent, base + ".update")
    _clear_stage(stage)                                                        # lần cập nhật trước dở dang
    fd, zp = tempfile.mkstemp(prefix="CloudBluePC-", suffix=".zip"); os.close(fd)
    try:
        n, sha = download_file(url or (WEB.rstrip("/") + "/download/CloudBluePC.zip"), zp, on_prog, cancelled)
        if num(info.get("size")) and n != int(num(info.get("size"))):
            raise ApiError(0, "File tải về chưa đủ — có thể web vừa lên bản mới hơn, thử lại.")
        if info.get("sha256") and sha != str(info["sha256"]).lower():
            raise ApiError(0, "File tải về không khớp mã kiểm tra — có thể web vừa lên bản mới hơn, thử lại.")
        if cancelled(): raise ApiError(0, "Đã huỷ cập nhật.")
        return extract_update(zp, here)
    finally:
        try: os.remove(zp)
        except OSError: pass


def _clear_stage(stage):
    if not os.path.exists(stage): return
    try: ok = remove_app_tree(stage)
    except OSError as e: raise ApiError(0, f"Thư mục cập nhật lần trước còn bị giữ ({stage}) — thử lại sau ít phút.") from e
    if not ok: raise ApiError(0, f"Có thư mục lạ trùng tên {stage} — đổi tên / xoá nó rồi thử lại.")


def extract_update(zp, here=None):
    """Giải nén gói cập nhật vào '<thư mục app>.update' → trả thư mục app mới. (GitHub Actions chạy hàm này với file zip thật trên Windows.)"""
    import shutil, zipfile
    here = os.path.abspath(here or HERE); parent, base = os.path.split(here)
    stage = os.path.join(parent, base + ".update")
    _clear_stage(stage)
    try:
        os.makedirs(stage)
        with zipfile.ZipFile(zp) as z:
            if z.testzip() is not None: raise ApiError(0, "File cập nhật bị hỏng — thử lại.")
            z.extractall(stage)
    except (OSError, zipfile.BadZipFile) as e:
        shutil.rmtree(stage, ignore_errors=True)
        raise ApiError(0, f"Không giải nén được bản mới (ổ đĩa đầy / không có quyền ghi?): {e}") from e
    except ApiError:
        shutil.rmtree(stage, ignore_errors=True); raise
    src = find_app_dir(stage)
    if not src:
        shutil.rmtree(stage, ignore_errors=True); raise ApiError(0, "Gói cập nhật thiếu CloudBluePC.exe — báo hỗ trợ.")
    return src


def finish_update(src, install, wait_pid=0, say=lambda m: None, procs=None, kill=None, sleep=time.sleep):
    """Bản MỚI (chạy từ thư mục .update): thay thư mục app cũ bằng bản mới. Trả (exe để mở lại, lỗi hoặc None, số cửa sổ phải đóng)."""
    import shutil
    procs = procs or procs_at; kill = kill or kill_pid
    src, install = os.path.abspath(src), os.path.abspath(install)
    exe = os.path.join(install, EXE_NAME)
    if not app_folder_ok(src): return None, "Bản mới tải về không đầy đủ — mở lại app rồi cập nhật lại.", 0
    if not app_folder_ok(install):                                             # không bao giờ đụng thư mục có file khác của khách
        return (exe if os.path.isfile(exe) else None), "Thư mục app có thêm file khác — không tự thay được. Tải bản mới trên web rồi giải nén đè.", 0
    say("Chờ app cũ đóng…")
    for _ in range(30):                                                        # app cũ tự thoát ngay sau khi mở trình cập nhật
        if not wait_pid or wait_pid not in procs(exe): break
        sleep(0.5)
    left = procs(exe); closed = len(left)
    if left:
        say("Đang đóng các cửa sổ máy đang mở…")
        for p in left: kill(p)
        for _ in range(20):
            if not procs(exe): break
            sleep(0.5)
    say("Đang thay bản mới…")
    old = f"{install}.old-{int(time.time())}"; err = None
    for _ in range(30):                                                        # phần mềm diệt virus đang quét file → thử lại vài giây
        try: os.rename(install, old); err = None; break
        except OSError as e: err = e; sleep(1)
    if err is not None:
        log("update: không đổi tên được thư mục app:", repr(err))
        return exe, ("Không thay được thư mục app vì có chương trình khác đang mở file trong đó (cửa sổ cmd, phần mềm diệt virus…). "
                     "Đã mở lại bản cũ — đóng chương trình đó rồi bấm cập nhật lại."), closed
    try:
        say("Đang chép bản mới…")
        shutil.copytree(src, install)
    except Exception as e:
        log("update: chép bản mới lỗi:", repr(e))
        shutil.rmtree(install, ignore_errors=True)
        try: os.rename(old, install)
        except OSError: return None, f"Cập nhật lỗi và chưa trả lại được bản cũ — app cũ đang nằm ở: {old}", closed
        return exe, f"Chép bản mới bị lỗi ({e}) — đã giữ nguyên bản cũ.", closed
    return exe, None, closed


def cleanup_update_leftovers(here=None, tries=10, gap=3.0):
    """Bản mới mở lên: xoá thư mục '<tên>.update' và '<tên>.old-<số>' cạnh thư mục app — CHỈ khi bên trong đúng là bản app."""
    import shutil
    here = os.path.abspath(here or HERE); parent, base = os.path.split(here)
    if parent == here: return
    old_re = re.compile(re.escape(base) + r"\.old-\d+", re.I)
    try: names = os.listdir(parent)
    except OSError: return
    for n in names:
        if n.lower() != (base + ".update").lower() and not old_re.fullmatch(n): continue
        p = os.path.join(parent, n)
        if not os.path.isdir(p) or not (find_app_dir(p) or _no_files(p)): continue
        for i in range(tries):                                                 # trình cập nhật có thể còn đang thoát
            try: remove_app_tree(p); break
            except OSError:
                if i + 1 < tries: time.sleep(gap)


def run_finish_update(install, wait_pid, test_out=None):
    """--finish-update: cửa sổ nhỏ "Đang cập nhật…" trong lúc thay bản → mở lại app (lỗi thì mở lại bản cũ).
       test_out (GitHub Actions): không cửa sổ, không mở lại app — ghi kết quả ra file."""
    if test_out:
        try:
            exe, err, closed = finish_update(HERE, install, wait_pid)
            res = ["FAIL", err] if err else ["OK", f"closed={closed}", f"exe={exe}"]
        except Exception:
            res = ["FAIL", traceback.format_exc()]
        with open(test_out, "w", encoding="utf-8") as f: f.write("\n".join(res) + "\n")
        return
    import tkinter as tk
    root = tk.Tk(); root.title("CloudBlue — đang cập nhật"); root.configure(bg=BG); root.resizable(False, False)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight(); root.geometry(f"470x150+{(sw - 470) // 2}+{(sh - 150) // 3}")
    tk.Label(root, text="Đang cập nhật CloudBlue PC…", font=("Segoe UI", 12, "bold"), fg=TXT, bg=BG, anchor="w").pack(fill="x", padx=20, pady=(22, 4))
    sub = tk.Label(root, text="Chờ app cũ đóng…", font=("Segoe UI", 10), fg=DIM, bg=BG, anchor="w", justify="left", wraplength=430)
    sub.pack(fill="x", padx=20)
    q = queue.Queue()
    def work():
        try: q.put(("done",) + finish_update(HERE, install, wait_pid, lambda m: q.put(("msg", m))))
        except Exception as e:
            log("update:", traceback.format_exc()); q.put(("done", os.path.join(install, EXE_NAME), f"Cập nhật lỗi: {e}", 0))
    def pump():
        try:
            while True:
                it = q.get_nowait()
                if it[0] == "msg": sub.config(text=it[1]); continue
                _, exe, err, _closed = it
                if err is None:
                    sub.config(text="Xong — đang mở lại app…", fg=OK)
                    try: launch_app(exe, "--updated")
                    except Exception as e: log("update: mở app mới lỗi:", e)
                    root.after(700, root.destroy); return
                sub.config(text=err, fg=BAD); log("update:", err)
                if exe and os.path.isfile(exe):
                    try: launch_app(exe)
                    except Exception as e: log("update: mở lại bản cũ lỗi:", e)
                tk.Button(root, text="Đóng", command=root.destroy, bg=LINE, fg=TXT, relief="flat", bd=0, font=("Segoe UI", 10, "bold"),
                          padx=14, pady=5, cursor="hand2").pack(anchor="e", padx=20, pady=(8, 0))
                root.geometry("470x200"); return
        except queue.Empty: pass
        root.after(100, pump)
    threading.Thread(target=work, daemon=True).start()
    root.after(100, pump); root.mainloop()


class UpdateDlg(Dlg):
    """Bấm dải "Có bản app mới": tải + thay bản mới + tự mở lại (giống app điện thoại). App nằm chung thư mục với file khác → hướng dẫn tải tay."""
    def __init__(self, app, info):
        super().__init__(app, "Cập nhật CloudBlue PC", 540, 360)
        tk = app.tk; self.info = info; self.stop = False; self.running = False; self.auto = can_self_update() and parent_writable()
        mb_ = num(info.get("size")) / 1048576
        f = self.section(f"Bản mới {info.get('version') or ''}" + (f"  ·  {mb_:.0f} MB" if mb_ else "") + f"  (đang dùng {APP_VER})")
        if self.auto:
            txt = ("Bấm Cập nhật ngay: app tự tải bản mới, đóng các cửa sổ máy đang mở, thay bản mới rồi tự mở lại (khoảng 1 phút). "
                   "Tài khoản, máy và cài đặt giữ nguyên.")
        else:
            txt = ("App đang nằm chung thư mục với file khác (hoặc trong thư mục không được ghi) nên không tự thay được. "
                   "Bấm Tải về → đóng app → giải nén file vừa tải đè lên thư mục app cũ → mở lại CloudBluePC.exe.")
        self.label(f, txt, self.app.f_t, TXT, wraplength=490).pack(fill="x")
        self.msg = self.label(f, "", ("Segoe UI", 10, "bold"), TXT, wraplength=490); self.msg.pack(fill="x", pady=(14, 0))
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=10)
        self.later = self.app.btn(bb, "Để sau", self.close, "soft"); self.later.pack(side="left")
        self.go = self.app.btn(bb, "Cập nhật ngay" if self.auto else "Tải về", self.start if self.auto else self.manual); self.go.pack(side="right")
        self.hand = self.app.btn(bb, "Tải bằng tay", self.manual, "soft")       # hiện khi tự cập nhật bị lỗi

    def say_(self, text, col=TXT):
        if self.alive and self.msg.winfo_exists(): self.msg.config(text=text, fg=col)

    def close(self):
        self.stop = True; super().close()

    def manual(self):
        webbrowser.open(WEB.rstrip("/") + "/download/CloudBluePC.zip")
        self.say_("Đang tải trong trình duyệt — tải xong: đóng app, giải nén đè lên thư mục app cũ, mở lại CloudBluePC.exe.", OK)

    def cancel(self):
        self.stop = True; self.say_("Đang huỷ…", WARN)

    def start(self):
        if self.running: return
        self.running = True; self.stop = False
        self.go.config(state="disabled"); self.later.config(text="Huỷ", command=self.cancel)
        self.say_("Đang tải bản mới…", WARN); last = [-1]
        def prog(done, total):
            pct = done * 100 // total if total else -1
            if pct == last[0]: return
            last[0] = pct
            t = f"Đang tải bản mới… {pct}%  ({done / 1048576:.0f} / {total / 1048576:.0f} MB)" if total else f"Đang tải bản mới… {done / 1048576:.0f} MB"
            self.app.ui(lambda: self.say_(t, WARN))
        def job():
            src = prepare_update(self.info, HERE, prog, lambda: self.stop)
            if self.stop: raise ApiError(0, "Đã huỷ cập nhật.")
            self.app.ui(lambda: self.say_("Đang mở trình cập nhật — app tự đóng rồi mở lại…", WARN))
            try: launch_app(os.path.join(src, EXE_NAME), "--finish-update", HERE, str(os.getpid()))
            except OSError as e:
                log("update: không mở được trình cập nhật:", repr(e))
                raise ApiError(0, "Không mở được bản mới vừa tải (phần mềm diệt virus chặn?) — bấm Tải bằng tay.") from e
            return src
        def ok(_src):
            self.app.root.after(500, self.app.root.destroy)                # thoát để trình cập nhật thay được thư mục app
        def fail(m):
            self.running = False
            if self.go.winfo_exists(): self.go.config(state="normal")
            if self.later.winfo_exists(): self.later.config(text="Để sau", command=self.close)
            if self.go.winfo_exists(): self.go.config(text="Thử lại")
            if self.hand.winfo_exists() and not self.hand.winfo_ismapped() and "huỷ" not in m: self.hand.pack(side="right", padx=(0, 8))
            self.say_("✗ " + m, BAD)
        self.bg(job, ok, fail)


class Launcher:
    def __init__(self, open_id=None, tools_for=None, updated=False):
        import tkinter as tk
        self.tk = tk; self.auth = Auth(); self.shop = Shop(self.auth); self.open_id = open_id; self.rows = []; self.busy = False
        self.just_updated = updated
        if FROZEN and not tools_for: threading.Thread(target=cleanup_update_leftovers, daemon=True).start()   # dọn thư mục của lần cập nhật trước
        self.scrollers = {}; self._fast = None; self._q = queue.Queue()
        self.root = tk.Tk(); self.root.title("CloudBlue PC"); self.root.configure(bg=BG); self.root.geometry("600x760"); self.root.minsize(480, 540)
        self.root.bind_all("<MouseWheel>", self._wheel)
        self.root.after(40, self._pump)
        try:
            ico = os.path.join(getattr(sys, "_MEIPASS", HERE), "icon.png")
            if os.path.isfile(ico): self.root.iconphoto(True, tk.PhotoImage(file=ico))
        except Exception: pass
        self.f_h1 = ("Segoe UI", 18, "bold"); self.f_h2 = ("Segoe UI", 12, "bold"); self.f_t = ("Segoe UI", 10); self.f_s = ("Segoe UI", 9)
        self.body = tk.Frame(self.root, bg=BG); self.body.pack(fill="both", expand=True)
        self.tools_only = bool(tools_for)
        if tools_for:                                    # mở từ nút "Công cụ" của cửa sổ máy: chỉ hiện cửa sổ Công cụ
            self.root.withdraw(); self._open_tools(tools_for)
        elif self.auth.logged_in: self.show_list()
        else: self.show_login()

    def _open_tools(self, pid):
        import tkinter.messagebox as mb
        def job():
            try:
                p = next((x for x in self.auth.phones() if str(x.get("id")) == pid), None)
                if not p: raise ApiError(404, "Không tìm thấy máy này trong tài khoản.")
                self.ui(lambda: ToolsDlg(self, p))
            except Exception as e:
                m = str(e); self.ui(lambda: (mb.showerror("CloudBlue", m), self.root.destroy()))
        threading.Thread(target=job, daemon=True).start()

    def clear(self):
        for w in self.body.winfo_children(): w.destroy()

    def btn(self, parent, text, cmd, kind="primary", **kw):
        bg = {"primary": ACC, "ghost": CARD, "soft": LINE, "danger": "#3a1d27"}[kind]; fg = TXT
        o = dict(padx=14, pady=7); o.update(kw)
        b = self.tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground="#4b8cff" if kind == "primary" else "#2a3a5c",
                           activeforeground=TXT, relief="flat", bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2", **o)
        return b

    def ui(self, fn):
        """Luồng nền gửi việc cập nhật giao diện về luồng chính (Tk chỉ an toàn khi gọi từ luồng chính)."""
        self._q.put(fn)

    def _pump(self):
        try:
            while True:
                fn = self._q.get_nowait()
                try: fn()
                except Exception: log("ui:", traceback.format_exc())
        except queue.Empty: pass
        try: self.root.after(40, self._pump)
        except Exception: pass

    def _wheel(self, e):
        """Lăn chuột cuộn đúng cửa sổ đang trỏ vào (danh sách máy hoặc hộp thoại mua / nạp)."""
        try: cv = self.scrollers.get(str(e.widget.winfo_toplevel()))
        except Exception: return
        if cv is not None and cv.winfo_exists(): cv.yview_scroll(int(-e.delta / 120), "units")

    # ---------- mua / nạp / gia hạn / nâng cấp / huỷ (cửa sổ con) ----------
    def open_order(self): OrderDlg(self)
    def open_topup(self, need=0): TopupDlg(self, need)
    def open_renew(self, p): RenewDlg(self, p)
    def open_upgrade(self, p): UpgradeDlg(self, p)
    def open_switch(self, p): SwitchDlg(self, p)

    def switch_note(self, p):
        """Chữ cho máy MỚI của lệnh đổi Android (SQL v28: máy cũ bị xoá TRƯỚC, xoá xong mới tạo máy mới)."""
        v = p.get("android") or "?"
        if any(str(r.get("id")) == str(p.get("replaces")) and r.get("status") in ("active", "expired") for r in getattr(self, "rows_last", []) or []):
            return f"🔄 Máy mới đổi sang Android {v} — đang tạo (2–5 phút), xong thì máy cũ tự xoá."
        if p.get("node") == "wait-old": return f"🔄 Đang xoá máy cũ… xoá xong tự tạo máy Android {v} (2–5 phút)."
        e = str(p.get("error") or "")
        return f"🔄 Máy cũ đã xoá — đang tạo máy Android {v} (2–5 phút)." + ("\n" + e if e.startswith("Đổi Android:") else "")

    def switching(self, p):
        """Máy đang đổi Android dở (máy mới còn đang tạo)?"""
        t = p.get("switch_to")
        return bool(t) and any(str(r.get("id")) == str(t) and r.get("status") in ("pending", "creating") for r in getattr(self, "rows_last", []) or [])

    def cancel(self, p):
        import tkinter.messagebox as mb
        if not mb.askyesno("Huỷ máy", f"Huỷ máy “{p.get('name')}”?\n\nMáy và TOÀN BỘ dữ liệu trong máy sẽ bị XOÁ vĩnh viễn, không hoàn tiền.",
                           icon="warning", default="no", parent=self.root): return
        def job():
            try:
                self.auth.rpc("cloudphone_cancel", {"p_id": p["id"]})
                self.ui(lambda: (self.refresh(), mb.showinfo("CloudBlue", "Đang huỷ máy — máy sẽ biến mất khỏi danh sách trong ít phút.", parent=self.root)))
            except Exception as e:
                m = str(e); self.ui(lambda m=m: mb.showerror("CloudBlue", m, parent=self.root))
        threading.Thread(target=job, daemon=True).start()

    def more(self, p, widget):
        """Menu "Khác" của 1 máy: công cụ (xoay màn, độ rộng, cài app, ứng dụng, clone tab…), nâng cấp RAM/CPU, huỷ máy."""
        m = self.tk.Menu(self.root, tearoff=0, bg=CARD, fg=TXT, activebackground=ACC, activeforeground=TXT, font=("Segoe UI", 10))
        can_up = p.get("status") == "active" and not p.get("locked") and not p.get("is_free") and p.get("pending_ram") is None
        on = p.get("status") == "active" and (not p.get("locked") or (getattr(self, "prof", None) or {}).get("role") == "admin")
        for lab, tab in (("Xoay màn · Độ rộng nhỏ nhất…", "screen"), ("Cài app (APK / link)…", "install"), ("Ứng dụng trong máy…", "apps"),
                         ("Clone tab…", "clone"), ("Root theo app…", "root"), ("Khác: mở link, GPS, chụp màn…", "more")):
            m.add_command(label=lab, command=lambda t=tab: ToolsDlg(self, p, t), state="normal" if on else "disabled")
        m.add_separator()
        m.add_command(label="Nâng cấp RAM / CPU", command=lambda: self.open_upgrade(p), state="normal" if can_up else "disabled")
        sw = self.switching(p); can_sw = p.get("status") == "active" and not p.get("locked") and not sw
        m.add_command(label="Đang đổi Android… (chờ máy mới)" if sw else "Đổi Android (9 / 12 / 15)…", command=lambda: self.open_switch(p),
                      state="normal" if can_sw else "disabled")
        m.add_separator()
        m.add_command(label="Huỷ máy (xoá vĩnh viễn)", command=lambda: self.cancel(p))
        try: m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally: m.grab_release()

    # ---------- đăng nhập ----------
    def show_login(self, msg=""):
        tk = self.tk; self.clear()
        box = tk.Frame(self.body, bg=BG); box.place(relx=0.5, rely=0.45, anchor="center")
        hb = tk.Frame(box, bg=BG); hb.pack()                        # chữ "CloudBlue" 2 màu giống logo web
        for t, c in (("Cloud", TXT), ("Blue", BRAND)):
            tk.Label(hb, text=t, font=("Segoe UI", 26, "bold"), fg=c, bg=BG, bd=0, padx=0, highlightthickness=0).pack(side="left")
        tk.Label(box, text="Điện thoại đám mây — điều khiển trên máy tính", font=self.f_t, fg=DIM, bg=BG).pack(pady=(2, 22))
        ents = {}
        for k, lab, show in (("email", "Email", ""), ("pw", "Mật khẩu", "•")):
            tk.Label(box, text=lab, font=self.f_t, fg=DIM, bg=BG, anchor="w").pack(fill="x")
            e = tk.Entry(box, font=("Segoe UI", 12), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat", show=show, width=30)
            e.pack(fill="x", ipady=8, pady=(3, 12)); ents[k] = e
        ents["email"].insert(0, prefs().get("email", ""))
        err = tk.Label(box, text=msg, font=self.f_t, fg=BAD, bg=BG, wraplength=320, justify="left"); err.pack(fill="x")
        def go(*_):
            if self.busy: return
            em, pw = ents["email"].get().strip(), ents["pw"].get()
            if not em or not pw: err.config(text="Nhập email và mật khẩu."); return
            self.busy = True; b.config(text="Đang đăng nhập…")
            def job():
                try:
                    self.auth.login(em, pw); prefs({"email": em}); self.ui(self.show_list)
                except Exception as e:
                    m = str(e); self.ui(lambda m=m: (err.config(text=m), b.config(text="Đăng nhập")))
                finally: self.busy = False
            threading.Thread(target=job, daemon=True).start()
        b = self.btn(box, "Đăng nhập", go); b.pack(fill="x", pady=(8, 10))
        ents["pw"].bind("<Return>", go); ents["email"].bind("<Return>", lambda *_: ents["pw"].focus_set())
        lk = tk.Label(box, text="Chưa có tài khoản? Đăng ký trên web  ↗", font=self.f_t, fg=ACC, bg=BG, cursor="hand2"); lk.pack()
        lk.bind("<Button-1>", lambda *_: webbrowser.open(WEB))
        (ents["pw"] if ents["email"].get() else ents["email"]).focus_set()

    # ---------- danh sách máy ----------
    def show_list(self):
        tk = self.tk; self.clear()
        top = tk.Frame(self.body, bg=BG); top.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(top, text="Máy của tôi", font=self.f_h1, fg=TXT, bg=BG).pack(side="left")
        self.btn(top, "Đăng xuất", self.logout, "ghost").pack(side="right")
        self.btn(top, "⟳ Làm mới", self.refresh, "ghost").pack(side="right", padx=6)
        sub = tk.Frame(self.body, bg=BG); sub.pack(fill="x", padx=18)
        tk.Label(sub, text=self.auth.email, font=self.f_s, fg=DIM, bg=BG).pack(side="left")
        lk = tk.Label(sub, text="Mở web ↗", font=self.f_s, fg=ACC, bg=BG, cursor="hand2"); lk.pack(side="right")
        lk.bind("<Button-1>", lambda *_: webbrowser.open(WEB))
        self.upd_slot = tk.Frame(self.body, bg=BG); self.upd_slot.pack(fill="x", padx=18)    # báo có bản app mới (nếu có)
        self._paint_update()
        shop = tk.Frame(self.body, bg=CARD, highlightbackground=LINE, highlightthickness=1); shop.pack(fill="x", padx=18, pady=(10, 0))
        bl = tk.Frame(shop, bg=CARD); bl.pack(side="left", padx=14, pady=8)
        tk.Label(bl, text="Số dư", font=self.f_s, fg=DIM, bg=CARD, anchor="w").pack(fill="x")
        self.bal = tk.Label(bl, text="…", font=("Segoe UI", 15, "bold"), fg=TXT, bg=CARD, anchor="w"); self.bal.pack(fill="x")
        self.btn(shop, "+ Thuê máy", self.open_order).pack(side="right", padx=(6, 12), pady=10)
        self.btn(shop, "Nạp tiền", self.open_topup, "soft").pack(side="right", pady=10)
        self.btn(shop, "🎟 Nhập mã", lambda: CodeDlg(self), "soft").pack(side="right", padx=(0, 6), pady=10)
        self.blue_btn = self.btn(shop, "💎 Tích Blue", lambda: BlueDlg(self), "soft")      # hiện khi máy chủ đã bật Tích Blue (SQL v27)
        wrap = tk.Frame(self.body, bg=BG); wrap.pack(fill="both", expand=True, padx=10, pady=10)
        cv = tk.Canvas(wrap, bg=BG, highlightthickness=0); sb = tk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        self.list = tk.Frame(cv, bg=BG); win = cv.create_window((0, 0), window=self.list, anchor="nw")
        self.list.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set); cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.scrollers[str(self.root)] = cv
        self.msg = tk.Label(self.list, text="Đang tải…", font=self.f_t, fg=DIM, bg=BG); self.msg.pack(pady=30)
        self.refresh()
        self._tick()

    def _tick(self):
        if hasattr(self, "list") and self.list.winfo_exists():
            self.refresh(quiet=True)
            self.root.after(20000, self._tick)

    def refresh(self, quiet=False):
        def job():
            try:
                rows = self.auth.phones()
                if not getattr(self, "_site_ok", False) or time.time() - getattr(self, "_site_t", 0) > 300:   # tên miền web + bản app tối thiểu (5 phút/lần)
                    try:
                        sd = self.shop.site(); self._site_ok = True; self._site_t = time.time()
                        OUTDATED["min"] = str(sd.get("min_app_pc") or "").strip()
                    except Exception: pass
                if FROZEN and (not getattr(self, "_upd_checked", False) or (must_update() and not getattr(self, "update_info", None))):
                    self._upd_checked = True                       # 1 lần mỗi lần mở app (bắt buộc cập nhật mà chưa đọc được → đọc lại)
                    try:
                        code, raw = http("GET", WEB.rstrip("/") + "/download/pc.json", timeout=10)
                        j = json.loads(raw.decode("utf-8") or "{}") if code == 200 else {}
                        if isinstance(j, dict) and int(num(j.get("code"))) > app_code(): self.update_info = j
                    except Exception as e: log("update check:", e)
                try: prof = self.shop.profile()
                except ApiError as e:
                    if e.code == 401: raise
                    prof = None
                if time.time() - BLUE["t"] > 60: blue_load(self.auth)          # 💎 Tích Blue (tối đa 1 lần / phút)
                def show():
                    self._paint_update(); self._paint_blue()
                    if prof is not None: self.prof = prof
                    if prof is not None and hasattr(self, "bal") and self.bal.winfo_exists():
                        self.bal.config(text=vnd(prof.get("balance")) + (f"  · CTV −{int(num(prof.get('ctv_discount')))}%" if is_ctv(prof) else ""))
                    self.render(rows)
                self.ui(show)
            except ApiError as e:
                m = str(e)
                if e.code == 401: self.ui(lambda m=m: self.show_login(m))
                elif not quiet: self.ui(lambda m=m: self.msg.config(text=m) if self.msg.winfo_exists() else None)
            except Exception as e:
                log("refresh:", traceback.format_exc())
        threading.Thread(target=job, daemon=True).start()

    def _paint_blue(self):
        b = getattr(self, "blue_btn", None)
        if b is None or not b.winfo_exists(): return
        if not blue_on(): b.pack_forget(); return
        n = blue_todo()
        b.config(text=f"💎 {blue_n(BLUE['info'].get('blue'))} Blue" + (f"  •{n}" if n else ""))
        if not b.winfo_manager(): b.pack(side="right", padx=(0, 6), pady=10)
        i = BLUE["info"]; k, d = "blue_nudge_" + str(self.auth.uid or ""), vn_today()
        if i and not i.get("today") and prefs().get(k) != d:
            prefs({k: d})
            try:
                import tkinter.messagebox as mb
                self.root.after(800, lambda: mb.askyesno("💎 Tích Blue", f"Hôm nay bạn chưa điểm danh — nhận +{blue_n(i.get('next_got'))} Blue ngay?",
                                                         parent=self.root) and BlueDlg(self))
            except Exception: pass

    def _paint_update(self):
        """Dải báo trên danh sách máy: "Có bản app mới — Cập nhật" (bấm 1 lần: tự tải, thay bản, mở lại) / "Đã cập nhật lên bản …".
           Bắt buộc cập nhật (app quá cũ) → dải ĐỎ, danh sách máy ẩn tới khi cập nhật."""
        u = getattr(self, "update_info", None); slot = getattr(self, "upd_slot", None)
        if slot is None or not slot.winfo_exists(): return
        mode = "force" if must_update() else ("avail" if u else ("done" if self.just_updated else ""))
        if slot.winfo_children() and getattr(self, "_upd_mode", None) == mode: return
        for w in slot.winfo_children(): w.destroy()
        self._upd_mode = mode
        tk = self.tk
        if mode == "force":
            C2 = "#3a1420"
            b = tk.Frame(slot, bg=C2, highlightbackground=BAD, highlightthickness=1); b.pack(fill="x", pady=(10, 0))
            go = self.btn(b, "⬇ Cập nhật ngay", (lambda: UpdateDlg(self, u)) if u else (lambda: webbrowser.open(WEB.rstrip("/") + "/download/CloudBluePC.zip")),
                          padx=12, pady=6)
            go.pack(side="right", padx=10, pady=10)
            tk.Label(b, text=f"⛔ Bắt buộc cập nhật — bản {APP_VER} đã cũ", font=("Segoe UI", 11, "bold"), fg="#ffd0d0", bg=C2, anchor="w").pack(fill="x", padx=12, pady=(10, 0))
            tk.Label(b, text=(f"Cập nhật lên bản {u.get('version')} mới dùng tiếp được. " if u and u.get("version") else "Tải bản mới nhất mới dùng tiếp được. ")
                     + "Tài khoản và máy của bạn giữ nguyên.", font=self.f_s, fg=TXT, bg=C2, anchor="w", justify="left", wraplength=420).pack(fill="x", padx=12, pady=(0, 10))
            return
        if not u:
            if self.just_updated:
                tk.Label(slot, text=f"✓ Đã cập nhật lên bản {APP_VER}.", font=("Segoe UI", 10, "bold"), fg=OK, bg=BG, anchor="w").pack(fill="x", pady=(8, 0))
            return
        C2 = "#14324f"
        b = tk.Frame(slot, bg=C2, highlightbackground=ACC, highlightthickness=1, cursor="hand2"); b.pack(fill="x", pady=(10, 0))
        go = self.btn(b, "Cập nhật", lambda: UpdateDlg(self, u), padx=12, pady=5); go.pack(side="right", padx=10, pady=8)
        t1 = tk.Label(b, text=f"Có bản app mới {u.get('version') or ''} (đang dùng {APP_VER})", font=("Segoe UI", 10, "bold"), fg=TXT, bg=C2, anchor="w", cursor="hand2")
        t2 = tk.Label(b, text="Bấm Cập nhật: app tự tải, thay bản mới rồi tự mở lại — tài khoản giữ nguyên." if can_self_update() and parent_writable()
                      else "Bấm Cập nhật để xem cách tải bản mới.", font=self.f_s, fg=DIM, bg=C2, anchor="w", cursor="hand2", justify="left", wraplength=400)
        t1.pack(fill="x", padx=12, pady=(8, 0)); t2.pack(fill="x", padx=12, pady=(0, 8))
        for w in (b, t1, t2): w.bind("<Button-1>", lambda *_: UpdateDlg(self, u))

    def render(self, rows):
        tk = self.tk; self.rows_last = rows
        if not self.list.winfo_exists(): return
        for w in self.list.winfo_children(): w.destroy()
        if must_update():                                  # app quá cũ: không cho mở / thuê máy tới khi cập nhật
            tk.Label(self.list, text="Cần cập nhật app để dùng tiếp", font=self.f_h2, fg=TXT, bg=BG).pack(pady=(40, 6))
            tk.Label(self.list, text="Bấm ⬇ Cập nhật ngay ở dải đỏ phía trên — app tự tải, thay bản mới và mở lại.", font=self.f_t, fg=DIM, bg=BG).pack()
            self.msg = tk.Label(self.list, bg=BG); return
        if self._fast: self.root.after_cancel(self._fast); self._fast = None
        if any(p.get("status") in ("pending", "cancelling") or p.get("pending_ram") is not None for p in rows):
            self._fast = self.root.after(6000, lambda: self.refresh(quiet=True))         # máy đang tạo / nâng cấp → cập nhật nhanh hơn
        if not rows:
            tk.Label(self.list, text="Bạn chưa có máy nào.", font=self.f_h2, fg=TXT, bg=BG).pack(pady=(40, 6))
            tk.Label(self.list, text="Thuê máy ngay trong app — chọn cấu hình, thanh toán bằng số dư.", font=self.f_t, fg=DIM, bg=BG).pack()
            self.btn(self.list, "+ Thuê máy", self.open_order).pack(pady=14)
            self.msg = tk.Label(self.list, bg=BG); return
        self.msg = tk.Label(self.list, bg=BG)
        for p in rows: self._card(p)
        if self.open_id:
            pid, self.open_id = self.open_id, None
            if any(str(p.get("id")) == pid for p in rows): spawn_viewer(pid)

    def _card(self, p):
        tk = self.tk
        c = tk.Frame(self.list, bg=CARD, highlightbackground=LINE, highlightthickness=1); c.pack(fill="x", padx=8, pady=6)
        row = tk.Frame(c, bg=CARD); row.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(row, text=p.get("name") or "Máy", font=self.f_h2, fg=TXT, bg=CARD).pack(side="left")
        st, col = STATUS.get(p.get("status"), (p.get("status") or "", DIM))
        tk.Label(row, text="● " + st, font=("Segoe UI", 9, "bold"), fg=col, bg=CARD).pack(side="right")
        info = f"{p.get('ram')}GB RAM · {p.get('cpu')} nhân · {p.get('res') or ''} · {p.get('fps') or 30} FPS · Android {p.get('android') or '9'}"
        if p.get("shared"): info += " · được chia sẻ"
        tk.Label(c, text=info, font=self.f_t, fg=DIM, bg=CARD, anchor="w").pack(fill="x", padx=14)
        if p.get("expires_at"): tk.Label(c, text="⏱ " + fmt_left(p["expires_at"]), font=self.f_s, fg=DIM, bg=CARD, anchor="w").pack(fill="x", padx=14, pady=(2, 0))
        if p.get("status") == "error" and p.get("error"): tk.Label(c, text=p["error"], font=self.f_s, fg=BAD, bg=CARD, anchor="w", wraplength=440, justify="left").pack(fill="x", padx=14)
        if p.get("replaces") and p.get("status") in ("pending", "creating"):
            tk.Label(c, text=self.switch_note(p), font=self.f_s, fg=WARN, bg=CARD,
                     anchor="w", wraplength=440, justify="left").pack(fill="x", padx=14)
        elif self.switching(p):
            tk.Label(c, text="🔄 Đang đổi Android: máy mới đang tạo, máy này vẫn dùng được tới lúc đó rồi tự xoá.", font=self.f_s, fg=WARN, bg=CARD,
                     anchor="w", wraplength=440, justify="left").pack(fill="x", padx=14)
        elif p.get("status") == "active" and str(p.get("error") or "").startswith("Đổi Android"):
            tk.Label(c, text=p["error"], font=self.f_s, fg=BAD, bg=CARD, anchor="w", wraplength=440, justify="left").pack(fill="x", padx=14)
        if p.get("pending_ram") is not None:
            tk.Label(c, text=f"⏳ Đang nâng cấp lên {p.get('pending_ram')}GB · {p.get('pending_cpu')} nhân…", font=self.f_s, fg=WARN, bg=CARD, anchor="w").pack(fill="x", padx=14)
        bar = tk.Frame(c, bg=CARD); bar.pack(fill="x", padx=14, pady=(10, 12))
        st = p.get("status"); adm = (getattr(self, "prof", None) or {}).get("role") == "admin"
        active = st == "active" and (not p.get("locked") or adm)                 # admin: toàn quyền (kể cả máy bị khoá, lúc bảo trì)
        b = self.btn(bar, "▶  Điều khiển", lambda pid=str(p["id"]): spawn_viewer(pid)); b.pack(side="left")
        if not active: b.config(state="disabled", bg=LINE)
        if active: self.btn(bar, "Khởi động lại", lambda q=p: self.reboot(q), "ghost").pack(side="left", padx=8)
        if p.get("shared"): return                                  # máy người khác chia sẻ: chỉ điều khiển
        mo = self.btn(bar, "Khác ▾", None, "soft", padx=10); mo.config(command=lambda q=p, w=mo: self.more(q, w)); mo.pack(side="right")
        if st in ("active", "expired") and not p.get("is_free"):
            self.btn(bar, "Gia hạn", lambda q=p: self.open_renew(q), "soft").pack(side="right", padx=(0, 6))

    def reboot(self, p):
        import tkinter.messagebox as mb
        if not mb.askyesno("Khởi động lại", f"Khởi động lại máy “{p.get('name')}”? Mất khoảng 1 phút."): return
        def job():
            try:
                CpClient(self.auth, p["id"]).json("POST", "reboot", {})
                self.ui(lambda: mb.showinfo("CloudBlue", "Đang khởi động lại máy — chờ khoảng 1 phút rồi mở lại."))
            except Exception as e:
                m = str(e); self.ui(lambda m=m: mb.showerror("CloudBlue", m))
        threading.Thread(target=job, daemon=True).start()

    def logout(self):
        self.auth.logout(); self.show_login()

    def run(self): self.root.mainloop()


def selftest(out):
    """Mở thử mọi thư viện cửa sổ máy cần (giải mã H.264, cửa sổ GPU, tkinter) → ghi kết quả ra file."""
    res = []
    try:
        import av, numpy, pygame, tkinter, ssl, brstream, qrcodegen              # noqa: F401,E401
        from pygame._sdl2.video import Window, Renderer, Texture                 # noqa: F401
        ctx = av.CodecContext.create("h264", "r"); ctx.options = {"flags": "+low_delay"}
        res.append(f"av {av.__version__} · pygame {pygame.version.ver} · numpy {numpy.__version__} · {ssl.OPENSSL_VERSION}")
        res.append(f"procs {len(procs_at(sys.executable))} · app folder ok {app_folder_ok(HERE)}")    # đọc được tiến trình (cần cho tự cập nhật)
        pygame.init()
        try:
            w = Window("selftest", size=(64, 64), hidden=True); r = Renderer(w)
            s = pygame.image.frombuffer(numpy.zeros((16, 16, 3), numpy.uint8).tobytes(), (16, 16), "RGB")
            Texture.from_surface(r, s).draw(dstrect=(0, 0, 16, 16)); r.present(); res.append("gpu ok")
        except Exception as e: res.append(f"gpu: {e} (dùng CPU)")
        pygame.quit()
        res.insert(0, "OK")
    except Exception:
        res.insert(0, "FAIL"); res.append(traceback.format_exc())
    with open(out, "w", encoding="utf-8") as f: f.write("\n".join(res) + "\n")


def main():
    if os.name == "nt":
        try:
            import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(2)      # chữ / hình nét trên màn hình phóng to 125–150%
        except Exception: pass
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--selftest":                 # GitHub Actions: kiểm tra bản exe có đủ thư viện trước khi đưa khách
        return selftest(args[1])
    if len(args) >= 3 and args[0] == "--finish-update":              # bản mới vừa tải: thay thư mục app cũ rồi mở lại app
        t = args.index("--test") if "--test" in args else -1
        try: wp = int(args[2])
        except ValueError: wp = 0
        return run_finish_update(args[1], wp, args[t + 1] if 0 <= t < len(args) - 1 else None)
    if len(args) >= 2 and args[0] == "--view":
        return run_viewer(args[1])
    if len(args) >= 2 and args[0] == "--tools":
        if not UUID_RE.fullmatch(args[1]) or not Auth().logged_in: return
        return Launcher(tools_for=args[1]).run()
    link = next((a for a in args if a.lower().startswith("blueroblox:")), "")
    m = UUID_RE.search(link)
    open_id = m.group(0) if m else None
    register_protocol()
    if open_id and Auth().logged_in:
        spawn_viewer(open_id); return                     # bấm "Mở bằng app" trên web → mở thẳng cửa sổ máy
    Launcher(open_id, updated="--updated" in args).run()


if __name__ == "__main__":
    main()
