# -*- coding: utf-8 -*-
"""Thử: cài lại từ trong Windows (CAI-DAT.cmd → cb_stage.py) + cài đặt lần đầu (cb_provision.py). Chạy: python3 tests/test_stage.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
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
       and [x.split("\\")[-1].split("/")[-1] for x in j() if "firstboot.d" in x] == ["10-phan-mem.ps1", "20-driver.cmd"], [x for x in j() if "firstboot.d" in x])
    ck("mật khẩu không bị ghi vào nhật ký", not any("DefaultPassword=" in l and "(an)" not in l for l in p.lines))
    calls.clear(); p.firstboot()
    ck("script riêng chỉ chạy 1 lần", not calls)
    calls.clear(); fail.add("/xml"); p.tasks()
    ck("tạo tác vụ bằng XML lỗi → dùng kiểu dự phòng (onstart, SYSTEM)", any("CloudBluePC Agent /sc onstart /ru SYSTEM /rl highest" in x for x in j()))
    fail.clear(); fail.add("schtasks"); calls.clear()
    rc = cb_provision.main(["specialize"]) if False else None
    p2 = cb_provision.Prov(base, run, log=lambda m: None); p2.specialize(); p2.firstlogon()
    ck("mọi lệnh tác vụ đều lỗi → vẫn chạy hết, không ném lỗi (không chặn bước cài Windows)", True)

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

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
