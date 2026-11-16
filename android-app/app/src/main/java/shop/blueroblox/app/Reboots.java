package shop.blueroblox.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONObject;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

/** 16/11c — KHỞI ĐỘNG LẠI CHẠY NGẦM. Khách bấm khởi động lại (đổi FPS / sửa máy) rồi thoát màn, thoát app cũng được:
 *  - việc chạy trên MÁY CHỦ (không phụ thuộc app); app chỉ theo dõi ở luồng riêng, không gắn với màn nào;
 *  - nhớ máy nào đang khởi động lại (≤ 5 phút, lưu cả khi app bị tắt) → thẻ máy hiện "🔄 Đang khởi động lại…", màn điều khiển báo chờ;
 *  - xong mà khách không mở app → thông báo "Máy … đã khởi động lại xong — bấm để vào". */
final class Reboots {
    private Reboots() { }
    static final long WIN = 5 * 60_000L;
    private static final String CH = "reboot";
    private static final Map<String, Long> RUN = new ConcurrentHashMap<>();           // máy đang được app theo dõi (luồng còn chạy)
    interface Watch { void changed(String pid, boolean done, boolean ok, String msg); }
    private static final List<Watch> WATCH = new CopyOnWriteArrayList<>();
    static volatile int visible = 0;                                                  // số màn của app đang hiện (MainActivity / ControlActivity)

    static void listen(Watch w) { if (w != null && !WATCH.contains(w)) WATCH.add(w); }
    static void unlisten(Watch w) { WATCH.remove(w); }
    private static void fire(String pid, boolean done, boolean ok, String msg) { for (Watch w : WATCH) Api.ui(() -> w.changed(pid, done, ok, msg)); }

    private static SharedPreferences sp(Context c) { return c.getApplicationContext().getSharedPreferences("reboots", Context.MODE_PRIVATE); }
    /** Lúc bắt đầu khởi động lại máy pid (ms), 0 = không / đã quá 5 phút. */
    static long since(Context c, String pid) {
        if (pid == null) return 0;
        Long r = RUN.get(pid);
        long t = r != null ? r : sp(c).getLong(pid, 0);
        return t > 0 && System.currentTimeMillis() - t < WIN ? t : 0;
    }
    static boolean active(Context c, String pid) { return since(c, pid) > 0; }
    /** App đang theo dõi việc khởi động lại máy này (luồng còn chạy trong app)? */
    static boolean running(String pid) { return pid != null && RUN.containsKey(pid); }
    private static void mark(Context c, String pid, long t) {
        SharedPreferences.Editor e = sp(c).edit();
        if (t > 0) e.putLong(pid, t); else e.remove(pid);
        e.apply();
    }

    /** Khởi động lại máy pid: hỏi máy chủ (base rỗng → tự hỏi cloudphone_endpoint) → POST …/reboot → theo dõi việc tới xong.
     *  step / done / fail chạy trên luồng giao diện (nơi gọi tự kiểm màn còn sống). Khách rời màn / thoát app: việc vẫn chạy trên máy chủ. */
    static void start(Context ctx, String pid, String name, String base0, Api.Cb<String> step, Api.Cb<String> done, Api.Err fail) {
        final Context app = ctx.getApplicationContext();
        final long t0 = System.currentTimeMillis();
        RUN.put(pid, t0); mark(app, pid, t0); fire(pid, false, true, "");
        Api.bgLong(() -> {
            String base = base0 == null ? "" : base0;
            if (base.isEmpty()) {
                Object o = Api.rpc("cloudphone_endpoint", new JSONObject().put("p_id", pid));
                JSONObject ep = o instanceof JSONObject ? (JSONObject) o : new JSONObject(), s = ep.optJSONObject("stream");
                String a = s == null || s.isNull("api") ? "" : s.optString("api", "").trim();
                base = a.startsWith("https://") ? a : "";
                Api.direct(base, s);
            }
            JSONObject j = Api.cpAt(base, "POST", pid + "/reboot", new JSONObject());
            String job = j.optString("job", "");
            if (job.isEmpty()) { Thread.sleep(45000); return ""; }                // máy chủ rất cũ (không trả mã việc) → chờ như trước
            int miss = 0;
            for (int i = 0; i < 240; i++) {                                         // tối đa ~6 phút
                Thread.sleep(1500);
                JSONObject q;
                try { q = Api.cpAt(base, "GET", "job?id=" + job, null); miss = 0; }
                catch (Exception e) { if (++miss >= 10) throw e; continue; }        // mạng chập chờn lúc hỏi → hỏi lại
                String st = q.optString("state"), msg = q.optString("msg");
                if ("done".equals(st)) return msg;
                if ("error".equals(st)) throw new Exception(msg.isEmpty() ? Ui.L("Chưa khởi động lại được.", "Couldn't restart.") : msg);
                if (!msg.isEmpty() && step != null) { final String m = msg; Api.ui(() -> step.ok(Ui.srvJob(m))); }
            }
            return "";
        }, msg -> {
            RUN.remove(pid); mark(app, pid, 0);
            String m = msg == null || msg.isEmpty() ? Ui.L("Máy đã khởi động lại xong.", "The phone has restarted.") : Ui.srvJob(msg);
            fire(pid, true, true, m);
            if (visible <= 0) notify(app, pid, name, true, m);
            if (done != null) done.ok(m);
        }, m -> {
            RUN.remove(pid); mark(app, pid, 0);
            String t = Ui.srv(m);
            fire(pid, true, false, t);
            if (visible <= 0) notify(app, pid, name, false, t);
            if (fail != null) fail.fail(t);
        });
    }

    /** Thông báo hệ thống khi khởi động lại xong mà khách không mở app (bấm → mở thẳng máy đó). */
    static void notify(Context c, String pid, String name, boolean ok, String msg) {
        try {
            Ui.loadLang(c);
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CH) == null)
                nm.createNotificationChannel(new NotificationChannel(CH, Ui.L("Máy khởi động lại xong", "Phone restarted"), NotificationManager.IMPORTANCE_DEFAULT));
            Intent it = new Intent(c, ControlActivity.class).putExtra("id", pid).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            PendingIntent open = PendingIntent.getActivity(c, pid.hashCode(), it, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            String nm2 = name == null || name.isEmpty() || "null".equals(name) ? Ui.L("Máy", "Phone") : name;
            String title = (ok ? "✅ " : "⚠ ") + nm2;
            String text = ok ? Ui.L("Đã khởi động lại xong — bấm để vào máy.", "Restarted — tap to open the phone.")
                    : Ui.L("Chưa khởi động lại được: ", "Couldn't restart: ") + msg;
            Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH) : new Notification.Builder(c);
            b.setSmallIcon(R.drawable.ic_notify).setContentTitle(title).setContentText(text)
                    .setStyle(new Notification.BigTextStyle().bigText(text)).setAutoCancel(true).setContentIntent(open);
            nm.notify(("rb" + pid).hashCode(), b.build());
        } catch (Exception ignored) { }
    }
}
