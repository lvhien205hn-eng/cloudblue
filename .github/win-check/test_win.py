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
OK, INFO = [0, 0], []


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True)


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


def run(do):
    TRACE.clear(); t0 = time.time(); code, j = cp.win_run(tsh, do)
    print(f"   win_run({do}) → {code} {j} · {time.time() - t0:.1f} giây", flush=True)
    print("\n".join(TRACE[:40]), flush=True); time.sleep(2)
    return code, j


def area(b): return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


st0 = cp.win_state(sh); g0 = st0["geo"]
print("geo:", g0, "sdk:", st0["sdk"], "free:", st0["free"], flush=True)
ck("đọc được danh sách tab + cỡ màn (dọc)", st0["ok"] and st0["sdk"] == API and g0["h"] > g0["w"] > 0, st0)

# 1. thu nhỏ app 1
open_app(1); shot("1-app1-toan-man")
a = task(1)
ck("app 1 mở toàn màn, đang hiện", a and a["mode"] == "fullscreen" and a["vis"], a)
code, j = run("mini"); a = task(1); shot("2-thu-nho-app1")
ck("Thu nhỏ tab → app 1 thành cửa sổ nổi đúng ô đã tính", code == 200 and a and a["mode"] == "freeform" and a["vis"] and tuple(j.get("b") or ()) == a["b"], (code, j, a))
b1 = a["b"] if a else None

# 2. về màn chính → mở app 2 → thu nhỏ
sh("input keyevent 3"); time.sleep(2); shot("3-ve-man-chinh")
open_app(2)
code, j = run("mini"); a, b = task(1), task(2); shot("4-thu-nho-app2")
ck("về màn chính rồi mở app 2 → thu nhỏ: 2 cửa sổ cùng hiện, cửa sổ app 1 giữ đúng chỗ, cửa sổ mới vào chỗ trống",
   code == 200 and a and b and a["mode"] == b["mode"] == "freeform" and a["vis"] and b["vis"] and a["b"] == b1 and cp._ovl(a["b"], b["b"]) == 0
   and b["b"] == tuple(j.get("b") or ()), (code, j, a, b))

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
    if "720x1280" not in sh("wm size"): sh("wm size 720x1280; wm density 320", 20); time.sleep(3); print("   (đặt lại cỡ màn sau khi Android khởi động lại giao diện)", flush=True)


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

# 5. sắp xếp (dọc) — sau khi về màn chính (màn chính che hết cửa sổ)
sh("input keyevent 3"); time.sleep(2)
code, j = run("tile"); ws = sorted([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")], key=lambda t: t["id"])
cells = cp.win_grid(cp.win_state(sh)["geo"], len(ws)); shot("8-sap-xep-doc")
ck(f"Sắp xếp tab (màn dọc): {len(ws)} cửa sổ đúng lưới, cùng hiện, không đè nhau",
   code == 200 and len(ws) >= 2 and [x["b"] for x in ws] == cells and all(x["vis"] for x in ws), (code, j, [(x["id"], x["b"], x["vis"]) for x in ws], cells))

# 6. xoay ngang rồi sắp xếp
sh("settings put system user_rotation 1"); time.sleep(4)
code, j = run("tile"); gl = cp.win_state(sh)["geo"]; ws = sorted([x for x in tasks() if x["mode"] == "freeform" and x["type"] in ("standard", "")], key=lambda t: t["id"])
shot("9-sap-xep-ngang")
ck("khoá xoay ngang + Sắp xếp tab: cửa sổ đúng lưới của màn lúc đó, trong màn", code == 200 and [x["b"] for x in ws] == cp.win_grid(gl, len(ws))
   and all(x["b"][2] <= gl["w"] and x["b"][3] <= gl["h"] for x in ws), (code, j, gl, [x["b"] for x in ws]))
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
open_app(4); code, j = run("mini"); g4 = task(4); time.sleep(2); s1 = game_size(); shot("12-game-cu-thu-nho")
ck("game cũ (app 4) thu nhỏ được", code == 200 and g4 and g4["mode"] == "freeform", (code, j, g4))
scm = [l.strip()[:200] for l in sh("dumpsys activity activities", 60).splitlines() if "mSizeCompatScale" in l or "inSizeCompatMode=true" in l]
info(f"game cũ vừa thu nhỏ: app thấy {s1 and s1[:2]} · khung game {s1 and s1[2:]}" + (f" · Android thu nhỏ hình: {scm[:1]}" if scm else ""),
     bool(s1) and (s1[0] >= s1[2] - 2 and s1[1] >= s1[3] - 2), s1)
if g4:
    gb = g4["b"]; sh("logcat -c"); t0 = time.time()
    code, j = run("refit"); time.sleep(4); g5 = task(4); s2 = game_size(); shot("13-mo-lai-vua-khung")
    if API < cp.WIN_REFIT_SDK:
        ck("Android 9: Mở lại vừa khung → báo chưa hỗ trợ (màn xoay theo game), game KHÔNG bị tắt / mở lại", code == 409 and "Android 9" in j.get("error", "")
           and g5 and g5["mode"] == "freeform" and g5["id"] == g4["id"], (code, j, g5))
    else:
        ck(f"🖼 Mở lại vừa khung → game mở lại ngay trong cửa sổ cũ (đúng chỗ + cỡ) · {time.time() - t0:.1f} giây", code == 200 and g5 and g5["mode"] == "freeform"
           and g5["b"] == gb and g5["vis"], (code, j, gb, g5))
        fit = bool(s2) and abs(s2[0] - s2[2]) <= 24 and abs(s2[1] - s2[3]) <= 24          # khung game = phần app thấy (Android 12L+ còn thu nhỏ cả hình)
        ck(f"… game dựng khung theo cỡ CỬA SỔ (vừa khung): app thấy {s2 and s2[:2]} · khung game {s2 and s2[2:]}", fit, s2)
print("--- am stack list (cuối) ---\n" + sh("am stack list")[:2500], flush=True)
print(f"API {API}: %d/%d dat · thông tin: %s" % (OK[0], OK[1], ", ".join(("✓ " if c else "✗ ") + n for n, c in INFO)), flush=True)
open(os.path.join(OUT, f"win-{API}-ketqua.txt"), "w", encoding="utf-8").write(f"{OK[0]}/{OK[1]}\n" + "\n".join(("OK " if c else "NO ") + n for n, c in INFO))
sys.exit(0 if OK[0] == OK[1] else 1)
