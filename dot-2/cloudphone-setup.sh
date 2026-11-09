#!/usr/bin/env bash
# =====================================================================
#  cloudphone-setup.sh — Cài TRỌN BỘ máy chủ điện thoại đám mây (blueroblox)
#  Chạy:   sudo bash ~/cloudphone-setup.sh
#  Chạy lại bao nhiêu lần cũng được: phần nào có rồi thì bỏ qua.
#  Sau khi cài xong, dùng lệnh:  cloudphone   (xem trạng thái, cập nhật, khởi động lại…)
# =====================================================================
set -u
REPO_RAW="https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main"
IMAGE="redroid/redroid:11.0.0_gapps_ndk"
WSNAME="wsscrcpy"
WSIMAGE="scavin/ws-scrcpy"

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; B='\033[1;36m'; N='\033[0m'
ok()   { echo -e "${G}✓${N} $*"; }
warn() { echo -e "${Y}!${N} $*"; }
err()  { echo -e "${R}✗${N} $*"; }
step() { echo; echo -e "${B}━━ $* ━━${N}"; }

if [ "$(id -u)" != "0" ]; then err "Hãy chạy bằng sudo:  sudo bash $0"; exit 1; fi
U="${CP_USER:-${SUDO_USER:-}}"
if [ -z "$U" ] || [ "$U" = "root" ]; then read -rp "Tên user Linux sẽ chạy dịch vụ (VD lehien): " U; fi
id "$U" >/dev/null 2>&1 || { err "Không có user $U"; exit 1; }
H=$(getent passwd "$U" | cut -d: -f6)
asu() { sudo -u "$U" -H bash -c "$*"; }
echo -e "${B}Cài máy chủ điện thoại đám mây cho user ${U} (${H})${N}"

# ---------------------------------------------------------------------
step "1/9 Gói hệ thống"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
PK="python3 curl ca-certificates unzip lvm2"
command -v docker >/dev/null || PK="$PK docker.io"
apt-get install -y -qq $PK >/dev/null && ok "python3, curl, docker…"
apt-get install -y -qq "linux-modules-extra-$(uname -r)" >/dev/null 2>&1 && ok "linux-modules-extra (binder)" || warn "Không cài được linux-modules-extra-$(uname -r) (có thể nhân đã có sẵn binder)"
systemctl enable --now docker >/dev/null 2>&1
usermod -aG docker "$U" && ok "User $U dùng được docker"

# ---------------------------------------------------------------------
step "2/9 Mở rộng ổ cứng (dùng hết dung lượng thật)"
LV=$(findmnt -no SOURCE / 2>/dev/null)
if [[ "$LV" == /dev/mapper/* ]] && lvs "$LV" >/dev/null 2>&1; then
  VG=$(lvs --noheadings -o vg_name "$LV" | tr -d ' ')
  FREE=$(vgs --noheadings --units g --nosuffix -o vg_free "$VG" | tr -d ' ' | cut -d. -f1)
  if [ "${FREE:-0}" -gt 1 ]; then
    lvextend -l +100%FREE "$LV" >/dev/null && resize2fs "$LV" >/dev/null 2>&1 ; ok "Đã mở rộng thêm ${FREE}GB"
  else ok "Ổ đã dùng hết dung lượng"; fi
else ok "Không dùng LVM — bỏ qua"; fi
df -h / | tail -1 | awk '{print "   Ổ /: tổng "$2", trống "$4}'
SWAP_MB=$(free -m | awk '/^Swap:/{print $2}')
if [ "${SWAP_MB:-0}" -lt 8000 ] && [ ! -f /swapfile-cloud ]; then      # vùng đệm khi máy ảo dùng sát hết RAM → chậm chứ không văng app
  fallocate -l 16G /swapfile-cloud 2>/dev/null || dd if=/dev/zero of=/swapfile-cloud bs=1M count=16384 status=none
  if chmod 600 /swapfile-cloud && mkswap /swapfile-cloud >/dev/null && swapon /swapfile-cloud; then
    grep -q swapfile-cloud /etc/fstab || echo "/swapfile-cloud none swap sw 0 0" >> /etc/fstab
    ok "Đã thêm 16GB swap (vùng đệm RAM)"
  else warn "Không tạo được swap — bỏ qua"; rm -f /swapfile-cloud; fi
else ok "Swap: ${SWAP_MB}MB"; fi
sysctl -q vm.swappiness=10 && echo "vm.swappiness=10" > /etc/sysctl.d/99-cloudphone.conf

# ---------------------------------------------------------------------
step "3/9 Binder cho Android (tự nạp mỗi lần khởi động)"
echo "binder_linux" > /etc/modules-load.d/redroid.conf
echo "options binder_linux devices=binder,hwbinder,vndbinder" > /etc/modprobe.d/redroid.conf
modprobe binder_linux devices="binder,hwbinder,vndbinder" 2>/dev/null
if lsmod | grep -q binder; then ok "binder đã bật"; else err "binder CHƯA bật — máy Android sẽ không chạy. Gửi kết quả 'uname -r' cho người hỗ trợ."; fi

# ---------------------------------------------------------------------
step "4/9 Tải image Android + trình điều khiển web"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then ok "$IMAGE (đã có sẵn)"; else docker pull -q "$IMAGE" >/dev/null && ok "$IMAGE" || warn "Chưa có image $IMAGE — cần tải/dựng image này trước khi tạo máy"; fi
docker pull -q alpine >/dev/null && ok "alpine (dùng để xoá sạch dữ liệu máy cũ)"
if docker ps -a --format '{{.Names}}' | grep -qx "$WSNAME"; then
  docker start "$WSNAME" >/dev/null 2>&1; ok "ws-scrcpy đã có (container $WSNAME)"
else
  docker run -d --name "$WSNAME" --restart unless-stopped --network host "$WSIMAGE" >/dev/null && ok "Đã tạo ws-scrcpy (cổng 8000, chỉ dùng trong máy)"
fi

# ---------------------------------------------------------------------
step "5/9 Tải chương trình từ GitHub"
for f in phonectl.py cloudphoned.py cpapi.py; do
  if asu "curl -fsSL -o '$H/$f.new' '$REPO_RAW/$f?t=$(date +%s)'" && [ -s "$H/$f.new" ]; then
    mv "$H/$f.new" "$H/$f"; chown "$U:$U" "$H/$f"; ok "$f"
  else rm -f "$H/$f.new"; err "Không tải được $f — kiểm tra file đã up lên GitHub chưa"; fi
done
asu "mkdir -p '$H/redroid' '$H/apk-cai-san'"

# ---------------------------------------------------------------------
step "6/9 File cấu hình bí mật (~/cloudphone.conf — KHÔNG đưa lên GitHub)"
CONF="$H/cloudphone.conf"
if [ -s "$CONF" ] && grep -q "^SUPABASE_SERVICE_KEY=." "$CONF"; then
  ok "Đã có $CONF — giữ nguyên"
elif [ ! -t 0 ]; then err "Thiếu $CONF (chạy cài bằng tay để nhập khoá)"; exit 1
else
  read -rp "SUPABASE_URL [https://nprftgodswlpzomcttal.supabase.co]: " SU; SU=${SU:-https://nprftgodswlpzomcttal.supabase.co}
  read -rsp "Dán SUPABASE_SERVICE_KEY (service_role, sẽ không hiện chữ): " SK; echo
  read -rp "Link điều khiển công khai [https://phone.blueroblox.shop]: " PB; PB=${PB:-https://phone.blueroblox.shop}
  read -rp "Tên máy chủ này [$(hostname)]: " NI; NI=${NI:-$(hostname)}
  printf "SUPABASE_URL=%s\nSUPABASE_SERVICE_KEY=%s\nPUBLIC_BASE=%s\nNODE_ID=%s\n" "$SU" "$SK" "$PB" "$NI" > "$CONF"
  chown "$U:$U" "$CONF"; chmod 600 "$CONF"; ok "Đã lưu $CONF (chỉ user $U đọc được)"
fi

# ---------------------------------------------------------------------
step "7/9 Dịch vụ chạy 24/7 (cloudphoned + cpapi)"
mk_unit() { # $1 tên  $2 mô tả  $3 file .py
cat > "/etc/systemd/system/$1.service" <<EOF
[Unit]
Description=$2
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=$U
WorkingDirectory=$H
ExecStart=/usr/bin/python3 -u $H/$3
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}
[ -f /etc/systemd/system/cloudphoned.service ] || mk_unit cloudphoned "Cloud Phone - tao/xoa/gia han may" cloudphoned.py
[ -f /etc/systemd/system/cpapi.service ] || mk_unit cpapi "Cloud Phone API + cong bao ve ws-scrcpy" cpapi.py
systemctl daemon-reload
systemctl enable cloudphoned cpapi >/dev/null 2>&1
systemctl restart cpapi cloudphoned
sleep 3
for s in cpapi cloudphoned; do systemctl is-active -q $s && ok "$s đang chạy" || err "$s lỗi — xem: sudo journalctl -u $s -n 30 --no-pager"; done

# ---------------------------------------------------------------------
step "8/9 Đường hầm Cloudflare (đưa trang điều khiển ra internet)"
if systemctl list-unit-files | grep -q "^cloudflared-phone"; then
  systemctl restart cloudflared-phone; ok "Đã có dịch vụ cloudflared-phone"
elif systemctl list-unit-files | grep -q "^cloudflared.service"; then
  ok "Đã có dịch vụ cloudflared (cài bằng token)"
else
  if ! command -v cloudflared >/dev/null; then
    curl -fsSL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
      && dpkg -i /tmp/cloudflared.deb >/dev/null && ok "Đã cài cloudflared"
  fi
  echo "   Vào https://one.dash.cloudflare.com → Networks → Tunnels → Create tunnel (Cloudflared) → copy TOKEN"
  echo "   (trong tunnel thêm Public hostname: phone.blueroblox.shop → Service HTTP → localhost:8010)"
  TK="${CF_TUNNEL_TOKEN:-}"
  [ -n "$TK" ] || [ ! -t 0 ] || read -rp "Dán TOKEN tunnel (Enter để bỏ qua, làm sau): " TK
  if [ -n "$TK" ]; then cloudflared service install "$TK" >/dev/null 2>&1 && ok "Đã cài tunnel (dịch vụ cloudflared)" || err "Cài tunnel lỗi — kiểm tra token"; fi
fi

# ---------------------------------------------------------------------
step "9/9 App cài sẵn cho mọi máy (thư mục ~/apk-cai-san)"
if ls "$H/apk-cai-san"/*irefox* >/dev/null 2>&1; then ok "Đã có Firefox"
else
  V=$(curl -fsSL https://ftp.mozilla.org/pub/fenix/releases/ | grep -oE '/[0-9]+\.[0-9]+(\.[0-9]+)?/' | tr -d / | sort -V | tail -1)
  if [ -n "$V" ] && asu "curl -fsSL -o '$H/apk-cai-san/firefox.apk' 'https://ftp.mozilla.org/pub/fenix/releases/$V/android/fenix-$V-android-x86_64/fenix-$V.multi.android-x86_64.apk'"; then
    ok "Đã tải Firefox $V"
  else warn "Không tải được Firefox tự động — tải tay rồi bỏ vào $H/apk-cai-san"; fi
fi
if ls "$H/apk-cai-san"/*rave* >/dev/null 2>&1; then ok "Đã có Brave (trình duyệt nhân Chrome)"
else
  asu "curl -fsSL -o '$H/apk-cai-san/brave.apk' 'https://github.com/brave/brave-browser/releases/latest/download/BraveMonox64.apk'" \
    && ok "Đã tải Brave (trình duyệt nhân Chrome, tải file/APK được, đăng nhập Google được)" || warn "Không tải được Brave"
fi
for f in "$H"/apk-cai-san/*; do [ -s "$f" ] && [ "$(stat -c %s "$f")" -lt 1000000 ] && { warn "File $(basename "$f") quá nhỏ (tải lỗi) — đã xoá"; rm -f "$f"; }; done
ls -lh "$H/apk-cai-san" | tail -n +2 | awk '{print "   • "$9"  ("$5")"}'
echo "   Muốn cài sẵn thêm app (Chrome/Gmail .apkm x86_64…): bỏ vào thư mục trên rồi chạy:  cloudphone apps"
echo "   Đang cài app sẵn cho các máy đang chạy (có thể mất vài phút)…"
asu "python3 '$H/phonectl.py' preinstall --all; python3 '$H/phonectl.py' perms" 2>&1 | grep -E "^\s*[+!]" || true

# ---------------------------------------------------------------------
# Tối ưu máy chủ: zram + swap ổ cứng (chừa 200GB) + CPU performance + thông số nhân
step "Tối ưu máy chủ (RAM ảo, CPU)"
if curl -fsSL -o /tmp/cloudphone-tune.sh "$REPO_RAW/cloudphone-tune.sh?t=$(date +%s)" && bash -n /tmp/cloudphone-tune.sh; then
  bash /tmp/cloudphone-tune.sh install | sed 's/^/   /'
else warn "Chưa tải được cloudphone-tune.sh — up file đó lên GitHub rồi chạy lại lệnh cài"; fi

# Người gác: tự kiểm tra + tự sửa mỗi 1 phút, tự chạy lại sau khi máy khởi động
step "Watchdog (tự kiểm tra, tự sửa khi lỗi / mất điện)"
if curl -fsSL -o /tmp/cloudphone-watchdog.sh "$REPO_RAW/cloudphone-watchdog.sh?t=$(date +%s)" && bash -n /tmp/cloudphone-watchdog.sh; then
  bash /tmp/cloudphone-watchdog.sh install | sed 's/^/   /'
else warn "Chưa tải được cloudphone-watchdog.sh — up file đó lên GitHub rồi chạy lại lệnh cài"; fi

# ---------------------------------------------------------------------
# Bộ root (su) cho máy mới: nếu đã có ~/cloudphone-su thì bật luôn
if [ -x "$H/cloudphone-su/su" ] && [ -x "$H/cloudphone-su/cpsud" ]; then ok "Bộ root đã có — máy tạo trên server này tự có root"; fi

# Lệnh tắt "cloudphone"
cat > /usr/local/bin/cloudphone <<EOF
#!/usr/bin/env bash
U="$U"; H="$H"; RAW="$REPO_RAW"
run() { if [ "\$(id -un)" = "\$U" ]; then "\$@"; else sudo -u "\$U" -H "\$@"; fi; }
case "\${1:-}" in
  status|"")
    for s in cpapi cloudphoned cloudflared-phone cloudflared; do systemctl list-unit-files | grep -q "^\$s.service" && printf "%-18s %s\n" "\$s" "\$(systemctl is-active \$s)"; done
    printf "%-18s %s\n" "watchdog" "\$(systemctl is-active cloudphone-watchdog.timer 2>/dev/null)"
    printf "%-18s %s\n" "ws-scrcpy" "\$(docker inspect -f '{{.State.Status}}' $WSNAME 2>/dev/null || echo không có)"
    lsmod | grep -q binder && echo "binder             bật" || echo "binder             TẮT (sudo modprobe binder_linux)"
    df -h / | tail -1 | awk '{print "ổ cứng             trống "\$4" / "\$2}'
    free -g | awk '/^Swap:/{print "RAM ảo (swap)      "\$2" GB (đang dùng "\$3" GB)"}'
    grep -q "def preinstall" "\$H/phonectl.py" && echo "phonectl.py        bản mới (có cài app sẵn)" || echo "phonectl.py        BẢN CŨ → chạy: cloudphone update"
    echo "app cài sẵn        \$(ls "\$H/apk-cai-san" 2>/dev/null | tr '\n' ' ')"
    run python3 "\$H/phonectl.py" capacity ;;
  update)
    for f in phonectl.py cloudphoned.py cpapi.py; do
      run curl -fsSL -o "\$H/\$f.new" "\$RAW/\$f?t=\$(date +%s)" && [ -s "\$H/\$f.new" ] && run python3 -m py_compile "\$H/\$f.new" \
        && run mv "\$H/\$f.new" "\$H/\$f" && echo "✓ \$f" || { echo "✗ \$f (giữ bản cũ)"; rm -f "\$H/\$f.new"; }
    done
    sudo systemctl restart cpapi cloudphoned && echo "✓ Đã khởi động lại dịch vụ"
    curl -fsSL -o /tmp/cpwd.sh "\$RAW/cloudphone-watchdog.sh?t=\$(date +%s)" && bash -n /tmp/cpwd.sh && sudo bash /tmp/cpwd.sh install >/dev/null && echo "✓ watchdog" ;;
  restart) sudo systemctl restart cpapi cloudphoned; docker restart $WSNAME >/dev/null; for s in cloudflared-phone cloudflared; do systemctl is-enabled -q \$s 2>/dev/null && sudo systemctl restart \$s; done; echo "✓ Đã khởi động lại (dịch vụ + phát hình + tunnel)" ;;
  tune)    curl -fsSL -o /tmp/cptune.sh "\$RAW/cloudphone-tune.sh?t=\$(date +%s)" && bash -n /tmp/cptune.sh && sudo bash /tmp/cptune.sh install ;;
  watch)   tail -n "\${2:-30}" /var/log/cloudphone-watchdog.log 2>/dev/null || echo "Chưa có nhật ký watchdog" ;;
  logs)    sudo journalctl -u "\${2:-cloudphoned}" -n "\${3:-50}" --no-pager ;;
  list)    run python3 "\$H/phonectl.py" list ;;
  apps)    run python3 "\$H/phonectl.py" preinstall --all; run python3 "\$H/phonectl.py" perms; echo "✓ Xong (máy nào đã có app thì bỏ qua)" ;;
  perms)   run python3 "\$H/phonectl.py" perms && echo "✓ Đã mở quyền cài APK cho mọi máy" ;;
  memfix)  run python3 "\$H/phonectl.py" memfix ;;
  *) echo "cloudphone [status|update|restart|tune|watch|logs [cpapi|cloudphoned]|list|apps|perms|memfix]" ;;
esac
EOF
chmod +x /usr/local/bin/cloudphone

echo
echo -e "${G}══════════ CÀI XONG ══════════${N}"
echo "  cloudphone          → xem trạng thái"
echo "  cloudphone update   → tải bản mới từ GitHub + khởi động lại"
echo "  cloudphone apps     → cài app trong ~/apk-cai-san cho mọi máy đang chạy"
echo "  cloudphone perms    → mở quyền cài APK cho mọi máy"
echo "  cloudphone logs     → xem nhật ký"
echo -e "${Y}Lưu ý:${N} lần đầu cài, hãy đăng xuất SSH rồi vào lại để user $U dùng được docker."
