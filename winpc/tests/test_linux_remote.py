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
cap = K.Cap(); cap.portal = p; cap.bus = b
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

print("4. ĐẦU-CUỐI: máy chủ phát hình thật ⇄ cbremote (root) ⇄ cbcap (tiến trình riêng) ⇄ người xem")
import pwd                                            # noqa: E402
import cbremote as CR                                 # noqa: E402
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
    CR.CAP_DIR = os.path.join(tmp, "cap")
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
