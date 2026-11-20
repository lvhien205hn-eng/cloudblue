# -*- coding: utf-8 -*-
"""Thử thẻ "💻 Máy PC" của trang quản trị bằng Chrome thật (Playwright) + Supabase giả.
   python3 test_web_pc.py <index gốc (chưa gắn)> <index đã gắn> [thư mục ghi ảnh chụp]
   Gắn bằng:  python3 patch_web_pc.py <index gốc> <index đã gắn>
   Mọi yêu cầu mạng đều bị chặn và trả lời tại chỗ — không gọi ra ngoài."""
import datetime, json, os, re, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
WINPC = os.path.join(HERE, "..", "..")
BASE_HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WINPC, "..", "..", "web", "index.base.html")
NEW_HTML = sys.argv[2] if len(sys.argv) > 2 else os.path.join(WINPC, "..", "..", "web", "index.html")
SHOTS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(NEW_HTML)), "shots")
os.makedirs(SHOTS, exist_ok=True)
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def read(p, mode="r"):
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f: return f.read()


def iso(sec_ago):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=sec_ago)).isoformat()


A, B, C, X, Y = ["00000000-0000-4000-8000-0000000000a%d" % i for i in range(1, 6)]
INFO_OK = {"host": "CB-A1B2C3", "os": "22h2", "os_ver": "10.0.19045.2965", "agent": "20.11a", "cpu": "Intel(R) Core(TM) i5-9400F CPU @ 2.90GHz", "cores": 6,
           "ram_gb": 15.9, "gpus": ["NVIDIA GeForce GTX 1650"], "lan_ip": "192.168.1.50", "fw": "uefi", "board": "ASUS PRIME B365M-A",
           "disks": [{"model": "KINGSTON SA400", "gb": 240, "bus": "SATA", "ssd": True}], "rec": {"ok": True, "images": ["22h2", "1511"], "ver": "20.11a"}}


def make_db():
    evil = {"host": "\"><svg onload=window.__xss=2>", "cpu": {"a": 1}, "cores": "abc", "ram_gb": "<b>", "gpus": "not-array", "board": ["a"], "agent": {"x": 1},
            "disks": [None, 5, {"gb": "<i>", "ssd": "x"}], "rec": {"ok": True, "images": "22h2"}, "sec": {"std": "<img src=x onerror=window.__xss=10>", "hard": "<b>", "lock": 1}}
    evil2 = {"host": "H", "cpu": "<img src=x onerror=window.__xss=4>", "cores": 4, "ram_gb": 8, "gpus": ["<img src=x onerror=window.__xss=5>", {"z": 1}], "agent": "<b>9</b>",
             "board": "<img src=x onerror=window.__xss=6>", "disks": [{"gb": 500, "ssd": False}], "rec": {"ok": True, "images": ["22h2", "<img src=x onerror=window.__xss=7>", "1511"]}}
    return {
        "pc_settings": [{"id": 1, "enroll_hash": None, "enroll_made_at": None, "auto_approve": False, "agent": {}, "poll_s": 30}],
        "pc_machines": [
            {"id": A, "name": "CB-A1B2C3", "code": None, "note": None, "approved": False, "status": "new", "os": "22h2", "os_ver": "10.0.19045.2965", "info": INFO_OK,
             "lan_ip": "192.168.1.50", "pub_ip": "1.54.69.205", "first_seen": iso(300), "last_seen": iso(10), "enrolled_at": iso(300), "reenroll_until": None, "created_at": iso(300)},
            {"id": B, "name": "Máy 14-85", "code": "A · 14-85", "note": "kệ 2, hàng trên", "approved": True, "status": "ready", "os": "1511", "os_ver": "10.0.10586.0",
             "info": dict(INFO_OK, host="CB-B", os="1511", disks=[{"gb": 480, "ssd": True}, {"gb": 2000, "ssd": False}], sec={"std": True, "hard": True, "lock": True}),
             "lan_ip": "192.168.1.51", "pub_ip": "1.54.69.205", "first_seen": iso(90000), "last_seen": iso(20), "enrolled_at": iso(4000), "reenroll_until": None, "created_at": iso(90000)},
            {"id": C, "name": "Máy khách Tèo", "code": None, "note": None, "approved": True, "status": "rented", "os": "22h2", "os_ver": "10.0.19045.1", "info": dict(INFO_OK, host="Máy khách Tèo", rec={"ok": False, "images": []}, sec={"std": False, "hard": False, "lock": True}),
             "lan_ip": "192.168.1.52", "pub_ip": "1.54.69.205", "first_seen": iso(200000), "last_seen": iso(3 * 3600), "enrolled_at": iso(200000), "reenroll_until": None, "created_at": iso(200000)},
            {"id": X, "name": "<img src=x onerror=\"window.__xss=1\">", "code": "<b>c</b>", "note": "<script>window.__xss=8</script>", "approved": True, "status": "maint", "os": "<script>window.__xss=3</script>",
             "os_ver": 12345, "info": evil, "lan_ip": "<u>ip</u>", "pub_ip": None, "first_seen": iso(500), "last_seen": iso(30), "enrolled_at": iso(500), "reenroll_until": None, "created_at": iso(250)},
            {"id": Y, "name": "May-Y", "code": None, "note": None, "approved": True, "status": "ready", "os": None, "os_ver": None, "info": evil2,
             "lan_ip": None, "pub_ip": None, "first_seen": iso(400), "last_seen": None, "enrolled_at": iso(400), "reenroll_until": None, "created_at": iso(200)},
        ],
        "pc_orders": [
            {"id": 11, "pc_id": B, "cmd": "reinstall", "args": {"os": "1511", "wipe": "all"}, "state": "done", "result": {"os": "1511", "secs": 742, "msg": "xong"}, "created_at": iso(5000), "sent_at": iso(4990), "done_at": iso(4000)},
            {"id": 12, "pc_id": C, "cmd": "reinstall", "args": {"os": "1511", "wipe": "system"}, "state": "failed", "result": {"msg": "May nay chua co phan vung cuu ho CloudBlue <b>x</b>"}, "created_at": iso(9000), "sent_at": iso(8990), "done_at": iso(8900)},
            {"id": 13, "pc_id": X, "cmd": "reboot", "args": "chuoi-la", "state": "failed", "result": "<img src=x onerror=window.__xss=9>", "created_at": iso(700), "sent_at": iso(690), "done_at": iso(600)},
            {"id": 14, "pc_id": Y, "cmd": "reinstall", "args": {"os": {"a": 1}, "wipe": "constructor"}, "state": "done", "result": {"msg": {"a": 1}, "secs": "<i>"}, "created_at": iso(800), "sent_at": iso(790), "done_at": iso(600)},
        ],
    }


QR_STUB = "window.qrcode=function(){return{addData(){},make(){},getModuleCount(){return 0},isDark(){return false},createSvgTag(){return ''},createImgTag(){return ''},createDataURL(){return ''}}};"
MANIFEST = json.loads(read(os.path.join(WINPC, "manifest.json")))


class Site:
    """1 trang quản trị mở trong Chrome, mọi yêu cầu mạng trả lời tại chỗ."""

    def __init__(self, browser, html, init, mobile=False, path="/admin"):
        self.errors, self.dialogs, self.accept, self.manifest, self.unrouted = [], [], True, MANIFEST, []
        vp = {"width": 390, "height": 800} if mobile else {"width": 1360, "height": 900}
        self.ctx = browser.new_context(viewport=vp, locale="vi-VN", permissions=["clipboard-read", "clipboard-write"])
        self.ctx.add_init_script("window.__FAKE_INIT = %s; try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}" % json.dumps(init))
        self.page = self.ctx.new_page()
        self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.on("dialog", self.on_dialog)
        self.page.goto(ORIGIN + path, wait_until="load")

    def on_dialog(self, d):
        self.dialogs.append(d.message)
        d.accept() if self.accept else d.dismiss()

    def route(self, route):
        u = route.request.url
        if u in (ORIGIN + "/admin", ORIGIN + "/"):
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u:
            return route.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js")))
        if "qrcode" in u:
            return route.fulfill(status=200, content_type="application/javascript", body=QR_STUB)
        if "raw.githubusercontent.com" in u and "/winpc/manifest.json" in u:
            if self.manifest is None: return route.fulfill(status=404, content_type="text/plain", body="404: Not Found")
            return route.fulfill(status=200, content_type="text/plain; charset=utf-8", body=json.dumps(self.manifest), headers={"access-control-allow-origin": "*"})
        if u.startswith(ORIGIN + "/download/") or u.startswith(ORIGIN + "/api/"):
            return route.fulfill(status=404, content_type="application/json", body="{}")
        if re.search(r"\.(png|jpg|jpeg|svg|webp|ico|mp4|woff2?|ttf|webmanifest)(\?|$)", u) or "fonts.g" in u:
            return route.fulfill(status=204, body="")
        self.unrouted.append(u)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg)

    def calls(self, name):
        return self.js("n => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)

    def wait_admin(self):
        self.page.wait_for_function("() => !document.getElementById('drawer').hidden", timeout=15000)
        self.page.wait_for_timeout(400)

    def tab(self, t):
        self.page.click('#adm-tabs button[data-tab="%s"]' % t)
        self.page.wait_for_timeout(250)

    def settle(self):
        self.page.wait_for_function("() => !window.PCA || !window.PCA.busy", timeout=5000)
        self.page.wait_for_timeout(120)

    def rows(self):
        return self.js("() => [...document.querySelectorAll('#pctbl tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")

    def close(self):
        self.ctx.close()


def tour(site, tabs):
    site.wait_admin()
    for t in tabs:
        site.tab(t)
    site.page.wait_for_timeout(600)
    return sorted(set(site.errors))


def main():
    base, new = read(BASE_HTML), read(NEW_HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox", "--disable-gpu"])
        TABS = ["stats", "ord", "prod", "cust", "tx", "sec", "cloud", "vps", "biz", "promo", "site"]

        print("1. Trang gốc và trang đã gắn: không thêm lỗi nào")
        s0 = Site(br, base, {"admin": True, "v41": True, "db": make_db()}); e0 = tour(s0, TABS); u0 = set(s0.unrouted); s0.close()
        s = Site(br, new, {"admin": True, "v41": True, "db": make_db()}); e1 = tour(s, TABS + ["pc"] + TABS[:3] + ["pc"])
        ck("trang gốc mở được bảng quản trị (bộ thử chạy đúng)", True)
        ck("trang đã gắn: không có lỗi mới so với trang gốc", [x for x in e1 if x not in e0] == [], [x for x in e1 if x not in e0])
        print("     (lỗi sẵn có của trang gốc trong môi trường thử: %d)" % len(e0))
        ck("không gọi thêm địa chỉ mạng nào so với trang gốc", sorted(set(s.unrouted) - u0) == [], sorted(set(s.unrouted) - u0)[:5])

        print("2. Thẻ Máy PC: hiện / ẩn đúng")
        s.tab("pc"); s.settle()
        ck("bấm thẻ → hiện pane-pc, nút thẻ sáng", s.js("() => !document.getElementById('pane-pc').hidden && document.querySelector('#adm-tabs button[data-tab=pc]').classList.contains('on')"))
        ck("các pane khác đều ẩn", s.js("() => [...document.querySelectorAll('#drawer .dbody')].filter(p => !p.hidden).map(p => p.id)") == ["pane-pc"])
        s.tab("vps")
        ck("sang thẻ khác → pane-pc ẩn, thẻ PC tắt sáng", s.js("() => document.getElementById('pane-pc').hidden && !document.querySelector('#adm-tabs button[data-tab=pc]').classList.contains('on') && !document.getElementById('pane-vps').hidden"))
        s.tab("sec")
        ck("thẻ Bảo mật vẫn chạy đúng", s.js("() => !document.getElementById('pane-sec').hidden && document.getElementById('pane-pc').hidden"))
        s.tab("pc"); s.settle()
        ck("không báo thiếu SQL", s.js("() => document.getElementById('pca-miss').hidden"))

        print("3. Số liệu + bảng")
        tiles = s.js("() => ['pk-total','pk-on','pk-new','pk-busy'].map(i => document.getElementById(i).textContent)")
        ck("ô số: 5 máy · 3 online · 1 chờ duyệt · 0 đang cài", tiles == ["5", "3", "1", "0"], tiles)
        ck("huy hiệu thẻ = 1 máy chờ duyệt", s.js("() => { const b = document.getElementById('pc-badge'); return !b.hidden && b.textContent === '1'; }"))
        rows = s.rows()
        ck("đủ 5 dòng máy", len(rows) == 5, rows)
        ra = next(r for r in rows if r.startswith("CB-A1B2C3"))
        ck("dòng máy mới: online, chờ duyệt, cấu hình gọn", all(k in ra for k in ["● online", "Chờ duyệt", "22H2", "agent 20.11a", "đổi được: 22H2, 1511", "Intel Core i5-9400F @ 2.90GHz · 6 luồng", "16GB RAM · ASUS PRIME B365M-A", "NVIDIA GeForce GTX 1650", "240GB SSD", "192.168.1.50", "Duyệt"]), ra)
        rb = next(r for r in rows if r.startswith("Máy 14-85"))
        ck("dòng máy trong kho: mã shop, ghi chú, 2 ổ, lệnh đã xong", all(k in rb for k in ["A · 14-85", "kệ 2, hàng trên", "Windows: CB-B", "Sẵn sàng", "1511", "480GB SSD + 2000GB HDD", "✓ Cài lại 1511 (dọn sạch cả máy)", "12 phút"]) and "Duyệt" not in rb, rb)
        rc = next(r for r in rows if r.startswith("Máy khách Tèo"))
        ck("dòng máy đang thuê: offline, không cứu hộ, lệnh lỗi có lý do", all(k in rc for k in ["○ offline", "3 giờ trước", "Đang thuê", "⚠ không có phân vùng cứu hộ", "✗ Cài lại 1511 (chỉ phân vùng Windows)", "May nay chua co phan vung cuu ho CloudBlue <b>x</b>"]) and "Windows:" not in rc, rc)

        print("4. Dữ liệu lạ từ máy cho thuê không chạy được mã, không làm hỏng bảng")
        ck("không đoạn mã nào chạy (window.__xss trống)", s.js("() => window.__xss") is None, s.js("() => window.__xss"))
        ck("không thẻ lạ nào lọt vào bảng", s.js("() => document.querySelectorAll('#pctbl img, #pctbl svg, #pctbl script, #pctbl u, #pctbl i').length") == 0)
        rx = next(r for r in rows if "onerror=\"window.__xss=1\"" in r)
        ck("tên máy độc in ra dạng chữ", rx.startswith("<img src=x onerror=\"window.__xss=1\">") and "<b>c</b>" in rx and "Bảo trì" in rx, rx)
        ck("thông tin sai kiểu → bỏ qua, không vỡ dòng", "chưa có thông tin" not in rx and "?GB" in rx and "⚠ không có phân vùng cứu hộ" in rx and "12345" in rx and "✗ Khởi động lại" in rx and "không rõ lý do" in rx, rx)
        ry = next(r for r in rows if r.startswith("May-Y"))
        ck("chuỗi độc trong CPU / card / bo mạch in dạng chữ; tên bản Windows lạ bị loại", "<img src=x onerror=window.__xss=4>" in ry and "đổi được: 22H2, 1511" in ry and "window.__xss=7" not in ry and "chưa từng" in ry and "agent <b>9</b>" in ry, ry)
        ck("lệnh có tham số lạ vẫn in được", "✓ Cài lại (?)" in ry, ry)

        print("5. Tìm kiếm")
        s.page.fill("#pcq", "14-85"); s.page.wait_for_timeout(100)
        ck("tìm theo mã shop", [r[:9] for r in s.rows()] == ["Máy 14-85"], s.rows())
        s.page.fill("#pcq", "192.168.1.52"); s.page.wait_for_timeout(100)
        ck("tìm theo IP", len(s.rows()) == 1 and s.rows()[0].startswith("Máy khách Tèo"))
        s.page.fill("#pcq", "cb-b"); s.page.wait_for_timeout(100)
        ck("tìm theo tên Windows của máy", len(s.rows()) == 1 and s.rows()[0].startswith("Máy 14-85"))
        s.page.fill("#pcq", "khong-co-may-nay"); s.page.wait_for_timeout(100)
        ck("không khớp → báo rõ", s.rows() == ["Không có máy nào khớp."], s.rows())
        s.page.fill("#pcq", ""); s.page.wait_for_timeout(100)
        ck("xoá ô tìm → đủ 5 máy", len(s.rows()) == 5)

        print("6. Duyệt máy")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="approve"]' % A); s.settle()
        ck("gọi pc_admin_set approved=true", s.calls("pc_admin_set") == [{"p_id": A, "p_patch": {"approved": True}}], s.calls("pc_admin_set"))
        ra = next(r for r in s.rows() if r.startswith("CB-A1B2C3"))
        ck("dòng chuyển Sẵn sàng, hết nút Duyệt, huy hiệu tắt", "Sẵn sàng" in ra and "Duyệt" not in ra and s.js("() => document.getElementById('pc-badge').hidden") and s.js("() => document.getElementById('pk-new').textContent") == "0", ra)
        ck("có thông báo", "Đã duyệt máy CB-A1B2C3." in s.js("() => document.getElementById('toast').textContent"))

        print("6b. Tình trạng bảo mật của máy + nút Bàn giao khách mới")
        rb, rc_, ra = (next(r for r in s.rows() if r.startswith(n)) for n in ("Máy 14-85", "Máy khách Tèo", "CB-A1B2C3"))
        ck("máy đã khoá (agent báo std + hard + lock) → dòng 🔒; máy khách là Admin → dòng ⚠; agent cũ không báo → không có dòng nào",
           "🔒 đã khoá · khách dùng tài khoản thường" in rb and "⚠ khách có quyền Admin trên máy" in rc_ and "🔒" not in ra and "đang khoá" not in ra and "quyền Admin" not in ra, (rb, rc_, ra))
        rx2 = next(r for r in s.rows() if "onerror=\"window.__xss=1\"" in r)
        ck("máy gửi tình trạng bảo mật sai kiểu / kèm mã → chỉ hiện 'đang khoá', không chạy mã", "⏳ đang khoá bảo mật" in rx2 and s.js("() => window.__xss") is None, rx2)
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="handover"]' % B); s.page.wait_for_timeout(150)
        ck("nút 🧼 Bàn giao mở hộp 'Bàn giao khách mới': chọn sẵn DỌN SẠCH CẢ MÁY, chọn được bản Windows, nút ghi 'Xoá sạch + cài lại'",
           s.js("() => document.getElementById('pcrd-title').textContent") == "Bàn giao khách mới — Máy 14-85" and s.js("() => document.querySelector('#pcrd-wipe input:checked').value") == "all"
           and s.js("() => [...document.getElementById('pcrd-os').options].map(o => o.value).join()") == "22h2,1511" and s.js("() => document.getElementById('pcrd-go').textContent") == "Xoá sạch + cài lại"
           and "Xoá sạch mọi ổ cứng" in s.js("() => document.getElementById('pcrd-info').textContent"))
        s.accept = False; s.dialogs.clear(); s.page.select_option("#pcrd-os", "22h2"); s.page.click("#pcrd-go"); s.page.wait_for_timeout(200)
        ck("bàn giao: hỏi lại rõ ràng (xoá sạch máy rồi cài Windows 22H2); Huỷ thì không gửi gì", len(s.dialogs) == 1 and 'BÀN GIAO KHÁCH MỚI — xoá sạch máy "Máy 14-85" rồi cài Windows 22H2?' in s.dialogs[0]
           and "dọn sạch cả máy" in s.dialogs[0] and s.calls("pc_admin_order") == [], s.dialogs)
        s.accept = True; s.page.click("#pcrd-cancel")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="handover"]' % C); s.page.wait_for_timeout(150)
        ck("bàn giao máy đang ghi 'đang thuê': vẫn chọn sẵn dọn sạch cả máy (khác nút Cài lại); máy không có cứu hộ thì nút khoá", s.js("() => document.querySelector('#pcrd-wipe input:checked').value") == "all"
           and s.js("() => document.getElementById('pcrd-go').disabled"))
        s.page.click("#pcrd-cancel")

        print("7. Cài lại / đổi Windows")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="reinstall"]' % B); s.page.wait_for_timeout(150)
        ck("hộp nằm TRÊN bảng quản trị (bấm được)", s.js("() => { const m = document.getElementById('pcrdlg'), r = m.querySelector('.dlg').getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + 16); return !!el && m.contains(el); }"))
        ck("mở hộp cài lại, liệt kê đúng 2 bản, chọn sẵn bản đang chạy; tiêu đề + nút trở về kiểu 'Cài lại'", s.js("() => !document.getElementById('pcrdlg').hidden && [...document.getElementById('pcrd-os').options].map(o => o.value + (o.selected ? '*' : '')).join()") == "22h2,1511*"
           and s.js("() => document.getElementById('pcrd-title').textContent") == "Cài lại Windows — Máy 14-85" and s.js("() => document.getElementById('pcrd-go').textContent") == "Cài lại")
        ck("máy trong kho → mặc định dọn sạch cả máy", s.js("() => document.querySelector('#pcrd-wipe input:checked').value") == "all")
        ck("có cảnh báo mất dữ liệu, nút bấm được", "không lấy lại được" in s.js("() => document.getElementById('pcrd-warn').innerText") and not s.js("() => document.getElementById('pcrd-go').disabled"))
        s.accept = False; s.dialogs.clear()
        s.page.click("#pcrd-go"); s.page.wait_for_timeout(200)
        ck("bấm Cài lại → hỏi lại; chọn Huỷ thì không gửi gì", len(s.dialogs) == 1 and "CÀI LẠI máy \"Máy 14-85\" sang Windows 1511" in s.dialogs[0] and "dọn sạch cả máy" in s.dialogs[0] and s.calls("pc_admin_order") == [], s.dialogs)
        s.accept = True
        s.page.select_option("#pcrd-os", "22h2"); s.page.check('#pcrd-wipe input[value="disk"]')
        s.page.click("#pcrd-go"); s.settle()
        ck("đồng ý → gửi đúng lệnh (22h2, cả ổ hệ thống)", s.calls("pc_admin_order") == [{"p_id": B, "p_cmd": "reinstall", "p_args": {"os": "22h2", "wipe": "disk"}}], s.calls("pc_admin_order"))
        ck("hộp đóng", s.js("() => document.getElementById('pcrdlg').hidden"))
        rb = next(r for r in s.rows() if r.startswith("Máy 14-85"))
        ck("dòng hiện lệnh đang chờ + nút Huỷ, nút Cài lại bị khoá, ô 'đang cài' = 1", "⏳ Cài lại 22H2 (cả ổ hệ thống)" in rb and "chờ máy nhận" in rb and "Huỷ lệnh" in rb
           and s.js("() => document.querySelector('#pctbl tr[data-pc=\"%s\"] [data-pca=reinstall]').disabled" % B) and s.js("() => document.getElementById('pk-busy').textContent") == "1", rb)
        ck("vé cài lại không nằm trong dữ liệu của trang", "ticket" not in json.dumps(s.js("() => window.PCA.orders")) and "ticket" in json.dumps(s.js("() => window.__FAKE.db.pc_orders")))
        s.dialogs.clear()
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="cancel"]' % B); s.settle()
        oid = s.js("() => window.__FAKE.seq")
        ck("huỷ lệnh → hỏi lại + gọi pc_admin_order_cancel", len(s.dialogs) == 1 and "Huỷ lệnh này?" in s.dialogs[0] and s.calls("pc_admin_order_cancel") == [{"p_order": oid}], s.calls("pc_admin_order_cancel"))
        rb = next(r for r in s.rows() if r.startswith("Máy 14-85"))
        ck("dòng báo đã huỷ, nút Cài lại mở lại", "Cài lại 22H2 (cả ổ hệ thống) — đã huỷ" in rb and not s.js("() => document.querySelector('#pctbl tr[data-pc=\"%s\"] [data-pca=reinstall]').disabled" % B), rb)

        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="reinstall"]' % C); s.page.wait_for_timeout(150)
        ck("máy không có phân vùng cứu hộ → báo rõ, nút Cài lại khoá", "không có phân vùng cứu hộ" in s.js("() => document.getElementById('pcrd-warn').innerText") and s.js("() => document.getElementById('pcrd-go').disabled"))
        ck("máy đang thuê → mặc định chỉ cài lại phân vùng Windows", s.js("() => document.querySelector('#pcrd-wipe input:checked').value") == "system")
        s.page.click("#pcrd-cancel")
        ck("nút Đóng đóng hộp", s.js("() => document.getElementById('pcrdlg').hidden"))
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="reinstall"]' % X); s.page.wait_for_timeout(150)
        ck("máy gửi danh sách bản Windows sai kiểu → coi như không cài lại được", s.js("() => document.getElementById('pcrd-go').disabled && document.getElementById('pcrd-os').options.length === 0"))
        s.page.keyboard.press("Escape"); s.page.wait_for_timeout(150)
        ck("phím Esc đóng hộp (theo cách chung của trang)", s.js("() => document.getElementById('pcrdlg').hidden"))
        s.page.goto(ORIGIN + "/admin", wait_until="load"); s.wait_admin(); s.tab("pc"); s.settle()         # Esc đóng luôn bảng quản trị → mở lại
        ck("mở lại trang: dữ liệu giữ nguyên (máy A đã duyệt là do CSDL giả giữ trong trang cũ — trang mới nạp lại từ đầu)", len(s.rows()) == 5)

        print("8. Sửa máy + lệnh nhanh")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % B); s.page.wait_for_timeout(150)
        ck("hộp Sửa nằm TRÊN bảng quản trị", s.js("() => { const m = document.getElementById('pcadlg'), r = m.querySelector('.dlg').getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + 16); return !!el && m.contains(el); }"))
        ck("hộp Sửa điền sẵn thông tin", s.js("() => [document.getElementById('pcad-name').value, document.getElementById('pcad-code').value, document.getElementById('pcad-note').value, document.getElementById('pcad-status').value]") == ["Máy 14-85", "A · 14-85", "kệ 2, hàng trên", "ready"])
        s.page.fill("#pcad-name", "   "); s.page.click("#pcad-save"); s.page.wait_for_timeout(150)
        ck("tên trống → báo, không gửi", s.js("() => document.getElementById('pcad-err').textContent") == "Nhập tên máy." and s.calls("pc_admin_set") == [])
        s.page.fill("#pcad-name", "Máy 14-86"); s.page.fill("#pcad-code", "B · 01"); s.page.fill("#pcad-note", ""); s.page.select_option("#pcad-status", "rented")
        s.page.click("#pcad-save"); s.settle()
        ck("lưu → gọi pc_admin_set đúng nội dung", s.calls("pc_admin_set") == [{"p_id": B, "p_patch": {"name": "Máy 14-86", "code": "B · 01", "note": "", "status": "rented", "approved": True}}], s.calls("pc_admin_set"))
        rb = next((r for r in s.rows() if r.startswith("Máy 14-86")), "")
        ck("bảng cập nhật tên / mã / trạng thái", "B · 01" in rb and "Đang thuê" in rb and "kệ 2" not in rb, rb)
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % A); s.page.wait_for_timeout(150)
        s.page.select_option("#pcad-status", "new"); s.page.click("#pcad-save"); s.settle()
        ck("đưa về 'Chờ duyệt' → bỏ duyệt luôn", s.calls("pc_admin_set")[-1] == {"p_id": A, "p_patch": {"name": "CB-A1B2C3", "code": "", "note": "", "status": "new", "approved": False}}, s.calls("pc_admin_set")[-1])
        for act, word in (("reboot", "KHỞI ĐỘNG LẠI máy \"Máy 14-86\"?"), ("shutdown", "TẮT máy \"Máy 14-86\"?")):
            s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % B); s.page.wait_for_timeout(150)
            s.dialogs.clear(); s.page.click('#pcadlg [data-pcact="%s"]' % act); s.settle()
            ck("nút %s → hỏi lại + gửi lệnh" % act, len(s.dialogs) == 1 and word in s.dialogs[0] and s.calls("pc_admin_order")[-1] == {"p_id": B, "p_cmd": act, "p_args": {}} and s.js("() => document.getElementById('pcadlg').hidden"), s.dialogs)
            oid = s.js("() => window.__FAKE.seq"); s.js("id => { const o = window.__FAKE.db.pc_orders.find(x => x.id === id); o.state = 'done'; o.done_at = new Date().toISOString(); }", oid)
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % C); s.page.wait_for_timeout(150)
        s.dialogs.clear(); s.page.click('#pcadlg [data-pcact="reboot"]'); s.settle()
        ck("máy offline → lời hỏi có nhắc 'lệnh sẽ chạy khi máy online lại'", "Máy đang offline" in s.dialogs[0], s.dialogs)
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % C); s.page.wait_for_timeout(150)
        s.dialogs.clear(); s.page.click('#pcadlg [data-pcact="reenroll"]'); s.settle()
        ck("cho đăng ký lại → hỏi lại + gọi pc_admin_allow_reenroll 6 giờ", "đăng ký lại KHÔNG cần mã trong 6 giờ" in s.dialogs[0] and s.calls("pc_admin_allow_reenroll") == [{"p_id": C, "p_hours": 6}], s.dialogs)
        s.dialogs.clear(); s.page.click('#pcadlg [data-pcact="delete"]'); s.settle()
        ck("xoá máy → hỏi lại + gọi pc_admin_delete, bảng còn 4 dòng", "XOÁ máy \"Máy khách Tèo\"" in s.dialogs[0] and s.calls("pc_admin_delete") == [{"p_id": C}] and len(s.rows()) == 4 and s.js("() => document.getElementById('pcadlg').hidden"), s.rows())
        s.js("() => { window.__FAKE.failRpc.pc_admin_order = 'BUSY'; }")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % B); s.page.wait_for_timeout(150)
        s.page.click('#pcadlg [data-pcact="reboot"]'); s.settle()
        ck("máy chủ báo BUSY → hiện câu dễ hiểu, hộp vẫn mở", "đang có lệnh cài lại chưa xong" in s.js("() => document.getElementById('toast').textContent") and not s.js("() => document.getElementById('pcadlg').hidden"))
        s.js("() => { window.__FAKE.failRpc = {}; }"); s.page.click("#pcad-cancel")

        print("9. Mã đăng ký + lệnh tạo ISO")
        ck("chưa có mã → báo 'đang đóng', không có nút Tắt mã", "đang đóng" in s.js("() => document.getElementById('pca-keyst').innerText") and s.js("() => document.getElementById('pca-keyoff').hidden"))
        s.dialogs.clear(); s.page.click("#pca-newkey"); s.settle()
        key = s.js("() => document.getElementById('pca-keyval').value")
        ck("tạo mã lần đầu: không hỏi lại, hiện mã cbpc_ 1 lần + hiện luôn lệnh tạo ISO", s.dialogs == [] and re.fullmatch(r"cbpc_[0-9a-f]{40}", key or "") is not None
           and s.js("() => !document.getElementById('pca-keybox').hidden && !document.getElementById('pca-cmdbox').hidden"), key)
        ck("trạng thái: đang nhận máy mới + có nút Tắt mã", "đang nhận máy mới" in s.js("() => document.getElementById('pca-keyst').innerText") and not s.js("() => document.getElementById('pca-keyoff').hidden"))
        s.page.click("#pca-keycopy"); s.page.wait_for_timeout(150)
        ck("nút Copy mã → mã vào bộ nhớ tạm", s.js("() => navigator.clipboard.readText()") == key)
        cmd = s.js("() => document.getElementById('pca-cmd').value")
        want = ('$d = "$env:TEMP\\cb-tao-iso.ps1"; Remove-Item $d -Force -ErrorAction SilentlyContinue; curl.exe -fsSL -o $d '
                '"https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/winpc/tao-iso.ps1?t=$(Get-Random)"; '
                "if (-not ((Test-Path $d) -and (Select-String -Path $d -Pattern 'cloudblue-tao-iso' -SimpleMatch -Quiet))) "
                "{ Write-Host 'Chua tai duoc tao-iso.ps1 - thu lai sau 1 phut' -ForegroundColor Red } else { Set-ExecutionPolicy -Scope Process Bypass -Force; & $d }")
        ck("lệnh tạo ISO đúng từng ký tự, 1 dòng, không chứa mã đăng ký", cmd == want and "\n" not in cmd and "cbpc_" not in cmd, cmd)
        s.page.click("#pca-cmdcopy"); s.page.wait_for_timeout(150)
        ck("nút Copy lệnh → lệnh vào bộ nhớ tạm", s.js("() => navigator.clipboard.readText()") == want)
        s.page.click("#pca-showcmd"); ck("nút 'Lệnh tạo ISO' ẩn / hiện khung lệnh", s.js("() => document.getElementById('pca-cmdbox').hidden"))
        s.accept = False; s.dialogs.clear(); s.page.click("#pca-newkey"); s.settle()
        ck("đã có mã → tạo mã mới phải hỏi lại; Huỷ thì giữ mã cũ", len(s.dialogs) == 1 and "Mã cũ hết dùng ngay" in s.dialogs[0] and len(s.calls("pc_admin_new_key")) == 1)
        s.accept = True; s.dialogs.clear(); s.page.click("#pca-keyoff"); s.settle()
        ck("tắt mã → hỏi lại, gọi pc_admin_key_off, ẩn khung mã", len(s.dialogs) == 1 and s.calls("pc_admin_key_off") == [{}] and s.js("() => document.getElementById('pca-keybox').hidden") and "đang đóng" in s.js("() => document.getElementById('pca-keyst').innerText"))

        print("10. Tự duyệt + công bố bản agent")
        s.dialogs.clear(); s.page.click("#pca-auto"); s.settle()
        ck("bật tự duyệt → hỏi lại + lưu", len(s.dialogs) == 1 and s.calls("pc_admin_settings") == [{"p_patch": {"auto_approve": True}}] and s.js("() => document.getElementById('pca-auto').checked"))
        s.dialogs.clear(); s.page.click("#pca-auto"); s.settle()
        ck("tắt tự duyệt → không hỏi, lưu", s.dialogs == [] and s.calls("pc_admin_settings")[-1] == {"p_patch": {"auto_approve": False}} and not s.js("() => document.getElementById('pca-auto').checked"))
        s.accept = False; s.page.click("#pca-auto"); s.settle()
        ck("bật mà chọn Huỷ → ô bỏ tích, không lưu", not s.js("() => document.getElementById('pca-auto').checked") and len(s.calls("pc_admin_settings")) == 2)
        s.accept = True
        ck("chưa công bố bản agent nào", "Bản agent công bố: chưa có" in s.js("() => document.getElementById('pca-agent').textContent") and "20.11a ×2" in s.js("() => document.getElementById('pca-agent').textContent"), s.js("() => document.getElementById('pca-agent').textContent"))
        s.dialogs.clear(); s.page.click("#pca-pub"); s.page.wait_for_timeout(500); s.settle()
        want_agent = {"ver": MANIFEST["ver"], "base": MANIFEST["base"], "files": MANIFEST["files"]}
        ck("công bố: đọc manifest.json trên GitHub, hỏi lại, lưu đúng ver/base/files (không kèm phần sha256 bộ công cụ)", len(s.dialogs) == 1 and ("Công bố bản agent %s (12 file)" % MANIFEST["ver"]) in s.dialogs[0]
           and s.calls("pc_admin_settings")[-1] == {"p_patch": {"agent": want_agent}}, s.dialogs)
        ck("dòng trạng thái đổi theo", ("Bản agent công bố: " + MANIFEST["ver"]) in s.js("() => document.getElementById('pca-agent').textContent"))
        n = len(s.calls("pc_admin_settings")); s.dialogs.clear(); s.page.click("#pca-pub"); s.page.wait_for_timeout(500); s.settle()
        ck("bấm lần nữa → báo đã công bố, không lưu lại", s.dialogs == [] and len(s.calls("pc_admin_settings")) == n and "đã được công bố rồi" in s.js("() => document.getElementById('toast').textContent"))
        for label, bad in (("nguồn không phải kho CloudBlue", dict(MANIFEST, ver="20.12x", base="https://raw.githubusercontent.com/ke-xau/x/main/winpc")),
                           ("tên file lạ", dict(MANIFEST, ver="20.12x", files=dict(MANIFEST["files"], **{"../x.py": "a" * 64}))),
                           ("mã kiểm sai dạng", dict(MANIFEST, ver="20.12x", files=dict(MANIFEST["files"], **{"agent/pcagent.py": "zz"}))),
                           ("thiếu chính file agent", dict(MANIFEST, ver="20.12x", files={k: v for k, v in MANIFEST["files"].items() if k != "agent/pcagent.py"})),
                           ("không phải JSON đúng dạng", ["x"]), ("GitHub trả 404", None)):
            s.manifest = bad; s.dialogs.clear(); s.page.click("#pca-pub"); s.page.wait_for_timeout(450); s.settle()
            ck("bản kê xấu (%s) → từ chối, không lưu" % label, s.dialogs == [] and len(s.calls("pc_admin_settings")) == n and "Không đọc được bản kê agent" in s.js("() => document.getElementById('toast').textContent"))
        s.manifest = MANIFEST
        ck("nút công bố mở lại sau mỗi lần", not s.js("() => document.getElementById('pca-pub').disabled"))

        print("11. Tự tải lại 15 giây khi đang mở thẻ")
        n0 = s.js("() => window.PCA.loads"); s.page.wait_for_timeout(16000); n1 = s.js("() => window.PCA.loads")
        ck("đang mở thẻ Máy PC → tự tải lại", n1 > n0, (n0, n1))
        s.tab("vps"); n0 = s.js("() => window.PCA.loads"); s.page.wait_for_timeout(16000); n1 = s.js("() => window.PCA.loads")
        ck("sang thẻ khác → không tải nữa", n1 == n0, (n0, n1))
        s.tab("pc"); s.settle()
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % B); n0 = s.js("() => window.PCA.loads"); s.page.wait_for_timeout(16000); n1 = s.js("() => window.PCA.loads")
        ck("đang mở hộp Sửa → tạm ngừng tải lại (không giật ô đang gõ)", n1 == n0, (n0, n1))
        s.page.click("#pcad-cancel")
        s.js("() => { window.__FAKE.delay = 300; }")
        s.page.click("#pca-reload"); s.page.wait_for_timeout(50); s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % A); s.page.wait_for_timeout(100)
        s.page.select_option("#pcad-status", "maint"); s.page.click("#pcad-save"); s.page.wait_for_timeout(1700); s.settle()
        ra = next(r for r in s.rows() if r.startswith("CB-A1B2C3"))
        ck("lưu đúng lúc đang tải dở → vẫn thấy thay đổi ngay (tải gộp thêm 1 lượt)", "Bảo trì" in ra, ra)
        s.js("() => { window.__FAKE.delay = 0; }")
        new_err = [x for x in sorted(set(s.errors)) if x not in e0]
        ck("cả lượt thử: không lỗi mới trong trang", new_err == [], new_err)
        s.page.screenshot(path=os.path.join(SHOTS, "pc-desktop.png"))
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="reinstall"]' % A); s.page.wait_for_timeout(300); s.page.screenshot(path=os.path.join(SHOTS, "pc-reinstall.png")); s.page.click("#pcrd-cancel")
        s.page.click('#pctbl tr[data-pc="%s"] [data-pca="edit"]' % A); s.page.wait_for_timeout(300); s.page.screenshot(path=os.path.join(SHOTS, "pc-edit.png")); s.page.click("#pcad-cancel")
        s.close()

        print("12. Chưa chạy SQL v41")
        s = Site(br, new, {"admin": True, "v41": False, "db": {}}); s.wait_admin()
        ck("mở bảng quản trị: không lỗi mới", [x for x in sorted(set(s.errors)) if x not in e0] == [], [x for x in sorted(set(s.errors)) if x not in e0])
        s.tab("pc"); s.settle()
        ck("hiện lời nhắc chạy cloud-pc-v41.sql + bảng báo rõ", s.js("() => !document.getElementById('pca-miss').hidden") and s.rows() == ["Chưa chạy SQL v41."] and "cloud-pc-v41.sql" in s.js("() => document.getElementById('pca-miss').innerText"), s.rows())
        ck("ghi nhớ trong phiên để lần mở sau khỏi gọi thừa", s.js("() => sessionStorage.getItem('pca_miss')") == "1")
        s.page.click("#pca-newkey"); s.settle()
        ck("bấm tạo mã → báo chưa chạy SQL, không hiện khung mã", "Chưa chạy SQL v41" in s.js("() => document.getElementById('toast').textContent") and s.js("() => document.getElementById('pca-keybox').hidden"))
        n = s.js("() => window.__FAKE.calls.filter(c => c.kind === 'from' && /^pc_/.test(c.table)).length")
        s.page.goto(ORIGIN + "/admin", wait_until="load"); s.wait_admin(); s.page.wait_for_timeout(500)
        ck("mở lại bảng quản trị trong cùng phiên → không gọi bảng pc_ khi chưa bấm thẻ", s.js("() => window.__FAKE.calls.filter(c => c.kind === 'from' && /^pc_/.test(c.table)).length") == 0)
        s.js("() => { window.__FAKE.v41 = true; }"); s.tab("pc"); s.settle()
        ck("chạy SQL xong, bấm thẻ → hết lời nhắc, bảng báo chưa có máy", s.js("() => document.getElementById('pca-miss').hidden && sessionStorage.getItem('pca_miss') === null") and s.rows()[0].startswith("Chưa có máy nào."), s.rows())
        s.close()

        print("13. Khách thường / chưa đăng nhập: không đụng gì tới phần Máy PC")
        for label, init, path in (("khách chưa đăng nhập ở trang chủ", {"admin": None, "db": make_db()}, "/"), ("tài khoản thường ở trang chủ", {"admin": False, "db": make_db()}, "/")):
            s0 = Site(br, base, init, path=path); s0.page.wait_for_timeout(1500); eb = sorted(set(s0.errors)); s0.close()
            s = Site(br, new, init, path=path); s.page.wait_for_timeout(1500)
            ck(label + ": không lỗi mới", [x for x in sorted(set(s.errors)) if x not in eb] == [], [x for x in sorted(set(s.errors)) if x not in eb])
            ck(label + ": không đọc bảng pc_, không gọi hàm pc_", s.js("() => window.__FAKE.calls.filter(c => /^pc_/.test(c.table || c.name || '')).length") == 0)
            ck(label + ": phần Máy PC ẩn", s.js("() => document.getElementById('pane-pc').hidden && document.getElementById('drawer').hidden && document.getElementById('pcadlg').hidden && document.getElementById('pcrdlg').hidden"))
            s.close()

        print("14. Màn hình điện thoại")
        s = Site(br, new, {"admin": True, "v41": True, "db": make_db()}, mobile=True); s.wait_admin(); s.tab("pc"); s.settle()
        ck("thẻ Máy PC bấm được trên màn hẹp, đủ 5 dòng", len(s.rows()) == 5)
        ck("trang không bị tràn ngang (bảng tự cuộn trong khung)", s.js("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), s.js("() => [document.documentElement.scrollWidth, window.innerWidth]"))
        ck("4 ô số xếp 2 cột", s.js("() => getComputedStyle(document.querySelector('.pca-tiles')).gridTemplateColumns.split(' ').length") == 2)
        s.page.screenshot(path=os.path.join(SHOTS, "pc-mobile.png"))
        s.page.click("#pca-showcmd"); s.page.click('#pctbl tr[data-pc="%s"] [data-pca="reinstall"]' % B, force=True); s.page.wait_for_timeout(300)
        ck("hộp cài lại vừa màn hình điện thoại", s.js("() => { const r = document.querySelector('#pcrdlg .dlg').getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1; }"))
        s.page.screenshot(path=os.path.join(SHOTS, "pc-mobile-reinstall.png"))
        s.close()
        br.close()
    print("\n%d/%d đạt" % (OK, OK + FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
