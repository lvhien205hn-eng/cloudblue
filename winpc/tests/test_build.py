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
P3 = dict(json.loads(json.dumps(P)), generic_key="on", info=os.path.join(tmp, "build-info.txt"), default="1511")
cfg3 = B.layout(P3)
info = open(P3["info"], "rb").read().decode("ascii").split("\r\n")
ck("ghi file tóm tắt cho tao-iso.ps1 (ASCII): 2 dòng ANH + dòng CUU_HO, có ghi chế độ khoá", len(info) == 4 and info[0].startswith("ANH 1511 | Windows 10 Pro | ban so 1 | 10.0.10586.0") and "MAC DINH" in info[0]
   and info[0].endswith("| dien khoa cai dat chung") and info[1].startswith("ANH 22h2") and info[1].endswith("| dien khoa cai dat chung") and info[2].startswith("CUU_HO ") and info[2].endswith("khoa cai dat chung: on") and info[3] == "", info)
au3 = open(os.path.join(out, "autounattend.xml"), encoding="utf-8").read()
ck("autounattend.xml (bộ cài thường, người cài tự chọn phiên bản) KHÔNG BAO GIỜ kèm khoá", cfg3["generic_key"] == "on" and cfg3["default"] == "1511" and "<ProductKey>" not in au3 and "ProductKey" not in au)
cfg = B.layout(json.loads(json.dumps(P)))                       # trả cây về như bước 1 cho các bước sau

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
