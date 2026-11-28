# -*- coding: utf-8 -*-
"""28/11f — THỬ cbwp.apk (app trợ giúp đặt ảnh nền CloudBlue, vn.cloudblue.wp) trên máy ảo Android THẬT trong CI.
     python3 .github/wp-check/test_wp.py <api>      (chạy trong android-emulator-runner, có sẵn adb · cbwp.apk ở thư mục gốc repo)
   Chạy bằng adb shell THƯỜNG (không root) — giống máy MuMu Android 15 (KernelSU giấu su với adb shell), đúng các lệnh phonectl dùng:
     1. cài app · chép ảnh vào /sdcard/Android/data/vn.cloudblue.wp/files/wp.png · am start-foreground-service · đọc res.txt → "OK <id>"
     2. màn hình chính hiện ảnh ngay (chụp màn: phần lớn là màu ảnh) · giao diện (SystemUI) KHÔNG khởi động lại
     3. gỡ app → ảnh nền VẪN GIỮ · 4. ảnh mới với if_id = id lần trước → thay · if_id sai (khách đã tự đổi ảnh nền) → "SKIP", không thay
     5. thiếu ảnh → "ERR" · 6. (root, thông tin) wallpaper_orig = đúng ảnh vừa đặt
   Kết quả: in ra + $GITHUB_STEP_SUMMARY + cbwp-<api>.json · đạt hết → cbwp-ok-<api>.txt (bước lưu apk chỉ chạy khi mọi bản Android đạt)."""
import hashlib, json, os, re, struct, subprocess, sys, time, zlib

API = sys.argv[1] if len(sys.argv) > 1 else "?"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
APK = os.path.join(ROOT, "cbwp.apk")
PKG, SVC = "vn.cloudblue.wp", "vn.cloudblue.wp/.Svc"
EXT = f"/sdcard/Android/data/{PKG}/files"
RES = {"api": API, "checks": []}
OK = True


def say(s=""):
    print(s, flush=True)


def ck(name, cond, extra=""):
    global OK
    RES["checks"].append({"name": name, "ok": bool(cond), "extra": str(extra)[:400]})
    say(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f" → {str(extra)[:400]}"))
    if not cond: OK = False


def adb(*a, t=60, binary=False):
    try:
        r = subprocess.run(["adb", *a], capture_output=True, timeout=t)
        return r.returncode, (r.stdout if binary else (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace"))
    except Exception as e:
        return -1, b"" if binary else repr(e)


def sh(cmd, t=60): return adb("shell", cmd, t=t)[1]


def png(w, h, rgb):
    """PNG 1 màu (không cần thư viện)."""
    row = b"\x00" + bytes(rgb) * w
    raw = zlib.compress(row * h, 9)
    def chunk(k, d): return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def shot_ratio(rgb, tol=40):
    """Tỷ lệ điểm ảnh màn hình (chụp thô RGBA) gần màu rgb."""
    rc, d = adb("exec-out", "screencap", t=60, binary=True)
    if rc != 0 or len(d) < 16: return -1.0
    w, h, f = struct.unpack("<III", d[:12])
    hdr = len(d) - w * h * 4
    if hdr not in (12, 16) or w <= 0 or h <= 0: return -1.0
    px = d[hdr:]; n = hit = 0
    for y in range(0, h, 9):
        base = y * w * 4
        for x in range(0, w, 9):
            i = base + x * 4; r, g, b = px[i], px[i + 1], px[i + 2]; n += 1
            if abs(r - rgb[0]) <= tol and abs(g - rgb[1]) <= tol and abs(b - rgb[2]) <= tol: hit += 1
    return hit / max(1, n)


def booted():
    for _ in range(90):
        if sh("getprop sys.boot_completed", t=20).strip().endswith("1"): return True
        time.sleep(2)
    return False


def home():
    sh("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard 2>/dev/null; input keyevent KEYCODE_HOME", t=30); time.sleep(5)


def install():
    rc, o = adb("install", "-r", "--user", "0", APK, t=180)
    return "Success" in o, o.strip()[-200:]


def set_wp(local, if_id=None):
    """Đúng các bước phonectl: thư mục app → chép ảnh → gọi dịch vụ → chờ res.txt. Trả dòng kết quả."""
    sh(f"mkdir -p {EXT}; rm -f {EXT}/res.txt {EXT}/wp.png", t=30)
    adb("push", local, f"{EXT}/wp.png", t=120)
    extra = f" --ei if_id {int(if_id)}" if if_id is not None else ""
    o = sh(f"am start-foreground-service --user 0 -n {SVC}{extra} 2>&1", t=30)
    for _ in range(40):
        r = sh(f"cat {EXT}/res.txt 2>/dev/null", t=15).strip()
        if r: return r
        time.sleep(0.5)
    return "KHÔNG CÓ res.txt · am: " + o.strip()[-200:]


say(f"=== cbwp.apk · Android API {API}")
ck("có cbwp.apk (dựng ở job build)", os.path.isfile(APK), APK)
adb("unroot", t=60); time.sleep(4); adb("wait-for-device", t=120)
ck("máy ảo đã khởi động xong", booted())
uid = sh("id -u", t=20).strip()
ck("adb shell THƯỜNG (uid 2000, không root) — giống MuMu Android 15", uid.endswith("2000"), uid)
m = re.search(r"(\d+)x(\d+)", sh("wm size", t=20)); W, H = (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)
mag, cyan = (255, 0, 255), (0, 200, 255)
for nm, col in (("a.png", mag), ("b.png", cyan)):
    with open("/tmp/" + nm, "wb") as f: f.write(png(W, H, col))
home()
say(f"  (trước: màn chính {shot_ratio(mag):.0%} màu tím · cỡ màn {W}x{H})")

ok_i, io = install()
ck("cài app trợ giúp (adb install --user 0)", ok_i, io)
pid0 = sh("pidof com.android.systemui", t=20).strip()
t0 = time.time(); r1 = set_wp("/tmp/a.png"); RES["set_s"] = round(time.time() - t0, 1); RES["r1"] = r1
ck("đặt ảnh 1 (tím) → OK <id>", r1.startswith("OK "), r1)
id1 = int(r1.split()[1]) if r1.startswith("OK ") and r1.split()[1].isdigit() else None
home(); ra = shot_ratio(mag); RES["ratio_a"] = round(ra, 3)
ck(f"màn hình chính hiện ảnh tím ngay ({ra:.0%})", ra >= 0.25, f"{ra:.0%}")
pid1 = sh("pidof com.android.systemui", t=20).strip()
ck("giao diện (SystemUI) không khởi động lại", pid0 and pid0 == pid1, f"{pid0} → {pid1}")
sh(f"pm uninstall {PKG}", t=60); time.sleep(3); home(); ru = shot_ratio(mag)
ck(f"gỡ app → ảnh nền VẪN GIỮ ({ru:.0%}) · app không còn trong máy", ru >= 0.25 and PKG not in sh("pm list packages", t=30), f"{ru:.0%}")

install(); r2 = set_wp("/tmp/b.png", if_id=id1 if id1 is not None else 0); RES["r2"] = r2
id2 = int(r2.split()[1]) if r2.startswith("OK ") and r2.split()[1].isdigit() else None
home(); rb = shot_ratio(cyan)
ck(f"ảnh mới với if_id = id lần trước → thay ({rb:.0%} xanh)", r2.startswith("OK ") and rb >= 0.25, f"{r2} · {rb:.0%}")
r3 = set_wp("/tmp/a.png", if_id=(id2 or 0) + 1000); RES["r3"] = r3
home(); rc_ = shot_ratio(cyan)
ck(f"if_id sai (khách đã tự đổi ảnh nền) → SKIP, giữ nguyên ({rc_:.0%} xanh)", r3.startswith("SKIP") and rc_ >= 0.25, f"{r3} · {rc_:.0%}")
sh(f"mkdir -p {EXT}; rm -f {EXT}/res.txt {EXT}/wp.png", t=30)
sh(f"am start-foreground-service --user 0 -n {SVC} 2>&1", t=30); r4 = ""
for _ in range(30):
    r4 = sh(f"cat {EXT}/res.txt 2>/dev/null", t=15).strip()
    if r4: break
    time.sleep(0.5)
ck("thiếu ảnh → ERR, không đổi gì", r4.startswith("ERR"), r4)
sh(f"pm uninstall {PKG}", t=60)
ck("cuối lượt: app đã gỡ", PKG not in sh("pm list packages", t=30))
RES["logcat"] = sh("logcat -d -s cbwp:V | tail -n 8", t=30)[-800:]

adb("root", t=60); time.sleep(4); adb("wait-for-device", t=120); booted()
mo = re.match(r"([0-9a-f]{32})", sh("md5sum /data/system/users/0/wallpaper_orig 2>/dev/null", t=30).strip())
want = hashlib.md5(open("/tmp/b.png", "rb").read()).hexdigest()
RES["orig_same"] = bool(mo and mo.group(1) == want)
say(f"  (root, thông tin) wallpaper_orig = ảnh vừa đặt: {RES['orig_same']}")
RES["dumpsys"] = sh("dumpsys wallpaper | head -30", t=30)[:1500]
adb("unroot", t=60)

summ = os.environ.get("GITHUB_STEP_SUMMARY")
if summ:
    with open(summ, "a", encoding="utf-8") as f:
        f.write(f"\n### cbwp.apk · Android API {API} — {'ĐẠT' if OK else 'CHƯA ĐẠT'}\n\n")
        for c in RES["checks"]: f.write(f"- {'✅' if c['ok'] else '❌'} {c['name']}" + ("" if c["ok"] else f" — `{c['extra']}`") + "\n")
        f.write(f"- đặt ảnh mất {RES.get('set_s')} giây · `{RES.get('r1', '')}` · `{RES.get('r2', '')}` · `{RES.get('r3', '')}`\n"
                f"- wallpaper_orig = ảnh vừa đặt (root): {RES.get('orig_same')}\n")
with open(os.path.join(ROOT, f"cbwp-{API}.json"), "w", encoding="utf-8") as f: json.dump(RES, f, ensure_ascii=False, indent=1)
if OK:
    with open(os.path.join(ROOT, f"cbwp-ok-{API}.txt"), "w") as f: f.write("ok\n")
say(f"=== {'ĐẠT' if OK else 'CHƯA ĐẠT'} · API {API}")
sys.exit(0 if OK else 1)
