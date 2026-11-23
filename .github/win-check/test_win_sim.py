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

    def __init__(self, sdk, w=720, h=1280, nav=96, free=True, lag=0, stick=False):
        self.sdk, self.W, self.H, self.nav, self.free = sdk, w, h, nav, free
        self.lag, self._true, self._old, self._left = lag, None, None, 0          # lag: máy chậm — màn xoay xong mới báo hướng mới sau `lag` lần đọc
        self.z = [{"id": 1, "comp": "com.android.launcher3/.Launcher", "user": 0, "mode": FS, "type": "home", "b": (0, 0, 0, 0), "land": False, "resz": True}]
        self.nid, self.log = 10, []
        self.rot, self.lo = sdk < 31, False
        self.sticky, self.stick, self.pend = False, stick, 0      # máy ảo 33–35 thật: game ngang vừa mở lại TOÀN MÀN (`am start -W`, mở nguội) — màn
        # còn đang xoay ngang (pend lần đọc nữa mới xong) mà đã thu game vào cửa sổ → màn xoay ngang MUỘN rồi KẸT NGANG tới khi về màn chính
        # / mở app khác. stick=True: máy kẹt ngang cả khi đã chờ xoay xong (để thử đường về màn chính).
        self.force, self.nonres, self.apps = ("1" if free else "null"), "null", {}
        self.pd, self.od, self.urot, self.home_rot = 320, None, 0, True   # 23/11c: mật độ (Physical / Override) · khoá xoay · màn chính xoay được khi ≥ 600 dp
        self.prev = None                                          # cài đặt global cb_win_prev_density (mật độ trước khi bật Màn ngang rộng)
        self.psize = None                                         # (rộng, cao) vật lý khi máy đã đổi độ phân giải (wm size) — như máy ảo CI 320x640 → 640x1280
        # tật của Android 15 THẬT (máy ảo Pixel, lượt chạy 23/11): đổi mật độ → vài nhịp sau giao diện hệ thống dựng lại thanh điều hướng và TỰ
        # đặt khoá xoay về hướng màn ĐANG hiện; màn chính cũng tới lúc đó mới dựng lại theo mật độ mới (thành kiểu máy tính bảng, xoay được).
        # quirk=True: bật tật · navlag: số lệnh sau khi đổi mật độ · navwhen: (thay navlag) dựng lại đúng lúc gặp lệnh có chữ này
        self.quirk, self.navlag, self.navwhen, self._nav, self._hsw = False, 3, None, 0, None
        # 23/11d (đo trên MuMu thật): app KIỂU CŨ chỉ vẽ vừa khi được MỞ LẠI đúng cỡ cửa sổ đang có → mỗi tab nhớ "made" = (rộng, cao, mật độ) lúc
        # app dựng hình; tiến trình (pid) tắt bằng `am kill` chỉ khi app đang ở nền. autorot=False: máy bỏ qua khoá xoay như MuMu
        # (mSupportAutoRotation=false) — màn chỉ xoay khi có cửa sổ yêu cầu hướng (app ép ngang toàn màn / cửa sổ phủ của app trợ giúp).
        self.autorot, self.helper, self.ovl, self.noinst, self.npid = True, 0, False, False, 4000

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
    def open(self, comp, user=0, land=False, resz=True, legacy=False, fgsvc=False, dens_ok=False):
        """legacy: app targetSdk < 24 (Android ghi FORCE_RESIZABLE_*) · fgsvc: app giữ dịch vụ chạy nổi → `am kill` không tắt được ·
           dens_ok: app tự xử lý đổi mật độ (Android không mở lại màn của nó)."""
        t = next((x for x in self.z if x["comp"] == comp and x["user"] == user), None)
        self.apps[(comp, user)] = (land, resz)
        if t is None:
            self.nid += 1; t = {"id": self.nid, "comp": comp, "user": user, "mode": FS, "type": "standard", "b": (0, 0, 0, 0), "land": land, "resz": resz,
                                "legacy": legacy, "fgsvc": fgsvc, "dens_ok": dens_ok, "pid": None, "made": None, "starts": 0}
        else: self.z.remove(t)
        t["mode"] = FS; t["cold"] = False; self.sticky = False; self.pend = 0
        self.z.insert(0, t); self._sync()
        if t["pid"] is None: self._born(t)
        return t

    def _box(self, t):
        """Cỡ vùng app được vẽ lúc này: cửa sổ nổi → cỡ cửa sổ, toàn màn → cỡ màn."""
        if t["mode"] == FF: return (t["b"][2] - t["b"][0], t["b"][3] - t["b"][1])
        return self.size()

    def _born(self, t):
        """App (màn của tab) vừa được dựng lại: tiến trình mới + dựng hình theo cỡ / mật độ lúc này."""
        self.npid += 1; t["pid"] = self.npid; t["made"] = self._box(t) + ((self.od or self.pd),); t["starts"] = t.get("starts", 0) + 1

    def oldkind(self, t):
        return (not t.get("resz", True)) or bool(t.get("legacy"))

    def fits(self, t):
        """Hình app có VỪA vùng đang có không: app kiểu cũ chỉ vừa khi được dựng đúng cỡ + mật độ đang có; app đổi cỡ thật luôn vừa."""
        if not self.oldkind(t): return True
        return t.get("pid") is not None and t.get("made") == self._box(t) + ((self.od or self.pd),)

    def install_helper(self):
        if self.noinst: return False
        self.helper = cp.ROT_VER; return True

    def home_key(self):
        h = next(x for x in self.z if x["type"] == "home"); self.z.remove(h); self.z.insert(0, h); self.sticky = False; self.pend = 0; self._sync()

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
        if self.sticky or self.ovl: return max(self.W, self.H), min(self.W, self.H)      # ovl: cửa sổ phủ của app trợ giúp yêu cầu màn ngang
        if self.pend > 0: return self.W, self.H                   # game ngang vừa mở nguội: màn chưa xoay xong
        top = next((x for x in self.z if x["mode"] == FS), None)
        if top is not None and top["land"]: return max(self.W, self.H), min(self.W, self.H)
        hsw = self.sw() if self._hsw is None else self._hsw       # màn chính còn chưa dựng lại → vẫn theo mật độ cũ
        if self.autorot and self.urot == 1 and (top is None or top["type"] != "home" or (self.home_rot and hsw >= 600)):   # khoá ngang: màn chính chỉ xoay
            return max(self.W, self.H), min(self.W, self.H)                                                       # khi máy như máy tính bảng
        return self.W, self.H

    def sw(self):
        return min(self.W, self.H) * 160 // (self.od or self.pd)

    def _dens(self, v):
        if self.quirk: self._hsw = self.sw(); self._nav = self.navlag if not self.navwhen else -1
        ch = (v or self.pd) != (self.od or self.pd)
        self.od = v
        if ch:
            for t in self.z:                                      # Android mở lại màn của app (không tự xử lý đổi mật độ) theo cỡ ĐANG CÓ lúc này
                if t["type"] == "standard" and t.get("pid") is not None and not t.get("dens_ok"): self._born(t)

    def _navbar(self):
        """Giao diện hệ thống dựng lại xong: đang khoá xoay → đặt khoá về hướng màn đang hiện; màn chính dựng lại theo mật độ mới."""
        W, H = self.size(); self.urot = 1 if W > H else 0; self._hsw = None; self._nav = 0

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
        if self._nav > 0:
            self._nav -= 1
            if self._nav == 0: self._navbar()
        elif self._nav < 0 and self.navwhen and self.navwhen in c: self._navbar()
        if c == cp.WIN_STATE_SH:
            if self.pend > 0: self.pend -= 1
            W, H = self.shown(); land = W > H
            return (f"{self.sdk}\n#S\n{self.stack_list()}\n#D\n  Display: mDisplayId=0 rootTasks=4\n"
                    f"    init=720x1280 320dpi cur={W}x{H} app={W - self.nav if land else W}x{H if land else H - self.nav} rng=720x672-1232x1184\n"
                    f"  Display: mDisplayId=2 rootTasks=1\n    init=360x640 160dpi cur=360x640 app=360x640\n#W\nPhysical density: {self.pd}"
                    + (f"\nOverride density: {self.od}" if self.od else "") + f"\n#F\n{1 if self.free else 0}"
                    f"\n#R\n{self.force}\n{self.nonres}")
        if c.startswith("am stack list"): return self.stack_list()
        if c == cp.WIN_SCREEN_SH:
            sz = (f"Physical size: {self.psize[0]}x{self.psize[1]}\nOverride size: {min(self.W, self.H)}x{max(self.W, self.H)}" if self.psize
                  else f"Physical size: {min(self.W, self.H)}x{max(self.W, self.H)}")
            return sz + f"\nPhysical density: {self.pd}" + (f"\nOverride density: {self.od}" if self.od else "")
        if c == cp.WIN_ROT_SH: return str(self.urot)          # 23/11c: 🖥 màn ngang rộng / màn dọc như cũ
        if c.startswith(f"settings get global {cp.WIN_PREV_KEY}"): return self.prev or "null"
        if "settings put system user_rotation" in c or "wm density" in c or cp.WIN_PREV_KEY in c:
            m = re.search(rf"settings put global {cp.WIN_PREV_KEY} (\S+?)(?:;|$)", c)
            if m: self.prev = m.group(1)
            if f"settings delete global {cp.WIN_PREV_KEY}" in c: self.prev = None
            m = re.search(r"wm density (\d+)", c)
            if m: self._dens(int(m.group(1)))
            if "wm density reset" in c: self._dens(None)
            m = re.search(r"settings put system user_rotation (\d)", c)
            if m: self.urot = int(m.group(1))
            return ""
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
            tk["b"] = tuple(int(m.group(i)) for i in range(6, 10)); self._born(tk); return f"REFIT {tk['id']} 0"
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
                if mode == FS:
                    tk["cold"] = "-W " in c
                    if tk["cold"] and tk["land"] and self.sdk >= 33: self.pend = 2
                    return "Status: ok"
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
                if self.sdk >= 33 and mode == FF and tk["mode"] == FS and tk["land"] and (self.pend > 0 or (self.stick and tk.get("cold"))):
                    self.sticky = True; self.pend = 0
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
        # ---- 23/11d: loại app (dumpsys activity) · tiến trình (ps) · am kill · mở lại sạch vào đúng tab · app trợ giúp xoay màn ----
        if c == cp.WIN_KIND_SH:
            o = []
            for tk in self.z:
                if tk["type"] != "standard":
                    o += [f"      * Hist  #0: ActivityRecord{{47020f2 u0 {tk['comp']} t{tk['id']}}}", "        resizeMode=RESIZE_MODE_RESIZEABLE"]; continue
                if tk.get("legacy"):                              # app nhiều màn: màn trên cùng (Hist #1) khai báo khác màn GỐC (Hist #0) → phải lấy màn gốc
                    o += [f"    * Hist  #1: ActivityRecord{{9a1b2c3 u{tk['user']} {tk['comp'].split('/')[0]}/.Game t{tk['id']}}}", "      resizeMode=RESIZE_MODE_RESIZEABLE"]
                o.append(f"    * Hist  #0: ActivityRecord{{223dfd3 u{tk['user']} {tk['comp']} t{tk['id']}}}")
                if tk["land"]: o.append("      mOrientation=SCREEN_ORIENTATION_LANDSCAPE" if self.sdk >= 31 else "      mOccludesParent=true mOrientation=0")
                o.append("      resizeMode=RESIZE_MODE_" + ("FORCE_RESIZABLE_LANDSCAPE_ONLY" if tk.get("legacy") else "RESIZEABLE" if tk["resz"] else "UNRESIZEABLE"))
            return "\n".join(o)
        m = re.match(r"ps -A -o USER,PID,NAME 2>/dev/null \| grep -F ' ([\w.]+)'$", c)
        if m:
            o = [f"u{tk['user']}_a{130 + tk['id']}        {tk['pid']} {tk['comp'].split('/')[0]}" for tk in self.z
                 if tk["type"] == "standard" and tk.get("pid") and tk["comp"].split("/")[0].startswith(m.group(1))]
            return "\n".join(o + [f"u0_a999          77 {m.group(1)}:push", f"u0_a998          78 {m.group(1)}.khac"])     # tiến trình phụ / app khác trùng đầu tên: không tính
        if c.startswith("am kill --user "):
            for u, pkg in re.findall(r"am kill --user (\d+) ([\w.]+)", c):
                for tk in self.z:                                 # `am kill` chỉ tắt app đang ở NỀN, không giữ dịch vụ chạy nổi; tab + khung vẫn còn
                    if tk["comp"].split("/")[0] == pkg and tk["user"] == int(u) and tk.get("pid") and not self.visible(tk) and not tk.get("fgsvc"): tk["pid"] = None
            return ""
        m = re.match(r"am start --user (\d+) --display 0 --windowingMode (\d) -a android\.intent\.action\.MAIN -c android\.intent\.category\.LAUNCHER "
                     r"-f 0x10008000 -n (\S+) 2>&1$", c)
        if m:                                                   # mở lại SẠCH (CLEAR_TASK) vào đúng tab đang có: giữ số tab + chế độ + khung
            u, mode, comp = int(m.group(1)), (FF if m.group(2) == "5" else FS), m.group(3).strip("'")
            if self.sdk < 29: return "Error: lệnh sai bản Android"
            tk = self.task(comp, u)
            if tk is None:
                if (comp, u) not in self.apps: return "Error: Activity class does not exist."
                tk = self.open(comp, u, *self.apps[(comp, u)])
            if tk["mode"] != mode:
                if mode == FF and tk["b"] == (0, 0, 0, 0): tk["b"] = (90, 300, 630, 700)
                tk["mode"] = mode
            tk["dirty"] = tk.get("pid") is not None             # mở lại khi tiến trình CÒN SỐNG (không sạch — cpapi phải tắt trước)
            self.z.remove(tk); self.z.insert(0, tk); self._sync(); self._born(tk)
            return "Starting: Intent { act=android.intent.action.MAIN cat=[android.intent.category.LAUNCHER] flg=0x10008000 }"
        if c == f"pm path {cp.ROT_PKG} 2>/dev/null": return f"package:/data/app/~~x/{cp.ROT_PKG}-1/base.apk" if self.helper else ""
        if c == f"am force-stop {cp.ROT_PKG}": self.ovl = False; return ""
        if c == f"dumpsys package {cp.ROT_PKG} 2>/dev/null | grep -m1 versionCode": return f"    versionCode={self.helper} minSdk=24 targetSdk=30" if self.helper else ""
        if c.startswith(f"appops set {cp.ROT_PKG} SYSTEM_ALERT_WINDOW allow"):
            if not self.helper: return "Error: Not found; no service started."
            self.ovl = "--es o land" in c; return "Starting service: Intent { cmp=vn.cloudblue.xoay/.Svc (has extras) }"
        if c == cp.WIN_AUTOROT_SH: return f"    mSupportAutoRotation={'true' if self.autorot else 'false'}"
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
_win_run = cp.win_run                                # … kể cả các nhịp chờ win_run nhận qua tham số sleep (mặc định là time.sleep THẬT, gắn lúc nạp cpapi)
cp.win_run = lambda sh, do, sleep=(lambda s: None), inst=None: _win_run(sh, do, sleep, inst)
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
    if sdk < 29:
        code, j = cp.win_run(d.sh, "refit"); a2 = d.task(R1)
        ck("Android 9: Mở lại vừa khung → báo chưa hỗ trợ (màn xoay theo game), KHÔNG tắt game", code == 409 and "Android 9" in j.get("error", "")
           and not any("force-stop" in x or "am kill" in x for x in d.log) and a2 is a and a2["b"] == ab, (code, j, d.log))
        continue
    # 23/11d: app tắt nền được (thường gặp) → MỞ LẠI NGAY TRONG TAB (am kill + mở sạch vào đúng tab): giữ số tab + đúng chỗ + cỡ, không tắt hẳn app
    n0, id0 = a["starts"], a["id"]
    code, j = cp.win_run(d.sh, "refit"); a2 = d.task(R1); bb = d.task(R2)
    kill = next((k for k, x in enumerate(d.log) if x.startswith("am kill --user 0 com.roblox.client")), -1)
    start = next((k for k, x in enumerate(d.log) if "-f 0x10008000 -n com.roblox.client/" in x), -1)
    ck(f"Android {sdk}: 🖼 Vừa khung → về màn chính, am kill (app nền), mở lại SẠCH vào ĐÚNG TAB cũ: giữ số tab + đúng chỗ khách kéo + cỡ, game mở lại đúng 1 lần",
       code == 200 and a2 is a and a2["id"] == id0 and a2["mode"] == FF and a2["b"] == ab and tuple(j["b"]) == ab and "khởi động lại" in j["msg"]
       and 0 <= d.log.index("input keyevent 3") < kill < start and not any("force-stop" in x for x in d.log) and a2["starts"] == n0 + 1
       and not a2.get("dirty") and d.fits(a2), (code, j, a2, [x[:70] for x in d.log]))
    ck(f"Android {sdk}: sau Vừa khung màn vẫn DỌC, cửa sổ khác (tab 2) hiện lại đúng chỗ (không bị mở lại), game trên cùng",
       d.size()[0] < d.size()[1] and bb and bb["mode"] == FF and d.visible(bb) and bb["b"] == b["b"] and bb["starts"] == 1 and d.z[0] is a2
       and any(x == f"am task focus {bb['id']} 2>&1" for x in d.log), (d.size(), bb, b["b"], [x for x in d.log if "keyevent" in x or "focus" in x]))
    ck(f"Android {sdk}: màn 360 dp → nhắc bấm Màn ngang rộng nếu hình vẫn bị cắt", "Màn ngang rộng" in j["msg"], j)
    # app KHÔNG tắt nền được (giữ dịch vụ chạy nổi) → cách cũ: tắt hẳn rồi mở lại vào cửa sổ
    d = Droid(sdk); d.open(R1, land=True, fgsvc=True); cp.win_run(d.sh, "mini"); a = d.task(R1)
    d.home_key(); d.open(R2, land=True, fgsvc=True); cp.win_run(d.sh, "mini"); b = d.task(R2)
    ab = a["b"] = (40, 600, 600, 920); d.z.remove(a); d.z.insert(0, a); d.log.clear()
    code, j = cp.win_run(d.sh, "refit"); a2 = d.task(R1)
    want = ab if sdk >= cp.WIN_SCM_SDK else (ab[0], ab[1], ab[2], ab[3] + 84)       # Android 10–12: cửa sổ cao thêm 42 dp (thanh tiêu đề)
    ck(f"Android {sdk}: app không tắt nền được → cách cũ: tắt hẳn app, mở lại NGAY TRONG cửa sổ cũ (đúng chỗ khách kéo{', cao thêm 42 dp' if sdk < cp.WIN_SCM_SDK else ''}), báo game khởi động lại",
       code == 200 and a2 and a2["mode"] == FF and a2["b"] == want and tuple(j["b"]) == want and "khởi động lại" in j["msg"]
       and any(x == "am force-stop --user 0 com.roblox.client 2>&1" for x in d.log) and d.visible(a2), (code, j, a2, d.log[-6:]))
    bb = d.task(R2)
    ck(f"Android {sdk}: (cách cũ) màn vẫn DỌC, cửa sổ khác (tab 2) vẫn hiện đúng chỗ, game trên cùng"
       + (" — chờ màn xoay ngang xong mới thu vào cửa sổ (không kẹt ngang)" if sdk >= 33 else ""),
       d.size()[0] < d.size()[1] and bb and bb["mode"] == FF and d.visible(bb) and bb["b"] == b["b"] and d.z[0] is a2,
       (d.size(), bb, b["b"], [x for x in d.log if "keyevent" in x or "focus" in x]))
    scr = next((x for x in d.log if x.startswith("C=")), "")
    if sdk >= cp.WIN_SCM_SDK: ck(f"Android {sdk}: (cách cũ) mở lại TOÀN MÀN (chờ game vẽ khung đầu) rồi đưa vào cửa sổ cũ",
                                 not scr and any(x.startswith("timeout 25 am start -W --user 0 --display 0 --windowingMode 1 ") for x in d.log)
                                 and any(x.startswith(f"am task resize {a2['id']} 40 600 600 920") for x in d.log), d.log[-8:])
    else: ck(f"Android {sdk}: (cách cũ) mở lại thẳng vào cửa sổ đúng chỗ + cỡ, chờ game vẽ khung đầu (gfxinfo) rồi kéo cao thêm 42 dp — lần vẽ đầu chưa có thanh tiêu đề",
             "am task resize $id 40 600 600 920 " in scr and any(x.startswith("dumpsys gfxinfo com.roblox.client") for x in d.log)
             and any(x.startswith(f"am task resize {a2['id']} 40 600 600 1004") for x in d.log), (scr[-160:], d.log[-6:]))
d = Droid(35, stick=True); d.open(R1, land=True, fgsvc=True); cp.win_run(d.sh, "mini"); a = d.task(R1)
d.home_key(); d.open(R2, land=True, fgsvc=True); cp.win_run(d.sh, "mini"); b = d.task(R2)
d.z.remove(a); d.z.insert(0, a); d.log.clear(); ab = a["b"]
code, j = cp.win_run(d.sh, "refit"); a2 = d.task(R1); bb = d.task(R2)
ck("(cách cũ) máy kẹt ngang cả khi đã chờ xoay xong → về màn chính rồi đưa các cửa sổ lên lại: màn DỌC, game trên cùng đúng chỗ, tab 2 vẫn hiện đúng chỗ",
   code == 200 and "input keyevent 3" in d.log and d.size()[0] < d.size()[1] and a2 and a2["b"] == ab and d.z[0] is a2
   and bb and d.visible(bb) and bb["b"] == b["b"], (code, j, d.size(), a2, bb, [x for x in d.log if "keyevent" in x or "focus" in x]))
d = Droid(31)
code, j = cp.win_run(d.sh, "refit")
ck("chưa mở app nào → Vừa khung báo 409 dễ hiểu (thu nhỏ trước)", code == 409 and "thu nhỏ app" in j.get("error", ""), (code, j))
d.open(R1, land=True, resz=False); g = d.task(R1); d.W, d.H = 720, 1280; g["made"] = (576, 400, 320); n0 = g["starts"]   # game dựng hình theo cỡ cửa sổ cũ rồi khách bấm ▭ ra toàn màn
code, j = cp.win_run(d.sh, "refit")
ck("không có tab nhỏ, game đang TOÀN MÀN mà hình sai cỡ → Vừa khung mở lại game toàn màn (đúng tab, 1 lần), hình đủ màn",
   code == 200 and "toàn màn" in j["msg"] and d.task(R1) is g and g["mode"] == FS and g["starts"] == n0 + 1 and d.fits(g) and d.z[0] is g, (code, j, g))
t_bad = {"id": 9, "comp": "com.x/.A;reboot", "pkg": "com.x", "user": 0, "b": (0, 0, 10, 10)}
ck("tên app lạ (chèn lệnh) → không chạy gì", cp.win_refit(lambda c, t=0: (_ for _ in ()).throw(AssertionError(c)), t_bad, 31, lambda s: None) is None)
d = Droid(28); d.open(R1, land=True, resz=False); cp.win_run(d.sh, "mini"); d.log.clear()
ta = next(x for x in cp.win_tasks(d.stack_list(), 28) if x["comp"] == R1)
d2 = cp.win_refit(d.sh, ta, 28, lambda s: None)
ck("(đường riêng Android 9 của win_refit, khi gọi thẳng) chỉ 1 cửa sổ → giữ khối cửa sổ nổi bằng Cài đặt, chuyển tab vào khối, đóng Cài đặt",
   d2 and d.task(R1)["mode"] == FF and any("am stack move-task $id 2 true" in x for x in d.log) and any("force-stop com.android.settings" in x for x in d.log)
   and d.task("com.android.settings/.Settings") is None, d.log[-8:])

print("4d. 23/11c · khách tự cho cửa sổ to hơn / nhỏ hơn · 🖥 Màn ngang rộng (600 dp + khoá ngang → màn chính nằm ngang, nhiều tab)")
for sdk in (31, 35):
    d = Droid(sdk); d.open(R1, land=True); cp.win_run(d.sh, "mini"); a = d.task(R1)
    d.home_key(); d.open(R2, land=True); cp.win_run(d.sh, "mini"); b2 = d.task(R2)
    d.z.remove(a); d.z.insert(0, a); a["b"] = (0, 600, 640, 1040); bb0 = b2["b"]
    code, j = cp.win_run(d.sh, "grow")
    ck(f"Android {sdk}: Cửa sổ to hơn → cửa sổ trên cùng to ra 25 % mỗi chiều (ngang chạm mép màn thì dừng ở mép), cửa sổ khác không đổi",
       code == 200 and a["b"] == (0, 600, 720, 1150) and tuple(j["b"]) == a["b"] and b2["b"] == bb0 and "to hơn (720×550)" in j["msg"], (code, j, a["b"]))
    for _ in range(8):
        code, j = cp.win_run(d.sh, "grow")
        if code != 200: break
    ck(f"Android {sdk}: bấm tiếp → to tới hết vùng dùng được của màn rồi báo 'to nhất rồi', không đổi nữa", code == 409 and "to nhất" in j["error"]
       and a["b"] == (0, 48, 720, 1184), (code, j, a["b"]))
    code, j = cp.win_run(d.sh, "shrink")
    ck(f"Android {sdk}: Cửa sổ nhỏ hơn → nhỏ đi 20 % mỗi chiều", code == 200 and a["b"] == (0, 48, 576, 957) and tuple(j["b"]) == a["b"], (code, j, a["b"]))
    for _ in range(8):
        code, j = cp.win_run(d.sh, "shrink")
        if code != 200: break
    ck(f"Android {sdk}: bấm tiếp → nhỏ tới mức Android cho (220 dp = 440 px mỗi chiều) rồi báo 'nhỏ nhất' + gợi ý Màn ngang rộng", code == 409
       and "nhỏ nhất" in j["error"] and "Màn ngang rộng" in j["error"] and (a["b"][2] - a["b"][0], a["b"][3] - a["b"][1]) == (440, 440), (code, j, a["b"]))
    code, j = cp.win_run(d.sh, "wide")
    W, H = d.size(); gl = cp.win_state(d.sh)["geo"]; ws = sorted([x for x in d.z if x["mode"] == FF], key=lambda t: t["id"])
    ck(f"Android {sdk}: 🖥 Màn ngang rộng → 600 dp + khoá ngang, màn chính nằm ngang, các tab xếp lại theo lưới màn ngang",
       code == 200 and j["turned"] and j["sw"] == 600 and (W, H) == (1280, 720) and d.od == 192 and d.urot == 1
       and [x["b"] for x in ws] == cp.win_grid(gl, len(ws)) and all(x["b"][2] <= gl["w"] - gl["right"] and x["b"][3] <= gl["h"] for x in ws)
       and "NGANG RỘNG" in j["msg"] and "Đã xếp 2 tab" in j["msg"], (code, j, (W, H), d.od, [x["b"] for x in ws]))
    code, j = cp.win_run(d.sh, "shrink")
    tt = next((x for x in d.z if code == 200 and x["id"] == j["id"]), None)
    ck(f"Android {sdk}: màn rộng → cửa sổ trên cùng nhỏ được hơn trước (220 dp ở mật độ mới < 440 px)", tt and tt["b"] == tuple(j["b"])
       and (tt["b"][3] - tt["b"][1]) < 600 and (tt["b"][2] - tt["b"][0]) < 592, (code, j))
    code, j = cp.win_run(d.sh, "narrow")
    W, H = d.size(); gp2 = cp.win_state(d.sh)["geo"]; ws = sorted([x for x in d.z if x["mode"] == FF], key=lambda t: t["id"])
    ck(f"Android {sdk}: Màn dọc như cũ → trả mật độ mặc định + khoá dọc, tab xếp lại theo màn dọc",
       code == 200 and not j["wide"] and (W, H) == (720, 1280) and d.od is None and d.urot == 0 and [x["b"] for x in ws] == cp.win_grid(gp2, len(ws)), (code, j, (W, H), d.od))
d = Droid(35); d.home_rot = False; d.open(R1, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide")
ck("màn chính của máy không xoay ngang → vẫn đặt 600 dp + khoá ngang, báo rõ app / game ngang vẫn hiện ngang",
   code == 200 and not j["turned"] and d.od == 192 and "không xoay ngang" in j["msg"], (code, j))
d = Droid(35); d.od = 160
code, j = cp.win_run(d.sh, "wide")
ck("máy đã đặt rộng hơn 600 dp (720 dp) → giữ nguyên mật độ khách chọn, chỉ khoá ngang", code == 200 and d.od == 160 and j["sw"] == 720 and j["n"] == 0, (code, j, d.od))
# máy thử thật 23/11 (lượt #32): màn 640×1280 (đã đổi độ phân giải) ra 599 dp + Màn dọc như cũ trả 284 thay vì 320 · Android 15 tự trả khoá xoay
d = Droid(31, w=640, h=1280); d.psize, d.pd, d.od = (320, 640), 160, 320; d.open(R1, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide")
ck("màn 640×1280 (đã đổi độ phân giải): Màn ngang rộng làm tròn XUỐNG → 602 dp (không phải 599), nhớ mật độ cũ 320", code == 200 and d.od == 170 and j["sw"] == 602
   and d.prev == "320:640" and j["turned"], (code, j, d.od, d.prev))
code, j = cp.win_run(d.sh, "narrow")
ck("… Màn dọc như cũ → trả ĐÚNG mật độ trước đó (320, không phải 284 'mặc định theo cỡ'), xoá dấu nhớ", code == 200 and d.od == 320 and d.prev is None and j["sw"] == 320
   and d.urot == 0 and not any("wm density reset" in x for x in d.log), (code, j, d.od, d.prev))
d = Droid(35); d.od = 240; d.open(R1, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide"); code2, j2 = cp.win_run(d.sh, "wide")
ck("khách đã tự chọn 480 dp ở 📐 → Màn ngang rộng 600 dp, bấm 2 lần vẫn nhớ mật độ khách chọn (240)", code == 200 and code2 == 200 and d.od == 192 and d.prev == "240:720", (code, j, code2, d.od, d.prev))
code, j = cp.win_run(d.sh, "narrow")
ck("… Màn dọc như cũ → về lại 480 dp khách chọn (không ép về mặc định)", code == 200 and d.od == 240 and j["sw"] == 480 and d.prev is None, (code, j, d.od))
d = Droid(35); d.od = 240; d.open(R1, land=True); cp.win_run(d.sh, "mini"); d.log.clear()
code, j = cp.win_run(d.sh, "narrow")
ck("chưa bật Màn ngang rộng mà bấm Màn dọc như cũ → chỉ khoá dọc, KHÔNG đụng mật độ khách chọn", code == 200 and d.od == 240 and d.urot == 0
   and not any(re.search(r"wm density (\d+(;|$)|reset)", x) for x in d.log), (code, j, d.od, [x for x in d.log if re.search(r"wm density (\d+(;|$)|reset)", x)]))
d = Droid(35); d.open(R1, land=True); cp.win_run(d.sh, "mini"); cp.win_run(d.sh, "wide"); d.W, d.H = 1080, 1920       # khách đổi độ phân giải sau đó
code, j = cp.win_run(d.sh, "narrow")
ck("bật Màn ngang rộng rồi máy đổi độ phân giải → Màn dọc như cũ không đặt mật độ cũ (hết đúng), chỉ xoá dấu nhớ + khoá dọc", code == 200 and d.od == 192 and d.prev is None and d.urot == 0, (code, j, d.od, d.prev))
for nm, kw in (("sớm (vài nhịp sau khi đổi mật độ)", {"navlag": 3}), ("muộn (lúc đang xếp lại tab)", {"navwhen": "am task resize"})):
    d = Droid(35); d.quirk = True
    for k, v in kw.items(): setattr(d, k, v)
    d.open(R1, land=True); cp.win_run(d.sh, "mini"); d.open(R2, land=True); cp.win_run(d.sh, "mini")
    code, j = cp.win_run(d.sh, "wide")
    W, H = d.size(); gl = cp.win_state(d.sh)["geo"]; ws = sorted([x for x in d.z if x["mode"] == FF], key=lambda t: t["id"])
    ck(f"Android 15 thật — giao diện hệ thống dựng lại {nm} rồi TỰ trả khoá xoay về dọc → khoá lại, màn chính vẫn nằm ngang, tab theo lưới ngang",
       code == 200 and j["turned"] and d.urot == 1 and (W, H) == (1280, 720) and d.od == 192 and [x["b"] for x in ws] == cp.win_grid(gl, len(ws))
       and "NGANG RỘNG" in j["msg"], (code, j, d.urot, (W, H), [x["b"] for x in ws]))
    code, j = cp.win_run(d.sh, "narrow")
    W, H = d.size(); gp3 = cp.win_state(d.sh)["geo"]; ws = sorted([x for x in d.z if x["mode"] == FF], key=lambda t: t["id"])
    ck(f"… ({nm}) Màn dọc như cũ → màn dọc, khoá dọc, mật độ cũ, tab theo lưới dọc", code == 200 and d.urot == 0 and (W, H) == (720, 1280) and d.od is None
       and [x["b"] for x in ws] == cp.win_grid(gp3, len(ws)), (code, j, d.urot, (W, H), d.od))
d = Droid(35); d.home_rot = False
for i in range(9): d.open(f"vn.game.t{i}/.Main", land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide")
ck("màn chính không xoay + nhiều tab vẫn chồng → gợi ý mức CAO HƠN (800 dp), không nhắc lại 600 dp đang dùng", code == 200 and not j["turned"] and "VD 800 dp" in j["msg"]
   and "VD 600 dp" not in j["msg"] and "Màn nhỏ nên" not in j["msg"] and "Đã xếp 9 tab" in j["msg"], (code, j))
d = Droid(35); d.open(R1, land=True)
code, j = cp.win_run(d.sh, "grow")
ck("chưa có tab nhỏ nào → Cửa sổ to hơn báo dễ hiểu", code == 409 and "Chưa có tab nhỏ" in j["error"], (code, j))

print("4e. 23/11d · GAME VỪA KHUNG THẬT (mở lại ngay trong tab) · màn rộng tự bật · XOAY MÀN bằng cửa sổ phủ — mô phỏng máy MuMu Android 12 thật")
G1, G2, RB, SETT = "com.replica.replicaisland/.MainMenuActivity", "vn.teamobi.knight/.Main", "com.roblox.client/.startup.ActivitySplash", "com.android.settings/.Settings"
def mumu(sdk=32):
    x = Droid(sdk); x.autorot = False; return x                # MuMu: bỏ qua khoá xoay, màn chỉ xoay khi có cửa sổ yêu cầu hướng
def at(d, pat): return next((k for k, x in enumerate(d.log) if pat in x), -1)
def want(d, g, ws):
    """Chỗ đúng sau Sắp xếp: app đổi cỡ thật → nguyên ô lưới; game kiểu cũ → cửa sổ đúng tỉ lệ hình game (16:9) ở góc trên trái của ô."""
    return [cp.win_shape(g, c, "land" if t["land"] else "") if d.oldkind(t) else c for t, c in zip(ws, cp.win_grid(g, len(ws)))]
d = mumu(); a = d.open(G1, land=True, legacy=True); b = d.open(RB, land=True); c = d.open(SETT); e = d.open("vn.game.cu/.Main", land=True, resz=False)
kd = cp.win_kinds(d.sh)
ck("đọc loại app theo màn GỐC của tab: game targetSdk < 24 (FORCE_RESIZABLE) + game khai báo không đổi cỡ = kiểu cũ · Roblox / Cài đặt = đổi cỡ thật · ép hướng",
   kd.get(a["id"]) == {"old": True, "fixed": "land"} and kd.get(b["id"]) == {"old": False, "fixed": "land"} and kd.get(c["id"]) == {"old": False, "fixed": ""}
   and kd.get(e["id"]) == {"old": True, "fixed": "land"} and kd.get(1) == {"old": False, "fixed": ""}, kd)
x = Droid(30); y = x.open(G1, land=True, resz=False)
ck("Android 11 ghi hướng bằng số (mOrientation=0) → vẫn nhận là app ép NGANG", cp.win_kinds(x.sh).get(y["id"]) == {"old": True, "fixed": "land"}, cp.win_kinds(x.sh))
gq = cp.win_geo("Display: mDisplayId=0\n cur=720x1280 app=720x1222", "Physical density: 320\nOverride density: 192", [])
sq = cp.win_shape(gq, (0, 29, 720, 426), "land"); sp = cp.win_shape(gq, (0, 29, 720, 426), "port")
ck("cửa sổ cho game kiểu cũ: phần HÌNH (trừ thanh tiêu đề) đúng 16:9 (game ngang) / 9:16 (game dọc), ở góc trên trái của ô, không ra ngoài ô; app không ép hướng → nguyên ô",
   sq[:2] == (0, 29) and sq[2] <= 720 and sq[3] <= 426 and abs((sq[2] - sq[0]) * 9 - (sq[3] - sq[1] - gq["cap"]) * 16) <= 16
   and sp[:2] == (0, 29) and sp[3] <= 426 and (sp[3] - sp[1] - gq["cap"]) > (sp[2] - sp[0]) and cp.win_shape(gq, (0, 29, 720, 426), "") == (0, 29, 720, 426), (gq, sq, sp))
ck("máy không đọc được dumpsys → không có loại app nào (không mở lại bừa)", cp.win_kinds(lambda c_, t=0: "") == {} and cp.win_kinds(lambda c_, t=0: "resizeMode=RESIZE_MODE_UNRESIZEABLE") == {})
d = mumu(); a = d.open(G1, land=True, legacy=True); c = d.open(G1, 10, land=True, legacy=True)
ck("pid tiến trình chính đúng người dùng (bản clone riêng), bỏ tiến trình phụ (:push) và app khác trùng đầu tên",
   cp.win_pids(d.sh, "com.replica.replicaisland", 0) == [a["pid"]] and cp.win_pids(d.sh, "com.replica.replicaisland", 10) == [c["pid"]]
   and cp.win_pids(d.sh, "com.replica", 0) == [], (cp.win_pids(d.sh, "com.replica.replicaisland", 0), cp.win_pids(d.sh, "com.replica", 0)))
# --- thu nhỏ game cũ đầu tiên trên màn 360 dp: màn rộng tự bật + mở lại đúng 1 lần, vừa cửa sổ
d = mumu(); a = d.open(G1, land=True, legacy=True); n0, id0 = a["starts"], a["id"]
ck("game cũ ép ngang toàn màn → màn máy NGANG (game yêu cầu)", d.size() == (1280, 720), d.size())
code, j = cp.win_run(d.sh, "mini"); g192 = cp.win_state(d.sh)["geo"]
ck("thu nhỏ game cũ (chưa có tab nhỏ nào, màn 360 dp): tắt app nền → bật màn rộng 600 dp (nhớ 320:720 + dấu tự bật) → đặt ô theo màn MỚI → mở lại đúng 1 LẦN vào đúng tab → game vừa cửa sổ",
   code == 200 and j["fit"] == "ok" and j["sw"] == 600 and d.od == 192 and d.prev == "320:720:a" and a["id"] == id0 and a["mode"] == FF
   and a["b"] == tuple(j["b"]) == cp.win_shape(g192, cp.win_slot(g192, []), "land") and a["starts"] == n0 + 1 and d.fits(a) and not a.get("dirty") and d.visible(a)
   and abs((a["b"][2] - a["b"][0]) * 9 - (a["b"][3] - a["b"][1] - g192["cap"]) * 16) <= 16 and a["b"][2] - a["b"][0] >= 600
   and 0 <= at(d, "am kill --user 0 com.replica.replicaisland") < at(d, "wm density 192") < at(d, "-f 0x10008000 -n com.replica.replicaisland/")
   and "màn rộng 600 dp" in j["msg"] and "vừa cửa sổ" in j["msg"] and d.size() == (720, 1280), (code, j, a, [x[:60] for x in d.log[-14:]]))
d.home_key(); b = d.open(G2, land=True, resz=False); an, ab = a["starts"], a["b"]; d.log.clear()
code, j = cp.win_run(d.sh, "mini")
ck("game cũ thứ 2 (khai báo không đổi cỡ): màn đã rộng → không đổi mật độ; cửa sổ 1 KHÔNG bị mở lại, hiện lại đúng chỗ; game 2 mở lại 1 lần, vừa cửa sổ, không đè, nằm trên cùng",
   code == 200 and j["fit"] == "ok" and j["sw"] is None and d.od == 192 and not any(re.search(r"wm density (\d+(;|$)|reset)", x) for x in d.log) and a["starts"] == an and a["b"] == ab
   and d.visible(a) and d.fits(a) and b["mode"] == FF and b["starts"] == 2 and d.fits(b) and ovl(a["b"], b["b"]) == 0 and d.z[0] is b and j["n"] == 2, (code, j, a, b))
# --- app đổi cỡ thật không bị đụng
d = mumu(); r = d.open(RB, land=True)
code, j = cp.win_run(d.sh, "mini")
ck("Roblox (đổi cỡ thật): KHÔNG mở lại, KHÔNG đổi mật độ, không về màn chính; câu báo như cũ + fit=ask (web hiện nút Vừa khung)",
   code == 200 and j["fit"] == "ask" and j["sw"] is None and d.od is None and r["starts"] == 1 and "input keyevent 3" not in d.log
   and j["msg"].startswith("Đã thu nhỏ Roblox (1 tab nhỏ). Kéo thanh"), (code, j, r))
st_ = d.open(SETT); code, j = cp.win_run(d.sh, "mini")
ck("app thường không ép hướng (Cài đặt): không mở lại, không có nút Vừa khung (fit rỗng)", code == 200 and j["fit"] is None and st_["starts"] == 1, (code, j))
d.home_key(); g = d.open(G1, land=True, legacy=True); rs = r["starts"]
code, j = cp.win_run(d.sh, "mini")
ck("đã có tab nhỏ khác đang chạy (màn 360 dp): game cũ vẫn mở lại vừa cửa sổ, nhưng KHÔNG tự đổi mật độ (không làm app đang chạy tải lại)",
   code == 200 and j["fit"] == "ok" and j["sw"] is None and d.od is None and d.prev is None and r["starts"] == rs and st_["starts"] == 1 and d.fits(g)
   and all(d.visible(x) for x in (r, st_, g)) and "màn rộng" not in j["msg"], (code, j, g))
d = mumu(); g = d.open(G1, land=True, legacy=True, fgsvc=True)
code, j = cp.win_run(d.sh, "mini")
ck("game cũ KHÔNG tắt nền được (giữ dịch vụ chạy nổi): không mở lại, không đổi mật độ, cửa sổ hiện lại đúng ô, fit=ask",
   code == 200 and j["fit"] == "ask" and g["starts"] == 1 and d.od is None and d.prev is None and g["mode"] == FF and d.visible(g) and g["b"] == tuple(j["b"]), (code, j, g))
d = Droid(28); g = d.open(G1, land=True, resz=False)
code, j = cp.win_run(d.sh, "mini")
ck("Android 9: như cũ — không đọc loại app, không mở lại, không đổi mật độ", code == 200 and j["fit"] is None and g["starts"] == 1 and d.od is None
   and not any("am kill" in x or "dumpsys activity" in x for x in d.log), (code, j))
# --- sắp xếp: ô đổi cỡ → game cũ mở lại trong ô mới
d = mumu(); a = d.open(G1, land=True, legacy=True); cp.win_run(d.sh, "mini"); d.home_key(); r = d.open(RB, land=True); cp.win_run(d.sh, "mini")
na, nr = a["starts"], r["starts"]
code, j = cp.win_run(d.sh, "tile"); g2 = cp.win_state(d.sh)["geo"]; ws = sorted([a, r], key=lambda t: t["id"])
ck("Sắp xếp 2 tab (ô to hơn ô lúc thu nhỏ): game cũ được mở lại ngay trong ô mới — cửa sổ đúng tỉ lệ hình game, vừa ô; Roblox nguyên ô lưới và KHÔNG bị mở lại; báo số game mở lại",
   code == 200 and [t["b"] for t in ws] == want(d, g2, ws) and all(d.fits(t) and d.visible(t) for t in ws) and a["starts"] == na + 1 and r["starts"] == nr
   and j["re"] == 1 and "1 game đã mở lại" in j["msg"] and a["b"][2] - a["b"][0] == 720, (code, j, [(t["b"], t["starts"], d.fits(t)) for t in ws], want(d, g2, ws)))
code, j = cp.win_run(d.sh, "tile")
ck("bấm Sắp xếp lần nữa (ô không đổi cỡ) → không game nào bị mở lại", code == 200 and j["re"] == 0 and a["starts"] == na + 1 and r["starts"] == nr
   and "mở lại" not in j["msg"], (code, j))
d.home_key(); b = d.open(G2, land=True, resz=False); cp.win_run(d.sh, "mini"); na, nb, nr = a["starts"], b["starts"], r["starts"]
code, j = cp.win_run(d.sh, "tile"); g3 = cp.win_state(d.sh)["geo"]; ws = sorted([a, r, b], key=lambda t: t["id"])
ck("thêm game cũ thứ 2 rồi Sắp xếp 3 tab: 2 game cũ có ô đổi cỡ → mở lại trong ô mới, vừa ô; Roblox không bị mở lại; đủ 3 cửa sổ cùng hiện",
   code == 200 and [t["b"] for t in ws] == want(d, g3, ws) and all(d.fits(t) and d.visible(t) for t in ws) and a["starts"] == na + 1 and b["starts"] == nb + 1
   and r["starts"] == nr and j["re"] == 2 and "2 game đã mở lại" in j["msg"], (code, j, [(t["b"], t["starts"], d.fits(t)) for t in ws]))
d.z.remove(a); d.z.insert(0, a); na = a["starts"]
code, j = cp.win_run(d.sh, "grow")
ck("Cửa sổ to hơn với game cũ: chỉ đổi cỡ (không mở lại mỗi lần bấm), fit=ask → chỉnh xong bấm Vừa khung 1 lần", code == 200 and j["id"] == a["id"] and j["fit"] == "ask"
   and a["starts"] == na and not d.fits(a), (code, j, a))
code, j = cp.win_run(d.sh, "refit")
ck("… rồi bấm Vừa khung → game mở lại đúng cỡ cửa sổ mới (vừa), các cửa sổ khác không bị mở lại", code == 200 and a["starts"] == na + 1 and d.fits(a)
   and b["starts"] == nb + 1 and r["starts"] == nr and all(d.visible(t) for t in (a, b, r)) and d.z[0] is a, (code, j, a))
# --- phóng to
d = mumu(); a = d.open(G1, land=True, legacy=True); cp.win_run(d.sh, "mini"); n0 = a["starts"]
code, j = cp.win_run(d.sh, "full")
ck("Phóng to tab nhỏ CUỐI CÙNG (màn rộng do máy tự bật): về toàn màn + trả mật độ cũ lúc app đang tắt + game mở lại đúng 1 lần, hình đủ toàn màn",
   code == 200 and a["mode"] == FS and d.od is None and d.prev is None and a["starts"] == n0 + 1 and d.fits(a) and d.z[0] is a and "toàn màn" in j["msg"]
   and "mật độ cũ" in j["msg"] and d.size() == (1280, 720), (code, j, a, d.od, d.prev))
d = mumu(); a = d.open(G1, land=True, legacy=True); cp.win_run(d.sh, "mini"); d.home_key(); b = d.open(G2, land=True, resz=False); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "full")
ck("còn tab nhỏ khác → Phóng to KHÔNG trả mật độ (tab còn lại vẫn cần màn rộng); game phóng to mở lại đủ màn, tab kia không bị mở lại",
   code == 200 and d.od == 192 and d.prev == "320:720:a" and b["mode"] == FS and d.fits(b) and a["starts"] == 2 and "mật độ cũ" not in j["msg"], (code, j, a, b))
d = mumu(); r = d.open(RB, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "full")
ck("Roblox (đổi cỡ thật) phóng to: không mở lại, câu báo như cũ", code == 200 and r["mode"] == FS and r["starts"] == 1 and j["msg"] == "Đã phóng to Roblox ra toàn màn.", (code, j))
# --- xoay màn / màn ngang rộng trên máy bỏ qua khoá xoay
d = mumu(); r = d.open(RB, land=True); cp.win_run(d.sh, "mini"); d.home_key(); a = d.open(G1, land=True, legacy=True); cp.win_run(d.sh, "mini")
calls = []; inst = lambda: (calls.append(1), d.install_helper())[1]
d.log.clear()
code, j = cp.win_run(d.sh, "wide", inst=inst)
W, H = d.size(); gl = cp.win_state(d.sh)["geo"]; ws = sorted([r, a], key=lambda t: t["id"])
ck("MuMu (bỏ qua khoá xoay): Màn ngang rộng → cài app trợ giúp 1 lần + cho quyền hiện trên app khác + bật cửa sổ phủ yêu cầu màn ngang → màn chính NGANG, 600 dp, tab theo lưới ngang, game cũ vừa ô",
   code == 200 and j["turned"] and (W, H) == (1280, 720) and d.ovl and len(calls) == 1 and d.od == 192 and d.prev == "320:720"
   and [x["b"] for x in ws] == want(d, gl, ws) and d.fits(a) and "NGANG RỘNG" in j["msg"]
   and any("SYSTEM_ALERT_WINDOW allow" in x and "am start-foreground-service --user 0 -n vn.cloudblue.xoay/.Svc --es o land" in x for x in d.log), (code, j, (W, H), calls, [x["b"] for x in ws]))
code, j = cp.win_run(d.sh, "wide", inst=inst)
ck("bấm lại: app trợ giúp đã có đúng bản → không cài lại", code == 200 and len(calls) == 1 and j["turned"] and d.ovl, (code, j, calls))
d.log.clear(); code, j = cp.win_run(d.sh, "narrow", inst=inst)
ck("Màn dọc như cũ: tắt cửa sổ phủ (tắt app trợ giúp) → màn DỌC, mật độ cũ, game cũ vừa ô mới", code == 200 and not d.ovl and d.size() == (720, 1280) and d.od is None
   and d.prev is None and d.fits(a) and f"am force-stop {cp.ROT_PKG}" in d.log and len(calls) == 1, (code, j, d.size(), d.od))
d = mumu(); d.noinst = True; r = d.open(RB, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide", inst=d.install_helper)
ck("không cài được app trợ giúp → vẫn đặt 600 dp, báo rõ màn chính của máy không xoay ngang", code == 200 and not j["turned"] and d.od == 192 and not d.ovl
   and "không xoay ngang" in j["msg"], (code, j))
d = mumu(); a = d.open(G1, land=True, legacy=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide", inst=d.install_helper)
ck("máy tự bật màn rộng lúc thu nhỏ rồi khách TỰ bấm Màn ngang rộng → bỏ dấu tự bật (giữ mật độ đã nhớ)", code == 200 and d.prev == "320:720" and d.od == 192 and j["turned"], (code, j, d.prev))
code, j = cp.win_run(d.sh, "full")
ck("… phóng to tab cuối KHÔNG tự trả mật độ nữa (khách đã chọn màn rộng)", code == 200 and d.od == 192 and d.prev == "320:720" and "mật độ cũ" not in j["msg"] and d.fits(a), (code, j, d.od, d.prev))
d = Droid(35); d.home_rot = False; r = d.open(RB, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide", inst=d.install_helper)
ck("máy có khoá xoay nhưng màn chính không chịu nằm ngang → cửa sổ phủ ép ngang: màn chính NGANG", code == 200 and j["turned"] and d.ovl and d.size() == (1280, 720)
   and d.urot == 1 and "NGANG RỘNG" in j["msg"], (code, j, d.size()))
d = Droid(35); r = d.open(RB, land=True); cp.win_run(d.sh, "mini")
code, j = cp.win_run(d.sh, "wide", inst=d.install_helper)
ck("máy xoay ngang được bằng khoá xoay (màn chính kiểu máy tính bảng) → KHÔNG cần app trợ giúp", code == 200 and j["turned"] and not d.ovl and d.helper == 0, (code, j, d.helper))
st0, ok0 = cp.win_rot(mumu().sh, 1, lambda s_: None, None)
ck("win_rot không có cách cài app trợ giúp → trả 'chưa xoay được' (không treo, không lỗi)", ok0 is False, ok0)

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
cp.rot_install = lambda port: D.install_helper()
c, j = call(PID + "/rotate", "t-owner", {"to": "land"})
ck("POST /rotate {to: land} → khoá xoay không xoay được màn chính (360 dp) → cửa sổ phủ → màn NGANG", c == 200 and j.get("to") == "land" and j.get("turned")
   and D.ovl and D.size() == (1280, 720) and "NGANG" in j.get("msg", ""), (c, j, D.size()))
c, j = call(PID + "/rotate", "t-owner", {})
ck("POST /rotate (không ghi hướng) → đổi sang hướng kia: về DỌC, tắt cửa sổ phủ", c == 200 and j.get("to") == "port" and not D.ovl and D.size() == (720, 1280)
   and "DỌC" in j.get("msg", ""), (c, j, D.size()))
c, j = call(PID + "/rotate", "t-owner", {})
ck("POST /rotate lần nữa → lại NGANG (app trợ giúp đã cài, không cài lại)", c == 200 and j.get("to") == "land" and j.get("turned") and D.ovl, (c, j))
call(PID + "/rotate", "t-owner", {"to": "port"})
c, j = call(PID + "/rotate", "t-other", {"to": "land"})
ck("xoay máy người khác → 404", c == 404 and not D.ovl, (c, j))
SLOW["on"] = True; res = {}
th = threading.Thread(target=lambda: res.update(a=call(PID + "/win", "t-owner", {"do": "tile"}))); th.start(); time.sleep(0.3)
cp_lock_to = None
c2, j2 = call(PID + "/win", "t-owner", {"do": "tile"}); th.join(); SLOW["on"] = False
ck("2 lần bấm cùng lúc: lần sau chờ lần trước xong (khoá 1 việc / máy) rồi vẫn chạy", res["a"][0] == 200 and c2 == 200, (res, c2, j2))

print("%d/%d dat" % (OK[0], OK[1]))
sys.exit(0 if OK[0] == OK[1] else 1)
