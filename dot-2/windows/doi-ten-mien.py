# -*- coding: utf-8 -*-
# =====================================================================================================
#  doi-ten-mien.py — chuyển MÁY CHỦ này sang tên miền mới (chạy 1 lần trên mỗi máy chủ)
#
#    Máy 1:  python C:\blue\doi-ten-mien.py cloudblue.vn
#    Máy 2:  python C:\blue\doi-ten-mien.py cloudblue.vn phone2
#
#  Làm:  1) sửa C:\blue\cloudphone.conf (giữ nguyên các dòng khác + khoá; chép dự phòng .bak trước khi sửa)
#           PUBLIC_BASE   = https://phone.<tên miền>           cổng bảo vệ cpapi qua đường hầm Cloudflare
#           STREAM_WS     = wss://stream.<tên miền>/v2/stream   đường phát hình dự phòng qua Cloudflare
#           CPAPI_ORIGINS = https://<tên miền>,https://www.<tên miền>  (giữ thêm các tên miền đã có)
#           NOTIFY_URL    = https://<tên miền>/api/notify-admin
#        2) đổi link điều khiển cũ (stream_url) của các máy khách trên máy chủ này sang tên miền mới
#        3) đường hầm Cloudflare "quản lý tại máy" (C:\blue\cloudflared.yml): thêm phone.<tên miền> → :8010 và
#           stream.<tên miền> → :8020 (giữ nguyên các tên cũ), kiểm tra file, khởi động lại đường hầm (cần PowerShell Admin),
#           rồi in 2 bản ghi DNS cần thêm ở Cloudflare (CNAME → <mã đường hầm>.cfargotunnel.com, mây cam)
#  Xong: trong bảng bấm ■ Tắt tất cả → ▶ Bật tất cả.   Không in khoá bí mật ra màn hình.
# =====================================================================================================
import base64, datetime, json, os, re, shutil, subprocess, sys, urllib.parse, urllib.request

try: sys.stdout.reconfigure(errors="replace")
except Exception: pass

B = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(B, "cloudphone.conf")
HOST_RE = re.compile(r"^(?=.{4,200}$)([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")


def read_conf():
    raw = open(CONF, encoding="utf-8-sig", newline="").read()   # utf-8-sig: bỏ BOM nếu PowerShell lỡ thêm vào; newline="": giữ kiểu xuống dòng
    cur = {}
    for l in raw.splitlines():
        s = l.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1); cur[k.strip()] = v.strip()
    return raw, cur


def write_conf(raw, want):
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines, seen = raw.splitlines(), set()
    for i, l in enumerate(lines):
        s = l.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in want: lines[i] = f"{k}={want[k]}"; seen.add(k)
    lines += [f"{k}={v}" for k, v in want.items() if k not in seen]
    data, tmp = nl.join(lines) + nl, CONF + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f: f.write(data)
    try: os.replace(tmp, CONF)
    except PermissionError:                     # file đang bị chương trình khác giữ → ghi thẳng
        with open(CONF, "w", encoding="utf-8", newline="") as f: f.write(data)
        os.remove(tmp)


def fix_stream_urls(cur, old_host, new_host):
    """Máy khách đã tạo trước đây giữ link cũ (phone.<tên miền cũ>/…) → đổi sang tên miền mới."""
    sb, key = cur.get("SUPABASE_URL", "").rstrip("/"), cur.get("SUPABASE_SERVICE_KEY", "")
    if not (sb and len(key) > 30): print("  (bỏ qua bước đổi link máy khách: chưa có khoá Supabase trong conf)"); return
    H = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}
    q = sb + "/rest/v1/cloud_phones?select=id,stream_url&stream_url=like." + urllib.parse.quote(f"*{old_host}*", safe="*")
    rows = json.loads(urllib.request.urlopen(urllib.request.Request(q, headers=H), timeout=20).read() or b"[]")
    n = 0
    for r in rows:
        su = r.get("stream_url") or ""
        nu = su.replace(old_host, new_host)
        if nu == su: continue
        req = urllib.request.Request(sb + "/rest/v1/cloud_phones?id=eq." + urllib.parse.quote(str(r["id"])),
                                     data=json.dumps({"stream_url": nu}).encode(), method="PATCH",
                                     headers={**H, "Prefer": "return=minimal"})
        urllib.request.urlopen(req, timeout=20).read(); n += 1
    print(f"✓ Đổi link điều khiển của {n} máy khách: {old_host} → {new_host}")


# ---------------- đường hầm Cloudflare "quản lý tại máy" ----------------
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def svc_cmd():
    """Lệnh chạy dịch vụ cloudflared trong Windows (có mã bí mật → chỉ đọc, KHÔNG in ra)."""
    if os.name != "nt": return os.environ.get("CF_SVC_CMD", "")          # (thử trên máy khác)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\cloudflared") as k:
            return str(winreg.QueryValueEx(k, "ImagePath")[0])
    except OSError: return ""


def tunnel_id(cmd, yml):
    m = re.search(r"(?m)^\s*tunnel\s*:\s*['\"]?(" + UUID_RE.pattern + ")", yml or "")
    if m: return m.group(1)
    m = re.search(r"--token[=\s]+['\"]?([A-Za-z0-9+/_=-]{40,})", cmd or "")
    if not m: return ""
    t = m.group(1)
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            tid = str(json.loads(dec(t + "=" * (-len(t) % 4))).get("t") or "")
            if UUID_RE.fullmatch(tid): return tid
        except Exception: pass
    return ""


def add_ingress(raw, rules):
    """Thêm luật (tên miền → dịch vụ) vào mục ingress, giữ nguyên các luật cũ; luật bắt-tất-cả luôn ở cuối.
       Trả (nội dung mới, các tên vừa thêm)."""
    nl = "\r\n" if "\r\n" in raw else "\n"
    L = raw.splitlines()
    i0 = next((i for i, l in enumerate(L) if re.match(r"^ingress\s*:\s*(#.*)?$", l)), None)
    if i0 is None:
        while L and not L[-1].strip(): L.pop()
        L.append("ingress:"); i0 = len(L) - 1
    i1 = i0 + 1
    while i1 < len(L) and (not L[i1].strip() or L[i1][:1] in (" ", "\t", "-", "#")): i1 += 1
    pre, blocks = [], []
    for l in L[i0 + 1:i1]:
        if l.lstrip().startswith("-"): blocks.append([l])
        elif blocks: blocks[-1].append(l)
        else: pre.append(l)
    host = lambda b: (re.search(r"hostname\s*:\s*['\"]?([^'\"\s#]+)", "\n".join(b)) or [None, ""])[1].lower()
    have = {host(b) for b in blocks if host(b)}
    d = len(blocks[0][0]) - len(blocks[0][0].lstrip()) if blocks else 2
    new = [[" " * d + f"- hostname: {h}", " " * (d + 2) + f"service: {svc}"] for h, svc in rules if h.lower() not in have]
    k = next((i for i, b in enumerate(blocks) if not host(b)), None)          # luật bắt-tất-cả (không có hostname)
    if k is None: blocks += new + [[" " * d + "- service: http_status:404"]]
    else: blocks[k:k] = new
    out = L[:i0 + 1] + pre + [l for b in blocks for l in b] + L[i1:]
    return nl.join(out) + nl, [b[0].split("hostname:", 1)[1].strip() for b in new]


def fix_tunnel(dom, sub, ssub, cur):
    cmd = svc_cmd()
    m = re.search(r'--config[=\s]+(?:"([^"]+)"|(\S+))', cmd)
    yml = (m.group(1) or m.group(2)) if m else os.path.join(B, "cloudflared.yml")
    if not os.path.isfile(yml):
        print(f"  (không thấy {yml} → đường hầm máy này quản lý trên web Cloudflare: thêm {sub}.{dom} và {ssub}.{dom} ở trang Tunnels)")
        return
    raw = open(yml, encoding="utf-8-sig", newline="").read()
    ws_port = str(cur.get("STREAM_WS_PORT") or 8020).strip()
    data, added = add_ingress(raw, [(f"{sub}.{dom}", "http://localhost:8010"), (f"{ssub}.{dom}", f"http://localhost:{ws_port}")])
    tid = tunnel_id(cmd, raw)
    if added:
        bak = yml + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(yml, bak)
        with open(yml, "w", encoding="utf-8", newline="") as f: f.write(data)
        print(f"✓ Đường hầm: thêm {', '.join(added)} vào {yml}  (bản cũ: {os.path.basename(bak)})")
        m = re.match(r'\s*(?:"([^"]+)"|(\S+))', cmd)
        exe = next((x for x in ((m.group(1) or m.group(2)) if m else "", shutil.which("cloudflared") or "",
                                r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe")
                    if x and x.lower().endswith(".exe") and os.path.isfile(x)), "")
        if exe:
            r = subprocess.run([exe, "tunnel", "--config", yml, "ingress", "validate"], capture_output=True, text=True, timeout=60)
            o = (r.stdout + r.stderr).strip()
            if r.returncode == 0: print("✓ cloudflared kiểm tra file: hợp lệ")
            elif re.search(r"Incorrect Usage|flag provided but not defined|No help topic", o): print("  (bản cloudflared này không có lệnh kiểm tra file — bỏ qua)")
            else:
                shutil.copy2(bak, yml)
                print("✗ cloudflared báo file chưa đúng → đã trả lại file cũ, chưa đổi gì. Chụp dòng dưới gửi hỗ trợ:")
                print("  ", o[-600:]); return
        if os.name == "nt":
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Restart-Service cloudflared -Force -ErrorAction Stop; Start-Sleep 2; Start-Service cloudflared"], capture_output=True, text=True, timeout=180)
            if r.returncode == 0: print("✓ Đã khởi động lại đường hầm Cloudflare")
            else: print("✗ Chưa khởi động lại được đường hầm (cần PowerShell mở bằng quyền Admin). Gõ:  Restart-Service cloudflared")
    else:
        print(f"✓ Đường hầm: {yml} đã có {sub}.{dom} và {ssub}.{dom}")
    print()
    print(f"→ Thêm 2 bản ghi ở Cloudflare: tên miền {dom} → DNS → Records → Add record (để MÂY CAM - Proxied):")
    tgt = f"{tid}.cfargotunnel.com" if tid else "<giống bản ghi phone của tên miền cũ, dạng ….cfargotunnel.com>"
    print(f"     Type CNAME   Name {sub:<8} Target {tgt}")
    print(f"     Type CNAME   Name {ssub:<8} Target {tgt}")


def main():
    a = [x.strip().lower().rstrip(".") for x in sys.argv[1:] if x.strip()]
    if a and a[0].startswith("www."): a[0] = a[0][4:]
    if not a or not HOST_RE.match(a[0]) or (len(a) > 1 and not re.fullmatch(r"[a-z0-9-]{1,40}", a[1])):
        print("Cách dùng:  python doi-ten-mien.py cloudblue.vn            (máy 1)")
        print("            python doi-ten-mien.py cloudblue.vn phone2     (máy 2)"); return 2
    dom, sub = a[0], (a[1] if len(a) > 1 else "phone")
    ssub = ("stream" + sub[5:]) if sub.startswith("phone") else ("stream-" + sub)
    try: raw, cur = read_conf()
    except FileNotFoundError: print("✗ Không thấy", CONF, "— chạy file này trong thư mục C:\\blue của máy chủ."); return 1

    origins = [f"https://{dom}", f"https://www.{dom}"] + [o.strip().rstrip("/") for o in cur.get("CPAPI_ORIGINS", "").split(",") if o.strip()]
    want = {"PUBLIC_BASE": f"https://{sub}.{dom}",
            "STREAM_WS": f"wss://{ssub}.{dom}/v2/stream",
            "CPAPI_ORIGINS": ",".join(dict.fromkeys(origins)),
            "NOTIFY_URL": f"https://{dom}/api/notify-admin"}
    old_host = urllib.parse.urlparse(cur.get("PUBLIC_BASE", "")).netloc.lower()

    bak = CONF + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"); i = 1
    while os.path.exists(bak): bak = bak.split("~")[0] + f"~{i}"; i += 1
    shutil.copy2(CONF, bak)
    write_conf(raw, want)
    print(f"✓ Đã sửa {CONF}  (bản cũ lưu ở {os.path.basename(bak)})")
    for k, v in want.items():
        o = cur.get(k, "")
        print(f"   {k:<14} {'(giữ nguyên)' if o == v else (o or '(chưa có)') + '  →'}  {v}")

    if old_host and old_host != f"{sub}.{dom}":
        try: fix_stream_urls(cur, old_host, f"{sub}.{dom}")
        except Exception as e: print("✗ Chưa đổi được link máy khách (chạy lại file này sau):", e)

    print()
    try: fix_tunnel(dom, sub, ssub, cur)
    except Exception as e: print("✗ Chưa sửa được đường hầm:", e)
    print()
    print("Cuối cùng: trong bảng BlueRoblox bấm  ■ Tắt tất cả  →  ▶ Bật tất cả.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
