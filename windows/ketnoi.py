# =====================================================================================================
#  ketnoi.py — LÀM MƯỢT KẾT NỐI xem/điều khiển máy (app điện thoại · app PC · web) — CloudBlue 09/11/2026
#
#  Chạy trên máy chủ Windows, PowerShell QUYỀN ADMIN:
#      & "C:\Program Files\Python312\python.exe" C:\blue\ketnoi.py
#  Làm lần lượt (in ra màn hình + ghi C:\blue\ketnoi.txt):
#    1. Khởi động lại "phát hình" (bluestream.py bản mới) — bảng CloudBlue tự bật lại sau ~5 giây; khách đang xem tự nối lại.
#    2. Đường THẲNG (app điện thoại + app PC không đi vòng Cloudflare): kiểm IP modem / CGNAT / cổng STREAM_PORT bằng UPnP;
#       cổng bị chiếm hoặc trỏ sai máy → tự chuyển sang cổng trống khác (8195…) mở được bằng UPnP + mở tường lửa + bật lại phát hình.
#    3. Đường VÒNG Cloudflare (web luôn đi đường này): đo tốc độ thật qua đường hầm, thử giao thức còn lại (QUIC ↔ HTTP/2),
#       GIỮ cái nhanh hơn (chậm hơn / không lên → trả lại như cũ). Không đụng tới mã đường hầm (token).
#  Tuỳ chọn:  --chi-kiem   chỉ đo + in, KHÔNG đổi gì, không khởi động lại gì
#             --cf auto|http2|quic   ép giao thức đường hầm (không đo so sánh)   ·   --khong-cf   bỏ qua bước 3
# =====================================================================================================
import ctypes, datetime, hashlib, os, random, re, socket, subprocess, sys, time, urllib.error, urllib.request

B = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
WIN = os.name == "nt"
NOWIN = 0x08000000 if WIN else 0
OUT = os.path.join(B, "ketnoi.txt")
SVC = r"SYSTEM\CurrentControlSet\Services\cloudflared"
PROTO_ENV = "TUNNEL_TRANSPORT_PROTOCOL"
_out = []


def say(*a):
    s = " ".join(str(x) for x in a)
    try: print(s, flush=True)
    except Exception: pass
    _out.append(s)


def save_report():
    try:
        with open(OUT, "w", encoding="utf-8") as f: f.write("\n".join(_out) + "\n")
    except OSError:
        pass


def load_conf():
    """Đọc cloudphone.conf GIỐNG bluestream (dòng đầu tiên của mỗi khoá thắng)."""
    c = {}
    for f in (os.path.join(B, "cloudphone.conf"), os.path.expanduser("~/cloudphone.conf")):
        try:
            for line in open(f, encoding="utf-8-sig"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1); c.setdefault(k.strip(), v.strip())
        except FileNotFoundError:
            pass
    return c


def speed_token(c):
    """Mã đo tốc độ — GIỐNG SPEED_TOKEN trong bluestream.py (băm từ khoá máy chủ, không in ra)."""
    node = c.get("NODE_ID") or socket.gethostname()
    return hashlib.sha256(((c.get("SUPABASE_SERVICE_KEY") or "") + "|" + node + "|cb-speed").encode()).hexdigest()[:24]


def ps(cmd, timeout=90):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, creationflags=NOWIN)
    return (r.stdout or "").strip()


# ---------------------------------------------------------------- phát hình (bluestream)
def bs_pids():
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\\.exe$' -and $_.CommandLine -match 'bluestream\\.py' "
             "-and $_.CommandLine -notmatch '--(netcheck|upnp|captest|selftest)' } | ForEach-Object { $_.ProcessId }")
    return sorted(int(x) for x in out.split() if x.isdigit())


def ws_banner(port, timeout=3.0):
    """WebSocket cục bộ của phát hình trả gì cho GET / ("BlueRoblox stream v2" = đang chạy)."""
    try:
        s = socket.create_connection(("127.0.0.1", int(port)), timeout=timeout)
        s.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"); s.settimeout(timeout); data = b""
        while len(data) < 4096:
            b = s.recv(4096)
            if not b: break
            data += b
        s.close()
        return data.decode("latin-1", "replace")
    except OSError:
        return ""


def new_code_up(port, tok):
    """Phát hình đang chạy là BẢN MỚI (có /v2/speed)?"""
    try:
        s = socket.create_connection(("127.0.0.1", int(port)), timeout=3)
        s.sendall(f"GET /v2/speed?kb=1&t={tok} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode()); s.settimeout(3); data = b""
        while len(data) < 3000:
            b = s.recv(4096)
            if not b: break
            data += b
        s.close()
        return data.startswith(b"HTTP/1.1 200") and len(data.split(b"\r\n\r\n", 1)[-1]) == 1024
    except OSError:
        return False


def restart_bluestream(c, why):
    old = bs_pids(); wsp = int(c.get("STREAM_WS_PORT") or 8020)
    if not old:
        say(f"  ✗ không thấy phát hình (bluestream.py) đang chạy → mở bảng CloudBlue, bấm ▶ Bật tất cả rồi chạy lại ketnoi.py")
        return False
    say(f"  ↻ {why}: tắt phát hình (pid {', '.join(map(str, old))}) — bảng CloudBlue tự bật lại sau ~5 giây…")
    for p in old: subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True, creationflags=NOWIN)
    t0 = time.time()
    while time.time() - t0 < 60:
        time.sleep(2)
        now = [p for p in bs_pids() if p not in old]
        if now and "BlueRoblox stream v2" in ws_banner(wsp):
            say(f"  ✓ phát hình đã chạy lại (pid {', '.join(map(str, now))}) sau {int(time.time() - t0)} giây")
            return True
    say("  ✗ sau 60 giây bảng chưa bật lại phát hình → trong bảng CloudBlue bấm ■ Tắt tất cả → ▶ Bật tất cả")
    return False


def log_tail_lines(n=400):
    p = os.path.join(B, "logs", "phat-hinh.log")
    try:
        with open(p, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 200_000))
            return f.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []


def firewall_open(port):
    nm = "BlueRoblox Stream TCP"
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], capture_output=True, creationflags=NOWIN)
    r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={nm}", "dir=in", "action=allow", "protocol=TCP",
                        f"localport={port}"], capture_output=True, creationflags=NOWIN)
    return r.returncode == 0


# ---------------------------------------------------------------- đường hầm Cloudflare
def https_base(c):
    w = (c.get("STREAM_WS") or "").strip()
    if not w.startswith(("wss://", "ws://")): return ""
    w = ("https://" + w[6:]) if w.startswith("wss://") else ("http://" + w[5:])
    return w.split("/v2/")[0].rstrip("/") + "/v2/speed"


def speed_once(base, tok, kb, limit=12.0):
    """1 lần tải kb KB qua đường hầm → {"kbps", "ms" (tới byte đầu), "kb"} · lỗi → {"err"}."""
    url = f"{base}?kb={kb}&t={tok}&r={random.randint(1, 1 << 30)}"
    req = urllib.request.Request(url, headers={"User-Agent": "CloudBlue-ketnoi/1", "Cache-Control": "no-cache"})
    t0 = time.time(); got = 0
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200: return {"err": f"HTTP {r.status}"}
            if not str(r.headers.get("Content-Type", "")).startswith("application/octet-stream"):
                return {"err": "phát hình chưa chạy bản mới (chưa có /v2/speed)"}
            t1 = time.time()
            while True:
                b = r.read(65536)
                if not b: break
                got += len(b)
                if time.time() - t1 > limit: break
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503) and WIN: return speed_curl(url, limit)       # Cloudflare chặn trình tải của Python → thử curl.exe
        return {"err": f"HTTP {e.code}"}
    except Exception as e:
        return {"err": (str(e) or e.__class__.__name__)[:90]}
    dt = max(0.001, time.time() - t1)
    return {"kbps": got * 8 / dt / 1000, "ms": (t1 - t0) * 1000, "kb": got // 1024}


def speed_curl(url, limit=12.0):
    try:
        r = subprocess.run(["curl.exe", "-s", "-o", "NUL", "--max-time", str(int(limit) + 3), "-A", "CloudBlue-ketnoi/1",
                            "-w", "%{http_code} %{time_starttransfer} %{time_total} %{size_download} %{content_type}", url],
                           capture_output=True, text=True, timeout=limit + 10, creationflags=NOWIN)
        parts = (r.stdout or "").split()
        code, ttfb, tot, size = parts[:4]; ctype = parts[4] if len(parts) > 4 else ""
        if code != "200": return {"err": f"HTTP {code}"}
        if not ctype.startswith("application/octet-stream"): return {"err": "phát hình chưa chạy bản mới (chưa có /v2/speed)"}
        dt = max(0.001, float(tot) - float(ttfb))
        return {"kbps": float(size) * 8 / dt / 1000, "ms": float(ttfb) * 1000, "kb": int(float(size)) // 1024}
    except Exception as e:
        return {"err": (str(e) or e.__class__.__name__)[:90]}


def measure(base, tok):
    """Độ trễ (3 lần 1 KB, lấy nhỏ nhất) + tốc độ (2 lần 1,5 MB / tối đa 12 giây, lấy lớn nhất). Đường hầm không lên → None."""
    pings = [speed_once(base, tok, 1, 5) for _ in range(3)]
    okp = [p["ms"] for p in pings if "ms" in p]
    if not okp: return {"err": next((p["err"] for p in pings if "err" in p), "?")}
    runs = [speed_once(base, tok, 1536) for _ in range(2)]
    okr = [r for r in runs if "kbps" in r]
    if not okr: return {"err": next((r["err"] for r in runs if "err" in r), "?"), "ms": min(okp)}
    best = max(okr, key=lambda r: r["kbps"])
    return {"ms": min(okp), "kbps": best["kbps"]}


def fmt_m(m):
    if not m: return "?"
    if "kbps" not in m: return f"LỖI ({m.get('err', '?')})"
    k = m["kbps"]
    return f"{k / 1000:.1f} Mbit/s · trễ {m['ms']:.0f} ms" if k >= 1000 else f"{k:.0f} kbit/s · trễ {m['ms']:.0f} ms"


def cf_key(write=False):
    import winreg
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SVC, 0, winreg.KEY_READ | (winreg.KEY_SET_VALUE if write else 0))


def cf_exists():
    try: cf_key().Close(); return True
    except OSError: return False


def cf_cmd_has_protocol():
    """Lệnh chạy dịch vụ đã có --protocol? (đọc ImagePath — KHÔNG in ra vì trong đó có mã đường hầm)"""
    import winreg
    try:
        with cf_key() as k: return "--protocol" in str(winreg.QueryValueEx(k, "ImagePath")[0])
    except OSError:
        return False


def cf_env():
    import winreg
    try:
        with cf_key() as k: v = winreg.QueryValueEx(k, "Environment")[0]
        return [str(x) for x in (v if isinstance(v, (list, tuple)) else [v]) if x]
    except OSError:
        return []


def cf_proto():
    for x in cf_env():
        if x.upper().startswith(PROTO_ENV + "="): return x.split("=", 1)[1].strip().lower() or "auto"
    return "auto"


def cf_set_proto(proto):
    """auto = xoá biến (cloudflared tự chọn, thường QUIC) · http2 / quic = ép. Chỉ sửa biến môi trường của dịch vụ."""
    import winreg
    lst = [x for x in cf_env() if not x.upper().startswith(PROTO_ENV + "=")]
    if proto and proto != "auto": lst.append(f"{PROTO_ENV}={proto}")
    with cf_key(write=True) as k:
        if lst: winreg.SetValueEx(k, "Environment", 0, winreg.REG_MULTI_SZ, lst)
        else:
            try: winreg.DeleteValue(k, "Environment")
            except OSError: pass


def cf_restart(base, tok):
    ps("Restart-Service cloudflared -Force -ErrorAction SilentlyContinue; Start-Sleep 2; Start-Service cloudflared -ErrorAction SilentlyContinue", 120)
    t0 = time.time()
    while time.time() - t0 < 75:
        time.sleep(3)
        if "kbps" in speed_once(base, tok, 1, 5): return True
    return False


def cf_locations():
    """Trạm Cloudflare đường hầm đang nối (đọc /metrics của cloudflared nếu có)."""
    for port in range(20241, 20246):
        try:
            t = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2).read().decode("utf-8", "replace")
            locs = sorted(set(re.findall(r'edge_location="([A-Za-z0-9_-]+)"', t)))
            if locs: return locs
        except Exception:
            continue
    return []


# ---------------------------------------------------------------- chạy
def main(argv):
    only_check = "--chi-kiem" in argv
    force = argv[argv.index("--cf") + 1].lower() if "--cf" in argv and argv.index("--cf") + 1 < len(argv) else None
    if force and force not in ("auto", "http2", "quic"): say("--cf chỉ nhận auto / http2 / quic"); return 2
    say(f"=== ketnoi.py · {datetime.datetime.now():%d/%m/%Y %H:%M:%S} · {'CHỈ KIỂM' if only_check else 'kiểm + sửa'}")
    if WIN and not only_check and not ctypes.windll.shell32.IsUserAnAdmin():
        say("✗ Cần PowerShell QUYỀN ADMIN (chuột phải PowerShell → Run as administrator) rồi chạy lại."); return 2
    bsf = os.path.join(B, "bluestream.py")
    if not os.path.isfile(bsf): say(f"✗ không thấy {bsf}"); return 2
    if "def netcheck" not in open(bsf, encoding="utf-8", errors="replace").read():
        say("✗ bluestream.py còn BẢN CŨ (chưa có --netcheck) → tải bản mới từ GitHub trước"); return 2
    c = load_conf(); tok = speed_token(c); wsp = int(c.get("STREAM_WS_PORT") or 8020)
    say(f"Máy chủ {c.get('NODE_ID') or socket.gethostname()} · cổng phát hình {c.get('STREAM_PORT') or 8189} · đường hầm {c.get('STREAM_WS') or '(chưa có)'}")

    # 1) phát hình bản mới
    say("\n[1] Phát hình (bluestream)")
    if new_code_up(wsp, tok): say("  ✓ đang chạy bản mới")
    elif only_check: say("  · đang chạy bản cũ (chưa khởi động lại)")
    else: restart_bluestream(c, "chạy bản mới")

    # 2) đường thẳng
    say("\n[2] Đường THẲNG cho app điện thoại + app PC")
    args = [PY, "-u", bsf, "--netcheck"] + ([] if only_check else ["--fix"])
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, cwd=B, creationflags=NOWIN)
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        out = "  ✗ kiểm cổng quá 4 phút — bỏ qua"
    for ln in out.splitlines():
        if ln.strip(): say(ln)
    m = re.search(r"NEWPORT=(\d+)", out)
    if m and not only_check:
        newp = int(m.group(1))
        say(f"  {'✓' if firewall_open(newp) else '✗'} tường lửa Windows: mở TCP {newp}")
        restart_bluestream(load_conf(), f"dùng cổng mới {newp}")
        time.sleep(20)                                            # chờ phát hình báo đường nối mới lên web + UPnP
        for ln in [x for x in log_tail_lines(300) if re.search(r"bluestream chạy|đường nối:|UPnP:", x)][-3:]: say("  log │ " + ln.strip())

    # 3) đường vòng Cloudflare
    say("\n[3] Đường VÒNG Cloudflare (web + app khi không đi thẳng được)")
    base = https_base(c)
    if "--khong-cf" in argv: say("  (bỏ qua theo --khong-cf)")
    elif not base: say("  · chưa có STREAM_WS trong cloudphone.conf — bỏ qua")
    elif not WIN or not cf_exists(): say("  · máy này không có dịch vụ cloudflared — bỏ qua")
    else:
        cur = cf_proto(); locs = cf_locations()
        say(f"  giao thức đường hầm: {cur}{' (lệnh chạy dịch vụ đã có --protocol — giữ nguyên)' if cf_cmd_has_protocol() else ''}"
            + (f" · trạm Cloudflare: {', '.join(locs)}" if locs else ""))
        a = measure(base, tok); say(f"  đo ({cur}): {fmt_m(a)}")
        if only_check or cf_cmd_has_protocol():
            pass
        elif force:
            if force != cur:
                cf_set_proto(force); up = cf_restart(base, tok)
                b = measure(base, tok) if up else None
                say(f"  đổi sang {force}: {fmt_m(b) if up else 'đường hầm KHÔNG lên'}")
                if not up:
                    cf_set_proto(cur); cf_restart(base, tok); say(f"  ↩ trả lại {cur}")
        elif "kbps" not in a:
            say("  ✗ chưa đo được qua đường hầm (phát hình chưa bản mới / đường hầm lỗi) — không đổi giao thức")
        else:
            alt = "http2" if cur in ("auto", "quic") else "auto"
            say(f"  thử {alt} (khách đang xem qua web mất hình ~10 giây rồi tự nối lại)…")
            cf_set_proto(alt); up = cf_restart(base, tok)
            b = measure(base, tok) if up else {"err": "đường hầm không lên"}
            say(f"  đo ({alt}): {fmt_m(b)}")
            if "kbps" in b and b["kbps"] > a["kbps"] * 1.15:
                locs2 = cf_locations()
                say(f"  ✓ GIỮ {alt}: nhanh hơn {b['kbps'] / max(1.0, a['kbps']):.1f} lần" + (f" · trạm: {', '.join(locs2)}" if locs2 else ""))
            else:
                cf_set_proto(cur); up2 = cf_restart(base, tok)
                say(f"  ↩ trả lại {cur} ({'không nhanh hơn' if 'kbps' in b else b.get('err', '?')})" + ("" if up2 else " — ✗ đường hầm chưa lên lại, kiểm dịch vụ cloudflared"))
        if "kbps" in a and a["kbps"] < 2000:
            say("  ⚠ Đường vòng Cloudflare chậm (< 2 Mbit/s) → khách xem qua web sẽ thấy mờ / giật; app điện thoại + PC cần đi đường THẲNG (bước 2).")

    say("\n=== XONG — gửi file C:\\blue\\ketnoi.txt cho Claude nếu còn lỗi")
    save_report()
    return 0


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    try:
        rc = main(sys.argv[1:])
    except Exception as e:
        say(f"✗ LỖI: {e!r}"); save_report(); rc = 1
    sys.exit(rc)
