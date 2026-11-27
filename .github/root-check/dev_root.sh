# Chạy TRONG máy Android của CI (adb root) — in KEY=VALUE cho test_root_emu.sh đọc. Không cần awk (Android 9 không có).
D=/data/adb/cpsu
T=/data/local/tmp
echo "ID=$(id -u)"
echo "SE=$(getenforce 2>/dev/null)"
echo "ROOTMNT=$(grep ' / ' /proc/mounts | tail -1)"
echo "HAD_DR=$([ -d /debug_ramdisk ] && echo 1 || echo 0)"
mkdir -p $D && chmod 700 $D
cp $T/cpsu $D/cpsu && cp $T/cpsu-su $D/su && chmod 755 $D/cpsu $D/su
SYS=""; for s in /system/xbin/su /system/bin/su; do [ -f $s ] && { SYS=$s; break; }; done
echo "SYSSU=$SYS"
[ -n "$SYS" ] && cp $SYS $T/aosp_su && chmod 755 $T/aosp_su
M0=$([ -n "$SYS" ] && md5sum $SYS | cut -d' ' -f1)
A1=""; U1=""; A2=""; U2=""
while read pkg uid rest; do
  case "$uid" in ''|*[!0-9]*) continue;; esac
  [ "$uid" -ge 10000 ] && [ "$uid" -lt 19999 ] || continue
  if [ -z "$A1" ]; then A1=$pkg; U1=$uid
  elif [ "$uid" != "$U1" ]; then A2=$pkg; U2=$uid; break; fi
done < /data/system/packages.list
echo "APPS=$A1:$U1 $A2:$U2"
echo "$A1" > $D/allow && chmod 600 $D/allow
echo "---INSTALL"
$D/cpsu install --dir $D --bind /system/xbin/su,/system/bin/su --notify 2>&1
echo "INSTALL_RC=$?"
echo "---"
echo "STATUS=$($D/cpsu status --dir $D 2>&1)"
echo "ROOTMNT2=$(grep ' / ' /proc/mounts | tail -1)"
echo "DRMNT=$(grep ' /debug_ramdisk ' /proc/mounts | tail -1)"
SUP=/debug_ramdisk/su; [ -x $SUP ] || SUP=$SYS
echo "SUP=$SUP"
[ -n "$SYS" ] && echo "SYS_IS_CPSU=$([ "$(md5sum $SYS | cut -d' ' -f1)" = "$(md5sum $D/su | cut -d' ' -f1)" ] && echo 1 || echo 0)"
if [ -x $T/aosp_su ] && [ -n "$U1" ]; then
  echo "APP1=$($T/aosp_su $U1 $SUP -c 'id -u' 2>&1 | tr '\n' ' ')"
  [ -n "$U2" ] && { O=$($T/aosp_su $U2 $SUP -c 'id -u' 2>&1); echo "APP2_RC=$?"; echo "APP2=$(echo "$O" | tr '\n' ' ')"; }
  echo "SHELL_UID=$($T/aosp_su 2000 $SUP -c 'id -u' 2>&1 | tr '\n' ' ')"
fi
echo "LOG=$(tail -n 3 $D/log 2>/dev/null | tr '\n' '|')"
echo "REINSTALL=$($D/cpsu install --dir $D --bind /system/xbin/su,/system/bin/su 2>&1 | tr '\n' ' ')"
echo "BINDS=$(grep -c '^bind ' $D/mounts 2>/dev/null)"
echo "UNINSTALL=$($D/cpsu uninstall --dir $D 2>&1 | tr '\n' ' ')"
sleep 1
echo "STATUS2=$($D/cpsu status --dir $D 2>&1)"
[ -n "$SYS" ] && echo "SYS_RESTORED=$([ "$(md5sum $SYS | cut -d' ' -f1)" = "$M0" ] && echo 1 || echo 0)"
echo "END=1"
