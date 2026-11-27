# -*- coding: utf-8 -*-
"""Thử 🧮 SL ẢO (SQL v66) + ✨ hiệu ứng luôn bật trên web bằng Chrome thật (Playwright) + Supabase giả.
   python3 test_web_slao.py <index.html> [thư mục ảnh chụp]
   · Quản trị › Sản phẩm: ô SL ảo chỉ hiện với hàng tự động, Sửa → điền đúng số, Lưu → admin_vstock_set (không đổi thì không gọi),
     bảng sản phẩm ghi "thật + ảo" + số đơn chờ, hộp Nhập kho báo đơn chờ và "tự giao …" sau khi nhập, bảng Đơn hàng + hộp Giao ghi đơn chờ hàng.
   · Chưa chạy SQL v66 → ô SL ảo khoá + nhắc chạy SQL, không gọi hàm.
   · Khách: mua hàng tự động lúc hết kho → hộp cảm ơn "đang chờ hàng, tự giao", báo Telegram cho admin; mục Đơn hàng ghi ⏳ Chờ hàng (tiếng Việt / Anh).
   · Hiệu ứng: điện thoại / máy yếu KHÔNG tự chuyển chế độ nhẹ nữa; khách tự bấm nút cuối trang mới tắt.
   Mọi yêu cầu mạng trả lời tại chỗ — không gọi ra ngoài."""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(NEW_HTML)), "shots")
os.makedirs(SHOTS, exist_ok=True)
ORIGIN = "https://cloudblue.test"
ME = "00000000-0000-4000-8000-000000000001"           # người đăng nhập của Supabase giả
OK = FAIL = 0
ROB, VPS = "7a7a7a7a-0000-4000-8000-000000000001", "7a7a7a7a-0000-4000-8000-000000000002"


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def iso(sec):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def read(p):
    with open(p, encoding="utf-8") as f: return f.read()


PRODUCTS = [{"id": ROB, "cat": "clone", "name": "ACCOUNT ROBLOX", "price": 500, "plans": [], "features": ["Acc mới"], "hot": True, "sort": 1, "manual": False, "stock": 57},
            {"id": VPS, "cat": "vps", "name": "VPS GPU BLUE", "price": 360000, "plans": [{"days": 7, "price": 360000}], "features": ["GPU"], "hot": False, "sort": 2,
             "manual": True, "stock": 5, "manual_stock": 5}]
ORDERS = [{"id": "o-w1", "user_id": ME, "product_id": ROB, "product_name": "ACCOUNT ROBLOX", "qty": 4, "total": 2000, "status": "pending", "days": None,
           "created_at": iso(-900), "delivered_at": None, "items": "⏳ Đang chờ hàng (đã có 1/4). Hàng về hệ thống tự giao vào đơn này — bạn không cần làm gì thêm."},
          {"id": "o-w2", "user_id": ME, "product_id": ROB, "product_name": "ACCOUNT ROBLOX", "qty": 2, "total": 1000, "status": "pending", "days": None,
           "created_at": iso(-600), "delivered_at": None, "items": "⏳ Đang chờ hàng. Hàng về hệ thống tự giao vào đơn này — bạn không cần làm gì thêm."},
          {"id": "o-vps", "user_id": ME, "product_id": VPS, "product_name": "VPS GPU BLUE · 7 ngày", "qty": 1, "total": 360000, "status": "pending", "days": 7,
           "created_at": iso(-300), "delivered_at": None, "items": "Đang chuẩn bị. Admin sẽ giao thông tin trong ít phút."},
          {"id": "o-done", "user_id": ME, "product_id": ROB, "product_name": "ACCOUNT ROBLOX", "qty": 1, "total": 500, "status": "done", "days": None,
           "created_at": iso(-86400), "delivered_at": iso(-86000), "items": "acc1|pass1"}]
VSLIST = [{"product_id": ROB, "qty": 50, "ready": 7, "waits": 2, "need": 5, "orders": [{"id": "o-w1", "need": 3}, {"id": "o-w2", "need": 2}]}]

HOOK = """window.__FAKE_HOOK = {
  admin_vstock_list: () => window.__VS.missing ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.admin_vstock_list without parameters in the schema cache' } } : JSON.parse(JSON.stringify(window.__VS.list)),
  admin_vstock_set: a => { window.__VS.set.push(a); const x = window.__VS.list.find(r => r.product_id === a.p_product); if (x) x.qty = a.p_qty; return { data: a.p_qty, error: null }; },   // số trần: Supabase giả chỉ nhận object
  admin_add_stock: a => { const n = String(a.p_lines || '').split('\\n').filter(l => l.trim()).length, x = window.__VS.list[0]; let left = n;
    while (left > 0 && x.orders.length) { const o = x.orders[0], g = Math.min(left, o.need); o.need -= g; x.need -= g; left -= g; if (!o.need) { x.orders.shift(); x.waits--; } }
    x.ready += left; return { data: n, error: null }; },
  admin_stock_by_source: () => [],
  buy_product: a => { window.__VS.bought.push(a); return window.__VS.buyRes; }
};"""


class Site:
    def __init__(self, browser, html, admin, vs, mobile=False, path="/", lang="vi", lite="1", weak=False):
        self.errors, self.notes = [], []
        vp = {"width": 390, "height": 844} if mobile else {"width": 1360, "height": 900}
        self.ctx = browser.new_context(viewport=vp, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", has_touch=mobile, is_mobile=mobile)
        init = {"admin": admin, "db": {"product_list": PRODUCTS, "products": PRODUCTS, "orders": json.loads(json.dumps(ORDERS)), "topups": []}}
        ls = "localStorage.setItem('br_lang', %s);" % json.dumps(lang) + ("localStorage.setItem('br_lite', %s);" % json.dumps(lite) if lite is not None else "localStorage.removeItem('br_lite');")
        weak_js = "Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: () => 2 }); Object.defineProperty(Navigator.prototype, 'deviceMemory', { get: () => 2 });" if weak else ""
        # localStorage chỉ đặt 1 lần cho mỗi tab (tải lại trang giữ lựa chọn khách vừa bấm)
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__VS = %s; %s %s try { if (!sessionStorage.getItem('__lsinit')) { sessionStorage.setItem('__lsinit', '1'); %s } } catch (e) {}"
                                 % (json.dumps(init), json.dumps(vs), HOOK, weak_js, ls))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.on("dialog", lambda d: d.accept())
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2600)

    def route(self, route):
        u = route.request.url
        if u.split("?")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js")))
        if "/api/notify-admin" in u: self.notes.append(route.request.post_data or ""); return route.fulfill(status=200, content_type="application/json", body="{}")
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def calls(self, name): return self.js("n => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)
    def toast(self): return self.js("() => { const t = document.getElementById('toast'); return t && !t.hidden ? t.innerText : ''; }")
    def vis(self, sel): return self.js("s => { const e = document.querySelector(s); return !!e && !e.hidden && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0; }", sel)
    def close(self): self.ctx.close()


def fresh_vs(**kw):
    v = {"list": json.loads(json.dumps(VSLIST)), "set": [], "bought": [], "missing": False,
         "buyRes": {"id": "o-new", "status": "pending", "total": 1000, "qty": 2, "product_id": ROB,
                    "items": "⏳ Đang chờ hàng (đã có 1/2). Hàng về hệ thống tự giao vào đơn này — bạn không cần làm gì thêm."}}
    v.update(kw); return v


def admin_site(br, html, vs):
    s = Site(br, html, True, vs, path="/admin")
    s.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
    s.js("() => setTab('prod')"); s.page.wait_for_timeout(600)
    return s


def main():
    html = read(NEW_HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch()

        print("1. Quản trị › Sản phẩm: bảng + ô SL ảo")
        vs = fresh_vs(); s = admin_site(br, html, vs)
        row = s.js("id => { const b = document.querySelector(`#ptbl [data-edit='${id}']`); return b ? b.closest('tr').innerText.replace(/\\s+/g, ' ') : ''; }", ROB)
        ck("bảng sản phẩm: Còn 57 · kho .txt: 7 thật + 50 ảo · ⏳ 2 đơn chờ · thiếu 5", "57" in row and "kho .txt: 7 thật + 50 ảo" in row and "2 đơn chờ · thiếu 5" in row, row)
        vrow = s.js("id => { const b = document.querySelector(`#ptbl [data-edit='${id}']`); return b ? b.closest('tr').innerText.replace(/\\s+/g, ' ') : ''; }", VPS)
        ck("hàng thủ công vẫn ghi 'số lượng', không có chữ ảo", "số lượng" in vrow and "ảo" not in vrow, vrow)
        s.js("id => document.querySelector(`#ptbl [data-edit='${id}']`).click()", ROB); s.page.wait_for_timeout(500)
        f = s.js("() => ({ vq: document.getElementById('pf-vq').value, was: document.getElementById('pf-vq').dataset.was, dis: document.getElementById('pf-vq').disabled, ms: !document.getElementById('pf-ms-wrap').hidden })")
        ck("Sửa ACCOUNT ROBLOX: ô SL ảo hiện = 50, ô 'Số lượng còn bán' (thủ công) ẩn", s.vis("#pf-vq-wrap") and f["vq"] == "50" and f["was"] == "50" and not f["dis"] and not f["ms"], f)
        s.page.screenshot(path=os.path.join(SHOTS, "slao-1-form.png"))
        s.js("() => { const m = document.getElementById('pf-mode'); m.value = 'manual'; m.dispatchEvent(new Event('change')); }")
        ck("đổi sang Thủ công → ô SL ảo ẩn, ô số lượng hiện", not s.vis("#pf-vq-wrap") and s.vis("#pf-ms-wrap"))
        s.js("() => { const m = document.getElementById('pf-mode'); m.value = 'auto'; m.dispatchEvent(new Event('change')); }")
        s.js("() => { document.getElementById('pf-vq').value = '80'; document.getElementById('pf').requestSubmit(); }"); s.page.wait_for_timeout(900)
        ck("Lưu → admin_vstock_set(ACCOUNT ROBLOX, 80) + báo 'SL ảo 80'", s.calls("admin_vstock_set") == [{"p_product": ROB, "p_qty": 80}] and "SL ảo 80" in s.toast(), (s.calls("admin_vstock_set"), s.toast()))
        s.js("id => document.querySelector(`#ptbl [data-edit='${id}']`).click()", ROB); s.page.wait_for_timeout(400)
        ck("mở lại → ô SL ảo = 80 (đọc lại từ máy chủ)", s.js("() => document.getElementById('pf-vq').value") == "80")
        s.js("() => document.getElementById('pf').requestSubmit()"); s.page.wait_for_timeout(800)
        ck("Lưu mà không đổi SL ảo → không gọi lại", len(s.calls("admin_vstock_set")) == 1, s.calls("admin_vstock_set"))
        s.js("() => resetForm()")
        ck("Thêm sản phẩm mới: ô SL ảo = 0", s.js("() => document.getElementById('pf-vq').value") == "0")

        print("2. Hộp Nhập kho + tự giao đơn chờ")
        s.js("id => document.querySelector(`#ptbl [data-stock='${id}']`).click()", ROB); s.page.wait_for_timeout(700)
        info = s.js("() => document.getElementById('sk-vs').innerText")
        ck("hộp Nhập kho ghi: kho thật 7 · SL ảo 80 · 2 đơn đang chờ hàng (thiếu 5)", s.vis("#sk-vs") and "Kho thật 7" in info and "SL ảo 80" in info and "2 đơn đang chờ hàng (thiếu 5" in info, info)
        s.page.screenshot(path=os.path.join(SHOTS, "slao-2-nhapkho.png"))
        s.js("() => { const t = document.getElementById('sk-lines'); t.value = 'a1|p1\\na2|p2\\na3|p3\\na4|p4'; t.dispatchEvent(new Event('input')); document.getElementById('sk-save').click(); }")
        s.page.wait_for_function("() => !window.skBusy && /Đã thêm/.test(document.getElementById('toast').innerText || '')", timeout=15000)
        t = s.toast()
        ck("nhập 4 → 'Đã thêm 4 tài khoản vào kho · tự giao 4 tài khoản cho đơn chờ (1 đơn đã đủ)'", "Đã thêm 4 tài khoản vào kho" in t and "tự giao 4 tài khoản cho đơn chờ (1 đơn đã đủ)" in t, t)
        ck("gọi admin_add_stock đúng 1 lần với 4 dòng", [c["p_lines"].count("\n") + 1 for c in s.calls("admin_add_stock")] == [4], s.calls("admin_add_stock"))
        row = s.js("id => { const b = document.querySelector(`#ptbl [data-edit='${id}']`); return b ? b.closest('tr').innerText.replace(/\\s+/g, ' ') : ''; }", ROB)
        ck("bảng cập nhật: còn 1 đơn chờ · thiếu 1", "1 đơn chờ · thiếu 1" in row, row)

        print("3. Bảng Đơn hàng + hộp Giao")
        s.js("() => loadAdmin()"); s.page.wait_for_timeout(900); s.js("() => setTab('ord')"); s.page.wait_for_timeout(300)
        rows = s.js("() => [...document.querySelectorAll('#otbl tr')].map(r => r.innerText.replace(/\\s+/g, ' '))")
        w2 = next((r for r in rows if "× 2" in r or "ACCOUNT ROBLOX 2" in r), "")
        ck("đơn chờ hàng ghi '⏳ Chờ hàng · thiếu 1'", any("Chờ hàng · thiếu 1" in r for r in rows), rows)
        ck("đơn VPS thủ công vẫn 'Đang chuẩn bị', đơn đã giao vẫn 'Đã giao'", any("VPS GPU BLUE" in r and "Đang chuẩn bị" in r for r in rows) and any("Đã giao" in r for r in rows), rows)
        s.js("() => document.querySelector(`#otbl [data-deliver='o-w2']`).click()"); s.page.wait_for_timeout(600)
        dl = s.js("() => document.getElementById('dl-info').innerText")
        ck("hộp Giao: nhắc đơn chờ hàng SL ảo, nhập kho là tự giao", "Đơn chờ hàng (SL ảo, còn thiếu 1)" in dl and "tự giao" in dl, dl)
        s.page.screenshot(path=os.path.join(SHOTS, "slao-3-don.png"))
        ck("không lỗi JS (admin)", not s.errors, s.errors)
        s.close()

        print("4. Chưa chạy SQL v66")
        s = admin_site(br, html, fresh_vs(missing=True))
        s.js("id => document.querySelector(`#ptbl [data-edit='${id}']`).click()", ROB); s.page.wait_for_timeout(500)
        st = s.js("() => ({ dis: document.getElementById('pf-vq').disabled, hint: document.getElementById('pf-vq-hint').innerText })")
        ck("ô SL ảo khoá + nhắc chạy SQL v66", st["dis"] and "SQL v66" in st["hint"], st)
        row = s.js("id => document.querySelector(`#ptbl [data-edit='${id}']`).closest('tr').innerText.replace(/\\s+/g, ' ')", ROB)
        ck("bảng sản phẩm như cũ (kho .txt)", "kho .txt" in row and "ảo" not in row, row)
        s.js("() => document.getElementById('pf').requestSubmit()"); s.page.wait_for_timeout(700)
        ck("Lưu sản phẩm vẫn được, không gọi admin_vstock_set", not s.calls("admin_vstock_set") and "Đã lưu" in s.toast(), (s.calls("admin_vstock_set"), s.toast()))
        ck("không lỗi JS", not s.errors, s.errors)
        s.close()

        print("5. Khách mua lúc hết kho (SL ảo)")
        vs = fresh_vs(); s = Site(br, html, False, vs)
        s.js("() => { window.__FAKE.db.profiles[0].balance = 50000; profile.balance = 50000; renderUser(); }")
        s.js("id => openBuy(id)", ROB); s.page.wait_for_timeout(400)
        s.js("() => { document.getElementById('m-qty').value = 2; document.getElementById('m-qty').dispatchEvent(new Event('input')); }")
        s.js("() => doBuy()"); s.page.wait_for_timeout(1200)
        th = s.js("() => ({ title: document.getElementById('th-title').innerText, info: document.getElementById('th-info').innerText, note: document.getElementById('th-note').innerText, dl: !document.getElementById('th-dl').hidden, ct: document.getElementById('th-contacts').innerHTML })")
        ck("gọi buy_product(ACCOUNT ROBLOX, 2)", vs and s.js("() => window.__VS.bought") == [{"p_product": ROB, "p_qty": 2, "p_days": None}], s.js("() => window.__VS.bought"))
        ck("hộp cảm ơn: 'Đặt hàng thành công!' + đang chờ hàng (đã có 1/2) + tự giao", s.vis("#thanks") and th["title"] == "Đặt hàng thành công!" and "Đang chờ hàng (đã có 1/2)" in th["info"] and "tự giao" in th["note"], th)
        ck("không có nút tải .txt, không bắt khách nhắn shop", not th["dl"] and th["ct"] == "", th)
        s.page.wait_for_timeout(400)
        ck("báo Telegram admin: Đơn chờ hàng (SL ảo) + tên hàng × 2", any("Đơn chờ hàng (SL ảo)" in n and "ACCOUNT ROBLOX × 2" in n for n in s.notes), s.notes)
        s.page.screenshot(path=os.path.join(SHOTS, "slao-4-camon.png"))
        s.js("() => { document.getElementById('th-close').click(); openOrders(); }"); s.page.wait_for_timeout(900)
        items = s.js("() => [...document.querySelectorAll('#or-list .oi')].map(e => e.innerText.replace(/\\s+/g, ' '))")
        w1 = next((x for x in items if "× 4" in x), "")
        ck("mục Đơn hàng: đơn SL ảo ghi '⏳ Chờ hàng' + đã có 1/4", "Chờ hàng" in w1 and "đã có 1/4" in w1 and "Đang chuẩn bị" not in w1, items)
        ck("đơn VPS thủ công vẫn 'Đang chuẩn bị'", any("VPS GPU BLUE" in x and "Đang chuẩn bị" in x for x in items), items)
        ck("đơn đã giao vẫn có nút tải .txt", s.js("() => !!document.querySelector(\"#or-list [data-dl='o-done']\")"))
        s.page.screenshot(path=os.path.join(SHOTS, "slao-5-donhang.png"))
        ck("không lỗi JS (khách)", not s.errors, s.errors)
        s.close()

        print("6. Tiếng Anh")
        s = Site(br, html, False, fresh_vs(), lang="en")
        s.js("() => { window.__FAKE.db.profiles[0].balance = 50000; profile.balance = 50000; renderUser(); }")
        s.js("id => openBuy(id)", ROB); s.page.wait_for_timeout(300); s.js("() => doBuy()"); s.page.wait_for_timeout(1000)
        th = s.js("() => ({ title: document.getElementById('th-title').innerText, info: document.getElementById('th-info').innerText })")
        ck("EN: 'Order placed!' + Waiting for stock (1/2 ready)", th["title"] == "Order placed!" and "Waiting for stock (1/2 ready)" in th["info"], th)
        s.js("() => { document.getElementById('th-close').click(); openOrders(); }"); s.page.wait_for_timeout(800)
        items = s.js("() => [...document.querySelectorAll('#or-list .oi')].map(e => e.innerText.replace(/\\s+/g, ' '))")
        ck("EN: đơn ghi 'Awaiting stock' + (1/4 ready)", any("Awaiting stock" in x and "1/4 ready" in x for x in items), items)
        ck("không lỗi JS", not s.errors, s.errors)
        s.close()

        print("7. Hiệu ứng luôn bật")
        m = Site(br, html, None, fresh_vs(), mobile=True, lite=None, weak=True)
        m.page.wait_for_timeout(5000)                                   # bản cũ đo khung hình 1,5 → 5 giây rồi tự chuyển chế độ nhẹ
        st = m.js("() => ({ lite: window.BR_LITE, cls: document.documentElement.classList.contains('lite'), btn: document.getElementById('fx-toggle').innerText, ls: localStorage.getItem('br_lite'), t: document.getElementById('toast').hidden ? '' : document.getElementById('toast').innerText, hw: navigator.hardwareConcurrency })")
        ck("điện thoại + máy yếu (2 nhân / 2 GB) chưa chọn gì → hiệu ứng BẬT, không tự chuyển chế độ nhẹ", st["hw"] == 2 and st["lite"] is False and not st["cls"] and "Bật" in st["btn"] and st["ls"] is None and "chế độ nhẹ" not in st["t"], st)
        m.js("() => document.getElementById('fx-toggle').click()"); m.page.wait_for_timeout(300)
        st = m.js("() => ({ lite: window.BR_LITE, cls: document.documentElement.classList.contains('lite'), btn: document.getElementById('fx-toggle').innerText, ls: localStorage.getItem('br_lite') })")
        ck("khách tự bấm → tắt hiệu ứng (chế độ nhẹ) + nhớ lựa chọn", st["lite"] is True and st["cls"] and "Tắt" in st["btn"] and st["ls"] == "1", st)
        m.page.reload(wait_until="load"); m.page.wait_for_timeout(1500)
        ck("tải lại trang → vẫn tắt theo lựa chọn của khách", m.js("() => window.BR_LITE === true && document.documentElement.classList.contains('lite')"))
        m.js("() => document.getElementById('fx-toggle').click()"); m.page.wait_for_timeout(2500)
        st = m.js("() => ({ lite: window.BR_LITE, ls: localStorage.getItem('br_lite'), btn: document.getElementById('fx-toggle').innerText })")
        ck("bấm lại → bật hiệu ứng (tải lại trang, lưu 0)", st["lite"] is False and st["ls"] == "0" and "Bật" in st["btn"], st)
        ck("không lỗi JS", not m.errors, m.errors)
        m.close()
        br.close()
    print(f"\nKẾT QUẢ: {OK} đạt / {FAIL} trượt")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
