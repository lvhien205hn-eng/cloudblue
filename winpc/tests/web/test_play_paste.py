# -*- coding: utf-8 -*-
"""THỬ bằng TRÌNH DUYỆT THẬT: DÁN CHỮ vào máy PC trong play.html (23/11b).
   Ctrl+V → gói Dán kiểu 1 (máy tự chọn phím dán theo cửa sổ: Konsole Ctrl+Shift+V…) · Ctrl+Shift+V → gói Dán kiểu 2 (máy bấm đúng Ctrl+Shift+V)
   · không gửi phím V sang máy (chỉ phím Ctrl / Shift thật) · Cloud Phone (không phải máy PC): Ctrl+Shift+V vẫn là kiểu 1 như cũ.
   Chạy:  python3 winpc/tests/web/test_play_paste.py [play.html]"""
import http.server, os, sys, tempfile, threading
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
  Object.defineProperty(navigator, "clipboard", {value: {readText: async () => "echo Tiếng Việt", writeText: async () => {}}, configurable: true});
  document.activeElement && document.activeElement.blur && document.activeElement.blur();
}"""
SENT = """() => window.__sent.map(([t, b]) => t === T.CLIP ? ["clip", b[0], new TextDecoder().decode(new Uint8Array(b.slice(1)))] : (t === T.KEY ? ["key", b[0], (b[1] << 24 | b[2] << 16 | b[3] << 8 | b[4]) >>> 0] : [t]))"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:300]))
    page.goto(URL); page.wait_for_timeout(800)
    page.evaluate(HOOK, "pc")
    page.keyboard.down("Control"); page.keyboard.press("KeyV"); page.keyboard.up("Control"); page.wait_for_timeout(300)
    s1 = page.evaluate(SENT)
    clips = [x for x in s1 if x[0] == "clip"]
    ck("máy PC: Ctrl+V → 1 gói Dán kiểu 1 với chữ của máy mình (có dấu nguyên vẹn)", clips == [["clip", 1, "echo Tiếng Việt"]], s1)
    ck("… gửi phím Ctrl thật (nhấn + nhả) nhưng KHÔNG gửi phím V (máy không bị dán 2 lần)", [x[1] for x in s1 if x[0] == "key"] == [0, 1], s1)
    page.evaluate("() => { window.__sent = []; }")
    page.keyboard.down("Control"); page.keyboard.down("Shift"); page.keyboard.press("KeyV"); page.keyboard.up("Shift"); page.keyboard.up("Control")
    page.wait_for_timeout(300)
    s2 = page.evaluate(SENT)
    ck("máy PC: Ctrl+Shift+V (Konsole máy Linux) → gói Dán kiểu 2 (máy bấm đúng Ctrl+Shift+V), không gửi phím V",
       [x for x in s2 if x[0] == "clip"] == [["clip", 2, "echo Tiếng Việt"]] and len([x for x in s2 if x[0] == "key"]) == 4, s2)
    page.evaluate(HOOK, "phone")
    page.keyboard.down("Control"); page.keyboard.down("Shift"); page.keyboard.press("KeyV"); page.keyboard.up("Shift"); page.keyboard.up("Control")
    page.wait_for_timeout(300)
    s3 = page.evaluate(SENT)
    ck("Cloud Phone: Ctrl+Shift+V vẫn là gói Dán kiểu 1 như cũ", [x for x in s3 if x[0] == "clip"] == [["clip", 1, "echo Tiếng Việt"]], s3)
    ck("không lỗi JavaScript", not errs, errs)
    br.close()
print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
