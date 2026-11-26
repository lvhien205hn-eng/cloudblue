# -*- coding: utf-8 -*-
"""27/11e — kiểm logic phát hình ANDROID 9 mới của windows/bluestream.py (không cần máy Android):
     python3 .github/a9-check/test_a9logic.py
   1. cỡ hình: Android 9 ≤ 960 ở Tiết kiệm / Cân bằng / Tự động, mức Nét giữ nguyên; máy khác không đổi
   2. khung I Android 9 thưa (5), máy khác như cũ
   3. "app chậm": Android 9 chịu gấp đôi trước khi bỏ khung; máy khác như cũ; đếm lý do bỏ khung
   4. hàng chờ: Android 9 chịu 0,5 giây; máy khác 0,15 giây
   5. bỏ khung → bật lại bộ nén sau ~0,2 giây (Android 9), máy khác không tự bật lại
   6. không dumpsys "màn ảo" sau cú bấm ở Android 9; máy khác vẫn có
   7. Thông số gửi app / web có efps, rs, rk, dr"""
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


def mk(android, q="bal", kind="ws"):
    phone = {"id": "p" + android + q + kind, "container": "cp_test", "port": 5555, "android": android, "fps": 30}
    s = bs.Session(Link(kind), {"uid": "u" * 8}, phone, {"q": q}, time.monotonic())
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


asyncio.run(main())
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
