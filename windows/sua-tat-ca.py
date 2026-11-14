# -*- coding: utf-8 -*-
# sua-tat-ca.py — 14/11 · SỬA MỘT LẦN CHO CẢ MÁY CHỦ WINDOWS. Mỗi máy chủ dán 1 lệnh ngắn: lệnh tải file này từ GitHub rồi chạy.
#   1. Cập nhật bản sửa từ GitHub (kiểm kỹ trước khi thay, giữ bản cũ *.truoc-1411):
#        cloudphoned  — tự sửa an toàn hơn (không tắt phát hình chỉ vì máy chủ chậm trả lời, bớt tin Telegram rác),
#                       máy mới / đổi Android chưa lên thì CHƯA giao cho khách (hết cảnh mở ra màn đen)
#        bluestream   — 13/11c: khách mở máy → bật sáng màn hình Android trước khi lấy hình
#        panel        — mở bảng CloudBlue kiểu nào cũng tự bật A→Z (dịch vụ + máy khách) nếu chưa chạy gì
#        cloudphoned  — TRẦN CỨNG mỗi máy chủ: cấp tới 68 nhân / 112GB là ngừng nhận (không bán vượt); hết hạn / huỷ / đổi Android
#                       xoá hẳn máy + dữ liệu, máy sót tự dọn 30 phút / lần
#        phonectl     — GIÃN CÁCH BẬT MÁY: tối đa 2 máy cùng khởi động (khách đang chờ được 3), cách nhau 20 giây
#   2. Bật lại đúng dịch vụ vừa thay / đang chạy bản cũ (bảng CloudBlue tự bật lại sau 5 giây) — không đụng máy khách
#   3. Tự chạy khi Windows khởi động lại: tác vụ / lối tắt phải có --auto · bảng mở mà chưa chạy gì → mở lại bảng kiểu tự bật
#   4. Kiểm cổng phát hình, đường hầm Cloudflare
#   5. Kiểm từng máy khách: nối adb, Android đã lên chưa, bật sáng màn hình, màn đen
#   6. Máy chưa lên / mất adb / đen ở màn hình chính → ép khởi động lại. Máy đen mà đang mở app/game → KHÔNG đụng, chỉ báo
#      (game treo máy hay tắt hình cho nhẹ). Máy khách tắt ngoài ý muốn → bật lại.
#   Chạy:  python sua-tat-ca.py            · chỉ kiểm, không thay / không bật lại gì:  python sua-tat-ca.py --chi-kiem
import ast, concurrent.futures as cf, datetime, json, os, re, struct, subprocess, sys, threading, time, urllib.parse, urllib.request

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception: pass

VER = "14/11"
B = os.environ.get("CB_HOME") or os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(B, "platform-tools", "adb.exe")
PHONECTL = os.path.join(B, "phonectl.py")
LOGS = os.path.join(B, "logs")
REPO = "lvhien205hn-eng/cloudblue"
NW = 0x08000000 if os.name == "nt" else 0
ONLY_CHECK = "--chi-kiem" in sys.argv
REMAKE = "--lam-moi-may-ma" in sys.argv          # tạo lại máy MỚI cho khách có máy "ma" (web còn thuê, máy chủ mất hẳn máy)
REMAKE_BROKEN = "--lam-moi-may-hong" in sys.argv  # máy ép khởi động lại rồi vẫn KHÔNG lên → xoá máy hỏng + tạo lại máy mới (mất dữ liệu)
NO_UPDATE = ONLY_CHECK or "--khong-cap-nhat" in sys.argv
ENV = dict(os.environ, PATH=os.path.join(B, "platform-tools") + os.pathsep + os.environ.get("PATH", ""), PYTHONIOENCODING="utf-8",
           PYTHONUTF8="1", ADB_LOCAL_TRANSPORT_MAX_PORT="5553")
# (đường dẫn trên GitHub, tên file trên máy chủ, dấu chắc chắn của bản mới, dịch vụ)
FILES = [("cloudphoned.py", "cloudphoned.py", "def _bg_dondep", "cloudphoned"),
         ("windows/bluestream.py", "bluestream.py", 'BS_SUB = "13/11d"', "bluestream"),
         ("windows/panel.py", "panel.py", "bang-tu-sua.log", "panel"),
         ("windows/phonectl.py", "phonectl.py", "def cmd_nhanlai", None)]
MARK_RUN = {"cloudphoned": "cloudphoned bản 14/11", "bluestream": "(WAKE_ON_OPEN)"}       # dòng khởi động của bản mới (trong nhật ký)
SVC_RX = {"cloudphoned": r"cloudphoned\.py\W*$", "bluestream": r"bluestream\.py\W*$"}
SVC_LOG = {"cloudphoned": "cloudphoned.log", "bluestream": "phat-hinh.log"}
SVC_VN = {"cloudphoned": "nhận đơn (cloudphoned)", "bluestream": "phát hình (bluestream)"}
HOME_PK = ("launcher", "lawnchair", "systemui", "keyguard", "trebuchet", "quickstep", "nexuslauncher", "com.android.settings")

def say(*a): print(*a, flush=True)

def run(cmd, t=30, raw=False):
    """Chạy 1 lệnh → chữ (hoặc byte). Không bao giờ ném lỗi; quá giờ → '' (chương trình bị tắt)."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=t, creationflags=NW, env=ENV, stdin=subprocess.DEVNULL)
        return r.stdout if raw else (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return b"" if raw else ""

def run2(cmd, t=30):
    """(mã thoát, stdout + stderr) — mã -1 = quá giờ / không chạy được."""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=t, creationflags=NW, env=ENV, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)

def ps(script, t=90):
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], t)

def adb(*a, t=15, raw=False): return run([ADB] + [str(x) for x in a], t, raw)

def pctl(*a, t=600): return run2([sys.executable, PHONECTL] + [str(x) for x in a], t)

def tail(path, nb=2000000):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2); z = fh.tell(); fh.seek(max(0, z - nb)); return fh.read().decode("utf-8", "replace").splitlines()
    except Exception:
        return []

def conf():
    c = {}
    for ln in tail(os.path.join(B, "cloudphone.conf"), 300000):
        ln = ln.lstrip("﻿")
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1); c[k.strip()] = v.strip()
    return c

def listening(ports):
    out = run(["netstat", "-ano"], 40)
    if not out.strip(): return None
    return {p for p in ports if re.search(r":%d\s+(?:0\.0\.0\.0|\[::\]|127\.0\.0\.1):0\s" % int(p), out)}

def procs(rx):
    """[(pid, số giây đã chạy)] các chương trình python* có dòng lệnh khớp rx."""
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match '%s' } | "
             "ForEach-Object { '{0} {1}' -f $_.ProcessId, [int]((Get-Date) - $_.CreationDate).TotalSeconds }" % rx.replace("'", "''"), 60)
    res = []
    for ln in out.splitlines():
        q = ln.split()
        if len(q) == 2 and q[0].isdigit() and q[1].lstrip("-").isdigit() and int(q[0]) != os.getpid(): res.append((int(q[0]), int(q[1])))
    return res

def py_cmdlines():
    return ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | ForEach-Object { $_.CommandLine }", 60)

def kill(pid): return run(["taskkill", "/PID", str(pid), "/F"], 30)       # CHỈ tắt đúng chương trình đó (không /T: giữ giả lập / adb)

# ------------------------------------------------------------------ 1. cập nhật file
def gh_get(path):
    """Tải 1 file từ GitHub (nhánh main): API (không bị bộ đệm) → raw → curl.exe. None = không tải được."""
    tries = [("https://api.github.com/repos/%s/contents/%s?ref=main" % (REPO, path), {"Accept": "application/vnd.github.raw"}),
             ("https://raw.githubusercontent.com/%s/main/%s?t=%d" % (REPO, path, int(time.time())), {})]
    for url, h in tries:
        try:
            req = urllib.request.Request(url, headers=dict({"User-Agent": "cloudblue-sua-tat-ca", "Cache-Control": "no-cache"}, **h))
            with urllib.request.urlopen(req, timeout=60) as r: data = r.read()
            if len(data) > 2000: return data
        except Exception:
            pass
    for url, h in tries:                                   # Python không tải được (chứng chỉ cũ…) → curl.exe của Windows
        tmp = os.path.join(B, "redroid", "sua-tai.tmp")
        try:
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            run(["curl.exe", "-sSL", "-H", "User-Agent: cloudblue-sua-tat-ca"] + (["-H", "Accept: " + h["Accept"]] if h else []) + ["-o", tmp, url], 120)
            data = open(tmp, "rb").read(); os.remove(tmp)
            if len(data) > 2000: return data
        except Exception:
            pass
    return None

def good_py(data, name):
    try: ast.parse(data.decode("utf-8"), name); return True
    except Exception: return False

CREATE_RX = r"phonectl\.py\S*\s+(create|resize)\s"
HUNG_S = 1800                                      # lệnh tạo / nâng máy chạy quá 30 phút = treo (bình thường 2–6 phút)
def wait_not_creating(limit=600):
    """Đang tạo / nâng cấp máy khách → chờ xong rồi mới bật lại nhận đơn (tối đa 10 phút). Lệnh tạo đã chạy quá 30 phút = TREO
       → tắt riêng lệnh đó (đơn đó được hoàn tiền / tạo lại) rồi đi tiếp. True = không còn lệnh tạo nào."""
    t0 = time.time(); said = 0
    while True:
        pr = procs(CREATE_RX)
        if not pr: return True
        hung = [pid for pid, age in pr if age > HUNG_S]
        if hung:
            for pid in hung: kill(pid)
            say(f"   ⚠ lệnh tạo / nâng máy chạy quá {HUNG_S // 60} phút (treo) → đã tắt riêng lệnh đó (pid {', '.join(map(str, hung))})")
            continue
        if time.time() - t0 >= limit: return False
        if time.time() - said > 60: say("   … đang tạo / nâng cấp máy khách — chờ xong rồi mới bật lại nhận đơn (tối đa 10 phút)"); said = time.time()
        time.sleep(10)

def update_files():
    changed = []; problems = []
    say("1/6 Cập nhật bản sửa từ GitHub")
    if NO_UPDATE: say("   (bỏ qua — chỉ kiểm)"); return changed, problems
    todo = []
    for gp, local, mark, svc in FILES:
        lp = os.path.join(B, local)
        if not os.path.isfile(lp) and svc != "panel":
            say(f"   - {local}: máy chủ này không có — bỏ qua"); continue
        data = gh_get(gp)
        if data is None: say(f"   ✗ {local}: không tải được từ GitHub (mạng?) — giữ bản đang có"); problems.append(f"không tải được {local}"); continue
        if mark.encode("utf-8") not in data:
            say(f"   ✗ {local}: GitHub CHƯA có bản mới ({mark}) — tải đủ file lên GitHub rồi chạy lại lệnh"); problems.append(f"GitHub chưa có {local} mới"); continue
        if not good_py(data, local): say(f"   ✗ {local}: file tải về bị lỗi — giữ bản đang có"); problems.append(f"{local} tải về lỗi"); continue
        try: cur = open(lp, "rb").read()
        except OSError: cur = b""
        if cur == data: say(f"   = {local}: đã là bản mới"); continue
        todo.append((local, lp, data, svc))
    for local, lp, data, svc in todo:
        try:
            bak = lp + ".truoc-1411"
            if os.path.isfile(lp) and not os.path.isfile(bak):
                with open(lp, "rb") as a, open(bak, "wb") as b: b.write(a.read())
            with open(lp + ".new", "wb") as f: f.write(data)
            os.replace(lp + ".new", lp)
            say(f"   ✓ {local}: đã thay bản mới" + (" (bản cũ: " + os.path.basename(bak) + ")" if os.path.isfile(bak) else ""))
            changed.append(svc or local)
        except Exception as e:
            say(f"   ✗ {local}: không ghi được ({e}) — đóng chương trình đang mở file này rồi chạy lại"); problems.append(f"không ghi được {local}")
    return changed, problems

# ------------------------------------------------------------------ 2. bật lại dịch vụ
def log_size(svc):
    try: return os.path.getsize(os.path.join(LOGS, SVC_LOG[svc]))
    except OSError: return 0

def log_new(svc, since):
    try:
        with open(os.path.join(LOGS, SVC_LOG[svc]), "rb") as fh:
            fh.seek(0, 2); z = fh.tell(); fh.seek(since if since <= z else 0); return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""

def restart_services(changed, done_new=()):
    say("2/6 Bật lại dịch vụ (bản mới chạy ngay)")
    probs = []
    if ONLY_CHECK: say("   (bỏ qua — chỉ kiểm)"); return probs
    waited = False
    for svc in ("cloudphoned", "bluestream"):
        fp = os.path.join(B, "cloudphoned.py" if svc == "cloudphoned" else "bluestream.py")
        if not os.path.isfile(fp): continue
        pr = procs(SVC_RX[svc])
        if not pr:
            say(f"   ⚠ {SVC_VN[svc]} đang KHÔNG chạy — bước 3 mở lại bảng CloudBlue"); continue
        try: age_file = time.time() - os.path.getmtime(fp)
        except OSError: age_file = 0
        old = svc in changed or any(age > age_file + 5 for _, age in pr)          # chạy từ TRƯỚC khi file được thay → đang chạy bản cũ
        if not old: say(f"   = {SVC_VN[svc]}: đang chạy đúng file hiện có" + (" (bản mới)" if svc in done_new else "")); continue
        if svc == "cloudphoned" and not waited:
            waited = True
            if not wait_not_creating():
                say("   ✗ nhận đơn: máy chủ đang tạo máy khách quá 10 phút — CHƯA bật lại (file mới đã thay), chạy lại lệnh sau ít phút")
                probs.append("nhận đơn chưa chạy bản mới (đang tạo máy) — chạy lại lệnh sau"); continue
        if svc == "bluestream": say("   … phát hình bật lại: khách đang xem bị ngắt ~10 giây rồi app tự nối lại")
        since = log_size(svc); t0 = time.time()
        for pid, _ in pr: kill(pid)
        say(f"   … {SVC_VN[svc]}: đã tắt bản cũ (pid {', '.join(str(p) for p, _ in pr)}) — chờ bảng CloudBlue bật lại bản mới")
        ok = False
        while time.time() - t0 < 90:
            time.sleep(3)
            if MARK_RUN[svc] in log_new(svc, since): ok = True; break
        newp = [p for p, _ in procs(SVC_RX[svc])]
        if ok: say(f"   ✓ {SVC_VN[svc]}: bản mới đã chạy sau {time.time() - t0:.0f} giây")
        elif newp: say(f"   ✓ {SVC_VN[svc]}: đã chạy lại (pid {newp[0]}) — chưa thấy dòng khởi động trong nhật ký, xem lại sau 1 phút")
        else:
            say(f"   ✗ {SVC_VN[svc]}: CHƯA chạy lại sau 90 giây → mở bảng CloudBlue bấm ▶ Bật tất cả"); probs.append(f"{SVC_VN[svc]} chưa chạy lại")
    return probs

# ------------------------------------------------------------------ 3. tự chạy khi Windows khởi động lại
AUTOSTART_PS = r"""
$t = Get-ScheduledTask -TaskName 'BlueRoblox' -ErrorAction SilentlyContinue
if ($t) { 'TASK=1'; 'TASK_ARG=' + $t.Actions[0].Arguments } else { 'TASK=0' }
$lnk = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk"
if (Test-Path $lnk) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk); 'LNK=1'; 'LNK_ARG=' + $s.Arguments } else { 'LNK=0' }
$u = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\CloudBlue.lnk"
if (Test-Path $u) { 'ULNK=1' } else { 'ULNK=0' }
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue
'AUTOLOGON=' + $w.AutoAdminLogon
$a = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
'ADMIN=' + $a
"""
def kv(out):
    d = {}
    for ln in out.splitlines():
        if "=" in ln: k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    return d

def pythonw():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.isfile(w) else sys.executable

def fix_autostart():
    say("3/6 Tự chạy khi Windows khởi động lại")
    probs = []
    d = kv(ps(AUTOSTART_PS, 60))
    if not d: say("   ? không đọc được (PowerShell lỗi)"); return probs
    pw = pythonw(); pan = os.path.join(B, "panel.py")
    if d.get("TASK") == "1":
        if "--auto" in d.get("TASK_ARG", ""): say("   ✓ tác vụ BlueRoblox (tự mở bảng lúc đăng nhập): có --auto")
        elif ONLY_CHECK: say("   ✗ tác vụ BlueRoblox THIẾU --auto (bảng mở mà không tự bật gì)"); probs.append("tác vụ thiếu --auto")
        else:
            out = ps("$t = Get-ScheduledTask -TaskName 'BlueRoblox'; $a = $t.Actions[0]; $a.Arguments = ($a.Arguments + ' --auto').Trim(); "
                     "Set-ScheduledTask -TaskName 'BlueRoblox' -Action $a | Out-Null; (Get-ScheduledTask -TaskName 'BlueRoblox').Actions[0].Arguments", 60)
            if "--auto" in out: say("   ✓ tác vụ BlueRoblox thiếu --auto → đã thêm (lần sau Windows lên là tự bật A→Z)")
            else: say("   ✗ tác vụ BlueRoblox thiếu --auto mà không sửa được (mở PowerShell bằng quyền Admin rồi chạy lại)"); probs.append("tác vụ thiếu --auto")
    if d.get("LNK") == "1":
        if "--auto" in d.get("LNK_ARG", ""): say("   ✓ lối tắt Startup BlueRoblox: có --auto")
        elif not ONLY_CHECK:
            out = ps("$l = \"$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\StartUp\\BlueRoblox.lnk\"; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); "
                     "$s.TargetPath = '%s'; $s.Arguments = '\"%s\" --auto'; $s.WorkingDirectory = '%s'; $s.Save(); "
                     "(New-Object -ComObject WScript.Shell).CreateShortcut($l).Arguments" % (pw, pan, B), 60)
            if "--auto" in out: say("   ✓ lối tắt Startup BlueRoblox thiếu --auto → đã sửa")
            else: say("   ✗ lối tắt Startup thiếu --auto mà không sửa được (cần quyền Admin)"); probs.append("lối tắt thiếu --auto")
    if d.get("TASK") != "1" and d.get("LNK") != "1" and d.get("ULNK") != "1":
        if ONLY_CHECK: say("   ✗ CHƯA có gì tự mở bảng CloudBlue khi Windows lên"); probs.append("chưa tự chạy")
        else:
            out = ps("$l = \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\CloudBlue.lnk\"; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); "
                     "$s.TargetPath = '%s'; $s.Arguments = '\"%s\" --auto'; $s.WorkingDirectory = '%s'; $s.Save(); Test-Path $l" % (pw, pan, B), 60)
            if "True" in out: say("   ✓ chưa có gì tự mở bảng khi Windows lên → đã thêm lối tắt Startup (kèm --auto)")
            else: say("   ✗ chưa có gì tự mở bảng khi Windows lên — bảng CloudBlue → bấm 🔑 Tự đăng nhập + tự chạy"); probs.append("chưa tự chạy")
    if d.get("AUTOLOGON") == "1": say("   ✓ Windows tự đăng nhập: bật")
    else:
        say("   ⚠ Windows CHƯA tự đăng nhập → khởi động lại sẽ đứng ở màn hình mật khẩu, máy khách không chạy tới khi có người đăng nhập.\n"
            "     Sửa: bảng CloudBlue → bấm 🔑 Tự đăng nhập + tự chạy (tự gõ mật khẩu Windows vào bảng)")
        probs.append("Windows chưa tự đăng nhập (bấm 🔑 trong bảng)")
    return probs

def panel_procs():
    out = ps("Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -match 'panel\\.py') -or $_.Name -eq 'BlueRobloxServer.exe' } | "
             "ForEach-Object { '{0} {1}' -f $_.ProcessId, $_.Name }", 60)
    return [(int(q[0]), q[1]) for q in (ln.split() for ln in out.splitlines()) if len(q) == 2 and q[0].isdigit()]

def ensure_running(c):
    """Không dịch vụ nào chạy (bảng mở mà chưa bật gì / bảng chưa mở) → mở lại bảng CloudBlue kiểu TỰ BẬT A→Z."""
    sp = int(c.get("STREAM_PORT") or 8189)
    up = listening([8000, 8010, sp]) or set()
    if up or procs(SVC_RX["cloudphoned"]) or procs(SVC_RX["bluestream"]): return None
    pans = panel_procs()
    if ONLY_CHECK:
        say("   ✗ KHÔNG dịch vụ nào chạy (máy khách không bật, không nhận đơn) — mở bảng CloudBlue bấm ▶ Bật tất cả"); return "không dịch vụ nào chạy"
    if any(n.lower() == "bluerobloxserver.exe" for _, n in pans):
        say("   ✗ KHÔNG dịch vụ nào chạy — bảng BlueRobloxServer đang mở: bấm ▶ Bật tất cả trong bảng"); return "không dịch vụ nào chạy"
    for pid, _ in pans: kill(pid)
    if pans:
        time.sleep(2)
        if panel_procs():
            say("   ✗ KHÔNG dịch vụ nào chạy, mà không tắt được bảng CloudBlue đang mở (bảng chạy quyền Admin) → bấm ▶ Bật tất cả trong bảng")
            return "không dịch vụ nào chạy"
    try:
        subprocess.Popen([pythonw(), os.path.join(B, "panel.py"), "--auto"], cwd=B, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, creationflags=(0x00000008 | 0x00000200) if os.name == "nt" else 0)
    except Exception as e:
        say(f"   ✗ không mở được bảng CloudBlue ({e}) — mở tay rồi bấm ▶ Bật tất cả"); return "không mở được bảng"
    say(("   ⚠ bảng CloudBlue mở mà KHÔNG chạy dịch vụ nào → đã mở lại bảng kiểu tự bật A→Z" if pans else
         "   ⚠ bảng CloudBlue chưa mở, không dịch vụ nào chạy → đã mở bảng kiểu tự bật A→Z") + " — chờ dịch vụ lên (tối đa 3 phút)…")
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(5)
        if procs(SVC_RX["cloudphoned"]) and (listening([sp]) or set()):
            say(f"   ✓ dịch vụ đã chạy sau {time.time() - t0:.0f} giây (bảng tự bật tiếp máy khách)"); return "LAUNCHED"
    say("   ✗ 3 phút dịch vụ vẫn chưa chạy — xem bảng CloudBlue (tab Tổng quan)"); return "dịch vụ chưa chạy"

# ------------------------------------------------------------------ 4. mạng / dịch vụ
def check_net(c):
    say("4/6 Dịch vụ + đường mạng")
    probs = []
    sp, wp = int(c.get("STREAM_PORT") or 8189), int(c.get("STREAM_WS_PORT") or 8020)
    up = listening([sp, wp, 8000, 8010])
    for lab, p in (("phát hình app (đi thẳng)", sp), ("phát hình qua Cloudflare", wp), ("trình phát hình web", 8000), ("cổng bảo vệ (cpapi)", 8010)):
        if up is None: say(f"   ? cổng {p} {lab}: không đọc được netstat"); continue
        say(f"   {'✓' if p in up else '✗'} cổng {p} {lab}: {'đang mở' if p in up else 'ĐÓNG'}")
        if p not in up and p in (sp, wp): probs.append(f"cổng {p} đóng")
    q = run(["sc", "query", "cloudflared"], 20)
    if "SERVICE_NAME" in q:
        okc = re.search(r":\s*4\s+RUNNING", q) is not None
        say(f"   {'✓' if okc else '✗'} đường hầm Cloudflare: {'đang chạy' if okc else 'KHÔNG CHẠY'}")
        if not okc:
            if not ONLY_CHECK: run(["sc", "start", "cloudflared"], 30); say("     → đã bật lại đường hầm")
            probs.append("Cloudflare tắt")
    ph = phones() or []
    a_c = sum(float(p.get("cpu") or 0) for p in ph); a_r = sum(float(p.get("ram") or 0) for p in ph)
    cap_c = float(c.get("CAP_CPU") or 68); cap_r = float(c.get("CAP_RAM") or 112)
    over = (cap_c > 0 and a_c >= cap_c) or (cap_r > 0 and a_r >= cap_r)
    say(f"   {'⚠' if over else '✓'} đã cấp {a_c:g} nhân · {a_r:g}GB cho {len(ph)} máy (trần {cap_c:g} nhân · {cap_r:g}GB)"
        + (" → ĐÃ ĐẦY: ngừng nhận máy mới tới khi xuống dưới trần (máy đang có vẫn chạy bình thường)" if over else ""))
    for svc in ("cloudphoned", "bluestream"):
        n = len(procs(SVC_RX[svc]))
        say(f"   {'✓' if n == 1 else '✗' if n == 0 else '⚠'} {SVC_VN[svc]}: " + ("đang chạy" if n == 1 else "KHÔNG chạy" if n == 0 else f"{n} bản cùng chạy (nên chỉ 1)"))
        if n != 1: probs.append(f"{SVC_VN[svc]}: {n} bản")
    return probs

# ------------------------------------------------------------------ 5. máy khách
def black(s):
    """Ảnh màn hình Android tối hết (< 0,3% điểm sáng)? None = không chụp được."""
    d = adb("-s", s, "exec-out", "screencap", t=25, raw=True)
    if len(d) < 16: return None
    w, h = struct.unpack("<II", d[:8]); n = w * h; hd = len(d) - n * 4
    if n <= 0 or hd not in (12, 16): return None
    st = max(1, n // 6000); tot = lit = 0
    for i in range(0, n, st):
        o = hd + 4 * i; tot += 1
        if d[o] > 24 or d[o + 1] > 24 or d[o + 2] > 24: lit += 1
    return lit * 1000 < tot * 3

def booted(s): return adb("-s", s, "shell", "getprop sys.boot_completed", t=12).strip() == "1"

def adb_ok(s):
    adb("connect", s, t=10)
    if adb("-s", s, "get-state", t=8).strip() == "device": return True, ""
    adb("disconnect", s, t=8); adb("connect", s, t=10)              # adb TCP hay kẹt "offline" → ngắt + nối lại
    if adb("-s", s, "get-state", t=8).strip() == "device": return True, "adb kẹt → đã nối lại"
    return False, ""

def focus(s):
    o = adb("-s", s, "shell", "dumpsys window | grep -m1 mCurrentFocus", t=15)
    m = re.search(r"\s([\w.]+)/", o)
    return m.group(1) if m else ("-" if "null" in o or not o.strip() else "?")

def is_home(pk): return pk in ("-", "?") or any(k in pk.lower() for k in HOME_PK)

def check_phone(p):
    nm = str(p["name"]); s = "127.0.0.1:%s" % p["port"]; r = {"name": nm, "s": s, "port": p["port"], "st": "OK", "note": "", "act": None}
    ok, note = adb_ok(s)
    if note: r["note"] += " (" + note + ")"
    if not ok: r.update(st="MẤT ADB", act="restart"); return r
    if not booted(s): r.update(st="CHƯA LÊN", act="restart"); return r
    w = adb("-s", s, "shell", "dumpsys power | grep -m1 mWakefulness=", t=10)
    if "mWakefulness=" in w and "Awake" not in w:
        adb("-s", s, "shell", "input keyevent 224", t=10); r["note"] += " (màn hình đang TẮT → đã bật sáng)"; time.sleep(1)
    adb("-s", s, "shell", "wm dismiss-keyguard; settings put system screen_off_timeout 2147483647; svc power stayon true", t=12)
    pk = focus(s); r["app"] = pk
    b = black(s)
    for _ in range(2):
        if not b: break
        time.sleep(4); b = black(s)
    if b is None: r.update(st="?"); r["note"] += " (không chụp được màn hình)"; return r
    if not b: return r
    if re.search(r"fl=[^\n]*\bSECURE\b", adb("-s", s, "shell", "dumpsys window windows", t=25)):
        r["note"] += " (app chặn chụp màn hình — không tính)"; return r
    if is_home(pk): r.update(st="ĐEN", act="restart"); return r
    r.update(st="ĐEN TRONG APP"); r["note"] += " — đang mở app/game (có thể game tắt hình để treo máy) → KHÔNG tự khởi động lại"
    return r

def sb_rows(c, q):
    url, key = c.get("SUPABASE_URL", "").rstrip("/"), c.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key: return None
    try:
        req = urllib.request.Request(url + "/rest/v1/" + q, headers={"apikey": key, "Authorization": "Bearer " + key, "User-Agent": "cloudblue-sua-tat-ca"})
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode() or "[]")
    except Exception:
        return None

GHOST = []

def remake_ghosts():
    """--lam-moi-may-ma: tạo lại máy MỚI (đúng cấu hình, bản Android, hạn) cho khách có máy "ma" còn hạn — remake.py, từng máy một."""
    if not GHOST: return []
    say(f"--- tạo lại {len(GHOST)} máy \"ma\" còn hạn (mỗi máy 2–5 phút, làm lần lượt) ---")
    code, out = run2([sys.executable, os.path.join(B, "run.py"), "remake.py", "all"], 4 * 3600)
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.startswith(("✓ ĐÃ LÀM MỚI", "✗", "=====")) or "ĐÃ LÀM MỚI" in ln: say("   " + ln[:170])
    m = re.search(r"ĐÃ LÀM MỚI (\d+)/(\d+)", out)
    return [m.group(1), m.group(2)] if m else []

def phones():
    try: return json.load(open(os.path.join(B, "redroid", "phones.json"), encoding="utf-8-sig")).get("phones", [])
    except Exception: return None

def check_phones(c):
    say("5/6 Kiểm từng máy khách (nối adb · Android đã lên · bật sáng màn hình · màn đen)")
    if not os.path.isfile(PHONECTL): say("   - máy chủ này không có phonectl.py — bỏ qua"); return [], {}, []
    if not ONLY_CHECK:
        code, out = pctl("nhanlai", t=300)                  # máy còn trong giả lập mà mất khỏi danh sách, web còn thuê → nhận lại (giữ dữ liệu)
        for ln in out.splitlines():
            if ln.startswith("NHAN_LAI "): say("   ✓ " + ln[9:])
    code, vl = pctl("vmlist", t=120)
    odd = [q[1].strip() for q in (ln.split(",") for ln in vl.splitlines()) if len(q) > 2 and q[0].strip().isdigit() and q[0].strip() != "0"
           and not q[1].strip().startswith(("cp_", "spare_", "tpl_"))]
    if odd: say(f"   ⚠ máy lạ trong giả lập (không phải máy khách — thường là lần tạo máy hỏng): {', '.join(odd[:8])} — không dùng thì xoá tay trong giả lập")
    state = {}
    if ONLY_CHECK:                                          # chỉ kiểm: đọc giả lập, không ghi gì
        ph = phones()
        run_by = {q[1].strip(): q[2].strip() == "1" for q in (ln.split(",") for ln in vl.splitlines()) if len(q) > 2 and q[0].strip().isdigit()}
        for p in ph or []:
            nm = str(p.get("name"))
            if nm in run_by: state[nm] = "chạy" if run_by[nm] else ("ngủ" if p.get("hold") and p.get("sleep") else "tắt")
    else:
        code, lst = pctl("list", t=300)                     # đọc lại số máy / cổng thật trong giả lập (phonectl tự sửa cổng lệch)
        ph = phones()
        names = {str(p.get("name")) for p in ph or []}
        for ln in lst.splitlines():
            q = ln.split()
            if len(q) > 2 and q[0] in names and q[-1] in ("chạy", "ngủ", "tắt"): state[q[0]] = q[-1]
    if ph is None: say("   ✗ không đọc được redroid\\phones.json"); return [], {}, ["không đọc được phones.json"]
    if not ph: say("   (máy chủ chưa có máy khách nào)"); return [], {}, []
    ports = {}
    for p in ph: ports.setdefault(str(p.get("port")), []).append(str(p.get("name")))
    dup = {k: v for k, v in ports.items() if len(v) > 1 and k not in ("None", "", "0")}
    probs = []
    for k, v in dup.items(): say(f"   ✗ {len(v)} máy cùng cổng {k}: {', '.join(v)} — gửi Claude dòng này"); probs.append(f"trùng cổng {k}")
    node = c.get("NODE_ID", "")
    rows = sb_rows(c, "cloud_phones?node=eq.%s&status=in.(active,expired)&select=container,port,status,ram,cpu,android,expires_at" % urllib.parse.quote(node)) if node else None
    if rows is not None:
        byn = {str(p.get("name")): p for p in ph}
        ghost = [r["container"] for r in rows if r.get("container") and r["container"] not in byn]
        gact = [r for r in rows if r.get("container") in ghost and r.get("status") == "active"]
        GHOST[:] = gact
        lech = [r["container"] for r in rows if r.get("container") in byn and str(r.get("port")) != str(byn[r["container"]].get("port"))]
        if ghost:
            say(f"   ✗ {len(ghost)} máy \"ma\": web ghi khách đang thuê ở máy chủ này mà máy chủ KHÔNG còn máy (khách mở cứ quay 'Đang mở máy…'): "
                f"{', '.join(ghost[:8])}{' …' if len(ghost) > 8 else ''}")
            if gact:
                say(f"     trong đó {len(gact)} máy còn hạn — tổng {sum(float(r.get('cpu') or 0) for r in gact):g} nhân · {sum(float(r.get('ram') or 0) for r in gact):g}GB"
                    + ("" if REMAKE else " → muốn tạo lại máy MỚI cho khách (giữ cấu hình + hạn, dữ liệu cũ đã mất): chạy lại lệnh này kèm --lam-moi-may-ma"))
            if len(ghost) > len(gact): say(f"     {len(ghost) - len(gact)} máy đã hết hạn → nhận đơn tự ghi huỷ sau 30 phút")
            probs.append(f"{len(ghost)} máy ma (web còn, máy chủ không có)")
        if lech:
            say(f"   ⚠ {len(lech)} máy web ghi cổng khác máy chủ (app vẫn vào đúng, web xem có thể đen): {', '.join(lech[:8])}")
    now = datetime.datetime.now().astimezone()
    def exp_ok(p):
        try: return datetime.datetime.fromisoformat(str(p.get("expires")).replace("Z", "+00:00")) > now
        except Exception: return True
    run_l, sleep_n, held_n, off_l = [], 0, 0, []
    for p in ph:
        nm = str(p.get("name")); stv = state.get(nm, "")
        if p.get("hold"):
            if p.get("sleep"): sleep_n += 1
            else: held_n += 1
            continue
        if not str(p.get("port") or "").isdigit(): say(f"   - {nm}: chưa có cổng (đang tạo?) — bỏ qua"); continue
        if stv == "tắt" and exp_ok(p): off_l.append(p); continue
        if stv == "chạy" or not stv: run_l.append(p)
    res = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(check_phone, run_l): res.append(r)
    for r in sorted(res, key=lambda x: x["name"]):
        icon = "✓" if r["st"] == "OK" else "?" if r["st"] == "?" else "✗"
        say(f"   {icon} {r['name']:<16} cổng {r['port']:<6} {r['st']:<13} {r.get('app', '') if r['st'] != 'OK' else ''}{r['note']}")
    for p in off_l: say(f"   ✗ {p['name']:<16} cổng {p['port']:<6} ĐANG TẮT (còn hạn, không phải ngủ) → bật lại")
    say(f"   Máy đang ngủ (khách mở là tự bật): {sleep_n} · tạm dừng / khoá: {held_n}")
    return res, {"off": off_l, "sleep": sleep_n, "held": held_n, "ph": ph}, probs

# ------------------------------------------------------------------ 6. sửa
def busy(nm, cl):
    return re.search(r"phonectl\.py\S*\s+(wake|restart|create|resize|delete|start|waitboot|reconfig|ramfix)\s+" + re.escape(nm) + r"\b", cl) is not None

def fix_phones(res, extra):
    say("6/6 Sửa máy hỏng")
    bad = [r for r in res if r["act"]]
    if not bad and not extra.get("off"): say("   ✓ không có máy nào cần khởi động lại"); return [], []
    if ONLY_CHECK: say(f"   (chỉ kiểm — {len(bad) + len(extra.get('off', []))} máy cần sửa, chạy lại không kèm --chi-kiem để sửa)"); return [], []
    cl = py_cmdlines(); whole = re.search(r"phonectl\.py\S*\s+(bootall|heal)\b", cl)
    jobs = []; slow = []
    for r in bad:
        if busy(r["name"], cl): say(f"   - {r['name']}: đang được bật / sửa — để nó làm xong"); continue
        if r["st"] in ("CHƯA LÊN", "MẤT ADB"):
            if whole: say(f"   - {r['name']}: bảng đang bật lại máy khách hàng loạt — để bảng làm xong"); continue
            slow.append(r); continue
        jobs.append(("restart", r["name"], r["s"], r["st"]))
    if slow:                                                  # có thể đang khởi động dở → chờ chung thêm 45 giây
        say(f"   … {len(slow)} máy chưa lên — chờ thêm 45 giây xem có tự lên không")
        t0 = time.time()
        while slow and time.time() - t0 < 45:
            time.sleep(9)
            for r in list(slow):
                if adb_ok(r["s"])[0] and booted(r["s"]): slow.remove(r); say(f"   ✓ {r['name']}: Android vừa lên — không cần khởi động lại")
        jobs += [("restart", r["name"], r["s"], r["st"]) for r in slow]
    for p in extra.get("off", []):
        if whole: say(f"   - {p['name']}: bảng đang bật lại máy khách hàng loạt — để bảng làm xong"); continue
        if not busy(str(p["name"]), cl): jobs.append(("start", str(p["name"]), "127.0.0.1:%s" % p["port"], "TẮT"))
    if not jobs: return [], []
    say(f"   Khởi động lại / bật {len(jobs)} máy (mỗi lúc 3 máy, mỗi máy 1–3 phút)…")
    lock = threading.Lock()
    def one(j):
        kind, nm, s, why = j
        code, out = pctl(*(["restart", nm, "--force"] if kind == "restart" else ["start", nm]), t=600)
        last = " / ".join(x.strip() for x in out.strip().splitlines()[-2:]) or "(không có kết quả)"
        with lock: say(f"   {'✓' if code == 0 else '✗'} {nm} ({why}) → {'ép khởi động lại' if kind == 'restart' else 'bật lại'}: {last[:160]}")
        return j, code
    done = []
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for j, code in ex.map(one, jobs): done.append(j)
    say("   Chờ các máy vừa sửa lên (tối đa 5 phút)…")
    left = list(done); t0 = time.time(); final = []
    while left and time.time() - t0 < 300:
        time.sleep(10)
        for j in list(left):
            if adb_ok(j[2])[0] and booted(j[2]):
                left.remove(j); time.sleep(6)
                adb("-s", j[2], "shell", "input keyevent 224; wm dismiss-keyguard", t=10); time.sleep(2)
                b = black(j[2]); pk = focus(j[2])
                if b and is_home(pk):
                    say(f"   ✗ {j[1]}: Android đã lên nhưng VẪN ĐEN — gửi Claude dòng này"); final.append((j[1], "vẫn đen"))
                else:
                    say(f"   ✓ {j[1]}: Android đã lên, có hình — khách vào được"); final.append((j[1], "ok"))
    for j in left:
        if REMAKE_BROKEN and str(j[1]).startswith("cp_"):
            say(f"   … {j[1]}: ép khởi động lại vẫn không lên → máy hỏng: xoá hẳn + tạo lại máy mới (giữ cấu hình + hạn, mất dữ liệu cũ)")
            code, out = pctl("delete", j[1], t=600)
            gone = "Đã xoá" in out or "không còn trong" in out
            if gone:
                code, out = run2([sys.executable, os.path.join(B, "run.py"), "remake.py", "one", j[1]], 1800)
                okm = "ĐÃ LÀM MỚI" in out and "1/1" in out
                say(f"   {'✓' if okm else '✗'} {j[1]}: " + ("đã tạo lại máy mới — khách vào được" if okm else "tạo lại CHƯA được — gửi Claude dòng này: "
                    + " / ".join(x.strip() for x in out.strip().splitlines()[-2:])[:160]))
                final.append((j[1], "ok" if okm else "tạo lại lỗi")); continue
            say(f"   ✗ {j[1]}: chưa xoá được máy hỏng: {' / '.join(x.strip() for x in out.strip().splitlines()[-2:])[:160]}")
        say(f"   ✗ {j[1]}: VẪN CHƯA LÊN sau 5 phút" + ("" if REMAKE_BROKEN else " — máy hỏng: chạy lại lệnh kèm --lam-moi-may-hong để xoá + tạo lại máy mới"))
        final.append((j[1], "chưa lên"))
    return done, final

# ------------------------------------------------------------------ báo cáo thêm
def recent_report(c, res):
    node = c.get("NODE_ID", "")
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = sb_rows(c, "cloud_phones?node=eq.%s&created_at=gte.%s&select=container,status,android,replaces&order=created_at.desc&limit=60"
                   % (urllib.parse.quote(node), since)) if node else None
    if rows is None: return
    by = {r["name"]: r for r in res}
    new = [r for r in rows if r.get("container")]
    if not new: return
    sw = [r for r in new if r.get("replaces")]
    badn = [r for r in new if by.get(r["container"]) and by[r["container"]]["st"] not in ("OK", "?")]
    say(f"--- máy tạo 3 ngày qua trên máy chủ này: {len(new)} (đổi Android: {len(sw)}) · lỗi lúc kiểm: {len(badn)} ---")
    for r in badn[:20]:
        k = by[r["container"]]
        say(f"   {r['container']:<16} Android {r.get('android') or '?':<3} {'ĐỔI ANDROID · ' if r.get('replaces') else ''}{k['st']}")

def log_report():
    try: ev = json.load(open(os.path.join(B, "redroid", "tusua.json"), encoding="utf-8")).get("events", [])
    except Exception: ev = []
    if ev:
        say("--- tự sửa gần nhất (redroid\\tusua.json) ---")
        for e in ev[-5:]: say("   " + time.strftime("%d/%m %H:%M", time.localtime(int(e.get("t", 0)))) + "  " + str(e.get("what", ""))[:150])
    T = [x for x in tail(os.path.join(LOGS, "bang-tu-sua.log"), 400000) if any(k in x for k in ("XOA", "KHOI_DONG_LAI", "NHAN_LAI", "GIU_LAI", "làm mới", "tạo lại"))]
    if T:
        say("--- bảng CloudBlue tự sửa gần nhất (logs\\bang-tu-sua.log) ---")
        for x in T[-5:]: say("   " + x[:170])
    L = tail(os.path.join(LOGS, "phat-hinh.log"))
    ks = ("lỗi bật hình", "ĐEN", "hình đen", "không ra khung", "ngừng ra hình", "lỗi quay", "không xuất được hình", "Traceback")
    er = [x for x in L if any(k in x for k in ks)]
    if er:
        say(f"--- lỗi phát hình gần nhất ({len(er)} dòng trong nhật ký) ---")
        for x in er[-5:]: say("   " + x[:170])

def main():
    c = conf(); node = c.get("NODE_ID") or "?"
    say(f"== CloudBlue · sửa tất cả ({VER}) · máy chủ {node} · {time.strftime('%d/%m %H:%M')}" + (" · CHỈ KIỂM" if ONLY_CHECK else "") + " ==")
    probs = []
    changed, p = update_files(); probs += p
    probs += restart_services(changed, {svc for gp, local, mark, svc in FILES if svc and os.path.isfile(os.path.join(B, local))
                                        and mark.encode() in open(os.path.join(B, local), "rb").read()})
    probs += fix_autostart()
    e = ensure_running(c)
    if e and e != "LAUNCHED": probs.append(e)
    probs += check_net(c)
    if e == "LAUNCHED":
        say("5/6 · 6/6 Bỏ qua kiểm máy khách: bảng CloudBlue vừa tự bật lại và đang bật lần lượt từng máy (vài phút) —\n"
            "    10 phút nữa chạy lại lệnh này để kiểm từng máy.")
        res, extra, done, final = [], {}, [], []
        probs.append("vừa mở lại bảng — 10 phút nữa chạy lại lệnh để kiểm máy khách")
    else:
        res, extra, p = check_phones(c); probs += p
        done, final = fix_phones(res, extra) if res or extra.get("off") else ([], [])
    rm = []
    if REMAKE and GHOST and not ONLY_CHECK: rm = remake_ghosts()
    recent_report(c, res)
    log_report()
    okn = sum(1 for r in res if r["st"] == "OK")
    inapp = [r["name"] for r in res if r["st"] == "ĐEN TRONG APP"]
    still = [n for n, k in final if k != "ok"]
    say(f"== TÓM TẮT {node} ==")
    if changed: say("   ✓ đã cập nhật: " + ", ".join(sorted(set(changed))))
    say(f"   máy khách: {okn} có hình · {len(done)} vừa sửa ({sum(1 for _, k in final if k == 'ok')} đã có hình)"
        + (f" · {extra.get('sleep', 0)} đang ngủ" if extra else "") + (f" · {len(inapp)} đen trong app (không đụng)" if inapp else ""))
    if rm: say(f"   ✓ đã tạo lại {rm[0]}/{rm[1]} máy \"ma\" cho khách")
    for x in probs: say("   ✗ " + x)
    for n in still: say(f"   ✗ {n}: sửa rồi vẫn {dict(final).get(n)}")
    say("   → XONG, máy chủ ổn." if not probs and not still else "   → Còn dòng ✗ ở trên: chụp phần TÓM TẮT gửi Claude.")

if __name__ == "__main__":
    main()
