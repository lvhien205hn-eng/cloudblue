# -*- coding: utf-8 -*-
"""THỬ bằng TRÌNH DUYỆT THẬT: hộp 🌐 Proxy trong play.html (trang điều khiển Cloud Phone trên web, 22/11).
   cpapi giả (GET/POST /cpapi/<máy>/proxy + /cpapi/job) chạy ở cổng khác (như phone.cloudblue.vn thật → có CORS).
   Chạy:  python3 winpc/tests/web/test_play_proxy.py [play.html] [thư mục ảnh]"""
import http.server, json, os, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "play.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="cbproxy-shots-")
PID = "00000000-0000-4000-8000-000000000001"
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:600], flush=True)


# ---------------- cpapi giả ----------------
S = {"get": 0, "posts": [], "jobs": {}, "mode": "proxy", "code": 200}
STATE = {
    "proxy": {"set": True, "kind": "auto", "show": "9.8.7.6:1080:khach:••••", "online": True, "has_pass": True,
              "state": {"mode": "proxy", "kind": "socks5", "ip": "5.6.7.8", "ms": 80, "alive": True}},
    "direct": {"set": True, "kind": "http", "show": "9.8.7.6:3128", "online": True,
               "state": {"mode": "direct", "kind": "http", "err": "proxy báo SAI user / mật khẩu (407)", "alive": True}},
    "crashed": {"set": True, "kind": "auto", "show": "9.8.7.6:1080", "online": True, "state": {"mode": "crashed", "err": "iptables lỗi", "alive": False}},
    "none": {"set": False, "kind": "auto", "show": "", "online": True, "state": None},
    "off": {"set": True, "kind": "socks5", "show": "1.2.3.4:1080:u:••••", "online": False, "state": None},
}


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
        if self.path.startswith("/cpapi/job"):
            jid = self.path.split("id=", 1)[1]
            j = S["jobs"].get(jid, {"state": "error", "msg": "Không có việc này."})
            return self.js(200, j)
        if self.path == f"/cpapi/{PID}/proxy":
            S["get"] += 1
            if S["code"] != 200: return self.js(S["code"], {"error": "Chỉ chủ máy mới xem / đặt được proxy của máy này."})
            return self.js(200, STATE[S["mode"]])
        self.js(404, {"error": "Không có chức năng này."})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); b = json.loads(self.rfile.read(n) or b"{}")
        if self.path == f"/cpapi/{PID}/proxy":
            S["posts"].append(b); jid = "j%d" % len(S["posts"])
            msg = {"set": "Đã BẬT proxy — IP ra: 5.6.7.8 · 80 ms", "off": "Đã TẮT proxy — máy đi mạng thường.", "again": "Đã BẬT proxy — IP ra: 5.6.7.8 · 81 ms"}.get(b.get("do"), "?")
            S["jobs"][jid] = {"state": "done", "msg": msg, "title": "Proxy"}
            if b.get("do") == "off": S["mode"] = "none"
            return self.js(200, {"job": jid})
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
        ctx = br.new_context(viewport={"width": 420, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(f"try {{ localStorage.setItem('br_lang', '{lang}'); }} catch (e) {{}}")
        page = ctx.new_page(); errs = []; dialogs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:300]))
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        S.update(get=0, posts=[], jobs={}, mode="proxy", code=200)
        page.goto(URL); page.wait_for_timeout(800)
        T = (lambda vi, en: vi if lang == "vi" else en)

        def reopen():
            if page.is_visible("#pxdlg"): page.click('[data-a="pxclose"]')
            page.evaluate("document.getElementById('menu').hidden = false"); page.click('#menu [data-a="proxy"]')

        page.evaluate("document.getElementById('menu').hidden = false")
        btns = page.eval_on_selector_all("#menu .grid:last-of-type button", "bs => bs.map(b => b.dataset.a)")
        ck("Công cụ có nút Proxy ngay sau Root (8 nút, đủ 2 hàng)", "proxy" in btns and btns.index("proxy") == btns.index("root") + 1 and len(btns) == 8, btns)
        page.click('#menu [data-a="proxy"]')
        ck("bấm Proxy → mở hộp 🌐 Proxy, hỏi máy chủ", wait(lambda: page.is_visible("#pxdlg") and S["get"] >= 1), S)
        cur = wait(lambda: (lambda t: t if "9.8.7.6" in t else "")(page.inner_text("#px-cur")))
        ck("hiện proxy đang dùng (che mật khẩu) + kiểu thật SOCKS5", cur == "9.8.7.6:1080:khach:•••• · SOCKS5", cur)
        st = page.inner_text("#px-s")
        ck("trạng thái: đang chạy qua proxy · IP ra · ms", st == T("✅ Đang chạy qua proxy · IP ra 5.6.7.8 · 80 ms", "✅ Running through the proxy · exit IP 5.6.7.8 · 80 ms"), st)
        ck("có nút Tắt proxy + Áp dụng lại", page.is_visible("#px-off") and page.is_visible("#px-again"))
        page.screenshot(path=os.path.join(SHOTS, f"proxy-{lang}-1-dang-chay.png"))
        if lang == "en":
            ck("chữ trong hộp đã dịch", page.inner_text("#pxdlg .sec") == "New proxy" and page.inner_text("#px-save") == "Save"
               and page.inner_text('#px-kind [data-kind="auto"]') == "Auto", page.inner_text("#pxdlg"))

        # nhập sai / thiếu → không gửi
        page.click("#px-save"); page.wait_for_timeout(200)
        ck("ô trống + Lưu → nhắc dán proxy, không gửi", not S["posts"] and T("Dán proxy vào ô trước", "Paste the proxy first") in page.inner_text("#toast-t"), page.inner_text("#toast-t"))
        page.fill("#px-in", "1.2.3.4 8080 u p"); page.click("#px-save"); page.wait_for_timeout(200)
        ck("có dấu cách → nhắc đúng dạng, không gửi", not S["posts"] and "IP:Port" in page.inner_text("#toast-t"), page.inner_text("#toast-t"))

        # lưu proxy HTTP
        page.fill("#px-in", "1.2.3.4:8080:khach:Mk#1")
        page.click('#px-kind [data-kind="http"]')
        ck("chọn HTTP → nút HTTP sáng, aria-checked", page.get_attribute('#px-kind [data-kind="http"]', "aria-checked") == "true"
           and "on" in page.get_attribute('#px-kind [data-kind="http"]', "class") and "on" not in (page.get_attribute('#px-kind [data-kind="auto"]', "class") or ""))
        g0 = S["get"]
        page.press("#px-in", "Enter")
        ck("Enter → gửi {do:set, url, kind:http}", wait(lambda: S["posts"]) and S["posts"][0] == {"do": "set", "url": "1.2.3.4:8080:khach:Mk#1", "kind": "http"}, S["posts"])
        ck("ô nhập được xoá ngay sau khi gửi (không giữ mật khẩu)", wait(lambda: page.input_value("#px-in") == ""), page.input_value("#px-in"))
        t = wait(lambda: (lambda x: x if ("xong" in x or "done" in x) else "")(page.inner_text("#toast-t")), 8)
        ck("xong → thông báo “Proxy xong: Đã BẬT proxy — IP ra …”", t == T("Proxy xong: Đã BẬT proxy — IP ra: 5.6.7.8 · 80 ms", "Proxy done: Proxy ON — exit IP: 5.6.7.8 · 80 ms"), t)
        ck("xong → hỏi lại trạng thái", wait(lambda: S["get"] > g0), (g0, S["get"]))
        ck("nút bấm lại được sau khi xong", wait(lambda: not page.is_disabled("#px-save")))

        # áp dụng lại
        page.click("#px-again")
        ck("Áp dụng lại → gửi {do:again}", wait(lambda: len(S["posts"]) == 2) and S["posts"][1] == {"do": "again"}, S["posts"])
        wait(lambda: not page.is_disabled("#px-again"), 8)

        # trạng thái lỗi
        for mode, want in (("direct", T("⚠ Proxy chưa dùng được: proxy báo SAI user / mật khẩu (407) — máy tạm đi mạng thường, tự thử lại mỗi 15 giây.",
                                        "⚠ The proxy doesn't work yet: proxy báo SAI user / mật khẩu (407) — the phone uses the normal network for now and retries every 15 s.")),
                           ("crashed", T("❌ Proxy đã dừng: iptables lỗi — bấm Áp dụng lại.", "❌ The proxy stopped: iptables lỗi — tap Re-apply.")),
                           ("off", T("Máy đang tắt — proxy tự bật khi máy bật.", "The phone is off — the proxy turns on when it starts.")),
                           ("none", T("Máy đang đi mạng của máy chủ.", "The phone uses the server's network."))):
            S["mode"] = mode
            reopen()
            got = wait(lambda: (lambda x: x if x == want else "")(page.inner_text("#px-s")))
            ck(f"trạng thái {mode}: đúng câu" + (" + nút Tắt / Áp dụng lại ẩn" if mode == "none" else ""), got == want and (mode != "none" or (page.is_hidden("#px-off") and page.is_hidden("#px-again"))), page.inner_text("#px-s"))
            if mode == "direct":
                ck("trạng thái lỗi tô màu cảnh báo", "warn" in page.get_attribute("#px-s", "class"))
                ck("kiểu proxy mặc định theo proxy đang lưu (HTTP)", wait(lambda: page.get_attribute('#px-kind [data-kind="http"]', "aria-checked") == "true"))
                page.screenshot(path=os.path.join(SHOTS, f"proxy-{lang}-2-loi.png"))
            if mode == "none": ck("chưa dùng proxy: tiêu đề “Chưa dùng proxy”", page.inner_text("#px-cur") == T("Chưa dùng proxy", "No proxy"))

        # tắt proxy
        S["mode"] = "proxy"; reopen(); wait(lambda: page.is_visible("#px-off"))
        n = len(S["posts"]); page.click("#px-off")
        ck("Tắt proxy → hỏi lại trước khi tắt", wait(lambda: dialogs) and T("Tắt proxy?", "Turn the proxy off?") in dialogs[-1], dialogs)
        ck("đồng ý → gửi {do:off}", wait(lambda: len(S["posts"]) > n) and S["posts"][-1] == {"do": "off"}, S["posts"])
        ck("tắt xong → đóng hộp", wait(lambda: page.is_hidden("#pxdlg"), 8))

        # người được chia sẻ → 403
        S["code"] = 403; reopen()
        got = wait(lambda: (lambda x: x if "chủ máy" in x or "owner" in x else "")(page.inner_text("#px-cur")))
        ck("không phải chủ máy → báo, khoá ô nhập + nút Lưu", got == T("Chỉ chủ máy mới xem / đặt được proxy của máy này.", "Only the phone's owner can view or set its proxy.")
           and page.is_disabled("#px-save") and page.is_disabled("#px-in"), got)
        S["code"] = 200; page.click('[data-a="pxclose"]')

        # máy PC (VPS GPU): KHÔNG có Proxy
        page.evaluate("document.body.classList.add('pcm')")
        ck("chế độ máy PC (VPS GPU) → ẩn nút Proxy", page.eval_on_selector('#menu [data-a="proxy"]', "b => getComputedStyle(b).display") == "none")
        page.evaluate("document.body.classList.remove('pcm')")
        ck("không lỗi JavaScript", not errs, errs)
        ctx.close()
    br.close()
api.shutdown(); hs.shutdown()
print(f"\nplay.html 🌐 Proxy: {OK[0]}/{OK[1]} đạt · ảnh: {SHOTS}")
sys.exit(0 if OK[0] == OK[1] else 1)
