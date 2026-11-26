# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbcap.py — CloudBlue PC (CachyOS): QUAY MÀN HÌNH + CHUỘT / PHÍM, chạy BẰNG TÀI KHOẢN KHÁCH trong phiên KDE (Wayland).
#  cbremote.py (root) mở chương trình này khi có người xem; 2 bên nói chuyện qua 1 ổ cắm (socketpair) truyền sẵn (--fd N).
#  KHÔNG giữ bí mật nào (mã máy, khoá… nằm ở /opt/cloudblue — chỉ root đọc được).
#    · 22.11g — ĐƯỜNG CHÍNH: nói thẳng với KWin (như krdp / xdg-desktop-portal-kde làm bên trong): zkde_screencast_unstable_v1 → luồng PipeWire
#      của màn hình, org_kde_kwin_fake_input → chuột / phím. KWin chỉ cho chương trình có tệp .desktop ghi X-KDE-Wayland-Interfaces trỏ đúng
#      tệp đang chạy → root cài sẵn bản python riêng (cbcap-py) + tệp .desktop đó → KHÔNG BAO GIỜ hiện hộp hỏi, không cần người ngồi ở máy
#      (máy thật 139: cổng XDG hiện hộp hỏi trên màn hình máy dù đã cấp quyền sẵn → khách chờ mãi "bộ quay màn hình chưa chạy").
#    · ĐƯỜNG PHỤ (KWin chưa cho): cổng XDG "RemoteDesktop" của KDE, mã ứng dụng vn.cloudblue.remote đã được CẤP QUYỀN SẴN (bảng kde-authorized,
#      có từ Plasma 6.3); chờ tối đa PORTAL_START_S giây rồi ĐÓNG phiên (KDE gỡ hộp hỏi đang treo) + báo lỗi rõ cho người xem
#    · GStreamer pipewiresrc → thu cỡ → khung thô I420 → ffmpeg (x264, CÙNG tham số nén với máy Windows do root đưa sang) → RTP → UDP
#      127.0.0.1:<cổng root mở>. Không có ffmpeg/libx264 thì nén luôn bằng GStreamer (x264enc → rtph264pay → udpsink).
#    · 23.11b — DÁN: khách bấm Dán / Ctrl+V mà chữ không vào Konsole (cửa sổ dòng lệnh không dán bằng Ctrl+V; máy không có wl-copy thì bộ
#      nhớ copy còn không đặt được). Giờ: đặt bộ nhớ copy bằng wl-copy, không có thì nhờ Klipper (bộ nhớ copy của Plasma, D-Bus); hỏi KWin
#      cửa sổ đang chọn là gì → dòng lệnh dán Ctrl+Shift+V, app thường Ctrl+V, không hỏi được thì Shift+Insert (cả 2 loại đều nhận).
#  Lệnh (1 gói JSON / lần, root → đây): start / stop / move / btn / wheel / key / text / clip_set / clip_get / paste / size / bye
#  Chạy thử:  python3 cbcap.py probe [giây]   → in từng bước dạng JSON (CI)
# =====================================================================================================
import json, os, random, socket, struct, subprocess, sys, threading, time, urllib.parse

CAP_VER = "23.11b"
APP_ID = "vn.cloudblue.remote"
OPEN_BUDGET_S = 17.0                                              # mở luồng màn hình (cả 2 đường) tối đa chừng này: trạm chỉ chờ máy PC 25 giây
PORTAL_START_S = 10.0                                             # cổng XDG: 4 bước tối đa chừng này (trong phần còn lại của OPEN_BUDGET_S)
KWIN_WAIT_S = 3.0                                                 # KWin: chờ mỗi bước (nối / chào / tạo luồng màn hình)
VOUT_W, VOUT_H, VOUT_NAME = 1920, 1080, "CloudBlue"               # 22.11h · máy KHÔNG cắm màn hình → KWin tạo màn hình ảo cỡ này để quay (mất khi hết người xem)
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
                if m["type"] in (1, 2, 3, 4):                     # 1 = có chương trình khác GỌI vào đây (script KWin báo cửa sổ đang chọn)
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
        self.deadline = None                                          # 22.11g: cả phiên mở có hạn chót (trạm chỉ chờ máy PC 25 giây)

    def _token(self): return "cb%d" % random.randrange(10 ** 9)

    def _request(self, iface, member, sig, head, options, timeout=20.0):
        if self.deadline is not None: timeout = max(0.5, min(timeout, self.deadline - time.time()))
        tok = self._token()
        path = "%s/request/%s/%s" % (PORTAL_PATH, self.b.name.lstrip(":").replace(".", "_"), tok)
        self.b.add_match("type='signal',interface='org.freedesktop.portal.Request',member='Response',path='%s'" % path)
        opts = dict(options); opts["handle_token"] = ("s", tok)
        self.b.call(PORTAL, PORTAL_PATH, iface, member, sig, list(head) + [opts])
        try:
            m = self.b.take(lambda m: m["type"] == 4 and m["path"] == path and m["member"] == "Response", timeout)
        except DBusError:
            try: self.b.call(PORTAL, path, "org.freedesktop.portal.Request", "Close", timeout=2)        # gỡ hộp hỏi đang treo trên màn hình máy
            except Exception: pass
            raise PortalError("%s.%s: KDE chua tra loi sau %d giay (dang hien hop hoi quyen tren man hinh may?)" % (iface.rsplit(".", 1)[-1], member, int(timeout)))
        code, results = m["body"]
        if code != 0: raise PortalError("%s.%s bi tu choi (ma %d)" % (iface.rsplit(".", 1)[-1], member, code))
        return results

    def authorize(self, timeout=15.0):
        """Cấp quyền sẵn: đăng ký mã ứng dụng (xdg-desktop-portal ≥ 1.19) + ghi vào bảng kde-authorized (Plasma ≥ 6.3)."""
        try:
            self.b.call(PORTAL, PORTAL_PATH, "org.freedesktop.host.portal.Registry", "Register", "sa{sv}", [APP_ID, {}], timeout=timeout)
            self.app = APP_ID
        except DBusError as e:
            self.app = ""
            self.log("cong XDG chua co Registry (%s) -> cap quyen cho ung dung khong ma" % str(e)[:80])
        self.b.call(*STORE, "SetPermission", "sbssas", ["kde-authorized", True, "remote-desktop", self.app, ["yes"]], timeout=timeout)
        return self.app

    def start(self, timeout=25.0, own_cursor=False):
        self.deadline = time.time() + timeout
        r = self._request(RD, "CreateSession", "a{sv}", [], {"session_handle_token": ("s", self._token())})
        self.session = str(r["session_handle"])
        self._request(RD, "SelectDevices", "oa{sv}", [self.session], {"types": ("u", 3)})                     # bàn phím + chuột
        try: modes = int(self.b.get_prop(PORTAL, PORTAL_PATH, SC, "AvailableCursorModes"))
        except (DBusError, TypeError, ValueError): modes = 2
        self.cursor = (modes, 1 if own_cursor and modes & 1 else 2 if modes & 2 else 1)     # tự vẽ con trỏ (FramePump) → KWin ẩn con trỏ trong hình
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

# ---- 23.11b · DÁN. Konsole / cửa sổ dòng lệnh: Ctrl+V là ^V của bash (không dán) → phải Ctrl+Shift+V. xterm / urxvt: Shift+Insert dán VÙNG CHỌN
#      (Klipper đặt cả bộ nhớ copy lẫn vùng chọn). Không biết cửa sổ gì: Shift+Insert — Konsole, Firefox, Chrome / Electron, app KDE / GTK,
#      LibreOffice, ô nhập chữ của Wine đều coi là Dán.
TERM_APPS = frozenset(("konsole", "yakuake", "alacritty", "kitty", "foot", "footclient", "wezterm", "wezterm-gui", "ghostty", "gnome-terminal",
                       "gnome-terminal-server", "terminal", "console", "kgx", "ptyxis", "tilix", "terminator", "xfce4-terminal", "qterminal",
                       "lxterminal", "mate-terminal", "terminology", "sakura", "guake", "tilda", "cool-retro-term", "deepin-terminal", "rio",
                       "contour", "blackbox", "warp", "termite", "cosmic-term", "wave", "tabby", "hyper"))
SEL_APPS = frozenset(("xterm", "uxterm", "urxvt", "rxvt", "urxvt256c", "urxvtc", "st", "st-256color"))
PASTE_KEYS = {"term": (29, 42, 47), "app": (29, 47), "sel": (42, 110), None: (42, 110)}           # Ctrl+Shift+V · Ctrl+V · Shift+Insert
PASTE_NAME = {"term": "Ctrl+Shift+V", "app": "Ctrl+V", "sel": "Shift+Insert", None: "Shift+Insert"}
KLIPPER = ("org.kde.klipper", "/klipper", "org.kde.klipper.klipper")
KWIN_SCRIPTING = ("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")
ACT_PATH, ACT_IFACE = "/vn/cloudblue/cap", "vn.cloudblue.Cap"
ACT_TTL_S = 1.0                                               # nhớ loại cửa sổ chừng này giây (gõ chữ có dấu từng chữ không phải hỏi KWin mỗi chữ)
# Script KWin (Plasma 6: workspace.activeWindow · Plasma 5: activeClient): đọc tên cửa sổ đang chọn rồi GỌI NGƯỢC về cbcap (tên bus riêng) qua D-Bus.
ACTIVE_JS = ('(function () {\n'
             '    var w = workspace.activeWindow || workspace.activeClient, r = "";\n'
             '    if (w) r = [w.resourceClass, w.resourceName, w.desktopFileName].map(function (x) { return x ? String(x) : ""; }).join("\\n");\n'
             '    callDBus(%s, "%s", "%s", "Active", %s + "\\n" + r);\n'
             '})();\n')


def app_kind(info):
    """Tên cửa sổ KWin báo (resourceClass / resourceName / desktopFileName, mỗi dòng 1 cái) → "term" (dòng lệnh) · "sel" (xterm…) · "app" ·
       None (không có cửa sổ nào đang chọn)."""
    names = set()
    for x in str(info or "").lower().split("\n"):
        x = x.strip()
        if x.endswith(".desktop"): x = x[:-8]
        if not x: continue
        names.update((x, x.rsplit(".", 1)[-1], x.rsplit("/", 1)[-1]))
    if not names: return None
    if names & SEL_APPS: return "sel"
    if names & TERM_APPS or any(n.endswith("-terminal") or n.endswith(".terminal") for n in names): return "term"
    return "app"


def pw_src(node, fd):
    """pipewiresrc: qua cổng XDG thì dùng ổ PipeWire riêng cổng đưa (fd); qua KWin trực tiếp thì nối PipeWire của phiên (fd = None)."""
    return ["pipewiresrc"] + ([] if fd is None else ["fd=%d" % fd]) + ["path=%d" % node]


def gst_src(node, w, h, fps, fd=3, fmt="BGRx"):
    """Phần đầu GStreamer: màn hình (PipeWire của KDE) → đổi màu + thu cỡ (chỉ khung THẬT) → nhịp khung đều (lặp khung khi màn hình đứng yên)
       → hàng chờ BỎ KHUNG CŨ (bộ nén chậm hơn nhịp khung thì bỏ bớt, KHÔNG dồn: dồn thì người xem thấy hình trễ dần — CI 22.11f: con trỏ trễ > 2,5 giây).
       Khung thô đưa sang ffmpeg dùng BGRx (4 byte/điểm: mỗi dòng không có byte đệm, ffmpeg đọc đúng với mọi chiều rộng)."""
    return pw_src(node, fd) + ["do-timestamp=true", "keepalive-time=250", "always-copy=true", "!",
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
    """GStreamer chỉ lấy khung thô BGRx ra stdout — CHỈ khi màn hình đổi (+ lặp lại mỗi giây); FramePump giữ nhịp đều + vẽ con trỏ rồi đưa ffmpeg nén."""
    return ["gst-launch-1.0", "-q"] + pw_src(node, fd) + ["do-timestamp=true", "keepalive-time=1000", "always-copy=true", "!",
            "queue", "max-size-buffers=2", "max-size-bytes=0", "max-size-time=0", "leaky=downstream", "!",
            "videoconvert", "!", "videoscale", "!", "video/x-raw,format=BGRx,width=%d,height=%d" % (w, h), "!",
            "queue", "max-size-buffers=2", "max-size-bytes=0", "max-size-time=0", "leaky=downstream", "!", "fdsink", "fd=1", "sync=false"]


# Con trỏ tự vẽ (mũi tên 12x19): B = viền đen, W = ruột trắng, cách = trong suốt
CURSOR = ("B", "BB", "BWB", "BWWB", "BWWWB", "BWWWWB", "BWWWWWB", "BWWWWWWB", "BWWWWWWWB", "BWWWWWWWWB", "BWWWWWWWWWB", "BWWWWWWBBBBB",
          "BWWWBWWB", "BWWBBWWB", "BWB  BWWB", "BB   BWWB", "B     BWWB", "      BWWB", "       BB")
_PX = {"B": b"\x00\x00\x00\xff", "W": b"\xff\xff\xff\xff"}


def cursor_runs(rows=CURSOR):
    """→ [(dy, dx, bytes BGRx)…]: các đoạn liền cùng màu của mũi tên (vẽ nhanh bằng gán lát cắt)."""
    out = []
    for dy, row in enumerate(rows):
        dx = 0
        while dx < len(row):
            c = row[dx]
            if c == " ": dx += 1; continue
            e = dx
            while e < len(row) and row[e] == c: e += 1
            out.append((dy, dx, _PX[c] * (e - dx))); dx = e
    return out


CURSOR_RUNS = cursor_runs()


def draw_cursor(buf, w, h, x, y, runs=CURSOR_RUNS):
    """Vẽ mũi tên lên khung BGRx (bytearray w*h*4) tại điểm (x, y) — mũi nhọn đúng điểm chuột. Cắt phần ra ngoài khung."""
    for dy, dx, seg in runs:
        yy, xx = y + dy, x + dx
        if yy < 0 or yy >= h or xx >= w: continue
        n = len(seg) // 4
        if xx < 0: seg = seg[-xx * 4:]; n += xx; xx = 0
        if xx + n > w: seg = seg[:(w - xx) * 4]; n = w - xx
        if n <= 0: continue
        o = (yy * w + xx) * 4
        buf[o:o + n * 4] = seg


class FramePump:
    """Khung thô của bộ quay (GStreamer: chỉ ra khung khi màn hình đổi) → giữ khung MỚI NHẤT → ghi sang ffmpeg ĐỀU fps khung/giây, VẼ CON TRỎ
       ở vị trí chuột cuối cùng. KWin không sinh khung mới khi chỉ rê chuột trên vùng đứng yên (CI 22.11f: con trỏ tới chậm ~3 giây) → tự vẽ thì
       người xem thấy chuột đi ngay; màn hình đứng yên vẫn đủ nhịp khung (khung khoá đều). Bộ nén chậm → ghi chậm lại, KHÔNG dồn (luôn lấy khung mới nhất)."""
    def __init__(self, src, dst, w, h, fps, pos=lambda: None, log=lambda m: None):
        self.src, self.dst, self.w, self.h, self.fps, self.pos, self.log = src, dst, w, h, max(1, int(fps)), pos, log
        self.n = w * h * 4; self.latest = None; self.seq = 0; self.sent = 0; self.got = 0
        self.stop_ev = threading.Event()
        self.threads = [threading.Thread(target=self._reader, daemon=True), threading.Thread(target=self._writer, daemon=True)]
        for t in self.threads: t.start()

    def _reader(self):
        buf = bytearray(self.n); mv = memoryview(buf)
        try:
            while not self.stop_ev.is_set():
                got = 0
                while got < self.n:
                    k = self.src.readinto(mv[got:])
                    if not k: self.stop_ev.set(); return
                    got += k
                self.latest = bytes(buf); self.seq += 1; self.got += 1
        except (OSError, ValueError):
            self.stop_ev.set()

    def _writer(self):
        period = 1.0 / self.fps; nxt = time.monotonic(); key = None; out = None
        try:
            while not self.stop_ev.is_set():
                fr, seq, p = self.latest, self.seq, self.pos()
                if fr is not None:
                    if (seq, p) != key:                              # khung mới hoặc chuột đổi chỗ → dựng lại; không thì gửi lại khung trước
                        out = bytearray(fr)
                        if p is not None: draw_cursor(out, self.w, self.h, p[0], p[1])
                        key = (seq, p)
                    self.dst.write(out); self.dst.flush(); self.sent += 1
                nxt += period
                d = nxt - time.monotonic()
                if d > 0: time.sleep(d)
                elif d < -1.0: nxt = time.monotonic()                 # tụt quá 1 giây (bộ nén chậm) → bắt nhịp lại, không dồn
        except (OSError, ValueError):
            pass
        finally:
            self.stop_ev.set()
            try: self.dst.close()
            except (OSError, ValueError): pass

    def stop(self):
        self.stop_ev.set()


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


# ====================================================================================== KWin trực tiếp (22.11g): Wayland tối thiểu, không thư viện ngoài
class WaylandError(Exception):
    pass


def _wl_str(s):
    b = str(s).encode("utf-8") + b"\0"
    return struct.pack("<I", len(b)) + b + b"\0" * ((-len(b)) % 4)


def _wl_rstr(p, pos):
    """Đọc 1 chuỗi Wayland ở vị trí pos → (chuỗi, vị trí kế tiếp)."""
    n = struct.unpack_from("<I", p, pos)[0]; pos += 4
    return (p[pos:pos + n - 1].decode("utf-8", "replace") if n else ""), pos + ((n + 3) & ~3)


def _wl_fixed(v): return struct.pack("<i", int(round(float(v) * 256.0)))


class Wayland:
    """Nói chuyện với KWin qua ổ cắm Wayland của phiên (WAYLAND_DISPLAY): registry, sync, bind, gửi yêu cầu; 1 luồng đọc sự kiện
       (luôn đọc để KWin không bị đầy bộ đệm rồi cắt kết nối). Chỉ đủ cho wl_output / zxdg_output / zkde_screencast / fake_input."""
    def __init__(self, path=None, timeout=KWIN_WAIT_S, log=None):
        self.log = log or (lambda m: None)
        if path is None:
            disp = os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
            path = disp if disp.startswith("/") else os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid(), disp)
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        try: self.s.connect(path)
        except OSError as e:
            self.s.close(); raise WaylandError("khong noi duoc KWin (%s): %s" % (path, e))
        self.s.settimeout(None)
        self.wlock = threading.Lock(); self.cv = threading.Condition()
        self.nid = 1; self.handlers = {1: self._on_display}; self.globals = {}; self.err = None; self.closed = False
        self.registry = self.new_id(self._on_registry)
        self.send(1, 1, struct.pack("<I", self.registry))                        # wl_display.get_registry
        threading.Thread(target=self._reader, name="wayland", daemon=True).start()
        self.roundtrip(timeout)

    def new_id(self, handler=None):
        with self.cv:
            self.nid += 1
            if handler is not None: self.handlers[self.nid] = handler
            return self.nid

    def send(self, obj, op, payload=b""):
        msg = struct.pack("<II", obj, ((8 + len(payload)) << 16) | op) + payload
        with self.wlock:
            try: self.s.sendall(msg)
            except OSError as e: raise WaylandError("mat ket noi KWin: %s" % e)

    def _reader(self):
        buf = b""
        try:
            while True:
                d = self.s.recv(65536)
                if not d: break
                buf += d
                while len(buf) >= 8:
                    obj, so = struct.unpack_from("<II", buf, 0)
                    size, op = so >> 16, so & 0xFFFF
                    if size < 8: raise WaylandError("goi Wayland hong")
                    if len(buf) < size: break
                    payload, buf = buf[8:size], buf[size:]
                    h = self.handlers.get(obj)
                    if h is None: continue
                    try: h(op, payload)
                    except Exception as e: self.log("wayland: loi doc su kien %d/%d: %r" % (obj, op, e))
        except (OSError, WaylandError):
            pass
        finally:
            with self.cv:
                self.closed = True; self.cv.notify_all()

    def _on_display(self, op, p):
        if op == 0:                                                              # error(object, code, message)
            oid, code = struct.unpack_from("<II", p, 0)
            with self.cv:
                self.err = "KWin bao loi Wayland (doi tuong %d, ma %d): %s" % (oid, code, _wl_rstr(p, 8)[0][:160]); self.cv.notify_all()

    def _on_registry(self, op, p):
        name = struct.unpack_from("<I", p, 0)[0]
        with self.cv:
            if op == 0:                                                          # global(name, interface, version)
                iface, pos = _wl_rstr(p, 4)
                self.globals[name] = (iface, struct.unpack_from("<I", p, pos)[0])
            elif op == 1: self.globals.pop(name, None)                           # global_remove(name)
            self.cv.notify_all()

    def wait(self, pred, timeout, what):
        end = time.time() + timeout
        with self.cv:
            while True:
                if self.err: raise WaylandError(self.err)
                r = pred()
                if r: return r
                if self.closed: raise WaylandError("KWin dong ket noi Wayland")
                left = end - time.time()
                if left <= 0: raise WaylandError(what)
                self.cv.wait(left)

    def roundtrip(self, timeout=KWIN_WAIT_S):
        done = []

        def h(op, p):
            with self.cv: done.append(1); self.cv.notify_all()
        cb = self.new_id(h)
        self.send(1, 0, struct.pack("<I", cb))                                  # wl_display.sync
        self.wait(lambda: done, timeout, "KWin khong tra loi sau %d giay" % int(timeout))
        self.handlers.pop(cb, None)

    def find(self, iface):
        with self.cv:
            for name, (i, v) in self.globals.items():
                if i == iface: return name, v
        return None

    def bind(self, name, iface, ver, handler=None):
        oid = self.new_id(handler)
        self.send(self.registry, 0, struct.pack("<I", name) + _wl_str(iface) + struct.pack("<II", ver, oid))
        return oid

    def close(self):
        try: self.s.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        try: self.s.close()
        except OSError: pass


KWIN_IFACES = ("zkde_screencast_unstable_v1", "org_kde_kwin_fake_input")


class KWinCast:
    """1 luồng màn hình (zkde_screencast_unstable_v1.stream_output → mã nút PipeWire) + chuột / phím (org_kde_kwin_fake_input, KWin tự cấp quyền
       khi authenticate — không hộp hỏi). Toạ độ chuột: 0..65535 trên màn hình đang quay → toạ độ LOGIC chung của KWin (zxdg_output: đúng cả khi
       phóng to 125 / 150 %). Cùng cách gọi với Portal (motion / button / axis / keycode / keysym / close)."""
    def __init__(self, log=None):
        self.log = log or (lambda m: None)
        self.wl = None; self.node = None; self.size = (0, 0); self.geo = (0, 0, 1, 1); self.fi = None; self.fi_ver = 0
        self.sc = None; self.stream = None; self.out = ""; self.outs = 0; self.session = None; self.virtual = False; self.xm = None

    @staticmethod
    def _on_output(o):
        def h(op, p):
            if op == 0: o["x"], o["y"] = struct.unpack_from("<ii", p, 0)                          # geometry(x, y, …)
            elif op == 1:                                                                        # mode(flags, w, h, refresh)
                fl, w, hh = struct.unpack_from("<Iii", p, 0)
                if fl & 1: o["mw"], o["mh"] = w, hh
            elif op == 3: o["scale"] = max(1, struct.unpack_from("<i", p, 0)[0])               # scale(factor)
            elif op == 4: o["name"] = _wl_rstr(p, 0)[0][:40]                                    # name(name)
        return h

    @staticmethod
    def _on_xdg(o):
        def h(op, p):
            if op == 0: o["lx"], o["ly"] = struct.unpack_from("<ii", p, 0)                      # logical_position
            elif op == 1: o["lw"], o["lh"] = struct.unpack_from("<ii", p, 0)                    # logical_size
        return h

    @staticmethod
    def pick(outs):
        """Màn hình để quay: cái ở góc (0, 0) (màn hình chính), không có thì cái lớn nhất."""
        items = [(k, o) for k, o in outs.items() if o.get("mw", 0) > 0] or list(outs.items())
        for k, o in items:
            if o.get("lx", o.get("x", 0)) == 0 and o.get("ly", o.get("y", 0)) == 0: return k, o
        return max(items, key=lambda it: it[1].get("mw", 0) * it[1].get("mh", 0))

    def start(self, pointer=1, timeout=KWIN_WAIT_S):
        """pointer: 1 ẩn con trỏ (FramePump tự vẽ), 2 KWin vẽ con trỏ vào hình."""
        wl = self.wl = Wayland(timeout=timeout, log=self.log)
        sc, fi = wl.find("zkde_screencast_unstable_v1"), wl.find("org_kde_kwin_fake_input")
        if not sc or not fi:
            miss = ", ".join(n for n, x in (("zkde_screencast", sc), ("fake_input", fi)) if not x)
            raise WaylandError("KWin chua cho chuong trinh nay quay man hinh / bam phim (thieu %s - tep .desktop X-KDE-Wayland-Interfaces)" % miss)
        if fi[1] < 4: raise WaylandError("fake_input cua KWin qua cu (ban %d < 4)" % fi[1])
        outs = self._outputs(wl, [n for n, (i, v) in list(wl.globals.items()) if i == "wl_output"], timeout)
        if not outs or os.environ.get("CBCAP_VIRTUAL") == "1":                       # 22.11h: không cắm màn hình → màn hình ảo
            return self._virtual(wl, sc, fi, pointer, timeout, len(outs))
        oid, o = self.pick(outs)
        self.outs = len(outs); self.out = o.get("name") or ""
        if not o.get("mw"): raise WaylandError("KWin chua bao do phan giai man hinh %s" % self.out)
        sc_n = max(1, o.get("scale", 1))
        self.geo = (o.get("lx", o.get("x", 0)), o.get("ly", o.get("y", 0)), o.get("lw") or o["mw"] // sc_n, o.get("lh") or o["mh"] // sc_n)
        self._fake(wl, fi)
        self.sc = wl.bind(sc[0], "zkde_screencast_unstable_v1", min(sc[1], 5))           # ≤ 5: KWin báo created(node) (bản 6 đổi sang serial)
        st = {}
        self.stream = wl.new_id(self._on_stream(wl, st))
        wl.send(self.sc, 0, struct.pack("<III", self.stream, oid, int(pointer)))          # stream_output(stream, output, pointer)
        wl.wait(lambda: st, timeout, "KWin chua tao luong man hinh sau %d giay" % int(timeout))
        if "err" in st: raise WaylandError("KWin tu choi quay man hinh: %s" % st["err"])
        if "node" not in st: raise WaylandError("KWin dong luong man hinh ngay khi tao")
        self.node, self.size, self.session = st["node"], (o["mw"], o["mh"]), "kwin"
        self.stream_st = st
        return self.node, self.size

    def _fake(self, wl, fi):
        self.fi_ver = min(fi[1], 6)
        self.fi = wl.bind(fi[0], "org_kde_kwin_fake_input", self.fi_ver)
        wl.send(self.fi, 0, _wl_str("CloudBlue") + _wl_str("dieu khien tu xa"))             # authenticate (KWin tự cho)

    @staticmethod
    def _on_stream(wl, st):
        def h(op, p):
            with wl.cv:
                if op == 1: st["node"] = struct.unpack_from("<I", p, 0)[0]                 # created(node)
                elif op == 2: st["err"] = _wl_rstr(p, 0)[0][:160]                          # failed(error)
                elif op == 0: st["closed"] = True                                            # closed
                wl.cv.notify_all()                                                           # (bản 6 thêm serial = sự kiện 3: bỏ qua)
        return h

    def _outputs(self, wl, names, timeout):
        """bind các wl_output (+ zxdg_output: vùng LOGIC khi phóng to %) → {mã đối tượng: thông tin màn hình}."""
        outs = {}
        for name in names:
            ver = wl.globals.get(name, ("", 4))[1]
            o = {"mw": 0, "mh": 0, "scale": 1}
            outs[wl.bind(name, "wl_output", min(ver, 4), self._on_output(o))] = o
        if not outs: return outs
        xm = wl.find("zxdg_output_manager_v1")
        if xm:
            if self.xm is None: self.xm = wl.bind(xm[0], "zxdg_output_manager_v1", min(xm[1], 3))
            for oid, o in outs.items():
                wl.send(self.xm, 1, struct.pack("<II", wl.new_id(self._on_xdg(o)), oid))     # get_xdg_output(id, output)
        wl.roundtrip(timeout); wl.roundtrip(timeout)
        return outs

    def _virtual(self, wl, sc, fi, pointer, timeout, had=0):
        """22.11h · máy KHÔNG cắm màn hình (KWin chỉ còn màn hình "giữ chỗ", không báo wl_output nào): xin KWin tạo MÀN HÌNH ẢO
           VOUT_W×VOUT_H rồi quay chính nó (zkde_screencast.stream_virtual_output — có từ bản 2, cách krdp làm). Desktop của khách hiện lên
           màn hình ảo; đóng luồng (hết người xem) → KWin bỏ màn hình ảo."""
        if sc[1] < 2: raise WaylandError("KWin khong bao man hinh nao (wl_output) va KWin qua cu de tao man hinh ao (zkde_screencast ban %d < 2)" % sc[1])
        self._fake(wl, fi)
        self.sc = wl.bind(sc[0], "zkde_screencast_unstable_v1", min(sc[1], 5))
        with wl.cv: before = {n for n, (i, v) in wl.globals.items() if i == "wl_output"}
        st = {}
        self.stream = wl.new_id(self._on_stream(wl, st))
        wl.send(self.sc, 3, struct.pack("<I", self.stream) + _wl_str(VOUT_NAME) + struct.pack("<ii", VOUT_W, VOUT_H)
                + _wl_fixed(1.0) + struct.pack("<I", int(pointer)))                          # stream_virtual_output(stream, name, w, h, scale, pointer)
        wl.wait(lambda: st, max(timeout, 5.0), "KWin chua tao man hinh ao sau %d giay" % int(max(timeout, 5.0)))
        if "err" in st: raise WaylandError("KWin khong tao duoc man hinh ao: %s" % st["err"])
        if "node" not in st: raise WaylandError("KWin dong man hinh ao ngay khi tao")
        self.geo = (0, 0, VOUT_W, VOUT_H); self.out = VOUT_NAME; self.outs = had; self.virtual = True
        try:                                                    # màn hình ảo = 1 wl_output mới → vùng logic thật (có màn hình khác thì nó nằm cạnh)
            new = wl.wait(lambda: [n for n, (i, v) in wl.globals.items() if i == "wl_output" and n not in before], 2.0, "khong thay wl_output moi")
            outs = self._outputs(wl, new[:4], timeout)
            got = [o for o in outs.values() if VOUT_NAME.lower() in str(o.get("name", "")).lower()] or list(outs.values())
            o = got[0] if got else {}
            if o.get("lw") or o.get("mw"):
                sc_n = max(1, o.get("scale", 1))
                self.geo = (o.get("lx", o.get("x", 0)), o.get("ly", o.get("y", 0)), o.get("lw") or o["mw"] // sc_n, o.get("lh") or o["mh"] // sc_n)
                self.out = o.get("name") or VOUT_NAME
        except WaylandError:
            pass
        self.node, self.size, self.session = st["node"], (VOUT_W, VOUT_H), "kwin"
        self.stream_st = st
        self.log("KWin: may khong cam man hinh -> man hinh ao %dx%d (%s, vung logic %s)" % (VOUT_W, VOUT_H, self.out, list(self.geo)))
        return self.node, self.size

    def alive(self):
        return self.wl is not None and not self.wl.closed and not getattr(self, "stream_st", {}).get("closed")

    # ---- chuột / phím (cùng tên với Portal) ----
    def motion(self, x, y):
        """x, y: điểm ảnh trên luồng màn hình (0..size) → toạ độ logic chung của KWin."""
        gx, gy, gw, gh = self.geo
        sw, sh = self.size
        X = gx + max(0.0, min(gw - 0.01, x * gw / float(max(1, sw)))); Y = gy + max(0.0, min(gh - 0.01, y * gh / float(max(1, sh))))
        self.wl.send(self.fi, 9, _wl_fixed(X) + _wl_fixed(Y))                             # pointer_motion_absolute
    def button(self, code, down): self.wl.send(self.fi, 2, struct.pack("<II", int(code), 1 if down else 0))
    def axis(self, axis, steps): self.wl.send(self.fi, 3, struct.pack("<I", int(axis)) + _wl_fixed(15.0 * steps))     # 15 = 1 nấc lăn
    def keycode(self, code, down): self.wl.send(self.fi, 10, struct.pack("<II", int(code), 1 if down else 0))

    def keysym(self, sym, down):
        if self.fi_ver < 6: return False                                                   # keyboard_keysym có từ bản 6
        self.wl.send(self.fi, 12, struct.pack("<II", int(sym), 1 if down else 0)); return True

    def close(self):
        wl, self.wl = self.wl, None
        if wl is None: return
        for obj, op in ((self.stream, 0), (self.sc, 2), (self.fi, 11 if self.fi_ver >= 5 else None)):
            if obj and op is not None:
                try: wl.send(obj, op)
                except Exception: pass
        wl.close()
        self.node = None; self.session = None


# ====================================================================================== phần chạy (theo lệnh của root)
class Cap:
    def __init__(self, log=None, bus_addr=None):
        self.log = log or (lambda m: None); self.bus_addr = bus_addr
        self.bus = None; self.portal = None; self.proc = None; self.src = None; self.mode = None; self.lock = threading.RLock()
        self.acc = [0.0, 0.0]; self.wl = None; self.pump = None; self.pt = None   # pt: chuột cuối cùng (0..65535) cho con trỏ tự vẽ
        self.kw = None; self.inp = None; self.backend = None; self.node = None; self.size = (0, 0); self.own = False; self.why = ""
        self.first = None                                             # thời gian mở lần đầu (giây) — ghi nhật ký / chạy thử
        self.sb = None; self.act_n = 0; self.act_fail = 0; self.act_t = 0.0; self.act_kind = None; self.act_info = ""   # 23.11b: dán (bus riêng + KWin)
        self.paste_last = False; self.klip_told = False

    def _drop(self):
        if self.kw is not None: self.kw.close()
        if self.portal is not None: self.portal.close()                # đóng phiên → KDE gỡ hộp hỏi còn treo (nếu có)
        if self.bus is not None: self.bus.close()
        self.kw = self.portal = self.bus = self.inp = None; self.backend = None; self.node = None

    def open(self, portal=True):
        """Mở luồng màn hình + đường chuột / phím: KWin trực tiếp trước (không hộp hỏi), không được thì cổng XDG (chờ tối đa PORTAL_START_S).
           Cả 2 đều hỏng → lỗi ghi rõ từng đường (người xem thấy, root ghi nhật ký).
           22.11h · portal=False: chỉ thử KWin (KWin chưa có quyền mới → cổng XDG chỉ hiện hộp hỏi trên màn hình máy, không ai bấm, tốn 10 giây)."""
        with self.lock:
            if self.inp is not None and self.node is not None and (self.kw is None or self.kw.alive()): return self.size
            self._drop()
            t0 = time.time(); errs = []
            own = pick_mode() == "ff"
            if os.environ.get("CBCAP_NO_KWIN") != "1":
                k = KWinCast(self.log)
                try:
                    k.start(pointer=1 if own else 2)
                    self.kw = self.inp = k; self.node, self.size, self.backend, self.own = k.node, k.size, "kwin", own
                    self.first = round(time.time() - t0, 2)
                    self.log("KWin truc tiep: luong man hinh %d (%dx%d) man hinh %s/%d, vung logic %s, fake_input v%d, %.1f giay" % (
                        k.node, k.size[0], k.size[1], k.out or "?", k.outs, list(k.geo), k.fi_ver, self.first))
                    return self.size
                except Exception as e:
                    k.close(); errs.append("KWin: %s" % str(e)[:170])
                    self.log("KWin truc tiep chua dung duoc -> thu cong XDG: %s" % (e,))
            if os.environ.get("CBCAP_NO_PORTAL") == "1" or not portal: raise RuntimeError("; ".join(errs) or "khong co duong quay nao")
            try:
                left = lambda: max(2.0, OPEN_BUDGET_S - (time.time() - t0))
                self.bus = DBus(self.bus_addr)
                self.portal = Portal(self.bus, self.log)
                self.portal.authorize(timeout=min(4.0, left()))
                self.portal.start(timeout=min(PORTAL_START_S, left()), own_cursor=own)
                self.inp, self.node, self.size, self.backend = self.portal, self.portal.node, self.portal.size, "portal"
                self.own = self.portal.cursor[1] == 1                    # KWin ẩn con trỏ → tự vẽ
                self.first = round(time.time() - t0, 2)
                self.log("phien KDE: luong man hinh %d (%dx%d), ma ung dung %r, thiet bi %s, con tro %s/%s" % (self.portal.node, self.portal.size[0], self.portal.size[1], self.portal.app,
                         self.portal.devices, self.portal.cursor[1], self.portal.cursor[0]))
                return self.size
            except Exception as e:
                errs.append("cong XDG: %s" % str(e)[:170])
                self._drop()
                self.why = "; ".join(errs)
                raise RuntimeError(self.why)

    def start(self, w, h, fps, kbps, port, enc_args=None):
        """Bật bộ quay + nén. → pid tiến trình theo dõi (ffmpeg hoặc gst-launch); chết = báo root bật lại."""
        with self.lock:
            self.stop()
            self.open()
            mode = pick_mode()
            if mode is None: raise RuntimeError("may thieu cong cu quay man hinh: %s" % have_tools()[1])
            if mode == "ff" and not enc_args: mode = "gst" if pick_mode(dict(tools(), ffmpeg_x264=False)) else "ff"
            fd = self.portal.pw_fd() if self.backend == "portal" else None      # KWin trực tiếp: nối PipeWire của phiên, không cần ổ riêng
            fds = () if fd is None else (fd,)
            try:
                if fd is not None: os.set_inheritable(fd, True)
                if mode == "ff":
                    src = subprocess.Popen(test_src(w, h, fps) if TEST_SRC else raw_pipeline(self.node, w, h, fps, fd), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=fds)
                    enc = subprocess.Popen(ff_encode(w, h, fps, enc_args or [], port), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    own = self.own
                    self.pump = FramePump(src.stdout, enc.stdin, w, h, fps,
                                          (lambda: None if self.pt is None else (self.pt[0] * w // 65536, self.pt[1] * h // 65536)) if own else (lambda: None), self.log)
                    self.src, self.proc = src, enc
                    threading.Thread(target=self._errlog, args=(src, "gstreamer"), daemon=True).start()
                else:
                    self.src = None
                    self.proc = subprocess.Popen(gst_pipeline(self.node, w, h, fps, kbps, port, fd), stdin=subprocess.DEVNULL,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, pass_fds=fds)
            finally:
                if fd is not None: os.close(fd)
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
            if self.pump is not None: self.pump.stop(); self.pump = None
            procs, self.proc, self.src = (self.src, self.proc), None, None
            for p in procs:
                if p is not None and p.poll() is None:
                    p.terminate()
                    try: p.wait(2)
                    except subprocess.TimeoutExpired: p.kill()

    def close(self):
        with self.lock:
            self.stop()
            self._drop()
            self._sbus_drop()

    # ---- chuột / phím: toạ độ người xem 0..65535 trên cả màn hình (đi qua KWin trực tiếp hoặc cổng XDG — cùng tên hàm) ----
    def _in(self):
        p = self.inp
        return p if p is not None and p.session else None

    def move(self, x, y):
        p = self._in()
        if p is None: return
        w, h = p.size
        self.pt = (max(0, min(65535, int(x))), max(0, min(65535, int(y))))
        p.motion(max(0, min(w - 1, x * w / 65536.0)), max(0, min(h - 1, y * h / 65536.0)))

    def btn(self, b, down):
        p = self._in()
        if p is not None and 0 <= b < len(BTN): p.button(BTN[b], down)

    def wheel(self, v, horiz):
        """Lăn kiểu Windows (120 = 1 nấc, dương = lên / phải) → số nấc (dương = xuống / phải). Cộng dồn phần lẻ."""
        p = self._in()
        if p is None: return
        i = 1 if horiz else 0
        self.acc[i] += (v if horiz else -v) / 120.0
        n = int(self.acc[i])
        if n: self.acc[i] -= n; p.axis(i, n)

    def key(self, vk, down, ext=False):
        p = self._in()
        code = (EXT_EV.get(vk) if ext else None) or VK2EV.get(vk)
        if p is not None and code: p.keycode(code, down)

    def text(self, s):
        p = self._in()
        if p is None: return
        if any(ch not in US for ch in s) and self.clip_set(s):           # chữ có dấu / ký tự lạ: dán qua bộ nhớ copy (đúng phím dán của cửa sổ đang chọn)
            time.sleep(0.05)
            self.paste(1)
            return
        for ch in s:
            m = US.get(ch)
            if m is None:
                sym = 0x01000000 + ord(ch)
                if p.keysym(sym, True) is not False: p.keysym(sym, False)
                continue
            code, shift = m
            if shift: p.keycode(42, True)
            p.keycode(code, True); p.keycode(code, False)
            if shift: p.keycode(42, False)

    def _wl(self):
        if self.wl is None:
            self.wl = all(subprocess.run(["sh", "-c", "command -v " + t], capture_output=True).returncode == 0 for t in ("wl-copy", "wl-paste"))
        return self.wl

    # ---- bus phiên RIÊNG cho bộ nhớ copy (Klipper) + hỏi KWin cửa sổ đang chọn (không đụng bus cổng XDG đang chở chuột / phím)
    def _sbus(self):
        if self.sb is None: self.sb = DBus(self.bus_addr, timeout=3.0)
        return self.sb

    def _sbus_drop(self):
        b, self.sb = self.sb, None
        if b is not None: b.close()

    def _scall(self, dest, path, iface, member, sig="", args=(), timeout=2.0):
        """Gọi hàm trên bus riêng. Bus đứt / quá giờ → bỏ kết nối (lần sau nối lại). Chương trình kia trả lỗi → DBusError (giữ kết nối)."""
        try: return self._sbus().call(dest, path, iface, member, sig, args, timeout=timeout)
        except (OSError, DBusError) as e:
            if isinstance(e, OSError) or "qua thoi gian" in str(e) or "dong ket noi" in str(e) or "dia chi bus" in str(e): self._sbus_drop()
            raise

    def clip_set(self, s):
        """Đặt chữ vào bộ nhớ copy của phiên KDE: wl-copy (gói wl-clipboard) nếu máy có, không thì nhờ Klipper (bộ nhớ copy của Plasma, D-Bus —
           đặt cả vùng chọn). → True nếu đặt được."""
        if self._wl():
            try:
                if subprocess.run(["wl-copy", "--type", "text/plain;charset=utf-8"], input=s.encode("utf-8"), timeout=5).returncode == 0: return True
            except (OSError, subprocess.TimeoutExpired): pass
        if not s: return False
        try:
            self._scall(*KLIPPER, "setClipboardContents", "s", [s], timeout=3.0)
            time.sleep(0.08)                                          # Klipper đặt xong bên Wayland ngay sau khi trả lời → chờ chút mới dán
            return True
        except Exception as e:
            if not self.klip_told: self.klip_told = True; self.log("bo nho copy: may khong co wl-copy, Klipper cung khong nhan (%s)" % str(e)[:160])
            return False

    def clip_get(self):
        if self._wl():
            try:
                r = subprocess.run(["wl-paste", "--no-newline", "--type", "text"], capture_output=True, timeout=3)
                return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired): return None
        try: return str(self._scall(*KLIPPER, "getClipboardContents", timeout=2.0)[0])
        except Exception: return None

    def active(self):
        """Loại cửa sổ đang chọn trên máy ("term" / "sel" / "app", xem app_kind) — nạp 1 đoạn script vào KWin, script gọi ngược về đây qua D-Bus.
           None = không hỏi được. Nhớ ACT_TTL_S giây; hỏng 3 lần liền thì thôi hỏi (dán bằng Shift+Insert)."""
        now = time.time()
        if now - self.act_t < ACT_TTL_S: return self.act_kind
        if self.act_fail >= 3: return None
        self.act_n += 1; n = str(self.act_n); name = "cloudblue_active_%d" % os.getpid(); path = None
        try:
            rt = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()             # thư mục riêng của khách (không dùng /tmp chung)
            if not os.path.isdir(rt) or os.stat(rt).st_uid != os.getuid(): raise DBusError("khong co thu muc rieng %s" % rt)
            b = self._sbus()
            path = os.path.join(rt, "cloudblue-active-%d.js" % os.getpid())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(ACTIVE_JS % (json.dumps(b.name), ACT_PATH, ACT_IFACE, json.dumps(n)))
            try: self._scall(*KWIN_SCRIPTING, "unloadScript", "s", [name])        # lần trước hỏng giữa chừng còn nằm trong KWin
            except DBusError: pass
            sid = int(self._scall(*KWIN_SCRIPTING, "loadScript", "ss", [path, name])[0])
            if sid < 0: raise DBusError("KWin khong nap script (%d)" % sid)
            for p in ("/Scripting/Script%d" % sid, "/%d" % sid, None):        # chạy: Plasma 6 · Plasma 5 · (cuối) chạy mọi script đã nạp
                try:
                    if p is None: self._scall(*KWIN_SCRIPTING, "start")
                    else: self._scall("org.kde.KWin", p, "org.kde.kwin.Script", "run")
                    break
                except DBusError:
                    if p is None or self.sb is not b: raise
            m = b.take(lambda m: m["type"] == 1 and m["member"] == "Active" and m["path"] == ACT_PATH and m["body"]
                       and str(m["body"][0]).split("\n", 1)[0] == n, 1.5)
            if not m["flags"] & 1: b.send(2, {5: ("u", m["serial"]), 6: ("s", m["sender"])})   # trả lời (KWin khỏi chờ)
            info = str(m["body"][0]).split("\n", 1)[1] if "\n" in str(m["body"][0]) else ""
            self.act_fail = 0; self.act_t = time.time(); self.act_kind = app_kind(info)
            self.act_info = " / ".join(x for x in info.split("\n") if x)[:120] or "(khong co cua so nao)"
            return self.act_kind
        except Exception as e:
            self.act_fail += 1; self.act_t = 0.0
            if "qua thoi gian" in str(e): self._sbus_drop()
            self.log("dan: chua hoi duoc KWin cua so dang chon (lan %d: %s) -> dan bang Shift+Insert" % (self.act_fail, str(e)[:160]))
            return None
        finally:
            if path is not None:
                if self.sb is not None:
                    try: self._scall(*KWIN_SCRIPTING, "unloadScript", "s", [name])
                    except Exception: pass
                try: os.unlink(path)
                except OSError: pass

    def paste(self, mode=1):
        """Dán bộ nhớ copy vào cửa sổ đang chọn. mode 2 = khách tự bấm Ctrl+Shift+V (bấm đúng tổ hợp đó); còn lại chọn phím theo loại cửa sổ
           (PASTE_KEYS: dòng lệnh Ctrl+Shift+V · app thường Ctrl+V · xterm / không biết Shift+Insert). → loại cửa sổ đã dùng."""
        p = self._in()
        if p is None: return None
        kind = "term" if int(mode or 1) == 2 else self.active()
        keys = PASTE_KEYS.get(kind, PASTE_KEYS[None])
        for c in keys: p.keycode(c, True)
        for c in reversed(keys): p.keycode(c, False)
        if kind != self.paste_last:
            self.paste_last = kind
            self.log("dan vao %s bang %s" % ("cua so khach chon (Ctrl+Shift+V)" if int(mode or 1) == 2 else self.act_info or "?", PASTE_NAME.get(kind, "Shift+Insert")))
        return kind


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
                    if rid is not None: send({"id": rid, "ok": True, "pid": pid, "mode": cap.mode, "size": list(cap.size), "backend": cap.backend})
                elif op == "open":
                    sz = cap.open(portal=j.get("portal") is not False)
                    if rid is not None: send({"id": rid, "ok": True, "size": list(sz), "backend": cap.backend, "open_s": cap.first})
                elif op == "stop": cap.stop()
                elif op == "move": cap.move(int(j["x"]), int(j["y"]))
                elif op == "btn": cap.btn(int(j["b"]), bool(j["d"]))
                elif op == "wheel": cap.wheel(int(j["v"]), bool(j.get("h")))
                elif op == "key": cap.key(int(j["vk"]), bool(j["d"]), bool(j.get("ext")))
                elif op == "text": cap.text(str(j.get("s") or ""))
                elif op == "clip_set": cap.clip_set(str(j.get("s") or ""))
                elif op == "paste":
                    k = cap.paste(int(j.get("m") or 1))
                    if rid is not None: send({"id": rid, "ok": True, "kind": k})
                elif op == "clip_get": send({"id": rid, "ok": True, "s": cap.clip_get()})
                elif op == "size": send({"id": rid, "ok": True, "size": list(cap.size) if cap.node is not None else None, "backend": cap.backend})
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
        out.update(session=True, backend=cap.backend, size=list(sz), node=cap.node, open_s=round(time.time() - t0, 1))
        if cap.backend == "portal":
            out.update(app=cap.portal.app, devices=cap.portal.devices, cursor_modes=cap.portal.cursor[0], cursor_mode=cap.portal.cursor[1])
            try:                                                 # 1 lệnh chuột CÓ chờ trả lời: cổng XDG từ chối thì biết ngay vì sao
                cap.portal.b.call(PORTAL, PORTAL_PATH, RD, "NotifyPointerMotionAbsolute", "oa{sv}udd", [cap.portal.session, {}, cap.portal.node, 100.0, 100.0])
                out["move_reply"] = "ok"
            except DBusError as e:
                out["move_reply"] = str(e)[:200]
        else:
            k = cap.kw
            out.update(output=k.out, outputs=k.outs, geo=list(k.geo), fake_input=k.fi_ver, virtual=k.virtual, exe=os.path.realpath("/proc/self/exe"))
            try:                                                 # KWin chưa nhận gì thì roundtrip lỗi ngay
                k.motion(100.0, 100.0); k.wl.roundtrip(3); out["move_reply"] = "ok"
            except Exception as e:
                out["move_reply"] = str(e)[:200]
        cap.move(32768, 32768); cap.move(40000, 20000); out["move"] = True
        if os.environ.get("CBCAP_PROBE_CLIP") == "1":                    # 23.11b (CI): bộ nhớ copy + hỏi KWin cửa sổ đang chọn — ĐỔI bộ nhớ copy của máy
            try:
                t1 = "cloudblue-probe-%d" % random.randrange(10 ** 6)
                out["clip"] = {"wl": cap._wl(), "set": cap.clip_set(t1)}
                time.sleep(0.3); out["clip"]["get_ok"] = cap.clip_get() == t1
                t0 = time.time(); k = cap.active()
                out["active"] = {"kind": k, "win": cap.act_info, "s": round(time.time() - t0, 2)}
            except Exception as e:
                out["clip_err"] = "%s: %s" % (type(e).__name__, str(e)[:200])
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
    print("cbcap probe: backend=%s virtual=%d rtp=%d err=%s%s" % (out.get("backend"), 1 if out.get("virtual") else 0, out.get("rtp_packets", 0), str(out.get("err") or "-")[:160],
          (" clip=%s active=%s" % (json.dumps(out.get("clip") or out.get("clip_err")), json.dumps(out.get("active"), ensure_ascii=False))) if "clip" in out or "clip_err" in out else ""), flush=True)
    return 0 if out.get("session") and (not ok or out.get("rtp_packets", 0) > 20) else 1


def main(argv):
    if argv[:1] == ["serve"] and len(argv) >= 3 and argv[1] == "--fd": return serve(int(argv[2]))
    if argv[:1] == ["probe"]: return probe(float(argv[1]) if len(argv) > 1 else 4.0)
    if argv[:1] == ["version"]: print(CAP_VER); return 0
    print("cbcap %s: serve --fd N | probe [giay] | version" % CAP_VER); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
