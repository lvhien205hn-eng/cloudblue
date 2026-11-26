# -*- coding: utf-8 -*-
"""Thử phần BÁN VPS GPU TỰ ĐỘNG trên web (pc_shop.html, SQL v43) bằng Chrome thật (Playwright) + Supabase giả.
   python3 test_web_shop.py <index đã gắn> [thư mục ảnh chụp]
   Mọi yêu cầu mạng trả lời tại chỗ — không gọi ra ngoài."""
import datetime, json, os, re, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "..", "web", "index.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(NEW_HTML)), "shots")
os.makedirs(SHOTS, exist_ok=True)
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0
PROD, OTHER = "48fa9b2d-cfc6-4394-851e-26715651fa8e", "11111111-2222-4333-8444-555555555555"
PC1, PC2, PC3 = ["00000000-0000-4000-8000-0000000000c%d" % i for i in range(1, 4)]


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def iso(sec_from_now):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec_from_now)).isoformat()


def read(p):
    with open(p, encoding="utf-8") as f: return f.read()


PRODUCTS = [{"id": PROD, "cat": "vps", "name": "VPS GPU BLUE", "price": 360000, "plans": [{"days": 7, "price": 360000}, {"days": 15, "price": 750000}, {"days": 30, "price": 1600000}],
             "features": ["2686V4", "RAM 128GB"], "hot": True, "sort": 1, "manual": True, "stock": 300, "manual_stock": 300},
            {"id": OTHER, "cat": "vps", "name": "VPS THƯỜNG", "price": 100000, "plans": [{"days": 7, "price": 100000}], "features": ["Xeon E5", "RAM 64GB"], "hot": False, "sort": 2, "manual": True, "stock": 5, "manual_stock": 5}]
INFO_ON = {"on": True, "product": PROD, "ready": True, "reinstall_max": 2,
           "os": [{"id": "22h2", "name": "Windows 10 Pro 22H2", "fast": True}, {"id": "1511", "name": "Windows 10 Pro 1511", "fast": False}]}
MINE = {"product": PROD, "reinstall_max": 2, "os": [{"id": "22h2", "name": "Windows 10 Pro 22H2"}, {"id": "1511", "name": "Windows 10 Pro 1511"}], "items": [
    {"rental": 7, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(6 * 86400), "left": 2, "used": 0,
     "pc": {"id": PC1, "name": "May-01", "code": "A1", "os": "22h2", "online": True, "link": True, "remote": True, "off": False, "job": None, "last_job": None,
            "cpu": "Xeon", "ram_gb": 128, "gpus": ["NVIDIA GeForce GTX 1080"]}},
    {"rental": 8, "state": "active", "os": "1511", "os_name": "Windows 10 Pro 1511", "days": 15, "until": iso(15 * 86400), "left": 1, "used": 1,
     "pc": {"id": PC2, "name": "<img src=x onerror=window.__xss=1>", "code": "", "os": "22h2", "online": True, "link": False, "remote": True, "off": False,
            "job": {"state": "sent", "os": "1511", "at": iso(-60)}, "last_job": None, "cpu": "", "ram_gb": 64, "gpus": ["<b>x</b>"]}},
    {"rental": 9, "state": "waiting", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": None, "left": 2, "used": 0, "pc": None},
    {"rental": 6, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(-3600), "left": 0, "used": 2,
     "pc": {"id": PC3, "name": "May-03", "code": "", "os": "22h2", "online": False, "link": False, "remote": True, "off": True, "job": None, "last_job": None, "ram_gb": 32, "gpus": []}}]}
ADM = {"product": PROD, "reinstall_max": 2, "os": INFO_ON["os"], "free": [
          {"id": PC3, "name": "May-03", "code": "", "os": "22h2", "online": True, "clean": True, "last_seen": iso(-5)},
          {"id": PC2, "name": "May-02", "code": "B2", "os": "1511", "online": False, "clean": False, "last_seen": iso(-3600)}],
       "rentals": [
          {"id": 21, "state": "waiting", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "created_at": iso(-600), "until": None, "left": 2, "used": 0, "note": "",
           "total": 360000, "user": {"id": "u1", "username": "khach<b>1</b>", "email": "k1@x.vn"}, "pc": None},
          {"id": 20, "state": "active", "os": "1511", "os_name": "Windows 10 Pro 1511", "days": 15, "created_at": iso(-86400), "until": iso(14 * 86400), "left": 1, "used": 1, "note": "vip",
           "total": 750000, "user": {"id": "u2", "username": "khach2", "email": "k2@x.vn"}, "pc": {"id": PC1, "name": "May-01", "code": "A1", "os": "1511", "online": True, "off": False, "job": None}}]}

HOOK = """window.__FAKE_HOOK = {
  pc_shop_info: () => window.__SHOP.info,
  pc_my_vps: () => window.__SHOP.mine,
  pc_buy: a => { window.__SHOP.bought.push(a); return window.__SHOP.buyRes; },
  pc_my_reinstall: a => ({ ok: true, left: 0, os: a.p_os }),
  pc_my_renew: a => ({ ok: true, until: new Date(Date.now() + 9 * 86400e3).toISOString(), was_off: true }),
  pc_admin_rentals: () => window.__SHOP.adm,
  pc_admin_handover: a => ({ state: 'active', pc: a.p_pc, name: 'May-03', reinstall: false, old_pc: null }),
  pc_admin_rental_set: a => ({ id: a.p_rental, left: 3, note: '' }),
  pc_admin_rental_end: a => ({ id: a.p_rental, state: 'cancelled', refunded: true }),
  pc_admin_sell: a => ({ product: a.p_patch.product, os: a.p_patch.os, reinstall_max: a.p_patch.reinstall_max }),
  buy_product: a => ({ id: 'o-old', status: 'pending', total: 100000 }),
  pc_admin_deliver: a => ({ state: 'active', pc: a.p_pc, name: 'May-03', code: '', reinstall: false, order: a.p_order }),
  pc_my_cancel: a => ({ ok: true, pc: a.p_pc, rental: 61 }),
  pc_my_power: a => { if (window.__SHOP.powErr) throw new Error(window.__SHOP.powErr); return window.__SHOP.powRes || { ok: true, cmd: a.p_cmd }; },
  pc_admin_flags: () => ({ cust_admin: true, agents: 1 }),
  pc_admin_set_flags: a => ({ cust_admin: a.p_patch.cust_admin, agents: 1 })
};"""


class Site:
    def __init__(self, browser, html, admin, shop, mobile=False, path="/"):
        self.errors, self.dialogs, self.accept = [], [], True
        vp = {"width": 390, "height": 844} if mobile else {"width": 1360, "height": 900}
        self.ctx = browser.new_context(viewport=vp, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {"product_list": PRODUCTS, "products": PRODUCTS}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps(shop), HOOK))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.on("dialog", lambda d: (self.dialogs.append(d.message), d.accept() if self.accept else d.dismiss()))
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2600)

    def route(self, route):
        u = route.request.url
        if u in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js")))
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def calls(self, name): return self.js("n => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)
    def close(self): self.ctx.close()


def main():
    html = read(NEW_HTML)
    shop = {"info": INFO_ON, "mine": MINE, "adm": ADM, "bought": [], "buyRes": {"state": "active", "pc": PC1, "name": "May-01", "reinstall": True, "rental": 30, "order": "o1", "total": 1600000}}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        print("1. Khách mua VPS GPU tự động")
        s = Site(br, html, False, shop)
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }")
        s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(500)
        st = s.js("""() => ({ auto: document.getElementById('modal').classList.contains('pcauto'), os: [...document.querySelectorAll('#pcs-os [data-pcsos]')].map(b => [b.dataset.pcsos, b.classList.contains('on'), b.innerText.replace(/\\s+/g, ' ')]),
                    vps: getComputedStyle(document.getElementById('m-vps')).display, qty: getComputedStyle(document.querySelector('#modal .qty')).display, how: document.querySelector('#pcs-os .pcs-how').innerText })""")
        ck("hộp mua VPS GPU tự động: hiện ô chọn Windows (22H2 / 1511), ẩn FarmV5 + mã PIN + số lượng", st["auto"] and [x[0] for x in st["os"]] == ["22h2", "1511"] and st["vps"] == "none" and st["qty"] == "none", st)
        ck("chọn sẵn bản có máy giao ngay (22H2), ghi rõ 'giao ngay' / 'cài theo yêu cầu'", st["os"][0][1] and "giao ngay" in st["os"][0][2] and "~20 phút" in st["os"][1][2], st["os"])
        ck("có dòng giải thích: tự giao máy, điều khiển web/app, 2 lần cài lại", "tự giao máy" in st["how"] and "app điện thoại" in st["how"] and "2 lần" in st["how"], st["how"])
        ck("hộp mua có nút 🎬 Xem video hướng dẫn", s.js("() => !!document.querySelector('#pcs-os [data-pcsvid]')") and "video hướng dẫn" in st["how"], st["how"])
        hz = s.js("""() => { const h = document.getElementById('pcs-hero'), cs = e => e ? getComputedStyle(e).display : 'none';
                    return { vis: !!h && !h.hidden && cs(h) !== 'none', t: h ? h.innerText.replace(/\\s+/g, ' ') : '', chips: h ? h.querySelectorAll('.ph-chips span').length : 0,
                             title: cs(document.getElementById('m-title')), first: document.querySelector('#modal .dlg').firstElementChild.id,
                             order: [...document.querySelector('#modal .dlg').children].map(e => e.id).filter(x => ['pcs-hero', 'pcs-os', 'm-plans-box'].includes(x)),
                             plans: [...document.querySelectorAll('#m-plans button')].map(b => b.innerText.replace(/\\s+/g, ' ')), lab: document.querySelector('#m-plans-box > span').textContent }; }""")
        ck("hộp mua VPS GPU 'sịn': thẻ cấu hình đầu hộp (tên, cấu hình admin nhập, chỉ từ 50.000đ / ngày, Có máy sẵn), ẩn tiêu đề cũ",
           hz["vis"] and hz["first"] == "pcs-hero" and "VPS GPU BLUE" in hz["t"] and hz["chips"] == 2 and "2686V4" in hz["t"] and "chỉ từ 50.000" in hz["t"] and "Có máy sẵn" in hz["t"] and hz["title"] == "none", hz)
        ck("26/11 · hộp thuê VPS GPU tự động đã có thẻ cấu hình ở đầu hộp → không lặp thêm dải cấu hình", s.js("() => getComputedStyle(document.getElementById('m-feats')).display") == "none")
        ck("① Chọn Windows rồi ② Chọn thời gian thuê; gói ghi giá / ngày, gói rẻ hơn có nhãn −%",
           hz["order"] == ["pcs-hero", "pcs-os", "m-plans-box"] and hz["lab"].startswith("②") and any("50.000" in x and "/ ngày" in x and "−3%" in x for x in hz["plans"])
           and not any("−" in x for x in hz["plans"] if x.startswith("30")), hz)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-1-buy.png"))
        s.page.click('#pcs-os [data-pcsos="1511"]'); s.page.click("#m-plans button[data-d='15']"); s.page.click("#m-ok"); s.page.wait_for_timeout(700)
        b = s.js("() => window.__SHOP.bought")
        ck("bấm Thanh toán → gọi pc_buy đúng sản phẩm + 15 ngày + 1511 (không gọi buy_product)", b == [{"p_product": PROD, "p_days": 15, "p_os": "1511"}] and not s.calls("buy_product"), (b, s.calls("buy_product")))
        d = s.js("() => { const m = document.getElementById('pcsdlg'); return m && !m.hidden ? m.innerText : ''; }")
        ck("xong → hộp 'Thanh toán thành công' kiểu ĐỢI MÁY: ① Đợi máy đang cài 1511 + mã thanh toán, nút VPS GPU của tôi",
           "Thanh toán thành công" in d and "Đợi máy" in d and "Đang cài Windows 10 Pro 1511" in d and "BR-O1" in d and "VPS GPU của tôi" in d and document_ok(s), d)
        mg = s.js("""() => { const g = document.getElementById('pcsw-msg'); return { open: g.open, sum: g.querySelector('summary').innerText, txt: document.getElementById('pcsw-txt').textContent,
                    ct: g.querySelectorAll('.contacts a').length, copy: !!document.getElementById('pcsw-copy') }; }""")
        ck("② nội dung gửi admin: ẨN sẵn (bấm mới hiện), có đủ mã thanh toán / sản phẩm / Windows / tài khoản / lượt thuê + nút Copy",
           not mg["open"] and "Máy lâu chưa lên" in mg["sum"] and "VPS GPU LÂU CHƯA LÊN" in mg["txt"] and "Mã thanh toán: BR-O1" in mg["txt"] and "VPS GPU BLUE · 15 ngày" in mg["txt"]
           and "Windows 10 Pro 1511" in mg["txt"] and "Lượt thuê: #30" in mg["txt"] and mg["copy"], mg)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-2-done.png"))
        s.js("() => { window.PCSHOP.w.t0 -= 46 * 60000; }"); s.page.wait_for_timeout(1300)
        lt = s.js("() => { const g = document.getElementById('pcsw-msg'); return { open: g.open, late: g.classList.contains('late'), note: !document.getElementById('pcsw-late').hidden, txt: document.getElementById('pcsw-txt').textContent }; }")
        ck("cài quá 45 phút → tự MỞ mục ② + nhắc gửi admin, nội dung ghi đúng trạng thái + số phút đã chờ",
           lt["open"] and lt["late"] and lt["note"] and "Trạng thái: Đang cài Windows 10 Pro 1511 (đã chờ 46 phút" in lt["txt"], lt)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-2b-late.png"))
        s.js("() => document.getElementById('pcsdlg').hidden = true")
        s.js("() => { window.__SHOP.buyRes = { state: 'waiting', rental: 31, order: 'o2', total: 360000 }; }")
        s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(300); s.page.click("#m-ok"); s.page.wait_for_timeout(600)
        d = s.js("() => document.getElementById('pcsdlg').innerText")
        ck("hết máy → ① Đang chờ máy, tự giao + cài Windows, không cần nhắn shop", "Đang chờ máy" in d and "tự giao" in d and "không cần nhắn shop" in d, d)
        s.js("""() => { const m = window.PCSHOP.mine; window.PCSHOP.mine = { ...m, items: [...m.items, { rental: 31, state: 'active', os: '22h2', os_name: 'Windows 10 Pro 22H2', days: 7,
                 until: new Date(Date.now() + 7 * 864e5).toISOString(), left: 2, used: 0, pc: { id: '%s', name: 'May-03', online: true, job: null, last_job: null, gpus: [] } }] }; }""" % PC3)
        s.page.wait_for_timeout(1300)
        rd = s.js("() => ({ t: document.getElementById('pcsdlg').innerText, a: (document.querySelector('#pcsw-acts a[href^=\"/play.html?pc=\"]') || {}).href || '', bar: document.getElementById('pcsw-bar').hidden })")
        ck("có máy → hộp tự đổi sang '✅ Máy đã sẵn sàng' + nút ▶ Điều khiển đúng máy (không cần tải lại)", "Máy đã sẵn sàng" in rd["t"] and rd["a"].endswith("/play.html?pc=" + PC3) and rd["bar"], rd)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-3-ready.png"))
        s.js("() => document.getElementById('pcsdlg').hidden = true")
        s.js("id => openBuy(id)", OTHER); s.page.wait_for_timeout(300)
        st = s.js("() => ({ auto: document.getElementById('modal').classList.contains('pcauto'), os: !!document.getElementById('pcs-os') && !document.getElementById('pcs-os').hidden, vps: getComputedStyle(document.getElementById('m-vps')).display })")
        ck("sản phẩm VPS khác (không bật tự động) → hộp mua kiểu cũ nhưng KHÔNG còn FarmV5 / FarmSync (21.11j), không có ô Windows tự động", not st["auto"] and not st["os"] and st["vps"] == "none", st)
        ck("sản phẩm khác: không có thẻ cấu hình VPS GPU, tiêu đề + nhãn gói như cũ", s.js("() => { const h = document.getElementById('pcs-hero'); return (!h || h.hidden) && getComputedStyle(document.getElementById('m-title')).display !== 'none' && !document.querySelector('#m-plans-box > span').textContent.startsWith('②'); }"))
        mf = s.js("""() => { const f = document.getElementById('m-feats'); return { title: document.getElementById('m-title').innerText.trim(), hid: f.hidden, disp: getComputedStyle(f).display,
                    chips: [...f.querySelectorAll('span')].map(e => e.innerText), fl: (f.querySelector('.fl') || {}).innerText || '' }; }""")
        ck("26/11 · hộp thuê VPS (kiểu cũ): tiêu đề 'Thuê VPS GPU' (không còn 'Mua sản phẩm') + nhắc lại CẤU HÌNH ngay trong hộp",
           mf["title"] == "Thuê VPS GPU" and not mf["hid"] and mf["disp"] != "none" and mf["chips"] == ["Xeon E5", "RAM 64GB"] and mf["fl"] == "Cấu hình", mf)
        print("2. VPS GPU của bạn (trang chủ)")
        s.js("() => window.PCSHOP && document.getElementById('modal') && (document.getElementById('modal').hidden = true)")
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 4", timeout=8000)
        cards = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => ({ t: c.innerText.replace(/\\s+/g, ' '), ctl: (c.querySelector('a[href^=\"/play.html?pc=\"]') || {}).href || '', re: (c.querySelector('[data-pcsre]') || {}).disabled }))")
        ck("khung 'VPS GPU của bạn' hiện ngay dưới máy đám mây, đủ 4 thẻ", s.js("() => !document.getElementById('pcs-mine').hidden && document.getElementById('pcs-mine').previousElementSibling.id === 'm3-mine'") and len(cards) == 4, cards)
        ck("máy sẵn sàng: nút ▶ Điều khiển mở play.html?pc=<máy>, cài lại 2/2", "Sẵn sàng" in cards[0]["t"] and cards[0]["ctl"].endswith("/play.html?pc=" + PC1) and "2/2" in cards[0]["t"] and cards[0]["re"] is False, cards[0])
        ck("máy đang cài: báo đang cài 1511 + thanh chạy, chưa cho điều khiển / cài lại", "Đang cài Windows" in cards[1]["t"] and "1511" in cards[1]["t"] and not cards[1]["ctl"] and cards[1]["re"] is True, cards[1])
        ck("đơn chờ máy: báo tự giao, không cần nhắn shop", "Đang chờ máy" in cards[2]["t"] and "không cần nhắn shop" in cards[2]["t"], cards[2])
        ck("máy hết hạn đã tắt: báo gia hạn để dùng tiếp, hết lượt cài lại", "Hết hạn" in cards[3]["t"] and "Gia hạn" in cards[3]["t"] and cards[3]["re"] is True, cards[3])
        ck("tên máy / GPU lạ không chạy được mã (đã esc)", s.js("() => !window.__xss") and "<img" in cards[1]["t"])
        pg_ = s.js("""() => { const c = document.querySelectorAll('#pcs-mine-list .pcs-card')[1], p = c && c.querySelector('.pcs-prog');
                    return p ? { k: p.dataset.pk, t: p.querySelector('.pp-t').textContent, w: p.querySelector('.pp-bar i').style.width, late: p.classList.contains('late') } : null; }""")
        ck("máy đang cài lại: thanh tiến độ có % + đếm giờ chạy (Khởi động lại vào bộ cài · đã chạy 1:0x)",
           pg_ and pg_["k"] == "inst" and "Khởi động lại vào bộ cài" in pg_["t"] and "đã chạy 1:0" in pg_["t"] and "%" in pg_["t"] and pg_["w"].endswith("%") and not pg_["late"], pg_)
        s.js("() => { const p = document.querySelectorAll('#pcs-mine-list .pcs-card')[1].querySelector('.pcs-prog'); p.dataset.t0 = new Date(Date.now() - 61 * 60000).toISOString(); }")
        s.page.wait_for_timeout(1300)
        lt2 = s.js("() => { const p = document.querySelectorAll('#pcs-mine-list .pcs-card')[1].querySelector('.pcs-prog'); return { late: p.classList.contains('late'), t: p.querySelector('.pp-t').textContent, rep: !!p.querySelector('[data-pcsrep]') }; }")
        ck("cài quá lâu (61 phút) → thanh vàng 'lâu hơn bình thường' + nút 📋 Báo admin", lt2["late"] and "lâu hơn bình thường" in lt2["t"] and lt2["rep"], lt2)
        s.page.click('#pcs-mine-list .pcs-prog [data-pcsrep]'); s.page.wait_for_timeout(300)
        rp = s.js("() => ({ open: !document.getElementById('pcsdlg').hidden, msg: (document.getElementById('pcs-repmsg') || {}).textContent || '', copy: !!document.getElementById('pcs-repcopy') })")
        ck("Báo admin → hộp có nội dung soạn sẵn (máy, việc đang làm + thời gian, lượt thuê) + nút Copy",
           rp["open"] and "VPS GPU CẦN HỖ TRỢ" in rp["msg"] and "Cài lại Windows 1511" in rp["msg"] and "Lượt thuê: #8" in rp["msg"] and rp["copy"], rp)
        s.js("() => { document.getElementById('pcsdlg').hidden = true; }")
        s.page.click('#pcs-mine [data-pcsvid]'); s.page.wait_for_timeout(300)
        vd = s.js("""() => { const m = document.getElementById('pcsdlg'), v = m && m.querySelector('video.pcs-vid');
                    return { open: !!m && !m.hidden, src: v ? v.getAttribute('src') : '', poster: v ? v.getAttribute('poster') : '', ctl: !!v && v.controls, inl: !!v && v.playsInline,
                             wide: !!m && m.querySelector('.pcs-dlg').classList.contains('vid'), t: m ? m.innerText : '' }; }""")
        ck("🎬 Video hướng dẫn (đầu khung VPS GPU của bạn) → hộp phát /video/vps-gpu.mp4 (ảnh bìa, nút điều khiển, phát ngay trên iPhone)",
           vd["open"] and vd["src"] == "/video/vps-gpu.mp4" and vd["poster"] == "/video/vps-gpu.jpg" and vd["ctl"] and vd["inl"] and vd["wide"] and "Hướng dẫn dùng VPS GPU" in vd["t"], vd)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-5-video.png"))
        s.page.click('#pcsdlg [data-pcsx]'); s.page.wait_for_timeout(150)
        ck("Đóng hộp video → ẩn + dừng video", s.js("() => { const m = document.getElementById('pcsdlg'); return m.hidden && [...m.querySelectorAll('video')].every(v => v.paused); }"))
        s.page.screenshot(path=os.path.join(SHOTS, "shop-3-mine.png"), full_page=False)
        apps = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => (c.querySelector('[data-pcsapp]') || {}).dataset ? (c.querySelector('[data-pcsapp]') || {dataset: {}}).dataset.pcsapp || '' : '')")
        ck("nút 📲 App chỉ có ở máy điều khiển được (máy sẵn sàng)", apps[0] == PC1 and apps[1:] == ["", "", ""], apps)
        s.page.click('#pcs-mine-list [data-pcsapp="%s"]' % PC1); s.page.wait_for_timeout(300)
        lk = s.js("() => [...document.querySelectorAll('#pcsdlg a')].map(a => a.getAttribute('href'))")
        ck("📲 App: link mở app máy tính blueroblox://pc/<máy>, tải app, mở trên trình duyệt play.html?pc=<máy>", "blueroblox://pc/" + PC1 in lk and "/play.html?pc=" + PC1 in lk
           and any(x and x.startswith("/download/") for x in lk) and not any(x and x.startswith("intent://") for x in lk), lk)
        ck("📲 App trên máy tính: app máy tính đứng đầu", s.js("() => document.querySelector('#pcsdlg .shsec b').textContent").startswith("💻"))
        s.page.click('#pcsdlg [data-pcsx]'); s.page.wait_for_timeout(150)
        ck("nút Đóng đóng hộp", s.js("() => document.getElementById('pcsdlg').hidden"))
        s.js("() => { Object.defineProperty(navigator, 'userAgent', { get: () => 'Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36' }); }")
        s.page.click('#pcs-mine-list [data-pcsapp="%s"]' % PC1); s.page.wait_for_timeout(300)
        la = s.js("() => [...document.querySelectorAll('#pcsdlg a')].map(a => a.getAttribute('href'))")
        ck("📲 App trên điện thoại Android: app Android đứng đầu, link intent://pc/<máy> đúng gói app + về trang tải APK khi chưa cài",
           s.js("() => document.querySelector('#pcsdlg .shsec b').textContent").startswith("📱") and any(x and x.startswith("intent://pc/" + PC1 + "#Intent;scheme=blueroblox;package=shop.blueroblox.app;S.browser_fallback_url=") and x.endswith(";end") for x in la), la)
        s.page.click('#pcsdlg [data-pcsx]'); s.page.wait_for_timeout(150)
        s.page.click('#pcs-mine-list [data-pcsre="%s"]' % PC1); s.page.wait_for_timeout(300)
        s.page.click('#pcsdlg [data-pcsreos="1511"]'); s.page.click('#pcsdlg [data-pcsgo2]'); s.page.wait_for_timeout(600)
        ck("Cài lại: chọn 1511 → hỏi xác nhận → gọi pc_my_reinstall đúng máy + bản", s.calls("pc_my_reinstall") == [{"p_pc": PC1, "p_os": "1511"}] and any("Ổ C: bị xoá" in x for x in s.dialogs), (s.calls("pc_my_reinstall"), s.dialogs[-1:]))
        s.page.click('#pcs-mine-list [data-pcsrenew="%s"]' % PC3); s.page.wait_for_timeout(300)
        rn = s.js("() => document.getElementById('pcsdlg').innerText")
        s.page.click('#pcsdlg [data-pcsplan="15"]'); s.page.click('#pcsdlg [data-pcsrnew]'); s.page.wait_for_timeout(600)
        ck("Gia hạn: hiện 3 gói giá thật, chọn +15 ngày → gọi pc_my_renew", "+7 ngày" in rn and "+30 ngày" in rn and s.calls("pc_my_renew") == [{"p_pc": PC3, "p_days": 15}], (rn, s.calls("pc_my_renew")))
        s.js("() => { const m = document.getElementById('pcsdlg'); if (m) m.hidden = true; }")
        nv = s.js("() => { const a = document.getElementById('nav-vps'), b = document.getElementById('vps-nav-badge'); return { vis: !!a && !a.hidden, has: !!a && a.classList.contains('has'), n: b && !b.hidden ? b.textContent : '' }; }")
        ck("menu bên 'VPS của tôi': nổi bật + số VPS GPU (4 = 3 đang thuê + 1 chờ máy)", nv["vis"] and nv["has"] and nv["n"] == "4", nv)
        s.page.click("#nav-vps"); s.page.wait_for_timeout(900)
        vm = s.js("""() => { const m = document.getElementById('vmach'), b = document.getElementById('pcs-vm');
                    return { open: !!m && !m.hidden, cards: b ? b.querySelectorAll('.pcs-card').length : 0, ctl: !!(b && b.querySelector('a[href="/play.html?pc=%s"]')),
                             app: !!(b && b.querySelector('[data-pcsapp="%s"]')), vid: !!(b && b.querySelector('[data-pcsvid]')), list: document.getElementById('vm-list').innerText.trim(),
                             note: document.getElementById('vm-note').hidden, first: b && b.nextElementSibling ? b.nextElementSibling.id : '', t: b ? b.innerText : '' }; }""" % (PC1, PC1))
        ck("bấm 'VPS của tôi' → VPS GPU nằm ĐẦU hộp: đủ 4 thẻ, ▶ Điều khiển trên web, 📲 App, 🎬 Video; không còn dòng 'chưa có máy VPS nào'",
           vm["open"] and vm["cards"] == 4 and vm["ctl"] and vm["app"] and vm["vid"] and vm["list"] == "" and vm["note"] and "Điều khiển ngay trên web" in vm["t"], vm)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-6-vps-cua-toi.png"))
        ap = s.js("""() => { const b = document.querySelector('#pcs-vm .pcs-appdl'); if (!b) return null;
                    return { t: b.innerText, links: [...b.querySelectorAll('a')].map(a => a.getAttribute('href')), dl: [...b.querySelectorAll('a[download]')].length,
                             help: !!document.querySelector('#pcs-vm .pcs-vmhelp[data-pcsvid]'), order: [...document.getElementById('pcs-vm').children].map(e => e.className) }; }""")
        ck("22/11: 'VPS của tôi' có thẻ 📲 Tải app đầy đủ như ĐT đám mây — app máy tính + app Android (tải về), iPhone · iPad · Mac mở VPS đầu tiên trên web, nhiều máy (≥ 2 VPS)",
           ap and "Tải app" in ap["t"] and ap["dl"] == 2 and "/play.html?pc=" + PC1 in ap["links"] and "/play.html?multi=pc" in ap["links"]
           and any(l and l.endswith(".apk") for l in ap["links"]) and "VPS" in ap["t"], ap)
        ck("… + thẻ 🎬 Video hướng dẫn VPS GPU từ A đến Z (như thẻ Hướng dẫn A→Z bên ĐT đám mây), nằm trên danh sách VPS",
           ap and ap["help"] and ap["order"].index("helpbtn pcs-vmhelp") < ap["order"].index("pcs-vm-list") and ap["order"].index("cpappdl pcs-appdl") < ap["order"].index("helpbtn pcs-vmhelp"), ap and ap["order"])
        s.page.click('#pcs-vm .pcs-vmhelp'); s.page.wait_for_timeout(300)
        ck("… bấm thẻ video → mở hộp phát video VPS (/video/vps-gpu.mp4) nằm trên hộp 'VPS của tôi'",
           s.js("() => { const m = document.getElementById('pcsdlg'), v = m && m.querySelector('video.pcs-vid'); return !!m && !m.hidden && !!v && v.getAttribute('src') === '/video/vps-gpu.mp4' && !document.getElementById('vmach').hidden; }"))
        s.page.click('#pcsdlg [data-pcsx]'); s.page.wait_for_timeout(150)
        s.page.click('#pcs-vm [data-pcsrenew="%s"]' % PC1); s.page.wait_for_timeout(300)
        ck("trong hộp 'VPS của tôi': nút ⏱ Gia hạn mở hộp gia hạn (nằm trên)", s.js("() => !document.getElementById('pcsdlg').hidden && document.getElementById('pcsdlg').innerText.includes('Gia hạn')"))
        s.js("() => { document.getElementById('pcsdlg').hidden = true; document.getElementById('vmach').hidden = true; }")
        # 🛠️ bảo trì riêng VPS GPU (settings.data.pc_maint) — khách: khoá điều khiển / app / cài lại + báo; gia hạn vẫn được
        s.js("() => { SITE.pc_maint = true; SITE.pc_maint_msg = 'Nâng cấp máy'; }"); s.js("() => window.PCSHOP && (window.PCSHOP.mineAt = 0)")
        s.page.evaluate("() => document.getElementById('nav-vps').click()"); s.page.wait_for_timeout(900)
        mt = s.js("""() => { const b = document.getElementById('pcs-vm'), h = document.getElementById('pcs-mine-mt');
                    return { bar: b ? (b.querySelector('.pcs-maint') || {}).innerText || '' : '', home: h ? h.innerText : '', ctl: !!(b && b.querySelector('a[href^=\"/play.html?pc=\"]')),
                             app: !!(b && b.querySelector('[data-pcsapp]')), re: [...(b ? b.querySelectorAll('[data-pcsre]') : [])].every(x => x.disabled), renew: [...(b ? b.querySelectorAll('[data-pcsrenew]') : [])].some(x => !x.disabled) }; }""")
        ck("bảo trì riêng VPS GPU: khách thấy dòng báo (kèm lời nhắn), không còn ▶ Điều khiển / 📲 App, cài lại bị khoá, gia hạn vẫn bấm được",
           "VPS GPU đang bảo trì — Nâng cấp máy" in mt["bar"] and "VPS GPU đang bảo trì" in mt["home"] and not mt["ctl"] and not mt["app"] and mt["re"] and mt["renew"], mt)
        s.js("() => { document.getElementById('vmach').hidden = true; }")
        s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(400); s.page.click("#m-ok"); s.page.wait_for_timeout(500)
        ck("bảo trì: hộp mua có dòng báo, bấm Thanh toán → báo bảo trì, KHÔNG gọi pc_buy",
           "VPS GPU đang bảo trì" in s.js("() => document.getElementById('pcs-hero').innerText") and "bảo trì" in s.js("() => document.getElementById('m-err').textContent") and len(s.js("() => window.__SHOP.bought")) == 2, s.js("() => window.__SHOP.bought"))
        s.js("() => { document.getElementById('modal').hidden = true; SITE.pc_maint = false; }")
        ck("không lỗi JS / console", not s.errors, s.errors)
        s.close()
        print("3. Điện thoại (màn hình hẹp)")
        s = Site(br, html, False, dict(shop, bought=[]), mobile=True)
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 4", timeout=8000)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-4-mobile.png"))
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }"); s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(400)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-5-mobile-buy.png"))
        ck("điện thoại: hộp mua + ô Windows vừa màn hình (không tràn ngang)", s.js("() => document.documentElement.scrollWidth <= window.innerWidth + 1 && document.getElementById('pcs-os').getBoundingClientRect().width <= window.innerWidth"))
        ck("điện thoại: không lỗi JS", not s.errors, s.errors)
        s.close()
        print("4. Cơ sở dữ liệu chưa chạy v43 → trang như cũ")
        s = Site(br, html, False, dict(shop, info=None, mine=None))
        s.js("""() => { window.__FAKE_HOOK.pc_shop_info = () => ({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.pc_shop_info' } });
                        window.__FAKE_HOOK.pc_my_vps = () => ({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.pc_my_vps' } }); }""")
        s.js("() => { PCSHOP.infoAt = 0; PCSHOP.info = null; }"); s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(500)
        ck("chưa có v43: hộp mua VPS GPU BLUE như cũ (FarmV5), không có ô Windows tự động", s.js("() => !document.getElementById('modal').classList.contains('pcauto')"))
        ck("chưa có v43: không hiện khung VPS GPU, không lỗi JS", s.js("() => !document.getElementById('pcs-mine') || document.getElementById('pcs-mine').hidden") and not s.errors, s.errors)
        s.close()
        print("5. Admin: đơn VPS GPU")
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.page.wait_for_function("() => document.getElementById('pcs-waitbar') && !document.getElementById('pcs-waitbar').hidden", timeout=8000)
        wb = s.js("() => document.getElementById('pcs-waitbar').innerText")
        ck("dải đỏ ở MỌI thẻ quản trị: 1 đơn chờ máy, tên khách, bản Windows (tên khách đã esc)", "1 đơn VPS GPU đang chờ máy" in wb and "khach<b>1</b>" in wb and "22H2" in wb, wb)
        s.page.click("#pcs-waitbar"); s.page.wait_for_timeout(600)
        ck("bấm dải đỏ → mở thẻ 💻 Máy PC, khung Đơn VPS GPU hiện", s.js("() => !document.getElementById('pane-pc').hidden && !document.getElementById('pcs-adm').hidden"))
        rows = s.js("() => [...document.querySelectorAll('#pcs-adm-tbl tr')].map(r => r.innerText.replace(/\\s+/g, ' '))")
        ck("thời gian trên bảng đơn / dải đỏ đọc đúng (không ra NaN)", not any("NaN" in r for r in rows) and "NaN" not in wb and "phút trước" in rows[0], (rows, wb))
        ck("bảng đơn: đơn chờ lên đầu (Bàn giao), đơn đang thuê có máy + lượt cài lại + ghi chú", len(rows) == 2 and "Chờ máy" in rows[0] and "Bàn giao" in rows[0] and "May-01" in rows[1] and "Đổi máy" in rows[1] and "vip" in rows[1], rows)
        sm = s.js("() => document.getElementById('pcs-adm-sum').innerText + ' | ' + document.getElementById('pcs-adm-wait').innerText")
        ck("tóm tắt: đang thuê / chờ / kho trống + online; hướng dẫn bật máy", "1 đang thuê" in sm and "1 chờ máy" in sm and "kho trống 2 máy (1 online)" in sm and "tự giao trong 1 phút" in sm, sm)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-6-admin.png"))
        s.page.click('#pcs-adm-tbl tr[data-r="21"] [data-ra="hand"]'); s.page.wait_for_timeout(300)
        hd = s.js("() => document.getElementById('pcsdlg').innerText")
        ck("hộp Bàn giao: liệt kê máy trống, máy sạch đúng bản ghi 'giao ngay, không cần cài', máy khách cũ ghi 'sẽ xoá sạch'", "May-03" in hd and "giao ngay, không cần cài" in hd and "sẽ xoá sạch" in hd, hd)
        s.page.click("#pcs-h-go"); s.page.wait_for_timeout(600)
        ck("bấm Bàn giao → gọi pc_admin_handover đơn 21 + máy đầu danh sách (online, sạch)", s.calls("pc_admin_handover") == [{"p_rental": 21, "p_pc": PC3, "p_reinstall": None}], s.calls("pc_admin_handover"))
        s.page.click('#pcs-adm-tbl tr[data-r="20"] [data-ra="plus"]'); s.page.wait_for_timeout(400)
        ck("+1 lượt → pc_admin_rental_set add_reinstall 1", s.calls("pc_admin_rental_set") == [{"p_rental": 20, "p_patch": {"add_reinstall": 1}}], s.calls("pc_admin_rental_set"))
        s.page.click('#pcs-adm-tbl tr[data-r="21"] [data-ra="end"]'); s.page.wait_for_timeout(400)
        ck("Huỷ đơn chờ → hỏi + gọi pc_admin_rental_end có hoàn tiền", s.calls("pc_admin_rental_end") == [{"p_rental": 21, "p_refund": True}] and "HOÀN TIỀN" in s.dialogs[-1], (s.calls("pc_admin_rental_end"), s.dialogs[-1:]))
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(200)
        opts = s.js("() => [...document.querySelectorAll('#pcs-set-prod option')].map(o => [o.value, o.selected])")
        ck("Cài đặt bán: chọn được sản phẩm VPS, đang chọn VPS GPU BLUE", ["", False] in opts and [PROD, True] in opts and [OTHER, False] in opts, opts)
        s.page.fill("#pcs-set-max", "3"); s.page.uncheck("#pcs-set-1511"); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(500)
        ck("Lưu → pc_admin_sell đúng sản phẩm, chỉ 22H2, 3 lần cài lại", s.calls("pc_admin_sell") == [{"p_patch": {"product": PROD, "os": [{"id": "22h2", "name": "Windows 10 Pro 22H2"}], "reinstall_max": 3}}], s.calls("pc_admin_sell"))
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=site]').click(); subShow('site', 'maint'); }"); s.page.wait_for_timeout(300)
        ck("Cài đặt → Bảo trì có thêm dòng 'Bảo trì riêng VPS GPU' + lời nhắn", s.js("() => !!document.getElementById('mt-pc') && !!document.getElementById('mt-pcmsg') && document.getElementById('mt-pc').closest('.mtbox').innerText.includes('Bảo trì riêng VPS GPU')"))
        s.page.check("#mt-pc"); s.page.fill("#mt-pcmsg", "Nâng cấp máy"); s.page.click("#mt-save"); s.page.wait_for_timeout(1200)
        sv = s.js("() => ({ on: !!SITE.pc_maint, msg: SITE.pc_maint_msg, upd: window.__FAKE.calls.some(c => c.kind === 'from' && c.table === 'settings' && c.op === 'update'), site: !!SITE.maint })")
        ck("Lưu bảo trì → ghi settings (pc_maint = bật, lời nhắn), KHÔNG bật bảo trì toàn web", sv["on"] and sv["msg"] == "Nâng cấp máy" and sv["upd"] and not sv["site"], sv)
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=pc]').click(); }"); s.page.wait_for_timeout(500)
        ck("khung Đơn VPS GPU (admin) hiện nhãn '🛠️ Đang bảo trì'", "Đang bảo trì" in s.js("() => document.getElementById('pcs-adm-on').textContent"), s.js("() => document.getElementById('pcs-adm-on').textContent"))
        s.js("() => { SITE.pc_maint = false; }")
        ck("bảng máy có nút 🖥 Điều khiển mở play.html?pc= (tab mới)", s.js("() => [...document.querySelectorAll('#pctbl a[href^=\"/play.html?pc=\"]')].every(a => a.target === '_blank')"))
        ck("admin: không lỗi JS / console, không chạy mã lạ", not s.errors and s.js("() => !window.__xss"), s.errors)
        s.close()
        print("5d. Đơn hàng › Giao: chọn máy PC đang trống giao thẳng cho khách (SQL v45)")
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.js("""() => { const F = window.__FAKE; F.db.orders = [{ id: 'o-vps1', user_id: F.db.profiles[0].id, product_id: '%s', product_name: 'VPS GPU BLUE · 7 ngày', qty: 1, total: 360000,
                     status: 'pending', days: 7, created_at: new Date(Date.now() - 7200e3).toISOString(), items: 'Đang chuẩn bị.' },
                   { id: 'o-other', user_id: F.db.profiles[0].id, product_id: 'zzz', product_name: 'CLONE', qty: 3, total: 9000, status: 'pending', days: null, created_at: new Date().toISOString(), items: '' }];
                   return loadAdmin(); }""" % PROD)
        s.page.wait_for_timeout(600)
        s.js("() => { const b = document.querySelector('#otbl [data-deliver=\"o-vps1\"]'); b.scrollIntoView(); b.click(); }")
        s.page.wait_for_function("() => document.querySelectorAll('#dl-pcl [data-pc]').length === 2", timeout=6000)
        d = s.js("""() => ({ box: !document.getElementById('dl-pcbox').hidden, items: [...document.querySelectorAll('#dl-pcl [data-pc]')].map(b => [b.dataset.pc, b.classList.contains('on'), b.innerText.replace(/\\s+/g, ' ')]),
                    os: [...document.getElementById('dl-pcos').options].map(o => o.value), sel: document.getElementById('dl-pcos').value, go: !document.getElementById('dl-pcgo').disabled,
                    hint: document.getElementById('dl-pchint').textContent })""")
        ck("đơn VPS chờ giao: hiện khung 'Giao máy PC đang trống' 2 máy, tự chọn máy online + sạch, bản Windows theo máy", d["box"] and d["items"][0][0] == PC3 and d["items"][0][1] and d["os"] == ["22h2", "1511"] and d["sel"] == "22h2" and d["go"] and "dùng được ngay" in d["hint"], d)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-5d-deliver.png"))
        s.page.click(f'#dl-pcl [data-pc="{PC2}"]'); s.page.wait_for_timeout(200)
        h2 = s.js("() => [document.getElementById('dl-pcos').value, document.getElementById('dl-pchint').textContent]")
        ck("chọn máy khách cũ trả (đang tắt) → báo sẽ tự xoá sạch + cài khi bật lên", h2[0] == "1511" and "xoá sạch" in h2[1] and "khi bật lên" in h2[1], h2)
        s.page.click(f'#dl-pcl [data-pc="{PC3}"]'); s.accept = True
        s.page.click("#dl-pcgo"); s.page.wait_for_timeout(900)
        ck("bấm Giao → gọi pc_admin_deliver(đơn, máy, 22h2), đóng hộp", s.calls("pc_admin_deliver") == [{"p_order": "o-vps1", "p_pc": PC3, "p_os": "22h2"}] and s.js("() => document.getElementById('deldlg').hidden"), s.calls("pc_admin_deliver"))
        s.js("() => { const b = document.querySelector('#otbl [data-deliver=\"o-other\"]'); b.click(); }"); s.page.wait_for_timeout(500)
        ck("đơn không phải VPS / nhiều máy: KHÔNG hiện khung máy PC", s.js("() => document.getElementById('dl-pcbox').hidden"))
        s.js("() => document.getElementById('deldlg').hidden = true")
        ck("5d: không lỗi JS", not s.errors, s.errors)
        s.close()

        print("5b. ♻️ Tự thu hồi máy hết hạn (SQL v44)")
        mine2 = {"product": PROD, "reinstall_max": 2, "os": MINE["os"], "items": [
            {"rental": 41, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(-600), "grace_until": iso(1200), "left": 2, "used": 0, "end_why": None,
             "pc": {"id": PC1, "name": "May-01", "code": "A1", "os": "22h2", "online": True, "link": True, "remote": True, "off": False, "lock": True, "job": None, "last_job": None, "ram_gb": 128, "gpus": []}},
            {"rental": 40, "state": "ended", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(-7200), "grace_until": None, "left": 2, "used": 0, "end_why": "expired", "pc": None}]}
        adm2 = dict(ADM, reclaim={"on": True, "grace_min": 30, "clean_min": 60, "os": None, "off": True, "since": iso(-86400)},
                    free=[dict(ADM["free"][0], clean=False, cleaning=True, reclaim_at=None), dict(ADM["free"][1], reclaim_at=iso(1800), cleaning=False)],
                    rentals=[dict(ADM["rentals"][1], id=50, until=iso(-600), grace_until=iso(1200), pc=dict(ADM["rentals"][1]["pc"], lock=True)),
                             dict(ADM["rentals"][1], id=49, state="ended", until=iso(-7200), ended_at=iso(-5400), end_why="expired", pc=None)])
        s = Site(br, html, False, dict(shop, mine=mine2, bought=[]))
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 2", timeout=8000)
        c2 = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => ({ t: c.innerText.replace(/\\s+/g, ' '), cd: !!c.querySelector('.m3m-exp [data-cd]'), ctl: !!c.querySelector('a[href^=\"/play.html?pc=\"]'), renew: !!c.querySelector('[data-pcsrenew]') }))")
        ck("khách: hết hạn trong thời gian chờ → 'Hết hạn — đang giữ máy', máy đã khoá, gia hạn trước giờ nào, đồng hồ đếm ngược, còn nút Gia hạn, chưa cho điều khiển",
           "đang giữ máy" in c2[0]["t"] and "Máy đã khoá" in c2[0]["t"] and "Gia hạn trước" in c2[0]["t"] and "xoá sạch" in c2[0]["t"] and c2[0]["cd"] and c2[0]["renew"] and not c2[0]["ctl"], c2[0])
        ck("khách: lượt thuê tự kết thúc → nói rõ máy đã thu hồi + xoá sạch, thuê máy mới", "Đã kết thúc" in c2[1]["t"] and "thu hồi" in c2[1]["t"] and "thuê máy mới" in c2[1]["t"], c2[1])
        s.page.screenshot(path=os.path.join(SHOTS, "shop-8-reclaim-khach.png"))
        s.page.click("#pcs-mine-list [data-pcsrenew]"); s.page.wait_for_timeout(500)
        s.js("() => { window.__FAKE_HOOK.pc_my_renew = a => ({ ok: true, until: new Date(Date.now() + 7 * 86400e3).toISOString(), was_off: false }); }")
        gb = s.page.query_selector("#pcsdlg [data-pcsrngo], #pcsdlg .acts .btn:not(.ghost)")
        if gb: gb.click(); s.page.wait_for_timeout(800)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("gia hạn lúc máy đang giữ → báo 'máy tự mở lại sau khoảng 1–2 phút'", "tự mở lại" in tt, tt)
        ck("khách (5b): không lỗi JS", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, dict(shop, adm=adm2, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=pc]').click(); }"); s.page.wait_for_timeout(900)
        rows = s.js("() => [...document.querySelectorAll('#pcs-adm-tbl tr')].map(r => r.innerText.replace(/\\s+/g, ' '))")
        ck("admin: đơn đang thuê hết hạn → 'giữ máy tới … quá giờ tự thu hồi' + máy '🔒 đã khoá'; đơn tự kết thúc → '♻️ tự thu hồi'",
           any("giữ máy tới" in r and "tự thu hồi" in r and "đã khoá" in r for r in rows) and any("♻️ tự thu hồi: hết hạn không gia hạn" in r for r in rows), rows)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(300)
        rc = s.js("() => ({ vis: !document.getElementById('pcs-rc').hidden, on: document.getElementById('pcs-rc-on').checked, g: document.getElementById('pcs-rc-grace').value, c: document.getElementById('pcs-rc-clean').value, off: document.getElementById('pcs-rc-off').checked, t: document.getElementById('pcs-rc').innerText })")
        ck("⚙ Cài đặt bán có ô '♻️ Tự thu hồi máy hết hạn' (bật, 30 phút, mốc 60, tự tắt) + giải thích", rc["vis"] and rc["on"] and rc["g"] == "30" and rc["c"] == "60" and rc["off"] and "tự tắt" in rc["t"] and "Bàn giao" in rc["t"], rc)
        s.page.fill("#pcs-rc-grace", "20"); s.page.fill("#pcs-rc-clean", "45"); s.page.select_option("#pcs-rc-os", "1511"); s.page.uncheck("#pcs-rc-off"); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(600)
        sv = s.calls("pc_admin_sell")
        ck("Lưu → pc_admin_sell kèm reclaim {on, 20, 45, 1511, không tự tắt}", sv and sv[-1]["p_patch"].get("reclaim") == {"on": True, "grace_min": 20, "clean_min": 45, "os": "1511", "off": False}, sv)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(200)
        if s.js("() => document.getElementById('pcs-adm-setbox').hidden"): s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(200)
        s.page.fill("#pcs-rc-grace", "50"); s.page.fill("#pcs-rc-clean", "40"); n0 = len(s.calls("pc_admin_sell")); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(400)
        ck("mốc cài sạch nhỏ hơn thời gian chờ → báo lỗi, không gửi", len(s.calls("pc_admin_sell")) == n0)
        s.page.click('#pcs-adm-tbl tr[data-r="50"] [data-ra="hand"]'); s.page.wait_for_timeout(300)
        hd = s.js("() => document.getElementById('pcsdlg').innerText")
        ck("hộp Bàn giao: máy trống ghi '🧽 đang tự cài sạch' / '♻️ tự cài sạch lúc …'", "đang tự cài sạch" in hd and "tự cài sạch lúc" in hd, hd)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-9-reclaim-admin.png"))
        ck("admin (5b): không lỗi JS", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=pc]').click(); }"); s.page.wait_for_timeout(700)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(300)
        ck("chưa chạy SQL v44 (không có reclaim) → ẩn ô tự thu hồi, Lưu không gửi reclaim", s.js("() => document.getElementById('pcs-rc').hidden"))
        s.page.click("#pcs-set-save"); s.page.wait_for_timeout(500)
        ck("(Lưu khi chưa có v44 → không kèm reclaim)", all("reclaim" not in c["p_patch"] for c in s.calls("pc_admin_sell")), s.calls("pc_admin_sell"))
        s.close()
        print("5e. 🗑 Khách tự huỷ máy (SQL v45) + thẻ 'Đã kết thúc' tự ẩn sau 30 phút")
        mine3 = {"product": PROD, "reinstall_max": 2, "os": MINE["os"], "cancel": True, "items": [
            {"rental": 61, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(3 * 86400), "left": 2, "used": 0, "end_why": None,
             "pc": {"id": PC1, "name": "May-01", "code": "A1", "os": "22h2", "online": True, "link": True, "remote": True, "off": False, "job": None, "last_job": None, "ram_gb": 128, "gpus": []}},
            {"rental": 60, "state": "ended", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(-600), "left": 2, "used": 0, "end_why": "expired",
             "ended_at": iso(-600), "hide_at": iso(1200), "pc": None},
            {"rental": 59, "state": "ended", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(-4000), "left": 2, "used": 0, "end_why": "expired",
             "ended_at": iso(-3600), "hide_at": iso(-1800), "pc": None}]}
        s = Site(br, html, False, dict(shop, mine=mine3, bought=[]))
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 2", timeout=8000)
        c3 = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ck("thẻ 'Đã kết thúc' quá giờ ẩn → không hiện nữa; thẻ vừa kết thúc ghi 'Thẻ này tự ẩn lúc …'; thẻ đang thuê có nút 🗑 Huỷ máy",
           len(c3) == 2 and "Huỷ máy" in c3[0] and "Đã kết thúc" in c3[1] and "tự ẩn lúc" in c3[1] and "Huỷ máy" not in c3[1], c3)
        s.page.click("#pcs-mine-list [data-pcscxl]"); s.page.wait_for_timeout(300)
        d3 = s.js("() => ({ t: document.getElementById('pcsdlg').innerText, dis: document.querySelector('#pcsdlg [data-pcscxgo]').disabled })")
        ck("bấm Huỷ máy → hộp xác nhận: gỡ khỏi tài khoản, xoá sạch mọi ổ, KHÔNG hoàn tiền (ghi thời gian còn lại); nút Huỷ khoá tới khi tick 'Tôi hiểu'",
           "gỡ khỏi tài khoản" in d3["t"] and "xoá sạch" in d3["t"] and "KHÔNG hoàn tiền" in d3["t"] and "Không hoàn tác" in d3["t"] and "ngày" in d3["t"] and d3["dis"], d3)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-10-huy-may.png"))
        s.page.click("#pcsdlg [data-pcscxgo]", force=True); s.page.wait_for_timeout(300)
        ck("chưa tick 'Tôi hiểu' → bấm không ăn, không gọi pc_my_cancel", not s.calls("pc_my_cancel"))
        s.page.check("#pcs-cx-ok"); s.page.click("#pcsdlg [data-pcscxgo]"); s.page.wait_for_timeout(900)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("tick + bấm → gọi pc_my_cancel(máy) đúng 1 lần, đóng hộp, báo 'Đã huỷ máy'", s.calls("pc_my_cancel") == [{"p_pc": PC1}] and s.js("() => document.getElementById('pcsdlg').hidden") and "Đã huỷ máy" in tt, (s.calls("pc_my_cancel"), tt))
        s.page.click("#pcs-mine-list [data-pcscxl]"); s.page.wait_for_timeout(200)
        s.page.click("#pcsdlg [data-pcsx]"); s.page.wait_for_timeout(200)
        ck("bấm 'Giữ máy' → đóng hộp, không gọi thêm", s.js("() => document.getElementById('pcsdlg').hidden") and len(s.calls("pc_my_cancel")) == 1)
        ck("5e: không lỗi JS", not s.errors, s.errors)
        s.close()
        s = Site(br, html, False, dict(shop, mine=dict(mine3, cancel=False), bought=[]))
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 2", timeout=8000)
        ck("máy chủ chưa có v45 (không có cờ cancel) → không hiện nút Huỷ máy", not s.js("() => !!document.querySelector('[data-pcscxl]')"))
        s.close()

        print("5h. ⏻ Nguồn máy (SQL v48): khách tự khởi động lại / tắt máy + trạng thái 'Đang khởi động lại…' / 'Đã tắt máy'")
        P4, P5, P6, P7 = ["00000000-0000-4000-8000-0000000000c%d" % i for i in range(4, 8)]
        def pcx(pid, nm, online, pow_=None):
            return {"id": pid, "name": nm, "code": "", "os": "22h2", "online": online, "link": online, "remote": True, "off": False, "job": None, "last_job": None,
                    "ram_gb": 128, "gpus": [], "pow": pow_}
        def it(r, pc): return {"rental": r, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(3 * 86400), "left": 2, "used": 0, "pc": pc}
        mine4 = {"product": PROD, "reinstall_max": 2, "os": MINE["os"], "cancel": True, "power": True, "items": [
            it(71, pcx(PC1, "Nguon-01", True)),
            it(72, pcx(PC2, "Nguon-02", True, {"cmd": "reboot", "state": "done", "at": iso(-60), "by": "customer"})),
            it(73, pcx(PC3, "Nguon-03", False, {"cmd": "shutdown", "state": "done", "at": iso(-1200), "by": "customer"})),
            it(74, pcx(P4, "Nguon-04", False, {"cmd": "reboot", "state": "done", "at": iso(-1200), "by": "customer"})),
            it(75, pcx(P5, "Nguon-05", True, {"cmd": "shutdown", "state": "queued", "at": iso(-30), "by": "admin"})),
            it(76, pcx(P6, "Nguon-06", False, {"cmd": "shutdown", "state": "done", "at": iso(-600), "by": "admin"})),
            it(77, pcx(P7, "Nguon-07", False, {"cmd": "reboot", "state": "done", "at": iso(-300), "by": "admin"}))]}
        s = Site(br, html, False, dict(shop, mine=mine4, bought=[]))
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 7", timeout=8000)
        cs = s.js("""() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => { const p = c.querySelector('[data-pcspow]'), ctl = c.querySelector('.m3m-acts .btn.sm');
                     return { t: c.innerText.replace(/\\s+/g, ' '), pow: p ? (p.disabled ? 'off' : 'on') : 'none', ctl: ctl ? (ctl.tagName === 'A' ? 'on' : 'off') : 'none' }; })""")
        ck("máy đang bật: có nút ⏻ Nguồn bấm được, Điều khiển bấm được", "Sẵn sàng" in cs[0]["t"] and "Nguồn" in cs[0]["t"] and cs[0]["pow"] == "on" and cs[0]["ctl"] == "on", cs[0])
        ck("vừa khởi động lại (1 phút): 'Đang khởi động lại…' + '1–3 phút'; Nguồn khoá, Điều khiển vẫn mở được",
           "Đang khởi động lại" in cs[1]["t"] and "1–3 phút" in cs[1]["t"] and "Shop vừa" not in cs[1]["t"] and cs[1]["pow"] == "off" and cs[1]["ctl"] == "on", cs[1])
        ck("khách đã tắt máy (máy không báo về): 'Đã tắt máy' + 'Bạn đã tắt máy lúc …' + nhắn shop bật nguồn; Nguồn + Điều khiển khoá",
           "Đã tắt máy" in cs[2]["t"] and "Bạn đã tắt máy lúc" in cs[2]["t"] and "nhắn shop bật nguồn" in cs[2]["t"] and cs[2]["pow"] == "off" and cs[2]["ctl"] == "off", cs[2])
        ck("khởi động lại 20 phút trước mà máy chưa báo về → về trạng thái 'Máy đang tắt / mất mạng' như cũ", "Máy đang tắt / mất mạng" in cs[3]["t"] and "khởi động lại" not in cs[3]["t"], cs[3])
        ck("shop vừa bấm tắt (lệnh chưa tới máy): 'Đang tắt máy…' + 'Đang gửi lệnh tới máy'", "Đang tắt máy" in cs[4]["t"] and "Đang gửi lệnh tới máy" in cs[4]["t"] and cs[4]["pow"] == "off", cs[4])
        ck("shop đã tắt máy: 'Shop đã tắt máy lúc …'", "Đã tắt máy" in cs[5]["t"] and "Shop đã tắt máy lúc" in cs[5]["t"], cs[5])
        ck("shop khởi động lại 5 phút trước, máy chưa báo về: 'Shop vừa khởi động lại máy'", "Đang khởi động lại" in cs[6]["t"] and "Shop vừa khởi động lại máy" in cs[6]["t"], cs[6])
        s.page.screenshot(path=os.path.join(SHOTS, "shop-14-trang-thai-nguon.png"))
        s.page.click('#pcs-mine-list [data-pcspow="%s"]' % PC1); s.page.wait_for_timeout(300)
        d5 = s.js("""() => { const m = document.getElementById('pcsdlg'), g = m.querySelector('[data-pcspgo="shutdown"]'), cb = document.getElementById('pcs-pw-ok'), lb = cb.closest('label').getBoundingClientRect(), r = cb.getBoundingClientRect();
                     return { open: !m.hidden, t: m.innerText.replace(/\\s+/g, ' '), dis: g.disabled, row: Math.abs((r.top + r.bottom) / 2 - (lb.top + lb.bottom) / 2) < 6 && lb.height < 40 }; }""")
        ck("bấm ⏻ Nguồn → hộp 'Nguồn máy Nguon-01': 🔁 Khởi động lại (tự bật lại, 1–3 phút) + ⏻ Tắt máy (tắt hẳn, nhắn shop bật nguồn, thời gian thuê vẫn tính)",
           d5["open"] and "Nguồn máy Nguon-01" in d5["t"] and "tự bật lại" in d5["t"] and "1–3 phút" in d5["t"] and "tắt hẳn" in d5["t"] and "nhắn shop bật nguồn" in d5["t"] and "thời gian thuê vẫn tính" in d5["t"], d5)
        ck("nút Tắt máy khoá tới khi tick 'Tôi hiểu'; ô tick nằm cùng hàng chữ", d5["dis"] and d5["row"], d5)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-13-nguon-may.png"))
        s.page.click('#pcsdlg [data-pcspgo="shutdown"]', force=True); s.page.wait_for_timeout(300)
        ck("chưa tick → bấm Tắt máy không ăn, không gọi pc_my_power", not s.calls("pc_my_power"))
        s.page.click('#pcsdlg [data-pcspgo="reboot"]'); s.page.wait_for_timeout(900)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("bấm 'Khởi động lại ngay' → pc_my_power(máy, reboot) đúng 1 lần, đóng hộp, báo 'Đã gửi lệnh khởi động lại'",
           s.calls("pc_my_power") == [{"p_pc": PC1, "p_cmd": "reboot"}] and s.js("() => document.getElementById('pcsdlg').hidden") and "Đã gửi lệnh khởi động lại" in tt, (s.calls("pc_my_power"), tt))
        s.page.click('#pcs-mine-list [data-pcspow="%s"]' % PC1); s.page.wait_for_timeout(300)
        s.page.check("#pcs-pw-ok"); s.page.click('#pcsdlg [data-pcspgo="shutdown"]'); s.page.wait_for_timeout(900)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("tick + Tắt máy → pc_my_power(máy, shutdown), báo 'Đã gửi lệnh tắt máy … nhắn shop bật nguồn'",
           s.calls("pc_my_power")[-1:] == [{"p_pc": PC1, "p_cmd": "shutdown"}] and "Đã gửi lệnh tắt máy" in tt and "nhắn shop bật nguồn" in tt, (s.calls("pc_my_power"), tt))
        s.js("() => { window.__SHOP.powErr = 'OFFLINE'; }")
        s.page.click('#pcs-mine-list [data-pcspow="%s"]' % PC1); s.page.wait_for_timeout(300)
        s.page.click('#pcsdlg [data-pcspgo="reboot"]'); s.page.wait_for_timeout(700)
        ee = s.js("() => ({ open: !document.getElementById('pcsdlg').hidden, e: document.getElementById('pcs-pw-err').textContent })")
        ck("máy mất kết nối (OFFLINE) → báo lỗi tiếng Việt trong hộp, hộp vẫn mở", ee["open"] and "mất kết nối" in ee["e"] and "nhắn shop" in ee["e"], ee)
        s.js("() => { window.__SHOP.powErr = ''; window.__SHOP.powRes = { ok: true, dup: true, cmd: 'reboot' }; }")
        s.page.click('#pcsdlg [data-pcspgo="reboot"]'); s.page.wait_for_timeout(900)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("lệnh trước chưa tới máy (dup) → báo 'đang có lệnh chờ nhận'", "lệnh chờ nhận" in tt, tt)
        ck("5h: không lỗi JS, không chèn được mã", not s.errors and document_ok(s), s.errors)
        s.close()
        s = Site(br, html, False, dict(shop, mine=mine4, bought=[]), mobile=True)
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 7", timeout=8000)
        s.js("id => document.querySelector('#pcs-mine-list [data-pcspow=\"' + id + '\"]').click()", PC1); s.page.wait_for_timeout(400)
        mo = s.js("""() => { const d = document.querySelector('#pcsdlg .dlg').getBoundingClientRect(); return { w: d.width, over: document.documentElement.scrollWidth - innerWidth, fit: d.left >= 0 && d.right <= innerWidth + 1 }; }""")
        ck("điện thoại 390px: hộp Nguồn máy vừa màn hình, không tràn ngang", mo["fit"] and mo["over"] <= 0, mo)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-13b-nguon-may-mobile.png"))
        s.close()
        s = Site(br, html, False, dict(shop, mine=dict(mine4, power=False), bought=[]))
        s.page.wait_for_function("() => document.querySelectorAll('#pcs-mine-list .pcs-card').length === 7", timeout=8000)
        ck("máy chủ chưa có v48 (không có cờ power) → không hiện nút ⏻ Nguồn", not s.js("() => !!document.querySelector('[data-pcspow]')"))
        s.close()

        print("5f. 🔑 Công tắc 'Cho khách quyền Admin' (SQL v46)")
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=pc]').click(); }"); s.page.wait_for_timeout(700)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(500)
        ca = s.js("() => ({ vis: !document.getElementById('pcs-ca-box').hidden, on: document.getElementById('pcs-ca').checked, t: document.getElementById('pcs-ca-box').innerText })")
        ck("⚙ Cài đặt bán có ô '🔑 Cho khách quyền Admin' (đang BẬT) + giải thích khởi động lại 1 lần / tắt thì hạ quyền", ca["vis"] and ca["on"] and "khởi động lại máy 1 lần" in ca["t"] and "tài khoản thường" in ca["t"], ca)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-11-quyen-admin.png"))
        n0 = len(s.calls("pc_admin_set_flags")); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(600)
        ck("Lưu mà không đổi công tắc → không gọi pc_admin_set_flags", len(s.calls("pc_admin_set_flags")) == n0)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(200)
        if s.js("() => document.getElementById('pcs-adm-setbox').hidden"): s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(500)
        s.page.uncheck("#pcs-ca"); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(700)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("bỏ tick + Lưu → pc_admin_set_flags({cust_admin: false}) + báo 'Đã TẮT quyền Admin'", s.calls("pc_admin_set_flags")[-1:] == [{"p_patch": {"cust_admin": False}}] and "TẮT quyền Admin" in tt, (s.calls("pc_admin_set_flags"), tt))
        ck("5f: không lỗi JS", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.js("""() => { window.__FAKE_HOOK.pc_admin_flags = () => ({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.pc_admin_flags' } }); }""")
        s.js("() => { document.querySelector('#adm-tabs button[data-tab=pc]').click(); }"); s.page.wait_for_timeout(700)
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(500)
        ck("chưa chạy SQL v46 → ẩn ô quyền Admin", s.js("() => document.getElementById('pcs-ca-box').hidden"))
        s.close()

        print("5g. 💰 Thẻ VPS GPU ở trang ngoài: giá TỪNG gói + giá / ngày, gói rẻ nhất / ngày có nhãn 'Rẻ nhất'; bấm gói → mở hộp mua chọn sẵn gói đó")
        for mob in (False, True):
            s = Site(br, html, False, dict(shop, bought=[]), mobile=mob)
            s.page.wait_for_function("id => !!document.querySelector('#grid .m3-plan[data-buy=\"' + id + '\"]')", arg=PROD, timeout=8000)
            pg = s.js("""id => { const c = document.querySelector('#grid .m3-plan[data-buy="' + id + '"]').closest('.m3-row'), bs = [...c.querySelectorAll('.m3-plan')];
                  c.scrollIntoView({ block: 'center' });
                  return { n: bs.length, t: bs.map(b => b.innerText.replace(/\\s+/g, ' ').trim()), best: bs.map(b => b.classList.contains('best')), days: bs.map(b => +b.dataset.days),
                           chip: !!c.querySelector('.days-chip'), over: document.documentElement.scrollWidth - innerWidth,
                           fit: bs.every(b => b.scrollWidth <= b.clientWidth + 1 && b.getBoundingClientRect().right <= c.getBoundingClientRect().right + 1),
                           box: c.querySelector('.m3-box').innerText.replace(/\\s+/g, ' ') }; }""", PROD)
            tag = "điện thoại" if mob else "máy tính"
            ck(f"{tag}: thẻ có 3 gói 7 · 15 · 30 ngày, mỗi gói ghi tổng tiền + giá / ngày; bỏ dòng 'Gói: 7 · 15 · 30 ngày' cũ",
               pg["n"] == 3 and pg["days"] == [7, 15, 30] and not pg["chip"] and "360.000đ" in pg["t"][0] and "51.429đ/ngày" in pg["t"][0]
               and "750.000đ" in pg["t"][1] and "50.000đ/ngày" in pg["t"][1] and "1.600.000đ" in pg["t"][2] and "53.333đ/ngày" in pg["t"][2], pg)
            ck(f"{tag}: gói rẻ nhất tính theo NGÀY (15 ngày) có nhãn 'Rẻ nhất' + −3%; gói đắt hơn / ngày (30 ngày) không có nhãn giảm",
               pg["best"] == [False, True, False] and "Rẻ nhất" in pg["t"][1] and "−3%" in pg["t"][1] and "−" not in pg["t"][2] and "Rẻ nhất" not in pg["t"][0] + pg["t"][2], pg)
            ck(f"{tag}: không tràn ngang, chữ trong ô gói không bị cắt; ô bên phải ghi giá mồi 'từ 50.000đ /ngày' (26/11: mức rẻ nhất tính theo ngày = gói 15 ngày, không còn 'từ 360.000đ') + nút 'Thuê ngay' (hàng cho thuê, không ghi 'Mua ngay')",
               pg["over"] <= 0 and pg["fit"] and "50.000đ" in pg["box"] and "/ngày" in pg["box"] and "360.000đ" not in pg["box"] and "Thuê ngay" in pg["box"] and "Mua ngay" not in pg["box"], pg)
            sp = s.js("""id => { const c = document.querySelector('#grid .m3-plan[data-buy="' + id + '"]').closest('.m3-row'), f = c.querySelector('.feats.spec'), x = f && f.querySelector('span');
                  return f ? { fl: (f.querySelector('.fl') || {}).innerText || '', chips: [...f.querySelectorAll('span')].map(e => e.innerText), fs: parseFloat(getComputedStyle(x).fontSize), fw: +getComputedStyle(x).fontWeight } : null; }""", PROD)
            ck(f"{tag}: 26/11 · chữ CẤU HÌNH của VPS GPU nổi bật (nhãn 'Cấu hình', chữ đậm 800, cỡ ≥ 12,5px)", sp and sp["fl"] == "Cấu hình" and sp["chips"] == ["2686V4", "RAM 128GB"] and sp["fs"] >= 12.5 and sp["fw"] >= 800, sp)
            s.page.wait_for_timeout(300)
            s.page.screenshot(path=os.path.join(SHOTS, "shop-12-bang-gia%s.png" % ("-mobile" if mob else "")))
            s.page.click('#grid .m3-plan[data-days="15"][data-buy="%s"]' % PROD); s.page.wait_for_timeout(600)
            md = s.js("""() => ({ open: !document.getElementById('modal').hidden, on: [...document.querySelectorAll('#m-plans button.on')].map(b => b.dataset.d),
                          best: [...document.querySelectorAll('#m-plans button.best')].map(b => b.dataset.d), t: [...document.querySelectorAll('#m-plans button')].map(b => b.innerText.replace(/\\s+/g, ' ')) })""")
            ck(f"{tag}: bấm gói 15 ngày → mở hộp mua chọn sẵn 15 ngày; trong hộp gói 15 ngày cũng có nhãn 'Rẻ nhất'",
               md["open"] and md["on"] == ["15"] and md["best"] == ["15"] and any("Rẻ nhất" in x for x in md["t"] if x.startswith("15")), md)
            if not mob: s.page.screenshot(path=os.path.join(SHOTS, "shop-12c-hop-mua-15-ngay.png"))
            s.js("() => closeBuy()"); s.page.wait_for_timeout(200)
            s.page.click('#grid [data-buy="%s"].btn' % PROD); s.page.wait_for_timeout(500)
            ck(f"{tag}: bấm 'Thuê ngay' (không chọn gói) → vẫn chọn sẵn 30 ngày như cũ", s.js("() => [...document.querySelectorAll('#m-plans button.on')].map(b => b.dataset.d)") == ["30"])
            ck(f"5g {tag}: không lỗi JS", not s.errors, s.errors)
            s.close()
        def grid_plans(prods):
            ctx = br.new_context(viewport={"width": 1360, "height": 900}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
            ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                % (json.dumps({"admin": False, "db": {"product_list": prods, "products": prods}}), json.dumps(dict(shop, bought=[])), HOOK))
            pg2 = ctx.new_page()
            pg2.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html) if r.request.url in (ORIGIN + "/admin", ORIGIN + "/")
                      else r.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js"))) if "supabase-js" in r.request.url
                      else r.fulfill(status=204, body=""))
            pg2.goto(ORIGIN + "/", wait_until="load"); pg2.wait_for_timeout(2600)
            o = pg2.evaluate("""id => { const bs = [...document.querySelectorAll('#grid .m3-plan[data-buy="' + id + '"]')];
                     return { n: bs.length, best: bs.map(b => b.classList.contains('best')), dis: bs.every(b => b.disabled), t: bs.map(b => b.innerText.replace(/\\s+/g, ' ')) }; }""", PROD)
            pg2.evaluate("id => openBuy(id)", PROD); pg2.wait_for_timeout(400)
            o["dlg"] = pg2.evaluate("() => [...document.querySelectorAll('#m-plans button')].map(b => [b.dataset.d, b.classList.contains('best')])")
            ctx.close()
            return o
        o1 = grid_plans([dict(PRODUCTS[0], plans=[{"days": 30, "price": 1500000}], price=1500000, stock=0), PRODUCTS[1]])
        ck("chỉ 1 gói: không gắn nhãn 'Rẻ nhất'; hết hàng → ô gói bấm không được", o1["n"] == 1 and o1["best"] == [False] and o1["dis"] and "50.000đ/ngày" in o1["t"][0], o1)
        o2 = grid_plans([dict(PRODUCTS[0], plans=[{"days": 7, "price": 350000}, {"days": 15, "price": 700000}, {"days": 30, "price": 1400000}], price=350000), PRODUCTS[1]])
        ck("2 gói cùng rẻ nhất / ngày (15 + 30 ngày đều 46.667đ) → gắn 'Rẻ nhất' cả 2, ở thẻ lẫn trong hộp mua",
           o2["best"] == [False, True, True] and all("46.667đ/ngày" in x and "−7%" in x for x in o2["t"][1:]) and o2["dlg"] == [["7", False], ["15", True], ["30", True]], o2)
        o3 = grid_plans([dict(PRODUCTS[0], plans=[{"days": 7, "price": 70000}, {"days": 14, "price": 140000}], price=70000), PRODUCTS[1]])
        ck("mọi gói cùng giá / ngày → không gắn nhãn nào", o3["best"] == [False, False] and o3["dlg"] == [["7", False], ["14", False]], o3)

        print("5c. Căn lề trang quản trị: mọi khối cùng mép trái / phải ở màn rộng 2296px, laptop 1366px, điện thoại 390px")
        for vw, vh in ((2296, 985), (1366, 768), (390, 844)):
            ctx = br.new_context(viewport={"width": vw, "height": vh}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
            init = {"admin": True, "db": {"product_list": PRODUCTS, "products": PRODUCTS}}
            ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                % (json.dumps(init), json.dumps(dict(shop, bought=[])), HOOK))
            pg = ctx.new_page()
            pg.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html) if r.request.url in (ORIGIN + "/admin", ORIGIN + "/")
                     else r.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js"))) if "supabase-js" in r.request.url
                     else r.fulfill(status=204, body=""))
            pg.goto(ORIGIN + "/admin", wait_until="load"); pg.wait_for_timeout(2600)
            for tb in ("cust", "pc"):
                pg.evaluate("t => document.querySelector('#adm-tabs button[data-tab=' + t + ']').click()", tb); pg.wait_for_timeout(700)
                al = pg.evaluate("""() => { const dp = document.querySelector('#drawer .dpanel'), E = [];
                    const vis = [...dp.querySelectorAll(':scope > .dbody')].find(x => !x.hidden), cs = getComputedStyle(vis), vr = vis.getBoundingClientRect();
                    const L = vr.left + vis.clientLeft + parseFloat(cs.paddingLeft), R = vr.left + vis.clientLeft + vis.clientWidth - parseFloat(cs.paddingRight);
                    const h2 = document.querySelector('#drawer .dhead h2').getBoundingClientRect();
                    for (const c of dp.children) { if (c.classList.contains('dhead') || c.classList.contains('dbody') || c.hidden || getComputedStyle(c).display === 'none') continue;
                      const b = c.getBoundingClientRect(); if (!b.width) continue; if (Math.abs(b.left - L) > 1.5 || Math.abs(b.right - R) > 1.5) E.push((c.id || c.className) + ' ' + Math.round(b.left - L) + '/' + Math.round(b.right - R)); }
                    if (Math.abs(h2.left - L) > 1.5) E.push('tiêu đề ' + Math.round(h2.left - L));
                    return { E, over: dp.scrollWidth - dp.clientWidth, n: [...dp.children].filter(c => !c.hidden && getComputedStyle(c).display !== 'none').length }; }""")
                ck(f"{vw}px · thẻ {tb}: cảnh báo, 5 nhóm, thanh mục con, tiêu đề thẳng mép với nội dung; không tràn ngang", not al["E"] and al["over"] <= 0 and al["n"] >= 4, al)
            ctx.close()
        print("5i. 🐧 Linux CachyOS (SQL v50): mua · VPS của tôi · đổi hệ điều hành · quản trị")
        OS_L = [dict(o, ready=True, linux=False) for o in INFO_ON["os"]] + [{"id": "cachyos", "name": "Linux CachyOS", "fast": False, "ready": False, "linux": True}]
        mine_l = json.loads(json.dumps(MINE)); mine_l["os"] = MINE["os"] + [{"id": "cachyos", "name": "Linux CachyOS"}]; mine_l["linux"] = True
        mine_l["items"][0]["pc"]["can"] = ["22h2", "1511", "cachyos"]                     # May-01 đổi được sang CachyOS
        mine_l["items"][1]["pc"]["can"] = ["22h2", "1511"]; mine_l["items"][1]["pc"]["job"] = {"state": "sent", "os": "cachyos", "at": iso(-120)}
        mine_l["items"][3]["pc"].update(os="cachyos", gpus=["NVIDIA GeForce GTX 1080"]); mine_l["items"][3]["os"] = "cachyos"; mine_l["items"][3]["os_name"] = "Linux CachyOS"
        adm_l = json.loads(json.dumps(ADM)); adm_l["os"] = OS_L; adm_l["lx"] = 2                  # SQL v50: pc_admin_rentals trả "lx": 2
        adm_l["free"][0]["can"] = ["22h2", "1511"]; adm_l["free"][1]["can"] = ["22h2", "1511", "cachyos"]
        adm_l["rentals"][0].update(os="cachyos", os_name="Linux CachyOS")
        s = Site(br, html, False, dict(shop, info=dict(INFO_ON, os=OS_L), mine=mine_l, bought=[], buyRes={"state": "active", "pc": PC1, "name": "May-01", "reinstall": True, "rental": 31, "order": "o2", "total": 360000}))
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }")
        s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(500)
        hd = s.js("() => ({ h: document.querySelector('#pcs-os .pcs-sec span').innerText, os: [...document.querySelectorAll('#pcs-os [data-pcsos]')].map(b => [b.dataset.pcsos, b.innerText.replace(/\\s+/g, ' ')]), how: document.querySelector('#pcs-os .pcs-how').innerText })")
        ck("có bản Linux → '① Chọn hệ điều hành', 3 lựa chọn; ô CachyOS ghi 'Linux / CachyOS' + 'Shop đang chuẩn bị máy' (chưa có máy cài được: ready = false)",
           hd["h"].startswith("① Chọn hệ điều hành") and [x[0] for x in hd["os"]] == ["22h2", "1511", "cachyos"] and "Linux" in hd["os"][2][1] and "CachyOS" in hd["os"][2][1]
           and "Shop đang chuẩn bị máy" in hd["os"][2][1] and "~20 phút" in hd["os"][1][1] and "đúng hệ điều hành bạn chọn" in hd["how"] and "đổi hệ điều hành 2 lần" in hd["how"], hd)
        s.page.click('#pcs-os [data-pcsos="cachyos"]'); s.page.wait_for_timeout(200)
        t = s.js("() => document.getElementById('pcs-os').innerText")
        ck("chọn CachyOS → lưu ý: điều khiển như máy Windows, KHÔNG dùng card NVIDIA, không chạy game Windows; cài 30–60 phút (+60 phút hạn)",
           "điều khiển từ xa như máy Windows" in t and "không dùng card đồ hoạ NVIDIA" in t and "game Windows" in t and "30–60 phút" in t, t)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-9-linux-buy.png"))
        s.js("() => { window.__SHOP.info.os[2].ready = true; }"); s.js("() => closeBuy()"); s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(400)
        s.page.click('#pcs-os [data-pcsos="cachyos"]'); s.page.wait_for_timeout(150)
        ck("có máy cài được (ready) → 'Cài theo yêu cầu · ~45 phút'", "~45 phút" in s.js("() => document.querySelector('#pcs-os [data-pcsos=\"cachyos\"]').innerText"))
        s.page.click("#m-plans button[data-d='7']"); s.page.click("#m-ok"); s.page.wait_for_timeout(700)
        d = s.js("() => { const m = document.getElementById('pcsdlg'); return m && !m.hidden ? m.innerText : ''; }")
        ck("mua CachyOS → pc_buy p_os = cachyos; hộp đợi máy: 'Đang cài Linux CachyOS cho bạn' · 30–60 phút",
           s.js("() => window.__SHOP.bought")[-1:] == [{"p_product": PROD, "p_days": 7, "p_os": "cachyos"}] and "Đang cài Linux CachyOS cho bạn" in d and "30–60 phút" in d, d)
        ck("nội dung gửi admin ghi 'Hệ điều hành: Linux CachyOS'", "Hệ điều hành: Linux CachyOS" in s.js("() => document.getElementById('pcsw-txt').textContent"))
        s.js("() => { const m = document.getElementById('pcsdlg'); if (m) m.hidden = true; }")
        s.js("() => PCSHOP.mine(true)") if s.js("() => typeof PCSHOP.mine === 'function'") else None
        s.page.wait_for_timeout(600)
        cards = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ck("thẻ máy đang cài CachyOS: '⚙️ Đang cài Linux CachyOS' · 'Máy đang cài Linux CachyOS (30–60 phút)'",
           any("Đang cài Linux CachyOS" in c and "Máy đang cài Linux CachyOS (30–60 phút)" in c for c in cards), cards)
        ck("thẻ máy chạy Linux không ghi tên card NVIDIA (Linux không dùng card)", any("Linux CachyOS" in c and "GTX 1080" not in c for c in cards) and any("GTX 1080" in c for c in cards), cards)
        s.page.click('#pcs-mine-list [data-pcsre="%s"]' % PC1); s.page.wait_for_timeout(300)
        rd = s.js("() => ({ h: document.querySelector('#pcsdlg h3').innerText, os: [...document.querySelectorAll('#pcsdlg [data-pcsreos]')].map(b => b.dataset.pcsreos), how: document.getElementById('pcs-re-how').innerText })")
        ck("hộp 'Cài lại / đổi hệ điều hành' của máy đổi được (can có cachyos): 3 lựa chọn, mặc định bản đang dùng (Windows 15–30 phút)",
           rd["h"].endswith("Cài lại / đổi hệ điều hành") and rd["os"] == ["22h2", "1511", "cachyos"] and "15–30 phút" in rd["how"] and "ổ C: (Windows)" in rd["how"], rd)
        s.page.click('#pcsdlg [data-pcsreos="cachyos"]'); s.page.wait_for_timeout(150)
        hw = s.js("() => document.getElementById('pcs-re-how').innerText")
        ck("chọn CachyOS → lời cảnh báo đổi theo: 30–60 phút + lưu ý không dùng card NVIDIA", "30–60 phút" in hw and "không dùng card đồ hoạ NVIDIA" in hw, hw)
        n0 = len(s.dialogs); s.page.click('#pcsdlg [data-pcsgo2]'); s.page.wait_for_timeout(600)
        ck("bấm Cài lại → xác nhận ghi 'sang Linux CachyOS' → pc_my_reinstall(p_os = cachyos)",
           s.calls("pc_my_reinstall")[-1:] == [{"p_pc": PC1, "p_os": "cachyos"}] and any("sang Linux CachyOS" in x for x in s.dialogs[n0:]), (s.calls("pc_my_reinstall"), s.dialogs[n0:]))
        s.close()
        mine_l2 = json.loads(json.dumps(mine_l)); mine_l2["items"][1]["pc"]["job"] = None
        s = Site(br, html, False, dict(shop, info=dict(INFO_ON, os=OS_L), mine=mine_l2, bought=[]))
        s.page.click('#pcs-mine-list [data-pcsre="%s"]' % PC2); s.page.wait_for_timeout(300)
        o2 = s.js("() => [...document.querySelectorAll('#pcsdlg [data-pcsreos]')].map(b => b.dataset.pcsreos)")
        ck("máy CHƯA đổi được sang Linux (can không có cachyos) → không hiện CachyOS", o2 == ["22h2", "1511"], o2)
        s.js("() => { const m = document.getElementById('pcsdlg'); if (m) m.hidden = true; }")
        cards = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ck("thẻ máy chạy Linux không ghi tên card NVIDIA (Linux không dùng card), máy Windows vẫn ghi", any("Linux CachyOS" in c and "GTX 1080" not in c for c in cards) and any("GTX 1080" in c for c in cards), cards)
        ck("không lỗi JS (khách, Linux)", not s.errors, s.errors)
        s.close()
        mine_old = json.loads(json.dumps(mine_l2)); mine_old.pop("linux"); [x["pc"].pop("can", None) for x in mine_old["items"] if x.get("pc")]
        s = Site(br, html, False, dict(shop, info=dict(INFO_ON, os=OS_L), mine=mine_old, bought=[]))
        s.page.click('#pcs-mine-list [data-pcsre="%s"]' % PC1); s.page.wait_for_timeout(300)
        o3 = s.js("() => [...document.querySelectorAll('#pcsdlg [data-pcsreos]')].map(b => b.dataset.pcsreos)")
        ck("máy chủ chưa chạy SQL v50 (không có 'can') → ẩn CachyOS (chưa kiểm được máy)", o3 == ["22h2", "1511"], o3)
        s.close()
        s = Site(br, html, True, dict(shop, info=dict(INFO_ON, os=OS_L), mine=mine_l2, adm=adm_l, bought=[]), path="/admin")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.page.wait_for_function("() => document.getElementById('pcs-waitbar') && !document.getElementById('pcs-waitbar').hidden", timeout=8000)
        s.page.click("#pcs-waitbar"); s.page.wait_for_timeout(600)
        s.page.click('#pcs-adm-tbl tr[data-r="21"] [data-ra="hand"]'); s.page.wait_for_timeout(300)
        hv = s.js("""() => ({ t: document.getElementById('pcsdlg').innerText, r: [...document.querySelectorAll('#pcsdlg input[name="pcs-hpc"]')].map(i => [i.value, i.disabled, i.checked]),
                              go: document.getElementById('pcs-h-go').disabled })""")
        ck("Bàn giao đơn CachyOS: máy chưa cài được bị khoá + ghi '⛔ chưa cài được Linux CachyOS', chọn sẵn máy cài được",
           hv["r"] == [[PC3, True, False], [PC2, False, True]] and "chưa cài được Linux CachyOS" in hv["t"] and not hv["go"], hv)
        s.page.click("#pcs-h-go"); s.page.wait_for_timeout(600)
        ck("bấm Bàn giao → pc_admin_handover đúng máy cài được (May-02)", s.calls("pc_admin_handover")[-1:] == [{"p_rental": 21, "p_pc": PC2, "p_reinstall": None}], s.calls("pc_admin_handover"))
        s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(300)
        st = s.js("() => ({ c: !!document.getElementById('pcs-set-cachyos'), on: (document.getElementById('pcs-set-cachyos') || {}).checked, lab: document.getElementById('pcs-set-cachyos').closest('span').innerText })")
        ck("Cài đặt bán: 'Bản bán: 22H2 · 1511 · 🐧 CachyOS', đang bán CachyOS thì tích sẵn", st["c"] and st["on"] is True and "Bản bán" in st["lab"] and "CachyOS" in st["lab"], st)
        s.page.click("#pcs-set-save"); s.page.wait_for_timeout(500)
        sv = s.calls("pc_admin_sell")
        ck("Lưu → os gửi kèm {id: cachyos, name: Linux CachyOS} (đã bán từ trước → không hỏi lại)", sv and {"id": "cachyos", "name": "Linux CachyOS"} in sv[-1]["p_patch"]["os"], sv[-1:])
        ck("không lỗi JS (quản trị, Linux)", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, dict(shop, bought=[]), path="/admin")                        # máy chủ CHƯA chạy SQL v50 (không có "lx")
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.page.wait_for_function("() => document.getElementById('pcs-waitbar') && !document.getElementById('pcs-waitbar').hidden", timeout=8000)
        s.page.click("#pcs-waitbar"); s.page.wait_for_timeout(600); s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(300)
        st = s.js("""() => { const c = document.getElementById('pcs-set-cachyos'), n = document.getElementById('pcs-set-cy-need');
                             return { dis: c.disabled, on: c.checked, off: document.getElementById('pcs-set-cy').classList.contains('off'), need: n.hidden ? '' : n.innerText,
                                      w: [document.getElementById('pcs-set-22h2').disabled, document.getElementById('pcs-set-1511').disabled] }; }""")
        ck("CHƯA chạy SQL v50: ô 🐧 CachyOS bị khoá + ghi '(chạy SQL v50 trước)'; 22H2 / 1511 vẫn chọn được",
           st["dis"] is True and st["on"] is False and st["off"] and "SQL v50" in st["need"] and st["w"] == [False, False], st)
        s.js("() => { const c = document.getElementById('pcs-set-cachyos'); c.disabled = false; c.checked = true; }")   # cố mở khoá bằng tay
        n0 = len(s.dialogs); s.page.click("#pcs-set-save"); s.page.wait_for_timeout(400)
        tt = s.js("() => [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | ')")
        ck("cố bật CachyOS khi chưa có v50 → báo 'Chưa chạy SQL v50', không hỏi, không lưu",
           "Chưa chạy SQL v50" in tt and not s.calls("pc_admin_sell") and len(s.dialogs) == n0, (tt, s.calls("pc_admin_sell"), s.dialogs[n0:]))
        s.close()
        s = Site(br, html, True, dict(shop, adm=dict(ADM, lx=2), bought=[]), path="/admin")   # đã chạy SQL v50
        s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        s.page.wait_for_function("() => document.getElementById('pcs-waitbar') && !document.getElementById('pcs-waitbar').hidden", timeout=8000)
        s.page.click("#pcs-waitbar"); s.page.wait_for_timeout(600); s.page.click("#pcs-adm-set"); s.page.wait_for_timeout(300)
        st = s.js("() => ({ dis: document.getElementById('pcs-set-cachyos').disabled, need: document.getElementById('pcs-set-cy-need').hidden })")
        ck("đã chạy SQL v50 (lx 2): ô 🐧 CachyOS mở, không còn dòng nhắc", st == {"dis": False, "need": True}, st)
        s.page.check("#pcs-set-cachyos"); n0 = len(s.dialogs); s.accept = False; s.page.click("#pcs-set-save"); s.page.wait_for_timeout(400)
        ck("BẬT bán CachyOS lần đầu → hỏi (cần SQL v50 + agent 22.11f, máy UEFI tắt Secure Boot); bấm Huỷ thì không lưu",
           any("BẬT bán Linux CachyOS" in x and "SQL v50" in x and "Secure Boot" in x for x in s.dialogs[n0:]) and not s.calls("pc_admin_sell"), s.dialogs[n0:])
        s.accept = True; s.page.click("#pcs-set-save"); s.page.wait_for_timeout(500)
        ck("đồng ý → lưu có cachyos", s.calls("pc_admin_sell") and {"id": "cachyos", "name": "Linux CachyOS"} in s.calls("pc_admin_sell")[-1]["p_patch"]["os"], s.calls("pc_admin_sell"))
        s.close()
        print("6. Khách thường không thấy phần admin")
        s = Site(br, html, False, dict(shop, bought=[]))
        ck("khách: không có dải đơn chờ, không gọi pc_admin_rentals", s.js("() => !document.getElementById('pcs-waitbar') || document.getElementById('pcs-waitbar').hidden") and not s.calls("pc_admin_rentals"))
        s.close()
        print("7. Chưa đăng nhập")
        s = Site(br, html, None, dict(shop, bought=[]))
        ck("chưa đăng nhập: không gọi pc_my_vps, khung ẩn; vẫn đọc pc_shop_info", not s.calls("pc_my_vps") and s.js("() => !document.getElementById('pcs-mine') || document.getElementById('pcs-mine').hidden") and s.calls("pc_shop_info"))
        s.js("id => openBuy(id)", PROD); s.page.wait_for_timeout(400); s.page.click("#m-ok"); s.page.wait_for_timeout(400)
        ck("chưa đăng nhập bấm Thanh toán → mở hộp đăng nhập, không gọi pc_buy", s.js("() => !document.getElementById('auth').hidden") and not s.js("() => window.__SHOP.bought.length"))
        ck("không lỗi JS", not s.errors, s.errors)
        s.close()
        print("8. Đăng ký: tên / email giả danh shop (SQL v58)")
        s = Site(br, html, None, dict(shop, bought=[]))
        s.js("""() => { window.__DK = { check: 'ok', avail: true, up: [], upErr: null };
          window.__FAKE_HOOK.signup_check = a => window.__DK.check === 'CHUA_CO' ? ({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.signup_check' } }) : ({ data: window.__DK.check, error: null });
          window.__FAKE_HOOK.username_available = a => ({ data: window.__DK.avail, error: null });
          const c = window.supabase.createClient(); c.auth.signUp = a => { window.__DK.up.push(a); return Promise.resolve(window.__DK.upErr ? { data: null, error: { message: window.__DK.upErr } } : { data: { session: null }, error: null }); }; }""")
        def dang_ky(u, em):
            s.js("() => openAuth('reg')"); s.page.wait_for_timeout(200)
            s.page.fill("#rg-u", u); s.page.fill("#rg-e", em); s.page.fill("#rg-p", "MatKhau123!"); s.page.fill("#rg-p2", "MatKhau123!")
            s.page.click("#rg-btn"); s.page.wait_for_timeout(700)
            return s.js("() => document.getElementById('rg-err').textContent")
        s.js("() => { window.__DK.check = 'reserved_name'; }")
        e1 = dang_ky("CloudBlue_shop", "khach@gmail.com")
        ck("tên đăng nhập giống tên shop → báo 'trùng hoặc giống tên của shop … chọn tên khác', KHÔNG gọi đăng ký", "giống tên của shop" in e1 and "tên khác" in e1 and s.js("() => window.__DK.up.length") == 0
           and s.calls("signup_check")[-1] == {"p_username": "CloudBlue_shop", "p_email": "khach@gmail.com"}, (e1, s.calls("signup_check")[-1:]))
        s.js("() => { window.__DK.check = 'reserved_email'; }")
        e2 = dang_ky("khach_thuong", "cloudblue@gmail.com")
        ck("email giống tên shop → báo 'Email này trùng hoặc giống tên của shop … dùng email khác', KHÔNG gọi đăng ký", "Email này trùng hoặc giống tên của shop" in e2 and s.js("() => window.__DK.up.length") == 0, e2)
        s.js("() => { window.__DK.check = 'taken'; }")
        e3 = dang_ky("khach_thuong", "khach@gmail.com")
        ck("tên đã có người dùng → báo như cũ, KHÔNG gọi đăng ký", "đã có người dùng" in e3 and s.js("() => window.__DK.up.length") == 0, e3)
        s.js("() => { window.__DK.check = 'ok'; }"); n_av = len(s.calls("username_available"))
        e4 = dang_ky("khach_thuong", "khach@gmail.com")
        ck("tên + email bình thường → gọi đăng ký đúng tên + email, không báo lỗi, không cần hỏi username_available nữa", e4 == "" and s.js("() => window.__DK.up.length") == 1
           and s.js("() => window.__DK.up[0].email + '|' + window.__DK.up[0].options.data.username") == "khach@gmail.com|khach_thuong" and len(s.calls("username_available")) == n_av, (e4, s.js("() => window.__DK.up")))
        s.js("() => { window.__DK.check = 'CHUA_CO'; window.__DK.avail = false; window.__DK.up = []; }")
        e5 = dang_ky("khach_thuong", "khach@gmail.com")
        ck("web CHƯA chạy SQL v58 (chưa có hàm signup_check) → tự hỏi kiểu cũ (username_available), vẫn báo 'đã có người dùng'", "đã có người dùng" in e5 and len(s.calls("username_available")) == n_av + 1
           and s.js("() => window.__DK.up.length") == 0, e5)
        s.js("() => { window.__DK.avail = true; window.__DK.upErr = 'Database error saving new user'; }")
        e6 = dang_ky("khach_thuong", "khach@gmail.com")
        ck("máy chủ từ chối lúc tạo (app / web cũ lọt bước hỏi trước) → báo dễ hiểu 'Không tạo được tài khoản với tên đăng nhập / email này', không hiện câu tiếng Anh của máy chủ",
           "Không tạo được tài khoản với tên đăng nhập / email này" in e6 and "Database error" not in e6 and s.js("() => window.__DK.up.length") == 1, e6)
        ck("đăng ký: không lỗi JS", not s.errors, s.errors)
        s.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(1 if FAIL else 0)


def document_ok(s): return s.js("() => !window.__xss")


if __name__ == "__main__":
    main()
