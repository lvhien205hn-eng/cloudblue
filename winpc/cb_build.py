# -*- coding: utf-8 -*-
# =====================================================================================================
#  cb_build.py — phần SẮP XẾP bộ cài (chạy trên máy tạo ISO, do tao-iso.ps1 gọi bằng Python nhúng vừa tải)
#     layout   <params.json>   chép phần mềm CloudBlue + các bản Windows phụ vào cây ISO, ghi cb.json / autounattend.xml / $OEM$
#     manifest <thư mục winpc> <base url> <tên bản>     in bản kê (sha256) để admin công bố bản agent mới
#     check    <cây ISO>       kiểm đủ file trước khi đóng ISO
#  tao-iso.ps1 chỉ lo: tải về, mở ISO gốc, đọc thông tin ảnh, chép cây ISO gốc, chèn boot.wim, đóng ISO (oscdimg).
# =====================================================================================================
import hashlib, json, os, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import cbcore as C                                               # noqa: E402

BUILD_VER = "22.11e"
PAYLOAD = {                                                       # file phần mềm → vị trí trong \cb của bộ cài
    "lib": ["cbsys.py", "cbcore.py", "cbrec.py"],
    "pe": ["cb_pe.py", "start.cmd"],
    "os": ["cb_provision.py", "provision.cmd", "cb_stage.py", "unattend.tpl.xml", "wallpaper.jpg"],
    "agent": ["pcagent.py", "pcremote.py", "watch.cmd", "cbpc.cmd"],
}
UPDATE_DIRS = ("agent", "lib", "os", "pe")
LINUX_PAYLOAD = ["grubx64.efi", "grub.cfg", "cb-install.sh", "cb-post.sh", "cbagent.py"]  # 22.11c (+ agent Linux 22.11e) · CachyOS: GRUB (dựng trên GitHub CI) + menu + bộ cài không người → cb\linux
LINUX_UPDATE_RE = re.compile(r"[A-Za-z0-9_.-]{1,60}\.(sh|cfg|py|service)")       # file Linux agent đẩy lên phân vùng cứu hộ khi admin công bố bản mới (không gồm GRUB)

PE_BLOCK = """  <settings pass="windowsPE">
{LANG}    <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <RunSynchronous>
        <RunSynchronousCommand wcm:action="add">
          <Order>1</Order>
          <Path>cmd.exe /c "for %a in (C D E F G H I J K L M N O P Q R S T U V W Y Z) do @if exist %a:\\cb\\pe\\start.cmd call %a:\\cb\\pe\\start.cmd"</Path>
          <Description>CloudBlue PC</Description>
        </RunSynchronousCommand>
      </RunSynchronous>
      <UserData>
        <AcceptEula>true</AcceptEula>
      </UserData>
    </component>
  </settings>
"""
LANG_BLOCK = """    <component name="Microsoft-Windows-International-Core-WinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <SetupUILanguage>
        <UILanguage>{L}</UILanguage>
      </SetupUILanguage>
      <InputLocale>en-US</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>{L}</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
"""


def say(m): print(m, flush=True)


def setup_lang(root):
    """Ngôn ngữ giao diện của bộ cài gốc (sources\\lang.ini, mục [Available UI Languages]). Không đọc được → ''."""
    try:
        with open(os.path.join(root, "sources", "lang.ini"), encoding="utf-8-sig", errors="replace") as f: txt = f.read()
    except OSError:
        return ""
    m = re.search(r"\[Available UI Languages\]\s*(.*?)(?:\n\s*\[|\Z)", txt, re.S | re.I)
    if not m: return ""
    for ln in m.group(1).splitlines():
        k = ln.split("=")[0].strip()
        if re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z0-9-]{2,8}", k): return k
    return ""


def assign_ids(images):
    """Đặt tên ngắn cho từng bản theo số build: 22h2, 1511… trùng thì thêm -2, -3."""
    seen = {}
    for im in images:
        base = C.os_id(im.get("version"))
        n = seen.get(base, 0) + 1; seen[base] = n
        im["id"] = base if n == 1 else "%s-%d" % (base, n)
    return images


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "0"))[:4])


def make_autounattend(os_tpl, image, cfg, lang):
    """autounattend.xml ở gốc bộ cài: móc gọi bộ cài CloudBlue (dự phòng khi boot.wim chưa được chèn) + phần bỏ màn hình hỏi / cài agent
       cho trường hợp người dùng cài bằng bộ cài Windows thường."""
    body = C.make_unattend(os_tpl, image, dict(cfg, generic_key="off"), "*")     # bộ cài thường: người cài tự chọn phiên bản → KHÔNG điền khoá ở đây
    pe = PE_BLOCK.replace("{LANG}", LANG_BLOCK.replace("{L}", C.xml_esc(lang)) if lang else "")
    i = body.index("<settings ")
    return body[:i] + pe.lstrip() + "  " + body[i:]


# Gói cài VGA NVIDIA: tên gốc kiểu 466.77-notebook-win10-64bit-international-whql.exe, hoặc file tao-iso.ps1 đã nhận ra (hãng NVIDIA) và đánh dấu nvidia-vga-…
NVIDIA_RE = re.compile(r"^(\d{3}\.\d{2}-(notebook|desktop)-.*|nvidia-vga-.*)\.exe$", re.I)
DROP_RE = re.compile(r"^_img(\d+)$", re.I)                         # cb\drivers\_img2 = driver người dùng đưa riêng cho bản Windows của ISO thứ 2


def adopt_driver_drops(cb, images):
    """tao-iso.ps1 chép driver người dùng kéo thả cho bản Windows thứ N vào cb\\drivers\\_img<N> (lúc đó chưa biết tên bản)
       → đổi thành cb\\drivers\\<tên bản> (1511, 22h2…) để bộ cài chỉ nạp khi cài đúng bản đó; thư mục tên bản đã có sẵn (từ cb-them) thì gộp vào.
       Trả {tên bản: số mục đã nhận}."""
    drv, got = os.path.join(cb, "drivers"), {}
    if not os.path.isdir(drv): return got
    for n in sorted(os.listdir(drv)):
        m, src = DROP_RE.match(n), os.path.join(drv, n)
        if not m or not os.path.isdir(src): continue
        k = int(m.group(1))
        if not 1 <= k <= len(images): continue                     # không khớp bản nào: để nguyên (tên lạ → bộ cài nạp cho mọi bản)
        tag = images[k - 1]["id"]
        dst = os.path.join(drv, tag)
        items = sorted(os.listdir(src))
        if not os.path.exists(dst):
            os.rename(src, dst)
        else:
            for f in items:
                stem, ext = os.path.splitext(f)
                to, i = os.path.join(dst, f), 1
                while os.path.exists(to):
                    i += 1; to = os.path.join(dst, "%s_%d%s" % (stem, i, ext))
                shutil.move(os.path.join(src, f), to)
            os.rmdir(src)
        got[tag] = got.get(tag, 0) + len(items)
    return got


def inf_info(path):
    """Đọc phần [Version] của 1 file .inf → (loại driver, hãng), chữ ASCII ngắn: ("Net", "Realtek") · ("Display", "NVIDIA")… Không đọc được → ("", "").
       File .inf có thể là UTF-16 (có / không có BOM), UTF-8 hoặc ANSI."""
    try:
        with open(path, "rb") as f: raw = f.read(8 << 20)
    except OSError:
        return "", ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"): txt = raw.decode("utf-16", "replace")
    elif raw[:3] == b"\xef\xbb\xbf": txt = raw[3:].decode("utf-8", "replace")
    elif b"\x00" in raw[:400]: txt = raw.decode("utf-16-le", "replace")
    else: txt = raw.decode("latin-1")
    cls = prov = sect = ""
    strings = {}
    for line in txt.splitlines():
        t = line.split(";", 1)[0].strip()
        if not t: continue
        if t.startswith("[") and t.endswith("]"):
            sect = t[1:-1].strip().lower(); continue
        if "=" not in t: continue
        k, v = [x.strip() for x in t.split("=", 1)]
        if sect == "version":
            if k.lower() == "class" and not cls: cls = v
            elif k.lower() == "provider" and not prov: prov = v
        elif sect == "strings":
            strings.setdefault(k.lower(), v.strip().strip('"'))
    if len(prov) > 2 and prov.startswith("%") and prov.endswith("%"): prov = strings.get(prov[1:-1].lower(), prov[1:-1])
    clean = lambda t, n: re.sub(r"[^A-Za-z0-9 ._+-]", "", t.strip().strip('"'))[:n].strip()
    return clean(cls, 20), clean(prov, 22)


def driver_kinds(d, deep=True):
    """Tóm tắt loại driver trong 1 thư mục để nhìn khung TÓM TẮT là biết có driver card mạng không:
       'card mang: 2 (rt640x64.inf Realtek; e1d65x64.inf Intel) | VGA: 1 | khac: 3'."""
    net, vga, other = [], 0, 0
    for root, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            if not f.lower().endswith(".inf"): continue
            cls, prov = inf_info(os.path.join(root, f))
            if cls.lower() == "net": net.append((re.sub(r"[^A-Za-z0-9._+-]", "_", f)[:28] + " " + prov).strip())
            elif cls.lower() == "display": vga += 1
            else: other += 1
        if not deep: break
    parts = ["card mang: %d%s" % (len(net), " (" + "; ".join(net[:5]) + ("; ..." if len(net) > 5 else "") + ")" if net else "")]
    if vga: parts.append("VGA: %d" % vga)
    if other: parts.append("khac: %d" % other)
    return " | ".join(parts)


def driver_report(cb):
    """Các dòng tóm tắt driver dạng .inf sẽ được nạp lúc cài, theo từng thư mục cấp 1 của cb\\drivers (gọi SAU khi đã chuyển gói VGA đi). Mỗi dòng ghi kèm loại driver
       (card mạng — kèm tên file + hãng —, VGA, khác) để chủ shop thấy ngay gói driver có phần card mạng hay không.
       Thư mục rỗng thì dọn luôn; thư mục có file mà không có .inf nào → dòng cảnh báo bắt đầu bằng (!)."""
    drv, lines = os.path.join(cb, "drivers"), []
    if not os.path.isdir(drv): return lines

    def count(d):
        files = [f for _, _, fs in os.walk(d) for f in fs]
        return sum(f.lower().endswith(".inf") for f in files), len(files)
    loose = sum(f.lower().endswith(".inf") for f in os.listdir(drv) if os.path.isfile(os.path.join(drv, f)))
    if loose: lines.append("DRIVER (file le trong drivers): %d file .inf [%s] - nap cho moi ban" % (loose, driver_kinds(drv, deep=False)))
    for n in sorted(os.listdir(drv)):
        d = os.path.join(drv, n)
        if not os.path.isdir(d): continue
        ninf, nall = count(d)
        who = ("chi nap khi cai ban %s" % n.lower()) if C.is_os_tag(n) else "nap cho moi ban"
        if ninf: lines.append("DRIVER %s: %d file .inf [%s] - %s" % (n, ninf, driver_kinds(d), who))
        elif nall: lines.append("(!) DRIVER %s: co %d file nhung KHONG co file .inf nao - khong nap duoc" % (n, nall))
        else: shutil.rmtree(d, ignore_errors=True)
    return lines


def place_vga_installers(cb):
    """Gói driver VGA NVIDIA dạng .exe bỏ trong cb\\drivers (hoặc cb\\drivers\\<bản>) KHÔNG nạp kiểu driver được: gói có hàng chục file .inf dùng chung
       ~1GB file, nạp hết thì kho driver của Windows phình hàng chục GB. → chuyển sang os\\firstboot.d[\\<bản>]; ở lần đăng nhập đầu cb_provision.py tự cài
       IM LẶNG (-s -noreboot) SAU KHI máy đã có mạng (driver card mạng xong trước), máy không có card NVIDIA thì bỏ qua; cài xong tự xoá bản chép trên ổ C:
       (phân vùng cứu hộ vẫn giữ để cài lại). Trả danh sách dòng ghi chú."""
    drv, notes = os.path.join(cb, "drivers"), []
    if not os.path.isdir(drv): return notes
    spots = [("", drv)] + [(n, os.path.join(drv, n)) for n in sorted(os.listdir(drv)) if os.path.isdir(os.path.join(drv, n))]
    for sub, folder in spots:
        packs = sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and NVIDIA_RE.match(f))
        if not packs: continue
        tag = sub if (sub and C.is_os_tag(sub)) else ""                # thư mục tên bản Windows (1511…) → chỉ cài trên bản đó; còn lại → mọi bản
        fb = os.path.join(cb, "os", "firstboot.d", tag) if tag else os.path.join(cb, "os", "firstboot.d")
        os.makedirs(fb, exist_ok=True)
        for f in packs:
            dst = os.path.join(fb, f)
            if os.path.exists(dst): os.remove(dst)
            shutil.move(os.path.join(folder, f), dst)
            notes.append("VGA NVIDIA %s: tu cai o lan dang nhap dau, SAU KHI may co mang%s" % (f, (" (chi ban %s)" % tag) if tag else " (moi ban)"))
        old = os.path.join(fb, "50-vga-nvidia.cmd")                    # file lệnh do bộ tạo ISO bản cũ sinh (thư mục làm việc dùng lại) → bỏ, cb_provision tự cài
        try:
            if os.path.isfile(old) and b"cai driver VGA NVIDIA im lang" in open(old, "rb").read(600): os.remove(old)
        except OSError: pass
    return notes


def copy_big(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    total, done, t0, last = max(1, os.path.getsize(src)), 0, time.time(), 0.0
    with open(src, "rb") as fi, open(dst + ".part", "wb") as fo:
        while True:
            b = fi.read(16 << 20)
            if not b: break
            fo.write(b); done += len(b)
            if time.time() - last > 2:
                last = time.time(); say("      %3d%%  %.1f / %.1f GB" % (done * 100 // total, done / 1e9, total / 1e9))
    if os.path.exists(dst): os.remove(dst)
    os.replace(dst + ".part", dst)


def copy_tree(src, dst):
    n = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        to = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(to, exist_ok=True)
        for f in files:
            shutil.copyfile(os.path.join(root, f), os.path.join(to, f)); n += 1
    return n


def add_linux(P, out, tool, out_imgs):
    """22.11c · ISO CachyOS người dùng kéo vào cùng ISO Windows → cb\\linux\\cachyos.iso + GRUB + menu + bộ cài không người, thêm 1 mục kind=linux
       vào CUỐI danh sách (sau mọi bản Windows). P["linux"] = {"src": file .iso, "name", "version"}. Không có → None."""
    L = P.get("linux") or None
    if not L: return None
    src = str(L.get("src") or "")
    if not src.lower().endswith(".iso") or not os.path.isfile(src): raise C.Stop("ISO CachyOS khong hop le: %s" % src)
    d = os.path.join(out, "cb", "linux")
    os.makedirs(d, exist_ok=True)
    for f in LINUX_PAYLOAD:
        p = os.path.join(tool, "linux", f)
        if not os.path.isfile(p): raise C.Stop("Thieu file phan mem: %s" % p)
        shutil.copyfile(p, os.path.join(d, f))
    say("  chep ISO CachyOS (%.1f GB) vao bo cai..." % (os.path.getsize(src) / 1e9))
    copy_big(src, os.path.join(d, "cachyos.iso"))
    ver = re.sub(r"[^0-9A-Za-z._-]", "", str(L.get("version") or ""))[:16]
    im = {"id": "cachyos", "name": str(L.get("name") or "CachyOS Linux (KDE)")[:60], "kind": "linux", "file": "cb\\linux\\cachyos.iso",
          "bytes": os.path.getsize(os.path.join(d, "cachyos.iso")), "version": ver}
    out_imgs.append(im)
    return im


def layout(P):
    """P: out (cây ISO đã chép từ ISO gốc), tool (thư mục winpc đã tải), py (Python nhúng đã giải nén), images [...], user, password,
       sb_url, sb_key, enroll_key."""
    out, tool, py = P["out"], P["tool"], P["py"]
    for need in (os.path.join(out, "sources", "boot.wim"), os.path.join(out, "boot", "boot.sdi"), os.path.join(py, "python.exe"), os.path.join(py, "pythonw.exe")):
        if not os.path.isfile(need): raise C.Stop("Thieu file: %s" % need)
    images = assign_ids([dict(i) for i in P["images"]])
    if not images: raise C.Stop("Khong co ban Windows nao.")
    cb = os.path.join(out, "cb")
    # ---- phần mềm
    for sub, files in PAYLOAD.items():
        os.makedirs(os.path.join(cb, sub), exist_ok=True)
        for f in files:
            src = os.path.join(tool, sub, f)
            if not os.path.isfile(src): raise C.Stop("Thieu file phan mem: %s" % src)
            shutil.copyfile(src, os.path.join(cb, sub, f))
    ca = os.path.join(tool, "os", "cacert.pem")
    if os.path.isfile(ca): shutil.copyfile(ca, os.path.join(cb, "os", "cacert.pem"))
    wp = (P.get("wallpaper") or "").strip()                        # ảnh nền riêng của chủ shop (thay ảnh CloudBlue mặc định)
    if wp:
        ext = wp.rsplit(".", 1)[-1].lower() if "." in os.path.basename(wp) else ""
        ext = {"jpeg": "jpg"}.get(ext, ext)
        if ext not in ("jpg", "png", "bmp") or not os.path.isfile(wp): raise C.Stop("Anh nen rieng phai la file .jpg / .png / .bmp: %s" % wp)
        for old in ("wallpaper.jpg", "wallpaper.png", "wallpaper.bmp"):
            if os.path.exists(os.path.join(cb, "os", old)): os.remove(os.path.join(cb, "os", old))
        shutil.copyfile(wp, os.path.join(cb, "os", "wallpaper." + ext))
        say("  anh nen rieng: %s" % os.path.basename(wp))
    n = copy_tree(py, os.path.join(cb, "py"))
    say("  phan mem CloudBlue + Python nhung (%d file)" % n)
    shutil.copyfile(os.path.join(tool, "CAI-DAT.cmd"), os.path.join(out, "CAI-DAT.cmd"))
    for d, note in (("drivers", "Bo driver (.inf) vao thu muc nay TRUOC khi dong ISO: bo cai se nap vao Windows moi (card mang, card do hoa...).\r\n"),
                    (os.path.join("os", "firstboot.d"), "Bo file .cmd / .bat / .ps1 vao day: se chay 1 LAN o lan dang nhap dau cua Windows moi, theo thu tu ten (vi du 10-driver.cmd).\r\n")):
        os.makedirs(os.path.join(cb, d), exist_ok=True)
        p = os.path.join(cb, d, "doc-toi.txt")
        if not os.path.exists(p):
            with open(p, "w", encoding="ascii", newline="") as f: f.write(note)
    # ---- các bản Windows
    out_imgs = []
    for im in images:
        src = im.pop("src")
        ext = "." + src.rsplit(".", 1)[-1].lower()
        if im.pop("base", False):
            rel = os.path.join("sources", os.path.basename(src))             # bản của ISO gốc nằm sẵn trong cây ISO
            if not os.path.isfile(os.path.join(out, rel)): raise C.Stop("Cay ISO thieu %s" % rel)
        else:
            rel = os.path.join("cb", "images", im["id"] + ext)
            say("  chep ban %s (%s, %.1f GB) vao bo cai..." % (im["id"], im.get("name"), os.path.getsize(src) / 1e9))
            copy_big(src, os.path.join(out, rel))
        im["file"] = rel.replace("/", "\\")
        im["bytes"] = os.path.getsize(os.path.join(out, rel))
        out_imgs.append(im)
    di = P.get("default_index")                                    # tao-iso.ps1: người dùng chọn bản mặc định theo số thứ tự (-1 = bản mới nhất)
    default = P.get("default") or (out_imgs[di]["id"] if isinstance(di, int) and not isinstance(di, bool) and 0 <= di < len(out_imgs) else None) \
        or max(out_imgs, key=lambda i: vkey(i.get("version")))["id"]
    if default not in [i["id"] for i in out_imgs]: raise C.Stop("Ban mac dinh '%s' khong co trong bo cai." % default)
    lin = add_linux(P, out, tool, out_imgs)                         # 22.11c · CachyOS (KHÔNG bao giờ là bản mặc định: cài từ USB luôn là Windows)
    cfg = {"ver": BUILD_VER, "built": time.strftime("%Y-%m-%d %H:%M:%S"), "images": out_imgs, "default": default,
           "user": P.get("user") or "PC", "password": P.get("password") or "", "timezone": P.get("timezone") or "SE Asia Standard Time",
           "sb_url": (P.get("sb_url") or "").rstrip("/"), "sb_key": P.get("sb_key") or "", "countdown": int(P.get("countdown") or 30),
           "wipe_other_disks": bool(P.get("wipe_other_disks")), "recovery": True, "generic_key": C.key_mode({"generic_key": P.get("generic_key", "auto")}),
           "user_admin": P.get("user_admin") is True,             # False (mặc định) = khách dùng TÀI KHOẢN THƯỜNG; True = để khách quyền Admin
           "update_base": P.get("update_base") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/"}
    with open(os.path.join(cb, "cb.json"), "w", encoding="utf-8", newline="") as f: json.dump(cfg, f, ensure_ascii=True, indent=1)
    with open(os.path.join(cb, "media.tag"), "w", encoding="ascii", newline="") as f: f.write("CloudBlue PC %s\r\n" % BUILD_VER)
    key = (P.get("enroll_key") or "").strip()
    kp = os.path.join(cb, "enroll.key")
    if key:
        with open(kp, "w", encoding="ascii", newline="") as f: f.write(key + "\r\n")
    elif os.path.exists(kp): os.remove(kp)
    # ---- file trả lời ở gốc + $OEM$ (để cài bằng bộ cài Windows THƯỜNG vẫn có agent)
    with open(os.path.join(tool, "os", "unattend.tpl.xml"), encoding="utf-8") as f: tpl = f.read()
    dimg = next(i for i in out_imgs if i["id"] == default)
    lang = setup_lang(out)
    with open(os.path.join(out, "autounattend.xml"), "w", encoding="utf-8", newline="") as f: f.write(make_autounattend(tpl, dimg, cfg, lang))
    oem = os.path.join(out, "sources", "$OEM$", "$1", "CloudBluePC")
    if os.path.isdir(oem): shutil.rmtree(oem)
    for sub in ("py", "lib", "agent", "os"): copy_tree(os.path.join(cb, sub), os.path.join(oem, sub))
    with open(os.path.join(oem, "cb.json"), "w", encoding="utf-8", newline="") as f: json.dump(C.recovery_cfg(cfg), f, ensure_ascii=True, indent=1)
    seed = {"from": "setup", "pe": BUILD_VER}
    if key: seed["enroll_key"] = key
    with open(os.path.join(oem, "seed.json"), "w", encoding="utf-8", newline="") as f: json.dump(seed, f)
    say("  ngon ngu bo cai: %s" % (lang or "(khong doc duoc lang.ini - bo cai se hoi ngon ngu neu phai chay bo cai thuong)"))
    info = []
    for im in out_imgs:
        if C.is_linux(im):
            info.append("ANH %s | %s | ISO %s | %.1f GB | chi cai THEO LENH tu web (may UEFI, TAT Secure Boot, can Internet)" % (im["id"], im.get("name"), im.get("version") or "?", im["bytes"] / 1e9))
            continue
        info.append("ANH %s | %s | ban so %s | %s | %.1f GB%s%s" % (im["id"], im.get("name"), im.get("index"), im.get("version"), im["bytes"] / 1e9, " | MAC DINH" if im["id"] == default else "",
                                                                  " | dien khoa cai dat chung" if C.generic_key_for(im, cfg) else ""))
    adopt_driver_drops(cb, out_imgs)                               # _img<N> → tên bản (làm TRƯỚC khi xếp gói VGA + đếm driver)
    vga_notes = place_vga_installers(cb)
    drv = sum(os.path.getsize(os.path.join(r, f)) for d in (os.path.join(cb, "drivers"), os.path.join(cb, "os", "firstboot.d")) for r, _, fs in os.walk(d) for f in fs)
    info.append("CUU_HO %.0f GB | khoa cai dat chung: %s%s | anh nen: %s" % (C.recovery_bytes(cfg, os.path.getsize(os.path.join(out, "sources", "boot.wim")), drv) / C.GB, cfg["generic_key"],
                                                                            (" | driver kem theo: %.0f MB" % (drv / 1e6)) if drv > 4096 else "",
                                                                            "rieng" if wp else "CloudBlue"))
    info.append("KHACH tai khoan '%s' | %s" % (cfg["user"], "quyen ADMIN (khach tu cai duoc moi thu, nhung cung pha duoc phan mem quan ly tren may do)" if cfg["user_admin"]
                                              else "tai khoan THUONG, khong co quyen Admin - thu muc CloudBluePC + phan vung cuu ho khoa quyen"))
    info += vga_notes + driver_report(cb)
    for ln in info: say(ln)
    if P.get("info"):                                              # tao-iso.ps1 in lại các dòng này trong khung TÓM TẮT
        try:
            with open(P["info"], "w", encoding="utf-8", newline="") as f: f.write("\r\n".join(x.encode("ascii", "replace").decode("ascii") for x in info) + "\r\n")
        except OSError: pass
    return cfg


def manifest(root, base, ver):
    files = {}
    for sub in UPDATE_DIRS:
        d = os.path.join(root, sub)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}\.(py|cmd|xml|json|txt|ini)", f): continue
            with open(os.path.join(d, f), "rb") as fh: files["%s/%s" % (sub, f)] = hashlib.sha256(fh.read()).hexdigest()
    lin = {}                                                         # 22.11c · bộ cài CachyOS trên phân vùng cứu hộ (agent 22.11c+ tự thay khi admin công bố bản mới;
    d = os.path.join(root, "linux")                                  #   tách riêng khỏi "files" để agent cũ — chưa biết thư mục linux — vẫn cập nhật được)
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not LINUX_UPDATE_RE.fullmatch(f) or f == "grub-embed.cfg": continue          # grub-embed.cfg: chỉ để dựng grubx64.efi trên CI
        with open(os.path.join(d, f), "rb") as fh: lin["linux/%s" % f] = hashlib.sha256(fh.read()).hexdigest()
    m = {"ver": ver, "base": base.rstrip("/"), "files": files}
    if lin: m["linux"] = lin
    return m


def check(out):
    need = ["sources\\boot.wim", "boot\\boot.sdi", "autounattend.xml", "CAI-DAT.cmd", "cb\\cb.json", "cb\\media.tag", "cb\\py\\python.exe",
            "cb\\pe\\cb_pe.py", "cb\\pe\\start.cmd", "cb\\lib\\cbsys.py", "cb\\lib\\cbcore.py", "cb\\lib\\cbrec.py", "cb\\agent\\pcagent.py", "cb\\agent\\pcremote.py",
            "cb\\os\\cb_provision.py", "cb\\os\\provision.cmd", "cb\\os\\unattend.tpl.xml"]
    miss = [n for n in need if not os.path.isfile(os.path.join(out, *n.split("\\")))]
    try:
        with open(os.path.join(out, "cb", "cb.json"), encoding="utf-8") as f: cfg = json.load(f)
        for im in cfg["images"]:
            if not os.path.isfile(os.path.join(out, *im["file"].split("\\"))): miss.append(im["file"])
            if C.is_linux(im):
                miss += [rel for rel in C.LINUX_FILES if not os.path.isfile(os.path.join(out, *rel.split("\\")))]
        if cfg.get("default") not in [i["id"] for i in C.windows_images(cfg)]: miss.append("cb\\cb.json (ban mac dinh phai la ban Windows)")
    except Exception as e:
        miss.append("cb\\cb.json (%s)" % e)
    for m in miss: say("THIEU " + m)
    say("KIEM_CAY_ISO " + ("DAT" if not miss else "CHUA_DAT"))
    return 0 if not miss else 1


def main(argv):
    try:
        if len(argv) >= 2 and argv[0] == "layout":
            with open(argv[1], encoding="utf-8-sig") as f: P = json.load(f)
            layout(P); return 0
        if len(argv) >= 4 and argv[0] == "manifest":
            print(json.dumps(manifest(argv[1], argv[2], argv[3]), indent=1)); return 0
        if len(argv) >= 2 and argv[0] == "check":
            return check(argv[1])
    except C.Stop as e:
        say("!! DUNG: %s" % e); return 3
    say("cb_build %s — lenh: layout <params.json> | manifest <winpc> <base> <ban> | check <cay ISO>" % BUILD_VER)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
