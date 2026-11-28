# -*- coding: utf-8 -*-
"""THỬ bằng TRÌNH DUYỆT THẬT: nút "Kéo cửa sổ bị lệch ra ngoài về giữa màn hình" của máy PC trong play.html (28/11g).
   Hộp thoại mở lệch ra ngoài màn hình máy PC (vd hộp Đổi tên của MuMu) → người xem từ xa không thấy / không gõ được.
   Máy PC bản 28.11g tự kéo về khi đang xem; nút này gửi lệnh "wins" để máy kéo tất cả ngay.
   Chạy:  python3 winpc/tests/web/test_play_cuaso.py [play.html]"""
import http.server, json, os, sys, tempfile, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "play.html")
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:600], flush=True)


site = tempfile.mkdtemp(prefix="cbsite-")
open(os.path.join(site, "play.html"), "w", encoding="utf-8").write(open(PLAY, encoding="utf-8").read())


class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=site, **k)
    def log_message(self, *a): pass


hs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=hs.serve_forever, daemon=True).start()
URL = f"http://localhost:{hs.server_address[1]}/play.html?test=1&id=00000000-0000-4000-8000-000000000001&ws=ws://127.0.0.1:9/v2/stream"
HOOK = """(kind) => {
  window.__sent = []; P.kind = kind; document.body.dataset.view = "v-play";
  document.getElementById("menu").hidden = true; document.getElementById("dlg").hidden = true;
  send = (t, b) => window.__sent.push([t, Array.from(b || [])]);
  pcMode(kind === "pc");
}"""
CMDS = """() => window.__sent.filter(([t]) => t === T.CMD).map(([t, b]) => JSON.parse(new TextDecoder().decode(new Uint8Array(b))).cmd)"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, nm in ((412, 860, "điện thoại dọc"), (1280, 800, "máy tính")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, has_touch=vw < 600, is_mobile=vw < 600, locale="vi-VN")
        ctx.add_init_script("try { localStorage.setItem('br_lang', 'vi'); } catch (e) {}")
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        page.on("dialog", lambda d: (errs.append("DIALOG " + d.message[:100]), d.dismiss()))
        page.goto(URL); page.wait_for_timeout(800)
        print(f"— {nm} ({vw}×{vh})")
        page.evaluate(HOOK, "phone")
        ck("Cloud Phone: không có nhóm phím Windows / nút kéo cửa sổ", page.evaluate("() => !document.getElementById('pc-grid') && !document.querySelector('[data-pck=wins]')"))
        page.evaluate(HOOK, "pc")
        page.evaluate("() => { document.getElementById('menu').hidden = false; }"); page.wait_for_timeout(200)
        info = page.evaluate("""() => { const g = document.getElementById('pc-grid'), b = g && g.querySelector('[data-pck=wins]'); if (!b) return null;
          b.scrollIntoView({ block: 'center' }); const r = b.getBoundingClientRect(), gr = g.getBoundingClientRect(), k = g.querySelector('[data-pck=win]').getBoundingClientRect();
          return { txt: b.innerText.replace(/\\s+/g, ' ').trim(), w: r.width, gw: gr.width, below: r.top >= k.bottom - 1, n: g.querySelectorAll('[data-pck]').length,
                   last: g.lastElementChild === b, vis: r.width > 0 && r.height >= 40 }; }""")
        ck("máy PC: menu có nút '🪟 Kéo cửa sổ bị lệch ra ngoài về giữa màn hình' (cả hàng, dưới 8 phím Windows)",
           info and "Kéo cửa sổ bị lệch ra ngoài về giữa màn hình" in info["txt"] and abs(info["w"] - info["gw"]) < 2 and info["below"] and info["n"] == 9 and info["last"] and info["vis"], info)
        page.click("#pc-grid [data-pck=wins]"); page.wait_for_timeout(300)
        ck("bấm nút → gửi lệnh 'wins' cho máy PC (đúng 1 lệnh), đóng menu, báo đã kéo",
           page.evaluate(CMDS) == ["wins"] and page.evaluate("() => document.getElementById('menu').hidden")
           and "Đã kéo các cửa sổ nằm ngoài màn hình về giữa" in page.evaluate("() => document.body.innerText"), (page.evaluate(CMDS), page.evaluate("() => document.getElementById('menu').hidden")))
        page.evaluate("() => { window.__sent = []; document.getElementById('menu').hidden = false; }"); page.wait_for_timeout(150)
        page.click("#pc-grid [data-pck=alttab]"); page.wait_for_timeout(200)
        ck("8 phím Windows cũ vẫn như cũ (Alt + Tab → lệnh alttab)", page.evaluate(CMDS) == ["alttab"], page.evaluate(CMDS))
        page.evaluate(HOOK, "pc"); page.wait_for_timeout(100)
        ck("bật lại chế độ máy PC không nhân đôi nút", page.evaluate("() => document.querySelectorAll('[data-pck=wins]').length") == 1, page.evaluate("() => document.querySelectorAll('[data-pck=wins]').length"))
        page.evaluate("() => { LANG = 'en'; document.getElementById('pc-grid').remove(); }"); page.evaluate(HOOK, "pc")
        ck("tiếng Anh: 'Bring off-screen windows back'", "Bring off-screen windows back" in page.evaluate("() => document.querySelector('[data-pck=wins]').innerText"))
        ck("không lỗi JavaScript", not errs, errs)
        ctx.close()
    br.close()
print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
