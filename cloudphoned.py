#!/usr/bin/env python3
# cloudphoned.py — Chương trình nền: đọc đơn từ Supabase (cloud_phones) → gọi phonectl tạo/xoá/gia hạn máy.
# Cấu hình đọc từ ~/cloudphone.conf (KEY=VALUE), KHÔNG đưa khoá bí mật lên GitHub.
#   SUPABASE_URL=https://xxxx.supabase.co
#   SUPABASE_SERVICE_KEY=eyJ...            (service_role key — bí mật)
#   PUBLIC_BASE=https://xxxx.trycloudflare.com   (link ws-scrcpy ra internet)
# Chạy:  python3 ~/cloudphoned.py           (vòng lặp mỗi 15s)
import json, os, re, sys, time, subprocess, tempfile, urllib.request, urllib.parse, urllib.error, datetime, socket, shutil, threading, random
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
# 16/11 — admin NÂNG TRẦN NHÂN: cấp tới 100 nhân mới ngừng (68 làm máy chủ còn nhiều RAM mà đã báo đầy, đơn bị hoàn tiền). Nhân bán
#   không vượt số luồng thật × CPU_SELL_X − CPU_KEEP (×2: máy 72 luồng → 140, trần 100 chặn trước; máy nhỏ vẫn giữ an toàn).
#   CPU thật nóng (TB 5 phút ≥ CPU_BUSY_PCT, 85%) vẫn ngừng nhận như cũ — chỗ chặn quá tải thật.
# Đổi trong cloudphone.conf: CAP_CPU=100 · CAP_RAM=112 (0 = bỏ trần, tính như trước 14/11) · CPU_SELL_X=2 · CPU_KEEP=4
CAP_CPU, CAP_RAM, CPU_KEEP = _f("CAP_CPU", 100), _f("CAP_RAM", 112), _f("CPU_KEEP", 4)
CPU_SELL_X = max(0.5, min(3.0, _f("CPU_SELL_X", 2.0)))
# 16/11 — tạo máy mà phonectl báo HẾT CHỖ (RAM thật lúc tạo ít hơn số ước) → không hoàn tiền ngay: còn máy chủ khác đủ chỗ thì TRẢ ĐƠN
#   cho nó nhận; máy chủ này nghỉ nhận đơn mới + báo web hết chỗ FULL_COOL_S giây (đơn không quay lại đúng máy vừa hết chỗ).
FULL_COOL_S = max(60, int(_f("FULL_COOL_S", 300)))
# 16/11e: đơn ADMIN chọn đúng máy chủ này (web: "Máy chủ (admin chọn)") mà máy chủ này đã GẦN ĐẦY (% đầy như web hiện ≥ NEAR_PCT)
# → tự chuyển đơn sang máy chủ còn trống nhất (đúng bản Android, đang chạy, đủ chỗ, trống hơn ≥ NEAR_GAP điểm %). NEAR_PCT=0 = tắt.
NEAR_PCT = max(0.0, min(100.0, _f("NEAR_PCT", 80)))
NEAR_GAP = max(0.0, min(50.0, _f("NEAR_GAP", 5)))
_HANDED = {}                       # id đơn → lúc máy chủ này đã chuyển đi (đơn quay lại thì nhận, không chuyển vòng)
_FULL = {"until": 0.0}
# 16/11f: đơn tạo máy quá STUCK_MIN phút chưa lên → tự HUỶ + HOÀN TIỀN, báo khách tạo máy mới (hàm SQL cloudphone_timeout_stuck — v36;
#   có pg_cron thì Supabase tự quét mỗi phút, mọi máy chủ cũng gọi mỗi phút cho chắc). Đơn đổi Android (giữ hạn máy cũ) KHÔNG đụng.
#   Máy đang tạo dở của đơn đã huỷ: máy chủ tự xoá (máy CHƯA giao cho khách, chưa có dữ liệu khách). STUCK_MIN=0 = tắt.
STUCK_MIN = max(0.0, _f("STUCK_MIN", 30))
# 16/11f: máy chủ đang có ≥ BOOT_MAX máy MỚI chưa lên, hoặc 1 máy mới chờ Android quá BOOT_SLOW_MIN phút → máy chủ đang quá tải tạo
#   máy: tạm KHÔNG nhận đơn mới + báo web hết chỗ (đơn sang máy chủ khác, khách không phải chờ 20–30 phút). Đơn admin chọn đúng máy
#   chủ này vẫn làm. BOOT_MAX=0 = tắt.
BOOT_MAX = max(0, int(_f("BOOT_MAX", 3)))
BOOT_SLOW_S = max(60.0, _f("BOOT_SLOW_MIN", 10) * 60)
BOOT_T = {}                        # tên máy MỚI → lúc bắt đầu chờ Android lên (chưa giao cho khách)
_busy_said = {"t": 0.0}
# 16/11g: máy chủ "ốm" — máy MỚI tạo ra mà không lên (tạo lỗi / chờ ~10 phút chưa lên / đơn tự huỷ ⏱) → tự NGỪNG nhận đơn mới
#   SICK_MIN phút (mỗi lần hỏng tính lại từ đầu) + báo web hết chỗ + nhắn admin. Trước: máy chủ hỏng mà đang trống thì giành đơn
#   TRƯỚC mọi máy chủ khác (ưu tiên máy chủ trống) → khách nào cũng chờ 30 phút rồi bị hoàn tiền. SICK_MIN=0 = tắt.
SICK_MIN = max(0.0, _f("SICK_MIN", 20))
_SICK = {"until": 0.0, "why": "", "said": 0.0, "rows": set()}
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
    if CAP_CPU > 0:                                          # 16/11: trần cứng 100 nhân (không vượt luồng thật × 2 − 4)
        lim = min(CAP_CPU, max(1.0, cpu_t * CPU_SELL_X - CPU_KEEP))
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
        # 16/11: độ bận tính cả NHÂN đã cấp → máy chủ còn trống nhiều (RAM lẫn nhân) nhận đơn trước, máy sắp đầy chờ thêm vài giây
        return max(a_r / max(c_r, 1), a_c / max(c_c, 1), (cpu_avg5() or 0) / 100, gl), sell_cap(a_r, c_r) - a_r, sell_cap(a_c, c_c) - a_c
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
ENG_POKE_F = os.path.join(HOME, "logs", "doc-lai-may-mau.txt")   # 24/11b: phonectl mktpl / lệnh A vừa tạo máy mẫu → ghi file này → đọc lại NGAY
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
def eng_due(t_now=None):
    """24/11b · đến lúc đọc lại máy mẫu chưa (báo cáo 30 giây / lần gọi). Vừa tạo máy mẫu (doc-lai-may-mau.txt mới hơn lần đọc trước) → đọc
       NGAY (web bán thêm bản đó sau ≤ 30 giây — trước đây chờ tới 10 phút) · còn thiếu máy mẫu → 2 phút / lần (tạo tay trong giả lập cũng
       bán sau ≤ 2 phút) · đủ máy mẫu → 10 phút / lần."""
    t_now = time.time() if t_now is None else t_now
    last = float(_eng.get("t") or 0)
    try:
        if os.path.getmtime(ENG_POKE_F) > last: return True
    except OSError: pass
    return t_now - last > (120 if (_eng.get("none") or _eng.get("missing")) else 600)
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

def node_pct(r):
    """% đầy của 1 máy chủ khác (dòng cloud_nodes) — cùng cách web tính: max(RAM đã cấp ÷ sức chứa, nhân đã cấp ÷ sức chứa)."""
    try:
        cr, ar = float(r.get("cap_ram") or 0), float(r.get("alloc_ram") or 0)
        cc, ac = float(r.get("cap_cpu") or 0), float(r.get("alloc_cpu") or 0)
    except (TypeError, ValueError):
        return 100.0
    return 100 * max(ar / cr if cr > 0 else 1.0, ac / cc if cc > 0 else 1.0)

def my_pct():
    """% đầy của CHÍNH máy chủ này (như web hiện): đã cấp ÷ sức chứa thật. Vừa hết chỗ lúc tạo máy → 100."""
    if time.time() < _FULL["until"]: return 100.0
    try: st = json.load(open(PHONES_JSON)).get("phones", [])
    except Exception: st = []
    if WIN:
        a_r, a_c, c_r, c_c = win_caps(st)
        return 100 * max(a_r / c_r if c_r > 0 else 1.0, a_c / c_c if c_c > 0 else 1.0)
    return 100 * local_load()[0]

def handover(row):
    """16/11e: đơn ADMIN chọn máy chủ này (node = máy này, chưa tạo máy) mà máy chủ này GẦN ĐẦY → chuyển sang máy chủ còn trống nhất.
       True = đã chuyển (máy này không làm đơn đó). Không có máy chủ nào trống hơn → giữ, làm như admin chọn."""
    if NEAR_PCT <= 0 or row.get("status") != "pending" or row.get("container") or row.get("replaces"): return False
    rid = str(row.get("id") or "")
    if not rid or rid in _HANDED: return False      # đơn máy này đã chuyển đi rồi quay lại → nhận luôn (không chuyển vòng)
    if phone_state(cname(row)): return False        # máy của đơn đã có trên máy chủ này (lần tạo trước dở dang) → làm tiếp ở đây
    if not node_enabled(): return False             # 16/11h: máy chủ đang "Ngừng nhận máy" → admin cố ý tạo máy THỬ ở đây (SQL v37) → giữ
    me = my_pct()
    if me < NEAR_PCT: return False
    v = str(row.get("android") or "").strip() or "9"; wr, wc = want(row); best = None
    for r in live_nodes():
        if r.get("id") == NODE_ID or not node_sells(r, v): continue
        try:
            room = float(r.get("cap_ram") or 0) - float(r.get("alloc_ram") or 0) + 0.01 >= wr and \
                   float(r.get("cap_cpu") or 0) - float(r.get("alloc_cpu") or 0) + 0.01 >= wc
        except (TypeError, ValueError):
            room = False
        if not room: continue
        p = node_pct(r)
        if p <= me - NEAR_GAP and (best is None or p < best[0]): best = (p, str(r.get("id")))
    if not best: return False
    _HANDED[rid] = time.time()
    try:
        got = sb("PATCH", f"cloud_phones?id=eq.{rid}&node=eq.{urllib.parse.quote(NODE_ID, safe='')}&status=eq.pending&container=is.null",
                 {"node": best[1]}, {"Prefer": "return=representation"})
    except Exception as e:
        print("lỗi chuyển đơn sang máy chủ trống hơn:", e); return False
    if not got: return True                         # đơn vừa đổi (máy chủ khác nhận / bị huỷ) → lượt sau đọc lại rồi mới quyết
    print(f"[chuyển] đơn {rid[:8]}: {NODE_ID} gần đầy ({me:.0f}%) → {best[1]} ({best[0]:.0f}%) còn trống nhất")
    return True

def busy_boot():
    """16/11f: máy chủ này đang quá tải TẠO MÁY? → lý do (chuỗi); không → ''. (Xem BOOT_MAX / BOOT_SLOW_MIN ở trên.)"""
    if BOOT_MAX <= 0: return ""
    t_now = time.time(); ts = list(BOOT_T.values())
    slow = [t for t in ts if t_now - t > BOOT_SLOW_S]
    if slow: return f"1 máy mới chờ Android lên đã {(t_now - min(slow)) / 60:.0f} phút"
    if len(ts) >= BOOT_MAX: return f"{len(ts)} máy mới đang khởi động"
    return ""

def mark_sick(why):
    """16/11g: máy mới không lên → ngừng nhận đơn mới SICK_MIN phút (xem trên). Nhắn admin tối đa 10 phút / lần."""
    if SICK_MIN <= 0: return
    _SICK["until"] = max(_SICK["until"], time.time() + SICK_MIN * 60); _SICK["why"] = why
    print(f"[ốm] {why} → tạm ngừng nhận đơn mới {SICK_MIN:g} phút (đơn sang máy chủ khác)")
    if time.time() - _SICK["said"] > 600:
        _SICK["said"] = time.time()
        notify(f"⚠️ <b>{NODE_ID}</b>: {why} → tự ngừng nhận đơn mới {SICK_MIN:g} phút (đơn sang máy chủ khác). "
               f"Lặp lại nhiều lần thì kiểm máy chủ này (lệnh A) hoặc bấm \"Ngừng nhận máy\" trên web.")

def sick_why():
    """16/11g: đang trong thời gian ngừng nhận đơn vì máy mới không lên → lý do; không → ''."""
    return _SICK["why"] if time.time() < _SICK["until"] else ""

def still_pending(pid):
    """16/11f: đơn còn đang chờ tạo (chưa bị huỷ / hoàn tiền / tự huỷ vì quá STUCK_MIN phút)? Lỗi mạng → coi như còn (không xoá nhầm)."""
    try:
        rows = sb("GET", f"cloud_phones?id=eq.{pid}&select=status")
        return not rows or rows[0].get("status") == "pending"
    except Exception:
        return True

def drop_vm(name, why):
    """16/11f: xoá máy ảo VỪA TẠO của đơn đã bị huỷ / hoàn tiền trong lúc tạo (máy chưa giao cho khách — chưa có dữ liệu khách)."""
    BOOT_T.pop(name, None)
    if not phone_state(name): return
    print(f"   ✗ {name}: {why} → xoá máy vừa tạo (chưa giao cho khách)")
    try:
        r = phonectl(["delete", name])
        if r.returncode != 0: print("   lỗi xoá máy:", ((r.stdout or "") + (r.stderr or "")).strip()[-200:])
    except Exception as e: print("   lỗi xoá máy:", e)

_stuck = {"next": 0.0, "del": {}}
def stuck_sweep():
    """16/11f: gọi hàm SQL v36 — đơn tạo máy quá STUCK_MIN phút chưa lên → huỷ + hoàn tiền + báo khách tạo máy mới."""
    if STUCK_MIN <= 0 or time.time() < _stuck["next"]: return
    try:
        n = sb("POST", "rpc/cloudphone_timeout_stuck", {"p_min": int(round(STUCK_MIN))})
    except urllib.error.HTTPError as e:
        if e.code == 404:                      # web chưa chạy SQL v36 → 30 phút sau hỏi lại (chạy SQL xong là tự dùng, khỏi khởi động lại)
            _stuck["next"] = time.time() + 1800
            print("   (chưa có hàm SQL cloudphone_timeout_stuck — chạy SQL v36 trên Supabase để tự huỷ + hoàn tiền đơn treo)")
            return
        raise
    if isinstance(n, int) and n > 0:
        print(f"[⏱ quá {STUCK_MIN:g} phút] {n} đơn tạo máy chưa lên → đã tự huỷ + hoàn tiền, báo khách tạo máy mới")
        notify(f"⏱ <b>{n} đơn ĐT đám mây</b> tạo quá {STUCK_MIN:g} phút chưa lên → đã tự huỷ + hoàn tiền, khách được báo tạo máy mới "
               f"(máy chủ gọi: {NODE_ID}).")

def stuck_cleanup():
    """16/11f: đơn của máy chủ này đã tự huỷ (⏱) mà máy ảo tạo dở vẫn còn → xoá (máy chưa giao cho khách)."""
    if STUCK_MIN <= 0: return
    rows = sb("GET", f"cloud_phones?node=eq.{urllib.parse.quote(NODE_ID, safe='')}&status=eq.error"
                     f"&error=like.{urllib.parse.quote('⏱*', safe='*')}&select=id,container,updated_at&order=updated_at.desc&limit=50") or []
    for row in rows:
        try: fresh = (now() - parse_dt(row.get("updated_at"))).total_seconds() < SICK_MIN * 60 + 120
        except Exception: fresh = False
        if fresh and row.get("id") not in _SICK["rows"]:              # 16/11g: đơn ở máy chủ này vừa tự huỷ vì máy không lên → ốm
            _SICK["rows"].add(row.get("id")); mark_sick(f"đơn {str(row.get('id'))[:8]} tạo quá {STUCK_MIN:g} phút không lên (đã tự huỷ + hoàn tiền)")
        name = row.get("container") or cname(row)
        if name in BOOTING or not phone_state(name): continue          # đang chờ lên → luồng chờ tự xoá
        k = _stuck["del"].get(name, 0)
        if time.time() < k: continue
        _stuck["del"][name] = time.time() + 600                          # xoá lỗi → 10 phút sau thử lại
        drop_vm(name, "đơn đã tự huỷ vì tạo quá lâu")

def _stuck_loop():
    time.sleep(20)
    while True:
        try: stuck_sweep()
        except Exception as e: print("lỗi quét đơn tạo máy treo:", e)
        try: stuck_cleanup()
        except Exception as e: print("lỗi dọn máy của đơn đã tự huỷ:", e)
        time.sleep(60)

def claim(row):
    """Giành đơn mới cho server này. Server còn trống nhiều nhận trước; không đủ chỗ thì nhường server khác.
    Trả về True nếu server này được làm đơn đó."""
    n = row.get("node")
    if n:                                           # đã có server nhận rồi (admin chọn / máy chủ khác)
        if n != NODE_ID: return False
        return not handover(row)                    # 16/11e: admin chọn máy chủ này mà nó gần đầy → chuyển sang máy chủ trống nhất
    if not node_enabled(): return False
    if time.time() < _FULL["until"]:                 # 16/11: vừa tạo máy báo HẾT CHỖ → nghỉ nhận đơn ít phút, nhường máy chủ khác
        if PRIMARY: refund_unserved(row)
        return False
    if not android_ok(row):                          # đơn Android 12/7 → máy chủ MuMu/MEmu; Android 9 → máy chủ LDPlayer
        if PRIMARY: refund_unserved(row)
        return False
    why = busy_boot() or sick_why()                  # 16/11f: đang quá tải tạo máy / 16/11g: máy mới không lên → nhường máy chủ khác (khách khỏi chờ 20–30 phút)
    if why:
        if time.time() - _busy_said["t"] > 60:
            print(f"[bận] {why} → tạm không nhận đơn mới, nhường máy chủ khác"); _busy_said["t"] = time.time()
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
          "resize": 1800, "create": 2400, "disk": 600}
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

# ---------- 19/11: BỘ NHỚ máy khách theo cấu hình + khách MUA THÊM bộ nhớ (SQL v40 · phonectl 19/11a) ----------
# Web tính cỡ (bậc miễn phí theo RAM + phần khách mua) → cloud_phones.disk_gb. Máy MỚI: create --disk N, phonectl nới lúc lên lần đầu.
# Khách mua thêm / nâng RAM lên bậc cao hơn → web ghi pending_disk = cỡ mới → máy chủ giữ máy đó gọi `phonectl disk TÊN --gb N`:
#   xong → disk_gb = N, bỏ pending · máy đang tắt / ngủ → phonectl hẹn lần bật, ở đây hỏi lại 5 phút / lần tới khi xong ·
#   lỗi không tự hết (máy chủ không hỗ trợ, phân vùng nhỏ…) hoặc lỗi 6 lần liền → hoàn tiền phần mua (cloudphone_disk_refund).
# Máy CŨ không bao giờ bị đụng nếu khách không mua. Web chưa chạy SQL v40 → không có cột → 10 phút hỏi lại 1 lần, không làm gì.
def _int(x):
    try: return int(float(x or 0))
    except (TypeError, ValueError): return 0
_pdisk = {"v": None}
def phonectl_disk():
    """phonectl.py trên máy này có lệnh disk + create --disk chưa (19/11a)?"""
    if _pdisk["v"] is None:
        try: _pdisk["v"] = 'add_parser("disk")' in open(PHONECTL, encoding="utf-8").read()
        except Exception: _pdisk["v"] = False
    return _pdisk["v"]
def _disk_live(ps):
    """Cột bộ nhớ ghi lên web lúc GIAO máy mới: máy chủ không nới được bộ nhớ (không phải MuMu / phonectl cũ) → bỏ số (web không hiện
       số sai) · phonectl chưa nới xong (dấu disk_new còn) → pending_disk = đích để vòng nới làm tiếp."""
    if engine().get("emu") != "mumu" or not phonectl_disk(): return {"disk_gb": None}
    w = _int((ps or {}).get("disk_new"))
    return {"pending_disk": w} if w >= 4 else {}
_dk = {"nocol": 0.0, "said": {}}
_dk_try = {}                       # id đơn → [số lần lỗi, lúc được thử lại]
DK_LATER_S, DK_RETRY_S, DK_MAX_FAIL = 300, 60, 6
def get_disk():
    if time.time() < _dk["nocol"]: return []
    try: return sb("GET", "cloud_phones?pending_disk=not.is.null&status=eq.active&select=*") or []
    except urllib.error.HTTPError as e:
        if e.code == 400: _dk["nocol"] = time.time() + 600; return []          # web chưa chạy SQL v40
        raise
def _bg_disk():
    try:
        for row in get_disk():
            if not mine(row): continue
            try: do_disk(row)
            except Exception as e: print("lỗi bộ nhớ:", e)
    except Exception as e: print("lỗi đọc đơn bộ nhớ:", e)
def disk_refund(row, msg):
    try: sb("POST", "rpc/cloudphone_disk_refund", {"p_id": row["id"], "p_err": msg})
    except Exception as e: print("   lỗi hoàn tiền bộ nhớ:", e)
def do_disk(row):
    """Đặt bộ nhớ máy khách lên pending_disk GB (khách mua thêm / nâng RAM lên bậc cao hơn) — chỉ lớn lên, giữ dữ liệu, không tắt máy."""
    pid = row["id"]; name = row.get("container") or cname(row); n = _int(row.get("pending_disk"))
    paid = _int(row.get("pending_disk_paid")); add = _int(row.get("pending_disk_add")); label = row.get("name") or name
    tr = _dk_try.get(pid) or [0, 0.0]
    if time.time() < tr[1]: return
    if n < 4:
        return disk_refund(row, "Cỡ bộ nhớ không hợp lệ")
    if not phonectl_disk():                       # phonectl máy này chưa cập nhật (chưa chạy lệnh A) → chờ, KHÔNG hoàn tiền
        _dk_try[pid] = [tr[0], time.time() + 600]
        if time.time() - _dk["said"].get(pid, 0) > 3600:
            _dk["said"][pid] = time.time(); print(f"[bộ nhớ] {label}: phonectl máy chủ {NODE_ID} chưa có lệnh disk — chạy lệnh A cập nhật máy chủ")
        return
    print(f"[bộ nhớ] {label} ({name}) → {n}GB" + (f" (khách mua +{add}GB)" if add else ""))
    r = phonectl(["disk", name, "--gb", str(n)])
    m = re.search(r"^DISK (\{.*\})\s*$", r.stdout or "", re.M)
    try: j = json.loads(m.group(1)) if m else {}
    except ValueError: j = {}
    k = j.get("k") or "?"; msg = str(j.get("msg") or (r.stdout or r.stderr or "")[-160:]).strip()
    if r.returncode == 0 and k in ("ok", "grown"):
        _dk_try.pop(pid, None)
        try:
            sb("PATCH", f"cloud_phones?id=eq.{pid}&pending_disk=eq.{n}",       # web vừa đổi đích (khách nâng RAM giữa chừng) → không ghi đè, vòng sau làm tiếp
               {"disk_gb": n, "pending_disk": None, "pending_disk_paid": None, "pending_disk_add": None, "disk_note": None,
                "updated_at": datetime.datetime.now().isoformat()}, {"Prefer": "return=minimal"})
        except Exception as e: print("   lỗi ghi bộ nhớ lên web:", e); return
        print(f"   ✓ {label}: bộ nhớ {msg}")
        if paid or k == "grown":
            notify(f"💾 Máy <b>{label}</b> ({NODE_ID}): bộ nhớ → {n}GB" + (f" · khách mua +{add}GB ({paid:,}đ)".replace(",", ".") if paid else ""))
        return
    if r.returncode == 6 or k == "later":         # máy tắt / ngủ / đang lên → phonectl đã hẹn lần bật, hỏi lại sau
        _dk_try[pid] = [tr[0], time.time() + DK_LATER_S]
        if time.time() - _dk["said"].get(pid, 0) > 3600: _dk["said"][pid] = time.time(); print(f"   … {label}: {msg}")
        return
    fails = tr[0] + 1
    print(f"   ✗ {label}: chưa nới được bộ nhớ ({k}: {msg[:160]}) — lần {fails}")
    if r.returncode == 4 or fails >= DK_MAX_FAIL:
        _dk_try.pop(pid, None)
        why = {"unsupported": "máy chủ chưa hỗ trợ", "nopart": "ổ máy không đủ chỗ", "notext4": "ổ máy không hỗ trợ nới",
               "hostlow": "máy chủ đang đầy ổ", "noroot": "máy chưa cho quyền nới"}.get(k, "máy chủ bận")
        disk_refund(row, f"Chưa nới được bộ nhớ ({why})")
        notify(f"⚠️ <b>{NODE_ID}</b>: máy <b>{label}</b> chưa nới được bộ nhớ lên {n}GB ({k}: {msg[:160]})"
               + (f" — đã hoàn {paid:,}đ cho khách.".replace(",", ".") if paid else "."))
    else:
        _dk_try[pid] = [fails, time.time() + DK_RETRY_S * fails]

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
                     + (["--until", str(row["until_at"])] if row.get("until_at") and phonectl_until() else [])
                     + (["--disk", str(int(row["disk_gb"]))] if _int(row.get("disk_gb")) >= 4 and phonectl_disk() else []))
        if r.returncode == 2:   # HẾT CHỖ lúc tạo (RAM thật ít hơn số ước)
            _FULL["until"] = time.time() + FULL_COOL_S
            print(f"   ✗ {NODE_ID} hết chỗ khi tạo máy → nghỉ nhận đơn {FULL_COOL_S // 60} phút, nhường đơn cho máy chủ khác")
            if age_s(row) < 600 and others_for(row)[1]:      # 16/11: còn máy chủ khác đủ chỗ → TRẢ ĐƠN cho nó nhận, KHÔNG hoàn tiền
                try:
                    back = sb("PATCH", f"cloud_phones?id=eq.{row['id']}&node=eq.{NODE_ID}&status=eq.pending", {"node": None},
                              {"Prefer": "return=representation"})
                    if back: print("   ↪ đã trả đơn — máy chủ còn chỗ sẽ nhận"); return
                except Exception as e: print("   lỗi trả đơn:", e)
            refund(row, "Máy chủ đã đầy, chưa tạo được máy")
            notify(f"⚠️ <b>Đơn ĐT đám mây bị hoàn tiền</b>: {NODE_ID} hết chỗ khi tạo máy và không máy chủ nào khác còn chỗ."); return
        if r.returncode != 0:
            log_err = (r.stdout + r.stderr)[-300:]
            print("   ✗", log_err)
            mark_sick("tạo máy mới bị lỗi")
            refund(row, "Tạo máy lỗi, vui lòng thử lại"); notify(f"⚠️ <b>Tạo máy lỗi</b> trên {NODE_ID} (đã hoàn tiền khách):\n<code>{log_err[-200:]}</code>"); return
        ps = phone_state(name)
        if not ps:
            refund(row, "Tạo máy lỗi, vui lòng thử lại"); return
        if not still_pending(row["id"]):             # 16/11f: đơn bị huỷ / tự huỷ (quá lâu) trong lúc nhân bản → không giao máy
            drop_vm(name, f"đơn {row['id'][:8]} đã huỷ trong lúc tạo"); return
        patch(row["id"], {"container": name, "port": ps["port"], "node": NODE_ID})
    if name in BOOTING: return
    BOOTING.add(name); BOOT_T.setdefault(name, time.time())
    threading.Thread(target=finish_boot, args=(row["id"], name, "pending_disk" in row), daemon=True).start()

def finish_boot(pid, name, v40=False):
    try:
        t0 = time.time()
        r = phonectl(["waitboot", name, "--noapps"])   # chỉ chờ Android lên → giao máy cho khách NGAY
        if r.returncode in (5, 124) and not still_pending(pid):    # 16/11f: đơn đã tự huỷ (quá lâu) / khách huỷ → thôi chờ
            return drop_vm(name, "đơn đã huỷ trong lúc chờ Android lên")
        # 14/11: Android chưa lên sau 5 phút (máy chủ bận / MuMu nhân bản máy mẫu lâu — hay gặp khi ĐỔI ANDROID) → bản cũ vẫn
        # giao máy → khách mở thấy MÀN ĐEN, bấm không được. Giờ: chờ thêm 1 lượt → vẫn chưa thì ép khởi động lại 1 lần → mới giao.
        if r.returncode in (5, 124):
            print(f"   … {name}: Android chưa lên sau {time.time() - t0:.0f}s → chờ thêm 1 lượt (chưa giao cho khách, tránh màn đen)")
            r = phonectl(["waitboot", name, "--noapps"])
        if r.returncode in (5, 124):
            mark_sick(f"máy mới {name} chờ {(time.time() - t0) / 60:.0f} phút vẫn chưa lên")
        if r.returncode in (5, 124) and not still_pending(pid):
            return drop_vm(name, "đơn đã huỷ trong lúc chờ Android lên")
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
        live = {"status": "active", "container": name, "port": ps["port"], "node": NODE_ID,
                "stream_url": stream_url(ps["port"]), "expires_at": parse_dt(ps["expires"]).isoformat(), "error": None}
        if v40: live.update(_disk_live(ps))                # 19/11: bộ nhớ THẬT lúc giao (SQL v40)
        # 16/11f: chỉ giao khi đơn CÒN chờ (cùng 1 lệnh với điều kiện) — đơn vừa tự huỷ + hoàn tiền (quá lâu) / khách huỷ thì KHÔNG
        # "sống lại" (trước: ghi đè thành đang chạy → khách vừa được hoàn tiền vừa có máy, hoặc máy đã huỷ vẫn chạy).
        try:
            got = sb("PATCH", f"cloud_phones?id=eq.{pid}&status=eq.pending", {**live, "updated_at": datetime.datetime.now().isoformat()},
                     {"Prefer": "return=representation"})
        except urllib.error.HTTPError as e:
            if e.code != 409: raise
            got = still_pending(pid)                    # trùng cổng / máy (máy ma) → đường cũ tự gỡ rồi ghi lại
            if got: patch(pid, live)
        if not got:
            return drop_vm(name, "đơn đã bị huỷ / tự huỷ trước khi giao")
        BOOT_T.pop(name, None)
        print(f"   ✓ {name} sẵn sàng sau {time.time() - t0:.0f}s, cổng {ps['port']} — đang cài app sẵn ở nền")
        r = phonectl(["preinstall", name])     # cài app sẵn song song, khách đang dùng máy vẫn được
        for ln in (r.stdout or "").splitlines():
            if ln.strip().startswith(("+", "!")): print("  ", ln.strip())
    except Exception as e:
        if getattr(e, "code", 0) != 409: print("lỗi chờ khởi động:", e)     # 409 trùng máy: patch() đã ghi nhật ký (1 lần / phút)
    finally:
        BOOTING.discard(name); BOOT_T.pop(name, None)

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
            print(f"[tự dọn] đã xoá hẳn {j['deleted']} máy khách web đã huỷ còn sót trên máy chủ (máy ảo + dữ liệu)"
                  + (f", trong đó {j['lost']} máy mất tên" if j.get("lost") else ""))
            ts_note(f"tự dọn {j['deleted']} máy khách web đã huỷ mà còn sót trên máy chủ (đã xoá hẳn máy + dữ liệu)", key="dondep", every=1800)
        if j.get("fail"): print(f"[tự dọn] còn {j['fail']} máy đã huỷ chưa xoá được (giả lập bận) — 10 phút sau thử lại")
        if j.get("lost_live"):                              # máy khách ĐANG THUÊ bị mất tên trong giả lập → tự đặt lại tên (giữ dữ liệu), như lệnh A
            r2 = phonectl(["nhanlai"])
            got = [ln[9:] for ln in (r2.stdout or "").splitlines() if ln.startswith("NHAN_LAI ")]
            for ln in got: print("[tự sửa] " + ln)
            ts_note(f"{j['lost_live']} máy khách đang thuê bị MẤT TÊN trong giả lập" + (f" — đã tự đặt lại tên {len(got)} máy" if got else " — chưa đặt lại được, chạy lệnh A"),
                    key="lostlive", every=3600, again=False)
    except Exception as e: print("lỗi tự dọn máy sót:", e)

def _bg_apps():
    try:
        r = phonectl(["preinstall", "--all"])
        for ln in (r.stdout or "").splitlines():
            if ln.strip(): print("  ", ln.strip())
        phonectl(["perms"])
    except Exception as e: print("lỗi cài app sẵn / mở quyền APK:", e)

# ---------------- 23/11f · BẢN ĐANG CHẠY + TỰ CẬP NHẬT THEO MÁY CHỦ KHÁC ----------------
# Mỗi máy chủ ghi kết quả lần cập nhật gần nhất vào ~/logs/cap-nhat.json (sua-tat-ca.py ghi) và báo lên web trong metrics.sw.
# TỰ THEO: admin cập nhật 1 máy chủ (lệnh A hoặc nút Cập nhật trên web). Bản đó chạy ỔN ở máy chủ ấy đủ lâu (mặc định 20 phút: cập nhật
# sạch + dịch vụ còn sống, vẫn báo cáo đều) thì các máy chủ khác TỰ tải sua-tat-ca.py từ GitHub và chạy `--tu-dong` — chỉ khi bản trên GitHub
# ĐÚNG LÀ bản đã chạy ổn đó (không bao giờ tự cài bản chưa máy chủ nào chạy thử; chỉ cài đúng bản đang ở GitHub). Mỗi bản tự thử tối đa 2 lần; lệch
# giờ ngẫu nhiên tới 10 phút để các máy chủ không cập nhật cùng lúc. Lượt tự cập nhật KHÔNG đụng máy khách (chỉ thay file + bật lại dịch vụ).
# 24/11b · BẢN MỚI TỰ CÀI, KHÔNG CẦN AI BẤM: GitHub có bản mới mà chưa máy chủ nào chạy → máy chủ "THỬ TRƯỚC" (Windows, còn sống, ÍT MÁY
# KHÁCH NHẤT — mọi máy chủ đọc cùng bảng nên cùng chọn 1 máy) tự cài (hỏi GitHub 15 phút / lần). Chạy ổn đủ thời gian chờ → các máy chủ
# khác tự theo như trên. Bản thử hỏng (2 lần) → dừng ở đó, báo Telegram, các máy chủ khác KHÔNG cài bản đó.
# Tắt cho mọi máy chủ: web admin (settings.data.node_update.auto = false) · tắt riêng máy chủ này: TU_CAP_NHAT=0 trong cloudphone.conf.
CPD_VER = "27/11k"
SW_STATE_F = os.path.join(HOME, "logs", "cap-nhat.json")
SW_LOG_F = os.path.join(HOME, "logs", "cap-nhat.log")
SW_TRIES_F = os.path.join(HOME, "logs", "cap-nhat-tu-dong.json")
SUA_FILE = os.path.join(HOME, "sua-tat-ca.py")
SUA_URLS = (("https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/sua-tat-ca.py?ref=main", {"Accept": "application/vnd.github.raw"}),
            ("https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/windows/sua-tat-ca.py", {}))
FOLLOW_ON = (CFG.get("TU_CAP_NHAT", "1") or "1").strip() != "0"
FOLLOW_JITTER = _f("TU_CAP_NHAT_LECH_S", 600)     # lệch giờ ngẫu nhiên (giây) giữa các máy chủ
FOLLOW_TRIES = 2
FOLLOW_SKIP_S = 1800                              # GitHub chưa có đúng bản đó → 30 phút sau mới đối chiếu lại (không hỏi GitHub mỗi 5 phút)
_follow = {"due": 0.0, "for": None, "said": None, "skip": None, "skip_t": 0.0}
FIRST_CHECK_S = _f("TU_CAP_NHAT_THU_S", 900)     # 24/11b: máy chủ THỬ TRƯỚC hỏi GitHub có bản mới chưa — 15 phút / lần
_first = {"t": 0.0}

def sw_state():
    try:
        d = json.load(open(SW_STATE_F, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def sw_running(st=None):
    r = (sw_state() if st is None else st).get("running") or {}
    try: return bool(r) and time.time() - float(r.get("start") or 0) < 1800
    except (TypeError, ValueError): return False

def _small(x, n=1800):
    """x nếu viết ra JSON không quá n ký tự (metrics gửi 30 giây / lần — giữ gọn), không thì None."""
    try: return x if len(json.dumps(x, ensure_ascii=False)) <= n else None
    except (TypeError, ValueError): return None

def sw_tune(st):
    """27/11k · kết quả bước 3b / 3c của sua-tat-ca 27/11j+ (tối ưu như máy cài từ ISO + phần mềm trên máy + card) → web thẻ máy chủ."""
    tu = st.get("tune") if isinstance(st.get("tune"), dict) else {}
    iv = st.get("inv") if isinstance(st.get("inv"), dict) else {}
    cards = ((iv.get("gpu") or {}).get("cards") or []) if isinstance(iv.get("gpu"), dict) else []
    t2 = _small({k: tu.get(k) for k in ("ok", "did", "miss", "plan", "defender", "av", "whea")}) if tu else None
    i2 = _small({"os": iv.get("os"), "emu": iv.get("emu"), "vga": iv.get("vga"), "adb": iv.get("adb"), "py": iv.get("py"), "tools": iv.get("clock_tools"),
                 "gpu": [{k: c.get(k) for k in ("name", "drv", "stuck", "why", "vram_full")} for c in cards[:2] if isinstance(c, dict)]}) if iv else None
    return t2, i2

def sw_info():
    """Phần báo lên web (metrics.sw): bản đang chạy, lúc cài, cập nhật sạch không, đang cập nhật không (+ 27/11k: tối ưu như ISO, phần mềm trên máy)."""
    st = sw_state(); last = st.get("last") if isinstance(st.get("last"), dict) else None
    tu, iv = sw_tune(st)
    return {"ver": st.get("ver"), "at": st.get("at"), "upd": bool(st.get("upd")), "ok": bool(st.get("ok")), "auto": bool(st.get("auto")),
            "run": sw_running(st), "last": last, "cpd": CPD_VER, "follow": FOLLOW_ON, "first": True, "win": WIN, "tune": tu, "inv": iv}

def follow_conf(site=None):
    """(đang bật tự theo?, số phút bản mới phải chạy ổn) — web admin đặt ở settings.data.node_update; chưa đặt: bật, 20 phút."""
    if site is None: site = ((sb("GET", "settings?id=eq.1&select=data") or [{}])[0].get("data") or {})
    nu = site.get("node_update") if isinstance(site.get("node_update"), dict) else {}
    try: soak = max(5.0, min(1440.0, float(nu.get("soak_min", 20))))
    except (TypeError, ValueError): soak = 20.0
    return nu.get("auto", True) is not False, soak

def follow_cands(me_ver, rows, t_now, soak_min, me=None):
    """Các bản (khác bản của mình) đang chạy ỔN ở máy chủ KHÁC còn sống: báo cáo trong 3 phút gần nhất, cập nhật sạch (upd), không đang cập
       nhật dở, đã cài được ≥ soak_min phút. rows = các dòng cloud_nodes (id, metrics, updated_at)."""
    out = set(); me = NODE_ID if me is None else me
    for r in rows or []:
        try:
            if r.get("id") == me: continue
            if (now() - parse_dt(r.get("updated_at"))).total_seconds() > 180: continue
            sw = (r.get("metrics") or {}).get("sw") or {}
            v, at = sw.get("ver"), sw.get("at")
            if not v or not isinstance(v, str) or v == me_ver or not sw.get("upd") or sw.get("run") or not at: continue
            if t_now - float(at) < soak_min * 60: continue
            out.add(v)
        except Exception:
            continue
    return out

def sua_fetch(get=None):
    """Tải sua-tat-ca.py mới nhất từ GitHub (như lệnh A) → (nội dung, bản). Không tải được / file lạ → ném lỗi."""
    def _get(url, h):
        req = urllib.request.Request(url, headers=dict({"User-Agent": "cloudblue-sua-tat-ca", "Cache-Control": "no-cache"}, **h))
        with urllib.request.urlopen(req, timeout=60) as r: return r.read()
    for url, h in SUA_URLS:
        try: data = (get or _get)(url, h)
        except Exception: continue
        m = re.search(rb'^VER = "([0-9a-z/]{3,12})"', data or b"", re.M)
        if data and len(data) > 20000 and b"cloudblue-sua-tat-ca" in data and m:
            try: compile(data.decode("utf-8"), "sua-tat-ca.py", "exec")
            except Exception: continue
            return data, m.group(1).decode()
    raise RuntimeError("chưa tải được sua-tat-ca.py từ GitHub")

def _tries_load():
    try:
        d = json.load(open(SW_TRIES_F, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def follow_step(t_now=None, get=None, spawn=None, rows=None, site=None, rnd=random.uniform):
    """1 nhịp tự theo (gọi ~5 phút / lần). Trả chữ cho biết đã làm gì: "off" · "run" · "none" · "wait" · "nomatch" · "tries" · "go <bản>"
       · "first <bản>" (24/11b: máy này thử trước bản mới trên GitHub)."""
    t_now = time.time() if t_now is None else t_now
    if not FOLLOW_ON: return "off"
    st = sw_state(); me_ver = st.get("ver")
    if sw_running(st): return "run"
    auto, soak = follow_conf(site)
    if not auto: _follow["due"] = 0.0; return "off"
    if rows is None: rows = sb("GET", "cloud_nodes?select=id,metrics,updated_at,phones") or []
    r = first_step(t_now, me_ver, rows, get, spawn)              # 24/11b: GitHub có bản mới chưa máy chủ nào chạy → máy chủ ít khách nhất tự cài thử
    if r != "none": return r
    cands = follow_cands(me_ver, rows, t_now, soak)
    if not cands: _follow["due"] = 0.0; _follow["for"] = None; return "none"
    key = ",".join(sorted(cands))
    if _follow["skip"] == (key, me_ver) and t_now < _follow["skip_t"]: return "nomatch"      # vừa đối chiếu: GitHub không phải bản đó → chưa hỏi lại
    if not _follow["due"] or _follow["for"] != key:           # vừa thấy bản khác chạy ổn ở máy chủ khác → hẹn giờ lệch ngẫu nhiên rồi đối chiếu GitHub
        _follow["due"] = t_now + rnd(0, max(0.0, FOLLOW_JITTER)); _follow["for"] = key
        print(f"[tự cập nhật] máy chủ khác đang chạy ổn bản {key} (máy này: {me_ver or '?'}) → ~{max(0, _follow['due'] - t_now) / 60:.0f} phút nữa đối chiếu với GitHub, đúng bản đó thì tự cập nhật")
    if t_now < _follow["due"]: return "wait"
    data, ver = sua_fetch(get)
    if ver == me_ver or ver not in cands:                       # GitHub chưa có / không phải bản đã chạy ổn đó → không làm gì
        _follow["due"] = 0.0; _follow["skip"] = (key, me_ver); _follow["skip_t"] = t_now + FOLLOW_SKIP_S
        print(f"[tự cập nhật] GitHub đang là bản {ver}" + (" = bản máy này đang chạy" if ver == me_ver else " — chưa máy chủ nào chạy ổn bản đó") + " → không làm gì")
        return "nomatch"
    return follow_go(data, ver, spawn, f"bản {ver} đã chạy ổn ở máy chủ khác ≥ {soak:g} phút")

def follow_go(data, ver, spawn=None, why=""):
    """Cài bản ver (data = sua-tat-ca.py vừa tải từ GitHub): tối đa FOLLOW_TRIES lần / bản; ghi file + chạy `--tu-dong` TÁCH RỜI
       (lượt đó tắt + bật lại chính cloudphoned). Trả "go <bản>" · "tries" (đã thử đủ lần → thôi, báo admin 1 lần)."""
    tries = _tries_load(); n = int(tries.get(ver) or 0)
    if n >= FOLLOW_TRIES:
        if _follow["said"] != ver:
            _follow["said"] = ver
            print(f"[tự cập nhật] đã tự thử bản {ver} {n} lần mà chưa xong — thôi tự thử, chạy lệnh A bằng tay ở máy chủ này")
            try: notify(f"⚠️ <b>{NODE_ID}</b>: tự cập nhật lên bản {ver} {n} lần chưa xong — vào máy chủ chạy lệnh A (hoặc bấm 🛠 Quản lý › Cập nhật trên web).")
            except Exception: pass
        return "tries"
    tries[ver] = n + 1
    try:
        os.makedirs(os.path.dirname(SW_TRIES_F), exist_ok=True)
        with open(SW_TRIES_F, "w", encoding="utf-8") as f: json.dump({k: v for k, v in list(tries.items())[-20:]}, f)
    except Exception as e: print("lỗi ghi sổ tự cập nhật:", e)
    with open(SUA_FILE + ".new", "wb") as f: f.write(data)
    os.replace(SUA_FILE + ".new", SUA_FILE)
    cmd = [sys.executable, "-u", SUA_FILE, "--tu-dong"]
    print(f"[tự cập nhật] {why} → tự cập nhật máy chủ này lên {ver} (lần {n + 1}/{FOLLOW_TRIES}); nhật ký: logs/cap-nhat.log")
    if spawn: spawn(cmd)
    else:
        lf = open(SW_LOG_F, "wb")
        try:
            kw = {"creationflags": 0x08000000 | 0x00000200} if WIN else {"start_new_session": True}      # tách rời: lượt này sẽ tắt + bật lại chính cloudphoned
            subprocess.Popen(cmd, cwd=HOME, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
        finally:
            lf.close()
    _follow["due"] = 0.0; _follow["for"] = None
    return "go " + ver

def _live(rows):
    """Các dòng cloud_nodes của máy chủ CÒN SỐNG (báo cáo trong 3 phút gần nhất)."""
    out = []
    for r in rows or []:
        try:
            if (now() - parse_dt(r.get("updated_at"))).total_seconds() <= 180: out.append(r)
        except Exception: continue
    return out

def first_pick(rows):
    """24/11b · máy chủ THỬ TRƯỚC bản mới: máy chủ Windows còn sống, chạy cloudphoned biết thử trước (sw.first), không tắt tự cập nhật,
       ÍT MÁY KHÁCH NHẤT (bằng nhau: mã nhỏ hơn). Mọi máy chủ đọc cùng 1 bảng → cùng chọn 1 máy. Trả mã máy chủ (None = không có)."""
    best = None
    for r in _live(rows):
        try:
            sw = (r.get("metrics") or {}).get("sw") or {}
            if sw.get("first") is not True or sw.get("win") is False or sw.get("follow") is False: continue
            k = (int(float(r.get("phones") or 0)), str(r.get("id") or ""))
            if best is None or k < best: best = k
        except Exception: continue
    return best[1] if best else None

def first_step(t_now, me_ver, rows, get=None, spawn=None):
    """24/11b · phần THỬ TRƯỚC của mỗi nhịp tự cập nhật (chạy trước phần tự theo). Chỉ máy chủ được chọn (first_pick) mới hỏi GitHub, 15 phút / lần.
       GitHub có bản KHÁC bản đang chạy mà chưa máy chủ nào chạy / thử bản đó → tự cài (≤ 2 lần / bản). Máy chủ khác đang cập nhật dở → chờ.
       Trả "none" · "first <bản>" · "tries"."""
    live = _live(rows)
    if first_pick(live) != NODE_ID: return "none"
    if any(((r.get("metrics") or {}).get("sw") or {}).get("run") for r in live if r.get("id") != NODE_ID): return "none"
    if _first["t"] and t_now - _first["t"] < FIRST_CHECK_S: return "none"
    _first["t"] = t_now
    data, ver = sua_fetch(get)
    if ver == me_ver: return "none"
    for r in live:                                       # đã có máy chủ chạy / đang thử / thử hỏng bản này → để luật tự theo lo (chạy ổn đủ lâu mới theo)
        if r.get("id") == NODE_ID: continue
        sw = (r.get("metrics") or {}).get("sw") or {}
        if sw.get("ver") == ver or (isinstance(sw.get("last"), dict) and sw["last"].get("ver") == ver): return "none"
    r = follow_go(data, ver, spawn, f"GitHub có bản mới {ver} (máy này: {me_ver or '?'}), chưa máy chủ nào chạy — máy này ít khách nhất nên "
                                    f"THỬ TRƯỚC; chạy ổn đủ lâu thì các máy chủ khác tự theo")
    return ("first " + ver) if r.startswith("go ") else r

def _bg_follow():
    try: follow_step()
    except Exception as e: print("lỗi tự cập nhật:", e)

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

def gpu_stuck(util, clk, cmax, pwr=None, pmax=None):
    """27/11k · card KẸT XUNG NGHỈ: bận ≥ 80% mà xung < 30% tối đa (+ điện < 25% giới hạn khi đọc được). win3 27/11: 98% ở 139/1974 MHz, 9/180 W,
       card báo "SW Power Cap" dù giới hạn điện đúng mặc định, khởi động lại vẫn kẹt (nghi nguồn điện của card) → card chậm hơn chục lần, mọi máy khách lag."""
    try: return bool(util is not None and clk and cmax and util >= 80 and clk < 0.3 * cmax and (pwr is None or not pmax or pwr < 0.25 * pmax))
    except TypeError: return False

def gpu_eff(util, clk, cmax, pwr=None, pmax=None):
    """27/11b · % card THẬT: card đang ở xung nhịp thấp (< 50% xung tối đa — chế độ nghỉ) mà nvidia-smi báo % vừa phải = việc lặt vặt
       chạy liên tục, card còn dư → nhân theo tỉ lệ xung. Card chạy nặng thật luôn lên xung cao → giữ nguyên %.
       27/11k: card BẬN gần hết mà vẫn ở xung nghỉ = KẸT (gpu_stuck), KHÔNG phải rảnh → coi là đầy 100% để máy chủ ngừng nhận máy mới
       (27/11b tính nhầm win3 là ~7% nên máy chủ kẹt card vẫn nhận khách mới)."""
    if util is None or not clk or not cmax: return util
    if gpu_stuck(util, clk, cmax, pwr, pmax): return 100.0
    r = clk / cmax
    return util if r >= 0.5 else round(util * r, 1)

def gpus():
    num = lambda x: float(x) if x.replace(".", "", 1).isdigit() else None
    for q in ("name,utilization.gpu,memory.used,memory.total,temperature.gpu,clocks.sm,clocks.max.sm,power.draw,power.limit",
              "name,utilization.gpu,memory.used,memory.total,temperature.gpu"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=" + q, "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
            out = []
            for line in r.stdout.strip().splitlines():
                f = [x.strip() for x in line.split(",")]
                if len(f) != q.count(",") + 1: raise ValueError(line)
                g = {"name": f[0], "util": num(f[1]), "mem_used": num(f[2]), "mem_total": num(f[3]), "temp": num(f[4])}
                if len(f) > 5:
                    g.update(clk=num(f[5]), clk_max=num(f[6]), pwr=num(f[7]), pwr_max=num(f[8]))
                    g["eff"] = gpu_eff(g["util"], g["clk"], g["clk_max"], g["pwr"], g["pwr_max"])
                    if gpu_stuck(g["util"], g["clk"], g["clk_max"], g["pwr"], g["pwr_max"]): g["stuck"] = True     # 27/11k: web + Telegram báo kẹt xung
                out.append(g)
            if out or r.returncode == 0: return out
        except Exception:
            continue
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
    g_list = gpus(); gf = gf_fresh(); held = float((gf or {}).get("held") or 0)
    g_eff = [dict(g, util=max(0.0, (g["eff"] if g.get("eff") is not None else g["util"]) - held)) if g.get("util") is not None else g for g in g_list]   # 27/11b: % THẬT (theo xung)   # 27/11a: máy đã hạ ưu tiên card nhường máy khác → không chặn nhận máy mới
    g_avg, v_avg = gpu_avg5(g_eff); g_why = gpu_busy()
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
        if time.time() < _FULL["until"]: c_ram, c_cpu = a_ram, a_cpu    # 16/11: vừa hết chỗ lúc tạo máy → báo web hết chỗ ít phút
        if busy_boot() or sick_why(): c_ram, c_cpu = a_ram, a_cpu       # 16/11f/g: quá tải / máy mới không lên → web bán máy chủ khác
    else:                                               # Linux: c_ram đã là LIMIT_PCT % RAM (như cũ) → sức chứa thật = 100%
        f_ram, f_cpu, stop = (ram_t * RAM_OVER if c_ram > a_ram else c_ram), c_cpu, float(LIMIT_PCT)
    fill = 100 * max(a_ram / f_ram if f_ram > 0 else 1.0, a_cpu / f_cpu if f_cpu > 0 else 1.0)
    metrics = {"cpu_pct": cp_now, "cpu_avg5": avg5, "cpu_over": CPU_OVER, "cpu_busy_pct": CPU_BUSY, "cpu_busy": busy, "ram_over": RAM_OVER, "ram_pct": ram_pct, "ram_busy_pct": RAM_BUSY, "ram_busy": ram_busy, "disk_busy": disk_busy, "disk_busy_pct": DISK_BUSY, "load": [round(x, 2) for x in os.getloadavg()], "cpu_temp": cpu_temp(),
               "ram_used": round(ram_t - ram_avail, 1), "gpus": g_list, "gpu_avg5": g_avg, "vram_avg5": v_avg, "gpu_busy_pct": GPU_BUSY, "vram_busy_pct": VRAM_BUSY, "gpu_busy": g_why == "gpu", "vram_busy": g_why == "vram", "disk_data": disk(DATA_ROOT), "disk_root": disk("/"),
               "running": running, "sleeping": sum(1 for p in st if p.get("sleep") and p.get("hold")), "uptime_h": up_h, "base": BASE, "primary": PRIMARY, "renew_v": 2}     # renew_v 2: gia hạn chỉ xoá ngày chờ khi đã ghi được
    if WIN: metrics.update(ram_over=WIN_RAM_OVER, sleep_gb=round(zz, 1), sleep_full_gb=round(zz_full, 1), sleep_pct=round(100 * ram_ratio() / WIN_RAM_OVER))   # web: máy ngủ giữ bao nhiêu RAM
    metrics.update(cap_ram_full=round(f_ram, 1), cap_cpu_full=round(f_cpu, 1), full_pct=stop, fill_pct=round(min(100.0, fill), 1))   # web: % đầy cho khách (SQL v33)
    if gf: metrics.update(gpu_top=gf.get("top") or [], gpu_held=held, gpu_fair=gf.get("fair"), gpu_hog=gf.get("hog"), gpu_other=gf.get("other") or [])   # 27/11a: máy nào ăn card
    try: metrics["sw"] = sw_info()                      # 23/11f: bản đang chạy + lần cập nhật gần nhất (web: thẻ máy chủ · máy chủ khác: tự theo)
    except Exception as e: print("lỗi đọc sổ cập nhật:", e)
    try: metrics["host"] = str(os.environ.get("COMPUTERNAME") or socket.gethostname() or "")[:64]   # 24/11: tên máy → web nối dòng máy chủ với "điều khiển từ xa" (agent CloudBlue PC)
    except Exception: pass
    body = {"id": NODE_ID, "cpu_total": cpu_t, "ram_total": round(ram_t, 1), "cap_cpu": round(c_cpu, 1), "cap_ram": round(c_ram, 1),
            "alloc_cpu": a_cpu, "alloc_ram": a_ram, "phones": len(st), "limit_pct": LIMIT_PCT, "metrics": metrics,
            "updated_at": now().isoformat()}
    if eng_due(): _engine_read()                         # 24/11b: vừa tạo máy mẫu → đọc ngay · thiếu máy mẫu: 2 phút / lần · đủ: 10 phút / lần
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
    sk = [g for g in g_list if g.get("stuck")]           # 27/11k: card kẹt xung nghỉ (lời báo riêng)
    if _alert["full"] is not None and full != _alert["full"]:
        notify((f"🚨 <b>{NODE_ID}: CPU thật đang {avg5:.0f}%</b> (ngưỡng {CPU_BUSY}%) — tạm ngừng nhận máy mới." if busy else
                f"🚨 <b>{NODE_ID}: RAM thật đang dùng {ram_pct:.0f}%</b> (ngưỡng {RAM_BUSY}%) — tạm ngừng nhận máy mới." if ram_busy else
                f"🚨 <b>{NODE_ID}: ổ cứng sắp đầy</b> (ngưỡng {DISK_BUSY}%) — tạm ngừng nhận máy mới. Xoá bớt máy hết hạn / file thừa." if disk_busy else
                (f"🚨 <b>{NODE_ID}: card đồ hoạ KẸT XUNG NGHỈ</b> — bận {sk[0]['util']:.0f}% mà chỉ {sk[0]['clk']:.0f}/{sk[0]['clk_max']:.0f} MHz"
                 + (f", {sk[0]['pwr']:.0f} W" if sk[0].get("pwr") is not None else "") + " → máy khách trên máy chủ này lag. Tạm ngừng nhận máy mới. "
                 "Khởi động lại máy chủ lúc vắng khách; vẫn kẹt → tắt máy, cắm lại chặt dây nguồn 8 pin của card (không qua dây chia / chuyển), kiểm nguồn."
                 if sk else f"🚨 <b>{NODE_ID}: card đồ hoạ đang chạy {g_avg or 0:.0f}%</b> (TB 5 phút, ngưỡng {GPU_BUSY}%) — tạm ngừng nhận máy mới.") if g_why == "gpu" else
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

# 27/11a · CHIA ĐỀU CARD ĐỒ HOẠ: ~1 phút / lần "phonectl gpufair" — đo % card từng máy, máy ăn quá phần lúc card bận → hạ ưu tiên card
#          (máy khác được card trước). Kết quả báo web (gpu_top) + phần card của máy đã bị hạ ưu tiên KHÔNG tính là "card quá tải".
GF_ON = WIN and _f("GPU_FAIR", 1) > 0
_gfair = {"t": 0.0, "res": None, "said": 0.0}
def _gf_loop():
    while True:
        try:
            r = subprocess.run(["python3", PHONECTL, "gpufair"], capture_output=True, text=True, timeout=240)
            o = (r.stdout or "") + (r.stderr or "")
            for ln in o.splitlines():
                if ln.startswith("GPUFAIR_ACT"): print("[card]", ln[12:].strip())
                elif ln.startswith("GPUFAIR "):
                    try: j = json.loads(ln[8:])
                    except ValueError: j = None
                    if isinstance(j, dict) and j.get("ok"): _gfair.update(t=time.time(), res=j)
                    elif isinstance(j, dict) and time.time() - _gfair["said"] > 6 * 3600: _gfair["said"] = time.time(); print("[card] chưa chia đều được:", j.get("why"))
            if r.returncode == 2 and "invalid choice" in o and time.time() - _gfair["said"] > 6 * 3600:
                _gfair["said"] = time.time(); print("[card] phonectl.py bản cũ chưa có lệnh gpufair")
        except Exception as e:
            print("lỗi chia đều card:", e)
        time.sleep(60)
def gf_fresh():
    """Kết quả chia đều card gần nhất (≤ 5 phút) hoặc None."""
    return _gfair["res"] if _gfair["res"] and time.time() - _gfair["t"] <= 300 else None

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
    bg_job("disk", _bg_disk)        # 19/11: khách mua thêm bộ nhớ / nâng RAM lên bậc cao hơn → nới (luồng riêng)
    for row in get_live():
        if not mine(row): continue
        try: do_expiry(row)
        except Exception as e: print("lỗi hết hạn:", e)
    try: release_switch_waits()
    except Exception as e: print("lỗi đổi Android chờ máy cũ:", e)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(line_buffering=True)   # in log ngay để xem bằng journalctl
    except Exception: pass
    print(f"cloudphoned bản 27/11k chạy — đọc {SB} mỗi {POLL}s. Ctrl+C để dừng.")
    if WIN: print("Tự cập nhật theo máy chủ khác (23/11f): " + ("BẬT — bản mới chạy ổn ở 1 máy chủ đủ lâu (web admin đặt, mặc định 20 phút) thì máy này tự cập nhật; "
                                                              "tắt riêng máy này: TU_CAP_NHAT=0" if FOLLOW_ON else "TẮT ở máy chủ này (TU_CAP_NHAT=0)"))
    print("Bộ nhớ máy khách (19/11a): máy MỚI theo cấu hình (web: bậc RAM → GB) · khách mua thêm bộ nhớ → máy chủ nới ngay, không tắt máy"
          + ("" if phonectl_disk() else " — ⚠ phonectl máy này CHƯA có lệnh disk (chạy lệnh A)"))
    if WIN: print("Tự dọn máy khách web đã HUỶ còn sót trên máy chủ (kể cả máy mất tên): ~1 phút sau khi bật, rồi 10 phút / lần (17/11f: tự dọn máy đã huỷ)")
    if SICK_MIN > 0: print(f"Máy mới tạo ra mà không lên → tự ngừng nhận đơn mới {SICK_MIN:g} phút + báo admin (máy chủ hỏng không giành đơn nữa)")
    if STUCK_MIN > 0: print(f"Đơn tạo máy quá {STUCK_MIN:g} phút chưa lên → tự huỷ + hoàn tiền, báo khách tạo máy mới (SQL v36) · máy tạo dở của đơn đó tự xoá")
    if BOOT_MAX > 0: print(f"Đang có ≥ {BOOT_MAX} máy mới chưa lên, hoặc 1 máy mới chờ quá {BOOT_SLOW_S / 60:g} phút → tạm không nhận đơn mới (đơn sang máy chủ khác)")
    if NEAR_PCT > 0: print(f"Đơn admin chọn máy chủ này lúc đã đầy ≥ {NEAR_PCT:g}% → tự chuyển sang máy chủ còn trống nhất (trống hơn ≥ {NEAR_GAP:g} điểm)")
    if WIN and CAP_CPU > 0: print(f"Trần mỗi máy chủ: {CAP_CPU:g} nhân (≤ luồng × {CPU_SELL_X:g} − {CPU_KEEP:g}) · {CAP_RAM:g}GB RAM · hết chỗ lúc tạo máy → trả đơn cho máy chủ khác")
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
    if GF_ON: threading.Thread(target=_gf_loop, daemon=True).start()   # 27/11a: chia đều card đồ hoạ giữa các máy khách
    threading.Thread(target=_stuck_loop, daemon=True).start()  # 16/11f: đơn tạo máy treo quá lâu → tự huỷ + hoàn tiền (luồng riêng)
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
        if WIN and (n == 4 or n % 40 == 20): # 17/11f: tự dọn máy đã huỷ — ~1 phút sau khi bật (máy chủ vừa khởi động lại: máy khách huỷ lúc
            bg_job("dondep", _bg_dondep)    #   máy chủ tắt được xoá ngay) rồi ~10 phút / lần (trước 30 phút): xoá hẳn máy web đã huỷ còn sót
        if WIN and FOLLOW_ON and n % 20 == 17:   # 23/11f · ~5 phút: máy chủ khác đã chạy ổn bản mới → tự cập nhật theo (luồng riêng)
            bg_job("follow", _bg_follow)
        if n % 20 == 12:                    # ~5 phút: máy nào chưa root → tự root (chạy nền, không chặn việc nhận đơn)
            try:
                if _rootjob[0] is None or _rootjob[0].poll() is not None:
                    _rootjob[0] = subprocess.Popen(["python3", PHONECTL, "rootfix", "--all"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e: print("lỗi tự root:", e)
        n += 1
        time.sleep(3)
