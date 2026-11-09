#!/usr/bin/env python3
# =====================================================================
#  cloudphone-migrate.py — CHUYỂN MÁY KHÁCH ĐANG THUÊ (máy thường/redroid) → MÁY GPU (GTX 1080, root sâu)
#   • Giữ nguyên: chủ máy, tên máy, cấu hình RAM/CPU/độ phân giải/FPS, HẠN SỬ DỤNG.
#   • Cài lại toàn bộ app khách đã cài + chép dữ liệu app (Android/data, obb). Android 9/10 → lên 11 (chạy được game ARM).
#   • Tài khoản Google trong Play Store KHÔNG chuyển được (khách đăng nhập lại); vài game có thể phải đăng nhập lại.
#   • Máy cũ chỉ bị xoá SAU KHI máy GPU đã chạy và trang web đã đổi sang máy mới. Lỗi → máy cũ giữ nguyên.
#
#   python3 ~/cloudphone-migrate.py list          # xem máy nào sẽ được chuyển (không đổi gì)
#   python3 ~/cloudphone-migrate.py one TÊN_MÁY   # chuyển 1 máy (thử trước)
#   python3 ~/cloudphone-migrate.py all           # chuyển TẤT CẢ máy thường đang chạy trên server này
# =====================================================================
import json, os, sys, subprocess, time, urllib.request, urllib.parse, datetime

HOME = os.path.expanduser("~")
PHONECTL = os.path.join(HOME, "phonectl.py")
PHONES_JSON = os.path.join(HOME, "redroid", "phones.json")

def conf():
    d = {}
    for line in open(os.path.join(HOME, "cloudphone.conf"), encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); d[k.strip()] = v.strip().strip('"').strip("'")
    return d

C = conf(); SB = C["SUPABASE_URL"].rstrip("/"); KEY = C["SUPABASE_SERVICE_KEY"]; BASE = C["PUBLIC_BASE"].rstrip("/")
NODE = C.get("NODE_ID") or os.uname().nodename; PRIMARY = C.get("PRIMARY", "1") == "1"

def sb(method, path, body=None):
    req = urllib.request.Request(f"{SB}/rest/v1/{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode() or "null"
        return json.loads(t)

def stream_url(port):
    q = urllib.parse.quote; udid = f"127.0.0.1:{port}"
    ws = BASE.replace("https://", "wss://") + "/?action=proxy-adb&remote=" + q("tcp:8886", safe="") + "&udid=" + q(udid, safe="")
    pl = "tinyh264" if 5600 <= int(port) <= 5699 else "webcodecs"
    return f"{BASE}/#!action=stream&udid={q(udid, safe='')}&player={pl}&ws={q(ws, safe='')}"

def local():
    try: return {p["name"]: p for p in json.load(open(PHONES_JSON)).get("phones", [])}
    except Exception: return {}

def rows():
    rs = sb("GET", "cloud_phones?status=eq.active&select=id,name,container,node,android,ram,cpu,user_id") or []
    L = local(); out = []
    for r in rs:
        if r.get("node") and r["node"] != NODE: continue
        if not r.get("node") and not PRIMARY: continue
        c = r.get("container") or ("cp_" + r["id"].replace("-", "")[:10])
        p = L.get(c)
        if not p or p.get("kind") == "gpu": continue
        out.append((r, c, p))
    return out

def migrate(r, c, p):
    new = c + "g"
    print(f"\n######## {r.get('name') or c}  ({c} · Android {p.get('android')} · {p['ram']}GB/{p['cpu']} nhân) ########", flush=True)
    pr = subprocess.Popen(["python3", PHONECTL, "migrate", c, new], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    last = ""
    for line in pr.stdout:
        print("   " + line.rstrip(), flush=True); last = line.strip() if line.startswith("MIGRATED") else last
    pr.wait()
    if pr.returncode != 0 or not last:
        print("   ✗ KHÔNG chuyển (máy cũ giữ nguyên)"); return False
    _, nname, port, av = last.split()
    sb("PATCH", f"cloud_phones?id=eq.{r['id']}", {"container": nname, "port": int(port), "stream_url": stream_url(port), "android": av,
                                                 "node": NODE, "updated_at": datetime.datetime.now().isoformat()})
    time.sleep(3)
    subprocess.run(["python3", PHONECTL, "delete", c], capture_output=True)       # web đã trỏ sang máy mới → xoá máy cũ
    print(f"   ✓ ĐÃ CHUYỂN → {nname} (GPU, Android {av})"); return True

if __name__ == "__main__":
    act = sys.argv[1] if len(sys.argv) > 1 else "list"
    L = rows()
    if act == "list":
        print(f"Máy thường đang chạy trên {NODE} sẽ được chuyển sang GPU: {len(L)}")
        for r, c, p in L: print(f"  {c:16} {str(r.get('name'))[:24]:24} Android {p.get('android')} → {'11' if str(p.get('android')) in ('9', '10') else p.get('android')}  {p['ram']}GB/{p['cpu']} nhân")
    elif act == "one":
        t = sys.argv[2] if len(sys.argv) > 2 else ""
        m = [x for x in L if x[1] == t or (x[0].get("name") or "") == t]
        if not m: print("Không thấy máy này (hoặc đã là máy GPU)."); sys.exit(1)
        sys.exit(0 if migrate(*m[0]) else 1)
    elif act == "all":
        ok = sum(1 for x in L if migrate(*x))
        print(f"\n================ ĐÃ CHUYỂN {ok}/{len(L)} MÁY SANG GPU ================")
    else: print(__doc__ or "list | one TÊN | all")
