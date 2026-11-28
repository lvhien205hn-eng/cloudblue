# -*- coding: utf-8 -*-
"""28/11e · 📱 BLUEREAL — công cụ máy (cpapi) với điện thoại THẬT cắm USB (SQL v70: cloud_phones.real_device → real_devices.serial / node).
   Thử bằng đồ giả (không cần Windows / điện thoại): Supabase giả + adb giả, chạy máy chủ cpapi thật ở cổng ngẫu nhiên.
   1. đơn máy thật cắm ở máy chủ này → mọi lệnh adb đi theo số máy USB (adb -s <serial>), không "adb connect", không cổng 127.0.0.1
   2. phím / gõ chữ / mở link / chụp màn / ứng dụng / cài APK dùng được · Root, Proxy, xoay, tab cửa sổ, clone, GPS, kho app, khởi động lại → báo rõ
   3. máy thật gắn máy chủ KHÁC → không đụng (máy chưa chạy) · máy của người khác → không thấy · ĐT đám mây thường vẫn như cũ
   Chạy: python3 .github/win-check/test_cpapi_real.py"""
import importlib.util, json, os, sys, tempfile, threading, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


home = tempfile.mkdtemp(prefix="cb_real_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\nNODE_ID=win-a\n")
os.environ["HOME"] = home; os.environ["CB_HOME"] = home
os.makedirs(os.path.join(home, "logs"), exist_ok=True)
cp = load("cpapi_real", "cpapi.py")

OWNER, OTHER = "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"
REAL, REAL_FAR, CLOUD = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002", "aaaaaaaa-0000-4000-8000-000000000003"
DEV, DEV_FAR = "dddddddd-0000-4000-8000-000000000001", "dddddddd-0000-4000-8000-000000000002"
PHONES = {
    REAL: {"id": REAL, "user_id": OWNER, "name": "Galaxy S10", "ram": 8, "cpu": 8, "res": "1440x3040", "status": "active", "node": "win-a",
           "container": "real_dddddddd", "port": None, "expires_at": "2030-01-01T00:00:00+00:00", "locked": False, "real_device": DEV, "real_model": "s10"},
    REAL_FAR: {"id": REAL_FAR, "user_id": OWNER, "name": "Galaxy S9", "ram": 4, "cpu": 8, "res": "1440x2960", "status": "active", "node": "win-a",
               "container": "real_dddddddf", "port": None, "expires_at": "2030-01-01T00:00:00+00:00", "locked": False, "real_device": DEV_FAR, "real_model": "s9"},
    CLOUD: {"id": CLOUD, "user_id": OWNER, "name": "Máy 4GB", "ram": 4, "cpu": 4, "res": "720x1280", "status": "active", "node": "win-a",
            "container": "cp_abc", "port": 16384, "expires_at": "2030-01-01T00:00:00+00:00", "locked": False, "real_device": None},
}
DEVICES = {DEV: {"serial": "R58M12ABCDE", "node": "win-a"}, DEV_FAR: {"serial": "R58M99ZZZZZ", "node": "win-b"}}
GETS = []


def fake_sb_get(path, token=None):
    GETS.append(path)
    if path.startswith("/rest/v1/cloud_phones?id=eq."):
        pid = path.split("id=eq.", 1)[1].split("&", 1)[0]
        p = PHONES.get(pid)
        return [dict(p)] if p else []
    if path.startswith("/rest/v1/real_devices?id=eq."):
        rid = path.split("id=eq.", 1)[1].split("&", 1)[0]
        d = DEVICES.get(rid)
        return [dict(d)] if d else []
    return []


TOK = {"t-owner": {"uid": OWNER, "admin": False}, "t-other": {"uid": OTHER, "admin": False}}
cp.whoami = lambda t: TOK.get(t)
cp.sb_get = fake_sb_get
cp.share_users = lambda pid: set()
cp.maint = lambda: {}
cp.log = lambda *a: None
RUNS = []
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _R:
    def __init__(self, out=b"", code=0, err=b""): self.stdout, self.stderr, self.returncode = out, err, code


def fake_run(cmd, *a, **k):
    RUNS.append([str(x) for x in cmd])
    s = " ".join(str(x) for x in cmd)
    if "get-state" in s: return _R(b"device\n")
    if "sys.boot_completed" in s: return _R(b"1\n")
    if "pm list packages -3" in s: return _R(b"package:com.roblox.client\npackage:com.zing.zalo\n")
    if "exec-out screencap -p" in s: return _R(PNG)
    if "exec-out screencap" in s: return _R(b"", 1)
    if "mInputShown" in s: return _R(b"mInputShown=true\n")
    return _R(b"ok\n")


cp.subprocess.run = fake_run
srv = cp.Server(("127.0.0.1", 0), cp.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}/cpapi/"


def call(path, tok="t-owner", body=None, method=None, raw=False):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read()
            return r.status, (b if raw else json.loads(b or b"{}"))
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")


def adb_calls(): return [c for c in RUNS if "adb" in c]


print("1. bản cpapi + đồ phụ")
ck("CPAPI_VER 28/11e · dòng khởi động khớp", cp.CPAPI_VER == "28/11e" and b"cpapi b\xe1\xba\xa3n 28/11e ch\xe1\xba\xa1y" in open(os.path.join(ROOT, "cpapi.py"), "rb").read())
s1 = cp.RealSerial("R58M12ABCDE")
ck("port_key(): cổng máy ảo → số · số máy USB → giữ nguyên chuỗi (khoá bảng nhớ)", cp.port_key(16384) == 16384 and cp.port_key("16384") == 16384 and cp.port_key(s1) == "R58M12ABCDE")
ck("is_memu(): cổng ≥ 21500 là MEmu · máy thật không bao giờ là MEmu", cp.is_memu(21503) and not cp.is_memu(16384) and not cp.is_memu(s1))
RUNS.clear(); cp.adb(s1, ["shell", "echo hi"])
ck("adb(máy thật) → adb -s <số máy USB>, không cổng 127.0.0.1", RUNS and RUNS[-1][-4:] == ["-s", "R58M12ABCDE", "shell", "echo hi"] and not any("127.0.0.1" in x for x in RUNS[-1]), RUNS)
RUNS.clear()
_old = cp.subprocess.run
cp.subprocess.run = lambda cmd, *a, **k: (RUNS.append([str(x) for x in cmd]), _R(b"", 1, b"error: device 'R58M12ABCDE' not found"))[1]
cp.adb(s1, ["get-state"])
ck("máy thật mất kết nối → KHÔNG chạy 'adb connect' (chỉ dành cho máy ảo qua mạng)", len(RUNS) == 1 and "connect" not in RUNS[0], RUNS)
cp.subprocess.run = _old

print("2. máy thật cắm ở máy chủ này")
RUNS.clear()
c, j = call(REAL + "/info", method="GET")
ck("info: đang chạy, online (adb get-state theo số máy USB), có cờ real", c == 200 and j.get("online") is True and j.get("real") is True
   and any("R58M12ABCDE" in x and "get-state" in x for x in [" ".join(r) for r in adb_calls()]), (c, j, RUNS))
RUNS.clear(); c, j = call(REAL + "/key", body={"code": 4})
ck("phím Quay lại → input keyevent 4 trên đúng máy", c == 200 and any("R58M12ABCDE" in " ".join(r) and "input keyevent 4" in " ".join(r) for r in RUNS), (c, j, RUNS))
RUNS.clear(); c, j = call(REAL + "/text", body={"text": "hello world"})
ck("gõ chữ không dấu → input text", c == 200 and any("input text" in " ".join(r) and "R58M12ABCDE" in " ".join(r) for r in RUNS), (c, j, RUNS))
RUNS.clear(); c, j = call(REAL + "/url", body={"url": "https://example.com/a"})
ck("mở link trong máy", c == 200 and any("android.intent.action.VIEW" in " ".join(r) and "R58M12ABCDE" in " ".join(r) for r in RUNS), (c, j))
c, j = call(REAL + "/apps", method="GET")
ck("danh sách ứng dụng", c == 200 and j.get("apps") == ["com.roblox.client", "com.zing.zalo"], (c, j))
RUNS.clear(); c, j = call(REAL + "/stop", body={"pkg": "com.roblox.client"})
ck("dừng app", c == 200 and any("am force-stop com.roblox.client" in " ".join(r) for r in RUNS), (c, j))
c, img = call(REAL + "/shot?fresh=1", method="GET", raw=True)
ck("chụp màn hình (PNG) — nhớ ảnh theo số máy USB, không lỗi int(port)", c == 200 and isinstance(img, bytes) and img.startswith(b"\x89PNG")
   and any(isinstance(k, tuple) and k[0] == "R58M12ABCDE" for k in cp.SHOTS), (c, list(cp.SHOTS)[:3]))
c, j = call(REAL + "/ime", method="GET")
ck("máy đang mở bàn phím? (app điện thoại tự bật bàn phím)", c == 200 and j.get("shown") is True, (c, j))
bad = {}
for act, method, body in (("rotate", "POST", {"to": "land"}), ("density", "GET", None), ("reboot", "POST", {}), ("rootcfg", "GET", None),
                          ("proxy", "GET", None), ("win", "POST", {"do": "mini"}), ("clone", "GET", None), ("gps", "POST", {"lat": 1, "lng": 2}),
                          ("store", "GET", None), ("display", "POST", {"res": "1080x1920"}), ("gsf", "GET", None), ("gfx", "GET", None), ("root", "POST", {})):
    RUNS.clear(); c, j = call(REAL + "/" + act, body=body, method=method)
    if not (c == 400 and j.get("real") is True and "Máy thật" in j.get("error", "") and not adb_calls()): bad[act] = (c, j, RUNS[:2])
ck("Root · Proxy · xoay · độ rộng · khởi động lại · tab cửa sổ · clone · GPS · kho app · đổi màn · Google · chế độ hình → 400 báo rõ, KHÔNG chạy adb",
   not bad, bad)

print("3. không đụng nhầm máy")
RUNS.clear(); c, j = call(REAL_FAR + "/key", body={"code": 3})
ck("máy thật đang gắn máy chủ KHÁC → 'máy chưa chạy', không chạy adb ở máy chủ này", c == 409 and not adb_calls(), (c, j, RUNS))
c, j = call(REAL + "/key", tok="t-other", body={"code": 3})
ck("người khác (không được chia sẻ) → không thấy máy", c == 404, (c, j))
RUNS.clear(); c, j = call(CLOUD + "/key", body={"code": 3})
ck("ĐT đám mây thường vẫn như cũ: adb -s 127.0.0.1:<cổng>", c == 200 and any("127.0.0.1:16384" in " ".join(r) for r in RUNS), (c, j, RUNS))
RUNS.clear(); c, j = call(CLOUD + "/reboot", body={})
ck("ĐT đám mây vẫn khởi động lại được (không bị chặn như máy thật)", not (c == 400 and j.get("real")), (c, j))
n0 = len([g for g in GETS if "real_devices" in g]); call(REAL + "/apps", method="GET"); call(REAL + "/apps", method="GET")
ck("số máy USB nhớ 30 giây (không hỏi Supabase mỗi lần bấm)", len([g for g in GETS if "real_devices" in g]) == n0, GETS[-4:])

print(f"\nKẾT QUẢ: {OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
