# -*- coding: utf-8 -*-
# =====================================================================================================
#  pcagent.py — PHẦN MỀM CloudBlue trên MÁY PC CHO THUÊ (chạy ngầm bằng tài khoản SYSTEM, tự chạy lúc Windows khởi động)
#
#  Việc làm (bản 21.11b):
#    · ĐĂNG KÝ máy lên hệ thống (pc_enroll): lần đầu bằng MÃ ĐĂNG KÝ trong bộ cài, sau lệnh cài lại bằng VÉ 1 lần
#    · BÁO SỐNG + cấu hình máy (pc_poll) mỗi ~30 giây, nhận LỆNH từ trang quản trị:
#        reinstall  cài lại / đổi bản Windows / dọn máy (ghi lệnh lên phân vùng cứu hộ rồi khởi động lại vào bộ cài)
#        reboot · shutdown · update
#    · báo kết quả lệnh cài lại sau khi Windows mới lên
#    · tự cập nhật theo bản admin công bố (kiểm sha256 từng file, chỉ tải từ đúng kho GitHub của shop)
#    · HẠN THUÊ (SQL v42): nhận hạn từ máy chủ, báo trước cho khách, hết hạn thì tự tắt máy (mất mạng vẫn đếm; chỉnh lùi đồng hồ không lách được)
#    · báo VIỆC LẠ về web (bảo mật trên máy bị đổi, đồng hồ bị chỉnh lùi, máy hết hạn bị bật lại) → admin nhận mail / Telegram
#    · chỉnh đồng hồ máy theo máy chủ khi lệch quá 2 phút; máy mới cài không có mạng thì hiện hộp báo tại máy
#  Máy cho thuê KHÔNG giữ khoá bí mật nào của hệ thống: chỉ khoá công khai của web + mã riêng của chính máy này.
#
#  Lệnh tại máy (PowerShell Admin):   C:\CloudBluePC\cbpc.cmd status | reinstall <bản> [all|disk|system] | enroll | log
# =====================================================================================================
import hashlib, json, os, re, socket, ssl, subprocess, sys, time, traceback
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "..", "lib"), HERE):
    _p = os.path.abspath(_p)
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import cbrec                                                     # noqa: E402
from cbsys import BUS_EXTERNAL, WIN, WinSys                                    # noqa: E402

AGENT_VER = "21.11b"
BASE = os.path.abspath(os.path.join(HERE, ".."))                 # C:\CloudBluePC
UPDATE_REL = re.compile(r"^(agent|lib|os|pe)/[A-Za-z0-9_.-]{1,60}\.(py|cmd|xml|json|txt|pem|ini)$")
UPDATE_BASE = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/"       # chỉ nhận bản cập nhật từ kho này
RENT_WARN_S = 2 * 86400                  # bắt đầu NHẮC khách từ khi hạn thuê còn 2 ngày (máy chủ gửi rent.warn_min thì theo máy chủ — thuê ngắn thì khoảng này ngắn theo)
RENT_EVERY_S = 4 * 3600                  # trong khoảng nhắc: nhắc lại mỗi 4 giờ + mỗi lần bật máy (máy chủ gửi rent.every_min thì theo máy chủ; 0 = chỉ nhắc ở các mốc)
RENT_MARKS = (3600, 1800, 600, 300, 60)  # giờ cuối luôn nhắc ở các mốc: còn 60 · 30 · 10 · 5 · 1 phút
RENT_MIN_S = 600                         # admin tắt báo trước (0) thì vẫn báo khách 10 phút + 1 phút trước khi máy tự tắt
RENT_BOOT_TELL = 60                      # vừa bật máy mà đang trong khoảng nhắc: chờ hỏi máy chủ tối đa 60 giây (có thể vừa được gia hạn) rồi nhắc 1 lần
RENT_POP_MAX = 6 * 3600                  # hộp nhắc nằm trên màn hình tới lần nhắc kế (tối đa 6 giờ) hoặc tới khi khách bấm OK
RENT_BOOT_GRACE = 180                    # máy bật lên lúc ĐÃ hết hạn: chờ hỏi máy chủ tối đa 3 phút (có thể vừa được gia hạn) rồi mới tắt
RENT_LAST_CALL = 60                      # hết hạn: báo khách, 60 giây sau tắt máy
RENT_SAVE_S = 120                        # ghi lại mốc thời gian (chống chỉnh lùi đồng hồ) tối đa 2 phút / lần
CLOCK_FIX_S = 120                        # đồng hồ máy lệch giờ máy chủ quá 2 phút → agent đặt lại theo máy chủ (cb.json "clock_fix": false để tắt)
NO_NET_TELL_S = 150                      # máy CHƯA đăng ký mà quá 2,5 phút vẫn không có địa chỉ IP → hiện 1 hộp báo tại máy (mỗi lần agent chạy 1 lần)


# ====================================================================================== đọc phần cứng (không cần WMI)
def parse_smbios(raw):
    """Bảng SMBIOS thô (GetSystemFirmwareTable 'RSMB') → {'uuid','sys_serial','board_serial','vendor','product','board'}."""
    out = {"uuid": "", "sys_serial": "", "board_serial": "", "vendor": "", "product": "", "board": ""}
    if not raw or len(raw) < 12: return out
    n = int.from_bytes(raw[4:8], "little")
    t = raw[8:8 + n]
    i = 0
    while i + 4 <= len(t):
        typ, ln = t[i], t[i + 1]
        if ln < 4: break
        body = t[i:i + ln]
        j = i + ln
        strs = []
        while j < len(t) and t[j] != 0:
            e = t.find(b"\0", j)
            if e < 0: e = len(t)
            strs.append(t[j:e].decode("ascii", "replace").strip()); j = e + 1
        j += 2 if not strs else 1

        def S(off):
            k = body[off] if off < len(body) else 0
            return strs[k - 1] if 0 < k <= len(strs) else ""
        if typ == 1 and not out["uuid"]:
            out["vendor"], out["product"], out["sys_serial"] = S(4), S(5), S(7)
            if ln >= 0x19: out["uuid"] = body[8:24].hex()
        elif typ == 2 and not out["board"]:
            out["board"], out["board_serial"] = (S(4) + " " + S(5)).strip(), S(7)
        elif typ == 127:
            break
        i = j
    return out


def hw_id(smb, disk_serial, disk_model):
    """Dấu phần cứng: giữ nguyên khi cài lại Windows; đổi khi thay bo mạch / ổ hệ thống. 64 ký tự hex."""
    s = "cbpc1|%s|%s|%s|%s|%s" % (smb.get("uuid", ""), smb.get("board_serial", ""), smb.get("sys_serial", ""), (disk_serial or "").strip(), (disk_model or "").strip())
    return hashlib.sha256(s.lower().encode("utf-8")).hexdigest()


class WinHost:
    """Thông tin máy + các việc chỉ Windows làm được. Bộ thử thay bằng lớp giả."""
    def hostname(self):
        return os.environ.get("COMPUTERNAME") or socket.gethostname()

    def _reg(self, path, name, default=None):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k: return winreg.QueryValueEx(k, name)[0]
        except Exception:
            return default

    def os_ver(self):
        p = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        return "%s.%s.%s.%s" % (self._reg(p, "CurrentMajorVersionNumber", 10), self._reg(p, "CurrentMinorVersionNumber", 0),
                                self._reg(p, "CurrentBuildNumber", self._reg(p, "CurrentBuild", "0")), self._reg(p, "UBR", 0))

    def os_name(self):
        p = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        return "%s %s" % (self._reg(p, "ProductName", "Windows"), self._reg(p, "DisplayVersion", "") or self._reg(p, "ReleaseId", ""))

    def cpu(self):
        return (str(self._reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString", "") or "").strip(), os.cpu_count() or 0)

    def ram_gb(self):
        try:
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
            m = M(); m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2 ** 30, 1)
        except Exception:
            return 0

    def gpus(self):
        out = []
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            for i in range(16):
                d = self._reg(base + "\\%04d" % i, "DriverDesc")
                if d and d not in out: out.append(str(d))
        except Exception:
            pass
        return out

    def lan_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
            return ip
        except OSError:
            return ""

    def uptime(self):
        try:
            import ctypes
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return int(ctypes.windll.kernel32.GetTickCount64() // 1000)
        except Exception:
            return 0

    def smbios(self):
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
            k.GetSystemFirmwareTable.restype = ctypes.c_uint32
            n = k.GetSystemFirmwareTable(0x52534D42, 0, None, 0)
            if not n: return parse_smbios(b"")
            buf = ctypes.create_string_buffer(n)
            k.GetSystemFirmwareTable(0x52534D42, 0, buf, n)
            return parse_smbios(buf.raw)
        except Exception:
            return parse_smbios(b"")

    def power(self, reboot=True, delay=5, msg=""):
        a = ["shutdown", "/r" if reboot else "/s", "/t", str(int(delay)), "/f"]
        if msg: a += ["/c", msg[:120]]
        try: subprocess.run(a, capture_output=True, timeout=60)
        except Exception: pass

    def abort_shutdown(self):
        """Huỷ lệnh tắt máy đang đếm ngược (khách vừa được gia hạn trong phút cuối)."""
        try: subprocess.run(["shutdown", "/a"], capture_output=True, timeout=60)
        except Exception: pass

    def set_clock(self, epoch):
        """Đặt đồng hồ hệ thống theo giờ quốc tế `epoch` (giây). Cần quyền SYSTEM / quản trị. True nếu Windows nhận."""
        try:
            import ctypes

            class ST(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ushort) for n in ("y", "mo", "dow", "d", "h", "mi", "s", "ms")]
            t = time.gmtime(int(epoch))
            st = ST(t.tm_year, t.tm_mon, (t.tm_wday + 1) % 7, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, 0)
            return bool(ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st)))
        except Exception:
            return False

    def notify(self, text, secs=60):
        """Hiện hộp thông báo cho người đang dùng máy (mọi phiên đăng nhập) bằng msg.exe của Windows. Không chờ ai bấm; không có msg.exe thì thôi."""
        try:
            exe = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "msg.exe")
            subprocess.Popen([exe, "*", "/TIME:%d" % max(5, int(secs)), str(text)[:250]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
        except Exception: pass

    def mutex(self, name="Global\\CloudBluePCAgent"):
        """True nếu đây là bản agent DUY NHẤT đang chạy."""
        try:
            import ctypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]; k.CreateMutexW.restype = ctypes.c_void_p
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            h = k.CreateMutexW(None, 0, name)
            if not h: return True                                             # không tạo được khoá → cứ chạy (thà 2 bản còn hơn không bản nào)
            if ctypes.get_last_error() == 183:                                # ERROR_ALREADY_EXISTS: bản khác đang chạy
                k.CloseHandle(h); return False                                # đóng ngay — giữ lại thì chính mình làm khoá "còn mãi"
            self._mx = h
            return True
        except Exception:
            return True

    def restart_self(self):
        try:
            subprocess.Popen([sys.executable, "-I", "-B", os.path.abspath(__file__), "run", "--wait"], close_fds=True,
                             creationflags=0x00000008 | 0x00000200 | 0x08000000)       # tách hẳn khỏi tác vụ đang chạy, không cửa sổ
            return True
        except Exception:
            return False

    def selfcheck(self, script):
        try:
            r = subprocess.run([sys.executable, "-I", "-B", script, "selfcheck"], capture_output=True, timeout=120, creationflags=0x08000000 if WIN else 0)
            return r.returncode == 0, ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")[-400:]
        except Exception as e:
            return False, str(e)


# ====================================================================================== mạng
class Net:
    def __init__(self, cfg, base=BASE):
        self.url = (cfg.get("sb_url") or "").rstrip("/")
        self.key = cfg.get("sb_key") or ""
        self.ctx = ssl.create_default_context()
        ca = os.path.join(base, "os", "cacert.pem")                # Windows vừa cài chưa đủ chứng chỉ gốc → mang theo bộ chứng chỉ
        if os.path.isfile(ca):
            try: self.ctx.load_verify_locations(ca)
            except Exception: pass

    def rpc(self, fn, body, timeout=20):
        """Gọi hàm trên Supabase bằng khoá CÔNG KHAI. Trả dict, hoặc None khi lỗi mạng / máy chủ."""
        if not self.url or not self.key: return None
        req = urllib.request.Request(self.url + "/rest/v1/rpc/" + fn, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"apikey": self.key, "Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                                              "User-Agent": "CloudBluePC/" + AGENT_VER})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                t = r.read().decode("utf-8")
                return json.loads(t) if t.strip() else {}
        except urllib.error.HTTPError as e:
            try: self.last_err = "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
            except Exception: self.last_err = "HTTP %s" % e.code
        except Exception as e:
            self.last_err = "%s: %s" % (type(e).__name__, e)
        return None

    last_err = ""

    def get(self, url, timeout=60, limit=8 << 20):
        req = urllib.request.Request(url, headers={"User-Agent": "CloudBluePC/" + AGENT_VER})
        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
            b = r.read(limit + 1)
            if len(b) > limit: raise ValueError("file qua lon")
            return b


def span_txt(sec):
    """Số giây → chữ không dấu cho hộp thông báo: '2 ngay 3 gio' · '5 gio 10 phut' · '9 phut' · '40 giay'."""
    sec = max(0, int(sec))
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    if d: return "%d ngay" % d + (" %d gio" % h if h else "")
    if h: return "%d gio" % h + (" %d phut" % m if m else "")
    if m: return "%d phut" % m
    return "%d giay" % sec


# ====================================================================================== agent
class Agent:
    def __init__(self, sysx, host, net, base=BASE, log=None):
        self.s, self.h, self.net, self.base = sysx, host, net, base.rstrip("\\")
        self._log = log or (lambda m: None)
        self.cfg = C.load_json(sysx, self.p("cb.json")) or {}
        self.ident = C.load_json(sysx, self.p("identity.json")) or None
        if self.ident and not (self.ident.get("id") and self.ident.get("token")): self.ident = None
        self.poll_s, self.ticks, self.fail = 30, 0, 0
        self.pending_done = None            # kết quả lệnh chờ báo về web
        self.result_from_rec = False
        self.rebooting = False
        self.bad_update = None
        self.enroll_turn = 0
        self.name = (self.ident or {}).get("name") or ""
        self.rent = C.load_json(sysx, self.p("rent.json")) or {}    # hạn thuê máy chủ giao: {"until", "skew", "hi", "warned", "off"} — giữ cả khi mất mạng / khởi động lại
        if not isinstance(self.rent, dict): self.rent = {}
        self.events = []                    # việc lạ chờ báo về web (kèm trong p_info.ev)
        self.t_start = sysx.now()
        self.rent_synced = False            # từ lúc agent chạy đã hỏi được máy chủ về hạn thuê chưa
        self.rent_call = None               # lúc đã báo khách "máy sắp tắt"
        self.rent_boot_told = False         # từ lúc agent chạy (máy bật) đã nhắc khách "sắp hết hạn" lần nào chưa
        self.rent_saved = 0
        self.clock_at = None                # lần gần nhất đã (thử) chỉnh đồng hồ theo máy chủ
        self.net_told = False               # đã hiện hộp "máy chưa có mạng" trong lần chạy này chưa

    def p(self, rel): return self.base + "\\" + rel
    def log(self, m): self._log(m)

    # ------------------------------------------------------------------ thông tin máy
    def sys_disk(self):
        try:
            v = cbrec.system_volume(self.s)
            return next((d for d in self.s.disks() if v and d.index == v.disk), None)
        except Exception:
            return None

    def calc_hw(self):
        d = self.sys_disk()
        return hw_id(self.h.smbios(), d.serial if d else "", d.model if d else "")

    def info(self):
        ver = self.h.os_ver()
        cpu, cores = self.h.cpu()
        i = {"host": self.h.hostname(), "os": C.os_id(ver), "os_ver": ver, "os_name": self.h.os_name(), "agent": AGENT_VER, "cpu": cpu, "cores": cores,
             "ram_gb": self.h.ram_gb(), "gpus": self.h.gpus()[:6], "lan_ip": self.h.lan_ip(), "uptime": self.h.uptime()}
        try:
            i["fw"] = self.s.firmware()
            i["disks"] = [{"model": (d.model or "")[:40], "gb": round(d.size / 1e9), "bus": d.bus_name, "ssd": d.ssd} for d in self.s.disks()
                          if not d.removable and d.bus not in BUS_EXTERNAL][:8]
            i["rec"] = cbrec.status(self.s)
        except Exception as e:
            i["err"] = str(e)[:120]
        smb = self.h.smbios()
        i["board"] = (smb.get("board") or (smb.get("vendor", "") + " " + smb.get("product", "")).strip())[:60]
        try:                                                        # tình trạng bảo mật trên máy (cb_provision đặt mốc): khách là tài khoản thường? đã khoá quyền?
            i["sec"] = {"std": not self.cfg.get("user_admin"), "hard": bool(self.s.exists(self.p("logs\\harden.done"))),
                        "lock": bool(self.s.exists(self.p("logs\\lock.done")))}
        except Exception: pass
        return i

    def write_status(self):
        """Ghi os\\status.txt — tình trạng agent KHÔNG có bí mật, tài khoản thường đọc được (thư mục os cho đọc) để chủ shop xem tại máy
           khi máy không hiện trên web mà trên máy không còn tài khoản quản trị. Chỉ ghi khi tình trạng đổi."""
        rent = self.rent_line()
        try: lan = self.h.lan_ip() or ""
        except Exception: lan = ""
        st = (bool(self.ident), self.fail == 0, self.name, (self.net.last_err if (self.net is not None and self.fail) else "") or "", rent, lan)
        if st == getattr(self, "_last_status", None): return
        self._last_status = st
        lines = ["CloudBlue PC - tinh trang (ghi luc %s)" % time.strftime("%Y-%m-%d %H:%M:%S"),
                 "Phan mem agent: %s" % AGENT_VER,
                 "Mang LAN: %s" % (("co - dia chi IP %s" % lan) if lan else "KHONG CO dia chi IP - kiem tra day mang / driver card mang"),
                 "Dang ky voi he thong: %s" % (("ROI - ten tren web: %s" % (self.name or "?")) if st[0] else "CHUA (dang thu dang ky)"),
                 "Ket noi may chu: %s" % ("duoc" if st[1] else ("CHUA DUOC - %s" % st[3][:200])),
                 "Han thue: %s" % rent,
                 "May khong hien tren web: kiem tra day mang / driver card mang; van khong duoc thi cai lai bang USB CloudBlue."]
        try: self.s.write_text(self.p("os\\status.txt"), "\r\n".join(lines) + "\r\n")
        except Exception: pass

    # ------------------------------------------------------------------ hạn thuê + việc lạ
    def event(self, k, **kw):
        """Ghi 1 việc lạ để báo về web ở lần gọi máy chủ kế (mỗi loại 1 mục đang chờ, tối đa 8 mục)."""
        if len(self.events) < 8 and not any(e.get("k") == k for e in self.events): self.events.append(dict(kw, k=k))

    def rent_save(self):
        try:
            C.save_json(self.s, self.p("rent.json"), self.rent); self.rent_saved = self.s.now()
        except Exception: pass

    def rent_est(self):
        """Giờ MÁY CHỦ ước tính (giây) = giờ máy + độ lệch đo ở lần hỏi máy chủ gần nhất.
           Lúc mất mạng mà đồng hồ máy bị chỉnh LÙI → nối tiếp từ mốc lớn nhất đã thấy (không lách được hạn thuê) + báo việc lạ."""
        r = self.rent
        est = self.s.now() + (r.get("skew") or 0)
        hi = r.get("hi") or 0
        if est < hi - 300:
            self.event("clock", d=int(est - hi))
            self.log("đồng hồ máy bị chỉnh lùi %d giây → hạn thuê vẫn tính theo mốc cũ" % (hi - est))
            r["skew"] = (r.get("skew") or 0) + (hi - est); est = hi
            self.rent_save()
        elif est > hi:
            r["hi"] = est
        return est

    def clock_fix(self, r):
        """Đồng hồ máy lệch giờ máy chủ quá CLOCK_FIX_S giây → đặt lại theo máy chủ (bản Windows tuỳ biến hay lệch đúng 1 giờ sau khi cài, pin CMOS yếu…).
           Mỗi 10 phút thử tối đa 1 lần. Các mốc thời gian agent đang giữ được dời theo để không tính nhầm."""
        if self.cfg.get("clock_fix") is False: return False
        try: now_srv = int(r.get("now") or 0)
        except (TypeError, ValueError): return False
        if now_srv < 1_600_000_000: return False
        before = self.s.now()
        d = now_srv - before
        if abs(d) <= CLOCK_FIX_S: return False
        if self.clock_at is not None and abs(before - self.clock_at) < 600: return False
        ok = False
        try: ok = bool(self.h.set_clock(now_srv))
        except Exception: ok = False
        moved = self.s.now() - before
        self.clock_at = self.s.now()
        if not ok:
            self.log("đồng hồ máy lệch %+d giây so với máy chủ nhưng KHÔNG chỉnh được" % d); return False
        self.log("đồng hồ máy lệch %+d giây so với máy chủ → đã chỉnh lại theo máy chủ" % d)
        self.t_start += moved
        if self.rent_call is not None: self.rent_call += moved
        if self.rent_saved: self.rent_saved += moved
        if self.rent.get("skew") is not None:                        # độ lệch đã đo trước đó không còn đúng nữa
            self.rent["skew"] = now_srv - self.s.now(); self.rent["hi"] = max(now_srv, 0)
        return True

    def rent_stop_off(self, why):
        """Đang đếm ngược tắt máy mà hạn thuê đổi (được gia hạn / bỏ hạn) → huỷ lệnh tắt."""
        if self.rent_call is None: return
        self.rent_call = None
        self.log("huỷ lệnh tắt máy: %s" % why)
        try: self.h.abort_shutdown()
        except Exception: pass

    def rent_sync(self, r):
        """Sau mỗi lần hỏi được máy chủ: nhận hạn thuê + chỉnh độ lệch đồng hồ (máy chủ là chuẩn)."""
        if not isinstance(r.get("rent"), dict): return                # máy chủ chưa có phần hạn thuê (chưa chạy SQL v42) → không làm gì
        u = r["rent"].get("until")
        u = int(u) if isinstance(u, (int, float)) and not isinstance(u, bool) and u > 0 else None
        try: now_srv = int(r.get("now") or 0)
        except (TypeError, ValueError): now_srv = 0
        if now_srv > 1_600_000_000:
            self.rent["skew"] = now_srv - self.s.now(); self.rent["hi"] = now_srv
        self.rent_synced = True
        ch = False
        for key, name, hi in (("warn_min", "warn_s", 10080), ("every_min", "every_s", 1440)):     # khoảng nhắc + nhịp nhắc do admin đặt trên web (phút)
            v = r["rent"].get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= hi and int(v) * 60 != self.rent.get(name):
                self.rent[name] = int(v) * 60; ch = True
        if u != self.rent.get("until"):
            self.rent_stop_off("hạn thuê vừa đổi")
            self.rent["until"] = u; self.rent["warned"] = []; self.rent.pop("off", None); self.rent.pop("told", None)
            self.log("hạn thuê: %s" % ("không đặt hạn" if u is None else "còn %s" % span_txt(u - self.rent_est())))
            self.rent_save()
        elif ch or (u and self.s.now() - self.rent_saved >= RENT_SAVE_S):
            self.rent_save()

    def rent_plan(self):
        """(khoảng nhắc, nhịp nhắc lại, các mốc) tính bằng giây cho hạn thuê hiện tại."""
        w, e = self.rent.get("warn_s"), self.rent.get("every_s")
        w = RENT_WARN_S if not isinstance(w, int) else w
        e = RENT_EVERY_S if not isinstance(e, int) else e
        win = w if w > 0 else RENT_MIN_S
        return win, e, sorted({m for m in RENT_MARKS if m < win} | {win}, reverse=True)

    def rent_line(self):
        u = self.rent.get("until")
        if not u: return "khong dat han"
        left = u - (self.s.now() + (self.rent.get("skew") or 0))
        if left <= 0: return "DA HET HAN - may tu tat. Lien he shop de gia han."
        if left < 60: return "con duoi 1 phut"
        return "con %s" % span_txt(left // 60 * 60 if left < 3600 else left // 3600 * 3600)      # làm tròn (phút / giờ) để không ghi lại file liên tục

    def rent_check(self):
        """Soát hạn thuê (chạy cả khi mất mạng). Trả số giây tối đa được nghỉ trước lần soát sau, hoặc None nếu máy không đặt hạn."""
        u = self.rent.get("until")
        if not u: return None
        est = self.rent_est()
        left = u - est
        if left > 0:
            if left > 5: self.rent_stop_off("còn hạn thuê")            # dư vài giây do đo lại đồng hồ thì không huỷ lệnh tắt đang đếm
            win, every, marks = self.rent_plan()
            if left > win:                                             # chưa tới khoảng nhắc
                if self.s.now() - self.rent_saved >= RENT_SAVE_S: self.rent_save()
                return max(2, min(left - win, 300))
            # ĐANG TRONG KHOẢNG NHẮC (mặc định 2 ngày cuối): nhắc khi vừa vào khoảng / tới 1 mốc của giờ cuối, nhắc LẠI theo nhịp, và mỗi lần bật máy
            if self.s.now() - self.rent_saved >= RENT_SAVE_S: self.rent_save()
            if not (self.rent_synced or self.s.now() - self.t_start >= RENT_BOOT_TELL or left <= 2 * RENT_BOOT_TELL):
                return 5                                               # máy vừa bật: chờ hỏi máy chủ đã (có thể chủ shop vừa gia hạn lúc máy đang tắt)
            done, told = self.rent.get("warned") or [], self.rent.get("told")
            told = told if isinstance(told, (int, float)) and told <= est else None      # mốc "đã nhắc" nằm ở tương lai (đồng hồ bị chỉnh) → coi như chưa nhắc
            due = (any(left <= w and w not in done for w in marks)     # máy vừa bật khi còn 5 phút thì chỉ nhắc 1 lần "con 5 phut"
                   or (every > 0 and (told is None or est - told >= every))
                   or not self.rent_boot_told)
            self.rent_boot_told = True
            nxt = [left - w for w in marks if w < left] + [left]       # tới mốc kế / lúc hết hạn
            if due:
                self.rent["warned"] = [w for w in marks if left <= w]
                self.rent["told"] = int(est); self.rent_save()
                if every > 0: nxt.append(every)
                self.log("nhắc khách: hạn thuê còn %s" % span_txt(left))
                try: when = time.strftime("%H:%M ngay %d/%m", time.localtime(self.rent["until"]))
                except Exception: when = ""
                self.h.notify("CloudBlue PC: may nay con %s nua la HET HAN THUE%s. Het han may se TU TAT. Lien he shop de gia han."
                              % (span_txt(left), " (het han luc %s)" % when if when else ""), max(45, min(min(nxt) - 3, RENT_POP_MAX)))
            elif every > 0 and told is not None:
                nxt.append(max(1, told + every - est))
            return max(2, min(min(nxt), 300))
        if not self.rent_synced and self.s.now() - self.t_start < RENT_BOOT_GRACE:
            return 10                                                  # vừa bật máy: chờ hỏi máy chủ đã (có thể chủ shop vừa gia hạn lúc máy đang tắt)
        if self.rent_call is None:
            self.rent_call = self.s.now()
            self.event("rent_boot" if self.rent.get("off") else "rent_off")
            self.log("HẾT HẠN THUÊ → báo khách, %d giây nữa tắt máy" % RENT_LAST_CALL)
            self.h.notify("CloudBlue PC: may nay da HET HAN THUE. May se TU TAT sau %d giay. Lien he shop de gia han." % RENT_LAST_CALL, RENT_LAST_CALL)
            # Windows tự đếm ngược + hiện lời nhắn của chính nó (máy không có msg.exe vẫn thấy). Khách có huỷ lệnh này thì 60 giây nữa agent vẫn tắt.
            self.h.power(reboot=False, delay=RENT_LAST_CALL, msg="CloudBlue PC: het han thue - may tu tat sau %d giay. Lien he shop de gia han." % RENT_LAST_CALL)
            return 3                                                   # nhịp kế báo về web ngay
        wait = RENT_LAST_CALL - (self.s.now() - self.rent_call)
        if wait > 0: return max(2, min(15, wait))
        self.rent["off"] = int(est); self.rent_save()
        self.log("hết hạn thuê → TẮT MÁY")
        self.h.power(reboot=False, delay=0, msg="CloudBlue PC: het han thue - may tat.")
        self.rent_call = self.s.now() + RENT_LAST_CALL                 # lệnh tắt bị chặn / máy chưa tắt: 2 phút sau ra lệnh lại
        return 30

    # ------------------------------------------------------------------ đăng ký
    def enroll(self):
        """Xin mã máy. Thử lần lượt: vé cài lại → mã đăng ký của bộ cài → không mã (khi admin bấm 'Cho đăng ký lại')."""
        seed = C.load_json(self.s, self.p("seed.json")) or {}
        hw = seed.get("hw") or (self.ident or {}).get("hw") or self.calc_hw()
        keys = [k for k in (seed.get("ticket"), seed.get("enroll_key")) if k] + [None]
        key = keys[self.enroll_turn % len(keys)]
        self.enroll_turn += 1
        r = self.net.rpc("pc_enroll", {"p_hw": hw, "p_info": self.info(), "p_key": key})
        if not r:
            self.fail += 1
            self.log("đăng ký: chưa gọi được máy chủ (%s)" % self.net.last_err)
            self.tell_no_net()
            return False
        self.fail = 0
        if not r.get("ok"):
            why = {"NEED_KEY": "cần mã đăng ký — vào trang quản trị › Máy PC bấm 'Cho đăng ký lại' cho máy này, hoặc cài lại bằng USB / ISO CloudBlue",
                   "BAD_KEY": "mã đăng ký / vé không đúng hoặc đã hết hạn", "WRONG_NET": "máy đang ở mạng khác lúc trước",
                   "SLOW_DOWN": "gọi quá dồn dập, thử lại sau", "BAD_HW": "dấu phần cứng sai"}.get(r.get("err"), str(r.get("err")))
            self.log("đăng ký chưa được: %s" % why); return False
        self.ident = {"id": r["id"], "token": r["token"], "hw": hw, "name": r.get("name") or ""}
        self.name = self.ident["name"]
        C.save_json(self.s, self.p("identity.json"), self.ident)
        if seed:                                                    # xoá bí mật 1 lần khỏi máy (mã đăng ký, vé)
            C.save_json(self.s, self.p("seed.json"), {k: v for k, v in seed.items() if k not in ("ticket", "enroll_key")})
        try: cbrec.save_identity(self.s, self.ident)
        except Exception: pass
        self.poll_s = int(r.get("poll_s") or 30)
        self.enroll_turn = 0
        self.log("ĐÃ ĐĂNG KÝ: máy %s (%s) — %s" % (self.name, r["id"], "đã duyệt" if r.get("approved") else "chờ admin duyệt trên trang quản trị"))
        return True

    def tell_no_net(self):
        """Máy mới cài (chưa đăng ký) mà không có địa chỉ IP → hiện 1 hộp báo tại máy để người cài biết vì sao máy không hiện trên web."""
        if self.net_told or self.s.now() - self.t_start < NO_NET_TELL_S: return
        try: lan = self.h.lan_ip()
        except Exception: lan = "?"
        if lan: return
        self.net_told = True
        self.log("máy chưa có địa chỉ IP (dây mạng / driver card mạng) → báo tại máy")
        self.h.notify("CloudBlue PC: may nay CHUA CO MANG (chua co dia chi IP) nen chua hien tren web. Kiem tra day mang / driver card mang.", 600)

    # ------------------------------------------------------------------ lệnh
    def done(self, oid, ok, result):
        self.pending_done = {"id": oid, "ok": bool(ok), "result": result}

    def check_result(self):
        """Bộ cài vừa làm xong 1 lệnh cài lại? → chuẩn bị báo về web."""
        if self.pending_done: return
        try: res = cbrec.take_result(self.s)
        except Exception: res = None
        if not isinstance(res, dict): return
        if not re.fullmatch(r"[0-9]{1,18}", str(res.get("id"))):
            cbrec.take_result(self.s, clear=True); return           # lệnh gõ tại máy (không có số trên web) → không cần báo
        self.done(int(res["id"]), res.get("ok"), {k: res.get(k) for k in ("msg", "os", "secs", "pe")})
        self.result_from_rec = True

    def handle(self, o):
        cmd, oid, args = o.get("cmd"), o.get("id"), o.get("args") or {}
        self.log("nhận lệnh #%s: %s %s" % (oid, cmd, {k: v for k, v in args.items() if k != "ticket"}))
        if cmd in ("reboot", "shutdown"):
            self.done(oid, True, {"msg": "đang %s" % ("khởi động lại" if cmd == "reboot" else "tắt máy")})
            self.poll(send_info=False)                              # báo xong TRƯỚC khi tắt (lệnh không bị giao lại sau khi máy lên)
            if self.pending_done is None:
                self.rebooting = True
                self.h.power(reboot=(cmd == "reboot"), delay=10, msg="CloudBlue: may se %s sau 10 giay." % ("khoi dong lai" if cmd == "reboot" else "tat"))
            return
        if cmd == "update":
            v = self.update(self.last_manifest, force=True)
            self.done(oid, bool(v), {"msg": v or "không có bản mới / tải lỗi", "agent": AGENT_VER})
            return
        if cmd == "reinstall":
            try:
                old = cbrec.pending_job(self.s)
                tries = int((old or {}).get("tries") or 0) if (old or {}).get("id") == oid else 0
                if tries >= 2:                                      # đã khởi động lại 2 lần mà không vào được bộ cài → thôi, báo lỗi
                    cbrec.drop_job(self.s)
                    self.done(oid, False, {"msg": "máy không khởi động được vào bộ cài lại (đã thử 2 lần) — cần cài bằng USB"}); return
                job = {"id": oid, "os": args.get("os"), "wipe": args.get("wipe") or "all", "ticket": args.get("ticket"),
                       "hw": (self.ident or {}).get("hw"), "tries": tries + 1}
                img = cbrec.stage_job(self.s, job, self.h.hostname(), self.s.now())
            except C.Stop as e:
                self.done(oid, False, {"msg": str(e)[:300]}); return
            except Exception as e:
                self.done(oid, False, {"msg": "lỗi chuẩn bị cài lại: %s" % str(e)[:200]}); self.log(traceback.format_exc()); return
            self.log("đã ghi lệnh cài lại %s (%s) → khởi động lại vào bộ cài sau 30 giây" % (img["id"], job["wipe"]))
            self.rebooting = True
            self.h.power(reboot=True, delay=30, msg="CloudBlue: may se CAI LAI WINDOWS sau 30 giay. Du lieu tren may se bi xoa.")
            return
        self.done(oid, False, {"msg": "agent bản %s không biết lệnh '%s'" % (AGENT_VER, cmd)})

    last_manifest = None

    # ------------------------------------------------------------------ tự cập nhật
    def update(self, m, force=False):
        """Bản admin công bố khác bản đang chạy → tải, kiểm sha256, chạy thử, thay file, khởi động lại agent. Trả tên bản mới hoặc None."""
        if not isinstance(m, dict) or not m.get("ver") or not isinstance(m.get("files"), dict): return None
        ver = str(m["ver"])
        if ver == AGENT_VER or (ver == self.bad_update and not force): return None
        if "agent/pcagent.py" not in m["files"]: return None            # bản công bố phải kèm chính agent (để số bản khớp, không cập nhật lặp)
        try:
            if self.s.exists(self.p("update\\applied.txt")) and self.s.read_text(self.p("update\\applied.txt")).strip() == ver: return None
        except Exception: pass
        base = str(m.get("base") or "")
        allow = self.cfg.get("update_base") or UPDATE_BASE
        if not base.startswith(allow) or not re.fullmatch(r"[A-Za-z0-9._-]{1,24}", ver):
            self.log("bỏ qua bản cập nhật %s: nguồn không đúng kho của shop" % ver); self.bad_update = ver; return None
        try:
            got = {}
            for rel, sha in m["files"].items():
                if not UPDATE_REL.match(rel) or not re.fullmatch(r"[0-9a-f]{64}", str(sha)):
                    raise ValueError("tên file / mã kiểm không hợp lệ: %s" % rel)
                data = self.net.get(base.rstrip("/") + "/" + rel)
                if hashlib.sha256(data).hexdigest() != sha: raise ValueError("sai mã kiểm: %s" % rel)
                if rel.endswith(".py"): compile(data.decode("utf-8"), rel, "exec")
                got[rel] = data
            stage = self.p("update\\" + ver)
            for rel, data in got.items(): self.s.write_bytes(stage + "\\" + rel.replace("/", "\\"), data)
            for rel in ("lib/cbsys.py", "lib/cbcore.py", "lib/cbrec.py", "agent/pcagent.py"):       # bản thử phải đủ bộ để tự chạy
                if rel not in got:
                    try: self.s.write_bytes(stage + "\\" + rel.replace("/", "\\"), self.s.read_bytes(self.p(rel.replace("/", "\\"))))
                    except Exception: pass
            ok, out = self.h.selfcheck(stage + "\\agent\\pcagent.py")
            if not ok: raise ValueError("bản mới chạy thử không đạt: %s" % out)
            for rel, data in got.items():
                dst = self.p(rel.replace("/", "\\"))
                try:
                    if self.s.exists(dst): self.s.write_bytes(dst + ".bak", self.s.read_bytes(dst))
                except Exception: pass
                self.s.write_bytes(dst, data)
            try:                                                   # bộ cài trên phân vùng cứu hộ cũng lên bản mới
                rec = cbrec.find_recovery(self.s)
                if rec:
                    for rel, data in got.items(): self.s.write_bytes(rec.root + "cb\\" + rel.replace("/", "\\"), data)
            except Exception as e:
                self.log("chưa cập nhật được phân vùng cứu hộ: %s" % e)
            self.s.write_text(self.p("update\\applied.txt"), ver)
            self.log("ĐÃ CẬP NHẬT lên bản %s (%d file) → khởi động lại agent" % (ver, len(got)))
            self.restart = True
            return ver
        except Exception as e:
            self.log("cập nhật bản %s lỗi: %s" % (ver, e)); self.bad_update = ver
            return None

    restart = False

    # ------------------------------------------------------------------ 1 nhịp
    def poll(self, send_info=True):
        sent_ev = list(self.events) if send_info else []
        info = self.info() if send_info else None
        if sent_ev: info["ev"] = sent_ev
        body = {"p_id": self.ident["id"], "p_token": self.ident["token"], "p_info": info, "p_done": self.pending_done}
        sent_done = self.pending_done
        r = self.net.rpc("pc_poll", body)
        if r is None:
            self.fail += 1
            if self.fail in (1, 10) or self.fail % 100 == 0: self.log("chưa gọi được máy chủ (%s) — lần %d" % (self.net.last_err, self.fail))
            return None
        self.fail = 0
        if not r.get("ok"):
            if r.get("err") == "BAD_TOKEN":
                self.log("mã máy không còn dùng được → đăng ký lại")
                self.ident = dict(self.ident, token="")
                C.save_json(self.s, self.p("identity.json"), self.ident)
                self.ident = None
            return r
        if sent_done is not None and self.pending_done is sent_done:
            self.pending_done = None
            if self.result_from_rec:
                try: cbrec.take_result(self.s, clear=True)
                except Exception: pass
                self.result_from_rec = False
        self.poll_s = max(10, min(600, int(r.get("poll_s") or 30)))
        if r.get("name") and r["name"] != self.name:
            self.name = r["name"]
            try:
                idf = C.load_json(self.s, self.p("identity.json")) or {}
                idf["name"] = self.name; C.save_json(self.s, self.p("identity.json"), idf); cbrec.save_identity(self.s, idf)
            except Exception: pass
        self.last_manifest = r.get("agent")
        if sent_ev: self.events = [e for e in self.events if e not in sent_ev]
        try: self.clock_fix(r)
        except Exception: self.log("lỗi chỉnh đồng hồ: " + traceback.format_exc())
        try: self.rent_sync(r)
        except Exception: self.log("lỗi nhận hạn thuê: " + traceback.format_exc())
        return r

    def tick(self):
        """1 nhịp làm việc. Trả số giây nghỉ trước nhịp sau."""
        nap = self._tick()
        self.write_status()
        return nap

    def _tick(self):
        nap = self._work()
        if self.rebooting: return nap                               # đang khởi động lại / cài lại theo lệnh → không xét hạn thuê
        try: rn = self.rent_check()
        except Exception:
            self.log("lỗi soát hạn thuê: " + traceback.format_exc()); rn = None
        return nap if rn is None else max(1, min(nap, rn))

    def _work(self):
        self.ticks += 1
        if self.rebooting: return 30
        if not self.ident:
            if self.enroll(): return 2
            return min(900, 30 * (2 ** min(self.enroll_turn // 3, 5)))
        self.check_result()
        r = self.poll(send_info=(self.ticks % 10 == 1 or self.pending_done is not None or bool(self.events)))
        if r is None: return min(300, self.poll_s * (1 + min(self.fail, 9)))
        if not r.get("ok"): return 5
        if r.get("order"):
            try: self.handle(r["order"])
            except Exception:
                self.log("lỗi khi làm lệnh: " + traceback.format_exc())
                self.done(r["order"].get("id"), False, {"msg": "agent lỗi khi làm lệnh"})
            if self.pending_done is not None and not self.rebooting: return 2      # báo kết quả ngay ở nhịp kế
        elif self.update(self.last_manifest):
            return 1
        return self.poll_s


# ====================================================================================== chạy thật
def make_logger(base):
    path = os.path.join(base, "logs", "agent.log")

    def log(m):
        line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
                try: os.replace(path, path + ".1")
                except OSError: pass
            with open(path, "a", encoding="utf-8") as f: f.write(line + "\n")
        except OSError: pass
        try: print(line, flush=True)
        except Exception: pass
    return log


def build():
    log = make_logger(BASE)
    s = WinSys(log=lambda *a: None)
    host = WinHost()
    ag = Agent(s, host, None, BASE, log)
    ag.net = Net(ag.cfg, BASE)
    return ag, log


def cmd_run(argv):
    ag, log = build()
    if "--wait" in argv: time.sleep(3)
    for _ in range(12):                                             # bản cũ đang thoát (vừa tự cập nhật) → chờ tối đa 1 phút
        if ag.h.mutex(): break
        if "--wait" not in argv: return 0                            # đã có 1 agent đang chạy (tác vụ canh 5 phút gọi) → thôi
        time.sleep(5)
    else:
        return 0
    log("=== CloudBlue PC agent %s chạy · máy %s · %s ===" % (AGENT_VER, ag.h.hostname(), "đã có mã máy" if ag.ident else "chưa đăng ký"))
    if not ag.net.url or not ag.net.key:
        log("THIẾU sb_url / sb_key trong %s — agent chờ (không làm gì)" % ag.p("cb.json"))
    secure(ag, log)
    t_sec = time.time()
    while True:
        try: nap = ag.tick()
        except Exception:
            log("lỗi nhịp: " + traceback.format_exc()); nap = 30
        if ag.restart:
            if ag.h.restart_self(): return 0
            ag.restart = False
        since = abs(time.time() - t_sec)
        if since > 6 * 3600 or (since > 300 and ag.ident and ag.fail == 0 and vga_pending()):     # driver VGA còn chờ mạng → máy có mạng rồi thì cài nốt
            secure(ag, log); t_sec = time.time()
        time.sleep(max(1, min(900, nap)))


def vga_pending(base=BASE):
    """cb_provision còn gói driver VGA chưa cài xong (lúc đăng nhập đầu chưa có mạng / card chưa nhận driver)?"""
    try:
        with open(os.path.join(base, "logs", "vga.json"), encoding="utf-8") as f: st = json.load(f)
        return isinstance(st, dict) and st.get("state") in ("wait", "fail")
    except Exception:
        return False


def secure(ag, log):
    """Gọi pha `system` của cb_provision: khoá lại quyền thư mục C:\\CloudBluePC + phân vùng cứu hộ, và hạ tài khoản khách xuống tài khoản thường nếu
       lần đăng nhập đầu chưa làm xong. Agent chạy bằng SYSTEM nên làm được; lỗi thì ghi nhật ký rồi bỏ qua."""
    prov, py = os.path.join(BASE, "os", "cb_provision.py"), os.path.join(BASE, "py", "python.exe")
    try:
        if os.path.isfile(prov) and os.path.isfile(py):
            rc, out = ag.s.run([py, "-I", "-B", prov, "system"], timeout=3000)      # có thể kèm cài nốt driver VGA (tối đa 40 phút)
            if rc != 0: log("khoá quyền (cb_provision system) báo mã %s" % rc)
    except Exception as e:
        log("khoá quyền lỗi: %s" % e)
    try:                                                            # cb_provision thấy bảo mật bị đổi (vd tài khoản khách có lại quyền Admin) → báo về web
        ev = os.path.join(BASE, "logs", "sec.event")
        if os.path.isfile(ev):
            with open(ev, encoding="ascii", errors="replace") as f: txt = f.read(200).strip()
            os.remove(ev)
            if txt: ag.event("sec", m=txt[:120]); log("việc lạ về bảo mật: %s" % txt[:120])
    except Exception as e:
        log("đọc sec.event lỗi: %s" % e)


def cmd_selfcheck(argv):
    """Bản mới tự thử trước khi thay bản cũ: nạp đủ mô-đun, đọc cấu hình, dựng thông tin máy — không gọi mạng, không đổi gì."""
    s = WinSys(log=lambda *a: None)
    ag = Agent(s, WinHost(), None, BASE, lambda m: None)
    i = ag.info()
    assert i.get("host") and i.get("os_ver") and len(ag.calc_hw()) == 64
    assert C.CORE_VER and cbrec.REC_VER
    print("selfcheck ok", AGENT_VER)
    return 0


def cmd_status(argv):
    ag, _ = build()
    i = ag.info()
    print("CloudBlue PC agent %s" % AGENT_VER)
    print("  May:        %s  (%s %s)" % (i["host"], i.get("os_name", ""), i["os_ver"]))
    print("  Dang ky:    %s" % ("ROI - ma so may %s, ten tren web: %s" % (ag.ident["id"], ag.ident.get("name") or "?") if ag.ident else "CHUA"))
    print("  May chu:    %s" % (ag.net.url or "(chua co sb_url trong cb.json)"))
    rec = i.get("rec") or {}
    print("  Cuu ho:     %s" % ("co - doi duoc sang: " + ", ".join(rec.get("images") or []) if rec.get("ok") else "KHONG CO phan vung cuu ho (cai lai phai dung USB)"))
    print("  Phan cung:  %s - %s luong - %s GB RAM - %s" % (i.get("cpu"), i.get("cores"), i.get("ram_gb"), ", ".join(i.get("gpus") or []) or "?"))
    print("  Han thue:   %s" % ag.rent_line())
    if ag.ident:
        r = ag.net.rpc("pc_poll", {"p_id": ag.ident["id"], "p_token": ag.ident["token"], "p_info": None, "p_done": None})
        print("  Ket noi:    %s" % ("OK - %s, %s" % ("da duyet" if r.get("approved") else "CHO ADMIN DUYET", r.get("status")) if r and r.get("ok")
                                     else "LOI - %s" % ((r or {}).get("err") or ag.net.last_err)))
    return 0


def cmd_reinstall(argv):
    """cbpc reinstall <bản> [all|disk|system] — cài lại ngay tại máy (cần quyền Admin)."""
    ag, log = build()
    rec = cbrec.status(ag.s)
    if not rec.get("ok"):
        print("May nay KHONG co phan vung cuu ho CloudBlue -> cai lai phai dung USB / ISO CloudBlue."); return 2
    want = argv[0] if argv else ""
    wipe = argv[1] if len(argv) > 1 else "all"
    if want not in rec["images"] or wipe not in ("all", "disk", "system"):
        print("Cach dung:  cbpc reinstall <%s> [all|disk|system]" % "|".join(rec["images"]))
        print("   all    = xoa MOI o cung trong may (mac dinh - dung khi doi khach)")
        print("   disk   = xoa ca o he thong, cac o cung khac giu nguyen")
        print("   system = chi dinh dang lai phan vung Windows (C:), cac phan vung khac giu nguyen")
        return 2
    print("\n  SE CAI LAI WINDOWS %s - kieu xoa: %s. DU LIEU SE MAT, KHONG LAY LAI DUOC." % (want, wipe))
    if "--yes" not in argv and input("  Go  XOA  roi Enter de tiep tuc: ").strip().upper() != "XOA":
        print("  Da huy."); return 1
    job = {"id": "local-%d" % int(time.time()), "os": want, "wipe": wipe}
    if ag.ident:
        r = ag.net.rpc("pc_allow_reenroll", {"p_id": ag.ident["id"], "p_token": ag.ident["token"]})
        if r and r.get("ok"): job["ticket"], job["hw"] = r["ticket"], ag.ident.get("hw")
        else: print("  (!) Chua xin duoc ve dang ky lai (%s) - sau khi cai xong vao trang quan tri bam 'Cho dang ky lai'." % ((r or {}).get("err") or ag.net.last_err))
    try:
        cbrec.stage_job(ag.s, job, ag.h.hostname(), time.time())
    except C.Stop as e:
        print("  KHONG LAM DUOC: %s" % e); return 3
    log("cài lại tại máy: %s (%s)" % (want, wipe))
    print("  Da ghi lenh. May khoi dong lai sau 15 giay...")
    ag.h.power(reboot=True, delay=15, msg="CloudBlue: cai lai Windows.")
    return 0


def cmd_enroll(argv):
    ag, log = build()
    ag.ident = None
    for _ in range(3):
        if ag.enroll(): print("DA DANG KY: %s" % ag.ident["id"]); return 0
    print("CHUA DANG KY DUOC - xem C:\\CloudBluePC\\logs\\agent.log"); return 1


def cmd_log(argv):
    p = os.path.join(BASE, "logs", "agent.log")
    try:
        with open(p, encoding="utf-8", errors="replace") as f: print("".join(f.readlines()[-60:]))
    except OSError:
        print("(chua co nhat ky)")
    return 0


def main(argv):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    cmd = argv[0] if argv else "status"
    fn = {"run": cmd_run, "selfcheck": cmd_selfcheck, "status": cmd_status, "reinstall": cmd_reinstall, "enroll": cmd_enroll, "log": cmd_log}.get(cmd)
    if cmd in ("version", "--version"): print(AGENT_VER); return 0
    if not fn:
        print("Lenh: status | reinstall <ban> [all|disk|system] | enroll | log | version"); return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
