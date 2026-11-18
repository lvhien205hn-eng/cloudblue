# -*- coding: utf-8 -*-
# =====================================================================
#  bonho.py — BỘ NHỚ (ổ dữ liệu) của từng máy ảo trên máy chủ này · bản 18/11b
#   python bonho.py         ← CHỈ ĐỌC: mỗi máy tổng / trống của /data trong Android (máy đang chạy), cỡ ổ ảo, cài đặt ổ của giả lập.
#                              Không sửa, không tắt / bật, không xoá gì → chạy lúc nào cũng được, máy khách không bị gián đoạn.
#   python bonho.py --json  ← như trên + 1 dòng JSON cuối (gửi hỗ trợ)
#   python bonho.py --thu 12[,15] [--giu]   ← MuMu: THỬ cách nới ổ trên 1 MÁY THỬ nhân bản từ máy mẫu (tên cbtest_disk12…, KHÔNG phải
#                              máy khách): ghi dấu → tắt "chế độ ổ nhỏ" (mini_disk) → bật lại → ổ có lớn lên + dấu còn nguyên không.
#                              Xong tắt + xoá ĐÚNG máy thử đó (--giu: để lại máy thử). Máy khách không bị đụng tới.
# =====================================================================
import json, os, re, struct, sys, time
HOME = os.environ.get("BLUE_HOME") or os.path.dirname(os.path.abspath(__file__))
os.environ["BLUE_HOME"] = HOME
if HOME not in sys.path: sys.path.insert(0, HOME)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import phonectl as P

VER = "18/11b"
GB = float(1 << 30)
WANT_GB = 20
# khoá cài đặt "về ổ": tên có disk / storage / capacity / expand / mini / fsAutoSize… hoặc có "size" mà không phải cửa sổ / màn hình / RAM.
# Bỏ khoá chứa đường dẫn (path / folder / dir / share) để không in đường dẫn trên máy chủ.
_KEY = re.compile(r"disk|storage|capac|expand|mini|fsauto|fs_auto|mulfs|sdcard|datasize|data_size|vdi|vmdk|rom_size|userdata", re.I)
_SKIP = re.compile(r"resolution|window|font|dpi|bright|frame|keymap|shortcut|mouse|memory|mem_|_mem|cpu|path|folder|dir|share|record|video|audio|icon|title", re.I)
def disk_key(k):
    k = str(k)
    if _SKIP.search(k): return False
    return bool(_KEY.search(k)) or "size" in k.lower()

def gb(x):
    try:
        x = float(x)
        return f"{x / GB:.1f}G" if x >= GB / 2 else f"{x / (1 << 20):.0f}M"
    except (TypeError, ValueError): return "?"

def vdi_cap(f):
    """Dung lượng KHAI BÁO của 1 file ổ ảo .vdi (VirtualBox) — đọc phần đầu file; không đọc được → None."""
    try:
        with open(f, "rb") as fh: h = fh.read(0x188)
        if len(h) >= 0x178 and struct.unpack_from("<I", h, 0x40)[0] == 0xBEDA107F and struct.unpack_from("<I", h, 0x44)[0] >= 0x00010001:
            return struct.unpack_from("<Q", h, 0x170)[0]
    except (OSError, struct.error): pass
    return None
def vmdk_cap(f):
    """Dung lượng khai báo của 1 file .vmdk (đầu file KDMV hoặc file mô tả "RW <số sector>")."""
    try:
        with open(f, "rb") as fh: h = fh.read(8192)
        if h[:4] == b"KDMV": return struct.unpack_from("<Q", h, 12)[0] * 512
        t = h.decode("latin-1")
        if "DescriptorFile" in t:
            secs = [int(x) for x in re.findall(r"(?m)^\s*R[WD]\s+(\d+)\s", t)]
            if secs: return sum(secs) * 512
    except (OSError, struct.error, ValueError): pass
    return None
def img_info(d):
    """[(tên file, dung lượng khai báo, cỡ file thật)] các ổ ảo trong thư mục máy d."""
    out = []
    try: names = sorted(os.listdir(d))
    except OSError: return out
    for n in names:
        f = os.path.join(d, n); low = n.lower()
        if not os.path.isfile(f) or not low.endswith((".vdi", ".vmdk")): continue
        try: sz = os.path.getsize(f)
        except OSError: sz = None
        out.append((n, vdi_cap(f) if low.endswith(".vdi") else vmdk_cap(f), sz))
    return out

def df_rows(txt):
    """Kết quả `df -k` trong Android → [(nơi gắn, tổng, đã dùng, trống)] (byte), theo thứ tự in ra."""
    out = []; carry = []
    for ln in (txt or "").splitlines():
        t = ln.split()
        if not t or t[0].lower() == "filesystem": continue
        t = carry + t
        if len(t) < 6: carry = t; continue
        carry = []
        try: out.append((t[-1], int(t[1]) * 1024, int(t[2]) * 1024, int(t[3]) * 1024))
        except ValueError: continue
    return out
def parse_df(txt): return {m: (a, b, c) for m, a, b, c in df_rows(txt)}
def sh(port, cmd, t=40):
    try:
        r = P.adb("-s", f"127.0.0.1:{port}", "shell", cmd, timeout=t)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e: return f"(adb lỗi: {e})"
DF_CMD = "df -k /data 2>&1; echo @@; df -k /storage/emulated/0 2>&1; echo @@; df -k /sdcard 2>&1"
def df2(port):
    """((tổng, dùng, trống) của ổ chứa /data, của bộ nhớ trong) — mỗi đường dẫn lấy dòng ĐẦU của `df -k <đường dẫn>`, và chữ df in ra."""
    o = sh(port, DF_CMD, 30)
    parts = (o.split("@@") + ["", "", ""])[:3]
    rs = [df_rows(x) for x in parts]
    pick = lambda r: tuple(r[0][1:]) if r else None
    return pick(rs[0]), pick(rs[1]) or pick(rs[2]), o
DF_RAW = []                      # chữ df của máy đầu tiên không đọc được /data (in 1 lần để biết vì sao)
def android_df(port):
    """(tổng, đã dùng, trống) của /data + của bộ nhớ trong nếu nằm ổ khác — máy phải đang chạy và adb nối được."""
    try:
        if not P._adb_fresh(port) and not P._adb_fresh(port): return None, None
        data, sd, raw = df2(port)
    except Exception: return None, None
    if data is None and not DF_RAW: DF_RAW.append(" | ".join(x.strip() for x in raw.splitlines() if x.strip())[:300])
    if sd and data and abs(sd[0] - data[0]) < (64 << 20): sd = None          # cùng 1 ổ (Android 11+: bộ nhớ trong nằm trên /data)
    return data, sd

def file_ver(path):
    """Số phiên bản của 1 file .exe (Windows) — không đọc được → ""."""
    try:
        import ctypes
        v = ctypes.windll.version; n = v.GetFileVersionInfoSizeW(path, None)
        if not n: return ""
        buf = ctypes.create_string_buffer(n)
        if not v.GetFileVersionInfoW(path, 0, n, buf): return ""
        p = ctypes.c_void_p(); ln = ctypes.c_uint()
        if not v.VerQueryValueW(buf, "\\", ctypes.byref(p), ctypes.byref(ln)): return ""
        ms, ls = struct.unpack_from("<II", ctypes.string_at(p.value, 52), 8)
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception: return ""

def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from flat(v, f"{pre}.{k}" if pre else str(k))
    elif not isinstance(o, list): yield pre, o
def cfg_keys(files):
    """Khoá về ổ trong các file cấu hình JSON của giả lập (bỏ giá trị là đường dẫn)."""
    out = {}
    for f in files:
        try: j = json.load(open(f, encoding="utf-8-sig"))
        except Exception: continue
        for k, v in flat(j):
            if disk_key(k) and not (isinstance(v, str) and re.match(r"^[A-Za-z]:[\\/]|^/|\\\\", v)): out[f"{os.path.basename(f)}:{k}"] = v
    return out
def host_free(d):
    try:
        import shutil
        u = shutil.disk_usage(d); return f"ổ chứa máy ảo: trống {u.free / GB:.0f}G / {u.total / GB:.0f}G"
    except Exception: return ""
def short(v, n=60):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"
def help_lines(args, n=12):
    """Dòng hướng dẫn của lệnh giả lập có nhắc tới ổ / dung lượng (chỉ đọc)."""
    try:
        r = P.run(args, 20); t = (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception: return []
    return [ln.strip()[:150] for ln in t.splitlines() if re.search(r"disk|mini|size|expand|capac|磁盘|扩容", ln, re.I)][:n]

def rows_mumu(info):
    out = []
    for i in sorted(info):
        v = info[i]; name = str(v.get("name", "")); a = str(v.get("android_version") or "?").split(".")[0]
        on = bool(P._mumu_running(v)); up = bool(v.get("is_android_started"))
        allk = P._mumu_all(i)
        keys = {k: allk[k] for k in sorted(allk) if disk_key(k)} if isinstance(allk, dict) else {}
        d = P._vm_dir(i); imgs = img_info(d) if d else []
        data = sd = None
        if on and up:
            try: port = int(v.get("adb_port"))
            except (TypeError, ValueError): port = 16384 + 32 * int(i)
            data, sd = android_df(port)
        out.append({"i": i, "name": name, "android": a, "on": on, "up": up, "data": data, "sd": sd, "imgs": imgs, "keys": keys,
                    "used_host": v.get("disk_size_bytes")})
    return out

def rows_ld():
    out = []
    L = P._ldlist()
    for i in sorted(L):
        x = L[i]
        try: cfg = json.load(open(P._ld_cfgfile(i), encoding="utf-8-sig"))
        except Exception: cfg = {}
        keys = {k: cfg[k] for k in sorted(cfg) if disk_key(k)} if isinstance(cfg, dict) else {}
        d = os.path.join(P.LD, "vms", f"leidian{int(i)}")
        data = sd = None
        if x.get("running"): data, sd = android_df(5555 + 2 * int(i))
        out.append({"i": i, "name": x.get("name", ""), "android": "9", "on": bool(x.get("running")), "up": data is not None,
                    "data": data, "sd": sd, "imgs": img_info(d), "keys": keys})
    return out

def line(r):
    s = f"#{r['i']} {r['name'][:22]} · A{r['android']} · " + ("chạy" if r["on"] else "tắt")
    if r["data"]: s += f" · /data {gb(r['data'][0])} (trống {gb(r['data'][2])})"
    elif r["on"]: s += " · /data ? (adb chưa nối / Android chưa lên)"
    if r["sd"]: s += f" · bộ nhớ trong {gb(r['sd'][0])} (trống {gb(r['sd'][2])})"
    for n, cap, sz in r["imgs"]:
        if re.search(r"data|sdcard", n, re.I): s += f" · {n} {gb(cap) if cap else '?'}" + (f" (file {gb(sz)})" if sz is not None else "")
    if r["keys"]: s += " · " + " ".join(f"{k.split('.')[-1] if len(k) > 30 else k}={short(v, 24)}" for k, v in r["keys"].items())
    return s

# ---------------- THỬ cách nới ổ trên 1 MÁY THỬ (MuMu) — không bao giờ đụng máy khách ----------------
TEST_NAME = "cbtest_disk{}"
INFO_CMD = ("echo uid=$(id -u) se=$(getenforce 2>/dev/null); mount | grep -E ' /data | /data/media | /storage/emulated ' | head -4; "
            "cat /proc/partitions 2>/dev/null | tail -n +3 | head -12; getprop | grep -i -E 'mini|disk|datasize|data_size|userdata|resize' | head -10; "
            "ls /system/bin/resize2fs /system/bin/resize.f2fs 2>&1 | head -2")
def _cap(t):
    return gb(t[0]) + f" (trống {gb(t[2])})" if t else "?"
T_POLL = float(os.environ.get("BONHO_POLL", "5"))          # giây giữa 2 lần xem máy thử đã lên chưa (chỉ đổi khi chạy thử nghiệm)
T_LIVE = float(os.environ.get("BONHO_T2", "30"))           # giây chờ sau khi đổi chế độ ổ lúc máy đang chạy
T_BOOT = float(os.environ.get("BONHO_BOOT", "420"))        # giây tối đa chờ máy thử lên
def _wait_up(idx, limit=None):
    """Chờ máy số idx lên hẳn Android → (cổng adb, số giây) · không lên → (None, số giây)."""
    t0 = time.time(); limit = limit or T_BOOT
    while time.time() - t0 < limit:
        time.sleep(T_POLL)
        try: port = P.port_of(idx)
        except Exception: port = 16384 + 32 * int(idx)
        try:
            if port and P._adb_fresh(port) and P.booted(port): return port, int(time.time() - t0)
        except Exception: pass
    return None, int(time.time() - t0)
def _dump(port, tag):
    o = sh(port, INFO_CMD, 40)
    for ln in [x.strip() for x in o.splitlines() if x.strip()][:24]: print(f"      [{tag}] {ln[:170]}")
    return o
def _data_dev(info):
    """(thiết bị, kiểu ổ) của /data theo dòng mount — không thấy → (None, None)."""
    for ln in info.splitlines():
        t = ln.split()
        if len(t) >= 3 and " /data " in f" {ln} ":
            if "on" in t and t.index("on") + 1 < len(t) and t[t.index("on") + 1] == "/data":
                k = t.index("on"); return t[0], (t[k + 3] if len(t) > k + 3 and t[k + 2] == "type" else None)
            if t[1] == "/data": return t[0], t[2]
    return None, None
def _marks_ok(port, mark):
    o = sh(port, "cat /data/local/tmp/cb_disk_marker /sdcard/cb_disk_marker.txt 2>&1", 20)
    return o.count(mark) >= 2, o.replace("\n", " | ")[:160]

def thu_one(ver, keep=False):
    name = TEST_NAME.format(ver)
    print(f"\n== THỬ NỚI Ổ — Android {ver} · máy thử '{name}' (nhân bản {P.tpl_name(ver)}, KHÔNG phải máy khách) · bonho {VER}", flush=True)
    if ver not in P.ANDROIDS: print(f"   máy chủ này không bán Android {ver} (ANDROIDS={','.join(P.ANDROIDS)}) — bỏ qua"); return "BO"
    L = P._mumu_stable()
    if not L: print("   ✗ không đọc được danh sách máy MuMu — dừng"); return "LOI"
    if not any(x["name"] == P.tpl_name(ver) for x in L.values()): print(f"   ✗ không có máy mẫu {P.tpl_name(ver)} — dừng"); return "LOI"
    old = [i for i, x in L.items() if x["name"] == name]
    if old:
        idx = old[0]; print(f"   dùng lại máy thử còn từ lần trước: #{idx}", flush=True)
    else:
        print("   tạo máy thử (nhân bản máy mẫu, 1–5 phút)…", flush=True)
        r = P.memuc("create", ver, timeout=900)
        m = re.search(r"index\D*(\d+)", r.stdout or "")
        if r.returncode not in (0, None) or not m:
            print("   ✗ không tạo được máy thử: " + ((r.stderr or "") + " " + (r.stdout or "")).strip()[-220:]); return "LOI"
        idx = int(m.group(1))
        P.memuc("rename", "-i", idx, name, timeout=120)
        if (P._mumu_list().get(idx) or {}).get("name") != name:
            cur = str((P._mumu_list().get(idx) or {}).get("name", ""))
            if cur and not cur.startswith(("cp_", "spare_")) and cur != P.tpl_name(ver): P.memuc("remove", "-i", idx, timeout=300)
            print(f"   ✗ đổi tên máy thử #{idx} không được — dừng"); return "LOI"
    try:
        k0 = P._mumu_all(idx).get("mini_disk")
        print(f"   máy thử #{idx} · mini_disk={k0} (máy mẫu {P.tpl_name(ver)}: {P._mumu_all(next(i for i, x in L.items() if x['name'] == P.tpl_name(ver))).get('mini_disk')})", flush=True)
        # Bước 1: bật như máy khách mới → ghi dấu + đo ổ
        P.memuc("start", "-i", idx, timeout=180)
        port, sec = _wait_up(idx)
        if not port: print(f"   ✗ bước 1: máy thử không lên sau {sec} giây — dừng"); return "LOI"
        mark = f"cb{int(time.time())}"
        sh(port, f"echo {mark} > /data/local/tmp/cb_disk_marker; echo {mark} > /sdcard/cb_disk_marker.txt; sync", 20)
        d1, s1, _ = df2(port)
        print(f"   1) bật lần 1 ({sec} giây): /data {_cap(d1)} · bộ nhớ trong {_cap(s1)} · ghi dấu: {'ok' if _marks_ok(port, mark)[0] else 'LỖI'}", flush=True)
        _dump(port, "1")
        # Bước 2: tắt chế độ ổ nhỏ LÚC MÁY ĐANG CHẠY → xem MuMu có nới ngay không
        r = P._mumu_locked(lambda: P._mumurun(["setting", "-v", str(idx), "-k", "mini_disk", "-val", "false"], 60))
        ans = " ".join(((r.stdout or "") + " " + (r.stderr or "")).split())[:120]
        k2 = P._mumu_all(idx).get("mini_disk")
        time.sleep(T_LIVE)
        d2, s2, _ = df2(port)
        print(f"   2) đặt mini_disk=false lúc đang chạy → MuMu trả: {ans or '(trống)'} · đọc lại: {k2} · {T_LIVE:.0f} giây sau: /data {_cap(d2)} · bộ nhớ trong {_cap(s2)}", flush=True)
        live = bool(d2 and d2[0] >= (WANT_GB - 1) * GB)
        # Bước 3: tắt máy (đặt lại khi tắt nếu lúc chạy không ghi được) → bật lại
        P.memuc("stop", "-i", idx, timeout=120)
        for _ in range(30):
            if not (P._mumu_list().get(idx) or {}).get("running"): break
            time.sleep(2)
        if str(P._mumu_all(idx).get("mini_disk")).lower() != "false":
            P._mumu_locked(lambda: P._mumurun(["setting", "-v", str(idx), "-k", "mini_disk", "-val", "false"], 60))
            print(f"   3) lúc chạy không ghi được → ghi lúc máy tắt, đọc lại: {P._mumu_all(idx).get('mini_disk')}", flush=True)
        P.memuc("start", "-i", idx, timeout=180)
        port, sec = _wait_up(idx)
        if not port: print(f"   ✗ bước 3: máy thử KHÔNG LÊN sau khi tắt chế độ ổ nhỏ ({sec} giây)"); return "KHONG_LEN"
        d3, s3, _ = df2(port); ok3, m3 = _marks_ok(port, mark)
        print(f"   3) bật lại ({sec} giây): /data {_cap(d3)} · bộ nhớ trong {_cap(s3)} · dấu: {'CÒN NGUYÊN' if ok3 else 'MẤT — ' + m3}", flush=True)
        info3 = _dump(port, "3")
        if not ok3: return "MAT_DU_LIEU"
        if d3 and d3[0] >= (WANT_GB - 1) * GB: return "LIVE" if live else "A"
        # Bước 4: ổ vẫn nhỏ → thử nới hệ thống tệp ngay trong Android (chỉ máy thử; cần root + ext4 + thiết bị lớn hơn)
        dev, fs = _data_dev(info3)
        uid0 = "uid=0" in info3
        size_dev = None
        if dev:
            try: size_dev = int(sh(port, f"cat /sys/class/block/{os.path.basename(dev)}/size", 15).split()[0]) * 512
            except (ValueError, IndexError): size_dev = None
        print(f"   4) /data trên {dev or '?'} · kiểu {fs or '?'} · thiết bị {gb(size_dev) if size_dev else '?'} · root={'có' if uid0 else 'không'}", flush=True)
        if not (dev and fs == "ext4" and uid0 and size_dev and size_dev >= WANT_GB * GB): return "C"
        o = sh(port, f"resize2fs {dev} 2>&1 | tail -3", 900)
        d4, _, _ = df2(port)
        print(f"   4) resize2fs: {' | '.join(o.splitlines())[:200]} → /data {_cap(d4)}", flush=True)
        if not (d4 and d4[0] >= (WANT_GB - 1) * GB): return "C"
        P.memuc("stop", "-i", idx, timeout=120); time.sleep(5)
        P.memuc("start", "-i", idx, timeout=180)
        port, sec = _wait_up(idx)
        if not port: print(f"   ✗ bước 4: máy thử KHÔNG LÊN sau khi nới ({sec} giây)"); return "KHONG_LEN"
        d5, _, _ = df2(port); ok5, m5 = _marks_ok(port, mark)
        print(f"   4) bật lại sau nới: /data {_cap(d5)} · dấu: {'CÒN NGUYÊN' if ok5 else 'MẤT — ' + m5}", flush=True)
        if not ok5: return "MAT_DU_LIEU"
        return "B" if d5 and d5[0] >= (WANT_GB - 1) * GB else "C"
    finally:
        if keep: print(f"   (--giu: để lại máy thử #{idx} '{name}' — xoá tay trong MuMu khi xong)", flush=True)
        else:
            try:
                P.memuc("stop", "-i", idx, timeout=120)
                for _ in range(30):
                    if not (P._mumu_list().get(idx) or {}).get("running"): break
                    time.sleep(2)
                cur = (P._mumu_list().get(idx) or {}).get("name")
                if cur == name:
                    r = P.memuc("remove", "-i", idx, timeout=300)
                    print(f"   dọn: {'đã xoá máy thử #' + str(idx) if idx not in P._mumu_list() else '✗ chưa xoá được máy thử #' + str(idx) + ' — xoá tay trong MuMu'}", flush=True)
                else: print(f"   dọn: máy #{idx} giờ tên '{cur}' (không phải máy thử) → KHÔNG xoá", flush=True)
            except Exception as e: print(f"   dọn lỗi: {e!r}"[:200], flush=True)

KQ_TXT = {"A": "tắt chế độ ổ nhỏ (mini_disk=false) lúc máy TẮT rồi bật lại là ổ lớn, dữ liệu còn nguyên",
          "LIVE": "tắt chế độ ổ nhỏ lúc máy đang chạy là ổ lớn NGAY, dữ liệu còn nguyên",
          "B": "phải tắt chế độ ổ nhỏ + nới hệ thống tệp trong Android (resize2fs), dữ liệu còn nguyên",
          "C": "chưa nới được bằng cách tự động (dữ liệu còn nguyên)", "MAT_DU_LIEU": "⚠ ĐỔI CHẾ ĐỘ LÀM MẤT DỮ LIỆU — không dùng cách này",
          "KHONG_LEN": "⚠ máy thử không lên sau khi đổi — không dùng cách này", "LOI": "không thử được", "BO": "bỏ qua"}
def thu(vers, keep=False):
    if P.EMU != "mumu": print("--thu chỉ dùng cho máy chủ MuMu."); return 2
    pb = P._priv_block()
    if pb: print("❌ " + pb); return 2
    try:
        import shutil
        free = shutil.disk_usage(os.path.join(P.MUMU, "vms")).free / GB
    except Exception: free = 99.0
    if free < 15: print(f"Ổ máy chủ chỉ còn {free:.0f}GB trống — không thử."); return 2
    t0 = time.time(); out = []
    for v in vers:
        try: k = thu_one(v, keep)
        except Exception as e: print(f"   ✗ lỗi: {e!r}"[:240], flush=True); k = "LOI"
        out.append((v, k))
    print("\nKẾT QUẢ THỬ: " + " · ".join(f"Android {v}: {k} — {KQ_TXT.get(k, k)}" for v, k in out) + f" · {time.time() - t0:.0f} giây", flush=True)
    return 0 if all(k in ("A", "LIVE", "B") for _, k in out) else 1


def main():
    if "--thu" in sys.argv:
        k = sys.argv.index("--thu"); arg = sys.argv[k + 1] if k + 1 < len(sys.argv) else ""
        vers = [x.strip() for x in arg.split(",") if x.strip().isdigit()]
        if not vers: print("Cách dùng: python bonho.py --thu 12   (hoặc 12,15)"); return 2
        return thu(vers, keep="--giu" in sys.argv)
    as_json = "--json" in sys.argv
    t0 = time.time()
    print(f"== BỘ NHỚ MÁY ẢO — {P.CONF.get('NODE_ID', '?')} · {P.EMU_NAME} · bonho {VER} · chỉ đọc", flush=True)
    extra = {}
    if P.EMU == "mumu":
        if not P.MUMU_CLI: print("Không thấy MuMu (MuMuManager / mumu-cli) — dừng."); return 2
        root = P.MUMU or ""
        vers = {n: file_ver(os.path.join(root, *n.split("/"))) for n in ("shell/MuMuPlayer.exe", "nx_main/MuMuNxMain.exe", "nx_main/MuMuManager.exe", "shell/MuMuManager.exe")}
        print("MuMu bản: " + (", ".join(f"{k.split('/')[-1]} {v}" for k, v in vers.items() if v) or "?"), flush=True)
        print(host_free(os.path.join(root, "vms")), flush=True)
        info = P._mumu_info()
        if not info: print("Không đọc được danh sách máy MuMu (MuMuManager info) — thử lại sau."); return 2
        rows = rows_mumu(info)
        # mặc định cho máy MỚI + thuộc tính các khoá ổ (ghi được không / giá trị cho phép) của 1 máy
        g = P._mumu_json(P._mumurun(["setting", "-a"], 60).stdout) or {}
        extra["default"] = {k: g[k] for k in sorted(g) if disk_key(k)} if isinstance(g, dict) else {}
        pick = next((r["i"] for r in rows if r["name"].startswith("cp_")), None)
        if pick is None and rows: pick = rows[0]["i"]
        if pick is not None:
            allk = P._mumu_all(pick)
            if isinstance(allk, dict): extra["names"] = sorted(allk)
            raw = P._mumurun(["setting", "-v", str(pick), "-i"], 60).stdout or ""
            j = P._mumu_json(raw)
            if isinstance(j, dict) and j:
                sub = {k: j[k] for k in j if disk_key(k)}
                if not sub and isinstance(j.get("data") or j.get("settings"), dict):
                    jj = j.get("data") or j.get("settings"); sub = {k: jj[k] for k in jj if disk_key(k)}
                extra["info"] = {"vm": pick, "keys": sub}
            else:
                extra["info"] = {"vm": pick, "lines": [ln.strip()[:200] for ln in raw.splitlines() if _KEY.search(ln)][:30]}
        # chỉ hỏi hướng dẫn (KHÔNG gọi "create" dù kèm -h: bản MuMu không hiểu -h có thể tạo máy thật)
        extra["help"] = help_lines([P.MUMU_CLI, "--help"]) + help_lines([P.MUMU_CLI, "setting", "-h"])
        d = P._vm_dir(pick) if pick is not None else None
        if d: extra["cfg"] = cfg_keys([os.path.join(d, "configs", n) for n in ("vm_config.json", "customer_config.json", "extra_config.json")]
                                 + [os.path.join(root, "configs", "main", "vm_config.json")])
    elif P.EMU == "ld":
        if not P.LD: print("Không thấy LDPlayer (ldconsole.exe) — dừng."); return 2
        print("LDPlayer bản: " + (file_ver(os.path.join(P.LD, "dnplayer.exe")) or "?") + " · " + host_free(os.path.join(P.LD, "vms")), flush=True)
        rows = rows_ld()
        try: extra["names"] = sorted(json.load(open(P._ld_cfgfile(next((r["i"] for r in rows if str(r["name"]).startswith("cp_")), 0)), encoding="utf-8-sig")))
        except Exception: pass
        try: g = json.load(open(os.path.join(P.LD, "vms", "config", "leidians.config"), encoding="utf-8-sig"))
        except Exception: g = {}
        extra["default"] = {k: g[k] for k in sorted(g) if disk_key(k)} if isinstance(g, dict) else {}
        extra["help"] = help_lines([os.path.join(P.LD, "ldconsole.exe")], 20)
    else:
        print(f"Giả lập {P.EMU_NAME}: bonho chưa hỗ trợ."); return 2

    for r in rows: print("  " + line(r), flush=True)
    if extra.get("default"): print("Mặc định cho máy MỚI: " + " ".join(f"{k}={short(v, 30)}" for k, v in extra["default"].items()))
    inf = extra.get("info")
    if inf:
        print(f"Thuộc tính khoá ổ (máy #{inf['vm']}):")
        for k, v in (inf.get("keys") or {}).items(): print(f"   {k}: {short(v, 300)}")
        for ln in inf.get("lines") or []: print("   " + ln)
        if not inf.get("keys") and not inf.get("lines"): print("   (MuMu không trả khoá nào về ổ)")
    for ln in extra.get("help") or []: print("   hướng dẫn: " + ln)
    if DF_RAW: print("df /data (máy đầu tiên không đọc được): " + DF_RAW[0])
    if extra.get("names"): print(f"Tên mọi khoá cài đặt ({len(extra['names'])}): " + " ".join(extra["names"]))
    if extra.get("cfg"): print("File cấu hình (máy #%s): " % (inf or {}).get("vm", "?") + " ".join(f"{k}={short(v, 30)}" for k, v in list(extra["cfg"].items())[:30]))

    cust = [r for r in rows if str(r["name"]).startswith(("cp_", "spare_"))]
    known = [r for r in cust if r["data"]]
    small = [r for r in known if r["data"][0] < (WANT_GB - 0.5) * GB]
    mini = [r for r in rows if str(r["keys"].get("mini_disk", "")).lower() == "true"]
    print(f"TÓM TẮT: {len(rows)} máy ảo · máy khách/dựng sẵn {len(cust)} · đọc được /data {len(known)} · /data dưới {WANT_GB}GB: {len(small)}"
          + (f" (nhỏ nhất {gb(min(r['data'][0] for r in small))})" if small else "")
          + (f" · mini_disk=true: {len(mini)} máy" if P.EMU == "mumu" else "")
          + f" · {time.time() - t0:.0f} giây", flush=True)
    if as_json:
        print("JSON " + json.dumps({"ver": VER, "node": P.CONF.get("NODE_ID"), "emu": P.EMU, "rows": rows, **extra}, ensure_ascii=False, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
