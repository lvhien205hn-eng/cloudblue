#!/usr/bin/env bash
# 23/11 · 3 app THỬ "giống Roblox" cho bộ thử tab cửa sổ nhỏ: vn.cloudblue.wintest1..3 — 1 màn, ÉP MÀN NGANG, khai báo KHÔNG đổi cỡ được
# (như game), nền màu riêng + chữ "Tab N" + cỡ cửa sổ đang có. Dựng bằng công cụ có sẵn của Android SDK trên máy GitHub (aapt2, d8, apksigner).
#   bash mkapk.sh <thư mục ra>     → <thư mục ra>/wintest1.apk … wintest3.apk
set -euo pipefail
OUT=${1:-/tmp/wintest}; mkdir -p "$OUT"; W=$(mktemp -d)
SDK=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/usr/local/lib/android/sdk}}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
PLAT=$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar
echo "build-tools: $BT · android.jar: $PLAT"
mkdir -p "$W/src/vn/cloudblue/wintest" "$W/cls" "$W/dex"
cat > "$W/src/vn/cloudblue/wintest/Main.java" <<'EOF'
package vn.cloudblue.wintest;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.TextView;

public class Main extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        String p = getPackageName();
        final int n = p.charAt(p.length() - 1) - '0';
        final int user = android.os.Process.myUid() / 100000;
        int[] col = {0xff444444, 0xff1e5aa8, 0xff2e8b57, 0xffb8860b, 0xff8b3a62};
        final TextView tv = new TextView(this);
        tv.setGravity(Gravity.CENTER);
        tv.setTextSize(26);
        tv.setTextColor(Color.WHITE);
        tv.setBackgroundColor(user != 0 ? 0xff6a1b9a : col[Math.max(0, Math.min(4, n))]);
        setContentView(tv);
        tv.addOnLayoutChangeListener(new View.OnLayoutChangeListener() {
            @Override public void onLayoutChange(View v, int l, int t, int r, int bo, int ol, int ot, int or, int ob) {
                tv.setText("Tab " + n + (user != 0 ? " (clone)" : "") + "\n" + (r - l) + " x " + (bo - t));
            }
        });
    }
}
EOF
javac -nowarn -source 8 -target 8 -bootclasspath "$PLAT" -d "$W/cls" "$W/src/vn/cloudblue/wintest/Main.java" 2>&1 | grep -v "^warning" || true
"$BT/d8" --min-api 24 --lib "$PLAT" --output "$W/dex" $(find "$W/cls" -name '*.class')
keytool -genkeypair -keystore "$W/k.jks" -storepass android -keypass android -alias k -keyalg RSA -keysize 2048 -validity 1000 -dname "CN=wintest" >/dev/null 2>&1
for n in 1 2 3; do
  cat > "$W/m$n.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="vn.cloudblue.wintest$n">
  <application android:label="Tab $n" android:theme="@android:style/Theme.Material.NoActionBar">
    <activity android:name="vn.cloudblue.wintest.Main" android:exported="true" android:screenOrientation="sensorLandscape"
              android:resizeableActivity="false" android:configChanges="orientation|screenSize|smallestScreenSize|screenLayout|keyboardHidden">
      <intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter>
    </activity>
  </application>
</manifest>
EOF
  "$BT/aapt2" link -o "$W/b$n.apk" -I "$PLAT" --manifest "$W/m$n.xml" --min-sdk-version 24 --target-sdk-version 30
  (cd "$W/dex" && zip -q "$W/b$n.apk" classes.dex)
  "$BT/zipalign" -f 4 "$W/b$n.apk" "$W/a$n.apk"
  "$BT/apksigner" sign --ks "$W/k.jks" --ks-pass pass:android --key-pass pass:android --out "$OUT/wintest$n.apk" "$W/a$n.apk"
done
ls -la "$OUT"
