# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_provision.py — CÀI ĐẶT LẦN ĐẦU trong Windows vừa cài (gọi bởi provision.cmd từ file trả lời unattend.xml)
#     specialize  (tài khoản SYSTEM, trước màn hình đăng nhập): chính sách bỏ màn hình hỏi, điện năng, tác vụ tự chạy agent, KHOÁ QUYỀN thư mục
#     firstlogon  (tài khoản vừa tạo — lúc này còn là Admin, lần đăng nhập đầu): tự đăng nhập vĩnh viễn, tác vụ, ẢNH NỀN, chạy script riêng của chủ shop
#                                                                 trong os\firstboot.d (và os\firstboot.d\<tên bản, vd 1511>), bật agent, rồi HẠ tài khoản khách
#                                                                 xuống TÀI KHOẢN THƯỜNG + khoá tài khoản Administrator có sẵn + khởi động lại 1 lần
#     logon       (mỗi lần đăng nhập — khoá Run, chạy bằng quyền của người đăng nhập): tài khoản chưa có ảnh nền thì đặt; có quyền quản trị thì kiểm tác vụ
#     system      (agent — SYSTEM — gọi lúc khởi động + định kỳ): khoá lại quyền thư mục / phân vùng cứu hộ; lần đăng nhập đầu chưa hạ quyền kịp thì làm nốt
#  BẢO MẬT (mặc định, cb.json "user_admin": false): khách dùng tài khoản THƯỜNG, không còn tài khoản quản trị nào dùng được trên máy;
#     C:\CloudBluePC + phân vùng cứu hộ chỉ SYSTEM / Administrators vào được (tài khoản thường chỉ đọc + chạy py\ và os\ để đặt ảnh nền).
#  Mọi lệnh lỗi đều được ghi nhật ký và BỎ QUA — không bao giờ làm hỏng bước cài Windows.
#  Nhật ký: C:\CloudBluePC\logs\provision.log (phần chạy bằng tài khoản thường: %LOCALAPPDATA%\CloudBluePC\provision.log)
# =====================================================================================================
import json, os, re, secrets, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
PROV_VER = "20.11c"
TASK_AGENT, TASK_WATCH = "CloudBluePC Agent", "CloudBluePC Watch"
NOWIN = 0x08000000 if os.name == "nt" else 0

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
    def __init__(self, base=BASE, run=None, log=None, spi=None, admin=None, rec=None, now=None):
        self.base = base
        self._run = run or self._real_run
        self._spi = spi or spi_wallpaper
        self._admin = admin                     # None = hỏi Windows; True / False = phép thử ép sẵn
        self._rec = rec or real_recovery_root
        self._now = now or time.time
        self.lines = []
        self._log = log

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
        try:
            r = subprocess.run(argv, capture_output=True, timeout=timeout, creationflags=NOWIN)
            return r.returncode, ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace").strip()[-300:]
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
    def policies(self):
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

    def autologon(self):
        c = self.cfg()
        user, pw = c.get("user") or "PC", c.get("password") or ""
        wl = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
        self.reg(wl, "AutoAdminLogon", "REG_SZ", 1)
        self.reg(wl, "DefaultUserName", "REG_SZ", user)
        self.reg(wl, "DefaultDomainName", "REG_SZ", os.environ.get("COMPUTERNAME", "."))
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
            self.sh(argv, "script rieng " + os.path.relpath(p, d), timeout=3600); n += 1
        try:
            os.makedirs(os.path.dirname(mark), exist_ok=True)
            with open(mark, "w") as fo: fo.write(str(n))
        except OSError: pass
        return n

    # ------------------------------------------------------------------ bảo mật
    def lockdown(self):
        """Khoá quyền C:\\CloudBluePC (chỉ SYSTEM + Administrators; tài khoản thường chỉ đọc + chạy py\\ và os\\) và gốc phân vùng cứu hộ.
           Cần quyền quản trị. Trả True nếu mọi lệnh icacls đều xong."""
        try:
            lib = os.path.join(self.base, "lib")
            if lib not in sys.path: sys.path.insert(0, lib)
            import cbcore
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
              "$b=(Get-WmiObject Win32_UserAccount -Filter 'LocalAccount=True' | Where-Object { $_.SID -like 'S-1-5-21-*-500' } | Select-Object -First 1).Name;"
              "Write-Output ('ADM=' + $a + '|USR=' + $u + '|BIA=' + $b + '|')")
        rc, out = self._run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], 180)
        m = re.search(r"ADM=([^|\r\n]*)\|USR=([^|\r\n]*)\|BIA=([^|\r\n]*)\|", out or "")
        adm, usr, bia = (m.group(1).strip(), m.group(2).strip(), m.group(3).strip()) if (rc == 0 and m) else ("", "", "")
        return adm or "Administrators", usr or "Users", bia or "Administrator"

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
        self._run(["net", "localgroup", usr, user, "/add"], 60)                      # đã ở trong nhóm thì lệnh báo lỗi 1378 — bỏ qua
        if self.in_group(adm, user):
            changed = self.sh(["net", "localgroup", adm, user, "/delete"], "go tai khoan '%s' khoi nhom %s (thanh tai khoan thuong)" % (user, adm))
        self.sh(["net", "user", user, "/passwordchg:no"], "cam tai khoan '%s' tu doi mat khau" % user)
        if not os.path.exists(self.mark("harden.done")):
            pw = "Cb1!" + secrets.token_urlsafe(8)[:10]                             # 14 ký tự: dài hơn thì lệnh net hỏi lại
            ok = self.quiet(["net", "user", bia, pw, "/active:no"], "tai khoan '%s' co san: dat mat khau ngau nhien (khong luu o dau) + tat" % bia)
            pw = None
            if ok: self.touch("harden.done")
        return changed

    def system(self):
        """Agent (SYSTEM) gọi lúc khởi động + vài giờ 1 lần. Khoá lại quyền (rẻ, làm lại vô hại) và làm nốt việc hạ quyền tài khoản khách nếu lần đăng nhập
           đầu không làm xong (mất điện giữa chừng, bản Windows tuỳ biến không chạy file trả lời…). KHÔNG khởi động lại máy."""
        if not self.is_admin(): return False
        self.touch("system.first")
        self.lockdown()
        done, started, first = self.mark_age("firstlogon.done"), self.mark_age("firstlogon.start"), self.mark_age("system.first")
        # chỉ hạ quyền khi lần đăng nhập đầu ĐÃ xong (script riêng của chủ shop cần quyền Admin), hoặc đã quá 1 giờ mà nó không xong
        if done is not None or (started is not None and started > 3600) or (started is None and first is not None and first > 3600):
            return self.harden()
        return False

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
        self.autologon(); self.policies(); self.power(); self.shortcut(); self.tasks()
        self.lockdown()
        self.start_agent()
        self.wallpaper()
        self.firstboot()                                             # script riêng của chủ shop (driver .exe…) — chạy khi tài khoản còn quyền Admin
        changed = self.harden()
        self.touch("firstlogon.done")
        if changed:                                                  # quyền mới (tài khoản thường) chỉ có hiệu lực ở lần đăng nhập sau → khởi động lại 1 lần
            self.sh(["shutdown", "/r", "/t", "20", "/c", "CloudBlue PC: hoan tat cai dat - may tu khoi dong lai 1 lan"], "hen khoi dong lai sau 20 giay")
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
        else:
            print("cb_provision %s — pha: specialize | setupcomplete | firstlogon | logon | system" % PROV_VER); return 2
    except Exception as e:                                           # không để lỗi nào chặn bước cài Windows
        p.log("LOI KHONG NGO: %r" % (e,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
