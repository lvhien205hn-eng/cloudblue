#!/usr/bin/env bash
# =====================================================================
#  cloudphone-addnode.sh — THÊM 1 MÁY CHỦ MỚI chỉ bằng 1 lệnh (chạy trên MÁY CHỦ CŨ)
#    Tự làm hết: tạo đường hầm Cloudflare (phone2.blueroblox.shop…), chép cấu hình + bộ root + app cài sẵn
#    + các bản Android sang máy mới, rồi cài trọn bộ dịch vụ trên máy mới. Máy mới tự nhận đơn thuê.
#
#   bash ~/cloudphone-addnode.sh IP_MÁY_MỚI                 # VD: bash ~/cloudphone-addnode.sh 192.168.1.30
#   bash ~/cloudphone-addnode.sh IP_MÁY_MỚI user             # nếu tên đăng nhập máy mới khác máy cũ
#   bash ~/cloudphone-addnode.sh list                        # xem các máy chủ đã thêm
#   bash ~/cloudphone-addnode.sh update                      # cập nhật bản mới cho MỌI máy chủ (cũ + mới)
#   bash ~/cloudphone-addnode.sh cf                          # nhập / đổi mã Cloudflare (làm 1 lần)
#
#   Máy mới chỉ cần: cài Ubuntu 22.04 + chạy 1 lệnh:  sudo apt install -y openssh-server
#   Máy ở nơi khác (mạng khác) cũng được — chỉ cần SSH tới được (IP công khai / mở cổng 22).
# =====================================================================
set -u
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; B='\033[1;36m'; NC='\033[0m'
ok() { echo -e "${G}✓${NC} $*"; }; warn() { echo -e "${Y}!${NC} $*"; }; err() { echo -e "${R}✗${NC} $*"; }; step() { echo; echo -e "${B}━━ $* ━━${NC}"; }
[ "$(id -u)" = "0" ] && { err "Chạy bằng user thường (không sudo):  bash $0 ${1:-}"; exit 1; }
RAW="https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main"
CONF="$HOME/cloudphone.conf"; CFENV="$HOME/.cloudphone-cf.env"; NODES="$HOME/cloudphone-nodes.txt"; ZONE="blueroblox.shop"
[ -s "$CONF" ] || { err "Không thấy $CONF — hãy chạy lệnh này trên MÁY CHỦ CŨ (máy đang chạy web)."; exit 1; }
touch "$NODES"

cf() { curl -s -m 30 -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" "$@"; }
jget() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
for k in sys.argv[1].split('.'):
    try: d = d[int(k)] if isinstance(d, list) else (d or {}).get(k)
    except Exception: d = None
print('' if d is None else d)" "$1"; }

cf_setup() {
  echo "Cần 1 mã Cloudflare (API Token) để tự tạo đường hầm cho máy mới. Làm 1 lần:"
  echo "  1) Mở https://dash.cloudflare.com/profile/api-tokens → Create Token → Create Custom Token"
  echo "  2) Permissions (bấm + Add more):"
  echo "       Account │ Cloudflare Tunnel │ Edit"
  echo "       Zone    │ DNS               │ Edit"
  echo "     Zone Resources: Include → Specific zone → $ZONE"
  echo "  3) Continue to summary → Create Token → Copy"
  read -rsp "Dán mã vào đây rồi Enter (không hiện chữ): " CF_TOKEN; echo; CF_TOKEN=$(echo "$CF_TOKEN" | tr -d ' \r\n')
  [ "$(cf https://api.cloudflare.com/client/v4/user/tokens/verify | jget success)" = "True" ] || { err "Mã không đúng / hết hạn"; return 1; }
  Z=$(cf "https://api.cloudflare.com/client/v4/zones?name=$ZONE")
  CF_ZONE=$(echo "$Z" | jget result.0.id); CF_ACC=$(echo "$Z" | jget result.0.account.id)
  [ -n "$CF_ZONE" ] && [ -n "$CF_ACC" ] || { err "Mã chưa có quyền với $ZONE (xem lại bước 2)"; return 1; }
  umask 077; printf "CF_TOKEN=%s\nCF_ZONE=%s\nCF_ACC=%s\n" "$CF_TOKEN" "$CF_ZONE" "$CF_ACC" > "$CFENV"
  ok "Đã lưu mã Cloudflare ($CFENV, chỉ bạn đọc được)"
}

case "${1:-}" in
  ""|-h|--help) sed -n '2,14p' "$0"; exit 0 ;;
  list) echo "Máy chủ đã thêm:"; [ -s "$NODES" ] && sed 's/^/   /' "$NODES" || echo "   (chưa có)"; exit 0 ;;
  cf) cf_setup; exit $? ;;
  update)
    echo "== Máy chủ này =="; cloudphone update
    while read -r nd hp _; do [ -n "$hp" ] || continue
      echo; echo "== $nd ($hp) — nhập mật khẩu sudo của máy đó nếu được hỏi =="; ssh -t -o ConnectTimeout=15 "$hp" "cloudphone update" || err "$nd: không cập nhật được"
    done < "$NODES"; exit 0 ;;
esac

IP="$1"; RU="${2:-$USER}"
step "0) Chuẩn bị"
N=$(( $(grep -c . "$NODES") + 2 )); NODE="node$N"; SUB="phone$N"; HOSTN="$SUB.$ZONE"
while grep -q "^$NODE " "$NODES"; do N=$((N+1)); NODE="node$N"; SUB="phone$N"; HOSTN="$SUB.$ZONE"; done
OLD=$(awk -v h="$RU@$IP" '$2==h{print $1}' "$NODES" | head -1)         # chạy lại cho máy đã thêm → giữ tên cũ (cài lại / sửa lỗi)
if [ -n "$OLD" ]; then NODE="$OLD"; N="${OLD#node}"; SUB="phone$N"; HOSTN="$SUB.$ZONE"; fi
echo "   Máy mới: $RU@$IP  →  tên $NODE  ·  link https://$HOSTN"

# ---- SSH: hỏi mật khẩu 1 lần, dùng lại cho mọi lệnh sau ----
SOCK="/tmp/cpnode-$$"; SSHO=(-o ControlMaster=auto -o ControlPath="$SOCK" -o ControlPersist=30m -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
rs() { ssh "${SSHO[@]}" "$RU@$IP" "$@"; }
trap 'ssh -o ControlPath="$SOCK" -O exit "$RU@$IP" >/dev/null 2>&1' EXIT
echo "   Nhập MẬT KHẨU đăng nhập của máy mới (1 lần):"
rs "echo ok" >/dev/null || { err "Không SSH được vào $RU@$IP — máy mới đã chạy: sudo apt install -y openssh-server ?"; exit 1; }
ok "Đã kết nối máy mới ($(rs 'lsb_release -ds 2>/dev/null || cat /etc/issue | head -1'))"
# lần sau vào máy mới không cần mật khẩu (dùng khoá SSH)
[ -f "$HOME/.ssh/id_ed25519" ] || ssh-keygen -t ed25519 -N "" -q -f "$HOME/.ssh/id_ed25519"
cat "$HOME/.ssh/id_ed25519.pub" | rs 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && k=$(cat) && (grep -qxF "$k" ~/.ssh/authorized_keys 2>/dev/null || echo "$k" >> ~/.ssh/authorized_keys) && chmod 600 ~/.ssh/authorized_keys'
read -rsp "   Nhập MẬT KHẨU sudo của máy mới (thường giống mật khẩu đăng nhập): " PW; echo
printf '%s\n' "$PW" | rs "sudo -S -p '' bash -c 'echo \"$RU ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/90-cloudphone-setup && chmod 440 /etc/sudoers.d/90-cloudphone-setup'" \
  || { err "Sai mật khẩu sudo (hoặc user $RU không có quyền sudo)"; exit 1; }
unset PW
trap 'rs "sudo rm -f /etc/sudoers.d/90-cloudphone-setup" >/dev/null 2>&1; ssh -o ControlPath="$SOCK" -O exit "$RU@$IP" >/dev/null 2>&1' EXIT   # cài xong thu hồi quyền tạm
ok "Đã có quyền cài đặt (tạm thời, tự thu hồi khi xong)"

# ---- 1) Đường hầm Cloudflare cho máy mới ----
step "1) Đường hầm Cloudflare: $HOSTN"
TK=""
[ -s "$CFENV" ] || cf_setup || warn "Bỏ qua tự tạo đường hầm"
if [ -s "$CFENV" ]; then
  . "$CFENV"; A="https://api.cloudflare.com/client/v4/accounts/$CF_ACC/cfd_tunnel"
  TID=$(cf "$A?name=blueroblox-$NODE&is_deleted=false" | jget result.0.id)
  [ -n "$TID" ] || TID=$(cf -X POST "$A" --data "{\"name\":\"blueroblox-$NODE\",\"config_src\":\"cloudflare\"}" | jget result.id)
  if [ -n "$TID" ]; then
    cf -X PUT "$A/$TID/configurations" --data "{\"config\":{\"ingress\":[{\"hostname\":\"$HOSTN\",\"service\":\"http://localhost:8010\"},{\"service\":\"http_status:404\"}]}}" >/dev/null
    REC=$(cf "https://api.cloudflare.com/client/v4/zones/$CF_ZONE/dns_records?name=$HOSTN" | jget result.0.id)
    BODY="{\"type\":\"CNAME\",\"name\":\"$SUB\",\"content\":\"$TID.cfargotunnel.com\",\"proxied\":true}"
    if [ -n "$REC" ]; then cf -X PUT "https://api.cloudflare.com/client/v4/zones/$CF_ZONE/dns_records/$REC" --data "$BODY" >/dev/null
    else cf -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE/dns_records" --data "$BODY" >/dev/null; fi
    TK=$(cf "$A/$TID/token" | jget result)
    [ -n "$TK" ] && ok "Đã tạo đường hầm + tên miền $HOSTN" || warn "Tạo đường hầm được nhưng chưa lấy được mã chạy"
  else warn "Không tạo được đường hầm (mã Cloudflare thiếu quyền 'Cloudflare Tunnel: Edit'?)"; fi
fi
if [ -z "$TK" ]; then
  echo "   Làm tay: https://one.dash.cloudflare.com → Networks → Tunnels → Create a tunnel → Cloudflared → đặt tên blueroblox-$NODE"
  echo "   → copy mã TOKEN (chuỗi dài sau 'service install') → Next → Public hostname: subdomain $SUB · domain $ZONE · Type HTTP · URL localhost:8010 → Save"
  read -rp "   Dán TOKEN vào đây: " TK; TK=$(echo "$TK" | tr -d ' \r\n'); TK=${TK##* }
  [ -n "$TK" ] || { err "Chưa có đường hầm — dừng."; exit 1; }
fi

# ---- 2) Docker trên máy mới (để nhận các bản Android) ----
step "2) Cài Docker trên máy mới"
rs "command -v docker >/dev/null || (sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io >/dev/null); sudo systemctl enable --now docker >/dev/null 2>&1; sudo usermod -aG docker $RU" \
  && ok "Docker sẵn sàng" || { err "Cài Docker lỗi"; exit 1; }

# ---- 3) Chép các bản Android (image) sang máy mới ----
step "3) Chép các bản Android sang máy mới (qua mạng LAN ~1–3 phút/bản; mạng ngoài lâu hơn)"
IMGS=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^redroid/redroid:[0-9]+\.0\.0_' | grep -v '_root$' | sort -u)
for img in $IMGS; do
  if rs "sudo docker image inspect $img >/dev/null 2>&1"; then ok "$img (máy mới đã có)"; continue; fi
  SZ=$(docker image inspect -f '{{.Size}}' "$img" | awk '{printf "%.1fGB", $1/1e9}')
  echo "   … $img ($SZ)"
  if docker save "$img" | gzip -1 | rs "gunzip | sudo docker load >/dev/null"; then ok "$img"; else err "Chép $img lỗi (chạy lại lệnh này để thử tiếp)"; fi
done

# ---- 4) Cấu hình + bộ root + app cài sẵn ----
step "4) Chép cấu hình, bộ root, app cài sẵn"
T=$(mktemp -d); trap 'rm -rf "$T"; rs "sudo rm -f /etc/sudoers.d/90-cloudphone-setup" >/dev/null 2>&1; ssh -o ControlPath="$SOCK" -O exit "$RU@$IP" >/dev/null 2>&1' EXIT
grep -vE '^(NODE_ID|PUBLIC_BASE|PRIMARY|FAST_BASE)=' "$CONF" > "$T/cloudphone.conf"
printf "NODE_ID=%s\nPUBLIC_BASE=https://%s\nPRIMARY=0\n" "$NODE" "$HOSTN" >> "$T/cloudphone.conf"
chmod 600 "$T/cloudphone.conf"
tar -C "$HOME" -czf "$T/pack.tgz" --ignore-failed-read cloudphone-su apk-cai-san android-versions.sh cloudphone-apps.sh cloudphone-root.sh cloudphone-multiclone.sh cloudphone-selftest.sh 2>/dev/null
cat "$T/cloudphone.conf" | rs "umask 077; cat > ~/cloudphone.conf" && ok "cloudphone.conf (tên $NODE, link https://$HOSTN)"
cat "$T/pack.tgz" | rs "mkdir -p ~/redroid && tar -xzf - -C ~" && ok "Bộ root, app cài sẵn ($(ls "$HOME/apk-cai-san" 2>/dev/null | wc -l) app), các script"

# ---- 5) Cài trọn bộ dịch vụ trên máy mới ----
step "5) Cài dịch vụ trên máy mới (5–10 phút)"
rs "curl -fsSL -o /tmp/cloudphone-setup.sh '$RAW/cloudphone-setup.sh?t=\$(date +%s)'" || { err "Máy mới không tải được từ GitHub (mất mạng?)"; exit 1; }
rs "sudo env CF_TUNNEL_TOKEN='$TK' CP_USER=$RU bash /tmp/cloudphone-setup.sh" 2>&1 | sed 's/^/   │ /'

# ---- 6) Kiểm tra ----
step "6) Kiểm tra máy mới"
sleep 8
rs "systemctl is-active -q cloudphoned && systemctl is-active -q cpapi" && ok "Dịch vụ trên máy mới đang chạy" || warn "Dịch vụ máy mới chưa chạy — xem: ssh $RU@$IP 'cloudphone logs'"
for i in 1 2 3 4 5 6; do
  C=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "https://$HOSTN/__cp/inject.js"); [ "$C" = 200 ] && break; sleep 10
done
[ "$C" = 200 ] && ok "https://$HOSTN đã ra internet" || warn "https://$HOSTN chưa trả lời (mã $C) — đợi 1–2 phút rồi mở thử"
grep -q "^$NODE " "$NODES" || echo "$NODE $RU@$IP https://$HOSTN $(date +%F)" >> "$NODES"
echo
echo -e "${G}══════════ XONG: đã thêm máy chủ $NODE ══════════${NC}"
echo "  • Máy mới tự nhận đơn thuê khi còn trống (máy nào trống nhiều hơn nhận trước)."
echo "  • Admin → ĐT đám mây → mục Máy chủ sẽ thấy $NODE sau ~30 giây."
echo "  • Cập nhật MỌI máy chủ sau này:  bash ~/cloudphone-addnode.sh update"
