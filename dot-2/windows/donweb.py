# -*- coding: utf-8 -*-
# =====================================================================
#  donweb.py — DỌN các máy bị KẸT trên WEB (Supabase) không còn máy thật trên Windows
#   python donweb.py          ← chỉ XEM sẽ dọn gì (không đổi gì)
#   python donweb.py --yes    ← dọn thật
#  • Đơn "Đang tạo…" kẹt > 5 phút mà MEmu không có máy  → HUỶ + HOÀN TIỀN vào số dư khách
#  • Đơn "Đang huỷ" kẹt                                   → đánh dấu đã huỷ
#  • Đơn lỗi cũ (> 1 giờ)                                 → ẩn khỏi danh sách (đã hoàn tiền từ trước)
#  • Máy đang thuê/hết hạn mà KHÔNG còn máy thật          → chỉ LIỆT KÊ (khách đã trả tiền: dùng ♻ Làm mới máy khách),
#                                                           thêm --mat-may để huỷ luôn (không hoàn tiền)
# =====================================================================
import datetime, json, os, subprocess, sys, urllib.parse, urllib.request

B = os.path.dirname(os.path.abspath(__file__))
def conf():
    d = {}
    for line in open(os.path.join(B, "cloudphone.conf"), encoding="utf-8-sig"):
        line = line.strip()
        if "=" in line and not line.startswith("#"): k, v = line.split("=", 1); d[k.strip()] = v.strip()
    return d
C = conf(); SB = C["SUPABASE_URL"].rstrip("/"); KEY = C["SUPABASE_SERVICE_KEY"]
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=minimal"}
YES = "--yes" in sys.argv; LOST = "--mat-may" in sys.argv

def sb(method, path, body=None):
    req = urllib.request.Request(f"{SB}/rest/v1/{path}", method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=30) as r: t = r.read().decode(); return json.loads(t) if t else None

def memu_names():
    """Tên các máy trong giả lập (MEmu hoặc LDPlayer) — lấy qua phonectl vmlist."""
    r = subprocess.run([sys.executable, os.path.join(B, "phonectl.py"), "vmlist"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if r.returncode != 0: sys.exit("Không đọc được danh sách máy giả lập: " + (r.stderr or "")[-200:])
    return {ln.split(",")[1].strip() for ln in (r.stdout or "").splitlines() if ln.count(",") >= 3 and ln.split(",")[0].strip().isdigit()}

def age_min(r):
    t = r.get("created_at") or r.get("updated_at")          # updated_at có lúc bị ghi giờ VN không kèm múi giờ → lệch 7 tiếng
    try: return (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))).total_seconds() / 60
    except Exception: return 999

NODE = C.get("NODE_ID") or os.environ.get("COMPUTERNAME", "win1"); PRIMARY = C.get("PRIMARY", "1") == "1"
def mine(r): return r.get("node") == NODE or (not r.get("node") and PRIMARY)   # chỉ dọn đơn của MÁY CHỦ NÀY
have = memu_names()
rows = sb("GET", "cloud_phones?status=in.(pending,creating,cancelling,active,expired,error)"
                 "&select=id,name,container,status,paid,created_at,updated_at,node&order=created_at.asc") or []
plan = []
for r in rows:
    if not mine(r): continue
    c = r.get("container") or ""; st = r["status"]; a = age_min(r); there = c and c in have
    tag = f"{(r.get('name') or '')[:22]:22} {c or '(chưa có máy)':16} {st:10} {a:6.0f} phút  trả {r.get('paid') or 0}đ"
    if st in ("pending", "creating") and not there and a > 5:
        plan.append(("refund", r, tag, "HUỶ + HOÀN TIỀN (kẹt Đang tạo)"))
    elif st == "cancelling" and not there:
        plan.append(("cancel", r, tag, "đánh dấu ĐÃ HUỶ (kẹt Đang huỷ)"))
    elif st == "error" and a > 60:
        plan.append(("cancel", r, tag, "ẨN đơn lỗi cũ"))
    elif st in ("active", "expired") and not there:
        plan.append(("lost" if LOST else "skip", r, tag, "mất máy thật → " + ("HUỶ (không hoàn tiền)" if LOST else "chỉ liệt kê — bấm ♻ Làm mới máy khách để tạo lại")))

if not plan: print("✓ Web sạch — không có máy nào bị kẹt."); sys.exit(0)
print(f"{'TÊN':22} {'MÁY':16} {'TRẠNG THÁI':10} {'KẸT':>6}        VIỆC SẼ LÀM")
for act, r, tag, what in plan: print(f"{tag}  →  {what}")
if not YES: print("\n(chỉ xem — chạy lại với --yes để dọn thật)"); sys.exit(0)

n = 0
for act, r, tag, what in plan:
    try:
        if act == "refund":
            sb("POST", "rpc/cloudphone_refund", {"p_id": r["id"], "p_err": "Đơn bị kẹt khi tạo máy — đã huỷ"})
            sb("PATCH", f"cloud_phones?id=eq.{r['id']}", {"status": "cancelled"}); n += 1
        elif act in ("cancel", "lost"):
            sb("PATCH", f"cloud_phones?id=eq.{r['id']}", {"status": "cancelled"}); n += 1
    except Exception as e: print("✗", r["id"][:8], e)
print(f"✅ Đã dọn {n} đơn/máy kẹt trên web.")
