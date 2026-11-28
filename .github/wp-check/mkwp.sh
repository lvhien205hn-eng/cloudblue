#!/usr/bin/env bash
# 28/11f · dựng cbwp.apk (app trợ giúp đặt ảnh nền CloudBlue vn.cloudblue.wp) bằng công cụ có sẵn của Android SDK trên máy GitHub
#   (javac, d8, aapt2, zipalign, apksigner). Khoá ký mới mỗi lần dựng — không sao: máy chủ cài → đặt ảnh nền → gỡ ngay, không cập nhật đè.
#   bash .github/wp-check/mkwp.sh <file ra>      (mặc định ./cbwp.apk)
set -euo pipefail
OUT=${1:-$PWD/cbwp.apk}
HERE=$(cd "$(dirname "$0")" && pwd); W=$(mktemp -d)
SDK=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/usr/local/lib/android/sdk}}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
PLAT=$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar
echo "build-tools: $BT · android.jar: $PLAT"
mkdir -p "$W/cls" "$W/dex"
javac -nowarn -encoding UTF-8 -source 8 -target 8 -Xlint:-options -bootclasspath "$PLAT" -d "$W/cls" "$HERE"/Svc.java
"$BT/d8" --release --min-api 24 --lib "$PLAT" --output "$W/dex" $(find "$W/cls" -name '*.class')
"$BT/aapt2" link -o "$W/b.apk" -I "$PLAT" --manifest "$HERE/AndroidManifest.xml" --min-sdk-version 24 --target-sdk-version 30
(cd "$W/dex" && zip -q "$W/b.apk" classes.dex)
"$BT/zipalign" -f 4 "$W/b.apk" "$W/a.apk"
keytool -genkeypair -keystore "$W/k.jks" -storepass android -keypass android -alias k -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=CloudBlue" >/dev/null 2>&1
"$BT/apksigner" sign --ks "$W/k.jks" --ks-pass pass:android --key-pass pass:android --out "$OUT" "$W/a.apk"
"$BT/apksigner" verify "$OUT"
ls -l "$OUT" && md5sum "$OUT"
rm -rf "$W"
