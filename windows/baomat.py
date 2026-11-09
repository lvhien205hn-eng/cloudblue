# -*- coding: utf-8 -*-
r"""
baomat.py — BẢO MẬT + ĐỒ HOẠ cho máy chủ Windows CloudBlue (MuMu / LDPlayer)

  & $PY C:\blue\baomat.py              kiểm tra + sửa + in báo cáo (PowerShell quyền Admin, mỗi máy chủ chạy 1 lần)
  & $PY C:\blue\baomat.py start        bật canh gác chạy nền nếu chưa chạy (run.py tự gọi mỗi lần bật cloudphoned)
  & $PY C:\blue\baomat.py khoidonglai  khởi động lại LẦN LƯỢT máy khách MuMu đang chạy để ăn cài đặt đồ hoạ (mỗi máy mất ~1 phút)
  & $PY C:\blue\baomat.py tatgac       tắt canh gác

MỖI MÁY KHÁCH RIÊNG HOÀN TOÀN. Giả lập mặc định DÙNG CHUNG vài thứ cho MỌI máy trên 1 máy chủ:
 1) Thư mục chia sẻ — MuMu: "MuMu共享文件夹" (hiện trong app Files của MỌI máy) · LDPlayer: Documents\XuanZhi9\Pictures / Misc /
    Applications (= /sdcard/Pictures… của mọi máy) → khách này thấy file của khách kia.
    → chỉ dời FILE cũ hơn BAOMAT_SHARE_AGE phút (mặc định 30) vào kho cách ly C:\blue\cachly (KHÔNG xoá; giữ 3 ngày),
      canh gác quét mỗi 30 giây. KHÔNG BAO GIỜ dời THƯ MỤC: MuMu 6.x gắn Download / Pictures / Movies / Music /
      Screenshots / DCIM/Camera của MỌI máy vào các thư mục con của MuMuSharedFolder — dời thư mục đi là máy khách
      không tải được file (Chrome 0 KB, lỗi 09/11). Thiếu thư mục con nào → tự tạo lại. File mới để yên 30 phút →
      khách tải xong vẫn cài / mở được; khách khác chỉ có thể thấy file mới trong tối đa 30 phút.
    → LDPlayer: mỗi máy 1 thư mục riêng C:\blue\vmdata\<tên máy> (phonectl.py; ăn từ lần bật máy kế tiếp; xoá máy là xoá luôn).
 2) Bộ nhớ copy (clipboard) của Windows — giả lập đồng bộ clipboard máy ảo ↔ Windows: khách A copy → khách B nhận.
    → canh gác cấm tiến trình giả lập đọc / ghi clipboard Windows (job object). Tiến trình nào không cấm được → khoá clipboard
      Windows khi không ai thao tác trên máy chủ (CLIP_LOCK_IDLE giây, mặc định 45) + xoá ngay chữ giả lập vừa đưa ra clipboard.
      Admin đang dùng máy chủ (chuột / phím) → mở khoá ngay, copy-dán bình thường.
MẠNG — máy khách KHÔNG được vào máy chủ / modem / máy khác trong nhà:
 3) Trình phát hình ws-scrcpy (cổng 8000) KHÔNG có mật khẩu và mặc định nghe MỌI địa chỉ → máy khách mở trình duyệt vào
    http://<IP máy chủ>:8000 là điều khiển được MỌI máy (tường lửa Windows không chặn được: kết nối từ giả lập đi qua chính máy chủ).
    → ép ws-scrcpy chỉ nghe 127.0.0.1 (file cb-local.js nạp trước index.js) — khách chỉ đi qua cpapi (kiểm đúng chủ máy).
 4) Máy ảo giả lập (…Headless.exe) gọi được modem / máy khác trong mạng nhà → luật tường lửa CHẶN mọi dải mạng riêng
    (10.x · 172.16–31.x · 192.168.x · 169.254.x), chừa DNS (cổng 53). Internet của khách bình thường.
ĐỒ HOẠ (khách báo load hình chậm): MuMu mặc định TẠM DỪNG app + tự HẠ FPS khi cửa sổ không ở trước (máy cloud luôn ẩn)
    → phonectl perfset: giữ app chạy nền, tắt tự hạ FPS, bắt dùng card rời, tắt VSync · Windows: ưu tiên card rời cho giả lập.
cloudphone.conf: BAOMAT_CLIP=0 (tắt chặn clipboard) · CLIP_LOCK_IDLE=45 · BAOMAT_SHARE=0 (tắt dọn thư mục chia sẻ) · BAOMAT_SHARE_AGE=30 (phút) · BAOMAT_NET=0 (tắt 3 + 4)
Không in tên file / nội dung của khách — báo cáo chỉ có số đếm.
"""
import ctypes, glob, json, os, re, shutil, subprocess, sys, time

VER = "2026-11-09a"
BLUE = os.path.dirname(os.path.abspath(__file__))
RED = os.path.join(BLUE, "redroid")
LOGD = os.path.join(BLUE, "logs")
CACH = os.path.join(BLUE, "cachly")
VMDATA = os.path.join(BLUE, "vmdata")
STATE_F = os.path.join(RED, "baomat.json")
JOB_F = os.path.join(RED, "baomat_job.json")
FW_F = os.path.join(RED, "baomat_fw.json")
STOP_F = os.path.join(RED, "baomat.stop")
LOG_F = os.path.join(LOGD, "baomat.log")
ADB = os.path.join(BLUE, "platform-tools", "adb.exe")
PHONES = os.path.join(RED, "phones.json")
PHONECTL = os.path.join(BLUE, "phonectl.py")
MUTEXES = ("Global\\CloudBlueBaoMat", "Local\\CloudBlueBaoMat")
WIN = os.name == "nt"
NOWIN = 0x08000000 if WIN else 0
os.environ.setdefault("ADB_LOCAL_TRANSPORT_MAX_PORT", "5553")      # như phonectl: adb không tự dò emulator-55xx (LDPlayer hiện trùng máy)


def _conf():
    c = {}
    try:
        with open(os.path.join(BLUE, "cloudphone.conf"), encoding="utf-8-sig") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1); c[k.strip()] = v.strip().strip('"').strip("'")
    except OSError: pass
    return c
CONF = _conf()
def _on(k, d="1"): return str(CONF.get(k, d)).strip().lower() not in ("0", "false", "no", "off")
def _num(k, d):
    try: return float(CONF.get(k, d))
    except (TypeError, ValueError): return float(d)
CLIP_ON = _on("BAOMAT_CLIP")
SHARE_ON = _on("BAOMAT_SHARE")
NET_ON = _on("BAOMAT_NET")
LOCK_IDLE = max(10.0, _num("CLIP_LOCK_IDLE", 45))
SHARE_AGE = max(5.0, _num("BAOMAT_SHARE_AGE", 30))      # phút: file mới hơn mức này để yên cho khách dùng
SWEEP_EVERY = 30                                         # giây giữa 2 lần quét thư mục chia sẻ
MUMU_SUBS = ("Download", "Camera", "Movies", "Music", "Pictures", "Screenshots")   # MuMu gắn vào Android của mọi máy


def log(msg):
    try:
        os.makedirs(LOGD, exist_ok=True)
        if os.path.isfile(LOG_F) and os.path.getsize(LOG_F) > 1_000_000: os.replace(LOG_F, LOG_F + ".1")
        with open(LOG_F, "a", encoding="utf-8") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except OSError: pass

def _run(args, timeout=60):
    """Chạy lệnh, kết quả ra FILE tạm (không dùng pipe: adb server mới bật làm "con" giữ pipe → chờ mãi)."""
    import tempfile
    args = [str(a) for a in args]
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        try: p = subprocess.Popen(args, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, creationflags=NOWIN)
        except OSError as e: return 127, "", str(e)
        try: code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: p.kill()
            except OSError: pass
            code = 124
        fo.seek(0); fe.seek(0)
        return code, fo.read().decode("utf-8", "replace"), fe.read().decode("utf-8", "replace")

def _read_json(f, d=None):
    try:
        with open(f, encoding="utf-8") as fh: return json.load(fh)
    except Exception: return {} if d is None else d
def _write_json(f, d):
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        tmp = f + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh: json.dump(d, fh, ensure_ascii=False)
        os.replace(tmp, f)
    except OSError: pass

def _key(p): return os.path.normcase(os.path.realpath(p))
def _uniq(xs):
    seen, res = set(), []
    for x in xs:
        k = _key(x)
        if k not in seen: seen.add(k); res.append(x)
    return res
def _gb(b): return f"{b / 2**30:.2f}GB" if b >= 2**30 else f"{b / 2**20:.1f}MB"


# ====================================================================== GIẢ LẬP: thư mục cài
def _ld_dir():
    for d in (CONF.get("LD_DIR", ""), r"C:\LDPlayer\LDPlayer9", r"D:\LDPlayer\LDPlayer9", r"C:\Program Files\LDPlayer\LDPlayer9",
              r"C:\leidian\LDPlayer9", r"D:\leidian\LDPlayer9"):
        if d and os.path.isfile(os.path.join(d, "ldconsole.exe")): return d
    return ""
def _mumu_dir():
    c = [CONF.get("MUMU_DIR", "")]
    try:
        with open(os.path.join(RED, "mumu_dir.txt"), encoding="utf-8") as f: c.append(f.read().strip())
    except OSError: pass
    c += [r"C:\Program Files\Netease\MuMuPlayer", r"D:\Program Files\Netease\MuMuPlayer", r"C:\Program Files\Netease\MuMuPlayer-12.0",
          r"D:\Program Files\Netease\MuMuPlayer-12.0", r"C:\Program Files\Netease\MuMu", r"D:\Program Files\Netease\MuMu",
          r"C:\Program Files\Netease\MuMu Player 12", r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0", r"C:\Program Files\MuMuPlayerGlobal-12.0"]
    for d in c:
        if d and os.path.isdir(d) and any(os.path.isfile(os.path.join(d, r)) for r in
                                          (r"nx_main\mumu-cli.exe", r"shell\MuMuManager.exe", r"nx_main\MuMuManager.exe", "MuMuManager.exe")):
            return d
    return ""
def emu_kind():
    e = (CONF.get("EMU") or "").strip().lower()
    if e in ("ld", "mumu", "memu"): return e
    return "mumu" if _mumu_dir() else ("ld" if _ld_dir() else "?")


# ====================================================================== 1) THƯ MỤC CHIA SẺ
SKIP_USERS = {"public", "default", "default user", "all users", "defaultapppool", "wdagutilityaccount"}
LD_DOC = ("xuanzhi9", "xuanzhi", "ldplayer", "ldplayer9", "ldplayer4", "leidian")
LD_SUB = ("pictures", "misc", "applications")
VM_EXT = (".vdi", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".img", ".vbox", ".nvram", ".sav")
PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

def _users():
    root = os.path.join((os.environ.get("SystemDrive") or "C:") + os.sep, "Users")
    try: return [os.path.join(root, u) for u in os.listdir(root) if u.lower() not in SKIP_USERS and os.path.isdir(os.path.join(root, u))]
    except OSError: return []
def _docs_dirs():
    out = []
    for u in _users():
        for sub in ("Documents", os.path.join("OneDrive", "Documents"), os.path.join("OneDrive", "Tài liệu")):
            p = os.path.join(u, sub)
            if os.path.isdir(p): out.append(p)
    if WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                v = str(winreg.QueryValueEx(k, "Personal")[0] or "")
            if v and "%" not in v and os.path.isdir(v): out.append(v)        # Documents chuyển sang ổ khác
        except Exception: pass
    return _uniq(out)
def _is_mumu_share(name):
    n = name.lower()
    return "mumu" in n and ("共享" in name or "share" in n)

LD_KEY_RE = re.compile(r"(?i)^statusSettings\.shared[A-Za-z]+$")     # LDPlayer: statusSettings.sharedPictures / sharedMisc / sharedApplications
def _walk_json(o, out, key=""):
    if isinstance(o, dict):
        for k, v in o.items(): _walk_json(v, out, str(k))
    elif isinstance(o, list):
        for v in o: _walk_json(v, out, key)
    elif isinstance(o, str) and "share" in key.lower() and PATH_RE.match(o):
        out.append((key, os.path.normpath(o)))
def _cfg_share_paths():
    """Thư mục chia sẻ ghi trong file cấu hình giả lập — CHỈ nhận đúng khoá đã biết (chỉ đọc):
       LDPlayer statusSettings.shared* · MuMu: khoá có "share" mà tên thư mục đúng kiểu MuMu共享文件夹."""
    out = []
    ld = _ld_dir()
    for f in (glob.glob(os.path.join(ld, "vms", "config", "*.config")) if ld else []):
        try:
            with open(f, encoding="utf-8-sig", errors="replace") as fh: d = json.load(fh)
        except Exception: continue
        if isinstance(d, dict):
            out += [os.path.normpath(v) for k, v in d.items() if LD_KEY_RE.match(str(k)) and isinstance(v, str) and PATH_RE.match(v)]
    files = []
    roots = [_mumu_dir()] + [os.path.join(u, "AppData", "Roaming", "Netease") for u in _users()]
    for r0 in [r for r in roots if r and os.path.isdir(r)]:
        for root, dirs, fs in os.walk(r0):
            if root[len(r0):].count(os.sep) >= 5: dirs[:] = []
            for f in fs:
                fl = f.lower()
                if fl.endswith(".json") and ("config" in fl or "setting" in fl): files.append(os.path.join(root, f))
            if len(files) > 800: break
    for f in files[:800]:
        try:
            if os.path.getsize(f) > 2_000_000: continue
            with open(f, encoding="utf-8-sig", errors="replace") as fh: j = json.load(fh)
        except Exception: continue
        kv = []; _walk_json(j, kv)
        out += [v for k, v in kv if _is_mumu_share(os.path.basename(v.rstrip("\\/")))]
    vk = _key(VMDATA) + os.sep
    return [p for p in _uniq(out) if not (_key(p) + os.sep).startswith(vk)]     # thư mục RIÊNG từng máy (vmdata) không phải chia sẻ chung

USER_SPECIAL = {"desktop", "documents", "my documents", "downloads", "pictures", "videos", "music", "onedrive", "appdata", "favorites",
                "contacts", "links", "saved games", "searches", "3d objects"}
def _protected():
    return [BLUE, VMDATA, CACH, os.environ.get("SystemRoot") or r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)", r"C:\ProgramData",
            _ld_dir(), _mumu_dir(), r"C:\Program Files\ldplayer9box", r"C:\Program Files\ldplayerbox"]
def _safe_share(p, docs_k):
    """Chỉ dọn thư mục chia sẻ THẬT, luôn nằm TRONG Documents (MuMu共享文件夹 / XuanZhi9/Pictures…). Không bao giờ: ổ đĩa gốc,
       thư mục người dùng, chính Documents / Pictures / Desktop…, thư mục cài giả lập / Windows / CloudBlue — và cả thư mục CHA của chúng."""
    k = _key(p)
    if k.rstrip("\\/").count(os.sep) < 3: return False                     # quá nông: C:\x · C:\Users\x
    for d in _protected():
        if not d: continue
        dk = _key(d)
        if k == dk or k.startswith(dk + os.sep) or dk.startswith(k + os.sep): return False
    root = os.path.join((os.environ.get("SystemDrive") or "C:") + os.sep, "Users")
    for u in [_key(x) for x in _users()] + [_key(os.path.join(root, "Public"))]:
        if k == u: return False
        if k.startswith(u + os.sep) and len(k[len(u) + 1:].split(os.sep)) == 1 and os.path.basename(k).lower() in USER_SPECIAL: return False
    if k in docs_k: return False
    return any(k.startswith(d + os.sep) for d in docs_k)

def share_dirs():
    """[(đường dẫn, loại)] — thư mục chia sẻ CHUNG của giả lập trên máy chủ này."""
    found = []
    docs = _docs_dirs()
    for d in docs:
        try: names = os.listdir(d)
        except OSError: continue
        for n in names:
            p = os.path.join(d, n)
            if not os.path.isdir(p): continue
            if _is_mumu_share(n): found.append((p, "MuMu"))
            elif n.lower() in LD_DOC:
                try: subs = os.listdir(p)
                except OSError: subs = []
                for s_ in subs:
                    q = os.path.join(p, s_)
                    if s_.lower() in LD_SUB and os.path.isdir(q): found.append((q, "LDPlayer"))
    for p in _cfg_share_paths():
        if os.path.isdir(p): found.append((p, "cấu hình"))
    docs_k = {_key(d) for d in docs}
    out, seen = [], set()
    for p, kind in found:
        k = _key(p)
        if k in seen: continue
        seen.add(k)
        if _safe_share(p, docs_k): out.append((p, kind))
        else: log(f"bỏ qua (không an toàn để dọn / không nằm trong Documents): {p}")
    return out

def _tag(p):
    import hashlib
    b = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(p.rstrip("\\/")))[:40].strip("_") or "share"
    return b + "_" + hashlib.md5(_key(p).encode("utf-8")).hexdigest()[:6]
def _stat(path):
    """(số file, số byte)"""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            n = b = 0
            for r, ds, fs in os.walk(path):
                for f in fs:
                    n += 1
                    try: b += os.path.getsize(os.path.join(r, f))
                    except OSError: pass
            return n, b
        return 1, os.path.getsize(path)
    except OSError: return 0, 0

def _cach_root(p):
    """Kho cách ly CÙNG Ổ với thư mục chia sẻ (chỉ đổi tên = tức thì, không bao giờ chép → không đầy ổ, không mất file đang ghi dở)."""
    dr = os.path.splitdrive(os.path.abspath(p))[0].upper()
    if not dr or dr == os.path.splitdrive(os.path.abspath(CACH))[0].upper(): return CACH
    return os.path.join(dr + os.sep, "cloudblue-cachly")
_skip_note = {}
def ensure_skeleton(dirs):
    """Thư mục chia sẻ MuMu: tạo lại thư mục con MuMu gắn vào Android (Download, Pictures…) nếu thiếu. Trả số thư mục vừa tạo."""
    made = 0
    for p, _kind in dirs:
        if not _is_mumu_share(os.path.basename(p.rstrip("\\/"))): continue
        for sub in MUMU_SUBS:
            q = os.path.join(p, sub)
            if os.path.isdir(q): continue
            try: os.makedirs(q, exist_ok=True); made += 1
            except OSError: pass
    if made: log(f"tạo lại {made} thư mục con MuMu (Download / Pictures …) trong thư mục chia sẻ")
    return made

def sweep(dirs, age_min=None):
    """Dời FILE cũ hơn age_min phút (mặc định SHARE_AGE) trong thư mục chia sẻ vào kho cách ly <ổ>/…/cachly/<ngày>/<thư mục>/<đường dẫn con>
       (không xoá). KHÔNG BAO GIỜ dời THƯ MỤC (MuMu gắn các thư mục con vào Android). CHỈ đổi tên — file đang mở / không đổi tên được
       → để lần sau (không chép). Trả (số file, số byte)."""
    nf = nb = 0
    day = time.strftime("%Y%m%d")
    cut = time.time() - (SHARE_AGE if age_min is None else age_min) * 60
    for p, _kind in dirs:
        for root, ds, fs in os.walk(p):
            ds[:] = [d for d in ds if not os.path.islink(os.path.join(root, d))]
            rel = os.path.relpath(root, p)
            for name in fs:
                if name.lower() in ("desktop.ini", "thumbs.db", ".nomedia"): continue
                src = os.path.join(root, name)
                try:
                    stt = os.stat(src)
                    if os.path.islink(src) or max(stt.st_mtime, stt.st_ctime) > cut: continue    # file mới → để khách dùng
                except OSError: continue
                dd = os.path.join(_cach_root(p), day, _tag(p)) if rel == "." else os.path.join(_cach_root(p), day, _tag(p), rel)
                try: os.makedirs(dd, exist_ok=True)
                except OSError: continue
                dst = os.path.join(dd, name); i = 1
                while os.path.exists(dst):
                    dst = os.path.join(dd, f"{time.strftime('%H%M%S')}_{i}_{name}"); i += 1
                try: os.replace(src, dst)
                except OSError as ex:
                    k = (src, day)
                    if k not in _skip_note:
                        _skip_note[k] = 1; log(f"chưa dời được (đang mở / khoá): {os.path.relpath(src, p)} — {ex.__class__.__name__}")
                    continue
                nf += 1; nb += stt.st_size
    if nf: log(f"dời {nf} file cũ hơn {int(SHARE_AGE if age_min is None else age_min)} phút ({_gb(nb)}) từ thư mục chia sẻ vào kho cách ly")
    return nf, nb

KEEP_DAYS = int(_num("BAOMAT_KEEP_DAYS", 3))           # kho cách ly giữ 3 ngày (0 = giữ mãi); ổ còn < 10GB → xoá ngày cũ nhất trước
def cach_trim(dirs):
    """Kho cách ly không được làm đầy ổ (ổ đầy → mọi máy ảo trên máy chủ chết)."""
    roots = {CACH} | {_cach_root(p) for p, _ in dirs}
    today = time.strftime("%Y%m%d")
    for r in roots:
        try: days = sorted(d for d in os.listdir(r) if re.fullmatch(r"\d{8}", d))
        except OSError: continue
        old = []
        if KEEP_DAYS > 0:
            cut = time.strftime("%Y%m%d", time.localtime(time.time() - KEEP_DAYS * 86400))
            old = [d for d in days if d < cut]
        for d in days:
            if d in old or d == today: continue
            try:
                if shutil.disk_usage(r).free < 10 * 2**30: old.append(d)
            except OSError: pass
        for d in old:
            shutil.rmtree(os.path.join(r, d), ignore_errors=True); log(f"xoá kho cách ly cũ {os.path.join(r, d)}")

def ld_share_status():
    """LDPlayer: (số máy đã dùng thư mục riêng, số máy còn dùng chung, tên khoá thấy trong cấu hình)."""
    ld = _ld_dir()
    if not ld: return None
    own = shared = 0; keys = set()
    vk = _key(VMDATA) + os.sep
    for f in glob.glob(os.path.join(ld, "vms", "config", "leidian*.config")):
        if not re.match(r"(?i)^leidian\d+\.config$", os.path.basename(f)): continue      # leidians.config = cài đặt CHUNG, không phải 1 máy
        try:
            with open(f, encoding="utf-8-sig") as fh: d = json.load(fh)
        except Exception: continue
        ks = [k for k, v in d.items() if "shared" in k.lower() and isinstance(v, str)]
        keys.update(ks)
        if ks and all((_key(os.path.normpath(d[k])) + os.sep).startswith(vk) for k in ks): own += 1
        else: shared += 1
    return own, shared, sorted(keys)


# ====================================================================== 2) CLIPBOARD + TIẾN TRÌNH GIẢ LẬP (Windows API)
EMU_RE = re.compile(r"^(mumu|nemu|dnplayer|dnmulti|ldplayer|ld9box|ldvbox|ldbox|ldmulti|memu)", re.I)
EMU_SKIP = re.compile(r"^(mumu-cli|mumumanager|ldconsole|dnconsole|memuc|mumuvmmsvc|.*uninst|.*update|.*crash|.*setup|.*install)", re.I)
def is_emu(exe): return bool(exe) and bool(EMU_RE.match(exe)) and not EMU_SKIP.match(exe)

if WIN:
    import ctypes.wintypes as W
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    def _proto(f, res, *args): f.restype = res; f.argtypes = list(args); return f
    _proto(u32.OpenClipboard, W.BOOL, W.HWND); _proto(u32.CloseClipboard, W.BOOL); _proto(u32.EmptyClipboard, W.BOOL)
    _proto(u32.GetClipboardOwner, W.HWND); _proto(u32.GetClipboardSequenceNumber, W.DWORD)
    _proto(u32.GetWindowThreadProcessId, W.DWORD, W.HWND, ctypes.POINTER(W.DWORD))
    class LASTINPUTINFO(ctypes.Structure): _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]
    _proto(u32.GetLastInputInfo, W.BOOL, ctypes.POINTER(LASTINPUTINFO)); _proto(k32.GetTickCount, W.DWORD)
    _proto(k32.OpenProcess, W.HANDLE, W.DWORD, W.BOOL, W.DWORD); _proto(k32.CloseHandle, W.BOOL, W.HANDLE)
    _proto(k32.CreateJobObjectW, W.HANDLE, ctypes.c_void_p, W.LPCWSTR)
    _proto(k32.SetInformationJobObject, W.BOOL, W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD)
    _proto(k32.AssignProcessToJobObject, W.BOOL, W.HANDLE, W.HANDLE)
    _proto(k32.IsProcessInJob, W.BOOL, W.HANDLE, W.HANDLE, ctypes.POINTER(W.BOOL))
    _proto(k32.CreateToolhelp32Snapshot, W.HANDLE, W.DWORD, W.DWORD)
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", W.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    _proto(k32.Process32FirstW, W.BOOL, W.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    _proto(k32.Process32NextW, W.BOOL, W.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    _proto(k32.GetProcessTimes, W.BOOL, W.HANDLE, *([ctypes.POINTER(W.FILETIME)] * 4))
    _proto(k32.CreateMutexW, W.HANDLE, ctypes.c_void_p, W.BOOL, W.LPCWSTR); _proto(k32.OpenMutexW, W.HANDLE, W.DWORD, W.BOOL, W.LPCWSTR)
    _proto(k32.QueryFullProcessImageNameW, W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))
    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", W.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                  "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
    INVALID_HANDLE = W.HANDLE(-1).value

def procs():
    """{pid: tên file chạy} của mọi tiến trình."""
    out = {}
    if not WIN: return out
    h = k32.CreateToolhelp32Snapshot(0x2, 0)                      # TH32CS_SNAPPROCESS
    if not h or h == INVALID_HANDLE: return out
    try:
        e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(h, ctypes.byref(e))
        while ok:
            out[int(e.th32ProcessID)] = e.szExeFile
            ok = k32.Process32NextW(h, ctypes.byref(e))
    finally: k32.CloseHandle(h)
    return out

def _ctime(h):
    t = [W.FILETIME() for _ in range(4)]
    if k32.GetProcessTimes(h, *[ctypes.byref(x) for x in t]): return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
    return 0

def _pid_ctime(pid):
    h = k32.OpenProcess(0x1000, False, pid)                                  # QUERY_LIMITED_INFORMATION
    if not h: return 0
    try: return _ctime(h)
    finally: k32.CloseHandle(h)

def make_job():
    """Job object CẤM đọc + ghi clipboard. Không giết tiến trình khi đóng; tiến trình con tự thoát job (không ảnh hưởng giả lập quản lý máy)."""
    job = k32.CreateJobObjectW(None, None)
    if not job: log(f"không tạo được job object (lỗi {ctypes.get_last_error()})"); return None
    ext = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    ext.BasicLimitInformation.LimitFlags = 0x00000800 | 0x00001000          # BREAKAWAY_OK | SILENT_BREAKAWAY_OK
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(ext), ctypes.sizeof(ext)):
        log(f"job: không đặt được cho phép tiến trình con thoát (lỗi {ctypes.get_last_error()}) — bỏ chặn bằng job"); k32.CloseHandle(job); return None
    ui = W.DWORD(0x00000002 | 0x00000004)                                     # UILIMIT_READCLIPBOARD | UILIMIT_WRITECLIPBOARD
    if not k32.SetInformationJobObject(job, 4, ctypes.byref(ui), ctypes.sizeof(ui)):
        log(f"job: không đặt được cấm clipboard (lỗi {ctypes.get_last_error()})"); k32.CloseHandle(job); return None
    return job

def restrict(job, pid):
    """→ ("ok" | "job" (đã nằm trong job khác, không cấm được) | "open" (không mở được tiến trình) | "errN", thời điểm tạo tiến trình)"""
    h = k32.OpenProcess(0x0100 | 0x0001 | 0x1000, False, pid)               # SET_QUOTA | TERMINATE (bắt buộc cho Assign) | QUERY_LIMITED
    if not h: return "open", 0
    try:
        ct = _ctime(h)
        inj = W.BOOL(0)
        if k32.IsProcessInJob(h, job, ctypes.byref(inj)) and inj.value: return "ok", ct
        if k32.AssignProcessToJobObject(job, h): return "ok", ct
        err = ctypes.get_last_error()
        inj = W.BOOL(0); k32.IsProcessInJob(h, None, ctypes.byref(inj))
        return ("job" if inj.value else f"err{err}"), ct
    finally: k32.CloseHandle(h)

def idle_s():
    li = LASTINPUTINFO(); li.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not u32.GetLastInputInfo(ctypes.byref(li)): return 0.0
    return ((k32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0

def clip_owner_pid():
    hw = u32.GetClipboardOwner()
    if not hw: return 0
    pid = W.DWORD(0); u32.GetWindowThreadProcessId(hw, ctypes.byref(pid)); return int(pid.value)

def clip_wipe():
    for _ in range(30):
        if u32.OpenClipboard(None):
            try: u32.EmptyClipboard()
            finally: u32.CloseClipboard()
            return True
        time.sleep(0.01)
    return False

def _mutex_exists(name):
    h = k32.OpenMutexW(0x00100000, False, name)                               # SYNCHRONIZE
    if h: k32.CloseHandle(h); return True
    return ctypes.get_last_error() == 5                                     # có nhưng không mở được (canh gác chạy quyền Admin) = có

def guard_alive():
    return WIN and any(_mutex_exists(n) for n in MUTEXES)

def _take_mutex(wait_s=60):
    """Giữ mutex canh gác — CHỈ khi không còn bản nào (Global lẫn Local); chờ bản cũ tắt tối đa wait_s giây. Trả handle hoặc None."""
    t_end = time.time() + wait_s
    while True:
        if not any(_mutex_exists(n) for n in MUTEXES):
            for name in MUTEXES:                                            # Global (mọi phiên Windows); thiếu quyền tạo Global → Local
                h = k32.CreateMutexW(None, False, name); e = ctypes.get_last_error()
                if h and e != 183: return h
                if h: k32.CloseHandle(h); break                             # bản khác vừa giành trước → chờ
        if time.time() > t_end: return None
        time.sleep(1)


# ====================================================================== CANH GÁC (chạy nền)
def guard():
    if not WIN: print("Canh gác chỉ chạy trên Windows."); return
    mtx = _take_mutex(60)
    if not mtx: log("canh gác cũ chưa tắt sau 60 giây — bản này thôi"); return
    try: os.remove(STOP_F)                                                  # lệnh tắt dành cho bản cũ (đã tắt) → bỏ
    except OSError: pass
    log(f"canh gác {VER} bật (pid {os.getpid()}) · clipboard={'BẬT' if CLIP_ON else 'tắt'} · thư mục chia sẻ="
        + (f"BẬT (dời file cũ hơn {int(SHARE_AGE)} phút, không đụng thư mục)" if SHARE_ON else "tắt"))
    job = make_job() if CLIP_ON else None
    known = {int(k): v for k, v in (_read_json(JOB_F) or {}).items() if str(k).isdigit()}   # pid → [thời điểm tạo, trạng thái] (job cũ vẫn còn hiệu lực)
    status = {}                                                             # pid → (tên, trạng thái, thời điểm tạo)
    st = {"ver": VER, "pid": os.getpid(), "started": time.time(), "clip": CLIP_ON, "share": SHARE_ON, "lock_idle": LOCK_IDLE,
          "job": bool(job), "locks": 0, "clears": 0, "writes": {}, "owners": {}, "swept_files": 0, "swept_bytes": 0, "dirs": []}
    locked = False; self_seq = None; seq_seen = u32.GetClipboardSequenceNumber()
    t_scan = t_dirs = t_sweep = t_state = t_trim = t_net = 0.0; dirs = []; names = {}
    while True:
        now = time.time()
        if os.path.exists(STOP_F): break
        try:
            if now - t_scan >= 5:                                           # tiến trình giả lập mới → cấm clipboard
                t_scan = now; names = procs(); live = {}
                for pid, exe in names.items():
                    if not is_emu(exe): continue
                    prev = status.get(pid)
                    if prev and prev[0] == exe and prev[1] in ("ok", "ok-cu") and prev[2] and _pid_ctime(pid) == prev[2]:
                        live[pid] = prev; continue                          # đúng tiến trình cũ (pid có thể bị dùng lại → so thời điểm tạo)
                    if job is None: live[pid] = (exe, "tat", 0); continue
                    s_, ct = restrict(job, pid)
                    if s_ == "job" and ct and known.get(pid, [0, ""])[0] == ct and known[pid][1] in ("ok", "ok-cu"): s_ = "ok-cu"
                    if s_ in ("ok", "ok-cu"): known[pid] = [ct, s_]
                    if not prev or prev[1] != s_: log(f"{exe} (pid {pid}): {s_}")
                    live[pid] = (exe, s_, ct)
                status = live
                known = {p: v for p, v in known.items() if p in status}
                _write_json(JOB_F, {str(p): v for p, v in known.items()})
            if SHARE_ON and now - t_dirs >= 600:
                t_dirs = now; dirs = share_dirs(); st["dirs"] = [p for p, _ in dirs]
            if SHARE_ON and dirs and now - t_sweep >= SWEEP_EVERY:
                t_sweep = now; ensure_skeleton(dirs)
                nf, nb = sweep(dirs); st["swept_files"] += nf; st["swept_bytes"] += nb
            if SHARE_ON and now - t_trim >= 3600:
                t_trim = now; cach_trim(dirs)
            if NET_ON and now - t_net >= 600:                               # ws-scrcpy chỉ nghe 127.0.0.1 + tường lửa chặn máy ảo vào mạng nhà
                t_net = now; st["net"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in net_protect().items()}
            if CLIP_ON:
                loose = [x for x in status.values() if x[1] not in ("ok", "ok-cu")]     # tiến trình giả lập CHƯA cấm được
                want = bool(loose) and idle_s() >= LOCK_IDLE
                if want and not locked:
                    if u32.OpenClipboard(None):                              # giữ clipboard Windows → không tiến trình nào đọc / ghi được
                        u32.EmptyClipboard(); locked = True; st["locks"] += 1
                        self_seq = seq_seen = u32.GetClipboardSequenceNumber()
                elif not want and locked:
                    u32.CloseClipboard(); locked = False
                if not locked:
                    seq = u32.GetClipboardSequenceNumber()
                    if seq != seq_seen:
                        if seq != self_seq:
                            pid = clip_owner_pid(); exe = names.get(pid) or procs().get(pid, "") if pid else ""
                            if is_emu(exe) or (not pid and loose):          # giả lập vừa đưa chữ của máy khách ra clipboard Windows → xoá ngay
                                if clip_wipe():                             # xoá không được (đang bị giữ) → lần sau (100ms) thử lại
                                    self_seq = seq_seen = u32.GetClipboardSequenceNumber()
                                    st["clears"] += 1; w = exe or "?"; st["writes"][w] = st["writes"].get(w, 0) + 1
                            else:
                                seq_seen = seq; o = exe or "(không rõ)"; st["owners"][o] = st["owners"].get(o, 0) + 1   # chỉ đếm tên chương trình
                        else: seq_seen = seq
            if now - t_state >= 10:
                t_state = now
                agg = {}
                for exe, s_, _ct in status.values():
                    a = agg.setdefault(exe, {}); a[s_] = a.get(s_, 0) + 1
                st.update(t=now, locked=locked, emu=agg, idle=round(idle_s()) if CLIP_ON else None)
                _write_json(STATE_F, st)
        except Exception as e:
            log(f"lỗi canh gác: {e!r}"); time.sleep(1)
        time.sleep(0.1 if CLIP_ON else 1.0)
    if locked:
        try: u32.CloseClipboard()
        except Exception: pass
    log("canh gác tắt")

def start_guard(force=False):
    """Bật canh gác chạy nền (pythonw, tách khỏi tiến trình gọi). Đang có bản cũ (hoặc force) → ra lệnh tắt bản cũ;
       bản mới tự chờ bản cũ tắt (≤60 giây) rồi chạy và tự xoá lệnh tắt."""
    if not WIN: return "chỉ chạy trên Windows"
    if guard_alive():
        if not force and (_read_json(STATE_F) or {}).get("ver") == VER: return "đang chạy"
        os.makedirs(RED, exist_ok=True); open(STOP_F, "w").close()
        msg = "đang thay bản mới (bản cũ tắt trong ≤60 giây)"
    else:
        try: os.remove(STOP_F)
        except OSError: pass
        msg = "đã bật"
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(exe): exe = sys.executable
    for fl in (0x00000008 | 0x00000200 | 0x01000000, 0x00000008 | 0x00000200):   # DETACHED | NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB
        try:
            subprocess.Popen([exe, os.path.abspath(__file__), "guard"], cwd=BLUE, creationflags=fl, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return msg
        except OSError: continue
    return "không bật được"


# ====================================================================== MẠNG: máy khách KHÔNG vào được máy chủ / mạng nhà
WS_DIST = os.path.join(BLUE, "ws-scrcpy", "dist")
WS_PORT = 8000
WS_MARK = b'/*cloudblue-local*/require("./cb-local.js");'
WS_SHIM_JS = r"""// CloudBlue (baomat.py): trình phát hình ws-scrcpy CHỈ nghe 127.0.0.1 — máy khách (giả lập) / máy khác trong mạng KHÔNG vào thẳng được
// (ws-scrcpy không có mật khẩu: vào được là điều khiển MỌI máy). Khách chỉ đi qua cpapi (cổng 8010, kiểm đúng chủ máy).
"use strict";
const net = require("net");
const LOCAL = "127.0.0.1", ANY = new Set(["", "0.0.0.0", "::", "0:0:0:0:0:0:0:0"]);
const listen0 = net.Server.prototype.listen;
if (!listen0.__cloudblue) {
  const f = function (...a) {
    try {
      if (typeof a[0] === "number" || (typeof a[0] === "string" && /^\d+$/.test(a[0]))) {
        if (typeof a[1] !== "string") a.splice(1, 0, LOCAL);
        else if (ANY.has(a[1])) a[1] = LOCAL;
      } else if (a[0] && typeof a[0] === "object" && !Array.isArray(a[0]) && a[0].path == null && a[0].handle == null && a[0].fd == null && a[0]._handle == null) {
        if (a[0].host == null || ANY.has(a[0].host)) a[0] = Object.assign({}, a[0], { host: LOCAL });
      }
    } catch (e) {}
    return listen0.apply(this, a);
  };
  f.__cloudblue = true;
  net.Server.prototype.listen = f;
}
"""

def _atomic_write(path, data):
    tmp = path + ".cbtmp"
    with open(tmp, "wb") as f: f.write(data)
    os.replace(tmp, path)

def ws_patch(dist=None):
    """ws-scrcpy chỉ nghe 127.0.0.1: ghi cb-local.js + chèn 1 dòng nạp nó ở ĐẦU index.js (giữ dòng #! / BOM / "use strict").
       → "ok" (đã có) | "moi" (vừa sửa — ăn khi ws-scrcpy bật lại) | "khong-co" (máy này không có ws-scrcpy) | "loi: …" """
    dist = dist or WS_DIST
    js = os.path.join(dist, "index.js")
    if not os.path.isfile(js): return "khong-co"
    try:
        shim = os.path.join(dist, "cb-local.js"); want = WS_SHIM_JS.encode("utf-8")
        try:
            with open(shim, "rb") as f: cur = f.read()
        except OSError: cur = None
        if cur != want: _atomic_write(shim, want)
        with open(js, "rb") as f: data = f.read()
        if WS_MARK in data[:8192]: return "ok"
        head, rest = b"", data
        if rest.startswith(b"\xef\xbb\xbf"): head, rest = rest[:3], rest[3:]
        if rest.startswith(b"#!"):
            nl = rest.find(b"\n"); cut = len(rest) if nl < 0 else nl + 1
            head, rest = head + rest[:cut] + (b"" if nl >= 0 else b"\n"), rest[cut:]
        m = re.match(rb"""\s*(["'])use strict\1\s*;?[ \t]*\r?\n?""", rest)
        if m: head, rest = head + rest[:m.end()] + (b"" if rest[:m.end()].endswith(b"\n") else b"\n"), rest[m.end():]
        _atomic_write(js, head + WS_MARK + b"\n" + rest)
        log("ws-scrcpy: đã ép chỉ nghe 127.0.0.1 (cb-local.js)")
        return "moi"
    except OSError as e:
        log(f"ws-scrcpy: không sửa được index.js: {e!r}"); return f"loi: {e.__class__.__name__}"

def _is_loop(host): return host in ("::1", "localhost") or host.startswith("127.")
def _ipv4(s): return bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", s or "")) and all(int(x) < 256 for x in s.split("."))
def _private(ip):
    if not _ipv4(ip): return False
    a, b = (int(x) for x in ip.split(".")[:2])
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)

def listeners(ports):
    """{cổng: [(địa chỉ đang nghe, pid)]} — đọc netstat -ano (nhận LISTEN qua địa chỉ xa 0.0.0.0:0 / [::]:0 → không phụ thuộc ngôn ngữ Windows)."""
    out = {int(p): [] for p in ports if p}
    if not WIN or not out: return out
    for proto in ("TCP", "TCPv6"):
        _c, txt, _e = _run(["netstat", "-ano", "-p", proto], 40)
        for ln in txt.splitlines():
            q = ln.split()
            if len(q) < 4 or q[0].upper() not in ("TCP", "TCPV6") or q[2] not in ("0.0.0.0:0", "[::]:0", "*:*"): continue
            host, _, port = q[1].rpartition(":")
            if not port.isdigit() or int(port) not in out: continue
            pid = int(q[-1]) if q[-1].isdigit() else 0
            item = (host.strip("[]"), pid)
            if item not in out[int(port)]: out[int(port)].append(item)
    return out

def ws_restart_if_open():
    """ws-scrcpy còn nghe ra ngoài (0.0.0.0 / ::) → tắt tiến trình node đó; bảng CloudBlue / keep.bat tự bật lại (bản đã ép 127.0.0.1).
       → số tiến trình đã tắt"""
    bad = {pid for host, pid in listeners([WS_PORT]).get(WS_PORT, []) if pid and not _is_loop(host)}
    if not bad: return 0
    names = procs(); n = 0
    for pid in sorted(bad):
        if (names.get(pid) or "").lower() != "node.exe": log(f"cổng {WS_PORT} mở ra ngoài nhưng không phải node (pid {pid}: {names.get(pid)}) — không tắt"); continue
        c, _o, _e = _run(["taskkill", "/PID", str(pid), "/F"], 30)
        if c == 0: n += 1; log(f"ws-scrcpy (pid {pid}) đang nghe ra ngoài → tắt để bật lại bản chỉ nghe 127.0.0.1")
    return n

# Tường lửa: máy ảo giả lập (…Headless.exe — tiến trình mở kết nối mạng THAY máy khách) KHÔNG được gọi vào mạng nhà.
LAN_NETS = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,169.254.0.0/16"
LAN_PORTS = "1-52,54-65535"                                                  # chừa DNS (53): máy chủ hay dùng modem làm DNS
FW_PREFIX = "CloudBlue-chanLAN"
FW_SIG = "v1|" + LAN_NETS + "|" + LAN_PORTS
HEADLESS_RE = re.compile(r"(?i)^(mumu|nemu|ld|memu|vbox)[^\\/]*headless[^\\/]*\.exe$")

def _exe_path(pid):
    if not WIN: return ""
    h = k32.OpenProcess(0x1000, False, pid)                                   # QUERY_LIMITED_INFORMATION
    if not h: return ""
    try:
        buf = ctypes.create_unicode_buffer(1024); n = W.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally: k32.CloseHandle(h)

def vmm_exes():
    """Đường dẫn file chạy MÁY ẢO của giả lập: đang chạy (đường dẫn thật) + tìm trong thư mục cài."""
    found = []
    for pid, exe in procs().items():
        if HEADLESS_RE.match(exe or ""):
            p = _exe_path(pid)
            if p: found.append(p)
    for d in (_mumu_dir(), _ld_dir(), r"C:\Program Files\ldplayer9box", r"C:\Program Files\ldplayerbox", r"C:\Program Files\Microvirt\MEmuHyperv"):
        if not d or not os.path.isdir(d): continue
        for root, dirs, files in os.walk(d):
            if root[len(d):].count(os.sep) >= 4: dirs[:] = []
            found += [os.path.join(root, f) for f in files if HEADLESS_RE.match(f)]
    return _uniq(found)

def _fw_name(path, proto):
    import hashlib
    b = re.sub(r"[^A-Za-z0-9]+", "", os.path.splitext(os.path.basename(path))[0])[:28] or "vmm"
    return f"{FW_PREFIX}-{proto}-{b}-" + hashlib.md5((_key(path) + "|" + FW_SIG).encode("utf-8")).hexdigest()[:6]

def _fw_has(name):
    c, _o, _e = _run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"], 30)
    return c == 0

def fw_apply(force=False):
    """Đặt luật tường lửa CHẶN máy ảo giả lập gọi vào mạng nhà (chừa DNS). force: xoá + đặt lại.
       Luật của file máy ảo lần này không thấy (giả lập đang tắt) nhưng file vẫn còn → GIỮ. → (số file máy ảo, số luật vừa đặt, lỗi cuối)"""
    if not WIN: return 0, 0, ""
    rec = _read_json(FW_F, {}) or {}
    if rec.get("disabled") and not force: return 0, 0, "tạm tắt (lần trước máy khách mất internet khi chặn — chạy baomat.py để thử lại)"
    exes = vmm_exes()
    want = {}
    for p in exes:
        for proto in ("TCP", "UDP"): want[_fw_name(p, proto)] = (p, proto)
    had = {str(n): tuple(v) for n, v in (rec.get("rules") or {}).items()
           if str(n).startswith(FW_PREFIX + "-") and isinstance(v, list) and len(v) == 2}
    keep = {}
    for nm, (p, proto) in had.items():
        if nm in want: continue
        if os.path.isfile(p) and _fw_name(p, proto) == nm: keep[nm] = (p, proto); continue
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], 30)     # file đã gỡ / luật đời cũ → xoá
    added, err = 0, ""
    for nm, (p, proto) in want.items():
        if not force and _fw_has(nm): continue
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], 30)
        c, o, e = _run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={nm}", "dir=out", "action=block", f"program={p}",
                        "enable=yes", "profile=any", f"protocol={proto}", f"remoteip={LAN_NETS}", f"remoteport={LAN_PORTS}"], 30)
        if c == 0: added += 1
        else: err = ((o or "") + (e or "")).strip()[-200:] or f"mã {c}"; log(f"không đặt được luật tường lửa {nm}: {err}")
    _write_json(FW_F, {"rules": {n: list(v) for n, v in {**keep, **want}.items()}, "t": time.time()})
    if added: log(f"tường lửa: đặt {added} luật chặn máy ảo gọi vào mạng nhà ({len(exes)} file)")
    return len(exes), added, err

def fw_remove(why=""):
    """Gỡ MỌI luật chặn đã đặt + tạm tắt phần chặn (canh gác không đặt lại) tới lần chạy baomat.py kế tiếp. → số luật đã gỡ"""
    rec = _read_json(FW_F, {}) or {}
    names = [str(n) for n in (rec.get("rules") or {}) if str(n).startswith(FW_PREFIX + "-")]
    for nm in names: _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], 30)
    _write_json(FW_F, {"rules": {}, "disabled": time.time(), "why": why})
    log(f"tường lửa: GỠ {len(names)} luật chặn mạng nhà — {why}")
    return len(names)

def guest_inet(port):
    """Máy khách ra được internet không: (theo IP 1.1.1.1:443, theo tên miền dns.google:443 — cần DNS)."""
    o = ashell(port, "T(){ timeout 5 toybox nc -w 3 \"$1\" \"$2\" </dev/null >/dev/null 2>&1; r=$?; "
                     "if [ $r -eq 0 ] || [ $r -eq 124 ]; then echo \"MO $1:$2\"; fi; }; T 1.1.1.1 443 & T dns.google 443 & wait", 40)
    return "MO 1.1.1.1:443" in o, "MO dns.google:443" in o

def fw_off_profiles():
    """Hồ sơ tường lửa Windows đang TẮT (Domain / Private / Public) — tắt thì luật chặn không có tác dụng."""
    if not WIN: return []
    _c, o, _e = _run(["powershell", "-NoProfile", "-Command",
                      "Get-NetFirewallProfile | Where-Object { -not $_.Enabled } | ForEach-Object { $_.Name }"], 60)
    return [x.strip() for x in o.splitlines() if x.strip()]

def host_net():
    """(IPv4 mạng nhà của máy chủ, IP modem) — đọc bảng định tuyến (route print), không phụ thuộc ngôn ngữ Windows."""
    ips, gw = [], ""
    if WIN:
        _c, o, _e = _run(["route", "print", "-4"], 30)
        for ln in o.splitlines():
            q = ln.split()
            if len(q) >= 5 and q[0] == "0.0.0.0" and q[1] == "0.0.0.0" and _ipv4(q[2]) and _ipv4(q[3]):
                gw = gw or q[2]
                if q[3] not in ips: ips.append(q[3])
    try:
        import socket
        for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if ai[4][0] not in ips: ips.append(ai[4][0])
    except Exception: pass
    return [ip for ip in ips if _private(ip)][:4], (gw if _private(gw) else "")

def net_protect(force=False):
    """Bảo vệ mạng (canh gác chạy mỗi 10 phút, baomat.py chạy ngay): ws-scrcpy chỉ nghe 127.0.0.1 + luật tường lửa.
       → dict kết quả cho báo cáo"""
    r = {"ws": ws_patch(), "ws_killed": 0, "fw": (0, 0, "")}
    if r["ws"] in ("ok", "moi"): r["ws_killed"] = ws_restart_if_open()
    try: r["fw"] = fw_apply(force)
    except Exception as e: r["fw"] = (0, 0, repr(e)); log(f"tường lửa: lỗi {e!r}")
    return r


# ====================================================================== 3) ĐỒ HOẠ
def gpu_prefs():
    """Windows: ưu tiên card rời (High performance) cho mọi file chạy của giả lập. → (số file, số file vừa đặt)"""
    if not WIN: return 0, 0
    exes = []
    for d in (_mumu_dir(), _ld_dir(), r"C:\Program Files\ldplayer9box", r"C:\Program Files\ldplayerbox", r"C:\Program Files\LDPlayer"):
        if not d or not os.path.isdir(d): continue
        for root, dirs, files in os.walk(d):
            if root[len(d):].count(os.sep) >= 4: dirs[:] = []
            exes += [os.path.join(root, f) for f in files if f.lower().endswith(".exe") and is_emu(f)]
    exes = _uniq(exes); n = 0
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\DirectX\UserGpuPreferences") as k:
            for e in exes:
                try: cur = winreg.QueryValueEx(k, e)[0]
                except OSError: cur = None
                if cur != "GpuPreference=2;": winreg.SetValueEx(k, e, 0, winreg.REG_SZ, "GpuPreference=2;"); n += 1
    except Exception as ex: log(f"không đặt được ưu tiên card rời: {ex!r}")
    return len(exes), n

def nvsmi():
    exe = shutil.which("nvidia-smi") or next((f for f in (r"C:\Windows\System32\nvidia-smi.exe",
                                                           r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe") if os.path.isfile(f)), "")
    if not exe: return None
    _c, out, _e = _run([exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,driver_version", "--format=csv,noheader,nounits"], 30)
    gpus = [ln.strip() for ln in out.splitlines() if ln.strip() and "," in ln]
    _c, full, _e = _run([exe], 30)
    used = {}
    for ln in full.splitlines():
        m = re.search(r"([^\s\\/|]+\.exe)", ln, re.I)
        x = m.group(1).lstrip(".") if m else ""                                   # nvidia-smi cắt đường dẫn dài thành "...Tên.exe"
        if is_emu(x): used[x] = used.get(x, 0) + 1
    return gpus, used

def video_cards():
    if not WIN: return []
    _c, out, _e = _run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' | driver ' + $_.DriverVersion + ' | ' + $_.Status }"], 60)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


# ====================================================================== 4) TRONG MÁY KHÁCH (adb, chỉ đọc)
def running_vms():
    """[(tên, cổng)] máy khách đang nối adb."""
    _c, out, _e = _run([ADB, "devices"], 30)
    ports = set()
    for ln in out.splitlines()[1:]:
        q = ln.split()
        if len(q) >= 2 and q[1] == "device" and q[0].startswith("127.0.0.1:"):
            try: ports.add(int(q[0].split(":")[1]))
            except ValueError: pass
    ph = (_read_json(PHONES) or {}).get("phones", [])
    return [(p["name"], int(p["port"])) for p in ph if str(p.get("name", "")).startswith("cp_") and int(p.get("port") or 0) in ports]

def ashell(port, script, timeout=40):
    return _run([ADB, "-s", f"127.0.0.1:{port}", "shell", script], timeout)[1]

def guest_net(port, other, hips=(), lan_gw=""):
    """Máy khách có gọi được dịch vụ của MÁY CHỦ / máy khách KHÁC / modem không: qua cổng mạng ảo (10.0.2.2 = máy chủ ở giả lập
       VirtualBox), qua IP mạng nhà của máy chủ (hips), và trang quản trị modem (lan_gw cổng 80 / 443)."""
    sp = int(_num("STREAM_PORT", 8189))
    plist = [8000, 8010, 8020, sp, 5037, port] + ([other] if other else [])
    hosts = " ".join(["$GW", "10.0.2.2"] + [h for h in hips if _ipv4(h)])
    sh = ("T(){ timeout 3 toybox nc -w 2 \"$1\" \"$2\" </dev/null >/dev/null 2>&1; r=$?; "
          "if [ $r -eq 0 ] || [ $r -eq 124 ]; then echo \"MO $1:$2\"; else echo \"dong $1:$2\"; fi; }; "
          "GW=$(ip route get 1.1.1.1 2>/dev/null | grep -m1 -o 'via [0-9.]*' | cut -d' ' -f2); case \"$GW\" in *.*.*.*) ;; *) GW=10.0.2.2;; esac; "
          "echo \"GW=$GW\"; AP=$(getprop service.adb.tcp.port); case \"$AP\" in ''|-1|0) AP=5555;; esac; T 127.0.0.1 $AP; "
          f"for h in $(echo \"{hosts}\" | tr ' ' '\\n' | sort -u); do for p in {' '.join(str(x) for x in plist)}; do T $h $p & done; done; "
          + (f"for p in 80 443; do T {lan_gw} $p & done; " if _ipv4(lan_gw) else "") + "wait")
    return ashell(port, sh, 90)

def net_verdict(lines, port, other, hips, lan_gw, sp):
    """Phân loại kết quả guest_net → (thử được?, NGHIÊM TRỌNG, cần chặn, bình thường)"""
    selfok = any(ln.startswith("MO 127.0.0.1:") for ln in lines)
    crit, warn, fine = [], [], []
    for hp in sorted({ln[3:] for ln in lines if ln.startswith("MO ") and not ln.startswith("MO 127.0.0.1:")}):
        h, _, p = hp.rpartition(":"); p = int(p) if p.isdigit() else 0
        if lan_gw and h == lan_gw and p in (80, 443): warn.append(hp + " (modem)")
        elif p == sp and h in hips: fine.append(hp)                           # cổng phát hình công khai (có mật khẩu) — bình thường
        elif p in (WS_PORT, 5037, port) or (other and p == other): crit.append(hp)
        else: warn.append(hp)
    return selfok, crit, warn, fine

def guest_mounts(port):
    return ashell(port, "grep -i -E 'vboxsf|9p|virtiofs|nemu|share|xuanzhi|mumu' /proc/mounts | cut -d' ' -f2,3 | head -8")

def ld_probe(name, port):
    """LDPlayer: máy này có THẬT SỰ dùng thư mục riêng vmdata\\<tên>\\Pictures không (thả 1 file dò rồi xem trong Android)."""
    d = os.path.join(VMDATA, str(name).lower(), "Pictures")
    if not os.path.isdir(d): return None
    f = os.path.join(d, ".cb_probe")
    try:
        with open(f, "w") as fh: fh.write("cloudblue")
    except OSError: return None
    try:
        out = ashell(port, "for d in /sdcard/Pictures /mnt/shared/Pictures /storage/emulated/0/Pictures; do ls -a $d 2>/dev/null; done | grep -c cb_probe").strip()
        return (int(out) > 0) if out.isdigit() else None
    finally:
        try: os.remove(f)
        except OSError: pass


def guest_gles(port):
    o = ashell(port, "dumpsys SurfaceFlinger 2>/dev/null | grep -m1 -i 'GLES:'")
    return o.strip().replace("GLES:", "").strip()[:110]


# ====================================================================== LỆNH
def phonectl(*args, timeout=600):
    return _run([sys.executable, PHONECTL] + list(args), timeout)

def cmd_check():
    t0 = time.time()
    node = CONF.get("NODE_ID") or os.environ.get("COMPUTERNAME", "?")
    kind = emu_kind()
    print(f"===== CloudBlue BẢO MẬT + ĐỒ HOẠ {VER} · máy chủ {node} · giả lập {kind} =====", flush=True)
    if WIN:
        try: admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception: admin = False
        if not admin: print("⚠ PowerShell CHƯA có quyền Admin → mở lại PowerShell bằng 'Run as administrator' rồi chạy lại lệnh.")

    # ---- 1) thư mục chia sẻ
    print("\n[1] THƯ MỤC CHIA SẺ của giả lập (mọi máy khách thấy chung):", flush=True)
    dirs = share_dirs() if SHARE_ON else []
    if not SHARE_ON: print("   (đang tắt: BAOMAT_SHARE=0)")
    for p, k in dirs:
        n, b = _stat(p); print(f"   • {k}: {p} — đang có {n} file ({_gb(b)})")
    if SHARE_ON and not dirs: print("   ✓ không thấy thư mục chia sẻ nào có thể dọn")
    mk = ensure_skeleton(dirs) if dirs else 0
    if mk: print(f"   → tạo lại {mk} thư mục con MuMu (Download / Pictures …) — thiếu thì máy khách không tải được file")
    nf, nb = sweep(dirs) if dirs else (0, 0)
    if nf: print(f"   → đã dời {nf} file cũ hơn {int(SHARE_AGE)} phút ({_gb(nb)}) vào kho cách ly {CACH} (KHÔNG xoá — khách không còn thấy)")
    ls = ld_share_status()
    if ls:
        own, shr, keys = ls
        print(f"   LDPlayer: {own} máy đã có thư mục riêng · {shr} máy còn dùng chung (tự đổi sang riêng ở lần bật máy kế tiếp)")
        print(f"   khoá cấu hình thấy: {', '.join(keys) if keys else 'KHÔNG THẤY khoá thư mục chia sẻ nào (đã ghi khoá mặc định)'}")

    # ---- 2) canh gác clipboard + thư mục
    print(f"\n[2] CANH GÁC (clipboard riêng từng máy + dọn file cũ hơn {int(SHARE_AGE)} phút trong thư mục chia sẻ, mỗi 30 giây):", flush=True)
    r = start_guard(force=True); print(f"   canh gác: {r}", flush=True)
    st = {}
    for _ in range(150):
        time.sleep(0.5); st = _read_json(STATE_F) or {}
        if st.get("ver") == VER and st.get("t", 0) >= t0: break
    if st.get("ver") == VER and st.get("t", 0) >= t0:
        if not st.get("clip"): print("   clipboard: KHÔNG chặn (BAOMAT_CLIP=0)")
        else:
            emu = st.get("emu") or {}
            if not emu: print("   chưa thấy tiến trình giả lập nào đang chạy")
            for exe, c in sorted(emu.items()):
                print(f"   • {exe}: " + " · ".join(f"{ {'ok': 'đã cấm clipboard', 'ok-cu': 'đã cấm (lần trước)', 'job': 'KHÔNG cấm được (đã ở job khác)', 'open': 'không mở được (thiếu quyền Admin?)', 'tat': 'không có job'}.get(s, s)} ×{n}" for s, n in c.items()))
            loose = sum(n for c in emu.values() for s, n in c.items() if s not in ("ok", "ok-cu"))
            print("   → clipboard Windows: " + ("ĐÃ CÁCH LY hoàn toàn (giả lập không đọc / ghi được)" if emu and not loose else
                  f"còn {loose} tiến trình chưa cấm được → KHOÁ clipboard khi không ai dùng máy chủ quá {LOCK_IDLE:g} giây + xoá ngay chữ giả lập đưa ra"))
            if not st.get("job"): print("   ⚠ không tạo được job cấm clipboard — xem logs\\baomat.log")
    else: print("   ⚠ canh gác chưa báo trạng thái — xem C:\\blue\\logs\\baomat.log")

    # ---- 3) đồ hoạ
    print("\n[3] ĐỒ HOẠ (load hình chậm):", flush=True)
    if kind == "mumu":
        _c, out, err = phonectl("perfset", timeout=900)
        line = next((ln for ln in out.splitlines() if ln.startswith("PERFSET")), (out or err).strip()[-200:])
        bad = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("✗")]
        for ln in bad[:3]: print("   " + ln)
        if len(bad) > 3: print(f"   … và {len(bad) - 3} máy nữa chưa ghi được")
        print("   MuMu (giữ app chạy nền · tắt tự hạ FPS · bắt dùng card rời · tắt VSync): " + line.replace("PERFSET ", ""))
    n_exe, n_set = gpu_prefs()
    print(f"   Windows ưu tiên card rời cho {n_exe} file chạy của giả lập ({n_set} file vừa đặt — ăn từ lần bật máy kế tiếp)")
    vc = video_cards()
    for v in vc: print(f"   card: {v}")
    if any("basic display" in v.lower() for v in vc): print("   ⚠ có 'Microsoft Basic Display Adapter' = card CHƯA cài driver → máy vẽ bằng CPU (rất chậm): cài driver NVIDIA")
    ns = nvsmi()
    if ns is None: print("   (không có nvidia-smi)")
    else:
        gpus, used = ns
        for g in gpus: print(f"   NVIDIA: {g}  (tên, % dùng, MB đã dùng, MB tổng, driver)")
        print("   tiến trình giả lập ĐANG DÙNG card NVIDIA: " + (", ".join(f"{k}×{v}" for k, v in used.items()) if used else
              "KHÔNG THẤY → giả lập có thể đang vẽ bằng card khác / bằng CPU"))

    # ---- 4) mạng: máy khách không vào được máy chủ / modem / máy khác trong nhà
    print("\n[4] MẠNG — máy khách KHÔNG được vào máy chủ / modem / máy khác trong nhà:", flush=True)
    sp = int(_num("STREAM_PORT", 8189))
    hips, lan_gw = host_net()
    vms = running_vms()
    probe = vms[0][1] if vms else 0
    before = guest_inet(probe) if (NET_ON and probe) else None
    if NET_ON:
        r = net_protect(force=True)
        print("   trình phát hình ws-scrcpy (8000): " + {"ok": "chỉ nghe 127.0.0.1 ✓ (đã ép từ trước)", "moi": "VỪA ép chỉ nghe 127.0.0.1",
              "khong-co": "máy này không có ws-scrcpy"}.get(r["ws"], "⚠ " + r["ws"] + " — xem logs\\baomat.log"))
        if r["ws_killed"]:
            print("   → đã tắt bản ws-scrcpy cũ đang nghe ra ngoài — bảng CloudBlue tự bật lại bản mới (≤30 giây)…", flush=True)
            for _ in range(45):
                time.sleep(2)
                if listeners([WS_PORT]).get(WS_PORT): break
        nexe, added, err = r["fw"]
        print(f"   tường lửa: chặn {nexe} file máy ảo giả lập gọi vào mạng nhà (10.x · 172.16–31.x · 192.168.x · 169.254.x, chừa DNS) — "
              + (f"đặt {added} luật ✓" if not err else f"⚠ LỖI: {err}"))
        if not nexe: print("   ⚠ không tìm thấy file máy ảo (…Headless.exe) — giả lập cài ở chỗ lạ? Gửi Claude dòng này.")
        off = fw_off_profiles()
        if off: print(f"   ⚠ Tường lửa Windows đang TẮT ở: {', '.join(off)} → luật chặn KHÔNG có tác dụng. Bật lại: Windows Security → Firewall & network protection → bật cả 3.")
        if before is not None:                                              # tự kiểm: chặn mạng nhà KHÔNG được làm khách mất internet
            after = guest_inet(probe)
            if any(before) and not any(after):
                n = fw_remove("máy khách mất internet sau khi chặn")
                print(f"   ⛔ sau khi chặn, máy khách MẤT internet → đã GỠ {n} luật (phần chặn mạng nhà tạm tắt) — GỬI CLAUDE NGAY")
            else:
                print("   internet trong máy khách: " + ("bình thường ✓" if all(after) else "theo IP được, theo tên miền KHÔNG (DNS lỗi?)" if after[0] else
                      "không kiểm được (máy thiếu lệnh nc / máy chưa có mạng từ trước — không phải do luật)" if not any(before) else "một phần"))
    else: print("   (đang tắt: BAOMAT_NET=0)")
    ph_ports = sorted({int(p.get("port") or 0) for p in (_read_json(PHONES) or {}).get("phones", []) if int(p.get("port") or 0) > 0})
    la = listeners([WS_PORT, 8010, 8020, 5037, sp] + ph_ports)
    out_ = lambda p: sorted({h for h, _pid in la.get(p, []) if not _is_loop(h)})
    bad_adb = [p for p in ph_ports if out_(p)]
    for p, nm, sev in ((WS_PORT, "ws-scrcpy", "⛔"), (5037, "adb máy chủ", "⛔"), (8010, "cpapi", "⚠"), (8020, "phát hình (WebSocket)", "⚠")):
        o = out_(p)
        if o: print(f"   {sev} cổng {p} ({nm}) đang nghe ra NGOÀI ({', '.join(o)}) — chỉ được nghe 127.0.0.1")
    if bad_adb: print(f"   ⛔ cổng adb của {len(bad_adb)} máy khách đang nghe ra NGOÀI (VD {bad_adb[0]}: {', '.join(out_(bad_adb[0]))}) — GỬI CLAUDE NGAY")
    if not any(out_(p) for p in (WS_PORT, 5037, 8010, 8020)) and not bad_adb:
        print(f"   ✓ ws-scrcpy / adb / cpapi / máy khách chỉ nghe 127.0.0.1 (cổng phát hình {sp} mở ra ngoài là đúng — có mật khẩu)")
    print(f"   IP mạng nhà của máy chủ: {', '.join(hips) or '?'} · modem: {lan_gw or '?'}")

    # ---- 5) trong máy khách
    print(f"\n[5] KIỂM TRA TRONG MÁY KHÁCH (chỉ đọc, {len(vms)} máy đang nối):", flush=True)
    for i, (nm, port) in enumerate(vms[:2]):
        other = next((p for n2, p in vms if p != port), 0)
        g = guest_gles(port)
        print(f"   {nm}: card Android thấy = {g or '?'}")
        mt = [ln.strip() for ln in guest_mounts(port).splitlines() if ln.strip()]
        print(f"   {nm}: ổ chia sẻ gắn trong máy = " + ("; ".join(mt) if mt else "không thấy"))
        if kind == "ld":
            pr = ld_probe(nm, port)
            print(f"   {nm}: thư mục riêng (vmdata) " + ("ĐANG DÙNG ✓" if pr else "chưa dùng (máy chưa khởi động lại sau khi cập nhật)" if pr is False else "chưa có"))
        if i == 0:
            net = [ln.strip() for ln in guest_net(port, other, hips, lan_gw).splitlines() if ln.strip()]
            gw = next((ln for ln in net if ln.startswith("GW=")), "GW=?")
            selfok, crit, warn, fine = net_verdict(net, port, other, hips, lan_gw, sp)
            if not selfok: print(f"   mạng trong máy ({gw}): không thử được (máy thiếu lệnh nc)")
            else:
                print(f"   mạng trong máy ({gw}): " + ("không gọi được máy chủ / modem ✓" if not (crit or warn) else "xem dưới")
                      + (f" · cổng phát hình công khai {', '.join(fine)} (đúng)" if fine else ""))
                if crit: print(f"   ⛔ NGHIÊM TRỌNG: máy khách gọi được {', '.join(crit)} (8000 = ws-scrcpy, 5037 = adb máy chủ, "
                               f"{port} = adb máy này, {other or '-'} = adb máy khác) — GỬI CLAUDE NGAY")
                if warn: print(f"   ⚠ máy khách còn gọi được {', '.join(warn)} — chưa chặn hết (tường lửa tắt? / giả lập lạ) — gửi Claude")

    # ---- 5) máy mẫu
    if kind == "mumu":
        _c, out, _e = phonectl("strays", timeout=300)
        tl = [ln.strip() for ln in out.splitlines() if "máy mẫu" in ln]
        print("\n[6] MÁY MẪU (máy khách mới được nhân bản từ đây — phải SẠCH, chưa từng dùng):")
        for ln in tl: print("   " + ln)
        if not tl: print("   (không thấy máy mẫu)")
    print(f"\n===== xong sau {time.time() - t0:.0f} giây · nhật ký: {LOG_F} =====")
    print("→ Copy TOÀN BỘ phần trên (từ dòng ===== đầu) gửi Claude.")

def cmd_khoidonglai():
    """MuMu: khởi động lại lần lượt máy khách đang chạy để ăn cài đặt đồ hoạ (mỗi máy ~1 phút mất kết nối)."""
    _c, out, _e = phonectl("list", timeout=300)
    names = [ln.split()[0] for ln in out.splitlines() if ln.strip().endswith("chạy") and ln.split()[0].startswith("cp_")]
    print(f"Khởi động lại {len(names)} máy khách đang chạy (lần lượt từng máy)…", flush=True)
    for i, nm in enumerate(names, 1):
        c, o, e = phonectl("restart", nm, timeout=600)
        print(f"  [{i}/{len(names)}] {nm}: " + ((o or e).strip().splitlines() or ["?"])[-1], flush=True)
        time.sleep(15)
    print("Xong.")

def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if cmd == "guard": guard()
    elif cmd == "start": print("canh gác:", start_guard())
    elif cmd == "tatgac":                                                   # tắt tới lần bật cloudphoned / chạy baomat kế tiếp
        os.makedirs(RED, exist_ok=True); open(STOP_F, "w").close()
        for _ in range(300):
            if not guard_alive(): break
            time.sleep(0.2)
        print("Đã tắt canh gác." if not guard_alive() else "Canh gác đang tắt (xong trong ít giây).")
    elif cmd == "khoidonglai": cmd_khoidonglai()
    else: cmd_check()

if __name__ == "__main__":
    main()
