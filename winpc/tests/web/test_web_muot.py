# -*- coding: utf-8 -*-
"""28/11g · web mượt hơn — trang quản trị không chờ nối tiếp, không vẽ thừa; viền neon chỉ chạy ở khung đang thấy.
   Chrome thật (Playwright) + Supabase giả có độ trễ (mỗi lần gọi chờ DELAY ms) → đo được truy vấn nào chạy song song.
   python3 winpc/tests/web/test_web_muot.py [blueroblox-site/index.html]"""
import datetime, json, os, re, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
DELAY = 80
OK = FAIL = 0
_A = "seq: 100, failRpc: {}, delay: 0 };"
FAKE = open(os.path.join(HERE, "fake_supabase.js"), encoding="utf-8").read()
assert _A in FAKE
FAKE = FAKE.replace(_A, "seq: 100, failRpc: {}, delay: INIT.delay || 0 }; F.calls.push = function (x) { x.t = performance.now(); return Array.prototype.push.call(this, x); };")


def iso(sec): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:700])


U = lambda i: "00000000-0000-4000-8000-%012d" % (i + 10)
DB = {
    "product_list": [{"id": "p%d" % i, "name": "Sản phẩm %d" % i, "cat": "acc", "price": 10000 + i, "stock": 5, "sort": i} for i in range(6)],
    "products": [], "settings": [{"id": 1, "data": {}}],
    "topups": [{"id": i, "user_id": U(i), "amount": 50000, "status": "done", "created_at": iso(-i * 600)} for i in range(30)],
    "orders": [{"id": "o%d" % i, "user_id": U(i), "product_id": "p1", "product_name": "Hàng %d" % i, "qty": 1, "total": 1000, "status": "done", "created_at": iso(-i * 300)} for i in range(30)],
    "vps_machines": [], "pc_machines": [{"id": "pc1", "name": "PC-1", "status": "ready", "approved": True, "created_at": iso(-3600)}],
    "cloud_phones": [{"id": "cp%03d" % i, "user_id": U(i % 300), "name": "Máy %d" % i, "status": "active", "ram": 4, "cpu": 4, "android": "12", "node_id": "n1",
                      "expires_at": iso(86400), "created_at": iso(-i * 60)} for i in range(260)],
    "cloud_nodes": [{"id": "n1", "name": "Server 1", "enabled": True, "updated_at": iso(-10), "created_at": iso(-86400), "ram_total": 64, "cpu_total": 32, "metrics": {}}],
    "cloudphone_pricing": [{"id": 1, "android_versions": "12", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32, "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}],
}
USERS = [{"id": U(i), "username": "khach%d" % i, "email": "khach%d@mail.test" % i, "role": "user", "locked": False, "balance": 1000 * i, "created_at": iso(-i * 900)} for i in range(450)]
INIT = """
window.__FAKE_INIT = %s;
(() => { const ex = %s; const t = setInterval(() => { if (window.__FAKE) { window.__FAKE.db.profiles = (window.__FAKE.db.profiles || []).concat(ex); clearInterval(t); } }, 0); })();
window.__FAKE_HOOK = {
  admin_stats: () => ({ generated_at: '17:00 28/11/2026', revenue_total: 1, revenue_today: 1, revenue_month: 1, topup_total: 1, balance_total: 1, customers: 450, orders_done: 1, top_products: [] }),
  admin_user_money: a => (a.p_ids || []).map(id => ({ id, dep: 50000, dep_manual: 0, bal: 1000, blue: 0, locked: false })),
};
try { localStorage.setItem('br_lang', 'vi'); } catch (e) {}
"""


class Site:
    def __init__(self, browser, html, path="/admin", admin=True, vw=1400, vh=1000):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": vw, "height": vh}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        self.ctx.add_init_script(INIT % (json.dumps({"admin": admin, "db": DB, "delay": DELAY}), json.dumps(USERS if admin else [])))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append(str(e).splitlines()[0][:300]))
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message[:200]), d.dismiss()))
        self.page.goto(ORIGIN + path, wait_until="load"); self.quiet()

    def route(self, r):
        u = r.request.url
        if u.split("#")[0].split("?")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return r.fulfill(status=200, content_type="application/javascript", body=FAKE)
        return r.fulfill(status=204, body="")

    def js(self, e, a=None): return self.page.evaluate(e, a)

    def quiet(self):     # chờ hết gọi mạng (không có lần gọi mới trong 3 × DELAY)
        self.js("""async D => { const F = window.__FAKE; await new Promise(res => { const chk = () => { const last = F.calls.length ? Math.max(...F.calls.map(x => x.t || 0)) : 0;
          if (performance.now() - last > D * 3 + 250) return res(); setTimeout(chk, 40); }; setTimeout(chk, 40); }); }""", DELAY)

    def mark(self): return self.js("() => window.__FAKE.calls.length")
    def calls(self, n0): return self.js("n => window.__FAKE.calls.slice(n).map(x => ({ k: x.kind === 'rpc' ? x.name : 'from:' + x.table, t: x.t, cols: x.cols || '', eq: x.eq || [] }))", n0)

    def open_tab(self, tab):
        self.js("""t => { const b = document.querySelector(`#adm-tabs button[data-tab='${t}']`); if (b && !b.offsetParent) for (const g of document.querySelectorAll('#adm-grp button[data-grp]')) { g.click(); if (b.offsetParent) break; } }""", tab)
        self.quiet()
        n0 = self.mark(); self.page.click("#adm-tabs button[data-tab='%s']" % tab); self.quiet(); return n0


def same_round(cs, keys):     # mọi truy vấn trong keys bắt đầu trong cùng 1 lượt (cách lần gọi đầu < DELAY/2)
    ts = [c["t"] for c in cs if c["k"] in keys]
    return len(ts) >= len(keys) and max(ts) - min(ts) < DELAY / 2, [(c["k"], round(c["t"] - min(ts))) for c in cs if c["k"] in keys]


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None, args=["--no-sandbox"])
        print("1. định dạng tiền giữ nguyên chữ (bộ định dạng tạo 1 lần)")
        s = Site(br, html)
        bad = s.js("""() => { const vals = [0, 1, -1, 999, 1000, 1234567, -5000, 99999.5, 12.49, 2800000000, NaN, -0.4]; for (let i = 0; i < 200; i++) vals.push(Math.random() * 1e9 - 5e8);
          return vals.filter(v => vnd(v) !== Math.round(+v || 0).toLocaleString('vi-VN') + 'đ').map(v => [v, vnd(v)]); }""")
        ck("vnd() ra đúng như toLocaleString('vi-VN') cho 212 giá trị (cả số âm, lẻ, NaN)", bad == [], bad)
        ck("vnd(1234567) = 1.234.567đ", s.js("() => vnd(1234567)") == "1.234.567đ", s.js("() => vnd(1234567)"))

        print("2. mở /admin: Tổng quan tải 1 lần, 5 truy vấn của bảng quản trị gửi cùng lúc")
        cs = s.calls(0)
        ck("admin_stats chỉ gọi 1 lần (trước: 2 lần — ô số liệu về 'Đang tải…' rồi tải lại)", sum(c["k"] == "admin_stats" for c in cs) == 1, [c["k"] for c in cs if c["k"] == "admin_stats"])
        pu = [c for c in cs if c["k"] == "from:profiles" and "*" in c["cols"]]
        t0 = pu[-1]["t"] if pu else None
        grp = [c for c in cs if t0 is not None and c["k"] in ("from:topups", "from:orders", "from:vps_machines") and abs(c["t"] - t0) < DELAY / 2]
        ck("khách · nạp tiền · đơn hàng · đơn chờ · máy VPS gửi cùng lượt (trước: chờ danh sách khách + vẽ bảng xong mới gửi)", t0 is not None and len(grp) >= 4,
           [(c["k"], round(c["t"] - (t0 or 0))) for c in cs if c["k"] in ("from:profiles", "from:topups", "from:orders", "from:vps_machines")])
        st = [c for c in cs if c["k"] in ("admin_stats", "admin_db_check", "from:cp_sales")]
        ck("Tổng quan: admin_stats · 🧩 kiểm SQL · lịch sử thuê gửi cùng lượt", len(st) >= 3 and max(c["t"] for c in st) - min(c["t"] for c in st) < DELAY / 2, [(c["k"], round(c["t"])) for c in st])

        print("3. bảng khách: chỉ vẽ khi mở thẻ 👥, mỗi lần 200 dòng")
        ck("đang ở Tổng quan: bảng khách CHƯA vẽ (0 dòng) nhưng ô 'Khách đã đăng ký' đã có số 450",
           s.js("() => document.querySelectorAll('#ctbl tr').length") == 0 and s.js("() => document.getElementById('k-users').textContent") == "450",
           [s.js("() => document.querySelectorAll('#ctbl tr').length"), s.js("() => document.getElementById('k-users').textContent")])
        s.open_tab("cust"); s.page.wait_for_timeout(200)
        n = s.js("() => document.querySelectorAll('#ctbl tr').length"); more = s.js("() => (document.querySelector('#ctbl [data-custmore]') || {}).textContent || ''")
        ck("mở 👥 Khách hàng → 200 dòng + nút 'Hiện thêm khách · đang hiện 200/451'", n == 201 and "200/451" in more, (n, more))
        s.page.click("#ctbl [data-custmore]"); s.page.wait_for_timeout(150)
        n = s.js("() => document.querySelectorAll('#ctbl tr').length"); more = s.js("() => (document.querySelector('#ctbl [data-custmore]') || {}).textContent || ''")
        ck("bấm 'Hiện thêm' → 400 dòng (400/451)", n == 401 and "400/451" in more, (n, more))
        s.js("() => { ADM.users.push({ id: 'x-noemail', username: 'khach44-thieu-email', role: 'user', created_at: new Date().toISOString() }, { id: 'x-noname', email: 'khach44@noname.test', role: 'user', created_at: new Date().toISOString() }); }")
        s.page.fill("#cq", "khach44"); s.page.wait_for_timeout(150)
        rows = s.js("() => [...document.querySelectorAll('#ctbl tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")
        ck("tìm 'khach44' → chỉ khách khớp (khach44, khach440…449 + 2 tài khoản thiếu email/tên), không còn nút Hiện thêm",
           len(rows) == 13 and all("khach44" in r for r in rows) and not any("Hiện thêm" in r for r in rows), [r[:60] for r in rows[:14]])
        ck("nút Cộng/trừ · 🔍 · Chi tiết vẫn có ở từng dòng", s.js("() => !!document.querySelector('#ctbl [data-adj]') && !!document.querySelector('#ctbl [data-sa=audit]') && !!document.querySelector('#ctbl [data-cust]')"))

        print("4. 💻 Máy PC: 3 truy vấn phụ gửi cùng lượt với truy vấn chính")
        n0 = s.open_tab("pc"); cs = s.calls(n0)
        pm = [c for c in cs if c["k"] == "from:pc_machines"]
        ts = [c["t"] for c in pm]
        ck("pc_machines (chính · v44 · v53 · v56) + pc_settings + pc_orders cùng 1 lượt (trước: 4 lượt nối tiếp)",
           len(pm) >= 4 and max(ts) - min(ts) < DELAY / 2, [(c["cols"][:30], round(c["t"] - min(ts))) for c in pm])

        print("5. 📱 ĐT đám mây: danh sách máy + máy chủ cùng lượt; tiền nạp điền vào ô, không vẽ lại cả bảng")
        # mở 💻 Máy PC ở trên đã tự mở 📱 trước (thẻ đầu của nhóm) → tiền nạp đã có; xoá để đo lại lần tải tiền
        s.js("() => { CPA_M.clear(); window.__rc = 0; const o = renderCpaTbl; renderCpaTbl = function () { window.__rc++; return o.apply(this, arguments); }; }")
        n0 = s.open_tab("cloud"); cs = s.calls(n0)
        ok, info = same_round(cs, ("from:cloud_phones", "from:cloudphone_pricing", "from:cloud_nodes"))
        ck("cloud_phones · bảng giá · cloud_nodes gửi cùng lượt (trước: 3 lượt)", ok, info)
        ck("tiền nạp của khách đã hiện trong bảng máy (💰 Nạp …)", s.js("() => document.querySelectorAll('#cpa-tbl .cpa-m').length") > 50, s.js("() => document.querySelectorAll('#cpa-tbl .cpa-m').length"))
        ck("bảng máy chỉ vẽ 1 lần khi mở (trước: vẽ lại cả bảng khi có tiền nạp)", s.js("() => window.__rc") == 1, s.js("() => window.__rc"))
        mo = [c for c in cs if c["k"] == "admin_user_money"]
        ck("admin_user_money: 2 lô (300 khách) gửi cùng lúc", len(mo) == 2 and abs(mo[0]["t"] - mo[1]["t"]) < DELAY / 2, [round(c["t"]) for c in mo])
        ck("trang quản trị không lỗi", not [e for e in s.errors if "reading 'cfg'" not in e], s.errors)
        s.ctx.close()

        print("6. viền neon: chỉ chạy ở khung đang thấy, tạm dừng lúc cuộn")
        s = Site(br, html, path="/", admin=None, vw=412, vh=800)
        s.js("() => document.querySelector('.m3-row').scrollIntoView({ block: 'center' })"); s.page.wait_for_timeout(700)
        a1 = s.js("() => getComputedStyle(document.querySelector('.m3-row'), '::after').getPropertyValue('--nr')"); s.page.wait_for_timeout(600)
        a2 = s.js("() => getComputedStyle(document.querySelector('.m3-row'), '::after').getPropertyValue('--nr')")
        ck("khung đang thấy: vệt neon chạy (góc --nr đổi)", a1 != a2, (a1, a2))
        s.js("() => window.scrollTo(0, 0)"); s.page.wait_for_timeout(700)
        far = s.js("""() => { const rs = [...document.querySelectorAll('.m3-row,.m3-sub')].filter(r => r.getBoundingClientRect().top > innerHeight * 1.8); return rs.length ? rs.map(r => r.classList.contains('nr-off')) : null; }""")
        ck("khung còn xa màn hình (> 1,8 màn): vệt neon đứng yên (nr-off)", far is None or all(far), far)
        sc = s.js("""async () => { window.scrollBy(0, 300); await new Promise(r => setTimeout(r, 40)); const on = document.documentElement.classList.contains('nr-scroll');
          await new Promise(r => setTimeout(r, 450)); return [on, document.documentElement.classList.contains('nr-scroll')]; }""")
        ck("đang cuộn → html.nr-scroll (neon tạm dừng); cuộn xong ~0,2 giây → bỏ", sc == [True, False], sc)
        ck("trang chủ không lỗi", not [e for e in s.errors if "reading 'cfg'" not in e], s.errors)
        s.ctx.close(); br.close()
    print("%d/%d đạt" % (OK, OK + FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
