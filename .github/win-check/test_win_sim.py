# -*- coding: utf-8 -*-
"""23/11 · 🗗 TAB CỬA SỔ NHỎ — thử phía MÁY CHỦ (cpapi.win_run + /cpapi/<máy>/win) bằng máy Android GIẢ (chạy được ở mọi máy, không cần Android):
   đọc `am stack list` kiểu Android 9 (Stack id=…, tab trong khối in từ dưới lên) và Android 12+ (RootTask id=…), cỡ màn / thanh điều hướng,
   lưới xếp tab (dọc / ngang), chỗ cho cửa sổ mới không đè cửa sổ khách đã kéo, thu nhỏ → về màn chính → mở app khác → thu nhỏ (cửa sổ cũ
   hiện lại đúng chỗ), bản clone (người dùng 10), sắp xếp, phóng to, báo lỗi dễ hiểu, cổng HTTP (đăng nhập, 400, khoá 1 việc / máy).
   Android 9/10/11 có "tật": app đang trên cùng thì `am start --windowingMode` KHÔNG đổi chế độ → máy giả bắt chước, cpapi phải về màn chính trước.
   Android 10/11: mở lại thường KHÔNG đổi chế độ tab đang chạy (chỉ đưa lên) — chỉ đường --task (số tab, như màn Gần đây) đổi được.
   Android 9–11: màn xoay (app ép ngang toàn màn) → Android xoay luôn chỗ các cửa sổ nổi; về màn chính thì xoay ngược lại.
   Chạy: python3 .github/win-check/test_win_sim.py"""
import importlib.util, json, os, re, sys, tempfile, threading, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:900], flush=True)


home = tempfile.mkdtemp(prefix="cpapi_win_")
open(os.path.join(home, "cloudphone.conf"), "w").write("SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone.test\n")
os.environ["HOME"] = home
spec = importlib.util.spec_from_file_location("cpapi_w", os.path.join(ROOT, "cpapi.py"))
cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
FS, FF = "fullscreen", "freeform"


class Droid:
    """Máy Android giả: danh sách tab theo thứ tự trên → dưới, mỗi tab {id, comp, user, mode, type, b, land, resz}. sdk 28: mô hình KHỐI của
       Android 9 (mọi cửa sổ nổi chung 1 khối, mọi app toàn màn chung 1 khối) + 2 tật của Android 9: "app đang trên cùng thì am start không đổi
       chế độ" và "app khai báo không đổi cỡ (game) không mở thẳng vào cửa sổ nổi" (phải am stack move-task). sdk 29/30: mở lại thường không
       đổi chế độ tab đang chạy, --task thì đổi; move-task chỉ Android ≤ 10. sdk 31: tật "am start --windowingMode 1 không đưa cửa sổ về toàn
       màn" (cả --task). App ÉP NGANG (land) đang toàn màn trên cùng → màn xoay ngang; còn lại theo màn chính. sdk < 31: màn xoay → chỗ các
       cửa sổ nổi xoay theo (giữ nguyên chỗ trên mặt kính)."""

    def __init__(self, sdk, w=720, h=1280, nav=96, free=True, lag=0):
        self.sdk, self.W, self.H, self.nav, self.free = sdk, w, h, nav, free
        self.lag, self._true, self._old, self._left = lag, None, None, 0          # lag: máy chậm — màn xoay xong mới báo hướng mới sau `lag` lần đọc
        self.z = [{"id": 1, "comp": "com.android.launcher3/.Launcher", "user": 0, "mode": FS, "type": "home", "b": (0, 0, 0, 0), "land": False, "resz": True}]
        self.nid, self.log = 10, []
        self.rot, self.lo = sdk < 31, False
        self.sticky = False                                   # máy ảo 33–35 thật: game ngang mở lại TOÀN MÀN bằng `am start -W` rồi thành cửa sổ
                                                              # → màn KẸT NGANG (không tự xoay về dọc) tới khi về màn chính / mở app khác
        self.force, self.nonres, self.apps = ("1" if free else "null"), "null", {}

    def _sync(self):
        """Màn vừa đổi hướng → Android 9–11 xoay chỗ các cửa sổ nổi theo (DisplayContent.rotateBounds); Android 10/11 còn đẩy cửa sổ
           nằm dưới thanh trạng thái (48 px) xuống → xoay về dọc thì cửa sổ sát mép phải lệch trái (đúng như máy ảo thật: 0 → -48)."""
        o = self.size()[0] > self.size()[1]
        if o != self.lo and self.rot:
            wp = min(self.W, self.H)
            for t in self.z:
                if t["mode"] == FF and t["b"] != (0, 0, 0, 0):
                    l, tp, r, b = t["b"]
                    t["b"] = (tp, wp - r, b, wp - l) if o else (wp - b, l, wp - tp, r)
                    if o and self.sdk >= 29 and t["b"][1] < 48:
                        d = 48 - t["b"][1]; t["b"] = (t["b"][0], 48, t["b"][2], t["b"][3] + d)
        self.lo = o

    # ---- việc của khách (không qua cpapi) ----
    def open(self, comp, user=0, land=False, resz=True):
        t = next((x for x in self.z if x["comp"] == comp and x["user"] == user), None)
        self.apps[(comp, user)] = (land, resz)
        if t is None: self.nid += 1; t = {"id": self.nid, "comp": comp, "user": user, "mode": FS, "type": "standard", "b": (0, 0, 0, 0), "land": land, "resz": resz}
        else: self.z.remove(t)
        t["mode"] = FS; t["w"] = False; self.sticky = False
        self.z.insert(0, t); self._sync(); return t

    def home_key(self):
        h = next(x for x in self.z if x["type"] == "home"); self.z.remove(h); self.z.insert(0, h); self.sticky = False; self._sync()

    def rotate(self):                                       # khách khoá màn ngang (màn chính xoay được)
        self.W, self.H = self.H, self.W; self._sync()

    def task(self, comp, user=0):
        return next((x for x in self.z if x["comp"] == comp and x["user"] == user), None)

    def shown(self):
        """Cỡ màn máy BÁO khi đọc (máy chậm: vừa đổi hướng thì vài lần đọc đầu vẫn báo hướng cũ — như máy ảo Android 15)."""
        cur = self.size()
        if self._true is None: self._true = cur
        if cur != self._true: self._old, self._true, self._left = self._true, cur, self.lag
        if self._left > 0: self._left -= 1; return self._old
        return cur

    def size(self):
        """Cỡ màn lúc này: app ép ngang đang toàn màn trên cùng → ngang (máy 33–35 kẹt ngang: vẫn ngang)."""
        if self.sticky: return max(self.W, self.H), min(self.W, self.H)
        top = next((x for x in self.z if x["mode"] == FS), None)
        if top is not None and top["land"]: return max(self.W, self.H), min(self.W, self.H)
        return self.W, self.H

    # ---- hiển thị ----
    def _p_stacks(self):
        order = []
        for t in self.z:
            k = "home" if t["type"] == "home" else t["mode"]
            if k not in order: order.append(k)
        return order

    def visible(self, t):
        if self.sdk < 31:
            for k in self._p_stacks():
                kk = "home" if t["type"] == "home" else t["mode"]
                if k == kk: return True
                if k in ("home", FS): return False
            return False
        for x in self.z:
            if x is t: return True
            if x["mode"] == FS: return False
        return False

    def stack_list(self):
        W, H = self.size(); D = f"[0,0][{W},{H}]"
        cfg = lambda mode, typ: (f" configuration={{1.0 ?mcc?mnc [en_US] ldltr sw360dp w360dp h616dp 320dpi nrml long port finger -keyb/v/h -nav/h "
                                 f"winConfig={{ mBounds=Rect(0, 0 - {W}, {H}) mAppBounds=Rect(0, 0 - {W}, {H}) "
                                 f"mWindowingMode={mode} mDisplayWindowingMode=fullscreen mActivityType={typ} mAlwaysOnTop=undefined mRotation=ROTATION_0}} s.6}}")
        bnd = lambda t: (f"[{t['b'][0]},{t['b'][1]}][{t['b'][2]},{t['b'][3]}]" if t["mode"] == FF else D)
        line = lambda t: (f"  taskId={t['id']}: {t['comp']} bounds={bnd(t)} userId={t['user']} visible={'true' if self.visible(t) else 'false'} "
                          f"topActivity=ComponentInfo{{{t['comp'].replace('/.', '/' + t['comp'].split('/')[0] + '.')}}}")
        out = []
        if self.sdk < 31:
            ids = {"home": 0, FS: 1, FF: 2}
            for k in self._p_stacks():
                ts = [t for t in self.z if ("home" if t["type"] == "home" else t["mode"]) == k]
                out.append(f"Stack id={ids[k]} bounds={D} displayId=0 userId=0")
                if self.sdk >= 28: out.append(cfg(FS if k == "home" else k, "home" if k == "home" else "standard"))
                out += [line(t) for t in reversed(ts)]                      # Android 9 in tab dưới trước
        else:
            for t in self.z:
                out.append(f"RootTask id={t['id']} bounds={bnd(t) if t['mode'] == FF else D} displayId=0 userId={t['user']}")
                out.append(cfg(t["mode"], t["type"])); out.append(line(t))
        return "\n".join(out)

    # ---- lệnh adb shell ----
    def sh(self, c, t=30):
        o = self._sh(c, t); self._sync(); return o

    def _sh(self, c, t=30):
        self.log.append(c)
        if c == cp.WIN_STATE_SH:
            W, H = self.shown(); land = W > H
            return (f"{self.sdk}\n#S\n{self.stack_list()}\n#D\n  Display: mDisplayId=0 rootTasks=4\n"
                    f"    init=720x1280 320dpi cur={W}x{H} app={W - self.nav if land else W}x{H if land else H - self.nav} rng=720x672-1232x1184\n"
                    f"  Display: mDisplayId=2 rootTasks=1\n    init=360x640 160dpi cur=360x640 app=360x640\n#W\nPhysical density: 320\n#F\n{1 if self.free else 0}"
                    f"\n#R\n{self.force}\n{self.nonres}")
        if c.startswith("am stack list"): return self.stack_list()
        if c.startswith("settings put global enable_freeform_support 1"):
            self.free = True
            m = re.search(r"force_resizable_activities (\d)", c); self.force = m.group(1) if m else self.force
            m = re.search(r"enable_non_resizable_multi_window (\d)", c); self.nonres = m.group(1) if m else self.nonres
            return ""
        m = re.match(r"am task focus (\d+) 2>&1$", c)
        if m:                                                   # 23/11b: chỉ đưa tab lên trên cùng (không đổi chế độ, không gửi lệnh mở)
            tk = next((x for x in self.z if x["id"] == int(m.group(1))), None)
            if tk is None: return f"Error: task {m.group(1)} not found"
            self.z.remove(tk); self.z.insert(0, tk); return f"Setting focus to task {tk['id']}"
        m = re.match(r"am force-stop --user (\d+) ([\w.]+) 2>&1$", c)
        if m:
            self.z = [x for x in self.z if not (x["comp"].split("/")[0] == m.group(2) and x["user"] == int(m.group(1)))]; return ""
        if c.startswith("dumpsys gfxinfo "): return "Total frames rendered: 7"
        m = re.match(r"C=(\S+); U=(\d+); am start --user \$U (--display 0 )?--windowingMode 5 .* -n \$C .*?(am stack move-task \$id (\d+) true .*?)?"
                     r"r=\$\(am task resize \$id (-?\d+) (-?\d+) (-?\d+) (-?\d+) 2>&1\)", c)
        if m:                                                   # 🔄 mở lại vừa khung: vòng lặp trên máy (mở lại → thấy tab → đặt cỡ ngay)
            comp, u = m.group(1).strip("'"), int(m.group(2))
            if bool(m.group(3)) != (self.sdk >= 29): return "Error: lệnh sai bản Android"
            land, resz = self.apps.get((comp, u), (False, True))
            tk = self.open(comp, u, land, resz)
            if self.free and (self.sdk >= 29 or resz): tk["mode"] = FF
            elif m.group(4) and self.sdk < 30 and any(x["mode"] == FF and x is not tk for x in self.z) and int(m.group(5)) == 2: tk["mode"] = FF
            if tk["mode"] != FF: return ""
            tk["b"] = tuple(int(m.group(i)) for i in range(6, 10)); return f"REFIT {tk['id']} 0"
        if c.startswith("input keyevent 3"): self.home_key(); return ""
        if c.startswith("am force-stop com.android.settings"):
            self.z = [x for x in self.z if not x["comp"].startswith("com.android.settings/")]; return ""
        m = re.match(r"am start (?:--windowingMode 5|--stack 2) -n com\.android\.settings/\.Settings 2>&1$", c)
        if m:
            tk = self.task("com.android.settings/.Settings") or self.open("com.android.settings/.Settings")
            if self.free: tk["mode"], tk["b"] = FF, (90, 300, 630, 700)           # chưa bật cửa sổ nổi → Cài đặt mở toàn màn
            self.z.remove(tk); self.z.insert(0, tk); return "Starting: Intent { cmp=com.android.settings/.Settings }"
        m = re.match(r"(?:timeout \d+ )?am start (?:-W )?--user (\d+) (?:--display 0 )?(?:--task (\d+) )?(?:--windowingMode (\d) |--stack (\d) )-a android\.intent\.action\.MAIN "
                     r"-c android\.intent\.category\.LAUNCHER -f 0x10200000 -n (\S+) 2>&1$", c)
        if m:
            u, tid, comp = int(m.group(1)), m.group(2), m.group(5).strip("'")
            mode = FF if (m.group(3) or m.group(4)) in ("5", "2") else FS
            tk = self.task(comp, u)
            if tk is None and (comp, u) in self.apps and tid is None:      # app đã tắt (force-stop) → mở lại = tab mới toàn màn
                tk = self.open(comp, u, *self.apps[(comp, u)])
                if mode == FS: tk["w"] = "-W " in c; return "Status: ok"
            if tk is None: return "Error: Activity class does not exist."
            if tid is not None and int(tid) != tk["id"]: return "Error: task khác app"
            if ("--display 0 " in c) != (self.sdk >= 29): return "Error: lệnh sai bản Android"
            if self.sdk < 31 and self.z[0] is tk: return "Warning: Activity not started, its current task has been brought to the front"
            if tid is not None:                                   # chỉ thẳng số tab (đường của màn Gần đây)
                ok = self.sdk < 31 or self.sdk >= 35 or mode == FF
            else:
                ok = not (29 <= self.sdk < 31 and tk["mode"] != mode) \
                    and not (mode == FF and self.sdk < 29 and not tk["resz"] and tk["mode"] != FF) \
                    and not (mode == FS and self.sdk < 29 and tk["mode"] == FF) \
                    and not (mode == FS and self.sdk == 31 and tk["mode"] == FF)
            ok = ok and (self.free or mode == FS)
            if ok:
                if tk["mode"] != mode and mode == FF and tk["b"] == (0, 0, 0, 0): tk["b"] = (90, 300, 630, 700)    # cỡ mặc định của Android
                if self.sdk >= 33 and mode == FF and tk["mode"] == FS and tk.get("w") and tk["land"] and self.z[0] is tk: self.sticky = True
                tk["mode"] = mode
            self.z.remove(tk); self.z.insert(0, tk)
            return "Starting: Intent { act=android.intent.action.MAIN cat=[android.intent.category.LAUNCHER] }"
        m = re.match(r"am stack move-task (\d+) (\d+) true 2>&1$", c)
        if m:
            tk = next((x for x in self.z if x["id"] == int(m.group(1))), None)
            if self.sdk >= 30 or tk is None: return "Error"
            if int(m.group(2)) != 2 or not any(x["mode"] == FF for x in self.z): return "java.lang.IllegalStateException: moveTaskToStack: No stack for stackId=" + m.group(2)
            tk["mode"] = FF; tk["b"] = (90, 300, 630, 700); self.z.remove(tk); self.z.insert(0, tk); return ""
        m = re.match(r"am task resize (\d+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) 2>&1$", c)
        if m:
            tk = next((x for x in self.z if x["id"] == int(m.group(1))), None)
            if tk is None or tk["mode"] != FF: return "java.lang.IllegalArgumentException: resizeTask not allowed on task"
            tk["b"] = tuple(int(m.group(i)) for i in range(2, 6)); return ""
        return "UNKNOWN " + c


def ovl(a, b): return cp._ovl(a, b)


# ============================================================== 1. đọc + lưới
print("1. Lưới xếp tab · chỗ cho cửa sổ mới")
gp = cp.win_geo("  Display: mDisplayId=0 rootTasks=3\n    init=720x1280 320dpi cur=720x1280 app=720x1184 rng=x", "Physical density: 320", [])
ck("màn dọc 720x1280: thanh trạng thái 48 px, thanh điều hướng dưới 96 px, thanh tiêu đề 64 px",
   (gp["w"], gp["h"], gp["top"], gp["bottom"], gp["right"], gp["cap"]) == (720, 1280, 48, 96, 0, 64), gp)
gl = cp.win_geo("  Display: mDisplayId=0 rootTasks=3\n    init=720x1280 320dpi cur=1280x720 app=1184x720 rng=x", "Physical density: 320\nOverride density: 240", [])
ck("màn ngang 1280x720: thanh điều hướng bên phải 96 px · mật độ ghi đè 240", (gl["w"], gl["h"], gl["bottom"], gl["right"], gl["top"]) == (1280, 720, 0, 96, 36), gl)
shape = lambda g, n: (len({c[0] for c in cp.win_grid(g, n)}), len({c[1] for c in cp.win_grid(g, n)}))
ck("màn dọc: 2 tab → 1 cột × 2 hàng, 4 tab → 1 × 4, 8 tab → 2 × 4", (shape(gp, 2), shape(gp, 4), shape(gp, 8)) == ((1, 2), (1, 4), (2, 4)),
   (shape(gp, 2), shape(gp, 4), shape(gp, 8)))
ck("màn ngang: 2 tab → 2 × 1, 4 tab → 2 × 2, 6 tab → 3 × 2", (shape(gl, 2), shape(gl, 4), shape(gl, 6)) == ((2, 1), (2, 2), (3, 2)),
   (shape(gl, 2), shape(gl, 4), shape(gl, 6)))
gb = cp.win_geo("  Display: mDisplayId=0 rootTasks=3\n    init=720x1280 160dpi cur=1280x720 app=1232x720 rng=x", "Physical density: 160", [])
ck("cửa sổ không nhỏ hơn 220 dp (Android chặn): 440 px ở 320 dpi, 220 px ở 160 dpi", (gp["min"], gb["min"]) == (440, 220), (gp, gb))
for g, nm in ((gp, "dọc 320 dpi"), (gl, "ngang 240 dpi"), (gb, "ngang 160 dpi")):
    cells = cp.win_grid(g, 7)
    inside = all(c[0] >= 0 and c[1] >= g["top"] and c[2] <= g["w"] - g["right"] and c[3] <= g["h"] - g["bottom"] for c in cells)
    big = all(c[2] - c[0] >= min(g["min"], g["w"] - g["right"]) and c[3] - c[1] >= min(g["min"], g["h"] - g["top"] - g["bottom"]) for c in cells)
    xs, ys = sorted({c[0] for c in cells}), sorted({c[1] for c in cells})
    peek = all(b - a >= g["cap"] for a, b in zip(ys, ys[1:])) and all(b - a >= g["cap"] for a, b in zip(xs, xs[1:]))
    ck(f"màn {nm}: 7 cửa sổ trong vùng dùng được, không nhỏ hơn mức tối thiểu, đè nhau thì vẫn lộ thanh tiêu đề", inside and big and peek and len(cells) == 7, cells)
c4 = cp.win_grid(gb, 4)
ck("màn ngang 160 dpi: 4 tab 2 × 2 KHÔNG đè nhau · màn dọc 320 dpi: 4 tab phải xếp chồng", not cp.win_overlap(c4) and cp.win_overlap(cp.win_grid(gp, 4)), c4)
s0 = cp.win_slot(gp, [])
ck("cửa sổ đầu tiên: góc trên, rộng hết màn, cao 220 dp (440 px), dưới thanh trạng thái", s0 == (0, 48, 720, 488), s0)
dragged = [(0, 24, 616, 372), (300, 380, 900, 700)]
s2 = cp.win_slot(gb, dragged)
ck("màn rộng, đã có 2 cửa sổ (1 cái khách kéo ra giữa) → chọn ô trống không đè", all(ovl(s2, d) == 0 for d in dragged), s2)
s3 = cp.win_slot(gp, [(0, 48, 720, 488), (100, 600, 600, 900)])
ck("màn chật: chọn chỗ ÍT đè nhất, không ra ngoài màn", s3[3] <= gp["h"] - gp["bottom"] and s3[1] >= gp["top"]
   and sum(ovl(s3, d) for d in [(0, 48, 720, 488), (100, 600, 600, 900)]) <= min(sum(ovl(c, d) for d in [(0, 48, 720, 488), (100, 600, 600, 900)]) for c in cp.win_grid(gp, 4)), s3)

print("2. Đọc `am stack list` (Android 9 kiểu khối · Android 12 kiểu RootTask)")
for sdk in (28, 31):
    d = Droid(sdk); a = d.open("com.roblox.client/.startup.ActivitySplash"); b = d.open("com.android.settings/.Settings")
    tl = cp.win_tasks(d.stack_list(), sdk)
    ck(f"Android {sdk}: thứ tự trên → dưới, tab trên cùng = Cài đặt (hiện), màn chính có loại home"
       + (" (Android 9: 'visible' tính theo cả khối)" if sdk < 31 else ", Roblox bị che"),
       [t["id"] for t in tl] == [b["id"], a["id"], 1] and tl[0]["vis"] and tl[1]["vis"] == (sdk < 31) and tl[2]["type"] == "home" and tl[0]["mode"] == FS,
       [(t["id"], t["mode"], t["type"], t["vis"]) for t in tl])
old = "Stack id=1 bounds=[0,0][720,1280] displayId=0 userId=0\n  taskId=5: com.x/.A bounds=[0,0][720,1280] userId=0 visible=true\nStack id=2 bounds=[0,0][720,1280] displayId=0 userId=0\n  taskId=6: com.y/.B bounds=[10,20][300,400] userId=0 visible=true"
to = cp.win_tasks(old, 25)
ck("Android 7: chế độ theo số khối (1 = toàn màn, 2 = cửa sổ nổi)", [(t["id"], t["mode"]) for t in to] == [(5, FS), (6, FF)] and to[1]["b"] == (10, 20, 300, 400), to)
ck("lệnh mở lại tab: Android 12 có --display 0 + --windowingMode 5, Android 7 dùng --stack 2",
   "--display 0 --windowingMode 5 " in "".join(cp.win_launch(lambda c, t=0: c, {"user": 10, "comp": "com.a/.B"}, 5, 31))
   and "--stack 2 " in cp.win_launch(lambda c, t=0: c, {"user": 0, "comp": "com.a/.B"}, 5, 25) and "--display" not in cp.win_launch(lambda c, t=0: c, {"user": 0, "comp": "com.a/.B"}, 5, 25))

# ============================================================== 3. luồng của khách
cp.time.sleep = lambda s: None                       # máy giả: không chờ thật
GP = cp.win_geo("Display: mDisplayId=0\n cur=720x1280 app=720x1184", "Physical density: 320", [])
for sdk in (28, 29, 30, 31, 35):
    print(f"3. Android {sdk}: thu nhỏ → về màn chính → mở app khác → thu nhỏ → clone → sắp xếp → phóng to")
    d = Droid(sdk); R1, R2, SET = "com.roblox.client/.startup.ActivitySplash", "vn.game.hai/.Main", "com.android.settings/.Settings"
    code, j = cp.win_run(d.sh, "mini")
    ck("chưa mở app nào → 409 'Chưa có app nào đang mở toàn màn'", code == 409 and "Chưa có app nào" in j.get("error", ""), (code, j))
    d.open(R1, land=True, resz=sdk >= 29)                  # Roblox ép ngang (Android 9: khai báo không đổi cỡ → phải chuyển khối)
    ck("Roblox toàn màn → màn máy đang NGANG", d.size() == (1280, 720), d.size())
    code, j = cp.win_run(d.sh, "mini"); a = d.task(R1)
    ck("thu nhỏ Roblox → cửa sổ nổi ở chỗ đầu tiên tính theo màn DỌC (màn quay về dọc khi app thành cửa sổ), không ra ngoài màn",
       code == 200 and a["mode"] == FF and a["b"] == tuple(j["b"]) == cp.win_slot(GP, []) == (0, 48, 720, 488)
       and j["msg"].startswith("Đã thu nhỏ Roblox (1 tab nhỏ). Kéo thanh") and j["n"] == 1, (code, j, a))
    if sdk < 29: ck("Android 9 + game không đổi cỡ: chuyển nguyên tab sang khối cửa sổ nổi (mở tạm Cài đặt rồi đóng)",
                    any(x.startswith("am stack move-task") for x in d.log) and any("force-stop com.android.settings" in x for x in d.log)
                    and d.task(SET) is None, d.log[-12:])
    elif sdk < 31: ck(f"Android {sdk}: về màn chính rồi mở lại ĐÚNG SỐ TAB (--task {a['id']}), không chuyển khối",
                      "input keyevent 3" in d.log and any(f"--task {a['id']} --windowingMode 5 " in x for x in d.log)
                      and not any(x.startswith("am stack move-task") for x in d.log), d.log[-8:])
    else: ck(f"Android {sdk}: KHÔNG bấm về màn chính (đổi thẳng)", "input keyevent 3" not in d.log and not any("--task" in x for x in d.log), d.log[-6:])
    ab = a["b"]
    d.home_key(); d.open(R2, land=True, resz=sdk >= 29)    # game ngang thứ 2: màn xoay ngang (Android 9–11 xoay luôn chỗ cửa sổ Roblox)
    if sdk < 31: ck("máy giả: màn ngang → chỗ cửa sổ Roblox bị Android xoay theo", a["b"] != ab and d.size() == (1280, 720), (a["b"], ab))
    code, j = cp.win_run(d.sh, "mini"); b = d.task(R2)
    ck("về màn chính rồi mở game ngang thứ 2 → thu nhỏ: 2 cửa sổ, Roblox vẫn ĐÚNG CHỖ CŨ và hiện lại, cửa sổ mới vào chỗ trống", code == 200 and b["mode"] == FF
       and a["b"] == ab and d.visible(a) and d.visible(b) and ovl(a["b"], b["b"]) == 0 and b["b"][2] <= 720 and j["n"] == 2, (code, j, a, b, d.stack_list()))
    a["b"] = DR = (200, 700, 700, 1000)                   # khách tự kéo Roblox xuống dưới (sát mép phải 20 px)
    d.open(R1, 10, land=True, resz=sdk >= 29)              # bản clone (người dùng 10) — toàn màn ngang
    code, j = cp.win_run(d.sh, "mini"); c = d.task(R1, 10)
    ck("bản clone (người dùng 10) thu nhỏ được, mở bằng --user 10, cửa sổ khách đã kéo giữ nguyên, chỗ mới trong màn dọc",
       code == 200 and c["mode"] == FF and "(bản clone)" in j["msg"] and any("--user 10 " in x for x in d.log)
       and c["b"] not in (a["b"], b["b"]) and c["b"][2] <= 720 and c["b"][3] <= 1184
       and (a["b"] == DR or (29 <= sdk < 31 and a["b"] == (DR[0] - 28, DR[1], DR[2] - 28, DR[3]))), (code, j, c, a, b))
    if 29 <= sdk < 31: ck("Android 10/11: cửa sổ khách kéo sát mép phải chỉ lệch trái ≤ 48 px (Android đẩy dưới thanh trạng thái khi màn ngang)",
                          a["b"] == (DR[0] - 28, DR[1], DR[2] - 28, DR[3]), a["b"])
    code, j = cp.win_run(d.sh, "mini")
    ck("thu nhỏ khi không còn app toàn màn → 409 'Các tab đang là cửa sổ nhỏ rồi'", code == 409 and "cửa sổ nhỏ rồi" in j.get("error", ""), (code, j))
    d.open("vn.game.khac/.Main", land=True)                # khách mở 1 game ngang khác toàn màn rồi bấm Sắp xếp
    code, j = cp.win_run(d.sh, "tile")
    cells = cp.win_grid(GP, 3); ws = sorted([a, b, c], key=lambda t: t["id"])
    ck("sắp xếp khi app ngang đang toàn màn: về màn chính, xếp 3 tab theo màn DỌC (1 cột × 3 hàng), hiện hết, báo xếp chồng + Độ rộng nhỏ nhất",
       code == 200 and [t["b"] for t in ws] == cells and all(d.visible(t) and t["mode"] == FF for t in ws) and "1 cột × 3 hàng" in j["msg"]
       and "chồng nhau" in j["msg"] and "Độ rộng nhỏ nhất" in j["msg"], (code, j, [t["b"] for t in ws], cells))
    d.rotate()
    code, j = cp.win_run(d.sh, "tile")
    ck("khoá màn ngang rồi sắp xếp: lưới ngang, trong màn", code == 200 and "2 cột" in j["msg"] and all(t["b"][2] <= 1280 and t["b"][3] <= 720 for t in ws), (code, j))
    d.rotate(); cp.win_run(d.sh, "tile")
    top = next(t for t in d.z if t["mode"] == FF)
    code, j = cp.win_run(d.sh, "full")
    if sdk == 31:
        ck("Android 12 (lệnh không về toàn màn được) → phóng cửa sổ to hết màn + chỉ nút ▭", code == 200 and top["mode"] == FF and top["b"] == (0, 48, 720, 1184)
           and "hết màn" in j["msg"] and "▭" in j["msg"], (code, j, top))
    else:
        ck("phóng to: cửa sổ trên cùng về toàn màn thật" + (" (Android 9–11: qua --task)" if sdk < 31 else ""), code == 200 and top["mode"] == FS
           and d.z[0] is top and "toàn màn" in j["msg"] and (sdk >= 31 or f"--task {top['id']} " in " ".join(d.log[-12:])), (code, j, top, d.log[-8:]))
    code, j = cp.win_run(d.sh, "list")
    ck("danh sách tab nhỏ + cỡ màn", code == 200 and j["n"] == (3 if sdk == 31 else 2) and j["screen"][0] in (720, 1280), (code, j))
    code, j = cp.win_run(d.sh, "mini")
    ck("thu nhỏ lại tab vừa phóng to → về ô nhỏ (3 tab), trong màn dọc", code == 200 and top["mode"] == FF and j["n"] == 3 and top["b"][2] <= 720
       and cp._area(top["b"]) < 0.85 * cp._area(cp.win_area(GP)), (code, j, top))
    code, j = cp.win_run(d.sh, "bay")
    ck("việc lạ → 400", code == 400, (code, j))

print("4b. Màn xoay về dọc CHẬM sau khi thu nhỏ (thấy ở máy ảo Android 15: vài giây sau vẫn ngang)")
for sdk in (31, 35):
    d = Droid(sdk, lag=3); R1, R2, R3 = "com.roblox.client/.startup.ActivitySplash", "vn.game.hai/.Main", "vn.game.ba/.Main"
    d.open(R1, land=True)
    code, j = cp.win_run(d.sh, "mini"); a = d.task(R1)
    ck(f"Android {sdk} xoay chậm: cửa sổ đầu vẫn tính theo màn DỌC (rộng hết màn, không theo màn ngang cũ)", code == 200 and a["b"] == (0, 48, 720, 488)
       and tuple(j["b"]) == a["b"], (code, j, a))
    d.home_key(); d.open(R2, land=True)
    code, j = cp.win_run(d.sh, "mini"); b = d.task(R2)
    ck(f"Android {sdk} xoay chậm: cửa sổ thứ 2 trong màn dọc, không đè cửa sổ 1", code == 200 and b["b"][0] >= 0 and b["b"][2] <= 720 and b["b"][3] <= 1184
       and ovl(a["b"], b["b"]) == 0 and a["b"] == (0, 48, 720, 488), (code, j, a, b))
    d.open(R3, land=True)
    code, j = cp.win_run(d.sh, "tile"); ws = sorted([a, b], key=lambda t: t["id"])
    ck(f"Android {sdk} xoay chậm: Sắp xếp khi game ngang đang toàn màn → lưới màn DỌC", code == 200 and [t["b"] for t in ws] == cp.win_grid(GP, 2), (code, j, ws))

print("4c. 23/11b · 🖼 Mở lại vừa khung · đưa tab lên bằng am task focus · Android 12L+ thu nhỏ hình game (size compat)")
R1, R2 = "com.roblox.client/.startup.ActivitySplash", "vn.game.hai/.Main"
for sdk in (28, 29, 31, 32, 33, 35):
    d = Droid(sdk); d.open(R1, land=True, resz=sdk >= 29); cp.win_run(d.sh, "mini"); a = d.task(R1)
    conf = [x for x in d.log if x.startswith("settings put global enable_freeform_support 1")]
    if sdk >= cp.WIN_SCM_SDK: ck(f"Android {sdk}: KHÔNG ép đổi cỡ + cho app không đổi cỡ vào cửa sổ (Android thu nhỏ hình game vừa khung)",
                                 conf and "force_resizable_activities 0" in conf[-1] and "enable_non_resizable_multi_window 1" in conf[-1]
                                 and (d.force, d.nonres) == ("0", "1"), (conf, d.force, d.nonres))
    else: ck(f"Android {sdk}: giữ ép đổi cỡ như cũ (không đổi cài đặt máy đang chạy tốt)", not conf and d.force == "1", (conf, d.force))
    d.log.clear(); d.home_key(); d.open(R2, land=True, resz=sdk >= 29); code, j = cp.win_run(d.sh, "mini"); b = d.task(R2)
    ck(f"Android {sdk}: cửa sổ cũ đưa lên lại bằng `am task focus` (không gửi lệnh mở cho app)", code == 200 and d.visible(a) and d.visible(b)
       and any(x == f"am task focus {a['id']} 2>&1" for x in d.log) and not any(f"-n {R1}" in x and "--task" not in x for x in d.log), d.log[-10:])
    if sdk >= cp.WIN_SCM_SDK: ck(f"Android {sdk} đã đúng cài đặt → lần sau không đặt lại", not any(x.startswith("settings put") for x in d.log), d.log[:4])
    ab = a["b"] = (40, 600, 600, 920)                    # khách kéo cửa sổ Roblox; Roblox nằm dưới → bấm vào cho lên trên
    d.z.remove(a); d.z.insert(0, a); d.log.clear()
    code, j = cp.win_run(d.sh, "refit"); a2 = d.task(R1)
    if sdk < 29:
        ck("Android 9: Mở lại vừa khung → báo chưa hỗ trợ (màn xoay theo game), KHÔNG tắt game", code == 409 and "Android 9" in j.get("error", "")
           and not any("force-stop" in x for x in d.log) and a2 is a and a2["b"] == ab, (code, j, d.log))
        continue
    want = ab if sdk >= cp.WIN_SCM_SDK else (ab[0], ab[1], ab[2], ab[3] + 84)       # Android 10–12: cửa sổ cao thêm 42 dp (thanh tiêu đề)
    ck(f"Android {sdk}: 🖼 Mở lại vừa khung → tắt app, mở lại NGAY TRONG cửa sổ cũ (đúng chỗ khách kéo{', cao thêm 42 dp' if sdk < cp.WIN_SCM_SDK else ''}), báo game khởi động lại",
       code == 200 and a2 and a2["mode"] == FF and a2["b"] == want and tuple(j["b"]) == want and "khởi động lại" in j["msg"]
       and any(x == "am force-stop --user 0 com.roblox.client 2>&1" for x in d.log) and d.visible(a2), (code, j, a2, d.log[-6:]))
    bb = d.task(R2)
    ck(f"Android {sdk}: sau Mở lại vừa khung màn vẫn DỌC, cửa sổ khác (tab 2) vẫn hiện đúng chỗ"
       + (" — máy 33–35 kẹt ngang → về màn chính 1 lần rồi đưa các cửa sổ lên lại" if sdk >= 33 else " — không bấm về màn chính"),
       d.size()[0] < d.size()[1] and bb and bb["mode"] == FF and d.visible(bb) and bb["b"] == b["b"]
       and (("input keyevent 3" in d.log) == (sdk >= 33)) and d.z[0] is a2, (d.size(), bb, b["b"], [x for x in d.log if "keyevent" in x or "focus" in x]))
    scr = next((x for x in d.log if x.startswith("C=")), "")
    if sdk >= cp.WIN_SCM_SDK: ck(f"Android {sdk}: mở lại TOÀN MÀN (chờ game vẽ khung đầu) rồi đưa vào cửa sổ cũ — Android thu nhỏ cả hình vừa khung",
                                 not scr and any(x.startswith("timeout 25 am start -W --user 0 --display 0 --windowingMode 1 ") for x in d.log)
                                 and any(x.startswith(f"am task resize {a2['id']} 40 600 600 920") for x in d.log), d.log[-8:])
    else: ck(f"Android {sdk}: mở lại thẳng vào cửa sổ đúng chỗ + cỡ, chờ game vẽ khung đầu (gfxinfo) rồi kéo cao thêm 42 dp — lần vẽ đầu chưa có thanh tiêu đề",
             "am task resize $id 40 600 600 920 " in scr and any(x.startswith("dumpsys gfxinfo com.roblox.client") for x in d.log)
             and d.log[-2].startswith(f"am task resize {a2['id']} 40 600 600 1004") if len(d.log) > 1 else False, (scr[-160:], d.log[-4:]))
d = Droid(31); d.open(R1, land=True)
code, j = cp.win_run(d.sh, "refit")
ck("chưa có tab nhỏ nào → 409 dễ hiểu (thu nhỏ trước)", code == 409 and "thu nhỏ app" in j.get("error", ""), (code, j))
t_bad = {"id": 9, "comp": "com.x/.A;reboot", "pkg": "com.x", "user": 0, "b": (0, 0, 10, 10)}
ck("tên app lạ (chèn lệnh) → không chạy gì", cp.win_refit(lambda c, t=0: (_ for _ in ()).throw(AssertionError(c)), t_bad, 31, lambda s: None) is None)
d = Droid(28); d.open(R1, land=True, resz=False); cp.win_run(d.sh, "mini"); d.log.clear()
ta = next(x for x in cp.win_tasks(d.stack_list(), 28) if x["comp"] == R1)
d2 = cp.win_refit(d.sh, ta, 28, lambda s: None)
ck("(đường riêng Android 9 của win_refit, khi gọi thẳng) chỉ 1 cửa sổ → giữ khối cửa sổ nổi bằng Cài đặt, chuyển tab vào khối, đóng Cài đặt",
   d2 and d.task(R1)["mode"] == FF and any("am stack move-task $id 2 true" in x for x in d.log) and any("force-stop com.android.settings" in x for x in d.log)
   and d.task("com.android.settings/.Settings") is None, d.log[-8:])

print("4. Máy chưa bật cửa sổ nổi")
d = Droid(31, free=False); d.open("com.roblox.client/.startup.ActivitySplash")
code, j = cp.win_run(d.sh, "mini")
ck("Android 12: tự bật enable_freeform_support rồi thu nhỏ luôn", code == 200 and any(x.startswith("settings put global enable_freeform_support 1") for x in d.log), (code, j))
class Stuck(Droid):                                       # Android 9 chưa khởi động lại sau khi bật → am start không đổi chế độ
    def sh(self, c, t=30):
        if c.startswith("settings put global"): self.log.append(c); return ""
        return super().sh(c, t)
d = Stuck(28, free=False); d.open("com.roblox.client/.startup.ActivitySplash")
code, j = cp.win_run(d.sh, "mini")
ck("Android 9 chưa nhận cửa sổ nổi → 409 bảo Khởi động lại máy 1 lần (reboot=true)", code == 409 and j.get("reboot") and "Khởi động lại" in j["error"], (code, j))
code, j = cp.win_run(lambda c, t=30: "25\n#S\nError: unknown command 'stack'\n#D\n#W\n#F\n1", "mini")
ck("Android không đọc được danh sách tab → 409 dễ hiểu", code == 409 and "chưa đọc được danh sách tab" in j["error"], (code, j))

# ============================================================== 5. cổng HTTP
print("5. Cổng /cpapi/<máy>/win")
OWNER, OTHER = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
PID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TOK = {"t-owner": {"uid": OWNER, "admin": False}, "t-other": {"uid": OTHER, "admin": False}}
cp.whoami = lambda t: TOK.get(t)
cp.phone_of = lambda me, pid: {"id": PID, "name": "M1", "user_id": OWNER, "status": "active", "port": 21503, "container": "m1"} if pid == PID and me["uid"] == OWNER else None
cp.maint = lambda: {}
cp.is_locked = lambda p: False
cp.log = lambda *a: None
D = Droid(31); D.open("com.roblox.client/.startup.ActivitySplash")
SLOW = {"on": False}
class _R:
    def __init__(self, s): self.stdout, self.stderr, self.returncode = s.encode(), b"", 0
def fake_shell(port, cmd, timeout=60):
    if SLOW["on"] and cmd == cp.WIN_STATE_SH: time.sleep(1.2)
    return _R(D.sh(cmd))
cp.shell = fake_shell
srv = cp.Server(("127.0.0.1", 0), cp.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}/cpapi/"


def call(path, tok, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")


c, j = call(PID + "/win", "t-owner", {"do": "mini"})
ck("chủ máy POST thu nhỏ → 200", c == 200 and j.get("ok") and j.get("n") == 1, (c, j))
c, j = call(PID + "/win", "t-owner", method="GET")
ck("GET → danh sách 1 tab nhỏ", c == 200 and j.get("n") == 1, (c, j))
c, j = call(PID + "/win", "t-other", {"do": "tile"})
ck("máy người khác → 404", c == 404, (c, j))
c, j = call(PID + "/win", "t-nobody", {"do": "tile"})
ck("chưa đăng nhập → 401", c == 401, (c, j))
c, j = call(PID + "/win", "t-owner", {"do": "xoa"})
ck("việc lạ → 400", c == 400, (c, j))
SLOW["on"] = True; res = {}
th = threading.Thread(target=lambda: res.update(a=call(PID + "/win", "t-owner", {"do": "tile"}))); th.start(); time.sleep(0.3)
cp_lock_to = None
c2, j2 = call(PID + "/win", "t-owner", {"do": "tile"}); th.join(); SLOW["on"] = False
ck("2 lần bấm cùng lúc: lần sau chờ lần trước xong (khoá 1 việc / máy) rồi vẫn chạy", res["a"][0] == 200 and c2 == 200, (res, c2, j2))

print("%d/%d dat" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
