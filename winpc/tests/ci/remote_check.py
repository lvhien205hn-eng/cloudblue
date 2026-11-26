# -*- coding: utf-8 -*-
# =====================================================================================================
#  winpc/tests/ci/remote_check.py   —   thu tren WINDOWS THAT phan DIEU KHIEN TU XA (ban 21.11d):
#       pcremote: tai ffmpeg + kiem ma da ghim, do bo nen / cach quay, quay man hinh THAT + nen + ghep khung, SendInput (chuot, phim), bo nho copy
#       cbsys:    phien man hinh, khoa "dang chay", mo chuong trinh bang SYSTEM vao phien man hinh (qua 1 tac vu SYSTEM that)
#       dau-cuoi: may chu phat hinh (windows/bluestream.py + pcrelay.py, chay ngay trong tien trinh) <-> pcremote that <-> nguoi xem
#    python remote_check.py <thu muc cb cua bo cai, hoac thu muc winpc>  <thu muc tam>  [<goc kho ma - noi co windows/bluestream.py>]
#  In ra:  "OK  ..." / "XX  ..." / ".. ghi chu"   (check.ps1 doc lai).
#  Viec chi lam duoc khi may chay thu co man hinh that (phien nguoi dung) se ghi ".." neu may chay thu khong co, khong tinh la loi.
# =====================================================================================================
import hashlib, json, os, shutil, ssl, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
MODE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("--") else ""
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
root = os.path.abspath(ARGS[0]) if ARGS else os.path.join(HERE, "..", "..")
tmp = os.path.abspath(ARGS[1]) if len(ARGS) > 1 else os.path.join(root, "_remote_check_tmp")
repo = os.path.abspath(ARGS[2]) if len(ARGS) > 2 else os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for sub in ("lib", "agent"): sys.path.insert(0, os.path.join(root, sub))
import pcremote as R                                                # noqa: E402
import cbsys                                                        # noqa: E402

WIN = os.name == "nt"
N = {"ok": 0, "xx": 0}
C_HELLO, C_BYE, S_WELCOME = 0x01, 0x19, 0x81


def ck(name, cond, extra=""):
    if cond: N["ok"] += 1; print("OK  " + name, flush=True)
    else: N["xx"] += 1; print("XX  " + name + ("   -> " + str(extra)[:400] if extra != "" else ""), flush=True)


def note(s): print(".. " + str(s)[:500], flush=True)


def wait(fn, timeout=10.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(step)
    return fn()


def who():
    """(ten tai khoan, so phien cua tien trinh nay)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(256); n = ctypes.c_uint32(256)
    ctypes.WinDLL("advapi32").GetUserNameW(buf, ctypes.byref(n))
    k = ctypes.WinDLL("kernel32"); sid = ctypes.c_uint32(0)
    k.ProcessIdToSessionId(k.GetCurrentProcessId(), ctypes.byref(sid))
    return buf.value, int(sid.value)


def cursor():
    import ctypes
    from ctypes import wintypes
    p = wintypes.POINT()
    ok = ctypes.WinDLL("user32").GetCursorPos(ctypes.byref(p))
    return (p.x, p.y) if ok else None


def key_down(vk):
    import ctypes
    u = ctypes.WinDLL("user32"); u.GetAsyncKeyState.restype = ctypes.c_short
    return bool(u.GetAsyncKeyState(vk) & 0x8000)


def capture(ff, cap, secs=4.0, w=960, h=540, fps=15):
    """Quay man hinh that `secs` giay -> (so khung, khung dau la khung khoa co SPS/PPS, du lieu H.264, loi ffmpeg)."""
    io = R.WinIO() if WIN else R.NullIO()
    sw, sh = io.screen(); w, h = R.fit(sw, sh, max(w, h)); got = []
    e = R.Encoder(ff, cap, "x264", sw, sh, w, h, fps, 1000, lambda d, k, c, pts: got.append((d, k, c)))
    e.start(); t0 = time.time()
    while time.time() - t0 < secs and not e.exited(): time.sleep(0.1)
    time.sleep(0.3); e.stop(); time.sleep(0.3)
    fr = [g for g in got if g[0] is not None]
    return len(fr), bool(fr and fr[0][1] and fr[0][2]), b"".join(g[0] for g in fr), e.err, (sw, sh, w, h)


def decode_count(ff, data, path):
    """Giai ma lai bang ffmpeg -> (so khung giai ma duoc, do sang lon nhat cua khung dau)."""
    with open(path, "wb") as f: f.write(data)
    r = subprocess.run([ff, "-hide_banner", "-nostdin", "-i", path, "-map", "0:v", "-f", "null", "-"], capture_output=True, timeout=120, creationflags=0x08000000 if WIN else 0)
    txt = (r.stderr or b"").decode("utf-8", "replace")
    import re
    m = re.findall(r"frame=\s*(\d+)", txt)
    r2 = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", path, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=120,
                        creationflags=0x08000000 if WIN else 0)
    return (int(m[-1]) if m else 0), (max(r2.stdout) if r2.stdout else -1)


# ====================================================================================== che do phu: chay trong PHIEN MAN HINH bang SYSTEM (do --system mo)
if MODE == "--child":
    out = {"err": ""}
    try:
        out["user"], out["session"] = who()
        out["console"] = cbsys.console_session()
        io = R.WinIO(); out["screen"] = list(io.screen())
        io.move(20000, 30000); time.sleep(0.2); out["cursor"] = cursor()
        ff = ARGS[2] if len(ARGS) > 2 else ""
        if ff and os.path.isfile(ff):
            n, key, data, err, dims = capture(ff, "gdi", 3.0)
            out["frames"], out["key"], out["fferr"], out["dims"] = n, key, err, list(dims)
    except Exception as e:
        out["err"] = repr(e)
    with open(os.path.join(tmp, "child.json"), "w", encoding="utf-8") as f: json.dump(out, f)
    sys.exit(0)

# ====================================================================================== che do phu: tac vu SYSTEM (phien 0) mo chuong trinh con vao phien man hinh
if MODE == "--system":
    out = {"err": ""}
    try:
        out["user"], out["session"] = who()
        out["console"] = cbsys.console_session()
        ff = ARGS[2] if len(ARGS) > 2 else ""
        pid, sid = cbsys.spawn_console([sys.executable, "-I", "-B", os.path.abspath(__file__), "--child", root, tmp, ff], cwd=tmp)
        out["pid"], out["sid"] = pid, sid
    except Exception as e:
        out["err"] = repr(e)
    with open(os.path.join(tmp, "system.json"), "w", encoding="utf-8") as f: json.dump(out, f)
    sys.exit(0)

# ====================================================================================== chay chinh
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp)
note("pcremote %s, cbsys %s, Python %s tren %s" % (R.REMOTE_VER, cbsys.SYS_VER, sys.version.split()[0], sys.platform))

# ---- 1. tu thu + tai ffmpeg that (kiem 2 ma sha256 da ghim)
r = subprocess.run([sys.executable, "-I", "-B", os.path.join(root, "agent", "pcremote.py"), "selfcheck"], capture_output=True, timeout=120)
ck("pcremote.py selfcheck chay duoc bang Python cua bo cai", r.returncode == 0 and b"selfcheck ok" in r.stdout, (r.stdout + r.stderr)[-300:])
r = subprocess.run([sys.executable, "-I", "-B", os.path.join(root, "agent", "pcagent.py"), "selfcheck"], capture_output=True, timeout=180)
ck("pcagent.py selfcheck (kem ca pcremote) chay duoc", r.returncode == 0 and b"selfcheck ok" in r.stdout, (r.stdout + r.stderr)[-300:])
logs = []
base = os.path.join(tmp, "cbpc"); os.makedirs(base)
if not WIN:
    ff = shutil.which("ffmpeg")                                      # may khong phai Windows: chi chay thu phan dau-cuoi bang ffmpeg co san (hinh thu)
    note("KHONG phai Windows: bo qua tai ffmpeg.exe + moi phep thu chi-Windows ; ffmpeg co san: %s" % ff)
else:
    t0 = time.time()
    ff = R.ensure_ffmpeg(base, logs.append, cafile=os.path.join(root, "os", "cacert.pem"))
    dt = time.time() - t0
    ck("tai ffmpeg tu GitHub: file zip + ffmpeg.exe ben trong deu KHOP ma sha256 da ghim trong pcremote.py", bool(ff) and os.path.isfile(ff) and hashlib.sha256(open(ff, "rb").read()).hexdigest() == R.FF_EXE_SHA, logs[-3:])
    note("tai + kiem ffmpeg mat %.0f giay ; %s" % (dt, " | ".join(logs[-2:])))
    if ff:
        t0 = time.time(); ff2 = R.ensure_ffmpeg(base, logs.append)
        ck("lan sau dung lai ban da kiem (khong tai lai, < 3 giay)", ff2 == ff and time.time() - t0 < 3, time.time() - t0)
        r = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, timeout=60)
        ck("ffmpeg.exe chay duoc tren may nay (ban 6.1.1)", r.returncode == 0 and b"ffmpeg version 6.1.1" in r.stdout, r.stdout[:120])

# ---- 2. do bo nen + cach quay
caps = {"enc": [], "cap": "gdi"}
if ff:
    plog = []
    caps = R.probe(ff, plog.append, test=not WIN)
    ck("do bo nen: it nhat nen duoc bang CPU (x264)", "x264" in caps["enc"], (caps, plog))
    note("may chay thu: nen duoc bang %s ; quay man hinh kieu %s" % (", ".join(caps["enc"]) or "-", caps["cap"]))
    for x in plog: note("  " + x)

if WIN:
    me, my_sid = who(); con = cbsys.console_session()
    note("tai khoan chay thu: %s, phien %s ; phien man hinh dang hien: %s" % (me, my_sid, con))
    desk = (con is not None and con == my_sid)

    # ---- 3. chuot / phim / bo nho copy THAT
    io = R.WinIO()
    sw, sh = io.screen()
    ck("WinIO.screen: co man hinh hop ly", 320 <= sw <= 16384 and 200 <= sh <= 16384, (sw, sh))
    note("man hinh may chay thu: %dx%d" % (sw, sh))
    io.move(32768, 32768); time.sleep(0.2); c1 = cursor()
    io.move(10000, 50000); time.sleep(0.2); c2 = cursor()
    exp1, exp2 = (sw * 32768 // 65536, sh * 32768 // 65536), (sw * 10000 // 65536, sh * 50000 // 65536)
    near = lambda a, b: a is not None and abs(a[0] - b[0]) <= 3 and abs(a[1] - b[1]) <= 3
    if desk:
        ck("WinIO.move: con tro chuot toi dung diem (giua man hinh, roi goc duoi trai)", near(c1, exp1) and near(c2, exp2), (c1, exp1, c2, exp2))
        io.key(0xA1, True); time.sleep(0.1); d1 = key_down(0xA1); io.key(0xA1, False); time.sleep(0.1); d2 = key_down(0xA1)
        ck("WinIO.key: nhan phim Shift phai -> Windows thay phim dang giu ; nha -> het giu", d1 and not d2, (d1, d2))
        io.button(2, True); time.sleep(0.1); b1 = key_down(0x04); io.button(2, False); time.sleep(0.1); b2 = key_down(0x04)
        ck("WinIO.button: nut chuot giua nhan / nha", b1 and not b2, (b1, b2))
        k = R.Keys(io); k.key(0, 59, 0); time.sleep(0.1); h1 = key_down(0xA0); k.release_all(); time.sleep(0.1); h2 = key_down(0xA0)
        ck("dong phien: phim dang giu duoc NHA het (khong ket phim)", h1 and not h2, (h1, h2))
    else:
        note("BO QUA thu chuot / phim that: tien trinh chay thu khong nam trong phien man hinh (con tro: %s / %s)" % (c1, c2))
    try:
        io.wheel(120, False); io.wheel(-120, True); io.text("a"); io.key(0x08, True); io.key(0x08, False); io.awake(True); io.awake(False)
        ck("WinIO: lan chuot, go chu, giu may thuc - khong loi", True)
    except Exception as e:
        ck("WinIO: lan chuot, go chu, giu may thuc - khong loi", False, repr(e))
    txt = "CloudBlue thử bộ nhớ copy ✓ \U0001F600 dong 2\r\nxong"
    try:
        okc = io.clip_set(txt); got = io.clip_get()
        ck("bo nho copy: dat chu co dau + bieu tuong -> doc lai dung nguyen van", okc and got == txt, (okc, got))
        io.seq = io.u.GetClipboardSequenceNumber()
        ck("bo nho copy khong doi -> clip_poll tra None", io.clip_poll() is None)
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value 'tu chuong trinh khac'"], capture_output=True, timeout=60)
        got2 = wait(lambda: io.clip_poll(), 5)
        ck("chuong trinh khac copy chu moi -> clip_poll tra chu do (de gui cho nguoi xem)", got2 == "tu chuong trinh khac", got2)
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, timeout=60)
        io.clip_set("chu tu nguoi xem")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, timeout=60)
        ck("chu nguoi xem gui -> chuong trinh khac (PowerShell) doc duoc tu bo nho copy", b"chu tu nguoi xem" in r.stdout, r.stdout[:80])
    except Exception as e:
        ck("bo nho copy chay duoc", False, repr(e))

    # ---- 3b. 22.11b: o nhap chu dang duoc chon (app dien thoai tu bat ban phim) — ImeWatch: con tro chu (Win32) + UI Automation
    try:
        import ctypes
        from ctypes import wintypes as wt
        got = []
        w = R.ImeWatch(lambda v: got.append(v), note)
        time.sleep(1.5)
        ck("ImeWatch: chay that tren Windows, luong theo doi song, UI Automation tao duoc", w.th.is_alive() and w.uia is not None, (w.th.is_alive(), w.uia))
        stop_ev = threading.Event(); made = []

        def edit_window():
            u = ctypes.WinDLL("user32", use_last_error=True)
            u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HANDLE, wt.HANDLE, ctypes.c_void_p]
            u.CreateWindowExW.restype = wt.HWND
            u.SetForegroundWindow.argtypes = [wt.HWND]; u.SetFocus.argtypes = [wt.HWND]; u.DestroyWindow.argtypes = [wt.HWND]
            h = u.CreateWindowExW(0, "EDIT", "CloudBlue thu o nhap chu", 0x10CF0000, 120, 120, 420, 180, None, None, None, None)   # WS_OVERLAPPEDWINDOW | WS_VISIBLE
            io.key(0x12, True); io.key(0x12, False)                 # nhan Alt 1 lan: Windows cho chuong trinh nay dua cua so len truoc
            u.SetForegroundWindow(h); u.SetFocus(h); made.append(h)
            msg = wt.MSG()
            while not stop_ev.is_set():
                while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    u.TranslateMessage(ctypes.byref(msg)); u.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.02)
            u.DestroyWindow(h)
        tw = threading.Thread(target=edit_window, daemon=True); tw.start()
        wait(lambda: made, 5)
        fg_ok = bool(made) and wait(lambda: ctypes.WinDLL("user32").GetForegroundWindow() == made[0], 3)
        if desk and fg_ok:
            ck("ImeWatch: bam vao o nhap chu (EDIT, co con tro chu) -> bao ime = 1 trong ~1 giay", wait(lambda: got and got[-1] == (1, 0), 3), got)
            ole = ctypes.WinDLL("ole32"); ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]; ole.CoInitializeEx(None, 0)
            ck("ImeWatch UI Automation: phan tu dang chon la o nhap chu (Edit, khong chi doc) -> (1, 0)", w._uia_focus() == (1, 0), w._uia_focus())
        else:
            note("BO QUA thu o nhap chu that: khong dua duoc cua so thu len truoc (desk=%s, fg=%s)" % (desk, fg_ok))
            try: note("ImeWatch UI Automation (khong man hinh): %s" % (w._uia_focus(),))
            except Exception as e: ck("ImeWatch UI Automation goi duoc", False, repr(e))
        stop_ev.set(); tw.join(3); w.stop(); w.th.join(3)
        ck("ImeWatch: tat duoc (luong theo doi dung)", not w.th.is_alive(), w.th.is_alive())
    except Exception as e:
        ck("ImeWatch chay duoc", False, repr(e))

    # ---- 4. quay man hinh THAT + nen + ghep khung
    if ff:
        for cap in dict.fromkeys([caps["cap"], "gdi"]):
            try:
                n, key, data, err, dims = capture(ff, cap, 4.0)
            except Exception as e:
                n, key, data, err, dims = 0, False, b"", repr(e), ()
            if n == 0 and not desk:
                note("BO QUA quay kieu %s: may chay thu khong co man hinh de quay (%s)" % (cap, err[:160])); continue
            ck("quay man hinh that kieu %s + nen x264: ra hinh (>= 20 khung / 4 giay), khung dau la khung khoa co SPS/PPS" % cap, n >= 20 and key, (n, key, err, dims))
            if n:
                dn, lum = decode_count(ff, data, os.path.join(tmp, "cap-%s.h264" % cap))
                ck("  ... ffmpeg giai ma lai du %d khung (ghep goi RTP khong hong byte nao)" % n, dn == n, (dn, n))
                note("  quay %s: %d khung, man %sx%s -> hinh %sx%s, do sang lon nhat cua khung dau: %s%s" % (cap, n, dims[0], dims[1], dims[2], dims[3], lum, " (hinh den?)" if 0 <= lum < 16 else ""))

    # ---- 4b. 26.11a: may KHONG co card nen (VPS NVMe) - chuong trinh TU chup man hinh bang GDI, chi dua khung DOI cho ffmpeg (cach quay "pipe")
    try:
        cur_mode, ok_modes = io.modes()
        ck("26.11a WinIO.modes: doc duoc co man hinh dang dung + danh sach co may nay dat duoc (co dang dung nam trong danh sach)",
           cur_mode == (sw, sh) and cur_mode in ok_modes and len(ok_modes) >= 1, (cur_mode, sorted(ok_modes)[:12]))
        ck("26.11a WinIO.set_mode: dat lai DUNG co dang dung -> duoc (khong doi gi) ; co khong ton tai (123x45) -> tu choi, man hinh giu nguyen",
           io.set_mode(sw, sh) is True and io.set_mode(123, 45) is False and io.screen() == (sw, sh), io.screen())
        qm = R.is_qemu()
        ck("26.11a is_qemu: doc duoc bang BIOS cua Windows (may chay thu cua GitHub khong phai may ao QEMU -> False)", qm is False, qm)
        md = os.path.join(tmp, "mode"); os.makedirs(md, exist_ok=True)
        ck("26.11a vm_default_mode tren may KHONG phai may ao QEMU: khong dung vao co man hinh", R.vm_default_mode(io, "pc-ci", md, note) == "khong phai may ao" and io.screen() == (sw, sh))
        note("co man hinh may chay thu: %s ; dat duoc: %s" % (cur_mode, ", ".join("%dx%d" % m for m in sorted(ok_modes)[:14])))
    except Exception as e:
        ck("26.11a co man hinh (modes / set_mode / is_qemu) chay duoc", False, repr(e))
    if desk:
        try:
            g = io.grabber()
            b1, ch1 = g.grab()
            t0 = time.perf_counter(); n_same = 0
            for _ in range(20):
                b, ch = g.grab()
                if b is not None and not ch: n_same += 1
            ms = (time.perf_counter() - t0) / 20 * 1000
            ck("26.11a GdiGrab: chup duoc man hinh that (dung co %dx%d x 4 byte), khung dau tinh la 'doi'" % (sw, sh), b1 is not None and ch1 and len(b1) == sw * sh * 4 and (g.w, g.h) == (sw, sh), (ch1, b1 is not None))
            lum = max(bytes(b1[:: max(1, len(b1) // 50000)])) if b1 is not None else -1
            ck("26.11a GdiGrab: hinh chup KHONG den thui (co diem sang) ; man hinh dung yen -> phan lon lan chup bao 'khong doi' (%d / 20)" % n_same, lum > 24 and n_same >= 12, (lum, n_same))
            note("GdiGrab: 1 lan chup + ve con tro + so voi khung truoc = %.1f ms (man %dx%d, may chay thu khong co card hinh)" % (ms, sw, sh))
            io.move(9000, 9000); time.sleep(0.25); g.grab(); io.move(30000, 30000); time.sleep(0.25); b, ch = g.grab()
            ck("26.11a GdiGrab: re con tro chuot -> khung moi KHAC khung truoc (con tro duoc ve vao hinh)", b is not None and ch, ch)
            g.close()
            ck("26.11a GdiGrab: dong xong tao lai duoc (khong ro tai nguyen GDI)", all((lambda x: (x.grab()[0] is not None, x.close())[0])(io.grabber()) for _ in range(5)))
        except Exception as e:
            ck("26.11a GdiGrab chay duoc tren Windows that", False, repr(e))
        if ff:
            try:
                au = []
                e = R.Encoder(ff, "pipe", "x264", sw, sh, sw, sh, 20, 3000, lambda d, k, c, pts: au.append((time.time(), d, bool(k), bool(c))), note, grab_fn=io.grabber,
                              tune={"x264_preset": "ultrafast", "x264_extra": "partitions=i4x4", "crf": R.PIPE_CRF, "key_s": 2})
                e.start()
                ok1 = wait(lambda: au and au[0][2] and au[0][3], 20)
                ck("26.11a cach quay 'pipe' tren Windows that: ffmpeg nhan khung qua ong, khung dau la khung khoa co SPS/PPS", bool(ok1), (len(au), e.err))
                time.sleep(1.5); n0 = len(au); g0 = e.grabs; time.sleep(4.0)
                idle_n, idle_g = len(au) - n0, e.grabs - g0
                ck("26.11a 'pipe': man hinh dung yen 4 giay -> chi vai khung giu nhip (<= 30, cach cu la 80) va chi chup ~3 lan / giay (<= 22 lan)", idle_n <= 30 and idle_g <= 22, (idle_n, idle_g))
                lat = []
                for i in range(6):
                    time.sleep(0.5); n1 = len(au); io.move(8000 + i * 6000, 12000 + i * 5000); e.kick(); t1 = time.time()
                    if wait(lambda: len(au) > n1, 1.5, 0.004): lat.append(au[n1][0] - t1)
                ck("26.11a 'pipe': nguoi xem re chuot (kick) -> khung moi co con tro ra trong <= 0,4 giay (6 / 6 lan)", len(lat) == 6 and max(lat) <= 0.4, [round(x, 3) for x in lat])
                note("  'pipe': tu luc re chuot toi luc co khung nen: %s ms" % ", ".join("%d" % (x * 1000) for x in lat))
                n1 = len(au); t1 = time.time(); k = 0
                while time.time() - t1 < 3.0:
                    io.move(5000 + (k * 1500) % 50000, 20000 + (k * 900) % 30000); e.kick(); k += 1; time.sleep(0.03)
                time.sleep(0.3); mov = len(au) - n1
                ck("26.11a 'pipe': re chuot lien tuc 3 giay -> hinh chay theo (>= 25 khung), khong vuot nhip 20 khung / giay (<= 72)", 25 <= mov <= 72, mov)
                e.stop(); time.sleep(0.4)
                fr = [x for x in au if x[1] is not None]
                dn, lum2 = decode_count(ff, b"".join(x[1] for x in fr), os.path.join(tmp, "cap-pipe.h264"))
                ck("26.11a 'pipe': ffmpeg giai ma lai du %d khung, hinh khong den" % len(fr), dn == len(fr) and lum2 > 24, (dn, len(fr), lum2))
                note("  'pipe': tong %d khung / %d lan chup ; dung yen 4 giay: %d khung, %d lan chup ; loi: %s" % (len(fr), e.grabs, idle_n, idle_g, e.err or "-"))
            except Exception as ex:
                ck("26.11a cach quay 'pipe' chay duoc tren Windows that", False, repr(ex))
    else:
        note("BO QUA thu GdiGrab / cach quay 'pipe': tien trinh chay thu khong nam trong phien man hinh")

    # ---- 5. cbsys: phien man hinh, khoa "dang chay", mo vao phien man hinh
    ck("cbsys.console_session: tra so phien (hoac None khi may khong co man hinh)", con is None or isinstance(con, int), con)
    import ctypes
    kk = ctypes.WinDLL("kernel32", use_last_error=True)
    kk.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]; kk.CreateMutexW.restype = ctypes.c_void_p
    nm = "Global\\CloudBlueCheck%d" % os.getpid()
    m0 = cbsys.mutex_exists(nm); hm = kk.CreateMutexW(None, 0, nm); m1 = cbsys.mutex_exists(nm)
    ck("cbsys.mutex_exists: chua ai giu -> False ; co chuong trinh giu -> True", (m0 is False) and bool(hm) and (m1 is True), (m0, hm, m1))
    if me.upper() != "SYSTEM":
        try: cbsys.spawn_console(["cmd.exe", "/c", "exit 0"]); e1 = "KHONG LOI"
        except OSError as e: e1 = str(e)
        ck("cbsys.spawn_console: tai khoan KHONG phai SYSTEM goi -> tu choi ro rang (khong mo duoc chuong trinh vao phien khac)", "1314" in e1 or "chua co phien" in e1, e1)
    # tac vu SYSTEM that -> spawn_console -> chuong trinh con trong phien man hinh
    if con is None:
        note("BO QUA thu mo chuong trinh bang SYSTEM vao phien man hinh: may chay thu khong co phien man hinh nao")
    else:
        tn = "CBRemoteCheck%d" % os.getpid()
        wrap = os.path.join(tmp, "run-system.cmd")
        with open(wrap, "w", encoding="ascii") as f:
            f.write('@echo off\r\n"%s" -I -B "%s" --system "%s" "%s" "%s"\r\n' % (sys.executable, os.path.abspath(__file__), root, tmp, ff or ""))
        r1 = subprocess.run(["schtasks", "/Create", "/TN", tn, "/TR", wrap, "/SC", "ONCE", "/ST", "23:59", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"], capture_output=True, timeout=60)
        r2 = subprocess.run(["schtasks", "/Run", "/TN", tn], capture_output=True, timeout=60)
        sj = wait(lambda: os.path.isfile(os.path.join(tmp, "system.json")), 60, 0.5)
        try: sysj = json.load(open(os.path.join(tmp, "system.json"), encoding="utf-8")) if sj else {}
        except Exception: sysj = {}
        cj = wait(lambda: os.path.isfile(os.path.join(tmp, "child.json")), 90, 0.5) if sysj.get("pid") else False
        try: chj = json.load(open(os.path.join(tmp, "child.json"), encoding="utf-8")) if cj else {}
        except Exception: chj = {}
        subprocess.run(["schtasks", "/Delete", "/TN", tn, "/F"], capture_output=True, timeout=60)
        note("tac vu SYSTEM: %s ; chuong trinh con: %s" % (json.dumps(sysj)[:200], json.dumps(chj)[:300]))
        ck("tac vu SYSTEM (phien 0) goi cbsys.spawn_console -> mo duoc chuong trinh con", r1.returncode == 0 and r2.returncode == 0 and sysj.get("user", "").upper() == "SYSTEM"
           and sysj.get("session") == 0 and not sysj.get("err") and sysj.get("pid", 0) > 0, (r1.stdout + r1.stderr + r2.stderr, sysj))
        ck("chuong trinh con chay bang SYSTEM nhung nam TRONG phien man hinh dang hien", chj.get("user", "").upper() == "SYSTEM" and chj.get("session") == con and not chj.get("err"), chj)
        if chj and not chj.get("err"):
            exp = (chj["screen"][0] * 20000 // 65536, chj["screen"][1] * 30000 // 65536)
            ck("  ... tu trong phien man hinh: SYSTEM re duoc con tro chuot", chj.get("cursor") is not None and near(tuple(chj["cursor"]), exp), (chj.get("cursor"), exp))
            if ff: ck("  ... tu trong phien man hinh: SYSTEM quay duoc man hinh (>= 15 khung / 3 giay, khung dau la khung khoa)", chj.get("frames", 0) >= 15 and chj.get("key") is True, chj)

# ---- 6. DAU-CUOI tren may that: may chu phat hinh (trong tien trinh) <-> pcremote <-> nguoi xem
srv_dir = os.path.join(repo, "windows")
if not ff: note("BO QUA thu dau-cuoi: chua co ffmpeg")
elif not (os.path.isfile(os.path.join(srv_dir, "bluestream.py")) and os.path.isfile(os.path.join(srv_dir, "pcrelay.py"))):
    note("BO QUA thu dau-cuoi: khong thay windows/bluestream.py + pcrelay.py o %s" % srv_dir)
else:
    import asyncio, importlib
    sd = os.path.join(tmp, "srv"); os.makedirs(sd)
    for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(srv_dir, f), os.path.join(sd, f))
    with open(os.path.join(sd, "cloudphone.conf"), "w") as f: f.write("NODE_ID=citest\n")
    sys.path.insert(0, sd); old_argv = sys.argv; sys.argv = ["bluestream.py", "--selftest"]
    slog = []
    try:
        H = importlib.import_module("bluestream")
        H.log = lambda *a: slog.append(" ".join(str(x) for x in a))
        imp_err = ""
    except Exception as e:
        H = None; imp_err = repr(e)
    sys.argv = old_argv
    ck("windows/bluestream.py + pcrelay.py nap duoc tren Windows that, tram may PC BAT", H is not None and H.PCRELAY is not None and H.SELFTEST, imp_err or getattr(H, "PCRELAY_ERR", ""))
    if H is not None and H.PCRELAY is not None:
        loop = asyncio.new_event_loop()

        async def boot():
            s = await asyncio.start_server(H.on_ws, "127.0.0.1", 0, limit=1 << 20)      # cong noi bo (nhu cloudflared chuyen vao): WebSocket khong TLS
            return s.sockets[0].getsockname()[1]
        wsport = loop.run_until_complete(boot())
        threading.Thread(target=loop.run_forever, daemon=True).start()
        url = "ws://127.0.0.1:%d/v2/stream" % wsport
        real_connect = R.connect
        R.connect = lambda stream, cafile=None, log=None: R.WSConn(url, 3.0, plain=True)
        plog = []
        io = R.WinIO(plog.append) if WIN else R.NullIO()
        cap0 = caps["cap"] if WIN else "test"
        PC = "11111111-1111-4111-8111-111111111111"
        rm = R.Remote(lambda: {"id": PC, "token": "tok-ci"}, lambda fn, body: {"ok": True, "on": True, "node": "citest", "stream": {}}, io, lambda: ff, plog.append, None,
                      caps={"enc": ["x264"], "cap": cap0})
        rm.sleep = lambda s: time.sleep(min(s, 0.3))
        threading.Thread(target=rm.run, daemon=True).start()
        ck("dau-cuoi: may PC vao duoc tram (R_OK), cho nguoi xem", wait(lambda: "cho nguoi xem" in rm.state, 10), (rm.state, plog[-3:], slog[-3:]))
        vc = R.WSConn(url, 3.0, plain=True)
        rx = []; lock = threading.Lock(); alive = [True]

        def vloop():
            try:
                while True:
                    t, p = vc.recv()
                    if t == R.S_VIDEO: vc.send(R.C_ACK, p[1:9])
                    with lock: rx.append((t, p))
            except Exception:
                alive[0] = False

        def vping():
            while alive[0]:
                try: vc.send(R.C_PING, struct.pack(">Q", int(time.time() * 1000)))
                except Exception: return
                time.sleep(2)
        vc.send(C_HELLO, json.dumps({"v": 2, "token": "t", "pc": PC, "client": "ci", "q": "eco", "fps": 15}).encode())
        threading.Thread(target=vloop, daemon=True).start(); threading.Thread(target=vping, daemon=True).start()

        def take(t, timeout=15):
            def f():
                with lock:
                    for i, m in enumerate(rx):
                        if m[0] == t: return rx.pop(i)
                return None
            return wait(f, timeout)

        def count(t):
            with lock: return sum(1 for m in rx if m[0] == t)
        m = take(S_WELCOME, 25)
        wel = json.loads(m[1]) if m else {}
        scr = io.screen(); expw = R.fit(scr[0], scr[1], 1280)
        ck("dau-cuoi: nguoi xem nhan WELCOME cua may PC that (kind = pc, co hinh dung ti le man hinh)", wel.get("ok") is True and wel.get("kind") == "pc" and (wel.get("w"), wel.get("h")) == expw,
           (wel, expw, rx[:2], plog[-4:], slog[-4:]))
        wig = [True]

        def wiggle():                                               # 26.11a: may chay thu chi nen duoc bang CPU -> cach quay "pipe" chi gui khung khi man hinh DOI -> re chuot cho co thay doi
            k = 0
            while wig[0] and k < 400:
                try: vc.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 6000 + (k * 1700) % 50000, 9000 + (k * 1100) % 40000))
                except Exception: return
                k += 1; time.sleep(0.05)
        if WIN: threading.Thread(target=wiggle, daemon=True).start()
        got_video = wait(lambda: count(R.S_VIDEO) >= 25, 20)
        wig[0] = False; time.sleep(0.3)
        s0 = rm.sess
        if WIN and s0 is not None and s0.enc is not None:
            ck("26.11a dau-cuoi: may chi nen duoc bang CPU -> phien dung cach quay 'pipe' (tu chup, chi nen khung doi), gop duoc lenh re chuot don neu co",
               s0.enc.cap == "pipe" and s0.long_gop and s0.skip >= 0, (s0.enc.cap, s0.long_gop, s0.skip, plog[-3:]))
        if not got_video and WIN and not (cbsys.console_session() is not None and cbsys.console_session() == who()[1]):
            note("BO QUA phan hinh dau-cuoi: may chay thu khong co man hinh de quay (%d khung) %s" % (count(R.S_VIDEO), plog[-3:]))
        else:
            ck("dau-cuoi: hinh man hinh THAT toi nguoi xem (>= 25 khung)", got_video, (count(R.S_VIDEO), plog[-4:]))
            with lock: fr = [x[1] for x in rx if x[0] == R.S_VIDEO]
            if fr:
                dn, lum = decode_count(ff, b"".join(x[9:] for x in fr), os.path.join(tmp, "e2e.h264"))
                ck("dau-cuoi: khung dau la khung khoa ; ffmpeg giai ma lai du so khung nguoi xem nhan", fr[0][0] & 3 == 3 and dn == len(fr), (fr[0][0], dn, len(fr)))
                note("dau-cuoi: nguoi xem nhan %d khung %sx%s (do sang lon nhat khung dau %s)" % (len(fr), wel.get("w"), wel.get("h"), lum))
        if WIN and cbsys.console_session() is not None and cbsys.console_session() == who()[1]:
            vc.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 40000, 20000)); time.sleep(0.6)
            c3 = cursor(); exp3 = (scr[0] * 40000 // 65536, scr[1] * 20000 // 65536)
            ck("dau-cuoi: nguoi xem re chuot -> con tro tren may PC that toi dung diem", c3 is not None and abs(c3[0] - exp3[0]) <= 3 and abs(c3[1] - exp3[1]) <= 3, (c3, exp3))
            vc.send(R.C_CLIP, b"\x00chu dan tu nguoi xem (dau-cuoi)"); time.sleep(0.8)
            ck("dau-cuoi: nguoi xem gui chu -> nam trong bo nho copy cua may PC", io.clip_get() == "chu dan tu nguoi xem (dau-cuoi)", io.clip_get())
            subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value 'copy tren may PC'"], capture_output=True, timeout=60)
            m = take(R.S_CLIP, 8)
            ck("dau-cuoi: copy chu tren may PC -> nguoi xem nhan duoc", m is not None and m[1] == b"copy tren may PC", m)
            # ---- 23.11b: DAN nhu khach that (app / web: khach GIU Ctrl -> phim Ctrl sang may, phim V doi thanh goi Dan): o EDIT · CMD · PowerShell
            try:
                import ctypes
                from ctypes import wintypes as wt
                u32 = ctypes.WinDLL("user32", use_last_error=True)
                u32.SetForegroundWindow.argtypes = [wt.HWND]; u32.GetForegroundWindow.restype = wt.HWND
                u32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]; u32.SendMessageW.restype = ctypes.c_ssize_t
                u32.GetAsyncKeyState.argtypes = [ctypes.c_int]; u32.GetAsyncKeyState.restype = ctypes.c_short
                u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]; u32.IsWindowVisible.argtypes = [wt.HWND]
                ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

                def find_title(sub):
                    hit = []

                    def cb(h, _):
                        b = ctypes.create_unicode_buffer(512); u32.GetWindowTextW(h, b, 512)
                        if sub in b.value and u32.IsWindowVisible(h): hit.append(h)
                        return True
                    u32.EnumWindows(ENUM(cb), 0)
                    return hit[0] if hit else None

                def front(h):
                    for _ in range(4):
                        io.key(0x12, True); io.key(0x12, False)          # Alt 1 lan: Windows cho chuong trinh nay dua cua so len truoc
                        u32.SetForegroundWindow(h)
                        if wait(lambda: u32.GetForegroundWindow() == h, 2): return True
                    return False

                def guest_paste(s, mode=1):
                    vc.send(R.C_KEY, struct.pack(">BII", 0, 113, 0)); time.sleep(0.15)          # khach giu Ctrl (Ctrl trai)
                    vc.send(R.C_CLIP, bytes([mode]) + s.encode("utf-8")); time.sleep(1.2)
                    vc.send(R.C_KEY, struct.pack(">BII", 1, 113, 0)); time.sleep(0.5)

                def enter():
                    vc.send(R.C_KEY, struct.pack(">BII", 0, 66, 0)); time.sleep(0.08); vc.send(R.C_KEY, struct.pack(">BII", 1, 66, 0))
                stop2 = threading.Event(); eh = []

                def edit_win():
                    u = ctypes.WinDLL("user32", use_last_error=True)
                    u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HANDLE, wt.HANDLE, ctypes.c_void_p]
                    u.CreateWindowExW.restype = wt.HWND; u.SetFocus.argtypes = [wt.HWND]; u.DestroyWindow.argtypes = [wt.HWND]
                    h = u.CreateWindowExW(0, "EDIT", "", 0x10CF0004, 140, 140, 560, 240, None, None, None, None)   # WS_OVERLAPPEDWINDOW | WS_VISIBLE | ES_MULTILINE
                    eh.append(h); msg = wt.MSG()
                    while not stop2.is_set():
                        while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            u.TranslateMessage(ctypes.byref(msg)); u.DispatchMessageW(ctypes.byref(msg))
                        time.sleep(0.02)
                    u.DestroyWindow(h)
                threading.Thread(target=edit_win, daemon=True).start()
                if wait(lambda: eh, 5) and front(eh[0]):
                    txt = "dán vào ô chữ · Tiếng Việt 23.11b"
                    guest_paste(txt)
                    buf = ctypes.create_unicode_buffer(4096); u32.SendMessageW(eh[0], 0x000D, 4096, ctypes.cast(buf, ctypes.c_void_p))
                    ck("23.11b dau-cuoi: khach giu Ctrl + Dan -> chu (co dau) vao o EDIT dung 1 lan", buf.value == txt, buf.value)
                    ck("23.11b dau-cuoi: dan xong + khach nha Ctrl -> may khong ket phim Ctrl", not (u32.GetAsyncKeyState(0x11) & 0x8000))
                else:
                    note("BO QUA thu dan vao o EDIT: khong dua duoc cua so thu len truoc")
                stop2.set()
                for name, argv, title, cmd, want in (
                        ("CMD (conhost)", ["cmd.exe", "/k", "title CBDANCMD"], "CBDANCMD", 'echo CB-DAN-CMD> "%s"', "CB-DAN-CMD"),
                        ("PowerShell (PSReadLine)", ["powershell.exe", "-NoLogo", "-NoProfile", "-NoExit", "-Command", "$Host.UI.RawUI.WindowTitle = 'CBDANPS'"], "CBDANPS",
                         "Set-Content -LiteralPath '%s' -Value 'CB-DAN-PS Tiếng Việt' -Encoding UTF8", "CB-DAN-PS Tiếng Việt")):
                    fout = os.path.join(tmp, "cbdan-%s.txt" % title.lower())
                    pr = subprocess.Popen(argv, creationflags=0x10)                     # CREATE_NEW_CONSOLE: cua so dong lenh that
                    try:
                        h = wait(lambda: find_title(title), 20)
                        time.sleep(2.0)
                        if h and front(h):
                            guest_paste(cmd % fout); enter()
                            got = wait(lambda: os.path.isfile(fout) and open(fout, "rb").read(), 10)
                            val = got.decode("utf-8-sig", "replace").strip() if got else None
                            ck("23.11b dau-cuoi: khach dan lenh vao %s (giu Ctrl + Dan) + Enter -> lenh chay dung chu" % name, val == want, (val, plog[-3:]))
                        else:
                            note("BO QUA thu dan vao %s: khong thay / khong dua duoc cua so len truoc (%s)" % (name, h))
                    finally:
                        pr.kill()
            except Exception as e:
                ck("23.11b dau-cuoi: thu dan chay duoc", False, repr(e))
        enc = wait(lambda: (rm.sess.enc if rm.sess is not None else None), 3)
        vc.send(C_BYE)
        ck("dau-cuoi: nguoi xem dong -> may PC tat ffmpeg (khong ai xem thi khong ton may)", wait(lambda: rm.sess is None and (enc is None or enc.exited()), 8), (rm.sess, plog[-3:]))
        rm.stop = True
        if rm.conn is not None: rm.conn.close()
        R.connect = real_connect
        time.sleep(0.5)
        ck("dau-cuoi: nhat ky may chu khong co loi phien", not any("Traceback" in x or "lỗi phiên" in x for x in slog), [x for x in slog if "Traceback" in x or "lỗi phiên" in x][:2])
        for x in plog[-6:]: note("  may PC: " + x)

note("xong remote_check: %d OK, %d XX" % (N["ok"], N["xx"]))
sys.exit(0)
