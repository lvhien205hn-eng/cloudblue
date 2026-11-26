# -*- coding: utf-8 -*-
"""23/11 · 🗗 TAB CỬA SỔ NHỎ — THỬ NGHIỆM (chỉ ghi kết quả, không làm trượt bài) trên máy Android ảo thật, chạy SAU test_win.py:
   A. GAME TỰ CO VỪA KHUNG: game "cũ" (mkapk.sh app 4, 5) dựng khung 1 lần theo cỡ lúc mở → cửa sổ nhỏ bị TRÀN VIỀN nếu Android ép đổi cỡ.
      E1 như hiện nay (force_resizable_activities=1) · E2 tắt ép đổi cỡ + cho app không đổi cỡ vào cửa sổ (Android thu nhỏ HÌNH = size compat)
      · E3 app khai báo đổi cỡ được: am compat FORCE_NON_RESIZE_APP · E4 đổi cài đặt lúc game đang chạy (không mở lại game).
   B. MỞ APP KHÁC ĐÈ LÊN: tab nhỏ có bị tắt (pid đổi), tải lại (create lần 2), dừng (stop) không · cách giữ tab nhỏ vẫn hiện (app mới thành cửa sổ to).
   Chạy:  python3 test_fit.py <api> <thư mục apk> <thư mục ảnh>   → in kết quả + <ảnh>/fit-<api>-ketqua.txt"""
import importlib.util, os, re, subprocess, sys, tempfile, time

API, APKS, OUT = int(sys.argv[1]), sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = "vn.cloudblue.wintest.Main"
RES = []


def adb(*a, t=90):
    return subprocess.run(["adb"] + list(a), capture_output=True, timeout=t)


def sh(c, t=30):
    r = adb("shell", c, t=t + 20)
    return ((r.stdout or b"") + (r.stderr or b"")).decode(errors="ignore").strip()


def shot(name):
    try:
        r = adb("exec-out", "screencap -p", t=40)
        if r.stdout and r.stdout[:4] == b"\x89PNG": open(os.path.join(OUT, f"fit-{API}-{name}.png"), "wb").write(r.stdout)
    except Exception as e: print("   (chưa chụp được ảnh", name, e, ")")


def note(key, text):
    RES.append(f"{key}: {text}"); print(f"  ▶ {key}: {text}", flush=True)


home = tempfile.mkdtemp(prefix="cpapi_fit_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\n")
os.environ["HOME"] = home
spec = importlib.util.spec_from_file_location("cpapi_f", os.path.join(ROOT, "cpapi.py"))
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)


def pkg(n): return f"vn.cloudblue.wintest{n}"


def logs(): return sh("logcat -d -s wintest:I", 40).splitlines()


def size(n):
    """Cỡ khung nhìn lần cuối của game n: (rộng, cao, rộng khung gốc, cao khung gốc) hoặc None."""
    m = [re.search(rf"n={n} size=(\d+)x(\d+) frame=(\d+)x(\d+)", l) for l in logs()]
    m = [x for x in m if x]
    return tuple(int(v) for v in m[-1].groups()) if m else None


def creates(n): return sum(1 for l in logs() if re.search(rf"n={n} u=0 create", l))


def pid(n): return sh(f"pidof {pkg(n)}").strip()


def states():
    """Trạng thái từng app thử theo dumpsys (RESUMED / PAUSED / STOPPED…) + dòng về size compat."""
    st, cur, sc = {}, None, {}
    for l in sh("dumpsys activity activities", 60).splitlines():
        m = re.search(r"ActivityRecord\{\S+ u0 (vn\.cloudblue\.wintest\d)/", l)
        if m: cur = m.group(1)[-1]; continue
        if cur and cur not in st:
            m = re.search(r"\bstate=(\w+)", l)
            if m: st[cur] = m.group(1)
        if cur and re.search(r"(?i)sizecompat|compatdisplayinsets|compat scale|mSizeCompat", l): sc.setdefault(cur, []).append(l.strip()[:160])
    return st, sc


def task(n):
    for t in cp.win_state(sh)["tasks"]:
        if t["pkg"] == pkg(n) and t["user"] == 0: return t
    return None


def start(n):
    sh(f"am start -W {cp.AS_ICON} -n {pkg(n)}/{MAIN}", 40); time.sleep(3)      # như bấm biểu tượng trên màn chính


def mini():
    code, j = cp.win_run(sh, "mini"); time.sleep(2.5)
    return code, j


def conf(force, nonres):
    sh(f"settings put global force_resizable_activities {force}; settings put global enable_non_resizable_multi_window {nonres}; "
       "settings put global enable_sizecompat_freeform 1"); time.sleep(1.5)


def fit(n, label):
    s, t = size(n), task(n)
    st, sc = states()
    if not s or not t:
        note(label, f"không đọc được (size={s} task={t and (t['mode'], t['b'])})"); return None
    w, h, fw, fh = s
    win = (t["b"][2] - t["b"][0], t["b"][3] - t["b"][1])
    scaled = t["mode"] == "freeform" and w >= fw - 2 and h >= fh - 2 and win[0] < fw - 20
    crop = t["mode"] == "freeform" and (w < fw - 2 or h < fh - 2)
    note(label, f"cửa sổ {t['mode']} {win[0]}x{win[1]} · app thấy {w}x{h} · khung game {fw}x{fh} → "
         + ("VỪA KHUNG (Android thu nhỏ hình)" if scaled else "TRÀN VIỀN (app bị ép nhỏ, khung game không co)" if crop else "?")
         + (f" · compat: {' | '.join(sc.get(str(n), [])[:2])}" if sc.get(str(n)) else ""))
    return "vua" if scaled else "tran" if crop else "?"


print(f"== THỬ NGHIỆM tab nhỏ · Android API {API} ==", flush=True)
for n in (4, 5):
    r = adb("install", "-r", "-t", os.path.join(APKS, f"wintest{n}.apk"), t=180)
    print(f"cài wintest{n}:", (r.stdout + r.stderr).decode(errors="ignore").strip()[-80:], flush=True)
sh("for n in 1 2 3 4 5; do am force-stop vn.cloudblue.wintest$n; done; input keyevent 3", 40); time.sleep(2)
sh("logcat -c")
print("cài đặt lúc đầu:", sh("settings get global force_resizable_activities; settings get global enable_non_resizable_multi_window; "
                            "settings get global enable_sizecompat_freeform").split(), flush=True)

# ---------------- A. game tự co vừa khung ----------------
print("A. Game tự co vừa khung", flush=True)
try:
    conf(1, 0); start(4); code, j = mini()
    print("   E1 mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E1 kết quả=" + str(fit(4, "E1 như hiện nay (ép đổi cỡ) · game 4 không đổi cỡ"))); shot("1-ep-doi-co")

    sh(f"am force-stop {pkg(4)}; input keyevent 3"); conf(0, 1); start(4); code, j = mini()
    print("   E2 mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E2 kết quả=" + str(fit(4, "E2 tắt ép đổi cỡ + cho app không đổi cỡ vào cửa sổ · game 4"))); shot("2-khong-ep-doi-co")

    sh(f"am force-stop {pkg(4)}; input keyevent 3"); start(5); code, j = mini()
    print("   E3a mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E3a kết quả=" + str(fit(5, "E3a cùng cài đặt E2 · game 5 KHAI BÁO đổi cỡ được"))); shot("3a-game-khai-doi-co")
    out = sh(f"am compat enable FORCE_NON_RESIZE_APP {pkg(5)}", 40)
    note("E3 lệnh am compat", out.replace("\n", " | ")[:200] or "(trống)")
    sh(f"am force-stop {pkg(5)}; input keyevent 3"); start(5); code, j = mini()
    print("   E3b mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E3b kết quả=" + str(fit(5, "E3b + am compat FORCE_NON_RESIZE_APP · game 5"))); shot("3b-compat")
    sh(f"am compat reset FORCE_NON_RESIZE_APP {pkg(5)}", 40)

    sh(f"for n in 4 5; do am force-stop vn.cloudblue.wintest$n; done; input keyevent 3"); conf(1, 0); start(4)
    conf(0, 1); code, j = mini()                       # đổi cài đặt lúc game ĐANG chạy (không mở lại game)
    print("   E4 mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E4 kết quả=" + str(fit(4, "E4 đổi cài đặt lúc game đang chạy · game 4"))); shot("4-doi-luc-dang-chay")

    sh(f"for n in 4 5; do am force-stop vn.cloudblue.wintest$n; done; input keyevent 3"); conf(0, 1); start(5)
    out = sh(f"am compat enable --no-kill FORCE_NON_RESIZE_APP {pkg(5)}", 40)   # bật lúc game (khai báo đổi cỡ) ĐANG chạy, không tắt game
    note("E5 lệnh am compat --no-kill", out.replace("\n", " | ")[:200] or "(trống)")
    p5 = pid(5); code, j = mini()
    print("   E5 mini:", code, j.get("msg") or j.get("error"), flush=True)
    RES.append("E5 kết quả=" + str(fit(5, "E5 am compat --no-kill lúc game đang chạy rồi thu nhỏ · game 5")) + f" · game không bị tắt={pid(5) == p5}")
    shot("5-compat-dang-chay")
    sh(f"am compat reset FORCE_NON_RESIZE_APP {pkg(5)}", 40)

    # E6 (Android 9–12): MỞ LẠI game ngay trong cửa sổ → game dựng khung theo cỡ cửa sổ (vừa khung) — game khởi động lại
    sh(f"for n in 4 5; do am force-stop vn.cloudblue.wintest$n; done; input keyevent 3"); conf(1, 0); start(4); code, j = mini()
    t = task(4); b0 = t and t["b"]
    sdk = int(sh("getprop ro.build.version.sdk") or 0)
    sh(f"am force-stop {pkg(4)}"); time.sleep(1)
    out = sh(f"am start --user 0 {'--display 0 ' if sdk >= 29 else ''}--windowingMode 5 {cp.AS_ICON} -n {pkg(4)}/{MAIN} 2>&1", 30)
    t = None
    for _ in range(10):
        time.sleep(0.3); t = task(4)
        if t and t["mode"] == "freeform": break
    b1 = t and t["b"]
    if t and b0 and b1 != b0: sh(f"am task resize {t['id']} {b0[0]} {b0[1]} {b0[2]} {b0[3]}")
    time.sleep(4)
    note("E6 mở lại game trong cửa sổ", f"chỗ cũ {b0} · mở lại vào {b1} ({'giữ chỗ' if b1 == b0 else 'chỗ khác → đổi cỡ ngay'})")
    RES.append("E6 kết quả=" + str(fit(4, "E6 mở lại game trong cửa sổ · game 4"))); shot("6-mo-lai-trong-cua-so")
except Exception as e:
    note("A lỗi", repr(e)[:300])

# ---------------- B. mở app khác đè lên: tab nhỏ có sao không ----------------
def run_b(tag, force, nonres):
    """Mục B với 1 kiểu cài đặt: tag "B" = cách máy chủ đang dùng cho bản Android này (cpapi.win_conf_sh), "Bép" = ép đổi cỡ (cách cũ) để so."""
    print(f"{tag}. Mở app khác đè lên tab nhỏ (force_resizable={force}, non_resizable_multi_window={nonres})", flush=True)
    try:
        sh("for n in 1 2 3 4 5; do am force-stop vn.cloudblue.wintest$n; done; input keyevent 3", 40); time.sleep(2); conf(force, nonres); sh("logcat -c")
        start(4); mini(); start(3); mini()
        p0 = {n: pid(n) for n in (3, 4)}; c0 = {n: creates(n) for n in (3, 4)}
        t3 = task(3)
        if t3: note(f"{tag} am task focus (đưa tab lên không gửi lệnh mở)", sh(f"am task focus {t3['id']} 2>&1").replace("\n", " ")[:160] or "(trống)")
        st, _ = states(); note(f"{tag}0 có 2 tab nhỏ", f"trạng thái {st} · pid {p0}"); shot(f"{tag.lower()}0-hai-tab-nho")
        start(1); time.sleep(15)                                # khách mở app khác (toàn màn, ép ngang) đè lên
        st, _ = states(); p1 = {n: pid(n) for n in (3, 4)}; c1 = {n: creates(n) for n in (3, 4)}
        note(f"{tag}1 mở app 1 toàn màn đè lên 15 giây", f"trạng thái {st} · pid giữ nguyên={p1 == p0} · tải lại={c1 != c0} ({c0}→{c1})"); shot(f"{tag.lower()}1-mo-app-de-len")
        oom = sh("for n in 3 4; do p=$(pidof vn.cloudblue.wintest$n); [ -n \"$p\" ] && echo \"$n:$(cat /proc/$p/oom_score_adj)\"; done")
        note(f"{tag}1 oom_score_adj (càng cao càng dễ bị Android tắt khi thiếu RAM)", oom.replace("\n", " "))
        t1 = task(1)                                             # cách giữ tab nhỏ vẫn hiện: app mới thành cửa sổ TO (gần hết màn)
        if t1:
            sh("input keyevent 3"); time.sleep(1)
            d = cp.win_to(sh, t1, cp.WIN_FREEFORM, int(sh("getprop ro.build.version.sdk") or 0), time.sleep)
            if d:
                g = cp.win_settle(sh)["geo"]; a = cp.win_area(g); sh(f"am task resize {d['id']} {a[0]} {a[1]} {a[2]} {a[3]}"); time.sleep(4)
            st, _ = states(); c2 = {n: creates(n) for n in (3, 4)}
            oom = sh("for n in 3 4; do p=$(pidof vn.cloudblue.wintest$n); [ -n \"$p\" ] && echo \"$n:$(cat /proc/$p/oom_score_adj)\"; done")
            note(f"{tag}2 app mới thành cửa sổ to (đổi={bool(d)})", f"trạng thái {st} · tải lại={c2 != c0} ({c2}) · oom {oom.replace(chr(10), ' ')}"); shot(f"{tag.lower()}2-app-moi-cua-so-to")
        c2b = {n: creates(n) for n in (3, 4)}
        code, j = cp.win_run(sh, "tile"); time.sleep(3)
        st, _ = states(); p3 = {n: pid(n) for n in (3, 4)}; c3 = {n: creates(n) for n in (3, 4)}
        note(f"{tag}3 Sắp xếp tab", f"{code} {j.get('msg') or j.get('error')} · trạng thái {st} · pid giữ nguyên={p3 == p0} · tải lại={c3 != c0} "
             f"(trước Sắp xếp {c2b} → sau {c3})"); shot(f"{tag.lower()}3-sap-xep")
        life = [l.split("wintest:")[-1].strip() for l in logs() if re.search(r"n=[34] u=0 (pause|stop|resume|start|create|size)", l)]
        note(f"{tag} nhật ký app 3/4", " · ".join(life[-18:]))
    except Exception as e:
        note(f"{tag} lỗi", repr(e)[:300])


if API in (31, 32, 33): run_b("Bep", 1, 0)                   # 12 / 12L / 13: so với cách cũ (ép đổi cỡ) — xem tải lại do cài đặt hay do bản Android
_c = cp.win_conf_sh(API)
run_b("B", 0 if "force_resizable_activities 0" in _c else 1, 1 if "enable_non_resizable_multi_window 1" in _c else 0)

open(os.path.join(OUT, f"fit-{API}-ketqua.txt"), "w", encoding="utf-8").write("\n".join(RES) + "\n")
print("\n".join(RES), flush=True)
