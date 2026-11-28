// 28/11f · cbwp.apk — app TRỢ GIÚP ĐẶT ẢNH NỀN CLOUDBLUE (vn.cloudblue.wp, không biểu tượng, không màn hình).
//   Android 13+ (MuMu Android 15): chép file vào /data/system/users/0/wallpaper* không còn hiện (MuMu 15 dùng KernelSU — lệnh su bị giấu với
//   adb shell nên không chép được; và Android mới đọc wallpaper_info.xml theo kiểu mới). App này xin quyền SET_WALLPAPER (quyền thường, cài
//   là có) rồi đặt ảnh nền bằng WallpaperManager như mọi app ảnh nền → Android tự cắt ảnh + vẽ lại ngay, KHÔNG khởi động lại giao diện,
//   KHÔNG cần root.
//   Máy chủ (phonectl): cài app → chép ảnh vào /sdcard/Android/data/vn.cloudblue.wp/files/wp.png → am start-foreground-service -n
//   vn.cloudblue.wp/.Svc [--ei if_id N] → đọc files/res.txt ("OK <id ảnh nền mới>" · "SKIP <id hiện tại>" · "ERR <lý do>") → gỡ app (ảnh nền
//   vẫn giữ). if_id: chỉ thay khi ảnh nền hiện tại vẫn là ảnh CloudBlue lần trước (id đó) — khách đã tự đổi ảnh nền thì giữ ảnh của khách.
//   Chỉ shell / hệ thống gọi được dịch vụ (quyền DUMP). Dựng + thử trên máy ảo Android 12 / 13 / 15 thật: .github/workflows/wp-check.yml.
package vn.cloudblue.wp;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.app.WallpaperManager;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;

public class Svc extends Service {
    static final String TAG = "cbwp";

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public int onStartCommand(Intent i, int flags, int startId) {
        fg();
        final int ifId = i != null ? i.getIntExtra("if_id", -1) : -1;
        final String fn = (i != null && i.getStringExtra("f") != null) ? i.getStringExtra("f") : "wp.png";
        new Thread(new Runnable() {
            @Override public void run() {
                String res;
                try { res = apply(fn, ifId); } catch (Throwable t) { res = "ERR " + t.getClass().getSimpleName() + ": " + t.getMessage(); }
                write(res);
                Log.i(TAG, res);
                try { stopForeground(true); } catch (Throwable t) { }
                stopSelf();
            }
        }).start();
        return START_NOT_STICKY;
    }

    void fg() {
        try {
            Notification.Builder b;
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
                nm.createNotificationChannel(new NotificationChannel("wp", "CloudBlue", NotificationManager.IMPORTANCE_MIN));
                b = new Notification.Builder(this, "wp");
            } else b = new Notification.Builder(this);
            b.setSmallIcon(android.R.drawable.ic_menu_gallery).setContentTitle("CloudBlue").setContentText("Wallpaper").setOngoing(true);
            startForeground(1, b.build());
        } catch (Throwable t) {
            Log.e(TAG, "startForeground: " + t);
        }
    }

    String apply(String fn, int ifId) throws Exception {
        WallpaperManager wm = WallpaperManager.getInstance(this);
        int cur = wm.getWallpaperId(WallpaperManager.FLAG_SYSTEM);
        if (ifId >= 0 && cur != ifId) return "SKIP " + cur;          // khách đã tự đổi ảnh nền → giữ
        File dir = getExternalFilesDir(null);
        File f = new File(dir, fn);
        if (!f.isFile() || f.length() < 64) return "ERR khong thay anh " + f;
        InputStream in = new FileInputStream(f);
        int nid;
        try {
            nid = wm.setStream(in, null, true, WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK);
        } finally {
            in.close();
        }
        if (nid <= 0) return "ERR setStream " + nid;
        int now = wm.getWallpaperId(WallpaperManager.FLAG_SYSTEM);
        return "OK " + (now > 0 ? now : nid) + " sdk=" + Build.VERSION.SDK_INT + " bytes=" + f.length();
    }

    void write(String s) {
        try {
            File o = new File(getExternalFilesDir(null), "res.txt");
            FileOutputStream w = new FileOutputStream(o);
            try { w.write((s + "\n").getBytes("UTF-8")); } finally { w.close(); }
        } catch (Throwable t) {
            Log.e(TAG, "ghi res.txt: " + t);
        }
    }
}
