# -*- coding: utf-8 -*-
"""28/11g · 🧹 DỌN SẠCH + XOÁ MÁY BỎ KHÔNG ≥ 7 NGÀY cho các máy chủ đã tick (ô "⚙ Cài đặt cho N máy đã chọn" — bấm 1 lần thay vì từng máy chủ).
   Chrome thật (Playwright) + Supabase giả + cpapi giả của từng máy chủ.
   python3 winpc/tests/web/test_web_donmay.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0
FAKE = open(os.path.join(HERE, "fake_supabase.js"), encoding="utf-8").read()
ADMIN_ID = "00000000-0000-4000-8000-000000000001"


def iso(sec): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


D = 86400
U = lambda i: "00000000-0000-4000-8000-%012d" % (i + 10)
P = lambda i: "10000000-0000-4000-8000-%012d" % i


def ph(i, node, status="active", idle_d=None, **kw):
    r = {"id": P(i), "name": "cp_may%02d" % i, "user_id": U(i), "node": node, "status": status, "ram": 4, "cpu": 4, "android": "12",
         "idle_since": iso(-idle_d * D) if idle_d is not None else None, "expires_at": iso(5 * D), "created_at": iso(-40 * D)}
    r.update(kw); return r


PHONES = [
    ph(1, "n1", idle_d=10),                                   # ✔ xoá
    ph(2, "n1", idle_d=3),                                    # mới không mở 3 ngày → giữ
    ph(3, "n1", status="expired", idle_d=8, expires_at=iso(-3600)),   # ✔ xoá (đã hết hạn)
    ph(4, "n1", idle_d=20, locked=True),                      # bị khoá → giữ
    ph(5, "n1", idle_d=9, real_device="rd-1"),                # máy thật → giữ
    ph(6, "n1", idle_d=9, switch_to="12"),                    # đang đổi Android → giữ
    ph(7, "n2", idle_d=12, user_id=ADMIN_ID),                 # máy của admin → giữ
    ph(8, "n2", idle_d=15, pending_renew_days=2),             # chờ cộng ngày gia hạn → giữ
    ph(9, "n2", idle_d=11),                                   # đang chờ máy thay (p10 replaces p9) → giữ
    ph(10, "n2", status="pending", replaces=P(9)),
    ph(11, "n2"),                                             # đang được dùng (idle_since null) → giữ
    ph(12, "n3", idle_d=30),                                  # ✔ xoá (máy chủ mất kết nối: chỉ ghi xoá, không dọn giả lập)
    ph(13, "n4", idle_d=30),                                  # máy chủ không tick → giữ
    ph(14, "n2", status="cancelled", idle_d=30),              # đã huỷ → bỏ qua
    ph(15, "n1", idle_d=7.2),                                 # ✔ xoá (vừa quá 7 ngày)
    ph(16, "n1", idle_d=6.8),                                 # chưa tới 7 ngày → giữ
]
WANT = sorted([P(1), P(3), P(12), P(15)])
NODES = [
    {"id": "n1", "name": "Server A", "enabled": True, "updated_at": iso(-20), "created_at": iso(-90 * D), "metrics": {"base": "https://s1.cloudblue.vn"}, "phones": 7},
    {"id": "n2", "name": "Server B", "enabled": True, "updated_at": iso(-30), "created_at": iso(-80 * D), "metrics": {"base": "https://s2.cloudblue.vn"}, "phones": 6},
    {"id": "n3", "name": "Server C", "enabled": True, "updated_at": iso(-3600), "created_at": iso(-70 * D), "metrics": {"base": "https://s3.cloudblue.vn"}, "phones": 1},
    {"id": "n4", "name": "Server D", "enabled": True, "updated_at": iso(-10), "created_at": iso(-60 * D), "metrics": {"base": "https://s4.cloudblue.vn"}, "phones": 1},
]
DB = {"product_list": [], "products": [], "settings": [{"id": 1, "data": {}}], "topups": [], "orders": [], "vps_machines": [], "pc_machines": [],
      "cloud_phones": PHONES, "cloud_nodes": NODES,
      "cloudphone_pricing": [{"id": 1, "android_versions": "12", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32, "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}]}
USERS = [{"id": U(i), "username": "khach%d" % i, "email": "k%d@mail.test" % i, "role": "user", "balance": 0, "created_at": iso(-i * 900)} for i in range(1, 17)]
INIT = """
window.__FAKE_INIT = %s;
(() => { const ex = %s; const t = setInterval(() => { if (window.__FAKE) { window.__FAKE.db.profiles = (window.__FAKE.db.profiles || []).concat(ex); clearInterval(t); } }, 0); })();
window.__FAKE_HOOK = {
  admin_stats: () => ({ generated_at: '19:00 28/11/2026', revenue_total: 1, customers: 16, top_products: [] }),
  admin_cloud_delete: a => ({ data: (a.p_ids || []).length, error: null }),
};
try { localStorage.setItem('br_lang', 'vi'); } catch (e) {}
"""


class Site:
    def __init__(self, browser, html):
        self.errors = []; self.dialogs = []; self.answer = "XOA"; self.api = []
        self.ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        self.ctx.add_init_script(INIT % (json.dumps({"admin": True, "db": DB}), json.dumps(USERS)))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append(str(e).splitlines()[0][:300]))
        self.page.on("dialog", self.dialog)
        self.page.goto(ORIGIN + "/admin", wait_until="load"); self.page.wait_for_timeout(2500)

    def dialog(self, d):
        self.dialogs.append((d.type, d.message))
        if d.type == "prompt": d.accept(self.answer)
        else: d.dismiss()

    def route(self, r):
        u, req = r.request.url, r.request
        cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*"}
        if u.split("#")[0].split("?")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return r.fulfill(status=200, content_type="application/javascript", body=FAKE)
        if ".cloudblue.vn/cpapi/" in u:
            if req.method == "OPTIONS": return r.fulfill(status=204, headers=cors, body="")
            host = u.split("//")[1].split(".")[0]
            if "/cpapi/admin/node" in u and req.method == "POST":
                self.api.append((host, json.loads(req.post_data or "{}")))
                return r.fulfill(status=200, headers=cors, content_type="application/json", body=json.dumps({"job": "j-" + host}))
            if "/cpapi/job?id=" in u:
                out = "XOA_THUA cp_cu1 (MEmu #5)\nXOA_THUA cp_cu2 (MEmu #6)\n" if host == "s1" else "Không có giả lập thừa.\n"
                return r.fulfill(status=200, headers=cors, content_type="application/json", body=json.dumps({"state": "done", "msg": "Xong: Dọn giả lập thừa", "out": out}))
            return r.fulfill(status=200, headers=cors, content_type="application/json", body="{}")
        return r.fulfill(status=204, body="")

    def js(self, e, a=None): return self.page.evaluate(e, a)

    def dels(self): return self.js("() => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === 'admin_cloud_delete').map(c => (c.args.p_ids || []).slice().sort())")

    def click_purge(self, ids):
        n0 = self.js("""ids => { if (!window.__pdw) { window.__pdw = 1; window.__pd = 0; const o = nodePurgeIdle;
            nodePurgeIdle = async function () { try { return await o.apply(this, arguments); } finally { window.__pd++; } }; }
          NSEL.clear(); ids.forEach(i => NSEL.add(i)); NBULK_OPEN = true; renderNodes(); return window.__pd; }""", ids)
        self.page.wait_for_timeout(150)
        self.page.click("#cpa-nbulk [data-nbulk=purge]")
        self.page.wait_for_function("n => window.__pd > n && !NBULK_BUSY", arg=n0, timeout=20000)      # chờ việc chạy XONG hẳn
        self.page.wait_for_timeout(300)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None, args=["--no-sandbox"])
        s = Site(br, html)
        s.js("""() => { const b = document.querySelector("#adm-tabs button[data-tab='cloud']"); if (b && !b.offsetParent) for (const g of document.querySelectorAll('#adm-grp button[data-grp]')) { g.click(); if (b.offsetParent) break; } }""")
        s.page.click("#adm-tabs button[data-tab='cloud']"); s.page.wait_for_timeout(1500)
        s.page.click('#pane-cloud .subtabs button[data-sub="servers"]'); s.page.wait_for_timeout(800)      # mục 🖥 Máy chủ (danh sách máy chủ + ô chỉnh nhiều máy)
        print("1. nút trong ô ⚙ Cài đặt cho N máy đã chọn")
        s.js("() => { NSEL.clear(); ['n1', 'n2', 'n3'].forEach(i => NSEL.add(i)); NBULK_OPEN = true; renderNodes(); }"); s.page.wait_for_timeout(200)
        b = s.js("() => { const b = document.querySelector('#cpa-nbulk [data-nbulk=purge]'); return b && { t: b.innerText.trim(), v: !!b.offsetParent, d: b.classList.contains('danger'), h: document.querySelector('#cpa-nbulk .hint').innerText }; }")
        ck("có nút '🧹 Dọn sạch + xoá máy bỏ không ≥ 7 ngày' (nút đỏ, đang hiện)", b and b["t"] == "🧹 Dọn sạch + xoá máy bỏ không ≥ 7 ngày" and b["v"] and b["d"], b)
        ck("chú thích không còn bảo 'Dọn giả lập' phải làm từng máy", b and "Dọn giả lập" not in b["h"] and "Xoá sạch MỌI máy" in b["h"], b and b["h"])

        print("2. hỏi trước: danh sách máy sẽ xoá + phải gõ XOA")
        s.answer = "khong"; s.dialogs.clear()
        s.click_purge(["n1", "n2", "n3"])
        msg = s.dialogs[-1][1] if s.dialogs else ""
        ck("hiện đúng 1 hộp gõ xác nhận", len(s.dialogs) == 1 and s.dialogs[0][0] == "prompt", s.dialogs)
        ck("… liệt kê đúng 4 máy bỏ không ≥ 7 ngày (cả máy đã hết hạn, máy ở máy chủ mất kết nối, máy vừa quá 7 ngày)",
           "XOÁ VĨNH VIỄN 4 máy khách" in msg and all(("cp_may%02d" % i) in msg for i in (1, 3, 12, 15)), msg)
        ck("… KHÔNG có máy mới không mở · bị khoá · máy thật · đang đổi Android · của admin · chờ cộng ngày · chờ máy thay · đang dùng · máy chủ không tick · đã huỷ · chưa tới 7 ngày",
           not any(("cp_may%02d" % i) in msg for i in (2, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16)), msg)
        ck("… ghi khách · số ngày không mở · còn hạn / đã hết hạn", "khach1 · 10 ngày không mở · còn hạn 5 ngày" in msg and "cp_may03 — khach3 · 8 ngày không mở · đã hết hạn" in msg, msg)
        ck("… nói rõ dọn giả lập thừa trên 2 máy chủ đang kết nối, bỏ qua Server C (mất kết nối)", "trên 2 máy chủ đang kết nối" in msg and "Bỏ qua: Server C" in msg, msg)
        ck("gõ sai → không xoá gì, không gọi máy chủ", s.dels() == [] and s.api == [] and "Chưa xác nhận" in s.js("() => document.body.innerText"), (s.dels(), s.api))

        print("3. gõ XOA → xoá + dọn giả lập thừa")
        s.answer = "xoa"; s.dialogs.clear()
        s.click_purge(["n1", "n2", "n3"])
        d = s.dels()
        ck("admin_cloud_delete gọi đúng 1 lần với đúng 4 máy (không hoàn tiền, như nút 🗑️ Xoá)", d == [WANT], d)
        api = sorted(s.api, key=lambda x: x[0])
        ck("mỗi máy chủ đang kết nối chạy 🧹 Dọn giả lập thừa (có mã máy chủ xác nhận); máy chủ mất kết nối không gọi",
           api == [("s1", {"do": "cleanup", "confirm": "n1"}), ("s2", {"do": "cleanup", "confirm": "n2"})], api)
        jobs = s.js("() => Object.fromEntries([...NJOB.entries()].map(([k, v]) => [k, v.st + ' | ' + v.msg]))")
        ck("Server A: ✅ xoá 3 máy bỏ không + dọn 2 giả lập thừa", jobs.get("n1", "").startswith("ok") and "xoá 3 máy bỏ không ≥ 7 ngày" in jobs["n1"] and "xoá 2 giả lập" in jobs["n1"], jobs.get("n1"))
        ck("Server B: ✅ không có máy bỏ không · không có giả lập thừa", jobs.get("n2", "").startswith("ok") and "không có máy bỏ không" in jobs["n2"] and "không có giả lập thừa" in jobs["n2"], jobs.get("n2"))
        ck("Server C (mất kết nối): ✅ đã ghi xoá 1 máy, nói rõ chưa dọn giả lập (tự xoá khi máy chủ chạy lại)",
           jobs.get("n3", "").startswith("ok") and "xoá 1 máy bỏ không" in jobs["n3"] and "chưa dọn giả lập thừa (máy chủ mất kết nối" in jobs["n3"], jobs.get("n3"))
        ck("báo xong: đã ghi xoá 4 máy", "Đã ghi xoá 4 máy bỏ không ≥ 7 ngày" in s.js("() => document.body.innerText"))

        print("4. không có máy bỏ không / đang bảo trì / lỗi xoá")
        s.answer = "XOA"; s.dialogs.clear(); s.api.clear(); n0 = len(s.dels())
        s.click_purge(["n4"])
        ck("Server D (máy p13 bỏ không 30 ngày): vẫn liệt kê + dọn giả lập (máy chủ D đang kết nối)", s.dialogs and "cp_may13" in s.dialogs[-1][1] and [a[0] for a in s.api] == ["s4"], (s.dialogs[-1:], s.api))
        s.js("() => { window.__FAKE.db.cloud_phones = window.__FAKE.db.cloud_phones.filter(p => p.id !== '%s'); }" % P(13))
        s.dialogs.clear(); s.api.clear()
        s.click_purge(["n4"])
        m4 = s.dialogs[-1][1] if s.dialogs else ""
        ck("không có máy nào bỏ không → vẫn hỏi để dọn giả lập thừa, không gọi xoá", "Không có máy khách nào bỏ không từ 7 ngày" in m4 and len(s.dels()) == n0 + 1 and [a[0] for a in s.api] == ["s4"], (m4[:200], s.dels(), s.api))
        s.dialogs.clear(); s.api.clear()
        s.js("() => { CPpricing.maintenance = true; }")
        s.click_purge(["n1"])
        ck("đang bảo trì → không hỏi, không xoá, báo tắt bảo trì trước", not s.dialogs and s.api == [] and "Đang bảo trì" in s.js("() => document.body.innerText"), (s.dialogs, s.api))
        s.js("() => { CPpricing.maintenance = false; window.__FAKE.failRpc.admin_cloud_delete = 'NOT_ADMIN'; }")
        s.dialogs.clear(); s.api.clear()
        s.click_purge(["n1"])
        jobs = s.js("() => Object.fromEntries([...NJOB.entries()].map(([k, v]) => [k, v.st + ' | ' + v.msg]))")
        ck("xoá lỗi → dòng máy chủ báo ❌ chưa xoá (lý do), vẫn dọn giả lập thừa", jobs.get("n1", "").startswith("err") and "chưa xoá" in jobs["n1"] and [a[0] for a in s.api] == ["s1"], jobs.get("n1"))
        ck("trang không lỗi JavaScript", not [e for e in s.errors if "reading 'cfg'" not in e], s.errors)
        s.ctx.close(); br.close()
    print("%d/%d đạt" % (OK, OK + FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
