# -*- coding: utf-8 -*-
"""Thử ĐIỀU KHIỂN TỪ XA bản CachyOS (linux/cbremote.py + linux/cbcap.py) trên máy Linux bất kỳ (không cần KDE):
   · D-Bus tự viết của cbcap: ghép / tách gói, gọi hàm, tín hiệu, nhận fd — trên dbus-daemon THẬT
   · cổng XDG RemoteDesktop GIẢ (giả KDE: chưa cấp quyền sẵn thì "hiện hộp hỏi" = không trả lời) → cbcap cấp quyền rồi mở phiên
   · ĐẦU-CUỐI: máy chủ phát hình thật (windows/bluestream.py --selftest + pcrelay.py, TLS thật) ⇄ cbremote (root) ⇄ cbcap (tiến trình
     riêng, hình thử của ffmpeg thay màn hình KDE) ⇄ người xem: hình tới, giải mã đủ; chuột / phím / chữ tới đúng cổng XDG
   Chạy: python3 tests/test_linux_remote.py   (cần dbus-daemon + ffmpeg + thư viện cryptography)"""
import hashlib, json, os, shutil, socket, ssl, struct, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
WINPC = os.path.join(HERE, "..")
for p in ("lib", "agent", "linux", os.path.join("tests", "remote")): sys.path.insert(0, os.path.join(WINPC, p))
import cbcap as K                                     # noqa: E402
import pcremote as R                                  # noqa: E402
from paths import SRV                                 # noqa: E402

OK = FAIL = 0
C_HELLO, C_BYE, S_WELCOME = 0x01, 0x19, 0x81
PC = "22222222-2222-4222-8222-222222222222"


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def wait(fn, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(step)
    return fn()


class View:
    """Người xem (như app / web): nối TLS + kiểm mã chứng chỉ tới trạm, gom gói nhận được, ACK từng khung."""
    def __init__(self, conn, hello):
        self.c = conn; self.rx = []; self.lock = threading.Lock(); self.alive = True
        conn.send(C_HELLO, json.dumps(hello).encode())
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._ping, daemon=True).start()

    def _loop(self):
        try:
            while True:
                t, p = self.c.recv()
                if t == R.S_PONG: continue
                if t == R.S_VIDEO: self.c.send(R.C_ACK, p[1:9])
                with self.lock: self.rx.append((t, p))
        except Exception:
            self.alive = False

    def _ping(self):
        while self.alive:
            try: self.c.send(R.C_PING, struct.pack(">Q", int(time.time() * 1000)))
            except Exception: return
            time.sleep(2)

    def take(self, t, timeout=10.0):
        def f():
            with self.lock:
                for i, m in enumerate(self.rx):
                    if m[0] == t: return self.rx.pop(i)
            return None
        return wait(f, timeout)

    def count(self, t):
        with self.lock: return sum(1 for m in self.rx if m[0] == t)

    def frames(self):
        with self.lock: return [m[1] for m in self.rx if m[0] == R.S_VIDEO]


if not shutil.which("dbus-daemon") or not shutil.which("ffmpeg"):
    print("(bỏ qua: máy thử thiếu dbus-daemon / ffmpeg)"); sys.exit(0)
tmp = tempfile.mkdtemp(prefix="cblr-")

print("1. D-Bus tự viết: ghép / tách gói")
for sig, args in (("a(ua{sv})", [[(42, {"size": ("(ii)", (1920, 1080)), "source_type": ("u", 1)})]]), ("oa{sv}udd", ["/a/b", {"x": ("s", "y")}, 7, 1.5, 2.25]),
                  ("sbssas", ["kde-authorized", True, "remote-desktop", "", ["yes"]]), ("ua{sv}", [0, {"streams": ("a(ua{sv})", [(5, {"size": ("(ii)", (800, 600))})])}]),
                  ("ayaxa(yv)", [[1, 2], [-1, 2 ** 40], []]), ("vv", [("s", "chữ có dấu"), ("ad", [1.5, -2.0])])):
    data, _ = K.build(1, 3, {1: ("o", "/p"), 3: ("s", "M")}, sig, args)
    m, n = K.parse(data)
    want = [[(42, {"size": (1920, 1080), "source_type": 1})]] if sig == "a(ua{sv})" else None
    ck("kiểu %s: tách lại đúng" % sig, n == len(data) and (m["body"] == want if want else len(m["body"]) == len(K.split_sig(sig))), m["body"])
m, n = K.parse(K.build(1, 3, {}, "s", ["x" * 50])[0][:20])
ck("gói chưa đủ byte → chờ thêm (không hỏng)", m is None and n == 0)

print("2. Cổng XDG giả (như KDE) trên dbus-daemon thật")
addr_f = os.path.join(tmp, "addr")
dbusd = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1", "--nopidfile"], stdout=subprocess.PIPE)
ADDR = dbusd.stdout.readline().decode().strip()
ck("dbus-daemon chạy", ADDR.startswith("unix:"), ADDR)
EV = []; AUTH = {}; STATE = {"inhibit": 0}


def portal_service():
    srv = K.DBus(ADDR)
    for nm in ("org.freedesktop.portal.Desktop", "org.freedesktop.impl.portal.PermissionStore", "org.freedesktop.ScreenSaver", "org.freedesktop.PowerManagement"):
        srv.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName", "su", [nm, 4])
    apps = {}

    def reply(m, sig="", args=()):
        srv.send(2, {5: ("u", m["serial"]), 6: ("s", m["sender"])}, sig, args)

    def respond(m, results, never=False):
        tok = m["body"][-1]["handle_token"]
        path = "/org/freedesktop/portal/desktop/request/%s/%s" % (m["sender"].lstrip(":").replace(".", "_"), tok)
        reply(m, "o", [path])
        if not never: srv.send(4, {1: ("o", path), 2: ("s", "org.freedesktop.portal.Request"), 3: ("s", "Response")}, "ua{sv}", [0, results])
    while True:
        try: m = srv.take(lambda m: m["type"] == 1, 3600)
        except Exception: return
        mem, body = m["member"], m["body"]
        if mem == "Register": apps[m["sender"]] = body[0]; reply(m)
        elif mem == "SetPermission": AUTH[(body[0], body[2], body[3])] = body[4]; reply(m)
        elif mem == "Get": reply(m, "v", [("u", 7)])
        elif mem == "CreateSession": respond(m, {"session_handle": ("s", "/org/freedesktop/portal/desktop/session/1/cb")})
        elif mem in ("SelectDevices", "SelectSources"): EV.append((mem, {k: v for k, v in body[1].items() if k != "handle_token"})); respond(m, {})
        elif mem == "Start":
            ok = AUTH.get(("kde-authorized", "remote-desktop", apps.get(m["sender"], ""))) == ["yes"]
            EV.append(("Start", ok))
            respond(m, {"devices": ("u", 3), "streams": ("a(ua{sv})", [(42, {"size": ("(ii)", (1600, 900)), "source_type": ("u", 1)})])}, never=not ok)
        elif mem == "OpenPipeWireRemote":
            r, w = os.pipe(); os.close(w); reply(m, "h", [r]); os.close(r); EV.append(("pw",))
        elif mem.startswith("Notify"): EV.append((mem,) + tuple(body[2:]))
        elif mem == "Inhibit": STATE["inhibit"] += 1; reply(m, "u", [STATE["inhibit"]])
        elif mem == "UnInhibit": STATE["inhibit"] -= 1; reply(m)
        elif mem == "Close": EV.append(("Close", m["path"])); reply(m)
        else: srv.send(3, {4: ("s", "org.freedesktop.DBus.Error.UnknownMethod"), 5: ("u", m["serial"]), 6: ("s", m["sender"])}, "s", [mem])


threading.Thread(target=portal_service, daemon=True).start()
time.sleep(0.3)
b = K.DBus(ADDR)
p = K.Portal(b)
try: p._request(K.RD, "CreateSession", "a{sv}", [], {"session_handle_token": ("s", "x")}, timeout=3); s1 = True
except Exception as e: s1 = repr(e)
ck("gọi cổng XDG + chờ tín hiệu Response đúng đường dẫn yêu cầu", s1 is True, s1)
p2 = K.Portal(K.DBus(ADDR))
try: p2.start(timeout=2); st = "mo duoc"
except K.PortalError as e: st = str(e)
ck("CHƯA cấp quyền sẵn → KDE 'hiện hộp hỏi' (không trả lời) → báo rõ, không treo", "chua tra loi" in st, st)
app = p.authorize()
ck("cấp quyền sẵn: đăng ký mã ứng dụng vn.cloudblue.remote + bảng kde-authorized/remote-desktop = yes", app == K.APP_ID
   and AUTH.get(("kde-authorized", "remote-desktop", K.APP_ID)) == ["yes"], (app, AUTH))
node, size = p.start(timeout=5)
ck("mở phiên: luồng màn hình 42 (1600x900), chọn 1 màn hình + con trỏ vẽ sẵn + bàn phím/chuột", (node, size) == (42, (1600, 900))
   and ("SelectSources", {"types": 1, "multiple": False, "cursor_mode": 2}) in EV and ("SelectDevices", {"types": 3}) in EV, (node, size, EV[-4:]))
ck("đang có người xem: chặn KDE khoá / tắt màn hình (ScreenSaver + PowerManagement)", STATE["inhibit"] == 2, STATE)
fd = p.pw_fd()
ck("OpenPipeWireRemote trả fd thật (qua SCM_RIGHTS)", isinstance(fd, int) and fd > 2 and os.read(fd, 10) == b"", fd); os.close(fd)

print("3. Chuột / phím → cổng XDG (mã Linux)")
cap = K.Cap(); cap.portal = cap.inp = p; cap.bus = b; cap.backend = "portal"
del EV[:]
cap.move(32768, 16384); cap.btn(0, True); cap.btn(0, False); cap.btn(1, True); cap.wheel(240, False); cap.wheel(-60, False); cap.wheel(-60, False)
cap.key(0x0D, True); cap.key(0x0D, False); cap.key(0x0D, True, True); cap.key(0x41, True); cap.key(0x70, True); cap.key(0xA2, True)
cap.text("Hi!"); cap.text("ă")
want = [("NotifyPointerMotionAbsolute", 42, 800.0, 225.0), ("NotifyPointerButton", 0x110, 1), ("NotifyPointerButton", 0x110, 0), ("NotifyPointerButton", 0x111, 1),
        ("NotifyPointerAxisDiscrete", 0, -2), ("NotifyPointerAxisDiscrete", 0, 1), ("NotifyKeyboardKeycode", 28, 1), ("NotifyKeyboardKeycode", 28, 0),
        ("NotifyKeyboardKeycode", 96, 1), ("NotifyKeyboardKeycode", 30, 1), ("NotifyKeyboardKeycode", 59, 1), ("NotifyKeyboardKeycode", 29, 1),
        ("NotifyKeyboardKeycode", 42, 1), ("NotifyKeyboardKeycode", 35, 1), ("NotifyKeyboardKeycode", 35, 0), ("NotifyKeyboardKeycode", 42, 0),
        ("NotifyKeyboardKeycode", 23, 1), ("NotifyKeyboardKeycode", 23, 0), ("NotifyKeyboardKeycode", 42, 1), ("NotifyKeyboardKeycode", 2, 1),
        ("NotifyKeyboardKeycode", 2, 0), ("NotifyKeyboardKeycode", 42, 0)]
ck("rê (toạ độ 0..65535 → điểm ảnh của luồng) · nút trái/phải · lăn (2 nấc lên, cộng dồn nửa nấc) · Enter / Enter số / A / F1 / Ctrl · gõ 'Hi!'",
   wait(lambda: EV[:len(want)] == want, 3), EV[:len(want)])
ck("chữ có dấu (máy không có wl-copy) → gửi keysym Unicode", wait(lambda: ("NotifyKeyboardKeysym", 0x01000103, 1) in EV, 3), EV[len(want):])
p.close()
ck("đóng phiên: Session.Close + bỏ chặn khoá màn hình", wait(lambda: any(e[0] == "Close" for e in EV), 3) and wait(lambda: STATE["inhibit"] == 0, 3), (EV[-2:], STATE))

print("3b. Dò công cụ quay màn hình: đủ thì nhớ, THIẾU thì dò lại sau 60 giây (agent đang tự cài gst-plugin-pipewire)")
_run, _ts = K.subprocess.run, K.TEST_SRC
HAVE = {"pipewiresrc": False}; NRUN = [0]
class _R:
    def __init__(self, rc, out=b""): self.returncode, self.stdout = rc, out
def _fake_run(argv, **kw):
    NRUN[0] += 1
    if argv[0] == "gst-inspect-1.0": return _R(0 if HAVE.get(argv[-1], argv[-1] not in ("x264enc",)) else 1)
    if argv[0] == "ffmpeg": return _R(0, b" V....D libx264  libx264 H.264 / AVC\n")
    return _R(1)
K.subprocess.run = _fake_run; K.TEST_SRC = False; K._TOOLS.clear(); K._TOOLS_T[0] = 0.0
ok1, why1 = K.have_tools()
ck("thiếu pipewiresrc → chưa quay được; chỉ báo phần CẦN (không kể x264enc — đường chính dùng ffmpeg)", not ok1 and why1 == "thieu pipewiresrc", why1)
n1 = NRUN[0]; K.have_tools()
ck("trong 60 giây không dò lại", NRUN[0] == n1)
HAVE["pipewiresrc"] = True; K._TOOLS_T[0] -= K.TOOLS_RETRY_S + 1
ok2, why2 = K.have_tools()
ck("agent cài xong → lần dò sau thấy đủ (không phải chạy lại chương trình)", ok2 and K.pick_mode() == "ff", why2)
n2 = NRUN[0]; K._TOOLS_T[0] -= 3600; K.have_tools()
ck("đủ rồi thì nhớ luôn, không dò nữa", NRUN[0] == n2)
K.subprocess.run, K.TEST_SRC = _run, _ts; K._TOOLS.clear(); K._TOOLS_T[0] = 0.0

print("3c. 22.11g — KWin trực tiếp (zkde_screencast + fake_input) trên máy chủ Wayland GIẢ: không qua cổng XDG → không hộp hỏi")


class FakeKWin:
    """Máy chủ Wayland giả như KWin: registry (wl_output · zxdg_output_manager_v1 · zkde_screencast_unstable_v1 · org_kde_kwin_fake_input — 2 cái
       sau CHỈ khi allow, như KWin giấu giao diện hạn chế với chương trình không có tệp .desktop), stream_output → created(node) | failed."""
    def __init__(self, path, allow=True, fail=None, outputs=None, fi_ver=6):
        self.path, self.allow, self.fail, self.fi_ver = path, allow, fail, fi_ver
        self.outputs = outputs or [{"name": "HDMI-A-1", "x": 0, "y": 0, "w": 1920, "h": 1080, "scale": 2, "lx": 0, "ly": 0, "lw": 1280, "lh": 720}]
        self.ev = []; self.conns = 0
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.srv.bind(path); self.srv.listen(8)
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try: c, _ = self.srv.accept()
            except OSError: return
            self.conns += 1
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    @staticmethod
    def _msg(obj, op, payload=b""):
        return struct.pack("<II", obj, ((8 + len(payload)) << 16) | op) + payload

    def _serve(self, c):
        ids = {1: "wl_display"}; out_of = {}; buf = b""
        names = {}
        n = 0
        for o in self.outputs: n += 1; names[n] = ("wl_output", 4, o)
        n += 1; names[n] = ("zxdg_output_manager_v1", 3, None)
        if self.allow:
            n += 1; names[n] = ("zkde_screencast_unstable_v1", 6, None)
            n += 1; names[n] = ("org_kde_kwin_fake_input", self.fi_ver, None)
        S = K._wl_str
        try:
            while True:
                d = c.recv(65536)
                if not d: return
                buf += d
                while len(buf) >= 8:
                    obj, so = struct.unpack_from("<II", buf, 0); size, op = so >> 16, so & 0xFFFF
                    if len(buf) < size: break
                    p, buf = buf[8:size], buf[size:]
                    it = ids.get(obj)
                    if it == "wl_display" and op == 1:                               # get_registry
                        rid = struct.unpack_from("<I", p, 0)[0]; ids[rid] = "wl_registry"
                        for nm, (iface, ver, _) in names.items(): c.sendall(self._msg(rid, 0, struct.pack("<I", nm) + S(iface) + struct.pack("<I", ver)))
                    elif it == "wl_display" and op == 0:                             # sync
                        c.sendall(self._msg(struct.unpack_from("<I", p, 0)[0], 0, struct.pack("<I", 0)))
                    elif it == "wl_registry" and op == 0:                            # bind(name, iface, ver, id)
                        nm = struct.unpack_from("<I", p, 0)[0]; iface, pos = K._wl_rstr(p, 4); ver, nid = struct.unpack_from("<II", p, pos)
                        ids[nid] = iface; self.ev.append(("bind", iface, ver))
                        if iface == "wl_output":
                            o = names[nm][2]; out_of[nid] = o
                            c.sendall(self._msg(nid, 0, struct.pack("<iiiii", o["x"], o["y"], 600, 340, 0) + S("Ha") + S("Hb") + struct.pack("<i", 0)))
                            c.sendall(self._msg(nid, 1, struct.pack("<Iiii", 0, 1280, 720, 60000)))               # chế độ KHÔNG phải hiện tại
                            c.sendall(self._msg(nid, 1, struct.pack("<Iiii", 3, o["w"], o["h"], 60000)))          # chế độ hiện tại (cờ 1)
                            c.sendall(self._msg(nid, 3, struct.pack("<i", o["scale"])))
                            if ver >= 4: c.sendall(self._msg(nid, 4, S(o["name"])))
                            c.sendall(self._msg(nid, 2))
                    elif it == "zxdg_output_manager_v1" and op == 1:                 # get_xdg_output(id, output)
                        xid, oid = struct.unpack_from("<II", p, 0); o = out_of[oid]; ids[xid] = "zxdg_output_v1"
                        c.sendall(self._msg(xid, 0, struct.pack("<ii", o["lx"], o["ly"]))); c.sendall(self._msg(xid, 1, struct.pack("<ii", o["lw"], o["lh"])))
                    elif it == "zkde_screencast_unstable_v1" and op == 0:            # stream_output(stream, output, pointer)
                        sid, oid, ptr = struct.unpack_from("<III", p, 0); ids[sid] = "stream"
                        self.ev.append(("stream_output", out_of[oid]["name"], ptr))
                        if self.fail: c.sendall(self._msg(sid, 2, S(self.fail)))
                        else: c.sendall(self._msg(sid, 1, struct.pack("<I", 77)))
                    elif it == "stream" and op == 0: self.ev.append(("stream_close",))
                    elif it == "org_kde_kwin_fake_input":
                        if op == 0: self.ev.append(("authenticate", K._wl_rstr(p, 0)[0]))
                        elif op == 9: self.ev.append(("abs",) + tuple(v / 256.0 for v in struct.unpack_from("<ii", p, 0)))
                        elif op == 2: self.ev.append(("button",) + struct.unpack_from("<II", p, 0))
                        elif op == 3: self.ev.append(("axis", struct.unpack_from("<I", p, 0)[0], struct.unpack_from("<i", p, 4)[0] / 256.0))
                        elif op == 10: self.ev.append(("key",) + struct.unpack_from("<II", p, 0))
                        elif op == 12: self.ev.append(("keysym",) + struct.unpack_from("<II", p, 0))
                        elif op == 11: self.ev.append(("fi_destroy",))
        except OSError:
            return

    def close(self):
        try: self.srv.close()
        except OSError: pass


wdir = os.path.join(tmp, "wl"); os.makedirs(wdir)
kw1 = FakeKWin(os.path.join(wdir, "kwin-ok"))
os.environ["WAYLAND_DISPLAY"] = kw1.path
kc = K.KWinCast()
node, size = kc.start(pointer=1)
ck("KWin cho phép → luồng màn hình 77, cỡ THẬT 1920x1080 (chế độ hiện tại), vùng logic 1280x720 (phóng 150 %: zxdg_output), tên HDMI-A-1",
   (node, size, kc.geo, kc.out, kc.outs) == (77, (1920, 1080), (0, 0, 1280, 720), "HDMI-A-1", 1), (node, size, kc.geo, kc.out))
ck("fake_input v6 + authenticate 'CloudBlue' (KWin tự cho, không hộp hỏi) · stream_output ẩn con trỏ (FramePump tự vẽ) · zkde bản ≤ 5",
   ("authenticate", "CloudBlue") in kw1.ev and ("stream_output", "HDMI-A-1", 1) in kw1.ev and ("bind", "zkde_screencast_unstable_v1", 5) in kw1.ev
   and ("bind", "org_kde_kwin_fake_input", 6) in kw1.ev, kw1.ev)
del kw1.ev[:]
cap = K.Cap(); cap.kw = cap.inp = kc; cap.node, cap.size, cap.backend = kc.node, kc.size, "kwin"
cap.move(32768, 16384); cap.btn(0, True); cap.btn(0, False); cap.wheel(240, False); cap.key(0x0D, True); cap.text("Hi"); cap.text("ă")
want = [("abs", 640.0, 180.0), ("button", 0x110, 1), ("button", 0x110, 0), ("axis", 0, -30.0), ("key", 28, 1),
        ("key", 42, 1), ("key", 35, 1), ("key", 35, 0), ("key", 42, 0), ("key", 23, 1), ("key", 23, 0), ("keysym", 0x01000103, 1), ("keysym", 0x01000103, 0)]
ck("chuột / phím qua fake_input: 0..65535 → toạ độ LOGIC (640, 180) · nút trái · lăn 2 nấc lên (-30) · Enter · gõ 'Hi' · chữ có dấu = keyboard_keysym",
   wait(lambda: kw1.ev[:len(want)] == want, 3), kw1.ev[:len(want)])
kc.close()
ck("đóng: đóng luồng màn hình + bỏ fake_input", wait(lambda: ("stream_close",) in kw1.ev and ("fi_destroy",) in kw1.ev, 3), kw1.ev[-3:])
kw2 = FakeKWin(os.path.join(wdir, "kwin-chua-cho"), allow=False); os.environ["WAYLAND_DISPLAY"] = kw2.path
try: K.KWinCast().start(); e2 = "mo duoc"
except K.WaylandError as e: e2 = str(e)
ck("KWin CHƯA cho (chưa có tệp .desktop) → lỗi nói rõ thiếu gì, không treo", "KWin chua cho" in e2 and "zkde_screencast" in e2 and "fake_input" in e2, e2)
kw3 = FakeKWin(os.path.join(wdir, "kwin-tu-choi"), fail="output gone"); os.environ["WAYLAND_DISPLAY"] = kw3.path
try: K.KWinCast().start(); e3 = "mo duoc"
except K.WaylandError as e: e3 = str(e)
ck("KWin từ chối tạo luồng → báo lý do của KWin", "KWin tu choi quay man hinh: output gone" in e3, e3)
kw4 = FakeKWin(os.path.join(wdir, "kwin-2-man-hinh"), outputs=[
    {"name": "DP-2", "x": 1920, "y": 0, "w": 2560, "h": 1440, "scale": 1, "lx": 1920, "ly": 0, "lw": 2560, "lh": 1440},
    {"name": "HDMI-A-1", "x": 0, "y": 0, "w": 1920, "h": 1080, "scale": 1, "lx": 0, "ly": 0, "lw": 1920, "lh": 1080}])
os.environ["WAYLAND_DISPLAY"] = kw4.path
k4 = K.KWinCast(); k4.start()
ck("2 màn hình → quay màn hình chính ở góc (0, 0) (không phải cái to hơn), chuột theo đúng vùng của nó", (k4.out, k4.outs, k4.geo) == ("HDMI-A-1", 2, (0, 0, 1920, 1080)), (k4.out, k4.geo))
k4.close()
os.environ["WAYLAND_DISPLAY"] = os.path.join(wdir, "khong-co")
try: K.KWinCast().start(); e5 = "mo duoc"
except K.WaylandError as e: e5 = str(e)
ck("không có ổ Wayland (khách chưa đăng nhập) → lỗi ngay", "khong noi duoc KWin" in e5, e5)
print("3d. Cap.open: KWin trước → không được thì cổng XDG (có hạn giờ, ĐÓNG phiên để KDE gỡ hộp hỏi) → cả 2 hỏng: báo đủ lý do")
os.environ["WAYLAND_DISPLAY"] = kw1.path
c1 = K.Cap(bus_addr=ADDR); sz = c1.open()
ck("KWin cho → dùng KWin (không đụng cổng XDG)", c1.backend == "kwin" and sz == (1920, 1080) and c1.portal is None, (c1.backend, sz))
c1.close()
os.environ["WAYLAND_DISPLAY"] = kw2.path
del EV[:]
c2 = K.Cap(bus_addr=ADDR); sz2 = c2.open()
ck("KWin chưa cho → cổng XDG (đã cấp quyền sẵn) → luồng 42 (1600x900)", c2.backend == "portal" and sz2 == (1600, 900) and ("Start", True) in EV, (c2.backend, sz2, EV[:4]))
c2.close()
AUTH.clear()
_ps, _ob = K.PORTAL_START_S, K.OPEN_BUDGET_S
K.PORTAL_START_S = 1.5; K.OPEN_BUDGET_S = 3.0
_reg = K.Portal.authorize
K.Portal.authorize = lambda self, timeout=15.0: setattr(self, "app", "") or ""             # giả: cấp quyền không ăn (như máy 139) → KDE hiện hộp hỏi
del EV[:]
c3 = K.Cap(bus_addr=ADDR); t0 = time.time()
try: c3.open(); e6 = "mo duoc"
except RuntimeError as e: e6 = str(e)
dt = time.time() - t0
K.Portal.authorize = _reg; K.PORTAL_START_S, K.OPEN_BUDGET_S = _ps, _ob
ck("KWin chưa cho + cổng XDG treo (hộp hỏi) → lỗi ghi CẢ 2 lý do, trong hạn giờ (trạm chờ 25 giây)", e6.startswith("KWin:") and "cong XDG:" in e6
   and "chua tra loi" in e6 and dt < 6, (e6, round(dt, 1)))
ck("… rồi ĐÓNG yêu cầu + phiên cổng XDG (KDE gỡ hộp hỏi đang treo trên màn hình máy)", wait(lambda: sum(1 for e in EV if e[0] == "Close") >= 2, 3)
   and c3.portal is None and c3.bus is None, [e for e in EV if e[0] == "Close"])
print("3e. Cấp quyền KWin cho cbcap (root): bản sao python riêng + pyvenv.cfg + tệp .desktop X-KDE-Wayland-Interfaces")
import cbremote as CR                                 # noqa: E402
cd_, ad_ = os.path.join(tmp, "kw-cap"), os.path.join(tmp, "kw-apps"); os.makedirs(ad_)
L3 = []
py1, ch1 = CR.install_kwin_access(L3.append, py=sys.executable, cap_dir=cd_, apps=ad_)
dsk = open(os.path.join(ad_, CR.KWIN_DESKTOP)).read()
r = subprocess.run([py1, "-I", "-B", "-c", "import json, socket; print('ok')"], capture_output=True, timeout=30) if py1 else None
ck("chép python → cbcap-py (chạy được nhờ pyvenv.cfg) + tệp .desktop Exec=cbcap-py, X-KDE-Wayland-Interfaces=zkde_screencast_unstable_v1,org_kde_kwin_fake_input",
   py1 == os.path.join(cd_, "cbcap-py") and ch1 and r is not None and r.stdout.strip() == b"ok" and "Exec=%s\n" % py1 in dsk
   and "X-KDE-Wayland-Interfaces=zkde_screencast_unstable_v1,org_kde_kwin_fake_input\n" in dsk and "NoDisplay=true" in dsk
   and os.stat(py1).st_mode & 0o777 == 0o755, (py1, ch1, dsk, r and r.stderr[-200:]))
py2, ch2 = CR.install_kwin_access(L3.append, py=sys.executable, cap_dir=cd_, apps=ad_)
ck("gọi lại: không đổi gì (tệp .desktop giữ nguyên → không phải làm mới ksycoca)", py2 == py1 and ch2 is False)
bad = os.path.join(tmp, "python-hong"); open(bad, "wb").write(b"#!/bin/sh\nexit 3\n"); os.chmod(bad, 0o755)
py3, ch3 = CR.install_kwin_access(L3.append, py=bad, cap_dir=cd_, apps=ad_)
ck("python chép ra không chạy được → (None): cbcap dùng python thường, đi cổng XDG", py3 is None and any("chua chay duoc" in m for m in L3), L3[-2:])
ck("thư mục không ghi được → (None), không ném lỗi", CR.install_kwin_access(L3.append, py=sys.executable, cap_dir="/proc/khong-ghi-duoc", apps=ad_)[0] is None)
_eb = os.path.join(tmp, "base"); os.makedirs(os.path.join(_eb, "logs"))
CR.note_error("KWin: thieu zkde_screencast; cong XDG: StartTimeout", base=_eb)
_ln = open(os.path.join(_eb, "logs", "remote.err")).read()
ck("ghi lỗi mở màn hình gần nhất (logs/remote.err: giờ + lỗi 1 dòng) cho agent báo lên web", _ln.split(" ", 1)[0].isdigit() and _ln.endswith("cong XDG: StartTimeout\n"), _ln)
print("3f. Mở màn hình lỗi → người xem thấy LÝ DO (S_ERROR) thay vì trạm báo chung chung 'bộ quay màn hình chưa chạy'")


class _Conn:
    def __init__(self): self.sent = []
    def send(self, t, p): self.sent.append((t, p))


class _IO:
    def awake(self, on):
        if on: raise CR.ViewerError("KWin: x; cong XDG: y", "Máy Linux chưa mở được màn hình để quay: KWin: x; cong XDG: y")
    def screen(self): return (1920, 1080)


_rm = CR.LinuxRemote(lambda: {"id": PC, "token": "t"}, lambda fn, body: {}, _IO(), lambda: None, lambda m: None, None)
_rm.ff, _rm.caps = object(), {"enc": ["x264"], "cap": "portal"}
_c = _Conn()
_rm._start(_c, json.dumps({"sid": 1, "q": "eco"}).encode())
_e = [json.loads(p) for t, p in _c.sent if t == R.S_ERROR]
ck("lỗi có lời báo cho người xem → gửi nguyên văn (code OFFLINE), phiên đóng", _e == [{"code": "OFFLINE", "msg": "Máy Linux chưa mở được màn hình để quay: KWin: x; cong XDG: y"}]
   and _rm.sess is None, _c.sent)
_IO.awake = lambda self, on: (_ for _ in ()).throw(RuntimeError("loi la")) if on else None
_c2 = _Conn(); _rm._start(_c2, json.dumps({"sid": 2}).encode())
ck("lỗi thường (máy Windows) → câu báo cũ như trước", [json.loads(p)["msg"] for t, p in _c2.sent if t == R.S_ERROR] == ["Máy PC chưa bật được bộ quay màn hình — thử lại sau ít phút."], _c2.sent)
print("4. ĐẦU-CUỐI: máy chủ phát hình thật ⇄ cbremote (root) ⇄ cbcap (tiến trình riêng) ⇄ người xem")
import pwd                                            # noqa: E402
import cbremote as CR                                 # noqa: E402
print("4b. Nén x264 trên Linux: chia lát 2–4 luồng (không thêm trễ) · GStreamer bỏ khung cũ khi bộ nén chậm (không dồn hình trễ)")
_x = CR.x264_linux(R.enc_args("x264", 30, 2000), cpus=8)
ck("8 nhân → -threads 4 + sliced-threads=1; còn lại giữ như bản Windows", _x[_x.index("-threads") + 1] == "4" and _x[_x.index("-x264-params") + 1].startswith("sliced-threads=1:keyint=30")
   and "-b:v" in _x and "-preset" in _x, _x)
ck("máy 2 nhân → 2 luồng; 32 nhân → tối đa 4", CR.x264_linux(R.enc_args("x264", 30, 2000), cpus=2)[_x.index("-threads") + 1] == "2"
   and CR.x264_linux(R.enc_args("x264", 30, 2000), cpus=32)[_x.index("-threads") + 1] == "4")
_g = " ".join(K.raw_pipeline(58, 1280, 800, 30))
ck("GStreamer: pipewiresrc → hàng chờ bỏ khung cũ → đổi màu/thu cỡ → hàng chờ bỏ khung cũ → fdsink (nhịp đều do FramePump, không videorate)",
   _g.index("pipewiresrc") < _g.index("leaky=downstream") < _g.index("videoconvert") < _g.rindex("leaky=downstream") < _g.index("fdsink") and "videorate" not in _g, _g)
print("4c. Con trỏ tự vẽ + nhịp khung đều (FramePump): KWin không ra khung mới khi chỉ rê chuột → tự vẽ mũi tên, lặp khung mới nhất đều fps")
_W, _H = 64, 48
_b = bytearray(_W * _H * 4); K.draw_cursor(_b, _W, _H, 10, 5)
_px = lambda b, x, y: bytes(b[(y * _W + x) * 4:(y * _W + x) * 4 + 4])
ck("mũi tên: đầu nhọn đúng điểm chuột (viền đen), ruột trắng, ngoài mũi tên không đụng", _px(_b, 10, 5) == b"\x00\x00\x00\xff" and _px(_b, 11, 7) == b"\xff\xff\xff\xff"
   and _px(_b, 9, 5) == b"\x00" * 4 and _px(_b, 30, 30) == b"\x00" * 4)
_b2 = bytearray(_W * _H * 4); K.draw_cursor(_b2, _W, _H, _W - 2, _H - 3); K.draw_cursor(_b2, _W, _H, -5, -5)
ck("sát mép phải / dưới / ngoài khung → cắt bớt, không lỗi, không tràn sang dòng khác", _px(_b2, _W - 2, _H - 3) == b"\x00\x00\x00\xff" and _px(_b2, 0, _H - 2) == b"\x00" * 4 and len(_b2) == _W * _H * 4)
_r, _wfd = os.pipe(); _r2, _w2 = os.pipe()
_src, _dst = os.fdopen(_r, "rb"), os.fdopen(_w2, "wb")
_pos = [None]
_pump = K.FramePump(_src, _dst, _W, _H, 20, lambda: _pos[0])
_rd = os.fdopen(_r2, "rb"); _frames = []
def _rx():
    n = _W * _H * 4
    while True:
        d = _rd.read(n)
        if not d or len(d) < n: return
        _frames.append(d)
threading.Thread(target=_rx, daemon=True).start()
os.write(_wfd, bytes([7]) * (_W * _H * 4)); time.sleep(0.5)
n1 = len(_frames)
ck("màn hình đứng yên (bộ quay chỉ ra 1 khung) → vẫn gửi đều ~20 khung/giây (lặp khung mới nhất)", 6 <= n1 <= 14, n1)
_pos[0] = (20, 10); time.sleep(0.25)
ck("rê chuột (không có khung mới) → khung gửi đi có mũi tên ở chỗ mới ngay", _frames and _px(bytearray(_frames[-1]), 20, 10) == b"\x00\x00\x00\xff" and _px(bytearray(_frames[-1]), 21, 12) == b"\xff\xff\xff\xff", len(_frames))
os.write(_wfd, bytes([9]) * (_W * _H * 4)); time.sleep(0.25)
ck("bộ quay ra khung mới → gửi khung mới (vẫn có mũi tên)", _frames[-1][0] == 9 and _px(bytearray(_frames[-1]), 20, 10) == b"\x00\x00\x00\xff")
os.close(_wfd); time.sleep(0.4)
ck("bộ quay dừng (hết dữ liệu) → FramePump dừng + đóng đầu vào ffmpeg", _pump.stop_ev.is_set() and not any(t.is_alive() for t in _pump.threads), [t.is_alive() for t in _pump.threads])
_rd.close()
_f = K.ff_encode(1280, 800, 30, _x, 5004)
ck("ffmpeg đọc khung thô với hàng chờ nhỏ (-thread_queue_size 2) → không dồn trễ", _f[_f.index("-thread_queue_size") + 1] == "2" and _f.index("-thread_queue_size") < _f.index("-i"), _f)
print("4a. Chuột ảo (uinput) giữ con trỏ KWin luôn hiện trên máy không cắm chuột")
_io = CR.fcntl.ioctl; CALLS = []
CR.fcntl.ioctl = lambda fd, req, arg=0: CALLS.append((req, arg if isinstance(arg, int) else bytes(arg)))
_tmp = tempfile.mkstemp()[1]
ok_ = CR.dummy_pointer(path=_tmp)
ck("tạo thiết bị: nút trái/phải/giữa + REL_X/Y/WHEEL + tên 'CloudBlue Remote Pointer' + UI_DEV_CREATE", ok_ and [c[0] for c in CALLS] == [0x40045564, 0x40045565, 0x40045565, 0x40045565, 0x40045564, 0x40045566, 0x40045566, 0x40045566, 0x405c5503, 0x5501]
   and CALLS[1][1] == 0x110 and CALLS[7][1] == 8 and b"CloudBlue Remote Pointer" in CALLS[8][1] and len(CALLS[8][1]) == 92, CALLS)
n = len(CALLS); ck("gọi lại → không tạo thêm thiết bị", CR.dummy_pointer(path=_tmp) and len(CALLS) == n)
CR.fcntl.ioctl = _io; [os.close(fd) for fd in CR._PTR]; CR._PTR.clear()
L2 = []
ck("không có /dev/uinput (hoặc lỗi) → bỏ qua, ghi nhật ký, không ném lỗi", CR.dummy_pointer(L2.append, path="/khong/co/uinput") is False and any("chuot ao" in m for m in L2))
ck("thiết bị thật không cho ioctl (file thường) → đóng fd, trả False", CR.dummy_pointer(path=_tmp) is False and not CR._PTR)
os.remove(_tmp)
sd = os.path.join(tmp, "srv"); os.makedirs(sd)
for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(SRV, f), os.path.join(sd, f))
port = socket.socket(); port.bind(("127.0.0.1", 0)); PORT = port.getsockname()[1]; port.close()
open(os.path.join(sd, "cloudphone.conf"), "w").write("NODE_ID=lnxtest\nSTREAM_PORT=%d\nSTREAM_WS_PORT=0\nUPNP=0\n" % PORT)
slog = open(os.path.join(sd, "out.log"), "wb")
relay = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=sd, stdout=slog, stderr=subprocess.STDOUT)
rm = None
try:
    up = wait(lambda: relay.poll() is None and not socket.socket().connect_ex(("127.0.0.1", PORT)), 40, 0.3)
    ck("máy chủ phát hình (bluestream --selftest) chạy", up)
    fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(os.path.join(sd, "rtc", "stream-cert.pem")).read())).hexdigest()
    stream = {"direct": [{"host": "127.0.0.1", "port": PORT, "lan": True}], "cert": fp}
    me = pwd.getpwuid(os.getuid())
    env = {"HOME": me.pw_dir, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DBUS_SESSION_BUS_ADDRESS": ADDR, "CBCAP_TEST_SRC": "1",
           "XDG_RUNTIME_DIR": tmp, "WAYLAND_DISPLAY": "wayland-0"}
    CR.user_session = lambda user: (me, dict(env))
    CR.CAP_DIR = os.path.join(tmp, "cap"); CR.APPS_DIR = os.path.join(tmp, "apps"); os.makedirs(CR.APPS_DIR, exist_ok=True)
    logs = []
    io_ = CR.LinuxIO(me.pw_name, logs.append)
    R.Encoder = CR.CapEncoder
    rm = CR.LinuxRemote(lambda: {"id": PC, "token": "tok-l"}, lambda fn, body: {"ok": True, "on": True, "node": "lnxtest", "stream": stream}, io_,
                        lambda: io_.helper, logs.append, None)
    rm.sleep = lambda s: time.sleep(min(s, 0.3))
    os.environ["CBCAP_TEST_SRC"] = "1"; K.TEST_SRC = True
    threading.Thread(target=rm.run, daemon=True).start()
    ck("máy CachyOS (cbremote) vào trạm (R_OK), chờ người xem; chưa mở cbcap", wait(lambda: "cho nguoi xem" in rm.state, 15) and not io_.helper.alive(), (rm.state, logs[-3:]))
    ck("… GStreamer giả (bộ thử) → nén x264", rm.caps.get("enc") == ["x264"] and rm.caps.get("cap") == "portal", rm.caps)
    del EV[:]
    v = View(R.DirectConn("127.0.0.1", PORT, fp, 3.0), {"v": 2, "token": "t", "pc": PC, "client": "web", "ver": "lnx", "q": "eco"})
    m = v.take(S_WELCOME, 40)
    wel = json.loads(m[1]) if m else {}
    ck("người xem nhận WELCOME (kind = pc, cỡ theo Tiết kiệm từ luồng 1600x900 của KDE → 1280x720)", wel.get("ok") is True and wel.get("kind") == "pc"
       and (wel.get("w"), wel.get("h")) == (1280, 720), (wel, logs[-6:]))
    ck("cbcap chạy riêng (tài khoản khách) + mở phiên KDE đã cấp quyền sẵn", io_.helper.alive() and ("Start", True) in EV and ("pw",) in EV, (EV[:6], logs[-4:]))
    ck("hình tới người xem: ≥ 40 khung", wait(lambda: v.count(R.S_VIDEO) >= 40, 20), (v.count(R.S_VIDEO), logs[-5:]))
    fr = v.frames()
    h264 = os.path.join(tmp, "v.h264"); open(h264, "wb").write(b"".join(x[9:] for x in fr))
    rr = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,nb_read_frames,profile",
                         "-of", "json", h264], capture_output=True, timeout=90)
    try: sj = json.loads(rr.stdout)["streams"][0]
    except Exception: sj = {"err": (rr.stderr or b"")[-300:]}
    ck("khung đầu là khung khoá có SPS/PPS; giải mã trọn vẹn đúng số khung, đúng cỡ 1280x720, Constrained Baseline", fr and fr[0][0] & 3 == 3
       and sj.get("width") == 1280 and sj.get("height") == 720 and int(sj.get("nb_read_frames") or 0) == len(fr) and "Baseline" in str(sj.get("profile")), (sj, len(fr)))
    del EV[:]
    v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 16384, 32768)); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 1, 0, 16384, 32768))
    v.c.send(R.C_MOUSE, struct.pack(">BBHH", 2, 0, 16384, 32768))
    v.c.send(R.C_KEY, struct.pack(">BII", 0, 29, 0x1000)); v.c.send(R.C_KEY, struct.pack(">BII", 1, 29, 0x1000))          # Ctrl+A (app gửi kèm meta)
    v.c.send(R.C_TEXT, "ok".encode()); v.c.send(R.C_SCROLL, struct.pack(">HHhh", 100, 100, 0, -120))
    want = [("NotifyPointerMotionAbsolute", 42, 400.0, 450.0), ("NotifyPointerMotionAbsolute", 42, 400.0, 450.0), ("NotifyPointerButton", 0x110, 1),
            ("NotifyPointerMotionAbsolute", 42, 400.0, 450.0), ("NotifyPointerButton", 0x110, 0),
            ("NotifyKeyboardKeycode", 29, 1), ("NotifyKeyboardKeycode", 30, 1), ("NotifyKeyboardKeycode", 30, 0), ("NotifyKeyboardKeycode", 29, 0),
            ("NotifyKeyboardKeycode", 24, 1), ("NotifyKeyboardKeycode", 24, 0), ("NotifyKeyboardKeycode", 37, 1), ("NotifyKeyboardKeycode", 37, 0),
            ("NotifyPointerMotionAbsolute", 42, round(100 * 1600 / 65536.0, 6), round(100 * 900 / 65536.0, 6)), ("NotifyPointerAxisDiscrete", 0, 1)]
    norm = lambda e: tuple(round(x, 6) if isinstance(x, float) else x for x in e)
    ck("người xem bấm chuột / Ctrl+A / gõ chữ / lăn → tới đúng cổng XDG của KDE theo thứ tự (toạ độ theo luồng 1600x900)",
       wait(lambda: [norm(e) for e in EV[:len(want)]] == want, 5), [norm(e) for e in EV[:len(want)]])
    enc = wait(lambda: (rm.sess.enc if rm.sess is not None else None), 3)
    v.c.send(R.C_QUALITY, b'{"q":"bal"}')
    m = v.take(R.S_SIZE, 15)
    ck("đổi chất lượng → cbcap bật lại bộ nén cỡ mới (1600x900 — nén CPU tối đa cạnh 1600), phiên KDE giữ nguyên", m is not None
       and json.loads(m[1]) == {"w": 1600, "h": 900} and wait(lambda: v.count(R.S_VIDEO) > len(fr) + 20, 15), (m, logs[-4:]))
    enc = wait(lambda: (rm.sess.enc if rm.sess is not None else None), 3)
    v.c.send(C_BYE)
    ck("người xem đóng → tắt bộ nén + đóng cbcap + đóng phiên KDE (biểu tượng chia sẻ màn hình tắt)", wait(lambda: rm.sess is None and enc.exited()
       and not io_.helper.alive(), 10) and wait(lambda: any(e[0] == "Close" for e in EV), 5) and wait(lambda: STATE["inhibit"] == 0, 5), (rm.sess, EV[-3:], STATE))
    ck("nhật ký không có lỗi Python", not any("Traceback" in x for x in logs), [x for x in logs if "Traceback" in x][:1])
finally:
    if rm is not None:
        rm.stop = True
        if rm.conn is not None: rm.conn.close()
    relay.kill(); dbusd.kill()
    shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
