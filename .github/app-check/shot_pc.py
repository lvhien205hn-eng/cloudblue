# Chụp ảnh giao diện app PC (Windows thật của GitHub Actions, đúng vỏ giao diện của app) với máy chủ GIẢ:
#   trang chính (thẻ "VPS GPU của bạn") + trang 🖥️ VPS GPU (thẻ cấu hình, chọn Windows, chọn gói, mã giảm giá, chân trang).
#   python shot_pc.py <thư mục pc-client> <thư mục ảnh ra> [vi|en]      (vi: pc-*.png · en: en-pc-*.png)
# Không gọi mạng: Auth / Shop thay bằng lớp giả trả dữ liệu cố định (sản phẩm giống hệt sản phẩm thật trên web).
import os, sys, tempfile, time, json
os.environ["APPDATA"] = tempfile.mkdtemp()
LANG = (sys.argv[3] if len(sys.argv) > 3 else "vi").lower()
PFX = "" if LANG == "vi" else LANG + "-"
_d = os.path.join(os.environ["APPDATA"], "BlueRobloxPC"); os.makedirs(_d, exist_ok=True)
with open(os.path.join(_d, "settings.json"), "w", encoding="utf-8") as _f: json.dump({"lang": LANG}, _f)      # ngôn ngữ app (không theo Windows của máy CI)
sys.path.insert(0, os.path.abspath(sys.argv[1]))
OUT = os.path.abspath(sys.argv[2]); os.makedirs(OUT, exist_ok=True)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import bluepc as B
from PIL import ImageGrab

PROD_ID = "48fa9b2d-cfc6-4394-851e-26715651fa8e"
PROD = {"id": PROD_ID, "cat": "vps", "name": "VPS GPU BLUE", "price": 360000, "description": None, "name_en": None, "features_en": [], "description_en": None,
        "plans": [{"days": 7, "price": 360000}, {"days": 15, "price": 750000}, {"days": 30, "price": 1600000}],
        "features": ["2686V4", "RAM 128GB", "VGA 1080-8GB", "NVME 512GB", "MẠNG 1000 MBPS"]}
OS = [{"id": "22h2", "name": "Windows 10 Pro 22H2"}, {"id": "1511", "name": "Windows 10 Pro 1511"}]
INFO = {"on": True, "product": PROD_ID, "ready": True, "reinstall_max": 2, "os": [dict(OS[0], fast=True), dict(OS[1], fast=False)]}
FUT = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 29 * 86400 + 5 * 3600 + 120))
MINE = {"product": PROD_ID, "reinstall_max": 2, "os": OS, "items": [
    {"rental": 7, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 30, "until": FUT, "left": 2, "used": 0,
     "pc": {"id": "00000000-0000-4000-8000-0000000000c1", "name": "VPS-GPU-01", "code": "A1", "os": "22h2", "online": True, "remote": True, "off": False,
            "job": None, "last_job": None, "ram_gb": 128, "gpus": ["NVIDIA GeForce GTX 1080"]}}]}


class FakeAuth:
    logged_in = True
    email = "khach@cloudblue.vn"
    uid = "00000000-0000-4000-8000-00000000aaaa"
    def rpc(self, fn, args=None):
        return {"pc_shop_info": INFO, "pc_my_vps": MINE}.get(fn, {})
    def rest(self, path, *a, **k):
        return [PROD] if str(path).startswith("product_list") else []
    def phones(self): return []
    def __getattr__(self, k): return lambda *a, **kw: {}


class FakeShop:
    def __init__(self, auth): self.auth = auth
    def profile(self): return {"balance": 2500000, "username": "khach", "role": "user", "ctv_status": None, "ctv_discount": 0}
    def site(self): return {}
    def __getattr__(self, k): return lambda *a, **kw: {}


B.Auth, B.Shop = FakeAuth, FakeShop
app = B.Launcher()
app._vps_auto = True              # ảnh 1 = trang chính (khách chỉ có VPS thì app tự mở trang VPS GPU — tắt cho ảnh này)
app.root.geometry("640x750+0+0")


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        try: app.root.update()
        except Exception: break
        time.sleep(0.02)


def grab(name):
    app.root.lift(); app.root.attributes("-topmost", True); pump(0.6)
    x, y, w, h = app.root.winfo_rootx(), app.root.winfo_rooty(), app.root.winfo_width(), app.root.winfo_height()
    name = PFX + name
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h)); img.save(os.path.join(OUT, name))
    print("ảnh", name, img.size, flush=True)


def scroll(frac):
    for k, cv in list(app.scrollers.items()):
        try:
            if cv.winfo_ismapped(): cv.yview_moveto(frac)
        except Exception: pass
    pump(0.8)


MINE["cancel"] = True                                      # SQL v45: khách tự huỷ máy → menu Khác ▾ có 🗑 Huỷ máy


def repaint(sec=3):
    """Đọc lại danh sách (FakeAuth trả MINE hiện tại) → vẽ lại thẻ VPS ở Máy của tôi."""
    app._vps_sig = None; app.refresh(quiet=True); pump(sec)


pump(4)
grab("pc-1-main.png")                                      # 21.11k: Máy của tôi — thẻ VPS GPU đầy đủ (▶ Điều khiển · ⏱ Gia hạn · Khác ▾)
dlg = B.VpsBuyDlg(app)                                     # trang 🖥 VPS GPU chỉ để MUA (+ 1 dòng "Bạn đang có … — quản lý ở Máy của tôi")
pump(4)
grab("pc-2-vps-top.png")
scroll(0.42); grab("pc-3-vps-mid.png")
scroll(1.0); grab("pc-4-vps-bottom.png")
dlg.os = "1511"; dlg.days = 15; dlg.upd(); pump(1)
scroll(0.42); grab("pc-5-vps-pick.png")
dlg.close(); pump(0.5)

# 21/11f · các trạng thái có thanh tiến độ đếm giờ: đang cài Windows · cài lại lỗi (📋 Báo admin) · chờ máy quá lâu (📋 Báo admin) · 21.11k: đã kết thúc (tự ẩn lúc …)
AGO = lambda m: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - m * 60))
PCX = lambda i, nm, **k: dict({"id": "00000000-0000-4000-8000-0000000000c" + str(i), "name": nm, "code": "A" + str(i), "os": "22h2", "online": True, "remote": True,
                              "off": False, "job": None, "last_job": None, "ram_gb": 128, "gpus": ["NVIDIA GeForce GTX 1080"]}, **k)
MINE["items"] = [
    {"rental": 8, "state": "active", "os": "1511", "os_name": "Windows 10 Pro 1511", "days": 15, "until": FUT, "left": 1, "used": 1, "created_at": AGO(60),
     "pc": PCX(2, "VPS-GPU-02", job={"state": "sent", "os": "1511", "at": AGO(7)})},
    {"rental": 9, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 30, "until": FUT, "left": 0, "used": 2, "created_at": AGO(300),
     "pc": PCX(3, "VPS-GPU-03", last_job={"state": "failed", "at": AGO(20), "msg": "Không tải được bộ cài Windows (mạng chập chờn)"})},
    {"rental": 10, "state": "waiting", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": None, "left": 2, "used": 0, "created_at": AGO(36), "pc": None},
    {"rental": 11, "state": "active", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": AGO(10), "grace_until": AGO(-20), "left": 2, "used": 0, "created_at": AGO(9000),
     "pc": PCX(4, "VPS-GPU-04", lock=True)},
    {"rental": 12, "state": "ended", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": AGO(40), "left": 2, "used": 0, "created_at": AGO(9000),
     "end_why": "expired", "ended_at": AGO(12), "hide_at": AGO(-18), "pc": None},
    {"rental": 13, "state": "ended", "os": "22h2", "os_name": "Windows 10 Pro 22H2", "days": 7, "until": AGO(90), "left": 2, "used": 0, "created_at": AGO(9000),
     "end_why": "expired", "ended_at": AGO(45), "hide_at": AGO(15), "pc": None}]          # quá giờ ẩn → không được vẽ
repaint()
grab("pc-6-vps-states.png")
scroll(0.5); grab("pc-7-vps-states-2.png")
scroll(0.0)
rep = B.VpsReportDlg(app, MINE["items"][1]); pump(2)
grab("pc-8-report.png")
rep.close(); pump(0.5)

# 21/11f · admin bật bảo trì riêng VPS GPU → dòng vàng, khoá Điều khiển / Cài lại / Mua ngay (khách thường)
B.SITE["d"] = {"pc_maint": True, "pc_maint_msg": "Nâng cấp máy chủ, khoảng 30 phút" if LANG == "vi" else "Server upgrade, about 30 minutes"}
MINE["items"] = MINE["items"][:1] + [dict(MINE["items"][1], pc=PCX(3, "VPS-GPU-03"))]
repaint()
grab("pc-9-vps-maint.png")
dlg = B.VpsBuyDlg(app); pump(4)
scroll(1.0); grab("pc-10-vps-maint-bottom.png")
dlg.close(); pump(0.5)

# 21.11k · 🗑 Huỷ máy: hộp xác nhận — nút Huỷ chỉ bấm được sau khi tick "Tôi hiểu"
B.SITE["d"] = {}
MINE["items"] = [dict(MINE["items"][1], pc=PCX(3, "VPS-GPU-03"))]
repaint(2)
cx = B.VpsCancelDlg(app, MINE["items"][0]); pump(2)
grab("pc-11-cancel.png")
cx.ok.set(True); cx._arm(); pump(0.6)
grab("pc-12-cancel-ok.png")
cx.close(); pump(0.5)

# 22/11 · ⏻ Nguồn máy (SQL v48): thẻ có nút ⏻ Nguồn + trạng thái "Đang khởi động lại…" / "Đã tắt máy" · hộp Nguồn máy (Tắt máy chỉ bấm được sau khi tick)
MINE["power"] = True
base = dict(MINE["items"][0], left=2, used=0)
MINE["items"] = [dict(base, rental=21, pc=PCX(3, "VPS-GPU-03")),
                 dict(base, rental=22, pc=PCX(5, "VPS-GPU-05", pow={"cmd": "reboot", "state": "done", "at": AGO(1), "by": "customer"})),
                 dict(base, rental=23, pc=PCX(6, "VPS-GPU-06", online=False, pow={"cmd": "shutdown", "state": "done", "at": AGO(20), "by": "customer"}))]
repaint()
grab("pc-13-power-states.png")
pw = B.VpsPowerDlg(app, MINE["items"][0]); pump(2)
grab("pc-14-power.png")
pw.ok.set(True); pw._arm(); pump(0.6)
grab("pc-15-power-ok.png")
pw.close(); pump(0.5)
# 22/11 · 🌐 Proxy riêng của máy (Cloud Phone · Công cụ › Proxy): đang chạy qua proxy · proxy lỗi (máy tự đi mạng thường)
PXJ = {"set": True, "kind": "auto", "show": "9.8.7.6:1080:khach:••••", "online": True, "has_pass": True,
       "state": {"mode": "proxy", "kind": "socks5", "ip": "5.6.7.8", "ms": 80, "alive": True}}


class FakeCp:
    def __init__(self, auth, pid): self.pid = pid
    def json(self, method, path, body=None, ctype=None, timeout=120): return PXJ if path == "proxy" else {}
    def wait_job(self, jid, on_msg=None, limit=1800): return "Đã BẬT proxy — IP ra: 5.6.7.8 · 80 ms"


B.CpClient = FakeCp
td = B.ToolsDlg(app, {"id": "00000000-0000-4000-8000-0000000000d1", "name": "Máy 1"}, "proxy"); pump(2.5)
grab("pc-16-proxy.png")
PXJ = dict(PXJ, kind="http", show="9.8.7.6:3128:khach:••••", state={"mode": "direct", "kind": "http", "err": "proxy báo SAI user / mật khẩu (407)", "alive": True})
td.load_proxy(); pump(1.5)
grab("pc-17-proxy-loi.png")
td.close(); pump(0.5)

# 22.11c · ▦ Xem tất cả: VPS GPU (ô ngang 16:9, xem trước trực tiếp qua trạm máy PC) + Cloud Phone (ô dọc) · chip lọc khi có cả 2 loại
from PIL import Image, ImageDraw
B.LiveTile._start = lambda self, g: None                   # không nối mạng — hình giả được bơm thẳng vào ô
B.PcTile._start = lambda self, g: None


def fake_frame(w, h, title, pc):
    im = Image.new("RGB", (max(16, w), max(16, h)), (8, 20, 48)); d = ImageDraw.Draw(im)
    for y in range(h): d.line([(0, y), (w, y)], fill=(10 + y * 40 // max(1, h), 40 + y * 60 // max(1, h), 110 + y * 80 // max(1, h)))
    if pc:
        d.rectangle([w * .18, h * .16, w * .78, h * .74], fill=(235, 240, 250), outline=(90, 140, 230))
        d.rectangle([w * .18, h * .16, w * .78, h * .24], fill=(40, 90, 200))
        d.rectangle([0, h - max(6, h // 14), w, h], fill=(16, 18, 26))
        for i in range(4): d.rectangle([6, 8 + i * h // 7, 6 + w // 18, 8 + i * h // 7 + w // 18], fill=(200, 210, 240))
    else:
        d.rectangle([w * .08, h * .1, w * .92, h * .22], fill=(255, 255, 255))
        for i in range(8): d.ellipse([w * (.1 + (i % 4) * .21), h * (.34 + (i // 4) * .14), w * (.1 + (i % 4) * .21) + w * .14, h * (.34 + (i // 4) * .14) + w * .14],
                                     fill=(60 + i * 20, 160, 255 - i * 15))
    d.text((8, h // 2 if pc else h - 24), title, fill=(255, 255, 255))
    return im.width, im.height, im.tobytes()


MINE["items"] = [dict(base, rental=31, pc=PCX(1, "139", code="139")), dict(base, rental=32, pc=PCX(2, "140", code="140")),
                 dict(base, rental=33, pc=PCX(3, "141", code="141", online=False))]
MINE.pop("power", None)
LEFT = lambda h: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + h * 3600))
PHONES = [{"id": "00000000-0000-4000-8000-0000000000e%d" % i, "name": "Máy %dGB" % r, "status": st, "ram": r, "android": a, "expires_at": LEFT(hl), "locked": False}
          for i, (r, a, st, hl) in enumerate(((8, "12", "active", 55), (6, "9", "active", 20), (12, "15", "active", 150), (4, "9", "expired", -2)), 1)]
FakeAuth.phones = lambda self: list(PHONES)
app.root.geometry("1280x820+0+0"); repaint(3)
grab("pc-18-main-vps-xem-tat-ca.png")                     # thẻ VPS GPU của bạn: nút ▦ Xem tất cả
app.open_wall("all"); pump(2.5)
wall = next(p for p in app.pages if isinstance(p, B.WallDlg) and p.alive)


def feed(sec=2.0):
    end = time.time() + sec
    while time.time() < end:
        for pid, t in list(wall.tiles.items()):
            if t.playing and t.pending is None and getattr(t, "_fed", 0) < 2:
                w, h = t.box_wh; nm = next((str(x["pc"]["name"]) for x in wall.pcs if str(x["pc"]["id"]) == pid), None)
                t.pending = fake_frame(int(w), int(h), ("VPS " + nm) if nm else "Cloud Phone", nm is not None); t._fed = getattr(t, "_fed", 0) + 1
        pump(0.25)


feed(); grab("pc-19-xem-tat-ca.png")                        # Tất cả: VPS GPU (3) + Cloud Phone (4), chip lọc
ok_chips = len(wall.chips.winfo_children()) == 3 and len(wall.cells) == 7
wall.set_kind("pc"); pump(1.5); feed()
grab("pc-20-xem-tat-ca-vps.png")                           # chỉ VPS GPU
ok_pc = len(wall.cells) == 3 and all(c.get("kind") == "pc" for c in wall.cells.values()) and len(wall.tiles) == 2
print("lưới Xem tất cả:", "chip + 7 ô" if ok_chips else "SAI chip / số ô", "·", "VPS 3 ô (2 ô phát hình)" if ok_pc else "SAI ô VPS", flush=True)
wall.close(); pump(0.5)
mine = [f for f in os.listdir(OUT) if f.startswith(PFX + "pc-")]
ok = len(mine) == 20 and all(os.path.getsize(os.path.join(OUT, f)) > 5000 for f in mine) and ok_chips and ok_pc
print("XONG", LANG, len(mine), "ảnh", "ĐẠT" if ok else "ẢNH RỖNG")
app.root.destroy()
sys.exit(0 if ok else 1)
