# Bộ thử mục "Video hướng dẫn" trên trang chủ (web 21.11j): 2 video (Cloud Phone · VPS GPU), tự phát khi kéo tới — kể cả máy tắt hiệu ứng chuyển động.
#   python3 test_web_video.py <index.html> <thư mục video (cloud-phone.mp4/jpg, vps-gpu.mp4/jpg)> [thư mục ảnh]
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HTML, VDIR = sys.argv[1], sys.argv[2]
SHOTS = sys.argv[3] if len(sys.argv) > 3 else "/tmp/shots-video"
os.makedirs(SHOTS, exist_ok=True)
sys.argv = [sys.argv[0], HTML, SHOTS]
sys.path.insert(0, HERE)
import test_web_shop as T
from playwright.sync_api import sync_playwright

OK = [0, 0]
def ck(name, cond, info=None):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name)
    else: print("  ✗", name, "→", info)


class Site(T.Site):
    def __init__(self, browser, html, reduced, mobile=False):
        self.errors, self.dialogs, self.accept = [], [], True
        vp = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 768}
        self.ctx = browser.new_context(viewport=vp, device_scale_factor=1, locale="vi-VN", reduced_motion="reduce" if reduced else "no-preference",
                                       is_mobile=mobile, has_touch=mobile)
        import json
        init = {"admin": False, "db": {"product_list": T.PRODUCTS, "products": T.PRODUCTS}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__SHOP = %s; %s try { localStorage.setItem('br_lang', 'vi'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps({"info": T.INFO_ON, "mine": {"items": []}, "adm": T.ADM, "bought": []}), T.HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.seen = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: print("     [console]", m.text[:160]) if "play" in m.text.lower() and m.type in ("error", "warning") else None)
        self.page.route("**/*", self.route)
        self.page.goto(T.ORIGIN + "/", wait_until="load")
        self.page.wait_for_timeout(1800)

    def route(self, route):
        u = route.request.url
        if "/video/" in u:
            f = os.path.join(VDIR, u.split("/video/")[1].split("?")[0])
            self.seen.append(u.split(T.ORIGIN)[-1])
            if os.path.exists(f):
                ct = "video/mp4" if f.endswith(".mp4") else "image/jpeg"
                data = open(f, "rb").read(); rg = route.request.headers.get("range", "")
                if rg.startswith("bytes=") and f.endswith(".mp4"):                 # tua video cần trả từng khúc (206) như Vercel
                    a_, _, b_ = rg[6:].partition("-"); a_ = int(a_ or 0); b_ = int(b_) if b_ else len(data) - 1
                    return route.fulfill(status=206, content_type=ct, body=data[a_:b_ + 1],
                                         headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes {a_}-{b_}/{len(data)}"})
                return route.fulfill(status=200, content_type=ct, body=data, headers={"Accept-Ranges": "bytes"})
            return route.fulfill(status=404, body="")
        if "gioi-thieu" in u: self.seen.append(u)
        return T.Site.route(self, route)


def state(s):
    return s.js("""() => { const one = id => { const el = document.getElementById(id); if (!el) return null; const v = el.querySelector('video'), f = el.querySelector('.m3v-fig');
        return { show: !el.hidden, src: v.getAttribute('src') || '', paused: v.paused, muted: v.muted, t: v.currentTime, on: f.classList.contains('on'), ended: v.ended,
                 h: el.querySelector('h3').innerText.replace(/\\s+/g, ' ').trim(), ch: [...el.querySelectorAll('.m3v-ch button')].map(b => b.innerText.replace(/\\s+/g, ' ').trim()),
                 snd: !el.querySelector('.m3v-snd').hidden, top: el.getBoundingClientRect().top + scrollY }; };
      return { sec: !document.getElementById('m3v').hidden, h: document.querySelector('#m3v h2').textContent, tabs: document.querySelectorAll('.m3v-sw').length,
               cp: one('m3v-cp'), vps: one('m3v-vps') } }""")


def scroll_to(s, id="m3v-cp", wait=2500):
    s.js("(id) => document.querySelector('#' + id + ' .m3v-fig').scrollIntoView({ block: 'center' })", id)
    s.page.wait_for_timeout(wait)


def main():
    html = T.read(HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        print("   (bản index:", HTML, ")")
        print("1. Máy TẮT hiệu ứng chuyển động (như Windows tắt Animation effects) — 2 video xếp chồng, tự phát khi kéo tới")
        s = Site(br, html, reduced=True)
        st0 = state(s)
        ck("mục video: tiêu đề mới · KHÔNG còn nút chọn video · Cloud Phone 1:02 ở trên, VPS GPU 1:41 ở dưới", st0["sec"] and "Video hướng dẫn" in st0["h"] and st0["tabs"] == 0
           and st0["cp"] and st0["vps"] and "Cloud Phone" in st0["cp"]["h"] and "1:02" in st0["cp"]["h"] and "VPS GPU" in st0["vps"]["h"] and "1:41" in st0["vps"]["h"]
           and st0["cp"]["top"] < st0["vps"]["top"], st0)
        ck("chưa kéo tới: chưa tải video nào", st0["cp"]["src"] == "" and st0["vps"]["src"] == "", st0)
        scroll_to(s, "m3v-cp")
        st = state(s)
        ck("kéo tới video trên → tự phát Cloud Phone (tắt tiếng) + nút 🔊 Bật tiếng; video dưới chưa chạy", st["cp"]["src"] == "/video/cloud-phone.mp4" and not st["cp"]["paused"] and st["cp"]["muted"]
           and st["cp"]["on"] and st["cp"]["snd"] and (st["vps"]["paused"] or st["vps"]["src"] == ""), st)
        ck("6 chương Cloud Phone, mốc đúng (0:00 … 0:54)", len(st["cp"]["ch"]) == 6 and st["cp"]["ch"][0].startswith("0:00") and st["cp"]["ch"][5].startswith("0:54"), st["cp"]["ch"])
        ck("trạng thái giảm chuyển động: nền máy chạy đầu trang VẪN chuyển động (không bị tắt)", s.js("() => { const c = document.querySelector('.m3-col'); return !c || getComputedStyle(c).animationName !== 'none'; }"))
        s.page.screenshot(path=os.path.join(SHOTS, "video-1-cp.png"))
        scroll_to(s, "m3v-vps")
        st = state(s)
        ck("kéo xuống video dưới → tự phát VPS GPU, video trên tự dừng (1 video chạy 1 lúc)", st["vps"]["src"] == "/video/vps-gpu.mp4" and not st["vps"]["paused"] and st["vps"]["muted"] and st["cp"]["paused"], st)
        ck("7 chương VPS GPU (… 1:36)", len(st["vps"]["ch"]) == 7 and st["vps"]["ch"][6].startswith("1:36"), st["vps"]["ch"])
        s.page.screenshot(path=os.path.join(SHOTS, "video-2-vps.png"))
        s.page.click('#m3v-vps .m3v-ch button[data-s="62"]'); s.page.wait_for_timeout(1200)
        st = state(s)
        ck("bấm chương 1:02 của VPS GPU → tua tới đúng chỗ", 61.5 <= st["vps"]["t"] <= 64.5 and not st["vps"]["paused"], st["vps"]["t"])
        s.page.click("#m3v-vps .m3v-snd"); s.page.wait_for_timeout(500)
        st = state(s)
        ck("bấm 🔊 → bật tiếng, nút ẩn", not st["vps"]["muted"] and not st["vps"]["snd"], st["vps"])
        s.js("() => window.scrollTo(0, 0)"); s.page.wait_for_timeout(1200)
        st = state(s)
        ck("kéo đi chỗ khác → cả 2 video dừng", st["cp"]["paused"] and st["vps"]["paused"], st)
        s.js("() => { const v = document.querySelector('#m3v-vps video'); v.currentTime = v.duration - .3; }"); scroll_to(s, "m3v-vps", 3000)
        ck("xem hết VPS GPU → video dừng ở cuối, không tự nhảy sang video khác", state(s)["vps"]["ended"] or state(s)["vps"]["paused"], state(s)["vps"])
        s.js("() => window.scrollTo(0, 0)"); s.page.wait_for_timeout(1000); scroll_to(s, "m3v-vps")
        st = state(s)
        ck("kéo đi rồi kéo lại tới video đã xem hết → phát lại từ đầu", not st["vps"]["paused"] and st["vps"]["t"] < 6, st["vps"])
        s.js("() => document.querySelector('#m3v-vps video').pause()"); s.page.wait_for_timeout(300)
        s.js("() => window.scrollTo(0, 0)"); s.page.wait_for_timeout(1000); scroll_to(s, "m3v-vps")
        ck("khách tự bấm dừng → kéo đi kéo lại cũng KHÔNG tự phát lại", state(s)["vps"]["paused"])
        ck("không tải video cũ (gioi-thieu-a / b)", not any("gioi-thieu" in u for u in s.seen), s.seen)
        ck("không lỗi JS", not s.errors, s.errors)
        s.close()

        print("2. Điện thoại (390 px)")
        m = Site(br, html, reduced=False, mobile=True)
        scroll_to(m, "m3v-cp")
        st = state(m)
        ck("điện thoại: kéo tới → tự phát Cloud Phone", st["cp"]["src"] == "/video/cloud-phone.mp4" and not st["cp"]["paused"], st["cp"])
        w = m.js("""() => { const b = document.getElementById('m3v-cp'), f = b.querySelector('.m3v-fig').getBoundingClientRect(), c = b.querySelector('.m3v-ch').getBoundingClientRect(),
                           v = document.getElementById('m3v-vps').getBoundingClientRect(); return [f.width, f.height, c.top >= f.bottom - 1, v.top >= c.bottom - 1, document.documentElement.scrollWidth <= innerWidth + 1]; }""")
        ck("điện thoại: khung video 16:9 vừa màn, chương nằm dưới, video VPS GPU nằm dưới nữa, không tràn ngang", w[0] > 300 and abs(w[0] / w[1] - 16 / 9) < .05 and w[2] and w[3] and w[4], w)
        ck("điện thoại (chế độ nhẹ tự bật): nền máy chạy đầu trang vẫn chuyển động", m.js("() => { const c = document.querySelector('.m3-col'); return !c || getComputedStyle(c).animationName !== 'none'; }"))
        m.page.screenshot(path=os.path.join(SHOTS, "video-3-mobile.png"), full_page=False)
        ck("điện thoại: không lỗi JS", not m.errors, m.errors)
        m.close()

        print("3. Tiếng Anh + khách tự bật chế độ nhẹ")
        e = Site(br, html, reduced=False)
        e.js("() => { try { setLang('en'); } catch (er) { localStorage.setItem('br_lang', 'en'); } }"); e.page.wait_for_timeout(600)
        st = state(e)
        ck("tiếng Anh: tiêu đề + chương dịch", "How-to" in st["h"] and any("Rent in 3 steps" in c for c in st["cp"]["ch"]) and any("Buying" in c for c in st["vps"]["ch"]), st)
        e.close()
        l = Site.__new__(Site)
        Site.__init__(l, br, html, reduced=False)
        l.js("() => { localStorage.setItem('br_lite', '1'); }"); l.page.reload(wait_until="load"); l.page.wait_for_timeout(1500)
        ck("khách TỰ bật chế độ nhẹ (br_lite = 1) → nền đầu trang mới đứng yên", l.js("() => { const c = document.querySelector('.m3-col'); return !c || getComputedStyle(c).animationName === 'none'; }"))
        l.close(); br.close()
    print(f"\n{OK[0]}/{OK[1]} đạt")
    sys.exit(0 if OK[0] == OK[1] else 1)


main()
