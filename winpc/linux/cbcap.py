# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbcap.py — CloudBlue PC (CachyOS): QUAY MÀN HÌNH + CHUỘT / PHÍM, chạy BẰNG TÀI KHOẢN KHÁCH trong phiên KDE (Wayland).
#  cbremote.py (root) mở chương trình này khi có người xem; 2 bên nói chuyện qua 1 ổ cắm (socketpair) truyền sẵn (--fd N).
#  KHÔNG giữ bí mật nào (mã máy, khoá… nằm ở /opt/cloudblue — chỉ root đọc được).
#    · cổng XDG "RemoteDesktop" của KDE: mã ứng dụng vn.cloudblue.remote đã được CẤP QUYỀN SẴN (bảng kde-authorized, có từ
#      Plasma 6.3) → không hiện hộp hỏi "Cho phép điều khiển?" → luồng PipeWire của màn hình + đường bơm chuột / phím
#    · GStreamer pipewiresrc → thu cỡ → khung thô I420 → ffmpeg (x264, CÙNG tham số nén với máy Windows do root đưa sang) → RTP → UDP
#      127.0.0.1:<cổng root mở>. Không có ffmpeg/libx264 thì nén luôn bằng GStreamer (x264enc → rtph264pay → udpsink).
#  Lệnh (1 gói JSON / lần, root → đây): start / stop / move / btn / wheel / key / text / clip_set / clip_get / size / bye
#  Chạy thử:  python3 cbcap.py probe [giây]   → in từng bước dạng JSON (CI)
# =====================================================================================================
import json, os, random, socket, struct, subprocess, sys, threading, time, urllib.parse

CAP_VER = "22.11f"
APP_ID = "vn.cloudblue.remote"
PORTAL, PORTAL_PATH = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
RD, SC = "org.freedesktop.portal.RemoteDesktop", "org.freedesktop.portal.ScreenCast"
STORE = ("org.freedesktop.impl.portal.PermissionStore", "/org/freedesktop/impl/portal/PermissionStore", "org.freedesktop.impl.portal.PermissionStore")


class DBusError(Exception):
    pass


# ====================================================================================== D-Bus tối thiểu (không cần thư viện ngoài)
ALIGN = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4, "x": 8, "t": 8, "d": 8, "s": 4, "o": 4, "g": 1, "a": 4, "(": 8, "{": 8, "v": 1, "h": 4}
FIX = {"b": (4, "I"), "n": (2, "h"), "q": (2, "H"), "i": (4, "i"), "u": (4, "I"), "x": (8, "q"), "t": (8, "Q"), "d": (8, "d"), "h": (4, "I")}


def _end(sig, i):
    """Vị trí ngay sau kiểu hoàn chỉnh bắt đầu tại sig[i]."""
    c = sig[i]
    if c == "a": return _end(sig, i + 1)
    if c in "({":
        depth, j = 0, i
        while True:
            if sig[j] in "({": depth += 1
            elif sig[j] in ")}": depth -= 1
            j += 1
            if depth == 0: return j
    return i + 1


def split_sig(sig):
    out, i = [], 0
    while i < len(sig):
        j = _end(sig, i); out.append(sig[i:j]); i = j
    return out


def _pad(buf, n): buf.extend(b"\0" * ((-len(buf)) % n))


def pack(e, buf, t, v, fds):
    """Ghi giá trị v kiểu t (biến thể = (chữ ký, giá trị); a{..} = dict) vào buf."""
    c = t[0]
    if c == "y": buf.extend(struct.pack("B", int(v) & 0xFF)); return
    if c in FIX:
        size, fmt = FIX[c]
        _pad(buf, size)
        if c == "h": fds.append(int(v)); v = len(fds) - 1
        buf.extend(struct.pack(e + fmt, (1 if v else 0) if c == "b" else v)); return
    if c in "so":
        _pad(buf, 4); d = str(v).encode("utf-8"); buf.extend(struct.pack(e + "I", len(d)) + d + b"\0"); return
    if c == "g":
        d = str(v).encode("ascii"); buf.extend(struct.pack("B", len(d)) + d + b"\0"); return
    if c == "v":
        sig, val = v
        pack(e, buf, "g", sig, fds); pack(e, buf, sig, val, fds); return
    if c == "a":
        _pad(buf, 4); at = len(buf); buf.extend(b"\0\0\0\0")
        et = t[1:]
        _pad(buf, ALIGN[et[0]]); start = len(buf)
        if et[0] == "{":
            kt, vt = split_sig(et[1:-1])
            for k, x in (v.items() if isinstance(v, dict) else v):
                _pad(buf, 8); pack(e, buf, kt, k, fds); pack(e, buf, vt, x, fds)
        else:
            for x in v: pack(e, buf, et, x, fds)
        struct.pack_into(e + "I", buf, at, len(buf) - start); return
    if c == "(":
        _pad(buf, 8)
        for st, x in zip(split_sig(t[1:-1]), v): pack(e, buf, st, x, fds)
        return
    raise DBusError("kieu chua ho tro: " + t)


def unpack(e, buf, pos, t):
    """→ (giá trị, vị trí kế). Vị trí tính từ ĐẦU GÓI (căn lề theo đầu gói, như chuẩn D-Bus)."""
    c = t[0]
    if c == "y": return buf[pos], pos + 1
    if c in FIX:
        size, fmt = FIX[c]
        pos += (-pos) % size
        v = struct.unpack_from(e + fmt, buf, pos)[0]
        return (bool(v) if c == "b" else v), pos + size
    if c in "so":
        pos += (-pos) % 4
        n = struct.unpack_from(e + "I", buf, pos)[0]; pos += 4
        return bytes(buf[pos:pos + n]).decode("utf-8", "replace"), pos + n + 1
    if c == "g":
        n = buf[pos]; pos += 1
        return bytes(buf[pos:pos + n]).decode("ascii"), pos + n + 1
    if c == "v":
        sig, pos = unpack(e, buf, pos, "g")
        return unpack(e, buf, pos, sig)
    if c == "a":
        pos += (-pos) % 4
        n = struct.unpack_from(e + "I", buf, pos)[0]; pos += 4
        et = t[1:]
        pos += (-pos) % ALIGN[et[0]]
        end = pos + n
        if et[0] == "{":
            kt, vt = split_sig(et[1:-1]); out = {}
            while pos < end:
                pos += (-pos) % 8
                k, pos = unpack(e, buf, pos, kt); x, pos = unpack(e, buf, pos, vt); out[k] = x
            return out, end
        out = []
        while pos < end:
            x, pos = unpack(e, buf, pos, et); out.append(x)
        return out, end
    if c == "(":
        pos += (-pos) % 8; out = []
        for st in split_sig(t[1:-1]):
            x, pos = unpack(e, buf, pos, st); out.append(x)
        return tuple(out), pos
    raise DBusError("kieu chua ho tro: " + t)


def build(mtype, serial, fields, sig="", args=(), flags=0):
    """Gói D-Bus hoàn chỉnh (little-endian) → (bytes, [fd])."""
    body, fds = bytearray(), []
    for t, v in zip(split_sig(sig), args): pack("<", body, t, v, fds)
    f = dict(fields)
    if sig: f[8] = ("g", sig)
    if fds: f[9] = ("u", len(fds))
    head = bytearray(b"l" + bytes([mtype, flags, 1]) + struct.pack("<II", len(body), serial))
    pack("<", head, "a(yv)", sorted(f.items()), [])
    _pad(head, 8)
    return bytes(head + body), fds


def parse(buf):
    """Tách 1 gói từ đầu buf → (gói dict, số byte) hoặc (None, 0) khi chưa đủ."""
    if len(buf) < 16: return None, 0
    e = "<" if buf[0:1] == b"l" else ">"
    blen, serial, flen = struct.unpack_from(e + "III", buf, 4)
    hlen = 16 + flen; hlen += (-hlen) % 8
    total = hlen + blen
    if len(buf) < total: return None, 0
    fields, _ = unpack(e, buf, 12, "a(yv)")
    f = {k: v for k, v in fields}
    m = {"type": buf[1], "flags": buf[2], "serial": serial, "path": f.get(1), "iface": f.get(2), "member": f.get(3), "error": f.get(4),
         "reply": f.get(5), "sender": f.get(7), "sig": f.get(8) or "", "nfds": f.get(9) or 0, "body": []}
    pos = hlen
    for t in split_sig(m["sig"]):
        x, pos = unpack(e, buf, pos, t); m["body"].append(x)
    return m, total


class DBus:
    """1 kết nối tới bus phiên của người dùng: gọi hàm, chờ tín hiệu, nhận fd (SCM_RIGHTS)."""
    def __init__(self, address=None, timeout=10.0):
        addr = address or os.environ.get("DBUS_SESSION_BUS_ADDRESS") or "unix:path=/run/user/%d/bus" % os.getuid()
        target = None
        for part in addr.split(";"):
            if not part.startswith("unix:"): continue
            kv = dict(x.split("=", 1) for x in part[5:].split(",") if "=" in x)
            if "path" in kv: target = urllib.parse.unquote(kv["path"]); break
            if "abstract" in kv: target = "\0" + urllib.parse.unquote(kv["abstract"]); break
        if not target: raise DBusError("khong doc duoc dia chi bus: %r" % addr)
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout); self.s.connect(target)
        self.rbuf = b""; self.fds = []; self.pending = []; self.serial = 0; self.lock = threading.RLock(); self.wlock = threading.Lock()
        self.s.sendall(b"\0AUTH EXTERNAL " + str(os.getuid()).encode().hex().encode() + b"\r\n")
        if not self._line().startswith(b"OK"): raise DBusError("bus tu choi xac thuc")
        self.s.sendall(b"NEGOTIATE_UNIX_FD\r\n")
        self.unix_fd = self._line().startswith(b"AGREE_UNIX_FD")
        self.s.sendall(b"BEGIN\r\n")
        self.name = self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "Hello")[0]

    def _line(self):
        while b"\r\n" not in self.rbuf:
            d = self.s.recv(4096)
            if not d: raise DBusError("bus dong ket noi")
            self.rbuf += d
        line, self.rbuf = self.rbuf.split(b"\r\n", 1)
        return line

    def close(self):
        try: self.s.close()
        except OSError: pass
        for fd in self.fds:
            try: os.close(fd)
            except OSError: pass
        self.fds = []

    def send(self, mtype, fields, sig="", args=(), flags=0):
        with self.wlock:
            self.serial += 1; serial = self.serial
            data, fds = build(mtype, serial, fields, sig, args, flags)
            if fds: socket.send_fds(self.s, [data], fds)
            else: self.s.sendall(data)
            return serial

    def _read(self, deadline):
        """Đọc thêm dữ liệu (kèm fd) cho tới khi có 1 gói hoàn chỉnh → gói."""
        while True:
            m, n = parse(self.rbuf)
            if m is not None:
                self.rbuf = self.rbuf[n:]
                m["fds"] = self.fds[:m["nfds"]]; del self.fds[:m["nfds"]]
                return m
            left = deadline - time.time()
            if left <= 0: raise DBusError("qua thoi gian cho bus")
            self.s.settimeout(min(left, 5.0))
            try: data, fds, _, _ = socket.recv_fds(self.s, 65536, 16)
            except socket.timeout: continue
            if not data: raise DBusError("bus dong ket noi")
            self.rbuf += data; self.fds.extend(fds)

    def take(self, pred, timeout):
        """Gói đầu tiên thoả pred (xem các gói đã nhận trước rồi đọc tiếp); gói khác giữ lại."""
        deadline = time.time() + timeout
        with self.lock:
            for i, m in enumerate(self.pending):
                if pred(m): return self.pending.pop(i)
            while True:
                m = self._read(deadline)
                if pred(m): return m
                if m["type"] in (2, 3, 4):
                    self.pending.append(m); del self.pending[:-200]

    def call(self, dest, path, iface, member, sig="", args=(), timeout=15.0, with_fds=False):
        s = self.send(1, {1: ("o", path), 2: ("s", iface), 3: ("s", member), 6: ("s", dest)}, sig, args)
        m = self.take(lambda m: m["type"] in (2, 3) and m["reply"] == s, timeout)
        if m["type"] == 3:
            for fd in m["fds"]: os.close(fd)
            raise DBusError("%s: %s" % (m["error"], m["body"][0] if m["body"] else ""))
        return (m["body"], m["fds"]) if with_fds else m["body"]

    def call_noreply(self, dest, path, iface, member, sig="", args=()):
        self.send(1, {1: ("o", path), 2: ("s", iface), 3: ("s", member), 6: ("s", dest)}, sig, args, flags=1)

    def add_match(self, rule):
        self.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule])

    def get_prop(self, dest, path, iface, name):
        return self.call(dest, path, "org.freedesktop.DBus.Properties", "Get", "ss", [iface, name])[0]


# ====================================================================================== cổng XDG RemoteDesktop (KDE)
class PortalError(Exception):
    pass


class Portal:
    """1 phiên RemoteDesktop + ScreenCast: luồng màn hình (PipeWire) + bơm chuột / phím. Mở khi có người xem, đóng khi hết."""
    def __init__(self, bus, log=None):
        self.b, self.log = bus, log or (lambda m: None)
        self.session = None; self.node = None; self.size = (0, 0); self.app = None; self.inhibit = []
        self.devices = None; self.cursor = (0, 0)                     # thiết bị KDE cho dùng (1 phím, 2 chuột) · (kiểu con trỏ có, kiểu đã chọn)

    def _token(self): return "cb%d" % random.randrange(10 ** 9)

    def _request(self, iface, member, sig, head, options, timeout=20.0):
        tok = self._token()
        path = "%s/request/%s/%s" % (PORTAL_PATH, self.b.name.lstrip(":").replace(".", "_"), tok)
        self.b.add_match("type='signal',interface='org.freedesktop.portal.Request',member='Response',path='%s'" % path)
        opts = dict(options); opts["handle_token"] = ("s", tok)
        self.b.call(PORTAL, PORTAL_PATH, iface, member, sig, list(head) + [opts])
        try:
            m = self.b.take(lambda m: m["type"] == 4 and m["path"] == path and m["member"] == "Response", timeout)
        except DBusError:
            raise PortalError("%s.%s: KDE chua tra loi sau %d giay (dang hien hop hoi quyen?)" % (iface.rsplit(".", 1)[-1], member, timeout))
        code, results = m["body"]
        if code != 0: raise PortalError("%s.%s bi tu choi (ma %d)" % (iface.rsplit(".", 1)[-1], member, code))
        return results

    def authorize(self):
        """Cấp quyền sẵn: đăng ký mã ứng dụng (xdg-desktop-portal ≥ 1.19) + ghi vào bảng kde-authorized (Plasma ≥ 6.3)."""
        try:
            self.b.call(PORTAL, PORTAL_PATH, "org.freedesktop.host.portal.Registry", "Register", "sa{sv}", [APP_ID, {}])
            self.app = APP_ID
        except DBusError as e:
            self.app = ""
            self.log("cong XDG chua co Registry (%s) -> cap quyen cho ung dung khong ma" % str(e)[:80])
        self.b.call(*STORE, "SetPermission", "sbssas", ["kde-authorized", True, "remote-desktop", self.app, ["yes"]])
        return self.app

    def start(self, timeout=25.0):
        r = self._request(RD, "CreateSession", "a{sv}", [], {"session_handle_token": ("s", self._token())})
        self.session = str(r["session_handle"])
        self._request(RD, "SelectDevices", "oa{sv}", [self.session], {"types": ("u", 3)})                     # bàn phím + chuột
        try: modes = int(self.b.get_prop(PORTAL, PORTAL_PATH, SC, "AvailableCursorModes"))
        except (DBusError, TypeError, ValueError): modes = 2
        self.cursor = (modes, 2 if modes & 2 else 1)
        self._request(SC, "SelectSources", "oa{sv}", [self.session],
                      {"types": ("u", 1), "multiple": ("b", False), "cursor_mode": ("u", self.cursor[1])})         # 1 màn hình, con trỏ vẽ sẵn
        r = self._request(RD, "Start", "osa{sv}", [self.session, ""], {}, timeout)
        try: self.devices = int(r.get("devices"))                    # thiếu bit 2 (chuột) → cổng XDG chặn mọi lệnh chuột
        except (TypeError, ValueError): self.devices = None
        streams = r.get("streams") or []
        if not streams: raise PortalError("KDE khong giao luong man hinh nao")
        self.node = int(streams[0][0])
        sz = (streams[0][1] or {}).get("size") or (0, 0)
        self.size = (int(sz[0]), int(sz[1]))
        for dest, path, iface, member in (("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver", "Inhibit"),
                                          ("org.freedesktop.PowerManagement", "/org/freedesktop/PowerManagement/Inhibit", "org.freedesktop.PowerManagement.Inhibit", "Inhibit")):
            try: self.inhibit.append((dest, path, iface, self.b.call(dest, path, iface, member, "ss", ["CloudBlue", "dang dieu khien tu xa"])[0]))
            except DBusError: pass
        return self.node, self.size

    def pw_fd(self):
        body, fds = self.b.call(PORTAL, PORTAL_PATH, SC, "OpenPipeWireRemote", "oa{sv}", [self.session, {}], with_fds=True)
        idx = int(body[0])
        for i, fd in enumerate(fds):
            if i != idx: os.close(fd)
        return fds[idx]

    # ---- chuột / phím (không chờ trả lời: nhanh) ----
    def motion(self, x, y): self.b.call_noreply(PORTAL, PORTAL_PATH, RD, "NotifyPointerMotionAbsolute", "oa{sv}udd", [self.session, {}, self.node, float(x), float(y)])
    def button(self, code, down): self.b.call_noreply(PORTAL, PORTAL_PATH, RD, "NotifyPointerButton", "oa{sv}iu", [self.session, {}, int(code), 1 if down else 0])
    def axis(self, axis, steps): self.b.call_noreply(PORTAL, PORTAL_PATH, RD, "NotifyPointerAxisDiscrete", "oa{sv}ui", [self.session, {}, int(axis), int(steps)])
    def keycode(self, code, down): self.b.call_noreply(PORTAL, PORTAL_PATH, RD, "NotifyKeyboardKeycode", "oa{sv}iu", [self.session, {}, int(code), 1 if down else 0])
    def keysym(self, sym, down): self.b.call_noreply(PORTAL, PORTAL_PATH, RD, "NotifyKeyboardKeysym", "oa{sv}iu", [self.session, {}, int(sym), 1 if down else 0])

    def close(self):
        for dest, path, iface, cookie in self.inhibit:
            try: self.b.call(dest, path, iface, "UnInhibit", "u", [cookie], timeout=3)
            except Exception: pass
        self.inhibit = []
        if self.session:
            try: self.b.call(PORTAL, self.session, "org.freedesktop.portal.Session", "Close", timeout=3)
            except Exception: pass
        self.session = None; self.node = None


# ====================================================================================== phím Windows (VK) → mã phím Linux (evdev)
VK2EV = {0x08: 14, 0x09: 15, 0x0D: 28, 0x10: 42, 0x11: 29, 0x12: 56, 0x13: 119, 0x14: 58, 0x1B: 1, 0x20: 57, 0x21: 104, 0x22: 109, 0x23: 107, 0x24: 102,
         0x25: 105, 0x26: 103, 0x27: 106, 0x28: 108, 0x2C: 99, 0x2D: 110, 0x2E: 111, 0x5B: 125, 0x5C: 126, 0x5D: 127,
         0x6A: 55, 0x6B: 78, 0x6D: 74, 0x6E: 83, 0x6F: 98, 0x90: 69, 0x91: 70, 0xA0: 42, 0xA1: 54, 0xA2: 29, 0xA3: 97, 0xA4: 56, 0xA5: 100,
         0xAD: 113, 0xAE: 114, 0xAF: 115, 0xB0: 163, 0xB1: 165, 0xB3: 164,
         0xBA: 39, 0xBB: 13, 0xBC: 51, 0xBD: 12, 0xBE: 52, 0xBF: 53, 0xC0: 41, 0xDB: 26, 0xDC: 43, 0xDD: 27, 0xDE: 40}
VK2EV.update({0x41 + i: c for i, c in enumerate((30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44))})
VK2EV.update({0x30 + i: c for i, c in enumerate((11, 2, 3, 4, 5, 6, 7, 8, 9, 10))})
VK2EV.update({0x60 + i: c for i, c in enumerate((82, 79, 80, 81, 75, 76, 77, 71, 72, 73))})
VK2EV.update({0x70 + i: c for i, c in enumerate((59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88))})
EXT_EV = {0x0D: 96}                                           # Enter của bàn phím số (cờ mở rộng)
BTN = (0x110, 0x111, 0x112, 0x113, 0x114)                    # trái, phải, giữa, nút phụ 1, nút phụ 2

US = {" ": (57, 0), "\n": (28, 0), "\t": (15, 0), "-": (12, 0), "_": (12, 1), "=": (13, 0), "+": (13, 1), "[": (26, 0), "{": (26, 1), "]": (27, 0), "}": (27, 1),
      "\\": (43, 0), "|": (43, 1), ";": (39, 0), ":": (39, 1), "'": (40, 0), '"': (40, 1), ",": (51, 0), "<": (51, 1), ".": (52, 0), ">": (52, 1),
      "/": (53, 0), "?": (53, 1), "`": (41, 0), "~": (41, 1)}
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    US[_ch] = (VK2EV[0x41 + _i], 0); US[_ch.upper()] = (VK2EV[0x41 + _i], 1)
for _i, (_d, _s) in enumerate(zip("0123456789", ")!@#$%^&*(")):
    US[_d] = (VK2EV[0x30 + _i], 0); US[_s] = (VK2EV[0x30 + _i], 1)


def gst_src(node, w, h, fps, fd=3, fmt="BGRx"):
    """Phần đầu GStreamer: màn hình (PipeWire của KDE) → đổi màu + thu cỡ (chỉ khung THẬT) → nhịp khung đều (lặp khung khi màn hình đứng yên)
       → hàng chờ BỎ KHUNG CŨ (bộ nén chậm hơn nhịp khung thì bỏ bớt, KHÔNG dồn: dồn thì người xem thấy hình trễ dần — CI 22.11f: con trỏ trễ > 2,5 giây).
       Khung thô đưa sang ffmpeg dùng BGRx (4 byte/điểm: mỗi dòng không có byte đệm, ffmpeg đọc đúng với mọi chiều rộng)."""
    return ["pipewiresrc", "fd=%d" % fd, "path=%d" % node, "do-timestamp=true", "keepalive-time=250", "always-copy=true", "!",
            "queue", "max-size-buffers=2", "max-size-bytes=0", "max-size-time=0", "leaky=downstream", "!",
            "videoconvert", "!", "videoscale", "!", "video/x-raw,format=%s,width=%d,height=%d" % (fmt, w, h), "!",
            "videorate", "drop-only=false", "!", "video/x-raw,framerate=%d/1" % fps, "!",
            "queue", "max-size-buffers=2", "max-size-bytes=0", "max-size-time=0", "leaky=downstream"]


def gst_pipeline(node, w, h, fps, kbps, port, fd=3):
    """Chỉ dùng GStreamer (máy không có ffmpeg + libx264): x264enc độ trễ thấp → RTP → UDP nội bộ."""
    gop = max(int(fps * (2 if kbps < 450 else 1)), 10)
    vbv = max(200, min(1000, int(6000 // max(fps, 1))))
    return ["gst-launch-1.0", "-q"] + gst_src(node, w, h, fps, fd, "I420") + [
            "!", "x264enc", "tune=zerolatency", "speed-preset=superfast", "bitrate=%d" % kbps, "vbv-buf-capacity=%d" % vbv, "key-int-max=%d" % gop,
            "bframes=0", "threads=2", "sliced-threads=false", "!",
            "video/x-h264,profile=constrained-baseline", "!",
            "rtph264pay", "config-interval=-1", "mtu=1300", "pt=96", "!",
            "udpsink", "host=127.0.0.1", "port=%d" % port, "sync=false", "async=false"]


def raw_pipeline(node, w, h, fps, fd=3):
    """GStreamer chỉ lấy khung thô BGRx ra stdout (ffmpeg nén)."""
    return ["gst-launch-1.0", "-q"] + gst_src(node, w, h, fps, fd, "BGRx") + ["!", "fdsink", "fd=1", "sync=false"]


def ff_encode(w, h, fps, enc_args, port):
    """ffmpeg đọc khung thô từ stdin → nén theo enc_args (của pcremote, root đưa sang) → RTP về 127.0.0.1:port (như máy Windows)."""
    safe = [str(a) for a in enc_args if isinstance(a, (str, int)) and len(str(a)) < 200][:60]
    return (["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-thread_queue_size", "2", "-f", "rawvideo", "-pix_fmt", "bgr0", "-video_size", "%dx%d" % (w, h),
             "-framerate", str(fps), "-i", "pipe:0", "-vf", "format=yuv420p"] + safe +
            ["-an", "-bsf:v", "dump_extra=freq=keyframe", "-f", "rtp", "-rtpflags", "skip_rtcp", "-payload_type", "96", "rtp://127.0.0.1:%d?pkt_size=1300" % port])


_TOOLS = {}
_TOOLS_T = [0.0]                                                  # lúc dò gần nhất
TOOLS_RETRY_S = 60                                                # thiếu công cụ → dò lại sau chừng này giây
TEST_SRC = os.environ.get("CBCAP_TEST_SRC") == "1"            # bộ thử: hình thử của ffmpeg thay màn hình thật (không có KDE / GStreamer)


def test_src(w, h, fps):
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-re", "-f", "lavfi", "-i", "testsrc2=size=%dx%d:rate=%d" % (w, h, fps),
            "-pix_fmt", "bgr0", "-f", "rawvideo", "pipe:1"]


def tools():
    """Có những phần nào: các phần tử GStreamer + ffmpeg có libx264. Đủ thì nhớ luôn; THIẾU thì dò lại sau TOOLS_RETRY_S giây
       (agent đang tự cài gst-plugin-pipewire — cài xong là quay được, không phải chạy lại)."""
    if TEST_SRC: return {"pipewiresrc": True, "videoconvert": True, "videoscale": True, "videorate": True, "fdsink": True, "ffmpeg_x264": True}
    if _TOOLS and (pick_mode(_TOOLS) or time.time() - _TOOLS_T[0] < TOOLS_RETRY_S): return dict(_TOOLS)
    t = {}
    for el in ("pipewiresrc", "videoconvert", "videoscale", "videorate", "fdsink", "x264enc", "rtph264pay", "udpsink"):
        try: t[el] = subprocess.run(["gst-inspect-1.0", "--exists", el], capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired): t[el] = False
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, timeout=30)
        t["ffmpeg_x264"] = r.returncode == 0 and b"libx264" in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        t["ffmpeg_x264"] = False
    _TOOLS.clear(); _TOOLS.update(t); _TOOLS_T[0] = time.time()
    return dict(_TOOLS)


def pick_mode(t=None):
    """"ff" (GStreamer lấy hình + ffmpeg nén) · "gst" (chỉ GStreamer) · None (thiếu)."""
    t = t or tools()
    base = all(t.get(k) for k in ("pipewiresrc", "videoconvert", "videoscale", "videorate"))
    if base and t.get("fdsink") and t.get("ffmpeg_x264"): return "ff"
    if base and all(t.get(k) for k in ("x264enc", "rtph264pay", "udpsink")): return "gst"
    return None


def X264_ARGS(fps, kbps):
    """Tham số x264 giống pcremote.enc_args("x264") (chỉ dùng khi chạy thử một mình — bình thường root đưa sang)."""
    gop = str(max(int(fps * (2 if kbps < 450 else 1)), 10))
    return ["-c:v", "libx264", "-preset", "superfast", "-tune", "zerolatency", "-profile:v", "baseline", "-threads", "1", "-x264-params",
            "sliced-threads=0:keyint=%s:min-keyint=%s:scenecut=0:bframes=0:rc-lookahead=0:sync-lookahead=0:repeat-headers=1" % (gop, gop),
            "-b:v", "%dk" % kbps, "-maxrate", "%dk" % kbps, "-bufsize", "%dk" % max(kbps * 6 // max(fps, 1), 96)]


def have_tools():
    """Máy đủ công cụ quay + nén không → (đủ?, chữ báo)."""
    t = tools(); m = pick_mode(t)
    if m: return True, "du (%s)" % ("GStreamer + ffmpeg x264" if m == "ff" else "GStreamer x264")
    need = ("pipewiresrc", "videoconvert", "videoscale", "videorate", "fdsink", "ffmpeg_x264")      # đường chính "ff" (x264enc… chỉ là đường phụ)
    return False, "thieu " + ", ".join(k for k in need if not t.get(k))


# ====================================================================================== phần chạy (theo lệnh của root)
class Cap:
    def __init__(self, log=None, bus_addr=None):
        self.log = log or (lambda m: None); self.bus_addr = bus_addr
        self.bus = None; self.portal = None; self.proc = None; self.src = None; self.mode = None; self.lock = threading.RLock()
        self.acc = [0.0, 0.0]; self.wl = None

    def open(self):
        with self.lock:
            if self.portal is not None and self.portal.session: return self.portal.size
            self.bus = DBus(self.bus_addr)
            self.portal = Portal(self.bus, self.log)
            self.portal.authorize()
            self.portal.start()
            self.log("phien KDE: luong man hinh %d (%dx%d), ma ung dung %r, thiet bi %s, con tro %s/%s" % (self.portal.node, self.portal.size[0], self.portal.size[1], self.portal.app,
                     self.portal.devices, self.portal.cursor[1], self.portal.cursor[0]))
            return self.portal.size

    def start(self, w, h, fps, kbps, port, enc_args=None):
        """Bật bộ quay + nén. → pid tiến trình theo dõi (ffmpeg hoặc gst-launch); chết = báo root bật lại."""
        with self.lock:
            self.stop()
            self.open()
            mode = pick_mode()
            if mode is None: raise RuntimeError("may thieu cong cu quay man hinh: %s" % have_tools()[1])
            if mode == "ff" and not enc_args: mode = "gst" if pick_mode(dict(tools(), ffmpeg_x264=False)) else "ff"
            fd = self.portal.pw_fd()
            try:
                os.set_inheritable(fd, True)
                if mode == "ff":
                    src = subprocess.Popen(test_src(w, h, fps) if TEST_SRC else raw_pipeline(self.portal.node, w, h, fps, fd), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(fd,))
                    enc = subprocess.Popen(ff_encode(w, h, fps, enc_args or [], port), stdin=src.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    src.stdout.close()
                    self.src, self.proc = src, enc
                    threading.Thread(target=self._errlog, args=(src, "gstreamer"), daemon=True).start()
                else:
                    self.src = None
                    self.proc = subprocess.Popen(gst_pipeline(self.portal.node, w, h, fps, kbps, port, fd), stdin=subprocess.DEVNULL,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, pass_fds=(fd,))
            finally:
                os.close(fd)
            self.mode = mode
            threading.Thread(target=self._errlog, args=(self.proc, "ffmpeg" if mode == "ff" else "gstreamer"), daemon=True).start()
            return self.proc.pid

    def _errlog(self, proc, name):
        lines = []
        try:
            for ln in iter(proc.stderr.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s: lines.append(s); del lines[:-4]
        except Exception: pass
        if lines: self.log("%s: %s" % (name, " | ".join(lines)[-300:]))

    def alive(self):
        if self.proc is None or self.proc.poll() is not None: return False
        return self.src is None or self.src.poll() is None

    def stop(self):
        with self.lock:
            procs, self.proc, self.src = (self.src, self.proc), None, None
            for p in procs:
                if p is not None and p.poll() is None:
                    p.terminate()
                    try: p.wait(2)
                    except subprocess.TimeoutExpired: p.kill()

    def close(self):
        with self.lock:
            self.stop()
            if self.portal is not None: self.portal.close()
            if self.bus is not None: self.bus.close()
            self.portal = self.bus = None

    # ---- chuột / phím: toạ độ người xem 0..65535 trên cả màn hình ----
    def move(self, x, y):
        p = self.portal
        if p is None or not p.session: return
        w, h = p.size
        p.motion(max(0, min(w - 1, x * w / 65536.0)), max(0, min(h - 1, y * h / 65536.0)))

    def btn(self, b, down):
        p = self.portal
        if p is not None and p.session and 0 <= b < len(BTN): p.button(BTN[b], down)

    def wheel(self, v, horiz):
        """Lăn kiểu Windows (120 = 1 nấc, dương = lên / phải) → số nấc của cổng XDG (dương = xuống / phải). Cộng dồn phần lẻ."""
        p = self.portal
        if p is None or not p.session: return
        i = 1 if horiz else 0
        self.acc[i] += (v if horiz else -v) / 120.0
        n = int(self.acc[i])
        if n: self.acc[i] -= n; p.axis(i, n)

    def key(self, vk, down, ext=False):
        p = self.portal
        code = (EXT_EV.get(vk) if ext else None) or VK2EV.get(vk)
        if p is not None and p.session and code: p.keycode(code, down)

    def text(self, s):
        p = self.portal
        if p is None or not p.session: return
        if any(ch not in US for ch in s) and self.clip_set(s):           # chữ có dấu / ký tự lạ: dán qua bộ nhớ copy (Ctrl+V)
            time.sleep(0.05)
            for c, d in ((29, 1), (47, 1), (47, 0), (29, 0)): p.keycode(c, d)
            return
        for ch in s:
            m = US.get(ch)
            if m is None:
                sym = 0x01000000 + ord(ch); p.keysym(sym, True); p.keysym(sym, False); continue
            code, shift = m
            if shift: p.keycode(42, True)
            p.keycode(code, True); p.keycode(code, False)
            if shift: p.keycode(42, False)

    def _wl(self):
        if self.wl is None:
            self.wl = all(subprocess.run(["sh", "-c", "command -v " + t], capture_output=True).returncode == 0 for t in ("wl-copy", "wl-paste"))
        return self.wl

    def clip_set(self, s):
        if not self._wl(): return False
        try: return subprocess.run(["wl-copy", "--type", "text/plain;charset=utf-8"], input=s.encode("utf-8"), timeout=5).returncode == 0
        except (OSError, subprocess.TimeoutExpired): return False

    def clip_get(self):
        if not self._wl(): return None
        try:
            r = subprocess.run(["wl-paste", "--no-newline", "--type", "text"], capture_output=True, timeout=3)
            return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired): return None


def serve(fd):
    """Vòng lệnh với root qua ổ cắm SOCK_SEQPACKET fd: mỗi gói 1 lệnh JSON {"id", "op", …} → trả {"id", "ok", …}. Root đóng ổ cắm = thoát."""
    sock = socket.socket(fileno=fd)
    out_lock = threading.Lock()

    def send(obj):
        with out_lock:
            try: sock.send(json.dumps(obj).encode("utf-8"))
            except OSError: pass

    cap = Cap(lambda m: send({"log": str(m)[:400]}))
    watch_stop = threading.Event()

    def watch():                                               # bộ quay chết giữa chừng → báo root (root bật lại)
        dead_told = None
        while not watch_stop.wait(0.5):
            p, src = cap.proc, cap.src
            if p is not None and dead_told is not p and (p.poll() is not None or (src is not None and src.poll() is not None)):
                dead_told = p; send({"ev": "stopped", "rc": p.poll(), "pid": p.pid})
    threading.Thread(target=watch, daemon=True).start()
    try:
        while True:
            try: data = sock.recv(256 * 1024)
            except InterruptedError: continue
            if not data: break
            try: j = json.loads(data.decode("utf-8"))
            except ValueError: continue
            op, rid = j.get("op"), j.get("id")
            try:
                if op == "start":
                    enc = j.get("enc") if isinstance(j.get("enc"), list) else None
                    pid = cap.start(int(j["w"]), int(j["h"]), int(j["fps"]), int(j["kbps"]), int(j["port"]), enc)
                    if rid is not None: send({"id": rid, "ok": True, "pid": pid, "mode": cap.mode, "size": list(cap.portal.size)})
                elif op == "open":
                    sz = cap.open()
                    if rid is not None: send({"id": rid, "ok": True, "size": list(sz)})
                elif op == "stop": cap.stop()
                elif op == "move": cap.move(int(j["x"]), int(j["y"]))
                elif op == "btn": cap.btn(int(j["b"]), bool(j["d"]))
                elif op == "wheel": cap.wheel(int(j["v"]), bool(j.get("h")))
                elif op == "key": cap.key(int(j["vk"]), bool(j["d"]), bool(j.get("ext")))
                elif op == "text": cap.text(str(j.get("s") or ""))
                elif op == "clip_set": cap.clip_set(str(j.get("s") or ""))
                elif op == "clip_get": send({"id": rid, "ok": True, "s": cap.clip_get()})
                elif op == "size": send({"id": rid, "ok": True, "size": list(cap.portal.size) if cap.portal else None})
                elif op == "bye": break
            except Exception as e:
                if rid is not None: send({"id": rid, "ok": False, "err": "%s: %s" % (type(e).__name__, str(e)[:300])})
                else: send({"log": "loi lenh %s: %r" % (op, e)})
    finally:
        watch_stop.set()
        cap.close()
        try: sock.close()
        except OSError: pass
    return 0


def probe(secs=4.0):
    """Thử từng bước (CI / tại máy): công cụ → cấp quyền → phiên KDE → luồng màn hình → quay + nén vài giây (đếm gói RTP) → rê chuột."""
    out = {"cap": CAP_VER, "uid": os.getuid(), "wayland": os.environ.get("WAYLAND_DISPLAY"), "runtime": os.environ.get("XDG_RUNTIME_DIR")}
    ok, why = have_tools(); out["tools"] = why; out["mode"] = pick_mode(); out["have"] = tools()
    cap = Cap(lambda m: out.setdefault("log", []).append(str(m)[:200]))
    try:
        t0 = time.time(); sz = cap.open()
        out.update(session=True, size=list(sz), node=cap.portal.node, app=cap.portal.app, open_s=round(time.time() - t0, 1))
        out.update(devices=cap.portal.devices, cursor_modes=cap.portal.cursor[0], cursor_mode=cap.portal.cursor[1])
        try:                                                     # 1 lệnh chuột CÓ chờ trả lời: cổng XDG từ chối thì biết ngay vì sao
            cap.portal.b.call(PORTAL, PORTAL_PATH, RD, "NotifyPointerMotionAbsolute", "oa{sv}udd", [cap.portal.session, {}, cap.portal.node, 100.0, 100.0])
            out["move_reply"] = "ok"
        except DBusError as e:
            out["move_reply"] = str(e)[:200]
        cap.move(32768, 32768); cap.move(40000, 20000); out["move"] = True
        if ok:
            rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); rx.bind(("127.0.0.1", 0)); rx.settimeout(0.5)
            w = min(1280, sz[0] or 1280) // 2 * 2; h = (w * (sz[1] or 720) // (sz[0] or 1280)) // 2 * 2
            cap.start(w, h, 15, 1500, rx.getsockname()[1], X264_ARGS(15, 1500))
            n = by = keys = 0; end = time.time() + secs
            while time.time() < end:
                try: pkt = rx.recv(65536)
                except socket.timeout: continue
                n += 1; by += len(pkt)
                if len(pkt) > 13 and (pkt[12] & 0x1F) in (5, 7): keys += 1
                elif len(pkt) > 14 and (pkt[12] & 0x1F) == 28 and (pkt[13] & 0x1F) in (5, 7) and pkt[13] & 0x80: keys += 1
            out.update(rtp_packets=n, rtp_bytes=by, rtp_key=keys, encoder_alive=cap.alive(), stream=[w, h])
            rx.close()
    except Exception as e:
        out["err"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    finally:
        cap.close()
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0 if out.get("session") and (not ok or out.get("rtp_packets", 0) > 20) else 1


def main(argv):
    if argv[:1] == ["serve"] and len(argv) >= 3 and argv[1] == "--fd": return serve(int(argv[2]))
    if argv[:1] == ["probe"]: return probe(float(argv[1]) if len(argv) > 1 else 4.0)
    if argv[:1] == ["version"]: print(CAP_VER); return 0
    print("cbcap %s: serve --fd N | probe [giay] | version" % CAP_VER); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
