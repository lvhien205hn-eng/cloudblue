# -*- coding: utf-8 -*-
"""Thử ĐÈN NEON (22/11) trên trang chủ bằng Chrome thật (Playwright) + Supabase giả.
   python3 test_web_neon.py <index đã gắn> [thư mục ảnh chụp]
   · neon thường (mặc định, mọi khách): viền phát sáng đứng yên quanh thẻ sản phẩm / thẻ máy / video / hộp thoại
   · 💡 Neon chạy (khách bật — nút cạnh Sáng / Tối + cuối trang, nhớ br_neon): 2 vệt sáng chạy đuổi nhau quanh viền
   · máy tắt hoạt ảnh / chế độ nhẹ → vệt sáng đứng yên. Mọi yêu cầu mạng trả lời tại chỗ."""
import json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "test_web_shop.py"), encoding="utf-8").read()
ns = {"__file__": os.path.join(HERE, "test_web_shop.py")}
exec(src[:src.index("class Site:")], ns)                          # dùng chung dữ liệu giả (sản phẩm, VPS của khách) với bộ thử bán VPS
NEW_HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "..", "web", "index.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(NEW_HTML)), "shots")
os.makedirs(SHOTS, exist_ok=True)
ORIGIN, HTML = ns["ORIGIN"], open(NEW_HTML, encoding="utf-8").read()
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


class Page:
    def __init__(self, b, theme="dark", neon=None, lite="0", reduce=False, lang="vi", mobile=False):
        self.errors = []
        vp = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}
        self.ctx = b.new_context(viewport=vp, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", reduced_motion="reduce" if reduce else "no-preference")
        init = {"admin": False, "db": {"product_list": ns["PRODUCTS"], "products": ns["PRODUCTS"]}}
        shop = {"info": ns["INFO_ON"], "mine": ns["MINE"], "bought": [], "buyRes": None, "adm": ns["ADM"]}
        ls = {"br_lang": lang, "br_lite": lite, "br_theme": theme}
        if neon is not None: ls["br_neon"] = neon
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { if (!sessionStorage.getItem('__t')) { sessionStorage.setItem('__t', '1'); const o = %s; for (const k in o) localStorage.setItem(k, o[k]); } } catch (e) {}"
                                 % (json.dumps(init), json.dumps(shop), ns["HOOK"], json.dumps(ls)))
        self.page = self.ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" else None)
        self.page.route("**/*", self.route)
        self.page.goto(ORIGIN + "/", wait_until="load"); self.page.wait_for_timeout(2300)

    def route(self, r):
        u = r.request.url
        if u in (ORIGIN + "/", ORIGIN + "/admin"): return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=HTML)
        if "supabase-js" in u: return r.fulfill(status=200, content_type="application/javascript", body=open(os.path.join(HERE, "fake_supabase.js"), encoding="utf-8").read())
        return r.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)

    def st(self):
        return self.js("""() => { const r = document.documentElement, b = document.getElementById('neon-btn'), f = document.getElementById('neon-foot');
            const row = document.querySelector('.m3-row'), card = document.querySelector('.m3m-card.run') || document.querySelector('.m3m-card'), dlg = document.querySelector('.dlg');
            const af = el => { if (!el) return null; const c = getComputedStyle(el, '::after'); return { content: c.content, anim: c.animationName, dur: c.animationDuration, pad: c.paddingTop }; };
            let ls = null; try { ls = localStorage.getItem('br_neon'); } catch (e) {}
            return { run: r.classList.contains('neonrun'), ls, btn: b ? { pressed: b.getAttribute('aria-pressed'), title: b.title, on: b.classList.contains('on') } : null,
                     foot: f ? { pressed: f.getAttribute('aria-pressed'), text: f.textContent } : null,
                     rowShadow: row ? getComputedStyle(row).boxShadow : '', cardShadow: card ? getComputedStyle(card).boxShadow : '', cardCls: card ? card.className : '',
                     dlgShadow: dlg ? getComputedStyle(dlg).boxShadow : '', rowAfter: af(row), cardAfter: af(card), btnAfter: af(b),
                     toast: (document.getElementById('toast') || {}).textContent || '' }; }""")

    def close(self): self.ctx.close()


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        print("1. Mặc định (khách chưa bật): neon thường — viền phát sáng đứng yên, không có vệt chạy")
        s = Page(b); t = s.st()
        ck("chưa bật → không có lớp neonrun, nút 💡 Neon 'đang tắt', nút cuối trang ghi 'Neon chạy: Tắt'",
           not t["run"] and t["btn"] and t["btn"]["pressed"] == "false" and "đang tắt" in t["btn"]["title"] and t["foot"] and t["foot"]["text"] == "💡 Neon chạy: Tắt", t)
        ck("thẻ sản phẩm có viền neon xanh phát sáng (đứng yên)", "rgba(64, 214, 255" in t["rowShadow"] and (t["rowAfter"] or {}).get("content") in ("none", "normal"), t["rowShadow"])
        ck("thẻ máy đang chạy giữ màu trạng thái (xanh lá) cho neon", "rgba(60, 224, 176" in t["cardShadow"] and "run" in t["cardCls"], (t["cardCls"], t["cardShadow"]))
        ck("hộp thoại có quầng neon (không chạy)", "rgba(64, 214, 255" in t["dlgShadow"], t["dlgShadow"])
        s.page.screenshot(path=os.path.join(SHOTS, "neon-1-thuong.png"))

        print("2. Bấm 💡 Neon → đèn chạy đuổi nhau; nhớ sau khi tải lại; tắt ở nút cuối trang")
        s.page.click("#neon-btn"); s.page.wait_for_timeout(400); t = s.st()
        ck("bấm → bật: lớp neonrun, nhớ br_neon = 1, nút 'đang BẬT', cuối trang 'Bật', báo đã bật",
           t["run"] and t["ls"] == "1" and t["btn"]["pressed"] == "true" and t["btn"]["on"] and t["foot"]["text"] == "💡 Neon chạy: Bật" and "Đã bật đèn neon chạy" in t["toast"], t)
        ck("thẻ sản phẩm + thẻ máy + chính nút có vệt sáng chạy (hoạt ảnh nrun), 1 vòng ~6,5 giây",
           all((x or {}).get("anim") == "nrun" for x in (t["rowAfter"], t["cardAfter"], t["btnAfter"])) and t["rowAfter"]["dur"] == "6.5s" and t["rowAfter"]["pad"] == "2.5px", t)
        a1 = s.js("() => getComputedStyle(document.querySelector('.m3-row'), '::after').getPropertyValue('--nr')"); s.page.wait_for_timeout(700)
        a2 = s.js("() => getComputedStyle(document.querySelector('.m3-row'), '::after').getPropertyValue('--nr')")
        ck("vệt sáng thật sự di chuyển (góc --nr đổi theo thời gian)", a1 != a2 and a1.endswith("deg"), (a1, a2))
        s.page.screenshot(path=os.path.join(SHOTS, "neon-2-chay.png"))
        s.page.reload(wait_until="load"); s.page.wait_for_timeout(1800); t = s.st()
        ck("tải lại trang → vẫn bật (nhớ trên máy)", t["run"] and t["btn"]["pressed"] == "true", t)
        s.page.click("#neon-foot"); s.page.wait_for_timeout(300); t = s.st()
        ck("bấm nút cuối trang → tắt: về neon thường, nhớ br_neon = 0", not t["run"] and t["ls"] == "0" and t["foot"]["text"] == "💡 Neon chạy: Tắt"
           and (t["rowAfter"] or {}).get("content") in ("none", "normal") and "rgba(64, 214, 255" in t["rowShadow"] and "giữ neon thường" in t["toast"], t)
        ck("không có lỗi JS", not s.errors, s.errors); s.close()

        print("3. Máy tắt hoạt ảnh / chế độ nhẹ → vệt sáng đứng yên")
        s = Page(b, neon="1", reduce=True); t = s.st()
        ck("máy tắt hoạt ảnh: vẫn có vệt sáng nhưng KHÔNG chạy", t["run"] and (t["rowAfter"] or {}).get("content") == '""' and t["rowAfter"]["anim"] == "none", t["rowAfter"])
        s.close()
        s = Page(b, neon="0", lite="1"); s.page.click("#neon-btn"); s.page.wait_for_timeout(300); t = s.st()
        ck("chế độ nhẹ: bật được nhưng đèn đứng yên + nhắc bật lại ✨ Hiệu ứng", t["run"] and t["rowAfter"]["anim"] == "none" and "chế độ nhẹ" in t["toast"], (t["rowAfter"], t["toast"]))
        s.close()

        print("4. Sáng / tiếng Anh / điện thoại")
        s = Page(b, theme="light", neon="1"); t = s.st()
        ck("chế độ sáng: neon xanh dương dịu + vệt chạy", t["run"] and "rgba(37, 110, 240" in t["rowShadow"] and t["rowAfter"]["anim"] == "nrun", t["rowShadow"])
        s.page.screenshot(path=os.path.join(SHOTS, "neon-3-sang.png")); s.close()
        s = Page(b, lang="en"); t = s.st()
        ck("tiếng Anh: nút ghi 'Running neon'", "Running neon" in t["btn"]["title"] and "Running neon" in t["foot"]["text"], t)
        s.close()
        s = Page(b, neon="1", mobile=True); t = s.st()
        bb = s.js("() => { const r = document.getElementById('neon-btn').getBoundingClientRect(); return { w: r.width, h: r.height, x: r.x, vis: r.width > 0 && r.right <= innerWidth + 1 }; }")
        ck("điện thoại: nút 💡 gọn (chỉ biểu tượng), nằm trong màn hình, bấm được", bb["vis"] and bb["w"] <= 48 and bb["h"] >= 32, bb)
        s.page.screenshot(path=os.path.join(SHOTS, "neon-4-dien-thoai.png"))
        ck("không có lỗi JS", not s.errors, s.errors); s.close()
        b.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(1 if FAIL else 0)


main()
