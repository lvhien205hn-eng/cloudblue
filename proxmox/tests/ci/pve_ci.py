#!/usr/bin/env python3
"""CI (Ubuntu, GitHub Actions, có KVM) cho ISO PROXMOX TỰ CÀI của CloudBlue — gọi qua pve_ci.sh. Không đụng máy thật nào, không gọi web thật
(cbhost trong máy thử gọi 1 web GIẢ chạy ngay trên máy CI).
   ghep  : bộ thử Python → ghép ISO từ ISO Proxmox VE THẬT → soát bằng xorriso + mount + công cụ chính thức của Proxmox
   win   : máy "đang có Windows" (ổ NTFS có \\Windows\\System32\\ntoskrnl.exe) khởi động từ ISO → KHÔNG tự cài, ổ không bị ghi
   bios  : máy BIOS, ISO ghi kiểu USB (DD), ổ SCSI  → tự cài → bật lại (USB vẫn cắm, USB đứng đầu thứ tự khởi động) → kiểm trong máy qua SSH
   uefi  : máy UEFI, ISO dạng ổ CD, ổ NVMe          → như trên
   mang  : lúc cài mạng KHÔNG cấp IPv4 (chỉ có IPv6 — như máy chủ thật ngày 26/11) → cài xong bật lại ở mạng có DHCP: máy phải TỰ xin IPv4
           (cbhost bật dịch vụ cloudblue-dhcp4), tự lên web; phá DNS → lệnh "cbhost.py net" tự đặt lại; khởi động lại vẫn còn mạng
Kết quả: kq/pve-ketqua.txt (dòng OK / XX), ảnh màn hình kq/*.png, nhật ký kq/*.txt."""
import hashlib, json, os, re, shutil, socket, struct, subprocess, sys, time, zlib

W = os.environ.get("W", "/mnt/w")
KQ = os.environ.get("KQ", os.path.join(os.getcwd(), "kq"))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ISO = os.path.join(W, "cb.iso")
PW_HASH = "$6$cbthu2611$f/E0E88wcetQEiEUYlTyWFTUy6Z7TbfRVRumzXvH6Y7PrcDqL/zDnnrZbu/Y3U6C2jgRc7NYkg2APNr17bDyX1"      # mật khẩu thử, chỉ dùng trong máy ảo CI
PORT_WEB = 8765
os.makedirs(KQ, exist_ok=True)


def ok(name, cond, extra=""):
    line = ("OK  " + name) if cond else ("XX  %s: %s" % (name, str(extra).replace("\n", " | ")[:600]))
    print(line, flush=True)
    open(os.path.join(KQ, "pve-ketqua.txt"), "a", encoding="utf-8").write(line + "\n")
    return bool(cond)


def sh(cmd, timeout=600, **kw):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, errors="replace", **kw)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(4 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ppm_to_png(ppm, png):
    d = open(ppm, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", d)
    w, h = int(m.group(1)), int(m.group(2))
    px = d[m.end():]
    raw = b"".join(b"\0" + px[y * w * 3:(y + 1) * w * 3] for y in range(h))
    chunk = lambda t, c: struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c) & 0xffffffff)
    open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class Qmp:
    def __init__(self, path, proc=None):
        self.s = None
        for _ in range(150):
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(path)
                self.s = s
                break
            except OSError:
                if proc is not None and proc.poll() is not None:
                    break
                time.sleep(0.2)
        if self.s is None:
            raise RuntimeError("QEMU không chạy được (không có cổng QMP)")
        self.f = self.s.makefile("rw")
        self.f.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, name, **args):
        self.f.write(json.dumps({"execute": name, "arguments": args}) + "\n")
        self.f.flush()
        while True:
            ln = self.f.readline()
            if not ln:
                return None
            d = json.loads(ln)
            if "return" in d or "error" in d:
                return d


class Vm:
    """1 máy ảo QEMU. iso_as: usb (ISO ghi kiểu DD ra USB) | cd. disk: scsi | nvme | sata."""
    def __init__(self, name, mode, disk, disk_kind, iso_as, iso_first, no_reboot=False, port=2222, disk_fmt="qcow2", usb2=None, net="v4", iso=None, hub=False):
        self.name, self.port = name, port
        self.serial = os.path.join(KQ, "pve-serial-%s.txt" % name)
        self.qmp_p = os.path.join(W, "qmp-%s.sock" % name)
        for p in (self.serial, self.qmp_p):
            if os.path.exists(p):
                os.remove(p)
        a = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "6144", "-smp", "2", "-display", "none", "-vga", "std", "-serial", "file:" + self.serial,
             "-qmp", "unix:%s,server,nowait" % self.qmp_p, "-netdev", ("user,id=n0,ipv4=off,ipv6=on,ipv6-prefix=2001:db8:cb::,ipv6-prefixlen=64" if net == "v6only" else "user,id=n0,hostfwd=tcp:127.0.0.1:%d-:22" % port),
             "-device", "virtio-net-pci,netdev=n0"]                 # net="v6only": mạng KHÔNG có DHCP IPv4, chỉ có IPv6 (quảng bá bộ định tuyến)
        if mode == "uefi":
            vars_f = os.path.join(W, "vars-%s.fd" % name.split("-")[0])
            if not os.path.exists(vars_f):
                shutil.copy("/usr/share/OVMF/OVMF_VARS_4M.fd", vars_f)
            a += ["-machine", "q35", "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", "if=pflash,format=raw,file=" + vars_f]
        else:
            a += ["-machine", "pc"]
        bi_iso, bi_hd = (1, 2) if iso_first else (2, 1)
        if iso_as == "usb":
            a += ["-device", "qemu-xhci,id=xhci", "-drive", "if=none,id=stick,format=raw,readonly=on,file=" + (iso or ISO), "-device", "usb-storage,bus=xhci.0,drive=stick,bootindex=%d" % bi_iso]
        elif iso_as == "cd":
            a += ["-drive", "if=none,id=cd,media=cdrom,format=raw,readonly=on,file=" + (iso or ISO), "-device", "ide-cd,bus=ide.0,drive=cd,bootindex=%d" % bi_iso]
        elif hub:
            a += ["-device", "qemu-xhci,id=xhci"]                    # cổng USB trống: bước thử cắm USB lúc máy ĐANG CHẠY (plug)
        if usb2:
            a += ["-device", "qemu-xhci,id=xhci2", "-drive", "if=none,id=stick2,format=raw,file=" + usb2, "-device", "usb-storage,bus=xhci2.0,drive=stick2"]
        a += ["-drive", "if=none,id=hd0,format=%s,file=%s%s" % (disk_fmt, disk, ",discard=unmap" if disk_fmt == "qcow2" else "")]
        if disk_kind == "scsi":
            a += ["-device", "virtio-scsi-pci,id=sc0", "-device", "scsi-hd,bus=sc0.0,drive=hd0,bootindex=%d" % bi_hd]
        elif disk_kind == "nvme":
            a += ["-device", "nvme,drive=hd0,serial=cbci0001,bootindex=%d" % bi_hd]
        else:
            a += ["-device", "ide-hd,bus=ide.1,drive=hd0,bootindex=%d" % bi_hd]
        if no_reboot:
            a.append("-no-reboot")
        self.qlog = os.path.join(KQ, "pve-qemu-%s.txt" % name)
        self.p = subprocess.Popen(a, stdout=open(self.qlog, "w"), stderr=subprocess.STDOUT)
        try:
            self.q = Qmp(self.qmp_p, self.p)
        except RuntimeError as e:
            self.kill()
            raise RuntimeError("%s: %s | lệnh: %s" % (e, open(self.qlog).read()[-400:].replace("\n", " | "), " ".join(a)[:900]))
        self.t0 = time.time()

    def shot(self, tag):
        ppm = os.path.join(W, "s.ppm")
        try:
            self.q.cmd("screendump", filename=ppm)
            time.sleep(0.4)
            ppm_to_png(ppm, os.path.join(KQ, "pve-%s-%s.png" % (self.name, tag)))
        except Exception as e:
            print("   (không chụp được màn hình: %s)" % e)

    def wait_exit(self, secs, shots=()):
        """Chờ máy tự thoát. shots: [(giây, tên ảnh)]; ngoài ra 2 phút chụp đè ảnh 'moi-nhat' 1 lần."""
        todo = sorted(shots)
        nxt = 120
        while time.time() - self.t0 < secs:
            if self.p.poll() is not None:
                return True
            el = time.time() - self.t0
            while todo and el >= todo[0][0]:
                self.shot(todo.pop(0)[1])
            if el >= nxt:
                self.shot("moi-nhat")
                nxt += 120
            time.sleep(1)
        return self.p.poll() is not None

    def ssh(self, cmd, timeout=60):
        return sh(["ssh", "-i", os.path.join(W, "id"), "-p", str(self.port), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5",
                   "-o", "BatchMode=yes", "-o", "LogLevel=ERROR", "root@127.0.0.1", cmd], timeout=timeout)

    def wait_ssh(self, secs):
        while time.time() - self.t0 < secs and self.p.poll() is None:
            try:
                if self.ssh("true", 15)[0] == 0:
                    return True
            except subprocess.TimeoutExpired:
                pass
            time.sleep(5)
        return False

    def plug(self, tag, path):
        """Cắm 1 USB (file ảnh, chỉ đọc) vào máy ĐANG CHẠY. → lỗi (chữ) hoặc ''"""
        r = self.q.cmd("blockdev-add", **{"node-name": "n" + tag, "driver": "raw", "read-only": True, "file": {"driver": "file", "filename": path, "read-only": True}})
        if not r or "error" in r:
            return "blockdev-add: %s" % r
        r = self.q.cmd("device_add", driver="usb-storage", bus="xhci.0", drive="n" + tag, id="u" + tag)
        return "" if r and "error" not in r else "device_add: %s" % r

    def unplug(self, tag):
        self.q.cmd("device_del", id="u" + tag)
        time.sleep(4)
        self.q.cmd("blockdev-del", **{"node-name": "n" + tag})

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait()

    def serial_txt(self):
        try:
            return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", open(self.serial, "rb").read().decode("latin-1"))
        except OSError:
            return ""


def ghep():
    for t in ("test_pve_iso.py", "test_cbhost.py"):
        rc, out = sh([sys.executable, os.path.join(REPO, "proxmox", "tests", t)], 900)
        ok("bộ thử %s: %s" % (t, out.strip().splitlines()[-1] if out.strip() else "?"), rc == 0, " | ".join(x for x in out.splitlines() if "✗" in x)[:500])
    sh("head -c 40M /dev/urandom > %s/CloudBlue-MayMau-thu1.iso; head -c 300M /dev/urandom > %s/CloudBlue-MayMau-thu2.iso" % (W, W))
    if not os.path.exists(os.path.join(W, "id")):
        sh(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "thu@ci", "-f", os.path.join(W, "id")])
    if os.path.exists(ISO):
        os.remove(ISO)
    env = dict(os.environ, CB_PVE_PW_HASH=PW_HASH)
    t0 = time.time()
    rc, out = sh([sys.executable, os.path.join(REPO, "proxmox", "vm", "pve_iso.py"), "--iso", os.path.join(W, "pve.iso"), "--mau", "%s/CloudBlue-MayMau-thu1.iso,%s/CloudBlue-MayMau-thu2.iso" % (W, W),
                  "--out", ISO, "--khong-hoi", "--ssh-key", open(os.path.join(W, "id.pub")).read().strip(),
                  "--conf", json.dumps({"sb_url": "http://10.0.2.2:%d" % PORT_WEB, "auto_update": False})], 1200, env=env)
    open(os.path.join(KQ, "pve-ghep.txt"), "w").write(out)
    if not ok("ghép ISO từ ISO Proxmox VE thật (%s): mã 0, %.0f giây, có đoạn bảo vệ, bản đã thử (khớp mã kiểm chính thức)" % (open(os.path.join(W, "pve.ver")).read().strip(), time.time() - t0),
              rc == 0 and os.path.exists(ISO) and "bao ve may da co Proxmox / Windows: CO" in out and "chua duoc CloudBlue cai thu" not in out, out[-500:]):
        return 1
    src = os.path.join(W, "pve.iso")
    # (dòng "Boot record" / "System area" / "MBR heads" của xorriso là suy đoán theo cỡ file — ISO do công cụ chính thức của Proxmox tạo cũng đổi y như vậy)
    pick = lambda t: "\n".join(x for x in t.splitlines() if re.match(r"^(El Torito|MBR partition|GPT|APM|Volume id)", x))
    a = pick(sh("xorriso -indev %s -report_el_torito plain -report_system_area plain 2>&1" % src)[1])
    b = pick(sh("xorriso -indev %s -report_el_torito plain -report_system_area plain 2>&1" % ISO)[1])
    ok("xorriso: bản ghi khởi động (El Torito BIOS + UEFI, MBR, GPT, APM) của ISO ghép Y HỆT ISO gốc", a == b and "El Torito boot img :   2  UEFI" in a,
       "\n".join(x for x in b.splitlines() if x not in a.splitlines())[:400])
    rc, cm = sh("cmp -n %d %s %s && cmp -i %d -n %d %s %s" % (16 * 2048, src, ISO, 17 * 2048, 2 * 2048, src, ISO))
    ok("32 KiB đầu (MBR, GPT, APM, mã khởi động) + bản ghi El Torito của ISO ghép giống từng byte ISO gốc", rc == 0, cm[-200:])
    rc, ls = sh("xorriso -indev %s -lsl / 2>&1" % ISO)
    ok("xorriso đọc được cây thư mục, thấy 3 file mới đúng tên", all(("'%s'" % n) in ls for n in ("auto-installer-mode.toml", "answer.toml", "proxmox-first-boot")) and "'pve-installer.squashfs'" in ls, ls[-600:])
    sh("sudo mkdir -p /mnt/a /mnt/b; sudo umount /mnt/a /mnt/b 2>/dev/null; sudo mount -o loop,ro %s /mnt/a && sudo mount -o loop,ro %s /mnt/b" % (src, ISO))
    rc, da = sh("cd /mnt/a && sudo find . -type f -print0 | sort -z | xargs -0 sudo sha256sum", 900)
    rc2, db = sh("cd /mnt/b && sudo find . -type f -print0 | sort -z | xargs -0 sudo sha256sum", 900)
    la, lb = set(da.strip().splitlines()), set(db.strip().splitlines())
    moi = sorted(x.split("  ", 1)[1] for x in lb - la)
    ok("Linux mount: %d file của ISO gốc còn nguyên (so SHA-256 từng file); khác biệt chỉ gồm 3 file mới + grub.cfg" % len(la & lb), rc == 0 and rc2 == 0 and len(la) > 1000
       and moi == ["./answer.toml", "./auto-installer-mode.toml", "./boot/grub/grub.cfg", "./proxmox-first-boot"] and sorted(x.split("  ", 1)[1] for x in la - lb) == ["./boot/grub/grub.cfg"], (moi, len(la), len(lb)))
    g = open("/mnt/b/boot/grub/grub.cfg").read()
    go = open("/mnt/a/boot/grub/grub.cfg").read()
    import importlib.util
    spec = importlib.util.spec_from_file_location("pve_iso", os.path.join(REPO, "proxmox", "vm", "pve_iso.py"))
    pi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pi)
    i0, i1 = g.find(pi.GUARD_MARK), g.find(pi.GUARD_END)
    ok("grub.cfg trong ISO ghép = bản gốc + đoạn CloudBlue chèn ngay trước khối tự cài + 'máy có Windows thì không đếm ngược'", 0 < i0 < i1 and g.count(pi.GUARD_TMO) == 1
       and (g[:i0] + g[i1 + len(pi.GUARD_END):]).replace(pi.GUARD_TMO, "") == go and g[i1 + len(pi.GUARD_END):].startswith("if [ -f auto-installer-mode.toml ]; then"), g[:200])
    shutil.copy("/mnt/b/answer.toml", os.path.join(W, "answer.toml"))
    shutil.copy("/mnt/b/proxmox-first-boot", os.path.join(W, "fb.sh"))
    aim = open("/mnt/b/auto-installer-mode.toml").read()
    sh("sudo umount /mnt/a /mnt/b")
    rc, out = sh("""docker run --rm -v %s:/w debian:trixie bash -c '
      set -e; apt-get update -q >/dev/null; apt-get install -y -q wget ca-certificates xorriso >/dev/null 2>&1
      wget -q https://enterprise.proxmox.com/debian/proxmox-archive-keyring-trixie.gpg -O /usr/share/keyrings/proxmox-archive-keyring.gpg
      printf "Types: deb\\nURIs: http://download.proxmox.com/debian/pve\\nSuites: trixie\\nComponents: pve-no-subscription\\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\\n" > /etc/apt/sources.list.d/pve.sources
      apt-get update -q >/dev/null; apt-get install -y -q proxmox-auto-install-assistant >/dev/null 2>&1
      echo "== validate"; proxmox-auto-install-assistant validate-answer /w/answer.toml
      echo "== prepare"; proxmox-auto-install-assistant prepare-iso /w/pve.iso --fetch-from iso --answer-file /w/answer.toml --on-first-boot /w/fb.sh --output /w/ref.iso >/dev/null
      xorriso -osirrox on -indev /w/ref.iso -extract /auto-installer-mode.toml /w/ref-aim.toml >/dev/null 2>&1; chmod a+r /w/ref-aim.toml; rm -f /w/ref.iso
    ' 2>&1""" % W, 900)
    open(os.path.join(KQ, "pve-chinh-thuc.txt"), "w").write(out)
    ok("công cụ chính thức của Proxmox (proxmox-auto-install-assistant): answer.toml của CloudBlue hợp lệ", "The answer file was parsed successfully, no errors found!" in out, out[-400:])
    ref = open(os.path.join(W, "ref-aim.toml")).read() if os.path.exists(os.path.join(W, "ref-aim.toml")) else None
    ok("auto-installer-mode.toml của CloudBlue giống từng byte file do công cụ chính thức tạo", ref is not None and ref == aim, (ref, aim))
    # Bản "cố định" (ISO máy mẫu giả nội dung cố định, mã kho cố định): job Windows ghép cùng đầu vào → 2 file phải giống nhau từng byte
    sh([sys.executable, os.path.join(HERE, "pve_det.py"), os.path.join(W, "det")])
    det = os.path.join(W, "det.iso")
    envd = dict(os.environ, CB_PVE_PW_HASH=PW_HASH, CB_PVE_KHO_ID="0123456789abcdef01234567")
    rc, out = sh([sys.executable, os.path.join(REPO, "proxmox", "vm", "pve_iso.py"), "--iso", src, "--mau", "%s/det/CloudBlue-MayMau-det1.iso,%s/det/CloudBlue-MayMau-det2.iso" % (W, W),
                  "--out", det, "--khong-hoi", "--ten", "cbvps"], 1200, env=envd)
    if ok("Linux: ghép bản 'cố định' để so với Windows", rc == 0 and os.path.exists(det), out[-300:]):
        open(os.path.join(KQ, "pve-sha-linux.txt"), "w").write("%s %d\n" % (sha(det), os.path.getsize(det)))
        os.remove(det)
    return 0


def fake_web(tag):
    log = os.path.join(KQ, "pve-web-%s.txt" % tag)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "pve_fakeweb.py"), str(PORT_WEB), log])
    time.sleep(1)
    return p, log


def win():
    """Máy đang có Windows: ISO không được tự cài."""
    res = 0
    img = os.path.join(W, "win.img")
    sh("rm -f %s; truncate -s 300M %s && parted -s %s mklabel msdos mkpart primary ntfs 1MiB 100%%" % (img, img, img))
    rc, lo = sh("sudo losetup -fP --show " + img)
    lo = lo.strip().splitlines()[-1] if rc == 0 else ""
    rc, out = sh("sudo mkfs.ntfs -Q -F %sp1 && sudo mkdir -p /mnt/x && sudo mount %sp1 /mnt/x && sudo mkdir -p /mnt/x/Windows/System32 && echo gia | sudo tee /mnt/x/Windows/System32/ntoskrnl.exe >/dev/null"
                 " && sudo umount /mnt/x; sudo losetup -d %s" % (lo, lo, lo))
    if not ok("dựng ổ 'Windows' giả (NTFS có \\Windows\\System32\\ntoskrnl.exe)", rc == 0 and lo, out[-300:]):
        return 1
    for mode, iso_as in (("bios", "usb"), ("uefi", "cd")):
        h0 = sha(img)
        try:
            vm = Vm("win-" + mode, mode, img, "sata", iso_as, True, disk_fmt="raw")
        except RuntimeError as e:
            ok("máy đang có Windows (%s): chạy được máy thử" % mode.upper(), False, e)
            res = 1
            continue
        vm.wait_exit(18)
        vm.shot("menu")
        vm.wait_exit(75)
        vm.shot("sau-70-giay")
        alive = vm.p.poll() is None
        vm.kill()
        s = vm.serial_txt()
        ok("máy đang có Windows (%s, ISO dạng %s): menu có dòng 'dang co WINDOWS - KHONG tu cai', sau 70 giây vẫn KHÔNG tự cài (không nạp kernel cài đặt), ổ Windows không bị ghi 1 byte" % (mode.upper(), iso_as.upper()),
           "dang co WINDOWS" in s and "Loading Proxmox VE Automatic Installer" not in s and "Install Proxmox VE (Automated)" in s and alive and sha(img) == h0
           and "Failed to boot" not in s,
           (alive, sha(img) == h0, s[-300:])) or (res := 1)
    return res


REMOTE = r"""
echo "#cmdline $(cat /proc/cmdline)"
echo "#host $(hostname) | $(pveversion 2>&1 | head -1)"
for i in $(seq 1 90); do [ -f /var/lib/cloudblue/nap-xong.json ] && break; sleep 4; done
echo "#fb"; cat /var/log/cloudblue-firstboot.log 2>&1
echo "#pending"; ls /var/lib/proxmox-first-boot/ 2>&1
echo "#nap"; cat /var/lib/cloudblue/nap-xong.json 2>&1; echo; journalctl -u cloudblue-nap --no-pager 2>&1 | tail -15
echo "#iso"; ls -l /var/lib/vz/template/iso/ 2>&1; sha256sum /var/lib/vz/template/iso/*.iso 2>&1
echo "#conf"; cat /etc/cloudblue/cbhost.conf 2>&1; echo; cat /etc/cloudblue/nap.json; echo; stat -c '%a %n' /etc/cloudblue /etc/cloudblue/cbhost.conf /etc/cloudblue/cbhost.secret 2>&1
echo "#units $(systemctl is-active cloudblue-cbhost) $(systemctl is-enabled cloudblue-cbhost) $(systemctl is-enabled cloudblue-nap)"
for i in $(seq 1 40); do qm config 99500 >/dev/null 2>&1 && qm config 99501 >/dev/null 2>&1 && break; sleep 5; done
sleep 8
echo "#qm"; qm list 2>&1; echo "--99500"; qm config 99500 2>&1; echo "--99501"; qm config 99501 2>&1 | head -5
echo "#cbhost $(python3 /opt/cloudblue/cbhost.py version)"; journalctl -u cloudblue-cbhost --no-pager 2>&1 | tail -25
echo "#status"; python3 /opt/cloudblue/cbhost.py status 2>&1
echo "#disk"; lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>&1; df -h / /var/lib/vz 2>&1
echo "#net"; cat /etc/network/interfaces 2>&1; ip -4 -o a 2>&1
echo "#kvm $(ls /dev/kvm 2>&1)"
echo "#het"
"""


def cai(mode, iso_as, disk_kind):
    """Cài thật + bật lại + kiểm trong máy."""
    res = 0
    disk = os.path.join(W, "d-%s.qcow2" % mode)
    for p in (disk, os.path.join(W, "vars-%s.fd" % mode)):
        if os.path.exists(p):
            os.remove(p)
    sh(["qemu-img", "create", "-f", "qcow2", disk, "48G"])
    web, weblog = fake_web(mode)
    lab = "%s, ISO dạng %s, ổ %s" % (mode.upper(), iso_as.upper(), disk_kind.upper())
    try:
        vm = Vm(mode + "-cai", mode, disk, disk_kind, iso_as, True, no_reboot=True)
        done = vm.wait_exit(1800, [(7, "menu"), (50, "50-giay"), (240, "4-phut")])
        mins = (time.time() - vm.t0) / 60
        if not done:
            vm.shot("TREO")
        vm.kill()
        s = vm.serial_txt()
        rc, qi = sh(["qemu-img", "info", "--output", "json", disk])
        used = json.loads(qi).get("actual-size", 0) if rc == 0 else 0
        if not ok("TỰ CÀI (%s): menu có dòng tự cài, không cần bấm phím nào, cài xong tự khởi động lại sau %.1f phút, ổ cứng đã có dữ liệu (%.1f GB)" % (lab, mins, used / 2**30),
                  done and "Install Proxmox VE (Automated)" in s and "Loading Proxmox VE Automatic Installer" in s and used > 2 * 2**30 and "DA CO Proxmox" not in s, (done, used, s[-300:])):
            return 1
        vm = Vm(mode + "-bat", mode, disk, disk_kind, iso_as, True)
        vm.wait_exit(9)
        vm.shot("menu")
        up = vm.wait_ssh(480)
        if not up:
            vm.shot("KHONG-LEN")
        s = vm.serial_txt()
        ok("BẬT LẠI với %s còn cắm và đứng ĐẦU thứ tự khởi động (%s): menu báo 'may nay DA CO Proxmox', KHÔNG cài lại, máy lên, vào được SSH bằng khoá thử" % (iso_as.upper(), mode.upper()),
           up and "DA CO Proxmox" in s and "Loading Proxmox VE Automatic Installer" not in s and "khoi dong Proxmox da cai tren o cung" in s, (up, s[-400:])) or (res := 1)
        if not up:
            vm.kill()
            return 1
        rc, out = vm.ssh(REMOTE, 1500)
        open(os.path.join(KQ, "pve-may-%s.txt" % mode), "w").write(out)
        sec = lambda k: (re.search(r"^#%s(.*?)(?=^#[a-z]+)" % k, out, re.S | re.M) or [None, ""])[1]
        ok("máy vừa bật là hệ đã cài trên ổ cứng, khởi động qua mục bảo vệ của ISO (kernel của hệ đã cài, root=/dev/mapper/pve-root)", "root=/dev/mapper/pve-root" in sec("cmdline")
           and "ramdisk_size=16777216" in sec("cmdline") and "proxmox-start-auto-installer" not in sec("cmdline"), sec("cmdline")) or (res := 1)
        ok("Proxmox VE đã cài: tên máy cbvps, có pve-manager", re.search(r"cbvps \| pve-manager/9\.", sec("host")), sec("host")) or (res := 1)
        fb = sec("fb")
        ok("script lần bật đầu đã chạy xong, không lỗi, Proxmox đã gỡ dấu 'chờ chạy lần đầu'", "xong first-boot: cbhost 26/" in fb and "LOI" not in fb and "pending-first-boot-setup" not in sec("pending")
           and "proxmox-first-boot" in sec("pending"), (fb[-300:], sec("pending"))) or (res := 1)
        want = {n: sha(os.path.join(W, n)) for n in ("CloudBlue-MayMau-thu1.iso", "CloudBlue-MayMau-thu2.iso")}
        iso_s = sec("iso")
        ok("kho ISO máy mẫu đã được chép từ %s vào /var/lib/vz/template/iso, SHA-256 khớp cả 2 file, dịch vụ nạp ghi dấu xong" % ("USB (đọc thẳng thiết bị)" if iso_as == "usb" else "ổ CD (/dev/sr0)"),
           all(("%s  /var/lib/vz/template/iso/%s" % (h, n)) in iso_s for n, h in want.items()) and '"note": "đủ"' in sec("nap").replace("\\u0111\\u1ee7", "đủ"), (iso_s[-400:], sec("nap")[-300:])) or (res := 1)
        cf = sec("conf")
        ok("cấu hình cbhost: tự dựng máy mẫu BẬT, tên riêng cbvps-<4 số MAC>; thư mục / file cấu hình + mã riêng của máy chỉ root đọc", '"auto_tpl": true' in cf
           and re.search(r'"host_name": "cbvps-[0-9a-f]{4}"', cf) and "700 /etc/cloudblue" in cf and "600 /etc/cloudblue/cbhost.conf" in cf and "600 /etc/cloudblue/cbhost.secret" in cf, cf[-400:]) or (res := 1)
        ok("dịch vụ cloudblue-cbhost đang chạy + tự chạy khi bật máy", sec("units").strip().startswith("active enabled"), sec("units")) or (res := 1)
        qm = sec("qm")
        ok("cbhost TỰ dựng máy mẫu trên Proxmox thật: lệnh qm create được Proxmox %s nhận — máy ảo cbmau-thu1 / thu2 (số 99500, 99501), gắn đúng ISO, ổ SCSI VirtIO 20 GB, mạng VirtIO vmbr0, có QEMU agent"
           % open(os.path.join(W, "pve.ver")).read().strip(),
           re.search(r"name: cbmau-thu[12]", qm) and re.search(r"ide2: local:iso/CloudBlue-MayMau-thu[12]\.iso,media=cdrom", qm) and re.search(r"scsi0: local-lvm:vm-9950[01]-disk-0,.*size=20G", qm)
           and "scsihw: virtio-scsi-single" in qm and re.search(r"net0: virtio=[0-9A-F:]+,bridge=vmbr0", qm) and "agent: enabled=1" in qm and "ostype: win10" in qm
           and "cbmau-thu1" in qm and "cbmau-thu2" in qm, qm[-900:]) or (res := 1)
        wl = open(weblog).read() if os.path.exists(weblog) else ""
        ok("máy chủ tự gọi web (web giả của CI): vm_host_hello với tên cbvps-xxxx, bản cbhost %s, rồi hỏi việc đều (vm_host_poll) kèm danh sách ISO + tiến độ tự dựng máy mẫu" % cb_ver(),
           re.search(r'vm_host_hello .*"host": "cbvps-[0-9a-f]{4}"', wl) and ('"ver": "%s"' % cb_ver()) in wl and "vm_host_poll" in wl and "CloudBlue-MayMau-thu1.iso" in wl and "tpl_auto" in wl, wl[-500:]) or (res := 1)
        dk = sec("disk")
        ok("ổ cài đúng ổ cứng của máy (%s), không phải USB cài đặt; mạng: IP tĩnh lấy từ DHCP lúc cài, có cầu vmbr0" % ("nvme0n1" if disk_kind == "nvme" else "sdX"),
           re.search(r"(nvme0n1|sd[a-z])\d+ .*LVM2_member|pve-root", dk) and ("nvme0n1p3" in dk if disk_kind == "nvme" else True) and "iface vmbr0 inet static" in sec("net") and "10.0.2.15/24" in sec("net"),
           (dk[-400:], sec("net")[-300:])) or (res := 1)
        if mode == "bios":
            vm.ssh("systemctl disable --now cloudblue-cbhost; qm stop 99501; rm -f /var/lib/cloudblue/nap-xong.json /var/lib/vz/template/iso/CloudBlue-MayMau-thu2.iso; sync", 120)
        vm.ssh("poweroff", 30)
        vm.wait_exit(time.time() - vm.t0 + 120)
        vm.kill()
        if mode == "bios":
            res |= ventoy(disk, disk_kind, want)
    finally:
        web.terminate()
    return res


def cb_ver():
    m = re.search(r'^CBHOST_VER = "([^"]+)"', open(os.path.join(REPO, "proxmox", "cbhost.py"), encoding="utf-8").read(), re.M)
    return m.group(1) if m else "?"


def mo_o(disk, tag):
    """Mổ ổ của máy thử (máy đang TẮT): gắn chỉ đọc phân vùng gốc (LVM pve/root) → chép cấu hình mạng + nhật ký ra kq/pve-mo-<tag>.txt. → chữ đọc được."""
    sh("sudo apt-get install -y -q lvm2 >/dev/null 2>&1; sudo modprobe nbd max_part=16", 300)
    out = sh("""sudo qemu-nbd -d /dev/nbd0 >/dev/null 2>&1; sudo qemu-nbd -r -c /dev/nbd0 @DISK@ && sleep 2 && sudo partprobe /dev/nbd0; sleep 2; sudo vgscan >/dev/null 2>&1; sudo vgchange -ay pve >/dev/null 2>&1; sleep 1
      sudo mkdir -p /mnt/r && sudo mount -o ro,noload /dev/pve/root /mnt/r && {
        for f in /etc/network/interfaces /etc/network/interfaces.cb-goc /etc/resolv.conf /etc/resolv.conf.cb-goc /etc/hosts; do echo "#file $f"; sudo cat /mnt/r$f 2>&1; done
        echo "#dhclient $(for b in /usr/sbin/dhclient /usr/sbin/ifreload /usr/sbin/dhcpcd /usr/bin/busybox; do [ -e /mnt/r$b ] && printf '%s ' $b; done)"
        echo "#fb"; sudo cat /mnt/r/var/log/cloudblue-firstboot.log 2>&1 | tail -20
        echo "#journal"; sudo journalctl --directory=/mnt/r/var/log/journal --no-pager -u cloudblue-cbhost -u networking 2>&1 | tail -80
        echo "#het"
      }
      sudo umount /mnt/r 2>/dev/null; sudo vgchange -an pve >/dev/null 2>&1; sudo qemu-nbd -d /dev/nbd0 >/dev/null 2>&1""".replace("@DISK@", disk), 300)[1]
    open(os.path.join(KQ, "pve-mo-%s.txt" % tag), "w").write(out)
    return out


REMOTE_NET = r"""
echo "#if"; cat /etc/network/interfaces 2>&1
echo "#goc"; cat /etc/network/interfaces.cb-goc 2>&1
echo "#ip4"; ip -4 -o a 2>&1; ip -4 route 2>&1
echo "#ip6"; ip -6 -o a 2>&1 | grep -v ' lo ' ; ip -6 route show default 2>&1
echo "#rs"; cat /etc/resolv.conf 2>&1
echo "#bin $(command -v dhclient) | $(pgrep -a dhclient | head -2 | tr '
' ' ')"
echo "#unit $(systemctl is-active cloudblue-dhcp4 2>&1) $(systemctl is-enabled cloudblue-dhcp4 2>&1) | $(grep ExecStart /etc/systemd/system/cloudblue-dhcp4.service 2>&1)"
echo "#log"; journalctl -b -u cloudblue-cbhost --no-pager 2>&1 | tail -40
echo "#status"; python3 /opt/cloudblue/cbhost.py status 2>&1 | head -8
echo "#het"
"""


def mang():
    """Như máy chủ thật 26/11: lúc cài mạng không cấp IPv4 → bộ cài Proxmox chỉ đặt IPv6. Bật lại ở mạng có DHCP: cbhost phải TỰ sửa (bật dịch vụ xin DHCP), tự lên web."""
    res = 0
    disk = os.path.join(W, "d-mang.qcow2")
    if os.path.exists(disk):
        os.remove(disk)
    sh(["qemu-img", "create", "-f", "qcow2", disk, "48G"])
    web, weblog = fake_web("mang")
    sec = lambda out, k: (re.search(r"^#%s(.*?)(?=^#[a-z0-9]+)" % k, out, re.S | re.M) or [None, ""])[1]
    try:
        vm = Vm("mang-cai", "bios", disk, "scsi", "usb", True, no_reboot=True, net="v6only")
        done = vm.wait_exit(1800, [(7, "menu"), (240, "4-phut")])
        mins = (time.time() - vm.t0) / 60
        if not done:
            vm.shot("TREO")
        vm.kill()
        s = vm.serial_txt()
        if not ok("mạng CHỈ CÓ IPv6 lúc cài (không DHCP IPv4 — như máy chủ thật 26/11): vẫn TỰ CÀI xong sau %.1f phút" % mins, done and "Loading Proxmox VE Automatic Installer" in s, (done, s[-300:])):
            return 1
        mo = mo_o(disk, "mang-sau-cai")
        fi = (re.search(r"#file /etc/network/interfaces\n(.*?)#file ", mo, re.S) or [None, ""])[1]
        rs0 = (re.search(r"#file /etc/resolv.conf\n(.*?)#file ", mo, re.S) or [None, ""])[1]
        ok("bộ cài Proxmox khi đó CHỈ đặt IPv6 cho cầu vmbr0 (đúng lỗi của máy thật): có 'iface vmbr0 inet6 static', KHÔNG có dòng IPv4 nào cho vmbr0 · DNS bộ cài ghi: %s"
           % (", ".join(re.findall(r"nameserver\s+(\S+)", rs0)) or "?"), "iface vmbr0 inet6 static" in fi and not re.search(r"^iface vmbr0 inet\s", fi, re.M), fi[-400:]) or (res := 1)
        ok("máy cài bằng ISO có sẵn dhclient (cbhost dùng để xin IPv4)", "/usr/sbin/dhclient" in sec(mo, "dhclient"), sec(mo, "dhclient")) or (res := 1)
        ip6 = (re.search(r"^\s*address\s+([0-9a-f:]+)/\d+", fi, re.M) or [None, "?"])[1]
        vm = Vm("mang-bat", "bios", disk, "scsi", "usb", True)                     # mạng lần này có DHCP IPv4; SSH của bộ thử đi qua IPv4 → chỉ vào được khi máy TỰ xin được IPv4
        up = vm.wait_ssh(600)
        t_up = time.time() - vm.t0
        if not up:
            vm.shot("KHONG-LEN")
            vm.kill()
            mo2 = mo_o(disk, "mang-khong-len")
            ok("BẬT LẠI ở mạng có DHCP: máy TỰ xin IPv4 (vào được SSH qua IPv4)", False, mo2[-900:])
            return 1
        time.sleep(20)
        vm.shot("man-hinh")                                                        # màn hình máy chủ phải có dòng [CloudBlue …] CHUA goi duoc web … / tu sua mang … / DA LEN WEB …
        rc, out = vm.ssh(REMOTE_NET, 300)
        open(os.path.join(KQ, "pve-may-mang.txt"), "w").write(out)
        fi2, goc, lg = sec(out, "if"), sec(out, "goc"), sec(out, "log")
        ok("BẬT LẠI ở mạng có DHCP: không ai gõ gì, sau %.0f giây máy đã TỰ có IPv4 (10.0.2.15 trên vmbr0, vào được SSH qua IPv4)" % t_up, "10.0.2.15/24" in sec(out, "ip4") and "vmbr0" in sec(out, "ip4")
           and re.search(r"^default via 10\.0\.2\.2", sec(out, "ip4"), re.M), sec(out, "ip4")) or (res := 1)
        un = sec(out, "unit")
        ok("cbhost tự sửa mà KHÔNG sửa file mạng của Proxmox (interfaces giống hệt bản bộ cài viết); dịch vụ cloudblue-dhcp4 đang chạy + tự bật cùng máy (dhclient -4 -d … vmbr0); địa chỉ IPv6 tĩnh %s vẫn còn" % ip6,
           fi2.strip() == fi.strip() and "No such file" in goc and un.strip().startswith("active enabled") and re.search(r"ExecStart=/usr/sbin/dhclient -4 -d .* vmbr0", un) and ip6 != "?" and ip6 in sec(out, "ip6"),
           (fi2[-300:], un, sec(out, "ip6")[-300:])) or (res := 1)
        ok("nhật ký cbhost: 'chưa lên web được' → 'TỰ SỬA MẠNG … cloudblue-dhcp4 … ĐÃ có IPv4' → 'đã lên web'; dhclient đang chạy cho vmbr0", "TỰ SỬA MẠNG" in lg and "cloudblue-dhcp4" in lg and "ĐÃ có IPv4" in lg and "đã lên web" in lg
           and lg.index("TỰ SỬA MẠNG") < lg.rindex("đã lên web") and "dhclient" in sec(out, "bin") and "vmbr0" in sec(out, "bin"), (lg[-600:], sec(out, "bin"))) or (res := 1)
        wl = open(weblog).read() if os.path.exists(weblog) else ""
        ok("web (giả của CI) nhận vm_host_hello của máy này sau khi nó tự sửa mạng (bản cbhost %s); lệnh status báo 'IPv4 có'" % cb_ver(), "vm_host_hello" in wl and ('"ver": "%s"' % cb_ver()) in wl
           and "IPv4 có" in sec(out, "status"), (wl[-300:], sec(out, "status"))) or (res := 1)
        # DNS hỏng (192.168.100.1 — số bộ cài tự điền khi không xin được gì): lệnh net (= việc dịch vụ tự làm) phải đặt lại và phân giải được thật
        rc, out2 = vm.ssh("""cp /etc/resolv.conf /root/rs.bak; printf 'search lan\nnameserver 192.168.100.1\n' > /etc/resolv.conf
            printf '{"sb_url": "https://github.com", "auto_tpl": true}' > /root/c2.json
            echo "#truoc $(getent hosts github.com | head -1)"; echo "#net"; CBHOST_CONF=/root/c2.json python3 /opt/cloudblue/cbhost.py net 2>&1
            echo "#rs"; cat /etc/resolv.conf; echo "#sau $(getent hosts github.com | head -1)"; echo "#goc"; cat /etc/resolv.conf.cb-goc; echo "#het"; rm -f /root/c2.json""", 180)
        open(os.path.join(KQ, "pve-may-mang-dns.txt"), "w").write(out2)
        ok("DNS bị đặt 192.168.100.1 (không phân giải được) → 'cbhost.py net' đặt lại máy chủ tên công cộng, giữ dòng search, lưu bản gốc; ngay sau đó máy phân giải được tên miền thật",
           sec(out2, "truoc").strip() == "" and "nameserver 8.8.8.8" in sec(out2, "rs") and "search lan" in sec(out2, "rs") and "192.168.100.1" not in sec(out2, "rs")
           and re.search(r"\d+\.\d+\.\d+\.\d+\s+github\.com", sec(out2, "sau")) and "192.168.100.1" in sec(out2, "goc") and "đã sửa: đặt lại máy chủ tên" in sec(out2, "net"), out2[-700:]) or (res := 1)
        # khởi động lại: cấu hình mới phải tự chạy (không cần cbhost sửa lần nữa)
        rc, b0 = vm.ssh("cat /proc/sys/kernel/random/boot_id", 30)
        try:
            vm.ssh("cp /root/rs.bak /etc/resolv.conf; qm stop 99500 >/dev/null 2>&1; qm stop 99501 >/dev/null 2>&1; sync; systemctl reboot", 180)
        except subprocess.TimeoutExpired:
            pass
        up2, t1 = False, time.time()
        while time.time() - t1 < 600 and vm.p.poll() is None:              # chờ tới khi máy lên lại bằng LẦN BẬT MỚI (mã lần bật khác trước)
            time.sleep(8)
            try:
                rc, b1 = vm.ssh("cat /proc/sys/kernel/random/boot_id", 15)
            except subprocess.TimeoutExpired:
                continue
            if rc == 0 and b1.strip() and b1.strip() != b0.strip():
                up2 = True
                break
        if up2:
            time.sleep(50)                                                  # cho cbhost kịp gọi web
        rc, out3 = vm.ssh(REMOTE_NET, 300) if up2 else (1, "không vào được SSH sau khi khởi động lại")
        open(os.path.join(KQ, "pve-may-mang-2.txt"), "w").write(out3)
        ok("KHỞI ĐỘNG LẠI: máy tự có IPv4 ngay từ lúc bật (dịch vụ cloudblue-dhcp4 tự chạy), IPv6 tĩnh vẫn còn, cbhost lên web mà không phải sửa gì nữa; file mạng vẫn nguyên như bộ cài viết",
           up2 and "10.0.2.15/24" in sec(out3, "ip4") and "đã lên web" in sec(out3, "log") and "TỰ SỬA MẠNG" not in sec(out3, "log") and sec(out3, "if").strip() == fi.strip()
           and sec(out3, "unit").strip().startswith("active enabled") and ip6 in sec(out3, "ip6"), (up2, sec(out3, "ip4")[-200:], sec(out3, "unit"), sec(out3, "log")[-400:])) or (res := 1)
        vm.ssh("poweroff", 30)
        vm.wait_exit(time.time() - vm.t0 + 120)
        vm.kill()
    finally:
        web.terminate()
    return res


def usb():
    """Như máy chủ thật 26/11 lần 2: cài bằng USB ghép THIẾU máy mẫu → máy lên web nhưng không có ISO nào. Cắm USB bản ĐỦ (rồi USB thường có file ISO) vào máy ĐANG CHẠY:
    cbhost phải tự chép vào kho ISO và tự dựng máy mẫu — KHÔNG cài lại."""
    res = 0
    disk = os.path.join(W, "d-usb.qcow2")
    if os.path.exists(disk):
        os.remove(disk)
    sh(["qemu-img", "create", "-f", "qcow2", disk, "48G"])
    iso0 = os.path.join(W, "cb-khong-mau.iso")
    rc, out = sh([sys.executable, os.path.join(REPO, "proxmox", "vm", "pve_iso.py"), "--iso", os.path.join(W, "pve.iso"), "--khong-mau", "--out", iso0, "--khong-hoi",
                  "--ssh-key", open(os.path.join(W, "id.pub")).read().strip(), "--conf", json.dumps({"sb_url": "http://10.0.2.2:%d" % PORT_WEB, "auto_update": False})],
                 1200, env=dict(os.environ, CB_PVE_PW_HASH=PW_HASH))
    if not ok("ghép 1 ISO KHÔNG kèm máy mẫu (-KhongMau) để dựng lại đúng tình huống máy thật", rc == 0 and os.path.exists(iso0) and "may mau kem: khong" in out, out[-400:]):
        return 1
    rc, out = sh([sys.executable, os.path.join(REPO, "proxmox", "vm", "pve_iso.py"), "--iso", os.path.join(W, "pve.iso"), "--out", iso0 + ".x", "--khong-hoi", "--work", os.path.join(W, "trong"),
                  "--ssh-key", open(os.path.join(W, "id.pub")).read().strip()], 600, env=dict(os.environ, CB_PVE_PW_HASH=PW_HASH, HOME=os.path.join(W, "nha-trong")), cwd=KQ)
    ok("lệnh ghép KHÔNG tìm thấy ISO máy mẫu mà không ghi -KhongMau → DỪNG (mã 1), không ra file ISO thiếu máy mẫu",
       rc == 1 and "KHONG THAY file ISO may mau nao" in out and not os.path.exists(iso0 + ".x"), out[-400:]) or (res := 1)
    web, weblog = fake_web("usb")
    sec = lambda out, k: (re.search(r"^#%s(.*?)(?=^#[a-z0-9]+)" % k, out, re.S | re.M) or [None, ""])[1]
    XEM = r"""echo "#iso"; ls -l /var/lib/vz/template/iso/ 2>&1; sha256sum /var/lib/vz/template/iso/*.iso 2>/dev/null
echo "#nap"; cat /var/lib/cloudblue/nap-xong.json 2>&1; echo
echo "#qm"; qm list 2>&1
echo "#blk"; lsblk -o NAME,TRAN,RM,FSTYPE,SIZE,MOUNTPOINT 2>&1
echo "#mnt $(mount | grep -c cloudblue-usb)"
echo "#log"; journalctl -b -u cloudblue-cbhost --no-pager 2>&1 | grep -i "usb" | tail -20
echo "#het"
"""
    try:
        vm = Vm("usb-cai", "bios", disk, "scsi", "usb", True, no_reboot=True, iso=iso0)
        done = vm.wait_exit(1800, [(240, "4-phut")])
        mins = (time.time() - vm.t0) / 60
        if not done:
            vm.shot("TREO")
        vm.kill()
        if not ok("cài Proxmox bằng USB THIẾU máy mẫu: tự cài xong sau %.1f phút" % mins, done and "Loading Proxmox VE Automatic Installer" in vm.serial_txt(), vm.serial_txt()[-300:]):
            return 1
        vm = Vm("usb-bat", "bios", disk, "scsi", "none", False, hub=True)        # rút USB cài đặt ra; máy có 1 cổng USB trống
        up = vm.wait_ssh(480)
        if not up:
            vm.shot("KHONG-LEN")
            ok("máy cài bằng USB thiếu máy mẫu: lên, vào được SSH", False, vm.serial_txt()[-300:])
            return 1
        time.sleep(45)
        rc, o0 = vm.ssh(XEM, 120)
        open(os.path.join(KQ, "pve-may-usb-0.txt"), "w").write(o0)
        ok("đúng tình huống máy thật: máy lên, cbhost chạy, kho ISO TRỐNG, dịch vụ nạp ghi 'không có kho', chưa có máy ảo nào", "total 0" in sec(o0, "iso") and "không có kho" in sec(o0, "nap")
           and "cbmau-" not in sec(o0, "qm"), (sec(o0, "iso"), sec(o0, "nap"), sec(o0, "qm"))) or (res := 1)
        # ---- cắm USB cài đặt bản ĐỦ vào máy đang chạy
        e = vm.plug("du", ISO)
        want = {n: sha(os.path.join(W, n)) for n in ("CloudBlue-MayMau-thu1.iso", "CloudBlue-MayMau-thu2.iso")}
        t1, o1 = time.time(), ""
        while time.time() - t1 < 300:
            time.sleep(10)
            rc, o1 = vm.ssh(XEM, 120)
            if all(("%s  /var/lib/vz/template/iso/%s" % (h, n)) in o1 for n, h in want.items()):
                break
        t_copy = time.time() - t1
        open(os.path.join(KQ, "pve-may-usb-1.txt"), "w").write(o1)
        ok("CẮM USB cài đặt bản ĐỦ vào máy ĐANG CHẠY (không cài lại, không gõ gì): sau %.0f giây cbhost đã tự chép 2 ISO máy mẫu vào kho ISO, SHA-256 khớp cả 2, đã gỡ gắn USB" % t_copy,
           not e and all(("%s  /var/lib/vz/template/iso/%s" % (h, n)) in o1 for n, h in want.items()) and sec(o1, "mnt").strip() == "0" and ".part" not in sec(o1, "iso"),
           (e, sec(o1, "iso")[-400:], sec(o1, "blk")[-300:], sec(o1, "log")[-500:])) or (res := 1)
        ok("nhật ký cbhost: 'thấy 2 ISO máy mẫu trên USB cài đặt — đang chép' rồi 'đã chép xong 2 ISO máy mẫu'", "thấy 2 ISO máy mẫu trên USB cài đặt" in sec(o1, "log")
           and "đã chép xong 2 ISO máy mẫu" in sec(o1, "log"), sec(o1, "log")[-500:]) or (res := 1)
        vm.shot("man-hinh")                                                        # màn hình máy chủ: [CloudBlue …] USB: … dang chep … / da chep xong …
        t2, o2 = time.time(), ""
        while time.time() - t2 < 240:
            time.sleep(10)
            rc, o2 = vm.ssh(XEM, 120)
            if "cbmau-thu1" in sec(o2, "qm") and "cbmau-thu2" in sec(o2, "qm"):
                break
        open(os.path.join(KQ, "pve-may-usb-2.txt"), "w").write(o2)
        wl = open(weblog).read() if os.path.exists(weblog) else ""
        ok("có ISO rồi thì TỰ dựng máy mẫu (sau %.0f giây đã có máy ảo cbmau-thu1 + cbmau-thu2 trên Proxmox thật); web giả nhận trạng thái USB + danh sách ISO" % (time.time() - t2),
           "cbmau-thu1" in sec(o2, "qm") and "cbmau-thu2" in sec(o2, "qm") and '"usb"' in wl and "CloudBlue-MayMau-thu1.iso" in wl, (sec(o2, "qm"), wl[-300:])) or (res := 1)
        # ---- rút ra, cắm USB THƯỜNG (FAT32) có 1 file ISO máy mẫu khác
        vm.unplug("du")
        img = os.path.join(W, "usb-thuong.img")
        sh("head -c 301M /dev/urandom > %s/CloudBlue-MayMau-thu3.iso" % W)
        sh("rm -f %s; truncate -s 1G %s && parted -s %s mklabel msdos mkpart primary fat32 1MiB 100%%" % (img, img, img))
        rc, lo = sh("sudo losetup -fP --show " + img)
        lo = lo.strip().splitlines()[-1] if rc == 0 else ""
        rc, out = sh("sudo mkfs.vfat -F 32 %sp1 && sudo mkdir -p /mnt/y && sudo mount %sp1 /mnt/y && sudo mkdir /mnt/y/may-mau && sudo cp %s/CloudBlue-MayMau-thu3.iso /mnt/y/may-mau/ && sudo umount /mnt/y; sudo losetup -d %s"
                     % (lo, lo, W, lo), 900)
        if ok("dựng USB thường (FAT32) có file may-mau/CloudBlue-MayMau-thu3.iso", rc == 0 and lo, out[-300:]):
            e = vm.plug("th", img)
            h3 = sha(os.path.join(W, "CloudBlue-MayMau-thu3.iso"))
            t3, o3 = time.time(), ""
            while time.time() - t3 < 240:
                time.sleep(10)
                rc, o3 = vm.ssh(XEM, 120)
                if ("%s  /var/lib/vz/template/iso/CloudBlue-MayMau-thu3.iso" % h3) in o3:
                    break
            open(os.path.join(KQ, "pve-may-usb-3.txt"), "w").write(o3)
            ok("CẮM USB THƯỜNG có file CloudBlue-MayMau-thu3.iso (thư mục con): sau %.0f giây cbhost tự chép vào kho ISO, SHA-256 khớp, gỡ gắn xong; 2 file cũ còn nguyên" % (time.time() - t3),
               not e and ("%s  /var/lib/vz/template/iso/CloudBlue-MayMau-thu3.iso" % h3) in o3 and sec(o3, "mnt").strip() == "0"
               and all(("%s  /var/lib/vz/template/iso/%s" % (h, n)) in o3 for n, h in want.items()), (e, sec(o3, "iso")[-400:], sec(o3, "blk")[-300:], sec(o3, "log")[-400:])) or (res := 1)
        else:
            res = 1
        vm.ssh("qm stop 99500 >/dev/null 2>&1; qm stop 99501 >/dev/null 2>&1; qm stop 99502 >/dev/null 2>&1; poweroff", 120)
        vm.wait_exit(time.time() - vm.t0 + 120)
        vm.kill()
    finally:
        web.terminate()
    return res


def ventoy(disk, disk_kind, want):
    """USB chứa file ISO (kiểu Ventoy: phân vùng FAT có CloudBlue-Proxmox.iso), không ghi kiểu DD → dịch vụ nạp phải tự gắn phân vùng, đọc kho trong file."""
    img = os.path.join(W, "vt.img")
    sh("rm -f %s; truncate -s 3G %s && parted -s %s mklabel msdos mkpart primary fat32 1MiB 100%%" % (img, img, img))
    rc, lo = sh("sudo losetup -fP --show " + img)
    lo = lo.strip().splitlines()[-1] if rc == 0 else ""
    rc, out = sh("sudo mkfs.vfat -F 32 %sp1 && sudo mkdir -p /mnt/x && sudo mount %sp1 /mnt/x && sudo mkdir /mnt/x/iso && sudo cp %s /mnt/x/iso/CloudBlue-Proxmox.iso && sudo umount /mnt/x; sudo losetup -d %s"
                 % (lo, lo, ISO, lo), 900)
    if not ok("dựng USB kiểu Ventoy (phân vùng FAT32 chứa file CloudBlue-Proxmox.iso)", rc == 0 and lo, out[-300:]):
        return 1
    try:
        vm = Vm("bios-file", "bios", disk, disk_kind, "none", False, usb2=img)
    except RuntimeError as e:
        ok("USB kiểu Ventoy: chạy được máy thử", False, e)
        return 1
    up = vm.wait_ssh(420)
    rc, out = vm.ssh("for i in $(seq 1 60); do [ -f /var/lib/cloudblue/nap-xong.json ] && break; sleep 4; done; cat /var/lib/cloudblue/nap-xong.json; journalctl -u cloudblue-nap -b --no-pager | tail -12; "
                     "sha256sum /var/lib/vz/template/iso/*.iso; lsblk -o NAME,TRAN,RM,FSTYPE,MOUNTPOINT; mount | grep -c cloudblue-nap", 600) if up else (1, "không vào được SSH")
    open(os.path.join(KQ, "pve-may-bios-file.txt"), "w").write(out)
    r = ok("USB kiểu Ventoy (ISO là 1 FILE trên phân vùng FAT của USB): dịch vụ nạp tự gắn phân vùng (chỉ đọc), thấy kho trong file, chép lại ISO bị thiếu, SHA-256 khớp, gỡ gắn xong",
           up and "trong file /run/cloudblue-nap/m/iso/CloudBlue-Proxmox.iso" in out and ("%s  /var/lib/vz/template/iso/CloudBlue-MayMau-thu2.iso" % want["CloudBlue-MayMau-thu2.iso"]) in out
           and '"note"' in out and out.strip().splitlines()[-1] == "0", out[-700:])
    vm.ssh("poweroff", 30)
    vm.wait_exit(time.time() - vm.t0 + 120)
    vm.kill()
    return 0 if r else 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ghep":
        return ghep()
    if not os.path.exists(ISO):
        ok("bước %s: chưa có ISO ghép (bước ghep lỗi)" % cmd, False)
        return 1
    sh("sudo chmod 666 /dev/kvm")
    if cmd == "win":
        return win()
    if cmd == "bios":
        return cai("bios", "usb", "scsi")
    if cmd == "uefi":
        return cai("uefi", "cd", "nvme")
    if cmd == "mang":
        return mang()
    if cmd == "usb":
        return usb()
    print("dùng: pve_ci.py ghep|win|bios|uefi|mang|usb")
    return 2


if __name__ == "__main__":
    sys.exit(main())
