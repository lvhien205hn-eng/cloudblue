# -*- coding: utf-8 -*-
"""CI linux-check (chạy trên MÁY CI, cạnh máy ảo QEMU đang chạy CachyOS vừa cài): thử ĐẦU-CUỐI điều khiển từ xa trên KDE thật.
     · máy chủ Supabase giả (fake_sb.py, cổng --sb) — agent trong máy ảo đăng ký + hỏi "nối tới trạm nào" (pc_relay_where)
     · máy chủ phát hình THẬT (windows/bluestream.py --selftest + pcrelay.py, TLS thật, cổng --relay) — máy ảo gọi 10.0.2.2 = máy CI
     · người xem (như app / web): chờ máy CachyOS vào trạm → mở điều khiển → nhận hình (giải mã đếm khung) → rê chuột 2 góc màn hình,
       so 2 khung hình: con trỏ chuột trên màn hình KDE THẬT phải đổi chỗ → gõ chữ → đóng
   Ghi kết quả JSON vào --out rồi tiếp tục phục vụ (máy ảo còn gọi máy chủ giả) tới khi bị tắt.
   python3 linux_remote_host.py --sb 8099 --relay 8189 --out remote.json --log rpc.log [--wait 900]"""
import argparse, hashlib, json, os, shutil, socket, ssl, struct, subprocess, sys, tempfile, threading, time
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [HERE, os.path.join(REPO, "winpc", "agent"), os.path.join(REPO, "winpc", "lib")]
import fake_sb                                                   # noqa: E402
import pcremote as R                                             # noqa: E402

C_HELLO, C_BYE, S_WELCOME, S_ERROR = 0x01, 0x19, 0x81, 0x86


def say(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


class View:
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
                with self.lock: self.rx.append((t, p, time.time()))
        except Exception:
            self.alive = False

    def _ping(self):
        while self.alive:
            try: self.c.send(R.C_PING, struct.pack(">Q", int(time.time() * 1000)))
            except Exception: return
            time.sleep(2)

    def first(self, t, timeout):
        end = time.time() + timeout
        while time.time() < end and self.alive:
            with self.lock:
                for m in self.rx:
                    if m[0] in (t, S_ERROR): return m
            time.sleep(0.1)
        return None

    def frames(self, since=0.0):
        with self.lock: return [(m[1], m[2]) for m in self.rx if m[0] == R.S_VIDEO and m[2] >= since]


def decode_gray(h264, w, h):
    """Giải mã cả luồng → danh sách khung xám (bytes, mỗi khung w*h)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "pipe:0", "-vf", "scale=%d:%d,format=gray" % (w, h),
                        "-f", "rawvideo", "pipe:1"], input=h264, capture_output=True, timeout=120)
    n = w * h
    return [r.stdout[i:i + n] for i in range(0, len(r.stdout) - n + 1, n)], (r.stderr or b"")[-200:].decode("utf-8", "replace")


def region_diff(a, b, w, cx, cy, r=12):
    """Khác biệt trung bình 2 khung xám quanh điểm (cx, cy) bán kính r."""
    tot = cnt = 0
    for y in range(max(0, cy - r), cy + r):
        for x in range(max(0, cx - r), min(w, cx + r)):
            i = y * w + x
            if i < len(a) and i < len(b): tot += abs(a[i] - b[i]); cnt += 1
    return tot / max(cnt, 1)


def decode_pick(h264, w, h, idx):
    """Giải mã ĐỦ độ phân giải chỉ vài khung (số thứ tự idx) → {số: khung xám w*h}."""
    sel = "+".join("eq(n\\,%d)" % i for i in sorted(set(idx)))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "pipe:0", "-vf", "select='%s',format=gray" % sel, "-fps_mode", "passthrough",
                        "-f", "rawvideo", "pipe:1"], input=h264, capture_output=True, timeout=180)
    n = w * h; frames = [r.stdout[i:i + n] for i in range(0, len(r.stdout) - n + 1, n)]
    return dict(zip(sorted(set(idx)), frames))


def timeline(h264, w, h, pts, half=24, thr=40):
    """Giải mã ĐỦ độ phân giải từng khung (đọc dần, không giữ cả luồng) → mỗi vùng quanh pts: số điểm khác hẳn khung ĐẦU (con trỏ tới / đi)."""
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "pipe:0", "-vf", "format=gray", "-f", "rawvideo", "pipe:1"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def feed():
        try: p.stdin.write(h264); p.stdin.close()
        except OSError: pass
    threading.Thread(target=feed, daemon=True).start()
    n = w * h; first = None; out = {k: [] for k in pts}
    while True:
        buf = p.stdout.read(n)
        if not buf or len(buf) < n: break
        if first is None: first = buf
        for k, (cx, cy) in pts.items():
            c = 0
            x0, x1 = max(0, cx - half), min(w, cx + half)
            for y in range(max(0, cy - half), min(h, cy + half)):
                a, b = buf[y * w + x0:y * w + x1], first[y * w + x0:y * w + x1]
                c += sum(1 for i in range(len(a)) if abs(a[i] - b[i]) > thr)
            out[k].append(c)
    p.wait(30)
    return out


def crop_art(g, w, h, cx, cy, half=24, step=3):
    """Ô vuông quanh (cx, cy) vẽ bằng chữ (sáng → '@'): nhìn được con trỏ chuột trong nhật ký CI."""
    pal = " .:-=+*#%@"; rows = []
    for y in range(max(0, cy - half), min(h, cy + half), step):
        rows.append("".join(pal[min(9, g[y * w + x] * 10 // 256)] for x in range(max(0, cx - half), min(w, cx + half), step)))
    return rows


def change_box(a, b, w, thr=30):
    """Chỗ 2 khung xám khác nhau rõ (|a-b| > thr): số điểm + khung bao [x0, y0, x1, y1] (toạ độ ảnh nhỏ) — để biết con trỏ / hình đổi ở đâu."""
    xs, ys = [], []
    for i in range(min(len(a), len(b))):
        if abs(a[i] - b[i]) > thr: xs.append(i % w); ys.append(i // w)
    return {"n": len(xs), "box": [min(xs), min(ys), max(xs), max(ys)] if xs else None}


def near(box_pts, p, r=20):
    """Có điểm đổi nào trong bán kính r quanh p không (dò lại từ danh sách điểm đổi)."""
    return any(abs(x - p[0]) <= r and abs(y - p[1]) <= r for x, y in box_pts)


def change_pts(a, b, w, thr=30):
    return [(i % w, i // w) for i in range(min(len(a), len(b))) if abs(a[i] - b[i]) > thr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sb", type=int, default=8099); ap.add_argument("--relay", type=int, default=8189)
    ap.add_argument("--out", default="remote.json"); ap.add_argument("--log", default="rpc.log"); ap.add_argument("--wait", type=int, default=900)
    ap.add_argument("--guest-host", default="10.0.2.2")
    a = ap.parse_args()
    out = {"ok": False}

    def save():
        with open(a.out, "w") as f: json.dump(out, f, ensure_ascii=False, indent=1)
    save()
    # ---- máy chủ phát hình thật
    sd = tempfile.mkdtemp(prefix="cbrelay-")
    for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(REPO, "windows", f), os.path.join(sd, f))
    open(os.path.join(sd, "cloudphone.conf"), "w").write("NODE_ID=citest\nSTREAM_PORT=%d\nSTREAM_WS_PORT=0\nUPNP=0\n" % a.relay)
    relay = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=sd, stdout=open(os.path.join(sd, "relay.log"), "wb"), stderr=subprocess.STDOUT)
    end = time.time() + 60
    while time.time() < end and relay.poll() is None:
        try: socket.create_connection(("127.0.0.1", a.relay), 0.5).close(); break
        except OSError: time.sleep(0.3)
    cert = os.path.join(sd, "rtc", "stream-cert.pem")
    if not os.path.isfile(cert):
        out["err"] = "may chu phat hinh khong chay: " + open(os.path.join(sd, "relay.log"), "rb").read()[-400:].decode("utf-8", "replace"); save(); return 1
    fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(cert).read())).hexdigest()
    say("may chu phat hinh chay :%d (ma chung chi %s...)" % (a.relay, fp[:12]))
    # ---- máy chủ Supabase giả (máy ảo gọi 10.0.2.2)
    fake_sb.RELAY = {"direct": [{"host": a.guest_host, "port": a.relay, "lan": True}], "cert": fp}
    srv = ThreadingHTTPServer(("0.0.0.0", a.sb), fake_sb.H); srv.log = os.path.abspath(a.log)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    say("may chu Supabase gia :%d" % a.sb)
    # ---- người xem: chờ máy CachyOS vào trạm
    t0 = time.time(); v = None; wel = None
    while time.time() - t0 < a.wait:
        try:
            v = View(R.DirectConn("127.0.0.1", a.relay, fp, 5.0), {"v": 2, "token": "t", "pc": fake_sb.PC_ID, "client": "web", "ver": "ci", "q": "eco"})
            m = v.first(S_WELCOME, 60)
            if m is not None and m[0] == S_WELCOME:
                wel = json.loads(m[1]); break
            say("chua mo duoc (%s) - thu lai" % ((m[1][:160].decode("utf-8", "replace")) if m else "het gio"))
        except Exception as e:
            say("chua noi duoc tram: %r" % (e,))
        try: v.c.close()
        except Exception: pass
        time.sleep(8)
    out["welcome"] = wel; out["wait_s"] = int(time.time() - t0)
    if not wel or not wel.get("ok"):
        out["err"] = "may CachyOS khong vao tram / khong mo duoc dieu khien sau %d giay" % out["wait_s"]; save()
        while True: time.sleep(60)
    w, h = int(wel.get("w") or 1280), int(wel.get("h") or 720)
    say("WELCOME %s" % wel)
    time.sleep(6)
    n0 = len(v.frames())
    t_m1 = time.time(); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 13000, 13000)); time.sleep(2.5); t_a = time.time()
    time.sleep(1.0)
    t_m2 = time.time(); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 52000, 52000)); time.sleep(2.5); t_b = time.time()
    time.sleep(1.0)
    t_m3 = time.time(); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 1100, 64600)); time.sleep(2.5); t_c = time.time()      # góc dưới trái (nút menu trên thanh tác vụ)
    # 22.11g: BẤM nút menu (chuột thật của KWin phải tới đúng chỗ — con trỏ tự vẽ không chứng minh được) → menu KDE mở = hình đổi lớn → Esc đóng
    t_k0 = time.time(); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 1, 0, 1100, 64600)); time.sleep(0.12); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 2, 0, 1100, 64600))
    time.sleep(3.0); t_k1 = time.time()
    v.c.send(R.C_KEY, struct.pack(">BII", 1, 0x1B, 0)); time.sleep(0.1); v.c.send(R.C_KEY, struct.pack(">BII", 0, 0x1B, 0)); time.sleep(2.0); t_k2 = time.time()
    v.c.send(R.C_TEXT, b"cloudblue"); time.sleep(1.5)
    # 23/11: MỞ APP NHƯ KHÁCH — bấm nút menu KDE, gõ tên app, Enter (Konsole = "cmd" của Linux · Firefox = trình duyệt) → ảnh từng bước
    t_app = {}

    def click(x, y):
        v.c.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, x, y)); time.sleep(0.3)
        v.c.send(R.C_MOUSE, struct.pack(">BBHH", 1, 0, x, y)); time.sleep(0.12); v.c.send(R.C_MOUSE, struct.pack(">BBHH", 2, 0, x, y))

    def key(vk):
        v.c.send(R.C_KEY, struct.pack(">BII", 1, vk, 0)); time.sleep(0.08); v.c.send(R.C_KEY, struct.pack(">BII", 0, vk, 0))
    t_app["0-truoc"] = time.time()
    for i, (app, wait_s) in enumerate((("konsole", 8), ("firefox", 16))):
        click(1100, 64600); time.sleep(2.5); t_app["%d-%s-1-menu" % (i + 1, app)] = time.time()
        v.c.send(R.C_TEXT, app.encode()); time.sleep(2.5); t_app["%d-%s-2-go-ten" % (i + 1, app)] = time.time()
        key(0x0D); time.sleep(wait_s); t_app["%d-%s-3-enter" % (i + 1, app)] = time.time()
    st = None
    with v.lock:
        for m in v.rx:
            if m[0] == R.S_STATS: st = m[1]
    fr = v.frames()
    out.update(frames=len(fr), frames_first_6s=n0, key_first=bool(fr and fr[0][0][0] & 3 == 3), stats=json.loads(st) if st else None)
    data = b"".join(x[0][9:] for x in fr)
    gw, gh = 320, max(2, int(320 * h / w) // 2 * 2)
    gray, err = decode_gray(data, gw, gh)
    out.update(decoded=len(gray), decode_err=err)
    ia = sum(1 for x in fr if x[1] <= t_a) - 1; ib = sum(1 for x in fr if x[1] <= t_b) - 1
    if gray and 0 <= ia < len(gray) and 0 <= ib < len(gray):
        A, B = gray[ia], gray[ib]
        p1 = (gw * 13000 // 65536, gh * 13000 // 65536); p2 = (gw * 52000 // 65536, gh * 52000 // 65536)
        d1, d2 = region_diff(A, B, gw, *p1), region_diff(A, B, gw, *p2)
        far = region_diff(A, B, gw, gw // 2, gh // 8)
        pts = change_pts(A, B, gw)
        moved = bool(d1 > 3 and d2 > 3) or (near(pts, p1) and near(pts, p2))
        out.update(cursor_diff_from=round(d1, 1), cursor_diff_to=round(d2, 1), diff_elsewhere=round(far, 1), cursor_moved=moved,
                   chg_ab=change_box(A, B, gw), chg_all=change_box(gray[0], gray[-1], gw), p1=list(p1), p2=list(p2), gray_size=[gw, gh],
                   frame_ab=[ia, ib])
        ic = sum(1 for x in fr if x[1] <= t_c) - 1
        try:                                                     # dòng thời gian từng khung: con trỏ có tới đúng chỗ sau mỗi lần rê không (trễ bao nhiêu khung)
            P = {"p1": (w * 13000 // 65536, h * 13000 // 65536), "p2": (w * 52000 // 65536, h * 52000 // 65536), "goc": (w * 1100 // 65536, h * 64600 // 65536)}
            tl = timeline(data, w, h, P)
            mi = [sum(1 for x in fr if x[1] <= t) for t in (t_m1, t_m2, t_m3, t_k0)]
            seen = {}
            for k, (i0, i1), tm in (("p1", (mi[0], mi[1]), t_m1), ("p2", (mi[1], mi[2]), t_m2), ("goc", (mi[2], mi[3]), t_m3)):     # (không dùng tên a: a = tham số dòng lệnh)
                hit = next((i for i in range(i0, min(i1, len(tl[k]))) if tl[k][i] >= 25), None)
                seen[k] = None if hit is None else round(fr[hit][1] - tm, 2)                            # giây từ lúc rê tới khung đầu có con trỏ ở đó
            out["tl"] = {"moves": mi[:3], "seen_s": seen, **{k: "".join(str(min(9, c // 25)) for c in tl[k]) for k in tl}}
            out["cursor_moved"] = all(seen[k] is not None for k in seen)
            out["cursor_lag_s"] = max(seen.values()) if out["cursor_moved"] else None
        except Exception as e:
            out["tl_err"] = repr(e)[:200]
        try:
            pk = decode_pick(data, w, h, [0, ia, ib, ic, len(fr) - 1])
            pts = {"giua": (w // 2, h // 2), "p1": (w * 13000 // 65536, h * 13000 // 65536), "p2": (w * 52000 // 65536, h * 52000 // 65536),
                   "goc": (w * 1100 // 65536, h * 64600 // 65536)}
            out["art"] = {"%s@%s" % (k, name): crop_art(g, w, h, *pts[name]) for k, g in (("dau", pk.get(0)), ("A", pk.get(ia)), ("B", pk.get(ib)), ("C", pk.get(ic)),
                                                                                           ("cuoi", pk.get(len(fr) - 1))) if g for name in pts}
        except Exception as e:
            out["art_err"] = repr(e)[:200]
        try:                                                     # bấm nút menu → menu KDE mở (hình đổi lớn), Esc → đóng
            k0, k1, k2 = (sum(1 for x in fr if x[1] <= t) - 1 for t in (t_k0, t_k1, t_k2))
            if 0 <= k0 < len(gray) and 0 <= k1 < len(gray) and 0 <= k2 < len(gray):
                c1, c2 = change_box(gray[k0], gray[k1], gw), change_box(gray[k0], gray[k2], gw)
                tot = float(gw * gh)
                out["click"] = {"frames": [k0, k1, k2], "open": round(c1["n"] / tot, 3), "open_box": c1["box"], "after_esc": round(c2["n"] / tot, 3)}
                out["click_ok"] = c1["n"] / tot > 0.03
        except Exception as e:
            out["click_err"] = repr(e)[:200]
        try:
            pk2 = decode_pick(data, w, h, [k0, k1])
            out["art_click"] = {"%s@goc" % k: crop_art(g, w, h, w * 9000 // 65536, h * 52000 // 65536, half=60, step=6) for k, g in (("truoc", pk2.get(k0)), ("sau", pk2.get(k1))) if g}
        except Exception as e:
            out["art_click_err"] = repr(e)[:200]
    try:                                                         # ảnh màu từng bước mở app → thư mục linux-shots (CI đẩy lên nhánh linux-shots)
        shots = os.path.join(os.path.dirname(os.path.abspath(a.out)), "linux-shots"); os.makedirs(shots, exist_ok=True)
        raw = os.path.join(shots, "stream.h264"); open(raw, "wb").write(data)
        for name, tm in sorted(t_app.items(), key=lambda x: x[1]):
            idx = sum(1 for x in fr if x[1] <= tm) - 1
            if idx >= 0:
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-vf", "select=eq(n\\,%d)" % idx, "-vsync", "0", "-frames:v", "1",
                                os.path.join(shots, name + ".png")], timeout=180)
        out["app_shots"] = sorted(f for f in os.listdir(shots) if f.endswith(".png"))
    except Exception as e:
        out["app_shots_err"] = repr(e)[:200]
    v.c.send(C_BYE); time.sleep(1)
    out["ok"] = bool(out.get("frames", 0) >= 30 and out.get("decoded", 0) >= out.get("frames", 0) - 2 and out.get("key_first"))
    save(); say("KET QUA %s" % json.dumps(out, ensure_ascii=False)[:600])
    while True: time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
