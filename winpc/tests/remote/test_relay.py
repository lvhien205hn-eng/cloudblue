# -*- coding: utf-8 -*-
"""Thử trạm trung chuyển máy PC (windows/pcrelay.py) + móc trong windows/bluestream.py — chạy ngay trong 1 tiến trình, không cần Windows.
   Supabase được thay bằng bản giả trong bộ nhớ (H.sb / H.whoami). Chạy:  python3 winpc/tests/remote/test_relay.py
"""
import asyncio, base64, hashlib, importlib, io, json, os, re, shutil, struct, sys, tempfile, time, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import SRV as SRC                                       # noqa: E402
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


def load(tmp, with_relay=True, conf=""):
    """Nạp bluestream.py (kèm / không kèm pcrelay.py) từ 1 thư mục tạm như trên máy chủ thật."""
    for f in ("bluestream.py",) + (("pcrelay.py",) if with_relay else ()):
        shutil.copy(os.path.join(SRC, f), os.path.join(tmp, f))
    if conf: open(os.path.join(tmp, "cloudphone.conf"), "w", encoding="utf-8").write(conf)
    for m in ("bluestream", "pcrelay"): sys.modules.pop(m, None)
    sys.path[:] = [p for p in sys.path if not p.startswith(tempfile.gettempdir())]
    sys.path.insert(0, tmp); sys.argv = ["bluestream.py"]
    H = importlib.import_module("bluestream")
    H.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
    return H


LOGS = []
C_HELLO, C_TOUCH, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_PING, C_QUALITY, C_KEYFRAME, C_CLIP, C_BYE, C_ACK, C_MOUSE = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B
S_WELCOME, S_VIDEO, S_SIZE, S_CLIP, S_PONG, S_ERROR, S_STATS = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87
P_HELLO, P_INFO, R_OK, R_START, R_STOP, R_SLOW = 0x02, 0x03, 0x90, 0x91, 0x92, 0x93
PC1, PC2, PC3 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"
UA, UB, UADM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


class FakeSB:
    """Supabase giả: bảng máy PC + 4 hàm SQL v43 mà trạm gọi (cùng tên tham số như file SQL)."""
    def __init__(self):
        self.pcs = {PC1: dict(token="tok-1", name="Máy 14-85", code="14-85", user=UA, approved=True, remote=True, until=None),
                    PC2: dict(token="tok-2", name="Máy 2", code="", user=UB, approved=True, remote=True, until=None),
                    PC3: dict(token="tok-3", name="Máy 3", code="", user=None, approved=False, remote=True, until=None)}
        self.users = {"jwt-a": {"uid": UA, "admin": False}, "jwt-b": {"uid": UB, "admin": False}, "jwt-adm": {"uid": UADM, "admin": True},
                      "jwt-adm1": {"uid": UADM, "admin": False}}            # 21.11l: admin đã bật 2 bước, phiên CHƯA nhập mã → whoami (is_admin()) = false
        self.calls = []; self.remote_on = True; self.nosql = False; self.down = False; self.relay = {}
        self.role_admin = {UADM}; self.mfa = set(); self.v47 = True; self.viewer_bodies = []

    def whoami(self, token): return self.users.get(token)

    def sb(self, method, path, body=None, token=None, timeout=15, extra=None):
        self.calls.append((method, path, body))
        if self.down: raise OSError("mạng đứt")
        if path.startswith("/rest/v1/rpc/pc_relay_") and self.nosql:
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, io.BytesIO(b'{"code":"PGRST202"}'))
        fn = path.rsplit("/", 1)[-1]
        if fn == "pc_relay_auth":
            assert set(body) == {"p_id", "p_token", "p_node", "p_info"}, body
            m = self.pcs.get(body["p_id"])
            if not m or m["token"] != body["p_token"]: return {"ok": False, "err": "BAD_TOKEN"}
            if not self.remote_on or not m["approved"] or not m["remote"]: return {"ok": False, "err": "OFF"}
            self.relay[body["p_id"]] = body["p_node"]; m["info"] = body["p_info"]
            return {"ok": True, "name": m["name"], "code": m["code"], "user_id": m["user"]}
        if fn == "pc_relay_seen":
            assert set(body) == {"p_ids", "p_node"}, body
            return sum(1 for i in body["p_ids"] if self.relay.get(i) == body["p_node"])
        if fn == "pc_relay_gone":
            assert set(body) == {"p_id", "p_node"}, body
            return self.relay.pop(body["p_id"], None) == body["p_node"]
        if fn == "pc_relay_viewer":
            assert set(body) in ({"p_id", "p_uid"}, {"p_id", "p_uid", "p_admin"}), body
            self.viewer_bodies.append(dict(body))
            if "p_admin" in body and not self.v47:                    # Supabase chưa chạy SQL v47: chỉ có hàm cũ 2 tham số
                raise urllib.error.HTTPError(path, 404, "Not Found", {}, io.BytesIO(b'{"code":"PGRST202"}'))
            u = next((x for x in self.users.values() if x["uid"] == body["p_uid"]), None)
            if not u: return {"ok": False, "code": "AUTH", "msg": "Phiên đăng nhập hết hạn, hãy đăng nhập lại."}
            m = self.pcs.get(body["p_id"])
            if not m: return {"ok": False, "code": "NOT_YOURS", "msg": "Không tìm thấy máy PC."}
            ra = body["p_uid"] in self.role_admin                          # như SQL v47: admin = vai admin + (trạm báo p_admin | chưa bật 2 bước); SQL cũ: chỉ vai admin
            adm = ra and (body["p_admin"] is True if "p_admin" in body else (body["p_uid"] not in self.mfa if self.v47 else True))
            u = dict(u, admin=adm)
            if not u["admin"]:
                if m["user"] != u["uid"]: return {"ok": False, "code": "NOT_YOURS", "msg": "Đây không phải máy PC của bạn."}
                if not self.remote_on or not m["approved"] or not m["remote"]: return {"ok": False, "code": "LOCKED", "msg": "Máy PC này chưa bật điều khiển từ xa — liên hệ hỗ trợ."}
                if m["until"] is not None and m["until"] <= time.time(): return {"ok": False, "code": "LOCKED", "msg": "Máy PC đã hết hạn thuê — gia hạn để dùng tiếp."}
            return {"ok": True, "name": m["name"], "code": m["code"], "admin": u["admin"], "owner": m["user"] == u["uid"], "until": m["until"]}
        if fn == "cloudphone_status": return {}
        if path.startswith("/rest/v1/cloud_phones"): return []
        return None

    def n(self, fn): return sum(1 for c in self.calls if c[1].endswith("/" + fn))


class Cli:
    """Máy khách thử nói giao thức BRS2 kiểu nối thẳng (khung [dài u32][loại u8][dữ liệu])."""
    def __init__(self, r, w): self.r, self.w = r, w

    @staticmethod
    async def open(port):
        r, w = await asyncio.open_connection("127.0.0.1", port, limit=1 << 22)
        return Cli(r, w)

    def send(self, t, payload=b""):
        if isinstance(payload, (dict, list)): payload = json.dumps(payload).encode()
        self.w.write(struct.pack(">IB", 1 + len(payload), t) + payload)

    async def recv(self, timeout=3.0, skip=(S_PONG,)):
        """Gói kế tiếp (bỏ PONG giữ chỗ). Hết giờ → None; bên kia đóng → ("EOF", b"")."""
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0: return None
            try:
                n = struct.unpack(">I", await asyncio.wait_for(self.r.readexactly(4), left))[0]
                b = await asyncio.wait_for(self.r.readexactly(n), max(0.5, end - time.time()))
            except asyncio.TimeoutError: return None
            except (asyncio.IncompleteReadError, ConnectionError): return ("EOF", b"")
            if b[0] in skip: continue
            return b[0], b[1:]

    async def want(self, t, timeout=3.0):
        """Chờ tới gói loại t (bỏ qua gói khác) → dữ liệu, hoặc None."""
        end = time.time() + timeout
        while time.time() < end:
            m = await self.recv(end - time.time(), skip=())
            if m is None or m[0] == "EOF": return None
            if m[0] == t: return m[1]
        return None

    async def closed(self, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            m = await self.recv(end - time.time(), skip=())
            if m is not None and m[0] == "EOF": return True
        return False

    def close(self):
        try: self.w.close()
        except Exception: pass


def vid(key, n, size=40):
    return struct.pack(">BQ", 3 if key else 0, n) + bytes([n & 255]) * size


async def source(port, pid=PC1, token="tok-1", **info):
    c = await Cli.open(port)
    c.send(P_HELLO, dict({"v": 1, "pc": pid, "token": token, "ver": "21.12a", "w": 1920, "h": 1080, "enc": "x264"}, **info))
    return c, await c.recv()


async def viewer(port, pid=PC1, token="jwt-a", **kw):
    c = await Cli.open(port)
    c.send(C_HELLO, dict({"v": 2, "token": token, "pc": pid, "client": "web", "ver": "t", "q": "auto"}, **kw))
    return c


async def pair(port, pid=PC1, token="tok-1", vtoken="jwt-a", w=1920, h=1080, **kw):
    """Máy PC + khách đã ghép xong (khách đã nhận WELCOME) → (máy, khách, R_START, WELCOME)."""
    s, ok = await source(port, pid, token)
    assert ok and ok[0] == R_OK, ok
    v = await viewer(port, pid, vtoken, **kw)
    st = json.loads(await s.want(R_START))
    s.send(P_INFO, {"sid": st["sid"], "w": w, "h": h, "fps": 30, "kbps": 4500, "enc": "x264", "q": st["q"]})
    wel = json.loads(await v.want(S_WELCOME))
    return s, v, st, wel


async def main():
    tmp = tempfile.mkdtemp(prefix="cbrelay-")
    H = load(tmp, conf="NODE_ID=wintest\nSUPABASE_URL=http://x\nSUPABASE_SERVICE_KEY=k\n")
    R = H.PCRELAY
    bs_sub = tuple(int(x) for x in re.findall(r"\d+", str(H.BS_SUB))[:2][::-1]) if re.match(r"\d+/\d+", str(H.BS_SUB)) else (0, 0)
    ck("bluestream nạp được pcrelay (trạm BẬT), bản phụ từ 21/11a trở đi", R is not None and bs_sub >= (11, 21) and R.P_HELLO == 0x02 and H.NODE_ID == "wintest",
       (H.BS_SUB, H.PCRELAY_ERR))
    db = FakeSB(); H.sb, H.whoami = db.sb, db.whoami; H.SELFTEST = False
    R.SRC_WAIT_NEW, R.SRC_WAIT_BACK, R.INFO_WAIT_S, R.REAUTH_S, R.BEAT_S = 0.8, 1.2, 1.5, 0.6, 0.4
    srv = await asyncio.start_server(H.on_direct, "127.0.0.1", 0, limit=1 << 20)
    port = srv.sockets[0].getsockname()[1]

    print("1. Phần máy điện thoại không đổi")
    c = await Cli.open(port); c.send(C_HELLO, {"v": 2, "token": "jwt-a", "phone": PC1, "client": "pc"})
    m = await c.recv()
    ck("HELLO không có \"pc\" → vẫn đi đường máy điện thoại (authorize → NOT_YOURS vì bảng máy trống)", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "NOT_YOURS", m)
    ck("… không gọi hàm nào của trạm máy PC", db.n("pc_relay_viewer") == 0 and db.n("pc_relay_auth") == 0)
    c.close()
    c = await Cli.open(port); c.send(0x55, b"x"); ck("gói đầu lạ → đóng kết nối như cũ", await c.closed()); c.close()

    print("2. Máy PC xin vào trạm")
    c = await Cli.open(port); c.send(P_HELLO, b"{khong phai json"); m = await c.recv()
    ck("gói chào hỏng → ERROR BAD, đóng", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "BAD" and await c.closed(), m); c.close()
    c = await Cli.open(port); c.send(P_HELLO, {"pc": "khong-phai-uuid", "token": "x"}); m = await c.recv()
    ck("mã máy không phải UUID → BAD (không hỏi Supabase)", m and json.loads(m[1])["code"] == "BAD" and db.n("pc_relay_auth") == 0, m); c.close()
    c, m = await source(port, PC1, "sai")
    ck("sai mã máy → ERROR AUTH, đóng", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "AUTH" and await c.closed(), m); c.close()
    c, m = await source(port, PC3, "tok-3")
    ck("máy chưa duyệt / tắt điều khiển từ xa → ERROR OFF", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "OFF", m); c.close()
    s, m = await source(port)
    ok = json.loads(m[1]) if m and m[0] == R_OK else {}
    ck("đúng mã → R_OK (tên máy, tên máy chủ, nhịp ping)", ok.get("ok") is True and ok.get("name") == "Máy 14-85" and ok.get("node") == "wintest" and ok.get("ping_s") == 5, m)
    a = next(c[2] for c in db.calls if c[1].endswith("/pc_relay_auth") and c[2]["p_id"] == PC1 and c[2]["p_token"] == "tok-1")
    ck("trạm gọi pc_relay_auth đúng tham số: tên máy chủ + thông số máy đã lọc", a["p_node"] == "wintest" and a["p_info"] == {"w": 1920, "h": 1080, "enc": "x264", "ver": "21.12a"}, a)
    ck("trạm ghi nhận máy đang nối", PC1 in R.SOURCES and db.relay.get(PC1) == "wintest")
    s.send(C_PING, struct.pack(">Q", 123456)); m = await s.recv(skip=())
    ck("máy PC gửi PING → trạm trả PONG đúng số", m == (S_PONG, struct.pack(">Q", 123456)), m)
    await asyncio.sleep(1.0)
    seen = [c[2] for c in db.calls if c[1].endswith("/pc_relay_seen")]
    ck("trạm báo định kỳ 'máy còn nối' (pc_relay_seen) kèm danh sách máy + tên máy chủ", seen and seen[-1] == {"p_ids": [PC1], "p_node": "wintest"}, seen[-2:])

    print("3. Khách mở điều khiển")
    c = await viewer(port, "khong-uuid"); m = await c.recv()
    ck("thiếu / sai mã máy PC → BAD", m and json.loads(m[1])["code"] == "BAD", m); c.close()
    c = await viewer(port, PC1, "jwt-het-han"); m = await c.recv()
    ck("phiên đăng nhập sai → AUTH", m and json.loads(m[1])["code"] == "AUTH", m); c.close()
    c = await viewer(port, PC1, "jwt-b"); m = await c.recv()
    ck("khách KHÁC → NOT_YOURS; máy PC không nhận lệnh bật hình", m and json.loads(m[1])["code"] == "NOT_YOURS" and await s.recv(0.3) is None, m); c.close()
    H.C["PC_PREVIEW"] = "0"
    c = await viewer(port, PC1, "jwt-a", mode="preview"); m = await c.recv()
    ck("PC_PREVIEW=0 trong cloudphone.conf → ô xem trước bị từ chối (PREVIEW_LIMIT) như bản cũ, máy PC không nhận lệnh",
       m and json.loads(m[1])["code"] == "PREVIEW_LIMIT" and await s.recv(0.3) is None, m); c.close()
    H.C.pop("PC_PREVIEW", None)
    c = await viewer(port, PC1, "jwt-b", mode="preview"); m = await c.recv()
    ck("ô xem trước máy của khách KHÁC → NOT_YOURS (kiểm quyền như điều khiển)", m and json.loads(m[1])["code"] == "NOT_YOURS" and await s.recv(0.3) is None, m); c.close()
    c = await viewer(port, PC2, "jwt-b"); m = await c.recv(3)
    ck("máy PC chưa nối vào trạm → chờ ngắn rồi OFFLINE (lời báo kiểm tra máy)", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "OFFLINE" and "chưa nối" in json.loads(m[1])["msg"], m); c.close()

    v = await viewer(port, PC1, "jwt-a", fps=60, maxh=1280, net="c", dl=3000)
    m = await s.recv()
    st = json.loads(m[1]) if m and m[0] == R_START else {}
    ck("chủ máy mở → máy PC nhận R_START (số phiên, chất lượng, khung/giây, cạnh dài, loại mạng, loại đường)", st.get("sid", 0) >= 1 and st.get("q") == "auto" and st.get("fps") == 60
       and st.get("maxh") == 1280 and st.get("net") == "c" and st.get("dl") == 3000 and st.get("client") == "web" and st.get("link") == "direct" and st.get("admin") is False and st.get("owner") is True, m)
    s.send(S_VIDEO, vid(True, 1)); s.send(P_INFO, {"sid": st["sid"] + 7, "w": 800, "h": 600})
    ck("hình + P_INFO của phiên KHÁC (số phiên lệch) → khách chưa nhận gì", await v.recv(0.4) is None)
    s.send(P_INFO, {"sid": st["sid"], "w": 1920, "h": 1080, "fps": 30, "kbps": 4500, "enc": "nvenc", "q": "auto"})
    m = await v.recv()
    wel = json.loads(m[1]) if m and m[0] == S_WELCOME else {}
    ck("P_INFO đúng phiên → khách nhận WELCOME như máy điện thoại (+ kind = pc, số máy)", wel == {"ok": True, "w": 1920, "h": 1080, "fps": 30, "kbps": 4500, "codec": "h264", "enc": "nvenc",
       "name": "Máy 14-85", "android": "pc", "q": "auto", "kind": "pc", "code": "14-85"}, m)
    s.send(S_VIDEO, vid(False, 2)); s.send(S_VIDEO, vid(True, 3)); s.send(S_VIDEO, vid(False, 4))
    m1, m2 = await v.recv(), await v.recv()
    ck("khung đầu tới khách phải là khung khoá (khung thường trước đó bị bỏ), nội dung nguyên vẹn", m1 == (S_VIDEO, vid(True, 3)) and m2 == (S_VIDEO, vid(False, 4)), (m1, m2))

    print("4. Chuột / phím từ khách → máy PC")
    sent = [(C_TOUCH, struct.pack(">BBHH", 0, 0, 100, 200)), (C_MOUSE, struct.pack(">BBHH", 1, 1, 300, 400)), (C_KEY, struct.pack(">BII", 0, 29, 0x1000)),
            (C_TEXT, "xin chào".encode()), (C_SCROLL, struct.pack(">HHhh", 1, 2, 0, -120)), (C_CMD, b'{"cmd":"home"}'), (C_QUALITY, b'{"q":"hd"}'),
            (C_KEYFRAME, b""), (C_CLIP, b"\x01dan chu"), (C_ACK, struct.pack(">Q", 3))]
    for t, p in sent: v.send(t, p)
    got = [await s.recv() for _ in sent]
    ck("10 loại gói điều khiển được chuyển nguyên vẹn, đúng thứ tự", got == sent, got)
    v.send(C_PING, struct.pack(">Q", 9)); m = await v.recv(skip=())
    ck("PING của khách: trạm tự trả lời, không làm phiền máy PC", m == (S_PONG, struct.pack(">Q", 9)) and await s.recv(0.3) is None, m)
    for t, p in ((R_START, b'{"sid":99}'), (R_STOP, b""), (P_HELLO, b"{}"), (P_INFO, b"{}"), (S_VIDEO, vid(True, 9)), (0x7F, b"x"), (C_TOUCH, b"\x00"), (C_KEY, b"123"), (C_CLIP, b"")):
        v.send(t, p)
    ck("khách KHÔNG giả được lệnh của trạm (R_START / R_STOP…), gói lạ / sai cỡ bị bỏ", await s.recv(0.4) is None)
    v.send(C_TEXT, b"a" * (64 * 1024 + 1)); v.send(C_TEXT, b"b" * 1000)
    m = await s.recv()
    ck("chữ dài quá 64 KB bị bỏ, gói kế vẫn tới", m == (C_TEXT, b"b" * 1000), m and (m[0], len(m[1])))

    print("5. Gói khác từ máy PC → khách")
    s.send(S_STATS, {"fps": 29.5, "kbps": 4100, "drop": 2, "enc": "nvenc", "q": "auto", "w": 1920, "h": 1080, "lag": 40}); m = await v.recv()
    stt = json.loads(m[1]) if m and m[0] == S_STATS else {}
    ck("số liệu của máy PC tới khách, số khung bỏ = máy bỏ + trạm bỏ", stt.get("fps") == 29.5 and stt.get("drop") == 2 + 1 and stt.get("enc") == "nvenc", m)
    s.send(S_CLIP, "chữ vừa copy trên máy PC".encode()); m = await v.recv()
    ck("chữ copy trên máy PC → khách", m == (S_CLIP, "chữ vừa copy trên máy PC".encode()), m)
    s.send(P_INFO, {"sid": st["sid"], "w": 1280, "h": 720, "fps": 30, "kbps": 2000, "enc": "nvenc"}); m = await v.recv()
    ck("máy PC đổi cỡ hình (đổi chất lượng / độ phân giải) → khách nhận SIZE", m == (S_SIZE, b'{"w": 1280, "h": 720}'), m)
    s.send(S_VIDEO, vid(False, 10)); s.send(S_VIDEO, vid(True, 11)); m = await v.recv()
    ck("sau khi đổi cỡ: lại chờ khung khoá", m == (S_VIDEO, vid(True, 11)), m)
    s.send(P_INFO, {"sid": st["sid"], "w": 1280, "h": 720, "fps": 30, "kbps": 1400, "enc": "nvenc"}); s.send(S_VIDEO, vid(True, 12)); m = await v.recv()
    ck("máy PC bật lại bộ nén cùng cỡ hình (hạ bitrate) → không gửi SIZE, phát tiếp từ khung khoá", m == (S_VIDEO, vid(True, 12)), m)

    print("6. Đóng phiên")
    v.send(C_BYE); m = await s.recv()
    ck("khách đóng → máy PC nhận R_STOP (tắt bộ quay)", m == (R_STOP, b""), m)
    ck("… khách bị đóng kết nối, trạm hết người xem", await v.closed() and PC1 not in R.VIEWERS and R.SOURCES[PC1].viewer is None); v.close()
    s.send(S_VIDEO, vid(True, 20)); s.send(S_VIDEO, vid(False, 21))
    await asyncio.sleep(3.2); s.send(S_VIDEO, vid(False, 22))
    m = await s.recv(1.5)
    ck("không ai xem mà máy vẫn gửi hình → trạm nhắc R_STOP (3 giây 1 lần)", m == (R_STOP, b""), m)

    print("7. Người mở sau đá người mở trước · admin")
    v1 = await viewer(port, PC1, "jwt-a"); st1 = json.loads(await s.want(R_START))
    s.send(P_INFO, {"sid": st1["sid"], "w": 1920, "h": 1080}); await v1.want(S_WELCOME)
    v2 = await viewer(port, PC1, "jwt-adm")
    m = await v1.recv()
    ck("người đang xem nhận KICKED", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "KICKED" and await v1.closed(), m); v1.close()
    m1, m2 = await s.recv(), await s.recv()
    st2 = json.loads(m2[1]) if m2 and m2[0] == R_START else {}
    ck("máy PC nhận R_STOP rồi R_START phiên mới (số phiên tăng, admin = true)", m1 == (R_STOP, b"") and st2.get("sid", 0) > st1["sid"] and st2.get("admin") is True and st2.get("owner") is False, (m1, m2))
    s.send(S_VIDEO, vid(True, 30)); s.send(P_INFO, {"sid": st1["sid"], "w": 640, "h": 480})
    ck("hình / P_INFO của phiên CŨ không lọt sang người mới", await v2.recv(0.4) is None)
    s.send(P_INFO, {"sid": st2["sid"], "w": 1920, "h": 1080}); s.send(S_VIDEO, vid(True, 31))
    wel = json.loads(await v2.want(S_WELCOME)); m = await v2.recv()
    ck("admin mở được máy của khách (WELCOME + hình)", wel["name"] == "Máy 14-85" and m == (S_VIDEO, vid(True, 31)), m)

    print("8. Máy PC nối lại / mất kết nối trong lúc khách đang xem")
    s_new, m = await source(port, PC1, "tok-1", w=1280, h=720)
    ck("chính máy đó nối lại bằng kết nối mới → kết nối cũ bị đóng", m and m[0] == R_OK and await s.closed(), m); s.close()
    m = await s_new.recv()
    st3 = json.loads(m[1]) if m and m[0] == R_START else {}
    ck("khách đang xem được chuyển sang kết nối mới (máy nhận R_START)", st3.get("sid", 0) >= 1, m)
    ck("… trạm KHÔNG báo 'máy đã rời' (bản ghi mới đang đúng)", db.n("pc_relay_gone") == 0 and db.relay.get(PC1) == "wintest")
    s_new.send(P_INFO, {"sid": st3["sid"], "w": 1280, "h": 720}); s_new.send(S_VIDEO, vid(False, 40)); s_new.send(S_VIDEO, vid(True, 41))
    m1, m2 = await v2.recv(), await v2.recv()
    ck("khách không bị đá: nhận SIZE mới rồi khung khoá", m1 == (S_SIZE, b'{"w": 1280, "h": 720}') and m2 == (S_VIDEO, vid(True, 41)), (m1, m2))
    s_new.close()
    m = await v2.recv(4)
    ck("máy PC mất hẳn kết nối → khách được giữ chờ rồi nhận OFFLINE", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "OFFLINE" and "mất kết nối" in json.loads(m[1])["msg"], m); v2.close()
    await asyncio.sleep(0.3)
    ck("… trạm báo Supabase 'máy đã rời' (pc_relay_gone)", db.n("pc_relay_gone") == 1 and PC1 not in db.relay and PC1 not in R.SOURCES)
    s, v, st, wel = await pair(port)
    s.send(S_ERROR, {"code": "OFFLINE", "msg": "Máy PC không quay được màn hình (chưa có ai đăng nhập Windows)."}); m = await v.recv()
    ck("máy PC báo không phát được hình → khách nhận đúng lời báo, phiên đóng, máy nhận R_STOP",
       m and m[0] == S_ERROR and "không quay được màn hình" in json.loads(m[1])["msg"] and await s.want(R_STOP) is not None, m); v.close()
    v = await viewer(port, PC1, "jwt-a"); await s.want(R_START); m = await v.recv(4)
    ck("máy PC nhận lệnh mà không gửi P_INFO → khách nhận OFFLINE (bộ quay chưa chạy)", m and m[0] == S_ERROR and "bộ quay" in json.loads(m[1])["msg"], m); v.close()
    await s.want(R_STOP)

    print("9. Kiểm lại quyền trong lúc đang xem")
    v = await viewer(port, PC1, "jwt-a"); stx = json.loads(await s.want(R_START)); s.send(P_INFO, {"sid": stx["sid"], "w": 1920, "h": 1080}); await v.want(S_WELCOME)
    db.pcs[PC1]["user"] = UB                                         # admin chuyển máy cho khách khác
    m = await v.want(S_ERROR, 3)
    ck("admin bỏ gán / chuyển máy → phiên đang mở bị ngắt (NOT_YOURS)", m and json.loads(m)["code"] == "NOT_YOURS", m); v.close()
    db.pcs[PC1]["user"] = UA; await s.want(R_STOP)
    db.pcs[PC1]["until"] = time.time() + 1.0
    v = await viewer(port, PC1, "jwt-a"); stx = json.loads(await s.want(R_START)); s.send(P_INFO, {"sid": stx["sid"], "w": 1920, "h": 1080}); await v.want(S_WELCOME)
    n0 = db.n("pc_relay_viewer"); db.down = True                     # Supabase đứt mạng: trạm vẫn tự cắt đúng giờ hết hạn
    m = await v.want(S_ERROR, 3)
    ck("tới giờ hết hạn thuê → trạm tự ngắt (LOCKED) kể cả khi không hỏi được Supabase", m and json.loads(m)["code"] == "LOCKED" and "hết hạn" in json.loads(m)["msg"], m); v.close()
    db.down = False; db.pcs[PC1]["until"] = None; await s.want(R_STOP)
    v = await viewer(port, PC1, "jwt-a"); stx = json.loads(await s.want(R_START)); s.send(P_INFO, {"sid": stx["sid"], "w": 1920, "h": 1080}); await v.want(S_WELCOME)
    db.down = True; await asyncio.sleep(1.6); s.send(S_VIDEO, vid(True, 50)); m = await v.recv()
    ck("Supabase đứt mạng lúc kiểm lại → KHÔNG ngắt oan khách đang xem", m == (S_VIDEO, vid(True, 50)), m)
    db.down = False; v.send(C_BYE); await s.want(R_STOP); v.close()

    print("10. Chưa chạy SQL v43 / chặn dò mã")
    db.nosql = True
    c = await viewer(port, PC1, "jwt-a"); m = await c.recv()
    ck("Supabase chưa có hàm v43 → khách nhận OFFLINE 'chưa bật điều khiển máy PC'", m and json.loads(m[1])["code"] == "OFFLINE" and "chưa bật" in json.loads(m[1])["msg"], m); c.close()
    c, m = await source(port, PC2, "tok-2")
    ck("… máy PC nhận BUSY (thử lại sau), nhật ký ghi rõ chưa chạy cloud-pc-v43.sql", m and json.loads(m[1])["code"] == "BUSY" and any("cloud-pc-v43.sql" in x for x in LOGS), m); c.close()
    db.nosql = False
    R._FAILS.clear(); n0 = db.n("pc_relay_auth")
    c, m = await source(port, PC2, "do-ma"); c.close()
    ck("kết nối từ chính máy chủ (127.0.0.1, không rõ IP khách) → không tính theo IP, chỉ tính theo máy bị dò", list(R._FAILS) == ["s:|" + PC2], list(R._FAILS))
    R._FAILS.clear()
    real_peer = R._peer; R._peer = lambda link: "198.51.100.7"       # giả: mọi kết nối thử tới từ 1 IP ngoài
    for _ in range(R.FAIL_MAX):
        c, m = await source(port, PC2, "do-ma"); c.close()
    c, m = await source(port, PC2, "do-ma")
    ck("1 IP sai mã CÙNG 1 máy 12 lần → lần sau bị từ chối luôn (BUSY), không hỏi Supabase nữa", m and json.loads(m[1])["code"] == "BUSY" and db.n("pc_relay_auth") == n0 + 1 + R.FAIL_MAX, (m, db.n("pc_relay_auth") - n0)); c.close()
    c, m = await source(port, PC2, "tok-2")
    ck("… trong lúc bị chặn, mã ĐÚNG của máy đó từ IP đó cũng phải chờ (chống dò)", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "BUSY", m); c.close()
    c, m = await source(port, PC1, "tok-1")
    ck("… máy KHÁC cùng IP (cùng phòng máy) vẫn vào được — 1 máy hỏng mã không chặn cả phòng", m and m[0] == R_OK, m)
    s_old, s = s, c
    ck("    (kết nối cũ của máy đó bị thay)", await s_old.closed()); s_old.close()
    for i in range(R.FAIL_IP):
        R._fail("s:198.51.100.7")
    c, m = await source(port, PC3, "x")
    ck("1 IP sai mã quá 120 lần (dò nhiều máy) → chặn cả IP đó 10 phút", m and json.loads(m[1])["code"] == "BUSY", m); c.close()
    R._peer = real_peer; R._FAILS.clear()
    ck("khoá chặn có hạn 10 phút và tính riêng máy PC / khách", R._blocked("s:1.2.3.4") is False and [R._fail("s:1.2.3.4", now=1000.0) for _ in range(12)] and R._blocked("s:1.2.3.4", now=1100.0) is True
       and R._blocked("v:1.2.3.4", R.FAIL_VIEW, now=1100.0) is False and R._blocked("s:1.2.3.4", now=1000.0 + 601) is False and R._blocked("s:") is False)

    print("10b. Xác minh 2 bước (21.11l): quyền admin trên trạm theo is_admin() của CHÍNH phiên người xem")
    db.mfa.add(UADM)
    s2, ok2 = await source(port, PC2, "tok-2")
    ck("(chuẩn bị) máy PC2 vào trạm", ok2 and ok2[0] == R_OK, ok2)
    n0 = len(db.viewer_bodies)
    c = await viewer(port, PC2, "jwt-adm1"); m = await c.recv()
    ck("admin đã bật 2 bước mà phiên chưa nhập mã (whoami: admin = false) → KHÔNG mở được máy của khách", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "NOT_YOURS", m); c.close()
    ck("… trạm báo kèm p_admin = false cho Supabase", db.viewer_bodies[n0:n0 + 1] and db.viewer_bodies[n0].get("p_admin") is False, db.viewer_bodies[n0:])
    c = await viewer(port, PC2, "jwt-adm"); st = json.loads(await s2.want(R_START) or b"{}")
    ck("admin đã nhập mã (whoami: admin = true) → mở được, trạm báo p_admin = true", st.get("admin") is True and db.viewer_bodies[-1].get("p_admin") is True, (st, db.viewer_bodies[-1:]))
    c.close(); await s2.want(R_STOP, 2)
    db.v47 = False; n0 = len(db.viewer_bodies)
    c = await viewer(port, PC2, "jwt-adm"); st = json.loads(await s2.want(R_START) or b"{}")
    ck("Supabase chưa chạy SQL v47 (hàm cũ 2 tham số) → trạm tự hỏi lại kiểu cũ, vẫn mở được như trước",
       st.get("admin") is True and [sorted(b) for b in db.viewer_bodies[n0:n0 + 2]] == [["p_admin", "p_id", "p_uid"], ["p_id", "p_uid"]], db.viewer_bodies[n0:])
    c.close(); await s2.want(R_STOP, 2); s2.close(); db.v47 = True; db.mfa.discard(UADM)
    await asyncio.sleep(0.3)

    print("11. Khách nhận chậm → bỏ khung, không dồn trễ")
    R._FAILS.clear()
    v = await viewer(port, PC1, "jwt-a"); stx = json.loads(await s.want(R_START)); s.send(P_INFO, {"sid": stx["sid"], "w": 1920, "h": 1080}); await v.want(S_WELCOME)
    big = 60 * 1024; n = 0
    for i in range(400):                                             # khách KHÔNG đọc: 24 MB hình dồn tới
        s.send(S_VIDEO, vid(i % 30 == 0, 1000 + i, big)); n += 1
        if i % 20 == 19: await s.w.drain(); await asyncio.sleep(0.02)
    await s.w.drain(); await asyncio.sleep(0.5)
    vw = R.VIEWERS.get(PC1)
    ck("trạm bỏ khung thay vì giữ hết trong bộ nhớ", vw is not None and vw.drop > 100 and R._buf(vw.link) < 4 * 1024 * 1024, vw and (vw.drop, vw.sent, R._buf(vw.link)))
    m = await s.want(R_SLOW, 2)
    ck("trạm báo máy PC 'khách nhận chậm' (R_SLOW) để máy tự hạ bitrate", m is not None and json.loads(m).get("n", 0) >= 1, m)
    frames = []
    while True:                                                      # khách đọc lại: sau mỗi chỗ bị bỏ khung, khung kế PHẢI là khung khoá
        m = await v.recv(0.6)
        if m is None or m[0] == "EOF": break
        if m[0] == S_VIDEO: frames.append((struct.unpack(">Q", m[1][1:9])[0], m[1][0] & 1))
    gaps_ok = all(k == 1 for (a, _), (b, k) in zip(frames, frames[1:]) if b != a + 1)
    ck("khách đọc lại: sau mỗi quãng bị bỏ, khung kế luôn là khung khoá (không hình vỡ)", len(frames) >= 3 and frames[0][1] == 1 and gaps_ok and len(frames) < n, (len(frames), frames[:6]))
    s.send(S_VIDEO, vid(True, 2000)); s.send(S_VIDEO, vid(False, 2001))
    m1, m2 = await v.recv(), await v.recv()
    ck("hết nghẽn → hình chạy lại bình thường", m1 == (S_VIDEO, vid(True, 2000)) and m2 == (S_VIDEO, vid(False, 2001)), (m1 and m1[0], m2 and m2[0]))
    v.send(C_BYE); await s.want(R_STOP); v.close()

    print("11b. Ô xem trước máy PC (22/11b · ▦ Xem tất cả VPS GPU)")
    ck("bản trạm 22/11b, bật ô xem trước", R.PCRELAY_VER == "22/11b" and R.PEEK is True and R._peek_on(H))
    p1 = await viewer(port, PC1, "jwt-a", mode="preview", maxh=400, client="pc")
    m = await s.recv()
    pv = json.loads(m[1]) if m and m[0] == R_START else {}
    ck("không ai điều khiển → máy PC nhận R_START luồng NHỎ (eco, 8 khung/giây, cạnh dài theo app, ~350 kbps, chủ máy, đánh dấu preview)",
       pv.get("q") == "eco" and pv.get("fps") == 8 and pv.get("maxh") == 400 and pv.get("kbps") == 350 and pv.get("preview") is True
       and pv.get("owner") is True and pv.get("admin") is False and pv.get("client") == "preview", m)
    s.send(P_INFO, {"sid": pv["sid"], "w": 400, "h": 226, "fps": 8, "kbps": 350, "enc": "nvenc", "q": "eco"})
    m = await p1.recv()
    w1 = json.loads(m[1]) if m and m[0] == S_WELCOME else {}
    ck("ô nhận WELCOME (preview = true, kind = pc, cỡ luồng nhỏ)", w1.get("preview") is True and w1.get("kind") == "pc" and w1.get("w") == 400
       and w1.get("q") == "preview" and w1.get("name") == "Máy 14-85", m)
    s.send(S_VIDEO, vid(False, 300)); s.send(S_VIDEO, vid(True, 301)); s.send(S_VIDEO, vid(False, 302))
    m1, m2 = await p1.recv(), await p1.recv()
    ck("luồng nhỏ: ô nhận đủ khung, bắt đầu từ khung khoá", m1 == (S_VIDEO, vid(True, 301)) and m2 == (S_VIDEO, vid(False, 302)), (m1, m2))
    for t, pl in ((C_TOUCH, struct.pack(">BBHH", 0, 0, 1, 1)), (C_MOUSE, struct.pack(">BBHH", 1, 1, 5, 5)), (C_KEY, struct.pack(">BII", 0, 29, 0)),
                  (C_TEXT, b"abc"), (C_CMD, b'{"cmd":"home"}'), (C_QUALITY, b'{"q":"hd"}'), (C_KEYFRAME, b""), (C_CLIP, b"\x01x"), (C_ACK, struct.pack(">Q", 302))):
        p1.send(t, pl)
    ck("ô xem trước CHỈ XEM: chuột / phím / chữ / chất lượng / xin khung khoá / ACK đều KHÔNG tới máy PC", await s.recv(0.5) is None)
    p1.send(C_PING, struct.pack(">Q", 77)); m = await p1.recv(skip=())
    ck("… PING của ô vẫn được trạm trả lời", m == (S_PONG, struct.pack(">Q", 77)), m)
    p2 = await viewer(port, PC1, "jwt-a", mode="preview", maxh=300, client="android")
    m = await p2.recv()
    w2 = json.loads(m[1]) if m and m[0] == S_WELCOME else {}
    ck("ô thứ 2 (máy khác của khách) dùng chung luồng nhỏ đang phát: WELCOME ngay, máy PC không bị bật lại", w2.get("preview") is True and w2.get("w") == 400
       and await s.recv(0.4) is None, (m, w2))
    s.send(S_VIDEO, vid(False, 303)); s.send(S_VIDEO, vid(True, 304))
    m1, m2 = await p2.recv(), await p1.recv()
    ck("… ô mới chờ khung khoá, ô cũ nhận tiếp đủ khung", m1 == (S_VIDEO, vid(True, 304)) and m2 == (S_VIDEO, vid(False, 303)), (m1, m2))
    await p1.recv()
    v = await viewer(port, PC1, "jwt-a", fps=60)
    m = await s.recv()
    ctl = json.loads(m[1]) if m and m[0] == R_START else {}
    ck("chủ máy mở ĐIỀU KHIỂN trong lúc có ô xem trước → máy PC nhận R_START phiên điều khiển (chất lượng của khách, không còn preview)",
       ctl.get("sid", 0) > pv["sid"] and ctl.get("q") == "auto" and ctl.get("fps") == 60 and not ctl.get("preview"), m)
    ck("… ô xem trước KHÔNG bị đá (không ERROR)", await p1.recv(0.3) is None and await p2.recv(0.2) is None)
    s.send(S_VIDEO, vid(True, 305))
    ck("hình của luồng nhỏ cũ (trước P_INFO phiên mới) không lọt tới ô / người điều khiển", await p1.recv(0.3) is None and await v.recv(0.2) is None)
    s.send(P_INFO, {"sid": ctl["sid"], "w": 1920, "h": 1080, "fps": 60, "kbps": 9000, "enc": "nvenc", "q": "auto"})
    wel = json.loads(await v.want(S_WELCOME) or b"{}")
    ck("người điều khiển nhận WELCOME bình thường", wel.get("w") == 1920 and wel.get("kind") == "pc" and not wel.get("preview"), wel)
    ck("… ô xem trước không nhận WELCOME / SIZE lần nữa", await p1.recv(0.3) is None)
    for i, k in enumerate((True, False, False, True, False)): s.send(S_VIDEO, vid(k, 310 + i))
    got_v = [await v.recv() for _ in range(5)]
    got_p = []
    while True:
        m = await p1.recv(0.4)
        if m is None: break
        got_p.append(m)
    ck("người điều khiển nhận đủ 5 khung", got_v == [(S_VIDEO, vid(k, 310 + i)) for i, k in enumerate((True, False, False, True, False))], [x and x[0] for x in got_v])
    ck("… ô xem trước chỉ nhận KHUNG KHOÁ thưa (khung khoá thứ 2 trong vòng 2 giây bị bỏ) → máy PC không phải nén thêm luồng",
       got_p == [(S_VIDEO, vid(True, 310))], got_p)
    while await p2.recv(0.2) is not None: pass
    await asyncio.sleep(R.PV_KEY_GAP + 0.1)
    for c_ in (p1, p2, v): c_.send(C_PING, struct.pack(">Q", 1))
    s.send(S_VIDEO, vid(False, 320)); s.send(S_VIDEO, vid(True, 321))
    m = await p1.want(S_VIDEO)
    ck("… quá 2 giây → khung khoá kế tới ô", m == vid(True, 321), m)
    v.send(C_TOUCH, struct.pack(">BBHH", 0, 0, 9, 9)); m = await s.recv()
    ck("chuột của người điều khiển vẫn tới máy PC bình thường", m == (C_TOUCH, struct.pack(">BBHH", 0, 0, 9, 9)), m)
    adm = await viewer(port, PC1, "jwt-adm")
    m = await v.want(S_ERROR, 3)
    ck("admin mở điều khiển → người điều khiển cũ bị đá (KICKED) như trước", m and json.loads(m)["code"] == "KICKED", m); v.close()
    m1, m2 = await s.recv(), await s.recv()
    st_a = json.loads(m2[1]) if m2 and m2[0] == R_START else {}
    ck("… máy PC nhận R_STOP rồi R_START phiên của admin — KHÔNG bật luồng nhỏ xen giữa", m1 == (R_STOP, b"") and st_a.get("admin") is True and not st_a.get("preview")
       and await s.recv(0.6) is None, (m1, m2))
    ck("… ô xem trước vẫn mở", await p1.recv(0.2) is None and not p1.w.is_closing())
    s.send(P_INFO, {"sid": st_a["sid"], "w": 1920, "h": 1080}); await adm.want(S_WELCOME)
    adm.send(C_BYE)
    m = await s.recv()
    pv2 = json.loads(m[1]) if m and m[0] == R_START else {}
    ck("người điều khiển đóng mà còn ô xem trước → máy PC chuyển về luồng nhỏ (R_START preview), KHÔNG tắt bộ quay",
       pv2.get("preview") is True and pv2.get("sid", 0) > st_a["sid"] and pv2.get("maxh") == 400, m); adm.close()
    s.send(P_INFO, {"sid": pv2["sid"], "w": 400, "h": 226, "fps": 8}); s.send(S_VIDEO, vid(False, 330)); s.send(S_VIDEO, vid(True, 331)); s.send(S_VIDEO, vid(False, 332))
    m1, m2 = await p1.want(S_VIDEO), await p1.want(S_VIDEO)
    ck("… ô nhận lại đủ khung của luồng nhỏ (từ khung khoá)", m1 == vid(True, 331) and m2 == vid(False, 332), (m1, m2))
    R.PV_PER_SRC = 2
    p3 = await viewer(port, PC1, "jwt-a", mode="preview"); m = await p3.want(S_ERROR, 3)
    ck("quá số ô xem trước của 1 máy → PV_FULL (lời báo rõ ràng), các ô khác không ảnh hưởng", m and json.loads(m)["code"] == "PV_FULL" and await p1.recv(0.2) is None, m); p3.close()
    R.PV_PER_SRC = 6
    p2.send(C_BYE); await asyncio.sleep(0.3)
    ck("1 ô đóng, còn ô khác → máy PC vẫn phát (không R_STOP)", await s.recv(0.4) is None)
    p1.send(C_BYE); m = await s.recv(2)
    ck("ô cuối cùng đóng, không ai điều khiển → máy PC nhận R_STOP (tắt bộ quay)", m == (R_STOP, b""), m)
    p1.close(); p2.close(); await asyncio.sleep(0.2)
    ck("… trạm không còn ô nào", not R.PEEKS and not R.SOURCES[PC1].peeks and R.SOURCES[PC1].pv_on is False)
    p1 = await viewer(port, PC1, "jwt-a", mode="preview")
    pv3 = json.loads(await s.want(R_START) or b"{}")
    s.send(S_ERROR, {"code": "OFFLINE", "msg": "Máy PC đang chuẩn bị bộ quay màn hình (lần đầu mất 1–2 phút) — thử lại sau ít phút."})
    m = await p1.want(S_ERROR, 3)
    ck("máy PC báo chưa bật được luồng nhỏ → ô nhận đúng lời báo của máy", pv3.get("preview") is True and m and "chuẩn bị bộ quay" in json.loads(m)["msg"], m)
    m = await s.recv()
    ck("… máy PC nhận R_STOP (dọn phiên hỏng)", m == (R_STOP, b""), m)
    p1.close(); await asyncio.sleep(0.3)
    p1 = await viewer(port, PC1, "jwt-a", mode="preview"); m = await p1.want(S_ERROR, 3)
    ck("mở ô khác ngay sau đó → báo luôn lời của máy, trạm KHÔNG xin lại máy PC liên tục", m and "chuẩn bị bộ quay" in json.loads(m)["msg"] and await s.recv(0.5) is None, m)
    p1.close(); await asyncio.sleep(0.3)
    R.SOURCES[PC1].t_pvfail = 0.0
    while await s.recv(0.3) is not None: pass
    p1 = await viewer(port, PC1, "jwt-a", mode="preview"); pv4 = json.loads(await s.want(R_START) or b"{}")
    s.send(P_INFO, {"sid": pv4["sid"], "w": 400, "h": 226}); await p1.want(S_WELCOME)
    db.pcs[PC1]["user"] = UB
    m = await p1.want(S_ERROR, 3)
    ck("admin chuyển máy cho khách khác → ô xem trước đang mở bị ngắt (NOT_YOURS)", m and json.loads(m)["code"] == "NOT_YOURS", m); p1.close()
    db.pcs[PC1]["user"] = UA
    m = await s.want(R_STOP, 2)
    ck("… máy PC nhận R_STOP", m is not None, m)
    c = await viewer(port, PC2, "jwt-b", mode="preview"); m = await c.want(S_ERROR, 3)
    ck("ô xem trước máy PC chưa nối vào trạm → OFFLINE (máy đang tắt / khởi động)", m and json.loads(m)["code"] == "OFFLINE" and "chưa nối" in json.loads(m)["msg"], m); c.close()
    R.PV_MAX = 0
    c = await viewer(port, PC1, "jwt-a", mode="preview"); m = await c.recv()
    ck("trạm đầy ô xem trước → PV_FULL, không hỏi Supabase", m and json.loads(m[1])["code"] == "PV_FULL", m); c.close()
    R.PV_MAX = 300
    await asyncio.sleep(0.3)

    print("12. Giới hạn số máy · đường vòng Cloudflare · báo web")
    R.MAX_SOURCES = 1
    c, m = await source(port, PC2, "tok-2")
    ck("trạm đầy → máy mới nhận BUSY; máy đang nối vẫn nối lại được", m and json.loads(m[1])["code"] == "BUSY", m); c.close()
    R.MAX_SOURCES = 400
    srv2 = await asyncio.start_server(H.on_ws, "127.0.0.1", 0, limit=1 << 20)
    port2 = srv2.sockets[0].getsockname()[1]
    r, w = await asyncio.open_connection("127.0.0.1", port2)
    key = base64.b64encode(os.urandom(16)).decode()
    w.write((f"GET /v2/stream HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
             "User-Agent: CloudBluePC-remote/21.12a\r\nCF-Connecting-IP: 203.0.113.9\r\n\r\n").encode())
    head = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), 3)

    def wsframe(t, payload):
        d = bytes([t]) + payload; mk = os.urandom(4); n_ = len(d)
        hdr = bytes([0x82]) + (bytes([0x80 | n_]) if n_ < 126 else bytes([0x80 | 126]) + struct.pack(">H", n_))
        return hdr + mk + bytes(b ^ mk[i % 4] for i, b in enumerate(d))
    w.write(wsframe(P_HELLO, json.dumps({"pc": PC2, "token": "sai-ma"}).encode()))
    b0 = await asyncio.wait_for(r.readexactly(2), 3); body = await asyncio.wait_for(r.readexactly(b0[1] & 0x7F), 3)
    ck("máy PC đi đường vòng Cloudflare (WebSocket) cũng vào được trạm (sai mã → ERROR AUTH)", b" 101 " in head and body[0] == S_ERROR and json.loads(body[1:])["code"] == "AUTH", (head[:40], body))
    ck("… lần sai tính cho IP khách do Cloudflare ghi, không tính chung cả đường vòng", "s:203.0.113.9" in R._FAILS and "s:" not in R._FAILS and "s:127.0.0.1" not in R._FAILS, list(R._FAILS))
    w.close(); srv2.close()

    class Stop(Exception): pass
    pub = []
    def fake_sb(method, path, body=None, **kw): pub.append((method, path, body)); return None
    def fake_sleep(x): raise Stop()
    H.sb = fake_sb; H.lan_ip = lambda: "192.168.1.6"; H.public_ip = lambda: "1.2.3.4"; H.web_url = lambda p=None: None
    real_sleep = H.time.sleep; H.time.sleep = fake_sleep
    try: H.publish_loop("ab" * 32)
    except Stop: pass
    finally: H.time.sleep = real_sleep
    ck("máy chủ báo lên web: stream.pc = 1 (SQL v43 chỉ giao máy PC cho máy chủ có cờ này), các trường cũ giữ nguyên",
       pub and pub[0][0] == "PATCH" and pub[0][1].endswith("cloud_nodes?id=eq.wintest") and pub[0][2]["stream"].get("pc") == 1
       and pub[0][2]["stream"]["preview"] == 1 and pub[0][2]["stream"]["cert"] == "ab" * 32 and len(pub[0][2]["stream"]["direct"]) == 2, pub)
    H.sb = db.sb
    s.close(); srv.close()
    await asyncio.sleep(0.3)

    print("13. Tắt trạm / thiếu file pcrelay.py → phần máy điện thoại vẫn chạy")
    tmp2 = tempfile.mkdtemp(prefix="cbrelay-")
    H2 = load(tmp2, conf="NODE_ID=w2\nPC_RELAY=0\n")
    ck("PC_RELAY=0 → trạm tắt", H2.PCRELAY is None and H2.PCRELAY_ERR == "PC_RELAY=0")
    db2 = FakeSB(); H2.sb, H2.whoami = db2.sb, db2.whoami
    srv = await asyncio.start_server(H2.on_direct, "127.0.0.1", 0); port = srv.sockets[0].getsockname()[1]
    c, m = await source(port)
    ck("… máy PC gửi P_HELLO → máy chủ đóng kết nối (như gói lạ), không hỏi Supabase", (m is None or m[0] == "EOF") and db2.n("pc_relay_auth") == 0, m); c.close()
    pub.clear(); H2.sb = fake_sb; H2.lan_ip = lambda: "192.168.1.6"; H2.public_ip = lambda: None; H2.web_url = lambda p=None: None; H2.time.sleep = fake_sleep
    try: H2.publish_loop("cd" * 32)
    except Stop: pass
    finally: H2.time.sleep = real_sleep
    ck("… không báo stream.pc lên web (máy PC không bị giao về máy chủ này)", pub and "pc" not in pub[0][2]["stream"], pub)
    srv.close()
    tmp3 = tempfile.mkdtemp(prefix="cbrelay-")
    H3 = load(tmp3, with_relay=False, conf="NODE_ID=w3\n")
    ck("thiếu file pcrelay.py → bluestream vẫn nạp được, trạm tắt, ghi rõ lý do", H3.PCRELAY is None and "thiếu file pcrelay.py" in H3.PCRELAY_ERR, H3.PCRELAY_ERR)
    db3 = FakeSB(); H3.sb, H3.whoami = db3.sb, db3.whoami
    srv = await asyncio.start_server(H3.on_direct, "127.0.0.1", 0); port = srv.sockets[0].getsockname()[1]
    c = await Cli.open(port); c.send(C_HELLO, {"v": 2, "token": "jwt-a", "phone": PC1, "pc": PC1}); m = await c.recv()
    ck("… HELLO có \"pc\" được xử lý như máy điện thoại (bản cũ): NOT_YOURS", m and m[0] == S_ERROR and json.loads(m[1])["code"] == "NOT_YOURS", m); c.close(); srv.close()
    open(os.path.join(tmp3, "pcrelay.py"), "w").write("def loi(:\n")
    for mname in ("bluestream", "pcrelay"): sys.modules.pop(mname, None)
    sys.path.insert(0, tmp3); H4 = importlib.import_module("bluestream")
    ck("file pcrelay.py hỏng (lỗi cú pháp) → bluestream VẪN chạy, trạm tắt", H4.PCRELAY is None and "SyntaxError" in H4.PCRELAY_ERR, H4.PCRELAY_ERR)
    for d in (tmp, tmp2, tmp3): shutil.rmtree(d, ignore_errors=True)


asyncio.run(main())
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
