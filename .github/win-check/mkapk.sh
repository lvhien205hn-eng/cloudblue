#!/usr/bin/env bash
# 23/11 · app THỬ cho bộ thử tab cửa sổ nhỏ: vn.cloudblue.wintest1..5 — 1 màn, ÉP MÀN NGANG.
#   app 1, 2: khai báo KHÔNG đổi cỡ được (như game), app 3: đổi cỡ được (app thường) — nền màu + chữ "Tab N" + cỡ cửa sổ đang có.
#   app 4, 5: "GAME CŨ" — dựng khung hình 1 lần theo cỡ lúc mở, KHÔNG vẽ lại theo cỡ mới (như nhiều game thật → thu nhỏ bị TRÀN VIỀN):
#            khung vàng + chữ TRÁI / PHẢI sát 2 mép. app 4 khai báo không đổi cỡ, app 5 khai báo đổi cỡ được.
#   Mọi app ghi nhật ký (logcat thẻ wintest): mở (create + pid), cỡ khung, resume / pause / stop — để kiểm app có bị tắt / tải lại khi chạy nền.
#   Dựng bằng công cụ có sẵn của Android SDK trên máy GitHub (aapt2, d8, apksigner).
#   bash mkapk.sh <thư mục ra>     → <thư mục ra>/wintest1.apk … wintest5.apk
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
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.TextView;

public class Main extends Activity {
    int n, user;

    /** "Game cũ": dựng khung 1 lần theo cỡ lúc mở, không vẽ lại theo cỡ mới (cửa sổ nhỏ hơn → phần phải / dưới bị cắt = tràn viền). */
    static class Game extends View {
        final int n; int w0, h0; final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        Game(Context c, int n) { super(c); this.n = n; }
        @Override protected void onSizeChanged(int w, int h, int ow, int oh) {
            if (w0 == 0 && w > 0) { w0 = w; h0 = h; }
            Log.i("wintest", "n=" + n + " size=" + w + "x" + h + " frame=" + w0 + "x" + h0);
        }
        @Override protected void onDraw(Canvas c) {
            int w = w0 > 0 ? w0 : getWidth(), h = h0 > 0 ? h0 : getHeight();
            c.drawColor(0xff102a43);
            p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(16); p.setColor(0xffffc107);
            c.drawRect(8, 8, w - 8, h - 8, p);
            p.setStyle(Paint.Style.FILL); p.setColor(Color.WHITE); p.setTextSize(h / 8f);
            p.setTextAlign(Paint.Align.LEFT); c.drawText("TRÁI", 34, h / 2f, p);
            p.setTextAlign(Paint.Align.RIGHT); c.drawText("PHẢI", w - 34, h / 2f, p);
            p.setTextAlign(Paint.Align.CENTER); c.drawText("Game " + n, w / 2f, h / 4f, p);
            p.setTextSize(h / 13f); c.drawText(getWidth() + " x " + getHeight() + " · khung " + w + " x " + h, w / 2f, h * 0.82f, p);
        }
    }

    void log(String s) { Log.i("wintest", "n=" + n + " u=" + user + " " + s); }
    @Override protected void onResume() { super.onResume(); log("resume"); }
    @Override protected void onPause() { log("pause"); super.onPause(); }
    @Override protected void onStop() { log("stop"); super.onStop(); }
    @Override protected void onStart() { super.onStart(); log("start"); }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        String p = getPackageName();
        n = p.charAt(p.length() - 1) - '0';
        user = android.os.Process.myUid() / 100000;
        log("create pid=" + android.os.Process.myPid());
        if (n >= 4) { setContentView(new Game(this, n)); return; }
        final int n = this.n, user = this.user;
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
javac -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath "$PLAT" -d "$W/cls" "$W/src/vn/cloudblue/wintest/Main.java" 2>&1 | grep -v "^warning" || true
"$BT/d8" --min-api 24 --lib "$PLAT" --output "$W/dex" $(find "$W/cls" -name '*.class')
keytool -genkeypair -keystore "$W/k.jks" -storepass android -keypass android -alias k -keyalg RSA -keysize 2048 -validity 1000 -dname "CN=wintest" >/dev/null 2>&1
for n in 1 2 3 4 5; do
  RZ=false; case "$n" in 3|5) RZ=true;; esac            # app 3, 5: khai báo đổi cỡ được · app 1, 2, 4: không đổi cỡ (như game)
  cat > "$W/m$n.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="vn.cloudblue.wintest$n">
  <application android:label="Tab $n" android:theme="@android:style/Theme.Material.NoActionBar">
    <activity android:name="vn.cloudblue.wintest.Main" android:exported="true" android:screenOrientation="sensorLandscape"
              android:resizeableActivity="$RZ" android:configChanges="orientation|screenSize|smallestScreenSize|screenLayout|keyboardHidden">
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
