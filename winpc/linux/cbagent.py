# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbagent.py — CloudBlue PC: AGENT cho máy đang chạy CachyOS (Linux). Chạy bằng root (dịch vụ systemd cloudblue.service).
#  Dùng LẠI lõi của agent Windows (pcagent.Agent: đăng ký bằng vé cài lại, hỏi máy chủ, hạn thuê / khoá máy, nhận lệnh) — chỉ thay phần đụng
#  hệ điều hành: đọc / ghi tệp, thông tin máy, tắt / khởi động lại, tự đăng nhập, hộp báo cho khách, phân vùng cứu hộ (NTFS), mục khởi động UEFI.
#    · lệnh CÀI LẠI (Windows / CachyOS): ghi cb/job.json lên phân vùng cứu hộ + BootNext = Windows Boot Manager (mặc định = WinPE cứu hộ)
#      → WinPE làm như với máy Windows (xoá phần Linux, cài bản được chọn)
#    · báo kết quả lần cài CachyOS (cb/job-result.json do cb-install.sh ghi) về web
#    · cập nhật: bản kê công bố có mục "linux" (linux/cbagent.py …) + agent/lib của bản đó → tải, kiểm sha256, chạy thử, thay, chạy lại
#  /opt/cloudblue: cb.json (bản sao của phân vùng cứu hộ) · seed.json (vé 1 lần, chỉ root đọc) · identity.json · rent.json · logs/
#  Lệnh:  cbagent.py run | status | selfcheck | reinstall <bản> [all|disk|system]
# =====================================================================================================
import fcntl, hashlib, json, os, re, shutil, socket, subprocess, sys, time, traceback

LINUX_VER = "22.11e"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("CB_BASE") or os.path.abspath(os.path.join(HERE, ".."))          # /opt/cloudblue
for _p in (os.path.join(BASE, "lib"), os.path.join(BASE, "agent")):
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import pcagent                                                   # noqa: E402

EFIVARS = "/sys/firmware/efi/efivars"
REC_MNT = "/run/cloudblue/rec"
LOCK = "/run/cloudblue-agent.lock"
POWER_UNIT = "cloudblue-power"
DM_CONF = {"plasmalogin": "/etc/plasmalogin.conf.d/autologin.conf", "sddm": "/etc/sddm.conf.d/autologin.conf"}
LIB_FILES = ("agent/pcagent.py", "lib/cbcore.py", "lib/cbrec.py", "lib/cbsys.py")
SELF_REL = "linux/cbagent.py"
LINUX_REL = re.compile(r"^linux/[A-Za-z0-9_.-]{1,60}\.(sh|cfg|py|service)$")   # = pcagent.LINUX_REL (giữ riêng: lõi agent chép từ phân vùng cứu hộ có thể là bản cũ)


def P(p):
    """Đường dẫn kiểu Windows của lõi agent (logs\\a.json) → đường dẫn Linux."""
    return str(p).replace("\\", "/")


def sh(argv, timeout=60, input=None):
    """Chạy 1 lệnh → (mã thoát, chữ in ra). Không ném lỗi."""
    try:
        r = subprocess.run([str(a) for a in argv], capture_output=True, timeout=timeout, input=input.encode() if isinstance(input, str) else input)
        return r.returncode, ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "qua thoi gian"
    except OSError as e:
        return 127, str(e)


def read(p, default=""):
    try:
        with open(p, encoding="utf-8", errors="replace") as f: return f.read()
    except OSError:
        return default


# ====================================================================================== tệp + giờ (thay cbsys.WinSys cho lõi agent)
class LinuxSys:
    dry = False

    def __init__(self, log=None): self._log = log or (lambda *a: None)
    def log(self, *a):
        try: self._log(" ".join(str(x) for x in a))
        except Exception: pass
    def now(self): return time.time()
    def sleep(self, s): time.sleep(s)
    def exists(self, p): return os.path.exists(P(p))
    def isdir(self, p): return os.path.isdir(P(p))
    def listdir(self, p):
        try: return os.listdir(P(p))
        except OSError: return []
    def size(self, p):
        try: return os.path.getsize(P(p))
        except OSError: return 0
    def read_text(self, p):
        with open(P(p), "r", encoding="utf-8-sig") as f: return f.read()
    def read_bytes(self, p):
        with open(P(p), "rb") as f: return f.read()

    def _write(self, p, data, mode):
        p = P(p)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "wb") as f: f.write(data)
        os.replace(tmp, p)

    def write_text(self, p, s, encoding="utf-8"): self._write(p, s.encode(encoding), 0o600)
    def write_bytes(self, p, b): self._write(p, bytes(b), 0o644 if str(p).endswith(".py") else 0o600)
    def makedirs(self, p): os.makedirs(P(p), exist_ok=True)

    def remove(self, p):
        try:
            if os.path.isfile(P(p)): os.remove(P(p))
        except OSError: pass

    def rename(self, a, b): os.replace(P(a), P(b))
    def firmware(self): return "uefi" if os.path.isdir("/sys/firmware/efi") else "bios"
    def disks(self): return []
    def volumes(self): return []

    def run(self, argv, timeout=3600, show=False, input=None, change=True): return sh(argv, timeout, input)

    def efi_get(self, name, guid="{8BE4DF61-93CA-11D2-AA0D-00E098032B8C}"):
        """Đọc 1 biến UEFI qua efivarfs (4 byte đầu = thuộc tính). Không có → None."""
        g = str(guid).strip("{}").lower()
        try:
            with open(os.path.join(EFIVARS, "%s-%s" % (name, g)), "rb") as f: b = f.read()
            return b[4:] if len(b) > 4 else None
        except OSError:
            return None

    def efi_set(self, name, data, guid="{8BE4DF61-93CA-11D2-AA0D-00E098032B8C}", attrs=7):
        """Ghi 1 biến UEFI qua efivarfs (4 byte thuộc tính + dữ liệu, ĐÚNG 1 lần ghi); dữ liệu rỗng = xoá biến. Được → True.
           BootNext / BootOrder / Boot#### không bị efivarfs khoá (immutable) nên ghi thẳng được; lỗi gì → False (người gọi thử efibootmgr)."""
        path = os.path.join(EFIVARS, "%s-%s" % (name, str(guid).strip("{}").lower()))
        try:
            if not data:
                if os.path.exists(path): os.remove(path)
                return True
            fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
            try: n = os.write(fd, int(attrs).to_bytes(4, "little") + bytes(data))
            finally: os.close(fd)
            return n == 4 + len(data)
        except OSError:
            return False


# ====================================================================================== thông tin máy + việc của hệ điều hành
def os_release():
    d = {}
    for ln in read("/etc/os-release").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1); d[k.strip()] = v.strip().strip('"')
    return d


def gui_sessions():
    """[(uid, tên, số phiên)] các phiên đồ hoạ đang mở (loginctl)."""
    out = []
    rc, txt = sh(["loginctl", "list-sessions", "--no-legend"], 15)
    for ln in txt.splitlines() if rc == 0 else []:
        f = ln.split()
        if len(f) < 3 or not f[1].isdigit(): continue
        rc2, t2 = sh(["loginctl", "show-session", f[0], "-p", "Type", "-p", "Active"], 10)
        if rc2 == 0 and re.search(r"Type=(wayland|x11)", t2): out.append((int(f[1]), f[2], f[0]))
    return out


class LinuxHost:
    def __init__(self, user=""): self.user = user or ""
    def hostname(self): return socket.gethostname()

    def os_ver(self):
        r = os_release()
        return ("%s %s" % (r.get("BUILD_ID") or r.get("VERSION_ID") or "rolling", os.uname().release)).strip()[:40]

    def os_name(self): return (os_release().get("PRETTY_NAME") or "CachyOS Linux")[:40]

    def cpu(self):
        m = re.search(r"^model name\s*:\s*(.+)$", read("/proc/cpuinfo"), re.M)
        return (m.group(1).strip() if m else ""), (os.cpu_count() or 0)

    def ram_gb(self):
        m = re.search(r"^MemTotal:\s*(\d+)", read("/proc/meminfo"), re.M)
        return round(int(m.group(1)) / 2 ** 20, 1) if m else 0

    def gpus(self):
        rc, txt = sh(["lspci", "-mm"], 20)
        out = []
        for ln in txt.splitlines() if rc == 0 else []:
            q = re.findall(r'"([^"]*)"', ln)
            if len(q) >= 3 and re.search(r"VGA|3D|Display", q[0]):
                n = re.sub(r"\s+", " ", ("%s %s" % (q[1], q[2])).replace("Corporation", "")).strip()
                if n not in out: out.append(n[:80])
        return out

    def lan_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
            return ip
        except OSError:
            return ""

    def uptime(self):
        try: return int(float(read("/proc/uptime", "0").split()[0]))
        except (ValueError, IndexError): return 0

    def smbios(self):
        try:
            with open("/sys/firmware/dmi/tables/DMI", "rb") as f: t = f.read()
            return pcagent.parse_smbios(bytes(8)[:4] + len(t).to_bytes(4, "little") + t)
        except OSError:
            return pcagent.parse_smbios(b"")

    def power(self, reboot=True, delay=5, msg=""):
        """Hẹn khởi động lại / tắt máy sau `delay` giây (đơn vị systemd tạm — huỷ được bằng abort_shutdown) + báo khách."""
        if msg: self.notify(msg, max(10, int(delay)))
        what = "reboot" if reboot else "poweroff"
        if int(delay) <= 0:
            sh(["systemctl", what], 60); return
        sh(["systemctl", "stop", POWER_UNIT + ".timer", POWER_UNIT + ".service"], 20)
        rc, _ = sh(["systemd-run", "--unit=" + POWER_UNIT, "--on-active=%ds" % int(delay), "--timer-property=AccuracySec=1s", "systemctl", what], 30)
        if rc != 0: sh(["shutdown", "-r" if reboot else "-P", "+%d" % max(1, int(delay) // 60)], 30)

    def abort_shutdown(self):
        sh(["systemctl", "stop", POWER_UNIT + ".timer", POWER_UNIT + ".service"], 20)
        sh(["shutdown", "-c"], 20)

    def autologon(self, on):
        """Bật / tắt TỰ ĐĂNG NHẬP khách (màn hình đăng nhập plasmalogin / sddm). Khoá máy hết hạn: tắt + khởi động lại → dừng ở màn hình đăng nhập."""
        dm = os.path.basename(os.path.realpath("/etc/systemd/system/display-manager.service")).replace(".service", "")
        path = DM_CONF.get(dm)
        if not path or not self.user: return False
        try:
            if on:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f: f.write("[Autologin]\nUser=%s\nSession=plasma.desktop\nRelogin=true\n" % self.user)
            elif os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            return False

    def set_clock(self, epoch):
        rc, _ = sh(["date", "-u", "-s", "@%d" % int(epoch)], 20)
        if rc == 0: sh(["hwclock", "--systohc", "--utc"], 30)
        return rc == 0

    def show_code(self, code):
        """SỐ MÁY ra màn hình nền của khách: file 'May so <số> (CloudBlue).txt' (root sở hữu, khách chỉ đọc). Số rỗng → gỡ file."""
        if not self.user: return False
        desk = os.path.join("/home", self.user, "Desktop")
        try:
            want = ("May so %s (CloudBlue).txt" % code) if code else ""
            if os.path.isdir(desk):
                for f in os.listdir(desk):
                    if re.fullmatch(r"May so .{1,40} \(CloudBlue\)\.txt", f) and f != want: os.remove(os.path.join(desk, f))
            if want:
                os.makedirs(desk, exist_ok=True)
                p = os.path.join(desk, want)
                with open(p, "w", encoding="utf-8") as f:
                    f.write("MÁY SỐ: %s\n\nKhi cần hỗ trợ (máy lỗi, gia hạn...), hãy báo cho shop SỐ MÁY này.\nCloudBlue PC\n" % code)
                os.chmod(p, 0o644)
            return True
        except OSError:
            return False

    def drivers(self): return None
    def remote_running(self): return False
    def remote_start(self, script): raise OSError("dieu khien tu xa ban Linux chua co")

    def notify(self, text, secs=60):
        """Hộp báo cho khách: thông báo trên màn hình mọi phiên đồ hoạ (notify-send, mức khẩn) + wall cho cửa sổ lệnh."""
        text = str(text)[:250]
        for uid, name, _ in gui_sessions():
            env = ["env", "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%d/bus" % uid, "XDG_RUNTIME_DIR=/run/user/%d" % uid]
            sh(["runuser", "-u", name, "--"] + env + ["notify-send", "-u", "critical", "-a", "CloudBlue PC", "-t", str(max(5, int(secs)) * 1000),
                                                      "CloudBlue PC", text], 15)
        sh(["wall", text], 10)

    def mutex(self):
        try:
            self._lk = open(LOCK, "w")
            fcntl.flock(self._lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def restart_self(self): return True                         # systemd (Restart=always) chạy lại sau khi thoát

    def selfcheck(self, script):
        rc, out = sh([sys.executable, "-I", "-B", script, "selfcheck"], 120)
        return rc == 0, out[-400:]


# ====================================================================================== phân vùng cứu hộ (NTFS) — gắn khi cần, gỡ ngay sau
class LinuxRec:
    def __init__(self, uuid="", log=None):
        self.uuid = uuid if re.fullmatch(r"[0-9A-Fa-f]{16}", str(uuid or "")) else ""
        self.log = log or (lambda m: None)

    def device(self):
        """Thiết bị của phân vùng cứu hộ: theo UUID (số seri NTFS, cb-install ghi vào seed.json) rồi theo nhãn CBRECOVERY."""
        for args in ([["-U", self.uuid]] if self.uuid else []) + [["-L", C.REC_LABEL]]:
            rc, out = sh(["blkid"] + args, 15)
            dev = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""
            if dev.startswith("/dev/"): return dev
        return ""

    def __enter__(self): return self
    def __exit__(self, *a): self.umount()

    def mount(self, rw=False):
        """Gắn phân vùng cứu hộ tại /run/cloudblue/rec (chỉ root đọc) → đường gốc có '/' cuối. Không thấy / không gắn được → None."""
        dev = self.device()
        if not dev: return None
        os.makedirs(REC_MNT, mode=0o700, exist_ok=True)
        if os.path.ismount(REC_MNT):
            if rw: sh(["mount", "-o", "remount,rw", REC_MNT], 30)
            return REC_MNT + "/"
        opt = ("rw" if rw else "ro") + ",uid=0,gid=0,umask=077"
        for fs in ("ntfs3", "ntfs-3g", "ntfs"):
            rc, out = sh(["mount", "-t", fs, "-o", opt, dev, REC_MNT], 60)
            if rc == 0: return REC_MNT + "/"
        self.log("chưa gắn được phân vùng cứu hộ %s: %s" % (dev, out.strip()[-160:]))
        return None

    def umount(self):
        if os.path.ismount(REC_MNT):
            sh(["sync"], 30); sh(["umount", REC_MNT], 60)

    def cfg(self, root): return C.load_json(LinuxSys(), root + "cb/cb.json") or {}

    def status(self):
        root = self.mount()
        if not root: return {"ok": False, "images": []}
        try:
            cfg = self.cfg(root)
            ok_file = lambda rel: os.path.exists(root + P(rel))
            imgs = [im["id"] for im in cfg.get("images") or [] if ok_file(im["file"]) and (not C.is_linux(im) or all(ok_file(r) for r in C.LINUX_FILES))]
            ok = bool(imgs) and ok_file("cb\\boot\\boot.wim") and ok_file("cb\\boot\\boot.sdi")
            return {"ok": ok, "images": imgs, "ver": cfg.get("ver") or ""}
        finally:
            self.umount()

    def take_result(self, clear=False):
        root = self.mount(rw=clear)
        if not root: return None
        try:
            p = root + "cb/job-result.json"
            if clear:
                try: os.remove(p)
                except OSError: pass
                return None
            return C.load_json(LinuxSys(), p)
        finally:
            self.umount()

    def stage_job(self, job, hostname, now, win_hint):
        """Ghi lệnh cài lại lên phân vùng cứu hộ (như cbrec.stage_job của Windows) + BootNext = Windows Boot Manager (→ WinPE cứu hộ).
           win_hint = vị trí phân vùng Linux đang chạy (wipe=system: WinPE thay ĐÚNG phần hệ điều hành, giữ dữ liệu khác). Trả bản sẽ cài."""
        root = self.mount(rw=True)
        if not root: raise C.Stop("May nay khong thay phan vung cuu ho CloudBlue - khong cai lai tu xa duoc.")
        try:
            cfg = self.cfg(root)
            image = C.find_image(cfg, job.get("os"))
            need = [image["file"], "cb\\boot\\boot.wim", "cb\\boot\\boot.sdi"] + (list(C.LINUX_FILES) if C.is_linux(image) else [])
            for rel in need:
                if not os.path.exists(root + P(rel)): raise C.Stop("Phan vung cuu ho thieu file %s" % rel)
            if job.get("wipe") not in ("all", "disk", "system"): raise C.Stop("Kieu xoa '%s' khong hop le." % job.get("wipe"))
            if C.is_linux(image) and C.secure_boot_on(LinuxSys()): raise C.Stop("May dang BAT Secure Boot - CachyOS can TAT Secure Boot trong BIOS truoc.")
            wbm = efi_find("Windows Boot Manager")
            if wbm is None: raise C.Stop("Khong thay muc khoi dong 'Windows Boot Manager' (loi ve bo cai WinPE) trong BIOS.")
            j = {k: v for k, v in job.items() if k in ("id", "os", "wipe", "ticket", "enroll_key", "hw", "tries")}
            j.update(win=win_hint or {}, name=hostname, state="queued", attempts=0, ts=int(now), from_os="cachyos")
            C.save_json(LinuxSys(), root + "cb/job.json", j)
            try: os.remove(root + "cb/job-result.json")
            except OSError: pass
            ok, why = boot_next(wbm)
            if not ok:                                              # không đặt được → gỡ lệnh vừa ghi (lần sau máy vào WinPE vì lý do khác sẽ KHÔNG tự cài lại)
                try: os.remove(root + "cb/job.json")
                except OSError: pass
                raise C.Stop("Khong dat duoc khoi dong 1 lan vao Windows Boot Manager (%s)" % (why or "efivarfs + efibootmgr deu loi"))
            return image
        finally:
            self.umount()

    def pending_job(self):
        """Lệnh cài lại đang chờ trên phân vùng cứu hộ (cb/job.json) hoặc None."""
        root = self.mount()
        if not root: return None
        try: return C.load_json(LinuxSys(), root + "cb/job.json")
        finally: self.umount()

    def drop_job(self):
        root = self.mount(rw=True)
        if root:
            try:
                try: os.remove(root + "cb/job.json")
                except OSError: pass
            finally:
                self.umount()
        if not LinuxSys().efi_set("BootNext", b""): sh(["efibootmgr", "-q", "-N"], 30)


def efi_find(desc):
    """Số mục Boot#### có tên `desc`: đọc thẳng NVRAM (efivarfs), không thấy thì hỏi efibootmgr. Không có → None."""
    try:
        n = C.efi_find(LinuxSys(), desc)
        if n is not None: return n
    except Exception: pass
    rc, out = sh(["efibootmgr"], 20)
    for ln in out.splitlines() if rc == 0 else []:
        m = re.match(r"^Boot([0-9A-Fa-f]{4})\*?\s+(.+?)(\t|\s{2,}|$)", ln)
        if m and m.group(2).strip() == desc: return int(m.group(1), 16)
    return None


def boot_next(num):
    """Lần khởi động SAU (1 lần) vào mục Boot`num`: ghi biến BootNext qua efivarfs, không được thì efibootmgr -n. → (được?, lời lỗi)."""
    try:
        if C.efi_boot_next(LinuxSys(), num): return True, ""
    except Exception: pass
    rc, out = sh(["efibootmgr", "-q", "-n", "%04X" % int(num)], 30)
    return rc == 0, ("efibootmgr: " + out.strip()[-120:]) if rc else ""


def root_hint():
    """Vị trí phân vùng gốc Linux đang chạy trên ổ: {"offset", "size"} tính bằng byte (giống vị trí ổ C: mà agent Windows ghi)."""
    rc, out = sh(["findmnt", "-no", "SOURCE", "/"], 10)
    dev = re.sub(r"\[.*\]$", "", out.strip().splitlines()[0]) if rc == 0 and out.strip() else ""
    name = os.path.basename(os.path.realpath(dev)) if dev else ""
    try:
        start = int(read("/sys/class/block/%s/start" % name, "0")) * 512
        size = int(read("/sys/class/block/%s/size" % name, "0")) * 512
        return {"offset": start, "size": size} if start and size else {}
    except ValueError:
        return {}


def root_disk():
    """(serial, model) của ổ chứa hệ thống (dấu phần cứng dự phòng khi seed.json không có)."""
    rc, out = sh(["findmnt", "-no", "SOURCE", "/"], 10)
    dev = re.sub(r"\[.*\]$", "", out.strip().splitlines()[0]) if rc == 0 and out.strip() else ""
    rc, pk = sh(["lsblk", "-no", "PKNAME", dev], 10) if dev else (1, "")
    disk = pk.strip().splitlines()[0] if rc == 0 and pk.strip() else ""
    rc, txt = sh(["lsblk", "-dno", "SERIAL,MODEL", "/dev/" + disk], 10) if disk else (1, "")
    f = txt.strip().split(None, 1) if rc == 0 else []
    return (f[0] if f else ""), (f[1] if len(f) > 1 else "")


# ====================================================================================== agent
class LinuxAgent(pcagent.Agent):
    def __init__(self, sysx, host, net, base=BASE, log=None, rec=None):
        super().__init__(sysx, host, net, base=base, log=log)
        seed = C.load_json(sysx, self.p("seed.json")) or {}
        self.rec = rec or LinuxRec(seed.get("rec_uuid") or "", self.log)
        self.result_sent = False

    def p(self, rel): return os.path.join(self.base, P(rel))

    # ---- thông tin máy cho web
    def calc_hw(self):
        ser, mod = root_disk()
        return pcagent.hw_id(self.h.smbios(), ser, mod)

    def info(self):
        cpu, cores = self.h.cpu()
        i = {"host": self.h.hostname(), "os": "cachyos", "os_ver": self.h.os_ver(), "os_name": self.h.os_name(), "agent": LINUX_VER, "cpu": cpu,
             "cores": cores, "ram_gb": self.h.ram_gb(), "gpus": self.h.gpus()[:6], "lan_ip": self.h.lan_ip(), "uptime": self.h.uptime(),
             "fw": self.s.firmware(), "linux": True}
        try: i["rec"] = self.rec.status()
        except Exception as e: i["err"] = str(e)[:120]
        smb = self.h.smbios()
        i["board"] = (smb.get("board") or (smb.get("vendor", "") + " " + smb.get("product", "")).strip())[:60]
        try:
            g = sh(["id", "-nG", self.h.user], 10)[1].split() if self.h.user else []
            i["sec"] = {"std": "wheel" not in g, "hard": True, "lock": True}
        except Exception: pass
        i["rmt"] = {"v": "", "s": "ban Linux chua co dieu khien tu xa", "age": 0}
        return i

    # ---- kết quả lần cài CachyOS (cb-install.sh ghi lên phân vùng cứu hộ)
    def check_result(self):
        if self.pending_done or self.result_sent: return
        try: res = self.rec.take_result()
        except Exception: res = None
        if not isinstance(res, dict): self.result_sent = True; return
        if not re.fullmatch(r"[0-9]{1,18}", str(res.get("id"))):
            self.rec.take_result(clear=True); self.result_sent = True; return
        self.done(int(res["id"]), res.get("ok"), {k: res.get(k) for k in ("msg", "os", "secs", "pe")})
        self.result_from_rec = True

    def job_orphan(self): return None
    def pe_sync(self): return None
    def remote_keep(self): return None
    def rec_admin(self, want): return True

    def poll(self, send_info=True):
        had = self.result_from_rec and self.pending_done is not None
        r = super().poll(send_info)
        if had and self.pending_done is None:                               # máy chủ đã nhận kết quả → xoá file trên phân vùng cứu hộ (lõi Windows chỉ xoá kiểu Windows)
            try: self.rec.take_result(clear=True)
            except Exception: pass
            self.result_from_rec = False; self.result_sent = True
        return r

    # ---- công tắc "Cho khách quyền Admin" của shop → khách trong nhóm wheel (sudo) hay không
    def admin_sync(self, r):
        want = r.get("cust_admin")
        if not isinstance(want, bool) or not self.h.user: return False
        g = sh(["id", "-nG", self.h.user], 10)[1].split()
        if want == ("wheel" in g): return False
        rc, out = sh(["gpasswd", "-a" if want else "-d", self.h.user, "wheel"], 30)
        self.log("công tắc quyền Admin: %s khách %s nhóm wheel (sudo)%s" % ("thêm" if want else "bỏ", self.h.user, "" if rc == 0 else " — LỖI " + out.strip()[-100:]))
        try:
            self.cfg["user_admin"] = want; C.save_json(self.s, self.p("cb.json"), self.cfg)
        except Exception: pass
        return rc == 0

    # ---- lệnh
    def handle(self, o):
        cmd, oid, args = o.get("cmd"), o.get("id"), o.get("args") or {}
        if cmd != "reinstall" and cmd != "update": return super().handle(o)
        self.log("nhận lệnh #%s: %s %s" % (oid, cmd, {k: v for k, v in args.items() if k != "ticket"}))
        if cmd == "update":
            v = self.update(self.last_manifest, force=True)
            self.done(oid, bool(v), {"msg": v or "không có bản mới / tải lỗi", "agent": LINUX_VER}); return
        seed = C.load_json(self.s, self.p("seed.json")) or {}
        if isinstance(seed, dict) and seed.get("from") == "job" and oid is not None and str(seed.get("order")) == str(oid):
            self.log("lệnh #%s: CachyOS này do chính lệnh đó cài ra (kết quả chưa tới web) → báo đã xong, KHÔNG cài lại" % oid)
            self.done(oid, True, {"msg": "xong (agent tự nhận ra: CachyOS do chính lệnh này cài)", "os": seed.get("os"), "pe": seed.get("pe") or "cb-install"}); return
        try:
            old = self.rec.pending_job()
            tries = int((old or {}).get("tries") or 0) if isinstance(old, dict) and str(old.get("id")) == str(oid) else 0
            if tries >= 2:                                          # đã khởi động lại 2 lần mà máy vẫn về CachyOS (BIOS bỏ qua BootNext?) → thôi, báo lỗi
                self.rec.drop_job()
                self.done(oid, False, {"msg": "máy không khởi động được vào bộ cài lại (đã thử 2 lần) — kiểm BIOS: phải còn mục 'Windows Boot Manager'"}); return
            job = {"id": oid, "os": args.get("os"), "wipe": args.get("wipe") or "all", "ticket": args.get("ticket"), "hw": (self.ident or {}).get("hw"), "tries": tries + 1}
            img = self.rec.stage_job(job, self.h.hostname(), self.s.now(), root_hint())
        except C.Stop as e:
            self.done(oid, False, {"msg": str(e)[:300]}); return
        except Exception as e:
            self.done(oid, False, {"msg": "lỗi chuẩn bị cài lại: %s" % str(e)[:200]}); self.log(traceback.format_exc()); return
        self.log("đã ghi lệnh cài lại %s (%s) → khởi động lại vào bộ cài sau 30 giây" % (img["id"], job["wipe"]))
        self.rebooting = True
        what = "CAI LAI CachyOS" if C.is_linux(img) else "CAI WINDOWS %s" % str(img["id"]).upper()
        self.h.power(reboot=True, delay=30, msg="CloudBlue: may se %s sau 30 giay. Du lieu tren may se bi xoa." % what)

    # ---- tự cập nhật (mục "linux" + agent/lib của bản kê admin công bố)
    def update(self, m, force=False):
        if not isinstance(m, dict) or not isinstance(m.get("linux"), dict) or SELF_REL not in m["linux"]: return None
        ver = str(m.get("ver") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,24}", ver) or (ver == self.bad_update and not force): return None
        base = str(m.get("base") or "")
        if not base.startswith(self.cfg.get("update_base") or pcagent.UPDATE_BASE): self.bad_update = ver; return None
        want = {rel: sha for rel, sha in (m.get("files") or {}).items() if rel in LIB_FILES}
        want.update({rel: sha for rel, sha in m["linux"].items() if LINUX_REL.match(str(rel)) and str(rel).endswith(".py")})
        cur = {}
        for rel in want:
            try: cur[rel] = hashlib.sha256(self.s.read_bytes(self.p(rel))).hexdigest()
            except Exception: cur[rel] = ""
        todo = {rel: sha for rel, sha in want.items() if cur.get(rel) != sha and re.fullmatch(r"[0-9a-f]{64}", str(sha))}
        if not todo: return None
        try:
            got = {}
            for rel, sha in todo.items():
                data = self.net.get(base.rstrip("/") + "/" + rel)
                if hashlib.sha256(data).hexdigest() != sha: raise ValueError("sai mã kiểm: %s" % rel)
                compile(data.decode("utf-8"), rel, "exec")
                got[rel] = data
            stage = self.p("update/" + ver)
            for rel in set(LIB_FILES) | {SELF_REL}:
                src = got.get(rel)
                if src is None:
                    try: src = self.s.read_bytes(self.p(rel))
                    except Exception: src = None
                if src is not None: self.s.write_bytes(stage + "/" + rel, src)
            ok, out = self.h.selfcheck(stage + "/" + SELF_REL)
            if not ok: raise ValueError("bản mới chạy thử không đạt: %s" % out)
            for rel, data in got.items():
                dst = self.p(rel)
                try:
                    if self.s.exists(dst): self.s.write_bytes(dst + ".bak", self.s.read_bytes(dst))
                except Exception: pass
                self.s.write_bytes(dst, data)
            try:                                                            # bộ cài trên phân vùng cứu hộ cũng lên bản mới (lần cài lại CachyOS sau dùng)
                root = self.rec.mount(rw=True)
                if root:
                    for rel, data in got.items(): LinuxSys().write_bytes(root + "cb/" + rel, data)
            except Exception as e:
                self.log("chưa cập nhật được phân vùng cứu hộ: %s" % e)
            finally:
                self.rec.umount()
            shutil.rmtree(stage, ignore_errors=True)
            self.log("ĐÃ CẬP NHẬT agent Linux theo bản %s (%d file) → chạy lại agent" % (ver, len(got)))
            self.restart = True
            return ver
        except Exception as e:
            self.log("cập nhật bản %s lỗi: %s" % (ver, e)); self.bad_update = ver
            return None


# ====================================================================================== chạy thật
def make_logger(base=BASE):
    d = os.path.join(base, "logs"); os.makedirs(d, exist_ok=True)

    def log(m):
        ln = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        try:
            p = os.path.join(d, "agent.log")
            if os.path.exists(p) and os.path.getsize(p) > 2 << 20: os.replace(p, p + ".1")
            with open(p, "a", encoding="utf-8") as f: f.write(ln + "\n")
        except OSError: pass
        print(ln, flush=True)
    return log


def build(base=BASE):
    log = make_logger(base)
    sysx = LinuxSys(log)
    cfg = C.load_json(sysx, os.path.join(base, "cb.json")) or {}
    seed = C.load_json(sysx, os.path.join(base, "seed.json")) or {}
    host = LinuxHost(seed.get("user") or C.linux_user(cfg.get("user") or "PC"))
    return LinuxAgent(sysx, host, pcagent.Net(cfg, base), base, log), host, log


def cmd_run(argv):
    ag, host, log = build()
    if not host.mutex(): print("agent dang chay roi"); return 0
    log("agent CloudBlue (Linux) %s chạy — máy %s" % (LINUX_VER, host.hostname()))
    while True:
        try: nap = ag.tick()
        except Exception: log("lỗi vòng chính: " + traceback.format_exc()); nap = 60
        if ag.restart: log("thoát để chạy bản mới"); return 0
        time.sleep(max(1, min(nap, 900)))


def cmd_status(argv):
    ag, host, log = build()
    i = ag.info()
    print(json.dumps({"agent": LINUX_VER, "registered": bool(ag.ident), "name": ag.name, "rent": ag.rent_line(), "info": i}, ensure_ascii=False, indent=1))
    return 0


def cmd_reinstall(argv):
    if not argv: print("cach dung: cbagent.py reinstall <ban: 22h2 | 1511 | cachyos> [all|disk|system]"); return 2
    ag, host, log = build()
    job = {"id": "local-%d" % int(time.time()), "os": argv[0], "wipe": argv[1] if len(argv) > 1 else "all", "hw": (ag.ident or {}).get("hw"), "tries": 1}
    try: img = ag.rec.stage_job(job, host.hostname(), time.time(), root_hint())
    except C.Stop as e: print("KHONG duoc: %s" % e); return 1
    print("Da ghi lenh cai %s - khoi dong lai sau 30 giay." % img["id"])
    host.power(reboot=True, delay=30, msg="CloudBlue: may se cai lai sau 30 giay.")
    return 0


def cmd_selfcheck(argv):
    s = LinuxSys(); h = LinuxHost("")
    assert P("logs\\a.json") == "logs/a.json"
    assert isinstance(h.cpu(), tuple) and h.uptime() >= 0
    assert C.linux_user("PC") == "pc" and pcagent.Agent and LinuxAgent
    print("selfcheck OK cbagent %s / pcagent %s" % (LINUX_VER, pcagent.AGENT_VER)); return 0


def main(argv):
    cmds = {"run": cmd_run, "status": cmd_status, "reinstall": cmd_reinstall, "selfcheck": cmd_selfcheck}
    if not argv or argv[0] not in cmds: print("cbagent %s: run | status | selfcheck | reinstall <ban> [all|disk|system]" % LINUX_VER); return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
