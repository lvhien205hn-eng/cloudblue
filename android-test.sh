#!/usr/bin/env bash
# =====================================================================
#  android-test.sh — THỬ NGHIỆM máy ảo Android 12 / 13 / 14 (có Google Play + bộ dịch ARM) để chạy Roblox
#  Chạy SONG SONG với hệ thống hiện tại, KHÔNG đụng máy khách (cổng 5591–5593, tên atest12/13/14).
#
#   bash android-test.sh build     # dựng 3 bản Android (tải ~3–5GB, 15–30 phút)
#   bash android-test.sh start     # bật 3 máy thử (4 nhân · 4GB · 720x1280 · 30 FPS)
#   bash android-test.sh check     # xem máy nào khởi động được, có Google Play, có bộ dịch ARM không
#   bash android-test.sh roblox    # đọc lỗi Roblox trong từng máy thử (sau khi đã cài & mở Roblox)
#   bash android-test.sh stop      # tắt 3 máy thử    ·   remove: xoá hẳn máy thử + dữ liệu
#  Xem màn hình: đăng nhập admin → https://phone.blueroblox.shop/ → thiết bị 127.0.0.1:5591 / 5592 / 5593
# =====================================================================
set -u
RS="$HOME/redroid-script"
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
[ "$(id -u)" = "0" ] && { err "Chạy bằng user thường (không sudo):  bash $0 ${1:-}"; exit 1; }

# tên | phiên bản | cờ dựng | bộ dịch ARM | cổng
TESTS="atest12|12.0.0|-mtg -n|ndk|5591
atest13|13.0.0|-mtg -i|houdini|5592
atest14|14.0.0|-mtg -i|houdini|5593"

img_of() { local v=$1 tr=$2; [ "$tr" = ndk ] && echo "redroid/redroid:${v}_mindthegapps_ndk" || echo "redroid/redroid:${v}_mindthegapps_houdini"; }
props() {   # thông số bộ dịch ARM (để app chỉ có bản ARM như Roblox cài & chạy được)
  local B="ro.product.cpu.abilist=x86_64,arm64-v8a,x86,armeabi-v7a,armeabi ro.product.cpu.abilist64=x86_64,arm64-v8a ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi ro.dalvik.vm.isa.arm=x86 ro.dalvik.vm.isa.arm64=x86_64 ro.enable.native.bridge.exec=1 ro.enable.native.bridge.exec64=1 ro.vendor.enable.native.bridge.exec=1 ro.vendor.enable.native.bridge.exec64=1"
  if [ "$1" = ndk ]; then echo "$B ro.dalvik.vm.native.bridge=libndk_translation.so ro.ndk_translation.version=0.2.3"
  else echo "$B ro.dalvik.vm.native.bridge=libhoudini.so"; fi
}

case "${1:-}" in
build)
  echo "== Công cụ (cần mật khẩu sudo) =="
  sudo apt-get install -y -qq git python3-venv python3-pip lzip unzip >/dev/null && ok "git, python, lzip"
  if [ -d "$RS/.git" ]; then git -C "$RS" pull -q; else git clone -q https://github.com/ayasa520/redroid-script "$RS"; fi && ok "redroid-script"
  python3 -m venv "$RS/.venv" && "$RS/.venv/bin/pip" install -q -r "$RS/requirements.txt" && ok "Thư viện python"
  while IFS='|' read -r name ver flags tr port; do
    img=$(img_of "$ver" "$tr")
    if docker image inspect "$img" >/dev/null 2>&1; then ok "Đã có $img"; continue; fi
    echo "== Dựng Android ${ver%%.*} ($tr) — vài phút =="
    (cd "$RS" && sudo "$RS/.venv/bin/python" redroid.py -a "$ver" $flags) > "$HOME/atest-build-$ver.log" 2>&1
    docker image inspect "$img" >/dev/null 2>&1 && ok "Dựng xong $img" || { err "Dựng Android $ver lỗi — xem: tail -30 ~/atest-build-$ver.log"; }
  done <<< "$TESTS"
  echo; ok "Xong. Chạy tiếp:  bash $0 start" ;;

start)
  lsmod | grep -qE '^binder' || sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
  while IFS='|' read -r name ver flags tr port; do
    img=$(img_of "$ver" "$tr")
    docker image inspect "$img" >/dev/null 2>&1 || { warn "Chưa có $img — chạy:  bash $0 build"; continue; }
    if docker ps --format '{{.Names}}' | grep -qx "$name"; then ok "$name đang chạy"; continue; fi
    docker rm -f "$name" >/dev/null 2>&1; mkdir -p "$HOME/redroid/$name"
    docker run -itd --privileged --name "$name" --memory=5g --memory-swap=12g --cpus=4 \
      -v "$HOME/redroid/$name:/data" -p "127.0.0.1:$port:5555" "$img" \
      androidboot.redroid_width=720 androidboot.redroid_height=1280 androidboot.redroid_dpi=320 androidboot.redroid_fps=30 \
      $(props "$tr") >/dev/null && ok "Bật $name (Android ${ver%%.*}, $tr) — cổng $port" || err "Không bật được $name"
  done <<< "$TESTS"
  echo "   Đợi 1–2 phút cho Android khởi động..."; sleep 60
  bash "$0" check ;;

check)
  while IFS='|' read -r name ver flags tr port; do
    docker ps --format '{{.Names}}' | grep -qx "$name" || { warn "$name: chưa chạy"; continue; }
    P=$(docker exec "$name" /system/bin/sh -c 'echo "boot=$(getprop sys.boot_completed) sdk=$(getprop ro.build.version.sdk) bridge=$(getprop ro.dalvik.vm.native.bridge) abi=$(getprop ro.product.cpu.abilist)"; pm list packages 2>/dev/null | grep -c -E "com.android.vending|com.google.android.gms"' 2>/dev/null | tr '\n' ' ')
    echo "== $name (Android ${ver%%.*}, $tr): $P"
    if [[ "$P" == boot=1* ]]; then
      docker exec wsscrcpy adb connect "127.0.0.1:$port" >/dev/null 2>&1
      docker exec "$name" /system/bin/sh -c 'settings put global window_animation_scale 0; settings put global transition_animation_scale 0; settings put global animator_duration_scale 0; settings put global stay_on_while_plugged_in 7; svc power stayon true' >/dev/null 2>&1
      ok "$name đã khởi động · xem tại phone.blueroblox.shop → 127.0.0.1:$port"
    else warn "$name chưa khởi động xong (đợi thêm rồi chạy lại check)"; fi
  done <<< "$TESTS" ;;

roblox)
  while IFS='|' read -r name ver flags tr port; do
    docker ps --format '{{.Names}}' | grep -qx "$name" || continue
    RB=$(docker exec "$name" /system/bin/pm list packages 2>/dev/null | grep -i roblox | cut -d: -f2 | tr -d '\r' | head -1)
    echo "=== $name (Android ${ver%%.*}, $tr): ${RB:-CHƯA CÀI ROBLOX}"
    [ -z "$RB" ] && continue
    docker exec "$name" /system/bin/logcat -d 2>/dev/null | grep -iE "roblox|FATAL|SIGSEGV|SIGILL|native.?bridge|houdini|ndk_translation|unsupported|abort" | tail -20
  done <<< "$TESTS" ;;

stop)
  while IFS='|' read -r name ver flags tr port; do
    docker exec wsscrcpy adb disconnect "127.0.0.1:$port" >/dev/null 2>&1; docker stop "$name" >/dev/null 2>&1 && ok "Đã tắt $name"
  done <<< "$TESTS" ;;

remove)
  bash "$0" stop >/dev/null 2>&1
  while IFS='|' read -r name ver flags tr port; do docker rm -f "$name" >/dev/null 2>&1; sudo rm -rf "$HOME/redroid/$name"; done <<< "$TESTS"
  ok "Đã xoá 3 máy thử (vẫn giữ image đã dựng; xoá image: docker rmi \$(docker images 'redroid/redroid:*_mindthegapps_*' -q))" ;;

*) sed -n '2,12p' "$0" ;;
esac
