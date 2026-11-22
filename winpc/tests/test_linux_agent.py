# -*- coding: utf-8 -*-
"""Thử agent CachyOS (linux/cbagent.py) NỐI CHUỖI với SQL thật (Postgres, như test_agent.py): máy Windows đổi sang CachyOS bằng lệnh cài lại
   → agent Linux đăng ký lại bằng vé của lệnh, báo kết quả lần cài, nhận lệnh cài lại về Windows (ghi job.json lên phân vùng cứu hộ giả + BootNext),
   hạn thuê, công tắc quyền Admin, tự cập nhật.  Chạy: python3 tests/test_linux_agent.py"""
import hashlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WINPC = os.path.join(HERE, "..")
for p in ("lib", "agent", "linux"): sys.path.insert(0, os.path.join(WINPC, p))
import cbcore as C                                    # noqa: E402
import cbagent                                        # noqa: E402
import pcagent                                        # noqa: E402

PSQL = ["psql", "-h", "127.0.0.1", "-p", "55432", "-U", "postgres", "-d", "pctest", "-X", "-At", "-v", "ON_ERROR_STOP=1"]
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:500])


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
    last_err = ""

    def __init__(self, ip="1.54.69.205"):
        self.ip, self.calls, self.files = ip, [], {}

    def rpc(self, fn, body, timeout=20):
        self.calls.append((fn, body))
        args = ", ".join("%s := %s" % (k, lit(v)) for k, v in body.items())
        return json.loads(q("select %s(%s)" % (fn, args), role="anon", ip=self.ip))

    def get(self, url, timeout=60, limit=8 << 20):
        if url not in self.files: raise OSError("404 " + url)
        return self.files[url]


class FakeHost(cbagent.LinuxHost):
    """Máy CachyOS giả: ghi lại các việc (tắt / khởi động lại, hộp báo, tự đăng nhập), không đụng máy thật."""
    def __init__(self, user="pc"):
        super().__init__(user)
        self.powers, self.msgs, self.autologons, self.aborts, self.codes, self.check_ok = [], [], [], 0, [], True
    def hostname(self): return "CB-LNX01"
    def os_ver(self): return "rolling 7.1.6-1-cachyos"
    def os_name(self): return "CachyOS Linux"
    def cpu(self): return ("AMD Ryzen 5 5600X 6-Core Processor", 12)
    def ram_gb(self): return 31.2
    def gpus(self): return ["NVIDIA GeForce RTX 3060"]
    def lan_ip(self): return "192.168.1.88"
    def uptime(self): return 321
    def smbios(self): return {"uuid": "u1", "board_serial": "BS9", "sys_serial": "S9", "vendor": "ASUS", "product": "PRIME", "board": "ASUS PRIME B550M"}
    def power(self, reboot=True, delay=5, msg=""): self.powers.append(("reboot" if reboot else "shutdown", delay, msg))
    def abort_shutdown(self): self.aborts += 1
    def autologon(self, on): self.autologons.append(bool(on)); return True
    def set_clock(self, epoch): return False
    def show_code(self, code): self.codes.append(code); return True
    def notify(self, text, secs=60): self.msgs.append(text)
    def selfcheck(self, script): return (self.check_ok, "" if self.check_ok else "loi")


class FakeRec(cbagent.LinuxRec):
    """Phân vùng cứu hộ giả = 1 thư mục tạm (không mount thật)."""
    def __init__(self, root):
        super().__init__("1234567890ABCDEF"); self.root = root.rstrip("/") + "/"; self.mounts = []
    def mount(self, rw=False): self.mounts.append(rw); return self.root
    def umount(self): pass


EFI_CALLS = []
_sh = cbagent.sh
def fake_sh(argv, timeout=60, input=None):
    a = [str(x) for x in argv]
    if a[0] == "efibootmgr": EFI_CALLS.append(a); return 0, ""
    if a[:2] == ["id", "-nG"]: return 0, " ".join(GROUPS)
    if a[0] == "gpasswd":
        (GROUPS.append("wheel") if a[1] == "-a" else GROUPS.remove("wheel")) if (a[1] == "-a") != ("wheel" in GROUPS) else None
        return 0, ""
    return _sh(argv, timeout, input)
GROUPS = ["pc", "users", "video"]
cbagent.sh = fake_sh
EFIV = tempfile.mkdtemp(); cbagent.EFIVARS = EFIV                   # biến UEFI giả (thư mục tạm) — KHÔNG BAO GIỜ đụng NVRAM thật của máy chạy thử
GUID = "8be4df61-93ca-11d2-aa0d-00e098032b8c"
def efiv(name):
    try: return open(os.path.join(EFIV, "%s-%s" % (name, GUID)), "rb").read()
    except OSError: return None
_efi_find = cbagent.efi_find
cbagent.efi_find = lambda desc: 0x0001 if desc == "Windows Boot Manager" else None
cbagent.root_hint = lambda: {"offset": 6548357120, "size": 40696266240}

# ---------------------------------------------------------------- CSDL + máy Windows có sẵn trên web
q("truncate pc_orders, pc_machines, pc_rl restart identity cascade")
q("update pc_settings set enroll_hash = null, auto_approve = true, agent = '{}'::jsonb, poll_s = 30")
q("do $$ begin if exists (select 1 from information_schema.columns where table_name = 'pc_settings' and column_name = 'cust_admin') "
  "then update pc_settings set cust_admin = false where id = 1; end if; end $$")
ADMIN = q("select id from profiles where role = 'admin' limit 1")
A = dict(role="authenticated", uid=ADMIN)
KEY = q("select pc_admin_new_key()", **A)
HW = hashlib.sha256(b"may-linux-1").hexdigest()
net = SqlNet()
w = net.rpc("pc_enroll", {"p_hw": HW, "p_info": {"host": "CB-LNX01", "os": "22h2", "os_ver": "10.0.19045.3803"}, "p_key": KEY})
PC = w["id"]
oid = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"cachyos\", \"wipe\": \"all\"}}'))", **A))["id"]
r = net.rpc("pc_poll", {"p_id": PC, "p_token": w["token"], "p_info": None, "p_done": None})         # agent Windows nhận lệnh (rồi khởi động lại vào WinPE)
TICKET = (r.get("order") or {}).get("args", {}).get("ticket")
print("1. Máy Windows nhận lệnh đổi sang CachyOS → WinPE + cb-install.sh cài xong → agent Linux chạy lần đầu")
ck("máy chủ giao lệnh reinstall os=cachyos kèm vé 1 lần", r.get("order", {}).get("cmd") == "reinstall" and r["order"]["args"]["os"] == "cachyos" and len(TICKET or "") >= 20, r)

tmp = tempfile.mkdtemp(); base = os.path.join(tmp, "opt"); recd = os.path.join(tmp, "rec")
os.makedirs(base); os.makedirs(os.path.join(recd, "cb", "linux")); os.makedirs(os.path.join(recd, "cb", "boot")); os.makedirs(os.path.join(recd, "cb", "images"))
rcfg = {"ver": "22.11c", "default": "22h2", "user": "PC", "password": "", "sb_url": "x", "sb_key": "x",
        "images": [{"id": "22h2", "file": "cb\\images\\22h2.wim", "index": 6}, {"id": "1511", "file": "cb\\images\\1511.wim", "index": 1},
                   {"id": "cachyos", "kind": "linux", "file": "cb\\linux\\cachyos.iso"}]}
def put(rel, data):
    p = os.path.join(recd, *rel.split("\\")); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb" if isinstance(data, bytes) else "w") as f: f.write(data)
put("cb\\cb.json", json.dumps(rcfg))
for rel in ("cb\\boot\\boot.wim", "cb\\boot\\boot.sdi", "cb\\images\\22h2.wim", "cb\\images\\1511.wim", "cb\\linux\\cachyos.iso", "cb\\linux\\grubx64.efi",
            "cb\\linux\\grub.cfg", "cb\\linux\\cb-install.sh", "cb\\linux\\cbagent.py"): put(rel, b"x")
put("cb\\job-result.json", json.dumps({"id": oid, "ok": True, "msg": "da cai CachyOS sau 9 phut (CB-LNX01, khach pc)", "os": "cachyos", "pe": "cb-install 22.11c", "secs": 540}))
with open(os.path.join(base, "cb.json"), "w") as f: json.dump(dict(rcfg, update_base=pcagent.UPDATE_BASE), f)
with open(os.path.join(base, "seed.json"), "w") as f: json.dump({"id": oid, "os": "cachyos", "ticket": TICKET, "hw": HW, "from": "job", "order": oid, "user": "pc"}, f)
logs = []
host, rec = FakeHost("pc"), FakeRec(recd)
ag = cbagent.LinuxAgent(cbagent.LinuxSys(), host, net, base, logs.append, rec=rec)
ag.tick(); ag.tick()
row = json.loads(q(f"select row_to_json(m) from pc_machines m where id = '{PC}'"))
ck("đăng ký lại bằng VÉ của lệnh → GIỮ đúng máy cũ trên web (cùng mã máy), vé bị xoá khỏi seed.json", ag.ident and ag.ident["id"] == PC
   and "ticket" not in json.load(open(os.path.join(base, "seed.json"))), (ag.ident, logs[-4:]))
ck("web thấy máy chạy CachyOS: os=cachyos, agent bản Linux, CPU / RAM / GPU / IP", row["os"] == "cachyos" and row["info"].get("agent") == cbagent.LINUX_VER
   and row["info"].get("linux") is True and row["info"].get("gpus") == ["NVIDIA GeForce RTX 3060"] and row["lan_ip"] == "192.168.1.88", row["info"])
ck("… phân vùng cứu hộ: đổi được sang 22h2, 1511, cachyos", row["info"].get("rec") == {"ok": True, "images": ["22h2", "1511", "cachyos"], "ver": "22.11c"}, row["info"].get("rec"))
o = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid}"))
ck("báo KẾT QUẢ lần cài CachyOS về web: lệnh #%s → done kèm lời nhắn của cb-install.sh" % oid, o["state"] == "done" and "da cai CachyOS" in (o.get("result") or {}).get("msg", ""), o)
ck("… xoá cb/job-result.json trên phân vùng cứu hộ sau khi web đã nhận (không báo lặp)", not os.path.exists(os.path.join(recd, "cb", "job-result.json")))
ck("tình trạng ghi ra /opt/cloudblue/os/status.txt", os.path.isfile(os.path.join(base, "os", "status.txt")))
st = os.stat(os.path.join(base, "identity.json"))
ck("identity.json (mã bí mật của máy) chỉ root đọc được (0600)", (st.st_mode & 0o077) == 0, oct(st.st_mode))

print("2. Đổi lại sang Windows từ web (chỉ thay hệ điều hành)")
oid2 = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"22h2\", \"wipe\": \"system\"}}'))", **A))["id"]
EFI_CALLS.clear(); ag.tick()
j = json.load(open(os.path.join(recd, "cb", "job.json")))
ck("ghi cb/job.json lên phân vùng cứu hộ: bản 22h2, wipe=system, vị trí = phân vùng Linux đang chạy, vé mới, dấu phần cứng", j.get("id") == oid2 and j.get("os") == "22h2"
   and j.get("wipe") == "system" and j.get("win") == {"offset": 6548357120, "size": 40696266240} and len(j.get("ticket") or "") >= 20 and j.get("hw") == HW
   and j.get("state") == "queued" and j.get("attempts") == 0, j)
ck("BootNext = Windows Boot Manager (Boot0001) ghi thẳng qua efivarfs: thuộc tính NV+BS+RT + số mục → WinPE cứu hộ làm lệnh",
   efiv("BootNext") == b"\x07\x00\x00\x00\x01\x00" and not EFI_CALLS, (efiv("BootNext"), EFI_CALLS))
ck("hẹn khởi động lại sau 30 giây + báo khách", host.powers and host.powers[-1][:2] == ("reboot", 30) and "CAI WINDOWS 22H2" in host.powers[-1][2], host.powers)
ck("phân vùng cứu hộ được gắn CÓ GHI chỉ lúc cần", True in rec.mounts)
os.remove(os.path.join(recd, "cb", "job.json"))

print("2b. NVRAM: đọc mục khởi động qua efivarfs · không ghi được thì dùng efibootmgr · lệnh do chính máy này cài ra · BIOS bỏ qua BootNext")
opt = C.efi_load_option("Windows Boot Manager", 1, 2048, 532480, "{11111111-2222-3333-4444-555555555555}", "\\EFI\\Microsoft\\Boot\\bootmgfw.efi")
ls = cbagent.LinuxSys()
ck("ghi / đọc lại biến UEFI qua efivarfs (Boot0003 + BootOrder)", ls.efi_set("Boot0003", opt) and ls.efi_set("BootOrder", b"\x05\x00\x03\x00")
   and ls.efi_get("Boot0003") == opt and efiv("Boot0003")[:4] == b"\x07\x00\x00\x00")
ck("tìm mục 'Windows Boot Manager' bằng cách đọc thẳng NVRAM (không cần efibootmgr)", _efi_find("Windows Boot Manager") == 3 and not EFI_CALLS, EFI_CALLS)
ck("xoá biến UEFI = xoá file trong efivarfs", ls.efi_set("Boot0003", b"") and efiv("Boot0003") is None)
EFI_CALLS.clear(); cbagent.EFIVARS = os.path.join(EFIV, "khong-co")
ok_bn = cbagent.boot_next(0x0001)
ck("efivarfs không ghi được → dùng efibootmgr -n 0001", ok_bn == (True, "") and ["efibootmgr", "-q", "-n", "0001"] in EFI_CALLS, (ok_bn, EFI_CALLS))
cbagent.EFIVARS = EFIV
h2 = FakeHost("pc"); ag2 = cbagent.LinuxAgent(cbagent.LinuxSys(), h2, net, base, logs.append, rec=rec)
ag2.handle({"cmd": "reinstall", "id": oid, "args": {"os": "cachyos", "wipe": "all"}})
ck("máy chủ giao lại đúng lệnh đã cài ra CachyOS này → báo XONG, KHÔNG cài lại", ag2.pending_done and ag2.pending_done["id"] == oid and ag2.pending_done["ok"]
   and not os.path.exists(os.path.join(recd, "cb", "job.json")) and not h2.powers, (ag2.pending_done, h2.powers))
XID = 990001
for n in (1, 2):
    ag2.pending_done = None; ag2.handle({"cmd": "reinstall", "id": XID, "args": {"os": "1511", "wipe": "all", "ticket": "v" * 24}})
    jn = json.load(open(os.path.join(recd, "cb", "job.json")))
    ck("lần %d: ghi lệnh (số lần thử = %d) + khởi động lại" % (n, n), jn.get("id") == XID and jn.get("tries") == n and ag2.pending_done is None and len(h2.powers) == n, (jn, h2.powers))
ag2.handle({"cmd": "reinstall", "id": XID, "args": {"os": "1511", "wipe": "all"}})
ck("BIOS bỏ qua BootNext 2 lần (máy vẫn về CachyOS) → gỡ lệnh + BootNext, báo LỖI rõ ràng, không khởi động lại nữa",
   ag2.pending_done and ag2.pending_done["ok"] is False and "2 lần" in ag2.pending_done["result"]["msg"] and len(h2.powers) == 2
   and not os.path.exists(os.path.join(recd, "cb", "job.json")) and efiv("BootNext") is None, (ag2.pending_done, h2.powers))
ag2.pending_done = None

print("3. Lệnh sai / thiếu file → báo lỗi về web, KHÔNG khởi động lại")
ag3 = cbagent.LinuxAgent(cbagent.LinuxSys(), FakeHost("pc"), net, base, logs.append, rec=rec)
q(f"update pc_orders set state = 'done' where id = {oid2}")
oid3 = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"win7\"}}'))", **A))["id"]
ag3.tick(); ag3.tick()
o3 = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid3}"))
ck("bản không có trong bộ cài (win7) → lệnh failed kèm lý do, không ghi job.json, không tắt máy", o3["state"] == "failed" and "win7" in o3["result"]["msg"]
   and not os.path.exists(os.path.join(recd, "cb", "job.json")) and not ag3.h.powers, o3)
os.remove(os.path.join(recd, "cb", "linux", "grubx64.efi"))
oid4 = json.loads(q(f"select row_to_json(pc_admin_order('{PC}', 'reinstall', '{{\"os\": \"cachyos\"}}'))", **A))["id"]
ag3.tick(); ag3.tick()
o4 = json.loads(q(f"select row_to_json(o) from pc_orders o where id = {oid4}"))
ck("cài lại CachyOS mà phân vùng cứu hộ thiếu GRUB → failed 'thieu file'", o4["state"] == "failed" and "grubx64.efi" in o4["result"]["msg"], o4)
put("cb\\linux\\grubx64.efi", b"x")

print("4. Hạn thuê: hết hạn → báo khách rồi TẮT máy (như máy Windows)")
q(f"select pc_admin_rent('{PC}', '{{\"until\": \"{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}\"}}')", **A)
h4 = FakeHost("pc"); ag4 = cbagent.LinuxAgent(cbagent.LinuxSys(), h4, net, base, logs.append, rec=rec)
ag4.tick()
for _ in range(3): ag4.rent_call = (ag4.rent_call or ag4.s.now()) - 61; ag4.tick()
ck("hết hạn: hộp báo cho khách + tắt máy", any("HET HAN THUE" in m for m in h4.msgs) and any(p[0] == "shutdown" for p in h4.powers), (h4.msgs, h4.powers))
q(f"select pc_admin_rent('{PC}', '{{\"until\": null}}')", **A)

print("5. Công tắc 'Cho khách quyền Admin' → khách vào / ra nhóm wheel (sudo)")
if q("select count(*) from information_schema.columns where table_name = 'pc_settings' and column_name = 'cust_admin'") == "1":
    ag5 = cbagent.LinuxAgent(cbagent.LinuxSys(), FakeHost("pc"), net, base, logs.append, rec=rec)
    q("select pc_admin_set_flags('{\"cust_admin\": true}'::jsonb)", **A); ag5.tick()
    ck("shop BẬT → thêm khách vào nhóm wheel (sudo)", "wheel" in GROUPS and json.load(open(os.path.join(base, "cb.json"))).get("user_admin") is True, GROUPS)
    q("select pc_admin_set_flags('{\"cust_admin\": false}'::jsonb)", **A); ag5.tick()
    ck("shop TẮT → bỏ khách khỏi nhóm wheel", "wheel" not in GROUPS, GROUPS)
else:
    print("  (bỏ qua: CSDL thử chưa có cust_admin)")

print("6. Tự cập nhật theo bản kê admin công bố (mục linux + agent/lib)")
BASEN = pcagent.UPDATE_BASE + "main/winpc"
NEW = {"linux/cbagent.py": b"# cbagent moi\nLINUX_VER = '22.12a'\n", "agent/pcagent.py": b"# pcagent moi\n", "lib/cbcore.py": b"# core moi\n"}
for rel, d in (("agent/pcagent.py", b"# pcagent cu\n"), ("lib/cbcore.py", b"# core cu\n"), ("lib/cbrec.py", b"# rec\n"), ("lib/cbsys.py", b"# sys\n"), ("linux/cbagent.py", b"# cbagent cu\n")):
    os.makedirs(os.path.join(base, os.path.dirname(rel)), exist_ok=True); open(os.path.join(base, rel), "wb").write(d)
sha = lambda b: hashlib.sha256(b).hexdigest()
man = {"ver": "22.12a", "base": BASEN, "files": {"agent/pcagent.py": sha(NEW["agent/pcagent.py"]), "lib/cbcore.py": sha(NEW["lib/cbcore.py"]), "agent/pcremote.py": sha(b"x")},
       "linux": {"linux/cbagent.py": sha(NEW["linux/cbagent.py"]), "linux/cb-install.sh": sha(b"sh")}}
net.files = {BASEN + "/" + k: v for k, v in NEW.items()}
q("select pc_admin_settings('%s')" % json.dumps({"agent": man}), **A)
h6 = FakeHost("pc"); ag6 = cbagent.LinuxAgent(cbagent.LinuxSys(), h6, net, base, logs.append, rec=rec)
ag6.tick()
ck("tải + kiểm sha256 + chạy thử → thay cbagent.py, pcagent.py, cbcore.py (KHÔNG tải pcremote.py của Windows), đòi chạy lại", ag6.restart
   and open(os.path.join(base, "linux", "cbagent.py"), "rb").read() == NEW["linux/cbagent.py"] and open(os.path.join(base, "agent", "pcagent.py"), "rb").read() == NEW["agent/pcagent.py"]
   and not any("pcremote" in c for c in net.files if False) and not os.path.exists(os.path.join(base, "agent", "pcremote.py")), [x for x in logs[-5:]])
ck("… bản mới cũng chép lên phân vùng cứu hộ (lần cài lại CachyOS sau dùng)", open(os.path.join(recd, "cb", "linux", "cbagent.py"), "rb").read() == NEW["linux/cbagent.py"])
h7 = FakeHost("pc"); ag7 = cbagent.LinuxAgent(cbagent.LinuxSys(), h7, net, base, logs.append, rec=rec); ag7.tick()
ck("chạy lại: đã đúng bản → không tải lại", not ag7.restart)
NEW2 = dict(NEW, **{"linux/cbagent.py": b"# ban 3\n"}); man2 = dict(man, ver="22.12b", linux={"linux/cbagent.py": sha(NEW2["linux/cbagent.py"])})
net.files[BASEN + "/linux/cbagent.py"] = NEW2["linux/cbagent.py"]
q("select pc_admin_settings('%s')" % json.dumps({"agent": man2}), **A)
h8 = FakeHost("pc"); h8.check_ok = False; ag8 = cbagent.LinuxAgent(cbagent.LinuxSys(), h8, net, base, logs.append, rec=rec); ag8.tick()
ck("bản mới chạy thử KHÔNG đạt → giữ bản cũ", not ag8.restart and open(os.path.join(base, "linux", "cbagent.py"), "rb").read() == NEW["linux/cbagent.py"])
q("select pc_admin_settings('{\"agent\": {}}')", **A)

print("7. Phần chạy được trên máy này (không cần máy CachyOS)")
ck("đường dẫn kiểu Windows của lõi agent → Linux", cbagent.P("logs\\emu.json") == "logs/emu.json")
ck("selfcheck", cbagent.main(["selfcheck"]) == 0)
ck("tên khách trên Linux từ tài khoản Windows 'PC' → 'pc'", C.linux_user("PC") == "pc")

shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(EFIV, ignore_errors=True)
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
