# -*- coding: utf-8 -*-
"""Kiểm phần MÁY ĐIỆN THOẠI của bluestream.py còn chạy y như cũ sau khi thêm móc trạm máy PC:
   chạy `bluestream.py --selftest` thật (TLS, nguồn hình giả, ffmpeg) rồi nối bằng brstream.StreamClient (mã của app PC).
   Chạy:  python3 winpc/tests/remote/test_phone_path.py [thư_mục_chứa_bluestream.py]      (mặc định: windows/ của kho mã)
"""
import hashlib, os, shutil, socket, ssl, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths                                                      # noqa: E402
SRC = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else paths.SRV
sys.path.insert(0, paths.CLIENT)
import brstream                                                   # noqa: E402

OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


tmp = tempfile.mkdtemp(prefix="cbphone-")
for f in ("bluestream.py", "pcrelay.py"):
    if os.path.isfile(os.path.join(SRC, f)): shutil.copy(os.path.join(SRC, f), os.path.join(tmp, f))
port, wsport = free_port(), free_port()
open(os.path.join(tmp, "cloudphone.conf"), "w").write(f"NODE_ID=wintest\nSTREAM_PORT={port}\nSTREAM_WS_PORT={wsport}\nUPNP=0\n")
logf = open(os.path.join(tmp, "out.log"), "wb")
proc = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=tmp, stdout=logf, stderr=subprocess.STDOUT)
try:
    t0 = time.time(); up = False
    while time.time() - t0 < 40 and proc.poll() is None:
        try: socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); up = True; break
        except OSError: time.sleep(0.3)
    ck("bluestream --selftest chạy, mở cổng TLS", up, open(os.path.join(tmp, "out.log"), errors="replace").read()[-800:])
    der = ssl.PEM_cert_to_DER_cert(open(os.path.join(tmp, "rtc", "stream-cert.pem")).read())
    fp = hashlib.sha256(der).hexdigest()
    ev = []; lock = threading.Lock()

    def on_event(k, d):
        with lock: ev.append((k, d if k != "video" else (d[0], d[1], len(d[2]), d[2][:5])))
    ep = {"stream": {"direct": [{"host": "127.0.0.1", "port": port, "lan": True}], "cert": fp}}
    cli = brstream.StreamClient(ep, lambda force=False: "t", "12345678-1234-4234-8234-123456789012", on_event, q="eco")
    cli.start()
    t0 = time.time()
    while time.time() - t0 < 25:
        with lock: nv = sum(1 for k, _ in ev if k == "video")
        if nv >= 30: break
        time.sleep(0.2)
    with lock: evs = list(ev)
    wel = next((d for k, d in evs if k == "welcome"), None)
    vids = [d for k, d in evs if k == "video"]
    ck("app nối thẳng TLS (kiểm mã chứng chỉ) → nhận WELCOME của máy thử", bool(wel) and wel.get("ok") and wel.get("codec") == "h264" and wel.get("w") and wel.get("h"), (wel, evs[:5]))
    ck("nhận hình H.264: ≥ 30 khung, khung đầu là khung khoá có SPS/PPS, mở đầu bằng mã bắt đầu NAL", len(vids) >= 30 and vids[0][0] & 3 == 3 and vids[0][3][:4] == b"\x00\x00\x00\x01",
       (len(vids), vids[:2]))
    ck("app không coi là hình của máy PC (WELCOME không có kind)", bool(wel) and "kind" not in wel, wel)
    cli.touch(0, 0, 0.5, 0.5); cli.touch(1, 0, 0.5, 0.5); cli.quality("bal")
    time.sleep(2.5)
    with lock: n2 = sum(1 for k, _ in ev if k == "video")
    st = [d for k, d in ev if k == "stats"]
    ck("chạm + đổi chất lượng xong hình vẫn chạy, có số liệu", n2 > len(vids) and bool(st), (n2, len(vids), st[-1:] if st else None))
    cli.close(); time.sleep(0.8)
    out = open(os.path.join(tmp, "out.log"), errors="replace").read()
    ck("nhật ký: phiên mở rồi đóng bình thường, không có lỗi phiên", "đóng (gửi" in out and "lỗi phiên" not in out and "Traceback" not in out, out[-1500:])
    if os.path.isfile(os.path.join(tmp, "pcrelay.py")):
        ck("dòng khởi động báo trạm máy PC BẬT (dấu để lệnh A nhận ra bản mới)", "bản 21/11a: trạm trung chuyển máy PC cho thuê BẬT" in out, [l for l in out.splitlines() if "21/11a" in l])
finally:
    proc.terminate()
    try: proc.wait(5)
    except Exception: proc.kill()
    logf.close()
    if FAIL: print(open(os.path.join(tmp, "out.log"), errors="replace").read()[-3000:])
    shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
