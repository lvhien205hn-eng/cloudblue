# -*- coding: utf-8 -*-
"""23/11f · QUẢN LÝ MÁY CHỦ TỪ WEB + TỰ CẬP NHẬT THEO MÁY CHỦ KHÁC — thử bằng đồ giả (chạy được ở mọi máy, không cần Windows / giả lập):
   1. cpapi  /cpapi/admin/node: chỉ admin · GET báo bản đang chạy · POST update chạy lệnh A tách rời · chỉ nhận việc ghi sẵn · việc mất dữ
      liệu / tắt máy phải gõ đúng mã máy chủ · 1 việc / lúc · không nhận lệnh tự gõ.
   2. cloudphoned  follow_step: chỉ tự theo bản ĐÃ chạy ổn ở máy chủ khác đủ lâu VÀ đúng là bản trên GitHub; không lùi bản; ≤ 2 lần / bản.
   3. sua-tat-ca.py  sổ logs/cap-nhat.json + dấu của từng file trong FILES phải có thật trong file trên kho (không thì lệnh A báo "GitHub chưa có bản mới").
   Chạy: python3 .github/win-check/test_node.py"""
import datetime, importlib.util, json, os, re, sys, tempfile, threading, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


home = tempfile.mkdtemp(prefix="cb_node_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\nNODE_ID=win-a\n")
os.environ["HOME"] = home; os.environ["CB_HOME"] = home
os.makedirs(os.path.join(home, "logs"), exist_ok=True)
cp = load("cpapi_n", "cpapi.py")
SUA_SRC = open(os.path.join(ROOT, "windows", "sua-tat-ca.py"), "rb").read()
VER_NOW = re.search(rb'^VER = "([^"]+)"', SUA_SRC, re.M).group(1).decode()

# ============================================================== 1. cpapi /cpapi/admin/node
print("1. cpapi · /cpapi/admin/node (web admin → 🛠 Quản lý máy chủ)")
ADMIN, USER = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
TOK = {"t-admin": {"uid": ADMIN, "admin": True}, "t-user": {"uid": USER, "admin": False}}
cp.whoami = lambda t: TOK.get(t)
cp.log = lambda *a: None
cp.IS_WIN = True
RUNS, POPENS, SLOW = [], [], {"s": 0.0}


class _R:
    def __init__(self, s, code=0): self.stdout, self.stderr, self.returncode = s.encode(), b"", code


FAKE_OUT = {"list": "cp_a chạy\ncp_b tắt\n", "cleanup": "Đã xoá 2 giả lập thừa\n", "shutdownserver": "1/3 …\nSHUTDOWN_OK Windows tắt sau 15 giây · bấm nút nguồn bật máy chủ lại thì 3 máy khách tự bật lại.\n",
            "rebootserver": "REBOOT_OK Windows khởi động lại sau 15 giây · 3 máy khách tự bật lại khi Windows lên (khoảng 3–8 phút).\n"}
CODE = {}


def fake_run(cmd, *a, **k):
    RUNS.append(list(cmd))
    if SLOW["s"]: time.sleep(SLOW["s"])
    key = next((x for x in cmd if x in FAKE_OUT), "")
    return _R(FAKE_OUT.get(key, "xong " + " ".join(str(x) for x in cmd[-2:])), CODE.get(key, 0))


class FakePopen:
    def __init__(self, cmd, **k): POPENS.append((list(cmd), k))


cp.subprocess.run = fake_run
cp.subprocess.Popen = FakePopen
cp.sua_fetch = lambda get=None: (SUA_SRC, VER_NOW)
srv = cp.Server(("127.0.0.1", 0), cp.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}/cpapi/"


def call(path, tok, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")


def job(j, tok="t-admin", limit=10):
    t0 = time.time()
    while time.time() - t0 < limit:
        c, r = call("job?id=" + j, tok, method="GET")
        if c != 200 or r.get("state") != "running": return c, r
        time.sleep(0.05)
    return 0, {}


ck("dấu bản trong cpapi.py khớp hằng số CPAPI_VER (dòng khởi động là dấu lệnh A dùng để biết bản mới đã chạy)",
   f"cpapi bản {cp.CPAPI_VER} chạy ở".encode() in open(os.path.join(ROOT, "cpapi.py"), "rb").read(), cp.CPAPI_VER)
c, j = call("admin/node", "t-nobody", method="GET"); ck("chưa đăng nhập → 401", c == 401, (c, j))
c, j = call("admin/node", "t-user", method="GET"); ck("khách thường xem → 403 (chỉ admin)", c == 403, (c, j))
c, j = call("admin/node", "t-user", {"do": "list"}); ck("khách thường bấm việc → 403, không chạy gì", c == 403 and not RUNS, (c, j, RUNS))
c, j = call("admin/node", "t-admin", method="GET")
ck("admin GET (máy chủ chưa từng ghi sổ) → mã máy chủ, bản cpapi, danh sách việc; chưa có bản đã cài; không đang cập nhật",
   c == 200 and j.get("node") == "win-a" and j.get("cpapi") == cp.CPAPI_VER and j.get("updating") is False and j["sw"].get("ver") is None
   and set(j.get("acts") or []) >= {"update", "list", "wallpaper", "hide", "test", "cleanup", "remake", "remake-list", "optimize", "restart", "shutdown"}, (c, j))
json.dump({"ver": "23/11e", "at": 1700000000, "upd": True, "ok": False, "auto": False, "changed": ["cpapi"], "probs": ["1 máy chưa lên"],
           "files": {"cpapi.py": True}, "last": {"ver": "23/11e", "at": 1700000000, "upd": True, "auto": False}}, open(cp.NODE_STATE_F, "w", encoding="utf-8"))
open(cp.NODE_LOG_F, "w", encoding="utf-8").write("\n".join(f"dòng {i}" for i in range(200)) + "\n== TÓM TẮT win-a ==\n")
c, j = call("admin/node", "t-admin", method="GET")
ck("admin GET → đọc đúng sổ cập nhật (bản 23/11e, cập nhật sạch, còn 1 dòng ✗) + mấy chục dòng cuối của nhật ký cập nhật",
   c == 200 and j["sw"]["ver"] == "23/11e" and j["sw"]["upd"] is True and j["sw"]["ok"] is False and j["sw"]["probs"] == ["1 máy chưa lên"]
   and j["log"].endswith("== TÓM TẮT win-a ==") and 20 < len(j["log"].splitlines()) <= 60, (c, {k: v for k, v in j.items() if k != "log"}))

c, j = call("admin/node", "t-admin", {"do": "rm -rf /"}); ck("việc lạ (lệnh tự gõ) → 400, không chạy gì", c == 400 and not RUNS, (c, j, RUNS))
c, j = call("admin/node", "t-admin", {"do": "list", "cmd": ["cmd.exe", "/c", "calc"]})
cj, r = job(j.get("job", ""))
ck("POST list → chạy đúng `python phonectl.py list` trong thư mục CloudBlue (tham số lạ trong lời gọi bị bỏ qua), việc xong trả chữ in ra",
   c == 200 and r.get("state") == "done" and r.get("out") == FAKE_OUT["list"].strip() and RUNS[-1] == [sys.executable, os.path.join(home, "phonectl.py"), "list"]
   and len(RUNS) == 1, (c, j, r, RUNS))
c, j = call("job?id=" + j.get("job", ""), "t-user", method="GET"); ck("khách thường hỏi việc của admin → 404", c == 404, (c, j))

n0 = len(RUNS)
c, j = call("admin/node", "t-admin", {"do": "cleanup"}); ck("🧹 Dọn giả lập thừa mà không gõ mã máy chủ → 400, không chạy", c == 400 and len(RUNS) == n0 and "win-a" in j.get("error", ""), (c, j))
c, j = call("admin/node", "t-admin", {"do": "cleanup", "confirm": "win-b"}); ck("… gõ SAI mã máy chủ → 400, không chạy", c == 400 and len(RUNS) == n0, (c, j))
c, j = call("admin/node", "t-admin", {"do": "remake", "confirm": ""}); ck("♻ Làm mới máy khách (mất dữ liệu) không gõ mã → 400", c == 400 and len(RUNS) == n0, (c, j))
c, j = call("admin/node", "t-admin", {"do": "cleanup", "confirm": " WIN-A "}); cj, r = job(j.get("job", ""))
ck("… gõ đúng mã (không kể hoa thường / dấu cách) → chạy `phonectl.py cleanup`", c == 200 and r.get("state") == "done" and RUNS[-1][-2:] == [os.path.join(home, "phonectl.py"), "cleanup"]
   and "Đã xoá 2" in r.get("out", ""), (c, j, r, RUNS[-1]))
c, j = call("admin/node", "t-admin", {"do": "remake-list"}); cj, r = job(j.get("job", ""))
ck("♻ xem máy cần làm mới (chỉ xem) không cần gõ mã → chạy `run.py remake.py list`", c == 200 and r.get("state") == "done" and RUNS[-1][-3:] == [os.path.join(home, "run.py"), "remake.py", "list"], (c, r, RUNS[-1]))
c, j = call("admin/node", "t-admin", {"do": "test"}); cj, r = job(j.get("job", ""))
ck("🧪 Tạo máy thử → `phonectl.py create test1 --ram 4 --cpu 4`", c == 200 and r.get("state") == "done" and RUNS[-1][-6:] == ["create", "test1", "--ram", "4", "--cpu", "4"], (c, r, RUNS[-1]))
c, j = call("admin/node", "t-admin", {"do": "optimize"}); cj, r = job(j.get("job", ""))
ck("⚡ Tối ưu Windows → chạy đúng đoạn PowerShell ghi sẵn (không nhận chữ từ web)", c == 200 and r.get("state") == "done" and RUNS[-1][0] == "powershell"
   and RUNS[-1][-1] == cp.NODE_OPTIMIZE_PS and "powercfg" in cp.NODE_OPTIMIZE_PS, (c, r, RUNS[-1][:3]))

SLOW["s"] = 0.6
c1, j1 = call("admin/node", "t-admin", {"do": "wallpaper"}); time.sleep(0.1)
c2, j2 = call("admin/node", "t-admin", {"do": "hide"})
cj, r1 = job(j1.get("job", "")); SLOW["s"] = 0.0
c3, j3 = call("admin/node", "t-admin", {"do": "hide"}); cj, r3 = job(j3.get("job", ""))
ck("đang chạy 1 việc → việc thứ 2 bị từ chối (409: 1 việc / lúc); việc đầu xong thì bấm lại được",
   c1 == 200 and c2 == 409 and r1.get("state") == "done" and c3 == 200 and r3.get("state") == "done", (c1, c2, j2, r1, c3, r3))

# cập nhật (lệnh A chạy tách rời)
n0 = len(POPENS)
c, j = call("admin/node", "t-admin", {"do": "update"})
cmd, kw = (POPENS[-1] if len(POPENS) > n0 else ([], {}))
ck(f"⬆ Cập nhật máy chủ → ghi sua-tat-ca.py vừa tải rồi chạy `python -u sua-tat-ca.py --tu-dong` TÁCH RỜI (không cửa sổ, nhóm tiến trình riêng), báo bản sẽ cài ({VER_NOW})",
   c == 200 and j.get("ver") == VER_NOW and cmd == [sys.executable, "-u", os.path.join(home, "sua-tat-ca.py"), "--tu-dong"]
   and open(os.path.join(home, "sua-tat-ca.py"), "rb").read() == SUA_SRC and kw.get("cwd") == home and kw.get("creationflags") == 0x08000200
   and kw.get("stdin") == cp.subprocess.DEVNULL, (c, j, cmd, {k: v for k, v in kw.items() if k != "stdout"}))
st = json.load(open(cp.NODE_STATE_F, encoding="utf-8")); st["running"] = {"ver": VER_NOW, "start": int(time.time()), "auto": True, "pid": 4242}
json.dump(st, open(cp.NODE_STATE_F, "w", encoding="utf-8"))
n0 = len(POPENS); c, j = call("admin/node", "t-admin", {"do": "update"})
ck("đang cập nhật dở → bấm Cập nhật lần nữa bị từ chối (409), không chạy chồng", c == 409 and len(POPENS) == n0, (c, j))
c, j = call("admin/node", "t-admin", {"do": "list"}); ck("… các việc khác cũng chờ cập nhật xong (409)", c == 409, (c, j))
c, j = call("admin/node", "t-admin", method="GET"); ck("… GET báo đang cập nhật", c == 200 and j.get("updating") is True and j["sw"]["running"]["ver"] == VER_NOW, (c, j.get("updating")))
st["running"]["start"] = int(time.time()) - 3600; json.dump(st, open(cp.NODE_STATE_F, "w", encoding="utf-8"))
c, j = call("admin/node", "t-admin", method="GET"); ck("lượt cập nhật treo quá 30 phút → không còn coi là đang cập nhật (bấm lại được)", c == 200 and j.get("updating") is False, (c, j.get("updating")))
st.pop("running"); json.dump(st, open(cp.NODE_STATE_F, "w", encoding="utf-8"))


def boom(get=None): raise RuntimeError("Chưa tải được bản cập nhật từ GitHub — thử lại sau 1 phút.")


cp.sua_fetch = boom; n0 = len(POPENS); c, j = call("admin/node", "t-admin", {"do": "update"})
ck("không tải được bản mới từ GitHub → 409 kèm lý do, không chạy gì", c == 409 and len(POPENS) == n0 and "GitHub" in j.get("error", ""), (c, j))
cp.sua_fetch = load("cpapi_n2", "cpapi.py").sua_fetch
good = lambda url, h: SUA_SRC
ck("sua_fetch: file thật → nhận, đọc đúng bản", cp.sua_fetch(good) == (SUA_SRC, VER_NOW))
bad = [("file ngắn (trang lỗi)", b'VER = "23/11z"\n# cloudblue-sua-tat-ca\n'), ("thiếu dấu cloudblue-sua-tat-ca", SUA_SRC.replace(b"cloudblue-sua-tat-ca", b"cloudblue-xxx")),
       ("thiếu dòng VER", SUA_SRC.replace(b'VER = "', b'VERX = "')), ("lỗi cú pháp Python", SUA_SRC + b"\ndef (:\n"), ("trang HTML", b"<html>" + b"x" * 30000)]
for nm, data in bad:
    try: cp.sua_fetch(lambda url, h, d=data: d); got = "nhận"
    except RuntimeError: got = "từ chối"
    ck(f"sua_fetch: {nm} → từ chối (không ghi, không chạy)", got == "từ chối", got)
seq = []
def flaky(url, h):
    seq.append(url)
    if len(seq) == 1: raise OSError("mất mạng")
    return SUA_SRC
ck("sua_fetch: đường tải thứ nhất lỗi → thử đường thứ 2", cp.sua_fetch(flaky) == (SUA_SRC, VER_NOW) and len(seq) == 2 and "raw.githubusercontent.com" in seq[1], seq)

# tắt / khởi động lại máy chủ
n0 = len(RUNS)
c, j = call("admin/node", "t-admin", {"do": "shutdown"}); ck("⏻ Tắt máy chủ không gõ mã → 400, không chạy", c == 400 and len(RUNS) == n0, (c, j))
c, j = call("admin/node", "t-admin", {"do": "shutdown", "confirm": "win-a"}); cj, r = job(j.get("job", ""))
ck("⏻ Tắt máy chủ gõ đúng mã → `phonectl.py shutdownserver` (tắt êm máy khách rồi tắt Windows), báo lại câu của máy chủ",
   c == 200 and r.get("state") == "done" and RUNS[-1][-2:] == [os.path.join(home, "phonectl.py"), "shutdownserver"] and "bấm nút nguồn" in r.get("msg", ""), (c, j, r, RUNS[-1]))
c, j = call("admin/node", "t-admin", {"do": "restart", "confirm": "win-a"}); ck("vừa bấm tắt → bấm khởi động lại ngay bị từ chối (409)", c == 409, (c, j))
cp._REBOOT["t"] = 0; CODE["rebootserver"] = 7
c, j = call("admin/node", "t-admin", {"do": "restart", "confirm": "win-a"}); cj, r = job(j.get("job", ""))
ck("⚡ Khởi động lại mà Windows chưa bật tự đăng nhập → báo lỗi NO_AUTOLOGON (web hỏi có vẫn làm không), cho bấm lại", c == 200 and r.get("state") == "error"
   and r.get("msg", "").startswith("NO_AUTOLOGON") and cp._REBOOT["t"] == 0, (c, r))
CODE.pop("rebootserver")
c, j = call("admin/node", "t-admin", {"do": "restart", "confirm": "win-a", "anyway": True}); cj, r = job(j.get("job", ""))
ck("… vẫn làm (anyway) → `phonectl.py rebootserver --anyway`", c == 200 and r.get("state") == "done" and RUNS[-1][-2:] == ["rebootserver", "--anyway"] and "khởi động lại" in r.get("msg", ""), (c, r, RUNS[-1]))
cp._REBOOT["t"] = 0; cp.IS_WIN = False
c, j = call("admin/node", "t-admin", {"do": "list"}); ck("máy chủ Linux → 400 (chỉ quản lý máy chủ Windows từ web)", c == 400, (c, j))
c, j = call("admin/node", "t-admin", method="GET"); ck("… GET vẫn xem được, ghi rõ không phải Windows", c == 200 and j.get("win") is False, (c, j.get("win")))
cp.IS_WIN = True
ck("mọi việc ghi sẵn đều là file của CloudBlue + tham số cố định (không có chỗ nào ghép chữ từ web vào lệnh)",
   all(v[1][0] in ("phonectl.py", "run.py") and all(isinstance(x, str) and re.fullmatch(r"[\w.\-]+", x) for x in v[1]) and isinstance(v[3], bool) for v in cp.NODE_ACTS.values())
   and all(cp.NODE_ACTS[k][3] for k in ("cleanup", "remake")), cp.NODE_ACTS)

# ============================================================== 2. cloudphoned: tự cập nhật theo máy chủ khác
print("2. cloudphoned · tự cập nhật theo máy chủ khác (follow_step)")
cpd = load("cpd_n", "cloudphoned.py")
ck("dấu bản trong cloudphoned.py khớp CPD_VER", f"cloudphoned bản {cpd.CPD_VER} chạy".encode() in open(os.path.join(ROOT, "cloudphoned.py"), "rb").read(), cpd.CPD_VER)
ck("cloudphoned báo metrics.sw trong báo cáo định kỳ + gọi tự theo ~5 phút / lần ở luồng riêng",
   'metrics["sw"] = sw_info()' in open(os.path.join(ROOT, "cloudphoned.py"), encoding="utf-8").read()
   and 'bg_job("follow", _bg_follow)' in open(os.path.join(ROOT, "cloudphoned.py"), encoding="utf-8").read())
NOTES = []
cpd.notify = lambda t: NOTES.append(t)
T0 = time.time()
iso = lambda ago: (datetime.datetime.now().astimezone() - datetime.timedelta(seconds=ago)).isoformat()
def node(i, ver, at_ago, upd=True, seen_ago=20, run=False):
    return {"id": i, "updated_at": iso(seen_ago), "metrics": {"sw": {"ver": ver, "at": T0 - at_ago, "upd": upd, "run": run}}}
def mine(ver, at_ago=86400, running=None):
    d = {"ver": ver, "at": int(T0 - at_ago), "upd": True, "ok": True}
    if running: d["running"] = running
    json.dump(d, open(cpd.SW_STATE_F, "w", encoding="utf-8"))
def reset():
    cpd._follow.update(due=0.0, said=None, skip=None, skip_t=0.0); cpd._follow["for"] = None
    for f in (cpd.SW_TRIES_F, cpd.SUA_FILE):
        try: os.remove(f)
        except OSError: pass
NEW = SUA_SRC.replace(b'VER = "' + VER_NOW.encode() + b'"', b'VER = "24/11a"')
GETS, SP = [], []
def get_new(url, h): GETS.append(url); return NEW
def step(rows, site=None, t=None, get=get_new, rnd=lambda a, b: 0.0):
    return cpd.follow_step(T0 if t is None else t, get, SP.append, rows, {} if site is None else site, rnd)

mine("23/11f")
ck("sw_info: đọc sổ → bản đang chạy cho web", (lambda s: s["ver"] == "23/11f" and s["upd"] is True and s["run"] is False and s["cpd"] == cpd.CPD_VER)(cpd.sw_info()), cpd.sw_info())
ck("follow_conf: chưa đặt gì → BẬT, 20 phút · web tắt → tắt · số phút kẹp trong 5 phút – 24 giờ",
   cpd.follow_conf({}) == (True, 20.0) and cpd.follow_conf({"node_update": {"auto": False}})[0] is False
   and cpd.follow_conf({"node_update": {"soak_min": 1}})[1] == 5.0 and cpd.follow_conf({"node_update": {"soak_min": "abc"}})[1] == 20.0
   and cpd.follow_conf({"node_update": {"soak_min": 99999}})[1] == 1440.0 and cpd.follow_conf({"node_update": "x"}) == (True, 20.0))
C = lambda rows, soak=20: cpd.follow_cands("23/11f", rows, T0, soak)
ck("bản mới chạy ổn ở máy chủ khác ≥ 20 phút → được chọn", C([node("win-b", "24/11a", 1500)]) == {"24/11a"})
ck("… mới cài 5 phút (chưa đủ lâu) → chưa", C([node("win-b", "24/11a", 300)]) == set())
ck("… cập nhật KHÔNG sạch (upd sai) → không", C([node("win-b", "24/11a", 1500, upd=False)]) == set())
ck("… máy chủ đó đang cập nhật dở → không", C([node("win-b", "24/11a", 1500, run=True)]) == set())
ck("… máy chủ đó mất báo cáo quá 3 phút (dịch vụ chết sau khi cập nhật?) → không", C([node("win-b", "24/11a", 1500, seen_ago=400)]) == set())
ck("… cùng bản với mình → không", C([node("win-b", "23/11f", 1500)]) == set())
ck("… chính mình (dòng của máy này) → không tính", C([node("win-a", "24/11a", 1500)]) == set())
ck("… máy chủ bản cũ không ghi sổ (không có sw) / dòng hỏng → bỏ qua, không lỗi",
   C([{"id": "win-c", "updated_at": iso(5), "metrics": {}}, {"id": "win-d", "updated_at": None, "metrics": None}, {"id": "win-e"}, node("win-b", "24/11a", 1500)]) == {"24/11a"})

reset(); mine("23/11f"); r = step([node("win-b", "24/11a", 1500)], site={"node_update": {"auto": False}})
ck("web admin TẮT tự cập nhật → không làm gì, không tải gì", r == "off" and not GETS and not SP, (r, GETS, SP))
reset(); r = step([node("win-b", "23/11f", 1500)]); ck("mọi máy chủ cùng bản → không làm gì, không tải gì", r == "none" and not GETS, (r, GETS))
reset(); mine("23/11f", running={"ver": "24/11a", "start": int(time.time()), "pid": 1}); r = step([node("win-b", "24/11a", 1500)])
ck("máy này đang cập nhật dở → không chồng thêm", r == "run" and not GETS and not SP, (r, GETS))
reset(); mine("23/11f"); r1 = step([node("win-b", "24/11a", 1500)], rnd=lambda a, b: 300.0)
r2 = step([node("win-b", "24/11a", 1500)], t=T0 + 200, rnd=lambda a, b: 300.0)
ck("vừa thấy bản mới chạy ổn → hẹn giờ lệch ngẫu nhiên (ở đây 5 phút), chưa tới giờ thì CHƯA tải, chưa chạy", (r1, r2) == ("wait", "wait") and not GETS and not SP, (r1, r2, GETS))
r3 = step([node("win-b", "24/11a", 1500)], t=T0 + 320, rnd=lambda a, b: 300.0)
ck("tới giờ → tải sua-tat-ca.py, GitHub ĐÚNG là bản đã chạy ổn (24/11a) → ghi file + chạy `--tu-dong`, ghi sổ lần thử 1",
   r3 == "go 24/11a" and len(GETS) == 1 and SP == [[sys.executable, "-u", cpd.SUA_FILE, "--tu-dong"]] and open(cpd.SUA_FILE, "rb").read() == NEW
   and json.load(open(cpd.SW_TRIES_F)) == {"24/11a": 1}, (r3, GETS, SP))
del GETS[:]; del SP[:]; cpd._follow.update(due=0.0); cpd._follow["for"] = None
r = step([node("win-b", "24/11a", 1500)])
ck("lần thử 1 hỏng (máy vẫn bản cũ) → thử lần 2", r == "go 24/11a" and len(SP) == 1 and json.load(open(cpd.SW_TRIES_F)) == {"24/11a": 2}, (r, SP))
del GETS[:]; del SP[:]; cpd._follow.update(due=0.0); cpd._follow["for"] = None
r = step([node("win-b", "24/11a", 1500)]); cpd._follow.update(due=0.0); cpd._follow["for"] = None; r2 = step([node("win-b", "24/11a", 1500)])
ck("đã tự thử 2 lần → thôi, báo admin 1 lần (Telegram), không chạy nữa", (r, r2) == ("tries", "tries") and not SP and len(NOTES) == 1 and "24/11a" in NOTES[0], (r, r2, SP, NOTES))
reset(); del GETS[:]; del SP[:]; mine("23/11f")
r = step([node("win-b", "24/11a", 1500)], get=lambda url, h: SUA_SRC.replace(b'VER = "' + VER_NOW.encode() + b'"', b'VER = "24/11b"'))
ck("GitHub đang là bản KHÁC bản đã chạy ổn (24/11b chưa máy chủ nào chạy thử) → KHÔNG tự cài", r == "nomatch" and not SP and not os.path.exists(cpd.SUA_FILE), (r, SP))
reset(); mine("24/11a")
r = step([node("win-b", "23/11f", 90000)], get=lambda url, h: NEW)
ck("mình đã ở bản mới, máy chủ khác còn bản cũ → không bao giờ lùi bản", r == "nomatch" and not SP, (r, SP))
n_get = [0]
def cnt_get(url, h): n_get[0] += 1; return NEW
r1 = step([node("win-b", "23/11f", 90000)], get=cnt_get, t=T0 + 300); r2 = step([node("win-b", "23/11f", 90000)], get=cnt_get, t=T0 + 600)
r3 = step([node("win-b", "23/11f", 90000)], get=cnt_get, t=T0 + 300 + cpd.FOLLOW_SKIP_S + 400)
ck("… và không hỏi GitHub mỗi 5 phút: 30 phút sau mới đối chiếu lại", (r1, r2, r3) == ("nomatch", "nomatch", "nomatch") and n_get[0] == 1, (r1, r2, r3, n_get))
reset(); mine("23/11f")
def nonet(url, h): raise OSError("mất mạng")
try: r = step([node("win-b", "24/11a", 1500)], get=nonet)
except RuntimeError as e: r = "lỗi: " + str(e)
ck("không tải được từ GitHub → báo lỗi ra ngoài (vòng nền ghi nhật ký, lần sau thử lại), không chạy gì", r.startswith("lỗi") and not SP and not os.path.exists(cpd.SW_TRIES_F), (r, SP))
old_on = cpd.FOLLOW_ON; cpd.FOLLOW_ON = False; reset()
r = step([node("win-b", "24/11a", 1500)]); cpd.FOLLOW_ON = old_on
ck("TU_CAP_NHAT=0 ở máy chủ này → tắt hẳn", r == "off" and not SP, r)
reset(); mine(None)
r = step([node("win-b", "24/11a", 1500), node("win-c", "24/11a", 4000)])
ck("máy chủ MỚI CÀI (chưa có sổ — VD cài từ ISO bản cũ) → tự lên bản đang chạy ổn ở các máy chủ khác", r == "go 24/11a" and len(SP) == 1, (r, SP))

# ============================================================== 3. sua-tat-ca.py: sổ cập nhật + dấu của các file
print("3. sua-tat-ca.py · sổ logs/cap-nhat.json + dấu bản của từng file")
sua = load("sua_n", "windows/sua-tat-ca.py")
for gp, local, mark, svc in sua.FILES:
    try: has = mark.encode("utf-8") in open(os.path.join(ROOT, gp), "rb").read()
    except OSError: has = False
    ck(f"dấu của {local} ({mark}) có thật trong {gp} trên kho", has)
ck("dòng khởi động (MARK_RUN) của từng dịch vụ có trong file dịch vụ đó",
   all(v.encode("utf-8") in open(os.path.join(ROOT, next(gp for gp, local, m, svc in sua.FILES if svc == k and local == sua.SVC_FILE[k])), "rb").read() for k, v in sua.MARK_RUN.items()), sua.MARK_RUN)
try: os.remove(sua.STATE_F)
except OSError: pass
for gp, local, mark, svc in sua.FILES: open(os.path.join(home, local), "wb").write(open(os.path.join(ROOT, gp), "rb").read())
sua.pid_alive = lambda pid: True
ck("bắt đầu: ghi 'đang cập nhật' (bản, giờ, pid)", sua.state_begin() is True and sua.state_read()["running"]["ver"] == sua.VER and sua.state_read()["running"]["pid"] == os.getpid(), sua.state_read())
sua.RUN.update(changed=["cpapi", "cpapi"], p_upd=[], p_rst=[], probs=["2 máy chưa lên"], done=True); sua.state_end(); s1 = sua.state_read()
ck("xong, cập nhật sạch nhưng còn dòng ✗ về máy khách → ver = bản này, upd đúng, ok sai, hết 'đang cập nhật'",
   s1.get("ver") == sua.VER and s1.get("upd") is True and s1.get("ok") is False and "running" not in s1 and s1.get("changed") == ["cpapi"]
   and s1.get("probs") == ["2 máy chưa lên"] and all(s1["files"].values()) and s1["last"]["upd"] is True, s1)
at1 = s1["at"]; s1["at"] = at1 - 5000; sua.state_write(s1)
sua.RUN.update(changed=[], p_upd=[], p_rst=[], probs=[], done=True); sua.state_begin(); sua.state_end(); s2 = sua.state_read()
ck("chạy lại lệnh A cùng bản → 'at' (lúc cài bản này) GIỮ NGUYÊN — máy chủ khác tính thời gian chạy ổn từ lúc cài, không bị tính lại", s2["at"] == at1 - 5000 and s2["ok"] is True and s2["ver"] == sua.VER, s2)
sua.VER = "99/99z"
sua.RUN.update(changed=[], p_upd=[], p_rst=["công cụ máy (cpapi) chưa chạy lại"], probs=["công cụ máy (cpapi) chưa chạy lại"], done=True); sua.state_begin(); sua.state_end(); s3 = sua.state_read()
ck("bản mới cài HỎNG (dịch vụ chưa chạy lại) → sổ vẫn ghi bản CŨ là bản đang chạy; lượt gần nhất ghi hỏng (máy chủ khác không theo máy này)",
   s3["ver"] == s2["ver"] and s3["upd"] is True and s3["at"] == s2["at"] and s3["last"] == {"ver": "99/99z", "at": s3["last"]["at"], "upd": False, "auto": False} and s3["ok"] is False, s3)
open(os.path.join(home, "cpapi.py"), "wb").write(b"# ban cu\n")
sua.RUN.update(changed=[], p_upd=[], p_rst=[], probs=[], done=True); sua.state_begin(); sua.state_end(); s4 = sua.state_read()
ck("còn file chưa phải bản mới → không tính là cập nhật sạch", s4["last"]["upd"] is False and s4["files"]["cpapi.py"] is False, s4)
sua.RUN.update(changed=[], p_upd=[], p_rst=[], probs=["dừng: khác quyền"], done=False); sua.state_begin(); sua.state_end(); s5 = sua.state_read()
ck("lệnh dừng giữa chừng (khác quyền với bảng) → không tính là cập nhật", s5["last"]["upd"] is False and s5["ok"] is False, s5)
sua.AUTO = True; st = sua.state_read(); st["running"] = {"ver": "99/99z", "start": int(time.time()), "auto": False, "pid": 77}; sua.state_write(st)
ck("lượt TỰ ĐỘNG gặp lượt khác đang chạy dở (dưới 30 phút, tiến trình còn sống) → thôi", sua.state_begin() is False and sua.state_read()["running"]["pid"] == 77)
sua.pid_alive = lambda pid: False
ck("… lượt kia đã chết (tiến trình không còn) → chạy", sua.state_begin() is True and sua.state_read()["running"]["pid"] == os.getpid())
sua.AUTO = False
src = open(os.path.join(ROOT, "windows", "sua-tat-ca.py"), encoding="utf-8").read()
ck("lượt tự động không kiểm / sửa máy khách (nhánh AUTO đứng trước nhánh kiểm máy) + luôn ghi sổ kể cả khi lỗi giữa chừng (try / finally)",
   src.index("elif AUTO:") < src.index("probs += priv_fix()") and "try: main()\n    finally: state_end()" in src)

print("%d/%d dat" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
