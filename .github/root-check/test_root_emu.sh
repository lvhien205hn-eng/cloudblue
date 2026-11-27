#!/bin/bash
# 27/11m · ROOT THEO APP (cpsu) trên máy Android THẬT của CI — thử đúng 2 file sẽ phát hành: windows/cpsu-x86_64 + windows/cpsu-su-x86_64.
#   API 28 = Android 9 (như LDPlayer 9: KHÔNG có /debug_ramdisk → bản cũ báo "INSTALL_FAIL copy" rồi "STOPPED")
#   API 31 = Android 12 (như MuMu: có /debug_ramdisk — phải chạy y như trước)
# Chạy: bash .github/root-check/test_root_emu.sh <api>  (máy ảo đã bật, adb nối sẵn)
set -u
API="${1:-?}"
SUM="${GITHUB_STEP_SUMMARY:-/dev/null}"
P=0; F=0
ck() { if [ "$2" = 1 ]; then P=$((P+1)); echo "- ✓ $1" | tee -a "$SUM"; else F=$((F+1)); echo "- ✗ $1 → $3" | tee -a "$SUM"; fi; }
echo "### Root theo app (cpsu) · Android API $API" | tee -a "$SUM"
echo "cpsu-x86_64 md5 \`$(md5sum windows/cpsu-x86_64 | cut -d' ' -f1)\` · cpsu-su-x86_64 md5 \`$(md5sum windows/cpsu-su-x86_64 | cut -d' ' -f1)\`" | tee -a "$SUM"
adb root >/dev/null 2>&1; sleep 4; adb wait-for-device
for i in $(seq 1 60); do [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break; sleep 2; done
adb push windows/cpsu-x86_64 /data/local/tmp/cpsu >/dev/null
adb push windows/cpsu-su-x86_64 /data/local/tmp/cpsu-su >/dev/null
adb push .github/root-check/dev_root.sh /data/local/tmp/dev_root.sh >/dev/null
OUT=$(adb shell sh /data/local/tmp/dev_root.sh 2>&1 | tr -d '\r')
echo "$OUT"
g() { echo "$OUT" | grep -m1 "^$1=" | cut -d= -f2-; }
INST=$(echo "$OUT" | sed -n '/^---INSTALL$/,/^---$/p')
{ echo '```'; echo "$OUT" | grep -E '^(ID|SE|ROOTMNT|HAD_DR|SYSSU|APPS|INSTALL_RC|STATUS|ROOTMNT2|DRMNT|SUP|SYS_IS_CPSU|APP1|APP2_RC|APP2|SHELL_UID|REINSTALL|BINDS|UNINSTALL|STATUS2|SYS_RESTORED)='; echo "$INST"; echo '```'; } >> "$SUM"
ck "adb là root (máy chủ chạy cpsu bằng quyền root)" "$([ "$(g ID)" = 0 ] && echo 1)" "$(g ID)"
ck "cpsu install → INSTALL_OK (không còn INSTALL_FAIL copy)" "$(echo "$INST" | grep -q INSTALL_OK && echo 1)" "$INST"
ck "daemon chạy sau install (hết lỗi 'Chưa bật được root: STOPPED')" "$(g STATUS | grep -q '^RUNNING' && echo 1)" "$(g STATUS)"
if [ "$(g HAD_DR)" = 0 ] && echo "$INST" | grep -q 'made=1'; then
  echo "Máy KHÔNG có /debug_ramdisk, \"/\" nằm trong RAM → cpsu tự tạo /debug_ramdisk (như LDPlayer 9)" | tee -a "$SUM"
  ck "/debug_ramdisk vừa tạo có tmpfs + su" "$([ -n "$(g DRMNT)" ] && [ "$(g SUP)" = /debug_ramdisk/su ] && echo 1)" "$(g DRMNT) · $(g SUP)"
  ck "\"/\" vẫn chỉ đọc như trước sau khi tạo (không để mở ghi)" "$([ "$(g ROOTMNT)" = "$(g ROOTMNT2)" ] && echo 1)" "$(g ROOTMNT) → $(g ROOTMNT2)"
elif [ "$(g HAD_DR)" = 0 ]; then
  echo "Máy KHÔNG có /debug_ramdisk, \"/\" KHÔNG nằm trong RAM → su để ở /data/adb/cpsu/bin, app tới su qua su hệ thống đã gắn đè" | tee -a "$SUM"
  ck "không tạo được /debug_ramdisk → vẫn INSTALL_OK, su ở /data/adb/cpsu/bin" "$(echo "$INST" | grep -q 'su kept in /data/adb/cpsu/bin' && echo 1)" "$INST"
  ck "\"/\" không bị mở ghi" "$([ "$(g ROOTMNT)" = "$(g ROOTMNT2)" ] && echo 1)" "$(g ROOTMNT) → $(g ROOTMNT2)"
else
  ck "máy có sẵn /debug_ramdisk → y như bản cũ (tmpfs=1, made=0)" "$(echo "$INST" | grep -q 'tmpfs=1 .*made=0' && echo 1)" "$INST"
fi
ck "su hệ thống được gắn đè bằng su của cpsu" "$([ "$(g SYS_IS_CPSU)" = 1 ] && echo 1)" "$(g SYS_IS_CPSU)"
ck "app ĐƯỢC chọn gọi su → root (uid 0)" "$(g APP1 | grep -qw 0 && echo 1)" "$(g APP1)"
ck "app KHÔNG được chọn gọi su → bị từ chối" "$([ "$(g APP2_RC)" != 0 ] && ! g APP2 | grep -qx '0 *' && echo 1)" "rc=$(g APP2_RC) $(g APP2)"
ck "adb shell (uid 2000) vẫn dùng được su (máy chủ quản lý máy)" "$(g SHELL_UID | grep -qw 0 && echo 1)" "$(g SHELL_UID)"
ck "cài lại lần 2 → INSTALL_OK, không gắn đè chồng (mỗi file 1 lần)" "$(g REINSTALL | grep -q INSTALL_OK && [ "$(g BINDS)" -le 2 ] && echo 1)" "$(g REINSTALL) binds=$(g BINDS)"
ck "tắt root (uninstall) → daemon dừng, su hệ thống trở lại như cũ" "$(g UNINSTALL | grep -q UNINSTALL_OK && g STATUS2 | grep -q STOPPED && [ "$(g SYS_RESTORED)" = 1 ] && echo 1)" "$(g UNINSTALL) / $(g STATUS2) / restored=$(g SYS_RESTORED)"
echo "**$P đạt · $F lỗi**" | tee -a "$SUM"
[ "$(g END)" = 1 ] && [ "$F" = 0 ]
