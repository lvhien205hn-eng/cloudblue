#!/usr/bin/env bash
# =====================================================================
#  cloudphone-gpu.sh — BẬT "MÁY GPU": máy Android 11 mới tự chạy bằng card NVIDIA (GTX 1080) khi card còn chỗ
#    • Card vẽ hình thay CPU → game 3D (Roblox…) mượt hơn, CPU server nhẹ hẳn
#    • Card đầy (mặc định 8 máy) → máy mới tự tạo kiểu thường (vẽ bằng CPU) như trước. Khách không phải chọn gì.
#    • Máy GPU chạy như dịch vụ hệ thống cloudgpu@TÊN: server khởi động lại → tự bật lại; cập nhật phần mềm không làm tắt máy.
#
#  Cần trước: đã chạy  bash ~/gpu-phone-test.sh install  (Android SDK + Android 11 + màn hình ảo trên GTX 1080)
#
#   sudo bash cloudphone-gpu.sh install [SỐ_MÁY]   # bật (mặc định 8 máy GPU)
#   bash cloudphone-gpu.sh test                    # tạo 1 máy GPU thử tên 'gputry' (4 nhân · 4GB) để xem trước
#   bash cloudphone-gpu.sh untest                  # xoá máy thử 'gputry'
#   bash cloudphone-gpu.sh status                  # xem số máy GPU / bộ nhớ card
#   sudo bash cloudphone-gpu.sh off                # tắt: máy mới quay về kiểu thường (máy GPU đang có vẫn chạy)
# =====================================================================
set -u
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
U=${SUDO_USER:-$USER}; H=$(eval echo "~$U"); CONF="$H/cloudphone.conf"
conf_set() { touch "$CONF"; grep -v "^$1=" "$CONF" > "$CONF.tmp"; [ -n "$2" ] && echo "$1=$2" >> "$CONF.tmp"; cat "$CONF.tmp" > "$CONF"; rm -f "$CONF.tmp"; chown "$U": "$CONF" 2>/dev/null; chmod 600 "$CONF"; }
need_root() { [ "$(id -u)" = 0 ] || { err "Chạy bằng sudo:  sudo bash $0 $*"; exit 1; }; }
PC="python3 $H/phonectl.py"

case "${1:-}" in
install)
  need_root install
  NUM=${2:-8}
  [ -x "$H/android-sdk/emulator/emulator" ] || { err "Chưa có Android SDK. Chạy trước:  bash ~/gpu-phone-test.sh install"; exit 1; }
  ls "$H/android-sdk/system-images/android-30/google_apis_playstore/x86_64" >/dev/null 2>&1 || { err "Chưa có Android 11 (GPU). Chạy:  bash ~/gpu-phone-test.sh install"; exit 1; }
  systemctl is-active -q cloudgpu-x || systemctl restart cloudgpu-x
  [ -S /tmp/.X11-unix/X9 ] && ok "Màn hình ảo trên GTX 1080 đang chạy" || { err "Màn hình ảo :9 chưa chạy — chạy:  bash ~/gpu-phone-test.sh xsetup"; exit 1; }
  grep -q "def cmd_gpurun" "$H/phonectl.py" || { err "phonectl.py trên server chưa phải bản mới — chạy:  cloudphone update"; exit 1; }

  cat > /etc/systemd/system/cloudgpu@.service <<EOF
[Unit]
Description=Cloud Phone GPU %i (Android Emulator tren GTX 1080)
After=cloudgpu-x.service network-online.target
Wants=cloudgpu-x.service
[Service]
User=$U
Group=$U
SupplementaryGroups=kvm
WorkingDirectory=$H
ExecStart=/usr/bin/python3 $H/phonectl.py gpurun %i
Restart=on-failure
RestartSec=10
TimeoutStopSec=25
KillMode=mixed
EOF
  systemctl daemon-reload && ok "Dịch vụ máy GPU (cloudgpu@)"

  # cho phép phần mềm quản lý máy (chạy bằng user $U) bật/tắt máy GPU mà không cần mật khẩu — CHỈ đúng 3 lệnh này
  printf '%s\n' "$U ALL=(root) NOPASSWD: /usr/bin/systemctl start cloudgpu@*, /usr/bin/systemctl stop cloudgpu@*, /usr/bin/systemctl restart cloudgpu@*" > /etc/sudoers.d/cloudgpu
  chmod 440 /etc/sudoers.d/cloudgpu
  visudo -cf /etc/sudoers.d/cloudgpu >/dev/null && ok "Quyền bật/tắt máy GPU" || { rm -f /etc/sudoers.d/cloudgpu; err "Lỗi quyền sudo"; exit 1; }

  conf_set GPU_PHONES "$NUM"
  systemctl restart cloudphoned cpapi 2>/dev/null && ok "Đã khởi động lại cloudphoned + cpapi"
  ok "BẬT MÁY GPU: tối đa $NUM máy Android 11 mới sẽ chạy bằng GTX 1080"
  echo "   Thử trước:  bash $0 test" ;;

test)
  [ "$(id -u)" = 0 ] && { err "Chạy bằng user thường (không sudo):  bash $0 test"; exit 1; }
  echo "== Tạo máy GPU thử 'gputry' (4 nhân · 4GB · 720x1280) — 1–3 phút =="
  $PC create gputry --ram 4 --cpu 4 --days 1 --res 720x1280 --fps 30 --android 11
  $PC list | grep -E "gputry|TÊN"
  $PC list | grep -q "gputry ⚡" && ok "Là MÁY GPU ⚡" || warn "Máy thử KHÔNG phải máy GPU (card chưa bật? chạy: sudo bash $0 install)"
  P=$(python3 -c "import json;print(next((p['port'] for p in json.load(open('$H/redroid/phones.json'))['phones'] if p['name']=='gputry'),''))" 2>/dev/null)
  echo "   Xem màn hình: https://phone.blueroblox.shop/ (admin) → thiết bị 127.0.0.1:${P:-?}"
  echo "   Xoá máy thử khi xong:  bash $0 untest" ;;

untest)
  $PC delete gputry ;;

status)
  $PC gpuinfo
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader | sed 's/^/   Card: dùng %, bộ nhớ, nhiệt độ → /' ;;

off)
  need_root off
  conf_set GPU_PHONES 0
  systemctl restart cloudphoned cpapi 2>/dev/null
  ok "Đã tắt: máy mới tạo kiểu thường. Máy GPU đang có vẫn chạy bình thường đến khi hết hạn." ;;

*) sed -n '2,15p' "$0" ;;
esac
