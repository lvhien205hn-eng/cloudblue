# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbremote.py — CloudBlue PC (CachyOS): ĐIỀU KHIỂN TỪ XA, chạy bằng ROOT (cbagent mở + giữ chạy, như pcagent mở pcremote trên Windows).
#  Dùng NGUYÊN giao thức / trạm phát hình của pcremote.py (nối ra máy chủ, phiên người xem, nén theo mạng, chuột / phím / bộ nhớ copy) — chỉ
#  thay phần đụng hệ điều hành:
#    · quay màn hình + bơm chuột / phím: cbcap.py chạy BẰNG TÀI KHOẢN KHÁCH trong phiên KDE (Wayland) qua cổng XDG RemoteDesktop đã cấp
#      quyền sẵn (không hộp hỏi) → GStreamer x264 (CPU, không cần card hình) → RTP về cổng UDP nội bộ của chương trình này
#    · cbcap.py không giữ bí mật nào: mã máy / mã riêng chỉ chương trình root này đọc (/opt/cloudblue, 0700)
#  Lệnh:  cbremote.py run | selfcheck | version          Nhật ký: /opt/cloudblue/logs/remote.log
# =====================================================================================================
import fcntl, grp, json, os, pwd, re, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("CB_BASE") or os.path.abspath(os.path.join(HERE, ".."))          # /opt/cloudblue
for _p in (os.path.join(BASE, "lib"), os.path.join(BASE, "agent"), HERE):
    if _p not in sys.path: sys.path.insert(0, _p)

import cbcore as C                                               # noqa: E402
import pcremote as R                                             # noqa: E402

LINUX_REMOTE_VER = "22.11f"
CAP_SRC = os.path.join(HERE, "cbcap.py")
CAP_DIR = "/usr/local/lib/cloudblue"                             # bản cbcap.py tài khoản khách đọc được (root sở hữu, khách không sửa được)
LOCK = "/run/cloudblue-remote.lock"
SIZE_TTL = 15.0


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
    if not os.path.exists(os.path.join(rt, "bus")): return pw, None
    way = sorted(f for f in (os.listdir(rt) if os.path.isdir(rt) else []) if re.fullmatch(r"wayland-\d+", f))
    if not way: return pw, None
    env = {"HOME": pw.pw_dir, "USER": user, "LOGNAME": user, "SHELL": pw.pw_shell or "/bin/bash", "PATH": "/usr/local/bin:/usr/bin:/bin",
           "LANG": os.environ.get("LANG") or "C.UTF-8", "XDG_RUNTIME_DIR": rt, "DBUS_SESSION_BUS_ADDRESS": "unix:path=%s/bus" % rt,
           "WAYLAND_DISPLAY": way[0], "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}
    return pw, env


def install_cap():
    """Chép cbcap.py sang chỗ tài khoản khách đọc được (chỉ khi khác bản đang có)."""
    os.makedirs(CAP_DIR, mode=0o755, exist_ok=True)
    dst = os.path.join(CAP_DIR, "cbcap.py")
    with open(CAP_SRC, "rb") as f: data = f.read()
    try:
        with open(dst, "rb") as f:
            if f.read() == data: return dst
    except OSError: pass
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f: f.write(data)
    os.chmod(tmp, 0o644); os.replace(tmp, dst)
    return dst


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
            mine, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                groups = [g.gr_gid for g in grp.getgrall() if self.user in g.gr_mem]
                self.proc = subprocess.Popen(["/usr/bin/python3", "-I", "-B", script, "serve", "--fd", str(child.fileno())], user=pw.pw_uid, group=pw.pw_gid,
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
class LinuxIO:
    """Thay WinIO của pcremote: mọi việc đụng màn hình / chuột / phím đi qua cbcap.py (tài khoản khách)."""
    def __init__(self, user, log=None, host=None):
        self.user, self.log, self.host = user, log or (lambda m: None), host
        self.helper = Helper(user, self.log)
        self.sz = (1920, 1080); self.sz_t = 0.0; self.clip_seen = None; self.clip_t = 0.0

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
        """Có người xem → mở cbcap + phiên KDE (luồng màn hình); hết người xem → đóng (KDE tắt biểu tượng chia sẻ màn hình)."""
        if on:
            self.helper.ensure()
            self.helper.request("open", 40)
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
            r = self.helper.request("start", 40, w=self.w, h=self.h, fps=self.fps, kbps=self.kbps, port=self.sock.getsockname()[1],
                                    enc=x264_linux(R.enc_args("x264", self.fps, self.kbps)))
            self.pid = r.get("pid"); self.helper.cur_pid = self.pid
        except Exception as e:
            self.err = str(e)[:300]; self.failed = True
            self.log("bo quay (%s): %s" % (self.cap, self.err))
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
    log("=== CloudBlue PC dieu khien tu xa (CachyOS) %s / pcremote %s chay - khach %s ===" % (LINUX_REMOTE_VER, R.REMOTE_VER, user))
    dummy_pointer(log)
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
                    with open(os.path.join(BASE, "logs", "remote.state"), "w", encoding="utf-8") as f: f.write("%d %s %s\n" % (time.time(), R.REMOTE_VER, rm.state))
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
