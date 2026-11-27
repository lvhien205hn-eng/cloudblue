# -*- coding: utf-8 -*-
"""Thử cbhost.py (máy chủ Proxmox của VPS ảo hoá) bằng Proxmox GIẢ (fakepve.py: qm + pvesh) + web GIẢ (vm_host_hello / vm_host_poll).
   Chạy mọi máy, không cần Proxmox:  python3 proxmox/tests/test_cbhost.py"""
import hashlib, importlib.util, json, os, re, socket, stat, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


tmp = tempfile.mkdtemp(prefix="cbhost_")
bind = os.path.join(tmp, "bin"); os.makedirs(bind)
for tool in ("qm", "pvesh", "pvesm"):
    p = os.path.join(bind, tool)
    open(p, "w").write("#!/bin/sh\nexec %s %s %s \"$@\"\n" % (sys.executable, os.path.join(HERE, "fakepve.py"), tool))
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
STATE = os.path.join(tmp, "pve.json")
# 27/11e · kho proxy: systemctl GIẢ (ghi lại lệnh; is-active theo file đánh dấu) + nơi tải cbpool giả (file://)
SYSLOG = os.path.join(tmp, "systemctl.log"); SYSON = os.path.join(tmp, "pool.on")
p_sc = os.path.join(bind, "systemctl")
open(p_sc, "w").write("#!%s\nimport sys, os\na = sys.argv[1:]\nopen(%r, 'a').write(' '.join(a) + '\\n')\n"
                      "if a[:1] == ['is-active']:\n    on = os.path.exists(%r); print('active' if on else 'inactive'); sys.exit(0 if on else 3)\n"
                      "if a[:2] == ['enable', '--now'] or a[:1] == ['restart']: open(%r, 'w').write('1')\n"
                      "if a[:2] == ['disable', '--now'] and os.path.exists(%r): os.remove(%r)\n" % (sys.executable, SYSLOG, SYSON, SYSON, SYSON, SYSON))
os.chmod(p_sc, 0o755)
RAWD = os.path.join(tmp, "rawpool"); os.makedirs(RAWD)
os.environ.update(CBHOST_SYSTEMCTL=p_sc, CBHOST_POOL_RAW="file://" + RAWD + "/", CBHOST_POOL_BIN=os.path.join(tmp, "cbpool-bin"),
                  CBHOST_POOL_CONF=os.path.join(tmp, "cbpool.json"), CBHOST_POOL_CTL=os.path.join(tmp, "pool.sock"),
                  CBHOST_POOL_UNIT=os.path.join(tmp, "cloudblue-pool.service"))
os.environ.update(FAKE_PVE_STATE=STATE, CBHOST_QM=os.path.join(bind, "qm"), CBHOST_PVESH=os.path.join(bind, "pvesh"), CBHOST_PVESM=os.path.join(bind, "pvesm"),
                  CBHOST_CONF=os.path.join(tmp, "cbhost.conf"), CBHOST_SECRET=os.path.join(tmp, "cbhost.secret"), CBHOST_STATE=os.path.join(tmp, "state.json"))
NODE = socket.gethostname().split(".")[0]


def pve(): return json.load(open(STATE))
def pve_set(fn):
    d = pve(); fn(d); json.dump(d, open(STATE, "w"))


json.dump({"vms": {"9000": {"name": "tpl-win10-22h2", "status": "stopped", "template": True, "disks": {"scsi0": 32}},
                   "9001": {"name": "win-dang-cai", "status": "running", "template": False, "disks": {"scsi0": 60}}},
           "log": [], "linked_ok": True, "guest_after": 2}, open(STATE, "w"))
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
spec = importlib.util.spec_from_file_location("cbhost", os.path.join(ROOT, "cbhost.py"))
cb = importlib.util.module_from_spec(spec); spec.loader.exec_module(cb)
cb.log = lambda *a: None
cb.POOL_FILE = ("cbpool-x86_64", "")          # mục 1–16: kho proxy không tải gì (không lẫn vào các phép thử tải khác) — mục 17 tự đặt md5


class FakeWeb:
    """Web giả: giữ trạng thái máy chủ + danh sách VPS muốn có; ghi lại các lần gọi."""
    def __init__(self):
        self.calls, self.status, self.vps, self.tickets, self.err = [], "new", [], {}, ""
        self.secret_hash = None
        self.jobs = None; self.jtickets = {}               # None = web cũ (chưa v57): không trả tpl_jobs
        self.tpl = ["tpl-win10-22h2"]                      # máy mẫu web cần (vm_images đang bán)

    def rpc(self, fn, body, timeout=25):
        self.calls.append((fn, json.loads(json.dumps(body))))
        if fn == "vm_host_hello":
            self.secret_hash = hashlib.sha256(body["p_secret"].encode()).hexdigest()
            return {"ok": True, "id": "h1", "status": self.status, "name": "pve-thu"}
        if fn == "vm_host_poll":
            if hashlib.sha256(body["p_secret"].encode()).hexdigest() != self.secret_hash: return {"ok": False, "err": "BAD_SECRET"}
            for x in body.get("p_vps") or []:
                if x.get("ticket_hash"): self.tickets[x["id"]] = x["ticket_hash"]
            for x in body.get("p_tpl") or []:
                if x.get("ticket_hash"): self.jtickets[x["id"]] = x["ticket_hash"]
            r = {"ok": True, "status": self.status, "name": "pve-thu", "vps": json.loads(json.dumps(self.vps)) if self.status != "new" else [],
                 "tpl": list(self.tpl), "poll_s": 10}
            if self.jobs is not None: r["tpl_jobs"] = json.loads(json.dumps(self.jobs))
            return r
        return None


HW = hashlib.sha256(b"vps-7").hexdigest()
def item(**kw):
    d = {"id": 7, "slot": 1, "want": "running", "inst": 1, "boot": 0, "cores": 2, "ram_mb": 2048, "disk_gb": 40, "tpl": "tpl-win10-22h2", "hw": HW,
         "name": "vps-7", "enrolled": False}
    d.update(kw); return d


def wait_idle(h, t=15):
    t0 = time.time()
    while h.busy and time.time() - t0 < t: time.sleep(0.05)


def sync(h, n=2):
    """n vòng hỏi việc (vòng sau mới làm theo danh sách web vừa trả) — chờ việc nền xong sau mỗi vòng."""
    for _ in range(n): h.poll_once(); wait_idle(h)


def last_poll(w): return [b for f, b in w.calls if f == "vm_host_poll"][-1]
def rep_of(w, vid=7): return next((x for x in (last_poll(w).get("p_vps") or []) if x["id"] == vid), None)
def qmlog(pat): return [x for x in pve()["log"] if re.search(pat, " ".join(x))]


print("1. Lên web · chờ duyệt")
w = FakeWeb(); h = cb.Host(web=w)
ok = h.poll_once()
sec = open(os.environ["CBHOST_SECRET"]).read().strip()
hello = [b for f, b in w.calls if f == "vm_host_hello"][0]
ck("tự sinh mã riêng (64 ký tự hex, file 0600) và chào web kèm cấu hình máy (node, số luồng, RAM, ổ chứa máy ảo)",
   ok and re.fullmatch(r"[0-9a-f]{64}", sec) and oct(os.stat(os.environ["CBHOST_SECRET"]).st_mode & 0o777) == "0o600"
   and hello["p_info"]["host"] == NODE and hello["p_info"]["threads"] >= 1 and hello["p_info"]["disk_gb"] == 1000 and hello["p_secret"] == sec, hello)
ck("chờ duyệt → không đụng máy ảo nào; báo máy mẫu đang có (tpl-win10-22h2)",
   not qmlog(r"^qm (clone|start|destroy)") and last_poll(w)["p_metrics"]["tpl"] == ["tpl-win10-22h2"] and last_poll(w)["p_vps"] == [], last_poll(w))
h2 = cb.Host(web=FakeWeb()); h2.poll_once()
ck("chạy lại dùng đúng mã cũ (không sinh mã mới)", h2.sec == sec)

print("2. Web giao 1 VPS → tạo máy ảo → đưa vé → agent đăng ký")
w.status = "ready"; w.vps = [item()]
h.poll_once()
ck("vòng đầu sau khi duyệt: nhận danh sách việc (chưa làm ngay — vòng sau làm)", h.status == "ready" and len(h.want) == 1 and not qmlog(r"^qm clone"))
h.poll_once(); wait_idle(h)
v = pve()["vms"].get(str(100007))
ck("tạo máy ảo 100007 'vps-7' nhân bản ĐẦY ĐỦ từ máy mẫu 9000 vào ổ local-lvm", v and v["name"] == "vps-7" and v["from"] == "9000" and v["full"] == "1" and v["storage"] == "local-lvm", v)
ck("đặt 2 nhân · 2048MB · không balloon · tự bật cùng máy chủ · bật guest agent · thẻ cloudblue · mã SMBIOS riêng",
   v["cfg"].get("cores") == "2" and v["cfg"].get("memory") == "2048" and v["cfg"].get("balloon") == "0" and v["cfg"].get("onboot") == "1"
   and v["cfg"].get("agent") == "enabled=1" and v["cfg"].get("tags") == "cloudblue" and v["cfg"].get("smbios1", "").startswith("uuid=" + HW[:8] + "-"), v["cfg"])
ck("nới ổ hệ thống 32GB → 40GB, rồi bật máy", v["disks"]["scsi0"] == 40 and v["status"] == "running", v)
ck("lúc đang tạo báo 'creating' (chưa đưa vé)", rep_of(w) == {"id": 7, "state": "creating", "inst": 0} or (rep_of(w) or {}).get("state") == "creating", rep_of(w))
h.poll_once()
r = rep_of(w); s = json.load(open(os.environ["CBHOST_STATE"]))["7"]
ck("máy chạy, agent chưa đăng ký → báo 'running' + dấu băm của vé (vé thật chỉ nằm ở máy chủ)", r["state"] == "running" and r["inst"] == 1
   and r["ticket_hash"] == hashlib.sha256(s["ticket"].encode()).hexdigest() and "ticket" not in json.dumps(last_poll(w)).replace("ticket_hash", ""), r)
ck("chưa ghi vé vào máy ảo khi web CHƯA nhận dấu băm", not pve()["vms"]["100007"].get("files"))
h.poll_once()
f = pve()["vms"]["100007"].get("files") or {}
ck("Windows chưa lên (guest agent chưa trả lời) → chưa ghi", not f, f)
h.poll_once()
f = pve()["vms"]["100007"].get("files") or {}
seed = json.loads(f.get("C:\\CloudBluePC\\seed.json") or "{}")
ck("guest agent trả lời → ghi C:\\CloudBluePC\\seed.json {hw, ticket} đúng vé web đã nhận", seed.get("hw") == HW
   and hashlib.sha256(seed.get("ticket", "").encode()).hexdigest() == w.tickets[7], seed)
w.vps = [item(enrolled=True)]
h.poll_once(); h.poll_once()
ck("agent đã đăng ký → thôi gửi vé, xoá vé khỏi sổ máy chủ", "ticket_hash" not in rep_of(w) and not json.load(open(os.environ["CBHOST_STATE"]))["7"].get("ticket"), rep_of(w))

print("3. Tắt · bật · khởi động cứng")
w.vps = [item(enrolled=True, want="stopped")]; sync(h)
ck("web muốn tắt → tắt êm (shutdown, quá 90 giây thì tắt hẳn)", pve()["vms"]["100007"]["status"] == "stopped" and qmlog(r"^qm shutdown 100007 --timeout 90 --forceStop 1"))
w.vps = [item(enrolled=True, want="running")]; sync(h)
ck("web muốn bật → bật lại", pve()["vms"]["100007"]["status"] == "running")
w.vps = [item(enrolled=True, boot=1)]; sync(h, 3)
ck("khởi động cứng (boot +1) → qm reset đúng 1 lần", pve()["vms"]["100007"].get("resets") == 1, pve()["vms"]["100007"])
pve_set(lambda d: d["vms"]["100007"].__setitem__("status", "stopped"))
sync(h, 1)
ck("máy ảo bị tắt ngoài ý muốn (khách tắt Windows) mà web muốn chạy → tự bật lại", pve()["vms"]["100007"]["status"] == "running")

print("4. Cài lại · xoá · thiếu máy mẫu")
w.vps = [item(inst=2)]; sync(h)
s2 = json.load(open(os.environ["CBHOST_STATE"]))["7"]
ck("cài lại (bản cài 2) → xoá máy ảo cũ, nhân bản lại, vé MỚI", qmlog(r"^qm destroy 100007 --purge 1") and s2["inst"] == 2 and s2["ticket"] and s2["ticket"] != s["ticket"]
   and pve()["vms"]["100007"]["status"] == "running" and not pve()["vms"]["100007"].get("files"), s2)
w.vps = [item(inst=2, want="deleted")]; sync(h, 3)
ck("web xoá VPS → xoá máy ảo (kèm ổ) → báo 'missing'", "100007" not in pve()["vms"] and rep_of(w)["state"] == "missing" and "7" not in json.load(open(os.environ["CBHOST_STATE"])), rep_of(w))
w.vps = [item(id=8, tpl="tpl-win2022", hw=hashlib.sha256(b"8").hexdigest())]; sync(h)
ck("máy mẫu web cần mà máy chủ chưa có → báo lỗi rõ, không tạo gì", rep_of(w, 8) and rep_of(w, 8)["state"] == "error" and "tpl-win2022" in rep_of(w, 8)["err"]
   and "100008" not in pve()["vms"], rep_of(w, 8))

print("5. An toàn: dữ liệu lạ từ web không thành lệnh")
w.vps = []; sync(h)
n0 = len(pve()["log"])
w.vps = [item(id=9, tpl="tpl; rm -rf /"), item(id=10, hw="abc"), item(id="11 && reboot"), item(id=12, cores=999), item(id=13, want="xoa-het")]
sync(h)
bad = [x for x in pve()["log"][n0:] if x[0] == "qm" and x[1] in ("clone", "destroy", "start", "set")]
ck("tên máy mẫu chứa ký tự lạ / dấu máy sai / số VPS lạ / cấu hình quá cỡ / trạng thái lạ → bỏ qua, không gọi qm", not bad and last_poll(w)["p_vps"] == [], bad)
ck("mọi lệnh Proxmox chạy dạng danh sách tham số (không qua shell)", "shell=True" not in open(os.path.join(ROOT, "cbhost.py")).read())
ck("không đụng máy ảo ngoài phần quản lý (9001 'win-dang-cai', máy của node khác)", "9001" in pve()["vms"] and pve()["vms"]["9001"]["status"] == "running"
   and not qmlog(r"^qm (stop|shutdown|destroy|reset) (9001|999)\b"))

print("6. Mất sổ máy chủ · nhân bản liên kết · ổ không thu nhỏ")
w.vps = [item(id=20, hw=hashlib.sha256(b"20").hexdigest(), enrolled=True)]
sync(h, 3)
os.remove(os.environ["CBHOST_STATE"])
h3 = cb.Host(web=w); w.calls.clear(); h3.hello_ok = True; h3.status = "ready"; h3.want = w.vps
n0 = len(qmlog(r"^qm clone"))
h3.poll_once(); wait_idle(h3)
ck("cài lại cbhost (mất sổ) mà máy ảo còn → nhận lại, KHÔNG tạo lại (dữ liệu khách giữ nguyên)", len(qmlog(r"^qm clone")) == n0 and "100020" in pve()["vms"]
   and (rep_of(w, 20) or {}).get("state") == "running", rep_of(w, 20))
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": False}))
pve_set(lambda d: d.__setitem__("linked_ok", False))
h4 = cb.Host(web=w); h4.hello_ok = True; h4.status = "ready"; h4.want = [item(id=21, hw=hashlib.sha256(b"21").hexdigest(), disk_gb=20)]
h4.poll_once(); wait_idle(h4)
v21 = pve()["vms"].get("100021") or {}
ck("đặt nhân bản liên kết mà ổ không hỗ trợ → tự nhân bản đầy đủ; gói 20GB < máy mẫu 32GB → giữ 32GB (không thu nhỏ)",
   qmlog(r"^qm clone 9000 100021 --name vps-21 --full 0") and v21.get("full") == "1" and v21["disks"]["scsi0"] == 32 and not qmlog(r"^qm resize 100021"), v21)

print("6b. Máy mẫu lỡ đã đăng ký CloudBlue → không đưa vé")
pve_set(lambda d: d["vms"].__setitem__("9100", {"name": "tpl-win10-1511", "status": "stopped", "template": True, "disks": {"scsi0": 30},
                                                 "files": {"C:\\CloudBluePC\\identity.json": '{"id": "x", "token": "y"}'}}))
pve_set(lambda d: d.__setitem__("guest_after", 1))
h5 = cb.Host(web=w); h5.hello_ok = True; h5.status = "ready"
w.vps = [item(id=40, tpl="tpl-win10-1511", hw=hashlib.sha256(b"40").hexdigest())]; h5.want = w.vps
sync(h5, 4)
f40 = (pve()["vms"].get("100040") or {}).get("files") or {}
ck("bản nhân ra có identity.json (máy mẫu đã đăng ký) → KHÔNG ghi vé, báo lỗi 'làm lại máy mẫu'", "C:\\CloudBluePC\\seed.json" not in f40
   and (rep_of(w, 40) or {}).get("state") == "error" and "làm lại máy mẫu" in (rep_of(w, 40) or {}).get("err", ""), (rep_of(w, 40), list(f40)))

print("7. Lệnh status chỉ xem")
n0 = len(pve()["log"])
w.vps = [item(id=30, hw=hashlib.sha256(b"30").hexdigest())]
real_web, cb.Web = cb.Web, (lambda c: w)                        # KHÔNG gọi web thật trong bài thử
try: rc = cb.cmd_status()
finally: cb.Web = real_web
ck("python3 cbhost.py status → không tạo / xoá máy ảo nào", not [x for x in pve()["log"][n0:] if x[0] == "qm" and x[1] in ("clone", "destroy", "start")] and "100030" not in pve()["vms"], rc)

print("8. Tự cập nhật (chỉ khi chạy bằng dịch vụ, không có máy ảo đang dựng)")
src = open(os.path.join(ROOT, "cbhost.py"), encoding="utf-8").read()
upd = os.path.join(tmp, "upd"); os.makedirs(upd)
def put(name, txt):
    open(os.path.join(upd, name), "w", encoding="utf-8").write(txt); return "file://" + os.path.join(upd, name)
u_new = put("new.py", src.replace('CBHOST_VER = "%s"' % cb.CBHOST_VER, 'CBHOST_VER = "99/12z"'))
u_same = put("same.py", src)
u_bad = put("bad.py", src.replace('CBHOST_VER = "%s"' % cb.CBHOST_VER, 'CBHOST_VER = "99/12y"').replace("def poll_once(self, act=True):", "def poll_once(self, act=True)"))
u_html = put("html.py", "<html>" + "x" * 5000 + "</html>")
r = cb.fetch_update(u_new)
ck("GitHub có bản khác (99/12z) → lấy được bản mới", r and r[0] == "99/12z" and "99/12z" in r[1], r and r[0])
ck("cùng bản / trang lạ (không phải cbhost) → không cập nhật", cb.fetch_update(u_same) is None and cb.fetch_update(u_html) is None)
try: cb.fetch_update(u_bad); bad_ok = False
except SyntaxError: bad_ok = True
ck("bản mới lỗi cú pháp → không nhận (giữ bản đang chạy)", bad_ok)
dst = os.path.join(tmp, "cbhost-cai.py"); open(dst, "w").write("cu")
cb.apply_update("99/12z", r[1], dst)
ck("thay file bằng bản mới (chạy được)", open(dst, encoding="utf-8").read() == r[1] and os.stat(dst).st_mode & 0o111 and not os.path.exists(dst + ".new"))
hu = cb.Host(web=w); hu.busy = {}
os.environ.pop("INVOCATION_ID", None)
ck("chạy tay (không phải dịch vụ) → không tự cập nhật", not cb.update_due(hu, time.time(), 0))
os.environ["INVOCATION_ID"] = "x"
due = cb.update_due(hu, time.time(), 0)
hu.busy = {5: object()}; busy = cb.update_due(hu, time.time(), 0); hu.busy = {}
soon = cb.update_due(hu, time.time(), time.time() - 600)
late = cb.update_due(hu, time.time(), time.time() - 1000)
hu.c["auto_update"] = False; off = cb.update_due(hu, time.time(), 0); hu.c["auto_update"] = True
ck("dịch vụ: tới giờ → xem bản mới; đang dựng máy ảo / chưa đủ 15 phút / tắt auto_update → chờ; quá 15 phút → xem (27/11f)",
   due and not busy and not soon and late and not off and cb.UPD_EVERY_S == 900, (due, busy, soon, late, off))
os.environ.pop("INVOCATION_ID", None)

print("9. Bảng điều khiển máy mẫu: dựng từ ISO → đưa vé → lưu thành mẫu · sửa · huỷ")
ISO = "local:iso/CloudBlue-MayMau-win2012r2.iso"
pve_set(lambda d: d.update(isos=[ISO, "local:iso/virtio-win-0.1.240.iso"], guest_after=1))
wj = FakeWeb(); wj.status = "ready"; hj = cb.Host(web=wj)
hj.poll_once()
pt = last_poll(wj)
ck("web cũ (chưa v57) → không gửi p_tpl (tránh lỗi gọi hàm), vẫn báo file ISO trên máy chủ (bỏ đường dẫn lạ)", "p_tpl" not in pt
   and [x["volid"] for x in pt["p_metrics"]["iso"]] == [ISO, "local:iso/virtio-win-0.1.240.iso"], pt["p_metrics"].get("iso"))
JHW = hashlib.sha256(b"mau-3").hexdigest()
def job(**kw):
    d = {"id": 3, "src": "iso", "iso": ISO, "tpl": "tpl-win2012r2", "cores": 2, "ram_mb": 2048, "disk_gb": 20, "hw": JHW, "want": "running", "enrolled": False}
    d.update(kw); return d
wj.jobs = [job()]
hj.poll_once(); hj.poll_once(); wait_idle(hj)
v = next(((k, x) for k, x in pve()["vms"].items() if x["name"] == "cbmau-3"), (None, None))
c = (v[1] or {}).get("cfg") or {}
ck("dựng từ ISO: máy ảo cbmau-3 số 99000 · ổ SCSI 20GB local-lvm · gắn ISO · SeaBIOS · VirtIO SCSI · mạng VirtIO vmbr0 · QEMU agent · không tự bật cùng máy chủ · mã SMBIOS riêng · đã bật",
   v[0] == "99000" and v[1]["disks"] == {"scsi0": 20} and v[1]["cdrom"] == {"ide2": ISO} and c.get("bios") == "seabios" and c.get("ostype") == "win8"
   and c.get("scsihw") == "virtio-scsi-single" and c.get("net0") == "virtio,bridge=vmbr0" and c.get("agent") == "enabled=1" and c.get("onboot") == "0"
   and c.get("vga") == "std" and c.get("smbios1", "").startswith("uuid=" + JHW[:8]) and v[1]["status"] == "running", v)
hj.poll_once()
tr = {x["id"]: x for x in last_poll(wj).get("p_tpl") or []}.get(3) or {}
sj = json.load(open(os.environ["CBHOST_STATE"]))["t3"]
ck("máy chạy → báo 'running' + dấu băm vé (web v57)", tr.get("state") == "running" and tr.get("ticket_hash") == hashlib.sha256(sj["ticket"].encode()).hexdigest(), tr)
hj.poll_once(); hj.poll_once()
f = pve()["vms"]["99000"].get("files") or {}
ck("web nhận dấu băm → ghi seed.json {hw, ticket} vào máy mẫu qua guest agent", json.loads(f.get("C:\\CloudBluePC\\seed.json") or "{}") == {"hw": JHW, "ticket": sj["ticket"]}, f)
pve_set(lambda d: d["vms"]["99000"]["files"].update({"C:\\CloudBluePC\\identity.json": json.dumps({"id": "pc-mau", "token": "t0k"})}))
wj.jobs = [job(enrolled=True)]
hj.poll_once(); hj.poll_once()
ck("agent đã đăng ký → thôi đưa vé (không còn dấu băm)", "ticket_hash" not in ({x["id"]: x for x in last_poll(wj)["p_tpl"]}.get(3) or {}) and not json.load(open(os.environ["CBHOST_STATE"]))["t3"].get("ticket"))
pve_set(lambda d: d["vms"].update({"9100": {"name": "tpl-win2012r2", "status": "stopped", "template": True, "disks": {"scsi0": 20}},
                                   "9101": {"name": "tpl-win2012r2-cu", "status": "stopped", "template": True, "disks": {"scsi0": 20}}}))
wj.jobs = [job(want="save", enrolled=True)]
hj.poll_once(); hj.poll_once(); wait_idle(hj, 30)
vm = pve()["vms"]
f = vm["99000"].get("files") or {}
ck("LƯU: dừng agent (taskkill pythonw) → xoá mã máy / vé / hạn thuê trong máy ({}) → tắt → gỡ ISO",
   vm["99000"].get("execs") == [["taskkill", "/f", "/im", "pythonw.exe"]] and all(f.get("C:\\CloudBluePC\\" + n) == "{}" for n in ("identity.json", "seed.json", "rent.json"))
   and vm["99000"]["cdrom"] == {"ide2": "none"}, (vm["99000"].get("execs"), f, vm["99000"].get("cdrom")))
ck("LƯU: máy mẫu cũ tpl-win2012r2 → tpl-win2012r2-cu (bản dự phòng cũ hơn bị xoá) · máy ảo tạm đổi tên tpl-win2012r2 + thành máy mẫu",
   vm["99000"]["name"] == "tpl-win2012r2" and vm["99000"].get("template") and vm["9100"]["name"] == "tpl-win2012r2-cu" and "9101" not in vm, {k: (x["name"], x.get("template")) for k, x in vm.items()})
hj.poll_once()
ck("báo web 'saved'", ({x["id"]: x for x in last_poll(wj)["p_tpl"]}.get(3) or {}).get("state") == "saved")
wj.jobs = []
hj.poll_once()
ck("web ghi nhận xong (thôi gửi việc) → máy chủ quên sổ việc này", "t3" not in json.load(open(os.environ["CBHOST_STATE"])))
d0 = pve()
hv = cb.Host(web=FakeWeb()); hv.want = [dict(item(id=55, tpl="tpl-win2012r2"))]; hv.status = "ready"
hv.st["55"] = {"inst": 1, "boot": 0, "ticket": "abc", "sent": True, "seeded": False}
pve_set(lambda d: d["vms"].update({"100055": {"name": "vps-55", "status": "running", "template": False, "disks": {"scsi0": 20}, "ga": 5,
                                              "files": {"C:\\CloudBluePC\\identity.json": "{}"}}}))
hv.seed(55, hv.want[0])
ck("VPS nhân từ máy mẫu vừa lưu (identity.json = {}) → vẫn đưa vé bình thường (không báo 'máy mẫu đã đăng ký')",
   json.loads((pve()["vms"]["100055"].get("files") or {}).get("C:\\CloudBluePC\\seed.json") or "{}").get("ticket") == "abc" and not hv.st["55"].get("err"), hv.st["55"])

wj.jobs = [job(id=4, src="tpl", iso="", hw=hashlib.sha256(b"mau-4").hexdigest())]
hj.poll_once(); hj.poll_once(); wait_idle(hj)
v4 = next(((k, x) for k, x in pve()["vms"].items() if x["name"] == "cbmau-4"), (None, None))
ck("SỬA máy mẫu: nhân bản tpl-win2012r2 (máy 99000) ra máy ảo tạm cbmau-4 (số tiếp theo), đặt cấu hình, bật", v4[0] == "99001" and v4[1]["from"] == "99000"
   and v4[1]["cfg"].get("agent") == "enabled=1" and v4[1]["cfg"].get("onboot") == "0" and v4[1]["status"] == "running", v4)
wj.jobs = [job(id=4, src="tpl", iso="", hw=hashlib.sha256(b"mau-4").hexdigest(), want="cancel")]
hj.poll_once(); hj.poll_once(); wait_idle(hj); hj.poll_once()
ck("HUỶ: xoá máy ảo tạm cbmau-4, máy mẫu giữ nguyên, báo 'cancelled'", "99001" not in pve()["vms"] and pve()["vms"]["99000"].get("template")
   and ({x["id"]: x for x in last_poll(wj)["p_tpl"]}.get(4) or {}).get("state") == "cancelled")
wj.jobs = [job(id=5, iso="local:iso/khong-co.iso", hw=hashlib.sha256(b"mau-5").hexdigest())]
hj.poll_once(); hj.poll_once(); wait_idle(hj); hj.poll_once()
tr = {x["id"]: x for x in last_poll(wj)["p_tpl"]}.get(5) or {}
ck("ISO không có trên máy chủ → báo lỗi rõ (không tạo máy ảo dở)", tr.get("state") == "error" and "tạo máy ảo lỗi" in tr.get("err", "")
   and not any(x["name"] == "cbmau-5" for x in pve()["vms"].values()), tr)
n0 = len(pve()["log"])
wj.jobs = [job(id=6, iso="local:iso/../../etc/x.iso"), job(id=7, tpl="tpl;rm -rf /"), job(id=8, cores=999), job(id=9, want="xoa"), "x"]
hj.poll_once(); hj.poll_once(); wait_idle(hj)
ck("việc máy mẫu lạ từ web (đường dẫn ISO lạ / tên lạ / số lạ / lệnh lạ) → bỏ qua, không thành lệnh", not qmlog(r"^qm (create|clone)") or
   all("cbmau-6" not in " ".join(x) and "rm -rf" not in " ".join(x) for x in pve()["log"][n0:]), pve()["log"][n0:])
wj.jobs = None


print("10. Tự dựng máy mẫu từ ISO (auto_tpl — đặt sẵn bởi ISO CloudBlue-Proxmox): không cần web, không cần bấm")
ISO16 = "local:iso/CloudBlue-MayMau-win2016.iso"; ISO19 = "local:iso/CloudBlue-MayMau-win2019.iso"
class DeadWeb:
    def __init__(self): self.calls, self.err, self.url = [], "mất mạng", "x"
    def rpc(self, fn, body, timeout=25): self.calls.append((fn, body)); return None
SF = os.environ["CBHOST_STATE"]
pve_set(lambda d: d.update(isos=[ISO, ISO16, "local:iso/virtio-win-0.1.240.iso"], guest_after=1))
h0 = cb.Host(web=DeadWeb()); h0.poll_once(); wait_idle(h0)
ck("auto_tpl tắt (máy chủ cài bằng lệnh thường) → có ISO máy mẫu cũng KHÔNG tự dựng", not any(x["name"].startswith("cbmau-win") for x in pve()["vms"].values()))
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm", "auto_tpl": True, "host_name": "vps-ab12"}))
cb.AUTO_CHK_S = 0
ha = cb.Host(web=DeadWeb())
ck("cấu hình: auto_tpl bật · tên riêng của máy chủ (host_name) báo lên web thay tên node", ha.c["auto_tpl"] is True and ha.pve.info()["host"] == "vps-ab12", ha.pve.info())
r = ha.poll_once(); wait_idle(ha)
va = next(((k, x) for k, x in pve()["vms"].items() if x["name"] == "cbmau-win2016"), (None, None))
c = (va[1] or {}).get("cfg") or {}
ck("chưa gọi được web (mất mạng) vẫn TỰ tạo máy ảo cbmau-win2016 từ ISO: số 99500 · win10 · 2 nhân · 2 GB · ổ 20 GB · gắn ISO · đã bật",
   r is False and va[0] == "99500" and c.get("ostype") == "win10" and c.get("cores") == "2" and c.get("memory") == "2048" and va[1]["disks"] == {"scsi0": 20}
   and va[1]["cdrom"] == {"ide2": ISO16} and va[1]["status"] == "running", va)
ck("bản đã có máy mẫu (tpl-win2012r2) → không dựng lại", not any(x["name"] == "cbmau-win2012r2" for x in pve()["vms"].values()))
ha.poll_once(); wait_idle(ha); ha.poll_once(); wait_idle(ha)
v = pve()["vms"]["99500"]
ck("Windows chưa cài xong (chưa có maymau.done) → chờ: không tắt, không đổi tên, không tạo thêm máy", v["name"] == "cbmau-win2016" and not v.get("template") and v["status"] == "running"
   and not v.get("execs") and sum(1 for x in pve()["vms"].values() if x["name"] == "cbmau-win2016") == 1, v)
pve_set(lambda d: d["vms"]["99500"].setdefault("files", {}).update({"C:\\CloudBluePC\\vm\\maymau.done": "ok 24.11a"}))
ha.poll_once(); wait_idle(ha, 30)
v = pve()["vms"]["99500"]
ck("máy mẫu báo cài xong (maymau.done) → TỰ dừng agent, tắt, gỡ ISO, đặt tên tpl-win2016, chuyển thành máy mẫu",
   v["name"] == "tpl-win2016" and v.get("template") and v["cdrom"] == {"ide2": "none"} and v.get("execs") == [["taskkill", "/f", "/im", "pythonw.exe"]]
   and json.load(open(SF))["awin2016"].get("done") is True, (v, json.load(open(SF)).get("awin2016")))
n0 = len(pve()["log"]); ha.poll_once(); wait_idle(ha); ha.poll_once(); wait_idle(ha)
ck("xong rồi → các vòng sau không tạo / đổi gì nữa", not [x for x in pve()["log"][n0:] if x[0] == "qm" and x[1] in ("create", "set", "template", "destroy", "shutdown")], pve()["log"][n0:])
pve_set(lambda d: d["vms"].pop("99500")); ha.poll_once(); wait_idle(ha); ha.poll_once(); wait_idle(ha)
ck("máy mẫu bị xoá tay sau khi đã dựng xong → KHÔNG tự dựng lại (tránh làm trái ý admin)", not any(x["name"] == "cbmau-win2016" for x in pve()["vms"].values()))

wn = FakeWeb(); hn = cb.Host(web=wn)                           # máy chủ vừa lên web, CHỜ DUYỆT
pve_set(lambda d: d.update(isos=[ISO, ISO16, ISO19]))
hn.iso_t = 0; hn.jobs = [job(id=11, iso=ISO19, tpl="tpl-win2019")]
hn.poll_once(); wait_idle(hn)
ck("admin đang dựng đúng bản đó bằng bảng điều khiển trên web → nhường, không tự dựng trùng", not any(x["name"] == "cbmau-win2019" for x in pve()["vms"].values()))
hn.jobs = []
hn.poll_once(); wait_idle(hn); hn.poll_once()
v19 = next(((k, x) for k, x in pve()["vms"].items() if x["name"] == "cbmau-win2019"), (None, None))
ta = last_poll(wn)["p_metrics"].get("tpl_auto") or []
ck("máy chủ CHỜ DUYỆT vẫn tự dựng máy mẫu (xong sớm, duyệt là bán được) + báo tiến độ lên web (tpl_auto)", wn.status == "new" and v19[0] is not None
   and v19[1]["status"] == "running" and any(x.get("tag") == "win2019" and x.get("state") in ("installing", "creating", "working") for x in ta), (v19, ta))
st19 = json.load(open(SF))["awin2019"]
pve_set(lambda d: d["vms"][v19[0]].update(status="stopped"))
hn.poll_once(); wait_idle(hn)
ck("máy mẫu đang cài bị tắt giữa chừng (mất điện …) → bật lại cho cài tiếp", pve()["vms"][v19[0]]["status"] == "running")
cb.AUTO_WAIT_S = 0; cb.RETRY_S = 0
with hn.lock: hn.st["awin2019"]["t_build"] = time.time() - 600
hn.poll_once(); wait_idle(hn)
ck("quá giờ mà Windows chưa cài xong → xoá máy ảo dựng dở", v19[0] not in pve()["vms"], list(pve()["vms"]))
pve_set(lambda d: d.update(isos=[ISO, ISO16]))                  # ISO biến mất khỏi kho nhưng máy chủ còn nhớ danh sách cũ → tạo lại sẽ lỗi
for _ in range(4): hn.poll_once(); wait_idle(hn)
s19 = json.load(open(SF))["awin2019"]
n0 = len(pve()["log"]); hn.poll_once(); wait_idle(hn)
ck("dựng lại vẫn lỗi → sau %d lần thì THÔI (không thử mãi), ghi lỗi để xem" % cb.AUTO_TRIES, s19.get("off") is True and int(s19.get("tries") or 0) == cb.AUTO_TRIES
   and not [x for x in pve()["log"][n0:] if x[0] == "qm" and x[1] == "create"], s19)
cb.AUTO_WAIT_S = 3 * 3600; cb.RETRY_S = 60
hn.iso_list = [{"volid": "local:iso/" + ("x" * 110) + "-%03d.iso" % i, "size": 5 * 2**30} for i in range(120)]; hn.iso_t = time.time()
hn.poll_once()
pm = last_poll(wn)["p_metrics"]
ck("gói số đo gửi web luôn dưới 12 KB (web bỏ cả gói nếu quá 16 KB): danh sách ISO quá dài thì cắt bớt, số đo chính (tpl, ver) vẫn đủ",
   len(json.dumps(pm)) <= 12000 and 0 < len(pm["iso"]) < 120 and "tpl" in pm and pm["ver"] == cb.CBHOST_VER, len(json.dumps(pm)))

print("11. Tự sửa mạng (26/11c): cài lúc mạng không cấp IPv4 → chỉ có IPv6 + DNS 192.168.100.1 → máy tự xin DHCP, tự đặt lại DNS")
IF6 = """# network interface settings; autogenerated
# Please do NOT modify this file directly, unless you know what
# you're doing.

auto lo
iface lo inet loopback

iface nic0 inet6 manual

auto vmbr0
iface vmbr0 inet6 static
\taddress 2001:db8:5:ac60:5054:ff:fe12:3456/64
\tgateway fe80::1
\tbridge-ports nic0
\tbridge-stp off
\tbridge-fd 0

source /etc/network/interfaces.d/*
"""
IF4 = IF6.replace("inet6 manual", "inet manual").replace("iface vmbr0 inet6 static", "iface vmbr0 inet static").replace("2001:db8:5:ac60:5054:ff:fe12:3456/64", "192.168.1.50/24").replace("fe80::1", "192.168.1.1")
netd = os.path.join(tmp, "net"); os.makedirs(netd)
cb.RESOLV_F, cb.IFACES_F, cb.DHCP_UNIT_F, cb.DHCP_WAIT_S = os.path.join(netd, "resolv.conf"), os.path.join(netd, "interfaces"), os.path.join(netd, "cloudblue-dhcp4.service"), 0
NET = {"v4": False, "v6": True, "lease": True, "cmds": [], "have": {"dhclient", "systemctl"}, "dns_ok": False, "active": False}
_run0, _which0, _res0 = cb.run, cb.shutil.which, cb.can_resolve


def fake_run(cmd, timeout=900):
    if cmd[0] == "ip":
        on = NET["v4"] if cmd[1] == "-4" else NET["v6"]
        return 0, ("default via %s dev vmbr0 proto kernel onlink" % ("192.168.1.1" if cmd[1] == "-4" else "fe80::1")) if on else ""
    if cmd[0] == "systemctl":
        NET["cmds"].append(" ".join(cmd))
        if cmd[1] == "is-active": return (0, "active") if NET["active"] else (3, "inactive")
        if cmd[1:3] == ["enable", "--now"]:
            NET["active"] = True
            if NET["lease"]: NET["v4"] = True                       # mạng có DHCP → dhclient lấy được IPv4
        if cmd[1:3] == ["disable", "--now"]: NET["active"] = False
        return 0, ""
    return _run0(cmd, timeout)


def net_reset(ifaces=IF6, resolv="search lan\nnameserver 192.168.100.1\n", **kw):
    for f in os.listdir(netd): os.remove(os.path.join(netd, f))
    open(cb.IFACES_F, "w").write(ifaces); open(cb.RESOLV_F, "w").write(resolv)
    NET.update(v4=False, v6=True, lease=True, cmds=[], have={"dhclient", "systemctl"}, dns_ok=False, active=False); NET.update(kw)


def sysc(pat): return [x for x in NET["cmds"] if re.search(pat, x)]


cb.run = fake_run
cb.shutil.which = lambda n, *a, **k: ("/usr/sbin/" + n) if n in NET["have"] else None
cb.can_resolve = lambda host, secs=8: NET["dns_ok"]
C6 = dict(cb.DEFAULTS, bridge="vmbr0", net_heal=True, sb_url="https://web.cloudblue.thu")
try:
    net_reset()
    ck("đọc đường ra: máy chỉ có IPv6 → (IPv4 không, IPv6 có), ip6_only = True; cấu hình cầu vmbr0: chỉ IPv6", cb.default_routes() == (False, True) and cb.ip6_only() is True and cb.bridge_ipv4("vmbr0") == "v6", cb.default_routes())
    did = cb.net_heal(C6, 1)
    ut = open(cb.DHCP_UNIT_F).read() if os.path.exists(cb.DHCP_UNIT_F) else ""
    ck("máy chỉ có IPv6, mạng CÓ DHCP: bật dịch vụ cloudblue-dhcp4 (dhclient -4 -d … vmbr0, tự chạy lại, tự bật cùng máy) → có IPv4; KHÔNG sửa 1 byte nào của /etc/network/interfaces",
       "ExecStart=/usr/sbin/dhclient -4 -d -pf /run/dhclient.vmbr0.pid -lf /var/lib/dhcp/dhclient.vmbr0.leases vmbr0\n" in ut and "Restart=always" in ut and "WantedBy=multi-user.target" in ut
       and sysc(r"^systemctl daemon-reload$") and sysc(r"^systemctl enable --now cloudblue-dhcp4\.service$") and open(cb.IFACES_F).read() == IF6 and not os.path.exists(cb.IFACES_F + ".cb-goc")
       and any("ĐÃ có IPv4" in x for x in did) and cb.default_routes()[0], (did, ut))
    rs = open(cb.RESOLV_F).read()
    ck("… DNS 192.168.100.1 (bộ cài tự điền) không phân giải được → đặt lại: có IPv4 + IPv6 thì 8.8.8.8, 2001:4860:4860::8888, 1.1.1.1; giữ dòng search; lưu bản gốc",
       cb.resolv_servers(rs) == ["8.8.8.8", "2001:4860:4860::8888", "1.1.1.1"] and "search lan" in rs and "192.168.100.1" not in rs
       and open(cb.RESOLV_F + ".cb-goc").read() == "search lan\nnameserver 192.168.100.1\n" and any("DNS" in x for x in did), (did, rs))
    n_en = len(sysc("enable --now"))
    did2 = cb.net_heal(C6, 2); did3 = cb.net_heal(C6, 5)
    ck("gọi lại nhiều lần: dịch vụ đang chạy thì KHÔNG bật lại, không ghi lại DNS, bản gốc không bị đè",
       did2 == [] and did3 == [] and len(sysc("enable --now")) == n_en and open(cb.RESOLV_F).read() == rs and open(cb.DHCP_UNIT_F).read() == ut, (did2, did3))
    net_reset(lease=False)
    did = cb.net_heal(C6, 1)
    rs = open(cb.RESOLV_F).read()
    ck("máy chỉ có IPv6, mạng KHÔNG có DHCP: vẫn bật dịch vụ (dhclient tự thử lại mãi) và đặt DNS IPv6 công cộng (2001:4860:4860::8888, 2606:4700:4700::1111) → chạy được chỉ bằng IPv6",
       os.path.exists(cb.DHCP_UNIT_F) and any("mạng chưa cấp IPv4" in x for x in did) and cb.resolv_servers(rs) == ["2001:4860:4860::8888", "2606:4700:4700::1111"] and len(did) == 2, (did, rs))
    n_en = len(sysc("enable --now"))
    ck("… lượt sau: dịch vụ vẫn đang chạy → không bật lại, không ghi gì thêm", cb.net_heal(C6, 2) == [] and len(sysc("enable --now")) == n_en)
    NET["active"] = False
    ck("… dịch vụ bị tắt (ai đó dừng) → lượt sau bật lại", any("cloudblue-dhcp4" in x for x in cb.net_heal(C6, 3)) and len(sysc("enable --now")) == n_en + 1)
    open(cb.IFACES_F, "w").write(IF4); NET.update(v4=True, dns_ok=True)
    did = cb.net_heal(C6, 4)
    ck("admin đã đặt IPv4 tĩnh cho vmbr0 (trang Proxmox) → gỡ dịch vụ xin DHCP tạm: disable --now + xoá file dịch vụ", len(did) == 1 and "gỡ dịch vụ" in did[0] and sysc(r"disable --now cloudblue-dhcp4\.service")
       and not os.path.exists(cb.DHCP_UNIT_F), did)
    net_reset(ifaces=IF4, v4=True, v6=False, resolv="nameserver 192.168.1.1\n")
    did = cb.net_heal(C6, 1)
    ck("máy cài bình thường (IPv4 tĩnh, DNS của mạng): mất mạng tạm thời → KHÔNG đụng gì ở lượt đầu (không dịch vụ, không DNS)", did == [] and not os.path.exists(cb.DHCP_UNIT_F) and open(cb.RESOLV_F).read() == "nameserver 192.168.1.1\n"
       and not sysc("enable|disable"), did)
    did = cb.net_heal(C6, 3)
    ck("… hỏng tên miền nhiều lượt liền (lượt 3) → mới đặt DNS công cộng IPv4 (8.8.8.8, 1.1.1.1); bản gốc lưu ở .cb-goc",
       cb.resolv_servers(open(cb.RESOLV_F).read()) == ["8.8.8.8", "1.1.1.1"] and open(cb.RESOLV_F + ".cb-goc").read() == "nameserver 192.168.1.1\n" and not os.path.exists(cb.DHCP_UNIT_F), did)
    net_reset(ifaces=IF4, v4=False, v6=False)
    ck("cầu mạng đã có cấu hình IPv4 (tĩnh) mà không có đường ra nào: không bật DHCP, không ghi DNS (không biết đường nào dùng được)", cb.net_heal(C6, 5) == [] and not os.path.exists(cb.DHCP_UNIT_F)
       and open(cb.RESOLV_F).read() == "search lan\nnameserver 192.168.100.1\n")
    net_reset(have={"systemctl"})
    did = cb.net_heal(C6, 1)
    ck("máy không có dhclient: không bật dịch vụ; vẫn sửa DNS", not os.path.exists(cb.DHCP_UNIT_F) and len(did) == 1 and "DNS" in did[0], did)
    net_reset(ifaces=IF6.replace("vmbr0", "vmbr9"))
    cb.net_heal(C6, 1)
    ck("file mạng không có cầu vmbr0 → không bật dịch vụ nào", not os.path.exists(cb.DHCP_UNIT_F) and not sysc("enable"))
    net_reset(resolv="nameserver 192.168.100.1\n")
    did = cb.net_heal(dict(C6, sb_url="http://10.0.2.2:8765"), 1)
    ck("web gọi bằng địa chỉ số (bộ thử): không cần tên miền → không đụng DNS, vẫn xin DHCP", open(cb.RESOLV_F).read() == "nameserver 192.168.100.1\n" and len(did) == 1 and "cloudblue-dhcp4" in did[0], did)
    net_reset(dns_ok=True, v4=True)
    ck("mạng đủ cả (có IPv4, phân giải được): không làm gì", cb.net_heal(C6, 9) == [] and open(cb.IFACES_F).read() == IF6 and not os.path.exists(cb.DHCP_UNIT_F))
    # NetWatch: khi nào thì gọi tự sửa
    T = [1000.0]; calls = []
    nw = cb.NetWatch(C6, heal=lambda c, n: calls.append(n) or ["x%d" % n], now=lambda: T[0])
    r = [nw.step(False, "<urlopen error [Errno -3] Temporary failure in name resolution>") for _ in range(2)]
    ck("2 vòng lỗi mạng đầu: chưa sửa", r == [[], []] and calls == [])
    r3 = nw.step(False, "<urlopen error [Errno 101] Network is unreachable>")
    ck("vòng lỗi mạng thứ 3 liền (≈ 30 giây): chạy tự sửa lượt 1", r3 == ["x1"] and calls == [1], (r3, calls))
    T[0] += 30; r4 = nw.step(False, "timed out")
    ck("chưa đủ 2 phút: không sửa lại", r4 == [] and calls == [1])
    T[0] += 100; r5 = nw.step(False, "timed out")
    ck("sau 2 phút vẫn lỗi: lượt 2", r5 == ["x2"] and calls == [1, 2])
    T[0] += 500
    ck("web TRẢ LỜI nhưng báo lỗi (HTTP 500 / web từ chối): không tính là lỗi mạng, không sửa", nw.step(False, "HTTP 500: x") == [] and nw.step(False, "") == [] and nw.step(None, "boom") == [] and calls == [1, 2])
    ck("gọi web được → đếm lại từ đầu (phải 3 vòng lỗi liền mới sửa tiếp)", nw.step(True, "") == [] and nw.fails == 0 and nw.step(False, "timed out") == [] and nw.step(False, "timed out") == [] and calls == [1, 2])
    nw.step(False, "timed out")                                      # đủ 3 vòng lỗi liền
    for _ in range(8):
        T[0] += 121; nw.step(False, "timed out")
    n10 = len(calls); T[0] += 121; r_a = nw.step(False, "timed out"); T[0] += 780; r_b = nw.step(False, "timed out")
    ck("10 lượt đầu cách nhau 2 phút; sau đó giãn ra 15 phút / lượt", n10 == 10 and r_a == [] and r_b == ["x11"] and calls[-1] == 11, (n10, calls[-3:], r_a, r_b))
    off = cb.NetWatch(dict(C6, net_heal=False), heal=lambda c, n: calls.append("off") or ["?"], now=lambda: T[0])
    ck("tắt tự sửa mạng (net_heal: false) → không bao giờ gọi", [off.step(False, "timed out") for _ in range(9)] == [[]] * 9 and "off" not in calls)
    open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"auto_tpl": True}))
    c1 = cb.conf()
    open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
    c2 = cb.conf()
    open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"auto_tpl": True, "net_heal": False}))
    c3 = cb.conf()
    ck("mặc định: máy cài bằng ISO CloudBlue-Proxmox (auto_tpl) thì BẬT tự sửa mạng; máy cài tay (cai-cbhost.sh) thì tắt; đặt net_heal: false thì tắt",
       c1["net_heal"] is True and c2["net_heal"] is False and c3["net_heal"] is False, (c1["net_heal"], c2["net_heal"], c3["net_heal"]))
    open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
    net_reset(lease=False)
    rep1 = cb.net_report(C6)
    ck("lệnh status / net in rõ tình trạng mạng (IPv4 KHÔNG · IPv6 có · DNS · phân giải KHÔNG ĐƯỢC)", "IPv4 KHÔNG" in rep1 and "IPv6 có" in rep1 and "192.168.100.1" in rep1 and "KHÔNG ĐƯỢC" in rep1 and "tự sửa mạng: bật" in rep1, rep1)
    said = []; T2 = [5000.0]
    class H0:                                                       # máy chủ tối thiểu cho Screen
        name, status = "cbvps-3456", "new"
        class web: err = "<urlopen error [Errno -3] Temporary failure in name resolution>"
    scr = cb.Screen(C6, say=said.append, now=lambda: T2[0], report=lambda c: "mạng: IPv4 KHÔNG · IPv6 có")
    scr.step(False, H0); scr.step(False, H0)
    n2 = len(said); scr.step(False, H0)
    ck("màn hình máy chủ: 3 vòng không gọi được web → in 1 dòng 'CHUA goi duoc web …' kèm lỗi + tình trạng mạng (để người ở chỗ máy chỉ cần chụp màn hình)",
       n2 == 0 and len(said) == 1 and said[0].startswith("CHUA goi duoc web CloudBlue (") and "name resolution" in said[0] and "IPv4" in said[0], said)
    for _ in range(20): scr.step(False, H0)
    T2[0] += 301; scr.step(False, H0)
    ck("… vẫn chưa được: 5 phút mới nhắc lại 1 lần (không tràn màn hình)", len(said) == 2, len(said))
    scr.healed(1, "bật dịch vụ xin IPv4 qua DHCP cho vmbr0")
    scr.step(True, H0); scr.step(True, H0)
    ck("… lên web được → in ĐÚNG 1 lần 'DA LEN WEB: may chu cbvps-3456 - CHO DUYET …'; dòng tự sửa mạng cũng in ra", len(said) == 4 and "tu sua mang (luot 1)" in said[2]
       and said[3].startswith("DA LEN WEB: may chu 'cbvps-3456' - CHO DUYET") and "bam DUYET" in said[3], said[2:])
    off2 = cb.Screen(dict(C6, net_heal=False), say=said.append)
    for _ in range(5): off2.step(False, H0)
    off2.step(True, H0)
    ck("máy cài tay (không phải ISO CloudBlue-Proxmox): không in gì ra màn hình", len(said) == 4)
    ttyf = os.path.join(netd, "tty"); cb.TTY_F = ttyf
    cb.tty_say("Chưa gọi được web — đang thử lại, máy chủ tên: đặt lại")
    tt = open(ttyf, "rb").read()
    ck("chữ in ra màn hình là chữ KHÔNG DẤU thuần ASCII, có giờ, xuống dòng kiểu màn hình chữ", tt.startswith(b"\r\n[CloudBlue ") and b"Chua goi duoc web" in tt and b"may chu ten: dat lai" in tt and all(c < 128 for c in tt), tt)
    cb.TTY_F = "/khong/co/tty"; cb.tty_say("x")
    ck("máy không có màn hình (không ghi được tty): bỏ qua, không lỗi", True)
    ck("web_host / is_ip: tên miền, địa chỉ IPv4, IPv6 trong ngoặc", cb.web_host(C6) == "web.cloudblue.thu" and cb.is_ip("10.0.2.2") and cb.is_ip(cb.web_host({"sb_url": "http://[fec0::2]:8765"})) and not cb.is_ip("a.b"))
finally:
    cb.run, cb.shutil.which, cb.can_resolve = _run0, _which0, _res0

print("12. USB có ISO máy mẫu cắm vào máy chủ ĐANG CHẠY (26/11d): ISO cài đặt ghép thiếu máy mẫu → không phải cài lại máy chủ")
import base64 as _b64, shutil as _sh, subprocess as _sp
spec2 = importlib.util.spec_from_file_location("pve_iso", os.path.join(ROOT, "vm", "pve_iso.py"))
pi = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pi)
usbd = os.path.join(tmp, "usb"); os.makedirs(usbd)
cb.USB_MNT, cb.ISO_DIR, cb.NAP_PY = os.path.join(usbd, "mnt"), os.path.join(usbd, "kho-iso"), os.path.join(ROOT, "vm", "cb_nap.py")
cb.NAP_CONF_F, cb.NAP_DONE_F, cb.MAU_MIN = os.path.join(usbd, "nap.json"), os.path.join(usbd, "nap-xong.json"), 1000
MP = os.path.join(cb.USB_MNT, "m")
KID, KOFF = "0123456789abcdef01234567", 1024 * 1024
F1, F2 = os.urandom(70000), os.urandom(123457)


def kho_img(path, kid=KID, hong=False):
    """Ảnh USB giả: [vùng ISO 1 MiB][đầu mục kho 16 KiB][file 1][file 2] — đúng khuôn pve_iso.build ghi."""
    files, pos = [], KOFF + cb.KHO_HDR
    for nm, dat in (("CloudBlue-MayMau-win2012r2.iso", F1), ("CloudBlue-MayMau-win2016.iso", F2)):
        files.append({"name": nm, "off": pos, "size": len(dat), "sha256": hashlib.sha256(dat).hexdigest()}); pos += len(dat)
    hdr = cb.KHO_MAGIC + json.dumps({"v": 1, "id": kid, "size": pos, "files": files}, sort_keys=True).encode() + b"\n"
    with open(path, "wb") as o:
        o.write(b"\0" * KOFF); o.write(hdr.ljust(cb.KHO_HDR, b"\0")); o.write(F1); o.write(F2 if not hong else F2[:-5] + b"hongg")
    return {"id": kid, "off": KOFF, "size": pos, "n": 2}


def fb_text(nap_conf):
    tmpl = open(os.path.join(ROOT, "vm", "pve_firstboot.sh"), encoding="utf-8").read()
    return pi.first_boot(tmpl, b"print('cbhost')\n" * 50, b"print('nap')\n" * 20, {"auto_tpl": True}, nap_conf)


IMG = os.path.join(usbd, "usb.img"); KC = kho_img(IMG)
os.makedirs(MP)
open(os.path.join(MP, "proxmox-first-boot"), "wb").write(fb_text(KC))
ck("đọc cấu hình kho ISO máy mẫu từ file proxmox-first-boot THẬT của USB cài đặt (do pve_iso ghép): đúng mã kho, vị trí, số file", cb.usb_kho_conf(MP) == KC, cb.usb_kho_conf(MP))
open(os.path.join(MP, "proxmox-first-boot"), "wb").write(fb_text({"id": KID, "off": 0, "size": 12345, "n": 0}))
ck("USB cài đặt KHÔNG kèm máy mẫu (như USB ghép lúc 12:20 ngày 26/11) → không có kho", cb.usb_kho_conf(MP) is None)
os.remove(os.path.join(MP, "proxmox-first-boot"))
ck("USB không phải USB cài đặt CloudBlue (không có file proxmox-first-boot) → bỏ qua", cb.usb_kho_conf(MP) is None)
kf = cb.kho_files(IMG, KC)
ck("đầu mục kho trên thiết bị: 2 file đúng tên + cỡ; sai mã kho / sai vị trí → không nhận", kf == [{"name": "CloudBlue-MayMau-win2012r2.iso", "size": len(F1)}, {"name": "CloudBlue-MayMau-win2016.iso", "size": len(F2)}]
   and cb.kho_files(IMG, dict(KC, id="f" * 24)) is None and cb.kho_files(IMG, dict(KC, off=KOFF + 2048)) is None and cb.kho_files("/khong/co", KC) is None, kf)

LS = {"blockdevices": [
    {"name": "sda", "type": "disk", "fstype": None, "mountpoint": None, "path": "/dev/sda", "tran": "sata", "rm": False, "size": 480103981056,
     "children": [{"name": "sda3", "type": "part", "fstype": "LVM2_member", "mountpoint": None, "path": "/dev/sda3", "tran": None, "rm": False, "size": 479000000000}]},
    {"name": "sdb", "type": "disk", "fstype": "iso9660", "mountpoint": None, "path": "/dev/sdb", "tran": "usb", "rm": True, "size": 61530439680,
     "children": [{"name": "sdb1", "type": "part", "fstype": "iso9660", "mountpoint": None, "path": "/dev/sdb1", "tran": None, "rm": True, "size": 1814000000},
                  {"name": "sdb2", "type": "part", "fstype": "vfat", "mountpoint": None, "path": "/dev/sdb2", "tran": None, "rm": True, "size": 8388608}]},
    {"name": "sdc", "type": "disk", "fstype": None, "mountpoint": None, "path": "/dev/sdc", "tran": "usb", "rm": True, "size": 32000000000,
     "children": [{"name": "sdc1", "type": "part", "fstype": "exfat", "mountpoint": "/mnt/dang-dung", "path": "/dev/sdc1", "tran": None, "rm": True, "size": 31999000000}]},
    {"name": "sdd", "type": "disk", "fstype": None, "mountpoint": None, "path": "/dev/sdd", "tran": "usb", "rm": False, "size": 1000204886016,
     "children": [{"name": "sdd1", "type": "part", "fstype": "zfs_member", "mountpoint": None, "path": "/dev/sdd1", "tran": None, "rm": False, "size": 1000000000000}]},
    {"name": "sde", "type": "disk", "fstype": None, "mountpoint": None, "path": "/dev/sde", "tran": "usb", "rm": True, "size": 64000000000,
     "children": [{"name": "sde1", "type": "part", "fstype": "ntfs", "mountpoint": None, "path": "/dev/sde1", "tran": None, "rm": True, "size": 63999000000}]},
    {"name": "sr0", "type": "rom", "fstype": None, "mountpoint": None, "path": "/dev/sr0", "tran": "sata", "rm": True, "size": 1073741312}]}
_run12, U = cb.run, {"ls": LS, "cmds": [], "mounts": {}, "active": False}


def run12(cmd, timeout=900):
    U["cmds"].append(list(cmd))
    if cmd[0] == "lsblk": return 0, json.dumps(U["ls"])
    if cmd[0] == "mount":                                         # mount -t <kiểu> -o <tuỳ chọn> <thiết bị> <chỗ gắn>: "gắn" = chép nội dung giả vào chỗ gắn
        src = U["mounts"].get(cmd[5])
        if src is None: return 32, "wrong fs type"
        _sh.rmtree(cmd[6], ignore_errors=True); _sh.copytree(src, cmd[6]); return 0, ""
    if cmd[0] == "umount":
        _sh.rmtree(cmd[1], ignore_errors=True); return 0, ""
    if cmd[:2] == ["systemctl", "is-active"]: return (0 if U["active"] else 3), ""
    return _run12(cmd, timeout)


cb.run = run12
try:
    dk = cb.usb_disks()
    ck("chỉ nhận ổ USB / ổ tháo rời CHƯA gắn phần nào: bỏ ổ hệ thống (LVM), USB đang gắn, ổ ZFS, ổ đĩa quang", [d["path"] for d in dk] == ["/dev/sdb", "/dev/sde"]
       and dk[0]["nodes"] == [("/dev/sdb", "iso9660"), ("/dev/sdb1", "iso9660"), ("/dev/sdb2", "vfat")], dk)
    # ---- (1) USB cài đặt bản đủ (ghi DD) cắm vào máy đã cài bằng USB bản THIẾU máy mẫu
    isod = os.path.join(usbd, "noi-dung-iso"); os.makedirs(isod)
    open(os.path.join(isod, "proxmox-first-boot"), "wb").write(fb_text(KC))
    U["mounts"] = {"/dev/sdb": isod}
    json.dump({"id": "a" * 24, "off": 0, "size": 1, "n": 0}, open(cb.NAP_CONF_F, "w"))           # máy này cài từ USB không kèm kho
    json.dump({"note": "không có kho"}, open(cb.NAP_DONE_F, "w"))
    said12 = []
    un = cb.UsbNap({"auto_tpl": True}, say=said12.append)
    D_KHO = {"path": IMG, "size": os.path.getsize(IMG), "nodes": [("/dev/sdb", "iso9660"), ("/dev/sdb1", "iso9660")]}
    r = un.one(D_KHO)
    got = {n: open(os.path.join(cb.ISO_DIR, n), "rb").read() for n in sorted(os.listdir(cb.ISO_DIR))} if os.path.isdir(cb.ISO_DIR) else {}
    ck("USB cài đặt bản ĐỦ cắm vào máy ĐANG CHẠY (máy cài từ USB thiếu máy mẫu): tự chép 2 ISO vào kho ISO bằng cb_nap THẬT, nội dung khớp từng byte, không sót file .part",
       r is True and got == {"CloudBlue-MayMau-win2012r2.iso": F1, "CloudBlue-MayMau-win2016.iso": F2}, (r, list(got), un.state))
    ck("báo ra màn hình máy chủ + trạng thái gửi web: 'đang chép … ĐỪNG rút USB' rồi 'đã chép xong 2 ISO … có thể rút USB'", len(said12) == 2 and "dang chep" not in said12[0]
       and said12[0].startswith("USB: thấy 2 ISO máy mẫu") and "ĐỪNG rút USB" in said12[0] and "đã chép xong 2 ISO máy mẫu" in said12[1] and un.state.get("s") == "done", said12)
    ck("gắn USB CHỈ ĐỌC (ro, nosuid, nodev, noexec) và gỡ gắn ngay sau khi đọc cấu hình", any(c[:5] == ["mount", "-t", "iso9660", "-o", "ro,nosuid,nodev,noexec"] for c in U["cmds"])
       and any(c[0] == "umount" for c in U["cmds"]) and not os.path.exists(MP))
    n0 = len(said12); r2 = un.one(D_KHO)
    ck("xem lại USB đó lần nữa: kho ISO đã đủ → không chép lại, không báo gì thêm", r2 is True and len(said12) == n0)
    # USB của CHÍNH lần cài này, dịch vụ cloudblue-nap chưa xong → để dịch vụ đó chép (tránh 2 bên cùng ghi)
    _sh.rmtree(cb.ISO_DIR); json.dump(KC, open(cb.NAP_CONF_F, "w")); os.remove(cb.NAP_DONE_F)
    r3 = un.one(D_KHO)
    ck("USB của chính lần cài này mà dịch vụ cloudblue-nap chưa xong: cbhost KHÔNG chép (dịch vụ nạp lo) → không có 2 bên cùng ghi 1 file", r3 is None and not os.path.isdir(cb.ISO_DIR) and len(said12) == n0, (r3, said12[n0:]))
    json.dump({"note": "đủ"}, open(cb.NAP_DONE_F, "w"))
    r4 = un.one(D_KHO)
    ck("… dịch vụ nạp đã xong mà kho ISO thiếu file (bị xoá tay) → cbhost chép bù", r4 is True and sorted(os.listdir(cb.ISO_DIR)) == ["CloudBlue-MayMau-win2012r2.iso", "CloudBlue-MayMau-win2016.iso"], r4)
    # USB ghi lỗi (mã kiểm không khớp)
    _sh.rmtree(cb.ISO_DIR); json.dump({"id": "a" * 24, "off": 0, "size": 1, "n": 0}, open(cb.NAP_CONF_F, "w"))
    IMG2 = os.path.join(usbd, "usb-hong.img"); kho_img(IMG2, hong=True); n0 = len(said12)
    r5 = un.one(dict(D_KHO, path=IMG2, size=os.path.getsize(IMG2)))
    ls5 = sorted(os.listdir(cb.ISO_DIR))
    ck("USB ghi lỗi (1 file sai mã kiểm SHA-256): file tốt vẫn vào kho, file hỏng KHÔNG vào kho (không sót .part), báo 'CHƯA được … thử lại'", r5 is False and ls5 == ["CloudBlue-MayMau-win2012r2.iso"]
       and un.state.get("s") == "err" and "CHƯA được" in said12[-1], (r5, ls5, said12[n0:]))
    IMG3 = os.path.join(usbd, "usb-cut.img"); open(IMG3, "wb").write(open(IMG, "rb").read()[:KOFF + 100])
    r6 = un.one(dict(D_KHO, path=IMG3, size=os.path.getsize(IMG3)))
    ck("USB ghi dở (không có đầu mục kho ở vị trí ghi trong cấu hình): báo 'không đọc được kho … ghi lại USB', không chép gì", r6 is False and "không đọc được kho" in said12[-1], said12[-1])
    # ---- (2) USB thường chứa file CloudBlue-MayMau-*.iso
    _sh.rmtree(cb.ISO_DIR, ignore_errors=True)
    thuong = os.path.join(usbd, "usb-thuong"); os.makedirs(os.path.join(thuong, "iso", "sau", "qua-sau")); os.makedirs(os.path.join(thuong, "System Volume Information"))
    open(os.path.join(thuong, "CloudBlue-MayMau-win2016.iso"), "wb").write(F2)
    open(os.path.join(thuong, "iso", "CloudBlue-MayMau-win2012r2.iso"), "wb").write(F1)
    open(os.path.join(thuong, "iso", "sau", "qua-sau", "CloudBlue-MayMau-win2019.iso"), "wb").write(F1)       # sâu 3 cấp → không tìm tới
    open(os.path.join(thuong, "System Volume Information", "CloudBlue-MayMau-win2022.iso"), "wb").write(F1)
    open(os.path.join(thuong, "CloudBlue-MayMau-nho.iso"), "wb").write(b"x" * 10)                              # quá nhỏ
    open(os.path.join(thuong, "windows.iso"), "wb").write(F1)                                                   # không đúng tên
    U["mounts"] = {"/dev/sde1": thuong}; U["cmds"] = []; n0 = len(said12)
    D_TH = {"path": "/dev/sde", "size": 64000000000, "nodes": [("/dev/sde", ""), ("/dev/sde1", "ntfs")]}
    r7 = un.one(D_TH)
    ls7 = sorted(os.listdir(cb.ISO_DIR))
    ck("USB THƯỜNG (NTFS) có file CloudBlue-MayMau-*.iso ở thư mục gốc / sâu ≤ 2 cấp: gặp file quá nhỏ thì dừng báo lỗi, các file trước đó đã vào kho",
       r7 is False and "CloudBlue-MayMau-nho.iso" not in ls7 and "quá nhỏ" in said12[-1] and any(c[:3] == ["mount", "-t", "ntfs3"] for c in U["cmds"]), (r7, ls7, said12[n0:]))
    os.remove(os.path.join(thuong, "CloudBlue-MayMau-nho.iso")); n0 = len(said12)
    r8 = un.one(D_TH)
    got8 = {n: open(os.path.join(cb.ISO_DIR, n), "rb").read() for n in sorted(os.listdir(cb.ISO_DIR))}
    ck("… bỏ file hỏng đi: chép đủ 2 file đúng tên (bỏ file sâu 3 cấp, thư mục hệ thống, file sai tên), khớp từng byte, quyền 644, báo 'đã chép xong'",
       r8 is True and got8 == {"CloudBlue-MayMau-win2012r2.iso": F1, "CloudBlue-MayMau-win2016.iso": F2} and "đã chép xong" in said12[-1]
       and stat.S_IMODE(os.stat(os.path.join(cb.ISO_DIR, "CloudBlue-MayMau-win2016.iso")).st_mode) == 0o644, (r8, list(got8), said12[n0:]))
    n0 = len(said12); r9 = un.one(D_TH)
    ck("cắm lại USB thường đó: file đã có đủ (cùng tên, cùng cỡ) → không chép lại", r9 is True and len(said12) == n0)
    os.remove(os.path.join(cb.ISO_DIR, "CloudBlue-MayMau-win2016.iso")); open(os.path.join(cb.ISO_DIR, "CloudBlue-MayMau-win2016.iso.part"), "wb").write(b"dang ghi")
    r10 = un.one(D_TH)
    ck("file .part của đúng ISO đó vừa được ghi (bên khác đang chép) → không đụng vào, 1 phút sau xem lại", r10 is False and open(os.path.join(cb.ISO_DIR, "CloudBlue-MayMau-win2016.iso.part"), "rb").read() == b"dang ghi")
    os.remove(os.path.join(cb.ISO_DIR, "CloudBlue-MayMau-win2016.iso.part"))
    r11 = un.one({"path": "/dev/sdf", "size": 1, "nodes": [("/dev/sdf", ""), ("/dev/sdf1", "exfat")]})
    ck("USB không gắn được / không có ISO máy mẫu → bỏ qua êm (không báo gì)", r11 is None)
    # ---- vòng quét: nhớ USB đã xem, rút ra cắm lại thì xem ngay
    calls = []
    un2 = cb.UsbNap({"auto_tpl": True}, say=lambda m: None); un2.one = lambda d: (calls.append(d["path"]), True)[1]
    U["ls"] = {"blockdevices": [LS["blockdevices"][4]]}
    un2.step(); un2.step()
    ck("vòng quét 20 giây: USB đã xem xong thì 10 phút sau mới xem lại (không đọc USB liên tục)", calls == ["/dev/sde"], calls)
    U["ls"] = {"blockdevices": []}; un2.step(); U["ls"] = {"blockdevices": [LS["blockdevices"][4]]}; un2.step()
    ck("rút USB ra rồi cắm lại → xem lại NGAY", calls == ["/dev/sde", "/dev/sde"], calls)
    un2.one = lambda d: (calls.append("loi"), False)[1]; un2.seen = {}
    un2.step(); k2 = list(un2.seen.values())[0] - time.time()
    ck("lượt chép lỗi → 1 phút sau thử lại (không chờ 10 phút)", 50 < k2 <= 60, k2)
    # ---- gói số đo gửi web + tự cập nhật
    H12 = cb.Host(); H12.usb = un
    un.state = {"s": "copy", "msg": "đang chép", "t": 1}
    os.environ["INVOCATION_ID"] = "x"; H12.c["auto_update"] = True
    ck("đang chép ISO từ USB thì KHÔNG tự cập nhật cbhost (không cắt ngang việc chép); chép xong mới cập nhật", not cb.update_due(H12, time.time(), 0)
       and bool(cb.update_due(dict(), 0, 0) if False else True) and (un.state.update(s="done") or cb.update_due(H12, time.time(), 0)))
    os.environ.pop("INVOCATION_ID", None)
    said13 = []; cb.TTY_F = os.path.join(usbd, "tty")
    cb.tty_say("mạng: IPv4 có · IPv6 không — vào Quản trị › VPS ảo hoá → bấm DUYỆT…")
    tt = open(cb.TTY_F, "rb").read().decode("ascii")
    ck("chữ ra màn hình máy chủ: dấu ngăn tiếng Việt (· — › → …) đổi sang ASCII, không còn ra dấu '?' như ảnh chụp máy thật", "IPv4 co | IPv6 khong - vao Quan tri > VPS ao hoa -> bam DUYET..." in tt and "?" not in tt, tt)
finally:
    cb.run = _run12

print("13. Đổi cấu hình (26/11e · web v59: khách nâng cấp / admin sửa) + nới ổ C trong Windows")
pve_set(lambda d: (d.__setitem__("guest_after", 1), d.__setitem__("grow_ok", True)))
os.environ.pop("INVOCATION_ID", None)
for k in list(pve()["vms"]):
    if k.startswith("1000"): pve_set(lambda d, k=k: d["vms"].pop(k, None))
try: os.remove(os.environ["CBHOST_STATE"])
except OSError: pass
cb.GROW_EVERY_S = 0
w13 = FakeWeb(); w13.status = "ready"; h13 = cb.Host(web=w13); h13.hello_ok = True; h13.status = "ready"
H50 = hashlib.sha256(b"50").hexdigest()
it50 = lambda **kw: item(**{"id": 50, "hw": H50, "disk_gb": 20, "cores": 2, "ram_mb": 2048, "cfg": 0, **kw})
w13.vps = [it50()]; h13.want = w13.vps; sync(h13, 2)
v = pve()["vms"]["100050"]
ck("VPS mới cấu hình 2 vCPU · 2 GB · ổ 20 GB (nhỏ hơn máy mẫu 32 GB → giữ 32), chạy; báo 'cfg' 0 cho web", v["status"] == "running" and v["cfg"].get("cores") == "2"
   and (rep_of(w13, 50) or {}).get("cfg") == 0 and not json.load(open(os.environ["CBHOST_STATE"]))["50"].get("grow"), (v, rep_of(w13, 50)))
w13.vps = [it50(enrolled=True)]; sync(h13, 2); n_sd = len(qmlog(r"^qm shutdown 100050")); b0 = pve()["vms"]["100050"].get("boots", 0)
w13.vps = [it50(enrolled=True, cores=4, ram_mb=4096, disk_gb=60, cfg=1)]
h13.poll_once(); h13.poll_once(); r1 = rep_of(w13, 50); wait_idle(h13)          # vòng 1 nhận danh sách mới, vòng 2 bắt đầu làm
v = pve()["vms"]["100050"]
ck("web đổi cấu hình lần 1 → 4 vCPU · 4 GB · 60 GB: lúc đang làm vẫn báo máy 'running' (không phải 'đang tạo'), CHƯA báo cfg 1",
   r1 and r1["state"] == "running" and r1.get("cfg") is None, r1)
ck("… đặt vCPU / RAM, nới ổ Proxmox 32 → 60 GB, máy đang chạy → TẮT HẲN rồi bật lại (1 lần) để nhận vCPU / RAM mới; không cài lại, không xoá (dữ liệu giữ)",
   v["cfg"].get("cores") == "4" and v["cfg"].get("memory") == "4096" and not v.get("pending") and v["disks"]["scsi0"] == 60 and v["status"] == "running"
   and len(qmlog(r"^qm shutdown 100050")) == n_sd + 1 and v.get("boots", 0) == b0 + 1 and len(qmlog(r"^qm clone \d+ 100050")) == 1, v)
h13.poll_once(); wait_idle(h13); h13.poll_once(); wait_idle(h13); h13.poll_once()
v = pve()["vms"]["100050"]; ps = [x for x in v.get("execs", []) if x and x[0] == "powershell"]
ck("… Windows lên → chạy lệnh CỐ ĐỊNH nới ổ C (Resize-Partition lên cỡ tối đa) qua guest agent; ổ C = 59 GB → xong, báo web cfg 1",
   ps and "Resize-Partition -DriveLetter C" in ps[-1][1] and v.get("part_gb") == 59 and (rep_of(w13, 50) or {}).get("cfg") == 1
   and not json.load(open(os.environ["CBHOST_STATE"]))["50"].get("grow"), (rep_of(w13, 50), v.get("part_gb"), len(ps)))
n_sd = len(qmlog(r"^qm shutdown 100050")); n_rs = len(qmlog(r"^qm resize 100050"))
sync(h13, 3)
ck("vòng sau không làm lại gì (không tắt / nới thêm)", len(qmlog(r"^qm shutdown 100050")) == n_sd and len(qmlog(r"^qm resize 100050")) == n_rs)
w13.vps = [it50(enrolled=True, cores=4, ram_mb=4096, disk_gb=100, cfg=2)]; sync(h13, 4)
v = pve()["vms"]["100050"]
ck("chỉ thêm ổ (60 → 100 GB): nới ổ Proxmox + ổ C, KHÔNG tắt máy; báo cfg 2", v["disks"]["scsi0"] == 100 and v.get("part_gb") == 99 and len(qmlog(r"^qm shutdown 100050")) == n_sd
   and (rep_of(w13, 50) or {}).get("cfg") == 2, (v, rep_of(w13, 50)))
w13.vps = [it50(enrolled=True, cores=4, ram_mb=4096, disk_gb=50, cfg=3)]; sync(h13, 3)
ck("web lỡ gửi ổ NHỎ hơn (50 < 100 GB) → không bao giờ thu nhỏ ổ (mất dữ liệu)", pve()["vms"]["100050"]["disks"]["scsi0"] == 100 and (rep_of(w13, 50) or {}).get("cfg") == 3)
w13.vps = [it50(enrolled=True, want="stopped", cores=4, ram_mb=4096, disk_gb=100, cfg=3)]; sync(h13, 2)
n_st = len(qmlog(r"^qm start 100050"))
w13.vps = [it50(enrolled=True, want="stopped", cores=6, ram_mb=8192, disk_gb=100, cfg=4)]; sync(h13, 3)
v = pve()["vms"]["100050"]
ck("máy đang TẮT (khách tắt): đặt cấu hình mới, KHÔNG tự bật máy lên; báo cfg 4", v["status"] == "stopped" and v["cfg"].get("cores") == "6" and len(qmlog(r"^qm start 100050")) == n_st
   and (rep_of(w13, 50) or {}).get("cfg") == 4, (v["status"], v["cfg"], rep_of(w13, 50)))
w13.vps = [it50(enrolled=True, cores=6, ram_mb=8192, disk_gb=100, cfg=4)]; sync(h13, 2)
pve_set(lambda d: d.__setitem__("set_fail", True))
w13.vps = [it50(enrolled=True, cores=8, ram_mb=8192, disk_gb=100, cfg=5)]; sync(h13, 3)
r = rep_of(w13, 50)
ck("đặt vCPU lỗi (Proxmox khoá file) → báo lỗi cho web, KHÔNG báo cfg 5 (web còn chờ, quá 15 phút báo admin)", r and r["state"] == "error" and "vCPU" in r.get("err", "") and r.get("cfg") is None, r)
pve_set(lambda d: d.__setitem__("set_fail", False)); time.sleep(0.01)
h13.st["50"]["t_err"] = 0; sync(h13, 3)
ck("… hết lỗi → lần sau tự làm lại được, báo cfg 5", (rep_of(w13, 50) or {}).get("cfg") == 5 and pve()["vms"]["100050"]["cfg"].get("cores") == "8", rep_of(w13, 50))
pve_set(lambda d: d.__setitem__("grow_ok", False)); cb.GROW_TRIES = 2
w13.vps = [it50(enrolled=True, cores=8, ram_mb=8192, disk_gb=120, cfg=6)]; sync(h13, 6)
ck("Windows không nới được ổ C (vd ổ C không nằm cuối ổ) → thử vài lần rồi THÔI, vẫn báo cfg 6 (ổ Proxmox đã đủ, khách tự Extend Volume) — không treo",
   (rep_of(w13, 50) or {}).get("cfg") == 6 and pve()["vms"]["100050"]["disks"]["scsi0"] == 120 and not json.load(open(os.environ["CBHOST_STATE"]))["50"].get("grow"), rep_of(w13, 50))
w13.vps = [it50(enrolled=True, cfg="1; reboot")]; n0 = len(pve()["log"]); sync(h13, 2)
ck("'cfg' lạ từ web (chữ) → bỏ qua cả mục, không gọi qm", not [x for x in pve()["log"][n0:] if x[0] == "qm" and x[1] in ("set", "resize", "shutdown")] and rep_of(w13, 50) is None)
ck("lệnh nới ổ C là lệnh CỐ ĐỊNH trong cbhost.py (không ghép chữ từ web)", "GROW_PS = (" in open(os.path.join(ROOT, "cbhost.py")).read() and "{" not in cb.GROW_ARGS[-1])


print("14. VPS NVMe LINUX (27/11a): tự dựng máy mẫu Ubuntu 24.04 + XFCE + CloudBlue + OpenClaw từ ảnh cloud chính chủ")
import base64 as _b64
IMGD = b"anh-ubuntu-gia" * 1000; IMGSHA = hashlib.sha256(IMGD).hexdigest(); FN = cb.LINUX_TPLS["ubuntu2404"]["file"]
cb.IMG_DIR = os.path.join(tmp, "img"); cb.SNIP_DIR = os.path.join(tmp, "snippets")
got_urls = []
cb.http_get = lambda url, limit=0: (got_urls.append(url), ("%s *%s\nffff *khac.img\n" % (IMGSHA, FN)).encode())[1]
cb.http_save = lambda url, dst: (got_urls.append(url), open(dst, "wb").write(IMGD))
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm", "auto_tpl": True}))
ck("cấu hình: máy cài bằng ISO (auto_tpl) mặc định tự dựng tpl-ubuntu2404; máy cài tay thì không; 'linux_tpl': [] tắt; tên lạ bỏ qua",
   cb.conf()["linux_tpl"] == ["ubuntu2404"] and (open(os.environ["CBHOST_CONF"], "w").write(json.dumps({})) and cb.conf()["linux_tpl"] == [])
   and (open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"auto_tpl": True, "linux_tpl": ["x; rm", "ubuntu2404"]})) and cb.conf()["linux_tpl"] == ["ubuntu2404"]))
hw_ = cb.Host.__new__(cb.Host); hw_.tpl_need = ["tpl-win2016", "tpl-ubuntu2404"]
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({})); hw_.c = cb.conf(); a1 = hw_.linux_tags()
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"linux_tpl": []})); hw_.c = cb.conf(); a2 = hw_.linux_tags()
hw_.tpl_need = ["tpl-win2016"]; open(os.environ["CBHOST_CONF"], "w").write(json.dumps({})); hw_.c = cb.conf(); a3 = hw_.linux_tags()
ck("27/11b: máy cài TAY + web đang bán bản Ubuntu (tpl-ubuntu2404) → tự dựng; ghi rõ 'linux_tpl': [] → không; web không bán → không",
   a1 == ["ubuntu2404"] and a2 == [] and a3 == [], (a1, a2, a3))
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm", "auto_tpl": True}))
try: os.remove(os.environ["CBHOST_STATE"])
except OSError: pass
pve_set(lambda d: d.update(vms={"9000": {"name": "tpl-win10-22h2", "status": "stopped", "template": True, "disks": {"scsi0": 32}}}, isos=[], guest_after=1, log=[]))
cb.AUTO_CHK_S = 0; cb.RETRY_S = 60
w14 = FakeWeb(); w14.status = "ready"; h14 = cb.Host(web=w14)
h14.poll_once(); wait_idle(h14, 30)
v = pve()["vms"].get("99600") or {}; c = v.get("cfg") or {}
sn = open(os.path.join(cb.SNIP_DIR, "cloudblue-ubuntu2404.yaml"), encoding="utf-8").read()
cbj = json.loads(_b64.b64decode(re.search(r"content: (\S+)", sn).group(1)))
ck("tải ảnh Ubuntu chính chủ (cloud-images.ubuntu.com) + kiểm SHA256SUMS rồi mới dùng", got_urls[:2] == [cb.LINUX_TPLS["ubuntu2404"]["base"] + "SHA256SUMS", cb.LINUX_TPLS["ubuntu2404"]["base"] + FN]
   and got_urls[0].startswith("https://cloud-images.ubuntu.com/") and open(os.path.join(cb.IMG_DIR, FN), "rb").read() == IMGD, got_urls)
ck("máy ảo 99600 cbmau-ubuntu2404: Linux (l26) · 4 nhân 4 GB · ổ = ảnh vừa tải (import-from) nới 20 GB · ổ cloud-init + file riêng · đã bật",
   v.get("name") == "cbmau-ubuntu2404" and c.get("ostype") == "l26" and c.get("cores") == "4" and c.get("agent") == "enabled=1" and v["status"] == "running"
   and qmlog(r"^qm set 99600 --scsi0 local-lvm:0,import-from=%s" % re.escape(os.path.join(cb.IMG_DIR, FN))) and qmlog(r"^qm resize 99600 scsi0 20G$")
   and qmlog(r"^qm set 99600 --ide2 local-lvm:cloudinit --boot order=scsi0 --cicustom user=local:snippets/cloudblue-ubuntu2404\.yaml"), (v, pve()["log"][-6:]))
ck("ổ local bật thêm loại snippets (giữ loại cũ) · cloud-init ghi cb.json (web + khoá CÔNG KHAI, chưa có mã đăng ký) rồi chạy linux-vm.sh từ kho CloudBlue",
   pve().get("local_content") == "iso,vztmpl,backup,snippets" and cbj.get("sb_url") == cb.DEFAULTS["sb_url"] and cbj.get("role") == "vm" and cbj.get("user") == "vps"
   and "ticket" not in sn and "enroll" not in sn and cb.LIN_BOOT_URL in sn and sn.startswith("#cloud-config"), (pve().get("local_content"), cbj))
try: bad = None; cb.http_save = lambda url, dst: open(dst, "wb").write(b"anh-bi-sua"); h14.linux_image.__func__(h14, "ubuntu2404") if False else None
except Exception as e: bad = e
os.remove(os.path.join(cb.IMG_DIR, FN))
try: h14.linux_image("ubuntu2404"); bad = None
except Exception as e: bad = str(e)
ck("ảnh tải về SAI mã kiểm → bỏ, không dùng", bad and "SAI mã kiểm" in bad and not os.path.exists(os.path.join(cb.IMG_DIR, FN)), bad)
h14.poll_once(); wait_idle(h14)
ck("chưa xong (chưa có /var/lib/cloudblue/maymau.done) → chờ, báo web 'installing'", any(x.get("tag") == "ubuntu2404" and x.get("state") == "installing" for x in last_poll(w14)["p_metrics"].get("tpl_auto") or []),
   last_poll(w14)["p_metrics"].get("tpl_auto"))
pve_set(lambda d: d["vms"]["99600"].setdefault("files", {}).update({cb.LIN_DONE_F: "ok 27.11a"}))
h14.poll_once(); wait_idle(h14, 30)
v = pve()["vms"]["99600"]; f = v.get("files") or {}
ck("xong → dừng agent (systemctl) · {} vào /opt/cloudblue/identity · seed · rent · tắt cloud-init + xoá machine-id · gỡ ổ cloud-init · thành máy mẫu tpl-ubuntu2404",
   v["name"] == "tpl-ubuntu2404" and v.get("template") and v.get("execs") == [["systemctl", "stop", "cloudblue.service"], ["sh", "-c", cb.LIN_SEAL_SH]]
   and all(f.get("/opt/cloudblue/" + n) == "{}" for n in ("identity.json", "seed.json", "rent.json")) and qmlog(r"^qm set 99600 --delete ide2,cicustom,ipconfig0$")
   and json.load(open(os.environ["CBHOST_STATE"]))["lubuntu2404"].get("done"), (v.get("execs"), f))
w14.vps = [item(id=60, tpl="tpl-ubuntu2404", hw=hashlib.sha256(b"60").hexdigest(), disk_gb=40)]
for _ in range(4): h14.poll_once(); wait_idle(h14, 30)
v60 = pve()["vms"].get("100060") or {}; s60 = json.load(open(os.environ["CBHOST_STATE"])).get("60") or {}
ck("VPS Linux nhân từ tpl-ubuntu2404: vé đăng ký ghi vào /opt/cloudblue/seed.json (không phải đường dẫn Windows)",
   json.loads((v60.get("files") or {}).get("/opt/cloudblue/seed.json") or "{}").get("ticket") == s60.get("ticket") and s60.get("lin") is True, (s60, list((v60.get("files") or {}))))
cb.GROW_EVERY_S = 0; cb.GROW_TRIES = 1
w14.vps = [item(id=60, tpl="tpl-ubuntu2404", hw=hashlib.sha256(b"60").hexdigest(), disk_gb=40, enrolled=True)]
for _ in range(3): h14.poll_once(); wait_idle(h14, 30)
ck("ổ VPS lớn hơn máy mẫu (40 > 20 GB) → nới ổ / trong Linux bằng lệnh cố định growpart + resize2fs (không phải lệnh PowerShell)",
   ["sh", "-c", cb.GROW_LIN_SH] in (pve()["vms"]["100060"].get("execs") or []), pve()["vms"]["100060"].get("execs"))
ck("27/11c: VPS Linux — đặt mạng DHCP không gắn MAC máy mẫu (lệnh cố định NET_LIN_ARGS qua guest agent) trước khi đưa vé",
   cb.NET_LIN_ARGS in (pve()["vms"]["100060"].get("execs") or []) and "macaddress" in cb.NET_LIN_SH and "60-cloudblue.yaml" in cb.LIN_SEAL_SH,
   pve()["vms"]["100060"].get("execs"))
ck("bật máy ảo đang chạy sẵn ('already running') → coi là được, không báo lỗi cho web", h14.pve.start(100060)[0] == 0 and "already running" in h14.pve.start(100060)[1])


print("16. 27/11d · CÁCH LY VPS KHÁCH: không vào được chính máy chủ Proxmox (8006 / SSH), VPS khác, trang quản trị modem / máy trong mạng nhà")
NFTF = os.path.join(tmp, "nft-luat.txt"); fake_nft = os.path.join(tmp, "nft")
open(fake_nft, "w").write("#!%s\nimport os, sys\nd = sys.stdin.read()\nopen(%r, 'a').write(d + '\\n#---\\n')\n"
                          "sys.exit(1 if os.path.exists(%r) else 0)\n" % (sys.executable, NFTF, NFTF + ".loi"))
os.chmod(fake_nft, 0o755); cb.NFT = fake_nft; _gw0 = cb.default_gw; cb.default_gw = lambda: "192.168.1.1"
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
pve_set(lambda d: d.update(vms={"9000": {"name": "tpl-win10-22h2", "status": "stopped", "template": True, "disks": {"scsi0": 32}},
                                 "100071": {"name": "vps-71", "status": "running", "template": False, "disks": {"scsi0": 40}},
                                 "101": {"name": "may-rieng-cua-chu", "status": "running", "template": False, "disks": {"scsi0": 40}}}, isos=[], log=[]))
w16 = FakeWeb(); w16.status = "ready"; h16 = cb.Host(web=w16); h16.poll_once(); wait_idle(h16)
luat = open(NFTF).read() if os.path.exists(NFTF) else ""
ck("đặt bảng nftables bridge cloudblue_vps: card VPS 100071 (tap + fwpr), KHÔNG gồm máy riêng số < vmid_base / máy mẫu",
   "table bridge cloudblue_vps {" in luat and '"tap100071i0"' in luat and '"fwpr100071p0"' in luat and "tap101i0" not in luat and "tap9000" not in luat, luat[-700:])
ck("VPS → CHÍNH máy chủ: chặn hết (hook input) · VPS ↔ VPS chặn · modem 192.168.1.1 chặn cổng quản trị · máy trong mạng nhà chặn SSH/SMB/RDP/WinRM/8006",
   "iifname @vps drop" in luat and "iifname @vps oifname @vps drop" in luat and "ip daddr 192.168.1.1 tcp dport { 22, 23, 80, 443, 8080, 8443 } drop" in luat
   and "tcp dport { 22, 139, 445, 3389, 5985, 5986, 8006 } drop" in luat and "53" not in luat.split("ip daddr 192.168.1.1")[1][:60], luat[-500:])
m16 = last_poll(w16)["p_metrics"]
ck("báo web metrics.vps_fw = {ok: true, n: 1}", m16.get("vps_fw") == {"ok": True, "n": 1}, m16.get("vps_fw"))
n_before = open(NFTF).read().count("#---"); h16.poll_once(); wait_idle(h16)
ck("danh sách VPS không đổi → không đặt lại mỗi 10 giây (chỉ 10 phút / lần)", open(NFTF).read().count("#---") == n_before)
open(NFTF + ".loi", "w").write("x"); pve_set(lambda d: d["vms"].update({"100072": {"name": "vps-72", "status": "running", "template": False, "disks": {"scsi0": 40}}}))
h16.poll_once(); wait_idle(h16); h16.poll_once(); wait_idle(h16)
m16 = last_poll(w16)["p_metrics"]
ck("nft lỗi (vd máy thiếu nftables) → báo web vps_fw.ok = false + lý do, máy chủ vẫn chạy bình thường", (m16.get("vps_fw") or {}).get("ok") is False, m16.get("vps_fw"))
os.remove(NFTF + ".loi"); cb.default_gw = _gw0
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"vps_iso": False})); ck("tắt được: \"vps_iso\": false", cb.conf()["vps_iso"] is False)

print("15. 27/11c · VPS bị huỷ mà máy ảo ĐANG CHẠY → tắt hẳn rồi xoá (Proxmox không xoá máy đang chạy); xoá không làm VPS mới đứng 'Đang tạo'")
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
try: os.remove(os.environ["CBHOST_STATE"])
except OSError: pass
pve_set(lambda d: d.update(vms={"9000": {"name": "tpl-win10-22h2", "status": "stopped", "template": True, "disks": {"scsi0": 32}},
                                 "100061": {"name": "vps-61", "status": "running", "template": False, "disks": {"scsi0": 40}},
                                 "100062": {"name": "vps-62", "status": "running", "template": False, "disks": {"scsi0": 40}}}, isos=[], log=[]))
w15 = FakeWeb(); w15.status = "ready"; h15 = cb.Host(web=w15)
w15.vps = [item(id=61, want="deleted", name="vps-61"), item(id=62, want="deleted", name="vps-62"), item(id=63, name="vps-63")]
sync(h15, 4)
v15 = pve()["vms"]
ck("2 VPS đã huỷ (máy ảo đang chạy) → qm stop rồi qm destroy, không còn trên máy chủ",
   "100061" not in v15 and "100062" not in v15 and qmlog(r"^qm stop 100061") and qmlog(r"^qm destroy 100061"), sorted(v15))
ck("VPS mới mua (63) vẫn được nhân bản + bật trong lúc đang xoá máy khác (việc xoá không chiếm chỗ max_builds)",
   (v15.get("100063") or {}).get("status") == "running", v15.get("100063"))
ck("việc xoá là việc NHẸ: bg(..., light=True) không bị chặn bởi max_builds, máy đang dựng vẫn tính đủ",
   "light=True" in open(os.path.join(ROOT, "cbhost.py"), encoding="utf-8").read())

print("17. 27/11e · KHO PROXY NHIỀU IP (cbpool): tự tải đúng md5, dịch vụ cloudblue-pool, báo web danh sách ô · 27/11f tự dò PPPoE")
import threading, urllib.request
cb.http_get = lambda url, limit=4 << 20: urllib.request.urlopen(url, timeout=10).read(limit)     # mục 14 thay bằng bản giả → trả lại bản thật
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"full_clone": True, "storage": "local-lvm"}))
FAKE_BIN = b"\x7fELF-cbpool-gia-" + os.urandom(64)
open(os.path.join(RAWD, "cbpool-x86_64"), "wb").write(FAKE_BIN)
cb.POOL_FILE = ("cbpool-x86_64", hashlib.md5(FAKE_BIN).hexdigest())
for f in (SYSLOG, SYSON, os.environ["CBHOST_POOL_BIN"], os.environ["CBHOST_POOL_UNIT"], os.environ["CBHOST_POOL_CONF"]):
    try: os.remove(f)
    except OSError: pass
c17 = cb.conf()
ck("mặc định BẬT kho proxy (pool)", c17["pool"] is True)
pm = cb.PoolMgr(c17); r = pm.step(True)
sl = open(SYSLOG).read() if os.path.exists(SYSLOG) else ""
ck("lần đầu: tải cbpool từ GitHub đúng md5 → /usr/local/bin/cbpool (755)", os.path.exists(os.environ["CBHOST_POOL_BIN"]) and open(os.environ["CBHOST_POOL_BIN"], "rb").read() == FAKE_BIN
   and os.stat(os.environ["CBHOST_POOL_BIN"]).st_mode & 0o777 == 0o755, pm.err)
pc = json.load(open(os.environ["CBHOST_POOL_CONF"]))
ck("ghi cấu hình đầu: cổng 8899 mọi card (lọc máy trong mạng nhà ở cbpool), card IPv6 = cầu vmbr0, 30 ô, 30 Mbit/s mỗi ô",
   pc == {"listen": "0.0.0.0:8899", "iface6": "vmbr0", "slots": 30, "bw_kbps": 30000}, pc)
ut = open(os.environ["CBHOST_POOL_UNIT"]).read()
ck("dịch vụ cloudblue-pool: Restart=always, chạy đúng file + cấu hình, bảo vệ hệ thống (ProtectSystem/NoNewPrivileges)",
   "Restart=always" in ut and (os.environ["CBHOST_POOL_BIN"] + " run -c " + os.environ["CBHOST_POOL_CONF"]) in ut and "ProtectSystem=full" in ut and "NoNewPrivileges=yes" in ut, ut)
ck("systemctl daemon-reload + enable --now cloudblue-pool", "daemon-reload" in sl and "enable --now cloudblue-pool.service" in sl, sl)
ck("cbpool chưa trả lời ổ cắm → báo web {ok: false, err}", r == {"ok": False, "err": "cbpool chưa chạy"}, r)
open(SYSLOG, "w").write(""); pm.t = 0; pm.step(True)
sl = open(SYSLOG).read()
ck("lần sau: file đúng md5 + dịch vụ đang chạy → không tải lại, không bật lại", "enable" not in sl and "restart" not in sl and pm.err == "", (sl, pm.err))
open(os.path.join(RAWD, "cbpool-x86_64"), "wb").write(b"ban-la"); os.remove(os.environ["CBHOST_POOL_BIN"]); pm.t = 0; pm.step(True)
ck("GitHub trả file sai md5 → KHÔNG ghi, báo lỗi rõ", not os.path.exists(os.environ["CBHOST_POOL_BIN"]) and "sai md5" in pm.err, pm.err)
pm.t = 0; pm.step(True)
ck("tải hỏng → 10 phút sau mới tải lại", "thử lại sau" in pm.err, pm.err)
open(os.path.join(RAWD, "cbpool-x86_64"), "wb").write(FAKE_BIN); pm.dl_fail_t = 0; open(SYSLOG, "w").write(""); pm.t = 0; pm.step(True)
ck("có lại đúng bản → tải + chạy lại dịch vụ", os.path.exists(os.environ["CBHOST_POOL_BIN"]) and "restart cloudblue-pool.service" in open(SYSLOG).read(), open(SYSLOG).read())

# cbpool giả trả trạng thái qua ổ cắm điều khiển
ST = {"ver": "27.11a", "listen": "0.0.0.0:8899", "v6": {"on": True, "iface": "vmbr0", "prefix": "2001:db8:5:ac60::/64", "err": ""},
      "ppp": {"want": 2, "up": 1, "account": True, "iface": "vmbr0", "sess": [{"k": 0, "up": True, "ip": "203.0.113.5"}, {"k": 1, "up": False, "err": "x"}]},
      "slots": [{"id": "p%02d" % (i + 1), "user": "p%02d" % (i + 1), "pass": "Pw%014d" % i, "rot": "R%019d" % i,
                 "ip6": "2001:db8:5:ac60:%x:1:2:3" % (i + 1), "ip4": "203.0.113.5" if i % 2 == 0 else "", "sess": i % 2, "conns": i} for i in range(3)]}
srv = socket.socket(socket.AF_UNIX); srv.bind(os.environ["CBHOST_POOL_CTL"]); srv.listen(4)
def _serve():
    while True:
        try: c, _ = srv.accept()
        except OSError: return
        rq = c.recv(4096)
        c.sendall((json.dumps(ST if b'"status"' in rq else {"ok": False}) + "\n").encode()); c.close()
threading.Thread(target=_serve, daemon=True).start()
r = pm.step(False)
ck("báo web gọn: máy (IP mạng nhà) + cổng 8899 + dải IPv6 + ô [id, mật khẩu, đuôi IPv6, IPv4, kết nối, khoá đổi IP] + IP các phiên PPPoE",
   r.get("ok") and r.get("port") == 8899 and r.get("v6") == "2001:db8:5:ac60::/64" and r["s"][0] == ["p01", "Pw00000000000000", "1:1:2:3", "203.0.113.5", 0, "R0000000000000000000"]
   and r["s"][1][3] == "" and r["ppp"] == {"want": 2, "up": 1, "acct": True, "ip": ["203.0.113.5"], "k": [0]} and "host" in r, r)
ST["ppp"] = {"want": 0, "up": 0, "account": False, "iface": "vmbr0", "sess": [], "err": "chưa có tài khoản PPPoE (gõ: cbpool ppp-set)",
             "disc": {"t": 1795760000, "iface": "vmbr0", "ok": True, "ac": ["cbtest-ac", "AC-" + "x" * 80, "c", "d"]}}
r = pm.step(False)
ck("27/11f · kết quả tự dò PPPoE lên web: modem cho đi qua + tên máy chủ nhà mạng (≤3 tên, ≤40 ký tự)",
   r["ppp"].get("disc") == {"t": 1795760000, "ok": True, "ac": ["cbtest-ac", "AC-" + "x" * 37, "c"]} and r["ppp"]["acct"] is False and "ppp-set" in r["ppp"]["err"], r["ppp"])
ST["ppp"]["disc"] = {"t": 1795760001, "iface": "vmbr0", "ok": False}
r1 = pm.step(False)
ST["ppp"]["disc"] = {"t": "lạ", "iface": "vmbr0", "err": "mở ổ cắm PPPoE lỗi (cần root): " + "e" * 300}
r2 = pm.step(False)
ST["ppp"]["disc"] = "rác"
r3 = pm.step(False)
ck("27/11f · dò không có trả lời → ok false; dò lỗi → err (≤120); dữ liệu lạ → bỏ qua",
   r1["ppp"].get("disc") == {"t": 1795760001, "ok": False, "ac": []} and r2["ppp"].get("disc") == {"t": 0, "err": ("mở ổ cắm PPPoE lỗi (cần root): " + "e" * 300)[:120]}
   and "disc" not in r3["ppp"], (r1["ppp"], r2["ppp"], r3["ppp"]))
w17 = FakeWeb(); w17.status = "ready"; h17 = cb.Host(web=w17); h17.pool = pm
ST["slots"] = [dict(ST["slots"][0], id="p%03d" % i, pass_="x" * 30) for i in range(200)]
h17.poll_once(); wait_idle(h17)
m17 = last_poll(w17)["p_metrics"]
ck("số đo (kèm px) luôn ≤ 12 KB: nhiều ô quá thì cắt bớt danh sách ô (đánh dấu cut)", len(json.dumps(m17)) <= 12000 and (m17.get("px") or {}).get("cut") == 1
   and 5 <= len(m17["px"]["s"]) < 200, (len(json.dumps(m17)), len((m17.get("px") or {}).get("s") or [])))
srv.close()
open(os.environ["CBHOST_CONF"], "w").write(json.dumps({"pool": False})); c18 = cb.conf(); open(SYSON, "w").write("1"); open(SYSLOG, "w").write("")
pm2 = cb.PoolMgr(c18); r = pm2.step(True)
ck("tắt được: \"pool\": false → systemctl disable --now cloudblue-pool, không báo px", c18["pool"] is False and "disable --now cloudblue-pool.service" in open(SYSLOG).read() and r is None,
   (open(SYSLOG).read(), r))
ck("cbhost không chạy lệnh qua shell (kho proxy cũng vậy)", "shell=True" not in open(os.path.join(ROOT, "cbhost.py")).read())

print("18. 27/11g · BÁN PROXY: px_host_sync → file tài khoản khách cho cbpool · tài khoản PPPoE mã hoá → cbpool ppp-import · báo IP ô + khoá")
cb.POOL_USERS_F = os.path.join(tmp, "cbpool-users.json")
PK = "B" + "A" * 86
CUST = {"ok": True, "units": {"s001": "2001:db8:5:ac60::77", "1": "203.0.113.11", "bad unit!": "x"}, "users": [], "pk": PK}
seen_ctl = []
srv18 = socket.socket(socket.AF_UNIX)
try: os.remove(os.environ["CBHOST_POOL_CTL"])
except OSError: pass
srv18.bind(os.environ["CBHOST_POOL_CTL"]); srv18.listen(8)
def _serve18():
    while True:
        try: c, _ = srv18.accept()
        except OSError: return
        rq = json.loads(c.recv(4096).decode() or "{}"); seen_ctl.append(rq.get("cmd"))
        c.sendall((json.dumps(CUST if rq.get("cmd") == "cust" else {"ok": True, "users": 2}) + "\n").encode()); c.close()
threading.Thread(target=_serve18, daemon=True).start()
# cbpool giả cho lệnh ppp-import: đọc chuỗi mã hoá từ stdin (KHÔNG từ dòng lệnh), trả JSON
open(os.environ["CBHOST_POOL_BIN"], "w").write("#!/usr/bin/env python3\nimport sys, json\nd = sys.stdin.read()\n"
    "open(sys.argv[0] + '.argv', 'w').write(' '.join(sys.argv[1:]))\n"
    "print(json.dumps({'ok': True, 'user': 'fpt***', 'sessions': 2}) if d.strip().startswith('{') and sys.argv[1] == 'ppp-import' else json.dumps({'ok': False, 'err': 'sai'}))\n")
os.chmod(os.environ["CBHOST_POOL_BIN"], 0o755)
class PxWeb:
    def __init__(self): self.calls = []; self.err = ""; self.resp = None
    def rpc(self, fn, body, timeout=25):
        self.calls.append((fn, json.loads(json.dumps(body))))
        return json.loads(json.dumps(self.resp)) if fn == "px_host_sync" else None
pw = PxWeb(); exp = int(time.time()) + 3600
pw.resp = {"ok": True, "bw": 20000, "fb4": False, "sale4": True, "maxc": 64, "self": ["203.0.113.200"], "users": [
    {"u": "pxabc12345", "p": "mat-khau-khach-1", "k": "v6", "n": "s001", "x": exp, "s": 1, "r": "rotkey-khach-0000001"},
    {"u": "pxdef67890", "p": "mat-khau-khach-2", "k": "v4", "n": "1", "x": exp, "s": 3, "r": "khoa-share-khong-duoc-doi"},
    {"u": "PX-SAI", "p": "mat-khau-khach-3", "k": "v6", "n": "s002", "x": exp, "s": 1},
    {"u": "pxhethan01", "p": "mat-khau-khach-4", "k": "v6", "n": "s003", "x": int(time.time()) - 5, "s": 1},
    {"u": "pxngan0001", "p": "ngan", "k": "v6", "n": "s004", "x": exp, "s": 1}],
    "ppp": {"gen": 3, "enc": json.dumps({"v": 1, "e": "x", "i": "y", "c": "z"})}}
pm18 = cb.PoolMgr(cb.conf(), pw, "bi-mat-may-chu"); pm18.sync()
uf = json.load(open(cb.POOL_USERS_F)) if os.path.exists(cb.POOL_USERS_F) else {}
ck("lấy tài khoản khách từ web → file 600 cho cbpool (bỏ dòng sai tên / hết hạn / mật khẩu ngắn; khoá đổi IP chỉ proxy riêng) + báo cbpool nạp lại",
   [u["u"] for u in uf.get("users", [])] == ["pxabc12345", "pxdef67890"] and uf["users"][0].get("r") == "rotkey-khach-0000001" and "r" not in uf["users"][1]
   and uf.get("sale4") is True and uf.get("self") == ["203.0.113.200"] and os.stat(cb.POOL_USERS_F).st_mode & 0o777 == 0o600 and "users" in seen_ctl, (uf, seen_ctl))
rep = pw.calls[-1][1]
ck("gọi px_host_sync bằng mã máy chủ + báo khoá công khai + IP đang ra của từng ô bán (bỏ tên ô lạ)",
   pw.calls[-1][0] == "px_host_sync" and rep["p_secret"] == "bi-mat-may-chu" and rep["p_report"]["pk"] == PK
   and rep["p_report"]["units"] == {"s001": "2001:db8:5:ac60::77", "1": "203.0.113.11"}, rep)
ck("tài khoản PPPoE mã hoá → cbpool ppp-import qua stdin (không lên dòng lệnh) → lần sau báo đã nhận (ppp_ok)",
   pm18.ppp_done == 3 and pm18.ppp_err == "" and "ppp-import -c" in open(os.environ["CBHOST_POOL_BIN"] + ".argv").read()
   and "\"v\"" not in open(os.environ["CBHOST_POOL_BIN"] + ".argv").read(), (pm18.ppp_done, pm18.ppp_err))
n_users = seen_ctl.count("users"); pm18.sync()
ck("lần sau: web không đổi gì → không ghi lại file, không bắt cbpool nạp lại; báo ppp_ok = 3",
   seen_ctl.count("users") == n_users and pw.calls[-1][1]["p_report"].get("ppp_ok") == 3, (seen_ctl, pw.calls[-1][1]["p_report"]))
pw.resp["ppp"] = {"gen": 4, "enc": "khong-phai-json"}; pm18.sync()
ck("chuỗi PPPoE hỏng → không nhận, báo lỗi lên web (ppp_err) lần sau", pm18.ppp_done == 3 and pm18.ppp_err, pm18.ppp_err)
pw.resp = None; pw.err = "HTTP 404: {\"code\":\"PGRST202\",\"message\":\"Could not find the function public.px_host_sync\"}"; pm18.sync()
ck("web chưa chạy SQL v63 → im lặng (không báo lỗi bán proxy)", pm18.sync_err == "", pm18.sync_err)
srv18.close()
st18 = {"ver": "27.11c", "listen": "0.0.0.0:8899", "v6": {"prefix": "2001:db8:5:ac60::/64"}, "pk": PK, "cust": {"n": 2, "conns": 5}, "pub4": "203.0.113.200",
        "ppp": {"want": 3, "up": 2, "account": True, "sess": [{"k": 0, "up": True, "ip": "203.0.113.10"}, {"k": 1, "up": False}, {"k": 2, "up": True, "ip": "203.0.113.12"}]}, "slots": []}
r18 = pm18.report(st18)
ck("số đo web: khoá công khai (để mã hoá tài khoản PPPoE) + số khách + phiên đang lên (bán IPv4)",
   r18.get("pk") == PK and r18.get("cust") == {"n": 2, "conns": 5} and r18["ppp"]["k"] == [0, 2] and r18["ppp"].get("enc_err") and r18.get("pub4") == "203.0.113.200", r18)

print("\n%d/%d đạt" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
