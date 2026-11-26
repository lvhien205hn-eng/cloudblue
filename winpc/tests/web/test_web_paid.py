# -*- coding: utf-8 -*-
"""Thử phần "rớt nhân khi đổi Android" trên web (SQL v49 / v49b) bằng Chrome thật (Playwright) + Supabase giả:
   thẻ máy ghi "(đã mua …)", hộp Đổi Android lấy theo cấu hình ĐÃ MUA, hộp Gia hạn báo trước khi máy đang tạm hạ.
   python3 test_web_paid.py <index đã gắn> [thư mục ảnh chụp]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
HTML = sys.argv[1]
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/shots-paid"
os.makedirs(SHOTS, exist_ok=True)
sys.argv = [sys.argv[0], HTML, SHOTS]
import test_web_shop as T                                            # noqa: E402

UID = "00000000-0000-4000-8000-000000000001"                        # tài khoản của Supabase giả
OK = [0, 0]


def ck(name, cond, info=None):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name)
    else: print("  ✗", name, "→", str(info)[:700])


def iso(s): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=s)).isoformat()


PRICING = {"id": 1, "android_versions": "9,12,15", "max_ram": 16, "max_cpu": 32, "max_days": 90, "price_ram_gb_day": 1000, "price_cpu_day": 500,
           "android_limits": {"9": {"ram": 8, "cpu": 8}, "12": {"ram": 16, "cpu": 32}, "15": {"ram": 16, "cpu": 32}}}
def phone(i, name, android, ram, cpu, paid=None, **kw):
    p = {"id": "00000000-0000-4000-8000-00000000a00%d" % i, "user_id": UID, "name": name, "android": android, "ram": ram, "cpu": cpu, "res": "720x1280", "fps": 30,
         "status": "active", "expires_at": iso(5 * 86400), "created_at": iso(-i * 60), "node": "win1", "is_free": False, "pending_renew_days": 0}
    if paid is not None: p["paid_ram"], p["paid_cpu"] = paid
    p.update(kw); return p
TAM = phone(1, "ryo", "9", 8, 8, (8, 12))                            # đang Android 9 → tạm 8 nhân, đã mua 12
DU = phone(2, "Máy 16", "12", 16, 16, (16, 16))                      # đủ cấu hình
CU = phone(3, "Máy cũ", "12", 16, 16)                                # chưa chạy v49 (không có cột paid_*)


class Site(T.Site):
    def __init__(self, browser, html, phones):
        self.errors, self.dialogs, self.accept = [], [], True
        self.ctx = browser.new_context(viewport={"width": 1360, "height": 900}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        init = {"admin": False, "db": {"product_list": T.PRODUCTS, "products": T.PRODUCTS, "cloud_phones": phones, "cloudphone_pricing": [PRICING]}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps({"info": T.INFO_ON, "mine": {"items": []}, "adm": T.ADM, "bought": []}), T.HOOK))
        self.page = self.ctx.new_page(); self.html = html
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.goto(T.ORIGIN + "/", wait_until="load")
        self.page.wait_for_timeout(2600)


TXT = "s => { const e = document.querySelector(s); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null }"


def main():
    html = T.read(HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        s = Site(br, html, [TAM, DU, CU])
        s.js("async () => { await openCloud(); }"); s.page.wait_for_timeout(800)
        cards = s.js("() => [...document.querySelectorAll('#cp-list .vmi .nm small')].map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
        print("1. Thẻ máy")
        ck("máy tạm hạ: thẻ ghi '(đã mua 12 nhân)' · máy đủ / máy chưa có cột: không ghi", any("8GB · 8 nhân (đã mua 12 nhân)" in c for c in cards)
           and sum("đã mua" in c for c in cards) == 1, cards)
        tip = s.js("() => { const e = document.querySelector('#cp-list .paidtag'); return e ? e.title : '' }")
        ck("rê chuột vào '(đã mua …)': nói rõ đổi sang Android 12 / 15 để dùng đủ", "Android 12 / Android 15" in tip, tip)
        s.page.screenshot(path=os.path.join(SHOTS, "paid-1-the-may.png"))

        print("2. Đổi Android: máy đang tạm hạ (Android 9 · 8 nhân, đã mua 12)")
        s.js("id => cpSwitch(id)", TAM["id"]); s.page.wait_for_timeout(600)
        d = s.js(TXT, "#cpswdlg .dlg")
        ck("hộp đổi Android: dòng đầu ghi '(đã mua 12 nhân)'", d and "8GB · 8 nhân (đã mua 12 nhân)" in d, d)
        ck("chọn sẵn Android 12 → máy mới 8GB · 12 nhân, ghi 'trả đủ cấu hình đã mua'", d and "Máy mới: Android 12 · 8GB · 12 nhân" in d and "trả đủ cấu hình đã mua" in d, d)
        s.page.screenshot(path=os.path.join(SHOTS, "paid-2-doi-ve-12.png"))
        s.page.click("#cpswdlg [data-swx]")

        print("3. Đổi Android: máy đủ 16GB · 16 nhân → Android 9")
        s.js("id => cpSwitch(id)", DU["id"]); s.page.wait_for_timeout(500)
        s.page.click("#cpswdlg [data-swv='9']"); s.page.wait_for_timeout(300)
        d = s.js(TXT, "#cpswdlg .swnote")
        ck("báo: máy mới TẠM chạy 8GB · 8 nhân, cấu hình đã mua 16GB · 16 nhân vẫn giữ, đổi sang Android 12 / 15 là trả đủ",
           d and "tạm chạy 8GB · 8 nhân" in d and "16GB · 16 nhân vẫn được giữ" in d and "Android 12 / Android 15 là trả đủ" in d and "không hoàn tiền" not in d, d)
        s.page.screenshot(path=os.path.join(SHOTS, "paid-3-doi-sang-9.png"))
        s.page.click("#cpswdlg [data-swx]")

        print("4. Đổi Android: cơ sở dữ liệu chưa chạy v49 (không có cột) → như cũ")
        s.js("id => cpSwitch(id)", CU["id"]); s.page.wait_for_timeout(500)
        s.page.click("#cpswdlg [data-swv='9']"); s.page.wait_for_timeout(300)
        d = s.js(TXT, "#cpswdlg .swnote")
        ck("chưa chạy v49: giữ câu cũ 'hạ còn … không hoàn tiền phần chênh'", d and "hạ còn 8GB · 8 nhân" in d and "không hoàn tiền phần chênh" in d, d)
        s.page.click("#cpswdlg [data-swx]")

        print("5. Gia hạn")
        s.js("id => cpRenew(id)", TAM["id"]); s.page.wait_for_timeout(700)
        d = s.js(TXT, "#cprendlg .swnote")
        ck("máy tạm hạ: hộp gia hạn báo trước — tính theo 8GB · 8 nhân, cấu hình đã mua hạ còn 8 · 8, muốn giữ 12 nhân thì đổi Android 12 / 15 trước",
           d and "tạm chạy 8GB · 8 nhân" in d and "đã mua 8GB · 12 nhân" in d and "hạ còn 8GB · 8 nhân" in d and "đổi sang Android 12 / Android 15 trước" in d, d)
        s.page.screenshot(path=os.path.join(SHOTS, "paid-4-gia-han.png"))
        s.js("() => { document.getElementById('cprendlg').hidden = true }")
        s.js("id => cpRenew(id)", DU["id"]); s.page.wait_for_timeout(600)
        ck("máy đủ cấu hình: hộp gia hạn không có cảnh báo", s.js("() => !document.querySelector('#cprendlg .swnote')"))
        ck("không có lỗi trang", not s.errors, s.errors)
        s.close(); br.close()
    print(f"\n{OK[0]}/{OK[1]} đạt")
    sys.exit(0 if OK[0] == OK[1] else 1)


if __name__ == "__main__":
    main()
