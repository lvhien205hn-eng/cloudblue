# -*- coding: utf-8 -*-
"""Thử phonectl 27/11a · CHIA ĐỀU CARD ĐỒ HOẠ (gpufair): đọc % card từng tiến trình (typeperf), gộp theo máy khách, máy ăn quá phần lúc card bận
   → hạ ưu tiên card (bậc 1 → 2), hết ăn quá phần → trả lại; máy chủ Windows cũ (không có bộ đếm) → báo, không làm gì.
   python3 .github/win-check/test_gpufair.py [phonectl.py]"""
import argparse, contextlib, io, json, os, runpy, subprocess, sys, tempfile

PHC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "windows", "phonectl.py")
OK = FAIL = 0
def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:1200])

d = tempfile.mkdtemp(prefix="gf-"); os.makedirs(os.path.join(d, "redroid"))
open(os.path.join(d, "cloudphone.conf"), "w").write("EMU=mumu\nNODE_ID=win3\n")
os.environ["BLUE_HOME"] = d
g = runpy.run_path(PHC, run_name="gf_test"); G = g["cmd_gpufair"].__globals__; G["NOWIN"] = 0

HDR = ['(PDH-CSV 4.0)', r'\\WIN3\GPU Engine(pid_100_luid_0x0_0x1_phys_0_eng_0_engtype_3D)\Utilization Percentage',
       r'\\WIN3\GPU Engine(pid_100_luid_0x0_0x1_phys_0_eng_1_engtype_3D)\Utilization Percentage',
       r'\\WIN3\GPU Engine(pid_101_luid_0x0_0x1_phys_0_eng_2_engtype_VideoEncode)\Utilization Percentage',
       r'\\WIN3\GPU Engine(pid_200_luid_0x0_0x1_phys_0_eng_0_engtype_3D)\Utilization Percentage',
       r'\\WIN3\GPU Engine(pid_300_luid_0x0_0x1_phys_0_eng_0_engtype_3D)\Utilization Percentage']
def csvline(xs): return ",".join('"%s"' % x for x in xs)
def typeperf_out(rows): return "\n" + csvline(HDR) + "\n" + "\n".join(csvline(r) for r in rows) + "\nExiting, please wait...\nThe command completed successfully.\n"
CALLS = []
class R:
    def __init__(self, out, rc=0): self.stdout, self.stderr, self.returncode = out, "", rc
TP = {"out": None, "nv": "98\n"}
def fake_run(args, **kw):
    CALLS.append(list(args))
    if args[0] == "typeperf": return R(TP["out"] if TP["out"] is not None else "Error: No valid counters.\n", 0 if TP["out"] else 1)
    if args[0] == "nvidia-smi": return R(TP["nv"])
    raise OSError("không có " + args[0])
G["subprocess"] = type("S", (), {"run": staticmethod(fake_run), "TimeoutExpired": subprocess.TimeoutExpired})
PIDS = {"cp_a": [100, 101], "cp_b": [200], "cp_c": [300], "spare_1": [400]}
G["_phone_pids"] = lambda: dict(PIDS)
G["load"] = lambda: {"phones": [{"name": n} for n in ("cp_a", "cp_b", "cp_c")]}
PRIO = []
G["_gpu_prio"] = lambda pid, cls: (PRIO.append((pid, cls)), True)[1]
NOW = [1000.0]
G["time"] = type("T", (), {"time": staticmethod(lambda: NOW[0]), "sleep": staticmethod(lambda s: None)})
def run(dry=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): G["cmd_gpufair"](argparse.Namespace(dry=dry))
    out = buf.getvalue(); line = [x for x in out.splitlines() if x.startswith("GPUFAIR ")]
    return out, (json.loads(line[-1][8:]) if line else None)

print("1. Đo % card từng tiến trình (typeperf, bộ đếm GPU Engine) → gộp theo máy")
TP["out"] = typeperf_out([["11/27/2026 22:00:00.000", "0", "0", "0", "0", "0"], ["11/27/2026 22:00:01.000", "70", "10", "50", "6", "4"],
                          ["11/27/2026 22:00:02.000", "74", "12", "40", "8", "4"]])
u = G["gpu_by_pid"]()
ck("bỏ lần đo đầu (=0), cộng các nhân 3D của cùng tiến trình, KHÔNG tính nhân mã hoá video", u == {100: 83.0, 200: 7.0, 300: 4.0}, u)
ck("gọi đúng bộ đếm: typeperf \"\\GPU Engine(*)\\Utilization Percentage\" -sc 3 -si 1", CALLS and CALLS[-1][:2] == ["typeperf", r"\GPU Engine(*)\Utilization Percentage"], CALLS[-1:])

print("2. Card 98% · cp_a ăn 83% (3 máy → phần chia đều 33%, ngưỡng ăn quá phần 66%) → hạ ưu tiên card của cp_a")
out, j = run()
ck("cp_a bị HẠ ưu tiên card bậc 1 (BELOW_NORMAL) — cả 2 tiến trình của máy (máy ảo + cửa sổ); máy khác không bị đụng",
   sorted(PRIO) == [(100, 1), (101, 1)] and "HẠ ưu tiên card bậc 1" in out, (PRIO, out))
ck("báo web: card 98%, phần chia đều 33.3%, ngưỡng 66.7%, top máy ăn card (cp_a 83% bậc 1), phần đã hạ = 83%",
   j and j["total"] == 98.0 and j["fair"] == 33.3 and j["hog"] == 66.7 and j["top"][0] == {"n": "cp_a", "p": 83.0, "lv": 1} and j["held"] == 83.0, j)
ck("máy không phải của khách (spare_…) không tính", all(x["n"].startswith("cp_") for x in j["top"]), j)
PRIO.clear(); NOW[0] += 120; out, j = run()
ck("vẫn ăn quá phần nhưng chưa đủ 10 phút → giữ bậc 1 (đặt lại ưu tiên phòng khi máy vừa khởi động lại)", sorted(PRIO) == [(100, 1), (101, 1)] and j["top"][0]["lv"] == 1, (PRIO, j))
PRIO.clear(); NOW[0] += 600; out, j = run()
ck("ăn quá phần liền 10 phút → hạ thêm: bậc 2 (IDLE)", sorted(PRIO) == [(100, 0), (101, 0)] and j["top"][0]["lv"] == 2 and "bậc 2" in out, (PRIO, out))

print("3. Hết ăn quá phần → giữ thêm 10 phút rồi trả lại bình thường")
TP["out"] = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "10", "0", "0", "6", "4"], ["t2", "10", "0", "0", "6", "4"]]); TP["nv"] = "40\n"
PRIO.clear(); NOW[0] += 60; out, j = run()
ck("card hết bận (40%) nhưng mới hết ăn quá phần → vẫn giữ bậc", sorted(PRIO) == [(100, 0), (101, 0)] and j["top"][0]["lv"] == 2, (PRIO, j))
PRIO.clear(); NOW[0] += 700; out, j = run()
ck("10 phút sau → trả lại ưu tiên card BÌNH THƯỜNG (NORMAL) + báo", sorted(PRIO) == [(100, 2), (101, 2)] and "trả lại ưu tiên card bình thường" in out and j["held"] == 0, (PRIO, out))

print("4. Card bận nhưng không máy nào ăn quá phần (nhiều máy chia nhau) → không hạ ai")
TP["out"] = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "30", "0", "0", "30", "30"], ["t2", "30", "0", "0", "30", "30"]]); TP["nv"] = "95\n"
PRIO.clear(); NOW[0] += 60; out, j = run()
ck("3 máy × 30% (dưới ngưỡng 66.7%) → không đổi ưu tiên máy nào", PRIO == [] and all(x["lv"] == 0 for x in j["top"]), (PRIO, j))

print("5. Máy chủ Windows cũ (không có bộ đếm GPU Engine) / chạy thử --dry")
TP["out"] = None
out, j = run()
ck("không có bộ đếm → báo rõ (ok=false), không đổi gì", '"ok": false' in out and "GPU Engine" in out and PRIO == [], out)
TP["out"] = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "90", "0", "0", "2", "2"], ["t2", "90", "0", "0", "2", "2"]]); TP["nv"] = "99\n"
PRIO.clear(); fsz = os.path.getsize(os.path.join(d, "redroid", "gpufair.json")); out, j = run(dry=True)
ck("--dry: chỉ in, không đặt ưu tiên, không ghi sổ", PRIO == [] and j["top"][0]["n"] == "cp_a" and os.path.getsize(os.path.join(d, "redroid", "gpufair.json")) == fsz, (PRIO, j))
ck("lệnh gpufair có trong phonectl (argparse) + cloudphoned gọi ~1 phút / lần, gửi web gpu_top, phần đã hạ không tính là card quá tải",
   "gf = s.add_parser(\"gpufair\")" in open(PHC, encoding="utf-8").read()
   and all(k in open(os.path.join(os.path.dirname(PHC), "..", "cloudphoned.py"), encoding="utf-8").read() for k in ('"gpufair"]', "gpu_top=", "g_eff")))
print("\n%d/%d đạt" % (OK, OK + FAIL))
sys.exit(1 if FAIL else 0)
