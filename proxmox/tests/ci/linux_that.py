#!/usr/bin/env python3
"""CI (Ubuntu, GitHub Actions, có KVM): THỬ THẬT máy mẫu VPS NVMe LINUX (27/11a) — đúng như cbhost dựng trên Proxmox:
   ảnh Ubuntu 24.04 cloud CHÍNH CHỦ (cbhost.linux_image: kiểm SHA256SUMS) + cloud-init cbhost.linux_userdata + proxmox/vm/linux-vm.sh của CHÍNH commit này.
   1. dựng : máy ảo tự cài XFCE + CloudBlue + OpenClaw → chờ /var/lib/cloudblue/maymau.done qua QEMU guest agent (như cbhost)
   2. kiểm : dịch vụ, phiên XFCE tự đăng nhập, OpenClaw, Firefox, cbcap probe (X11: x11grab + XTEST → gói RTP)
   3. lưu  : như cbhost._seal bản Linux (dừng agent, {} vào identity / seed / rent, LIN_SEAL_SH) → tắt
   4. VPS  : nhân bản (ổ nối tiếp, nới 30 GB) → machine-id mới, XFCE lên, cloud-init không chạy lại, lệnh nới ổ GROW_LIN_SH → ~30 GB, agent chạy
   Mạng máy ảo ra được internet (phải tải gói); địa chỉ web trong cb.json trỏ vào cổng không có gì → không gọi web thật."""
import base64, hashlib, importlib.util, json, os, re, socket, subprocess, sys, time, types

os.environ.setdefault("TAG", "linux-ubuntu2404")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import win_that as W                                                  # noqa: E402  (Qga, Qmp, ghi kết quả, đẩy nhánh kết quả)

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.environ["CBHOST_CONF"] = "/nonexistent/cbhost.conf"
spec = importlib.util.spec_from_file_location("cbhost", os.path.join(ROOT, "cbhost.py"))
cb = importlib.util.module_from_spec(spec); spec.loader.exec_module(cb)
cb.log = lambda *a: print("   cbhost:", *a, flush=True)
WD = W.W
SHA = os.environ.get("GITHUB_SHA") or "main"
RAW = "https://raw.githubusercontent.com/%s/%s" % (os.environ.get("GITHUB_REPOSITORY") or "lvhien205hn-eng/cloudblue", SHA)
ok, info = W.ok, W.info


class Vm:
    def __init__(self, name, disk, seed=None, mac="BC:24:11:CB:10:01"):
        self.name = name
        self.qmp_p, self.qga_p = os.path.join(WD, "qmp-%s.sock" % name), os.path.join(WD, "qga-%s.sock" % name)
        for p in (self.qmp_p, self.qga_p):
            if os.path.exists(p): os.remove(p)
        a = ["qemu-system-x86_64", "-enable-kvm", "-name", name, "-machine", "pc", "-cpu", "host", "-smp", "4", "-m", "4096", "-display", "none",
             "-vga", "std", "-qmp", "unix:%s,server,nowait" % self.qmp_p, "-serial", "file:" + os.path.join(W.KQ, "linux-%s-serial.txt" % name),
             "-chardev", "socket,path=%s,server=on,wait=off,id=qga0" % self.qga_p, "-device", "virtio-serial", "-device", "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0",
             "-device", "virtio-scsi-pci,id=scsi0", "-drive", "file=%s,if=none,id=d0,format=qcow2,cache=unsafe,discard=unmap" % disk, "-device", "scsi-hd,drive=d0,bus=scsi0.0",
             "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0,mac=" + mac, "-usb", "-device", "usb-tablet"]
        if seed: a += ["-drive", "file=%s,media=cdrom,readonly=on" % seed]
        self.qlog = os.path.join(W.KQ, "linux-%s-qemu.txt" % name)
        self.p = subprocess.Popen(a, stdout=open(self.qlog, "w"), stderr=subprocess.STDOUT)
        self.q = W.Qmp(self.qmp_p, self.p); self.ga = W.Qga(self.qga_p); self.t0 = time.time(); self.n = 0

    def alive(self): return self.p.poll() is None

    def shot(self, tag):
        ppm = os.path.join(WD, "s-%s.ppm" % self.name)
        try:
            self.q.cmd("screendump", filename=ppm); time.sleep(0.5)
            W.ppm_to_png(ppm, os.path.join(W.KQ, "linux-%s-%s.png" % (self.name, tag)))
        except Exception as e:
            print("   (không chụp được: %s)" % e, flush=True)

    def tick(self):
        el = time.time() - self.t0
        if el >= self.n * 60:
            self.n = int(el // 60) + 1; self.shot("moi-nhat")
            if int(el // 60) % 5 == 0 and el >= 60: self.shot("p%03d" % int(el // 60))
            W.push("dang chay %s phut %d" % (self.name, int(el // 60)))

    def sh(self, cmd, timeout=180):
        return self.ga.run("/bin/sh", ["-c", cmd], timeout)

    def wait_exit(self, secs):
        t0 = time.time()
        while time.time() - t0 < secs and self.alive(): time.sleep(1)
        return not self.alive()

    def kill(self):
        if self.alive(): self.p.kill(); self.p.wait()


def save(name, data):
    if data is None: return ""
    t = W.clean(data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data))
    open(os.path.join(W.KQ, "linux-%s.txt" % name), "w", encoding="utf-8").write(t)
    return t


def userdata():
    """Đúng cloud-init cbhost tạo (linux_userdata) — chỉ đổi: địa chỉ web → cổng không có gì; file tải từ CHÍNH commit này."""
    c = dict(cb.conf()); c["sb_url"] = "http://10.0.2.2:9"
    ud = cb.Host.linux_userdata(types.SimpleNamespace(c=c), "ubuntu2404")
    ud = ud.replace(cb.LIN_BOOT_URL, RAW + "/proxmox/vm/linux-vm.sh").replace("&& bash /root/cb-linux-vm.sh", "&& CB_RAW=%s bash /root/cb-linux-vm.sh" % RAW)
    return ud


def build():
    cb.IMG_DIR = os.path.join(WD, "img")
    t0 = time.time()
    try: img = cb.Host.linux_image(types.SimpleNamespace(), "ubuntu2404")
    except Exception as e:
        ok("tải ảnh Ubuntu 24.04 cloud chính chủ + kiểm SHA256SUMS (cbhost.linux_image)", False, e); return None
    ok("tải ảnh Ubuntu 24.04 cloud chính chủ + kiểm SHA256SUMS (cbhost.linux_image) — %.0f MB, %.0f giây" % (os.path.getsize(img) / 2 ** 20, time.time() - t0), True)
    disk = os.path.join(WD, "mau.qcow2")
    W.sh(["qemu-img", "create", "-f", "qcow2", "-b", img, "-F", "qcow2", disk, "20G"])
    sd = os.path.join(WD, "seed"); os.makedirs(sd, exist_ok=True)
    ud = userdata()
    open(os.path.join(sd, "user-data"), "w").write(ud)
    open(os.path.join(sd, "meta-data"), "w").write("instance-id: cbci-%s\nlocal-hostname: cloudblue-vps\n" % SHA[:8])
    cbj = json.loads(base64.b64decode(re.search(r"content: (\S+)", ud).group(1)))
    info("cloud-init (như cbhost): cb.json %s · chạy %s" % ({k: cbj[k] for k in ("ver", "role", "user", "sb_url")}, RAW + "/proxmox/vm/linux-vm.sh"))
    seed = os.path.join(WD, "seed.iso")
    rc, out = W.sh(["genisoimage", "-quiet", "-output", seed, "-volid", "cidata", "-joliet", "-rock", os.path.join(sd, "user-data"), os.path.join(sd, "meta-data")])
    if rc != 0: ok("tạo đĩa cloud-init", False, out); return None
    vm = Vm("mau", disk, seed)
    done = bad = None; ga_at = None
    while time.time() - vm.t0 < 50 * 60 and vm.alive():
        vm.tick(); time.sleep(20)
        if not vm.ga.ping(): continue
        if ga_at is None:
            ga_at = time.time() - vm.t0; info("phút %.0f: QEMU guest agent trong máy đã trả lời (linux-vm.sh đã cài xong gói)" % (ga_at / 60))
        done = vm.ga.read(cb.LIN_DONE_F)
        bad = vm.ga.read(cb.LIN_FAIL_F)
        if done or bad: break
    vm.shot("dung-xong")
    save("maymau-log", vm.ga.read("/var/log/cloudblue-maymau.log"))
    save("cloud-init-log", (vm.ga.read("/var/log/cloud-init-output.log") or b"")[-20000:])
    good = ok("máy mẫu Linux TỰ DỰNG xong (maymau.done) — %.0f phút" % ((time.time() - vm.t0) / 60), bool(done) and not bad,
              ("linux-vm.sh báo lỗi: %s" % bad) if bad else "quá giờ / máy tắt (xem linux-maymau-log.txt)")
    if done: info("maymau.done: " + done.decode("utf-8", "replace").replace("\n", " | "))
    return vm if good else (vm.kill() or None)


def checks(vm, label):
    t0 = time.time()
    while time.time() - t0 < 180:
        rc, t = vm.sh("pgrep -u vps -x xfce4-session")
        if rc == 0: break
        time.sleep(10)
    ok("%s: tài khoản khách vps TỰ đăng nhập giao diện XFCE (LightDM)" % label, rc == 0, t)
    rc, t = vm.sh("systemctl is-active cloudblue.service lightdm.service qemu-guest-agent.service | tr '\\n' ' '")
    ok("%s: dịch vụ cloudblue (agent) · lightdm · qemu-guest-agent đang chạy" % label, (t or "").split() == ["active"] * 3, t)
    return rc


def probe(vm, label):
    time.sleep(10)
    rc, t = vm.sh("install -D -m 0644 /opt/cloudblue/linux/cbcap.py /usr/local/lib/cloudblue/cbcap.py && runuser -u vps -- env DISPLAY=:0 XAUTHORITY=/home/vps/.Xauthority python3 -I -B /usr/local/lib/cloudblue/cbcap.py probe 5 2>&1 | tail -n 2", 120)
    m = re.search(r"cbcap probe: backend=(\S+) virtual=\d+ rtp=(\d+)", t or "")
    ok("%s: điều khiển từ xa X11 — cbcap probe: backend x11 (x11grab + XTEST), gói RTP H.264 > 20" % label, m and m.group(1) == "x11" and int(m.group(2)) > 20, (t or "")[-600:])
    vm.shot("man-hinh-nen")


def seal(vm):
    rc, t = vm.sh("bash -lc 'openclaw --version' 2>&1 | head -1; command -v firefox; ls /home/vps/Desktop 2>/dev/null | tr '\\n' ' '")
    ok("máy mẫu: có OpenClaw (bộ cài chính thức) + Firefox + lối tắt màn hình nền", re.search(r"\d+\.\d+", (t or "").split("\n")[0] or "") and "firefox" in (t or ""), t)
    rc, t = vm.sh("python3 -I -B /opt/cloudblue/linux/cbagent.py status 2>&1 | head -c 1500")
    info("agent status: " + W.clean(t or "")[:800])
    save("agent-log", vm.ga.read("/opt/cloudblue/logs/agent.log"))
    save("remote-log", vm.ga.read("/opt/cloudblue/logs/remote.log"))
    probe(vm, "máy mẫu")
    vm.sh("systemctl stop cloudblue.service", 60)
    wr = [vm.ga.write(cb.LIN_BASE + "/" + fn, "{}") for fn in ("identity.json", "seed.json", "rent.json")]
    rc, t = vm.ga.run("/bin/sh", ["-c", cb.LIN_SEAL_SH], 120)
    mid = vm.ga.read("/etc/machine-id")
    ok("lưu máy mẫu (như cbhost._seal Linux): {} vào identity / seed / rent · tắt cloud-init · machine-id rỗng", all(wr) and rc == 0 and mid is not None and mid.strip() == b""
       and vm.ga.read("/etc/cloud/cloud-init.disabled") is not None, (wr, rc, t, mid))
    vm.ga.call("guest-shutdown", {"mode": "powerdown"}, 10)
    off = vm.wait_exit(240)
    ok("máy mẫu tắt được bằng guest agent", off)
    vm.kill()
    return off


def vps():
    disk = os.path.join(WD, "vps.qcow2")
    W.sh(["qemu-img", "create", "-f", "qcow2", "-b", os.path.join(WD, "mau.qcow2"), "-F", "qcow2", disk, "30G"])
    vm = Vm("vps", disk, None, mac="BC:24:11:CB:10:02")
    up = None
    while time.time() - vm.t0 < 600 and vm.alive():
        vm.tick(); time.sleep(10)
        if vm.ga.ping(): up = time.time() - vm.t0; break
    if not ok("VPS nhân từ máy mẫu (không có đĩa cloud-init): bật lên, guest agent trả lời" + (" sau %.0f giây" % up if up else ""), up is not None):
        vm.shot("cuoi"); vm.kill(); return
    checks(vm, "VPS")
    rc, t = vm.sh("cat /etc/machine-id; cloud-init status 2>&1 | head -1")
    ok("VPS: machine-id MỚI (máy tự sinh) · cloud-init không chạy lại", re.match(r"[0-9a-f]{32}\n", t or "") is not None and "disabled" in (t or "").lower(), t)
    rc, t = vm.ga.run("/bin/sh", ["-c", cb.GROW_LIN_SH], 120)
    gb = int(re.findall(r"\d+", t or "0")[-1]) if re.findall(r"\d+", t or "") else 0
    ok("VPS: lệnh nới ổ của cbhost (GROW_LIN_SH: growpart + resize2fs) → ổ / ≈ 30 GB", 28 <= gb <= 31, t)
    seed = json.dumps({"hw": "cb" + "0" * 30, "ticket": "ve-thu-ci-khong-co-that"})
    ok("VPS: cbhost ghi được vé vào /opt/cloudblue/seed.json qua guest agent", vm.ga.write(cb.LIN_BASE + "/seed.json", seed) and (vm.ga.read(cb.LIN_BASE + "/seed.json") or b"").decode() == seed)
    probe(vm, "VPS")
    time.sleep(20)
    save("vps-agent-log", vm.ga.read("/opt/cloudblue/logs/agent.log"))
    vm.shot("cuoi")
    vm.ga.call("guest-shutdown", {"mode": "powerdown"}, 10)
    if not vm.wait_exit(180): vm.kill()


def main():
    W.line("== VPS NVMe Linux: Ubuntu 24.04 + XFCE + CloudBlue + OpenClaw (commit %s)" % SHA[:12])
    try:
        vm = build()
        W.push("dung xong / dung", True)
        if vm is not None:
            checks(vm, "máy mẫu")
            if seal(vm):
                W.push("da luu may mau", True)
                vps()
    except Exception as e:
        import traceback
        ok("bộ thử chạy tới hết", False, "%s | %s" % (e, traceback.format_exc()[-600:]))
    W.line("== hết (%.0f phút)" % ((time.time() - W.T00) / 60))
    W.push("xong", True)
    return 0 if "\nXX" not in "\n" + open(W.RES, encoding="utf-8").read() else 1


if __name__ == "__main__":
    sys.exit(main())
