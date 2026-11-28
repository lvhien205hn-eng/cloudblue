# -*- coding: utf-8 -*-
"""28/11 · SQL v70 — app PC: 📱 BlueReal (thuê điện thoại thật) — nút 📲 Máy thật · hộp thuê / gia hạn theo giá mẫu máy · máy thật trong danh sách
   (nhãn, không Khởi động lại / công cụ giả lập / nâng cấp / đổi Android / FPS) · tiếng Anh. Chạy không cần màn hình.
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
ck("hộp thuê gọi realphone_order(p_model, p_days) · gia hạn gọi realphone_renew(p_id, p_days)",
   'self.app.auth.rpc("realphone_order", {"p_model": m, "p_days": d, "p_name": None})' in SRC
   and 'self.app.auth.rpc("realphone_renew", {"p_id": self.p["id"], "p_days": d})' in SRC)
ck("máy thật bấm Gia hạn → hộp gia hạn máy thật (giá theo mẫu máy)", 'RealRenewDlg(self, p) if p.get("real_device") else RenewDlg(self, p)' in SRC)
ck("thẻ máy thật: dòng '📱 Máy thật · Galaxy S10 · Android …' · không có nút Khởi động lại",
   """info = f"📱 Máy thật · {real_model_name(p.get('real_model'))} · Android""" in SRC and 'if active and not p.get("real_device"): self.btn(bar, "Khởi động lại"' in SRC)
ck("menu Khác của máy thật: chỉ Đổi tên + Trả máy sớm (không công cụ giả lập / nâng cấp / đổi Android / FPS)",
   SRC.index('if p.get("real_device"):                    # 28/11 · SQL v70') < SRC.index('("Tab cửa sổ nhỏ · Xoay màn · Độ rộng nhỏ nhất…", "screen")'))
ck("làm mới danh sách có máy thật → đọc tên mẫu máy", 'if any(isinstance(r, dict) and r.get("real_device") for r in rows or []): real_catalog(self)' in SRC)
print("3. tiếng Anh")
for vi in ["📲 Máy thật", "📱 Thuê máy thật", "📱 Máy thật · Galaxy S10 · Android 12 · 8GB RAM", "Galaxy S10\nAndroid 12 · 8GB · 6.000đ/ngày · còn 2 máy",
           "Galaxy S9\nAndroid 10 · 4GB · 5.000đ/ngày · hết máy", "Galaxy S10 · 7 ngày = 42.000đ", "Thuê ngay · 42.000đ",
           "Đã thuê Galaxy S10 · 7 ngày — máy đang được chuẩn bị (thường dưới 1 phút).", "Gia hạn máy thật — Máy farm", "6.000đ × 15 ngày = 90.000đ",
           "Gia hạn · 90.000đ", "📱 Máy thật: không nâng cấp / đổi Android / đổi FPS được", "Mẫu máy này vừa hết máy — chọn mẫu khác hoặc quay lại sau ít phút."]:
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
