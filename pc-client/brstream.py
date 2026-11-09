# -*- coding: utf-8 -*-
"""brstream.py — phần NỐI MẠNG của app PC BlueRoblox (giao thức phát hình v2, xem docs/STREAM-PROTOCOL.md).

Không dùng thư viện ngoài: socket + ssl + threading. Dùng chung cho cửa sổ xem máy (bluepc.py) và chạy thử.
    cli = StreamClient(endpoint_json, token_fn, phone_id, on_event)
    cli.start()      # luồng nền: nối (trực tiếp TLS → dự phòng WebSocket), tự nối lại
    cli.touch(0, 0, 0.5, 0.5) …  cli.close()
Sự kiện gửi về on_event(kind, data):
    "welcome" dict · "video" (flags, pts_us, annexb bytes) · "size" dict · "clip" str · "stats" dict
    "state" ("connecting"|"connected"|"reconnecting"|"kicked"|"error"|"closed", text) · "ping" ms
"""
import base64, hashlib, json, os, random, socket, ssl, struct, threading, time, urllib.parse

C_HELLO, C_TOUCH, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_PING, C_QUALITY, C_KEYFRAME, C_CLIP, C_BYE, C_ACK = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A
S_WELCOME, S_VIDEO, S_SIZE, S_CLIP, S_PONG, S_ERROR, S_STATS = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87
VERSION = "1.0.0"


class Fatal(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code, self.msg = code, msg


# ------------------------------------------------------------------ đường truyền
class DirectConn:
    kind = "direct"

    def __init__(self, host, port, cert_hex, timeout):
        raw = socket.create_connection((host, port), timeout=timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try: raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except OSError: pass
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        raw.settimeout(6)
        s = ctx.wrap_socket(raw, server_hostname="blueroblox")
        der = s.getpeercert(binary_form=True) or b""
        if not cert_hex or hashlib.sha256(der).hexdigest().lower() != cert_hex.lower():
            s.close(); raise ssl.SSLError("chứng chỉ máy chủ không khớp")
        s.settimeout(None)
        self.s = s; self.wlock = threading.Lock(); self.desc = f"{host}:{port}"

    def _rd(self, n):
        b = bytearray()
        while len(b) < n:
            x = self.s.recv(n - len(b))
            if not x: raise EOFError("mất kết nối")
            b += x
        return bytes(b)

    def recv(self):
        n = struct.unpack(">I", self._rd(4))[0]
        if n < 1 or n > 8 * 1024 * 1024: raise EOFError("khung hỏng")
        b = self._rd(n)
        return b[0], b[1:]

    def send(self, t, payload=b""):
        with self.wlock: self.s.sendall(struct.pack(">IB", 1 + len(payload), t) + payload)

    def settimeout(self, t): self.s.settimeout(t)

    def close(self):
        try: self.s.close()
        except Exception: pass


class WSConn:
    kind = "ws"

    def __init__(self, url, timeout):
        u = urllib.parse.urlparse(url)
        host = u.hostname; port = u.port or (443 if u.scheme == "wss" else 80)
        raw = socket.create_connection((host, port), timeout=timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if u.scheme == "wss" else raw
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: BlueRobloxPC/{VERSION}\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            x = s.recv(4096)
            if not x: raise EOFError("WebSocket bị từ chối")
            head += x
            if len(head) > 65536: raise EOFError("WebSocket trả lời lạ")
        hdr, _, rest = head.partition(b"\r\n\r\n")
        lines = hdr.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ": raise EOFError("WebSocket: " + lines[0][:80])
        acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        if not any(l.lower().startswith("sec-websocket-accept:") and l.split(":", 1)[1].strip() == acc for l in lines[1:]):
            raise EOFError("WebSocket: sai mã chấp nhận")
        s.settimeout(None)
        self.s = s; self.buf = bytearray(rest); self.wlock = threading.Lock(); self.desc = host

    def _rd(self, n):
        while len(self.buf) < n:
            x = self.s.recv(max(65536, n - len(self.buf)))
            if not x: raise EOFError("mất kết nối")
            self.buf += x
        b = bytes(self.buf[:n]); del self.buf[:n]
        return b

    def _frame(self):
        b0, b1 = self._rd(2)
        n = b1 & 0x7F
        if n == 126: n = struct.unpack(">H", self._rd(2))[0]
        elif n == 127: n = struct.unpack(">Q", self._rd(8))[0]
        mk = self._rd(4) if b1 & 0x80 else None
        d = self._rd(n) if n else b""
        if mk: d = bytes(c ^ mk[i % 4] for i, c in enumerate(d))
        return b0 & 0x80, b0 & 0x0F, d

    def recv(self):
        frag = None; fop = 0
        while True:
            fin, op, d = self._frame()
            if op == 8: raise EOFError("máy chủ đóng kết nối")
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
        if n:
            iv = int.from_bytes(data, "little") ^ int.from_bytes((mk * (n // 4 + 1))[:n], "little")
            data = iv.to_bytes(n, "little")
        with self.wlock: self.s.sendall(hdr + mk + data)

    def send(self, t, payload=b""): self._write(2, bytes([t]) + payload)

    def settimeout(self, t): self.s.settimeout(t)

    def close(self):
        try:
            self.s.sendall(b"\x88\x80" + os.urandom(4)); self.s.close()
        except Exception: pass


# ------------------------------------------------------------------ máy khách
class StreamClient:
    def __init__(self, endpoint, token_fn, phone_id, on_event, q="auto", client="pc", fps=None, maxh=None, prefer=None):
        self.ep, self.token_fn, self.phone, self.on_event = endpoint or {}, token_fn, phone_id, on_event
        self.q, self.client, self.fps, self.maxh = q, client, fps, maxh
        self.prefer = prefer                       # (kind, desc) lần trước nối được
        self.direct_fail_t = 0.0                   # lúc đường trực tiếp vừa hỏng trong phiên này (nối lại trong 5 phút thì đi Cloudflare luôn)
        self.conn = None; self.stop_flag = False; self.thread = None
        self.last_rx = 0.0; self.path = ""; self.fails = 0; self.auth_retry = False
        self.moves = {}; self.mlock = threading.Lock(); self.last_pts = 0; self.acked = 0

    # ---------- vòng nối / nối lại ----------
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()

    def _paths(self):
        st = (self.ep or {}).get("stream") or {}
        cert = st.get("cert") or ""
        out = []
        direct = st.get("direct") or []
        if cert:
            for d in direct:
                if d.get("lan"): out.append(("direct", d["host"], int(d["port"]), 0.4))
            for d in direct:
                if not d.get("lan"): out.append(("direct", d["host"], int(d["port"]), 2.0))
        if st.get("ws"): out.append(("ws", st["ws"], 0, 8.0))
        if self.prefer:
            pk = tuple(self.prefer)
            # Cloudflare chỉ được đưa lên đầu khi đường trực tiếp VỪA hỏng trong phiên này (5 phút). Còn lại luôn thử trực tiếp
            # trước (tối đa ~2,4 giây) → modem mở cổng xong là app tự về đường nhanh (trước đây nhớ Cloudflare mãi mãi).
            if pk[0] == "direct" or time.time() - self.direct_fail_t < 300:
                out.sort(key=lambda p: 0 if (p[0], f"{p[1]}:{p[2]}" if p[0] == "direct" else p[1]) == pk else 1)
        return out, cert

    def _connect(self):
        paths, cert = self._paths()
        if not paths: raise Fatal("OFFLINE", "Máy chủ chưa mở đường phát hình (chưa cập nhật?).")
        errs = []; dfail = False
        for kind, a, port, to in paths:
            if self.stop_flag: break
            try:
                c = DirectConn(a, port, cert, to) if kind == "direct" else WSConn(a, to)
                self.path = ("trực tiếp" if kind == "direct" else "Cloudflare")
                self.prefer = (kind, c.desc if kind == "direct" else a)
                if kind == "ws" and dfail: self.direct_fail_t = time.time()
                return c
            except Exception as e:
                errs.append(f"{kind} {a}: {e}")
                if kind == "direct": dfail = True
        raise ConnectionError("; ".join(errs)[-300:] or "không nối được")

    def _run(self):
        backoff = [0.5, 1, 2, 4, 5]; attempt = 0
        while not self.stop_flag:
            self._emit("state", ("connecting" if attempt == 0 else "reconnecting", f"Đang kết nối{' lại' if attempt else ''}…"))
            try:
                self.conn = self._connect()
                hello = {"v": 2, "token": self.token_fn(), "phone": self.phone, "client": self.client, "ver": VERSION, "q": self.q}
                if self.fps: hello["fps"] = int(self.fps)
                if self.maxh: hello["maxh"] = int(self.maxh)
                self.conn.send(C_HELLO, json.dumps(hello).encode())
                self.conn.settimeout(6)
                self.last_rx = time.time()
                threading.Thread(target=self._pinger, args=(self.conn,), daemon=True).start()
                threading.Thread(target=self._mover, args=(self.conn,), daemon=True).start()
                got_video = self._loop(self.conn)
                if got_video: attempt = 0
            except Fatal as f:
                if f.code == "AUTH" and not self.auth_retry:
                    self.auth_retry = True; self._emit("state", ("reconnecting", "Đang làm mới đăng nhập…"))
                    try: self.token_fn(force=True)
                    except Exception: pass
                    continue
                self._emit("state", ("kicked" if f.code == "KICKED" else "error", f.msg, f.code))
                self.stop_flag = True; break
            except Exception as e:
                if self.stop_flag: break
                self._emit("state", ("reconnecting", f"Mất kết nối ({str(e)[:80]}) — đang nối lại…"))
            finally:
                if self.conn: self.conn.close()
                self.conn = None
            if self.stop_flag: break
            time.sleep(backoff[min(attempt, len(backoff) - 1)] * (0.8 + random.random() * 0.4)); attempt += 1
        self._emit("state", ("closed", "Đã đóng"))

    def _loop(self, c):
        got_video = False
        while not self.stop_flag:
            try:
                t, p = c.recv()
            except socket.timeout:
                raise ConnectionError("không nhận được dữ liệu 6 giây")
            self.last_rx = time.time()
            if t == S_VIDEO and len(p) > 9:
                flags, pts = struct.unpack(">BQ", p[:9]); self.last_pts = pts
                if flags & 1: self._ack()
                if not got_video: got_video = True; self.auth_retry = False; self._emit("state", ("connected", self.path))
                self._emit("video", (flags, pts, p[9:]))
            elif t == S_WELCOME: self._emit("welcome", json.loads(p.decode("utf-8")))
            elif t == S_SIZE: self._emit("size", json.loads(p.decode("utf-8")))
            elif t == S_CLIP: self._emit("clip", p.decode("utf-8", "replace"))
            elif t == S_STATS: self._emit("stats", json.loads(p.decode("utf-8")))
            elif t == S_PONG and len(p) >= 8: self._emit("ping", max(0, int(time.time() * 1000) - struct.unpack(">Q", p[:8])[0]))
            elif t == S_ERROR:
                j = json.loads(p.decode("utf-8") or "{}")
                raise Fatal(j.get("code") or "INTERNAL", j.get("msg") or "Lỗi máy chủ")
        return got_video

    def _pinger(self, c):
        while not self.stop_flag and self.conn is c:
            try: c.send(C_PING, struct.pack(">Q", int(time.time() * 1000)))
            except Exception: return
            time.sleep(2)

    def _ack(self):
        if self.last_pts and self.last_pts != self.acked:
            self.acked = self.last_pts; self._send(C_ACK, struct.pack(">Q", self.last_pts))

    def _mover(self, c):
        """Gộp các lần kéo: mỗi ngón tối đa 1 lệnh kéo / 8 ms (chuột rê nhanh không làm nghẽn) + báo đã nhận hình (ACK) mỗi 0,1 giây."""
        n = 0
        while not self.stop_flag and self.conn is c:
            time.sleep(0.008); n += 1
            if n % 12 == 0: self._ack()
            with self.mlock:
                mv, self.moves = self.moves, {}
            for ptr, (x, y) in mv.items():
                self._send(C_TOUCH, struct.pack(">BBHH", 2, ptr, x, y))

    def _emit(self, k, d):
        try: self.on_event(k, d)
        except Exception: pass

    def _send(self, t, p=b""):
        c = self.conn
        if c is None: return False
        try: c.send(t, p); return True
        except Exception: return False

    # ---------- lệnh ----------
    @staticmethod
    def _u16(v): return max(0, min(65535, int(v * 65535 + 0.5)))

    def touch(self, action, pointer, nx, ny):
        x, y = self._u16(nx), self._u16(ny)
        if action == 2:
            with self.mlock: self.moves[pointer] = (x, y)
            return
        with self.mlock: self.moves.pop(pointer, None)
        self._send(C_TOUCH, struct.pack(">BBHH", action, pointer, x, y))

    def key(self, action, code, meta=0): self._send(C_KEY, struct.pack(">BII", action, code, meta))
    def press(self, code, meta=0): self.key(0, code, meta); self.key(1, code, meta)
    def text(self, s):
        if s: self._send(C_TEXT, s.encode("utf-8"))
    def scroll(self, nx, ny, h, v): self._send(C_SCROLL, struct.pack(">HHhh", self._u16(nx), self._u16(ny), int(h), int(v)))
    def cmd(self, name): self._send(C_CMD, json.dumps({"cmd": name}).encode())
    def rotate(self, to):
        """Xoay máy: "land" khoá ngang · "port" khoá dọc (máy chủ cũ hiểu như "rotate" đổi qua lại)."""
        self._send(C_CMD, json.dumps({"cmd": "rotate", "to": to}).encode())
    def quality(self, q, fps=None, kbps=None):
        self.q = q; j = {"q": q}
        if fps: j["fps"] = fps
        if kbps: j["kbps"] = kbps
        self._send(C_QUALITY, json.dumps(j).encode())
    def keyframe(self): self._send(C_KEYFRAME)
    def clip_set(self, text, paste=True): self._send(C_CLIP, bytes([1 if paste else 0]) + text.encode("utf-8"))

    def close(self):
        self.stop_flag = True
        self._send(C_BYE)
        c = self.conn
        if c: c.close()
