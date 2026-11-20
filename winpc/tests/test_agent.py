# -*- coding: utf-8 -*-
"""Thử NỐI CHUỖI: SQL thật (Postgres) ⇄ agent (pcagent.py) ⇄ bộ cài WinPE (cb_pe.py) trên máy Windows giả.
   Cần CSDL thử pctest đã nạp cloud-pc-v41.sql (bộ thử SQL không nằm trên GitHub):  python3 test_agent.py"""
import hashlib, json, os, subprocess, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for d in ("lib", "pe", "agent"): sys.path.insert(0, os.path.join(HERE, "..", d))
import cbcore as C                                    # noqa: E402
import cbrec                                          # noqa: E402
import cb_pe                                          # noqa: E402
import pcagent                                        # noqa: E402
from cbsys import GPT_DATA, GPT_ESP, GPT_MSR          # noqa: E402
from fakesys import GB, MB, FakeSys, ScriptUI         # noqa: E402
import test_pe_helpers as H                           # noqa: E402

PSQL = ["psql", "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", "pctest", "-X", "-At", "-v", "ON_ERROR_STOP=1"]
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", extra)


def q(sql, role=None, uid=None, ip=None):
    pre = ["begin;"]
    if role: pre.append(f"set local role {role};")
    if uid: pre.append(f"set local request.jwt.claim.sub = '{uid}';")
    if ip: pre.append("set local request.headers = '%s';" % json.dumps({"cf-connecting-ip": ip}))
    r = subprocess.run(PSQL + ["-c", " ".join(pre) + " " + sql.rstrip(";") + "; commit;"], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr.strip() + "\nSQL: " + sql[:300])
    out = [x for x in r.stdout.strip().splitlines() if x not in ("BEGIN", "SET", "COMMIT")]
    return out[-1] if out else ""


def lit(v):
    if v is None: return "null"
    if isinstance(v, (dict, list)): return "$j$%s$j$::jsonb" % json.dumps(v, ensure_ascii=False)
    return "$s$%s$s$" % v


class SqlNet:
    """Thay Supabase: gọi thẳng hàm SQL bằng vai trò anon + IP giả (đúng như PostgREST gọi)."""
    last_err = ""

    def __init__(self, ip="1.54.69.205"):
        self.ip, self.calls, self.down, self.files = ip, [], False, {}
        self.url = self.key = "x"

    def rpc(self, fn, body, timeout=20):
        self.calls.append((fn, body))
        if self.down: self.last_err = "mất mạng"; return None
        args = ", ".join("%s := %s" % (k, lit(v)) for k, v in body.items())
        return json.loads(q("select %s(%s)" % (fn, args), role="anon", ip=self.ip))

    def get(self, url, timeout=60, limit=8 << 20):
        if url not in self.files: raise OSError("404 " + url)
        return self.files[url]


class FakeHost:
    def __init__(self, fs, name="CB-TEST01"):
        self.fs, self.name, self.powers, self.check_ok, self.restarts = fs, name, [], True, 0
        self.ip, self.aborts, self.clock_ok, self.clock_tries, self.msgs = "192.168.1.77", 0, False, [], []

    def hostname(self): return self.name

    def os_ver(self):
        m = self.fs.file("C", "windows\\cb-image.txt") or ""
        return "10.0.10586.0" if m.startswith("1511") else "10.0.19045.3803"

    def os_name(self): return "Windows 10 Pro"
    def cpu(self): return ("Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz", 56)
    def ram_gb(self): return 64.0
    def gpus(self): return ["NVIDIA GeForce GTX 1060 6GB"]
    def lan_ip(self): return self.ip
    def uptime(self): return 1234
    def smbios(self): return {"uuid": "03000200040005000006000700080009", "board_serial": "BS123", "sys_serial": "Default string", "vendor": "HUANANZHI", "product": "X99", "board": "HUANANZHI X99-TF"}
    def power(self, reboot=True, delay=5, msg=""): self.powers.append(("reboot" if reboot else "shutdown", delay)); self.fs.rebooted = True
    def notify(self, text, secs=60): self.msgs = getattr(self, "msgs", []) + [text]
    def abort_shutdown(self): self.aborts += 1

    def set_clock(self, epoch):                                       # clock_ok = False: Windows từ chối (mặc định của bộ thử → đồng hồ giả giữ nguyên)
        self.clock_tries.append(epoch)
        if not self.clock_ok: return False
        self.fs.clock = float(epoch); return True
    def mutex(self, name=""): return True
    def restart_self(self): self.restarts += 1; return True
    def selfcheck(self, script): return (self.check_ok, "" if self.check_ok else "ImportError: x")


def boot_windows(fs):
    """Máy 'khởi động vào Windows': phân vùng Windows nhận chữ C, các chữ tạm của bộ cài (W/S/R) biến mất."""
    for d in fs.fdisks:
        for p in d.slots:
            if not p.vol: continue
            if p.vol.letter in ("W", "S", "R", "C"): p.vol.letter = None
    for d in fs.fdisks:
        for p in d.slots:
            if p.vol and p.vol.label == "Windows" and "windows\\system32\\config\\system" in p.vol.files: p.vol.letter = "C"; break
    fs.rebooted = False
    fs.bcd.pop("(system)", None)


def boot_pe(fs):
    for d in fs.fdisks:
        for p in d.slots:
            if p.vol and p.vol.letter == "C": p.vol.letter = None
    fs.rebooted = False


def agent(fs, net, host):
    logs = []
    a = pcagent.Agent(fs, host, net, "C:\\CloudBluePC", logs.append)
    a.logs = logs
    return a


def sysbcd(fs): return fs.bcd.get("(system)", {})


# ---------------------------------------------------------------- chuẩn bị CSDL
q("truncate pc_orders, pc_machines, pc_rl restart identity cascade")
q("update pc_settings set enroll_hash = null, auto_approve = false, agent = '{}'::jsonb, poll_s = 30")
ADMIN = q("select id from profiles where role = 'admin' limit 1")
A = dict(role="authenticated", uid=ADMIN)
KEY = q("select pc_admin_new_key()", **A)

print("1. Cài mới từ USB → Windows lên → agent tự đăng ký bằng mã trong bộ cài")
fs = FakeSys("uefi"); cfg = H.cfg0(); H.usb(fs, cfg, key=KEY)
ssd = fs.disk(0, 480, bus=17, model="Samsung 970 EVO", ssd=True, style="raw", serial="S466NX0M123456")
hdd = fs.disk(1, 2000, model="ST2000DM008", ssd=False, style="gpt"); hdd.add(0, GPT_DATA, "NTFS", "KHO", "D", files={"a.txt": "1"})
rc = cb_pe.Installer(fs).run(ScriptUI())
ck("bộ cài chạy xong", rc == 0)
fs.fdisks = [d for d in fs.fdisks if d.index != 9]                 # rút USB
boot_windows(fs)
net, host = SqlNet(), FakeHost(fs)
ag = agent(fs, net, host)
ck("Windows mới chưa có mã máy", ag.ident is None and fs.file("C", "cloudbluepc\\seed.json") and KEY in fs.file("C", "cloudbluepc\\seed.json"))
nap = ag.tick()
ck("nhịp 1: đăng ký được bằng mã của bộ cài", ag.ident is not None and len(ag.ident["token"]) == 64 and nap <= 5, ag.logs)
PC = ag.ident["id"]
row = json.loads(q(f"select row_to_json(m) from pc_machines m where id = '{PC}'"))
ck("máy hiện trên web: tên Windows, 22H2, IP LAN, chờ duyệt", row["name"] == "CB-TEST01" and row["os"] == "22h2" and row["lan_ip"] == "192.168.1.77" and row["status"] == "new" and row["approved"] is False, row)
ck("web thấy cấu hình: CPU, RAM, card, ổ đĩa, bo mạch", row["info"]["cores"] == 56 and row["info"]["ram_gb"] == 64.0 and row["info"]["gpus"] == ["NVIDIA GeForce GTX 1060 6GB"]
   and [(d["gb"], d["ssd"], d["bus"]) for d in row["info"]["disks"]] == [(515, True, "NVMe"), (2147, False, "SATA")] and row["info"]["board"] == "HUANANZHI X99-TF", row["info"])
ck("web biết máy đổi được sang 22h2 / 1511", row["info"]["rec"] == {"ok": True, "images": ["22h2", "1511"], "ver": "20.11a"}, row["info"].get("rec"))
ck("sau khi đăng ký: seed.json hết mã đăng ký", KEY not in fs.file("C", "cloudbluepc\\seed.json"))
ck("web biết tình trạng bảo mật của máy (khách là tài khoản thường; chưa có mốc khoá quyền / hạ quyền vì Windows giả chưa chạy cb_provision)", row["info"].get("sec") == {"std": True, "hard": False, "lock": False}, row["info"].get("sec"))
stt = fs.file("C", "cloudbluepc\\os\\status.txt") or ""
ck("os\\status.txt (tài khoản thường đọc được): ghi đã đăng ký + tên trên web, KHÔNG có mã máy / mã đăng ký", "Dang ky voi he thong: ROI" in stt and "CB-TEST01" in stt and "Ket noi may chu: duoc" in stt
   and ag.ident["token"] not in stt and KEY not in stt and PC not in stt, stt)
rec = next(p for p in ssd.slots if p.vol and p.vol.label == "CBRECOVERY")
ident_rec = json.loads(rec.vol.files["cb\\identity.json"])
ck("phân vùng cứu hộ nhớ mã số máy + dấu phần cứng, KHÔNG có mã bí mật", ident_rec["id"] == PC and len(ident_rec["hw"]) == 64 and "token" not in ident_rec and KEY not in json.dumps({k: str(v) for k, v in rec.vol.files.items()}))
ck("dấu phần cứng tính từ bo mạch + ổ hệ thống", ag.ident["hw"] == pcagent.hw_id(host.smbios(), "S466NX0M123456", "Samsung 970 EVO"))
nap = ag.tick()
ck("nhịp 2: báo sống, chưa có lệnh, nghỉ 30 giây", nap == 30 and net.calls[-1][0] == "pc_poll" and q(f"select last_seen > now() - interval '5 seconds' from pc_machines where id = '{PC}'") == "t")

print("2. Mất mạng / máy chủ lỗi")
net.down = True
naps = [ag.tick() for _ in range(3)]
ck("mất mạng: không sập, giãn nhịp dần", naps == [60, 90, 120] and ag.ident is not None, naps)
ck("mất mạng: status.txt ghi rõ chưa nối được máy chủ", "Ket noi may chu: CHUA DUOC" in (fs.file("C", "cloudbluepc\\os\\status.txt") or ""), fs.file("C", "cloudbluepc\\os\\status.txt"))
net.down = False
ck("có mạng lại: chạy tiếp bình thường", ag.tick() == 30 and ag.fail == 0)

print("3. Admin duyệt + đổi tên + lệnh khởi động lại")
q(f"select pc_admin_set('{PC}', '{{\"approved\": true, \"name\": \"Máy 14-85\"}}')", **A)
ag.tick()
ck("agent nhận tên mới, ghi lại vào identity (cả phân vùng cứu hộ)", ag.name == "Máy 14-85" and json.loads(fs.file("C", "cloudbluepc\\identity.json"))["name"] == "Máy 14-85" and json.loads(rec.vol.files["cb\\identity.json"])["name"] == "Máy 14-85")
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reboot'))", **A))["id"]
ag.tick()
ck("lệnh reboot: báo xong về web TRƯỚC rồi mới khởi động lại", q(f"select state from pc_orders where id = {oid}") == "done" and host.powers == [("reboot", 10)] and ag.rebooting)
ck("đang chờ khởi động lại thì không gọi máy chủ nữa", (lambda n: (ag.tick(), len(net.calls) == n)[1])(len(net.calls)))
boot_windows(fs); ag = agent(fs, net, host); host.powers.clear()
ck("lên lại: còn mã máy, không nhận lại lệnh cũ", ag.ident and ag.tick() == 30 and not host.powers)

print("4. Lệnh DỌN MÁY + đổi sang Windows 1511 (khách cũ trả máy)")
ssd_win = next(p for p in ssd.slots if p.vol and p.vol.letter == "C")
ssd_win.vol.put("users\\khach\\mat-khau.txt", "bi mat cua khach cu")
old_token = ag.ident["token"]
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"1511\", \"wipe\": \"all\"}}'))", **A))["id"]
ag.tick()
job = json.loads(rec.vol.files["cb\\job.json"])
ck("agent ghi lệnh lên phân vùng cứu hộ: bản 1511, xoá hết, kèm vé + vị trí ổ C + tên máy", job["id"] == oid and job["os"] == "1511" and job["wipe"] == "all" and len(job["ticket"]) == 32
   and job["win"] == {"offset": ssd_win.offset, "size": ssd_win.size} and job["name"] == "CB-TEST01" and job["state"] == "queued" and job["tries"] == 1, job)
sb = sysbcd(fs)
ck("đặt khởi động 1 LẦN vào bộ cài, mục BCD trỏ đúng phân vùng cứu hộ (không cần chữ ổ)", sb.get("bootsequence") == C.PE_GUID
   and sb["entries"][C.PE_GUID]["device"].startswith("ramdisk=[\\Device\\HarddiskVolume") and rec.vol.letter is None, sb)
ck("hẹn khởi động lại 30 giây, lệnh trên web vẫn 'đang giao'", host.powers == [("reboot", 30)] and q(f"select state from pc_orders where id = {oid}") == "sent")
boot_pe(fs)
rc = cb_pe.Installer(fs).run(ScriptUI())
ck("bộ cài (trong RAM) làm lệnh xong", rc == 0)
ck("ổ hệ thống + ổ phụ sạch dữ liệu khách cũ", not any("mat-khau" in k for d in fs.fdisks for p in d.slots if p.vol for k in p.vol.files) and not hdd.slots[0].vol.files)
boot_windows(fs)
host2 = FakeHost(fs)
ag = agent(fs, net, host2)
ck("Windows 1511 mới: chưa có mã máy, có vé trong seed.json", ag.ident is None and json.loads(fs.file("C", "cloudbluepc\\seed.json")).get("ticket") == job["ticket"])
ag.tick()
ck("đăng ký lại bằng vé → mã máy MỚI, vẫn là máy cũ trên web", ag.ident and ag.ident["id"] == PC and ag.ident["token"] != old_token, ag.logs)
ck("mã máy cũ (khách cũ có thể đã chép) hết dùng", json.loads(q(f"select pc_poll('{PC}', '{old_token}')", role="anon", ip=net.ip))["err"] == "BAD_TOKEN")
ck("vé đã dùng bị xoá khỏi máy", "ticket" not in fs.file("C", "cloudbluepc\\seed.json"))
ag.tick()
o = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid}"))
ck("Windows mới báo lệnh XONG về web, kèm thời gian", o["state"] == "done" and o["result"]["os"] == "1511" and "ticket" not in o["args"], o)
ck("web thấy máy giờ chạy 1511, tên + duyệt giữ nguyên", q(f"select os || '|' || name || '|' || approved from pc_machines where id = '{PC}'") == "1511|Máy 14-85|true")
ck("kết quả trên phân vùng cứu hộ đã dọn", "cb\\job-result.json" not in rec.vol.files and "cb\\job.json" not in rec.vol.files)
ck("nhịp sau: không còn gì để báo", ag.tick() == 30 and ag.pending_done is None)

print("5. Đổi Windows cho khách đang thuê — chỉ phân vùng Windows, giữ ổ phụ")
hdd.slots[0].vol.put("game\\save.dat", "cua khach dang thue")
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"22h2\", \"wipe\": \"system\"}}'))", **A))["id"]
ag.tick(); boot_pe(fs)
rc = cb_pe.Installer(fs).run(ScriptUI())
boot_windows(fs); ag = agent(fs, net, FakeHost(fs)); ag.tick(); ag.tick()
ck("xong: về 22H2, ổ phụ của khách còn nguyên", rc == 0 and q(f"select state from pc_orders where id = {oid}") == "done" and q(f"select os from pc_machines where id = '{PC}'") == "22h2"
   and hdd.slots[0].vol.files.get("game\\save.dat") == "cua khach dang thue")

print("6. Máy không vào được bộ cài (firmware bỏ qua khởi động 1 lần) → không lặp mãi")
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"1511\"}}'))", **A))["id"]
host = FakeHost(fs); ag = agent(fs, net, host); ag.tick()
ck("lần 1: ghi lệnh + khởi động lại", host.powers == [("reboot", 30)] and json.loads(rec.vol.files["cb\\job.json"])["tries"] == 1)
boot_windows(fs); host = FakeHost(fs); ag = agent(fs, net, host); ag.tick()      # máy lại lên Windows cũ
ck("lần 2: thử lại 1 lần nữa", host.powers == [("reboot", 30)] and json.loads(rec.vol.files["cb\\job.json"])["tries"] == 2)
boot_windows(fs); host = FakeHost(fs); ag = agent(fs, net, host); ag.tick(); ag.tick()
o = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid}"))
ck("lần 3: thôi — báo lỗi về web, gỡ lệnh, KHÔNG khởi động lại nữa", o["state"] == "failed" and "USB" in o["result"]["msg"] and not host.powers and "cb\\job.json" not in rec.vol.files, o)

print("7. Lệnh không làm được → báo lỗi rõ, không khởi động lại")
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"win7\"}}'))", **A))["id"]
host = FakeHost(fs); ag = agent(fs, net, host); ag.tick(); ag.tick()
o = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid}"))
ck("bản Windows không có trong máy → failed + lý do", o["state"] == "failed" and "win7" in o["result"]["msg"] and not host.powers, o)
fs2 = FakeSys("uefi"); d2 = fs2.disk(0, 240, ssd=True, style="gpt"); d2.add(260, GPT_ESP, "FAT32"); d2.add(0, GPT_DATA, "NTFS", "Windows", "C", files={"windows\\system32\\config\\system": b"x"})
r2 = json.loads(q(f"select pc_enroll('{'c' * 64}', '{{\"host\": \"KHONG-CUU-HO\"}}', '{KEY}')", role="anon", ip=net.ip))
fs2.file  # máy không có phân vùng cứu hộ
d2.slots[1].vol.put("cloudbluepc\\identity.json", json.dumps({"id": r2["id"], "token": r2["token"], "hw": "c" * 64, "name": "x"}))
d2.slots[1].vol.put("cloudbluepc\\cb.json", "{}")
oid2 = json.loads(q(f"select row_to_json(pc_admin_order('{r2['id']}', 'reinstall', '{{\"os\": \"22h2\"}}'))", **A))["id"]
h2 = FakeHost(fs2); a2 = agent(fs2, net, h2); a2.tick(); a2.tick()
o = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid2}"))
ck("máy không có phân vùng cứu hộ → failed 'cần cài bằng USB', không khởi động lại", o["state"] == "failed" and "USB" in o["result"]["msg"] and not h2.powers, o)
ck("web biết máy này không có cứu hộ", json.loads(q(f"select info->'rec' from pc_machines where id = '{r2['id']}'")) == {"ok": False, "images": []})

print("8. Mã máy bị thu hồi (admin xoá máy / đăng ký ở nơi khác)")
host = FakeHost(fs); ag = agent(fs, net, host); ag.tick()
q(f"update pc_machines set token_hash = 'x' where id = '{PC}'")
nap = ag.tick()
ck("BAD_TOKEN → bỏ mã cũ, chuyển sang đăng ký lại", ag.ident is None and nap == 5 and json.loads(fs.file("C", "cloudbluepc\\identity.json"))["token"] == "")
ag.tick()
ck("không có mã / vé → chưa đăng ký được, chờ admin", ag.ident is None and any("Cho đăng ký lại" in l for l in ag.logs), ag.logs[-2:])
q(f"select pc_admin_allow_reenroll('{PC}', 2)", **A)
ag.tick()
ck("admin bấm 'Cho đăng ký lại' → tự đăng ký lại được", ag.ident is not None and ag.ident["id"] == PC)

print("9. Tự cập nhật agent")
BASEURL = pcagent.UPDATE_BASE + "main/winpc"
new_agent = b"# ban moi\nAGENT_VER = '20.12a'\n"; new_lib = b"# lib moi\nX = 1\n"
man = {"ver": "20.12a", "base": BASEURL, "files": {"agent/pcagent.py": hashlib.sha256(new_agent).hexdigest(), "lib/cbcore.py": hashlib.sha256(new_lib).hexdigest()}}
net.files = {BASEURL + "/agent/pcagent.py": new_agent, BASEURL + "/lib/cbcore.py": new_lib}
q("select pc_admin_settings('%s')" % json.dumps({"agent": man}), **A)
host = FakeHost(fs); ag = agent(fs, net, host)
ag.tick()
ck("tải + kiểm sha256 + chạy thử đạt → thay file, giữ bản cũ .bak, đòi khởi động lại agent", ag.restart and fs.file("C", "cloudbluepc\\agent\\pcagent.py") == new_agent.decode()
   and fs.file("C", "cloudbluepc\\agent\\pcagent.py.bak") == "a" and fs.file("C", "cloudbluepc\\lib\\cbcore.py") == new_lib.decode(), ag.logs[-3:])
ck("phân vùng cứu hộ cũng nhận bản mới", rec.vol.files.get("cb\\agent\\pcagent.py") == new_agent)
ag2 = agent(fs, net, host); ag2.tick()
ck("đã áp bản đó rồi → không tải lại (không lặp)", not ag2.restart)
bad = dict(man, ver="20.12b"); net.files[BASEURL + "/lib/cbcore.py"] = b"bi sua giua duong"
q("select pc_admin_settings('%s')" % json.dumps({"agent": bad}), **A)
ag3 = agent(fs, net, host); ag3.tick()
ck("file bị sửa giữa đường (sai sha256) → KHÔNG cập nhật", not ag3.restart and fs.file("C", "cloudbluepc\\lib\\cbcore.py") == new_lib.decode() and any("sai mã kiểm" in l for l in ag3.logs))
evil = {"ver": "66.6", "base": "https://evil.example/winpc", "files": {"agent/pcagent.py": "0" * 64}}
q("select pc_admin_settings('%s')" % json.dumps({"agent": evil}), **A)
ag4 = agent(fs, net, host); ag4.tick()
ck("nguồn không phải kho GitHub của shop → bỏ qua", not ag4.restart and any("không đúng kho" in l for l in ag4.logs))
trav = {"ver": "20.12c", "base": BASEURL, "files": {"agent/pcagent.py": man["files"]["agent/pcagent.py"], "../../Windows/System32/x.py": "0" * 64}}
q("select pc_admin_settings('%s')" % json.dumps({"agent": trav}), **A)
ag5 = agent(fs, net, host); ag5.tick()
ck("tên file lạ / thoát thư mục → bỏ cả bản", not ag5.restart and any("không hợp lệ" in l for l in ag5.logs))
net.files[BASEURL + "/lib/cbcore.py"] = new_lib
good2 = dict(man, ver="20.12d"); q("select pc_admin_settings('%s')" % json.dumps({"agent": good2}), **A)
host.check_ok = False
ag6 = agent(fs, net, host); ag6.tick()
ck("bản mới chạy thử KHÔNG đạt → giữ bản cũ", not ag6.restart and any("chạy thử không đạt" in l for l in ag6.logs))
q("select pc_admin_settings('{\"agent\": {}}')", **A)

print("10. Đọc SMBIOS + dấu phần cứng")
def smb_struct(typ, body, strs):
    b = bytes([typ, 4 + len(body), 0, 0]) + body
    return b + (b"".join(s.encode() + b"\0" for s in strs) + b"\0" if strs else b"\0\0")
t1 = smb_struct(1, bytes([1, 2, 0, 3]) + bytes(range(16)) + bytes([6, 0, 0]), ["HUANANZHI", "X99", "SN-SYS-1"])
t2 = smb_struct(2, bytes([1, 2, 0, 3]), ["HUANANZHI", "X99-TF", "BS-778899"])
t0 = smb_struct(0, bytes(20), ["AMI", "5.11"])
table = t0 + t1 + t2 + smb_struct(127, b"", [])
raw = bytes([0, 3, 0, 0]) + len(table).to_bytes(4, "little") + table
sm = pcagent.parse_smbios(raw)
ck("đọc đúng hãng, tên máy, serial, UUID, bo mạch", sm == {"uuid": bytes(range(16)).hex(), "sys_serial": "SN-SYS-1", "board_serial": "BS-778899", "vendor": "HUANANZHI", "product": "X99", "board": "HUANANZHI X99-TF"}, sm)
ck("bảng rỗng / hỏng không làm sập", pcagent.parse_smbios(b"")["uuid"] == "" and pcagent.parse_smbios(b"\0" * 9)["uuid"] == "" and pcagent.parse_smbios(raw[:30]) is not None)
h1 = pcagent.hw_id(sm, "S466NX0M123456", "Samsung 970"); h2_ = pcagent.hw_id(sm, "S466NX0M999999", "Samsung 970")
ck("2 máy cùng bo mạch 'UUID mặc định' nhưng khác ổ → dấu khác nhau; cùng máy → dấu giống", h1 != h2_ and h1 == pcagent.hw_id(dict(sm), " s466nx0m123456 ", "SAMSUNG 970") and len(h1) == 64)

print("11. Hạn thuê: máy nhận hạn, báo trước cho khách, hết hạn tự tắt, bật lại cũng tự tắt (cần SQL v42)")
q("delete from sec_alerts where kind like 'pc\\_%'")
def rented_machine(serial, name):
    """Cài 1 máy mới từ USB, Windows lên, agent đăng ký, admin duyệt. Trả (fs, net, host, agent, mã số máy)."""
    fs = FakeSys("uefi"); H.usb(fs, H.cfg0(), key=KEY)
    fs.disk(0, 480, bus=17, model="Samsung 970 EVO", ssd=True, style="raw", serial=serial)
    fs.disk(5, 64, bus=7, removable=False, model="WD Elements USB", style="mbr")          # ổ cứng gắn ngoài qua USB
    assert cb_pe.Installer(fs).run(ScriptUI()) == 0
    fs.fdisks = [d for d in fs.fdisks if d.index != 9]
    boot_windows(fs)
    net, host = SqlNet(), FakeHost(fs, name); host.msgs = []
    ag = agent(fs, net, host); ag.tick()
    pc = ag.ident["id"]
    q(f"select pc_admin_set('{pc}', '{{\"approved\": true}}')", **A)
    return fs, net, host, ag, pc
def al(kind): return json.loads(q(f"select coalesce(json_agg(msg order by id), '[]') from sec_alerts where kind = '{kind}'"))
def rentjson(fs): return json.loads(fs.file("C", "cloudbluepc\\rent.json") or "{}")
fs, net, host, ag, PCR = rented_machine("RENT0001", "CB-THUE01")
nap = ag.tick()
ck("chưa đặt hạn → agent không làm gì thêm; status.txt ghi 'khong dat han'", ag.rent.get("until") is None and host.msgs == [] and not host.powers and nap == 30
   and "Han thue: khong dat han" in (fs.file("C", "cloudbluepc\\os\\status.txt") or ""), (ag.rent, nap))
ck("thông tin gửi web không tính ổ cứng gắn ngoài (USB) → cắm / rút ổ ngoài không bị coi là đổi phần cứng",
   [d["bus"] for d in json.loads(q(f"select info->'disks' from pc_machines where id = '{PCR}'"))] == ["NVMe"], q(f"select info->'disks' from pc_machines where id = '{PCR}'"))
q(f"select pc_admin_rent('{PCR}', '{{\"add_hours\": 30, \"renter\": \"anh Teo\"}}')", **A)
nap = ag.tick()
srv_now = int(q("select floor(extract(epoch from now()))"))
ck("admin cho thuê 30 giờ → máy nhận hạn (giây epoch theo giờ MÁY CHỦ) + ghi rent.json; còn hơn 1 ngày nên chưa báo gì", abs(ag.rent["until"] - srv_now - 108000) < 10
   and rentjson(fs)["until"] == ag.rent["until"] and host.msgs == [] and abs(ag.rent["skew"] - (srv_now - fs.clock)) < 10, (ag.rent, host.msgs))
ck("đồng hồ máy lệch xa giờ máy chủ vẫn tính đúng thời gian còn lại (độ lệch đo lại mỗi lần hỏi máy chủ)", abs((ag.rent["until"] - ag.rent_est()) - 108000) < 10)
import re as _re
ck("status.txt ghi thời gian còn lại (làm tròn giờ)", _re.search(r"Han thue: con 1 ngay [56] gio", fs.file("C", "cloudbluepc\\os\\status.txt")), fs.file("C", "cloudbluepc\\os\\status.txt"))
net.down = True
fs.clock += 108000 - 86000; ag.tick()
ck("MẤT MẠNG vẫn đếm: còn dưới 1 ngày → hộp thông báo cho khách (1 lần)", len(host.msgs) == 1 and "con 23 gio" in host.msgs[0] and "HET HAN THUE" in host.msgs[0], host.msgs)
ag.tick(); fs.clock += 3000; ag.tick()
ck("chưa tới mốc kế (1 giờ) → không báo lặp", len(host.msgs) == 1)
fs.clock += 86000 - 3000 - 3500; nap = ag.tick()
ck("còn dưới 1 giờ → báo lần 2; nghỉ không quá lúc tới mốc 10 phút", len(host.msgs) == 2 and "con 58 phut" in host.msgs[1] and nap <= 300, (host.msgs, nap))
fs.clock += 3500 - 590; ag.tick(); fs.clock += 590 - 50; nap = ag.tick()
ck("còn 10 phút và 1 phút → báo tiếp; sát giờ thì nhịp ngắn lại", len(host.msgs) == 4 and "con 9 phut" in host.msgs[2] and "giay" in host.msgs[3] and nap <= 50, (host.msgs, nap))
ck("chưa hết hạn → chưa tắt máy", not host.powers)
fs.clock += 51; nap = ag.tick()
ck("HẾT HẠN (đang mất mạng) → báo khách 'tu tat sau 60 giay' + cho Windows ĐẾM NGƯỢC 60 giây (lời nhắn của chính Windows, không cần msg.exe)", len(host.msgs) == 5 and "da HET HAN THUE" in host.msgs[4]
   and host.powers == [("shutdown", 60)] and nap <= 5 and ag.events == [{"k": "rent_off"}], (host.msgs[-1], host.powers, nap, ag.events))
fs.clock += 30; nap = ag.tick()
ck("trong 60 giây chờ → chưa ra lệnh tắt ngay, không đếm ngược lặp", host.powers == [("shutdown", 60)] and nap <= 15)
fs.clock += 31; ag.tick()
ck("hết 60 giây → agent ra lệnh TẮT NGAY (khách có huỷ lệnh đếm ngược cũng không thoát), ghi mốc 'off'", host.powers == [("shutdown", 60), ("shutdown", 0)] and rentjson(fs).get("off"), (host.powers, rentjson(fs)))
fs.clock += 60; ag.tick()
ck("máy chưa tắt hẳn → chưa ra lệnh lặp ngay", len(host.powers) == 2)
fs.clock += 70; ag.tick()
ck("2 phút sau máy vẫn chạy (lệnh tắt bị chặn) → ra lệnh tắt lại", host.powers == [("shutdown", 60), ("shutdown", 0), ("shutdown", 0)], host.powers)

print("12. Máy hết hạn bị BẬT LẠI + gia hạn")
fs.rebooted = False; host.powers.clear(); host.msgs.clear()
ag2 = agent(fs, net, host)                                           # máy khởi động lại: agent mới, đọc rent.json cũ
nap = ag2.tick()
ck("bật lại lúc đã hết hạn, CHƯA hỏi được máy chủ → chờ (tối đa 3 phút) chứ chưa tắt", not host.powers and host.msgs == [] and nap == 10, (nap, host.msgs))
fs.clock += 100; ag2.tick()
ck("vẫn trong 3 phút chờ", not host.powers and host.msgs == [])
fs.clock += 90; ag2.tick()
ck("quá 3 phút vẫn không có mạng → báo khách + đếm ngược tắt, ghi việc lạ 'bật lại khi hết hạn'", len(host.msgs) == 1 and ag2.events == [{"k": "rent_boot"}] and host.powers == [("shutdown", 60)], (host.msgs, ag2.events, host.powers))
fs.clock += 61; ag2.tick()
ck("→ tắt lại", host.powers == [("shutdown", 60), ("shutdown", 0)])
fs.rebooted = False; host.powers.clear(); host.msgs.clear(); net.down = False
q(f"update pc_machines set rent_until = now() - interval '2 hours' where id = '{PCR}'")       # máy chủ: hạn đã qua 2 giờ, máy đã tự tắt 1 lần lúc hết hạn
u_old = int(q(f"select floor(extract(epoch from rent_until)) from pc_machines where id = '{PCR}'"))
next(x for _, _, x in fs._allvols() if x.letter == "C").put("cloudbluepc\\rent.json", json.dumps(dict(rentjson(fs), until=u_old, off=u_old + 60)))
ag3 = agent(fs, net, host)
nap = ag3.tick()
ck("bật lại, CÓ mạng, máy chủ xác nhận vẫn hết hạn → báo khách ngay (không cần chờ 3 phút)", len(host.msgs) == 1 and ag3.events == [{"k": "rent_boot"}] and nap <= 5, (host.msgs, ag3.events, nap))
ag3.tick()
ck("việc 'bật lại khi hết hạn' đã báo về web → có cảnh báo cho admin", ag3.events == [] and len(al("pc_rent_boot")) == 1 and "BẬT LẠI" in al("pc_rent_boot")[0], al("pc_rent_boot"))
q(f"select pc_admin_rent('{PCR}', '{{\"add_hours\": 48}}')", **A)       # admin gia hạn đúng lúc máy đang đếm 60 giây
n_ab = host.aborts
fs.clock += 61; ag3.tick()
ck("được GIA HẠN trong lúc Windows đang đếm ngược tắt máy → HUỶ lệnh tắt (shutdown /a), không tắt nữa, xoá mốc 'off'", host.powers == [("shutdown", 60)] and host.aborts == n_ab + 1 and "off" not in rentjson(fs)
   and ag3.rent_call is None and any("huỷ lệnh tắt máy" in x for x in ag3.logs), (host.powers, host.aborts, rentjson(fs)))
ck("gia hạn xong còn 2 ngày → không báo gì thêm cho khách", len(host.msgs) == 1)
q(f"update pc_machines set rent_until = now() - interval '1 second' where id = '{PCR}'")
nap = ag3.tick()
ck("hết hạn lúc máy ĐANG CHẠY + có mạng → việc lạ là 'rent_off' (không phải bật lại)", ag3.events == [{"k": "rent_off"}] and nap <= 5, ag3.events)
ag3.tick()
row = json.loads(q(f"select row_to_json(m) from pc_machines m where id = '{PCR}'"))
ck("web nhận tin máy tự tắt vì hết hạn: ghi rent_off_at + cảnh báo 'máy đã tự tắt' có tên máy và tên khách", row["rent_off_at"] and len(al("pc_rent_end")) == 1
   and "máy đã tự tắt" in al("pc_rent_end")[0] and "«CB-THUE01»" in al("pc_rent_end")[0] and "anh Teo" in al("pc_rent_end")[0], al("pc_rent_end"))
fs.clock += 61; ag3.tick()
ck("→ tắt máy", host.powers[-2:] == [("shutdown", 60), ("shutdown", 0)] and host.powers.count(("shutdown", 0)) == 1, host.powers)
fs.rebooted = False; host.powers.clear(); host.msgs.clear()
q(f"select pc_admin_rent('{PCR}', '{{\"add_hours\": 72}}')", **A)       # chủ shop gia hạn lúc máy đang TẮT
ag4 = agent(fs, net, host); nap = ag4.tick()
ck("gia hạn lúc máy đang tắt → bật lên máy hỏi máy chủ, thấy còn hạn → chạy bình thường", not host.powers and host.msgs == [] and nap == 30 and ag4.events == [] and "off" not in ag4.rent, (nap, host.msgs, ag4.rent))
q(f"select pc_admin_rent('{PCR}', '{{\"until\": null}}')", **A); ag4.tick()
ck("admin bỏ hạn → máy thôi đếm", ag4.rent.get("until") is None and "Han thue: khong dat han" in fs.file("C", "cloudbluepc\\os\\status.txt"))

print("13. Chỉnh lùi đồng hồ để lách hạn thuê + việc lạ về bảo mật")
q(f"select pc_admin_rent('{PCR}', '{{\"add_hours\": 3}}')", **A); ag4.tick()
host.msgs.clear(); net.down = True
fs.clock += 3600; ag4.tick()                                         # mất mạng 1 giờ → còn 2 giờ
left1 = ag4.rent["until"] - ag4.rent_est()
fs.clock -= 6 * 3600                                                 # khách (có quyền Admin) chỉnh đồng hồ lùi 6 giờ
ag4.tick()
left2 = ag4.rent["until"] - ag4.rent_est()
ck("đồng hồ bị chỉnh lùi 6 giờ lúc mất mạng → thời gian còn lại KHÔNG tăng thêm", abs(left1 - left2) < 5 and 7100 < left2 <= 7200, (left1, left2))
ck("ghi việc lạ 'clock' kèm số giây bị lùi", [e for e in ag4.events if e["k"] == "clock" and -21700 < e["d"] < -21500], ag4.events)
fs.clock += 7200 + 5; ag4.tick(); fs.clock += 61; ag4.tick()
ck("hết 2 giờ (tính nối tiếp) → vẫn tắt đúng hạn", host.powers == [("shutdown", 60), ("shutdown", 0)], host.powers)
fs.rebooted = False; host.powers.clear(); net.down = False
q(f"select pc_admin_rent('{PCR}', '{{\"add_hours\": 100}}')", **A)
ag4.event("sec", m="tai khoan khach 'PC' co lai quyen Admin - da ha lai")
ag4.tick()
ck("có mạng lại → việc lạ được báo: cảnh báo đồng hồ + cảnh báo ĐỎ về bảo mật", ag4.events == [] and len(al("pc_clock")) == 1 and "LÙI" in al("pc_clock")[0] and len(al("pc_sec")) == 1
   and "co lai quyen Admin" in al("pc_sec")[0] and q("select level from sec_alerts where kind = 'pc_sec'") == "crit", (ag4.events, al("pc_clock"), al("pc_sec")))
ck("máy chủ là chuẩn: hỏi được máy chủ thì độ lệch đồng hồ được đo lại — còn đúng 3 giờ cũ (theo giờ máy chủ) + 100 giờ gia hạn",
   abs((ag4.rent["until"] - ag4.rent_est()) - 103 * 3600) < 15, ag4.rent["until"] - ag4.rent_est())
ev = "C:\\CloudBluePC"
class OldNet(SqlNet):                                                # máy chủ CHƯA chạy SQL v42: câu trả lời không có mục rent
    def rpc(self, fn, body, timeout=20):
        r = super().rpc(fn, body, timeout)
        if isinstance(r, dict): r.pop("rent", None)
        return r
fs5, net5, host5, ag5r, PC5 = rented_machine("RENT0005", "CB-THUE05")
ag5r.net = OldNet(); ag5r.tick(); ag5r.tick()
ck("máy chủ chưa có phần hạn thuê (SQL cũ) → agent bản mới vẫn chạy bình thường, không đếm gì", ag5r.rent.get("until") is None and not host5.powers and host5.msgs == [])
ck("span_txt", [pcagent.span_txt(x) for x in (0, 59, 60, 3599, 3600, 3660, 86399, 86400, 90000, 200000)]
   == ["0 giay", "59 giay", "1 phut", "59 phut", "1 gio", "1 gio 1 phut", "23 gio 59 phut", "1 ngay", "1 ngay 1 gio", "2 ngay 7 gio"])

print("14. Đồng hồ máy lệch giờ máy chủ → agent chỉnh lại (bản Windows tuỳ biến hay lệch đúng 1 giờ sau khi cài)")
srv = lambda: int(q("select floor(extract(epoch from now()))"))
fs6, net6, host6, ag6, PC6 = rented_machine("CLOCK006", "CB-GIO06")
ag6.tick()                                                           # nhịp báo sống đầu tiên: đồng hồ giả (năm 2027) lệch xa giờ máy chủ
ck("(bộ thử) Windows từ chối đổi giờ → agent ghi nhật ký rồi chạy tiếp", len(host6.clock_tries) == 1 and any("KHÔNG chỉnh được" in x for x in ag6.logs) and not ag6.events, (host6.clock_tries, ag6.logs[-3:]))
ag6.tick(); fs6.clock += 300; ag6.tick()
ck("trong 10 phút không thử lại", len(host6.clock_tries) == 1)
fs6.clock += 400; ag6.tick()
ck("quá 10 phút → thử lại", len(host6.clock_tries) == 2)
host6.clock_ok = True; host6.clock_tries.clear(); fs6.clock = srv() - 3600; ag6.clock_at = None; ag6.logs.clear()
ag6.tick()
ck("đồng hồ máy CHẬM 1 giờ → đặt lại đúng giờ máy chủ, ghi nhật ký, không coi là việc lạ", len(host6.clock_tries) == 1 and abs(host6.clock_tries[0] - srv()) < 10 and abs(fs6.clock - srv()) < 10
   and any("đã chỉnh lại theo máy chủ" in x and "+36" in x for x in ag6.logs) and not ag6.events, (host6.clock_tries, ag6.logs))
ag6.clock_at = None; ag6.tick()
ck("đồng hồ đã đúng → không đụng nữa", len(host6.clock_tries) == 1)
fs6.clock = srv() + 90; ag6.clock_at = None; ag6.tick()
ck("lệch 90 giây (dưới ngưỡng 2 phút) → để yên", len(host6.clock_tries) == 1 and abs(fs6.clock - srv() - 90) < 10)
q(f"select pc_admin_rent('{PC6}', '{{\"add_hours\": 0.5}}')", **A)
fs6.clock = srv() + 3600; ag6.clock_at = None; host6.msgs.clear(); ag6.tick()
left = ag6.rent["until"] - ag6.rent_est()
ck("đồng hồ máy NHANH 1 giờ + máy còn 30 phút thuê: chỉnh lùi về đúng giờ, hạn thuê vẫn còn 30 phút, KHÔNG báo nhầm 'chỉnh lùi đồng hồ', không tắt máy",
   len(host6.clock_tries) == 2 and abs(fs6.clock - srv()) < 10 and 1700 < left <= 1800 and not [e for e in ag6.events if e["k"] == "clock"] and not host6.powers
   and len(host6.msgs) == 1 and _re.search(r"con (29|30) phut", host6.msgs[0]), (left, ag6.events, host6.powers, host6.msgs, host6.clock_tries))
fs6.clock += 60; ag6.tick()
ck("nhịp sau vẫn không có việc lạ về đồng hồ", not [e for e in ag6.events if e["k"] == "clock"] and len(al("pc_clock")) == 1)       # 1 = cảnh báo cũ của mục 13
C6 = next(x for _, _, x in fs6._allvols() if x.letter == "C")
cfg6 = json.loads(fs6.file("C", "cloudbluepc\\cb.json")); cfg6["clock_fix"] = False; C6.put("cloudbluepc\\cb.json", json.dumps(cfg6))
ag7 = agent(fs6, net6, host6); host6.clock_tries.clear(); fs6.clock = srv() - 7200; ag7.tick(); ag7.tick()
ck('cb.json "clock_fix": false → agent không bao giờ đụng đồng hồ', host6.clock_tries == [] and abs(fs6.clock - (srv() - 7200)) < 30)

print("15. Máy mới cài KHÔNG có mạng: status.txt ghi đúng + hiện hộp báo tại máy")
fs8 = FakeSys("uefi"); H.usb(fs8, H.cfg0(), key=KEY)
fs8.disk(0, 480, bus=17, model="Samsung 970 EVO", ssd=True, style="raw", serial="NONET008")
assert cb_pe.Installer(fs8).run(ScriptUI()) == 0
fs8.fdisks = [d for d in fs8.fdisks if d.index != 9]; boot_windows(fs8)
net8, host8 = SqlNet(), FakeHost(fs8, "CB-KOMANG"); net8.down = True; host8.ip = ""
ag8 = agent(fs8, net8, host8); ag8.tick()
st8 = fs8.file("C", "cloudbluepc\\os\\status.txt") or ""
ck("chưa đăng ký + không gọi được máy chủ → status.txt ghi 'CHUA DUOC' kèm lý do (trước đây ghi nhầm 'duoc')", "Dang ky voi he thong: CHUA" in st8 and "Ket noi may chu: CHUA DUOC - " in st8 and "Ket noi may chu: duoc" not in st8, st8)
ck("status.txt có dòng mạng LAN: không có địa chỉ IP → nhắc kiểm tra dây mạng / driver card mạng", "Mang LAN: KHONG CO dia chi IP - kiem tra day mang / driver card mang" in st8, st8)
ck("mới chạy chưa tới 2,5 phút → chưa hiện hộp báo", host8.msgs == [])
fs8.clock += 160; ag8.tick()
ck("quá 2,5 phút vẫn không có IP → hiện 1 hộp báo tại máy: CHUA CO MANG, kiểm tra dây mạng / driver card mạng", len(host8.msgs) == 1 and "CHUA CO MANG" in host8.msgs[0] and "driver card mang" in host8.msgs[0] and host8.msgs[0].isascii(), host8.msgs)
fs8.clock += 900; ag8.tick(); fs8.clock += 900; ag8.tick()
ck("không báo lặp", len(host8.msgs) == 1)
host8.ip = "192.168.1.88"; ag8.tick()
ck("có IP nhưng chưa tới được máy chủ → status.txt ghi có IP, vẫn 'CHUA DUOC'", "Mang LAN: co - dia chi IP 192.168.1.88" in fs8.file("C", "cloudbluepc\\os\\status.txt") and "CHUA DUOC" in fs8.file("C", "cloudbluepc\\os\\status.txt"))
ag9 = agent(fs8, net8, host8); host8.msgs.clear(); fs8.clock += 400; ag9.tick()
ck("máy có IP mà máy chủ chưa tới được (mạng nội bộ chưa ra ngoài) → không hiện hộp 'chưa có mạng'", host8.msgs == [])
net8.down = False; ag9.tick(); ag9.tick()
st8 = fs8.file("C", "cloudbluepc\\os\\status.txt")
ck("có mạng lại → đăng ký được, status.txt ghi 'ROI' + 'duoc'", ag9.ident and "Dang ky voi he thong: ROI" in st8 and "Ket noi may chu: duoc" in st8, st8)
import tempfile as _tf
with _tf.TemporaryDirectory() as tb:
    os.makedirs(os.path.join(tb, "logs"))
    r0 = pcagent.vga_pending(tb)
    res = []
    for body in ('{"state": "wait", "tries": 0}', '{"state": "fail", "tries": 1}', '{"state": "done", "tries": 1}', '{"state": "gave-up", "tries": 3}', '{"state": "skip"}', "khong phai json", "[1]"):
        open(os.path.join(tb, "logs", "vga.json"), "w").write(body); res.append(pcagent.vga_pending(tb))
    ck("vga_pending: chỉ 'wait' / 'fail' là còn việc (agent gọi lại cb_provision khi máy có mạng); file hỏng → không", r0 is False and res == [True, True, False, False, False, False, False], (r0, res))

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
