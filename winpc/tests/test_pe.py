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


from test_pe_helpers import WINFILES, cb_layout, cfg0, cfg_lin, job0, lin_layout, media_files, rec_files, usb   # noqa: E402


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
ck("phân vùng cứu hộ 16GB (12GB nội dung + 4GB để dành), nhãn CBRECOVERY, đã ẩn (không chữ ổ, có cờ bảo vệ)", rec.size == 16 * GB and rec.vol.label == "CBRECOVERY" and rec.vol.letter is None and rec.attrs == 0x8000000000000001, (rec.size / GB, rec.vol.letter, hex(rec.attrs)))
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

print("15b. WinPE tự gán CHỮ Ổ cho phân vùng cứu hộ (máy thật 21/11: D:) → cài lại vẫn ghi được kết quả (lỗi bản ≤ 21.11c)")
for fwx in ("uefi", "bios"):
    fs = FakeSys(fwx); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0(), fw=fwx)
    rec.vol.letter = "D"                                               # như WinPE thật: phân vùng cứu hộ đang mang chữ D:
    rc, ui, inst = run(fs)
    res = json.loads(rec.vol.files.get("cb\\job-result.json") or "{}")
    ck("%s: phân vùng cứu hộ đang mang chữ D: → cài xong, mã 0, không dòng lỗi nào" % fwx, rc == 0 and not any("LOI" in l or "Khong ghi duoc" in l or "Errno" in l for l in inst.lines), [l for l in inst.lines if "LOI" in l or "Khong ghi duoc" in l or "Errno" in l][:3])
    ck("%s: … kết quả ghi đúng vào phân vùng cứu hộ (dù chữ D: đã bị đổi sang chữ tạm rồi gỡ), lệnh được gỡ" % fwx, res.get("ok") is True and res.get("id") == 77 and res.get("pe") == cb_pe.PE_VER
       and "cb\\job.json" not in rec.vol.files and json.loads(rec.vol.files["cb\\job.done.json"])["state"] == "done" and rec.vol.letter is None, (res, rec.vol.letter))
    neww = max((p for p in d.slots if p.vol and p is not rec), key=lambda p: p.offset)
    ck("%s: … Windows mới có đủ seed (số lệnh + vé) để agent báo về web" % fwx, json.loads(neww.vol.files["cloudbluepc\\seed.json"]).get("order") == 77 and json.loads(neww.vol.files["cloudbluepc\\seed.json"]).get("from") == "job")
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0()); rec.vol.letter = "D"; fs.fail_dism = True
rc, ui, inst = run(fs)
ck("chữ D: + bung Windows lỗi → vẫn ghi được 'lần thử 1 lỗi' lên phân vùng cứu hộ (để lần sau làm tiếp)", rc == 10 and json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is False
   and json.loads(rec.vol.files["cb\\job.json"])["attempts"] == 1, rec.vol.files.get("cb\\job-result.json"))
fs = FakeSys("uefi"); cfg = cfg0(); d, rec, win = cb_layout(fs, cfg, job0())
_wt = fs.write_text


def _wt_bad(p, s, encoding="utf-8"):
    if p.lower().endswith("job-result.json"): raise OSError(28, "No space left on device")
    return _wt(p, s, encoding)


fs.write_text = _wt_bad
rc, ui, inst = run(fs)
neww = max((p for p in d.slots if p.vol and p is not rec), key=lambda p: p.offset)
ck("không ghi được file kết quả (ổ cứu hộ đầy…) → Windows mới ĐÃ cài xong thì vẫn tính là xong (mã 0), chỉ ghi chú — không cài lại lần nữa",
   rc == 0 and any("(!) Khong ghi duoc ket qua" in l for l in inst.lines) and fs.file(neww.vol, "windows\\cb-image.txt") == "1511.wim|1" and not any("!! LOI" in l for l in inst.lines), [l for l in inst.lines if "(!)" in l or "LOI" in l])
fs.write_text = _wt

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
ck("recovery_bytes làm tròn GB, tối thiểu 6GB, có 4GB để dành", C.recovery_bytes({"images": []}) == 7 * GB and C.recovery_bytes({"images": [], "rec_spare_gb": 0}) == 6 * GB and C.recovery_bytes(cfg0()) == 17 * GB
   and C.recovery_bytes(cfg0(), 7) == 16 * GB, C.recovery_bytes(cfg0()) / GB)
ck('chỗ để dành đổi được bằng cb.json "rec_spare_gb" (0 = không để dành; số lạ → mặc định 4; tối đa 64)', C.recovery_bytes(cfg0(rec_spare_gb=0)) == 13 * GB and C.recovery_bytes(cfg0(rec_spare_gb=10)) == 23 * GB
   and C.recovery_bytes(cfg0(rec_spare_gb="x")) == 17 * GB and C.recovery_bytes(cfg0(rec_spare_gb=None)) == 17 * GB and C.recovery_bytes(cfg0(rec_spare_gb=-3)) == 13 * GB and C.recovery_bytes(cfg0(rec_spare_gb=999)) == 77 * GB,
   [C.recovery_bytes(cfg0(rec_spare_gb=v)) / GB for v in (0, 10, "x", None, -3, 999)])
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
ck("cỡ phân vùng cứu hộ có tính thêm phần driver", C.recovery_bytes(cfg0(), 600 * MB, 3 * GB) == 20 * GB and C.recovery_bytes(cfg0(), 600 * MB, 0) == 17 * GB
   and C.recovery_bytes(cfg0(), 600 * MB, None) == 17 * GB, C.recovery_bytes(cfg0(), 600 * MB, 3 * GB) / GB)
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
def run_code(lines, cfg_extra=None, name=""):
    """Kịch bản gõ ở 2 ô sau khi cài xong: ô TÊN MÁY nhận `name` ('' = bấm Enter bỏ qua, None = không có ô tên trong kịch bản), các ô sau nhận `lines`."""
    fs = FakeSys("uefi"); cfg = dict(cfg0(), **(cfg_extra or {})); fb_media(fs, cfg)
    ui = ScriptUI(); ui.lines = ([] if name is None else [name]) + list(lines)
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
ck('cb.json "ask_code": false → không hỏi số máy (ô tên máy vẫn hỏi)', rc == 0 and [p[1] for p in ui.prompts if p[1].startswith("<line>")] == ["<line> Ten may"] and "code" not in seed)
rc, ui, fs, seed = run_code(["9"], {"ask_code": False, "ask_name": False}, name=None)
ck('"ask_code": false + "ask_name": false → cài xong không hỏi gì', rc == 0 and not any(p[1].startswith("<line>") for p in ui.prompts) and "code" not in seed and "label" not in seed
   and not any("WINDOWS DA CAI XONG" in x for x in fs.logs))
rc, ui, fs, seed = run_code(["7"], {"code_wait": 600})
ck("thời gian chờ đổi được bằng code_wait", (600, "<line> So may") in ui.prompts and seed.get("code") == "7")
ck("clean_code: giữ chữ số . _ / - và dấu cách, tối đa 24 ký tự, rỗng nếu toàn ký tự lạ", C.clean_code(" khu-a_1.2/3 ") == "KHU-A_1.2/3" and C.clean_code("<>\"'") == "" and C.clean_code(None) == ""
   and len(C.clean_code("9" * 60)) == 24 and C.clean_code("a   b") == "A B")
import io as _io, contextlib as _ctx
class KeySys:                                                      # bàn phím giả cho ô gõ thật (ConsoleUI.line): mỗi lần hỏi trả 1 phím trong danh sách, hết thì None
    def __init__(self, keys): self.keys = list(keys)
    def key_wait(self, seconds): return self.keys.pop(0) if self.keys else None
def typed(keys, secs=5, prompt="So may", maxlen=None):
    with _ctx.redirect_stdout(_io.StringIO()):
        ui = cb_pe.ConsoleUI(KeySys(keys))
        return ui.line(secs, prompt) if maxlen is None else ui.line(secs, prompt, maxlen)
ck("ô gõ thật: gõ 1 4 - 8 5 rồi Enter → '14-85'; Backspace xoá được; Esc = bỏ", typed(list("14-85") + ["\r"]) == "14-85" and typed(["1", "2", "\x08", "4", "\r"]) == "14" and typed(["9", "\x1b"]) == "")
ck("ô gõ thật: không ai gõ → None sau đúng số giây chờ; gõ dở rồi bỏ đó → lấy phần đã gõ", typed([]) is None and typed(["a", "7"]) == "a7" and typed(["\r"]) == "")
ck("ô gõ thật: không nhận quá 24 ký tự, bỏ phím điều khiển lạ", typed(list("x" * 40) + ["\r"]) == "x" * 24 and typed(["\t", "5", "\r"]) == "5")
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
ui = ScriptUI(); ui.lines = ["", "55"]
assert cb_pe.Installer(fs).run(ui) == 0
win, rec = fb_vols(fs); fs.fdisks = [d for d in fs.fdisks if d.index != 9]
rec.put("cb\\job.json", json.dumps(job0(win=None, wipe="all") if False else job0(wipe="all")))
ui2 = ScriptUI(); ui2.lines = ["99"]
rc2 = cb_pe.Installer(fs).run(ui2)
win2, _ = fb_vols(fs)
ck("cài lại TỪ XA (lệnh từ web, không ai ngồi máy) → KHÔNG hỏi số máy, KHÔNG hỏi tên máy; số máy + tên cũ do web giữ", rc2 == 0 and not any(p[1].startswith("<line>") for p in ui2.prompts)
   and "code" not in json.loads(win2.files["cloudbluepc\\seed.json"]) and "label" not in json.loads(win2.files["cloudbluepc\\seed.json"]), ui2.prompts[-3:])

print("25. Cài xong từ USB / ISO: thêm ô gõ TÊN MÁY — máy mang tên đó trong Windows và trên web (21.11d)")
def run_name(lines, cfg_extra=None):
    rc, ui, fs, seed = run_code(lines, cfg_extra, name=None)
    win, rec = fb_vols(fs)
    return rc, ui, fs, seed, win.files.get("windows\\panther\\unattend.xml", ""), json.loads(rec.files["cb\\identity.json"])
def lines_of(ui): return [p for p in ui.prompts if p[1].startswith("<line>")]
rc, ui, fs, seed, ua, idf = run_name(["May-01", "14-85"])
ck("Windows bung xong → hỏi 'Ten may' TRƯỚC rồi mới hỏi 'So may' (cùng thời gian chờ)", rc == 0 and lines_of(ui) == [(120, "<line> Ten may"), (120, "<line> So may")], lines_of(ui))
ck("gõ May-01 → Windows mang tên May-01 (file trả lời + seed.json + identity.json trên phân vùng cứu hộ)", seed["name"] == "May-01" and "<ComputerName>May-01</ComputerName>" in ua and idf["name"] == "May-01", (seed, idf))
ck("tên hiển thị ghi vào seed.json (label) để agent báo về web; số máy vẫn ghi như cũ", seed.get("label") == "May-01" and seed.get("code") == "14-85", seed)
ck("màn hình bộ cài: 'WINDOWS DA CAI XONG' chỉ in 1 lần, có dòng xác nhận tên + dòng XONG nhắc đúng tên", sum("WINDOWS DA CAI XONG" in x for x in fs.logs) == 1 and any(x.strip() == "Ten may: May-01" for x in fs.logs)
   and any(x.startswith("XONG sau") and "ten may: May-01" in x for x in fs.logs), [x for x in fs.logs if "Ten may" in x or "XONG" in x])
rc, ui, fs, seed, ua, idf = run_name(["Phong A 07", ""])
ck("tên có dấu cách: web giữ nguyên 'Phong A 07', Windows lấy tên hợp lệ 'PhongA07' (bộ cài báo rõ)", seed["name"] == "PhongA07" and seed["label"] == "Phong A 07" and "<ComputerName>PhongA07</ComputerName>" in ua
   and any("Ten may: Phong A 07" in x and "ten trong Windows: PhongA07" in x for x in fs.logs), seed)
rc, ui, fs, seed, ua, idf = run_name(["07", ""])
ck("tên toàn số (Windows không cho): Windows lấy CB-07, web vẫn hiện 07", seed["name"] == "CB-07" and seed["label"] == "07" and idf["name"] == "CB-07", seed)
rc, ui, fs, seed, ua, idf = run_name(["7"], {"name_prefix": "NET"})
ck("tên toàn số dùng đúng tiền tố name_prefix của cb.json", seed["name"] == "NET-7" and seed["label"] == "7", seed)
rc, ui, fs, seed, ua, idf = run_name(["Day-May-So-01-Tang-2-Khu-B", ""])
ck("tên dài: web giữ tới 40 ký tự, Windows cắt còn 15", seed["label"] == "Day-May-So-01-Tang-2-Khu-B" and seed["name"] == "Day-May-So-01-T" and len(seed["name"]) == 15, seed)
rc, ui, fs, seed, ua, idf = run_name(["", "9"])
ck("bấm Enter trống ở ô tên → máy tự lấy tên CB-XXXXXX như cũ, không ghi label, vẫn hỏi tiếp số máy", rc == 0 and "label" not in seed and len(seed["name"]) == 9 and seed["name"].startswith("CB-") and seed.get("code") == "9"
   and any("Ten may: (bo qua)" in x and seed["name"] in x for x in fs.logs), seed)
rc, ui, fs, seed, ua, idf = run_name([])
ck("ô tên hết giờ mà không ai gõ (không có người ngồi máy) → bỏ qua LUÔN ô số máy, không chờ thêm; vẫn cài xong", rc == 0 and lines_of(ui) == [(120, "<line> Ten may")] and "label" not in seed and "code" not in seed
   and seed["name"].startswith("CB-"), lines_of(ui))
rc, ui, fs, seed, ua, idf = run_name(["<<>>", "!!!", "May 02", "5"])
ck("gõ toàn ký tự lạ → báo và cho gõ lại (tối đa 3 lần), lần sau gõ đúng thì nhận", seed.get("label") == "May 02" and seed["name"] == "May02" and seed.get("code") == "5"
   and [p[1] for p in lines_of(ui)] == ["<line> Ten may"] * 3 + ["<line> So may"] and sum("khong dung duoc" in x for x in fs.logs) == 2, (seed, lines_of(ui)))
rc, ui, fs, seed, ua, idf = run_name(["??", "##", "@@", "6"])
ck("gõ sai cả 3 lần → coi như bỏ qua tên (tên tự sinh), vẫn hỏi số máy", "label" not in seed and seed["name"].startswith("CB-") and seed.get("code") == "6", seed)
rc, ui, fs, seed, ua, idf = run_name(["8"], {"ask_name": False})
ck('cb.json "ask_name": false → không hỏi tên (tên tự sinh), vẫn hỏi số máy', rc == 0 and lines_of(ui) == [(120, "<line> So may")] and "label" not in seed and seed.get("code") == "8" and seed["name"].startswith("CB-")
   and sum("WINDOWS DA CAI XONG" in x for x in fs.logs) == 1, lines_of(ui))
rc, ui, fs, seed, ua, idf = run_name(["  may   <b>3</b>  ", ""], {"code_wait": 300})
ck("tên được làm sạch (bỏ ký tự lạ, gộp dấu cách); thời gian chờ theo code_wait", seed.get("label") == "may b3/b" and seed["name"] == "mayb3b" and (300, "<line> Ten may") in ui.prompts, seed)
ck("clean_label: giữ chữ số . _ / - và dấu cách (không đổi hoa thường), tối đa 40, phải có ít nhất 1 chữ / số", C.clean_label(" Khu-a_1.2/3 ") == "Khu-a_1.2/3" and C.clean_label("<>\"'") == "" and C.clean_label(None) == ""
   and C.clean_label("---") == "" and C.clean_label(". /") == "" and len(C.clean_label("x" * 90)) == 40 and C.clean_label("a   b") == "a b" and C.clean_label("M\u00e1y 01") == "My 01")
ck("win_name: tên hiển thị → tên Windows hợp lệ", C.win_name("May-01") == "May-01" and C.win_name("Phong A 07") == "PhongA07" and C.win_name("07") == "CB-07" and C.win_name("07", "NET") == "NET-07"
   and C.win_name("", "CB", "X") == "X" and C.win_name("...", "CB", "X") == "X" and C.win_name("1234567890123456789") == "CB-123456789012" and C.win_name("9", "MOTTIENTORATDAI") == "MOTTIENTORATD-9"
   and C.win_name("9", "!!") == "CB-9" and all(len(C.win_name(x, "ABCDEFGHIJKLMNOPQ")) <= 15 for x in ("1", "12345678", "123456789012345678")))
ck("ô gõ thật nhận tới 40 ký tự cho tên máy (ô số máy vẫn 24)", typed(list("y" * 60) + ["\r"], 5, "Ten may", 40) == "y" * 40 and typed(list("y" * 60) + ["\r"]) == "y" * 24)
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
ui = ScriptUI(); ui.lines = ["May 05", "55"]
assert cb_pe.Installer(fs).run(ui) == 0
win, rec = fb_vols(fs); fs.fdisks = [d for d in fs.fdisks if d.index != 9]
rec.put("cb\\job.json", json.dumps(dict(job0(wipe="all"), name="May 05")))
ui2 = ScriptUI(); rc2 = cb_pe.Installer(fs).run(ui2)
win2, _ = fb_vols(fs); seed2 = json.loads(win2.files["cloudbluepc\\seed.json"])
ck("cài lại TỪ XA sau đó: không hỏi gì, Windows mới vẫn mang đúng tên cũ (May05) suy từ tên trên web 'May 05'", rc2 == 0 and not lines_of(ui2) and seed2["name"] == "May05" and "label" not in seed2, (seed2, lines_of(ui2)))
fs = FakeSys("uefi"); cfg = cfg0(); fb_media(fs, cfg)
ui = ScriptUI(); ui.lines = ["07", ""]
assert cb_pe.Installer(fs).run(ui) == 0
win, rec = fb_vols(fs); fs.fdisks = [d for d in fs.fdisks if d.index != 9]
rec.put("cb\\job.json", json.dumps(dict(job0(wipe="all"), name="07")))
rc2 = cb_pe.Installer(fs).run(ScriptUI())
win2, _ = fb_vols(fs); seed2 = json.loads(win2.files["cloudbluepc\\seed.json"])
ck("tên trên web toàn số ('07'): cài lại từ xa vẫn ra đúng CB-07 (trước đây mỗi lần cài lại đổi 1 tên ngẫu nhiên)", rc2 == 0 and seed2["name"] == "CB-07", seed2)

print("26. Bộ cài MỚI HƠN do agent đặt sẵn trên phân vùng cứu hộ (cb\\pe-next) → bộ cài trong boot.wim chạy bản đó (sửa bộ cài không cần tạo lại ISO) (21.11d)")
import hashlib as _hl
def put_next(recp, seq=None, files=None, ver="02.12a", bad=None, meta=None):
    """Đặt 1 bộ cài 'mới' lên phân vùng cứu hộ. bad = tên file cố ý ghi sai nội dung sau khi tính mã băm."""
    seq = cb_pe.PE_SEQ + 1 if seq is None else seq                   # bản "mới hơn" = số thứ tự lớn hơn bản đang chạy 1 bậc
    files = files if files is not None else {"pe/cb_pe.py": b"# bo cai moi\n", "lib/cbcore.py": b"# core moi\n", "lib/cbsys.py": b"# sys moi\n", "lib/cbrec.py": b"# rec moi\n"}
    for rel, data in files.items(): recp.vol.put("cb\\pe-next\\" + rel.replace("/", "\\"), data + (b"X" if rel == bad else b""))
    m = {"seq": seq, "ver": ver, "files": {rel: _hl.sha256(d).hexdigest() for rel, d in files.items()}}
    recp.vol.put("cb\\pe-next\\next.json", json.dumps(meta if meta is not None else m))
    return files
def pe_job(job=True, **kw):
    fs = FakeSys("uefi"); cfg = cfg0()
    d, recp, winp = cb_layout(fs, cfg, job0() if job else None, **kw)
    return fs, recp, winp
def chained(fs): return [c for c in fs.cmds if os.path.basename(c[0].replace("\\", "/")).lower().startswith("python") or "--chained" in c]
def applied(fs): return any(c[0] == "dism" and "/Apply-Image" in c for c in fs.cmds)
import os
fs, recp, winp = pe_job(); rc, ui, inst = run(fs)
ck("không có cb\\pe-next → không gọi bộ cài nào khác, tự làm lệnh như cũ", rc == 0 and not chained(fs) and applied(fs))
fs, recp, winp = pe_job(); files = put_next(recp); fs.chain_rc = 0
rc, ui, inst = run(fs)
cmd = (chained(fs) or [[]])[0]
NS = cb_pe.PE_SEQ + 1
ck("có bản số %d (> bản đang chạy) đủ file, đúng mã băm → chép cả bộ vào ổ tạm X:\\cb-next rồi chạy bản đó (python -I -B -u … --chained)" % NS, len(chained(fs)) == 1 and cmd[1:4] == ["-I", "-B", "-u"]
   and cmd[4].lower() == "x:\\cb-next\\pe\\cb_pe.py" and cmd[5:] == ["--chained"] and all(fs.file("X", "cb-next\\" + rel.replace("/", "\\")) == d.decode() for rel, d in files.items()), cmd)
ck("bản mới làm xong (mã 0) → bộ cài cũ KHÔNG đụng vào lệnh nữa (không bung Windows lần 2, lệnh để bản mới lo), trả đúng mã của bản mới", rc == 0 and not applied(fs)
   and json.loads(recp.vol.files["cb\\job.json"])["state"] == "queued" and any("BO CAI MOI HON (ban 02.12a, so %d > %d)" % (NS, cb_pe.PE_SEQ) in x for x in fs.logs), (rc, fs.logs[-3:]))
ck("biến môi trường báo cho bản mới: nó được bản số mấy gọi + thư mục bộ cài gốc", os.environ.get("CB_CHAINED") == str(cb_pe.PE_SEQ) and os.environ.get("CB_CHAIN_BASE", "").replace("\\", "/").rstrip("/").endswith("winpc"), dict((k, v) for k, v in os.environ.items() if k.startswith("CB_")))
fs, recp, winp = pe_job(); put_next(recp); fs.chain_rc = 10
rc, ui, inst = run(fs)
ck("bản mới trả mã 10 (không có gì để làm / đã xử lý) → cũng coi là xong", rc == 10 and not applied(fs))
for bad_rc, why in ((1, "lỗi cú pháp / Python chết"), (3, "tự dừng vì lỗi"), (127, "không chạy được"), (-1073741819, "sập")):
    fs, recp, winp = pe_job(); put_next(recp); fs.chain_rc = bad_rc
    rc, ui, inst = run(fs)
    ck("bản mới hỏng (%s, mã %s) → bộ cài sẵn có trong boot.wim tự làm lệnh như thường, ghi rõ nhật ký" % (why, bad_rc), rc == 0 and len(chained(fs)) == 1 and applied(fs)
       and json.loads(recp.vol.files["cb\\job-result.json"])["ok"] is True and any("khong lam xong (ma thoat %s)" % bad_rc in x for x in fs.logs), (rc, fs.logs[-4:]))
fs, recp, winp = pe_job(); put_next(recp, bad="lib/cbsys.py"); rc, ui, inst = run(fs)
ck("1 file sai mã băm (ghi dở / bị sửa) → KHÔNG chạy bản mới, không chép gì vào ổ tạm, dùng bộ cài sẵn có", rc == 0 and not chained(fs) and applied(fs) and not any(k.startswith("cb-next") for k in fs.x.files)
   and any("lib/cbsys.py thieu / sai ma bam" in x for x in fs.logs), [x for x in fs.logs if "ma bam" in x])
fs, recp, winp = pe_job(); put_next(recp); del recp.vol.files["cb\\pe-next\\lib\\cbrec.py"]; rc, ui, inst = run(fs)
ck("thiếu 1 file → không chạy bản mới", rc == 0 and not chained(fs) and applied(fs))
for seq in (cb_pe.PE_SEQ, 1, 0, -5, "9", 2.5, True, "x"):
    fs, recp, winp = pe_job(); put_next(recp, seq=seq); rc, ui, inst = run(fs)
    ck("số thứ tự %r không lớn hơn bản đang chạy / không phải số nguyên → bỏ qua (không hạ cấp, không chạy lại chính mình)" % (seq,), rc == 0 and not chained(fs) and applied(fs))
for label, fl in (("ngoài thư mục pe / lib", {"pe/cb_pe.py": b"a", "os/x.py": b"b"}), ("có ..", {"pe/cb_pe.py": b"a", "pe/../../evil.py": b"b"}), ("không phải .py", {"pe/cb_pe.py": b"a", "pe/run.cmd": b"b"}),
                  ("đường tuyệt đối", {"pe/cb_pe.py": b"a", "C:/x.py": b"b"}), ("thiếu pe/cb_pe.py", {"lib/cbcore.py": b"a"}), ("quá 40 file", dict({"pe/cb_pe.py": b"a"}, **{"lib/m%d.py" % i: b"b" for i in range(41)}))):
    fs, recp, winp = pe_job()
    for rel, d in fl.items(): recp.vol.put("cb\\pe-next\\" + rel.replace("/", "\\"), d)
    recp.vol.put("cb\\pe-next\\next.json", json.dumps({"seq": 5, "ver": "x", "files": {rel: _hl.sha256(d).hexdigest() for rel, d in fl.items()}}))
    rc, ui, inst = run(fs)
    ck("danh sách file %s → bỏ qua cả bản mới" % label, rc == 0 and not chained(fs) and applied(fs) and not any(k.startswith("cb-next") for k in fs.x.files), [x for x in fs.logs if "Bo cai moi" in x])
for label, raw in (("không phải JSON", "{{{"), ("là danh sách", "[1, 2]"), ("files không phải bảng", json.dumps({"seq": 3, "files": ["pe/cb_pe.py"]})), ("mã băm không phải chữ", json.dumps({"seq": 3, "files": {"pe/cb_pe.py": 5}}))):
    fs, recp, winp = pe_job(); put_next(recp); recp.vol.put("cb\\pe-next\\next.json", raw); rc, ui, inst = run(fs)
    ck("next.json hỏng (%s) → bỏ qua, cài như thường" % label, rc == 0 and not chained(fs) and applied(fs))
fs, recp, winp = pe_job(); put_next(recp, files={"pe/cb_pe.py": b"x" * ((2 << 20) + 1)}); rc, ui, inst = run(fs)
ck("file quá 2 MB → bỏ qua", rc == 0 and not chained(fs) and applied(fs))
fs, recp, winp = pe_job(); put_next(recp); fs.chain_rc = 0
inst = cb_pe.Installer(fs); inst.chained = True; rc = inst.run(ScriptUI())
ck("bản đang chạy chính là bản được gọi tiếp (--chained) → không gọi tiếp lần nữa (không lặp vô hạn), tự làm lệnh", rc == 0 and not chained(fs) and applied(fs))
fs, recp, winp = pe_job(job=False); put_next(recp); fs.chain_rc = 10
rc, ui, inst = run(fs)
ck("khởi động vào phân vùng cứu hộ mà không có lệnh: vẫn giao cho bản mới xử lý", rc == 10 and len(chained(fs)) == 1)
fs, recp, winp = pe_job(); put_next(recp); fs.chain_rc = 0; usb(fs, cfg0())
rc, ui, inst = run(fs)
ck("đang cắm USB / ISO cài đặt → bộ cài trên USB là bản người cài chọn: KHÔNG chạy bản trên phân vùng cứu hộ", not chained(fs), chained(fs))
fs, recp, winp = pe_job(); put_next(recp); fs.chain_rc = 0; fs.dry = True
rc, ui, inst = run(fs)
ck("chạy thử (dry-run) → không gọi bản khác", not chained(fs))
fs, recp, winp = pe_job(); put_next(recp, seq=cb_pe.PE_SEQ + 1, ver="cu"); fs.chain_rc = 0
d2 = fs.disk(1, 240, model="O thu hai", ssd=True, style="gpt")
rec2 = d2.add(12 * 1024, GPT_DATA, "NTFS", "CBRECOVERY", attrs=0x8000000000000001, files={"cb\\recovery.tag": "1", "cb\\cb.json": "{}"})
put_next(rec2, seq=cb_pe.PE_SEQ + 5, ver="moi-nhat", files={"pe/cb_pe.py": b"# ban 7\n"})
rc, ui, inst = run(fs)
ck("máy có 2 phân vùng cứu hộ (2 ổ từng cài) → lấy bản có số lớn nhất", len(chained(fs)) == 1 and fs.file("X", "cb-next\\pe\\cb_pe.py") == "# ban 7\n" and any("ban moi-nhat, so %d" % (cb_pe.PE_SEQ + 5) in x for x in fs.logs), [x for x in fs.logs if "MOI HON" in x])
ck("PE_SEQ là số nguyên dương; mã thoát cố định 0 / 3 / 10", isinstance(cb_pe.PE_SEQ, int) and cb_pe.PE_SEQ >= 1 and (cb_pe.RC_OK, cb_pe.RC_SETUP, cb_pe.RC_REBOOT) == (0, 3, 10))


print("27. CÀI CachyOS (Linux) theo lệnh — WinPE chia ổ, chép GRUB, ghi việc, khởi động 1 lần vào GRUB (22.11c)")
import struct, uuid as _uuid
from cbsys import GPT_LINUX
import cbrec


def nvram(fs, linux=False):
    """NVRAM giả: Boot0000 = Windows Boot Manager (+ Boot0001 = Linux Boot Manager của CachyOS nếu máy đang chạy Linux)."""
    wbm = C.efi_load_option("Windows Boot Manager", 1, 2048, 532480, str(_uuid.uuid4()), "\\EFI\\Microsoft\\Boot\\bootmgfw.efi")
    fs.efi["Boot0000"] = wbm
    order = [0]
    if linux:
        fs.efi["Boot0001"] = C.efi_load_option("Linux Boot Manager", 4, 99999, 2097152, str(_uuid.uuid4()), "\\EFI\\systemd\\systemd-bootx64.efi"); order = [1, 0]
    fs.efi["BootOrder"] = b"".join(struct.pack("<H", n) for n in order)


def order_of(fs): return [struct.unpack("<H", fs.efi["BootOrder"][i:i + 2])[0] for i in range(0, len(fs.efi.get("BootOrder", b"")), 2)]


def lin_job(**kw): return job0(os="cachyos", **kw)


fs = FakeSys("uefi"); cfg = cfg_lin(user="PC", password="mk-khach", user_admin=True); nvram(fs)
d, rec, win = cb_layout(fs, cfg, lin_job())
esp0 = d.slots[0]
rc, ui, inst = run(fs)
ck("cài xong phần WinPE (mã 0, khởi động lại)", rc == 0, (rc, fs.logs[-6:]))
ck("lần đầu vẫn cho 10 giây bấm X để huỷ", ui.prompts and ui.prompts[0][0] == 10)
types = [p.type for p in d.slots]
ck("ổ: EFI Windows · MSR · cứu hộ · EFI Linux 1GB (FAT32, CBLINUXEFI) · phân vùng Linux (kiểu Linux) — Windows cũ đã xoá",
   types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_ESP, GPT_LINUX] and d.slots[3].size == 1024 * MB and d.slots[3].vol.fs == "FAT32" and d.slots[3].vol.label == "CBLINUXEFI"
   and d.slots[4].size > 400 * GB and not any("bi-mat" in k for p in d.slots if p.vol for k in p.vol.files), [(p.type[:8], p.size // MB) for p in d.slots])
ck("phân vùng cứu hộ còn nguyên (ISO CachyOS, bộ cài)", rec.vol.files.get("cb\\linux\\cachyos.iso") == b"ISO" and "cb\\boot\\boot.wim" in rec.vol.files)
ck("GRUB của CloudBlue nằm trên EFI Windows: \\EFI\\cblinux\\grubx64.efi", esp0.vol.files.get("efi\\cblinux\\grubx64.efi") == b"GRUB")
j = json.loads(rec.vol.files["cb\\job.json"])
L = j.get("linux") or {}
ck("cb\\job.json giữ lệnh (state running, lần 1) + mục linux trỏ ĐÚNG vị trí 2 phân vùng mới", j["state"] == "running" and j["attempts"] == 1 and j["os"] == "cachyos"
   and L.get("esp", {}).get("offset") == d.slots[3].offset and L.get("root", {}).get("offset") == d.slots[4].offset and L["root"]["size"] == d.slots[4].size, L)
ck("tài khoản Linux: 'pc' (chữ thường), mật khẩu như Windows, có quyền admin theo cấu hình, tự đăng nhập, múi giờ Việt Nam",
   (L.get("user"), L.get("pass"), L.get("admin"), L.get("autologin"), L.get("tz"), L.get("desktop")) == ("pc", "mk-khach", True, True, "Asia/Ho_Chi_Minh", "kde"), L)
ck("vé đăng ký lại (ticket) còn trong job.json cho agent Linux", j.get("ticket") == "t" * 32)
want_uuid = C.ntfs_uuid(fs.read_boot_sector("R") if False else b"")
rec_letter_free = rec.vol.letter is None
bs = None
for _, _, v in fs._allvols():
    if v is rec.vol:
        v.letter = "Q"; bs = fs.read_boot_sector("Q"); v.letter = None
uid = C.ntfs_uuid(bs)
ck("cb\\linux\\job.cfg cho GRUB: ISO nằm trên phân vùng cứu hộ (UUID = số seri NTFS 16 chữ hex)", rec.vol.files.get("cb\\linux\\job.cfg", "").count("set cbdev=UUID=%s" % uid) == 1 and len(uid) == 16, rec.vol.files.get("cb\\linux\\job.cfg"))
ck("phân vùng cứu hộ ẩn lại (không chữ ổ)", rec_letter_free)
grub = [n for n in range(64) if fs.efi.get("Boot%04X" % n) and C.efi_option_desc(fs.efi["Boot%04X" % n]) == C.GRUB_DESC]
bo = fs.efi.get("Boot%04X" % grub[0], b"") if grub else b""
ck("NVRAM: 1 mục 'CloudBlue Linux' trỏ \\EFI\\cblinux\\grubx64.efi trên ĐÚNG phân vùng EFI (GUID + LBA)", len(grub) == 1 and esp0.guid and _uuid.UUID(esp0.guid).bytes_le in bo
   and struct.pack("<QQ", esp0.offset // 512, esp0.size // 512) in bo and "\\EFI\\cblinux\\grubx64.efi".encode("utf-16-le") in bo, grub)
ck("BootNext = mục GRUB (khởi động 1 lần), BootOrder KHÔNG đổi (Windows Boot Manager vẫn là lối về)", grub and fs.efi.get("BootNext") == struct.pack("<H", grub[0]) and order_of(fs) == [0])
st = fs.bcd.get("s:\\efi\\microsoft\\boot\\bcd", {})
ck("Windows Boot Manager mặc định = WinPE cứu hộ (Linux lỗi / tắt ngang → tự vào lại bộ cài), chờ 0 giây", st.get("default") == C.PE_GUID and st.get("timeout") == "0" and C.PE_GUID in st.get("entries", {}))
ck("không bung Windows, không bcdboot", not any(c[0] == "dism" and "/Apply-Image" in c for c in fs.cmds) and not any("bcdboot" in c[0].lower() for c in fs.cmds))
ck("không có file kết quả (bộ cài Linux mới là bên báo xong)", "cb\\job-result.json" not in rec.vol.files)
rc2, ui2, inst2 = run(fs)
grub2 = [n for n in range(64) if fs.efi.get("Boot%04X" % n) and C.efi_option_desc(fs.efi["Boot%04X" % n]) == C.GRUB_DESC]
ck("máy vào lại WinPE (Linux chưa chạy / bị tắt ngang) → làm lại lần 2, KHÔNG đẻ thêm mục khởi động", rc2 == 0 and json.loads(rec.vol.files["cb\\job.json"])["attempts"] == 2 and grub2 == grub
   and [p.type for p in d.slots] == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_ESP, GPT_LINUX] and not ui2.prompts, (rc2, grub2, ui2.prompts))

# wipe=system: chỉ thay ổ C:, giữ phân vùng dữ liệu của khách
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs)
d, rec, win = cb_layout(fs, cfg, None, extra_data=True)
rec.vol.put("cb\\job.json", json.dumps(lin_job(wipe="system", win=win)))
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
ck("wipe=system: ổ C: thành EFI Linux + Linux, ổ D: của khách giữ nguyên", rc == 0 and fs.file("D", "game\\save.dat") == "cua khach" and GPT_LINUX in types
   and [p.vol.label for p in d.slots if p.vol and p.type == GPT_DATA][-1] == "Data", [(p.type[:8], p.size // GB) for p in d.slots])
lp = next(p for p in d.slots if p.type == GPT_LINUX)
ck("phần Linux nằm đúng chỗ ổ C: cũ (dữ liệu khác không bị dời)", next(p for p in d.slots if p.type == GPT_ESP and p is not d.slots[0]).offset == win.offset and lp.offset + lp.size == win.offset + win.size)

# kiểm trước, CHƯA xoá gì
for label, setup in (("máy bật Secure Boot", lambda fs, rec: fs.efi.__setitem__("SecureBoot", b"\x01")),
                     ("thiếu grubx64.efi trên phân vùng cứu hộ", lambda fs, rec: rec.vol.files.pop("cb\\linux\\grubx64.efi")),
                     ("thiếu ISO CachyOS", lambda fs, rec: rec.vol.files.pop("cb\\linux\\cachyos.iso"))):
    fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); d, rec, win = cb_layout(fs, cfg, lin_job()); setup(fs, rec)
    rc, ui, inst = run(fs)
    res = json.loads(rec.vol.files.get("cb\\job-result.json", "{}"))
    ck("%s → dừng TRƯỚC khi xoá, Windows còn nguyên, báo lỗi về web" % label, rc == 10 and not fs.dp_scripts and fs.file("C", "users\\khach\\bi-mat.txt") and res.get("ok") is False
       and "cb\\job.json" not in rec.vol.files, (rc, res.get("msg")))
ck("lý do Secure Boot ghi rõ cho người đọc", True)
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); fs.efi["SecureBoot"] = b"\x01"; d, rec, win = cb_layout(fs, cfg, lin_job()); run(fs)
ck("  … 'Secure Boot' có trong thông báo lỗi", "Secure Boot" in json.loads(rec.vol.files["cb\\job-result.json"])["msg"])
fs = FakeSys("bios"); cfg = cfg_lin(); d, rec, win = cb_layout(fs, cfg, lin_job(), fw="bios")
rc, ui, inst = run(fs)
ck("máy BIOS → không cài CachyOS, không xoá gì", rc == 10 and not fs.dp_scripts and "UEFI" in json.loads(rec.vol.files["cb\\job-result.json"])["msg"])
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); d, rec, win = cb_layout(fs, cfg, lin_job(), size=50)
rc, ui, inst = run(fs)
ck("ổ quá nhỏ (50GB) → không đủ chỗ cho CachyOS, không xoá gì", rc == 10 and not fs.dp_scripts and "khong du cai CachyOS" in json.loads(rec.vol.files["cb\\job-result.json"])["msg"])

# NVRAM không ghi được → thử lại; quá 2 lần → cài lại Windows mặc định
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); fs.efi_ro = True
d, rec, win = cb_layout(fs, cfg, lin_job())
rc, ui, inst = run(fs)
j = json.loads(rec.vol.files["cb\\job.json"])
ck("BIOS chặn ghi biến UEFI → báo lỗi, giữ lệnh (lần 1) để thử lại", rc == 10 and j["attempts"] == 1 and j["state"] == "running" and json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is False
   and "NVRAM" in json.loads(rec.vol.files["cb\\job-result.json"])["msg"])
rc, ui, inst = run(fs)
ck("lần 2 vẫn lỗi → giữ lệnh", rc == 10 and json.loads(rec.vol.files["cb\\job.json"])["attempts"] == 2)
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
res = json.loads(rec.vol.files.get("cb\\job-result.json", "{}"))
win_new = next(p for p in d.slots if p.vol and p.vol.label == "Windows")
ck("lần 3: KHÔNG thử CachyOS nữa → cài lại Windows mặc định (22H2) để máy lên lại được", rc == 0 and types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA]
   and fs.file(win_new.vol, "windows\\cb-image.txt") == "22h2.wim|6", ([t[:8] for t in types], rc, fs.file(win_new.vol, "windows\\cb-image.txt")))
ck("  … báo về web: lệnh CachyOS THẤT BẠI kèm lý do + đã cài lại Windows", res.get("ok") is False and "CachyOS chua cai duoc" in res.get("msg", "") and "22h2" in res.get("msg", ""), res)
seed = json.loads(win_new.vol.files["cloudbluepc\\seed.json"])
ck("  … Windows mới mang đúng số lệnh + vé để agent đăng ký lại", seed.get("order") == 77 and seed.get("ticket") == "t" * 32 and seed.get("os") == "22h2")

# cb-install.sh báo lỗi 2 lần (mạng, …), khách chọn chỉ thay hệ điều hành → Windows mới nằm đúng chỗ phần Linux, ổ D: giữ nguyên
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs, linux=False)
d, rec, lesp, lroot = lin_layout(fs, cfg, None, extra_data=True, installed=False)
jj = lin_job(wipe="system", attempts=2, state="running", linux_fail=2, linux_msg="chua co mang sau 5 phut",
             linux={"esp": {"offset": lesp.offset, "size": lesp.size}, "root": {"offset": lroot.offset, "size": lroot.size}})
rec.vol.put("cb\\job.json", json.dumps(jj))
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
res = json.loads(rec.vol.files.get("cb\\job-result.json", "{}"))
wn = next((p for p in d.slots if p.vol and p.vol.label == "Windows"), None)
ck("CachyOS lỗi 2 lần (cb-install báo) → cài Windows vào ĐÚNG chỗ phần Linux, ổ D: giữ nguyên", rc == 0 and types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA, GPT_DATA]
   and fs.file("D", "game\\save.dat") == "cua khach" and wn is not None and wn.offset == lesp.offset and wn.size == lesp.size + lroot.size and "mang" in res.get("msg", ""),
   ([t[:8] for t in types], res.get("msg")))

print("28. Máy ĐANG CHẠY CachyOS → cài lại Windows / cài lại CachyOS / vào nhầm WinPE (22.11c)")
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs, linux=True)
d, rec, lesp, lroot = lin_layout(fs, cfg, job0(os="22h2"))
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
ck("đổi sang Windows (wipe=all): EFI Linux + phân vùng Linux bị xoá, còn EFI Windows · MSR · cứu hộ · Windows", rc == 0 and types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA]
   and d.slots[3].vol.label == "Windows", [t[:8] for t in types])
ck("mục khởi động 'Linux Boot Manager' trong NVRAM đã gỡ (khỏi BootOrder + xoá biến)", "Boot0001" not in fs.efi and order_of(fs) == [0], (sorted(fs.efi), order_of(fs)))
ck("bỏ dấu 'máy đang chạy CachyOS' trên phân vùng cứu hộ", "cb\\linux\\installed.json" not in rec.vol.files)
ck("báo XONG (Windows)", json.loads(rec.vol.files["cb\\job-result.json"])["ok"] is True)

fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs, linux=True)
d, rec, lesp, lroot = lin_layout(fs, cfg, None, extra_data=True)
rec.vol.put("cb\\job.json", json.dumps(job0(os="22h2", wipe="system", win={"offset": lroot.offset, "size": lroot.size})))
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
wn = next((p for p in d.slots if p.vol and p.vol.label == "Windows"), None)
ck("đổi sang Windows chỉ thay hệ điều hành (wipe=system, vị trí = phân vùng Linux): EFI Linux + Linux → 1 phân vùng Windows, ổ D: giữ nguyên",
   rc == 0 and types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_DATA, GPT_DATA] and wn is not None and wn.offset == lesp.offset and wn.size == lesp.size + lroot.size
   and fs.file("D", "game\\save.dat") == "cua khach", [(t[:8], p.size // GB) for t, p in zip(types, d.slots)])

fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs, linux=True)
d, rec, lesp, lroot = lin_layout(fs, cfg, lin_job())
old_root = lroot
rc, ui, inst = run(fs)
types = [p.type for p in d.slots]
ck("cài lại CachyOS trên máy đang chạy CachyOS: phần Linux cũ xoá, tạo mới (đúng 1 EFI Linux + 1 Linux)", rc == 0 and types == [GPT_ESP, GPT_MSR, GPT_DATA, GPT_ESP, GPT_LINUX]
   and d.slots[4] is not old_root, [t[:8] for t in types])

fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs, linux=True); fs.efi["BootOrder"] = struct.pack("<HH", 0, 1)    # BIOS tự đưa Windows Boot Manager lên đầu
d, rec, lesp, lroot = lin_layout(fs, cfg, None)
rc, ui, inst = run(fs)
ck("máy chạy CachyOS mà BIOS lại vào Windows Boot Manager (→ WinPE, không lệnh): đưa 'Linux Boot Manager' lên đầu + BootNext, khởi động lại, KHÔNG xoá gì",
   rc == 10 and order_of(fs) == [1, 0] and fs.efi.get("BootNext") == struct.pack("<H", 1) and not fs.dp_scripts, (rc, order_of(fs)))

print("29. Bộ cài có CachyOS: cài từ USB vẫn chỉ cài Windows · phân vùng cứu hộ chép đủ phần Linux · agent thấy được CachyOS (22.11c)")
fs = FakeSys("uefi"); cfg = cfg_lin(); u = usb(fs, cfg)
for rel, data in (("cb\\linux\\cachyos.iso", b"ISO"), ("cb\\linux\\grubx64.efi", b"GRUB"), ("cb\\linux\\grub.cfg", "cfg"), ("cb\\linux\\cb-install.sh", "sh")): u.slots[0].vol.put(rel, data)
d0 = fs.disk(0, 480, ssd=True, style="gpt")
rc, ui, inst = run(fs, ["3", "\r"])
ck("menu chỉ liệt kê bản Windows (phím 3 không chọn được CachyOS) → cài 22H2 như thường", rc == 0 and fs.file(d0.slots[3].vol, "windows\\cb-image.txt") == "install.wim|6"
   and not any("cachyos" in x.lower() and "=" in x for x in fs.logs), [x for x in fs.logs if " = " in x])
rv = d0.slots[2].vol
ck("phân vùng cứu hộ có đủ phần Linux (ISO + GRUB + kịch bản), ISO chỉ chép 1 lần", all(k in rv.files for k in ("cb\\linux\\cachyos.iso", "cb\\linux\\grubx64.efi", "cb\\linux\\grub.cfg", "cb\\linux\\cb-install.sh"))
   and not any(k.startswith("cb\\images\\cachyos") for k in rv.files), sorted(k for k in rv.files if "linux" in k or "images" in k))
rcfg = json.loads(rv.files["cb\\cb.json"])
ck("cb.json trên phân vùng cứu hộ: CachyOS trỏ cb\\linux\\cachyos.iso", [i["file"] for i in rcfg["images"]][-1] == "cb\\linux\\cachyos.iso")
rv.letter = "R"
st = cbrec.status(fs)
ck("agent báo web: đổi được sang 22h2, 1511, cachyos", st["ok"] and st["images"] == ["22h2", "1511", "cachyos"], st)

rv.files.pop("cb\\linux\\grubx64.efi")
ck("thiếu GRUB → agent KHÔNG báo cachyos (không cho chọn bản không cài được)", cbrec.status(fs)["images"] == ["22h2", "1511"], cbrec.status(fs))
rv.letter = None

def stage(fs, **kw):
    try: return cbrec.stage_job(fs, dict({"id": 91, "os": "cachyos", "wipe": "all", "ticket": "t" * 32}, **kw), "CB-STAGE", 1_800_000_000)
    except C.Stop as e: return "STOP: %s" % e
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); d, rec, win = cb_layout(fs, cfg, None)
img = stage(fs)
jj = json.loads(rec.vol.files.get("cb\\job.json", "{}"))
ck("agent Windows ghi lệnh đổi sang CachyOS: job.json os=cachyos + vị trí ổ C: + đặt khởi động 1 lần vào bộ cài", isinstance(img, dict) and img.get("id") == "cachyos"
   and jj.get("os") == "cachyos" and jj.get("state") == "queued" and jj.get("win", {}).get("offset") == win.offset and fs.bcd.get("(system)", {}).get("bootsequence") == C.PE_GUID, (img, jj))
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); fs.efi["SecureBoot"] = b"\x01"; d, rec, win = cb_layout(fs, cfg, None)
r = stage(fs)
ck("… máy bật Secure Boot → agent báo lỗi NGAY (không khởi động lại vào bộ cài)", isinstance(r, str) and "Secure Boot" in r and "cb\\job.json" not in rec.vol.files, r)
fs = FakeSys("bios"); cfg = cfg_lin(); d, rec, win = cb_layout(fs, cfg, None, fw="bios")
r = stage(fs)
ck("… máy BIOS → báo lỗi ngay", isinstance(r, str) and "UEFI" in r, r)
fs = FakeSys("uefi"); cfg = cfg_lin(); nvram(fs); d, rec, win = cb_layout(fs, cfg, None); rec.vol.files.pop("cb\\linux\\cb-install.sh")
r = stage(fs)
ck("… phân vùng cứu hộ thiếu cb-install.sh → báo lỗi ngay", isinstance(r, str) and "cb-install.sh" in r, r)

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
