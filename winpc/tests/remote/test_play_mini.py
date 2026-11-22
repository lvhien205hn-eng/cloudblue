# -*- coding: utf-8 -*-
"""THỬ ĐẦU-CUỐI bằng TRÌNH DUYỆT THẬT: dải ⊟ THU NHỎ của play.html (22/11, kiểu Redfinger — khách xin) ⇄ máy chủ phát hình thật
   (bluestream --selftest, nguồn hình giả). Kiểm: dải hiện ở màn "Máy của tôi" · mỗi máy 1 ô (thanh tên ● tên · ⤢ · ✕ + hình) · hình ô là
   phiên XEM TRƯỚC (máy chủ ghi "▷ xem trước", hello mode=preview, không phải phiên điều khiển) · ô chỉ xem (không gửi chạm) ·
   bấm ô → điều khiển máy đó (dải ẩn, đóng các ô) · ⊟ ở màn điều khiển → về danh sách, máy đó có trong dải · ✕ bỏ · đổi cỡ · thu gọn.
   Chạy:  python3 winpc/tests/remote/test_play_mini.py <play.html> [thư mục ảnh]"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import SRV as SRC                                         # noqa: E402
from playwright.sync_api import sync_playwright                    # noqa: E402

OK = FAIL = 0
PLAY = sys.argv[1] if len(sys.argv) > 1 else "play.html"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="cbshots-")
A, B = "aaaaaaaa-1111-4111-8111-111111111111", "bbbbbbbb-2222-4222-8222-222222222222"


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:700])


def wait(fn, timeout=8.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v: return v
        except Exception:
            pass
        time.sleep(step)
    try: return fn()
    except Exception: return None


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


if not shutil.which("ffmpeg"):
    print("(bỏ qua: máy thử không có ffmpeg)"); sys.exit(0)
tmp = tempfile.mkdtemp(prefix="cbmini-")
for f in ("bluestream.py", "pcrelay.py"): shutil.copy(os.path.join(SRC, f), os.path.join(tmp, f))
port, wsport = free_port(), free_port()
open(os.path.join(tmp, "cloudphone.conf"), "w").write(f"NODE_ID=wintest\nSTREAM_PORT={port}\nSTREAM_WS_PORT={wsport}\nUPNP=0\n")
logp = os.path.join(tmp, "out.log"); logf = open(logp, "wb")
proc = subprocess.Popen([sys.executable, "-u", "bluestream.py", "--selftest"], cwd=tmp, stdout=logf, stderr=subprocess.STDOUT)
srvlog = lambda: open(logp, encoding="utf-8", errors="replace").read()
try:
    t0 = time.time(); up = False
    while time.time() - t0 < 40 and proc.poll() is None:
        try: socket.create_connection(("127.0.0.1", wsport), timeout=0.5).close(); up = True; break
        except OSError: time.sleep(0.3)
    ck("máy chủ phát hình chạy (cổng WebSocket cho trình duyệt)", up, srvlog()[-600:])
    import http.server
    site = tempfile.mkdtemp(prefix="cbsite-")
    shutil.copy(PLAY, os.path.join(site, "play.html"))

    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=site, **k)
        def log_message(self, *a): pass
    hs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=hs.serve_forever, daemon=True).start()
    base = "http://localhost:%d/play.html" % hs.server_address[1]
    WS = "ws://127.0.0.1:%d/v2/stream" % wsport
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1100, "height": 760})
        ctx.route("**/cdn.jsdelivr.net/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body="window.supabase={createClient:()=>({auth:{getSession:async()=>({data:{session:null}})},rpc:async()=>({data:null,error:null})})};"))
        ctx.add_init_script("try { if (!sessionStorage.getItem('mn_seed')) { sessionStorage.setItem('mn_seed', '1'); localStorage.setItem('cb_minis_test', JSON.stringify([{id: '%s', n: 'Núi I', w: 1280, h: 720}, {id: '%s', n: 'Núi II', w: 720, h: 1280}])); localStorage.setItem('cb_minis_ui', '{}'); localStorage.setItem('br_lang', 'vi'); } } catch (e) {}" % (A, B))
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        page.goto(base + "?test=1&list=1&ids=%s,%s&ws=%s" % (A, B, WS))
        page.wait_for_selector("#mini .mn-t", timeout=15000)
        st = page.evaluate("""() => ({ view: document.body.dataset.view, tiles: [...document.querySelectorAll('#mini .mn-t')].map(t => ({ name: t.querySelector('.mn-h b').textContent,
             w: t.querySelector('.mn-b').getBoundingClientRect().width, h: t.querySelector('.mn-b').getBoundingClientRect().height, src: t.querySelector('iframe').getAttribute('src') })),
             head: document.querySelector('#mini .mn-hd b').textContent, rowBtns: [...document.querySelectorAll('#list [data-mini]')].map(b => b.textContent) })""")
        ck("màn Máy của tôi: dải thu nhỏ hiện 2 ô (thanh tên đúng tên máy), máy ngang ô ngang, máy dọc ô dọc",
           st["view"] == "v-list" and [t["name"] for t in st["tiles"]] == ["Núi I", "Núi II"] and st["tiles"][0]["w"] > st["tiles"][0]["h"] and st["tiles"][1]["h"] > st["tiles"][1]["w"]
           and st["head"] == "Thu nhỏ · 2", st)
        ck("ô là khung xem trước của chính trang này (?id=…&tile=1&pv=1&mh=320) · thẻ máy có nút ✕ Bỏ thu nhỏ",
           all("tile=1" in t["src"] and "pv=1" in t["src"] and "mh=320" in t["src"] for t in st["tiles"]) and st["rowBtns"] == ["✕ Bỏ thu nhỏ", "✕ Bỏ thu nhỏ"], st)
        fr = lambda i: page.frames[1 + i] if len(page.frames) > 1 + i else None
        def kid(i, js):
            f = [x for x in page.frames if "pv=1" in x.url]
            return f[i].evaluate(js) if len(f) > i else None
        ok = wait(lambda: (kid(0, "() => P.frames") or 0) > 3 and (kid(1, "() => P.frames") or 0) > 3, 25)
        k0 = kid(0, "() => ({ pv: document.body.classList.contains('pv'), frames: P.frames, ovl: document.getElementById('ovl').hidden, ptr: getComputedStyle(document.getElementById('cv')).pointerEvents })")
        ck("2 ô ra hình trực tiếp (giải mã được) · ô ở chế độ xem trước, canvas không nhận chạm", ok and k0 and k0["pv"] and k0["ovl"] and k0["ptr"] == "none", k0)
        log = srvlog()
        ck("máy chủ mở 2 phiên XEM TRƯỚC (▷ xem trước), không phải phiên điều khiển", log.count("▷ xem trước") >= 2, log[-900:])
        dots = wait(lambda: page.evaluate("() => [...document.querySelectorAll('#mini .mn-h .d')].every(d => d.classList.contains('ok'))"), 8)
        ck("chấm trạng thái các ô xanh (đang phát)", dots)
        page.screenshot(path=os.path.join(SHOTS, "mini-1-list.png"))
        sent = kid(0, """() => { const bad = []; const w = P.ws, o = w.send.bind(w); w.send = b => { const t = new Uint8Array(b)[0]; if (![T.HELLO, T.PING, T.ACK, T.KEYFRAME, T.BYE].includes(t)) bad.push(t); return o(b); };
                              touch(0, 0, 100, 100); touch(1, 0, 100, 100); key(4, 0); try { cmd('home'); } catch (e) {} setClip('x', true); return new Promise(r => setTimeout(() => r(bad), 300)); }""")
        ck("ô xem trước KHÔNG gửi chạm / phím / lệnh / chữ (chỉ xem)", sent == [], sent)
        # ---- đổi cỡ · thu gọn / mở
        w0 = page.evaluate("() => document.querySelector('#mini .mn-b').getBoundingClientRect().width")
        page.click('#mini [data-mn="size"]'); page.wait_for_timeout(200)
        w1 = page.evaluate("() => document.querySelector('#mini .mn-b').getBoundingClientRect().width")
        ck("bấm Cỡ: Vừa → To: ô to hơn, khung giữ nguyên (không nối lại)", w1 > w0 and page.evaluate("() => document.querySelector('#mini [data-mn=\"size\"]').textContent") == "Cỡ: To"
           and len([x for x in page.frames if "pv=1" in x.url]) == 2, (w0, w1))
        page.click('#mini button[data-mn="tog"]'); page.wait_for_timeout(200)
        col = page.evaluate("() => ({ col: document.getElementById('mini').classList.contains('col'), tiles: document.querySelectorAll('#mini .mn-t').length, head: document.querySelector('#mini .mn-hd b').textContent })")
        ck("thu gọn: dải còn 1 dòng, đóng các ô (tắt hình, đỡ mạng)", col == {"col": True, "tiles": 0, "head": "2 máy đang thu nhỏ — bấm để mở"}, col)
        page.screenshot(path=os.path.join(SHOTS, "mini-2-collapsed.png"))
        page.click('#mini button[data-mn="tog"]'); page.wait_for_selector("#mini .mn-t")
        ck("mở lại: 2 ô", page.evaluate("() => document.querySelectorAll('#mini .mn-t').length") == 2)
        # ---- bấm ô → điều khiển máy đó
        page.click('#mini .mn-t >> nth=1 >> .mn-cv')
        pl = wait(lambda: page.evaluate("() => document.body.dataset.view === 'v-play' && P.id") , 8)
        ck("bấm ô máy Núi II → mở điều khiển ĐÚNG máy đó; dải ẩn + đóng hết ô xem trước", pl == B and page.evaluate("() => document.getElementById('mini').hidden && !document.querySelector('#mini .mn-t')")
           and not [x for x in page.frames if "pv=1" in x.url], pl)
        ok2 = wait(lambda: page.evaluate("() => P.frames") > 5, 20)
        ck("phiên điều khiển ra hình", ok2)
        page.screenshot(path=os.path.join(SHOTS, "mini-3-play.png"))
        # ---- ⊟ ở màn điều khiển
        page.evaluate("() => { const a = JSON.parse(localStorage.getItem('cb_minis_test')); localStorage.setItem('cb_minis_test', JSON.stringify(a.filter(x => x.id !== '%s'))); }" % B)
        page.click("#mini-btn")
        back = wait(lambda: page.evaluate("() => document.body.dataset.view === 'v-list' && document.querySelectorAll('#mini .mn-t').length === 2 && MN.tiles.map(t => t.key)"), 10)
        ck("⊟ ở màn điều khiển → về Máy của tôi, máy vừa mở vào CUỐI dải", back == [A, B], back)
        fl = page.evaluate("() => !!document.querySelector('#mini .mn-t.flash')")
        ck("… ô vừa thu nhỏ sáng viền", fl)
        # ---- ✕ bỏ 1 ô · nút trên thẻ máy
        page.click('#mini .mn-t >> nth=0 >> button[aria-label^="Bỏ khỏi dải"]'); page.wait_for_timeout(300)
        left = page.evaluate("() => ({ tiles: document.querySelectorAll('#mini .mn-t').length, saved: JSON.parse(localStorage.getItem('cb_minis_test')).map(x => x.id) })")
        ck("✕ trên ô → bỏ khỏi dải (lưu lại), còn 1 ô", left == {"tiles": 1, "saved": [B]}, left)
        page.click('#list [data-mini="%s"]' % A); page.wait_for_timeout(300)
        add = page.evaluate("() => ({ tiles: [...document.querySelectorAll('#mini .mn-t .mn-h b')].map(b => b.textContent), btn: document.querySelector('#list [data-mini=\"%s\"]').textContent })" % A)
        ck("nút ⊟ Thu nhỏ trên thẻ máy → thêm vào dải, nút đổi thành ✕ Bỏ thu nhỏ", len(add["tiles"]) == 2 and add["btn"] == "✕ Bỏ thu nhỏ", add)
        page.screenshot(path=os.path.join(SHOTS, "mini-4-after.png"))
        page.set_viewport_size({"width": 390, "height": 800}); page.wait_for_timeout(400)
        mob = page.evaluate("() => { const r = document.getElementById('mini').getBoundingClientRect(); return { w: r.width, h: r.height, right: r.right, sw: innerWidth }; }")
        ck("điện thoại (390 px): dải vừa màn, không tràn", mob["right"] <= mob["sw"] and mob["w"] <= mob["sw"] - 8, mob)
        page.screenshot(path=os.path.join(SHOTS, "mini-5-phone.png"))
        page.evaluate("() => { document.querySelector('.langb').click(); }"); page.wait_for_timeout(300)
        en = page.evaluate("() => ({ head: document.querySelector('#mini .mn-hd b').textContent, size: document.querySelector('#mini [data-mn=\"size\"]').textContent })")
        ck("English: dải đổi chữ (Minimized · 2, Size: L)", en == {"head": "Minimized · 2", "size": "Size: L"}, en)
        page.evaluate("() => { document.querySelector('.langb').click(); }")
        ck("không lỗi JS trên trang", not errs, errs)
        br.close()
    hs.shutdown()
finally:
    proc.terminate()
    try: proc.wait(10)
    except Exception: proc.kill()
print("\n%d/%d đạt" % (OK, OK + FAIL))
sys.exit(0 if FAIL == 0 else 1)
