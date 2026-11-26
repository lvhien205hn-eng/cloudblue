#!/usr/bin/env bash
# 23/11 · app THỬ cho bộ thử tab cửa sổ nhỏ: vn.cloudblue.wintest1..5 — 1 màn, ÉP MÀN NGANG.
#   app 1, 2: khai báo KHÔNG đổi cỡ được (như game), app 3: đổi cỡ được (app thường) — nền màu + chữ "Tab N" + cỡ cửa sổ đang có.
#   app 4, 5: "GAME CŨ" — dựng khung hình 1 lần theo cỡ lúc mở, KHÔNG vẽ lại theo cỡ mới (như nhiều game thật → thu nhỏ bị TRÀN VIỀN):
#            khung vàng + chữ TRÁI / PHẢI sát 2 mép. app 4 khai báo không đổi cỡ, app 5 khai báo đổi cỡ được.
#   Mọi app ghi nhật ký (logcat thẻ wintest): mở (create + pid), cỡ khung, resume / pause / stop — để kiểm app có bị tắt / tải lại khi chạy nền.
#   Dựng bằng công cụ có sẵn của Android SDK trên máy GitHub (aapt2, d8, apksigner).
#   bash mkapk.sh <thư mục ra>     → <thư mục ra>/wintest1.apk … wintest5.apk + cbxoay.apk (app trợ giúp xoay màn — cuối file)
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
                log("size=" + (r - l) + "x" + (bo - t));
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

# ---------------- 23/11d · APP TRỢ GIÚP XOAY MÀN vn.cloudblue.xoay (cbxoay.apk) ----------------
#   Máy MuMu bỏ qua khoá xoay của Android (mSupportAutoRotation=false) — màn chỉ xoay khi CÓ CỬA SỔ yêu cầu hướng. App này (không có biểu
#   tượng) chạy 1 dịch vụ đặt 1 cửa sổ phủ 1×1 trong suốt, không nhận chạm, yêu cầu màn NGANG → cả màn chính nằm ngang.
#   Bật:  appops set vn.cloudblue.xoay SYSTEM_ALERT_WINDOW allow; am start-foreground-service -n vn.cloudblue.xoay/.Svc --es o land
#   Tắt:  am force-stop vn.cloudblue.xoay          (máy khởi động lại lúc đang bật → tự bật lại: Boot)
#   Chỉ shell / hệ thống gọi được dịch vụ (quyền DUMP). cpapi cài file này từ ROT_APK_B64 (cpapi.py).
X="$W/xoay"; mkdir -p "$X/src/vn/cloudblue/xoay" "$X/cls" "$X/dex"
cat > "$X/src/vn/cloudblue/xoay/Svc.java" <<'EOF'
package vn.cloudblue.xoay;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;

public class Svc extends Service {
    static final String TAG = "cbxoay";
    View v;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public int onStartCommand(Intent i, int flags, int id) {
        SharedPreferences sp = getSharedPreferences("xoay", MODE_PRIVATE);
        String o = i != null ? i.getStringExtra("o") : null;
        if (o == null) o = sp.getString("o", "off");
        sp.edit().putString("o", o).commit();
        fg();
        apply(o);
        if (v == null) { stopForeground(true); stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }

    void fg() {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            nm.createNotificationChannel(new NotificationChannel("xoay", "Xoay man", NotificationManager.IMPORTANCE_MIN));
            b = new Notification.Builder(this, "xoay");
        } else b = new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_menu_rotate).setContentTitle("CloudBlue").setContentText("Man ngang").setOngoing(true);
        startForeground(1, b.build());
    }

    void apply(String o) {
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        if (v != null) { try { wm.removeView(v); } catch (Exception e) { } v = null; }
        if (!"land".equals(o) && !"port".equals(o)) { Log.i(TAG, "off"); return; }
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(1, 1,
                Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_SYSTEM_ALERT,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.LEFT;
        lp.screenOrientation = "land".equals(o) ? ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE : ActivityInfo.SCREEN_ORIENTATION_PORTRAIT;
        lp.setTitle("cbxoay");
        View nv = new View(this);
        try { wm.addView(nv, lp); v = nv; Log.i(TAG, "on " + o); }
        catch (Exception e) { Log.e(TAG, "addView: " + e); }
    }

    @Override public void onDestroy() {
        if (v != null) { try { ((WindowManager) getSystemService(WINDOW_SERVICE)).removeView(v); } catch (Exception e) { } v = null; }
        super.onDestroy();
    }
}
EOF
cat > "$X/src/vn/cloudblue/xoay/Boot.java" <<'EOF'
package vn.cloudblue.xoay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public class Boot extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        String o = c.getSharedPreferences("xoay", Context.MODE_PRIVATE).getString("o", "off");
        if ("off".equals(o)) return;
        Intent s = new Intent(c, Svc.class);
        try { if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(s); else c.startService(s); } catch (Exception e) { }
    }
}
EOF
cat > "$X/m.xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="vn.cloudblue.xoay" android:versionCode="1" android:versionName="1.0">
  <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW"/>
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
  <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED"/>
  <application android:label="CloudBlue Xoay" android:allowBackup="false" android:hasCode="true">
    <service android:name=".Svc" android:exported="true" android:permission="android.permission.DUMP"/>
    <receiver android:name=".Boot" android:exported="true">
      <intent-filter><action android:name="android.intent.action.BOOT_COMPLETED"/></intent-filter>
    </receiver>
  </application>
</manifest>
EOF
javac -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath "$PLAT" -d "$X/cls" "$X"/src/vn/cloudblue/xoay/*.java 2>&1 | grep -v "^warning" || true
"$BT/d8" --min-api 24 --lib "$PLAT" --output "$X/dex" $(find "$X/cls" -name '*.class')
"$BT/aapt2" link -o "$X/b.apk" -I "$PLAT" --manifest "$X/m.xml" --min-sdk-version 24 --target-sdk-version 30
(cd "$X/dex" && zip -q "$X/b.apk" classes.dex)
"$BT/zipalign" -f 4 "$X/b.apk" "$X/a.apk"
"$BT/apksigner" sign --ks "$W/k.jks" --ks-pass pass:android --key-pass pass:android --out "$OUT/cbxoay.apk" "$X/a.apk"
ls -la "$OUT"
