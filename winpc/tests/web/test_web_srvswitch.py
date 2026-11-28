# -*- coding: utf-8 -*-
"""28/11 · ĐỔI MÁY CHỦ GIỮ NGUYÊN ANDROID (SQL v67 · cloudphone_change_server) — phần web của khách:
   nút "🤖 Đổi Android / máy chủ" trên thẻ máy · hộp đổi có lựa chọn "🔀 Giữ Android 12 · máy chủ khác" · gọi đúng hàm, đúng tham số ·
   báo lỗi rõ (chưa có máy chủ khác còn chỗ · web chưa chạy SQL v67) · đổi sang Android khác vẫn gọi hàm cũ · máy mới hiện "ở máy chủ khác".
   Chrome thật (Playwright) + Supabase giả (fake_supabase.js); không gọi ra ngoài.
   python3 winpc/tests/web/test_web_srvswitch.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-srvswitch"
ME = "00000000-0000-4000-8000-000000000001"
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


def iso(sec):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


PH = [{"id": "p-1", "name": "Máy farm", "user_id": ME, "status": "active", "android": "12", "ram": 4, "cpu": 4, "paid_ram": 4, "paid_cpu": 4,
       "res": "720x1280", "fps": 30, "node": "n1", "container": "cp_aaaa", "port": 16416, "expires_at": iso(5 * 86400), "created_at": iso(-86400),
       "is_free": False, "stream_url": "https://phone.test/x"}]
PRICING = [{"id": 1, "android_versions": "9,12,15", "price_ram_gb_day": 300, "price_cpu_day": 350, "max_ram": 16, "max_cpu": 32, "min_days": 1, "max_days": 90,
            "android_limits": {"9": {"ram": 8, "cpu": 8}, "12": {"ram": 16, "cpu": 32}, "15": {"ram": 16, "cpu": 32}}}]
HOOK = """(() => {
  window.__SW = { mode: 'ok' };
  const av = { free_ram: 40, free_cpu: 40, online: true };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    cloudphone_status: () => ({ maint: false, online: true, free_ram: 80, free_cpu: 80, android: { '9': av, '12': av, '15': av } }),
    cloudphone_change_server: (a, F) => {
      if (window.__SW.mode === 'full') return { data: null, error: { code: 'P0001', message: 'NO_OTHER_SERVER: Hiện chưa có máy chủ khác còn chỗ cho Android 12 — máy của bạn vẫn giữ nguyên, thử lại sau ít phút' } };
      if (window.__SW.mode === 'nosql') return { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.cloudphone_change_server(p_id) in the schema cache' } };
      return { ok: true, new_id: 'p-2', android: '12', server_change: true };
    },
    cloudphone_switch_android: () => ({ ok: true, new_id: 'p-3', android: '15' }),
    cloudphone_servers: () => ({ stop: 95, names: { n1: 'Server Alpha', n2: 'Server Beta' }, servers: [
      { id: 'n1', name: 'Server Alpha', androids: ['12', '15'], online: true, pct: 81, free_ram: 20, free_cpu: 20 },
      { id: 'n2', name: 'Server Beta', androids: ['12', '15'], online: true, pct: 40, free_ram: 60, free_cpu: 60 }] }),
  }); })();"""


class Site:
    def __init__(self, browser, html, db=None):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": 1400, "height": 950}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": False, "db": db or {"product_list": [], "products": [], "cloud_phones": json.loads(json.dumps(PH)), "cloudphone_pricing": PRICING}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("dialog", lambda d: (self.errors.append("DIALOG: " + d.message[:200]), d.dismiss()))
        self.page.goto(ORIGIN + "/", wait_until="load")
        self.page.wait_for_timeout(2000)

    def route(self, route):
        u = route.request.url
        if u.split("#")[0].split("?")[0] in (ORIGIN + "/",): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def calls(self, name): return self.js("n => (window.__FAKE.calls || []).filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)
    def shot(self, name): os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name))

    def open_switch(self):
        self.js("() => openCloud()"); self.page.wait_for_timeout(900)
        self.page.click('[data-cpswitch="p-1"]'); self.page.wait_for_timeout(700)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        print("1. thẻ máy + hộp đổi")
        s = Site(br, html)
        s.js("() => openCloud()"); s.page.wait_for_timeout(900)
        ck("nút trên thẻ máy: '🤖 Đổi Android / máy chủ'", "Đổi Android / máy chủ" in (s.txt('[data-cpswitch="p-1"]') or ""), s.txt('[data-cpswitch="p-1"]'))
        s.page.click('[data-cpswitch="p-1"]'); s.page.wait_for_timeout(700)
        chips = s.js("() => [...document.querySelectorAll('#cpswdlg [data-swv]')].map(b => [b.dataset.swv, b.innerText.trim()])")
        ck("hộp có lựa chọn '🔀 Giữ Android 12 · máy chủ khác' + Android 9, 15 (không có nút Android 12 riêng)",
           ["srv", "🔀 Giữ Android 12 · máy chủ khác"] in chips and {c[0] for c in chips} == {"srv", "9", "15"}, chips)
        ck("tiêu đề 'Đổi Android / máy chủ'", "Đổi Android / máy chủ" in (s.txt("#csw-t") or ""))
        ck("khách thấy số lượt còn lại: 'Còn 3/3 lượt đổi trong 24 giờ … Máy mới tự vào máy chủ còn trống nhất'",
           "Còn 3/3 lượt đổi trong 24 giờ" in (s.txt("#csw-left") or "") and "máy chủ còn trống nhất" in (s.txt("#csw-left") or ""), s.txt("#csw-left"))
        s.page.click('#cpswdlg [data-swv="srv"]'); s.page.wait_for_timeout(250)
        hint = s.txt("#cpswdlg .dlg") or ""
        ck("chọn giữ Android: máy mới Android 12 · 4GB · 4 nhân · ở máy chủ khác · vẫn cảnh báo xoá sạch dữ liệu",
           "Máy mới: Android 12 · 4GB · 4 nhân" in hint and "ở máy chủ khác" in hint and "XOÁ SẠCH" in hint, hint)
        ck("nút 'Đổi sang máy chủ khác' khoá tới khi tick đã hiểu", s.txt("#csw-go") == "Đổi sang máy chủ khác" and s.js("() => document.querySelector('#csw-go').disabled"))
        s.shot("1-hop-doi-may-chu.png")
        s.page.check("#csw-ok"); s.page.wait_for_timeout(200)
        s.page.click("#csw-go"); s.page.wait_for_timeout(900)
        ck("bấm → gọi cloudphone_change_server(p_id = máy này), không gọi đổi Android", s.calls("cloudphone_change_server") == [{"p_id": "p-1"}]
           and not s.calls("cloudphone_switch_android"), (s.calls("cloudphone_change_server"), s.calls("cloudphone_switch_android")))
        ck("hộp đóng + báo đang xoá máy cũ, tạo máy Android 12 ở máy chủ khác",
           s.js("() => document.getElementById('cpswdlg').hidden") and "ở máy chủ khác" in (s.txt("#toast") or s.js("() => document.body.innerText") or ""))
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()

        print("1b. khách không thấy máy chủ (chỉ admin)")
        s = Site(br, html)
        s.js("async () => { await cpLoadServers(); }"); s.page.wait_for_timeout(300)
        s.js("() => openCpOrder()"); s.page.wait_for_timeout(1200)
        ck("hộp thuê máy: khách KHÔNG thấy danh sách máy chủ / % đầy", s.js("() => { const f = document.getElementById('cp-srv-f'); return !f || f.hidden; }")
           and "Server Alpha" not in (s.js("() => document.body.innerText") or ""))
        ck("thẻ máy: khách không thấy tên máy chủ (cpSrvName rỗng)", s.js("() => cpSrvName('n1')") == "")
        s.ctx.close()

        print("2. báo lỗi rõ")
        s = Site(br, html); s.js("() => { window.__SW.mode = 'full'; }"); s.open_switch()
        s.page.click('#cpswdlg [data-swv="srv"]'); s.page.check("#csw-ok"); s.page.click("#csw-go"); s.page.wait_for_timeout(700)
        ck("chưa có máy chủ khác còn chỗ → câu dễ hiểu, máy giữ nguyên, hộp vẫn mở",
           "Hiện chưa có máy chủ khác còn chỗ cho bản Android này" in (s.txt("#csw-err") or "") and not s.js("() => document.getElementById('cpswdlg').hidden"), s.txt("#csw-err"))
        s.js("() => { window.__SW.mode = 'nosql'; }"); s.page.click("#csw-go"); s.page.wait_for_timeout(700)
        ck("web chưa chạy SQL v67 → khách thấy 'Tính năng đang cập nhật', không lộ chữ kỹ thuật",
           (s.txt("#csw-err") or "").startswith("Tính năng đang cập nhật") and "SQL" not in (s.txt("#csw-err") or ""), s.txt("#csw-err"))
        s.ctx.close()

        print("3. đổi sang Android khác vẫn như cũ + máy mới ghi 'ở máy chủ khác'")
        s = Site(br, html); s.open_switch()
        s.page.click('#cpswdlg [data-swv="15"]'); s.page.check("#csw-ok"); s.page.wait_for_timeout(150)
        ck("nút 'Đổi sang Android 15'", s.txt("#csw-go") == "Đổi sang Android 15", s.txt("#csw-go"))
        s.page.click("#csw-go"); s.page.wait_for_timeout(800)
        ck("gọi cloudphone_switch_android(p_android 15), không gọi đổi máy chủ",
           s.calls("cloudphone_switch_android") == [{"p_id": "p-1", "p_android": "15"}] and not s.calls("cloudphone_change_server"))
        s.ctx.close()
        db = {"product_list": [], "products": [], "cloudphone_pricing": PRICING, "cloud_phones": [
            dict(PH[0], status="cancelling", switch_to="p-2", error="Đổi máy chủ: máy cũ đang bị xoá — xong tự tạo máy Android 12 ở máy chủ khác (2–5 phút)."),
            {"id": "p-2", "name": "Máy farm", "user_id": ME, "status": "pending", "android": "12", "ram": 4, "cpu": 4, "res": "720x1280", "fps": 30, "node": None,
             "replaces": "p-1", "avoid_node": "n1", "created_at": iso(-60), "expires_at": None, "is_free": False}]}
        s = Site(br, html, db); s.js("() => openCloud()"); s.page.wait_for_timeout(900)
        body = s.txt("#cp-list") or ""
        ck("máy mới (đơn tránh máy chủ cũ) hiện 'Máy cũ đã xoá — đang tạo máy Android 12 ở máy chủ khác'",
           "Máy cũ đã xoá — đang tạo máy Android 12 ở máy chủ khác" in body, body)
        s.shot("3-dang-doi-may-chu.png")
        s.ctx.close()

        print("4. số lượt còn lại đếm như SQL (kể cả máy đã đổi tiếp / đã xoá, chỉ 24 giờ gần nhất)")
        old_sw = [dict(PH[0], id="p-0a", status="cancelled", replaces="p-00", created_at=iso(-2 * 3600)),     # đổi lần 1 (máy đó đã đổi tiếp → đã xoá)
                  dict(PH[0], id="p-0b", status="cancelled", replaces="p-0z", created_at=iso(-30 * 3600))]    # quá 24 giờ → không tính
        db = {"product_list": [], "products": [], "cloudphone_pricing": PRICING,
              "cloud_phones": [dict(PH[0], replaces="p-0a", created_at=iso(-3600))] + old_sw}                 # máy đang dùng = đổi lần 2
        s = Site(br, html, db); s.open_switch()
        ck("đã đổi 2 lần trong 24 giờ (1 máy đã xoá) → 'Còn 1/3 lượt'", "Còn 1/3 lượt đổi trong 24 giờ" in (s.txt("#csw-left") or ""), s.txt("#csw-left"))
        cnt = s.js("() => (window.__FAKE.calls || []).filter(c => c.kind === 'from' && c.table === 'cloud_phones' && c.cols === 'id').length")
        ck("đọc số lượt thẳng từ bảng cloud_phones (không chỉ máy đang hiện)", cnt >= 1, cnt)
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt · ảnh: {SHOTS}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
