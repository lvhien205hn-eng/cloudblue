# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbremote.py — CloudBlue PC (CachyOS): ĐIỀU KHIỂN TỪ XA, chạy bằng ROOT (cbagent mở + giữ chạy, như pcagent mở pcremote trên Windows).
#  Dùng NGUYÊN giao thức / trạm phát hình của pcremote.py (nối ra máy chủ, phiên người xem, nén theo mạng, chuột / phím / bộ nhớ copy) — chỉ
#  thay phần đụng hệ điều hành:
#    · quay màn hình + bơm chuột / phím: cbcap.py chạy BẰNG TÀI KHOẢN KHÁCH trong phiên KDE (Wayland) → GStreamer x264 (CPU, không cần card
#      hình) → RTP về cổng UDP nội bộ của chương trình này. 22.11g: cbcap nói THẲNG với KWin (zkde_screencast + fake_input) bằng bản python riêng
#      (cbcap-py) mà tệp .desktop do chương trình này cài cấp quyền → không bao giờ hiện hộp hỏi; KWin chưa cho thì mới đi cổng XDG.
#      Mở không được → báo người xem lý do cụ thể (trước khi trạm hết 25 giây chờ) + ghi logs/remote.err (agent báo lên web).
#    · cbcap.py không giữ bí mật nào: mã máy / mã riêng chỉ chương trình root này đọc (/opt/cloudblue, 0700)
#    · 23.11a: dựng lại danh sách app của KDE (ksycoca) bằng ĐÚNG môi trường phiên Plasma (có XDG_MENU_PREFIX=plasma-) — bản cũ thiếu biến
#      này nên bộ đệm KHÔNG CÒN APP NÀO (thanh tác vụ 3 ô trắng, menu / tìm kiếm trống: khách tưởng không có Firefox, không mở được terminal);
#      + lối tắt Firefox · Konsole · Dolphin trên màn hình nền (1 lần / tài khoản)
#    · 23.11b: DÁN — khách bấm Dán / Ctrl+V mà chữ không vào Konsole: cbcap đặt bộ nhớ copy (wl-copy, không có thì Klipper) rồi hỏi KWin cửa
#      sổ đang chọn → dòng lệnh dán bằng Ctrl+Shift+V, app thường Ctrl+V (LinuxIO.paste)
#    · 27.11a: máy ảo VPS NVMe Linux (Ubuntu + XFCE, phiên X11): tìm phiên X của khách (DISPLAY / XAUTHORITY lấy từ tiến trình phiên),
#      bỏ qua phần riêng của KDE (quyền KWin, ksycoca) — cbcap tự quay bằng x11grab + XTEST
#  Lệnh:  cbremote.py run | selfcheck | version          Nhật ký: /opt/cloudblue/logs/remote.log
# =====================================================================================================
import fcntl, grp, json, os, pwd, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("CB_BASE") or os.path.abspath(os.path.join(HERE, ".."))          # /opt/cloudblue
for _p in (os.path.join(BASE, "lib"), os.path.join(BASE, "agent"), HERE):
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import pcremote as R                                             # noqa: E402

LINUX_REMOTE_VER = "27.11a"
CAP_SRC = os.path.join(HERE, "cbcap.py")
CAP_DIR = "/usr/local/lib/cloudblue"                             # bản cbcap.py tài khoản khách đọc được (root sở hữu, khách không sửa được)
APPS_DIR = "/usr/share/applications"
KWIN_DESKTOP = "vn.cloudblue.cbcap.desktop"                       # 22.11g: KWin cho cbcap-py dùng zkde_screencast + fake_input (không hộp hỏi)
LOCK = "/run/cloudblue-remote.lock"
SIZE_TTL = 15.0
OPEN_WAIT = 20.0                                                  # chờ cbcap mở màn hình (cbcap tự giới hạn 17 giây; trạm chờ máy PC 25 giây)
START_WAIT = 20.0
KWIN_ONLY_WAIT = 8.0                                              # 22.11h · KWin chưa có quyền mới: chỉ thử KWin (vài giây) rồi báo người xem khởi động lại máy
SYCOCA_KEYS = ("XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_MENU_PREFIX", "XDG_CURRENT_DESKTOP",
               "LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "KDE_FULL_SESSION", "KDE_SESSION_VERSION")   # 23.11a · tên + nội dung bộ đệm ksycoca theo các biến này
DESK_APPS = ("firefox.desktop", "org.kde.konsole.desktop", "org.kde.dolphin.desktop")     # 23.11a · lối tắt màn hình nền: trình duyệt · cửa sổ lệnh · thư mục


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f: j = json.load(f)
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def _run(argv, timeout=10, **kw):
    try: return subprocess.run(argv, capture_output=True, timeout=timeout, **kw)
    except (OSError, subprocess.TimeoutExpired): return None


# ====================================================================================== phiên đồ hoạ của khách
def user_session(user):
    """(pwd, môi trường) của phiên KDE đang mở của tài khoản khách — chưa đăng nhập / chưa có Wayland → (pwd, None)."""
    try: pw = pwd.getpwnam(user)
    except KeyError: return None, None
    rt = "/run/user/%d" % pw.pw_uid
    way = sorted(f for f in (os.listdir(rt) if os.path.isdir(rt) else []) if re.fullmatch(r"wayland-\d+", f))
    if not way: return pw, x11_env(pw, rt)                          # 27.11a: không có Wayland → phiên X11 (XFCE) nếu có
    if not os.path.exists(os.path.join(rt, "bus")): return pw, None
    env = {"HOME": pw.pw_dir, "USER": user, "LOGNAME": user, "SHELL": pw.pw_shell or "/bin/bash", "PATH": "/usr/local/bin:/usr/bin:/bin",
           "LANG": os.environ.get("LANG") or "C.UTF-8", "XDG_RUNTIME_DIR": rt, "DBUS_SESSION_BUS_ADDRESS": "unix:path=%s/bus" % rt,
           "WAYLAND_DISPLAY": way[0], "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}
    return pw, env


X11_COMMS = ("xfce4-session", "xfwm4", "xfdesktop", "xfce4-panel", "lxqt-session", "mate-session", "openbox")


def x11_env(pw, rt):
    """27.11a · môi trường phiên X11 của khách (lấy DISPLAY / XAUTHORITY / bus phiên từ tiến trình phiên đồ hoạ) → dict | None (chưa đăng nhập)."""
    e = {}
    for comm in X11_COMMS:
        pid = _user_pid(pw.pw_uid, comm)
        if pid is not None:
            e = _proc_env(pid)
            if e.get("DISPLAY"): break
    if not e.get("DISPLAY") or not re.fullmatch(r":\d{1,3}(\.\d)?", e["DISPLAY"]): return None
    xa = e.get("XAUTHORITY") or os.path.join(pw.pw_dir, ".Xauthority")
    env = {"HOME": pw.pw_dir, "USER": pw.pw_name, "LOGNAME": pw.pw_name, "SHELL": pw.pw_shell or "/bin/bash", "PATH": "/usr/local/bin:/usr/bin:/bin",
           "LANG": os.environ.get("LANG") or "C.UTF-8", "DISPLAY": e["DISPLAY"], "XAUTHORITY": xa, "XDG_SESSION_TYPE": "x11",
           "XDG_CURRENT_DESKTOP": e.get("XDG_CURRENT_DESKTOP") or "XFCE"}
    if os.path.isdir(rt): env["XDG_RUNTIME_DIR"] = rt
    bus = e.get("DBUS_SESSION_BUS_ADDRESS") or ("unix:path=%s/bus" % rt if os.path.exists(os.path.join(rt, "bus")) else "")
    if bus: env["DBUS_SESSION_BUS_ADDRESS"] = bus
    return env


def _same(path, data):
    try:
        with open(path, "rb") as f: return f.read() == data
    except OSError:
        return False


def _put(path, data, mode):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f: f.write(data)
    os.chmod(tmp, mode); os.replace(tmp, path)


def install_cap(cap_dir=None):
    """Chép cbcap.py sang chỗ tài khoản khách đọc được (chỉ khi khác bản đang có)."""
    cap_dir = cap_dir or CAP_DIR
    os.makedirs(cap_dir, mode=0o755, exist_ok=True)
    dst = os.path.join(cap_dir, "cbcap.py")
    with open(CAP_SRC, "rb") as f: data = f.read()
    if not _same(dst, data): _put(dst, data, 0o644)
    return dst


_KW = {"py": None, "t": 0.0, "kwin": None}                         # bản python riêng đang dùng · lúc cài · KWin (pid) đã làm mới ksycoca


def install_kwin_access(log=lambda m: None, py="/usr/bin/python3", cap_dir=None, apps=None):
    """22.11g — cho cbcap nói thẳng với KWin (không qua cổng XDG → không hộp hỏi trên màn hình máy):
         · cbcap-py: BẢN SAO python của máy ở đường dẫn riêng (KWin nhận chương trình theo /proc/<pid>/exe) + pyvenv.cfg (bản sao tìm thư viện python)
         · tệp .desktop: Exec = cbcap-py, X-KDE-Wayland-Interfaces = zkde_screencast_unstable_v1, org_kde_kwin_fake_input (cách KWin cấp quyền cho
           xdg-desktop-portal-kde / krdp). python của máy được cập nhật → chép lại.
       → (đường dẫn cbcap-py | None, tệp .desktop vừa đổi?). Lỗi → (None, False): cbcap chạy bằng python thường (đi cổng XDG như 22.11f)."""
    cap_dir = cap_dir or CAP_DIR
    try:
        real = os.path.realpath(py)
        with open(real, "rb") as f: data = f.read()
        os.makedirs(cap_dir, mode=0o755, exist_ok=True)
        dst = os.path.join(cap_dir, "cbcap-py")
        fresh = not _same(dst, data)
        if fresh: _put(dst, data, 0o755)
        cfg = ("home = %s\ninclude-system-site-packages = false\n" % os.path.dirname(real)).encode()
        if not _same(os.path.join(cap_dir, "pyvenv.cfg"), cfg): _put(os.path.join(cap_dir, "pyvenv.cfg"), cfg, 0o644)
        if fresh or _KW["py"] != dst:
            r = _run([dst, "-I", "-B", "-c", "import json, socket, struct, threading, subprocess"], 30)
            if r is None or r.returncode != 0:
                log("ban python rieng cho cbcap chua chay duoc (%s) -> dung python thuong (cong XDG)" %
                    (((r.stderr or b"")[-160:].decode("utf-8", "replace").strip() or r.returncode) if r is not None else "loi"))
                _KW["py"] = None; return None, False
        desk = ("[Desktop Entry]\nType=Application\nName=CloudBlue - quay man hinh\nExec=%s\nNoDisplay=true\n"
                "X-KDE-Wayland-Interfaces=zkde_screencast_unstable_v1,org_kde_kwin_fake_input\n" % dst).encode()
        path = os.path.join(apps or APPS_DIR, KWIN_DESKTOP)
        changed = not _same(path, desk)
        if changed:
            _put(path, desk, 0o644); log("da cap quyen KWin cho cbcap-py (%s)" % path)
        _KW["py"], _KW["t"] = dst, time.time()
        return dst, changed
    except OSError as e:
        log("chua cap quyen KWin cho cbcap: %s" % e)
        _KW["py"] = None
        return None, False


KWIN_ENV_FILE = "/etc/environment.d/90-cloudblue-kwin.conf"
KWIN_ENV = ("KWIN_FORCE_SW_CURSOR=1", "KWIN_WAYLAND_NO_PERMISSION_CHECKS=1")


def ensure_kwin_env(log=lambda m: None, path=None, etc_env="/etc/environment"):
    """22.11g — máy cài từ bản cũ: bật cho KWin KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 (cbcap dùng thẳng zkde_screencast + fake_input, không qua
       cổng XDG → không hộp hỏi). Có hiệu lực từ lần đăng nhập / khởi động sau. Máy cho thuê 1 khách, phiên là của khách. → vừa đổi gì không."""
    path = path or KWIN_ENV_FILE
    want = ("# CloudBlue: dieu khien tu xa can con tro ve bang phan mem + quay man hinh / bam phim thang qua KWin\n" + "\n".join(KWIN_ENV) + "\n").encode()
    changed = False
    try:
        os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
        if not _same(path, want): _put(path, want, 0o644); changed = True
        try:
            with open(etc_env, encoding="utf-8", errors="replace") as f: cur = f.read()
        except OSError:
            cur = ""
        add = [kv for kv in KWIN_ENV if not re.search(r"(?m)^" + re.escape(kv.split("=", 1)[0]) + "=", cur)]
        if add:
            with open(etc_env, "a", encoding="utf-8") as f: f.write(("\n" if cur and not cur.endswith("\n") else "") + "\n".join(add) + "\n")
            changed = True
        if changed: log("da bat cho KWin quay man hinh / bam phim truc tiep (%s) - co hieu luc tu lan khoi dong lai may sau" % path)
    except OSError as e:
        log("chua ghi duoc %s: %s" % (path, e))
    return changed


def kwin_env_ok(user):
    """KWin đang chạy đã có KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 chưa → True / False · None: chưa có KWin (khách chưa đăng nhập)."""
    try: pw = pwd.getpwnam(user)
    except KeyError: return None
    pid = _kwin_pid(pw.pw_uid)
    if pid is None: return None
    try:
        with open("/proc/%d/environ" % pid, "rb") as f: return b"KWIN_WAYLAND_NO_PERMISSION_CHECKS=1" in f.read().split(b"\0")
    except OSError:
        return None


def _user_pid(uid, comm):
    """pid tiến trình tên `comm` của tài khoản khách (None nếu chưa có)."""
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        try:
            with open("/proc/%s/comm" % d) as f:
                if f.read().strip() != comm: continue
            if os.stat("/proc/%s" % d).st_uid == uid: return int(d)
        except OSError:
            continue
    return None


def _kwin_pid(uid):
    """pid kwin_wayland của tài khoản khách (None nếu chưa có)."""
    return _user_pid(uid, "kwin_wayland")


def _proc_env(pid):
    """Biến môi trường của 1 tiến trình ({} nếu không đọc được)."""
    try:
        with open("/proc/%d/environ" % pid, "rb") as f: raw = f.read().split(b"\0")
    except (OSError, TypeError):
        return {}
    out = {}
    for kv in raw:
        k, _, v = kv.decode("utf-8", "replace").partition("=")
        if k: out[k] = v
    return out


def session_env(uid):
    """Môi trường phiên Plasma của khách: plasmashell (có đủ XDG_MENU_PREFIX…) → không có thì KWin → {}."""
    for comm in ("plasmashell", "kwin_wayland"):
        pid = _user_pid(uid, comm)
        if pid is not None:
            e = _proc_env(pid)
            if e: return e
    return {}


def sycoca_env(env, sess, exists=os.path.isfile):
    """23.11a — môi trường chạy kbuildsycoca6 GIỐNG phiên Plasma. Thiếu XDG_MENU_PREFIX thì kbuildsycoca6 tìm 'applications.menu' (Arch / CachyOS
       không có, chỉ có plasma-applications.menu) → không nạp thư mục app nào → bộ đệm rỗng: thanh tác vụ hiện ô trắng, menu và ô tìm kiếm không
       ra app. Phiên không có biến này (KWin bật sớm…) → tự chọn tiền tố có tệp menu thật (plasma- trước)."""
    kenv = dict(env)
    for k in SYCOCA_KEYS:
        if sess.get(k): kenv[k] = sess[k]
    if not kenv.get("XDG_MENU_PREFIX"):
        dirs = [d for d in (kenv.get("XDG_CONFIG_DIRS") or "").split(":") if d.startswith("/")] + ["/etc/xdg"]
        if not any(exists(os.path.join(d, "menus", "applications.menu")) for d in dirs):
            pre = next((p for p in ("plasma-", "arch-", "kf6-", "kde-") if any(exists(os.path.join(d, "menus", p + "applications.menu")) for d in dirs)), None)
            if pre: kenv["XDG_MENU_PREFIX"] = pre
    return kenv


def refresh_sycoca(user, log=lambda m: None, force=False):
    """KWin tra tệp .desktop qua bộ đệm ksycoca của phiên → chạy kbuildsycoca6 bằng tài khoản khách với CÙNG biến môi trường của KWin
       (tên tệp bộ đệm tính theo XDG_DATA_DIRS). Mỗi KWin (pid) chỉ làm 1 lần, trừ khi tệp .desktop vừa đổi."""
    pw, env = user_session(user)
    if env is None: return False
    pid = _kwin_pid(pw.pw_uid)
    if pid is None or (pid == _KW["kwin"] and not force): return False
    kenv = sycoca_env(env, session_env(pw.pw_uid) or _proc_env(pid))      # 23.11a: CÙNG môi trường phiên Plasma (có XDG_MENU_PREFIX)
    r = _run(["kbuildsycoca6"], 120, user=pw.pw_uid, group=pw.pw_gid, env=kenv, cwd=pw.pw_dir)
    ok = r is not None and r.returncode == 0
    _KW["kwin"] = pid
    log("lam moi danh sach ung dung cua KDE (kbuildsycoca6, menu %s): %s" % (kenv.get("XDG_MENU_PREFIX") or "-",
        "xong" if ok else ((r.stderr or b"")[-120:].decode("utf-8", "replace").strip() if r else "khong chay duoc")))
    return ok


def desktop_shortcuts(user, log=lambda m: None, mark_dir=None, apps_dir=APPS_DIR, names=DESK_APPS, home=None):
    """23.11a (khách: 'không có trình duyệt, không mở được cmd') — lối tắt Firefox · Konsole · Dolphin lên màn hình nền, 1 LẦN cho mỗi tài khoản
       (khách xoá thì thôi, không tạo lại). Lối tắt = liên kết tới tệp .desktop của hệ thống (KDE coi là app tin cậy, bấm là mở). Chạy BẰNG TÀI KHOẢN
       KHÁCH (root không ghi vào thư mục của khách). → True khi đã xong (hoặc đã làm từ trước)."""
    try: pw = pwd.getpwnam(user)
    except KeyError: return False
    mark = os.path.join(mark_dir or BASE, "desktop-shortcuts.%s.done" % user)
    if os.path.exists(mark): return True
    srcs = [os.path.join(apps_dir, n) for n in names if os.path.isfile(os.path.join(apps_dir, n))]
    if not srcs: return False
    home = home or pw.pw_dir
    sh = ('d=$(xdg-user-dir DESKTOP 2>/dev/null); case "$d" in ""|"$HOME"|"$HOME/") d="$HOME/Desktop";; esac; mkdir -p "$d" || exit 3; n=0; '
          'for f in "$@"; do b=${f##*/}; if [ ! -e "$d/$b" ] && [ ! -L "$d/$b" ]; then ln -s "$f" "$d/$b" && n=$((n+1)); fi; done; echo "$n $d"')
    env = {"HOME": home, "USER": user, "LOGNAME": user, "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
    r = _run(["/bin/sh", "-c", sh, "sh"] + srcs, 20, user=pw.pw_uid, group=pw.pw_gid, env=env, cwd=home)
    if r is None or r.returncode != 0:
        log("chua tao duoc loi tat man hinh nen: %s" % ((r.stderr or b"")[-120:].decode("utf-8", "replace").strip() if r else "khong chay duoc"))
        return False
    try:
        with open(mark, "w", encoding="utf-8") as f: f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(names)))
    except OSError:
        pass
    log("loi tat man hinh nen (Firefox / Konsole / Dolphin) cho khach %s: %s" % (user, r.stdout.decode("utf-8", "replace").strip()[:200]))
    return True


# ====================================================================================== tiến trình cbcap.py (tài khoản khách)
class Helper:
    """cbcap.py chạy bằng tài khoản khách; nói chuyện qua socketpair SEQPACKET (mỗi gói 1 lệnh JSON). Mở khi có người xem, đóng khi hết."""
    def __init__(self, user, log=None):
        self.user, self.log = user, log or (lambda m: None)
        self.proc = None; self.sock = None; self.lock = threading.RLock(); self.wl = threading.Lock()
        self.waits = {}; self.nid = 0; self.size = None; self.dead_pid = None; self.cur_pid = None

    def alive(self): return self.proc is not None and self.proc.poll() is None and self.sock is not None

    def ensure(self):
        with self.lock:
            if self.alive(): return True
            self.close()
            pw, env = user_session(self.user)
            if pw is None: raise RuntimeError("khong co tai khoan khach '%s'" % self.user)
            if env is None: raise RuntimeError("khach chua dang nhap man hinh (chua co phien KDE)")
            script = install_cap()
            py, changed = install_kwin_access(self.log) if env.get("WAYLAND_DISPLAY") else (None, False)   # 22.11g (27.11a: phiên X11 không cần)
            if py and kwin_env_ok(self.user) is not True:              # 22.11h: KWin đã có KWIN_WAYLAND_NO_PERMISSION_CHECKS → khỏi kbuildsycoca6 (đỡ vài giây)
                try:
                    if refresh_sycoca(self.user, self.log, force=changed): time.sleep(2)   # KWin chỉ dò lại ksycoca mỗi 1,5 giây
                except Exception as e: self.log("kbuildsycoca6 loi: %r" % (e,))
            mine, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                groups = [g.gr_gid for g in grp.getgrall() if self.user in g.gr_mem]
                self.proc = subprocess.Popen([py or "/usr/bin/python3", "-I", "-B", script, "serve", "--fd", str(child.fileno())], user=pw.pw_uid, group=pw.pw_gid,
                                             extra_groups=groups, env=env, cwd=pw.pw_dir, pass_fds=(child.fileno(),), stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
            finally:
                child.close()
            self.sock = mine; self.size = None; self.dead_pid = None
            threading.Thread(target=self._reader, args=(mine, self.proc), daemon=True).start()
            threading.Thread(target=self._errlog, args=(self.proc,), daemon=True).start()
            return True

    def _errlog(self, proc):
        try:
            for ln in iter(proc.stderr.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s: self.log("cbcap: " + s[:300])
        except Exception: pass

    def _reader(self, sock, proc):
        while True:
            try: data = sock.recv(256 * 1024)
            except OSError: data = b""
            if not data: break
            try: j = json.loads(data.decode("utf-8"))
            except ValueError: continue
            if "log" in j: self.log("cbcap: %s" % j["log"])
            if j.get("ev") == "stopped": self.dead_pid = j.get("pid") or self.cur_pid
            if j.get("id") is not None:
                w = self.waits.get(j["id"])
                if w is not None: w[1] = j; w[0].set()
        with self.lock:
            if self.sock is sock: self.sock = None
        for w in list(self.waits.values()): w[0].set()

    def send(self, op, **kw):
        s = self.sock
        if s is None: return False
        kw["op"] = op
        try:
            with self.wl: s.send(json.dumps(kw).encode("utf-8"))
            return True
        except OSError:
            return False

    def request(self, op, timeout=10.0, **kw):
        with self.lock:
            self.nid += 1; rid = self.nid
        ev = threading.Event(); w = [ev, None]; self.waits[rid] = w
        try:
            if not self.send(op, id=rid, **kw): raise RuntimeError("cbcap chua chay")
            if not ev.wait(timeout): raise RuntimeError("cbcap khong tra loi lenh %s sau %d giay" % (op, timeout))
            r = w[1]
            if r is None: raise RuntimeError("cbcap da thoat")
            if not r.get("ok"): raise RuntimeError(str(r.get("err") or "loi")[:300])
            if r.get("size"): self.size = tuple(int(v) for v in r["size"])
            return r
        finally:
            self.waits.pop(rid, None)

    def close(self):
        with self.lock:
            s, p = self.sock, self.proc
            self.sock = None; self.proc = None; self.size = None
        if s is not None:
            try: s.send(b'{"op": "bye"}')
            except OSError: pass
            try: s.close()
            except OSError: pass
        if p is not None and p.poll() is None:
            try: p.wait(3)
            except subprocess.TimeoutExpired: p.kill()


# ====================================================================================== chuột / phím / màn hình cho pcremote
class ViewerError(RuntimeError):
    """Lỗi kèm lời báo cho người xem (pcremote gửi nguyên văn qua S_ERROR — trạm chuyển cho khách)."""
    def __init__(self, msg, viewer_msg):
        RuntimeError.__init__(self, msg); self.viewer_msg = viewer_msg


def note_error(msg, base=None):
    """Ghi lỗi mở màn hình gần nhất → cbagent gửi lên web (info.rmt.e) để admin / Claude xem được mà không cần ngồi ở máy."""
    try:
        with open(os.path.join(base or BASE, "logs", "remote.err"), "w", encoding="utf-8") as f: f.write("%d %s\n" % (time.time(), " ".join(str(msg).split())[:300]))
    except OSError:
        pass


class LinuxIO:
    """Thay WinIO của pcremote: mọi việc đụng màn hình / chuột / phím đi qua cbcap.py (tài khoản khách)."""
    def __init__(self, user, log=None, host=None):
        self.user, self.log, self.host = user, log or (lambda m: None), host
        self.helper = Helper(user, self.log)
        self.sz = (1920, 1080); self.sz_t = 0.0; self.clip_seen = None; self.clip_t = 0.0
        self.backend = ""; self.on_backend = None                         # 22.11g: "kwin" | "portal" — báo pcremote (thông số gửi người xem)
        self.kwin_env = lambda: kwin_env_ok(self.user)

    def screen(self):
        h = self.helper
        if h.alive() and h.size and h.size[0] > 0: return h.size
        if time.time() - self.sz_t > SIZE_TTL:
            self.sz_t = time.time(); got = self._kscreen()
            if got: self.sz = got
        return self.sz

    def _kscreen(self):
        """Cỡ màn hình đang dùng (kscreen-doctor của KDE, chạy bằng tài khoản khách) — chưa có phiên → None."""
        pw, env = user_session(self.user)
        if env is None: return None
        r = _run(["kscreen-doctor", "-j"], 10, user=pw.pw_uid, group=pw.pw_gid, env=env, cwd=pw.pw_dir)
        if r is None or r.returncode != 0: return None
        try:
            j = json.loads(r.stdout.decode("utf-8", "replace"))
            for o in j.get("outputs") or []:
                if not (o.get("enabled") and o.get("connected")): continue
                mode = next((m for m in o.get("modes") or [] if str(m.get("id")) == str(o.get("currentModeId"))), None)
                if mode:
                    w, h = int(mode["size"]["width"]), int(mode["size"]["height"])
                    sc = float(o.get("scale") or 1) or 1
                    return (int(w / sc) // 2 * 2, int(h / sc) // 2 * 2)
        except (ValueError, KeyError, TypeError):
            return None
        return None

    def move(self, x, y): self.helper.send("move", x=int(x), y=int(y))
    def button(self, b, down): self.helper.send("btn", b=int(b), d=bool(down))
    def wheel(self, v, horiz): self.helper.send("wheel", v=int(v), h=bool(horiz))
    def key(self, vk, down, ext=False): self.helper.send("key", vk=int(vk), d=bool(down), ext=bool(ext))
    def text(self, s): self.helper.send("text", s=str(s))

    def clip_set(self, s):
        self.clip_seen = s
        self.helper.send("clip_set", s=str(s))

    def paste(self, mode=1):
        """23.11b: dán bộ nhớ copy vào cửa sổ đang chọn — cbcap hỏi KWin cửa sổ gì rồi bấm đúng phím dán (Konsole: Ctrl+Shift+V…)."""
        self.helper.send("paste", m=int(mode))

    def clip_poll(self):
        """Chữ khách copy trên máy (đổi so với lần trước) → gửi người xem. Lần đầu chỉ ghi nhớ (không đẩy bộ nhớ copy cũ ra)."""
        if not self.helper.alive() or time.time() - self.clip_t < 1.5: return None
        self.clip_t = time.time()
        try: s = self.helper.request("clip_get", 3).get("s")
        except Exception: return None
        if s is None: return None
        if self.clip_seen is None: self.clip_seen = s; return None
        if s == self.clip_seen: return None
        self.clip_seen = s
        return s

    def awake(self, on):
        """Có người xem → mở cbcap + luồng màn hình (KWin trực tiếp / cổng XDG); hết người xem → đóng.
           Không mở được → ViewerError: người xem thấy LÝ DO (trước khi trạm hết 25 giây chờ) + ghi logs/remote.err."""
        if on:
            env = self.kwin_env()                     # False = KWin đang chạy mà CHƯA có quyền mới (máy chưa khởi động lại từ khi lên 22.11g)
            try:
                self.helper.ensure()
                if env is False: r = self.helper.request("open", KWIN_ONLY_WAIT, portal=False)   # 22.11h: chỉ thử KWin → báo "khởi động lại" sau vài giây
                else: r = self.helper.request("open", OPEN_WAIT)
            except Exception as e:
                why = " ".join(str(e).split())[:230]
                note_error(why); self.log("khong mo duoc man hinh de quay: %s" % why)
                if env is False or ("KWin chua cho" in why and self.kwin_env() is False):   # máy vừa lên 22.11g: KWin cũ chưa có quyền mới → khởi động lại 1 lần
                    raise ViewerError(why, "Máy Linux cần KHỞI ĐỘNG LẠI 1 lần để bật cách điều khiển mới: bấm Nguồn › Khởi động lại, "
                                           "đợi khoảng 3 phút rồi mở lại. (%s)" % why[:120])
                raise ViewerError(why, "Máy Linux chưa mở được màn hình để quay: %s" % why)
            self.backend = str(r.get("backend") or "")
            if self.on_backend is not None:
                try: self.on_backend(self.backend)
                except Exception: pass
            self.clip_seen = None
        else:
            self.helper.close()

    def notify(self, text):
        if self.host is not None:
            try: self.host.notify(text, 30)
            except Exception: pass


# ====================================================================================== bộ quay + nén (thay Encoder ffmpeg của pcremote)
class CapEncoder:
    """Cùng cách dùng với pcremote.Encoder: cbcap.py chạy GStreamer gửi RTP về cổng UDP nội bộ; luồng đọc ghép thành khung → on_au."""
    def __init__(self, ff, cap, enc, sw, sh, w, h, fps, kbps, on_au, log=None):
        self.helper = ff                                           # LinuxRemote.ff = Helper (vị trí đường dẫn ffmpeg bên Windows)
        self.cap, self.enc, self.sw, self.sh, self.w, self.h, self.fps, self.kbps = cap, enc, sw, sh, w, h, fps, kbps
        self.on_au, self.log = on_au, log or (lambda m: None)
        self.sock = None; self.alive = False; self.stopped = False; self.frames = 0; self.t0 = 0.0; self.t_frame = 0.0; self.err = ""; self.pid = None; self.failed = False
        self.proc = self                                           # pcremote / bộ thử đọc enc.proc.poll()

    def poll(self): return 0 if self.exited() else None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError: pass
        self.sock.bind(("127.0.0.1", 0)); self.sock.settimeout(0.5)
        self.t0 = self.t_frame = time.time(); self.alive = True
        try:
            r = self.helper.request("start", START_WAIT, w=self.w, h=self.h, fps=self.fps, kbps=self.kbps, port=self.sock.getsockname()[1],
                                    enc=x264_linux(R.enc_args("x264", self.fps, self.kbps)))
            self.pid = r.get("pid"); self.helper.cur_pid = self.pid
            if r.get("backend"): self.cap = str(r["backend"])[:16]           # thông số người xem: "kwin" / "portal"
        except Exception as e:
            self.err = str(e)[:300]; self.failed = True
            self.log("bo quay (%s): %s" % (self.cap, self.err)); note_error("bo quay: " + self.err)
            return
        threading.Thread(target=self._rtp, daemon=True).start()

    def _rtp(self):
        asm = R.RtpAssembler(); sock = self.sock
        while self.alive:
            try: pkt, addr = sock.recvfrom(65536)
            except socket.timeout:
                if self.exited(): break
                continue
            except OSError: break
            if addr[0] != "127.0.0.1": continue
            r = asm.feed(pkt)
            if r is None: continue
            if r[0] is not None: self.frames += 1; self.t_frame = time.time()
            try: self.on_au(r[0], r[1], r[2], int(time.monotonic() * 1e6))
            except Exception: pass

    def exited(self):
        if self.failed: return True
        h = self.helper
        return (not h.alive()) or (self.pid is not None and h.dead_pid == self.pid)

    def stop(self):
        self.stopped = True; self.alive = False
        if not self.failed: self.helper.send("stop")
        try:
            if self.sock: self.sock.close()
        except OSError: pass


class LinuxRemote(R.Remote):
    def prepare(self):
        """Không tải ffmpeg như Windows: kiểm máy có đủ GStreamer (cbcap.have_tools) — có thì nén bằng x264 (CPU)."""
        with self.prep_lock:
            try:
                if not self.ff: self.ff = self.ff_fn()
                if self.caps.get("enc") and time.time() - self.caps_t < 6 * 3600: return True
                import cbcap
                ok, why = cbcap.have_tools()
                self.caps = {"enc": ["x264"] if ok else [], "cap": "portal"}; self.caps_t = time.time()
                self.log("may nay: quay man hinh qua cong XDG cua KDE, nen x264 (CPU) - GStreamer: %s" % why)
                if not ok: self.state = "thieu cong cu quay man hinh (%s) - agent dang tu cai, xong tu chay" % why
                return ok
            except Exception as e:
                self.log("chuan bi bo quay loi: %r" % (e,)); return False


def x264_linux(args, cpus=None):
    """Máy Linux không dùng card đồ hoạ → luôn nén x264 bằng CPU: chia lát (sliced-threads, không thêm trễ) cho 2–4 luồng thay vì 1 luồng
       của bản Windows (ở Windows x264 chỉ là đường phụ) — 1 luồng nén 1280x800 30 khung/giây không kịp → hình trễ dần."""
    n = max(2, min(4, (cpus or os.cpu_count() or 2) // 2))
    out = [str(a) for a in args]
    for i, a in enumerate(out[:-1]):
        if a == "-threads": out[i + 1] = str(n)
        elif a == "-x264-params": out[i + 1] = out[i + 1].replace("sliced-threads=0", "sliced-threads=1")
    return out


# ====================================================================================== chuột ảo giữ con trỏ hiện
UINPUT = "/dev/uinput"
_PTR = []                                                        # giữ fd thiết bị (đóng = thiết bị biến mất)


def dummy_pointer(log=lambda m: None, path=None):
    """Máy cho thuê thường KHÔNG cắm chuột → KWin (Wayland) ẩn hẳn con trỏ (không có thiết bị trỏ) → người xem không thấy chuột ở đâu.
       Tạo 1 chuột ảo (uinput, không bao giờ gửi gì) để KWin luôn coi là có chuột → con trỏ hiện + vẽ vào hình. Lỗi → thôi (không ảnh hưởng gì khác).
       → True khi đã có thiết bị."""
    if _PTR: return True
    import struct
    UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT, UI_DEV_SETUP, UI_DEV_CREATE = 0x40045564, 0x40045565, 0x40045566, 0x405c5503, 0x5501
    fd = None
    try:
        fd = os.open(path or UINPUT, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        fcntl.ioctl(fd, UI_SET_EVBIT, 1)                         # EV_KEY: nút chuột
        for b in (0x110, 0x111, 0x112): fcntl.ioctl(fd, UI_SET_KEYBIT, b)
        fcntl.ioctl(fd, UI_SET_EVBIT, 2)                         # EV_REL: REL_X, REL_Y, REL_WHEEL
        for r in (0, 1, 8): fcntl.ioctl(fd, UI_SET_RELBIT, r)
        fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("HHHH80sI", 0x06, 0x0cb1, 0x0001, 1, b"CloudBlue Remote Pointer", 0))
        fcntl.ioctl(fd, UI_DEV_CREATE)
        _PTR.append(fd)
        log("da tao chuot ao (uinput) de KWin luon hien con tro")
        return True
    except OSError as e:
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
        log("chua tao duoc chuot ao (uinput): %s" % (e,))
        return False


# ====================================================================================== chạy thật
def make_logger(base=BASE):
    return R.make_logger(base, "remote.log")


def cmd_run(argv):
    log = make_logger()
    try:
        lk = open(LOCK, "w"); fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0                                                # đã có 1 bản đang chạy
    cfg = _load_json(os.path.join(BASE, "cb.json")) or {}
    if cfg.get("remote") is False:
        log("cb.json dat remote = false -> khong chay dieu khien tu xa"); return 0
    seed = _load_json(os.path.join(BASE, "seed.json")) or {}
    user = seed.get("user") or C.linux_user(cfg.get("user") or "PC")
    import pcagent                                              # dùng chung phần gọi web (khoá công khai)
    import cbagent
    net = pcagent.Net(cfg, BASE)
    cafile = os.path.join(BASE, "os", "cacert.pem")

    def ident():
        j = _load_json(os.path.join(BASE, "identity.json")) or {}
        return j if j.get("id") and j.get("token") else None
    io = LinuxIO(user, log, cbagent.LinuxHost(user))
    R.Encoder = CapEncoder                                       # phiên người xem của pcremote dùng bộ quay của Linux
    rm = LinuxRemote(ident, net.rpc, io, lambda: io.helper, log, cafile if os.path.isfile(cafile) else None)
    io.on_backend = lambda b: rm.caps.__setitem__("cap", b or "portal")
    log("=== CloudBlue PC dieu khien tu xa (CachyOS) %s / pcremote %s chay - khach %s ===" % (LINUX_REMOTE_VER, R.REMOTE_VER, user))
    dummy_pointer(log)
    ensure_kwin_env(log)
    if kwin_env_ok(user) is False: log("KWin dang chay chua co quyen quay man hinh truc tiep -> can khoi dong lai may 1 lan (tam dung cong XDG)")

    def prep():
        """22.11g: cấp quyền KWin cho cbcap-py + làm mới ksycoca NGAY khi khách đăng nhập (không đợi người xem đầu tiên).
           23.11a: + lối tắt app trên màn hình nền (1 lần)."""
        for _ in range(120):
            try:
                if (user_session(user)[1] or {}).get("XDG_SESSION_TYPE") == "x11": return    # 27.11a: phiên X11 (máy ảo XFCE) — không có KWin
                py, changed = install_kwin_access(log)
                if refresh_sycoca(user, log, force=changed) or _KW["kwin"] is not None:    # 23.11a: luôn dựng lại ĐÚNG (sửa bộ đệm rỗng của bản cũ)
                    desktop_shortcuts(user, log)
                    return
            except Exception as e:
                log("chuan bi quyen KWin loi: %r" % (e,))
            time.sleep(15)
    threading.Thread(target=prep, name="kwin-prep", daemon=True).start()
    files = [os.path.abspath(__file__), CAP_SRC, os.path.abspath(R.__file__)]

    def stamp():
        out = []
        for f in files:
            try: out.append((os.path.getmtime(f), os.path.getsize(f)))
            except OSError: out.append(None)
        return out
    st0 = stamp(); last = ["", 0.0]

    def watch():
        """Thoát khi chương trình vừa được cập nhật (đang không có người xem) → cbagent mở lại bản mới. Ghi trạng thái cho cbagent báo web."""
        while True:
            time.sleep(5)
            try:
                if rm.sess is None and stamp() != st0:
                    log("chuong trinh vua duoc cap nhat -> thoat de chay ban moi"); os._exit(0)
                if rm.state != last[0] or time.time() - last[1] > 60:
                    last[0], last[1] = rm.state, time.time()
                    kw = kwin_env_ok(user)                      # 22.11h: web / SQL thấy KWin đã có quyền mới chưa (chưa → máy cần khởi động lại 1 lần)
                    note = "" if kw is None else " | kwin ok" if kw else " | kwin chua co quyen - can khoi dong lai"
                    with open(os.path.join(BASE, "logs", "remote.state"), "w", encoding="utf-8") as f: f.write("%d %s %s%s\n" % (time.time(), R.REMOTE_VER, rm.state, note))
            except Exception:
                pass
    threading.Thread(target=watch, daemon=True).start()
    rm.run()
    return 0


def cmd_selfcheck(argv):
    import cbcap
    assert cbcap.VK2EV[0x41] == 30 and cbcap.VK2EV[0x0D] == 28 and cbcap.US["A"] == (30, 1)
    assert "x264enc" in cbcap.gst_pipeline(7, 1280, 720, 30, 2000, 5000)
    e = CapEncoder(Helper("nobody"), "portal", "x264", 1920, 1080, 1280, 720, 30, 2000, lambda *a: None)
    assert e.exited() and LinuxRemote and R.Remote
    print("selfcheck ok cbremote %s / pcremote %s" % (LINUX_REMOTE_VER, R.REMOTE_VER))
    return 0


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "version": print(LINUX_REMOTE_VER); return 0
    fn = {"run": cmd_run, "selfcheck": cmd_selfcheck}.get(cmd)
    if not fn: print("cbremote %s: run | selfcheck | version" % LINUX_REMOTE_VER); return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
