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
            {"id": OTHER, "cat": "vps", "name": "VPS THƯỜNG", "price": 100000, "plans": [{"days": 7, "price": 100000}], "features": [], "hot": False, "sort": 2, "manual": True, "stock": 5, "manual_stock": 5}]
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
  pc_admin_deliver: a => ({ state: 'active', pc: a.p_pc, name: 'May-03', code: '', reinstall: false, order: a.p_order })
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
        ck("① Chọn Windows rồi ② Chọn thời gian thuê; gói ghi giá / ngày, gói rẻ hơn có nhãn −%",
           hz["order"] == ["pcs-hero", "pcs-os", "m-plans-box"] and hz["lab"].startswith("②") and any("50.000" in x and "/ ngày" in x and "−3%" in x for x in hz["plans"])
           and not any("−" in x for x in hz["plans"] if x.startswith("30")), hz)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-1-buy.png"))
        s.page.click('#pcs-os [data-pcsos="1511"]'); s.page.click("#m-plans button[data-d='15']"); s.page.click("#m-ok"); s.page.wait_for_timeout(700)
        b = s.js("() => window.__SHOP.bought")
        ck("bấm Thanh toán → gọi pc_buy đúng sản phẩm + 15 ngày + 1511 (không gọi buy_product)", b == [{"p_product": PROD, "p_days": 15, "p_os": "1511"}] and not s.calls("buy_product"), (b, s.calls("buy_product")))
        d = s.js("() => { const m = document.getElementById('pcsdlg'); return m && !m.hidden ? m.innerText : ''; }")
        ck("xong → hộp 'Thanh toán thành công' kiểu ĐỢI MÁY: ① Đợi máy đang cài 1511 + mã thanh toán, nút VPS của tôi",
           "Thanh toán thành công" in d and "Đợi máy" in d and "Đang cài Windows 10 Pro 1511" in d and "BR-O1" in d and "VPS của tôi" in d and document_ok(s), d)
        mg = s.js("""() => { const g = document.getElementById('pcsw-msg'); return { open: g.open, sum: g.querySelector('summary').innerText, txt: document.getElementById('pcsw-txt').textContent,
                    ct: g.querySelectorAll('.contacts a').length, copy: !!document.getElementById('pcsw-copy') }; }""")
        ck("② nội dung gửi admin: ẨN sẵn (bấm mới hiện), có đủ mã thanh toán / sản phẩm / Windows / tài khoản / lượt thuê + nút Copy",
           not mg["open"] and "Máy lâu chưa lên" in mg["sum"] and "VPS GPU LÂU CHƯA LÊN" in mg["txt"] and "Mã thanh toán: BR-O1" in mg["txt"] and "VPS GPU BLUE · 15 ngày" in mg["txt"]
           and "Windows 10 Pro 1511" in mg["txt"] and "Lượt thuê: #30" in mg["txt"] and mg["copy"], mg)
        s.page.screenshot(path=os.path.join(SHOTS, "shop-2-done.png"))
        s.js("() => { window.PCSHOP.w.t0 -= 46 * 60000; }"); s.page.wait_for_timeout(1300)
        lt = s.js("() => { const g = document.getElementById('pcsw-msg'); return { open: g.open, late: g.classList.contains('late'), note: !document.getElementById('pcsw-late').hidden, txt: document.getElementById('pcsw-txt').textContent }; }")
        ck("cài quá 45 phút → tự MỞ mục ② + nhắc gửi admin, nội dung ghi đúng trạng thái + số phút đã chờ",
           lt["open"] and lt["late"] and lt["note"] and "Trạng thái: Đang cài Windows (đã chờ 46 phút" in lt["txt"], lt)
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
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(1 if FAIL else 0)


def document_ok(s): return s.js("() => !window.__xss")


if __name__ == "__main__":
    main()
