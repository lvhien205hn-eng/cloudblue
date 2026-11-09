#!/usr/bin/env bash
# =====================================================================
#  cloudphone-root.sh — ROOT cho máy Cloud Phone (Magisk, kiểu "bootless" dành cho redroid)
#    • Dựng thêm bản ROOT cho từng bản Android đang bán (giữ nguyên Google Play / bộ dịch ARM như cũ)
#    • Máy MỚI tạo sau đó tự có root. Máy ĐANG CÓ: chạy "apply" để chuyển sang bản root (giữ nguyên app + tài khoản)
#    • Trong máy có app Magisk: tool xin quyền root → hiện bảng "Cho phép" (Grant) → bấm là xong
#
#   bash cloudphone-root.sh su           # ★ ROOT AN TOÀN (khuyên dùng): app/tool gọi su là có root, KHÔNG làm văng app ARM
#   bash cloudphone-root.sh build        # (cũ) dựng bản Magisk — LÀM VĂNG app ARM, không dùng nữa
#   bash cloudphone-root.sh gpu          # root luôn máy GPU (Android 11 Emulator, dùng rootAVD) — vài phút
#   bash cloudphone-root.sh apply        # root NGAY mọi máy đang có (server cũng tự làm mỗi 5 phút)
#   bash cloudphone-root.sh apply TÊN    # chỉ 1 máy (VD: cp_761fa7e548)
#   bash cloudphone-root.sh check TÊN    # kiểm tra máy đã có root chưa
#   bash cloudphone-root.sh off          # máy MỚI không root nữa (máy đã root giữ nguyên)
#   bash cloudphone-root.sh undo         # TẮT ROOT + trả mọi máy về bản không root (khi root làm app văng)
# =====================================================================
set -u
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok() { echo -e "${G}✓${N} $*"; }; warn() { echo -e "${Y}!${N} $*"; }; err() { echo -e "${R}✗${N} $*"; }
[ "$(id -u)" = "0" ] && { err "Chạy bằng user thường (không sudo):  bash $0 ${1:-}"; exit 1; }
RS="$HOME/redroid-script"; CONF="$HOME/cloudphone.conf"; PC="python3 $HOME/phonectl.py"
conf_set() { touch "$CONF"; grep -v "^$1=" "$CONF" > "$CONF.tmp"; echo "$1=$2" >> "$CONF.tmp"; cat "$CONF.tmp" > "$CONF"; rm -f "$CONF.tmp"; chmod 600 "$CONF"; }
# các bản Android đang bán (giống phonectl.py)
BASES="redroid/redroid:12.0.0_mindthegapps_ndk redroid/redroid:10.0.0_gapps_houdini redroid/redroid:9.0.0_gapps_houdini redroid/redroid:11.0.0_gapps_ndk redroid/redroid:13.0.0_mindthegapps_houdini redroid/redroid:14.0.0_mindthegapps_houdini"

case "${1:-}" in
su)
  # ROOT AN TOÀN (khuyên dùng): su + dịch vụ root chạy nền trong máy. KHÔNG đổi Android, KHÔNG làm hỏng bộ dịch ARM (Roblox/Noka chạy bình thường)
  RAW="https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main"; S="$HOME/cloudphone-su"; mkdir -p "$S"
  echo "== 1) Tải bộ root (su) =="
  curl -fsSL -o "$S/su.new" "$RAW/cpsu-su.bin?t=$(date +%s)" && curl -fsSL -o "$S/cpsud.new" "$RAW/cpsu-daemon.bin?t=$(date +%s)" || { err "Không tải được — đã tải cpsu-su.bin + cpsu-daemon.bin lên GitHub chưa?"; exit 1; }
  file "$S/su.new" 2>/dev/null | grep -q ELF || head -c 4 "$S/su.new" | grep -q ELF || { err "File su tải về không đúng"; exit 1; }
  mv "$S/su.new" "$S/su"; mv "$S/cpsud.new" "$S/cpsud"; chmod 755 "$S/su" "$S/cpsud"; ok "Bộ root đã sẵn sàng"
  conf_set ROOT 1
  echo "== 2) Root mọi máy đang chạy (KHÔNG khởi động lại máy; máy nào đang dùng bản Magisk sẽ được trả về bản thường ~1 phút) =="
  $PC rootfix --all --force
  echo; ok "XONG: máy mới + máy cũ tự có root (server tự kiểm tra mỗi 5 phút, máy khởi động lại cũng tự bật lại root)." ;;

build)
  echo "== 1) Chuẩn bị công cụ (cần mật khẩu sudo) =="
  sudo apt-get install -y -qq git python3-venv python3-pip lzip unzip >/dev/null && ok "git, python"
  if [ -d "$RS/.git" ]; then git -C "$RS" pull -q; else git clone -q https://github.com/ayasa520/redroid-script "$RS"; fi && ok "redroid-script"
  [ -x "$RS/.venv/bin/python" ] || python3 -m venv "$RS/.venv"
  "$RS/.venv/bin/pip" install -q -r "$RS/requirements.txt" && ok "Thư viện python"

  echo "== 2) Tải + giải nén Magisk =="
  W="$HOME/.cache/cloudphone-root"; sudo rm -rf "$W"; mkdir -p "$W"
  (cd "$W" && sudo env "PYTHONPATH=$RS" "SUDO_USER=$USER" "$RS/.venv/bin/python" -c "import os,sys; sys.path.insert(0,'$RS'); from stuff.magisk import Magisk; Magisk().install()") > "$W.log" 2>&1
  [ -f "$W/magisk/system/etc/init/bootanim.rc" ] && ok "Magisk đã sẵn sàng" || { err "Chuẩn bị Magisk lỗi — xem: tail -30 $W.log"; exit 1; }
  sudo chown -R "$USER": "$W"
  printf 'COPY magisk /\n' > "$W/Dockerfile.part"

  echo "== 3) Dựng bản ROOT cho từng bản Android đang có =="
  n=0
  for B in $BASES; do
    docker image inspect "$B" >/dev/null 2>&1 || continue
    { echo "FROM $B"; cat "$W/Dockerfile.part"; } > "$W/Dockerfile"
    if docker build -q -t "${B}_root" "$W" >/dev/null 2>>"$W.log"; then ok "${B}_root"; n=$((n+1)); else err "Dựng ${B}_root lỗi — xem: tail -30 $W.log"; fi
  done
  [ $n -gt 0 ] || { err "Không dựng được bản nào"; exit 1; }
  conf_set ROOT 1
  sudo systemctl restart cloudphoned 2>/dev/null
  echo; ok "XONG: máy MỚI tạo từ giờ tự có root (Magisk)."
  echo "   Máy ĐANG CÓ: server tự root dần (mỗi 5 phút). Muốn root ngay tất cả:  bash $0 apply"
  echo "   Root luôn máy GPU:  bash $0 gpu" ;;

gpu)
  SDK="$HOME/android-sdk"; IMG_DIR="system-images/android-30/google_apis_playstore/x86_64"
  [ -f "$SDK/$IMG_DIR/ramdisk.img" ] || { err "Chưa có Android 11 cho máy GPU (chạy: bash ~/gpu-phone-test.sh install)"; exit 1; }
  export ANDROID_HOME="$SDK" ANDROID_SDK_ROOT="$SDK" ANDROID_ADB_SERVER_PORT=5038 PATH="$SDK/platform-tools:$PATH"
  echo "== 1) Tải rootAVD =="
  if [ -d "$HOME/rootAVD/.git" ]; then git -C "$HOME/rootAVD" pull -q; else git clone -q --depth 1 https://github.com/newbit1/rootAVD "$HOME/rootAVD"; fi && ok "rootAVD"
  [ -f "$SDK/$IMG_DIR/ramdisk.img.cloudphone-goc" ] || cp "$SDK/$IMG_DIR/ramdisk.img" "$SDK/$IMG_DIR/ramdisk.img.cloudphone-goc"
  ok "Đã sao lưu ramdisk gốc (khôi phục: bash $0 gpu-undo)"
  echo "== 2) Bật máy thử GPU (gputest) để vá =="
  bash "$HOME/gpu-phone-test.sh" start >/dev/null 2>&1
  adb -s emulator-5600 wait-for-device; sleep 5
  [ "$(adb -s emulator-5600 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] || { err "Máy thử GPU chưa lên (xem: bash ~/gpu-phone-test.sh check)"; exit 1; }
  echo "== 3) Vá root (Magisk) vào Android 11 của máy GPU — 2–5 phút, cứ để yên =="
  (cd "$HOME/rootAVD" && ANDROID_SERIAL=emulator-5600 ./rootAVD.sh "$IMG_DIR/ramdisk.img") > "$HOME/rootavd.log" 2>&1 < /dev/null
  if cmp -s "$SDK/$IMG_DIR/ramdisk.img" "$SDK/$IMG_DIR/ramdisk.img.cloudphone-goc"; then err "Vá chưa thành công — gửi: tail -40 ~/rootavd.log"; exit 1; fi
  touch "$HOME/.cloudphone-gpu-rooted"; ok "Đã vá root cho máy GPU"
  bash "$HOME/gpu-phone-test.sh" stop >/dev/null 2>&1
  echo "== 4) Khởi động lại các máy GPU đang chạy để nhận root =="
  for u in $(systemctl list-units --no-legend 'cloudgpu@*' | awk '{print $1}'); do sudo -n /usr/bin/systemctl restart "$u" && ok "$u"; done
  ok "XONG: máy GPU mới + cũ đều có root. Server tự cài app Magisk cho từng máy trong vài phút." ;;

gpu-undo)
  SDK="$HOME/android-sdk"; IMG_DIR="system-images/android-30/google_apis_playstore/x86_64"
  [ -f "$SDK/$IMG_DIR/ramdisk.img.cloudphone-goc" ] && cp "$SDK/$IMG_DIR/ramdisk.img.cloudphone-goc" "$SDK/$IMG_DIR/ramdisk.img" && rm -f "$HOME/.cloudphone-gpu-rooted" && ok "Đã trả máy GPU về không root (máy khởi động lại sẽ hết root)" ;;

apply)
  echo "== Root ngay ${2:-tất cả máy} — máy chưa root khởi động lại ~1 phút, app + tài khoản giữ nguyên =="
  if [ -n "${2:-}" ]; then $PC rootfix "$2" --force; else $PC rootfix --all --force; fi ;;

check)
  [ -n "${2:-}" ] || { err "Ghi tên máy:  bash $0 check cp_xxxxxxxx   (xem tên: python3 ~/phonectl.py list)"; exit 1; }
  img=$(docker inspect -f '{{.Config.Image}}' "$2" 2>/dev/null)
  echo "Image: ${img:-không thấy máy}"
  docker exec "$2" /system/bin/sh -c 'ls /sbin/magisk /system/etc/init/magisk/magisk 2>/dev/null; pm list packages 2>/dev/null | grep -i magisk; echo "su: $(which su 2>/dev/null)"' 2>/dev/null
  [[ "$img" == *_root ]] && ok "Máy đang chạy bản ROOT" || warn "Máy CHƯA root — chạy:  bash $0 apply $2" ;;

undo)
  conf_set ROOT 0
  echo "== Trả mọi máy về bản KHÔNG root (giữ nguyên app + tài khoản, mỗi máy khởi động lại ~1 phút) =="
  $PC unroot ${2:-} ;;

off)
  conf_set ROOT 0; sudo systemctl restart cloudphoned 2>/dev/null
  ok "Máy mới sẽ KHÔNG root nữa (máy đã root vẫn giữ nguyên)." ;;

*) sed -n '2,14p' "$0" ;;
esac
