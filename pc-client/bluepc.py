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


# 16/11 · CỠ CHỮ do khách tự chỉnh (🎨 Giao diện): 80–130%, nhớ theo máy. 100% = y như cũ.
UI_MIN, UI_MAX, UI_STEP = 80, 130, 5
def ui_scale():
    try: v = int(float(prefs().get("ui_scale") or 100))
    except (TypeError, ValueError): v = 100
    return max(UI_MIN, min(UI_MAX, v))


# 16/11c · TIẾNG VIỆT / ENGLISH: khách chọn ở 🌐 (màn đăng nhập · dưới "Máy của tôi" · 🎨 Giao diện) → nhớ trong settings.json.
#   Chưa chọn → theo Windows: ngôn ngữ hiển thị / định dạng / vùng là Việt Nam → tiếng Việt, còn lại → English.
#   English: bluepc_en.py dịch mọi chữ Tk (nhãn, nút, menu, hộp thoại, tiêu đề) + chữ cửa sổ máy (T()). Thiếu file → tiếng Việt như cũ.
def _sys_vi():
    if os.name != "nt": return True
    try:
        import ctypes; k = ctypes.windll.kernel32
        if (k.GetUserDefaultUILanguage() & 0x3FF) == 0x2A or (k.GetUserDefaultLCID() & 0x3FF) == 0x2A: return True
        return k.GetUserGeoID(16) == 251                          # GEOCLASS_NATION · 251 = Việt Nam
    except Exception: return True


def ui_lang():
    v = str(prefs().get("lang") or "")
    return v if v in ("vi", "en") else ("vi" if _sys_vi() else "en")


LANG, EN_UI = ui_lang(), None
if LANG == "en":
    try:
        import bluepc_en; bluepc_en.install(); EN_UI = bluepc_en
    except Exception as _e:
        LANG = "vi"; log("lang en:", repr(_e))


def T(s): return EN_UI.tr(s) if EN_UI else s
def L(vi, en): return en if EN_UI else vi


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
    "APP_OUTDATED": "Bản app này đã cũ — phải cập nhật mới dùng tiếp được.",
    "Invalid login credentials": "Sai email hoặc mật khẩu.", "Email not confirmed": "Email chưa xác nhận — mở hộp thư để xác nhận.",
    "SESSION_EXPIRED": "Phiên đăng nhập hết hạn, hãy đăng nhập lại.", "NOT_LOGGED_IN": "Hãy đăng nhập.",
    "NOT_ALLOWED": "Bạn không có quyền mở máy này.", "NOT_FOUND": "Không tìm thấy máy.", "MAINTENANCE": "Hệ thống đang bảo trì.",
    "SWITCH_EXPIRING": "Máy còn dưới 30 phút — gia hạn trước rồi hãy đổi Android.", "SWITCH_BUSY": "Máy đang nâng cấp / gia hạn — chờ 1–2 phút rồi đổi Android.",
    "SWITCHING": "Máy đang đổi Android — chờ máy mới tạo xong (2–5 phút).", "SWITCH_SAME": "Máy đang chạy bản Android này rồi.",
    "SWITCH_LIMIT": "Mỗi tài khoản đổi Android tối đa 3 lần trong 24 giờ.", "NO_PHONE": "Không tìm thấy máy (hoặc máy không phải của bạn).",
    "PHONE_NOT_ACTIVE": "Máy phải đang chạy mới làm được việc này.", "PHONE_LOCKED": "Máy đang bị khoá.", "BAD_ANDROID": "Bản Android này chưa bán.",
    "Service for this project is restricted": "⚠️ Hệ thống đang bảo trì nên tạm thời chưa đăng nhập / tải dữ liệu được. Vui lòng thử lại sau ít phút.",
    "SERVER_OFFLINE": "Máy chủ bản Android này đang bảo trì — thử lại sau.", "OUT_OF_CAPACITY": "Máy chủ bản Android này đang hết chỗ — chọn bản khác hoặc thử lại sau.",
}


class ApiError(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code = code


def _dev_id():
    """Mã thiết bị (bản BĂM, không gửi mã gốc) gửi kèm yêu cầu lên Supabase (header x-cb-dev, SQL v29): nhiều tài khoản trên CÙNG 1 máy
       là bot gác nhận ra (chống cày Blue bằng clone). Ghép mã cài Windows + card mạng → máy quán net dùng chung ảnh Windows vẫn khác nhau."""
    parts = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
            parts.append(str(winreg.QueryValueEx(k, "MachineGuid")[0]))
    except Exception: pass
    try:
        import uuid
        n = uuid.getnode()
        if not (n >> 40) & 1: parts.append("%012x" % n)          # bỏ MAC ngẫu nhiên (bit multicast) — Python tự bịa khi không đọc được
    except Exception: pass
    if not parts:
        try:
            f = os.path.join(DATA, "dev.id")
            if not os.path.exists(f):
                os.makedirs(DATA, exist_ok=True); open(f, "w").write(secrets.token_hex(16))
            parts.append(open(f).read().strip())
        except Exception: return ""
    return "p-" + hashlib.sha256(("cloudblue-dev:" + "|".join(parts)).encode()).hexdigest()[:32]


DEV_ID = _dev_id()


def http(method, url, body=None, headers=None, timeout=25):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    h = {"Accept": "application/json", "User-Agent": f"BlueRobloxPC/{APP_VER}"}
    if DEV_ID and url.startswith(SB): h["x-cb-dev"] = DEV_ID                   # chỉ gửi cho Supabase
    if isinstance(body, (dict, list)): h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(0, "Không có kết nối mạng.") from e


SAID = {}                                              # câu máy chủ vừa trả → mã lỗi của câu đó (để biết lỗi thuộc ô mã giảm giá)
def err_text(code, raw):
    try:
        j = json.loads(raw.decode("utf-8") or "{}")
        m = next((j.get(k) for k in ("error_description", "msg", "message", "error") if j.get(k)), "") if isinstance(j, dict) else ""
    except Exception:
        m = ""
    if "APP_OUTDATED" in (m or ""): OUTDATED["v"] = True
    sm = re.match(r"^(.{12,}?)\s*\(([A-Z][A-Z0-9]*_[A-Z0-9_]+)\)\s*$", (m or "").strip(), re.S)
    if sm:                                             # v35: máy chủ viết sẵn câu dễ hiểu + (MÃ_LỖI) → hiện đúng câu đó (số tiền / số lần khớp cài đặt admin)
        if len(SAID) > 200: SAID.clear()
        SAID[sm.group(1).strip()] = sm.group(2); return sm.group(1).strip()
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
        # 16/11: gợi ý của máy chủ khi báo lỗi (fix = "reboot" → cho khởi động lại máy · boot = 1 → máy đang được bật, tự thử lại)
        self.err_x = {}; self.fix_arm = 0.0; self.fixing = False; self.auto_at = 0.0; self.auto_n = 0
        self.weak = False; self.stall = False; self.slow = False      # mạng yếu (máy chủ đã giảm nét) · đang đứng hình · chờ máy chủ lâu

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
        elif k == "stats":
            w = bool(d.get("weak")) if isinstance(d, dict) else False        # 16/11: máy chủ đang phải giảm nét vì mạng của khách yếu
            if w and not self.weak: self._say("📶 Mạng yếu — đã giảm nét cho hình mượt.", 6)
            self.weak = w; self.stats = d; self._post()
        elif k == "ping": self.ping = d
        elif k == "state":
            if d[0] == "closed" and self.state[0] in ("kicked", "error"): return      # giữ thông báo lỗi / "mở ở nơi khác"
            self.state = d
            x = d[3] if d[0] == "error" and len(d) > 3 and isinstance(d[3], dict) else {}
            if d[0] == "error" and not x and "Khởi động lại máy" in str(d[1]): x = {"fix": "reboot"}      # brstream bản cũ không chuyển gợi ý → đọc theo câu
            self.err_x = x
            if d[0] == "error" and x.get("boot") and self.auto_n < 40:       # máy đang được bật lại → tự thử lại sau 6 giây (tối đa ~4 phút)
                self.auto_n += 1; self.auto_at = time.time() + 6
            if d[0] == "connected":
                self.auto_n = 0; self.auto_at = 0.0
                self.path = d[1]
                if self.cli and self.cli.prefer: prefs({"path_" + str(self.node): list(self.cli.prefer)})
                if not getattr(self, "_upd_tried", False):             # có bản app mới → nhắc ngay trong cửa sổ máy
                    self._upd_tried = True; threading.Thread(target=self._upd_note, daemon=True).start()
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
            dirty |= self._watch()
            if dirty: self._draw(pygame); dirty = False
            clock.tick(500)
        if self.cli: self.cli.close()
        pygame.quit()

    def _watch(self):
        """16/11 · gọi ~4 lần / giây: tự thử lại khi máy đang được bật · báo đứng hình vì mạng chậm · nói rõ khi chờ máy chủ lâu. Trả True nếu cần vẽ lại."""
        now = time.time(); ch = False; c = self.cli; st = self.state[0]
        if self.auto_at and now >= self.auto_at:
            self.auto_at = 0.0
            if st == "error" and not self.fixing: self._retry(); ch = True
        rx = getattr(c, "last_rx", 0) if c is not None else 0
        if st == "connected" and rx:
            q = now - rx
            if q > 2.5 and not self.stall: self.stall = True; self._say("⏳ Mạng chậm — đang chờ hình…", 6)
            elif q < 1.0 and self.stall:
                self.stall = False; n = self.notice
                if n and str(n[0]).startswith("⏳"): self.notice = None; ch = True
        else: self.stall = False
        ht = getattr(c, "hello_t", 0) if c is not None else 0
        slow = bool(st in ("connecting", "reconnecting") and not self.fixing and ht and now - ht > 8 and rx and now - rx < 5)
        if slow != self.slow: self.slow = slow; ch = True
        return ch

    def _fix_click(self):
        """Lỗi có gợi ý "Khởi động lại máy": bấm / phím K lần 1 = hỏi lại (8 giây), lần 2 = làm (cửa sổ máy không có hộp hỏi)."""
        if self.fixing: return
        if time.time() < self.fix_arm: self.fix_arm = 0.0; return self._fix_reboot()
        self.fix_arm = time.time() + 8
        self._say("Bấm lần nữa (hoặc phím K) để KHỞI ĐỘNG LẠI máy — khoảng 1–2 phút. App đang mở trong máy sẽ tắt, dữ liệu vẫn giữ nguyên.", 8)

    def _fix_reboot(self):
        """Khởi động lại máy rồi CHỜ máy chủ làm xong mới nối lại (không nối trong lúc máy đang tắt / bật)."""
        if self.fixing: return
        self.fixing = True; self.notice = None; self.auto_at = 0.0; self.err_x = {}
        old, self.cli = self.cli, None; self.gen += 1
        if old: threading.Thread(target=old.close, daemon=True).start()
        self.kicked = False; self.state = ("connecting", "Đang khởi động lại máy… (1–2 phút)"); self.need_key = True; self._post()
        def job():
            try:
                cp = self._cp(); j = cp.json("POST", "reboot", {}, timeout=60)
                def prog(m): self.state = ("connecting", str(m)); self._post()
                if j.get("job"): cp.wait_job(j["job"], prog, limit=420)
                else: time.sleep(45)
            except Exception as e:
                log("fix reboot:", e)
                self.fixing = False
                self.state = ("error", "Chưa khởi động lại được: " + (str(e) or "lỗi") + " Bấm R để thử lại; vẫn lỗi thì báo hỗ trợ kèm tên máy."); self._post(); return
            self.fixing = False
            self.state = ("connecting", "Máy đã khởi động lại — đang kết nối…"); self._post()
            self._connect_bg()
        threading.Thread(target=job, daemon=True).start()

    def _connect_bg(self):
        try: self.connect()
        except Exception as e:
            self.state = ("error", str(e)); log("connect:", traceback.format_exc()); self._post()
            if must_update() and not getattr(self, "_outdated_seen", False):
                self._outdated_seen = True; threading.Thread(target=self._outdated, daemon=True).start()

    # ---------- cập nhật app ngay trong cửa sổ máy ----------
    def _outdated(self):
        """Máy chủ báo app đã cũ: có bản mới trên web → tự mở trình cập nhật (tải, thay bản, mở lại ĐÚNG máy này).
           Nhiều cửa sổ máy cùng báo / vừa tự cập nhật trong 10 phút → chỉ hiện nút (khỏi mở trình cập nhật lặp)."""
        info = fetch_update_info(force=True)
        if not info:
            self.upd_hint = "Chưa có bản mới trên trang tải — báo shop giúp nhé."; self._post(); return
        self.upd_info = info
        if update_claim(): self._open_updater()
        else: self.upd_hint = f"Bấm phím U hoặc bấm vào đây để cập nhật lên bản {info.get('version') or 'mới'}."; self._post()

    def _open_updater(self):
        """Mở trình cập nhật (danh sách máy ở chế độ cập nhật): tải + thay bản mới → tự mở lại máy này."""
        try: spawn_viewer(self.pid, "--update")
        except Exception as e:
            log("update: không mở được trình cập nhật:", repr(e))
            self.upd_hint = "Không mở được trình cập nhật — mở app CloudBlue PC rồi bấm Cập nhật."; self._post(); return
        self.upd_hint = "Đang cập nhật — app tự tải bản mới, đóng cửa sổ này rồi mở lại máy (khoảng 1 phút)."
        self._say("Đang mở trình cập nhật…", 4.0)

    def _upd_note(self):
        """Đang dùng máy mà web có bản app mới → nhắc 1 dòng (bấm vào để cập nhật) — mỗi bản nhắc tối đa 12 giờ / lần."""
        if not FROZEN: return
        info = fetch_update_info()
        if not info or must_update(): return
        v = str(info.get("version") or ""); seen = prefs().get("upd_note") or {}
        if seen.get("v") == v and time.time() - num(seen.get("t")) < 43200: return
        prefs({"upd_note": {"v": v, "t": time.time()}})
        self._say(f"Có bản app mới {v} — bấm vào đây để cập nhật (app tự tải, máy này tự mở lại).", 15.0, self._open_updater)

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
               self.bar_on, (self.notice or ("",))[0], self.slow, self.err_x.get("fix"), self.err_x.get("boot"), self.weak if self.show_info else 0)
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
                t = self.font_s.render({"auto": "AUTO", "hd": "HD", "bal": L("CB", "BAL"), "eco": L("TK", "ECO")}[self.q], True, c); s.blit(t, t.get_rect(center=(cx, cy)))
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
            lb = self.font_s.render(T(label if name != "quality" else dict(QUALITIES)[self.q]), True, C_DIM if not hot else C_TXT)
            s.blit(lb, lb.get_rect(center=(x + w // 2, y + int(h * 0.80))))

    def _draw_overlay(self, pygame, s, W, H, has_video):
        st = self.state[0]; aw = W - self._bw()
        self.notice_rect = None; n = self.notice
        if n:                                            # thông báo nhỏ phía dưới hình (VD "Đang xoay ngang…", "Đã lưu ảnh…")
            lines = [ln for ln in wrap_text(self.font, T(n[0]), max(120, min(aw - 60, 560))) if ln][:3]
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
            if st == "error":
                x = self.err_x                               # 16/11: máy chủ gợi ý → nói rõ khách cần làm gì (trước đây chỉ "bấm R" rồi lỗi lặp lại)
                lines = [msg, (getattr(self, "upd_hint", "") or "Đang tìm bản mới…") if must_update()
                         else "App tự thử lại sau vài giây — không cần bấm gì." if x.get("boot") and self.auto_at
                         else "Bấm phím K (hoặc bấm vào đây) để KHỞI ĐỘNG LẠI MÁY · phím R: thử lại." if x.get("fix") == "reboot"
                         else "Bấm phím R để thử lại."]
            elif self.slow:                                  # máy chủ đang giữ kết nối chờ máy bật lên (máy vừa tự nghỉ / đang khởi động)
                lines = [msg, "Máy đang được bật lên (thức dậy / khởi động) — thường 1–2 phút, app tự vào khi máy lên."]
            bw = min(aw - 40, 520); rows = []
            for i, ln in enumerate(lines):
                f_ = self.font_b if i == 0 else self.font
                rows += [(f_, w, C_TXT if i == 0 else C_DIM) for w in wrap_text(f_, T(ln), bw - 32) if w]
            rows = rows[:7]; box_h = 30 + 26 * len(rows)
            pygame.draw.rect(s, (10, 16, 30, 215), ((aw - bw) // 2, H // 2 - box_h // 2, bw, box_h), border_radius=14)
            for i, (f_, ln, col) in enumerate(rows):
                t = f_.render(ln, True, col)
                s.blit(t, t.get_rect(center=(aw // 2, H // 2 - box_h // 2 + 26 + 26 * i)))
        if self.show_info and st == "connected":
            d = self.stats
            txt = T(f"{self.fps_show:.0f} khung/s · {d.get('kbps', 0) / 1000:.1f} Mbps · trễ mạng {self.ping} ms · {self.path} · {str(d.get('enc', '')).upper()}")
            if self.weak: txt += T(" · mạng yếu (đã giảm nét)")
            if d.get("drop"): txt += T(f" · bỏ {d['drop']}")
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
            self.kicked = False; self.state = ("connecting", "Đang kết nối…"); self.need_key = True; self.err_x = {}; self.fix_arm = 0.0
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
            if self.state[0] == "error" and e.button == 1 and must_update(): self._open_updater(); return True
            if self.state[0] == "error" and e.button == 1 and self.err_x.get("fix") == "reboot": self._fix_click(); return True
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
            if down and e.key == pygame.K_u and self.state[0] == "error" and must_update(): self._open_updater(); return True
            if down and e.key == pygame.K_k and self.state[0] == "error" and self.err_x.get("fix") == "reboot" and not must_update(): self._fix_click(); return True
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
    "LOCKED": "⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng. Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.", "MIN_AMOUNT": "Số tiền thấp hơn mức nạp tối thiểu.",
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


TIER_COLORS = {"blue": "#6f8cff", "teal": "#2fd3c5", "amber": "#ffb547", "violet": "#a77bff", "rose": "#ff6b8a", "green": "#46d989", "sky": "#38bdf8", "gold": "#f5c451"}
TIERS_DEF = [   # 🎴 5 gói mặc định — giống web (admin chỉnh trên web thì app đọc settings.cp_tiers)
    {"id": "lite", "icon": "💬", "name": "Blue Lite", "vi": "Treo app · nuôi acc", "ram": 2, "cpu": 2, "fps": 30, "res": "", "badge": "", "color": "blue",
     "fvi": ["Zalo, Facebook, TikTok, Telegram", "Chạy 24/7 kể cả khi tắt máy tính"]},
    {"id": "game", "icon": "🎮", "name": "Blue Game", "vi": "Game nhẹ · treo cả ngày", "ram": 4, "cpu": 2, "fps": 30, "res": "", "badge": "", "color": "teal",
     "fvi": ["Game 2D, nhàn rỗi, cờ, bài", "Treo game nhẹ ổn định"]},
    {"id": "roblox", "icon": "🕹️", "name": "Blue Plus", "vi": "Treo game 1 tab mượt", "ram": 4, "cpu": 4, "fps": 30, "res": "", "badge": "🔥 Bán chạy", "color": "amber",
     "fvi": ["1 tab game, đồ hoạ thấp", "Game dùng ~2GB RAM — vẫn còn dư"]},
    {"id": "pro", "icon": "🚀", "name": "Blue Pro", "vi": "Treo 2–4 tab game", "ram": 8, "cpu": 8, "fps": 30, "res": "", "badge": "⭐ Đề xuất", "color": "violet",
     "fvi": ["2–4 tab game cùng lúc", "Mỗi tab thêm cần ~1,5–2GB RAM"]},
    {"id": "max", "icon": "🔥", "name": "Blue Max", "vi": "Game nặng 3D · 60 FPS", "ram": 12, "cpu": 8, "fps": 60, "res": "", "badge": "", "color": "rose",
     "fvi": ["Free Fire, Liên Quân, PUBG Mobile…", "Không có card đồ hoạ — game nặng có thể giật"]},
]


def tier_clean(s):
    """Thẻ hiện cho khách không nhắc tên game: "Roblox" → "game", "Blue Roblox" → "Blue Plus" (gói admin lưu từ trước cũng tự đổi — giống web)."""
    s = str(s or "")
    if "roblox" not in s.lower(): return s
    r = re.sub(r"\s{2,}", " ", re.sub(r"(?i)\bgame(\s+game)+\b", "game", re.sub(r"(?i)roblox", "game", re.sub(r"(?i)blue\s*roblox", "Blue Plus", s)))).strip()
    return r[:1].upper() + r[1:] if r and s[:1].isupper() else r


def tiers_list(site):
    """Gói đang bật (tối đa 8): settings.cp_tiers do admin chỉnh trên web, trống thì 5 gói mặc định."""
    a = (site or {}).get("cp_tiers") if isinstance(site, dict) else None
    out = []
    for t in (a if isinstance(a, list) and a else TIERS_DEF):
        if not isinstance(t, dict) or t.get("on") is False: continue
        ram, cpu, name = int(num(t.get("ram"))), int(num(t.get("cpu"))), tier_clean(str(t.get("name") or "").strip())
        if ram > 0 and cpu > 0 and name:
            fv = (t.get("fen") if EN_UI and t.get("fen") else None) or t.get("fvi") or []
            fit = [tier_clean(str(x).strip()) for x in fv if str(x).strip()][:3]
            out.append({"id": str(t.get("id") or name), "icon": str(t.get("icon") or "📱")[:4], "name": name[:24],
                        "vi": tier_clean((t.get("en") if EN_UI and t.get("en") else None) or t.get("vi"))[:60],
                        "ram": ram, "cpu": cpu, "fps": int(num(t.get("fps"))) or 30, "res": str(t.get("res") or ""), "badge": tier_clean(t.get("badge"))[:20],
                        "color": TIER_COLORS.get(t.get("color"), t.get("color") if re.match(r"^#[0-9a-fA-F]{6}$", str(t.get("color") or "")) else TIER_COLORS["blue"]),
                        "fit": fit})
    return out[:8]


def _mix(a, b, k):
    """Trộn 2 màu #rrggbb: a·k + b·(1−k)."""
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * k + y * (1 - k)) for x, y in zip(pa, pb))


class AndTiles:
    """Bước ① — ô hệ điều hành TO, chia đều 1 hàng: "Android" nhỏ · số bản to · gợi ý. Bấm → set_(v) → on_change()."""
    def __init__(self, app, parent, items, get, set_, on_change, why=None):
        tk = app.tk; self.get, self.why = get, why
        self.frame = tk.Frame(parent, bg=BG); self.tiles = []
        for i, (val, hint) in enumerate(items):
            self.frame.grid_columnconfigure(i, weight=1, uniform="and")
            t = tk.Frame(self.frame, bg=CARD, highlightthickness=1, highlightbackground=LINE, cursor="hand2", height=86)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0), pady=2); t.grid_propagate(False); t.pack_propagate(False)
            inner = tk.Frame(t, bg=CARD); inner.place(relx=.5, rely=.5, anchor="center")
            k = tk.Label(inner, text="Android", font=("Segoe UI", 9, "bold"), bg=CARD, fg=DIM)
            n = tk.Label(inner, text=str(val), font=("Segoe UI", 22, "bold"), bg=CARD, fg=TXT)
            h = tk.Label(inner, text=hint, font=("Segoe UI", 8, "bold"), bg=CARD, fg=WARN)
            for w in (k, n, h): w.pack()
            def click(_e, v=val):
                if self.why and self.why(v): return
                set_(v); on_change()
            for w in (t, inner, k, n, h): w.bind("<Button-1>", click)
            self.tiles.append((val, hint, t, inner, k, n, h))
        self.paint()

    def paint(self):
        cur = self.get()
        for v, hint, t, inner, k, n, h in self.tiles:
            w = self.why(v) if self.why else ""; off = bool(w); on = (v == cur) and not off
            bg = "#1c3f93" if on else CARD
            t.config(bg=bg, highlightthickness=2 if on else 1, highlightbackground="#7cbcff" if on else LINE, cursor="arrow" if off else "hand2")
            inner.config(bg=bg)
            k.config(bg=bg, text="✓ Android" if on else "Android", fg="#cfe4ff" if on else ("#55607a" if off else DIM))
            n.config(bg=bg, fg="#ffffff" if on else ("#55607a" if off else TXT))
            h.config(bg=bg, text=("Bảo trì" if w == "off" else "Hết chỗ") if off else hint, fg=BAD if off else WARN)


class TierList:
    """Bước ② — danh sách gói dọc (thấy đủ hết, không phải kéo ngang): bấm hàng nào chọn hàng đó → dlg.pick_tier(gói).
       Hàng đang chọn: viền màu gói + "✓ Đã chọn" + mở thêm "phù hợp". paint() tô lại theo dlg.tier_on()."""
    def __init__(self, dlg, parent, tiers):
        tk = dlg.app.tk; self.dlg = dlg; self.rows = []
        self.frame = tk.Frame(parent, bg=BG)
        for t in tiers: self.rows.append(self._row(t))

    def _row(self, t):
        tk = self.dlg.app.tk; acc = t["color"]; bg = _mix(acc, CARD, .14)
        c = tk.Frame(self.frame, bg=bg, highlightthickness=1, highlightbackground=_mix(acc, BG, .45), cursor="hand2")
        c.pack(fill="x", pady=(0, 8))
        bar = tk.Frame(c, bg=acc, width=4); bar.pack(side="left", fill="y")
        body = tk.Frame(c, bg=bg); body.pack(side="left", fill="both", expand=True, padx=(10, 10), pady=8)
        top = tk.Frame(body, bg=bg); top.pack(fill="x")
        ic = tk.Label(top, text=t["icon"], font=("Segoe UI", 16), bg=bg, fg=TXT, width=2); ic.pack(side="left", padx=(0, 8))
        mid = tk.Frame(top, bg=bg); mid.pack(side="left", fill="x", expand=True)
        nm = tk.Label(mid, text=t["name"], font=("Segoe UI", 12, "bold"), bg=bg, fg=_mix(acc, "#ffffff", .55), anchor="w"); nm.pack(fill="x")
        wl = [c, bar, body, top, ic, mid, nm]
        if t["vi"]: x = tk.Label(mid, text=t["vi"], font=("Segoe UI", 9), bg=bg, fg=DIM, anchor="w"); x.pack(fill="x"); wl.append(x)
        ands = self.dlg.tier_ands(t); allv = and_list(self.dlg.pr)
        spec = f"{t['cpu']} nhân · {t['ram']}GB RAM · {t['fps']} FPS"
        if len(ands) < len(allv): spec += "   ·   Android " + (" / ".join(ands) if ands else "— vượt trần")
        sp = tk.Label(mid, text=spec, font=("Segoe UI", 9, "bold"), bg=bg, fg=TXT, anchor="w"); sp.pack(fill="x"); wl.append(sp)
        rt = tk.Frame(top, bg=bg); rt.pack(side="right", padx=(8, 0)); wl.append(rt)
        if t["badge"]: b = tk.Label(rt, text=t["badge"], font=("Segoe UI", 8, "bold"), bg="#ff5f6d", fg="white", padx=7); b.pack(anchor="e"); wl.append(b)
        per = per_day(self.dlg.pr, t["ram"], t["cpu"])
        pr = tk.Label(rt, text=vnd(per), font=("Segoe UI", 13, "bold"), bg=bg, fg=TXT, anchor="e"); pr.pack(anchor="e")
        pd = tk.Label(rt, text="/ ngày", font=("Segoe UI", 8), bg=bg, fg=DIM, anchor="e"); pd.pack(anchor="e"); wl += [pr, pd]
        btn = tk.Label(top, text="Chọn", font=("Segoe UI", 9, "bold"), bg=_mix(acc, CARD, .30), fg=TXT, padx=10, pady=5, cursor="hand2")
        btn.pack(side="right", padx=(10, 0)); wl.append(btn)
        more = tk.Frame(body, bg=bg)
        mw = []
        for f in t["fit"]: y = tk.Label(more, text="✓  " + f, font=("Segoe UI", 9), bg=bg, fg=TXT, anchor="w"); y.pack(fill="x"); mw.append(y)
        z = tk.Label(more, text=f"≈ {vnd(per * 30)} / 30 ngày", font=("Segoe UI", 8), bg=bg, fg=DIM, anchor="w"); z.pack(fill="x"); mw.append(z)
        def click(_e, t=t): self.dlg.pick_tier(t)
        for w in wl + [more] + mw: w.bind("<Button-1>", click)
        return t, c, btn, more, ic

    def paint(self):
        for t, c, btn, more, ic in self.rows:
            on = self.dlg.tier_on(t)
            c.config(highlightthickness=2 if on else 1, highlightbackground=t["color"] if on else _mix(t["color"], BG, .45))
            btn.config(text="✓ Đã chọn" if on else "Chọn", bg=t["color"] if on else _mix(t["color"], CARD, .30), fg="#06112b" if on else TXT)
            if on: more.pack(fill="x", padx=(ic.winfo_reqwidth() + 8, 0), pady=(6, 0))
            else: more.pack_forget()




class Dlg:
    """Cửa sổ con (mua / gia hạn / nạp): phần trên cuộn được, phần dưới (tổng tiền + nút) đứng yên."""
    def __init__(self, app, title, w=580, h=700, grow=True):
        tk = app.tk; self.app = app; self.alive = True
        self.win = d = tk.Toplevel(app.root); d.title(title); d.configure(bg=BG)
        if not getattr(app, "tools_only", False): d.transient(app.root)
        app.root.update_idletasks()
        g = max(1.0, getattr(app, "scale", 1.0)) if grow else 1.0     # 16/11: khách chỉnh chữ to → hộp thoại rộng / cao theo (không quá màn hình)
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight(); w = min(int(w * g), max(440, sw - 40)); h = min(int(h * g), sh - 80)
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
        self.mine = tk.Frame(self.frame, bg=parent["bg"])                  # 🎫 mã của tôi dùng được cho loại đơn này — bấm là điền + áp dụng (SQL v35)
        cs = my_codes(scope)
        if cs:
            self.mine.pack(fill="x", pady=(4, 0))
            dlg.label(self.mine, "🎫 Mã của bạn:", dlg.app.f_s, DIM).pack(side="left")
            for c in cs[:4]:
                dlg.app.btn(self.mine, code_label(c), lambda v=str(c.get("code")): self.pick(v), "soft", padx=8, pady=2).pack(side="left", padx=(6, 0))
        self.ent.bind("<KeyRelease>", self._typed); self.ent.bind("<Return>", lambda *_: self.check())

    def pick(self, code):
        self.ent.delete(0, "end"); self.ent.insert(0, code); self.check()

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
        if e == "PROMO_DAY_LIMIT":
            lim = int(num(x.get("limit")) or num((OFFERS["pub"] or {}).get("day_limit")))
            return f"Mỗi tài khoản dùng tối đa {str(lim) + ' ' if lim > 0 else ''}mã giảm giá mỗi ngày — hôm nay bạn đã dùng đủ, mai dùng tiếp nhé."
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
        k = SAID.get(m)
        if k and k.startswith("PROMO_"): self.r, self.key = {"ok": False, "err": k}, self._keynow(); self.paint(); return True
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
def blue_intro_text(i):
    """Cách nhận / dùng Blue theo cấu hình admin đang bật (con số đổi theo admin) — hộp giới thiệu lần đầu của app PC."""
    i = i or {}; c = i.get("cfg") or {}; ln = []
    ck, sb, sd = int(num(c.get("checkin"))), int(num(c.get("streak_bonus"))), int(num(c.get("streak_days")))
    if ck > 0: ln.append(f"📅 Điểm danh mỗi ngày: +{blue_n(ck)} Blue" + (f" (đủ {sd} ngày liền thưởng thêm +{blue_n(sb)})" if sb > 0 and sd > 0 else ""))
    names = {"play": "📱 Mở máy đám mây", "share": "🔗 Chia sẻ link mời", "invite": "👥 Bạn được mời nạp tiền"}
    for t in i.get("tasks") or []:
        if t.get("id") in names and num(t.get("got")) > 0: ln.append(f"{names[t['id']]}: +{blue_n(t.get('got'))} Blue mỗi ngày")
    if num(c.get("ref")) > 0: ln.append(f"🎁 Bạn được mời nạp tiền lần đầu" + (f" (từ {vnd(c.get('ref_min_topup'))})" if num(c.get("ref_min_topup")) > 0 else "") + f": +{blue_n(c.get('ref'))} Blue")
    if num(c.get("cashback")) > 0: ln.append(f"💸 Mỗi đơn trả bằng tiền: hoàn {'%g' % num(c.get('cashback'))}% thành Blue")
    mp = 100 if c.get("max_pct") is None else max(0, min(100, int(num(c.get("max_pct")))))
    out = "\n".join(ln) + "\n\nDùng Blue: bật \"💎 Trả bằng Blue\" khi thuê / gia hạn máy — 1 Blue = 1đ" + (f", tối đa {mp}% mỗi đơn." if mp < 100 else ", trả được cả đơn.")
    if not i.get("can_use") and i.get("need_topup", True): out += "\n🔒 Nạp tiền" + (f" từ {vnd(i.get('use_min_topup'))}" if num(i.get("use_min_topup")) > 0 else " ít nhất 1 lần") + " để mở khoá trả bằng Blue (vẫn tích bình thường)."
    return out + "\n\nXem lại bất cứ lúc nào: bấm nút 💎 trên app."
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
            "invite": ("🤝", "Bạn được mời nạp tiền", "Có bạn đăng ký qua link của bạn và NẠP TIỀN trong hôm nay")}
    KIND = {"checkin": "Điểm danh", "streak": "Thưởng chuỗi", "task": "Nhiệm vụ", "ref": "Mời bạn", "cashback": "Hoàn đơn",
            "spend": "Đã dùng", "refund": "Hoàn lại", "admin": "Admin", "clawback": "Thu lại", "creator": "Kiếm tiền (video)"}

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
        if i.get("hold"):
            self.label(self.body, "🧊 Blue của bạn đang được tạm giữ để kiểm tra (không nhận / không dùng được). Liên hệ hỗ trợ nếu cần.", self.app.f_s, WARN, wraplength=520).pack(fill="x", padx=18, pady=(8, 0))
        elif i.get("new_account"):
            self.label(self.body, f"🆕 Tài khoản mới — sau {int(num(i.get('min_age_h')) or 24)} giờ mới bắt đầu tích Blue được.", self.app.f_s, WARN, wraplength=520).pack(fill="x", padx=18, pady=(8, 0))
        elif not i.get("can_use") and i.get("need_topup"):
            self.label(self.body, "🔒 Nạp tiền" + (f" từ {vnd(i.get('use_min_topup'))}" if num(i.get("use_min_topup")) > 0 else " lần đầu") + " để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.", self.app.f_s, WARN, wraplength=520).pack(fill="x", padx=18, pady=(8, 0))
        if num(i.get("day_cap")) > 0:
            self.label(self.body, f"Hôm nay đã nhận {blue_n(i.get('today_earned'))} / {blue_n(i.get('day_cap'))} Blue (điểm danh + nhiệm vụ)", self.app.f_s, DIM, wraplength=520).pack(fill="x", padx=18, pady=(6, 0))
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
            if tid == "invite" and t.get("ready"): sub = "Bạn bạn mời đã nạp tiền hôm nay 🎉"
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
        if num(cfg.get("ref")) > 0: more.append(f"• Bạn bè bạn mời nạp tiền lần đầu" + (f" từ {vnd(cfg.get('ref_min_topup'))}" if num(cfg.get("ref_min_topup")) > 0 else "") + f" (khác mạng / thiết bị): +{blue_n(cfg.get('ref'))} Blue mỗi bạn")
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
            text = T("Thuê điện thoại Android đám mây chạy 24/7 ở CloudBlue — đăng ký qua link của mình nhé: ") + link
            try: self.win.clipboard_clear(); self.win.clipboard_append(text)
            except Exception: pass
            self.task("share")
            self.app.ui(lambda: self.alive and self.msg.config(text="📋 Đã copy link mời — dán gửi bạn bè / nhóm (Zalo, Facebook, Discord…).", fg=OK))
        self.bg(job, done)


# ================= 🎁 ƯU ĐÃI & 🎬 KIẾM TIỀN (SQL v35) — mọi con số / câu chữ do MÁY CHỦ trả về, app chỉ hiển thị =================
# promo_public() → pub {day_limit, topup{levels[{min,pct}],days,max}, trial{hours,days,need,ram,cpu}, wheel, creator{rate,per,video_max,month_max,
#                       day_submit,platforms,blue_min}, blue, ticker[{k,vi,en}]}
# promo_my()     → my  {day_limit, day_used, topup_got, codes[{code,pct,amount,expires_at,scopes,usable,used,share,src}], trial{on,hours,need,ok,used}}
# Máy chủ chưa chạy SQL v35 → pub = None → app ẩn hết, chạy như cũ.
OFFERS = {"pub": None, "my": None, "t": 0.0}
SRC_NAME = {"wheel": "🎡 Vòng quay", "topup": "💰 Ưu đãi nạp", "gift": "🎁 Quà tặng"}
PLATFORM = {"tiktok": "TikTok", "youtube": "YouTube", "facebook": "Facebook", "instagram": "Instagram", "other": "nền tảng khác"}
def offers_load(auth):
    """Đọc promo_public + promo_my (gọi ở luồng nền). Chưa chạy SQL v35 → None (ẩn mọi thứ); mất mạng / máy chủ lỗi tạm → giữ bản cũ."""
    def soft(e): return e.code == 0 or e.code >= 500
    try: p = auth.rpc("promo_public")
    except ApiError as e:
        if e.code == 401: raise
        if soft(e): OFFERS["t"] = time.time(); return OFFERS
        p = None
    except Exception: p = None
    m = None
    if isinstance(p, dict):
        try: m = auth.rpc("promo_my")
        except ApiError as e:
            if e.code == 401: raise
            m = OFFERS["my"] if soft(e) else None
        except Exception: m = None
    OFFERS.update(pub=p if isinstance(p, dict) else None, my=m if isinstance(m, dict) else None, t=time.time())
    return OFFERS
def offers_fresh(auth, age=30.0):
    if time.time() - OFFERS["t"] > age: offers_load(auth)
    return OFFERS
def offers_sec(k):
    v = (OFFERS["pub"] or {}).get(k); return v if isinstance(v, dict) else None
def offers_topup():
    t = offers_sec("topup"); return t if t and t.get("levels") else None
def offers_text(o):
    o = o or {}
    return str((o.get("en") if EN_UI else None) or o.get("vi") or "")
def trial_hours(pr): return max(0, int(num((pr or {}).get("free_hours"))))
def trial_need(pr): return max(0, int(num((pr or {}).get("free_need_topup"))))
def trial_dur(pr):
    h = trial_hours(pr); return f"{h} giờ" if h > 0 else f"{int(num((pr or {}).get('free_days'))) or 1} ngày"
def trial_my():
    t = (OFFERS["my"] or {}).get("trial"); return t if isinstance(t, dict) else None
def trial_err(pr, admin=False):
    """"" = nhận được · không thì lý do. Chưa có SQL v35 / chưa tải xong → "" (máy chủ tự kiểm khi đặt)."""
    t = trial_my()
    if admin or not t: return ""
    if t.get("used"): return "Mỗi tài khoản chỉ được dùng thử 1 máy miễn phí — bạn đã nhận rồi."
    if not t.get("ok") and trial_need(pr) > 0: return f"Dùng thử miễn phí dành cho tài khoản đã nạp 1 lần từ {vnd(trial_need(pr))}."
    return ""
def trial_locked(pr, admin=False):
    t = trial_my(); return bool(not admin and t and not t.get("used") and not t.get("ok") and trial_need(pr) > 0)
def my_codes(scope=None):
    cs = (OFFERS["my"] or {}).get("codes") or []
    return [c for c in cs if isinstance(c, dict) and c.get("usable") and (scope is None or scope in (c.get("scopes") or []))][:6]
def code_label(c):
    return f"{c.get('code')}  −" + (f"{int(num(c.get('pct')))}%" if num(c.get("pct")) > 0 else vnd(c.get("amount")))
def offers_hint(dlg):
    """Dòng '🎁 Lần nạp này được tặng mã giảm N%' / '📱 Mở dùng thử…' dưới ô số tiền (hộp Nạp tiền)."""
    l = getattr(dlg, "oh", None)
    try:
        if l is None or not l.winfo_exists(): return
    except Exception: return
    amt = getattr(dlg, "amt", 0); out = []; tc = offers_topup(); my = OFFERS["my"] or {}
    if tc and not my.get("topup_got"):
        best = max([int(num(x.get("pct"))) for x in tc["levels"] if isinstance(x, dict) and amt >= num(x.get("min"))] or [0])
        if best > 0: out.append(f"🎁 Lần nạp này được tặng mã giảm {best}% cloud phone")
    tr = offers_sec("trial"); t = trial_my()
    if tr and t and not t.get("used") and not t.get("ok") and num(tr.get("need")) > 0 and amt >= num(tr.get("need")):
        out.append(f"📱 Mở dùng thử 1 cloud phone {int(num(tr.get('hours')))} giờ miễn phí" if num(tr.get("hours")) > 0 else "📱 Mở dùng thử 1 cloud phone miễn phí")
    l.config(text="\n".join(out))
    if out and not l.winfo_manager(): l.pack(fill="x", pady=(6, 0))
    elif not out and l.winfo_manager(): l.pack_forget()

def offers_after_top(dlg, amt):
    """Nạp xong (hộp Nạp tiền): đọc lại ưu đãi của tôi → báo mã vừa được tặng / lượt dùng thử vừa mở. Máy chủ quyết định, app chỉ hiện."""
    old = OFFERS["my"]; app = dlg.app
    if old is None: OFFERS["t"] = 0; return                       # chưa từng tải (chưa chạy SQL v35) → không đoán
    had = {str(c.get("code")) for c in (old.get("codes") or []) if isinstance(c, dict)}; was_ok = bool((old.get("trial") or {}).get("ok"))
    def show(_r):
        my = OFFERS["my"] or {}; t = my.get("trial") or {}; tk = app.tk
        new = [c for c in (my.get("codes") or []) if isinstance(c, dict) and c.get("usable") and c.get("src") == "topup" and str(c.get("code")) not in had]
        opened = bool(t.get("on") and t.get("ok") and not t.get("used") and not was_ok)
        try:
            bb = dlg.done_btn.master
            if new:
                dlg.label(dlg.foot, f"🎁 Bạn được tặng mã giảm giá cloud phone:  {code_label(new[0])}  — mã nằm ở 🎁 Ưu đãi, bấm chọn khi thuê / gia hạn máy.",
                          ("Segoe UI", 9, "bold"), OK, wraplength=540).pack(fill="x", padx=16, pady=(4, 0), before=bb)
            if opened:
                h = int(num(t.get("hours")))
                dlg.label(dlg.foot, f"📱 Đã mở dùng thử 1 cloud phone {str(h) + ' giờ ' if h > 0 else ''}miễn phí.", ("Segoe UI", 9, "bold"), OK, wraplength=540).pack(
                    fill="x", padx=16, pady=(4, 0), before=bb)
                app.btn(bb, "📱 Nhận máy dùng thử", lambda: (dlg.close(), OrderDlg(app, True)), "soft").pack(side="right", padx=(0, 8))
        except Exception: log("offers:", traceback.format_exc())
        try: app._paint_offers()
        except Exception: pass
    dlg.bg(lambda: offers_load(app.auth), show)


class Ticker:
    """📣 Dòng chữ chạy ưu đãi trên cùng màn danh sách máy (bấm → hộp Ưu đãi). Chữ trôi sang trái ~40 px / giây, nối vòng liên tục."""
    GAP = "      •      "
    def __init__(self, app, holder):
        tk = app.tk; self.app = app; self.text = ""; self.x = 0.0; self.w = 1; self.job = None
        self.cv = tk.Canvas(holder, height=26, bg="#2e2206", highlightthickness=0, cursor="hand2")
        self.cv.bind("<Button-1>", lambda e: OffersDlg(app))

    def set(self, items):
        t = self.GAP.join(x for x in items if x)
        if t == self.text: return
        self.text = t
        if not t:
            self.stop()
            try: self.cv.pack_forget()
            except Exception: pass
            return
        import tkinter.font as tkfont
        f = tkfont.Font(family="Segoe UI", size=10, weight="bold"); unit = t + self.GAP
        self.w = max(1, f.measure(unit)); self.cv.delete("all")
        self.cv.create_text(0, 13, text=unit * (2 + int(2600 / self.w)), anchor="w", fill="#ffe296", font=f, tags="t")      # lặp đủ dài để phủ kín cửa sổ rộng
        self.x = 0.0
        if not self.cv.winfo_manager(): self.cv.pack(fill="x")
        if self.job is None: self._step()

    def _step(self):
        self.job = None
        try:
            if not self.text or not self.cv.winfo_exists(): return
            self.x -= 1.2
            if self.x <= -self.w: self.x += self.w
            self.cv.coords("t", self.x, 13)
            self.job = self.cv.after(30, self._step)
        except Exception: self.job = None

    def stop(self):
        if self.job is not None:
            try: self.cv.after_cancel(self.job)
            except Exception: pass
            self.job = None


class OffersDlg(Dlg):
    """🎁 Ưu đãi: mã của tôi · ưu đãi khi nạp · dùng thử · vòng quay · Kiếm tiền · Blue (giống hộp Ưu đãi trên web)."""
    def __init__(self, app):
        super().__init__(app, "Ưu đãi", 600, 720)
        self.draw()
        self.bg(lambda: offers_load(app.auth), lambda _r: self.draw())

    def card(self, title):
        tk = self.app.tk
        c = tk.Frame(self.body, bg=CARD, highlightbackground=LINE, highlightthickness=1); c.pack(fill="x", padx=18, pady=(10, 0))
        self.label(c, title, ("Segoe UI", 11, "bold"), TXT).pack(fill="x", padx=12, pady=(10, 2))
        return c

    def copy(self, v, lbl):
        try: self.app.root.clipboard_clear(); self.app.root.clipboard_append(v)
        except Exception: pass
        try: lbl.config(text=f"✓ Đã chép mã {v}", fg=OK)
        except Exception: pass

    def codes(self):
        tk = self.app.tk; my = OFFERS["my"]
        if my is None: return
        cs = [c for c in (my.get("codes") or []) if isinstance(c, dict)]
        c = self.card("🎫 Mã của tôi")
        msg = self.label(c, "Chỉ dùng cho cloud phone: nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn / nâng cấp máy — hoặc bấm chọn mã ngay dưới ô đó.",
                         self.app.f_s, DIM, wraplength=530)
        if not cs: self.label(c, "Chưa có mã nào. Mã từ ưu đãi nạp, vòng quay, quà tặng sẽ nằm ở đây.", self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12, pady=(0, 10)); return
        now = now_utc()
        for x in cs[:12]:
            ok = bool(x.get("usable")); exp = parse_iso(x.get("expires_at"))
            st = ("Đã dùng" if x.get("used") else "Dùng được đến " + (exp.astimezone().strftime("%H:%M %d/%m") if exp else "") if ok
                  else "Hết hạn" if exp is not None and exp <= now else "Đã tắt")
            r = tk.Frame(c, bg=BG, highlightbackground=LINE, highlightthickness=1); r.pack(fill="x", padx=12, pady=2)
            tk.Label(r, text=f"{int(num(x.get('pct')))}%" if num(x.get("pct")) > 0 else vnd(x.get("amount")), font=("Segoe UI", 10, "bold"), fg=OK if ok else DIM, bg=BG, width=6).pack(side="left", padx=6, pady=6)
            if ok: self.app.btn(r, "Chép", lambda v=str(x.get("code")): self.copy(v, msg), "soft", padx=10, pady=2).pack(side="right", padx=8)
            tx = tk.Frame(r, bg=BG); tx.pack(side="left", fill="x", expand=True)
            tk.Label(tx, text=str(x.get("code")), font=("Consolas", 10, "bold"), fg=TXT if ok else DIM, bg=BG, anchor="w").pack(fill="x")
            tk.Label(tx, text=SRC_NAME.get(x.get("src"), "🎁 Mã giảm giá") + " · " + st + (" · 🤝 tặng bạn bè được" if ok and x.get("share") else ""),
                     font=("Segoe UI", 8), fg=DIM, bg=BG, anchor="w").pack(fill="x")
        msg.pack(fill="x", padx=12, pady=(4, 10))

    def draw(self):
        if not self.alive: return
        tk = self.app.tk; app = self.app; self.clear()
        pub = OFFERS["pub"]; my = OFFERS["my"] or {}
        self.app.btn(self.foot, "Đóng", self.close, "soft").pack(side="right", padx=16, pady=10)
        if not pub:
            self.label(self.body, "Hiện chưa có ưu đãi nào.", self.app.f_t, DIM).pack(padx=18, pady=30); return
        top = bool(my_codes())
        if top: self.codes()
        tc = offers_topup()
        if tc:
            c = self.card("💰 Ưu đãi khi nạp")
            for x in tc["levels"]:
                if isinstance(x, dict): self.label(c, f"Nạp 1 lần từ {vnd(x.get('min'))}  →  mã giảm {int(num(x.get('pct')))}%", ("Segoe UI", 10, "bold"), OK).pack(fill="x", padx=12)
            self.label(c, f"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp đó), dùng 1 lần, hạn {int(num(tc.get('days')) or 7)} ngày"
                          + (f", giảm tối đa {vnd(tc.get('max'))}" if num(tc.get("max")) > 0 else "") + ". Chỉ dùng cho cloud phone: thuê, gia hạn, nâng cấp máy.",
                       self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12, pady=(4, 0))
            app.btn(c, "Nạp tiền", lambda: (self.close(), app.open_topup()), padx=12, pady=5).pack(anchor="w", padx=12, pady=(8, 10))
        tr = offers_sec("trial")
        if tr:
            h = int(num(tr.get("hours"))); need = int(num(tr.get("need"))); t = trial_my() or {}
            c = self.card(f"📱 Dùng thử cloud phone {str(h) + ' giờ' if h > 0 else str(int(num(tr.get('days')) or 1)) + ' ngày'} miễn phí")
            self.label(c, (f"Dành cho tài khoản đã nạp 1 lần từ {vnd(need)}. " if need > 0 else "") + f"Mỗi tài khoản 1 máy (tối đa {int(num(tr.get('ram')))}GB RAM · {int(num(tr.get('cpu')))} nhân). "
                          "Hết giờ, máy và dữ liệu tự xoá — muốn dùng tiếp thì thuê máy.", self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12)
            if t.get("used"): self.label(c, "✓ Bạn đã dùng thử rồi.", self.app.f_s, DIM).pack(fill="x", padx=12, pady=(6, 10))
            elif t and not t.get("ok") and need > 0: app.btn(c, f"Nạp {vnd(need)}", lambda: (self.close(), app.open_topup(need)), padx=12, pady=5).pack(anchor="w", padx=12, pady=(8, 10))
            else: app.btn(c, "Nhận máy dùng thử", lambda: (self.close(), OrderDlg(app, True)), padx=12, pady=5).pack(anchor="w", padx=12, pady=(8, 10))
        wh = offers_sec("wheel")
        if wh and wheel_live(WHEEL["st"]):
            c = self.card("🎡 Vòng quay may mắn")
            self.label(c, offers_text(wh), self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12)
            app.btn(c, "Mở vòng quay", lambda: (self.close(), wheel_open(app)), "soft", padx=12, pady=5).pack(anchor="w", padx=12, pady=(8, 10))
        cr = offers_sec("creator")
        if cr:
            c = self.card("🎬 Kiếm tiền")
            self.label(c, f"Làm video về CloudBlue: {blue_n(cr.get('per'))} view = {blue_n(cr.get('rate'))} 💎 Blue. View tăng thì nhận thêm.", self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12)
            app.btn(c, "Xem cách làm", lambda: (self.close(), CreatorDlg(app)), "soft", padx=12, pady=5).pack(anchor="w", padx=12, pady=(8, 10))
        bl = offers_sec("blue")
        if bl and blue_on():
            c = self.card("💎 Blue"); self.label(c, offers_text(bl), self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12, pady=(0, 10))
        dl = int(num(pub.get("day_limit")))
        if dl > 0:
            self.label(self.body, f"🎟 Mỗi tài khoản dùng tối đa {dl} mã giảm giá mỗi ngày." + (f"  Hôm nay: {int(num(my.get('day_used')))}/{dl}" if OFFERS["my"] is not None else ""),
                       self.app.f_s, DIM, wraplength=540).pack(fill="x", padx=18, pady=(10, 0))
        if not top: self.codes()
        tk.Frame(self.body, bg=BG, height=14).pack()


class CreatorDlg(Dlg):
    """🎬 Kiếm tiền: luật + gửi link video + danh sách video của tôi (báo view mới). creator_my / creator_submit / creator_report."""
    def __init__(self, app):
        super().__init__(app, "Kiếm tiền", 620, 780)
        self.data = None
        self.draw()
        self.reload()

    def reload(self):
        def ok(r): self.data = r if isinstance(r, dict) else {}; self.fill()
        def fail(m):
            self.data = self.data or {}; self.fill()
            if hasattr(self, "err"): self.err.config(text=m, fg=BAD)
        self.bg(lambda: self.app.auth.rpc("creator_my"), ok, fail)

    def draw(self):
        tk = self.app.tk; app = self.app; self.clear()
        cr = offers_sec("creator")
        app.btn(self.foot, "Đóng", self.close, "soft").pack(side="right", padx=16, pady=10)
        if not cr:
            self.label(self.body, "Chương trình Kiếm tiền đang tạm tắt.", app.f_t, DIM).pack(padx=18, pady=30); return
        hero = tk.Frame(self.body, bg=CARD, highlightbackground=OK, highlightthickness=1); hero.pack(fill="x", padx=18, pady=(14, 0))
        self.label(hero, f"{blue_n(cr.get('per'))} view = {blue_n(cr.get('rate'))} 💎", ("Segoe UI", 18, "bold"), OK).pack(fill="x", padx=14, pady=(10, 0))
        self.label(hero, "1 💎 Blue = 1đ khi thuê / gia hạn cloud phone", app.f_s, DIM).pack(fill="x", padx=14)
        self.sum = self.label(hero, "", ("Segoe UI", 9, "bold"), TXT); self.sum.pack(fill="x", padx=14, pady=(4, 10))
        pl = [str(x) for x in (cr.get("platforms") or [])]
        pf = ", ".join(PLATFORM.get(x, x) for x in pl if x != "other") + (" và nền tảng khác" if "other" in pl else "")
        caps = " · ".join(x for x in (f"Tối đa {blue_n(cr.get('video_max'))} 💎 / video" if num(cr.get("video_max")) > 0 else "",
                                      f"{blue_n(cr.get('month_max'))} 💎 / tháng" if num(cr.get("month_max")) > 0 else "",
                                      f"gửi tối đa {int(num(cr.get('day_submit')))} video / ngày" if num(cr.get("day_submit")) > 0 else "") if x)
        f = self.section("Cách làm")
        for t in ("1. Quay video giới thiệu CloudBlue — ví dụ treo game 24/7 trên cloud phone, cách thuê máy, so sánh giá.",
                  f"2. Đăng công khai lên {pf}. Nói hoặc ghi rõ tên web {WEB.split('//')[-1]}.",
                  "3. Dán link video vào ô bên dưới. Admin mở video kiểm tra rồi cộng 💎 theo số view.",
                  "4. View tăng thì bấm “Báo view mới” — mỗi lần duyệt cộng thêm 💎 cho phần view mới."):
            self.label(f, t, app.f_t, TXT, wraplength=540).pack(fill="x", pady=1)
        for t in ("• " + caps[:1].upper() + caps[1:] if caps else "",
                  "• Video của chính bạn, để công khai. Không mua view, không đăng lại video người khác — vi phạm bị từ chối.",
                  "• 💎 Blue chỉ dùng cho cloud phone (thuê / gia hạn), 1 💎 = 1đ" + (f", dùng được khi tài khoản đã nạp từ {vnd(cr.get('blue_min'))}" if num(cr.get("blue_min")) > 0 else "")
                  + ". Không dùng cho sản phẩm khác."):
            if t: self.label(f, t, app.f_s, DIM, wraplength=540).pack(fill="x", pady=1)
        f = self.section("Gửi video")
        self.url = tk.Entry(f, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat"); self.url.pack(fill="x", ipady=5)
        self.label(f, "Link video (TikTok, YouTube…) — dán link đầy đủ bắt đầu bằng https://", app.f_s, DIM).pack(fill="x")
        line = tk.Frame(f, bg=BG); line.pack(fill="x", pady=(6, 0))
        self.label(line, "Số view hiện tại:", app.f_s, DIM).pack(side="left")
        self.views = tk.Entry(line, width=10, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat"); self.views.pack(side="left", padx=6, ipady=4)
        self.label(line, "Ghi chú:", app.f_s, DIM).pack(side="left", padx=(8, 0))
        self.note = tk.Entry(line, font=("Segoe UI", 11), bg=CARD, fg=TXT, insertbackground=TXT, relief="flat"); self.note.pack(side="left", fill="x", expand=True, padx=6, ipady=4)
        self.err = self.label(f, "", app.f_s, BAD, wraplength=540); self.err.pack(fill="x", pady=(4, 0))
        self.send = app.btn(f, "Gửi video", self.submit); self.send.pack(anchor="w", pady=(4, 0))
        self.list_f = self.section("Video của bạn")
        self.fill()
        tk.Frame(self.body, bg=BG, height=14).pack()

    def fill(self):
        if not self.alive or not hasattr(self, "list_f"): return
        tk = self.app.tk; app = self.app; f = self.list_f
        for w in f.winfo_children()[1:]: w.destroy()                 # giữ dòng tiêu đề của mục
        o = self.data
        if o is None: self.label(f, "Đang tải…", app.f_s, DIM).pack(fill="x"); return
        self.sum.config(text=f"Đã nhận {blue_n(o.get('total'))} 💎   ·   tháng này {blue_n(o.get('month'))} 💎   ·   chờ duyệt {int(num(o.get('pending')))}")
        vs = [v for v in (o.get("videos") or []) if isinstance(v, dict)]
        if not vs: self.label(f, "Bạn chưa gửi video nào.", app.f_s, DIM).pack(fill="x"); return
        for v in vs:
            st = v.get("status"); r = tk.Frame(f, bg=CARD, highlightbackground=LINE, highlightthickness=1); r.pack(fill="x", pady=3)
            hd = tk.Frame(r, bg=CARD); hd.pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(hd, text=PLATFORM.get(str(v.get("platform")), str(v.get("platform") or "")), font=("Segoe UI", 9, "bold"), fg=ACC, bg=CARD).pack(side="left")
            tk.Label(hd, text="Đã duyệt" if st == "ok" else "Từ chối" if st == "rejected" else "Chờ duyệt", font=("Segoe UI", 9, "bold"),
                     fg=OK if st == "ok" else BAD if st == "rejected" else WARN, bg=CARD).pack(side="right")
            u = str(v.get("url") or "")
            self.label(r, u if len(u) <= 76 else u[:50] + "…" + u[-22:], app.f_s, DIM).pack(fill="x", padx=10)
            self.label(r, f"Đã duyệt {blue_n(v.get('views'))} view  ·  đã nhận {blue_n(v.get('paid'))} 💎" + (f"  ·  bạn báo {blue_n(v.get('claimed'))} view" if v.get("claimed") is not None and st == "pending" else ""),
                       app.f_t, TXT).pack(fill="x", padx=10)
            if v.get("admin_note"): self.label(r, "💬 " + str(v.get("admin_note")), app.f_s, BAD if st == "rejected" else DIM, wraplength=520).pack(fill="x", padx=10)
            if st == "ok":
                ln = tk.Frame(r, bg=CARD); ln.pack(fill="x", padx=10, pady=(4, 0))
                e = tk.Entry(ln, width=12, font=("Segoe UI", 10), bg=BG, fg=TXT, insertbackground=TXT, relief="flat"); e.pack(side="left", ipady=3)
                app.btn(ln, "Báo view mới", lambda vid=v.get("id"), ent=e: self.report(vid, ent), "soft", padx=10, pady=2).pack(side="left", padx=8)
            tk.Frame(r, bg=CARD, height=8).pack()

    def submit(self):
        u = self.url.get().strip(); vw = re.sub(r"\D", "", self.views.get()); nt = self.note.get().strip()
        if not re.match(r"(?i)^https://[^\s/]+\.[^\s/]+/.+", u):
            self.err.config(text="Link video không đúng — dán link đầy đủ bắt đầu bằng https://", fg=BAD); return
        self.err.config(text=""); self.send.config(state="disabled", text="Đang gửi…")
        def done(_r):
            self.send.config(state="normal", text="Gửi video")
            for e in (self.url, self.views, self.note): e.delete(0, "end")
            self.err.config(text="✓ Đã gửi — admin duyệt xong sẽ cộng 💎 vào tài khoản.", fg=OK); self.reload()
        def fail(m): self.send.config(state="normal", text="Gửi video"); self.err.config(text=m, fg=BAD)
        self.bg(lambda: self.app.auth.rpc("creator_submit", {"p_url": u, "p_views": int(vw) if vw and len(vw) <= 11 else None, "p_note": nt or None}), done, fail)

    def report(self, vid, ent):
        vw = re.sub(r"\D", "", ent.get())
        if not vw or len(vw) > 11: self.err.config(text="Nhập số view đang hiện trên video.", fg=BAD); return
        def done(_r): self.err.config(text="✓ Đã báo — admin duyệt xong sẽ cộng 💎 cho phần view mới.", fg=OK); self.reload()
        self.bg(lambda: self.app.auth.rpc("creator_report", {"p_id": vid, "p_views": int(vw)}), done, lambda m: self.err.config(text=m, fg=BAD))


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
    def __init__(self, app, free=False):
        super().__init__(app, "Thuê điện thoại đám mây", 620, 800)
        self.want_free = bool(free)                                         # mở từ nút "Nhận máy dùng thử" → bật sẵn chế độ dùng thử
        self.loading("Đang tải bảng giá…")
        def load():
            sh = app.shop
            try: site = sh.site()
            except Exception: site = {}
            try: offers_fresh(app.auth)                                     # 🎁 lượt dùng thử + mã của tôi (SQL v35)
            except Exception: pass
            return sh.pricing(), sh.status(), sh.profile(), sh.live_count(), site
        self.bg(load, self._loaded, lambda m: self.loading(m))

    def _loaded(self, r):
        self.pr, self.st, self.prof, have, self.site = r
        self.custom = False                                                 # ⚙️ Tự chỉnh cấu hình đang mở
        self.picked = False                                                 # khách ĐÃ bấm 1 gói / tự chỉnh — chưa thì chưa hiện tiền
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
        if self.want_free and free_live(p): self.set_free(True)
        else: self.build()

    # ---------- vẽ ----------
    def need(self):
        """Còn gói mà khách CHƯA chọn → chưa hiện số tiền nào (giống web + app điện thoại)."""
        return not self.s["free"] and not getattr(self, "picked", False) and bool(getattr(self, "tl", []))

    def step(self, n, title, sub=""):
        """Đầu mỗi bước: số tròn xanh + tiêu đề to + 1 dòng gợi ý."""
        tk = self.app.tk
        f = tk.Frame(self.body, bg=BG); f.pack(fill="x", padx=18, pady=(16, 6))
        hr = tk.Frame(f, bg=BG); hr.pack(fill="x")
        cv = tk.Canvas(hr, width=28, height=28, bg=BG, highlightthickness=0); cv.pack(side="left", padx=(0, 10))
        cv.create_oval(2, 2, 26, 26, fill=ACC, outline="#9fd0ff", width=1); cv.create_text(14, 14, text=str(n), fill="white", font=("Segoe UI", 11, "bold"))
        tx = tk.Frame(hr, bg=BG); tx.pack(side="left", fill="x", expand=True)
        self.label(tx, title, ("Segoe UI", 12, "bold"), TXT).pack(fill="x")
        if sub: self.label(tx, sub, self.app.f_s, DIM, wraplength=500).pack(fill="x")
        return f

    def build(self):
        tk = self.app.tk; p, s = self.pr, self.s; self.clear(); self.rows = []
        lo = lambda k: int(num(p.get(k)))
        if self.prof.get("role") == "admin" and (self.st.get("maint") or self.st.get("online") is False):
            self.label(self.body, "⚠ Đang bật BẢO TRÌ — khách không thuê được. Tài khoản admin vẫn thuê được (không giới hạn chỗ trống) để thử máy.",
                       ("Segoe UI", 10, "bold"), WARN, wraplength=540).pack(fill="x", padx=18, pady=(14, 0))
        if free_live(p):
            fb = tk.Frame(self.body, bg=CARD, highlightbackground=WARN if s["free"] else LINE, highlightthickness=1); fb.pack(fill="x", padx=18, pady=(14, 0))
            v = tk.BooleanVar(value=s["free"])
            tk.Checkbutton(fb, text=f"  ★ Dùng thử MIỄN PHÍ {trial_dur(p)}", variable=v, command=lambda: self.set_free(v.get()),
                           font=("Segoe UI", 11, "bold"), fg=TXT, bg=CARD, selectcolor=BG, activebackground=CARD, activeforeground=TXT,
                           anchor="w", cursor="hand2").pack(fill="x", padx=10, pady=(8, 0))
            self.label(fb, f"Tối đa {lo('free_max_ram')}GB RAM · {lo('free_max_cpu')} nhân · mỗi tài khoản 1 máy"
                           + (f" · dành cho tài khoản đã nạp 1 lần từ {vnd(trial_need(p))}" if trial_need(p) > 0 else "")
                           + f". Hết {trial_dur(p)} (tính từ lúc máy chạy) máy và dữ liệu tự xoá, không gia hạn được — muốn dùng tiếp thì thuê máy.",
                       self.app.f_s, DIM, wraplength=520).pack(fill="x", padx=12, pady=(0, 8))
            if trial_locked(p, self.prof.get("role") == "admin"):          # chưa nạp đủ → nói rõ + nút nạp đúng số tiền
                lk = tk.Frame(fb, bg=CARD); lk.pack(fill="x", padx=12, pady=(0, 8))
                self.app.btn(lk, f"Nạp {vnd(trial_need(p))}", lambda: (self.close(), self.app.open_topup(trial_need(p))), "soft", padx=10, pady=3).pack(side="right")
                self.label(lk, f"🔒 Nạp 1 lần từ {vnd(trial_need(p))} để mở dùng thử miễn phí.", ("Segoe UI", 9, "bold"), WARN).pack(side="left")
        def chp(key):                                        # tự chỉnh RAM / CPU / độ phân giải / FPS = đã chọn cấu hình
            def setv(v):
                self.s[key] = v
                if not self.picked:
                    self.picked = True; self.app.root.after_idle(lambda: self.alive and self.build())
            return setv
        get = lambda key: (lambda: self.s[key])
        avs = and_list(p)
        self.tl = [] if s["free"] else tiers_list(getattr(self, "site", {}))
        need = self.need()
        # ① Hệ điều hành — ô to
        f = self.step(1, "Chọn hệ điều hành", "Chưa chắc thì chọn Android 9 — ổn định, chạy được nhiều app nhất." if len(avs) > 1 and "9" in avs else "")
        self.rows.append(AndTiles(self.app, f, [(v, AND_HINT.get(v, "").split(" · ")[0]) for v in avs], get("android"), self.set_android, self.upd,
                                  why=lambda v: and_why(self.st, v, *self.fit(v)) if self.prof.get("role") != "admin" else ""))
        self.rows[-1].frame.pack(fill="x", pady=(4, 0))
        self.and_note = self.label(f, "", self.app.f_s, DIM); self.and_note.pack(fill="x")
        if "15" in avs:
            self.label(f, "💡 Android 15 không vào được Google / Play Store? Chọn Android 12 — máy đang thuê thì dùng Khác ▾ → Đổi Android (giữ nguyên hạn).",
                       self.app.f_s, WARN, wraplength=540).pack(fill="x", pady=(4, 0))
        # ② Chọn gói (cùng danh sách với web) — máy miễn phí / không có gói: tự chỉnh cấu hình
        if self.tl:
            f = self.step(2, "Chọn gói", "Bấm 1 gói để xem giá — muốn khác thì mở ⚙️ Tự chỉnh ở dưới.")
            self.rows.append(TierList(self, f, self.tl)); self.rows[-1].frame.pack(fill="x", pady=(4, 0))
            self.tier_note = self.label(f, getattr(self, "_tier_msg", ""), self.app.f_s, WARN, wraplength=540); self.tier_note.pack(fill="x")
            self._tier_msg = ""
        else:
            self.step(2, ("Cấu hình máy dùng thử" if trial_hours(p) else "Cấu hình máy miễn phí") if s["free"] else "Cấu hình máy",
                      f"Tối đa {lo('free_max_ram')}GB RAM · {lo('free_max_cpu')} nhân — để mặc định là dùng được." if s["free"] else "Chọn RAM · CPU · FPS cho máy.")
        self.cust_lbl = None
        if self.tl:
            if self.picked and not any(self.tier_match(t) for t in self.tl): self.custom = True
            tg = tk.Frame(self.body, bg=CARD, highlightbackground=LINE, highlightthickness=1, cursor="hand2"); tg.pack(fill="x", padx=18, pady=(2, 2))
            self.cust_lbl = self.label(tg, "", ("Segoe UI", 10, "bold"), TXT, cursor="hand2"); self.cust_lbl.pack(side="left", padx=10, pady=8)
            arw = self.label(tg, "▴" if self.custom else "▾", ("Segoe UI", 11, "bold"), DIM, cursor="hand2"); arw.pack(side="right", padx=10)
            for w in (tg, self.cust_lbl, arw): w.bind("<Button-1>", lambda _e: self.toggle_custom())
        if not self.tl or self.custom:
            ar, ac = and_lim(p, s["android"])                                   # trần theo bản Android đang chọn (Android 9: 8GB · 8 nhân · Android 12 / 15: 16GB · 32 nhân)
            mr = min(ar, lo("free_max_ram") or 999) if s["free"] else ar
            mc = min(ac, lo("free_max_cpu") or 999) if s["free"] else ac
            f = self.section("RAM", f"{lo('min_ram')}–{mr} GB")
            self.rows.append(Chips(self.app, f, [(v, f"{v}GB") for v in cp_opts(CP_RAM, lo("min_ram"), mr)], get("ram"), chp("ram"), self.upd, wrap=8)); self.rows[-1].frame.pack(fill="x")
            f = self.section("CPU (nhân)", f"{lo('min_cpu')}–{mc} nhân")
            self.rows.append(Chips(self.app, f, [(v, str(v)) for v in cp_opts(CP_CPU, lo("min_cpu"), mc)], get("cpu"), chp("cpu"), self.upd, wrap=9)); self.rows[-1].frame.pack(fill="x")
            self.label(f, "💡 Treo game 1 tab: nên chọn từ 4GB RAM · 4 nhân (vào trận game đã dùng khoảng 2GB RAM) — 3GB · 2 nhân dễ giật. "
                          "Treo 2–4 tab: 8GB · 8 nhân.", self.app.f_s, DIM, wraplength=520).pack(fill="x", pady=(4, 0))
            f = self.section("Độ phân giải")
            self.rows.append(Chips(self.app, f, [(r, f"{n}\n{r}") for r, n in CP_RES], get("res"), chp("res"), self.upd)); self.rows[-1].frame.pack(fill="x")
            f = self.section("FPS (khung hình / giây)")
            self.rows.append(Chips(self.app, f, [(v, f"{v} FPS") for v in CP_FPS if lo("min_fps") <= v <= lo("max_fps")], get("fps"), chp("fps"), self.upd)); self.rows[-1].frame.pack(fill="x")
        # ③ Số ngày & số máy (máy miễn phí: số ngày cố định, 1 máy → bỏ bước này)
        if not s["free"]:
            self.step(3, "Số ngày & số máy" if self.left > 1 else "Số ngày thuê")
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
            if self.left > 1:
                f = self.section("Số lượng máy")
                self.rows.append(Chips(self.app, f, [(v, f"{v} máy") for v in CP_QTY if v <= min(20, self.left)], get("qty"),
                                       lambda v: self.s.__setitem__("qty", v), self.upd)); self.rows[-1].frame.pack(fill="x")
        self.promo = self.bpay = None
        if not s["free"] and not need:                       # 🏷️ mã giảm giá + 💎 trả bằng Blue (máy miễn phí / chưa chọn gói: ẩn)
            f = self.section("Mã giảm giá · Blue")
            self.promo = PromoBox(self, f, "cp_new", lambda: None if self.s["free"] else {"p_ram": self.s["ram"], "p_cpu": self.s["cpu"],
                                                                                      "p_days": self.s["days"], "p_qty": self.s["qty"]}, self.upd)
            self.promo.frame.pack(fill="x")
            if getattr(self, "_promo_code", ""): self.promo.ent.insert(0, self._promo_code); self.promo.check()
            self.bpay = BluePay(self, f, self.upd, getattr(self, "_blue_on", False))
        note = (p.get("order_note") or "").strip() or ("Máy mới tinh, không dính dữ liệu hay tài khoản Gmail của ai. Hết hạn máy tạm dừng — "
                                                       "gia hạn trong 30 phút, quá thời gian máy và dữ liệu bị xoá.")
        self.label(self.body, note, self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=18, pady=(14, 18))
        # ---- chân: gói đang chọn + tổng tiền + nút ----
        ft = self.foot
        self.pick_lbl = self.label(ft, "", ("Segoe UI", 10, "bold"), TXT); self.pick_lbl.pack(fill="x", padx=16, pady=(10, 0))
        self.calc = self.label(ft, "", self.app.f_s, DIM); self.calc.pack(fill="x", padx=16)
        r = tk.Frame(ft, bg=CARD); r.pack(fill="x", padx=16)
        self.total = self.label(r, "", ("Segoe UI", 18, "bold"), TXT); self.total.pack(side="left")
        self.bal = self.label(r, "", self.app.f_t, DIM); self.bal.pack(side="right")
        self.err = self.label(ft, "", self.app.f_s, BAD, wraplength=540); self.err.pack(fill="x", padx=16)
        bb = tk.Frame(ft, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Huỷ", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Thuê ngay", self.buy); self.go.pack(side="right")
        self.upd()

    def tier_match(self, t):
        """Cấu hình đang chọn khớp gói t (kẹp theo trần của bản Android đang chọn)."""
        p, s = self.pr, self.s; lo = lambda k: int(num(p.get(k))); ar, ac = and_lim(p, s["android"])
        cl = lambda v, a, b: max(a, min(b, v))
        return (s["ram"] == cl(t["ram"], lo("min_ram"), ar) and s["cpu"] == cl(t["cpu"], lo("min_cpu"), ac)
                and s["fps"] == cl(t["fps"], lo("min_fps"), lo("max_fps")) and (not t.get("res") or s["res"] == t["res"]))

    def tier_on(self, t):
        """Gói t đang được chọn = khách ĐÃ chọn + cấu hình khớp gói."""
        return getattr(self, "picked", False) and self.tier_match(t)

    def tier_ands(self, t):
        """Bản Android chạy được gói t (đủ trần RAM / nhân)."""
        return [v for v in and_list(self.pr) if t["ram"] <= and_lim(self.pr, v)[0] and t["cpu"] <= and_lim(self.pr, v)[1]]

    def pick_tier(self, t):
        """Bấm 1 gói → điền RAM · CPU · FPS (· độ phân giải); bản Android đang chọn không đủ trần → chuyển bản."""
        p, s = self.pr, self.s; lo = lambda k: int(num(p.get(k)))
        self.picked = True
        ands = self.tier_ands(t)
        if ands and s["android"] not in ands:
            free = [v for v in ands if not and_why(self.st, v, t["ram"], t["cpu"])]
            s["android"] = (free or ands)[0]
            self._tier_msg = f"Gói {t['name']} chạy trên Android {' / '.join(ands)} — đã chuyển sang Android {s['android']}."
        ar, ac = and_lim(p, s["android"]); cl = lambda v, a, b: max(a, min(b, v))
        s["ram"], s["cpu"] = cl(t["ram"], lo("min_ram"), ar), cl(t["cpu"], lo("min_cpu"), ac)
        s["fps"] = cl(t["fps"], lo("min_fps"), lo("max_fps"))
        if t.get("res") and any(r == t["res"] for r, _n in CP_RES): s["res"] = t["res"]
        self.app.root.after_idle(lambda: self.alive and self.build())

    def toggle_custom(self):
        self.custom = not self.custom
        self.app.root.after_idle(lambda: self.alive and self.build())

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
            te = trial_err(p)                                               # v35: chưa nạp đủ / đã dùng thử rồi
            if te: return te
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
        need = self.need()
        if getattr(self, "cust_lbl", None):
            try: self.cust_lbl.config(text="⚙️ Tự chỉnh cấu hình" + ("" if need else f"    {s['ram']}GB · {s['cpu']} nhân · {s['res']} · {s['fps']} FPS"))
            except Exception: pass
        why = {v: and_why(self.st, v, *self.fit(v)) for v in and_list(p)}                  # giải thích vì sao bản Android bị mờ
        self.and_note.config(text="   ".join(f"Android {v}: " + ("máy chủ đang bảo trì" if w == "off" else "hết chỗ cho cấu hình này")
                                             for v, w in why.items() if w and self.prof.get("role") != "admin"))
        bal = num(self.prof.get("balance"))
        self.bal.config(text="Số dư: " + vnd(bal))
        if need:                                             # CHƯA chọn gói → không hiện số tiền nào
            self.pick_lbl.config(text="Chưa chọn gói", fg=DIM)
            self.calc.config(text="Bấm 1 gói ở bước 2 để xem giá.")
            self.total.config(text="—"); self.err.config(text="")
            self.go.config(text="Chọn gói trước", state="disabled", bg=LINE)
            return
        cur = next((t for t in getattr(self, "tl", []) if self.tier_on(t)), None)
        name = ("★ Máy dùng thử" if trial_hours(p) else "★ Máy miễn phí") if s["free"] else (f"{cur['icon']}  {cur['name']}" if cur else "⚙️ Cấu hình tự chọn")
        self.pick_lbl.config(fg=TXT, text=f"{name}   ·   Android {s['android']} · {s['cpu']} nhân · {s['ram']}GB · {s['fps']} FPS · "
                                          + (trial_dur(p) if s["free"] else f"{s['days']} ngày" + (f" × {s['qty']} máy" if s["qty"] > 1 else "")))
        bad, price = self.check(), self.price()
        if s["free"]:
            self.calc.config(text=f"Dùng thử miễn phí {trial_dur(p)} · Android {s['android']} · {s['ram']}GB · {s['cpu']} nhân")
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
        self.total.config(text="—" if bad else vnd(price))
        low = (s["ram"] < 4 or s["cpu"] < 4) and cur is None and not s["free"]     # gói đã ghi rõ công dụng → chỉ nhắc khi tự chỉnh
        warn = "" if bad else ("Số dư không đủ — cần nạp thêm " + vnd(price - bal) + "." if price > bal
                               else "⚠ Cấu hình này chưa đủ chơi game 3D (cần tối thiểu 4GB · 4 nhân) — hợp treo app, game nhẹ." if low else "")
        self.err.config(text=bad or warn, fg=BAD if bad or price > bal else WARN)
        self.go.config(text=("Nhận máy dùng thử" if trial_hours(p) else "Nhận máy miễn phí") if s["free"] else ("Nạp tiền" if not bad and price > bal else "💎 Thuê bằng Blue" if price <= 0 and bu > 0
                                                                   else "Thuê ngay" + (f" {s['qty']} máy" if s["qty"] > 1 else "")),
                       state="disabled" if bad else "normal", bg=LINE if bad else ACC)

    def buy(self):
        if self.need(): return                                 # chưa chọn gói → nút đang khoá, chặn thêm 1 lớp
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
        if not mb.askyesno("Xác nhận thuê máy", what + extra + ((f"\n\nMáy dùng thử {trial_dur(self.pr)} — không trừ tiền. Hết giờ máy và dữ liệu tự xoá." if trial_hours(self.pr) else "\n\nMáy miễn phí — không trừ tiền.") if s["free"] else f"\n\nTrừ {vnd(price)} từ số dư?"), parent=self.win): return
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
            self._promo_code = ""; self._blue_on = False; BLUE["t"] = 0; OFFERS["t"] = 0
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
        self.bg(lambda: (app.shop.site(), app.shop.profile(), wheel_fresh(app.auth), offers_fresh(app.auth)), self._loaded, lambda m: self.loading(m))   # 🎡 vòng quay + 🎁 ưu đãi

    def _loaded(self, r):
        tk = self.app.tk; self.site, self.prof = r[0], r[1]; self.clear()
        self.min = max(1000, int(num(self.site.get("minTop")) or 10000))
        amt = max(self.min, int(-(-self.need // 1000) * 1000)) if self.need > 0 else max(self.min, 50000)
        self.amt = amt
        self.label(self.body, "Nạp tiền vào tài khoản", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, "Số dư hiện tại: " + vnd(self.prof.get("balance")) + (f"   ·   Cần thêm {vnd(self.need)}" if self.need > 0 else ""),
                   self.app.f_t, DIM).pack(fill="x", padx=18)
        self.whb = tk.Frame(self.body, bg=BG); self.whb.pack(fill="x", padx=18); wheel_banner(self, self.whb)   # 🎡 vòng quay may mắn
        self._offers_box()                                                   # 💰 ưu đãi khi nạp + 📱 dùng thử (SQL v35)
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
        self.wh = self.label(f, "", self.app.f_s, W_SKY, wraplength=540)      # 🎡 "Lệnh nạp này được +N lượt quay" (wheel_hint tự hiện / ẩn)
        self.oh = self.label(f, "", ("Segoe UI", 9, "bold"), OK, wraplength=540)   # 🎁 "Lần nạp này được tặng mã giảm N%" (offers_hint tự hiện / ẩn)
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

    def _offers_box(self):
        tk = self.app.tk; tc = offers_topup(); tr = offers_sec("trial"); my = OFFERS["my"] or {}
        trial = bool(tr and num(tr.get("need")) > 0)
        if not tc and not trial: return
        c = tk.Frame(self.body, bg=CARD, highlightbackground=LINE, highlightthickness=1); c.pack(fill="x", padx=18, pady=(8, 0))
        if tc:
            self.label(c, "💰 Nạp 1 lần — nhận 1 mã giảm giá cloud phone", ("Segoe UI", 10, "bold"), TXT).pack(fill="x", padx=12, pady=(8, 2))
            row = tk.Frame(c, bg=CARD); row.pack(fill="x", padx=12)
            for x in tc["levels"]:
                if not isinstance(x, dict): continue
                self.app.btn(row, f"Từ {vnd(x.get('min'))} → mã {int(num(x.get('pct')))}%", lambda v=int(num(x.get("min"))): self._pick_amt(v), "soft", padx=8, pady=3).pack(side="left", padx=(0, 6))
            self.label(c, f"Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp) · dùng 1 lần · hạn {int(num(tc.get('days')) or 7)} ngày · chỉ cho cloud phone (thuê / gia hạn / nâng cấp).",
                       self.app.f_s, DIM, wraplength=530).pack(fill="x", padx=12, pady=(4, 0))
            if my.get("topup_got"):
                mine = next((x for x in (my.get("codes") or []) if isinstance(x, dict) and x.get("src") == "topup" and x.get("usable")), None)
                self.label(c, "🎫 " + ("Mã của bạn: " + code_label(mine) if mine else "Bạn đã nhận mã của đợt này rồi."), ("Segoe UI", 9, "bold"), OK).pack(fill="x", padx=12, pady=(2, 0))
        if trial:
            t = trial_my() or {}; h = int(num(tr.get("hours"))); dur = f"{h} giờ" if h > 0 else f"{int(num(tr.get('days')) or 1)} ngày"
            self.label(c, "📱 " + ("Bạn đã dùng thử 1 máy rồi." if t.get("used")
                                   else f"Bạn được dùng thử 1 cloud phone {dur} miễn phí — mở + Thuê máy, tích “Dùng thử MIỄN PHÍ”." if t.get("ok")
                                   else f"Nạp 1 lần từ {vnd(tr.get('need'))} → dùng thử 1 cloud phone {dur} miễn phí."),
                       self.app.f_s, TXT, wraplength=530).pack(fill="x", padx=12, pady=(6 if tc else 8, 0))
        tk.Frame(c, bg=CARD, height=8).pack()

    def _pick_amt(self, v):
        self.amt = max(self.min, int(v))
        try: self.x.delete(0, "end")
        except Exception: pass
        self.upd()

    def upd(self):
        self.ch.paint(); wheel_hint(self); offers_hint(self)
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
        wheel_after_top(self, amt)                     # 🎡 lệnh nạp được lượt quay → nút Quay ngay
        offers_after_top(self, amt)                    # 🎁 mã vừa được tặng / lượt dùng thử vừa mở (SQL v35)
        self.app.refresh()


# ================= 🎡 VÒNG QUAY MAY MẮN (SQL v34d) — giống web / app Android: nạp 100.000đ = 2 lượt · mua lượt 15.000đ · 🍀 vé may mắn 20.000đ =================
# Máy chủ rút số (wheel_spin) → app chỉ quay hình tới ĐÚNG ô mã khách nhận. Lúc chưa quay: hiện số. Đang quay: ẩn hết số + màu ô (dấu ?)
# → kim dừng → cửa sổ mở quà: hộp quà rơi · rung · NỔ (nắp bay, chớp sáng, tia sáng, pháo giấy + bong bóng) → thẻ mã. Khách KHÔNG thấy tỷ lệ.
# Quay thêm có tính phí: luôn hỏi lại (giá + số dư còn lại) — máy chủ trừ tiền và quay trong CÙNG 1 lệnh.
# Máy chủ chưa chạy SQL v34c / admin tắt → wheel_status lỗi hoặc state off → ẩn hết, app như cũ.
import math

WHEEL = {"st": None, "t": 0.0, "dlg": None}
W_INK, W_PEARL, W_PEARL2, W_SUB, W_SKY = "#0b1433", "#f2f7ff", "#c9d7ee", "#b9c8ea", "#8fd0ff"
W_DEEP, W_CARD, W_FOOT, W_EDGE, W_TILE = "#0d1640", "#132160", "#0a1132", "#2a3a78", "#14205a"
W_REV = "#060b1d"

ERRORS.update({                                                  # 🎡 vòng quay may mắn (SQL v34c)
    "PROMO_NOT_YOURS": "Mã này là mã riêng của tài khoản khác — chỉ tài khoản được tặng mới dùng được.",
    "PROMO_DAY_LIMIT": "Hôm nay bạn đã dùng đủ số mã giảm giá cho phép — mai dùng tiếp nhé.",
    "cloudphone_switch_retry": "Máy chủ chưa bật nút thử lại — nhắn shop để được tạo lại máy.",
    "WHEEL_NO_SPIN": "Bạn đã hết lượt quay — nạp thêm để nhận lượt mới.", "WHEEL_NOT_STARTED": "Vòng quay chưa bắt đầu.",
    "WHEEL_ENDED": "Chương trình vòng quay đã kết thúc.", "WHEEL_OFF": "Vòng quay đang tạm tắt.", "WHEEL_EMPTY": "Vòng quay đã hết giải.",
    "WHEEL_NO_BUY": "Hiện không bán thêm lượt quay.", "WHEEL_PRICE_CHANGED": "Giá quay thêm vừa thay đổi — xem lại giá rồi bấm lại.",
    "WHEEL_NEED_TOPUP": "Nạp từ 100.000đ trong chương trình để được quay thêm.",
    "WHEEL_BUY_LIMIT": "Hôm nay bạn đã mua đủ số lượt quay thêm — mai quay tiếp nhé.",
    "WHEEL_TERMS_CHANGED": "Điều kiện mua lượt / vé vừa đổi — xem lại rồi bấm lại.", "WHEEL_NO_LUCKY": "Hiện không bán vé may mắn.",   # SQL v34d
})


def wheel_load(auth):
    """Đọc wheel_status (gọi ở luồng nền). Chưa chạy SQL v34c → None (ẩn mọi thứ); mất mạng / máy chủ lỗi tạm → giữ bản cũ."""
    try: s = auth.rpc("wheel_status")
    except ApiError as e:
        if e.code == 401: raise
        if e.code == 0 or e.code >= 500: WHEEL["t"] = time.time(); return WHEEL["st"]
        s = None
    except Exception: s = None
    WHEEL["st"] = s if isinstance(s, dict) and s.get("state") else None; WHEEL["t"] = time.time()
    return WHEEL["st"]

def wheel_fresh(auth, age=30.0):
    if time.time() - WHEEL["t"] > age: wheel_load(auth)
    return WHEEL["st"]

def wheel_live(s=None):
    s = WHEEL["st"] if s is None else s
    return bool(s and s.get("state") in ("on", "soon") and (s.get("prizes") or []))

def wheel_per(s=None): return max(1, int(num((s or WHEEL["st"] or {}).get("spins_per")) or 1))

def wheel_first(s=None):
    """(nạp bao nhiêu, được mấy lượt) cho câu 'Nạp 100.000đ = 2 lượt'."""
    s = s or WHEEL["st"] or {}
    per = max(1, int(num(s.get("per")) or 100000)); a = max(int(num(s.get("min"))), per)
    return a, (a // per) * wheel_per(s)

def wheel_spins_for(amount, s=None):
    s = s or WHEEL["st"]
    if not s or num(amount) < num(s.get("min")): return 0
    return int(num(amount) // max(1, int(num(s.get("per")) or 100000))) * wheel_per(s)

def wheel_top(s=None):
    pz = (s or WHEEL["st"] or {}).get("prizes") or []
    av = [p for p in pz if p.get("left") is None or num(p.get("left")) > 0]
    return max([int(num(p.get("pct"))) for p in (av or pz)] or [0])

def wheel_when(iso):
    d = parse_iso(iso)
    return d.astimezone().strftime("%H:%M %d/%m") if d else ""

def wheel_order(pz):
    """Xen kẽ giải nhỏ / giải lớn: 5 · 40 · 10 · 50 · 15 · 60 · 20 · 80 · 25 (giống web + app Android)."""
    a = sorted(pz or [], key=lambda p: num(p.get("pct"))); lo = [p for p in a if num(p.get("pct")) < 40]; hi = [p for p in a if num(p.get("pct")) >= 40]; out = []
    while lo or hi:
        if lo: out.append(lo.pop(0))
        if hi: out.append(hi.pop(0))
    return out

def wheel_rate(v):
    v = round(float(num(v)), 2)
    return (str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0")).replace(".", ",")

def wheel_pcts(a):
    """[5, 10] → "5% hoặc 10%"."""
    v = sorted({int(num(x)) for x in (a or [])})
    if not v: return ""
    return f"{v[0]}%" if len(v) == 1 else "%, ".join(str(x) for x in v[:-1]) + f"% hoặc {v[-1]}%"

def wheel_lucky(s=None):
    """🍀 vé may mắn (SQL v34d): {price, pool, rate, lo, hi, else} — rate = % trúng nhóm mức cao · None = không bán vé / SQL cũ."""
    s = s or WHEEL["st"] or {}
    pool = [{"pct": int(num(p.get("pct"))), "rate": float(num(p.get("rate")))} for p in (s.get("lucky_pool") or []) if isinstance(p, dict)]
    if num(s.get("lucky_price")) <= 0 or not pool: return None
    lo = min(p["pct"] for p in pool); up = [p for p in pool if p["pct"] > lo]; g = up or pool
    return {"price": int(num(s.get("lucky_price"))), "pool": pool, "rate": round(sum(p["rate"] for p in g), 2),
            "lo": min(p["pct"] for p in g), "hi": max(p["pct"] for p in g), "else": lo if up else None}

def wheel_lucky_line(k):
    rg = f"{k['lo']}%" if k["lo"] == k["hi"] else f"{k['lo']}–{k['hi']}%"
    return f"{wheel_rate(k['rate'])}% trúng mã {rg}" + (f" · còn lại mã {k['else']}%" if k["else"] is not None else "")

def wheel_luck_slices(s=None):
    """Mặt vé: các mức giải của vé lặp lại cho đủ ~8 ô."""
    k = wheel_lucky(s)
    if not k: return []
    out = []
    for _ in range(max(1, -(-8 // len(k["pool"])))):
        for p in k["pool"]:
            if len(out) < 12: out.append({"pct": p["pct"], "stock": None, "left": None})
    return out

def wheel_mix(c1, c2, t):
    """Pha 2 màu #rrggbb (Tk không có độ trong suốt)."""
    t = max(0.0, min(1.0, t)); a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

def wheel_ease(t, x1=.12, y1=.67, x2=.06, y2=1.0):
    """cubic-bezier(.12,.67,.06,1) — đúng đường chậm dần của web / app Android."""
    if t <= 0: return 0.0
    if t >= 1: return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(32):
        u = (lo + hi) / 2
        if 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3 < t: lo = u
        else: hi = u
    u = (lo + hi) / 2
    return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3

def wheel_scale(app):
    """Màn hình phóng to 125–150%: chữ Tk tự to theo, hình vẽ trên Canvas phải nhân theo cho cân."""
    try: return max(1.0, min(2.0, float(app.root.tk.call("tk", "scaling")) / (96 / 72)))
    except Exception: return 1.0

def wheel_open(app, parent=None):
    """Mở hộp vòng quay (đang mở rồi thì đưa lên trước, không mở 2 hộp)."""
    d = WHEEL.get("dlg")
    if d is not None and d.alive:
        try: d.win.deiconify(); d.win.lift(); d.win.focus_force()
        except Exception: pass
        return d
    WHEEL["dlg"] = d = WheelDlg(app, parent)
    return d

def wheel_icon(cv, m):
    """Vòng quay nhỏ trên thẻ (giống icon web)."""
    k = m / 48.0; c = 24 * k; r = 19 * k
    for i in range(8):
        col = W_PEARL if i % 4 == 1 else "#3d7bff" if i % 2 else "#1b2a63"
        cv.create_arc(c - r, c - r, c + r, c + r, start=90 - (i + .5) * 45, extent=45, fill=col, outline="#9eacc8", width=1)
    cv.create_oval(c - 21 * k, c - 21 * k, c + 21 * k, c + 21 * k, outline="#dfe6f2", width=max(2, round(3 * k)))
    cv.create_oval(c - 5.5 * k, c - 5.5 * k, c + 5.5 * k, c + 5.5 * k, fill="#2a5fe0", outline="#e9eef8", width=max(1, round(1.6 * k)))
    cv.create_polygon(c, 9 * k, c - 4 * k, 1.5 * k, c + 4 * k, 1.5 * k, fill="#eef3fb", outline=W_INK)

def wheel_banner(owner, holder):
    """Thẻ 🎡 ngay trong hộp Nạp tiền + màn danh sách máy (ẩn khi chưa chạy SQL / admin tắt / đã kết thúc)."""
    app = getattr(owner, "app", owner); tk = app.tk; sc = wheel_scale(app)
    try:
        for w in holder.winfo_children(): w.destroy()
    except Exception: return
    s = WHEEL["st"]
    if not wheel_live(s): return
    a, n = wheel_first(s); left = int(num(s.get("left"))); soon = s.get("state") == "soon"; hot = not soon and left > 0
    sub = (f"Bắt đầu {wheel_when(s.get('starts_at'))} · nạp {vnd(a)} = {n} lượt quay" if soon
           else f"Bạn đang có {left} lượt quay — lượt nào cũng trúng 1 mã giảm giá" if hot
           else f"Nạp {vnd(a)} = {n} lượt quay" + (f" · mua lượt {vnd(s.get('price'))}" if num(s.get("price")) > 0 else "")
                + (f" · 🍀 vé may mắn {vnd(wheel_lucky(s)['price'])}" if wheel_lucky(s) else ""))
    f = tk.Frame(holder, bg=W_CARD, highlightbackground="#5a6c9c", highlightthickness=1); f.pack(fill="x", pady=(8, 0))
    b = app.btn(f, f"🎡 Quay ngay · {left}" if hot else "Xem giải" if soon else "🎡 Mở vòng quay",
                lambda: wheel_open(app, owner if isinstance(owner, Dlg) else None), "primary" if hot else "soft")
    if not hot: b.config(bg="#24357a", activebackground="#33489a")
    b.pack(side="right", padx=10, pady=8)
    m = int(44 * sc); ic = tk.Canvas(f, width=m, height=m, bg=W_CARD, highlightthickness=0); ic.pack(side="left", padx=(10, 0), pady=8)
    wheel_icon(ic, m)
    ic.bind("<Button-1>", lambda e: wheel_open(app, owner if isinstance(owner, Dlg) else None)); ic.configure(cursor="hand2")
    tx = tk.Frame(f, bg=W_CARD); tx.pack(side="left", fill="x", expand=True, padx=10, pady=8)
    tk.Label(tx, text=f"Vòng quay may mắn · mã giảm đến {wheel_top(s)}%", font=("Segoe UI", 10, "bold"), fg=W_PEARL, bg=W_CARD, anchor="w").pack(fill="x")
    tk.Label(tx, text=sub, font=("Segoe UI", 9), fg=W_SUB, bg=W_CARD, anchor="w", justify="left", wraplength=int(300 * sc)).pack(fill="x")

def wheel_hint(dlg):
    """Dòng '🎡 Lệnh nạp này được +N lượt quay' dưới ô số tiền (hộp Nạp tiền)."""
    l = getattr(dlg, "wh", None)
    try:
        if l is None or not l.winfo_exists(): return
    except Exception: return
    s = WHEEL["st"]; t = ""
    if wheel_live(s):
        n = wheel_spins_for(getattr(dlg, "amt", 0), s); a, fn = wheel_first(s)
        t = (f"🎡 Vòng quay bắt đầu {wheel_when(s.get('starts_at'))} — lệnh nạp từ lúc đó mới được tính lượt quay." if s.get("state") == "soon"
             else f"🎡 Lệnh nạp này được +{n} lượt quay may mắn" if n > 0 else f"🎡 Nạp từ {vnd(a)} để được {fn} lượt quay may mắn")
    l.config(text=t)
    if t and not l.winfo_manager(): l.pack(fill="x", pady=(6, 0))
    elif not t and l.winfo_manager(): l.pack_forget()

def wheel_after_top(dlg, amt):
    """Nạp xong (hộp Nạp tiền): lệnh nạp được lượt quay → báo +N lượt + nút 🎡 Quay ngay. Lần làm mới sau đọc lại số lượt từ máy chủ."""
    s = WHEEL["st"]; WHEEL["t"] = 0.0
    n = wheel_spins_for(amt, s) if s and s.get("state") == "on" else 0
    if n <= 0 or not dlg.alive: return
    try:
        dlg.state.config(text=f"✓ Đã nhận {vnd(amt)} — số dư đã được cộng.   🎡 +{n} lượt quay may mắn!", fg=OK)
        app = dlg.app
        dlg.app.btn(dlg.done_btn.master, f"🎡 Quay ngay · +{n} lượt", lambda: (dlg.close(), wheel_open(app))).pack(side="right", padx=(0, 8))
    except Exception: log("wheel:", traceback.format_exc())


class WheelDlg(Dlg):
    """🎡 Hộp vòng quay: vẽ trên Canvas, quay tới đúng ô máy chủ báo, ẩn số khi quay, mở quà, quay thêm có hỏi lại, hướng dẫn, mã của tôi, thể lệ."""
    LO = ("#22337f", "#16236a"); LO_IN = ("#121c4f", "#0d1540"); MID, MID_IN = "#4a86ff", "#1f4bc4"; HI, HI_IN = "#f4f7fc", "#c2cfe8"
    GONE, GONE_IN = "#2c3352", "#1a1f36"; MYS = ("#1d2c74", "#283d9c"); MYS_IN = ("#0e1648", "#142060")
    LK = (("#ffe08a", "#7a5a10"), ("#5cf0c2", "#0d7a5f"), ("#20b98c", "#0a5546"), ("#11524a", "#062a28"))   # 🍀 mặt vé: cao nhất vàng → thấp nhất xanh đậm
    LK_MYS = ("#0f5a4a", "#137a63"); LK_MYS_IN = ("#04261f", "#073a30")

    def __init__(self, app, parent=None):
        self.sc = sc = wheel_scale(app)
        super().__init__(app, "🎡 Vòng quay may mắn", int(560 * sc), int(840 * sc), grow=False)       # hộp này tự nhân theo cỡ chữ (sc) rồi
        self.parent = parent; self.S = int(360 * sc)
        self.st = WHEEL["st"]; self.rot = 0.0; self.mys = False; self.busy = False; self.win_i = -1; self.pz = []; self.paid_any = False
        self.act = "spin"; self.rules_open = False; self.cv = None; self.t_bulb = 0; self.hub_on = False; self.bulb_ids = []; self.geo = None; self.luck = False
        self.win.configure(bg=W_DEEP); self.body.configure(bg=W_DEEP)                       # nền xanh sapphire sâu (giống web)
        scv = app.scrollers.get(str(self.win))
        if scv is not None: scv.configure(bg=W_DEEP); scv.master.configure(bg=W_DEEP)
        self.foot.configure(bg=W_FOOT, highlightbackground=W_EDGE)
        self.loading("Đang tải vòng quay…")
        self.bg(lambda: wheel_load(app.auth), self._loaded, lambda m: self.loading(m))

    def px(self, v): return int(v * self.sc)

    def close(self):
        if not self.alive: return
        paid, par = self.paid_any, self.parent
        super().close()
        if WHEEL.get("dlg") is self: WHEEL["dlg"] = None
        try: self.app._paint_wheel()
        except Exception: pass
        if par is not None and getattr(par, "alive", False):                               # mở từ hộp Nạp tiền → trả lại hộp đó
            try:
                if getattr(par, "whb", None) is not None: wheel_banner(par, par.whb)
                wheel_hint(par); par._grab()
            except Exception: pass
        if paid:
            try: self.app.refresh(quiet=True)
            except Exception: pass

    def _grab(self):
        if self.alive: super()._grab()

    def _loaded(self, s):
        self.st = s
        if not s:
            self.clear(); self.label(self.body, "Vòng quay chưa mở — quay lại sau nhé.", self.app.f_t, W_SUB).pack(padx=18, pady=30)
            self.app.btn(self.foot, "Đóng", self.close, "soft").pack(side="right", padx=16, pady=10); return
        self.build()

    # ---------------------------------------------------------------- bố cục
    def build(self):
        tk = self.app.tk; self.clear()
        hd = tk.Frame(self.body, bg=W_DEEP); hd.pack(fill="x", padx=18, pady=(16, 0))
        tk.Label(hd, text="Vòng quay may mắn", font=("Segoe UI", 17, "bold"), fg=W_PEARL, bg=W_DEEP).pack(side="left")
        tk.Label(hd, text=" VIP ", font=("Segoe UI", 8, "bold"), fg=W_INK, bg=W_PEARL2).pack(side="left", padx=8, pady=(4, 0))
        self.left_l = tk.Label(hd, text="", font=("Segoe UI", 10, "bold"), bg=W_DEEP, padx=12, pady=3); self.left_l.pack(side="right")
        self.sub_l = self.label(self.body, "", self.app.f_s, W_SUB, wraplength=self.px(500)); self.sub_l.pack(fill="x", padx=18, pady=(4, 0))
        self.cv = tk.Canvas(self.body, width=self.S, height=int(self.S * 1.07), bg=W_DEEP, highlightthickness=0); self.cv.pack(pady=(6, 0))
        self.cv.tag_bind("hub", "<Button-1>", lambda e: self.hub())
        self.cv.tag_bind("hub", "<Enter>", lambda e: self.cv.configure(cursor="hand2" if self.hub_on and not self.busy else ""))
        self.cv.tag_bind("hub", "<Leave>", lambda e: self.cv.configure(cursor=""))
        self.luck_f = tk.Frame(self.body, bg=W_DEEP); self.luck_f.pack(fill="x", padx=18, pady=(6, 0))     # 🍀 vé may mắn
        self.err_l = self.label(self.body, "", self.app.f_s, BAD, wraplength=self.px(500)); self.err_l.pack(fill="x", padx=18)
        self.guide_f = tk.Frame(self.body, bg=W_DEEP); self.guide_f.pack(fill="x", padx=18, pady=(8, 0))
        self.mine_f = tk.Frame(self.body, bg=W_DEEP); self.mine_f.pack(fill="x", padx=18, pady=(12, 0))
        self.rules_b = self.label(self.body, "📜 Thể lệ  ▸", ("Segoe UI", 10, "bold"), W_PEARL, cursor="hand2"); self.rules_b.pack(fill="x", padx=18, pady=(12, 14))
        self.rules_b.bind("<Button-1>", lambda e: self.toggle_rules())
        self.rules_f = tk.Frame(self.body, bg=W_DEEP)
        bb = tk.Frame(self.foot, bg=W_FOOT); bb.pack(fill="x", padx=16, pady=10)
        self.app.btn(bb, "Đóng", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Quay", self.main, padx=18, pady=10); self.go.config(font=("Segoe UI", 11, "bold"))
        self.go.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self.render(); self._bulbs()

    def render(self):
        s = self.st or {}; left = int(num(s.get("left"))); st = s.get("state", "off"); a, n = wheel_first(s); has = st == "on" and left > 0
        self.left_l.config(text=f"{left} lượt", fg=W_INK if has else "#cfe0ff", bg=W_PEARL if has else "#16205a")
        self.sub_l.config(text=(f"Bắt đầu {wheel_when(s.get('starts_at'))}. Nạp {vnd(a)} = {n} lượt quay." if st == "soon"
                                else f"Nạp {vnd(a)} = {n} lượt · lượt nào cũng trúng mã giảm giá · số dư {vnd(self.balance())}" if st == "on"
                                else "Chương trình đã kết thúc. Mã đã trúng vẫn dùng được đến hết hạn." if st == "ended"
                                else "Vòng quay đang tạm tắt. Mã đã trúng vẫn dùng được đến hết hạn."))
        if not self.busy: self.pz = wheel_luck_slices(s) if self.luck else wheel_order(s.get("prizes"))
        self.buttons(); self.draw(); self.fill_luck(); self.fill_guide(); self.fill_mine(); self.fill_rules()

    def fill_luck(self):
        tk = self.app.tk; f = self.luck_f
        for w in f.winfo_children(): w.destroy()
        s = self.st or {}; k = wheel_lucky(s)
        if not k or s.get("state") != "on": return
        c = tk.Frame(f, bg="#0f3d37", highlightbackground="#4fd6ad", highlightthickness=1); c.pack(fill="x")
        b = self.app.btn(c, "Dùng vé", self.ask_lucky, padx=14, pady=6)
        b.config(bg="#2fd9a6", fg="#03261b", activebackground="#5cf0c2", activeforeground="#03261b", state="disabled" if self.busy else "normal")
        b.pack(side="right", padx=10, pady=8)
        tk.Label(c, text="🍀", font=("Segoe UI", 18), fg="#ffffff", bg="#0f3d37").pack(side="left", padx=(10, 6))
        tx = tk.Frame(c, bg="#0f3d37"); tx.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(tx, text=f"Vé may mắn · {vnd(k['price'])}", font=("Segoe UI", 10, "bold"), fg="#dcfff2", bg="#0f3d37", anchor="w").pack(fill="x")
        tk.Label(tx, text=wheel_lucky_line(k), font=("Segoe UI", 9), fg="#a9dcc9", bg="#0f3d37", anchor="w", justify="left", wraplength=self.px(330)).pack(fill="x")

    def balance(self):
        s = self.st or {}
        if s.get("balance") is not None: return num(s.get("balance"))
        return num((getattr(self.app, "prof", None) or {}).get("balance"))

    def buttons(self):
        s = self.st or {}; left = int(num(s.get("left"))); st = s.get("state", "off"); a, n = wheel_first(s); dis = False; self.act = "spin"; kind = "primary"
        if self.busy: txt, dis = "Đang quay…", True
        elif st == "off": txt, dis = "Vòng quay đang tạm tắt", True
        elif st == "ended": txt, dis = "Chương trình đã kết thúc", True
        elif st == "soon": txt, dis = f"Bắt đầu lúc {wheel_when(s.get('starts_at'))}", True
        elif left > 0: txt = f"🎡 Quay ngay · còn {left} lượt"
        elif s.get("can_buy"): txt, self.act, kind = (f"➕ Quay thêm · {vnd(s.get('price'))}/lượt" if num(s.get("earned")) > 0 else f"➕ Mua lượt quay · {vnd(s.get('price'))}"), "buy", "pearl"
        elif num(s.get("price")) > 0 and s.get("qualified") and s.get("buy_left") == 0: txt, self.act, kind = "Hôm nay đã mua đủ lượt — nạp thêm để nhận lượt mới", "top", "soft"
        else: txt, self.act, kind = f"💳 Nạp {vnd(a)} để nhận {n} lượt quay", "top", "soft"
        bg = {"primary": ACC, "pearl": W_PEARL2, "soft": "#24357a"}[kind]
        try:
            self.go.config(text=txt, state="disabled" if dis else "normal", bg="#1c2550" if dis else bg, fg=W_INK if kind == "pearl" else TXT,
                           activebackground="#ffffff" if kind == "pearl" else "#4b8cff", activeforeground=W_INK if kind == "pearl" else TXT,
                           disabledforeground="#8f9bbd")
        except Exception: pass
        self.hub_on = not self.busy and not self.luck and st == "on" and (left > 0 or bool(s.get("can_buy")))

    def main(self):
        if self.act == "top": self.to_topup(); return
        if self.act == "buy": self.ask(); return
        self.spin(False)

    def to_topup(self, need=0):
        par = self.parent
        self.close()
        if par is not None and getattr(par, "alive", False) and isinstance(par, TopupDlg): return    # đang ở hộp Nạp tiền rồi
        self.app.open_topup(need)

    def hub(self):
        s = self.st or {}
        if self.busy or not self.hub_on: return
        if int(num(s.get("left"))) > 0: self.spin(False)
        elif s.get("can_buy"): self.ask()

    def ask(self):
        """Quay thêm có tính phí: LUÔN hỏi lại, ghi rõ giá + số dư còn lại. Thiếu tiền → mời nạp thêm."""
        import tkinter.messagebox as mb
        s = self.st or {}; price = int(num(s.get("price"))); bal = self.balance()
        if self.busy or price <= 0 or not self.alive: return
        if bal < price:
            if mb.askyesno("Số dư chưa đủ", f"Quay thêm 1 lượt giá {vnd(price)} — số dư của bạn còn {vnd(bal)}.\n\nNạp thêm để quay tiếp?", parent=self.win):
                self.to_topup(price - bal)
            return
        more = "" if s.get("buy_left") is None else f"\nHôm nay còn mua được {int(num(s.get('buy_left')))} lượt / vé."
        note = "" if s.get("paid_max") is None else (f"🎯 Lượt mua chỉ trúng mã {wheel_pcts(s.get('paid_pcts'))} — mã lớn hơn có ở lượt nạp tiền"
                                                     + (" và 🍀 vé may mắn" if wheel_lucky(s) else "") + ".\n\n")
        if mb.askyesno("Quay thêm 1 lượt?" if num(s.get("earned")) > 0 else "Mua 1 lượt quay?",
                       f"{note}Trừ {vnd(price)} vào số dư · còn lại {vnd(bal - price)}.{more}\n\nTrả {vnd(price)} và quay?", parent=self.win):
            self.spin(True)

    def ask_lucky(self):
        """🍀 Dùng vé: LUÔN hỏi lại, ghi đủ từng mức giải + tỷ lệ, giá, số dư còn lại."""
        import tkinter.messagebox as mb
        s = self.st or {}; k = wheel_lucky(s); bal = self.balance()
        if self.busy or not k or s.get("state") != "on" or not self.alive: return
        if s.get("can_lucky") is False:
            mb.showinfo("Vé may mắn", "Hôm nay bạn đã mua đủ số lượt / vé — mai quay tiếp nhé.", parent=self.win); return
        if bal < k["price"]:
            if mb.askyesno("Số dư chưa đủ", f"Vé may mắn giá {vnd(k['price'])} — số dư của bạn còn {vnd(bal)}.\n\nNạp thêm để dùng vé?", parent=self.win):
                self.to_topup(k["price"] - bal)
            return
        odds = "\n".join(f"   Mã {p['pct']}% · {wheel_rate(p['rate'])}%" for p in sorted(k["pool"], key=lambda x: -x["pct"]))
        more = "" if s.get("buy_left") is None else f"\nHôm nay còn mua được {int(num(s.get('buy_left')))} lượt / vé."
        if mb.askyesno("🍀 Dùng 1 vé may mắn?", f"Giải của vé (tỷ lệ công khai):\n{odds}\n\nTrừ {vnd(k['price'])} vào số dư · còn lại {vnd(bal - k['price'])}.{more}\n\nTrả {vnd(k['price'])} và quay?",
                       parent=self.win):
            self.spin(True, lucky=True)

    # ---------------------------------------------------------------- quay
    def spin(self, pay=False, lucky=False):
        s = self.st
        if self.busy or not s or s.get("state") != "on" or not self.alive: return
        left = int(num(s.get("left"))); k = wheel_lucky(s) if lucky else None
        if lucky and not k: return
        if not lucky and left <= 0 and not pay:
            if s.get("can_buy"): self.ask()
            return
        self.luck = lucky; self.pz = wheel_luck_slices(s) if lucky else wheel_order(s.get("prizes"))
        self.busy = True; self.mys = True; self.win_i = -1; self.err_l.config(text="", fg=BAD); self.buttons(); self.draw(); self.fill_luck()   # ẨN hết số + màu ô
        if lucky: args = {"p_lucky": True, "p_price": k["price"], "p_terms": s.get("terms")}
        elif left > 0: args = {}                                                            # còn lượt miễn phí → máy chủ dùng lượt đó, không trừ tiền
        else:
            args = {"p_pay": True, "p_price": int(num(s.get("price")))}
            if s.get("terms"): args["p_terms"] = s.get("terms")                             # SQL cũ (chưa có terms) → gửi như bản 3
        self.bg(lambda: self.app.auth.rpc("wheel_spin", args), self._spun, self._fail)

    def _fail(self, m):
        self.busy = False; self.mys = False; self.luck = False; self.err_l.config(text=m, fg=BAD); self.render()
        self.bg(lambda: wheel_load(self.app.auth), lambda s: self._reloaded(s))                 # giá đổi / hết lượt… → đọc lại

    def _reloaded(self, s):
        if s: self.st = s
        if not self.busy: self.render()

    def _spun(self, r):
        if not isinstance(r, dict) or not r.get("code"): return self._fail("Vòng quay đã hết giải.")
        if num(r.get("paid")) > 0:
            self.paid_any = True
            p = getattr(self.app, "prof", None)
            if isinstance(p, dict): p["balance"] = r.get("balance")
            try:
                if getattr(self.app, "bal", None) is not None and self.app.bal.winfo_exists():
                    self.app.bal.config(text=vnd(r.get("balance")) + (f"  · CTV −{int(num(p.get('ctv_discount')))}%" if isinstance(p, dict) and is_ctv(p) else ""))
            except Exception: pass
        r["lucky"] = self.luck
        ks = [i for i, p in enumerate(self.pz) if num(p.get("pct")) == num(r.get("pct"))]                         # kim dừng đúng ô mã khách NHẬN
        if not ks: ks = [i for i, p in enumerate(self.pz) if num(p.get("pct")) == num(r.get("drawn"))] or [0]
        k = ks[secrets.randbelow(len(ks))]                                                                         # mặt vé: ô trùng → chọn ngẫu nhiên 1 ô
        seg = 360.0 / max(1, len(self.pz)); want = (-k * seg + (secrets.randbelow(1000) / 1000 - .5) * seg * .6) % 360; cur = self.rot % 360
        self.r0, self.r1, self.t0, self.dur, self.res, self.k = self.rot, self.rot + 360 * 8 + ((want - cur) % 360), time.time(), 5.6, r, k
        self._frame()

    def _frame(self):
        if not self.alive: return
        t = min(1.0, (time.time() - self.t0) / self.dur)
        self.rot = self.r0 + (self.r1 - self.r0) * wheel_ease(t); self.draw_disc()
        if t < 1: self.win.after(15, self._frame); return
        self.rot = self.r1; self.busy = False; self.win_i = self.k; r = self.res; s = self.st
        if s is not None:
            s["left"] = r.get("left", 0)
            if "buy_left" in r: s["buy_left"] = r.get("buy_left")
            if r.get("balance") is not None: s["balance"] = r.get("balance")
            if s.get("buy_left") == 0: s["can_buy"] = False; s["can_lucky"] = False
            self.render()
        self.win.after(380, lambda: self.alive and RevealWin(self, r))
        self.bg(lambda: wheel_load(self.app.auth), lambda s2: self._reloaded(s2))

    def after_reveal(self, what):
        if not self.alive: return
        self.mys = False; self._grab()                                   # hết bất ngờ → hiện lại số, ô vừa trúng sáng viền
        if self.luck: self.luck = False; self.win_i = -1; self.render()  # xong vé may mắn → về mặt vòng chính
        else: self.draw()
        if what == "again": self.spin(False)
        elif what == "buy": self.ask()
        elif what == "lucky": self.ask_lucky()

    # ---------------------------------------------------------------- vẽ (nền + đĩa quay + viền/đèn/kim/núm)
    def draw(self):
        cv = self.cv
        if cv is None or not cv.winfo_exists(): return
        cv.delete("all"); k = self.S / 200.0; cx, cy, R = 100 * k, 108 * k, 85 * k; self.geo = (k, cx, cy, R)
        for x, y, r in ((12, 9, 1), (186, 14, 1), (172, 46, 1.4), (20, 60, 1), (190, 92, 1), (8, 150, 1.2), (192, 168, 1), (28, 196, 1)):
            cv.create_oval(x * k - r, y * k - r, x * k + r, y * k + r, fill="#cfe0ff", outline="")              # sao lấp lánh
        for i in range(8, 0, -1):                                                                          # quầng sáng sân khấu
            rr = R + 20 * k * i / 8; cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=wheel_mix(W_DEEP, "#1d3a8c", (8 - i) / 8 * .85), outline="")
        cv.create_oval(cx - 70 * k, cy + 92 * k, cx + 70 * k, cy + 104 * k, fill="#091033", outline="")         # bóng đổ dưới chân
        self.draw_disc(); O = ("over",)
        for i, col in enumerate(("#0b1233", "#8e9cb6", "#c8d2e3", "#f4f7fc", "#e3e9f4", "#b8c4d9", "#dfe6f2", "#9eabc4", "#0b1233")):   # viền bạch kim
            rr = R + (i * 1.5 + .5) * k; cv.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=col, width=max(1, round(1.6 * k)), tags=O)
        self.bulb_ids = []
        for i in range(24):                                                                                # 24 bóng đèn: quầng vàng + lõi trắng
            a = math.radians(i * 15); x, y = cx + 91.5 * k * math.sin(a), cy - 91.5 * k * math.cos(a); r1, r2 = 3.4 * k, 2.1 * k
            self.bulb_ids.append((cv.create_oval(x - r1, y - r1, x + r1, y + r1, fill="#ffe6a0", outline="", tags=O),
                                  cv.create_oval(x - r2, y - r2, x + r2, y + r2, fill="#fffdf4", outline="#f0c35a", tags=O)))
        cv.create_polygon(cx, 31 * k, cx - 8 * k, 11 * k, cx + 8 * k, 11 * k, fill="#dfe6f2", outline=W_INK, width=1, tags=O)   # kim bạch kim + đá sapphire
        cv.create_line(cx, 29 * k, cx - 5.5 * k, 13 * k, fill="#ffffff", tags=O)
        cv.create_oval(cx - 7.5 * k, 1 * k, cx + 7.5 * k, 16 * k, fill="#eef3fb", outline=W_INK, width=1, tags=O)
        cv.create_oval(cx - 4 * k, 4.5 * k, cx + 4 * k, 12.5 * k, fill="#3d7bff", outline="#132c90", tags=O)
        cv.create_oval(cx - 2.2 * k, 5.6 * k, cx - .4 * k, 7.4 * k, fill="#ffffff", outline="", tags=O)
        on = self.hub_on and not self.busy; H = ("over", "hub")
        if on: cv.create_oval(cx - 36 * k, cy - 36 * k, cx + 36 * k, cy + 36 * k, outline="#6f9cff", width=max(2, round(2.4 * k)), tags=O)
        for rr, col in ((33, "#0b1233"), (31.5, "#8e9cb6"), (29.5, "#e9eef8"), (26, "#c6d1e6"), (24, "#0d2170"), (20, "#1b3fae"), (15, "#3d7bff")):  # núm QUAY
            cv.create_oval(cx - rr * k, cy - rr * k, cx + rr * k, cy + rr * k, fill=col if on or rr > 24 else wheel_mix(col, "#2a3150", .55), outline="", tags=H)
        cv.create_oval(cx - 12 * k, cy - 16 * k, cx - 2 * k, cy - 9 * k, fill="#9cc0ff" if on else "#5f6f95", outline="", tags=H)
        cv.create_text(cx, cy + .5 * k, text="QUAY", font=("Segoe UI", -int(10.5 * k), "bold"), fill="#ffffff" if on else "#aab4cf", tags=H)

    def draw_disc(self):
        cv = self.cv
        if cv is None or self.geo is None or not cv.winfo_exists(): return
        k, cx, cy, R = self.geo; cv.delete("disc"); T = ("disc",)
        n = max(1, len(self.pz)); seg = 360.0 / n; lo = 0
        ranks = sorted({int(num(p.get("pct"))) for p in self.pz}, reverse=True) if self.luck else []
        def lkr(pct): r_ = ranks.index(pct); return 3 if r_ == len(ranks) - 1 and len(ranks) > 1 else min(2, r_)
        for i, p in enumerate(self.pz):
            pct = int(num(p.get("pct"))); gone = p.get("left") is not None and num(p.get("left")) == 0
            if self.mys and self.luck: c1, c2 = self.LK_MYS[i % 2], self.LK_MYS_IN[i % 2]
            elif self.luck: c1, c2 = self.LK[lkr(pct)]
            elif self.mys: c1, c2 = self.MYS[i % 2], self.MYS_IN[i % 2]
            elif gone: c1, c2 = self.GONE, self.GONE_IN
            elif pct >= 40: c1, c2 = self.HI, self.HI_IN
            elif pct >= 20: c1, c2 = self.MID, self.MID_IN
            else: c1, c2 = self.LO[lo % 2], self.LO_IN[lo % 2]; lo += 1
            st = 90 - ((i - .5) * seg + self.rot) - seg                    # ô i: giữa ô ở góc i·seg + rot, tính theo chiều kim đồng hồ từ 12 giờ
            for rr, t in ((R, 0), (R * .89, .2), (R * .78, .4), (R * .67, .6), (R * .56, .8), (R * .45, 1)):
                cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=st, extent=seg, fill=wheel_mix(c1, c2, t), outline="", style="pieslice", tags=T)
        for i in range(n):                                                 # vạch chia + đinh tán
            a = math.radians((i - .5) * seg + self.rot)
            cv.create_line(cx, cy, cx + R * math.sin(a), cy - R * math.cos(a), fill="#b9c6de", width=1, tags=T)
            b = math.radians((i + .5) * seg + self.rot); x, y = cx + 80 * k * math.sin(b), cy - 80 * k * math.cos(b)
            cv.create_oval(x - 1.6 * k, y - 1.6 * k, x + 1.6 * k, y + 1.6 * k, fill=W_PEARL, outline=W_INK, tags=T)
        if not self.mys and 0 <= self.win_i < n:                           # ô vừa trúng: viền sáng
            st = 90 - ((self.win_i - .5) * seg + self.rot) - seg
            cv.create_arc(cx - R + 2, cy - R + 2, cx + R - 2, cy + R - 2, start=st, extent=seg, outline="#ffffff", width=max(2, round(1.8 * k)), style="pieslice", tags=T)
        fs = -int(15.5 * k * (1 if n <= 8 else .92 if n <= 10 else .8))
        for i, p in enumerate(self.pz):
            pct = int(num(p.get("pct"))); gone = p.get("left") is not None and num(p.get("left")) == 0; a = i * seg + self.rot; ar = math.radians(a)
            ang = (-a) % 360
            if self.mys:
                x, y = cx + 54 * k * math.sin(ar), cy - 54 * k * math.cos(ar)
                cv.create_text(x, y, text="?", angle=ang, font=("Segoe UI", -int(19 * k), "bold"), fill="#dfe9ff", tags=T)
                continue
            rr = 58 * k if gone else 54 * k; x, y = cx + rr * math.sin(ar), cy - rr * math.cos(ar)
            ink = ("#2a1c00" if lkr(pct) == 0 else "#effff9") if self.luck else "#6f7da3" if gone else W_INK if pct >= 40 else "#eef4ff"
            cv.create_text(x, y, text=f"{pct}%", angle=ang, font=("Segoe UI", fs, "bold"), fill=ink, tags=T)
            if gone:
                x2, y2 = cx + 42 * k * math.sin(ar), cy - 42 * k * math.cos(ar)
                cv.create_text(x2, y2, text="HẾT", angle=ang, font=("Segoe UI", -int(7 * k), "bold"), fill="#8a95b8", tags=T)
        cv.tag_raise("over")

    def _bulbs(self):
        """Đèn viền: lúc chờ nhấp nháy chậm, lúc quay chạy đuổi nhanh."""
        if not self.alive or self.cv is None or not self.cv.winfo_exists(): return
        self.t_bulb += 1; fast = self.busy
        for i, (h, c) in enumerate(self.bulb_ids):
            lit = ((self.t_bulb + i) % 2 == 0) if fast else ((self.t_bulb // 5 + i) % 2 == 0)
            try:
                self.cv.itemconfig(h, fill="#ffe6a0" if lit else "#c6cfdf")
                self.cv.itemconfig(c, fill="#fffdf4" if lit else "#7c8496", outline="#f0c35a" if lit else "#5f677a")
            except Exception: return
        self.win.after(90 if fast else 130, self._bulbs)

    # ---------------------------------------------------------------- hướng dẫn · mã của tôi · thể lệ
    def fill_guide(self):
        tk = self.app.tk; f = self.guide_f
        for w in f.winfo_children(): w.destroy()
        s = self.st or {}; a, n = wheel_first(s); sp = wheel_per(s); days = int(num(s.get("days")) or 7)
        self.label(f, "📖 Hướng dẫn chơi", ("Segoe UI", 11, "bold"), W_PEARL).pack(fill="x", pady=(0, 4))
        steps = [("💳", f"Nạp {vnd(a)} = {n} lượt", f"Cứ {vnd(s.get('per'))} nạp được {sp} lượt quay miễn phí. Nạp ngân hàng hay crypto đều tính."),
                 ("🎡", "Bấm QUAY", "Đang quay, số trên vòng ẩn hết. Kim dừng là hộp quà nổ ra mã của bạn."),
                 ("🏷", "Dùng mã khi thanh toán", f"Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy. Mã dùng 1 lần, hạn {days} ngày.")]
        if num(s.get("price")) > 0:
            steps.append(("➕", f"Mua lượt {vnd(s.get('price'))}",
                          ("Hết lượt miễn phí vẫn quay tiếp được." if s.get("need_topup") else f"Không cần nạp đủ {vnd(a)} — có số dư là mua được.")
                          + (f" Lượt mua trúng mã {wheel_pcts(s.get('paid_pcts'))}." if s.get("paid_max") is not None else "") + " Luôn hỏi lại trước khi trừ tiền."))
        k = wheel_lucky(s)
        if k: steps.append(("🍀", f"Vé may mắn {vnd(k['price'])}", wheel_lucky_line(k) + ". Vòng đổi sang mặt vé riêng, trừ vào số dư, luôn hỏi lại trước khi trừ."))
        grid = tk.Frame(f, bg=W_DEEP); grid.pack(fill="x")
        for i, (ic, t, d) in enumerate(steps):
            c = tk.Frame(grid, bg=W_TILE, highlightbackground=W_EDGE, highlightthickness=1)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 4) if i % 2 == 0 else (4, 0), pady=3)
            tk.Label(c, text=ic, font=("Segoe UI", 12), fg="#ffffff", bg="#2f66ec", width=2).pack(side="left", anchor="n", padx=8, pady=8)
            tx = tk.Frame(c, bg=W_TILE); tx.pack(side="left", fill="both", expand=True, pady=6, padx=(0, 8))
            tk.Label(tx, text=t, font=("Segoe UI", 9, "bold"), fg="#ffffff", bg=W_TILE, anchor="w", justify="left", wraplength=self.px(185)).pack(fill="x")
            tk.Label(tx, text=d, font=("Segoe UI", 8), fg=W_SUB, bg=W_TILE, anchor="w", justify="left", wraplength=self.px(185)).pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="g"); grid.grid_columnconfigure(1, weight=1, uniform="g")
        self.label(f, "🌐 Chơi được cả trên web (vòng quay ngay trang chủ) và app Android (bản tải từ web). "
                      "Lượt quay, vé và mã dùng chung cho cả tài khoản.", self.app.f_s, W_SUB, wraplength=self.px(500)).pack(fill="x", pady=(6, 0))

    def fill_mine(self):
        tk = self.app.tk; f = self.mine_f
        for w in f.winfo_children(): w.destroy()
        cs = (self.st or {}).get("codes") or []
        self.label(f, "🎟 Mã của tôi", ("Segoe UI", 11, "bold"), W_PEARL).pack(fill="x", pady=(0, 4))
        if not cs: self.label(f, "Mã bạn quay trúng sẽ nằm ở đây.", self.app.f_s, W_SUB).pack(fill="x"); return
        now = now_utc()
        for c in cs[:12]:
            exp = parse_iso(c.get("expires_at")); used = bool(c.get("used")); act = c.get("active", True) is not False; gone = exp is not None and exp <= now
            live = not used and act and not gone
            st = ("Đã dùng" if used else "Đã tắt" if not act else "Hết hạn" if gone else "Dùng được đến " + (exp.astimezone().strftime("%H:%M %d/%m") if exp else ""))
            if c.get("lucky"): st += f"  ·  🍀 vé {vnd(c.get('paid'))}"
            elif num(c.get("paid")) > 0: st += f"  ·  lượt mua {vnd(c.get('paid'))}"
            if live and c.get("share"): st += "  ·  🤝 tặng bạn bè được"
            r = tk.Frame(f, bg="#111b4c", highlightbackground="#26345f", highlightthickness=1); r.pack(fill="x", pady=2)
            big = num(c.get("pct")) >= 40
            tk.Label(r, text=f"{int(num(c.get('pct')))}%", font=("Segoe UI", 10, "bold"), fg=W_INK if big else "#ffffff",
                     bg=(W_PEARL2 if big else "#2f66ec") if live else "#2c3352", width=5).pack(side="left", padx=8, pady=6)
            if live: self.app.btn(r, "Chép", lambda v=str(c.get("code")): self.copy(v), "soft", padx=10, pady=2).pack(side="right", padx=8)
            tx = tk.Frame(r, bg="#111b4c"); tx.pack(side="left", fill="x", expand=True)
            tk.Label(tx, text=str(c.get("code")), font=("Consolas", 10, "bold"), fg="#ffffff" if live else "#7f8bab", bg="#111b4c", anchor="w").pack(fill="x")
            tk.Label(tx, text=st, font=("Segoe UI", 8), fg=W_SUB if live else "#6c779a", bg="#111b4c", anchor="w").pack(fill="x")

    def copy(self, v):
        try: self.app.root.clipboard_clear(); self.app.root.clipboard_append(v)
        except Exception: pass
        try: self.err_l.config(text=f"✓ Đã chép mã {v}", fg=OK)
        except Exception: pass

    def toggle_rules(self):
        self.rules_open = not self.rules_open
        self.rules_b.config(text="📜 Thể lệ  " + ("▾" if self.rules_open else "▸"))
        if self.rules_open: self.rules_f.pack(fill="x", padx=18, pady=(0, 16), after=self.rules_b)
        else: self.rules_f.pack_forget()

    def fill_rules(self):
        f = self.rules_f
        for w in f.winfo_children(): w.destroy()
        s = self.st or {}; sp = wheel_per(s); per = int(num(s.get("per")) or 100000); mn = vnd(s.get("min")); wl = self.px(500)
        lines = [f"⏰ Thời gian: từ {wheel_when(s.get('starts_at'))}" + (f" đến {wheel_when(s.get('ends_at'))}." if s.get("ends_at") else " đến khi có thông báo kết thúc."),
                 f"💳 Mỗi lệnh nạp thành công từ {mn} trong thời gian chương trình: cứ {vnd(per)} = {sp} lượt quay (ví dụ nạp {vnd(per * 2.5)} = {2 * sp} lượt). "
                 "Tính nạp ngân hàng và crypto; nạp qua Google Play không tính lượt."]
        if num(s.get("price")) > 0:
            lines.append(f"➕ Mua lượt: {vnd(s.get('price'))}/lượt, trừ vào số dư" + (f", dành cho tài khoản đã nạp từ {mn} trong chương trình" if s.get("need_topup") else "")
                         + (f", tối đa {int(num(s.get('buy_max')))} lượt mua + vé/ngày" if num(s.get("buy_max")) > 0 else "") + "."
                         + (f" Lượt mua chỉ trúng mã {wheel_pcts(s.get('paid_pcts'))}; mã lớn hơn có ở lượt nạp tiền" + (" và vé may mắn" if wheel_lucky(s) else "") + "."
                            if s.get("paid_max") is not None else "") + " Luôn hỏi lại trước khi trừ tiền.")
        k = wheel_lucky(s)
        if k:
            odds = " · ".join(f"mã {p['pct']}%: {wheel_rate(p['rate'])}%" for p in sorted(k["pool"], key=lambda x: -x["pct"]))
            lines.append(f"🍀 Vé may mắn: {vnd(k['price'])}/vé = 1 lượt quay riêng (không dùng lượt miễn phí), trừ vào số dư. Tỷ lệ công khai: {odds}. Mã từ vé không giới hạn số lượng.")
        lines += [f"🎟 Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn {int(num(s.get('days')) or 7)} ngày, " + ("giữ dùng sau hoặc tặng bạn bè dùng đều được" if s.get("share") else "chỉ tài khoản quay trúng dùng được")
                  + (f", giảm tối đa {vnd(s.get('max_disc'))}" if num(s.get("max_disc")) > 0 else "") + ".",
                  "🎲 Kết quả quay hoàn toàn ngẫu nhiên do máy chủ quyết định. Mỗi ô có tỷ lệ trúng khác nhau — giải càng lớn càng hiếm. "
                  "Giải có số lượng giới hạn; ô ghi HẾT là đã có người trúng hết."]
        for t in lines: self.label(f, t, self.app.f_s, W_SUB, wraplength=wl).pack(fill="x", pady=2)
        tb = self.app.tk.Frame(f, bg=W_TILE, highlightbackground=W_EDGE, highlightthickness=1); tb.pack(fill="x", pady=(6, 0))
        for p in sorted(s.get("prizes") or [], key=lambda x: -num(x.get("pct"))):
            r = self.app.tk.Frame(tb, bg=W_TILE); r.pack(fill="x", padx=10, pady=1)
            self.label(r, f"Mã giảm {int(num(p.get('pct')))}%", self.app.f_s, TXT).pack(side="left")
            self.label(r, "Không giới hạn" if p.get("stock") is None else f"{int(num(p.get('stock')))} giải · còn {int(num(p.get('left')))}", self.app.f_s, W_SUB).pack(side="right")


class RevealWin:
    """Cửa sổ mở quà: nền sapphire sâu · hộp quà rơi, rung, NỔ (nắp bay, chớp sáng, tia sáng xoay, pháo giấy rơi + bong bóng bay) → thẻ mã."""

    def __init__(self, dlg, r):
        app = dlg.app; tk = app.tk; self.sc = sc = dlg.sc; self.W, self.H = int(460 * sc), int(620 * sc)
        self.dlg = dlg; self.r = r; self.alive = True; self.big = num(r.get("pct")) >= 40
        self.win = w = tk.Toplevel(dlg.win); w.title("🎁 Chúc mừng!"); w.configure(bg=W_REV); w.resizable(False, False)
        dlg.win.update_idletasks()
        x = dlg.win.winfo_rootx() + (dlg.win.winfo_width() - self.W) // 2; y = dlg.win.winfo_rooty() + 20
        w.geometry(f"{self.W}x{self.H}+{max(0, x)}+{max(0, y)}"); w.transient(dlg.win)
        w.protocol("WM_DELETE_WINDOW", self.close); w.bind("<Escape>", lambda e: self.close())
        self.cv = cv = tk.Canvas(w, width=self.W, height=self.H, bg=W_REV, highlightthickness=0); cv.pack(fill="both", expand=True)
        cx, cy = self.W / 2, self.H * .46
        for i in range(18, 0, -1):                                          # nền: quầng xanh sâu ở giữa (radial-gradient #16327a → #060b1d)
            rr = (14 + i * 22) * sc; cv.create_oval(cx - rr * 1.05, cy - rr * .92, cx + rr * 1.05, cy + rr * .92, fill=wheel_mix("#16327a", W_REV, i / 18), outline="")
        self.rays = [cv.create_polygon(cx, cy, cx, cy, cx, cy, fill="#16327a", outline="", state="hidden") for _ in range(18)]
        self.flash = cv.create_oval(cx, cy, cx, cy, fill="#ffffff", outline="", state="hidden")
        self.waves = [cv.create_oval(cx, cy, cx, cy, outline="#ffffff", width=1, state="hidden") for _ in range(2)]
        self.card = self.make_card(); self.card_id = None
        self.parts = []; self.t0 = time.time(); self.tb = None; self.cx, self.cy = cx, cy
        cv.bind("<Button-1>", self._bg_click)
        w.after(60, self._grab); self._frame()

    def _grab(self):
        try: self.win.grab_set(); self.win.focus_force()
        except Exception: pass

    def _bg_click(self, e):
        if self.tb is not None and (time.time() - self.tb) > .8: self.close("done")      # bấm ra ngoài thẻ (sau khi thẻ hiện) = Xong

    def make_card(self):
        tk = self.dlg.app.tk; r = self.r; big = self.big; app = self.dlg.app; bg = "#15215c"
        c = tk.Frame(self.cv, bg=bg, highlightbackground=W_PEARL2 if big else "#5a6c9c", highlightthickness=2 if big else 1)
        if r.get("lucky"): tk.Label(c, text=" 🍀 Vé may mắn ", font=("Segoe UI", 9, "bold"), fg="#03261b", bg="#5cf0c2").pack(pady=(14, 0))
        tk.Label(c, text=("🎉 " if big else "🎁 ") + "Chúc mừng! Bạn nhận được", font=("Segoe UI", 11, "bold"), fg=W_SKY, bg=bg).pack(pady=(8 if r.get("lucky") else 18, 0))
        tk.Label(c, text=f"−{int(num(r.get('pct')))}%", font=("Segoe UI", 46, "bold"), fg=W_PEARL, bg=bg).pack()
        tk.Label(c, text="mã giảm giá", font=("Segoe UI", 11, "bold"), fg=W_SUB, bg=bg).pack(pady=(0, 10))
        cr = tk.Frame(c, bg=bg); cr.pack()
        tk.Label(cr, text=str(r.get("code")), font=("Consolas", 15, "bold"), fg="#ffffff", bg="#060a1c", padx=12, pady=6).pack(side="left")
        self.cp = app.btn(cr, "Chép mã", self.copy, "soft", padx=10, pady=6); self.cp.pack(side="left", padx=(8, 0))
        exp = parse_iso(r.get("expires_at")); exp = exp.astimezone().strftime("%H:%M %d/%m/%Y") if exp else ""
        tk.Label(c, text=f"Dùng 1 lần · hạn đến {exp} · " + ("giữ dùng sau hoặc tặng bạn bè dùng đều được" if r.get("share") else "chỉ tài khoản của bạn dùng được")
                         + ". Nhập ở ô 🏷️ Mã giảm giá khi thuê / gia hạn máy.",
                 font=("Segoe UI", 9), fg=W_SUB, bg=bg, justify="center", wraplength=self.W - int(110 * self.sc)).pack(padx=16, pady=(10, 0))
        if num(r.get("paid")) > 0:
            tk.Label(c, text=f"Đã trừ {vnd(r.get('paid'))} · số dư còn {vnd(r.get('balance'))}", font=("Segoe UI", 9), fg=W_SUB, bg=bg).pack(pady=(4, 0))
        s = self.dlg.st or {}; lk = bool(r.get("lucky")); left = 0 if lk else int(num(s.get("left"))); buy = not lk and left <= 0 and bool(s.get("can_buy"))
        k = wheel_lucky(s); more = lk and k is not None and s.get("can_lucky") is not False
        bb = tk.Frame(c, bg=bg); bb.pack(fill="x", padx=18, pady=(14, 16))
        if left > 0: app.btn(bb, f"🎡 Quay tiếp · còn {left} lượt", lambda: self.close("again"), pady=9).pack(fill="x")
        elif buy:
            b = app.btn(bb, f"➕ Quay thêm · {vnd(s.get('price'))}", lambda: self.close("buy"), pady=9)
            b.config(bg=W_PEARL2, fg=W_INK, activebackground="#ffffff", activeforeground=W_INK); b.pack(fill="x")
        elif more:
            b = app.btn(bb, f"🍀 Dùng thêm vé · {vnd(k['price'])}", lambda: self.close("lucky"), pady=9)
            b.config(bg="#2fd9a6", fg="#03261b", activebackground="#5cf0c2", activeforeground="#03261b"); b.pack(fill="x")
        x = app.btn(bb, "Xong", lambda: self.close("done"), "soft" if left > 0 or buy or more else "primary", pady=8); x.pack(fill="x", pady=(6, 0))
        if left > 0 or buy or more: x.config(bg="#24357a", activebackground="#33489a")
        return c

    def copy(self):
        try: self.dlg.app.root.clipboard_clear(); self.dlg.app.root.clipboard_append(str(self.r.get("code")))
        except Exception: pass
        try: self.cp.config(text="✓ Đã chép")
        except Exception: pass

    def close(self, what="done"):
        if not self.alive: return
        self.alive = False
        try: self.win.grab_release()
        except Exception: pass
        try: self.win.destroy()
        except Exception: pass
        self.dlg.after_reveal(what)

    def _burst(self):
        self.tb = time.time(); n = 150 if self.big else 110; cx, cy = self.cx, self.cy + 30 * self.sc; sc = self.sc
        cols = ["#ffffff", W_PEARL, W_PEARL2, W_SKY, "#3d7bff", "#ffe7a8"] if self.big else [W_SKY, "#3d7bff", W_PEARL, W_PEARL2, "#3ce0b0"]
        rnd = secrets.SystemRandom()
        for i in range(n):
            a = rnd.random() * math.pi * 2; sp = (3 + rnd.random() * (10 if self.big else 8)) * sc; bub = rnd.random() < .28
            q = {"x": cx, "y": cy, "vx": math.cos(a) * sp, "vy": math.sin(a) * sp - (3 + rnd.random() * 3) * sc, "rot": rnd.random() * 6,
                 "vr": (rnd.random() - .5) * .4, "w": (4 + rnd.random() * 5) * sc, "h": (7 + rnd.random() * 7) * sc, "bub": bub}
            col = cols[i % len(cols)]
            q["id"] = (self.cv.create_oval(cx, cy, cx, cy, outline=col, width=max(1, round(1.6 * sc))) if bub
                       else self.cv.create_polygon(cx, cy, cx, cy, cx, cy, cx, cy, fill=col, outline=""))
            self.parts.append(q)
        for it in self.rays + self.waves + [self.flash]: self.cv.itemconfig(it, state="normal")

    def _frame(self):
        if not self.alive: return
        try:
            if not self.win.winfo_exists(): self.alive = False; return
        except Exception: self.alive = False; return
        cv = self.cv; now = time.time(); t = (now - self.t0) * 1000; cx, cy, sc = self.cx, self.cy, self.sc
        if self.tb is None and t >= 1250: self._burst()
        b = None if self.tb is None else (now - self.tb) * 1000
        if b is not None:                                                    # tia sáng xoay chậm
            s = min(1.0, b / 900); rr = 300 * sc * (.25 + .75 * s); rot = (now % 24) / 24 * 360
            for i, ray in enumerate(self.rays):
                a0, a1 = math.radians(i * 20 + rot), math.radians(i * 20 + 9 + rot)
                cv.coords(ray, cx, cy, cx + rr * math.cos(a0), cy + rr * math.sin(a0), cx + rr * math.cos(a1), cy + rr * math.sin(a1))
                if b < 950: cv.itemconfig(ray, fill=wheel_mix(W_REV, "#2a4fae" if i % 2 else "#1d3a8c", s))
        cv.delete("gift"); self._gift(t, b); cv.tag_lower("gift", self.flash)
        if b is not None:                                                    # chớp sáng: lõi trắng loé 0,14 giây + 2 vòng sóng nổ lan ra rồi tắt
            if b < 140:
                rr = (30 + 60 * b / 140) * sc; cv.coords(self.flash, cx - rr, cy - rr, cx + rr, cy + rr); cv.itemconfig(self.flash, fill="#ffffff" if b < 70 else "#dff1ff")
            else: cv.itemconfig(self.flash, state="hidden")
            for j, wv in enumerate(self.waves):
                u = (b - j * 110) / 520
                if 0 <= u <= 1:
                    rr = (40 + 250 * (1 - (1 - u) ** 2)) * sc; cv.coords(wv, cx - rr, cy - rr, cx + rr, cy + rr)
                    cv.itemconfig(wv, width=max(1, round((9 - 8 * u) * sc)), outline=wheel_mix("#ffffff", "#3d7bff", u), state="normal")
                else: cv.itemconfig(wv, state="hidden")
        if b is not None and self.parts:                                     # pháo giấy rơi · bong bóng bay lên (~3 giây)
            if b > 3300:
                for q in self.parts: cv.delete(q["id"])
                self.parts = []
            else:
                shrink = max(0.0, 1 - max(0.0, b - 1900) / 1400)
                for q in self.parts:
                    q["vx"] *= .982
                    q["vy"] = q["vy"] * .965 - .06 * sc if q["bub"] else q["vy"] * .985 + .24 * sc
                    q["x"] += q["vx"]; q["y"] += q["vy"]; q["rot"] += q["vr"]
                    if q["bub"]:
                        rr = q["w"] * .7 * shrink; cv.coords(q["id"], q["x"] - rr, q["y"] - rr, q["x"] + rr, q["y"] + rr)
                    else:
                        f = abs(math.cos(q["rot"] * 1.7)); w2, h2 = q["w"] / 2, max(.5, q["h"] * f / 2); ca, sa = math.cos(q["rot"]), math.sin(q["rot"])
                        cv.coords(q["id"], *[v for dx, dy in ((-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2)) for v in (q["x"] + dx * ca - dy * sa, q["y"] + dx * sa + dy * ca)])
        if b is not None and b >= 300:                                       # thẻ mã bật ra (trượt lên) sau khi nổ
            u = min(1.0, (b - 300) / 380); e = 1 - (1 - u) ** 3; y = cy + 40 * sc * (1 - e)
            if self.card_id is None: self.card_id = cv.create_window(cx, y, window=self.card, width=self.W - int(56 * sc))
            else: cv.coords(self.card_id, cx, y)
        self.win.after(16 if b is None or b < 3400 else 50, self._frame)

    def _gift(self, t, b):
        """Hộp quà: rơi xuống (0–0,42 giây) · rung 3 nhịp · nổ: nắp bay lên xoay, thân hộp rơi xuống mờ dần."""
        cv = self.cv; sc = self.sc; cx, cy = self.cx, self.cy + 30 * sc
        drop = min(1.0, t / 420); ease = 1 - (1 - drop) ** 3; y0 = cy - 80 * sc * (1 - ease); k = 1.25 * sc * (.55 + .45 * ease)
        ang = math.radians(8 * math.sin((t - 500) / 260 * 2 * math.pi)) if b is None and 500 < t < 1280 else 0.0
        lid = (0.0, 0.0, 0.0, 1.0); body = (0.0, 1.0)
        if b is not None:
            u = min(1.0, b / 750); e2 = 1 - (1 - u) ** 3; lid = (-34 * e2, -220 * e2, math.radians(-40 * e2), 1 - u)
            v = max(0.0, min(1.0, (b - 120) / 520)); body = (60 * v * v, 1 - v)
        top, bot, rib, bow = ("#ffffff", W_PEARL2, "#3d7bff", "#3d7bff") if self.big else ("#5a95ff", "#2a5fe0", W_PEARL, W_PEARL)
        def poly(pts, dx, dy, rot, fill):
            c, s_ = math.cos(rot), math.sin(rot); out = []
            for x, y in pts:
                x, y = x * c - y * s_, x * s_ + y * c; out += [cx + (x + dx) * k, y0 + (y + dy) * k]
            cv.create_polygon(out, fill=fill, outline="", tags=("gift",))
        if body[1] > 0:
            m = lambda col: wheel_mix(W_REV, col, body[1])
            poly([(-60, -44), (60, -44), (60, 46), (-60, 46)], 0, body[0], ang, m(bot))
            poly([(-60, -44), (60, -44), (60, -12), (-60, -12)], 0, body[0], ang, m(top))
            poly([(-10, -44), (10, -44), (10, 46), (-10, 46)], 0, body[0], ang, m(rib))
        if lid[3] > 0:
            m = lambda col: wheel_mix(W_REV, col, lid[3]); ox, oy, rot = lid[0], -44 - 15 + lid[1], ang + lid[2]
            poly([(-70, -15), (70, -15), (70, 15), (-70, 15)], ox, oy, rot, m("#ffffff" if self.big else "#7aaeff"))
            poly([(-10, -15), (10, -15), (10, 15), (-10, 15)], ox, oy, rot, m(rib))
            for side in (-1, 1):                                              # nơ: 2 vòng bầu dục nghiêng
                tilt = math.radians(26 * side); loop = []
                for j in range(18):
                    q = j * math.pi / 9; ex, ey = 16 * math.cos(q), 10 * math.sin(q)
                    loop.append((side * 17 + ex * math.cos(tilt) - ey * math.sin(tilt), -15 - 9 + ex * math.sin(tilt) + ey * math.cos(tilt)))
                poly(loop, ox, oy, rot, m(bow))
                poly([(side * 17 + (x - side * 17) * .5, -24 + (y + 24) * .5) for x, y in loop], ox, oy, rot, m("#15215c"))
            poly([(-6, -30), (6, -30), (6, -18), (-6, -18)], ox, oy, rot, m(bow))


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


# ================= 🎞 16/11 · KHÁCH TỰ ĐỔI FPS (SQL doi-fps-1611 → cloudphone_set_fps) =================
FPS_PICK = [15, 20, 30, 45, 60, 90, 120]
def fps_tip(v):
    return "tiết kiệm nhất" if v < 20 else "mạng yếu" if v < 30 else "treo game" if v <= 30 else "cân bằng" if v <= 45 else "mượt" if v <= 60 else "rất mượt"


class FpsDlg(Dlg):
    """Đổi FPS của máy đang thuê: cùng máy đó, giữ nguyên dữ liệu, không tốn tiền. Hình truyền về đổi ở lần mở máy kế tiếp;
       máy Android 12 · 15 cần khởi động lại 1 lần để FPS mới có tác dụng trong game (máy chủ trả reboot = true → hỏi khách)."""
    def __init__(self, app, phone):
        super().__init__(app, "Đổi FPS — " + (phone.get("name") or "máy"), 560, 520)
        self.p = phone; self.cur = int(num(phone.get("fps")) or 30); self.v = self.cur; self.busy = False
        self.loading("Đang tải…")
        self.bg(lambda: app.shop.pricing(), self._loaded, lambda m: self.loading(m))

    def _loaded(self, pr):
        tk = self.app.tk; p = self.p; self.clear()
        small = int(num(p.get("cpu"))) < 4
        lo = int(num(pr.get("min_fps")) or 10); hi = min(int(num(pr.get("max_fps")) or 60), 60 if small else 120)
        opts = sorted({x for x in FPS_PICK if lo <= x <= hi} | {self.cur})
        self.label(self.body, p.get("name") or "Máy", self.app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.label(self.body, f"Android {p.get('android') or '9'} · {p.get('ram')}GB · {p.get('cpu')} nhân · đang dùng {self.cur} FPS",
                   self.app.f_t, DIM, wraplength=500).pack(fill="x", padx=18)
        s = self.section("Số khung hình mỗi giây")
        self.cv = Chips(self.app, s, [(x, f"{x} FPS\n{fps_tip(x)}") for x in opts], lambda: self.v, lambda x: setattr(self, "v", x), self.upd, wrap=4)
        self.cv.frame.pack(fill="x")
        self.label(self.body, "FPS càng cao hình càng mượt nhưng máy chạy nặng hơn và tốn mạng hơn. Treo game cả ngày nên để 30 FPS (mạng yếu: 20 FPS)."
                   + (" Máy dưới 4 nhân chọn tối đa 60 FPS." if small else ""), self.app.f_s, DIM, wraplength=510).pack(fill="x", padx=18, pady=(8, 0))
        self.label(self.body, "✔ Không tạo máy mới · không mất dữ liệu · không tốn tiền.", self.app.f_s, OK, wraplength=510).pack(fill="x", padx=18, pady=(4, 12))
        self.err = self.label(self.foot, "", self.app.f_s, BAD, wraplength=500); self.err.pack(fill="x", padx=16, pady=(8, 0))
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=(6, 12))
        self.app.btn(bb, "Đóng", self.close, "soft").pack(side="left")
        self.go = self.app.btn(bb, "Lưu", self.save); self.go.pack(side="right")
        self.upd()

    def upd(self):
        self.cv.paint()
        ch = self.v != self.cur and not self.busy
        self.go.config(text="Đang lưu…" if self.busy else f"Lưu {self.v} FPS" if self.v != self.cur else "Chọn số FPS khác để đổi",
                       state="normal" if ch else "disabled", bg=ACC if ch else LINE)

    def save(self):
        if self.busy or self.v == self.cur: return
        v = self.v; self.busy = True; self.err.config(text=""); self.upd()
        def done(r):
            self.busy = False; self.p["fps"] = v; self.cur = v; self.app.refresh(quiet=True)
            if isinstance(r, dict) and r.get("reboot"): return self._ask_reboot(v)
            import tkinter.messagebox as mb
            self.close()
            mb.showinfo("CloudBlue", f"Đã đổi sang {v} FPS — mở lại cửa sổ máy là thấy.", parent=self.app.root)
        def fail(m):
            self.busy = False; self.err.config(text=m); self.upd()
        self.bg(lambda: self.app.auth.rpc("cloudphone_set_fps", {"p_id": self.p["id"], "p_fps": v}), done, fail)

    def _ask_reboot(self, v):
        """Đã lưu FPS mới mà máy cần khởi động lại 1 lần (Android 12 · 15) → khởi động lại ngay, hay để sau (lần bật kế tiếp tự áp dụng)."""
        tk = self.app.tk; self.clear()
        self.label(self.body, f"✅ Đã lưu {v} FPS", self.app.f_h2, OK).pack(fill="x", padx=18, pady=(18, 0))
        self.label(self.body, "Hình truyền về đổi ngay ở lần mở máy kế tiếp.", self.app.f_t, TXT, wraplength=510).pack(fill="x", padx=18, pady=(4, 0))
        self.label(self.body, "Để FPS mới có tác dụng BÊN TRONG GAME, máy cần khởi động lại 1 lần (khoảng 1–2 phút). App đang mở trong máy sẽ tắt, "
                              "dữ liệu giữ nguyên. Chưa tiện thì để sau — lần máy bật lại kế tiếp sẽ tự áp dụng.", self.app.f_t, DIM, wraplength=510).pack(fill="x", padx=18, pady=(10, 0))
        self.st = self.label(self.body, "", self.app.f_t, ACC, wraplength=510); self.st.pack(fill="x", padx=18, pady=(12, 12))
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=12)
        self.b_later = self.app.btn(bb, "Để sau", self.close, "soft"); self.b_later.pack(side="left")
        self.b_now = self.app.btn(bb, "⚡ Khởi động lại ngay", self._reboot); self.b_now.pack(side="right")

    def _reboot(self):
        self.b_now.config(state="disabled", bg=LINE); self.st.config(text="Đang khởi động lại máy… (1–2 phút, có thể đóng hộp này)", fg=ACC)
        cp = CpClient(self.app.auth, self.p["id"])
        def job():
            j = cp.json("POST", "reboot", {}, timeout=60)
            if not j.get("job"): return "Máy đang khởi động lại — khoảng 1–2 phút."
            return cp.wait_job(j["job"], lambda m: self.app.ui(lambda: self.alive and self.st.config(text=str(m))), limit=420)
        def done(m):
            self.st.config(text="✅ " + str(m), fg=OK); self.b_later.config(text="Xong"); self.app.refresh(quiet=True)
        def fail(m):
            self.st.config(text="Chưa khởi động lại được: " + str(m), fg=BAD); self.b_now.config(state="normal", bg=ACC)
        self.bg(job, done, fail)


class LookDlg(Dlg):
    """16/11 · 🎨 Giao diện: thanh chỉnh CỠ CHỮ 80–130% (bấm Áp dụng → app mở lại với cỡ mới, nhớ theo máy) · ẩn / hiện ô ưu đãi đầu danh sách."""
    def __init__(self, app):
        super().__init__(app, "Giao diện", 520, 520)
        tk = app.tk; self.cur = ui_scale()
        self.label(self.body, "🔍 Cỡ chữ của app", app.f_h2).pack(fill="x", padx=18, pady=(16, 0))
        self.val = self.label(self.body, "", app.f_t, TXT); self.val.pack(fill="x", padx=18, pady=(4, 0))
        self.var = tk.IntVar(value=self.cur)
        self.sc = tk.Scale(self.body, from_=UI_MIN, to=UI_MAX, resolution=UI_STEP, orient="horizontal", variable=self.var, showvalue=False,
                           command=lambda *_: self.upd(), bg=ACC, fg=TXT, troughcolor=LINE, activebackground="#4b8cff", highlightthickness=0, bd=0,
                           sliderlength=34, width=18, sliderrelief="flat", cursor="hand2")
        self.sc.pack(fill="x", padx=18, pady=(6, 0))
        ends = tk.Frame(self.body, bg=BG); ends.pack(fill="x", padx=18)
        self.label(ends, f"nhỏ {UI_MIN}%", app.f_s, DIM).pack(side="left"); self.label(ends, f"to {UI_MAX}%", app.f_s, DIM).pack(side="right")
        box = tk.Frame(self.body, bg=CARD, highlightbackground=LINE, highlightthickness=1); box.pack(fill="x", padx=18, pady=(10, 0))
        self.demo = tk.Label(box, text="Chữ mẫu: Máy 6GB · 6 nhân · 60 FPS", fg=TXT, bg=CARD, anchor="w"); self.demo.pack(fill="x", padx=12, pady=10)
        self.label(self.body, "Kéo sang phải cho chữ TO hơn, sang trái cho NHỎ hơn rồi bấm Áp dụng. App sẽ tự mở lại cửa sổ danh sách với cỡ mới — "
                              "các cửa sổ máy đang mở không bị đóng.", app.f_s, DIM, wraplength=470).pack(fill="x", padx=18, pady=(8, 0))
        lr = tk.Frame(self.body, bg=BG); lr.pack(fill="x", padx=18, pady=(14, 0))            # 16/11c: 🌐 Tiếng Việt / English
        self.label(lr, "🌐 Ngôn ngữ · Language", app.f_h2).pack(side="left")
        for code, name in (("en", "English"), ("vi", "Tiếng Việt")):
            b = app.btn(lr, ("✓ " if LANG == code else "") + name, lambda c=code: self.app.set_lang(c), "soft" if LANG == code else "ghost")
            b.pack(side="right", padx=(6, 0))
            if LANG == code: b.config(state="disabled")
        self.pv = tk.BooleanVar(value=not prefs().get("promo_hide"))
        tk.Checkbutton(self.body, text="Hiện ô ưu đãi · vòng quay ở đầu danh sách máy", variable=self.pv, command=self.promo, font=app.f_t,
                       fg=TXT, bg=BG, selectcolor=CARD, activebackground=BG, activeforeground=TXT, anchor="w", cursor="hand2",
                       highlightthickness=0, bd=0).pack(fill="x", padx=14, pady=(14, 12))
        bb = tk.Frame(self.foot, bg=CARD); bb.pack(fill="x", padx=16, pady=12)
        app.btn(bb, "Đóng", self.close, "soft").pack(side="left")
        self.go = app.btn(bb, "Áp dụng", self.apply); self.go.pack(side="right")
        app.btn(bb, "Mặc định 100%", lambda: (self.var.set(100), self.upd()), "ghost").pack(side="right", padx=8)
        self.upd()

    def value(self):
        try: v = int(round(float(self.var.get()) / UI_STEP)) * UI_STEP
        except Exception: v = self.cur
        return max(UI_MIN, min(UI_MAX, v))

    def upd(self):
        v = self.value(); ch = v != self.cur
        self.val.config(text=f"{v}%" + (" (mặc định)" if v == 100 else "") + (f"  ·  đang dùng {self.cur}%" if ch else ""))
        self.demo.config(font=("Segoe UI", max(6, int(round(10 * v / self.cur)))))            # hộp này đang vẽ ở cỡ hiện tại → chữ mẫu theo tỉ lệ
        self.go.config(state="normal" if ch else "disabled", bg=ACC if ch else LINE)

    def promo(self):
        prefs({"promo_hide": not self.pv.get()}); self.app._promo_sig = None; self.app._paint_promo()

    def apply(self):
        v = self.value()
        if v == self.cur: return
        prefs({"ui_scale": v}); self.close(); self.app.restart_ui()


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
        self.muted(f, "Khoá màn máy NGANG hoặc DỌC (giữ luôn cả khi tắt app). Game chỉ chạy màn ngang vẫn tự xoay ngang. "
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
        self.muted(f, "Một số game và app có thể phát hiện máy đã root. Chỉ bật cho app thật sự cần.")
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
    # 🛡️ bảo mật (SQL v29)
    "BLUE_DAY_CAP": "Hôm nay bạn đã nhận đủ Blue tối đa — mai quay lại nhé.", "BLUE_HOLD": "Blue của bạn đang được tạm giữ để kiểm tra — liên hệ hỗ trợ.",
    "BLUE_NEW_ACCOUNT": "Tài khoản mới — sau 24 giờ mới tích Blue được.", "MONEY_GUARD": "Bị chặn: không được tự cộng tiền.", "BLUE_GUARD": "Bị chặn.",
    "MAX_AMOUNT": "Số tiền quá lớn.", "banned": "⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng (gian lận / cày clone / lợi dụng lỗi). Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.",
})
ERRORS.update({"FPS_NOT_ACTIVE": "Máy phải đang chạy mới đổi FPS được.", "FPS_WAIT": "Vừa đổi FPS xong — đợi vài giây rồi đổi tiếp nhé.",
               "cloudphone_set_fps": "Máy chủ chưa bật tính năng đổi FPS — thử lại sau ít phút."})                      # 16/11 · khách tự đổi FPS
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


UPD = {"info": None, "t": 0.0}                       # bản app mới hơn trên web (download/pc.json) — đọc tối đa 5 phút / lần


def fetch_update_info(force=False, timeout=8, with_min=True):
    """Bản app MỚI HƠN đang phát hành (dict của download/pc.json) hoặc None. Kèm bản tối thiểu admin đặt (settings.min_app_pc):
       cổng chặn app cũ vẫn cho đọc settings → app cũ bị chặn vẫn biết để hiện nút cập nhật. Bản chạy thử từ mã nguồn: luôn None."""
    if not FROZEN: return None
    if not force and time.time() - UPD["t"] < 300: return UPD["info"]
    if with_min:
        try:
            sel = urllib.parse.quote("min_app_pc:data->>min_app_pc,web:data->>web", safe=":,")     # chỉ lấy 2 ô cần (đỡ tốn băng thông)
            code, raw = http("GET", SB + "/rest/v1/settings?id=eq.1&select=" + sel, headers={"apikey": KEY}, timeout=timeout)
            rows = json.loads(raw.decode("utf-8") or "[]") if code == 200 else []
            d = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
            if d is not None: set_web(d.get("web")); OUTDATED["min"] = str(d.get("min_app_pc") or "").strip()
        except Exception as e: log("update check (settings):", e)
    try:
        code, raw = http("GET", WEB.rstrip("/") + "/download/pc.json", timeout=timeout)
        j = json.loads(raw.decode("utf-8") or "{}") if code == 200 else {}
        UPD["info"] = j if isinstance(j, dict) and int(num(j.get("code"))) > app_code() else None
        UPD["t"] = time.time()
    except Exception as e: log("update check:", e)
    return UPD["info"]


def update_claim(ttl=600):
    """Chỉ 1 nơi được TỰ mở trình cập nhật trong 10 phút (mở nhiều cửa sổ máy cùng lúc / cập nhật lỗi rồi mở lại app → không lặp)."""
    p = os.path.join(DATA, "update.claim")
    try:
        if time.time() - os.path.getmtime(p) < ttl: return False
        os.remove(p)
    except OSError: pass
    try: os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)); return True
    except OSError: return False


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


def run_finish_update(install, wait_pid, test_out=None, open_id=None):
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
                    try: launch_app(exe, "--updated", *([f"blueroblox://phone/{open_id}"] if open_id else []))   # mở lại máy đang dùng
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
    def __init__(self, app, info, auto=False):
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
        if auto and self.auto: app.root.after(400, self.start)                 # app quá cũ / bấm cập nhật từ cửa sổ máy → tải luôn, khỏi bấm thêm

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
            ro = getattr(self.app, "reopen_id", None)
            try: launch_app(os.path.join(src, EXE_NAME), "--finish-update", HERE, str(os.getpid()), *(["--open", ro] if ro else []))
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
    def __init__(self, open_id=None, tools_for=None, updated=False, upd_mode=False, reopen=None):
        import tkinter as tk
        self.tk = tk; self.auth = Auth(); self.shop = Shop(self.auth); self.open_id = open_id; self.rows = []; self.busy = False
        self.just_updated = updated
        self.upd_mode = upd_mode; self.reopen_id = reopen      # --update <máy>: tự tải bản mới, xong mở lại đúng máy đó
        if FROZEN and not tools_for: threading.Thread(target=cleanup_update_leftovers, daemon=True).start()   # dọn thư mục của lần cập nhật trước
        self.scrollers = {}; self._fast = None; self._q = queue.Queue()
        self.root = tk.Tk(); self.root.title("CloudBlue PC"); self.root.configure(bg=BG)
        self.scale = ui_scale() / 100.0                   # 16/11: cỡ chữ khách tự chỉnh (🎨 Giao diện) — chữ Tk tính theo điểm nên nhân hệ số là to / nhỏ theo
        if abs(self.scale - 1.0) > 0.01:
            try: self.root.tk.call("tk", "scaling", float(self.root.tk.call("tk", "scaling")) * self.scale)
            except Exception as e: log("scale:", e); self.scale = 1.0
        g = max(1.0, self.scale)                          # chữ to → cửa sổ rộng / cao theo (chữ nhỏ thì giữ cỡ cửa sổ cũ)
        try: sw_, sh_ = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except Exception: sw_, sh_ = 1920, 1080
        self.root.geometry(f"{min(int(600 * g), max(480, sw_ - 40))}x{min(int(760 * g), max(540, sh_ - 80))}"); self.root.minsize(480, 540)
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

    def set_lang(self, code):
        """16/11c · 🌐 đổi Tiếng Việt / English → nhớ theo máy, mở lại app (cửa sổ máy đang mở giữ nguyên, mở lại máy là theo ngôn ngữ mới)."""
        if code not in ("vi", "en") or code == LANG: return
        prefs({"lang": code}); self.restart_ui()

    def restart_ui(self):
        """16/11 · mở lại app (tiến trình mới) để áp dụng cỡ chữ mới — cửa sổ máy đang mở là tiến trình riêng nên không bị đóng."""
        try:
            args = [sys.executable] if FROZEN else [sys.executable, os.path.abspath(__file__)]
            kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}     # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(args, close_fds=True, **kw)
        except Exception as e:
            log("restart:", e)
            import tkinter.messagebox as mb
            mb.showinfo("CloudBlue", "Đã lưu — đóng app rồi mở lại là thấy.", parent=self.root); return
        self.root.after(200, self.root.destroy)

    def toggle_promo(self):
        prefs({"promo_hide": not prefs().get("promo_hide")}); self._promo_sig = None; self._paint_promo()

    def _paint_promo(self):
        """16/11 · dòng nhỏ "Ẩn ưu đãi ▴" / "🎁 Hiện ưu đãi · vòng quay ▾" trên các ô 🎡 Vòng quay · 🎬 Kiếm tiền · 🎁 Ưu đãi — khách bấm ẩn / hiện,
           nhớ theo máy. Ẩn chỉ để gọn danh sách: dòng chữ chạy và hộp Nạp tiền vẫn như cũ. Không có ô nào → không hiện dòng này."""
        bar, ws, os_, anchor = (getattr(self, k, None) for k in ("promo_bar", "wheel_slot", "offers_slot", "list_wrap"))
        try:
            if any(w is None or not w.winfo_exists() for w in (bar, ws, os_, anchor)): return
            hide = bool(prefs().get("promo_hide")); any_ = bool(ws.winfo_children() or os_.winfo_children())
            sig = (hide, any_)
            if getattr(self, "_promo_sig", None) == sig: return
            self._promo_sig = sig
            for w in (bar, ws, os_): w.pack_forget()
            if any_:
                bar.config(text="🎁 Hiện ưu đãi · vòng quay  ▾" if hide else "Ẩn ưu đãi  ▴", fg=ACC if hide else DIM)
                bar.pack(anchor="e", padx=18, pady=(6, 0), before=anchor)
            if not hide:
                ws.pack(fill="x", padx=18, before=anchor); os_.pack(fill="x", padx=18, before=anchor)
        except Exception: log("promo:", traceback.format_exc())

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
        m.add_command(label=f"Đổi FPS (đang {int(num(p.get('fps')) or 30)} FPS)…", command=lambda: FpsDlg(self, p),      # 16/11: khách tự đổi FPS, không tạo máy mới
                      state="normal" if can_sw else "disabled")
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
        lg = tk.Label(box, text="🌐 English" if LANG == "vi" else "🌐 Tiếng Việt", font=self.f_t, fg=DIM, bg=BG, cursor="hand2"); lg.pack(pady=(14, 0))
        lg.bind("<Button-1>", lambda *_: self.set_lang("en" if LANG == "vi" else "vi"))          # 16/11c
        (ents["pw"] if ents["email"].get() else ents["email"]).focus_set()

    # ---------- danh sách máy ----------
    def show_list(self):
        tk = self.tk; self.clear()
        self.tick_slot = tk.Frame(self.body, bg=BG); self.tick_slot.pack(fill="x")         # 📣 dòng chữ chạy ưu đãi (SQL v35) — trống khi chưa bật
        self.ticker = Ticker(self, self.tick_slot); self._offers_sig = None
        top = tk.Frame(self.body, bg=BG); top.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(top, text="Máy của tôi", font=self.f_h1, fg=TXT, bg=BG).pack(side="left")
        self.btn(top, "Đăng xuất", self.logout, "ghost").pack(side="right")
        self.btn(top, "⟳ Làm mới", self.refresh, "ghost").pack(side="right", padx=6)
        self.btn(top, "🎨 Giao diện", lambda: LookDlg(self), "ghost").pack(side="right")       # 16/11: cỡ chữ · ẩn / hiện ô ưu đãi
        sub = tk.Frame(self.body, bg=BG); sub.pack(fill="x", padx=18)
        tk.Label(sub, text=self.auth.email, font=self.f_s, fg=DIM, bg=BG).pack(side="left")
        lk = tk.Label(sub, text="Mở web ↗", font=self.f_s, fg=ACC, bg=BG, cursor="hand2"); lk.pack(side="right")
        lk.bind("<Button-1>", lambda *_: webbrowser.open(WEB))
        lg = tk.Label(sub, text="🌐 English" if LANG == "vi" else "🌐 Tiếng Việt", font=self.f_s, fg=DIM, bg=BG, cursor="hand2"); lg.pack(side="right", padx=(0, 14))
        lg.bind("<Button-1>", lambda *_: self.set_lang("en" if LANG == "vi" else "vi"))          # 16/11c
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
        self.promo_bar = tk.Label(self.body, text="", font=self.f_s, fg=DIM, bg=BG, cursor="hand2")      # 16/11: bấm để ẩn / hiện các ô ưu đãi bên dưới
        self.promo_bar.bind("<Button-1>", lambda *_: self.toggle_promo()); self._promo_sig = None
        self.wheel_slot = tk.Frame(self.body, bg=BG); self.wheel_slot.pack(fill="x", padx=18)   # 🎡 vòng quay may mắn (SQL v34c) — trống khi chưa bật
        self._paint_wheel()
        self.offers_slot = tk.Frame(self.body, bg=BG); self.offers_slot.pack(fill="x", padx=18)   # 🎬 Kiếm tiền · 🎁 Ưu đãi (SQL v35) — trống khi chưa bật
        self._paint_offers()
        wrap = tk.Frame(self.body, bg=BG); wrap.pack(fill="both", expand=True, padx=10, pady=10)
        self.list_wrap = wrap; self._paint_promo()
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
                # bản app tối thiểu + bản mới đọc TRƯỚC danh sách máy: app cũ bị cổng chặn đọc máy vẫn hiện được nút ⬇ Cập nhật ngay
                if not getattr(self, "_site_ok", False) or time.time() - getattr(self, "_site_t", 0) > 300:   # tên miền web + bản app tối thiểu (5 phút/lần)
                    try:
                        sd = self.shop.site(); self._site_ok = True; self._site_t = time.time()
                        OUTDATED["min"] = str(sd.get("min_app_pc") or "").strip()
                    except Exception: pass
                if FROZEN and (not getattr(self, "_upd_checked", False) or (must_update() and not getattr(self, "update_info", None))):
                    self._upd_checked = True                       # 1 lần mỗi lần mở app (bắt buộc cập nhật mà chưa đọc được → đọc lại)
                    u = fetch_update_info(force=True, timeout=10, with_min=not getattr(self, "_site_ok", False))
                    if u: self.update_info = u
                rows = self.auth.phones()
                try: prof = self.shop.profile()
                except ApiError as e:
                    if e.code == 401: raise
                    prof = None
                if time.time() - BLUE["t"] > 60: blue_load(self.auth)          # 💎 Tích Blue (tối đa 1 lần / phút)
                if time.time() - WHEEL["t"] > 60: wheel_load(self.auth)        # 🎡 vòng quay may mắn (tối đa 1 lần / phút)
                if time.time() - OFFERS["t"] > 120: offers_load(self.auth)     # 🎁 ưu đãi + Kiếm tiền (tối đa 1 lần / 2 phút)
                def show():
                    self._paint_update(); self._paint_blue(); self._paint_wheel(); self._paint_offers(); self._paint_promo(); self._auto_update()
                    if prof is not None: self.prof = prof
                    if prof is not None and hasattr(self, "bal") and self.bal.winfo_exists():
                        self.bal.config(text=vnd(prof.get("balance")) + (f"  · CTV −{int(num(prof.get('ctv_discount')))}%" if is_ctv(prof) else ""))
                    self.render(rows)
                self.ui(show)
            except ApiError as e:
                m = str(e)
                if e.code == 401: self.ui(lambda m=m: self.show_login(m))
                elif must_update(): self.ui(self._show_outdated)                    # app cũ bị chặn → dải đỏ + nút cập nhật (trước đây chỉ hiện chữ)
                elif not quiet: self.ui(lambda m=m: self.msg.config(text=m) if self.msg.winfo_exists() else None)
            except Exception as e:
                log("refresh:", traceback.format_exc())
        threading.Thread(target=job, daemon=True).start()

    def _show_outdated(self):
        self._paint_update()
        if hasattr(self, "list") and self.list.winfo_exists(): self.render([])
        self._auto_update()

    def _auto_update(self):
        """Tự mở hộp Cập nhật và tải luôn: app quá cũ (không dùng được nữa) hoặc mở từ nút cập nhật của cửa sổ máy.
           Mỗi lần mở app tối đa 1 lần; app cũ tự mở thì cần update_claim (cập nhật lỗi → mở lại app → không tự tải lặp)."""
        u = getattr(self, "update_info", None)
        if not u or getattr(self, "_auto_upd", False) or not (self.upd_mode or must_update()): return
        if not self.upd_mode and not update_claim(): return
        self._auto_upd = True
        UpdateDlg(self, u, auto=True)

    def _paint_blue(self):
        b = getattr(self, "blue_btn", None)
        if b is None or not b.winfo_exists(): return
        if not blue_on(): b.pack_forget(); return
        n = blue_todo()
        b.config(text=f"💎 {blue_n(BLUE['info'].get('blue'))} Blue" + (f"  •{n}" if n else ""))
        if not b.winfo_manager(): b.pack(side="right", padx=(0, 6), pady=10)
        i = BLUE["info"]; k, d = "blue_nudge_" + str(self.auth.uid or ""), vn_today(); ki = "blue_intro_" + str(self.auth.uid or "")
        if i and not prefs().get(ki):                    # lần đầu thấy Tích Blue → hộp hướng dẫn cách nhận (1 lần / tài khoản / máy)
            prefs({ki: 1, k: d})
            try:
                import tkinter.messagebox as mb
                self.root.after(800, lambda: mb.askyesno("🎉 Mới: Tích Blue", "Tích Blue để thuê / gia hạn máy rẻ hơn — 1 Blue = 1đ. Cách nhận:\n\n"
                                                         + blue_intro_text(i) + "\n\nMở Tích Blue để điểm danh ngay?", parent=self.root) and BlueDlg(self))
            except Exception: pass
        elif i and not i.get("today") and prefs().get(k) != d:
            prefs({k: d})
            try:
                import tkinter.messagebox as mb
                self.root.after(800, lambda: mb.askyesno("💎 Tích Blue", f"Hôm nay bạn chưa điểm danh — nhận +{blue_n(i.get('next_got'))} Blue ngay?",
                                                         parent=self.root) and BlueDlg(self))
            except Exception: pass

    def _paint_wheel(self):
        slot = getattr(self, "wheel_slot", None)
        if slot is not None and slot.winfo_exists(): wheel_banner(self, slot)

    def _paint_offers(self):
        """📣 dòng chữ chạy + 2 ô 🎬 Kiếm tiền / 🎁 Ưu đãi (SQL v35). Máy chủ chưa bật → không hiện gì."""
        tk = self.tk; pub = OFFERS["pub"] or {}
        tkr = getattr(self, "ticker", None)
        if tkr is not None:
            try: tkr.set([str((x.get("en") if EN_UI else None) or x.get("vi") or "") for x in (pub.get("ticker") or []) if isinstance(x, dict)])
            except Exception: log("ticker:", traceback.format_exc())
        slot = getattr(self, "offers_slot", None)
        try:
            if slot is None or not slot.winfo_exists(): return
        except Exception: return
        cr, tc, tr, mine = offers_sec("creator"), offers_topup(), offers_sec("trial"), len(my_codes())
        sig = json.dumps([cr, tc, tr, mine], sort_keys=True, default=str)
        if getattr(self, "_offers_sig", None) == sig: return
        self._offers_sig = sig
        for w in slot.winfo_children(): w.destroy()
        def tile(col, icon, title, sub, cmd, edge):
            f = tk.Frame(slot, bg=CARD, highlightbackground=edge, highlightthickness=1, cursor="hand2")
            f.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0), pady=(8, 0))
            t1 = tk.Label(f, text=icon + "  " + title, font=("Segoe UI", 10, "bold"), fg=TXT, bg=CARD, anchor="w", cursor="hand2")
            t2 = tk.Label(f, text=sub, font=self.f_s, fg=DIM, bg=CARD, anchor="w", justify="left", wraplength=250, cursor="hand2")
            t1.pack(fill="x", padx=10, pady=(7, 0)); t2.pack(fill="x", padx=10, pady=(0, 7))
            for w in (f, t1, t2): w.bind("<Button-1>", lambda *_: cmd())
        col = 0
        if cr:
            tile(col, "🎬", f"Kiếm tiền · {blue_n(cr.get('per'))} view = {blue_n(cr.get('rate'))} 💎", "Làm video về CloudBlue trên TikTok, YouTube… view càng tăng 💎 càng nhiều.",
                 lambda: CreatorDlg(self), OK); col += 1
        sub = []
        if tc:
            lv = [x for x in tc["levels"] if isinstance(x, dict)]
            if lv: sub.append(f"Nạp từ {vnd(lv[0].get('min'))} nhận mã đến {int(num(lv[-1].get('pct')))}%")
        if tr:
            h = int(num(tr.get("hours"))); dur = f"{h} giờ" if h > 0 else f"{int(num(tr.get('days')) or 1)} ngày"
            sub.append(f"nạp {vnd(tr.get('need'))} dùng thử {dur}" if num(tr.get("need")) > 0 else f"dùng thử {dur} miễn phí")
        if mine: sub.append(f"bạn có {mine} mã")
        if sub: tile(col, "🎁", "Ưu đãi cloud phone", " · ".join(sub), lambda: OffersDlg(self), WARN); col += 1
        for i in range(col): slot.grid_columnconfigure(i, weight=1, uniform="ofr")

    def switch_retry(self, p):
        """🔁 Máy mới của lệnh ĐỔI ANDROID đang "Lỗi" → khách tự xếp lại lệnh tạo máy (hạn dùng vẫn giữ) — SQL doi-android-1511."""
        import tkinter.messagebox as mb
        def job():
            try:
                self.auth.rpc("cloudphone_switch_retry", {"p_id": p["id"]})
                self.ui(lambda: (self.refresh(), mb.showinfo("CloudBlue", "Đã xếp lại lệnh tạo máy — máy mới sẽ có sau ít phút. Hạn dùng của bạn vẫn giữ nguyên.", parent=self.root)))
            except Exception as e:
                m = str(e); self.ui(lambda m=m: mb.showerror("CloudBlue", m, parent=self.root))
        threading.Thread(target=job, daemon=True).start()

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
        if p.get("status") == "error" and p.get("replaces") and not p.get("shared"):       # máy mới của lệnh đổi Android → khách tự thử lại
            self.btn(c, "🔁 Thử tạo lại máy", lambda q=p: self.switch_retry(q), "soft", padx=10, pady=4).pack(anchor="w", padx=14, pady=(6, 0))
        if int(num(p.get("trial_hours"))) > 0 and p.get("status") != "error":
            tk.Label(c, text=f"🎁 Máy dùng thử {int(num(p.get('trial_hours')))} giờ — hết giờ máy và dữ liệu tự xoá, không gia hạn được.", font=self.f_s, fg=WARN, bg=CARD,
                     anchor="w", wraplength=440, justify="left").pack(fill="x", padx=14)
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
        import av, numpy, pygame, tkinter, ssl, brstream, qrcodegen, bluepc_en   # noqa: F401,E401
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
        o = args.index("--open") if "--open" in args else -1
        oid = args[o + 1] if 0 <= o < len(args) - 1 and UUID_RE.fullmatch(args[o + 1]) else None
        try: wp = int(args[2])
        except ValueError: wp = 0
        return run_finish_update(args[1], wp, args[t + 1] if 0 <= t < len(args) - 1 else None, oid)
    if len(args) >= 1 and args[0] == "--update":                      # nút cập nhật trong cửa sổ máy: tải bản mới → mở lại đúng máy đó
        rid = args[1] if len(args) >= 2 and UUID_RE.fullmatch(args[1]) else None
        return Launcher(upd_mode=True, reopen=rid).run()
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
