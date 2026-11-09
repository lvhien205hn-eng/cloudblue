#!/usr/bin/env bash
# =====================================================================
#  cloudphone-watchdog — "người gác" máy chủ Cloud Phone (blueroblox)
#  Chạy mỗi 1 phút (và 1 phút sau khi bật máy). Tự phát hiện và tự sửa:
#    docker tắt · binder/tun chưa nạp · ws-scrcpy (phát hình) chết/treo
#    cpapi / cloudphoned tắt hoặc treo · tunnel Cloudflare rớt
#  Cài:      sudo bash cloudphone-watchdog.sh install
#  Xem log:  cloudphone watch      (hoặc: tail -50 /var/log/cloudphone-watchdog.log)
# =====================================================================
LOG=/var/log/cloudphone-watchdog.log
ST=/run/cloudphone-watchdog
WS=wsscrcpy
SELF=/usr/local/sbin/cloudphone-watchdog

log() { echo "$(date '+%F %T') $*" >> "$LOG"; echo "$*"; }
# đếm số lần lỗi liên tiếp (tránh khởi động lại vì trục trặc 1 giây)
bad()  { local n; n=$(( $(cat "$ST/$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$ST/$1"; echo "$n"; }
good() { rm -f "$ST/$1"; }
has_unit() { systemctl list-unit-files --no-legend "$1.service" 2>/dev/null | grep -q "^$1.service"; }

if [ "$(id -u)" != "0" ]; then echo "Hãy chạy bằng sudo"; exit 1; fi

# ---------------------------------------------------------------- cài đặt
if [ "${1:-}" = "install" ]; then
  [ "$(readlink -f "$0")" != "$SELF" ] && cp "$0" "$SELF"
  chmod 755 "$SELF"
  cat > /etc/systemd/system/cloudphone-watchdog.service <<EOF
[Unit]
Description=Cloud Phone watchdog (tu kiem tra va tu sua)
After=network-online.target docker.service
[Service]
Type=oneshot
ExecStart=$SELF
EOF
  cat > /etc/systemd/system/cloudphone-watchdog.timer <<EOF
[Unit]
Description=Cloud Phone watchdog moi 1 phut
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  # mọi dịch vụ đều tự bật khi khởi động máy
  for s in docker cpapi cloudphoned cloudflared-phone cloudflared; do has_unit "$s" && systemctl enable "$s" >/dev/null 2>&1; done
  printf 'binder_linux\nashmem_linux\n' > /etc/modules-load.d/redroid.conf      # ashmem: Chrome / WebView trong máy cần
  echo tun > /etc/modules-load.d/tun.conf
  docker update --restart unless-stopped "$WS" >/dev/null 2>&1
  systemctl enable --now cloudphone-watchdog.timer >/dev/null 2>&1
  touch "$LOG"
  echo "✓ Đã cài watchdog: tự kiểm tra mỗi 1 phút, tự chạy lại khi máy khởi động"
  "$SELF"
  exit 0
fi

mkdir -p "$ST"
[ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 2000000 ] && tail -2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fixed=0

# 1) docker
if ! systemctl is-active -q docker; then log "docker đang tắt → bật lại"; systemctl restart docker; sleep 8; fixed=1; fi

# 2) binder (Android cần) + tun (VPN trong máy cần)
if ! lsmod | grep -qE '^binder(_linux)?\b'; then
  log "binder chưa nạp → nạp lại"; modprobe binder_linux devices=binder,hwbinder,vndbinder 2>>"$LOG"; fixed=1
fi
lsmod | grep -qw '^tun' || modprobe tun 2>/dev/null
[ -e /dev/ashmem ] || modprobe ashmem_linux 2>/dev/null

# 3) ws-scrcpy (phát hình cho trang điều khiển)
s=$(docker inspect -f '{{.State.Status}}' "$WS" 2>/dev/null)
if [ -z "$s" ]; then
  log "! không thấy container $WS — chạy lại: sudo bash ~/cloudphone-setup.sh"
elif [ "$s" != "running" ]; then
  log "ws-scrcpy đang '$s' → bật lại"; docker start "$WS" >/dev/null 2>&1; good ws; fixed=1
elif curl -s -m 6 -o /dev/null http://127.0.0.1:8000/; then good ws
elif [ "$(bad ws)" -ge 2 ]; then
  log "ws-scrcpy không trả lời 2 lần liền → khởi động lại"; docker restart "$WS" >/dev/null 2>&1; good ws; fixed=1
fi

# 4) cpapi + cloudphoned
for s in cpapi cloudphoned; do
  has_unit "$s" || continue
  if ! systemctl is-active -q "$s"; then log "$s đang tắt → bật lại"; systemctl restart "$s"; good "$s"; fixed=1; fi
done
if has_unit cpapi && systemctl is-active -q cpapi; then
  if curl -s -m 6 -o /dev/null http://127.0.0.1:8010/; then good cpapi_http
  elif [ "$(bad cpapi_http)" -ge 2 ]; then log "cpapi bị treo (không trả lời) → khởi động lại"; systemctl restart cpapi; good cpapi_http; fixed=1; fi
fi

# 5) tunnel Cloudflare: dịch vụ phải chạy + từ ngoài internet vào được trang điều khiển
TUN=""; for s in cloudflared-phone cloudflared; do has_unit "$s" && TUN="$TUN $s"; done
for s in $TUN; do
  systemctl is-enabled -q "$s" 2>/dev/null || continue
  if ! systemctl is-active -q "$s"; then log "$s đang tắt → bật lại"; systemctl restart "$s"; good tunnel; fixed=1; fi
done
CONF=$(ls /home/*/cloudphone.conf /root/cloudphone.conf 2>/dev/null | head -1)
PUB=$(grep -s '^PUBLIC_BASE=' "$CONF" | cut -d= -f2-); PUB=${PUB:-https://phone.blueroblox.shop}
if [ -n "$TUN" ]; then
  code=$(curl -s -m 12 -o /dev/null -w '%{http_code}' "$PUB/__cp/inject.js")
  if [ "$code" = "200" ]; then good tunnel
  elif ! curl -s -m 8 -o /dev/null https://1.1.1.1; then :     # mất mạng internet → khởi động lại tunnel cũng vô ích
  elif [ "$(bad tunnel)" -ge 3 ]; then
    log "Từ internet không vào được $PUB (mã $code) 3 lần liền → khởi động lại tunnel"
    for s in $TUN; do systemctl is-enabled -q "$s" 2>/dev/null && systemctl restart "$s"; done; good tunnel; fixed=1
  fi
fi

# 6) máy Android bị kẹt ở trạng thái "restarting" quá lâu (thường do binder nạp sau docker lúc vừa bật máy)
for c in $(docker ps -a --filter status=restarting --format '{{.Names}}' | grep -E '^cp_|^test'); do
  if [ "$(bad "rs_$c")" -ge 3 ]; then log "$c kẹt khởi động → chạy lại"; docker restart "$c" >/dev/null 2>&1; good "rs_$c"; fixed=1; fi
done

# 6b) máy Android 9/10/11 KHÔNG thấy /dev/ashmem (máy bật TRƯỚC khi server nạp ashmem) → mọi app/Chrome/game văng khi bấm.
#     Android 12+ dùng memfd nên không bị. Máy thấy thiết bị lúc khởi động → chỉ cần khởi động lại máy đó (dữ liệu giữ nguyên).
if [ -e /dev/ashmem ]; then
  for c in $(docker ps --format '{{.Names}}' | grep -E '^cp_'); do
    v=$(timeout 10 docker exec "$c" getprop ro.build.version.sdk 2>/dev/null | tr -dc 0-9)
    [ -n "$v" ] && [ "$v" -le 30 ] || continue
    timeout 10 docker exec "$c" /system/bin/sh -c 'test -e /dev/ashmem' 2>/dev/null && continue
    log "$c (SDK $v) thiếu /dev/ashmem → app sẽ văng → khởi động lại máy"; docker restart "$c" >/dev/null 2>&1; fixed=1
  done
fi

# 7) máy Android bị treo (chạy > 6 phút mà Android không lên / mất màn hình) → 3 phút liền thì tự khởi động lại máy đó
now=$(date +%s)
for c in $(docker ps --format '{{.Names}}' | grep -E '^cp_'); do
  st=$(date -d "$(docker inspect -f '{{.State.StartedAt}}' "$c" 2>/dev/null)" +%s 2>/dev/null || echo "$now")
  [ $((now - st)) -lt 360 ] && { good "hang_$c"; continue; }
  okb=$(timeout 15 docker exec "$c" /system/bin/sh -c 'getprop sys.boot_completed; pidof surfaceflinger >/dev/null && echo SF; pidof system_server >/dev/null && echo SS' 2>/dev/null | tr -d '\r' | tr '\n' ' ')
  if [[ "$okb" == 1*SF*SS* ]]; then good "hang_$c"
  elif [ "$(bad "hang_$c")" -ge 3 ]; then log "$c bị treo (Android: '${okb:-không phản hồi}') 3 phút liền → khởi động lại máy"; docker restart "$c" >/dev/null 2>&1; good "hang_$c"; fixed=1; fi
done

# 8) đường thẳng (fast-route.sh): nginx cổng 8443 phải chạy
if [ -f /etc/nginx/conf.d/cloudphone-fast.conf ]; then
  if ! systemctl is-active -q nginx; then log "nginx (đường thẳng) đang tắt → bật lại"; systemctl restart nginx; fixed=1; fi
fi

# 9) ưu tiên luồng hình: khi game nặng (Roblox…) ngốn hết CPU, phần vẽ màn hình + nén hình + nhận chạm vẫn được chạy trước
#    → khách điều khiển vẫn mượt, game chỉ giảm FPS một chút. Đặt độ ưu tiên -10 cho mọi luồng của các tiến trình này.
python3 - <<'PYEOF'
import os
HIGH = (b"com.genymobile.scrcpy", b"android.hardware.media.omx", b"media.swcodec", b"mediaswcodec")   # gửi hình + nén hình + nhận chạm
LOW = (b"com.roblox",)                                                                               # game nặng: nhường CPU cho luồng hình
nh = nl = 0
for pid in os.listdir("/proc"):
    if not pid.isdigit(): continue
    try: cl = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[0:3]
    except OSError: continue
    cl = b" ".join(cl)
    want = -10 if any(p in cl for p in HIGH) else 8 if any(cl.startswith(p) for p in LOW) else None
    if want is None: continue
    try: tids = os.listdir(f"/proc/{pid}/task")
    except OSError: continue
    for t in tids:
        try:
            if os.getpriority(os.PRIO_PROCESS, int(t)) != want:
                os.setpriority(os.PRIO_PROCESS, int(t), want)
                if want < 0: nh += 1
                else: nl += 1
        except OSError: pass
if nh or nl: print(f"ưu tiên luồng hình: +{nh} luồng lên trước, {nl} luồng game nhường")
PYEOF

[ "$fixed" = 0 ] && echo "✓ Mọi thứ bình thường"
exit 0
