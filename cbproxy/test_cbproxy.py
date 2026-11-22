# -*- coding: utf-8 -*-
"""Bộ thử cbproxy trên Linux THẬT với iptables THẬT, trong 1 không gian mạng riêng (unshare -n) — không đụng mạng của máy chạy thử.
   Dựng: "web" 203.0.113.5 (+ 1.1.1.1 trả /cdn-cgi/trace), proxy SOCKS5 + HTTP 198.51.100.7 (đi ra bằng IP 198.51.100.8).
   App thường nối 203.0.113.5 → iptables → cbproxy → proxy → web: web thấy IP 198.51.100.8 = đã qua proxy; thấy 203.0.113.5 = đi thẳng.
   Chạy (root):  python3 test_cbproxy.py [đường dẫn cbproxy-x86_64]"""
import base64, json, os, select, socket, socketserver, struct, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(HERE, "cbproxy-x86_64")
if "--inner" not in sys.argv:
    r = subprocess.run(["unshare", "-n", sys.executable, os.path.abspath(__file__), BIN, "--inner"])
    sys.exit(r.returncode)

MARK = 0x40000000
WEB, TRACE, PX, PX_OUT = "203.0.113.5", "1.1.1.1", "198.51.100.7", "198.51.100.8"
USER, PASS = "khach", "mk:2@x"
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:600], flush=True)


def sh(*a, check=False):
    r = subprocess.run(list(a), capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError(" ".join(a) + ": " + r.stderr)
    return r


def wait(fn, t=10.0, step=0.1):
    end = time.time() + t
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(step)
    return fn()


def ifaddr(name, ip):
    """Như 'ifconfig lo:N IP netmask 255.255.255.255 up' (máy thử không có lệnh ip): ioctl SIOCSIFADDR / SIOCSIFNETMASK / SIOCSIFFLAGS."""
    import fcntl
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    req = lambda a: struct.pack("16sH2s4s8s", name.encode(), socket.AF_INET, b"\0\0", socket.inet_aton(a), b"\0" * 8)
    if ip: fcntl.ioctl(s, 0x8916, req(ip)); fcntl.ioctl(s, 0x891C, req("255.255.255.255"))
    fl = struct.unpack("16sH22s", fcntl.ioctl(s, 0x8913, struct.pack("16sH22s", name.encode(), 0, b"\0" * 22)))[1]
    fcntl.ioctl(s, 0x8914, struct.pack("16sH22s", name.encode(), fl | 0x1 | 0x40, b"\0" * 22))      # IFF_UP | IFF_RUNNING
    s.close()


ifaddr("lo", None)
for i, a in enumerate((WEB, TRACE, PX, PX_OUT)): ifaddr("lo:%d" % (i + 1), a)


# ---------------------------------------------------------------- "web": trả IP người hỏi
class Web(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True; daemon_threads = True


class WebH(socketserver.BaseRequestHandler):
    def handle(self):
        s = self.request; s.settimeout(5)
        data = b""
        while b"\r\n\r\n" not in data:
            x = s.recv(4096)
            if not x: return
            data += x
        ip = self.client_address[0]
        body = ("fl=1\nip=%s\nts=1\n" % ip if b"/cdn-cgi/trace" in data.split(b"\r\n")[0] else ip).encode()
        if b"GET /big" in data: body = b"x" * (5 * 1024 * 1024)
        s.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)


for host in (WEB, TRACE):
    w = Web((host, 80), WebH); threading.Thread(target=w.serve_forever, daemon=True).start()


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            x = self.request.recv(65536)
            if not x: break
            self.request.sendall(x)


e9 = Web((WEB, 9000), Echo); threading.Thread(target=e9.serve_forever, daemon=True).start()


# ---------------------------------------------------------------- proxy thử: SOCKS5 (user/pass) + HTTP CONNECT (Basic), đi ra bằng 198.51.100.8 + mang dấu
def out_conn(host, port):
    c = socket.socket(); c.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK); c.bind((PX_OUT, 0)); c.settimeout(5)
    c.connect((host, port)); c.settimeout(None); return c


def pipe(a, b):
    """Chuyển 2 chiều, hỗ trợ đóng 1 chiều (bên này hết gửi → báo bên kia hết gửi, vẫn nhận tiếp chiều còn lại)."""
    live = {a, b}
    try:
        while live:
            r, _, _ = select.select(list(live), [], [], 60)
            if not r: break
            for s in r:
                o = b if s is a else a
                x = s.recv(65536)
                if x: o.sendall(x); continue
                live.discard(s)
                try: o.shutdown(socket.SHUT_WR)
                except OSError: pass
    except OSError: pass
    finally:
        for s in (a, b):
            try: s.close()
            except OSError: pass


PSTATE = {"socks": None, "http": None, "conns": 0}


class Socks(socketserver.BaseRequestHandler):
    def handle(self):
        s = self.request; PSTATE["conns"] += 1
        try:
            v, n = s.recv(2); m = s.recv(n)
            if 2 not in m: s.sendall(b"\x05\xff"); return
            s.sendall(b"\x05\x02")
            hdr = s.recv(2); u = s.recv(hdr[1]); pl = s.recv(1)[0]; p = s.recv(pl)
            if (u.decode(), p.decode()) != (USER, PASS): s.sendall(b"\x01\x01"); return
            s.sendall(b"\x01\x00")
            h = s.recv(4); at = h[3]
            if at == 1: host = socket.inet_ntoa(s.recv(4))
            elif at == 3: host = s.recv(s.recv(1)[0]).decode()
            else: s.sendall(b"\x05\x08\x00\x01" + b"\0" * 6); return
            port = struct.unpack(">H", s.recv(2))[0]
            if host == "api.ipify.org": host = WEB
            try: o = out_conn(host, port)
            except OSError: s.sendall(b"\x05\x05\x00\x01" + b"\0" * 6); return
            s.sendall(b"\x05\x00\x00\x01" + socket.inet_aton(PX) + b"\x04\x38")
            pipe(s, o)
        except Exception: pass


class Http(socketserver.BaseRequestHandler):
    def handle(self):
        s = self.request; PSTATE["conns"] += 1
        try:
            d = b""
            while b"\r\n\r\n" not in d:
                x = s.recv(4096)
                if not x: return
                d += x
            lines = d.split(b"\r\n"); f = lines[0].split()
            if f[0] != b"CONNECT": s.sendall(b"HTTP/1.1 405 No\r\n\r\n"); return
            want = b"Basic " + base64.b64encode((USER + ":" + PASS).encode())
            if not any(l.lower().startswith(b"proxy-authorization:") and l.split(b":", 1)[1].strip() == want for l in lines[1:]):
                s.sendall(b"HTTP/1.1 407 Auth\r\nProxy-Authenticate: Basic\r\n\r\n"); return
            host, _, port = f[1].decode().rpartition(":")
            if host == "api.ipify.org": host = WEB
            try: o = out_conn(host, int(port))
            except OSError: s.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"); return
            s.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            pipe(s, o)
        except Exception: pass


def start_proxy(kind):
    srv = Web((PX, 1080 if kind == "socks" else 3128), Socks if kind == "socks" else Http)
    threading.Thread(target=srv.serve_forever, daemon=True).start(); PSTATE[kind] = srv


def stop_proxy(kind):
    srv = PSTATE.get(kind)
    if srv: srv.shutdown(); srv.server_close(); PSTATE[kind] = None


start_proxy("socks"); start_proxy("http")

D = "/tmp/cbpx-test"; PUBF = D + "/pub.json"
sh("rm", "-rf", D); os.makedirs(D)
ENV = dict(os.environ, CBPX_PUB=PUBF)


def conf(path, kind, port, pw=PASS, ips=(PX,)):
    json.dump({"kind": kind, "host": "proxy.test", "ips": list(ips), "port": port, "user": USER, "pass": pw}, open(path, "w"))
    return path


def cb(*a, t=40):
    r = subprocess.run([BIN] + list(a), capture_output=True, text=True, env=ENV, timeout=t)
    try: return json.loads(r.stdout.strip().splitlines()[-1]), r
    except Exception: return {}, r


def app_ip(host=WEB, port=80, path="/"):
    """App bình thường (không dấu) hỏi web: trả IP web thấy."""
    try:
        s = socket.create_connection((host, port), timeout=8)
        s.sendall(b"GET " + path.encode() + b" HTTP/1.1\r\nHost: x\r\n\r\n")
        d = b""
        while True:
            x = s.recv(65536)
            if not x: break
            d += x
        s.close()
        return d.split(b"\r\n\r\n", 1)[1].decode() if b"\r\n\r\n" in d else "?"
    except OSError as e:
        return "ERR " + str(e)


def st(): return cb("status", "-d", D)[0]


print("1. Thử proxy (cbproxy test)")
j, r = cb("test", "-c", conf(D + "/s.json", "socks5", 1080))
ck("SOCKS5 + user/pass đúng → ok, IP ra 198.51.100.8", j.get("ok") and j.get("kind") == "socks5" and j.get("ip") == PX_OUT, (j, r.stderr[-200:]))
j, _ = cb("test", "-c", conf(D + "/bad.json", "socks5", 1080, pw="sai"))
ck("SOCKS5 sai mật khẩu → báo SAI user / mật khẩu", not j.get("ok") and "SAI user" in j.get("err", ""), j)
j, _ = cb("test", "-c", conf(D + "/a.json", "auto", 3128))
ck("kiểu 'tự nhận' với proxy HTTP → nhận ra http, IP ra đúng", j.get("ok") and j.get("kind") == "http" and j.get("ip") == PX_OUT, j)
j, _ = cb("test", "-c", conf(D + "/dead.json", "auto", 1999))
ck("proxy chết (cổng đóng) → báo không nối được", not j.get("ok") and "không nối được" in j.get("err", ""), j)

print("2. Bật (up) — SOCKS5")
ck("chưa bật: app đi thẳng (web thấy 203.0.113.5)", app_ip() == WEB, app_ip())
j, r = cb("up", "-c", conf(D + "/up.json", "socks5", 1080), "-d", D)
ck("up → ok, chế độ proxy, đã gắn iptables, IP ra 198.51.100.8", j.get("ok") and j["state"]["mode"] == "proxy" and j["state"]["rules"] and j["state"]["ip"] == PX_OUT, (j, r.stderr[-300:]))
ck("app thường (không biết gì về proxy) → web thấy IP của proxy", app_ip() == PX_OUT, app_ip())
ck("trang báo IP kiểu Cloudflare cũng thấy IP proxy", "ip=" + PX_OUT in app_ip(TRACE, 80, "/cdn-cgi/trace"), app_ip(TRACE, 80, "/cdn-cgi/trace"))
big = app_ip(WEB, 80, "/big")
ck("tải 5 MB qua proxy: đủ, đúng từng byte", big == "x" * (5 * 1024 * 1024), len(big))
s = socket.create_connection((WEB, 9000), timeout=5); payload = os.urandom(2 * 1024 * 1024); got = bytearray()
threading.Thread(target=lambda: (s.sendall(payload), s.shutdown(socket.SHUT_WR)), daemon=True).start()
while True:
    x = s.recv(65536)
    if not x: break
    got += x
s.close()
ck("gửi + nhận 2 MB 2 chiều (đóng 1 chiều đúng cách)", bytes(got) == payload, len(got))
ck("cổng nội bộ / loopback KHÔNG qua proxy", socket.create_connection(("127.0.0.1", 12081), timeout=2) is not None)
ck("iptables: có chain CBPX + chặn UDP 443 (CBPXF)", sh("iptables", "-t", "nat", "-C", "OUTPUT", "-j", "CBPX").returncode == 0 and "443" in sh("iptables", "-S", "CBPXF").stdout,
   sh("iptables", "-S", "CBPXF").stdout)
pub = json.load(open(PUBF)) if os.path.isfile(PUBF) else {}
ck("trạng thái công khai (adb thường đọc) có chế độ + IP ra, KHÔNG có mật khẩu", pub.get("mode") == "proxy" and pub.get("ip") == PX_OUT and PASS not in json.dumps(pub), pub)

print("3. Đích không tới được qua proxy → báo lỗi, KHÔNG đi thẳng (không lộ IP)")
r9 = app_ip(WEB, 9999)
ck("cổng đóng phía đích → app thấy lỗi / đóng, proxy vẫn dùng", r9 != WEB and st().get("mode") == "proxy", (r9, st()))

print("4. Proxy chết → tự đi mạng thường → proxy sống lại → quay lại proxy")
stop_proxy("socks")
ips = [app_ip() for _ in range(4)]
ck("proxy chết: app VẪN vào được web (đi thẳng)", all(x == WEB for x in ips), ips)
ck("trạng thái chuyển 'direct' + lý do", wait(lambda: st().get("mode") == "direct", 10) and st().get("err"), st())
t0 = time.time(); start_proxy("socks")
ck("proxy sống lại → tự quay về 'proxy' (≤ ~20 giây)", wait(lambda: st().get("mode") == "proxy", 30, 0.5), (st(), time.time() - t0))
ck("… app lại đi qua proxy", wait(lambda: app_ip() == PX_OUT, 5), app_ip())

print("5. Tiến trình proxy chết bất ngờ → gỡ iptables ngay, tự bật lại")
wp = int(open(D + "/worker.pid").read())
os.kill(wp, 9)
ck("tự bật lại tiến trình mới + gắn lại iptables", wait(lambda: st().get("running") and st().get("rules") and int(open(D + "/worker.pid").read()) != wp, 15, 0.3), st())
ck("… app vẫn qua proxy", wait(lambda: app_ip() == PX_OUT, 10), app_ip())
sh("iptables", "-t", "nat", "-D", "OUTPUT", "-j", "CBPX")
ck("iptables bị xoá mất (Android nạp lại) → tự gắn lại trong ~15 giây", wait(lambda: sh("iptables", "-t", "nat", "-C", "OUTPUT", "-j", "CBPX").returncode == 0, 25, 0.5))

print("6. Đổi sang proxy HTTP (up lần 2 thay bản cũ)")
j, r = cb("up", "-c", conf(D + "/h.json", "http", 3128), "-d", D)
ck("up HTTP → proxy, kiểu http", j.get("ok") and j["state"]["mode"] == "proxy" and j["state"]["kind"] == "http", (j, r.stderr[-200:]))
ck("chỉ còn 1 bộ iptables (không chồng 2 lần)", sh("iptables", "-t", "nat", "-S", "OUTPUT").stdout.count("CBPX") == 1, sh("iptables", "-t", "nat", "-S", "OUTPUT").stdout)
ck("app qua proxy HTTP", app_ip() == PX_OUT, app_ip())

print("7. Sai mật khẩu từ đầu → vẫn bật nhưng đi mạng thường (máy không mất mạng)")
j, _ = cb("up", "-c", conf(D + "/w.json", "socks5", 1080, pw="sai"), "-d", D)
ck("up với mật khẩu sai → chế độ direct + lý do 'SAI user / mật khẩu'", j.get("ok") and j["state"]["mode"] == "direct" and "SAI user" in j["state"].get("err", ""), j)
ck("app vẫn vào web (đi thẳng)", app_ip() == WEB, app_ip())

print("8. Tắt (down)")
j, _ = cb("down", "-d", D)
ck("down → gỡ sạch iptables, tiến trình dừng", j.get("ok") and not j.get("rules") and not st().get("running") and "CBPX" not in sh("iptables-save").stdout, (j, st()))
ck("app đi thẳng như chưa từng bật", app_ip() == WEB, app_ip())
ck("không còn file trạng thái công khai", not os.path.exists(PUBF))

print(f"\ncbproxy: {OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
