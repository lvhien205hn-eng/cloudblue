# -*- coding: utf-8 -*-
"""28/11 · SQL v70 — app PC: 📱 BlueReal (thuê điện thoại thật) — nút 📲 Máy thật · hộp thuê / gia hạn theo giá mẫu máy · máy thật trong danh sách
   (nhãn, không Khởi động lại / công cụ giả lập / nâng cấp / đổi Android / FPS) · tiếng Anh. Chạy không cần màn hình.
   28/11f: hộp thuê / gia hạn y hệt ĐT đám mây — số máy, mã giảm giá (realphone_promo_check), 💎 Blue, giá CTV, hỏi xác nhận.
   Chạy:  python test_pc_real.py <thư mục pc-client>"""
import json, os, sys, tempfile
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
d = tempfile.mkdtemp(); os.environ["APPDATA"] = d; os.environ["HOME"] = d
os.makedirs(os.path.join(d, "BlueRobloxPC"), exist_ok=True)
with open(os.path.join(d, "BlueRobloxPC", "settings.json"), "w", encoding="utf-8") as _f: json.dump({"lang": "vi"}, _f)
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "pc-client"))
import bluepc as B
import bluepc_en as EN

OK = [0, 0]
def ck(n, c, x=""):
    OK[1] += 1
    if c: OK[0] += 1; print("  ✓", n)
    else: print("  ✗", n, "→", str(x)[:500])

SRC = open(B.__file__, encoding="utf-8").read()
CAT = {"name": "BlueReal", "on": True, "max_days": 90, "models": [{"id": "s9", "name": "Galaxy S9", "price_day": 5000, "stock": 0},
                                                                  {"id": "s10", "name": "Galaxy S10", "price_day": 6000, "stock": 2}]}
print("1. danh sách mẫu máy")
class Auth:
    n = 0
    def rpc(self, name, params):
        Auth.n += 1; assert name == "realphone_catalog"; return CAT
class App: auth = Auth()
c1 = B.real_catalog(App(), True); c2 = B.real_catalog(App())
ck("đọc realphone_catalog · nhớ 60 giây (lần 2 không hỏi lại)", c1 == CAT and c2 == CAT and Auth.n == 1, Auth.n)
ck("tên mẫu theo mã (s10 → Galaxy S10) · mã lạ → viết hoa", B.real_model_name("s10") == "Galaxy S10" and B.real_model_name("note10") == "NOTE10")
class Bad:
    def rpc(self, name, params): raise RuntimeError("Could not find the function public.realphone_catalog")
class App2: auth = Bad()
B._REAL_CAT["v"] = None
ck("web chưa chạy SQL v70 → None (hộp thuê báo đang cập nhật, không lỗi)", B.real_catalog(App2(), True) is None)
ck("lỗi dễ hiểu: hết máy / chưa mở bán / thiếu tiền", "vừa hết máy" in B.real_err("REAL_OUT: x") and "chưa mở bán" in B.real_err("REAL_NO_PRICE")
   and "nạp thêm" in B.real_err("INSUFFICIENT_BALANCE"))
print("2. giao diện")
ck("thanh dưới có nút '📲 Máy thật' → hộp thuê máy thật", '("📲 Máy thật", lambda: RealOrderDlg(self), "primary")' in SRC)
ck("hộp thuê gọi realphone_order(p_model, p_days, p_name [+ p_qty, p_promo, p_blue]) · gia hạn realphone_renew(p_id, p_days [+ p_promo, p_blue])",
   'self.app.auth.rpc("realphone_order", args)' in SRC and 'args = {"p_model": m, "p_days": d, "p_name": nm}' in SRC and 'if q > 1: args["p_qty"] = q' in SRC
   and 'self.app.auth.rpc("realphone_renew", args)' in SRC and 'args = {"p_id": self.p["id"], "p_days": d}' in SRC)
print("2b. 28/11f · y hệt hộp thuê ĐT đám mây (số máy · mã giảm giá · 💎 Blue · giá CTV)")
ck("ô mã giảm giá kiểm bằng realphone_promo_check (thuê: cp_new · gia hạn: cp_renew) · ô 💎 Trả bằng Blue ở cả 2 hộp",
   'PromoBox(self, f, "cp_new", lambda: {"p_model": self.m, "p_days": self.days, "p_qty": self.qty}, self.upd, rpc="realphone_promo_check")' in SRC
   and 'PromoBox(self, f, "cp_renew", lambda: {"p_phone": self.p["id"], "p_days": self.days}, self.upd, rpc="realphone_promo_check")' in SRC
   and SRC.count("self.bpay = BluePay(self, f, self.upd") >= 3)
ck("hộp thuê dùng chung đầu bước của hộp ĐT đám mây (① Chọn mẫu máy · ② Số ngày & số máy) · hỏi xác nhận · báo Telegram admin",
   "step = OrderDlg.step" in SRC and 'self.step(1, "Chọn mẫu máy"' in SRC and 'self.step(2, "Số ngày & số máy" if self.qmax() > 1 else "Số ngày thuê")' in SRC
   and 'mb.askyesno("Xác nhận thuê máy", f"📱 {md.get(\'name\')}' in SRC and "Đơn máy thật mới" in SRC)
class FakeLbl:
    def __init__(self): self.t = ""
    def config(self, **k): self.t = k.get("text", self.t)
    def winfo_exists(self): return True
class FakeEnt:
    def __init__(self, v): self.v = v
    def get(self): return self.v
class FakeAuth:
    calls = []
    def rpc(self, name, params):
        FakeAuth.calls.append((name, params))
        return {"ok": True, "kind": "discount", "use_promo": True, "discount": 3600, "price": 32400, "base": 36000, "code": "GIAM10"}
class FakeDlg:
    alive = True
    class app: auth = FakeAuth()
    def bg(self, job, done, fail=None): done(job())
pz = object.__new__(B.PromoBox)
pz.dlg, pz.scope, pz.rpc, pz.ctx, pz.changed = FakeDlg(), "cp_new", "realphone_promo_check", (lambda: {"p_model": "s10", "p_days": 3, "p_qty": 2}), (lambda: None)
pz.code, pz.key, pz.r, pz.busy, pz.seq, pz.res, pz.ent = "", "", None, False, 0, FakeLbl(), FakeEnt("giam10")
pz.check()
ck("ô mã của máy thật gọi đúng realphone_promo_check(p_code, p_scope, p_model, p_days, p_qty) → giảm 3.600đ còn 32.400đ",
   FakeAuth.calls == [("realphone_promo_check", {"p_code": "GIAM10", "p_scope": "cp_new", "p_model": "s10", "p_days": 3, "p_qty": 2})]
   and pz.price(36000) == 32400 and pz.send() == "GIAM10" and "32.400" in pz.res.t, (FakeAuth.calls, pz.res.t))
pz2 = object.__new__(B.PromoBox); pz2.rpc = None
ck("ô mã ĐT đám mây / VPS vẫn gọi promo_check như cũ (mặc định)", 'def __init__(self, dlg, parent, scope, ctx, changed, rpc="promo_check"):' in SRC
   and 'self.rpc = rpc or "promo_check"' in SRC)
md = {"id": "s10", "name": "Galaxy S10", "android": "12", "ram": 8, "price_day": 6000, "stock": 2}
dl = object.__new__(B.RealOrderDlg)
dl.ms, dl.m, dl.days, dl.qty, dl.adm, dl.mx, dl.promo, dl.bpay = [md], "s10", 3, 2, False, 90, None, None
dl.prof = {"balance": 500000, "ctv_status": "approved", "ctv_discount": 10}
ck("giá = giá / ngày × số ngày × số máy, CTV −10% (6.000 × 3 × 2 = 36.000 → 32.400) — như máy chủ (SQL v71)", dl.price() == 32400 and dl.pay() == (32400, 32400, 0, 32400), dl.pay())
ck("số máy tối đa = số máy rảnh của mẫu (S10 còn 2 → 2) · admin 10 · mẫu hết máy → báo vừa hết máy", dl.qmax() == 2 and dl.check() == "")
dl.qty = 3
ck("chọn 3 máy khi chỉ còn 2 → 'chỉ còn 2 máy rảnh — giảm số máy'", "chỉ còn 2 máy rảnh" in dl.check(), dl.check())
dl.adm = True; q_adm = dl.qmax(); dl.adm = False; dl.ms = [dict(md, stock=0)]; dl.qty = 1
ck("admin thuê tối đa 10 máy · mẫu hết máy → 'vừa hết máy'", q_adm == 10 and "vừa hết máy" in dl.check(), (q_adm, dl.check()))
rr = object.__new__(B.RealRenewDlg); rr.per, rr.days, rr.promo, rr.bpay = 6000, 7, None, None; rr.prof = {"ctv_status": "approved", "ctv_discount": 10}
ck("gia hạn: 6.000 × 7 ngày, CTV −10% → 37.800", rr.pay() == (37800, 37800, 0, 37800), rr.pay())
ck("máy thật bấm Gia hạn → hộp gia hạn máy thật (giá theo mẫu máy)", 'RealRenewDlg(self, p) if p.get("real_device") else RenewDlg(self, p)' in SRC)
ck("thẻ máy thật: dòng '📱 Máy thật · Galaxy S10 · Android …' · không có nút Khởi động lại",
   """info = f"📱 Máy thật · {real_model_name(p.get('real_model'))} · Android""" in SRC and 'if active and not p.get("real_device"): self.btn(bar, "Khởi động lại"' in SRC)
ck("menu Khác của máy thật: chỉ Đổi tên + Trả máy sớm (không công cụ giả lập / nâng cấp / đổi Android / FPS)",
   SRC.index('if p.get("real_device"):                    # 28/11 · SQL v70') < SRC.index('("Tab cửa sổ nhỏ · Xoay màn · Độ rộng nhỏ nhất…", "screen")'))
ck("làm mới danh sách có máy thật → đọc tên mẫu máy", 'if any(isinstance(r, dict) and r.get("real_device") for r in rows or []): real_catalog(self)' in SRC)
print("3. tiếng Anh")
for vi in ["📲 Máy thật", "📱 Thuê máy thật", "📱 Máy thật · Galaxy S10 · Android 12 · 8GB RAM", "Galaxy S10\nAndroid 12 · 8GB · 6.000đ/ngày · còn 2 máy",
           "Galaxy S9\nAndroid 10 · 4GB · 5.000đ/ngày · hết máy", "Chọn mẫu máy", "còn 2 máy rảnh", "Tên máy (tuỳ chọn)",
           "📱 Galaxy S10   ·   Android 12 · 8GB · 3 ngày × 2 máy", "6.000đ × 3 ngày × 2 máy − 10% CTV  ·  🏷️ −3.600đ  ·  💎 −5.000 Blue",
           "📱 Galaxy S10 · Android 12 · 2 máy · 3 ngày\n🏷️ Mã GIAM10: −3.600đ\n💎 Trả 5.000 Blue\n\nTrừ 27.400đ từ số dư?", "Mẫu này chỉ còn 2 máy rảnh — giảm số máy.",
           "Đã thuê Galaxy S10 · 7 ngày — máy đang được chuẩn bị (thường dưới 1 phút).", "Đã thuê 2 máy Galaxy S10 · 3 ngày — máy đang được chuẩn bị (thường dưới 1 phút).",
           "Gia hạn máy thật — Galaxy S10", "📱 Máy thật: không nâng cấp / đổi Android / đổi FPS được", "Mẫu máy này vừa hết máy — chọn mẫu khác hoặc quay lại sau ít phút.",
           "Điện thoại THẬT đặt tại shop, đã xoá sạch dữ liệu khách trước. Hết hạn máy tạm dừng — gia hạn trong 30 phút, quá thời gian app + dữ liệu của bạn bị xoá, máy về lại shop."]:
    en = EN.tr(vi)
    ck("EN: " + vi.replace("\n", " ")[:46] + "… → " + en.replace("\n", " ")[:46] + "…", en != vi and not any(w in en for w in ("ngày", "Máy thật", "còn ", "hết máy"))
       and ("Galaxy S10" in en or "Galaxy S9" in en or "Galaxy" not in vi), en)
print("4. cửa sổ máy + công cụ của máy thật (cpapi 28/11e chặn phần chỉ giả lập có)")
v = object.__new__(B.Viewer); v.bar_on = True; v.pc = False; v.real = True
names = [n for n, _, _ in v._tool_rects(900, 700)]
v.real = False; names2 = [n for n, _, _ in v._tool_rects(900, 700)]
ck("thanh công cụ máy thật: bỏ Xoay · Thu nhỏ tab · Sắp xếp tab, còn Quay lại / Màn chính / Chụp màn / Dán chữ / Công cụ",
   not {"rotate", "winmini", "wintile"} & set(names) and {"back", "home", "shot", "paste", "tools"} <= set(names) and "rotate" in names2, (names, names2))
ck("bấm phím tắt xoay / tab cửa sổ trên máy thật → báo, không gọi máy chủ", 'if self.real and name in ("rotate", "winmini", "wintile"):' in SRC)
ck("biết máy thật bằng cột real_device (web chưa chạy v70 → coi như ĐT đám mây)", 'select=real_device") or [{}])[0] or {}).get("real_device"))' in SRC)
ck("Công cụ của máy thật chỉ có Cài app · Ứng dụng · Khác (không Màn hình / Kho app / Clone / Root / Proxy)",
   B.ToolsDlg.REAL_TABS == ("install", "apps", "more") and "tabs = [t for t in self.TABS if t[0] in self.REAL_TABS] if self.real else self.TABS" in SRC)
ck("thẻ Khác của máy thật: không GPS giả / Root / khởi động lại", SRC.index("if self.real:                                    # 28/11: máy thật — chỉ chụp màn")
   < SRC.index('f = self.section("Vị trí GPS giả (máy Android 12 trở lên)", parent=pg)'))
en = EN.tr("📱 Máy thật: không có vị trí GPS giả, Root hay khởi động lại — máy tự xoay theo app.")
ck("EN: ghi chú công cụ máy thật", en.startswith("📱 Real phone: no fake GPS"), en)
print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
