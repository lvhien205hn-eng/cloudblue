#!/usr/bin/env python3
# cloudphoned.py — Chương trình nền: đọc đơn từ Supabase (cloud_phones) → gọi phonectl tạo/xoá/gia hạn máy.
# Cấu hình đọc từ ~/cloudphone.conf (KEY=VALUE), KHÔNG đưa khoá bí mật lên GitHub.
#   SUPABASE_URL=https://xxxx.supabase.co
#   SUPABASE_SERVICE_KEY=eyJ...            (service_role key — bí mật)
#   PUBLIC_BASE=https://xxxx.trycloudflare.com   (link ws-scrcpy ra internet)
# Chạy:  python3 ~/cloudphoned.py           (vòng lặp mỗi 15s)
import json, os, re, sys, time, subprocess, tempfile, urllib.request, urllib.parse, urllib.error, datetime, socket, shutil, threading
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
WIN_VCPU_OVER = _f("WIN_VCPU_OVER", 0.9)        # (chỉ dùng khi ghi rõ trong cloudphone.conf) tổng nhân ảo ≤ ×K số luồng thật
# 14/11 — TRẦN CỨNG mỗi máy chủ Windows (admin: "130 nhân máy không chịu nổi, cứ sập"): đã cấp tới 68 nhân hoặc 112GB RAM là NGỪNG
# nhận máy mới / nâng cấp. Không bán vượt ("buff"): máy NGỦ tính đủ RAM + nhân đã cấp, RAM bán không vượt RAM thật − WIN_RAM_RESERVE,
# nhân bán không vượt số luồng thật − CPU_KEEP. Máy đang có KHÔNG bị tắt bớt — chỉ ngừng nhận thêm tới khi xuống dưới trần.
# Đổi trong cloudphone.conf: CAP_CPU=68 · CAP_RAM=112 (0 = bỏ trần, tính như trước 14/11) · CPU_KEEP=4
CAP_CPU, CAP_RAM, CPU_KEEP = _f("CAP_CPU", 68), _f("CAP_RAM", 112), _f("CPU_KEEP", 4)
# ---------- Máy NGỦ giữ bao nhiêu RAM (Windows) ----------
# Trước 13/11: mỗi máy ngủ giữ ĐỦ RAM đã cấp (máy 6GB giữ 6GB) trong khi máy đang chạy thật chỉ dùng ~3GB → win1 (14 máy,
# 9 máy ngủ) báo ĐẦY lúc RAM thật mới dùng 32%. Giờ máy ngủ giữ đúng phần RAM THẬT 1 máy đang chạy dùng (đo trên chính
# máy chủ này) → mọi máy ngủ cùng thức một lúc vẫn đủ RAM. RAM_OVER (dùng chung ×K) > 1 → giữ ít hơn K lần, bán được nhiều
# hơn nhưng nếu quá nhiều máy ngủ cùng thức thì RAM có thể thiếu (giả lập giật / không bật được). Thiếu dòng RAM_OVER → ×1.
RAM_RATIO_F = os.path.join(HOME, "redroid", "ram_ratio.json")   # cloudphoned ghi mỗi 30 giây · phonectl đọc (tạo / nâng máy)
RATIO_HOURS, RATIO_MIN_N, RATIO_FLOOR = 12, 6, 0.5   # mức cao nhất 12 giờ qua · giờ cần ≥ 6 lần đo (3 phút) · giữ tối thiểu 50%
_ram_rt = {"h": {}}       # {giờ: [tổng tỉ lệ, số lần đo]} — chỉ luồng báo cáo thay CẢ bảng (luồng nhận đơn đọc bảng cũ không lỗi)
def _rr_load():
    """Đọc lại số đo cũ: khởi động lại cloudphoned / Windows không mất (máy vừa bật lại chưa chạy game → đo thấp hơn thật)."""
    try:
        with open(RAM_RATIO_F, encoding="utf-8") as f: d = json.load(f)
        t_h = int(time.time() // 3600)
        _ram_rt["h"] = {int(k): [float(v[0]), int(v[1])] for k, v in (d.get("h") or {}).items() if int(k) > t_h - RATIO_HOURS}
    except Exception: pass
def ram_ratio(sample=None):
    """RAM THẬT 1 máy ĐANG CHẠY dùng ÷ RAM đã cấp cho nó: lấy giờ CAO NHẤT trong 12 giờ qua (TB từng giờ), kẹp 0,5–1.
       Chưa đo được (vừa cài, không máy nào chạy) → 1 = giữ đủ RAM đã cấp như cũ. Truyền sample = thêm 1 lần đo (luồng báo cáo)."""
    t_h = int(time.time() // 3600)
    if sample is not None:
        h = {k: list(v) for k, v in _ram_rt["h"].items() if k > t_h - RATIO_HOURS}
        s = h.setdefault(t_h, [0.0, 0]); s[0] += sample; s[1] += 1
        _ram_rt["h"] = h
    v = [x[0] / x[1] for k, x in _ram_rt["h"].items() if k > t_h - RATIO_HOURS and x[1] >= RATIO_MIN_N]
    return max(RATIO_FLOOR, min(1.0, max(v))) if v else 1.0
def sleep_reserve(st):
    """(GB RAM giữ cho máy NGỦ, GB RAM đã cấp của chúng, số máy ngủ). Khách mở máy là bật lại → phần giữ không bán cho máy mới."""
    zz = [min(float(p.get("ram", 0)), MEMU_MAX_RAM) for p in st if p.get("sleep") and p.get("hold")]
    return sum(zz) * ram_ratio() / WIN_RAM_OVER, sum(zz), len(zz)
def ram_sample(st, rn, ram_t, ram_avail):
    """Luồng báo cáo (30 giây/lần): đo (RAM thật đang dùng − phần của Windows WIN_RAM_RESERVE) ÷ RAM đã cấp của các máy ĐANG
       CHẠY (cần ≥ 8GB đang chạy cho số đo đáng tin)."""
    a_run = sum(min(float(p.get("ram", 0)), MEMU_MAX_RAM) for p in st
                if rn and p.get("name") in rn and not (p.get("sleep") and p.get("hold")))
    if a_run >= 8: ram_ratio(max(0.0, min(1.5, (ram_t - ram_avail - WIN_RESERVE) / a_run)))
def rr_write(st, a_ram, c_ram):
    """Ghi ram_ratio.json (30 giây/lần): phonectl đọc "factor" khi tạo / nâng máy (cùng mức với web + nhận đơn) · lệnh cập nhật
       đọc để in kết quả. Trả (GB giữ cho máy ngủ, GB đã cấp của chúng, số máy ngủ)."""
    zz, full, n = sleep_reserve(st); h = _ram_rt["h"]; t_h = int(time.time() // 3600)
    try:
        tmp = RAM_RATIO_F + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"t": time.time(), "factor": round(ram_ratio() / WIN_RAM_OVER, 4), "ratio": round(ram_ratio(), 3), "over": WIN_RAM_OVER,
                       "measured": any(k > t_h - RATIO_HOURS and v[1] >= RATIO_MIN_N for k, v in h.items()),
                       "sleeping": n, "sleep_gb": round(zz, 1), "sleep_full_gb": round(full, 1), "alloc_gb": round(a_ram, 1), "cap_gb": round(c_ram, 1),
                       "h": {str(k): [round(v[0], 6), v[1]] for k, v in h.items()}}, f)
        os.replace(tmp, RAM_RATIO_F)
    except Exception as e: print("lỗi ghi ram_ratio.json:", e)
    return zz, full, n
def want(row):
    """RAM/CPU THẬT sẽ cấp cho đơn: Windows/MEmu tối đa 16GB · 16 nhân mỗi máy (gói to hơn vẫn nhận, chạy mức tối đa)."""
    r, c = float(row.get("ram") or 0), float(row.get("cpu") or 0)
    return (min(r, MEMU_MAX_RAM), min(c, MEMU_MAX_CPU)) if WIN else (r, c)
def win_caps(st):
    """Windows: sức chứa theo RAM TRỐNG THẬT (máy ảo đang chạy đã trừ sẵn) chứ không cộng dồn cấu hình;
       CPU dùng chung (72 luồng) → chỉ ngừng khi CPU thật đã nóng. Trả (đã cấp RAM, đã cấp CPU, trần RAM, trần CPU)."""
    a_r = sum(min(float(p.get("ram", 0)), MEMU_MAX_RAM) for p in st); a_c = sum(min(float(p.get("cpu", 0)), MEMU_MAX_CPU) for p in st)
    t_r, av_r = meminfo(); cpu_t = os.cpu_count() or 1
    hot = bool(t_r) and 100 * (1 - av_r / t_r) >= RAM_BUSY   # RAM THẬT đã đầy (chưa tính phần giữ cho máy ngủ)
    av_r -= sleep_reserve(st)[0]                              # máy NGỦ bật lại khi khách mở → chừa RAM thật của chúng, không bán
    c_r = a_r + max(0.0, av_r - WIN_RESERVE - 1)             # −1GB: khớp phonectl create (máy mới cần thêm 1GB) → web / nhận đơn / tạo máy cùng một mức, không nhận rồi hoàn tiền
    c_c = a_c + cpu_t * CPU_OVER
    if CAP_CPU > 0:                                          # 14/11: trần cứng nhân (68 · không vượt luồng thật − 4)
        lim = min(CAP_CPU, max(1.0, cpu_t - CPU_KEEP))
        if "WIN_VCPU_OVER" in CFG: lim = min(lim, cpu_t * WIN_VCPU_OVER)
        c_c = max(a_c, min(c_c, lim))
    else:
        c_c = max(a_c, min(c_c, cpu_t * WIN_VCPU_OVER))      # TỰ GIỚI HẠN: tổng nhân ảo không vượt số luồng thật
    if CAP_RAM > 0:                                          # 14/11: trần cứng RAM (112GB · không vượt RAM thật − phần của Windows)
        c_r = max(a_r, min(c_r, CAP_RAM, (t_r - WIN_RESERVE) if t_r else CAP_RAM))
    if (cpu_avg5() or 0) >= CPU_BUSY: c_c = a_c
    if hot: c_r = a_r
    if disk_full(): c_r = a_r
    if gpu_busy(): c_r, c_c = a_r, a_c                         # card đồ hoạ / VRAM quá tải → hết chỗ, đơn mới sang máy chủ khác
    if MEMU_MAX_VMS > 0 and len(st) >= MEMU_MAX_VMS: c_r, c_c = a_r, a_c   # đủ số máy tối đa → báo HẾT CHỖ, web ngừng bán
    return a_r, a_c, c_r, c_c

def local_load():
    """(phần trăm đã cấp, còn RAM, còn CPU) của server này theo ngưỡng LIMIT_PCT."""
    try: st = json.load(open(PHONES_JSON)).get("phones", [])
    except Exception: st = []
    gl = (gpu_avg5()[0] or 0) / 100                     # card đồ hoạ bận → nhường máy chủ card rảnh hơn nhận trước
    if WIN:
        a_r, a_c, c_r, c_c = win_caps(st)
        return max(a_r / max(c_r, 1), (cpu_avg5() or 0) / 100, gl), sell_cap(a_r, c_r) - a_r, sell_cap(a_c, c_c) - a_c   # đạt 95% → không nhận
    ram_t = meminfo()[0]; cpu_t = os.cpu_count() or 1
    a_r = sum(float(p.get("ram", 0)) for p in st); a_c = sum(float(p.get("cpu", 0)) for p in st)
    c_r, c_c = ram_t * LIMIT_PCT / 100 * RAM_OVER, cpu_t * CPU_OVER
    busy = (cpu_avg5() or 0) >= CPU_BUSY
    if busy: c_c = a_c                                  # CPU thật đã nóng → coi như hết chỗ CPU
    t_r, av_r = meminfo()
    if t_r and 100 * (1 - av_r / t_r) >= RAM_BUSY: c_r = a_r          # RAM thật đã đầy → coi như hết chỗ RAM
    if disk_full(): c_r = a_r                                           # ổ cứng sắp đầy → không nhận máy mới
    if gpu_busy(): c_r, c_c = a_r, a_c                                  # card đồ hoạ / VRAM quá tải → không nhận máy mới
    return max(a_r / max(c_r, 1), (cpu_avg5() or 0) / 100, gl), c_r - a_r, c_c - a_c

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
_eng = {"emu": "", "androids": [], "none": False, "missing": [], "t": 0.0, "bad": 0}
ENG_RETRY_S = 15            # lúc bật mà đọc ra "không bản nào" → đọc lại 1 lần sau 15 giây
def engine(refresh=False):
    """none = THẤY giả lập mà KHÔNG bản Android nào tạo được (VD MuMu thiếu máy mẫu tpl_a12 / tpl_a15) → không nhận đơn nào.
       13/11: trước đây danh sách rỗng bị hiểu là "nhận mọi bản" + web coi là máy chủ Android 9 → win5 (MuMu) hiện thành LD9,
       giành đơn Android 9 rồi tạo lỗi, hoàn tiền. refresh: luồng báo cáo đọc lại định kỳ (tạo máy mẫu xong là bán lại, khỏi khởi động lại)."""
    if refresh or not _eng["emu"]:
        first = not _eng["emu"]
        _engine_read()
        if first and _eng.get("none"):       # 13/11 win5: giả lập đang NHÂN BẢN máy mẫu → đọc danh sách thiếu đúng lúc đó → đọc lại
            time.sleep(ENG_RETRY_S); _engine_read()
    return _eng
def _engine_read():
    try:
        r = phonectl(["engine"]); j = json.loads((r.stdout or "").strip().splitlines()[-1])
        av = [str(x) for x in j.get("androids") or []]
        if _eng["emu"] and not _eng.get("none") and set(av) < set(_eng["androids"]):
            # ÍT bản hơn lần trước: có thể chỉ đọc thiếu 1 lúc (giả lập đang nhân bản máy mẫu để tạo máy khách) → giữ kết quả cũ,
            # ~1 phút sau đọc lại; 3 lần liền vẫn thiếu mới tin (bớt bản / báo thiếu máy mẫu)
            _eng["bad"] = _eng.get("bad", 0) + 1
            if _eng["bad"] < 3: _eng["t"] = time.time() - 540; return
        _eng.update(emu=j.get("emu") or "", androids=av, none=bool(j.get("found")) and not av,
                    missing=[str(x) for x in j.get("missing_tpl") or []], t=time.time(), bad=0)
    except Exception:
        if not _eng["emu"]:
            _eng.update(emu=CFG.get("EMU", "") or "", androids=[x.strip() for x in (CFG.get("ANDROIDS") or "").split(",") if x.strip()],
                        t=time.time())
        else: _eng["t"] = time.time()                # đọc lại lỗi → giữ kết quả cũ, lần sau thử lại
# Bản Android bán ở máy chủ RIÊNG (LDPlayer 9 · MEmu 7/12 · MuMu 12/15…). Máy chủ chính KHÔNG được nhận các bản này nếu nó
# không bán — trước đây thiếu "15" → máy chủ chính (LDPlayer, Android 9) giành đơn Android 15 rồi tạo nhầm Android 9.
KNOWN_ANDROIDS = ("7", "9", "12", "13", "14", "15", "16")
def android_ok(row):
    """Đơn này đúng bản Android máy chủ này bán? (đơn cũ không ghi bản / máy chủ chưa khai báo → nhận như cũ)"""
    e = engine()
    if e.get("none"): return False          # có giả lập mà không bản nào tạo được (thiếu máy mẫu) → không nhận đơn nào
    av = e["androids"]
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
try: WIN_RAM_OVER = max(1.0, min(4.0, float(CFG.get("RAM_OVER", "1"))))   # Windows: máy NGỦ giữ RAM thật ÷ ×K — thiếu dòng RAM_OVER → ×1 (an toàn)
except ValueError: WIN_RAM_OVER = 1.0
try: RAM_BUSY = max(30, min(98, int(CFG.get("RAM_BUSY_PCT", "85"))))   # RAM thật ≥ 85% → ngừng nhận máy mới
except ValueError: RAM_BUSY = 85
try: DISK_BUSY = max(50, min(98, int(CFG.get("DISK_BUSY_PCT", "90"))))  # ổ cứng ≥ 90% → ngừng nhận máy mới
except ValueError: DISK_BUSY = 90
try: FULL_PCT = max(50.0, min(100.0, float(CFG.get("FULL_PCT", "100"))))  # Windows: đã cấp tới N% sức chứa → NGỪNG nhận máy mới. 14/11: trần cứng
except ValueError: FULL_PCT = 100.0                                         #   68 nhân / 112GB đã là điểm ngừng → mặc định 100% (13/11 là 95%)
def sell_cap(a, c, pct=None):
    """Sức chứa BÁN = pct % (mặc định FULL_PCT) sức chứa thật, không thấp hơn phần đã cấp (máy đang có vẫn chạy bình thường).
       Báo lên web đúng số này → web, nâng cấp, chia đơn đều ngừng ở 95%; % đầy THẬT báo riêng trong metrics (fill_pct)."""
    return max(a, c * (FULL_PCT if pct is None else pct) / 100)
def _busy_pct(k, d, lo, hi):
    """Ngưỡng % trong cloudphone.conf — 0 = tắt kiểm tra này."""
    try: v = int(float(CFG.get(k, d)))
    except (TypeError, ValueError): v = d
    return 0 if v <= 0 else max(lo, min(hi, v))
GPU_BUSY = _busy_pct("GPU_BUSY_PCT", 85, 30, 100)    # card đồ hoạ dùng ≥ 85% (TB 5 phút) → ngừng nhận máy mới, đơn sang máy chủ khác
VRAM_BUSY = _busy_pct("VRAM_BUSY_PCT", 90, 50, 99)   # bộ nhớ card (VRAM) ≥ 90% (TB 5 phút) → ngừng nhận máy mới
_gpu_hist = []                                       # (giờ, % card cao nhất, % VRAM cao nhất) — đo mỗi 30 giây ở luồng báo cáo
def gpu_avg5(sample=None):
    """(% card đồ hoạ TB ~5 phút, % VRAM TB ~5 phút) — máy nhiều card lấy card cao nhất; chưa đo được → None.
       Truyền sample (kết quả gpus()) để thêm 1 lần đo; không truyền thì chỉ đọc số đã đo (không gọi nvidia-smi)."""
    t = time.time()
    if sample is not None:                           # chỉ luồng báo cáo ghi / bỏ số cũ (luồng nhận đơn chỉ đọc bản chụp)
        u = [g["util"] for g in sample if g.get("util") is not None]
        v = [100 * g["mem_used"] / g["mem_total"] for g in sample if g.get("mem_used") is not None and g.get("mem_total")]
        if u or v: _gpu_hist.append((t, max(u) if u else None, max(v) if v else None))
        while _gpu_hist and t - _gpu_hist[0][0] > 300: _gpu_hist.pop(0)
    h = [x for x in list(_gpu_hist) if t - x[0] <= 300]   # luồng báo cáo dừng → số cũ hết hạn sau 5 phút
    us = [x[1] for x in h if x[1] is not None]; vs = [x[2] for x in h if x[2] is not None]
    return (round(sum(us) / len(us), 1) if us else None), (round(sum(vs) / len(vs), 1) if vs else None)
def gpu_busy():
    """Card đồ hoạ quá tải → "gpu" (dùng ≥ GPU_BUSY_PCT) / "vram" (VRAM ≥ VRAM_BUSY_PCT) / "" (bình thường)."""
    u, v = gpu_avg5()
    if GPU_BUSY and u is not None and u >= GPU_BUSY: return "gpu"
    if VRAM_BUSY and v is not None and v >= VRAM_BUSY: return "vram"
    return ""
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
    if threading.current_thread() is threading.main_thread():
        _loop_t[0] = max(_loop_t[0], time.time())     # 14/11: vòng nhận đơn vẫn đang nhích (nhiều máy → 1 lượt dài) → không báo "đứng" nhầm
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

# Hạn chờ từng lệnh phonectl (giây). Trước 13/11 KHÔNG có hạn → 1 lệnh treo (giả lập / adb không trả lời) làm vòng nhận đơn đứng
# MÃI: luồng báo cáo vẫn báo "còn sống" 30 phút nên web vẫn chia đơn cho máy chủ này, mà máy chủ không nhận, không làm gì.
# Quá hạn → tắt riêng lệnh đó (mã 124), máy chủ chạy tiếp. Hạn rộng hơn hẳn thời gian thật (tạo máy MuMu nhân bản vài phút…).
PCTL_T = {"connect-all": 300, "perms": 300, "list": 120, "show": 120, "hide": 120, "capacity": 120, "engine": 300, "memfix": 600,
          "idle": 900, "preinstall": 1800, "stop": 600, "start": 900, "waitboot": 1200, "renew": 1200, "delete": 1200,
          "resize": 1800, "create": 2400}
PCTL_T_DEF = 1800
_pc_main = {"args": None, "t": 0.0, "to": 0}     # lệnh phonectl mà VÒNG NHẬN ĐƠN đang chờ → luồng tự kiểm biết nó đứng vì đâu

def _run_tf(cmd, timeout):
    """Chạy 1 lệnh, kết quả ghi ra FILE tạm (KHÔNG dùng pipe — cùng cách phonectl.run): pipe mà bị chương trình con (adb server,
       giả lập…) giữ đầu ghi thì Python chờ MÃI, kể cả khi đã quá giờ. Quá giờ → tắt RIÊNG chương trình đó (không tắt cả cây:
       giả lập / adb server của khách có thể là "con" của nó). Trả về (mã, out, err, quá_giờ)."""
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        try: p = subprocess.Popen(cmd, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL)
        except Exception as e: return 127, "", str(e), False
        hung = False
        try: code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            hung = True
            try: p.kill()
            except Exception: pass
            try: p.wait(timeout=10)
            except Exception: pass
            code = 124
        fo.seek(0); fe.seek(0)
        dec = lambda b: b.decode("utf-8", "replace").replace("\r\n", "\n")
        return code, dec(fo.read()), dec(fe.read()), hung

def _dur(sec):
    sec = int(sec)
    return f"{sec // 60} phút" if sec >= 120 else f"{sec} giây"

def phonectl(args, timeout=None):
    args = [str(x) for x in args]
    to = int(timeout or PCTL_T.get(args[0] if args else "", PCTL_T_DEF))
    main = threading.current_thread() is threading.main_thread()
    if main: _pc_main.update(args=args[:2], t=time.time(), to=to)
    cmd = ["python3", PHONECTL] + args
    try:
        code, out, err, hung = _run_tf(cmd, to)
        if hung:
            msg = f"lệnh phonectl {' '.join(args[:2])} treo quá {_dur(to)} → đã tắt riêng lệnh đó, máy chủ chạy tiếp"
            err = (err.rstrip() + "\n" if err.strip() else "") + msg
            ts_note(msg, key="pctl_" + (args[0] if args else ""), every=1800)     # 14/11: không nhắn Telegram (tin rác)
        return subprocess.CompletedProcess(cmd, code, out, err)
    finally:
        if main:
            _pc_main.update(args=None, t=0.0, to=0)
            _loop_t[0] = max(_loop_t[0], time.time())     # xong 1 lệnh = vòng nhận đơn vẫn đang nhích

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
            refund(row, "Máy chủ đã đầy, chưa tạo được máy"); notify(f"⚠️ <b>Đơn ĐT đám mây bị hoàn tiền</b> vì {NODE_ID} đã đầy {FULL_PCT if WIN else LIMIT_PCT:g}%."); return
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
        r = phonectl(["waitboot", name, "--noapps"])   # chỉ chờ Android lên → giao máy cho khách NGAY
        # 14/11: Android chưa lên sau 5 phút (máy chủ bận / MuMu nhân bản máy mẫu lâu — hay gặp khi ĐỔI ANDROID) → bản cũ vẫn
        # giao máy → khách mở thấy MÀN ĐEN, bấm không được. Giờ: chờ thêm 1 lượt → vẫn chưa thì ép khởi động lại 1 lần → mới giao.
        if r.returncode in (5, 124):
            print(f"   … {name}: Android chưa lên sau {time.time() - t0:.0f}s → chờ thêm 1 lượt (chưa giao cho khách, tránh màn đen)")
            r = phonectl(["waitboot", name, "--noapps"])
        if r.returncode in (5, 124):
            print(f"   … {name}: vẫn chưa lên sau {time.time() - t0:.0f}s → ép khởi động lại 1 lần")
            phonectl(["restart", name, "--force"])
            r = phonectl(["waitboot", name, "--noapps"])
        if r.returncode in (5, 124):
            print(f"   ⚠ {name}: Android vẫn chưa lên sau {(time.time() - t0) / 60:.0f} phút — vẫn giao, bảng CloudBlue tự chống kẹt")
            notify(f"⚠️ <b>{NODE_ID}</b>: máy mới <b>{name}</b> chờ {(time.time() - t0) / 60:.0f} phút (đã ép khởi động lại 1 lần) mà Android "
                   f"chưa lên — vẫn giao cho khách. Khách báo màn đen thì xem máy này.")
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

# ---------------- TỰ KIỂM · TỰ SỬA (13/11) ----------------
# 13/11: 1 máy chủ "không nhận đơn mà cũng chả làm gì" = vòng nhận đơn đứng (chờ 1 lệnh không có hạn), trong khi luồng báo cáo
# vẫn báo "còn sống" tới 30 phút → web vẫn chia đơn cho nó. Giờ:
#   • mọi lệnh phonectl có hạn chờ (PCTL_T); cài app sẵn / nối lại adb chạy ở LUỒNG RIÊNG, không chặn việc nhận đơn
#   • luồng tự kiểm (30 giây/lần):
#       – vòng nhận đơn không nhích quá TS_STUCK_MIN phút → in chỗ đứng (Telegram chỉ khi lặp lại trong 1 giờ) → TỰ THOÁT, bảng CloudBlue / systemd
#         bật lại sau 5 giây (đơn đang làm dở: máy đã tạo thì bản mới chờ Android lên rồi giao tiếp, không tạo trùng)
#       – đọc đơn từ Supabase lỗi liên tục: 10 phút → báo admin · 30 phút → tự khởi động lại (đọc lại cloudphone.conf)
#       – Windows: phát hình (bluestream) ĐÓNG CỔNG 3 lần liền (~3 phút) → tắt tiến trình phát hình chính, bảng CloudBlue tự
#         bật lại (tối đa 3 lần / giờ; quá → chỉ báo admin). Mở cổng mà chậm trả lời → chỉ ghi nhật ký (14/11: không tắt nữa)
#       – Windows: máy khách đang chạy mà màn hình Android TẮT (khách bấm nút nguồn…) → bật sáng (~2 phút/lần). Phát hình
#         chạy scrcpy với power_on=false nên màn tắt = khách thấy MÀN ĐEN.
# Mỗi lần: dòng "🩺 tự sửa: …" trong nhật ký + redroid/tusua.json (20 lần gần nhất). Tắt hết: TUSUA=0 trong cloudphone.conf.
TS_ON = CFG.get("TUSUA", "1") != "0"
TS_STUCK_MIN = max(3.0, _f("TS_STUCK_MIN", 10))
TS_F = os.path.join(HOME, "redroid", "tusua.json")
_ts = {"ev": [], "noti": {}, "bs_bad": 0, "bs_seen": False, "bs_kill": 0.0, "bs_kills": [], "err_t": 0.0, "err_msg": ""}
_ts_exit = os._exit

def _ts_save():
    try:
        os.makedirs(os.path.dirname(TS_F), exist_ok=True)
        tmp = TS_F + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"node": NODE_ID, "events": _ts["ev"][-20:], "noti": _ts["noti"]}, f, ensure_ascii=False)
        os.replace(tmp, TS_F)
    except Exception: pass

def _ts_load():
    """Nhớ lần nhắn Telegram trước qua các lần khởi động lại → tự thoát lặp lại không nhắn dồn."""
    try:
        j = json.load(open(TS_F, encoding="utf-8"))
        _ts["ev"] = list(j.get("events") or [])[-20:]
        _ts["noti"] = {str(k): float(v) for k, v in (j.get("noti") or {}).items()}
    except Exception: pass

def ts_note(what, tg=False, key=None, every=600, again=True):
    """Ghi 1 lần tự kiểm / tự sửa: nhật ký "🩺 tự sửa: …" + redroid/tusua.json. tg=True → nhắn Telegram admin, mỗi loại (key)
       tối đa 1 tin / every giây. again=False → việc lặp lại trong every giây thì không ghi lại (tránh rác nhật ký)."""
    k = key or what[:40]; t = time.time()
    fresh = t - float(_ts["noti"].get(k, 0)) > every
    if not fresh and not again: return False
    print(f"🩺 tự sửa: {what}", flush=True)
    ev = _ts["ev"]; ev.append({"t": int(t), "what": what}); del ev[:-20]
    if fresh: _ts["noti"][k] = t
    _ts_save()
    if tg and fresh:
        w = what.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        notify(f"🩺 <b>{NODE_ID}</b> tự sửa: {w}")
    return True

def ts_stuck_check(now=None):
    """Vòng nhận đơn có đứng không → (đứng, mô tả). Đang chờ 1 lệnh phonectl thì chỉ coi là đứng khi quá hạn lệnh đó + 3 phút."""
    now = now or time.time()
    idle = now - _loop_t[0]
    pc = dict(_pc_main)
    if pc.get("args"):
        waited = now - pc["t"]
        return (waited > pc["to"] + 180 and idle > TS_STUCK_MIN * 60), f"chờ lệnh phonectl {' '.join(pc['args'])} {waited / 60:.0f} phút"
    return idle > TS_STUCK_MIN * 60, f"{idle / 60:.0f} phút không chạy hết 1 lượt"

def ts_main_stack():
    try:
        import traceback
        fr = sys._current_frames().get(threading.main_thread().ident)
        return "".join(traceback.format_stack(fr)[-6:]) if fr else ""
    except Exception:
        return ""

def ts_loop_err(now=None):
    """Đọc đơn từ Supabase lỗi LIÊN TỤC: 10 phút → báo admin · 30 phút → True (tự khởi động lại: đọc lại cloudphone.conf, kết nối mới)."""
    t0 = _ts.get("err_t") or 0
    if not t0: return False
    m = ((now or time.time()) - t0) / 60
    why = _ts.get("err_msg") or "?"
    if m >= 30:
        ts_note(f"đọc đơn từ Supabase lỗi liên tục {m:.0f} phút ({why}) → tự khởi động lại", tg=True, key="sb_err_restart", every=3600)
        return True
    if m >= 10:
        ts_note(f"đọc đơn từ Supabase lỗi liên tục {m:.0f} phút: {why} — kiểm tra mạng / khoá Supabase trong cloudphone.conf",
                tg=True, key="sb_err", every=3600, again=False)
    return False

def _conf_ports():
    """Cổng phát hình — đọc LẠI cloudphone.conf mỗi lần (bluestream --netcheck --fix có thể đổi STREAM_PORT lúc máy chủ đang chạy)."""
    c = {}
    try:
        for ln in open(CONF, encoding="utf-8"):
            if "=" in ln and not ln.lstrip().startswith("#"):
                a, b = ln.split("=", 1); c[a.strip().lstrip("\ufeff")] = b.strip()
    except Exception:
        c = CFG
    def num(k, d):
        try: return int(c.get(k) or d)
        except Exception: return d
    return num("STREAM_PORT", 8189), num("STREAM_WS_PORT", 8020)

def _listening(ports):
    """Cổng nào ĐANG NGHE (netstat). None = không đọc được (không kết luận gì)."""
    code, out, _, _ = _run_tf(["netstat", "-ano"], 30)
    if not out.strip(): return None
    return {p for p in ports if re.search(r":%d\s+(?:0\.0\.0\.0|\[::\]):0\s" % int(p), out)}

def _ws_probe(port, t=8):
    """Phát hình còn TRẢ LỜI không: hỏi HTTP thường vào cổng WebSocket nội bộ — bluestream trả "BlueRoblox stream v2" và không ghi
       nhật ký. Vòng xử lý của nó bị treo thì cổng vẫn mở (Windows vẫn nhận kết nối) nhưng không ai trả lời → app khách quay mãi."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=t) as s:
            s.settimeout(t)
            s.sendall(b"GET /tusua HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            return s.recv(16).startswith(b"HTTP/")
    except Exception:
        return False

def _bs_pids():
    """PID tiến trình phát hình CHÍNH (bảng CloudBlue chạy: python -u bluestream.py — không kèm tham số; các lệnh kiểm
       --netcheck / --captest… có tham số → không đụng)."""
    code, out, _, _ = _run_tf(["powershell", "-NoProfile", "-Command",
                               "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                               "$_.CommandLine -match 'bluestream\\.py\\W*$' } | ForEach-Object { $_.ProcessId }"], 60)
    return [int(x) for x in out.split() if x.strip().isdigit()]

def ts_bluestream(now=None):
    """Windows · ~1 phút/lần: phát hình (bluestream) còn MỞ CỔNG không. Cổng đóng 3 lần liền (~3 phút) mà tiến trình phát hình vẫn
       còn (kẹt lúc khởi động / hỏng giữa chừng) → tắt RIÊNG tiến trình đó (không tắt cả cây: giữ adb server) → bảng CloudBlue tự
       bật lại sau 5 giây. Tối đa 3 lần / giờ; quá → chỉ báo admin.
       14/11: cổng MỞ mà hỏi không trả lời (máy chủ đang bận, nhiều khách xem) → CHỈ ghi nhật ký, KHÔNG tắt. Bản 13/11 tắt luôn
       trường hợp này → mọi khách đang xem trên máy chủ đó bị ngắt cùng lúc, mở lại thấy màn đen + Telegram báo liên tục."""
    if not os.path.isfile(os.path.join(HOME, "bluestream.py")): return None
    now = now or time.time()
    port, wsp = _conf_ports()
    up = _listening([port, wsp])
    if up is None: return None
    closed = [p for p in (port, wsp) if p not in up]
    s = _ts
    if not closed:
        if s["bs_kill"]: ts_note(f"phát hình đã chạy lại sau {(now - s['bs_kill']) / 60:.0f} phút"); s["bs_kill"] = 0.0
        s["bs_seen"] = True; s["bs_bad"] = 0
        if not _ws_probe(wsp, 15):
            ts_note(f"phát hình mở cổng nhưng hỏi cổng {wsp} không trả lời trong 15 giây (máy chủ bận?) — chỉ ghi lại, KHÔNG tắt",
                    key="bs_slow", every=3600, again=False)
            return "slow"
        return "ok"
    s["bs_bad"] += 1
    if s["bs_bad"] < 3: return "wait"
    why = ", ".join(f"cổng {p} đóng" for p in closed)
    if s["bs_kill"]:
        if now - s["bs_kill"] < 150: return "waitback"         # vừa tắt: chờ bảng CloudBlue bật lại (5 giây) + bluestream mở cổng
        s["bs_kill"] = 0.0
        pids = _bs_pids()
        if not pids:
            ts_note(f"phát hình CHƯA chạy lại sau khi tự tắt ({why}) → mở bảng CloudBlue bấm ▶ Bật tất cả", tg=True, key="bs_back", every=3600)
            return "noback"
    else:
        pids = _bs_pids()
    if not pids:
        if s["bs_seen"]:
            ts_note(f"phát hình (bluestream) không chạy ({why}) — bảng CloudBlue chưa bật lại thì bấm ▶ Bật tất cả",
                    tg=True, key="bs_dead", every=3600, again=False)
        return "dead"
    s["bs_kills"] = [t for t in s["bs_kills"] if now - t < 3600]
    if len(s["bs_kills"]) >= 3:
        ts_note(f"phát hình hỏng lặp lại ({why}) — đã tự bật lại 3 lần trong 1 giờ, không tự tắt nữa: cần xem tay (nhật ký phat-hinh)",
                tg=True, key="bs_loop", every=3600, again=False)
        return "loop"
    for pid in pids: _run_tf(["taskkill", "/PID", str(pid), "/F"], 30)
    s["bs_kill"] = now; s["bs_kills"].append(now); s["bs_bad"] = 0
    ts_note(f"phát hình (bluestream) đóng cổng ~3 phút ({why}) → đã tắt để bảng CloudBlue bật lại", tg=True, key="bs_hang", every=1800)
    return "killed"

def ts_wake_screens():
    """Windows · ~2 phút/lần: máy khách đang chạy mà màn hình Android TẮT → bật sáng (KEYCODE_WAKEUP: máy đang sáng thì không gửi gì).
       Bỏ qua máy đang tắt / ngủ / tạm dừng (hold)."""
    try: st = json.load(open(PHONES_JSON, encoding="utf-8")).get("phones", [])
    except Exception: return 0
    woke = []
    for p in st:
        if p.get("hold") or p.get("sleep") or not p.get("port") or p.get("kind") == "gpu": continue
        s = f"127.0.0.1:{p['port']}"
        code, out, _, _ = _run_tf(["adb", "-s", s, "shell", "dumpsys power | grep mWakefulness="], 12)
        if "mWakefulness=" in out and "mWakefulness=Awake" not in out:
            _run_tf(["adb", "-s", s, "shell", "input keyevent 224"], 12); woke.append(str(p.get("name")))
    if woke: ts_note(f"bật sáng màn hình {len(woke)} máy khách đang tắt màn: {', '.join(woke[:6])}" + (" …" if len(woke) > 6 else ""))
    return len(woke)

def _ts_loop():
    k = 0
    while True:
        time.sleep(30); k += 1
        try:
            stuck, desc = ts_stuck_check()
            if stuck:
                stack = ts_main_stack()
                if stack: print("🩺 phần nhận đơn đang đứng ở:\n" + stack, flush=True)
                again = any(str(e.get("what", "")).startswith("phần nhận đơn ĐỨNG") and time.time() - float(e.get("t", 0)) < 3600
                            for e in _ts["ev"])           # 14/11: chỉ nhắn Telegram khi đứng LẶP LẠI trong 1 giờ
                ts_note(f"phần nhận đơn ĐỨNG ({desc}) → tự khởi động lại cloudphoned", tg=again, key="stuck" if again else "stuck1", every=1800)
            if stuck or ts_loop_err():
                time.sleep(3); _ts_exit(3); return
            if WIN and k % 2 == 0: ts_bluestream()
            if WIN and k % 4 == 1: ts_wake_screens()
        except Exception as e:
            print("lỗi tự kiểm:", e, flush=True)

# Việc bảo trì chạy ở LUỒNG RIÊNG (mỗi loại 1 luồng, lượt trước chưa xong thì bỏ lượt này) → không bao giờ chặn việc nhận đơn
_bg = {}
def bg_job(key, fn):
    th = _bg.get(key)
    if th is not None and th.is_alive(): return False
    th = threading.Thread(target=fn, name="bg-" + key, daemon=True); _bg[key] = th; th.start(); return True

def _bg_connect():
    try: phonectl(["connect-all"])
    except Exception as e: print("lỗi connect-all:", e)

def _bg_dondep():
    """14/11: máy khách web đã HUỶ (đổi Android, hết hạn, khách / admin huỷ) mà vẫn còn trên máy chủ (lần xoá trước lỗi, máy chủ bận
       quá 10 phút lúc đổi Android…) → xoá hẳn máy ảo + dữ liệu, như admin bấm 🧹 Xoá sạch. Máy web ghi còn dùng / không có trên web:
       KHÔNG bao giờ đụng."""
    try:
        r = phonectl(["dondep", "--xoa"])
        m = re.search(r"DONDEP (\{.*\})", r.stdout or "")
        j = json.loads(m.group(1)) if m else {}
        if j.get("deleted"):
            ts_note(f"tự dọn {j['deleted']} máy khách web đã huỷ mà còn sót trên máy chủ (đã xoá hẳn máy + dữ liệu)", key="dondep", every=1800)
    except Exception as e: print("lỗi tự dọn máy sót:", e)

def _bg_apps():
    try:
        r = phonectl(["preinstall", "--all"])
        for ln in (r.stdout or "").splitlines():
            if ln.strip(): print("  ", ln.strip())
        phonectl(["perms"])
    except Exception as e: print("lỗi cài app sẵn / mở quyền APK:", e)

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

_alert = {"full": None, "none": None}
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
    rn = None                                           # tên các máy đang chạy (Windows: đo RAM thật 1 máy chạy dùng)
    try:
        rn = {l for l in subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15).stdout.split() if l.startswith("cp_")}
        running = len(rn)
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
    g_list = gpus(); g_avg, v_avg = gpu_avg5(g_list); g_why = gpu_busy()
    if g_why: c_ram, c_cpu = a_ram, a_cpu               # card đồ hoạ / VRAM quá tải → báo hết chỗ, đơn mới sang máy chủ khác
    zz, zz_full, nz = 0.0, 0.0, 0
    if WIN:
        try: ram_sample(st, rn, ram_t, ram_avail)       # đo RAM thật máy đang chạy → phần giữ cho máy ngủ
        except Exception as e: print("lỗi đo RAM máy ngủ:", e)
        a_ram, a_cpu, c_ram, c_cpu = win_caps(st)       # Windows: sức chứa theo RAM trống thật, CPU dùng chung (đã tính card đồ hoạ)
        try: zz, zz_full, nz = rr_write(st, a_ram, c_ram)
        except Exception as e: print("lỗi ghi phần giữ RAM máy ngủ:", e)
    if WIN:                                             # 13/11: sức chứa THẬT → % đầy cho web; sức chứa BÁN (95%) → cap_ram / cap_cpu
        f_ram, f_cpu, stop = c_ram, c_cpu, FULL_PCT
        c_ram, c_cpu = sell_cap(a_ram, f_ram), sell_cap(a_cpu, f_cpu)
    else:                                               # Linux: c_ram đã là LIMIT_PCT % RAM (như cũ) → sức chứa thật = 100%
        f_ram, f_cpu, stop = (ram_t * RAM_OVER if c_ram > a_ram else c_ram), c_cpu, float(LIMIT_PCT)
    fill = 100 * max(a_ram / f_ram if f_ram > 0 else 1.0, a_cpu / f_cpu if f_cpu > 0 else 1.0)
    metrics = {"cpu_pct": cp_now, "cpu_avg5": avg5, "cpu_over": CPU_OVER, "cpu_busy_pct": CPU_BUSY, "cpu_busy": busy, "ram_over": RAM_OVER, "ram_pct": ram_pct, "ram_busy_pct": RAM_BUSY, "ram_busy": ram_busy, "disk_busy": disk_busy, "disk_busy_pct": DISK_BUSY, "load": [round(x, 2) for x in os.getloadavg()], "cpu_temp": cpu_temp(),
               "ram_used": round(ram_t - ram_avail, 1), "gpus": g_list, "gpu_avg5": g_avg, "vram_avg5": v_avg, "gpu_busy_pct": GPU_BUSY, "vram_busy_pct": VRAM_BUSY, "gpu_busy": g_why == "gpu", "vram_busy": g_why == "vram", "disk_data": disk(DATA_ROOT), "disk_root": disk("/"),
               "running": running, "sleeping": sum(1 for p in st if p.get("sleep") and p.get("hold")), "uptime_h": up_h, "base": BASE, "primary": PRIMARY, "renew_v": 2}     # renew_v 2: gia hạn chỉ xoá ngày chờ khi đã ghi được
    if WIN: metrics.update(ram_over=WIN_RAM_OVER, sleep_gb=round(zz, 1), sleep_full_gb=round(zz_full, 1), sleep_pct=round(100 * ram_ratio() / WIN_RAM_OVER))   # web: máy ngủ giữ bao nhiêu RAM
    metrics.update(cap_ram_full=round(f_ram, 1), cap_cpu_full=round(f_cpu, 1), full_pct=stop, fill_pct=round(min(100.0, fill), 1))   # web: % đầy cho khách (SQL v33)
    body = {"id": NODE_ID, "cpu_total": cpu_t, "ram_total": round(ram_t, 1), "cap_cpu": round(c_cpu, 1), "cap_ram": round(c_ram, 1),
            "alloc_cpu": a_cpu, "alloc_ram": a_ram, "phones": len(st), "limit_pct": LIMIT_PCT, "metrics": metrics,
            "updated_at": now().isoformat()}
    if time.time() - _eng.get("t", 0) > (120 if _eng.get("none") else 600): _engine_read()   # thiếu máy mẫu: 2 phút đọc lại 1 lần
    eng = engine()
    metrics["missing_tpl"] = list(eng.get("missing") or [])                      # web: thẻ máy chủ báo thiếu máy mẫu
    if eng["emu"] and not _hb_old["v"]:
        body.update(engine=eng["emu"], androids=",".join(eng["androids"]) or ("-" if eng.get("none") else ""))   # "-" = không bán bản nào (KHÔNG phải Android 9)
    if bool(eng.get("none")) != bool(_alert["none"]) and (_alert["none"] is not None or eng.get("none")):
        notify(f"⚠️ <b>{NODE_ID}</b>: giả lập {eng['emu']} thiếu máy mẫu {', '.join(eng.get('missing') or []) or '?'} → máy chủ này KHÔNG bán được bản Android nào, "
               f"web không chia đơn vào đây. Tạo máy mẫu (đúng tên, để tắt) là tự bán lại sau ~2 phút." if eng.get("none") else
               f"✅ <b>{NODE_ID}</b>: đã có máy mẫu — bán lại Android {', '.join(eng['androids'])}.")
    _alert["none"] = bool(eng.get("none"))
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
                f"🚨 <b>{NODE_ID}: card đồ hoạ đang chạy {g_avg or 0:.0f}%</b> (TB 5 phút, ngưỡng {GPU_BUSY}%) — tạm ngừng nhận máy mới." if g_why == "gpu" else
                f"🚨 <b>{NODE_ID}: VRAM card đồ hoạ đầy {v_avg or 0:.0f}%</b> (TB 5 phút, ngưỡng {VRAM_BUSY}%) — tạm ngừng nhận máy mới." if g_why == "vram" else
                f"🚨 <b>{NODE_ID} đã đầy {min(100.0, fill):.0f}%</b> (ngưng nhận ở {stop:g}%) — RAM cấp {a_ram:.0f}/{f_ram:.0f}GB, CPU cấp {a_cpu:.0f}/{f_cpu:.0f}."
                + (f" Đang giữ {zz:.0f}GB RAM cho {nz} máy ngủ (khách mở là bật lại)." if nz else "")) + " Đơn mới sang máy chủ khác (mọi máy chủ đều đầy thì khách thấy HẾT HÀNG)."
               if full else f"✅ <b>{NODE_ID}</b> đã có chỗ trống trở lại (RAM cấp {a_ram:.0f}/{ram_t:.0f}GB).")
    _alert["full"] = full

def running(name):
    ps = phone_state(name)
    if ps and ps.get("kind") == "gpu":          # máy GPU chạy bằng dịch vụ cloudgpu@TÊN
        return subprocess.run(["systemctl", "is-active", "-q", f"cloudgpu@{name}"]).returncode == 0
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name], capture_output=True, text=True)
    if threading.current_thread() is threading.main_thread(): _loop_t[0] = max(_loop_t[0], time.time())
    return r.stdout.strip() == "true"

_sec_t = {"pull": 0.0, "watch": 0.0, "miss": 0}
def sec_tick():
    """🛡️ Bot gác bảo mật (SQL v29): máy chủ chính nhắn Telegram cảnh báo ĐỎ / VÀNG (mỗi cảnh báo chỉ 1 máy chủ gửi);
       Supabase chưa bật pg_cron thì máy chủ chạy luôn lượt quét 5 phút / lần. Chưa chạy v29 → im lặng, thử lại sau 30 phút."""
    if not PRIMARY: return
    t = time.time()
    if _sec_t["miss"] and t - _sec_t["miss"] < 1800: return
    if t - _sec_t["watch"] >= 300:
        _sec_t["watch"] = t
        try: sb("POST", "rpc/sec_watch", {})
        except Exception as e:
            if "sec_watch" in str(e) or "404" in str(e): _sec_t["miss"] = t; return
    if t - _sec_t["pull"] >= 60:
        _sec_t["pull"] = t
        try: rows = sb("POST", "rpc/sec_alerts_pull", {"p_limit": 20}) or []
        except Exception: rows = []
        for r in (rows if isinstance(rows, list) else [])[:20]:
            msg = str(r.get("msg") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            try: notify(("🚨" if r.get("level") == "crit" else "⚠️") + " <b>BẢO MẬT CLOUDBLUE</b>\n" + msg + "\n👉 Admin › 🛡️ Bảo mật")
            except Exception: pass

def asleep(name):
    """Máy đang NGỦ (phonectl idle tắt vì lâu không dùng; khách mở máy → phát hình bật lại): dấu ngủ + hold."""
    q = phone_state(name) or {}
    return bool(q.get("sleep") and q.get("hold"))

def do_locks():
    """Máy admin khoá → tắt; hết hạn khoá → tự mở khoá; máy đang chạy mà bị tắt ngoài ý muốn → bật lại."""
    rows = sb("GET", "cloud_phones?status=eq.active&select=id,container,locked,locked_until") or []
    t = now(); relaunch = []
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
        elif not lk and not on and asleep(name):
            continue                        # máy NGỦ (tự tắt vì lâu không dùng) → khách mở máy thì phát hình bật lại
        elif not lk and not on:
            relaunch.append(name)
    if relaunch:                                            # 14/11: bật lần lượt (phonectl giãn cách) ở luồng riêng — không chặn nhận đơn
        def go(names=tuple(relaunch)):
            for nm in names:
                print(f"[bật lại] {nm}")
                try: phonectl(["start", nm])
                except Exception as e: print("lỗi bật lại:", e)
        bg_job("relaunch", go)

IDLE_ON = WIN and _f("IDLE_STOP_MIN", 30) > 0          # Windows: máy rảnh lâu tự NGỦ (phonectl idle) · IDLE_STOP_MIN=0 → tắt
_idle = {"th": None, "old": 0.0, "skip": 0.0}
def idle_job():
    """~2 phút/lần: máy khách đứng ở MÀN HÌNH CHÍNH, không ai xem, CPU thấp liền IDLE_STOP_MIN phút → phonectl cho NGỦ (tắt êm,
       giữ dữ liệu). Máy treo game không bao giờ bị tắt. Khách mở máy → bluestream gọi phonectl wake bật lại."""
    try: r = subprocess.run(["python3", PHONECTL, "idle"], capture_output=True, text=True, timeout=900)
    except Exception as e: print("lỗi cho máy ngủ:", e); return
    o = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 2 and "invalid choice" in o:                  # phonectl.py cũ chưa có lệnh idle
        if time.time() - _idle["old"] > 6 * 3600: _idle["old"] = time.time(); print("[ngủ] phonectl.py bản cũ chưa có lệnh idle — tải phonectl.py mới")
        return
    for ln in o.splitlines():
        if ln.startswith("NGU"): print("[ngủ]", ln.strip())
        elif ln.startswith("IDLE_SKIP") and time.time() - _idle["skip"] > 3600: _idle["skip"] = time.time(); print("[ngủ]", ln.strip())

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
        pid = row["id"]; n, nxt = _cancel_try.get(pid, (0, 0))
        if time.time() < nxt: return
        print(f"[xoá hết hạn] {name}")
        if ps or str(name).startswith("cp_"):               # 14/11: xoá hẳn (cả máy sót trong giả lập) — chưa xoá được thì CHƯA ghi huỷ, thử lại sau
            r = phonectl(["delete", name]); o = (r.stdout or "") + (r.stderr or "")
            gone = (r.returncode == 0 and "Chưa xoá được" not in o) or (r.returncode == 1 and "Không có máy tên này" in o)
            if not gone:
                n += 1; wait = min(60 * n, 900); _cancel_try[pid] = (n, time.time() + wait)
                why = (o.strip().splitlines() or ["?"])[-1]
                print(f"   ⚠ chưa xoá được {name} (lần {n}, {wait}s sau thử lại): {why[:200]}")
                if n in (1, 5) or n % 20 == 0:
                    notify(f"⚠️ <b>{NODE_ID}</b>: máy hết hạn <b>{name}</b> chưa xoá được — máy chủ tự thử lại. Lý do: {why[:160]}")
                return
        _cancel_try.pop(pid, None)
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
    print(f"cloudphoned bản 14/11 chạy — đọc {SB} mỗi {POLL}s. Ctrl+C để dừng.")
    try:                                    # nới RAM cho máy đang chạy (chống văng app khi hết RAM)
        r = phonectl(["memfix"]); print(r.stdout.strip())
    except Exception as e: print("lỗi memfix:", e)
    print(f"Server: {NODE_ID} ({'CHÍNH' if PRIMARY else 'phụ'}) · {BASE}")
    print("Ngừng nhận máy mới khi: đã cấp ≥ %g%% sức chứa (%s) · CPU TB 5 phút ≥ %d%% · RAM ≥ %d%% · ổ cứng ≥ %d%% · card đồ hoạ TB 5 phút %s · VRAM %s (GPU_BUSY_PCT / VRAM_BUSY_PCT, 0 = tắt)"
          % (FULL_PCT if WIN else LIMIT_PCT, "FULL_PCT" if WIN else "LIMIT_PCT", CPU_BUSY, RAM_BUSY, DISK_BUSY, "≥ %d%%" % GPU_BUSY if GPU_BUSY else "TẮT", "≥ %d%%" % VRAM_BUSY if VRAM_BUSY else "TẮT"))
    e = engine(); print(f"Giả lập: {e['emu'] or '?'} · nhận đơn Android: "
                        + (f"KHÔNG bản nào — thiếu máy mẫu {', '.join(e.get('missing') or []) or '?'} (tạo trong giả lập, đúng tên, để tắt)"
                           if e.get("none") else (', '.join(e['androids']) or 'mọi bản')))
    if WIN: print(f"Máy rảnh tự ngủ (IDLE_STOP_MIN={_f('IDLE_STOP_MIN', 30):g}): " + ("máy ở màn hình chính, không ai xem, CPU thấp liền ngần ấy phút → tắt; khách mở máy tự bật lại" if IDLE_ON else "TẮT"))
    if WIN:
        _rr_load()
        print(f"Máy ngủ giữ RAM (SLEEP_RAM): bằng RAM thật 1 máy đang chạy dùng (mức cao nhất {RATIO_HOURS} giờ, tối thiểu "
              f"{RATIO_FLOOR:.0%} RAM cấp) ÷ RAM_OVER {WIN_RAM_OVER:g} → hiện giữ {ram_ratio() / WIN_RAM_OVER:.0%} RAM cấp của máy ngủ")
    adopt_old()
    n = 0; last = 0.0; _rootjob = [None]
    threading.Thread(target=_hb_loop, daemon=True).start()     # báo "còn sống" lên web ở luồng riêng
    if TS_ON:
        _ts_load(); _loop_t[0] = time.time()
        threading.Thread(target=_ts_loop, daemon=True).start()
        print(f"Tự kiểm · tự sửa (TUSUA): lệnh phonectl có hạn chờ · phần nhận đơn đứng quá {TS_STUCK_MIN:g} phút → tự khởi động lại"
              + (" · phát hình đóng cổng ~3 phút → bật lại · màn hình máy khách tắt → bật sáng" if WIN else "") + " · nhật ký: 🩺 tự sửa (14/11)")
    else:
        print("Tự kiểm · tự sửa: TẮT (TUSUA=0)")
    while True:
        _loop_t[0] = time.time()
        try: tick_orders(); _ts["err_t"] = 0.0      # đơn mới: kiểm tra mỗi 3 giây → nhận đơn gần như tức thì
        except Exception as e:
            print("lỗi vòng lặp:", e)
            _ts["err_t"] = _ts["err_t"] or time.time(); _ts["err_msg"] = str(e)[:160]
        if time.time() - last < 15:
            time.sleep(3); continue
        last = time.time()
        try: tick()
        except Exception as e: print("lỗi vòng lặp:", e)
        bg_job("connect", _bg_connect)      # mỗi 15 giây: máy nào rớt kết nối thì nối lại (tránh màn xám) — luồng riêng (13/11)
        if n % 2 == 0:                      # ~30 giây: khoá / mở khoá / bật lại máy (báo cáo tài nguyên chạy ở luồng riêng _hb_loop)
            try: do_locks()
            except Exception as e: print("lỗi khoá máy:", e)
        if IDLE_ON and n % 8 == 3:          # ~2 phút: máy rảnh lâu → cho NGỦ (luồng riêng, không chặn việc nhận đơn)
            if _idle["th"] is None or not _idle["th"].is_alive():
                _idle["th"] = threading.Thread(target=idle_job, daemon=True); _idle["th"].start()
        if n % 4 == 1:                      # ~1 phút: 🛡️ bot gác bảo mật — nhắn Telegram cảnh báo, quét 5 phút / lần
            try: sec_tick()
            except Exception as e: print("lỗi bot gác:", e)
        if n % 20 == 5:                     # ~5 phút: cài app còn thiếu (máy nào lỡ) + mở quyền cài APK cho app khách mới cài
            bg_job("apps", _bg_apps)        # luồng riêng (13/11): trước chạy ở vòng chính → 1 máy cài APK treo (chờ tới 15 phút / file)
                                            # là cả máy chủ không nhận đơn
        if WIN and n % 120 == 60:           # ~30 phút: xoá hẳn máy web đã huỷ mà còn sót trên máy chủ (14/11)
            bg_job("dondep", _bg_dondep)
        if n % 20 == 12:                    # ~5 phút: máy nào chưa root → tự root (chạy nền, không chặn việc nhận đơn)
            try:
                if _rootjob[0] is None or _rootjob[0].poll() is not None:
                    _rootjob[0] = subprocess.Popen(["python3", PHONECTL, "rootfix", "--all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e: print("lỗi tự root:", e)
        n += 1
        time.sleep(3)
