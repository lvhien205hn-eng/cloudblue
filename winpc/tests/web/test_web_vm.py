# -*- coding: utf-8 -*-
"""Thử phần 🧩 VPS ẢO HOÁ trên web (SQL v56) + bỏ 2 thẻ quản trị (Máy VPS · Dàn máy nội bộ).
   Chrome thật (Playwright) + Supabase giả (fake_supabase.js của kho) + hàm vm_* giả trong trang; không gọi ra ngoài.
   python3 winpc/tests/web/test_web_vm.py [blueroblox-site/index.html] [thư mục ảnh]"""
import datetime, json, os, sys, tempfile, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_supabase.js")
HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "..", "blueroblox-site", "index.html")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(), "cb-web-vm-shots")      # không ghi ảnh vào thư mục web (Vercel)
os.makedirs(SHOTS, exist_ok=True)
ORIGIN = "https://cloudblue.test"
OK = FAIL = 0
H1, H2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
VPC1, VPC2, VPC3, GPC = ("00000000-0000-4000-8000-00000000a%03d" % i for i in (1, 2, 3, 9))


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:900])


def iso(sec_from_now):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=sec_from_now)).isoformat()


PLANS = [("vps1-1", "VPS 1-1", 1, 1024, 100000), ("vps1-2", "VPS 1-2", 1, 2048, 110000), ("vps2-2", "VPS 2-2", 2, 2048, 170000), ("vps2-4", "VPS 2-4", 2, 4096, 240000),
         ("vps3-3", "VPS 3-3", 3, 3072, 270000), ("vps4-4", "VPS 4-4", 4, 4096, 360000), ("vps4-8", "VPS 4-8", 4, 8192, 420000), ("vps8-16", "VPS 8-16", 8, 16384, 780000)]
IMAGES = [("win2012r2", "Windows Server 2012 R2", "tpl-win2012r2", 1024), ("win10ltsc", "Windows 10 LTSC 2021 (nhẹ)", "tpl-win10ltsc", 2048),
          ("win2016", "Windows Server 2016", "tpl-win2016", 2048), ("win2019", "Windows Server 2019", "tpl-win2019", 2048), ("win2022", "Windows Server 2022", "tpl-win2022", 2048)]
READY = {"win2012r2", "win10ltsc"}


def plan_rows(admin=False):
    out = []
    for i, (pid, nm, c, r, pr) in enumerate(PLANS):
        x = {"id": pid, "name": nm, "cores": c, "ram_mb": r, "disk_gb": 20, "note": "", "prices": [] if pid == "vps4-8" else [{"days": 30, "price": pr}]}   # 4-8: chủ shop chưa nhập giá
        if admin: x.update(enabled=True, sort=i + 1, product_id="p-" + pid, product_name="VPS ảo hoá · " + nm)
        else: x["free"] = pid != "vps8-16"
        out.append(x)
    return out


def img_rows(admin=False):
    out = []
    for i, (iid, nm, tpl, ram) in enumerate(IMAGES):
        x = {"id": iid, "name": nm, "min_disk": 20, "min_ram": ram}
        if admin: x.update(tpl=tpl, enabled=True, sort=i + 1)
        else: x["ready"] = iid in READY
        out.append(x)
    return out


SHOP = {"sell": True, "admin": False, "plans": plan_rows(), "images": img_rows(), "reinstall_max": 3, "grace_days": 3}
MY = {"items": [
    {"id": 12, "pc": VPC1, "name": "VPS-12", "label": "Treo game", "plan": "vps2-4", "plan_name": "VPS 2-4", "cores": 2, "ram_mb": 4096, "disk_gb": 20, "image": "win10ltsc",
     "image_name": "Windows 10 LTSC 2021 (nhẹ)", "status": "running", "want": "running", "err": False, "busy": False, "online": True, "until": iso(20 * 86400), "expired": False,
     "delete_at": None, "left": 3, "created_at": iso(-86400), "prices": [{"days": 7, "price": 70000}, {"days": 30, "price": 240000}]},
    {"id": 13, "pc": VPC2, "name": "VPS-13", "label": "", "plan": "vps1-1", "plan_name": "VPS 1-1", "cores": 1, "ram_mb": 1024, "disk_gb": 20, "image": "win2012r2",
     "image_name": "Windows Server 2012 R2", "status": "creating", "want": "running", "err": False, "busy": True, "online": False, "until": None, "expired": False,
     "delete_at": None, "left": 3, "created_at": iso(-120), "prices": [{"days": 30, "price": 100000}]},
    {"id": 14, "pc": VPC3, "name": "<img src=x onerror=window.__xss=1>", "label": "", "plan": "vps1-2", "plan_name": "VPS 1-2", "cores": 1, "ram_mb": 2048, "disk_gb": 20,
     "image": "win2012r2", "image_name": "Windows Server 2012 R2", "status": "stopped", "want": "stopped", "err": False, "busy": False, "online": False, "until": iso(-3600),
     "expired": True, "delete_at": iso(2 * 86400), "left": 0, "created_at": iso(-40 * 86400), "prices": [{"days": 30, "price": 110000}]}],
    "images": [{"id": i[0], "name": i[1], "min_disk": 20, "min_ram": i[3]} for i in IMAGES]}
GPU_MINE = {"product": "x", "reinstall_max": 2, "os": [], "power": True, "cancel": True, "items": [
    {"rental": None, "state": "active", "os": "", "os_name": "", "until": iso(20 * 86400), "left": 0, "used": 0,
     "pc": {"id": VPC1, "name": "VPS-12", "code": "", "os": "", "online": True, "link": True, "remote": True, "off": False, "job": None, "last_job": None, "gpus": []}},
    {"rental": 7, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": iso(6 * 86400), "left": 2, "used": 0,
     "pc": {"id": GPC, "name": "May-GPU-01", "code": "A1", "os": "22h2", "online": True, "link": True, "remote": True, "off": False, "job": None, "last_job": None, "gpus": ["GTX 1080"]}}]}


def adm_state():
    return {"settings": {"sell": False, "auto_approve": False, "grace_days": 3, "reinstall_max": 3, "cpu_over": 3, "ram_reserve_mb": 4096, "disk_over": 1.5, "create_min": 40},
            "hosts": [{"id": H1, "name": "pve1", "status": "ready", "slots": 40, "online": True, "last_seen": iso(-5), "pub_ip": "14.160.1.2", "note": "", "created_at": iso(-86400 * 3),
                       "info": {"host": "pve1", "pve": "9.2", "cpu": "Intel Xeon E5-2696 v4", "threads": 44, "ram_mb": 131072, "disk_gb": 1800, "kvm": True, "ver": "24/11a", "lan_ip": "192.168.1.50"},
                       "metrics": {"cpu": 12.5, "ram_used_mb": 40960, "running": 3, "tpl": ["tpl-win10ltsc", "tpl-win2012r2"], "ver": "24/11a"},
                       "used": {"n": 3, "cores": 5, "ram_mb": 7168, "disk_gb": 60}},
                      {"id": H2, "name": "pve-<b>2</b>", "status": "new", "slots": 60, "online": True, "last_seen": iso(-20), "pub_ip": "14.160.1.3", "note": "", "created_at": iso(-600),
                       "info": {"host": "pve2", "pve": "9.2", "cpu": "AMD EPYC 7542", "threads": 64, "ram_mb": 262144, "disk_gb": 3600, "kvm": True, "ver": "24/11a", "lan_ip": "192.168.1.51"},
                       "metrics": {"cpu": 1, "ram_used_mb": 4096, "running": 0, "tpl": [], "tpl_auto": [{"tag": "win2016", "state": "installing", "min": 12}, {"tag": "win2012r2", "state": "saving"},
                                   {"tag": "<i>x</i>", "state": "error", "err": "tạo máy ảo lỗi <script>"}]}, "used": {"n": 0, "cores": 0, "ram_mb": 0, "disk_gb": 0}}],
            "plans": plan_rows(True), "images": img_rows(True), "products": [],
            "vps": [{"id": 12, "user": "khachA", "plan": "vps2-4", "image": "win10ltsc", "cores": 2, "ram_mb": 4096, "disk_gb": 20, "host": H1, "slot": 1, "pc": VPC1, "status": "running",
                     "want": "running", "inst_gen": 1, "inst_done": 1, "err": "", "end_why": "", "until": iso(20 * 86400), "left": 3, "label": "Treo game", "created_at": iso(-86400),
                     "started_at": iso(-86000), "deleted_at": None, "online": True, "order": "o-12"},
                    {"id": 13, "user": "khachB", "plan": "vps1-1", "image": "win2012r2", "cores": 1, "ram_mb": 1024, "disk_gb": 20, "host": H1, "slot": 2, "pc": VPC2, "status": "error",
                     "want": "running", "inst_gen": 1, "inst_done": 0, "err": "nhân bản lỗi: storage full", "end_why": "", "until": None, "left": 3, "label": "", "created_at": iso(-3600),
                     "started_at": None, "deleted_at": None, "online": False, "order": "o-13"},
                    {"id": 11, "user": "chushop", "plan": "vps2-2", "image": "win10ltsc", "cores": 2, "ram_mb": 2048, "disk_gb": 20, "host": H1, "slot": 3, "pc": VPC3, "status": "stopped",
                     "want": "stopped", "inst_gen": 1, "inst_done": 1, "err": "", "end_why": "", "until": iso(300 * 86400), "left": 3, "label": "", "created_at": iso(-86400 * 2),
                     "started_at": iso(-86400 * 2), "deleted_at": None, "online": False, "order": None}]}


REV = {"ok": True, "months": [
    {"month": "2026-11", "closed": False, "rows": [{"host": H1, "name": "pve1", "amount": 140000, "vps": 2, "cash": 840000, "pays": 2}], "amount_total": 140000, "cash_total": 840000},
    {"month": "2026-10", "closed": True, "rows": [{"host": H1, "name": "pve1", "amount": 90000, "vps": 1, "cash": 0, "pays": 0}], "amount_total": 90000, "cash_total": 0},
    {"month": "2026-09", "closed": True, "rows": [], "amount_total": 0, "cash_total": 0}]}

HOOK = """(() => { const V = window.__VM; const c = v => JSON.parse(JSON.stringify(v));
  const miss = n => ({ data: null, error: { code: 'PGRST202', message: 'Could not find the function public.' + n + ' in the schema cache' } });
  const raise = m => ({ data: null, error: { code: 'P0001', message: m } });
  window.__FAKE_HOOK = Object.assign(window.__FAKE_HOOK || {}, {
    vm_shop_info: () => V.miss ? miss('vm_shop_info') : c(V.shop),
    vm_my: () => V.miss ? miss('vm_my') : c(V.my),
    pc_my_vps: () => c(V.gpu),
    pc_shop_info: () => ({ on: false }),
    cp_shared_with_me: () => [{ id: 'cp-s', name: 'Máy được chia sẻ', shared: true, share_id: 9, status: 'active', android: '9', ram: 2, cpu: 2, expires_at: new Date(Date.now() + 3 * 864e5).toISOString() }],
    cloudphone_rename: a => ({ ok: true }),
    vm_buy: a => V.buyErr ? raise(V.buyErr) : ({ ok: true, id: 15, pc: 'pc-15', order: 'o-15', total: 170000 }),
    vm_my_power: a => ({ ok: true, act: a.p_act }),
    vm_my_reinstall: a => ({ ok: true, left: 2, image: a.p_image }),
    vm_my_renew: a => ({ ok: true, until: new Date(Date.now() + 50 * 864e5).toISOString(), order: 'o-r', total: 240000 }),
    vm_my_label: a => ({ ok: true, label: a.p_label }),
    vm_buy_custom: a => V.buyErr ? raise(V.buyErr) : ({ ok: true, id: 17, pc: 'pc-17', order: 'o-17', total: 112000 }),
    vm_my_upgrade: a => V.upErr ? raise(V.upErr) : a.p_dry ? ({ ok: true, dry: true, price: (a.p_cores - 2) * 8000 * 2 / 3 + (a.p_disk_gb - 20) * 1000 * 2 / 3 || 1000, days_left: 20, restart: a.p_cores !== 2 || a.p_ram_gb !== 4 })
      : ({ ok: true, price: 5000, order: 'o-u', restart: a.p_cores !== 2 || a.p_ram_gb !== 4, days_left: 20 }),
    vm_my_cancel: a => ({ ok: true }),
    vm_admin_state: () => V.admErr ? raise(V.admErr) : V.miss ? miss('vm_admin_state') : c(V.adm),
    vm_admin_revenue: () => V.miss ? miss('vm_admin_revenue') : c(V.rev),
    vm_admin_host: a => { const h = V.adm.hosts.find(x => x.id === a.p_id); if (!h) return raise('NO_HOST');
      if (a.p_patch.approve && h.status === 'new') h.status = 'ready'; else if (a.p_patch.status) h.status = a.p_patch.status;
      if (a.p_patch.delete) { V.adm.hosts = V.adm.hosts.filter(x => x !== h); return { ok: true, deleted: true }; }
      if (a.p_patch.name) h.name = a.p_patch.name; if (a.p_patch.slots) h.slots = +a.p_patch.slots; if ('note' in a.p_patch) h.note = a.p_patch.note; return { ok: true }; },
    vm_admin_settings: a => { Object.assign(V.adm.settings, a.p_patch); V.shop.sell = !!V.adm.settings.sell; return c(V.adm.settings); },
    vm_admin_plan: a => { if (a.p_patch.delete) { V.adm.plans = V.adm.plans.filter(p => p.id !== a.p_id); return { ok: true }; }
      let p = V.adm.plans.find(x => x.id === a.p_id); if (!p) { p = { id: a.p_id, enabled: true, sort: 0, prices: [] }; V.adm.plans.push(p); }
      Object.assign(p, a.p_patch); return c(p); },
    vm_admin_image: a => { let i = V.adm.images.find(x => x.id === a.p_id); if (!i) { i = { id: a.p_id }; V.adm.images.push(i); } Object.assign(i, a.p_patch); return c(i); },
    vm_admin_vps: a => { const v = V.adm.vps.find(x => x.id === a.p_id); if (!v) return raise('NO_VPS');
      if (a.p_act === 'stop') v.want = 'stopped'; if (a.p_act === 'start') v.want = 'running'; if (a.p_act === 'delete' || a.p_act === 'refund') v.status = 'deleted';
      if (a.p_act === 'config') { v.cores = a.p_arg.cores; v.ram_mb = a.p_arg.ram_mb; v.disk_gb = a.p_arg.disk_gb; v.cfg_gen = (v.cfg_gen || 0) + 1; }
      return { ok: true, act: a.p_act, refunded: a.p_act === 'refund' }; },
    vm_admin_give: a => V.giveErr ? raise(V.giveErr) : ({ ok: true, id: 16, pc: 'pc-16', host: '%s', slot: 4 }),
    vm_tpl_state: () => V.tpl === null ? miss('vm_tpl_state') : c(V.tpl),
    vm_tpl_new: a => { if (V.tplErr) return raise(V.tplErr); const h = V.tpl.hosts.find(x => x.id === a.p_host), i = V.tpl.images.find(x => x.id === a.p_image);
      const j = { id: 40 + V.tpl.jobs.length, host: a.p_host, host_name: h.name, image: a.p_image, image_name: i.name, tpl: i.tpl, src: a.p_src, iso: a.p_iso || '',
        cores: 2, ram_mb: 2048, disk_gb: 20, pc: null, want: 'running', status: 'creating', err: '', enrolled: false, online: false };
      V.tpl.jobs.unshift(j); return c(j); },
    vm_tpl_act: a => { const j = V.tpl.jobs.find(x => x.id === a.p_id); if (!j) return raise('NOT_FOUND');
      if (a.p_act === 'save') { j.want = 'save'; j.status = 'saving'; } else if (a.p_act === 'cancel') j.want = 'cancel'; else if (a.p_act === 'retry') { j.status = 'creating'; j.err = ''; }
      return c(j); }
  }); })();""" % H1


class Site:
    def __init__(self, browser, html, admin, vm, path="/", vp=(1360, 900), products=None):
        self.errors = []
        self.ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
        prods = products or []
        phones = [{"id": "cp-1", "name": "Máy farm 1", "user_id": "00000000-0000-4000-8000-000000000001", "status": "active", "android": "12", "ram": 4, "cpu": 2,
                   "expires_at": iso(5 * 86400), "created_at": iso(-86400), "is_free": False}]
        init = {"admin": admin, "db": {"product_list": prods, "products": prods, "cloud_phones": phones,
                                       "pc_machines": [{"id": GPC, "name": "May-GPU-01", "approved": True, "created_at": iso(-9e5)}]}}
        self.ctx.add_init_script("window.__FAKE_INIT = %s; window.__VM = %s; %s try { localStorage.setItem('br_lang', 'vi'); localStorage.setItem('br_lite', '1'); } catch (e) {}"
                                 % (json.dumps(init), json.dumps(vm), HOOK))
        self.page = self.ctx.new_page(); self.html = html; self.fake = open(FAKE, encoding="utf-8").read()
        self.page.route("**/*", self.route)
        self.page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e).splitlines()[0][:300]))
        self.page.on("console", lambda m: self.errors.append("console: " + m.text[:300]) if m.type == "error" and "Failed to load resource" not in m.text else None)
        self.answer = None                                           # câu trả lời cho hộp prompt có sẵn của trang (Đổi tên ĐT đám mây)
        self.page.on("dialog", self.on_dialog)
        self.page.goto(ORIGIN + path, wait_until="load")
        self.page.wait_for_timeout(2200)

    def on_dialog(self, d):
        if d.type == "prompt" and self.answer is not None: d.accept(self.answer); return
        self.errors.append("DIALOG: " + d.message); d.dismiss()

    def route(self, route):
        u = route.request.url
        if u in (ORIGIN + "/admin", ORIGIN + "/"): return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=self.html)
        if "supabase-js" in u: return route.fulfill(status=200, content_type="application/javascript", body=self.fake)
        return route.fulfill(status=204, body="")

    def js(self, expr, arg=None): return self.page.evaluate(expr, arg)
    def calls(self, name): return self.js("n => window.__FAKE.calls.filter(c => c.kind === 'rpc' && c.name === n).map(c => c.args)", name)
    def txt(self, sel): return self.js("q => { const e = document.querySelector(q); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)
    def vis(self, sel): return self.js("q => { const e = document.querySelector(q); if (!e) return false; const r = e.getBoundingClientRect(); return !e.closest('[hidden]') && r.width > 0 && r.height > 0; }", sel)
    def dlg(self): return self.txt("#vzdlg:not([hidden]) .dlg") or ""
    def shot(self, name, full=False): self.page.screenshot(path=os.path.join(SHOTS, name), full_page=full)
    def close(self): self.ctx.close()


TPC = "00000000-0000-4000-8000-00000000b001"
ISO = "local:iso/CloudBlue-MayMau-win2012r2.iso"
def tpl_state(err=False):
    d = {"hosts": [{"id": H1, "name": "pve1", "status": "ready", "online": True, "tpl": ["tpl-win10ltsc", "tpl-win2012r2"], "ver": "26/11a",
                       "iso": [{"volid": ISO, "size": 4500000000}, {"volid": "local:iso/virtio-win-0.1.240.iso", "size": 627000000}]}],
            "images": [{"id": i[0], "name": i[1], "tpl": i[2], "min_ram": i[3], "enabled": True} for i in IMAGES],
            "jobs": [{"id": 31, "host": H1, "host_name": "pve1", "image": "win2022", "image_name": "Windows Server 2022", "tpl": "tpl-win2022", "src": "iso",
                      "iso": "local:iso/CloudBlue-MayMau-win2022.iso", "cores": 2, "ram_mb": 2048, "disk_gb": 20, "pc": TPC, "want": "running", "status": "ready", "err": "",
                      "enrolled": True, "online": True, "created_at": iso(-3600)},
                     {"id": 30, "host": H1, "host_name": "pve1", "image": "win2016", "image_name": "Windows Server 2016", "tpl": "tpl-win2016", "src": "iso",
                      "iso": "local:iso/x.iso", "cores": 2, "ram_mb": 2048, "disk_gb": 20, "pc": None, "want": "running", "status": "error", "err": "tạo máy ảo lỗi: volume does not exist",
                      "enrolled": False, "online": False, "created_at": iso(-7200)},
                     {"id": 29, "host": H1, "host_name": "pve1", "image": "win10ltsc", "image_name": "Windows 10 LTSC", "tpl": "tpl-win10ltsc", "src": "tpl", "iso": "",
                      "cores": 2, "ram_mb": 2048, "disk_gb": 20, "pc": None, "want": "save", "status": "saved", "err": "", "enrolled": False, "online": False,
                      "created_at": iso(-90000), "done_at": iso(-86000)}]}
    if not err: d["jobs"] = [j for j in d["jobs"] if j["status"] != "error"]
    return d


CUST = {"on": True, "unit_cpu": 8000, "unit_ram": 12000, "unit_disk": 1000, "disk_free_gb": 20, "short_up": 0, "days": [1, 3, 7, 30], "max_cores": 16, "max_ram_gb": 32,
        "max_disk_gb": 200, "room": {"cores": 40, "ram_gb": 100, "disk_gb": 500}}


def v59(d, maint=False):
    """Dữ liệu trả về sau khi đã chạy SQL v59: khối custom (đơn giá) · bảo trì · nâng cấp · lần đổi cấu hình."""
    d["shop"].update(custom=json.loads(json.dumps(CUST)), upgrade=True, maint=maint, v=59)
    d["my"].update(custom=json.loads(json.dumps(CUST)), upgrade=True, maint=maint, v=59)
    for x in d["my"]["items"]: x["cfg_busy"] = False
    d["adm"]["settings"].update(unit_cpu=8000, unit_ram=12000, unit_disk=1000, disk_free_gb=20, short_up=0, day_tiers=[1, 3, 7, 30], custom_on=True, upgrade_on=True,
                                max_cores=16, max_ram_gb=32, max_disk_gb=200)
    for v in d["adm"]["vps"]: v.update(cfg_gen=0, cfg_done=0)
    return d


def vm_data(**kw):
    d = {"shop": json.loads(json.dumps(SHOP)), "my": json.loads(json.dumps(MY)), "gpu": json.loads(json.dumps(GPU_MINE)), "adm": adm_state(), "rev": REV, "miss": False,
         "tpl": tpl_state()}
    d.update(kw)
    return d


def admin_open(s, sub=None):
    s.page.click('#adm-grp button[data-grp="mach"]'); s.page.wait_for_timeout(250)
    s.page.click('#adm-tabs button[data-tab="vm"]'); s.page.wait_for_timeout(700)
    if sub: s.page.click('#pane-vm .subtabs button[data-sub="%s"]' % sub); s.page.wait_for_timeout(250)


def main():
    html = open(HTML, encoding="utf-8").read()
    prods = [{"id": "p-vm", "cat": "vm", "name": "VPS ảo hoá · VPS 1-1", "price": 100000, "plans": [{"days": 30, "price": 100000}], "features": [], "hot": False, "sort": 901, "manual": True, "stock": 100000},
             {"id": "p-clone", "cat": "clone", "name": "Clone Roblox", "price": 5000, "plans": [], "features": [], "hot": False, "sort": 1, "manual": True, "stock": 50}]
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

        print("1. Quản trị: bỏ 2 thẻ cũ, thêm 🧩 VPS ảo hoá")
        s = Site(br, html, True, vm_data(), path="/admin", vp=(1600, 1000))
        tabs = s.js("() => [...document.querySelectorAll('#adm-tabs button[data-tab]')].map(b => b.dataset.tab)")
        grp = s.js("() => window.ADMNAV.groups().find(g => g.id === 'mach')")
        ck("không còn thẻ 'Máy VPS' (vps) / 'Dàn máy nội bộ' (biz); có thẻ 'vm'", "vps" not in tabs and "biz" not in tabs and "vm" in tabs, tabs)
        ck("nhóm 🖥️ Máy cho thuê = ĐT đám mây · Máy PC · VPS ảo hoá (không sinh nhóm 'Khác')", grp and grp["m"] == ["cloud", "pc", "vm"]
           and not s.js("() => !!document.querySelector('#adm-grp button[data-grp=\"more\"]')"), grp)
        ck("số trên thẻ VPS ảo hoá = 1 máy chủ chờ duyệt + 1 VPS lỗi = 2", s.js("() => document.getElementById('vm-badge').textContent") == "2" and not s.js("() => document.getElementById('vm-badge').hidden"))
        admin_open(s)
        ck("bấm thẻ → hiện khung VPS ảo hoá, khung khác ẩn", s.vis("#pane-vm") and not s.vis("#pane-pc") and not s.vis("#pane-vps") and not s.vis("#pane-biz"))
        top = s.txt("#vma-top")
        ck("đầu khung: máy chủ 2/2 liên lạc · 1 chờ duyệt · VPS 1/3 chạy · doanh thu T11 140.000đ · đã thu 840.000đ · CHƯA BÁN · 7 gói có giá + nút Bật bán",
           "2/2" in top and "1 chờ duyệt" in top and "1/3" in top and "140.000đ" in top and "840.000đ" in top and "CHƯA BÁN" in top and "7 gói có giá" in top and "Bật bán" in top, top)
        h1 = s.txt('[data-vmhost="%s"]' % H1); h2 = s.txt('[data-vmhost="%s"]' % H2)
        ck("máy chủ pve1: đang nhận VPS, CPU / RAM / ổ, 3/40 chỗ, vCPU bán 5/132, máy mẫu ✓ 2012 R2 ✓ LTSC ✗ 2022, IP, doanh thu",
           "Đang nhận VPS" in h1 and "Xeon E5-2696 v4" in h1 and "3 / 40" in h1 and "5 / 132" in h1 and "✓ tpl-win2012r2" in h1 and "✓ tpl-win10ltsc" in h1 and "✗ tpl-win2022" in h1
           and "14.160.1.2" in h1 and "192.168.1.50" in h1 and "140.000đ" in h1 and "840.000đ" in h1, h1)
        ck("pve1: nút 🔧 Trang Proxmox → https://192.168.1.50:8006 (mở tab mới)", s.js("id => { const a = document.querySelector('[data-vmhost=\"' + id + '\"] a[href^=\"https://192.168.1.50:8006\"]'); return !!a && a.target === '_blank'; }", H1))
        ck("máy chủ mới: viền vàng 'Chờ duyệt' + nút ✅ Duyệt; tên lạ không chạy mã", "Chờ duyệt" in h2 and "Duyệt máy này" in h2 and "<b>2</b>" in h2
           and s.js("id => document.querySelector('[data-vmhost=\"' + id + '\"]').classList.contains('new')", H2))
        ck("máy chủ cài bằng ISO CloudBlue-Proxmox: thẻ báo đang TỰ dựng máy mẫu (bản nào, đang cài mấy phút / đang chuyển thành mẫu / lỗi gì); chữ lạ không chạy mã; máy không tự dựng thì không có dòng này",
           "TỰ dựng máy mẫu" in h2 and "win2016 đang cài Windows (12 phút)" in h2 and "win2012r2 cài xong, đang chuyển thành máy mẫu" in h2 and "lỗi: tạo máy ảo lỗi <script>" in h2
           and "<i>x</i>" in h2 and "TỰ dựng" not in h1 and not s.js("() => document.querySelector('.vma-auto i, .vma-auto script')"), h2)
        s.shot("vm-1-hosts.png")
        s.page.click('[data-vmhost="%s"] [data-vmah="approve"]' % H2); s.page.wait_for_timeout(500)
        ck("bấm Duyệt → vm_admin_host {approve: true} → máy chuyển 'Đang nhận VPS', số trên thẻ còn 1", s.calls("vm_admin_host") == [{"p_id": H2, "p_patch": {"approve": True}}]
           and "Đang nhận VPS" in s.txt('[data-vmhost="%s"]' % H2) and s.js("() => document.getElementById('vm-badge').textContent") == "1", s.calls("vm_admin_host"))
        s.page.click('[data-vmhost="%s"] [data-vmah="maint"]' % H1); s.page.wait_for_timeout(400)
        ck("bấm Bảo trì → vm_admin_host {status: maint}", s.calls("vm_admin_host")[-1] == {"p_id": H1, "p_patch": {"status": "maint"}}, s.calls("vm_admin_host"))
        s.page.click('[data-vmhost="%s"] [data-vmah="edit"]' % H1); s.page.wait_for_timeout(200)
        s.page.fill("#vma-h-slots", "50"); s.page.fill("#vma-h-note", "phòng máy 2"); s.page.click("#vma-h-go"); s.page.wait_for_timeout(400)
        ck("sửa tên · số chỗ · ghi chú → vm_admin_host {name, slots, note}", s.calls("vm_admin_host")[-1] == {"p_id": H1, "p_patch": {"name": "pve1", "slots": "50", "note": "phòng máy 2"}}
           and not s.vis("#vzdlg"), s.calls("vm_admin_host")[-1])
        ck("nút Xoá máy chủ bị khoá khi còn VPS", s.js("id => document.querySelector('[data-vmhost=\"' + id + '\"] [data-vmah=\"del\"]').disabled", H1))

        print("2. Quản trị › VPS")
        admin_open(s, "vps")
        rows = s.js("() => [...document.querySelectorAll('#vma-vps .vma-vps')].map(r => r.innerText.replace(/\\s+/g, ' '))")
        ck("3 VPS: VPS-12 đang chạy (khachA, 2 vCPU, Win LTSC, pve1 chỗ 1) · VPS-13 lỗi kèm lý do · VPS-11 đã tắt", len(rows) == 3 and "VPS-12" in rows[0] and "khachA" in rows[0]
           and "Đang chạy" in rows[0] and "pve1" in rows[0] and "storage full" in rows[1] and "Lỗi" in rows[1] and "Đã tắt" in rows[2], rows)
        ck("VPS chạy: nút ▶ Điều khiển → play.html?pc=<máy ảo>; VPS lỗi có nút ⟳ Tạo lại; VPS không có đơn không có nút Hoàn tiền",
           s.js("p => !!document.querySelector('[data-vmv=\"12\"] a[href=\"/play.html?pc=' + p + '\"]')", VPC1) and s.js("() => !!document.querySelector('[data-vmv=\"13\"] [data-vmav=\"retry\"]')")
           and not s.js("() => !!document.querySelector('[data-vmv=\"11\"] [data-vmav=\"refund\"]')"))
        s.page.fill("#vma-q", "khachb"); s.page.wait_for_timeout(200)
        ck("ô tìm: 'khachb' → chỉ VPS-13", s.js("() => [...document.querySelectorAll('#vma-vps .vma-vps')].map(r => r.dataset.vmv)") == ["13"])
        s.page.fill("#vma-q", ""); s.page.wait_for_timeout(150)
        s.shot("vm-2-vps.png")
        s.page.click('[data-vmv="12"] [data-vmav="stop"]'); s.page.wait_for_timeout(200)
        ck("bấm Tắt → hộp xác nhận riêng (không dùng hộp của trình duyệt)", "Tắt VPS-12" in s.dlg(), s.dlg())
        s.page.click("#vma-v-go"); s.page.wait_for_timeout(500)
        ck("xác nhận → vm_admin_vps {12, stop}", s.calls("vm_admin_vps") == [{"p_id": 12, "p_act": "stop", "p_arg": {}}], s.calls("vm_admin_vps"))
        s.page.click('[data-vmv="12"] [data-vmav="extend"]'); s.page.wait_for_timeout(200); s.page.fill("#vma-v-days", "-2"); s.page.click("#vma-v-go"); s.page.wait_for_timeout(400)
        s.page.click('[data-vmv="12"] [data-vmav="reinstall"]'); s.page.wait_for_timeout(200); s.page.select_option("#vma-v-img", "win2012r2"); s.page.click("#vma-v-go"); s.page.wait_for_timeout(400)
        s.page.click('[data-vmv="13"] [data-vmav="refund"]'); s.page.wait_for_timeout(200); s.page.click("#vma-v-go"); s.page.wait_for_timeout(400)
        c = s.calls("vm_admin_vps")
        ck("trừ 2 ngày · cài lại Server 2012 R2 · hoàn tiền + xoá VPS-13 → đúng lệnh", c[1:] == [{"p_id": 12, "p_act": "extend", "p_arg": {"days": -2}},
           {"p_id": 12, "p_act": "reinstall", "p_arg": {"image": "win2012r2"}}, {"p_id": 13, "p_act": "refund", "p_arg": {}}], c)

        print("3. Quản trị › Gói & giá · Bản Windows · Cài đặt")
        admin_open(s, "plans")
        pt = s.txt("#vma-plans")
        ck("bảng 8 gói: 1-1 = 100.000đ … 8-16 = 780.000đ; gói chưa nhập giá (4-8) ghi đỏ 'chưa có giá — khách chưa thấy'", s.js("() => document.querySelectorAll('#vma-plans tbody tr').length") == 8
           and "30n: 100.000đ" in pt and "30n: 780.000đ" in pt and "chưa có giá — khách chưa thấy" in pt, pt)
        s.page.click('[data-vmap="vps1-1"]'); s.page.wait_for_timeout(200)
        s.page.fill('#vma-p-rows .vms-row:nth-child(1) [data-pr="p"]', "120000"); s.page.click("#vma-p-add")
        s.page.fill('#vma-p-rows .vms-row:nth-child(2) [data-pr="d"]', "7"); s.page.fill('#vma-p-rows .vms-row:nth-child(2) [data-pr="p"]', "40000")
        s.shot("vm-3-plan.png")
        s.page.click("#vma-p-go"); s.page.wait_for_timeout(500)
        pc = s.calls("vm_admin_plan")
        ck("sửa gói 1-1: giá 30 ngày 120.000đ + thêm 7 ngày 40.000đ → vm_admin_plan (cấu hình giữ nguyên)", pc and pc[-1]["p_id"] == "vps1-1"
           and pc[-1]["p_patch"]["prices"] == [{"days": 30, "price": 120000}, {"days": 7, "price": 40000}] and pc[-1]["p_patch"]["cores"] == 1 and pc[-1]["p_patch"]["ram_mb"] == 1024
           and pc[-1]["p_patch"]["disk_gb"] == 20, pc)
        s.page.click("#vma-p-new"); s.page.wait_for_timeout(200); s.page.fill("#vma-p-id", "VPS 6/12"); s.page.click("#vma-p-go"); s.page.wait_for_timeout(200)
        ck("thêm gói: mã sai → báo lỗi ngay, không gọi máy chủ", "Mã gói chỉ gồm" in s.dlg() and len(s.calls("vm_admin_plan")) == 1, s.dlg())
        s.page.fill("#vma-p-id", "vps6-12"); s.page.fill("#vma-p-name", "VPS 6-12"); s.page.fill("#vma-p-cores", "6"); s.page.fill("#vma-p-ram", "12")
        s.page.fill('#vma-p-rows .vms-row:nth-child(1) [data-pr="d"]', "30"); s.page.fill('#vma-p-rows .vms-row:nth-child(1) [data-pr="p"]', "600000"); s.page.click("#vma-p-go"); s.page.wait_for_timeout(500)
        pc = s.calls("vm_admin_plan")
        ck("thêm gói VPS 6-12 (6 vCPU · 12 GB · 20 GB · 600.000đ / 30 ngày)", pc[-1]["p_id"] == "vps6-12" and pc[-1]["p_patch"]["ram_mb"] == 12288 and pc[-1]["p_patch"]["cores"] == 6
           and pc[-1]["p_patch"]["prices"] == [{"days": 30, "price": 600000}] and s.js("() => document.querySelectorAll('#vma-plans tbody tr').length") == 9, pc[-1])
        # 26/11 · ⚡ tự tính giá theo đơn giá
        ck("⚡ tự tính giá: chưa nhập đơn giá → 2 nút khoá, có lời nhắc", s.vis("#vma-calc") and s.js("() => document.getElementById('vma-c-go').disabled && document.getElementById('vma-c-miss').disabled")
           and "Nhập ít nhất 1 đơn giá" in (s.txt("#vma-c-prev") or ""), s.txt("#vma-c-prev"))
        s.page.fill("#vma-c-cpu", "30000"); s.page.fill("#vma-c-ram", "20000"); s.page.fill("#vma-c-disk", "1000"); s.page.fill("#vma-c-days", "30, 7,1"); s.page.fill("#vma-c-up", "20"); s.page.wait_for_timeout(150)
        pv = s.txt("#vma-c-prev") or ""
        ck("xem trước: VPS 1-1 (1 vCPU · 1 GB · 20 GB) = 30n 70.000đ · 7n 20.000đ · 1n 3.000đ; VPS 8-16 = 30n 580.000đ · 7n 162.000đ (dưới 30 ngày +20%, làm tròn nghìn)",
           "VPS 1-1 1n 3.000đ · 7n 20.000đ · 30n 70.000đ" in pv and "VPS 8-16 1n 23.000đ · 7n 162.000đ · 30n 580.000đ" in pv and not s.js("() => document.getElementById('vma-c-go').disabled"), pv)
        n0 = len(s.calls("vm_admin_plan"))
        s.page.click("#vma-c-miss"); s.page.wait_for_timeout(600)
        pc = s.calls("vm_admin_plan")[n0:]
        ck("'Chỉ điền gói chưa có giá' → chỉ gọi vm_admin_plan cho gói 4-8 (4 vCPU · 8 GB): 1n 12.000đ · 7n 84.000đ · 30n 300.000đ; không đụng gói khác",
           len(pc) == 1 and pc[0] == {"p_id": "vps4-8", "p_patch": {"prices": [{"days": 1, "price": 12000}, {"days": 7, "price": 84000}, {"days": 30, "price": 300000}]}}
           and "30n: 300.000đ" in (s.txt("#vma-plans") or ""), pc)
        n0 = len(s.calls("vm_admin_plan"))
        s.page.click("#vma-c-go"); s.page.wait_for_timeout(250)
        d = s.dlg()
        ck("'Áp dụng cho tất cả gói' khi đã có gói có giá → hỏi trước 'Ghi đè giá đang có?' (hộp của trang), chưa gọi máy chủ", "Ghi đè giá đang có" in d and "9 gói đã có giá" in d and len(s.calls("vm_admin_plan")) == n0, d)
        s.page.click("#vma-c-ok"); s.page.wait_for_timeout(1200)
        pc = s.calls("vm_admin_plan")[n0:]
        ck("bấm Ghi đè → gọi vm_admin_plan cho cả 9 gói, chỉ gửi bảng giá (không đổi cấu hình); bảng hiện giá mới; nhớ đơn giá trên máy",
           len(pc) == 9 and all(list(x["p_patch"].keys()) == ["prices"] for x in pc) and pc[0] == {"p_id": "vps1-1", "p_patch": {"prices": [{"days": 1, "price": 3000}, {"days": 7, "price": 20000}, {"days": 30, "price": 70000}]}}
           and "30n: 70.000đ" in (s.txt("#vma-plans") or "") and "30n: 580.000đ" in (s.txt("#vma-plans") or "") and not s.vis("#vzdlg")
           and s.js("() => JSON.parse(localStorage.getItem('cb_vm_unit') || '{}').c") == 30000, (len(pc), pc[:1], s.txt("#vma-plans")))
        s.shot("vm-3b-tinh-gia.png")
        admin_open(s, "images")
        it = s.txt("#vma-images")
        ck("bản Windows: 5 bản, tên máy mẫu tpl-…, máy chủ đã có mẫu (pve1) / chưa máy nào", s.js("() => document.querySelectorAll('#vma-images tbody tr').length") == 5
           and "tpl-win2012r2" in it and "pve1" in it and "chưa máy nào" in it, it)
        s.page.click("#vma-i-new"); s.page.wait_for_timeout(200)
        s.page.fill("#vma-i-id", "win11"); s.page.fill("#vma-i-name", "Windows 11 LTSC"); s.page.fill("#vma-i-tpl", "tpl-win11"); s.page.fill("#vma-i-ram", "4"); s.page.fill("#vma-i-disk", "30")
        s.page.click("#vma-i-go"); s.page.wait_for_timeout(500)
        ck("thêm bản Windows 11 LTSC (tpl-win11, ≥ 4 GB RAM, ≥ 30 GB) → vm_admin_image", s.calls("vm_admin_image") == [{"p_id": "win11", "p_patch": {"name": "Windows 11 LTSC", "tpl": "tpl-win11",
           "min_ram": 4096, "min_disk": 30, "sort": 9, "enabled": True}}], s.calls("vm_admin_image"))
        admin_open(s, "set")
        ck("Cài đặt: có lệnh cài cbhost 1 dòng + nút Copy", "cai-cbhost.sh" in (s.txt("#vma-cmd") or "") and s.vis("#vma-cmd-copy"), s.txt("#vma-cmd"))
        s.page.fill("#vma-s-grace", "5"); s.page.check("#vma-s-sell"); s.page.click("#vma-s-save"); s.page.wait_for_timeout(500)
        st = s.calls("vm_admin_settings")
        ck("Lưu cài đặt → vm_admin_settings (bật bán, giữ 5 ngày, RAM chừa 4 GB = 4096 MB)", st and st[-1]["p_patch"]["sell"] is True and st[-1]["p_patch"]["grace_days"] == 5
           and st[-1]["p_patch"]["ram_reserve_mb"] == 4096 and st[-1]["p_patch"]["cpu_over"] == 3, st)
        ck("đầu khung đổi sang ĐANG BÁN", "ĐANG BÁN" in s.txt("#vma-top"), s.txt("#vma-top"))
        s.page.fill("#vma-g-user", "khachA"); s.page.select_option("#vma-g-plan", "vps2-2"); s.page.select_option("#vma-g-img", "win10ltsc"); s.page.fill("#vma-g-days", "3")
        s.page.click("#vma-g-go"); s.page.wait_for_timeout(500)
        ck("Tạo VPS cho tài khoản (không trừ tiền) → vm_admin_give", s.calls("vm_admin_give") == [{"p_user": "khachA", "p_plan": "vps2-2", "p_image": "win10ltsc", "p_days": 3}], s.calls("vm_admin_give"))
        s.shot("vm-4-set.png")
        ck("không lỗi trang / không hộp thoại trình duyệt (quản trị)", not s.errors, s.errors)
        s.close()

        print("3a. 🧰 Bảng điều khiển máy mẫu (SQL v57)")
        s = Site(br, html, True, vm_data(tpl=tpl_state(err=True)), path="/admin", vp=(1600, 1000))
        admin_open(s, "images")
        box = s.txt("#vma-images .vma-sec") or ""
        ck("thẻ Bản Windows có bảng máy mẫu: máy mẫu đang dựng (Server 2022 sẵn sàng, Server 2016 lỗi) + lịch sử (10 LTSC đã lưu)",
           "Bảng điều khiển máy mẫu" in box and "tpl-win2022" in box and "Sẵn sàng" in box and "volume does not exist" in box and "✅ tpl-win10ltsc" in box, box)
        ck("máy mẫu sẵn sàng: ▶ Điều khiển mở play.html?pc=<máy mẫu> (tab mới) + nút 💾 Lưu bật; máy lỗi: Lưu tắt, có ↻ Thử lại",
           s.js("() => { const a = document.querySelector('[data-vmtj=\"31\"] a.btn'); return a && a.getAttribute('href'); }") == "/play.html?pc=" + TPC
           and s.js("() => !document.querySelector('[data-vmtj=\"31\"] [data-vmt=\"save\"]').disabled")
           and s.js("() => document.querySelector('[data-vmtj=\"30\"] [data-vmt=\"save\"]').disabled")
           and s.js("() => !!document.querySelector('[data-vmtj=\"30\"] [data-vmt=\"retry\"]')"))
        ck("số trên thẻ VPS ảo hoá cộng thêm máy mẫu lỗi (2 + 1 = 3)", s.js("() => document.getElementById('vm-badge').textContent") == "3")
        s.js("() => document.querySelector('#vma-images .vma-sec').scrollIntoView()"); s.page.wait_for_timeout(200)
        s.shot("vm-10-tpl-panel.png")
        s.page.click('[data-vmtj="30"] [data-vmt="retry"]'); s.page.wait_for_timeout(500)
        ck("↻ Thử lại → vm_tpl_act retry", s.calls("vm_tpl_act")[-1:] == [{"p_id": 30, "p_act": "retry"}], s.calls("vm_tpl_act"))
        s.page.click('[data-vmtj="31"] [data-vmt="save"]'); s.page.wait_for_timeout(300)
        d1 = s.dlg()
        ck("💾 Lưu → hộp xác nhận nói rõ: xoá mã máy, tắt, gỡ ISO, máy mẫu cũ thành tpl-win2022-cu, VPS đang chạy giữ nguyên",
           "tpl-win2022-cu" in d1 and "xoá mã máy" in d1 and "VPS đang chạy giữ nguyên" in d1, d1)
        s.shot("vm-11-tpl-save.png")
        s.page.click("#vma-tj-go"); s.page.wait_for_timeout(600)
        ck("xác nhận → vm_tpl_act save, đóng hộp, thẻ chuyển 'Đang lưu'", s.calls("vm_tpl_act")[-1] == {"p_id": 31, "p_act": "save"} and not s.vis("#vzdlg")
           and "Đang lưu" in (s.txt('[data-vmtj="31"]') or ""), s.calls("vm_tpl_act"))
        s.page.click("#vma-t-new"); s.page.wait_for_timeout(300)
        d2 = s.dlg()
        ck("➕ Dựng / sửa máy mẫu: chọn máy chủ + bản Windows; dựng từ ISO tự chọn đúng file ISO máy mẫu của bản đó (2012 R2)",
           "Dựng mới từ ISO" in d2 and s.js("() => document.getElementById('vma-t-iso').value") == ISO
           and s.js("() => document.getElementById('vma-t-img').value") == "win2012r2", d2)
        s.page.select_option("#vma-t-img", "win2019"); s.page.wait_for_timeout(200)
        ck("bản máy chủ chưa có mẫu (2019) → nút 'Sửa máy mẫu đang có' bị khoá", s.js("() => document.querySelector('[data-vmtsrc=\"tpl\"]').disabled"))
        s.page.select_option("#vma-t-img", "win2012r2"); s.page.wait_for_timeout(200)
        s.shot("vm-12-tpl-new.png")
        s.page.click("#vma-t-go"); s.page.wait_for_timeout(700)
        ck("Bắt đầu → vm_tpl_new {máy chủ, win2012r2, iso, đúng file ISO}; việc mới hiện 'Đang tạo máy ảo'",
           s.calls("vm_tpl_new") == [{"p_host": H1, "p_image": "win2012r2", "p_src": "iso", "p_iso": ISO}] and "Đang tạo máy ảo" in (s.txt("#vma-images .vma-sec") or ""), s.calls("vm_tpl_new"))
        s.page.click("#vma-t-new"); s.page.wait_for_timeout(300)
        s.page.click('[data-vmtsrc="tpl"]'); s.page.wait_for_timeout(200)
        s.js("() => { window.__VM.tplErr = 'BUSY'; }")
        s.page.click("#vma-t-go"); s.page.wait_for_timeout(500)
        ck("sửa máy mẫu đang có → vm_tpl_new src tpl (không ISO); máy chủ báo bận → báo lỗi trong hộp, không đóng",
           s.calls("vm_tpl_new")[-1] == {"p_host": H1, "p_image": "win2012r2", "p_src": "tpl", "p_iso": None} and s.vis("#vzdlg") and (s.txt("#vzd-err") or ""), s.calls("vm_tpl_new"))
        s.js("() => { window.__VM.tplErr = null; }"); s.page.click("#vzdlg [data-vmx]"); s.page.wait_for_timeout(200)
        s.page.click('[data-vmtj="31"] [data-vmt="cancel"]'); s.page.wait_for_timeout(300)
        ck("✖ Huỷ → hộp xác nhận xoá máy ảo tạm (máy mẫu đang dùng giữ nguyên)", "Máy mẫu đang dùng giữ nguyên" in s.dlg(), s.dlg())
        s.page.click("#vma-tj-go"); s.page.wait_for_timeout(500)
        ck("xác nhận huỷ → vm_tpl_act cancel", s.calls("vm_tpl_act")[-1] == {"p_id": 31, "p_act": "cancel"}, s.calls("vm_tpl_act"))
        ck("nút 📋 chép lệnh ghép ISO máy mẫu có (lệnh tải tao-iso-may-mau.ps1)", s.vis("#vma-t-cmd")
           and "tao-iso-may-mau.ps1" in s.js("() => { let t = ''; const o = navigator.clipboard; return 'x'; }") + open(HTML, encoding="utf-8").read()[:0] + s.page.content())
        ck("không lỗi trang / không hộp thoại trình duyệt (máy mẫu)", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, vm_data(tpl=None), path="/admin", vp=(1600, 1000))
        admin_open(s, "images")
        ck("chưa chạy SQL v57 → bảng máy mẫu báo 'Cần chạy SQL v57', phần còn lại vẫn chạy, không lỗi", "Cần chạy SQL v57" in (s.txt("#vma-images") or "")
           and "tpl-win2012r2" in (s.txt("#vma-images") or "") and not s.errors, (s.txt("#vma-images"), s.errors))
        s.close()

        print("3b. Mới chạy SQL: 8 cấu hình CHƯA có giá")
        d0 = vm_data(); [p.__setitem__("prices", []) for p in d0["adm"]["plans"]]; [p.__setitem__("prices", []) for p in d0["shop"]["plans"]]
        s = Site(br, html, True, d0, path="/admin", vp=(1600, 1000))
        admin_open(s)
        ck("chưa nhập giá gói nào → đầu khung báo đỏ 'chưa nhập giá gói nào — khách chưa thấy gì'", "chưa nhập giá gói nào" in s.txt("#vma-top"), s.txt("#vma-top"))
        s.page.goto(ORIGIN + "/", wait_until="load"); s.page.wait_for_timeout(2000)
        ck("… và dòng VPS NVMe ngoài trang ẩn hẳn (không có gói nào có giá, kể cả với admin)", not s.js("() => !!document.querySelector('#grid [data-vmbuy], #grid .m3-row.vm, #vm-shop')"))
        s.close()

        print("4. Quản trị khi CHƯA chạy SQL v56")
        s = Site(br, html, True, vm_data(miss=True), path="/admin", vp=(1600, 1000))
        admin_open(s)
        ck("báo cần chạy SQL v56, không vẽ phần dưới, không báo lỗi đỏ", s.vis("#vma-miss") and not s.vis("#pane-vm .subtabs") and not s.errors, s.errors)
        s.close()

        print("5. Khách: VPS NVMe là 1 DÒNG sản phẩm (như Cloud Phone) + hộp Thuê ngay sổ bảng cấu hình")
        s = Site(br, html, False, vm_data(), products=prods)
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }"); s.page.wait_for_timeout(300)
        row = s.js("""() => { const r = document.querySelector('#grid article.m3-row.vm'); if (!r) return null; const t = e => e ? e.innerText.replace(/\\s+/g, ' ').trim() : '';
          const rows = [...document.querySelectorAll('#grid > article.m3-row')], b = r.querySelector('.m3-box button');
          return {i: rows.indexOf(r), n: rows.length, first: t(rows[0].querySelector('h3')), h3: t(r.querySelector('h3')), cat: t(r.querySelector('.cat')), fl: t(r.querySelector('.feats.spec .fl')),
                  feats: [...r.querySelectorAll('.feats.spec span')].map(t), box: t(r.querySelector('.m3-box')), btn: t(b), dis: b.disabled, txt: t(r), old: !!document.getElementById('vm-shop')}; }""")
        ck("VPS NVMe là 1 DÒNG trong danh sách Sản phẩm (không còn khối riêng #vm-shop): tên 'VPS NVMe BLUE', nút 'Thuê ngay'",
           row and not row["old"] and row["h3"] == "VPS NVMe BLUE" and row["cat"] == "VPS NVMe" and row["btn"] == "Thuê ngay" and row["dis"] is False, row)
        ck("dòng VPS NVMe: chữ CẤU HÌNH nổi bật gom mọi gói có giá — 1–8 vCPU · 1–16 GB RAM · SSD NVMe 20 GB · Windows đã có máy mẫu; giá mồi = mức rẻ nhất tính theo NGÀY 'từ 3.333đ /ngày' (100.000đ / 30 ngày); 'Còn chỗ'",
           row and row["fl"] == "Cấu hình" and row["feats"][:3] == ["1–8 vCPU", "1–16 GB RAM", "SSD NVMe 20 GB"] and len(row["feats"]) == 4 and "Server 2012 R2" in row["feats"][3]
           and "10 LTSC" in row["feats"][3] and "2022" not in row["feats"][3] and "3.333đ" in row["box"] and "/ngày" in row["box"] and "tháng" not in row["box"] and "Còn chỗ" in row["box"], row)
        ck("thứ tự: dòng VPS NVMe nằm ngay sau Cloud Phone, trước các sản phẩm khác", row and row["i"] == 1 and "Cloud Phone" in row["first"], row)
        ck("sản phẩm ẩn chuyên mục 'vm' KHÔNG hiện trong lưới sản phẩm", "VPS ảo hoá · VPS 1-1" not in (s.txt("#grid") or "") and "Clone Roblox" in (s.txt("#grid") or ""), s.txt("#grid"))
        ck("26/11 · khách thấy tên 'VPS NVMe' (không còn chữ 'ảo hoá' / hình 🧩; không có dòng 'chỉ admin thấy')", row and "ảo hoá" not in row["txt"] and "🧩" not in row["txt"] and "admin" not in row["txt"], row)
        cats = s.js("() => [...document.querySelectorAll('#cats button')].map(b => b.innerText.replace(/\\s+/g, ' ').trim())")
        ck("thanh chuyên mục có nút 'VPS NVMe'; bấm → chỉ còn dòng VPS NVMe", any(c.startswith("VPS NVMe") for c in cats), cats)
        s.js("() => { const b = [...document.querySelectorAll('#cats button')].find(b => b.innerText.trim().startsWith('VPS NVMe')); if (b) b.click(); }"); s.page.wait_for_timeout(250)
        only = s.js("() => [...document.querySelectorAll('#grid > article.m3-row, #grid .m3-li')].map(r => (r.querySelector('h3, .nm b') || {}).innerText)")
        ck("… lọc theo 'VPS NVMe' → lưới chỉ còn VPS NVMe BLUE", only == ["VPS NVMe BLUE"], only)
        s.js("() => { const b = document.querySelector('#cats button'); if (b) b.click(); }"); s.page.wait_for_timeout(250)
        s.page.fill("#q", "nvme"); s.page.wait_for_timeout(300)
        found = s.js("() => [...document.querySelectorAll('#grid > article.m3-row, #grid .m3-li')].map(r => (r.querySelector('h3, .nm b') || {}).innerText)")
        s.page.fill("#q", ""); s.page.wait_for_timeout(300)
        ck("ô tìm: gõ 'nvme' → ra VPS NVMe BLUE", found == ["VPS NVMe BLUE"], found)
        art = s.js("""() => { const c = document.querySelector('#grid .m3-row.vm .thumb canvas[data-c="nvme"]'); if (!c) return null; const r = c.getBoundingClientRect(), x = c.getContext('2d');
          const at = (px, py) => [...x.getImageData(Math.round(px * c.width), Math.round(py * c.height), 1, 1).data];
          return {kind: c._kind, w: Math.round(r.width), h: Math.round(r.height), mid: at(.56, .5), corner: at(.5, .12), hot: (document.querySelector('#grid .m3-row.vm .thumb .hot') || {}).innerText || ''}; }""")
        ck("ảnh riêng của VPS NVMe (thanh SSD M.2) vẽ trong ô ảnh của dòng: giữa ảnh là thân xanh của thanh SSD, mép trên là nền bảng sáng; có nhãn MỚI",
           art and art["kind"] == "nvme" and art["w"] >= 200 and art["mid"][2] > 150 and art["mid"][2] > art["mid"][0] + 60 and min(art["corner"][:3]) > 170 and art["hot"] == "MỚI", art)
        s.js("() => document.querySelector('#grid .m3-row.vm').scrollIntoView({block: 'center'})"); s.page.wait_for_timeout(250)
        s.shot("vm-5-shop.png")
        s.page.click('#grid .m3-row.vm .m3-box button[data-vmbuy]'); s.page.wait_for_timeout(300)
        d = s.dlg()
        tiles = s.js("() => [...document.querySelectorAll('#vms-plan [data-vmplan]')].map(b => [b.dataset.vmplan, b.classList.contains('on'), b.disabled, b.innerText.replace(/\\s+/g, ' ').trim()])")
        ck("bấm Thuê ngay → hộp '⚡ Thuê VPS NVMe' sổ bảng cấu hình: 7 gói có giá (4-8 chưa có giá → không hiện), chọn sẵn gói rẻ nhất còn chỗ (VPS 1-1), gói hết chỗ (8-16) bị khoá + ghi 'tạm hết chỗ'",
           "Thuê VPS NVMe" in d and "Chọn cấu hình" in d and "Chọn hệ điều hành" in d and [t[0] for t in tiles] == ["vps1-1", "vps1-2", "vps2-2", "vps2-4", "vps3-3", "vps4-4", "vps8-16"]
           and [t[0] for t in tiles if t[1]] == ["vps1-1"] and [t[0] for t in tiles if t[2]] == ["vps8-16"] and "tạm hết chỗ" in tiles[-1][3]
           and "⚙️ 1 vCPU" in tiles[0][3] and "🧠 1 GB RAM" in tiles[0][3] and "💾 SSD NVMe 20 GB" in tiles[0][3] and "100.000đ / tháng" in tiles[0][3] and "100.000đ" in (s.txt("#vms-sum") or ""), (d, tiles))
        s.page.click('#vms-plan [data-vmplan="vps2-2"]'); s.page.wait_for_timeout(200)
        ck("chọn VPS 2-2: ô gói đổi dấu ✓, tổng tiền 30 ngày 170.000đ; Windows có máy mẫu chọn sẵn; bản chưa có máy mẫu bị khoá",
           s.js("() => [...document.querySelectorAll('#vms-plan .on')].map(b => b.dataset.vmplan)") == ["vps2-2"] and "170.000đ" in (s.txt("#vms-sum") or "")
           and s.js("() => document.querySelector('#vms-os [data-vmos=\"win2012r2\"]').classList.contains('on')")
           and s.js("() => document.querySelector('#vms-os [data-vmos=\"win2022\"]').disabled"), (s.dlg(), s.txt("#vms-sum")))
        s.page.click('#vms-os [data-vmos="win10ltsc"]'); s.page.wait_for_timeout(100)
        s.shot("vm-6-buy.png")
        s.page.click("#vms-pay"); s.page.wait_for_timeout(700)
        ck("Thanh toán → vm_buy {vps2-2, win10ltsc, 30 ngày}, đóng hộp, báo 'Đã thuê VPS-15', tải lại VPS của tôi", s.calls("vm_buy") == [{"p_plan": "vps2-2", "p_image": "win10ltsc", "p_days": 30}]
           and not s.vis("#vzdlg") and len(s.calls("vm_my")) >= 2 and "Đã thuê VPS-15" in (s.txt("#toast") or ""), (s.calls("vm_buy"), s.txt("#toast")))
        ck("mua xong: dòng VPS NVMe vẫn còn trong danh sách (vẽ lại lưới không làm mất)", s.js("() => document.querySelectorAll('#grid article.m3-row.vm').length") == 1)
        s.js("() => { window.__VM.buyErr = 'NO_CAPACITY'; }")
        s.page.click('#grid .m3-row.vm h3'); s.page.wait_for_timeout(250)
        need = s.js("() => [...document.querySelectorAll('#vms-os button')].map(b => [b.dataset.vmos || '', b.dataset.vmneed || '', b.disabled, b.innerText.replace(/\\s+/g, ' ').trim()])")
        ck("bấm vào DÒNG (không cần đúng nút) cũng mở hộp; gói 1 GB RAM: Server 2012 R2 chọn được; bản máy chủ có sẵn nhưng cần 2 GB (10 LTSC) hiện MỜ kèm 'cần gói từ 2 GB RAM'; bản chưa có máy mẫu không hiện",
           "Thuê VPS NVMe" in s.dlg() and len(need) == 2 and need[0][0] == "win2012r2" and need[0][2] is False and need[1][1] == "win10ltsc" and need[1][2] is True and "cần gói từ 2 GB RAM" in need[1][3], need)
        s.page.click('#vms-plan [data-vmplan="vps2-4"]'); s.page.wait_for_timeout(120); s.page.click('#vms-os [data-vmos="win10ltsc"]'); s.page.wait_for_timeout(120)
        s.page.click('#vms-plan [data-vmplan="vps3-3"]'); s.page.wait_for_timeout(120)
        keep = s.js("() => [[...document.querySelectorAll('#vms-os .on')].map(b => b.dataset.vmos), document.getElementById('vms-sum').innerText]")
        s.page.click('#vms-plan [data-vmplan="vps1-1"]'); s.page.wait_for_timeout(120)
        back = s.js("() => [[...document.querySelectorAll('#vms-os .on')].map(b => b.dataset.vmos), document.getElementById('vms-sum').innerText]")
        ck("đổi gói: hệ điều hành đang chọn còn hợp thì GIỮ (2-4 → 3-3 vẫn 10 LTSC, tổng 270.000đ); không hợp nữa (về gói 1 GB) thì tự về bản dùng được (2012 R2, tổng 100.000đ)",
           keep[0] == ["win10ltsc"] and "270.000đ" in keep[1] and back[0] == ["win2012r2"] and "100.000đ" in back[1], (keep, back))
        hit = s.js("() => { const b = document.querySelector('#vms-plan [data-vmplan=\"vps8-16\"]'); b.click(); return [...document.querySelectorAll('#vms-plan .on')].map(x => x.dataset.vmplan); }")
        ck("gói hết chỗ trong bảng cấu hình: bấm không chọn được", hit == ["vps1-1"], hit)
        s.page.click("#vms-pay"); s.page.wait_for_timeout(500)
        ck("hết chỗ lúc mua → báo rõ trong hộp (không trừ tiền)", "hết chỗ" in s.dlg(), s.dlg())
        s.page.click('#vzdlg [data-vmx]'); s.page.wait_for_timeout(100)
        s.js("() => { window.__VM.buyErr = null; }")

        print("6. Khách: VPS ảo hoá của bạn")
        ck("khung 'VPS NVMe của bạn' nằm ngay dưới 'VPS GPU của bạn', 3 VPS", s.vis("#vm-mine") and s.js("() => document.getElementById('vm-mine').previousElementSibling.id") == "pcs-mine"
           and s.js("() => document.querySelectorAll('#vm-mine-list .vms-card').length") == 3 and "VPS NVMe của bạn" in (s.txt("#vm-mine-h") or ""), s.txt("#vm-mine-h"))
        gpu = s.js("() => [...document.querySelectorAll('#pcs-mine-list .pcs-card')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ck("VPS GPU của bạn KHÔNG lặp máy ảo VPS-12 (chỉ còn máy GPU thật)", len(gpu) == 1 and "May-GPU-01" in gpu[0], gpu)
        cards = s.js("() => [...document.querySelectorAll('#vm-mine-list .vms-card')].map(c => c.innerText.replace(/\\s+/g, ' '))")
        ck("VPS-12 'Treo game': Đang chạy · VPS 2-4 · 2 vCPU · 4 GB · 10 LTSC, nút ▶ Điều khiển → play.html?pc=<máy ảo>", "Treo game" in cards[0] and "Đang chạy" in cards[0]
           and "VPS 2-4" in cards[0] and "4 GB RAM" in cards[0] and s.js("p => !!document.querySelector('#vm-mine-list a[href=\"/play.html?pc=' + p + '\"]')", VPC1), cards[0])
        ck("VPS-13 đang tạo: chưa cho điều khiển / gia hạn; VPS-14 hết hạn: báo hạn xoá, tên lạ không chạy mã", "Đang tạo" in cards[1]
           and s.js("() => document.querySelector('[data-vm=\"13\"] .btn.sm').disabled && document.querySelector('[data-vm=\"13\"] [data-vmrenew]').disabled")
           and "Hết hạn" in cards[2] and "Gia hạn trước" in cards[2] and not s.js("() => !!window.__xss"), cards)
        nav = s.js("""() => { const g = document.getElementById('nav-vps'), v = document.getElementById('nav-vm'), t = e => e ? e.innerText.replace(/\\s+/g, ' ').trim() : null;
          return {gpu: t(g), vm: t(v), vmHidden: v ? v.hidden : null, has: v ? v.classList.contains('has') : null, after: v && g ? g.nextElementSibling === v : null}; }""")
        ck("26/11 · menu bên tách 2 mục: 'VPS GPU của tôi' và ngay dưới là 'VPS NVMe của tôi' kèm số VPS (3)", nav["gpu"].startswith("VPS GPU của tôi") and nav["vm"] == "VPS NVMe của tôi 3"
           and nav["vmHidden"] is False and nav["has"] and nav["after"], nav)
        s.js("() => window.scrollTo(0, document.body.scrollHeight)"); s.page.wait_for_timeout(150)
        s.page.click("#nav-vm"); s.page.wait_for_timeout(900)
        top = s.js("() => Math.round(document.getElementById('vm-mine').getBoundingClientRect().top)")
        ck("bấm 'VPS NVMe của tôi' → cuộn tới khung 'VPS NVMe của bạn'", -40 <= top <= 360, top)
        s.shot("vm-7-mine.png")
        s.page.click("#vm-mine-new"); s.page.wait_for_timeout(300)
        ck("nút ➕ ở khung 'VPS NVMe của bạn' → mở thẳng hộp Thuê VPS NVMe (không phải cuộn đi tìm)", "Thuê VPS NVMe" in s.dlg() and s.js("() => document.querySelectorAll('#vms-plan [data-vmplan]').length") == 7, s.dlg())
        s.page.click('#vzdlg [data-vmx]'); s.page.wait_for_timeout(150)
        s.page.click('[data-vm="12"] [data-vmpow="stop"]'); s.page.wait_for_timeout(400)
        ck("bấm Tắt → vm_my_power {12, stop}", s.calls("vm_my_power") == [{"p_id": 12, "p_act": "stop"}], s.calls("vm_my_power"))
        s.page.click('[data-vm="12"] [data-vmre]'); s.page.wait_for_timeout(200); s.page.click('#vms-reos [data-vmreos="win2012r2"]'); s.page.click("#vms-re-go"); s.page.wait_for_timeout(200)
        ck("cài lại: chưa tick 'tôi hiểu' → không gọi", not s.calls("vm_my_reinstall") and "Tick" in s.dlg(), s.dlg())
        s.page.check("#vms-re-ok"); s.page.click("#vms-re-go"); s.page.wait_for_timeout(400)
        ck("tick xong → vm_my_reinstall {12, win2012r2}", s.calls("vm_my_reinstall") == [{"p_id": 12, "p_image": "win2012r2"}], s.calls("vm_my_reinstall"))
        s.page.click('[data-vm="12"] [data-vmrenew]'); s.page.wait_for_timeout(200)
        ck("gia hạn: chọn sẵn 30 ngày 240.000đ, có 7 ngày 70.000đ", "240.000đ" in s.dlg() and "70.000đ" in s.dlg() and s.js("() => document.querySelector('[data-vmrndays=\"30\"]').classList.contains('on')"), s.dlg())
        s.page.click('[data-vmrndays="7"]'); s.page.click("#vms-rn-go"); s.page.wait_for_timeout(500)
        ck("gia hạn 7 ngày → vm_my_renew {12, 7}", s.calls("vm_my_renew") == [{"p_id": 12, "p_days": 7}], s.calls("vm_my_renew"))
        ck("VPS: khách KHÔNG có nút đổi tên (đổi tên chỉ dành cho ĐT đám mây)", not s.js("() => !!document.querySelector('#vm-mine-list [data-vmlabel]')"))
        s.page.click('[data-vm="14"] [data-vmdel]'); s.page.wait_for_timeout(200); s.page.check("#vms-del-ok"); s.page.click("#vms-del-go"); s.page.wait_for_timeout(400)
        ck("xoá VPS (tick xác nhận) → vm_my_cancel {14}", s.calls("vm_my_cancel") == [{"p_id": 14}], s.calls("vm_my_cancel"))
        print("6b. ĐT đám mây: khách đổi tên máy ngay ở khung trang chủ")
        ren = s.js("() => [...document.querySelectorAll('#m3-mine-list .m3m-card')].map(c => [c.querySelector('.m3m-nm').innerText.replace(/\\s+/g, ' '), !!c.querySelector('.m3m-ren[data-cprename]')])")
        ck("máy của mình có nút ✏️ cạnh tên; máy được chia sẻ thì không", ["Máy farm 1 ✏️", True] in ren and any(r[0].startswith("Máy được chia sẻ") and not r[1] for r in ren), ren)
        n0 = s.js("() => window.__FAKE.calls.filter(c => c.kind === 'from' && c.table === 'cloud_phones').length")
        s.answer = "Máy treo game"; s.page.click('#m3-mine-list [data-cprename="cp-1"]'); s.page.wait_for_timeout(600); s.answer = None
        ck("bấm ✏️ → nhập tên → cloudphone_rename {cp-1, 'Máy treo game'}, báo 'Đã đổi tên máy', tải lại khung (không mở hộp ĐT đám mây của tôi)",
           s.calls("cloudphone_rename") == [{"p_id": "cp-1", "p_name": "Máy treo game"}] and "Đã đổi tên máy" in (s.txt("#toast") or "")
           and s.js("() => document.getElementById('cpdlg').hidden") and s.js("() => window.__FAKE.calls.filter(c => c.kind === 'from' && c.table === 'cloud_phones').length") > n0,
           (s.calls("cloudphone_rename"), s.txt("#toast")))
        ck("không lỗi trang / không hộp thoại trình duyệt ngoài ý muốn (khách)", not s.errors, s.errors)
        s.close()

        print("6c. SQL v59: tự chọn cấu hình · ổ thêm · nâng cấp · bảo trì")
        s = Site(br, html, False, v59(vm_data()), products=prods)
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }"); s.page.wait_for_timeout(300)
        row = s.txt("#grid article.m3-row.vm") or ""
        ck("dòng VPS NVMe ghi thêm 'Tự chọn cấu hình' trong phần Cấu hình", "Tự chọn cấu hình" in row, row)
        s.page.click('#grid .m3-row.vm .m3-box button[data-vmbuy]'); s.page.wait_for_timeout(300)
        d = s.dlg(); cust = s.txt('#vms-plan [data-vmplan="custom"]') or ""
        ck("hộp Thuê: có dòng '20 GB ổ đầu miễn phí'; cuối bảng gói có ô '🛠 Tự chọn cấu hình' giá 'từ 20.000đ / tháng' (1 vCPU 8.000 + 1 GB 12.000)",
           "20 GB ổ đầu miễn phí" in d and "Tự chọn cấu hình" in cust and "từ 20.000đ / tháng" in cust, (d, cust))
        s.page.click('#vms-plan [data-vmplan="vps2-2"]'); s.page.wait_for_timeout(200)
        ck("gói có sẵn + shop bán ổ thêm → hiện ô '💾 Ổ SSD NVMe' (gói có sẵn 20 GB · thêm 1.000đ / GB / tháng), mặc định 20 GB, tổng 170.000đ",
           s.vis("#vms-cfg") and "gói có sẵn 20 GB" in (s.txt("#vms-cfg") or "") and s.js("() => document.getElementById('vms-c-pdisk').value") == "20" and "170.000đ" in (s.txt("#vms-sum") or ""), (s.txt("#vms-cfg"), s.txt("#vms-sum")))
        s.page.click('[data-vmstep="pdisk"][data-d="10"]'); s.page.click('[data-vmstep="pdisk"][data-d="10"]'); s.page.wait_for_timeout(150)
        sm = s.txt("#vms-sum") or ""
        ck("bấm + 2 lần → ổ 40 GB: tổng 170.000 + 20 × 1.000 = 190.000đ, ghi 'VPS 2-2 + 20 GB ổ (SSD NVMe 40 GB)'", "190.000đ" in sm and "VPS 2-2 + 20 GB ổ" in sm, sm)
        ck("ổ không xuống dưới ổ của gói: nút − bị khoá khi về 20 GB", s.js("() => { const b = document.querySelector('[data-vmstep=\"pdisk\"][data-d=\"-10\"]'); b.click(); b.click(); b.click(); return [document.getElementById('vms-c-pdisk').value, b.disabled]; }") == ["20", True])
        s.page.click('[data-vmstep="pdisk"][data-d="10"]'); s.page.click('[data-vmstep="pdisk"][data-d="10"]'); s.page.wait_for_timeout(100)
        s.page.click('#vms-os [data-vmos="win10ltsc"]'); s.page.click("#vms-pay"); s.page.wait_for_timeout(600)
        ck("Thanh toán gói + ổ thêm → vm_buy {vps2-2, win10ltsc, 30 ngày, p_disk_gb 40}", s.calls("vm_buy") == [{"p_plan": "vps2-2", "p_image": "win10ltsc", "p_days": 30, "p_disk_gb": 40}], s.calls("vm_buy"))
        s.page.click("#vm-mine-new"); s.page.wait_for_timeout(300)
        s.page.click('#vms-plan [data-vmplan="custom"]'); s.page.wait_for_timeout(200)
        cfg = s.txt("#vms-cfg") or ""
        ck("bấm ô Tự chọn → 3 ô vCPU · RAM · SSD NVMe kèm đơn giá (8.000đ / vCPU / tháng · 12.000đ / GB · 20 GB đầu miễn phí · thêm 1.000đ / GB); mặc định 2 vCPU · 4 GB · 20 GB = 64.000đ / 30 ngày",
           all(x in cfg for x in ("vCPU", "RAM (GB)", "SSD NVMe (GB)", "8.000đ / vCPU / tháng", "12.000đ / GB / tháng", "20 GB đầu miễn phí", "1.000đ / GB / tháng"))
           and s.js("() => ['cores','ram','disk'].map(k => document.getElementById('vms-c-' + k).value)") == ["2", "4", "20"] and "64.000đ" in (s.txt("#vms-sum") or ""), (cfg, s.txt("#vms-sum")))
        days = s.js("() => [...document.querySelectorAll('#vms-days [data-vmdays]')].map(b => b.innerText.replace(/\\s+/g, ' ').trim())")
        ck("tự chọn: kỳ hạn theo cài đặt máy chủ 1 · 3 · 7 · 30 ngày, giá theo đơn giá (1 ngày 2.000đ · 7 ngày 15.000đ · 30 ngày 64.000đ)",
           len(days) == 4 and "2.000đ" in days[0] and "15.000đ" in days[2] and "64.000đ" in days[3], days)
        s.page.fill("#vms-c-cores", "3"); s.page.wait_for_timeout(120); s.page.fill("#vms-c-disk", "60"); s.page.wait_for_timeout(120)
        sm = s.txt("#vms-sum") or ""
        ck("gõ 3 vCPU + ổ 60 GB → 3×8.000 + 4×12.000 + 40×1.000 = 112.000đ; ô Tự chọn hiện đúng cấu hình đang chọn", "112.000đ" in sm and "3 vCPU · 4 GB RAM · SSD NVMe 60 GB" in sm
           and "3 vCPU" in (s.txt('#vms-plan [data-vmplan="custom"]') or "") and "112.000đ / tháng" in (s.txt('#vms-plan [data-vmplan="custom"]') or ""), (sm, s.txt('#vms-plan [data-vmplan="custom"]')))
        s.page.fill("#vms-c-cores", "99"); s.page.wait_for_timeout(100); s.page.dispatch_event("#vms-c-cores", "change"); s.page.wait_for_timeout(100)
        ck("gõ quá giới hạn (99 vCPU) → tự kẹp về 16 (tối đa của shop)", s.js("() => document.getElementById('vms-c-cores').value") == "16" and "16 vCPU" in (s.txt("#vms-sum") or ""), s.txt("#vms-sum"))
        s.page.fill("#vms-c-cores", "3"); s.page.dispatch_event("#vms-c-cores", "change"); s.page.wait_for_timeout(100)
        s.page.click('#vms-os [data-vmos="win10ltsc"]'); s.page.fill("#vms-c-ram", "1"); s.page.wait_for_timeout(150)
        osx = s.js("() => [[...document.querySelectorAll('#vms-os .on')].map(b => b.dataset.vmos), [...document.querySelectorAll('#vms-os [data-vmneed]')].map(b => b.dataset.vmneed)]")
        ck("RAM 1 GB → bản cần 2 GB (10 LTSC) tự mờ, tự về bản dùng được (2012 R2)", osx == [["win2012r2"], ["win10ltsc"]], osx)
        s.page.fill("#vms-c-ram", "4"); s.page.wait_for_timeout(100); s.page.click('#vms-os [data-vmos="win10ltsc"]'); s.page.wait_for_timeout(100)
        s.shot("vm-6c-custom.png")
        s.page.click("#vms-pay"); s.page.wait_for_timeout(600)
        ck("Thanh toán tự chọn → vm_buy_custom {3 vCPU, 4 GB, 60 GB, win10ltsc, 30 ngày}, báo 'Đã thuê VPS-17'",
           s.calls("vm_buy_custom") == [{"p_cores": 3, "p_ram_gb": 4, "p_disk_gb": 60, "p_image": "win10ltsc", "p_days": 30}] and "Đã thuê VPS-17" in (s.txt("#toast") or ""), (s.calls("vm_buy_custom"), s.txt("#toast")))
        ups = s.js("() => [...document.querySelectorAll('#vm-mine-list [data-vmup]')].map(b => [b.dataset.vmup, b.disabled])")
        ck("VPS của bạn: nút ⬆ Nâng cấp — VPS-12 (đang chạy) bấm được; VPS-13 (đang tạo) / VPS-14 (hết hạn) bị khoá", ups == [["12", False], ["13", True], ["14", True]], ups)
        s.page.click('[data-vmup="12"]'); s.page.wait_for_timeout(300)
        d = s.dlg()
        ck("hộp Nâng cấp: ghi cấu hình hiện tại (2 vCPU · 4 GB RAM · SSD NVMe 20 GB); chưa tăng gì thì nút Nâng cấp khoá, không hỏi giá",
           "Hiện tại: 2 vCPU · 4 GB RAM · SSD NVMe 20 GB" in d and s.js("() => document.getElementById('vms-up-go').disabled") and not s.calls("vm_my_upgrade")
           and s.js("() => document.querySelector('[data-vmstep=\"ucores\"][data-d=\"-1\"]').disabled"), d)
        s.page.click('[data-vmstep="ucores"][data-d="1"]'); s.page.wait_for_timeout(700)
        ck("bấm + vCPU → hỏi giá máy chủ (vm_my_upgrade p_dry) {12, 3 vCPU, 4 GB, 20 GB}; hiện số phải trả + 'tự khởi động lại'; nút Nâng cấp mở",
           s.calls("vm_my_upgrade")[-1:] == [{"p_id": 12, "p_cores": 3, "p_ram_gb": 4, "p_disk_gb": 20, "p_dry": True}] and "Phải trả" in (s.txt("#vms-up-sum") or "")
           and "khởi động lại" in (s.txt("#vms-up-sum") or "") and not s.js("() => document.getElementById('vms-up-go').disabled"), (s.calls("vm_my_upgrade"), s.txt("#vms-up-sum")))
        s.page.click("#vms-up-go"); s.page.wait_for_timeout(600)
        ck("bấm Nâng cấp → vm_my_upgrade {12, 3, 4, 20} (không p_dry), đóng hộp, báo 'Đã nâng cấp'", s.calls("vm_my_upgrade")[-1] == {"p_id": 12, "p_cores": 3, "p_ram_gb": 4, "p_disk_gb": 20}
           and not s.vis("#vzdlg") and "Đã nâng cấp" in (s.txt("#toast") or ""), (s.calls("vm_my_upgrade"), s.txt("#toast")))
        apps = s.txt("#vm-mine-app") or ""
        ck("khung 'VPS NVMe của bạn' có dải tải app như VPS GPU: 💻 App máy tính (Windows) · 📱 App Android", "App máy tính (Windows)" in apps and "App Android" in apps
           and s.js("() => !!document.querySelector('#vm-mine-app a[href*=\"CloudBluePC\"], #vm-mine-app a[href$=\".exe\"], #vm-mine-app a[download]')"), apps)
        s.page.click('[data-vmapp="12"]'); s.page.wait_for_timeout(250)
        ck("nút 📲 App trên VPS-12 → hộp mở bằng app máy tính (blueroblox://pc/<máy ảo>) / Android / trình duyệt", "Mở VPS trong app" in s.dlg()
           and s.js("p => !!document.querySelector('#vzdlg a[href=\"blueroblox://pc/' + p + '\"]') && !!document.querySelector('#vzdlg a[href=\"/play.html?pc=' + p + '\"]')", VPC1), s.dlg())
        s.page.click('#vzdlg .acts [data-vmx]'); s.page.wait_for_timeout(150)
        ck("VPS chưa chạy (VPS-13 đang tạo) không có nút 📲 App", not s.js("() => !!document.querySelector('[data-vmapp=\"13\"]')"))
        s.js("() => { window.__VM.my.items[0].cfg_busy = true; return VMSHOP.mineLoad(true); }"); s.page.wait_for_timeout(500)
        c12 = s.txt('[data-vm="12"]') or ""
        ck("máy chủ đang đặt cấu hình mới → thẻ VPS-12 hiện '⚙️ Đang đổi cấu hình' (tự khởi động lại 1–2 phút), vẫn ▶ Điều khiển được, nút Nâng cấp tạm khoá",
           "Đang đổi cấu hình" in c12 and s.js("() => !!document.querySelector('[data-vm=\"12\"] a[href^=\"/play.html\"]')") and s.js("() => document.querySelector('[data-vmup=\"12\"]').disabled"), c12)
        ck("không lỗi trang (v59)", not s.errors, s.errors)
        s.close()

        s = Site(br, html, False, v59(vm_data(), maint=True), products=prods)
        mt = s.js("() => { const r = document.querySelector('#grid article.m3-row.vm'); const b = r.querySelector('.m3-box button'); return [r.querySelector('.m3-box').innerText.replace(/\\s+/g, ' '), b.disabled]; }")
        ck("BẢO TRÌ riêng VPS NVMe → dòng sản phẩm ghi '🛠️ Đang bảo trì', nút khoá", "Đang bảo trì" in mt[0] and mt[1] is True, mt)
        ck("… khung 'VPS NVMe của bạn' có dòng báo bảo trì; nút Nâng cấp bấm vào chỉ báo, không mở hộp", s.vis("#vm-mine-mt") and "bảo trì" in (s.txt("#vm-mine-mt") or "")
           and (s.page.click('[data-vmup="12"]') or s.page.wait_for_timeout(200) or True) and not s.vis("#vzdlg"), s.txt("#vm-mine-mt"))
        s.page.click("#vm-mine-new"); s.page.wait_for_timeout(300)
        ck("… mở hộp Thuê (nút ➕) → có ghi chú bảo trì, nút Thanh toán khoá", "đang bảo trì" in s.dlg() and s.js("() => document.getElementById('vms-pay').disabled"), s.dlg())
        s.close()

        print("6d. Quản trị v59: đơn giá · đổi cấu hình 1 VPS · bảo trì riêng VPS NVMe")
        s = Site(br, html, True, v59(vm_data()), path="/admin", vp=(1600, 1000))
        admin_open(s, "set")
        st = s.txt("#vma-set") or ""
        ck("tab ⚙ Cài đặt có khung '🛠 Tự chọn cấu hình · ổ thêm · nâng cấp': bật tự chọn / nâng cấp, đơn giá, ổ miễn phí, %, kỳ hạn, giới hạn + bảng xem trước",
           "Tự chọn cấu hình · ổ thêm · nâng cấp" in st and s.js("() => ['vma-s-cust','vma-s-up','vma-s-ucpu','vma-s-uram','vma-s-udisk','vma-s-free','vma-s-short','vma-s-tiers','vma-s-mc','vma-s-mr','vma-s-md'].every(i => !!document.getElementById(i))")
           and "2 vCPU · 4 GB · 40 GB" in (s.txt("#vma-s-prev") or "") and "84.000đ" in (s.txt("#vma-s-prev") or ""), (st[:300], s.txt("#vma-s-prev")))
        s.page.fill("#vma-s-ucpu", "9000"); s.page.fill("#vma-s-tiers", "30, 7, 7, 90"); s.page.uncheck("#vma-s-cust"); s.page.wait_for_timeout(100)
        ck("gõ đơn giá → bảng xem trước tính lại ngay (2 vCPU · 4 GB · 40 GB: 30 ngày 86.000đ)", "86.000đ" in (s.txt("#vma-s-prev") or ""), s.txt("#vma-s-prev"))
        s.page.click("#vma-s-save"); s.page.wait_for_timeout(600)
        pt = (s.calls("vm_admin_settings") or [{}])[-1].get("p_patch", {})
        ck("Lưu → vm_admin_settings kèm unit_cpu 9000 · custom_on false · upgrade_on true · day_tiers [7, 30, 90] · ổ miễn phí 20 · giới hạn 16 / 32 / 200",
           pt.get("unit_cpu") == 9000 and pt.get("custom_on") is False and pt.get("upgrade_on") is True and pt.get("day_tiers") == [7, 30, 90] and pt.get("disk_free_gb") == 20
           and (pt.get("max_cores"), pt.get("max_ram_gb"), pt.get("max_disk_gb")) == (16, 32, 200), pt)
        admin_open(s, "plans")
        ck("⚡ Tự tính giá lấy đơn giá từ máy chủ (9.000đ / vCPU vừa lưu); ổ chỉ tính phần vượt 20 GB miễn phí → VPS 2-2 = 2×9.000 + 2×12.000 = 42.000đ / 30 ngày",
           s.js("() => document.getElementById('vma-c-cpu').value") == "9000" and "30n 42.000đ" in (s.txt("#vma-c-prev") or ""), (s.js("() => document.getElementById('vma-c-cpu').value"), (s.txt("#vma-c-prev") or "")[:400]))
        admin_open(s, "vps")
        s.page.click('[data-vmv="12"] [data-vmav="config"]'); s.page.wait_for_timeout(250)
        s.page.fill("#vma-v-cores", "4"); s.page.fill("#vma-v-ram", "8"); s.page.fill("#vma-v-disk", "60"); s.page.click("#vma-v-go"); s.page.wait_for_timeout(600)
        ck("VPS-12 › 🔧 Đổi cấu hình (không tính tiền khách) → vm_admin_vps {12, config, 4 vCPU · 8192 MB · 60 GB}; dòng VPS hiện 'Đang đổi cấu hình (lần 1)'",
           (s.calls("vm_admin_vps") or [{}])[-1] == {"p_id": 12, "p_act": "config", "p_arg": {"cores": 4, "ram_mb": 8192, "disk_gb": 60}} and "Đang đổi cấu hình (lần 1)" in (s.txt('[data-vmv="12"]') or ""),
           (s.calls("vm_admin_vps"), s.txt('[data-vmv="12"]')))
        ok_mt = s.js("() => !!document.getElementById('mt-vm') && !!document.getElementById('mt-vmmsg') && document.getElementById('mt-vm').closest('label').previousElementSibling.querySelector('#mt-pcmsg') !== null")
        ck("Cài đặt → Bảo trì có thêm dòng 'Bảo trì riêng VPS NVMe' + lời nhắn (ngay dưới dòng VPS GPU)", ok_mt and "Bảo trì riêng VPS NVMe" in (s.js("() => document.getElementById('mt-vm').closest('label').innerText") or ""))
        ck("không lỗi trang (quản trị v59)", not s.errors, s.errors)
        s.close()
        s = Site(br, html, True, vm_data(), path="/admin", vp=(1600, 1000))
        admin_open(s, "set")
        ck("web mới + máy chủ CHƯA chạy SQL v59 → tab Cài đặt chỉ nhắc chạy 'CloudBlue v59 VPS NVMe cau hinh - bam Run', không có ô đơn giá; hộp Thuê không có ô Tự chọn / ổ thêm",
           "CloudBlue v59 VPS NVMe cau hinh" in (s.txt("#vma-set") or "") and not s.js("() => !!document.getElementById('vma-s-ucpu')"), s.txt("#vma-set"))
        s.close()

        print("7. Khách khi chưa bật bán / hết chỗ / chưa chạy SQL · admin xem trước · điện thoại")
        NOROW = "() => !!document.querySelector('#grid [data-vmbuy], #grid .m3-row.vm, #vm-shop')"
        s = Site(br, html, False, vm_data(shop=dict(SHOP, sell=False, admin=False)))
        ck("chưa bật bán → khách không thấy dòng VPS NVMe", not s.js(NOROW))
        s.js("() => { window.__VM.my = { items: [], images: [] }; return VMSHOP.mineLoad(true); }"); s.page.wait_for_timeout(400)
        ck("chưa bật bán + khách chưa có VPS NVMe nào → menu bên KHÔNG hiện mục 'VPS NVMe của tôi'", s.js("() => document.getElementById('nav-vm').hidden") is True)
        s.close()
        s = Site(br, html, True, vm_data(shop=dict(SHOP, sell=False, admin=True)))
        adm = s.js("""() => { const r = document.querySelector('#grid article.m3-row.vm'); return r ? {note: (r.querySelector('.vms-adm') || {}).innerText || '', btn: r.querySelector('.m3-box button').innerText.trim(), dis: r.querySelector('.m3-box button').disabled} : null; }""")
        ck("chưa bật bán nhưng là ADMIN → vẫn thấy dòng VPS NVMe để xem trước, có ghi chú 'Chỉ admin thấy — chưa bật bán'", adm and "Chỉ admin thấy" in adm["note"] and adm["btn"] == "Thuê ngay" and not adm["dis"], adm)
        s.close()
        full = json.loads(json.dumps(SHOP)); [p.__setitem__("free", False) for p in full["plans"]]
        s = Site(br, html, False, vm_data(shop=full))
        so = s.js("""() => { const r = document.querySelector('#grid article.m3-row.vm'); if (!r) return null; const b = r.querySelector('.m3-box button');
          r.querySelector('h3').click(); return {btn: b.innerText.trim(), dis: b.disabled, box: r.querySelector('.m3-box').innerText.replace(/\\s+/g, ' '), dlg: !!document.getElementById('vzdlg') && !document.getElementById('vzdlg').hidden}; }""")
        ck("mọi gói đều hết chỗ → dòng vẫn hiện nhưng nút 'Tạm hết chỗ' bị khoá, bấm vào dòng không mở hộp", so and so["btn"] == "Tạm hết chỗ" and so["dis"] and "Tạm hết chỗ" in so["box"] and not so["dlg"], so)
        s.close()
        s = Site(br, html, False, vm_data(miss=True))
        ck("chưa chạy SQL v56 → không thấy gì, không lỗi trang", not s.js(NOROW) and not s.vis("#vm-mine") and not s.errors, s.errors)
        s.close()
        s = Site(br, html, False, vm_data(), vp=(390, 844), products=prods)
        s.js("() => { window.__FAKE.db.profiles[0].balance = 5000000; profile.balance = 5000000; renderUser(); }"); s.page.wait_for_timeout(300)
        s.js("() => document.querySelector('#grid .m3-row.vm').scrollIntoView({block: 'center'})"); s.page.wait_for_timeout(250)
        ow = s.js("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ck("điện thoại (390px): dòng VPS NVMe không tràn ngang", ow <= 1, ow)
        ph = s.js("""() => { const r = document.querySelector('#grid .m3-row.vm'), b = r.getBoundingClientRect(), c = r.querySelector('.thumb canvas').getBoundingClientRect(), k = r.querySelector('.m3-box button').getBoundingClientRect();
          const sp = [...r.querySelectorAll('.feats.spec span')].map(e => e.getBoundingClientRect());
          return {w: Math.round(b.width), cw: Math.round(c.width), kin: k.left >= b.left - 1 && k.right <= b.right + 1 && k.width >= 120, spin: sp.every(q => q.left >= b.left - 1 && q.right <= b.right + 1 && q.width > 20)}; }""")
        ck("điện thoại: ảnh, chữ cấu hình và nút Thuê ngay nằm gọn trong dòng", ph["w"] <= 390 and ph["cw"] >= 120 and ph["kin"] and ph["spin"], ph)
        s.shot("vm-8-phone.png")
        s.page.click('#grid .m3-row.vm .m3-box button[data-vmbuy]'); s.page.wait_for_timeout(300)
        s.page.click('#vms-plan [data-vmplan="vps2-4"]'); s.page.wait_for_timeout(200)
        pd = s.js("""() => { const d = document.querySelector('#vzdlg .dlg').getBoundingClientRect(), l = document.getElementById('vms-plan'), pay = document.getElementById('vms-pay');
          pay.scrollIntoView({block: 'center'}); const k = pay.getBoundingClientRect();
          return {dw: Math.round(d.width), over: document.documentElement.scrollWidth - document.documentElement.clientWidth, scroll: l.scrollHeight > l.clientHeight + 1 || l.clientHeight < 400,
                  tiles: [...l.querySelectorAll('button')].every(b => b.scrollWidth <= b.clientWidth + 1), pay: k.top >= 0 && k.bottom <= innerHeight + 1 && k.width > 80}; }""")
        ck("điện thoại: hộp Thuê vừa màn hình, bảng cấu hình cuộn riêng, chữ trong ô gói không bị cắt, kéo xuống bấm được nút Thanh toán", pd["dw"] <= 390 and pd["over"] <= 1 and pd["scroll"] and pd["tiles"] and pd["pay"], pd)
        s.js("() => document.getElementById('vms-plan').scrollIntoView({block: 'start'})"); s.page.wait_for_timeout(150)
        s.shot("vm-9-phone-buy.png")
        ck("không lỗi trang (điện thoại)", not s.errors, s.errors)
        s.close()

        print("8. Quản trị: tải dữ liệu LỖI → báo rõ + nút Thử lại (26/11: web thật từng để trắng cả ô vì rpc(...).catch — supabase-js thật không có .catch)")
        adm0 = adm_state(); adm0["hosts"] = []; adm0["vps"] = []
        s = Site(br, html, True, vm_data(adm=adm0, rev={"ok": True, "months": []}, tpl={"hosts": [], "images": [], "jobs": []}), path="/admin", vp=(412, 915))
        admin_open(s)
        ck("chưa có máy chủ nào (web thật lúc mới cài): khung vẫn hiện đủ — 0/0 máy chủ, các mục con, dòng 'Chưa có máy chủ nào'; không báo lỗi",
           s.vis("#vma-top") and s.vis("#pane-vm .subtabs") and "0/0" in (s.txt("#vma-top") or "") and "Chưa có máy chủ nào" in (s.txt("#vma-hosts") or "") and not s.vis("#vma-err") and not s.errors,
           (s.txt("#vma-top"), s.txt("#vma-hosts"), s.errors))
        s.close()
        s = Site(br, html, True, vm_data(admErr="boom-thu-loi"), path="/admin", vp=(412, 915))
        admin_open(s)
        e1 = s.txt("#vma-err") or ""
        ck("hàm vm_admin_state báo lỗi ngay từ lần tải đầu → hiện dòng ⚠️ 'Không tải được dữ liệu VPS ảo hoá: boom-thu-loi' + nút Thử lại (không để trắng), không hiện lời nhắc chạy SQL",
           s.vis("#vma-err") and "Không tải được dữ liệu VPS ảo hoá" in e1 and "boom-thu-loi" in e1 and s.vis("#vma-retry") and not s.vis("#vma-miss") and not s.vis("#vma-top"), (e1, s.vis("#vma-top")))
        s.shot("vm-13-loi-tai.png")
        s.js("() => { window.__VM.admErr = null; }")
        s.page.click("#vma-retry"); s.page.wait_for_timeout(700)
        ck("bấm Thử lại (lần này tải được) → hết dòng lỗi, khung hiện đủ máy chủ", not s.vis("#vma-err") and s.vis("#vma-top") and "pve1" in (s.txt("#vma-hosts") or ""), (s.txt("#vma-err"), s.txt("#vma-top")))
        s.js("() => { window.__VM.admErr = 'mat-mang-tam'; }")
        s.page.click("#vma-reload"); s.page.wait_for_timeout(700)
        e2 = s.txt("#vma-err") or ""
        ck("đang có dữ liệu mà lần tải sau lỗi → GIỮ dữ liệu lần trước (máy chủ vẫn hiện) + dòng ⚠️ ghi 'đang hiện dữ liệu của lần tải trước'",
           s.vis("#vma-err") and "mat-mang-tam" in e2 and "lần tải trước" in e2 and s.vis("#vma-top") and "pve1" in (s.txt("#vma-hosts") or ""), (e2, s.vis("#vma-top")))
        s.js("() => { window.__VM.admErr = null; }")
        s.page.click("#vma-retry"); s.page.wait_for_timeout(700)
        ck("không lỗi trang khi tải lỗi / thử lại", not s.vis("#vma-err") and not s.errors, s.errors)
        s.close()
        adm6 = adm_state(); adm6["hosts"][0]["info"]["lan_ip"] = "2405:4803:ff84:ac60::10"; adm6["hosts"][0]["info"]["ip6_only"] = True
        s = Site(br, html, True, vm_data(adm=adm6), path="/admin")
        admin_open(s)
        href = s.js("() => { const a = document.querySelector('#vma-hosts [data-vmhost] a[href*=\":8006\"]'); return a ? a.getAttribute('href') : null; }")
        ck("máy chủ chỉ có IPv6: nút 🔧 Trang Proxmox mở đúng dạng https://[địa chỉ]:8006", href == "https://[2405:4803:ff84:ac60::10]:8006", href)
        cards = s.js("() => [...document.querySelectorAll('#vma-hosts [data-vmhost]')].map(e => e.innerText)")
        ck("máy chủ chỉ có IPv6 (cbhost báo ip6_only): thẻ máy đó có dòng ⚠️ 'chỉ có IPv6 — mạng chưa cấp IPv4'; máy khác không có", "chỉ có IPv6 — mạng chưa cấp IPv4" in cards[0] and "chỉ có IPv6" not in cards[1], cards)
        s.close()
        # 26/11d: máy chủ chưa có ISO máy mẫu nào → web chỉ cách (cắm USB bản đủ, không cài lại); cbhost đang chép từ USB → hiện tiến độ
        adm7 = adm_state()
        adm7["hosts"][0]["metrics"] = {"cpu": 0.2, "ram_used_mb": 2700, "running": 0, "tpl": [], "iso": [], "ver": "26/11d"}
        adm7["hosts"][1]["metrics"] = {"cpu": 1, "ram_used_mb": 4096, "running": 0, "tpl": [], "iso": [], "ver": "26/11d",
                                       "usb": {"s": "copy", "msg": "thấy 2 ISO máy mẫu trên USB cài đặt — đang chép 2 file (10.5 GB) vào máy chủ, ĐỪNG rút USB <b>x</b>", "t": int(time.time()) - 30}}
        s = Site(br, html, True, vm_data(adm=adm7), path="/admin")
        admin_open(s)
        cards = s.js("() => [...document.querySelectorAll('#vma-hosts [data-vmhost]')].map(e => e.innerText)")
        ck("máy chủ đã lên web nhưng CHƯA có file ISO máy mẫu nào (USB ghép thiếu máy mẫu): thẻ máy chủ nói rõ + chỉ cách 'cắm USB … KHÔNG cần cài lại'",
           "CHƯA có file ISO máy mẫu nào" in cards[0] and "KHÔNG cần cài lại" in cards[0], cards[0][-400:])
        ck("máy chủ đang chép ISO từ USB (cbhost báo metrics.usb): thẻ hiện '💾 USB: … đang chép … ĐỪNG rút USB', không hiện dòng 'chưa có ISO'; chữ máy chủ gửi lên không chạy thành mã",
           "💾 USB: thấy 2 ISO máy mẫu" in cards[1] and "ĐỪNG rút USB <b>x</b>" in cards[1] and "CHƯA có file ISO máy mẫu nào" not in cards[1] and not s.errors, (cards[1][-400:], s.errors))
        s.close()
        adm8 = adm_state()
        adm8["hosts"][0]["metrics"]["usb"] = {"s": "done", "msg": "đã chép xong 2 ISO máy mẫu", "t": int(time.time()) - 7200}
        adm8["hosts"][1]["metrics"]["usb"] = {"s": "err", "msg": "chép ISO máy mẫu từ USB CHƯA được", "t": int(time.time()) - 5}
        s = Site(br, html, True, vm_data(adm=adm8), path="/admin")
        admin_open(s)
        cards = s.js("() => [...document.querySelectorAll('#vma-hosts [data-vmhost]')].map(e => e.innerText)")
        ck("dòng USB 'đã chép xong' tự ẩn sau 1 giờ; máy đã có máy mẫu / bản cbhost cũ (không báo danh sách ISO) không hiện dòng 'chưa có ISO'; lỗi chép thì hiện",
           "💾 USB" not in cards[0] and "CHƯA có file ISO máy mẫu nào" not in cards[0] and "💾 USB: chép ISO máy mẫu từ USB CHƯA được" in cards[1] and not s.errors, cards)
        s.close()
        br.close()
    print("\nKẾT QUẢ: %d đạt, %d lỗi" % (OK, FAIL))
    sys.exit(1 if FAIL else 0)


main()
