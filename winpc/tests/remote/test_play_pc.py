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
