# -*- coding: utf-8 -*-
"""Thử phần XÁC MINH 2 BƯỚC cho admin trên web (21.11l, SQL v47) bằng Chrome thật (Playwright) + Supabase giả.
   python3 test_web_mfa.py <index đã gắn> [thư mục ảnh chụp]
   Mọi yêu cầu mạng trả lời tại chỗ — không gọi ra ngoài."""
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "..", "web", "index.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(NEW_HTML)), "shots")
os.makedirs(SHOTS, exist_ok=True)
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def read(p):
    with open(p, encoding="utf-8") as f: return f.read()


class Site:
    def __init__(self, browser, html, admin, mfa, path="/admin", mobile=False):
        self.errors = []
        vp = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 900}
        self.ctx = browser.new_context(viewport=vp, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": admin, "db": {}}
        if mfa is not None: init["mfa"] = mfa
        self.ctx.add_init_script("window.__FAKE_INIT = %s; try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}" % json.dumps(init))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2600)

    def route(self, route):
        u = route.request.url
        if u in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=read(os.path.join(HERE, "fake_supabase.js")))
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def vis(self, id_): return self.js("id => { const e = document.getElementById(id); return !!e && !e.hidden && getComputedStyle(e).display !== 'none'; }", id_)
    def mcalls(self, kind): return self.js("k => window.__FAKE.mfa ? window.__FAKE.mfa.calls.filter(c => c[0] === k).map(c => c[1] || null) : []", kind)
    def close(self): self.ctx.close()


def main():
    html = read(NEW_HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch()

        print("1. Admin CHƯA bật 2 bước: vào quản trị bình thường + cảnh báo nhắc bật")
        s = Site(br, html, True, {"factors": [], "aal": "aal1"})
        st = s.js("() => ({ drawer: !document.getElementById('drawer').hidden, adm: isAdmin(), alert: document.getElementById('adm-alert').innerText, btn: document.getElementById('adm-mfa').innerText, btnVis: !document.getElementById('adm-mfa').hidden })")
        ck("vào thẳng bảng quản trị (không hỏi mã), isAdmin() = true", st["drawer"] and st["adm"] and not s.vis("mfa"), st)
        ck("đầu bảng quản trị có cảnh báo vàng 'chưa bật xác minh 2 bước' + link Bật ngay; nút 🔐 'Bật 2 bước'", "chưa bật xác minh 2 bước" in st["alert"] and "Bật ngay" in st["alert"] and st["btnVis"] and "Bật 2 bước" in st["btn"], st)
        s.page.click("#adm-alert [data-mfa]"); s.page.wait_for_timeout(500)
        q = s.js("() => ({ new: !document.getElementById('mfa-new').hidden, ask: !document.getElementById('mfa-ask').hidden, src: document.getElementById('mfa-qr').getAttribute('src') || '', sec: document.getElementById('mfa-sec').textContent })")
        ck("bấm 'Bật ngay' → hộp hướng dẫn 3 bước + mã QR + khoá gõ tay", s.vis("mfa") and q["new"] and not q["ask"] and q["src"].startswith("data:image/svg+xml") and q["sec"] == "JBSWY3DPEHPK3PXP", q)
        ck("đã gọi enroll kiểu totp", [c.get("factorType") for c in s.mcalls("enroll")] == ["totp"], s.mcalls("enroll"))
        s.page.screenshot(path=os.path.join(SHOTS, "mfa-1-bat.png"))
        s.page.fill("#mfa-code2", "000000"); s.page.click("#mfa-on"); s.page.wait_for_timeout(400)
        e = s.js("() => document.getElementById('mfa-err2').textContent")
        ck("nhập sai mã → báo 'Mã sai hoặc đã hết hạn', chưa bật", "Mã sai" in e and s.vis("mfa") and s.js("() => !MFA.on"), e)
        s.page.fill("#mfa-code2", "12 34 56"); s.page.click("#mfa-on"); s.page.wait_for_timeout(700)
        st = s.js("() => ({ on: MFA.on, need: MFA.need, alert: document.getElementById('adm-alert').innerText, btn: document.getElementById('adm-mfa').innerText, toast: [...document.querySelectorAll('.toast, #toast')].map(x => x.innerText).join(' | '), f: window.__FAKE.mfa.factors })")
        ck("nhập đúng mã (có dấu cách vẫn nhận) → bật: đóng hộp, hết cảnh báo, nút '🔐 Đã bật 2 bước', báo 'Đã bật'",
           not s.vis("mfa") and st["on"] and not st["need"] and "chưa bật xác minh" not in st["alert"] and "Đã bật 2 bước" in st["btn"] and "Đã bật xác minh 2 bước" in st["toast"]
           and [f["status"] for f in st["f"]] == ["verified"], st)
        s.page.click("#adm-mfa"); s.page.wait_for_timeout(400)
        ck("bấm 🔐 khi đã bật → hộp quản lý (Đổi điện thoại / Tắt)", s.vis("mfa") and s.vis("mfa-man") and not s.vis("mfa-new"))
        s.page.screenshot(path=os.path.join(SHOTS, "mfa-2-quan-ly.png"))
        s.page.click("#mfa-off"); s.page.wait_for_timeout(300)
        ck("bấm Tắt lần 1 → chỉ hỏi lại (chưa tắt)", not s.mcalls("unenroll") and "lần nữa" in s.js("() => document.getElementById('mfa-off').textContent"))
        s.page.click("#mfa-off"); s.page.wait_for_timeout(700)
        st = s.js("() => ({ on: MFA.on, alert: document.getElementById('adm-alert').innerText, f: window.__FAKE.mfa.factors })")
        ck("bấm lần 2 → gỡ mã, cảnh báo 'chưa bật' hiện lại", len(s.mcalls("unenroll")) == 1 and not st["on"] and not st["f"] and "chưa bật xác minh 2 bước" in st["alert"], st)
        ck("1: không lỗi JS", not s.errors, s.errors)
        s.close()

        print("2. Admin ĐÃ bật, phiên mới chưa nhập mã (aal1) → hỏi mã 6 số trước khi vào quản trị")
        s = Site(br, html, True, {"factors": [{"id": "fac1", "status": "verified", "factor_type": "totp"}], "aal": "aal1"})
        st = s.js("() => ({ drawer: !document.getElementById('drawer').hidden, adm: isAdmin(), need: MFA.need, ask: !document.getElementById('mfa-ask').hidden })")
        ck("hiện hộp 'Nhập mã 6 số', KHÔNG mở bảng quản trị, isAdmin() = false", s.vis("mfa") and st["ask"] and st["need"] and not st["drawer"] and not st["adm"], st)
        s.page.screenshot(path=os.path.join(SHOTS, "mfa-3-hoi-ma.png"))
        s.page.fill("#mfa-code", "111111"); s.page.keyboard.press("Enter"); s.page.wait_for_timeout(400)
        e = s.js("() => document.getElementById('mfa-err').textContent")
        ck("mã sai (bấm Enter) → báo lỗi, vẫn chưa vào", "Mã sai" in e and not s.js("() => isAdmin()"), e)
        s.page.fill("#mfa-code", "123456"); s.page.click("#mfa-ok"); s.page.wait_for_timeout(1200)
        st = s.js("() => ({ drawer: !document.getElementById('drawer').hidden, adm: isAdmin(), need: MFA.need })")
        v = s.mcalls("verify")
        ck("mã đúng → đóng hộp, isAdmin() = true, tự mở bảng quản trị (trang /admin)", not s.vis("mfa") and st["adm"] and not st["need"] and st["drawer"], st)
        ck("xác minh đúng mã của tài khoản (fac1)", v and v[-1] == {"factorId": "fac1", "code": "123456"}, v)
        ck("2: không lỗi JS", not s.errors, s.errors)
        s.close()

        print("3. Đăng xuất ngay ở hộp hỏi mã")
        s = Site(br, html, True, {"factors": [{"id": "fac1", "status": "verified", "factor_type": "totp"}], "aal": "aal1"})
        s.page.keyboard.press("Escape"); s.page.wait_for_timeout(900)
        g = s.js("() => ({ msg: document.getElementById('adm-gate-msg').textContent, btn: document.getElementById('adm-gate-login').textContent, vis: !document.getElementById('adm-gate-login').hidden })")
        ck("lỡ đóng hộp (Esc) → trang /admin ghi 'nhập mã 6 số để vào' + nút 'Nhập mã 6 số' (không báo nhầm 'không phải admin')", "xác minh 2 bước" in g["msg"] and "không phải admin" not in g["msg"] and g["vis"] and "Nhập mã" in g["btn"], g)
        s.page.click("#adm-gate-login"); s.page.wait_for_timeout(400)
        ck("bấm 'Nhập mã 6 số' → mở lại hộp hỏi mã", s.vis("mfa") and s.vis("mfa-ask"))
        s.page.click("#mfa-out"); s.page.wait_for_timeout(600)
        ck("bấm Đăng xuất → đóng hộp, không còn hồ sơ, không vào quản trị", not s.vis("mfa") and s.js("() => profile === null && document.getElementById('drawer').hidden"))
        s.close()

        print("4. Phiên đã nhập mã (aal2) → vào thẳng, không hỏi")
        s = Site(br, html, True, {"factors": [{"id": "fac1", "status": "verified", "factor_type": "totp"}], "aal": "aal2"})
        ck("không hỏi mã, mở bảng quản trị, nút '🔐 Đã bật 2 bước', không có cảnh báo 'chưa bật'",
           not s.vis("mfa") and s.js("() => isAdmin() && !document.getElementById('drawer').hidden && document.getElementById('adm-mfa').innerText.includes('Đã bật') && !document.getElementById('adm-alert').innerText.includes('chưa bật xác minh')"))
        s.page.click("#adm-mfa"); s.page.wait_for_timeout(300); s.page.click("#mfa-swap"); s.page.wait_for_timeout(500)
        ck("Đổi sang điện thoại khác → tạo mã QR mới (máy cũ vẫn giữ tới khi máy mới chạy được)", s.vis("mfa-new") and len(s.mcalls("enroll")) == 1 and len(s.js("() => window.__FAKE.mfa.factors")) == 2)
        s.page.fill("#mfa-code2", "123456"); s.page.click("#mfa-on"); s.page.wait_for_timeout(800)
        f = s.js("() => window.__FAKE.mfa.factors")
        ck("máy mới xác nhận xong → gỡ mã máy cũ, còn đúng 1 mã (của máy mới)", [x["id"] for x in f] != ["fac1"] and len(f) == 1 and f[0]["status"] == "verified" and {"factorId": "fac1"} in s.mcalls("unenroll"), f)
        ck("4: không lỗi JS", not s.errors, s.errors)
        s.close()

        print("5. Bật dở rồi bấm 'Để sau' → dọn mã chưa xác nhận")
        s = Site(br, html, True, {"factors": [], "aal": "aal1"})
        s.page.click("#adm-mfa"); s.page.wait_for_timeout(500); s.page.click("#mfa-new-x"); s.page.wait_for_timeout(400)
        ck("đóng hộp + gỡ mã chưa xác nhận", not s.vis("mfa") and len(s.mcalls("unenroll")) == 1 and not s.js("() => window.__FAKE.mfa.factors.length"))
        s.close()

        print("6. Khách thường: không đụng tới xác minh 2 bước")
        s = Site(br, html, False, {"factors": [], "aal": "aal1"}, path="/")
        ck("khách: không hỏi mã, không gọi API 2 bước", not s.vis("mfa") and not s.mcalls("aal") and not s.mcalls("list") and not s.js("() => isAdmin()"))
        ck("6: không lỗi JS", not s.errors, s.errors)
        s.close()

        print("7. Thư viện Supabase cũ (không có mfa) → web vẫn chạy như trước")
        s = Site(br, html, True, None)
        ck("vào quản trị bình thường, ẩn nút 🔐, không cảnh báo 2 bước, không lỗi JS",
           s.js("() => isAdmin() && !document.getElementById('drawer').hidden && document.getElementById('adm-mfa').hidden && !document.getElementById('adm-alert').innerText.includes('xác minh 2 bước')") and not s.errors, s.errors)
        s.close()

        print("8. Điện thoại 390px: hộp hỏi mã gọn, không tràn")
        s = Site(br, html, True, {"factors": [{"id": "fac1", "status": "verified", "factor_type": "totp"}], "aal": "aal1"}, mobile=True)
        r = s.js("() => { const d = document.querySelector('#mfa .dlg').getBoundingClientRect(); return { w: d.width, l: d.left, r: d.right, vw: innerWidth, over: document.documentElement.scrollWidth - innerWidth }; }")
        ck("hộp nằm trong màn hình 390px", s.vis("mfa") and r["l"] >= 0 and r["r"] <= r["vw"] + 1 and r["over"] <= 0, r)
        s.page.screenshot(path=os.path.join(SHOTS, "mfa-4-hoi-ma-dien-thoai.png"))
        s.close()
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
