# -*- coding: utf-8 -*-
# =====================================================================
#  phathinh.py — PHÁT HÌNH KIỂU PARSEC (WebRTC qua UDP · nén bằng card NVIDIA) cho máy LDPlayer
#
#  python phathinh.py --server   ← bảng BlueRoblox tự chạy (dịch vụ "phat-hinh"): tự tải FFmpeg 6.1 + MediaMTX,
#                                  mở tường lửa, chạy máy chủ WebRTC. Có khách mở máy nào → tự bật phát máy đó,
#                                  khách đóng → 8 giây sau tự tắt (không tốn card/CPU khi không ai xem).
#  python phathinh.py TÊN_MÁY    ← MediaMTX tự gọi (chạy tay để thử cũng được)
#
#  Đường hình:  cửa sổ máy (Windows Graphics Capture — quay được cả khi cửa sổ chạy ngầm/bị che)
#    → cắt đúng phần màn hình Android → NVENC (card hết phiên/lỗi → CPU x264) → RTSP nội bộ → MediaMTX → WebRTC (UDP)
#  Trang web / app: tự dùng hình mới (cpapi /__rtc/<cổng>/whep); không nối được → tự quay về hình cũ. Chạm/phím đi đường cũ.
#
#  cloudphone.conf (không bắt buộc):
#    RTC=0 tắt hẳn · RTC_UDP_PORT=8189 (máy chủ 2 đặt 8190…) · RTC_FPS=60 · RTC_MBPS=4 · RTC_CPU=1 luôn nén CPU
#    RTC_PUBLIC_IP=… (để trống = tự dò IP mạng nhà)
# =====================================================================
import argparse, ctypes, ctypes.wintypes as wt, io, json, os, subprocess, sys, threading, time, urllib.request, zipfile

B = os.path.dirname(os.path.abspath(__file__)); RTC = os.path.join(B, "rtc"); NOWIN = 0x08000000
LOGD = os.path.join(RTC, "log"); os.makedirs(LOGD, exist_ok=True)
def conf():
    d = {}
    try:
        for l in open(os.path.join(B, "cloudphone.conf"), encoding="utf-8-sig"):
            l = l.strip()
            if "=" in l and not l.startswith("#"): k, v = l.split("=", 1); d[k.strip()] = v.strip()
    except FileNotFoundError: pass
    return d
C = conf()
UDP = int(C.get("RTC_UDP_PORT") or 8189); HTTP = int(C.get("RTC_HTTP_PORT") or 8889); RTSP = int(C.get("RTC_RTSP_PORT") or 8554)
MTXV = "v1.9.3"                                         # khoá phiên bản (file cấu hình viết đúng cho bản này)
FF = os.path.join(RTC, "ffmpeg.exe"); MTXD = os.path.join(RTC, "mtx193"); MTX = os.path.join(MTXD, "mediamtx.exe")
YML = os.path.join(MTXD, "blue.yml")
PY = sys.executable
PYW = os.path.join(os.path.dirname(PY), "pythonw.exe")
if not os.path.isfile(PYW): PYW = PY
_LOGF = None
def log(*a):
    s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        if sys.stdout: print(s, flush=True)
    except Exception: pass
    if _LOGF:
        try: _LOGF.write(s + "\n"); _LOGF.flush()
        except Exception: pass

# ======================= MÁY CHỦ (--server) =======================
def fetch(url, timeout=300):
    rq = urllib.request.Request(url, headers={"User-Agent": "BlueRoblox"})
    with urllib.request.urlopen(rq, timeout=timeout) as r: return r.read()
def setup_tools():
    # FFmpeg 6.1 (NVENC API 12.1) — bản 7.x đòi driver NVIDIA 570+, card GTX 10xx đang có NVENC 12.2
    if not (os.path.isfile(FF) and os.path.isfile(os.path.join(RTC, "ff61.ok"))):
        log("tải FFmpeg 6.1 (~80MB)…")
        z = zipfile.ZipFile(io.BytesIO(fetch("https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip")))
        open(FF, "wb").write(z.read(next(x for x in z.namelist() if x.endswith("/bin/ffmpeg.exe"))))
        open(os.path.join(RTC, "ff61.ok"), "w").write("1")
    if not os.path.isfile(MTX):
        log(f"tải MediaMTX {MTXV}…"); os.makedirs(MTXD, exist_ok=True)
        z = zipfile.ZipFile(io.BytesIO(fetch(f"https://github.com/bluenviron/mediamtx/releases/download/{MTXV}/mediamtx_{MTXV}_windows_amd64.zip")))
        open(MTX, "wb").write(z.read("mediamtx.exe"))
    try:
        import windows_capture, numpy  # noqa: F401
    except ImportError:
        log("cài thư viện quay cửa sổ (windows-capture, numpy)…")
        subprocess.run([PY, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "windows-capture", "numpy"], creationflags=NOWIN)
def public_ip():
    if C.get("RTC_PUBLIC_IP"): return C["RTC_PUBLIC_IP"]
    for u in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://checkip.amazonaws.com"):
        try:
            ip = fetch(u, 10).decode().strip()
            if ip.count(".") == 3 and all(p.isdigit() for p in ip.split(".")): return ip
        except Exception: pass
    return ""
def write_yml(ip):
    cmd = f'"{PYW}" "{os.path.join(B, "phathinh.py")}" $MTX_PATH'
    hosts = f"[{ip}]" if ip else "[]"
    open(YML, "w", encoding="utf-8").write(f"""# TỰ TẠO bởi phathinh.py — đừng sửa tay (sửa cloudphone.conf rồi bật lại dịch vụ phat-hinh)
logLevel: warn
logDestinations: [stdout]
rtmp: no
hls: no
srt: no
rtsp: yes
protocols: [tcp]
rtspAddress: 127.0.0.1:{RTSP}
webrtc: yes
webrtcAddress: 127.0.0.1:{HTTP}
webrtcAllowOrigin: '*'
webrtcLocalUDPAddress: :{UDP}
webrtcLocalTCPAddress: :{UDP}
webrtcIPsFromInterfaces: yes
webrtcAdditionalHosts: {hosts}
webrtcICEServers2: []
paths:
  "~^[A-Za-z0-9_.-]+$":
    runOnDemand: '{cmd}'
    runOnDemandRestart: yes
    runOnDemandStartTimeout: 15s
    runOnDemandCloseAfter: 8s
""")
def firewall():
    for proto in ("UDP", "TCP"):
        nm = f"BlueRoblox WebRTC {proto}"
        subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], capture_output=True, creationflags=NOWIN)
        subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={nm}", "dir=in", "action=allow",
                        f"protocol={proto}", f"localport={UDP}"], capture_output=True, creationflags=NOWIN)
def server():
    if C.get("RTC", "1") == "0":
        log("RTC=0 — đang TẮT hình kiểu mới (web/app dùng hình cũ)")
        while True: time.sleep(3600)
    setup_tools(); firewall()
    subprocess.run(["taskkill", "/F", "/IM", "mediamtx.exe"], capture_output=True, creationflags=NOWIN); time.sleep(1)
    while True:
        ip = public_ip(); write_yml(ip)
        log(f"máy chủ hình WebRTC chạy · IP mạng nhà {ip or '(không dò được)'} · cổng hình {UDP} UDP+TCP")
        log(f"  → modem/router phải MỞ CỔNG {UDP} (UDP và TCP) về máy này, không thì khách ở xa tự dùng hình cũ")
        p = subprocess.Popen([MTX, YML], cwd=MTXD, creationflags=NOWIN, stdin=subprocess.DEVNULL,
                             stdout=(sys.stdout if sys.stdout else subprocess.DEVNULL), stderr=subprocess.STDOUT)
        while p.poll() is None:                        # IP mạng nhà đổi (cáp quang cấp lại) → bật lại với IP mới
            time.sleep(300)
            if not C.get("RTC_PUBLIC_IP"):
                n = public_ip()
                if n and n != ip: log(f"IP mạng nhà đổi {ip} → {n}: bật lại"); p.kill(); break
        else:
            log(f"MediaMTX dừng (mã {p.returncode}) — bật lại sau 3 giây"); time.sleep(3)

# ======================= PHÁT 1 MÁY =======================
def stream(name, fps, mbps, cpu):
    global _LOGF
    _LOGF = open(os.path.join(LOGD, name + ".txt"), "a", encoding="utf-8")
    try:
        if os.path.getsize(_LOGF.name) > 2_000_000: _LOGF.truncate(0)
    except Exception: pass
    import numpy as np
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl
    u = ctypes.windll.user32
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: u.SetProcessDPIAware()
    def find_top():
        hits = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
                if b.value == name: hits.append(h)
            return True
        u.EnumWindows(cb, 0); return hits[0] if hits else None
    def rect(h):
        r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r)); return r.left, r.top, r.right, r.bottom
    def frame_bounds(h):                               # vùng Windows Graphics Capture quay thật (không gồm bóng đổ)
        r = wt.RECT()
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0: return r.left, r.top, r.right, r.bottom
        return rect(h)
    def render_child(h):                               # cửa sổ con lớn nhất = phần màn hình Android
        kids = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(c, _):
            if u.IsWindowVisible(c):
                l, t, r_, b_ = rect(c); kids.append(((r_ - l) * (b_ - t), (l, t, r_, b_)))
            return True
        u.EnumChildWindows(h, cb, 0)
        return max(kids)[1] if kids else None
    top = find_top()
    if not top: log(f"không thấy cửa sổ '{name}' (máy tắt / không phải LDPlayer)"); time.sleep(5); sys.exit(2)
    if u.IsIconic(top): u.ShowWindow(top, 4); time.sleep(1)       # thu nhỏ thì Windows không vẽ → hiện lại (không cướp chuột/bàn phím)
    fb = frame_bounds(top); ch = render_child(top) or fb
    CX, CY = max(0, ch[0] - fb[0]), max(0, ch[1] - fb[1])
    CW, CH = (ch[2] - ch[0]) & ~1, (ch[3] - ch[1]) & ~1
    FW, FH = fb[2] - fb[0], fb[3] - fb[1]
    log(f"'{name}': quay {CW}x{CH} (lệch {CX},{CY}) · {fps} FPS · {mbps:g} Mbps · {'CPU' if cpu else 'card NVIDIA'}")
    latest = {"buf": None, "n": 0}; lock = threading.Lock()
    cap = WindowsCapture(cursor_capture=None, draw_border=None, window_name=name)   # None = mặc định (Windows 10 cũ không cho tắt viền)
    @cap.event
    def on_frame_arrived(frame: Frame, ctl: InternalCaptureControl):
        a = frame.frame_buffer                         # (cao, rộng, 4) BGRA
        if abs(a.shape[1] - FW) > 6 or abs(a.shape[0] - FH) > 6:      # xoay ngang/dọc → cửa sổ đổi cỡ → thoát, MediaMTX tự bật lại đúng cỡ mới
            log(f"cửa sổ đổi cỡ {FW}x{FH} → {a.shape[1]}x{a.shape[0]} (xoay màn hình) → phát lại"); os._exit(3)
        sub = a[CY:CY + CH, CX:CX + CW]
        if sub.shape[0] == CH and sub.shape[1] == CW:
            with lock: latest["buf"] = np.ascontiguousarray(sub).tobytes(); latest["n"] += 1
    @cap.event
    def on_closed(): log("cửa sổ đóng"); os._exit(0)
    if hasattr(cap, "start_free_threaded"): cap.start_free_threaded()
    else: threading.Thread(target=cap.start, daemon=True).start()
    t0 = time.time()
    while latest["buf"] is None:
        if time.time() - t0 > 10: log("10 giây không nhận được hình từ cửa sổ"); os._exit(4)
        time.sleep(0.01)

    def ffmpeg_cmd(cpu):
        br = f"{mbps:g}M"
        enc = (["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-profile:v", "baseline", "-pix_fmt", "yuv420p", "-threads", "2"] if cpu else
               ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ull", "-zerolatency", "1", "-rc", "cbr", "-delay", "0", "-profile:v", "baseline", "-pix_fmt", "yuv420p"])
        return ([FF, "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer", "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", f"{CW}x{CH}",
                 "-framerate", str(fps), "-i", "-"] + enc +
                ["-b:v", br, "-maxrate", br, "-bufsize", f"{max(mbps / 8, 0.25):.2f}M", "-bf", "0", "-g", str(fps * 2), "-an",
                 "-f", "rtsp", "-rtsp_transport", "tcp", f"rtsp://127.0.0.1:{RTSP}/{name}"])
    def run(cpu):
        p = subprocess.Popen(ffmpeg_cmd(cpu), stdin=subprocess.PIPE, stderr=_LOGF, creationflags=NOWIN)
        step = 1.0 / fps; nxt = time.perf_counter(); t1 = time.time(); sent = 0; start = time.time()
        try:
            while p.poll() is None:
                with lock: buf = latest["buf"]
                p.stdin.write(buf); sent += 1          # gửi đều KHUNG MỚI NHẤT (không xếp hàng khung cũ → không trễ dồn)
                nxt += step; d = nxt - time.perf_counter()
                if d > 0: time.sleep(d)
                else: nxt = time.perf_counter()
                if time.time() - t1 > 15:
                    dt = time.time() - t1
                    log(f"  {'CPU' if cpu else 'NVENC'}: gửi {sent / dt:.0f} khung/giây · cửa sổ vẽ {latest['n'] / dt:.0f}/giây")
                    t1 = time.time(); sent = 0; latest["n"] = 0
        except (BrokenPipeError, OSError): pass
        return p.wait(), time.time() - start
    code, dur = run(cpu)
    if not cpu and dur < 6:                            # card hết phiên NVENC (GTX tối đa vài luồng cùng lúc) / lỗi driver → nén CPU
        log(f"card NVIDIA không nén được (mã {code}) → chuyển CPU x264"); run(True)
    os._exit(0)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("name", nargs="?"); ap.add_argument("--server", action="store_true")
    ap.add_argument("--fps", type=int, default=int(C.get("RTC_FPS") or 60)); ap.add_argument("--mbps", type=float, default=float(C.get("RTC_MBPS") or 4))
    ap.add_argument("--cpu", action="store_true", default=C.get("RTC_CPU", "0") == "1")
    A = ap.parse_args()
    if A.server: server()
    elif A.name: stream(A.name, A.fps, A.mbps, A.cpu)
    else: ap.print_help()
