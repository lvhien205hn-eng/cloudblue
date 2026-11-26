#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cbhost.py — CloudBlue · phần mềm chạy trên MÁY CHỦ PROXMOX VE cho "VPS ảo hoá" (SQL v56).
#   · Tự lên web (vm_host_hello) → hiện ở Quản trị › VPS ảo hoá › Máy chủ dạng "chờ duyệt" → admin bấm Duyệt.
#   · 10 giây / lần hỏi việc (vm_host_poll) bằng khoá CÔNG KHAI của web + mã riêng của máy này (sinh 1 lần, chỉ nằm trên máy, 0600).
#   · Mỗi VPS = 1 máy ảo nhân bản từ MÁY MẪU Windows (tên đặt ở web, vd tpl-win10-22h2) có sẵn phần mềm CloudBlue PC (chưa đăng ký):
#       tạo: qm clone → đặt CPU / RAM / ổ → bật → sinh VÉ 1 lần, báo dấu băm của vé lên web (web mở cửa đăng ký đúng dòng máy) →
#            ghi C:\CloudBluePC\seed.json {hw, ticket} vào máy ảo qua QEMU guest agent → agent trong máy tự đăng ký (pc_enroll)
#            → khách thấy máy trong web / app CloudBlue, bấm là vào màn hình (không IP, không mở cổng).
#       tắt / bật / khởi động cứng / cài lại (xoá máy ảo, nhân bản lại) / xoá — theo đúng trạng thái web muốn.
#   · BẢNG ĐIỀU KHIỂN MÁY MẪU (SQL v57): web gửi việc "dựng máy mẫu" (từ file ISO máy mẫu đã đưa lên Proxmox, hoặc nhân bản máy mẫu đang có
#     để sửa) → máy ảo tạm cbmau-<số> → Windows tự cài (ISO ghép bằng proxmox/tao-iso-may-mau.ps1) → đưa vé → agent đăng ký → admin
#     ▶ điều khiển trên web → "Lưu": xoá mã máy trong máy (identity / seed / rent = {}), tắt, gỡ ISO, đổi máy mẫu cũ thành <tên>-cu,
#     đặt tên <tên> + chuyển thành máy mẫu. "Huỷ": xoá máy ảo tạm. Báo danh sách file ISO trên máy chủ để admin chọn.
#   · KHÔNG chạy lệnh nào do web gửi xuống: chỉ các việc ghi sẵn ở đây, số / tên đều kiểm kỹ.
#   · TỰ CẬP NHẬT (chạy bằng dịch vụ cloudblue-cbhost): 1 giờ / lần xem bản trên GitHub của CloudBlue — khác bản đang chạy → kiểm biên dịch
#     được → thay file → thoát để dịch vụ tự bật lại bản mới (chỉ lúc không có máy ảo nào đang dựng / xoá). Tắt: "auto_update": false.
#   · TỰ SỬA MẠNG (26/11c, máy cài bằng ISO CloudBlue-Proxmox): lúc cài mà mạng không cấp IPv4 (DHCP không trả lời) thì bộ cài Proxmox chỉ đặt
#     IPv6 + DNS mặc định 192.168.100.1 (không có thật) → máy lên nhưng không gọi được web. Khi KHÔNG gọi được web, cbhost tự: thêm
#     "iface vmbr0 inet dhcp" (xin IPv4 ngay + mỗi lần bật máy, dhclient tự thử lại mãi) và đặt lại máy chủ tên (DNS) công cộng hợp với
#     đường ra đang có (IPv4 / IPv6). Luôn lưu bản gốc (*.cb-goc), không đụng cấu hình IPv4 đã có. Tắt: "net_heal": false.
#   Lệnh:  python3 cbhost.py run | status | once | update | net | version
#   Cấu hình: /etc/cloudblue/cbhost.conf (JSON): sb_url, sb_key (khoá công khai của web), storage (để trống = cùng ổ với máy mẫu),
#             full_clone (true = nhân bản đầy đủ, false = nhân bản liên kết — nhanh, cần ổ hỗ trợ), vmid_base (mặc định 100000), auto_update,
#             bridge (card mạng máy mẫu, mặc định vmbr0), tpl_vmid_from (số máy ảo tạm của máy mẫu, mặc định 99000)
CBHOST_VER = "26/11c"

import hashlib, json, os, re, secrets, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

CONF_F = os.environ.get("CBHOST_CONF") or "/etc/cloudblue/cbhost.conf"
SECRET_F = os.environ.get("CBHOST_SECRET") or "/etc/cloudblue/cbhost.secret"
STATE_F = os.environ.get("CBHOST_STATE") or "/var/lib/cloudblue/cbhost-state.json"
QM = os.environ.get("CBHOST_QM") or "qm"
PVESH = os.environ.get("CBHOST_PVESH") or "pvesh"
DEFAULTS = {"sb_url": "https://nprftgodswlpzomcttal.supabase.co", "sb_key": "sb_publishable_qfNcnOMv70nq5LIlYXDJzg_UtdWHVze",
            "storage": "", "full_clone": True, "vmid_base": 100000, "seed_path": "C:\\CloudBluePC\\seed.json", "max_builds": 2, "auto_update": True,
            "bridge": "vmbr0", "tpl_vmid_from": 99000, "auto_tpl": False, "host_name": "", "net_heal": None}
UPD_URL = os.environ.get("CBHOST_UPD_URL") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/cbhost.py"   # chỉ nhận bản từ kho này
UPD_EVERY_S = 3600
RX_TPL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,40}$")
RX_HW = re.compile(r"^[0-9a-f]{64}$")
RX_STORE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}$")
RX_ISO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}:iso/[A-Za-z0-9][A-Za-z0-9_.+-]{0,120}\.iso$")
RX_BRIDGE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,14}$")
ISO_EVERY_S = 60                # danh sách file ISO trên máy chủ: 1 phút đọc lại 1 lần
RX_AUTO_ISO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,40}:iso/CloudBlue-MayMau-([a-z0-9]{3,24})\.iso$")    # ISO máy mẫu do tao-iso-may-mau.ps1 ghép
RX_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
AUTO_DONE_F = "C:\\CloudBluePC\\vm\\maymau.done"      # maymau.ps1 ghi file này khi máy mẫu cài xong
AUTO_WAIT_S = 3 * 3600          # tự dựng máy mẫu: Windows tự cài tối đa 3 giờ
AUTO_TRIES = 2                  # tự dựng máy mẫu: thử tối đa 2 lần / bản
AUTO_CHK_S = 45                 # tự dựng máy mẫu: hỏi máy ảo "cài xong chưa" 45 giây / lần
RETRY_S = 60                    # việc lỗi → 1 phút sau thử lại
RESOLV_F = os.environ.get("CBHOST_RESOLV") or "/etc/resolv.conf"
IFACES_F = os.environ.get("CBHOST_IFACES") or "/etc/network/interfaces"
DNS4, DNS6 = ("8.8.8.8", "1.1.1.1"), ("2001:4860:4860::8888", "2606:4700:4700::1111")
DNS_BOGUS = ("192.168.100.1",)  # DNS mặc định bộ cài Proxmox tự điền khi lúc cài không xin được gì từ mạng
NET_FAILS = 3                   # gọi web lỗi MẠNG liên tiếp bấy nhiêu vòng (≈ 30 giây) → thử tự sửa mạng
NET_EVERY_S = (120, 900)        # tự sửa mạng: 2 phút / lần trong 10 lần đầu, sau đó 15 phút / lần


def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


def load_json(p, dflt=None):
    try:
        with open(p, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else (dflt if dflt is not None else {})
    except Exception:
        return dflt if dflt is not None else {}


def save_json(p, d, mode=0o600):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False)
    os.chmod(tmp, mode); os.replace(tmp, p)


def conf():
    c = dict(DEFAULTS); c.update({k: v for k, v in load_json(CONF_F).items() if k in DEFAULTS})
    if not isinstance(c.get("storage"), str) or (c["storage"] and not RX_STORE.match(c["storage"])): c["storage"] = ""
    try: c["vmid_base"] = max(1000, min(900000000, int(c.get("vmid_base") or 100000)))
    except (TypeError, ValueError): c["vmid_base"] = 100000
    try: c["max_builds"] = max(1, min(8, int(c.get("max_builds") or 2)))
    except (TypeError, ValueError): c["max_builds"] = 2
    c["full_clone"] = c.get("full_clone") is not False
    c["auto_update"] = c.get("auto_update") is not False
    if not isinstance(c.get("bridge"), str) or not RX_BRIDGE.match(c["bridge"]): c["bridge"] = "vmbr0"
    try: c["tpl_vmid_from"] = max(100, min(900000000, int(c.get("tpl_vmid_from") or 99000)))
    except (TypeError, ValueError): c["tpl_vmid_from"] = 99000
    c["auto_tpl"] = c.get("auto_tpl") is True
    c["net_heal"] = c["auto_tpl"] if c.get("net_heal") is None else c.get("net_heal") is True      # mặc định: bật trên máy cài bằng ISO CloudBlue-Proxmox
    if not isinstance(c.get("host_name"), str) or not RX_HOSTNAME.match(c["host_name"]): c["host_name"] = ""
    return c


def secret():
    """Mã riêng của máy chủ này: sinh 1 lần, chỉ nằm ở /etc/cloudblue/cbhost.secret (0600). Web chỉ giữ dấu băm.
       2 tiến trình cùng sinh lần đầu (dịch vụ + lệnh status) → chỉ 1 mã được ghi, cả 2 cùng dùng mã đó."""
    os.makedirs(os.path.dirname(SECRET_F) or ".", exist_ok=True)
    for _ in range(5):
        try:
            s = open(SECRET_F, encoding="utf-8").read().strip()
            if re.fullmatch(r"[0-9a-f]{64}", s): return s
            bad = True                                              # file hỏng → thay
        except FileNotFoundError:
            bad = False
        tmp = "%s.%d.tmp" % (SECRET_F, os.getpid())
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f: f.write(secrets.token_hex(32))
        try:
            if bad: os.replace(tmp, SECRET_F)
            else: os.link(tmp, SECRET_F)                            # chưa có → tạo; đã có (tiến trình kia vừa tạo) → lỗi, đọc lại
        except FileExistsError:
            pass
        finally:
            try: os.remove(tmp)
            except OSError: pass
    raise RuntimeError("không ghi được mã riêng của máy chủ: " + SECRET_F)


def run(cmd, timeout=900):
    """Chạy 1 lệnh Proxmox (danh sách tham số, KHÔNG qua shell) → (mã thoát, chữ in ra)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "quá giờ chờ: " + " ".join(cmd[:3])
    except OSError as e:
        return 127, str(e)


# ---------------------------------------------------------------- gọi web (Supabase RPC, khoá công khai)
class Web:
    def __init__(self, c):
        self.url, self.key, self.err = c["sb_url"].rstrip("/"), c["sb_key"], ""

    def rpc(self, fn, body, timeout=25):
        req = urllib.request.Request(self.url + "/rest/v1/rpc/" + fn, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"apikey": self.key, "Authorization": "Bearer " + self.key, "Content-Type": "application/json",
                                              "User-Agent": "CloudBlue-cbhost/" + CBHOST_VER})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: d = json.loads(r.read().decode("utf-8") or "null")
            self.err = ""
            return d
        except urllib.error.HTTPError as e:
            try: self.err = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
            except Exception: self.err = "HTTP %s" % e.code
        except Exception as e:
            self.err = str(e)[:200]
        return None


# ---------------------------------------------------------------- Proxmox
class Pve:
    def __init__(self, c):
        self.c, self.node = c, socket.gethostname().split(".")[0]

    def vms(self):
        """{vmid: {name, status, template}} của node này (pvesh /cluster/resources — 1 lần gọi, JSON)."""
        rc, out = run([PVESH, "get", "/cluster/resources", "--type", "vm", "--output-format", "json"], 60)
        if rc != 0: raise RuntimeError("không đọc được danh sách máy ảo: " + out[-200:])
        res = {}
        for x in json.loads(out or "[]"):
            if not isinstance(x, dict) or x.get("type") != "qemu" or (x.get("node") and x.get("node") != self.node): continue
            try: vid = int(x.get("vmid"))
            except (TypeError, ValueError): continue
            res[vid] = {"name": str(x.get("name") or ""), "status": str(x.get("status") or ""), "template": bool(x.get("template"))}
        return res

    def config(self, vmid):
        rc, out = run([QM, "config", str(int(vmid))], 60)
        return out if rc == 0 else ""

    def boot_disk(self, vmid):
        """(tên ổ, cỡ GB) ổ hệ thống của máy ảo (bootdisk / boot order / ổ đầu tiên)."""
        cfg = self.config(vmid); disks = {}; order = []
        for ln in cfg.splitlines():
            m = re.match(r"^((?:scsi|virtio|sata|ide)\d+):\s*([^,\s]+)(.*)$", ln.strip())
            if m and "media=cdrom" not in m.group(3):
                sz = re.search(r"size=(\d+(?:\.\d+)?)([KMGT])", m.group(3))
                gb = 0.0
                if sz: gb = float(sz.group(1)) * {"K": 1 / 1048576, "M": 1 / 1024, "G": 1, "T": 1024}[sz.group(2)]
                disks[m.group(1)] = gb
            m2 = re.match(r"^boot:\s*order=(.+)$", ln.strip()) or re.match(r"^bootdisk:\s*(\S+)$", ln.strip())
            if m2: order = [x for x in re.split(r"[;,]", m2.group(1)) if x]
        for k in order:
            if k in disks: return k, disks[k]
        return (sorted(disks)[0], disks[sorted(disks)[0]]) if disks else (None, 0.0)

    def clone(self, tpl_id, vmid, name):
        base = [QM, "clone", str(int(tpl_id)), str(int(vmid)), "--name", name]
        if self.c["full_clone"]:
            cmd = base + ["--full", "1"] + (["--storage", self.c["storage"]] if self.c["storage"] else [])
            return run(cmd, 3600)
        rc, out = run(base + ["--full", "0"], 600)                 # liên kết: vài giây; ổ không hỗ trợ → nhân bản đầy đủ
        if rc == 0: return rc, out
        log("nhân bản liên kết không được (%s) → nhân bản đầy đủ" % out[-120:])
        return run(base + ["--full", "1"] + (["--storage", self.c["storage"]] if self.c["storage"] else []), 3600)

    def setup(self, vmid, cores, ram_mb, disk_gb, hw):
        rc, out = run([QM, "set", str(vmid), "--cores", str(cores), "--sockets", "1", "--memory", str(ram_mb), "--balloon", "0",
                       "--onboot", "1", "--agent", "enabled=1", "--tags", "cloudblue", "--smbios1", "uuid=" + hw_uuid(hw)], 120)
        if rc != 0: return rc, out
        dk, gb = self.boot_disk(vmid)
        if dk and disk_gb > gb + 0.5:
            rc, out = run([QM, "resize", str(vmid), dk, "%dG" % int(disk_gb)], 600)
            if rc != 0: return rc, "nới ổ lỗi: " + out
        return 0, ""

    def start(self, vmid): return run([QM, "start", str(vmid)], 180)
    def stop(self, vmid): return run([QM, "stop", str(vmid)], 180)
    def shutdown(self, vmid): return run([QM, "shutdown", str(vmid), "--timeout", "90", "--forceStop", "1"], 240)
    def reset(self, vmid): return run([QM, "reset", str(vmid)], 120)
    def destroy(self, vmid): return run([QM, "destroy", str(vmid), "--purge", "1", "--destroy-unreferenced-disks", "1"], 900)
    def ga_ping(self, vmid): return run([QM, "guest", "cmd", str(vmid), "ping"], 30)[0] == 0

    def ga_read(self, vmid, path):
        """Đọc 1 file trong máy ảo qua guest agent → nội dung (None = không có file / không đọc được)."""
        rc, out = run([PVESH, "get", "/nodes/%s/qemu/%d/agent/file-read" % (self.node, int(vmid)), "--file", path, "--output-format", "json"], 60)
        if rc != 0: return None
        try: return str((json.loads(out or "{}") or {}).get("content") or "")
        except Exception: return None

    def ga_write(self, vmid, path, content):
        return run([PVESH, "create", "/nodes/%s/qemu/%d/agent/file-write" % (self.node, int(vmid)), "--file", path, "--content", content], 60)

    def ga_exec(self, vmid, args):
        """Chạy 1 lệnh CỐ ĐỊNH (ghi sẵn trong file này) trong máy ảo qua guest agent."""
        return run([QM, "guest", "exec", str(int(vmid)), "--timeout", "30", "--"] + list(args), 90)

    # ---- máy mẫu
    def isos(self):
        """[{volid, size}] file ISO trên các ổ chứa ISO của node này (tối đa 60 file)."""
        res = []
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--content", "iso", "--output-format", "json"], 60)
        try: sts = [x for x in json.loads(out or "[]") if isinstance(x, dict) and x.get("active") and "iso" in str(x.get("content") or "")] if rc == 0 else []
        except Exception: sts = []
        for st in sts:
            name = str(st.get("storage") or "")
            if not RX_STORE.match(name): continue
            rc, out = run([PVESH, "get", "/nodes/%s/storage/%s/content" % (self.node, name), "--content", "iso", "--output-format", "json"], 60)
            try: items = json.loads(out or "[]") if rc == 0 else []
            except Exception: items = []
            for x in items if isinstance(items, list) else []:
                v = str((x or {}).get("volid") or "")
                if RX_ISO.match(v) and len(res) < 60:
                    try: sz = int((x or {}).get("size") or 0)
                    except (TypeError, ValueError): sz = 0
                    res.append({"volid": v, "size": sz})
        return sorted(res, key=lambda x: x["volid"])

    def image_storage(self):
        """Ổ để tạo ổ đĩa máy mẫu: cấu hình storage → local-lvm → local-zfs → ổ chứa máy ảo đầu tiên đang chạy."""
        if self.c["storage"]: return self.c["storage"]
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--content", "images", "--output-format", "json"], 60)
        try: names = [str(x.get("storage")) for x in json.loads(out or "[]") if isinstance(x, dict) and x.get("active")
                      and "images" in str(x.get("content") or "") and RX_STORE.match(str(x.get("storage") or ""))] if rc == 0 else []
        except Exception: names = []
        for pref in ("local-lvm", "local-zfs"):
            if pref in names: return pref
        return names[0] if names else ""

    def create_tpl_vm(self, vmid, name, it, storage):
        """Máy ảo trống + gắn ISO máy mẫu: BIOS thường (SeaBIOS), ổ SCSI VirtIO, card mạng VirtIO, có QEMU agent, màn hình thường (không VGA riêng)."""
        t = str(it["tpl"]).lower()
        ost = "win8" if "2012" in t else ("win11" if ("2022" in t or "2025" in t) else "win10")
        return run([QM, "create", str(int(vmid)), "--name", name, "--ostype", ost, "--machine", "pc", "--bios", "seabios",
                    "--scsihw", "virtio-scsi-single", "--scsi0", "%s:%d,discard=on,iothread=1" % (storage, int(it["disk_gb"])),
                    "--ide2", "%s,media=cdrom" % it["iso"], "--boot", "order=scsi0;ide2", "--net0", "virtio,bridge=%s" % self.c["bridge"],
                    "--cores", str(int(it["cores"])), "--sockets", "1", "--cpu", "host", "--memory", str(int(it["ram_mb"])), "--balloon", "0",
                    "--agent", "enabled=1", "--onboot", "0", "--vga", "std", "--tags", "cloudblue-mau", "--smbios1", "uuid=" + hw_uuid(it["hw"])], 600)

    def setup_tpl_vm(self, vmid, it):
        return run([QM, "set", str(int(vmid)), "--cores", str(int(it["cores"])), "--sockets", "1", "--memory", str(int(it["ram_mb"])), "--balloon", "0",
                    "--onboot", "0", "--agent", "enabled=1", "--tags", "cloudblue-mau", "--smbios1", "uuid=" + hw_uuid(it["hw"])], 120)

    def cdroms(self, vmid):
        """Ổ CD đang gắn file (ide2 / sata0 …) → để gỡ ISO trước khi thành máy mẫu."""
        res = []
        for ln in self.config(vmid).splitlines():
            m = re.match(r"^((?:ide|sata|scsi)\d+):\s*([^,\s]+)(.*)$", ln.strip())
            if m and "media=cdrom" in m.group(3) and m.group(2) != "none": res.append(m.group(1))
        return res

    def set_name(self, vmid, name): return run([QM, "set", str(int(vmid)), "--name", name], 120)
    def eject(self, vmid, dev): return run([QM, "set", str(int(vmid)), "--" + dev, "none,media=cdrom"], 120)
    def make_template(self, vmid): return run([QM, "template", str(int(vmid))], 600)

    def info(self):
        def first(cmd, rx, dflt=""):
            rc, out = run(cmd, 30)
            m = re.search(rx, out or "", re.M) if rc == 0 else None
            return m.group(1).strip() if m else dflt
        mem = meminfo()
        return {"host": self.c.get("host_name") or self.node, "pve": first(["pveversion"], r"pve-manager/([0-9.]+)"), "cpu": first(["lscpu"], r"^Model name:\s*(.+)$")[:80],
                "threads": os.cpu_count() or 1, "ram_mb": int(mem.get("MemTotal", 0) / 1024), "disk_gb": self.disk_total(),
                "kvm": os.path.exists("/dev/kvm"), "ver": CBHOST_VER, "lan_ip": lan_ip(), "ip6_only": ip6_only()}

    def disk_total(self):
        """Tổng GB các ổ chứa máy ảo (images) đang chạy — hoặc riêng ổ đặt ở cấu hình."""
        rc, out = run([PVESH, "get", "/nodes/%s/storage" % self.node, "--output-format", "json"], 60)
        tot = 0.0
        try:
            for s in json.loads(out or "[]") if rc == 0 else []:
                if not isinstance(s, dict) or not s.get("active") or "images" not in str(s.get("content") or ""): continue
                if self.c["storage"] and s.get("storage") != self.c["storage"]: continue
                tot += float(s.get("total") or 0) / 1073741824
        except Exception:
            pass
        return int(tot)


def hw_uuid(hw):
    """Mã máy (SMBIOS) riêng cho từng máy ảo, suy từ dấu máy web cấp."""
    return hw[:8] + "-" + hw[8:12] + "-4" + hw[13:16] + "-a" + hw[17:20] + "-" + hw[20:32]


def has_identity(txt):
    """identity.json trong máy ảo có mã máy thật (id + token)? ("{}" do lúc lưu máy mẫu xoá = không có)."""
    try: d = json.loads(txt or "")
    except Exception: return bool((txt or "").strip())
    return isinstance(d, dict) and bool(d.get("id")) and bool(d.get("token"))


def meminfo():
    d = {}
    try:
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":", 1); d[k] = float(v.split()[0])
    except Exception:
        pass
    return d


def lan_ip():
    """Địa chỉ của máy chủ trên đường ra Internet: IPv4 nếu có, không thì IPv6 (máy chỉ có IPv6). Không gửi gói nào (UDP connect chỉ chọn đường)."""
    for fam, dst in ((socket.AF_INET, DNS4[1]), (socket.AF_INET6, DNS6[1])):
        try:
            s = socket.socket(fam, socket.SOCK_DGRAM); s.connect((dst, 53)); ip = s.getsockname()[0]; s.close()
            if ip and not ip.lower().startswith(("fe80:", "::", "0.", "127.")): return ip
        except Exception:
            pass
    return ""


# ---------------------------------------------------------------- tự sửa mạng (26/11c) — xem phần đầu file
def default_routes():
    """→ (có đường ra Internet IPv4, có đường ra Internet IPv6)"""
    def has(fam):
        rc, out = run(["ip", fam, "route", "show", "default"], 15)
        return rc == 0 and bool(re.search(r"^default\s", out or "", re.M))
    return has("-4"), has("-6")


def ip6_only():
    try:
        v4, v6 = default_routes()
        return bool(v6 and not v4)
    except Exception:
        return False


def can_resolve(host, secs=8):
    """Phân giải được tên miền không (chạy ở luồng riêng: getaddrinfo không có giờ chờ)."""
    res = []
    def go():
        try: socket.getaddrinfo(host, 443); res.append(True)
        except Exception: res.append(False)
    t = threading.Thread(target=go, daemon=True); t.start(); t.join(secs)
    return bool(res and res[0])


def resolv_servers(txt):
    return re.findall(r"^[ \t]*nameserver[ \t]+(\S+)", txt or "", re.M)


def keep_once(path, old):
    """Lưu bản gốc 1 lần (<file>.cb-goc) trước khi cbhost sửa file cấu hình mạng."""
    bak = path + ".cb-goc"
    if old and not os.path.exists(bak):
        with open(bak, "w", encoding="utf-8") as f: f.write(old)


def fix_dns(v4, v6, force=False):
    """Không phân giải được tên miền → ghi máy chủ tên công cộng hợp với đường ra đang có vào resolv.conf (giữ dòng search / domain / options).
       Chỉ sửa khi máy chủ tên đang đặt RÕ RÀNG không dùng được (trống · 192.168.100.1 của bộ cài · khác họ địa chỉ với đường ra đang có);
       trường hợp còn lại chỉ sửa khi force (đã hỏng nhiều lần liền). → True nếu có ghi."""
    want = [DNS4[0], DNS6[0], DNS4[1]] if (v4 and v6) else list(DNS4) if v4 else list(DNS6) if v6 else []
    if not want: return False
    try: old = open(RESOLV_F, encoding="utf-8", errors="replace").read()
    except OSError: old = ""
    cur = resolv_servers(old)
    if cur == want: return False
    usable = [x for x in cur if x not in DNS_BOGUS and ((":" in x and v6) or (":" not in x and v4))]
    if usable and not force: return False
    keep = [ln.strip() for ln in old.splitlines() if re.match(r"^[ \t]*(search|domain|options)[ \t]", ln)]
    new = "\n".join(["# CloudBlue (cbhost): may chu ten (DNS) cu khong dung duoc -> dat may chu ten cong cong. Ban goc: %s.cb-goc" % RESOLV_F]
                    + keep + ["nameserver " + x for x in want]) + "\n"
    keep_once(RESOLV_F, old)
    with open(RESOLV_F, "w", encoding="utf-8") as f: f.write(new)      # ghi thẳng (không đổi tên file): giữ nguyên nếu file là liên kết
    return True


def ensure_dhcp4(bridge):
    """Cầu mạng của máy chủ CHƯA có cấu hình IPv4 nào (bộ cài chỉ đặt IPv6) → thêm "iface <cầu> inet dhcp" + nạp lại mạng (ifreload):
       máy xin IPv4 ngay và mỗi lần bật máy; mạng chưa cấp thì dhclient tự thử lại. Đã có cấu hình IPv4 (tĩnh / dhcp / manual) → KHÔNG đụng.
       → chữ mô tả việc đã làm ("" = không làm gì)."""
    if not RX_BRIDGE.match(bridge or "") or not shutil.which("dhclient") or not shutil.which("ifreload"): return ""      # ifupdown2 của Proxmox xin DHCP bằng dhclient
    try: old = open(IFACES_F, encoding="utf-8", errors="replace").read()
    except OSError: return ""
    b = re.escape(bridge)
    if not re.search(r"^[ \t]*iface[ \t]+%s[ \t]+inet6[ \t]" % b, old, re.M): return ""      # không phải máy "chỉ có IPv6" do bộ cài đặt → không đụng
    if re.search(r"^[ \t]*iface[ \t]+%s[ \t]+inet[ \t]" % b, old, re.M): return ""
    keep_once(IFACES_F, old)
    new = old.rstrip("\n") + "\n\n# CloudBlue (cbhost): luc cai, mang khong cap IPv4 -> tu xin IPv4 qua DHCP (ban goc: %s.cb-goc)\niface %s inet dhcp\n" % (IFACES_F, bridge)
    tmp = IFACES_F + ".cb-tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(new)
    os.chmod(tmp, 0o644); os.replace(tmp, IFACES_F)
    rc, out = run(["ifreload", "-a"], 240)
    return "thêm 'iface %s inet dhcp' + nạp lại mạng (ifreload mã %d%s)" % (bridge, rc, "" if rc == 0 else ": " + (out or "")[-160:].replace("\n", " | "))


def web_host(c):
    try: return urllib.parse.urlsplit(c["sb_url"]).hostname or ""
    except Exception: return ""


def is_ip(host):
    for fam in (socket.AF_INET, socket.AF_INET6):
        try: socket.inet_pton(fam, host); return True
        except (OSError, ValueError): pass
    return False


def net_heal(c, n=1):
    """1 lượt tự sửa mạng (gọi khi KHÔNG tới được web). n = lượt thứ mấy. → danh sách việc đã làm."""
    did = []
    v4, v6 = default_routes()
    if not v4:
        r = ensure_dhcp4(c["bridge"])
        if r:
            did.append(r)
            v4, v6 = default_routes()
    host = web_host(c)
    if host and not is_ip(host) and not can_resolve(host):
        if fix_dns(v4, v6, force=n >= 3): did.append("đặt lại máy chủ tên (DNS): %s" % ", ".join(resolv_servers(open(RESOLV_F, encoding="utf-8", errors="replace").read())))
    return did


class NetWatch:
    """Đếm số vòng liền không TỚI ĐƯỢC web (lỗi mạng, không phải web trả lỗi) → đến lúc thì gọi net_heal."""
    def __init__(self, c, heal=None, now=time.time):
        self.c, self.heal, self.now = c, heal or net_heal, now
        self.fails = self.heals = 0; self.last = 0.0

    def step(self, ok, err):
        """Gọi sau mỗi vòng hỏi web. → danh sách việc vừa tự sửa (thường rỗng)."""
        if ok: self.fails = 0; return []
        if ok is not False or not err or str(err).startswith("HTTP "): return []      # web có trả lời (kể cả báo lỗi) → mạng không sao
        self.fails += 1
        if not self.c.get("net_heal") or self.fails < NET_FAILS: return []
        if self.now() - self.last < NET_EVERY_S[0 if self.heals < 10 else 1]: return []
        self.last = self.now(); self.heals += 1
        try: return self.heal(self.c, self.heals) or []
        except Exception as e: return ["lỗi: %s" % str(e)[:160]]


_cpu = {"t": None}
def cpu_pct():
    try:
        v = [float(x) for x in open("/proc/stat").readline().split()[1:]]
        idle, tot = v[3] + (v[4] if len(v) > 4 else 0), sum(v)
        prev, _cpu["t"] = _cpu["t"], (idle, tot)
        if not prev or tot <= prev[1]: return 0.0
        return round(100 * (1 - (idle - prev[0]) / (tot - prev[1])), 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- 1 việc máy mẫu: kiểm dữ liệu web gửi xuống
def job_ok(it):
    try:
        return (isinstance(it, dict) and re.fullmatch(r"[0-9]{1,12}", str(it.get("id"))) and it.get("want") in ("running", "save", "cancel")
                and it.get("src") in ("iso", "tpl") and (it.get("src") == "tpl" or RX_ISO.match(str(it.get("iso") or "")))
                and 1 <= int(it.get("cores")) <= 16 and 1024 <= int(it.get("ram_mb")) <= 32768 and 16 <= int(it.get("disk_gb")) <= 200
                and RX_TPL.match(str(it.get("tpl") or "")) and len(str(it.get("tpl"))) <= 36 and RX_HW.match(str(it.get("hw") or "")))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- 1 VPS: kiểm dữ liệu web gửi xuống
def item_ok(it):
    try:
        return (isinstance(it, dict) and re.fullmatch(r"[0-9]{1,12}", str(it.get("id"))) and it.get("want") in ("running", "stopped", "deleted")
                and 1 <= int(it.get("cores")) <= 64 and 512 <= int(it.get("ram_mb")) <= 262144 and 10 <= int(it.get("disk_gb")) <= 4000
                and 1 <= int(it.get("inst")) and 0 <= int(it.get("boot")) and RX_TPL.match(str(it.get("tpl") or "")) and RX_HW.match(str(it.get("hw") or "")))
    except (TypeError, ValueError):
        return False


class Host:
    def __init__(self, c=None, web=None, pve=None):
        self.c = c or conf(); self.web = web or Web(self.c); self.pve = pve or Pve(self.c)
        self.sec = secret(); self.st = load_json(STATE_F, {}); self.status = "?"; self.name = ""
        self.lock = threading.Lock(); self.busy = {}; self.poll_s = 10; self.want = []; self.tpl_need = []
        self.info_t = 0.0; self.hello_ok = False
        self.jobs = []; self.jobs_ok = False; self.iso_t = 0.0; self.iso_list = []; self.auto = []      # việc máy mẫu (web v57) · file ISO trên máy chủ

    def save(self):
        with self.lock: save_json(STATE_F, self.st)

    def vmid(self, vid): return self.c["vmid_base"] + int(vid)

    # ---- việc chạy lâu (nhân bản, xoá) ở luồng riêng: vẫn hỏi web đều 10 giây / lần
    def bg(self, vid, fn, *a):
        if vid in self.busy or len(self.busy) >= self.c["max_builds"]: return
        def go():
            try: fn(*a)
            except Exception as e:
                self.fail(vid, "lỗi: %s" % e)
            finally:
                self.busy.pop(vid, None)
        th = threading.Thread(target=go, daemon=True); self.busy[vid] = th; th.start()

    def fail(self, vid, msg):
        with self.lock:
            s = self.st.setdefault(str(vid), {}); s["err"] = str(msg)[:280]; s["t_err"] = time.time()
        log("%s: %s" % (("MẪU-" + str(vid)[1:]) if str(vid).startswith("t") else ("VPS-%s" % vid), msg)); self.save()

    def build(self, it, tpl_id):
        vid, vmid = int(it["id"]), self.vmid(it["id"])
        log("VPS-%s: tạo máy ảo %d từ máy mẫu %s (bản cài %s)" % (vid, vmid, it["tpl"], it["inst"]))
        if vmid in self.pve.vms():
            rc, out = self.pve.destroy(vmid)
            if rc != 0: return self.fail(vid, "xoá máy ảo cũ lỗi: " + out[-200:])
        rc, out = self.pve.clone(tpl_id, vmid, "vps-%d" % vid)
        if rc != 0: return self.fail(vid, "nhân bản lỗi: " + out[-200:])
        rc, out = self.pve.setup(vmid, int(it["cores"]), int(it["ram_mb"]), int(it["disk_gb"]), it["hw"])
        if rc != 0: return self.fail(vid, "đặt cấu hình lỗi: " + out[-200:])
        with self.lock:
            self.st[str(vid)] = {"inst": int(it["inst"]), "boot": int(it["boot"]), "ticket": secrets.token_hex(24), "sent": False, "seeded": False,
                                 "t_build": time.time()}
        self.save()
        if it["want"] == "running":
            rc, out = self.pve.start(vmid)
            if rc != 0: return self.fail(vid, "bật máy lỗi: " + out[-200:])
        log("VPS-%s: tạo xong, chờ Windows lên để đưa vé đăng ký" % vid)

    def remove(self, vid):
        vmid = self.vmid(vid)
        if vmid in self.pve.vms():
            log("VPS-%s: xoá máy ảo %d" % (vid, vmid))
            rc, out = self.pve.destroy(vmid)
            if rc != 0: return self.fail(vid, "xoá máy ảo lỗi: " + out[-200:])
        with self.lock: self.st.pop(str(vid), None)
        self.save()

    def seed(self, vid, it):
        """Windows đã lên (guest agent trả lời) + web đã nhận dấu băm của vé → ghi seed.json {hw, ticket} vào máy ảo."""
        s = self.st.get(str(vid)) or {}
        vmid = self.vmid(vid)
        if not s.get("ticket") or not s.get("sent") or s.get("seeded") or not self.pve.ga_ping(vmid): return
        idf = self.c["seed_path"].rsplit("\\", 1)[0] + "\\identity.json"
        if has_identity(self.pve.ga_read(vmid, idf)):             # máy mẫu lỡ ĐÃ ĐĂNG KÝ → mọi bản nhân ra sẽ mang chung 1 mã máy → dừng, báo làm lại máy mẫu
            return self.fail(vid, "máy mẫu %s đã đăng ký CloudBlue (có %s) — làm lại máy mẫu theo hướng dẫn (cài CloudBlue PC KHÔNG nhập mã)" % (it["tpl"], idf))
        rc, out = self.pve.ga_write(vmid, self.c["seed_path"], json.dumps({"hw": it["hw"], "ticket": s["ticket"]}))
        if rc != 0: return self.fail(vid, "ghi vé vào máy ảo lỗi (QEMU guest agent): " + out[-200:])
        with self.lock: s["seeded"] = True; s["t_seed"] = time.time(); s.pop("err", None)
        log("VPS-%s: đã đưa vé vào máy ảo → agent CloudBlue tự đăng ký" % vid); self.save()

    # ---- MÁY MẪU (bảng điều khiển máy mẫu trên web)
    def job_vmid(self, jid, vms):
        s = self.st.get("t%d" % jid) or {}
        if s.get("vmid") in vms or (s.get("vmid") and s.get("made")): return int(s["vmid"])
        for k, v in vms.items():
            if v["name"] == "cbmau-%d" % jid: return k
        return None

    def job_create(self, it, tpl_id):
        jid = int(it["id"]); key = "t%d" % jid
        vms = self.pve.vms()
        with self.lock:                                                # chọn số máy ảo + ghi sổ trong 1 lần khoá: 2 việc cùng lúc không trùng số
            vmid = self.c["tpl_vmid_from"]
            while vmid in vms or vmid in [int((x or {}).get("vmid") or 0) for k, x in self.st.items() if k[:1] in ("t", "a") and k != key]: vmid += 1
            self.st[key] = {"vmid": vmid, "made": False, "ticket": secrets.token_hex(24), "sent": False, "seeded": False, "t_build": time.time()}
        self.save()
        if it["src"] == "iso":
            stg = self.pve.image_storage()
            if not stg: return self.fail(key, "máy chủ không có ổ chứa máy ảo (images)")
            log("MẪU-%d: tạo máy ảo %d (%s) từ ISO %s" % (jid, vmid, it["tpl"], it["iso"]))
            rc, out = self.pve.create_tpl_vm(vmid, "cbmau-%d" % jid, it, stg)
            if rc != 0: return self.fail(key, "tạo máy ảo lỗi: " + out[-200:])
        else:
            log("MẪU-%d: nhân bản máy mẫu %s → máy ảo %d để sửa" % (jid, it["tpl"], vmid))
            rc, out = self.pve.clone(tpl_id, vmid, "cbmau-%d" % jid)
            if rc != 0: return self.fail(key, "nhân bản lỗi: " + out[-200:])
            rc, out = self.pve.setup_tpl_vm(vmid, it)
            if rc != 0: return self.fail(key, "đặt cấu hình lỗi: " + out[-200:])
        with self.lock: self.st[key]["made"] = True
        self.save()
        rc, out = self.pve.start(vmid)
        if rc != 0: return self.fail(key, "bật máy lỗi: " + out[-200:])
        log("MẪU-%d: đã bật — %s" % (jid, "Windows tự cài từ ISO (20–40 phút)" if it["src"] == "iso" else "chờ Windows lên để đưa vé"))

    def job_wait(self, vmid, cond, secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            if cond(): return True
            time.sleep(3)
        return cond()

    def _seal(self, key, lab, vmid, tpl, uniq):
        """Máy ảo đang chạy → máy mẫu <tpl>: xoá mã máy trong máy (qua guest agent) → tắt → gỡ ISO → máy mẫu cũ thành <tên>-cu → đặt tên → chuyển thành mẫu.
        True = xong; lỗi → ghi lỗi (self.fail) và trả None."""
        vm = self.pve.vms().get(vmid)
        if not vm: return self.fail(key, "không thấy máy ảo %d" % vmid)
        if vm["template"]: return True
        if vm["status"] != "running":
            rc, out = self.pve.start(vmid)
            if rc != 0: return self.fail(key, "bật máy để xoá mã máy lỗi: " + out[-200:])
        if not self.job_wait(vmid, lambda: self.pve.ga_ping(vmid), 600):
            return self.fail(key, "QEMU guest agent trong máy mẫu không trả lời — chưa xoá được mã máy, chưa lưu")
        self.pve.ga_exec(vmid, ["taskkill", "/f", "/im", "pythonw.exe"])            # dừng agent CloudBlue (để nó không ghi lại mã máy)
        base = self.c["seed_path"].rsplit("\\", 1)[0]
        for fn in ("identity.json", "seed.json", "rent.json"):
            rc, out = self.pve.ga_write(vmid, base + "\\" + fn, "{}")
            if rc != 0 and fn == "identity.json": return self.fail(key, "xoá mã máy trong máy mẫu lỗi: " + out[-200:])
        if has_identity(self.pve.ga_read(vmid, base + "\\identity.json")):
            return self.fail(key, "máy mẫu vẫn còn mã máy sau khi xoá — chưa lưu")
        log("%s: đã xoá mã máy trong máy, tắt máy" % lab)
        rc, out = self.pve.shutdown(vmid)
        if not self.job_wait(vmid, lambda: (self.pve.vms().get(vmid) or {}).get("status") == "stopped", 300):
            rc, out = self.pve.stop(vmid)
            if not self.job_wait(vmid, lambda: (self.pve.vms().get(vmid) or {}).get("status") == "stopped", 60):
                return self.fail(key, "không tắt được máy mẫu: " + out[-200:])
        for dev in self.pve.cdroms(vmid):
            rc, out = self.pve.eject(vmid, dev)
            if rc != 0: return self.fail(key, "gỡ ISO lỗi: " + out[-200:])
        vms = self.pve.vms()
        old = [k for k, v in vms.items() if v["name"] == tpl and k != vmid]
        if old:
            bak = tpl + "-cu"
            for k, v in vms.items():
                if v["name"] == bak and v["template"] and k != vmid:
                    rc, out = self.pve.destroy(k)                                   # bỏ bản lưu cũ hơn (còn VPS nhân bản liên kết thì đổi tên)
                    if rc != 0: self.pve.set_name(k, "%s-cu%s" % (tpl, uniq))
            for k in old:
                rc, out = self.pve.set_name(k, bak)
                if rc != 0: return self.fail(key, "đổi tên máy mẫu cũ lỗi: " + out[-200:])
            log("%s: máy mẫu cũ %s → %s (giữ 1 bản dự phòng)" % (lab, tpl, bak))
        rc, out = self.pve.set_name(vmid, tpl)
        if rc != 0: return self.fail(key, "đặt tên máy mẫu lỗi: " + out[-200:])
        rc, out = self.pve.make_template(vmid)
        if rc != 0: return self.fail(key, "chuyển thành máy mẫu lỗi: " + out[-200:])
        return True

    def job_save(self, it, vmid):
        """Lưu máy ảo tạm thành máy mẫu (việc từ bảng điều khiển máy mẫu trên web)."""
        jid = int(it["id"]); key = "t%d" % jid; tpl = it["tpl"]
        if not self._seal(key, "MẪU-%d" % jid, vmid, tpl, "%d" % jid): return
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "saved": True}
        self.save()
        log("MẪU-%d: ĐÃ LƯU máy mẫu %s (máy ảo %d)" % (jid, tpl, vmid))

    def job_cancel(self, jid, vmid):
        key = "t%d" % jid
        if vmid and vmid in self.pve.vms() and not self.pve.vms()[vmid]["template"]:
            log("MẪU-%d: huỷ — xoá máy ảo tạm %d" % (jid, vmid))
            rc, out = self.pve.destroy(vmid)
            if rc != 0: return self.fail(key, "xoá máy ảo tạm lỗi: " + out[-200:])
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "cancelled": True}
        self.save()

    def job_seed(self, key, vmid, it):
        s = self.st.get(key) or {}
        if not s.get("ticket") or not s.get("sent") or s.get("seeded") or not self.pve.ga_ping(vmid): return
        base = self.c["seed_path"].rsplit("\\", 1)[0]
        if has_identity(self.pve.ga_read(vmid, base + "\\identity.json")): return     # agent đã có mã máy (đăng ký rồi) → thôi
        rc, out = self.pve.ga_write(vmid, self.c["seed_path"], json.dumps({"hw": it["hw"], "ticket": s["ticket"]}))
        if rc != 0: return                                                                # Windows còn đang cài (agent chưa có) → lần sau
        with self.lock: s["seeded"] = True; s["t_seed"] = time.time()
        log("MẪU-%s: đã đưa vé vào máy mẫu → agent CloudBlue tự đăng ký" % key[1:]); self.save()

    def reconcile_jobs(self, vms, tpls):
        rep = []
        for it in self.jobs:
            if not job_ok(it): continue
            jid = int(it["id"]); key = "t%d" % jid; s = self.st.get(key)
            vmid = self.job_vmid(jid, vms); vm = vms.get(vmid) if vmid else None
            if key in self.busy: rep.append({"id": jid, "state": "saving" if it["want"] == "save" else "creating"}); continue
            if it["want"] == "cancel":
                if vm and not vm["template"]: self.bg(key, self.job_cancel, jid, vmid); continue
                if s is not None:
                    with self.lock: self.st.pop(key, None)
                    self.save()
                rep.append({"id": jid, "state": "cancelled"}); continue
            if s and s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                rep.append({"id": jid, "state": "error", "err": s["err"]}); continue
            if s and s.get("err"):
                with self.lock: s.pop("err", None)
            if it["want"] == "save":
                if (s or {}).get("saved") or (vm and vm["template"] and vm["name"] == it["tpl"]):
                    rep.append({"id": jid, "state": "saved"}); continue
                if not vm: rep.append({"id": jid, "state": "error", "err": "không thấy máy ảo của máy mẫu này trên máy chủ"}); continue
                self.bg(key, self.job_save, dict(it), vmid); rep.append({"id": jid, "state": "saving"}); continue
            if not vm:
                if (s or {}).get("made"): rep.append({"id": jid, "state": "missing"}); continue
                tid = tpls.get(it["tpl"]) if it["src"] == "tpl" else None
                if it["src"] == "tpl" and tid is None:
                    rep.append({"id": jid, "state": "error", "err": "máy chủ không có máy mẫu " + it["tpl"]}); continue
                self.bg(key, self.job_create, dict(it), tid); rep.append({"id": jid, "state": "creating"}); continue
            if vm["template"]: rep.append({"id": jid, "state": "error", "err": "máy ảo này đã thành máy mẫu"}); continue
            if s is None:                                                    # mất sổ (cài lại cbhost) → nhận lại máy ảo đang có
                s = {"vmid": vmid, "made": True, "ticket": None, "sent": False, "seeded": False}
                with self.lock: self.st[key] = s
                self.save()
            running = vm["status"] == "running"
            if not running:
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(key, "bật máy lỗi: " + out[-200:]); rep.append({"id": jid, "state": "error", "err": "bật máy lỗi"}); continue
                running = True
            r = {"id": jid, "state": "running"}
            if it.get("enrolled") is True:
                if s.get("ticket"):
                    with self.lock: s["ticket"] = None; s["sent"] = False; s["seeded"] = False
                    self.save()
            else:
                if not s.get("ticket"):
                    with self.lock: s["ticket"] = secrets.token_hex(24); s["sent"] = False; s["seeded"] = False
                    self.save()
                r["ticket_hash"] = hashlib.sha256(s["ticket"].encode()).hexdigest()
                if s.get("sent") and not s.get("seeded"): self.job_seed(key, vmid, it)
            rep.append(r)
        return rep

    # ---- TỰ DỰNG máy mẫu từ file ISO máy mẫu có trên máy chủ (cấu hình auto_tpl — ISO CloudBlue-Proxmox đặt sẵn): không cần web, không cần bấm
    def auto_create(self, tag, iso):
        key = "a" + tag; tpl = "tpl-" + tag
        vms = self.pve.vms()
        with self.lock:                                                # chọn số máy ảo + ghi sổ trong 1 lần khoá: 2 bản dựng cùng lúc không trùng số
            vmid = self.c["tpl_vmid_from"] + 500
            used = [int((x or {}).get("vmid") or 0) for k, x in self.st.items() if k[:1] in ("t", "a") and k != key]
            while vmid in vms or vmid in used: vmid += 1
            s = self.st.setdefault(key, {}); s.pop("err", None)
            s.update({"vmid": vmid, "made": False, "t_build": time.time(), "tries": int(s.get("tries") or 0) + 1})
        self.save()
        stg = self.pve.image_storage()
        if not stg: return self.fail(key, "máy chủ không có ổ chứa máy ảo (images)")
        it = {"tpl": tpl, "iso": iso, "cores": 2, "ram_mb": 2048, "disk_gb": 20, "hw": hashlib.sha256(("cbauto|%s|%s" % (tag, self.sec)).encode()).hexdigest()}
        log("MẪU-%s: TỰ DỰNG — tạo máy ảo %d từ ISO %s" % (tag, vmid, iso))
        rc, out = self.pve.create_tpl_vm(vmid, "cbmau-" + tag, it, stg)
        if rc != 0: return self.fail(key, "tạo máy ảo lỗi: " + out[-200:])
        with self.lock: self.st[key]["made"] = True
        self.save()
        rc, out = self.pve.start(vmid)
        if rc != 0: return self.fail(key, "bật máy lỗi: " + out[-200:])
        log("MẪU-%s: đã bật — Windows tự cài từ ISO (20–40 phút), xong sẽ tự thành máy mẫu %s" % (tag, tpl))

    def auto_save(self, tag, vmid):
        key = "a" + tag; tpl = "tpl-" + tag
        if not self._seal(key, "MẪU-" + tag, vmid, tpl, tag): return
        with self.lock: self.st[key] = {"vmid": vmid, "made": True, "done": True, "t_done": time.time()}
        self.save()
        log("MẪU-%s: ĐÃ TỰ DỰNG XONG máy mẫu %s (máy ảo %d)" % (tag, tpl, vmid))

    def auto_drop(self, tag, vmid):
        key = "a" + tag
        log("MẪU-%s: quá %d giờ Windows chưa cài xong — xoá máy ảo %d để dựng lại" % (tag, AUTO_WAIT_S // 3600, vmid))
        rc, out = self.pve.stop(vmid)
        rc, out = self.pve.destroy(vmid)
        if rc != 0: return self.fail(key, "xoá máy ảo dựng dở lỗi: " + out[-200:])
        with self.lock: s = self.st.setdefault(key, {}); s["made"] = False; s.pop("vmid", None)
        self.save()

    def reconcile_auto(self, vms, tpls):
        res = []
        if not self.c["auto_tpl"]: return res
        for iso in self.iso_list:
            m = RX_AUTO_ISO.match(str((iso or {}).get("volid") or ""))
            if not m: continue
            tag = m.group(1); tpl = "tpl-" + tag; key = "a" + tag; s = self.st.get(key) or {}
            if key in self.busy: res.append({"tag": tag, "state": "working"}); continue
            if tpl in tpls or any(v["name"] == tpl for v in vms.values()):          # đã có máy mẫu này (hoặc máy ảo trùng tên) → không làm gì
                if s and not s.get("done"):
                    with self.lock: self.st[key] = {"vmid": s.get("vmid"), "made": True, "done": True}
                    self.save()
                continue
            if s.get("done") or s.get("off"):                                       # đã dựng xong 1 lần (máy mẫu bị xoá tay sau đó) / đã bỏ cuộc → không tự làm lại
                if s.get("off"): res.append({"tag": tag, "state": "error", "err": str(s.get("err") or "")[:120]})
                continue
            if any(job_ok(j) and j.get("tpl") == tpl and j.get("want") != "cancel" for j in self.jobs): continue     # admin đang dựng bản này trên web
            if s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                res.append({"tag": tag, "state": "error", "err": str(s["err"])[:120]}); continue
            vmid = s.get("vmid") if s.get("vmid") in vms else next((k for k, v in vms.items() if v["name"] == "cbmau-" + tag and not v["template"]), None)
            vm = vms.get(vmid) if vmid else None
            if not vm:
                if int(s.get("tries") or 0) >= AUTO_TRIES:
                    with self.lock: self.st.setdefault(key, {})["off"] = True
                    self.save(); log("MẪU-%s: tự dựng %d lần chưa được — thôi. Dựng tay ở web › VPS ảo hoá › Bản Windows › Bảng điều khiển máy mẫu." % (tag, AUTO_TRIES))
                    continue
                self.bg(key, self.auto_create, tag, iso["volid"]); res.append({"tag": tag, "state": "creating"}); continue
            if not s.get("vmid") or not s.get("made"):                              # mất sổ (cài lại cbhost) → nhận lại máy ảo đang có
                with self.lock:
                    s = self.st.setdefault(key, {}); s.update({"vmid": vmid, "made": True}); s.setdefault("t_build", time.time()); s.setdefault("tries", 1)
                self.save()
            if s.get("err"):
                with self.lock: s.pop("err", None)
            if vm["status"] != "running":                                           # máy tắt giữa chừng (mất điện …) → bật lại cho cài tiếp
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(key, "bật máy lỗi: " + out[-200:]); res.append({"tag": tag, "state": "error", "err": "bật máy lỗi"}); continue
            mins = int((time.time() - float(s.get("t_build") or time.time())) / 60)
            if time.time() - float(s.get("t_chk") or 0) >= AUTO_CHK_S:
                with self.lock: s["t_chk"] = time.time()
                if self.pve.ga_ping(vmid) and self.pve.ga_read(vmid, AUTO_DONE_F) is not None:
                    self.bg(key, self.auto_save, tag, vmid); res.append({"tag": tag, "state": "saving"}); continue
                if mins * 60 > AUTO_WAIT_S:
                    self.bg(key, self.auto_drop, tag, vmid); res.append({"tag": tag, "state": "working"}); continue
            res.append({"tag": tag, "state": "installing", "min": mins})
        return res

    # ---- 1 vòng: so trạng thái web muốn với máy ảo thật
    def reconcile(self, vms, tpls):
        rep = []
        for it in self.want:
            if not item_ok(it): continue
            vid = int(it["id"]); vmid = self.vmid(vid); vm = vms.get(vmid); s = self.st.get(str(vid))
            if vid in self.busy: rep.append({"id": vid, "state": "creating", "inst": (s or {}).get("inst") or 0}); continue
            if it["want"] == "deleted":
                if vm: self.bg(vid, self.remove, vid); rep.append({"id": vid, "state": "stopped", "inst": (s or {}).get("inst") or 0})
                else:
                    if s is not None:
                        with self.lock: self.st.pop(str(vid), None)
                        self.save()
                    rep.append({"id": vid, "state": "missing", "inst": int(it["inst"])})
                continue
            if s and s.get("err") and time.time() - float(s.get("t_err") or 0) < RETRY_S:
                rep.append({"id": vid, "state": "error", "inst": s.get("inst") or 0, "err": s["err"]}); continue
            if vm and s is None:                                    # máy ảo có sẵn mà mất sổ (cài lại cbhost) → nhận lại, không tạo lại
                s = {"inst": int(it["inst"]), "boot": int(it["boot"]), "ticket": None, "sent": False, "seeded": False}
                with self.lock: self.st[str(vid)] = s
                self.save()
            if not vm or int(s.get("inst") or 0) != int(it["inst"]):
                tid = tpls.get(it["tpl"])
                if tid is None:
                    rep.append({"id": vid, "state": "error", "inst": (s or {}).get("inst") or 0, "err": "máy chủ thiếu máy mẫu " + it["tpl"]}); continue
                self.bg(vid, self.build, dict(it), tid)
                rep.append({"id": vid, "state": "creating", "inst": (s or {}).get("inst") or 0}); continue
            if s.get("err"):
                with self.lock: s.pop("err", None)
            running = vm["status"] == "running"
            if it["want"] == "running" and not running:
                rc, out = self.pve.start(vmid)
                if rc != 0: self.fail(vid, "bật máy lỗi: " + out[-200:])
                else: running = True; log("VPS-%s: bật máy ảo" % vid)
            elif it["want"] == "stopped" and running:
                rc, out = self.pve.shutdown(vmid)
                if rc != 0: self.fail(vid, "tắt máy lỗi: " + out[-200:])
                else: running = False; log("VPS-%s: tắt máy ảo" % vid)
            if int(it["boot"]) != int(s.get("boot") or 0):
                if running:
                    rc, out = self.pve.reset(vmid)
                    if rc != 0: self.fail(vid, "khởi động cứng lỗi: " + out[-200:])
                    else: log("VPS-%s: khởi động cứng" % vid)
                with self.lock: s["boot"] = int(it["boot"])
                self.save()
            r = {"id": vid, "state": "running" if running else "stopped", "inst": int(s.get("inst") or 0), "boot": int(s.get("boot") or 0)}
            if it.get("enrolled") is True:
                if s.get("ticket"):
                    with self.lock: s["ticket"] = None; s["sent"] = False; s["seeded"] = False
                    self.save()
            else:
                if not s.get("ticket"):
                    with self.lock: s["ticket"] = secrets.token_hex(24); s["sent"] = False; s["seeded"] = False
                    self.save()
                r["ticket_hash"] = hashlib.sha256(s["ticket"].encode()).hexdigest()
                if running and s.get("sent") and not s.get("seeded"): self.seed(vid, it)
            rep.append(r)
        return rep

    def poll_once(self, act=True):
        vms = self.pve.vms()
        tpls = {}
        for vid_, v in vms.items():
            if v["template"] and RX_TPL.match(v["name"]): tpls.setdefault(v["name"], vid_)
        if time.time() - self.iso_t > ISO_EVERY_S:
            try: self.iso_list = self.pve.isos()
            except Exception as e: log("đọc danh sách ISO lỗi: %s" % e)
            self.iso_t = time.time()
        self.auto = self.reconcile_auto(vms, tpls) if act else []    # tự dựng máy mẫu: không phụ thuộc web
        if not self.hello_ok:
            r = self.web.rpc("vm_host_hello", {"p_secret": self.sec, "p_info": self.pve.info()})
            if not r or not r.get("ok"):
                log("chưa lên web được: %s" % ((r or {}).get("err") or self.web.err)); return False
            self.hello_ok, self.status, self.name, self.info_t = True, r.get("status"), r.get("name"), time.time()
            log("đã lên web: máy chủ %s (%s)%s" % (self.name, r.get("id"), " — CHỜ admin duyệt ở Quản trị › VPS ảo hoá" if self.status == "new" else ""))
        rep = self.reconcile(vms, tpls) if act and self.status != "new" else []
        trep = self.reconcile_jobs(vms, tpls) if act and self.status != "new" and self.jobs_ok else []
        mem = meminfo()
        metrics = {"cpu": cpu_pct(), "ram_used_mb": int((mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)) / 1024),
                   "running": sum(1 for x in vms.values() if x["status"] == "running" and not x["template"]),
                   "tpl": sorted(t for t in tpls if t in self.tpl_need or not self.tpl_need), "iso": self.iso_list, "ver": CBHOST_VER}
        if self.auto: metrics["tpl_auto"] = self.auto[:8]
        while len(json.dumps(metrics)) > 12000 and (metrics.get("tpl_auto") or metrics["iso"]):      # web bỏ CẢ gói số đo nếu quá 16 KB → cắt bớt phần phụ
            if metrics.get("tpl_auto"): metrics.pop("tpl_auto")
            else: metrics["iso"] = metrics["iso"][:len(metrics["iso"]) // 2]
        body = {"p_secret": self.sec, "p_metrics": metrics, "p_vps": rep, "p_info": None}
        if self.jobs_ok: body["p_tpl"] = trep                     # web cũ (chưa chạy v57) không có tham số này
        if time.time() - self.info_t > 600: body["p_info"] = self.pve.info(); self.info_t = time.time()
        r = self.web.rpc("vm_host_poll", body)
        if not r or not r.get("ok"):
            if r and r.get("err") == "BAD_SECRET": self.hello_ok = False
            log("hỏi việc lỗi: %s" % ((r or {}).get("err") or self.web.err)); return False
        for x in rep if act else []:                               # web đã nhận dấu băm vé → giờ mới được đưa vé vào máy ảo
            if x.get("ticket_hash"):
                s = self.st.get(str(x["id"]))
                if s and s.get("ticket") and hashlib.sha256(s["ticket"].encode()).hexdigest() == x["ticket_hash"] and not s.get("sent"):
                    with self.lock: s["sent"] = True
                    self.save()
        for x in trep if act else []:                              # vé máy mẫu: như VPS
            if x.get("ticket_hash"):
                s = self.st.get("t%d" % x["id"])
                if s and s.get("ticket") and hashlib.sha256(s["ticket"].encode()).hexdigest() == x["ticket_hash"] and not s.get("sent"):
                    with self.lock: s["sent"] = True
                    self.save()
        for x in trep if act else []:                              # web đã ghi nhận lưu / huỷ xong → quên sổ
            if x.get("state") in ("saved", "cancelled") and not any(int(j.get("id") or 0) == x["id"] for j in (r.get("tpl_jobs") or []) if isinstance(j, dict)):
                with self.lock: self.st.pop("t%d" % x["id"], None)
                self.save()
        self.status, self.name = r.get("status") or self.status, r.get("name") or self.name
        self.want = r.get("vps") if isinstance(r.get("vps"), list) else []
        self.jobs_ok = isinstance(r.get("tpl_jobs"), list)
        self.jobs = r.get("tpl_jobs") if self.jobs_ok else []
        self.tpl_need = [t for t in (r.get("tpl") or []) if isinstance(t, str) and RX_TPL.match(t)]
        try: self.poll_s = max(5, min(120, int(r.get("poll_s") or 10)))
        except (TypeError, ValueError): self.poll_s = 10
        return True


# ---------------------------------------------------------------- tự cập nhật
def fetch_update(url=None):
    """Bản cbhost.py trên GitHub → (bản, nội dung) nếu KHÁC bản đang chạy và biên dịch được; không thì None."""
    req = urllib.request.Request((url or UPD_URL) + ("" if (url or UPD_URL).startswith("file:") else "?t=%d" % int(time.time())),
                                 headers={"User-Agent": "CloudBlue-cbhost/" + CBHOST_VER, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r: raw = r.read(2_000_001)
    if not 2000 <= len(raw) <= 2_000_000: return None
    txt = raw.decode("utf-8")
    m = re.search(r'^CBHOST_VER = "([0-9A-Za-z/._-]{1,20})"$', txt, re.M)
    if not m or m.group(1) == CBHOST_VER or "def poll_once" not in txt: return None
    compile(txt, "cbhost.py", "exec")                               # lỗi cú pháp → ném lỗi, giữ bản cũ
    return m.group(1), txt


def apply_update(ver, txt, path=None):
    path = path or os.path.abspath(__file__)
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as f: f.write(txt)
    os.chmod(tmp, 0o755); os.replace(tmp, path)
    log("đã cập nhật cbhost %s → %s" % (CBHOST_VER, ver))


def update_due(h, t_now, last):
    """Đến lúc xem bản mới chưa: dịch vụ systemd (có INVOCATION_ID), bật tự cập nhật, 1 giờ / lần, không có máy ảo nào đang dựng / xoá."""
    return (h.c.get("auto_update") and bool(os.environ.get("INVOCATION_ID")) and t_now - last >= UPD_EVERY_S and not h.busy)


def cmd_run():
    h = Host()
    log("cbhost %s chạy — node %s, gọi %s mỗi ~10 giây" % (CBHOST_VER, h.pve.node, h.web.url))
    last_upd = time.time() - UPD_EVERY_S + 120                     # bật lên 2 phút sau mới xem bản mới lần đầu
    nw = NetWatch(h.c)
    while True:
        ok = None
        try: ok = h.poll_once()
        except Exception as e: log("lỗi vòng:", e)
        for x in nw.step(ok, h.web.err): log("TỰ SỬA MẠNG (lượt %d): %s" % (nw.heals, x))
        if update_due(h, time.time(), last_upd):
            last_upd = time.time()
            try:
                u = fetch_update()
                if u:
                    apply_update(*u)
                    return 0                                        # dịch vụ (Restart=always) tự bật lại bằng bản mới
            except Exception as e:
                log("xem bản mới lỗi (giữ bản đang chạy): %s" % str(e)[:160])
        time.sleep(h.poll_s)


def cmd_update():
    try: u = fetch_update()
    except Exception as e:
        print("không lấy được bản mới: %s" % str(e)[:200]); return 1
    if not u: print("đang là bản mới nhất (%s)" % CBHOST_VER); return 0
    apply_update(*u)
    print("đã cập nhật %s → %s — bật lại dịch vụ: systemctl restart cloudblue-cbhost" % (CBHOST_VER, u[0])); return 0


def net_report(c):
    v4, v6 = default_routes()
    try: dns = resolv_servers(open(RESOLV_F, encoding="utf-8", errors="replace").read())
    except OSError: dns = []
    host = web_host(c)
    res = "địa chỉ số" if (not host or is_ip(host)) else ("được" if can_resolve(host) else "KHÔNG ĐƯỢC")
    return "mạng: IPv4 %s · IPv6 %s · địa chỉ %s · máy chủ tên (DNS) %s · phân giải tên web: %s · tự sửa mạng: %s" % (
        "có" if v4 else "KHÔNG", "có" if v6 else "không", lan_ip() or "?", ", ".join(dns) or "(trống)", res, "bật" if c.get("net_heal") else "tắt")


def cmd_net():
    """Xem tình trạng mạng + chạy NGAY 1 lượt tự sửa (như dịch vụ làm khi không gọi được web)."""
    c = conf()
    print(net_report(c))
    did = net_heal(c, 3)
    for x in did: print("đã sửa: " + x)
    if did: print(net_report(c))
    else: print("không có gì phải sửa (hoặc không sửa tự động được)")
    return 0


def cmd_status():
    h = Host(); ok = h.poll_once(act=False)                       # chỉ xem: không tạo / xoá gì (dịch vụ đang chạy lo việc đó)
    vms = h.pve.vms()
    tp = sorted(v["name"] for v in vms.values() if v["template"])
    print("cbhost %s · máy chủ: %s · trạng thái web: %s" % (CBHOST_VER, h.name or "?", {"new": "CHỜ DUYỆT (Quản trị › VPS ảo hoá › Máy chủ)", "ready": "đang nhận VPS",
          "maint": "bảo trì (không nhận VPS mới)", "off": "tắt"}.get(h.status, h.status) if ok else "chưa gọi được web (%s)" % h.web.err))
    try: print(net_report(h.c))
    except Exception as e: print("mạng: không đọc được (%s)" % str(e)[:80])
    print("máy mẫu trên Proxmox: %s" % (", ".join(tp) or "CHƯA CÓ — xem hướng dẫn dựng máy mẫu Windows"))
    if h.tpl_need: print("web cần máy mẫu: %s" % ", ".join(("%s ✓" if t in tp else "%s ✗ (thiếu)") % t for t in h.tpl_need))
    print("VPS web giao cho máy chủ này: %d" % len(h.want))
    if h.c["auto_tpl"]:
        au = {k[1:]: v for k, v in h.st.items() if k[:1] == "a" and isinstance(v, dict)}
        print("tự dựng máy mẫu từ ISO: BẬT%s" % ("".join(" · %s: %s" % (t, "xong" if v.get("done") else ("LỖI — " + str(v.get("err"))[:80]) if v.get("err") else
              "đang cài Windows (máy ảo %s)" % v.get("vmid")) for t, v in sorted(au.items())) or " · chưa có ISO máy mẫu nào trong kho ISO"))
    return 0 if ok else 1


def main(argv):
    cmd = argv[0] if argv else "run"
    if cmd == "run": return cmd_run()
    if cmd == "status": return cmd_status()
    if cmd == "once": return 0 if Host().poll_once() else 1
    if cmd == "update": return cmd_update()
    if cmd == "net": return cmd_net()
    if cmd in ("-v", "--version", "version"): print(CBHOST_VER); return 0
    print("Lệnh: run | status | once | update | net | version"); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
