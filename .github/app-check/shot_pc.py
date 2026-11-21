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


pump(4)
grab("pc-1-main.png")
dlg = B.VpsBuyDlg(app)
pump(4)
grab("pc-2-vps-top.png")
scroll(0.42); grab("pc-3-vps-mid.png")
scroll(1.0); grab("pc-4-vps-bottom.png")
dlg.os = "1511"; dlg.days = 15; dlg.upd(); pump(1)
scroll(0.42); grab("pc-5-vps-pick.png")
mine = [f for f in os.listdir(OUT) if f.startswith(PFX + "pc-")]
ok = len(mine) == 5 and all(os.path.getsize(os.path.join(OUT, f)) > 5000 for f in mine)
print("XONG", LANG, len(mine), "ảnh", "ĐẠT" if ok else "ẢNH RỖNG")
app.root.destroy()
sys.exit(0 if ok else 1)
