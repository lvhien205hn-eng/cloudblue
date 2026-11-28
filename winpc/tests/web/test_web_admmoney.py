# -*- coding: utf-8 -*-
"""28/11 · SQL v68 — tiền của tài khoản admin (nạp thử / mua thử / tự cộng) không tính ở trang admin + 🧩 dòng "Cơ sở dữ liệu" (admin_db_check):
   Tổng quan: SQL 67 ✓ · SQL 68 ✓ / ✗ thiếu phần nào / chưa chạy v68 · Khách & tiền: 3 ô số liệu không tính tài khoản admin ·
   Lệnh nạp: lệnh của admin ghi "🧪 admin thử". Chrome thật (Playwright) + Supabase giả; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_admmoney.py [blueroblox-site/index.html]"""
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-admmoney"
ADMIN = "00000000-0000-4000-8000-000000000001"
CUS = "00000000-0000-4000-8000-0000000000c1"
OK = FAIL = 0

ALL_OK = {"v67": {"avoid_node": True, "change_server": True, "switch_other_server": True, "switch_limit": 3, "orders_cp_sales": True},
          "v68": {"topups": True, "balances": True, "rev_funcs": 9, "stats_api": True, "fresh": True, "views": ["orders", "topups"]}}
HOOK = """(() => {
  window.__DBC = { mode: 'ok', data: %s };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    admin_stats: () => ({ generated_at: '12:00 28/11/2026', revenue_total: 70000, revenue_today: 0, revenue_month: 70000, topup_total: 200000, balance_total: 150000,
                          customers: 1, orders_done: 1, top_products: [], cp_revenue_total: 0, cp_revenue_month: 0, cp_revenue_today: 0 }),
    admin_db_check: () => window.__DBC.mode === 'none'
      ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.admin_db_check without parameters in the schema cache' } }
      : JSON.parse(JSON.stringify(window.__DBC.data)),
  }); })();""" % json.dumps(ALL_OK)


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


class Site:
    def __init__(self, browser, html):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": True, "db": {"product_list": [], "products": [], "cloud_phones": [], "pc_machines": [],
                                      "topups": [{"id": 3, "user_id": ADMIN, "amount": 20000000, "status": "done", "memo": "NAPTHU", "created_at": "2026-11-28T03:00:00Z"},
                                                 {"id": 2, "user_id": CUS, "amount": 200000, "status": "done", "memo": "NAPKHACH", "created_at": "2026-11-28T02:00:00Z"},
                                                 {"id": 1, "user_id": CUS, "amount": 30000, "status": "pending", "memo": "CHO", "created_at": "2026-11-28T01:00:00Z"}]}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message[:200]), d.dismiss()))
        self.page.goto(ORIGIN + "/admin", wait_until="load")
        self.page.wait_for_timeout(2200)

    def route(self, route):
        u = route.request.url
        if u.split("#")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def shot(self, name): os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name))
    def stats(self):
        self.js("async () => { await loadStats(); }"); self.page.wait_for_timeout(500)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        s = Site(br, html)
        print("1. 🧩 dòng Cơ sở dữ liệu ở Tổng quan")
        s.stats()
        ck("đủ hết → 'SQL 67 ✓ · SQL 68 ✓'", "SQL 67 ✓" in (s.txt("#st-db") or "") and "SQL 68 ✓" in (s.txt("#st-db") or "")
           and s.js("() => document.getElementById('st-db').dataset.ok") == "1", s.txt("#st-db"))
        ck("dòng cập nhật ghi 'không tính tiền của tài khoản admin (nạp / mua / cộng thử)'", "không tính tiền của tài khoản admin" in (s.txt("#st-time") or ""), s.txt("#st-time"))
        s.shot("1-tong-quan.png")
        s.js("() => { window.__DBC.data.v67.change_server = false; window.__DBC.data.v67.switch_other_server = false; window.__DBC.data.v68.fresh = false; }")
        s.stats()
        t = s.txt("#st-db") or ""
        ck("thiếu phần nào ghi rõ phần đó: 'SQL 67 ✗ thiếu: đổi máy chủ giữ Android, đổi Android sang máy chủ khác' + cách làm mới nadm",
           "SQL 67 ✗" in t and "đổi máy chủ giữ Android" in t and "đổi Android sang máy chủ khác" in t and "_nadm_refresh" in t
           and s.js("() => document.getElementById('st-db').dataset.ok") == "0", t)
        s.js("() => { window.__DBC.mode = 'none'; }"); s.stats()
        ck("chưa có hàm kiểm tra → 'chưa chạy SQL v68'", "chưa chạy SQL v68" in (s.txt("#st-db") or ""), s.txt("#st-db"))
        ck("không lỗi trang", not s.errors, s.errors)

        print("2. Khách & tiền · Lệnh nạp: không tính tiền / tài khoản admin")
        s.js("""async () => { const F = window.__FAKE; F.db.profiles[0].balance = 900000000;
                 F.db.profiles.push({ id: '%s', username: 'khach1', email: 'k1@test', role: 'user', locked: false, balance: 150000, created_at: new Date().toISOString() });
                 await loadAdmin(); }""" % CUS)
        s.page.wait_for_timeout(600)
        s.js("() => document.querySelector('#adm-tabs button[data-tab=\"cust\"]').click()"); s.page.wait_for_timeout(400)
        ck("ô 'Khách đã đăng ký' = 1 (không tính admin)", s.txt("#k-users") == "1", s.txt("#k-users"))
        ck("ô 'Tổng số dư khách' = 150.000đ (số dư 900 triệu tự cộng của admin không tính)", "150.000" in (s.txt("#k-bal") or "") and "900" not in (s.txt("#k-bal") or ""), s.txt("#k-bal"))
        ck("ô 'Đã nạp' = 200.000đ (lệnh nạp thử 20 triệu của admin + lệnh đang chờ không tính)", "200.000" in (s.txt("#k-rev") or "") and "20.200" not in (s.txt("#k-rev") or ""), s.txt("#k-rev"))
        s.shot("2-khach-tien.png")
        s.js("() => document.querySelector('#adm-tabs button[data-tab=\"tx\"]').click()"); s.page.wait_for_timeout(400)
        rows = s.js("() => [...document.querySelectorAll('#ttbl tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")
        ck("lệnh nạp của admin ghi '🧪 admin thử', lệnh của khách thì không",
           any("NAPTHU" in r and "🧪 admin thử" in r for r in rows) and not any("NAPKHACH" in r and "🧪" in r for r in rows), rows)
        s.shot("3-lenh-nap.png")
        s.js("""async () => { window.__FAKE_HOOK.admin_topup_search = () => ({ n: 3, sum_done: 20200000, rows: [
                   { id: 3, user_id: '%s', username: 'chushop', amount: 20000000, status: 'done', via: 'manual', memo: 'NAPTHU', created_at: '2026-11-28T03:00:00Z' },
                   { id: 2, user_id: '%s', username: 'khach1', amount: 200000, status: 'done', via: 'sepay', memo: 'NAPKHACH', created_at: '2026-11-28T02:00:00Z' },
                   { id: 1, user_id: '%s', username: 'khach1', amount: 30000, status: 'pending', memo: 'CHO', created_at: '2026-11-28T01:00:00Z' }] });
                 await txLoad(); }""" % (ADMIN, CUS, CUS))
        s.page.wait_for_timeout(400)
        t = s.txt("#tx-sum") or ""
        ck("tìm lệnh nạp (v29): tổng 'đã cộng' = 200.000đ, ghi rõ 'đã bỏ 20.000.000đ admin nạp thử'", "đã cộng 200.000" in t and "đã bỏ 20.000.000" in t, t)
        rows = s.js("() => [...document.querySelectorAll('#ttbl tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")
        ck("bảng tìm kiếm vẫn hiện đủ lệnh (cả lệnh admin, có nhãn 🧪)", len(rows) == 3 and any("NAPTHU" in r and "🧪" in r for r in rows), rows)
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt · ảnh: {SHOTS}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
