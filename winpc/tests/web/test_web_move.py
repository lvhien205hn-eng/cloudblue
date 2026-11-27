# -*- coding: utf-8 -*-
"""27/11n · 🚚 CHUYỂN HẾT MÁY KHÁCH SANG MÁY CHỦ KHÁC — phần web admin (thẻ máy chủ › ⚙ Cài đặt › 🚚):
   hộp thoại · máy chủ nhận được (cùng giả lập · bản 27/11n · đang kết nối · không ⛔ Ngừng hẳn) · máy Android không hợp → giữ lại · gõ mã máy chủ
   mới mở nút · gọi admin_cp_move_start đúng tham số · tiến độ từng máy (chép / lỗi / xong) · chuyển lại máy lỗi · dừng · dòng tiến độ trên thẻ máy chủ
   (máy chủ cũ + máy chủ nhận) · chữ lỗi từ máy chủ được thoát HTML · chưa chạy SQL v65 · máy chủ cũ chưa lên bản / mất kết nối.
   Chrome thật (Playwright) + Supabase giả (fake_supabase.js); không gọi ra ngoài.
   python3 winpc/tests/web/test_web_move.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-move"
OK = FAIL = 0
U1 = "00000000-0000-4000-8000-0000000000a1"


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


def iso(sec):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def node(i, name, engine="mumu", move=1, age=0, enabled=True, hard=False, androids="12,15", phones=0, alloc=8):
    return {"id": i, "name": name, "enabled": enabled, "pause_hard": hard, "engine": engine, "androids": androids, "updated_at": iso(-age * 60),
            "created_at": iso(-86400 * 30), "ram_total": 64, "cap_ram": 56, "alloc_ram": alloc, "cpu_total": 32, "cap_cpu": 64, "alloc_cpu": 8, "limit_pct": 85,
            "phones": phones, "metrics": {"move": move, "gpus": [], "disk_data": {"used": 100, "total": 476}}}


NODES = [node("win3", "Server-3", phones=4, alloc=16), node("win5", "Server-5", androids="12"), node("win6", "Server-6", enabled=False),
         node("win7", "Server-7 cũ", move=0, phones=1), node("win8", "Server-8 LD", engine="ld", androids="9"), node("win9", "Server-9", age=12, phones=1),
         node("win4", "Server-4", enabled=False, hard=True)]
PH = [  # máy khách: 3 đang thuê + 1 chờ gia hạn ở win3 (1 máy Android 15), 1 máy đã huỷ (không tính), 1 máy ở win7, 1 máy ở win9
    {"id": "p-a", "name": "Farm A", "user_id": U1, "node": "win3", "status": "active", "android": "12", "ram": 4, "cpu": 4, "container": "cp_aaaaaaaaaa", "port": 16416},
    {"id": "p-b", "name": "Farm B", "user_id": U1, "node": "win3", "status": "active", "android": "12", "ram": 4, "cpu": 4, "container": "cp_bbbbbbbbbb", "port": 16448},
    {"id": "p-c", "name": "Farm C15", "user_id": U1, "node": "win3", "status": "active", "android": "15", "ram": 4, "cpu": 4, "container": "cp_cccccccccc", "port": 16480},
    {"id": "p-d", "name": "Farm D hết hạn", "user_id": U1, "node": "win3", "status": "expired", "android": "12", "ram": 4, "cpu": 4, "container": "cp_dddddddddd", "port": 16512},
    {"id": "p-x", "name": "Đã huỷ", "user_id": U1, "node": "win3", "status": "cancelled", "android": "12", "ram": 4, "cpu": 4},
    {"id": "p-7", "name": "Máy win7", "user_id": U1, "node": "win7", "status": "active", "android": "12", "ram": 4, "cpu": 4},
    {"id": "p-9", "name": "Máy win9", "user_id": U1, "node": "win9", "status": "active", "android": "12", "ram": 4, "cpu": 4},
]
for i, p in enumerate(PH): p.setdefault("created_at", iso(-86400 * (10 - i))); p.setdefault("expires_at", iso(5 * 86400)); p.setdefault("is_free", False)

HOOK = """(() => {
  window.__MV = { start: [], cancel: [] };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    admin_cp_move_start: (a, F) => {
      window.__MV.start.push(a);
      const ph = (F.db.cloud_phones || []).filter(p => p.node === a.p_node && ["active", "expired"].includes(p.status) && (!a.p_ids || a.p_ids.includes(p.id)));
      const live = ["queued", "claimed", "ready", "stopping", "serving", "copying", "booting"], b = "b" + (window.__MV.start.length);
      let n = 0, sk = 0; F.db.cp_moves = F.db.cp_moves || [];
      for (const p of ph) {
        if (F.db.cp_moves.some(j => j.phone_id === p.id && live.includes(j.status))) { sk++; continue; }
        F.db.cp_moves.push({ id: "j-" + p.id + "-" + b, batch: b, phone_id: p.id, src: a.p_node, want: a.p_target, dst: null, src_name: p.container, android: p.android,
          ram: p.ram, cpu: p.cpu, status: "queued", created_at: new Date(Date.now() + window.__MV.start.length * 1000).toISOString(), src_fin: false, dst_fin: false, tries: 0 });
        n++;
      }
      return { ok: true, batch: n ? b : null, count: n, skipped: sk };
    },
    admin_cp_move_cancel: (a, F) => { window.__MV.cancel.push(a); let c = 0;
      for (const j of F.db.cp_moves || []) if (j.src === a.p_node && ["queued", "claimed", "ready"].includes(j.status)) { j.status = "cancelled"; c++; }
      return { ok: true, cancelled: c, running: (F.db.cp_moves || []).filter(j => j.src === a.p_node && ["stopping", "serving", "copying", "booting"].includes(j.status)).length }; },
  }); })();"""


class Site:
    def __init__(self, browser, html, extra_init=None, vp=(1500, 1000)):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": True, "db": {"product_list": [], "products": [], "cloud_phones": json.loads(json.dumps(PH)), "cloud_nodes": json.loads(json.dumps(NODES)),
                                      "cp_moves": [], "pc_machines": []}}
        init.update(extra_init or {})
        self.ctx.add_init_script("window.__FAKE_INIT = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" and "Failed to load resource" not in m.text else None)
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
    def vis(self, sel): return self.js("q => { const e = document.querySelector(q); if (!e) return false; const r = e.getBoundingClientRect(); return !e.closest('[hidden]') && r.width > 0 && r.height > 0; }", sel)
    def dis(self, sel): return self.js("q => { const e = document.querySelector(q); return !e || e.disabled; }", sel)
    def shot(self, name):
        os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name))
    def close(self): self.ctx.close()

    def cloud(self):
        self.page.click('#adm-grp button[data-grp="mach"]'); self.page.wait_for_timeout(250)
        self.page.click('#adm-tabs button[data-tab="cloud"]'); self.page.wait_for_timeout(1200)
        self.page.click('#pane-cloud .subtabs button[data-sub="servers"]'); self.page.wait_for_timeout(500)
        self.page.wait_for_selector('#cpa-nodes .node[data-node="win3"]', timeout=8000)

    def open_move(self, nid):
        self.js("id => { const b = document.querySelector(`[data-nset=\"${id}\"]`); if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); }", nid)
        self.page.wait_for_timeout(150)
        self.page.click(f'.nacts [data-nmove="{nid}"]'); self.page.wait_for_timeout(900)

    def opts(self):
        return self.js("() => [...document.querySelectorAll('#nmv-to option')].map(o => ({ v: o.value, t: o.textContent, d: o.disabled }))")

    def tick(self):
        self.js("() => mvTick()"); self.page.wait_for_timeout(400)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

        print("1. Thẻ máy chủ › ⚙ Cài đặt › 🚚 — hộp thoại, máy chủ nhận được")
        s = Site(br, html); s.cloud()
        ck("nút 🚚 có ở máy chủ có máy khách (win3, win7, win9), không có ở máy chủ trống (win5)",
           s.js("() => ['win3','win7','win9'].every(id => !!document.querySelector(`.nacts [data-nmove=\"${id}\"]`)) && !document.querySelector('.nacts [data-nmove=\"win5\"]')"))
        s.open_move("win3")
        ck("mở hộp thoại 🚚 Chuyển hết máy · ghi tên + mã máy chủ + MuMu", s.vis("#nmvdlg") and "Server-3 (win3)" in (s.txt("#nmv-who") or "") and "MuMu" in s.txt("#nmv-who"), s.txt("#nmv-who"))
        st = s.txt("#nmv-st") or ""
        ck("tóm tắt: 4 máy (3 đang thuê · 1 chờ gia hạn) — máy đã huỷ không tính · Android 12, 15 · ✅ Chuyển được",
           "4 máy (3 đang thuê · 1 chờ gia hạn)" in st and "12, 15" in st and "✅ Chuyển được" in st, st)
        ck("máy chủ nhận được: Server-5 + Server-6 (đang ngừng nhận) — không có máy chủ cũ / khác giả lập / mất kết nối / Ngừng hẳn",
           "Server-5" in st and "Server-6 (đang ngừng nhận)" in st and not any(x in st for x in ("Server-7", "Server-8", "Server-9", "Server-4")), st)
        o = {x["v"]: x for x in s.opts()}
        ck("chọn đích: Tự chia (1 máy chủ đang nhận) + từng máy chủ; máy chủ không nhận được bị khoá, ghi lý do",
           o[""]["d"] is False and "(1 máy chủ)" in o[""]["t"] and o["win5"]["d"] is False and o["win6"]["d"] is False
           and "đang ngừng nhận máy (vẫn nhận máy chuyển khi chọn đích danh)" in o["win6"]["t"]
           and o["win7"]["d"] and "chưa lên bản 27/11n" in o["win7"]["t"] and o["win8"]["d"] and "khác giả lập (LDPlayer 9)" in o["win8"]["t"]
           and o["win9"]["d"] and "mất kết nối" in o["win9"]["t"] and o["win4"]["d"] and "Ngừng hẳn" in o["win4"]["t"] and "win3" not in o, list(o.values()))
        ck("nút Bắt đầu KHOÁ khi chưa gõ mã máy chủ · ghi số máy (4)", s.dis("#nmv-go") and "4 máy" in (s.txt("#nmv-go") or ""), s.txt("#nmv-go"))
        s.page.fill("#nmv-confirm", "win5"); s.page.wait_for_timeout(100)
        ck("gõ sai mã (win5) → vẫn khoá", s.dis("#nmv-go"))
        s.page.fill("#nmv-confirm", " WIN3 "); s.page.wait_for_timeout(100)
        ck("gõ đúng mã (không phân biệt hoa thường, bỏ khoảng trắng) → mở nút", not s.dis("#nmv-go"))
        s.shot("1-hop-thoai.png")

        print("2. Chọn đích win5 (chỉ bán Android 12) → máy Android 15 giữ lại · bắt đầu chuyển")
        s.page.select_option("#nmv-to", "win5"); s.page.wait_for_timeout(150)
        w = s.txt("#nmv-warn") or ""
        ck("cảnh báo: 1 máy Android 15 không chuyển sang Server-5 được — giữ ở đây · nút ghi 3 máy",
           "1 máy Android 15 không chuyển sang Server-5 được" in w and "giữ ở đây" in w and "3 máy" in (s.txt("#nmv-go") or ""), [w, s.txt("#nmv-go")])
        s.page.click("#nmv-go"); s.page.wait_for_timeout(900)
        calls = s.js("() => window.__MV.start")
        ck("gọi admin_cp_move_start(p_node=win3, p_target=win5, p_ids = 3 máy Android 12 — gồm máy chờ gia hạn)",
           len(calls) == 1 and calls[0]["p_node"] == "win3" and calls[0]["p_target"] == "win5" and sorted(calls[0]["p_ids"]) == ["p-a", "p-b", "p-d"], calls)
        m = s.txt("#nmv-msg") or ""
        ck("báo: đã xếp 3 máy sang win5 · máy chủ đã sang ⛔ Ngừng hẳn · ô xác nhận được xoá", "Đã xếp 3 máy vào hàng chuyển sang win5" in m and "Ngừng hẳn" in m
           and s.js("() => document.getElementById('nmv-confirm').value") == "", m)
        ck("hiện tiến độ: 3 máy chờ máy chủ nhận (win5)", s.vis("#nmv-prog") and (s.txt("#nmv-list") or "").count("⏳ Chờ máy chủ nhận (win5)") == 3, s.txt("#nmv-list"))
        ck("máy đã trong lượt chuyển → nút còn 1 máy (Android 15) — chọn Tự chia", True)
        s.page.select_option("#nmv-to", ""); s.page.wait_for_timeout(150)
        ck("… Tự chia: còn đúng 1 máy (Farm C15) chưa có lượt chuyển; báo '3 máy đang trong lượt chuyển'",
           "1 máy" in (s.txt("#nmv-go") or "") and "3 máy đang trong lượt chuyển" in (s.txt("#nmv-warn") or ""), [s.txt("#nmv-go"), s.txt("#nmv-warn")])

        print("3. Tiến độ từng máy (tự cập nhật) · chuyển lại máy lỗi · dừng")
        s.js("""() => { const J = window.__FAKE.db.cp_moves, G = 2 ** 30;
          Object.assign(J.find(j => j.phone_id === 'p-a'), { status: 'copying', dst: 'win5', bytes_total: 4 * G, bytes_done: G, rate_kbs: 25600, note: 'qua mạng LAN', size_hint: 4 * G });
          Object.assign(J.find(j => j.phone_id === 'p-b'), { status: 'failed', dst: 'win5', error: 'win5: Android không lên sau 2 lần bật <img src=x onerror="window.__xss=1">', src_fin: true });
          Object.assign(J.find(j => j.phone_id === 'p-d'), { status: 'done', dst: 'win5', dst_name: 'cp_ddddddddddm1a2b', src_fin: true, dst_fin: true, bytes_total: G, bytes_done: G }); }""")
        s.tick()
        L = s.txt("#nmv-list") or ""
        ck("đang chép: 1.0 GB / 4.0 GB · 25 MB/s · qua mạng LAN + thanh 25%", "⬇ Đang chép sang win5: 1.0 GB / 4.0 GB · 25 MB/s · qua mạng LAN" in L
           and s.js("() => document.querySelector('[data-mvjob^=\"j-p-a\"] .nmv-bar i').style.width") == "25%", L)
        ck("lỗi: ghi lý do + 'máy đã về như cũ ở đây' · chữ lỗi được thoát HTML (không chạy mã)", "❌ win5: Android không lên sau 2 lần bật" in L and "máy đã về như cũ ở đây" in L
           and not s.js("() => window.__xss") and s.js("() => !document.querySelector('#nmv-list img')"), L)
        ck("xong: ✅ Đã chạy ở win5 (tên máy mới)", "✅ Đã chạy ở win5 (cp_ddddddddddm1a2b)" in L, L)
        ck("tóm tắt đợt: 1/3 máy xong · 1 đang làm · 1 lỗi", "1/3 máy xong · 1 đang làm · 1 lỗi" in (s.txt("#nmv-sum") or ""), s.txt("#nmv-sum"))
        ck("thứ tự: máy đang chép lên đầu, máy xong xuống cuối", s.js("() => [...document.querySelectorAll('#nmv-list [data-mvjob]')].map(r => r.dataset.mvjob.split('-')[2])") == ["a", "b", "d"],
           s.js("() => [...document.querySelectorAll('#nmv-list [data-mvjob]')].map(r => r.dataset.mvjob)"))
        ck("nút 🔁 Chuyển lại 1 máy lỗi hiện, khoá khi chưa gõ mã", s.vis("#nmv-retry") and "1 máy lỗi" in (s.txt("#nmv-retry") or "") and s.dis("#nmv-retry"), s.txt("#nmv-retry"))
        s.page.select_option("#nmv-to", "win5"); s.page.fill("#nmv-confirm", "win3"); s.page.wait_for_timeout(150)
        s.page.click("#nmv-retry"); s.page.wait_for_timeout(900)
        calls = s.js("() => window.__MV.start")
        ck("chuyển lại: admin_cp_move_start chỉ máy lỗi (p_ids=[p-b]), đúng đích win5", len(calls) == 2 and calls[1]["p_ids"] == ["p-b"] and calls[1]["p_target"] == "win5", calls)
        ck("không có hộp thoại trình duyệt (confirm / alert) nào bật lên", not any(e.startswith("DIALOG") for e in s.errors), s.errors)
        s.tick()
        ck("nút ⏹ Dừng hiện khi còn máy chưa chuyển (1 máy chờ)", s.vis("#nmv-stop") and "1 máy chưa chuyển" in (s.txt("#nmv-stop") or ""), s.txt("#nmv-stop"))
        s.page.click("#nmv-stop"); s.page.wait_for_timeout(900)
        m = s.txt("#nmv-msg") or ""
        ck("dừng: gọi admin_cp_move_cancel(win3) · báo đã dừng 1 máy, 1 máy đang chép làm cho xong", s.js("() => window.__MV.cancel") == [{"p_node": "win3"}]
           and "Đã dừng 1 máy chưa chuyển" in m and "1 máy đang chép dở sẽ làm cho xong" in m, m)
        s.shot("3-tien-do.png")

        print("4. Dòng tiến độ trên thẻ máy chủ (máy chủ cũ + máy chủ nhận)")
        s.page.click("#nmv-close"); s.page.wait_for_timeout(200)
        s.js("() => refreshNodes()"); s.page.wait_for_timeout(700)
        c3 = s.txt('#cpa-nodes .node[data-node="win3"] .nmeta') or ""; c5 = s.txt('#cpa-nodes .node[data-node="win5"] .nmeta') or ""
        ck("thẻ win3: 🚚 Đang chuyển máy đi: 1/3 xong (tính theo máy — máy chuyển lại tính lượt mới) · 1 đang chép + nút Xem", "🚚 Đang chuyển máy đi: 1/3 xong · 1 đang chép" in c3
           and s.js("() => !!document.querySelector('#cpa-nodes .node[data-node=\"win3\"] .nmeta [data-nmove=\"win3\"]')"), c3)
        ck("thẻ win5: 🚚 Đang nhận 1 máy từ win3", "🚚 Đang nhận 1 máy từ win3" in c5, c5)
        s.page.click('#cpa-nodes .node[data-node="win3"] .nmeta [data-nmove="win3"]'); s.page.wait_for_timeout(700)
        ck("bấm Xem → mở lại hộp thoại tiến độ", s.vis("#nmvdlg") and s.vis("#nmv-prog"))
        s.page.click("#nmv-close")
        ck("không lỗi JS / console", not s.errors, s.errors)
        s.close()

        print("5. Chưa chạy SQL v65 · máy chủ cũ chưa lên bản · máy chủ cũ mất kết nối · lỗi từ cơ sở dữ liệu")
        s = Site(br, html, {"noTables": ["cp_moves"]}); s.cloud(); s.open_move("win3")
        w = s.txt("#nmv-warn") or ""
        ck("chưa có bảng cp_moves → báo chạy SQL v65, nút khoá dù đã gõ mã", "Cần chạy file SQL v65" in w and (s.page.fill("#nmv-confirm", "win3") or True) and s.dis("#nmv-go"), w)
        ck("… không báo lỗi đỏ / lỗi JS, thẻ máy chủ vẫn vẽ bình thường", not s.errors and s.js("() => document.querySelectorAll('#cpa-nodes .node').length") == len(NODES), s.errors)
        s.close()
        s = Site(br, html); s.cloud(); s.open_move("win7")
        st = s.txt("#nmv-st") or ""; w = s.txt("#nmv-warn") or ""
        ck("máy chủ cũ chưa lên bản 27/11n → báo ⚠ + cách cập nhật, nút khoá", "⚠ Chưa lên bản 27/11n" in st and "⬆ Cập nhật máy chủ" in w
           and (s.page.fill("#nmv-confirm", "win7") or True) and s.dis("#nmv-go"), [st, w])
        s.page.click("#nmv-close"); s.open_move("win9")
        st = s.txt("#nmv-st") or ""; w = s.txt("#nmv-warn") or ""
        ck("máy chủ cũ mất kết nối → báo không chép được, nút khoá", "❌ Mất kết nối" in st and "đang mất kết nối" in w and (s.page.fill("#nmv-confirm", "win9") or True)
           and s.dis("#nmv-go"), [st, w])
        s.page.click("#nmv-close"); s.open_move("win3")
        s.js("() => { window.__FAKE.failRpc.admin_cp_move_start = 'SAME_NODE: máy chủ đích phải khác máy chủ cũ'; }")
        s.page.fill("#nmv-confirm", "win3"); s.page.wait_for_timeout(100); s.page.click("#nmv-go"); s.page.wait_for_timeout(800)
        ck("cơ sở dữ liệu báo lỗi → hiện lời dễ hiểu, nút mở lại", "Máy chủ đích phải khác máy chủ này" in (s.txt("#nmv-msg") or "") and not s.dis("#nmv-go"), s.txt("#nmv-msg"))
        s.js("() => { window.__FAKE.failRpc.admin_cp_move_start = 'Could not find the function public.admin_cp_move_start(p_ids, p_node, p_target) in the schema cache'; }")
        s.page.click("#nmv-go"); s.page.wait_for_timeout(800)
        ck("chưa có hàm SQL → báo chạy SQL v65", "Cần chạy file SQL v65" in (s.txt("#nmv-msg") or ""), s.txt("#nmv-msg"))
        ck("không lỗi JS / console", not s.errors, s.errors)
        s.close()

        print("6. Điện thoại (390px): hộp thoại vừa màn, không tràn ngang")
        s = Site(br, html, vp=(390, 844)); s.cloud(); s.open_move("win3")
        ow = s.js("() => { const d = document.querySelector('#nmvdlg .dlg'); return [d.scrollWidth, d.clientWidth, document.documentElement.scrollWidth]; }")
        ck("không tràn ngang", ow[0] <= ow[1] + 1 and ow[2] <= 391, ow)
        s.shot("6-dien-thoai.png")
        s.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
