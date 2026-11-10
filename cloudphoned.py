#!/usr/bin/env python3
# cloudphoned.py — Chương trình nền: đọc đơn từ Supabase (cloud_phones) → gọi phonectl tạo/xoá/gia hạn máy.
# Cấu hình đọc từ ~/cloudphone.conf (KEY=VALUE), KHÔNG đưa khoá bí mật lên GitHub.
#   SUPABASE_URL=https://xxxx.supabase.co
#   SUPABASE_SERVICE_KEY=eyJ...            (service_role key — bí mật)
#   PUBLIC_BASE=https://xxxx.trycloudflare.com   (link ws-scrcpy ra internet)
# Chạy:  python3 ~/cloudphoned.py           (vòng lặp mỗi 15s)
import json, os, sys, time, subprocess, urllib.request, urllib.parse, urllib.error, datetime, socket, shutil, threading
GRACE_MIN = 30          # hết hạn quá 30 phút không gia hạn → xoá máy + dữ liệu

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, "cloudphone.conf")
PHONES_JSON = os.path.join(HOME, "redroid", "phones.json")
PHONECTL = os.path.join(HOME, "phonectl.py")
POLL = 15

def load_conf():
    c = {}
    try:
        for line in open(CONF):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); c[k.strip()] = v.strip()
    except FileNotFoundError:
        print("THIẾU file cấu hình:", CONF); sys.exit(1)
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "PUBLIC_BASE"):
        if not c.get(k): print("THIẾU", k, "trong", CONF); sys.exit(1)
    return c

CFG = load_conf()
SB = CFG["SUPABASE_URL"].rstrip("/")
KEY = CFG["SUPABASE_SERVICE_KEY"]
BASE = CFG["PUBLIC_BASE"].rstrip("/")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
NODE_ID = CFG.get("NODE_ID") or socket.gethostname()           # mỗi server 1 tên riêng
PRIMARY = CFG.get("PRIMARY", "1") == "1"     # server CHÍNH (máy đầu tiên). Server thêm sau: PRIMARY=0 (cloudphone-addnode.sh tự ghi)

# ---------- NHIỀU SERVER: mỗi đơn chỉ 1 server nhận, mỗi server chỉ lo máy của mình ----------
def mine(row):
    """Máy này thuộc server này? (máy cũ chưa ghi server → thuộc server chính)"""
    n = row.get("node")
    return n == NODE_ID or (not n and PRIMARY)

WIN = os.name == "nt"                       # máy chủ Windows (MEmu)
def _f(k, d):
    try: return float(CFG.get(k, d))
    except (TypeError, ValueError): return float(d)
_MUMU = (CFG.get("EMU") or "").strip().lower() == "mumu"   # MuMu (Android 12 / 7) chạy được máy to (tới 128GB · 72 nhân) → tính đủ RAM/CPU đã bán
MEMU_MAX_RAM, MEMU_MAX_CPU = _f("MEMU_MAX_RAM", 1024 if _MUMU else 16), _f("MEMU_MAX_CPU", 1024 if _MUMU else 8)
WIN_RESERVE = _f("WIN_RAM_RESERVE", 4)
MEMU_MAX_VMS = int(_f("MEMU_MAX_VMS", 0))      # Windows: giới hạn SỐ máy (0 = không giới hạn số máy, chỉ tính theo tổng nhân + RAM)
WIN_VCPU_OVER = _f("WIN_VCPU_OVER", 0.9)        # tổng nhân ảo cấp cho các máy ≤ 90% số luồng thật (72 luồng → 64 nhân) — chừa 10% cho Windows + phát hình
def want(row):
    """RAM/CPU THẬT sẽ cấp cho đơn: Windows/MEmu tối đa 16GB · 16 nhân mỗi máy (gói to hơn vẫn nhận, chạy mức tối đa)."""
    r, c = float(row.get("ram") or 0), float(row.get("cpu") or 0)
    return (min(r, MEMU_MAX_RAM), min(c, MEMU_MAX_CPU)) if WIN else (r, c)
def win_caps(st):
    """Windows: sức chứa theo RAM TRỐNG THẬT (máy ảo đang chạy đã trừ sẵn) chứ không cộng dồn cấu hình;
       CPU dùng chung (72 luồng) → chỉ ngừng khi CPU thật đã nóng. Trả (đã cấp RAM, đã cấp CPU, trần RAM, trần CPU)."""
    a_r = sum(min(float(p.get("ram", 0)), MEMU_MAX_RAM) for p in st); a_c = sum(min(float(p.get("cpu", 0)), MEMU_MAX_CPU) for p in st)
    t_r, av_r = meminfo(); cpu_t = os.cpu_count() or 1
    c_r = a_r + max(0.0, av_r - WIN_RESERVE)
    c_c = a_c + cpu_t * CPU_OVER
    c_c = max(a_c, min(c_c, cpu_t * WIN_VCPU_OVER))          # TỰ GIỚI HẠN: tổng nhân ảo không vượt số luồng thật
    if (cpu_avg5() or 0) >= CPU_BUSY: c_c = a_c
    if t_r and 100 * (1 - av_r / t_r) >= RAM_BUSY: c_r = a_r
    if disk_full(): c_r = a_r
    if MEMU_MAX_VMS > 0 and len(st) >= MEMU_MAX_VMS: c_r, c_c = a_r, a_c   # đủ số máy tối đa → báo HẾT CHỖ, web ngừng bán
    return a_r, a_c, c_r, c_c

def local_load():
    """(phần trăm đã cấp, còn RAM, còn CPU) của server này theo ngưỡng LIMIT_PCT."""
    try: st = json.load(open(PHONES_JSON)).get("phones", [])
    except Exception: st = []
    if WIN:
        a_r, a_c, c_r, c_c = win_caps(st)
        return max(a_r / max(c_r, 1), (cpu_avg5() or 0) / 100), c_r - a_r, c_c - a_c
    ram_t = meminfo()[0]; cpu_t = os.cpu_count() or 1
    a_r = sum(float(p.get("ram", 0)) for p in st); a_c = sum(float(p.get("cpu", 0)) for p in st)
    c_r, c_c = ram_t * LIMIT_PCT / 100 * RAM_OVER, cpu_t * CPU_OVER
    busy = (cpu_avg5() or 0) >= CPU_BUSY
    if busy: c_c = a_c                                  # CPU thật đã nóng → coi như hết chỗ CPU
    t_r, av_r = meminfo()
    if t_r and 100 * (1 - av_r / t_r) >= RAM_BUSY: c_r = a_r          # RAM thật đã đầy → coi như hết chỗ RAM
    if disk_full(): c_r = a_r                                           # ổ cứng sắp đầy → không nhận máy mới
    return max(a_r / max(c_r, 1), (cpu_avg5() or 0) / 100), c_r - a_r, c_c - a_c

def age_s(row):
    try: return (now() - parse_dt(row.get("created_at"))).total_seconds()
    except Exception: return 999

_en = {"t": 0, "v": True}
def node_enabled():
    """Admin bấm "Ngừng nhận máy" cho server này → không nhận đơn mới (máy đang chạy vẫn chạy)."""
    if time.time() - _en["t"] > 30:
        try:
            r = sb("GET", f"cloud_nodes?id=eq.{urllib.parse.quote(NODE_ID)}&select=enabled") or []
            _en["v"] = bool(r[0].get("enabled", True)) if r else True
        except Exception: pass
        _en["t"] = time.time()
    return _en["v"]

# ---------- LOẠI GIẢ LẬP + BẢN ANDROID của máy chủ này (LDPlayer 9 = Android 9 · MuMu/MEmu = Android 12, 7) ----------
_eng = {"emu": "", "androids": []}
def engine():
    if not _eng["emu"]:
        try:
            r = phonectl(["engine"]); j = json.loads((r.stdout or "").strip().splitlines()[-1])
            _eng.update(emu=j.get("emu") or "", androids=[str(x) for x in j.get("androids") or []])
        except Exception:
            _eng.update(emu=CFG.get("EMU", "") or "", androids=[x.strip() for x in (CFG.get("ANDROIDS") or "").split(",") if x.strip()])
    return _eng
# Bản Android bán ở máy chủ RIÊNG (LDPlayer 9 · MEmu 7/12 · MuMu 12/15…). Máy chủ chính KHÔNG được nhận các bản này nếu nó
# không bán — trước đây thiếu "15" → máy chủ chính (LDPlayer, Android 9) giành đơn Android 15 rồi tạo nhầm Android 9.
KNOWN_ANDROIDS = ("7", "9", "12", "13", "14", "15", "16")
def android_ok(row):
    """Đơn này đúng bản Android máy chủ này bán? (đơn cũ không ghi bản / máy chủ chưa khai báo → nhận như cũ)"""
    av = engine()["androids"]
    if not av: return True
    v = str(row.get("android") or "").strip()
    return (not v) or v in av or (v not in KNOWN_ANDROIDS and PRIMARY)   # bản lạ (đơn cũ 11…) → máy chủ chính lo

# ---------- các máy chủ KHÁC (đọc bảng cloud_nodes 30 giây/lần) → máy chủ chính biết lúc nào nên hoàn tiền ----------
_nodes = {"t": 0, "rows": []}
def live_nodes():
    """Máy chủ đang bật nhận đơn và vừa báo cáo trong 3 phút gần nhất."""
    if time.time() - _nodes["t"] > 30:
        cols = "id,enabled,updated_at,cap_ram,alloc_ram,cap_cpu,alloc_cpu"
        try: _nodes["rows"] = sb("GET", f"cloud_nodes?select={cols},engine,androids") or []
        except urllib.error.HTTPError as e:
            if e.code == 400:                                 # web chưa chạy SQL v20 (chưa có cột engine/androids)
                try: _nodes["rows"] = sb("GET", f"cloud_nodes?select={cols}") or []
                except Exception: pass
        except Exception: pass
        _nodes["t"] = time.time()
    out = []
    for r in _nodes["rows"]:
        try:
            if r.get("enabled") is False or (now() - parse_dt(r.get("updated_at"))).total_seconds() > 180: continue
            out.append(r)
        except Exception: pass
    return out
def node_sells(r, v):
    av = [x.strip() for x in str(r.get("androids") or "").split(",") if x.strip()] or ["9"]   # máy chủ cũ chưa khai báo = Android 9
    return v in av
def others_for(row):
    """(còn máy chủ KHÁC đang chạy bán đúng bản Android của đơn?, trong đó có máy còn đủ chỗ cho đơn?)"""
    v = str(row.get("android") or "").strip() or "9"; wr, wc = want(row); live = room = False
    for r in live_nodes():
        if r.get("id") == NODE_ID or not node_sells(r, v): continue
        live = True
        try:
            if float(r.get("cap_ram") or 0) - float(r.get("alloc_ram") or 0) + 0.01 >= wr and \
               float(r.get("cap_cpu") or 0) - float(r.get("alloc_cpu") or 0) + 0.01 >= wc: room = True
        except (TypeError, ValueError): pass
    return live, room
def refund_unserved(row):
    """Máy chủ chính: đơn chưa ai nhận → chỉ hoàn tiền khi chắc chắn không máy chủ nào nhận được.
       Còn máy chủ khác đúng bản Android, đang chạy, còn chỗ (có thể đang bận tạo máy khác) → chờ nó tới 10 phút."""
    age = age_s(row); v = str(row.get("android") or "").strip() or "9"
    live, room = others_for(row)
    if age < (600 if room else 90 if android_ok(row) else 120): return
    if room:
        msg = f"Máy chủ Android {v} chưa nhận đơn — đã hoàn tiền, thử lại sau"
        why = "máy chủ đúng bản còn chỗ nhưng 10 phút không nhận đơn (kiểm tra cloudphoned trên máy đó)"
    elif android_ok(row) or live:
        msg = "Máy chủ đã đầy, chưa tạo được máy"; why = f"mọi máy chủ Android {v} đều đã đầy"
    else:
        msg = f"Máy chủ Android {v} đang bảo trì — đã hoàn tiền, thử lại sau"; why = f"không máy chủ Android {v} nào đang chạy"
    refund(row, msg); notify(f"⚠️ <b>Đơn Android {v} bị hoàn tiền</b>: {why}.")

def claim(row):
    """Giành đơn mới cho server này. Server còn trống nhiều nhận trước; không đủ chỗ thì nhường server khác.
    Trả về True nếu server này được làm đơn đó."""
    n = row.get("node")
    if n: return n == NODE_ID                       # đã có server nhận rồi
    if not node_enabled(): return False
    if not android_ok(row):                          # đơn Android 12/7 → máy chủ MuMu/MEmu; Android 9 → máy chủ LDPlayer
        if PRIMARY: refund_unserved(row)
        return False
    load, fr, fc = local_load(); age = age_s(row)
    wr, wc = want(row)
    if wr > fr + 0.01 or wc > fc + 0.01:             # máy này hết chỗ → nhường máy chủ khác
        if PRIMARY: refund_unserved(row)
        return False
    if age < load * 5: return False                 # server đang bận hơn chờ thêm vài giây để server trống hơn nhận trước
    try:
        got = sb("PATCH", f"cloud_phones?id=eq.{row['id']}&node=is.null&status=eq.pending",
                 {"node": NODE_ID}, {"Prefer": "return=representation"})
    except Exception as e:
        print("lỗi nhận đơn:", e); return False
    return bool(got)

def adopt_old():
    """Server chính: ghi tên server cho các máy cũ chưa có (để chia đơn đúng khi có nhiều server)."""
    if not PRIMARY: return
    try:
        for row in sb("GET", "cloud_phones?node=is.null&status=in.(active,expired,creating)&select=id,container") or []:
            if row.get("container") and phone_state(row["container"]): patch(row["id"], {"node": NODE_ID})
    except Exception as e: print("lỗi ghi server cho máy cũ:", e)
NOTIFY_URL = CFG.get("NOTIFY_URL", "https://cloudblue.vn/api/notify-admin")   # tên miền chính (www.cloudblue.vn chuyển về đây) → gọi thẳng, không qua chuyển hướng
def _lim():
    try: return max(50, min(100, int(CFG.get("LIMIT_PCT", "95"))))
    except ValueError: return 95
LIMIT_PCT = _lim()                 # ngưỡng nhận đơn (% RAM/CPU máy chủ). Đổi: LIMIT_PCT=90 trong ~/cloudphone.conf
try: CPU_OVER = max(1.0, min(10.0, float(CFG.get("CPU_OVER", "4"))))     # CPU dùng chung: cấp vượt số nhân thật tối đa ×4
except ValueError: CPU_OVER = 4.0
try: CPU_BUSY = max(30, min(100, int(CFG.get("CPU_BUSY_PCT", "85"))))   # CPU thật ≥ 85% (TB 5 phút) → ngừng nhận máy mới
except ValueError: CPU_BUSY = 85
try: RAM_OVER = max(1.0, min(4.0, float(CFG.get("RAM_OVER", "2"))))     # RAM dùng chung: cấp vượt tối đa ×2
except ValueError: RAM_OVER = 2.0
try: RAM_BUSY = max(30, min(98, int(CFG.get("RAM_BUSY_PCT", "85"))))   # RAM thật ≥ 85% → ngừng nhận máy mới
except ValueError: RAM_BUSY = 85
try: DISK_BUSY = max(50, min(98, int(CFG.get("DISK_BUSY_PCT", "90"))))  # ổ cứng ≥ 90% → ngừng nhận máy mới
except ValueError: DISK_BUSY = 90
def disk_full():
    try:
        d = shutil.disk_usage(os.path.join(HOME, "redroid")); return 100 * d.used / d.total >= DISK_BUSY or d.free < 15 * 1073741824
    except Exception: return False
_cpu_hist = []
def cpu_avg5(sample=None):
    """% CPU thật trung bình ~5 phút (ghi ra file cho phonectl đọc)."""
    if sample is not None:
        _cpu_hist.append((time.time(), sample))
        while _cpu_hist and time.time() - _cpu_hist[0][0] > 300: _cpu_hist.pop(0)
    if not _cpu_hist: return None
    v = round(sum(x for _, x in _cpu_hist) / len(_cpu_hist), 1)
    try:
        with open(os.path.join(HOME, "redroid", "cpu_now.json"), "w") as f: json.dump({"avg5": v, "ts": time.time()}, f)
    except Exception: pass
    return v
DATA_ROOT = os.path.join(HOME, "redroid")

def sb(method, path, body=None, extra=None):
    url = SB + "/rest/v1/" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={**H, **(extra or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t else None

def get_pending(status):
    return sb("GET", f"cloud_phones?status=eq.{status}&select=*&order=created_at.asc") or []

def get_renew():
    return sb("GET", "cloud_phones?pending_renew_days=gt.0&status=in.(active,expired)&select=*") or []

def get_upgrade():
    return sb("GET", "cloud_phones?or=(pending_ram.not.is.null,pending_cpu.not.is.null)&status=eq.active&select=*") or []

def do_upgrade(row):
    """Khách đã trả tiền nâng RAM/CPU → cấp thêm cho máy (không khởi động lại)."""
    name = row.get("container") or cname(row)
    ram = int(row.get("pending_ram") or row["ram"]); cpu = int(row.get("pending_cpu") or row["cpu"])
    print(f"[nâng cấp] {name} → {ram}GB · {cpu} nhân")
    r = phonectl(["resize", name, "--ram", str(ram), "--cpu", str(cpu)])
    if r.returncode == 0:
        patch(row["id"], {"ram": ram, "cpu": cpu, "pending_ram": None, "pending_cpu": None})
        notify(f"⬆️ Máy <b>{row.get('name') or name}</b> đã nâng lên {ram}GB RAM · {cpu} nhân.")
    else:
        print("lỗi nâng cấp:", (r.stdout or "")[-300:], (r.stderr or "")[-300:])

def get_live():
    return sb("GET", "cloud_phones?status=in.(active,expired)&select=*") or []

_dup_note = {}; _dup_said = {}; _ghost_said = {}
LIVE_ST = "pending,creating,active,expired,cancelling"          # trạng thái "còn sống" — giống chỉ mục chặn trùng của SQL v23

def _phones_reg():
    """Danh sách máy khách phonectl đang giữ trên máy chủ này {tên: máy} · đọc lỗi → None (khi đó KHÔNG tự sửa gì)."""
    try:
        with open(PHONES_JSON, encoding="utf-8") as f: st = json.load(f)
        return {p["name"]: p for p in st.get("phones", []) if p.get("name")}
    except Exception:
        return None

def _ghost_fix(pid, fields):
    """Giao máy bị cơ sở dữ liệu từ chối (409: dòng KHÁC trên máy chủ này đang giữ cùng cổng / tên máy ảo — SQL v23 chặn 2 khách 1 máy).
       Xem từng dòng đang giữ:
         • máy ảo của dòng đó CÒN trên máy chủ này nhưng ở cổng khác → web ghi cổng cũ → ghi lại đúng cổng;
         • máy ảo của dòng đó KHÔNG còn trên máy chủ này ("máy ma": đã bị xoá trước đây mà web không biết, MuMu cấp lại số cổng
           cho máy mới) → bỏ số cổng của dòng đó (KHÔNG xoá, KHÔNG đụng tiền, khách đó vẫn thấy máy như cũ) + báo admin xử lý;
         • máy ảo còn và đúng cổng đó (2 đơn cùng 1 máy thật) → không tự sửa, để admin xem.
       Trả True nếu đã gỡ được ít nhất 1 dòng → giao lại ngay."""
    port, cont = fields.get("port"), fields.get("container")
    reg = _phones_reg()
    if reg is None or not cont or cont not in reg: return False        # chưa chắc danh sách máy trên máy chủ → không đoán
    conds = []
    try:
        if port: conds.append(f"port.eq.{int(port)}")
    except (TypeError, ValueError): pass
    conds.append("container.eq." + urllib.parse.quote(str(cont), safe=""))
    try:
        rows = sb("GET", f"cloud_phones?node=eq.{urllib.parse.quote(NODE_ID, safe='')}&status=in.({LIVE_ST})&id=neq.{pid}"
                         f"&or=({','.join(conds)})&select=id,name,status,container,port") or []
    except Exception as e:
        print("   lỗi đọc dòng đang giữ máy:", e); return False
    fixed = False
    for r in rows:
        c = r.get("container") or ""; ps = reg.get(c) if c else None; tag = f"{r.get('name') or c or '?'} (đơn {str(r['id'])[:8]}, {r.get('status')})"
        try:
            if c == cont:
                continue                                                # 2 dòng cùng tên máy ảo → admin xem
            if ps:
                real = int(ps.get("port") or 0)
                if port and real and real != int(port) and int(r.get("port") or 0) == int(port):
                    sb("PATCH", f"cloud_phones?id=eq.{r['id']}&node=eq.{urllib.parse.quote(NODE_ID, safe='')}",
                       {"port": real, "stream_url": stream_url(real), "updated_at": datetime.datetime.now().isoformat()}, {"Prefer": "return=minimal"})
                    print(f"   🩹 {tag}: web ghi cổng cũ {port} → sửa đúng cổng {real}"); fixed = True
                continue                                                # máy thật đúng cổng → không tự sửa
            sb("PATCH", f"cloud_phones?id=eq.{r['id']}&node=eq.{urllib.parse.quote(NODE_ID, safe='')}",
               {"port": None, "updated_at": datetime.datetime.now().isoformat()}, {"Prefer": "return=minimal"})
            print(f"   🧹 máy ma {tag}: máy ảo {c or '?'} không còn trên {NODE_ID} → bỏ số cổng {r.get('port')} để giao máy mới")
            fixed = True
            if not _ghost_said.get(r["id"]):
                _ghost_said[r["id"]] = time.time()
                try: notify(f"🧹 <b>{NODE_ID}</b>: máy <b>{r.get('name') or c}</b> (đơn {str(r['id'])[:8]}, {r.get('status')}) KHÔNG còn máy ảo trên máy chủ"
                            f" nhưng web vẫn giữ cổng {r.get('port')} → đã bỏ số cổng để giao máy mới. Khách máy đó cần <b>làm lại máy hoặc hoàn tiền</b>.")
                except Exception: pass
        except Exception as e:
            print(f"   lỗi gỡ {tag}:", e)
    return fixed

def patch(pid, fields):
    fields["updated_at"] = datetime.datetime.now().isoformat()
    try:
        sb("PATCH", f"cloud_phones?id=eq.{pid}", fields, {"Prefer": "return=minimal"})
    except urllib.error.HTTPError as e:
        if e.code == 409 and ("port" in fields or "container" in fields):
            # SQL v23: 2 máy khách còn sống KHÔNG được chung 1 máy ảo / 1 cổng → cơ sở dữ liệu từ chối. Thường là "máy ma" (máy cũ đã bị xoá
            # trên máy chủ mà web vẫn ghi đang sống, MuMu cấp lại đúng số cổng đó cho máy mới) → tự gỡ rồi giao lại ngay.
            try:
                if _ghost_fix(pid, fields):
                    sb("PATCH", f"cloud_phones?id=eq.{pid}", fields, {"Prefer": "return=minimal"})
                    print(f"   ✓ đã gỡ dòng đang giữ máy — giao lại đơn {str(pid)[:8]} được")
                    _dup_note.pop(pid, None); _dup_said.pop(pid, None)
                    return
            except urllib.error.HTTPError as e2:
                if e2.code != 409: raise
            except Exception as e2:
                print("   lỗi tự gỡ máy ma:", e2)
            msg = f"TRÙNG MÁY: đơn {str(pid)[:8]} → {fields.get('container')} cổng {fields.get('port')} đang ghi cho máy khách KHÁC — chưa giao"
            if time.time() - _dup_said.get(pid, 0) > 60:              # in 1 lần / phút / đơn (trước: 3 giây / lần → đầy nhật ký)
                _dup_said[pid] = time.time(); print("   ⚠", msg)
            if time.time() - _dup_note.get(pid, 0) > 3600:
                _dup_note[pid] = time.time()
                try: notify(f"⚠️ <b>{NODE_ID}</b>: {msg}. Kiểm tra trang admin (2 đơn cùng 1 máy ảo).")
                except Exception: pass
        raise

def phonectl(args):
    return subprocess.run(["python3", PHONECTL] + args, capture_output=True, text=True)

def phone_state(name):
    try:
        st = json.load(open(PHONES_JSON))
        return next((p for p in st.get("phones", []) if p["name"] == name), None)
    except Exception:
        return None

def stream_url(port):
    # Phải có tham số ws= thì trang điều khiển mới hiện hình (thiếu → màn đen)
    q = urllib.parse.quote
    udid = f"127.0.0.1:{port}"
    ws = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/?action=proxy-adb&remote=" + q("tcp:8886", safe="") + "&udid=" + q(udid, safe="")
    # máy GPU (máy ảo Google, cổng 5600–5699): trình phát tinyh264 — webcodecs của Chrome có thể từ chối hình máy GPU gửi ra
    pl = "tinyh264" if 5600 <= int(port) <= 5699 else "webcodecs"
    return f"{BASE}/#!action=stream&udid={q(udid, safe='')}&player={pl}&ws={q(ws, safe='')}"

def now(): return datetime.datetime.now().astimezone()
def parse_dt(s):
    d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()

def cname(row):
    return "cp_" + row["id"].replace("-", "")[:10]

_until = {"v": None}
def phonectl_until():
    """phonectl.py trên máy này có hiểu --until chưa (máy đổi Android giữ đúng hạn cũ)?"""
    if _until["v"] is None:
        try: _until["v"] = '"--until"' in open(PHONECTL, encoding="utf-8").read()
        except Exception: _until["v"] = False
    return _until["v"]

BOOTING = set()
def do_create(row):
    """Tạo container ngay (vài giây), rồi chờ Android khởi động ở luồng riêng → nhiều máy khởi động song song."""
    name = cname(row)
    ps = phone_state(name)
    if not ps:
        print(f"[tạo] đơn {row['id'][:8]} → {name} ({row['ram']}GB/{row['cpu']} {row['days']}n {row.get('fps') or 30}fps)")
        r = phonectl(["create", name, "--ram", str(row["ram"]), "--cpu", str(row["cpu"]),
                      "--days", str(row["days"]), "--res", row.get("res") or "720x1280",
                      "--fps", str(row.get("fps") or 30), "--android", str(row.get("android") or "11"), "--nowait"]
                     + (["--until", str(row["until_at"])] if row.get("until_at") and phonectl_until() else []))
        if r.returncode == 2:   # HẾT HÀNG (quá ngưỡng)
            refund(row, "Máy chủ đã đầy, chưa tạo được máy"); notify(f"⚠️ <b>Đơn ĐT đám mây bị hoàn tiền</b> vì {NODE_ID} đã đầy {LIMIT_PCT}%."); return
        if r.returncode != 0:
            log_err = (r.stdout + r.stderr)[-300:]
            print("   ✗", log_err)
            refund(row, "Tạo máy lỗi, vui lòng thử lại"); notify(f"⚠️ <b>Tạo máy lỗi</b> trên {NODE_ID} (đã hoàn tiền khách):\n<code>{log_err[-200:]}</code>"); return
        ps = phone_state(name)
        if not ps:
            refund(row, "Tạo máy lỗi, vui lòng thử lại"); return
        patch(row["id"], {"container": name, "port": ps["port"], "node": NODE_ID})
    if name in BOOTING: return
    BOOTING.add(name)
    threading.Thread(target=finish_boot, args=(row["id"], name), daemon=True).start()

def finish_boot(pid, name):
    try:
        t0 = time.time()
        phonectl(["waitboot", name, "--noapps"])   # chỉ chờ Android lên → giao máy cho khách NGAY
        ps = phone_state(name)
        if not ps: return
        patch(pid, {"status": "active", "container": name, "port": ps["port"], "node": NODE_ID,
                    "stream_url": stream_url(ps["port"]), "expires_at": parse_dt(ps["expires"]).isoformat(), "error": None})
        print(f"   ✓ {name} sẵn sàng sau {time.time() - t0:.0f}s, cổng {ps['port']} — đang cài app sẵn ở nền")
        r = phonectl(["preinstall", name])     # cài app sẵn song song, khách đang dùng máy vẫn được
        for ln in (r.stdout or "").splitlines():
            if ln.strip().startswith(("+", "!")): print("  ", ln.strip())
    except Exception as e:
        if getattr(e, "code", 0) != 409: print("lỗi chờ khởi động:", e)     # 409 trùng máy: patch() đã ghi nhật ký (1 lần / phút)
    finally:
        BOOTING.discard(name)

def refund(row, msg):
    """Tạo máy lỗi → hoàn lại tiền khách đã trả (hàm SQL cloudphone_refund)."""
    try:
        sb("POST", "rpc/cloudphone_refund", {"p_id": row["id"], "p_err": msg})
    except Exception as e:
        print("   lỗi hoàn tiền:", e)
        patch(row["id"], {"status": "error", "error": msg + " — liên hệ admin để hoàn tiền."})

def notify(text):
    try:
        req = urllib.request.Request(NOTIFY_URL, data=json.dumps({"text": text}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "cloudphoned"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print("   không gửi được Telegram:", e)

# ---------------- Bảo trì ----------------
_maint = {"t": 0, "on": False, "off_at": None}
def maint_state():
    """Đang bảo trì (ĐT đám mây hoặc toàn web)? + lúc tắt bảo trì gần nhất."""
    if time.time() - _maint["t"] < 30: return _maint
    try:
        pr = (sb("GET", "cloudphone_pricing?id=eq.1&select=maintenance,maint_off_at") or [{}])[0]
        site = ((sb("GET", "settings?id=eq.1&select=data") or [{}])[0].get("data") or {})
        offs = [parse_dt(x) for x in (pr.get("maint_off_at"), site.get("maint_off_at")) if x]
        _maint.update(t=time.time(), on=bool(pr.get("maintenance")) or bool(site.get("maint")), off_at=max(offs) if offs else None)
    except Exception as e:
        print("lỗi đọc bảo trì:", e)
    return _maint

# ---------------- Báo cáo tài nguyên máy chủ ----------------
_cpu_prev = None
def cpu_pct():
    global _cpu_prev
    with open("/proc/stat") as f: v = [int(x) for x in f.readline().split()[1:]]
    idle, tot = v[3] + (v[4] if len(v) > 4 else 0), sum(v)
    p = None
    if _cpu_prev and tot > _cpu_prev[0]:
        p = round(100 * (1 - (idle - _cpu_prev[1]) / (tot - _cpu_prev[0])), 1)
    _cpu_prev = (tot, idle)
    return p

def meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1); m[k] = int(v.split()[0])
    return m.get("MemTotal", 0) / 1048576, m.get("MemAvailable", 0) / 1048576

def gpus():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        out = []
        for line in r.stdout.strip().splitlines():
            n, u, mu, mt, tp = [x.strip() for x in line.split(",")]
            num = lambda x: float(x) if x.replace(".", "", 1).isdigit() else None
            out.append({"name": n, "util": num(u), "mem_used": num(mu), "mem_total": num(mt), "temp": num(tp)})
        return out
    except Exception:
        return []

def disk(path):
    try:
        d = shutil.disk_usage(path); return {"used": round(d.used / 1073741824, 1), "total": round(d.total / 1073741824, 1)}
    except Exception:
        return None

def cpu_temp():
    best = None
    for p in ("/sys/class/hwmon",):
        try:
            for h in os.listdir(p):
                for f in os.listdir(os.path.join(p, h)):
                    if f.startswith("temp") and f.endswith("_input"):
                        v = int(open(os.path.join(p, h, f)).read()) / 1000
                        if 0 < v < 130: best = max(best or 0, v)
        except Exception:
            pass
    return best

_alert = {"full": None}
_hb_old = {"v": False}
_loop_t = [time.time()]             # lần cuối vòng chính chạy xong 1 lượt
def _hb_loop():
    """Báo cáo tài nguyên + "máy chủ còn sống" mỗi 30 giây ở LUỒNG RIÊNG: tạo / bật / xoá máy lâu (nhân bản Android 12,
       bật lần lượt từng máy) không làm web tưởng máy chủ mất kết nối (quá 3 phút không báo → web ngừng bán, app báo offline).
       Vòng chính kẹt thật quá 30 phút → thôi báo, để web biết máy chủ này có vấn đề."""
    while True:
        if time.time() - _loop_t[0] < 1800:
            try: heartbeat()
            except Exception as e: print("lỗi báo cáo tài nguyên:", e)
        time.sleep(30)
def heartbeat():
    try:
        st = json.load(open(PHONES_JSON)).get("phones", [])
    except Exception:
        st = []
    ram_t, ram_avail = meminfo(); cpu_t = os.cpu_count() or 1
    a_ram = sum(float(p.get("ram", 0)) for p in st); a_cpu = sum(float(p.get("cpu", 0)) for p in st)
    c_ram, c_cpu = ram_t * LIMIT_PCT / 100 * RAM_OVER, cpu_t * CPU_OVER
    try:
        running = len([l for l in subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15).stdout.split() if l.startswith("cp_")])
        running += len([p for p in st if p.get("kind") == "gpu" and
                        subprocess.run(["systemctl", "is-active", "-q", f"cloudgpu@{p['name']}"]).returncode == 0])
    except Exception:
        running = None
    try: up_h = round(float(open("/proc/uptime").read().split()[0]) / 3600, 1)
    except Exception: up_h = None
    cp_now = cpu_pct(); avg5 = cpu_avg5(cp_now)
    busy = avg5 is not None and avg5 >= CPU_BUSY
    if busy: c_cpu = a_cpu                              # CPU thật ≥ 85% → báo hết chỗ, web ngừng cho thuê thêm
    ram_pct = round(100 * (1 - ram_avail / ram_t), 1) if ram_t else None
    ram_busy = ram_pct is not None and ram_pct >= RAM_BUSY
    if ram_busy: c_ram = a_ram                          # RAM thật ≥ 85% → báo hết chỗ
    disk_busy = disk_full()
    if disk_busy: c_ram = a_ram                         # ổ cứng ≥ 90% → báo hết chỗ
    if WIN: a_ram, a_cpu, c_ram, c_cpu = win_caps(st)   # Windows: sức chứa theo RAM trống thật, CPU dùng chung
    metrics = {"cpu_pct": cp_now, "cpu_avg5": avg5, "cpu_over": CPU_OVER, "cpu_busy_pct": CPU_BUSY, "cpu_busy": busy, "ram_over": RAM_OVER, "ram_pct": ram_pct, "ram_busy_pct": RAM_BUSY, "ram_busy": ram_busy, "disk_busy": disk_busy, "disk_busy_pct": DISK_BUSY, "load": [round(x, 2) for x in os.getloadavg()], "cpu_temp": cpu_temp(),
               "ram_used": round(ram_t - ram_avail, 1), "gpus": gpus(), "disk_data": disk(DATA_ROOT), "disk_root": disk("/"),
               "running": running, "uptime_h": up_h, "base": BASE, "primary": PRIMARY, "renew_v": 2}     # renew_v 2: gia hạn chỉ xoá ngày chờ khi đã ghi được
    body = {"id": NODE_ID, "cpu_total": cpu_t, "ram_total": round(ram_t, 1), "cap_cpu": round(c_cpu, 1), "cap_ram": round(c_ram, 1),
            "alloc_cpu": a_cpu, "alloc_ram": a_ram, "phones": len(st), "limit_pct": LIMIT_PCT, "metrics": metrics,
            "updated_at": now().isoformat()}
    eng = engine()
    if eng["emu"] and not _hb_old["v"]: body.update(engine=eng["emu"], androids=",".join(eng["androids"]))
    try:
        sb("POST", "cloud_nodes", body, {"Prefer": "resolution=merge-duplicates,return=minimal"})
    except urllib.error.HTTPError as e:
        if e.code == 400 and "engine" in body:      # web chưa chạy SQL v20 (chưa có cột engine/androids) → báo như cũ
            _hb_old["v"] = True; body.pop("engine", None); body.pop("androids", None)
            print("   (web chưa chạy SQL v20 — chưa báo được loại giả lập / bản Android)")
            sb("POST", "cloud_nodes", body, {"Prefer": "resolution=merge-duplicates,return=minimal"})
        else: raise
    # Báo Telegram 1 lần khi chạm ngưỡng (và khi có chỗ trở lại)
    full = a_ram >= c_ram - 1 or a_cpu >= c_cpu - 1
    if _alert["full"] is not None and full != _alert["full"]:
        notify((f"🚨 <b>{NODE_ID}: CPU thật đang {avg5:.0f}%</b> (ngưỡng {CPU_BUSY}%) — tạm ngừng nhận máy mới." if busy else
                f"🚨 <b>{NODE_ID}: RAM thật đang dùng {ram_pct:.0f}%</b> (ngưỡng {RAM_BUSY}%) — tạm ngừng nhận máy mới." if ram_busy else
                f"🚨 <b>{NODE_ID}: ổ cứng sắp đầy</b> (ngưỡng {DISK_BUSY}%) — tạm ngừng nhận máy mới. Xoá bớt máy hết hạn / file thừa." if disk_busy else
                f"🚨 <b>{NODE_ID} đã đầy</b> — RAM cấp {a_ram:.0f}/{c_ram:.0f}GB, CPU cấp {a_cpu:.0f}/{c_cpu:.0f}.") + " Khách sẽ thấy HẾT HÀNG."
               if full else f"✅ <b>{NODE_ID}</b> đã có chỗ trống trở lại (RAM cấp {a_ram:.0f}/{ram_t:.0f}GB).")
    _alert["full"] = full

def running(name):
    ps = phone_state(name)
    if ps and ps.get("kind") == "gpu":          # máy GPU chạy bằng dịch vụ cloudgpu@TÊN
        return subprocess.run(["systemctl", "is-active", "-q", f"cloudgpu@{name}"]).returncode == 0
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True)
    return r.stdout.strip() == "true"

def do_locks():
    """Máy admin khoá → tắt; hết hạn khoá → tự mở khoá; máy đang chạy mà bị tắt ngoài ý muốn → bật lại."""
    rows = sb("GET", "cloud_phones?status=eq.active&select=id,container,locked,locked_until") or []
    t = now()
    for row in rows:
        name = row.get("container") or cname(row)
        if not phone_state(name): continue
        lk = bool(row.get("locked"))
        if lk and row.get("locked_until") and parse_dt(row["locked_until"]) <= t:
            patch(row["id"], {"locked": False, "locked_until": None, "lock_reason": None}); lk = False
            print(f"[mở khoá] {name} (hết thời hạn khoá)")
        on = running(name)
        if lk and on:
            print(f"[khoá] tắt {name}"); phonectl(["stop", name])
        elif not lk and not on:
            print(f"[bật lại] {name}")
            phonectl(["start", name])

_cancel_try = {}          # máy xoá chưa được: {id đơn: (số lần lỗi, lúc được thử lại)}
def do_cancel(row):
    """Khách / admin / ĐỔI ANDROID bấm xoá → xoá máy ảo + toàn bộ dữ liệu. CHỈ ghi "đã huỷ" khi giả lập CHẮC CHẮN không còn máy:
       đổi Android đợi đúng lúc này mới tạo máy mới → khách không bao giờ dùng được 2 máy. Xoá chưa được (giả lập bận / lỗi)
       → giữ "đang huỷ" (khách vẫn không mở được), thử lại giãn dần 1 → 15 phút, báo admin."""
    pid = row["id"]; n, nxt = _cancel_try.get(pid, (0, 0))
    if time.time() < nxt: return
    name = row.get("container") or cname(row)
    print(f"[huỷ] {name}")
    r = phonectl(["delete", name])
    o = (r.stdout or "") + (r.stderr or "")
    gone = (r.returncode == 0 and "Chưa xoá được" not in o) or (r.returncode == 1 and "Không có máy tên này" in o)
    if not gone:
        n += 1; wait = min(60 * n, 900); _cancel_try[pid] = (n, time.time() + wait)
        why = (o.strip().splitlines() or ["?"])[-1]
        print(f"   ⚠ chưa xoá được {name} (lần {n}, {wait}s sau thử lại): {why[:200]}")
        if n in (1, 5) or n % 20 == 0:
            notify(f"⚠️ <b>{NODE_ID}</b>: chưa xoá được máy <b>{row.get('name') or name}</b> ({name}) — máy chủ tự thử lại. Lý do: {why[:160]}")
        return
    _cancel_try.pop(pid, None)
    patch(pid, {"status": "cancelled"})

def release_switch_waits():
    """ĐỔI ANDROID: máy mới chờ máy cũ bị xoá (node 'wait-old'). Máy cũ xoá mãi chưa xong — máy chủ giữ nó mất kết nối > 3 phút,
       hoặc giả lập lỗi > 10 phút — thì web ghi máy cũ đã xoá (khách đằng nào cũng không mở được máy cũ) để máy mới được tạo.
       Máy ảo cũ còn sót trên máy chủ: admin bấm 🧹 Xoá sạch (phonectl dondep --xoa)."""
    rows = sb("GET", "cloud_phones?node=eq.wait-old&status=eq.pending&select=id,replaces") or []
    if not rows: return
    alive = {r.get("id") for r in live_nodes()}
    for w in rows:
        if not w.get("replaces"): continue
        o = (sb("GET", f"cloud_phones?id=eq.{w['replaces']}&select=id,status,node,updated_at,name,container") or [None])[0]
        if not o or o.get("status") == "cancelled":
            sb("PATCH", f"cloud_phones?id=eq.{w['id']}&node=eq.wait-old", {"node": None}, {"Prefer": "return=minimal"})
            print(f"[đổi Android] máy mới {w['id'][:8]} hết chờ (máy cũ đã xoá)"); continue
        if o.get("status") != "cancelling": continue
        try: age = (now() - parse_dt(o["updated_at"])).total_seconds()
        except Exception: age = 0
        off = bool(o.get("node")) and o["node"] not in alive
        if (off and age > 180) or age > 600:
            sb("PATCH", f"cloud_phones?id=eq.{o['id']}&status=eq.cancelling",
               {"status": "cancelled", "error": "Đổi Android: máy chủ chưa xoá kịp máy cũ — web ghi đã xoá để tạo máy mới ngay."},
               {"Prefer": "return=minimal"})
            why = f"máy chủ {o.get('node')} mất kết nối" if off else "giả lập chưa xoá được sau 10 phút"
            print(f"[đổi Android] {o.get('container') or o['id'][:8]}: {why} → web ghi máy cũ đã xoá, máy mới được tạo")
            notify(f"🧹 <b>Đổi Android</b>: máy cũ <b>{o.get('name') or ''}</b> ({o.get('container') or '?'}, {o.get('node') or '?'}) chưa xoá được ({why}) "
                   f"→ web ghi đã xoá để khách có máy mới. Máy ảo cũ còn sót: admin → ĐT đám mây → 🧹 Xoá sạch.")

_renew_note = {}
def do_renew(row):
    """Khách đã trả tiền gia hạn (hoặc admin cộng ngày) → cộng vào máy rồi ghi hạn mới lên web.
       CHỈ xoá số ngày chờ cộng khi máy chủ ĐÃ ghi được hạn mới (bản cũ xoá luôn dù phonectl không ghi được → khách mất ngày).
       Chưa ghi được → giữ nguyên, 15 giây sau thử lại, báo admin (1 lần / giờ / máy)."""
    name = row.get("container") or cname(row)
    d = int(row["pending_renew_days"])
    before = phone_state(name)
    old = parse_dt(before["expires"]) if before and before.get("expires") else None
    db_old = parse_dt(row["expires_at"]) if row.get("expires_at") else None
    gap = datetime.timedelta(days=d) - datetime.timedelta(minutes=5)
    if before and old and db_old and old >= db_old + gap:          # lần trước ĐÃ cộng vào máy chủ nhưng ghi lên web lỗi (mạng) → chỉ ghi lại, KHÔNG cộng lần 2
        print(f"[gia hạn] {name} +{d}n đã cộng từ lần trước → chỉ ghi hạn lên web")
        patch(row["id"], {"pending_renew_days": 0, "expires_at": old.isoformat(), "status": "active", "error": None, "stream_url": stream_url(before["port"])})
        return
    print(f"[gia hạn] {name} +{d}n")
    args = ["renew", name, "--days", str(d)]
    r = phonectl(args + (["--base", db_old.isoformat()] if db_old else []))      # cộng từ hạn muộn hơn (máy chủ / web)
    if r.returncode == 2 and "--base" in (r.stderr or ""):                       # phonectl cũ chưa hiểu --base
        r = phonectl(args)
    ps = phone_state(name)
    new = parse_dt(ps["expires"]) if ps and ps.get("expires") else None
    floor = max([x for x in (old, db_old) if x] or [now()])
    if not new or new < floor + gap:                                             # máy chủ CHƯA ghi được hạn mới (thước đo: file, không phải mã thoát)
        why = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-1:] or ["?"]
        print(f"   ⚠ gia hạn {name} CHƯA ghi được (giữ +{d} ngày chờ, thử lại sau): {why[0][:200]}")
        if time.time() - _renew_note.get(name, 0) > 3600:
            _renew_note[name] = time.time()
            try: notify(f"⚠️ <b>{NODE_ID}</b>: gia hạn máy <b>{row.get('name') or name}</b> +{d} ngày chưa ghi được — máy chủ tự thử lại mỗi 15 giây. Lý do: {why[0][:160]}")
            except Exception: pass
        return
    patch(row["id"], {"pending_renew_days": 0, "expires_at": new.isoformat(), "status": "active", "error": None, "stream_url": stream_url(ps["port"])})
    _renew_note.pop(name, None)

def do_expiry(row):
    """Hết hạn → tạm dừng (giữ dữ liệu 30 phút). Quá 30 phút → xoá máy + toàn bộ dữ liệu."""
    name = row.get("container") or cname(row)
    ps = phone_state(name)
    if int(row.get("pending_renew_days") or 0) > 0: return      # khách vừa gia hạn, máy chủ đang cộng → không tạm dừng / xoá
    ex = [parse_dt(x) for x in ((ps or {}).get("expires"), row.get("expires_at")) if x]
    exp = max(ex) if ex else None                            # lấy hạn MUỘN hơn (máy chủ / web) — lệch nhau thì không tắt nhầm máy khách
    if not exp: return
    t = now()
    m = maint_state()
    if m["on"]: return                       # đang bảo trì: không tạm dừng / không xoá máy khách
    start = max(exp, m["off_at"]) if m["off_at"] else exp   # hết hạn lúc bảo trì → 30 phút tính từ lúc tắt bảo trì
    if t > start + datetime.timedelta(minutes=GRACE_MIN):
        print(f"[xoá hết hạn] {name}")
        if ps: phonectl(["delete", name])
        patch(row["id"], {"status": "cancelled", "error": f"Hết hạn quá {GRACE_MIN} phút không gia hạn — máy và dữ liệu đã bị xoá."})
    elif t > exp and row["status"] == "active":
        print(f"[tạm dừng] {name} hết hạn, chờ gia hạn {GRACE_MIN} phút")
        if ps: phonectl(["stop", name])
        patch(row["id"], {"status": "expired"})

def tick_orders():
    """Việc cần làm ngay (mỗi 3 giây): tạo máy mới, huỷ máy."""
    for row in get_pending("pending"):
        try:
            if not claim(row): continue
            do_create(row)
        except Exception as e:
            if getattr(e, "code", 0) != 409: print("lỗi tạo:", e)
    for row in get_pending("cancelling"):
        if not mine(row): continue
        try: do_cancel(row)
        except Exception as e: print("lỗi huỷ:", e)

def tick():
    """Việc định kỳ (mỗi 15 giây): gia hạn, hết hạn."""
    for row in get_renew():
        if not mine(row): continue
        try: do_renew(row)
        except Exception as e: print("lỗi gia hạn:", e)
    for row in get_upgrade():
        if not mine(row): continue
        try: do_upgrade(row)
        except Exception as e: print("lỗi nâng cấp:", e)
    for row in get_live():
        if not mine(row): continue
        try: do_expiry(row)
        except Exception as e: print("lỗi hết hạn:", e)
    try: release_switch_waits()
    except Exception as e: print("lỗi đổi Android chờ máy cũ:", e)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(line_buffering=True)   # in log ngay để xem bằng journalctl
    except Exception: pass
    print(f"cloudphoned chạy — đọc {SB} mỗi {POLL}s. Ctrl+C để dừng.")
    try:                                    # nới RAM cho máy đang chạy (chống văng app khi hết RAM)
        r = phonectl(["memfix"]); print(r.stdout.strip())
    except Exception as e: print("lỗi memfix:", e)
    print(f"Server: {NODE_ID} ({'CHÍNH' if PRIMARY else 'phụ'}) · {BASE}")
    e = engine(); print(f"Giả lập: {e['emu'] or '?'} · nhận đơn Android: {', '.join(e['androids']) or 'mọi bản'}")
    adopt_old()
    n = 0; last = 0.0; _rootjob = [None]
    threading.Thread(target=_hb_loop, daemon=True).start()     # báo "còn sống" lên web ở luồng riêng
    while True:
        _loop_t[0] = time.time()
        try: tick_orders()                  # đơn mới: kiểm tra mỗi 3 giây → nhận đơn gần như tức thì
        except Exception as e: print("lỗi vòng lặp:", e)
        if time.time() - last < 15:
            time.sleep(3); continue
        last = time.time()
        try: tick()
        except Exception as e: print("lỗi vòng lặp:", e)
        try: phonectl(["connect-all"])      # mỗi 15 giây: máy nào rớt kết nối thì nối lại (tránh màn xám)
        except Exception as e: print("lỗi connect-all:", e)
        if n % 2 == 0:                      # ~30 giây: khoá / mở khoá / bật lại máy (báo cáo tài nguyên chạy ở luồng riêng _hb_loop)
            try: do_locks()
            except Exception as e: print("lỗi khoá máy:", e)
        if n % 20 == 5:                     # ~5 phút: cài app còn thiếu (máy nào lỡ) + mở quyền cài APK cho app khách mới cài
            try:
                r = phonectl(["preinstall", "--all"])
                for ln in (r.stdout or "").splitlines():
                    if ln.strip(): print("  ", ln.strip())
                phonectl(["perms"])
            except Exception as e: print("lỗi cài app sẵn / mở quyền APK:", e)
        if n % 20 == 12:                    # ~5 phút: máy nào chưa root → tự root (chạy nền, không chặn việc nhận đơn)
            try:
                if _rootjob[0] is None or _rootjob[0].poll() is not None:
                    _rootjob[0] = subprocess.Popen(["python3", PHONECTL, "rootfix", "--all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e: print("lỗi tự root:", e)
        n += 1
        time.sleep(3)
