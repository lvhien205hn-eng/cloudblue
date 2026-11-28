# -*- coding: utf-8 -*-
"""27/11e — kiểm logic phát hình ANDROID 9 mới của windows/bluestream.py (không cần máy Android):
     python3 .github/a9-check/test_a9logic.py
   1. cỡ hình: Android 9 ≤ 960 ở Tiết kiệm / Cân bằng / Tự động, mức Nét giữ nguyên; máy khác không đổi
   2. khung I Android 9 thưa (5), máy khác như cũ
   3. "app chậm": Android 9 chịu gấp đôi trước khi bỏ khung; máy khác như cũ; đếm lý do bỏ khung
   4. hàng chờ: Android 9 chịu 0,5 giây; máy khác 0,15 giây
   5. bỏ khung → bật lại bộ nén sau ~0,2 giây (Android 9), máy khác không tự bật lại
   6. không dumpsys "màn ảo" sau cú bấm ở Android 9; máy khác vẫn có
   7. Thông số gửi app / web có efps, rs, rk, dr
   8. (27/11f) cbvideo: lệnh chạy, xin khung khoá, ngưỡng bỏ khung, chọn / quay về scrcpy, chế độ thử ?cbv=1, md5 ghim"""
import asyncio, importlib.util, json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location("bluestream", os.path.join(ROOT, "windows", "bluestream.py"))
bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)
SRC_TXT = open(os.path.join(ROOT, "windows", "bluestream.py"), encoding="utf-8").read()
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:400])


class Link:
    kind = "ws"; closed = False
    def __init__(self, kind="ws"): self.kind = kind; self.out = []
    def dead(self): return False
    async def send(self, t, payload=b"", timeout=5.0): self.out.append((t, payload))
    def send_nowait(self, t, payload=b""): self.out.append((t, payload))


class Src:
    cw, ch = 720, 1280; closed = False
    def resized(self): return False


def mk(android, q="bal", kind="ws", adm=True):
    phone = {"id": "p" + android + q + kind, "container": "cp_test", "port": 5555, "android": android, "fps": 30}
    s = bs.Session(Link(kind), {"uid": "u" * 8, "admin": adm}, phone, {"q": q}, time.monotonic())   # 28/11a: thông số kỹ thuật chỉ gửi cho admin
    s.src = Src()
    return s


async def main():
    print("1. cỡ hình")
    for android, q, want in (("9", "bal", (536, 960)), ("9", "auto", (536, 960)), ("9", "eco", (536, 960)), ("9", "hd", (720, 1280)),
                             ("12", "bal", (720, 1280)), ("15", "auto", (720, 1280))):
        s = mk(android, q); ow, oh, fps, kbps = s._dims()
        ck(f"Android {android} · {q} → {want[0]}x{want[1]}", (ow, oh) == want, (ow, oh, fps, kbps))
    s = mk("9", "bal"); ow, oh, _, _ = s._dims()
    ck("… scrcpy ra 544x960 (2 cạnh chia hết 16)", bs._scr_out(720, 1280, bs._scr_max(720, 1280, max(ow, oh))) == (544, 960),
       bs._scr_out(720, 1280, bs._scr_max(720, 1280, max(ow, oh))))
    ck("mặc định conf: A9_MAXH 960 · LAG ×2 · hàng chờ 0,5 · khung I 5 · chờ khoá 0,2",
       (bs.A9_MAXH, bs.A9_LAG_MUL, bs.A9_QWAIT, bs.SCR_IFRAME_A9, bs.KEY_WAIT_S_A9) == (960, 2.0, 0.5, 5.0, 0.2),
       (bs.A9_MAXH, bs.A9_LAG_MUL, bs.A9_QWAIT, bs.SCR_IFRAME_A9, bs.KEY_WAIT_S_A9))

    print("2. khung I")
    ck("Android 9 → khung I mỗi 5 (scrcpy: 300 khung)", mk("9")._iframe(30, 3000) == 5.0, mk("9")._iframe(30, 3000))
    s12 = mk("12"); exp = max(0.1, min(5.0, bs.SCR_KEY_S * bs.key_every(3000) * 30 / 60.0))
    ck("Android 12 → như cũ", s12._iframe(30, 3000) == exp, (s12._iframe(30, 3000), exp))

    print("3. app báo nhận chậm")
    async def lag_case(android, behind_s, kind="ws"):
        s = mk(android, kind=kind); s.wait_key = False; s.ack_pts = 1; s.ack_t = time.time(); s.base_ms = 0.0
        s.inflight.append((1, 1000, time.time() - behind_s)); s.key_grace = 0.0
        await s._consider((s.gen, b"\x00\x00\x00\x01\x41\x9a", False, False, 2, time.monotonic()))
        return s
    s = await lag_case("9", 1.0)
    ck("Android 9, đường vòng, chậm 1,0 giây → VẪN gửi (ngưỡng 1,4 giây)", s.drop == 0 and any(t == bs.S_VIDEO for t, _ in s.link.out), (s.drop, s.dr))
    s = await lag_case("12", 1.0)
    ck("Android 12, đường vòng, chậm 1,0 giây → bỏ khung như cũ (ngưỡng 0,7) + đếm lý do 'lag'", s.drop == 1 and (s.dr or {}).get("lag") == 1, (s.drop, s.dr))
    s = await lag_case("9", 1.6)
    ck("Android 9 chậm 1,6 giây → bỏ khung, chờ khung khoá", s.drop == 1 and s.wait_key and (s.dr or {}).get("lag") == 1, (s.drop, s.wait_key, s.dr))
    s = await lag_case("9", 0.5, kind="direct")
    ck("Android 9, đường thẳng, chậm 0,5 giây → vẫn gửi (ngưỡng 0,7)", s.drop == 0, (s.drop, s.dr))
    s = await lag_case("12", 0.5, kind="direct")
    ck("Android 12, đường thẳng, chậm 0,5 giây → bỏ (ngưỡng 0,35)", s.drop == 1, (s.drop, s.dr))
    s = mk("9"); s.wait_key = True
    await s._consider((s.gen, b"\x00\x00\x00\x01\x41\x9a", False, False, 2, time.monotonic()))
    await s._consider((s.gen, None, False, False, 3, time.monotonic()))
    ck("đếm 'chờ khoá' (wk) + 'thiếu lát' (cut)", (s.dr or {}).get("wk") == 1 and (s.dr or {}).get("cut") == 1, s.dr)

    print("4. hàng chờ gửi")
    async def queue_case(android, age_s):
        s = mk(android); s.wait_key = False
        t = time.monotonic() - age_s
        for i in range(3): s.aq.put_nowait((s.gen, b"\x00\x00\x00\x01\x41\x9a", False, False, 10 + i, t))
        task = asyncio.ensure_future(s._sender()); await asyncio.sleep(0.05); s.closed = True; task.cancel()
        try: await task
        except BaseException: pass
        return s
    s = await queue_case("9", 0.3)
    ck("Android 9: 3 khung chờ 0,3 giây → gửi cả 3", s.drop == 0 and s.sent == 3, (s.drop, s.sent, s.dr))
    s = await queue_case("12", 0.3)
    ck("Android 12: 3 khung chờ 0,3 giây → bỏ cả 3 như cũ (đếm 'q')", s.drop == 3 and (s.dr or {}).get("q") == 3, (s.drop, s.sent, s.dr))
    s = await queue_case("9", 0.8)
    ck("Android 9: chờ 0,8 giây → bỏ (nghẽn thật)", s.drop == 3 and (s.dr or {}).get("q") == 3, (s.drop, s.sent, s.dr))

    print("5. bỏ khung → bật lại bộ nén (vòng canh phiên)")
    async def keyfix(android, secs=1.2):
        s = mk(android); s.sent = 5; s.wait_key = True; s.last_restart = time.time() - 10; s.last_rx = time.time() + 60
        s.t_auth = time.time() + 3600
        class Enc:
            enc = "scrcpy"; proc = None; frames_in = 0; fps = 30
            def failed_early(self): return False
        s.enc = Enc(); hits = []
        async def fake_restart(size_msg=False, cpu=False): hits.append((time.time(), s.restart_req)); s.wait_key = False; s.last_restart = time.time()
        s.restart_video = fake_restart
        s._early_down = lambda now: False; s._may_raise = lambda now: False
        t0 = time.time(); task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(secs); s.closed = True
        try: await asyncio.wait_for(task, 2)
        except BaseException: pass
        return s, hits, t0
    s, hits, t0 = await keyfix("9")
    ck("Android 9: đang chờ khung khoá → bật lại bộ nén trong ≤ 0,8 giây, đếm rk", bool(hits) and hits[0][0] - t0 <= 0.8 and s.n_keyfix == 1,
       ([round(h[0] - t0, 2) for h in hits], s.n_keyfix))
    s, hits, t0 = await keyfix("12")
    ck("Android 12: KHÔNG tự bật lại (chờ khung khoá thật của bộ nén)", not hits and s.n_keyfix == 0, hits)

    print("6. canh màn ảo sau cú bấm")
    c9 = bs.Control("127.0.0.1:1", None, dfix=False); c9._dfix_soon()
    ck("Control Android 9 (dfix=False): bấm xong KHÔNG chạy dumpsys", c9.dfix_busy is False, c9.dfix_busy)
    c12 = bs.Control("127.0.0.1:1", None); c12._dfix_soon(); c12.dead = True      # dead sau khi hẹn → luồng ngủ xong thì thôi (không gọi adb)
    ck("Control máy khác: vẫn hẹn kiểm màn ảo như cũ", c12.dfix_busy is True or not bs.DISPLAY_FIX, c12.dfix_busy)
    ck("phiên tạo Control với dfix=not a9 (cả 2 chỗ)", SRC_TXT.count("Control(self.serial, self._on_clip, dfix=not") == 2)

    print("7. thông số gửi app / web")
    s = mk("9"); s._dropx("lag"); s._dropx("q", 2); s.n_in = 30; s.n_restart = 2; s.n_keyfix = 1
    class Enc2:
        enc = "scrcpy"; proc = None; frames_in = 0
        def failed_early(self): return False
    s.enc = Enc2(); s.last_rx = time.time() + 60; s.t_auth = time.time() + 3600; s.last_restart = time.time()
    s._early_down = lambda now: False; s._may_raise = lambda now: False; s.wait_key = False
    task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(0.1); s.n_in = 60; await asyncio.sleep(2.2); s.closed = True
    try: await asyncio.wait_for(task, 2)
    except BaseException: pass
    st = [json.loads(p) for t, p in s.link.out if t == bs.S_STATS]
    ck("S_STATS có efps / rs / rk / dr / a9", bool(st) and all(k in st[-1] for k in ("efps", "rs", "rk", "dr", "a9")) and st[-1]["dr"] == {"lag": 1, "q": 2}
       and st[-1]["rs"] == 2 and st[-1]["rk"] == 1 and st[-1]["efps"] > 0, st[-1:] if st else None)
    ck("28/11a: phiên admin → S_STATS có enc 'scrcpy' + ctl", bool(st) and st[-1].get("enc") == "scrcpy" and "ctl" in st[-1], st[-1:] if st else None)
    s = mk("9", adm=False); s._dropx("lag"); s.n_in = 30; s.n_restart = 2; s.n_keyfix = 1
    s.enc = Enc2(); s.last_rx = time.time() + 60; s.t_auth = time.time() + 3600; s.last_restart = time.time()
    s._early_down = lambda now: False; s._may_raise = lambda now: False; s.wait_key = False
    task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(0.1); s.n_in = 60; await asyncio.sleep(2.2); s.closed = True
    try: await asyncio.wait_for(task, 2)
    except BaseException: pass
    st = [json.loads(p) for t, p in s.link.out if t == bs.S_STATS]
    ck("28/11a: phiên KHÁCH → S_STATS không có bộ nén / cách điều khiển / efps rs rk dr a9 kq cbs (vẫn có fps, kbps)",
       bool(st) and st[-1].get("enc") == "" and not any(k in st[-1] for k in ("ctl", "efps", "rs", "rk", "dr", "a9", "kq", "cbs"))
       and "fps" in st[-1] and "kbps" in st[-1], st[-1:] if st else None)
    ck("28/11a: _enc_name() khách = '' · admin = tên bộ nén", s._enc_name() == "" and mk("9")._enc_name() == "", (s._enc_name(),))
    ck("28/11a: lỗi không lấy được hình không còn chữ 'cửa sổ' (lộ cách lấy hình)", "từ cửa sổ máy" not in bs.MSG_NOWIN and "Máy chủ chưa lấy được hình" in bs.MSG_NOWIN
       and 'Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy' not in SRC_TXT and SRC_TXT.count('Deny("OFFLINE", MSG_NOWIN)') == 3)

    print("8. cbvideo (27/11f) — máy chủ hình riêng cho Android 9")
    ck("bản 28/11a + dòng khởi động 'bản 28/11a: ẩn thông số kỹ thuật với khách' (vẫn giữ dòng 'bản 27/11h: Android 9 cbvideo')",
       bs.BS_SUB == "28/11a" and "bản 28/11a: ẩn thông số kỹ thuật với khách" in SRC_TXT and "bản 27/11h: Android 9 cbvideo" in SRC_TXT, bs.BS_SUB)
    ck("md5 libcbenc-x86_64.so (openh264) ghim đủ 32 ký tự hex · mặc định nén openh264 1 luồng",
       len(bs.CBV_LIB[1]) == 32 and all(c in "0123456789abcdef" for c in bs.CBV_LIB[1]) and bs.CBV_ENC == "oh264" and bs.CBV_THREADS == 1, (bs.CBV_LIB, bs.CBV_ENC))
    ck("md5 cbvideo.jar ghim đủ 32 ký tự hex", len(bs.CBV_FILE[1]) == 32 and all(c in "0123456789abcdef" for c in bs.CBV_FILE[1]), bs.CBV_FILE)
    sv = bs.ScrcpyVideo("127.0.0.1:1", 960, 30, 3000, lambda *a: None, iframe=5.0, kind="cbv")
    sv2 = bs.ScrcpyVideo("127.0.0.1:1", 960, 30, 3000, lambda *a: None, iframe=5.0)
    ck("ScrcpyVideo kind=cbv → enc 'cbvideo' · mặc định vẫn scrcpy", (sv.enc, sv.kind, sv2.enc, sv2.kind) == ("cbvideo", "cbv", "scrcpy", "scrcpy"),
       (sv.enc, sv.kind, sv2.enc, sv2.kind))
    class FakeSock:
        def __init__(self): self.sent = b""
        def sendall(self, b): self.sent += b
    sv.sock = FakeSock(); sv2.sock = FakeSock()
    ck("request_key: cbvideo gửi 1 byte 'K' · scrcpy không gửi gì", sv.request_key() is True and sv.sock.sent == b"K"
       and sv2.request_key() is False and sv2.sock.sent == b"", (sv.sock.sent, sv2.sock.sent))
    cmds = []
    class StopPop(Exception): pass
    real_pop = bs.subprocess.Popen; real_lib = bs.ensure_cbv_lib
    def fake_pop(args, *a, **k): cmds.append(args); raise StopPop()
    bs.subprocess.Popen = fake_pop
    try:
        for kd, lib in (("cbv", True), ("scrcpy", True), ("cbv", False)):
            bs.ensure_cbv_lib = (lambda v: (lambda: v))(lib)
            v = bs.ScrcpyVideo("127.0.0.1:1", 960, 30, 3000, lambda *a: None, iframe=5.0, quick=True, kind=kd)
            try: v.start()
            except StopPop: pass
    finally:
        bs.subprocess.Popen = real_pop; bs.ensure_cbv_lib = real_lib
    c_cb = cmds[0][-1] if cmds else ""; c_sc = cmds[1][-1] if len(cmds) > 1 else ""; c_omx = cmds[2][-1] if len(cmds) > 2 else ""
    ck("27/11h: có libcbenc → lệnh cbvideo kèm lib=<libcbenc> enc_threads=1 · không có → không kèm (nén bằng Android)",
       f"lib={bs.CBV_LIB_DEV}" in c_cb and "enc_threads=1" in c_cb and "lib=" not in c_omx and "com.cloudblue.A9Video" in c_omx, (c_cb, c_omx))
    ck("lệnh cbvideo: CLASSPATH cbvideo + com.cloudblue.A9Video + max_size/max_fps/bitrate/i_frame", all(x in c_cb for x in (
        f"CLASSPATH={bs.CBV_DEV}", "com.cloudblue.A9Video", "max_size=960", "max_fps=30", "video_bit_rate=3000000", "i_frame=5", "scid=")), c_cb)
    ck("lệnh scrcpy không đổi (com.genymobile.scrcpy.Server 2.4)", "com.genymobile.scrcpy.Server 2.4" in c_sc and "A9Video" not in c_sc, c_sc)

    # Android 9 lấy hình bằng cbvideo: ngưỡng bỏ khung như máy khác + bỏ khung là xin khung khoá ngay
    class CbEnc:
        enc = "cbvideo"; kind = "cbv"; proc = None; frames_in = 5; fps = 30
        def __init__(self): self.keys = 0
        def failed_early(self): return False
        def request_key(self): self.keys += 1; return True
    async def queue_cb(age_s):
        s = mk("9"); s.enc = CbEnc(); s.wait_key = False
        t = time.monotonic() - age_s
        for i in range(3): s.aq.put_nowait((s.gen, b"\x00\x00\x00\x01\x41\x9a", False, False, 10 + i, t))
        task = asyncio.ensure_future(s._sender()); await asyncio.sleep(0.05); s.closed = True; task.cancel()
        try: await task
        except BaseException: pass
        return s
    s = await queue_cb(0.3)
    ck("Android 9 + cbvideo: 3 khung chờ 0,3 giây → bỏ như máy khác (ngưỡng 0,15) + xin khung khoá ngay", s.drop == 3 and s.enc.keys == 1 and s.n_kreq == 1,
       (s.drop, s.enc.keys, s.n_kreq, s.dr))
    s = mk("9"); s.enc = CbEnc()
    ck("_a9slow: Android 9 + cbvideo = False · Android 9 + scrcpy = True · Android 12 = False",
       (s._a9slow(), mk("9")._a9slow(), mk("12")._a9slow()) == (False, True, False), (s._a9slow(), mk("9")._a9slow(), mk("12")._a9slow()))
    s._dropx("lag"); s._dropx("lag")
    ck("xin khung khoá tối đa 4 lần / giây (2 lần bỏ khung liền → 1 lệnh)", s.enc.keys == 1 and s.n_kreq == 1, (s.enc.keys, s.n_kreq))

    async def keyfix_cb(secs, maxs):
        old = bs.CBV_KEY_MAX_S; bs.CBV_KEY_MAX_S = maxs
        s = mk("9"); s.sent = 5; s.wait_key = True; s.last_restart = time.time() - 10; s.last_rx = time.time() + 60
        s.t_auth = time.time() + 3600; s.enc = CbEnc(); hits = []
        async def fake_restart(size_msg=False, cpu=False): hits.append((time.time(), s.restart_req)); s.wait_key = False; s.last_restart = time.time()
        s.restart_video = fake_restart
        s._early_down = lambda now: False; s._may_raise = lambda now: False
        t0 = time.time(); task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(secs); s.closed = True
        try: await asyncio.wait_for(task, 2)
        except BaseException: pass
        bs.CBV_KEY_MAX_S = old
        return s, hits, t0
    s, hits, t0 = await keyfix_cb(1.2, 2.5)
    ck("cbvideo đang chờ khung khoá 1,2 giây → xin khoá (≥ 2 lần), KHÔNG bật lại bộ nén", not hits and s.enc.keys >= 2 and s.n_keyfix == 0,
       (hits, s.enc.keys, s.n_keyfix))
    s, hits, t0 = await keyfix_cb(1.6, 0.6)
    ck("cbvideo xin mãi không có khung khoá (quá CBV_KEY_MAX_S) → bật lại bộ nén như cũ, đếm rk", bool(hits) and s.n_keyfix == 1, (hits, s.n_keyfix))

    # chọn cbvideo khi mở máy Android 9 · cbvideo lỗi → quay về scrcpy ngay + đánh dấu máy 30 phút
    made = []
    class FakeSV:
        def __init__(self, serial, msz, fps, kbps, on_au, on_size=None, iframe=1.0, quick=False, ready_wait=12.0, kind="scrcpy"):
            self.kind = kind; self.enc = "cbvideo" if kind == "cbv" else "scrcpy"; self.proc = None; self.frames_in = 0
            made.append(kind)
        def start(self):
            if self.kind == "cbv" and FAIL_CB[0]: raise RuntimeError("cbvideo (hình) không nối được")
            return 544, 960
        def stop(self): pass
    class Src9(bs.ScrcpySource):
        def __init__(self): self.serial = "x"; self.res = None; self.cw, self.ch = 720, 1280; self.closed = False; self.stopping = False
    FAIL_CB = [False]
    real_sv, real_ens = bs.ScrcpyVideo, bs.ensure_cbv
    bs.ScrcpyVideo = FakeSV; bs.ensure_cbv = lambda: True
    real_mode = bs.A9_CBV_MODE
    try:
        ck("mặc định từ 27/11g: cbvideo BẬT cho mọi máy Android 9", real_mode == "on", real_mode)
        bs.A9_CBV_MODE = "test"
        s = mk("9"); s.src = Src9(); s.enc = None; bs._CBV_BAD.pop(s.serial, None)
        s._start_video_scrcpy()
        ck("chế độ thử: máy Android 9 mở thường → vẫn scrcpy", made == ["scrcpy"], made)
        made.clear()
        s = mk("9"); s.cbv_req = "1"; s.src = Src9(); s.enc = None
        w, h = s._start_video_scrcpy()
        ck("chế độ thử: phiên ?cbv=1 → lấy hình bằng cbvideo", made == ["cbv"] and s.enc.enc == "cbvideo" and (w, h) == (544, 960), (made, getattr(s.enc, "enc", None)))
        made.clear(); bs.A9_CBV_MODE = "on"
        s = mk("9"); s.src = Src9(); s.enc = None
        s._start_video_scrcpy()
        s0 = mk("9"); s0.cbv_req = "0"; s0.src = Src9(); s0.enc = None
        s0._start_video_scrcpy()
        ck("chế độ on: mọi máy Android 9 → cbvideo · phiên ?cbv=0 → scrcpy", made == ["cbv", "scrcpy"], made)
        made.clear(); FAIL_CB[0] = True
        s = mk("9"); s.src = Src9(); s.enc = None; bs._CBV_BAD.pop(s.serial, None)
        w, h = s._start_video_scrcpy()
        ck("cbvideo lỗi → đổi sang scrcpy ngay trong lần mở đó + máy bị đánh dấu", made == ["cbv", "scrcpy"] and s.enc.enc == "scrcpy"
           and bs._CBV_BAD.get(s.serial, 0) > time.time() + 1700, (made, getattr(s.enc, "enc", None), bs._CBV_BAD.get(s.serial)))
        made.clear(); FAIL_CB[0] = False
        s._start_video_scrcpy()
        ck("máy vừa lỗi cbvideo → các lần mở sau dùng scrcpy (30 phút)", made == ["scrcpy"], made)
        made.clear()
        s12 = mk("12"); s12.cbv_req = "1"; s12.src = Src9(); s12.enc = None
        s12._start_video_scrcpy()
        ck("Android 12 / 15 vẫn scrcpy (kể cả ?cbv=1)", made == ["scrcpy"], made)
    finally:
        bs.ScrcpyVideo, bs.ensure_cbv = real_sv, real_ens
        bs._CBV_BAD.clear(); bs.A9_CBV_MODE = real_mode

    sh = bs.Session(Link("ws"), {"uid": "u" * 8}, {"id": "p9c", "container": "cp_t", "port": 5555, "android": "9", "fps": 30}, {"q": "bal", "cbv": "1"}, time.monotonic())
    ck("HELLO {cbv: '1'} → phiên ép cbvideo", sh.cbv_req == "1" and sh._want_cbv() is True, (sh.cbv_req, sh._want_cbv()))

    # ensure_cbv: md5 ghim — file đúng → dùng · sai md5 → không chạy file lạ
    import hashlib, tempfile
    data = b"PK\x03\x04 test cbvideo"; md = hashlib.md5(data).hexdigest()
    real_file, real_state = bs.CBV_FILE, dict(bs._CBV)
    try:
        fn = "cbvideo-test-%d.jar" % os.getpid(); fp = os.path.join(bs.RTC, fn)
        open(fp, "wb").write(data)
        bs.CBV_FILE = (fn, md); bs._CBV["ok"] = None; bs._CBV["t"] = 0.0
        ck("ensure_cbv: file có sẵn đúng md5 → True (không tải lại)", bs.ensure_cbv() is True)
        bs.CBV_FILE = (fn, "0" * 32); bs._CBV["ok"] = None; bs._CBV["t"] = time.time()
        real_open = bs.urllib.request.urlopen
        bs.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("no net"))
        try: r = bs.ensure_cbv()
        finally: bs.urllib.request.urlopen = real_open
        ck("ensure_cbv: md5 không khớp + không tải được → False (Android 9 dùng scrcpy)", r is False, r)
        os.remove(fp)
    finally:
        bs.CBV_FILE = real_file; bs._CBV.clear(); bs._CBV.update(real_state)

    s = mk("9"); s.enc = CbEnc(); s.n_kreq = 3; s.last_rx = time.time() + 60; s.t_auth = time.time() + 3600; s.last_restart = time.time()
    s._early_down = lambda now: False; s._may_raise = lambda now: False; s.wait_key = False
    task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(2.2); s.closed = True
    try: await asyncio.wait_for(task, 2)
    except BaseException: pass
    st = [json.loads(p) for t, p in s.link.out if t == bs.S_STATS]
    ck("S_STATS: enc 'cbvideo' + kq (số lần xin khung khoá)", bool(st) and st[-1].get("enc") == "cbvideo" and st[-1].get("kq") == 3, st[-1:] if st else None)

    cs = bs._cbv_stat("cbvideo stats: 5.0s in 100 sub 80 rep 2 out 81 (16.2 fps) read 9.1 ms conv 6.3 ms")
    ck("đọc dòng thống kê cbvideo → khung vào / nạp / ra mỗi giây + ms đọc / đổi màu", cs == {"in": 20.0, "sub": 16.0, "out": 16.2, "read": 9.1, "conv": 6.3}
       and bs._cbv_stat("rác") is None, cs)
    cs2 = bs._cbv_stat("cbvideo stats: 5.0s in 150 sub 140 rep 1 out 141 (28.2 fps) read 8.0 ms conv 1.5 ms enc 3.2 ms oh264")
    ck("27/11h: dòng thống kê có 'enc … ms oh264' → thêm enc + by", cs2 and cs2.get("enc") == 3.2 and cs2.get("by") == "oh264" and cs2.get("out") == 28.2, cs2)
    import types
    lines = ["cbvideo stats: 5.0s in 100 sub 80 rep 2 out 81 (16.2 fps) read 9.1 ms conv 6.3 ms",
             "cbvideo stats: 5.0s in 90 sub 85 rep 0 out 85 (17.0 fps) read 8.0 ms conv 6.0 ms", "cbvideo: 544x960 fmt 21"]
    it = iter([x.encode() + b"\n" for x in lines] + [b""])
    p = types.SimpleNamespace(stdout=types.SimpleNamespace(readline=lambda: next(it)))
    v = bs.ScrcpyVideo("127.0.0.1:1", 960, 30, 3000, lambda *a: None, kind="cbv")
    logged = []; real_log = bs.log; bs.log = lambda *a, **k: logged.append(" ".join(str(x) for x in a))
    try: v._srvlog(p)
    finally: bs.log = real_log
    ck("cbvideo: thống kê mới nhất vào Thông số, nhật ký chỉ 1 dòng thống kê / 10 phút (dòng khác vẫn ghi)",
       getattr(v, "cstat", {}).get("out") == 17.0 and sum("cbvideo stats" in x for x in logged) == 1 and any("544x960" in x for x in logged), (getattr(v, "cstat", None), logged))
    s = mk("9"); e = CbEnc(); e.cstat = {"in": 20.0, "sub": 16.0, "out": 16.2, "read": 9.1, "conv": 6.3}; s.enc = e
    s.last_rx = time.time() + 60; s.t_auth = time.time() + 3600; s.last_restart = time.time()
    s._early_down = lambda now: False; s._may_raise = lambda now: False; s.wait_key = False
    task = asyncio.ensure_future(s._monitor()); await asyncio.sleep(2.2); s.closed = True
    try: await asyncio.wait_for(task, 2)
    except BaseException: pass
    st = [json.loads(p) for t, p in s.link.out if t == bs.S_STATS]
    ck("S_STATS: cbs = thống kê cbvideo (web hiện dòng cbvideo)", bool(st) and st[-1].get("cbs", {}).get("read") == 9.1, st[-1:] if st else None)

    print("9. 28/11a — độ nhiễu màn hình (giả lập vẽ hỏng → rác màu)")
    import random
    W, H = 720, 1280
    rnd = random.Random(7)
    img = bytearray(bytes((20, 40, 90, 255)) * (W * H))          # nền phẳng
    def rect(x0, y0, x1, y1, c):
        for y in range(y0, y1):
            for x in range(x0, x1): img[(y * W + x) * 4: (y * W + x) * 4 + 4] = bytes(c)
    for i in range(12): rect(40 + (i % 4) * 170, 200 + (i // 4) * 220, 160 + (i % 4) * 170, 320 + (i // 4) * 220, (240, 240, 250, 255))   # icon
    for k in range(60):                                          # "chữ": nét ngang / dọc mảnh
        y = 900 + k * 5; x0 = 40 + rnd.randrange(0, 200); rect(x0, y, x0 + rnd.randrange(80, 400), y + 1, (255, 255, 255, 255))
        x = 40 + rnd.randrange(0, 600); rect(x, 900 + rnd.randrange(0, 280), x + 1, 1200, (255, 255, 255, 255))
    clean = bs.noise_score(W, H, bytes(img))
    noisy = bs.noise_score(W, H, bytes(rnd.getrandbits(8) for _ in range(W * H * 4)))
    half = bytearray(img); half[(H // 2) * W * 4:] = bytes(rnd.getrandbits(8) for _ in range((H - H // 2) * W * 4))
    hn = bs.noise_score(W, H, bytes(half))
    ck("giao diện phẳng + icon + chữ → độ nhiễu < NOISE_OK", clean is not None and clean < bs.NOISE_OK, clean)
    ck("rác màu toàn màn → độ nhiễu ≥ NOISE_BAD", noisy is not None and noisy >= bs.NOISE_BAD, noisy)
    ck("nửa màn rác → vẫn ≥ NOISE_BAD (28/11: hình nền + icon rác, chữ nét)", hn is not None and hn >= bs.NOISE_BAD, hn)
    ck("ảnh quá nhỏ / thiếu byte → None", bs.noise_score(8, 8, b"x" * 256) is None and bs.noise_score(100, 100, b"x" * 10) is None)
    ck("_noise_txt: nhãn NHIỄU / bình thường / không đo được", "NHIỄU" in bs._noise_txt(0.5) and "bình thường" in bs._noise_txt(0.02)
       and bs._noise_txt(None) == "không đo được")
    ck("có lệnh --quetnhieu (không lưu ảnh màn của khách) + kiemhinh đo màn thật trước", callable(bs.quetnhieu) and '"--quetnhieu" in sys.argv' in SRC_TXT
       and "MÀN HÌNH THẬT CỦA ANDROID ĐÃ NHIỄU" in SRC_TXT and "KHÔNG lưu / xem ảnh màn của khách" in SRC_TXT)
    ck("kiemhinh KHÔNG còn kết luận 'SẠCH' chỉ vì 0 lỗi giải mã (phải kiểm hình)", "đã đo độ nhiễu từng lần" in SRC_TXT
       and "Hình phát ra từ máy SẠCH ở mọi kiểu thử → lỗi nằm ở đường truyền" not in SRC_TXT)


asyncio.run(main())
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
