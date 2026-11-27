# -*- coding: utf-8 -*-
"""27/11j · MÁY CHỦ CÀI TAY ĐƯỢC TỐI ƯU NHƯ MÁY CÀI TỪ ISO + PHẦN MỀM TRÊN MÁY + CARD KẸT XUNG NGHỈ — thử bằng đồ giả (không cần Windows):
   1. emu_roots: dò chỗ cài giả lập (cloudphone.conf · chỗ phonectl dò lần trước · chương trình đang chạy).
   2. iso_tune: script PowerShell đúng tham số (đường dẫn trong nháy đơn, CHỈ KIỂM thì không đổi gì) · đọc kết quả → dòng in + TÓM TẮT + sổ.
   3. gpu_check: card khoẻ · card kẹt xung nghỉ (win3 27/11: 98% ở 139/1974 MHz, 9 W, SW Power Cap) · lỗi điện phần cứng · giới hạn điện bị hạ → tự
      trả mặc định · VRAM đầy · driver cũ thiếu trường.
   4. hw_report: bản Windows / giả lập / driver card / adb.
   Chạy: python3 .github/win-check/test_iso_tune.py"""
import importlib.util, io, json, os, re, sys, tempfile, contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True)


home = tempfile.mkdtemp(prefix="cb_iso_")
os.environ["CB_HOME"] = home
os.makedirs(os.path.join(home, "logs"), exist_ok=True)
spec = importlib.util.spec_from_file_location("sua_iso", os.path.join(ROOT, "windows", "sua-tat-ca.py"))
sua = importlib.util.module_from_spec(spec); spec.loader.exec_module(sua)
SRC = open(os.path.join(ROOT, "windows", "sua-tat-ca.py"), encoding="utf-8").read()


def captured(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): r = fn(*a)
    return r, buf.getvalue()


def reset():
    sua.RUN.clear(); sua.RUN.update({"changed": [], "p_upd": [], "p_rst": [], "probs": [], "done": False})
    sua.HW["procs"] = None


# ============================================================== 1. emu_roots
print("1. emu_roots · dò chỗ cài giả lập")
mumu = os.path.join(home, "Netease", "MuMuPlayer")
os.makedirs(mumu, exist_ok=True); open(os.path.join(mumu, "nx_main\\MuMuManager.exe"), "w").close()
ld = os.path.join(home, "LDPlayer9"); os.makedirs(ld, exist_ok=True); open(os.path.join(ld, "ldconsole.exe"), "w").close()
other = os.path.join(home, "rong"); os.makedirs(other, exist_ok=True)
ck("thư mục MuMu (có nx_main\\MuMuManager.exe) → mumu · LDPlayer (ldconsole.exe) → ld · thư mục khác → ''",
   sua.emu_kind(mumu) == "mumu" and sua.emu_kind(ld) == "ld" and sua.emu_kind(other) == "" and sua.emu_kind("") == "" and sua.emu_kind(None) == "")
r = sua.emu_roots({"MUMU_DIR": mumu + "\\", "LD_DIR": ""})
ck("MUMU_DIR trong cloudphone.conf (thừa dấu \\ cuối) → nhận đúng 1 lần", r == [("mumu", os.path.abspath(mumu))], r)
os.makedirs(os.path.join(home, "redroid"), exist_ok=True)
open(os.path.join(home, "redroid", "mumu_dir.txt"), "w", encoding="utf-8").write(mumu)
r = sua.emu_roots({"LD_DIR": ld})
ck("chỗ phonectl dò được lần trước (redroid/mumu_dir.txt) + LD_DIR → cả 2, không trùng", r == [("ld", os.path.abspath(ld)), ("mumu", os.path.abspath(mumu))], r)
ck("chương trình đang chạy ở chỗ lạ (không phải ổ Windows) → bỏ qua, không lỗi", sua.emu_roots({}, ["/x/y/MuMuVMMHeadless.exe", "dnplayer.exe", ""]) == [("mumu", os.path.abspath(mumu))])
ck("ps_q: nháy đơn trong đường dẫn được nhân đôi (PowerShell)", sua.ps_q("C:\\a'b") == "'C:\\a''b'")

# ============================================================== 2. iso_tune
print("2. iso_tune · tối ưu Windows như máy cài từ ISO")
SEEN = []
def fake_ps(out):
    def f(script, t=90):
        SEEN.append(script); return out
    return f
sua.emu_procs = lambda: []
reset(); sua.ONLY_CHECK = False
sua.ps = fake_ps("PLAN=Ultimate Performance\nPLAN_MIN=100\nSLEEP=0,0,0\nDEF=ok\nDEF_RT=1\nDEF_HAVE=2/2,8/8\nWHEA=0\nEND=1\n")
SEEN.clear(); p, out = captured(sua.iso_tune, {"MUMU_DIR": mumu})
scr = SEEN[0] if SEEN else ""
ck("script: $APPLY = $true · đường dẫn C:\\blue + MuMu trong nháy đơn · đủ chương trình của ISO + MuMu (không trùng)",
   "$APPLY = $true" in scr and sua.ps_q(sua.B) in scr and sua.ps_q(os.path.abspath(mumu)) in scr
   and all(sua.ps_q(x) in scr for x in sua.ISO_PROCS + sua.EMU_PROCS["mumu"]) and scr.count("'MuMuVMMHeadless.exe'") == 1
   and "__" not in scr, scr[:600])
ck("script PowerShell chỉ có chữ ASCII (gửi qua dòng lệnh Windows không bị đổi mã)", all(ord(ch) < 128 for ch in sua.ISO_TUNE_PS + sua.INV_PS + sua.EMU_PROC_PS))
nostr = lambda s: re.sub(r"'(?:[^']|'')*'", "''", re.sub(r"(?m)^\s*#.*$", "", s))          # bỏ chuỗi '...' (regex có ngoặc lẻ) rồi mới đếm
bal = lambda s, a, b: nostr(s).count(a) == nostr(s).count(b)
ck("script cân ngoặc { } ( ) [ ]", all(bal(sua.ISO_TUNE_PS, a, b) and bal(sua.INV_PS, a, b) for a, b in ("{}", "()", "[]")))
ck("máy đã đủ như ISO → không báo ✗, không ghi 'vừa', TÓM TẮT 'đã đủ'",
   p == [] and "vừa" not in out and sua.RUN["tune"]["did"] == [] and sua.RUN["tune"]["miss"] == []
   and any("đã đủ" in x for x in sua.tune_line()), out)
reset()
sua.ps = fake_ps("PLAN=Balanced\nPLAN_MIN=5\nPLAN_SET=Ultimate Performance\nPLAN_MIN2=100\nSLEEP=1800,3600,600\nSLEEP_SET=0,0,0\nHIB_SET=1\n"
                 "DEF=ok\nDEF_RT=1\nDEF_HAVE=0/2,0/8\nDEF_ADDP=C:\\blue\nDEF_ADDP=C:\\Program Files\\Netease\\MuMuPlayer\nDEF_ADDX=adb.exe\nDEF_ADDX=MuMuVMMHeadless.exe\n"
                 "DVR_SET=1\nDO_SET=1\nAUR_SET=1\nWHEA=0\nEND=1\n")
p, out = captured(sua.iso_tune, {"MUMU_DIR": mumu})
T = sua.RUN["tune"]
ck("máy cài tay thiếu hết → in từng việc vừa làm (chế độ điện, không ngủ, ngủ đông, Defender 2 thư mục + 2 chương trình, Game DVR, Windows Update)",
   p == [] and "Balanced" in out and "Ultimate Performance" in out and "vừa tắt ngủ" in out and "vừa tắt hẳn ngủ đông" in out
   and "bỏ qua 2 thư mục + 2 chương trình" in out and "vừa tắt Xbox Game DVR" in out and "không chia sẻ bản cập nhật lên mạng + không tự khởi động lại" in out
   and len(T["did"]) == 6, out)
ck("TÓM TẮT: 'vừa làm: …' liệt kê đủ", any(x.startswith("⚙ tối ưu như máy cài từ ISO — vừa làm: chế độ điện") and "Defender bỏ qua 2 thư mục" in x for x in sua.tune_line()), sua.tune_line())
reset()
sua.ps = fake_ps("PLAN=Balanced\nPLAN_MIN=5\nPLAN_SET=Balanced\nPLAN_MIN2=5\nSLEEP=0,0,0\nDEF=ok\nDEF_HAVE=0/2,0/8\nDEF_ERR=Access denied\nDEF_ERR=Access denied\nEND=1\n")
p, out = captured(sua.iso_tune, {})
ck("không đổi được chế độ điện + Defender từ chối (không phải Admin) → 2 dòng ✗ cho TÓM TẮT",
   len(p) == 2 and any("chế độ điện" in x for x in p) and any("Defender" in x and "Admin" in x for x in p), (p, out))
reset(); sua.ONLY_CHECK = True; SEEN.clear()
sua.ps = fake_ps("PLAN=Balanced\nPLAN_MIN=5\nSLEEP=1800,0,0\nSLEEP_MISS=1\nHIB_MISS=1\nDEF=ok\nDEF_HAVE=0/1,6/8\nDEF_MISSP=C:\\blue\nDEF_MISSX=adb.exe\nDEF_MISSX=node.exe\n"
                 "DVR_MISS=1\nDO_MISS=1\nAUR_MISS=1\nAV=Kaspersky Anti-Virus\nWHEA=3\nEND=1\n")
p, out = captured(sua.iso_tune, {})
ck("CHỈ KIỂM → $APPLY = $false (không đổi gì) · báo còn thiếu từng mục · phần mềm diệt virus khác · RAM lỗi WHEA → ✗",
   "$APPLY = $false" in SEEN[0] and "còn QUÉT: C:\\blue, adb.exe, node.exe" in out and "Kaspersky" in out and "WHEA 47) 3 lần" in out
   and any("WHEA" in x for x in p) and "chế độ điện" in sua.RUN["tune"]["miss"] and any(x.startswith("⚙ tối ưu như máy cài từ ISO — còn thiếu") for x in sua.tune_line()), out)
sua.ONLY_CHECK = False
reset(); sua.ps = fake_ps("PLAN=x\n")
p, out = captured(sua.iso_tune, {})
ck("PowerShell không chạy hết (thiếu END) → báo ?, không kết luận bừa, TÓM TẮT 'chưa đọc được'",
   p == [] and "không chạy hết" in out and sua.RUN["tune"]["ok"] is False and any("chưa đọc được" in x for x in sua.tune_line()), out)
reset(); sua.ps = fake_ps("DEF=none\nPLAN=High performance\nPLAN_MIN=100\nSLEEP=0,0,0\nWHEA=0\nEND=1\n")
p, out = captured(sua.iso_tune, {})
ck("máy không có Windows Defender (Windows Lite như ISO) → không báo lỗi", p == [] and "không chạy trên máy này" in out, out)

# ============================================================== 3. gpu_check
print("3. gpu_check · card đồ hoạ kẹt xung nghỉ")
Q = sua.SMI_Q.split(",")
def row(**k):
    base = {"name": "NVIDIA GeForce GTX 1080", "pstate": "P2", "utilization.gpu": "18", "clocks.sm": "1708", "clocks.max.sm": "2012", "power.draw": "43.18",
            "power.limit": "180.00", "power.default_limit": "180.00", "memory.used": "3057", "memory.total": "8192", "temperature.gpu": "48", "driver_version": "560.94"}
    base.update({kk.replace("__", "."): str(v) for kk, v in k.items()})
    return ", ".join(base[x] for x in Q)
CALLS = []
def fake_run2(rows, perf="", pl_rows=None, q_fail=False):
    st = {"n": 0}
    def f(cmd, t=30):
        CALLS.append(cmd)
        if "-q" in cmd: return 0, perf
        if "-pl" in cmd: st["pl"] = True; return 0, "Power limit for GPU 00000000:03:00.0 was set to 180.00 W from 120.00 W.\nAll done."
        if any(str(x).startswith("--query-gpu=") for x in cmd):
            q = next(str(x) for x in cmd if str(x).startswith("--query-gpu="))
            if q_fail and q == "--query-gpu=" + sua.SMI_Q: return 2, 'Field "power.default_limit" is not a valid field to query.'
            if q == "--query-gpu=" + sua.SMI_Q2:
                return 0, "NVIDIA GeForce GTX 1070, 53, 1923, 1987, 71.12, 230.00, 7421, 8192, 61, 466.77\n"
            if st.get("pl") and pl_rows: return 0, pl_rows + "\n"
            return 0, rows + "\n"
        return 1, ""
    return f
sua.smi_path = lambda: "nvidia-smi"
sua.time.sleep = lambda s: None
PERF_SW = ("    Performance State                     : P8\n    Clocks Event Reasons\n        Idle                              : Not Active\n"
           "        SW Power Cap                      : Active\n        HW Slowdown                       : Not Active\n"
           "            HW Power Brake Slowdown       : Not Active\n")
PERF_HW = PERF_SW.replace("SW Power Cap                      : Active", "SW Power Cap                      : Not Active").replace(
    "HW Slowdown                       : Not Active", "HW Slowdown                       : Active").replace("HW Power Brake Slowdown       : Not Active", "HW Power Brake Slowdown       : Active")
reset(); sua.emu_procs = lambda: []
sua.run2 = fake_run2(row())
lines, p, book = sua.gpu_check(True)
ck("card khoẻ (1708/2012 MHz) → 1 dòng thông số, không ✗, không đọc lý do", p == [] and len(lines) == 1 and "GTX 1080 · driver 560.94 · P2 · bận 18% · xung 1708/2012 MHz" in lines[0]
   and not book["cards"][0]["stuck"] and not any("-q" in c for c in CALLS), lines)
CALLS.clear(); sua.run2 = fake_run2(row(pstate="P8", utilization__gpu=98, clocks__sm=139, clocks__max__sm=1974, power__draw=9.25), perf=PERF_SW)
lines, p, book = sua.gpu_check(True)
ck("win3: bận 98% mà 139/1974 MHz, 9 W cả 3 lần đọc → ✗ KẸT XUNG NGHỈ + lý do card báo (SW Power Cap) + giới hạn điện 180/180 → khuyên khởi động lại, rồi dây nguồn",
   len(p) == 1 and "kẹt xung nghỉ (139/1974 MHz, 9.25 W)" in p[0] and "khởi động lại máy chủ" in p[0] and "8 pin" in p[0]
   and any("card báo: SW Power Cap" in x and "giới hạn điện 180/180 W" in x for x in lines) and book["cards"][0]["stuck"] is True
   and book["cards"][0]["why"] == ["SW Power Cap"] and not any("-pl" in c for c in CALLS), (lines, p))
ck("… không chạy lệnh đổi điện khi giới hạn đã đúng mặc định", not any("-pl" in c for c in CALLS))
CALLS.clear(); sua.run2 = fake_run2(row(utilization__gpu=97, clocks__sm=139, clocks__max__sm=1974, power__draw=9), perf=PERF_HW)
lines, p, book = sua.gpu_check(True)
ck("card báo HW Slowdown / HW Power Brake → khuyên kiểm dây nguồn 8 pin / riser / nguồn (không khuyên khởi động lại)",
   len(p) == 1 and "lỗi điện / phần cứng card" in p[0] and "khởi động lại" not in p[0] and book["cards"][0]["why"] == ["HW Slowdown", "HW Power Brake Slowdown"], p)
CALLS.clear()
sua.run2 = fake_run2(row(utilization__gpu=99, clocks__sm=139, clocks__max__sm=1974, power__draw=9, power__limit=120), perf=PERF_SW,
                     pl_rows=row(utilization__gpu=40, clocks__sm=1850, clocks__max__sm=1974, power__draw=95))
lines, p, book = sua.gpu_check(True)
ck("giới hạn điện bị hạ (120 < 180 W mặc định) → tự chạy nvidia-smi -pl 180 → báo đã trả về mặc định, xung lên 1850",
   any(c[-2:] == ["-pl", "180"] for c in CALLS) and any("đã trả về mặc định, xung lên 1850 MHz" in x for x in lines) and book["cards"][0].get("fixed_pl") is True, (lines, CALLS))
CALLS.clear()
sua.run2 = fake_run2(row(utilization__gpu=99, clocks__sm=139, clocks__max__sm=1974, power__draw=9, power__limit=120), perf=PERF_SW)
lines, p, book = sua.gpu_check(False)
ck("CHỈ KIỂM → không đổi giới hạn điện, chỉ báo", not any("-pl" in c for c in CALLS) and len(p) == 1 and "giới hạn điện 120/180 W" in " ".join(lines), lines)
CALLS.clear()
seq = iter([row(utilization__gpu=98, clocks__sm=139, clocks__max__sm=1974), row(utilization__gpu=60, clocks__sm=1900, clocks__max__sm=1974), row(utilization__gpu=97, clocks__sm=139, clocks__max__sm=1974)])
base_rr = fake_run2(row())
def rr(cmd, t=30):
    if any(str(x).startswith("--query-gpu=") for x in cmd): return 0, next(seq) + "\n"
    return base_rr(cmd, t)
sua.run2 = rr
lines, p, book = sua.gpu_check(True)
ck("chỉ 1–2 lần đọc thấy xung nghỉ (card vừa lên xung) → KHÔNG kết luận kẹt", p == [] and not book["cards"][0]["stuck"], lines)
sua.run2 = fake_run2(row(memory__used=7465, memory__total=8192, utilization__gpu=49, clocks__sm=1923, clocks__max__sm=1987))
lines, p, book = sua.gpu_check(True)
ck("VRAM 91% → ⚠ card phải đẩy dữ liệu qua RAM (máy khách giật) — không phải ✗", p == [] and any("VRAM card đầy 91%" in x for x in lines) and book["cards"][0]["vram_full"], lines)
sua.run2 = fake_run2(row(), q_fail=True)
lines, p, book = sua.gpu_check(True)
ck("driver cũ không có trường power.default_limit → đọc bộ trường ngắn, vẫn ra thông số", p == [] and "GTX 1070 · driver 466.77" in lines[0] and "1923/1987" in lines[0], lines)
sua.emu_procs = lambda: [r"C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe"]
sua.run2 = fake_run2(row(utilization__gpu=98, clocks__sm=139, clocks__max__sm=1974, power__draw=9), perf=PERF_SW)
lines, p, book = sua.gpu_check(True)
ck("card kẹt + đang chạy MSI Afterburner → khuyên tắt / gỡ phần mềm đó", len(p) == 1 and "MSI Afterburner" in p[0], p)
sua.smi_path = lambda: ""
lines, p, book = sua.gpu_check(True)
ck("không có nvidia-smi → 1 dòng báo, không lỗi", p == [] and "không có nvidia-smi" in lines[0] and book == {"smi": False})
sua.smi_path = lambda: "nvidia-smi"

# ============================================================== 4. hw_report
print("4. hw_report · phần mềm trên máy")
ck("nv_ver: 31.0.15.6094 → 560.94 · 27.21.14.6647 → 466.47 · lạ → ''",
   sua.nv_ver("31.0.15.6094") == "560.94" and sua.nv_ver("27.21.14.6647") == "466.47" and sua.nv_ver("1.2") == "" and sua.nv_ver("") == "")
reset(); sua.emu_procs = lambda: []
sua.RUN["tune"] = {"ok": True, "did": [], "miss": [], "emu": [["mumu", os.path.abspath(mumu)]]}
open(os.path.join(mumu, "nx_main\\MuMuNxMain.exe"), "w").close()
exe = os.path.join(os.path.abspath(mumu), "nx_main\\MuMuNxMain.exe")
SEEN.clear()
sua.ps = fake_ps("OS=Microsoft Windows 10 Pro|22H2|2009|19045.5131\nVGA=NVIDIA GeForce GTX 1080|31.0.15.6094|2024-08-14\n"
                 f"EXE={exe}|4.1.21.3240|4.1.21.3240\nEND=1\n")
sua.run2 = fake_run2(row())
sua.run = lambda cmd, t=30, raw=False: "Android Debug Bridge version 1.0.41\nVersion 35.0.2-12147458\n"
open(sua.ADB, "w").close() if os.path.isdir(os.path.dirname(sua.ADB)) else (os.makedirs(os.path.dirname(sua.ADB), exist_ok=True), open(sua.ADB, "w").close())
p, out = captured(sua.hw_report, {})
I = sua.RUN.get("inv") or {}
ck("in: Windows 10 Pro 22H2 (build 19045.5131) · MuMu 4.1.21.3240 · card GTX 1080 driver 560.94 · adb 35.0.2 · Python",
   p == [] and "Windows 10 Pro 22H2 (build 19045.5131)" in out and "MuMu 4.1.21.3240" in out and "driver 560.94 (2024-08-14)" in out
   and "adb 35.0.2" in out and I.get("adb") == "35.0.2" and I.get("emu") == ["MuMu 4.1.21.3240"] and sua.ps_q(exe) in SEEN[0], out)
tl = sua.tune_line()
ck("TÓM TẮT có dòng 🖥 phần mềm (để so với máy cài từ ISO)", any(x.startswith("🖥 Windows 10 Pro 22H2") and "MuMu 4.1.21.3240" in x and "adb 35.0.2" in x for x in tl), tl)

# ============================================================== 5. nối vào lệnh A + sổ
print("5. nối vào lệnh A / lượt tự cập nhật + sổ cập nhật")
ck("main(): chạy 3b + 3c ngay sau 'tự chạy' (cả lượt TỰ ĐỘNG), lỗi không làm dừng lệnh A",
   SRC.index("probs += fix_autostart()") < SRC.index("try: probs += iso_tune(c)") < SRC.index("try: probs += hw_report(c)") < SRC.index("e = ensure_running(c)", SRC.index("try: probs += hw_report(c)"))
   and "except Exception as e_: say(f\"   (tối ưu như ISO lỗi: {e_})\")" in SRC)
ck("TÓM TẮT in dòng tối ưu + phần mềm", "for ln in tune_line(): say(\"   \" + ln)" in SRC)
reset(); sua.RUN.update(done=True); sua.RUN["tune"] = {"ok": True, "did": ["tắt Game DVR"], "miss": []}; sua.RUN["inv"] = {"adb": "35.0.2"}
try: os.remove(sua.STATE_F)
except OSError: pass
sua.state_begin(); sua.state_end(); st = json.load(open(sua.STATE_F, encoding="utf-8"))
ck("sổ logs/cap-nhat.json ghi kèm tune + inv (web đọc sau)", st.get("tune", {}).get("did") == ["tắt Game DVR"] and st.get("inv", {}).get("adb") == "35.0.2", st)
ck("bản sua-tat-ca 27/11j", sua.VER == "27/11j")

print("%d/%d dat" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
