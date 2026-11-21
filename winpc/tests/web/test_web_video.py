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
    return s.js("""() => { const v = document.getElementById('m3v-video'), f = document.getElementById('m3v-fig');
      return { sec: !document.getElementById('m3v').hidden, src: v.getAttribute('src') || '', paused: v.paused, muted: v.muted, t: v.currentTime, on: f.classList.contains('on'),
               tabs: [...document.querySelectorAll('.m3v-sw button')].map(b => [b.dataset.v, b.classList.contains('on'), b.innerText.replace(/\\s+/g, ' ').trim()]),
               ch: [...document.querySelectorAll('#m3v-ch button')].map(b => b.innerText.replace(/\\s+/g, ' ').trim()),
               snd: !document.getElementById('m3v-snd').hidden, tag: (document.getElementById('m3v-tag') || {}).textContent || '',
               h: document.querySelector('#m3v h2').textContent } }""")


def scroll_to(s):
    s.js("() => document.getElementById('m3v').scrollIntoView({ block: 'center' })")
    s.page.wait_for_timeout(2500)


def main():
    html = T.read(HTML)
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        print("1. Máy TẮT hiệu ứng chuyển động (như Windows tắt Animation effects) — vẫn tự phát khi kéo tới")
        s = Site(br, html, reduced=True)
        st0 = state(s)
        ck("mục video có, tiêu đề mới, 2 nút: Cloud Phone 1:02 · VPS GPU 1:41", st0["sec"] and "Video hướng dẫn" in st0["h"] and [t[0] for t in st0["tabs"]] == ["cp", "vps"]
           and "Cloud Phone" in st0["tabs"][0][2] and "1:02" in st0["tabs"][0][2] and "1:41" in st0["tabs"][1][2], st0)
        ck("chưa kéo tới: chưa tải video", st0["src"] == "" and st0["paused"], st0)
        scroll_to(s)
        st = state(s)
        ck("kéo tới → tự phát video Cloud Phone (tắt tiếng), có nút 🔊 Bật tiếng + nhãn tên video", st["src"] == "/video/cloud-phone.mp4" and not st["paused"] and st["muted"] and st["on"] and st["snd"] and "Cloud Phone" in st["tag"], st)
        ck("6 chương Cloud Phone, mốc đúng (0:00 … 0:54)", len(st["ch"]) == 6 and st["ch"][0].startswith("0:00") and st["ch"][5].startswith("0:54"), st["ch"])
        s.page.screenshot(path=os.path.join(SHOTS, "video-1-cp.png"))
        s.page.click('.m3v-sw button[data-v="vps"]'); s.page.wait_for_timeout(1800)
        st = state(s)
        ck("bấm VPS GPU → phát video VPS GPU, 7 chương (… 1:36), nhãn đổi", st["src"] == "/video/vps-gpu.mp4" and not st["paused"] and len(st["ch"]) == 7 and st["ch"][6].startswith("1:36") and "VPS GPU" in st["tag"], st)
        s.page.click('#m3v-ch button[data-s="62"]'); s.page.wait_for_timeout(1200)
        st = state(s)
        ck("bấm chương 1:02 → tua tới đúng chỗ", 61.5 <= st["t"] <= 64.5 and not st["paused"], st["t"])
        s.page.click("#m3v-snd"); s.page.wait_for_timeout(500)
        st = state(s)
        ck("bấm 🔊 → bật tiếng, nút ẩn", not st["muted"] and not st["snd"], st)
        s.js("() => window.scrollTo(0, 0)"); s.page.wait_for_timeout(1200)
        ck("kéo đi chỗ khác → tự dừng", state(s)["paused"])
        s.js("() => { const v = document.getElementById('m3v-video'); v.currentTime = v.duration - .3; }"); scroll_to(s); s.page.wait_for_timeout(1500)
        st = state(s)
        ck("hết video VPS GPU → tự sang Cloud Phone", st["src"] == "/video/cloud-phone.mp4" and [t[0] for t in st["tabs"] if t[1]] == ["cp"], st)
        ck("không tải video cũ (gioi-thieu-a / b)", not any("gioi-thieu" in u for u in s.seen), s.seen)
        ck("không lỗi JS", not s.errors, s.errors)
        s.close()

        print("2. Điện thoại (390 px)")
        m = Site(br, html, reduced=False, mobile=True)
        scroll_to(m)
        st = state(m)
        ck("điện thoại: kéo tới → tự phát Cloud Phone", st["src"] == "/video/cloud-phone.mp4" and not st["paused"], st)
        w = m.js("() => { const f = document.getElementById('m3v-fig').getBoundingClientRect(), c = document.getElementById('m3v-ch').getBoundingClientRect(); return [f.width, f.height, c.top >= f.bottom - 1, document.documentElement.scrollWidth <= innerWidth + 1]; }")
        ck("điện thoại: khung video 16:9 vừa màn, chương nằm dưới, không tràn ngang", w[0] > 300 and abs(w[0] / w[1] - 16 / 9) < .05 and w[2] and w[3], w)
        m.page.screenshot(path=os.path.join(SHOTS, "video-2-mobile.png"))
        ck("điện thoại: không lỗi JS", not m.errors, m.errors)
        m.close()

        print("3. Tiếng Anh")
        e = Site(br, html, reduced=False)
        e.js("() => { try { setLang('en'); } catch (er) { localStorage.setItem('br_lang', 'en'); } }"); e.page.wait_for_timeout(600)
        st = state(e)
        ck("tiếng Anh: tiêu đề + chương dịch", "How-to" in st["h"] and any("Rent in 3 steps" in c for c in st["ch"]), st)
        e.close(); br.close()
    print(f"\n{OK[0]}/{OK[1]} đạt")
    sys.exit(0 if OK[0] == OK[1] else 1)


main()
