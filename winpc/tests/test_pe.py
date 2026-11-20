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
_pro = lambda ver: {"edition": "Professional", "version": ver}
ck("mặc định (auto): bản 1511 Pro → điền khoá cài đặt chung (màn hình cài lần đầu của 1511 dừng hỏi key)", "<ProductKey>VK7JG-NPHTM-C97JM-9MPGT-3V66T</ProductKey>" in C.make_unattend(TPL, _pro("10.0.10586.0"), {}, "x1"))
ck("mặc định (auto): bản 22H2 → không điền khoá", "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.19045.2965"), {}, "x1") and "<ProductKey>" not in C.make_unattend(TPL, _pro(""), {}, "x1"))
ck("auto: 1511 nhưng phiên bản lạ → không điền", "<ProductKey>" not in C.make_unattend(TPL, {"edition": "ProfessionalN", "version": "10.0.10586.0"}, {"generic_key": "auto"}, "x1"))
ck("tắt (off / false) → 1511 cũng không điền", "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.10586.0"), {"generic_key": "off"}, "x1") and "<ProductKey>" not in C.make_unattend(TPL, _pro("10.0.10586.0"), {"generic_key": False}, "x1"))
ck("bật (on) → 22H2 cũng điền; Home dùng đúng khoá Home", "VK7JG" in C.make_unattend(TPL, _pro("10.0.19045.1"), {"generic_key": "on"}, "x1") and "<ProductKey>YTMG3-N6DKC-DKB77-7M9GH-8HVX7</ProductKey>" in C.make_unattend(TPL, {"edition": "Core", "version": "10.0.10586.0"}, {}, "x1"))
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
   and next(x for x in dc if x.startswith("/Driver:")).lower().endswith("\\cb\\drivers"), dc)
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
ck("cài lại từ phân vùng cứu hộ: cũng nạp driver nằm trên phân vùng cứu hộ", rc == 0 and bool(dc) and next(x for x in dc if x.startswith("/Driver:")).lower().endswith("\\cb\\drivers") and "/Recurse" in dc, (rc, dc))

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
