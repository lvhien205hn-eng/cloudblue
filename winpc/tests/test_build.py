# -*- coding: utf-8 -*-
"""Thử phần sắp xếp bộ cài (cb_build.py). Chạy: python3 tests/test_build.py"""
import hashlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "lib"))
import cb_build as B                                  # noqa: E402
import cbcore as C                                    # noqa: E402

OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", extra)


def w(p, data=b"x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data if isinstance(data, bytes) else data.encode())


tmp = tempfile.mkdtemp()
out, tool, py, iso2 = (os.path.join(tmp, n) for n in ("iso", "tool", "py", "iso1511"))
shutil.copytree(REPO, tool, ignore=shutil.ignore_patterns("tests", "__pycache__", "docs"))
w(os.path.join(tool, "os", "cacert.pem"), "-----BEGIN CERTIFICATE-----")
for f in ("python.exe", "pythonw.exe", "python312.dll", "python312.zip", "python312._pth"): w(os.path.join(py, f), f)
w(os.path.join(out, "sources", "boot.wim"), b"B" * 1000); w(os.path.join(out, "boot", "boot.sdi")); w(os.path.join(out, "sources", "install.wim"), b"W" * 5000)
w(os.path.join(out, "sources", "lang.ini"), "[Available UI Languages]\r\nen-US = 3\r\n\r\n[Fallback Languages]\r\nen-US = en-us\r\n")
w(os.path.join(out, "setup.exe")); w(os.path.join(iso2, "sources", "install.esd"), b"E" * 3000)
KEY = "cbpc_" + "c" * 40
P = {"out": out, "tool": tool, "py": py, "user": "PC", "password": "", "sb_url": "https://abc.supabase.co/", "sb_key": "sb_publishable_xyz", "enroll_key": KEY,
     "images": [{"src": os.path.join(iso2, "sources", "install.esd"), "base": False, "index": 1, "name": "Windows 10 Pro", "edition": "Professional", "version": "10.0.10586.0", "lang": "en-US", "arch": 9},
                {"src": os.path.join(out, "sources", "install.wim"), "base": True, "index": 6, "name": "Windows 10 Pro", "edition": "Professional", "version": "10.0.19045.3803", "lang": "en-US", "arch": 9}]}

print("1. Sắp xếp bộ cài 2 bản (22H2 làm gốc + 1511)")
cfg = B.layout(json.loads(json.dumps(P)))
ck("đặt tên bản theo số build + bản mới nhất làm mặc định", [i["id"] for i in cfg["images"]] == ["1511", "22h2"] and cfg["default"] == "22h2")
ck("bản gốc ở sources\\install.wim, bản phụ chép vào cb\\images\\1511.esd", cfg["images"][1]["file"] == "sources\\install.wim" and cfg["images"][0]["file"] == "cb\\images\\1511.esd"
   and open(os.path.join(out, "cb", "images", "1511.esd"), "rb").read() == b"E" * 3000 and cfg["images"][0]["bytes"] == 3000)
ck("đủ phần mềm trong \\cb + CAI-DAT.cmd ở gốc + Python nhúng + chứng chỉ", all(os.path.isfile(os.path.join(out, *x.split("/"))) for x in
   ("cb/lib/cbsys.py", "cb/lib/cbcore.py", "cb/lib/cbrec.py", "cb/pe/cb_pe.py", "cb/pe/start.cmd", "cb/os/cb_provision.py", "cb/os/provision.cmd", "cb/os/cb_stage.py",
    "cb/os/unattend.tpl.xml", "cb/os/cacert.pem", "cb/agent/pcagent.py", "cb/agent/watch.cmd", "cb/agent/cbpc.cmd", "cb/py/python.exe", "cb/py/pythonw.exe", "CAI-DAT.cmd",
    "cb/media.tag", "cb/drivers/doc-toi.txt", "cb/os/firstboot.d/doc-toi.txt")))
c = json.load(open(os.path.join(out, "cb", "cb.json")))
ck("cb.json: địa chỉ máy chủ + khoá CÔNG KHAI, KHÔNG chứa mã đăng ký", c["sb_url"] == "https://abc.supabase.co" and c["sb_key"] == "sb_publishable_xyz" and KEY not in json.dumps(c) and c["generic_key"] == "auto" and c["update_base"].startswith("https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/"))
ck("mã đăng ký nằm riêng ở cb\\enroll.key", open(os.path.join(out, "cb", "enroll.key")).read().strip() == KEY)
au = open(os.path.join(out, "autounattend.xml"), encoding="utf-8").read()
r = subprocess.run(["xmllint", "--noout", os.path.join(out, "autounattend.xml")], capture_output=True, text=True)
ck("autounattend.xml hợp lệ: 3 pha (windowsPE có móc gọi bộ cài + ngôn ngữ en-US), tên máy '*'", r.returncode == 0 and au.count("<settings pass=") == 3 and 'pass="windowsPE"' in au
   and "\\cb\\pe\\start.cmd" in au and "<UILanguage>en-US</UILanguage>" in au and "<ComputerName>*</ComputerName>" in au and "{{" not in au and "{LANG}" not in au, r.stderr)
ck("thứ tự pha: windowsPE → specialize → oobeSystem", au.index('pass="windowsPE"') < au.index('pass="specialize"') < au.index('pass="oobeSystem"'))
oem = os.path.join(out, "sources", "$OEM$", "$1", "CloudBluePC")
ck("$OEM$: cài bằng bộ cài Windows THƯỜNG vẫn có agent + mã đăng ký", os.path.isfile(os.path.join(oem, "agent", "pcagent.py")) and os.path.isfile(os.path.join(oem, "py", "python.exe"))
   and json.load(open(os.path.join(oem, "seed.json"))) == {"from": "setup", "pe": B.BUILD_VER, "enroll_key": KEY} and KEY not in open(os.path.join(oem, "cb.json")).read())
ck("kiểm cây ISO: đạt", B.check(out) == 0)
ck("mặc định (auto): chỉ bản 1511 được điền khoá cài đặt chung", [bool(C.generic_key_for(i, cfg)) for i in cfg["images"]] == [True, False])
ck("mặc định: khách dùng TÀI KHOẢN THƯỜNG (user_admin = false) — cấu hình trên phân vùng cứu hộ / máy cũng vậy", cfg["user_admin"] is False and c["user_admin"] is False
   and json.load(open(os.path.join(oem, "cb.json")))["user_admin"] is False)
cfga = B.layout(dict(json.loads(json.dumps(P)), user_admin=True, info=os.path.join(tmp, "build-info.txt")))
ck("-KhachAdmin: để khách quyền Admin, khung tóm tắt ghi rõ; giá trị lạ ('1', 1) không bật nhầm", cfga["user_admin"] is True and "quyen ADMIN" in open(os.path.join(tmp, "build-info.txt")).read()
   and all(B.layout(dict(json.loads(json.dumps(P)), user_admin=x))["user_admin"] is False for x in ("1", 1, None, "true")))
cfg = B.layout(json.loads(json.dumps(P)))
P3 = dict(json.loads(json.dumps(P)), generic_key="on", info=os.path.join(tmp, "build-info.txt"), default="1511")
cfg3 = B.layout(P3)
info = open(P3["info"], "rb").read().decode("ascii").split("\r\n")
ck("ghi file tóm tắt cho tao-iso.ps1 (ASCII): 2 dòng ANH + dòng CUU_HO + dòng KHACH, có ghi chế độ khoá", len(info) == 5 and info[0].startswith("ANH 1511 | Windows 10 Pro | ban so 1 | 10.0.10586.0") and "MAC DINH" in info[0]
   and info[0].endswith("| dien khoa cai dat chung") and info[1].startswith("ANH 22h2") and info[1].endswith("| dien khoa cai dat chung") and info[2].startswith("CUU_HO ") and "| khoa cai dat chung: on |" in info[2] and info[3].startswith("KHACH tai khoan 'PC' | tai khoan THUONG") and info[4] == "", info)
au3 = open(os.path.join(out, "autounattend.xml"), encoding="utf-8").read()
ck("autounattend.xml (bộ cài thường, người cài tự chọn phiên bản) KHÔNG BAO GIỜ kèm khoá", cfg3["generic_key"] == "on" and cfg3["default"] == "1511" and "<ProductKey>" not in au3 and "ProductKey" not in au)
ck("ảnh nền CloudBlue mặc định đi theo bộ cài (cả đường cài bằng bộ cài Windows thường)", open(os.path.join(out, "cb", "os", "wallpaper.jpg"), "rb").read() == open(os.path.join(REPO, "os", "wallpaper.jpg"), "rb").read()
   and os.path.isfile(os.path.join(oem, "os", "wallpaper.jpg")) and "anh nen: CloudBlue" in info[2], info[2])
wp = os.path.join(tmp, "anh-cua-shop.PNG"); w(wp, b"PNG-RIENG")
P4 = dict(json.loads(json.dumps(P)), wallpaper=wp, info=os.path.join(tmp, "build-info.txt"), default_index=0)
cfg4 = B.layout(P4)
info4 = open(P4["info"], "rb").read().decode("ascii").split("\r\n")
ck("ảnh nền riêng của shop (.png) thay ảnh mặc định, không để lẫn 2 file", open(os.path.join(out, "cb", "os", "wallpaper.png"), "rb").read() == b"PNG-RIENG"
   and not os.path.exists(os.path.join(out, "cb", "os", "wallpaper.jpg")) and os.path.isfile(os.path.join(oem, "os", "wallpaper.png")) and not os.path.exists(os.path.join(oem, "os", "wallpaper.jpg"))
   and "anh nen: rieng" in info4[2], info4[2])
ck("chọn bản mặc định theo số thứ tự (bản thứ 1 trong danh sách = 1511)", cfg4["default"] == "1511" and "MAC DINH" in info4[0], (cfg4["default"], info4[0]))
ck("số thứ tự -1 / ngoài khoảng / sai kiểu → bản mới nhất", all(B.layout(dict(json.loads(json.dumps(P)), default_index=x))["default"] == "22h2" for x in (-1, 5, None, "1", True)))
try: B.layout(dict(json.loads(json.dumps(P)), wallpaper=os.path.join(tmp, "anh.gif"))); _bad = False
except C.Stop: _bad = True
ck("ảnh nền sai loại file → dừng có lời nhắn", _bad)
cfg = B.layout(json.loads(json.dumps(P)))                       # trả cây về như bước 1 cho các bước sau
ck("chạy lại không có ảnh riêng → trả về ảnh CloudBlue mặc định", os.path.isfile(os.path.join(out, "cb", "os", "wallpaper.jpg")))
NV1, NV2 = "466.77-notebook-win10-64bit-international-whql.exe", "511.23-desktop-win10-win11-64bit-international-dch-whql.exe"
w(os.path.join(out, "cb", "drivers", "1511", NV1), b"N" * 5000); w(os.path.join(out, "cb", "drivers", "1511", "LAN", "rt640x64.inf"), "inf")
w(os.path.join(out, "cb", "drivers", NV2), b"M" * 3000); w(os.path.join(out, "cb", "drivers", "setup.exe"), b"khac"); w(os.path.join(out, "cb", "drivers", "wifi", NV1), b"W" * 10)
P5 = dict(json.loads(json.dumps(P)), info=os.path.join(tmp, "build-info.txt"))
fb = os.path.join(out, "cb", "os", "firstboot.d")
OLD_CMD = b'@echo off\r\nrem CloudBlue PC: cai driver VGA NVIDIA im lang o lan dang nhap dau (file nay do bo tao ISO tu sinh)\r\nexit /b 0\r\n'
w(os.path.join(fb, "1511", "50-vga-nvidia.cmd"), OLD_CMD)                           # thư mục làm việc dùng lại từ bản 20.11: còn file lệnh do bản cũ sinh
w(os.path.join(fb, "50-vga-nvidia.cmd"), b"@echo off\r\nrem file cua chu shop tu viet, trung ten\r\n")
B.layout(P5)
info5 = open(P5["info"], "rb").read().decode("ascii").split("\r\n")
ck("gói VGA NVIDIA .exe trong drivers\\1511 → chuyển sang firstboot.d\\1511 (không nạp kiểu driver)", open(os.path.join(fb, "1511", NV1), "rb").read() == b"N" * 5000
   and not os.path.exists(os.path.join(out, "cb", "drivers", "1511", NV1)) and os.path.isfile(os.path.join(out, "cb", "drivers", "1511", "LAN", "rt640x64.inf")))
ck("KHÔNG còn sinh file lệnh 50-vga-nvidia.cmd (cb_provision tự cài sau khi máy có mạng); file do bản cũ sinh bị dọn, file trùng tên của chủ shop giữ nguyên",
   not os.path.exists(os.path.join(fb, "1511", "50-vga-nvidia.cmd")) and open(os.path.join(fb, "50-vga-nvidia.cmd"), "rb").read().startswith(b"@echo off\r\nrem file cua chu shop"), os.listdir(os.path.join(fb, "1511")))
ck("gói NVIDIA để ở gốc drivers hoặc thư mục không phải tên bản Windows → cài cho MỌI bản (firstboot.d gốc)", os.path.isfile(os.path.join(fb, NV2)) and os.path.isfile(os.path.join(fb, NV1))
   and not os.path.exists(os.path.join(out, "cb", "drivers", "wifi", NV1)) and not os.path.exists(os.path.join(out, "cb", "drivers", NV2)))
ck("file .exe khác (không phải gói NVIDIA) để nguyên", open(os.path.join(out, "cb", "drivers", "setup.exe"), "rb").read() == b"khac")
ck("khung tóm tắt ghi rõ gói VGA nào, cài SAU KHI máy có mạng, cho bản nào", sum("VGA NVIDIA" in x and "SAU KHI may co mang" in x for x in info5) == 3 and any("(chi ban 1511)" in x for x in info5) and any("(moi ban)" in x for x in info5), info5)
B.layout(P5)
ck("chạy lại lần 2 không lỗi, không nhân đôi", sorted(os.listdir(os.path.join(fb, "1511"))) == [NV1] and not os.path.exists(os.path.join(out, "cb", "drivers", "1511", NV1)), os.listdir(os.path.join(fb, "1511")))
for d in ("drivers", os.path.join("os", "firstboot.d")): shutil.rmtree(os.path.join(out, "cb", d))
cfg = B.layout(json.loads(json.dumps(P)))

print("1b. Driver người dùng đưa riêng cho từng bản Windows (tao-iso.ps1 chép vào cb\\drivers\\_img<số thứ tự ISO>)")
drv = os.path.join(out, "cb", "drivers")
w(os.path.join(drv, "_img1", NV1), b"N" * 4000)                                      # ISO thứ 1 = bản 1511: gói VGA NVIDIA để nguyên file
w(os.path.join(drv, "_img1", "nvidia-vga-VGA_cua_toi.exe"), b"V" * 100)               # gói NVIDIA bị đổi tên, tao-iso.ps1 đã nhận ra và đánh dấu
w(os.path.join(drv, "_img1", "Driver_WLAN", "netrtwlane.inf"), "inf"); w(os.path.join(drv, "_img1", "Driver_WLAN", "rtwlane.sys"), "sys")
w(os.path.join(drv, "_img2", "lan", "e1d68x64.inf"), "inf")                          # ISO thứ 2 = bản 22h2
w(os.path.join(drv, "_img9", "x", "y.inf"), "inf")                                   # số lạ (không có ISO thứ 9)
w(os.path.join(drv, "rac", "readme.txt"), "khong co inf")
P6 = dict(json.loads(json.dumps(P)), info=os.path.join(tmp, "build-info.txt"))
B.layout(P6)
info6 = open(P6["info"], "rb").read().decode("ascii").split("\r\n")
ck("_img1 → drivers\\1511, _img2 → drivers\\22h2 (đúng thứ tự ISO), không còn thư mục _img1 / _img2", os.path.isfile(os.path.join(drv, "1511", "Driver_WLAN", "netrtwlane.inf"))
   and os.path.isfile(os.path.join(drv, "1511", "Driver_WLAN", "rtwlane.sys")) and os.path.isfile(os.path.join(drv, "22h2", "lan", "e1d68x64.inf"))
   and not os.path.exists(os.path.join(drv, "_img1")) and not os.path.exists(os.path.join(drv, "_img2")), os.listdir(drv))
ck("gói VGA NVIDIA kéo thả cho bản 1511 (cả file bị đổi tên đã đánh dấu nvidia-vga-) → nằm ở firstboot.d\\1511 để cài ở lần đăng nhập đầu, CHỈ bản 1511",
   sorted(os.listdir(os.path.join(fb, "1511"))) == [NV1, "nvidia-vga-VGA_cua_toi.exe"] and not any(B.NVIDIA_RE.match(f) for f in os.listdir(fb) if os.path.isfile(os.path.join(fb, f)))
   and not os.path.exists(os.path.join(drv, "1511", NV1)), os.listdir(os.path.join(fb, "1511")))
ck("khung tóm tắt: mỗi thư mục driver 1 dòng, ghi rõ nạp cho bản nào", "DRIVER 1511: 1 file .inf - chi nap khi cai ban 1511" in info6 and "DRIVER 22h2: 1 file .inf - chi nap khi cai ban 22h2" in info6
   and "DRIVER _img9: 1 file .inf - nap cho moi ban" in info6 and sum("VGA NVIDIA" in x and "(chi ban 1511)" in x for x in info6) == 2, info6)
ck("thư mục có file mà không có .inf nào → dòng cảnh báo (!)", "(!) DRIVER rac: co 1 file nhung KHONG co file .inf nao - khong nap duoc" in info6, info6)
ck("bộ cài chỉ nạp driver đúng bản: 1511 dùng thư mục 1511, không dùng 22h2", C.folder_applies("1511", "1511") and not C.folder_applies("22h2", "1511")
   and not C.folder_applies("1511", "22h2") and C.folder_applies("_img9", "1511") and C.folder_applies("rac", "22h2"))
w(os.path.join(drv, "_img1", "Driver_WLAN", "moi.inf"), "inf"); w(os.path.join(drv, "_img1", "le.zip"), b"zip")
got = B.adopt_driver_drops(os.path.join(out, "cb"), cfg["images"])
ck("thư mục tên bản đã có sẵn → gộp vào, trùng tên thì thêm đuôi _2 (không đè)", got == {"1511": 2} and os.path.isfile(os.path.join(drv, "1511", "Driver_WLAN", "netrtwlane.inf"))
   and os.path.isfile(os.path.join(drv, "1511", "Driver_WLAN_2", "moi.inf")) and os.path.isfile(os.path.join(drv, "1511", "le.zip")) and not os.path.exists(os.path.join(drv, "_img1")), (got, os.listdir(os.path.join(drv, "1511"))))
w(os.path.join(drv, "trong", "con", ".giu"), b""); os.remove(os.path.join(drv, "trong", "con", ".giu"))
rep6 = B.driver_report(os.path.join(out, "cb"))
ck("thư mục driver rỗng → dọn đi, không ghi dòng nào", not os.path.exists(os.path.join(drv, "trong")) and not any("trong" in x for x in rep6)
   and "DRIVER 1511: 2 file .inf - chi nap khi cai ban 1511" in rep6, rep6)
w(os.path.join(drv, "le.inf"), "inf")
ck("file .inf để lẻ ngay trong drivers → ghi là nạp cho mọi bản", B.driver_report(os.path.join(out, "cb"))[0] == "DRIVER (file le trong drivers): 1 file .inf - nap cho moi ban")
ck("không có thư mục drivers → không lỗi", B.adopt_driver_drops(os.path.join(tmp, "khong-co"), cfg["images"]) == {} and B.driver_report(os.path.join(tmp, "khong-co")) == [])
for d in ("drivers", os.path.join("os", "firstboot.d")): shutil.rmtree(os.path.join(out, "cb", d))
cfg = B.layout(json.loads(json.dumps(P)))

print("2. Chạy lại / đổi tham số")
P2 = json.loads(json.dumps(P)); P2["enroll_key"] = ""; P2["images"] = [P["images"][1]]
cfg = B.layout(P2)
ck("không nhập mã đăng ký → xoá enroll.key cũ, seed không có mã", not os.path.exists(os.path.join(out, "cb", "enroll.key")) and "enroll_key" not in json.load(open(os.path.join(oem, "seed.json"))))
ck("chỉ 1 ISO → 1 bản, vẫn tạo được", [i["id"] for i in cfg["images"]] == ["22h2"])
os.remove(os.path.join(out, "sources", "lang.ini"))
B.layout(P2)
au = open(os.path.join(out, "autounattend.xml"), encoding="utf-8").read()
r = subprocess.run(["xmllint", "--noout", os.path.join(out, "autounattend.xml")], capture_output=True, text=True)
ck("không đọc được lang.ini → bỏ khối ngôn ngữ (không điền bừa), XML vẫn hợp lệ", r.returncode == 0 and "International-Core-WinPE" not in au and 'pass="windowsPE"' in au)
P3 = json.loads(json.dumps(P)); P3["images"][0]["version"] = "10.0.19045.1"
cfg = B.layout(P3)
ck("2 ISO cùng build → tên 22h2 và 22h2-2, không đè nhau", sorted(i["id"] for i in cfg["images"]) == ["22h2", "22h2-2"] and os.path.isfile(os.path.join(out, "cb", "images", "22h2.esd")), [i["id"] for i in cfg["images"]])
for bad, why in (({"py": tmp}, "thiếu Python"), ({"images": []}, "không có bản nào")):
    Pb = json.loads(json.dumps(P)); Pb.update(bad)
    try: B.layout(Pb); okb = False
    except C.Stop: okb = True
    ck("%s → dừng có lời nhắn" % why, okb)
os.remove(os.path.join(out, "cb", "pe", "start.cmd"))
ck("thiếu file → kiểm cây ISO báo CHƯA ĐẠT", B.check(out) == 1)

print("3. Bản kê cập nhật agent")
m = B.manifest(REPO, "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/winpc/", "20.11a")
ck("có đủ file agent / lib / os / pe với sha256 đúng", m["ver"] == "20.11a" and not m["base"].endswith("/") and "agent/pcagent.py" in m["files"] and "lib/cbcore.py" in m["files"] and "pe/cb_pe.py" in m["files"] and "pe/start.cmd" in m["files"]
   and m["files"]["agent/pcagent.py"] == hashlib.sha256(open(os.path.join(REPO, "agent", "pcagent.py"), "rb").read()).hexdigest())
sys.path.insert(0, os.path.join(REPO, "agent"))
import pcagent
ck("mọi tên file trong bản kê đều được agent chấp nhận", all(pcagent.UPDATE_REL.match(k) for k in m["files"]), [k for k in m["files"] if not pcagent.UPDATE_REL.match(k)])
ck("ngôn ngữ bộ cài: đọc được nhiều kiểu lang.ini", (lambda d: (w(os.path.join(d, "sources", "lang.ini"), "[Available UI Languages]\nvi-VN = 2\nen-US = 3\n[Fallback Languages]\n"), B.setup_lang(d))[1])(tempfile.mkdtemp()) == "vi-VN" and B.setup_lang(tmp) == "")
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
