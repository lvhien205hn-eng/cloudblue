# -*- coding: utf-8 -*-
"""THỬ bằng TRÌNH DUYỆT THẬT: 🗗 TAB CỬA SỔ NHỎ trong play.html (trang điều khiển Cloud Phone trên web, 23/11 — như Redfinger):
   nút trên thanh dưới (bấm = Thu nhỏ tab, giữ = mở ⋯ ở mục Tab cửa sổ nhỏ), mục ⋯ có 4 nút (Thu nhỏ / Sắp xếp / Phóng to tab / 23/11b Mở lại vừa khung),
   gửi đúng POST /cpapi/<máy>/win {do}, hiện câu của máy chủ (English: câu dịch), máy chủ cũ (404) → câu dễ hiểu, máy PC → ẩn hết.
   cpapi giả chạy ở cổng khác (như phone.cloudblue.vn thật → có CORS).
   Chạy:  python3 winpc/tests/web/test_play_win.py [play.html] [thư mục ảnh]"""
import http.server, json, os, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "play.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="cbwin-shots-")
os.makedirs(SHOTS, exist_ok=True)
PID = "00000000-0000-4000-8000-000000000001"
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:600], flush=True)


S = {"posts": [], "old": False}
MSG = {"mini": (200, {"ok": True, "n": 1, "msg": "Đã thu nhỏ Roblox (1 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ."}),
       "tile": (200, {"ok": True, "n": 3, "msg": "Đã xếp 3 tab nhỏ (1 cột × 3 hàng). Màn nhỏ nên tab chồng nhau — tăng 📐 Độ rộng nhỏ nhất (VD 600 dp) để tab không đè nhau."}),
       "full": (409, {"error": "Chưa có tab nhỏ nào đang hiện trên màn hình."}),
       "refit": (200, {"ok": True, "id": 7, "b": [0, 48, 720, 488], "msg": "Đã mở lại Roblox ngay trong cửa sổ — game vẽ vừa khung (game vừa khởi động lại, vào lại trận nếu cần)."})}


class Api(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def js(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.cors(); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        self.js(404, {"error": "Không có chức năng này."})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); b = json.loads(self.rfile.read(n) or b"{}")
        if self.path == f"/cpapi/{PID}/win" and not S["old"]:
            S["posts"].append(b.get("do")); code, j = MSG.get(b.get("do"), (400, {"error": "Thiếu việc cần làm (thu nhỏ / sắp xếp / phóng to)."}))
            return self.js(code, j)
        self.js(404, {"error": "Không có chức năng này."})


api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api); threading.Thread(target=api.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{api.server_address[1]}"
site = tempfile.mkdtemp(prefix="cbsite-")
open(os.path.join(site, "play.html"), "w", encoding="utf-8").write(open(PLAY, encoding="utf-8").read())


class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=site, **k)
    def log_message(self, *a): pass


hs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Q); threading.Thread(target=hs.serve_forever, daemon=True).start()
URL = f"http://localhost:{hs.server_address[1]}/play.html?test=1&id={PID}&api={API}&ws=ws://127.0.0.1:9/v2/stream&name=M%C3%A1y%20th%E1%BB%AD"


def wait(fn, t=8.0):
    end = time.time() + t
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(0.1)
    return fn()


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for lang in ("vi", "en"):
        print(f"— {'Tiếng Việt' if lang == 'vi' else 'English'}")
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(f"try {{ localStorage.setItem('br_lang', '{lang}'); }} catch (e) {{}}")
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        S.update(posts=[], old=False)
        page.goto(URL); page.wait_for_timeout(900)
        T = (lambda vi, en: vi if lang == "vi" else en)
        toast = lambda want: wait(lambda: (lambda x: x if want in x else "")(page.inner_text("#toast-t")), 6) or page.inner_text("#toast-t")

        ck("thanh dưới có nút Thu nhỏ tab (biểu tượng cửa sổ), tên đúng ngôn ngữ", page.is_visible("#win-btn")
           and page.get_attribute("#win-btn", "title") == T("Thu nhỏ tab (giữ: sắp xếp / phóng to)", "Minimize tab (hold: arrange / maximize)"),
           page.get_attribute("#win-btn", "title"))
        box = page.eval_on_selector(".bar", "b => { const r = b.getBoundingClientRect(); return [r.width, b.scrollWidth]; }")
        ck("thanh dưới vừa màn điện thoại 390 px (không tràn)", box[1] <= box[0] + 1, box)
        page.click("#win-btn")
        t = toast(T("Đã thu nhỏ Roblox", "Minimized Roblox"))
        ck("bấm nút → POST {do: mini} 1 lần + hiện câu máy chủ", S["posts"] == ["mini"] and T("Đã thu nhỏ Roblox (1 tab nhỏ). Kéo thanh", "Minimized Roblox (1 small tabs). Drag") in t, (S["posts"], t))
        page.screenshot(path=os.path.join(SHOTS, f"{lang}-win-1-thu-nho.png"))

        page.evaluate("document.getElementById('menu').hidden = false"); page.wait_for_timeout(200)
        page.eval_on_selector("#win-sec", "x => x.scrollIntoView()"); page.wait_for_timeout(150)
        btns = page.eval_on_selector_all("#win-grid button", "bs => bs.map(b => [b.dataset.a, b.innerText.trim()])")
        ck("⋯ có mục Tab cửa sổ nhỏ: 4 nút Thu nhỏ / Sắp xếp / Phóng to tab / Mở lại vừa khung + lời chỉ cách kéo + cách sửa game tràn viền",
           [b[0] for b in btns] == ["winmini", "wintile", "winfull", "winrefit"] and [b[1] for b in btns] == [T("Thu nhỏ tab", "Minimize tab"), T("Sắp xếp tab", "Arrange tabs"),
                                                                                    T("Phóng to tab", "Maximize tab"), T("Mở lại vừa khung", "Refit to window")]
           and page.inner_text("#win-sec") == T("Tab cửa sổ nhỏ", "Small tab windows") and T("Kéo thanh trên cùng", "Drag a window") in page.inner_text("#win-d")
           and T("Mở lại vừa khung (game khởi động lại", "Refit to window (the game restarts") in page.inner_text("#win-d"), (btns, page.inner_text("#win-d")))
        page.screenshot(path=os.path.join(SHOTS, f"{lang}-win-2-menu.png"))
        page.click('#win-grid [data-a="wintile"]')
        t = toast(T("Đã xếp 3 tab", "Arranged 3 small tabs"))
        ck("Sắp xếp tab → POST tile, menu đóng, câu xếp chồng + cách khắc phục", S["posts"][-1] == "tile" and page.is_hidden("#menu")
           and T("Màn nhỏ nên tab chồng nhau", "so they overlap") in t, (S["posts"], t))
        page.evaluate("document.getElementById('menu').hidden = false"); page.click('#win-grid [data-a="winfull"]')
        t = toast(T("Chưa có tab nhỏ nào", "No small tab"))
        ck("Phóng to tab khi chưa có cửa sổ → báo lỗi máy chủ (dịch đúng)", S["posts"][-1] == "full" and T("Chưa có tab nhỏ nào đang hiện trên màn hình.", "No small tab is on the screen.") in t, t)

        dlg = []
        def on_dialog(d, keep=dlg): keep.append(d.message); d.dismiss() if len(keep) == 1 else d.accept()
        page.on("dialog", on_dialog)
        page.evaluate("document.getElementById('menu').hidden = false"); page.click('#win-grid [data-a="winrefit"]'); page.wait_for_timeout(400)
        ck("Mở lại vừa khung → hỏi trước (game sẽ khởi động lại); bấm Huỷ → không gửi gì", len(dlg) == 1 and S["posts"][-1] == "full"
           and T("Game sẽ khởi động lại", "The game restarts") in dlg[0], (dlg, S["posts"]))
        page.evaluate("document.getElementById('menu').hidden = false"); page.click('#win-grid [data-a="winrefit"]')
        t = toast(T("Đã mở lại Roblox", "Reopened Roblox"))
        ck("đồng ý → POST {do: refit} + câu máy chủ (dịch đúng)", len(dlg) == 2 and S["posts"][-1] == "refit"
           and T("ngay trong cửa sổ — game vẽ vừa khung", "inside its window — the game now fits") in t, (dlg, S["posts"], t))
        page.remove_listener("dialog", on_dialog)
        page.screenshot(path=os.path.join(SHOTS, f"{lang}-win-2b-mo-lai-vua-khung.png"))

        n0 = len(S["posts"])
        page.dispatch_event("#win-btn", "pointerdown"); page.wait_for_timeout(750); page.dispatch_event("#win-btn", "pointerup")
        page.dispatch_event("#win-btn", "click"); page.dispatch_event("#menu", "click")       # cú nhả tay: vào nút hoặc vào nền ⋯ vừa mở
        page.wait_for_timeout(300)
        top = page.evaluate("(() => { const r = document.getElementById('win-sec').getBoundingClientRect(); return r.top; })()")
        ck("giữ nút → mở ⋯ cuộn tới mục Tab cửa sổ nhỏ, KHÔNG thu nhỏ, nhả tay không đóng ⋯", not page.is_hidden("#menu") and len(S["posts"]) == n0 and top < 500,
           (len(S["posts"]), n0, top))
        page.screenshot(path=os.path.join(SHOTS, f"{lang}-win-3-giu-nut.png"))
        page.evaluate("document.getElementById('menu').hidden = true")
        page.click("#win-btn"); page.wait_for_timeout(300)
        ck("bấm thường sau khi giữ → lại thu nhỏ bình thường", S["posts"][-1] == "mini" and len(S["posts"]) == n0 + 1, S["posts"])

        S["old"] = True; page.click("#win-btn")
        t = toast(T("Máy chủ của máy này chưa có", "doesn't have this feature"))
        ck("máy chủ cũ (404) → 'Máy chủ của máy này chưa có tính năng này'", T("Máy chủ của máy này chưa có tính năng này", "This phone's server doesn't have this feature yet") in t, t)
        S["old"] = False

        page.evaluate("document.body.classList.add('pcm')")
        ck("máy PC (VPS GPU) → ẩn nút trên thanh + mục Tab cửa sổ nhỏ", page.eval_on_selector("#win-btn", "b => getComputedStyle(b).display") == "none"
           and page.eval_on_selector("#win-grid", "b => getComputedStyle(b).display") == "none" and page.eval_on_selector("#win-sec", "b => getComputedStyle(b).display") == "none")
        page.evaluate("document.body.classList.remove('pcm')")
        ck("không lỗi JavaScript", not errs, errs)
        ctx.close()
    br.close()
api.shutdown(); hs.shutdown()
print(f"\nplay.html 🗗 Tab cửa sổ nhỏ: {OK[0]}/{OK[1]} đạt · ảnh: {SHOTS}")
sys.exit(0 if OK[0] == OK[1] else 1)
