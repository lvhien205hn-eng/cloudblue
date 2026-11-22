# -*- coding: utf-8 -*-
"""22/11 · ⊟ DẢI THU NHỎ của app PC (MiniStrip) — thử logic bằng Tk GIẢ (chạy được cả máy không có tkinter): dựng ô, phiên xem trước,
   dán hình, máy đang mở bên phải thì tạm dừng, bấm ô mở máy, đổi cỡ, thu gọn tắt hình, bỏ ô, máy vắng > 2 phút tự bỏ, trang huỷ thì đóng phiên.
   Chạy:  python test_pc_mini.py <thư mục pc-client>"""
import os, sys, json, tempfile, time
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
d = tempfile.mkdtemp(); os.environ["APPDATA"] = d; os.environ["HOME"] = d
os.makedirs(os.path.join(d, "BlueRobloxPC"), exist_ok=True)
with open(os.path.join(d, "BlueRobloxPC", "settings.json"), "w", encoding="utf-8") as _f: json.dump({"lang": "vi"}, _f)   # chữ tiếng Việt (máy CI Windows tiếng Anh)
sys.path.insert(0, sys.argv[1])
import bluepc as B

class W:
    n = 0
    def __init__(self, master=None, **kw):
        W.n += 1; self.master = master; self.kw = dict(kw); self.kids = []; self.alive = True; self.binds = {}; self.mgr = None; self.after_q = []
        if master is not None and hasattr(master, "kids"): master.kids.append(self)
        self._name = ".w%d" % W.n
    def __str__(self): return self._name
    def pack(self, **k): self.mgr = "pack"
    def grid(self, **k): self.mgr = "grid"
    def place(self, **k): self.mgr = "place"
    def place_forget(self): self.mgr = None
    def pack_forget(self): self.mgr = None
    def pack_propagate(self, v): pass
    def bind(self, ev, fn, add=None): self.binds.setdefault(ev, []).append(fn)
    def winfo_children(self): return [k for k in self.kids if k.alive]
    def destroy(self):
        self.alive = False
        for k in self.kids: k.destroy()
    def winfo_exists(self): return self.alive
    def winfo_viewable(self): return True
    def winfo_ismapped(self): return True
    def after(self, ms, fn=None): ROOT.after_q.append((ms, fn)); return "after#%d" % len(ROOT.after_q)
    def config(self, **k): self.kw.update(k)
    configure = config
    def cget(self, k): return self.kw.get(k, "")
    def tkraise(self): pass
    def winfo_x(self): return 0
    def winfo_reqwidth(self): return 900
    def winfo_reqheight(self): return 230
    def create_window(self, *a, **k): return 1
    def bbox(self, *a): return (0, 0, 900, 230)
    def xview_moveto(self, f): self.kw["xview"] = f
    def xview_scroll(self, n, what): pass
    def update_idletasks(self): pass

class Img:
    def __init__(self, master=None): self.data = None
    def configure(self, data=None, format=None): self.data = (len(data), format)

class FakeTk:
    Frame = Label = Canvas = Scrollbar = W
    PhotoImage = Img
    dp = 1.0
    @staticmethod
    def px(n): return int(n)

ROOT = W(); ROOT.after_q = []
class App:
    tk = FakeTk(); root = ROOT; hscrollers = {}
    class auth: uid = "u-test"
    def __init__(self): self.opened = []; self.docked = set(); self.rows_last = None; self.vps_last = None; self.prof = {"role": "user"}
    def btn(self, parent, text, cmd, kind="primary", **kw): b = W(parent, text=text); b.cmd = cmd; return b
    def docked_pids(self): return set(self.docked)
    def open_machine(self, pid, pc=False): self.opened.append((pid, pc))

B.ppm_ok = lambda root: True
B.LiveTile._start = lambda self, g: None
B.PcTile._start = lambda self, g: None
app = App()
P1, P2, P3, PC = "aaaaaaaa-1111-4111-8111-111111111111", "bbbbbbbb-2222-4222-8222-222222222222", "cccccccc-3333-4333-8333-333333333333", "dddddddd-4444-4444-8444-444444444444"
B.minis_set(app, [{"id": P1, "pc": 0, "n": "Núi I", "w": 1280, "h": 720}, {"id": P2, "pc": 0, "n": "Núi II", "w": 720, "h": 1280},
                  {"id": PC, "pc": 1, "n": "139", "w": 1920, "h": 1080}, {"id": P3, "pc": 0, "n": "Hết hạn"}])
slot = W(ROOT)
ok = {}
ms = B.MiniStrip(app, slot)
ok["truoc khi tai danh sach: 4 o 'Dang tai', 0 phien"] = len(ms.cells) == 4 and not ms.tiles
FUT = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 86400 * 5))
app.rows_last = [{"id": P1, "name": "Núi I", "status": "active"}, {"id": P2, "name": "Núi II (mới)", "status": "active"}, {"id": P3, "name": "Hết hạn", "status": "expired"}]
app.vps_last = {"items": [{"state": "active", "until": FUT, "pc": {"id": PC, "name": "139", "online": True, "remote": True, "off": False}}]}
ms.render()
ok["co du lieu: 4 o, 3 phien xem truoc (2 phone + 1 PC), o het han khong co phien"] = len(ms.cells) == 4 and sorted(ms.tiles) == sorted([P1, P2, "pc:" + PC])
ok["ten moi duoc luu"] = [x["n"] for x in B.minis_get(app)][1] == "Núi II (mới)"
ms._tick()
ok["_tick: phien dang chay (thay o)"] = all(t.playing for t in ms.tiles.values())
t1 = ms.tiles[P1]; w, h = t1.box_wh; t1.pending = (int(w), int(h), bytes(int(w) * int(h) * 3)); ms._tick()
ok["_tick: dan hinh vao o, bo lop che"] = ms.cells[P1]["shown"] and ms.cells[P1]["img"].data is not None
ok["o ngang rong hon cao, o doc cao hon rong"] = ms.tiles[P1].box_wh[0] > ms.tiles[P1].box_wh[1] and ms.tiles[P2].box_wh[1] > ms.tiles[P2].box_wh[0]
app.docked = {P2}; ms.dirty(); ms._tick()
ok["may dang mo ben phai -> o tam dung, che 'Dang mo'"] = not ms.tiles[P2].playing and "Đang mở" in ms.cells[P2]["cover"].kw.get("text", "")
app.docked = set()
for fn in ms.cells[P2]["box"].binds["<Button-1>"]: fn(None)
ok["bam o -> mo dieu khien dung may"] = app.opened == [(P2, False)]
class Cli:
    n = 0
    def keyframe(self): Cli.n += 1
    def close(self): pass
w0 = ms.tiles[P1].box_wh[0]; ms.tiles[P1].cli = Cli(); ms.tiles[P1].kf_t = 0.0; ms.cycle()
ok["Co: Vua -> To: o to hon"] = ms.tiles[P1].box_wh[0] > w0 and B.MiniStrip.ui()[1] == 2
for _ in range(50):
    if Cli.n: break
    time.sleep(0.02)
ok["ve lai dai: o dang phat dan ngay hinh cuoi (khong 'Dang noi') + xin khung khoa"] = ms.cells[P1]["shown"] and ms.cells[P1]["img"].data is not None and Cli.n == 1
ms.toggle()
ok["thu gon: tat het phien"] = not ms.tiles and not ms.cells and not ms.last and B.MiniStrip.ui()[0]
ms.toggle()
ok["mo lai: 3 phien"] = len(ms.tiles) == 3
ms.remove({"id": P3, "pc": False})
ok["bo 1 o"] = len(ms.cells) == 3 and len(B.minis_get(app)) == 3
app.rows_last = [r for r in app.rows_last if r["id"] != P1]; ms.render()
ok["may vang < 2 phut: giu o"] = any(x["id"] == P1 for x in B.minis_get(app))
ms.miss[P1] -= 200; ms.sig = None; ms.render()
ok["vang > 2 phut: tu bo"] = not any(x["id"] == P1 for x in B.minis_get(app)) and P1 not in ms.tiles
ms.flash = P2; ms.sig = None; ms.render()
ok["o vua thu nho sang vien"] = ms.cells[P2]["t"].kw.get("highlightbackground") == B.ACC
slot.destroy(); ms._tick()
ok["trang bi huy -> dong het phien"] = not ms.alive and not ms.tiles
bad = [k for k, v in ok.items() if not v]
for k, v in ok.items(): print(("  ✓ " if v else "  ✗ ") + k)
print("%d/%d dat" % (len(ok) - len(bad), len(ok))); sys.exit(1 if bad else 0)
