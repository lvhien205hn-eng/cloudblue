# -*- coding: utf-8 -*-
"""Thử phần 🌐 PROXY DÂN CƯ trên web (SQL v63): dòng sản phẩm · hộp mua · Proxy của bạn · gia hạn · Quản trị › 🌐 Proxy ·
   ô tài khoản PPPoE mã hoá (WebCrypto trên trang → giải lại bằng Node đúng thuật toán của cbpool/cust.go).
   Chrome thật (Playwright) + Supabase giả (fake_supabase.js) + hàm px_* giả trong trang; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_px.py [blueroblox-site/index.html]"""
import datetime, json, os, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0
H1 = "11111111-1111-4111-8111-111111111111"
# khoá THỬ (ngẫu nhiên, chỉ dùng cho bộ thử — giống cbpool/cbpool_test.go): khoá công khai đưa cho trang, khoá riêng để giải lại
TEST_D = "0RBspaOpwPNKqFgibkOSRRdG/ZnbpBiFp7pcLfsk5X8="
TEST_PK = "BJOI4IvJR8+Gt/Mxkvw37q5S/t4MJmE9PpXkdqeJvCF8GC4qaxk88SanKPp7X7zax2bikI3HsRbW3ASYIOS3ru0="
DEC_JS = r"""
import crypto from "node:crypto";
const [d, enc] = [process.argv[2], process.argv[3]];
const e = JSON.parse(enc);
const ecdh = crypto.createECDH("prime256v1"); ecdh.setPrivateKey(Buffer.from(d, "base64"));
const eph = Buffer.from(e.e, "base64"), shared = ecdh.computeSecret(eph);
const key = Buffer.from(crypto.hkdfSync("sha256", shared, eph, Buffer.from("cbpool-ppp-v1"), 32));
const iv = Buffer.from(e.i, "base64"), ct = Buffer.from(e.c, "base64");
const dc = crypto.createDecipheriv("aes-256-gcm", key, iv); dc.setAuthTag(ct.subarray(ct.length - 16));
console.log(Buffer.concat([dc.update(ct.subarray(0, ct.length - 16)), dc.final()]).toString("utf8"));
"""


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


def iso(sec):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


PRICES = {"v6": {"1": {"1": 5000, "7": 25000, "30": 80000}, "3": {"30": 35000}}, "v4": {"2": {"7": 30000, "30": 90000}}}
SHOP = {"sell": True, "admin": False, "prices": PRICES, "port": 18899, "max_qty": 20, "note": "Proxy FPT <b>Hà Nội</b>", "fb4": False, "grace_h": 24, "v": 63,
        "stock": {"v6": {"1": 3, "2": 6, "3": 9, "4": 12, "5": 15}, "v4": {"1": 2, "2": 4, "3": 6, "4": 8, "5": 10}}}
MY = {"sell": True, "grace_h": 24, "v": 63, "items": [
    {"id": 5, "kind": "v6", "share": 1, "host": "203.0.113.50", "port": 18899, "user": "pxabc12345", "pass": "a1b2c3d4e5f60718", "ip": "2001:db8:5:ac60::a1",
     "label": "<img src=x onerror=window.__xss=1>", "until": iso(5 * 86400), "expired": False, "delete_at": iso(6 * 86400),
     "rot": "http://203.0.113.50:18899/rotate?key=r0123456789abcdef0123456789abcdef", "iplink": "http://203.0.113.50:18899/ip?key=r0123", "online": True,
     "prices": {"1": 5000, "7": 25000, "30": 80000}, "created_at": iso(-86400)},
    {"id": 6, "kind": "v4", "share": 2, "host": "203.0.113.50", "port": 18899, "user": "pxdef67890", "pass": "ffeeddccbbaa9988", "ip": "203.0.113.11", "label": "",
     "until": iso(-3600), "expired": True, "delete_at": iso(20 * 3600), "rot": None, "iplink": None, "online": True, "prices": {"7": 30000, "30": 90000}, "created_at": iso(-8 * 86400)}]}
ADM = {"v": 63, "active": 2, "revenue_month": 160000, "stock": SHOP["stock"],
       "settings": {"sell": False, "pub_port": 18899, "pub_host": None, "prices": PRICES, "bw_kbps": 20000, "fb4": False, "sale4": True, "v6_units": 200, "max_qty": 20,
                    "max_conns": 64, "grace_h": 24, "note": ""},
       "hosts": [{"id": H1, "name": "cbvps-01", "status": "ready", "online": True, "px": True, "v6": "2001:db8:5:ac60::/64", "sess": [1, 2], "pk": TEST_PK,
                  "ppp_gen": 0, "ppp_ok": 0, "ppp_wait": False, "ppp_err": None, "ep": "203.0.113.50", "lan": "192.168.77.10", "acct": False,
                  "disc": {"ok": True, "ac": ["cbtest-ac"], "t": 1795760000}, "used6": 2, "used4": 1, "n": 3, "ver": "27/11g"}],
       "proxies": [{"id": 5, "user": "khach<b>A</b>", "email": "a@x.vn", "host": "cbvps-01", "kind": "v6", "unit": "s001", "share": 1, "username": "pxabc12345",
                    "ip": "2001:db8:5:ac60::a1", "until": iso(5 * 86400), "status": "active", "expired": False, "price": 80000, "created_at": iso(-86400), "label": ""},
                   {"id": 6, "user": "khachB", "email": "b@x.vn", "host": "cbvps-01", "kind": "v4", "unit": "1", "share": 2, "username": "pxdef67890",
                    "ip": "203.0.113.11", "until": iso(-3600), "status": "active", "expired": True, "price": 30000, "created_at": iso(-8 * 86400), "label": ""}]}

HOOK = """(() => { const V = window.__PX; const c = v => JSON.parse(JSON.stringify(v));
  const raise = m => ({ data: null, error: { code: 'P0001', message: m } });
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    vm_shop_info: () => ({ sell: false, plans: [], images: [] }),
    px_shop_info: () => c(V.shop),
    px_my: () => c(V.my),
    px_buy: a => V.buyErr ? raise(V.buyErr) : ({ ok: true, ids: [7, 8, 9], order: 'o-px', total: 90000 }),
    px_my_renew: a => ({ ok: true, id: a.p_id, until: new Date(Date.now() + 40 * 864e5).toISOString(), total: 80000 }),
    px_my_label: a => ({ ok: true }),
    px_admin_state: () => c(V.adm),
    px_admin_settings: a => { Object.assign(V.adm.settings, a.p_patch); return c(V.adm.settings); },
    px_admin_proxy: a => ({ ok: true, id: a.p_id }),
    px_admin_give: a => V.giveErr ? raise(V.giveErr) : ({ ok: true, ids: [11] }),
    px_admin_ppp: a => ({ ok: true, gen: 1, wait: true })
  }); })();"""


class Site:
    def __init__(self, browser, html, admin, px, path="/", vp=(1360, 900)):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {"product_list": [], "products": [], "cloud_phones": [], "pc_machines": []}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__PX = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps(px), HOOK))
        self.ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=ORIGIN)
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" and "Failed to load resource" not in m.text else None)
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message), d.dismiss()))
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2200)

    def route(self, route):
        u = route.request.url
        if u in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def calls(self, name): return self.js("n => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def vis(self, sel): return self.js("q => { const e = document.querySelector(q); if (!e) return false; const r = e.getBoundingClientRect(); return !e.closest('[hidden]') && r.width > 0 && r.height > 0; }", sel)
    def clip(self): return self.js("() => window.__cp")
    def close(self): self.ctx.close()


def data(**kw):
    d = {"shop": json.loads(json.dumps(SHOP)), "my": json.loads(json.dumps(MY)), "adm": json.loads(json.dumps(ADM))}
    d.update(kw)
    return d


def main():
    html = open(HTML, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="pxweb_"); dec = os.path.join(tmp, "dec.mjs"); open(dec, "w").write(DEC_JS)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

        print("1. Khách: dòng sản phẩm + hộp mua")
        s = Site(br, html, False, data())
        s.js("() => { navigator.clipboard.writeText = v => { window.__cp = v; return Promise.resolve(); }; }")
        row = s.txt("#grid .m3-row.px")
        ck("danh sách Sản phẩm có dòng 'Proxy dân cư' (từ 1.167đ / ngày = IPv6 share 3 · 35.000đ / 30 ngày · còn hàng · nút Mua ngay)",
           row and "Proxy dân cư" in row and "Còn hàng" in row and "Mua ngay" in row and "1.167" in row, row)
        ck("thanh mục có 'Proxy'", "Proxy" in (s.txt("#cats") or ""), s.txt("#cats"))
        s.page.click("#grid .m3-row.px button[data-pxbuy]"); s.page.wait_for_timeout(400)
        d = s.txt("#pxdlg .dlg") or ""
        ck("hộp mua: IPv6 + IPv4 · kiểu Riêng / Share 3 người (chỉ kiểu có giá) · 1 ngày / 7 ngày / 1 tháng · ghi chú shop (chữ, không thành mã)",
           "IPv6" in d and "IPv4" in d and "Riêng" in d and "Share 3 người" in d and "Share 2" not in d and "1 tháng" in d and "Proxy FPT <b>Hà Nội</b>" in d, d)
        s.page.click('#pxb-k [data-pxk="v4"]'); s.page.wait_for_timeout(150)
        d = s.txt("#pxdlg .dlg") or ""
        ck("chọn IPv4 → chỉ còn kiểu Share 2 người (7 ngày 30.000đ · 1 tháng 90.000đ)", "Share 2 người" in d and "Riêng" not in s.txt("#pxb-s") and "30.000" in d and "90.000" in d, d)
        s.page.click('#pxb-d [data-pxd="7"]'); s.page.click('[data-pxq="1"]'); s.page.click('[data-pxq="1"]'); s.page.wait_for_timeout(150)
        ck("số lượng 3 · tổng 3 × 30.000đ = 90.000đ", "× 3" in (s.txt("#pxb-sum-t") or "") and "90.000" in (s.txt("#pxb-sum") or ""), (s.txt("#pxb-sum-t"), s.txt("#pxb-sum")))
        for _ in range(5): s.page.click('[data-pxq="1"]')
        ck("số lượng không quá số còn bán được (IPv4 share 2: còn 4)", s.js("() => document.getElementById('pxb-q').value") == "4")
        s.page.click('[data-pxq="-1"]'); s.page.fill("#pxb-promo", "GIAM10"); s.page.click("#pxb-pay"); s.page.wait_for_timeout(700)
        ck("Thanh toán → px_buy(v4, share 2, 7 ngày, 3 cái, mã GIAM10) · đóng hộp · hiện 'Proxy của bạn'",
           s.calls("px_buy") == [{"p_kind": "v4", "p_share": 2, "p_days": 7, "p_qty": 3, "p_promo": "GIAM10"}] and not s.vis("#pxdlg .dlg") and s.vis("#px-mine"), s.calls("px_buy"))

        print("2. Proxy của bạn")
        mine = s.txt("#px-mine") or ""
        ck("2 proxy: dòng IP:PORT:USER:PASS · IP đang ra · loại + kiểu · proxy hết hạn báo gia hạn trước giờ xoá",
           "203.0.113.50:18899:pxabc12345:a1b2c3d4e5f60718" in mine and "2001:db8:5:ac60::a1" in mine and "IPv4 · Share 2 người" in mine and "Hết hạn" in mine and "Gia hạn trước" in mine, mine)
        ck("tên proxy lạ (<img onerror>) hiện thành chữ, không chạy mã", "<img src=x onerror" in mine and not s.js("() => window.__xss"))
        s.page.click('#px-mine [data-pxcp="5"]'); s.page.wait_for_timeout(150); c1 = s.clip()
        s.page.click('#px-mine [data-pxrot="5"]'); s.page.wait_for_timeout(150); c2 = s.clip()
        s.page.click("#px-mine-all"); s.page.wait_for_timeout(150); c3 = s.clip()
        ck("nút Chép · Link đổi IP (chỉ proxy riêng) · Chép tất cả (chỉ proxy còn hạn)",
           c1 == "203.0.113.50:18899:pxabc12345:a1b2c3d4e5f60718" and c2.startswith("http://203.0.113.50:18899/rotate?key=r0123") and c3 == c1
           and not s.js("() => !!document.querySelector('#px-mine [data-pxrot=\"6\"]')"), (c1, c2, c3))
        s.page.click('#px-mine [data-pxrenew="6"]'); s.page.wait_for_timeout(300)
        rd = s.txt("#pxdlg .dlg") or ""
        s.page.click('#pxr-d [data-pxrd="7"]'); s.page.click("#pxr-go"); s.page.wait_for_timeout(500)
        ck("Gia hạn proxy hết hạn: chọn 7 ngày (30.000đ) → px_my_renew(6, 7)", "30.000" in rd and s.calls("px_my_renew") == [{"p_id": 6, "p_days": 7, "p_promo": None}], (rd, s.calls("px_my_renew")))
        ck("menu bên có 'Proxy của tôi' (2)", s.vis("#nav-px") and s.txt("#px-nav-badge") == "2", s.txt("#nav-px"))
        ck("không lỗi trang / hộp thoại trình duyệt", not s.errors, s.errors)
        s.close()

        print("3. Chưa bán / hết hàng")
        s = Site(br, html, False, data(shop={"sell": False, "v": 63}, my={"items": []}))
        ck("chưa bật bán → không có dòng Proxy, không có khung Proxy của bạn", not s.js("() => !!document.querySelector('#grid .m3-row.px')") and not s.vis("#px-mine") and not s.errors, s.errors)
        s.close()
        sh = json.loads(json.dumps(SHOP)); sh["stock"] = {"v6": {k: 0 for k in "12345"}, "v4": {k: 0 for k in "12345"}}
        s = Site(br, html, False, data(shop=sh))
        ck("hết hàng mọi kiểu → dòng Proxy báo 'Tạm hết', nút mua tắt", "Tạm hết" in (s.txt("#grid .m3-row.px") or "") and s.js("() => document.querySelector('#grid .m3-row.px button').disabled"))
        s.close()

        print("4. Quản trị › 🌐 Proxy")
        s = Site(br, html, True, data(), path="/admin", vp=(1600, 1000))
        s.page.click('#adm-grp button[data-grp="mach"]'); s.page.wait_for_timeout(250)
        s.page.click('#adm-tabs button[data-tab="px"]'); s.page.wait_for_timeout(700)
        top = s.txt("#pxa") or ""
        ck("khung Proxy: CHƯA BÁN · 2 đang chạy · doanh thu 160.000đ · máy chủ (IPv6 dải, phiên lên 2, khách nối 203.0.113.50:18899, mở cổng 18899 → 192.168.77.10:8899, modem cho PPPoE đi qua)",
           s.vis("#pane-px") and "CHƯA BÁN" in top and "160.000" in top and "2001:db8:5:ac60::/64" in top and "203.0.113.50:18899" in top
           and "18899 TCP → 192.168.77.10 cổng 8899" in top and "modem cho PPPoE đi qua" in top, top[:1500])
        ck("danh sách proxy: tên khách lạ hiện thành chữ", "khach<b>A</b>" in top and not s.js("() => !!document.querySelector('#pxa-list b')"))
        s.page.check("#pxa-sell"); s.page.fill('[data-pxpr="v6|2|30"]', "50000"); s.page.fill('[data-pxpr="v6|1|1"]', "")
        s.page.fill("#pxa-port", "28899"); s.page.click("#pxa-save"); s.page.wait_for_timeout(600)
        pt = (s.calls("px_admin_settings") or [{}])[-1].get("p_patch", {})
        ck("Lưu: bật bán, cổng 28899, bảng giá thêm IPv6 share 2 · 30 ngày 50.000đ, bỏ ô để trống (IPv6 riêng 1 ngày)",
           pt.get("sell") is True and pt.get("pub_port") == 28899 and pt.get("prices", {}).get("v6", {}).get("2") == {"30": 50000}
           and "1" not in pt.get("prices", {}).get("v6", {}).get("1", {}) and pt["prices"]["v4"]["2"] == {"7": 30000, "30": 90000}, pt)
        s.page.click('#pxa-list [data-pxact="revoke"][data-pxid="5"]'); s.page.wait_for_timeout(400)
        ck("Thu hồi proxy #5 → px_admin_proxy(5, revoke)", (s.calls("px_admin_proxy") or [{}])[-1] == {"p_id": 5, "p_act": "revoke", "p_arg": {}}, s.calls("px_admin_proxy"))
        s.page.fill("#pxa-q", "pxdef"); s.page.wait_for_timeout(200)
        ck("ô tìm: lọc theo tài khoản proxy", "pxdef67890" in (s.txt("#pxa-list") or "") and "pxabc12345" not in (s.txt("#pxa-list") or ""))

        print("5. Tài khoản PPPoE mã hoá (trình duyệt mã hoá bằng khoá của máy chủ)")
        s.page.click('#pxa-hosts [data-pxppp]'); s.page.wait_for_timeout(300)
        s.page.fill("#pxp-u", "fpt-hn-test"); s.page.fill("#pxp-p", "Mật khẩu thử 9!"); s.page.fill("#pxp-n", "3")
        s.page.click("#pxp-go"); s.page.wait_for_timeout(900)
        cl = s.calls("px_admin_ppp")
        enc = cl[-1]["p_enc"] if cl else "{}"
        dec_out = subprocess.run(["node", dec, TEST_D, enc], capture_output=True, text=True).stdout.strip()
        ck("gửi px_admin_ppp(máy chủ, chuỗi mã hoá {v:1,e,i,c}) — chuỗi KHÔNG chứa tên / mật khẩu thật; chỉ khoá riêng của máy chủ giải ra đúng",
           cl and cl[-1]["p_host"] == H1 and enc.startswith('{"v":1,"e":"') and "fpt-hn-test" not in enc and "Mật khẩu" not in enc
           and json.loads(dec_out or "{}") == {"user": "fpt-hn-test", "pass": "Mật khẩu thử 9!", "sessions": 3}, (enc[:80], dec_out))
        ck("trang không giữ lại mật khẩu sau khi gửi (hộp đóng, ô mật khẩu đã xoá)", not s.vis("#pxdlg .dlg") and not s.js("() => { const e = document.getElementById('pxp-p'); return e && e.value; }"))
        ck("không lỗi trang / hộp thoại trình duyệt (quản trị)", not s.errors, s.errors)
        s.close()
        br.close()
    print("\nKẾT QUẢ: %d đạt, %d lỗi" % (OK, FAIL))
    sys.exit(1 if FAIL else 0)


main()
