# -*- coding: utf-8 -*-
"""28/11 · SQL v70 — 📱 BlueReal (thuê điện thoại THẬT): dòng sản phẩm ở trang chủ · hộp thuê (mẫu + số ngày → giá / ngày × ngày) ·
   máy thật trong "Máy của tôi" (nhãn, ẩn đổi Android / nâng cấp / FPS / root / proxy, gia hạn theo giá mẫu) · admin › 📱 Máy thật
   (giá / ngày, thêm mẫu, máy đang cắm → thêm vào kho, Sẵn sàng / Bảo trì). Chrome thật (Playwright) + Supabase giả; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_bluereal.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
SHOTS = os.environ.get("SHOTS") or "/tmp/shots-bluereal"
ME = "00000000-0000-4000-8000-000000000001"
OK = FAIL = 0


def iso(sec): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


CAT = {"name": "BlueReal", "on": True, "max_days": 90, "models": [
    {"id": "s9", "name": "Galaxy S9", "android": "10", "ram": 4, "cpu": 8, "res": "1440x2960", "price_day": 5000, "note": "Samsung Galaxy S9", "stock": 0, "total": 1},
    {"id": "s10", "name": "Galaxy S10", "android": "12", "ram": 8, "cpu": 8, "res": "1440x3040", "price_day": 6000, "note": "Samsung Galaxy S10 · 8GB", "stock": 2, "total": 3}]}
ADM_STATE = {"name": "BlueReal", "on": True, "max_days": 90,
             "models": [dict(CAT["models"][0], active=True, sort=1, devices=1), dict(CAT["models"][1], active=True, sort=2, devices=3)],
             "devices": [{"id": "d1", "model_id": "s10", "label": "S10 #1", "node": "box1", "serial": "R58M10AAA", "status": "rented", "phone_id": "p-r", "online": True,
                          "last_seen": iso(-20), "battery": 88, "ended_at": None, "note": None,
                          "phone": {"id": "p-r", "name": "Máy farm thật", "status": "active", "expires_at": iso(86400 * 6), "user": "khach1"}},
                         {"id": "d2", "model_id": "s10", "label": "S10 #2", "node": "box1", "serial": "R58M10BBB", "status": "maint", "phone_id": None, "online": True,
                          "last_seen": iso(-30), "battery": 64, "ended_at": iso(-3600), "note": None, "phone": None}],
             "seen": [{"node": "box1", "serial": "R58M10CCC", "model": "SM_G973F", "battery": 91, "state": "device", "last_seen": iso(-10)},
                      {"node": "box1", "serial": "R58M10DDD", "model": "", "battery": None, "state": "unauthorized", "last_seen": iso(-10)}]}
PH_REAL = {"id": "p-r", "name": "Máy farm thật", "user_id": ME, "status": "active", "android": "12", "ram": 8, "cpu": 8, "res": "1440x3040", "fps": 30,
           "node": "box1", "container": "real_d1", "expires_at": iso(6 * 86400), "created_at": iso(-3600), "is_free": False, "stream_url": "x",
           "real_device": "d1", "real_model": "s10"}
HOOK = """(() => {
  window.__RL = { cat: %s, adm: %s, mode: 'ok', orders: [], renews: [], msave: [], dsave: [] };
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    realphone_catalog: () => window.__RL.mode === 'none' ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.realphone_catalog without parameters in the schema cache' } }
                                                         : JSON.parse(JSON.stringify(window.__RL.cat)),
    realphone_order: (a) => { window.__RL.orders.push(a); return window.__RL.mode === 'out' ? { data: null, error: { code: 'P0001', message: 'REAL_OUT: Galaxy S10 đang hết máy' } }
                                                                 : { id: 'p-new', status: 'pending', real_device: 'd3', real_model: a.p_model }; },
    realphone_renew: (a) => { window.__RL.renews.push(a); return { id: a.p_id, pending_renew_days: a.p_days }; },
    admin_real_state: () => window.__RL.mode === 'none' ? { data: null, error: { code: 'PGRST202', message: 'Could not find the function public.admin_real_state without parameters in the schema cache' } }
                                                        : JSON.parse(JSON.stringify(window.__RL.adm)),
    admin_real_model_save: (a) => { window.__RL.msave.push(a.p); return a.p; },
    admin_real_device_save: (a) => { window.__RL.dsave.push(a.p); return a.p; },
    cloudphone_status: () => ({ maint: false, online: true, free_ram: 80, free_cpu: 80, android: { '12': { free_ram: 40, free_cpu: 40, online: true } } }),
  }); })();""" % (json.dumps(CAT), json.dumps(ADM_STATE))


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


class Site:
    def __init__(self, browser, html, admin=False, path="/", mode="ok", phones=None):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {"product_list": [], "products": [], "cloud_phones": phones or [], "pc_machines": [],
                                       "cloudphone_pricing": [{"id": 1, "android_versions": "12", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32,
                                                               "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}]}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; %s window.__RL.mode = %s; try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
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
    def shot(self, name): os.makedirs(SHOTS, exist_ok=True); self.page.screenshot(path=os.path.join(SHOTS, name))
    def rich(self, n=500000):
        self.js("async (n) => { window.__FAKE.db.profiles[0].balance = n; await loadProfile(); }", n); self.page.wait_for_timeout(200)


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        print("1. trang chủ: dòng 📱 BlueReal")
        s = Site(br, html)
        s.js("async () => { await REALSHOP.load(true); renderGrid(); }"); s.page.wait_for_timeout(400)
        row = s.txt("#grid .m3-row.real") or ""
        ck("dòng 'Điện thoại thật · 📱 BlueReal' · từ 5.000đ/ngày · Còn máy · mẫu Galaxy S9 (hết) + Galaxy S10",
           "BlueReal" in row and "5.000" in row and "Còn máy" in row and "Galaxy S10" in row and "Galaxy S9" in row and "hết" in row, row)
        ck("mục lọc 'Máy thật' ở thanh danh mục", "Máy thật" in (s.txt("#cats") or ""), s.txt("#cats"))
        s.shot("1-trang-chu.png")
        print("2. hộp thuê")
        s.rich()
        s.page.click('#grid .m3-row.real button[data-realbuy]'); s.page.wait_for_timeout(500)
        dl = s.txt("#rldlg .dlg") or ""
        ck("mở hộp thuê: chọn sẵn Galaxy S10 (S9 hết máy → khoá) · 7 ngày = 42.000đ",
           s.js("() => document.querySelector('#rldlg [data-rlm=\"s10\"]').classList.contains('on') && document.querySelector('#rldlg [data-rlm=\"s9\"]').disabled")
           and "42.000" in dl and "6.000" in dl, dl)
        s.page.click('#rldlg [data-rld="3"]'); s.page.wait_for_timeout(200)
        ck("chọn 3 ngày → 18.000đ", "18.000" in (s.txt("#rldlg .dlg") or ""), s.txt("#rldlg .cpsum"))
        s.page.fill("#rl-name", "Máy farm thật"); s.page.click("#rl-go"); s.page.wait_for_timeout(800)
        ck("bấm Thuê ngay → realphone_order(p_model s10, p_days 3, p_name)", s.js("() => window.__RL.orders") == [{"p_model": "s10", "p_days": 3, "p_name": "Máy farm thật"}],
           s.js("() => window.__RL.orders"))
        ck("hộp đóng + báo đang chuẩn bị máy", s.js("() => document.getElementById('rldlg').hidden") is True)
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()
        s = Site(br, html, mode="out"); s.rich()
        s.js("async () => { await REALSHOP.load(true); }"); s.js("() => REALSHOP.buy('s10')"); s.page.wait_for_timeout(500)
        s.page.click("#rl-go"); s.page.wait_for_timeout(600)
        ck("vừa hết máy → báo 'vừa hết máy — chọn mẫu khác', hộp vẫn mở", "vừa hết máy" in (s.txt("#rl-err") or "") and not s.js("() => document.getElementById('rldlg').hidden"), s.txt("#rl-err"))
        s.ctx.close()
        s = Site(br, html); s.rich(1000)
        s.js("async () => { await REALSHOP.load(true); }"); s.js("() => REALSHOP.buy('s10')"); s.page.wait_for_timeout(500)
        ck("thiếu tiền → nút 'Nạp thêm tiền' + ghi số còn thiếu", "Nạp thêm tiền" in (s.txt("#rl-go") or "") and "thiếu" in (s.txt("#rldlg .dlg") or ""), s.txt("#rl-go"))
        s.ctx.close()

        print("3. máy thật trong 'Máy của tôi'")
        s = Site(br, html, phones=[PH_REAL]); s.rich()
        s.js("async () => { await REALSHOP.load(true); await openCloud(); }"); s.page.wait_for_timeout(900)
        card = s.txt("#cp-list .vmi") or ""
        ck("nhãn '📱 Máy thật · Galaxy S10' trên thẻ máy", "Máy thật · Galaxy S10" in card, card)
        btns = s.js("() => [...document.querySelectorAll('#cp-list .vmi [data-cpup], #cp-list .vmi [data-cpswitch], #cp-list .vmi [data-cpfps], #cp-list .vmi [data-cpdisk], #cp-list .vmi a[href*=\"root=1\"], #cp-list .vmi a[href*=\"proxy=1\"]')].length")
        ck("không có nút đổi Android / nâng cấp / FPS / bộ nhớ / root / proxy", btns == 0, btns)
        ck("vẫn có Mở máy · Gia hạn · Chia sẻ · Đổi tên", all(x in card for x in ("Gia hạn", "Chia sẻ", "Đổi tên")), card)
        s.page.click('#cp-list [data-cprenew="p-r"]'); s.page.wait_for_timeout(600)
        rd = s.txt("#rlrdlg .dlg") or ""
        ck("bấm Gia hạn → hộp gia hạn máy thật (giá theo Galaxy S10: 7 ngày = 42.000đ)", "Gia hạn máy thật" in rd and "42.000" in rd, rd)
        s.page.click('#rlrdlg [data-rld="15"]'); s.page.click("#rlr-go"); s.page.wait_for_timeout(600)
        ck("15 ngày → realphone_renew(p_id, 15)", s.js("() => window.__RL.renews") == [{"p_id": "p-r", "p_days": 15}], s.js("() => window.__RL.renews"))
        s.shot("3-may-cua-toi.png")
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()

        print("4. admin › 📱 Máy thật")
        s = Site(br, html, admin=True, path="/admin")
        s.js("() => document.querySelector('#adm-tabs button[data-tab=\"real\"]').click()"); s.page.wait_for_timeout(900)
        pane = s.txt("#rla") or ""
        ck("khung admin: mẫu máy (giá / ngày) · kho máy (S10 #1 đang thuê khach1, S10 #2 cần reset) · máy đang cắm (R58M10CCC kết nối, R58M10DDD chưa cho phép)",
           all(x in pane for x in ("Galaxy S10", "Giá / ngày", "S10 #1", "khach1", "Cần reset", "R58M10CCC", "unauthorized")), pane[:600])
        ck("nhóm 'Máy cho thuê' có thẻ 📱 Máy thật · huy hiệu 1 máy cần reset", s.js("() => document.getElementById('real-badge').textContent") == "1")
        s.page.fill('[data-rlmod="s10"] [data-k="price_day"]', "6.500"); s.page.click('[data-rlmsave="s10"]'); s.page.wait_for_timeout(500)
        ms = s.js("() => window.__RL.msave")
        ck("1 ô giá / ngày: sửa S10 = 6.500 → admin_real_model_save(price_day 6500)", ms and ms[-1]["id"] == "s10" and ms[-1]["price_day"] == "6500", ms)
        s.page.fill("#rla-nm", "Galaxy Note 10"); s.page.fill("#rla-np", "7000"); s.page.click("#rla-add"); s.page.wait_for_timeout(500)
        ms = s.js("() => window.__RL.msave")
        ck("thêm mẫu 'Galaxy Note 10' (mã tự tạo galaxy-note-10, giá 7000)", ms[-1]["id"] == "galaxy-note-10" and ms[-1]["price_day"] == "7000", ms[-1])
        s.js("() => { const r = document.querySelector('[data-rlseen=\"box1|R58M10CCC\"]'); r.querySelector('[data-k=\"model\"]').value = 's10'; r.querySelector('[data-k=\"label\"]').value = 'S10 #3'; }")
        s.page.click('[data-rlseen="box1|R58M10CCC"] [data-rladd]'); s.page.wait_for_timeout(500)
        ds = s.js("() => window.__RL.dsave")
        ck("máy đang cắm → ➕ Thêm: admin_real_device_save(s10, S10 #3, box1, R58M10CCC, Sẵn sàng)",
           ds and ds[-1] == {"model_id": "s10", "label": "S10 #3", "node": "box1", "serial": "R58M10CCC", "status": "ready"}, ds)
        s.page.click('[data-rldev="d2"] [data-rlst="ready"]'); s.page.wait_for_timeout(500)
        ck("máy cần reset → ✅ Sẵn sàng", s.js("() => window.__RL.dsave")[-1] == {"id": "d2", "status": "ready"})
        ck("máy đang có khách thuê không có nút đổi trạng thái / xoá", s.js("() => document.querySelectorAll('[data-rldev=\"d1\"] [data-rlst], [data-rldev=\"d1\"] [data-rldel]').length") == 0)
        s.shot("4-admin.png")
        ck("không lỗi trang", not s.errors, s.errors)
        s.ctx.close()
        s = Site(br, html, admin=True, path="/admin", mode="none")
        s.js("() => document.querySelector('#adm-tabs button[data-tab=\"real\"]').click()"); s.page.wait_for_timeout(700)
        ck("chưa chạy SQL v70 → admin thấy 'Chưa chạy SQL v70'", "Chưa chạy SQL v70" in (s.txt("#rla") or ""), s.txt("#rla"))
        s.ctx.close()
        s = Site(br, html, mode="none")
        s.js("async () => { await REALSHOP.load(true); renderGrid(); }"); s.page.wait_for_timeout(300)
        ck("chưa chạy SQL v70 → trang chủ không hiện dòng BlueReal, không lỗi", s.js("() => !document.querySelector('#grid .m3-row.real')") and not s.errors, s.errors)
        s.ctx.close()
        br.close()
    play = open(os.path.join(os.path.dirname(HTML), "play.html"), encoding="utf-8").read()
    ck("play.html máy thật: ẩn Root · Proxy · kho app · khởi động lại · xoay · tab cửa sổ (thanh trên + menu) — cpapi 28/11e cũng chặn",
       all(x in play for x in ('body.realm #menu [data-a="root"]', 'body.realm #menu [data-a="proxy"]', 'body.realm #menu [data-a="store"]',
                               'body.realm #menu [data-a="reboot"]', 'body.realm #menu [data-a="rotate"]', 'body.realm .bar [data-a="winmini"]',
                               'body.realm #menu [data-a^="win"]')) and "realCheck(P.id)" in play)
    print(f"\n{OK}/{OK + FAIL} đạt · ảnh: {SHOTS}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
