# -*- coding: utf-8 -*-
"""27/11e — ĐO PHÁT HÌNH ANDROID 9 (đường scrcpy của máy LDPlayer 9) trên máy ảo Android THẬT trong CI. Chỉ đo, không phát hành gì.
     python3 .github/a9-check/test_a9stream.py <api>
   Dùng đúng ScrcpyVideo của windows/bluestream.py (scrcpy-server 2.4 chạy trong máy, H.264, gói 12 byte) để trả lời:
     1. bộ nén H.264 trong máy (list_encoders) — Android 9: OMX.google.h264.encoder (giống LDPlayer 9)
     2. KHUNG KHOÁ: khung I định kỳ có cờ "khoá" của scrcpy không, có phải IDR (NAL 5) không — với khoảng 0,25 (cấu hình A9 hiện tại) và 1
        (máy chủ chỉ thôi "chờ khung khoá" khi thấy cờ khoá → khung I thường không có cờ = phải bật lại bộ nén mới có hình lại)
     3. màn đứng yên: bộ nén có lặp khung không (MuMu lặp ~10 khung/giây, LD9 nghi là không)
     4. khung/giây + cỡ khung theo cỡ hình 1280 / 960 / 800 khi màn hình đang cuộn liên tục
     5. thời gian bật lại bộ nén (gọi start → khung đầu tiên tới máy chủ)
   Kết quả: in ra + bảng trong $GITHUB_STEP_SUMMARY + file a9stream-<api>.json. Mã thoát 0 khi đo được (không chấm đậu/trượt)."""
import importlib.util, json, os, random, re, socket, subprocess, sys, threading, time

API = sys.argv[1] if len(sys.argv) > 1 else "?"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location("bluestream", os.path.join(ROOT, "windows", "bluestream.py"))
bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)
OUT = []


def say(s=""):
    print(s, flush=True); OUT.append(s)


def sh(*a, t=30):
    try:
        r = subprocess.run(["adb", "-s", SERIAL, *a], capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, repr(e)


def serial():
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=20).stdout
    m = re.search(r"^(emulator-\d+)\s+device", out, re.M)
    return m.group(1) if m else ""


def rbsp(b):
    out = bytearray(); z = 0
    for x in b:
        if z >= 2 and x == 3: z = 0; continue
        out.append(x); z = z + 1 if x == 0 else 0
    return bytes(out)


def nals(au):
    """[(loại NAL, loại lát hoặc None)] của 1 gói Annex-B."""
    res = []; i = 0; n = len(au); starts = []
    while True:
        j = au.find(b"\x00\x00\x01", i)
        if j < 0: break
        starts.append(j + 3); i = j + 3
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 3) if k + 1 < len(starts) else n
        if s >= n: continue
        t = au[s] & 0x1F; st = None
        if t in (1, 5):
            try:
                b = bs._Bits(rbsp(au[s + 1:s + 16])); b.ue(); st = b.ue() % 5
            except Exception: st = None
        res.append((t, st))
    return res


class Mover:
    """Cuộn màn hình liên tục (vuốt lên / xuống) bằng adb trong luồng nền."""
    def __init__(self): self.on = False; self.th = None
    def start(self):
        self.on = True; self.th = threading.Thread(target=self.run, daemon=True); self.th.start()
    def run(self):
        up = True
        while self.on:
            sh("shell", "input swipe 360 1050 360 350 350" if up else "input swipe 360 350 360 1050 350", t=10); up = not up
    def stop(self):
        self.on = False
        if self.th: self.th.join(timeout=5)


def capture(tag, msz, fps, kbps, ifr, secs, move):
    fr = []; cut = [0]; lock = threading.Lock()
    def on_au(d, k, c, p):
        if d is None:
            cut[0] += 1; return
        with lock: fr.append((time.monotonic(), len(d), bool(k), bool(c), nals(d)))
    mv = Mover() if move else None
    if mv: mv.start(); time.sleep(0.8)
    sv = bs.ScrcpyVideo(SERIAL, msz, fps, kbps, on_au, iframe=ifr)
    t0 = time.monotonic(); r = {"tag": tag, "max": msz, "fps_req": fps, "kbps": kbps, "iframe": ifr}
    try:
        w, h = sv.start(); r["size"] = f"{w}x{h}"; r["start_s"] = round(time.monotonic() - t0, 2)
        t_end = time.monotonic() + secs
        while time.monotonic() < t_end: time.sleep(0.1)
    except Exception as e:
        r["err"] = repr(e)[:200]
    finally:
        try: sv.stop()
        except Exception: pass
        if mv: mv.stop()
    with lock: f = list(fr)
    r["frames"] = len(f); r["cut"] = cut[0]
    if not f: return r
    r["first_s"] = round(f[0][0] - t0, 2)
    span = max(0.5, f[-1][0] - f[0][0])
    r["fps"] = round((len(f) - 1) / span, 1) if len(f) > 1 else 0.0
    flag = [x for x in f if x[2]]
    idr = [x for x in f if any(t == 5 for t, _ in x[4])]
    intra = [x for x in f if x[4] and all(t not in (1, 5) or st in (2, 4) for t, st in x[4]) and any(t in (1, 5) for t, _ in x[4])]
    i_nonidr = [x for x in intra if not any(t == 5 for t, _ in x[4])]
    p = [x for x in f if x not in intra]
    r.update(flag=len(flag), idr=len(idr), i_all=len(intra), i_nonidr=len(i_nonidr),
             i_nonidr_flag=sum(1 for x in i_nonidr if x[2]), idr_noflag=sum(1 for x in idr if not x[2]),
             multi_slice=sum(1 for x in f if sum(1 for t, _ in x[4] if t in (1, 5)) > 1),
             kb_p=round(sum(x[1] for x in p) / max(1, len(p)) / 1024, 1),
             kb_i=round(sum(x[1] for x in intra) / max(1, len(intra)) / 1024, 1),
             kb_max=round(max(x[1] for x in f) / 1024, 1))
    gaps = [round(b[0] - a[0], 3) for a, b in zip(f, f[1:])]
    if gaps: r["gap_max_s"] = max(gaps)
    return r


def row(r):
    if r.get("err") and not r.get("frames"): return f"| {r['tag']} | ✗ {r['err']} |" + " |" * 9
    return (f"| {r['tag']} | {r.get('size', '?')} | {r.get('fps', 0)} | {r.get('frames', 0)} | {r.get('flag', 0)} | {r.get('idr', 0)} | "
            f"{r.get('i_nonidr', 0)} ({r.get('i_nonidr_flag', 0)} có cờ) | {r.get('kb_p', 0)} / {r.get('kb_i', 0)} / {r.get('kb_max', 0)} | "
            f"{r.get('first_s', '?')} | {r.get('multi_slice', 0)} | {r.get('cut', 0)} |")


# ---------- 27/11f: ĐO SÂU — vì sao Android 9 chỉ ~15 khung/giây (Android 12 cùng máy ảo ~30) ----------
# Mỗi lần đo: khung/giây scrcpy + app trong máy vẽ bao nhiêu khung (dumpsys gfxinfo) + luồng nào ăn CPU (top -H) giữa lúc đo.
# Thêm: giới hạn khung/giây của bộ nén (max_fps 30 / 60 / 0 = không giới hạn), cỡ 480–960, bitrate, tuỳ chọn priority / operating-rate,
# và simpleperf toàn máy (nếu có) để biết thời gian nằm ở đâu (đổi màu RGB→YUV, mã hoá libavc, đọc ngược hình từ GPU…).
def gfx_reset():
    sh("shell", "dumpsys gfxinfo com.android.settings reset", t=15)


def gfx_frames():
    _, out = sh("shell", "dumpsys gfxinfo com.android.settings", t=15)
    m = re.search(r"Total frames rendered:\s*(\d+)", out or ""); j = re.search(r"Janky frames:\s*(\d+)", out or "")
    return (int(m.group(1)) if m else -1), (int(j.group(1)) if j else -1)


def top_threads(n=22):
    """Các luồng ăn CPU nhất (top -H, lấy khối thứ 2 = đo trong 1 giây)."""
    _, out = sh("shell", "top -H -b -n 2 -d 1 -m 40", t=25)
    blocks = re.split(r"\n(?=\s*Tasks:|\s*Threads:)", out or "")
    blk = blocks[-1] if blocks else ""
    lines = [ln.rstrip() for ln in blk.splitlines() if ln.strip()]
    hdr = next((i for i, ln in enumerate(lines) if re.search(r"\bTID\b|\bPID\b", ln) and "%CPU" in ln.replace(" ", "")), None)
    if hdr is None: return lines[:n]
    return lines[hdr:hdr + 1 + n]


_EXTRA = {"v": ""}
_POP = subprocess.Popen
def _pop(args, *a, **k):
    if _EXTRA["v"] and isinstance(args, list) and args and isinstance(args[-1], str) and "video_codec_options=" in args[-1]:
        args = args[:-1] + [args[-1] + _EXTRA["v"]]
    return _POP(args, *a, **k)
subprocess.Popen = _pop


CB_JAR = os.path.join(ROOT, "cbvideo.jar")
CB_DEV = "/data/local/tmp/cbvideo.jar"
CB_LIB = os.path.join(ROOT, "libcbenc.so")              # 27/11h: openh264 + JNI (bộ nén riêng)
CB_LIB_DEV = "/data/local/tmp/libcbenc.so"


class CbVideo(bs.ScrcpyVideo):
    """27/11f: máy chủ hình riêng cho Android 9 (A9Video.java → cbvideo.jar) — cùng giao thức scrcpy, đọc bằng chính ScrcpyVideo."""
    native = False                                           # 27/11h: True → nén bằng openh264 (libcbenc.so)

    def start(self):
        self.started = time.time(); self.lines = []
        sh("push", CB_JAR, CB_DEV, t=60)
        extra = ""
        if self.native:
            sh("push", CB_LIB, CB_LIB_DEV, t=60); extra = f" lib={CB_LIB_DEV} enc_threads=1"
        scid = random.randint(1, 0x7FFFFFFF); self.scid = scid
        cmd = (f"CLASSPATH={CB_DEV} app_process / com.cloudblue.A9Video scid={scid:08x} max_size={self.max_size} "
               f"max_fps={self.fps} video_bit_rate={self.kbps * 1000} i_frame={self.iframe:g} stats=3{extra}")
        with self.lock:
            self.proc = subprocess.Popen([bs.ADB, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL)
        threading.Thread(target=self._srvlog, args=(self.proc,), daemon=True).start()
        code, out, err = bs.adb(self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid:08x}", timeout=10)
        with self.lock: self.fport = int(out.strip()) if out.strip().isdigit() else None
        if not self.fport: self._kill(); raise RuntimeError("forward: " + (err or out)[-200:])
        t0 = time.time(); sock = None
        while time.time() - t0 < 10 and not self.stopped:
            if self.proc.poll() is not None: break
            try:
                s = socket.create_connection(("127.0.0.1", self.fport), timeout=2); s.settimeout(3)
                if s.recv(1) == b"\x00": sock = s; break
                s.close()
            except OSError: pass
            time.sleep(0.15)
        if not sock: self._kill(); raise RuntimeError("cbvideo không nối được: " + " | ".join(self.lines[-5:]))
        return self.attach(sock)

    def _srvlog(self, p):
        try:
            for ln in iter(p.stdout.readline, b""):
                t = ln.decode("utf-8", "replace").strip()
                if t: self.lines.append(t); print("  [cbvideo] " + t, flush=True)
        except Exception: pass

    def request_key(self):
        s = self.sock
        if s:
            try: s.sendall(b"K")
            except OSError: pass


class CbVideoN(CbVideo):
    native = True


def probe(path):
    """ffprobe / ffmpeg giải mã thử dòng H.264 đã ghi → (rộng x cao, số khung giải được, số dòng lỗi)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        e = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True, text=True, timeout=120)
        parts = (r.stdout or "").strip().split(",")
        errs = [x for x in (e.stderr or "").splitlines() if x.strip()]
        if len(parts) >= 3: return f"{parts[0]}x{parts[1]}", int(parts[2] or 0), len(errs), errs[:5]
        return "?", 0, len(errs), errs[:5] + [(r.stderr or "")[-200:]]
    except Exception as ex:
        return "?", 0, -1, [repr(ex)[:200]]


def prof(tag, msz, fps, kbps, secs=6, extra="", sample=False, perf=False, cls=None, keys=0, record=None, move=True):
    """Đo 1 cấu hình: khung/giây phát, khung app vẽ (gfxinfo), luồng ăn CPU (top), simpleperf, xin khung khoá (cbvideo), ghi dòng hình."""
    fr = []; lock = threading.Lock(); r = {"tag": tag, "max": msz, "fps_req": fps, "kbps": kbps, "extra": extra}
    fh = open(record, "wb") if record else None
    def on_au(d, k, c, p):
        if d is None: return
        with lock:
            fr.append((time.monotonic(), len(d), bool(k)))
            if fh: fh.write(d)
    mv = Mover() if move else None
    if mv: mv.start(); time.sleep(0.8)
    _EXTRA["v"] = extra
    sv = (cls or bs.ScrcpyVideo)(SERIAL, msz, fps, kbps, on_au, iframe=5.0)
    tops = []; perf_out = []; kreq = []
    t_start = time.monotonic()
    try:
        w, h = sv.start(); r["size"] = f"{w}x{h}"
        time.sleep(1.0); gfx_reset(); g0 = time.monotonic()
        with lock: n0 = len(fr)
        th = None
        if sample:
            th = threading.Thread(target=lambda: tops.extend(top_threads()), daemon=True); time.sleep(1.0); th.start()
        if perf:
            perf_out.extend(simpleperf(4))
        for i in range(keys):
            time.sleep(1.0)
            if hasattr(sv, "request_key"): kreq.append(time.monotonic()); sv.request_key()
        t_end = g0 + secs
        while time.monotonic() < t_end: time.sleep(0.1)
        if th: th.join(timeout=30)
        with lock: n1 = len(fr); span = time.monotonic() - g0; f = list(fr)
        gf, gj = gfx_frames()
        r["fps"] = round((n1 - n0) / span, 1); r["app_fps"] = round(gf / span, 1) if gf >= 0 else None; r["app_jank"] = gj
        r["frames"] = len(f); r["first_s"] = round(f[0][0] - t_start, 2) if f else None
        r["kb_avg"] = round(sum(x[1] for x in f) / max(1, len(f)) / 1024, 1)
        if kreq:
            lat = []
            for tr in kreq:
                nk = next((x[0] for x in f if x[0] > tr and x[2]), None)
                lat.append(round((nk - tr) * 1000) if nk else None)
            r["key_ms"] = lat
    except Exception as e:
        r["err"] = repr(e)[:300]
    finally:
        _EXTRA["v"] = ""
        try: sv.stop()
        except Exception: pass
        if mv: mv.stop()
        if fh: fh.close()
    if record and r.get("frames"):
        r["probe"] = probe(record)
    r["log"] = [x for x in getattr(sv, "lines", []) if "stats" in x or "error" in x.lower() or "cbvideo:" in x][-8:]
    r["top"] = tops; r["perf"] = perf_out
    return r


SU = {}
def root_pre():
    """'' = adb shell đã là root · 'su 0 ' = chạy qua su · None = không có quyền root."""
    if "v" not in SU:
        _, o = sh("shell", "id", t=10)
        if "uid=0" in (o or ""): SU["v"] = ""
        else:
            _, o = sh("shell", "su 0 id", t=10)
            SU["v"] = "su 0 " if "uid=0" in (o or "") else None
    return SU["v"]


def simpleperf(dur=4):
    """simpleperf toàn máy (cpu-clock) → [dòng báo cáo]. Không có simpleperf / không có quyền root → báo lý do."""
    pre = root_pre()
    _, w = sh("shell", "which simpleperf || ls /system/bin/simpleperf", t=10)
    if "simpleperf" not in (w or ""): return ["(máy không có simpleperf)"]
    if pre is None: return ["(không có quyền root cho simpleperf -a)"]
    rc, o = sh("shell", f"{pre}simpleperf record -a -e cpu-clock -f 1000 --duration {dur} -o /data/local/tmp/cb.perf", t=dur + 40)
    if rc != 0: return [f"(simpleperf record lỗi: {(o or '').strip()[-300:]})"]
    out = []
    for srt, lim in (("comm,dso", "1"), ("dso,symbol", "0.6")):
        _, rep = sh("shell", f"{pre}simpleperf report -i /data/local/tmp/cb.perf --sort {srt} --percent-limit {lim}", t=60)
        ls = [x.rstrip() for x in (rep or "").splitlines() if x.strip()]
        k = next((i for i, x in enumerate(ls) if x.lstrip().startswith("Overhead")), 0)
        out += [f"--- sort {srt} ---"] + ls[k:k + 45]
    return out


def prof_main(ver, cores, encs):
    say(f"## Android 9: scrcpy vs cbvideo (máy chủ hình riêng) — Android {ver.strip()} (API {API}) · {cores.strip()} nhân · bộ nén {encs[0] if encs else '?'}")
    say("")
    res = []
    mv = Mover(); mv.start(); time.sleep(0.8); gfx_reset(); g0 = time.monotonic()
    time.sleep(5); gf, gj = gfx_frames(); span = time.monotonic() - g0; mv.stop()
    res.append({"tag": "KHÔNG phát hình (chỉ cuộn)", "size": "-", "fps": 0, "app_fps": round(gf / span, 1) if gf >= 0 else None, "app_jank": gj})
    have_cb = os.path.isfile(CB_JAR); have_lib = os.path.isfile(CB_LIB)
    tests = [dict(tag="scrcpy · 800 · max_fps 30 (như máy 4GB)", msz=800, fps=30, kbps=3000),
             dict(tag="scrcpy · 960 · 30", msz=960, fps=30, kbps=3000)]
    if have_cb:
        tests += [dict(tag="cbvideo OMX · 800 · 30", msz=800, fps=30, kbps=3000, cls=CbVideo)]
    if have_cb and have_lib:
        tests += [dict(tag="cbvideo openh264 · 800 · 30 · xin khoá ×3", msz=800, fps=30, kbps=3000, secs=7, cls=CbVideoN, keys=3, sample=True,
                       record=os.path.join(ROOT, f"cbn800-{API}.h264")),
                  dict(tag="cbvideo openh264 · 800 · 60", msz=800, fps=60, kbps=3000, cls=CbVideoN),
                  dict(tag="cbvideo openh264 · 960 · 30", msz=960, fps=30, kbps=3000, cls=CbVideoN, record=os.path.join(ROOT, f"cbn960-{API}.h264")),
                  dict(tag="cbvideo openh264 · 1280 · 30", msz=1280, fps=30, kbps=3000, cls=CbVideoN, record=os.path.join(ROOT, f"cbn1280-{API}.h264")),
                  dict(tag="cbvideo openh264 · đứng yên (khung đầu)", msz=800, fps=30, kbps=3000, secs=3, move=False, cls=CbVideoN),
                  dict(tag="cbvideo openh264 · 960 · 30 · simpleperf", msz=960, fps=30, kbps=3000, secs=7, perf=True, cls=CbVideoN)]
    elif have_cb:
        say("**Không có libcbenc.so** (bước dựng openh264 hỏng) — chỉ đo cbvideo OMX.")
        tests += [dict(tag="cbvideo OMX · 800 · 30 · xin khoá ×3", msz=800, fps=30, kbps=3000, secs=7, cls=CbVideo, keys=3,
                       record=os.path.join(ROOT, f"cb800-{API}.h264"))]
    else:
        say("**Không có cbvideo.jar** (bước dựng hỏng) — chỉ đo scrcpy.")
    for t in tests:
        r = prof(**t); res.append(r); time.sleep(1.0)
        print(json.dumps({k: v for k, v in r.items() if k not in ("top", "perf")}, ensure_ascii=False), flush=True)
    say("| lần đo | cỡ | khung/giây phát | app vẽ khung/giây | khung đầu (giây) | KB/khung | xin khoá → khung khoá (ms) | giải mã thử |")
    say("|---|---|---|---|---|---|---|---|")
    for r in res:
        if r.get("err"): say(f"| {r['tag']} | ✗ {r['err']} | | | | | | |"); continue
        pr = r.get("probe")
        pv = f"{pr[0]} · {pr[1]} khung · {pr[2]} lỗi" if pr else ""
        say(f"| {r['tag']} | {r.get('size', '?')} | {r.get('fps', '?')} | {r.get('app_fps', '?')} | {r.get('first_s', '')} | "
            f"{r.get('kb_avg', '')} | {r.get('key_ms', '')} | {pv} |")
    say("")
    for r in res:
        if r.get("log"): say(f"- nhật ký cbvideo · {r['tag']}: " + " ‖ ".join(r["log"]))
        pr = r.get("probe")
        if pr and pr[3]: say(f"- lỗi giải mã · {r['tag']}: " + " ‖ ".join(str(x) for x in pr[3]))
    say("")
    for r in res:
        if r.get("top"):
            say(f"<details open><summary>top -H · {r['tag']}</summary>\n\n```\n" + "\n".join(r["top"])[:5000] + "\n```\n</details>\n")
        if r.get("perf"):
            say(f"<details open><summary>simpleperf · {r['tag']}</summary>\n\n```\n" + "\n".join(r["perf"])[:15000] + "\n```\n</details>\n")
    # cbvideo đạt: dựng được + ra hình + giải mã sạch → bước sau lưu cbvideo.jar vào nhánh
    cb = next((r for r in res if "800 · 30 · xin" in r.get("tag", "") and r.get("tag", "").startswith("cbvideo")), None)
    ok = bool(cb and cb.get("probe") and cb["probe"][1] >= max(5, int(cb.get("frames", 0) * 0.9)) and cb["probe"][2] == 0 and not cb.get("err"))
    if ok and str(API) == "28":
        open(os.path.join(ROOT, "cbvideo-ok.txt"), "w").write(json.dumps({k: v for k, v in cb.items() if k not in ("top", "perf")}, ensure_ascii=False))
    say(f"- cbvideo giải mã sạch: **{'ĐẠT' if ok else 'CHƯA'}**")
    js = os.path.join(ROOT, f"a9stream-{API}.json")
    json.dump({"api": API, "encoders": encs, "prof": res}, open(js, "w"), ensure_ascii=False, indent=1)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as fh: fh.write("\n".join(OUT) + "\n")
    return 0


SERIAL = ""
def main():
    global SERIAL
    for _ in range(60):
        SERIAL = serial()
        if SERIAL: break
        time.sleep(2)
    if not SERIAL: print("không thấy máy ảo"); return 1
    bs.adb_ready(SERIAL, 30)
    sh("shell", "wm size 720x1280"); sh("shell", "wm density 320")
    sh("shell", "svc power stayon true; settings put system screen_off_timeout 2147483647; input keyevent 224; wm dismiss-keyguard")
    sh("shell", "am start -a android.settings.SETTINGS"); time.sleep(3)
    if not bs.ensure_jar(): print("không tải được scrcpy-server"); return 1
    bs.push_jar(SERIAL)
    _, ver = sh("shell", "getprop ro.build.version.release")
    _, cores = sh("shell", "cat /sys/devices/system/cpu/present")
    _, enc = sh("shell", f"CLASSPATH={bs.JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 list_encoders=true log_level=info", t=40)
    encs = re.findall(r"--video-codec=h264\s+--video-encoder='?([\w.\-]+)'?", enc or "")
    if os.environ.get("A9_MODE", "prof") == "prof": return prof_main(ver, cores, encs)
    say(f"## Phát hình scrcpy — Android {ver.strip()} (API {API}) · {cores.strip()} nhân · màn 720x1280")
    say(f"Bộ nén H.264 trong máy: **{', '.join(encs) or '?'}** (scrcpy dùng cái đầu)")
    say("")
    res = []
    tests = [("đứng yên 1280 · khoá 1", 1280, 30, 3000, 1.0, 4, False),
             ("cuộn 1280 · khoá 0,25 (A9 hiện tại)", 1280, 30, 3000, 0.25, 8, True),
             ("cuộn 1280 · khoá 1", 1280, 30, 3000, 1.0, 8, True),
             ("cuộn 960 · khoá 0,25", 960, 30, 3000, 0.25, 8, True),
             ("cuộn 960 · khoá 5", 960, 30, 3000, 5.0, 8, True),
             ("cuộn 800 · khoá 5", 800, 30, 3000, 5.0, 8, True)]
    for t in tests:
        r = capture(*t); res.append(r); time.sleep(1.0)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    rs = []
    for i in range(3):
        r = capture(f"bật lại #{i + 1}", 960, 30, 3000, 5.0, 2, False); rs.append(r); time.sleep(0.5)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    say("| lần đo | cỡ | khung/giây | khung | cờ khoá | IDR | I thường (không IDR) | KB: P / I / lớn nhất | khung đầu sau (giây) | khung nhiều lát | bỏ thiếu lát |")
    say("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in res + rs: say(row(r))
    say("")
    st = res[0]
    say(f"- Màn đứng yên 4 giây: {st.get('frames', 0)} khung → " + ("**có** lặp khung" if st.get("frames", 0) >= 8 else "**không** lặp khung"))
    a = res[1]
    if a.get("frames"):
        say(f"- Khoá 0,25 lúc cuộn: {a.get('i_all', 0)} khung I, trong đó IDR {a.get('idr', 0)}, có cờ khoá {a.get('flag', 0)} "
            + ("→ khung I định kỳ KHÔNG phải khung khoá với máy chủ (chỉ bật lại bộ nén mới có khung khoá)" if a.get("i_nonidr", 0) > 0 and a.get("i_nonidr_flag", 0) == 0
               else "→ khung I định kỳ có cờ khoá"))
    say(f"- Bật lại bộ nén → khung đầu: {', '.join(str(r.get('first_s', '?')) for r in rs)} giây")
    js = os.path.join(ROOT, f"a9stream-{API}.json")
    json.dump({"api": API, "encoders": encs, "tests": res, "restart": rs}, open(js, "w"), ensure_ascii=False, indent=1)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as fh: fh.write("\n".join(OUT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
