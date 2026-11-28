# -*- coding: utf-8 -*-
"""28/11h · 🖥 THẺ MÁY CHỦ: CPU đủ cả 2 CPU · RAM chính · RAM ảo · lý do ngừng nhận (user 28/11 21:40: "máy x2 CPU mà toàn thấy báo 1 CPU ·
   RAM cứ lấy RAM chính mà dùng, đến full mới dùng RAM ảo"). Trước: card kẹt xung làm thẻ hiện 31/31 nhân · 41/41 GB như CPU / RAM đầy.
   Chrome thật (Playwright) + Supabase giả. python3 winpc/tests/web/test_web_cpu2.py [blueroblox-site/index.html]"""
import datetime, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0
FAKE = open(os.path.join(HERE, "fake_supabase.js"), encoding="utf-8").read()


def iso(sec): return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec)).isoformat()


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


STUCK = {"name": "NVIDIA GeForce GTX 1080", "util": 95, "eff": 100, "clk": 139, "clk_max": 1974, "pwr": 10, "pwr_max": 180, "mem_used": 3324, "mem_total": 8192, "temp": 35, "stuck": True}
GOOD = {"name": "NVIDIA GeForce GTX 1070", "util": 15, "clk": 1700, "clk_max": 1987, "pwr": 60, "pwr_max": 230, "mem_used": 4907, "mem_total": 8192, "temp": 56}
BASEM = {"cpu_over": 1.8, "cpu_busy_pct": 85, "cpu_busy": False, "ram_over": 1, "ram_busy_pct": 98, "ram_busy": False, "disk_busy": False, "disk_busy_pct": 90,
         "gpu_busy_pct": 85, "vram_busy_pct": 90, "vram_busy": False, "full_pct": 100}
NEW = dict(BASEM, cpu_pct=6.7, cpu_avg5=7.6, ram_pct=33.4, ram_used=42.7, gpus=[STUCK], gpu_avg5=100, vram_avg5=40.6, gpu_busy=True, disk_data={"used": 101.9, "total": 466.7},
           running=9, cap_ram_full=112, cap_cpu_full=100, fill_pct=36.6, stop=["gpu_stuck"], cpu_threads=72, cpu_sockets=2, cpu_cores=36, cpu_groups=2,
           cpu_name="Intel(R) Xeon(R) CPU E5-2686 v4 @ 2.30GHz", cpu_rule=[100, 2, 4], cpu_sock_pct=[5.1, 8.4], swap_used=0.5, swap_total=24, base="https://s1.cloudblue.vn")
OLD = dict(BASEM, cpu_pct=43.6, cpu_avg5=42, ram_pct=27, ram_used=30.3, gpus=[GOOD], gpu_avg5=14.5, vram_avg5=59.6, gpu_busy=False, disk_data={"used": 58.4, "total": 466.7},
           running=4, cap_ram_full=112, cap_cpu_full=108, fill_pct=46.3, base="https://s2.cloudblue.vn")
ONE = dict(NEW, cpu_pct=51.0, cpu_avg5=50.2, cpu_busy=False, gpus=[GOOD], gpu_avg5=14, gpu_busy=False, stop=["cpu1"], cpu_sock_pct=[97.4, 4.6], cpu_hot5=97.4,
           cpu_hot_pct=95, base="https://s4.cloudblue.vn")
HOT = dict(NEW, cpu_pct=93.0, cpu_avg5=91.0, cpu_busy=True, gpus=[GOOD], gpu_avg5=14, gpu_busy=False, stop=["cpu"], cpu_sock_pct=[95.2, 90.1], swap_used=1.2,
           base="https://s3.cloudblue.vn")
NODES = [
    {"id": "win55", "name": "Server 8", "enabled": True, "updated_at": iso(-20), "created_at": iso(-9e5), "alloc_cpu": 31, "alloc_ram": 41, "cap_cpu": 31, "cap_ram": 41,
     "cpu_total": 72, "ram_total": 127.9, "limit_pct": 90, "phones": 9, "metrics": NEW},
    {"id": "win82", "name": "Server 9", "enabled": True, "updated_at": iso(-30), "created_at": iso(-8e5), "alloc_cpu": 50, "alloc_ram": 34, "cap_cpu": 108, "cap_ram": 112,
     "cpu_total": 56, "ram_total": 127.9, "limit_pct": 90, "phones": 5, "metrics": OLD},
    {"id": "win60", "name": "Server 10", "enabled": True, "updated_at": iso(-15), "created_at": iso(-7e5), "alloc_cpu": 60, "alloc_ram": 70, "cap_cpu": 60, "cap_ram": 112,
     "cpu_total": 72, "ram_total": 127.9, "limit_pct": 90, "phones": 14, "metrics": HOT},
    {"id": "win61", "name": "Server 11", "enabled": True, "updated_at": iso(-15), "created_at": iso(-6e5), "alloc_cpu": 48, "alloc_ram": 60, "cap_cpu": 48, "cap_ram": 112,
     "cpu_total": 72, "ram_total": 127.9, "limit_pct": 90, "phones": 12, "metrics": ONE},
]
DB = {"product_list": [], "products": [], "settings": [{"id": 1, "data": {}}], "topups": [], "orders": [], "vps_machines": [], "pc_machines": [],
      "cloud_phones": [], "cloud_nodes": NODES,
      "cloudphone_pricing": [{"id": 1, "android_versions": "12", "min_ram": 2, "min_cpu": 2, "max_ram": 16, "max_cpu": 32, "price_ram_gb_day": 300, "price_cpu_day": 350, "min_days": 1, "max_days": 90}]}
INIT = """
window.__FAKE_INIT = %s;
window.__FAKE_HOOK = { admin_stats: () => ({ generated_at: '21:50 28/11/2026', revenue_total: 1, customers: 1, top_products: [] }) };
try { localStorage.setItem('br_lang', 'vi'); } catch (e) {}
"""


def main():
    html = open(HTML, encoding="utf-8").read()
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None, args=["--no-sandbox"])
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        ctx.add_init_script(INIT % json.dumps({"admin": True, "db": DB}))
        page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0][:300]))

        def route(r):
            u = r.request.url
            if u.split("#")[0].split("?")[0] in (ORIGIN + "/admin", ORIGIN + "/"): return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            if "supabase-js" in u: return r.fulfill(status=200, content_type="application/javascript", body=FAKE)
            return r.fulfill(status=204, body="")
        page.route("**/*", route)
        page.goto(ORIGIN + "/admin", wait_until="load"); page.wait_for_timeout(2500)
        page.evaluate("""() => { const b = document.querySelector("#adm-tabs button[data-tab='cloud']"); if (b && !b.offsetParent) for (const g of document.querySelectorAll('#adm-grp button[data-grp]')) { g.click(); if (b.offsetParent) break; } }""")
        page.click("#adm-tabs button[data-tab='cloud']"); page.wait_for_timeout(1500)
        page.click('#pane-cloud .subtabs button[data-sub="servers"]'); page.wait_for_timeout(800)
        card = lambda i: page.evaluate("""id => { const c = document.querySelector(`#cpa-nodes .node[data-node="${id}"]`); if (!c) return null;
            return { t: c.innerText.replace(/\\s+/g, ' '), tips: [...c.querySelectorAll('[title]')].map(x => x.getAttribute('title')).join(' | '),
                     pill: (c.querySelector('.nh .pill') || {}).innerText || '', full: c.classList.contains('full') }; }""", i)

        print("1. Server 8 (máy chủ 28/11h · 2 CPU · card kẹt xung)")
        a = card("win55")
        ck("thẻ hiện", a is not None)
        t = (a or {}).get("t", ""); tips = (a or {}).get("tips", "")
        ck("dòng CPU thật ghi đủ '2 CPU · 72 luồng' (không còn trông như 1 CPU)", "CPU thật · 2 CPU · 72 luồng" in t, t[:600])
        ck("thêm dòng % từng CPU: 'CPU 1: 5% · CPU 2: 8%'", "Từng CPU" in t and "CPU 1: 5% · CPU 2: 8%" in t, t[:800])
        ck("đã cấp nhân = 31/100 (sức chứa thật), KHÔNG còn 31/31", "31/100 nhân" in t and "31/31" not in t, t[:900])
        ck("chú thích trần: nhỏ hơn của 100 nhân (CAP_CPU) và 72 luồng × 2 − 4 = 140 → 100 nhân", "72 luồng × 2 − 4 = 140 → 100 nhân" in tips, tips[:900])
        ck("chú thích CPU thật: cộng đủ mọi CPU (2 CPU · 72 luồng · 36 nhân thật · tên CPU)", "cộng đủ mọi CPU của máy (2 CPU · 72 luồng · 36 nhân thật · Intel(R) Xeon(R) CPU E5-2686 v4" in tips, tips[:900])
        ck("RAM: 'RAM chính (thật)' + 'Đã cấp · theo RAM chính …' 41/112 GB, không còn 'chung ×1' / 41/41",
           "RAM chính (thật)" in t and "Đã cấp · theo RAM chính · ngừng khi RAM thật ≥ 98%" in t and "41/112 GB" in t and "chung ×1" not in t and "41/41" not in t, t[:1200])
        ck("dòng RAM ảo riêng: 'RAM ảo · chỉ dùng khi RAM chính đầy 0.5/24 GB' + chú thích bán theo RAM chính",
           "RAM ảo · chỉ dùng khi RAM chính đầy" in t and "0.5/24 GB" in t and "KHÔNG tính RAM ảo" in tips, t[:1400])
        ck("nhãn trạng thái: 'Card kẹt xung' (không còn 'Tự ngừng · 100%' / 'VGA quá tải 100%')", (a or {}).get("pill") == "Card kẹt xung", (a or {}).get("pill"))
        ck("dòng lý do: '⏸ Ngừng nhận máy mới vì card đồ hoạ kẹt xung nghỉ — CPU, RAM chính vẫn còn trống'",
           "⏸ Ngừng nhận máy mới vì card đồ hoạ kẹt xung nghỉ — CPU, RAM chính vẫn còn trống" in t, t[:1200])

        print("2. Server 9 (máy chủ bản cũ, chưa báo số CPU / lý do)")
        b = card("win82"); tb = (b or {}).get("t", "")
        ck("thẻ hiện như cũ: 'CPU thật' không ghi số luồng, không có dòng từng CPU / RAM ảo / lý do", b is not None and "CPU thật 43.6%" in tb and "luồng" not in tb.split("TB 5 phút")[0]
           and "Từng" not in tb and "RAM ảo" not in tb and "Ngừng nhận máy mới vì" not in tb, tb[:900])
        ck("đã cấp 50/108 nhân · RAM 'Đã cấp · theo RAM chính' 34/112 GB · nhãn 'Đang chạy · 46%'", "50/108 nhân" in tb and "Đã cấp · theo RAM chính" in tb and "34/112 GB" in tb
           and (b or {}).get("pill") == "Đang chạy · 46%", (tb[:900], (b or {}).get("pill")))

        print("3. Server 10 (CPU thật nóng 91%)")
        c = card("win60"); tc = (c or {}).get("t", "")
        ck("nhãn 'CPU nóng 91%' · lý do 'CPU thật nóng' (không ghi 'còn trống')", (c or {}).get("pill") == "CPU nóng 91%" and "⏸ Ngừng nhận máy mới vì CPU thật nóng" in tc
           and "vẫn còn trống" not in tc, ((c or {}).get("pill"), tc[:900]))
        ck("% từng CPU khi nóng: 'CPU 1: 95% · CPU 2: 90%'", "CPU 1: 95% · CPU 2: 90%" in tc, tc[:900])

        print("4. Server 11 (TB cả máy 50% nhưng 1 CPU đã 97% — máy khách dồn vào 1 CPU)")
        e = card("win61"); te = (e or {}).get("t", "")
        ck("nhãn '1 CPU nóng 97%' · lý do '1 CPU gần đầy (máy khách dồn vào 1 CPU)' (không ghi 'còn trống') · từng CPU 97% / 5%",
           (e or {}).get("pill") == "1 CPU nóng 97%" and "⏸ Ngừng nhận máy mới vì 1 CPU gần đầy (máy khách dồn vào 1 CPU)" in te and "vẫn còn trống" not in te
           and "CPU 1: 97% · CPU 2: 5%" in te, ((e or {}).get("pill"), te[:900]))

        print("5. máy chủ ngừng nhận (admin bấm) → không chồng thêm dòng lý do")
        page.evaluate("() => { NODES.find(n => n.id === 'win55').enabled = false; renderNodes(); }"); page.wait_for_timeout(150)
        d = card("win55"); td = (d or {}).get("t", "")
        ck("đang 'Ngừng nhận máy' → chỉ dòng ngừng của admin, không có dòng '⏸ Ngừng nhận máy mới vì …'", "Ngừng nhận máy mới vì" not in td, td[:700])
        ck("không lỗi JavaScript", not errors, errors)
        br.close()
    print(f"\n{OK}/{OK + FAIL} đạt")
    sys.exit(0 if FAIL == 0 else 1)


main()
