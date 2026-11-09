#!/usr/bin/env bash
# =====================================================================
#  fast-route.sh — "ĐƯỜNG THẲNG" cho Cloud Phone (bỏ vòng qua Cloudflare Hồng Kông → bớt trễ khi điều khiển)
#    Khách ở VN  →  fast.blueroblox.shop:8443 (IP nhà mạng FPT)  →  router mở cổng 8443  →  máy chủ 192.168.1.21
#    Không tới được đường thẳng thì trang tự dùng lại phone.blueroblox.shop (Cloudflare) như cũ.
#
#  Cần trước: router đã cố định IP 192.168.1.21 + mở cổng 8443 → 192.168.1.21:8443
#             1 token Cloudflare quyền "Edit zone DNS" cho blueroblox.shop (dán khi script hỏi, không gửi ai)
#
#   sudo bash fast-route.sh install    # cài 1 lần (nginx + chứng chỉ HTTPS + tự cập nhật IP)
#   sudo bash fast-route.sh check      # kiểm tra đường thẳng
#   sudo bash fast-route.sh off        # tắt đường thẳng (khách dùng Cloudflare như cũ)
# =====================================================================
set -u
HOST=fast.blueroblox.shop
ZONE=blueroblox.shop
PORT=8443
UP=127.0.0.1:8010                      # cpapi
ENV=/root/.cloudphone-fast.env         # token Cloudflare (chỉ root đọc được)
SELF=/usr/local/sbin/cloudphone-fast
CERT=/etc/nginx/cloudphone-fast
AC=/root/.acme.sh/acme.sh
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
[ "$(id -u)" = "0" ] || { err "Hãy chạy bằng sudo:  sudo bash $0 ${1:-}"; exit 1; }
U=${SUDO_USER:-$(ls /home | head -1)}; CONF=$(eval echo "~$U")/cloudphone.conf

cf() { curl -s -m 20 -H "Authorization: Bearer $CF_Token" -H "Content-Type: application/json" "$@"; }
myip() { curl -s -m 8 https://1.1.1.1/cdn-cgi/trace | sed -n 's/^ip=//p' | grep -E '^[0-9.]+$' || curl -s -m 8 https://api.ipify.org; }
conf_set() { touch "$CONF"; grep -v "^$1=" "$CONF" > "$CONF.tmp"; [ -n "$2" ] && echo "$1=$2" >> "$CONF.tmp"; cat "$CONF.tmp" > "$CONF"; rm -f "$CONF.tmp"; chown "$U": "$CONF"; chmod 600 "$CONF"; }

ddns() {   # trỏ fast.blueroblox.shop về IP nhà mạng hiện tại (đám mây XÁM — không qua Cloudflare)
  . "$ENV"
  local ip rec cur
  ip=$(myip); [ -n "$ip" ] || { warn "Không đọc được IP nhà mạng (mất mạng?)"; return 1; }
  rec=$(cf "https://api.cloudflare.com/client/v4/zones/$CF_Zone_ID/dns_records?type=A&name=$HOST")
  cur=$(echo "$rec" | python3 -c 'import sys,json; r=json.load(sys.stdin)["result"]; print((r[0]["id"]+" "+r[0]["content"]) if r else "")' 2>/dev/null)
  if [ "${cur#* }" = "$ip" ]; then return 0; fi
  local body="{\"type\":\"A\",\"name\":\"$HOST\",\"content\":\"$ip\",\"ttl\":60,\"proxied\":false}"
  if [ -n "$cur" ]; then r=$(cf -X PUT "https://api.cloudflare.com/client/v4/zones/$CF_Zone_ID/dns_records/${cur%% *}" --data "$body")
  else r=$(cf -X POST "https://api.cloudflare.com/client/v4/zones/$CF_Zone_ID/dns_records" --data "$body"); fi
  if echo "$r" | grep -q '"success":true'; then echo "$(date '+%F %T') $HOST → $ip" >> /var/log/cloudphone-fast.log; ok "$HOST → $ip"
  else err "Cloudflare từ chối cập nhật DNS: $(echo "$r" | head -c 300)"; return 1; fi
}

case "${1:-}" in
install)
  [ "$(readlink -f "$0")" != "$SELF" ] && cp "$0" "$SELF"; chmod 755 "$SELF"
  echo "== 1) Token Cloudflare =="
  if [ -f "$ENV" ] && . "$ENV" && [ -n "${CF_Token:-}" ] && [ -n "${CF_Zone_ID:-}" ]; then ok "Đã có token (muốn nhập lại: sudo rm $ENV)"
  else
    echo "   Dán token Cloudflare (quyền Zone → DNS → Edit cho $ZONE). Chữ sẽ KHÔNG hiện ra khi dán, dán xong bấm Enter:"
    read -rs CF_Token; echo
    CF_Token=$(echo "$CF_Token" | tr -d ' \r\n')
    v=$(cf https://api.cloudflare.com/client/v4/user/tokens/verify)
    echo "$v" | grep -q '"status":"active"' || { err "Token không hợp lệ: $(echo "$v" | head -c 200)"; exit 1; }
    CF_Zone_ID=$(cf "https://api.cloudflare.com/client/v4/zones?name=$ZONE" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result") or []; print(r[0]["id"] if r else "")' 2>/dev/null)
    if [ -z "$CF_Zone_ID" ]; then
      echo "   Token không đọc được Zone ID. Mở Cloudflare → $ZONE → trang Overview, cột bên phải mục 'Zone ID' → copy, dán vào đây:"
      read -r CF_Zone_ID; CF_Zone_ID=$(echo "$CF_Zone_ID" | tr -d ' \r\n')
    fi
    umask 077; printf 'CF_Token=%s\nCF_Zone_ID=%s\n' "$CF_Token" "$CF_Zone_ID" > "$ENV"; chmod 600 "$ENV"
    ok "Đã lưu token vào $ENV (chỉ root đọc được)"
  fi
  . "$ENV"; export CF_Token CF_Zone_ID

  echo "== 2) Trỏ tên miền $HOST về IP nhà mạng =="
  ddns || exit 1

  echo "== 3) Phần mềm =="
  apt-get install -y -qq nginx curl git >/dev/null && ok "nginx"
  if [ ! -x "$AC" ]; then
    rm -rf /tmp/acme.sh && git clone -q --depth 1 https://github.com/acmesh-official/acme.sh /tmp/acme.sh \
      && (cd /tmp/acme.sh && ./acme.sh --install --home /root/.acme.sh --nocron >/dev/null) && ok "acme.sh (chứng chỉ HTTPS miễn phí)" || { err "Không cài được acme.sh"; exit 1; }
  fi
  "$AC" --set-default-ca --server letsencrypt >/dev/null

  echo "== 4) Chứng chỉ HTTPS cho $HOST (Let's Encrypt, xác minh qua DNS — 1–2 phút) =="
  mkdir -p "$CERT"
  "$AC" --issue --dns dns_cf -d "$HOST" --keylength ec-256 > /var/log/cloudphone-fast-acme.log 2>&1; rc=$?
  [ $rc = 0 ] || [ $rc = 2 ] || { err "Lấy chứng chỉ lỗi — xem: sudo tail -30 /var/log/cloudphone-fast-acme.log"; exit 1; }
  "$AC" --install-cert -d "$HOST" --ecc --key-file "$CERT/key.pem" --fullchain-file "$CERT/full.pem" --reloadcmd "systemctl reload nginx" >/dev/null 2>&1
  [ -s "$CERT/full.pem" ] && ok "Có chứng chỉ HTTPS" || { err "Chưa có chứng chỉ"; exit 1; }

  echo "== 5) nginx cổng $PORT → cpapi =="
  cat > /etc/nginx/conf.d/cloudphone-fast.conf <<EOF
# Đường thẳng Cloud Phone: https://$HOST:$PORT → cpapi ($UP). Do fast-route.sh tạo.
map \$http_upgrade \$cp_conn { default upgrade; '' close; }
server {
    listen $PORT ssl;
    server_name $HOST;
    ssl_certificate     $CERT/full.pem;
    ssl_certificate_key $CERT/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:cpfast:10m;
    ssl_session_timeout 1d;
    client_max_body_size 0;
    location / {
        proxy_pass http://$UP;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$cp_conn;
        proxy_set_header Host \$host:\$server_port;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;            # hình đi thẳng, không gom lại → bớt trễ
        proxy_request_buffering off;
        proxy_read_timeout 1d;
        proxy_send_timeout 1d;
        tcp_nodelay on;
    }
}
EOF
  nginx -t >/dev/null 2>&1 || { err "Cấu hình nginx lỗi:"; nginx -t; exit 1; }
  systemctl enable nginx >/dev/null 2>&1; systemctl restart nginx && ok "nginx chạy cổng $PORT"
  command -v ufw >/dev/null && ufw status | grep -q "Status: active" && ufw allow $PORT/tcp >/dev/null && ok "Mở tường lửa ufw cổng $PORT"

  echo "== 6) Báo cpapi chấp nhận đường thẳng =="
  conf_set FAST_BASE "https://$HOST:$PORT"
  systemctl restart cpapi && ok "cpapi đã nhận FAST_BASE=https://$HOST:$PORT"

  echo "== 7) Tự cập nhật IP mỗi 5 phút (FPT đổi IP khi rớt mạng) + gia hạn chứng chỉ =="
  printf '%s\n' '[Unit]' 'Description=Cloud Phone duong thang: cap nhat IP + chung chi' 'After=network-online.target' \
    '[Service]' 'Type=oneshot' "ExecStart=$SELF tick" > /etc/systemd/system/cloudphone-fast.service
  printf '%s\n' '[Unit]' 'Description=Cloud Phone duong thang moi 5 phut' '[Timer]' 'OnBootSec=90' 'OnUnitActiveSec=300' \
    '[Install]' 'WantedBy=timers.target' > /etc/systemd/system/cloudphone-fast.timer
  systemctl daemon-reload; systemctl enable --now cloudphone-fast.timer >/dev/null 2>&1 && ok "Đã bật hẹn giờ"
  echo; bash "$SELF" check ;;

tick)
  [ -f "$ENV" ] || exit 0
  ddns >/dev/null
  st=/var/lib/cloudphone-fast.renew
  if [ ! -f "$st" ] || [ $(( $(date +%s) - $(stat -c %Y "$st") )) -gt 86400 ]; then
    "$AC" --cron --home /root/.acme.sh >> /var/log/cloudphone-fast-acme.log 2>&1; touch "$st"
  fi
  systemctl is-active -q nginx || systemctl restart nginx ;;

check)
  . "$ENV" 2>/dev/null
  ip=$(myip); dns=$(getent ahostsv4 "$HOST" | awk '{print $1; exit}')
  echo "IP nhà mạng: ${ip:-?}   ·   $HOST đang trỏ về: ${dns:-chưa có}"
  [ -n "$ip" ] && [ "$ip" = "$dns" ] && ok "Tên miền đúng IP" || warn "Tên miền chưa khớp IP (đợi 1–2 phút rồi check lại)"
  systemctl is-active -q nginx && ok "nginx đang chạy" || err "nginx đang tắt"
  c=$(curl -s -m 8 -o /dev/null -w '%{http_code}' --resolve "$HOST:$PORT:127.0.0.1" "https://$HOST:$PORT/__cp/inject.js")
  [ "$c" = 200 ] && ok "HTTPS + cpapi trong máy chủ: OK" || err "Trong máy chủ gọi https://$HOST:$PORT lỗi (mã $c)"
  grep -q "^FAST_BASE=" "$CONF" && ok "cpapi: $(grep '^FAST_BASE=' "$CONF")" || warn "cpapi chưa có FAST_BASE"
  echo
  echo "BƯỚC CUỐI — thử TỪ NGOÀI: tắt wifi điện thoại, dùng 4G, mở:"
  echo "    https://$HOST:$PORT/__cp/inject.js"
  echo "  • Ra một trang chữ (code)  → router mở cổng đúng, đường thẳng chạy ✓"
  echo "  • Không vào được           → kiểm tra lại mở cổng $PORT trên router (hoặc nhà mạng chặn / IP chung CGNAT)" ;;

off)
  rm -f /etc/nginx/conf.d/cloudphone-fast.conf; systemctl reload nginx 2>/dev/null
  conf_set FAST_BASE ""; systemctl restart cpapi
  systemctl disable --now cloudphone-fast.timer >/dev/null 2>&1
  ok "Đã tắt đường thẳng — khách tự dùng Cloudflare như cũ" ;;

*) sed -n '2,13p' "$0" ;;
esac
