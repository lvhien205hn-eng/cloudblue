#!/usr/bin/env bash
# CloudBlue — cài cbhost (VPS ảo hoá) lên MÁY CHỦ PROXMOX VE. Dán vào Shell của Proxmox (đăng nhập root):
#   bash <(curl -fsSL https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/proxmox/cai-cbhost.sh)
# Chạy lại lúc nào cũng được = cập nhật bản mới (giữ nguyên mã riêng của máy + sổ máy ảo). Bình thường cbhost tự cập nhật 1 giờ / lần.
# Không hỏi / không cần khoá bí mật nào: máy tự sinh mã riêng (chỉ nằm trên máy), web chỉ giữ dấu băm → admin bấm DUYỆT trên web.
set -euo pipefail
REPO="lvhien205hn-eng/cloudblue"
DIR=${CB_DIR:-/opt/cloudblue}
ETC=${CB_ETC:-/etc/cloudblue}
VAR=${CB_VAR:-/var/lib/cloudblue}
UNIT=${CB_UNIT:-/etc/systemd/system/cloudblue-cbhost.service}
say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mLỖI: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "phải chạy bằng root (Shell của Proxmox)"
command -v qm >/dev/null 2>&1 && command -v pvesh >/dev/null 2>&1 || die "máy này không phải Proxmox VE (không có lệnh qm / pvesh)"
[ -e /dev/kvm ] || echo "CẢNH BÁO: không thấy /dev/kvm — bật ảo hoá (Intel VT-x / AMD-V) trong BIOS, không thì máy ảo chạy rất chậm."
if ! command -v python3 >/dev/null 2>&1; then
  say "cài python3"
  apt-get update -o Acquire::Retries=3 || true
  apt-get install -y python3 || die "không cài được python3"
fi
command -v curl >/dev/null 2>&1 || { apt-get install -y curl || die "thiếu curl"; }
PY=$(command -v python3)

say "tải cbhost.py bản mới nhất"
SHA=$(curl -fsSL --max-time 30 "https://api.github.com/repos/$REPO/commits/main" 2>/dev/null \
      | "$PY" -c 'import sys, json; print(json.load(sys.stdin)["sha"])' 2>/dev/null || true)
case "$SHA" in ([0-9a-f]*) REF=$SHA ;; (*) REF=main ;; esac
mkdir -p "$DIR" "$ETC" "$VAR"
chmod 700 "$ETC" "$VAR"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
curl -fsSL --max-time 120 "https://raw.githubusercontent.com/$REPO/$REF/proxmox/cbhost.py" -o "$TMP" || die "không tải được cbhost.py (kiểm tra mạng của máy Proxmox)"
grep -q '^CBHOST_VER = ' "$TMP" && "$PY" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), "cbhost.py", "exec")' "$TMP" \
  || die "file tải về hỏng — chạy lại lệnh"
install -m 755 "$TMP" "$DIR/cbhost.py"
[ -f "$ETC/cbhost.conf" ] || { echo '{}' > "$ETC/cbhost.conf"; chmod 600 "$ETC/cbhost.conf"; }
echo "bản: $("$PY" "$DIR/cbhost.py" version)"

say "tạo dịch vụ cloudblue-cbhost (tự chạy khi bật máy, tự bật lại khi lỗi, tự cập nhật)"
cat > "$UNIT" <<UNITEOF
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
systemctl daemon-reload
systemctl enable cloudblue-cbhost >/dev/null 2>&1
systemctl restart cloudblue-cbhost
sleep 8

say "trạng thái"
"$PY" "$DIR/cbhost.py" status || true
echo
echo "XONG. Bước tiếp: web › Quản trị › 🧩 VPS ảo hoá › Máy chủ → bấm DUYỆT máy này."
echo "Xem nhật ký:   journalctl -u cloudblue-cbhost -f"
echo "Xem trạng thái: python3 $DIR/cbhost.py status"
