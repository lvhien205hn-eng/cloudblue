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

    def __init__(self, sdk, w=720, h=1280, nav=96, free=True, lag=0, stick=False, ui=None):
        self.sdk, self.W, self.H, self.nav, self.free = sdk, w, h, nav, free
        # 23/11e (đo trên MuMu Android 12 thật + máy ảo thật): GIAO DIỆN HỆ THỐNG chỉ lo cửa sổ nổi khi nó khởi động LÚC máy đã bật cửa sổ nổi
        # (ui = True). ui = False: · Android 12L (sdk 32): hình của tab ("at") đứng nguyên chỗ cũ dù khung tab ("b") đã đổi; chỉ về đúng chỗ khi tab
        # vừa được đưa từ chỗ bị che lên / vừa mở mới · Android 13+: hình đúng chỗ nhưng cửa sổ KHÔNG CÓ thanh tiêu đề (lớp hình "Decor container
        # of Task=N") · Android 12 (sdk 31): lõi Android tự lo, không lỗi. Bật lại giao diện hệ thống lúc cửa sổ nổi đã bật → hết.
        self.ui = (free if ui is None else ui) if sdk >= 31 else True
        self.ui_pid, self.ui_kills, self.ui_wait, self.ui_key, self.boot = 900, 0, 0, None, "b00t-1"
        self.ui_root, self.ui_heal, self.in_ok, self.ghost = True, True, True, None   # tắt được tiến trình · bật lại thì khỏi · đọc được dumpsys input · dòng cửa sổ ẩn
        self.sf_ok = True                                         # đọc được tên lớp hình (dumpsys SurfaceFlinger --list)
        # 23/11e lượt 3 (đo máy ảo thật): · decor_move: Android 13+ vừa bật lại giao diện hệ thống thì cửa sổ nổi ĐANG CÓ chưa được vẽ thanh tiêu đề, tới
        # khi tab đó "đổi" (đổi khung / lên trên / hiện ra / đổi chế độ; decor_move = "front": chỉ khi lên trên / hiện ra) · decor_never: bản Android không bao giờ vẽ thanh tiêu đề · insetlag: vừa
        # HẠ mật độ thì thanh trạng thái còn cao như cũ thêm N lệnh — Android đẩy cửa sổ nổi xuống dưới thanh cũ; và Android NHỚ khung đã yêu cầu:
        # yêu cầu lại đúng khung đó thì bỏ qua (khung thật giữ nguyên chỗ lệch). Máy ảo 12L thật: lệch 22 px, 8 giây sau vẫn lệch.
        self.decor_move, self.decor_never, self.insetlag, self._stale = False, False, 0, None
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
        # stoplag: máy chậm — sau khi về màn chính, màn của app còn "đang dừng" thêm N lần `am kill` nữa mới tắt được (máy ảo 12L: ~10 giây)
        # ofmt: cách máy ghi hướng của app trong dumpsys — "m" (Android ≤ 13: mOrientation=) · "o" (Android 14+: overrideOrientation=) · "" (không ghi)
        self.stoplag, self._lag, self.ofmt = 0, 0, "m"
        # nokill: `am kill` không bao giờ ăn (máy ảo Android 12L thật: màn đã dừng 10 giây vẫn sống) · root9: tắt thẳng tiến trình (kill -9) được
        self.nokill, self.root9 = False, True

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

    def scaled(self, t):
        """Android 13+ ở kiểu không ép đổi cỡ: app KHAI BÁO không đổi cỡ (không phải app targetSdk < 24) được Android thu nhỏ cả hình vừa cửa sổ."""
        return self.sdk >= 33 and (self.force, self.nonres) == ("0", "1") and not t.get("resz", True) and not t.get("legacy")

    def oldkind(self, t):
        return (not t.get("resz", True)) or bool(t.get("legacy"))

    def fits(self, t):
        """Hình app có VỪA vùng đang có không: app kiểu cũ chỉ vừa khi được dựng đúng cỡ + mật độ đang có; app đổi cỡ thật luôn vừa."""
        if not self.oldkind(t): return True
        if self.scaled(t): return True
        return t.get("pid") is not None and t.get("made") == self._box(t) + ((self.od or self.pd),)

    def install_helper(self):
        if self.noinst: return False
        self.helper = cp.ROT_VER; return True

    def home_key(self):
        h = next(x for x in self.z if x["type"] == "home"); self.z.remove(h); self.z.insert(0, h); self.sticky = False; self.pend = 0; self._sync()
        self._lag = self.stoplag

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
        if self.insetlag and (v or self.pd) < (self.od or self.pd):       # hạ mật độ: thanh trạng thái cũ (24 dp ở mật độ CŨ) còn đó thêm insetlag lệnh
            self._stale = [int(round(24 * (self.od or self.pd) / 160.0)), self.insetlag + 1]
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
        vis = {x["id"]: self.visible(x) for x in self.z}
        pre = {x["id"]: (x["mode"], tuple(x["b"]), vis[x["id"]]) for x in self.z}; top0 = self.z[0]["id"] if self.z else None
        o = self._sh(c, t); self._sync(); self._place(vis)
        if self.ui:                                               # tab vừa "đổi" lúc giao diện hệ thống đang lo cửa sổ nổi → được vẽ thanh tiêu đề
            for x in self.z:
                if not x.get("nodecor"): continue
                was = pre.get(x["id"]) or (None, None, False)
                up_ = (self.visible(x) and not was[2]) or (self.z[0] is x and top0 != x["id"])        # vừa hiện ra / vừa lên trên cùng
                if up_ or (self.decor_move != "front" and was[:2] != (x["mode"], tuple(x["b"]))): x["nodecor"] = False
        return o

    def _want(self, t):
        W, H = self.size()
        return tuple(t["b"]) if t["mode"] == FF else (0, 0, W, H)

    def _place(self, vis=None):
        """Chỗ THẬT của hình mỗi tab ("at"): giao diện hệ thống đặt chỗ được (ui) / Android ≤ 11 → theo khung; không thì cỡ theo khung nhưng
           GÓC đứng nguyên chỗ cũ, trừ tab mới, tab toàn màn, tab vừa được đưa từ chỗ bị che lên (Android đặt lại chỗ khi chạy hiệu ứng mở tab)."""
        for t in self.z:
            w = self._want(t); old = t.get("at")
            if self.ui or self.sdk != 32 or old is None or t["mode"] != FF or (vis is not None and not vis.get(t["id"], False) and self.visible(t)): t["at"] = w
            else: t["at"] = (old[0], old[1], old[0] + w[2] - w[0], old[1] + w[3] - w[1])

    def drawn_ok(self, t):
        """Hình của tab nằm đúng khung tab + (Android 13+) cửa sổ nổi có thanh tiêu đề — thứ khách thấy."""
        self._place({x["id"]: self.visible(x) for x in self.z}); return t.get("at") == self._want(t) and self.decorated(t)

    def decorated(self, t):
        """Android 13+: cửa sổ nổi có thanh tiêu đề (do giao diện hệ thống vẽ) không. Bản khác / tab toàn màn: không xét."""
        return (self.ui and not t.get("nodecor") and not self.decor_never) if (self.sdk >= 33 and t["mode"] == FF) else True

    def _sh(self, c, t=30):
        self.log.append(c)
        if self._stale:
            self._stale[1] -= 1
            if self._stale[1] <= 0: self._stale = None
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
            req = tuple(int(m.group(i)) for i in range(2, 6))
            if self.insetlag:
                if tk.get("req") == req: return ""               # Android: trùng khung ĐÃ YÊU CẦU → bỏ qua, khung thật giữ nguyên (kể cả đang lệch)
                tk["req"] = req
                top = self._stale[0] if self._stale else 0
                if req[1] < top: req = (req[0], top, req[2], req[3] + top - req[1])      # đẩy xuống dưới thanh trạng thái (cũ)
            tk["b"] = req; return ""
        # ---- 23/11d: loại app (dumpsys activity) · tiến trình (ps) · am kill · mở lại sạch vào đúng tab · app trợ giúp xoay màn ----
        if c == cp.WIN_KIND_SH:
            o = []
            for tk in self.z:
                if tk["type"] != "standard":
                    o += [f"      * Hist  #0: ActivityRecord{{47020f2 u0 {tk['comp']} t{tk['id']}}}", "        resizeMode=RESIZE_MODE_RESIZEABLE"]; continue
                if tk.get("legacy"):                              # app nhiều màn: màn trên cùng (Hist #1) khai báo khác màn GỐC (Hist #0) → phải lấy màn gốc
                    o += [f"    * Hist  #1: ActivityRecord{{9a1b2c3 u{tk['user']} {tk['comp'].split('/')[0]}/.Game t{tk['id']}}}", "      resizeMode=RESIZE_MODE_RESIZEABLE"]
                o.append(f"    * Hist  #0: ActivityRecord{{223dfd3 u{tk['user']} {tk['comp']} t{tk['id']}}}")
                if tk["land"] and self.ofmt == "o":
                    o += ["      mOccludesParent=true overrideOrientation=SCREEN_ORIENTATION_SENSOR_LANDSCAPE", "      requestedOrientation=SCREEN_ORIENTATION_SENSOR_LANDSCAPE"]
                elif tk["land"] and self.ofmt == "m":
                    o.append("      mOrientation=SCREEN_ORIENTATION_LANDSCAPE" if self.sdk >= 31 else "      mOccludesParent=true mOrientation=0")
                elif self.ofmt == "o": o.append("      mOccludesParent=true overrideOrientation=SCREEN_ORIENTATION_UNSPECIFIED")
                o.append("      resizeMode=RESIZE_MODE_" + ("FORCE_RESIZABLE_LANDSCAPE_ONLY" if tk.get("legacy") else "RESIZEABLE" if tk["resz"] else "UNRESIZEABLE"))
            return "\n".join(o)
        m = re.match(r"ps -A -o USER,PID,NAME 2>/dev/null \| grep -F ' ([\w.]+)'$", c)
        if m:
            o = [f"u{tk['user']}_a{130 + tk['id']}        {tk['pid']} {tk['comp'].split('/')[0]}" for tk in self.z
                 if tk["type"] == "standard" and tk.get("pid") and tk["comp"].split("/")[0].startswith(m.group(1))]
            return "\n".join(o + [f"u0_a999          77 {m.group(1)}:push", f"u0_a998          78 {m.group(1)}.khac"])     # tiến trình phụ / app khác trùng đầu tên: không tính
        m = re.match(r"kill -9 ([\d ]+) 2>/dev/null \|\| su -c 'kill -9 ([\d ]+)' 2>/dev/null$", c)
        if m:
            assert m.group(1) == m.group(2), c
            if self.root9:
                for pid in m.group(1).split():
                    for tk in self.z:                             # màn của app đã dừng + lưu trạng thái → tiến trình chết, tab + khung vẫn còn
                        if tk.get("pid") == int(pid) and not self.visible(tk): tk["pid"] = None
            return ""
        if c.startswith("am kill --user "):
            if self.nokill: return ""
            if self._lag > 0: self._lag -= 1; return ""             # màn của app chưa dừng hẳn → chưa tắt được
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
        m = re.match(r"dumpsys activity services ([\w.]+) 2>/dev/null \| grep -m1 isForeground=true$", c)
        if m: return "      isForeground=true foregroundId=7 foregroundNoti=Notification(channel=x)" if any(
            tk.get("fgsvc") and tk["comp"].split("/")[0] == m.group(1) for tk in self.z) else ""
        if c.startswith(f"cmd appops set {cp.ROT_PKG} SYSTEM_ALERT_WINDOW allow"):
            if not self.helper: return "Error: Not found; no service started."
            self.ovl = "--es o land" in c; return "Starting service: Intent { cmp=vn.cloudblue.xoay/.Svc (has extras) }"
        if c == cp.WIN_AUTOROT_SH: return f"    mSupportAutoRotation={'true' if self.autorot else 'false'}"
        # ---- 23/11e: giao diện hệ thống (SystemUI) + chỗ thật của hình (dumpsys input) ----
        if c == cp.WIN_UI_PID_SH:
            if self.ui_wait > 0: self.ui_wait -= 1; return ""       # đang bật lại, chưa có tiến trình mới
            return str(self.ui_pid)
        if c in (cp.WIN_UI_KILL_SH.replace("@F@", "0"), cp.WIN_UI_KILL_SH.replace("@F@", "1")):
            if c == cp.WIN_UI_KILL_SH.replace("@F@", "0") and self.ui_key == self.boot: return "#done"
            self.ui_key = self.boot; old = self.ui_pid
            if self.ui_root:                                        # tiến trình tắt → Android tự bật lại (2 lần hỏi sau mới thấy tiến trình mới)
                self.ui_pid += 1; self.ui_wait = 2; self.ui_kills += 1
                if self.ui_heal: self.ui = self.free
                if self.decor_move:                                 # thanh tiêu đề do tiến trình cũ vẽ mất theo nó; cửa sổ nổi đang có phải "đổi" mới được vẽ lại
                    for x in self.z:
                        if x["mode"] == FF and x["type"] == "standard": x["nodecor"] = True
            return f"#kill {old}"
        if c.startswith("dumpsys input 2>/dev/null | grep -E "):
            if not self.in_ok: return ""
            m = re.search(r"name='\?\[0-9a-f\]\+ \((.*?)\)/", c); pk = set(m.group(1).replace("\\.", ".").split("|")) if m else set()
            assert pk, "máy giả không đọc được danh sách gói trong lệnh dumpsys input: " + c      # đổi dạng lệnh mà quên sửa máy giả → báo ngay
            self._place(); o = []
            for k, tk in enumerate(self.z):
                pkg = tk["comp"].split("/")[0]
                if pkg not in pk or tk["type"] != "standard": continue
                l, tp, r, b = tk["at"]; shown = self.visible(tk)
                cls = tk["comp"].replace("/.", "/" + pkg + ".")
                if self.sdk >= 33:
                    o.append(f"      {k}: name='5f0c{k}a1 {cls}', id={300 + k}, displayId=0, inputConfig={'0x0' if shown else 'NOT_VISIBLE'}, alpha=1.00, "
                             f"frame=[{l},{tp}][{r},{b}], globalScale=1.000000, applicationInfo.name=, touchableRegion=[{l - 36},{tp - 36}][{r + 36},{b + 36}]")
                else:
                    o.append(f"      {k}: name='5f0c{k}a1 {cls}', id={300 + k}, displayId=0, portalToDisplayId=-1, paused=false, focusable=true, hasWallpaper=false, "
                             f"visible={'true' if shown else 'false'}, alpha=1.00, flags=NOT_TOUCH_MODAL, type=BASE_APPLICATION, frame=[{l},{tp}][{r},{b}], "
                             f"globalScale=1.000000, touchableRegion=[{l - 36},{tp - 36}][{r + 36},{b + 36}]")
            if self.ghost and self.ghost[0] in pk:                  # máy thật còn giữ dòng của cửa sổ ĐÃ ẨN (khung cũ) → không được tính
                g = self.ghost[1]
                o.append(f"      9: name='23304ae {self.ghost[0]}/{self.ghost[0]}.Main', id=77, displayId=0, " + (
                    f"inputConfig=NOT_VISIBLE | NOT_FOCUSABLE, alpha=1.00, " if self.sdk >= 33 else
                    f"portalToDisplayId=-1, paused=false, focusable=false, hasWallpaper=false, visible=false, alpha=1.00, flags=0, type=BASE_APPLICATION, ")
                    + f"frame=[{g[0]},{g[1]}][{g[2]},{g[3]}], globalScale=1.000000")
            return "\n".join(o)
        if c.startswith("am startservice --user 0 -n com.android.systemui/"): self.ui_wait = 0; return ""
        if c == cp.WIN_DECOR_SH:                                # tên lớp hình: hình của tab + (Android 13+, giao diện hệ thống lo cửa sổ nổi) thanh tiêu đề
            if not self.sf_ok: return ""
            new = self.sdk >= 34                                  # Android 14 / 15 (đo máy ảo 35): mỗi dòng bọc trong RequestedLayerState{…}
            wrap = (lambda n, k: f"RequestedLayerState{{{n}#{k} parentId={k + 40} z=1}}") if new else (lambda n, k: f"{n}#{k}")
            o = [wrap("Bounds for - Task=99", 1), wrap("Dim layer of Task=98", 2)]
            for tk in self.z:
                i = tk["id"]; o.append(wrap(f"Task={i}", i * 3))
                if tk["mode"] == FF and tk["type"] == "standard" and self.sdk >= 33 and self.decorated(tk) and self.visible(tk):     # tab bị che: Android gỡ thanh tiêu đề
                    o += [wrap(f"Decor container of Task={i}", i * 3 + 1), wrap(f"Caption container of Task={i}", i * 3 + 2)]
                    if new: o += [f"RequestedLayerState{{TaskInputSink of Surface(name=Decor container of Task={i})/@0x8ca0b65#{i * 3 + 5} parentId={i * 3 + 1} z=-2}}",
                                  f"RequestedLayerState{{Caption of Task={i}Leash#{i * 3 + 6} parentId={i * 3 + 2}}}"]
            return "\n".join(o)
        return "UNKNOWN " + c


def ovl(a, b): return cp._ovl(a, b)


# ============================================================== 1. đọc + lưới
print("1. Lưới xếp tab · chỗ cho cửa sổ mới")
gp = cp.win_geo("  Display: mDisplayId=0 rootTasks=3\n    init=720x1280 320dpi cur=720x1280 app=720x1184 rng=x", "Physical density: 320", [])
ck("màn dọc 720x1280: thanh trạng thái 48 px, thanh điều hướng dưới 96 px, thanh tiêu đề 84 px (42 dp)",
   (gp["w"], gp["h"], gp["top"], gp["bottom"], gp["right"], gp["cap"]) == (720, 1280, 48, 96, 0, 84), gp)
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
cp.win_run = lambda sh, do, sleep=(lambda s: None), inst=None, memo=None: _win_run(sh, do, sleep, inst, memo)
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
    if sdk >= cp.WIN_SCM_SDK: ck(f"Android {sdk}: KHÔNG ép đổi cỡ + cho app không đổi cỡ vào cửa sổ (Android thu nhỏ cả hình — máy MuMu Android 15 thật: đúng chỗ)",
                                 conf and "force_resizable_activities 0" in conf[-1] and "enable_non_resizable_multi_window 1" in conf[-1]
                                 and (d.force, d.nonres) == ("0", "1"), (conf, d.force, d.nonres))
    else: ck(f"Android {sdk}: giữ ép đổi cỡ (không đổi cài đặt máy đang chạy tốt)", not conf and d.force == "1", (conf, d.force))
    d.log.clear(); d.home_key(); d.open(R2, land=True, resz=sdk >= 29); code, j = cp.win_run(d.sh, "mini"); b = d.task(R2)
    ck(f"Android {sdk}: cửa sổ cũ đưa lên lại bằng `am task focus` (không gửi lệnh mở cho app)", code == 200 and d.visible(a) and d.visible(b)
       and any(x == f"am task focus {a['id']} 2>&1" for x in d.log) and not any(f"-n {R1}" in x and "--task" not in x for x in d.log), d.log[-10:])
    ck(f"Android {sdk} đã đúng cài đặt → lần sau không đặt lại", not any(x.startswith("settings put global enable_freeform") for x in d.log), d.log[:4])
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
   and abs((a["b"][2] - a["b"][0]) * 9 - (a["b"][3] - a["b"][1] - g192["cap"]) * 16) <= 16 and a["b"][2] - a["b"][0] >= 590
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
# --- 23/11d vòng 3: bỏ kiểu size compat · bù thanh tiêu đề lúc mở lại (Android 10–12L) · `am kill` không ăn → tắt thẳng tiến trình
d = mumu(); d.force, d.nonres = "0", "1"; a = d.open(G1, land=True, resz=False); code, j = cp.win_run(d.sh, "mini")
ck("máy đang ở kiểu cũ của bản 23/11c (không ép đổi cỡ) → lần bấm đầu đặt lại ÉP ĐỔI CỠ (bỏ kiểu Android thu nhỏ hình — MuMu vẽ lệch chỗ), game vẫn mở lại vừa cửa sổ",
   code == 200 and d.force == "1" and j["fit"] == "ok" and d.fits(a)
   and any(x == "settings put global enable_freeform_support 1; settings put global force_resizable_activities 1" for x in d.log), (code, j, d.force, d.log[:3]))
for sdk in (29, 31, 32, 33, 35):
    d = Droid(sdk); d.od = 192; a = d.open(G1, land=True, legacy=True); n0 = a["starts"]; code, j = cp.win_run(d.sh, "mini"); fb = tuple(j.get("b") or ())
    st = at(d, "-f 0x10008000 -n com.replica.replicaisland/")
    late = [x for k, x in enumerate(d.log) if k > st >= 0 and x.startswith(f"am task resize {a['id']} ") and x != f"am task resize {a['id']} {fb[0]} {fb[1]} {fb[2]} {fb[3]} 2>&1"]
    ck(f"Android {sdk}: mở lại THẲNG đúng cỡ cửa sổ — sau khi mở không đổi cỡ thêm lần nào (game kiểu cũ không chịu được đổi cỡ muộn), không chờ gfxinfo",
       code == 200 and j["fit"] == "ok" and st >= 0 and not late and at(d, "dumpsys gfxinfo") < 0 and a["b"] == fb and d.fits(a) and a["starts"] == n0 + 1
       and at(d, f"am task resize {a['id']} {fb[0]} {fb[1]} {fb[2]} {fb[3]} 2>&1") < st, (code, j, a, late))
for sdk in (33, 35):
    d = mumu(sdk); a = d.open(G2, land=True, resz=False); n0 = a["starts"]; code, j = cp.win_run(d.sh, "mini")
    kd = cp.win_kinds(d.sh, True).get(a["id"]); kd0 = cp.win_kinds(d.sh).get(a["id"])
    ck(f"Android {sdk} (máy MuMu Android 15 thật thu hình đúng chỗ): game KHAI BÁO không đổi cỡ → để Android thu nhỏ cả hình: KHÔNG mở lại, không đổi mật độ, không tắt app; web vẫn hiện nút Vừa khung (fit=ask)",
       code == 200 and j["fit"] == "ask" and a["starts"] == n0 and a["mode"] == FF and d.od is None and (d.force, d.nonres) == ("0", "1") and d.fits(a)
       and not any("am kill" in x or "-f 0x10008000" in x for x in d.log) and kd == {"old": False, "fixed": "land", "scm": True} and kd0 == {"old": True, "fixed": "land"},
       (code, j, a, kd, kd0))
    gq = cp.win_state(d.sh)["geo"]; cq = cp.win_slot(gq, []); wq = (a["b"][2] - a["b"][0], a["b"][3] - a["b"][1] - gq["cap"])
    ck(f"Android {sdk}: 23/11e — cửa sổ của game được Android THU HÌNH cũng đúng tỉ lệ hình game 16:9 (không thì Android chừa dải đen quanh hình — đo máy MuMu Android 15 thật)",
       a["b"] == cp.win_shape(gq, cq, "land") and a["b"] != cq and abs(wq[0] * 9 - wq[1] * 16) <= 16, (a["b"], cq, wq))
    code, j = cp.win_run(d.sh, "tile"); c1 = cp.win_grid(gq, 1)[0]; wq = (a["b"][2] - a["b"][0], a["b"][3] - a["b"][1] - gq["cap"])
    ck(f"Android {sdk}: … Sắp xếp khi chỉ có 1 tab: cửa sổ rộng hết màn nhưng CAO đúng tỉ lệ game (không phủ đen cả màn), game không bị mở lại",
       code == 200 and a["b"] == cp.win_shape(gq, c1, "land") and a["b"][3] - a["b"][1] < (c1[3] - c1[1]) // 2 and abs(wq[0] * 9 - wq[1] * 16) <= 16 and a["starts"] == n0,
       (code, j, a["b"], c1, wq))
    d.log.clear(); code, j = cp.win_run(d.sh, "refit")
    ck(f"Android {sdk}: … khách bấm 🖼 Vừa khung → mở lại đúng 1 lần ngay trong tab (hình nét theo cỡ cửa sổ)",
       code == 200 and a["starts"] == n0 + 1 and a["mode"] == FF and not a.get("dirty") and at(d, "am kill --user 0 vn.teamobi.knight") >= 0, (code, j, a))
    d = mumu(sdk); g = d.open(G1, land=True, legacy=True); n0 = g["starts"]; code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: game targetSdk < 24 (Android coi là đổi cỡ được, KHÔNG thu hình) → vẫn tự mở lại ngay trong tab, vừa cửa sổ",
       code == 200 and j["fit"] == "ok" and g["starts"] == n0 + 1 and d.fits(g), (code, j, g))
cp.WIN_SCM_KEEP = False
d = mumu(35); a = d.open(G2, land=True, resz=False); n0 = a["starts"]; code, j = cp.win_run(d.sh, "mini")
ck("WIN_SCM_KEEP = False (bộ thử máy ảo thật dùng): Android 15 cũng tự mở lại app khai báo không đổi cỡ", code == 200 and j["fit"] == "ok" and a["starts"] == n0 + 1, (code, j, a))
cp.WIN_SCM_KEEP = True
d = mumu(); d.nokill = True; a = d.open(G1, land=True, legacy=True); n0 = a["starts"]; code, j = cp.win_run(d.sh, "mini")
nk = len([x for x in d.log if x.startswith("am kill --user")]); k9 = [x for x in d.log if x.startswith("kill -9 ")]
ck("`am kill` không bao giờ ăn (máy ảo Android 12L thật) → thử đủ số lần rồi tắt THẲNG tiến trình (kill -9, có đường su) → tab vẫn giữ, game mở lại đúng 1 lần, vừa cửa sổ",
   code == 200 and j["fit"] == "ok" and nk == cp.WIN_KILL_TRIES and len(k9) == 1 and " || su -c 'kill -9 " in k9[0] and a["starts"] == n0 + 1 and d.fits(a) and not a.get("dirty"),
   (code, j, nk, k9, a))
d = mumu(); d.nokill = True; d.root9 = False; a = d.open(G1, land=True, legacy=True); n0 = a["starts"]; code, j = cp.win_run(d.sh, "mini")
ck("… máy không tắt thẳng được (không đủ quyền): KHÔNG mở lại, app chưa bị đụng, cửa sổ hiện lại, fit=ask (khách bấm Vừa khung nếu cần)",
   code == 200 and j["fit"] == "ask" and a["starts"] == n0 and a["pid"] is not None and a["mode"] == FF and d.visible(a) and not a.get("dirty"), (code, j, a))
# --- máy ghi hướng app kiểu khác / không ghi · máy chậm · app giữ dịch vụ chạy nổi
d = mumu(35); d.ofmt = "o"; a = d.open(G1, land=True, resz=False); c = d.open(SETT)
kd = cp.win_kinds(d.sh)
ck("Android 14+ ghi hướng ở dòng overrideOrientation= / requestedOrientation= → vẫn nhận app ép NGANG; app không ép hướng (UNSPECIFIED) → rỗng",
   kd.get(a["id"]) == {"old": True, "fixed": "land"} and kd.get(c["id"]) == {"old": False, "fixed": ""}, kd)
d = mumu(35); d.ofmt = ""; a = d.open(G1, land=True, legacy=True)
ck("máy KHÔNG ghi hướng của app → loại app đọc được, hướng rỗng", cp.win_kinds(d.sh).get(a["id"]) == {"old": True, "fixed": ""}, cp.win_kinds(d.sh))
code, j = cp.win_run(d.sh, "mini"); gq2 = cp.win_state(d.sh)["geo"]
ck("… thu nhỏ: app toàn màn làm màn NGANG rồi thành cửa sổ thì màn về dọc → coi là app ép ngang: cửa sổ vẫn đúng tỉ lệ hình game, game mở lại vừa cửa sổ",
   code == 200 and j["fit"] == "ok" and a["b"] == cp.win_shape(gq2, cp.win_slot(gq2, []), "land") and d.fits(a), (code, j, a["b"]))
d = mumu(); d.stoplag = 8; a = d.open(G1, land=True, legacy=True); n0 = a["starts"]
code, j = cp.win_run(d.sh, "mini"); nk = len([x for x in d.log if x.startswith("am kill --user")])
ck("máy CHẬM (màn của app dừng hẳn sau ~7 giây): kiên nhẫn thử `am kill` tới khi tắt được rồi mở lại — vẫn vừa cửa sổ, đúng 1 lần mở lại",
   code == 200 and j["fit"] == "ok" and nk == 9 and a["starts"] == n0 + 1 and d.fits(a), (code, j, nk, a))
d = mumu(); a = d.open(G1, land=True, legacy=True, fgsvc=True)
code, j = cp.win_run(d.sh, "mini"); nk = len([x for x in d.log if x.startswith("am kill --user")])
ck("app giữ dịch vụ chạy nổi: thử 3 lần rồi thôi (không chờ đủ 10 giây), không mở lại", code == 200 and j["fit"] == "ask" and nk == 3 and a["starts"] == 1
   and any("isForeground=true" in x for x in d.log), (code, j, nk))
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

# ============================================================== 4b. 23/11e — hình của cửa sổ nhỏ nằm đúng chỗ (Android 12+)
print("4b. 23/11e · Android 12+: giao diện hệ thống đặt chỗ cửa sổ nhỏ — bật cửa sổ nổi sau khi mở máy thì phải bật lại giao diện hệ thống 1 lần")
RZ1, RZ2, OLD1 = "com.roblox.client/.startup.ActivitySplash", "com.termux/.app.TermuxActivity", "vn.game.cu/.Main"
kills = lambda d: len([x for x in d.log if x.startswith("B=$(cat /proc/sys/kernel/random/boot_id") and "#kill" in x])
reads = lambda d: len([x for x in d.log if x.startswith("dumpsys input")])
layers = lambda d: len([x for x in d.log if x == cp.WIN_DECOR_SH])
for sdk, why in ((32, "hình lệch khung"), (33, "cửa sổ thiếu thanh tiêu đề"), (35, "cửa sổ thiếu thanh tiêu đề")):
    d = Droid(sdk, ui=False); a = d.open(RZ1)                # máy THẬT đang chạy: cửa sổ nổi đã bật, nhưng giao diện hệ thống chạy từ trước đó
    code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}, giao diện hệ thống chạy từ trước khi bật cửa sổ nổi: thu nhỏ tab đầu → thấy {why} → bật lại giao diện hệ thống ĐÚNG 1 lần → hình đúng ô"
       + (", có thanh tiêu đề" if sdk >= 33 else ""),
       code == 200 and a["mode"] == FF and d.ui_kills == 1 and d.ui and d.drawn_ok(a) and a["at"] == tuple(j["b"]) and d.ui_key == d.boot
       and (reads(d) == 0 and layers(d) >= 2 if sdk >= 33 else reads(d) >= 2 and layers(d) == 0), (code, j, a, d.ui_kills, reads(d), layers(d)))
    b = d.open(RZ2); code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: thu nhỏ tab thứ 2 → KHÔNG bật lại nữa, hình tab 2 nằm đúng ô của nó, không đè tab đầu",
       code == 200 and d.ui_kills == 1 and d.drawn_ok(a) and d.drawn_ok(b) and ovl(a["at"], b["at"]) == 0, (code, j, a, b, d.ui_kills))
    code, j = cp.win_run(d.sh, "tile")
    ck(f"Android {sdk}: Sắp xếp tab → hình mọi tab đúng ô, không bật lại giao diện hệ thống", code == 200 and d.ui_kills == 1 and d.drawn_ok(a) and d.drawn_ok(b), (code, j, a, b))
d = Droid(31, ui=False); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini"); b = d.open(RZ2); cp.win_run(d.sh, "mini")
ck("Android 12 (sdk 31 — máy ảo thật: lõi Android tự đặt chỗ, không lỗi): có kiểm chỗ thật của hình, KHÔNG bật lại giao diện hệ thống",
   code == 200 and d.ui_kills == 0 and reads(d) >= 2 and d.drawn_ok(a) and d.drawn_ok(b), (d.ui_kills, reads(d)))
for sdk in (33, 35):
    d = Droid(sdk); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini"); b = d.open(RZ2); cp.win_run(d.sh, "mini"); cp.win_run(d.sh, "tile")
    ck(f"Android {sdk} đúng sẵn (cửa sổ có thanh tiêu đề): thu nhỏ 2 tab + sắp xếp → không bật lại lần nào, có đọc lớp hình để kiểm",
       code == 200 and d.ui_kills == 0 and kills(d) == 0 and layers(d) >= 3 and d.drawn_ok(a) and d.drawn_ok(b), (d.ui_kills, layers(d)))
    d = Droid(sdk, ui=False); d.sf_ok = False; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: máy không cho đọc tên lớp hình → KHÔNG bật lại bừa", code == 200 and d.ui_kills == 0 and kills(d) == 0 and layers(d) >= 1, (d.ui_kills, layers(d)))
    d = Droid(sdk, ui=False); d.ui_heal = False; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini"); b = d.open(RZ2); c2, j2 = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: bật lại rồi mà cửa sổ VẪN không có thanh tiêu đề (máy khác kiểu) → chỉ bật lại 1 lần cho mỗi lần mở máy",
       code == 200 and c2 == 200 and d.ui_kills == 1 and kills(d) >= 2, (code, c2, d.ui_kills, kills(d)))
ck("win_decor: có lớp 'Decor container of Task=N' / 'Caption … of Task=N' của tab → True · chỉ có lớp hình của tab → False · không thấy gì → None · lớp của tab KHÁC không tính",
   cp.win_decor(lambda c, t=0: "Task=24#110\nDecor container of Task=24#123\nCaption container of Task=24#124", [({"id": 24}, (0, 0, 1, 1))], lambda s_: None, 1) is True
   and cp.win_decor(lambda c, t=0: "Task=7#3\n  Caption of Task=7", [({"id": 7}, (0, 0, 1, 1))], lambda s_: None, 1) is True
   and cp.win_decor(lambda c, t=0: "Task=24#110\nDecor container of Task=25#123\nDim layer of Task=24#5", [({"id": 24}, (0, 0, 1, 1))], lambda s_: None, 2) is False
   and cp.win_decor(lambda c, t=0: "Task=25#110\nDecor container of Task=25#123", [({"id": 24}, (0, 0, 1, 1))], lambda s_: None, 2) is None
   and cp.win_decor(lambda c, t=0: "", [({"id": 24}, (0, 0, 1, 1))], lambda s_: None, 2) is None)
d = Droid(32, ui=False); a = d.open(RZ1); cp._win_seen_dbg = None
d0 = Droid(32, ui=False); a0 = d0.open(RZ1); d0.in_ok = False; code, j = cp.win_run(d0.sh, "mini")
ck("máy giả: không bật lại thì hình tab đầu nằm ở GÓC MÀN (chỗ lúc còn toàn màn) dù khung tab đã ở ô — đúng lỗi đo trên máy thật",
   code == 200 and a0["b"][1] > 0 and a0["at"][:2] == (0, 0) and not d0.drawn_ok(a0), (a0, j))
ck("máy không cho đọc chỗ thật của hình (dumpsys input trống) → KHÔNG bật lại bừa", d0.ui_kills == 0 and kills(d0) == 0 and reads(d0) >= 1, (d0.ui_kills, reads(d0)))
d = Droid(32); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini"); b = d.open(RZ2); cp.win_run(d.sh, "mini"); cp.win_run(d.sh, "tile")
ck("máy đúng sẵn (giao diện hệ thống khởi động lúc cửa sổ nổi đã bật): thu nhỏ 2 tab + sắp xếp → không bật lại lần nào, có đọc chỗ thật để kiểm",
   code == 200 and d.ui_kills == 0 and kills(d) == 0 and reads(d) >= 3 and d.drawn_ok(a) and d.drawn_ok(b), (d.ui_kills, reads(d)))
for sdk in (32,):
    d = Droid(sdk, ui=False); d.ghost = ("com.roblox.client", cp.win_slot(GP, [])); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: dòng cửa sổ ĐÃ ẨN còn sót trong dumpsys input (nằm đúng ô) không che được lỗi — hình đang hiện lệch thì vẫn bật lại",
       code == 200 and d.ui_kills == 1 and d.drawn_ok(a), (code, j, d.ui_kills, a))
    d = Droid(sdk); d.ghost = ("com.roblox.client", (0, 0, 720, 417)); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: máy đúng sẵn + dòng cửa sổ ẩn ở góc màn → không bật lại", code == 200 and d.ui_kills == 0, (code, j, d.ui_kills))
for sdk in (31, 32, 35):
    d = Droid(sdk, free=False); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    k_set = next((k for k, x in enumerate(d.log) if x.startswith("settings put global enable_freeform_support 1")), -1)
    k_kill = next((k for k, x in enumerate(d.log) if "#kill" in x and x.startswith("B=$(cat")), -1)
    k_start = next((k for k, x in enumerate(d.log) if "--windowingMode 5 " in x), -1)
    ck(f"Android {sdk} CHƯA bật cửa sổ nổi: bật cài đặt → bật lại giao diện hệ thống NGAY (trước khi thu nhỏ) → thu nhỏ, hình đúng ô, chỉ 1 lần bật lại",
       code == 200 and 0 <= k_set < k_kill < k_start and d.ui_kills == 1 and d.drawn_ok(a) and a["mode"] == FF, (code, j, k_set, k_kill, k_start, d.ui_kills))
    ck(f"Android {sdk}: lệnh bật lại lúc vừa bật cửa sổ nổi là lệnh ÉP (không xét dấu đã bật lại)", cp.WIN_UI_KILL_SH.replace("@F@", "1") in d.log, d.log[:6])
d = Droid(30, ui=False); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
ck("Android 11 trở xuống (lõi Android tự đặt chỗ): không đọc dumpsys input, không đụng giao diện hệ thống", code == 200 and reads(d) == 0 and kills(d) == 0, (reads(d), kills(d)))
d = Droid(28, free=False); a = d.open(RZ1, resz=True); code, j = cp.win_run(d.sh, "mini")
ck("Android 9 chưa bật cửa sổ nổi: không bật lại giao diện hệ thống", kills(d) == 0 and d.ui_kills == 0, (code, j))
d = Droid(32, ui=False); d.ui_heal = False; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini"); b = d.open(RZ2); c2, j2 = cp.win_run(d.sh, "mini"); cp.win_run(d.sh, "tile")
ck("máy bật lại rồi mà hình VẪN lệch (lỗi khác): chỉ bật lại 1 lần cho mỗi lần mở máy, các lần bấm sau không bật lại nữa, việc vẫn xong",
   code == 200 and c2 == 200 and d.ui_kills == 1 and kills(d) >= 2 and d.ui_key == d.boot, (code, c2, d.ui_kills, kills(d)))
d.boot = "b00t-2"; d.ui_heal = True; c3, j3 = cp.win_run(d.sh, "tile")
ck("… máy khởi động lại (mã lần mở máy mới) mà hình còn lệch → được bật lại 1 lần nữa", c3 == 200 and d.ui_kills == 2 and d.drawn_ok(a) and d.drawn_ok(b), (c3, d.ui_kills))
d = Droid(32, ui=False); d.ui_root = False; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
ck("không tắt được tiến trình giao diện hệ thống (máy khoá quyền): không treo, thu nhỏ vẫn trả kết quả", code == 200 and a["mode"] == FF and d.ui_kills == 0, (code, j))
d = Droid(32, ui=False); a = d.open(OLD1, land=True, resz=False); code, j = cp.win_run(d.sh, "mini")
k_kill = next((k for k, x in enumerate(d.log) if "#kill" in x and x.startswith("B=$(cat")), -1); k_amkill = next((k for k, x in enumerate(d.log) if x.startswith("am kill ")), -1)
ck("game KIỂU CŨ trên máy lệch chỗ: bật lại giao diện hệ thống TRƯỚC khi mở lại game → game mở lại đúng cỡ, hình đúng ô, fit = ok",
   code == 200 and j.get("fit") == "ok" and 0 <= k_kill < k_amkill and d.ui_kills == 1 and d.fits(a) and d.drawn_ok(a), (code, j, k_kill, k_amkill, a))
d = Droid(32, ui=False); a = d.open(RZ1); cp.win_run(d.sh, "mini"); d.ui = False; a["at"] = (0, 0, a["b"][2] - a["b"][0], a["b"][3] - a["b"][1]); d.ui_key = None
code, j = cp.win_run(d.sh, "grow")
ck("Cửa sổ to hơn trên máy lệch chỗ → cũng kiểm + bật lại 1 lần, hình về đúng khung mới", code == 200 and d.ui_kills == 2 and d.drawn_ok(a) and a["at"] == tuple(j["b"]), (code, j, a))
ck("win_seen: hình nằm lọt TRONG khung (app được Android thu hình / chừa viền) không tính là lệch; nằm ngoài khung thì tính",
   cp.win_seen(lambda c, t=0: "  1: name='ab12 com.a/com.a.M', id=1, visible=true, frame=[40,120][600,435], x", [({"pkg": "com.a"}, (0, 100, 652, 516))], lambda s_: None) is True
   and cp.win_seen(lambda c, t=0: "  1: name='ab12 com.a/com.a.M', id=1, visible=true, frame=[0,0][652,416], x", [({"pkg": "com.a"}, (0, 100, 652, 516))], lambda s_: None) is False
   and cp.win_seen(lambda c, t=0: "", [({"pkg": "com.a"}, (0, 100, 652, 516))], lambda s_: None) is None
   and cp.win_seen(lambda c, t=0: "x", [({"pkg": "com.a; rm -rf /"}, (0, 100, 652, 516))], lambda s_: None) is None)

import subprocess
def ui_sh(force, boot="B1", key="", pid="900", kill_ok=True, su_ok=False):
    lg = os.path.join(home, "ui-log.txt"); open(lg, "w").close()      # ghi việc ra file: đoạn lệnh thật bỏ chữ báo lỗi (2>/dev/null)
    stub = ('L="%s"\ncat() { echo "%s"; }\npidof() { [ -n "%s" ] && echo "%s"; }\n'
            'settings() { if [ "$1" = get ]; then echo "%s"; else echo "PUT $3 $4" >> "$L"; fi; }\n'
            'kill() { echo "KILL $*" >> "$L"; return %d; }\nsu() { echo "SU $*" >> "$L"; return %d; }\nam() { echo "AM $*" >> "$L"; return 0; }\n'
            % (lg, boot, pid, pid, key, 0 if kill_ok else 1, 0 if su_ok else 1))
    r = subprocess.run(["sh", "-c", stub + cp.WIN_UI_KILL_SH.replace("@F@", "1" if force else "0")], capture_output=True, text=True, timeout=20)
    return r.stdout.strip(), open(lg).read() + r.stderr
o, e = ui_sh(False, key="B1")
ck("đoạn lệnh bật lại (chạy thật bằng sh): lần mở máy này đã bật lại rồi → '#done', không tắt gì", o == "#done" and "KILL" not in e and "PUT" not in e, (o, e))
o, e = ui_sh(False, key="B0")
ck("… dấu của lần mở máy TRƯỚC → ghi dấu mới + tắt tiến trình → '#kill <pid>'", o == "#kill 900" and "PUT cb_win_ui B1" in e and "KILL 900" in e and "SU" not in e, (o, e))
o, e = ui_sh(False, key="null")
ck("… chưa có dấu (settings trả null) → tắt", o == "#kill 900" and "PUT cb_win_ui B1" in e, (o, e))
o, e = ui_sh(True, key="B1")
ck("… lệnh ÉP: đã có dấu vẫn tắt", o == "#kill 900" and "KILL 900" in e, (o, e))
o, e = ui_sh(False, pid="")
ck("… không thấy tiến trình giao diện hệ thống → '#none', không ghi dấu", o == "#none" and "PUT" not in e and "KILL" not in e, (o, e))
o, e = ui_sh(False, kill_ok=False, su_ok=True)
ck("… adb không đủ quyền tắt → dùng su -c (máy MuMu)", o == "#kill 900" and "SU -c kill 900" in e and "AM" not in e, (o, e))
o, e = ui_sh(False, kill_ok=False, su_ok=False)
ck("… không có su → thử su 0 rồi am force-stop", o == "#kill 900" and "SU 0 kill 900" in e and "AM force-stop com.android.systemui" in e, (o, e))
o, e = ui_sh(False, boot="", key="")
ck("… máy không cho đọc mã lần mở máy → vẫn tắt, ghi dấu '0'", o == "#kill 900" and "PUT cb_win_ui 0" in e, (o, e))
SAMPLE15 = "      2: name=4f1b2c3 com.termux/com.termux.app.TermuxActivity, id=77, displayId=0, inputConfig=0x0, alpha=1.00, frame=[0,48][640,488], globalScale=1.000000\n"
ck("đọc chỗ thật của hình: bản in kiểu không có dấu nháy quanh tên (Android mới) vẫn đọc được",
   cp.win_frames(lambda c, t=0: SAMPLE15, ["com.termux"]) == {"com.termux": [(0, 48, 640, 488)]}, cp.win_frames(lambda c, t=0: SAMPLE15, ["com.termux"]))
SAMPLE = ("    Windows:\n      0: name='e1 StatusBar', id=1, visible=true, frame=[0,0][720,29], x\n"
          "      4: name='d17d71d com.termux/com.termux.app.TermuxActivity', id=1133, displayId=0, portalToDisplayId=-1, paused=false, focusable=true, "
          "hasWallpaper=false, visible=true, alpha=1.00, flags=NOT_TOUCH_MODAL, type=BASE_APPLICATION, frame=[0,0][720,417], globalScale=1.0, touchableRegion=[-36,-36][756,453]\n"
          "      5: name='f61d20c vn.cloudblue.wintest4/vn.cloudblue.wintest.Main', id=1140, visible=true, alpha=1.00, frame=[0,29][652,445], globalScale=1.0\n"
          "      6: name='23304ae com.termux/com.termux.app.TermuxActivity', id=1100, visible=false, alpha=1.00, frame=[0,493][720,910], globalScale=1.0\n"
          "      7: name='aa01 com.termuxx/com.termuxx.Main', id=1, visible=true, frame=[5,5][9,9], x\n")
def real_sh(c, t=0):
    f = os.path.join(home, "input.txt"); open(f, "w").write(SAMPLE)
    return subprocess.run(["sh", "-c", 'dumpsys() { cat "%s"; }\n' % f + c], capture_output=True, text=True, timeout=20).stdout
fr = cp.win_frames(real_sh, ["com.termux", "vn.cloudblue.wintest4", "bad pkg; id"])
ck("đọc chỗ thật của hình (chạy thật grep trên bản in của máy MuMu Android 12): đúng cửa sổ đang hiện của từng app, bỏ cửa sổ ẩn, bỏ app trùng đầu tên",
   fr == {"com.termux": [(0, 0, 720, 417)], "vn.cloudblue.wintest4": [(0, 29, 652, 445)]}, fr)
ck("… bản in đó = đúng lỗi đo trên máy thật: Termux khung [0,446][720,863] mà hình ở góc màn → lệch; wintest4 đúng chỗ",
   cp.win_seen(real_sh, [({"pkg": "com.termux"}, (0, 446, 720, 863))], lambda s_: None, tries=1) is False
   and cp.win_seen(real_sh, [({"pkg": "vn.cloudblue.wintest4"}, (0, 29, 652, 445))], lambda s_: None, tries=1) is True, fr)

print("4b'. 23/11e lượt 3 · bản in lớp hình của Android 15 thật · thanh tiêu đề chỉ được vẽ khi tab đổi khung · vừa hạ mật độ thì cửa sổ bị đẩy lệch")
A15_OK = ("RequestedLayerState{Task=15#1281 z=1}\nRequestedLayerState{Task=6#71 parentId=1339}\nRequestedLayerState{Task=16#1343 parentId=1344 z=2}\n"
          "RequestedLayerState{Task=1#1339 parentId=1344}\nRequestedLayerState{Task=16#1319 z=2}\nRequestedLayerState{Task=17#1347 parentId=1344 z=1}\n"
          "RequestedLayerState{TaskInputSink of Surface(name=Decor container of Task=16)/@0x8ca0b65#1389 parentId=1385 z=-2}\nRequestedLayerState{Caption of Task=16#1388 parentId=1387}\n"
          "RequestedLayerState{Decor container of Task=16#1385 parentId=1343 z=20000}\nRequestedLayerState{Caption container of Task=16#1386 parentId=1385 z=-1}\n"
          "RequestedLayerState{Caption of Task=16Leash#1387 parentId=1386}\n")
A15_BAD = ("RequestedLayerState{Task=6#71 parentId=1397}\nRequestedLayerState{Task=1#1397 parentId=1401}\nRequestedLayerState{Task=20#1404 parentId=1401 z=1}\n"
           "RequestedLayerState{Task=21#1405 parentId=1404}\nRequestedLayerState{Task=22#1406 parentId=1404 z=1}\nRequestedLayerState{Task=23#1440 parentId=1401 z=2}\n")
nosl = lambda s_: None
ck("bản in THẬT của máy ảo Android 15 (RequestedLayerState{…}): cửa sổ có thanh tiêu đề → đọc ra đúng tab 16; tab 1 / 6 không bị nhận nhầm",
   cp.win_decor_ids(lambda c, t=0: A15_OK, {16, 1, 6}) == ({16, 1, 6}, {16}) and cp.win_decor(lambda c, t=0: A15_OK, [({"id": 16}, (0, 0, 1, 1))], nosl, 1) is True
   and cp.win_decor(lambda c, t=0: A15_OK, [({"id": 1}, (0, 0, 1, 1))], nosl, 1) is False, cp.win_decor_ids(lambda c, t=0: A15_OK, {16, 1, 6}))
ck("… bản in lúc giao diện hệ thống chạy từ trước khi bật cửa sổ nổi (tab 23 không có lớp thanh tiêu đề) → False; tab không có trong bản in → None",
   cp.win_decor(lambda c, t=0: A15_BAD, [({"id": 23}, (0, 0, 1, 1))], nosl, 2) is False and cp.win_decor(lambda c, t=0: A15_BAD, [({"id": 2}, (0, 0, 1, 1))], nosl, 2) is None
   and cp.win_decor(lambda c, t=0: A15_BAD, [({"id": 3}, (0, 0, 1, 1))], nosl, 2) is None, cp.win_decor_ids(lambda c, t=0: A15_BAD, {23, 2, 3}))
nudges = lambda d, t: len([x for x in d.log if re.match(rf"am task resize {t['id']} ", x)])
for sdk in (33, 35):
    d = Droid(sdk, ui=False); d.decor_move = True; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    k_kill = next((k for k, x in enumerate(d.log) if "#kill" in x and x.startswith("B=$(cat")), -1)
    after = [x for x in d.log[k_kill + 1:] if x.startswith(f"am task resize {a['id']} ")]
    ck(f"Android {sdk}: bật lại giao diện hệ thống xong, cửa sổ đang có CHƯA được vẽ thanh tiêu đề (chỉ vẽ lúc tab đổi) → dời tab 1 px rồi trả lại → có thanh tiêu đề, khung đúng như đã báo",
       code == 200 and d.ui_kills == 1 and d.drawn_ok(a) and tuple(a["b"]) == tuple(j["b"]) and len(after) == 2
       and after[1] == "am task resize %d %d %d %d %d 2>&1" % ((a["id"],) + tuple(j["b"])), (code, j, a, after, d.ui_kills))
    b = d.open(RZ2); code, j = cp.win_run(d.sh, "mini"); n_a = nudges(d, a)
    ck(f"Android {sdk}: tab thứ 2 → không bật lại, không dời thừa tab đầu, cả 2 có thanh tiêu đề", code == 200 and d.ui_kills == 1 and d.drawn_ok(a) and d.drawn_ok(b), (code, j, d.ui_kills))
    d = Droid(sdk, ui=False); a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini")
    k_kill = next((k for k, x in enumerate(d.log) if "#kill" in x and x.startswith("B=$(cat")), -1)
    ck(f"Android {sdk}: máy tự vẽ lại thanh tiêu đề ngay khi giao diện hệ thống lên → KHÔNG dời tab thừa",
       code == 200 and d.ui_kills == 1 and d.drawn_ok(a) and not [x for x in d.log[k_kill + 1:] if x.startswith(f"am task resize {a['id']} ")], (code, j))
    d = Droid(sdk, ui=False); d.decor_move = "front"; a = d.open(RZ1); cp.win_run(d.sh, "mini"); b = d.open(RZ2); cp.win_run(d.sh, "mini")
    d.ui = False; d.ui_key = None; n0 = len(d.log); z0 = [x["id"] for x in d.z]; ba, bb = tuple(a["b"]), tuple(b["b"]); code, j = cp.win_run(d.sh, "tile")
    homes = [k for k, x in enumerate(d.log) if k >= n0 and x.startswith("input keyevent 3")]
    ck(f"Android {sdk}: máy chỉ vẽ thanh tiêu đề lúc tab LÊN TRÊN (dời 1 px không ăn) → về màn chính rồi đưa các cửa sổ nổi lên lại: đủ thanh tiêu đề, "
       "đúng thứ tự trên dưới + đúng ô đã xếp",
       code == 200 and d.ui_kills == 2 and len(homes) == 1 and d.drawn_ok(a) and d.drawn_ok(b) and [x["id"] for x in d.z if x["mode"] == FF] == [i for i in z0 if i in (a["id"], b["id"])]
       and d.visible(a) and d.visible(b) and ovl(a["b"], b["b"]) == 0, (code, j, d.ui_kills, homes, [x["id"] for x in d.z], z0, a["b"], b["b"]))
    d = Droid(sdk); d.decor_move = True; a = d.open(RZ1); cp.win_run(d.sh, "mini"); d.ui_key = d.boot; a["nodecor"] = True; n0 = nudges(d, a)
    code, j = cp.win_run(d.sh, "grow"); 
    ck(f"Android {sdk}: lần mở máy này ĐÃ bật lại giao diện hệ thống mà tab vẫn thiếu thanh tiêu đề → không bật lại nữa, chỉ dời tab → có thanh tiêu đề",
       code == 200 and d.ui_kills == 0 and d.drawn_ok(a) and tuple(a["b"]) == tuple(j["b"]), (code, j, a, d.ui_kills))
    d = Droid(sdk); a = d.open(RZ1); cp.win_run(d.sh, "mini"); b = d.open(RZ2, land=True)        # app toàn màn che tab nhỏ → Android gỡ thanh tiêu đề của tab bị che
    r = cp.win_ui_fix(d.sh, sdk, [(dict(a, pkg="com.roblox.client"), a["b"])], nosl)
    ck(f"Android {sdk}: tab nhỏ đang bị app toàn màn che (Android không vẽ thanh tiêu đề cho tab bị che) → không coi là lỗi, không bật lại", r is False and d.ui_kills == 0 and kills(d) == 0, (r, d.ui_kills))
    d = Droid(sdk, ui=False); d.decor_never = True; memo = {}; a = d.open(RZ1); code, j = cp.win_run(d.sh, "mini", memo=memo); l1, k1 = layers(d), d.ui_kills
    b = d.open(RZ2); c2, j2 = cp.win_run(d.sh, "mini", memo=memo); l2 = layers(d); c3, j3 = cp.win_run(d.sh, "tile", memo=memo)
    ck(f"Android {sdk}: bản Android KHÔNG vẽ thanh tiêu đề (bật lại + dời vẫn không có) → bật lại đúng 1 lần, ghi nhớ; các lượt sau không đọc lớp hình / không dời / không chờ nữa",
       code == 200 and c2 == 200 and c3 == 200 and k1 == 1 and d.ui_kills == 1 and bool(memo.get("off")) and l2 == l1 and layers(d) == l1, (code, c2, c3, k1, d.ui_kills, memo, l1, l2, layers(d)))
    memo["off"] = time.time() - cp.WIN_MEMO_OFF - 5; c4, j4 = cp.win_run(d.sh, "tile", memo=memo)
    ck(f"Android {sdk}: … hết 30 phút → thử lại (đọc lớp hình), vẫn không bật lại giao diện hệ thống lần 2 trong cùng lần mở máy", c4 == 200 and layers(d) > l1 and d.ui_kills == 1, (c4, layers(d), l1, d.ui_kills))
# vừa hạ mật độ: thanh trạng thái cũ còn đó → cửa sổ bị đẩy lệch và Android bỏ qua lệnh đặt lại y hệt
for sdk in (31, 32):
    d = Droid(sdk); d.insetlag = 14; a = d.open(OLD1, land=True, resz=False); code, j = cp.win_run(d.sh, "mini")
    k_d = next((k for k, x in enumerate(d.log) if re.search(r"wm density \d+(;|$)", x)), -1)
    ck(f"Android {sdk}: game kiểu cũ → máy tự bật màn rộng (hạ mật độ) → cửa sổ bị Android đẩy xuống dưới thanh trạng thái CŨ; cpapi dời 1 px rồi đặt lại tới khi "
       f"khung THẬT = khung đã báo ({j.get('b')}), game chỉ được mở lại 1 lần, vừa khung",
       code == 200 and j.get("fit") == "ok" and j.get("sw") and k_d > 0 and tuple(a["b"]) == tuple(j["b"]) and a["starts"] == 2 and d.fits(a) and d._stale is None
       and any(x == "am task resize %d %d %d %d %d 2>&1" % (a["id"], j["b"][0], j["b"][1] + 1, j["b"][2], j["b"][3] + 1) for x in d.log), (code, j, a, d._stale))
    d = Droid(sdk); d.insetlag = 500; a = d.open(OLD1, land=True, resz=False); n0 = len(d.log); code, j = cp.win_run(d.sh, "mini")
    ck(f"Android {sdk}: thanh trạng thái KHÔNG bao giờ dựng lại (máy lạ) → thử có hạn (≤ 7 lượt dời) rồi thôi, việc vẫn xong, game vẫn vừa khung",
       code == 200 and j.get("fit") == "ok" and d.fits(a) and tuple(a["b"])[1] > j["b"][1] and (a["b"][2] - a["b"][0], a["b"][3] - a["b"][1]) == (j["b"][2] - j["b"][0], j["b"][3] - j["b"][1])
       and len([x for x in d.log if re.fullmatch(rf"am task resize {a['id']} \d+ \d+ \d+ \d+ 2>&1", x)
                and x.split()[5] == str(j["b"][1] + 1)]) == 7, (code, j, a, len(d.log) - n0))
d = Droid(32); a = d.open(OLD1, land=True, resz=False); code, j = cp.win_run(d.sh, "mini")
ck("máy không lệch (khung thật = khung muốn ngay): không có lệnh dời 1 px nào", code == 200 and tuple(a["b"]) == tuple(j["b"])
   and not any(x == "am task resize %d %d %d %d %d 2>&1" % (a["id"], j["b"][0], j["b"][1] + 1, j["b"][2], j["b"][3] + 1) for x in d.log), (code, j, a))
tk = {"id": 5, "b": (0, 26, 640, 431)}
fake = lambda bb: (lambda c, t=0: (LOGP.append(c) or "") if c.startswith("am task resize") else
                   f"RootTask id=5 bounds=[{bb[0]},{bb[1]}][{bb[2]},{bb[3]}] displayId=0 userId=0\n configuration={{ mWindowingMode=freeform mActivityType=standard}}\n"
                   f"  taskId=5: a.b/a.b.M bounds=[{bb[0]},{bb[1]}][{bb[2]},{bb[3]}] userId=0 visible=true")
LOGP = []; r1 = cp.win_put(fake((0, 26, 640, 431)), [tk], 32, nosl); n1 = len(LOGP)
LOGP = []; r2 = cp.win_put(fake((0, 48, 640, 488)), [tk], 32, nosl); n2 = len(LOGP)           # Android ép cỡ khác (không phải lệch chỗ) → không dời
LOGP = []; r3 = cp.win_put(fake((0, 48, 640, 453)), [tk], 32, nosl, tries=3); n3 = len(LOGP)  # lệch chỗ, đúng cỡ, không bao giờ về → 3 lượt × 2 lệnh rồi thôi
ck("win_put: đúng khung → True, không lệnh nào · lệch CỠ → không dời (không phải lỗi này) · lệch chỗ mãi → dời có hạn rồi trả False",
   (r1, n1) == (True, 0) and (r2, n2) == (True, 0) and (r3, n3) == (False, 6), (r1, n1, r2, n2, r3, n3))

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
