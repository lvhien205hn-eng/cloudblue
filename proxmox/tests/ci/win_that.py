#!/usr/bin/env python3
"""CI (Ubuntu, GitHub Actions, có KVM): THỬ THẬT ISO máy mẫu Windows — gọi qua win_that.sh. Không đụng máy thật nào, không gọi web thật
(mạng của máy ảo thử bị chặn hết đường ra ngoài: restrict=on).

   ISO máy mẫu do proxmox/tao-iso-may-mau.ps1 ghép trên máy Windows CI từ ISO Windows Server chính chủ (bản dùng thử) — đúng lệnh chủ shop chạy.
   Máy ảo QEMU ở đây có cấu hình như máy cbhost tạo trên Proxmox (qm create: máy "pc" + SeaBIOS, ổ SCSI VirtIO single sau cầu PCI,
   card mạng VirtIO, ổ CD IDE, cổng QEMU guest agent, VGA std, CPU host + cờ hv_* của Proxmox cho Windows, 2 nhân, 2048 MB, ổ 20 GB).

   1. cài   : bật từ ISO → Windows TỰ cài → chờ như cbhost chờ: guest agent trả lời + có C:\\CloudBluePC\\vm\\maymau.done
   2. kiểm  : tài khoản khách tự đăng nhập, agent CloudBlue chạy, driver đủ, tài khoản Administrator đã khoá …
   3. lưu   : làm như cbhost._seal qua guest agent — dừng pythonw, ghi {} vào identity / seed / rent, tắt máy
   4. VPS   : nhân bản (ổ nối tiếp), bật KHÔNG có ISO, mã máy khác → guest agent trả lời, tự đăng nhập, ghi được vé vào seed.json

   Kết quả: kq/win-<tag>-ketqua.txt (dòng OK / XX / ..), ảnh màn hình kq/win-<tag>-*.png, nhật ký trong máy kq/win-<tag>-*.txt.
   Cứ 5 phút đẩy kết quả dở lên nhánh win-shots-<tag> (win_that_push.sh) để theo dõi được lúc đang chạy."""
import base64, hashlib, json, os, random, re, shutil, socket, struct, subprocess, sys, time, zlib

TAG = os.environ.get("TAG", "win2016")                          # nhãn kết quả (win2016, win2012r2, win2016-uefi)
BAN = os.environ.get("BAN") or TAG.replace("-uefi", "")         # bản Windows = tên ISO máy mẫu
UEFI = TAG.endswith("-uefi")                                    # máy ảo OVMF (admin tự tạo máy kiểu UEFI) — cbhost thì luôn tạo SeaBIOS
W = os.environ.get("W", "/mnt/w")
KQ = os.environ.get("KQ", os.path.join(os.getcwd(), "kq"))
HERE = os.path.dirname(os.path.abspath(__file__))
ISO = os.path.join(W, "iso", "CloudBlue-MayMau-%s.iso" % BAN)
DISK = os.path.join(W, "mau-%s.qcow2" % TAG)
RES = os.path.join(KQ, "win-%s-ketqua.txt" % TAG)
T_INSTALL = int(os.environ.get("T_INSTALL", "50")) * 60           # cbhost cho 3 giờ; trên máy CI bản 2016 cài hết 4 phút
T_STALL = 6                                                      # màn hình đứng yên từng ấy phút mà guest agent chưa lên → coi là kẹt: chẩn đoán rồi dừng
BASE = "C:\\CloudBluePC"
DONE_F = BASE + "\\vm\\maymau.done"
FAIL_F = BASE + "\\vm\\maymau.loi"
# cờ CPU Proxmox đặt cho máy Windows (qemu-server): win10 / 2016+ đủ bộ, win8 / 2012 R2 bộ ngắn. Máy CI không nhận → lùi dần.
CPU_FULL = "host,hv_ipi,hv_relaxed,hv_reset,hv_runtime,hv_spinlocks=0x1fff,hv_stimer,hv_synic,hv_time,hv_vapic,hv_vpindex,+kvm_pv_eoi,+kvm_pv_unhalt"
CPU_WIN8 = "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,+kvm_pv_eoi,+kvm_pv_unhalt"
CPUS = ([CPU_WIN8] if "2012" in TAG else [CPU_FULL, CPU_WIN8]) + ["host"]
os.makedirs(KQ, exist_ok=True)
T00 = time.time()
LAST_PUSH = [time.time()]


def line(t):
    print(t, flush=True)
    with open(RES, "a", encoding="utf-8") as f:
        f.write(t + "\n")


def ok(name, cond, extra=""):
    line(("OK  " + name) if cond else ("XX  %s: %s" % (name, str(extra).replace("\n", " | ")[:700])))
    return bool(cond)


def info(t):
    line("..  " + str(t).replace("\n", " | ")[:900])


def sh(cmd, timeout=600, **kw):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, errors="replace", **kw)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "qua %d giay" % timeout


def push(msg, force=False):
    if not force and time.time() - LAST_PUSH[0] < 290:
        return
    LAST_PUSH[0] = time.time()
    rc, out = sh(["bash", os.path.join(HERE, "win_that_push.sh"), TAG, KQ, msg], 180)
    if rc != 0:
        print("   (đẩy kết quả dở chưa được: %s)" % out[-200:].replace("\n", " | "), flush=True)


def clean(t):
    """Bỏ chuỗi trông như khoá / mã (không đưa lên nhánh kết quả công khai)."""
    t = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}", "<jwt>", t)
    t = re.sub(r"\b(sb_[a-z]+_[A-Za-z0-9_-]{12,}|cb(pc|sv)_[A-Za-z0-9_-]{8,})", "<khoa>", t)
    t = re.sub(r"[a-z0-9]{16,}\.supabase\.co", "<du-an>.supabase.co", t)
    return re.sub(r"\b[A-Za-z0-9+/=_-]{48,}\b", "<chuoi-dai>", t)


def ppm_to_png(ppm, png):
    d = open(ppm, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", d)
    w, h = int(m.group(1)), int(m.group(2))
    px = d[m.end():]
    raw = b"".join(b"\0" + px[y * w * 3:(y + 1) * w * 3] for y in range(h))
    chunk = lambda t, c: struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c) & 0xffffffff)
    open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


class Qmp:
    def __init__(self, path, proc):
        self.s = None
        for _ in range(100):
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(path)
                self.s = s
                break
            except OSError:
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        if self.s is None:
            raise RuntimeError("QEMU không chạy được (không có cổng QMP)")
        self.s.settimeout(30)
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


class Qga:
    """QEMU guest agent qua cổng virtio-serial (như Proxmox: qm guest cmd / pvesh …/agent/…). Mỗi lệnh 1 lần nối, đồng bộ bằng guest-sync."""
    def __init__(self, path):
        self.path = path

    def call(self, name, args=None, timeout=25):
        try:
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(timeout)
            s.connect(self.path)
        except OSError:
            return None
        try:
            sid = random.randint(1, 2 ** 31 - 1)
            s.sendall((json.dumps({"execute": "guest-sync", "arguments": {"id": sid}}) + "\n").encode())
            buf, synced, t0 = b"", False, time.time()
            while time.time() - t0 < timeout:
                try:
                    d = s.recv(1 << 20)
                except (socket.timeout, OSError):
                    return None
                if not d:
                    return None
                buf += d
                while b"\n" in buf:
                    ln, buf = buf.split(b"\n", 1)
                    try:
                        o = json.loads(ln.replace(b"\xff", b"").decode("utf-8", "replace"))
                    except ValueError:
                        continue
                    if not synced:
                        if isinstance(o, dict) and o.get("return") == sid:
                            synced = True
                            if name == "guest-sync":
                                return o
                            s.sendall((json.dumps({"execute": name, "arguments": args or {}}) + "\n").encode())
                        continue
                    return o
            return None
        finally:
            try:
                s.close()
            except OSError:
                pass

    def ping(self):
        return self.call("guest-sync", timeout=8) is not None

    def read(self, path, limit=4 << 20):
        """Nội dung file trong máy (bytes); không có file / agent chưa chạy → None."""
        o = self.call("guest-file-open", {"path": path, "mode": "r"})
        if not o or "return" not in o:
            return None
        h, data = o["return"], b""
        try:
            while len(data) < limit:
                r = self.call("guest-file-read", {"handle": h, "count": 1 << 18}, 40)
                if not r or "return" not in r:
                    break
                data += base64.b64decode(r["return"].get("buf-b64") or "")
                if r["return"].get("eof") or not r["return"].get("count"):
                    break
        finally:
            self.call("guest-file-close", {"handle": h})
        return data

    def write(self, path, content):
        o = self.call("guest-file-open", {"path": path, "mode": "w"})
        if not o or "return" not in o:
            return False
        h = o["return"]
        r = self.call("guest-file-write", {"handle": h, "buf-b64": base64.b64encode(content.encode()).decode()})
        self.call("guest-file-close", {"handle": h})
        return bool(r and "return" in r)

    def run(self, path, args=(), timeout=120):
        """→ (mã thoát, chữ in ra); không chạy được → (None, lý do)."""
        o = self.call("guest-exec", {"path": path, "arg": list(args), "capture-output": True})
        if not o or "return" not in o:
            return None, json.dumps(o)[:300]
        pid, t0 = o["return"]["pid"], time.time()
        while time.time() - t0 < timeout:
            r = self.call("guest-exec-status", {"pid": pid}, 30)
            if r and "return" in r and r["return"].get("exited"):
                out = base64.b64decode(r["return"].get("out-data") or "") + base64.b64decode(r["return"].get("err-data") or "")
                return r["return"].get("exitcode"), out.decode("utf-8", "replace").replace("\r", "")
            time.sleep(2)
        return None, "qua %d giay" % timeout

    def cmd(self, text, timeout=120):
        return self.run("cmd.exe", ["/c", text], timeout)


class Vm:
    def __init__(self, name, disk, iso=None, cpu=CPUS[0], uuid="5a1b3c4d-0000-4000-8000-00000000cb01", mac="BC:24:11:CB:00:01", vars_from=None):
        self.name = name
        self.qmp_p = os.path.join(W, "qmp-%s.sock" % name)
        self.qga_p = os.path.join(W, "qga-%s.sock" % name)
        for p in (self.qmp_p, self.qga_p):
            if os.path.exists(p):
                os.remove(p)
        self.same, self.last_hash = 0, None
        a = ["qemu-system-x86_64", "-enable-kvm", "-name", name, "-machine", "pc,hpet=off", "-cpu", cpu, "-smp", "2,sockets=1,cores=2,maxcpus=2", "-m", "2048",
             "-nodefaults", "-display", "none", "-boot", "menu=on,strict=on,reboot-timeout=1000", "-smbios", "type=1,uuid=" + uuid,
             "-qmp", "unix:%s,server,nowait" % self.qmp_p,
             "-device", "pci-bridge,id=pci.3,chassis_nr=3,bus=pci.0,addr=0x5",
             "-device", "piix3-usb-uhci,id=uhci,bus=pci.0,addr=0x1.0x2", "-device", "usb-tablet,id=tablet,bus=uhci.0,port=1",
             "-chardev", "socket,path=%s,server=on,wait=off,id=qga0" % self.qga_p,
             "-device", "virtio-serial,id=qga0,bus=pci.0,addr=0x8", "-device", "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0",
             "-device", "VGA,id=vga,bus=pci.0,addr=0x2,edid=off",
             "-object", "iothread,id=iothread-virtioscsi0",
             "-device", "virtio-scsi-pci,id=virtioscsi0,bus=pci.3,addr=0x1,iothread=iothread-virtioscsi0",
             "-drive", "file=%s,if=none,id=drive-scsi0,discard=on,format=qcow2,cache=unsafe,detect-zeroes=unmap" % disk,
             "-device", "scsi-hd,bus=virtioscsi0.0,channel=0,scsi-id=0,lun=0,drive=drive-scsi0,id=scsi0,bootindex=100",
             "-netdev", "user,id=net0,restrict=on", "-device", "virtio-net-pci,mac=%s,netdev=net0,bus=pci.0,addr=0x12,id=net0" % mac,
             "-rtc", "driftfix=slew,base=localtime", "-global", "kvm-pit.lost_tick_policy=discard"]
        if iso:
            a += ["-drive", "file=%s,if=none,id=drive-ide2,media=cdrom,readonly=on,format=raw" % iso, "-device", "ide-cd,bus=ide.1,unit=0,drive=drive-ide2,id=ide2,bootindex=101"]
        if UEFI:
            vars_f = os.path.join(W, "vars-%s.fd" % name)
            if not os.path.exists(vars_f):
                shutil.copy(vars_from or "/usr/share/OVMF/OVMF_VARS_4M.fd", vars_f)
            a += ["-drive", "if=pflash,unit=0,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", "if=pflash,unit=1,format=raw,file=" + vars_f]
        self.cmdline = " ".join(a)
        self.qlog = os.path.join(KQ, "win-%s-qemu-%s.txt" % (TAG, name))
        self.p = subprocess.Popen(a, stdout=open(self.qlog, "w"), stderr=subprocess.STDOUT)
        try:
            self.q = Qmp(self.qmp_p, self.p)
        except RuntimeError as e:
            self.kill()
            raise RuntimeError("%s | %s" % (e, open(self.qlog).read()[-500:].replace("\n", " | ")))
        self.ga = Qga(self.qga_p)
        self.t0 = time.time()
        self.n = 0

    def alive(self):
        return self.p.poll() is None

    def shot(self, tag):
        """Chụp màn hình → kq/win-<tag>-<máy>-<tên>.png; trả mã băm của ảnh (để biết màn hình có đổi không)."""
        ppm = os.path.join(W, "s-%s.ppm" % self.name)
        try:
            self.q.cmd("screendump", filename=ppm)
            time.sleep(0.5)
            ppm_to_png(ppm, os.path.join(KQ, "win-%s-%s-%s.png" % (TAG, self.name, tag)))
            return hashlib.sha256(open(ppm, "rb").read()).hexdigest()
        except Exception as e:
            print("   (không chụp được màn hình: %s)" % e, flush=True)
            return None

    def key(self, *codes):
        self.q.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in codes], **{"hold-time": 70})
        time.sleep(0.16)

    def type_line(self, text, wait=3):
        """Gõ 1 dòng lệnh + Enter (bàn phím en-US) — để hỏi bộ cài Windows qua cửa sổ lệnh Shift+F10 khi nó kẹt."""
        plain = {" ": "spc", "\\": "backslash", ".": "dot", "-": "minus", "/": "slash", "=": "equal", ",": "comma", ";": "semicolon", "'": "apostrophe"}
        shift = {":": "semicolon", "_": "minus", "|": "backslash", ">": "dot", "<": "comma", "*": "8", "$": "4", "~": "grave_accent", '"': "apostrophe",
                 "(": "9", ")": "0", "&": "7", "%": "5", "+": "equal", "?": "slash", "!": "1"}
        for ch in text:
            if ch.isascii() and ch.isalpha():
                self.key(*((["shift"] if ch.isupper() else []) + [ch.lower()]))
            elif ch.isdigit():
                self.key(ch)
            elif ch in plain:
                self.key(plain[ch])
            elif ch in shift:
                self.key("shift", shift[ch])
        self.key("ret")
        time.sleep(wait)

    def tick(self, every=300):
        """Gọi đều trong lúc chờ: 1 phút chụp đè ảnh 'moi-nhat', mỗi <every> giây giữ thêm 1 ảnh đánh số phút + đẩy kết quả dở."""
        el = time.time() - self.t0
        if el >= self.n * 60:
            self.n = int(el // 60) + 1
            h = self.shot("moi-nhat")
            self.same = self.same + 1 if (h and h == self.last_hash) else 0
            self.last_hash = h
            if int(el // 60) % (every // 60) == 0 and el >= 60:
                self.shot("p%03d" % int(el // 60))
            push("dang chay: %s phut %d" % (self.name, int(el // 60)))

    def wait_exit(self, secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            if not self.alive():
                return True
            time.sleep(1)
        return not self.alive()

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait()


def start_vm(name, disk, iso=None, **kw):
    """Bật máy với bộ cờ CPU giống Proxmox nhất mà máy CI nhận."""
    err = ""
    for cpu in CPUS:
        try:
            vm = Vm(name, disk, iso, cpu=cpu, **kw)
        except RuntimeError as e:
            err = str(e)
            continue
        time.sleep(3)
        if vm.alive():
            info("máy %s: CPU [%s]%s" % (name, cpu, "" if cpu == CPUS[0] else " (máy CI không nhận bộ cờ đầy đủ của Proxmox: " + err[-160:] + ")"))
            return vm
        err = open(vm.qlog).read()[-300:]
    raise RuntimeError("không bật được QEMU: " + err)


def save_txt(name, data, tail=400):
    """Lưu nhật ký lấy từ trong máy (đuôi <tail> dòng, đã lọc chuỗi trông như khoá)."""
    if data is None:
        return ""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        t = data.decode("utf-16", "replace")
    else:
        t = data.decode("utf-8", "replace")
    t = clean("\n".join(t.replace("\r", "").splitlines()[-tail:]))
    open(os.path.join(KQ, "win-%s-%s.txt" % (TAG, name)), "w", encoding="utf-8").write(t)
    return t


def collect(vm, why):
    """Gom nhật ký trong máy qua guest agent (khi agent còn trả lời)."""
    if not vm.ga.ping():
        info("%s: guest agent không trả lời → không lấy được nhật ký trong máy qua agent" % why)
        return
    for name, path in (("maymau-log", BASE + "\\logs\\maymau.log"), ("maymau-out", BASE + "\\logs\\maymau.out"), ("provision-log", BASE + "\\logs\\provision.log"),
                       ("pe-log", BASE + "\\logs\\cbvm-pe.log"), ("pe-log-c", "C:\\cbvm-pe.log"),
                       ("maymau-loi", FAIL_F), ("setuperr", "C:\\Windows\\Panther\\setuperr.log"), ("setupact", "C:\\Windows\\Panther\\setupact.log"),
                       ("unattendgc", "C:\\Windows\\Panther\\UnattendGC\\setupact.log"), ("qemu-ga-msi", BASE + "\\logs\\qemu-ga-msi.log")):
        save_txt(name, vm.ga.read(path), 250 if name in ("setupact", "unattendgc", "qemu-ga-msi") else 400)


def autopsy(disk):
    """Windows không cài xong + agent không trả lời: mở ổ máy ảo (chỉ đọc) lấy nhật ký bộ cài."""
    mnt, raw = "/mnt/cbx", os.path.join(W, "x.raw")
    sh("sudo mkdir -p %s; sudo umount %s 2>/dev/null" % (mnt, mnt))
    rc, out = sh("sudo modprobe nbd max_part=8 && sudo qemu-nbd -r -c /dev/nbd0 %s && sleep 2 && sudo partprobe /dev/nbd0; lsblk -o NAME,SIZE,FSTYPE /dev/nbd0" % disk, 120)
    info("mổ ổ: " + out[-300:])
    done = False
    for part in ("/dev/nbd0p1", "/dev/nbd0p2", "/dev/nbd0p3", "/dev/nbd0p4"):
        if not os.path.exists(part):
            continue
        rc, out = sh("sudo mount -t ntfs-3g -o ro,norecover %s %s 2>&1 || sudo mount -o ro %s %s 2>&1" % (part, mnt, part, mnt), 60)
        if rc != 0:
            continue
        rc, ls = sh("ls %s | head -30" % mnt)
        info("ổ %s: %s" % (part, ls.replace("\n", " ")))
        for name, rel in (("x-pe-log", "cbvm-pe.log"), ("x-pe-setuperr", "cb-setuperr.log"), ("x-pe-setupact", "cb-setupact.log"),
                          ("x-setupact-bt", "$WINDOWS.~BT/Sources/Panther/setupact.log"), ("x-setuperr-bt", "$WINDOWS.~BT/Sources/Panther/setuperr.log"),
                          ("x-setupact", "Windows/Panther/setupact.log"), ("x-setuperr", "Windows/Panther/setuperr.log"),
                          ("x-unattendgc", "Windows/Panther/UnattendGC/setupact.log"), ("x-maymau-log", "CloudBluePC/logs/maymau.log"),
                          ("x-maymau-out", "CloudBluePC/logs/maymau.out"), ("x-provision-log", "CloudBluePC/logs/provision.log")):
            p = os.path.join(mnt, rel)
            rc, _ = sh(["sudo", "test", "-f", p])
            if rc == 0:
                rc, _ = sh("sudo cat '%s' > /tmp/x.bin" % p.replace("'", "'\\''"))
                save_txt(name, open("/tmp/x.bin", "rb").read(), 250)
                done = True
        sh("sudo umount %s" % mnt)
    sh("sudo qemu-nbd -d /dev/nbd0")
    if not done:
        info("mổ ổ: không đọc được nhật ký nào (ổ chưa chia / chưa có file)")


def diag(vm):
    """Bộ cài kẹt (màn hình đứng yên, guest agent chưa lên): mở cửa sổ lệnh của bộ cài (Shift+F10), in nhật ký ra màn hình rồi chụp,
    chép nhật ký của bộ cài sang ổ Windows mới (W:) để bước mổ ổ đọc được."""
    vm.shot("ket-o-day")
    vm.key("shift", "f10")
    time.sleep(5)
    vm.type_line("mode con cols=125 lines=50", 2)
    vm.type_line("type X:\\Windows\\Panther\\setuperr.log", 3)
    vm.shot("chan-doan-1-setuperr")
    vm.type_line("cls & type X:\\cbvm-pe.log", 3)
    vm.shot("chan-doan-2-pe")
    vm.type_line("cls & echo list disk> X:\\q.txt & echo list volume>> X:\\q.txt & diskpart /s X:\\q.txt", 8)
    vm.shot("chan-doan-3-o-dia")
    vm.type_line("cls & copy /y X:\\Windows\\Panther\\setupact.log W:\\cb-setupact.log & copy /y X:\\Windows\\Panther\\setuperr.log W:\\cb-setuperr.log & copy /y X:\\cbvm-pe.log W:\\cbvm-pe.log", 5)
    vm.type_line("dir W:\\ & dir X:\\Windows\\Panther", 3)
    vm.shot("chan-doan-4-chep")
    vm.type_line("cls & find /i \"error\" X:\\Windows\\Panther\\setupact.log", 4)          # (WinPE của 2012 R2 không có findstr)
    vm.shot("chan-doan-5-setupact")
    vm.type_line("cls & find \"!!!\" X:\\Windows\\inf\\setupapi.dev.log", 4)                # driver nạp lỗi (chữ ký số, thiết bị không khởi động …)
    vm.shot("chan-doan-6-driver")


def install():
    if not os.path.isfile(ISO):
        ok("có file ISO máy mẫu do job Windows ghép (%s)" % os.path.basename(ISO), False, "không thấy %s — xem phần ghép ở trên" % ISO)
        return None
    info("ISO máy mẫu: %.2f GB" % (os.path.getsize(ISO) / 2 ** 30))
    if os.path.exists(DISK):
        os.remove(DISK)
    sh(["qemu-img", "create", "-f", "qcow2", DISK, "20G"])
    vm = start_vm("cai", DISK, ISO)
    info("lệnh QEMU (như máy cbhost tạo trên Proxmox): " + vm.cmdline[:880])
    ga_at, done_at, fail_txt = None, None, None
    stalled = False
    while time.time() - vm.t0 < T_INSTALL and vm.alive():
        vm.tick()
        time.sleep(20)
        if not vm.ga.ping():
            if ga_at is None and vm.same >= T_STALL:
                stalled = True
                info("phút %.0f: màn hình đứng yên %d phút, guest agent chưa lên → bộ cài KẸT (xem ảnh ket-o-day + chan-doan-*)" % ((time.time() - vm.t0) / 60, vm.same))
                try:
                    diag(vm)
                except Exception as e:
                    info("chẩn đoán lỗi: %s" % e)
                break
            continue
        if ga_at is None:
            ga_at = time.time() - vm.t0
            info("phút %.0f: QEMU guest agent trong máy đã trả lời (Windows cài xong, SetupComplete.cmd đã chạy bước 1)" % (ga_at / 60))
            vm.shot("agent-len")
        if vm.ga.read(DONE_F) is not None:
            done_at = time.time() - vm.t0
            break
        f = vm.ga.read(FAIL_F)
        if f:
            fail_txt = f.decode("utf-8", "replace")
            break
    vm.shot("cuoi")
    mins = (time.time() - vm.t0) / 60
    if not vm.alive():
        ok("máy ảo cài Windows không tự tắt giữa chừng", False, "QEMU thoát ở phút %.0f: %s" % (mins, open(vm.qlog).read()[-300:]))
    good = ok("Windows TỰ CÀI từ ISO máy mẫu tới hết (không bấm gì): guest agent trả lời + có maymau.done — như cbhost chờ"
              + (" — %.0f phút trên máy CI" % (done_at / 60) if done_at else ""), done_at is not None,
              ("maymau.ps1 báo lỗi: " + fail_txt) if fail_txt else ("bộ cài Windows KẸT ở phút %d — xem ảnh ket-o-day / chan-doan-*" % mins) if stalled
              else ("quá %d phút chưa xong (agent %s)" % (mins, "đã trả lời từ phút %.0f" % (ga_at / 60) if ga_at else "CHƯA trả lời — xem ảnh màn hình")))
    collect(vm, "sau khi cài")
    if not good:
        vm.kill()
        if ga_at is None:
            try:
                autopsy(DISK)
            except Exception as e:
                info("mổ ổ lỗi: %s" % e)
        return None
    return vm


def checks(vm, label):
    """Kiểm trong máy qua guest agent. label: 'máy mẫu' | 'VPS'."""
    ga = vm.ga
    o = ga.call("guest-get-osinfo")
    if o and "return" in o:
        info("%s: %s | %s | bản %s" % (label, o["return"].get("pretty-name"), o["return"].get("version"), o["return"].get("kernel-version")))
    o = ga.call("guest-info")
    if o and "return" in o:
        info("%s: QEMU guest agent bản %s" % (label, o["return"].get("version")))
    procs, t0 = [], time.time()
    while time.time() - t0 < 300:                       # lần đăng nhập đầu Windows còn dựng hồ sơ người dùng vài chục giây rồi mới hiện màn hình nền
        rc, t = ga.run("tasklist.exe", ["/fo", "csv", "/nh"])
        procs = sorted(set(x.split('","')[0].strip('"').lower() for x in (t or "").splitlines() if x.startswith('"')))
        if "explorer.exe" in procs:
            break
        time.sleep(10)
    rc, qu = ga.cmd("query user 2>&1")
    o = ga.call("guest-get-users")
    users = [str(u.get("user")) for u in (o or {}).get("return", [])] if isinstance((o or {}).get("return"), list) else []
    ok("%s: tài khoản khách VPS TỰ đăng nhập vào màn hình nền (không mật khẩu)" % label,
       "explorer.exe" in procs and (any(u.lower() == "vps" for u in users) or re.search(r"(?im)^\s*>?vps\s", qu or "")), "người đang đăng nhập %s | query user: %s | explorer: %s" % (users, (qu or "")[:200], "explorer.exe" in procs))
    # (tên có dấu cách → gọi thẳng chương trình, không qua cmd: guest agent tự bọc tham số đúng kiểu Windows)
    t1 = "".join(str(ga.run("schtasks.exe", ["/query", "/tn", n, "/fo", "list"])[1] or "") for n in ("CloudBluePC Agent", "CloudBluePC Watch"))
    ok("%s: có 2 tác vụ CloudBluePC Agent + Watch" % label, t1.count("TaskName:") >= 2, t1[-300:])
    rc, t2 = ga.cmd("sc query QEMU-GA & sc qc QEMU-GA")
    ok("%s: dịch vụ QEMU-GA đang chạy, tự chạy khi bật máy" % label, "RUNNING" in (t2 or "") and "AUTO_START" in (t2 or ""), (t2 or "")[-300:])
    rc, t3 = ga.cmd("ipconfig")
    ip = re.findall(r"IPv4[^:]*:\s*([0-9.]+)", t3 or "")
    ok("%s: card mạng VirtIO có driver, nhận địa chỉ DHCP" % label, any(x.startswith("10.0.2.") for x in ip), (t3 or "")[-300:])
    rc, t4 = ga.run("wmic.exe", ["path", "Win32_PnPEntity", "where", "ConfigManagerErrorCode<>0", "get", "Name,PNPDeviceID,ConfigManagerErrorCode", "/format:list"], 180)
    devs = [dict(re.findall(r"(?m)^(\w+)=(.*)$", blk)) for blk in re.split(r"\n\s*\n", (t4 or "").replace("&amp;", "&")) if "PNPDeviceID=" in blk]
    # Thiết bị báo lỗi nhưng vô hại, không dính ổ đĩa / mạng / cổng agent:
    #   ACPI\ACPI0010 "HID Button over Interrupt Driver" — lỗi có sẵn của Windows 10 1607 / Server 2016 trên máy ảo KVM
    #   ACPI\QEMU0002 "QEMU FwCfg Device" — thiết bị chỉ để ghi thông tin lúc máy ảo sập; driver bản 0.1.215 không khởi động trên 2012 R2
    why = {"ACPI\\ACPI0010": "lỗi vô hại có sẵn của Windows Server 2016 trên KVM", "ACPI\\QEMU0002": "thiết bị chỉ ghi thông tin lúc máy ảo sập — vô hại"}
    known = [d for d in devs if d.get("PNPDeviceID", "").upper()[:13] in why]
    bad = ["%s [%s] mã %s" % (d.get("Name"), d.get("PNPDeviceID"), d.get("ConfigManagerErrorCode")) for d in devs if d not in known]
    for d in known:
        info("%s: bỏ qua thiết bị '%s' mã %s (%s)" % (label, d.get("Name"), d.get("ConfigManagerErrorCode"), why[d["PNPDeviceID"].upper()[:13]]))
    ok("%s: không còn thiết bị nào thiếu driver (ổ đĩa, mạng, cổng agent …)" % label, rc == 0 and not bad, " ; ".join(bad)[:500] or (t4 or "")[-200:])
    rc, t5 = ga.cmd("net user Administrator")
    act = re.search(r"(?im)^Account active\s+(\S+)", t5 or "")
    ok("%s: tài khoản Administrator có sẵn đã bị tắt (mật khẩu ngẫu nhiên, không ai biết)" % label, bool(act) and act.group(1).lower() == "no", (t5 or "")[:300])
    rc, t6 = ga.cmd("net localgroup Administrators")
    ok("%s: tài khoản khách VPS có quyền Admin" % label, re.search(r"(?im)^VPS\s*$", t6 or "") is not None, (t6 or "")[-300:])
    return procs


def seal(vm):
    """Như cbhost._seal: dừng agent CloudBlue, xoá mã máy (ghi {}), tắt máy bằng guest agent."""
    ga = vm.ga
    procs = checks(vm, "máy mẫu")
    time.sleep(20)
    rc, t = ga.run("tasklist.exe", ["/fo", "csv", "/nh"])
    ok("máy mẫu: agent CloudBlue (pythonw.exe) đang chạy sau khi cài xong (chưa đăng ký — chờ vé)", "pythonw.exe" in (t or "").lower(), sorted(procs)[:60])
    ga.run("taskkill", ["/f", "/im", "pythonw.exe"])
    wr = [ga.write(BASE + "\\" + fn, "{}") for fn in ("identity.json", "seed.json", "rent.json")]
    back = ga.read(BASE + "\\identity.json")
    ok("lưu máy mẫu (như cbhost): dừng agent, ghi {} vào identity / seed / rent qua guest agent, đọc lại đúng", all(wr) and back is not None and back.strip() == b"{}", (wr, back))
    vm.shot("truoc-khi-tat")
    ga.call("guest-shutdown", {"mode": "powerdown"}, 10)
    off = vm.wait_exit(300)
    ok("lưu máy mẫu: Windows tắt được bằng guest agent (≤ 5 phút)", off)
    if not off:
        vm.kill()
    return off


def vps():
    """1 VPS nhân bản từ máy mẫu: ổ nối tiếp (linked clone), không có ISO, mã máy + MAC khác."""
    disk = os.path.join(W, "vps-%s.qcow2" % TAG)
    if os.path.exists(disk):
        os.remove(disk)
    rc, out = sh(["qemu-img", "create", "-f", "qcow2", "-b", DISK, "-F", "qcow2", disk])
    vm = start_vm("vps", disk, None, uuid="5a1b3c4d-0000-4000-8000-00000000cb02", mac="BC:24:11:CB:00:02", vars_from=os.path.join(W, "vars-cai.fd") if UEFI else None)
    up = None
    while time.time() - vm.t0 < 900 and vm.alive():
        vm.tick()
        time.sleep(10)
        if vm.ga.ping():
            up = time.time() - vm.t0
            break
    if not ok("VPS nhân bản từ máy mẫu: bật lên, guest agent trả lời" + (" sau %.0f giây" % up if up else ""), up is not None, "15 phút chưa trả lời — xem ảnh"):
        vm.shot("cuoi")
        vm.kill()
        return
    t0 = time.time()
    while time.time() - t0 < 240:                       # chờ tự đăng nhập xong + agent CloudBlue lên
        rc, t = vm.ga.run("tasklist.exe", ["/fo", "csv", "/nh"])
        if "explorer.exe" in (t or "").lower() and "pythonw.exe" in (t or "").lower():
            break
        time.sleep(10)
    time.sleep(15)
    vm.shot("man-hinh-nen")
    procs = checks(vm, "VPS")
    ok("VPS: agent CloudBlue (pythonw.exe) tự chạy sau khi bật", "pythonw.exe" in procs, procs[:60])
    idt = vm.ga.read(BASE + "\\identity.json")
    ok("VPS: chưa mang mã máy nào (identity.json = {}) → mỗi VPS đăng ký riêng", idt is not None and idt.strip() == b"{}", idt)
    seed = json.dumps({"hw": "cb" + "0" * 30, "ticket": "ve-thu-ci-khong-co-that"})
    ok("VPS: cbhost đưa được vé đăng ký vào C:\\CloudBluePC\\seed.json qua guest agent", vm.ga.write(BASE + "\\seed.json", seed) and (vm.ga.read(BASE + "\\seed.json") or b"").decode() == seed)
    time.sleep(40)
    save_txt("vps-agent-log", vm.ga.read(BASE + "\\logs\\agent.log"), 60)
    vm.shot("cuoi")
    vm.ga.call("guest-shutdown", {"mode": "powerdown"}, 10)
    if not vm.wait_exit(240):
        vm.kill()


def main():
    line("== Windows tự cài từ ISO máy mẫu — %s, máy ảo %s (commit %s)" % (BAN, "UEFI (OVMF)" if UEFI else "BIOS (SeaBIOS) như cbhost tạo", os.environ.get("GITHUB_SHA", "?")[:12]))
    rc, out = sh("ls -l /dev/kvm; nproc; free -m | sed -n 2p; df -h %s | tail -1; qemu-system-x86_64 --version | head -1" % W)
    info("máy CI: " + out)
    try:
        vm = install()
        push("cai xong / dung", True)
        if vm is not None:
            if seal(vm):
                push("da luu may mau", True)
                vps()
            else:
                vm.kill()
    except Exception as e:
        import traceback
        ok("bộ thử chạy tới hết", False, "%s | %s" % (e, traceback.format_exc()[-500:]))
    line("== hết (%.0f phút)" % ((time.time() - T00) / 60))
    push("xong", True)
    return 0 if "\nXX" not in "\n" + open(RES, encoding="utf-8").read() else 1


if __name__ == "__main__":
    sys.exit(main())
