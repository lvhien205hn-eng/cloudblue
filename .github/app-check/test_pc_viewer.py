# Thử nhanh phần chế độ máy PC của cửa sổ máy (bluepc.Viewer._input) bằng pygame GIẢ — không cần màn hình
import os, sys, types, tempfile
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # máy Windows CI dùng cp1252
except Exception: pass
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1])
import bluepc as B
OK = FAIL = 0
def ck(n, c, x=""):
    global OK, FAIL
    if c: OK += 1; print("  ✓", n)
    else: FAIL += 1; print("  ✗", n, "→", x)
pg = types.SimpleNamespace(MOUSEMOTION=1, MOUSEBUTTONDOWN=2, MOUSEBUTTONUP=3, MOUSEWHEEL=4, TEXTINPUT=5, KEYDOWN=6, KEYUP=7, WINDOWFOCUSGAINED=8, WINDOWFOCUSLOST=9,
                           KMOD_CTRL=64, KMOD_SHIFT=1, KMOD_ALT=256, K_F11=1073741892, K_F10=1073741891, K_F5=1073741886, K_F3=1073741884, K_r=114, K_u=117, K_k=107, K_v=118,
                           K_a=97, K_b=98, K_1=49, K_LSHIFT=1073742049, K_LCTRL=1073742048, K_LALT=1073742050, K_ESCAPE=27, K_TAB=9, K_F1=1073741882, K_F12=1073741893,
                           K_RETURN=13, K_SPACE=32, K_KP_ENTER=1073741912, K_LGUI=1073742051)
for i in range(26): setattr(pg, "K_" + chr(97 + i), 97 + i)
for i in range(10): setattr(pg, "K_%d" % i, 48 + i)
for i in range(1, 13): setattr(pg, "K_F%d" % i, 1073741881 + i)
mods = [0]
pg.key = types.SimpleNamespace(get_mods=lambda: mods[0], name=lambda k: "")
pg.mouse = types.SimpleNamespace(get_pos=lambda: (100, 100))
class FakeCli:
    def __init__(self): self.ev = []
    def mouse(self, a, b, x, y): self.ev.append(("m", a, b, round(x, 2), round(y, 2)))
    def key(self, a, code, meta=0): self.ev.append(("k", a, code, meta))
    def text(self, s): self.ev.append(("t", s))
    def cmd(self, n): self.ev.append(("c", n))
    def touch(self, *a): self.ev.append(("touch",) + a)
    def scroll(self, *a): self.ev.append(("s",) + a)
    def clip_set(self, t, p=True): self.ev.append(("clip", t))
    def quality(self, q, fps=None, kbps=None, fpsx=None): self.ev.append(("q", q, fpsx))
v = B.Viewer("22222222-2222-4222-8222-222222222222", None, pc=True)
cli = FakeCli()
v._cx = lambda: cli; v._tool_at = lambda pos: None; v._norm = lambda pos: (0.25, 0.5); v._clamp = lambda pos: (0.25, 0.5)
v.state = ("connected", ""); v.docked = False; v.notice_rect = None; v.notice = None
E = lambda **k: types.SimpleNamespace(**k)
import time
v._input(E(type=1, pos=(10, 10)), pg); time.sleep(0.01)
v._input(E(type=2, pos=(10, 10), button=1), pg); v._input(E(type=3, pos=(10, 10), button=1), pg)
v._input(E(type=2, pos=(10, 10), button=3), pg); v._input(E(type=3, pos=(10, 10), button=3), pg)
v._input(E(type=2, pos=(10, 10), button=2), pg); v._input(E(type=3, pos=(10, 10), button=2), pg)
ck("rê chuột + trái / phải / giữa → C_MOUSE đúng nút, nhấn + nhả", cli.ev == [("m", 0, 0, 0.25, 0.5), ("m", 1, 0, 0.25, 0.5), ("m", 2, 0, 0.25, 0.5), ("m", 1, 1, 0.25, 0.5), ("m", 2, 1, 0.25, 0.5),
                                                                        ("m", 1, 2, 0.25, 0.5), ("m", 2, 2, 0.25, 0.5)], cli.ev)
ck("máy PC: không gửi chạm (touch) và không biến chuột phải thành Back", not any(e[0] in ("touch", "c") for e in cli.ev))
cli.ev.clear()
for k in (pg.K_LCTRL, pg.K_LSHIFT, pg.K_ESCAPE): v._input(E(type=6, key=k), pg)
for k in (pg.K_ESCAPE, pg.K_LSHIFT, pg.K_LCTRL): v._input(E(type=7, key=k), pg)
v._input(E(type=6, key=pg.K_F5), pg); v._input(E(type=7, key=pg.K_F5), pg)
v._input(E(type=6, key=pg.K_a), pg); v._input(E(type=5, text="a"), pg); v._input(E(type=7, key=pg.K_a), pg)
v._input(E(type=5, text="ế"), pg)
ck("phím thật: Ctrl+Shift+Esc, F5 (không bị app giữ để tải lại hình), chữ a không gửi 2 lần, chữ có dấu gửi bằng TEXT",
   cli.ev == [("k", 0, 113, 0), ("k", 0, 59, 0), ("k", 0, 111, 0), ("k", 1, 111, 0), ("k", 1, 59, 0), ("k", 1, 113, 0), ("k", 0, 135, 0), ("k", 1, 135, 0),
              ("k", 0, 29, 0), ("k", 1, 29, 0), ("t", "ế")], cli.ev)
cli.ev.clear()
v._input(E(type=7, key=pg.K_b), pg)
ck("nhả phím chưa từng nhấn (nhấn lúc cửa sổ khác đang được chọn) → bỏ qua", cli.ev == [], cli.ev)
mods[0] = pg.KMOD_CTRL
B.clip_get = lambda: "chu dan"
v._input(E(type=6, key=pg.K_v), pg); mods[0] = 0
ck("Ctrl+V → dán chữ của máy mình sang máy PC", cli.ev == [("clip", "chu dan")], cli.ev)
cli.ev.clear()
v._input(E(type=6, key=pg.K_LSHIFT), pg); v._input(E(type=2, pos=(1, 1), button=1), pg)
v._input(E(type=9), pg)
ck("mất tiêu điểm khi đang giữ Shift + chuột trái → nhả hết", ("k", 1, 59, 0) in cli.ev and ("m", 2, 0, 0.5, 0.5) in cli.ev and not v.pc_keys and not v.pc_down, cli.ev)
cli.ev.clear()
for n in ("win", "alttab", "taskmgr", "back", "recents"): v._tool(n, pg)
ck("thanh công cụ máy PC: Windows / Alt+Tab / Task Manager / Esc / Win+Tab", cli.ev == [("c", "win"), ("c", "alttab"), ("c", "taskmgr"), ("c", "back"), ("c", "recents")], cli.ev)
ck("thanh công cụ máy PC không có nút Android (xoay, chụp, công cụ APK)", [n for n, _, _ in v._tool_rects(1280, 800)] == [n for n, _ in B.PC_TOOLS]
   and not {"rotate", "shot", "tools", "home"} & {n for n, _ in B.PC_TOOLS})
v2 = B.Viewer("33333333-3333-4333-8333-333333333333", None)
cli2 = FakeCli(); v2._cx = lambda: cli2; v2._tool_at = lambda pos: None; v2._norm = lambda pos: (0.5, 0.5); v2._clamp = lambda pos: (0.5, 0.5); v2.state = ("connected", ""); v2.docked = False
v2._input(E(type=2, pos=(1, 1), button=3), pg); v2._input(E(type=2, pos=(1, 1), button=1), pg)
ck("điện thoại đám mây (không --pc): chuột phải vẫn là Back, chuột trái vẫn là chạm như cũ", cli2.ev[0] == ("c", "back") and cli2.ev[1][0] == "touch" and not v2.pc, cli2.ev)
# ---- 21.11k: máy PC — Siêu nét + khách tự chọn khung hình/giây · đồng bộ chuột giữa các máy PC
cli.ev.clear(); v.q = "auto"; v.fpsx = 0; v._say = lambda *a, **k: None
v._tool("quality", pg); v._tool("quality", pg)
ck("máy PC: nút Chất lượng có Siêu nét (Tự động → Siêu nét → Nét …), nhớ riêng cho máy PC", [e[1] for e in cli.ev] == ["uhd", "hd"] and B.prefs().get("pcq") == "hd"
   and [k for k, _ in B.PC_QUALITIES] == ["auto", "uhd", "hd", "bal", "eco"], (cli.ev, B.prefs().get("pcq")))
cli.ev.clear()
for _ in range(4): v._tool("fps", pg)
ck("máy PC: nút FPS → Mặc định → 30 → 60 → 120 → Mặc định, mỗi lần gửi kèm fpsx, nhớ lựa chọn", [e[2] for e in cli.ev] == [30, 60, 120, 0] and B.prefs().get("pcf") == 0
   and "fps" in [n for n, _ in B.PC_TOOLS], cli.ev)
v2.q = "auto"; cli2.ev.clear(); v2._tool("quality", pg)
ck("điện thoại đám mây: nút Chất lượng như cũ (không có Siêu nét 2K, không gửi fpsx)", cli2.ev == [("q", "hd", None)] and B.prefs().get("q") == "hd", cli2.ev)
import struct
sl = B.SyLink.__new__(B.SyLink); sl.pc = True; sl.mdown = {}; sl.down = {}; sl.txt = {}
c3 = FakeCli()
sl._apply("t1", c3, B.SY_MOUSE, 0, 0, struct.pack("<HH", 32768, 16384)); sl._apply("t1", c3, B.SY_MOUSE, 1, 0, struct.pack("<HH", 32768, 16384))
sl._apply("t1", c3, B.SY_MOUSE, 2, 0, struct.pack("<HH", 32768, 16384)); sl._apply("t1", c3, B.SY_MOUSE, 2, 1, struct.pack("<HH", 1, 1))
sl._apply("t1", c3, B.SY_MOUSE, 1, 1, struct.pack("<HH", 0, 65535)); sl._release("t1", c3)
ck("đồng bộ chuột máy PC: rê / nhấn / nhả theo máy bạn; nhả nút chưa nhấn thì bỏ; máy bạn rời nhóm → nhả hộ nút đang giữ",
   c3.ev == [("m", 0, 0, 0.5, 0.25), ("m", 1, 0, 0.5, 0.25), ("m", 2, 0, 0.5, 0.25), ("m", 1, 1, 0.0, 1.0), ("m", 2, 1, 0.0, 1.0)], c3.ev)
sl.pc = False; c4 = FakeCli(); sl._apply("t1", c4, B.SY_MOUSE, 1, 0, struct.pack("<HH", 1, 1))
ck("cửa sổ điện thoại đám mây KHÔNG làm theo chuột máy PC", c4.ev == [], c4.ev)
class _S:
    def __init__(self): self.ev = []
    def mouse(self, *a): self.ev.append(a)
sy = _S(); c5 = FakeCli(); tee = B._SyTee(c5, sy); tee.mouse(1, 0, 0.5, 0.5)
ck("đang đồng bộ: chuột của máy PC đang thao tác vừa gửi cho máy này vừa ghi cho các máy bạn", c5.ev == [("m", 1, 0, 0.5, 0.5)] and sy.ev == [(1, 0, 0.5, 0.5)], (c5.ev, sy.ev))
print(f"\n{OK}/{OK + FAIL} đạt"); sys.exit(1 if FAIL else 0)
