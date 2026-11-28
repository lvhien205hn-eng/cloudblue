# -*- coding: utf-8 -*-
"""27/11j · MÁY CHỦ CÀI TAY ĐƯỢC TỐI ƯU NHƯ MÁY CÀI TỪ ISO + PHẦN MỀM TRÊN MÁY + CARD KẸT XUNG NGHỈ — thử bằng đồ giả (không cần Windows):
   1. emu_roots: dò chỗ cài giả lập (cloudphone.conf · chỗ phonectl dò lần trước · chương trình đang chạy).
   2. iso_tune: script PowerShell đúng tham số (đường dẫn trong nháy đơn, CHỈ KIỂM thì không đổi gì) · đọc kết quả → dòng in + TÓM TẮT + sổ.
   3. gpu_check: card khoẻ · card kẹt xung nghỉ (win3 27/11: 98% ở 139/1974 MHz, 9 W, SW Power Cap) · lỗi điện phần cứng · giới hạn điện bị hạ → tự
      trả mặc định · VRAM đầy · driver cũ thiếu trường.
   4. hw_report: bản Windows / giả lập / driver card / adb.
   27/11l: bản MuMu / LD đọc từ thông tin gỡ cài đặt của Windows (MuMu bản mới không ghi bản trong file chạy) · thư mục nx_main không thành chỗ cài
   thứ 2 · sổ nhớ lần tối ưu phải sửa gì (web hiện cả khi các lần sau báo đủ) · cloudphoned + phonectl tìm nvidia-smi ở thư mục NVSMI (driver cũ).
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
nx = os.path.join(mumu, "nx_main"); os.makedirs(nx, exist_ok=True); open(os.path.join(nx, "MuMuManager.exe"), "w").close()
r = sua.emu_roots({"MUMU_DIR": nx + os.sep, "LD_DIR": ""})
ck("27/11l · thư mục nx_main (cũng có MuMuManager.exe) → gộp về thư mục cài MuMu, không thành 2 chỗ (win54 27/11k báo 2 MuMu)",
   sua.emu_kind(nx) == "mumu" and r == [("mumu", os.path.abspath(mumu))], r)

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
A = sua.app_list(['MuMuPlayer|4.1.24.3700|C:\\Program Files\\Netease\\MuMuPlayer\\|"C:\\Program Files\\Netease\\MuMuPlayer\\nx_main\\MuMuNxMain.exe",0|'
                  '"C:\\Program Files\\Netease\\MuMuPlayer\\uninstall.exe" /S',
                  'LDPlayer9|9.1.40.0||C:\\LDPlayer\\LDPlayer9\\dnplayer.exe,0|C:\\LDPlayer\\LDPlayer9\\dnuninst.exe /S', 'Rong||C:\\x|', 'MsiX|1.0||MsiExec.exe /X{AB}|C:\\'])
ck("27/11l · app_list: đọc bản + đường dẫn (bỏ nháy, ',0', tham số, dấu \\ cuối) · mục không có bản → bỏ · ổ trống 'C:\\' → bỏ",
   A == [("4.1.24.3700", ["c:\\program files\\netease\\mumuplayer", "c:\\program files\\netease\\mumuplayer\\nx_main\\mumunxmain.exe",
                          "c:\\program files\\netease\\mumuplayer\\uninstall.exe"]),
         ("9.1.40.0", ["c:\\ldplayer\\ldplayer9\\dnplayer.exe", "c:\\ldplayer\\ldplayer9\\dnuninst.exe"]), ("1.0", ["msiexec.exe"])], A)
ck("27/11l · app_ver: đúng thư mục cài · không lẫn MuMuPlayer với MuMuPlayer-12.0 (chung đầu tên) · mục chỉ ghi thư mục cha (khớp lỏng) thua mục khớp chắc",
   sua.app_ver(A, "C:\\Program Files\\Netease\\MuMuPlayer") == "4.1.24.3700" and sua.app_ver(A, "c:/program files/netease/mumuplayer/") == "4.1.24.3700"
   and sua.app_ver(A, "C:\\Program Files\\Netease\\MuMuPlayer-12.0") == "" and sua.app_ver(A, "C:\\LDPlayer\\LDPlayer9") == "9.1.40.0"
   and sua.app_ver([("1", ["c:\\program files\\netease"]), ("2", ["c:\\program files\\netease\\mumuplayer\\x.exe"])], "C:\\Program Files\\Netease\\MuMuPlayer") == "2"
   and sua.app_ver([("1", ["c:\\program files\\netease"])], "C:\\Program Files\\Netease\\MuMuPlayer") == "1" and sua.app_ver(A, "C:\\") == "")
ck("27/11l · script đọc thông tin gỡ cài đặt (HKLM + WOW6432Node + HKCU) cho MuMu / LDPlayer / MEmu, chỉ chữ ASCII, không có nháy kép",
   "CurrentVersion\\Uninstall\\*" in sua.INV_PS and "WOW6432Node" in sua.INV_PS and "HKCU:" in sua.INV_PS and "'APP=' + $k.PSChildName" in sua.INV_PS
   and "MuMu|LDPlayer|leidian|MEmu|Microvirt" in sua.INV_PS and '"' not in sua.INV_PS)
reset(); sua.emu_procs = lambda: []
sua.RUN["tune"] = {"ok": True, "did": [], "miss": [], "emu": [["mumu", os.path.abspath(mumu)]]}
mgr = os.path.join(os.path.abspath(mumu), "nx_main\\MuMuManager.exe")
SEEN.clear()
sua.ps = fake_ps("OS=Microsoft Windows 10 Pro||1511|10586.0\nVGA=NVIDIA GeForce GTX 1070|27.21.14.6677|2021-06-08\n"
                 f"EXE={exe}||\nEXE={mgr}|4.0.0.9|4.0.0.9\nAPP=MuMuPlayer|4.1.24.3700|{os.path.abspath(mumu)}|\"{exe}\",0|\n"
                 f"APP=MuMuPlayer-12.0|4.0.1.1|{os.path.abspath(mumu)}-12.0||\nEND=1\n")
p, out = captured(sua.hw_report, {})
I = sua.RUN.get("inv") or {}
ck("27/11l · máy như win54: file chạy MuMu không ghi bản → lấy bản từ thông tin gỡ cài đặt (4.1.24.3700), không lẫn MuMuPlayer-12.0 · hỏi bản MỌI file chạy",
   I.get("emu") == ["MuMu 4.1.24.3700"] and "Windows 10 Pro 1511 (build 10586.0)" in out and "driver 466.77 (2021-06-08)" in out
   and sua.ps_q(exe) in SEEN[0] and sua.ps_q(mgr) in SEEN[0], (I, out))
reset(); sua.RUN["tune"] = {"ok": True, "did": [], "miss": [], "emu": [["mumu", os.path.abspath(mumu)]]}
sua.ps = fake_ps(f"OS=Microsoft Windows 10 Pro|22H2|2009|19045.5131\nEXE={exe}||\nEXE={mgr}|4.0.0.9|4.0.0.9\nEND=1\n")
p, out = captured(sua.hw_report, {})
ck("27/11l · không có thông tin gỡ cài đặt → bản của file chạy ĐẦU TIÊN có ghi bản (MuMuNxMain trống → MuMuManager 4.0.0.9)",
   (sua.RUN.get("inv") or {}).get("emu") == ["MuMu 4.0.0.9"], out)
reset(); sua.RUN["tune"] = {"ok": True, "did": [], "miss": [], "emu": [["mumu", os.path.abspath(mumu)]]}
sua.ps = fake_ps(f"EXE={exe}||\nEND=1\n")
p, out = captured(sua.hw_report, {})
ck("… không file nào ghi bản → '(không đọc được bản)', không lỗi", (sua.RUN.get("inv") or {}).get("emu") == ["MuMu (không đọc được bản)"] and p == [], out)

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
ck("bản sua-tat-ca 28/11c", sua.VER == "28/11c")
reset(); sua.RUN.update(done=True); sua.RUN["tune"] = {"ok": True, "did": ["chế độ điện hiệu năng cao nhất", "tắt Game DVR"], "miss": []}
os.remove(sua.STATE_F); sua.state_begin(); sua.state_end(); st = json.load(open(sua.STATE_F, encoding="utf-8"))
fx = st.get("tune_fix") or {}
ck("27/11l · lần tối ưu có sửa → sổ nhớ tune_fix {lúc, đã sửa gì}", fx.get("did") == ["chế độ điện hiệu năng cao nhất", "tắt Game DVR"] and isinstance(fx.get("at"), int), st)
reset(); sua.RUN.update(done=True); sua.RUN["tune"] = {"ok": True, "did": [], "miss": []}
sua.state_begin(); sua.state_end(); st2 = json.load(open(sua.STATE_F, encoding="utf-8"))
ck("… các lần sau báo đủ → tune.did trống nhưng tune_fix GIỮ NGUYÊN (web vẫn hiện lần sửa)", st2.get("tune", {}).get("did") == [] and st2.get("tune_fix") == fx, st2)
json.dump({"ver": "27/11j", "tune": {"ok": True, "did": ["không ngủ"]}, "last": {"ver": "27/11j", "at": 1764200000}}, open(sua.STATE_F, "w", encoding="utf-8"))
reset(); sua.RUN.update(done=True); sua.RUN["tune"] = {"ok": True, "did": [], "miss": []}
sua.state_begin(); sua.state_end(); st3 = json.load(open(sua.STATE_F, encoding="utf-8"))
ck("… máy mới chạy 27/11j (sổ có tune.did, chưa có tune_fix) → giữ lần sửa đó với giờ của lượt 27/11j", st3.get("tune_fix") == {"at": 1764200000, "did": ["không ngủ"]}, st3)

# ============================================================== 6. cloudphoned 27/11k: card kẹt xung = đầy (ngừng nhận máy mới)
print("6. cloudphoned 27/11k · card kẹt xung nghỉ tính là ĐẦY")
import ast
CPD = open(os.path.join(ROOT, "cloudphoned.py"), encoding="utf-8").read()
mod = ast.parse(CPD); G = {}
for node in mod.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("gpu_stuck", "gpu_eff"):
        exec(compile(ast.Module(body=[node], type_ignores=[]), "cloudphoned.py", "exec"), G)
ck("win3: 98% ở 139/1974 MHz, 9/180 W → kẹt → % dùng để chia đơn = 100 (máy chủ ngừng nhận máy mới)",
   G["gpu_stuck"](98.0, 139.0, 1974.0, 9.35, 180.0) is True and G["gpu_eff"](98.0, 139.0, 1974.0, 9.35, 180.0) == 100.0)
ck("card đang nghỉ thật (40% ở xung nghỉ) → vẫn tính theo xung như 27/11b (~3%)", G["gpu_stuck"](40.0, 139.0, 1974.0, 9.0, 180.0) is False and G["gpu_eff"](40.0, 139.0, 1974.0, 9.0, 180.0) == 2.8)
ck("card vừa lên tải (xung chưa lên nhưng điện đã cao) → không kẹt, giữ cách tính cũ", G["gpu_stuck"](95.0, 300.0, 1987.0, 150.0, 230.0) is False)
ck("card khoẻ xung cao → giữ nguyên %; thiếu xung / điện → không kết luận kẹt",
   G["gpu_eff"](53.0, 1923.0, 1987.0, 71.0, 230.0) == 53.0 and G["gpu_stuck"](98.0, None, 1974.0) is False and G["gpu_stuck"](98.0, 139.0, 1974.0) is True
   and G["gpu_eff"](98.0, None, 1974.0) == 98.0)
ck("gpus() ghi cờ stuck + chia đơn dùng % mới; Telegram có lời báo KẸT XUNG NGHỈ riêng; bản cloudphoned 28/11c",
   'g["eff"] = gpu_eff(g["util"], g["clk"], g["clk_max"], g["pwr"], g["pwr_max"])' in CPD and 'g["stuck"] = True' in CPD
   and "card đồ hoạ KẸT XUNG NGHỈ" in CPD and 'sk = [g for g in g_list if g.get("stuck")]' in CPD and 'CPD_VER = "28/11c"' in CPD
   and "cloudphoned bản 28/11c chạy" in CPD)
ck("sua-tat-ca 28/11c: dấu cloudphoned 28/11c + cpapi 27/11n (cài + nhật ký khởi động)", ("cloudphoned.py", "cloudphoned.py", "cloudphoned bản 28/11c", "cloudphoned") in sua.FILES
   and sua.MARK_RUN["cloudphoned"] == "cloudphoned bản 28/11c" and ("cpapi.py", "cpapi.py", "cpapi bản 27/11n", "cpapi") in sua.FILES
   and sua.MARK_RUN["cpapi"] == "cpapi bản 27/11n")
ck("27/11l · gpus() gọi nvidia-smi qua smi_bin() (không còn gọi trần 'nvidia-smi' → win54 driver 466.77 hết 'không đọc được card')",
   '[smi_bin(), "--query-gpu=" + q' in CPD and 'subprocess.run(["nvidia-smi"' not in CPD and "NVSMI\\nvidia-smi.exe" in CPD and "DriverStore" in CPD)
import shutil as _sh, time as _tm
for node in mod.body:
    if isinstance(node, ast.FunctionDef) and node.name == "smi_bin":
        exec(compile(ast.Module(body=[node], type_ignores=[]), "cloudphoned.py", "exec"), G)
G.update(_SMI={"p": None, "t": 0.0}, shutil=_sh, os=os, time=_tm, WIN=False)
fake = tempfile.mkdtemp(prefix="cb_smi_"); fp = os.path.join(fake, "nvidia-smi"); open(fp, "w").close(); os.chmod(fp, 0o755)
old_path = os.environ.get("PATH", "")
os.environ["PATH"] = "/nonexistent"; a1 = G["smi_bin"]()
os.environ["PATH"] = fake + os.pathsep + old_path; a2 = G["smi_bin"](); G["_SMI"]["t"] -= 700; a3 = G["smi_bin"]()
os.environ["PATH"] = old_path
ck("27/11l · smi_bin: không thấy → 'nvidia-smi' · nhớ kết quả · quá 10 phút dò lại (vừa cài driver)", a1 == "nvidia-smi" and a2 == "nvidia-smi" and a3 == fp, (a1, a2, a3))

print("7. cloudphoned 27/11k · báo tối ưu như ISO + phần mềm trên máy lên web (metrics.sw.tune / inv)")
for node in mod.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_small", "sw_tune"):
        exec(compile(ast.Module(body=[node], type_ignores=[]), "cloudphoned.py", "exec"), G)
G["json"] = json
st = {"tune": {"ok": True, "did": ["tắt Game DVR"], "miss": [], "plan": "Ultimate Performance", "defender": "ok", "av": [], "whea": 0, "emu": [["mumu", "C:\\x"]]},
      "inv": {"os": "Windows 10 Pro 22H2 (build 19045.5131)", "emu": ["MuMu 4.1.21"], "vga": ["NVIDIA GeForce GTX 1080 · driver 560.94"], "adb": "35.0.2", "py": "3.12.7",
              "clock_tools": [], "gpu": {"smi": True, "cards": [{"name": "GTX 1080", "drv": "560.94", "stuck": True, "why": ["SW Power Cap"], "util": 98, "vram_full": False}]}}}
tu, iv = G["sw_tune"](st)
ck("sw_tune: gửi gọn (không gửi đường dẫn giả lập, số đo chi tiết) — tune: ok/did/miss/plan/defender/av/whea · inv: os/emu/vga/adb/py/tools + card (tên, driver, kẹt, lý do)",
   tu == {"ok": True, "did": ["tắt Game DVR"], "miss": [], "plan": "Ultimate Performance", "defender": "ok", "av": [], "whea": 0}
   and iv["os"].startswith("Windows 10") and iv["gpu"] == [{"name": "GTX 1080", "drv": "560.94", "stuck": True, "why": ["SW Power Cap"], "vram_full": False}] and "emu" not in tu, (tu, iv))
ck("sổ cũ (chưa có tune / inv) → None, None · quá dài → bỏ (không làm phình metrics)",
   G["sw_tune"]({}) == (None, None) and G["sw_tune"]({"tune": {"ok": True, "did": ["x" * 3000]}})[0] is None)
st["tune_fix"] = {"at": 1764200000, "did": ["không ngủ", "tắt Game DVR"]}
tu, iv = G["sw_tune"](st)
ck("27/11l · sổ có tune_fix → web nhận tune.fix {lúc, đã sửa gì}; sổ không có → không gửi fix",
   tu.get("fix") == {"at": 1764200000, "did": ["không ngủ", "tắt Game DVR"]} and "fix" not in G["sw_tune"]({"tune": {"ok": True, "did": []}})[0], tu)
ck("sw_info gửi kèm tune + inv", '"run": sw_running(st), "last": last, "cpd": CPD_VER, "follow": FOLLOW_ON, "first": True, "win": WIN, "tune": tu, "inv": iv}' in CPD)

print("8. phonectl 27/11l · chia đều card đo % card bằng nvidia-smi tìm đủ chỗ")
PC = open(os.path.join(ROOT, "windows", "phonectl.py"), encoding="utf-8").read()
ck("_nv_util gọi nvidia-smi qua _smi_exe() (PATH → System32 → NVSMI → kho driver) · PCTL_SUB 27/11n · sua-tat-ca cài theo dấu 27/11n",
   "exe = _smi_exe()" in PC and 'subprocess.run([exe, "--query-gpu=" + q' in PC and 'subprocess.run(["nvidia-smi"' not in PC.split("def _nv_util")[1].split("def gpufair_plan")[0]
   and 'PCTL_SUB = "27/11n"' in PC and ("windows/phonectl.py", "phonectl.py", 'PCTL_SUB = "27/11n"', None) in sua.FILES)
pm = ast.parse(PC); G2 = {"shutil": _sh, "glob": __import__("glob"), "os": os}
for node in pm.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_smi_exe":
        exec(compile(ast.Module(body=[node], type_ignores=[]), "phonectl.py", "exec"), G2)
os.environ["PATH"] = "/nonexistent"; b1 = G2["_smi_exe"](); os.environ["PATH"] = fake + os.pathsep + old_path; b2 = G2["_smi_exe"](); os.environ["PATH"] = old_path
ck("_smi_exe: không thấy → 'nvidia-smi' (như cũ) · có trong PATH → đường dẫn đó", b1 == "nvidia-smi" and b2 == fp, (b1, b2))

print("9. phonectl 27/11m · 🔓 Root theo app trên Android 9 (cpsu mới) + lý do lỗi đúng dòng")
import hashlib
md5 = lambda p: hashlib.md5(open(os.path.join(ROOT, p), "rb").read()).hexdigest()
ck("CPSU_FILES ghim đúng md5 2 file trong windows/ (máy chủ tải đúng bản, file lạ không dùng)",
   ('"cpsu": ("cpsu-x86_64", "%s")' % md5("windows/cpsu-x86_64")) in PC and ('"su": ("cpsu-su-x86_64", "%s")' % md5("windows/cpsu-su-x86_64")) in PC)
for node in pm.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_root_why":
        exec(compile(ast.Module(body=[node], type_ignores=[]), "phonectl.py", "exec"), G2)
W = G2["_root_why"]
ck("Android 9 bản cũ: INSTALL_FAIL copy … + STOPPED → báo dòng INSTALL_FAIL (không chỉ 'STOPPED')",
   W("INSTALL_FAIL copy No such file or directory\nSTOPPED\n") == "INSTALL_FAIL copy No such file or directory (daemon không chạy)")
ck("cảnh báo cpsu: … → báo cảnh báo · chỉ có STOPPED → STOPPED · rỗng → 'máy không trả lời'",
   W("cpsu: socket @cpsu already in use\nINSTALL_OK ramdisk=/debug_ramdisk tmpfs=1 su=/debug_ramdisk/su made=0\nSTOPPED") == "cpsu: socket @cpsu already in use (daemon không chạy)"
   and W("STOPPED\n") == "STOPPED" and W("") == "máy không trả lời" and W(None) == "máy không trả lời")
ck("_root_apply báo lỗi qua _root_why", 'return False, "Chưa bật được root: " + _root_why(o)' in PC)

# ============================================================== 28/11c · 🤖 tự ngừng / tự nhận máy theo mức đầy
print("28/11c · cloudphoned tự Ngừng nhận máy khi đầy ≥ ngưỡng, tự Nhận máy lại khi giảm ≤ ngưỡng − 20% liên tục N phút")
G3 = {}
for node in mod.body:
    if isinstance(node, ast.FunctionDef) and node.name == "autopause_plan":
        exec(compile(ast.Module(body=[node], type_ignores=[]), "cloudphoned.py", "exec"), G3)
P = G3["autopause_plan"]; T0 = 1764300000.0
st, a = P({}, True, False, 96.0, T0, 95, 20, 5)
ck("đang nhận máy, đầy 96% ≥ 95% → TỰ NGỪNG (ghi sổ auto + lúc + mức)", a == "pause" and st.get("auto") is True and st.get("lv") == 96.0 and st.get("at") == T0, (st, a))
ck("đầy 94% < 95% → không làm gì", P({}, True, False, 94.0, T0, 95, 20, 5) == ({}, None))
st2, a2 = P(st, False, False, 80.0, T0 + 60, 95, 20, 5)
ck("đang tự ngừng, còn 80% (> 75%) → vẫn ngừng", a2 is None and st2.get("auto") and "low" not in st2, (st2, a2))
st3, a3 = P(st2, False, False, 74.0, T0 + 120, 95, 20, 5)
ck("xuống 74% (≤ 75%) → bắt đầu đếm, CHƯA nhận lại ngay", a3 is None and st3.get("low") == T0 + 120, (st3, a3))
st4, a4 = P(st3, False, False, 76.0, T0 + 200, 95, 20, 5)
ck("lên lại 76% trước đủ 5 phút → bỏ đếm", a4 is None and "low" not in st4, (st4, a4))
st5, a5 = P(dict(st4, low=T0 + 300), False, False, 70.0, T0 + 300 + 5 * 60, 95, 20, 5)
ck("≤ 75% liên tục đủ 5 phút → TỰ NHẬN MÁY LẠI, xoá sổ", a5 == "resume" and st5 == {}, (st5, a5))
ck("admin ngừng tay (không phải tự ngừng) → KHÔNG tự nhận lại (luật cũ của web lo)", P({}, False, False, 10.0, T0, 95, 20, 5) == ({}, None))
ck("⛔ Ngừng hẳn → không đụng, quên sổ tự ngừng", P(st, False, True, 10.0, T0, 95, 20, 5) == ({}, None))
st6, a6 = P(st, True, False, 96.0, T0 + 60, 95, 20, 5)
ck("đang tự ngừng mà admin bấm Nhận máy lại (còn 96%) → tôn trọng: không tự ngừng lại (hold)", a6 is None and st6 == {"hold": True}, (st6, a6))
ck("… hold: còn trên mức nhận lại → vẫn không tự ngừng", P(st6, True, False, 97.0, T0 + 120, 95, 20, 5) == ({"hold": True}, None))
st7, a7 = P(st6, True, False, 70.0, T0 + 180, 95, 20, 5)
ck("… đầy xuống ≤ 75% → hết hold (bật lại chế độ tự ngừng)", a7 is None and st7 == {}, (st7, a7))
ck("… sau đó đầy lại ≥ 95% → tự ngừng như thường", P(st7, True, False, 95.0, T0 + 240, 95, 20, 5)[1] == "pause")
ck("tắt tính năng (ngưỡng 0) lúc đang tự ngừng → nhận lại luôn", P(st, False, False, 99.0, T0, 0, 20, 5) == ({}, "resume"))
ck("tắt tính năng lúc đang nhận → không tự ngừng", P({}, True, False, 99.0, T0, 0, 20, 5) == ({}, None))
ck("không đọc được mức đầy → không tự ngừng", P({}, True, False, None, T0, 95, 20, 5) == ({}, None))
ck("khoảng giảm tuỳ chỉnh: ngưỡng 90, giảm 30 → nhận lại khi ≤ 60%", P({"auto": True, "at": T0, "low": T0}, False, False, 60.0, T0 + 300, 90, 30, 5)[1] == "resume"
   and P({"auto": True, "at": T0}, False, False, 61.0, T0 + 900, 90, 30, 5)[1] is None)
ck("heartbeat gọi autopause_tick(metrics fill_pct) → metrics.autopause cho web · bấm bằng PATCH cloud_nodes enabled (+paused_at / auto_on_at)",
   'ap = autopause_tick(metrics.get("fill_pct"))' in CPD and 'if ap: metrics["autopause"] = ap' in CPD
   and 'f1 = {"enabled": on, ("auto_on_at" if on else "paused_at"): now().isoformat()}' in CPD and '_en.update(v=on, t=time.time())' in CPD)
ck("cài đặt đọc từ settings.data (node_autopause_pct mặc định 95 · gap 20 (5–50) · min 5) · gõ nhầm < 50% → 50%", '_ap = {"t": 0.0, "cfg": (95.0, 20.0, 5.0)}' in CPD
   and 'pct = num("node_autopause_pct", 95.0, 0, 100)' in CPD and 'if 0 < pct < 50: pct = 50.0' in CPD and 'num("node_autopause_gap", 20.0, 5, 50)' in CPD)
ck("mức nhận lại không âm (ngưỡng − khoảng giảm < 0 → 0%): máy chủ vẫn tự nhận lại được khi trống hẳn",
   P({"auto": True, "at": T0, "low": T0}, False, False, 0.0, T0 + 300, 30, 40, 5)[1] == "resume" and CPD.count("back = max(0.0, pct - gap)") == 2)

# ============================================================== 28/11c · 🤖 đổi Android gặp máy chủ đầy → giữ đơn, máy chủ nào trống trước nhận
print("28/11c · đổi Android: máy chủ đầy → GIỮ ĐƠN chờ chỗ trống (không hoàn / tạo lại ngay) · máy chủ giữ máy cũ vẫn nhận lại dù đang ngừng")
import datetime as _dt
G4 = {"time": _tm, "datetime": _dt, "SW_WAIT_MIN": 20.0, "NODE_ID": "win-a", "PRIMARY": True, "_sw_said": {}, "_own_sw": {},
      "_nodes": {"rows": []}, "_FULL": {"until": 0.0}, "_busy_said": {"t": 0.0}}
for node in mod.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("now", "parse_dt", "node_sells", "sw_waiting", "sw_hope", "own_switch", "refund_unserved", "claim"):
        exec(compile(ast.Module(body=[node], type_ignores=[]), "cloudphoned.py", "exec"), G4)
S = {"others": (False, False), "aok": True, "refunds": [], "sb": [], "old_node": "win-a", "enabled": True, "room": True}
def _sb4(method, path, body=None, extra=None):
    S["sb"].append((method, path, body))
    if method == "GET" and path.startswith("cloud_phones?id=eq.OLD"): return [{"node": S["old_node"]}]
    return [{"id": "x"}] if method == "PATCH" else []
G4.update(age_s=lambda row: row.get("_age", 0), others_for=lambda row: S["others"], android_ok=lambda row: S["aok"], live_nodes=lambda: [],
          refund=lambda row, msg: S["refunds"].append(msg), notify=lambda t: None, sb=_sb4, node_enabled=lambda: S["enabled"],
          handover=lambda row: False, busy_boot=lambda: "", sick_why=lambda: "", want=lambda row: (4.0, 4.0),
          local_load=lambda: (0.5, 8.0 if S["room"] else 0.0, 8.0 if S["room"] else 0.0))
def R(**k): return dict({"id": "NEW-1", "status": "pending", "android": "15", "replaces": "OLD-1", "_age": 100}, **k)
def run(f, *a):
    with contextlib.redirect_stdout(io.StringIO()): return f(*a)
def reset(**k): S.update(others=(False, False), aok=True, refunds=[], sb=[], old_node="win-a", enabled=True, room=True); S.update(k); G4["_own_sw"].clear(); G4["_nodes"]["rows"] = []
fresh = _dt.datetime.now().astimezone().isoformat(); stale = (_dt.datetime.now().astimezone() - _dt.timedelta(minutes=10)).isoformat()
reset(others=(True, False))
ck("đơn đổi Android 100 giây, các máy chủ Android 15 đều đầy (còn chạy) → GIỮ ĐƠN", run(G4["sw_waiting"], R()) is True)
ck("đơn thường (không phải đổi Android) → không giữ (như cũ)", run(G4["sw_waiting"], R(replaces=None)) is False)
ck("đã giữ đủ 20 phút (SWITCH_WAIT_MIN) → thôi giữ, về cách cũ", run(G4["sw_waiting"], R(_age=20 * 60)) is False)
reset(aok=False)
ck("không máy chủ nào bán Android 15 còn báo cáo → không giữ (khách khỏi chờ vô ích)", run(G4["sw_waiting"], R()) is False)
G4["_nodes"]["rows"] = [{"id": "win-b", "enabled": False, "androids": "12,15", "updated_at": fresh}]
ck("máy chủ Android 15 đang NGỪNG nhận máy (tự ngừng vì đầy) nhưng còn báo cáo → vẫn giữ (nó tự nhận lại khi bớt đầy)", run(G4["sw_waiting"], R()) is True)
G4["_nodes"]["rows"] = [{"id": "win-b", "enabled": True, "androids": "15", "updated_at": stale}, {"id": "win-c", "enabled": True, "androids": "9", "updated_at": fresh}]
ck("máy chủ Android 15 mất kết nối 10 phút / máy chủ chỉ bán Android 9 → không tính", run(G4["sw_hope"], R()) is False)
reset(others=(True, False))
run(G4["refund_unserved"], R())
ck("máy chủ chính: đơn đổi Android chưa ai nhận vì đầy → KHÔNG hoàn / tạo lại lúc 90 giây", S["refunds"] == [], S["refunds"])
run(G4["refund_unserved"], R(replaces=None))
ck("… đơn thường cùng lúc → hoàn như cũ ('Máy chủ đã đầy, chưa tạo được máy')", S["refunds"] == ["Máy chủ đã đầy, chưa tạo được máy"], S["refunds"])
S["refunds"] = []; run(G4["refund_unserved"], R(_age=21 * 60))
ck("… đơn đổi Android quá 20 phút vẫn không có chỗ → hoàn / web tự tạo lại như cũ", S["refunds"] == ["Máy chủ đã đầy, chưa tạo được máy"], S["refunds"])
reset(enabled=False)
ok_c = run(G4["claim"], R())
ck("máy chủ đang Ngừng nhận máy mà máy CŨ của khách ở chính nó (vừa xoá → trống chỗ) → vẫn nhận lại đơn đổi Android",
   ok_c is True and any(m == "PATCH" and b == {"node": "win-a"} for m, _, b in S["sb"]), S["sb"])
reset(enabled=False, old_node="win-z")
ck("… máy cũ ở máy chủ khác → máy chủ đang ngừng KHÔNG nhận", run(G4["claim"], R()) is False and not any(m == "PATCH" for m, _, _ in S["sb"]), S["sb"])
reset(enabled=False)
ck("… đơn thường → máy chủ đang ngừng KHÔNG nhận (như cũ)", run(G4["claim"], R(replaces=None)) is False and not any(m == "PATCH" for m, _, _ in S["sb"]))
reset(enabled=False, room=False, others=(True, False))
ck("… máy cũ ở đây nhưng không đủ chỗ cho bản mới → không nhận, đơn vẫn được giữ (không hoàn)", run(G4["claim"], R()) is False and S["refunds"] == [], (S["sb"], S["refunds"]))
reset(enabled=False)
run(G4["own_switch"], R()); run(G4["own_switch"], R())
ck("own_switch đọc máy cũ 1 lần / 2 phút / đơn (không hỏi web mỗi 3 giây)", sum(1 for m, p_, _ in S["sb"] if m == "GET") == 1, S["sb"])
ck("tạo máy báo HẾT CHỖ (mã 2) với đơn đổi Android → TRẢ ĐƠN (node trống) cho máy chủ khác thay vì hoàn",
   "sw = sw_waiting(row)" in CPD and "if (age_s(row) < 600 and others_for(row)[1]) or sw:" in CPD and '" (đổi Android: giữ đơn chờ có chỗ)" if sw else ""' in CPD)
ck("máy chủ chính gọi sw_waiting trước khi hoàn đơn chưa ai nhận · máy chủ đang ngừng chỉ nhận own_switch",
   "if sw_waiting(row, live): return" in CPD and "if not node_enabled() and not own_switch(row): return False" in CPD)
ck("thời gian giữ (SWITCH_WAIT_MIN 20) < hạn tự huỷ đơn treo (STUCK_MIN 30)", 'SW_WAIT_MIN = max(0.0, _f("SWITCH_WAIT_MIN", 20))' in CPD and 'STUCK_MIN = max(0.0, _f("STUCK_MIN", 30))' in CPD)

print("%d/%d dat" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
