#!/bin/bash
# CloudBlue - LAN BAT DAU cua may chu Proxmox cai bang ISO CloudBlue-Proxmox (ban @@VER@@).
# Proxmox tu chay file nay DUNG 1 LAN (quyen root, khi may da len du - dich vu proxmox-first-boot). pve_iso.py dien cac cho @@...@@ luc ghep ISO.
#   1. cbhost  (dich vu cloudblue-cbhost): may chu tu len web CloudBlue (cho admin bam DUYET), tu cap nhat, tu dung may mau tu ISO may mau (auto_tpl).
#   2. cb_nap  (dich vu cloudblue-nap): chep kho ISO may mau tu USB cai dat vao kho ISO cua Proxmox (rut USB som thi cam lai luc nao cung duoc).
# Khong chua khoa bi mat nao. Nhat ky: /var/log/cloudblue-firstboot.log
LOG=/var/log/cloudblue-firstboot.log
exec >> "$LOG" 2>&1
echo "== $(date '+%F %T') CloudBlue first-boot ban @@VER@@ (${1:-})"
DIR=/opt/cloudblue
ETC=/etc/cloudblue
VAR=/var/lib/cloudblue
mkdir -p "$DIR" "$ETC" "$VAR"
chmod 700 "$ETC" "$VAR"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then echo "LOI: may khong co python3 - khong cai duoc cbhost"; exit 0; fi

put() {   # put <duong dan> <quyen> : noi dung (base64) doc tu stdin
  local rc
  base64 -d > "$1.tmp" && [ -s "$1.tmp" ] && install -m "$2" "$1.tmp" "$1"
  rc=$?
  rm -f "$1.tmp"
  [ $rc -eq 0 ] || echo "LOI: khong ghi duoc $1"
  return $rc
}

put "$DIR/cbhost.py" 755 <<'CB_B64_EOF'
@@CBHOST_B64@@
CB_B64_EOF
put "$DIR/cb_nap.py" 755 <<'CB_B64_EOF'
@@NAP_B64@@
CB_B64_EOF
put "$ETC/nap.json" 600 <<'CB_B64_EOF'
@@NAPCONF_B64@@
CB_B64_EOF
if [ ! -s "$ETC/cbhost.conf" ]; then
put "$ETC/cbhost.conf" 600 <<'CB_B64_EOF'
@@CONF_B64@@
CB_B64_EOF
fi

for f in cbhost.py cb_nap.py; do
  "$PY" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$DIR/$f" || echo "LOI: $f hong"
done

# Ten rieng cua may chu tren web: may dat ten mac dinh (cbvps) -> them 4 ky tu cuoi dia chi MAC de cac may cai cung 1 ISO khong trung ten.
MAC=$(cat /sys/class/net/vmbr0/address 2>/dev/null || true)
"$PY" - "$ETC/cbhost.conf" "$(hostname -s 2>/dev/null || hostname)" "$MAC" <<'CB_PY_EOF'
import json, re, sys
p, host, mac = sys.argv[1:4]
try:
    c = json.load(open(p))
    if not isinstance(c, dict): c = {}
except Exception:
    c = {}
suf = re.sub(r"[^0-9a-f]", "", (mac or "").lower())[-4:]
if not c.get("host_name") and host == "cbvps" and len(suf) == 4:
    c["host_name"] = "cbvps-" + suf
json.dump(c, open(p, "w"))
print("cau hinh cbhost:", json.dumps({k: v for k, v in c.items() if k != "sb_key"}))
CB_PY_EOF
chmod 600 "$ETC/cbhost.conf"

cat > /etc/systemd/system/cloudblue-cbhost.service <<UNITEOF
[Unit]
Description=CloudBlue cbhost - VPS ao hoa (Proxmox)
After=network-online.target pve-cluster.service pvedaemon.service
Wants=network-online.target

[Service]
ExecStart=$PY $DIR/cbhost.py run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
UNITEOF
cat > /etc/systemd/system/cloudblue-nap.service <<UNITEOF
[Unit]
Description=CloudBlue - nap kho ISO may mau tu USB cai dat
After=local-fs.target pve-storage.target
ConditionPathExists=!$VAR/nap-xong.json

[Service]
ExecStart=$PY $DIR/cb_nap.py run
Restart=on-failure
RestartSec=30
Environment=PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
UNITEOF
systemctl daemon-reload
systemctl enable cloudblue-cbhost cloudblue-nap
systemctl start --no-block cloudblue-nap
systemctl restart --no-block cloudblue-cbhost
[ -e /dev/kvm ] || echo "CANH BAO: khong thay /dev/kvm - bat ao hoa (Intel VT-x / AMD-V) trong BIOS, khong thi may ao chay rat cham."
echo "== $(date '+%F %T') xong first-boot: cbhost $("$PY" "$DIR/cbhost.py" version 2>/dev/null) | cb_nap $("$PY" "$DIR/cb_nap.py" version 2>/dev/null)"
exit 0
