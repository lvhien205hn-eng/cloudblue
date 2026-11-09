#!/usr/bin/env bash
# =====================================================================
#  android-versions.sh — thêm ANDROID 9 và ANDROID 10 (có Google Play + bộ dịch ARM để chạy Roblox) cho máy chủ
#    Sau khi dựng xong, chạy lại  bash ~/cloudphone-root.sh build  để có bản ROOT cho 9 / 10.
#
#   bash android-versions.sh build      # dựng Android 9 + 10 (tải ~2–3GB, 15–30 phút)
#   bash android-versions.sh test       # bật 2 máy thử (cổng 5594 = A9, 5595 = A10) + kiểm tra Google Play / ARM / root
#   bash android-versions.sh roblox     # đọc lỗi Roblox trong máy thử (sau khi cài & mở Roblox)
#   bash android-versions.sh stop       # tắt + xoá 2 máy thử (giữ image)
#   bash android-versions.sh a12h       # Android 12 với bộ dịch ARM HOUDINI (thay libndk bị văng) + máy thử cổng 5596
#   bash android-versions.sh a12h-on    # dùng Android 12 Houdini cho MÁY MỚI + chuyển máy Android 12 đang có (giữ dữ liệu)
#   Xem màn hình máy thử: admin → https://phone.blueroblox.shop/ → thiết bị 127.0.0.1:5594 / 5595
# =====================================================================
set -u
RS="$HOME/redroid-script"; RX="$HOME/redroid-script-cp"
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
[ "$(id -u)" = "0" ] && { err "Chạy bằng user thường (không sudo):  bash $0 ${1:-}"; exit 1; }
# tên | phiên bản | image | cổng thử
LIST="atest9|9.0.0|redroid/redroid:9.0.0_gapps_houdini|5594
atest10|10.0.0|redroid/redroid:10.0.0_gapps_houdini|5595"
PROPS="ro.product.cpu.abilist=x86_64,arm64-v8a,x86,armeabi-v7a,armeabi ro.product.cpu.abilist64=x86_64,arm64-v8a ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi ro.dalvik.vm.isa.arm=x86 ro.dalvik.vm.isa.arm64=x86_64 ro.enable.native.bridge.exec=1 ro.enable.native.bridge.exec64=1 ro.vendor.enable.native.bridge.exec=1 ro.vendor.enable.native.bridge.exec64=1 ro.dalvik.vm.native.bridge=libhoudini.so"

case "${1:-}" in
build)
  echo "== Công cụ (cần mật khẩu sudo) =="
  sudo apt-get install -y -qq git python3-venv python3-pip lzip unzip rsync >/dev/null && ok "git, python"
  if [ -d "$RS/.git" ]; then git -C "$RS" pull -q; else git clone -q https://github.com/ayasa520/redroid-script "$RS"; fi && ok "redroid-script"
  [ -x "$RS/.venv/bin/python" ] || python3 -m venv "$RS/.venv"
  "$RS/.venv/bin/pip" install -q -r "$RS/requirements.txt" && ok "Thư viện python"
  # Bản sao riêng: mở thêm bộ dịch ARM (libhoudini đời Android 9) cho Android 10 — script gốc chưa hỗ trợ
  rm -rf "$RX"; rsync -a --exclude .git "$RS/" "$RX/"
  "$RS/.venv/bin/python" - "$RX" <<'PY'
import re, sys, os
d = sys.argv[1]
p = os.path.join(d, "stuff", "houdini.py"); s = open(p).read()
if '"10.0.0":' not in s:
    s = s.replace('        "11.0.0": [', '        "10.0.0":[\n            "https://github.com/rote66/vendor_intel_proprietary_houdini/archive/46682f423b8497db3f96222f2669d770eff764c3.zip",\n            "cd4dd2891aa18e7699d33dcc3fe3ffd4"],\n        "11.0.0": [', 1)
open(p, "w").write(s)
p = os.path.join(d, "stuff", "houdini_hack.py"); s = open(p).read()
s = s.replace('self.version), os.path.join(self.copy_dir, "system"), dirs_exist_ok=True)',
              '("9.0.0" if self.version == "10.0.0" else self.version)), os.path.join(self.copy_dir, "system"), dirs_exist_ok=True)')
s = s.replace('if not self.version == "9.0.0":', 'if self.version not in ("9.0.0", "10.0.0"):')
open(p, "w").write(s)
# Google Play: link LiteGapps cho Android 9/10 đã chết (tải về chỉ 51KB → lặp vô hạn) → dùng OpenGapps pico chính thức cho 9 / 10
p = os.path.join(d, "stuff", "gapps.py"); s = open(p).read()
if "CP_GAPPS_VER" not in s:
    s = s.replace('    copy_dir = "./gapps"', '''    _v = os.environ.get("CP_GAPPS_VER", "")
    if _v:
        dl_link = "https://sourceforge.net/projects/opengapps/files/%s/20220503/open_gapps-%s-%s-pico-20220503.zip" % (arch[0], arch[0], _v)
        dl_file_name = os.path.join(download_loc, "open_gapps-%s.zip" % _v)
        act_md5 = "ANY"
    copy_dir = "./gapps"''', 1)
open(p, "w").write(s)
p = os.path.join(d, "stuff", "general.py"); s = open(p).read()
if '"ANY"' not in s:
    s = s.replace("    def download(self):\n", '''    def download(self):
        if getattr(self, "act_md5", "") == "ANY":          # không có md5 → chỉ cần là file zip hợp lệ, tải lỗi thì DỪNG (không lặp vô hạn)
            if not (os.path.isfile(self.dl_file_name) and zipfile.is_zipfile(self.dl_file_name)):
                download_file(self.dl_link, self.dl_file_name)
            if not zipfile.is_zipfile(self.dl_file_name):
                raise SystemExit("Tai Google Play loi (file khong hop le): " + self.dl_link)
            return
''', 1)
open(p, "w").write(s)
p = os.path.join(d, "redroid.py"); s = open(p).read()
s = s.replace('if args.android in ["11.0.0"]:\n            Gapps().install()', 'if args.android in ["9.0.0", "10.0.0", "11.0.0"]:\n            Gapps().install()')
s = s.replace('["8.1.0", "9.0.0", "11.0.0", "12.0.0", "13.0.0", "14.0.0"]', '["8.1.0", "9.0.0", "10.0.0", "11.0.0", "12.0.0", "13.0.0", "14.0.0"]')
open(p, "w").write(s)
print("patched")
PY
  while IFS='|' read -r name ver img port; do
    if docker image inspect "$img" >/dev/null 2>&1; then ok "Đã có $img"; continue; fi
    echo "== Dựng Android ${ver%%.*} (Google Play OpenGapps + bộ dịch ARM Houdini) — 10–20 phút =="
    sudo pkill -f "redroid.py -a $ver" 2>/dev/null
    (cd "$RX" && sudo env "CP_GAPPS_VER=${ver%.0}" "$RS/.venv/bin/python" redroid.py -a "$ver" -g -i) > "$HOME/aver-build-$ver.log" 2>&1
    docker image inspect "$img" >/dev/null 2>&1 && ok "Dựng xong $img" || err "Dựng Android $ver lỗi — xem: tail -30 ~/aver-build-$ver.log"
  done <<< "$LIST"
  echo; ok "Xong. Tiếp theo:"
  echo "   1) Dựng bản ROOT cho 9/10:   bash ~/cloudphone-root.sh build"
  echo "   2) Thử máy:                   bash $0 test" ;;

test)
  lsmod | grep -qE '^binder' || sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
  while IFS='|' read -r name ver img port; do
    use="$img"; docker image inspect "${img}_root" >/dev/null 2>&1 && use="${img}_root"
    docker image inspect "$use" >/dev/null 2>&1 || { warn "Chưa có $img — chạy:  bash $0 build"; continue; }
    docker rm -f "$name" >/dev/null 2>&1; mkdir -p "$HOME/redroid/$name"
    docker run -itd --privileged --name "$name" --memory=5g --memory-swap=12g --cpus=4 \
      -v "$HOME/redroid/$name:/data" -p "127.0.0.1:$port:5555" "$use" \
      androidboot.redroid_width=720 androidboot.redroid_height=1280 androidboot.redroid_dpi=320 androidboot.redroid_fps=30 \
      $PROPS >/dev/null && ok "Bật $name (Android ${ver%%.*}) từ $use — cổng $port" || err "Không bật được $name"
  done <<< "$LIST"
  echo "   Đợi Android khởi động (tối đa 3 phút)..."
  for i in $(seq 1 36); do
    sleep 5; all=1
    while IFS='|' read -r name ver img port; do
      docker ps --format '{{.Names}}' | grep -qx "$name" || continue
      [ "$(docker exec "$name" getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] || all=0
    done <<< "$LIST"
    [ $all = 1 ] && break
  done
  while IFS='|' read -r name ver img port; do
    docker ps --format '{{.Names}}' | grep -qx "$name" || { warn "$name không chạy (xem: docker logs $name | tail)"; continue; }
    P=$(docker exec "$name" /system/bin/sh -c 'echo "boot=$(getprop sys.boot_completed) sdk=$(getprop ro.build.version.sdk) bridge=$(getprop ro.dalvik.vm.native.bridge)"; echo "google=$(pm list packages 2>/dev/null | grep -c -E "com.android.vending|com.google.android.gms")"; echo "magisk=$(ls /sbin/magisk 2>/dev/null)"; ls /system/lib64/libhoudini.so /system/lib/libhoudini.so 2>/dev/null | tr "\n" " "' 2>/dev/null | tr '\n' ' ')
    echo "== $name (Android ${ver%%.*}): $P"
    if [[ "$P" == boot=1* ]]; then
      docker exec wsscrcpy adb connect "127.0.0.1:$port" >/dev/null 2>&1
      ok "$name đã khởi động · xem: phone.blueroblox.shop → 127.0.0.1:$port · cài thử Roblox rồi chạy:  bash $0 roblox"
    else warn "$name chưa khởi động xong — chạy lại:  bash $0 test   (hoặc xem: docker logs $name | tail -30)"; fi
  done <<< "$LIST" ;;

roblox)
  while IFS='|' read -r name ver img port; do
    docker ps --format '{{.Names}}' | grep -qx "$name" || continue
    RB=$(docker exec "$name" /system/bin/pm list packages 2>/dev/null | grep -i roblox | cut -d: -f2 | tr -d '\r' | head -1)
    echo "=== $name (Android ${ver%%.*}): ${RB:-CHƯA CÀI ROBLOX}"
    [ -z "$RB" ] && continue
    docker exec "$name" /system/bin/logcat -d 2>/dev/null | grep -iE "roblox|FATAL|SIGSEGV|SIGILL|native.?bridge|houdini|unsupported|abort" | tail -20
  done <<< "$LIST" ;;

stop)
  while IFS='|' read -r name ver img port; do
    docker exec wsscrcpy adb disconnect "127.0.0.1:$port" >/dev/null 2>&1; docker rm -f "$name" >/dev/null 2>&1 && ok "Đã xoá máy thử $name"
    sudo rm -rf "$HOME/redroid/$name"
  done <<< "$LIST" ;;

a12h)
  IMG=redroid/redroid:12.0.0_mindthegapps_houdini
  if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    [ -x "$RS/.venv/bin/python" ] || { err "Chạy trước:  bash $0 build   (để có công cụ)"; exit 1; }
    echo "== Dựng Android 12 + Google Play + bộ dịch ARM Houdini (10–20 phút, đừng bấm Ctrl+C) =="
    (cd "$RS" && sudo "$RS/.venv/bin/python" redroid.py -a 12.0.0 -mtg -i) > "$HOME/a12h-build.log" 2>&1
    docker image inspect "$IMG" >/dev/null 2>&1 && ok "Dựng xong $IMG" || { err "Dựng lỗi — xem: tail -30 ~/a12h-build.log"; exit 1; }
  else ok "Đã có $IMG"; fi
  docker rm -f atest12h >/dev/null 2>&1; mkdir -p "$HOME/redroid/atest12h"
  docker run -itd --privileged --name atest12h --memory=5g --memory-swap=12g --cpus=4 -v "$HOME/redroid/atest12h:/data" -p 127.0.0.1:5596:5555 "$IMG" \
    androidboot.redroid_width=720 androidboot.redroid_height=1280 androidboot.redroid_dpi=320 androidboot.redroid_fps=30 $PROPS >/dev/null && ok "Bật máy thử atest12h"
  for i in $(seq 1 36); do sleep 5; [ "$(docker exec atest12h getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break; done
  docker exec wsscrcpy adb connect 127.0.0.1:5596 >/dev/null 2>&1
  ok "Máy thử Android 12 Houdini: phone.blueroblox.shop → 127.0.0.1:5596 — cài Noka / Roblox thử. Văng thì chạy:  docker exec atest12h logcat -d -b crash | tail -20" ;;

a12h-on)
  docker image inspect redroid/redroid:12.0.0_mindthegapps_houdini >/dev/null 2>&1 || { err "Chạy trước:  bash $0 a12h"; exit 1; }
  C="$HOME/cloudphone.conf"; grep -q '^A12_ARM=houdini' "$C" || echo "A12_ARM=houdini" >> "$C"
  ok "Máy Android 12 MỚI sẽ dùng Houdini. Chuyển máy Android 12 đang có (giữ app + tài khoản, mỗi máy khởi động lại ~1 phút):"
  python3 "$HOME/phonectl.py" unroot
  docker rm -f atest12h >/dev/null 2>&1; true ;;

*) sed -n '2,13p' "$0" ;;
esac
