# -*- coding: utf-8 -*-
"""28/11 · SQL v67 — app PC: đổi Android / ĐỔI MÁY CHỦ giữ nguyên Android · tối đa 3 lần / 24 giờ (chạy không cần màn hình).
   Chạy:  python test_pc_switch.py <thư mục pc-client>"""
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

print("1. số lần đổi / 24 giờ")
ck("mặc định 3 · admin đặt 5 → 5 · rác → 3 · quá 50 → 50", (B.sw_limit({}), B.sw_limit({"switch_limit": "5"}), B.sw_limit({"switch_limit": "abc"}),
   B.sw_limit({"switch_limit": "99"})) == (3, 5, 3, 50))
class Auth:
    uid = "u1"; seen = []
    def rest(self, path): Auth.seen.append(path); return [{"id": 1}, {"id": 2}]
class Shop:
    def site(self): return {"switch_limit": "3"}
class App: auth = Auth(); shop = Shop()
lim, used = B.sw_quota(App())
ck("đếm đúng như SQL: mọi máy mới của lệnh đổi (replaces) tạo trong 24 giờ, kể cả máy đã đổi tiếp", (lim, used) == (3, 2)
   and "replaces=not.is.null" in Auth.seen[-1] and "created_at=gte." in Auth.seen[-1] and "user_id=eq.u1" in Auth.seen[-1], (lim, used, Auth.seen))
class Bad:
    uid = "u1"
    def rest(self, path): raise RuntimeError("mạng")
class App2: auth = Bad(); shop = Shop()
ck("lỗi mạng → (3, 0), không làm hỏng hộp", B.sw_quota(App2()) == (3, 0))

print("2. hộp đổi")
ck("có lựa chọn '🔀 Giữ Android X · máy chủ khác' → gọi cloudphone_change_server(p_id)",
   'opts = ([("srv", f"🔀 Giữ Android {cur} · máy chủ khác")] if self.can_srv else [])' in SRC
   and 'self.app.auth.rpc("cloudphone_change_server", {"p_id": self.p["id"]})' in SRC)
ck("chọn Android khác vẫn gọi cloudphone_switch_android như cũ", 'self.app.auth.rpc("cloudphone_switch_android", {"p_id": self.p["id"], "p_android": v})' in SRC)
ck("hộp hiện số lượt còn lại + máy mới vào máy chủ trống nhất", "Còn {max(0, lim - used)}/{lim} lượt đổi trong 24 giờ" in SRC)
ck("menu 'Đổi Android / máy chủ…' · cảnh báo xoá dữ liệu nói cả đổi máy chủ",
   '"Đổi Android / máy chủ…"' in SRC and "⚠ Đổi Android hoặc đổi máy chủ sẽ XOÁ SẠCH" in SRC)
ck("máy mới của lệnh đổi máy chủ ghi 'ở máy chủ khác' (cột avoid_node)", '(" ở máy chủ khác" if p.get("avoid_node") else "")' in SRC)
_cls = next(c for c in vars(B).values() if isinstance(c, type) and "switch_note" in vars(c))
_me = type("Me", (), {"rows_last": []})()
_n1 = _cls.switch_note(_me, {"android": "12", "node": "wait-old", "avoid_node": "n1", "replaces": "p-1"})
_n2 = _cls.switch_note(_me, {"android": "15", "node": "wait-old", "replaces": "p-1"})
_n3 = _cls.switch_note(_me, {"android": "12", "node": None, "avoid_node": "n1", "replaces": "p-1"})
ck("chờ xoá máy cũ: đổi máy chủ ghi 'ở máy chủ khác', đổi Android thường thì không",
   "Android 12 ở máy chủ khác (2–5 phút)" in _n1 and "ở máy chủ khác" not in _n2 and "Máy cũ đã xoá — đang tạo máy Android 12 ở máy chủ khác" in _n3, (_n1, _n2, _n3))
ck("lỗi NO_OTHER_SERVER + SWITCH_LIMIT (3 lần / 24 giờ) có câu dễ hiểu", "NO_OTHER_SERVER" in SRC and "tối đa 3 lần trong 24 giờ" in SRC)
ck("máy chủ chưa có hàm (web chưa chạy SQL v67) → 'Tính năng đang cập nhật'", "Tính năng đang cập nhật — thử lại sau ít phút." in SRC)

print("3. tiếng Anh")
for vi in ["Đổi Android / máy chủ — Máy farm", "🔀 Giữ Android 12 · máy chủ khác", "Đổi sang máy chủ khác", "Đổi Android / máy chủ…",
           "Còn 2/3 lượt đổi trong 24 giờ (đổi Android và đổi máy chủ tính chung). Máy mới tự vào máy chủ còn trống nhất.",
           "Máy mới: Android 12 · 4GB · 4 nhân · 720x1280 · 30 FPS · ở máy chủ khác (không tạo lại ở máy chủ đang dùng)",
           "Đang xoá máy cũ… xoá xong tự tạo máy Android 12 ở máy chủ khác (2–5 phút).",
           "🔄 Đang xoá máy cũ… xoá xong tự tạo máy Android 12 ở máy chủ khác (2–5 phút).",
           "🔄 Máy cũ đã xoá — đang tạo máy Android 12 ở máy chủ khác (2–5 phút).",
           "Hiện chưa có máy chủ khác còn chỗ cho bản Android này — máy của bạn vẫn giữ nguyên, thử lại sau ít phút.",
           "Mỗi tài khoản đổi Android / máy chủ tối đa 3 lần trong 24 giờ — bạn đã đổi đủ, thử lại sau.",
           "Tính năng đang cập nhật — thử lại sau ít phút."]:
    en = EN.tr(vi)
    ck(f"EN: {vi[:46]}… → {en[:46]}…", not EN.has_vi(en.replace("Máy farm", "")), en)

print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
