# -*- coding: utf-8 -*-
"""THỬ ĐẦU-CUỐI bằng TRÌNH DUYỆT THẬT: play.html?pc=… (web-2.0) ⇄ máy chủ phát hình thật (bluestream --selftest + pcrelay.py) ⇄ máy PC (pcremote.py thật, quay hình thử).
   Chạy:  python3 winpc/tests/remote/test_play_pc.py <play.html> [thư mục site có broadway.js + avc.wasm] [thư mục ảnh]
   Kiểm: ra hình trên canvas · chuột thật (rê / trái / phải / giữa) · phím thật (Ctrl+Shift+Esc, F5, Alt…) · gõ chữ · cuộn · nhả hết phím khi rời trang."""
import hashlib, json, os, shutil, socket, struct, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import SRV as SRC, AGENT                                # noqa: E402
sys.path.insert(0, AGENT)
import pcremote as R                                               # noqa: E402
from playwright.sync_api import sync_playwright                    # noqa: E402

OK = FAIL = 0
FF = shutil.which("ffmpeg")
PC = "22222222-2222-4222-8222-222222222222"
PLAY = sys.argv[1] if len(sys.argv) > 1 else "play.html"
SITE = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(PLAY))
SHOTS = sys.argv[3] if len(sys.argv) > 3 else tempfile.mkdtemp(prefix="cbshots-")


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


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


if not FF:
    print("(bỏ qua: máy thử không có ffmpeg)"); sys.exit(0)
tmp = tempfile.mkdtemp(prefix="cbplay-")
for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(SRC, f), os.path.join(tmp, f))
port, wsport = free_port(), free_port()
open(os.path.join(tmp, "cloudphone.conf"), "w").write(f"NODE_ID=wintest\nSTREAM_PORT={port}\nSTREAM_WS_PORT={wsport}\nUPNP=0\n")
logf = open(os.path.join(tmp, "out.log"), "wb")
proc = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=tmp, stdout=logf, stderr=subprocess.STDOUT)
rm = None
try:
    t0 = time.time(); up = False
    while time.time() - t0 < 40 and proc.poll() is None:
        try: socket.create_connection(("127.0.0.1", wsport), timeout=0.5).close(); up = True; break
        except OSError: time.sleep(0.3)
    ck("máy chủ phát hình chạy (cổng WebSocket nội bộ cho trình duyệt)", up)
    io_ = R.NullIO(1920, 1080); logs = []
    real_connect = R.connect
    R.connect = lambda stream_, cafile=None, log=None: R.WSConn("ws://127.0.0.1:%d/v2/stream" % wsport, 3.0, plain=True)
    rm = R.Remote(lambda: {"id": PC, "token": "tok-1"}, lambda fn, body: {"ok": True, "on": True, "node": "wintest", "stream": {"direct": [], "ws": "x"}}, io_, lambda: FF, logs.append, None,
                  caps={"enc": ["x264"], "cap": "test"})
    rm.sleep = lambda s: time.sleep(min(s, 0.3))
    threading.Thread(target=rm.run, daemon=True).start()
    ck("máy PC vào trạm, chờ người xem", wait(lambda: "cho nguoi xem" in rm.state, 10), (rm.state, logs[-3:]))
    html = open(PLAY, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1280, "height": 760})
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))

        import http.server                                          # trang phải là trang THẬT trên localhost (trang giả bằng route bị Chrome chặn nối WebSocket nội bộ)
        site = tempfile.mkdtemp(prefix="cbsite-")
        open(os.path.join(site, "play.html"), "w", encoding="utf-8").write(html)
        for f in ("broadway.js", "avc.wasm"):
            if os.path.isfile(os.path.join(SITE, f)): shutil.copy(os.path.join(SITE, f), os.path.join(site, f))
        class Q(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k): super().__init__(*a, directory=site, **k)
            def log_message(self, *a): pass
        Q.extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{".wasm": "application/wasm", ".js": "application/javascript"})
        hs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=hs.serve_forever, daemon=True).start()
        page.route("**/cdn.jsdelivr.net/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body="window.supabase={createClient:()=>({auth:{getSession:async()=>({data:{session:null}}),onAuthStateChange(){return{data:{subscription:{unsubscribe(){}}}}}},rpc:async()=>({data:null,error:null})})};"))
        page.goto("http://localhost:%d/play.html?test=1&pc=%s&ws=ws://127.0.0.1:%d/v2/stream&name=May-Thu" % (hs.server_address[1], PC, wsport))
        ok = wait(lambda: page.evaluate("() => P.frames") > 15, 25)
        st = page.evaluate("() => ({ kind: P.kind, frames: P.frames, vw: P.vw, vh: P.vh, ovl: document.getElementById('ovl').hidden, pcm: document.body.classList.contains('pcm'), sw: P.sw, err: P.lastErr })")
        ck("trình duyệt mở máy PC: chế độ pc, nhận WELCOME + hình (giải mã được, lớp chờ đã tắt)", ok and st["kind"] == "pc" and st["pcm"] and st["ovl"] and st["vw"] > 0, st)
        page.screenshot(path=os.path.join(SHOTS, "play-pc-1.png"))
        page.evaluate("() => document.getElementById('menu').hidden = false"); page.wait_for_timeout(200)
        mn = page.evaluate("() => ({ pc: [...document.querySelectorAll('#pc-grid [data-pck]')].map(b => b.dataset.pck), hidden: ['store', 'root', 'reboot', 'apkfile', 'power', 'rotate'].map(a => getComputedStyle(document.querySelector('#menu [data-a=\"' + a + '\"]')).display) })")
        ck("menu ⋯ của máy PC: có phím Windows (Win, Alt+Tab, Alt+F4, Task Manager, Explorer…), ẩn nút chỉ dành cho Android", mn["pc"][:5] == ["win", "alttab", "altf4", "taskmgr", "explorer"] and set(mn["hidden"]) == {"none"}, mn)
        page.screenshot(path=os.path.join(SHOTS, "play-pc-2-menu.png"))
        io_.ev.clear()
        page.click('#pc-grid [data-pck="taskmgr"]'); page.wait_for_timeout(300)
        ck("bấm Task Manager → máy PC nhận Ctrl+Shift+Esc", wait(lambda: [e for e in io_.ev if e[0] == "key"] == [("key", 0xA2, True, False), ("key", 0xA0, True, False), ("key", 0x1B, True, False),
                                                                                                                     ("key", 0x1B, False, False), ("key", 0xA0, False, False), ("key", 0xA2, False, False)], 4), io_.ev)
        box = page.evaluate("() => { const r = document.getElementById('cv').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")
        cx, cy = box[0] + box[2] * 0.25, box[1] + box[3] * 0.5
        io_.ev.clear()
        page.mouse.move(cx, cy); page.wait_for_timeout(120)
        page.mouse.down(); page.mouse.up(); page.wait_for_timeout(100)
        page.mouse.down(button="right"); page.mouse.up(button="right"); page.wait_for_timeout(100)
        page.mouse.down(button="middle"); page.mouse.up(button="middle"); page.wait_for_timeout(300)
        btn = [e for e in io_.ev if e[0] == "btn"]
        mv = [e for e in io_.ev if e[0] == "move"]
        ck("chuột thật: rê chuột KHÔNG bấm cũng tới máy (hover), toạ độ đúng 1/4 ngang · 1/2 dọc", mv and abs(mv[0][1] - 16384) < 900 and abs(mv[0][2] - 32768) < 900, mv[:2])
        ck("chuột thật: trái / phải / giữa → đúng nút, đủ nhấn + nhả", btn == [("btn", 0, True), ("btn", 0, False), ("btn", 1, True), ("btn", 1, False), ("btn", 2, True), ("btn", 2, False)], btn)
        io_.ev.clear()
        page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx + 120, cy + 40, steps=6); page.mouse.up(); page.wait_for_timeout(300)
        b2 = [e for e in io_.ev if e[0] == "btn"]; m2 = [e for e in io_.ev if e[0] == "move"]
        ck("kéo thả: giữ trái, rê, nhả (nhiều điểm rê giữa nhấn và nhả)", b2 == [("btn", 0, True), ("btn", 0, False)] and len(m2) >= 3, (b2, len(m2)))
        io_.ev.clear()
        page.keyboard.press("Control+Shift+Escape"); page.keyboard.press("F5"); page.keyboard.down("Alt"); page.keyboard.press("Tab"); page.keyboard.up("Alt")
        page.keyboard.press("Shift+KeyA"); page.keyboard.type("b1"); page.wait_for_timeout(400)
        ks = [e for e in io_.ev if e[0] == "key"]
        want = [("key", 0xA2, True, False), ("key", 0xA0, True, False), ("key", 0x1B, True, False), ("key", 0x1B, False, False), ("key", 0xA0, False, False), ("key", 0xA2, False, False),
                ("key", 0x74, True, False), ("key", 0x74, False, False), ("key", 0xA4, True, False), ("key", 0x09, True, False), ("key", 0x09, False, False), ("key", 0xA4, False, False),
                ("key", 0xA0, True, False), ("key", 0x41, True, False), ("key", 0x41, False, False), ("key", 0xA0, False, False), ("key", 0x42, True, False), ("key", 0x42, False, False),
                ("key", 0x31, True, False), ("key", 0x31, False, False)]
        ck("phím thật: Ctrl+Shift+Esc, F5, Alt+Tab, Shift+A, b, 1 → đúng phím Windows, đúng thứ tự nhấn / nhả (chơi game được)", ks == want, ks)
        io_.ev.clear()
        page.mouse.move(cx, cy); page.mouse.wheel(0, -240); page.wait_for_timeout(300)
        wh = [e for e in io_.ev if e[0] == "wheel"]
        ck("lăn chuột → máy PC cuộn", wh and wh[0][1] > 0, io_.ev[-3:])
        io_.ev.clear()
        page.keyboard.down("Shift"); page.mouse.down(button="right"); page.wait_for_timeout(150)
        page.evaluate("() => window.dispatchEvent(new Event('blur'))"); page.wait_for_timeout(300)
        rel_ = [e for e in io_.ev if (e[0] == "key" and e[2] is False) or (e[0] == "btn" and e[2] is False)]
        ck("rời trang giữa chừng (mất tiêu điểm) khi đang giữ Shift + chuột phải → nhả hết, không kẹt bên máy PC", ("key", 0xA0, False, False) in rel_ and ("btn", 1, False) in rel_, io_.ev[-6:])
        page.keyboard.up("Shift"); page.mouse.up(button="right")
        page.evaluate("() => document.getElementById('menu').hidden = true")
        ck("không lỗi JS trên trang", not errs, errs)
        page.screenshot(path=os.path.join(SHOTS, "play-pc-3.png"))

        # ---- web-2.2 (21.11k): độ nét Siêu nét + khách tự chọn khung hình/giây · nhiều máy PC cùng lúc + đồng bộ chuột
        page.evaluate("() => document.getElementById('menu').hidden = false"); page.wait_for_timeout(200)
        qv = page.evaluate("""() => ({ uhd: getComputedStyle(document.querySelector('#q-seg [data-q="uhd"]')).display, fseg: getComputedStyle(document.getElementById('f-seg')).display,
                                        fps: [...document.querySelectorAll('#f-seg [data-f]')].map(b => b.dataset.f), multi: getComputedStyle(document.querySelector('#menu [data-a="multi"]')).display })""")
        ck("menu máy PC: có mức Siêu nét + hàng Khung hình/giây (Mặc định · 30 · 60 · 120) + nút Nhiều máy", qv["uhd"] != "none" and qv["fseg"] != "none" and qv["fps"] == ["0", "30", "60", "120"] and qv["multi"] != "none", qv)
        page.screenshot(path=os.path.join(SHOTS, "play-pc-4-quality.png"))
        page.click('#q-seg [data-q="uhd"]'); page.wait_for_timeout(300); page.click('#f-seg [data-f="60"]')
        mh = page.evaluate("() => Math.min(1920, maxH())")                    # trang xin cạnh dài ≤ màn hình của người xem (máy thử: màn 1280)
        ok_q = wait(lambda: rm.sess is not None and rm.sess.q == "uhd" and rm.sess.fps_fix == 60 and rm.sess.fps == 60 and rm.sess.vw == mh, 12)
        ck("chọn Siêu nét + 60 FPS → máy PC đổi ngay: mức uhd, 60 khung/giây, nét tối đa theo màn người xem; trang nhớ lựa chọn",
           ok_q and page.evaluate("() => [localStorage.getItem('cb_pcq'), localStorage.getItem('cb_pcf'), document.querySelector('#f-seg .on').dataset.f]") == ["uhd", "60", "60"],
           (getattr(rm.sess, "q", None), getattr(rm.sess, "fps_fix", None), getattr(rm.sess, "fps", None), getattr(rm.sess, "vw", None)))
        page.click('#f-seg [data-f="0"]'); page.click('#q-seg [data-q="bal"]')
        ck("về Mặc định + Cân bằng → máy PC về 30 khung/giây", wait(lambda: rm.sess is not None and rm.sess.q == "bal" and rm.sess.fps_fix == 0 and rm.sess.fps == 30, 12),
           (getattr(rm.sess, "q", None), getattr(rm.sess, "fps_fix", None), getattr(rm.sess, "fps", None)))
        page.evaluate("() => document.getElementById('menu').hidden = true")
        PC2 = "33333333-3333-4333-8333-333333333333"
        page.goto("http://localhost:%d/play.html?test=1&multi=pc&ids=%s,%s&ws=ws://127.0.0.1:%d/v2/stream" % (hs.server_address[1], PC, PC2, wsport))
        TS = "() => { try { return { f: P.frames || 0, ovl: document.getElementById('ovl').hidden, kind: P.kind, vw: P.vw, err: P.lastErr, ws: P.ws ? P.ws.readyState : -1 }; } catch (e) { return { e: String(e) }; } }"
        def tile_st():
            got = {}
            for f in list(page.frames[1:]):
                if f.url.find("pc=" + PC) > 0 and f.url.find("tile=1") > 0:
                    try: got = f.evaluate(TS)
                    except Exception as e: got = {"e": str(e)[:100]}
                    if got.get("kind") == "pc" and (got.get("vw") or 0) > 0: return got
            return got
        fr_ok = wait(lambda: (lambda t: t.get("kind") == "pc" and t.get("ovl") and (t.get("vw") or 0) > 0)(tile_st()), 60)            # máy vừa đóng ở trang đơn → trạm nhả phiên cũ rồi ô mới vào
        mu = page.evaluate("() => ({ view: document.body.dataset.view, n: document.querySelectorAll('#mu-grid .mt').length, src: [...document.querySelectorAll('#mu-grid iframe')].map(f => f.getAttribute('src')), url: location.search })")
        mu["tile"] = tile_st()
        ck("Nhiều máy PC (?multi=pc): lưới 2 ô, mỗi ô mở play.html?pc=…&tile=1, ô máy đang bật lên hình", fr_ok and mu["view"] == "v-multi" and mu["n"] == 2 and all("pc=" in x and "tile=1" in x for x in mu["src"]) and "multi=pc" in mu["url"], mu)
        page.screenshot(path=os.path.join(SHOTS, "play-pc-5-multi.png"))
        io_.ev.clear()
        page.evaluate("""() => { const f = [...document.querySelectorAll('#mu-grid iframe')].find(x => x.getAttribute('src').includes('%s'));
                                 f.contentWindow.postMessage({ cb: 'host', k: 'sync', on: true }, location.origin);
                                 f.contentWindow.postMessage({ cb: 'host', k: 'ev', src: '%s', e: ['m', 1, 0, 0.5, 0.5] }, location.origin);
                                 f.contentWindow.postMessage({ cb: 'host', k: 'ev', src: '%s', e: ['m', 2, 0, 0.5, 0.5] }, location.origin); }""" % (PC, PC2, PC2))
        ck("đồng bộ: máy PC khác trong lưới bấm chuột → máy này bấm theo (nhấn + nhả cùng chỗ)", wait(lambda: [e for e in io_.ev if e[0] == "btn"] == [("btn", 0, True), ("btn", 0, False)], 6), io_.ev[-4:])
        ck("không lỗi JS (độ nét, FPS, nhiều máy PC)", not errs, errs)
        br.close()
    R.connect = real_connect
finally:
    if rm is not None:
        rm.stop = True
        try:
            if rm.conn: rm.conn.close()
        except Exception: pass
    proc.terminate()
    try: proc.wait(10)
    except Exception: proc.kill()
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
