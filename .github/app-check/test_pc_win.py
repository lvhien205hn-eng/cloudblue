# -*- coding: utf-8 -*-
"""23/11 · 🗗 TAB CỬA SỔ NHỎ trong app PC (bluepc.py) — thử bằng pygame / Tk GIẢ (chạy được cả máy không có màn hình / tkinter):
   thanh công cụ cửa sổ máy có Thu nhỏ tab + Sắp xếp tab (máy PC thì không), bấm → POST /cpapi/<máy>/win {do}, hiện câu máy chủ,
   máy chủ cũ (404) → câu dễ hiểu, vẽ được biểu tượng mới, thẻ Màn hình của Công cụ có mục Tab cửa sổ nhỏ (4 nút: + 23/11b Mở lại vừa khung), bản tiếng Anh dịch đủ.
   Chạy:  python test_pc_win.py <thư mục pc-client>"""
import json, os, sys, tempfile, threading, time, types
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
d = tempfile.mkdtemp(); os.environ["APPDATA"] = d; os.environ["HOME"] = d
os.makedirs(os.path.join(d, "BlueRobloxPC"), exist_ok=True)
with open(os.path.join(d, "BlueRobloxPC", "settings.json"), "w", encoding="utf-8") as _f: json.dump({"lang": "vi"}, _f)   # chữ tiếng Việt (máy CI Windows tiếng Anh)
sys.path.insert(0, sys.argv[1])
import bluepc as B
import bluepc_en as EN

OK = [0, 0]


def ck(n, c, x=""):
    OK[1] += 1
    if c: OK[0] += 1; print("  ✓", n)
    else: print("  ✗", n, "→", str(x)[:500])


class Cp:
    def __init__(self): self.calls = []; self.mode = "ok"
    def json(self, method, path, body=None, timeout=120):
        self.calls.append((method, path, body))
        if self.mode == "old": raise B.ApiError(404, "Không có chức năng này.")
        if self.mode == "err": raise B.ApiError(409, "Chưa có app nào đang mở toàn màn — mở app (VD Roblox) rồi bấm Thu nhỏ tab.")
        return {"ok": True, "n": 2, "msg": {"mini": "Đã thu nhỏ Roblox (2 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ.",
                                            "tile": "Đã xếp 2 tab nhỏ (1 cột × 2 hàng).", "full": "Đã phóng to Roblox ra toàn màn."}[body["do"]]}


def wait(fn, t=3.0):
    end = time.time() + t
    while time.time() < end:
        if fn(): return True
        time.sleep(0.02)
    return fn()


# ---------------- 1. thanh công cụ cửa sổ máy ----------------
names = [n for n, _ in B.TOOLS]
ck("cửa sổ Cloud Phone: thanh công cụ có Thu nhỏ tab + Sắp xếp tab (ngay sau Xoay)", names[names.index("rotate") + 1:names.index("rotate") + 3] == ["winmini", "wintile"]
   and dict(B.TOOLS)["winmini"] == "Thu nhỏ tab" and dict(B.TOOLS)["wintile"] == "Sắp xếp tab", names)
ck("cửa sổ máy PC (VPS GPU): KHÔNG có nút tab cửa sổ nhỏ", not {"winmini", "wintile"} & {n for n, _ in B.PC_TOOLS})
v = B.Viewer("33333333-3333-4333-8333-333333333333", None)
cp = Cp(); said = []
v._cp = lambda: cp; v._say = lambda t, secs=3.0, action=None: said.append(t)
pg = types.SimpleNamespace()
v._tool("winmini", pg)
ck("bấm Thu nhỏ tab → POST win {do: mini} + hiện câu máy chủ", wait(lambda: len(said) >= 2) and cp.calls == [("POST", "win", {"do": "mini"})]
   and said[0] == "Đang thu nhỏ tab…" and said[-1].startswith("Đã thu nhỏ Roblox (2 tab nhỏ)"), (cp.calls, said))
said.clear(); v._tool("wintile", pg)
ck("bấm Sắp xếp tab → POST win {do: tile}", wait(lambda: len(said) >= 2) and cp.calls[-1] == ("POST", "win", {"do": "tile"}) and "Đã xếp 2 tab nhỏ" in said[-1], said)
said.clear(); cp.mode = "old"; v._tool("winmini", pg)
ck("máy chủ cũ (404) → 'Máy chủ của máy này chưa có tính năng này'", wait(lambda: len(said) >= 2) and "chưa có tính năng này" in said[-1], said)
said.clear(); cp.mode = "err"; v._tool("winmini", pg)
ck("lỗi máy chủ (409) → hiện đúng câu", wait(lambda: len(said) >= 2) and said[-1].startswith("Chưa có app nào đang mở toàn màn"), said)
vp = B.Viewer("44444444-4444-4444-8444-444444444444", None, pc=True); cpp = Cp(); vp._cp = lambda: cpp; vp._say = lambda *a, **k: None
vp._win("mini"); time.sleep(0.2)
ck("máy PC: _win không gửi gì", not cpp.calls, cpp.calls)

# ---------------- 2. vẽ biểu tượng (pygame giả) ----------------
drawn = []
class Draw:
    def __getattr__(self, n): return lambda *a, **k: drawn.append(n)
class Font:
    def render(self, *a, **k): return types.SimpleNamespace(get_rect=lambda **k: (0, 0, 1, 1))
class Surf:
    def blit(self, *a, **k): pass
pgd = types.SimpleNamespace(draw=Draw())
v.bar_on = True; v.hover = None; v.font_s = Font(); v.q = "auto"; v.fpsx = 0
try:
    v._draw_bar(pgd, Surf(), 1280, 800); err = None
except Exception as e: err = repr(e)
rects = [n for n, _, _ in v._tool_rects(1280, 800)]
ck("vẽ thanh công cụ có 2 nút mới, không lỗi, nút vẫn đủ cao để có chữ (720 px)", err is None and "winmini" in rects and "wintile" in rects
   and all(r[3] >= 38 for _, _, r in v._tool_rects(1280, 720)), (err, rects))

# ---------------- 3. Công cụ › Màn hình ----------------
src = open(os.path.join(sys.argv[1], "bluepc.py"), encoding="utf-8").read()
ck("Công cụ › Màn hình: mục 'Tab cửa sổ nhỏ' + 3 nút Thu nhỏ / Sắp xếp / Phóng to tab (gửi win)", 'self.section("Tab cửa sổ nhỏ", parent=pg)' in src
   and all(f'self.app.btn(r, "{t}", lambda: self.win("{w}")' in src for t, w in (("Thu nhỏ tab", "mini"), ("Sắp xếp tab", "tile"), ("Phóng to tab", "full")))
   and 'self.cp.json("POST", "win", {"do": what}' in src)
ck("menu Khác ▾ mở thẳng thẻ Màn hình có Tab cửa sổ nhỏ", '("Tab cửa sổ nhỏ · Xoay màn · Độ rộng nhỏ nhất…", "screen")' in src)
ck("23/11b · nút Mở lại vừa khung: hỏi trước (game khởi động lại) rồi gửi win {do: refit}", 'self.app.btn(r, "Mở lại vừa khung", self.win_refit' in src
   and 'mb.askyesno("Mở lại vừa khung"' in src and 'self.win("refit")' in src and '"refit": "Đang mở lại game trong cửa sổ…"' in src)

# ---------------- 4. tiếng Anh ----------------
for vi, en in (("Thu nhỏ tab", "Minimize tab"), ("Sắp xếp tab", "Arrange tabs"), ("Phóng to tab", "Maximize tab"), ("Tab cửa sổ nhỏ", "Small tab windows"),
               ("Đang thu nhỏ tab…", "Minimizing the tab…"), ("Mở lại vừa khung", "Refit to window"), ("Đang mở lại game trong cửa sổ…", "Reopening the game in its window…")):
    ck(f"English: '{vi}' → '{en}'", EN.tr(vi) == en, EN.tr(vi))
for vi, want in (("Đã thu nhỏ Roblox (2 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ.", "Minimized Roblox (2 small tabs)."),
                 ("Đã thu nhỏ Roblox (bản clone) (3 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ.", "Minimized Roblox (clone) (3 small tabs)."),
                 ("Đã xếp 4 tab nhỏ (1 cột × 4 hàng). Màn nhỏ nên tab chồng nhau — tăng 📐 Độ rộng nhỏ nhất (VD 600 dp) để tab không đè nhau.", "Arranged 4 small tabs (1 × 4)."),
                 ("Đã phóng to Roblox hết màn. Muốn toàn màn như cũ: bấm nút ▭ trên thanh tiêu đề cửa sổ.", "Roblox now fills the screen."),
                 ("Các tab đang là cửa sổ nhỏ rồi — mở thêm tab khác (VD bản clone) rồi bấm Thu nhỏ tab.", "Your tabs are already small windows"),
                 ("Đã mở lại Roblox ngay trong cửa sổ — game vẽ vừa khung (game vừa khởi động lại, vào lại trận nếu cần).", "Reopened Roblox inside its window — the game now fits"),
                 ("Chưa mở lại được Roblox trong cửa sổ — thử lại, hoặc mở app rồi bấm Thu nhỏ tab.", "Couldn't reopen Roblox in its window")):
    got = EN.tr(vi)
    ck(f"English câu máy chủ: …{want[:40]}", want in got and not EN.has_vi(got), got)
print("%d/%d dat" % (OK[0], OK[1])); sys.exit(0 if OK[0] == OK[1] else 1)
