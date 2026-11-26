# -*- coding: utf-8 -*-
"""cloudblue vm_build — phần Python của bộ tạo ISO MÁY MẪU VPS ảo hoá (proxmox/tao-iso-may-mau.ps1 gọi bằng Python nhúng trên máy Windows của chủ shop).

   pick    <images.json> <out.json>     các bản Windows trong ISO gốc → bản nào dùng được, bản mặc định, thư mục driver virtio, tên máy mẫu
   ffmpeg  <pcremote.py> <thư mục đích> <thư mục tải>   tải ffmpeg đúng bản + mã kiểm mà agent dùng (đọc hằng số trong pcremote.py) → <đích>\\bin\\ffmpeg.exe
   layout  <params.json>                ghi vào cây ISO đã chép: autounattend.xml, cbvm\\ (chia ổ trong WinPE), $WinPEDriver$\\ (driver virtio),
                                        sources\\$OEM$\\$1\\CloudBluePC\\ (Python + agent + cb.json + vm\\) và $OEM$\\$$\\Setup\\Scripts\\SetupComplete.cmd
   check   <cây ISO>                    kiểm cây ISO trước khi đóng file

   Chỉ dùng thư viện chuẩn. Không in mật khẩu nào ra màn hình."""
import hashlib, json, os, re, secrets, shutil, string, sys, zipfile
from xml.sax.saxutils import escape as xml_esc

VER = "26.11a"
WIN_PART = 2                        # số phân vùng Windows sau khi pe.cmd chia ổ (BIOS: System + Windows · UEFI: EFI + Windows)
TZ = "SE Asia Standard Time"
USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,19}$")
# driver virtio cho VPS (KHÔNG có driver màn hình: VPS không cần VGA). Bắt buộc: ổ đĩa + mạng + cổng nối QEMU guest agent.
DRV_NEED = ("vioscsi", "viostor", "NetKVM", "vioserial")
DRV_MORE = ("Balloon", "pvpanic", "viorng", "vioinput", "fwcfg")
VIRTIO_FOR = {"2k12R2": "0.1.240"}             # 0.1.240 = bản cuối còn driver 2012 R2 · bản khác: 0.1.271 (0.1.285 lỗi ổ đĩa / mạng)
VIRTIO_DEFAULT = "0.1.271"
VIRTIO_URL = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-{v}-1/virtio-win-{v}.iso"
COMPUTER = "CLOUDBLUE-VPS"
# phần mềm CloudBlue PC chép vào C:\CloudBluePC (giống bộ cài PC: winpc/cb_build.py PAYLOAD, bỏ phần bộ cài PE)
PAYLOAD = {"lib": ("cbsys.py", "cbcore.py", "cbrec.py"),
           "os": ("cb_provision.py", "provision.cmd", "cb_stage.py", "unattend.tpl.xml", "wallpaper.jpg"),
           "agent": ("pcagent.py", "pcremote.py", "watch.cmd", "cbpc.cmd")}
VM_FILES = ("maymau.ps1",)
NS = 'processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS"'


def say(m): print(m, flush=True)


def load(p):
    with open(p, encoding="utf-8-sig") as f: return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8", newline="") as f: json.dump(obj, f, ensure_ascii=True, indent=1)


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4]) + (0, 0, 0, 0)


# ====================================================================================== chọn bản Windows
def classify(im):
    """1 bản trong install.wim → dict(ok, why, os = thư mục driver virtio, tag = đuôi tên máy mẫu, server)."""
    v = vtuple(im.get("version"))
    itype = str(im.get("itype") or "").strip().lower()
    ed = str(im.get("edition") or "")
    name = str(im.get("name") or "")
    out = {"ok": False, "why": "", "os": "", "tag": "", "server": False}
    if int(im.get("arch") or 0) != 9: out["why"] = "khong phai ban 64-bit"; return out
    server = itype.startswith("server") or ed.lower().startswith("server") or "server" in name.lower()
    out["server"] = server
    if itype == "server core" or (not itype and (re.search(r"core$", ed, re.I) or re.search(r"core$", name.strip(), re.I))):
        out["why"] = "ban Server Core (khong co giao dien) - chon ban co giao dien (Desktop Experience / khong co chu CORE)"; return out
    if itype not in ("", "server", "client"):
        out["why"] = "khong phai ban Windows de cai (%s)" % im.get("itype"); return out
    major, minor, build = v[0], v[1], v[2]
    if server:
        if (major, minor) == (6, 3): out.update(os="2k12R2", tag="win2012r2")
        elif major == 10 and build == 14393: out.update(os="2k16", tag="win2016")
        elif major == 10 and build == 17763: out.update(os="2k19", tag="win2019")
        elif major == 10 and build == 20348: out.update(os="2k22", tag="win2022")
        elif major == 10 and build == 26100: out.update(os="2k25", tag="win2025")
        else: out["why"] = "ban Server %s chua ho tro (2012 R2 / 2016 / 2019 / 2022 / 2025)" % im.get("version"); return out
    else:
        if major == 10 and build >= 22000: out["why"] = "Windows 11 chua ho tro (can TPM + Secure Boot)"; return out
        if major == 10 and build >= 10240: out.update(os="w10", tag="win10ltsc" if re.match(r"(Enterprise|IoTEnterprise)S", ed) else "win10")
        else: out["why"] = "ban Windows %s chua ho tro (Windows 10 / Server)" % im.get("version"); return out
    out["ok"] = True
    return out


def pick(images):
    """→ {"images": [... + ok/why/os/tag/server], "default": số thứ tự bản mặc định (0 = không có bản nào dùng được)}.
       Mặc định: bản Server có giao dien + Standard → bản Server có giao diện khác → bản Windows 10 LTSC → bản đầu tiên dùng được."""
    rows = []
    for im in images:
        r = dict(im); r.update(classify(im)); r["index"] = int(im.get("index") or 0)
        r["virtio"] = VIRTIO_FOR.get(r["os"], VIRTIO_DEFAULT) if r["ok"] else ""
        rows.append(r)
    ok = [r for r in rows if r["ok"]]

    def rank(r):
        ed = str(r.get("edition") or "") + " " + str(r.get("name") or "")
        return (0 if r["server"] and re.search(r"standard", ed, re.I) else 1 if r["server"] else 2 if r["tag"] == "win10ltsc" else 3, r["index"])
    best = min(ok, key=rank) if ok else None
    return {"images": rows, "default": best["index"] if best else 0}


# ====================================================================================== file trả lời
def admin_password():
    """Mật khẩu Administrator dùng 1 lần lúc cài (máy mẫu tự đặt lại ngẫu nhiên + tắt tài khoản này ở cuối). Đủ 4 loại ký tự."""
    pool = string.ascii_letters + string.digits
    core = "".join(secrets.choice(pool) for _ in range(20))
    return "Cb" + core + "7!x"


def component(name, body):
    return '    <component name="%s" %s>\n%s    </component>\n' % (name, NS, body)


def unattend(p):
    """autounattend.xml cho máy mẫu. Chỉ dùng các mục có ở MỌI bản (2012 R2 … 2022, Win10): mục lạ làm bộ cài Windows dừng lại báo lỗi."""
    im = p["image"]
    lang = str(im.get("lang") or "en-US")
    if not re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z0-9-]{2,8}", lang): lang = "en-US"
    srv = bool(p["server"])
    user = p["user"]
    if not USER_RE.match(user): raise ValueError("ten tai khoan khong hop le: %r" % user)
    key = str(p.get("key") or "").strip().upper()
    if key and not re.fullmatch(r"[0-9A-Z]{5}(-[0-9A-Z]{5}){4}", key): raise ValueError("khoa cai dat phai co dang XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")
    idx = int(im["index"])
    pe_lang = ("      <SetupUILanguage>\n        <UILanguage>%s</UILanguage>\n      </SetupUILanguage>\n"
               "      <InputLocale>en-US</InputLocale>\n      <SystemLocale>en-US</SystemLocale>\n      <UILanguage>%s</UILanguage>\n"
               "      <UserLocale>en-US</UserLocale>\n") % (lang, lang)
    setup = ("      <RunSynchronous>\n"
             "        <RunSynchronousCommand wcm:action=\"add\">\n"
             "          <Order>1</Order>\n"
             "          <Path>cmd.exe /c \"for %%a in (C D E F G H I J K L M N O P Q R S T U V W Y Z) do @if exist %%a:\\cbvm\\pe.cmd call %%a:\\cbvm\\pe.cmd\"</Path>\n"
             "          <Description>CloudBlue - chia o dia may mau</Description>\n"
             "        </RunSynchronousCommand>\n"
             "      </RunSynchronous>\n"
             "      <ImageInstall>\n"
             "        <OSImage>\n"
             "          <InstallFrom>\n"
             "            <MetaData wcm:action=\"add\">\n"
             "              <Key>/IMAGE/INDEX</Key>\n"
             "              <Value>%d</Value>\n"
             "            </MetaData>\n"
             "          </InstallFrom>\n"
             "          <InstallTo>\n"
             "            <DiskID>0</DiskID>\n"
             "            <PartitionID>%d</PartitionID>\n"
             "          </InstallTo>\n"
             "          <WillShowUI>OnError</WillShowUI>\n"
             "        </OSImage>\n"
             "      </ImageInstall>\n"
             "      <UserData>\n"
             "        <AcceptEula>true</AcceptEula>\n"
             "        <FullName>CloudBlue</FullName>\n"
             "        <Organization>CloudBlue</Organization>\n"
             "%s"
             "      </UserData>\n") % (idx, WIN_PART, ("        <ProductKey>\n          <Key>%s</Key>\n          <WillShowUI>OnError</WillShowUI>\n        </ProductKey>\n" % key) if key else "")
    spec = "      <ComputerName>%s</ComputerName>\n      <TimeZone>%s</TimeZone>\n" % (COMPUTER, TZ)
    dep = ("      <RunSynchronous>\n"
           "        <RunSynchronousCommand wcm:action=\"add\">\n"
           "          <Order>1</Order>\n"
           "          <Path>reg.exe add HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\OOBE /v DisablePrivacyExperience /t REG_DWORD /d 1 /f</Path>\n"
           "          <Description>CloudBlue - bo trang quyen rieng tu</Description>\n"
           "        </RunSynchronousCommand>\n"
           "      </RunSynchronous>\n")
    intl = ("      <InputLocale>en-US</InputLocale>\n      <SystemLocale>en-US</SystemLocale>\n      <UILanguage>%s</UILanguage>\n"
            "      <UserLocale>en-US</UserLocale>\n") % lang
    if srv:
        # Server: bộ cài BẮT đặt mật khẩu Administrator → đặt ngẫu nhiên (không ai biết). Tài khoản khách (không mật khẩu) do maymau.ps1 tạo
        # sau khi tắt luật "mật khẩu phức tạp" của Server; tự đăng nhập cũng do maymau.ps1 đặt.
        oobe = "      <OOBE>\n        <HideEULAPage>true</HideEULAPage>\n      </OOBE>\n"
        acc = ("      <UserAccounts>\n        <AdministratorPassword>\n          <Value>%s</Value>\n          <PlainText>true</PlainText>\n"
               "        </AdministratorPassword>\n      </UserAccounts>\n") % xml_esc(p["admin_pw"])
        auto = ""
    else:
        oobe = ("      <OOBE>\n        <HideEULAPage>true</HideEULAPage>\n        <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>\n"
                "        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>\n        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>\n"
                "        <HideLocalAccountScreen>true</HideLocalAccountScreen>\n        <ProtectYourPC>3</ProtectYourPC>\n      </OOBE>\n")
        acc = ("      <UserAccounts>\n        <LocalAccounts>\n          <LocalAccount wcm:action=\"add\">\n            <Name>%s</Name>\n"
               "            <DisplayName>%s</DisplayName>\n            <Group>Administrators</Group>\n            <Password>\n              <Value></Value>\n"
               "              <PlainText>true</PlainText>\n            </Password>\n          </LocalAccount>\n        </LocalAccounts>\n"
               "      </UserAccounts>\n") % (user, user)
        auto = ("      <AutoLogon>\n        <Enabled>true</Enabled>\n        <Username>%s</Username>\n        <Password>\n          <Value></Value>\n"
                "          <PlainText>true</PlainText>\n        </Password>\n        <LogonCount>999</LogonCount>\n      </AutoLogon>\n") % user
    shell_oobe = oobe + acc + auto + "      <TimeZone>%s</TimeZone>\n" % TZ
    x = ['<?xml version="1.0" encoding="utf-8"?>\n',
         "<!-- CloudBlue - MAY MAU VPS ao hoa (%s, ban so %d): tu chia o dia, cai Windows, tao tai khoan khach '%s' (Admin, khong mat khau), "
         "tu dang nhap, SetupComplete.cmd cai driver + QEMU guest agent + phan mem CloudBlue. XOA SACH o dia 0 cua may ao. -->\n" % (p["tag"], idx, user),
         '<unattend xmlns="urn:schemas-microsoft-com:unattend" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">\n',
         '  <settings pass="windowsPE">\n', component("Microsoft-Windows-International-Core-WinPE", pe_lang), component("Microsoft-Windows-Setup", setup), "  </settings>\n",
         '  <settings pass="specialize">\n', component("Microsoft-Windows-Shell-Setup", spec)]
    if not srv: x.append(component("Microsoft-Windows-Deployment", dep))
    x += ["  </settings>\n", '  <settings pass="oobeSystem">\n', component("Microsoft-Windows-International-Core", intl),
          component("Microsoft-Windows-Shell-Setup", shell_oobe), "  </settings>\n", "</unattend>\n"]
    return "".join(x)


# ====================================================================================== diskpart trong WinPE
# Cả 2 kiểu: phân vùng 1 = khởi động (100 MB), phân vùng 2 = Windows (WIN_PART — file trả lời cài thẳng vào Ổ 0 · PHÂN VÙNG 2), gán chữ W để pe.cmd
# chép nhật ký sang. Phân vùng Windows nằm CUỐI ổ (sau này nới ổ cho gói lớn được). 26/11: bỏ "cài vào phân vùng trống đầu tiên"
# (InstallToAvailablePartition) — bộ cài Windows Server 2012 R2 báo "cannot locate the disk and partition" khi thử cài thật.
BIOS_TXT = ("select disk 0\r\nclean\r\ncreate partition primary size=100\r\nformat quick fs=ntfs label=System\r\nactive\r\n"
            "create partition primary\r\nformat quick fs=ntfs label=Windows\r\nassign letter=W\r\nexit\r\n")
UEFI_TXT = ("select disk 0\r\nclean\r\nconvert gpt\r\ncreate partition efi size=100\r\nformat quick fs=fat32 label=System\r\n"
            "create partition primary\r\nformat quick fs=ntfs label=Windows\r\nassign letter=W\r\nexit\r\n")


# ====================================================================================== cb.json
def cb_cfg(p):
    return {"ver": "vm-" + VER, "built": p.get("built") or "", "images": [], "default": "", "user": p["user"], "password": "",
            "timezone": TZ, "sb_url": p.get("sb_url") or "", "sb_key": p.get("sb_key") or "", "wipe_other_disks": False,
            "recovery": False, "generic_key": "off", "user_admin": True, "role": "vm",
            "update_base": p.get("update_base") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/"}


# ====================================================================================== chép file
def copy_tree(src, dst):
    n = 0
    for r, _, fs in os.walk(src):
        rel = os.path.relpath(r, src)
        d = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(d, exist_ok=True)
        for f in fs:
            shutil.copyfile(os.path.join(r, f), os.path.join(d, f)); n += 1
    return n


def driver_dirs(virtio, osdir):
    """{tên driver: thư mục <virtio>\\<driver>\\<os>\\amd64} — chỉ những driver có file .inf cho đúng bản Windows."""
    out = {}
    for d in DRV_NEED + DRV_MORE:
        p = os.path.join(virtio, d, osdir, "amd64")
        if os.path.isdir(p) and any(f.lower().endswith(".inf") for f in os.listdir(p)): out[d] = p
    return out


def layout(P):
    root, tool, osdir = P["iso_root"], P["tool"], P["os"]
    if not os.path.isfile(os.path.join(root, "sources", "boot.wim")): raise ValueError("cay ISO thieu sources\\boot.wim")
    drv = driver_dirs(P["virtio_root"], osdir)
    miss = [d for d in DRV_NEED if d not in drv]
    if miss: raise ValueError("ISO virtio thieu driver %s cho %s (%s) - 2012 R2 dung virtio 0.1.240" % (", ".join(miss), osdir, P["tag"]))
    ga = P["ga_msi"]
    if not os.path.isfile(ga): raise ValueError("thieu bo cai QEMU guest agent: %s" % ga)
    P = dict(P)
    P.setdefault("admin_pw", admin_password())
    # 1. file trả lời + chia ổ trong WinPE
    with open(os.path.join(root, "autounattend.xml"), "w", encoding="utf-8", newline="\r\n") as f: f.write(unattend(P))
    cbvm = os.path.join(root, "cbvm"); os.makedirs(cbvm, exist_ok=True)
    shutil.copyfile(os.path.join(tool, "proxmox", "vm", "pe.cmd"), os.path.join(cbvm, "pe.cmd"))
    for n, t in (("bios.txt", BIOS_TXT), ("uefi.txt", UEFI_TXT)):
        with open(os.path.join(cbvm, n), "w", encoding="ascii", newline="") as f: f.write(t)
    with open(os.path.join(cbvm, "README.txt"), "w", encoding="ascii", newline="") as f:
        f.write("CloudBlue - ISO MAY MAU VPS ao hoa %s (%s). Cai TU DONG va XOA SACH o dia 0 - chi dung cho may ao mau moi tao tren Proxmox.\r\n" % (VER, P["tag"]))
    # 2. driver virtio: $WinPEDriver$ (bộ cài nạp lúc cài + đưa vào kho driver của Windows mới)
    wpd = os.path.join(root, "$WinPEDriver$")
    if os.path.isdir(wpd): shutil.rmtree(wpd)
    for d, src in drv.items(): copy_tree(src, os.path.join(wpd, d))
    # 3. phần mềm CloudBlue → C:\CloudBluePC (bộ cài Windows chép sources\$OEM$\$1 vào ổ C)
    oem = os.path.join(root, "sources", "$OEM$")
    if os.path.isdir(oem): shutil.rmtree(oem)
    cb = os.path.join(oem, "$1", "CloudBluePC")
    copy_tree(P["py_dir"], os.path.join(cb, "py"))
    for sub, files in PAYLOAD.items():
        os.makedirs(os.path.join(cb, sub), exist_ok=True)
        for fn in files: shutil.copyfile(os.path.join(tool, "winpc", sub, fn), os.path.join(cb, sub, fn))
    if P.get("cacert") and os.path.isfile(P["cacert"]): shutil.copyfile(P["cacert"], os.path.join(cb, "os", "cacert.pem"))
    if P.get("ffmpeg") and os.path.isfile(P["ffmpeg"]):
        os.makedirs(os.path.join(cb, "bin"), exist_ok=True); shutil.copyfile(P["ffmpeg"], os.path.join(cb, "bin", "ffmpeg.exe"))
    save(os.path.join(cb, "cb.json"), cb_cfg(P))
    vm = os.path.join(cb, "vm"); os.makedirs(vm, exist_ok=True)
    for fn in VM_FILES: shutil.copyfile(os.path.join(tool, "proxmox", "vm", fn), os.path.join(vm, fn))
    shutil.copyfile(ga, os.path.join(vm, "qemu-ga-x86_64.msi"))
    if P.get("ucrt") and os.path.isfile(P["ucrt"]): shutil.copyfile(P["ucrt"], os.path.join(vm, "ucrt.msu"))
    for d, src in drv.items(): copy_tree(src, os.path.join(vm, "drivers", d))
    save(os.path.join(vm, "maymau.json"), {"ver": VER, "tag": P["tag"], "os": osdir, "server": bool(P["server"]), "user": P["user"],
                                          "image": {k: P["image"].get(k) for k in ("index", "name", "edition", "version")},
                                          "virtio": P.get("virtio_ver") or "", "drivers": sorted(drv), "built": P.get("built") or ""})
    scr = os.path.join(oem, "$$", "Setup", "Scripts"); os.makedirs(scr, exist_ok=True)
    shutil.copyfile(os.path.join(tool, "proxmox", "vm", "SetupComplete.cmd"), os.path.join(scr, "SetupComplete.cmd"))
    say("  ban Windows: %s (so %d) | %s | tai khoan khach %s (Admin, khong mat khau)" % (P["image"].get("name"), int(P["image"]["index"]), P["tag"], P["user"]))
    say("  driver virtio %s (%s): %s + QEMU guest agent%s" % (P.get("virtio_ver") or "?", osdir, " ".join(sorted(drv)), " + ban va Universal C Runtime" if P.get("ucrt") else ""))
    say("  ffmpeg (dieu khien tu xa): %s" % ("kem san" if P.get("ffmpeg") else "KHONG kem - VPS tu tai lan dau dieu khien"))
    return 0


# ====================================================================================== kiểm cây ISO
def check(root):
    need = ["autounattend.xml", "sources\\boot.wim", "cbvm\\pe.cmd", "cbvm\\bios.txt", "cbvm\\uefi.txt",
            "sources\\$OEM$\\$$\\Setup\\Scripts\\SetupComplete.cmd", "sources\\$OEM$\\$1\\CloudBluePC\\cb.json",
            "sources\\$OEM$\\$1\\CloudBluePC\\py\\python.exe", "sources\\$OEM$\\$1\\CloudBluePC\\vm\\maymau.ps1",
            "sources\\$OEM$\\$1\\CloudBluePC\\vm\\maymau.json", "sources\\$OEM$\\$1\\CloudBluePC\\vm\\qemu-ga-x86_64.msi",
            "sources\\$OEM$\\$1\\CloudBluePC\\agent\\pcagent.py", "sources\\$OEM$\\$1\\CloudBluePC\\os\\cb_provision.py",
            "sources\\$OEM$\\$1\\CloudBluePC\\lib\\cbsys.py"]
    miss = [n for n in need if not os.path.isfile(os.path.join(root, *n.split("\\")))]
    if not (os.path.isfile(os.path.join(root, "sources", "install.wim")) or os.path.isfile(os.path.join(root, "sources", "install.esd"))):
        miss.append("sources\\install.wim | install.esd")
    try:
        import xml.dom.minidom
        xml.dom.minidom.parse(os.path.join(root, "autounattend.xml"))
    except Exception as e:
        miss.append("autounattend.xml (khong doc duoc: %s)" % e)
    try:
        mj = load(os.path.join(root, "sources", "$OEM$", "$1", "CloudBluePC", "vm", "maymau.json"))
        for d in DRV_NEED:
            if not os.path.isdir(os.path.join(root, "$WinPEDriver$", d)): miss.append("$WinPEDriver$\\" + d)
        if mj.get("os") == "2k12R2" and not os.path.isfile(os.path.join(root, "sources", "$OEM$", "$1", "CloudBluePC", "vm", "ucrt.msu")):
            miss.append("vm\\ucrt.msu (2012 R2 can ban va Universal C Runtime de chay Python)")
    except Exception as e:
        miss.append("vm\\maymau.json (%s)" % e)
    if os.path.exists(os.path.join(root, "sources", "$OEM$", "$1", "CloudBluePC", "identity.json")): miss.append("CO identity.json (may mau KHONG duoc mang ma may)")
    if miss:
        for m in miss: say("  THIEU / SAI: " + m)
        return 1
    say("  cay ISO du file")
    return 0


# ====================================================================================== ffmpeg
def ff_consts(pcremote_py):
    src = open(pcremote_py, encoding="utf-8").read()
    g = lambda k: re.search(r'^%s\s*=\s*"?([^"\s]+)"?' % k, src, re.M).group(1)
    return g("FF_URL"), int(g("FF_ZIP_SIZE")), g("FF_ZIP_SHA").lower(), g("FF_EXE_SHA").lower()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def ffmpeg(pcremote_py, dst_dir, cache_dir, fetch=None):
    """<dst_dir>\\ffmpeg.exe đúng mã kiểm agent đòi (FF_EXE_SHA). File zip giữ ở <cache_dir> (chạy lại không tải lại). Trả 0 / 1."""
    url, size, zsha, esha = ff_consts(pcremote_py)
    os.makedirs(dst_dir, exist_ok=True); os.makedirs(cache_dir, exist_ok=True)
    exe = os.path.join(dst_dir, "ffmpeg.exe")
    if os.path.isfile(exe) and sha_file(exe) == esha: say("  ffmpeg: da co (dung ma kiem)"); return 0
    z = os.path.join(cache_dir, "ffmpeg.zip")
    if not (os.path.isfile(z) and sha_file(z) == zsha):
        say("  tai ffmpeg (~%d MB) ..." % (size >> 20))
        if fetch: fetch(url, z + ".tmp")
        else:
            import ssl, urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "cloudblue-iso-may-mau/" + VER})
            n = 0
            with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r, open(z + ".tmp", "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b: break
                    n += len(b)
                    if n > size + (1 << 20): raise ValueError("file tai ve lon hon du kien")
                    f.write(b)
        if sha_file(z + ".tmp") != zsha:
            os.remove(z + ".tmp"); say("  ffmpeg: file zip tai ve SAI ma kiem - bo qua"); return 1
        os.replace(z + ".tmp", z)
    with zipfile.ZipFile(z) as zf:
        name = next((x for x in zf.namelist() if x.endswith("/bin/ffmpeg.exe")), None)
        if not name: say("  ffmpeg: file zip khong co bin/ffmpeg.exe"); return 1
        data = zf.read(name)
    if hashlib.sha256(data).hexdigest() != esha: say("  ffmpeg: ffmpeg.exe SAI ma kiem - bo qua"); return 1
    with open(exe + ".new", "wb") as f: f.write(data)
    os.replace(exe + ".new", exe)
    say("  ffmpeg: %d MB, dung ma kiem" % (len(data) >> 20))
    return 0


def main(argv):
    if len(argv) >= 3 and argv[0] == "pick":
        data = load(argv[1])
        r = pick([data] if isinstance(data, dict) else list(data or [])); save(argv[2], r)
        for im in r["images"]:
            say("  %2d. %-55s %-14s %s" % (im["index"], (im.get("name") or "")[:55], im.get("version") or "",
                                          ("-> " + im["tag"] + (" (mac dinh)" if im["index"] == r["default"] else "")) if im["ok"] else "x " + im["why"]))
        return 0 if r["default"] else 1
    if len(argv) >= 4 and argv[0] == "ffmpeg":
        try: return ffmpeg(argv[1], argv[2], argv[3])
        except Exception as e:
            say("  ffmpeg: chua tai duoc (%s)" % str(e)[:200]); return 1
    if len(argv) >= 2 and argv[0] == "layout":
        try: return layout(load(argv[1]))
        except (ValueError, OSError, KeyError) as e:
            say("  LOI: %s" % e); return 1
    if len(argv) >= 2 and argv[0] == "check": return check(argv[1])
    say("vm_build %s - pick <images.json> <out.json> | ffmpeg <pcremote.py> <dich> <tai> | layout <params.json> | check <cay ISO>" % VER)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
