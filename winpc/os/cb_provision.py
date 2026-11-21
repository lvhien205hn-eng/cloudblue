# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_provision.py — CÀI ĐẶT LẦN ĐẦU trong Windows vừa cài (gọi bởi provision.cmd từ file trả lời unattend.xml)
#     specialize  (tài khoản SYSTEM, trước màn hình đăng nhập): chính sách bỏ màn hình hỏi, điện năng, tác vụ tự chạy agent, KHOÁ QUYỀN thư mục
#     firstlogon  (tài khoản vừa tạo — lúc này còn là Admin, lần đăng nhập đầu): tự đăng nhập vĩnh viễn, tác vụ, ẢNH NỀN, chạy script riêng của chủ shop
#                                                                 trong os\firstboot.d (và os\firstboot.d\<tên bản, vd 1511>), bật agent, CÀI DRIVER CARD MẠNG
#                                                                 (thiết bị chưa có driver → cài từ gói driver kèm theo), CHỜ MÁY CÓ MẠNG
#                                                                 rồi mới cài driver VGA NVIDIA, sau đó HẠ tài khoản khách xuống
#                                                                 TÀI KHOẢN THƯỜNG + khoá tài khoản Administrator có sẵn + khởi động lại 1 lần.
#                                                                 Tiến độ in ra cửa sổ lệnh trên màn hình (chữ không dấu).
#     logon       (mỗi lần đăng nhập — khoá Run, chạy bằng quyền của người đăng nhập): tài khoản chưa có ảnh nền thì đặt; có quyền quản trị thì kiểm tác vụ
#     boot        (dịch vụ khởi động do bộ cài chèn sẵn — SYSTEM, mỗi lần máy bật): lưới an toàn thứ 3 khi bản Windows không chạy file trả lời lẫn
#                                                                 SetupComplete.cmd (bản kiểu ghost): chưa có tác vụ agent thì dựng + bật agent; xong tự gỡ dịch vụ
#     system      (agent — SYSTEM — gọi lúc khởi động + định kỳ): khoá lại quyền thư mục / phân vùng cứu hộ; lần đăng nhập đầu chưa hạ quyền kịp thì làm nốt;
#                                                                 driver VGA chưa cài được ở lần đăng nhập đầu (lúc đó chưa có mạng) thì cài nốt
#  BẢO MẬT (mặc định, cb.json "user_admin": false): khách dùng tài khoản THƯỜNG, không còn tài khoản quản trị nào dùng được trên máy;
#     C:\CloudBluePC + phân vùng cứu hộ chỉ SYSTEM / Administrators vào được (tài khoản thường chỉ đọc + chạy py\ và os\ để đặt ảnh nền).
#  Mọi lệnh lỗi đều được ghi nhật ký và BỎ QUA — không bao giờ làm hỏng bước cài Windows.
#  Nhật ký: C:\CloudBluePC\logs\provision.log (phần chạy bằng tài khoản thường: %LOCALAPPDATA%\CloudBluePC\provision.log)
# =====================================================================================================
import json, os, re, secrets, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
PROV_VER = "21.11c"
TASK_AGENT, TASK_WATCH = "CloudBluePC Agent", "CloudBluePC Watch"
BOOT_SVC = "CloudBluePCBoot"            # dịch vụ khởi động bộ cài chèn vào Windows mới (cbcore.boot_service_cmds) — gọi pha `boot`
NOWIN = 0x08000000 if os.name == "nt" else 0
# Gói cài VGA NVIDIA bộ tạo ISO đặt trong os\firstboot.d[\<bản>]: tên gốc kiểu 466.77-notebook-win10-64bit-international-whql.exe hoặc đã đánh dấu nvidia-vga-…
NVIDIA_RE = re.compile(r"^(\d{3}\.\d{2}-(notebook|desktop)-.*|nvidia-vga-.*)\.exe$", re.I)
VGA_TRIES = 3                            # chạy bộ cài VGA tối đa 3 lần (lần đăng nhập đầu + các lần agent gọi lại)
NET_WAIT_VGA, NET_WAIT = 240, 60         # lần đăng nhập đầu chờ mạng tối đa: 4 phút khi có gói VGA phải cài, 1 phút khi không
DRV_SETTLE = 30                          # bước driver: sau khi bảo Windows cài lại thiết bị chưa có driver, chờ card mạng nhận driver tối đa 30 giây (5 giây xem 1 lần)
DRV_PNPUTIL_MAX = 12                     # card mạng vẫn chưa nhận: chạy pnputil cho tối đa 12 gói driver MẠNG đang nằm trong kho driver
DRV_KICKS = 3                            # bước driver chạy tối đa 3 lần cho 1 máy (lần đăng nhập đầu + các lần agent gọi lại khi máy vẫn chưa có card mạng chạy được)
VGA_CMD_MARK = "cai driver VGA NVIDIA im lang"      # dấu của file 50-vga-nvidia.cmd do bộ tạo ISO bản cũ sinh ra (nay cb_provision tự cài → bỏ qua file đó)

GHOST_SKIP_RIDS = (500, 501, 503, 504)      # Administrator · Guest · DefaultAccount · WDAGUtilityAccount có sẵn của Windows: không nhận làm tài khoản khách
GHOST_TELL_WAIT = 25                         # bản ghost: chờ Windows tự đăng nhập xong rồi mới hiện lời báo "đang hoàn tất cài đặt" lên màn hình

TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CloudBlue PC agent</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT15S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{PYW}</Command>
      <Arguments>-I -B "{AGENT}" run</Arguments>
      <WorkingDirectory>{BASE}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def spi_wallpaper(path):
    """Đặt ảnh nền cho tài khoản đang đăng nhập (SPI_SETDESKWALLPAPER, ghi vào hồ sơ + báo cho Windows). True nếu được."""
    import ctypes
    return bool(ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3))


def pick_ghost_user(users, hints, want):
    """Bản Windows kiểu ghost đã có sẵn tài khoản → chọn tài khoản để NHẬN làm tài khoản khách (giữ nguyên hồ sơ: màn hình nền, phần mềm cài sẵn).
       users = [{"name", "rid", "off"}] · hints = tên tài khoản Windows đang tự đăng nhập / đăng nhập gần nhất (ưu tiên từ trái sang) · want = tên tài khoản khách.
       Trả (tên, kiểu):  (tên, "have") đã có đúng tên đó · (tên, "adopt") nhận tài khoản này rồi đổi tên · (None, "new") phải tạo mới ·
       (None, "bia") tên muốn dùng trùng tài khoản có sẵn của Windows (Administrator, Guest…) — không dùng được."""
    low = {u["name"].lower(): u for u in users}
    u = low.get((want or "").lower())
    if u: return (None, "bia") if u["rid"] in GHOST_SKIP_RIDS else (u["name"], "have")
    ok = [x for x in users if x["rid"] >= 1000 and not x["off"]]
    for h in hints:
        h = (h or "").replace("/", "\\").split("\\")[-1].strip().lower()
        if not h: continue
        u = low.get(h)
        if u is not None and u in ok: return u["name"], "adopt"
        if u is not None and u["rid"] == 500: return None, "new"      # ảnh ghost dùng thẳng tài khoản Administrator có sẵn: không hạ quyền được → tạo tài khoản mới
    if len(ok) == 1: return ok[0]["name"], "adopt"
    return None, "new"


def real_blank_pw(user):
    """Tài khoản cục bộ `user` có mật khẩu TRỐNG không? Thử đăng nhập bằng mật khẩu rỗng: được, hoặc bị từ chối vì "tài khoản mật khẩu trống chỉ đăng nhập tại máy"
       (lỗi 1327) → True; sai mật khẩu (1326) → False; lỗi khác → None."""
    try:
        import ctypes
        from ctypes import wintypes
        a = ctypes.WinDLL("advapi32", use_last_error=True)
        a.LogonUserW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        h = wintypes.HANDLE()
        if a.LogonUserW(user, ".", "", 2, 0, ctypes.byref(h)):       # LOGON32_LOGON_INTERACTIVE, LOGON32_PROVIDER_DEFAULT
            ctypes.WinDLL("kernel32").CloseHandle(h); return True
        err = ctypes.get_last_error()
        return True if err == 1327 else False if err == 1326 else None
    except Exception:
        return None


def real_net(host, port, timeout=4):
    """Máy tới được `host:port` không (đã có driver card mạng + địa chỉ IP + đường ra ngoài)?"""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout): return True
    except OSError:
        return False


def real_nvidia_state():
    """(máy có card màn hình NVIDIA không, card đã nhận driver NVIDIA chưa) — đọc danh sách thiết bị PCI trong registry, không cần WMI / PowerShell.
       Không đọc được → (None, None)."""
    try:
        import winreg
        have = ok = False
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\PCI") as k:
            i = 0
            while True:
                try: dev = winreg.EnumKey(k, i)
                except OSError: break
                i += 1
                if not dev.upper().startswith("VEN_10DE"): continue           # 10DE = NVIDIA
                try: kd = winreg.OpenKey(k, dev)
                except OSError: continue
                with kd:
                    j = 0
                    while True:
                        try: inst = winreg.EnumKey(kd, j)
                        except OSError: break
                        j += 1
                        try:
                            with winreg.OpenKey(kd, inst) as ki:
                                def val(n):
                                    try: return winreg.QueryValueEx(ki, n)[0]
                                    except OSError: return None
                                ids = val("CompatibleIDs") or []
                                if isinstance(ids, str): ids = [ids]
                                if not any("CC_03" in str(x).upper() for x in ids): continue    # lớp 03 = card màn hình (bỏ qua cổng âm thanh / USB của card)
                                have = True
                                if str(val("Service") or "").lower() == "nvlddmkm": ok = True
                        except OSError:
                            continue
        return have, ok
    except Exception:
        return None, None


def _cbsys():
    lib = os.path.join(BASE, "lib")
    if lib not in sys.path: sys.path.insert(0, lib)
    import cbsys
    return cbsys


def real_devices():
    """Danh sách thiết bị đang cắm của máy (cbsys.pnp_devices — như Device Manager). Không đọc được → None."""
    try: return _cbsys().pnp_devices()
    except Exception: return None


def real_pnp_retry():
    """Bảo Windows dò lại phần cứng + cài lại thiết bị chưa có driver từ kho driver. True nếu ra lệnh được."""
    try: return _cbsys().pnp_retry() == 0
    except Exception: return False


def real_staged():
    """Gói driver bên thứ ba đang nằm trong kho driver của Windows: [{"pub", "inf"}]. Không đọc được → []."""
    try: return _cbsys().staged_infs()
    except Exception: return []


def real_recovery_root():
    """Đường dẫn gốc (\\\\?\\Volume{…}\\) của phân vùng cứu hộ trên máy này; không có → ''."""
    try:
        lib = os.path.join(BASE, "lib")
        if lib not in sys.path: sys.path.insert(0, lib)
        import cbsys, cbrec
        v = cbrec.find_recovery(cbsys.WinSys(log=lambda *a: None))
        return v.root if v else ""
    except Exception:
        return ""


class Prov:
    def __init__(self, base=BASE, run=None, log=None, spi=None, admin=None, rec=None, now=None, net=None, gpu=None, sleep=None, say=None, blank=None,
                 devs=None, pnp=None, staged=None):
        self.base = base
        self._run = run or self._real_run
        self._spi = spi or spi_wallpaper
        self._admin = admin                     # None = hỏi Windows; True / False = phép thử ép sẵn
        self._rec = rec or real_recovery_root
        self._now = now or time.time
        self._net = net or real_net             # (host, port) → tới được không
        self._gpu = gpu or real_nvidia_state    # () → (có card NVIDIA, card đã có driver NVIDIA)
        self._sleep = sleep or time.sleep
        self._say = say
        self._blank = blank or real_blank_pw    # (tên tài khoản) → mật khẩu đang trống?
        self._devs = devs or real_devices       # () → danh sách thiết bị đang cắm (None = không đọc được)
        self._pnp = pnp or real_pnp_retry       # () → bảo Windows cài lại thiết bị chưa có driver
        self._staged = staged or real_staged    # () → gói driver bên thứ ba trong kho driver
        self.lines = []
        self._log = log

    def say(self, m):
        """1 dòng tiến độ ra cửa sổ lệnh (lần đăng nhập đầu có cửa sổ hiện trên màn hình) — chữ KHÔNG DẤU. Không có cửa sổ thì thôi."""
        if self._say: self._say(m); return
        try: print("  " + m, flush=True)
        except Exception: pass

    def log(self, m):
        ln = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        self.lines.append(ln)
        if self._log: self._log(ln); return
        dirs = [os.path.join(self.base, "logs")]
        if os.environ.get("LOCALAPPDATA"): dirs.append(os.path.join(os.environ["LOCALAPPDATA"], "CloudBluePC"))   # tài khoản thường không ghi được vào C:\CloudBluePC
        for d in dirs:
            try:
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "provision.log"), "a", encoding="utf-8") as f: f.write(ln + "\n")
                return
            except OSError: continue

    def is_admin(self):
        """Tiến trình này có quyền quản trị không (SYSTEM, hoặc tài khoản Admin đã nâng quyền)?"""
        if self._admin is not None: return bool(self._admin)
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def mark(self, name):
        return os.path.join(self.base, "logs", name)

    def touch(self, name):
        try:
            os.makedirs(os.path.join(self.base, "logs"), exist_ok=True)
            if not os.path.exists(self.mark(name)):
                with open(self.mark(name), "w") as f: f.write(str(int(self._now())))
        except OSError: pass

    def mark_age(self, name):
        """Số giây từ lúc đặt mốc `name`; chưa có mốc → None."""
        try:
            with open(self.mark(name)) as f: return max(0, int(self._now()) - int((f.read().strip() or "0")))
        except (OSError, ValueError):
            return None

    def _real_run(self, argv, timeout=300):
        """Chạy 1 lệnh, trả (mã thoát, đoạn cuối chữ in ra). Chữ in ra hứng vào FILE TẠM chứ không qua ống dẫn: bộ cài driver / script của chủ shop hay để lại
           tiến trình con chạy nền — hứng bằng ống dẫn thì phải chờ tới khi tiến trình con đó thoát (có khi không bao giờ). Không cho lệnh đọc bàn phím."""
        try:
            with tempfile.TemporaryFile() as out:
                r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, timeout=timeout, creationflags=NOWIN)
                out.seek(0, 2); n = out.tell(); out.seek(max(0, n - 16000))
                return r.returncode, out.read().decode("utf-8", "replace").strip()[-4000:]
        except Exception as e:
            return 127, str(e)

    def sh(self, argv, what=None, timeout=300):
        rc, out = self._run(argv, timeout)
        self.log("%s %s%s" % ("ok " if rc == 0 else "LOI(%s)" % rc, what or " ".join(argv[:4]), "" if rc == 0 else " :: " + out.replace("\n", " ")[-200:]))
        return rc == 0

    def reg(self, key, name, typ, val):
        return self.sh(["reg", "add", key, "/v", name, "/t", typ, "/d", str(val), "/f"], "reg %s\\%s=%s" % (key.split("\\")[-1], name, "(an)" if "Password" in name else val))

    def cfg(self):
        try:
            with open(os.path.join(self.base, "cb.json"), encoding="utf-8-sig") as f: return json.load(f)
        except Exception:
            return {}

    # ------------------------------------------------------------------ các phần
    def pw_never_expires(self):
        """Tài khoản do file trả lời tạo có mật khẩu HẾT HẠN sau 42 ngày (mặc định của Windows) — kể cả mật khẩu trống. Tới ngày đó Windows bắt đổi mật khẩu lúc đăng nhập,
           mà tài khoản khách bị cấm tự đổi mật khẩu → kẹt ở màn hình đăng nhập. Bỏ hạn mật khẩu cho cả máy (1 lần là đủ, làm lại vô hại)."""
        if os.path.exists(self.mark("pwage.done")): return True
        ok = self.sh(["net", "accounts", "/maxpwage:unlimited"], "mat khau tai khoan khong het han (mac dinh Windows: 42 ngay)")
        if ok: self.touch("pwage.done")
        return ok

    def policies(self):
        self.pw_never_expires()
        self.reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\OOBE", "DisablePrivacyExperience", "REG_DWORD", 1)          # bỏ trang "quyền riêng tư" lúc đăng nhập đầu
        self.reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization", "NoLockScreen", "REG_DWORD", 1)           # không màn hình khoá
        self.reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "PromptOnSecureDesktop", "REG_DWORD", 0)   # hộp hỏi quyền hiện trên màn hình thường
        self.reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "CloudBluePC", "REG_SZ",       # mỗi lần đăng nhập: kiểm tác vụ (không hiện cửa sổ)
                 '"%s" -I -B "%s" logon' % (os.path.join(self.base, "py", "pythonw.exe"), os.path.join(self.base, "os", "cb_provision.py")))

    def power(self):
        self.sh(["powercfg", "/hibernate", "off"], "tat ngu dong")
        for k in ("standby-timeout-ac", "standby-timeout-dc", "hibernate-timeout-ac", "hibernate-timeout-dc", "monitor-timeout-ac", "disk-timeout-ac"):
            self.sh(["powercfg", "/change", k, "0"], "dien nang %s=0" % k)

    def tasks(self):
        """Tác vụ chạy agent bằng SYSTEM lúc khởi động + tác vụ canh 5 phút / lần (agent chết thì dựng lại)."""
        pyw = os.path.join(self.base, "py", "pythonw.exe")
        agent = os.path.join(self.base, "agent", "pcagent.py")
        xml = os.path.join(self.base, "os", "task-agent.xml")
        ok = False
        try:
            with open(xml, "w", encoding="utf-16") as f: f.write(TASK_XML.format(PYW=pyw, AGENT=agent, BASE=self.base))
            ok = self.sh(["schtasks", "/create", "/tn", TASK_AGENT, "/xml", xml, "/f"], "tac vu agent (XML)")
        except OSError as e:
            self.log("LOI ghi %s: %s" % (xml, e))
        watch = os.path.join(self.base, "agent", "watch.cmd")
        if not ok:                                                 # dự phòng: kiểu tạo đơn giản (bị giới hạn 3 ngày → tác vụ canh sẽ dựng lại)
            ok = self.sh(["schtasks", "/create", "/tn", TASK_AGENT, "/sc", "onstart", "/ru", "SYSTEM", "/rl", "highest", "/tr", watch, "/f"], "tac vu agent (don gian)")
        ok2 = self.sh(["schtasks", "/create", "/tn", TASK_WATCH, "/sc", "minute", "/mo", "5", "/ru", "SYSTEM", "/rl", "highest", "/tr", watch, "/f"], "tac vu canh 5 phut")
        return ok and ok2

    def autologon(self, domain=None):
        """Tự đăng nhập bằng tài khoản khách. domain = tên máy SẼ dùng sau lần khởi động lại (bản ghost vừa bị đổi tên máy); bỏ trống = tên máy hiện tại."""
        c = self.cfg()
        user, pw = c.get("user") or "PC", c.get("password") or ""
        wl = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
        self.reg(wl, "AutoAdminLogon", "REG_SZ", 1)
        self.reg(wl, "DefaultUserName", "REG_SZ", user)
        self.reg(wl, "DefaultDomainName", "REG_SZ", domain or os.environ.get("COMPUTERNAME", "."))
        self.reg(wl, "DefaultPassword", "REG_SZ", pw)
        self._run(["reg", "delete", wl, "/v", "AutoLogonCount", "/f"], 60)          # bỏ bộ đếm → tự đăng nhập mãi (không hết sau N lần)

    def shortcut(self):
        """cbpc.cmd ở gốc C:\\CloudBluePC cho tiện gõ lệnh."""
        try:
            src, dst = os.path.join(self.base, "agent", "cbpc.cmd"), os.path.join(self.base, "cbpc.cmd")
            if os.path.isfile(src):
                with open(src, "rb") as fi, open(dst, "wb") as fo: fo.write(fi.read())
        except OSError: pass

    def os_tag(self):
        """Tên bản Windows vừa cài (22h2, 1511…) do bộ cài ghi trong seed.json; không có → ''."""
        try:
            with open(os.path.join(self.base, "seed.json"), encoding="utf-8-sig") as f: t = str(json.load(f).get("os") or "")
        except Exception:
            t = ""
        return t.lower() if re.fullmatch(r"[A-Za-z0-9-]{2,12}", t) else ""

    def wallpaper(self):
        """Đặt ảnh nền CloudBlue (os\\wallpaper.jpg) cho tài khoản đang đăng nhập. Mỗi tài khoản chỉ đặt 2 LẦN ĐẦU (lần đăng nhập đầu tiên Windows
           có thể tự trả về ảnh mặc định ngay sau khi hiện màn hình → lần chạy kế tiếp đặt lại 1 lần nữa); sau đó khách đổi ảnh khác thì giữ ảnh của khách."""
        img = next((p for p in (os.path.join(self.base, "os", n) for n in ("wallpaper.jpg", "wallpaper.png", "wallpaper.bmp")) if os.path.isfile(p)), None)
        if not img: return False
        mark = r"HKCU\Software\CloudBluePC"
        if self._run(["reg", "query", mark, "/v", "Wallpaper2"], 60)[0] == 0: return False
        step = "Wallpaper2" if self._run(["reg", "query", mark, "/v", "Wallpaper"], 60)[0] == 0 else "Wallpaper"
        desk = r"HKCU\Control Panel\Desktop"
        self.reg(desk, "WallpaperStyle", "REG_SZ", 10)             # 10 = phủ kín màn hình (Fill), giữ tỉ lệ
        self.reg(desk, "TileWallpaper", "REG_SZ", 0)
        try: ok = bool(self._spi(img))
        except Exception as e:
            ok = False; self.log("LOI dat anh nen: %r" % (e,))
        if not ok:                                                 # dự phòng: ghi thẳng vào hồ sơ, Windows áp dụng ở lần đăng nhập sau
            ok = self.reg(desk, "Wallpaper", "REG_SZ", img)
            self._run(["rundll32.exe", "user32.dll,UpdatePerUserSystemParameters", "1", "True"], 60)
        self.log("%s anh nen %s" % ("ok " if ok else "LOI", os.path.basename(img)))
        if ok: self.reg(mark, step, "REG_SZ", PROV_VER)
        return ok

    def firstboot(self):
        """Chạy 1 LẦN các script của chủ shop: os\\firstboot.d\\*.cmd|*.bat|*.ps1 rồi os\\firstboot.d\\<tên bản Windows, vd 1511>\\* (theo thứ tự tên)
           — cài driver dạng .exe, phần mềm… Script đọc được biến CB_OS (tên bản đang cài)."""
        d, mark = os.path.join(self.base, "os", "firstboot.d"), os.path.join(self.base, "logs", "firstboot.done")
        if os.path.exists(mark) or not os.path.isdir(d): return 0
        tag = self.os_tag()
        os.environ["CB_OS"] = tag
        todo = [(d, f) for f in sorted(os.listdir(d))]
        for sub in dict.fromkeys([tag, re.sub(r"-\d+$", "", tag)]):       # '22h2-2' dùng cả thư mục 22h2-2 lẫn 22h2
            sd = os.path.join(d, sub) if sub else ""
            if sd and os.path.isdir(sd): todo += [(sd, f) for f in sorted(os.listdir(sd))]
        n = 0
        for folder, f in todo:
            p, ext = os.path.join(folder, f), f.lower().rsplit(".", 1)[-1]
            if not os.path.isfile(p): continue
            if ext in ("cmd", "bat"): argv = ["cmd.exe", "/c", p]
            elif ext == "ps1": argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", p]
            else: continue
            if f.lower() == "50-vga-nvidia.cmd" and self.is_old_vga_cmd(p):      # bộ tạo ISO bản cũ sinh: nay tự cài ở bước VGA (sau khi có mạng)
                self.log("bo qua %s (ban cu) - goi VGA do buoc VGA cai sau khi co mang" % os.path.relpath(p, d)); continue
            self.say("    chay %s ..." % os.path.relpath(p, d))
            self.sh(argv, "script rieng " + os.path.relpath(p, d), timeout=3600); n += 1
        try:
            os.makedirs(os.path.dirname(mark), exist_ok=True)
            with open(mark, "w") as fo: fo.write(str(n))
        except OSError: pass
        return n

    def is_old_vga_cmd(self, path):
        try:
            with open(path, "rb") as f: return VGA_CMD_MARK.encode("ascii") in f.read(600)
        except OSError:
            return False

    # ------------------------------------------------------------------ driver CARD MẠNG (làm TRƯỚC khi chờ mạng; có mạng rồi mới tới driver VGA)
    def drv_state(self):
        """Tóm tắt driver của máy lúc này (cbcore.drv_summary: miss / net_miss / nics / vga_basic). Không đọc được danh sách thiết bị → None."""
        try: devs = self._devs()
        except Exception: devs = None
        if devs is None: return None
        try: return self.core().drv_summary(devs)
        except Exception as e:
            self.log("LOI tom tat thiet bi: %r" % (e,)); return None

    def drv_text(self, st, n=4):
        lab = self.core().drv_label
        return "; ".join(lab(x) for x in st["miss"][:n]) + (" ... (+%d)" % (len(st["miss"]) - n) if len(st["miss"]) > n else "")

    def drv_kicks(self):
        try:
            with open(self.mark("drv.json"), encoding="utf-8") as f: return max(0, int(json.load(f).get("kicks") or 0))
        except Exception:
            return 0

    def drv_mark(self, st, kicks):
        """Ghi logs\\drv.json: lần soát driver gần nhất (để xem tại máy + để đếm số lần đã chạy bước driver)."""
        try:
            lab = self.core().drv_label
            os.makedirs(os.path.join(self.base, "logs"), exist_ok=True)
            with open(self.mark("drv.json"), "w", encoding="utf-8") as f:
                json.dump({"at": int(self._now()), "kicks": int(kicks), "miss": [lab(x) for x in st["miss"][:12]], "net_miss": st["net_miss"],
                           "nics": st["nics"][:4], "vga_basic": st["vga_basic"]}, f)
        except Exception: pass

    def drv_pnputil(self):
        """Chạy `pnputil -i -a` cho từng gói driver CARD MẠNG bên thứ ba đang nằm trong kho driver (bộ cài đã nạp từ gói chủ shop kèm theo) — cài ngay lên thiết bị khớp.
           Cú pháp cũ `-i -a` chạy được từ Windows 10 bản 1507 tới bản mới nhất. Trả số gói đã chạy."""
        try: staged = self._staged() or []
        except Exception: staged = []
        C, todo = self.core(), []
        for x in staged:
            cls = x.get("cls")
            if cls is None:
                try:
                    with open(x["inf"], "rb") as f: cls = C.inf_class(f.read(2 << 20))
                except Exception: cls = ""
            if cls == "net": todo.append(x)
        if not todo:
            self.log("kho driver cua Windows KHONG co goi driver card mang nao cua ben thu ba (goi driver kem theo khong co driver card mang?)"); return 0
        exe = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "pnputil.exe")
        for x in todo[:DRV_PNPUTIL_MAX]:
            rc, out = self._run([exe, "-i", "-a", x["inf"]], 600)
            if rc != 0 and "/add-driver" in (out or "").lower():      # bản Windows nào đó bỏ cú pháp cũ (in ra hướng dẫn cú pháp mới) → gọi cú pháp mới
                rc, out = self._run([exe, "/add-driver", x["inf"], "/install"], 600)
            self.log("pnputil: cai goi driver card mang %s (%s) -> ma %s%s" % (os.path.basename(x["inf"]), x.get("pub", "?"), rc,
                                                                          "" if rc == 0 else " :: " + (out or "").replace("\r", " ").replace("\n", " ")[-160:]))
        return len(todo[:DRV_PNPUTIL_MAX])

    def drivers(self, show=True):
        """BƯỚC DRIVER CARD MẠNG — chạy TRƯỚC khi chờ mạng (driver VGA chỉ cài sau khi máy đã có mạng):
             1. soát thiết bị: mọi thứ đã có driver → xong ngay, không đụng gì
             2. còn thiết bị chưa có driver → bảo Windows dò lại phần cứng + cài lại từ kho driver (bộ cài đã nạp sẵn gói driver chủ shop kèm theo vào kho)
             3. chờ card mạng nhận driver (tối đa DRV_SETTLE giây); vẫn chưa → pnputil cài thẳng từng gói driver card mạng trong kho
           Trả tóm tắt sau cùng (cbcore.drv_summary) — None nếu không đọc được danh sách thiết bị (khi đó để Windows tự nhận như cũ)."""
        st = self.drv_state()
        if st is None:
            self.log("khong doc duoc danh sach thiet bi cua may - bo qua buoc driver (Windows van tu nhan driver da nap)"); return None
        kicks = self.drv_kicks()
        if not st["miss"]:
            self.log("ok  moi thiet bi da co driver; card mang: %s" % (", ".join(st["nics"]) or "KHONG THAY card mang nao"))
            self.drv_mark(st, kicks); return st
        self.log("thiet bi CHUA CO DRIVER: %d (%s); card mang da nhan driver: %s" % (len(st["miss"]), self.drv_text(st, 8), ", ".join(st["nics"]) or "chua co"))
        if show: self.say("    %d thiet bi chua co driver -> cai tu goi driver kem theo (card mang truoc) ..." % len(st["miss"]))
        try: ok = bool(self._pnp())
        except Exception: ok = False
        self.log("%s bao Windows do lai phan cung + cai lai thiet bi chua co driver tu kho driver" % ("ok " if ok else "LOI"))
        cur, t0 = st, self._now()
        while self._now() - t0 < DRV_SETTLE:
            self._sleep(5)
            cur = self.drv_state() or cur
            if not cur["net_miss"] and (cur["nics"] or not cur["miss"]): break
        if cur["net_miss"] or (cur["miss"] and not cur["nics"]):       # card mạng vẫn chưa nhận driver → cài thẳng từng gói driver card mạng
            if self.drv_pnputil():
                self._sleep(5); cur = self.drv_state() or cur
        self.drv_mark(cur, kicks + 1)
        self.log("sau buoc driver: con %d thiet bi chua co driver%s; card mang da nhan driver: %s" % (
            len(cur["miss"]), (" (%s)" % self.drv_text(cur, 8)) if cur["miss"] else "", ", ".join(cur["nics"]) or "CHUA CO"))
        return cur

    def drv_say(self, st):
        """In tình trạng driver ra cửa sổ tiến độ (chữ không dấu)."""
        if st is None: return
        if st["miss"]: self.say("    con %d thiet bi chua co driver: %s" % (len(st["miss"]), self.drv_text(st)))
        if st["net_miss"]:
            self.say("    !! CARD MANG CHUA CO DRIVER: %s" % "; ".join(self.core().drv_label(x) for x in st["miss"] if x["k"] == "net")[:150])
            self.say("       Goi driver kem theo khong co driver cho loai card nay -> may chua co mang.")
        elif not st["nics"]:
            self.say("    !! Khong thay card mang nao da nhan driver -> may chua co mang.")
        else:
            self.say("    card mang da nhan driver: %s" % ", ".join(st["nics"][:2])[:150])

    def drv_retry(self):
        """Agent (pha system) gọi: lần đăng nhập đầu đã xong mà máy vẫn chưa có card mạng chạy được → làm lại bước driver (cả máy tối đa DRV_KICKS lần).
           Máy đã ổn thì chỉ ghi lại tình trạng."""
        st = self.drv_state()
        if st is None: return None
        kicks = self.drv_kicks()
        if kicks >= DRV_KICKS or not (st["net_miss"] or (st["miss"] and not st["nics"])):
            self.drv_mark(st, kicks); return st
        return self.drivers(show=False)

    # ------------------------------------------------------------------ mạng + driver VGA
    def net_target(self):
        """Nơi thử kết nối: máy chủ của hệ thống (sb_url trong cb.json); không có thì 1 địa chỉ kiểm mạng của Microsoft."""
        m = re.match(r"^https?://([A-Za-z0-9.-]+)", str(self.cfg().get("sb_url") or ""))
        return (m.group(1), 443) if m else ("www.msftconnecttest.com", 80)

    def net_wait(self, limit):
        """Chờ máy RA ĐƯỢC MẠNG (driver card mạng đã chạy, có địa chỉ IP, tới được máy chủ). Trả số giây đã chờ; hết `limit` giây vẫn chưa có → None."""
        host, port = self.net_target()
        t0 = self._now()
        while True:
            try: ok = bool(self._net(host, port))
            except Exception: ok = False
            if ok: return max(0, int(self._now() - t0))
            if self._now() - t0 >= limit: return None
            self._sleep(3)

    def vga_packs(self):
        """Các gói cài VGA NVIDIA (.exe) nằm trong os\\firstboot.d và os\\firstboot.d\\<tên bản Windows đang chạy>."""
        d, tag, out = os.path.join(self.base, "os", "firstboot.d"), self.os_tag(), []
        for sub in dict.fromkeys(["", tag, re.sub(r"-\d+$", "", tag)]):
            folder = os.path.join(d, sub) if sub else d
            if not os.path.isdir(folder): continue
            out += [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if NVIDIA_RE.match(f) and os.path.isfile(os.path.join(folder, f))]
        return out

    def vga_needed(self):
        """Còn gói VGA NVIDIA phải cài không (có gói + máy có card NVIDIA chưa nhận driver, hoặc không đọc được danh sách thiết bị)?"""
        if not self.vga_packs(): return False
        try: have, ok = self._gpu()
        except Exception: have, ok = None, None
        return have is not False and not ok

    def vga_state(self):
        try:
            with open(self.mark("vga.json"), encoding="utf-8") as f: st = json.load(f)
            return st if isinstance(st, dict) else {}
        except Exception:
            return {}

    def vga_mark(self, state, tries):
        try:
            os.makedirs(os.path.join(self.base, "logs"), exist_ok=True)
            with open(self.mark("vga.json"), "w", encoding="utf-8") as f: json.dump({"state": state, "tries": int(tries), "at": int(self._now())}, f)
        except OSError: pass

    def vga_drop(self, packs):
        """Xoá bản chép gói VGA trên ổ C: (700MB+; phân vùng cứu hộ vẫn giữ để cài lại) + thư mục giải nén tạm C:\\NVIDIA của bộ cài."""
        for p in packs:
            try: os.remove(p)
            except OSError: pass
        tmp = os.path.join(os.path.splitdrive(self.base)[0] + os.sep, "NVIDIA")
        if os.path.isdir(os.path.join(tmp, "DisplayDriver")):
            self._run(["cmd.exe", "/c", "rd", "/s", "/q", os.path.join(tmp, "DisplayDriver")], 300)
            try: os.rmdir(tmp)
            except OSError: pass

    def vga(self, net_ok):
        """Cài driver VGA NVIDIA bằng gói .exe chủ shop kèm theo — CHỈ KHI máy đã ra được mạng (net_ok: True / False hoặc hàm trả True / False):
           driver card mạng phải xong trước, vì bản Windows cũ
           (1511…) cần mạng để lấy chứng chỉ gốc thì bộ cài NVIDIA mới kiểm được chữ ký. Trả:
             'none'  không có gói nào (hoặc đã xử lý xong từ trước)      'skip'  máy không có card NVIDIA → bỏ qua, xoá bản chép gói
             'done'  card đã nhận driver NVIDIA                          'wait'  chưa có mạng → agent (SYSTEM) cài sau khi máy có mạng
             'fail'  đã chạy bộ cài mà card chưa nhận driver (sau khởi động lại agent kiểm lại; chạy lại tối đa VGA_TRIES lần)"""
        packs = self.vga_packs()
        if not packs: return "none"
        names = ", ".join(os.path.basename(p) for p in packs)
        st = self.vga_state()
        tries = int(st.get("tries") or 0) if str(st.get("tries") or "0").isdigit() else 0
        try: have, ok = self._gpu()
        except Exception: have, ok = None, None
        if have is False:
            self.log("may nay KHONG co card NVIDIA - bo qua goi VGA (%s)" % names)
            self.vga_drop(packs); self.vga_mark("skip", tries); return "skip"
        if ok:
            self.log("card NVIDIA da co driver - khong can cai goi VGA (%s)" % names)
            self.vga_drop(packs); self.vga_mark("done", tries); return "done"
        if tries >= VGA_TRIES:
            if st.get("state") != "gave-up":
                self.log("LOI goi VGA: da chay %d lan ma card NVIDIA van chua nhan driver - thoi khong thu nua (%s)" % (tries, names)); self.vga_mark("gave-up", tries)
            return "fail"
        if not (net_ok() if callable(net_ok) else net_ok):           # chỉ thử mạng khi thật sự sắp chạy bộ cài
            self.log("chua co mang - CHUA cai goi VGA (%s); agent se cai khi may co mang" % names)
            self.vga_mark("wait", tries); return "wait"
        for p in packs:
            self.say("    cai %s (5-15 phut, man hinh co the nhay) ..." % os.path.basename(p))
            self.sh([p, "-s", "-noreboot"], "cai VGA NVIDIA %s" % os.path.basename(p), timeout=2400)
        tries += 1
        try: have2, ok2 = self._gpu()
        except Exception: have2, ok2 = None, None
        if ok2 or have2 is None:                                     # không đọc được danh sách thiết bị → coi như xong (không chạy lại mãi)
            self.log("ok  driver VGA NVIDIA da vao%s" % ("" if ok2 else " (khong kiem lai duoc)"))
            self.vga_drop(packs); self.vga_mark("done", tries); return "done"
        self.log("goi VGA da chay (lan %d) nhung card chua nhan driver - kiem lai sau khi khoi dong lai" % tries)
        self.vga_mark("fail", tries); return "fail"

    # ------------------------------------------------------------------ bảo mật
    def core(self):
        lib = os.path.join(self.base, "lib")
        if lib not in sys.path: sys.path.insert(0, lib)
        import cbcore
        return cbcore

    def lockdown(self):
        """Khoá quyền C:\\CloudBluePC (chỉ SYSTEM + Administrators; tài khoản thường chỉ đọc + chạy py\\ và os\\) và gốc phân vùng cứu hộ.
           Cần quyền quản trị. Trả True nếu mọi lệnh icacls đều xong."""
        try:
            cbcore = self.core()
            cmds, vol = cbcore.acl_lock_cmds(self.base), cbcore.acl_vol_cmds
        except Exception as e:
            self.log("LOI nap cbcore de khoa quyen: %r" % (e,)); return False
        if not os.path.isdir(os.path.join(self.base, "os", "firstboot.d")): cmds = cmds[:-1]
        bad = sum(1 for argv in cmds if self._run(argv, 900)[0] != 0)
        self.log("%s khoa quyen thu muc %s%s" % ("ok " if not bad else "LOI", self.base, "" if not bad else " (%d / %d lenh bao loi)" % (bad, len(cmds))))
        try: root = self._rec() or ""
        except Exception: root = ""
        if root:
            bad2 = sum(1 for argv in vol(root) if self._run(argv, 900)[0] != 0)
            self.log("%s khoa quyen phan vung cuu ho%s" % ("ok " if not bad2 else "LOI", "" if not bad2 else " (%d lenh bao loi)" % bad2))
            bad += bad2
        self.touch("lock.done")
        return not bad

    def names(self):
        """Tên (theo ngôn ngữ của Windows đang chạy) của nhóm Administrators, nhóm Users và tài khoản Administrator có sẵn. Không hỏi được → tên tiếng Anh."""
        ps = ("$a=([Security.Principal.SecurityIdentifier]'S-1-5-32-544').Translate([Security.Principal.NTAccount]).Value.Split('\\')[-1];"
              "$u=([Security.Principal.SecurityIdentifier]'S-1-5-32-545').Translate([Security.Principal.NTAccount]).Value.Split('\\')[-1];"
              "$o=(Get-WmiObject Win32_UserAccount -Filter 'LocalAccount=True' | Where-Object { $_.SID -like 'S-1-5-21-*-500' } | Select-Object -First 1);"
              "$b=$o.Name;"
              "Write-Output ('ADM=' + $a + '|USR=' + $u + '|BIA=' + $b + '|DIS=' + $o.Disabled + '|')")
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 180)
        m = re.search(r"ADM=([^|\r\n]*)\|USR=([^|\r\n]*)\|BIA=([^|\r\n]*)\|", out or "")
        adm, usr, bia = (m.group(1).strip(), m.group(2).strip(), m.group(3).strip()) if (rc == 0 and m) else ("", "", "")
        d = re.search(r"\|DIS=(True|False)\|", out or "") if rc == 0 else None
        self.bia_off = None if not d else d.group(1) == "True"          # tài khoản Administrator có sẵn đang TẮT? (None = không hỏi được)
        return adm or "Administrators", usr or "Users", bia or "Administrator"

    bia_off = None

    def admin_members(self, adm):
        """Tên các thành viên nhóm quản trị (PowerShell + ADSI: không phụ thuộc ngôn ngữ Windows). Không hỏi được → None."""
        ps = ("$g=[ADSI]('WinNT://./%s,group'); @($g.psbase.Invoke('Members')) | ForEach-Object "
              "{ Write-Output ('M=' + $_.GetType().InvokeMember('Name','GetProperty',$null,$_,$null)) }; Write-Output 'M_END'" % adm.replace("'", "''"))
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 180)
        if rc != 0 or "M_END" not in (out or ""): return None
        return [x.strip() for x in re.findall(r"^M=(.+?)\s*$", out, re.M) if x.strip()]

    def known_admins(self):
        try:
            with open(self.mark("admins.known"), encoding="utf-8") as f: return {x.strip().lower() for x in f if x.strip()}
        except OSError: return set()

    def sec_event(self, text):
        """Ghi 1 việc lạ về bảo mật để agent báo về web (agent đọc xong thì xoá file). Chữ không dấu."""
        self.log("VIEC LA: " + text)
        try:
            p, old = self.mark("sec.event"), ""
            if os.path.exists(p):
                with open(p, encoding="ascii", errors="replace") as f: old = f.read(300).strip()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="ascii", errors="replace") as f: f.write((((old + "; ") if old else "") + text)[:300])
        except OSError: pass

    def admins_watch(self, adm, bia, baseline):
        """Nhóm quản trị có tài khoản nào ngoài tài khoản Administrator có sẵn? Lần đầu (baseline): ghi nhớ (tài khoản chủ shop tự tạo bằng script riêng).
           Các lần sau: thấy tài khoản MỚI → báo việc lạ 1 lần rồi ghi nhớ (không tự xoá: có thể là tài khoản chủ shop mới thêm)."""
        ms = self.admin_members(adm)
        if ms is None: return
        extra = {m.lower() for m in ms} - {bia.lower()}
        known = self.known_admins()
        new = sorted(extra - known)
        if new and not baseline: self.sec_event("nhom quan tri co tai khoan moi: " + ", ".join(new)[:120])
        if new or baseline:
            try:
                os.makedirs(os.path.dirname(self.mark("admins.known")), exist_ok=True)
                with open(self.mark("admins.known"), "w", encoding="utf-8") as f: f.write("\n".join(sorted(extra | known)) + "\n")
            except OSError: pass

    def quiet(self, argv, what, timeout=120):
        """Như sh() nhưng KHÔNG BAO GIỜ ghi dòng lệnh / chữ in ra vào nhật ký (lệnh có thể mang mật khẩu)."""
        rc = self._run(argv, timeout)[0]
        self.log("%s %s" % ("ok " if rc == 0 else "LOI(%s)" % rc, what))
        return rc == 0

    def in_group(self, group, user):
        rc, out = self._run(["net", "localgroup", group], 60)
        return rc == 0 and any(ln.strip().lower() == user.lower() for ln in (out or "").splitlines())

    def harden(self):
        """Chế độ khách = TÀI KHOẢN THƯỜNG (mặc định; cb.json có "user_admin": true thì bỏ qua). Cần quyền quản trị.
             · gỡ tài khoản khách khỏi nhóm Administrators (giữ trong nhóm Users) — có hiệu lực từ lần đăng nhập sau
             · cấm tài khoản khách tự đổi mật khẩu (đổi là hỏng tự đăng nhập)
             · tài khoản Administrator có sẵn: đặt mật khẩu NGẪU NHIÊN không ai biết + tắt (không có nó thì vào Safe Mode là đăng nhập được, mật khẩu trống)
           → trên máy không còn tài khoản quản trị nào dùng được; việc quản trị đi qua agent (SYSTEM) theo lệnh từ web, hoặc cài lại.
           Trả True nếu VỪA gỡ quyền Admin của tài khoản khách (cần đăng nhập lại / khởi động lại để có hiệu lực)."""
        c = self.cfg()
        if c.get("user_admin"):
            self.log("tai khoan khach duoc de quyen Admin (user_admin) - khong ha quyen"); return False
        user = c.get("user") or "PC"
        adm, usr, bia = self.names()
        if user.lower() == bia.lower():
            self.log("tai khoan khach trung ten tai khoan Administrator co san - khong ha quyen"); return False
        changed = False
        if self._run(["net", "user", user], 60)[0] != 0:
            self.log("chua co tai khoan '%s' (Windows chua tao xong) - de lan sau" % user); return False
        was = os.path.exists(self.mark("harden.done"))                               # đã khoá xong từ trước → mọi thay đổi thấy ở dưới là VIỆC LẠ
        self._run(["net", "localgroup", usr, user, "/add"], 60)                      # đã ở trong nhóm thì lệnh báo lỗi 1378 — bỏ qua
        if self.in_group(adm, user):
            changed = self.sh(["net", "localgroup", adm, user, "/delete"], "go tai khoan '%s' khoi nhom %s (thanh tai khoan thuong)" % (user, adm))
            if was: self.sec_event("tai khoan khach '%s' co lai quyen Admin - da ha lai" % user)
        self.sh(["net", "user", user, "/passwordchg:no"], "cam tai khoan '%s' tu doi mat khau" % user)
        if not was or self.bia_off is False:                                         # lần đầu, hoặc tài khoản Administrator có sẵn bị ai đó BẬT lại
            if was: self.sec_event("tai khoan '%s' co san bi bat lai - da tat lai" % bia)
            pw = "Cb1!" + secrets.token_urlsafe(8)[:10]                             # 14 ký tự: dài hơn thì lệnh net hỏi lại
            ok = self.quiet(["net", "user", bia, pw, "/active:no"], "tai khoan '%s' co san: dat mat khau ngau nhien (khong luu o dau) + tat" % bia)
            pw = None
            if ok and not was: self.touch("harden.done")
        self.admins_watch(adm, bia, baseline=not was)
        return changed

    def system(self):
        """Agent (SYSTEM) gọi lúc khởi động + vài giờ 1 lần. Khoá lại quyền (rẻ, làm lại vô hại) và làm nốt việc hạ quyền tài khoản khách nếu lần đăng nhập
           đầu không làm xong (mất điện giữa chừng, bản Windows tuỳ biến không chạy file trả lời…). KHÔNG khởi động lại máy."""
        if not self.is_admin(): return False
        self.touch("system.first")
        self.pw_never_expires()
        self.lockdown()
        done, started, first = self.mark_age("firstlogon.done"), self.mark_age("firstlogon.start"), self.mark_age("system.first")
        # chỉ hạ quyền khi lần đăng nhập đầu ĐÃ xong (script riêng của chủ shop cần quyền Admin), hoặc đã quá 1 giờ mà nó không xong
        if done is not None or (started is not None and started > 3600) or (started is None and first is not None and first > 3600):
            if done is None and self.ghost_needed(late=True):       # 1 giờ rồi vẫn chưa có tài khoản khách: bản kiểu ghost mà bộ cài không nhận ra → dựng tại đây
                return self.ghost()
            changed = self.harden()
            try: self.drv_retry()                                    # máy vẫn chưa có card mạng chạy được → làm lại bước driver (tối đa DRV_KICKS lần)
            except Exception as e:
                self.log("LOI buoc driver: %r" % (e,))
            try:                                                     # driver VGA còn dở (lần đăng nhập đầu chưa có mạng / card chưa nhận driver) → làm nốt
                if self.vga_packs(): self.vga(lambda: self.net_wait(45) is not None)
            except Exception as e:
                self.log("LOI buoc VGA: %r" % (e,))
            return changed
        return False

    def boot(self):
        """Dịch vụ khởi động gọi (SYSTEM). Tác vụ agent đã có → chỉ bật agent rồi gỡ dịch vụ. Chưa có (file trả lời + SetupComplete.cmd đều không chạy)
           → làm phần `specialize` + dựng tác vụ (dịch vụ tác vụ của Windows có thể chưa kịp chạy lúc máy vừa bật → thử lại tối đa ~2 phút) + bật agent.
           Chưa dựng được thì GIỮ dịch vụ để lần bật máy sau làm tiếp."""
        if not self.is_admin(): return False
        have = self.task_exists(TASK_AGENT) and self.task_exists(TASK_WATCH)
        if not have:
            self.log("=== boot (ban %s): chua co tac vu agent -> tu dung (dich vu khoi dong) ===" % PROV_VER)
            self.policies(); self.power(); self.shortcut()
            for _ in range(12):
                if self.tasks(): have = True; break
                self._sleep(10)
            self.lockdown()
        if not have:
            self.log("LOI boot: chua tao duoc tac vu agent - lan bat may sau thu lai"); return False
        self.start_agent()
        if self.ghost_needed():
            if not self.ghost(): return False                       # chưa xong → GIỮ dịch vụ, lần bật máy sau làm tiếp
        self.sh(["sc", "delete", BOOT_SVC], "go dich vu khoi dong (het viec)")
        return True

    # ------------------------------------------------------------------ bản Windows kiểu GHOST (ảnh chụp 1 máy đã cài sẵn — không chạy file trả lời)
    def image_oobe(self):
        """Bộ cài ghi logs\\image.json: True = bản cài bình thường (sẽ chạy file trả lời) · False = kiểu ghost · None = không rõ."""
        try:
            with open(self.mark("image.json"), encoding="utf-8-sig") as f: v = json.load(f).get("oobe")
            return v if isinstance(v, bool) else None
        except Exception:
            return None

    def setup_live(self):
        """Windows ĐANG CHẠY có đang ở bước "cài đặt lần đầu" không (đọc registry thật): True / False / None = không đọc được."""
        rc, out = self._run(["reg", "query", r"HKLM\SYSTEM\Setup"], 60)
        if rc != 0: return None
        try: return self.core().setup_state(out)
        except Exception: return None

    def ghost_needed(self, late=False):
        """Có phải bản kiểu ghost CHƯA được dựng tài khoản khách không. late = agent gọi sau 1 giờ (lưới cuối: chỉ cần chưa có tài khoản khách + Windows không ở bước cài)."""
        if os.path.exists(self.mark("ghost.done")) or os.path.exists(self.mark("firstlogon.done")): return False
        resume = self.mark_age("ghost.start") is not None           # lần trước làm dở (mất điện) → làm tiếp
        if not resume and self.mark_age("firstlogon.start") is not None and not late: return False      # lần đăng nhập đầu kiểu thường đang chạy
        oobe = self.image_oobe()
        if late:
            user = self.cfg().get("user") or "PC"
            if self._run(["net", "user", user], 60)[0] == 0 and not resume: return False               # đã có tài khoản khách → việc của harden()
            return self.setup_live() is False
        if oobe is True and not resume: return False                # bản cài bình thường: file trả lời lo
        live = self.setup_live()
        return live is False if oobe is None else live is not True

    def reg_value(self, key, name):
        rc, out = self._run(["reg", "query", key, "/v", name], 60)
        m = re.search(r"^\s*%s\s+REG_\w+[ \t]*(.*?)\s*$" % re.escape(name), out or "", re.M | re.I) if rc == 0 else None
        return m.group(1).strip() if m else ""

    def local_users(self):
        """Tài khoản cục bộ của máy: [{"name", "rid", "off"}] (hỏi WMI — không phụ thuộc ngôn ngữ Windows). Không hỏi được → None."""
        ps = ("Get-WmiObject Win32_UserAccount -Filter 'LocalAccount=True' | ForEach-Object { Write-Output ('U=' + $_.Name + '|' + $_.SID + '|' + $_.Disabled + '|') }; "
              "Write-Output 'U_END'")
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 180)
        if rc != 0 or "U_END" not in (out or ""): return None
        return [{"name": n.strip(), "rid": int(sid.rsplit("-", 1)[1]), "off": off == "True"}
                for n, sid, off in re.findall(r"^U=([^|\r\n]+)\|(S-1-5-21-[0-9-]+)\|(True|False)\|", out, re.M)]

    def rename_user(self, old, new):
        """Đổi tên 1 tài khoản cục bộ (hồ sơ C:\\Users\\<tên cũ> giữ nguyên). ADSI trước, wmic dự phòng."""
        if old.lower() == new.lower(): return True
        q = lambda t: t.replace("'", "''")
        ps = "$u=[ADSI]('WinNT://./%s,user'); $u.psbase.Rename('%s'); Write-Output 'RN_OK'" % (q(old), q(new))
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 180)
        if not (rc == 0 and "RN_OK" in (out or "")):
            self._run(["wmic", "useraccount", "where", "name='%s'" % old.replace("'", ""), "rename", new], 180)
        return self._run(["net", "user", new], 60)[0] == 0          # kiểm lại: đã có tài khoản tên mới

    def seed_name(self):
        """Tên máy bộ cài đã cấp (seed.json) — đúng kiểu tên máy Windows thì trả, không thì ''."""
        try:
            with open(os.path.join(self.base, "seed.json"), encoding="utf-8-sig") as f: n = str(json.load(f).get("name") or "")
        except Exception:
            n = ""
        return n if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,14}", n) else ""

    def rename_pc(self, target):
        """Đổi tên máy (có hiệu lực sau khi khởi động lại). Trả True nếu vừa ra lệnh đổi được."""
        cur = os.environ.get("COMPUTERNAME", "")
        if not target or cur.lower() == target.lower(): return False
        ps = "Rename-Computer -NewName '%s' -Force -ErrorAction Stop; Write-Output 'RC_OK'" % target
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 300)
        ok = rc == 0 and "RC_OK" in (out or "")
        if not ok and cur:
            rc, out = self._run(["wmic", "computersystem", "where", "name='%s'" % cur, "call", "rename", "name='%s'" % target], 300)
            ok = rc == 0 and re.search(r"ReturnValue\s*=\s*0\b", out or "") is not None
        self.log("%s doi ten may %s -> %s (co hieu luc sau khi khoi dong lai)" % ("ok " if ok else "LOI", cur or "?", target))
        return ok

    def tell(self, text, secs=300):
        """Hiện 1 hộp báo cho người đang ngồi tại máy (mọi phiên đăng nhập) — không có msg.exe / chưa ai đăng nhập thì thôi."""
        try: self._run([os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "msg.exe"), "*", "/TIME:%d" % secs, text[:250]], 30)
        except Exception: pass

    def ghost_account(self, user, pw):
        """Dựng tài khoản khách trên bản ghost. Trả "have" / "adopt" / "new"; None = chưa làm được (lần bật máy sau thử lại)."""
        us = self.local_users()
        if us is None:
            self.log("LOI ghost: khong doc duoc danh sach tai khoan cua may"); return None
        hints = [self.reg_value(r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "DefaultUserName"),
                 self.reg_value(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\LogonUI", "LastLoggedOnSAMUser")]
        name, how = pick_ghost_user(us, hints, user)
        if how == "bia":
            self.log("LOI ghost: ten tai khoan khach '%s' trung tai khoan co san cua Windows - tao lai ISO voi ten khac (-TaiKhoan)" % user); return None
        if how == "adopt":
            if self.rename_user(name, user):
                self.log("ok  NHAN tai khoan co san '%s' lam tai khoan khach '%s' (giu nguyen ho so: man hinh nen, phan mem cai san)" % (name, user))
                self._run(["net", "user", user, "/fullname:" + user], 60)
            else:
                self.log("LOI khong doi duoc ten tai khoan '%s' -> '%s' - tao tai khoan khach moi" % (name, user)); how = "new"
        if how == "new":
            if not self.quiet(["net", "user", user, pw, "/add"], "tao tai khoan khach moi '%s'" % user): return None
        else:                                                        # tài khoản có sẵn: đặt mật khẩu theo cb.json (để trống thì chỉ đặt lại khi mật khẩu cũ không trống)
            if pw or self._blank(user) is not True:
                self.quiet(["net", "user", user, pw], "dat mat khau tai khoan khach theo cau hinh (%s)" % ("co mat khau" if pw else "de trong"))
        self._run(["net", "user", user, "/active:yes"], 60)
        adm = self.names()[0]
        for u in (self.local_users() or []):                        # tài khoản KHÁC có sẵn trong ảnh (kể cả Guest đang bật): tắt + gỡ khỏi nhóm quản trị. Administrator có sẵn: harden() lo
            if u["name"].lower() == user.lower() or u["off"] or u["rid"] in (500, 503, 504): continue
            self.sh(["net", "user", u["name"], "/active:no"], "tat tai khoan khac co san trong anh: '%s'" % u["name"])
            self._run(["net", "localgroup", adm, u["name"], "/delete"], 60)
        return how

    def ghost(self):
        """BẢN WINDOWS KIỂU GHOST: khởi động thẳng vào tài khoản có sẵn, KHÔNG chạy file trả lời → dịch vụ khởi động (SYSTEM) làm thay toàn bộ:
             1. tài khoản khách: nhận tài khoản ảnh đang dùng (đổi tên theo cb.json, giữ hồ sơ) — không có thì tạo mới; tắt các tài khoản khác
             2. tự đăng nhập bằng tài khoản khách + đổi tên máy theo tên bộ cài đã cấp (seed.json)
             3. việc của "lần đăng nhập đầu": script riêng của chủ shop → chờ có mạng → driver VGA → khoá tài khoản khách (harden)
             4. khởi động lại 1 lần (tên máy mới + quyền mới có hiệu lực)
           Mất điện giữa chừng → lần bật máy sau làm lại (bước đã xong tự bỏ qua). Trả True khi xong."""
        self.touch("ghost.start"); self.touch("firstlogon.start")
        self.log("=== ghost (ban %s): ban Windows kieu ghost (khong chay file tra loi) -> tu dung tai khoan khach ===" % PROV_VER)
        c = self.cfg()
        user, pw = c.get("user") or "PC", c.get("password") or ""
        self._sleep(GHOST_TELL_WAIT)
        self.tell("CloudBlue PC: dang hoan tat cai dat may nay (vai phut). KHONG tat may - xong may se TU KHOI DONG LAI 1 lan.", 900)
        how = self.ghost_account(user, pw)
        if how is None:
            self.log("LOI ghost: chua dung duoc tai khoan khach - lan bat may sau thu lai"); return False
        target = self.seed_name()
        self.rename_pc(target)
        self.autologon(domain=target or None)
        self.firstboot()                                             # script riêng của chủ shop (driver .exe…) — chạy bằng SYSTEM
        limit = NET_WAIT_VGA if self.vga_needed() else NET_WAIT
        drv = None
        try: drv = self.drivers(show=False)                          # driver card mạng TRƯỚC — có mạng rồi mới tới VGA
        except Exception as e:
            self.log("LOI buoc driver: %r" % (e,))
        if drv is not None and not drv["nics"]: limit = min(limit, NET_WAIT)
        waited = self.net_wait(limit)
        self.log("ok  may da co mang (cho %d giay)" % waited if waited is not None else "LOI chua co mang sau %d giay (day mang / driver card mang?)" % limit)
        try: self.vga(waited is not None)
        except Exception as e:
            self.log("LOI buoc VGA: %r" % (e,))
        self.harden()
        self.touch("firstlogon.done"); self.touch("ghost.done")
        self.sh(["shutdown", "/r", "/t", "30", "/c", "CloudBlue PC: hoan tat cai dat - may tu khoi dong lai 1 lan"], "hen khoi dong lai sau 30 giay")
        self.log("xong ghost (tai khoan khach: %s)" % {"have": "da co san", "adopt": "nhan tai khoan cua anh", "new": "tao moi"}[how])
        return True

    def start_agent(self):
        if not self.sh(["schtasks", "/run", "/tn", TASK_AGENT], "bat agent"):
            self.sh(["schtasks", "/run", "/tn", TASK_WATCH], "bat agent (qua tac vu canh)")

    def task_exists(self, name):
        return self._run(["schtasks", "/query", "/tn", name], 60)[0] == 0

    # ------------------------------------------------------------------ các pha
    def specialize(self):
        self.log("=== specialize (ban %s) ===" % PROV_VER)
        self.policies(); self.power(); self.shortcut()
        self.tasks()                                               # lúc này dịch vụ tác vụ có thể chưa chạy → firstlogon / logon làm lại
        self.lockdown()

    def firstlogon(self):
        self.log("=== firstlogon (ban %s) ===" % PROV_VER)
        self.touch("firstlogon.start")
        self.say("CloudBlue PC %s - dang hoan tat cai dat Windows %s" % (PROV_VER, self.os_tag().upper()))
        self.say("KHONG tat may. Xong may se tu khoi dong lai 1 lan.")
        self.say("")
        self.say("[1/5] Tu dang nhap, phan mem quan ly, khoa quyen thu muc ...")
        self.autologon(); self.policies(); self.power(); self.shortcut(); self.tasks()
        self.lockdown()
        self.start_agent()
        self.wallpaper()
        self.say("[2/5] Lenh rieng cua chu shop (firstboot.d) ...")
        n = self.firstboot()                                         # script riêng của chủ shop (driver .exe…) — chạy khi tài khoản còn quyền Admin
        self.say("    %s" % ("da chay %d lenh" % n if n else "khong co lenh nao"))
        limit = NET_WAIT_VGA if self.vga_needed() else NET_WAIT      # có gói VGA phải cài (máy có card NVIDIA chưa có driver) thì chờ mạng lâu hơn
        self.say("[3/5] Driver card mang, roi cho may co mang - toi da %d phut ..." % (limit // 60))
        drv = None
        try: drv = self.drivers()                                    # driver card mạng TRƯỚC — có mạng rồi mới tới VGA
        except Exception as e:
            self.log("LOI buoc driver: %r" % (e,))
        self.drv_say(drv)
        if drv is not None and not drv["nics"]: limit = min(limit, NET_WAIT)      # chưa card mạng nào nhận driver: chờ lâu cũng không có mạng
        waited = self.net_wait(limit)
        if waited is None:
            self.log("LOI chua co mang sau %d giay (day mang / driver card mang?)" % limit)
            self.say("    !! CHUA CO MANG sau %d phut. Kiem tra day mang / driver card mang." % (limit // 60))
            self.say("       May se chua hien tren web cho toi khi co mang.")
        else:
            self.log("ok  may da co mang (cho %d giay)" % waited)
            self.say("    da co mang (cho %d giay)" % waited)
        self.say("[4/5] Driver VGA NVIDIA ...")
        try: v = self.vga(waited is not None)
        except Exception as e:
            v = "fail"; self.log("LOI buoc VGA: %r" % (e,))
        self.say("    " + {"none": "khong co goi VGA nao", "skip": "may nay khong co card NVIDIA - bo qua", "done": "xong - card da nhan driver",
                           "wait": "CHUA cai (chua co mang) - se tu cai khi may co mang",
                           "fail": "da chay bo cai nhung card chua nhan driver - se kiem lai sau khi khoi dong lai"}.get(v, v))
        self.say("[5/5] Khoa tai khoan khach (tai khoan thuong) ...")
        changed = self.harden()
        self.touch("firstlogon.done")
        if changed:                                                  # quyền mới (tài khoản thường) chỉ có hiệu lực ở lần đăng nhập sau → khởi động lại 1 lần
            self.sh(["shutdown", "/r", "/t", "20", "/c", "CloudBlue PC: hoan tat cai dat - may tu khoi dong lai 1 lan"], "hen khoi dong lai sau 20 giay")
            self.say(""); self.say("XONG. May tu khoi dong lai sau 20 giay.")
        else:
            self.say(""); self.say("XONG.")
        self.log("xong firstlogon")

    def logon(self):
        if self.is_admin():                                          # tài khoản thường không xem / dựng được tác vụ của SYSTEM — agent tự lo phần đó
            if not (self.task_exists(TASK_AGENT) and self.task_exists(TASK_WATCH)):
                self.log("=== logon: thieu tac vu → dung lai ==="); self.tasks()
            self._run(["schtasks", "/run", "/tn", TASK_WATCH], 60)   # agent đang chạy thì lệnh này tự thoát ngay
        self.wallpaper()                                             # tài khoản nào chưa từng được đặt ảnh nền thì đặt 1 lần


def main(argv):
    phase = argv[0] if argv else ""
    p = Prov()
    try:
        if phase == "specialize": p.specialize()
        elif phase == "setupcomplete":                             # SetupComplete.cmd (lưới an toàn khi file trả lời không được Windows dùng)
            p.specialize(); p.start_agent()
        elif phase == "firstlogon": p.firstlogon()
        elif phase == "logon": p.logon()
        elif phase == "system": p.system()
        elif phase == "boot": p.boot()
        else:
            print("cb_provision %s — pha: specialize | setupcomplete | firstlogon | logon | system | boot" % PROV_VER); return 2
    except Exception as e:                                           # không để lỗi nào chặn bước cài Windows
        p.log("LOI KHONG NGO: %r" % (e,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
