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
        if path == "rotate":                              # 23/11d: máy chủ mới trả "turned" + câu kết quả; máy chủ cũ ("rot_old") chỉ trả ok
            if self.mode == "rot_old": return {"ok": True}
            return {"ok": True, "to": body.get("to"), "turned": self.mode != "rot_no",
                    "msg": ("Đã xoay màn NGANG." if self.mode != "rot_no" else "Máy này chưa xoay ngang được màn chính — app / game cần màn ngang vẫn tự hiện ngang.")
                    if body.get("to") == "land" else "Đã về màn DỌC."}
        if self.mode == "ask": return {"ok": True, "n": 1, "fit": "ask", "msg": "Đã thu nhỏ knight (1 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ."}
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
# 23/11d–e: máy chủ báo fit = ask → nhắc chỗ bấm Vừa khung · Xoay dùng câu của máy chủ mới · chờ máy chủ đủ lâu
said.clear(); cp.mode = "ask"; cp.calls.clear(); v._tool("winmini", pg)
ck("23/11d · máy chủ báo fit=ask (game chưa chắc vừa cửa sổ) → câu máy chủ + chỉ chỗ bấm Mở lại vừa khung", wait(lambda: len(said) >= 2)
   and said[-1].startswith("Đã thu nhỏ knight (1 tab nhỏ)") and "Mở lại vừa khung" in said[-1], said)
src0 = open(os.path.join(sys.argv[1], "bluepc.py"), encoding="utf-8").read()
ck("23/11e · chờ máy chủ đủ lâu: win ≥ 100 giây (lần đầu máy chủ bật lại giao diện hệ thống của máy), rotate ≥ 75 giây (lần đầu cài app trợ giúp xoay)",
   src0.count('self._cp().json("POST", "win", {"do": what}, timeout=100)') == 1 and src0.count('self.cp.json("POST", "win", {"do": what}, timeout=100)') == 1
   and src0.count('timeout=75') == 2 and 'timeout=45' not in src0.split("def _win(self, what):")[1][:900])
v.state = ["connected"]; v.vw, v.vh = 720, 1280; v.notice = None; v._post = lambda: None; v.cli = None
said.clear(); cp.mode = "ok"; cp.calls.clear(); v._rotate()
ck("23/11d · bấm Xoay (hình đang dọc) → POST rotate {to: land}; máy chủ mới báo đã xoay → không hiện câu 'app chỉ chạy màn dọc'", wait(lambda: len(cp.calls) >= 1)
   and cp.calls[-1][:2] == ("POST", "rotate") and cp.calls[-1][2]["to"] == "land" and (time.sleep(0.3) or True) and said == ["Đang xoay ngang…"], (cp.calls, said))
said.clear(); cp.mode = "rot_no"; v._rotate("land")
ck("23/11d · máy chủ báo chưa xoay ngang được màn chính → hiện đúng câu của máy chủ (không chờ 3,5 giây)", wait(lambda: len(said) >= 2, 2.0)
   and said[-1].startswith("Máy này chưa xoay ngang được màn chính"), said)
said.clear(); cp.mode = "rot_old"; v._rotate("land")
ck("máy chủ cũ (không có 'turned') → cách cũ: 3,5 giây sau hình chưa đổi hướng thì nói rõ", wait(lambda: len(said) >= 2, 6.0) and said[-1].startswith("Đã khoá màn NGANG"), said)
cp.mode = "ok"
B.SITE["d"] = {"joinZl": " https://zalo.me/g/abcxyz123 "}; z1 = B.zalo_group_url()
B.SITE["d"] = {"joinZl": "javascript:alert(1)"}; z2 = B.zalo_group_url()
B.SITE["d"] = {"joinZl": "https://zalo.me/g/a b"}; z3 = B.zalo_group_url()
B.SITE["d"] = {}; z4 = B.zalo_group_url()
ck("23/11 · link nhóm Zalo (settings.data.joinZl): nhận link http(s) hợp lệ, bỏ link lạ / có khoảng trắng / trống", (z1, z2, z3, z4) == ("https://zalo.me/g/abcxyz123", "", "", ""), (z1, z2, z3, z4))
ck("23/11 · app PC hiện chữ '💬 Nhóm Zalo ↗' cạnh 'Mở web ↗' khi admin đã đặt link (vẽ lại mỗi lần đọc cài đặt web)",
   'self.zl_lbl = tk.Label(sub, text=L("💬 Nhóm Zalo ↗", "💬 Zalo group ↗")' in src0 and "self._paint_site(); self._auto_update()" in src0 and "def _paint_site(self):" in src0)
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
ck("23/11c · nút Cửa sổ to hơn / nhỏ hơn (gửi win grow / shrink) + Màn ngang rộng (hỏi trước, gửi wide) + Màn dọc như cũ (narrow)",
   all(f'self.app.btn(r, "{t}", lambda: self.win("{w}"), "soft")' in src for t, w in (("Cửa sổ to hơn", "grow"), ("Cửa sổ nhỏ hơn", "shrink"), ("Màn dọc như cũ", "narrow")))
   and 'self.app.btn(r, "Màn ngang rộng", self.win_wide, "soft")' in src and 'mb.askyesno("Màn ngang rộng"' in src and 'self.win("wide")' in src
   and '"grow": "Đang cho cửa sổ to hơn…"' in src and '"wide": "Đang bật màn ngang rộng…"' in src)

# ---------------- 4. tiếng Anh ----------------
for vi, en in (("Thu nhỏ tab", "Minimize tab"), ("Sắp xếp tab", "Arrange tabs"), ("Phóng to tab", "Maximize tab"), ("Tab cửa sổ nhỏ", "Small tab windows"),
               ("Đang thu nhỏ tab…", "Minimizing the tab…"), ("Mở lại vừa khung", "Refit to window"), ("Đang mở lại game trong cửa sổ…", "Reopening the game in its window…"),
               ("Cửa sổ to hơn", "Bigger window"), ("Cửa sổ nhỏ hơn", "Smaller window"), ("Màn ngang rộng", "Wide landscape"), ("Màn dọc như cũ", "Normal portrait"),
               ("Đang cho cửa sổ to hơn…", "Making the window bigger…"), ("Đang bật màn ngang rộng…", "Turning on the wide landscape screen…")):
    ck(f"English: '{vi}' → '{en}'", EN.tr(vi) == en, EN.tr(vi))
for vi, want in (("Đã thu nhỏ Roblox (2 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ.", "Minimized Roblox (2 small tabs)."),
                 ("Đã thu nhỏ Roblox (bản clone) (3 tab nhỏ). Kéo thanh trên cùng để dời, kéo mép để đổi cỡ.", "Minimized Roblox (clone) (3 small tabs)."),
                 ("Đã xếp 4 tab nhỏ (1 cột × 4 hàng). Màn nhỏ nên tab chồng nhau — tăng 📐 Độ rộng nhỏ nhất (VD 600 dp) để tab không đè nhau.", "Arranged 4 small tabs (1 × 4)."),
                 ("Đã phóng to Roblox hết màn. Muốn toàn màn như cũ: bấm nút ▭ trên thanh tiêu đề cửa sổ.", "Roblox now fills the screen."),
                 ("Các tab đang là cửa sổ nhỏ rồi — mở thêm tab khác (VD bản clone) rồi bấm Thu nhỏ tab.", "Your tabs are already small windows"),
                 ("Đã mở lại Roblox ngay trong cửa sổ — game vẽ vừa khung (game vừa khởi động lại, vào lại trận nếu cần).", "Reopened Roblox inside its window — the game now fits"),
                 ("Chưa mở lại được Roblox trong cửa sổ — thử lại, hoặc mở app rồi bấm Thu nhỏ tab.", "Couldn't reopen Roblox in its window"),
                 ("Cửa sổ Roblox (bản clone) đã to hơn (720×495). Bấm tiếp để to nữa.", "window is bigger (720×495)"),
                 ("Cửa sổ Roblox đã nhỏ hơn (474×553). Bấm tiếp để nhỏ nữa.", "The Roblox window is smaller (474×553)"),
                 ("Cửa sổ đã to nhất rồi (hết màn) — muốn to nữa bấm Phóng to tab.", "The window already fills the screen"),
                 ("Cửa sổ đã nhỏ nhất rồi (Android không cho nhỏ hơn) — muốn xếp nhiều tab hơn bấm 🖥 Màn ngang rộng.", "as small as Android allows"),
                 ("Chưa có tab nhỏ nào đang hiện — thu nhỏ app (VD Roblox) trước rồi bấm Cửa sổ to hơn / nhỏ hơn.", "then click Bigger / Smaller window"),
                 ("Đã bật màn NGANG RỘNG (600 dp) — màn chính nằm ngang, chứa được nhiều tab hơn. Đã xếp 2 tab nhỏ (2 cột × 1 hàng).", "Wide landscape is on (600 dp)"),
                 ("Đã đặt màn rộng (600 dp) + khoá ngang — màn chính của máy này không xoay ngang, app / game ngang vẫn hiện ngang.", "Wide screen set (600 dp)"),
                 ("Đã trả màn DỌC như cũ (360 dp). Đã xếp 2 tab nhỏ (1 cột × 2 hàng).", "Back to the normal portrait screen (360 dp)"),
                 # 23/11d–e
                 ("Đã thu nhỏ knight (1 tab nhỏ) — game đã mở lại để vẽ vừa cửa sổ. Máy chuyển sang màn rộng 600 dp cho tab đủ chỗ — bấm Màn dọc như cũ để trả lại.", "The phone switched to a wide 600 dp screen"),
                 ("Đã thu nhỏ Roblox (bản clone) (2 tab nhỏ) — game đã mở lại để vẽ vừa cửa sổ.", "Minimized Roblox (clone) (2 small tabs) — the game reopened"),
                 ("Đã xếp 3 tab nhỏ (1 cột × 3 hàng). 2 game đã mở lại để vẽ vừa ô mới.", "2 game(s) reopened to fit the new size"),
                 ("Đã phóng to knight ra toàn màn. Game đã mở lại để vẽ đủ toàn màn. Máy đã về mật độ cũ (360 dp).", "back to its previous screen density (360 dp)"),
                 ("Đã phóng to knight ra toàn màn. Hình chưa đủ màn thì bấm Vừa khung.", "click Refit to window"),
                 ("Đã mở lại knight toàn màn — game vẽ đủ màn (game vừa khởi động lại, vào lại trận nếu cần).", "Reopened knight full screen"),
                 ("Đã mở lại knight ngay trong cửa sổ — game vẽ vừa khung (game vừa khởi động lại, vào lại trận nếu cần). Hình vẫn bị cắt thì bấm Màn ngang rộng cho cửa sổ đủ chỗ.", "Still cut off?"),
                 ("Đã xoay màn NGANG.", "The screen is now landscape."),
                 ("Máy này chưa xoay ngang được màn chính — app / game cần màn ngang vẫn tự hiện ngang.", "home screen can't turn landscape yet"),
                 ("Đã về màn DỌC.", "The screen is back to portrait."),
                 ("Đã về màn DỌC — app / game đang mở cần màn ngang nên vẫn hiện ngang.", "Back to portrait — the open app / game needs landscape")):
    got = EN.tr(vi)
    ck(f"English câu máy chủ: …{want[:40]}", want in got and not EN.has_vi(got), got)
# ---------------- 5. 27/11 · ⚡ VPS NVMe (giá như web / máy chủ · trạng thái · tách khỏi VPS GPU · đổi tên) ----------------
C = {"unit_cpu": 8000, "unit_ram": 12000, "unit_disk": 1000, "disk_free_gb": 20, "short_up": 0, "days": [1, 3, 7, 30]}
ck("VPS NVMe: giá tháng 2 vCPU · 4 GB · ổ miễn phí = 64.000đ; 1/3/7/30 ngày = 2.000/6.000/15.000/64.000đ (như web)",
   B.vm_month(C, 2, 4, 0) == 64000 and [B.vm_tier(C, 64000, d) for d in (1, 3, 7, 30)] == [2000, 6000, 15000, 64000])
ck("tự chọn 3 vCPU · 4 GB · 60 GB (40 GB vượt mức miễn phí) = 112.000đ / 30 ngày; thuê dưới 30 ngày cộng short_up %",
   B.vm_tier(C, B.vm_month(C, 3, 4, 40), 30) == 112000 and B.vm_tier(dict(C, short_up=20), 64000, 7) == 18000)
ck("ổ miễn phí mặc định 20 GB khi máy chủ chưa báo", B.vm_free_gb({}) == 20 and B.vm_free_gb({"custom": {"disk_free_gb": 30}}) == 30)
V = {"id": 12, "name": "VPS-12", "label": "", "status": "running", "want": "running", "online": True, "until": "2099-01-01T00:00:00Z"}
ck("trạng thái VPS NVMe: chạy · đã tắt · đang tạo · đổi cấu hình · hết hạn · lỗi", [B.vm_state(x)[0] for x in (V, dict(V, want="stopped"), dict(V, status="creating", busy=True),
   dict(V, cfg_busy=True), dict(V, expired=True), dict(V, err="x"))] == ["run", "off", "inst", "cfg", "exp", "warn"])
ck("tên hiện: tên riêng (nếu có) rồi mới tới mã VPS-…", B.vm_name(dict(V, label="Treo game")) == "Treo game" and B.vm_name(V) == "VPS-12")
ck("máy ảo VPS NVMe (pc) không vẽ lặp ở mục VPS GPU", B.vm_pc_ids({"items": [{"id": 1, "pc": "abc"}, {"id": 2}]}) == {"abc"})
ck("lỗi máy chủ → câu dễ hiểu (hết chỗ không trừ tiền, bảo trì)", "Không trừ tiền" in B.vm_err("P0001 NO_CAPACITY") and "bảo trì" in B.vm_err("MAINT"))
ck("máy chủ chưa có hàm (chưa chạy SQL) → nhận ra được để báo dễ hiểu", B.vm_missing("Could not find the function public.pc_my_rename") and not B.vm_missing("NOT_ALLOWED"))
ck("trang chính: thanh dưới có nút ⚡ VPS NVMe, đọc vm_my mỗi lần làm mới, mục VPS NVMe nằm dưới VPS GPU, mở điều khiển không bị bảo trì VPS GPU chặn",
   '("⚡ VPS NVMe", lambda: VmBuyDlg(self), "primary")' in src0 and 'vm = self.auth.rpc("vm_my", {})' in src0 and "self.vm_slot = tk.Frame(page, bg=BG)" in src0
   and "self._paint_vm(vm)" in src0 and "def open_pc(self, pid, vm=False):" in src0 and "app.open_pc(i, vm=True)" in src0)
ck("Thuê VPS NVMe gọi đúng hàm: vm_buy (gói + p_disk_gb khi thêm ổ) · vm_buy_custom (tự chọn); gia hạn / nâng cấp (hỏi giá p_dry) / cài lại / xoá / tắt-bật",
   all(x in src0 for x in ('"vm_buy_custom", {"p_cores"', 'fn, args = "vm_buy", {"p_plan"', 'args["p_disk_gb"] = b["disk"]', '"vm_my_renew"', '"p_dry": True', '"vm_my_reinstall"',
                           '"vm_my_cancel"', '"vm_my_power"')))
ck("✏️ đổi tên: VPS NVMe → vm_my_label · VPS GPU → pc_my_rename (chỉ khi máy chủ có cờ rename — SQL v60)", '"vm_my_label", {"p_id"' in src0
   and '"pc_my_rename", {"p_pc"' in src0 and 'can_ren = bool((data or {}).get("rename"))' in src0)
for vi, want in (("⚡ VPS NVMe của bạn", "Your VPS NVMe"), ("Tự chọn cấu hình", "Custom specs"), ("Thuê ngay", "Rent now")):
    ck(f"English (L): '{vi}' có bản tiếng Anh '{want}'", f'"{want}"' in src0)
print("%d/%d dat" % (OK[0], OK[1])); sys.exit(0 if OK[0] == OK[1] else 1)
