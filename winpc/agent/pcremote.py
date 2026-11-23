# -*- coding: utf-8 -*-
# =====================================================================================================
#  pcremote.py — ĐIỀU KHIỂN TỪ XA trên MÁY PC CHO THUÊ (đợt 2 · bản 22.11c — số bản theo agent; ô xem trước "Xem tất cả" chạy bằng
#  lệnh R_START chất lượng thấp của trạm 22/11b, máy PC không phải đổi gì)
#
#  pcagent (SYSTEM) mở chương trình này vào PHIÊN MÀN HÌNH đang hiện của máy. Việc làm:
#    1. hỏi web (pc_relay_where, bằng mã riêng của máy) xem nối tới máy chủ phát hình nào → tự nối RA máy chủ đó (TLS, kiểm đúng
#       mã chứng chỉ; không được thì đi đường vòng Cloudflare) rồi ngồi chờ. Máy KHÔNG mở cổng nào, không ai nối thẳng vào máy được.
#    2. có người mở điều khiển (khách được gán máy / admin — máy chủ kiểm quyền) → máy chủ gửi R_START → máy quay màn hình + nén H.264
#       bằng ffmpeg (card NVIDIA / Intel / AMD, không có thì CPU) rồi gửi từng khung; nhận chuột / phím / chữ / bộ nhớ copy và làm theo.
#    3. hết người xem (R_STOP) → TẮT bộ quay, nhả mọi phím / nút chuột đang giữ. Không ai xem thì máy không tốn CPU / card hình.
#  Admin (không phải khách được gán máy) vào xem → người ngồi máy thấy 1 hộp báo "quản trị viên đang hỗ trợ từ xa".
#  ffmpeg: tải 1 lần từ GitHub (bản 6.1.1 của Gyan), kiểm đúng mã sha256 đã ghim rồi mới dùng → C:\CloudBluePC\bin\ffmpeg.exe
#
#  Lệnh:  pcremote.py run        chạy thật (pcagent gọi)          pcremote.py selfcheck   bản mới tự thử trước khi thay bản cũ
#         pcremote.py probe      in ra máy này quay / nén được kiểu nào                  Nhật ký: C:\CloudBluePC\logs\remote.log
#  Tắt hẳn trên 1 máy: thêm "remote": false vào C:\CloudBluePC\cb.json. Tắt cả hệ thống / từng máy: Bảng quản trị › 💻 Máy PC.
# =====================================================================================================
import base64, collections, hashlib, json, os, queue, random, re, socket, ssl, struct, subprocess, sys, threading, time, urllib.parse

REMOTE_VER = "23.11c"
IME_ON = True                                                    # 22.11b: theo dõi ô nhập chữ → app điện thoại tự bật bàn phím (cb.json "ime": false = tắt)
WIN = os.name == "nt"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))                 # C:\CloudBluePC
MUTEX = "Global\\CloudBluePCRemote"

# ---- giao thức BRS2 (docs/STREAM-PROTOCOL.md) ----
C_TOUCH, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_PING, C_QUALITY, C_KEYFRAME, C_CLIP, C_ACK, C_MOUSE = 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1B
S_VIDEO, S_SIZE, S_CLIP, S_PONG, S_ERROR, S_STATS = 0x82, 0x83, 0x84, 0x85, 0x86, 0x87
P_HELLO, P_INFO, R_OK, R_START, R_STOP, R_SLOW = 0x02, 0x03, 0x90, 0x91, 0x92, 0x93

# ---- ffmpeg (cùng bản máy chủ phát hình đang dùng) ----
FF_URL = "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip"
FF_ZIP_SIZE = 87520045
FF_ZIP_SHA = "742e32fc9f92681f9f254b925e1b613fdd8074ba40749d4879aefdb009b94cc5"
FF_EXE_SHA = "04e1307997530f9cf2fe35cba2ca7e8875ca91da02f89d6c7243df819c94ad00"       # bin/ffmpeg.exe bên trong file zip

# ---- chất lượng ----
PRESETS = {"eco": (1280, 30, 2000), "bal": (1920, 30, 4500), "hd": (1920, 60, 9000), "uhd": (2560, 60, 16000)}  # cạnh dài tối đa, khung/giây, kbps ("auto" = bal + tự hạ / tăng)
QS = ("auto", "eco", "bal", "hd", "uhd")   # Tự động · Tiết kiệm · Cân bằng · Nét · Siêu nét (21.11g)
FIX_TIERS = ((900, 1280, 30),)            # khách TỰ CHỌN độ nét: giữ độ phân giải, chỉ bớt khi mạng rất yếu
TIERS = ((500, 960, 15), (900, 1280, 20), (1600, 1280, 30), (2600, 1600, 30))           # bitrate dưới mức này → cạnh dài tối đa, khung/giây tối đa
MIN_KBPS, MAX_KBPS = 300, 20000
CPU_SIDE, CPU_FPS = 1600, 30              # nén bằng CPU (không có card nén): nhẹ hơn để không giành CPU của người đang dùng máy
LAG_DROP_MS = {"direct": 350, "wsd": 350, "ws": 700}       # người xem chậm hơn mức này → bỏ khung tới khung khoá kế (đường vòng Cloudflare cho rộng hơn)
ENCODERS = ("nvenc", "qsv", "amf", "x264")
BAD_S = 1800                              # bộ nén / cách quay vừa lỗi → 30 phút sau mới thử lại
CLIP_MAX = 256 * 1024


def clamp(v, lo, hi, d=0):
    try: v = int(v)
    except (TypeError, ValueError, OverflowError): return d
    return max(lo, min(hi, v))


# ====================================================================================== PHẦN THUẦN (thử được trên mọi máy)
def fit(sw, sh, side):
    """Thu cỡ màn hình về cạnh dài ≤ side (không phóng to), giữ tỉ lệ, 2 cạnh chẵn."""
    sw, sh = max(16, int(sw)), max(16, int(sh))
    m = max(sw, sh)
    if side and m > side:
        k = side / float(m); sw, sh = int(sw * k + 0.5), int(sh * k + 0.5)
    return max(16, sw & ~1), max(16, sh & ~1)


def plan(q, fps_req, maxh_req, kbps_req, kbps_cur, sw, sh, cpu=False, fps_fix=0):
    """Chọn cỡ hình + khung/giây + bitrate cho phiên → (rộng, cao, khung/giây, kbps, trần kbps).
       fps_req = máy người xem chỉ chịu tới mức này (chỉ HẠ) · fps_fix = khung/giây KHÁCH TỰ CHỌN (21.11g, 5–120, kể cả cao hơn mặc định của mức nét).
       Tự động: bitrate tụt → bớt điểm ảnh + khung (TIERS) cho hình không vỡ ô.
       Khách tự chọn độ nét (eco / bal / hd / uhd): GIỮ độ phân giải — chỉ bớt khi mạng rất yếu (< 900 kbps)."""
    fix = q in PRESETS
    side, fps, cap = PRESETS.get(q, PRESETS["bal"])
    if kbps_req: cap = clamp(kbps_req, MIN_KBPS, MAX_KBPS, cap)
    if fps_fix: fps = max(5, min(120, clamp(fps_fix, 1, 240, fps)))
    if fps_req: fps = max(5, min(fps, clamp(fps_req, 1, 240, fps)))
    if maxh_req and int(maxh_req) >= 320: side = min(side, int(maxh_req))
    if cpu: side = min(side, 1920 if fix else CPU_SIDE); fps = min(fps, 60 if fix or fps_fix else CPU_FPS)
    k = clamp(kbps_cur or cap, MIN_KBPS, cap, cap)
    for lim, s, f in (FIX_TIERS if fix else TIERS):
        if k < lim: side = min(side, s); fps = min(fps, f); break
    w, h = fit(sw, sh, side)
    return w, h, fps, k, cap


def kbps_start(cap, q, net="", link="", dl=0):
    """Bitrate lúc bắt đầu: Tự động + người xem dùng 4G / đi đường vòng → bắt đầu nhẹ rồi tự tăng; app báo tốc độ tải thấp → 60% tốc độ đó."""
    k = cap
    if q == "auto" and (net == "c" or link == "ws"): k = min(k, 1500)
    if dl and 0 < int(dl) < 2500: k = min(k, int(int(dl) * 0.6))
    return max(MIN_KBPS, min(cap, k))


class Rate:
    """Tự chỉnh bitrate theo tốc độ người xem THẬT SỰ nhận (gói ACK) + báo nghẽn (máy chủ báo khách nhận chậm / đường lên của máy nghẽn)."""
    DOWN_GAP, UP_GAP, REPEAT, WIN_S = 8.0, 45.0, 3, 20.0

    def __init__(self, cap, start):
        self.cap, self.cur = int(cap), int(min(cap, start))
        self.inflight = collections.deque(); self.delivered = collections.deque(); self.lat = collections.deque()
        self.base_ms = 0.0; self.ack_t = 0.0; self.t_change = 0.0; self.events = collections.deque(maxlen=40)
        self.hold_until = 0.0; self.hold_s = 0.0; self.last_cong = 0.0; self.lag_ms = 0

    def sent(self, pts, n, now):
        self.inflight.append((pts, n, now))
        if len(self.inflight) > 3000: self.inflight.popleft()

    def ack(self, pts, now, mono_us=None):
        got = 0; last = None
        while self.inflight and self.inflight[0][0] <= pts:
            _, n, last = self.inflight.popleft(); got += n
        self.ack_t = now
        if mono_us is not None: self.lag_ms = max(0, int((mono_us - pts) / 1000))
        if got: self.delivered.append((now, got))
        while self.delivered and now - self.delivered[0][0] > 7: self.delivered.popleft()
        if last is not None:
            self.lat.append((now, (now - last) * 1000.0))
            while self.lat and now - self.lat[0][0] > 10: self.lat.popleft()
            self.base_ms = min(250.0, min(s for _, s in self.lat))      # trễ nền của đường truyền (quá 0,25 giây là nghẽn, không phải "mạng xa")

    def behind_ms(self, now):
        """Khung cũ nhất người xem chưa báo nhận đã đi bao lâu, trừ trễ nền. Người xem không gửi ACK → 0."""
        if not self.ack_t or not self.inflight: return 0.0
        return max(0.0, (now - self.inflight[0][2]) * 1000.0 - self.base_ms)

    def goodput(self, now):
        return sum(n for t, n in self.delivered if now - t <= 2.0) * 8 / 2.0 / 1000

    def congested(self, now, hard=False):
        """Ghi 1 lần nghẽn. Trả bitrate MỚI (đã hạ) hoặc None: 1–2 lần giật lẻ chỉ bỏ khung, lặp lại ≥ 3 lần / 20 giây (nghẽn thật: 2 lần) mới hạ."""
        self.events.append(now); self.last_cong = now
        n = sum(1 for t in self.events if now - t <= self.WIN_S and t > self.t_change)
        if not (n >= self.REPEAT or (hard and n >= 2)) or now - self.t_change <= self.DOWN_GAP: return None
        gp = self.goodput(now) if self.ack_t and now - self.ack_t < 3 else 0
        new = int(max(MIN_KBPS, min(self.cur * 0.7, gp * 0.8 if gp > 50 else self.cur * 0.6)))
        if new >= self.cur * 0.92: return None
        self.hold_s = min(600.0, self.hold_s * 2) if self.hold_s and now - self.hold_until < 180 else 40.0
        self.cur = new; self.t_change = now; self.hold_until = now + self.hold_s
        return new

    def raise_(self, now):
        """Yên đủ lâu → thử tăng 1 bước (×1,25). Trả bitrate mới hoặc None."""
        if self.cur >= self.cap or now < self.hold_until or now - self.last_cong < self.UP_GAP or now - self.t_change < self.UP_GAP: return None
        self.cur = int(min(self.cap, max(self.cur + 50, self.cur * 1.25))); self.t_change = now
        return self.cur


class RtpAssembler:
    """Ghép gói RTP (RFC 6184) của ffmpeg thành từng khung H.264 Annex-B. Bit marker = hết khung → trả NGAY (không chờ khung sau)."""
    SC = b"\x00\x00\x00\x01"

    def __init__(self):
        self.au = []; self.key = self.cfg = self.bad = False; self.last_seq = None; self.fu = None

    def feed(self, pkt):
        """1 gói RTP → None (chưa hết khung) · (dữ liệu, khung_khoá, có_SPS_PPS) · (None, False, False) = khung hỏng (mất gói) → chờ khung khoá."""
        if len(pkt) < 13 or (pkt[0] >> 6) != 2: return None
        cc = pkt[0] & 0x0F; ext = pkt[0] & 0x10; pad = pkt[0] & 0x20
        marker = pkt[1] & 0x80; seq = (pkt[2] << 8) | pkt[3]
        off = 12 + 4 * cc
        if ext and len(pkt) >= off + 4: off += 4 + 4 * struct.unpack(">H", pkt[off + 2:off + 4])[0]
        end = len(pkt) - (pkt[-1] if pad else 0)
        pl = pkt[off:end]
        if self.last_seq is not None and seq != (self.last_seq + 1) & 0xFFFF: self.bad = True
        self.last_seq = seq
        if pl:
            t = pl[0] & 0x1F
            if 1 <= t <= 23:
                self.au.append(self.SC + pl)
                if t == 5: self.key = True
                elif t in (7, 8): self.cfg = True
            elif t == 24:                                       # STAP-A
                i = 1
                while i + 2 <= len(pl):
                    n = (pl[i] << 8) | pl[i + 1]; i += 2
                    nal = pl[i:i + n]; i += n
                    if nal:
                        self.au.append(self.SC + nal); nt = nal[0] & 0x1F
                        if nt == 5: self.key = True
                        elif nt in (7, 8): self.cfg = True
            elif t == 28 and len(pl) >= 2:                      # FU-A
                s, e, nt = pl[1] & 0x80, pl[1] & 0x40, pl[1] & 0x1F
                if s: self.fu = bytearray(self.SC + bytes([(pl[0] & 0xE0) | nt])) + pl[2:]
                elif self.fu is not None: self.fu += pl[2:]
                else: self.bad = True
                if e and self.fu is not None:
                    self.au.append(bytes(self.fu)); self.fu = None
                    if nt == 5: self.key = True
        if not marker: return None
        out = None
        if self.au and not self.bad: out = (b"".join(self.au), self.key, self.cfg)
        elif self.bad: out = (None, False, False)
        self.au = []; self.key = self.cfg = self.bad = False; self.fu = None
        return out


# ---- phím: mã phím Android (giao thức) → phím ảo Windows (mã, phím mở rộng) ----
VK = {4: (0x1B, 0), 66: (0x0D, 0), 160: (0x0D, 1), 67: (0x08, 0), 112: (0x2E, 1), 61: (0x09, 0), 111: (0x1B, 0), 62: (0x20, 0),
      19: (0x26, 1), 20: (0x28, 1), 21: (0x25, 1), 22: (0x27, 1), 122: (0x24, 1), 123: (0x23, 1), 92: (0x21, 1), 93: (0x22, 1), 124: (0x2D, 1),
      59: (0xA0, 0), 60: (0xA1, 0), 113: (0xA2, 0), 114: (0xA3, 1), 57: (0xA4, 0), 58: (0xA5, 1), 117: (0x5B, 1), 118: (0x5C, 1), 82: (0x5D, 1),
      115: (0x14, 0), 143: (0x90, 1), 116: (0x91, 0), 120: (0x2C, 1), 121: (0x13, 0),
      68: (0xC0, 0), 69: (0xBD, 0), 70: (0xBB, 0), 71: (0xDB, 0), 72: (0xDD, 0), 73: (0xDC, 0), 74: (0xBA, 0), 75: (0xDE, 0), 55: (0xBC, 0), 56: (0xBE, 0), 76: (0xBF, 0),
      154: (0x6F, 1), 155: (0x6A, 0), 156: (0x6D, 0), 157: (0x6B, 0), 158: (0x6E, 0),
      24: (0xAF, 1), 25: (0xAE, 1), 164: (0xAD, 1), 85: (0xB3, 1), 87: (0xB0, 1), 88: (0xB1, 1)}
VK.update({29 + i: (0x41 + i, 0) for i in range(26)})            # A–Z
VK.update({7 + i: (0x30 + i, 0) for i in range(10)})             # 0–9
VK.update({131 + i: (0x70 + i, 0) for i in range(12)})           # F1–F12
VK.update({144 + i: (0x60 + i, 0) for i in range(10)})           # bàn phím số 0–9
META = ((0x1, 0xA0, (0xA0, 0xA1, 0x10)), (0x2, 0xA4, (0xA4, 0xA5, 0x12)), (0x1000, 0xA2, (0xA2, 0xA3, 0x11)), (0x10000, 0x5B, (0x5B, 0x5C)))   # bit meta → phím bổ trợ + các phím tương đương
MOD_VKS = frozenset(v for _, _, g in META for v in g)
EXT_VKS = frozenset(v for v, e in VK.values() if e)
CMDS = {"back": (0x1B,), "home": (0x5B, 0x44), "recents": (0x5B, 0x09), "menu": (0x5D,), "volup": (0xAF,), "voldown": (0xAE,), "mute": (0xAD,),
        "notif": (0x5B, 0x41), "win": (0x5B,), "taskmgr": (0xA2, 0xA0, 0x1B), "alttab": (0xA4, 0x09), "altf4": (0xA4, 0x73), "desktop": (0x5B, 0x44),
        "explorer": (0x5B, 0x45), "enter": (0x0D,)}                # lệnh nút bấm trên app → tổ hợp phím (power / rotate: bỏ qua)


class Keys:
    """Phím từ người xem → phím Windows. Nhớ phím đang giữ để NHẢ HẾT khi phiên đóng (không kẹt phím)."""
    def __init__(self, out):
        self.o = out; self.down = set(); self.auto = {}; self.auto_held = set()

    def _held(self, group): return any(v in self.down or v in self.auto_held for v in group)

    def key(self, action, code, meta=0):
        """action 0 = nhấn · 1 = nhả. App cũ không gửi phím bổ trợ riêng mà kèm trong meta (Ctrl+A = phím A + meta CTRL) → tự nhấn kèm."""
        m = VK.get(int(code))
        if m is None: return False
        vk, ext = m
        if action == 0:
            if vk not in MOD_VKS and vk not in self.down:
                add = [mvk for bit, mvk, group in META if meta & bit and not self._held(group)]
                for mvk in add: self.o.key(mvk, True, mvk in EXT_VKS); self.auto_held.add(mvk)
                if add: self.auto[vk] = add
            self.o.key(vk, True, bool(ext)); self.down.add(vk)
        else:
            self.o.key(vk, False, bool(ext)); self.down.discard(vk)
            for mvk in reversed(self.auto.pop(vk, [])):
                self.o.key(mvk, False, mvk in EXT_VKS); self.auto_held.discard(mvk)
        return True

    def tap(self, *vks):
        for v in vks: self.o.key(v, True, v in EXT_VKS)
        for v in reversed(vks): self.o.key(v, False, v in EXT_VKS)

    def release_all(self):
        for vk in list(self.down): self.o.key(vk, False, vk in EXT_VKS)
        for vk in list(self.auto_held): self.o.key(vk, False, vk in EXT_VKS)
        self.down.clear(); self.auto.clear(); self.auto_held.clear()


class Touch:
    """Chạm (điện thoại / app cũ) → chuột: chạm nhanh = bấm trái · giữ yên 0,55 giây = bấm PHẢI · chạm rồi kéo = kéo thả ·
       chạm 2 lần liền = bấm đúp (lần 2 trúng đúng điểm lần 1) · 2 ngón vuốt = cuộn."""
    SLOP, LONG_S, DBL_S, DBL_D, WHEEL_K, STEP = 900, 0.55, 0.45, 2200, 1800.0, 30

    def __init__(self, out):
        self.o = out; self.p = {}; self.st = None; self.x0 = self.y0 = 0; self.t0 = 0.0
        self.t_tap = -9.0; self.tap_x = self.tap_y = 0; self.cx = self.cy = 0.0; self.av = self.ah = 0.0; self.left = False

    def _avg(self):
        n = float(len(self.p)) or 1.0
        return sum(x for x, _ in self.p.values()) / n, sum(y for _, y in self.p.values()) / n

    def touch(self, a, ptr, x, y, now):
        if a == 0:
            self.p[ptr] = (x, y)
            if len(self.p) == 1:
                self.x0, self.y0, self.t0, self.st = x, y, now, "pend"; self.o.move(x, y)
            elif len(self.p) == 2:
                if self.left: self.o.button(0, False); self.left = False
                self.st = "scroll"; self.cx, self.cy = self._avg(); self.av = self.ah = 0.0
            return
        if a == 2:
            if ptr not in self.p: return
            self.p[ptr] = (x, y)
            if self.st == "pend":
                if abs(x - self.x0) > self.SLOP or abs(y - self.y0) > self.SLOP:
                    self.o.move(self.x0, self.y0); self.o.button(0, True); self.left = True; self.st = "drag"; self.o.move(x, y)
            elif self.st == "drag": self.o.move(x, y)
            elif self.st == "scroll" and len(self.p) >= 2:
                ax, ay = self._avg(); dx, dy = ax - self.cx, ay - self.cy; self.cx, self.cy = ax, ay
                self.av += dy / 65535.0 * self.WHEEL_K; self.ah -= dx / 65535.0 * self.WHEEL_K     # vuốt xuống = nội dung đi xuống = lăn chuột lên
                v, h = int(self.av / self.STEP) * self.STEP, int(self.ah / self.STEP) * self.STEP
                if v: self.av -= v; self.o.wheel(v, False)
                if h: self.ah -= h; self.o.wheel(h, True)
            return
        if self.p.pop(ptr, None) is None: return                # nhả (1) / huỷ (3)
        if self.st == "pend" and a == 1:
            tx, ty = self.x0, self.y0
            if now - self.t_tap < self.DBL_S and abs(tx - self.tap_x) < self.DBL_D and abs(ty - self.tap_y) < self.DBL_D: tx, ty = self.tap_x, self.tap_y
            self.o.move(tx, ty); self.o.button(0, True); self.o.button(0, False)
            self.t_tap, self.tap_x, self.tap_y = now, tx, ty
        elif self.st == "drag":
            if a == 1: self.o.move(x, y)
            if self.left: self.o.button(0, False); self.left = False
        self.st = None if not self.p else ("scroll" if self.st == "scroll" and len(self.p) >= 2 else "wait")

    def tick(self, now):
        if self.st == "pend" and now - self.t0 >= self.LONG_S:
            self.o.button(1, True); self.o.button(1, False); self.st = "long"

    def reset(self):
        if self.left: self.o.button(0, False); self.left = False
        self.p.clear(); self.st = None


class Pointer:
    """Chuột thật (C_MOUSE): rê không bấm, nút trái / phải / giữa / 2 nút phụ. Nhớ nút đang giữ để nhả khi phiên đóng."""
    def __init__(self, out): self.o = out; self.held = set()

    def mouse(self, action, button, x, y):
        self.o.move(x, y)
        if action == 0 or button > 4: return
        if action == 1: self.o.button(button, True); self.held.add(button)
        elif action == 2: self.o.button(button, False); self.held.discard(button)

    def release_all(self):
        for b in list(self.held): self.o.button(b, False)
        self.held.clear()


def clean_text(s, limit=64 * 1024):
    """Chữ sẽ gõ vào máy: bỏ ký tự điều khiển (giữ xuống dòng + tab), cắt bớt nếu quá dài."""
    s = s[:limit].replace("\r\n", "\n").replace("\r", "\n")
    return "".join(c for c in s if c in "\n\t" or ord(c) >= 32)


# ---- lệnh ffmpeg ----
def enc_args(enc, fps, kbps, x264_preset="superfast", nv_preset="p4"):
    """Tham số bộ nén H.264 độ trễ thấp (giống máy chủ phát hình): khung khoá mỗi ~1 giây, không khung B, bitrate cố định, bộ đệm ~6 khung."""
    gop = str(max(int(fps * (2 if kbps < 450 else 1)), 10))
    buf = "%dk" % max(kbps * 6 // max(fps, 1), min(250, max(96, kbps // 2)))
    rate = ["-b:v", "%dk" % kbps, "-maxrate", "%dk" % kbps, "-bufsize", buf]
    if enc == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", nv_preset, "-tune", "ull", "-zerolatency", "1", "-delay", "0", "-rc", "cbr", "-profile:v", "baseline",
                "-bf", "0", "-g", gop, "-forced-idr", "1", "-strict_gop", "1"] + rate
    if enc == "qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-profile:v", "baseline", "-look_ahead", "0", "-async_depth", "1", "-bf", "0", "-g", gop] + rate
    if enc == "amf":
        return ["-c:v", "h264_amf", "-usage", "ultralowlatency", "-quality", "speed", "-rc", "cbr", "-profile:v", "constrained_baseline",
                "-bf", "0", "-g", gop] + rate
    return ["-c:v", "libx264", "-preset", x264_preset, "-tune", "zerolatency", "-profile:v", "baseline", "-threads", "1", "-x264-params",
            "sliced-threads=0:keyint=%s:min-keyint=%s:scenecut=0:bframes=0:rc-lookahead=0:sync-lookahead=0:repeat-headers=1" % (gop, gop)] + rate


def ff_cmd(ff, cap, enc, sw, sh, w, h, fps, kbps, port):
    """Dòng lệnh ffmpeg: quay màn hình chính (dda = Desktop Duplication · gdi = GDI · test = hình thử) → thu cỡ → nén → RTP về 127.0.0.1:port."""
    pix = "bgra" if enc == "nvenc" else ("nv12" if enc in ("qsv", "amf") else "yuv420p")       # card NVIDIA nhận thẳng BGRA (tự đổi màu trong card)
    vf = []
    if (w, h) != (sw, sh): vf.append("scale=%d:%d:flags=bicubic" % (w, h))
    if pix != "bgra" or cap == "test": vf.append("format=" + ("yuv420p" if cap == "test" and pix == "bgra" else pix))
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if cap == "dda":
        cmd += ["-filter_complex", ",".join(["ddagrab=output_idx=0:framerate=%d:draw_mouse=1" % fps, "hwdownload", "format=bgra"] + vf)]
    elif cap == "test":
        cmd += ["-re", "-f", "lavfi", "-i", "testsrc2=size=%dx%d:rate=%d" % (sw, sh, fps)]
        if vf: cmd += ["-vf", ",".join(vf)]
    else:
        cmd += ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1", "-offset_x", "0", "-offset_y", "0", "-video_size", "%dx%d" % (sw, sh), "-i", "desktop"]
        if vf: cmd += ["-vf", ",".join(vf)]
    cmd += enc_args(enc, fps, kbps)
    cmd += ["-an", "-bsf:v", "dump_extra=freq=keyframe", "-f", "rtp", "-rtpflags", "skip_rtcp", "-payload_type", "96", "rtp://127.0.0.1:%d?pkt_size=1300" % port]
    return cmd


def parse_paths(stream):
    """Đường nối tới máy chủ phát hình (pc_relay_where.stream) → [(kiểu, địa chỉ, cổng, giây chờ)], mã chứng chỉ. Nối thẳng trong mạng nhà trước."""
    st = stream if isinstance(stream, dict) else {}
    cert = st.get("cert") if isinstance(st.get("cert"), str) and re.fullmatch(r"[0-9a-fA-F]{64}", st.get("cert") or "") else ""
    out = []
    if cert:
        ds = [d for d in (st.get("direct") if isinstance(st.get("direct"), list) else []) if isinstance(d, dict) and isinstance(d.get("host"), str)
              and re.fullmatch(r"[A-Za-z0-9.\-:]{1,80}", d["host"]) and isinstance(d.get("port"), int) and 1 <= d["port"] <= 65535]
        out += [("direct", d["host"], int(d["port"]), 1.5) for d in ds if d.get("lan")][:4]
        out += [("direct", d["host"], int(d["port"]), 4.0) for d in ds if not d.get("lan")][:4]
    ws = st.get("ws")
    if isinstance(ws, str) and re.fullmatch(r"wss://[A-Za-z0-9.\-]{1,120}(:\d{1,5})?(/[A-Za-z0-9._~/\-]{0,120})?", ws): out.append(("ws", ws, 0, 8.0))
    return out, cert.lower()


# ====================================================================================== ĐƯỜNG TRUYỀN
class Refused(Exception):
    """Máy chủ phát hình từ chối (gói ERROR): AUTH = sai mã máy · OFF = chưa bật điều khiển từ xa · BUSY = thử lại sau."""
    def __init__(self, code, msg=""): super().__init__(msg or code); self.code = code


class Tls:
    """22.11a · TLS qua MemoryBIO — thay ssl.SSLSocket dùng chung nhiều luồng.
       Máy gửi hình (luồng gửi) + PING (luồng phụ) trong lúc luồng đọc đang chờ chuột / phím của khách — CÙNG 1 kết nối.
       ssl.SSLSocket (OpenSSL) không chịu được đọc + ghi cùng lúc từ 2 luồng: trạng thái "đang chờ đọc" bị luồng ghi đè → luồng đọc báo lỗi giả
       (WinError 10035) hoặc ĐỨT GIẢ ("EOF occurred in violation of protocol") dù mạng vẫn tốt → máy rớt khỏi máy chủ phát hình, khách thấy
       "Mất kết nối — đang nối lại" cứ được một lúc. Ở đây mọi thao tác trên đối tượng SSL nằm trong 1 khoá (chỉ mã hoá / giải mã trong RAM);
       đọc / ghi socket thật nằm NGOÀI khoá; khoá ghi riêng giữ đúng thứ tự bản ghi TLS."""

    def __init__(self, raw, ctx, sni):
        self.raw = raw; self.inb = ssl.MemoryBIO(); self.outb = ssl.MemoryBIO()
        self.obj = ctx.wrap_bio(self.inb, self.outb, server_side=False, server_hostname=sni)
        self.sl = threading.Lock(); self.wl = threading.Lock()
        while True:                                            # bắt tay (timeout của socket thật áp dụng)
            try:
                with self.sl: self.obj.do_handshake()
                self._flush(); break
            except ssl.SSLWantReadError:
                self._flush()
                x = raw.recv(65536)
                if not x: raise ssl.SSLError("may chu dong ket noi khi bat tay TLS")
                with self.sl: self.inb.write(x)

    def _flush(self):
        with self.wl:
            with self.sl: out = self.outb.read()
            if out: self.raw.sendall(out)

    def sendall(self, data):
        mv = memoryview(data)
        with self.wl:
            with self.sl:
                while mv:
                    k = self.obj.write(mv); mv = mv[k:]
                out = self.outb.read()
            if out: self.raw.sendall(out)

    def recv(self, n):
        """Như socket.recv: dữ liệu đã giải mã (≤ n byte) · b"" = bên kia đóng thật · socket.timeout / OSError như socket thường."""
        while True:
            with self.sl:
                try: d = self.obj.read(n)
                except ssl.SSLWantReadError: d = None
                except (ssl.SSLZeroReturnError, ssl.SSLEOFError): d = b""
                pend = self.outb.pending
            if pend: self._flush()
            if d is not None: return d
            x = self.raw.recv(262144)
            with self.sl:
                if x: self.inb.write(x)
                else: self.inb.write_eof()

    def getpeercert(self, binary_form=False): return self.obj.getpeercert(binary_form)

    def settimeout(self, t): self.raw.settimeout(t)

    def shutdown(self, how): self.raw.shutdown(how)

    def close(self): self.raw.close()


class DirectConn:
    kind = "direct"

    def __init__(self, host, port, cert_hex, timeout):
        raw = socket.create_connection((host, port), timeout=timeout)
        try:
            raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE     # không dựa vào CA: kiểm ĐÚNG mã chứng chỉ web báo
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            raw.settimeout(8)
            s = Tls(raw, ctx, "cloudblue")                     # 22.11a: TLS an toàn nhiều luồng (xem Tls)
        except BaseException:
            raw.close(); raise
        der = s.getpeercert(binary_form=True) or b""
        if not cert_hex or hashlib.sha256(der).hexdigest().lower() != cert_hex.lower():
            s.close(); raise ssl.SSLError("chung chi may chu khong khop")
        self.s = s; self.wlock = threading.Lock(); self.desc = "%s:%s" % (host, port)

    def _rd(self, n):
        b = bytearray()
        while len(b) < n:
            x = self.s.recv(n - len(b))
            if not x: raise EOFError("mat ket noi")
            b += x
        return bytes(b)

    def recv(self):
        n = struct.unpack(">I", self._rd(4))[0]
        if n < 1 or n > 2 * 1024 * 1024: raise EOFError("khung hong")
        b = self._rd(n)
        return b[0], b[1:]

    def send(self, t, payload=b""):
        with self.wlock: self.s.sendall(struct.pack(">IB", 1 + len(payload), t) + payload)

    def settimeout(self, t): self.s.settimeout(t)

    def close(self):
        try: self.s.shutdown(socket.SHUT_RDWR)                 # luồng khác đang chờ nhận trên kết nối này thoát ngay, bên kia thấy đóng liền
        except Exception: pass
        try: self.s.close()
        except Exception: pass


class WSConn:
    kind = "ws"

    def __init__(self, url, timeout, cafile=None, plain=False):
        u = urllib.parse.urlparse(url)
        if not u.hostname or u.scheme != ("ws" if plain else "wss"): raise ValueError("chi nhan wss://")      # plain: CHỈ bộ thử dùng (nối cổng nội bộ không TLS)
        host, port = u.hostname, u.port or (80 if plain else 443)
        raw = socket.create_connection((host, port), timeout=timeout)
        try:
            raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if plain: s = raw
            else:
                ctx = ssl.create_default_context()             # đường vòng: kiểm chứng chỉ thật của tên miền
                if cafile and os.path.isfile(cafile):
                    try: ctx.load_verify_locations(cafile)
                    except Exception: pass
                s = Tls(raw, ctx, host)                        # 22.11a: TLS an toàn nhiều luồng (xem Tls) — vẫn kiểm chứng chỉ + tên miền
            key = base64.b64encode(os.urandom(16)).decode()
            path = (u.path or "/") + ("?" + u.query if u.query else "")
            s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                       "Sec-WebSocket-Version: 13\r\nUser-Agent: CloudBluePC-remote/%s\r\n\r\n" % (path, host, key, REMOTE_VER)).encode())
            head = b""
            while b"\r\n\r\n" not in head:
                x = s.recv(4096)
                if not x: raise EOFError("WebSocket bi tu choi")
                head += x
                if len(head) > 65536: raise EOFError("WebSocket tra loi la")
        except Exception:
            raw.close(); raise
        hdr, _, rest = head.partition(b"\r\n\r\n")
        lines = hdr.decode("latin-1").split("\r\n")
        acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        if " 101 " not in lines[0] + " " or not any(l.lower().startswith("sec-websocket-accept:") and l.split(":", 1)[1].strip() == acc for l in lines[1:]):
            s.close(); raise EOFError("WebSocket: " + lines[0][:80])
        self.s = s; self.buf = bytearray(rest); self.wlock = threading.Lock(); self.desc = host

    def _rd(self, n):
        while len(self.buf) < n:
            x = self.s.recv(max(65536, n - len(self.buf)))
            if not x: raise EOFError("mat ket noi")
            self.buf += x
        b = bytes(self.buf[:n]); del self.buf[:n]
        return b

    def _frame(self):
        b0, b1 = self._rd(2)
        n = b1 & 0x7F
        if n == 126: n = struct.unpack(">H", self._rd(2))[0]
        elif n == 127: n = struct.unpack(">Q", self._rd(8))[0]
        if n > 2 * 1024 * 1024: raise EOFError("khung hong")
        mk = self._rd(4) if b1 & 0x80 else None
        d = self._rd(n) if n else b""
        if mk: d = bytes(c ^ mk[i % 4] for i, c in enumerate(d))
        return b0 & 0x80, b0 & 0x0F, d

    def recv(self):
        frag = None; fop = 0
        while True:
            fin, op, d = self._frame()
            if op == 8: raise EOFError("may chu dong ket noi")
            if op == 9: self._write(10, d); continue
            if op == 10: continue
            if op in (1, 2):
                if fin:
                    if op == 2 and d: return d[0], d[1:]
                    continue
                frag, fop = bytearray(d), op; continue
            if op == 0 and frag is not None:
                frag += d
                if fin:
                    if fop == 2 and frag: return frag[0], bytes(frag[1:])
                    frag = None

    def _write(self, op, data):
        n = len(data); mk = os.urandom(4)
        hdr = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n)) if n < 65536 else (bytes([0x80 | 127]) + struct.pack(">Q", n)))
        if n: data = (int.from_bytes(data, "little") ^ int.from_bytes((mk * (n // 4 + 1))[:n], "little")).to_bytes(n, "little")
        with self.wlock: self.s.sendall(hdr + mk + data)

    def send(self, t, payload=b""): self._write(2, bytes([t]) + payload)

    def settimeout(self, t): self.s.settimeout(t)

    def close(self):
        try: self.s.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        try: self.s.close()
        except Exception: pass


def connect(stream, cafile=None, log=None):
    """Nối tới máy chủ phát hình theo thứ tự: thẳng trong mạng nhà → thẳng qua IP ngoài → đường vòng Cloudflare."""
    paths, cert = parse_paths(stream)
    if not paths: raise ConnectionError("may chu chua bao duong noi")
    errs = []
    for kind, a, port, to in paths:
        try:
            return DirectConn(a, port, cert, to) if kind == "direct" else WSConn(a, to, cafile)
        except Exception as e:
            errs.append("%s %s: %s" % (kind, a, str(e)[:60]))
    raise ConnectionError("; ".join(errs)[-300:])


# ====================================================================================== BỘ QUAY + NÉN (ffmpeg)
class Encoder:
    """1 tiến trình ffmpeg: quay màn hình + nén, đẩy RTP về cổng nội bộ; luồng đọc ghép thành khung rồi gọi on_au(dữ liệu | None, khoá, cfg, pts_us)."""
    def __init__(self, ff, cap, enc, sw, sh, w, h, fps, kbps, on_au, log=None):
        self.ff, self.cap, self.enc, self.sw, self.sh, self.w, self.h, self.fps, self.kbps = ff, cap, enc, sw, sh, w, h, fps, kbps
        self.on_au, self.log = on_au, log or (lambda m: None)
        self.proc = None; self.sock = None; self.alive = False; self.stopped = False; self.frames = 0; self.t0 = 0.0; self.t_frame = 0.0; self.err = ""

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError: pass
        self.sock.bind(("127.0.0.1", 0)); self.sock.settimeout(0.5)
        cmd = ff_cmd(self.ff, self.cap, self.enc, self.sw, self.sh, self.w, self.h, self.fps, self.kbps, self.sock.getsockname()[1])
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     creationflags=(0x08000000 | 0x00008000) if WIN else 0)        # không cửa sổ · ưu tiên trên mức thường (hình không khựng khi máy bận)
        self.alive = True; self.t0 = self.t_frame = time.time()
        threading.Thread(target=self._rtp, daemon=True).start()
        threading.Thread(target=self._errlog, daemon=True).start()

    def _errlog(self):
        lines = []
        try:
            for ln in iter(self.proc.stderr.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s: lines.append(s); del lines[:-6]
        except Exception: pass
        self.err = " | ".join(lines[-3:])[:300]
        if lines and not self.stopped: self.log("ffmpeg (%s, %s): %s" % (self.cap, self.enc, self.err))

    def _rtp(self):
        asm = RtpAssembler(); sock = self.sock
        while self.alive:
            try: pkt = sock.recv(65536)
            except socket.timeout:
                if self.proc.poll() is not None: break
                continue
            except OSError: break
            r = asm.feed(pkt)
            if r is None: continue
            if r[0] is not None: self.frames += 1; self.t_frame = time.time()
            try: self.on_au(r[0], r[1], r[2], int(time.monotonic() * 1e6))
            except Exception: pass

    def exited(self): return self.proc is not None and self.proc.poll() is not None

    def stop(self):
        self.stopped = True; self.alive = False
        try:
            if self.proc and self.proc.poll() is None: self.proc.kill()
        except Exception: pass
        try:
            if self.sock: self.sock.close()
        except Exception: pass


def probe(ff, log=None, timeout=20, want=ENCODERS, test=False):
    """Máy này quay + nén được kiểu nào → {"enc": [bộ nén dùng được, tốt nhất trước], "cap": "dda" | "gdi"}. Chạy thử ffmpeg vài khung, không đụng gì khác."""
    log = log or (lambda m: None); ok = []
    flags = 0x08000000 if WIN else 0
    for enc in want:
        try:
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30", "-frames:v", "8",
                                "-vf", "format=" + ("yuv420p" if enc == "x264" else "nv12")] + enc_args(enc, 30, 1000) + ["-f", "null", "-"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, creationflags=flags)
            if r.returncode == 0: ok.append(enc)
            else: log("bo nen %s: khong dung duoc (%s)" % (enc, (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1][:140] if r.stderr else r.returncode))
        except Exception as e:
            log("bo nen %s: thu loi %s" % (enc, str(e)[:100]))
    cap = "test" if test else "gdi"
    if WIN and not test:
        try:
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-filter_complex", "ddagrab=output_idx=0:framerate=5,hwdownload,format=bgra",
                                "-frames:v", "2", "-f", "null", "-"], stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, creationflags=flags)
            if r.returncode == 0: cap = "dda"
            else: log("quay kieu Desktop Duplication: khong dung duoc (%s) -> quay kieu GDI" % ((r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1][:140] if r.stderr else r.returncode))
        except Exception as e:
            log("quay kieu Desktop Duplication: thu loi %s -> quay kieu GDI" % str(e)[:100])
    return {"enc": ok, "cap": cap, "t": time.time()}


# ====================================================================================== 1 PHIÊN CÓ NGƯỜI XEM
class Session:
    """Từ R_START tới R_STOP: quay + nén + gửi hình, nhận chuột / phím. Mọi thứ đụng Windows đi qua `io` (bộ thử dùng bản giả)."""
    def __init__(self, remote, conn, req):
        self.r, self.conn, self.req = remote, conn, req
        self.log = remote.log; self.io = remote.io
        self.sid = clamp(req.get("sid"), 0, 2 ** 31 - 1)
        self.q = req.get("q") if req.get("q") in QS else "auto"
        self.fps_req = clamp(req.get("fps"), 0, 240); self.maxh_req = clamp(req.get("maxh"), 0, 16384); self.kbps_req = clamp(req.get("kbps"), 0, MAX_KBPS)
        self.fps_fix = clamp(req.get("fpsx"), 0, 120)                      # 21.11g: khung/giây khách tự chọn
        self.link = str(req.get("link") or "direct"); self.net = str(req.get("net") or "")[:2]
        self.lag_lim = LAG_DROP_MS.get(self.link, 350) + (150 if self.net == "c" else 0)
        cap = self.kbps_req or PRESETS.get(self.q, PRESETS["bal"])[2]
        self.rate = Rate(cap, kbps_start(cap, self.q, self.net, self.link, clamp(req.get("dl"), 0, 10 ** 6)))
        self.enc = None; self.lock = threading.RLock(); self.closed = False
        self.sq = collections.deque(); self.sev = threading.Event(); self.wait_key = True; self.gen = 0
        self.sent = 0; self.bytes = 0; self.drop = 0; self.t_restart = 0.0; self.t_key = 0.0; self.fails = 0; self.restart_why = None
        self.vw = self.vh = 0; self.fps = 30; self.sw = self.sh = 0
        self.keys = Keys(self.io); self.touch = Touch(self.io); self.ptr = Pointer(self.io)
        self.iq = queue.Queue(maxsize=4000); self.clip_last = None; self.t0 = time.time()
        self.ime = None; self.ime_v = None; self.ime_dirty = False; self.last_st = None       # 22.11b: ô nhập chữ đang được chọn → app tự bật bàn phím

    def _on_ime(self, v):
        self.ime_v = (1 if v[0] else 0, 1 if v[1] else 0); self.ime_dirty = True

    # ---------- hình ----------
    def _pick(self):
        """(cách quay, bộ nén) tốt nhất đang dùng được."""
        caps = self.r.caps; now = time.time()
        enc = next((e for e in caps.get("enc") or [] if self.r.bad.get(e, 0) < now), None) or "x264"
        cap = caps.get("cap") or "gdi"
        if cap == "dda" and self.r.bad.get("dda", 0) > now: cap = "gdi"
        return cap, enc

    def start_video(self):
        """Bật (lại) bộ quay + nén theo chất lượng hiện tại rồi báo thông số (P_INFO). Khung kế tiếp gửi đi là khung khoá."""
        with self.lock:
            if self.closed: return
            old, self.enc = self.enc, None
            if old: old.stop()
            self.gen += 1; gen = self.gen; self.sq.clear(); self.wait_key = True
            cap, enc = self._pick()
            self.sw, self.sh = self.io.screen()
            w, h, fps, kbps, _ = plan(self.q, self.fps_req, self.maxh_req, self.kbps_req, self.rate.cur, self.sw, self.sh, cpu=(enc == "x264"), fps_fix=self.fps_fix)
            self.vw, self.vh, self.fps = w, h, fps
            e = Encoder(self.r.ff, cap, enc, self.sw, self.sh, w, h, fps, kbps, lambda d, k, c, pts, g=gen: self._on_au(g, d, k, c, pts), self.log)
            e.start(); self.enc = e; self.t_restart = time.time()
            self.conn.send(P_INFO, json.dumps({"sid": self.sid, "w": w, "h": h, "fps": fps, "kbps": kbps, "enc": enc, "cap": cap, "q": self.q}).encode())

    def _on_au(self, gen, data, key, cfg, pts):
        if gen != self.gen or self.closed: return
        self.sq.append((gen, data, key, cfg, pts, time.time())); self.sev.set()

    def _sender(self):
        """Gửi khung theo thứ tự; đường lên nghẽn (hàng chờ dồn) hoặc người xem chậm (ACK trễ) → bỏ tới khung khoá kế, không để trễ dồn."""
        while not self.closed:
            if not self.sq:
                self.sev.wait(0.5); self.sev.clear(); continue
            try: gen, data, key, cfg, pts, tq = self.sq.popleft()
            except IndexError: continue
            if gen != self.gen: continue
            now = time.time()
            if data is None: self.wait_key = True; continue
            if now - tq > 0.4 or len(self.sq) > max(8, self.fps // 2):            # đường lên của máy không kịp (hàng chờ > 0,4 giây)
                self.drop += 1 + len(self.sq); self.sq.clear(); self.wait_key = True
                self._congested(now, hard=True); continue
            if self.rate.behind_ms(now) > (1500 if now - self.t_key < 1.0 else self.lag_lim):
                if not self.wait_key: self._congested(now)
                self.drop += 1; self.wait_key = True; continue
            if self.wait_key and not key: self.drop += 1; continue
            self.wait_key = False
            try: self.conn.send(S_VIDEO, struct.pack(">BQ", (1 if key else 0) | (2 if cfg else 0), pts) + data)
            except Exception: self.closed = True; return
            self.sent += 1; self.bytes += len(data); self.rate.sent(pts, len(data), now)
            if key: self.t_key = now

    def _congested(self, now, hard=False):
        new = self.rate.congested(now, hard)
        if new:
            self.log("nguoi xem nhan cham -> ha bitrate con %d kbps" % new); self.restart_why = "rate"

    # ---------- lệnh từ người xem ----------
    def handle(self, t, p):
        """Gọi từ luồng nhận mạng. Việc đụng chuột / phím xếp vào hàng cho luồng nhập liệu; còn lại làm ngay."""
        if t == C_ACK:
            if len(p) >= 8: self.rate.ack(struct.unpack(">Q", p[:8])[0], time.time(), int(time.monotonic() * 1e6))
        elif t == C_KEYFRAME:
            if time.time() - self.t_key > 1.5 and time.time() - self.t_restart > 1.5: self.restart_why = self.restart_why or "key"
        elif t == C_QUALITY:
            try: j = json.loads(p.decode("utf-8") or "{}")
            except Exception: return
            if not isinstance(j, dict): return
            if j.get("q") in QS: self.q = j["q"]
            if "fps" in j: self.fps_req = clamp(j.get("fps"), 0, 240)
            if "maxh" in j: self.maxh_req = clamp(j.get("maxh"), 0, 16384)
            if "fpsx" in j: self.fps_fix = clamp(j.get("fpsx"), 0, 120)
            self.kbps_req = clamp(j.get("kbps"), 0, MAX_KBPS)
            cap = self.kbps_req or PRESETS.get(self.q, PRESETS["bal"])[2]
            self.rate = Rate(cap, kbps_start(cap, self.q, self.net, self.link)); self.restart_why = "quality"
        elif t == R_SLOW:
            self._congested(time.time(), hard=True)
        elif t in (C_TOUCH, C_MOUSE, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_CLIP):
            try: self.iq.put_nowait((t, p))
            except queue.Full: pass

    def _apply(self, t, p):
        if t == C_TOUCH and len(p) >= 6:
            a, ptr, x, y = struct.unpack(">BBHH", p[:6])
            if a <= 3 and ptr <= 9: self.touch.touch(a, ptr, x, y, time.time())
        elif t == C_MOUSE and len(p) >= 6:
            a, b, x, y = struct.unpack(">BBHH", p[:6])
            if a <= 2: self.ptr.mouse(a, b, x, y)
        elif t == C_KEY and len(p) >= 9:
            a, code, meta = struct.unpack(">BII", p[:9]); self.keys.key(1 if a else 0, code, meta)
        elif t == C_TEXT:
            s = clean_text(p.decode("utf-8", "replace"))
            if s: self.io.text(s)
        elif t == C_SCROLL and len(p) >= 8:
            x, y, h, v = struct.unpack(">HHhh", p[:8]); self.io.move(x, y)
            if v: self.io.wheel(max(-2400, min(2400, v)), False)
            if h: self.io.wheel(max(-2400, min(2400, h)), True)
        elif t == C_CMD:
            j = json.loads(p.decode("utf-8") or "{}")
            combo = CMDS.get(str(j.get("cmd") or "")) if isinstance(j, dict) else None
            if combo: self.keys.tap(*combo)
        elif t == C_CLIP and len(p) >= 1:
            s = p[1:1 + CLIP_MAX].decode("utf-8", "replace")
            self.clip_last = s; self.io.clip_set(s)
            if p[0]: self._paste(p[0])                                   # dán ngay (1 = Ctrl+V / nút Dán · 2 = khách bấm Ctrl+Shift+V)

    def _paste(self, mode):
        """23.11b: dán ngay sau khi đặt bộ nhớ copy. Phím bổ trợ khách ĐANG GIỮ (Ctrl của Ctrl+V…) nhả ra trước, dán, rồi nhấn lại → tổ hợp dán
           sạch (không thành Ctrl+Shift+Insert / Ctrl+Ctrl+V lẫn lộn) và máy vẫn khớp phím khách đang giữ (bấm tiếp Ctrl+C vẫn là copy).
           Máy Linux (io.paste): cbcap tự chọn phím theo cửa sổ (Konsole Ctrl+Shift+V…). Windows: Ctrl+V (mode 2: Ctrl+Shift+V)."""
        held = [vk for vk in sorted(self.keys.down | self.keys.auto_held) if vk in MOD_VKS]
        for vk in held: self.io.key(vk, False, vk in EXT_VKS)
        time.sleep(0.05)
        fn = getattr(self.io, "paste", None)
        if fn is not None: fn(mode)
        else: self.keys.tap(*((0xA2, 0xA0, 0x56) if mode == 2 else (0xA2, 0x56)))
        for vk in held: self.io.key(vk, True, vk in EXT_VKS)

    def _input(self):
        while not self.closed:
            try: t, p = self.iq.get(timeout=0.05)
            except queue.Empty:
                try: self.touch.tick(time.time())
                except Exception: pass
                continue
            try: self._apply(t, p); self.touch.tick(time.time())
            except (ValueError, struct.error, UnicodeError, AttributeError, TypeError): pass       # gói hỏng → bỏ qua
            except Exception as e: self.log("loi lam lenh nguoi xem (0x%02x): %r" % (t, e))

    # ---------- canh phiên ----------
    def _monitor(self):
        t_stat = time.time(); s0 = b0 = 0; t_clip = t_size = 0.0
        while not self.closed:
            time.sleep(0.25); now = time.time(); e = self.enc
            try:
                if e is not None and (e.exited() or (now - e.t_frame > 6 and now - self.t_restart > 6)):
                    first = e.frames == 0
                    self.log("bo quay / nen dung%s (%s, %s) %s" % (" khi chua ra khung nao" if first else "", e.cap, e.enc, e.err))
                    if first:                                   # chưa ra khung nào: cách quay / bộ nén này không chạy được trên máy → đổi sang cách kế
                        self.fails += 1
                        if e.cap == "dda": self.r.bad["dda"] = now + BAD_S
                        elif e.enc != "x264": self.r.bad[e.enc] = now + BAD_S
                        if self.fails >= 4:
                            self.conn.send(S_ERROR, json.dumps({"code": "OFFLINE", "msg": "Máy PC chưa quay được màn hình (chưa ai đăng nhập Windows hoặc màn hình đang khoá) — thử lại sau ít phút."},
                                                               ensure_ascii=False).encode())
                            self.r.caps_t = 0; self.close(); return
                    self.start_video(); continue
                if e is not None and e.frames > 30: self.fails = 0
                if now - t_size > 1.0:
                    t_size = now
                    if tuple(self.io.screen()) != (self.sw, self.sh) and now - self.t_restart > 1.0:
                        self.log("man hinh doi do phan giai -> phat lai"); self.restart_why = "size"
                if self.restart_why is None:
                    up = self.rate.raise_(now)
                    if up: self.log("duong truyen on -> tang len %d kbps" % up); self.restart_why = "rate"
                if self.restart_why and now - self.t_restart > 1.0:
                    self.restart_why = None; self.start_video()
                if now - t_clip > 0.5:
                    t_clip = now
                    c = self.io.clip_poll()
                    if c is not None and c != self.clip_last and len(c) <= CLIP_MAX:
                        self.clip_last = c; self.conn.send(S_CLIP, c.encode("utf-8"))
                if now - t_stat >= 2:
                    dt = now - t_stat
                    st = {"fps": round((self.sent - s0) / dt, 1), "kbps": int((self.bytes - b0) * 8 / dt / 1000), "drop": self.drop, "enc": e.enc if e else "",
                          "q": self.q, "w": self.vw, "h": self.vh, "lag": self.rate.lag_ms, "cap": e.cap if e else ""}
                    if self.q == "auto" and self.rate.cur < self.rate.cap * 0.6 and now - self.rate.last_cong < 900: st["weak"] = 1; st["tgt"] = int(self.rate.cur)
                    self.last_st = dict(st); self.ime_dirty = False
                    self.conn.send(S_STATS, json.dumps(self._ime_fields(st)).encode())
                    t_stat = now; s0, b0 = self.sent, self.bytes
                elif self.ime_dirty:                                  # 22.11b: ô nhập chữ vừa được chọn / bỏ chọn → báo NGAY (không chờ nhịp 2 giây)
                    self.ime_dirty = False
                    self.conn.send(S_STATS, json.dumps(self._ime_fields(dict(self.last_st or {}))).encode())
            except Exception as ex:
                if self.closed: return
                self.log("loi canh phien: %r" % (ex,))
                if isinstance(ex, (OSError, EOFError)): self.closed = True; return

    def _ime_fields(self, st):
        v = self.ime_v
        if v is not None:
            st["ime"] = v[0]
            if v[1]: st["pw"] = 1
        return st

    def start(self):
        self.io.awake(True)
        mk = getattr(self.io, "ime_watch", None)
        if mk is not None:
            try: self.ime = mk(self._on_ime, self.log)
            except Exception as e: self.log("ime: %r" % (e,))
        if self.req.get("admin") and not self.req.get("owner"): self.io.notify("CloudBlue: quan tri vien dang ho tro / dieu khien may nay tu xa.")
        self.th_in = threading.Thread(target=self._input, daemon=True); self.th_in.start()
        for fn in (self._sender, self._monitor): threading.Thread(target=fn, daemon=True).start()
        self.start_video()

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed = True
            e, self.enc = self.enc, None
        if e: e.stop()
        w, self.ime = self.ime, None
        if w is not None:
            try: w.stop()
            except Exception: pass
        self.sev.set()
        th = getattr(self, "th_in", None)
        if th is not None and th is not threading.current_thread(): th.join(0.5)        # luồng nhập liệu dừng hẳn rồi mới nhả (không nhả xong lại bị nhấn tiếp)
        for fn in (self.touch.reset, self.ptr.release_all, self.keys.release_all):      # nhả mọi nút / phím đang giữ
            try: fn()
            except Exception: pass
        self.io.awake(False)
        self.log("het nguoi xem: gui %d khung, bo %d, %d giay" % (self.sent, self.drop, int(time.time() - self.t0)))


# ====================================================================================== VÒNG CHÍNH
class ImeWatch:
    """22.11b · Khách bấm vào ô nhập chữ trên máy PC → app điện thoại tự bật bàn phím (như máy Android).
       Mỗi 0,3 giây xem chỗ đang được chọn trên màn hình Windows:
         1. cửa sổ đang dùng có con trỏ chữ nhấp nháy (GetGUIThreadInfo) — ô nhập kiểu Win32: Notepad, hộp Run, thanh địa chỉ Explorer…
         2. không có → UI Automation: phần tử đang được chọn là ô nhập (Edit) không chỉ đọc — Chrome / Edge / Firefox / app mới.
       Đổi thì gọi on_change((có_ô_nhập 0/1, ô_mật_khẩu 0/1)). Chạy trên luồng RIÊNG gắn vào màn hình Default; lỗi gì cũng chỉ thôi
       báo — không bao giờ làm hỏng phiên điều khiển. COM gọi thẳng qua bảng hàm ảo, chỉ 3 chỗ: Release (2),
       IUIAutomation::GetFocusedElement (8), IUIAutomationElement::GetCurrentPropertyValue (10)."""
    EDIT, COMBO, DOC = 50004, 50003, 50030                              # UIA_EditControlTypeId · ComboBox · Document
    P_TYPE, P_PW, P_RO, P_HASVAL = 30003, 30019, 30046, 30043           # ControlType · IsPassword · ValueIsReadOnly · IsValuePatternAvailable
    STEP = 0.3

    def __init__(self, on_change, log=None):
        self.cb, self.log = on_change, (log or (lambda m: None))
        self.ev = threading.Event(); self.last = None; self.uia = None; self.com = False; self.err_n = 0
        self.th = threading.Thread(target=self._run, name="ime", daemon=True); self.th.start()

    def stop(self): self.ev.set()

    def _run(self):
        try: self._setup()
        except Exception as e:
            self.log("ime: khong bat duoc theo doi o nhap chu (%r)" % (e,)); return
        try:
            while not self.ev.wait(self.STEP):
                try: v = self._poll()
                except Exception as e:
                    v = None; self.err_n += 1
                    if self.err_n in (1, 100): self.log("ime: loi doc o dang chon (%r)" % (e,))
                if v is not None and v != self.last:
                    self.last = v
                    try: self.cb(v)
                    except Exception: pass
        finally: self._teardown()

    def _setup(self):
        import ctypes, uuid
        from ctypes import wintypes as wt
        ct = self.ct = ctypes
        u = self.u = ctypes.WinDLL("user32", use_last_error=True)
        o = self.o = ctypes.WinDLL("ole32"); oa = self.oa = ctypes.WinDLL("oleaut32")
        u.OpenDesktopW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD]; u.OpenDesktopW.restype = wt.HANDLE
        u.SetThreadDesktop.argtypes = [wt.HANDLE]; u.SetThreadDesktop.restype = wt.BOOL
        u.GetForegroundWindow.argtypes = []; u.GetForegroundWindow.restype = wt.HWND
        u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.c_void_p]; u.GetWindowThreadProcessId.restype = wt.DWORD

        class GTI(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND),
                        ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]

        class GUID(ctypes.Structure): _fields_ = [("a", wt.DWORD), ("b", wt.WORD), ("c", wt.WORD), ("d", ctypes.c_ubyte * 8)]

        class VARIANT(ctypes.Structure):
            _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort), ("v", ctypes.c_ulonglong), ("v2", ctypes.c_ulonglong)]
        self.GTI, self.VARIANT = GTI, VARIANT
        u.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GTI)]; u.GetGUIThreadInfo.restype = wt.BOOL
        o.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]; o.CoInitializeEx.restype = ctypes.c_long
        o.CoUninitialize.argtypes = []; o.CoUninitialize.restype = None
        o.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        o.CoCreateInstance.restype = ctypes.c_long
        oa.VariantClear.argtypes = [ctypes.POINTER(VARIANT)]; oa.VariantClear.restype = ctypes.c_long
        self.F_REL = ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)
        self.F_FOCUS = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        self.F_PROP = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(VARIANT))
        d = u.OpenDesktopW("Default", 0, False, 0x10000000)          # GENERIC_ALL — cửa sổ của khách nằm ở màn hình Default
        if d: u.SetThreadDesktop(d)
        self.com = o.CoInitializeEx(None, 0) in (0, 1)                 # COINIT_MULTITHREADED

        def guid(s):
            x = uuid.UUID(s); g = GUID(); g.a, g.b, g.c = x.fields[0], x.fields[1], x.fields[2]
            g.d = (ctypes.c_ubyte * 8)(*x.bytes[8:]); return g
        clsid, iid = guid("ff48dba4-60ef-4201-aa87-54103eef594e"), guid("30cbe57d-d9d0-452a-ab13-7ac5ac4825ee")    # CUIAutomation · IUIAutomation
        p = ctypes.c_void_p()
        hr = o.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(p))     # CLSCTX_INPROC_SERVER
        if hr == 0 and p.value: self.uia = p
        else: self.log("ime: khong tao duoc UI Automation (0x%08x) — chi nhan o nhap kieu Win32" % (hr & 0xFFFFFFFF))

    def _vfn(self, obj, idx, proto):
        vt = self.ct.cast(obj, self.ct.POINTER(self.ct.c_void_p))[0]           # *(void**)obj = bảng hàm ảo
        return proto(self.ct.cast(vt, self.ct.POINTER(self.ct.c_void_p))[idx])

    def _prop(self, el, pid):
        """Thuộc tính UIA của phần tử: số (VT_I4) / đúng-sai (VT_BOOL) · None = không có / lỗi."""
        v = self.VARIANT()
        try:
            if self._vfn(el, 10, self.F_PROP)(el, pid, self.ct.byref(v)) != 0: return None
            if v.vt == 3: return self.ct.c_int32(v.v & 0xFFFFFFFF).value
            if v.vt == 11: return bool(v.v & 0xFFFF)
            return None
        finally: self.oa.VariantClear(self.ct.byref(v))

    def _poll(self):
        if self._caret(): return (1, 0)
        return self._uia_focus()

    def _caret(self):
        """Cửa sổ đang dùng có con trỏ chữ (ô nhập kiểu Win32)?"""
        u = self.u
        fg = u.GetForegroundWindow()
        if not fg: return False
        gi = self.GTI(); gi.cbSize = self.ct.sizeof(self.GTI)
        tid = u.GetWindowThreadProcessId(fg, None)
        return bool(tid and u.GetGUIThreadInfo(tid, self.ct.byref(gi)) and gi.hwndCaret)

    def _uia_focus(self):
        """UI Automation: phần tử đang được chọn có phải ô nhập chữ (không chỉ đọc) → (0/1, mật khẩu 0/1)."""
        if not self.uia: return (0, 0)
        el = self.ct.c_void_p()
        if self._vfn(self.uia, 8, self.F_FOCUS)(self.uia, self.ct.byref(el)) != 0 or not el.value: return (0, 0)
        try:
            t = self._prop(el, self.P_TYPE)
            if t == self.EDIT:
                if self._prop(el, self.P_RO) is True: return (0, 0)
                return (1, 1 if self._prop(el, self.P_PW) is True else 0)
            if t in (self.COMBO, self.DOC) and self._prop(el, self.P_HASVAL) is True and self._prop(el, self.P_RO) is False: return (1, 0)
            return (0, 0)
        finally: self._vfn(el, 2, self.F_REL)(el)

    def _teardown(self):
        try:
            if self.uia: self._vfn(self.uia, 2, self.F_REL)(self.uia); self.uia = None
        except Exception: pass
        try:
            if self.com: self.o.CoUninitialize()
        except Exception: pass


class NullIO:
    """Nhập liệu giả (máy không phải Windows / bộ thử): ghi lại lệnh, không làm gì thật."""
    def __init__(self, w=1280, h=720): self.w, self.h = w, h; self.ev = []; self.clip = None
    def screen(self): return self.w, self.h
    def move(self, x, y): self.ev.append(("move", x, y))
    def button(self, b, down): self.ev.append(("btn", b, down))
    def wheel(self, v, horiz): self.ev.append(("wheel", v, horiz))
    def key(self, vk, down, ext=False): self.ev.append(("key", vk, down, ext))
    def text(self, s): self.ev.append(("text", s))
    def clip_set(self, s): self.ev.append(("clip", s)); self.clip = s
    def clip_poll(self): return None
    def awake(self, on): self.ev.append(("awake", on))
    def notify(self, text): self.ev.append(("notify", text))


class Remote:
    """Giữ kết nối tới máy chủ phát hình; có người xem thì mở Session."""
    WHERE_S = 600                         # đang rảnh: 10 phút hỏi lại web 1 lần (admin tắt tính năng / đổi máy chủ)

    def __init__(self, ident_fn, rpc, io, ff_fn, log=None, cafile=None, caps=None):
        self.ident_fn, self.rpc, self.io, self.ff_fn, self.cafile = ident_fn, rpc, io, ff_fn, cafile
        self.log = log or (lambda m: None)
        self.caps = caps or {}; self.caps_t = time.time() if caps else 0; self.bad = {}; self.ff = None
        self.sess = None; self.conn = None; self.stop = False; self.node = None; self.t_where = 0.0; self.fails = 0; self.state = "khoi dong"
        self.sleep = time.sleep; self.prep_lock = threading.Lock()

    # ---------- chuẩn bị bộ quay ----------
    def prepare(self):
        """Tải ffmpeg (lần đầu) + dò máy này quay / nén được kiểu nào. Chạy ở luồng nền (có thể mất 1–2 phút); gọi lại nhiều lần không sao."""
        with self.prep_lock:
            try:
                if not self.ff: self.ff = self.ff_fn()
                if not self.ff: return False
                if not self.caps.get("enc") or time.time() - self.caps_t > 6 * 3600:
                    self.caps = probe(self.ff, self.log, test=(self.caps.get("cap") == "test")); self.caps_t = time.time()
                    self.log("may nay: nen bang %s; quay man hinh kieu %s" % (", ".join(self.caps["enc"]) or "KHONG CO BO NEN NAO", self.caps["cap"]))
                return bool(self.caps.get("enc"))
            except Exception as e:
                self.log("chuan bi bo quay loi: %r" % (e,)); return False

    def prepare_bg(self):
        if self.prep_lock.locked(): return
        if self.ff and self.caps.get("enc") and time.time() - self.caps_t <= 6 * 3600: return
        threading.Thread(target=self.prepare, daemon=True).start()

    # ---------- hỏi web: nối tới máy chủ nào ----------
    def where(self):
        """→ (stream, số giây nghỉ). stream = None: chưa nối (tính năng tắt / chưa có máy chủ / lỗi mạng) → nghỉ rồi hỏi lại."""
        idn = self.ident_fn()
        if not idn: self.state = "may chua dang ky"; return None, 60
        r = self.rpc("pc_relay_where", {"p_id": idn["id"], "p_token": idn["token"]})
        self.t_where = time.time()
        if not isinstance(r, dict): self.state = "chua goi duoc web"; return None, 60
        if not r.get("ok"):
            self.state = "web tu choi: %s" % r.get("err")
            return None, (600 if r.get("err") == "BAD_TOKEN" else 300)
        if not r.get("on"): self.state = "dieu khien tu xa dang TAT (admin chua bat / may chua duyet)"; return None, 300
        if not r.get("node") or not isinstance(r.get("stream"), dict): self.state = "chua co may chu phat hinh nao nhan"; return None, 90
        self.node = str(r["node"])[:60]
        return r["stream"], 0

    # ---------- 1 lần nối ----------
    def serve(self, conn):
        alive = [True]
        try:
            idn = self.ident_fn()
            if not idn: raise ConnectionError("may chua dang ky")
            sw, sh = self.io.screen()
            conn.settimeout(15)
            conn.send(P_HELLO, json.dumps({"v": 1, "pc": idn["id"], "token": idn["token"], "ver": REMOTE_VER, "w": sw, "h": sh,
                                           "enc": (self.caps.get("enc") or [""])[0], "cap": self.caps.get("cap") or ""}).encode())
            t, p = conn.recv()
            if t == S_ERROR:
                try: j = json.loads(p.decode("utf-8"))
                except Exception: j = {}
                raise Refused(str(j.get("code") or "BUSY"), str(j.get("msg") or ""))
            if t != R_OK: raise ConnectionError("may chu tra loi la")
            try: ok = json.loads(p.decode("utf-8"))
            except Exception: ok = {}
            ping_s = clamp(ok.get("ping_s") if isinstance(ok, dict) else 5, 2, 20, 5)
            self.fails = 0; self.state = "da noi may chu %s (%s) - cho nguoi xem" % (self.node, conn.kind)
            self.log("da noi may chu phat hinh %s qua duong %s (%s)" % (self.node, conn.kind, conn.desc))
            conn.settimeout(ping_s * 4)                       # máy chủ trả lời mỗi PING → quá 4 nhịp không nhận gì = đường truyền chết
            self.conn = conn

            def pinger():
                while alive[0] and not self.stop:
                    try: conn.send(C_PING, struct.pack(">Q", int(time.time() * 1000)))
                    except Exception: return
                    t0 = time.time()
                    while alive[0] and time.time() - t0 < ping_s: time.sleep(0.25)

            def keeper():
                """Đang rảnh: 10 phút hỏi lại web 1 lần — admin tắt tính năng / giao máy cho máy chủ khác → ngắt để nối lại cho đúng."""
                while alive[0] and not self.stop:
                    time.sleep(1.0)
                    if self.sess is not None or time.time() - self.t_where < self.WHERE_S: continue
                    old = self.node
                    try: st, _ = self.where()
                    except Exception: continue
                    if alive[0] and (st is None or self.node != old) and self.sess is None:
                        self.log("web bao doi (%s) -> ngat ket noi hien tai" % self.state); conn.close(); return
            for fn in (pinger, keeper): threading.Thread(target=fn, daemon=True).start()
            while not self.stop:
                t, p = conn.recv()
                if t == S_PONG: continue
                if t == R_START: self._start(conn, p)
                elif t == R_STOP: self._stop()
                elif t == S_ERROR: raise Refused("BUSY", "may chu dong ket noi")
                elif self.sess is not None: self.sess.handle(t, p)
        finally:
            alive[0] = False; self.conn = None
            self._stop()
            conn.close()

    def _start(self, conn, p):
        try: req = json.loads(p.decode("utf-8"))
        except Exception: return
        if not isinstance(req, dict): return
        self._stop()
        if not (self.ff and self.caps.get("enc")):                # chưa có ffmpeg / chưa dò xong → báo người xem thử lại, chuẩn bị tiếp ở luồng nền
            self.prepare_bg()
            conn.send(S_ERROR, json.dumps({"code": "OFFLINE", "msg": "Máy PC đang chuẩn bị bộ quay màn hình (lần đầu mất 1–2 phút) — thử lại sau ít phút."}, ensure_ascii=False).encode())
            return
        s = Session(self, conn, req); self.sess = s
        self.state = "dang co nguoi xem"
        self.log("co nguoi xem (%s, duong %s) -> bat bo quay" % ("admin ho tro" if req.get("admin") and not req.get("owner") else "khach", req.get("link")))
        try: s.start()
        except Exception as e:
            self.log("khong bat duoc bo quay: %r" % (e,)); self._stop()
            msg = str(getattr(e, "viewer_msg", "") or "")[:280] or "Máy PC chưa bật được bộ quay màn hình — thử lại sau ít phút."   # 22.11g: máy Linux báo lý do
            try: conn.send(S_ERROR, json.dumps({"code": "OFFLINE", "msg": msg}, ensure_ascii=False).encode())
            except Exception: pass

    def _stop(self):
        s, self.sess = self.sess, None
        if s is not None:
            s.close()
            if self.conn is not None: self.state = "da noi may chu %s - cho nguoi xem" % self.node

    def run(self):
        """Vòng chính: hỏi web → nối → phục vụ → đứt thì nối lại (chờ lâu dần, tối đa 60 giây; bị từ chối thì chờ lâu hơn)."""
        while not self.stop:
            nap = 5
            try:
                stream, nap = self.where()
                if stream is not None:
                    self.prepare_bg()                                              # tải ffmpeg + dò bộ nén sẵn trong lúc chờ người xem
                    self.serve(connect(stream, self.cafile, self.log))
                    nap = 2
            except Refused as e:
                self.state = "may chu tu choi: %s %s" % (e.code, e)
                nap = {"AUTH": 600, "OFF": 300}.get(e.code, 45)
                self.log("may chu phat hinh tu choi (%s) - thu lai sau %d giay" % (e.code, nap))
            except Exception as e:
                self.fails += 1; nap = min(60, 2 ** min(self.fails, 6))
                self.state = "chua noi duoc may chu: %s" % str(e)[:120]
                if self.fails in (1, 5) or self.fails % 30 == 0: self.log("chua noi duoc may chu phat hinh (%s) - lan %d" % (str(e)[:160], self.fails))
            if self.stop: break
            self.sleep(nap * (0.8 + random.random() * 0.4))


# ====================================================================================== WINDOWS
class WinIO:
    """Chuột / phím / bộ nhớ copy / cỡ màn hình thật của Windows (SendInput). Chạy bằng SYSTEM trong phiên màn hình → bấm được cả cửa sổ chạy quyền Admin."""
    def __init__(self, log=None):
        import ctypes
        from ctypes import wintypes as wt
        self.ct, self.wt, self.log = ctypes, wt, log or (lambda m: None)
        u = self.u = ctypes.WinDLL("user32", use_last_error=True); k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        try: ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)              # toạ độ + cỡ màn hình theo điểm ảnh thật
        except Exception:
            try: u.SetProcessDPIAware()
            except Exception: pass
        UP = ctypes.c_size_t

        class MI(ctypes.Structure): _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", UP)]
        class KI(ctypes.Structure): _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", UP)]
        class HI(ctypes.Structure): _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]
        class U(ctypes.Union): _fields_ = [("mi", MI), ("ki", KI), ("hi", HI)]
        class INPUT(ctypes.Structure): _fields_ = [("type", wt.DWORD), ("u", U)]
        self.MI, self.KI, self.INPUT = MI, KI, INPUT
        u.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]; u.SendInput.restype = wt.UINT
        u.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]; u.MapVirtualKeyW.restype = wt.UINT
        u.GetSystemMetrics.argtypes = [ctypes.c_int]; u.GetSystemMetrics.restype = ctypes.c_int
        u.OpenClipboard.argtypes = [wt.HWND]; u.OpenClipboard.restype = wt.BOOL
        u.CloseClipboard.argtypes = []; u.EmptyClipboard.argtypes = []
        u.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]; u.SetClipboardData.restype = wt.HANDLE
        u.GetClipboardData.argtypes = [wt.UINT]; u.GetClipboardData.restype = wt.HANDLE
        u.GetClipboardSequenceNumber.argtypes = []; u.GetClipboardSequenceNumber.restype = wt.DWORD
        u.IsClipboardFormatAvailable.argtypes = [wt.UINT]; u.IsClipboardFormatAvailable.restype = wt.BOOL
        u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HANDLE, wt.HANDLE, ctypes.c_void_p]
        u.CreateWindowExW.restype = wt.HWND
        u.DestroyWindow.argtypes = [wt.HWND]; u.DestroyWindow.restype = wt.BOOL
        u.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]; u.OpenInputDesktop.restype = wt.HANDLE
        u.SetThreadDesktop.argtypes = [wt.HANDLE]; u.SetThreadDesktop.restype = wt.BOOL
        u.CloseDesktop.argtypes = [wt.HANDLE]
        u.GetUserObjectInformationW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]; u.GetUserObjectInformationW.restype = wt.BOOL
        k.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]; k.GlobalAlloc.restype = wt.HANDLE
        k.GlobalLock.argtypes = [wt.HANDLE]; k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalUnlock.argtypes = [wt.HANDLE]; k.GlobalFree.argtypes = [wt.HANDLE]
        k.GlobalSize.argtypes = [wt.HANDLE]; k.GlobalSize.restype = ctypes.c_size_t
        k.SetThreadExecutionState.argtypes = [wt.DWORD]; k.SetThreadExecutionState.restype = wt.DWORD
        self.seq = u.GetClipboardSequenceNumber(); self.desk = None; self.desk_name = ""; self.t_desk = 0.0; self.t_note = 0.0

    def screen(self):
        w, h = self.u.GetSystemMetrics(0), self.u.GetSystemMetrics(1)
        return (w, h) if w >= 16 and h >= 16 else (1024, 768)

    # ---- chuột / phím ----
    def _desk(self):
        """Luồng nhập liệu đi theo màn hình ĐANG HIỆN (hộp hỏi quyền Admin / màn hình khoá nằm ở màn hình riêng của Windows)."""
        now = time.time()
        if now - self.t_desk < 0.5: return
        self.t_desk = now
        try:
            h = self.u.OpenInputDesktop(0, False, 0x10000000)                 # GENERIC_ALL
            if not h: return
            buf = self.ct.create_unicode_buffer(128); need = self.wt.DWORD(0)
            name = buf.value if self.u.GetUserObjectInformationW(h, 2, buf, 256, self.ct.byref(need)) else ""
            if name and name != self.desk_name and self.u.SetThreadDesktop(h):
                old, self.desk, self.desk_name = self.desk, h, name
                if old: self.u.CloseDesktop(old)
            else: self.u.CloseDesktop(h)
        except Exception: pass

    def _send(self, *items):
        self._desk()
        arr = (self.INPUT * len(items))(*items)
        self.u.SendInput(len(items), arr, self.ct.sizeof(self.INPUT))

    def _mi(self, flags, dx=0, dy=0, data=0):
        i = self.INPUT(); i.type = 0; i.u.mi = self.MI(dx, dy, data & 0xFFFFFFFF, flags, 0, 0); return i

    def _ki(self, vk, scan, flags):
        i = self.INPUT(); i.type = 1; i.u.ki = self.KI(vk, scan, flags, 0, 0); return i

    def move(self, x, y): self._send(self._mi(0x8001, clamp(x, 0, 65535), clamp(y, 0, 65535)))      # MOVE | ABSOLUTE (0..65535 = màn hình chính)

    def button(self, b, down):
        f, data = {0: ((0x0002, 0x0004), 0), 1: ((0x0008, 0x0010), 0), 2: ((0x0020, 0x0040), 0), 3: ((0x0080, 0x0100), 1), 4: ((0x0080, 0x0100), 2)}.get(b, (None, 0))
        if f: self._send(self._mi(f[0] if down else f[1], data=data))

    def wheel(self, v, horiz): self._send(self._mi(0x1000 if horiz else 0x0800, data=int(v)))

    def key(self, vk, down, ext=False):
        self._send(self._ki(vk, self.u.MapVirtualKeyW(vk, 0) & 0xFFFF, (0 if down else 0x0002) | (0x0001 if ext else 0)))

    def text(self, s):
        """Gõ chữ có dấu / ký tự bất kỳ (KEYEVENTF_UNICODE); xuống dòng = Enter, tab = Tab."""
        for ch in s:
            if ch == "\n": self.key(0x0D, True); self.key(0x0D, False); continue
            if ch == "\t": self.key(0x09, True); self.key(0x09, False); continue
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                u16 = b[i] | (b[i + 1] << 8)
                self._send(self._ki(0, u16, 0x0004), self._ki(0, u16, 0x0004 | 0x0002))

    # ---- bộ nhớ copy ----
    def _open_clip(self, hwnd=None):
        for _ in range(10):
            if self.u.OpenClipboard(hwnd): return True
            time.sleep(0.02)
        return False

    def clip_set(self, s):
        """Đặt chữ vào bộ nhớ copy. Windows cần 1 cửa sổ làm "chủ" lúc ghi → tạo cửa sổ ẩn tạm, ghi xong huỷ ngay (dữ liệu vẫn nằm lại)."""
        data = (s + "\0").encode("utf-16-le")
        try: hwnd = self.u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
        except Exception: hwnd = None
        try:
            if not self._open_clip(hwnd or None): return False
            try:
                self.u.EmptyClipboard()
                h = self.k.GlobalAlloc(0x0002, len(data))
                if not h: return False
                ptr = self.k.GlobalLock(h)
                if not ptr: self.k.GlobalFree(h); return False
                self.ct.memmove(ptr, data, len(data)); self.k.GlobalUnlock(h)
                if not self.u.SetClipboardData(13, h): self.k.GlobalFree(h); return False
                return True
            finally:
                self.u.CloseClipboard(); self.seq = self.u.GetClipboardSequenceNumber()
        finally:
            if hwnd: self.u.DestroyWindow(hwnd)

    def clip_get(self):
        if not self.u.IsClipboardFormatAvailable(13) or not self._open_clip(None): return None
        try:
            h = self.u.GetClipboardData(13)
            if not h: return None
            n = self.k.GlobalSize(h)
            if not n or n > 2 * CLIP_MAX + 2: return None
            ptr = self.k.GlobalLock(h)
            if not ptr: return None
            try: return self.ct.wstring_at(ptr, n // 2).split("\0", 1)[0]
            finally: self.k.GlobalUnlock(h)
        finally:
            self.u.CloseClipboard()

    def clip_poll(self):
        """Bộ nhớ copy của máy vừa đổi → chữ mới (để gửi cho người xem); không đổi → None."""
        q = self.u.GetClipboardSequenceNumber()
        if q == self.seq: return None
        self.seq = q
        try: return self.clip_get()
        except Exception: return None

    # ---- khác ----
    def ime_watch(self, on_change, log=None):
        """22.11b: theo dõi ô nhập chữ đang được chọn (cho app điện thoại tự bật bàn phím). Tắt: "ime": false trong cb.json."""
        return ImeWatch(on_change, log or self.log) if IME_ON else None

    def awake(self, on):
        try: self.k.SetThreadExecutionState((0x80000000 | 0x00000001 | 0x00000002) if on else 0x80000000)    # có người xem: không cho máy ngủ / tắt màn
        except Exception: pass

    def notify(self, text):
        if time.time() - self.t_note < 60: return
        self.t_note = time.time()
        try:
            exe = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "msg.exe")
            subprocess.Popen([exe, "*", "/TIME:20", str(text)[:250]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True, creationflags=0x08000000)
        except Exception: pass


def ensure_ffmpeg(base=BASE, log=None, fetch=None, url=FF_URL, zip_sha=FF_ZIP_SHA, exe_sha=FF_EXE_SHA, zip_size=FF_ZIP_SIZE, cafile=None):
    """Đường dẫn ffmpeg.exe đã kiểm mã (bin\\ffmpeg.exe trong thư mục CloudBluePC). Chưa có / sai mã → tải file zip từ GitHub, kiểm sha256 file zip
       VÀ sha256 file exe bên trong rồi mới ghi. Không tải / không kiểm được → None (lần sau thử lại)."""
    log = log or (lambda m: None)
    d = os.path.join(base, "bin"); exe = os.path.join(d, "ffmpeg.exe"); mark = os.path.join(d, "ffmpeg.ok")

    def sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""): h.update(blk)
        return h.hexdigest()
    try:
        if os.path.isfile(exe):
            st = os.stat(exe); tag = "%s %d %d" % (exe_sha, st.st_size, int(st.st_mtime))
            try:
                with open(mark, encoding="ascii") as f: seen = f.read().strip()
            except OSError: seen = ""
            if seen == tag: return exe                           # đã kiểm ở lần chạy trước, file chưa bị đụng (cùng cỡ + giờ sửa)
            if sha(exe) == exe_sha:
                with open(mark, "w", encoding="ascii") as f: f.write(tag)
                return exe
            log("ffmpeg.exe dang co SAI ma kiem -> tai lai")
    except OSError as e:
        log("khong doc duoc ffmpeg.exe: %s" % e)
    tmp = os.path.join(d, "ffmpeg.zip.tmp")
    try:
        os.makedirs(d, exist_ok=True)
        log("tai ffmpeg (~84 MB, 1 lan) ...")
        if fetch is not None: fetch(url, tmp)
        else:
            import urllib.request
            ctx = ssl.create_default_context()
            if cafile and os.path.isfile(cafile):
                try: ctx.load_verify_locations(cafile)
                except Exception: pass
            n = 0
            req = urllib.request.Request(url, headers={"User-Agent": "CloudBluePC-remote/" + REMOTE_VER})
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r, open(tmp, "wb") as f:
                while True:
                    blk = r.read(1 << 20)
                    if not blk: break
                    n += len(blk)
                    if n > zip_size + (1 << 20): raise ValueError("file tai ve lon hon du kien")
                    f.write(blk)
        if sha(tmp) != zip_sha: raise ValueError("file zip tai ve SAI ma kiem")
        import zipfile
        with zipfile.ZipFile(tmp) as z:
            name = next((x for x in z.namelist() if x.endswith("/bin/ffmpeg.exe")), None)
            if not name: raise ValueError("file zip khong co bin/ffmpeg.exe")
            data = z.read(name)
        if hashlib.sha256(data).hexdigest() != exe_sha: raise ValueError("ffmpeg.exe trong file zip SAI ma kiem")
        with open(exe + ".new", "wb") as f: f.write(data)
        os.replace(exe + ".new", exe)
        st = os.stat(exe)
        with open(mark, "w", encoding="ascii") as f: f.write("%s %d %d" % (exe_sha, st.st_size, int(st.st_mtime)))
        log("da co ffmpeg (%d MB, dung ma kiem)" % (len(data) >> 20))
        return exe
    except Exception as e:
        log("chua tai duoc ffmpeg: %s" % str(e)[:200])
        return None
    finally:
        try: os.remove(tmp)
        except OSError: pass


def make_logger(base=BASE, name="remote.log"):
    path = os.path.join(base, "logs", name)

    def log(m):
        line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
                try: os.replace(path, path + ".1")
                except OSError: pass
            with open(path, "a", encoding="utf-8") as f: f.write(line + "\n")
        except OSError: pass
        try: print(line, flush=True)
        except Exception: pass
    return log


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f: j = json.load(f)
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def _session_ok():
    """Chương trình này còn nằm đúng PHIÊN MÀN HÌNH đang hiện không (người dùng đăng xuất / đổi phiên → thoát, pcagent mở lại đúng phiên)."""
    try:
        import ctypes
        k = ctypes.WinDLL("kernel32")
        k.WTSGetActiveConsoleSessionId.restype = ctypes.c_uint32
        mine = ctypes.c_uint32(0)
        if not k.ProcessIdToSessionId(k.GetCurrentProcessId(), ctypes.byref(mine)): return True
        con = k.WTSGetActiveConsoleSessionId()
        return con == 0xFFFFFFFF or con == mine.value
    except Exception:
        return True


def cmd_run(argv):
    log = make_logger()
    if WIN:
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]; k.CreateMutexW.restype = ctypes.c_void_p
        h = k.CreateMutexW(None, 0, MUTEX)
        if h and ctypes.get_last_error() == 183: return 0            # đã có 1 bản đang chạy
    cfg = _load_json(os.path.join(BASE, "cb.json")) or {}
    if cfg.get("remote") is False:
        log("cb.json dat remote = false -> khong chay dieu khien tu xa"); return 0
    global IME_ON
    if cfg.get("ime") is False: IME_ON = False; log("cb.json dat ime = false -> khong theo doi o nhap chu")
    sys.path.insert(0, HERE)
    import pcagent                                                    # dùng chung phần gọi web (khoá công khai + bộ chứng chỉ kèm theo)
    net = pcagent.Net(cfg, BASE)
    cafile = os.path.join(BASE, "os", "cacert.pem")

    def ident():
        j = _load_json(os.path.join(BASE, "identity.json")) or {}
        return j if j.get("id") and j.get("token") else None
    io = WinIO(log) if WIN else NullIO()
    rm = Remote(ident, net.rpc, io, lambda: ensure_ffmpeg(BASE, log, cafile=cafile), log, cafile)
    log("=== CloudBlue PC dieu khien tu xa %s chay (phien man hinh, man %dx%d) ===" % ((REMOTE_VER,) + tuple(io.screen())))
    me = os.path.abspath(__file__)
    try: stamp = (os.path.getmtime(me), os.path.getsize(me))
    except OSError: stamp = None

    last = ["", 0.0]

    def watch():
        """Thoát khi: không còn ở phiên màn hình đang hiện · file chương trình vừa được cập nhật (đang rảnh) → pcagent mở lại bản mới / đúng phiên."""
        while True:
            time.sleep(5)
            try:
                if WIN and not _session_ok():
                    log("phien man hinh da doi -> thoat de pcagent mo lai dung phien"); os._exit(0)
                if rm.sess is None and stamp and (os.path.getmtime(me), os.path.getsize(me)) != stamp:
                    log("chuong trinh vua duoc cap nhat -> thoat de chay ban moi"); os._exit(0)
                if rm.state != last[0] or time.time() - last[1] > 60:           # trạng thái cho `cbpc status` + pcagent (đổi mới ghi, tối đa 1 phút / lần)
                    last[0], last[1] = rm.state, time.time()
                    with open(os.path.join(BASE, "logs", "remote.state"), "w", encoding="utf-8") as f: f.write("%d %s %s\n" % (time.time(), REMOTE_VER, rm.state))
            except Exception:
                pass
    threading.Thread(target=watch, daemon=True).start()
    rm.run()
    return 0


def cmd_selfcheck(argv):
    """Bản mới tự thử (pcagent gọi trước khi thay bản cũ): bảng phím, ghép RTP, chọn chất lượng — không gọi mạng, không đụng chuột / phím."""
    assert plan("auto", 0, 0, 0, 0, 1920, 1080)[:3] == (1920, 1080, 30) and fit(2560, 1440, 1280) == (1280, 720)
    assert VK[29] == (0x41, 0) and len(VK) > 100 and CMDS["home"] == (0x5B, 0x44)
    io = NullIO(); k = Keys(io); k.key(0, 29, 0x1000); k.key(1, 29, 0x1000)
    assert io.ev == [("key", 0xA2, True, False), ("key", 0x41, True, False), ("key", 0x41, False, False), ("key", 0xA2, False, False)]
    a = RtpAssembler(); pkt = bytes([0x80, 0xE0, 0, 1]) + bytes(8) + bytes([0x65, 1, 2, 3])
    assert a.feed(pkt) == (b"\x00\x00\x00\x01\x65\x01\x02\x03", True, False)
    assert parse_paths({"direct": [{"host": "1.2.3.4", "port": 8189}], "cert": "ab" * 32, "ws": "wss://a.b/v2/stream"})[0][0][:3] == ("direct", "1.2.3.4", 8189)
    assert "h264_nvenc" in ff_cmd("ffmpeg", "gdi", "nvenc", 1920, 1080, 1920, 1080, 30, 4500, 5000)
    print("selfcheck ok", REMOTE_VER)
    return 0


def cmd_probe(argv):
    log = lambda m: print(m, flush=True)
    ff = ensure_ffmpeg(BASE, log, cafile=os.path.join(BASE, "os", "cacert.pem"))
    if not ff: print("CHUA CO ffmpeg (chua tai duoc)"); return 2
    c = probe(ff, log)
    print("Nen duoc bang: %s" % (", ".join(c["enc"]) or "KHONG CO"))
    print("Quay man hinh kieu: %s" % c["cap"])
    return 0 if c["enc"] else 1


def main(argv):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    cmd = argv[0] if argv else ""
    fn = {"run": cmd_run, "selfcheck": cmd_selfcheck, "probe": cmd_probe}.get(cmd)
    if cmd in ("version", "--version"): print(REMOTE_VER); return 0
    if not fn: print("Lenh: run | selfcheck | probe | version"); return 2
    return fn(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
