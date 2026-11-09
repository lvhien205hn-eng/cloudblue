#!/usr/bin/env bash
# =====================================================================
#  cloudphone-apps.sh — KHO ỨNG DỤNG có sẵn cho máy khách (thư mục ~/apk-cai-san)
#    • App trong kho được TỰ CÀI vào mọi máy (máy mới + máy cũ, ~5 phút/lần) và hiện trong "🛍️ Kho ứng dụng" trên trang điều khiển
#    • Firefox: tải bản CHÍNH THỨC từ máy chủ Mozilla (bản x86_64 chạy nhanh nhất trên máy ảo)
#    • Chrome: cài 1 lần từ CH Play trong 1 máy, rồi "grab chrome" chép bản chính chủ Google đó vào kho cho mọi máy
#    • App khác: admin tự thêm ở Quản trị → ĐT đám mây → Cài APK (tick "giữ lại cho máy mới"), hoặc chép file .apk vào ~/apk-cai-san
#
#   bash cloudphone-apps.sh firefox     # tải / cập nhật Firefox chính thức vào kho
#   bash cloudphone-apps.sh grab chrome cp_xxx   # chép Chrome (đã cài từ CH Play trong máy cp_xxx) vào kho → mọi máy khác cài 1 chạm
#   bash cloudphone-apps.sh grab TÊN.GÓI cp_xxx  # chép app bất kỳ đã cài trong máy vào kho (VD com.discord)
#   bash cloudphone-apps.sh list        # xem kho
#   bash cloudphone-apps.sh push        # cài ngay kho vào mọi máy đang chạy (không cần đợi 5 phút)
# =====================================================================
set -u
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
D="$HOME/apk-cai-san"; mkdir -p "$D"

case "${1:-}" in
firefox)
  V=$(curl -fsSL -m 30 https://product-details.mozilla.org/1.0/mobile_versions.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('version',''))" 2>/dev/null)
  if [ -z "$V" ]; then   # dự phòng: đọc danh sách bản phát hành trên máy chủ Mozilla
    V=$(curl -fsSL -m 30 https://ftp.mozilla.org/pub/fenix/releases/ | grep -oE 'releases/[0-9]+\.[0-9]+(\.[0-9]+)?/' | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | sort -V | tail -1)
  fi
  [ -n "$V" ] || { err "Không đọc được phiên bản Firefox mới nhất (mất mạng?)"; exit 1; }
  F="$D/Firefox-$V.apk"
  [ -s "$F" ] && { ok "Kho đã có Firefox $V"; exit 0; }
  echo "== Tải Firefox $V (chính thức Mozilla, x86_64) =="
  U="https://ftp.mozilla.org/pub/fenix/releases/$V/android/fenix-$V-android-x86_64/fenix-$V.multi.android-x86_64.apk"
  curl -fL -m 900 -o "$F.part" "$U" || { rm -f "$F.part"; err "Tải lỗi: $U"; exit 1; }
  python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).testzip()" "$F.part" 2>/dev/null || { rm -f "$F.part"; err "File tải về bị hỏng"; exit 1; }
  rm -f "$D"/Firefox-*.apk; mv "$F.part" "$F"
  ok "Đã thêm Firefox $V vào kho — server tự cài vào mọi máy trong vài phút (hoặc chạy: bash $0 push)" ;;

grab)
  PKG="${2:-}"; C="${3:-}"
  [ "$PKG" = "chrome" ] && PKG=com.android.chrome
  [ "$PKG" = "firefox" ] && PKG=org.mozilla.firefox
  [ -n "$PKG" ] && [ -n "$C" ] || { err "Cách dùng:  bash $0 grab chrome TÊN_MÁY   (xem tên máy: python3 ~/phonectl.py list)"; exit 1; }
  docker ps --format '{{.Names}}' | grep -qx "$C" || { err "Không thấy máy $C đang chạy (máy GPU chưa hỗ trợ — chọn máy thường)"; exit 1; }
  PATHS=$(docker exec "$C" /system/bin/pm path "$PKG" 2>/dev/null | tr -d '\r' | sed -n 's/^package://p')
  [ -n "$PATHS" ] || { err "Máy $C chưa cài $PKG — mở CH Play trong máy đó, cài $PKG trước rồi chạy lại"; exit 1; }
  VER=$(docker exec "$C" /system/bin/sh -c "dumpsys package $PKG | grep -m1 versionName" | tr -d '\r' | sed 's/.*versionName=//; s/[^0-9A-Za-z._-]//g')
  T=$(mktemp -d); i=0
  for f in $PATHS; do docker cp "$C:$f" "$T/" >/dev/null 2>&1 || { err "Không chép được $f"; rm -rf "$T"; exit 1; }; i=$((i+1)); done
  NAME=$( [ "$PKG" = com.android.chrome ] && echo Chrome || echo "$PKG")
  OUT="$D/$NAME-${VER:-latest}"
  rm -f "$D/$NAME"-*.apk "$D/$NAME"-*.apks
  if [ "$i" = 1 ]; then cp "$T"/*.apk "$OUT.apk"; OUT="$OUT.apk"
  else (cd "$T" && python3 -c "import zipfile,glob,sys; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_STORED); [z.write(f) for f in glob.glob('*.apk')]; z.close()" "$OUT.apks"); OUT="$OUT.apks"; fi
  rm -rf "$T"
  ok "Đã thêm $(basename "$OUT") ($i phần) vào kho — máy khác cài 1 chạm ở 🛍️ Kho ứng dụng, và server tự cài sẵn cho mọi máy" ;;

list)
  echo "Kho: $D"; ls -lh "$D" | awk 'NR>1{print "   " $5 "\t" $9}' ;;

push)
  python3 "$HOME/phonectl.py" preinstall --all && ok "Đã cài kho vào các máy đang chạy" ;;

*) sed -n '2,12p' "$0" ;;
esac
