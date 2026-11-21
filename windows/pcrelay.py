# -*- coding: utf-8 -*-
# =====================================================================================================
#  pcrelay.py — TRẠM TRUNG CHUYỂN cho MÁY PC CHO THUÊ (đợt 2), chạy BÊN TRONG bluestream.py
#
#  Máy PC thuê nằm sau modem của phòng máy → không ai nối thẳng vào được. Mỗi máy PC tự nối RA cổng phát hình của 1 máy chủ
#  cloud phone (TLS :8189 hoặc đường vòng Cloudflare) rồi ngồi chờ. Khách mở điều khiển máy PC (web / app) cũng nối vào đúng
#  cổng đó như mở máy điện thoại → trạm ghép 2 kết nối: hình đi máy PC → khách, chuột / phím đi khách → máy PC.
#
#     máy PC  ──P_HELLO {pc, token}──▶  trạm ──pc_relay_auth (khoá dịch vụ)──▶ Supabase       trạm trả R_OK
#     khách   ──HELLO {pc, token}────▶  trạm ──whoami + pc_relay_viewer──────▶ Supabase       (chủ máy / admin mới được)
#     trạm    ──R_START {sid, q, fps…}▶ máy PC bật bộ quay màn hình ──P_INFO {sid, w, h…}──▶ trạm ──WELCOME──▶ khách
#     máy PC  ──VIDEO…──▶ trạm ──VIDEO…──▶ khách        khách ──TOUCH / MOUSE / KEY / TEXT…──▶ trạm ──▶ máy PC
#     khách đóng → trạm gửi R_STOP → máy PC TẮT bộ quay (không ai xem thì máy không tốn CPU / card hình)
#
#  Trạm KHÔNG giải mã hình, không đọc phím: chỉ chuyển gói. Người xem nhận chậm → trạm bỏ khung tới khung khoá kế (không dồn trễ)
#  và báo máy PC (R_SLOW) để máy tự hạ bitrate. Mỗi máy PC 1 người xem (người mở sau đá người mở trước, giống máy điện thoại).
#  Cần SQL v43 (pc_relay_auth · pc_relay_seen · pc_relay_gone · pc_relay_viewer). Tắt trạm: PC_RELAY=0 trong cloudphone.conf.
#
#  bluestream.py gọi 2 hàm:   serve_source(H, link, gói_chào)   ·   serve_viewer(H, link, hello)      (H = chính mô-đun bluestream)
# =====================================================================================================
import asyncio, collections, json, re, time, urllib.error

PCRELAY_VER = "21/11a"
P_HELLO, P_INFO = 0x02, 0x03                          # máy PC → trạm: chào (JSON) · thông số hình của phiên đang phát (JSON)
R_OK, R_START, R_STOP, R_SLOW = 0x90, 0x91, 0x92, 0x93   # trạm → máy PC: đã nhận máy · có người xem, bật hình · hết người xem · người xem nhận chậm
C_MOUSE = 0x1B                                        # khách → máy PC: chuột thật (rê không bấm, nút phải / giữa) — xem docs/STREAM-PROTOCOL.md mục 6
# gói khách → máy PC được chuyển nguyên: loại → (dài tối thiểu, dài tối đa). Máy PC tự kiểm nội dung từng gói.
FWD = {0x10: (6, 16), 0x11: (9, 16), 0x12: (0, 64 * 1024), 0x13: (8, 16), 0x14: (2, 2048), 0x16: (2, 2048), 0x17: (0, 8),
       0x18: (1, 256 * 1024), 0x1A: (8, 16), C_MOUSE: (6, 16)}
MOVES = (0x10, C_MOUSE)                               # gói rê (bỏ được khi đường tới máy PC đang nghẽn)

MAX_SOURCES = 400                                     # tối đa số máy PC nối vào 1 trạm
PING_S = 5                                            # máy PC đang rảnh gửi PING mỗi 5 giây
SRC_IDLE_S = 40                                       # máy PC im quá chừng này giây → coi là đứt
VIEW_IDLE_S = 15                                      # khách im quá chừng này giây → đóng phiên (như máy điện thoại)
INFO_WAIT_S = 25                                      # chờ máy PC bật bộ quay màn hình rồi gửi P_INFO
SRC_WAIT_NEW = 8                                      # khách tới mà máy PC chưa nối vào trạm này: chờ tối đa
SRC_WAIT_BACK = 25                                    # đang xem mà máy PC đứt (mạng chập chờn): giữ khách chờ máy nối lại tối đa
REAUTH_S = 30                                         # phiên đang mở: kiểm lại quyền (hết hạn thuê / admin bỏ gán / khoá tài khoản → ngắt)
BEAT_S = 40                                           # báo Supabase "các máy này còn nối" (SQL coi máy đứt sau 100 giây không báo)
BUF_HIGH = 192 * 1024                                 # bộ đệm gửi tới khách vượt mức này → bỏ khung tới khung khoá kế
SRC_BUF_MAX = 1024 * 1024                             # bộ đệm gửi tới máy PC vượt mức này → máy PC treo, đóng kết nối
FAIL_MAX, FAIL_IP, FAIL_VIEW, FAIL_WIN = 12, 120, 40, 600   # trong 10 phút: 1 IP sai mã CÙNG 1 máy PC quá 12 lần / sai mã mọi máy quá 120 lần /
                                                      # khách sai phiên đăng nhập quá 40 lần → từ chối luôn, không hỏi Supabase (cả phòng máy chung 1 IP:
                                                      # 1 máy hỏng mã không làm cả phòng bị chặn)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

SOURCES = {}                                          # mã máy PC → Source (máy đang nối vào trạm này)
VIEWERS = {}                                          # mã máy PC → Viewer (người đang điều khiển)
_FAILS = {}                                           # IP → deque(lúc sai mã)
_state = {"beat": None, "nosql": 0.0, "said": 0.0}


class Bye(Exception):
    """Kết thúc phiên kèm lời báo cho bên kia (gói ERROR)."""
    def __init__(self, code, msg, **extra): super().__init__(msg); self.code, self.msg, self.extra = code, msg, extra


# ------------------------------------------------------------------ tiện ích
def _peer(link):
    """IP bên kia. Kết nối thẳng: địa chỉ TCP. Đường vòng Cloudflare (cloudflared chạy ngay trên máy chủ → địa chỉ TCP là 127.0.0.1):
       IP khách do Cloudflare ghi (bluestream chỉ đặt link.ip cho kết nối tới từ cổng nội bộ). Không biết → "" (không giới hạn theo IP)."""
    try: h = str((link.w.get_extra_info("peername") or ("",))[0])
    except Exception: h = ""
    if h in ("127.0.0.1", "::1", ""):
        ip = getattr(link, "ip", "")
        return ip if isinstance(ip, str) and re.fullmatch(r"[0-9A-Fa-f:.]{3,45}", ip) else ""
    return h


def _blocked(key, limit=FAIL_MAX, now=None):
    """Khoá `key` (loại + IP) vừa sai quá `limit` lần trong FAIL_WIN giây → True (từ chối luôn, không hỏi Supabase)."""
    if not key or key.endswith(":"): return False
    now = time.time() if now is None else now
    q = _FAILS.get(key)
    if not q: return False
    while q and now - q[0] > FAIL_WIN: q.popleft()
    if not q: _FAILS.pop(key, None); return False
    return len(q) >= limit


def _fail(key, now=None):
    if not key or key.endswith(":"): return
    if len(_FAILS) > 20000: _FAILS.clear()
    _FAILS.setdefault(key, collections.deque(maxlen=FAIL_IP)).append(time.time() if now is None else now)


def _buf(link):
    try: return link.w.transport.get_write_buffer_size()
    except Exception: return 0


def _int(v, lo, hi, d=0):
    try: v = int(v)
    except (TypeError, ValueError, OverflowError): return d
    return v if lo <= v <= hi else d


def _clean_info(j):
    """Thông số máy PC tự báo (gói chào / P_INFO) → chỉ giữ trường đã biết, đúng kiểu."""
    j = j if isinstance(j, dict) else {}
    out = {"w": _int(j.get("w"), 16, 16384), "h": _int(j.get("h"), 16, 16384)}
    for k, n in (("enc", 16), ("ver", 24), ("cap", 16), ("q", 8)):
        v = j.get(k)
        if isinstance(v, str) and v: out[k] = re.sub(r"[^A-Za-z0-9_./+-]", "", v)[:n]
    for k, hi in (("fps", 240), ("kbps", 200000), ("sid", 2 ** 31 - 1)):
        if k in j: out[k] = _int(j.get(k), 0, hi)
    return out


def _rpc(H, fn, body):
    return H.sb("POST", "/rest/v1/rpc/" + fn, body, timeout=12)


def _rpc_safe(H, fn, body):
    """Gọi hàm SQL v43 → dict. Lỗi: {'ok': False, 'err': 'NO_SQL' | 'NET'} (không ném lỗi)."""
    try:
        r = _rpc(H, fn, body)
        return r if isinstance(r, dict) else {"ok": False, "err": "NET"}
    except urllib.error.HTTPError as e:
        if e.code == 404:                                     # PostgREST: chưa có hàm → chưa chạy SQL v43
            _state["nosql"] = time.time()
            if time.time() - _state["said"] > 600:
                _state["said"] = time.time(); H.log("trạm máy PC: Supabase chưa có hàm " + fn + " — chưa chạy cloud-pc-v43.sql?")
            return {"ok": False, "err": "NO_SQL"}
        return {"ok": False, "err": "NET"}
    except Exception:
        return {"ok": False, "err": "NET"}


async def _refuse(H, link, code, msg, **extra):
    link.send_nowait(H.S_ERROR, H.err_json(code, msg, **extra))
    try: await asyncio.wait_for(link.w.drain(), 2)
    except Exception: pass
    await link.close()


# ------------------------------------------------------------------ nhịp báo "máy còn nối"
async def _beat_loop(H):
    idle = 0
    while idle < 15:                                          # 10 phút không còn máy PC nào → dừng nhịp (máy sau nối tới thì bật lại)
        await asyncio.sleep(BEAT_S)
        ids = [s.pid for s in SOURCES.values() if not s.closed]
        if not ids: idle += 1; continue
        idle = 0
        if H.SELFTEST: continue
        try: await asyncio.to_thread(_rpc_safe, H, "pc_relay_seen", {"p_ids": ids, "p_node": H.NODE_ID})
        except Exception: pass


def _ensure_beat(H):
    t = _state["beat"]
    if t is None or t.done(): _state["beat"] = asyncio.ensure_future(_beat_loop(H))


# ================================================================== MÁY PC (nguồn hình)
class Source:
    def __init__(self, H, link, pid, auth, info):
        self.H, self.link, self.pid = H, link, pid
        self.name = str(auth.get("name") or "Máy PC")[:80]; self.code = str(auth.get("code") or "")[:24]
        self.hello = info                              # máy tự báo lúc chào: {"w","h","enc","ver"}
        self.viewer = None; self.sid = 0; self.closed = False; self.why = ""
        self.t0 = time.time(); self.last_rx = time.time(); self.stray = 0; self.t_stop = 0.0; self.frames = 0

    @property
    def tag(self): return (self.code + " · " if self.code else "") + self.name

    def tell(self, t, payload=b""):
        """Gửi 1 gói nhỏ cho máy PC (không chờ). Máy PC không đọc → bộ đệm phình → coi như treo, đóng."""
        if self.closed or self.link.dead(): return False
        if _buf(self.link) > SRC_BUF_MAX:
            self.why = self.why or "máy PC không đọc lệnh (treo)"; self.closed = True
            asyncio.ensure_future(self.link.close()); return False
        self.link.send_nowait(t, payload); return True

    def start(self, v):
        """Có người xem → bảo máy PC bật bộ quay màn hình cho phiên số sid."""
        self.sid = self.sid % 0x7FFFFFF0 + 1
        self.viewer = v; v.src = self; v.sid = self.sid; v.got_info = False; v.wait_key = True; v.t_req = time.time()
        h = v.hello
        req = {"sid": self.sid, "q": v.q, "fps": _int(h.get("fps"), 1, 240), "maxh": _int(h.get("maxh"), 160, 16384),
               "kbps": _int(h.get("kbps"), 100, 200000), "net": str(h.get("net") or "")[:2], "dl": _int(h.get("dl"), 0, 10 ** 6),
               "client": re.sub(r"[^a-z0-9]", "", str(h.get("client") or "").lower())[:12], "link": v.link.kind, "admin": bool(v.me.get("admin")), "owner": v.owner}
        return self.tell(R_START, json.dumps(req).encode())

    def stop(self, v):
        if self.viewer is v:
            self.viewer = None
            self.tell(R_STOP, b""); self.t_stop = time.time()

    def _on_info(self, p):
        if len(p) > 2048: return
        try: info = _clean_info(json.loads(p.decode("utf-8")))
        except Exception: return
        v = self.viewer
        if v is not None and info.get("sid") == v.sid and info["w"] and info["h"]: v.on_info(info)

    async def run(self):
        H = self.H; S_VIDEO, C_PING = H.S_VIDEO, H.C_PING
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), SRC_IDLE_S)
            self.last_rx = time.time()
            v = self.viewer
            if t == S_VIDEO:
                self.frames += 1
                if v is not None:
                    if len(p) > 9: v.on_video(p)
                else:                                          # không ai xem mà máy vẫn gửi hình (lệnh dừng chưa tới) → nhắc dừng, 3 giây 1 lần
                    self.stray += 1
                    if time.time() - self.t_stop > 3: self.t_stop = time.time(); self.tell(R_STOP, b"")
            elif t == C_PING: self.link.send_nowait(H.S_PONG, p[:8])
            elif t == P_INFO: self._on_info(p)
            elif v is None or not v.got_info: continue
            elif t == H.S_STATS: v.on_stats(p)
            elif t == H.S_SIZE and len(p) <= 256: v.link.send_nowait(t, p)
            elif t == H.S_CLIP and len(p) <= 256 * 1024: v.link.send_nowait(t, p)
            elif t == H.S_ERROR and len(p) <= 2048: v.src_error(p)

    async def finish(self):
        self.closed = True
        mine = SOURCES.get(self.pid) is self
        if mine: SOURCES.pop(self.pid, None)
        v, self.viewer = self.viewer, None
        if v is not None and v.src is self: v.src = None; v.t_nosrc = time.time()      # khách được giữ chờ máy nối lại (SRC_WAIT_BACK)
        await self.link.close()
        H = self.H
        H.log(f"🖥 máy PC {self.tag} rời trạm · {int(time.time() - self.t0)} giây · {self.frames} khung" + (f" · {self.why}" if self.why else ""))
        if mine and not H.SELFTEST:                            # máy nối lại bằng kết nối khác thì KHÔNG báo "đã rời" (bản ghi mới đang đúng)
            try: await asyncio.to_thread(_rpc_safe, H, "pc_relay_gone", {"p_id": self.pid, "p_node": H.NODE_ID})
            except Exception: pass


def _auth_source(H, pid, token, info):
    if H.SELFTEST: return {"ok": True, "name": "PC thử", "code": "T-1", "user_id": None}
    return _rpc_safe(H, "pc_relay_auth", {"p_id": pid, "p_token": token, "p_node": H.NODE_ID, "p_info": info})


async def serve_source(H, link, payload):
    """Kết nối có gói đầu là P_HELLO: 1 máy PC cho thuê xin vào trạm."""
    ip = "s:" + _peer(link)
    try: hello = json.loads(payload.decode("utf-8")) if len(payload) <= 4096 else None
    except Exception: hello = None
    pid = str((hello or {}).get("pc") or "").lower() if isinstance(hello, dict) else ""
    token = (hello or {}).get("token") if isinstance(hello, dict) else None
    if not UUID.fullmatch(pid) or not isinstance(token, str) or not 0 < len(token) <= 200:
        return await _refuse(H, link, "BAD", "Gói chào không hợp lệ.")
    if _blocked(ip, FAIL_IP) or _blocked(ip + "|" + pid): return await _refuse(H, link, "BUSY", "Sai mã máy quá nhiều lần — thử lại sau 10 phút.")
    if len(SOURCES) >= MAX_SOURCES and pid not in SOURCES: return await _refuse(H, link, "BUSY", "Trạm đang đầy — thử lại sau.")
    info = _clean_info(hello)
    r = await asyncio.to_thread(_auth_source, H, pid, token, info)
    if not r.get("ok"):
        err = str(r.get("err") or "")
        if err == "BAD_TOKEN": _fail(ip); _fail(ip + "|" + pid)
        code, msg = {"BAD_TOKEN": ("AUTH", "Mã máy không đúng."), "OFF": ("OFF", "Máy này chưa được bật điều khiển từ xa."),
                     "NO_SQL": ("BUSY", "Hệ thống chưa bật điều khiển máy PC.")}.get(err, ("BUSY", "Trạm chưa kiểm được mã máy — thử lại sau."))
        return await _refuse(H, link, code, msg)
    src = Source(H, link, pid, r, info)
    old = SOURCES.get(pid); SOURCES[pid] = src
    if old is not None:                                        # chính máy đó nối lại (mạng chập chờn) → bỏ kết nối cũ; khách đang xem được chuyển sang kết nối mới
        old.why = old.why or "máy nối lại bằng kết nối khác"; old.closed = True
        try: await old.link.close()
        except Exception: pass
    link.welcomed = True
    link.send_nowait(R_OK, json.dumps({"ok": True, "name": src.name, "node": H.NODE_ID, "ping_s": PING_S, "ver": PCRELAY_VER}, ensure_ascii=False).encode())
    _ensure_beat(H)
    H.log(f"🖥 máy PC {src.tag} nối vào trạm ({link.kind}" + (f", màn {info['w']}x{info['h']}" if info["w"] else "")
          + (f", bản {info['ver']}" if info.get("ver") else "") + f") · đang có {len(SOURCES)} máy")
    try:
        await src.run()
    except asyncio.TimeoutError:
        src.why = src.why or f"{SRC_IDLE_S} giây máy không gửi gì"; raise
    except (asyncio.IncompleteReadError, ConnectionError, EOFError, OSError):
        src.why = src.why or "máy ngắt kết nối"; raise
    finally:
        await src.finish()


# ================================================================== KHÁCH (người điều khiển)
class Viewer:
    def __init__(self, H, link, me, pid, hello, grant):
        self.H, self.link, self.me, self.pid, self.hello = H, link, me, pid, hello
        self.name = str(grant.get("name") or "Máy PC")[:80]; self.code = str(grant.get("code") or "")[:24]
        self.until = grant.get("until") if isinstance(grant.get("until"), (int, float)) else None
        self.owner = bool(grant.get("owner"))          # người xem chính là khách được gán máy (admin vào hỗ trợ thì máy PC hiện lời báo cho người ngồi máy)
        self.q = hello.get("q") if hello.get("q") in ("eco", "bal", "hd", "auto") else "auto"
        self.src = None; self.sid = 0; self.got_info = False; self.info = {}; self.wait_key = True
        self.closed = False; self.why = ""; self.t0 = time.time(); self.last_rx = time.time(); self.t_auth = time.time()
        self.t_nosrc = time.time(); self.t_req = 0.0; self.t_slow = 0.0
        self.sent = 0; self.bytes = 0; self.drop = 0; self.cong = 0; self.err = None

    @property
    def tag(self): return (self.code + " · " if self.code else "") + self.name

    # ---------- hình: máy PC → khách ----------
    def on_info(self, info):
        """Máy PC đã bật bộ quay cho phiên này: gói đầu → WELCOME; về sau đổi cỡ hình → SIZE. Khung kế phải là khung khoá."""
        H = self.H; old = (self.info.get("w"), self.info.get("h"))
        self.info = info; self.got_info = True; self.wait_key = True
        if not self.link.welcomed:
            self.link.welcomed = True
            dt = time.time() - self.t0
            if dt > 5: H.log(f"  PC {self.tag}: mở mất {dt:.0f} giây (khách được giữ kết nối trong lúc máy bật bộ quay)")
            self.link.send_nowait(H.S_WELCOME, json.dumps({"ok": True, "w": info["w"], "h": info["h"], "fps": info.get("fps") or 30,
                "kbps": info.get("kbps") or 0, "codec": "h264", "enc": info.get("enc") or "", "name": self.name, "android": "pc",
                "q": self.q, "kind": "pc", "code": self.code}, ensure_ascii=False).encode())
        elif (info["w"], info["h"]) != old:
            self.link.send_nowait(H.S_SIZE, json.dumps({"w": info["w"], "h": info["h"]}).encode())

    def on_video(self, p):
        """1 khung hình từ máy PC. Khách nhận không kịp (bộ đệm gửi phình) → bỏ tới khung khoá kế, không để trễ dồn."""
        if not self.got_info or self.closed: return
        key = p[0] & 1; buf = _buf(self.link)
        if self.wait_key:
            if not key or buf > BUF_HIGH: self.drop += 1; return
            self.wait_key = False
        elif buf > BUF_HIGH:
            self.drop += 1; self.cong += 1; self.wait_key = True
            now = time.time()
            if now - self.t_slow > 1 and self.src is not None:   # báo máy PC: người xem nhận chậm (máy tự hạ bitrate nếu lặp lại)
                self.t_slow = now; self.src.tell(R_SLOW, json.dumps({"buf": buf // 1024, "n": self.cong}).encode())
            return
        if self.link.dead(): return
        try: self.link.write(self.H.S_VIDEO, p)
        except Exception: return
        self.sent += 1; self.bytes += len(p) - 9

    def on_stats(self, p):
        if len(p) > 1024: return
        try:
            st = json.loads(p.decode("utf-8"))
            if not isinstance(st, dict): return
            st["drop"] = _int(st.get("drop"), 0, 10 ** 9) + self.drop
            self.link.send_nowait(self.H.S_STATS, json.dumps(st).encode())
        except Exception:
            pass

    def src_error(self, p):
        """Máy PC báo không phát được hình (không quay được màn hình, thiếu bộ nén…) → chuyển lời báo cho khách rồi đóng phiên."""
        try: j = json.loads(p.decode("utf-8"))
        except Exception: j = {}
        msg = str((j or {}).get("msg") or "")[:300] or "Máy PC chưa phát được hình — thử lại sau ít phút."
        self.err = Bye("OFFLINE", msg)

    # ---------- chuột / phím: khách → máy PC ----------
    async def _receiver(self):
        H = self.H; C_PING, C_BYE = H.C_PING, H.C_BYE
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), VIEW_IDLE_S)
            self.last_rx = time.time()
            if t == C_PING: self.link.send_nowait(H.S_PONG, p[:8]); continue
            if t == C_BYE: return
            lim = FWD.get(t)
            if lim is None or not lim[0] <= len(p) <= lim[1]: continue
            src = self.src
            if src is None or src.closed or not self.got_info: continue
            if t in MOVES and len(p) >= 1 and p[0] in (0, 2) and _buf(src.link) > 128 * 1024:
                if (t == 0x10 and p[0] == 2) or (t == C_MOUSE and p[0] == 0): continue      # đường tới máy PC nghẽn: bỏ gói RÊ (bấm / nhả vẫn chuyển)
            src.tell(t, p)

    def _recheck(self):
        """Phiên đang mở còn quyền không → None (còn) hoặc Bye. Lỗi mạng → không kết luận (không ngắt oan)."""
        H = self.H
        if H.SELFTEST: return None
        r = _rpc_safe(H, "pc_relay_viewer", {"p_id": self.pid, "p_uid": self.me.get("uid")})
        if r.get("ok"):
            self.until = r.get("until") if isinstance(r.get("until"), (int, float)) else None
            return None
        if r.get("err") in ("NET", "NO_SQL"): return None
        return Bye(str(r.get("code") or "LOCKED"), str(r.get("msg") or "Bạn không còn quyền điều khiển máy PC này."))

    async def _monitor(self):
        H = self.H
        while not self.closed:
            now = time.time()
            if self.err is not None: raise self.err
            src = SOURCES.get(self.pid)
            if src is not None and src.closed: src = None
            if src is not self.src or (src is not None and src.viewer is not self):
                if src is not None:                            # máy PC vừa nối (lại) vào trạm → gắn phiên này vào, xin hình
                    if self.src is not None or self.link.welcomed: H.log(f"  PC {self.tag}: máy nối lại → phát tiếp cho khách")
                    old = src.viewer
                    if old is not None and old is not self: await old.kick()
                    src.start(self)
                else:
                    self.src = None
            if self.src is None:
                if now - self.t_nosrc > (SRC_WAIT_BACK if self.link.welcomed else SRC_WAIT_NEW):
                    raise Bye("OFFLINE", "Máy PC vừa mất kết nối (tắt máy / mất mạng) — mở lại sau ít phút." if self.link.welcomed
                              else "Máy PC chưa nối tới máy chủ — kiểm tra máy đang bật và có mạng rồi mở lại.")
            else:
                self.t_nosrc = now
                if not self.got_info and now - self.t_req > INFO_WAIT_S:
                    raise Bye("OFFLINE", "Máy PC chưa gửi được hình (bộ quay màn hình chưa chạy) — thử lại sau ít giây.")
            if now - self.last_rx > VIEW_IDLE_S: self.why = self.why or f"{VIEW_IDLE_S} giây app không gửi gì"; return
            if self.until and now >= self.until and not self.me.get("admin"):
                raise Bye("LOCKED", "Máy PC đã hết hạn thuê — gia hạn để dùng tiếp.")
            if now - self.t_auth >= REAUTH_S:
                self.t_auth = now
                d = await asyncio.to_thread(self._recheck)
                if d is not None:
                    H.log(f"  PC {self.tag}: hết quyền ({d.code}) → ngắt phiên của {str(self.me.get('uid'))[:8]}")
                    raise d
            await asyncio.sleep(0.25)

    async def run(self):
        H = self.H
        tasks = [asyncio.ensure_future(x) for x in (self._receiver(), self._monitor())]
        try:
            done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                if not t.done(): t.cancel()
        for t in done:
            ex = t.exception() if not t.cancelled() else None
            if isinstance(ex, Bye):
                self.why = self.why or f"báo khách {ex.code}"
                self.link.send_nowait(H.S_ERROR, H.err_json(ex.code, ex.msg, **ex.extra))
            elif ex is None: self.why = self.why or ("app đóng" if t is tasks[0] else "canh phiên dừng")
            elif isinstance(ex, asyncio.TimeoutError): self.why = self.why or f"{VIEW_IDLE_S} giây app không gửi gì"
            elif isinstance(ex, (asyncio.IncompleteReadError, ConnectionError, EOFError, OSError)): self.why = self.why or "app ngắt kết nối"
            else:
                self.why = self.why or f"lỗi phiên {type(ex).__name__}"; H.log(f"  PC {self.tag}: lỗi phiên {ex!r}")

    async def kick(self):
        self.why = self.why or "mở ở nơi khác"
        self.link.send_nowait(self.H.S_ERROR, json.dumps({"code": "KICKED", "msg": "Máy đang được mở ở nơi khác."}, ensure_ascii=False).encode())
        await self.finish()

    async def finish(self):
        if self.closed: return
        self.closed = True
        if VIEWERS.get(self.pid) is self: VIEWERS.pop(self.pid, None)
        src, self.src = self.src, None
        if src is not None: src.stop(self)                     # hết người xem → máy PC tắt bộ quay
        try: await asyncio.wait_for(self.link.w.drain(), 2)    # để lời báo (ERROR) kịp tới khách trước khi đóng
        except Exception: pass
        await self.link.close()
        self.H.log(f"■ PC {self.tag} đóng (gửi {self.sent} khung, bỏ {self.drop}) · {int(time.time() - self.t0)} giây" + (f" · {self.why}" if self.why else ""))


def _auth_viewer(H, hello, pid):
    """Kiểm quyền điều khiển máy PC → (me, grant). Không được → Bye."""
    if H.SELFTEST: return {"uid": "test", "admin": True}, {"ok": True, "name": "PC thử", "code": "T-1", "admin": True, "owner": False, "until": None}
    me = H.whoami(hello.get("token") or "")
    if not me: raise Bye("AUTH", "Phiên đăng nhập hết hạn, hãy đăng nhập lại.")
    r = _rpc_safe(H, "pc_relay_viewer", {"p_id": pid, "p_uid": me["uid"]})
    if not r.get("ok"):
        if r.get("err") == "NO_SQL": raise Bye("OFFLINE", "Hệ thống chưa bật điều khiển máy PC — báo hỗ trợ.")
        if r.get("err") == "NET": raise Bye("OFFLINE", "Máy chủ chưa kiểm được quyền — thử lại sau ít giây.")
        raise Bye(str(r.get("code") or "NOT_YOURS"), str(r.get("msg") or "Đây không phải máy PC của bạn."))
    try: mt = H.maint()
    except Exception: mt = {}
    if isinstance(mt, dict) and mt.get("maint") and not me.get("admin"):
        raise Bye("MAINT", mt.get("maint_msg") or "Hệ thống đang bảo trì, quay lại sau ít phút.")
    return me, r


async def serve_viewer(H, link, hello):
    """Kết nối có HELLO chứa "pc": khách (hoặc admin) mở điều khiển 1 máy PC."""
    ka = asyncio.ensure_future(H.hello_keepalive(link)); v = None
    try:
        pid = str(hello.get("pc") or "").lower()
        if not UUID.fullmatch(pid): return await _refuse(H, link, "BAD", "Thiếu mã máy PC.")
        if str(hello.get("mode") or "") == "preview": return await _refuse(H, link, "PREVIEW_LIMIT", "Máy PC không có hình xem trước.")
        ip = "v:" + _peer(link)
        if _blocked(ip, FAIL_VIEW): return await _refuse(H, link, "BUSY", "Thử quá nhiều lần — đợi vài phút rồi mở lại.")
        try:
            me, grant = await asyncio.to_thread(_auth_viewer, H, hello, pid)
        except Bye as d:
            if d.code in ("AUTH", "NOT_YOURS"): _fail(ip)
            return await _refuse(H, link, d.code, d.msg, **d.extra)
        v = Viewer(H, link, me, pid, hello, grant)
        old = VIEWERS.get(pid)
        if old is not None: await old.kick()                   # mỗi máy 1 người điều khiển: người mở sau đá người mở trước
        VIEWERS[pid] = v
        H.log(f"▶ PC {v.tag}: {str(me.get('uid'))[:8]}{' (admin)' if me.get('admin') else ''} mở điều khiển ({link.kind}, {str(hello.get('client') or '?')[:12]})")
        await v.run()
    finally:
        ka.cancel()
        if v is not None: await v.finish()
