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

    def rpc(self, fn, body, timeout=25):
        self.calls.append((fn, json.loads(json.dumps(body))))
        if fn == "vm_host_hello":
            self.secret_hash = hashlib.sha256(body["p_secret"].encode()).hexdigest()
            return {"ok": True, "id": "h1", "status": self.status, "name": "pve-thu"}
        if fn == "vm_host_poll":
            if hashlib.sha256(body["p_secret"].encode()).hexdigest() != self.secret_hash: return {"ok": False, "err": "BAD_SECRET"}
            for x in body.get("p_vps") or []:
                if x.get("ticket_hash"): self.tickets[x["id"]] = x["ticket_hash"]
            return {"ok": True, "status": self.status, "name": "pve-thu", "vps": json.loads(json.dumps(self.vps)) if self.status != "new" else [],
                    "tpl": ["tpl-win10-22h2"], "poll_s": 10}
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

print("\n%d/%d đạt" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
