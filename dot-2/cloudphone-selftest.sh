#!/usr/bin/env bash
# =====================================================================
#  cloudphone-selftest.sh — KIỂM TRA TOÀN BỘ CHỨC NĂNG trên máy thật (không đụng dữ liệu khách)
#    Mỗi máy được thử: lên màn hình chính · luồng hình (adb) · chụp màn · bấm phím
#    · TẢI + CÀI APK ngoài (cài xong tự gỡ) · chép file vào Download · root · Chrome/Firefox
#    · bộ dịch ARM (Roblox) · clone tab · GPS · mạng · app văng
#
#   (máy khách đang mở app thì KHÔNG mở app thử, chỉ kiểm tra ngầm)
#   bash cloudphone-selftest.sh            # thử 1 máy cho MỖI bản Android đang chạy (nhanh)
#   bash cloudphone-selftest.sh all        # thử TẤT CẢ máy đang chạy
#   bash cloudphone-selftest.sh cp_xxx     # thử 1 máy
# =====================================================================
set -u
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
PASS=0; FAIL=0; WARN=0; FAILS=""
ok()   { echo -e "   ${G}✓${N} $*"; PASS=$((PASS+1)); }
bad()  { echo -e "   ${R}✗${N} $*"; FAIL=$((FAIL+1)); FAILS="$FAILS\n   ✗ $CUR: $*"; }
warn() { echo -e "   ${Y}!${N} $*"; WARN=$((WARN+1)); }
WS=wsscrcpy; ST="$HOME/redroid/phones.json"
TESTAPK_URL="https://blueroblox.shop/download/blueroblox-cloud.apk"   # app của chính bạn — cài thử rồi gỡ
TESTPKG=""

echo "== Dịch vụ trên server =="
CUR=server
systemctl is-active --quiet cloudphoned && ok "cloudphoned đang chạy" || bad "cloudphoned KHÔNG chạy (sudo systemctl restart cloudphoned)"
systemctl is-active --quiet cpapi 2>/dev/null && ok "cpapi đang chạy" || { curl -fsS -o /dev/null -m 5 http://127.0.0.1:8010/__cp/inject.js && ok "cpapi đang chạy" || bad "cpapi KHÔNG chạy (sudo systemctl restart cpapi)"; }
curl -fsS -m 5 http://127.0.0.1:8010/__cp/inject.js 2>/dev/null | grep -q "cpcmd" && ok "cpapi trả trang điều khiển OK" || bad "cpapi không trả inject.js"
docker ps --format '{{.Names}}' | grep -qx "$WS" && ok "ws-scrcpy (luồng hình) đang chạy" || bad "ws-scrcpy KHÔNG chạy"
[ -e /dev/ashmem ] && ok "ashmem có (Chrome cần)" || bad "thiếu /dev/ashmem (sudo modprobe ashmem_linux)"
FREE=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9); [ "${FREE:-0}" -ge 20 ] && ok "Ổ đĩa còn ${FREE}GB" || warn "Ổ đĩa chỉ còn ${FREE}GB"
APKN=$(ls "$HOME/apk-cai-san" 2>/dev/null | grep -ciE '\.(apk|apks|xapk|apkm)$'); ok "Kho ứng dụng: ${APKN:-0} app ($(ls "$HOME/apk-cai-san" 2>/dev/null | tr '\n' ' '))"

# tải APK thử 1 lần
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
if curl -fsSL -m 120 -o "$T/test.apk" "$TESTAPK_URL" && python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).getinfo('AndroidManifest.xml')" "$T/test.apk" 2>/dev/null; then
  ok "Tải APK thử từ link: $(du -h "$T/test.apk" | cut -f1)"
  docker cp "$T/test.apk" "$WS:/tmp/selftest.apk" >/dev/null 2>&1 && ok "Chép APK vào ws-scrcpy" || bad "Không chép được APK vào $WS"
else bad "Không tải được APK thử ($TESTAPK_URL)"; fi

port_of() { python3 -c "import json,sys; print(next((p['port'] for p in json.load(open('$ST'))['phones'] if p['name']==sys.argv[1]),''))" "$1" 2>/dev/null; }
A() { timeout 60 docker exec "$WS" adb -s "127.0.0.1:$P" "$@" 2>&1 | tr -d '\r'; }
S() { timeout 60 docker exec "$CUR" /system/bin/sh -c "$1" 2>&1 | tr -d '\r'; }

# chọn máy cần thử
RUN=$(docker ps --format '{{.Names}}' | grep -E '^cp_' | sort)
case "${1:-}" in
  all) LIST="$RUN" ;;
  cp_*) LIST="$1" ;;
  *) LIST=""; seen=" "
     for c in $RUN; do v=$(docker exec "$c" getprop ro.build.version.release 2>/dev/null | tr -d '\r'); [[ "$seen" == *" $v "* ]] && continue; seen="$seen$v "; LIST="$LIST $c"; done ;;
esac
[ -n "$(echo $LIST)" ] || { echo -e "${R}Không có máy nào đang chạy để thử${N}"; exit 1; }

for CUR in $LIST; do
  P=$(port_of "$CUR"); VER=$(S 'getprop ro.build.version.release'); SDK=$(S 'getprop ro.build.version.sdk')
  echo; echo "== $CUR · Android $VER (SDK $SDK) · cổng ${P:-?} · image $(docker inspect -f '{{.Config.Image}}' "$CUR" | sed 's#redroid/redroid:##') =="
  [ -n "$P" ] || { bad "không thấy cổng trong phones.json"; continue; }
  [ "$(S 'getprop sys.boot_completed')" = 1 ] && ok "Android đã khởi động xong" || { bad "Android CHƯA khởi động xong"; continue; }
  TOP=$(S 'dumpsys activity activities | grep -m1 ResumedActivity' | sed 's/.* u0 //; s/ .*//')
  case "$TOP" in *setupwizard*) bad "Kẹt ở trình cài đặt Google (màn đen) → cloudphone update rồi chạy lại" ;; "") warn "Không đọc được màn hình đang mở" ;; *) ok "Màn hình đang mở: $TOP" ;; esac
  docker exec "$WS" adb connect "127.0.0.1:$P" >/dev/null 2>&1
  [ "$(A get-state)" = device ] && ok "Kết nối điều khiển (adb) OK" || { bad "adb không kết nối được → web không có hình"; continue; }
  PNGH=$(timeout 30 docker exec "$WS" adb -s "127.0.0.1:$P" exec-out screencap -p 2>/dev/null | head -c 8 | od -An -tx1 | tr -d ' \n')
  [ "$PNGH" = 89504e470d0a1a0a ] && ok "Chụp màn hình OK" || bad "Chụp màn hình lỗi"
  A shell input keyevent 224 >/dev/null && ok "Bấm phím (bật màn) OK" || bad "Bấm phím lỗi"
  A shell 'settings get system user_rotation' | grep -qE '^[0-3]$' && ok "Xoay màn hình: đọc được cài đặt" || warn "Không đọc được cài đặt xoay"
  # máy đang mở app (khách đang dùng) → KHÔNG mở app thử để khỏi phá khách
  IDLE=0; case "$TOP" in *launcher*|*Launcher*|*quickstep*) IDLE=1 ;; esac
  [ $IDLE = 1 ] || warn "Máy đang mở app ($TOP) — bỏ qua phần mở app thử để không làm phiền khách"
  # cài APK ngoài
  if S 'pm path shop.blueroblox.app' | grep -q package; then warn "Máy đã có sẵn app BlueRoblox — bỏ qua thử cài để không gỡ mất app của khách"
  elif docker exec "$WS" test -f /tmp/selftest.apk; then
    O=$(timeout 300 docker exec "$WS" adb -s "127.0.0.1:$P" install -r -g /tmp/selftest.apk 2>&1 | tr -d '\r' | tail -1)
    if [ "$O" = Success ]; then
      TESTPKG=shop.blueroblox.app
      ok "TẢI + CÀI APK ngoài OK (${TESTPKG:-?})"
      if [ $IDLE = 1 ]; then S "monkey -p $TESTPKG -c android.intent.category.LAUNCHER 1" >/dev/null; sleep 4
        S "pidof $TESTPKG" >/dev/null && ok "Mở app vừa cài: chạy được" || bad "App vừa cài mở ra bị văng"
        S "am force-stop $TESTPKG; input keyevent 3"
      fi
      A uninstall "$TESTPKG" | grep -q Success && ok "Gỡ app thử OK" || warn "Chưa gỡ được $TESTPKG"
    else bad "Cài APK ngoài lỗi: $O"; fi
  fi
  # chép file vào Download (nút Tải file với file không phải APK)
  echo "blueroblox selftest" > "$T/selftest.txt"; docker cp "$T/selftest.txt" "$WS:/tmp/selftest.txt" >/dev/null 2>&1
  A push /tmp/selftest.txt /data/local/tmp/selftest.txt >/dev/null; A shell 'cp /data/local/tmp/selftest.txt /sdcard/Download/selftest.txt; rm -f /data/local/tmp/selftest.txt' >/dev/null; [ "$(A shell cat /sdcard/Download/selftest.txt)" = "blueroblox selftest" ] && ok "Chép file vào thư mục Download OK" || bad "Chép file vào Download lỗi"
  A shell rm -f /sdcard/Download/selftest.txt >/dev/null
  # root
  R1=$(timeout 20 docker exec --user 2000 "$CUR" /system/xbin/su -c id 2>&1 | tr -d '\r')
  case "$R1" in *uid=0*) ok "Root (su) OK: app gọi su → uid=0" ;; *) bad "Root chưa chạy (bấm Root máy, hoặc: python3 ~/phonectl.py rootfix $CUR --force)" ;; esac
  # trình duyệt
  CH=$(S 'pm path com.android.chrome'); FF=$(S 'pm path org.mozilla.firefox')
  [ -n "$CH" ] && ok "Chrome đã cài" || { [ "$SDK" -lt 29 ] && warn "Chưa có Chrome (Android 9: cài từ CH Play rồi grab)" || bad "Chưa có Chrome"; }
  [ -n "$FF" ] && ok "Firefox đã cài" || warn "Chưa có Firefox"
  if [ -n "$CH" ] && [ $IDLE = 1 ]; then S 'am start -n com.google.android.apps.chrome.Main >/dev/null 2>&1 || monkey -p com.android.chrome 1 >/dev/null'; sleep 6
    S 'pidof com.android.chrome' >/dev/null && ok "Mở Chrome: chạy được" || bad "Chrome mở ra bị văng"; S 'am force-stop com.android.chrome; input keyevent 3'; fi
  # bộ dịch ARM
  ABI=$(S 'getprop ro.product.cpu.abilist'); case "$ABI" in *arm64*) ok "Chạy được app ARM 64-bit ($ABI)" ;; *armeabi*) warn "Chỉ chạy app ARM 32-bit ($ABI) — Roblox mới cần 64-bit" ;; *) bad "Không có bộ dịch ARM ($ABI) → Roblox không chạy" ;; esac
  S 'pm path com.roblox.client' | grep -q package && ok "Roblox đã cài" || warn "Roblox chưa cài (khách tự cài từ CH Play)"
  # clone tab
  S 'setprop fw.max_users 8' >/dev/null
  MU=$(S 'pm get-max-users' | tr -dc 0-9); FE=$(S 'pm list features' | grep -c managed_users)
  if [ "${MU:-1}" -gt 1 ] && [ "$FE" -gt 0 ]; then ok "Clone tab: sẵn sàng (tối đa $MU người dùng, có hồ sơ công việc)"
  else bad "Clone tab chưa dùng được (max_users=$MU, managed_users=$FE)"; fi
  # GPS
  if [ "$SDK" -ge 31 ]; then
    # chạy như nút GPS trên web: qua adb (người dùng "shell"), không phải root
    O=$(A shell 'appops set com.android.shell android:mock_location allow; cmd location providers add-test-provider gps 2>&1; cmd location providers set-test-provider-enabled gps true 2>&1; cmd location providers set-test-provider-location gps --location 21.0285,105.8542 2>&1; cmd location providers remove-test-provider gps 2>&1')
    echo "$O" | grep -qi "exception\|unknown\|error" && bad "GPS giả lỗi: $(echo "$O" | grep -iv '^\s*at ' | grep -v '^\s*$' | head -4 | tr '\n' ' ')" || ok "Đổi vị trí GPS OK"
  else warn "GPS giả cần Android 12+ (máy này Android $VER — nút báo khách rõ ràng)"; fi
  # mạng
  S 'ping -c1 -W3 8.8.8.8 >/dev/null 2>&1 && echo y' | grep -q y && ok "Có mạng Internet" || bad "Máy KHÔNG có mạng"
  # app văng gần đây
  CR=$(S 'logcat -d -b crash' | grep -E "Process:" | sed 's/.*Process: //; s/,.*//' | sort | uniq -c | sort -rn | head -3 | tr '\n' ';')
  [ -z "$CR" ] && ok "Không có app nào văng" || warn "App từng văng: $CR"
done

echo; echo "======================================"
echo -e " ${G}Đạt: $PASS${N}   ${Y}Lưu ý: $WARN${N}   ${R}Lỗi: $FAIL${N}"
[ "$FAIL" -gt 0 ] && echo -e " Các lỗi:$FAILS"
echo " → Gửi toàn bộ kết quả này cho Claude để sửa."
docker exec "$WS" rm -f /tmp/selftest.apk /tmp/selftest.txt >/dev/null 2>&1
