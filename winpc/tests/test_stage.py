# -*- coding: utf-8 -*-
"""Thử: cài lại từ trong Windows (CAI-DAT.cmd → cb_stage.py) + cài đặt lần đầu (cb_provision.py). Chạy: python3 tests/test_stage.py"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
for d in ("lib", "pe", "agent", "os"): sys.path.insert(0, os.path.join(HERE, "..", d))
import cbcore as C                                    # noqa: E402
import cbrec                                          # noqa: E402
import cb_pe                                          # noqa: E402
import cb_stage                                       # noqa: E402
import cb_provision                                   # noqa: E402
from cbsys import GPT_DATA, GPT_ESP, GPT_MSR, GPT_WINRE  # noqa: E402
from fakesys import GB, MB, FakeSys, ScriptUI         # noqa: E402
import test_pe_helpers as H                           # noqa: E402

OK = FAIL = 0


# Mặc định cho mọi phép thử cb_provision: máy "có mạng" ngay, không có card NVIDIA, dòng tiến độ gom vào SAID (không in ra màn hình thử).
SAID = []
REAL_NET, REAL_GPU = cb_provision.real_net, cb_provision.real_nvidia_state
cb_provision.real_net = lambda host, port, timeout=4: True
cb_provision.real_nvidia_state = lambda: (False, False)
cb_provision.Prov.say = lambda self, m: (self._say(m) if self._say else SAID.append(m))


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", extra)


def plain_uefi(fs, size=480):
    """Máy Windows thường (chưa có gì của CloudBlue): EFI · MSR · C: · WinRE."""
    d = fs.disk(0, size, ssd=True, style="gpt", model="SSD may khach")
    esp = d.add(100, GPT_ESP, "FAT32", "", files={"efi\\microsoft\\boot\\bcd": "old"})
    d.add(16, GPT_MSR)
    c = d.add((size - 2) * 1024, GPT_DATA, "NTFS", "OS", "C", files=dict(H.WINFILES))
    re_ = d.add(0, GPT_WINRE, "NTFS", "Recovery", attrs=0x8000000000000001)
    return d, esp, c, re_


def to_pe(fs):
    for d in fs.fdisks:
        for p in d.slots:
            if p.vol and p.vol.letter == "C": p.vol.letter = None


logs = []
print("1. CAI-DAT.cmd trên máy Windows thường (UEFI) — mở ISO rồi chạy")
fs = FakeSys("uefi"); cfg = H.cfg0(); KEY = "cbpc_" + "b" * 40
fs.cd(letter="D", files=H.media_files(cfg, key=KEY))
d, esp, c, re_ = plain_uefi(fs)
other = fs.disk(1, 1000, ssd=False, style="gpt", model="HDD phu"); other.add(0, GPT_DATA, "NTFS", "DATA", "E", files={"x": "1"})
c_size0 = c.size
img = cb_stage.stage(fs, "D:\\", "1511", "disk", "MAY-KHACH", fs.now(), logs.append)
rec = next(p for p in d.slots if p.vol and p.vol.label == "CBRECOVERY")
ck("ổ C: được thu nhỏ đúng bằng cỡ phân vùng cứu hộ (12GB), dữ liệu C: còn nguyên", c_size0 - c.size == 12 * GB and fs.file("C", "users\\khach\\bi-mat.txt") == "du lieu khach cu", (c_size0 - c.size) / GB)
ck("phân vùng cứu hộ nằm ngay sau C:, đã ẩn (không chữ ổ, cờ bảo vệ)", rec.offset == c.offset + c.size and rec.vol.letter is None and rec.attrs == 0x8000000000000001)
ck("đã chép boot.wim + 2 bản Windows + phần mềm vào", all(k in rec.vol.files for k in ("cb\\boot\\boot.wim", "cb\\boot\\boot.sdi", "cb\\images\\22h2.wim", "cb\\images\\1511.wim", "cb\\py\\python.exe", "cb\\pe\\cb_pe.py", "cb\\recovery.tag")))
job = json.loads(rec.vol.files["cb\\job.json"])
ck("lệnh: bản 1511, xoá cả ổ hệ thống, kèm mã đăng ký của bộ cài + vị trí ổ C", job["os"] == "1511" and job["wipe"] == "disk" and job["enroll_key"] == KEY and job["win"]["offset"] == c.offset and job["win"]["size"] == c.size and job["id"].startswith("local-"), job)
sb = fs.bcd.get("(system)", {})
ck("đặt khởi động 1 lần vào bộ cài", sb.get("bootsequence") == C.PE_GUID and C.PE_GUID in sb["entries"])
ck("CHƯA xoá gì trước khi khởi động lại", fs.file("C", "users\\khach\\bi-mat.txt") and fs.file("E", "x") == "1" and re_ in d.slots)
to_pe(fs)
rc = cb_pe.Installer(fs).run(ScriptUI())
ck("khởi động lại → bộ cài làm lệnh xong", rc == 0, rc)
ck("ổ hệ thống: EFI · MSR · cứu hộ · Windows mới; WinRE cũ + C: cũ đã xoá; ổ phụ giữ nguyên (kiểu disk)", len(d.slots) == 4 and re_ not in d.slots and c not in d.slots and rec in d.slots and esp in d.slots and fs.file("E", "x") == "1")
neww = next(p for p in d.slots if p.vol and p.vol.label == "Windows")
seed = json.loads(neww.vol.files["cloudbluepc\\seed.json"])
ck("Windows mới (1511) mang mã đăng ký để tự lên web", neww.vol.files["windows\\cb-image.txt"] == "1511.wim|1" and seed["enroll_key"] == KEY and seed["name"] == "MAY-KHACH")
ck("lệnh đã đóng, không còn mã đăng ký trên phân vùng cứu hộ", "cb\\job.json" not in rec.vol.files and KEY not in json.dumps({k: str(v) for k, v in rec.vol.files.items()}))

print("2. Máy BIOS: System Reserved + C:")
fs = FakeSys("bios"); cfg = H.cfg0(); fs.cd(letter="D", files=H.media_files(cfg))
d = fs.disk(0, 240, ssd=True, style="mbr")
sr = d.add(500, 0x07, "NTFS", "System Reserved", active=True, files={"boot\\bcd": "old"})
c = d.add(0, 0x07, "NTFS", "", "C", files=dict(H.WINFILES))
cb_stage.stage(fs, "D:\\", "22h2", "system", "PC-BIOS", fs.now(), logs.append)
rec = next(p for p in d.slots if p.vol and p.vol.label == "CBRECOVERY")
ck("tạo phân vùng cứu hộ kiểu 27 (ẩn)", rec.type == 0x27 and rec.vol.letter is None and len(d.slots) == 3)
ck("phân vùng cứu hộ tạo từ Windows đang chạy cũng được khoá quyền (chỉ SYSTEM + Administrators)", any(c[0] == "icacls" and len(c[1]) == 3 and "/remove:g" in c and "*S-1-5-11" in c for c in fs.cmds)
   and any(c[0] == "icacls" and "/inheritance:r" in c and len(c[1]) == 3 for c in fs.cmds), [c for c in fs.cmds if c[0] == "icacls"])
to_pe(fs); rc = cb_pe.Installer(fs).run(ScriptUI())
ck("kiểu 'system': chỉ định dạng lại C:, không xoá phân vùng nào", rc == 0 and len(d.slots) == 3 and c in d.slots and sr in d.slots and "users\\khach\\bi-mat.txt" not in c.vol.files and c.vol.files.get("windows\\cb-image.txt") == "22h2.wim|6", (rc, len(d.slots), c.vol.files.get("windows\\cb-image.txt")))

print("3. Trường hợp không làm được → báo rõ, không đổi gì")
fs = FakeSys("uefi"); cfg = H.cfg0(); fs.cd(letter="D", files=H.media_files(cfg)); d, esp, c, re_ = plain_uefi(fs); fs.fail_shrink = True
try: cb_stage.stage(fs, "D:\\", "22h2", "all", "X", fs.now(), logs.append); msg = ""
except C.Stop as e: msg = str(e)
ck("không thu nhỏ được ổ C: → dừng, khuyên dùng USB; không có lệnh nào được ghi", "USB" in msg and not fs.bcd.get("(system)") and len(d.slots) == 4, msg)
fs = FakeSys("bios"); cfg = H.cfg0(); fs.cd(letter="D", files=H.media_files(cfg)); d, esp, c, re_ = plain_uefi(fs)
try: cb_stage.stage(fs, "D:\\", "22h2", "all", "X", fs.now(), logs.append); msg = ""
except C.Stop as e: msg = str(e)
ck("máy BIOS mà ổ GPT (không khớp) → dừng", "USB" in msg and not fs.dp_scripts, msg)
fs = FakeSys("bios"); cfg = H.cfg0(); fs.cd(letter="D", files=H.media_files(cfg)); d = fs.disk(0, 240, style="mbr")
for i in range(3): d.add(500, 0x07, "NTFS", "p%d" % i, active=(i == 0))
d.add(0, 0x07, "NTFS", "", "C", files=dict(H.WINFILES))
try: cb_stage.stage(fs, "D:\\", "22h2", "all", "X", fs.now(), logs.append); msg = ""
except C.Stop as e: msg = str(e)
ck("ổ MBR đã đủ 4 phân vùng → dừng", "4 phan vung" in msg and not fs.dp_scripts, msg)
fs = FakeSys("uefi"); cfg = H.cfg0(); fs.cd(letter="D", files=H.media_files(cfg)); plain_uefi(fs)
for bad, why in (("win7", "ban Windows"), ):
    try: cb_stage.stage(fs, "D:\\", bad, "all", "X", fs.now(), logs.append); msg = ""
    except C.Stop as e: msg = str(e)
    ck("bản Windows không có trong bộ cài → dừng trước khi đụng ổ", "win7" in msg and not fs.dp_scripts, msg)

print("4. Máy ĐÃ có phân vùng cứu hộ → chép đè bộ cài mới, không tạo thêm phân vùng")
fs = FakeSys("uefi"); cfg = H.cfg0(); fs.cd(letter="D", files=dict(H.media_files(cfg), **{"sources\\install.wim": b"I22-MOI"}))
d, rec, win = H.cb_layout(fs, cfg)
n = len(d.slots)
cb_stage.stage(fs, "D:\\", "22h2", "all", "CB-OLD001", fs.now(), logs.append, extra={"ticket": "v" * 32, "hw": "h" * 64})
ck("không tạo phân vùng mới; ảnh 22H2 trên cứu hộ là bản MỚI", len(d.slots) == n and rec.vol.files["cb\\images\\22h2.wim"] == b"I22-MOI" and not fs.dp_scripts)
job = json.loads(rec.vol.files["cb\\job.json"])
ck("máy đã đăng ký: lệnh mang vé (giữ đúng máy trên web)", job["ticket"] == "v" * 32 and job["hw"] == "h" * 64)

print("5. Cài đặt lần đầu trong Windows mới (cb_provision)")
with tempfile.TemporaryDirectory() as base:
    for sub in ("os", "agent", "py", "logs"): os.makedirs(os.path.join(base, sub))
    open(os.path.join(base, "cb.json"), "w").write(json.dumps({"user": "PC", "password": ""}))
    open(os.path.join(base, "agent", "cbpc.cmd"), "w").write("x")
    os.makedirs(os.path.join(base, "os", "firstboot.d"))
    for f in ("20-driver.cmd", "10-phan-mem.ps1", "ghi-chu.txt"): open(os.path.join(base, "os", "firstboot.d", f), "w").write("x")
    calls, fail = [], set()

    def run(argv, timeout=300):
        calls.append(argv)
        return (1, "loi") if any(k in " ".join(argv) for k in fail) else (0, "")
    p = cb_provision.Prov(base, run, log=lambda m: None)
    p.specialize()
    j = lambda: [" ".join(a) for a in calls]
    ck("specialize: chính sách bỏ trang riêng tư + không màn hình khoá + hộp hỏi quyền trên màn hình thường", any("DisablePrivacyExperience" in x and "/d 1" in x for x in j()) and any("NoLockScreen" in x for x in j()) and any("PromptOnSecureDesktop" in x and "/d 0" in x for x in j()))
    ck("specialize: tắt ngủ đông / ngủ / tắt màn hình", any(x == "powercfg /hibernate off" for x in j()) and any("standby-timeout-ac 0" in x for x in j()) and any("monitor-timeout-ac 0" in x for x in j()))
    ck("specialize: tạo tác vụ agent (XML) + tác vụ canh 5 phút bằng SYSTEM", any("schtasks /create /tn CloudBluePC Agent /xml" in x for x in j()) and any("CloudBluePC Watch /sc minute /mo 5 /ru SYSTEM" in x for x in j()))
    xml = open(os.path.join(base, "os", "task-agent.xml"), encoding="utf-16").read()
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f: f.write(xml); xp = f.name
    r = subprocess.run(["xmllint", "--noout", xp], capture_output=True, text=True); os.unlink(xp)
    ck("XML tác vụ hợp lệ: chạy pythonw … pcagent.py run, SYSTEM, không giới hạn thời gian, tự bật lại khi lỗi", r.returncode == 0 and "pythonw.exe</Command>" in xml and 'pcagent.py" run' in xml
       and "<UserId>S-1-5-18</UserId>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml and "<RestartOnFailure>" in xml and "<BootTrigger>" in xml, r.stderr)
    ck("cbpc.cmd được chép ra gốc thư mục", os.path.isfile(os.path.join(base, "cbpc.cmd")))
    calls.clear(); p.firstlogon()
    ck("firstlogon: tự đăng nhập vĩnh viễn (có DefaultPassword rỗng, xoá bộ đếm)", any("AutoAdminLogon" in x and x.endswith("/d 1 /f") for x in j()) and any("DefaultUserName /t REG_SZ /d PC" in x for x in j())
       and ["reg", "add", r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "/v", "DefaultPassword", "/t", "REG_SZ", "/d", "", "/f"] in calls and any("reg delete" in x and "AutoLogonCount" in x for x in j()))
    ck("firstlogon: bật agent + chạy script riêng theo thứ tự tên (chỉ .cmd/.bat/.ps1)", any(x == "schtasks /run /tn CloudBluePC Agent" for x in j())
       and [x.split("\\")[-1].split("/")[-1] for x in j() if "firstboot.d" in x and not x.startswith("icacls")] == ["10-phan-mem.ps1", "20-driver.cmd"], [x for x in j() if "firstboot.d" in x])
    ck("mật khẩu không bị ghi vào nhật ký", not any("DefaultPassword=" in l and "(an)" not in l for l in p.lines))
    calls.clear(); p.firstboot()
    ck("script riêng chỉ chạy 1 lần", not calls)
    calls.clear(); fail.add("/xml"); p.tasks()
    ck("tạo tác vụ bằng XML lỗi → dùng kiểu dự phòng (onstart, SYSTEM)", any("CloudBluePC Agent /sc onstart /ru SYSTEM /rl highest" in x for x in j()))
    fail.clear(); fail.add("schtasks"); calls.clear()
    rc = cb_provision.main(["specialize"]) if False else None
    p2 = cb_provision.Prov(base, run, log=lambda m: None); p2.specialize(); p2.firstlogon()
    ck("mọi lệnh tác vụ đều lỗi → vẫn chạy hết, không ném lỗi (không chặn bước cài Windows)", True)

print("5b. Bảo mật: khoá quyền thư mục / phân vùng cứu hộ + hạ tài khoản khách xuống tài khoản thường")
def sec_env(cfg, admins=("Administrator", "PC"), names="ADM=Administrators|USR=Users|BIA=Administrator|"):
    base = tempfile.mkdtemp()
    for sub in ("os", "agent", "py", "logs", "lib"): os.makedirs(os.path.join(base, sub))
    shutil.copy(os.path.join(REPO, "lib", "cbcore.py"), os.path.join(base, "lib", "cbcore.py"))
    open(os.path.join(base, "cb.json"), "w").write(json.dumps(cfg))
    os.makedirs(os.path.join(base, "os", "firstboot.d")); open(os.path.join(base, "os", "firstboot.d", "10-driver.cmd"), "w").write("x")
    open(os.path.join(base, "os", "wallpaper.jpg"), "w").write("jpg")
    st = {"calls": [], "admins": list(admins), "users": [], "fail": set(), "names": names, "clock": 1_000_000, "base": base}

    def run(argv, timeout=300):
        st["calls"].append(list(argv)); a = " ".join(argv)
        if any(k in a for k in st["fail"]): return 1, "loi"
        if argv[0] == "powershell.exe" and "S-1-5-32-544" in a: return (0, st["names"] + "\r\n") if st["names"] else (1, "")
        if argv[0] == "powershell.exe" and "WinNT://" in a:                     # hỏi thành viên nhóm quản trị (chỉ trả lời khi phép thử bật "adsi")
            return (0, "".join("M=%s\r\n" % x for x in st["admins"]) + "M_END\r\n") if st.get("adsi") else (0, "")
        if argv[:2] == ["net", "localgroup"] and len(argv) == 3:
            mem = st["admins"] if argv[2] == st["names"].split("|")[0][4:] or (not st["names"] and argv[2] == "Administrators") else st["users"]
            return 0, "Alias name     %s\r\nMembers\r\n\r\n-------\r\n%s\r\nThe command completed successfully.\r\n" % (argv[2], "\r\n".join(mem))
        if argv[:2] == ["net", "localgroup"] and argv[-1] == "/delete": st["admins"].remove(argv[3]); return 0, ""
        if argv[:2] == ["net", "localgroup"] and argv[-1] == "/add":
            if argv[3] in st["users"]: return 2, "System error 1378"
            st["users"].append(argv[3]); return 0, ""
        return 0, ""
    pr = cb_provision.Prov(base, run, log=lambda m: None, spi=lambda path: True, admin=True, rec=lambda: "\\\\?\\Volume{abc}\\", now=lambda: st["clock"])
    return pr, st
FULL = ["*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"]
pr, st = sec_env({"user": "PC", "password": ""})
base, calls = st["base"], st["calls"]
pr.specialize()
ck("specialize khoá thư mục: bỏ thừa hưởng, chỉ SYSTEM + Administrators toàn quyền, gỡ Users / Authenticated Users / Everyone, đặt lại mọi thứ bên trong",
   ["icacls", base, "/inheritance:r", "/grant:r"] + FULL in calls and ["icacls", base, "/remove:g", "*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0", "*S-1-3-0"] in calls
   and ["icacls", base + "\\*", "/reset", "/T", "/C", "/Q"] in calls and ["icacls", base, "/setowner", "*S-1-5-32-544", "/T", "/C", "/Q"] in calls, [c for c in calls if c[0] == "icacls"])
ck("tài khoản thường chỉ được ĐỌC + CHẠY đúng 2 thư mục py và os; firstboot.d (script của chủ shop) lại bị khoá",
   sorted(c[1].split("\\")[-1] for c in calls if c[0] == "icacls" and "*S-1-5-32-545:(OI)(CI)RX" in c) == ["os", "py"]
   and ["icacls", base + "\\os\\firstboot.d", "/inheritance:r", "/grant:r"] + FULL in calls and not any("RX" in " ".join(c) and ("agent" in c[1] or "logs" in c[1] or "lib" in c[1]) for c in calls if c[0] == "icacls"))
ck("thứ tự: đặt lại bên trong TRƯỚC, rồi mới cho đọc py / os, cuối cùng khoá firstboot.d", [i for i, c in enumerate(calls) if c[0] == "icacls" and "/reset" in c][0]
   < [i for i, c in enumerate(calls) if c[0] == "icacls" and "*S-1-5-32-545:(OI)(CI)RX" in c][0] < calls.index(["icacls", base + "\\os\\firstboot.d", "/inheritance:r", "/grant:r"] + FULL))
ck("khoá cả gốc phân vùng cứu hộ (qua đường \\\\?\\Volume{…}\\)", ["icacls", "\\\\?\\Volume{abc}\\", "/inheritance:r", "/grant:r"] + FULL in calls
   and ["icacls", "\\\\?\\Volume{abc}\\", "/remove:g", "*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0", "*S-1-3-0"] in calls and ["icacls", "\\\\?\\Volume{abc}\\*", "/reset", "/T", "/C", "/Q"] in calls
   and ["icacls", "\\\\?\\Volume{abc}\\*", "/setowner", "*S-1-5-32-544", "/T", "/C", "/Q"] in calls
   and os.path.isfile(os.path.join(base, "logs", "lock.done")))
calls.clear(); pr.system()
ck("agent gọi pha system TRƯỚC lần đăng nhập đầu: chỉ khoá quyền, CHƯA hạ quyền tài khoản khách (script riêng còn cần quyền Admin)",
   any(c[0] == "icacls" for c in calls) and not any(c[:2] == ["net", "localgroup"] and c[-1] == "/delete" for c in calls) and st["admins"] == ["Administrator", "PC"])
calls.clear(); pr.firstlogon()
j = [" ".join(c) for c in calls]
i_script = next(i for i, x in enumerate(j) if x.startswith("cmd.exe /c") and "10-driver.cmd" in x)
i_demote = j.index("net localgroup Administrators PC /delete")
ck("firstlogon: chạy script riêng (còn quyền Admin) RỒI MỚI gỡ tài khoản khách khỏi nhóm Administrators, vẫn ở nhóm Users", i_script < i_demote and st["admins"] == ["Administrator"] and st["users"] == ["PC"])
ck("cấm tài khoản khách tự đổi mật khẩu (giữ tự đăng nhập)", "net user PC /passwordchg:no" in j)
adm_pw = [c for c in calls if c[:2] == ["net", "user"] and len(c) == 5 and c[2] == "Administrator" and c[4] == "/active:no"]
ck("tài khoản Administrator có sẵn: mật khẩu ngẫu nhiên 14 ký tự + tắt", len(adm_pw) == 1 and len(adm_pw[0][3]) == 14 and adm_pw[0][3].startswith("Cb1!"), adm_pw)
ck("mật khẩu ngẫu nhiên KHÔNG nằm trong nhật ký", adm_pw and not any(adm_pw[0][3] in l for l in pr.lines) and any("dat mat khau ngau nhien" in l for l in pr.lines))
ck("hẹn khởi động lại 1 lần để quyền mới có hiệu lực + đặt mốc đã xong", any(x.startswith("shutdown /r /t 20") for x in j) and j.index("net localgroup Administrators PC /delete") < next(i for i, x in enumerate(j) if x.startswith("shutdown"))
   and all(os.path.isfile(os.path.join(base, "logs", n)) for n in ("firstlogon.start", "firstlogon.done", "harden.done")))
first_pw = adm_pw[0][3]
calls.clear(); pr.system(); pr.harden()
j = [" ".join(c) for c in calls]
ck("chạy lại (agent gọi định kỳ): không gỡ lần 2, không đặt lại mật khẩu Administrator, không khởi động lại", not any("/delete" in x for x in j) and not any("/active:no" in x for x in j) and not any(x.startswith("shutdown") for x in j))
calls.clear(); st["admins"].append("PC"); pr.system()
ck("có ai thêm lại tài khoản khách vào nhóm Administrators → agent gỡ lại ở lần kiểm sau", "net localgroup Administrators PC /delete" in [" ".join(c) for c in calls] and st["admins"] == ["Administrator"])
pr, st = sec_env({"user": "PC", "password": "", "user_admin": True}); pr.firstlogon()
ck('chủ shop chọn để khách quyền Admin ("user_admin") → không hạ quyền, không khởi động lại — nhưng VẪN khoá quyền thư mục', st["admins"] == ["Administrator", "PC"] and not any(c[0] == "shutdown" for c in st["calls"])
   and not any(c[:2] == ["net", "user"] and "/active:no" in c for c in st["calls"]) and any(c[0] == "icacls" for c in st["calls"]))
pr, st = sec_env({"user": "PC", "password": ""})
pr.touch("firstlogon.start"); st["clock"] += 1800; pr.system()
half = list(st["admins"])
st["clock"] += 1900; st["calls"].clear(); pr.system()
ck("lần đăng nhập đầu chạy dở (mất điện…): chưa quá 1 giờ thì chờ, quá 1 giờ agent tự hạ quyền — không khởi động lại máy",
   half == ["Administrator", "PC"] and st["admins"] == ["Administrator"] and not any(c[0] == "shutdown" for c in st["calls"]))
pr, st = sec_env({"user": "PC", "password": ""})
pr.system(); st["clock"] += 3700; pr.system()
ck("bản Windows không chạy file trả lời (không có lần đăng nhập đầu của CloudBlue): 1 giờ sau lần chạy đầu của agent thì hạ quyền", st["admins"] == ["Administrator"])
pr, st = sec_env({"user": "Khach", "password": ""}, admins=("Administrator",)); st["fail"].add("net user Khach"); pr.system(); st["clock"] += 4000; pr.system()
ck("tài khoản khách chưa được Windows tạo → chưa làm gì, không lỗi", not any("/active:no" in c for c in st["calls"]) and not os.path.exists(os.path.join(st["base"], "logs", "harden.done")))
pr, st = sec_env({"user": "Gast", "password": ""}, admins=("Administrator", "Gast"), names="ADM=Administratoren|USR=Benutzer|BIA=Administrator|"); pr.firstlogon()
j = [" ".join(c) for c in st["calls"]]
ck("Windows tiếng nước khác: dùng đúng tên nhóm theo ngôn ngữ máy (hỏi theo SID)", "net localgroup Administratoren Gast /delete" in j and "net localgroup Benutzer Gast /add" in j)
pr, st = sec_env({"user": "PC", "password": ""}, names=""); pr.firstlogon()
ck("không hỏi được tên nhóm → dùng tên tiếng Anh", "net localgroup Administrators PC /delete" in [" ".join(c) for c in st["calls"]])
pr, st = sec_env({"user": "Administrator", "password": ""}, admins=("Administrator",)); pr.firstlogon()
ck("tài khoản khách trùng tên tài khoản Administrator có sẵn → không đụng", st["admins"] == ["Administrator"] and not any("/active:no" in c for c in st["calls"]))
pr, st = sec_env({"user": "PC", "password": ""})
pu = cb_provision.Prov(st["base"], pr._run, log=lambda m: None, spi=lambda path: True, admin=False, rec=lambda: "")
pu.logon(); pu.system()
ck("tài khoản thường đăng nhập: chỉ đặt ảnh nền — không đụng tác vụ, không khoá quyền, không hạ quyền", not any(c[0] in ("schtasks", "icacls", "net", "shutdown") for c in st["calls"]) and any(c[0] == "reg" for c in st["calls"]))
old_la = os.environ.get("LOCALAPPDATA")
with tempfile.TemporaryDirectory() as la, tempfile.TemporaryDirectory() as b2:
    os.environ["LOCALAPPDATA"] = la
    open(os.path.join(b2, "logs"), "w").write("khong phai thu muc")                     # giả cảnh tài khoản thường không ghi được vào C:\CloudBluePC\logs
    cb_provision.Prov(b2, lambda a, t=0: (0, ""), admin=False, rec=lambda: "").log("dong thu")
    ck("không ghi được nhật ký vào thư mục bị khoá → ghi vào hồ sơ người dùng (%LOCALAPPDATA%\\CloudBluePC)", "dong thu" in open(os.path.join(la, "CloudBluePC", "provision.log"), encoding="utf-8").read())
if old_la is None: os.environ.pop("LOCALAPPDATA", None)
else: os.environ["LOCALAPPDATA"] = old_la
cmd = open(os.path.join(REPO, "os", "provision.cmd"), "rb").read().decode("ascii")
ck("provision.cmd: không ghi được vào logs thì chuyển nhật ký sang hồ sơ người dùng, vẫn chạy", '|| set "CBLOG=%LOCALAPPDATA%\\CloudBluePC"' in cmd and '>> "%CBLOG%\\provision.out" 2>&1' in cmd and cmd.rstrip().endswith("exit /b 0"))

print("5c. Việc lạ về bảo mật SAU khi đã khoá xong → ghi logs\\sec.event cho agent báo về web")
def sec_ev(st):
    p = os.path.join(st["base"], "logs", "sec.event")
    return open(p).read() if os.path.exists(p) else None
pr, st = sec_env({"user": "PC", "password": ""}, admins=("Administrator", "PC", "shopadmin"), names="ADM=Administrators|USR=Users|BIA=Administrator|DIS=False|")
st["adsi"] = True
pr.firstlogon()
ck("lần khoá đầu: không coi là việc lạ; ghi nhớ tài khoản quản trị chủ shop tự tạo (shopadmin)", sec_ev(st) is None and st["admins"] == ["Administrator", "shopadmin"]
   and open(os.path.join(st["base"], "logs", "admins.known")).read().split() == ["shopadmin"], (sec_ev(st), st["admins"]))
st["names"] = "ADM=Administrators|USR=Users|BIA=Administrator|DIS=True|"
st["calls"].clear(); pr.system()
ck("các lần soát sau, không có gì đổi → không có việc lạ, không đặt lại mật khẩu Administrator", sec_ev(st) is None and not any("/active:no" in " ".join(c) for c in st["calls"]))
st["admins"].append("PC"); st["calls"].clear(); pr.system()
ck("tài khoản khách có lại quyền Admin → gỡ lại + ghi việc lạ", st["admins"] == ["Administrator", "shopadmin"] and "tai khoan khach 'PC' co lai quyen Admin - da ha lai" in (sec_ev(st) or ""), sec_ev(st))
os.remove(os.path.join(st["base"], "logs", "sec.event"))
st["names"] = "ADM=Administrators|USR=Users|BIA=Administrator|DIS=False|"; st["calls"].clear(); pr.system()
pw2 = [c for c in st["calls"] if c[:2] == ["net", "user"] and len(c) == 5 and c[4] == "/active:no"]
ck("tài khoản Administrator có sẵn bị bật lại → tắt lại bằng mật khẩu ngẫu nhiên MỚI + ghi việc lạ", len(pw2) == 1 and len(pw2[0][3]) == 14 and "co san bi bat lai" in (sec_ev(st) or "")
   and not any(pw2[0][3] in l for l in pr.lines), (pw2, sec_ev(st)))
os.remove(os.path.join(st["base"], "logs", "sec.event"))
st["names"] = "ADM=Administrators|USR=Users|BIA=Administrator|DIS=True|"
st["admins"].append("hacker"); pr.system()
ck("nhóm quản trị có tài khoản MỚI → ghi việc lạ (không tự xoá)", "nhom quan tri co tai khoan moi: hacker" in (sec_ev(st) or "") and "hacker" in st["admins"], sec_ev(st))
os.remove(os.path.join(st["base"], "logs", "sec.event")); pr.system()
ck("tài khoản đó chỉ báo 1 lần", sec_ev(st) is None)
st["admins"].append("PC"); st["admins"].append("x2"); pr.system()
ck("nhiều việc lạ cùng lúc → gộp trong 1 file, chữ không dấu, không quá 300 ký tự", all(k in sec_ev(st) for k in ("co lai quyen Admin", "tai khoan moi: x2")) and len(sec_ev(st)) <= 300 and sec_ev(st).isascii(), sec_ev(st))
pr, st = sec_env({"user": "PC", "password": ""}); pr.firstlogon(); st["admins"].append("PC"); pr.system()
ck("không hỏi được thành viên nhóm / tình trạng Administrator (PowerShell lỗi) → vẫn gỡ quyền khách + ghi việc lạ, không lỗi", st["admins"] == ["Administrator"] and "co lai quyen Admin" in (sec_ev(st) or ""))

print("6. Ảnh nền + script riêng theo từng bản Windows")
def fake_reg():
    """reg add / reg query giả: nhớ các giá trị đã ghi (để thử 'mỗi tài khoản chỉ đặt ảnh nền 1 lần')."""
    store, calls = {}, []

    def run(argv, timeout=300):
        calls.append(list(argv))
        if argv[:2] == ["reg", "add"]: store[(argv[2], argv[4])] = argv[8]; return 0, ""
        if argv[:2] == ["reg", "query"]: return (0, "") if (argv[2], argv[4]) in store else (1, "khong co")
        return 0, ""
    return store, calls, run
with tempfile.TemporaryDirectory() as base:
    for sub in ("os", "agent", "py", "logs"): os.makedirs(os.path.join(base, sub))
    open(os.path.join(base, "cb.json"), "w").write(json.dumps({"user": "PC", "password": ""}))
    store, calls, run = fake_reg(); spi = []
    p = cb_provision.Prov(base, run, log=lambda m: None, spi=lambda path: (spi.append(path), True)[1])
    ck("không có file ảnh nền → không làm gì", p.wallpaper() is False and not calls and not spi)
    wp = os.path.join(base, "os", "wallpaper.jpg"); open(wp, "wb").write(b"JPG")
    ck("có ảnh nền → đặt kiểu phủ kín màn hình rồi gọi Windows đổi ảnh", p.wallpaper() is True and spi == [wp]
       and store.get((r"HKCU\Control Panel\Desktop", "WallpaperStyle")) == "10" and store.get((r"HKCU\Control Panel\Desktop", "TileWallpaper")) == "0"
       and [c[4] for c in calls if c[:2] == ["reg", "add"]][:2] == ["WallpaperStyle", "TileWallpaper"], (spi, store))
    ck("ghi dấu lần 1 cho tài khoản này", (r"HKCU\Software\CloudBluePC", "Wallpaper") in store and (r"HKCU\Software\CloudBluePC", "Wallpaper2") not in store)
    ck("lần chạy kế tiếp đặt lại 1 lần nữa (Windows hay trả về ảnh mặc định ở lần đăng nhập đầu) + ghi dấu lần 2", p.wallpaper() is True and len(spi) == 2 and (r"HKCU\Software\CloudBluePC", "Wallpaper2") in store)
    ck("từ lần thứ 3 KHÔNG đặt lại → khách đổi ảnh nền thì giữ ảnh của khách", p.wallpaper() is False and p.wallpaper() is False and len(spi) == 2)
    store, calls, run = fake_reg()

    def spi_bad(path): raise OSError("khong goi duoc")
    p = cb_provision.Prov(base, run, log=lambda m: None, spi=spi_bad)
    ck("Windows từ chối đổi ngay → ghi thẳng vào hồ sơ (áp dụng lần đăng nhập sau) + vẫn ghi dấu", p.wallpaper() is True and store.get((r"HKCU\Control Panel\Desktop", "Wallpaper")) == wp
       and any(c[0] == "rundll32.exe" for c in calls) and (r"HKCU\Software\CloudBluePC", "Wallpaper") in store, store)
    store, calls, run = fake_reg(); spi = []
    p = cb_provision.Prov(base, run, log=lambda m: None, spi=lambda path: (spi.append(path), True)[1])
    p.firstlogon()
    ck("firstlogon có đặt ảnh nền", spi == [wp])
    calls.clear(); p.logon()
    ck("logon ngay sau đó (cùng phiên đầu): đặt lại 1 lần nữa", spi == [wp, wp])
    p.logon(); p.logon()
    ck("các lần đăng nhập sau: không đặt lại", spi == [wp, wp])
    store.pop((r"HKCU\Software\CloudBluePC", "Wallpaper")); store.pop((r"HKCU\Software\CloudBluePC", "Wallpaper2")); p.logon(); p.logon(); p.logon()
    ck("tài khoản khác (chưa có dấu): cũng chỉ đặt 2 lần đầu", spi == [wp] * 4)
    os.remove(wp); open(os.path.join(base, "os", "wallpaper.png"), "wb").write(b"PNG"); store.clear(); spi.clear()
    ck("ảnh nền dạng .png cũng nhận", p.wallpaper() is True and spi[0].endswith("wallpaper.png"))
with tempfile.TemporaryDirectory() as base:
    for sub in ("os", "agent", "py", "logs"): os.makedirs(os.path.join(base, sub))
    fb = os.path.join(base, "os", "firstboot.d")
    for d in ("", "1511", "22h2", "ghi-chu"): os.makedirs(os.path.join(fb, d), exist_ok=True)
    for f in ("20-chung.cmd", "10-chung.ps1", "1511/05-lan.cmd", "1511/50-vga.bat", "1511/setup.exe", "22h2/05-chi-22h2.cmd", "ghi-chu/x.cmd"):
        open(os.path.join(fb, *f.split("/")), "w").write("x")
    open(os.path.join(base, "seed.json"), "w").write(json.dumps({"os": "1511", "name": "CB-1"}))
    store, calls, run = fake_reg(); envs = []

    def run2(argv, timeout=300):
        if "firstboot.d" in " ".join(argv): envs.append(os.environ.get("CB_OS"))
        return run(argv, timeout)
    p = cb_provision.Prov(base, run2, log=lambda m: None, spi=lambda path: True)
    n = p.firstboot()
    ran = [os.path.relpath(c[-1], fb).replace(os.sep, "/") for c in calls if "firstboot.d" in " ".join(c)]
    ck("bản 1511: chạy script chung trước rồi tới thư mục 1511 (theo tên), KHÔNG chạy thư mục 22h2 / thư mục lạ / file .exe", n == 4 and ran == ["10-chung.ps1", "20-chung.cmd", "1511/05-lan.cmd", "1511/50-vga.bat"], ran)
    ck("script đọc được biến CB_OS = tên bản đang cài", envs == ["1511"] * 4, envs)
    ck("os_tag: đọc từ seed.json; thiếu / sai dạng → rỗng", p.os_tag() == "1511")
    open(os.path.join(base, "seed.json"), "w").write(json.dumps({"os": "../x"})); ck("os_tag sai dạng → rỗng", p.os_tag() == "")
    os.remove(os.path.join(base, "seed.json")); ck("không có seed.json → rỗng", p.os_tag() == "")
with tempfile.TemporaryDirectory() as base:
    fb = os.path.join(base, "os", "firstboot.d"); os.makedirs(os.path.join(fb, "22h2")); os.makedirs(os.path.join(fb, "22h2-2")); os.makedirs(os.path.join(base, "logs"))
    for f in ("22h2/a.cmd", "22h2-2/b.cmd", "c.cmd"): open(os.path.join(fb, *f.split("/")), "w").write("x")
    open(os.path.join(base, "seed.json"), "w").write(json.dumps({"os": "22h2-2"}))
    store, calls, run = fake_reg()
    p = cb_provision.Prov(base, run, log=lambda m: None, spi=lambda path: True); p.firstboot()
    ran = [os.path.relpath(c[-1], fb).replace(os.sep, "/") for c in calls if "firstboot.d" in " ".join(c)]
    ck("bản 22h2-2: chạy chung → thư mục 22h2-2 → thư mục 22h2", ran == ["c.cmd", "22h2-2/b.cmd", "22h2/a.cmd"], ran)

print("7. Bản 1511: driver card mạng xong (máy có mạng) rồi mới cài driver VGA NVIDIA; tiến độ in ra màn hình")
NV = "466.77-notebook-win10-64bit-international-whql.exe"
def vga_env(tag="1511", gpu=(True, False), after=(True, True), net=True, packs=("1511/" + NV,), extra=()):
    pr0, st = sec_env({"user": "PC", "password": "", "sb_url": "https://abcdxyz.supabase.co"})
    fb = os.path.join(st["base"], "os", "firstboot.d")
    for f in tuple(packs) + tuple(extra):
        os.makedirs(os.path.dirname(os.path.join(fb, *f.split("/"))), exist_ok=True)
        if not os.path.exists(os.path.join(fb, *f.split("/"))): open(os.path.join(fb, *f.split("/")), "wb").write(b"EXE")
    open(os.path.join(st["base"], "seed.json"), "w").write(json.dumps({"os": tag}))
    st.update(gpu=gpu, after=after, net=net, said=[], slept=0, net_calls=[], log=[], fb=fb, vga_runs=0)
    base_run = pr0._run

    def run(argv, timeout=300):
        if cb_provision.NVIDIA_RE.match(os.path.basename(argv[0])):                # bộ cài VGA chạy ~10 phút; xong thì card nhận driver (hoặc không, tuỳ phép thử)
            st["calls"].append(list(argv)); st["vga_runs"] += 1; st["clock"] += 600; st["gpu"] = st["after"]; st["vga_timeout"] = timeout
            return st.get("vga_rc", 0), ""
        return base_run(argv, timeout)

    def net_fn(host, port):
        st["net_calls"].append((host, port))
        return st["net"](st) if callable(st["net"]) else st["net"]

    def sleep(sec): st["clock"] += sec; st["slept"] += sec
    pr = cb_provision.Prov(st["base"], run, log=st["log"].append, spi=lambda path: True, admin=True, rec=lambda: "", now=lambda: st["clock"],
                           net=net_fn, gpu=lambda: st["gpu"], sleep=sleep, say=st["said"].append)
    return pr, st
vstate = lambda st: json.load(open(os.path.join(st["base"], "logs", "vga.json")))
has_pack = lambda st, rel="1511/" + NV: os.path.exists(os.path.join(st["fb"], *rel.split("/")))
idx = lambda st, word: next((i for i, c in enumerate(st["calls"]) if word in " ".join(c)), -1)

pr, st = vga_env()
ck("nơi thử mạng = máy chủ của hệ thống (sb_url trong cb.json), cổng 443", pr.net_target() == ("abcdxyz.supabase.co", 443))
open(os.path.join(st["base"], "cb.json"), "w").write(json.dumps({"user": "PC"}))
ck("không có sb_url → thử địa chỉ kiểm mạng của Microsoft", pr.net_target() == ("www.msftconnecttest.com", 80))
pr, st = vga_env()
ck("net_wait: có mạng ngay → 0 giây, không chờ", pr.net_wait(240) == 0 and st["slept"] == 0 and st["net_calls"] == [("abcdxyz.supabase.co", 443)])
pr, st = vga_env(net=lambda s: s["clock"] >= 1_000_000 + 30)
w = pr.net_wait(240)
ck("net_wait: 30 giây sau mới có mạng → chờ đúng chừng đó rồi đi tiếp", w == 30 and st["slept"] == 30, (w, st["slept"]))
pr, st = vga_env(net=False)
ck("net_wait: mãi không có mạng → trả None sau đúng hạn chờ (không chờ vô hạn)", pr.net_wait(60) is None and 60 <= st["slept"] <= 63, st["slept"])
pr, st = vga_env(net=lambda s: 1 / 0)
ck("net_wait: hàm thử mạng lỗi → coi như chưa có mạng, không ném lỗi", pr.net_wait(6) is None)

pr, st = vga_env(extra=("1511/05-lan.cmd",))
pr.firstlogon()
i_lan, i_vga, i_grp, i_boot = idx(st, "05-lan.cmd"), idx(st, NV), idx(st, "/passwordchg:no"), idx(st, "shutdown /r")
ck("lần đăng nhập đầu, bản 1511, máy có card NVIDIA + có mạng: lệnh riêng (driver LAN) → thử mạng → cài VGA → khoá tài khoản → khởi động lại",
   0 <= i_lan < i_vga < i_grp < i_boot and st["net_calls"] and st["calls"][i_vga][1:] == ["-s", "-noreboot"] and st["vga_timeout"] == 2400, (i_lan, i_vga, i_grp, i_boot, st["net_calls"]))
ck("cài xong: card đã nhận driver → ghi 'done', xoá bản chép gói 700MB trên ổ C:", vstate(st)["state"] == "done" and vstate(st)["tries"] == 1 and not has_pack(st) and st["vga_runs"] == 1, vstate(st))
said = "\n".join(st["said"])
ck("tiến độ in ra màn hình đủ 5 bước, chữ không dấu, có nhắc KHÔNG tắt máy + tự khởi động lại", all(k in said for k in ["dang hoan tat cai dat Windows 1511", "KHONG tat may", "[1/5]", "[2/5]", "05-lan.cmd", "[3/5]", "da co mang", "[4/5]", NV,
   "xong - card da nhan driver", "[5/5]", "XONG. May tu khoi dong lai sau 20 giay."]) and said.isascii(), said)
ck("nhật ký ghi rõ đã có mạng + driver VGA đã vào", any("may da co mang" in x for x in st["log"]) and any("driver VGA NVIDIA da vao" in x for x in st["log"]))

pr, st = vga_env(net=False)
pr.firstlogon()
said = "\n".join(st["said"])
ck("CHƯA có mạng (driver card mạng chưa chạy): chờ đủ 4 phút rồi KHÔNG cài VGA, giữ nguyên gói, ghi 'wait'", st["vga_runs"] == 0 and has_pack(st) and vstate(st) == {"state": "wait", "tries": 0, "at": vstate(st)["at"]} and 240 <= st["slept"] <= 243, (st["slept"], vstate(st)))
ck("… báo rõ trên màn hình: chưa có mạng, kiểm tra dây mạng / driver card mạng, VGA sẽ tự cài sau", all(k in said for k in ["!! CHUA CO MANG sau 4 phut", "day mang / driver card mang", "CHUA cai (chua co mang) - se tu cai khi may co mang"]), said)
ck("… các bước còn lại vẫn chạy hết (khoá tài khoản, khởi động lại) — không treo lần đăng nhập đầu", idx(st, "shutdown /r") > 0 and os.path.exists(os.path.join(st["base"], "logs", "firstlogon.done")) and st["admins"] == ["Administrator"])
st["net"] = True; st["calls"].clear(); st["net_calls"].clear(); pr.system()
ck("sau đó máy có mạng → agent (SYSTEM) gọi pha system: cài nốt VGA, xoá gói", st["vga_runs"] == 1 and vstate(st)["state"] == "done" and not has_pack(st) and st["net_calls"], vstate(st))
st["calls"].clear(); pr.system()
ck("các lần soát sau không cài lại", st["vga_runs"] == 1 and idx(st, NV) == -1)

pr, st = vga_env(gpu=(False, False), net=False)
pr.firstlogon()
ck("máy KHÔNG có card NVIDIA (máy ảo, máy dùng card khác): bỏ qua gói VGA, xoá bản chép, không chờ mạng 4 phút vì VGA", st["vga_runs"] == 0 and not has_pack(st) and vstate(st)["state"] == "skip" and 60 <= st["slept"] <= 63
   and "may nay khong co card NVIDIA - bo qua" in "\n".join(st["said"]), (st["slept"], st["said"]))
pr, st = vga_env(gpu=(True, True))
pr.firstlogon()
ck("card NVIDIA đã có driver sẵn → không chạy bộ cài, ghi 'done'", st["vga_runs"] == 0 and vstate(st)["state"] == "done" and not has_pack(st))
pr, st = vga_env(gpu=(None, None), after=(None, None))
pr.firstlogon()
ck("không đọc được danh sách thiết bị → vẫn cài 1 lần rồi coi như xong (không chạy lại mãi)", st["vga_runs"] == 1 and vstate(st)["state"] == "done" and not has_pack(st))
pr, st = vga_env(tag="22h2")
pr.firstlogon()
ck("đang cài bản 22H2: gói VGA của riêng bản 1511 không được đụng tới", st["vga_runs"] == 0 and has_pack(st) and not os.path.exists(os.path.join(st["base"], "logs", "vga.json")) and "khong co goi VGA nao" in "\n".join(st["said"]))
pr, st = vga_env(tag="22h2", packs=(NV, "nvidia-vga-cua-toi.exe"))
pr.firstlogon()
ck("gói VGA để ở firstboot.d gốc (mọi bản) → bản nào cũng cài; nhiều gói thì cài lần lượt theo tên", [os.path.basename(c[0]) for c in st["calls"] if cb_provision.NVIDIA_RE.match(os.path.basename(c[0]))] == [NV, "nvidia-vga-cua-toi.exe"]
   and not has_pack(st, NV) and not has_pack(st, "nvidia-vga-cua-toi.exe"))

pr, st = vga_env(after=(True, False))
pr.firstlogon()
ck("bộ cài chạy xong mà card CHƯA nhận driver → ghi 'fail' lần 1, GIỮ gói để thử lại, báo trên màn hình", st["vga_runs"] == 1 and vstate(st)["state"] == "fail" and vstate(st)["tries"] == 1 and has_pack(st)
   and "card chua nhan driver" in "\n".join(st["said"]), vstate(st))
st["gpu"] = (True, True); pr.system()
ck("sau khởi động lại card đã nhận driver → pha system chỉ kiểm lại, ghi 'done', không chạy bộ cài lần 2", st["vga_runs"] == 1 and vstate(st)["state"] == "done" and not has_pack(st))
pr, st = vga_env(after=(True, False))
pr.firstlogon(); pr.system(); pr.system(); pr.system(); pr.system()
ck("card mãi không nhận driver → chạy bộ cài tối đa 3 lần rồi thôi (không lặp vô hạn), ghi rõ vào nhật ký", st["vga_runs"] == 3 and vstate(st)["state"] == "gave-up" and vstate(st)["tries"] == 3
   and sum("thoi khong thu nua" in x for x in st["log"]) == 1, (st["vga_runs"], vstate(st)))
pr, st = vga_env(net=False)
os.remove(os.path.join(st["base"], "logs", "firstlogon.done")) if os.path.exists(os.path.join(st["base"], "logs", "firstlogon.done")) else None
pr.touch("firstlogon.start"); st["net"] = True; pr.system()
ck("lần đăng nhập đầu ĐANG chạy (chưa xong) → pha system không đụng tới VGA (khỏi cài chồng 2 lần cùng lúc)", st["vga_runs"] == 0 and has_pack(st))

pr, st = vga_env(extra=("1511/50-vga-nvidia.cmd", "50-vga-nvidia.cmd", "1511/10-lan.cmd"))
open(os.path.join(st["fb"], "1511", "50-vga-nvidia.cmd"), "wb").write(b'@echo off\r\nrem CloudBlue PC: cai driver VGA NVIDIA im lang o lan dang nhap dau (file nay do bo tao ISO tu sinh)\r\n"%~dp0x.exe" -s -noreboot\r\n')
open(os.path.join(st["fb"], "50-vga-nvidia.cmd"), "wb").write(b"@echo off\r\nrem lenh cua chu shop, trung ten\r\n")
n = pr.firstboot()
ran = [os.path.relpath(c[-1], st["fb"]).replace(os.sep, "/") for c in st["calls"] if c[0] == "cmd.exe" and "firstboot.d" in " ".join(c)]
ck("file 50-vga-nvidia.cmd do bộ tạo ISO bản cũ sinh → bỏ qua (bước VGA tự cài sau khi có mạng); file trùng tên của chủ shop vẫn chạy", ran == ["10-driver.cmd", "50-vga-nvidia.cmd", "1511/10-lan.cmd"] and n == 3, ran)
cmd = open(os.path.join(REPO, "os", "provision.cmd"), "rb").read().decode("ascii")
ck("provision.cmd: lần đăng nhập đầu chạy nhánh riêng — KHÔNG nuốt chữ in ra (tiến độ hiện trên cửa sổ), lỗi vẫn ghi vào provision.out, chờ vài giây cho kịp đọc",
   'if /i "%~1"=="firstlogon" goto show' in cmd and '\r\n:show\r\n' in cmd and 'cb_provision.py" %* 2>> "%CBLOG%\\provision.out"\r\nping -n 9 127.0.0.1 >nul 2>&1\r\nexit /b 0' in cmd and cmd.count("exit /b 0") == 2 and cmd.isascii(), cmd)
ck("real_nvidia_state / real_net có sẵn cho Windows thật; trên máy không phải Windows trả 'không biết' chứ không ném lỗi", REAL_GPU() == (None, None) and REAL_NET("127.0.0.1", 9, 0.2) is False)

print("7b. Bước DRIVER CARD MẠNG (bản 21.11c): thiết bị chưa có driver → cài từ kho driver TRƯỚC khi chờ mạng; có mạng rồi mới tới VGA")
D_LAN_OFF = {"name": "Ethernet Controller", "cls": "", "id": "PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15\\4&1", "problem": 28, "service": "", "compat": ["PCI\\CC_020000", "PCI\\CC_0200"]}
D_LAN_ON = {"name": "Realtek PCIe GbE Family Controller", "cls": "Net", "id": D_LAN_OFF["id"], "problem": 0, "service": "rt640x64", "compat": ["PCI\\CC_020000"]}
D_SMBUS = {"name": "SM Bus Controller", "cls": "", "id": "PCI\\VEN_8086&DEV_A323\\3&2", "problem": 28, "service": "", "compat": ["PCI\\CC_0C0500"]}
D_VGA_BASIC = {"name": "Microsoft Basic Display Adapter", "cls": "Display", "id": "PCI\\VEN_10DE&DEV_1C8D\\4&3", "problem": 0, "service": "BasicDisplay", "compat": ["PCI\\CC_030000"]}
D_SOFT = {"name": "WAN Miniport (IP)", "cls": "Net", "id": "SWD\\MSRRAS\\MS_NDISWANIP", "problem": 0, "service": "NdisWan", "compat": []}
D_SOFT_BAD = {"name": "Teredo Tunneling Pseudo-Interface", "cls": "Net", "id": "SWD\\IP_TUNNEL_VBUS\\TEREDO", "problem": 10, "service": "tunnel", "compat": []}
D_OFF = {"name": "Intel Wireless-AC 9560", "cls": "Net", "id": "PCI\\VEN_8086&DEV_9DF0\\3&9", "problem": 22, "service": "Netwtw08", "compat": []}
NET_INF, VGA_INF = "C:\\Windows\\System32\\DriverStore\\FileRepository\\rt640x64.inf_amd64_0123\\rt640x64.inf", "C:\\Windows\\System32\\DriverStore\\FileRepository\\nv_dispi.inf_amd64_9\\nv_dispi.inf"
def drv_env(devs, fix_after_kick=None, fix_after_pnputil=False, staged=(), pnp_ok=True, **kw):
    """devs: thiết bị lúc đầu. fix_after_kick = số giây sau khi 'dò lại phần cứng' thì card mạng nhận driver (None = không bao giờ). fix_after_pnputil: chạy pnputil xong thì nhận."""
    pr, st = vga_env(**kw)
    st.update(devs=list(devs), kick_at=None, kicks=0, pnputil=[])
    def cur():
        if fix_after_kick is not None and st["kick_at"] is not None and st["clock"] - st["kick_at"] >= fix_after_kick:
            st["devs"] = [D_LAN_ON if d is D_LAN_OFF else d for d in st["devs"]]
        return list(st["devs"])
    def kick():
        st["kicks"] += 1; st["kick_at"] = st["clock"]; st["calls"].append(["<pnp-retry>"])
        if pnp_ok is None: raise OSError("khong goi duoc cfgmgr32")
        return pnp_ok
    inner = pr._run
    def run(argv, timeout=300):
        if os.path.basename(argv[0]).lower() == "pnputil.exe":
            st["calls"].append(list(argv)); st["pnputil"].append(list(argv[1:]))
            if fix_after_pnputil: st["devs"] = [D_LAN_ON if d is D_LAN_OFF else d for d in st["devs"]]
            return (0 if fix_after_pnputil else 259), "Microsoft PnP Utility"
        return inner(argv, timeout)
    pr._run, pr._devs, pr._pnp, pr._staged = run, cur, kick, (lambda: list(staged))
    return pr, st
dstate = lambda st: json.load(open(os.path.join(st["base"], "logs", "drv.json")))
STAGED = ({"pub": "oem3.inf", "inf": NET_INF, "cls": "net"}, {"pub": "oem4.inf", "inf": VGA_INF, "cls": "display"})

sm = C.drv_summary([D_LAN_OFF, D_LAN_ON, D_SMBUS, D_VGA_BASIC, D_SOFT, D_SOFT_BAD, D_OFF])
ck("tóm tắt thiết bị: card mạng chưa có driver đứng đầu (kèm hãng + mã phần cứng), thiết bị phần mềm / thiết bị người dùng tắt không tính là thiếu driver",
   [C.drv_label(x) for x in sm["miss"]] == ["Ethernet Controller [Realtek 10EC:8168]", "SM Bus Controller [Intel 8086:A323]"] and sm["net_miss"] == 1
   and sm["nics"] == ["Realtek PCIe GbE Family Controller"] and sm["vga_basic"] == 1 and sm["vga_ok"] == 0, sm)
ck("bản gọn gửi về web: số thiết bị thiếu, tên, card mạng thiếu driver, VGA đang chạy driver cơ bản", C.drv_brief(sm) == {"miss": 2, "names": ["Ethernet Controller [Realtek 10EC:8168]",
   "SM Bus Controller [Intel 8086:A323]"], "net": "miss", "vga": "basic"} and C.drv_brief(C.drv_summary([D_LAN_ON])) == {"miss": 0, "names": [], "net": "ok", "vga": "ok"}
   and C.drv_brief(C.drv_summary([D_SOFT]))["net"] == "none", C.drv_brief(sm))
ck("tên thiết bị có ký tự lạ / dài → nhãn chỉ còn chữ ASCII, cắt ngắn; dữ liệu hỏng không làm lỗi", C.drv_label({"n": "Thiết bị ® lạ" + "x" * 90, "hw": "", "v": ""}).isascii()
   and len(C.drv_label({"n": "y" * 200})) <= 60 and C.drv_summary([None, 5, {"problem": "abc", "id": None}, {"name": None, "problem": 28, "id": "USB\\VID_0BDA&PID_8179\\1"}])["miss"]
   == [{"n": "?", "e": 28, "k": "", "hw": "0BDA:8179", "v": "Realtek"}])
ck("đọc lớp driver trong file .inf: ANSI / UTF-16, theo mã lớp (không phụ thuộc chữ), chỉ đọc phần [Version]",
   C.inf_class(b"; x\r\n[Version]\r\nSignature=\"$Windows NT$\"\r\nClass = Net\r\nClassGUID={4D36E972-E325-11CE-BFC1-08002BE10318}\r\n[Manufacturer]\r\nClass=Display\r\n") == "net"
   and C.inf_class("[version]\r\nClass=\"LAN gi do\"\r\nClassGuid = {4d36e972-e325-11ce-bfc1-08002be10318} ; mang\r\n".encode("utf-16")) == "net"
   and C.inf_class("[Version]\r\nClass=Display\r\n".encode("utf-16-le")) == "display" and C.inf_class(b"[Strings]\r\nClass=Net\r\n") == "" and C.inf_class(b"") == ""
   and C.inf_class(b"[Version]\nClass=HDC\n") == "hdc")

pr, st = drv_env([D_LAN_ON, D_SOFT, D_OFF])
r = pr.drivers()
ck("mọi thiết bị đã có driver → không đụng gì (không dò lại phần cứng, không pnputil, không chờ), ghi lại tình trạng", r["miss"] == [] and r["nics"] == ["Realtek PCIe GbE Family Controller"]
   and st["kicks"] == 0 and st["pnputil"] == [] and st["slept"] == 0 and dstate(st)["kicks"] == 0 and dstate(st)["miss"] == [] and any("moi thiet bi da co driver" in x for x in st["log"]), (r, st["slept"]))
pr, st = drv_env([D_LAN_OFF, D_SMBUS], fix_after_kick=10)
r = pr.drivers()
ck("card mạng chưa có driver → bảo Windows dò lại phần cứng + cài từ kho driver; 10 giây sau card nhận → đi tiếp ngay, KHÔNG cần pnputil",
   st["kicks"] == 1 and st["pnputil"] == [] and r["nics"] == ["Realtek PCIe GbE Family Controller"] and r["net_miss"] == 0 and st["slept"] == 10 and dstate(st)["kicks"] == 1
   and dstate(st)["miss"] == ["SM Bus Controller [Intel 8086:A323]"], (r, st["slept"], st["pnputil"]))
ck("… nhật ký ghi rõ thiết bị nào chưa có driver lúc đầu và sau bước driver", any("thiet bi CHUA CO DRIVER: 2 (Ethernet Controller [Realtek 10EC:8168]; SM Bus Controller" in x for x in st["log"])
   and any("sau buoc driver: con 1 thiet bi chua co driver" in x and "card mang da nhan driver: Realtek PCIe GbE" in x for x in st["log"]), st["log"])
pr, st = drv_env([D_LAN_OFF], fix_after_pnputil=True, staged=STAGED)
r = pr.drivers()
ck("dò lại phần cứng 30 giây vẫn chưa nhận → chạy pnputil -i -a CHỈ cho gói driver card mạng trong kho (không đụng gói VGA) → card nhận",
   st["kicks"] == 1 and st["pnputil"] == [["-i", "-a", NET_INF]] and r["nics"] and not r["miss"] and 30 <= st["slept"] <= 40 and idx(st, "<pnp-retry>") < idx(st, "pnputil.exe"), (st["pnputil"], st["slept"], r))
pr, st = drv_env([D_LAN_OFF], staged=(STAGED[1],))
r = pr.drivers()
ck("kho driver không có gói driver card mạng nào → không chạy pnputil, ghi rõ vào nhật ký, card vẫn thiếu driver (không treo)",
   st["pnputil"] == [] and r["net_miss"] == 1 and not r["nics"] and any("KHONG co goi driver card mang nao" in x for x in st["log"]) and dstate(st)["net_miss"] == 1 and st["slept"] <= 35, (r, st["slept"]))
pr, st = drv_env([D_LAN_OFF], staged=tuple({"pub": "oem%d.inf" % i, "inf": NET_INF.replace("0123", "%04d" % i), "cls": "net"} for i in range(30)))
pr.drivers()
ck("kho có rất nhiều gói driver mạng → chạy tối đa 12 gói (không kéo dài lần cài)", len(st["pnputil"]) == 12)
pr, st = drv_env([D_LAN_ON, D_SMBUS])
r = pr.drivers()
ck("card mạng đã chạy, chỉ thiếu driver thiết bị khác → vẫn bảo Windows cài lại (đủ driver), chờ 5 giây rồi đi tiếp, không pnputil", st["kicks"] == 1 and st["slept"] == 5 and st["pnputil"] == [] and len(r["miss"]) == 1)
pr, st = drv_env([D_LAN_OFF], pnp_ok=None, fix_after_pnputil=True, staged=STAGED)
r = pr.drivers()
ck("không gọi được lệnh dò lại phần cứng → không sập, vẫn thử pnputil", r is not None and st["pnputil"] == [["-i", "-a", NET_INF]] and r["nics"])
pr, st = drv_env([D_LAN_OFF]); pr._devs = lambda: None
ck("không đọc được danh sách thiết bị → bỏ qua bước driver (Windows tự nhận như cũ), không chờ", pr.drivers() is None and st["kicks"] == 0 and st["slept"] == 0 and not os.path.exists(os.path.join(st["base"], "logs", "drv.json")))
pr, st = drv_env([D_LAN_OFF]); pr._devs = lambda: 1 / 0
ck("hàm đọc thiết bị lỗi → coi như không đọc được, không ném lỗi", pr.drivers() is None and pr.drv_retry() is None)
pr, st = drv_env([D_LAN_OFF], fix_after_pnputil=True, staged=({"pub": "oem7.inf", "inf": os.path.join(st["base"], "khong-co.inf")},))
real_inf = os.path.join(st["base"], "lan.inf"); open(real_inf, "wb").write(b"[Version]\r\nClass=Net\r\nClassGuid={4d36e972-e325-11ce-bfc1-08002be10318}\r\n")
pr._staged = lambda: [{"pub": "oem7.inf", "inf": os.path.join(st["base"], "khong-co.inf")}, {"pub": "oem8.inf", "inf": real_inf}]
pr.drivers()
ck("gói trong kho không ghi sẵn lớp → tự đọc file .inf để biết là driver mạng; file không đọc được thì bỏ qua", st["pnputil"] == [["-i", "-a", real_inf]], st["pnputil"])

pr, st = drv_env([D_LAN_OFF, D_VGA_BASIC], fix_after_kick=5, extra=("1511/05-lan.cmd",))
pr.firstlogon()
i_fb, i_kick, i_vga, i_grp, i_boot = idx(st, "05-lan.cmd"), idx(st, "<pnp-retry>"), idx(st, NV), idx(st, "/passwordchg:no"), idx(st, "shutdown /r")
said = "\n".join(st["said"])
ck("lần đăng nhập đầu bản 1511: lệnh riêng → DRIVER CARD MẠNG → thử mạng → VGA NVIDIA → khoá tài khoản → khởi động lại (đúng thứ tự LAN trước, VGA sau)",
   0 <= i_fb < i_kick < i_vga < i_grp < i_boot and st["net_calls"] and st["vga_runs"] == 1, (i_fb, i_kick, i_vga, i_grp, i_boot))
ck("… màn hình ghi bước 3 là driver card mạng, báo số thiết bị chưa có driver và card mạng đã nhận", all(k in said for k in ["[3/5] Driver card mang, roi cho may co mang",
   "1 thiet bi chua co driver -> cai tu goi driver kem theo (card mang truoc)", "card mang da nhan driver: Realtek PCIe GbE Family Controller", "da co mang"]) and said.isascii(), said)
pr, st = drv_env([D_LAN_OFF, D_SMBUS], net=False)
pr.firstlogon()
said = "\n".join(st["said"])
ck("card mạng KHÔNG có driver phù hợp trong gói kèm theo: màn hình báo đúng tên thiết bị + hãng + mã phần cứng để tìm driver",
   all(k in said for k in ["con 2 thiet bi chua co driver: Ethernet Controller [Realtek 10EC:8168]; SM Bus Controller [Intel 8086:A323]", "!! CARD MANG CHUA CO DRIVER: Ethernet Controller [Realtek 10EC:8168]",
   "Goi driver kem theo khong co driver cho loai card nay", "!! CHUA CO MANG sau 1 phut"]) and said.isascii(), said)
ck("… chưa card mạng nào nhận driver → chỉ chờ mạng 1 phút (không chờ 4 phút vô ích), CHƯA cài VGA, các bước sau vẫn chạy hết", st["vga_runs"] == 0 and vstate(st)["state"] == "wait"
   and 90 <= st["slept"] <= 100 and idx(st, "shutdown /r") > 0, st["slept"])
st["devs"] = [D_LAN_OFF, D_SMBUS]; st["calls"].clear(); k0 = st["kicks"]
pr.system(); pr.system(); pr.system(); pr.system()
ck("sau đó agent (pha system) thử lại bước driver — cả máy tối đa 3 lần rồi thôi (không lặp mãi)", st["kicks"] == 3 and k0 == 1 and dstate(st)["kicks"] == 3, (k0, st["kicks"]))
pr, st = drv_env([D_LAN_OFF], net=False)
pr.firstlogon(); st["devs"] = [D_LAN_ON]; st["net"] = True; k0 = st["kicks"]; pr.system()
ck("máy sau đó đã có card mạng chạy → pha system không chạy lại bước driver, cài nốt VGA", st["kicks"] == k0 and st["vga_runs"] == 1 and dstate(st)["net_miss"] == 0)
pr, st = drv_env([D_LAN_ON, D_SOFT], net=False)
pr.firstlogon()
ck("card mạng đã có driver mà vẫn chưa có mạng (dây mạng?) → vẫn chờ đủ 4 phút cho VGA như cũ", 240 <= st["slept"] <= 243 and "card mang da nhan driver" in "\n".join(st["said"]), st["slept"])

print("8. Dịch vụ khởi động (pha boot — lưới an toàn thứ 3): bản Windows không chạy file trả lời lẫn SetupComplete.cmd thì agent vẫn lên")
def boot_env(admin=True):
    pr0, st = sec_env({"user": "PC", "password": ""})
    st["slept"] = 0
    def sleep(sec): st["slept"] += sec; st["clock"] += sec
    pr = cb_provision.Prov(st["base"], pr0._run, log=st.setdefault("log", []).append, spi=lambda path: True, admin=admin, rec=lambda: "", now=lambda: st["clock"], sleep=sleep, say=lambda m: None)
    return pr, st
J = lambda st: [" ".join(c) for c in st["calls"]]
pr, st = boot_env(); st["fail"].add("schtasks /query")                               # chưa có tác vụ nào
r = pr.boot(); j = J(st)
ck("chưa có tác vụ agent → tự làm phần specialize: chính sách, điện năng, tạo 2 tác vụ, khoá quyền thư mục", r is True and any("DisablePrivacyExperience" in x for x in j) and any(x == "powercfg /hibernate off" for x in j)
   and any("schtasks /create /tn CloudBluePC Agent /xml" in x for x in j) and any("CloudBluePC Watch /sc minute /mo 5" in x for x in j) and any(x.startswith("icacls") for x in j), j[:6])
ck("… rồi bật agent và TỰ GỠ dịch vụ khởi động (hết việc)", j.index("schtasks /run /tn CloudBluePC Agent") < j.index("sc delete CloudBluePCBoot") and st["slept"] == 0, j[-4:])
pr, st = boot_env()
r = pr.boot(); j = J(st)
ck("đã có tác vụ (file trả lời đã chạy bình thường) → không tạo lại gì, chỉ bật agent + gỡ dịch vụ", r is True and not any("schtasks /create" in x or x.startswith("icacls") or x.startswith("powercfg") for x in j)
   and "schtasks /run /tn CloudBluePC Agent" in j and "sc delete CloudBluePCBoot" in j, j)
pr, st = boot_env(); st["fail"].update({"schtasks /query", "schtasks /create"})
r = pr.boot(); j = J(st)
ck("dịch vụ tác vụ của Windows chưa sẵn sàng (tạo tác vụ lỗi mãi) → thử lại ~2 phút rồi thôi, GIỮ dịch vụ để lần bật máy sau làm tiếp", r is False and st["slept"] == 120 and "sc delete CloudBluePCBoot" not in j
   and sum("CloudBluePC Agent /xml" in x for x in j) == 12 and any("LOI boot" in x for x in st["log"]), (st["slept"], j[-3:]))
pr, st = boot_env(); st["fail"].add("schtasks /query")
n = {"k": 0}
real_run = pr._run
def flaky(argv, timeout=300):
    if argv[:2] == ["schtasks", "/create"]:
        n["k"] += 1
        if n["k"] <= 6: st["calls"].append(list(argv)); return 1, "ERROR: The Task Scheduler service is not available."
    return real_run(argv, timeout)
pr._run = flaky
r = pr.boot(); j = J(st)
ck("tạo tác vụ lỗi vài lần đầu rồi được → vẫn xong trong lần bật máy này", r is True and st["slept"] == 20 and "sc delete CloudBluePCBoot" in j, (st["slept"], n))
pr, st = boot_env(admin=False)
ck("không phải SYSTEM / quản trị gọi → không làm gì", pr.boot() is False and st["calls"] == [])
ck("cb_provision và cbcore dùng CÙNG tên dịch vụ", cb_provision.BOOT_SVC == C.BOOT_SVC == "CloudBluePCBoot" and all(c[2].endswith("\\Services\\" + C.BOOT_SVC) for c in C.boot_service_cmds("HKLM\\X", 3))
   and C.boot_service_cmds("HKLM\\X", 3)[0][2] == "HKLM\\X\\ControlSet003\\Services\\CloudBluePCBoot")

print("9. BẢN WINDOWS KIỂU GHOST (ảnh chụp máy đã cài sẵn — không chạy file trả lời): dịch vụ khởi động tự dựng tài khoản khách, đổi tên máy, khoá, khởi động lại")
SETUP_IDLE = "\r\nHKEY_LOCAL_MACHINE\\SYSTEM\\Setup\r\n    OsLoaderPath    REG_SZ    \\\r\n    SystemSetupInProgress    REG_DWORD    0x0\r\n    SetupType    REG_DWORD    0x0\r\n    CmdLine    REG_SZ    \r\n    OOBEInProgress    REG_DWORD    0x0\r\n"
SETUP_BUSY = SETUP_IDLE.replace("SystemSetupInProgress    REG_DWORD    0x0", "SystemSetupInProgress    REG_DWORD    0x1").replace("CmdLine    REG_SZ    ", "CmdLine    REG_SZ    oobe\\windeploy.exe")
def ghost_env(cfg=None, users=None, auto="admin", last=".\\admin", oobe=False, setup=SETUP_IDLE, tasks=False, blank=True, seed="CB-E3B72F", host="DESKTOP-DKDCA09"):
    """Máy Windows giả có sẵn tài khoản (như ảnh ghost): users = [(tên, rid, đang tắt, thuộc nhóm quản trị)]."""
    pr0, st = sec_env(cfg or {"user": "PC", "password": ""})
    base = st["base"]
    us = users if users is not None else [("Administrator", 500, True, True), ("Guest", 501, True, False), ("DefaultAccount", 503, True, False), ("admin", 1001, False, True)]
    st.update(u=[{"name": n, "rid": r, "off": o} for n, r, o, _ in us], admins=[n for n, _, _, a in us if a], users=[], pw={}, slept=0, msgs=[], log=[], newname=None,
              auto=auto, last=last, setup=setup, tasks=tasks, ps_users=True, ren_ok=True, blank=blank)
    if oobe is not None: open(os.path.join(base, "logs", "image.json"), "w").write(json.dumps({"oobe": oobe, "control_set": 1, "boot_svc": True}))
    open(os.path.join(base, "seed.json"), "w").write(json.dumps({"name": seed, "os": "1511"}))
    os.environ["COMPUTERNAME"] = host
    base_run = pr0._run
    find = lambda n: next((x for x in st["u"] if x["name"].lower() == n.lower()), None)
    def run(argv, timeout=300):
        a = " ".join(argv)
        if argv[0] == "powershell.exe" and "Win32_UserAccount -Filter 'LocalAccount=True' | ForEach-Object" in a:
            st["calls"].append(list(argv))
            if not st["ps_users"]: return 1, "loi WMI"
            return 0, "".join("U=%s|S-1-5-21-1111-2222-3333-%d|%s|\r\n" % (x["name"], x["rid"], x["off"]) for x in st["u"]) + "U_END\r\n"
        if argv[0] == "powershell.exe" and ".psbase.Rename(" in a:
            st["calls"].append(list(argv)); m = re.search(r"WinNT://\./(.+?),user'\); \$u\.psbase\.Rename\('(.+?)'\)", a)
            if not st["ren_ok"] or not m or not find(m.group(1)): return 1, "loi"
            old = find(m.group(1))["name"]; find(old)["name"] = m.group(2)
            st["admins"] = [m.group(2) if x == old else x for x in st["admins"]]; st["users"] = [m.group(2) if x == old else x for x in st["users"]]
            return 0, "RN_OK\r\n"
        if argv[0] == "wmic" and "useraccount" in argv: st["calls"].append(list(argv)); return 1, "loi"
        if argv[0] == "powershell.exe" and "Rename-Computer" in a:
            st["calls"].append(list(argv)); st["newname"] = re.search(r"-NewName '(.+?)'", a).group(1); return 0, "RC_OK\r\n"
        if argv[:2] == ["reg", "query"] and argv[2] == "HKLM\\SYSTEM\\Setup": st["calls"].append(list(argv)); return (0, st["setup"]) if st["setup"] else (1, "")
        if argv[:2] == ["reg", "query"] and argv[-1] == "DefaultUserName": st["calls"].append(list(argv)); return (0, "\r\n    DefaultUserName    REG_SZ    %s\r\n" % st["auto"]) if st["auto"] else (1, "")
        if argv[:2] == ["reg", "query"] and argv[-1] == "LastLoggedOnSAMUser": st["calls"].append(list(argv)); return (0, "\r\n    LastLoggedOnSAMUser    REG_SZ    %s\r\n" % st["last"]) if st["last"] else (1, "")
        if argv[:2] == ["schtasks", "/query"]: st["calls"].append(list(argv)); return (0, "") if st["tasks"] else (1, "")
        if argv[:2] == ["schtasks", "/create"]: st["tasks"] = True
        if argv[:2] == ["net", "user"] and len(argv) == 3: st["calls"].append(list(argv)); return (0, "") if find(argv[2]) else (2, "The user name could not be found.")
        if argv[:2] == ["net", "user"] and argv[-1] == "/add":
            st["calls"].append(list(argv))
            if find(argv[2]): return 2, "The account already exists."
            st["u"].append({"name": argv[2], "rid": 1000 + len(st["u"]), "off": False}); st["users"].append(argv[2]); st["pw"][argv[2]] = argv[3]; return 0, ""
        if argv[:2] == ["net", "user"] and len(argv) == 4 and argv[3].startswith("/active:"):
            st["calls"].append(list(argv)); x = find(argv[2])
            if not x: return 2, ""
            x["off"] = argv[3] == "/active:no"; return 0, ""
        if argv[:2] == ["net", "user"] and len(argv) == 5 and argv[4] == "/active:no":       # harden(): tài khoản Administrator có sẵn — mật khẩu ngẫu nhiên + tắt
            st["calls"].append(list(argv)); x = find(argv[2]); st["pw"][argv[2]] = argv[3]
            if x: x["off"] = True
            return 0, ""
        if argv[:2] == ["net", "user"] and len(argv) == 4 and not argv[3].startswith("/"): st["calls"].append(list(argv)); st["pw"][argv[2]] = argv[3]; return 0, ""
        if argv[0].lower().endswith("msg.exe"): st["calls"].append(list(argv)); st["msgs"].append(argv[-1]); return 0, ""
        if argv[:2] == ["net", "localgroup"] and argv[-1] == "/delete" and argv[3] not in st["admins"]: st["calls"].append(list(argv)); return 2, "System error 1377 has occurred."
        return base_run(argv, timeout)
    def sleep(sec): st["slept"] += sec; st["clock"] += sec
    pr = cb_provision.Prov(base, run, log=st["log"].append, spi=lambda path: True, admin=True, rec=lambda: "", now=lambda: st["clock"], sleep=sleep, say=lambda m: None,
                           net=lambda h, p: True, gpu=lambda: (False, False), blank=lambda u: st["blank"])
    st["find"] = find
    return pr, st
has = lambda st, n: os.path.exists(os.path.join(st["base"], "logs", n))
names_on = lambda st: sorted(x["name"] for x in st["u"] if not x["off"])

PG = cb_provision.pick_ghost_user
U0 = [{"name": "Administrator", "rid": 500, "off": True}, {"name": "Guest", "rid": 501, "off": True}, {"name": "admin", "rid": 1001, "off": False}]
ck("chọn tài khoản để nhận: theo tài khoản Windows đang tự đăng nhập (kể cả ghi kiểu MAY\\admin); không có gợi ý mà chỉ có 1 tài khoản thường đang bật → lấy nó",
   PG(U0, ["admin"], "PC") == ("admin", "adopt") and PG(U0, ["", "DESKTOP-X\\admin"], "PC") == ("admin", "adopt") and PG(U0, [], "PC") == ("admin", "adopt"))
ck("đã có tài khoản đúng tên → dùng luôn; tên muốn dùng trùng tài khoản có sẵn của Windows → từ chối", PG(U0, [], "ADMIN") == ("admin", "have") and PG(U0, [], "Administrator") == (None, "bia") and PG(U0, [], "guest") == (None, "bia"))
U1 = U0 + [{"name": "khach", "rid": 1002, "off": False}]
ck("nhiều tài khoản mà không biết cái nào đang dùng → tạo mới; ảnh dùng thẳng Administrator có sẵn → tạo mới (không hạ quyền được tài khoản đó)",
   PG(U1, [], "PC") == (None, "new") and PG(U1, [".\\khach"], "PC") == ("khach", "adopt") and PG([dict(U0[0], off=False)] + U0[1:], ["Administrator"], "PC") == (None, "new")
   and PG([dict(U0[0], off=False), U0[1], dict(U0[2], off=True)], [], "PC") == (None, "new"))

pr, st = ghost_env()
r = pr.boot(); j = J(st)
ck("ảnh ghost (đúng như máy ảo 1511 của user: tài khoản 'admin', tên máy DESKTOP-DKDCA09) → pha boot chạy trọn, đặt mốc ghost.done + firstlogon.done", r is True and has(st, "ghost.done") and has(st, "firstlogon.done") and has(st, "ghost.start"), st["log"][-6:])
ck("NHẬN tài khoản 'admin' có sẵn: đổi tên thành 'PC' (giữ số tài khoản → giữ hồ sơ), không tạo tài khoản mới", st["find"]("PC") and st["find"]("PC")["rid"] == 1001 and not st["find"]("admin")
   and not any(c[:2] == ["net", "user"] and c[-1] == "/add" for c in st["calls"]) and any("NHAN tai khoan co san 'admin'" in x for x in st["log"]), [x["name"] for x in st["u"]])
ck("tài khoản khách thành TÀI KHOẢN THƯỜNG: rời nhóm quản trị, vào nhóm Users, cấm tự đổi mật khẩu", "PC" not in st["admins"] and "PC" in st["users"] and "net user PC /passwordchg:no" in j, (st["admins"], st["users"]))
ck("mật khẩu đang trống + cấu hình để trống → KHÔNG đặt lại mật khẩu (giữ dữ liệu đã lưu trong hồ sơ)", "PC" not in st["pw"])
ck("tài khoản Administrator có sẵn: mật khẩu ngẫu nhiên + tắt; trên máy chỉ còn tài khoản khách đang bật", st["find"]("Administrator")["off"] and len(st["pw"].get("Administrator", "")) >= 12 and names_on(st) == ["PC"], names_on(st))
ck("tự đăng nhập bằng 'PC' với TÊN MÁY MỚI (tên cũ sẽ mất sau khi khởi động lại)", any(c[:3] == ["reg", "add", "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"] and c[4] == "DefaultUserName" and c[8] == "PC" for c in st["calls"])
   and any(c[:2] == ["reg", "add"] and c[4] == "DefaultDomainName" and c[8] == "CB-E3B72F" for c in st["calls"]) and any(c[:2] == ["reg", "add"] and c[4] == "AutoAdminLogon" and c[8] == "1" for c in st["calls"]),
   [c for c in st["calls"] if c[:2] == ["reg", "add"] and "Winlogon" in c[2]])
ck("đổi tên máy theo tên bộ cài đã cấp (DESKTOP-DKDCA09 → CB-E3B72F)", st["newname"] == "CB-E3B72F" and any("doi ten may DESKTOP-DKDCA09 -> CB-E3B72F" in x for x in st["log"]), st["newname"])
ck("chạy script riêng của chủ shop + bỏ hạn mật khẩu 42 ngày + báo người ngồi tại máy 'KHONG tat may'", any(c[:2] == ["cmd.exe", "/c"] and c[2].endswith("10-driver.cmd") for c in st["calls"])
   and "net accounts /maxpwage:unlimited" in j and len(st["msgs"]) == 1 and "KHONG tat may" in st["msgs"][0] and st["slept"] >= 25, (st["msgs"], st["slept"]))
ren = next(i for i, c in enumerate(st["calls"]) if ".psbase.Rename(" in " ".join(c))
ck("thứ tự: đổi tên tài khoản → script riêng → hạ quyền → hẹn khởi động lại 30 giây → gỡ dịch vụ khởi động", ren < next(i for i, x in enumerate(j) if x.endswith("10-driver.cmd"))
   < j.index("net localgroup Administrators PC /delete") < next(i for i, x in enumerate(j) if x.startswith("shutdown /r /t 30")) < j.index("sc delete CloudBluePCBoot"), j[-8:])
n0 = len(st["calls"]); r2 = pr.boot(); r3 = pr.system()
ck("đã xong → lần bật máy sau / agent gọi lại KHÔNG dựng lại (không đổi tên, không khởi động lại nữa)", r2 is True and not any("Rename" in " ".join(c) or c[0] == "shutdown" for c in st["calls"][n0:]), J(st)[n0:][:6])

pr, st = ghost_env(cfg={"user": "Khach", "password": "abc123"})
pr.boot()
ck("cấu hình có mật khẩu → đặt đúng mật khẩu đó cho tài khoản nhận về; nhật ký KHÔNG ghi mật khẩu", st["find"]("Khach") and st["pw"].get("Khach") == "abc123" and not any("abc123" in x for x in st["log"])
   and any(c[:2] == ["reg", "add"] and c[4] == "DefaultPassword" and c[8] == "abc123" for c in st["calls"]), [x for x in st["log"] if "mat khau" in x])
pr, st = ghost_env(blank=False)
pr.boot()
ck("tài khoản của ảnh đang có mật khẩu mà cấu hình để trống → đặt lại thành trống (không thì tự đăng nhập hỏng)", st["pw"].get("PC") == "" and ["net", "user", "PC", ""] in st["calls"])

pr, st = ghost_env(users=[("Administrator", 500, True, True), ("Guest", 501, False, False), ("admin", 1001, False, True), ("thue2", 1002, False, True), ("cu", 1003, True, False)])
pr.boot(); j = J(st)
ck("ảnh có thêm tài khoản khác: tắt hết (kể cả Guest đang bật), gỡ khỏi nhóm quản trị; tài khoản vốn đã tắt thì để yên", names_on(st) == ["PC"] and "net user thue2 /active:no" in j and "net user Guest /active:no" in j
   and "thue2" not in st["admins"] and "net user cu /active:no" not in j, (names_on(st), st["admins"]))

pr, st = ghost_env(users=[("Administrator", 500, False, True), ("Guest", 501, True, False)], auto="Administrator", last=".\\Administrator")
r = pr.boot(); j = J(st)
ck("ảnh ghost dùng thẳng tài khoản Administrator có sẵn → TẠO tài khoản khách mới (tài khoản thường), tắt Administrator", r is True and ["net", "user", "PC", "", "/add"] in st["calls"] and names_on(st) == ["PC"]
   and "PC" not in st["admins"] and st["find"]("Administrator")["off"], (names_on(st), j[-6:]))

pr, st = ghost_env(oobe=True)
r = pr.boot(); j = J(st)
ck("bản cài BÌNH THƯỜNG (bộ cài ghi oobe = true) → pha boot không đụng tài khoản, không đổi tên máy, không khởi động lại", r is True and st["newname"] is None and not any(x.startswith("shutdown") or "Rename" in x for x in j)
   and names_on(st) == ["admin"] and "sc delete CloudBluePCBoot" in j and not has(st, "ghost.start"))
pr, st = ghost_env(oobe=None, setup=SETUP_BUSY)
r = pr.boot()
ck("không có image.json + Windows ĐANG ở bước cài lần đầu → không coi là ghost", r is True and not has(st, "ghost.start") and names_on(st) == ["admin"])
pr, st = ghost_env(oobe=None)
r = pr.boot()
ck("không có image.json + Windows KHÔNG ở bước cài lần đầu → coi là ghost, dựng như trên", r is True and has(st, "ghost.done") and names_on(st) == ["PC"])
pr, st = ghost_env(oobe=False, setup=SETUP_BUSY)
r = pr.boot()
ck("bộ cài ghi là ghost nhưng Windows đang chạy bước cài lần đầu (đọc registry thật) → tin Windows, không đụng", not has(st, "ghost.start") and names_on(st) == ["admin"])
pr, st = ghost_env(oobe=False, setup="")
r = pr.boot()
ck("bộ cài ghi là ghost, registry không đọc được → vẫn dựng (theo bộ cài)", has(st, "ghost.done") and names_on(st) == ["PC"])

pr, st = ghost_env(); st["ps_users"] = False
r = pr.boot(); j = J(st)
ck("chưa đọc được danh sách tài khoản → dừng, GIỮ dịch vụ khởi động để lần bật máy sau làm tiếp; chưa đổi gì", r is False and "sc delete CloudBluePCBoot" not in j and names_on(st) == ["admin"] and not has(st, "ghost.done")
   and any("khong doc duoc danh sach tai khoan" in x for x in st["log"]), j[-4:])
st["ps_users"] = True; st["clock"] += 600
r = pr.boot()
ck("lần bật máy sau → làm tiếp và xong", r is True and has(st, "ghost.done") and names_on(st) == ["PC"] and "sc delete CloudBluePCBoot" in J(st))

pr, st = ghost_env(users=[("Administrator", 500, True, True), ("Guest", 501, True, False), ("PC", 1001, False, True)], auto="PC", last=".\\PC")
pr.touch("ghost.start"); pr.touch("firstlogon.start")              # lần trước đã đổi tên tài khoản xong thì mất điện
r = pr.boot()
ck("mất điện giữa chừng (đã đổi tên tài khoản, chưa hạ quyền) → bật lại làm tiếp: hạ quyền + khởi động lại", r is True and has(st, "ghost.done") and "PC" not in st["admins"] and any(x.startswith("shutdown /r") for x in J(st))
   and not any(".psbase.Rename(" in x for x in J(st)))

pr, st = ghost_env(); st["ren_ok"] = False
r = pr.boot()
ck("không đổi được tên tài khoản có sẵn (ADSI lẫn wmic đều lỗi) → tạo tài khoản khách mới, tắt tài khoản cũ", r is True and ["net", "user", "PC", "", "/add"] in st["calls"] and names_on(st) == ["PC"] and st["find"]("admin")["off"], names_on(st))
pr, st = ghost_env(cfg={"user": "Guest", "password": ""})
r = pr.boot()
ck("tên tài khoản khách trùng tài khoản có sẵn của Windows (Guest) → báo rõ trong nhật ký, không phá gì", r is False and names_on(st) == ["admin"] and any("trung tai khoan co san cua Windows" in x for x in st["log"]))

pr, st = ghost_env(oobe=True, tasks=True)                             # bộ cài nhận nhầm là bản thường; file trả lời không chạy → 1 giờ sau agent gọi pha system
pr.system()
ck("lưới cuối: trong 1 giờ đầu pha system chưa đụng tài khoản", names_on(st) == ["admin"] and not has(st, "ghost.start"))
st["clock"] += 3700
r = pr.system()
ck("quá 1 giờ vẫn chưa có tài khoản khách + Windows không ở bước cài → pha system tự dựng kiểu ghost", r is True and has(st, "ghost.done") and names_on(st) == ["PC"] and any(x.startswith("shutdown /r") for x in J(st)), st["log"][-5:])
pr, st = ghost_env(oobe=True, tasks=True, setup=SETUP_BUSY); st["clock"] += 0; pr.system(); st["clock"] += 3700; pr.system()
ck("… nhưng Windows còn đang ở bước cài lần đầu thì không", names_on(st) == ["admin"] and not has(st, "ghost.start"))

pr, st = ghost_env()                                                   # bản ghost 1511 trên máy thật: card mạng chưa có driver, gói VGA NVIDIA kèm theo
fbv = os.path.join(st["base"], "os", "firstboot.d", "1511"); os.makedirs(fbv); open(os.path.join(fbv, NV), "wb").write(b"EXE")
gs = {"devs": [D_LAN_OFF, D_VGA_BASIC], "gpu": (True, False), "order": []}
g_run = pr._run
def ghost_run(argv, timeout=300):
    if cb_provision.NVIDIA_RE.match(os.path.basename(argv[0])): gs["order"].append("vga"); gs["gpu"] = (True, True); return 0, ""
    if os.path.basename(argv[0]).lower() == "pnputil.exe": gs["order"].append("pnputil"); gs["devs"] = [D_LAN_ON, D_VGA_BASIC]; return 0, ""
    return g_run(argv, timeout)
def ghost_net(h, p_):
    gs["order"].append("net:%s" % any(d is D_LAN_ON for d in gs["devs"])); return any(d is D_LAN_ON for d in gs["devs"])
pr._run, pr._devs, pr._pnp, pr._staged = ghost_run, (lambda: list(gs["devs"])), (lambda: gs["order"].append("kick") or True), (lambda: [{"pub": "oem3.inf", "inf": NET_INF, "cls": "net"}])
pr._net, pr._gpu = ghost_net, (lambda: gs["gpu"])
r = pr.boot()
ck("bản GHOST 1511 trên máy thật: dựng tài khoản → DRIVER CARD MẠNG (dò lại phần cứng → pnputil gói driver mạng) → có mạng → MỚI cài VGA NVIDIA → khoá → khởi động lại",
   r is True and gs["order"][:2] == ["kick", "pnputil"] and "vga" in gs["order"] and gs["order"].index("pnputil") < gs["order"].index("net:True") < gs["order"].index("vga")
   and "net:False" not in gs["order"] and has(st, "ghost.done") and any(x.startswith("shutdown /r") for x in J(st)), gs["order"])
ck("… nhật ký ghi card mạng lúc đầu chưa có driver và sau bước driver đã nhận", any("thiet bi CHUA CO DRIVER: 1 (Ethernet Controller [Realtek 10EC:8168])" in x for x in st["log"])
   and any("sau buoc driver: con 0 thiet bi chua co driver; card mang da nhan driver: Realtek PCIe GbE" in x for x in st["log"]), [x for x in st["log"] if "driver" in x])

pr, st = sec_env({"user": "PC", "password": ""})
pr.specialize(); n1 = sum(c == ["net", "accounts", "/maxpwage:unlimited"] for c in st["calls"]); pr.firstlogon(); pr.system()
ck("mọi bản Windows: bỏ hạn mật khẩu 42 ngày ngay từ bước đầu, chỉ làm 1 lần (mốc pwage.done)", n1 == 1 and sum(c == ["net", "accounts", "/maxpwage:unlimited"] for c in st["calls"]) == 1 and os.path.isfile(os.path.join(st["base"], "logs", "pwage.done")))
pr, st = sec_env({"user": "PC", "password": ""}); st["fail"].add("net accounts")
pr.specialize(); st["fail"].clear(); pr.system()
ck("lệnh bỏ hạn mật khẩu lỗi ở bước đầu → pha system (agent gọi) làm lại", sum(c == ["net", "accounts", "/maxpwage:unlimited"] for c in st["calls"]) == 2 and os.path.isfile(os.path.join(st["base"], "logs", "pwage.done")))
os.environ["COMPUTERNAME"] = "CB-THU"
pr, st = sec_env({"user": "PC", "password": ""}); pr.autologon()
ck("bản thường: tự đăng nhập ghi tên máy hiện tại", any(c[:2] == ["reg", "add"] and c[4] == "DefaultDomainName" and c[8] == "CB-THU" for c in st["calls"]))

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
