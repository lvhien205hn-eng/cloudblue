# -*- coding: utf-8 -*-
# =====================================================================
#  remake.py — LÀM MỚI máy khách đang thuê của MÁY CHỦ NÀY: máy chưa có ở đây (từ server cũ) hoặc máy "ma"
#   (có trong danh sách nhưng giả lập không còn máy đó — VD bị xoá tay trong Multi-Instance).
#   • Giữ: chủ máy, tên, RAM/CPU, độ phân giải, BẢN ANDROID, HẠN SỬ DỤNG.   • Máy mới tinh (khách cài lại game, đăng nhập lại).
#   python run.py remake.py list        ← xem những máy sẽ làm mới
#   python run.py remake.py all         ← làm mới tất cả (từng máy một)
#   python run.py remake.py one TÊN     ← làm mới 1 máy
# =====================================================================
import datetime, json, os, subprocess, sys, time, urllib.parse, urllib.request

BLUE = os.environ.get("BLUE_HOME") or os.path.dirname(os.path.abspath(__file__))
PHONES = os.path.join(BLUE, "redroid", "phones.json")
def conf():
    d = {}
    for line in open(os.path.join(BLUE, "cloudphone.conf"), encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"): k, v = line.split("=", 1); d[k.strip()] = v.strip()
    return d
C = conf(); SB = C["SUPABASE_URL"].rstrip("/"); KEY = C["SUPABASE_SERVICE_KEY"]; BASE = C["PUBLIC_BASE"].rstrip("/")
NODE = C.get("NODE_ID") or os.environ.get("COMPUTERNAME", "win1")

def sb(method, path, body=None):
    req = urllib.request.Request(f"{SB}/rest/v1/{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode() or "null")

def stream_url(port):
    q = urllib.parse.quote; udid = f"127.0.0.1:{port}"
    ws = BASE.replace("https://", "wss://") + "/?action=proxy-adb&remote=" + q("tcp:8886", safe="") + "&udid=" + q(udid, safe="")
    return f"{BASE}/#!action=stream&udid={q(udid, safe='')}&player=webcodecs&ws={q(ws, safe='')}"

def pc(*a):
    return subprocess.run([sys.executable, os.path.join(BLUE, "phonectl.py")] + list(a), capture_output=True, text=True, encoding="utf-8", errors="replace")
def engine():
    """Giả lập + các bản Android máy chủ này tạo được (phonectl engine)."""
    try: return json.loads(pc("engine").stdout.strip().splitlines()[-1])
    except Exception: return {"emu": C.get("EMU", ""), "androids": [x.strip() for x in (C.get("ANDROIDS") or "").split(",") if x.strip()]}
def vm_names():
    """Tên mọi máy trong giả lập. Đọc lỗi (giả lập bận) → None: KHÔNG coi máy nào là đã mất."""
    names = {ln.split(",")[1].strip() for ln in pc("vmlist").stdout.splitlines() if ln.count(",") >= 2 and ln.split(",")[0].strip().isdigit()}
    return names or None
ENG = engine()
def want_android(r):
    """Bản Android máy khách đã mua. Máy chủ này không chạy bản đó → None (bỏ qua, không bao giờ tạo nhầm bản)."""
    v = str(r.get("android") or (local().get(r.get("container") or "") or {}).get("android") or "").strip().split(".")[0]
    if ENG.get("emu") == "ld": return "9"                       # LDPlayer 9 = Android 9 (đơn cũ chưa ghi bản → 9)
    return v if v and v in (ENG.get("androids") or []) else None

def local():
    try: return {p["name"]: p for p in json.load(open(PHONES, encoding="utf-8")).get("phones", [])}
    except Exception: return {}

PRIMARY = C.get("PRIMARY", "1") == "1"
def rows():
    rs = sb("GET", "cloud_phones?status=eq.active&select=id,name,container,node,ram,cpu,pending_ram,pending_cpu,res,fps,expires_at,user_id,android&order=created_at.asc") or []
    L = local(); names = vm_names() if L else set()
    # CHỈ máy của MÁY CHỦ NÀY (nhiều máy chủ: không bao giờ làm lại máy đang chạy ở máy chủ khác).
    # Máy cũ chưa ghi máy chủ → thuộc máy chủ chính (PRIMARY=1).
    mine = [r for r in rs if r.get("node") == NODE or (not r.get("node") and PRIMARY)]
    out = []
    for r in mine:
        c = r.get("container")
        if c not in L: r["_why"] = "chưa có ở máy chủ này"; out.append(r)
        elif names is not None and c not in names and r.get("node") == NODE:     # máy "ma": danh sách có, giả lập không còn
            r["_why"] = "giả lập không còn máy này"; out.append(r)
    return out

def remake(r):
    name = r.get("container") or ("cp_" + r["id"].replace("-", "")[:10])
    ver = want_android(r)
    ram = r.get("pending_ram") or r["ram"]; cpu = r.get("pending_cpu") or r["cpu"]     # đang chờ đổi cấu hình (VD hạ về trần mới) → tạo luôn theo cấu hình mới
    print(f"\n######## {r.get('name') or name}  (Android {ver or r.get('android') or '?'} · {ram}GB/{cpu} nhân · hết hạn {str(r.get('expires_at'))[:16]}) ########", flush=True)
    if not ver:
        print(f"   ✗ bỏ qua: máy chủ này không chạy Android {r.get('android') or '?'} (bán: {', '.join(ENG.get('androids') or [])})"); return False
    if name in local():                                        # máy "ma" → bỏ khỏi danh sách (phonectl forget: CHỈ bỏ khi giả lập chắc chắn không còn máy, không bao giờ xoá máy thật)
        d = pc("forget", name)
        if name in local(): print("   ✗ chưa bỏ được máy cũ khỏi danh sách:", ((d.stdout or "") + (d.stderr or "")).strip()[-160:]); return False
    p = pc("create", name, "--ram", str(ram), "--cpu", str(cpu), "--days", "1", "--res", r.get("res") or "720x1280",
           "--fps", str(r.get("fps") or 30), "--android", ver)
    print("   " + ((p.stdout or "") + (p.stderr or "")).strip().replace("\n", "\n   "))
    q = local().get(name)
    if p.returncode != 0 or not q: print("   ✗ chưa làm mới được máy này"); return False
    st = json.load(open(PHONES, encoding="utf-8"))
    for x in st["phones"]:
        if x["name"] == name and r.get("expires_at"): x["expires"] = r["expires_at"]
    json.dump(st, open(PHONES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sb("PATCH", f"cloud_phones?id=eq.{r['id']}", {"container": name, "port": q["port"], "stream_url": stream_url(q["port"]),
                                                 "node": NODE, "android": str(q.get("android") or ver), "ram": ram, "cpu": cpu, "pending_ram": None, "pending_cpu": None,
                                                 "error": None, "updated_at": datetime.datetime.now().isoformat()})
    print(f"   ✓ ĐÃ LÀM MỚI → {name} (Android {q.get('android') or ver}, cổng {q['port']})"); return True

if __name__ == "__main__":
    act = sys.argv[1] if len(sys.argv) > 1 else "list"; L = rows()
    OK = [r for r in L if want_android(r)]; SKIP = [r for r in L if not want_android(r)]
    if act == "list":
        print(f"Máy khách đang thuê cần làm mới trên Windows: {len(OK)}  (tổng RAM {sum(float(r['ram']) for r in OK):g} GB)")
        for r in OK: print(f"  {(r.get('container') or '')[:16]:16} {str(r.get('name'))[:24]:24} Android {want_android(r)} · {r.get('pending_ram') or r['ram']}GB/{r.get('pending_cpu') or r['cpu']} nhân"
                           f"  hết hạn {str(r.get('expires_at'))[:16]} · {r.get('_why', '')}")
        if SKIP: print(f"Bỏ qua {len(SKIP)} máy (máy chủ này không chạy bản Android đó): " +
                       ", ".join(f"{r.get('container') or r.get('name')} (Android {r.get('android') or '?'})" for r in SKIP))
    elif act == "one":
        m = [r for r in L if sys.argv[2] in (r.get("container"), r.get("name"))]
        if not m: sys.exit("Không thấy máy này.")
        remake(m[0])
    elif act == "all":
        ok = sum(1 for r in OK if remake(r)); print(f"\n================ ĐÃ LÀM MỚI {ok}/{len(OK)} MÁY ================")
