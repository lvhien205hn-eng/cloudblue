# CloudBlue - kiem tra vi sao lag (CHI DOC, khong sua gi tren may, khong in khoa/mat khau)
# Chay tren may chu (PowerShell):  & "C:\Program Files\Python312\python.exe" -I C:\blue\kiemlag.py   [so gio, mac dinh 3]
import os, re, sys, time, shutil, subprocess, collections

B = r"C:\blue"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
LOG = next((a for a in ARGS if not a.isdigit()), os.path.join(B, "logs", "phat-hinh.log"))
HOURS = next((int(a) for a in ARGS if a.isdigit()), 3)
WIN = os.name == "nt"


def node_id():
    try:
        for ln in open(os.path.join(B, "cloudphone.conf"), encoding="utf-8-sig"):
            if ln.strip().startswith("NODE_ID="):
                return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return "?"


def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def gpu_sample(smi):
    for q in ("name,utilization.gpu,memory.used,memory.total,temperature.gpu,clocks.sm,clocks.max.sm,encoder.stats.sessionCount",
              "name,utilization.gpu,memory.used,memory.total,temperature.gpu"):
        try:
            out = subprocess.run([smi, "--query-gpu=" + q, "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
        except Exception:
            return []
        n = q.count(",") + 1; res = []
        for line in out.strip().splitlines():
            f = [x.strip() for x in line.split(",")]
            if len(f) != n: continue
            f += [""] * (8 - n)
            res.append({"name": f[0], "util": num(f[1]), "mu": num(f[2]), "mt": num(f[3]), "temp": num(f[4]),
                        "clk": num(f[5]), "clkmax": num(f[6]), "enc": num(f[7])})
        if res: return res
    return []


def systimes():
    import ctypes
    class FT(ctypes.Structure): _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]
    i, k, u = FT(), FT(), FT()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u)): return None
    v = lambda t: (t.hi << 32) | t.lo
    return v(i), v(k), v(u)


def memory():
    import ctypes
    class MS(ctypes.Structure):
        _fields_ = [("len", ctypes.c_uint32), ("load", ctypes.c_uint32), ("total", ctypes.c_uint64), ("avail", ctypes.c_uint64),
                    ("ptotal", ctypes.c_uint64), ("pavail", ctypes.c_uint64), ("vtotal", ctypes.c_uint64), ("vavail", ctypes.c_uint64),
                    ("ext", ctypes.c_uint64)]
    m = MS(); m.len = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    g = 1024 ** 3
    return m.total / g, m.avail / g, m.ptotal / g, m.pavail / g


def machine():
    """Card, CPU, RAM, o cung, so may ao dang chay. Tra danh sach canh bao."""
    warn = []
    smi = shutil.which("nvidia-smi") or next((f for f in (r"C:\Windows\System32\nvidia-smi.exe",
                                                          r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe") if os.path.isfile(f)), "")
    gs, cs = [], []
    t0 = systimes() if WIN else None
    for _ in range(6):
        if smi: gs.append(gpu_sample(smi))
        time.sleep(1)
    t1 = systimes() if WIN else None
    if t0 and t1:
        di, dk, du = t1[0] - t0[0], t1[1] - t0[1], t1[2] - t0[2]
        cpu = 100.0 * (dk + du - di) / max(1, dk + du)
    else:
        cpu = None
    print("== MÁY CHỦ " + node_id() + " · " + time.strftime("%d/%m %H:%M:%S"))
    if not smi: print("  Card: không có nvidia-smi")
    for gi in range(max((len(s) for s in gs), default=0)):
        rows = [s[gi] for s in gs if len(s) > gi]
        us = [r["util"] for r in rows if r["util"] is not None]
        r = rows[-1]; ua = sum(us) / len(us) if us else None
        vp = 100 * r["mu"] / r["mt"] if r["mu"] and r["mt"] else None
        line = "  Card %s: dùng %s%% (6 lần đo: %s)" % (r["name"], "?" if ua is None else round(ua), " ".join(str(int(u)) for u in us))
        if vp is not None: line += " · VRAM %d/%d MB (%d%%)" % (r["mu"], r["mt"], vp)
        if r["temp"] is not None: line += " · %d°C" % r["temp"]
        if r["clk"] and r["clkmax"]: line += " · xung %d/%d MHz" % (r["clk"], r["clkmax"])
        if r["enc"] is not None: line += " · NVENC %d phiên" % r["enc"]
        print(line)
        if ua is not None and ua >= 90: warn.append("CARD ĐỒ HOẠ QUÁ TẢI (dùng %d%%) → máy ảo vẽ hình chậm → khách thấy giật dù ping thấp" % ua)
        if vp is not None and vp >= 90: warn.append("VRAM gần đầy (%d%%) → thêm máy nữa là cả loạt máy giật" % vp)
        if r["temp"] is not None and r["temp"] >= 83: warn.append("Card nóng %d°C → card tự hạ xung" % r["temp"])
    if cpu is not None:
        print("  CPU: %d%% (trung bình 6 giây)" % round(cpu))
        if cpu >= 85: warn.append("CPU QUÁ TẢI (%d%%)" % cpu)
    if WIN:
        tot, av, pt, pa = memory()
        print("  RAM: dùng %.0f/%.0f GB · bộ nhớ ảo (commit) còn %.0f/%.0f GB" % (tot - av, tot, pa, pt))
        if av < tot * 0.1: warn.append("RAM gần hết (còn %.0f GB)" % av)
        if pa < pt * 0.08: warn.append("Bộ nhớ ảo (commit) gần hết → máy ảo dễ treo")
        drives = os.listdrives() if hasattr(os, "listdrives") else ["C:\\"]
        ds = []
        for d in drives:
            try: u = shutil.disk_usage(d)
            except OSError: continue
            if u.total < 20 * 1024 ** 3: continue
            p = 100 * u.used / u.total
            ds.append("%s %.0f/%.0f GB (%d%%)" % (d[:2], u.used / 1024 ** 3, u.total / 1024 ** 3, p))
            if p >= 90: warn.append("Ổ %s đầy %d%% (còn %.0f GB) → máy ảo ghi đĩa chậm/treo, web ngừng giao máy mới" % (d[:2], p, u.free / 1024 ** 3))
        print("  Ổ cứng: " + " · ".join(ds))
        try:
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30).stdout
            names = collections.Counter(l.split('","')[0].strip('"') for l in out.splitlines() if l.strip())
            vm = {n: c for n, c in names.items() if re.search(r"headless|mumuplayer|mumunx|dnplayer|memu", n, re.I)}
            print("  Tiến trình giả lập: " + (", ".join("%s × %d" % (n, c) for n, c in sorted(vm.items())) or "?"))
        except Exception:
            pass
    return warn


RE_T = re.compile(r"^(\d\d):(\d\d):(\d\d) (.*)$")
RE_T2 = re.compile(r"^\d\d:\d\d:\d\d ")
RE_START = re.compile(r"▶ (\S+) ← \S+ \((direct|ws), ([^)]*)\)")
RE_CLOSE = re.compile(r"■ (\S+) đóng \(gửi (\d+) khung, bỏ (\d+)(?:, (\d+) kbps)?\)(?: · (\d+) giây)?(?: · (.+))?")
RE_VER = re.compile(r"bản (\S+) \(ngưỡng")
RE_DOWN = re.compile(r"^\s*(\S+): mạng khách ~(\d+) kbps → hạ còn (\d+) kbps")
RE_UP = re.compile(r"^\s*(\S+): mạng ổn → tăng lên (\d+) kbps")
RE_ENC = re.compile(r"^\s*(\S+): bộ nén dừng → bật lại")
RE_LATE = re.compile(r"(\d+) cú bấm, (\d+) lần lệnh nhả tay")
RE_STALL = re.compile(r"\[hình (\S+)\] scrcpy ngừng gửi hình")


def read_tail(p, nbytes=12_000_000):
    with open(p, "rb") as fh:
        fh.seek(0, 2); size = fh.tell(); fh.seek(max(0, size - nbytes))
        data = fh.read()
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[1:] if size > nbytes else lines


def sessions():
    try: lines = read_tail(LOG)
    except OSError as e:
        print("  (không đọc được nhật ký %s: %s)" % (LOG, e)); return None
    day = 0; prev = None; last = 0
    open_s = {}; done = []; cnt = collections.Counter(); taps = [0, 0]
    for ln in lines:
        m = RE_T.match(ln)
        if not m: continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if prev is not None and t < prev - 6 * 3600: day += 1
        prev = t; t += day * 86400; last = t
        msg = RE_T2.sub("", m.group(4), count=1)          # bảng CloudBlue ghi thêm 1 mốc giờ trước dòng của bluestream
        if "mã chứng chỉ:" in msg:                               # phát hình vừa khởi động lại → phiên cũ đã mất
            open_s.clear(); x = RE_VER.search(msg); cnt["ver"] = x.group(1) if x else "cũ"; cnt["boot"] = t; continue
        x = RE_START.search(msg)
        if x:
            open_s[x.group(1)] = {"name": x.group(1), "kind": x.group(2), "app": x.group(3).strip() or "?", "t0": t,
                                  "down": 0, "up": 0, "enc": 0, "kmin": None}
            continue
        x = RE_CLOSE.search(msg)
        if x:
            s = open_s.pop(x.group(1), None)
            if s:
                s.update(t1=t, sent=int(x.group(2)), drop=int(x.group(3)), kbps=int(x.group(4)) if x.group(4) else None,
                         why=(x.group(6) or "").strip())
                done.append(s)
            continue
        x = RE_DOWN.search(msg)
        if x:
            s = open_s.get(x.group(1)); cnt["down"] += 1
            if s:
                s["down"] += 1; k = int(x.group(3)); s["kmin"] = k if s["kmin"] is None else min(s["kmin"], k)
            continue
        x = RE_UP.search(msg)
        if x:
            s = open_s.get(x.group(1)); cnt["up"] += 1
            if s: s["up"] += 1
            continue
        x = RE_ENC.search(msg)
        if x:
            s = open_s.get(x.group(1)); cnt["enc"] += 1
            if s: s["enc"] += 1
            continue
        if RE_STALL.search(msg): cnt["stall"] += 1; continue
        if "bật lại hình lỗi" in msg: cnt["refail"] += 1; continue
        if "tạm dùng lệnh input" in msg: cnt["ctl_input"] += 1; continue
        if "card NVIDIA không nén được" in msg: cnt["x264"] += 1; continue
        if "Android không xuất được hình" in msg: cnt["noscreen"] += 1; continue
        x = RE_LATE.search(msg)
        if x: taps[0] += int(x.group(1)); taps[1] += int(x.group(2))
    since = last - HOURS * 3600
    done = [s for s in done if s["t1"] >= since]
    live = [dict(s, t1=last, sent=None, drop=None, kbps=None) for s in open_s.values() if last - s["t0"] < 12 * 3600]
    return done, live, cnt, taps, last


def hm(t):
    t %= 86400
    return "%02d:%02d" % (t // 3600, t % 3600 // 60)


def report_sessions():
    warn = []
    r = sessions()
    if r is None: return warn
    done, live, cnt, taps, last = r
    ver = cnt.get("ver") or "?"
    print("== PHÁT HÌNH bản %s%s" % (ver, (" · chạy từ %s" % hm(cnt["boot"])) if cnt.get("boot") else ""))
    print("== PHIÊN XEM %d GIỜ QUA (tới %s) · đang xem lúc này: %d" % (HOURS, hm(last), len(live)))
    for s in sorted(live, key=lambda s: s["t0"]):
        print("  • đang xem: %-16s %-6s %-7s từ %s (%d phút) · đổi chất lượng %d lần" % (s["name"][:16], "thẳng" if s["kind"] == "direct" else "vòng",
              s["app"][:7], hm(s["t0"]), (last - s["t0"]) // 60, s["down"] + s["up"]))
    if not done:
        print("  (chưa có phiên nào đóng trong %d giờ qua)" % HOURS); return warn
    print("  %-5s %-16s %-6s %-7s %5s %6s %5s %4s %6s" % ("giờ", "máy", "đường", "app", "phút", "hình/s", "bỏ%", "đổi", "kbps"))
    for s in sorted(done, key=lambda s: s["t0"])[-18:]:
        dur = max(1, s["t1"] - s["t0"]); tot = s["sent"] + s["drop"]
        print("  %-5s %-16s %-6s %-7s %5.1f %6s %5s %4d %6s" % (
            hm(s["t0"]), s["name"][:16], "thẳng" if s["kind"] == "direct" else "vòng", s["app"][:7], dur / 60,
            "%.1f" % (s["sent"] / dur) if dur >= 20 else "-", "%d" % (100 * s["drop"] / tot) if tot else "-", s["down"] + s["up"],
            s["kbps"] if s["kbps"] else "-"))
    agg = {}
    for k in ("direct", "ws"):
        ss = [s for s in done if s["kind"] == k]
        if not ss: continue
        longs = [s for s in ss if s["t1"] - s["t0"] >= 60] or [s for s in ss if s["t1"] - s["t0"] >= 20]
        dur = sum(s["t1"] - s["t0"] for s in longs) or 1
        sent = sum(s["sent"] for s in longs); drop = sum(s["drop"] for s in longs)
        short = len([s for s in ss if s["t1"] - s["t0"] < 60])
        downs = sum(s["down"] + s["up"] for s in ss)
        alldur = sum(max(1, s["t1"] - s["t0"]) for s in ss)        # đổi chất lượng / giờ: chia cho TỔNG thời gian xem (cả phiên ngắn)
        agg[k] = (len(ss), sent / dur, 100 * drop / max(1, sent + drop), short, downs * 3600 / alldur, len(longs))
        print("  → %s: %d phiên · hình/s TB %.1f · bỏ khung %d%% · %d phiên < 1 phút (đứt/nối lại) · tự đổi chất lượng %.1f lần/giờ xem" % (
            "Đường THẲNG" if k == "direct" else "Vòng Cloudflare", len(ss), agg[k][1], agg[k][2], short, agg[k][4]))
    whys = collections.Counter(s.get("why") or "?" for s in done if s.get("why"))
    if whys: print("  → Lý do đóng phiên: " + " · ".join("%s %d" % (w, n) for w, n in whys.most_common(5)))
    extra = []
    if cnt["enc"]: extra.append("bộ nén Android dừng %d lần" % cnt["enc"])
    if cnt["stall"]: extra.append("scrcpy ngừng gửi hình %d lần" % cnt["stall"])
    if cnt["refail"]: extra.append("bật lại hình lỗi %d lần" % cnt["refail"])
    if cnt["ctl_input"]: extra.append("chạm rơi xuống lệnh input %d lần" % cnt["ctl_input"])
    if cnt["x264"]: extra.append("NVENC hỏng → CPU x264 %d lần" % cnt["x264"])
    if cnt["noscreen"]: extra.append("Android không ra hình %d lần" % cnt["noscreen"])
    if taps[0]: extra.append("chạm trễ ≥0,35 giây %d/%d cú (mạng khách giật)" % (taps[1], taps[0]))
    if extra: print("  → Khác (cả nhật ký đọc được): " + " · ".join(extra))
    allong = [a for a in agg.values() if a[5]]
    if allong:
        fps = sum(a[1] * a[5] for a in allong) / sum(a[5] for a in allong)
        drop = max(a[2] for a in allong)
        if fps < 20 and drop < 8: warn.append("Ít hình mới (TB %.0f hình/s) mà gần như không bỏ khung → máy ảo vẽ chậm (card / CPU quá tải) hoặc màn hình đứng yên — KHÔNG phải mạng" % fps)
        if drop >= 10: warn.append("Bỏ khung nhiều (%d%%) → mạng khách hoặc đường truyền chập chờn" % drop)
        if "direct" in agg and "ws" in agg and agg["direct"][5] and agg["ws"][5]:
            d, w = agg["direct"], agg["ws"]
            if d[1] < w[1] * 0.7 or d[2] > w[2] + 8: warn.append("Đường THẲNG kém hơn vòng Cloudflare (hình/s %.0f vs %.0f, bỏ %d%% vs %d%%)" % (d[1], w[1], d[2], w[2]))
    rate = [a[4] for a in agg.values()]
    if ver in ("cũ", "?"): warn.append("Phát hình còn BẢN CŨ → cập nhật bluestream.py (bản 11/11c)")
    if rate and max(rate) >= 4: warn.append("Máy chủ tự đổi chất lượng nhiều (%.0f lần/giờ) → mỗi lần đổi, bộ nén trong máy Android bật lại → đứng hình 1–3 giây" % max(rate))
    if cnt["enc"] >= 3: warn.append("Bộ nén trong máy Android dừng/bật lại %d lần → mỗi lần đứng hình 1–3 giây" % cnt["enc"])
    if cnt["ctl_input"] >= 3: warn.append("Điều khiển chạm hay rơi xuống lệnh input (%d lần) → bấm chậm ~1 giây" % cnt["ctl_input"])
    return warn


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    w = [] if "--test" in sys.argv else machine()
    w += report_sessions()
    print("== KẾT LUẬN")
    for x in w or ["Không thấy máy chủ quá tải, không bỏ khung nhiều → xem dòng thông số trên app của khách (hình/s · kbps · ms)"]:
        print("  ⚠ " + x)
