# -*- coding: utf-8 -*-
"""THỬ ĐẦU-CUỐI điều khiển máy PC:  máy PC thuê (pcremote.py thật, quay hình thử bằng ffmpeg)  ⇄  máy chủ phát hình thật
   (bluestream.py --selftest + pcrelay.py, TLS thật)  ⇄  người xem (nói giao thức BRS2 như app / web).
   Chạy:  python3 winpc/tests/remote/test_e2e.py     (cần ffmpeg + thư viện cryptography; chạy trên Linux / Windows đều được)
"""
import hashlib, json, os, shutil, socket, ssl, struct, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import SRV as SRC, AGENT                                # noqa: E402
sys.path.insert(0, AGENT)
import pcremote as R                                               # noqa: E402

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
OK = FAIL = 0
FF = shutil.which("ffmpeg")
C_HELLO, C_BYE, S_WELCOME, S_ERROR = 0x01, 0x19, 0x81, 0x86
PC = "11111111-1111-4111-8111-111111111111"


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:700])


def wait(fn, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(step)
    return fn()


def cur_enc(r):
    """Bộ nén của phiên đang chạy (đọc 1 lần — luồng của máy PC có thể đổi phiên giữa chừng)."""
    s = r.sess
    return s.enc if s is not None else None


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class View:
    """Người xem: nối như app (TLS + kiểm mã chứng chỉ, hoặc WebSocket nội bộ), gom gói nhận được."""
    def __init__(self, conn, hello):
        self.c = conn; self.rx = []; self.lock = threading.Lock(); self.alive = True; self.t0 = time.time(); self.t_first = None; self.acks = True
        conn.send(C_HELLO, json.dumps(hello).encode())
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._ping, daemon=True).start()

    def _loop(self):
        try:
            while True:
                t, p = self.c.recv()
                if t == R.S_PONG: continue
                if t == R.S_VIDEO:
                    if self.t_first is None: self.t_first = time.time()
                    if self.acks: self.c.send(R.C_ACK, p[1:9])
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


if not FF:
    print("(bỏ qua: máy thử không có ffmpeg)"); sys.exit(0)
tmp = tempfile.mkdtemp(prefix="cbe2e-")
for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(SRC, f), os.path.join(tmp, f))
port, wsport = free_port(), free_port()
open(os.path.join(tmp, "cloudphone.conf"), "w").write(f"NODE_ID=wintest\nSTREAM_PORT={port}\nSTREAM_WS_PORT={wsport}\nUPNP=0\n")
logf = open(os.path.join(tmp, "out.log"), "wb")
proc = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=tmp, stdout=logf, stderr=subprocess.STDOUT)
rm = rm2 = None
try:
    up = False; t0 = time.time()
    while time.time() - t0 < 40 and proc.poll() is None:
        try: socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); up = True; break
        except OSError: time.sleep(0.3)
    ck("máy chủ phát hình (bluestream --selftest + trạm máy PC) chạy", up)
    fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(os.path.join(tmp, "rtc", "stream-cert.pem")).read())).hexdigest()
    stream = {"direct": [{"host": "127.0.0.1", "port": port, "lan": True}], "cert": fp, "ws": None}

    print("1. Máy PC nối ra máy chủ, khách mở điều khiển")
    logs = []; io_ = R.NullIO(1920, 1080)
    rm = R.Remote(lambda: {"id": PC, "token": "tok-1"}, lambda fn, body: {"ok": True, "on": True, "node": "wintest", "stream": stream}, io_, lambda: FF, logs.append, None,
                  caps={"enc": ["x264"], "cap": "test"})
    rm.sleep = lambda s: time.sleep(min(s, 0.3))
    threading.Thread(target=rm.run, daemon=True).start()
    ck("máy PC được trạm nhận (R_OK) → chờ người xem, chưa chạy ffmpeg", wait(lambda: "cho nguoi xem" in rm.state, 8) and rm.sess is None, (rm.state, logs[-3:]))
    v = View(R.DirectConn("127.0.0.1", port, fp, 3.0), {"v": 2, "token": "t", "pc": PC, "client": "web", "ver": "e2e", "q": "eco"})
    m = v.take(S_WELCOME, 15)
    wel = json.loads(m[1]) if m else {}
    ck("khách nhận WELCOME của máy PC: cỡ hình theo chất lượng Tiết kiệm (1280x720), kind = pc", wel.get("ok") is True and (wel.get("w"), wel.get("h")) == (1280, 720) and wel.get("kind") == "pc"
       and wel.get("codec") == "h264" and wel.get("enc") == "x264" and wel.get("android") == "pc", (wel, v.rx[:2], logs[-4:]))
    ck("hình tới khách: ≥ 60 khung", wait(lambda: v.count(R.S_VIDEO) >= 60, 15), v.count(R.S_VIDEO))
    fr = v.frames()
    print("     (từ lúc khách bấm mở tới khung hình đầu: %.2f giây)" % ((v.t_first or time.time()) - v.t0))
    ck("khung đầu là khung khoá có SPS/PPS", fr and fr[0][0] & 3 == 3 and fr[0][9:13] == b"\x00\x00\x00\x01", fr and fr[0][:14])
    h264 = os.path.join(tmp, "v.h264"); open(h264, "wb").write(b"".join(x[9:] for x in fr))
    rr = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,nb_read_frames",
                         "-of", "json", h264], capture_output=True, timeout=90)
    try: sj = json.loads(rr.stdout)["streams"][0]
    except Exception: sj = {"err": (rr.stderr or b"")[-300:]}
    ck("hình khách nhận giải mã được trọn vẹn: đúng số khung, đúng cỡ (qua 2 chặng TLS không hỏng byte nào)", sj.get("codec_name") == "h264" and sj.get("width") == 1280
       and int(sj.get("nb_read_frames") or 0) == len(fr), (sj, len(fr)))
    st = v.take(R.S_STATS, 6); sj = json.loads(st[1]) if st else {}
    ck("số liệu tới khách: ~30 khung/giây, không bỏ khung khi mạng tốt", sj.get("fps", 0) >= 20 and sj.get("drop") == 0 and sj.get("enc") == "x264", sj)

    print("2. Khách điều khiển")
    io_.ev.clear()
    v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 32768, 32768)); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 1, 0, 32768, 32768)); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 2, 0, 32768, 32768))
    v.c.send(R.C_KEY, struct.pack(">BII", 0, 66, 0)); v.c.send(R.C_KEY, struct.pack(">BII", 1, 66, 0)); v.c.send(R.C_TEXT, "Chào máy PC".encode())
    v.c.send(R.C_SCROLL, struct.pack(">HHhh", 100, 100, 0, 240)); v.c.send(R.C_CLIP, b"\x00chu copy")
    v.c.send(0x91, b'{"sid": 99}'); v.c.send(0x92, b"")                          # khách thử giả lệnh của trạm
    want = [("move", 32768, 32768), ("move", 32768, 32768), ("btn", 0, True), ("move", 32768, 32768), ("btn", 0, False), ("key", 0x0D, True, False), ("key", 0x0D, False, False),
            ("text", "Chào máy PC"), ("move", 100, 100), ("wheel", 240, False), ("clip", "chu copy")]
    ck("chuột / phím / chữ có dấu / cuộn / bộ nhớ copy của khách tới đúng máy PC, đúng thứ tự", wait(lambda: io_.ev == want, 5), io_.ev)
    n0 = v.count(R.S_VIDEO); time.sleep(1.0)
    ck("gói giả lệnh trạm từ khách bị trạm bỏ: phiên vẫn chạy, hình vẫn tới", rm.sess is not None and v.count(R.S_VIDEO) > n0 + 10, (rm.sess, v.count(R.S_VIDEO) - n0))
    v.c.send(R.C_QUALITY, b'{"q":"bal"}')
    m = v.take(R.S_SIZE, 10)
    ck("khách đổi chất lượng → nhận SIZE mới (1600x900: nén CPU tối đa cạnh 1600)", m is not None and json.loads(m[1]) == {"w": 1600, "h": 900}, m)

    print("3. Người mở sau đá người mở trước · đóng phiên")
    sess1 = rm.sess
    v2 = View(R.DirectConn("127.0.0.1", port, fp, 3.0), {"v": 2, "token": "t", "pc": PC, "client": "android", "q": "auto", "maxh": 960})
    m = v.take(S_ERROR, 6)
    ck("người đang xem nhận KICKED", m is not None and json.loads(m[1])["code"] == "KICKED", m)
    m = v2.take(S_WELCOME, 15); wel = json.loads(m[1]) if m else {}
    ck("người mới nhận WELCOME theo yêu cầu của mình (cạnh dài ≤ 960)", (wel.get("w"), wel.get("h")) == (960, 540), wel)
    ck("máy PC: phiên cũ đã đóng, phiên mới là phiên khác", wait(lambda: rm.sess is not None and rm.sess is not sess1 and sess1.closed, 5))
    fr = wait(lambda: len(v2.frames()) >= 20 and v2.frames(), 10) or []
    ck("người mới nhận hình từ khung khoá", bool(fr) and fr[0][0] & 1 == 1, len(fr))
    enc = wait(lambda: cur_enc(rm), 5)
    v2.c.send(C_BYE)
    ck("khách đóng → máy PC tắt ffmpeg (không ai xem thì không tốn máy)", wait(lambda: rm.sess is None and enc.exited(), 6), (rm.sess, enc.proc.poll()))

    print("4. Máy PC đi đường vòng (WebSocket) · máy PC mất mạng giữa phiên")
    rm.stop = True
    if rm.conn: rm.conn.close()
    time.sleep(0.5)
    io2 = R.NullIO(1366, 768); logs2 = []
    real_connect = R.connect
    R.connect = lambda stream_, cafile=None, log=None: R.WSConn("ws://127.0.0.1:%d/v2/stream" % wsport, 3.0, plain=True)     # như cloudflared chuyển vào cổng nội bộ
    rm2 = R.Remote(lambda: {"id": PC, "token": "tok-1"}, lambda fn, body: {"ok": True, "on": True, "node": "wintest", "stream": stream}, io2, lambda: FF, logs2.append, None,
                   caps={"enc": ["x264"], "cap": "test"})
    rm2.sleep = lambda s: time.sleep(min(s, 0.3))
    threading.Thread(target=rm2.run, daemon=True).start()
    ck("máy PC vào trạm qua đường WebSocket", wait(lambda: "cho nguoi xem" in rm2.state and "(ws)" in rm2.state, 8), (rm2.state, logs2[-3:]))
    v3 = View(R.DirectConn("127.0.0.1", port, fp, 3.0), {"v": 2, "token": "t", "pc": PC, "client": "pc", "q": "auto"})
    m = v3.take(S_WELCOME, 15); wel = json.loads(m[1]) if m else {}
    ck("khách xem được máy đi đường vòng: hình giữ nguyên cỡ màn 1366x768", (wel.get("w"), wel.get("h")) == (1366, 768) and wait(lambda: v3.count(R.S_VIDEO) >= 30, 12), (wel, v3.count(R.S_VIDEO)))
    fr = v3.frames(); open(h264, "wb").write(b"".join(x[9:] for x in fr))
    rr = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=width,nb_read_frames", "-of", "json", h264],
                        capture_output=True, timeout=90)
    try: sj = json.loads(rr.stdout)["streams"][0]
    except Exception: sj = {"err": (rr.stderr or b"")[-300:]}
    ck("hình đi đường WebSocket (có che mặt nạ từng khung) vẫn giải mã trọn vẹn", sj.get("width") == 1366 and int(sj.get("nb_read_frames") or 0) == len(fr), (sj, len(fr)))
    enc = wait(lambda: cur_enc(rm2), 5)
    rm2.conn.close()                                                       # máy PC rớt mạng
    ck("máy PC rớt mạng → tắt ffmpeg rồi tự nối lại; khách KHÔNG bị đá, hình chạy tiếp", wait(lambda: enc is not None and enc.exited() and cur_enc(rm2) not in (None, enc), 12),
       (rm2.state, logs2[-4:]))
    with v3.lock: v3.rx[:] = [m for m in v3.rx if m[0] != R.S_VIDEO]
    fr = wait(lambda: len(v3.frames()) >= 10 and v3.frames(), 12) or []
    ck("… hình sau khi nối lại bắt đầu bằng khung khoá, khách vẫn còn kết nối", bool(fr) and fr[0][0] & 1 == 1 and v3.alive and v3.count(S_ERROR) == 0, (len(fr), v3.alive))
    rm2.stop = True
    c_ = rm2.conn
    if c_ is not None: c_.close()
    m = v3.take(S_ERROR, 40)
    ck("máy PC tắt hẳn → khách được giữ chờ rồi nhận OFFLINE", m is not None and json.loads(m[1])["code"] == "OFFLINE", m)
    R.connect = real_connect
    time.sleep(0.5)
    out = open(os.path.join(tmp, "out.log"), errors="replace").read()
    ck("nhật ký máy chủ: có dòng máy PC vào / rời trạm + phiên xem, không lỗi phiên, không lộ mã máy", "nối vào trạm" in out and "rời trạm" in out and "▶ PC" in out and "■ PC" in out
       and "lỗi phiên" not in out and "Traceback" not in out and "tok-1" not in out, out[-1200:])
finally:
    for x in (rm, rm2):
        if x is not None: x.stop = True
    proc.terminate()
    try: proc.wait(5)
    except Exception: proc.kill()
    logf.close()
    if FAIL: print(open(os.path.join(tmp, "out.log"), errors="replace").read()[-2500:])
    shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
