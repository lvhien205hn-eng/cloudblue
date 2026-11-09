#!/usr/bin/env python3
# cpapi_setup.py — Cài cổng bảo vệ cpapi.py thành dịch vụ chạy 24/7 + chuyển tunnel phone.blueroblox.shop sang cổng 8010.
# Chạy:  sudo python3 ~/cpapi_setup.py            Quay lại như cũ:  sudo python3 ~/cpapi_setup.py --undo
import os, re, shutil, subprocess, sys, time, glob, pwd

TUNNEL_SVC = "cloudflared-phone"
OLD, NEW = "8000", "8010"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def say(*a):
    print(*a, flush=True)


if os.geteuid() != 0:
    say("Hãy chạy bằng sudo:  sudo python3 ~/cpapi_setup.py"); sys.exit(1)

user = os.environ.get("SUDO_USER") or "lehien"
home = pwd.getpwnam(user).pw_dir
undo = "--undo" in sys.argv

# ---------- 1) Tìm file cấu hình tunnel ----------
unit = sh(f"systemctl cat {TUNNEL_SVC}").stdout
if not unit:
    say(f"✗ Không thấy dịch vụ {TUNNEL_SVC}. Gõ: systemctl list-units | grep cloudflared  rồi gửi kết quả."); sys.exit(1)
execs = [l for l in unit.splitlines() if l.strip().startswith("ExecStart=") and l.strip() != "ExecStart="]
exec_line = execs[-1] if execs else ""
m = re.search(r"--config[ =](\S+)", exec_line)
cands = [m.group(1)] if m else []
cands += [f"{home}/.cloudflared/config.yml", f"{home}/.cloudflared/config.yaml", "/etc/cloudflared/config.yml",
          "/etc/cloudflared/config.yaml", "/root/.cloudflared/config.yml", "/usr/local/etc/cloudflared/config.yml"]
cfg = next((c for c in cands if os.path.isfile(c) and re.search(r"(localhost|127\.0\.0\.1):(8000|8010)", open(c).read())), None)
unit_path = None
if not cfg and re.search(r"--url\s+\S*:(8000|8010)", exec_line):
    unit_path = sh(f"systemctl show -p FragmentPath {TUNNEL_SVC}").stdout.strip().split("=", 1)[-1]
if not cfg and not unit_path:
    say("✗ Không tìm thấy cấu hình tunnel trên máy (có thể tunnel được quản lý trên trang Cloudflare).")
    say("  Vào https://one.dash.cloudflare.com → Networks → Tunnels → chọn tunnel → Public Hostname")
    say(f"  → sửa phone.blueroblox.shop: Service = http://localhost:{NEW if not undo else OLD}  → Save.")
    say("  Dòng chạy tunnel hiện tại:", exec_line.strip())
    if undo: sys.exit(0)

target = cfg or unit_path
a, b = (NEW, OLD) if undo else (OLD, NEW)

# ---------- 2) Cài / gỡ dịch vụ cpapi ----------
svc = "/etc/systemd/system/cpapi.service"
if undo:
    sh("systemctl disable --now cpapi")
    say("• Đã tắt dịch vụ cpapi.")
else:
    if not os.path.isfile(f"{home}/cpapi.py"):
        say(f"✗ Chưa có {home}/cpapi.py — tải về trước (lệnh curl trong hướng dẫn)."); sys.exit(1)
    open(svc, "w").write(f"""[Unit]
Description=Cloud Phone API + cong bao ve ws-scrcpy
After=network-online.target docker.service
Wants=network-online.target

[Service]
User={user}
WorkingDirectory={home}
ExecStart=/usr/bin/python3 -u {home}/cpapi.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
""")
    sh("systemctl daemon-reload")
    sh("systemctl enable cpapi")
    sh("systemctl restart cpapi")
    time.sleep(2)
    code = sh(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{NEW}/").stdout.strip()
    if code not in ("200", "301", "302", "304"):
        say("✗ cpapi chưa chạy được (mã", code + "). Xem lỗi:  sudo journalctl -u cpapi -n 30 --no-pager"); sys.exit(1)
    say(f"✓ Dịch vụ cpapi đang chạy (cổng {NEW}).")

# ---------- 3) Chuyển tunnel ----------
if target:
    txt = open(target).read()
    new = re.sub(rf"((?:localhost|127\.0\.0\.1):){a}\b", rf"\g<1>{b}", txt)
    if new != txt:
        bak = target + ".bak-" + time.strftime("%Y%m%d%H%M%S")
        shutil.copy2(target, bak)
        open(target, "w").write(new)
        say(f"✓ Đã sửa {target}: cổng {a} → {b}  (bản sao lưu: {bak})")
        if unit_path: sh("systemctl daemon-reload")
    else:
        say(f"• {target} đã dùng cổng {b} sẵn.")
    r = sh(f"systemctl restart {TUNNEL_SVC}")
    time.sleep(4)
    st = sh(f"systemctl is-active {TUNNEL_SVC}").stdout.strip()
    say(f"✓ Đã khởi động lại tunnel: {st}" if st == "active" else f"✗ Tunnel không chạy ({st}). Xem: sudo journalctl -u {TUNNEL_SVC} -n 30 --no-pager")

say("\nXONG." + (" Đã quay về như cũ." if undo else " Khách giờ chỉ mở được máy của mình qua trang blueroblox.shop."))
