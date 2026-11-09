#!/usr/bin/env bash
# =====================================================================
#  cloudphone-tune — tối ưu máy chủ Cloud Phone (blueroblox)
#   1) zram: RAM nén (nhanh gần bằng RAM thật) — dùng trước
#   2) swap trên ổ cứng: lấy hết chỗ trống, CHỪA LẠI 200GB cho máy khách — dùng sau zram
#   3) CPU chạy hết công suất (performance), không tự hạ xung
#   4) thông số nhân Linux hợp cho nhiều máy Android
#  Cài:   sudo bash cloudphone-tune.sh install    (tự chạy lại mỗi lần bật máy)
#  Chạy:  sudo cloudphone-tune     ·  Đổi số GB chừa lại:  KEEP_GB=300 sudo cloudphone-tune
# =====================================================================
KEEP_GB=${KEEP_GB:-200}          # chừa lại cho dữ liệu máy khách
MAX_SWAP_GB=${MAX_SWAP_GB:-512}  # swap ổ cứng tối đa
SWAPFILE=/swapfile-cloud
SELF=/usr/local/sbin/cloudphone-tune
G='\033[1;32m'; Y='\033[1;33m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }

if [ "$(id -u)" != "0" ]; then echo "Hãy chạy bằng sudo"; exit 1; fi

if [ "${1:-}" = "install" ]; then
  [ "$(readlink -f "$0")" != "$SELF" ] && cp "$0" "$SELF"; chmod 755 "$SELF"
  cat > /etc/systemd/system/cloudphone-tune.service <<EOF
[Unit]
Description=Cloud Phone - toi uu may chu (zram, swap, CPU)
After=local-fs.target
Before=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
Environment=KEEP_GB=$KEEP_GB
ExecStart=$SELF
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload; systemctl enable cloudphone-tune.service >/dev/null 2>&1
  ok "Đã cài: tự tối ưu mỗi lần máy chủ khởi động"
  exec "$SELF"
fi

RAM_GB=$(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo)

# ---------- 1) zram ----------
ZGB=$(( RAM_GB / 4 )); [ "$ZGB" -gt 64 ] && ZGB=64; [ "$ZGB" -lt 2 ] && ZGB=2
if swapon --show=NAME --noheadings | grep -q '^/dev/zram0'; then
  ok "zram đang bật ($(swapon --show=SIZE --noheadings /dev/zram0 | tr -d ' '))"
elif modprobe zram num_devices=1 2>/dev/null && [ -e /sys/block/zram0 ]; then
  echo 1 > /sys/block/zram0/reset 2>/dev/null
  for a in zstd lz4 lzo-rle lzo; do grep -qw "$a" /sys/block/zram0/comp_algorithm && { echo "$a" > /sys/block/zram0/comp_algorithm; break; }; done
  echo "${ZGB}G" > /sys/block/zram0/disksize && mkswap /dev/zram0 >/dev/null && swapon -p 100 /dev/zram0 \
    && ok "zram ${ZGB}GB ($(cat /sys/block/zram0/comp_algorithm | grep -o '\[[a-z0-9-]*\]' | tr -d '[]')) — dùng trước" \
    || warn "Không bật được zram"
else
  warn "Nhân Linux không có zram — bỏ qua (cài: sudo apt install linux-modules-extra-\$(uname -r))"
fi

# ---------- 2) swap trên ổ cứng ----------
ROTA=$(lsblk -ndo ROTA "$(findmnt -no SOURCE /)" 2>/dev/null | tr -dc 01); ROTA=${ROTA:-0}     # 1 = HDD, 0 = SSD
CUR_GB=0; [ -f "$SWAPFILE" ] && CUR_GB=$(( $(stat -c %s "$SWAPFILE") / 1073741824 ))
AVAIL_GB=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
WANT=$(( AVAIL_GB + CUR_GB - KEEP_GB ))
[ "$WANT" -gt "$MAX_SWAP_GB" ] && WANT=$MAX_SWAP_GB
if [ "$ROTA" = "1" ] && [ "$WANT" -gt 32 ]; then WANT=32; warn "Ổ cứng là HDD (chậm) → swap ổ cứng giới hạn 32GB"; fi
if [ "$WANT" -lt 4 ]; then
  warn "Ổ cứng không đủ chỗ (trống ${AVAIL_GB}GB, phải chừa ${KEEP_GB}GB) — giữ swap hiện tại ${CUR_GB}GB"
elif [ "$CUR_GB" -ge $(( WANT * 9 / 10 )) ] && [ "$CUR_GB" -le $(( WANT + 8 )) ] && swapon --show=NAME --noheadings | grep -qx "$SWAPFILE"; then
  ok "Swap ổ cứng ${CUR_GB}GB (đã đúng) — chừa ổ trống ~$(df -BG --output=avail / | tail -1 | tr -d ' ')"
else
  if swapon --show=NAME --noheadings | grep -qx "$SWAPFILE" && ! swapoff "$SWAPFILE"; then
    warn "Swap cũ đang được dùng, chưa đổi kích thước được — giữ ${CUR_GB}GB, chạy lại lúc ít máy"
  else
  rm -f "$SWAPFILE"
  if fallocate -l "${WANT}G" "$SWAPFILE" 2>/dev/null || dd if=/dev/zero of="$SWAPFILE" bs=1G count="$WANT" status=none; then
    chmod 600 "$SWAPFILE"; mkswap "$SWAPFILE" >/dev/null && swapon -p 10 "$SWAPFILE" \
      && ok "Swap ổ cứng ${WANT}GB — ổ còn trống ~$(df -BG --output=avail / | tail -1 | tr -d ' ') cho máy khách" \
      || warn "Không bật được swap ổ cứng"
  else warn "Không tạo được file swap ${WANT}GB"; rm -f "$SWAPFILE"; fi
  fi
fi
sed -i '\|swapfile-cloud|d' /etc/fstab          # bật bằng dịch vụ này (đúng thứ tự ưu tiên), không qua fstab

# ---------- 3) CPU hết công suất ----------
n=0; for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [ -w "$g" ] && grep -qw performance "${g%/*}/scaling_available_governors" 2>/dev/null && echo performance > "$g" && n=$((n+1))
done
for e in /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference; do [ -w "$e" ] && echo performance > "$e" 2>/dev/null; done
[ "$n" -gt 0 ] && ok "CPU: chế độ performance ($n nhân)" || ok "CPU: không có điều chỉnh xung (máy chủ/BIOS tự quản) — bỏ qua"

# ---------- 4) nhân Linux ----------
cat > /etc/sysctl.d/99-cloudphone.conf <<EOF
# dùng RAM thật trước, đầy mới sang zram rồi ổ cứng
vm.swappiness=10
# zram: đọc từng trang, không đọc trước
vm.page-cluster=0
vm.vfs_cache_pressure=50
# nhiều máy Android mở rất nhiều file / tiến trình
fs.inotify.max_user_watches=1048576
fs.inotify.max_user_instances=8192
fs.file-max=4194304
kernel.pid_max=4194304
vm.max_map_count=1048576
EOF
sysctl -q --system >/dev/null 2>&1 && ok "Thông số nhân Linux"
[ -w /sys/kernel/mm/transparent_hugepage/enabled ] && echo madvise > /sys/kernel/mm/transparent_hugepage/enabled

echo; swapon --show; free -h | head -2
