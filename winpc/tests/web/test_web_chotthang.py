# -*- coding: utf-8 -*-
"""28/11 · SQL v69 — 📅 chốt doanh thu từng tháng + tiền điện / chi phí → lãi (trang admin › Tổng quan) và thẻ ĐT đám mây "Còn chỗ / Hết hàng"
   theo máy chủ (không hiện số lượng). Chrome thật (Playwright) + Supabase giả; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_chotthang.py [blueroblox-site/index.html]"""
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-chotthang"
OK = FAIL = 0

REV = {"year": 2026, "cur": "2026-11", "years": [2025, 2026], "elec_price": 2800, "watt_total": 3500,
       "months": [
           {"month": "2026-10", "rev_shop": 2040000, "rev_cp": 400000, "rev": 2440000, "kwh": 1200, "kwh_est": 2604, "kwh_auto": False, "elec_price": 2800,
            "elec_cost": 3360000, "other_cost": 500000, "cost": 3860000, "profit": -1420000, "closed": True, "note": "tiền mạng"},
           {"month": "2026-11", "rev_shop": 700000, "rev_cp": 55000, "rev": 755000, "kwh": 2271.5, "kwh_est": 2271.5, "kwh_auto": True, "elec_price": 2800,
            "elec_cost": 6360200, "other_cost": 0, "cost": 6360200, "profit": -5605200, "closed": False, "note": None}],
       "total": {"rev": 3195000, "kwh": 3471.5, "elec_cost": 9720200, "other_cost": 500000, "profit": -7025200, "closed": False, "closed_at": None}}
HOOK = """(() => {
  window.__REV = { mode: 'ok', data: %s, saves: [], sets: [] };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    admin_stats: () => ({ generated_at: '12:30 28/11/2026', revenue_total: 53000000, revenue_today: 10000, revenue_month: 700000, topup_total: 200000, balance_total: 150000,
                          customers: 3, orders_done: 9, top_products: [], cp_revenue_total: 9000000, cp_revenue_month: 55000, cp_revenue_today: 5000 }),
    admin_db_check: () => ({ v67: { change_server: true }, v68: { topups: true, rev_funcs: 9 }, v69: { month_close: true, year_close: true, costs: true, cp_no_stock: true } }),
    admin_rev_months: (a) => window.__REV.mode === 'none'
      ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.admin_rev_months(p_year) in the schema cache' } }
      : Object.assign(JSON.parse(JSON.stringify(window.__REV.data)), a && a.p_year ? { year: a.p_year } : {}),
    admin_rev_month_save: (a) => { window.__REV.saves.push(a); const d = JSON.parse(JSON.stringify(window.__REV.data));
      const m = d.months.find(x => x.month === a.p_month); if (m && 'kwh' in a.p) { m.kwh = a.p.kwh === null ? m.kwh_est : +a.p.kwh; m.kwh_auto = a.p.kwh === null; m.elec_cost = Math.round(m.kwh * 2800); }
      if (m && 'other_cost' in a.p) m.other_cost = +a.p.other_cost; if (m && 'note' in a.p) m.note = a.p.note;
      if (m) { m.cost = m.elec_cost + m.other_cost; m.profit = m.rev - m.cost; } window.__REV.data = d; return d; },
    admin_rev_settings_save: (a) => { window.__REV.sets.push(a); return JSON.parse(JSON.stringify(window.__REV.data)); },
    cloudphone_status: () => (window.__FULL ? { maint: false, online: true, free_ram: 0, free_cpu: 0, android: { '9': { free_ram: 0, free_cpu: 0, online: true } } }
                                            : { maint: false, online: true, free_ram: 80, free_cpu: 80, android: { '9': { free_ram: 80, free_cpu: 80, online: true } } }),
  }); })();""" % json.dumps(REV)


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


class Site:
    def __init__(self, browser, html, admin=True, path="/admin", full=False):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": 1500, "height": 1100}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {"product_list": [], "products": [], "cloud_phones": [], "pc_machines": [],
                                       "cloudphone_pricing": [{"id": 1, "stock": 9846, "android_versions": "9", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32,
                                                               "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}]}}
        self.ctx.add_init_script("window.__FULL = %s; window.__FAKE_INIT = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % ("true" if full else "false", json.dumps(init), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message[:200]), d.dismiss()))
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2400)

    def route(self, route):
        u = route.request.url
        if u.split("#")[0].split("?")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def shot(self, name): os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name), full_page=False)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        print("1. 📅 chốt tháng ở Tổng quan")
        s = Site(br, html)
        s.js("async () => { await loadStats(); }"); s.page.wait_for_timeout(700)
        ck("ô 1 = 'Tổng doanh thu tháng này' 755.000đ (cửa hàng + ĐT đám mây của tháng đang chạy)",
           "755.000" in (s.txt("#st-revm") or "") and "Tổng doanh thu tháng này" in (s.txt("#st-tiles") or ""), (s.txt("#st-revm"), (s.txt("#st-tiles") or "")[:200]))
        ck("ô 2 = 'Lãi tháng này (đã trừ tiền điện + chi phí)' = −5.605.200đ, màu đỏ",
           "5.605.200" in (s.txt("#st-profm") or "") and "Lãi tháng này" in (s.txt("#st-tiles") or ""), s.txt("#st-profm"))
        rows = s.js("() => [...document.querySelectorAll('#rev-tb tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")
        ck("bảng: tháng này (⏳ Đang chạy) trên cùng, tháng 10 (✅ Đã chốt), dòng 'Cả năm 2026'",
           len(rows) == 3 and rows[0].startswith("11/2026") and "Đang chạy" in rows[0] and rows[1].startswith("10/2026") and "Đã chốt" in rows[1] and rows[2].startswith("Cả năm 2026"), rows)
        ck("tháng 10: doanh thu 2.440.000 · tiền điện 3.360.000 (1.200 số × 2.800đ) · chi phí 500.000 · lãi −1.420.000",
           all(x in rows[1] for x in ("2.440.000", "3.360.000", "1.200 số × 2.800", "1.420.000")), rows[1])
        ck("tháng này: số điện để trống = số ƯỚC (ô ghi 'ước 2.271,5')",
           s.js("() => document.querySelector('[data-revm=\"2026-11\"] [data-revk=\"kwh\"]').placeholder").startswith("ước 2.271,5")
           and s.js("() => document.querySelector('[data-revm=\"2026-11\"] [data-revk=\"kwh\"]').value") == "", None)
        ck("ô giá điện = 2800 · tổng công suất = 3500", s.js("() => [document.getElementById('rev-price').value, document.getElementById('rev-watt').value]") == ["2800", "3500"])
        s.shot("1-chot-thang.png")
        s.page.fill('[data-revm="2026-11"] [data-revk="kwh"]', "1.500"); s.page.keyboard.press("Enter"); s.page.wait_for_timeout(500)
        sv = s.js("() => window.__REV.saves")
        ck("gõ số điện '1.500' (ngăn nghìn) → lưu kwh = 1500 cho tháng 2026-11 · tiền điện tính lại 4.200.000",
           sv and sv[-1] == {"p_month": "2026-11", "p": {"kwh": "1500"}} and "4.200.000" in (s.txt('[data-revm="2026-11"]') or ""), (sv, s.txt('[data-revm="2026-11"]')))
        s.page.fill('[data-revm="2026-11"] [data-revk="other_cost"]', "300.000"); s.page.keyboard.press("Enter"); s.page.wait_for_timeout(500)
        sv = s.js("() => window.__REV.saves")
        ck("gõ chi phí khác '300.000' → lưu other_cost = 300000 · lãi tháng này cập nhật ở ô 2",
           sv[-1] == {"p_month": "2026-11", "p": {"other_cost": "300000"}} and "3.745.000" in (s.txt("#st-profm") or ""), (sv[-1], s.txt("#st-profm")))
        s.page.fill('[data-revm="2026-10"] [data-revk="kwh"]', ""); s.page.keyboard.press("Enter"); s.page.wait_for_timeout(500)
        ck("xoá số điện tháng đã chốt → gửi kwh = null (về số ước)", s.js("() => window.__REV.saves")[-1] == {"p_month": "2026-10", "p": {"kwh": None}})
        s.page.fill('[data-revm="2026-10"] [data-revk="kwh"]', "-3"); s.page.keyboard.press("Enter"); s.page.wait_for_timeout(300)
        ck("số điện sai → báo lỗi, không gửi", "Số điện là số" in (s.txt("#rev-msg") or "") and len(s.js("() => window.__REV.saves")) == 3, s.txt("#rev-msg"))
        s.page.fill("#rev-price", "2.800"); s.page.fill("#rev-watt", "4000"); s.page.click("#rev-save"); s.page.wait_for_timeout(500)
        ck("lưu giá điện 2.800đ / số + công suất 4000 W → admin_rev_settings_save", s.js("() => window.__REV.sets")[-1] == {"p": {"elec_price": "2800", "watt_total": "4000"}},
           s.js("() => window.__REV.sets"))
        ck("không lỗi trang", not s.errors, s.errors)
        s.js("() => { window.__REV.mode = 'none'; }"); s.js("async () => { await revLoad(); }"); s.page.wait_for_timeout(300)
        ck("chưa chạy SQL v69 → 'Chưa chạy SQL v69 (chốt tháng)'", "Chưa chạy SQL v69" in (s.txt("#rev-tb") or ""), s.txt("#rev-tb"))
        s.ctx.close()

        print("2. thẻ ĐT đám mây: Còn chỗ / Hết hàng (không hiện số lượng)")
        s = Site(br, html, admin=False, path="/")
        s.js("async () => { await cpLoadPricing(); await cpLoadStatus(); }"); s.page.wait_for_timeout(300)
        st = s.js("() => m3CloudSt()")
        ck("máy chủ còn chỗ → 'Còn chỗ' (không còn 'Còn 9846 máy')", st == ["ok", "Còn chỗ"] and "9846" not in (s.js("() => document.body.innerText") or ""), st)
        ck("cho thuê bình thường (không chặn theo số lượng)", s.js("() => cpBlocked()") is None)
        s.ctx.close()
        s = Site(br, html, admin=False, path="/", full=True)
        s.js("async () => { await cpLoadPricing(); await cpLoadStatus(); }"); s.page.wait_for_timeout(300)
        ck("mọi máy chủ đầy → 'Hết hàng' + chặn thuê với lời nhắn rõ", s.js("() => m3CloudSt()") == ["out", "Hết hàng"] and "mọi máy chủ đang đầy" in (s.js("() => cpBlocked()") or ""),
           (s.js("() => m3CloudSt()"), s.js("() => cpBlocked()")))
        s.ctx.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt · ảnh: {SHOTS}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
