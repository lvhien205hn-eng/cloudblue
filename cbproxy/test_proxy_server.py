# -*- coding: utf-8 -*-
"""Bộ thử phía MÁY CHỦ của 🌐 Proxy riêng từng máy (22/11) — chạy trên Linux, không cần máy Android:
   1. windows/phonectl.py: đọc chuỗi proxy khách dán, che mật khẩu, lệnh `proxy` (--get/--set/--off/--again), đẩy cbproxy + cấu hình vào máy
      (adb giả), đọc trạng thái, tự bật lại sau khi máy khởi động lại, đường lùi "adb root" (máy KernelSU).
   2. cpapi.py: GET/POST /cpapi/<máy>/proxy — chỉ chủ máy / admin, proxy (có mật khẩu) đi qua stdin chứ không nằm trên dòng lệnh,
      1 việc / máy, máy chủ cũ chưa có lệnh proxy.
   Chạy:  python3 cbproxy/test_proxy_server.py"""
import importlib.util, io, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error
from contextlib import redirect_stdout
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:700], flush=True)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


# ============================================================== 1. phonectl
print("1. Đọc chuỗi proxy khách dán (_px_parse)")
sys.argv = ["phonectl.py"]
pc = load(os.path.join(ROOT, "windows", "phonectl.py"), "phonectl_t")
P = pc._px_parse
good = [
    ("1.2.3.4:8080", {"kind": "auto", "host": "1.2.3.4", "port": 8080, "user": "", "pass": ""}),
    ("  1.2.3.4:8080:khach:mk123  ", {"kind": "auto", "host": "1.2.3.4", "port": 8080, "user": "khach", "pass": "mk123"}),
    ("1.2.3.4:8080:khach:mk:có:hai", {"kind": "auto", "host": "1.2.3.4", "port": 8080, "user": "khach", "pass": "mk:có:hai"}),
    ("khach:mk@1.2.3.4:1080", {"kind": "auto", "host": "1.2.3.4", "port": 1080, "user": "khach", "pass": "mk"}),
    ("socks5://u:p@proxy.example.vn:1080", {"kind": "socks5", "host": "proxy.example.vn", "port": 1080, "user": "u", "pass": "p"}),
    ("SOCKS5H://9.9.9.9:1080/", {"kind": "socks5", "host": "9.9.9.9", "port": 1080, "user": "", "pass": ""}),
    ("http://u:p@9.9.9.9:3128", {"kind": "http", "host": "9.9.9.9", "port": 3128, "user": "u", "pass": "p"}),
    ("khach:mk:5.6.7.8:9000", {"kind": "auto", "host": "5.6.7.8", "port": 9000, "user": "khach", "pass": "mk"}),
    ("u:p@w@1.2.3.4:80", {"kind": "auto", "host": "1.2.3.4", "port": 80, "user": "u", "pass": "p@w"}),
]
for s, want in good:
    try: got = P(s)
    except ValueError as e: got = f"ValueError: {e}"
    ck(f"{s.strip()!r} → {want['kind']} {want['host']}:{want['port']} user={want['user']!r}", got == want, got)
ck("chọn kiểu SOCKS5 trong hộp → giữ socks5", P("1.2.3.4:8080", "socks5")["kind"] == "socks5")
bad = [("", "Chưa nhập"), ("1.2.3.4", "Thiếu cổng"), ("1.2.3.4:abc", "phải là số"), ("1.2.3.4:70000", "từ 1 đến 65535"),
       ("1.2.3.4:0", "từ 1 đến 65535"), ("127.0.0.1:8080", "không hợp lệ"), ("0.0.0.0:80", "không hợp lệ"),
       ("https://1.2.3.4:443", "HTTPS"), ("bad host!:80", "không hợp lệ"), ("1.2.3:80", "không hợp lệ"),
       ("[2001:db8::1]:1080", "IPv6"), ("u:p@[2001:db8::1]:1080", "IPv6"), ("1.2.3.4:80\n", None), ("1.2.3.4:80:u\x01:p", "ký tự lạ"),
       ("1.2.3.4:80:" + "u" * 300 + ":p", "quá dài")]
for s, word in bad:
    try: P(s); got = "không báo lỗi"
    except ValueError as e: got = str(e)
    if word is None: ck(f"{s!r} (xuống dòng cuối) vẫn đọc được", got == "không báo lỗi", got)
    else: ck(f"{s[:40]!r} → lỗi “…{word}…”", word in got, got)
try: P("1.2.3.4:80", "ftp"); got = ""
except ValueError as e: got = str(e)
ck("kiểu lạ → lỗi", "Kiểu proxy" in got, got)

print("2. Che mật khẩu khi trả về web (_px_mask)")
ck("có user/pass → user:••••", pc._px_mask(P("1.2.3.4:8080:khach:BiMat")) == "1.2.3.4:8080:khach:••••")
ck("không user → IP:cổng", pc._px_mask(P("1.2.3.4:8080")) == "1.2.3.4:8080")
ck("chưa có proxy → rỗng", pc._px_mask(None) == "")

# ---------- máy giả: trạng thái phones.json trong bộ nhớ + adb giả ----------
ST = {"phones": [{"name": "m1", "port": 21503}, {"name": "m2", "port": 21513}]}
RUN = {"m1": True, "m2": False}
pc.load = lambda: json.loads(json.dumps(ST))
def _save(st): ST.clear(); ST.update(json.loads(json.dumps(st)))
pc.save = _save
pc.rec = lambda name, st=None: next((x for x in (st or pc.load())["phones"] if x["name"] == name), None)
pc._need = lambda name: (lambda st: (st, next(x for x in st["phones"] if x["name"] == name)))(pc.load())
pc.is_running = lambda name, p=None, _v=None: RUN.get(name, False)
pc.vms = lambda: []
APPLY = []
real_apply = pc._px_apply


def run_cmd(argv, stdin=None):
    """Chạy cmd_proxy như từ dòng lệnh → (mã thoát, chữ in ra)."""
    a = SimpleNamespace(name=argv[0], get=False, set=False, off=False, again=False, url="", url_stdin=False, kind="auto")
    for x in argv[1:]:
        if x.startswith("--url="): a.url = x[6:]
        elif x.startswith("--kind="): a.kind = x[7:]
        else: setattr(a, x[2:].replace("-", "_"), True)
    buf = io.StringIO(); code = 0
    old_in = sys.stdin
    if stdin is not None: sys.stdin = SimpleNamespace(buffer=io.BytesIO(stdin.encode("utf-8")))
    try:
        with redirect_stdout(buf): pc.cmd_proxy(a)
    except SystemExit as e: code = e.code or 0
    finally: sys.stdin = old_in
    return code, buf.getvalue()


print("3. Lệnh `proxy` (--set / --get / --off / --again)")
pc._px_apply = lambda p, quiet=False: (APPLY.append(json.loads(json.dumps(p))), (True, "Đã BẬT proxy — IP ra: 5.6.7.8 · 120 ms", {"mode": "proxy"}))[1]
pc._px_state = lambda p: {"mode": "proxy", "ip": "5.6.7.8", "ms": 120, "alive": True, "kind": "socks5"}
code, out = run_cmd(["m2", "--set", "--url=1.2.3.4:8080:khach:BiMat123"])
ck("máy đang TẮT: lưu, chưa áp dụng", code == 0 and "PROXY_OK Đã lưu — máy đang tắt" in out and not APPLY, out)
ck("phones.json có proxy của m2", (pc.rec("m2") or {}).get("proxy", {}).get("pass") == "BiMat123")
code, out = run_cmd(["m1", "--set", "--url-stdin", "--kind=socks5"], stdin="khach:Mk#1@9.8.7.6:1080\n")
ck("máy đang CHẠY + proxy qua stdin → áp dụng, báo IP ra", code == 0 and "PROXY_OK Đã BẬT proxy — IP ra: 5.6.7.8" in out and len(APPLY) == 1, out)
ck("cấu hình áp dụng đúng (kiểu socks5, mật khẩu đọc từ stdin)", APPLY and APPLY[-1]["proxy"] == {"kind": "socks5", "host": "9.8.7.6", "port": 1080, "user": "khach", "pass": "Mk#1"}, APPLY)
code, out = run_cmd(["m1", "--set", "--url=1.2.3.4"])
ck("proxy sai → PROXY_FAIL, mã 2, KHÔNG đổi cấu hình cũ", code == 2 and out.startswith("PROXY_FAIL Thiếu cổng") and pc.rec("m1")["proxy"]["host"] == "9.8.7.6", out)
code, out = run_cmd(["m1", "--get"])
j = json.loads(out.split("PROXY ", 1)[1]) if out.startswith("PROXY ") else {}
ck("--get: có proxy, che mật khẩu, kèm trạng thái", j.get("set") and j.get("show") == "9.8.7.6:1080:khach:••••" and j.get("has_pass") and j.get("state", {}).get("ip") == "5.6.7.8", out)
ck("--get KHÔNG in mật khẩu ra", "Mk#1" not in out, out)
code, out = run_cmd(["m2", "--get"])
j = json.loads(out.split("PROXY ", 1)[1]) if out.startswith("PROXY ") else {}
ck("--get máy tắt: online=false, không đọc trong máy", j.get("set") and j.get("online") is False and j.get("state") is None, out)
APPLY.clear()
code, out = run_cmd(["m1", "--again"])
ck("--again: áp dụng lại cấu hình đã lưu", code == 0 and len(APPLY) == 1 and APPLY[0]["proxy"]["host"] == "9.8.7.6", out)
code, out = run_cmd(["m1", "--off"])
ck("--off: xoá cấu hình + áp dụng (tắt trong máy)", code == 0 and "proxy" not in pc.rec("m1") and len(APPLY) == 2 and "proxy" not in APPLY[-1], out)
APPLY.clear()
pc._px_state = lambda p: None
code, out = run_cmd(["m1", "--off"])
ck("--off lần nữa (máy không chạy proxy) → báo luôn, không cần root", code == 0 and "Máy không dùng proxy" in out and not APPLY, out)
code, out = run_cmd(["m1", "--again"])
ck("--again khi chưa đặt proxy → PROXY_FAIL", code == 2 and "PROXY_FAIL Máy chưa đặt proxy" in out, out)
pc._px_apply = lambda p, quiet=False: (False, "Máy chưa có quyền root cho máy chủ (cần để bật proxy) — bấm 🔓 Root máy rồi thử lại.", None)
code, out = run_cmd(["m1", "--set", "--url=1.2.3.4:8080"])
ck("không áp dụng được → PROXY_FAIL + mã 1 (cấu hình vẫn lưu để lần bật sau thử lại)", code == 1 and "PROXY_FAIL Máy chưa có quyền root" in out and pc.rec("m1").get("proxy"), out)
pc._px_apply = real_apply

print("4. Đẩy cbproxy + cấu hình vào máy (_px_apply, adb giả)")
CALLS = []
binf = tempfile.NamedTemporaryFile(delete=False); binf.write(b"x"); binf.close()
pc._px_local = lambda: binf.name
pc._px_resolve = lambda host: ["9.8.7.6"] if host != "khong-co.example" else []
SEEN = {}


def fake_root(p, script, files=(), timeout=120):
    CALLS.append((script, [n for _, n in files]))
    for loc, n in files:
        if n == "conf.json": SEEN["conf"] = json.load(open(loc, encoding="utf-8")); SEEN["conf_path"] = loc
    if "cbproxy up" in script: return FAKE["up"] + "\nPX_END\n"
    if "cbproxy down" in script: return "{\"ok\":true,\"rules\":false}\nPX_END\n"
    return "PX_END\n"


pc._px_root = fake_root
FAKE = {"up": json.dumps({"ok": True, "state": {"mode": "proxy", "kind": "socks5", "ip": "5.6.7.8", "ms": 87}})}
ph = {"name": "m1", "port": 21503, "proxy": P("socks5://khach:Mk#1@px.example:1080")}
ok, msg, stt = pc._px_apply(ph, quiet=True)
ck("bật được → “Đã BẬT proxy — IP ra: 5.6.7.8 · 87 ms”", ok and msg == "Đã BẬT proxy — IP ra: 5.6.7.8 · 87 ms", msg)
ck("1 lần chạy root duy nhất: đẩy cbproxy + cấu hình cùng lúc", len(CALLS) == 1 and CALLS[-1][1] == ["up_cbproxy", "conf.json"], CALLS)
ck("trong máy chỉ thay cbproxy khi md5 khác bản ghim", f'!= "{pc.CBPX_FILE[1]}" ]; then cp $T/up_cbproxy' in CALLS[-1][0], CALLS[-1][0])
ck("cấu hình gửi vào máy: IP đã phân giải + mật khẩu (chỉ trong máy, quyền 600)",
   SEEN.get("conf") == {"kind": "socks5", "host": "px.example", "ips": ["9.8.7.6"], "port": 1080, "user": "khach", "pass": "Mk#1"} and "chmod 600 $D/conf.json" in CALLS[-1][0], SEEN)
ck("file cấu hình tạm trên máy chủ đã xoá ngay", not os.path.exists(SEEN.get("conf_path", "/x")))
ck("lệnh bật: cbproxy up -c $D/conf.json -d $D", "$D/cbproxy up -c $D/conf.json -d $D" in CALLS[-1][0])
FAKE["up"] = json.dumps({"ok": True, "state": {"mode": "direct", "err": "proxy báo SAI user / mật khẩu"}})
ok, msg, stt = pc._px_apply(ph, quiet=True)
ck("proxy sai mật khẩu → vẫn lưu, báo đang đi mạng thường", ok and msg.startswith("Đã lưu proxy nhưng proxy CHƯA dùng được (proxy báo SAI user / mật khẩu)"), msg)
FAKE["up"] = json.dumps({"ok": False, "err": "iptables nat: exit status 1 can't initialize iptables table `nat'"})
ok, msg, stt = pc._px_apply(ph, quiet=True)
ck("iptables lỗi → báo “Chưa bật được proxy: …”", not ok and msg.startswith("Chưa bật được proxy: iptables nat"), msg)
FAKE["up"] = "sh: /data/adb/cbproxy/cbproxy: not executable"
ok, msg, stt = pc._px_apply(ph, quiet=True)
ck("máy trả lời lạ → báo dòng cuối", not ok and "not executable" in msg, msg)
ok, msg, stt = pc._px_apply(dict(ph, proxy=P("khong-co.example:80")), quiet=True)
ck("tên miền proxy không phân giải được → báo, không đụng máy", not ok and "Không tìm được IP của proxy khong-co.example" in msg, msg)
pc._px_root = lambda p, script, files=(), timeout=120: None
ok, msg, stt = pc._px_apply(ph, quiet=True)
ck("máy không có root → báo bấm 🔓 Root máy", not ok and "bấm 🔓 Root máy" in msg, msg)
pc._px_root = fake_root; CALLS.clear()
ok, msg, stt = pc._px_apply({"name": "m1", "port": 21503}, quiet=True)
ck("không còn proxy → cbproxy down + xoá cấu hình", ok and "Đã TẮT proxy" in msg and "cbproxy down -d $D" in CALLS[-1][0] and "rm -f $D/conf.json" in CALLS[-1][0], CALLS)

print("5. Đọc trạng thái trong máy bằng adb THƯỜNG (_px_state)")
now = int(time.time())
pub = {"ver": "22.11a", "mode": "proxy", "kind": "socks5", "host": "px.example", "ip": "5.6.7.8", "ms": 90, "beat": now - 4, "rules": True}
OUT = {"o": json.dumps(pub) + f"\nNOW={now}\n"}
pc.ashell = lambda name, script, port=None, timeout=60: SimpleNamespace(stdout=OUT["o"], stderr="", returncode=0)
real_state = pc.__dict__.get("_px_state")
pc._px_state = load(os.path.join(ROOT, "windows", "phonectl.py"), "phonectl_t2")._px_state     # bản thật (đã bị thay ở mục 3)
pc._px_state.__globals__["ashell"] = pc.ashell
s = pc._px_state({"name": "m1", "port": 21503})
ck("đọc được: proxy, IP ra, còn sống", s and s["mode"] == "proxy" and s["ip"] == "5.6.7.8" and s["alive"] is True and s["age"] == 4, s)
ck("không trả host / user / mật khẩu ra ngoài", s is not None and "host" not in s and "user" not in s and "pass" not in s, s)
OUT["o"] = json.dumps(dict(pub, beat=now - 300)) + f"\nNOW={now}\n"
s = pc._px_state({"name": "m1", "port": 21503})
ck("nhịp sống cũ 5 phút (máy vừa khởi động lại) → không còn sống", s and s["alive"] is False, s)
OUT["o"] = f"\nNOW={now}\n"
ck("chưa từng bật → None", pc._px_state({"name": "m1", "port": 21503}) is None)

print("6. Tự bật lại sau khi máy khởi động lại (_proxy_keep)")
ST["phones"][0]["proxy"] = P("1.2.3.4:8080")
KEEP = []
g2 = pc._px_state.__globals__
g2["rec"] = pc.rec
g2["_px_apply"] = lambda p, quiet=False: (KEEP.append(p["name"]), (True, "Đã BẬT proxy — IP ra: 5.6.7.8 · 9 ms", {}))[1]
keep = g2["_proxy_keep"]
OUT["o"] = json.dumps(dict(pub, beat=now - 2)) + f"\nNOW={now}\n"
with redirect_stdout(io.StringIO()): keep({"name": "m1"})
ck("proxy đang chạy → để yên", KEEP == [], KEEP)
OUT["o"] = json.dumps(dict(pub, beat=now - 900)) + f"\nNOW={now}\n"
with redirect_stdout(io.StringIO()): keep({"name": "m1"}, 21503)
ck("tiến trình proxy không chạy (máy vừa bật lại) → bật lại", KEEP == ["m1"], KEEP)
KEEP.clear(); OUT["o"] = json.dumps({"mode": "crashed", "err": "iptables lỗi", "beat": now - 60}) + f"\nNOW={now}\n"
with redirect_stdout(io.StringIO()): keep({"name": "m1"})
ck("vừa hỏng < 30 phút → không thử lại liên tục", KEEP == [], KEEP)
OUT["o"] = json.dumps({"mode": "crashed", "err": "iptables lỗi", "beat": now - 3600}) + f"\nNOW={now}\n"
with redirect_stdout(io.StringIO()): keep({"name": "m1"})
ck("hỏng đã lâu → thử lại", KEEP == ["m1"], KEEP)
KEEP.clear(); ST["phones"][1].pop("proxy", None)
with redirect_stdout(io.StringIO()): keep({"name": "m2"})
ck("máy không đặt proxy → không làm gì", KEEP == [], KEEP)

print("7. Máy KernelSU (adb không có su) → dùng “adb root” đúng 1 lần rồi “adb unroot”")
ADB = []
g2["_root_sh"] = lambda p, script, timeout=120, files=(): ((SimpleNamespace(stdout="/system/bin/sh: su: inaccessible or not found\n", stderr=""), False)
                                                          if not ADB or ADB[-1] != "root" else (SimpleNamespace(stdout="ok\nPX_END\n", stderr=""), True))
g2["adb"] = lambda *a, timeout=60: (ADB.append(a[2]), SimpleNamespace(stdout="restarting adbd as root\n" if a[2] == "root" else "restarting adbd as non root\n", stderr="", returncode=0))[1]
g2["_adb_fresh"] = lambda port: True
g2["time"] = SimpleNamespace(sleep=lambda s: None, time=time.time)
g2["DG_ADBROOT"] = True
o = g2["_px_root"]({"name": "m1", "port": 21503}, "echo PX_END\n")
ck("có kết quả sau adb root, và đã adb unroot", o is not None and "PX_END" in o and ADB == ["root", "unroot"], (o, ADB))
ADB.clear(); g2["DG_ADBROOT"] = False
ck("tắt DISK_ADBROOT → không thử adb root", g2["_px_root"]({"name": "m1", "port": 21503}, "echo PX_END\n") is None and ADB == [], ADB)
g2["DG_ADBROOT"] = True
g2["adb"] = lambda *a, timeout=60: (ADB.append(a[2]), SimpleNamespace(stdout="adbd cannot run as root in production builds\n", stderr="", returncode=0))[1]
ADB.clear()
ck("máy không cho adb root → None, không unroot", g2["_px_root"]({"name": "m1", "port": 21503}, "echo PX_END\n") is None and ADB == ["root"], ADB)
os.remove(binf.name)

print("8. Lệnh `proxy` có trong phonectl (argparse) + móc vào lúc máy bật")
src = open(os.path.join(ROOT, "windows", "phonectl.py"), encoding="utf-8").read()
r = subprocess.run([sys.executable, os.path.join(ROOT, "windows", "phonectl.py"), "proxy", "--help"], capture_output=True, text=True, cwd=tempfile.gettempdir())
ck("phonectl proxy --help chạy được", r.returncode == 0 and "--url-stdin" in r.stdout and "--again" in r.stdout, r.stdout + r.stderr)
ck("wait_boot gọi _proxy_keep (máy bật lại / máy mới)", '_proxy_keep({"name": name}, port)' in src)
ck("_wake_one bật proxy TRƯỚC khi báo WAKE_READY (khách vào là đã qua proxy)",
   src.find("try: _proxy_keep(p)") != -1 and src.find("try: _proxy_keep(p)") < src.find('print(f"WAKE_READY {nm}'))
ck("vòng 5 phút (rootfix --all) canh proxy", 'if p.get("proxy") and is_running(p["name"], p): _proxy_keep(p)' in src)
ck("khách bấm Khởi động lại máy có proxy → lệnh nền bật lại proxy ngay khi Android lên", 'if p.get("proxy"): _proxy_later(p["name"])' in src)
KW = []
pc.android_ready = lambda port, wait=120: True
pc._proxy_keep = lambda p, port=None: KW.append(p["name"])
pc.time = SimpleNamespace(sleep=lambda s: None, time=time.time)
ST["phones"][0]["proxy"] = P("1.2.3.4:8080"); RUN["m1"] = True
with redirect_stdout(io.StringIO()): pc.cmd_proxykeep(SimpleNamespace(name="m1", all=False, wait=True))
ck("proxykeep TÊN --wait: chờ Android lên rồi bật lại proxy", KW == ["m1"], KW)
KW.clear(); ST["phones"][0].pop("proxy", None)
with redirect_stdout(io.StringIO()): pc.cmd_proxykeep(SimpleNamespace(name="m1", all=False, wait=True))
ck("máy không có proxy → --wait thoát ngay", KW == [], KW)
import hashlib
binp = os.path.join(ROOT, "windows", "cbproxy-x86_64")
ck("windows/cbproxy-x86_64 đúng md5 ghim trong phonectl", os.path.isfile(binp) and hashlib.md5(open(binp, "rb").read()).hexdigest() == pc.CBPX_FILE[1])

# ============================================================== 2. cpapi
print("9. cpapi: GET/POST /cpapi/<máy>/proxy")
home = tempfile.mkdtemp(prefix="cpapi_home_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\n")
LOG = os.path.join(home, "calls.jsonl")
open(os.path.join(home, "phonectl.py"), "w", encoding="utf-8").write(r'''import json, os, sys, time
a = sys.argv[1:]
data = sys.stdin.read() if "--url-stdin" in a else ""
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls.jsonl"), "a", encoding="utf-8").write(json.dumps({"argv": a, "stdin": data}) + "\n")
if a[0] != "proxy": sys.exit(9)
if a[1] == "cu":
    sys.stderr.write("phonectl.py: error: argument cmd: invalid choice: 'proxy'\n"); sys.exit(2)
if "--get" in a:
    print("   (dòng thường)"); print("PROXY " + json.dumps({"set": True, "kind": "auto", "show": "1.2.3.4:8080:khach:••••", "online": True,
          "state": {"mode": "proxy", "ip": "5.6.7.8", "ms": 80, "alive": True}}, ensure_ascii=False)); sys.exit(0)
if "slow" in data: time.sleep(1.5)
if "sai" in data: print("PROXY_FAIL Thiếu cổng — nhập dạng IP:cổng hoặc IP:cổng:user:pass."); sys.exit(2)
if "--off" in a: print("PROXY_OK Đã TẮT proxy — máy đi mạng thường."); sys.exit(0)
print("   🌐 m: ..."); print("PROXY_OK Đã BẬT proxy — IP ra: 5.6.7.8 · 80 ms")
''')
os.environ["HOME"] = home
cp = load(os.path.join(ROOT, "cpapi.py"), "cpapi_t")
OWNER, SHARED, ADMIN = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"
PID, PID_OLD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TOK = {"t-owner": {"uid": OWNER, "admin": False}, "t-shared": {"uid": SHARED, "admin": False}, "t-admin": {"uid": ADMIN, "admin": True}}
cp.whoami = lambda t: TOK.get(t)
PHONES = {PID: {"id": PID, "name": "M1", "user_id": OWNER, "status": "active", "port": 21503, "container": "m1"},
          PID_OLD: {"id": PID_OLD, "name": "M0", "user_id": OWNER, "status": "active", "port": 21513, "container": "cu"}}
cp.phone_of = lambda me, pid: PHONES.get(pid) if (me["admin"] or PHONES.get(pid, {}).get("user_id") == me["uid"] or me["uid"] == SHARED) else None
cp.maint = lambda: {}
cp.is_locked = lambda p: False
cp.log = lambda *a: None
srv = cp.Server(("127.0.0.1", 0), cp.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}/cpapi/"


def call(path, tok, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        b = e.read() or b"{}"
        try: return e.code, json.loads(b)
        except ValueError: return e.code, {"raw": b[:200].decode("utf-8", "replace")}


def job(jid, tok="t-owner"):
    for _ in range(100):
        c, j = call("job?id=" + jid, tok, method="GET")
        if j.get("state") != "running": return j
        time.sleep(0.1)
    return j


def calls():
    try: return [json.loads(l) for l in open(LOG, encoding="utf-8")]
    except FileNotFoundError: return []


c, j = call(PID + "/proxy", "t-owner", method="GET")
ck("chủ máy GET → trạng thái proxy", c == 200 and j.get("show") == "1.2.3.4:8080:khach:••••" and j["state"]["ip"] == "5.6.7.8", (c, j))
c, j = call(PID + "/proxy", "t-admin", method="GET")
ck("admin GET được", c == 200 and j.get("set") is True, (c, j))
c, j = call(PID + "/proxy", "t-shared", method="GET")
ck("người được chia sẻ máy → 403 (proxy là của chủ máy)", c == 403 and "Chỉ chủ máy" in j.get("error", ""), (c, j))
c, j = call(PID + "/proxy", "t-shared", {"do": "set", "url": "1.2.3.4:8080"})
ck("người được chia sẻ POST → 403", c == 403, (c, j))
c, j = call(PID + "/proxy", "t-nobody", method="GET")
ck("không đăng nhập → 401", c == 401, (c, j))
open(LOG, "w").close()
c, j = call(PID + "/proxy", "t-owner", {"do": "set", "url": "1.2.3.4:8080:khach:BiMat#99", "kind": "socks5"})
ck("POST lưu → có mã việc", c == 200 and j.get("job"), (c, j))
r = job(j["job"])
ck("việc xong: “Đã BẬT proxy — IP ra …”", r.get("state") == "done" and r.get("msg") == "Đã BẬT proxy — IP ra: 5.6.7.8 · 80 ms", r)
cl = calls()
ck("phonectl nhận: proxy m1 --set --url-stdin --kind socks5", cl and cl[-1]["argv"] == ["proxy", "m1", "--set", "--url-stdin", "--kind", "socks5"], cl)
ck("MẬT KHẨU proxy đi qua stdin, KHÔNG nằm trên dòng lệnh", cl and "BiMat#99" in cl[-1]["stdin"] and not any("BiMat" in x for x in cl[-1]["argv"]), cl)
c, j = call(PID + "/proxy", "t-owner", {"do": "set", "url": "sai:1"})
r = job(j["job"]) if c == 200 else {}
ck("phonectl báo lỗi → việc lỗi, câu báo của phonectl", r.get("state") == "error" and r.get("msg", "").startswith("Thiếu cổng"), (c, r))
for body, word in (({"do": "set", "url": ""}, "Proxy không hợp lệ"), ({"do": "set", "url": "a" * 601}, "Proxy không hợp lệ"),
                   ({"do": "set", "url": "1.2.3.4:80\n"}, None), ({"do": "set", "url": "1.2.3.4:80", "kind": "ftp"}, "Kiểu proxy"),
                   ({"do": "xoa"}, "Thiếu việc"), ({}, "Thiếu việc")):
    c, j = call(PID + "/proxy", "t-owner", body)
    if word is None:
        ck("xuống dòng ở cuối ô (dán từ ghi chú) vẫn nhận", c == 200, (c, j))
        if c == 200: job(j["job"])
    else: ck(f"POST {json.dumps(body)[:40]} → 400 “{word}…”", c == 400 and word in j.get("error", ""), (c, j))
c, j = call(PID + "/proxy", "t-owner", {"do": "set", "url": "1.2.3.4:80\x01"})
ck("ký tự điều khiển → 400", c == 400, (c, j))
c1, j1 = call(PID + "/proxy", "t-owner", {"do": "set", "url": "slow:1.2.3.4:80"})
c2, j2 = call(PID + "/proxy", "t-owner", {"do": "off"})
ck("đang áp dụng mà bấm tiếp → 409 (1 việc / máy)", c1 == 200 and c2 == 409 and "đợi vài giây" in j2.get("error", ""), (c1, c2, j2))
job(j1["job"])
c, j = call(PID + "/proxy", "t-owner", {"do": "off"})
r = job(j["job"]) if c == 200 else {}
ck("tắt proxy → phonectl proxy m1 --off", r.get("msg") == "Đã TẮT proxy — máy đi mạng thường." and calls()[-1]["argv"] == ["proxy", "m1", "--off"], (r, calls()[-1:]))
c, j = call(PID + "/proxy", "t-owner", {"do": "again"})
r = job(j["job"]) if c == 200 else {}
ck("áp dụng lại → phonectl proxy m1 --again", r.get("state") == "done" and calls()[-1]["argv"] == ["proxy", "m1", "--again"], (r, calls()[-1:]))
c, j = call(PID_OLD + "/proxy", "t-owner", method="GET")
ck("máy chủ chưa cập nhật (phonectl cũ) → 409 old", c == 409 and j.get("old") is True and "chưa cập nhật" in j.get("error", ""), (c, j))
c, j = call(PID_OLD + "/proxy", "t-owner", {"do": "set", "url": "1.2.3.4:80"})
r = job(j["job"]) if c == 200 else {}
ck("POST ở máy chủ cũ → việc lỗi “chưa cập nhật bản có Proxy”", r.get("state") == "error" and "chưa cập nhật bản có Proxy" in r.get("msg", ""), r)
c, j = call(PID + "/proxy", "t-owner", method="PUT")
ck("phương thức lạ → không làm gì", c in (404, 405, 501), c)
srv.shutdown(); shutil.rmtree(home, ignore_errors=True)

print(f"\nproxy (máy chủ): {OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
