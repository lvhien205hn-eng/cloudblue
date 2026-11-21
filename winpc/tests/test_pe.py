# -*- coding: utf-8 -*-
"""Thử bộ cài WinPE (cb_pe.py) + phần tính toán (cbcore.py) trên máy Windows GIẢ. Chạy: python3 tests/test_pe.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, "..", "pe"))
import cbcore as C                                    # noqa: E402
import cb_pe                                          # noqa: E402
from cbsys import GPT_DATA, GPT_ESP, GPT_MSR, GPT_WINRE  # noqa: E402
from fakesys import GB, MB, FakeSys, ScriptUI         # noqa: E402

OK = FAIL = 0
TPL = open(os.path.join(HERE, "..", "os", "unattend.tpl.xml"), encoding="utf-8").read()


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", extra)


from test_pe_helpers import WINFILES, cb_layout, cfg0, job0, media_files, rec_files, usb   # noqa: E402


def run(fs, keys=()):
    ui = ScriptUI(keys)
    inst = cb_pe.Installer(fs)
    try: rc = inst.run(ui)
    except C.Stop as e: rc = "STOP: %s" % e
    return rc, ui, inst


def xml_ok(text):
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f: f.write(text); p = f.name
    r = subprocess.run(["xmllint", "--noout", p], capture_output=True, text=True); os.unlink(p)
    return r.returncode == 0, r.stderr


def dp_all(fs): return [ln for sc in fs.dp_scripts for ln in sc]


# =====================================================================================
print("1. Cài mới từ USB — máy UEFI, 1 ổ SSD")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
d0 = fs.disk(0, 480, bus=17, model="Samsung 970 EVO", ssd=True, style="gpt")
d0.add(0, GPT_DATA, "NTFS", "OldWin", "C", files=dict(WINFILES))
rc, ui, inst = run(fs)
ck("cài xong, mã 0", rc == 0, rc)
ck("có đếm ngược 30 giây trước khi xoá", ui.prompts and ui.prompts[0][0] == 30)
ck("USB không bị đụng", fs.file("E", "cb\\media.tag") == "1" and len(fs.fdisks[0].slots) == 1)
ck("dữ liệu cũ trên ổ đích đã bị xoá", all("bi-mat" not in k for p in d0.slots if p.vol for k in p.vol.files))
ck("ổ đích thành GPT 4 phân vùng: EFI · MSR · cứu hộ · Windows", d0.style == "gpt" and [p.type for p in d0.slots] == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA])
esp, msr, rec, win = d0.slots
ck("EFI 260MB FAT32", esp.size == 260 * MB and esp.vol.fs == "FAT32")
ck("phân vùng cứu hộ 12GB, nhãn CBRECOVERY, đã ẩn (không chữ ổ, có cờ bảo vệ)", rec.size == 12 * GB and rec.vol.label == "CBRECOVERY" and rec.vol.letter is None and rec.attrs == 0x8000000000000001, (rec.size / GB, rec.vol.letter, hex(rec.attrs)))
ck("Windows chiếm phần còn lại", win.size > 460 * GB and win.vol.fs == "NTFS")
ck("bung đúng bản mặc định 22H2, bản số 6", fs.file(win.vol, "windows\\cb-image.txt") == "install.wim|6")
ck("đã ghi file khởi động (bcdboot … /f UEFI)", any(c[0].lower().endswith("bcdboot.exe") and c[-1] == "UEFI" for c in fs.cmds))
st = fs.bcd.get("s:\\efi\\microsoft\\boot\\bcd", {})
ck("có mục khởi động cài lại + ramdisk trỏ boot.wim trên phân vùng cứu hộ", C.PE_GUID in st.get("entries", {}) and C.RD_GUID in st["entries"]
   and st["entries"][C.PE_GUID].get("device", "").startswith("ramdisk=[R:]\\cb\\boot\\boot.wim") and st["entries"][C.PE_GUID].get("path", "").endswith("winload.efi"))
ck("mặc định vẫn khởi động vào Windows (không phải bộ cài)", st.get("default", "").startswith("windows"))
ck("phân vùng cứu hộ có boot.wim + boot.sdi + 2 bản Windows + phần mềm", all(k in rec.vol.files for k in
   ("cb\\boot\\boot.wim", "cb\\boot\\boot.sdi", "cb\\images\\22h2.wim", "cb\\images\\1511.wim", "cb\\pe\\cb_pe.py", "cb\\py\\python.exe", "cb\\recovery.tag")))
rcfg = json.loads(rec.vol.files["cb\\cb.json"])
ck("cấu hình trên phân vùng cứu hộ trỏ ảnh về cb\\images, không có mã đăng ký", [i["file"] for i in rcfg["images"]] == ["cb\\images\\22h2.wim", "cb\\images\\1511.wim"]
   and "enroll" not in json.dumps(rcfg) and "cb\\enroll.key" not in rec.vol.files and not any("cbpc_" in str(v) for v in rec.vol.files.values()))
seed = json.loads(win.vol.files["cloudbluepc\\seed.json"])
ck("Windows mới có seed.json kèm mã đăng ký (để tự đăng ký lần đầu)", seed.get("enroll_key") == "cbpc_" + "a" * 40 and seed["os"] == "22h2" and seed["from"] == "media")
ck("Windows mới có agent + Python + thư viện", all(k in win.vol.files for k in ("cloudbluepc\\agent\\pcagent.py", "cloudbluepc\\py\\python.exe", "cloudbluepc\\lib\\cbsys.py", "cloudbluepc\\os\\provision.cmd")))
ua = win.vol.files.get("windows\\panther\\unattend.xml", "")
okx, err = xml_ok(ua)
ck("file trả lời hợp lệ (XML), có tên máy + tài khoản + lệnh cài CloudBlue", okx and "<ComputerName>%s</ComputerName>" % seed["name"] in ua and "<Name>PC</Name>" in ua
   and "provision.cmd specialize" in ua and "provision.cmd firstlogon" in ua and "{{" not in ua, err)
ck("mặc định KHÔNG điền khoá Windows vào file trả lời", "<ProductKey>" not in ua)
ck("tên máy dạng CB-XXXXXX", len(seed["name"]) == 9 and seed["name"].startswith("CB-"), seed["name"])
ck("identity.json trên phân vùng cứu hộ giữ tên máy", json.loads(rec.vol.files["cb\\identity.json"])["name"] == seed["name"])
ck("chỉ xoá (clean) đúng 1 ổ", dp_all(fs).count("clean") == 1 and "select disk 0" in dp_all(fs) and "select disk 9" not in dp_all(fs))
icl = [c for c in fs.cmds if c[0] == "icacls"]
ck("khoá quyền thư mục CloudBluePC ngay lúc cài: chỉ SYSTEM + Administrators, tài khoản thường chỉ ĐỌC py / os, firstboot.d bị khoá",
   ["icacls", "W:\\CloudBluePC", "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"] in icl and ["icacls", "W:\\CloudBluePC\\*", "/reset", "/T", "/C", "/Q"] in icl
   and sorted(c[1] for c in icl if "*S-1-5-32-545:(OI)(CI)RX" in c) == ["W:\\CloudBluePC\\os", "W:\\CloudBluePC\\py"]
   and ["icacls", "W:\\CloudBluePC\\os\\firstboot.d", "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"] in icl, icl)
ck("khoá quyền gốc phân vùng cứu hộ: chỉ SYSTEM + Administrators (gỡ Users / Authenticated Users / Everyone)",
   ["icacls", "R:\\", "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"] in icl and ["icacls", "R:\\", "/remove:g", "*S-1-5-32-545", "*S-1-5-11", "*S-1-1-0", "*S-1-3-0"] in icl
   and ["icacls", "R:\\*", "/reset", "/T", "/C", "/Q"] in icl and ["icacls", "R:\\*", "/setowner", "*S-1-5-32-544", "/T", "/C", "/Q"] in icl
   and not any("RX" in " ".join(c) for c in icl if c[1].startswith("R:")), icl)

print("2. Cài mới — máy BIOS")
fs = FakeSys("bios"); cfg = cfg0(); usb(fs, cfg)
d0 = fs.disk(0, 240, model="Kingston A400", ssd=True, style="mbr"); d0.add(0, 0x07, "NTFS", "Old", "C", active=True, files=dict(WINFILES))
rc, ui, inst = run(fs)
ck("cài xong", rc == 0, rc)
ck("MBR 3 phân vùng: System (active) · cứu hộ (id 27, ẩn) · Windows", d0.style == "mbr" and len(d0.slots) == 3 and d0.slots[0].active and d0.slots[0].size == 500 * MB
   and d0.slots[1].type == 0x27 and d0.slots[1].vol.letter is None and d0.slots[2].vol.label == "Windows", [(hex(p.type) if isinstance(p.type, int) else p.type, p.active) for p in d0.slots])
ck("bcdboot /f BIOS + kho BCD ở \\Boot\\BCD + winload.exe", any(c[-1] == "BIOS" for c in fs.cmds if "bcdboot" in c[0].lower())
   and fs.bcd.get("s:\\boot\\bcd", {}).get("entries", {}).get(C.PE_GUID, {}).get("path", "").endswith("winload.exe"))

print("3. Hai ổ trong máy: SSD 256GB + HDD 2TB")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
hdd = fs.disk(0, 2000, model="ST2000DM008", ssd=False, style="gpt"); hdd.add(0, GPT_DATA, "NTFS", "KHO", "D", files={"phim\\a.mkv": "quan trong"})
ssd = fs.disk(1, 256, model="Samsung 860", ssd=True, style="raw")
rc, ui, inst = run(fs)
ck("tự chọn SSD (ổ 1), không chọn HDD", rc == 0 and len(ssd.slots) == 4 and len(hdd.slots) == 1)
ck("HDD giữ nguyên dữ liệu", fs.file("D", "phim\\a.mkv") == "quan trong")
ck("màn hình ghi rõ ổ nào bị xoá, ổ nào không đụng", any("SE BI XOA SACH" in l and "Samsung 860" in l for l in fs.logs) and any("khong dung toi" in l and "ST2000DM008" in l for l in fs.logs))
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
hdd = fs.disk(0, 2000, model="ST2000DM008", ssd=False, style="gpt"); hdd.add(0, GPT_DATA, "NTFS", "KHO", "D", files={"phim\\a.mkv": "quan trong"})
ssd = fs.disk(1, 256, model="Samsung 860", ssd=True, style="raw")
rc, ui, inst = run(fs, ["a", "\r"])
ck("bấm A rồi Enter → xoá luôn HDD (1 phân vùng NTFS trống)", rc == 0 and len(hdd.slots) == 1 and hdd.slots[0].vol.label == "DATA" and not hdd.slots[0].vol.files, [p.vol.label for p in hdd.slots if p.vol])
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
hdd = fs.disk(0, 2000, model="ST2000DM008", ssd=False, style="gpt"); hdd.add(0, GPT_DATA, "NTFS", "KHO", "D", files={"phim\\a.mkv": "quan trong"})
ssd = fs.disk(1, 256, model="Samsung 860", ssd=True, style="raw")
rc, ui, inst = run(fs, ["d", "\r"])
ck("bấm D → đổi ổ đích sang HDD; SSD không đụng", rc == 0 and len(hdd.slots) == 4 and len(ssd.slots) == 0)
# ổ đang có Windows cũ được ưu tiên dù không phải SSD nhỏ nhất
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
a = fs.disk(0, 500, model="WD Blue 500", ssd=True, style="gpt"); a.add(0, GPT_DATA, "NTFS", "Win", "C", files=dict(WINFILES))
b = fs.disk(1, 250, model="SSD trong", ssd=True, style="gpt"); b.add(0, GPT_DATA, "NTFS", "Data", "D", files={"x.txt": "1"})
rc, ui, inst = run(fs)
ck("2 SSD: chọn ổ đang chứa Windows cũ", rc == 0 and len(a.slots) == 4 and fs.file("D", "x.txt") == "1")

print("4. Không bao giờ chọn USB / ổ rời / ổ quá nhỏ")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
fs.disk(1, 1000, bus=7, removable=False, model="WD Elements USB", style="gpt").add(0, GPT_DATA, "NTFS", "Backup", "F", files={"sao-luu.zip": "x"})
fs.disk(2, 16, bus=13, model="eMMC nho", style="gpt")
rc, ui, inst = run(fs, ["x"])
ck("chỉ có USB + ổ quá nhỏ → không tự cài, chờ người bấm; X → về bộ cài thường (mã 3)", rc == 3 and ui.prompts[0][0] == 0, (rc, ui.prompts[:1]))
ck("không lệnh diskpart nào chạy", not fs.dp_scripts and fs.file("F", "sao-luu.zip") == "x")

print("5. Người đứng máy can thiệp")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); d0 = fs.disk(0, 480, ssd=True, style="gpt"); d0.add(0, GPT_DATA, "NTFS", "Old", "C", files=dict(WINFILES))
rc, ui, inst = run(fs, ["x"])
ck("bấm X lúc đếm ngược → huỷ, không xoá gì", rc == 3 and not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt"))
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); d0 = fs.disk(0, 480, ssd=True, style="gpt")
rc, ui, inst = run(fs, ["2", "\r"])
ck("bấm 2 rồi Enter → cài bản 1511", rc == 0 and fs.file(d0.slots[3].vol, "windows\\cb-image.txt") == "1511.wim|1" and json.loads(d0.slots[3].vol.files["cloudbluepc\\seed.json"])["os"] == "1511")
ck("bấm phím thì thôi đếm ngược, chờ Enter", ui.prompts[0][0] == 30 and ui.prompts[1][0] == 0)

print("6. Ổ nhỏ → không tạo phân vùng cứu hộ nhưng vẫn cài")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); d0 = fs.disk(0, 64, ssd=True, style="raw", model="SSD 64GB")
rc, ui, inst = run(fs)
ck("cài được, 3 phân vùng (không có cứu hộ), có cảnh báo", rc == 0 and len(d0.slots) == 3 and any("KHONG tao phan vung cuu ho" in l for l in fs.logs))
ck("không tạo mục khởi động cài lại", C.PE_GUID not in fs.bcd.get("s:\\efi\\microsoft\\boot\\bcd", {}).get("entries", {}))

print("7. Bộ cài nằm trên đĩa ISO (máy ảo / Ventoy) + USB lên chậm")
fs = FakeSys("uefi"); cfg = cfg0(); fs.cd(files=media_files(cfg)); d0 = fs.disk(0, 120, ssd=None, style="raw", model="VBOX HARDDISK")
rc, ui, inst = run(fs)
ck("cài từ đĩa ISO được", rc == 0 and len(d0.slots) == 4)
fs = FakeSys("uefi"); cfg = cfg0(); d0 = fs.disk(0, 120, style="raw")
from fakesys import FVol
late = FVol("UDF", "CB", kind=5); late.letter = "D"
for k, v in media_files(cfg).items(): late.put(k, v)
fs.late = [late]
rc, ui, inst = run(fs)
ck("chưa thấy bộ cài → gọi wpeinit rồi thấy → cài", rc == 0 and ["wpeinit"] in fs.cmds and len(d0.slots) == 4)
fs = FakeSys("uefi"); fs.disk(0, 120, style="raw")
os.environ["CB_WAIT"] = "5"
rc, ui, inst = run(fs)
ck("không có bộ cài CloudBlue ở đâu → mã 3 (bộ cài Windows thường), không xoá gì", rc == 3 and not fs.dp_scripts)
os.environ.pop("CB_WAIT")

print("8. Chữ ổ W/S/R đang bị ổ khác dùng")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg, letter="W")
fs.disk(1, 2000, ssd=False, style="gpt", model="HDD kho").add(0, GPT_DATA, "NTFS", "KHO", "S", files={"a": "1"})
d0 = fs.disk(0, 480, ssd=True, style="raw")
rc, ui, inst = run(fs)
ck("tự dùng chữ ổ khác, vẫn cài xong, ổ khác nguyên vẹn", rc == 0 and len(d0.slots) == 4 and fs.file("S", "a") == "1" and fs.file("W", "cb\\media.tag") == "1")

print("9. Khởi động vào phân vùng cứu hộ mà KHÔNG có lệnh")
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg)
rc, ui, inst = run(fs)
ck("không xoá gì, khởi động lại (mã 10)", rc == 10 and not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt") == "du lieu khach cu")
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0(state="done"))
rc, ui, inst = run(fs)
ck("lệnh đã xong (state=done) → không làm lại", rc == 10 and not fs.dp_scripts)

print("10. Cài lại theo lệnh — chỉ phân vùng Windows (đổi Windows cho khách đang thuê)")
fs = FakeSys("uefi"); cfg = cfg0()
d, rec, win = cb_layout(fs, cfg, None, extra_data=True)
other = fs.disk(1, 2000, ssd=False, style="gpt", model="HDD game"); other.add(0, GPT_DATA, "NTFS", "GAME", "E", files={"roblox\\a": "1"})
rec.vol.put("cb\\job.json", json.dumps(job0(win, wipe="system")))
n_slots = len(d.slots)
rc, ui, inst = run(fs)
ck("xong, mã 0", rc == 0, rc)
ck("có 10 giây cho người đứng máy huỷ", ui.prompts[0][0] == 10)
ck("số phân vùng không đổi, không lệnh xoá phân vùng / clean nào", len(d.slots) == n_slots and "clean" not in dp_all(fs) and not any("delete partition" in l for l in dp_all(fs)))
ck("phân vùng Windows cũ được định dạng lại (hết dữ liệu khách cũ) + bung 1511", "users\\khach\\bi-mat.txt" not in win.vol.files and fs.file(win.vol, "windows\\cb-image.txt") == "1511.wim|1")
ck("phân vùng D: của khách trên cùng ổ còn nguyên", fs.file(d.slots[4].vol, "game\\save.dat") == "cua khach")
ck("ổ cứng khác còn nguyên", fs.file(other.slots[0].vol, "roblox\\a") == "1")
seed = json.loads(win.vol.files["cloudbluepc\\seed.json"])
ck("Windows mới nhận vé đăng ký lại + số lệnh + giữ tên máy + mã máy cũ", seed.get("ticket") == "t" * 32 and seed["order"] == 77 and seed["name"] == "CB-OLD001" and seed["id"].startswith("1111") and seed["hw"] == "h" * 64 and "enroll_key" not in seed, seed)
res = json.loads(rec.vol.files["cb\\job-result.json"])
ck("ghi kết quả cho agent báo về web", res["id"] == 77 and res["ok"] is True and res["os"] == "1511")
ck("job.json đã gỡ, job.done.json không còn vé", "cb\\job.json" not in rec.vol.files and "ticket" not in rec.vol.files["cb\\job.done.json"] and json.loads(rec.vol.files["cb\\job.done.json"])["state"] == "done")
st = fs.bcd.get("s:\\efi\\microsoft\\boot\\bcd", {})
ck("kho BCD làm mới: mặc định = Windows mới, vẫn có mục cài lại", st.get("default", "").startswith("windows@") and C.PE_GUID in st["entries"] and "made" in st)
ck("phân vùng cứu hộ lại được ẩn, EFI không bị xoá", rec.vol.letter is None and d.slots[0].type == GPT_ESP and "efi\\microsoft\\boot\\bcd" in d.slots[0].vol.files)

print("11. Cài lại theo lệnh — dọn sạch cả máy (khách cũ trả máy)")
fs = FakeSys("uefi"); cfg = cfg0()
d, rec, win = cb_layout(fs, cfg, None, extra_data=True)
other = fs.disk(1, 2000, ssd=False, style="gpt", model="HDD game"); other.add(0, GPT_DATA, "NTFS", "GAME", "E", files={"roblox\\a": "1"})
u = usb(fs, cfg0(), index=5, letter="U", key=None); u.slots[0].vol.files.pop("cb\\media.tag")      # USB lạ đang cắm (không phải bộ cài)
rec.vol.put("cb\\job.json", json.dumps(job0(wipe="all", os="22h2")))
rec_off = rec.offset
rc, ui, inst = run(fs)
ck("xong", rc == 0, rc)
ck("ổ hệ thống còn đúng EFI · MSR · cứu hộ · Windows mới", [p.type for p in sorted(d.slots, key=lambda p: p.offset)] == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA] and len(d.slots) == 4)
neww = max(d.slots, key=lambda p: p.offset)
ck("phân vùng cứu hộ nguyên vị trí, nguyên dữ liệu", rec in d.slots and rec.offset == rec_off and "cb\\images\\22h2.wim" in rec.vol.files)
ck("Windows mới chiếm hết phần sau cứu hộ (gộp cả C: và D: cũ)", neww.offset == rec.offset + rec.size and neww.size > 460 * GB, (neww.offset, neww.size / GB))
ck("không còn dữ liệu khách cũ ở đâu trên ổ hệ thống", not any("bi-mat" in k or "save.dat" in k for p in d.slots if p.vol for k in p.vol.files))
ck("ổ cứng khác bị xoá sạch (1 phân vùng DATA trống)", len(other.slots) == 1 and other.slots[0].vol.label == "DATA" and not other.slots[0].vol.files)
ck("USB đang cắm không bị đụng", len(u.slots) == 1 and "cb\\cb.json" in u.slots[0].vol.files)
ck("bung 22H2", fs.file(neww.vol, "windows\\cb-image.txt") == "22h2.wim|6")
icl = [c for c in fs.cmds if c[0] == "icacls"]
ck("cài lại theo lệnh: Windows mới + phân vùng cứu hộ đều được khoá quyền lại", any(c[1].endswith(":\\CloudBluePC") and "/inheritance:r" in c for c in icl)
   and any(len(c[1]) == 3 and c[1].endswith(":\\") and "/remove:g" in c for c in icl), icl)
fs = FakeSys("uefi"); cfg = cfg0()
d, rec, win = cb_layout(fs, cfg, None, extra_data=True)
other = fs.disk(1, 2000, ssd=False, style="gpt"); other.add(0, GPT_DATA, "NTFS", "GAME", "E", files={"roblox\\a": "1"})
rec.vol.put("cb\\job.json", json.dumps(job0(wipe="disk")))
rc, ui, inst = run(fs)
ck("wipe=disk: dọn cả ổ hệ thống nhưng ổ khác giữ nguyên", rc == 0 and len(d.slots) == 4 and fs.file(other.slots[0].vol, "roblox\\a") == "1")

print("12. Cài lại — máy BIOS")
fs = FakeSys("bios"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, None, fw="bios", extra_data=True)
rec.vol.put("cb\\job.json", json.dumps(job0(wipe="all")))
rc, ui, inst = run(fs)
ck("xong; còn System (active) · cứu hộ (id 27) · Windows mới", rc == 0 and len(d.slots) == 3 and d.slots[0].active and rec.type == 0x27 and rec.vol.letter is None, (rc, len(d.slots)))
ck("kho BCD ở phân vùng System làm mới + mục cài lại", C.PE_GUID in fs.bcd.get("s:\\boot\\bcd", {}).get("entries", {}))
# kiểu cũ: 1 phân vùng Windows vừa là khởi động (active) + cứu hộ tạo thêm ở cuối (máy chuyển sang bằng CAI-DAT.cmd)
fs = FakeSys("bios"); cfg = cfg0()
d = fs.disk(0, 240, ssd=True, style="mbr", model="SSD cu")
w = d.add(200 * 1024, 0x07, "NTFS", "Win", "C", active=True, files=dict(WINFILES, **{"boot\\bcd": "old"}))
rec = d.add(12 * 1024, 0x27, "NTFS", "CBRECOVERY", files=rec_files(cfg, job0(wipe="all", os="22h2")))
rc, ui, inst = run(fs)
neww = next(p for p in d.slots if p is not rec)
ck("ổ BIOS 1 phân vùng: tạo lại Windows + đặt active, giữ cứu hộ", rc == 0 and len(d.slots) == 2 and neww.active and neww.vol.label == "Windows" and "users\\khach\\bi-mat.txt" not in neww.vol.files, rc)
ck("file khởi động ghi lên chính phân vùng Windows", any("bcdboot" in c[0].lower() and c[3] == "W:" for c in fs.cmds))

print("13. Ổ được chuyển sang từ Windows có sẵn — số phân vùng đổi sau khi xoá")
fs = FakeSys("uefi"); cfg = cfg0()
d = fs.disk(0, 480, ssd=True, style="gpt", model="SSD hang")
re_ = d.add(500, GPT_WINRE, "NTFS", "Recovery", attrs=0x8000000000000001)                   # 1: WinRE của hãng ở đầu ổ
esp = d.add(100, GPT_ESP, "FAT32", "", files={"efi\\microsoft\\boot\\bcd": "old"})         # 2
d.add(16, GPT_MSR)                                                                          # 3
w = d.add(300 * 1024, GPT_DATA, "NTFS", "OS", "C", files=dict(WINFILES))                    # 4
rec = d.add(12 * 1024, GPT_DATA, "NTFS", "CBRECOVERY", attrs=0x8000000000000001, files=rec_files(cfg, job0(wipe="all")))   # 5 (tạo sau khi thu nhỏ C:)
dd = d.add(0, GPT_DATA, "NTFS", "DATA", "D", files={"x": "1"})                              # 6
rc, ui, inst = run(fs)
ck("xong", rc == 0, rc)
ck("giữ đúng EFI + MSR + cứu hộ; WinRE hãng, C:, D: bị xoá", esp in d.slots and rec in d.slots and re_ not in d.slots and w not in d.slots and dd not in d.slots and len(d.slots) == 4)
ck("xoá theo số giảm dần (6 → 4 → 1)", [l for l in dp_all(fs) if l.startswith("select partition") or l.startswith("delete")][:6] ==
   ["select partition 6", "delete partition override", "select partition 4", "delete partition override", "select partition 1", "delete partition override"], dp_all(fs)[:12])
neww = next(p for p in d.slots if p not in (esp, rec) and p.vol)
ck("Windows mới nằm ở khoảng trống LỚN NHẤT (chỗ C: cũ)", neww.offset == w.offset and neww.size == w.size, (neww.offset // MB, neww.size // MB))
ck("chữ S gán đúng phân vùng EFI, kho BCD mới nằm trên EFI", "efi\\microsoft\\boot\\bcd" in esp.vol.files and esp.vol.files["efi\\microsoft\\boot\\bcd"] == "bcd")
ck("cờ ẩn đặt đúng phân vùng cứu hộ, KHÔNG đặt nhầm lên Windows", rec.attrs == 0x8000000000000001 and rec.vol.letter is None and neww.attrs == 0)

print("14. Lệnh sai / thiếu → dừng TRƯỚC khi xoá, Windows cũ còn nguyên")
for label, jb in (("bản Windows không có trong bộ cài", dict(os="win7")), ("kiểu xoá lạ", dict(wipe="tat-ca")),):
    fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0(**jb))
    rc, ui, inst = run(fs)
    ok = not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt") == "du lieu khach cu"
    ck("%s → không làm, không xoá gì" % label, ok and rc in (10,), rc)
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, None)
rec.vol.put("cb\\job.json", json.dumps(job0(wipe="system", win={"offset": 123456, "size": 1})))
rc, ui, inst = run(fs)
ck("wipe=system mà vị trí phân vùng Windows không khớp → dừng, không xoá nhầm", rc == 10 and not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt"))
res = json.loads(rec.vol.files["cb\\job-result.json"])
ck("ghi kết quả lỗi + đóng lệnh (không lặp lại mãi)", res["ok"] is False and "cb\\job.json" not in rec.vol.files and json.loads(rec.vol.files["cb\\job.done.json"])["state"] == "failed")
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, None)
rec.vol.files.pop("cb\\images\\1511.wim"); rec.vol.put("cb\\job.json", json.dumps(job0()))
rc, ui, inst = run(fs)
ck("thiếu file ảnh trên phân vùng cứu hộ → dừng trước khi xoá", rc == 10 and not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt"))
fs = FakeSys("bios"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0(), fw="uefi")
rc, ui, inst = run(fs)
ck("máy BIOS mà ổ GPT → dừng, không xoá", rc == 10 and not fs.dp_scripts)

print("15. Huỷ tại máy + thử lại sau lỗi")
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0())
rc, ui, inst = run(fs, ["x"])
ck("bấm X trong 10 giây → huỷ, không xoá, lệnh đóng (cancelled)", rc == 10 and not fs.dp_scripts and json.loads(rec.vol.files["cb\\job.done.json"])["state"] == "cancelled" and json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is False)
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0()); fs.fail_dism = True
rc, ui, inst = run(fs)
j = json.loads(rec.vol.files["cb\\job.json"])
ck("bung Windows lỗi → ghi lần thử 1, giữ lệnh để thử lại", rc == 10 and j["attempts"] == 1 and j["state"] == "running" and json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is False)
st = fs.bcd.get("s:\\efi\\microsoft\\boot\\bcd", {})
ck("trước khi xoá đã đặt máy tự vào lại bộ cài (mất điện vẫn làm tiếp)", st.get("default") == C.PE_GUID)
fs.fail_dism = False
rc, ui, inst = run(fs)
ck("lần khởi động kế: làm tiếp KHÔNG hỏi lại, xong", rc == 0 and not ui.prompts and json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is True, (rc, ui.prompts))
ck("xong thì mặc định quay về Windows", fs.bcd["s:\\efi\\microsoft\\boot\\bcd"].get("default", "").startswith("windows@"))
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0(attempts=2, state="running")); fs.fail_dism = True
rc, ui, inst = run(fs)
ck("thử lần 3 vẫn lỗi → dừng hẳn, giữ màn hình báo lỗi", ui.held == 1 and json.loads(rec.vol.files["cb\\job.json"])["attempts"] == 3)
rc, ui, inst = run(fs)
ck("khởi động lại sau đó → không tự xoá nữa, chờ người xử lý", ui.held == 1 and len(fs.dp_scripts) == 1)

print("16. Vừa có USB bộ cài vừa có phân vùng cứu hộ")
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); d, rec, win = cb_layout(fs, cfg, job0(wipe="system", win={"offset": 0, "size": 0}))
j = json.loads(rec.vol.files["cb\\job.json"]); j["win"] = {"offset": win.offset, "size": win.size}; rec.vol.put("cb\\job.json", json.dumps(j))
rc, ui, inst = run(fs)
ck("có lệnh đang chờ → làm lệnh (không cài mới từ USB)", rc == 0 and "clean" not in dp_all(fs) and rec in d.slots)
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); d, rec, win = cb_layout(fs, cfg, None)
rc, ui, inst = run(fs)
ck("không có lệnh → cài mới từ USB, xoá cả phân vùng cứu hộ cũ rồi tạo lại", rc == 0 and dp_all(fs).count("clean") == 1 and rec not in d.slots and len(d.slots) == 4)

print("17. Phần tính toán (cbcore)")
ck("os_id", C.os_id("10.0.19045.3803") == "22h2" and C.os_id("10.0.10586.0") == "1511" and C.os_id("10.0.99999.1") == "b99999" and C.os_id("") == "win")
ck("clean_name", C.clean_name("máy số 1!!") == "mys1" and C.clean_name("12345") == "CB-PC" and C.clean_name("A" * 30) == "A" * 15 and C.clean_name("-x-") == "x")
ck("recovery_bytes làm tròn GB, tối thiểu 6GB", C.recovery_bytes({"images": []}) == 6 * GB and C.recovery_bytes(cfg0()) == 13 * GB and C.recovery_bytes(cfg0(), 7) == 12 * GB, C.recovery_bytes(cfg0()) / GB)
ck("pick_letters tránh chữ đang dùng + X", C.pick_letters({"W", "S"}) == ["V", "U", "R"] and C.pick_letters(set("WSRVUTQPONMLKJ")) == ["I", "H", "G"], C.pick_letters({"W", "S"}))
try: C.pick_letters(set("WSRVUTQPONMLKJIHGFEDZ")); _full = False
except C.Stop: _full = True
ck("hết chữ ổ trống → dừng có lời nhắn (không gán bừa)", _full)
u2 = C.make_unattend(TPL, {"edition": "Professional", "lang": "vi-VN"}, {"user": "A&B", "password": "p<w>\"", "generic_key": True}, "CB-1")
okx, err = xml_ok(u2)
ck("ký tự đặc biệt trong tên / mật khẩu được mã hoá XML", okx and "A&amp;B" in u2 and "p&lt;w&gt;&quot;" in u2 and "<UILanguage>vi-VN</UILanguage>" in u2, err)
ck("bật generic_key + đúng phiên bản → có khoá cài đặt chung của Pro", "<ProductKey>VK7JG-NPHTM-C97JM-9MPGT-3V66T</ProductKey>" in u2)
ck("phiên bản lạ → không điền khoá", "<ProductKey>" not in C.make_unattend(TPL, {"edition": "EnterpriseS"}, {"generic_key": True}, "x1"))
_pro = lambda ver: {"edition": "Professional", "version": ver, "name": "Windows 10 Pro"}
ck("mặc định (auto): bản 1511 Pro → điền khoá cài đặt chung (màn hình cài lần đầu của 1511 dừng hỏi key)", "<ProductKey>VK7JG-NPHTM-C97JM-9MPGT-3V66T</ProductKey>" in C.make_unattend(TPL, _pro("10.0.10586.0"), {}, "x1"))
ck("mặc định (auto): bản 22H2 → không điền khoá", "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.19045.2965"), {}, "x1") and "<ProductKey>" not in C.make_unattend(TPL, _pro(""), {}, "x1"))
ck("auto: 1511 nhưng phiên bản lạ → không điền", "<ProductKey>" not in C.make_unattend(TPL, {"edition": "ProfessionalN", "version": "10.0.10586.0"}, {"generic_key": "auto"}, "x1"))
ck("tắt (off / false) → 1511 cũng không điền", "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.10586.0"), {"generic_key": "off"}, "x1") and "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.10586.0"), {"generic_key": False}, "x1"))
ck("bật (on) → 22H2 cũng điền; Home dùng đúng khoá Home", "VK7JG" in C.make_unattend(TPL, _pro("10.0.19045.1"), {"generic_key": "on"}, "x1") and "<ProductKey>YTMG3-N6DKC-DKB77-7M9GH-8HVX7</ProductKey>" in C.make_unattend(TPL, {"edition": "Core", "version": "10.0.10586.0", "name": "Windows 10 Home"}, {}, "x1"))
ck("auto: bản 1511 TUỲ BIẾN (Lite, Premium, có tên người làm…) → KHÔNG tự điền khoá", not any("<ProductKey>" in C.make_unattend(TPL, {"edition": "Professional", "version": "10.0.10586.0", "name": n}, {}, "x1")
   for n in ("Win10 Lite 1511 x64", "Windows 10 Pro Lite", "Windows 10 Pro 1511 by Abc", "", None)))
ck("bản tuỳ biến mà bật hẳn (on) → vẫn điền", "VK7JG" in C.make_unattend(TPL, {"edition": "Professional", "version": "10.0.10586.0", "name": "Win10 Lite 1511"}, {"generic_key": "on"}, "x1"))
ck("is_stock_name", all(C.is_stock_name(n) for n in ("Windows 10 Pro", "Windows 10 Home Single Language", "Windows 10 Pro N for Workstations", "windows 11 enterprise", "Windows 10 Enterprise LTSB"))
   and not any(C.is_stock_name(n) for n in ("Windows 10", "Win10 Pro", "Windows 10 Pro 22H2 Premium V5", "Windows 10 Lite", "Windows 7 Pro", "", None)))
ck("find_unattend_key: đọc khoá trong file trả lời cũ (2 kiểu viết), không có → rỗng",
   C.find_unattend_key("<x><ProductKey>w269n-wfgwx-yvc9b-4j6c9-t83gx</ProductKey></x>") == "W269N-WFGWX-YVC9B-4J6C9-T83GX"
   and C.find_unattend_key("<UserData><ProductKey>\n  <Key>VK7JG-NPHTM-C97JM-9MPGT-3V66T</Key><WillShowUI>Never</WillShowUI></ProductKey></UserData>") == "VK7JG-NPHTM-C97JM-9MPGT-3V66T"
   and C.find_unattend_key("<ProductKey></ProductKey>") == "" and C.find_unattend_key("") == "" and C.find_unattend_key(None) == "" and C.find_unattend_key("<ProductKey>ABCDE-12345</ProductKey>") == "")
ck("khoá có sẵn của bản Windows được giữ (kể cả 22H2); tắt hẳn (off) thì bỏ; khoá sai dạng thì bỏ", "<ProductKey>AAAAA-BBBBB-CCCCC-DDDDD-EEEEE</ProductKey>" in C.make_unattend(TPL, _pro("10.0.19045.1"), {}, "x1", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
   and "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.19045.1"), {"generic_key": "off"}, "x1", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
   and "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.19045.1"), {}, "x1", "<x>&bad"))
ck("key_mode / build_no", C.key_mode({}) == "auto" and C.key_mode({"generic_key": True}) == "on" and C.key_mode({"generic_key": "OFF"}) == "off" and C.key_mode({"generic_key": "la"}) == "auto"
   and C.build_no("10.0.10586.0") == 10586 and C.build_no("x") == 0 and C.build_no(None) == 0)
ck("job_valid", C.job_valid(job0()) and not C.job_valid(job0(attempts=3)) and not C.job_valid(job0(state="done")) and not C.job_valid(job0(os="../x")) and not C.job_valid(None) and not C.job_valid(job0(wipe="x")))
cmds = C.bcd_pe_cmds("uefi", "R", "S:\\EFI\\Microsoft\\Boot\\BCD")
ck("lệnh BCD: xoá mục cũ (bỏ qua lỗi) rồi tạo lại, dùng GUID cố định", cmds[0][1] is True and cmds[2][1] is False and cmds[2][0][3:5] == ["/create", C.RD_GUID] and all(c[0][1:3] == ["/store", "S:\\EFI\\Microsoft\\Boot\\BCD"] for c in cmds))
import re as _re
ck("GUID hợp lệ", all(_re.fullmatch(r"\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}", g) for g in (C.PE_GUID, C.RD_GUID)))

print("18. Đọc bảng phân vùng thật (bộ đệm DeviceIoControl dựng theo tài liệu Microsoft)")
import cbsys, struct, uuid as _uuid
def gpt_entry(num, off, size, tguid, attrs=0, name=""):
    e = struct.pack("<I4xqqI?3x", 1, off, size, num, False)
    e += _uuid.UUID(tguid).bytes_le + _uuid.uuid4().bytes_le + struct.pack("<Q", attrs) + name.encode("utf-16-le").ljust(72, b"\0")
    return e
def mbr_entry(num, off, size, ptype, boot):
    e = struct.pack("<I4xqqI?3x", 0, off, size, num, False) + struct.pack("<B??xI", ptype, boot, True, 2048)
    return e.ljust(144, b"\0")
ck("mỗi mục phân vùng dài 144 byte", len(gpt_entry(1, 0, 1, GPT_ESP)) == 144 and len(mbr_entry(1, 0, 1, 7, True)) == 144)
hdr = struct.pack("<II", 1, 3) + _uuid.uuid4().bytes_le + struct.pack("<qqI4x", 34 * 512, 480 * GB, 128)
buf = hdr + gpt_entry(1, MB, 260 * MB, GPT_ESP, name="EFI system partition") + gpt_entry(2, 261 * MB, 16 * MB, GPT_MSR) + gpt_entry(3, 277 * MB, 100 * GB, GPT_DATA, 0x8000000000000001, "Basic data partition")
ck("đầu bảng dài 48 byte", len(hdr) == 48)
style, sig, parts = cbsys.parse_drive_layout(buf)
ck("GPT: kiểu, 3 phân vùng, đúng loại / vị trí / cờ / tên", style == "gpt" and len(parts) == 3 and parts[0].type == GPT_ESP and parts[0].offset == MB and parts[0].size == 260 * MB
   and parts[1].type == GPT_MSR and parts[2].attrs == 0x8000000000000001 and parts[2].name == "Basic data partition" and parts[2].number == 3, [(p.number, p.type) for p in parts])
hdr = struct.pack("<III", 0, 4, 0xA1B2C3D4).ljust(48, b"\0")
buf = hdr + mbr_entry(1, MB, 500 * MB, 0x07, True) + mbr_entry(2, 501 * MB, 12 * GB, 0x27, False) + mbr_entry(0, 0, 0, 0, False) + mbr_entry(3, 13 * GB, 5 * GB, 0x0F, False)
style, sig, parts = cbsys.parse_drive_layout(buf)
ck("MBR: bỏ mục trống + phân vùng mở rộng, giữ cờ active + chữ ký ổ", style == "mbr" and sig == "a1b2c3d4" and [(p.number, p.type, p.active) for p in parts] == [(1, 7, True), (2, 0x27, False)], [(p.number, p.type, p.active) for p in parts])
desc = bytearray(struct.pack("<IIBB??IIIIII", 1, 100, 0, 0, False, False, 40, 48, 0, 70, 17, 0)); desc += b"\0" * (100 - len(desc))
desc[40:47] = b"Samsung"; desc[48:67] = b"SSD 970 EVO 500GB\0\0"; desc[70:85] = b"S466NX0M123456\0"
dd = cbsys.parse_device_descriptor(bytes(desc))
ck("mô tả ổ: tên, số serial, kiểu NVMe, không tháo rời", dd == {"bus": 17, "removable": False, "model": "Samsung SSD 970 EVO 500GB", "serial": "S466NX0M123456"}, dd)
ext = struct.pack("<I4x", 1) + struct.pack("<I4xqq", 2, 277 * MB, 100 * GB)
ck("volume → (ổ, vị trí, dài)", cbsys.parse_disk_extents(ext) == [(2, 277 * MB, 100 * GB)])
ck("bộ đệm ngắn / rỗng không làm sập", cbsys.parse_drive_layout(b"") == ("raw", "", []) and cbsys.parse_disk_extents(b"") == [] and cbsys.parse_device_descriptor(b"")["bus"] == 0)
import ctypes
class PIE_GPT(ctypes.Structure): _fields_ = [("t", ctypes.c_ubyte * 16), ("i", ctypes.c_ubyte * 16), ("a", ctypes.c_uint64), ("n", ctypes.c_uint16 * 36)]
class PIE_MBR(ctypes.Structure): _fields_ = [("t", ctypes.c_ubyte), ("b", ctypes.c_ubyte), ("r", ctypes.c_ubyte), ("h", ctypes.c_uint32), ("g", ctypes.c_ubyte * 16)]
class PIE_U(ctypes.Union): _fields_ = [("m", PIE_MBR), ("g", PIE_GPT)]
class PIE(ctypes.Structure): _fields_ = [("style", ctypes.c_uint32), ("start", ctypes.c_int64), ("len", ctypes.c_int64), ("num", ctypes.c_uint32), ("rw", ctypes.c_ubyte), ("svc", ctypes.c_ubyte), ("u", PIE_U)]
class DL_GPT(ctypes.Structure): _fields_ = [("id", ctypes.c_ubyte * 16), ("s", ctypes.c_int64), ("l", ctypes.c_int64), ("m", ctypes.c_uint32)]
class DL_U(ctypes.Union): _fields_ = [("sig", ctypes.c_uint32 * 2), ("g", DL_GPT)]
class DL(ctypes.Structure): _fields_ = [("style", ctypes.c_uint32), ("count", ctypes.c_uint32), ("u", DL_U), ("p", PIE * 1)]
ck("đối chiếu với cấu trúc C: PARTITION_INFORMATION_EX = 144 byte, phần riêng ở byte 32; DRIVE_LAYOUT_INFORMATION_EX đầu 48 byte, tổng 192",
   ctypes.sizeof(PIE) == 144 and PIE.u.offset == 32 and PIE.start.offset == 8 and PIE.num.offset == 24 and PIE_GPT.a.offset == 32 and PIE_GPT.n.offset == 40
   and DL.p.offset == 48 and ctypes.sizeof(DL) == 192, (ctypes.sizeof(PIE), PIE.u.offset, DL.p.offset, ctypes.sizeof(DL)))

print("19. Nạp driver kèm bộ cài (cb\\drivers)")
fs = FakeSys("uefi"); cfg = cfg0(); u = usb(fs, cfg)
u.slots[0].vol.put("cb\\drivers\\doc-toi.txt", "x")
fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
rc, ui, inst = run(fs)
ck("thư mục driver chỉ có file hướng dẫn → không gọi nạp driver", rc == 0 and not any("/Add-Driver" in c for c in fs.cmds), rc)
fs = FakeSys("uefi"); cfg = cfg0(); u = usb(fs, cfg)
u.slots[0].vol.put("cb\\drivers\\doc-toi.txt", "x"); u.slots[0].vol.put("cb\\drivers\\lan\\rt640x64.inf", "inf")
fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
rc, ui, inst = run(fs)
dc = next((c for c in fs.cmds if "/Add-Driver" in c), [])
ck("có driver → gọi dism nạp vào Windows mới, dùng chỗ tạm trên ổ đích (không dùng ổ RAM của WinPE)", rc == 0 and dc[:2] == ["dism", "/English"] and "/Recurse" in dc
   and any(x.lower().startswith("/image:") for x in dc) and any(x.lower().endswith(":\\cb-scratch") and x.lower().startswith("/scratchdir:") for x in dc)
   and next(x for x in dc if x.startswith("/Driver:")).lower().endswith("\\cb\\drivers\\lan"), dc)
ck("dọn chỗ tạm sau khi nạp", any(c[:5] == ["cmd", "/c", "rd", "/s", "/q"] and c[5].lower().endswith(":\\cb-scratch") for c in fs.cmds), [c for c in fs.cmds if c[0] == "cmd"])
ck("nạp driver SAU khi bung Windows xong", [i for i, c in enumerate(fs.cmds) if "/Apply-Image" in c][0] < fs.cmds.index(dc), [c[:3] for c in fs.cmds])
recv = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and p.vol.label == "CBRECOVERY")
ck("driver được chép sang phân vùng cứu hộ (để cài lại từ xa cũng nạp)", recv.files.get("cb\\drivers\\lan\\rt640x64.inf") == "inf", sorted(k for k in recv.files if "drivers" in k))
ck("cỡ phân vùng cứu hộ có tính thêm phần driver", C.recovery_bytes(cfg0(), 600 * MB, 3 * GB) == 16 * GB and C.recovery_bytes(cfg0(), 600 * MB, 0) == 13 * GB
   and C.recovery_bytes(cfg0(), 600 * MB, None) == 13 * GB, C.recovery_bytes(cfg0(), 600 * MB, 3 * GB) / GB)
import cbrec as _cbrec
ck("tree_bytes: cộng cả thư mục con, không có thư mục → 0", _cbrec.tree_bytes(fs, "E:\\cb\\drivers") == len("x") + len("inf") and _cbrec.tree_bytes(fs, "E:\\khong-co") == 0 and _cbrec.extra_bytes(fs, "E:\\") == 4)
fs = FakeSys("uefi"); cfg = cfg0()
d, rec, win = cb_layout(fs, cfg, job=None)
rec.vol.put("cb\\drivers\\vga\\nv.inf", "inf"); rec.vol.put("cb\\job.json", json.dumps(job0(win, wipe="system", os="1511")))
rc, ui, inst = run(fs)
dc = next((c for c in fs.cmds if "/Add-Driver" in c), [])
ck("cài lại từ phân vùng cứu hộ: cũng nạp driver nằm trên phân vùng cứu hộ", rc == 0 and bool(dc) and next(x for x in dc if x.startswith("/Driver:")).lower().endswith("\\cb\\drivers\\vga") and "/Recurse" in dc, (rc, dc))

print("20. Driver riêng cho từng bản Windows (cb\\drivers\\1511, cb\\drivers\\22h2)")
def drv_media(fs, cfg):
    u = usb(fs, cfg); v = u.slots[0].vol
    for k in ("cb\\drivers\\doc-toi.txt", "cb\\drivers\\chung.inf", "cb\\drivers\\lan\\rt640x64.inf", "cb\\drivers\\1511\\vga\\nv_dispi.inf",
              "cb\\drivers\\1511\\lan-cu\\e1d65x64.inf", "cb\\drivers\\22h2\\wifi\\netwtw.inf"): v.put(k, "inf")
    fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
def drv_jobs(fs):
    return [(next(x for x in c if x.startswith("/Driver:"))[8:].lower().split("\\cb\\drivers")[-1] or "\\", "/Recurse" in c) for c in fs.cmds if "/Add-Driver" in c]
fs = FakeSys("uefi"); cfg = cfg0(); drv_media(fs, cfg)
rc, ui, inst = run(fs)
ck("cài 22H2: nạp file lẻ (không đệ quy) + thư mục chung + thư mục 22h2, KHÔNG nạp thư mục 1511", rc == 0 and drv_jobs(fs) == [("\\", False), ("\\22h2", True), ("\\lan", True)], drv_jobs(fs))
ck("có ghi rõ thư mục bị bỏ qua", any("Driver cua ban khac (1511)" in ln for ln in inst.lines), [ln for ln in inst.lines if "river" in ln])
fs = FakeSys("uefi"); cfg = cfg0(); drv_media(fs, cfg)
rc, ui, inst = run(fs, ["2", "\r"])
ck("cài 1511: nạp file lẻ + thư mục 1511 + thư mục chung, KHÔNG nạp thư mục 22h2", rc == 0 and drv_jobs(fs) == [("\\", False), ("\\1511", True), ("\\lan", True)], drv_jobs(fs))
recv = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and p.vol.label == "CBRECOVERY")
ck("phân vùng cứu hộ giữ driver của MỌI bản (để sau đổi bản vẫn có)", all(k in recv.files for k in ("cb\\drivers\\1511\\vga\\nv_dispi.inf", "cb\\drivers\\22h2\\wifi\\netwtw.inf", "cb\\drivers\\lan\\rt640x64.inf", "cb\\drivers\\chung.inf")))
ck("folder_applies: tên bản Windows chỉ khớp đúng bản; tên khác dùng chung", C.folder_applies("1511", "1511") and not C.folder_applies("1511", "22h2") and C.folder_applies("LAN", "22h2")
   and C.folder_applies("22H2", "22h2") and C.folder_applies("22h2", "22h2-2") and not C.folder_applies("22h2-2", "22h2") and C.folder_applies("22h2-2", "22h2-2")
   and not C.folder_applies("w11-23h2", "22h2") and not C.folder_applies("b99999", "22h2") and C.folder_applies("b99999", "b99999") and C.folder_applies("2024-driver", "1511") and C.folder_applies("vga", None))
ck("is_os_tag", all(C.is_os_tag(x) for x in ("1511", "22h2", "22H2", "1607", "w11-24h2", "b12345", "1511-2")) and not any(C.is_os_tag(x) for x in ("lan", "vga", "intel", "2024", "h22", "", "driver-1511")))

print("20b. Sau khi nạp driver: nhật ký ghi Windows mới có những gói driver nào — có driver CARD MẠNG không (21.11c)")
DRV_TABLE = """Deployment Image Servicing and Management tool
Version: 10.0.19041.3636

Image Version: 10.0.10586.0

Obtaining list of 3rd party drivers from the driver store...

Driver packages listing:

-------------- | ------------------ | ----- | ---------- | --------------------- | ---------- | ----------------
Published Name | Original File Name | Inbox | Class Name | Provider Name         | Date       | Version
-------------- | ------------------ | ----- | ---------- | --------------------- | ---------- | ----------------
oem0.inf       | rt640x64.inf       | No    | Net        | Realtek               | 5/10/2019  | 10.35.510.2019
oem1.inf       | netrtwlane.inf     | No    | Net        | Realtek Semiconductor Corp. | 1/2/2018 | 2023.66.1104.2017
oem2.inf       | nv_dispi.inf       | No    | Display    | NVIDIA                | 6/1/2021   | 27.21.14.6677
oem3.inf       | hdxrt.inf          | No    | MEDIA      | Realtek <b>           | 1/1/2019   | 6.0.1.8619

The operation completed successfully.
"""
rows = C.parse_dism_drivers(DRV_TABLE)
ck("đọc bảng driver của dism: tên công bố, tên file gốc, lớp (viết thường), hãng — chữ lạ trong tên hãng bị lược", [(r["pub"], r["inf"], r["cls"]) for r in rows] == [("oem0.inf", "rt640x64.inf", "net"),
   ("oem1.inf", "netrtwlane.inf", "net"), ("oem2.inf", "nv_dispi.inf", "display"), ("oem3.inf", "hdxrt.inf", "media")] and rows[3]["prov"] == "Realtek b" and rows[1]["prov"] == "Realtek Semiconductor"
   and C.parse_dism_drivers("") == [] and C.parse_dism_drivers(None) == [] and C.parse_dism_drivers("oem9.inf | thieu cot") == [], rows)
fs = FakeSys("uefi"); cfg = cfg0(); drv_media(fs, cfg); fs.drv_table = DRV_TABLE
rc, ui, inst = run(fs, ["2", "\r"])
gd = [c for c in fs.cmds if "/Get-Drivers" in c]
ck("cài 1511 có gói driver: sau khi nạp, hỏi dism danh sách driver của Windows mới (chỉ đọc) rồi ghi 1 dòng: số gói, card mạng (tên file + hãng), VGA",
   rc == 0 and len(gd) == 1 and gd[0][:2] == ["dism", "/English"] and "/Format:Table" in gd[0] and fs.cmds.index(gd[0]) > max(i for i, c in enumerate(fs.cmds) if "/Add-Driver" in c)
   and any("driver ben thu ba trong Windows moi: 4 goi - card mang: 2 (rt640x64.inf Realtek; netrtwlane.inf Realtek Semiconductor) | VGA: 1 | khac: 1" in ln for ln in inst.lines)
   and not any("KHONG co goi driver card mang" in ln for ln in inst.lines), [ln for ln in inst.lines if "river" in ln])
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
fs.drv_table = DRV_TABLE.replace("| Net        |", "| System     |")
rc, ui, inst = run(fs, ["2", "\r"])
ck("cài 1511 mà KHÔNG có gói driver card mạng nào → nhật ký cảnh báo rõ: máy có thể không có mạng, đưa gói driver card mạng cho bản 1511", rc == 0
   and any("(!) Ban Windows 1511 KHONG co goi driver card mang nao kem theo" in ln for ln in inst.lines) and any("dua goi driver card mang cho ban 1511" in ln for ln in inst.lines), [ln for ln in inst.lines if "river" in ln])
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt"); fs.drv_table = ""
rc, ui, inst = run(fs)
ck("cài 22H2 không kèm driver: không cảnh báo (Windows mới tự có driver card mạng), vẫn ghi dòng tổng", rc == 0 and any("driver ben thu ba trong Windows moi: 0 goi - card mang: 0 | VGA: 0 | khac: 0" in ln for ln in inst.lines)
   and not any("KHONG co goi driver card mang" in ln for ln in inst.lines), [ln for ln in inst.lines if "river" in ln])
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg); fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt"); fs.drv_table = None
rc, ui, inst = run(fs, ["2", "\r"])
ck("dism không liệt kê được driver → bỏ qua, vẫn cài xong", rc == 0 and not any("driver ben thu ba" in ln for ln in inst.lines))

print("21. Bản Windows tuỳ biến: file trả lời có sẵn, SetupComplete.cmd có sẵn")
import fakesys as _fk
fs = FakeSys("uefi"); cfg = cfg0(); usb(fs, cfg)
fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
rc, ui, inst = run(fs)
win = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and "windows\\cb-image.txt" in p.vol.files)
ua1, ua2 = win.files.get("windows\\panther\\unattend.xml", ""), win.files.get("windows\\panther\\unattend\\unattend.xml", "")
ck("file trả lời ghi vào CẢ HAI chỗ Windows có thể đọc (Panther và Panther\\Unattend)", rc == 0 and ua1 and ua1 == ua2 and "provision.cmd specialize" in ua2)
sc = win.files.get("windows\\setup\\scripts\\setupcomplete.cmd", b"")
ck("tạo SetupComplete.cmd gọi phần cài agent (lưới an toàn thứ 2)", sc == b'@echo off\r\ncall "C:\\CloudBluePC\\os\\provision.cmd" setupcomplete\r\n', sc)

class CustomFS(FakeSys):
    """Ảnh Windows tuỳ biến: bung ra đã có sẵn file trả lời (kèm khoá) + SetupComplete.cmd của người làm."""
    def run(self, argv, timeout=3600, show=False, input=None, change=True):
        r = super().run(argv, timeout, show, input, change)
        if argv and os.path.basename(argv[0]).lower().startswith("dism") and "/Apply-Image" in argv and r[0] == 0:
            a = {x.split(":", 1)[0].lower(): x.split(":", 1)[1] for x in argv[1:] if x.startswith("/") and ":" in x}
            v, rel = self._res(a["/applydir"])
            v.put("windows\\panther\\unattend\\unattend.xml", "<unattend><settings pass='specialize'><ProductKey>W269N-WFGWX-YVC9B-4J6C9-T83GX</ProductKey></settings></unattend>")
            v.put("windows\\setup\\scripts\\setupcomplete.cmd", b"\xef\xbb\xbf@echo off\r\necho cua nguoi lam ban Lite\r\n")
        return r
fs = CustomFS("uefi"); cfg = cfg0(); usb(fs, cfg)
fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
rc, ui, inst = run(fs)
win = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and "windows\\cb-image.txt" in p.vol.files)
ua1, ua2 = win.files.get("windows\\panther\\unattend.xml", ""), win.files.get("windows\\panther\\unattend\\unattend.xml", "")
ck("ảnh có sẵn Panther\\Unattend\\unattend.xml → bị thay bằng file của CloudBlue (không thì agent không được cài)", rc == 0 and ua1 == ua2 and "provision.cmd firstlogon" in ua2 and "cua nguoi lam" not in ua2)
ck("khoá sản phẩm trong file trả lời cũ được giữ lại (bản 22H2 bình thường không điền khoá)", "<ProductKey>W269N-WFGWX-YVC9B-4J6C9-T83GX</ProductKey>" in ua1, ua1[:400])
sc = win.files.get("windows\\setup\\scripts\\setupcomplete.cmd", b"")
ck("SetupComplete.cmd có sẵn → giữ nguyên phần cũ, dòng gọi CloudBlue chèn lên ĐẦU, bỏ dấu BOM", sc == b'call "C:\\CloudBluePC\\os\\provision.cmd" setupcomplete\r\n@echo off\r\necho cua nguoi lam ban Lite\r\n', sc)
ck("có ghi nhật ký 2 việc trên", any("giu lai" in ln for ln in inst.lines) and any("SetupComplete.cmd" in ln for ln in inst.lines))
fs2 = CustomFS("uefi"); cfg2 = cfg0(generic_key="off"); usb(fs2, cfg2)
fs2.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
rc, ui, inst = run(fs2)
win = next(p.vol for d in fs2.fdisks for p in d.slots if p.vol and "windows\\cb-image.txt" in p.vol.files)
ck("tắt hẳn khoá (off) → không giữ khoá cũ", rc == 0 and "<ProductKey>" not in win.files.get("windows\\panther\\unattend.xml", "x<ProductKey>"))

print("22. Gói cài lần đầu riêng từng bản Windows (os\\firstboot.d\\<bản>): chỉ chép bản đang cài vào ổ C:, phân vùng cứu hộ giữ đủ")
FB = ("cb\\os\\firstboot.d\\10-chung.cmd", "cb\\os\\firstboot.d\\cong-cu\\tool.txt", "cb\\os\\firstboot.d\\1511\\10-nvidia-vga.cmd",
      "cb\\os\\firstboot.d\\1511\\nvidia-vga-466.77.exe", "cb\\os\\firstboot.d\\22h2\\20-app.cmd")
def fb_media(fs, cfg):
    u = usb(fs, cfg); v = u.slots[0].vol
    for k in FB: v.put(k, "x")
    fs.disk(0, 240, bus=11, model="Kingston A400", ssd=True, style="gpt")
def fb_on(vol, prefix): return sorted(k[len(prefix):] for k in vol.files if k.startswith(prefix))
def fb_vols(fs):
    win = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and "windows\\cb-image.txt" in p.vol.files)
    rec = next(p.vol for d in fs.fdisks for p in d.slots if p.vol and p.vol.label == "CBRECOVERY")
    return win, rec
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
rc, ui, inst = run(fs)
win, rec = fb_vols(fs)
ck("cài 22H2: ổ C: có script chung + thư mục thường + thư mục 22h2, KHÔNG có gói của bản 1511", rc == 0 and fb_on(win, "cloudbluepc\\os\\firstboot.d\\")
   == ["10-chung.cmd", "22h2\\20-app.cmd", "cong-cu\\tool.txt"], fb_on(win, "cloudbluepc\\os\\firstboot.d\\"))
ck("cài 22H2: phân vùng cứu hộ vẫn giữ gói của MỌI bản", fb_on(rec, "cb\\os\\firstboot.d\\")
   == ["10-chung.cmd", "1511\\10-nvidia-vga.cmd", "1511\\nvidia-vga-466.77.exe", "22h2\\20-app.cmd", "cong-cu\\tool.txt"], fb_on(rec, "cb\\os\\firstboot.d\\"))
ck("phần còn lại của os\\ vẫn chép đủ", all(k in win.files for k in ("cloudbluepc\\os\\provision.cmd", "cloudbluepc\\os\\unattend.tpl.xml")))
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
rc, ui, inst = run(fs, ["2", "\r"])
win, rec = fb_vols(fs)
ck("cài 1511: ổ C: có gói 1511 (cả file .exe), KHÔNG có thư mục 22h2", rc == 0 and fb_on(win, "cloudbluepc\\os\\firstboot.d\\")
   == ["10-chung.cmd", "1511\\10-nvidia-vga.cmd", "1511\\nvidia-vga-466.77.exe", "cong-cu\\tool.txt"], fb_on(win, "cloudbluepc\\os\\firstboot.d\\"))
fs = FakeSys("uefi"); cfg = cfg0()
d, recp, winp = cb_layout(fs, cfg, job0())
for k in FB: recp.vol.put(k, "x")
job = json.loads(recp.vol.files["cb\\job.json"]); job["win"] = {"offset": winp.offset, "size": winp.size}; recp.vol.put("cb\\job.json", json.dumps(job))
rc, ui, inst = run(fs)
win, rec = fb_vols(fs)
ck("cài lại từ xa sang 1511 (từ phân vùng cứu hộ): ổ C: nhận gói 1511, không nhận 22h2; phân vùng cứu hộ còn đủ", rc == 0
   and fb_on(win, "cloudbluepc\\os\\firstboot.d\\") == ["10-chung.cmd", "1511\\10-nvidia-vga.cmd", "1511\\nvidia-vga-466.77.exe", "cong-cu\\tool.txt"]
   and "cb\\os\\firstboot.d\\22h2\\20-app.cmd" in rec.files, (rc, fb_on(win, "cloudbluepc\\os\\firstboot.d\\")))

print("23. Múi giờ đặt sẵn trong Windows mới + dịch vụ khởi động (lưới an toàn thứ 3) + nhận ra bản Windows kiểu ghost")
OOBE_REG = "\r\nHKEY_LOCAL_MACHINE\\CB_OFFSYS\\Setup\r\n    SetupType    REG_DWORD    0x2\r\n    SystemSetupInProgress    REG_DWORD    0x1\r\n    CmdLine    REG_SZ    oobe\\windeploy.exe\r\n    OOBEInProgress    REG_DWORD    0x1\r\n"
GHOST_REG = "\r\nHKEY_LOCAL_MACHINE\\CB_OFFSYS\\Setup\r\n    SetupType    REG_DWORD    0x0\r\n    SystemSetupInProgress    REG_DWORD    0x0\r\n    CmdLine    REG_SZ    \r\n    OOBEInProgress    REG_DWORD    0x0\r\n"
def regs(fs, verb): return [c for c in fs.cmds if c[0] == "reg" and c[1] == verb]
def image_json(fs):
    win, _ = fb_vols(fs)
    return json.loads(win.files["cloudbluepc\\logs\\image.json"])
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg); fs.reg_off = {"Select": "    Default    REG_DWORD    0x1\r\n", "Setup": OOBE_REG}
rc, ui, inst = run(fs)
tz = next((c for c in fs.cmds if c[0] == "dism" and any(x.startswith("/Set-TimeZone:") for x in c)), [])
ck("đặt múi giờ ngay trong Windows vừa bung (dism /Set-TimeZone, đúng ổ đích, dùng chỗ tạm trên ổ đích) — đồng hồ không lệch ở lần khởi động đầu",
   rc == 0 and "/Set-TimeZone:SE Asia Standard Time" in tz and any(x.lower().startswith("/image:") for x in tz) and any(x.startswith("/ScratchDir:") for x in tz)
   and [i for i, c in enumerate(fs.cmds) if "/Apply-Image" in c][0] < fs.cmds.index(tz), tz)
adds = regs(fs, "add")
ck("nạp kho registry của Windows mới → ghi dịch vụ khởi động CloudBluePCBoot (6 giá trị) → nhả kho, đúng thứ tự", len(regs(fs, "load")) == 1 and regs(fs, "load")[0][2] == "HKLM\\CB_OFFSYS"
   and regs(fs, "load")[0][3].lower().endswith(":\\windows\\system32\\config\\system") and len(adds) == 6 and all(c[2] == "HKLM\\CB_OFFSYS\\ControlSet001\\Services\\CloudBluePCBoot" for c in adds)
   and fs.cmds.index(regs(fs, "load")[0]) < fs.cmds.index(adds[0]) < fs.cmds.index(adds[-1]) < fs.cmds.index(regs(fs, "unload")[0]) and not fs.reg_loaded, [c[:5] for c in fs.cmds if c[0] == "reg"])
vals = {c[4]: (c[6], c[8]) for c in adds}
ck("dịch vụ: tự chạy lúc khởi động bằng SYSTEM, lỗi thì Windows bỏ qua, gọi đúng cb_provision.py boot", vals["Start"] == ("REG_DWORD", "2") and vals["Type"] == ("REG_DWORD", "16") and vals["ErrorControl"] == ("REG_DWORD", "0")
   and vals["ObjectName"] == ("REG_SZ", "LocalSystem") and vals["ImagePath"] == ("REG_EXPAND_SZ", '%SystemRoot%\\System32\\cmd.exe /c start "" /b "C:\\CloudBluePC\\py\\pythonw.exe" -I -B "C:\\CloudBluePC\\os\\cb_provision.py" boot'), vals)
ck("bản Windows chuẩn (đang ở trạng thái cài đặt lần đầu): ghi nhận, không cảnh báo", image_json(fs) == {"oobe": True, "control_set": 1, "boot_svc": True} and not any("kieu GHOST" in x for x in fs.logs), image_json(fs))
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg); fs.reg_off = {"Select": "    Default    REG_DWORD    0x2\r\n", "Setup": GHOST_REG}
rc, ui, inst = run(fs)
ck("bản Windows kiểu GHOST (không qua bước cài lần đầu): vẫn cài xong, cảnh báo rõ trên màn hình bộ cài, dịch vụ ghi đúng ControlSet đang dùng (002)",
   rc == 0 and image_json(fs) == {"oobe": False, "control_set": 2, "boot_svc": True} and any("kieu GHOST" in x for x in fs.logs) and any("TU KHOI DONG LAI 1 lan" in x for x in fs.logs)
   and all(c[2] == "HKLM\\CB_OFFSYS\\ControlSet002\\Services\\CloudBluePCBoot" for c in regs(fs, "add")) and len(regs(fs, "add")) == 6, (image_json(fs), [x for x in fs.logs if "ghost" in x]))
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
rc, ui, inst = run(fs)
ck("không đọc được trạng thái (kho thiếu khoá) → coi là 'không biết', vẫn chèn dịch vụ vào ControlSet001, không cảnh báo nhầm", rc == 0 and image_json(fs) == {"oobe": None, "control_set": 1, "boot_svc": True}
   and len(regs(fs, "add")) == 6 and not any("kieu GHOST" in x for x in fs.logs), image_json(fs))
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg); fs.fail_reg_load = True; fs.fail_tz = True
rc, ui, inst = run(fs)
win, _ = fb_vols(fs)
ck("không nạp được kho registry + dism đặt múi giờ lỗi → ghi nhật ký, BỎ QUA, Windows vẫn cài xong (2 lưới kia còn nguyên)", rc == 0 and not regs(fs, "add") and any("khong nap duoc kho registry" in x for x in fs.logs)
   and any("mui gio" in x and "bo qua" in x for x in fs.logs) and "windows\\panther\\unattend.xml" in win.files and "windows\\setup\\scripts\\setupcomplete.cmd" in win.files, [x for x in fs.logs if "mui gio" in x or "registry" in x])
fs = FakeSys("uefi"); cfg = cfg0()
d, recp, winp = cb_layout(fs, cfg, job0()); fs.reg_off = {"Setup": OOBE_REG}
rc, ui, inst = run(fs)
ck("cài lại từ xa (từ phân vùng cứu hộ): cũng đặt múi giờ + chèn dịch vụ khởi động", rc == 0 and any(c[0] == "dism" and "/Set-TimeZone:SE Asia Standard Time" in c for c in fs.cmds) and len(regs(fs, "add")) == 6 and not fs.reg_loaded)
ck("setup_state: đọc đúng chữ reg in ra", C.setup_state(OOBE_REG) is True and C.setup_state(GHOST_REG) is False and C.setup_state("") is None and C.setup_state("ERROR: x") is None
   and C.setup_state("    SetupType    REG_DWORD    0x1\r\n") is True)

print("24. Cài xong từ USB / ISO: hiện 1 ô cho người cài gõ SỐ MÁY (21.11b)")
def run_code(lines, cfg_extra=None):
    fs = FakeSys("uefi"); cfg = dict(cfg0(), **(cfg_extra or {})); fb_media(fs, cfg)
    ui = ScriptUI(); ui.lines = list(lines)
    inst = cb_pe.Installer(fs); rc = inst.run(ui)
    win, _ = fb_vols(fs)
    return rc, ui, fs, json.loads(win.files["cloudbluepc\\seed.json"])
rc, ui, fs, seed = run_code(["14-85"])
ck("Windows bung xong → màn hình bộ cài hỏi 'So may' (chờ 120 giây), gõ 14-85 → ghi vào seed.json để máy báo về web", rc == 0 and (120, "<line> So may") in ui.prompts and seed.get("code") == "14-85"
   and any("WINDOWS DA CAI XONG" in x for x in fs.logs) and any("So may: 14-85" in x for x in fs.logs), (ui.prompts[-3:], seed))
ck("ô hỏi hiện SAU khi bung Windows (người cài còn ngồi đó), TRƯỚC dòng XONG", next(i for i, x in enumerate(fs.logs) if "WINDOWS DA CAI XONG" in x) > next(i for i, x in enumerate(fs.logs) if "100%" in x or "Bung" in x or "bung" in x)
   and next(i for i, x in enumerate(fs.logs) if "So may: 14-85" in x) < next(i for i, x in enumerate(fs.logs) if x.startswith("XONG sau")), [x for x in fs.logs if "XONG" in x or "So may" in x])
rc, ui, fs, seed = run_code(["  a07 <b>khu 2</b>  "])
ck("số máy được làm sạch: bỏ ký tự lạ, viết hoa", seed.get("code") == "A07 BKHU 2/B", seed.get("code"))
rc, ui, fs, seed = run_code([""])
ck("bấm Enter trống → bỏ qua, không ghi số máy, vẫn cài xong", rc == 0 and "code" not in seed and any("So may: (bo qua)" in x for x in fs.logs))
rc, ui, fs, seed = run_code([])
ck("không ai gõ (hết giờ chờ) → bỏ qua, vẫn cài xong", rc == 0 and "code" not in seed)
rc, ui, fs, seed = run_code(["9"], {"ask_code": False})
ck('cb.json "ask_code": false → không hỏi', rc == 0 and not any(p[1].startswith("<line>") for p in ui.prompts) and "code" not in seed)
rc, ui, fs, seed = run_code(["7"], {"code_wait": 600})
ck("thời gian chờ đổi được bằng code_wait", (600, "<line> So may") in ui.prompts and seed.get("code") == "7")
ck("clean_code: giữ chữ số . _ / - và dấu cách, tối đa 24 ký tự, rỗng nếu toàn ký tự lạ", C.clean_code(" khu-a_1.2/3 ") == "KHU-A_1.2/3" and C.clean_code("<>\"'") == "" and C.clean_code(None) == ""
   and len(C.clean_code("9" * 60)) == 24 and C.clean_code("a   b") == "A B")
import io as _io, contextlib as _ctx
class KeySys:                                                      # bàn phím giả cho ô gõ thật (ConsoleUI.line): mỗi lần hỏi trả 1 phím trong danh sách, hết thì None
    def __init__(self, keys): self.keys = list(keys)
    def key_wait(self, seconds): return self.keys.pop(0) if self.keys else None
def typed(keys, secs=5):
    with _ctx.redirect_stdout(_io.StringIO()): return cb_pe.ConsoleUI(KeySys(keys)).line(secs, "So may")
ck("ô gõ thật: gõ 1 4 - 8 5 rồi Enter → '14-85'; Backspace xoá được; Esc = bỏ", typed(list("14-85") + ["\r"]) == "14-85" and typed(["1", "2", "\x08", "4", "\r"]) == "14" and typed(["9", "\x1b"]) == "")
ck("ô gõ thật: không ai gõ → None sau đúng số giây chờ; gõ dở rồi bỏ đó → lấy phần đã gõ", typed([]) is None and typed(["a", "7"]) == "a7" and typed(["\r"]) == "")
ck("ô gõ thật: không nhận quá 24 ký tự, bỏ phím điều khiển lạ", typed(list("x" * 40) + ["\r"]) == "x" * 24 and typed(["\t", "5", "\r"]) == "5")
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
ui = ScriptUI(); ui.lines = ["55"]
assert cb_pe.Installer(fs).run(ui) == 0
win, rec = fb_vols(fs); fs.fdisks = [d for d in fs.fdisks if d.index != 9]
rec.put("cb\\job.json", json.dumps(job0(win=None, wipe="all") if False else job0(wipe="all")))
ui2 = ScriptUI(); ui2.lines = ["99"]
rc2 = cb_pe.Installer(fs).run(ui2)
win2, _ = fb_vols(fs)
ck("cài lại TỪ XA (lệnh từ web, không ai ngồi máy) → KHÔNG hỏi số máy; số máy cũ do web giữ", rc2 == 0 and not any(p[1].startswith("<line>") for p in ui2.prompts) and "code" not in json.loads(win2.files["cloudbluepc\\seed.json"]), ui2.prompts[-3:])

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
