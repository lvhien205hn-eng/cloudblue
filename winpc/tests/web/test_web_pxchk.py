# -*- coding: utf-8 -*-
"""Thử 🔎 KIỂM TRA PROXY trên web (27/11h): nút ở dòng 'Proxy dân cư' · 'Proxy của bạn' (tất cả / từng proxy) · #kiem-tra-proxy ·
   đọc nhiều dạng dòng · bỏ trùng · IP mạng nhà báo ngay không gửi · gửi theo lô 20 · LIVE / DIE / chép · lỗi 429 không tính là DIE.
   Chrome thật (Playwright) + Supabase giả (fake_supabase.js) + /api/px-check giả; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_pxchk.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


def iso(sec):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


PRICES = {"v6": {"1": {"1": 5000, "7": 25000, "30": 80000}, "3": {"30": 35000}}}
SHOP = {"sell": True, "admin": False, "prices": PRICES, "port": 18899, "max_qty": 20, "note": "", "fb4": False, "grace_h": 24, "v": 63,
        "stock": {"v6": {"1": 3, "2": 6, "3": 9, "4": 12, "5": 15}, "v4": {}}}
MY = {"sell": True, "grace_h": 24, "v": 63, "items": [
    {"id": 5, "kind": "v6", "share": 1, "host": "203.0.113.50", "port": 18899, "user": "pxabc12345", "pass": "a1b2c3d4e5f60718", "ip": "2001:db8:5:1::a1",
     "label": "", "until": iso(5 * 86400), "expired": False, "delete_at": iso(6 * 86400), "rot": None, "iplink": None, "online": True,
     "prices": {"30": 80000}, "created_at": iso(-86400)},
    {"id": 6, "kind": "v6", "share": 3, "host": "203.0.113.50", "port": 18899, "user": "pxdef67890", "pass": "ffeeddccbbaa9988", "ip": "", "label": "",
     "until": iso(-3600), "expired": True, "delete_at": iso(20 * 3600), "rot": None, "iplink": None, "online": True, "prices": {"30": 35000}, "created_at": iso(-8 * 86400)}]}
HOOK = """(() => { const V = window.__PX; const c = v => JSON.parse(JSON.stringify(v));
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    vm_shop_info: () => ({ sell: false, plans: [], images: [] }), px_shop_info: () => c(V.shop), px_my: () => c(V.my) }); })();"""

FAKE_RES = {
    "203.0.113.50": {"live": True, "s5": {"ok": True, "ms": 640}, "http": {"ok": True, "ms": 700}, "ip": "2001:db8:5:1::a1", "fam": 6, "ms": 640, "cc": "VN", "city": "Hanoi", "org": "FPT Telecom"},
    "198.51.100.20": {"live": True, "s5": {"ok": True, "ms": 900}, "ip": "198.51.100.20", "fam": 4, "ms": 900, "cc": "VN", "org": "<img src=x onerror=window.__xss2=1>"},
    "198.51.100.21": {"live": False, "s5": {"ok": False, "err": "BAD_AUTH"}, "http": {"ok": False, "err": "BAD_AUTH"}, "err": "BAD_AUTH"},
    "198.51.100.22": {"live": False, "http": {"ok": False, "err": "REFUSED"}, "err": "REFUSED"},
    "2001:db8::5": {"live": False, "err": "NO_V6"},
    "198.51.100.23": {"live": False, "s5": {"ok": False, "err": "TIMEOUT"}, "http": {"ok": False, "err": "S5_2"}, "err": "TIMEOUT"},
}


class Site:
    def __init__(self, browser, html, admin, px, path="/", vp=(1360, 900)):
        self.errors = []; self.api = []; self.api429_after = None
        self.ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {"product_list": [], "products": [], "cloud_phones": [], "pc_machines": []}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__PX = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps(px), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" and "Failed to load resource" not in m.text else None)
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message), d.dismiss()))
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2200)
        self.js("() => { navigator.clipboard.writeText = v => { window.__cp = v; return Promise.resolve(); }; }")

    def route(self, route):
        u = route.request.url
        if u.split("#")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        if u == ORIGIN + "/api/px-check":
            b = json.loads(route.request.post_data or "{}")
            self.api.append({"body": b, "auth": route.request.headers.get("authorization"), "method": route.request.method})
            if self.api429_after is not None and len(self.api) > self.api429_after:
                return route.fulfill(status=429, content_type="application/json", body=json.dumps({"ok": False, "error": "SLOW_DOWN"}))
            res = [FAKE_RES.get(it.get("h"), {"live": True, "s5": {"ok": True, "ms": 100}, "http": {"ok": True, "ms": 120}, "ip": "198.51.100.99", "fam": 4, "ms": 100}) for it in b.get("items", [])]
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "results": res}))
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def val(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.value : null; }", sel)
    def vis(self, sel): return self.js("q => { const e = document.querySelector(q); if (!e) return false; const r = e.getBoundingClientRect(); return !e.closest('[hidden]') && r.width > 0 && r.height > 0; }", sel)
    def wait_done(self, ms=6000):
        self.page.wait_for_function("() => { const g = document.getElementById('pxc-go'); const s = document.getElementById('pxc-st'); return g && !g.disabled && s && /Xong|Checked/.test(s.textContent); }", timeout=ms)
    def close(self): self.ctx.close()


def data(**kw):
    d = {"shop": json.loads(json.dumps(SHOP)), "my": json.loads(json.dumps(MY))}
    d.update(kw)
    return d


LINES = [
    "203.0.113.50:18899:pxabc12345:a1b2c3d4e5f60718",      # 1 LIVE (IPv6, SOCKS5 + HTTP)
    "socks5://u1:p1@198.51.100.20:1080",                    # 2 LIVE (chỉ SOCKS5) · nhà mạng lạ (<img>) phải thành chữ
    "192.168.77.10:8899:p25:MatKhauNoiBo",                  # 3 mạng nhà → báo ngay, KHÔNG gửi
    "dong nay sai",                                         # 4 sai định dạng
    "user9:pass9@198.51.100.21:3128",                       # 5 sai mật khẩu
    "http://198.51.100.22:8080",                            # 6 chỉ HTTP, cổng đóng
    "203.0.113.50:18899:pxabc12345:a1b2c3d4e5f60718",      # 7 trùng dòng 1 → không gửi lại
    "[2001:db8::5]:1080:u:p",                               # 8 IPv6 trong [ ]
    "u2:p2:198.51.100.23:8000",                             # 9 dạng user:pass:host:port
    "# dòng ghi chú",                                       # bỏ qua
]


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

        print("1. Dòng 'Proxy dân cư' → nút Kiểm tra proxy")
        s = Site(br, html, False, data())
        ck("dòng sản phẩm có nút '🔎 Kiểm tra proxy'", "Kiểm tra proxy" in (s.txt("#grid .m3-row.px") or ""), s.txt("#grid .m3-row.px"))
        s.page.click("#grid .m3-row.px [data-pxchk]"); s.page.wait_for_timeout(300)
        d = s.txt("#pxdlg .dlg") or ""
        ck("bấm → mở hộp Kiểm tra proxy (KHÔNG mở hộp mua)", "Kiểm tra proxy" in d and not s.vis("#pxb-pay") and s.vis("#pxc-in") and s.val("#pxc-in") == "", d[:300])
        ck("3 kiểu: Tự nhận (cả 2, mặc định) / SOCKS5 / HTTP", s.txt("#pxc-m") and "Tự nhận" in s.txt("#pxc-m") and s.js("() => document.querySelector('#pxc-m .on').dataset.pxcm") == "auto")
        s.page.click("#pxc-go"); s.page.wait_for_timeout(150)
        ck("bấm Kiểm tra khi ô trống → nhắc dán proxy, không gọi máy chủ", "Dán proxy" in (s.txt("#pxc-st") or "") and not s.api, s.txt("#pxc-st"))

        print("2. Kiểm tra danh sách nhiều dạng")
        s.page.fill("#pxc-in", "\n".join(LINES)); s.page.click("#pxc-go"); s.wait_done()
        ck("gọi /api/px-check 1 lần (POST, kèm mã đăng nhập, kiểu auto)", len(s.api) == 1 and s.api[0]["method"] == "POST" and s.api[0]["auth"] == "Bearer x" and s.api[0]["body"]["mode"] == "auto", s.api)
        items = s.api[0]["body"]["items"] if s.api else []
        hosts = [i["h"] for i in items]
        ck("gửi 6 proxy (bỏ dòng trùng, dòng sai, dòng ghi chú, IP mạng nhà)", sorted(hosts) == sorted(["203.0.113.50", "198.51.100.20", "198.51.100.21", "198.51.100.22", "2001:db8::5", "198.51.100.23"]), items)
        ck("KHÔNG gửi mật khẩu proxy mạng nhà đi đâu", "MatKhauNoiBo" not in json.dumps(s.api), items)
        by = {i["h"]: i for i in items}
        ck("đọc đúng: socks5://u1:p1@… → SOCKS5, user u1, pass p1, cổng 1080", by.get("198.51.100.20") == {"h": "198.51.100.20", "p": 1080, "u": "u1", "w": "p1", "t": "socks5"}, by.get("198.51.100.20"))
        ck("đọc đúng: http://host:port → chỉ HTTP, không user", by.get("198.51.100.22") == {"h": "198.51.100.22", "p": 8080, "u": "", "w": "", "t": "http"}, by.get("198.51.100.22"))
        ck("đọc đúng: user:pass@host:port", by.get("198.51.100.21", {}).get("u") == "user9" and by["198.51.100.21"]["w"] == "pass9" and by["198.51.100.21"]["p"] == 3128, by.get("198.51.100.21"))
        ck("đọc đúng: user:pass:host:port", by.get("198.51.100.23", {}).get("u") == "u2" and by["198.51.100.23"]["w"] == "p2" and by["198.51.100.23"]["p"] == 8000, by.get("198.51.100.23"))
        ck("đọc đúng: [IPv6]:port:user:pass", by.get("2001:db8::5", {}).get("p") == 1080 and by["2001:db8::5"]["u"] == "u", by.get("2001:db8::5"))
        st = s.txt("#pxc-st") or ""
        ck("tóm tắt: Xong 9 proxy · LIVE 3 · DIE 6", "Xong 9 proxy" in st and "LIVE 3" in st and "DIE 6" in st, st)
        live, die = s.val("#pxc-live") or "", s.val("#pxc-die") or ""
        ck("ô LIVE = dòng gốc của proxy sống (kể cả dòng trùng)", live.split("\n") == [LINES[0], LINES[1], LINES[6]], live)
        ck("ô DIE = dòng gốc của proxy chết / sai", die.split("\n") == [LINES[2], LINES[3], LINES[4], LINES[5], LINES[7], LINES[8]], die)
        tb = s.txt("#pxc-tbl") or ""
        ck("bảng: IP ra + IPv6 · nơi + nhà mạng · SOCKS5 ✓ / HTTP ✓ có ms", "2001:db8:5:1::a1 IPv6" in tb and "VN · Hanoi · FPT Telecom" in tb and "✓ 640 ms" in tb and "✓ 700 ms" in tb, tb[:900])
        ck("bảng: lý do chết dễ hiểu (mạng nhà · sai định dạng · sai mật khẩu · cổng đóng · máy kiểm tra chưa có IPv6 · quá thời gian · SOCKS5 mã 2)",
           all(x in tb for x in ["IP mạng nội bộ", "Dòng sai định dạng", "Sai user / mật khẩu", "Cổng đóng", "chưa có IPv6", "Quá thời gian", "SOCKS5 mã 2"]), tb[:1500])
        ck("tên nhà mạng lạ (<img onerror>) hiện thành chữ, không chạy mã", "<img src=x onerror" in tb and not s.js("() => window.__xss2"))
        s.page.click('[data-pxccp="live"]'); s.page.wait_for_timeout(150)
        ck("Chép LIVE → 3 dòng", s.js("() => window.__cp") == "\n".join([LINES[0], LINES[1], LINES[6]]), s.js("() => window.__cp"))
        s.page.click('[data-pxccp="die"]'); s.page.wait_for_timeout(150)
        ck("Chép DIE → 6 dòng", (s.js("() => window.__cp") or "").count("\n") == 5)

        print("3. Kiểu SOCKS5 · nhiều dòng chia lô 20 · quá tần suất")
        s.page.click('#pxc-m [data-pxcm="socks5"]')
        many = ["198.51.100.%d:1080:u:p" % i for i in range(30, 75)]                  # 45 dòng
        s.api.clear(); s.page.fill("#pxc-in", "\n".join(many)); s.page.click("#pxc-go"); s.wait_done()
        ck("45 proxy → 3 lần gọi (20 + 20 + 5), kiểu socks5", sorted(len(a["body"]["items"]) for a in s.api) == [5, 20, 20] and all(a["body"]["mode"] == "socks5" for a in s.api), [len(a["body"]["items"]) for a in s.api])
        ck("LIVE 45", "LIVE 45" in (s.txt("#pxc-st") or ""), s.txt("#pxc-st"))
        s.api.clear(); s.api429_after = 1; s.page.fill("#pxc-in", "\n".join(many)); s.page.click("#pxc-go"); s.wait_done()
        st = s.txt("#pxc-st") or ""
        ck("bị giới hạn tần suất (429) → lô sau báo 'chưa kiểm tra được', KHÔNG tính là DIE", "LIVE 20" in st and "DIE 0" in st and "chưa kiểm tra được 25" in st, st)
        s.api429_after = None
        s.page.fill("#pxc-in", "\n".join("198.51.100.1:%d" % (1000 + i) for i in range(205))); s.api.clear(); s.page.click("#pxc-go"); s.wait_done()
        ck("quá 200 dòng → chỉ kiểm tra 200, báo bỏ 5 dòng", "Xong 200 proxy" in (s.txt("#pxc-st") or "") and "bỏ 5 dòng" in (s.txt("#pxc-st") or "") and sum(len(a["body"]["items"]) for a in s.api) == 200, s.txt("#pxc-st"))
        ck("không lỗi trang / hộp thoại trình duyệt", not s.errors, s.errors)
        s.close()

        print("4. Proxy của bạn → Kiểm tra")
        s = Site(br, html, False, data())
        ck("proxy còn hạn có nút Kiểm tra, proxy hết hạn thì không", s.js("() => !!document.querySelector('#px-mine [data-pxchk=\"5\"]')") and not s.js("() => !!document.querySelector('#px-mine [data-pxchk=\"6\"]')"))
        s.page.click('#px-mine [data-pxchk="all"]'); s.wait_done()
        ck("'Kiểm tra' ở đầu khung → điền sẵn proxy còn hạn + tự chạy", s.val("#pxc-in") == "203.0.113.50:18899:pxabc12345:a1b2c3d4e5f60718" and len(s.api) == 1 and "LIVE 1" in (s.txt("#pxc-st") or ""), (s.val("#pxc-in"), s.api))
        s.page.click("#pxdlg [data-pxx]"); s.page.wait_for_timeout(200); s.api.clear()
        s.page.click('#px-mine [data-pxchk="5"]'); s.wait_done()
        ck("'Kiểm tra' trên 1 proxy → chỉ proxy đó", len(s.api) == 1 and [i["u"] for i in s.api[0]["body"]["items"]] == ["pxabc12345"], s.api)
        s.close()

        print("5. Mở bằng đường dẫn #kiem-tra-proxy · chưa đăng nhập")
        s = Site(br, html, False, data(), path="/#kiem-tra-proxy")
        s.page.wait_for_timeout(1200)
        ck("cloudblue.vn/#kiem-tra-proxy → mở thẳng hộp Kiểm tra proxy", s.vis("#pxc-in"), s.txt("#pxdlg"))
        s.close()
        s = Site(br, html, None, data(my={"items": []}))
        s.js("() => window.PXSHOP.check('', false)"); s.page.wait_for_timeout(300)
        ck("chưa đăng nhập → mở hộp đăng nhập, không mở công cụ", s.vis("#auth") and not s.vis("#pxc-in"), (s.vis("#auth"), s.vis("#pxc-in")))
        ck("không lỗi trang", not s.errors, s.errors)
        s.close()
        br.close()
    print("\nKẾT QUẢ: %d đạt, %d lỗi" % (OK, FAIL))
    sys.exit(1 if FAIL else 0)


main()
