# -*- coding: utf-8 -*-
"""28/11f · SQL v71 — trang admin › Tổng quan chia nhóm (💰 Tiền · 📊 doanh thu theo dịch vụ · 📱 ĐT đám mây · 🖥 VPS · 🛒 Cửa hàng)
   + bảng thuê mới / gia hạn / nâng cấp / hoàn tiền từng dịch vụ (admin_rev_services) + từng lần khách trả tiền (admin_rev_list)
   + 🧹 sổ tự dọn máy (admin_clean_log · Dọn ngay · số ngày không mở) + thẻ máy chủ báo đồng hồ lệch / Windows không WGC / điểm lag
   + thẻ máy của khách báo trước khi máy lâu không mở bị xoá + 🧩 nhãn SQL v71. Chrome thật (Playwright) + Supabase giả; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_tongquan.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-tongquan"
ME = "00000000-0000-4000-8000-000000000001"
OK = FAIL = 0


def iso(sec): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


R = lambda p, svc, kind, n, amt: {"p": p, "svc": svc, "kind": kind, "n": n, "amt": amt}
SVC = {"ok": True, "at": iso(0), "rows": [
    R("month", "cp", "new", 3, 90000), R("month", "cp", "renew", 2, 60000), R("month", "cp", "upgrade", 1, 15000), R("month", "cp", "refund", 1, -30000),
    R("month", "real", "renew", 1, 42000), R("month", "pc", "renew", 1, 360000), R("month", "vm", "new", 1, 64000), R("month", "shop", "new", 4, 120000),
    R("prev", "cp", "renew", 5, 250000), R("prev", "pc", "new", 2, 720000),
    R("today", "cp", "renew", 1, 30000)]}
LIST = [{"at": iso(-600 - i * 60), "svc": "pc" if i % 3 == 0 else "cp", "kind": "renew", "amt": 360000 if i % 3 == 0 else 30000, "item": "VPS-GPU-0%d" % i if i % 3 == 0 else "Máy %d" % i,
         "days": 7, "user": "khach%d" % i, "ref": str(i)} for i in range(40)]
CLEAN = {"rows": [{"id": 3, "at": iso(-300), "kind": "switch_stuck", "phone_id": "p1", "node": "n1", "name": "Máy farm 1", "info": "quá 60 phút → huỷ lệnh, chờ khách bấm Thử lại", "username": "khach1"},
                  {"id": 2, "at": iso(-900), "kind": "expired", "phone_id": "p2", "node": "n1", "name": "Máy cũ", "info": "hết hạn 26/11 10:00", "username": "khach2"},
                  {"id": 1, "at": iso(-1800), "kind": "idle_purge", "phone_id": "p3", "node": "n2", "name": "Máy bỏ quên", "info": "8 ngày không mở máy", "username": "khach3"}],
         "day": {"switch_stuck": 1, "expired": 1, "idle_purge": 1}, "idle_days": 8, "cron": True}
NODES = [{"id": "n1", "name": "Máy chủ 8", "enabled": True, "updated_at": iso(-20), "created_at": iso(-86400 * 30), "ram_total": 64, "cpu_total": 16, "alloc_ram": 20, "alloc_cpu": 10,
          "cap_ram": 60, "cap_cpu": 30, "phones": 5, "limit_pct": 85,
          "metrics": {"cpu_pct": 40, "ram_used": 30, "clock_off_s": 185, "win_build": 10586, "lag_pen": 25, "gpus": []}},
         {"id": "n2", "name": "Máy chủ 2", "enabled": True, "updated_at": iso(-15), "created_at": iso(-86400 * 30), "ram_total": 128, "cpu_total": 32, "alloc_ram": 40, "alloc_cpu": 20,
          "cap_ram": 120, "cap_cpu": 60, "phones": 9, "limit_pct": 85,
          "metrics": {"cpu_pct": 20, "ram_used": 50, "clock_skew_s": 4, "win_build": 19045, "lag_pen": 0, "gpus": []}}]
HOOK = """(() => {
  window.__TQ = { svc: %s, list: %s, clean: %s, mode: 'ok', lists: [], cleaned: 0, db: 'ok' };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    admin_stats: () => ({ generated_at: '15:30 28/11/2026', revenue_total: 5300000, revenue_today: 10000, revenue_month: 700000, topup_total: 2000000, balance_total: 150000,
                          customers: 31, orders_done: 9, top_products: [], cp_revenue_total: 9000000, cp_revenue_month: 135000, cp_revenue_today: 30000, cp_active: 12, cp_expiring: 2,
                          cp_new: 40, cp_renews: 25, cp_upgrades: 3, cp_switches: 7, ref_paid_total: 12000, vps_orders: 5, vps_revenue: 1800000, vps_active: 2, vps_expiring: 1, vps_expired: 0,
                          clone_qty: 14, clone_revenue: 140000 }),
    admin_db_check: () => window.__TQ.db === 'bad'
      ? { v68: { topups: true, rev_funcs: 9 }, v71: { auto_clean: true, auto_clean_cron: false, node_clock: true, rev_services: true, idle_purge: false, idle_days: 8, real_like_cp: true } }
      : { v68: { topups: true, rev_funcs: 9 }, v71: { auto_clean: true, auto_clean_cron: false, node_clock: true, rev_services: true, idle_purge: true, idle_days: 8, real_like_cp: null } },
    admin_rev_months: () => ({ year: 2026, cur: '2026-11', years: [2026], elec_price: 2800, watt_total: 0, months: [], total: { rev: 0, kwh: 0, elec_cost: 0, other_cost: 0, profit: 0 } }),
    admin_rev_services: () => window.__TQ.mode === 'none' ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.admin_rev_services without parameters in the schema cache' } }
                                                         : JSON.parse(JSON.stringify(window.__TQ.svc)),
    admin_rev_list: (a) => { window.__TQ.lists.push(a); if (a.p_kind === 'new') return [];
      return window.__TQ.list.filter(x => (!a.p_svc || x.svc === a.p_svc) && (!a.p_before || x.at < a.p_before)).slice(0, a.p_limit || 50); },
    admin_clean_log: () => JSON.parse(JSON.stringify(window.__TQ.clean)),
    admin_auto_clean: () => { window.__TQ.cleaned++; return { total: 2, switch_cancelled: 1, expired: 1 }; },
    cloudphone_status: () => ({ maint: false, online: true, free_ram: 80, free_cpu: 80, android: { '12': { free_ram: 40, free_cpu: 40, online: true } } }),
  }); })();""" % (json.dumps(SVC), json.dumps(LIST), json.dumps(CLEAN))


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


class Site:
    def __init__(self, browser, html, admin=True, path="/admin", phones=None, settings=None, nodes=None, mode="ok"):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": 1500, "height": 1100}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        db = {"product_list": [], "products": [], "cloud_phones": phones or [], "pc_machines": [], "cloud_nodes": nodes or [],
              "cloudphone_pricing": [{"id": 1, "android_versions": "12", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32,
                                      "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}]}
        if settings is not None: db["settings"] = [{"id": 1, "data": settings}]
        init = {"admin": admin, "db": db}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; %s window.__TQ.mode = %s; try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), HOOK, json.dumps(mode)))
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
    def row(self, svc): return self.js("s => { const r = document.querySelector(`#rsv-tb tr[data-rsvsvc='${s}']`); return r ? [...r.cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim()) : null; }", svc)
    def shot(self, name, full=False): os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name), full_page=full)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        print("1. Tổng quan chia nhóm")
        s = Site(br, html)
        s.js("async () => { await loadStats(); }"); s.page.wait_for_timeout(900)
        heads = s.js("() => [...document.querySelectorAll('#pane-stats .stg h4')].map(h => h.textContent)")
        ck("4 nhóm: 💰 Tiền · 📱 ĐT đám mây · 🖥 VPS · 🛒 Cửa hàng · khách", heads == ["💰 Tiền", "📱 ĐT đám mây", "🖥 VPS", "🛒 Cửa hàng · khách"], heads)
        money = s.txt("#st-tiles") or ""
        ck("nhóm Tiền: doanh thu tháng này · lãi · hôm nay · khách đã nạp · số dư khách · hoa hồng",
           all(x in money for x in ("Tổng doanh thu tháng này", "Lãi tháng này", "Doanh thu hôm nay", "Tổng khách đã nạp", "Số dư khách", "Hoa hồng")), money[:300])
        ck("nhóm ĐT đám mây / VPS / Cửa hàng có đủ ô (7 · 5 · 6)", s.js("() => ['st-cp','st-vps','st-shop'].map(i => document.getElementById(i).children.length)") == [7, 5, 6],
           s.js("() => ['st-cp','st-vps','st-shop'].map(i => document.getElementById(i).children.length)"))
        print("2. 📊 doanh thu theo dịch vụ (tháng này)")
        cp = s.row("cp")
        ck("ĐT đám mây: thuê mới 90.000 (3 lượt) · gia hạn 60.000 (2 lượt) · nâng cấp 15.000 · hoàn tiền −30.000 · tổng 135.000",
           cp and "90.000" in cp[1] and "3 lượt" in cp[1] and "60.000" in cp[2] and "2 lượt" in cp[2] and "15.000" in cp[3] and "30.000" in cp[4] and "135.000" in cp[5], cp)
        ck("có dòng 📲 Máy thật (gia hạn 42.000) · 🖥 VPS GPU (gia hạn 360.000) · ⚡ VPS NVMe (thuê mới 64.000) · 🛒 Cửa hàng (thuê mới 120.000)",
           "42.000" in (s.row("real") or ["", "", ""])[2] and "360.000" in (s.row("pc") or ["", "", ""])[2] and "64.000" in (s.row("vm") or ["", ""])[1]
           and "120.000" in (s.row("shop") or ["", ""])[1], [s.row("real"), s.row("pc"), s.row("vm"), s.row("shop")])
        ck("không có dòng VPS khác (không có tiền)", s.row("vps") is None)
        tot = s.js("() => [...document.querySelector('#rsv-tb tr.rev-tot').cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim())")
        ck("dòng Tổng: gia hạn 462.000 (4 lượt) · tổng 721.000", "462.000" in tot[2] and "4 lượt" in tot[2] and "721.000" in tot[5], tot)
        s.shot("1-tong-quan.png")
        s.page.click('[data-rsvp="prev"]'); s.page.wait_for_timeout(300)
        ck("bấm 'Tháng trước' → ĐT đám mây gia hạn 250.000 (5 lượt) · VPS GPU thuê mới 720.000", "250.000" in s.row("cp")[2] and "720.000" in s.row("pc")[1], [s.row("cp"), s.row("pc")])
        s.page.click('[data-rsvp="today"]'); s.page.wait_for_timeout(300)
        ck("bấm 'Hôm nay' → chỉ ĐT đám mây gia hạn 30.000", "30.000" in s.row("cp")[2] and "—" in s.row("pc")[1], [s.row("cp"), s.row("pc")])
        print("3. 🧾 từng lần khách trả tiền")
        ls = s.js("() => window.__TQ.lists")
        ck("mặc định xem 🔁 Gia hạn mọi dịch vụ: admin_rev_list(p_kind renew, p_limit 40)", ls and ls[0] == {"p_svc": None, "p_kind": "renew", "p_limit": 40}, ls)
        rl = s.txt("#rsl-tb") or ""
        ck("bảng có khách, máy, số ngày, tiền (khach0 · VPS-GPU-00 · 360.000)", "khach0" in rl and "VPS-GPU-00" in rl and "360.000" in rl and "🔁 Gia hạn" in rl, rl[:300])
        ck("đủ 40 dòng → có nút Xem thêm", s.js("() => !document.getElementById('rsl-more').hidden") and s.js("() => document.querySelectorAll('#rsl-tb tr').length") == 40)
        s.page.click('#rsv-tb tr[data-rsvsvc="pc"]'); s.page.wait_for_timeout(500)
        ck("bấm dòng 🖥 VPS GPU ở bảng trên → chỉ xem VPS GPU (p_svc pc) · dòng được tô", s.js("() => window.__TQ.lists").pop() == {"p_svc": "pc", "p_kind": "renew", "p_limit": 40}
           and s.js("() => document.querySelector('#rsv-tb tr[data-rsvsvc=\"pc\"]').classList.contains('on')") and "khach3" in (s.txt("#rsl-tb") or "") and "Máy 1" not in (s.txt("#rsl-tb") or ""),
           s.js("() => window.__TQ.lists").pop())
        ck("ô Dịch vụ tự chọn 'VPS GPU'", s.js("() => document.getElementById('rsl-svc').value") == "pc")
        s.page.click('[data-rslk="new"]'); s.page.wait_for_timeout(500)
        ck("bấm 🆕 Thuê mới → p_kind new · chưa có thì ghi rõ", s.js("() => window.__TQ.lists").pop() == {"p_svc": "pc", "p_kind": "new", "p_limit": 40}
           and "Chưa có lần trả tiền nào loại này ở 🖥 VPS GPU" in (s.txt("#rsl-tb") or ""), s.txt("#rsl-tb"))
        s.page.click('#rsv-tb tr[data-rsvsvc="pc"]'); s.page.click('[data-rslk="renew"]'); s.page.wait_for_timeout(600)
        s.page.click("#rsl-more"); s.page.wait_for_timeout(600)
        last = s.js("() => window.__TQ.lists").pop()
        ck("Xem thêm → hỏi tiếp từ dòng cuối (p_before)", last.get("p_kind") == "renew" and last.get("p_svc") is None and last.get("p_before") == LIST[39]["at"], last)
        ck("không lỗi trang", not s.errors, s.errors)
        s.shot("2-tung-lan.png", True)
        print("4. 🧩 nhãn SQL v71")
        ck("không có pg_cron vẫn ✓ (máy chủ tự gọi dọn) + ghi chú", "SQL 71 ✓" in (s.txt("#st-db") or "") and "máy chủ tự gọi" in (s.txt("#st-db") or ""), s.txt("#st-db"))
        s.js("async () => { window.__TQ.db = 'bad'; await dbCheck(); }"); s.page.wait_for_timeout(300)
        ck("thiếu phần xoá máy lâu không mở → 'SQL 71 ✗ thiếu: xoá máy không mở'", "SQL 71 ✗" in (s.txt("#st-db") or "") and "xoá máy không mở" in (s.txt("#st-db") or ""), s.txt("#st-db"))
        s.ctx.close()
        s = Site(br, html, mode="none")
        s.js("async () => { await loadStats(); }"); s.page.wait_for_timeout(700)
        ck("chưa chạy SQL v71 → bảng ghi 'Chưa chạy SQL v71', không lỗi", "Chưa chạy SQL v71" in (s.txt("#rsv-tb") or "") and not s.errors, (s.txt("#rsv-tb"), s.errors))
        s.ctx.close()

        print("5. 🧹 sổ tự dọn máy + số ngày không mở")
        s = Site(br, html, nodes=NODES)
        s.js("async () => { setTab('cloud'); await new Promise(r => setTimeout(r, 300)); subShow('cloud', 'tools'); }"); s.page.wait_for_timeout(1200)
        msg = s.txt("#cln-msg") or ""
        ck("mở mục Công cụ → tự đọc sổ dọn: '✅ Cơ sở dữ liệu tự dọn 5 phút / lần · 24 giờ qua dọn 3 máy'", "tự dọn 5 phút / lần" in msg and "dọn 3 máy" in msg and "8 ngày" in msg, msg)
        tb = s.txt("#cln-tb") or ""
        ck("bảng sổ dọn: đổi Android quá lâu → huỷ lệnh · hết hạn → xoá · lâu không mở → xoá vĩnh viễn (khách, máy chủ)",
           all(x in tb for x in ("Đổi Android quá lâu", "Hết hạn quá 1 ngày", "Lâu không mở", "khach1", "Máy farm 1")), tb[:400])
        ck("ô số ngày không mở = 8 (mặc định)", s.js("() => document.getElementById('cln-days').value") == "8")
        s.page.click("#cln-go"); s.page.wait_for_timeout(700)
        ck("🧹 Dọn ngay → admin_auto_clean", s.js("() => window.__TQ.cleaned") == 1)
        s.page.fill("#cln-days", "10"); s.page.click("#cln-save"); s.page.wait_for_timeout(800)
        ck("đổi thành 10 ngày → Lưu vào cài đặt (idle_purge_days 10)", s.js("() => SITE.idle_purge_days") == "10" and "Đã lưu" in (s.txt("#cln-smsg") or ""), (s.js("() => SITE.idle_purge_days"), s.txt("#cln-smsg")))
        s.page.fill("#cln-days", "400"); s.page.click("#cln-save"); s.page.wait_for_timeout(400)
        ck("số sai (400) → không lưu", s.js("() => SITE.idle_purge_days") == "10")
        s.shot("3-so-don.png")
        print("6. thẻ máy chủ: đồng hồ lệch · Windows không WGC · điểm lag")
        s.js("async () => { await loadNodes(); renderNodes(); }"); s.page.wait_for_timeout(600)
        n8 = s.txt('[data-node="n1"] .nf') or ""; n2 = s.txt('[data-node="n2"] .nf') or ""
        ck("máy chủ 8: '🕒 Đồng hồ lệch 3 phút (chạy nhanh)' · '🐢 Windows 10586 · không WGC' · '⚖️ Điểm lag +25'",
           "Đồng hồ lệch 3 phút (chạy nhanh)" in n8 and "Windows 10586 · không WGC" in n8 and "Điểm lag +25" in n8, n8)
        ck("máy chủ 2 (Windows 19045, lệch 4 giây) không báo gì thêm", "Đồng hồ" not in n2 and "WGC" not in n2 and "Điểm lag" not in n2, n2)
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()

        print("7. thẻ máy của khách: báo trước khi máy lâu không mở bị xoá")
        P = lambda pid, days, **k: dict({"id": pid, "name": "Máy " + pid, "user_id": ME, "status": "active", "android": "12", "ram": 4, "cpu": 4, "res": "720x1280", "fps": 30,
                                         "node": "n1", "expires_at": iso(10 * 86400), "created_at": iso(-20 * 86400), "is_free": False, "stream_url": "x",
                                         "idle_since": iso(-days * 86400) if days is not None else None}, **k)
        s = Site(br, html, admin=False, path="/", phones=[P("a", 6.2), P("b", 2), P("c", None), P("d", 9, real_device="d1", real_model="s10")])
        s.js("async () => { await openCloud(); }"); s.page.wait_for_timeout(900)
        cards = s.js("() => [...document.querySelectorAll('#cp-list .vmi')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ca = next((c for c in cards if "Máy a" in c), ""); cb = next((c for c in cards if "Máy b" in c), ""); cc = next((c for c in cards if "Máy c" in c), ""); cd = next((c for c in cards if "Máy d" in c), "")
        ck("máy 6 ngày không mở (mặc định 8): '💤 Máy đã 6 ngày không mở … xoá vĩnh viễn (không hoàn tiền) — còn khoảng 2 ngày'",
           "6 ngày không mở" in ca and "xoá vĩnh viễn" in ca and "không hoàn tiền" in ca and "còn khoảng 2 ngày" in ca, ca)
        ck("máy 2 ngày không mở · máy đang dùng · máy thật → không báo", "không mở" not in cb and "không mở" not in cc and "không mở" not in cd, (cb, cc, cd))
        s.shot("4-the-may-khach.png")
        s.ctx.close()
        s = Site(br, html, admin=False, path="/", phones=[P("a", 6.2)], settings={"idle_purge_days": "0"})
        s.js("async () => { await openCloud(); }"); s.page.wait_for_timeout(900)
        ck("admin tắt (0 ngày) → không báo", "không mở" not in (s.txt("#cp-list") or ""), s.txt("#cp-list"))
        s.ctx.close()
        s = Site(br, html, admin=False, path="/", phones=[P("a", 13)], settings={"idle_purge_days": "15"})
        s.js("async () => { await openCloud(); }"); s.page.wait_for_timeout(900)
        t = s.txt("#cp-list") or ""
        ck("admin đặt 15 ngày: máy 13 ngày → 'Quá 15 ngày không mở … còn khoảng 2 ngày'", "Quá 15 ngày không mở" in t and "còn khoảng 2 ngày" in t, t[:300])
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt · ảnh: {SHOTS}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
