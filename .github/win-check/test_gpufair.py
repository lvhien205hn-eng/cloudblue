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
TP = {"out": None, "nv": "98\n", "seq": []}
def fake_run(args, **kw):
    CALLS.append(list(args))
    if args[0] == "typeperf":
        o = TP["seq"].pop(0) if TP["seq"] else TP["out"]
        return R(o if o is not None else "Error: No valid counters.\n", 0 if o else 1)
    if args[0] == "nvidia-smi":
        if "clocks" in args[1] and TP.get("nvclk") is not None: return R(TP["nvclk"])
        if "clocks" in args[1]: return R("Field \"clocks.sm\" is not a valid field to query.\n", 2)
        return R(TP["nv"])
    if args[0] == "tasklist": return R('"System","4","Services","0","148 K"\r\n"MuMuVMMHeadless.exe","999","Console","1","2,000,000 K"\r\n')
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
   sorted(set(PRIO)) == [(100, 1), (101, 1)] and "HẠ ưu tiên card bậc 1" in out, (PRIO, out))
ck("báo web: card 98%, phần chia đều 33.3%, ngưỡng 66.7%, top máy ăn card (cp_a 83% bậc 1), phần đã hạ = 83%",
   j and j["total"] == 98.0 and j["fair"] == 33.3 and j["hog"] == 66.7 and j["top"][0] == {"n": "cp_a", "p": 83.0, "lv": 1} and j["held"] == 83.0, j)
ck("máy không phải của khách (spare_…) không tính", all(x["n"].startswith("cp_") for x in j["top"]), j)
PRIO.clear(); NOW[0] += 120; out, j = run()
ck("vẫn ăn quá phần nhưng chưa đủ 10 phút → giữ bậc 1 (đặt lại ưu tiên phòng khi máy vừa khởi động lại)", sorted(set(PRIO)) == [(100, 1), (101, 1)] and j["top"][0]["lv"] == 1, (PRIO, j))
PRIO.clear(); NOW[0] += 600; out, j = run()
ck("ăn quá phần liền 10 phút → hạ thêm: bậc 2 (IDLE)", sorted(set(PRIO)) == [(100, 0), (101, 0)] and j["top"][0]["lv"] == 2 and "bậc 2" in out, (PRIO, out))

print("3. Hết ăn quá phần → giữ thêm 10 phút rồi trả lại bình thường")
TP["out"] = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "10", "0", "0", "6", "4"], ["t2", "10", "0", "0", "6", "4"]]); TP["nv"] = "40\n"
PRIO.clear(); NOW[0] += 60; out, j = run()
ck("card hết bận (40%) nhưng mới hết ăn quá phần → vẫn giữ bậc", sorted(set(PRIO)) == [(100, 0), (101, 0)] and j["top"][0]["lv"] == 2, (PRIO, j))
PRIO.clear(); NOW[0] += 700; out, j = run()
ck("10 phút sau → trả lại ưu tiên card BÌNH THƯỜNG (NORMAL) + báo", sorted(set(PRIO)) == [(100, 2), (101, 2)] and "trả lại ưu tiên card bình thường" in out and j["held"] == 0, (PRIO, out))

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
print("6. Hạ mà máy bị ĐÓI card (card vẫn bận, máy ~0%) → trả lại ngay, 30 phút không hạ máy đó (không để máy khách bị đứng)")
os.remove(os.path.join(d, "redroid", "gpufair.json"))
HOG = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "80", "3", "0", "6", "4"], ["t2", "80", "3", "0", "6", "4"]])
STARV = typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "0.5", "0", "0", "60", "38"], ["t2", "0.5", "0", "0", "60", "38"]])
TP["seq"] = [HOG, STARV]; TP["nv"] = "98\n"; PRIO.clear(); NOW[0] += 60; out, j = run()
ck("hạ xong đo lại ngay: cp_a còn ~0% mà card vẫn 98% → trả lại bình thường NGAY + báo", PRIO[:2] == [(100, 1), (101, 1)] and PRIO[-2:] == [(100, 2), (101, 2)]
   and "ĐÓI card" in out and j["top"][0]["lv"] == 0, (PRIO, out))
TP["seq"] = [HOG]; PRIO.clear(); NOW[0] += 60; out, j = run()
ck("phút sau cp_a lại ăn 83% → KHÔNG hạ nữa (đang trong 30 phút không hạ)", PRIO == [] and j["top"][0]["lv"] == 0, (PRIO, j))
TP["seq"] = [HOG, HOG]; PRIO.clear(); NOW[0] += 1900; out, j = run()
ck("hết 30 phút → hạ lại được (đo lại thấy máy vẫn chạy → giữ bậc 1)", sorted(set(PRIO)) == [(100, 1), (101, 1)] and j["top"][0]["lv"] == 1, (PRIO, j))
TP["seq"] = [typeperf_out([["t0", "0", "0", "0", "0", "0"], ["t1", "1", "0", "0", "60", "37"], ["t2", "1", "0", "0", "60", "37"]])]; PRIO.clear(); NOW[0] += 60; out, j = run()
ck("đang bị hạ mà về sau bị đói (card vẫn bận, máy 1%) → trả lại ngay, không chờ 10 phút", sorted(set(PRIO)) == [(100, 2), (101, 2)] and "ĐÓI card" in out, (PRIO, out))
print("7. 27/11b · % card THẬT theo xung nhịp + tiến trình NGOÀI máy khách ăn card")
ck("card ở xung nghỉ (139/1911 MHz) mà nvidia-smi báo 98% → thật ~7% (không coi là quá tải); xung cao (1800/1911) → giữ 98%; thiếu xung → giữ",
   G["gpu_eff"](98.0, 139.0, 1911.0) == 7.1 and G["gpu_eff"](98.0, 1800.0, 1911.0) == 98.0 and G["gpu_eff"](98.0, None, 1911.0) == 98.0, G["gpu_eff"](98.0, 139.0, 1911.0))
TP["nvclk"] = "98, 139, 1911\n"; u_ = G["_nv_util"](); TP["nvclk"] = None; u2_ = G["_nv_util"]()
ck("_nv_util: hỏi kèm xung → % thật; driver cũ không có trường xung → hỏi lại chỉ % (98)", u_ == 7.1 and u2_ == 98.0, (u_, u2_))
os.remove(os.path.join(d, "redroid", "gpufair.json"))
HDR.append(r'\\WIN3\GPU Engine(pid_999_luid_0x0_0x1_phys_0_eng_0_engtype_3D)\Utilization Percentage')
TP["seq"] = [typeperf_out([["t0", "0", "0", "0", "0", "0", "0"], ["t1", "2", "0", "0", "3", "2", "91"], ["t2", "2", "0", "0", "3", "2", "93"]])]
TP["nvclk"] = "98, 1800, 1911\n"; PRIO.clear(); NOW[0] += 60; out, j = run()
ck("tiến trình 999 không thuộc máy khách nào ăn 92% card → báo web (tên từ tasklist, loại nhân 3D), KHÔNG hạ ưu tiên ai",
   j["other"] == [{"n": "MuMuVMMHeadless.exe", "pid": 999, "e": "3D", "p": 92.0}] and PRIO == [], (j.get("other"), PRIO))
src_cp = open(os.path.join(os.path.dirname(PHC), "..", "cloudphoned.py"), encoding="utf-8").read()
ck("cloudphoned: hỏi nvidia-smi kèm xung (có đường lùi), card bận tính bằng % THẬT, gửi web gpu_other",
   "clocks.sm,clocks.max.sm" in src_cp and 'g["eff"] if g.get("eff") is not None else g["util"]' in src_cp and "gpu_other=" in src_cp)
ck("lệnh gpufair có trong phonectl (argparse) + cloudphoned gọi ~1 phút / lần, gửi web gpu_top, phần đã hạ không tính là card quá tải",
   "gf = s.add_parser(\"gpufair\")" in open(PHC, encoding="utf-8").read()
   and all(k in open(os.path.join(os.path.dirname(PHC), "..", "cloudphoned.py"), encoding="utf-8").read() for k in ('"gpufair"]', "gpu_top=", "g_eff")))
print("8. 27/11e · máy MuMu: gộp đủ 2 tiến trình MuMuVMMHeadless mỗi máy (vỏ + máy ảo thật) khi tính % card")
g2 = runpy.run_path(PHC, run_name="gf_test2"); G2 = g2["_phone_pids"].__globals__; G2["EMU"] = "mumu"
G2["_mumu_info"] = lambda fresh=True: {0: {"name": "tpl_a12", "pid": 50, "headless_pid": -1}, 3: {"name": "cp_a", "pid": 100, "headless_pid": 101},
                                       5: {"name": "cp_b", "pid": 200, "headless_pid": 201}}
G2["_img_pids"] = lambda imgs: {101: "MuMuVMMHeadless.exe", 102: "MuMuVMMHeadless.exe", 202: "MuMuVMMHeadless.exe", 777: "MuMuVMMHeadless.exe",
                               888: "MuMuVMMHeadless.exe"} if "mumuvmmheadless.exe" in imgs else {}
G2["_hl_info"] = lambda pids: {k: v for k, v in {102: (3, 101), 202: (-1, 201), 777: (9, 1), 888: (-1, 5)}.items() if k in pids}
pp = G2["_phone_pids"]()
ck("pid máy thật gộp vào đúng máy (theo số máy trong dòng lệnh, không có thì theo pid cha); máy ảo lạ (#9 / cha lạ) KHÔNG gộp",
   pp.get("cp_a") == [101, 100, 102] and pp.get("cp_b") == [201, 200, 202] and pp.get("tpl_a12") == [50]
   and 777 not in sum(pp.values(), []) and 888 not in sum(pp.values(), []), pp)
G2["_img_pids"] = lambda imgs: {}
ck("không có tiến trình MuMuVMMHeadless thừa → như cũ (không gọi PowerShell)", G2["_phone_pids"]().get("cp_a") == [101, 100])
print("\n%d/%d đạt" % (OK, OK + FAIL))
sys.exit(1 if FAIL else 0)
