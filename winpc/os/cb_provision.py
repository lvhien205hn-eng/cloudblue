# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_provision.py — CÀI ĐẶT LẦN ĐẦU trong Windows vừa cài (gọi bởi provision.cmd từ file trả lời unattend.xml)
#     specialize  (tài khoản SYSTEM, trước màn hình đăng nhập): chính sách bỏ màn hình hỏi, điện năng, tác vụ tự chạy agent
#     firstlogon  (tài khoản vừa tạo, lần đăng nhập đầu):        tự đăng nhập vĩnh viễn, tác vụ (làm lại cho chắc), chạy script riêng
#                                                                 của chủ shop trong os\firstboot.d, bật agent
#     logon       (mỗi lần đăng nhập — khoá Run):                 thiếu tác vụ / agent chưa chạy thì dựng lại
#  Mọi lệnh lỗi đều được ghi nhật ký và BỎ QUA — không bao giờ làm hỏng bước cài Windows.
#  Nhật ký: C:\CloudBluePC\logs\provision.log
# =====================================================================================================
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
PROV_VER = "20.11a"
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


class Prov:
    def __init__(self, base=BASE, run=None, log=None):
        self.base = base
        self._run = run or self._real_run
        self.lines = []
        self._log = log

    def log(self, m):
        ln = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        self.lines.append(ln)
        if self._log: self._log(ln); return
        try:
            os.makedirs(os.path.join(self.base, "logs"), exist_ok=True)
            with open(os.path.join(self.base, "logs", "provision.log"), "a", encoding="utf-8") as f: f.write(ln + "\n")
        except OSError: pass

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

    def firstboot(self):
        """Chạy 1 LẦN các script của chủ shop: os\\firstboot.d\\*.cmd|*.bat|*.ps1 (theo thứ tự tên) — cài driver, phần mềm…"""
        d, mark = os.path.join(self.base, "os", "firstboot.d"), os.path.join(self.base, "logs", "firstboot.done")
        if os.path.exists(mark) or not os.path.isdir(d): return 0
        n = 0
        for f in sorted(os.listdir(d)):
            p, ext = os.path.join(d, f), f.lower().rsplit(".", 1)[-1]
            if ext in ("cmd", "bat"): argv = ["cmd.exe", "/c", p]
            elif ext == "ps1": argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", p]
            else: continue
            self.sh(argv, "script rieng " + f, timeout=3600); n += 1
        try:
            os.makedirs(os.path.dirname(mark), exist_ok=True)
            with open(mark, "w") as fo: fo.write(str(n))
        except OSError: pass
        return n

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

    def firstlogon(self):
        self.log("=== firstlogon (ban %s) ===" % PROV_VER)
        self.autologon(); self.policies(); self.power(); self.shortcut(); self.tasks()
        self.start_agent()
        self.firstboot()
        self.log("xong firstlogon")

    def logon(self):
        if not (self.task_exists(TASK_AGENT) and self.task_exists(TASK_WATCH)):
            self.log("=== logon: thieu tac vu → dung lai ==="); self.tasks()
        self._run(["schtasks", "/run", "/tn", TASK_WATCH], 60)       # agent đang chạy thì lệnh này tự thoát ngay


def main(argv):
    phase = argv[0] if argv else ""
    p = Prov()
    try:
        if phase == "specialize": p.specialize()
        elif phase == "firstlogon": p.firstlogon()
        elif phase == "logon": p.logon()
        else:
            print("cb_provision %s — pha: specialize | firstlogon | logon" % PROV_VER); return 2
    except Exception as e:                                           # không để lỗi nào chặn bước cài Windows
        p.log("LOI KHONG NGO: %r" % (e,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
