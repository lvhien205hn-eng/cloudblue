# -*- coding: utf-8 -*-
"""28/11f · 🧹 TỰ DỌN MÁY KẸT + 💤 XOÁ MÁY KHÔNG MỞ N NGÀY + 🕒 GIỜ MÁY CHỦ + 🖥 WINDOWS 10 1511 ỔN ĐỊNH + 🖼 ẢNH NỀN ANDROID 13+ — thử bằng đồ giả:
   1. cloudphoned · đồng hồ lệch: đo theo giờ Supabase (header Date) → now() tự bù · w32tm / chỉnh giờ Windows
   2. cloudphoned · điểm lag (Windows không WGC, CPU / card bận) + chia đơn theo % đầy + điểm lag
   3. cloudphoned · 🧹 cp_auto_clean ~5 phút (SQL v71) · 💤 máy ngủ ≥ N ngày → cp_purge_idle (không tính lúc máy chủ tắt) · idle_since lên web
   4. phonectl · dondep --mocoi (máy cp_… mồ côi, dòng web tạo lỗi / hoàn tiền) · 🖼 ảnh nền bằng app trợ giúp cbwp.apk (Android 13+)
   5. sua-tat-ca · 3b thêm đồng bộ giờ / TLS 1.2 / Windows 1511 cập nhật chỉ báo · tải từ GitHub qua PowerShell khi không có curl.exe · chứng chỉ gốc
   6. panel / cpapi / ISO máy chủ · "Tối ưu Windows" không còn lỗi Add-MpPreference khi máy không có Defender
   Chạy: python3 .github/win-check/test_2811f.py"""
import ast, contextlib, datetime as _dt, email.utils, importlib.util, io, json, os, re, ssl, sys, tempfile, time as _tm, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True)


def quiet(f, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): r = f(*a, **k)
    return r, buf.getvalue()


CPD = open(os.path.join(ROOT, "cloudphoned.py"), encoding="utf-8").read()
PCS = open(os.path.join(ROOT, "windows", "phonectl.py"), encoding="utf-8").read()
CPM, PCM = ast.parse(CPD), ast.parse(PCS)


def pick(mod, names, g, src="x.py"):
    for node in mod.body:
        if isinstance(node, (ast.FunctionDef, ast.Assign)) and (getattr(node, "name", None) in names or
                                                               (isinstance(node, ast.Assign) and any(getattr(t, "id", "") in names for t in node.targets))):
            exec(compile(ast.Module(body=[node], type_ignores=[]), src, "exec"), g)
    return g


# ============================================================== 1. đồng hồ
print("1. cloudphoned · đồng hồ máy chủ lệch → tự bù theo giờ Supabase + w32tm / chỉnh giờ Windows")
G = {"time": _tm, "datetime": _dt, "_CLK": {"off": 0.0, "s": [], "fix_t": 0.0, "set_t": 0.0, "said": 0.0, "last": ""}}
pick(CPM, ("_clk_sample", "clock_off", "now"), G, "cloudphoned.py")


class R:
    def __init__(self, date): self.headers = {"Date": date}


t = _tm.time()
for _ in range(3): G["_clk_sample"](R(email.utils.formatdate(t + 300, usegmt=True)), t, t + 0.2)
ck("Supabase chạy trước 300 giây (đồng hồ máy chủ CHẬM 5 phút, như Server 8) → lệch ≈ −300 giây", -302 <= G["clock_off"]() <= -298, G["clock_off"]())
d = (G["now"]() - _dt.datetime.now().astimezone()).total_seconds()
ck("now() trả giờ THẬT (nhanh hơn đồng hồ máy 300 giây) → hạn / đơn / máy chủ khác tính đúng", 298 <= d <= 302, d)
G["_CLK"].update(off=0.0, s=[])
G["_clk_sample"](R(email.utils.formatdate(t + 300, usegmt=True)), t, t + 3.5)
ck("lần gọi chậm (> 2 giây) → không lấy làm mẫu", G["_CLK"]["s"] == [], G["_CLK"])
for k in range(3): G["_clk_sample"](R(email.utils.formatdate(t + 1, usegmt=True)), t, t + 0.1)
ck("lệch < 3 giây (mạng / làm tròn giây) → coi như đúng giờ (0)", G["clock_off"]() == 0.0, G["_CLK"])
G["_clk_sample"](types.SimpleNamespace(headers={}), t, t)
ck("không có header Date / đồ lạ → bỏ qua, không lỗi", True)
del G["_CLK"]
ck("now() chép riêng không có _CLK (bộ thử khác) → như cũ, không lỗi", abs((G["now"]() - _dt.datetime.now().astimezone()).total_seconds()) < 2)

RUNS = []
G2 = {"time": _tm, "datetime": _dt, "WIN": True, "CLOCK_FIX": True, "NODE_ID": "win54", "_CLK": {"off": -300.0, "s": [1] * 6, "fix_t": 0.0, "set_t": 0.0, "said": 0.0, "last": ""},
      "notify": lambda t: RUNS.append(("notify", t)), "subprocess": types.SimpleNamespace(run=lambda c, **k: RUNS.append(tuple(c)) or types.SimpleNamespace(returncode=0))}
pick(CPM, ("clock_off", "_clock_job"), G2, "cloudphoned.py")
r, out = quiet(G2["_clock_job"])
ck("lệch 5 phút → bật w32time (tự chạy) + đặt máy giờ + ép đồng bộ (w32tm /resync), xoá mẫu để đo lại",
   ("sc", "config", "w32time", "start=", "auto") in RUNS and ("w32tm", "/resync", "/force") in RUNS and G2["_CLK"]["s"] == [] and "w32tm" in out, (RUNS, out))
RUNS.clear(); G2["_CLK"].update(s=[1] * 6, fix_t=_tm.time() - 600)
r, out = quiet(G2["_clock_job"])
ck("đồng bộ xong vẫn lệch (mạng chặn NTP) ≥ 120 giây → chỉnh giờ Windows theo Supabase (Set-Date +300 giây) + báo admin, lệch về 0",
   any(c[0] == "powershell" and "Set-Date -Adjust ([TimeSpan]::FromSeconds(300.0))" in c[-1] for c in RUNS if isinstance(c, tuple))
   and G2["_CLK"]["off"] == 0.0 and any(x[0] == "notify" for x in RUNS if isinstance(x, tuple) and len(x) == 2), (RUNS, out))
RUNS.clear(); G2["_CLK"].update(off=-300.0, s=[1] * 6, fix_t=_tm.time() - 600)
quiet(G2["_clock_job"])
ck("vừa chỉnh giờ < 6 giờ trước → không chỉnh lại liên tục", not any(c[0] == "powershell" for c in RUNS if isinstance(c, tuple) and c and isinstance(c[0], str)), RUNS)
RUNS.clear(); G2.update(WIN=False); G2["_CLK"].update(set_t=0.0, said=0.0)
r, out = quiet(G2["_clock_job"])
ck("máy chủ Linux / CLOCK_FIX=0 → chỉ báo (now() vẫn tự bù), không đụng giờ máy", RUNS == [] and "tự bù" in out, (RUNS, out))
RUNS.clear(); G2.update(WIN=True); G2["_CLK"].update(off=-30.0, s=[1] * 6, fix_t=0.0)
quiet(G2["_clock_job"])
ck("lệch < 60 giây → không làm gì", RUNS == [], RUNS)
ck("sb() đo giờ ở MỌI lần gọi Supabase · metrics báo clock_off_s / win_build / wgc / lag_pen",
   "_clk_sample(r, t0, time.time())" in CPD and 'metrics["clock_off_s"] = round(clock_off()); metrics["lag_pen"] = lag_pen()' in CPD
   and 'metrics["win_build"] = b; metrics["wgc"] = b >= WGC_MIN_BUILD' in CPD)

# ============================================================== 2. điểm lag + chia đơn
print("2. cloudphoned · điểm lag + chia đơn theo % đầy + điểm lag")
S = {"build": 10586, "cpu": 20.0, "gpu": None}
G3 = {"WGC_MIN_BUILD": 18362, "LAG_OLDWIN": 25.0, "win_build": lambda: S["build"], "cpu_avg5": lambda: S["cpu"], "gpu_avg5": lambda: (S["gpu"], None)}
pick(CPM, ("lag_pen", "node_lag"), G3, "cloudphoned.py")
ck("Windows 10 1511 (bản 10586, không có WGC → hình nén trong Android) → +25", G3["lag_pen"]() == 25.0, G3["lag_pen"]())
S.update(build=19045, cpu=80.0)
ck("Windows 10 22H2 · CPU thật TB 80% → +18 (0,6 mỗi % trên 50)", G3["lag_pen"]() == 18.0, G3["lag_pen"]())
S.update(build=10586, cpu=100.0, gpu=100.0)
ck("1511 + CPU 100% + card 100% → tối đa 40 điểm", G3["lag_pen"]() == 40.0, G3["lag_pen"]())
S.update(build=None, cpu=None, gpu=None)
ck("không đo được gì (máy Linux, vừa bật) → 0", G3["lag_pen"]() == 0.0)
ck("điểm lag máy chủ khác đọc từ cloud_nodes (metrics->lag_pen) · lạ / thiếu → 0 · kẹp 0–40",
   G3["node_lag"]({"lag": 25}) == 25.0 and G3["node_lag"]({}) == 0.0 and G3["node_lag"]({"lag": "x"}) == 0.0 and G3["node_lag"]({"lag": 99}) == 40.0
   and "lag:metrics->lag_pen" in CPD)
G6 = {"time": _tm, "datetime": _dt, "NODE_ID": "win-a", "NEAR_GAP": 5.0, "want": lambda row: (4.0, 4.0), "lag_pen": lambda: 25.0, "my_pct": lambda: 30.0}
pick(CPM, ("better_node", "node_pct", "node_sells", "node_lag"), G6, "cloudphoned.py")
N6 = [{"id": "win-b", "androids": "12,15", "cap_ram": 100, "alloc_ram": 50, "cap_cpu": 100, "alloc_cpu": 50, "lag": 0},       # 50% · mượt
      {"id": "win-c", "androids": "12,15", "cap_ram": 100, "alloc_ram": 20, "cap_cpu": 100, "alloc_cpu": 20, "lag": 40}]      # 20% · rất lag
G6["live_nodes"] = lambda: N6
ck("máy này 1511 đầy 30% (+25 lag = 55) · win-b 22H2 đầy 50% (55−5 ≥ 50) → nhường win-b mượt · win-c đầy 20% mà lag 40 (60) không chọn",
   G6["better_node"]({"android": "12"}) == ("win-b", 50.0), G6["better_node"]({"android": "12"}))
G6["lag_pen"] = lambda: 0.0
ck("máy này mượt (lag 0, 30%) → không nhường máy nào (win-b 50%, win-c 60 điểm)", G6["better_node"]({"android": "12"}) is None)
ck("handover chọn đích theo % đầy + điểm lag, ngưỡng 'gần đầy' vẫn theo % đầy",
   "p = node_pct(r) + node_lag(r)                                   # 28/11f: tính cả điểm lag" in CPD and "if p <= me + lag_pen() - NEAR_GAP" in CPD
   and "if me < NEAR_PCT: return False" in CPD)

# ============================================================== 3. tự dọn + máy không mở
print("3. cloudphoned · 🧹 cp_auto_clean ~5 phút · 💤 máy NGỦ ≥ N ngày → xoá vĩnh viễn (không tính lúc máy chủ tắt)")
tmp = tempfile.mkdtemp(prefix="cb2811f_")
CALLS, NOTE = [], []


class HTTPErr(Exception):
    def __init__(self, code): self.code = code


import urllib.error as _ue
STATE = {"clean": {"ok": True, "total": 3, "old_forced": 2, "switch_cancelled": 1}, "rows": [], "purge": True, "e404": False}


def fsb(method, path, body=None, extra=None):
    CALLS.append((method, path, body))
    if path == "rpc/cp_auto_clean":
        if STATE["e404"]: raise _ue.HTTPError("u", 404, "nf", {}, None)
        return STATE["clean"]
    if path.startswith("settings?"): return [{"data": STATE.get("site", {})}]
    if path.startswith("cloud_phones?node=eq."): return STATE["rows"]
    if path == "rpc/cp_purge_idle": return STATE["purge"]
    if path == "rpc/cp_idle_sync": return len(body["p_rows"])
    return None


PJ = os.path.join(tmp, "phones.json")
G7 = {"time": _tm, "datetime": _dt, "json": json, "os": os, "re": re, "urllib": __import__("urllib"), "sb": fsb, "notify": NOTE.append,
      "NODE_ID": "win54", "WIN": True, "IDLE_ON": True, "CLEAN_ON": True, "CLOCK_FIX": True, "IDLE_H_CFG": 18.0, "PHONES_JSON": PJ,
      "ALIVE_F": os.path.join(tmp, "logs", "cpd_alive.json"), "DOWN_F": os.path.join(tmp, "logs", "cpd_down.json"),
      "_clean": {"next": 0.0, "idle_next": 0.0, "site": {}, "site_t": 0.0, "down": None, "alive_t": 0.0, "said": {}},
      "_CLK": {"off": 0.0, "s": [], "fix_t": 0.0, "set_t": 0.0, "said": 0.0, "last": ""}}
G7["urllib"].error = _ue
pick(CPM, ("_site_data", "idle_purge_days", "_down_load", "alive_mark", "_down_overlap", "idle_purge", "CLEAN_LBL", "_bg_clean", "clock_off", "_clock_job",
           "parse_dt"), G7, "cloudphoned.py")
r, out = quiet(G7["_bg_clean"])
ck("gọi rpc/cp_auto_clean · có dọn → in + báo Telegram đủ từng loại", ("POST", "rpc/cp_auto_clean", {}) in CALLS and NOTE
   and "2 máy cũ đổi Android xoá kẹt" in NOTE[0] and "1 đổi Android quá 1 giờ" in NOTE[0], (CALLS[:3], NOTE, out))
CALLS.clear(); NOTE.clear(); quiet(G7["_bg_clean"])
ck("lần gọi kế trong vòng 280 giây → không gọi lại (luồng 5 phút + máy chủ khác cùng gọi)", not any(p == "rpc/cp_auto_clean" for _, p, _ in CALLS), CALLS)
G7["_clean"]["next"] = 0.0; STATE["e404"] = True; CALLS.clear()
r, out = quiet(G7["_bg_clean"])
ck("web chưa chạy SQL v71 (404) → báo 1 dòng, 30 phút sau hỏi lại", "SQL v71" in out and G7["_clean"]["next"] > _tm.time() + 1700, out)
STATE["e404"] = False

# máy ngủ
now_t = _tm.time(); DAY = 86400
phones = [{"name": "cp_aaaaaaaaaa", "sleep": int(now_t - 9 * DAY + 18 * 3600), "hold": True},     # ngủ từ 8,25 ngày trước → không dùng 9 ngày
          {"name": "cp_bbbbbbbbbb", "sleep": int(now_t - 5 * DAY), "hold": True},                 # không dùng 5,75 ngày
          {"name": "cp_cccccccccc"},                                                             # đang dùng
          {"name": "cp_dddddddddd", "sleep": int(now_t - 9 * DAY), "hold": False},                # dấu ngủ sót, đã thức
          {"name": "cp_eeeeeeeeee", "sleep": int(now_t - 7 * DAY), "hold": True}]                 # không dùng 7,75 ngày
json.dump({"phones": phones}, open(PJ, "w"))
os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
G7["_clean"]["down"] = None
fresh = _dt.datetime.now(_dt.timezone.utc)
STATE["rows"] = [{"id": "A", "name": "Máy A", "container": "cp_aaaaaaaaaa", "status": "active", "idle_since": None},
                 {"id": "B", "name": "Máy B", "container": "cp_bbbbbbbbbb", "status": "active",
                  "idle_since": (fresh - _dt.timedelta(seconds=5 * DAY + 18 * 3600 - 120)).isoformat()},      # đã ghi, lệch 2 phút → không ghi lại
                 {"id": "C", "name": "Máy C", "container": "cp_cccccccccc", "status": "active", "idle_since": fresh.isoformat()},   # đã thức → xoá idle_since
                 {"id": "D", "name": "Máy D", "container": "cp_dddddddddd", "status": "active", "idle_since": None},
                 {"id": "E", "name": "Máy E", "container": "cp_eeeeeeeeee", "status": "active", "idle_since": None}]
CALLS.clear(); NOTE.clear(); G7["_clean"]["idle_next"] = 0.0
r, out = quiet(G7["idle_purge"])
pur = [b for m, p, b in CALLS if p == "rpc/cp_purge_idle"]
sync = next((b for m, p, b in CALLS if p == "rpc/cp_idle_sync"), {"p_rows": []})
ck("máy ngủ không ai dùng 9 ngày (≥ 8) → cp_purge_idle(máy A, win54, 9 ngày) → báo admin 'không hoàn tiền' · máy 7,75 ngày / 5,75 ngày → chưa",
   len(pur) == 1 and pur[0]["p_id"] == "A" and pur[0]["p_node"] == "win54" and 8.9 <= pur[0]["p_days"] <= 9.1 and NOTE and "không hoàn tiền" in NOTE[0], (pur, NOTE))
ids = {x["id"]: x["idle_since"] for x in sync["p_rows"]}
ck("ghi idle_since lên web: A, E (mới ngủ) · C đã thức → xoá (null) · B lệch < 10 phút → không ghi lại · D dấu ngủ sót (đã thức) → không ghi",
   set(ids) == {"A", "E", "C"} and ids["C"] is None and ids["A"] and ids["E"], sync)
a_since = _dt.datetime.fromisoformat(ids["A"])
ck("idle_since = lúc bắt đầu không ai dùng (lúc ngủ − 18 giờ): A ≈ 9 ngày trước", abs((fresh - a_since).total_seconds() - 9 * DAY) < 120, a_since)
CALLS.clear(); quiet(G7["idle_purge"])
ck("gọi lại ngay → chờ 10 phút (không hỏi web mỗi 5 phút)", CALLS == [], CALLS)
json.dump([[now_t - 5 * DAY, now_t - 2 * DAY]], open(G7["DOWN_F"], "w")); G7["_clean"].update(down=None, idle_next=0.0)
for r_ in STATE["rows"]: r_["idle_since"] = ids.get(r_["id"], r_["idle_since"])
CALLS.clear(); NOTE.clear()
quiet(G7["idle_purge"])
pur = [b for m, p, b in CALLS if p == "rpc/cp_purge_idle"]
sync = next((b for m, p, b in CALLS if p == "rpc/cp_idle_sync"), {"p_rows": []}); ids2 = {x["id"]: x["idle_since"] for x in sync["p_rows"]}
ck("máy chủ TẮT 3 ngày giữa chừng (khách không mở được) → không tính: A còn 6 ngày, E 4,75 ngày → không xoá máy nào",
   pur == [] and NOTE == [], (pur, NOTE))
ck("… idle_since dời theo thời gian máy chủ tắt (A ≈ 6 ngày, B ≈ 2,75 ngày, E ≈ 4,75 ngày trước)",
   abs((fresh - _dt.datetime.fromisoformat(ids2["A"])).total_seconds() - 6 * DAY) < 120
   and abs((fresh - _dt.datetime.fromisoformat(ids2["B"])).total_seconds() - 2.75 * DAY) < 120
   and abs((fresh - _dt.datetime.fromisoformat(ids2["E"])).total_seconds() - 4.75 * DAY) < 120, ids2)
os.remove(G7["DOWN_F"]); G7["_clean"]["down"] = None
G7["_clean"].update(idle_next=0.0, site={"idle_purge_days": "0"}, site_t=_tm.time()); CALLS.clear()
quiet(G7["idle_purge"])
ck("admin đặt 0 ngày (tắt) → không xoá máy nào (máy A 9 ngày vẫn giữ)", not any(p == "rpc/cp_purge_idle" for _, p, _ in CALLS)
   and any(p.startswith("cloud_phones?node=eq.win54") for _, p, _ in CALLS), CALLS)
G7["_clean"].update(idle_next=0.0, site={"idle_purge_days": "5"}); CALLS.clear(); STATE["purge"] = False
r, out = quiet(G7["idle_purge"])
ck("admin đặt 5 ngày → A, B, E đủ ngày được hỏi xoá · web từ chối (máy khoá / admin…) → không báo xoá",
   sorted(b["p_id"] for m, p, b in CALLS if p == "rpc/cp_purge_idle") == ["A", "B", "E"] and "xoá vĩnh viễn" not in out, (CALLS, out))
STATE["purge"] = True
ck("số ngày: settings.data.idle_purge_days, thiếu / sai → 8", G7["idle_purge_days"]() == 5.0 and
   (G7["_clean"].update(site={}) or G7["idle_purge_days"]() == 8.0) and (G7["_clean"].update(site={"idle_purge_days": "abc"}) or G7["idle_purge_days"]() == 8.0))
# máy chủ tắt
json.dump({"t": _tm.time() - 7200}, open(G7["ALIVE_F"], "w")); G7["_clean"]["down"] = None
if os.path.exists(G7["DOWN_F"]): os.remove(G7["DOWN_F"])
r, out = quiet(G7["alive_mark"], True)
dn = json.load(open(G7["DOWN_F"]))
ck("bật lại sau 2 giờ tắt → ghi khoảng tắt (không tính vào thời gian máy không dùng) · ghi mốc còn chạy",
   len(dn) == 1 and 7100 < dn[0][1] - dn[0][0] < 7300 and abs(json.load(open(G7["ALIVE_F"]))["t"] - _tm.time()) < 5 and "đã tắt 2.0 giờ" in out, (dn, out))
json.dump({"t": _tm.time() - 120}, open(G7["ALIVE_F"], "w"))
quiet(G7["alive_mark"], True)
ck("khởi động lại nhanh (2 phút) → không tính là tắt", len(json.load(open(G7["DOWN_F"]))) == 1)
ck("_down_overlap: chỉ phần nằm trong khoảng hỏi", G7["_down_overlap"](dn[0][0] - 100, dn[0][0] + 100) == 100.0)
ck("vòng chính: ~5 phút bg_job('clean') + alive_mark mỗi vòng · lúc bật alive_mark(start=True) · bản 28/11f",
   'bg_job("clean", _bg_clean)' in CPD and "alive_mark()" in CPD and "alive_mark(start=True)" in CPD and 'CPD_VER = "28/11f"' in CPD
   and "cloudphoned bản 28/11f chạy" in CPD)
ck("_bg_dondep dùng --mocoi; phonectl cũ không hiểu → chạy lại như cũ", 'phonectl(["dondep", "--xoa", "--mocoi"])' in CPD
   and '"unrecognized arguments" in ((r.stdout or "") + (r.stderr or "")): r = phonectl(["dondep", "--xoa"])' in CPD)

# ============================================================== 4. phonectl
print("4. phonectl · dondep --mocoi · ảnh nền Android 13+ bằng app trợ giúp")
SBQ = []
P = {"time": _tm, "datetime": _dt, "re": re, "os": os, "json": json, "hashlib": __import__("hashlib"), "CONF": {"MEMU_TEMPLATE": "mau1"}}
pick(PCM, ("now", "parse_dt", "fmt", "DEAD_LATE", "_CP_ID_RX", "_row_dead", "_rows_by_cname", "_is_tpl_name"), P, "phonectl.py")
P["_sb_get"] = lambda q: SBQ.append(q) or [{"id": "abcdef12-3456-7890-aaaa-bbbbccccdddd", "status": "pending"}]
old = (_dt.datetime.now().astimezone() - _dt.timedelta(minutes=40)).isoformat(); new = _dt.datetime.now().astimezone().isoformat()
ck("dòng web đã huỷ → hết dùng · tạo lỗi / hoàn tiền yên ≥ 30 phút → hết dùng · vừa lỗi < 30 phút → chưa · đang dùng → không",
   P["_row_dead"]({"status": "cancelled"}) and P["_row_dead"]({"status": "error", "updated_at": old}) and P["_row_dead"]({"status": "refunded", "updated_at": old})
   and not P["_row_dead"]({"status": "error", "updated_at": new}) and not P["_row_dead"]({"status": "active"}) and not P["_row_dead"](None))
r = P["_rows_by_cname"]("cp_abcdef1234")
ck("tìm theo MÃ ĐƠN trong tên máy (máy tạo dở chưa ghi tên máy lên web): khoảng id đúng", SBQ and
   "id=gte.abcdef12-3400-0000-0000-000000000000&id=lte.abcdef12-34ff-ffff-ffff-ffffffffffff" in SBQ[-1] and r[0]["status"] == "pending", SBQ)
ck("tên không đúng kiểu cp_ + 10 ký tự → không hỏi web", P["_rows_by_cname"]("Android Device-3") is None and P["_rows_by_cname"]("cp_xyz") is None)
ck("máy mẫu (tpl_…, MEMU_TEMPLATE) không bao giờ là máy mồ côi", P["_is_tpl_name"]("tpl_a15") and P["_is_tpl_name"]("mau1") and not P["_is_tpl_name"]("cp_abcdef1234"))
ck("dondep: máy cp_… KHÔNG CÒN dòng web, TẮT, tạo ≥ 2 giờ → xoá (mồ côi) · đang chạy / mới tạo → không · dòng tạo lỗi mà máy đang chạy → không",
   'elif rr_ is not None and _CP_ID_RX.match(n) and i is not None and not run_:' in PCS and 'if born is not None and (now() - born).total_seconds() >= ORPHAN_H * 3600:' in PCS
   and 'if dead and stt in DEAD_LATE and run_:' in PCS and '"orphan": orphan' in PCS)
ck("máy mất tên: --mocoi → không có dòng web / tạo SAU lần huỷ, tắt, tạo ≥ 24 giờ → xoá; khách vừa huỷ < 10 phút vẫn chờ",
   'if force and not x["running"] and born is not None and (now() - born).total_seconds() >= LOST_ORPHAN_H * 3600:' in PCS
   and 'if why.startswith("máy ảo được tạo SAU") and force and not x["running"] and born is not None' in PCS
   and 'lost, lost_keep, lost_unk = _lost_scan(v, st, force=mocoi)' in PCS and 'dd.add_argument("--mocoi", action="store_true")' in PCS)

AD = []; RES = {"res": "OK 7 sdk=35", "marker": "", "install": "Success"}


def fadb(*a, timeout=60):
    AD.append(a); c = " ".join(a)
    out = ""
    if "cat /data/local/tmp/.br_wp2" in c: out = RES["marker"]
    elif "pm install" in c: out = RES["install"]
    elif "res.txt 2>/dev/null" in c and c.strip().startswith("-s 127.0.0.1:16384 shell cat"): out = RES["res"]
    return types.SimpleNamespace(stdout=out, returncode=0)


W = {"time": types.SimpleNamespace(time=_tm.time, sleep=lambda s: None), "os": os, "adb": fadb, "WP": "/x/wallpaper.png",
     "_wpa_local": lambda: "/x/cbwp.apk"}
pick(PCM, ("WPA_PKG", "WPA_SVC", "WPA_EXT", "_wp_by_app"), W, "phonectl.py")
r, out = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
cmds = [" ".join(a) for a in AD]
ck("chưa có dấu → cài app (pm install --user 0) → chép ảnh vào thư mục app → gọi dịch vụ → OK 7 → ghi dấu 'v2 7' → GỠ app",
   r is True and any("pm install -r --user 0 /data/local/tmp/cbwp.apk" in c for c in cmds)
   and any(c.endswith("/sdcard/Android/data/vn.cloudblue.wp/files/wp.png") and "push" in c for c in cmds)
   and any("am start-foreground-service --user 0 -n vn.cloudblue.wp/.Svc" in c and "if_id" not in c for c in cmds)
   and any("echo 'v2 7' > /data/local/tmp/.br_wp2" in c for c in cmds) and "pm uninstall vn.cloudblue.wp" in cmds[-2] + cmds[-1]
   and "không khởi động lại" in out, (cmds, out))
AD.clear(); RES["marker"] = "v2 7"
r, _ = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("đã có đúng ảnh bản này → không làm gì (không cài app)", r is False and not any("pm install" in " ".join(a) for a in AD))
AD.clear(); RES.update(marker="v1 7", res="OK 9 sdk=35")
r, _ = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("ảnh CloudBlue bản mới → chỉ thay khi ảnh nền hiện tại vẫn là id 7 (--ei if_id 7) → ghi 'v2 9'",
   r is True and any("--ei if_id 7" in " ".join(a) for a in AD) and any("echo 'v2 9'" in " ".join(a) for a in AD))
AD.clear(); RES.update(marker="v1 7", res="SKIP 12")
r, out = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("khách đã tự đổi ảnh nền (SKIP) → giữ ảnh của khách, ghi 'v2 -' (bản sau cũng không đụng)",
   r is False and any("echo 'v2 -'" in " ".join(a) for a in AD) and "giữ ảnh của khách" in out, (AD, out))
AD.clear(); RES.update(marker="v1 -")
r, _ = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("dấu không có id (khách đã đổi trước đó) → giữ, không cài app", r is False and not any("pm install" in " ".join(a) for a in AD))
AD.clear(); RES.update(marker="", res="", install="Failure [INSTALL_FAILED_X]")
r, out = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("cài app lỗi 2 lần → None (dùng cách cũ), không gọi dịch vụ", r is None and not any("start-foreground-service" in " ".join(a) for a in AD), out)
AD.clear(); RES.update(install="Success", res="ERR khong thay anh")
r, out = quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")
ck("app báo lỗi → None (dùng cách cũ) + vẫn gỡ app", r is None and any("pm uninstall vn.cloudblue.wp" in " ".join(a) for a in AD), out)
W["_wpa_local"] = lambda: None; AD.clear(); RES.update(marker="")
ck("chưa có cbwp.apk đúng md5 (chưa ghim / tải lỗi) → None, không cài gì", quiet(W["_wp_by_app"], "cp_x", "127.0.0.1:16384", "v2")[0] is None
   and not any("pm install" in " ".join(a) for a in AD))
ck("set_wallpaper: Android 13+ (sdk ≥ 33) → app trợ giúp trước, lỗi mới về cách chép file cũ · WALLPAPER_APP=0 tắt · Android ≤ 12 giữ cách cũ",
   'if CONF.get("WALLPAPER_APP", "1") == "1":' in PCS and "if sdk >= 33:" in PCS and "r = _wp_by_app(name, s_, ver, force)" in PCS
   and "if r is not None: return r" in PCS and re.search(r'WPA_FILE = \("cbwp\.apk", "([0-9a-f]{32})?"\)', PCS))
ck("phonectl 28/11f (sua-tat-ca cài theo dấu này)", 'PCTL_SUB = "28/11f"' in PCS)

# ============================================================== 5. sua-tat-ca
print("5. sua-tat-ca · 3b đồng bộ giờ / TLS 1.2 / Windows 1511 · tải qua PowerShell · chứng chỉ gốc")
home = tempfile.mkdtemp(prefix="cb_sua_"); os.environ["CB_HOME"] = home; os.makedirs(os.path.join(home, "logs"), exist_ok=True)
spec = importlib.util.spec_from_file_location("sua_2811f", os.path.join(ROOT, "windows", "sua-tat-ca.py"))
sua = importlib.util.module_from_spec(spec); spec.loader.exec_module(sua)
sua.emu_procs = lambda: []
sua.RUN.clear(); sua.RUN.update({"changed": [], "p_upd": [], "p_rst": [], "probs": [], "done": False}); sua.HW["procs"] = None
sua.ONLY_CHECK = False
SEEN = []
sua.ps = lambda script, t=90: SEEN.append(script) or ("PLAN=Ultimate\nPLAN_MIN=100\nSLEEP=0,0,0\nDEF=none\nTIME=Stopped,Disabled\nTIME_SET=1\nTLS_SET=2\n"
                                                      "BUILD=10586\nWU_SET=1\nWHEA=0\nEND=1\n")
p, out = quiet(sua.iso_tune, {})
T = sua.RUN["tune"]
ck("máy 1511: dịch vụ giờ đang tắt → vừa bật + đồng bộ · TLS 1.2 cho PowerShell · Windows Update chỉ báo (1511) → 3 việc 'vừa làm', không ✗",
   p == [] and "vừa bật dịch vụ giờ Windows" in out and "vừa bật TLS 1.2" in out and "Windows Update chỉ báo" in out
   and {"đồng bộ giờ Windows", "TLS 1.2 cho PowerShell", "Windows Update chỉ báo (1511)"} <= set(T["did"]) and T["build"] == 10586, (p, out))
scr = SEEN[-1]
ck("script 3b: w32time tự chạy + w32tm /resync · SchUseStrongCrypto + SystemDefaultTlsVersions (64 + 32 bit) · AUOptions=2 chỉ khi bản < 14393 · chữ ASCII",
   "sc.exe config w32time start= auto" in scr and "w32tm.exe /resync /force" in scr and "SchUseStrongCrypto" in scr and "SystemDefaultTlsVersions" in scr
   and "WOW6432Node" in scr and "($bn -lt 14393)" in scr and "/v AUOptions /t REG_DWORD /d 2" in scr and all(ord(ch) < 128 for ch in sua.ISO_TUNE_PS))
sua.RUN.clear(); sua.RUN.update({"changed": [], "p_upd": [], "p_rst": [], "probs": [], "done": False})
sua.ps = lambda script, t=90: "PLAN=Ultimate\nPLAN_MIN=100\nSLEEP=0,0,0\nDEF=none\nTIME=Running,Auto\nBUILD=19045\nWHEA=0\nEND=1\n"
p, out = quiet(sua.iso_tune, {})
ck("máy 22H2 đã đủ → '✓ dịch vụ giờ Windows đang chạy', không 'vừa'", p == [] and "dịch vụ giờ Windows đang chạy" in out and "vừa" not in out, out)
sua.ONLY_CHECK = True; sua.RUN.clear(); sua.RUN.update({"changed": [], "p_upd": [], "p_rst": [], "probs": [], "done": False})
sua.ps = lambda script, t=90: "PLAN=Ultimate\nPLAN_MIN=100\nSLEEP=0,0,0\nDEF=none\nTIME=Stopped,Manual\nTIME_MISS=1\nTLS_MISS=1\nBUILD=10586\nWU_MISS=1\nWHEA=0\nEND=1\n"
p, out = quiet(sua.iso_tune, {})
ck("CHỈ KIỂM → báo còn thiếu: đồng bộ giờ · TLS 1.2 · Windows Update chỉ báo (1511)", {"đồng bộ giờ Windows", "TLS 1.2 cho PowerShell", "Windows Update chỉ báo (1511)"}
   <= set(sua.RUN["tune"]["miss"]), (sua.RUN["tune"], out))
sua.ONLY_CHECK = False
# tải qua PowerShell khi không có curl.exe
RUNC = []


def frun(cmd, t=30, raw=False):
    RUNC.append(cmd)
    if cmd[0] == "powershell":
        m = re.search(r"-OutFile '([^']+)'", cmd[-1]); open(m.group(1), "wb").write(b"# cloudblue-sua-tat-ca\n" + b"x" * 3000)
    return ""


def nourl(*a, **k): raise OSError("CERTIFICATE_VERIFY_FAILED")


sua.run = frun; sua.urllib.request.urlopen = nourl
sua.os = types.SimpleNamespace(name="nt", path=os.path, makedirs=os.makedirs, remove=os.remove, environ=os.environ)
data = sua.gh_get("windows/sua-tat-ca.py")
ps_ = [c for c in RUNC if c[0] == "powershell"]
ck("Python lỗi chứng chỉ + không có curl.exe (Windows 1511) → tải bằng PowerShell ép TLS 1.2 (API GitHub trước, có Accept raw)",
   data and data.startswith(b"# cloudblue-sua-tat-ca") and ps_ and "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12" in ps_[0][-1]
   and "api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/sua-tat-ca.py?ref=main" in ps_[0][-1] and "'Accept'='application/vnd.github.raw'" in ps_[0][-1],
   (RUNC, data[:40] if data else None))
sua.os = os
# chứng chỉ gốc thêm (giả Windows)
ca = os.path.join(home, "cacert.pem")
try:
    import certifi; src_ca = certifi.where()
except Exception:
    src_ca = ssl.get_default_verify_paths().cafile or "/etc/ssl/certs/ca-certificates.crt"
open(ca, "wb").write(open(src_ca, "rb").read())
saved = (ssl._create_default_https_context, getattr(ssl, "_cb_extra", None))
try:
    if hasattr(ssl, "_cb_extra"): del ssl._cb_extra
    os.environ["SSL_CERT_FILE"] = ca
    G9 = {"os": types.SimpleNamespace(name="nt", path=os.path, environ=os.environ), "__import__": __import__}
    pick(ast.parse(open(os.path.join(ROOT, "windows", "sua-tat-ca.py"), encoding="utf-8").read()), ("_ssl_ca_extra",), G9, "sua-tat-ca.py")
    G9["_ssl_ca_extra"]()
    c1 = ssl._create_default_https_context(); c2 = ssl._create_default_https_context()
    ck("Windows: nạp THÊM chứng chỉ gốc Mozilla (SSL_CERT_FILE / certifi / pip / CloudBlue PC) vào mọi kết nối HTTPS · 1 context dùng lại",
       ca in (ssl._cb_extra or []) and c1 is c2 and c1.cert_store_stats()["x509_ca"] > 50, (getattr(ssl, "_cb_extra", None), c1.cert_store_stats()))
    c3 = ssl._create_default_https_context(cafile=ca)
    ck("gọi có tham số → context riêng (không dùng chung)", c3 is not c1)
    n0 = ssl._create_default_https_context
    G9["_ssl_ca_extra"]()
    ck("gọi lần 2 → không bọc thêm lần nữa", ssl._create_default_https_context is n0)
finally:
    ssl._create_default_https_context = saved[0]
    if saved[1] is None and hasattr(ssl, "_cb_extra"): del ssl._cb_extra
    os.environ.pop("SSL_CERT_FILE", None)
for f, nm in (("cloudphoned.py", "cloudphoned"), ("windows/phonectl.py", "phonectl"), ("windows/bluestream.py", "bluestream"), ("windows/sua-tat-ca.py", "sua-tat-ca")):
    src = open(os.path.join(ROOT, f), encoding="utf-8").read()
    ck(f"{nm}: có _ssl_ca_extra() chạy lúc nạp (Windows 1511 Lite thiếu chứng chỉ gốc)", "def _ssl_ca_extra():" in src and "\n_ssl_ca_extra()\n" in src
       and r"C:\CloudBluePC\os\cacert.pem" in src and '"pip._vendor.certifi"' in src)
BSS = open(os.path.join(ROOT, "windows", "bluestream.py"), encoding="utf-8").read()
ck("sua-tat-ca 28/11f: dấu đủ 5 file + dòng khởi động bluestream 28/11f có trong bluestream.py",
   sua.VER == "28/11f" and sua.MARK_RUN["bluestream"] in BSS and 'BS_SUB = "28/11f"' in BSS and sua.MARK_RUN["cloudphoned"] in CPD)

# ============================================================== 6. Tối ưu Windows
print("6. panel / cpapi / ISO máy chủ · Tối ưu Windows không lỗi khi không có Defender")
PAN = open(os.path.join(ROOT, "windows", "panel.py"), encoding="utf-8").read()
CPA = open(os.path.join(ROOT, "cpapi.py"), encoding="utf-8").read()
ISO = open(os.path.join(ROOT, "winpc", "maychu", "may-chu-iso.ps1"), encoding="utf-8").read()
pb = PAN[PAN.index('run_admin(r"""') + len('run_admin(r"""'):PAN.index('""", log)', PAN.index('run_admin(r"""'))]
cb = CPA[CPA.index('NODE_OPTIMIZE_PS = r"""') + len('NODE_OPTIMIZE_PS = r"""'):CPA.index('"""', CPA.index('NODE_OPTIMIZE_PS = r"""') + 25)]
for nm, b in (("panel (bảng trên máy chủ)", pb), ("cpapi (nút trên web)", cb)):
    ck(f"{nm}: Add-MpPreference chỉ chạy khi máy CÓ Defender (Get-Command) · không có → '[--] … bỏ qua' · thư mục MuMu / LD · đồng bộ giờ · TLS 1.2",
       "if (Get-Command Add-MpPreference -ErrorAction SilentlyContinue) {" in b and "May khong co Windows Defender" in b
       and b.index("Get-Command Add-MpPreference") < b.index("Add-MpPreference -ExclusionPath") and "'C:\\Program Files\\Netease'" in b
       and "w32tm /resync /force" in b and "SchUseStrongCrypto" in b and "MuMuVMMHeadless.exe" in b)
ck("panel và cpapi dùng CÙNG 1 đoạn script", pb.strip() == cb.strip())
ck("cpapi 28/11f (dòng khởi động)", 'CPAPI_VER = "28/11f"' in CPA and "cpapi bản 28/11f chạy" in CPA)
oi = ISO[ISO.index("function Optimize-Windows"):ISO.index("function Get-PanelProcs")]
ck("ISO máy chủ (cài máy mới): Optimize-Windows kiểm Defender trước + đồng bộ giờ + TLS 1.2 · bản 28.11f · chữ ASCII",
   "if (Get-Command Add-MpPreference -ErrorAction SilentlyContinue) {" in oi and oi.index("Get-Command Add-MpPreference") < oi.index("Add-MpPreference -ExclusionPath")
   and "w32tm.exe /resync /force" in oi and "SchUseStrongCrypto" in oi and "$MC_VER = '28.11f'" in ISO and all(ord(ch) < 128 for ch in oi))

print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
