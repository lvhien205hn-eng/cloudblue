package shop.blueroblox.app;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashSet;
import java.util.Set;

/** Nhắc khách khi máy sắp hết hạn (trước 1 ngày và trước 1 giờ) — chạy cả khi app đang đóng. */
public class ExpiryAlarm extends BroadcastReceiver {
    private static final String CH = "expiry";

    private static SharedPreferences p(Context c) { return c.getSharedPreferences("expiry", Context.MODE_PRIVATE); }
    public static boolean enabled(Context c) { return p(c).getBoolean("on", true); }
    public static void setEnabled(Context c, boolean on) { p(c).edit().putBoolean("on", on).apply(); }

    private static PendingIntent pi(Context c, int code, String title, String text) {
        Intent i = new Intent(c, ExpiryAlarm.class).putExtra("title", title).putExtra("text", text).putExtra("code", code);
        return PendingIntent.getBroadcast(c, code, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    public static void cancelAll(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        Set<String> old = p(c).getStringSet("codes", new HashSet<>());
        for (String s : old) {
            try { am.cancel(pi(c, Integer.parseInt(s), "", "")); } catch (Exception ignored) { }
        }
        p(c).edit().putStringSet("codes", new HashSet<>()).apply();
    }

    /** Đặt lại lịch nhắc theo danh sách máy mới nhất. */
    public static void schedule(Context c, JSONArray phones) {
        cancelAll(c);
        if (!enabled(c) || phones == null) return;
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        Set<String> codes = new HashSet<>();
        long now = System.currentTimeMillis();
        for (int i = 0; i < phones.length(); i++) {
            JSONObject ph = phones.optJSONObject(i);
            if (ph == null || !"active".equals(ph.optString("status"))) continue;
            long exp = MainActivity.parseTime(ph.optString("expires_at"));
            if (exp <= now) continue;
            String name = ph.optString("name", "Máy");
            long[] at = {exp - 86400000L, exp - 3600000L};
            String[] txt = {
                    Ui.L("Còn 1 ngày nữa là hết hạn. Gia hạn để giữ máy và dữ liệu.", "Expires in 1 day. Renew to keep your phone and data."),
                    Ui.L("Còn 1 giờ nữa là hết hạn! Gia hạn ngay kẻo máy bị tạm dừng.", "Expires in 1 hour! Renew now.")};
            for (int k = 0; k < 2; k++) {
                if (at[k] <= now) continue;
                int code = (ph.optString("id") + k).hashCode();
                try {
                    am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at[k], pi(c, code, "⏰ " + name, txt[k]));
                    codes.add(String.valueOf(code));
                } catch (Exception ignored) { }
            }
        }
        p(c).edit().putStringSet("codes", codes).apply();
    }

    @Override
    public void onReceive(Context c, Intent i) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CH) == null)
            nm.createNotificationChannel(new NotificationChannel(CH, Ui.L("Nhắc hết hạn máy", "Expiry reminders"), NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH) : new Notification.Builder(c);
        b.setSmallIcon(R.drawable.ic_notify)
                .setContentTitle(i.getStringExtra("title"))
                .setContentText(i.getStringExtra("text"))
                .setStyle(new Notification.BigTextStyle().bigText(i.getStringExtra("text")))
                .setAutoCancel(true)
                .setContentIntent(open);
        try { nm.notify(i.getIntExtra("code", 1), b.build()); } catch (SecurityException ignored) { }
    }
}
