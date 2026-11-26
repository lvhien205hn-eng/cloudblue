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
for tool in ("qm", "pvesh"):
    p = os.path.join(bind, tool)
    open(p, "w").write("#!/bin/sh\nexec %s %s %s \"$@\"\n" % (sys.executable, os.path.join(HERE, "fakepve.py"), tool))
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
STATE = os.path.join(tmp, "pve.json")
os.environ.update(FAKE_PVE_STATE=STATE, CBHOST_QM=os.path.join(bind, "qm"), CBHOST_PVESH=os.path.join(bind, "pvesh"),
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


class FakeWeb:
    """Web giả: giữ trạng thái máy chủ + danh sách VPS muốn có; ghi lại các lần gọi."""
    def __init__(self):
        self.calls, self.status, self.vps, self.tickets, self.err = [], "new", [], {}, ""
        self.secret_hash = None
        self.jobs = None; self.jtickets = {}               # None = web cũ (chưa v57): không trả tpl_jobs

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
                 "tpl": ["tpl-win10-22h2"], "poll_s": 10}
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
hu.c["auto_update"] = False; off = cb.update_due(hu, time.time(), 0)
ck("dịch vụ: tới giờ → xem bản mới; đang dựng máy ảo / chưa đủ 1 giờ / tắt auto_update → chờ", due and not busy and not soon and not off, (due, busy, soon, off))
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
\taddress 2405:4803:ff84:ac60:2034:4dff:fe09:6697/64
\tgateway fe80::1
\tbridge-ports nic0
\tbridge-stp off
\tbridge-fd 0

source /etc/network/interfaces.d/*
"""
IF4 = IF6.replace("inet6 manual", "inet manual").replace("iface vmbr0 inet6 static", "iface vmbr0 inet static").replace("2405:4803:ff84:ac60:2034:4dff:fe09:6697/64", "192.168.1.50/24").replace("fe80::1", "192.168.1.1")
netd = os.path.join(tmp, "net"); os.makedirs(netd)
cb.RESOLV_F, cb.IFACES_F = os.path.join(netd, "resolv.conf"), os.path.join(netd, "interfaces")
NET = {"v4": False, "v6": True, "lease": True, "cmds": [], "have": {"dhclient", "ifreload"}, "dns_ok": False}
_run0, _which0, _res0 = cb.run, cb.shutil.which, cb.can_resolve


def fake_run(cmd, timeout=900):
    if cmd[0] == "ip":
        NET["cmds"].append(" ".join(cmd))
        on = NET["v4"] if cmd[1] == "-4" else NET["v6"]
        return 0, ("default via %s dev vmbr0 proto kernel onlink" % ("192.168.1.1" if cmd[1] == "-4" else "fe80::1")) if on else ""
    if cmd[0] == "ifreload":
        NET["cmds"].append(" ".join(cmd))
        if NET["lease"] and re.search(r"^iface vmbr0 inet dhcp$", open(cb.IFACES_F).read(), re.M): NET["v4"] = True     # mạng có DHCP → có IPv4
        return 0, ""
    return _run0(cmd, timeout)


def net_reset(ifaces=IF6, resolv="search lan\nnameserver 192.168.100.1\n", **kw):
    for f in os.listdir(netd): os.remove(os.path.join(netd, f))
    open(cb.IFACES_F, "w").write(ifaces); open(cb.RESOLV_F, "w").write(resolv)
    NET.update(v4=False, v6=True, lease=True, cmds=[], have={"dhclient", "ifreload"}, dns_ok=False); NET.update(kw)


cb.run = fake_run
cb.shutil.which = lambda n, *a, **k: ("/usr/sbin/" + n) if n in NET["have"] else None
cb.can_resolve = lambda host, secs=8: NET["dns_ok"]
C6 = dict(cb.DEFAULTS, bridge="vmbr0", net_heal=True, sb_url="https://web.cloudblue.thu")
try:
    net_reset()
    ck("đọc đường ra: máy chỉ có IPv6 → (IPv4 không, IPv6 có), ip6_only = True", cb.default_routes() == (False, True) and cb.ip6_only() is True, cb.default_routes())
    did = cb.net_heal(C6, 1)
    it = open(cb.IFACES_F).read()
    ck("máy chỉ có IPv6, mạng CÓ DHCP: thêm đúng 1 đoạn 'iface vmbr0 inet dhcp' vào CUỐI file (phần cũ còn nguyên từng byte), chạy ifreload -a, lưu bản gốc .cb-goc",
       it.startswith(IF6.rstrip("\n")) and it.count("\niface vmbr0 inet dhcp\n") == 1 and it.endswith("iface vmbr0 inet dhcp\n") and "ifreload -a" in NET["cmds"]
       and open(cb.IFACES_F + ".cb-goc").read() == IF6 and any("inet dhcp" in x for x in did), (did, it[-200:]))
    rs = open(cb.RESOLV_F).read()
    ck("… DNS 192.168.100.1 (bộ cài tự điền) không phân giải được → đặt lại: có IPv4 + IPv6 thì 8.8.8.8, 2001:4860:4860::8888, 1.1.1.1; giữ dòng search; lưu bản gốc",
       cb.resolv_servers(rs) == ["8.8.8.8", "2001:4860:4860::8888", "1.1.1.1"] and "search lan" in rs and "192.168.100.1" not in rs
       and open(cb.RESOLV_F + ".cb-goc").read() == "search lan\nnameserver 192.168.100.1\n" and any("DNS" in x for x in did), (did, rs))
    n_cmd = len([x for x in NET["cmds"] if x.startswith("ifreload")])
    did2 = cb.net_heal(C6, 2); did3 = cb.net_heal(C6, 5)
    ck("gọi lại nhiều lần: KHÔNG thêm đoạn thứ hai, không chạy lại ifreload, không ghi lại DNS, bản gốc không bị đè",
       did2 == [] and did3 == [] and open(cb.IFACES_F).read() == it and open(cb.RESOLV_F).read() == rs and len([x for x in NET["cmds"] if x.startswith("ifreload")]) == n_cmd
       and open(cb.IFACES_F + ".cb-goc").read() == IF6, (did2, did3))
    net_reset(lease=False)
    did = cb.net_heal(C6, 1)
    rs = open(cb.RESOLV_F).read()
    ck("máy chỉ có IPv6, mạng KHÔNG có DHCP: vẫn thêm 'inet dhcp' (dhclient tự thử lại về sau) và đặt DNS IPv6 công cộng (2001:4860:4860::8888, 2606:4700:4700::1111) → chạy được chỉ bằng IPv6",
       "\niface vmbr0 inet dhcp\n" in open(cb.IFACES_F).read() and cb.resolv_servers(rs) == ["2001:4860:4860::8888", "2606:4700:4700::1111"] and len(did) == 2, (did, rs))
    net_reset(ifaces=IF4, v4=True, v6=False, resolv="nameserver 192.168.1.1\n")
    did = cb.net_heal(C6, 1)
    ck("máy cài bình thường (IPv4 tĩnh, DNS của mạng): mất mạng tạm thời → KHÔNG đụng file nào ở lượt đầu", did == [] and open(cb.IFACES_F).read() == IF4 and open(cb.RESOLV_F).read() == "nameserver 192.168.1.1\n"
       and not os.path.exists(cb.IFACES_F + ".cb-goc") and not [x for x in NET["cmds"] if x.startswith("ifreload")], did)
    did = cb.net_heal(C6, 3)
    ck("… hỏng tên miền nhiều lượt liền (lượt 3) → mới đặt DNS công cộng IPv4 (8.8.8.8, 1.1.1.1), file mạng vẫn nguyên; bản gốc lưu ở .cb-goc",
       cb.resolv_servers(open(cb.RESOLV_F).read()) == ["8.8.8.8", "1.1.1.1"] and open(cb.IFACES_F).read() == IF4 and open(cb.RESOLV_F + ".cb-goc").read() == "nameserver 192.168.1.1\n", did)
    net_reset(ifaces=IF4, v4=False, v6=False)
    ck("cầu mạng đã có cấu hình IPv4 (tĩnh) mà không có đường ra nào: không thêm DHCP, không ghi DNS (không biết đường nào dùng được)", cb.net_heal(C6, 5) == [] and open(cb.IFACES_F).read() == IF4
       and open(cb.RESOLV_F).read() == "search lan\nnameserver 192.168.100.1\n")
    net_reset(have={"ifreload"})
    did = cb.net_heal(C6, 1)
    ck("máy không có dhclient (ifupdown2 của Proxmox chỉ xin DHCP bằng dhclient): KHÔNG sửa file mạng; vẫn sửa DNS", open(cb.IFACES_F).read() == IF6 and len(did) == 1 and "DNS" in did[0], did)
    net_reset(ifaces=IF6.replace("vmbr0", "vmbr9"))
    cb.net_heal(C6, 1)
    ck("file mạng không có cầu vmbr0 → không thêm gì", "inet dhcp" not in open(cb.IFACES_F).read())
    net_reset(resolv="nameserver 192.168.100.1\n")
    did = cb.net_heal(dict(C6, sb_url="http://10.0.2.2:8765"), 1)
    ck("web gọi bằng địa chỉ số (bộ thử): không cần tên miền → không đụng DNS, vẫn xin DHCP", open(cb.RESOLV_F).read() == "nameserver 192.168.100.1\n" and len(did) == 1 and "inet dhcp" in did[0], did)
    net_reset(dns_ok=True, v4=True)
    ck("mạng đủ cả (có IPv4, phân giải được): không làm gì", cb.net_heal(C6, 9) == [] and open(cb.IFACES_F).read() == IF6)
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
    ck("web_host / is_ip: tên miền, địa chỉ IPv4, IPv6 trong ngoặc", cb.web_host(C6) == "web.cloudblue.thu" and cb.is_ip("10.0.2.2") and cb.is_ip(cb.web_host({"sb_url": "http://[fec0::2]:8765"})) and not cb.is_ip("a.b"))
finally:
    cb.run, cb.shutil.which, cb.can_resolve = _run0, _which0, _res0

print("\n%d/%d đạt" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
