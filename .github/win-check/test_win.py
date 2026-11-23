# -*- coding: utf-8 -*-
"""23/11 · 🗗 TAB CỬA SỔ NHỎ — thử THẬT trên máy Android ảo (GitHub Actions có KVM): cpapi.win_run chạy qua adb vào Android 9 / 10 / 11 / 12 / 15.
   3 app "giống Roblox" (ép màn ngang, không đổi cỡ được — mkapk.sh) + 1 bản clone trong hồ sơ Công việc (y như Clone tab của máy thật):
   thu nhỏ → về màn chính → mở app khác → thu nhỏ (cửa sổ cũ vẫn đúng chỗ, hiện lại) → clone → kéo thanh tiêu đề (dời) + kéo góc (đổi cỡ)
   bằng chạm như khách bấm qua luồng hình → sắp xếp (dọc, ngang) → phóng to → thu nhỏ lại. Chụp ảnh từng bước.
   Chạy (máy ảo đã bật):  python3 test_win.py <api> <thư mục apk> <thư mục ảnh>"""
import importlib.util, os, re, subprocess, sys, tempfile, time

API, APKS, OUT = int(sys.argv[1]), sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK, INFO, FAILS = [0, 0], [], []


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True); FAILS.append(name + " → " + str(extra)[:400])


def info(name, cond, extra=""):
    """Kiểm tra mang tính THÔNG TIN (không làm trượt cả bài): kéo / đổi cỡ bằng chạm tuỳ bản Android."""
    INFO.append((name, cond)); print("  " + ("ⓘ✓" if cond else "ⓘ✗"), name, "" if cond else "→ " + str(extra)[:600], flush=True)


def adb(*a, t=90):
    return subprocess.run(["adb"] + list(a), capture_output=True, timeout=t)


def sh(c, t=30):
    r = adb("shell", c, t=t + 20)
    return ((r.stdout or b"") + (r.stderr or b"")).decode(errors="ignore").strip()


def shot(name):
    try:
        r = adb("exec-out", "screencap -p", t=40)
        if r.stdout and r.stdout[:4] == b"\x89PNG": open(os.path.join(OUT, f"win-{API}-{name}.png"), "wb").write(r.stdout)
    except Exception as e: print("   (chưa chụp được ảnh", name, e, ")")


def boot_wait(limit=420):
    adb("wait-for-device", t=limit)
    t0 = time.time()
    while time.time() - t0 < limit:
        if sh("getprop sys.boot_completed", 15).strip() == "1": break
        time.sleep(3)
    time.sleep(8)
    for c in ("wm dismiss-keyguard", "input keyevent 82", "svc power stayon true"): sh(c, 15)


# ---------------- chuẩn bị máy: root (để tạo hồ sơ clone), bật cửa sổ nổi như phonectl TUNE, khởi động lại ----------------
print(f"== Android API {API} ==", flush=True)
home = tempfile.mkdtemp(prefix="cpapi_win_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\n")
os.environ["HOME"] = home
spec = importlib.util.spec_from_file_location("cpapi_w", os.path.join(ROOT, "cpapi.py"))
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
# 23/11b: cài đặt cửa sổ nổi THEO BẢN ANDROID như máy chủ (phonectl TUNE = cpapi.win_conf_sh): Android 15 không ép đổi cỡ → thu nhỏ hình game
TUNE = ("locksettings set-disabled true; settings put system screen_off_timeout 2147483647; " + cp.win_conf_sh(API) + "; "
        "settings put global enable_sizecompat_freeform 1; settings put system accelerometer_rotation 0; settings put system user_rotation 0")
FREE = "settings get global enable_freeform_support; settings get global force_resizable_activities"
WANT = ["1", "0" if API >= cp.WIN_SCM_SDK else "1"]
print(adb("root").stdout.decode(errors="ignore").strip()); adb("wait-for-device", t=120); time.sleep(3); boot_wait(120)
for k in range(3):                       # như phonectl TUNE mỗi lần máy bật; có lần máy ảo chưa nhận lệnh (adbd vừa đổi sang root) → kiểm, làm lại
    sh(TUNE, 30); time.sleep(2); print("đặt cửa sổ nổi:", sh(FREE).split(), flush=True)
    adb("reboot", t=60); time.sleep(10); boot_wait()
    print(adb("root").stdout.decode(errors="ignore").strip()); adb("wait-for-device", t=120); time.sleep(3); boot_wait(120)
    if sh(FREE).split()[:2] == WANT: break
    print("   (sau khi khởi động lại chưa thấy cài đặt cửa sổ nổi → làm lại)", flush=True)
else:
    sh(TUNE, 30); time.sleep(3)          # Android 11+ nhận ngay không cần khởi động lại
sh("wm size 720x1280; wm density 320", 20); time.sleep(3)                    # giống máy Cloud Phone thật (720x1280, 320 dpi)
print("freeform:", sh("settings get global enable_freeform_support; settings get global force_resizable_activities"), "·", sh("wm size; wm density"), flush=True)
for n in (1, 2, 3, 4):
    r = adb("install", "-r", "-t", os.path.join(APKS, f"wintest{n}.apk"), t=180)
    print(f"cài wintest{n}:", (r.stdout + r.stderr).decode(errors="ignore").strip()[-120:], flush=True)
print("--- am stack list (lúc đầu) ---\n" + sh("am stack list")[:3000], flush=True)
print("--- dumpsys window displays ---\n" + "\n".join(l for l in sh("dumpsys window displays").splitlines() if re.search(r"mDisplayId=|cur=", l))[:1500], flush=True)

MAIN = "vn.cloudblue.wintest.Main"


def comp(n): return f"vn.cloudblue.wintest{n}/{MAIN}"


def open_app(n, user=0):
    """Khách mở app (như bấm biểu tượng) — toàn màn."""
    o = sh(f"am start --user {user} -W {'--windowingMode 1 ' if API >= 28 else ''}-a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
           f"-f 0x10200000 -n {comp(n)}", 40)
    time.sleep(3); return o


def tasks():
    return cp.win_tasks(sh("am stack list"), API)


def task(n, user=0):
    return next((t for t in tasks() if t["pkg"] == f"vn.cloudblue.wintest{n}" and t["user"] == user and t["type"] in ("standard", "")), None)


TRACE = []


def tsh(c, t=30):
    """sh có ghi lại lệnh cpapi gửi (trừ lệnh đọc danh sách) + chữ máy trả → in ra để xem từng bản Android đi đường nào."""
    o = sh(c, t)
    if c != cp.WIN_STATE_SH and not c.startswith("am stack list"):
        TRACE.append(f"      $ {c[:150]}" + (f"\n        ↳ {' | '.join(o.splitlines())[:240]}" if o else ""))
    return o


XOAY = cp.rot_apk() or os.path.join(APKS, "cbxoay.apk")          # app trợ giúp xoay màn: bản nằm trong cpapi (ROT_APK_B64), chưa có thì bản vừa dựng


def inst():
    r = adb("install", "-r", XOAY, t=180); o = (r.stdout + r.stderr).decode(errors="ignore").strip()
    print("   cài app trợ giúp xoay màn:", XOAY, "→", o[-120:], flush=True)
    return "Success" in o


def run(do):
    TRACE.clear(); t0 = time.time(); code, j = cp.win_run(tsh, do, inst=inst)
    print(f"   win_run({do}) → {code} {j} · {time.time() - t0:.1f} giây", flush=True)
    print("\n".join(TRACE[:60]), flush=True); time.sleep(2)
    return code, j


NEW = API >= cp.WIN_REFIT_SDK                                    # 23/11d: Android 10+ mở lại app KIỂU CŨ ngay trong tab (Android 9: như cũ)
def logs(): return sh("logcat -d -s wintest:I", 40).splitlines()
def creates(n, user=0): return len([l for l in logs() if f"n={n} u={user} create" in l])
def last_size(n, user=0):
    m = [re.search(rf"n={n} u={user} size=(\d+)x(\d+)", l) for l in logs()]; m = [x for x in m if x]
    return tuple(int(v) for v in m[-1].groups()) if m else None
def prevv(): return sh(f"settings get global {cp.WIN_PREV_KEY}").strip()
def dens(): return [int(v) for v in re.findall(r"density:\s*(\d+)", sh("wm density"))][-1:]
def want(g, ws):
    """Chỗ đúng sau Sắp xếp: app đổi cỡ thật → nguyên ô lưới; app kiểu cũ (Android 10+) → cửa sổ đúng tỉ lệ hình game ở góc trên trái của ô."""
    kd = cp.win_kinds(sh) if NEW else {}
    return [cp.win_shape(g, c, kd[t["id"]]["fixed"]) if kd.get(t["id"], {}).get("old") else c for t, c in zip(ws, cp.win_grid(g, len(ws)))]
def fitted(sz, b, g):
    """App dựng hình đúng theo cửa sổ: bề ngang = cửa sổ, bề cao = cửa sổ trừ thanh tiêu đề (không tràn, không hụt nhiều)."""
    return bool(sz) and bool(b) and abs(sz[0] - (b[2] - b[0])) <= 6 and -2 <= (b[3] - b[1]) - sz[1] <= g["cap"] * 2 + 24


def area(b): return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


st0 = cp.win_state(sh); g0 = st0["geo"]
print("geo:", g0, "sdk:", st0["sdk"], "free:", st0["free"], flush=True)
D0 = (dens() or [320])[0]                                        # mật độ lúc đầu của máy thử (320)
_m0 = re.search(r"Override size:\s*(\d+x\d+)", sh("wm size")); SIZE0 = _m0.group(1) if _m0 else ""      # cỡ màn máy ảo nhận (API 31 / 32: 640x1280)
SHORT0 = min(g0["w"], g0["h"]); DENS_NOW = [D0]
print("--- máy có nhận khoá xoay không:", sh(cp.WIN_AUTOROT_SH), flush=True)
ck("đọc được danh sách tab + cỡ màn (dọc)", st0["ok"] and st0["sdk"] == API and g0["h"] > g0["w"] > 0, st0)

# 1. thu nhỏ app 1
sh("logcat -c"); open_app(1); shot("1-app1-toan-man")
a = task(1)
ck("app 1 mở toàn màn, đang hiện", a and a["mode"] == "fullscreen" and a["vis"], a)
print("--- loại app (dumpsys activity activities) ---\n" + sh(cp.WIN_KIND_SH, 40)[:1800] + "\n    → " + str(cp.win_kinds(sh)), flush=True)
print("--- mọi dòng nói về hướng / đổi cỡ của app 1 ---\n" + sh("dumpsys activity activities | grep -A90 'Hist.*wintest1' | grep -i -E 'orient|resiz' | head -n 14", 40)[:1500], flush=True)
print("--- tiến trình app 1 (ps) ---\n" + sh(cp.WIN_PS_SH.format(p="vn.cloudblue.wintest1"))[:500], flush=True)
if NEW:
    ck("đọc được loại app + pid: app 1 khai báo không đổi cỡ + ép ngang → app KIỂU CŨ, có đúng 1 tiến trình",
       a and cp.win_kinds(sh).get(a["id"]) == {"old": True, "fixed": "land"} and len(cp.win_pids(sh, "vn.cloudblue.wintest1", 0)) == 1,
       (cp.win_kinds(sh), cp.win_pids(sh, "vn.cloudblue.wintest1", 0)))
id1 = a["id"] if a else None
code, j = run("mini"); time.sleep(2); a = task(1); shot("2-thu-nho-app1")
ck("Thu nhỏ tab → app 1 thành cửa sổ nổi đúng ô đã tính", code == 200 and a and a["mode"] == "freeform" and a["vis"] and tuple(j.get("b") or ()) == a["b"], (code, j, a))
b1 = a["b"] if a else None
if NEW and j.get("fit") != "ok":
    sh("input keyevent 3"); time.sleep(4)
    print("--- CHẨN ĐOÁN: app không tắt nền được. 4 giây sau khi về màn chính: ---\n" + sh("am stack list | grep -E 'taskId=.*wintest'")[:400] + "\n"
          + sh("dumpsys activity activities | grep -E 'Hist +#|state=|mVisibleRequested|visible=' | grep -A3 wintest1", 40)[:900] + "\n"
          + sh("dumpsys activity oom 2>/dev/null | grep -B1 -A2 wintest1", 40)[:900] + "\n"
          + sh("dumpsys activity services vn.cloudblue.wintest1 2>/dev/null | head -n 12", 40)[:600], flush=True)
    time.sleep(8)
    print("--- 12 giây sau: ---\n" + sh("dumpsys activity activities | grep -E 'Hist +#|state=|mVisibleRequested|visible=' | grep -A3 wintest1", 40)[:900] + "\n"
          + sh("dumpsys activity oom 2>/dev/null | grep -B1 -A2 wintest1", 40)[:900] + "\n" + sh("am kill --user 0 vn.cloudblue.wintest1; sleep 1; ps -A -o USER,PID,NAME | grep wintest1")[:300], flush=True)
    if a: sh(f"am task focus {a['id']}"); time.sleep(2)
if NEW:
    scr1 = cp.win_screen(sh) or {}; gA = cp.win_state(sh)["geo"]; sz = last_size(1)
    ck(f"… app kiểu cũ trên màn 360 dp, chưa có tab nhỏ nào → máy TỰ bật màn rộng (≥ 600 dp, nhớ mật độ cũ {D0} + dấu tự bật), mở lại app ĐÚNG 1 LẦN vào ĐÚNG TAB cũ",
       code == 200 and j.get("fit") == "ok" and (j.get("sw") or 0) >= 600 and scr1.get("sw", 0) >= 600 and prevv() == f"{D0}:{SHORT0}:a" and creates(1) == 2
       and a and a["id"] == id1, (j, scr1, prevv(), creates(1), id1, a))
    ck(f"… app dựng hình theo ĐÚNG CỠ CỬA SỔ (vừa khung): app thấy {sz} · cửa sổ {a and a['b']} · thanh tiêu đề {gA['cap']} px; phần hình đúng tỉ lệ game 16:9",
       a and fitted(sz, a["b"], gA) and abs((a["b"][2] - a["b"][0]) * 9 - (a["b"][3] - a["b"][1] - gA["cap"]) * 16) <= 16, (sz, a and a["b"], gA))
    gs1 = cp.win_state(sh)["geo"]
    ck("… màn về DỌC sau khi game ngang thành cửa sổ, cửa sổ nằm trong màn", gs1["h"] > gs1["w"] and a and a["b"][2] <= gs1["w"] and a["b"][3] <= gs1["h"], (gs1, a and a["b"]))

# 2. về màn chính → mở app 2 → thu nhỏ
sh("input keyevent 3"); time.sleep(2); shot("3-ve-man-chinh")
open_app(2)
code, j = run("mini"); a, b = task(1), task(2); shot("4-thu-nho-app2")
ck("về màn chính rồi mở app 2 → thu nhỏ: 2 cửa sổ cùng hiện, cửa sổ app 1 giữ đúng chỗ, cửa sổ mới vào chỗ trống",
   code == 200 and a and b and a["mode"] == b["mode"] == "freeform" and a["vis"] and b["vis"] and a["b"] == b1 and cp._ovl(a["b"], b["b"]) == 0
   and b["b"] == tuple(j.get("b") or ()), (code, j, a, b))
if NEW:
    gB = cp.win_state(sh)["geo"]; sz = last_size(2)
    ck(f"… màn đã rộng → không đổi mật độ nữa; app 1 KHÔNG bị mở lại; app 2 mở lại đúng 1 lần và dựng hình đúng cỡ cửa sổ: app thấy {sz} · cửa sổ {b and b['b']}",
       j.get("fit") == "ok" and not j.get("sw") and creates(1) == 2 and creates(2) == 2 and b and fitted(sz, b["b"], gB), (j, creates(1), creates(2), sz, b and b["b"]))

# 3. kéo thanh tiêu đề (dời) + kéo góc (đổi cỡ) bằng chạm — như khách bấm qua luồng hình
if b:
    l, t_, r, bo = b["b"]; cap = g0["cap"]; x = (l + r) // 2 - 60; y = t_ + cap // 2
    sh(f"input touchscreen swipe {x} {y} {x + 40} {y + 160} 900"); time.sleep(2); b2 = task(2)
    info("kéo thanh trên cùng của cửa sổ (chạm) → cửa sổ dời xuống", b2 and b2["b"][1] > t_ + 60, (b["b"], b2 and b2["b"]))
    shot("5-keo-doi-cho")
    if b2:
        l, t_, r, bo = b2["b"]
        sh(f"input touchscreen swipe {r - 3} {bo - 3} {min(g0['w'] - 2, r + 120)} {min(g0['h'] - 2, bo + 90)} 900"); time.sleep(2); b3 = task(2)
        if not (b3 and area(b3["b"]) > area(b2["b"]) * 1.05):
            sh(f"input touchscreen swipe {r + 6} {bo + 6} {min(g0['w'] - 2, r + 120)} {min(g0['h'] - 2, bo + 90)} 900"); time.sleep(2); b3 = task(2)
        info("kéo góc dưới phải (chạm) → cửa sổ to ra", b3 and area(b3["b"]) > area(b2["b"]) * 1.05, (b2["b"], b3 and b3["b"]))
        shot("6-keo-doi-co")

# 4. bản clone trong hồ sơ Công việc (như Clone tab)
sh("setprop fw.max_users 8")
o = sh("pm create-user --profileOf 0 --managed CloneTab", 60); m = re.search(r"created user id (\d+)", o)
U = int(m.group(1)) if m else None
print("hồ sơ clone:", o[-160:], flush=True)
def settle_system(limit=120):
    """Tạo / mở hồ sơ clone có lúc làm Android (máy ảo 10) khởi động lại giao diện → chờ đọc được danh sách tab lại + đặt lại cỡ màn."""
    end = time.time() + limit
    while time.time() < end:
        try:
            if sh("getprop sys.boot_completed", 15).strip() == "1" and cp.win_state(sh)["ok"]: break
        except Exception: pass
        time.sleep(3)
    if SIZE0 and f"Override size: {SIZE0}" not in sh("wm size"):   # giao diện Android khởi động lại làm mất cỡ màn đã đặt → đặt lại ĐÚNG cỡ + mật độ đang thử
        sh(f"wm size {SIZE0}; wm density {(DENS_NOW or [D0])[0]}", 20); time.sleep(3); print("   (đặt lại cỡ màn sau khi Android khởi động lại giao diện)", flush=True)


DENS_NOW = dens()
if U:
    print(sh(f"am start-user {U}; pm install-existing --user {U} vn.cloudblue.wintest1", 60)[-200:], flush=True)
    time.sleep(3); settle_system()
    sh("input keyevent 3"); time.sleep(2)                          # như khách: về màn chính rồi bấm biểu tượng bản clone (đang ở trong cửa sổ thì
    open_app(1, U)                                                 # Android 12 có lúc mở bản clone luôn thành cửa sổ → "Các tab đang là cửa sổ nhỏ rồi")
    if (task(1, U) or {}).get("mode") == "freeform": open_app(1, U)
    code, j = run("mini"); c = task(1, U); shot("7-thu-nho-clone")
    ck("bản clone (hồ sơ Công việc) thu nhỏ được → 3 cửa sổ", code == 200 and c and c["mode"] == "freeform" and c["vis"] and j.get("n") == 3, (code, j, c))
else:
    info("tạo hồ sơ clone trên máy ảo (máy thật đã có sẵn)", False, o)
n0 = len([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")])
open_app(3)                                                         # app 3 KHAI BÁO đổi cỡ được (app thường) — Android 9 đi đường mở thẳng
code, j = run("mini"); c3 = task(3); shot("7b-thu-nho-app3")
ck("app 3 (đổi cỡ được) thu nhỏ được, nằm trong màn", code == 200 and c3 and c3["mode"] == "freeform" and c3["vis"] and j.get("n") == n0 + 1
   and c3["b"][2] <= cp.win_state(sh)["geo"]["w"] + 1, (code, j, c3))
if NEW:
    ck("… app 3 khai báo ĐỔI CỠ ĐƯỢC: không bị mở lại (vẫn chạy), web được báo hiện nút Vừa khung (fit=ask); các app kiểu cũ khác cũng không bị mở lại",
       j.get("fit") == "ask" and creates(3) == 1 and creates(1) == 2 and creates(2) == 2, (j, creates(3), creates(1), creates(2)))

# 5. sắp xếp (dọc) — sau khi về màn chính (màn chính che hết cửa sổ)
sh("input keyevent 3"); time.sleep(2)
c1, c2 = creates(1), creates(2)
code, j = run("tile"); time.sleep(2); ws = sorted([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")], key=lambda t: t["id"])
g5t = cp.win_state(sh)["geo"]; cells = want(g5t, ws); shot("8-sap-xep-doc")
ck(f"Sắp xếp tab (màn dọc): {len(ws)} cửa sổ đúng lưới (app kiểu cũ: cửa sổ đúng tỉ lệ game trong ô), cùng hiện",
   code == 200 and len(ws) >= 2 and [x["b"] for x in ws] == cells and all(x["vis"] for x in ws), (code, j, [(x["id"], x["b"], x["vis"]) for x in ws], cells))
if NEW:
    t1_, t2_ = task(1), task(2); s1_, s2_ = last_size(1), last_size(2)
    ck(f"… ô đổi cỡ → app kiểu cũ được mở lại ngay trong ô mới ({j.get('re')} app), dựng hình đúng cỡ ô: app 1 thấy {s1_} · ô {t1_ and t1_['b']} — app 2 thấy {s2_} · ô {t2_ and t2_['b']}; app 3 (đổi cỡ thật) không bị mở lại",
       (j.get("re") or 0) >= 2 and creates(1) == c1 + 1 and creates(2) == c2 + 1 and creates(3) == 1 and t1_ and t2_ and fitted(s1_, t1_["b"], g5t)
       and fitted(s2_, t2_["b"], g5t), (j, creates(1), c1, creates(2), c2, creates(3), s1_, t1_ and t1_["b"], s2_, t2_ and t2_["b"]))
    c1, c2 = creates(1), creates(2)
    code, j = run("tile")
    ck("… bấm Sắp xếp lần nữa (ô không đổi cỡ) → không app nào bị mở lại", code == 200 and not j.get("re") and creates(1) == c1 and creates(2) == c2, (j, creates(1), c1, creates(2), c2))

# 6. xoay ngang rồi sắp xếp
sh("settings put system user_rotation 1"); time.sleep(4)
code, j = run("tile"); gl = cp.win_state(sh)["geo"]; ws = sorted([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")], key=lambda t: t["id"])
shot("9-sap-xep-ngang")
ck("khoá xoay ngang + Sắp xếp tab: cửa sổ đúng lưới của màn lúc đó, trong màn", code == 200 and [x["b"] for x in ws] == want(gl, ws)
   and all(x["b"][2] <= gl["w"] and x["b"][3] <= gl["h"] for x in ws), (code, j, gl, [x["b"] for x in ws], want(gl, ws)))
info("màn chính của máy này xoay ngang được (máy ảo Pixel: màn chính chỉ dọc)", gl["w"] > gl["h"], gl)
sh("settings put system user_rotation 0"); time.sleep(4)
run("tile")

# 7. phóng to cửa sổ trên cùng → toàn màn; thu nhỏ lại
top = next((x for x in tasks() if x["mode"] == "freeform" and x["vis"] and x["type"] in ("standard", "")), None)
code, j = run("full"); tf = next((x for x in tasks() if top and x["id"] == top["id"]), None); shot("10-phong-to")
ga = cp.win_state(sh)["geo"]
ck("Phóng to tab → cửa sổ trên cùng về toàn màn (hoặc to hết màn nếu Android không cho)", code == 200 and tf and tf["vis"]
   and (tf["mode"] == "fullscreen" or tf["b"] == cp.win_area(ga)), (code, j, tf, cp.win_area(ga)))
info("Phóng to = toàn màn thật", tf and tf["mode"] == "fullscreen", tf and tf["mode"])
if NEW and top and tf and tf["mode"] == "fullscreen" and cp.win_kinds(sh).get(top["id"], {}).get("old"):
    ck("… app kiểu cũ phóng to → được mở lại để vẽ đủ toàn màn (báo rõ), vẫn đúng tab đó; còn tab nhỏ khác nên KHÔNG trả mật độ",
       "mở lại để vẽ đủ toàn màn" in j.get("msg", "") and tf["id"] == top["id"] and (cp.win_screen(sh) or {}).get("sw", 0) >= 600, (j, tf, cp.win_screen(sh)))
code, j = run("mini"); tf = next((x for x in tasks() if top and x["id"] == top["id"]), None); shot("11-thu-nho-lai")
g2 = cp.win_state(sh)["geo"]
ck("Thu nhỏ lại tab vừa phóng to → cửa sổ nhỏ, trong màn", code == 200 and tf and tf["mode"] == "freeform" and area(tf["b"]) < 0.85 * area(cp.win_area(g2))
   and tf["b"][2] <= g2["w"] + 1 and tf["b"][3] <= g2["h"] + 1, (code, j, tf, g2))
code, j = run("list")
ck("danh sách tab nhỏ đúng số", code == 200 and j.get("n") == len([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")]), (code, j))
sh("input keyevent 3"); time.sleep(2)
code, j = run("mini")
ck("ở màn chính bấm Thu nhỏ tab → báo 'Các tab đang là cửa sổ nhỏ rồi'", code == 409 and "cửa sổ nhỏ rồi" in j.get("error", ""), (code, j))
# 8. 23/11b · GAME "CŨ" (dựng khung 1 lần theo cỡ lúc mở — app 4) thu nhỏ → 🔄 Mở lại vừa khung → game vẽ đúng cỡ cửa sổ
def game_size():
    m = [re.search(r"n=4 size=(\d+)x(\d+) frame=(\d+)x(\d+)", l) for l in sh("logcat -d -s wintest:I", 40).splitlines()]
    m = [x for x in m if x]
    return tuple(int(v) for v in m[-1].groups()) if m else None


sh("input keyevent 3"); time.sleep(2); sh("logcat -c")
open_app(4); code, j = run("mini"); time.sleep(3); g4 = task(4); s1 = game_size(); shot("12-game-cu-thu-nho")
ck("game cũ (app 4) thu nhỏ được", code == 200 and g4 and g4["mode"] == "freeform", (code, j, g4))
scm = [l.strip()[:200] for l in sh("dumpsys activity activities", 60).splitlines() if "mSizeCompatScale" in l or "inSizeCompatMode=true" in l]
if NEW:
    g8 = cp.win_state(sh)["geo"]
    capr = int(round(cp.WIN_CAP_DP * g8["dpi"] / 160.0))
    ck(f"… game cũ TỰ được mở lại ngay trong cửa sổ lúc thu nhỏ → dựng khung theo cỡ CỬA SỔ (bề ngang đúng, bề cao lệch tối đa bằng thanh tiêu đề {capr} px): app thấy {s1 and s1[:2]} · khung game {s1 and s1[2:]} · cửa sổ {g4 and g4['b']}",
       j.get("fit") == "ok" and bool(s1) and abs(s1[0] - s1[2]) <= 4 and -4 <= s1[3] - s1[1] <= capr + 8 and g4 and fitted(s1[:2], g4["b"], g8) and creates(4) == 2,
       (j, s1, g4 and g4["b"], creates(4), scm[:1]))
    info(f"… khung game KHÍT phần app thấy (lần dựng hình đầu đã trừ thanh tiêu đề): app thấy {s1 and s1[:2]} · khung game {s1 and s1[2:]}", bool(s1) and abs(s1[1] - s1[3]) <= 4, s1)
else:
    info(f"game cũ vừa thu nhỏ: app thấy {s1 and s1[:2]} · khung game {s1 and s1[2:]}" + (f" · Android thu nhỏ hình: {scm[:1]}" if scm else ""),
         bool(s1) and (s1[0] >= s1[2] - 2 and s1[1] >= s1[3] - 2), s1)
if g4:
    gb = g4["b"]; t0 = time.time(); ga0 = cp.win_state(sh)["geo"]; c4 = creates(4)
    if NEW:                                                         # khách tự kéo / bấm cho cửa sổ to hơn → hình hết vừa → bấm Vừa khung
        code, j = run("grow"); time.sleep(2); g4b = task(4); sg = game_size()
        ck(f"Cửa sổ to hơn với game cũ: chỉ đổi cỡ, KHÔNG mở lại (bấm nhiều lần không bị tải lại), báo web hiện nút Vừa khung: app thấy {sg and sg[:2]} · khung game {sg and sg[2:]}",
           code == 200 and j.get("fit") == "ask" and creates(4) == c4 and g4b and tuple(g4b["b"]) == tuple(j.get("b") or ()), (code, j, creates(4), c4, g4b))
        gb = g4b["b"] if g4b else gb
    code, j = run("refit"); time.sleep(4); g5 = task(4); s2 = game_size(); shot("13-mo-lai-vua-khung")
    if not NEW:
        ck("Android 9: Mở lại vừa khung → báo chưa hỗ trợ (màn xoay theo game), game KHÔNG bị tắt / mở lại", code == 409 and "Android 9" in j.get("error", "")
           and g5 and g5["mode"] == "freeform" and g5["id"] == g4["id"], (code, j, g5))
    else:
        ck(f"🖼 Vừa khung → game mở lại ngay trong ĐÚNG TAB + đúng chỗ + cỡ cửa sổ đang có (không đổi cỡ cửa sổ), đúng 1 lần · {time.time() - t0:.1f} giây",
           code == 200 and g5 and g5["mode"] == "freeform" and tuple(g5["b"]) == tuple(gb) == tuple(j.get("b") or ()) and g5["vis"] and g5["id"] == g4["id"]
           and creates(4) == c4 + 1, (code, j, gb, g5, creates(4), c4))
        gs = cp.win_state(sh)["geo"]
        ck("… màn vẫn đúng hướng như trước khi mở lại (game ngang không làm màn kẹt ngang)", (gs["w"] > gs["h"]) == (ga0["w"] > ga0["h"]), (ga0, gs))
        capr = int(round(cp.WIN_CAP_DP * gs["dpi"] / 160.0))
        ck(f"… game dựng khung theo cỡ CỬA SỔ mới (bề ngang đúng, bề cao lệch tối đa bằng thanh tiêu đề {capr} px): app thấy {s2 and s2[:2]} · khung game {s2 and s2[2:]} · cửa sổ {g5 and g5['b']}",
           bool(s2) and abs(s2[0] - s2[2]) <= 4 and -4 <= s2[3] - s2[1] <= capr + 8 and g5 and fitted(s2[:2], g5["b"], gs), (s2, g5 and g5["b"], gs))
        info(f"… khung game KHÍT phần app thấy sau Vừa khung: app thấy {s2 and s2[:2]} · khung game {s2 and s2[2:]}", bool(s2) and abs(s2[1] - s2[3]) <= 4, s2)
# 9. 23/11c · khách tự cho cửa sổ TO / NHỎ hơn · 🖥 Màn ngang rộng (600 dp + khoá ngang) · Màn dọc như cũ
def ffs(): return [x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")]
def inside(g, ws): return all(x["b"][0] >= 0 and x["b"][1] >= 0 and x["b"][2] <= g["w"] + 1 and x["b"][3] <= g["h"] + 1 for x in ws)
top = next((x for x in ffs() if x["vis"]), None)
if top:
    g9 = cp.win_state(sh)["geo"]; b0 = top["b"]
    code, j = run("grow"); t1 = next((x for x in tasks() if x["id"] == top["id"]), None); shot("14-cua-so-to-hon")
    ck("Cửa sổ to hơn → cửa sổ trên cùng to ra (đúng cỡ máy chủ báo), vẫn trong màn", code == 200 and t1 and tuple(t1["b"]) == tuple(j.get("b") or ())
       and area(t1["b"]) > area(b0) and inside(g9, [t1]) and t1["vis"], (code, j, b0, t1))
    code, j = run("shrink"); t2 = next((x for x in tasks() if x["id"] == top["id"]), None); shot("15-cua-so-nho-hon")
    ck("Cửa sổ nhỏ hơn → cửa sổ đó nhỏ lại (đúng cỡ máy chủ báo)", code == 200 and t1 and t2 and tuple(t2["b"]) == tuple(j.get("b") or ())
       and area(t2["b"]) < area(t1["b"]), (code, j, t1 and t1["b"], t2))
n9 = len(ffs()); d0 = dens(); scr = cp.win_screen(sh) or {"w": 720, "h": 1280}; dw = min(scr["w"], scr["h"]) * 160 // 600
if not NEW: ck("Android 9: thu nhỏ KHÔNG tự đổi mật độ (màn vẫn như lúc đầu)", d0 == [D0] and prevv() in ("null", ""), (d0, prevv()))
def rotv(): return sh("settings get system user_rotation").strip()
print("   màn trước khi bật Màn ngang rộng:", scr, "mật độ", d0, "→ cần", dw, flush=True)
code, j = run("wide"); time.sleep(3); gw = cp.win_state(sh)["geo"]; ws = ffs(); shot("16-man-ngang-rong")
p9 = {"mã": code, "sw": j.get("sw"), "mật độ": dens(), "cần": dw, "khoá": rotv(), "tab": (len(ws), n9), "trong màn": inside(gw, ws), "nhớ": prevv(), "xoay": j.get("turned")}
short9 = min(scr["w"], scr["h"])
ck(f"🖥 Màn ngang rộng → độ rộng nhỏ nhất ≥ 600 dp + khoá ngang (giữ được khoá), nhớ mật độ LÚC ĐẦU ({D0}, bỏ dấu tự bật), {n9} tab vẫn đủ và nằm trong màn",
   code == 200 and (j.get("sw") or 0) >= 600 and p9["mật độ"] == [dw] and p9["khoá"] == "1" and len(ws) == n9 and p9["trong màn"]
   and p9["nhớ"] == f"{D0}:{short9}", (p9, (gw["w"], gw["h"]), [x["b"] for x in ws], j.get("msg")))
ck("… màn chính NẰM NGANG thật (khoá xoay của Android, hoặc cửa sổ phủ của app trợ giúp nếu màn chính không chịu xoay)", gw["w"] > gw["h"] and bool(j.get("turned")),
   (p9, (gw["w"], gw["h"]), sh(f"dumpsys package {cp.ROT_PKG} | grep -m1 versionCode"), sh("logcat -d -s cbxoay:V | tail -n 5")))
ck("… các tab xếp đúng lưới của màn ngang (app kiểu cũ: cửa sổ đúng tỉ lệ game trong ô)", [x["b"] for x in sorted(ws, key=lambda t: t["id"])] == want(gw, sorted(ws, key=lambda t: t["id"])),
   ([x["b"] for x in sorted(ws, key=lambda t: t["id"])], want(gw, sorted(ws, key=lambda t: t["id"]))))
code, j = run("narrow"); time.sleep(3); gn = cp.win_state(sh)["geo"]; ws = ffs(); shot("17-man-doc-nhu-cu")
p9 = {"mã": code, "sw": j.get("sw"), "mật độ": dens(), "cần": d0, "khoá": rotv(), "tab": (len(ws), n9), "trong màn": inside(gn, ws), "nhớ": prevv(), "màn": (gn["w"], gn["h"])}
ck(f"Màn dọc như cũ → trả ĐÚNG mật độ lúc đầu ({D0}) + khoá dọc + tắt cửa sổ phủ, màn dọc, xoá dấu nhớ, {n9} tab nằm trong màn",
   code == 200 and p9["mật độ"] == [D0] and p9["khoá"] == "0" and gn["h"] > gn["w"] and len(ws) == n9 and p9["trong màn"]
   and p9["nhớ"] in ("null", ""), (p9, [x["b"] for x in ws], j.get("msg")))

# 10. 23/11d · XOAY MÀN bằng cửa sổ phủ của app trợ giúp (máy bỏ qua khoá xoay như MuMu: màn chỉ xoay khi có cửa sổ yêu cầu hướng)
def land_now(): g = cp.win_state(sh)["geo"]; return g["w"] > g["h"]
def wait_land(want_, limit=10):
    end = time.time() + limit
    while time.time() < end:
        if land_now() == want_: return True
        time.sleep(0.5)
    return land_now() == want_
sh("input keyevent 3"); time.sleep(2)
sh("settings put system accelerometer_rotation 0; settings put system user_rotation 0; wm user-rotation lock 0", 20); time.sleep(3)
ck("(chuẩn bị) khoá xoay DỌC, màn đang dọc", wait_land(False), cp.win_state(sh)["geo"])
ok1 = cp.rot_helper(tsh, inst, True); t1 = wait_land(True); shot("18-xoay-ngang-bang-cua-so-phu")
ck("app trợ giúp bật cửa sổ phủ yêu cầu màn ngang → MÀN CHÍNH XOAY NGANG dù khoá xoay của Android đang để DỌC", ok1 and t1 and rotv() == "0",
   (ok1, t1, rotv(), sh("dumpsys window displays | grep -E 'mCurrentRotation|mLastOrientation' | head -n 4"), sh("logcat -d -s cbxoay:V | tail -n 6"),
    sh(f"appops get {cp.ROT_PKG} SYSTEM_ALERT_WINDOW"), "\n".join(TRACE[-6:])))
cp.rot_helper(tsh, None, False); t2 = wait_land(False)
ck("tắt app trợ giúp → màn chính về DỌC", t2, (cp.win_state(sh)["geo"], sh("dumpsys window displays | grep -E 'mCurrentRotation' | head -n 2")))
TRACE.clear(); stR, goodR = cp.win_rot(tsh, 1, time.sleep, inst); t3 = land_now()
print("\n".join(TRACE[:30]), flush=True)
ck("win_rot(ngang) — như nút Xoay / Màn ngang rộng → màn chính NGANG", goodR and t3, (goodR, t3, stR and stR["geo"]))
stR, goodR = cp.win_rot(tsh, 0, time.sleep, inst); t4 = wait_land(False)
nwin = (sh("dumpsys window windows 2>/dev/null | grep -c cbxoay").strip().splitlines() or ["?"])[-1]
ck("win_rot(dọc) → màn chính DỌC, cửa sổ phủ đã tắt (không còn cửa sổ của app trợ giúp)", t4 and nwin == "0", (goodR, t4, nwin, cp.win_state(sh)["geo"]))
sh(f"wm density {D0}; settings put system user_rotation 0; settings delete global {cp.WIN_PREV_KEY}; am force-stop {cp.ROT_PKG}", 20); time.sleep(2)   # trả máy như cũ cho test_fit.py chạy sau
print("--- am stack list (cuối) ---\n" + sh("am stack list")[:2500], flush=True)
print(f"API {API}: %d/%d dat · thông tin: %s" % (OK[0], OK[1], ", ".join(("✓ " if c else "✗ ") + n for n, c in INFO)), flush=True)
open(os.path.join(OUT, f"win-{API}-ketqua.txt"), "w", encoding="utf-8").write(f"{OK[0]}/{OK[1]}\n" + "".join("XX " + f + "\n" for f in FAILS)
                                                                         + "\n".join(("OK " if c else "NO ") + n for n, c in INFO))
sys.exit(0 if OK[0] == OK[1] else 1)
