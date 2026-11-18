# -*- coding: utf-8 -*-
# =====================================================================
#  bonho.py — xem BỘ NHỚ (ổ dữ liệu) của từng máy ảo trên máy chủ này · bản 18/11a · CHỈ ĐỌC
#   Không sửa, không tắt / bật, không xoá gì → chạy lúc nào cũng được, máy khách không bị gián đoạn.
#   python bonho.py         ← mỗi máy: tổng / trống của /data trong Android (máy đang chạy), cỡ ổ ảo, cài đặt ổ của giả lập
#   python bonho.py --json  ← thêm 1 dòng JSON cuối (gửi hỗ trợ)
# =====================================================================
import json, os, re, struct, sys, time
HOME = os.environ.get("BLUE_HOME") or os.path.dirname(os.path.abspath(__file__))
os.environ["BLUE_HOME"] = HOME
if HOME not in sys.path: sys.path.insert(0, HOME)
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import phonectl as P

VER = "18/11a"
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

def parse_df(txt):
    """Kết quả `df -k` trong Android → {nơi gắn: (tổng, đã dùng, trống)} tính bằng byte."""
    out = {}; carry = []
    for ln in (txt or "").splitlines():
        t = ln.split()
        if not t or t[0].lower() == "filesystem": continue
        t = carry + t
        if len(t) < 6: carry = t; continue
        carry = []
        try: out[t[-1]] = (int(t[1]) * 1024, int(t[2]) * 1024, int(t[3]) * 1024)
        except ValueError: continue
    return out
def android_df(port):
    """(tổng, đã dùng, trống) của /data + của bộ nhớ trong (sdcard) nếu nằm ổ khác — máy phải đang chạy và adb nối được."""
    try:
        if not P._adb_fresh(port) and not P._adb_fresh(port): return None, None
        r = P.adb("-s", f"127.0.0.1:{port}", "shell", "df -k /data /sdcard /storage/emulated/0 2>/dev/null", timeout=25)
    except Exception: return None, None
    d = parse_df(r.stdout)
    data = d.get("/data") or next((v for k, v in d.items() if k.startswith("/data")), None)
    sd = next((v for k, v in d.items() if k != "/data" and ("sdcard" in k or "emulated" in k or k.startswith("/storage"))), None)
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

def main():
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
