# -*- coding: utf-8 -*-
"""Thử bộ tạo ISO MÁY MẪU (proxmox/vm/vm_build.py + soát tĩnh tao-iso-may-mau.ps1 / maymau.ps1 / pe.cmd / SetupComplete.cmd).
   Chạy mọi máy, không cần Windows:  python3 proxmox/tests/test_vm_build.py"""
import hashlib, importlib.util, io, json, os, re, shutil, sys, tempfile, zipfile
import xml.dom.minidom as minidom

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


spec = importlib.util.spec_from_file_location("vm_build", os.path.join(ROOT, "vm", "vm_build.py"))
vb = importlib.util.module_from_spec(spec); spec.loader.exec_module(vb)
vb.say = lambda *a: None
tmp = tempfile.mkdtemp(prefix="vmbuild_")


def els(doc, tag): return doc.getElementsByTagName(tag)
def txt(e): return "".join(n.data for n in e.childNodes if n.nodeType == n.TEXT_NODE)


# ------------------------------------------------------------------ 1. chọn bản Windows
print("== 1. chọn bản Windows trong ISO")
r12 = vb.pick([
    {"index": 1, "name": "Windows Server 2012 R2 SERVERSTANDARDCORE", "edition": "ServerStandardEval", "version": "6.3.9600.17031", "itype": "Server Core", "arch": 9, "lang": "en-US"},
    {"index": 2, "name": "Windows Server 2012 R2 SERVERSTANDARD", "edition": "ServerStandardEval", "version": "6.3.9600.17031", "itype": "Server", "arch": 9, "lang": "en-US"},
    {"index": 3, "name": "Windows Server 2012 R2 SERVERDATACENTERCORE", "edition": "ServerDatacenterEval", "version": "6.3.9600.17031", "itype": "Server Core", "arch": 9, "lang": "en-US"},
    {"index": 4, "name": "Windows Server 2012 R2 SERVERDATACENTER", "edition": "ServerDatacenterEval", "version": "6.3.9600.17031", "itype": "Server", "arch": 9, "lang": "en-US"}])
im = {i["index"]: i for i in r12["images"]}
ck("2012 R2: mặc định bản Standard có giao diện (số 2), bản Core bị loại (nói rõ vì sao)", r12["default"] == 2 and not im[1]["ok"] and "Core" in im[1]["why"] and im[4]["ok"], r12)
ck("2012 R2 → driver 2k12R2, máy mẫu tpl-win2012r2, virtio 0.1.240", (im[2]["os"], im[2]["tag"], im[2]["virtio"], im[2]["server"]) == ("2k12R2", "win2012r2", "0.1.240", True), im[2])
r22 = vb.pick([
    {"index": 1, "name": "Windows Server 2022 Standard Evaluation", "edition": "ServerStandardEval", "version": "10.0.20348.587", "itype": "Server Core", "arch": 9},
    {"index": 2, "name": "Windows Server 2022 Standard Evaluation (Desktop Experience)", "edition": "ServerStandardEval", "version": "10.0.20348.587", "itype": "Server", "arch": 9},
    {"index": 4, "name": "Windows Server 2022 Datacenter Evaluation (Desktop Experience)", "edition": "ServerDatacenterEval", "version": "10.0.20348.587", "itype": "Server", "arch": 9}])
im22 = {i["index"]: i for i in r22["images"]}
ck("2022: Desktop Experience Standard → 2k22 / win2022 / virtio 0.1.271", r22["default"] == 2 and (im22[2]["os"], im22[2]["tag"], im22[2]["virtio"]) == ("2k22", "win2022", "0.1.271"), r22)
for ver, osd, tag in (("10.0.14393.0", "2k16", "win2016"), ("10.0.17763.737", "2k19", "win2019"), ("10.0.26100.1742", "2k25", "win2025")):
    c = vb.classify({"name": "Windows Server X SERVERSTANDARD", "edition": "ServerStandard", "version": ver, "itype": "Server", "arch": 9})
    ck("Server %s → %s / %s" % (ver, osd, tag), c["ok"] and (c["os"], c["tag"]) == (osd, tag), c)
rl = vb.pick([{"index": 1, "name": "Windows 10 Enterprise LTSC", "edition": "EnterpriseS", "version": "10.0.19044.1288", "itype": "Client", "arch": 9}])
ck("Windows 10 LTSC → w10 / win10ltsc, máy khách (không phải Server)", rl["default"] == 1 and (rl["images"][0]["os"], rl["images"][0]["tag"], rl["images"][0]["server"]) == ("w10", "win10ltsc", False), rl)
c = vb.classify({"name": "Windows 10 Pro", "edition": "Professional", "version": "10.0.19045.2006", "itype": "Client", "arch": 9})
ck("Windows 10 Pro → win10", c["ok"] and c["tag"] == "win10", c)
c11 = vb.classify({"name": "Windows 11 Pro", "edition": "Professional", "version": "10.0.22631.2428", "itype": "Client", "arch": 9})
c32 = vb.classify({"name": "Windows Server 2012 R2 SERVERSTANDARD", "edition": "ServerStandard", "version": "6.3.9600", "itype": "Server", "arch": 0})
cpe = vb.classify({"name": "Microsoft Windows Recovery Environment", "edition": "WindowsPE", "version": "10.0.20348.1", "itype": "WindowsPE", "arch": 9})
cdi = vb.classify({"name": "Windows Server 2016 SERVERSTANDARDCORE", "edition": "ServerStandard", "version": "10.0.14393.0", "itype": "", "arch": 9})
c08 = vb.classify({"name": "Windows Server 2008 R2 SERVERSTANDARD", "edition": "ServerStandard", "version": "6.1.7601", "itype": "Server", "arch": 9})
ck("loại: Win 11 · bản 32-bit · WinPE · bản Core khi chỉ đọc được bằng dism (không có loại cài) · Server 2008 R2",
   not any(x["ok"] for x in (c11, c32, cpe, cdi, c08)) and all(x["why"] for x in (c11, c32, cpe, cdi, c08)), (c11, c32, cpe, cdi, c08))
ck("không bản nào dùng được → mặc định 0", vb.pick([dict(index=1, name="x", edition="WindowsPE", version="10.0.1", itype="WindowsPE", arch=9)])["default"] == 0)


# ------------------------------------------------------------------ 2. file trả lời
print("== 2. autounattend.xml")
base = {"user": "VPS", "tag": "win2012r2", "admin_pw": "Cb<&>\"'Pw7!x", "image": {"index": 2, "lang": "en-US", "name": "Windows Server 2012 R2 SERVERSTANDARD"}}
xs = vb.unattend(dict(base, server=True))
ds = minidom.parseString(xs.encode("utf-8"))
passes = [e.getAttribute("pass") for e in els(ds, "settings")]
ck("Server: đọc được (XML hợp lệ), đủ 3 lượt windowsPE / specialize / oobeSystem", passes == ["windowsPE", "specialize", "oobeSystem"], passes)
paths = [txt(e) for e in els(ds, "Path")]
ck("windowsPE: tìm ổ có \\cbvm\\pe.cmd rồi chạy (chia ổ theo BIOS / UEFI) — không đụng bộ cài PC (\\cb\\pe\\start.cmd)",
   len(paths) == 1 and "\\cbvm\\pe.cmd" in paths[0] and "%a:" in paths[0] and "start.cmd" not in xs, paths)
md = els(ds, "MetaData")[0]
it = els(ds, "InstallTo")
ck("cài đúng bản số 2 (/IMAGE/INDEX) vào Ổ 0 · PHÂN VÙNG 2 (không dùng 'phân vùng trống đầu tiên' — bộ cài 2012 R2 không tìm ra)",
   txt(els(md, "Key")[0]) == "/IMAGE/INDEX" and txt(els(md, "Value")[0]) == "2" and len(it) == 1 and txt(els(it[0], "DiskID")[0]) == "0"
   and txt(els(it[0], "PartitionID")[0]) == "2" == str(vb.WIN_PART) and not els(ds, "InstallToAvailablePartition") and not els(ds, "DiskConfiguration"), xs)
ap = els(ds, "AdministratorPassword")
ck("Server: mật khẩu Administrator ngẫu nhiên (ký tự đặc biệt được thoát đúng), KHÔNG tạo tài khoản / tự đăng nhập trong file trả lời",
   len(ap) == 1 and txt(els(ap[0], "Value")[0]) == base["admin_pw"] and not els(ds, "LocalAccounts") and not els(ds, "AutoLogon"), xs)
ck("Server: chỉ ẩn trang điều khoản (mục OOBE có ở mọi bản), không mục chỉ có ở Windows 10",
   [n.tagName for n in els(ds, "OOBE")[0].childNodes if n.nodeType == n.ELEMENT_NODE] == ["HideEULAPage"] and "Microsoft-Windows-Deployment" not in xs, xs)
ck("tên máy CLOUDBLUE-VPS, giờ SE Asia Standard Time (UTC+7)", txt(els(ds, "ComputerName")[0]) == "CLOUDBLUE-VPS"
   and all(txt(e) == "SE Asia Standard Time" for e in els(ds, "TimeZone")) and len(els(ds, "TimeZone")) == 2)
ck("không khoá cài đặt khi không đưa -Key", not els(ds, "ProductKey"))
xc = vb.unattend(dict(base, server=False, tag="win10ltsc", image={"index": 1, "lang": "en-US"}))
dc = minidom.parseString(xc.encode("utf-8"))
la = els(dc, "LocalAccount")
ck("Win10: tạo tài khoản VPS (nhóm Administrators, mật khẩu trống) + tự đăng nhập, không mật khẩu Administrator",
   len(la) == 1 and txt(els(la[0], "Name")[0]) == "VPS" and txt(els(la[0], "Group")[0]) == "Administrators" and txt(els(la[0], "Value")[0]) == ""
   and txt(els(els(dc, "AutoLogon")[0], "Username")[0]) == "VPS" and not els(dc, "AdministratorPassword"), xc)
ck("Win10: ẩn các trang hỏi lúc đầu + tắt trang quyền riêng tư (chính sách DisablePrivacyExperience)",
   all(els(dc, t) for t in ("HideLocalAccountScreen", "HideOnlineAccountScreens", "HideWirelessSetupInOOBE", "ProtectYourPC"))
   and "DisablePrivacyExperience" in xc, xc)
xk = vb.unattend(dict(base, server=True, key="d2n9p-3p6x9-2r39c-7rtcd-mdvjx"))
ck("-Key hợp lệ → ProductKey (chữ hoa)", "<Key>D2N9P-3P6X9-2R39C-7RTCD-MDVJX</Key>" in xk)
bad = []
for kw in ({"key": "abc"}, {"user": "bad user"}, {"user": "1VPS"}):
    try: vb.unattend(dict(base, server=True, **kw)); bad.append(kw)
    except ValueError: pass
ck("khoá sai dạng / tên tài khoản lạ → báo lỗi", not bad, bad)
xl = vb.unattend(dict(base, server=True, image={"index": 3, "lang": "vi-VN"}))
xj = vb.unattend(dict(base, server=True, image={"index": 3, "lang": "<x>"}))
ck("ngôn ngữ giao diện theo bản Windows (vi-VN); giá trị lạ → en-US", "<UILanguage>vi-VN</UILanguage>" in xl and "<x>" not in xj and "<UILanguage>en-US</UILanguage>" in xj)
pw = [vb.admin_password() for _ in range(20)]
ck("mật khẩu Administrator: 25 ký tự, đủ hoa / thường / số / ký tự đặc biệt, mỗi lần khác nhau",
   all(len(p) == 25 and re.search(r"[A-Z]", p) and re.search(r"[a-z]", p) and re.search(r"\d", p) and "!" in p for p in pw) and len(set(pw)) == 20)


# ------------------------------------------------------------------ 3. ghép cây ISO
print("== 3. ghép cây ISO (layout + check)")


def mk(p, data=b"x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)


def make_tree(osdir, drivers=("vioscsi", "viostor", "NetKVM", "vioserial", "Balloon", "pvpanic", "qxldod", "viogpudo")):
    t = tempfile.mkdtemp(dir=tmp)
    iso, tool, py, vio = (os.path.join(t, n) for n in ("iso", "tool", "py", "virtio"))
    for n in ("sources/boot.wim", "sources/install.wim", "boot/etfsboot.com", "efi/microsoft/boot/efisys.bin", "setup.exe"): mk(os.path.join(iso, n))
    for sub, files in vb.PAYLOAD.items():
        for f in files: shutil.copyfile(os.path.join(REPO, "winpc", sub, f), os.path.join(tool, "winpc", sub, f)) if os.makedirs(os.path.join(tool, "winpc", sub), exist_ok=True) is None else None
    os.makedirs(os.path.join(tool, "proxmox", "vm"), exist_ok=True)
    for f in ("maymau.ps1", "pe.cmd", "SetupComplete.cmd", "vm_build.py"): shutil.copyfile(os.path.join(ROOT, "vm", f), os.path.join(tool, "proxmox", "vm", f))
    for n in ("python.exe", "pythonw.exe", "python312.zip", "python312._pth"): mk(os.path.join(py, n))
    for d in drivers:
        mk(os.path.join(vio, d, osdir, "amd64", d.lower() + ".inf"), b"[Version]")
        mk(os.path.join(vio, d, osdir, "amd64", d.lower() + ".sys"))
        mk(os.path.join(vio, d, "w11", "amd64", d.lower() + ".inf"), b"[Version]")       # bản Windows khác: không được chép
    mk(os.path.join(vio, "guest-agent", "qemu-ga-x86_64.msi"), b"msi")
    for n, d in (("ucrt.msu", b"msu"), ("ffmpeg.exe", b"MZff"), ("cacert.pem", b"-----BEGIN CERTIFICATE-----")): mk(os.path.join(t, n), d)
    return t, {"iso_root": iso, "tool": tool, "py_dir": py, "virtio_root": vio, "ga_msi": os.path.join(vio, "guest-agent", "qemu-ga-x86_64.msi"),
               "os": osdir, "user": "VPS", "image": {"index": 2, "name": "Windows Server 2012 R2 SERVERSTANDARD", "edition": "ServerStandardEval", "version": "6.3.9600.17031", "lang": "en-US"},
               "ucrt": os.path.join(t, "ucrt.msu"), "ffmpeg": os.path.join(t, "ffmpeg.exe"), "cacert": os.path.join(t, "cacert.pem"),
               "sb_url": "https://abc.supabase.co", "sb_key": "sb_publishable_x", "virtio_ver": "0.1.240", "built": "2026-11-24 15:30:00"}


t, P = make_tree("2k12R2")
P.update(tag="win2012r2", server=True)
rc = vb.layout(P)
iso = P["iso_root"]
cbd = os.path.join(iso, "sources", "$OEM$", "$1", "CloudBluePC")
ck("layout chạy xong + check đạt", rc == 0 and vb.check(iso) == 0)
wpd = sorted(os.listdir(os.path.join(iso, "$WinPEDriver$")))
ck("$WinPEDriver$: driver ổ đĩa / mạng / cổng QEMU agent / balloon / pvpanic của ĐÚNG bản 2k12R2 — KHÔNG driver màn hình (VPS không cần VGA)",
   wpd == ["Balloon", "NetKVM", "pvpanic", "vioscsi", "vioserial", "viostor"] and os.path.isfile(os.path.join(iso, "$WinPEDriver$", "vioscsi", "vioscsi.inf"))
   and not os.path.exists(os.path.join(iso, "$WinPEDriver$", "vioscsi", "w11")), wpd)
cfg = json.load(open(os.path.join(cbd, "cb.json")))
ck("cb.json: tài khoản VPS mật khẩu trống, GIỮ quyền Admin, không phân vùng cứu hộ, không bản Windows nào để cài lại, vai trò vm, địa chỉ web",
   (cfg["user"], cfg["password"], cfg["user_admin"], cfg["recovery"], cfg["images"], cfg["role"], cfg["sb_url"], cfg["sb_key"]) ==
   ("VPS", "", True, False, [], "vm", "https://abc.supabase.co", "sb_publishable_x") and cfg["timezone"] == "SE Asia Standard Time", cfg)
ck("KHÔNG mang mã máy / vé / mã đăng ký (identity.json, seed.json, enroll.key)", not any(os.path.exists(os.path.join(cbd, n)) for n in ("identity.json", "seed.json", "enroll.key"))
   and "enroll" not in json.dumps(cfg))
have = {os.path.relpath(os.path.join(r, f), cbd).replace(os.sep, "/") for r, _, fs in os.walk(cbd) for f in fs}
want = {"py/python.exe", "py/pythonw.exe", "lib/cbsys.py", "lib/cbcore.py", "lib/cbrec.py", "os/cb_provision.py", "os/provision.cmd", "os/cacert.pem",
        "agent/pcagent.py", "agent/pcremote.py", "agent/watch.cmd", "agent/cbpc.cmd", "bin/ffmpeg.exe", "cb.json", "vm/maymau.ps1", "vm/maymau.json",
        "vm/qemu-ga-x86_64.msi", "vm/ucrt.msu", "vm/drivers/vioscsi/vioscsi.inf", "vm/drivers/NetKVM/netkvm.inf"}
ck("C:\\CloudBluePC: Python + agent + chứng chỉ + ffmpeg + cb.json + vm\\ (maymau.ps1, QEMU agent, bản vá UCRT, driver)", want <= have, sorted(want - have))
ck("bộ cài Windows chạy SetupComplete.cmd của máy mẫu", open(os.path.join(iso, "sources", "$OEM$", "$$", "Setup", "Scripts", "SetupComplete.cmd"), "rb").read()
   == open(os.path.join(ROOT, "vm", "SetupComplete.cmd"), "rb").read())
mj = json.load(open(os.path.join(cbd, "vm", "maymau.json")))
ck("maymau.json: tpl / bản driver / Server / tài khoản / bản Windows", (mj["tag"], mj["os"], mj["server"], mj["user"], mj["image"]["index"], mj["virtio"]) ==
   ("win2012r2", "2k12R2", True, "VPS", 2, "0.1.240") and "qxldod" not in mj["drivers"], mj)
ux = open(os.path.join(iso, "autounattend.xml"), "rb").read()
ck("autounattend.xml ở gốc ISO, xuống dòng CRLF, có mật khẩu Administrator ngẫu nhiên (không in ra)", b"\r\n" in ux and not re.search(rb"(?<!\r)\n", ux) and b"<AdministratorPassword>" in ux)
bt, ut = (open(os.path.join(iso, "cbvm", n), "rb").read() for n in ("bios.txt", "uefi.txt"))
nparts = lambda t: [x for x in t.split(b"\r\n") if x.startswith(b"create partition")]
ck("diskpart: BIOS = System 100 MB (active) + Windows · UEFI = GPT, EFI 100 MB + Windows — cả 2 kiểu Windows là PHÂN VÙNG 2, nằm cuối ổ, gán chữ W (cùng xoá sạch ổ 0)",
   bt.startswith(b"select disk 0\r\nclean\r\n") and ut.startswith(b"select disk 0\r\nclean\r\n") and b"convert gpt" not in bt and b"convert gpt" in ut
   and nparts(bt) == [b"create partition primary size=100", b"create partition primary"] and nparts(ut) == [b"create partition efi size=100", b"create partition primary"]
   and bt.index(b"active") < bt.index(b"create partition primary\r\n") and all(t.rstrip().endswith(b"label=Windows\r\nassign letter=W\r\nexit") for t in (bt, ut))
   and len(nparts(bt)) == len(nparts(ut)) == vb.WIN_PART, (bt, ut))
pe = open(os.path.join(iso, "cbvm", "pe.cmd"), encoding="ascii").read()
ck("pe.cmd: nạp driver ổ VirtIO trước (drvload) → đọc kiểu firmware → chọn bios.txt / uefi.txt",
   "drvload" in pe and "$WinPEDriver$\\vioscsi" in pe and "PEFirmwareType" in pe and "cbvm\\uefi.txt" in pe and "cbvm\\bios.txt" in pe and pe.index("drvload") < pe.index("diskpart"))
ck("pe.cmd: CHỜ ổ đĩa 0 hiện ra (driver vừa nạp) rồi mới chia; diskpart lỗi thì thử lại; chép nhật ký sang ổ Windows mới (W:); luôn thoát mã 0",
   pe.index("drvload") < pe.index('find /i "Disk 0"') < pe.index('diskpart /s "%DP%"') and "goto cho" in pe and "goto chia" in pe and "if not errorlevel 1 goto xong" in pe
   and "W:\\cbvm-pe.log" in pe and pe.count("exit /b 0") == 2 and "timeout" not in pe.lower().replace("khong co timeout.exe", "") and "\r\n" in open(os.path.join(iso, "cbvm", "pe.cmd"), "rb").read().decode("ascii")
   and not re.search(r"(?<!\r)\n", open(os.path.join(iso, "cbvm", "pe.cmd"), "rb").read().decode("ascii")))
os.remove(os.path.join(cbd, "vm", "ucrt.msu"))
ck("check: 2012 R2 thiếu bản vá UCRT → báo thiếu", vb.check(iso) == 1)
mk(os.path.join(cbd, "vm", "ucrt.msu")); mk(os.path.join(cbd, "identity.json"), b'{"id":"x"}')
ck("check: lỡ có identity.json (máy mẫu mang mã máy) → báo", vb.check(iso) == 1)
os.remove(os.path.join(cbd, "identity.json"))
rc2 = vb.layout(P)
ck("ghép lại lần 2 trên cùng cây (chạy lại lệnh) → vẫn đạt, không chồng file cũ", rc2 == 0 and vb.check(iso) == 0)

t2, P2 = make_tree("2k12R2", drivers=("vioscsi", "viostor", "vioserial"))
P2.update(tag="win2012r2", server=True)
try: vb.layout(P2); err = ""
except ValueError as e: err = str(e)
ck("ISO virtio thiếu driver mạng cho đúng bản → dừng, nói rõ (2012 R2 dùng virtio 0.1.240)", "NetKVM" in err and "0.1.240" in err, err)
t3, P3 = make_tree("w10")
P3.update(tag="win10ltsc", server=False, ucrt="", ffmpeg="", image={"index": 1, "name": "Windows 10 Enterprise LTSC", "edition": "EnterpriseS", "version": "10.0.19044.1288", "lang": "en-US"})
ok3 = vb.layout(P3) == 0 and vb.check(P3["iso_root"]) == 0
cb3 = os.path.join(P3["iso_root"], "sources", "$OEM$", "$1", "CloudBluePC")
ck("Win10 LTSC: không cần bản vá UCRT; không kèm ffmpeg thì VPS tự tải; tạo tài khoản VPS trong file trả lời",
   ok3 and not os.path.exists(os.path.join(cb3, "vm", "ucrt.msu")) and not os.path.exists(os.path.join(cb3, "bin"))
   and b"<LocalAccount" in open(os.path.join(P3["iso_root"], "autounattend.xml"), "rb").read())
out = os.path.join(tmp, "pick.json")
json.dump({"index": 1, "name": "Windows 10 Enterprise LTSC", "edition": "EnterpriseS", "version": "10.0.19044.1288", "itype": "Client", "arch": 9}, open(os.path.join(tmp, "one.json"), "w"))
rcp = vb.main(["pick", os.path.join(tmp, "one.json"), out])
ck("pick: PowerShell ghi 1 bản thành object (không phải mảng) vẫn đọc được", rcp == 0 and json.load(open(out))["default"] == 1)
ck("layout lỗi → mã 1 (không văng lỗi Python)", vb.main(["layout", os.path.join(tmp, "khong-co.json")]) == 1)


# ------------------------------------------------------------------ 4. ffmpeg
print("== 4. ffmpeg kèm sẵn")
exe_data = b"MZ" + os.urandom(5000)
zb = io.BytesIO()
with zipfile.ZipFile(zb, "w") as z: z.writestr("ffmpeg-6.1.1-essentials_build/bin/ffmpeg.exe", exe_data); z.writestr("ffmpeg-6.1.1-essentials_build/README.txt", "x")
zdata = zb.getvalue()
fake_rem = os.path.join(tmp, "pcremote.py")
open(fake_rem, "w").write('FF_URL = "https://example.test/ff.zip"\nFF_ZIP_SIZE = %d\nFF_ZIP_SHA = "%s"\nFF_EXE_SHA = "%s"       # ghi chu\n'
                          % (len(zdata), hashlib.sha256(zdata).hexdigest(), hashlib.sha256(exe_data).hexdigest()))
calls = []


def fetch(url, dst):
    calls.append(url); open(dst, "wb").write(zdata)


dd, cache = os.path.join(tmp, "ffout"), os.path.join(tmp, "ffcache")
r1 = vb.ffmpeg(fake_rem, dd, cache, fetch=fetch)
r2 = vb.ffmpeg(fake_rem, dd, cache, fetch=fetch)
os.remove(os.path.join(dd, "ffmpeg.exe"))
r3 = vb.ffmpeg(fake_rem, dd, cache, fetch=fetch)
ck("tải 1 lần, kiểm mã zip + exe, chạy lại không tải lại (exe có sẵn / zip trong bộ nhớ đệm)", (r1, r2, r3) == (0, 0, 0) and calls == ["https://example.test/ff.zip"]
   and open(os.path.join(dd, "ffmpeg.exe"), "rb").read() == exe_data)
ck("hằng số ffmpeg đọc đúng từ pcremote.py thật", vb.ff_consts(os.path.join(REPO, "winpc", "agent", "pcremote.py"))[0].startswith("https://github.com/"))
open(fake_rem, "a").write("")
bad_rem = os.path.join(tmp, "pcremote_bad.py")
open(bad_rem, "w").write(open(fake_rem).read().replace(hashlib.sha256(zdata).hexdigest(), "0" * 64))
r4 = vb.ffmpeg(bad_rem, os.path.join(tmp, "ffout2"), os.path.join(tmp, "ffcache2"), fetch=fetch)
ck("zip tải về sai mã kiểm → bỏ qua (không chép file lạ)", r4 == 1 and not os.path.exists(os.path.join(tmp, "ffout2", "ffmpeg.exe")))


# ------------------------------------------------------------------ 5. soát tĩnh các script
print("== 5. soát tĩnh script")
ps = open(os.path.join(ROOT, "tao-iso-may-mau.ps1"), encoding="ascii").read()
mm = open(os.path.join(ROOT, "vm", "maymau.ps1"), encoding="ascii").read()
sc = open(os.path.join(ROOT, "vm", "SetupComplete.cmd"), encoding="ascii").read()
ck("lệnh 1 dòng nhận ra đúng file (chuỗi cloudblue-iso-may-mau)", "cloudblue-iso-may-mau" in ps and "cloudblue-may-mau" in mm)
wl = re.search(r"\$WinpcFiles = @\((.*?)\)", ps, re.S).group(1)
psw = set(re.findall(r'"([^"]+)"', wl))
vbw = {"%s/%s" % (sub, f) for sub, fs in vb.PAYLOAD.items() for f in fs}
man = json.load(open(os.path.join(REPO, "winpc", "manifest.json")))
ck("file phần mềm CloudBlue: tao-iso-may-mau.ps1 tải đúng bộ vm_build.py chép, đều có mã kiểm trong winpc/manifest.json",
   psw == vbw and all(f in man["sha256"] for f in psw), (psw ^ vbw, [f for f in psw if f not in man["sha256"]]))
vmw = set(re.findall(r'"(proxmox/vm/[^"]+)"', re.search(r"\$VmFiles = @\((.*?)\)", ps, re.S).group(1)))
ck("tải đủ file máy mẫu (vm_build.py, maymau.ps1, SetupComplete.cmd, pe.cmd) và có thật trong kho",
   vmw == {"proxmox/vm/" + f for f in ("vm_build.py", "maymau.ps1", "SetupComplete.cmd", "pe.cmd")} and all(os.path.isfile(os.path.join(REPO, f)) for f in vmw), vmw)
ck("SetupComplete.cmd gọi maymau.ps1 bước 1 (PowerShell, bỏ qua chính sách chạy script), luôn thoát 0",
   "C:\\CloudBluePC\\vm\\maymau.ps1\" -Buoc 1" in sc and "-ExecutionPolicy Bypass" in sc and sc.rstrip().endswith("exit /b 0"))
ck("maymau.ps1: không dùng lệnh chỉ có ở PowerShell 5+ (máy 2012 R2 là PowerShell 4)",
   not re.search(r"(?i)Get-LocalUser|New-LocalUser|Add-LocalGroupMember|::new\(|-NoNewline|-AsByteStream|Expand-Archive", mm))
ck("maymau.ps1: bước 2 chạy bằng SYSTEM (S-1-5-18) lúc đăng nhập / bật máy / sau 4 phút; xong tự gỡ tác vụ",
   all(k in mm for k in ("<UserId>S-1-5-18</UserId>", "<LogonTrigger>", "<BootTrigger>", "<TimeTrigger>", "/delete\", \"/tn\", $TaskName")))
ck("maymau.ps1: cài phần mềm bằng đúng 2 pha của cb_provision (specialize + system) + đặt mốc firstlogon (để pha system khoá quyền / chặn tài khoản khách sửa phần mềm)",
   'Prov "specialize"' in mm and 'Prov "system"' in mm and 'Touch-Mark "firstlogon.done"' in mm and mm.index('Prov "specialize"') < mm.index('Touch-Mark "firstlogon.done"') < mm.index('Prov "system"'))
ck("maymau.ps1: khoá MỌI tài khoản khác (mật khẩu ngẫu nhiên + tắt) — VPS nhân ra không chung mật khẩu quản trị", "Lock-Others" in mm and "SetPassword($pw)" in mm and "/active:no" in mm)
ck("maymau.ps1: Python chưa chạy (vừa cài bản vá UCRT) → khởi động lại, tối đa 3 lần; không in mật khẩu", "reboot.n" in mm and "-lt 3" in mm and not re.search(r"Log[^\n]*\$pw", mm))
ck("maymau.ps1: KHÔNG xoá seed.json / identity.json (bảng điều khiển máy mẫu: máy chủ đưa vé vào để admin điều khiển; lúc lưu mẫu máy chủ tự xoá mã máy)",
   not re.search(r'Remove-Item[^\n]*(seed|identity)\.json', mm) and "seed.json" in mm)
ck("maymau.ps1: không bao giờ tự tắt máy mẫu khi xong (để điều khiển / chỉnh tiếp)", not re.search(r'shutdown\.exe"\s*@\("/s"', mm) and 'shutdown.exe" @("/r"' in mm)

shutil.rmtree(tmp, ignore_errors=True)
print("\n%d/%d đạt" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
