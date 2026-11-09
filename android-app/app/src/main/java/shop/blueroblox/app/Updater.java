package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Tự cập nhật app ngay trong app (không cần lên web tải file):
 *  1) Đọc <web>/download/app.json (GitHub tự ghi mỗi lần build); web không vào được (tên miền hỏng…)
 *     thì đọc thẳng file đó trên GitHub (Api.GH_DL) → app luôn tự cập nhật được.
 *  2) Có bản mới → hiện thông báo "Cập nhật ngay".
 *  3) Bấm → app tự tải APK (có thanh %), rồi giao cho trình cài đặt của Android.
 * Android luôn hỏi xác nhận 1 lần ("Cập nhật") vì app không cài từ CH Play; lần đầu còn hỏi quyền
 * "Cho phép cài ứng dụng từ nguồn này". Từ Android 12, các lần sau có thể tự cập nhật không cần hỏi.
 */
public final class Updater {
    private static long lastCheck = 0, shownCode = 0, shownAt = 0;
    private static final String P = "upd";

    /** Mã phiên bản đang chạy (số build GitHub). */
    static long myCode(Context c) {
        try {
            PackageInfo pi = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) { return 0; }
    }

    private static Dialog forcedDlg = null;

    /** Gọi khi mở app. manual = true: bấm "Kiểm tra cập nhật" (luôn báo kết quả).
     *  App đã cũ (máy chủ báo APP_OUTDATED / thấp hơn mức admin đặt) → hộp "Bắt buộc cập nhật" KHÔNG tắt được, không có "Để sau". */
    public static void check(Activity a, boolean manual) {
        long now = System.currentTimeMillis();
        if (forcedDlg != null && forcedDlg.isShowing()) return;
        if (!manual && !Api.outdated && now - lastCheck < 10 * 60_000L) return;      // tự kiểm tra tối đa 10 phút/lần (mở app, quay lại app, vào máy)
        lastCheck = now;
        SharedPreferences sp = a.getSharedPreferences(P, Context.MODE_PRIVATE);
        Api.bg(() -> {
            try { Api.site(); } catch (Exception ignored) { }          // bản tối thiểu admin đặt (settings.min_app_android)
            Exception last = null;
            for (String base : order(null)) {
                try {
                    JSONObject j = readJson(base + "/app.json?t=" + System.currentTimeMillis());
                    if (j.optLong("code", 0) <= 0) throw new java.io.IOException("app.json sai");
                    return j.put("_src", base);
                } catch (Exception e) { last = e; }
            }
            throw last != null ? last : new java.io.IOException("no source");
        }, j -> {
            long code = j.optLong("code", 0);
            boolean forced = Api.mustUpdate();
            if (code <= myCode(a)) { if (manual) Ui.toast(a, Ui.L("Bạn đang dùng bản mới nhất (v" + Api.version + ").", "You're on the latest version (v" + Api.version + ").")); return; }
            if (a.isFinishing()) return;
            if (!forced) {
                // "Để sau" → không làm phiền lại trong 3 giờ (trừ khi tự bấm kiểm tra)
                if (!manual && sp.getLong("later_" + code, 0) > System.currentTimeMillis()) return;
                if (!manual && shownCode == code && System.currentTimeMillis() - shownAt < 30 * 60_000L) return;   // vừa báo bản này rồi
            }
            shownCode = code; shownAt = System.currentTimeMillis();
            offer(a, j, code, sp, forced);
        }, m -> { if (manual) Ui.toast(a, Ui.L("Không kiểm tra được cập nhật: ", "Couldn't check for updates: ") + m); });
    }

    private static void offer(Activity a, JSONObject j, long code, SharedPreferences sp, boolean forced) {
        LinearLayout c = Ui.col(a, 12);
        double mb = j.optLong("size", 0) / 1048576.0;
        if (forced) c.addView(Ui.text(a, Ui.L("Bản app v" + Api.version + " đã cũ và không dùng được nữa (không mở / thuê / gia hạn máy được).",
                "App version v" + Api.version + " is outdated and can no longer be used."), 14, 0xFFFF8A8A, true), Ui.fill());
        c.addView(Ui.muted(a, Ui.L("Đã có bản mới v" + j.optString("version", "?") + " (" + String.format(java.util.Locale.ROOT, "%.1f", mb) + " MB). "
                        + "Bấm Cập nhật ngay — app tự tải và cài, tài khoản và máy của bạn giữ nguyên.",
                "Version v" + j.optString("version", "?") + " is available (" + String.format(java.util.Locale.ROOT, "%.1f", mb) + " MB). "
                        + "Tap Update now — the app downloads and installs it; your account and phones stay the same.")));
        ProgressBar bar = new ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100); bar.setVisibility(android.view.View.GONE);
        c.addView(bar, Ui.fill());
        TextView st = Ui.text(a, "", 13, Ui.MUTED, false);
        st.setVisibility(android.view.View.GONE);
        c.addView(st, Ui.fill());
        LinearLayout r = Ui.row(a, 10);
        Button later = Ui.button(a, forced ? Ui.L("Thoát app", "Quit app") : Ui.L("Để sau", "Later"), Ui.GHOST);
        Button go = Ui.button(a, "⬇️ " + Ui.L("Cập nhật ngay", "Update now"), Ui.PRIMARY);
        r.addView(later, Ui.weight(1));
        r.addView(go, Ui.weight(1.4f));
        c.addView(r, Ui.fill());
        Dialog d = Ui.sheet(a, forced ? "⛔ " + Ui.L("Bắt buộc cập nhật", "Update required") : "🚀 " + Ui.L("Có bản cập nhật mới", "Update available"), c);
        if (forced) {
            d.setCancelable(false); d.setCanceledOnTouchOutside(false); forcedDlg = d;
            later.setOnClickListener(v -> { d.dismiss(); forcedDlg = null; a.finishAffinity(); });
        } else later.setOnClickListener(v -> { sp.edit().putLong("later_" + code, System.currentTimeMillis() + 3 * 3600_000L).apply(); d.dismiss(); });
        go.setOnClickListener(v -> {
            // Lần đầu: Android yêu cầu cho phép app này cài ứng dụng
            if (Build.VERSION.SDK_INT >= 26 && !a.getPackageManager().canRequestPackageInstalls()) {
                Ui.toast(a, Ui.L("Bật \"Cho phép từ nguồn này\" rồi quay lại bấm Cập nhật ngay.", "Enable \"Allow from this source\", then come back and tap Update now."));
                try { a.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.getPackageName()))); } catch (Exception ignored) { }
                return;
            }
            go.setEnabled(false); later.setEnabled(false); d.setCancelable(false);
            bar.setVisibility(android.view.View.VISIBLE); st.setVisibility(android.view.View.VISIBLE);
            st.setText(Ui.L("Đang tải bản mới…", "Downloading…"));
            download(a, j.optString("_src", null), bar, st, () -> { d.dismiss(); forcedDlg = null; }, m -> { go.setEnabled(true); later.setEnabled(true); d.setCancelable(!forced); st.setText(m); });
        });
        d.show();
    }

    interface Done { void run(); }
    interface Fail { void run(String m); }

    /** Thứ tự nguồn tải: nguồn vừa đọc được app.json trước, rồi web, rồi GitHub. */
    private static String[] order(String first) {
        java.util.LinkedHashSet<String> s = new java.util.LinkedHashSet<>();
        if (first != null && first.startsWith("https://")) s.add(first);
        s.add(Api.WEB + "/download");
        s.add(Api.GH_DL);
        return s.toArray(new String[0]);
    }

    private static JSONObject readJson(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(8000); c.setReadTimeout(10000); c.setUseCaches(false);
        try {
            if (c.getResponseCode() != 200) throw new java.io.IOException("HTTP " + c.getResponseCode());
            try (InputStream in = c.getInputStream()) {
                java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream(); byte[] b = new byte[4096]; int n;
                while ((n = in.read(b)) > 0) bo.write(b, 0, n);
                return new JSONObject(bo.toString("UTF-8"));
            }
        } finally { c.disconnect(); }
    }

    /** Tải APK (thử lần lượt các nguồn) thẳng vào phiên cài đặt của Android (không cần lưu file ra bộ nhớ). */
    private static void download(Activity a, String src, ProgressBar bar, TextView st, Done ok, Fail fail) {
        Api.bg(() -> {
            Exception last = null;
            for (String base : order(src)) {
                try { install(a, base + "/blueroblox-cloud.apk?t=" + System.currentTimeMillis(), bar, st); return Boolean.TRUE; }
                catch (Exception e) { last = e; }
            }
            throw last != null ? last : new java.io.IOException("no source");
        }, r -> { st.setText(Ui.L("Đang mở trình cài đặt… bấm \"Cập nhật\" để hoàn tất.", "Opening installer… tap \"Update\" to finish.")); ok.run(); },
           m -> fail.run(Ui.L("Tải bản mới bị lỗi: ", "Download failed: ") + m + Ui.L(" — thử lại nhé.", " — please try again.")));
    }

    private static void install(Activity a, String url, ProgressBar bar, TextView st) throws Exception {
        PackageInstaller pi = a.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams sp = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        sp.setAppPackageName(a.getPackageName());
        if (Build.VERSION.SDK_INT >= 31) sp.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        int id = pi.createSession(sp);
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000); c.setReadTimeout(30000); c.setUseCaches(false);
        boolean committed = false;
        try (PackageInstaller.Session s = pi.openSession(id)) {
            if (c.getResponseCode() != 200) throw new java.io.IOException("HTTP " + c.getResponseCode());
            long total = c.getContentLengthLong();
            try (InputStream in = c.getInputStream()) {
                OutputStream out = s.openWrite("base.apk", 0, total > 0 ? total : -1);
                byte[] b = new byte[65536]; long done = 0; int n, last = -1;
                while ((n = in.read(b)) > 0) {
                    out.write(b, 0, n); done += n;
                    final int pct = total > 0 ? (int) (done * 100 / total) : -1;
                    if (pct != last) { last = pct; Api.ui(() -> { if (pct >= 0) { bar.setProgress(pct); st.setText(Ui.L("Đang tải… ", "Downloading… ") + pct + "%"); } }); }
                }
                if (total > 0 && done != total) throw new java.io.IOException("tải thiếu " + done + "/" + total);
                s.fsync(out);
                out.close();
            }
            Intent i = new Intent(a, Updater.Result.class);
            int fl = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
            s.commit(PendingIntent.getBroadcast(a, id, i, fl).getIntentSender());
            committed = true;
        } finally {
            c.disconnect();
            if (!committed) try { pi.abandonSession(id); } catch (Exception ignored) { }
        }
    }

    /** Nhận kết quả cài: cần người dùng xác nhận → mở hộp "Cập nhật" của Android. */
    public static class Result extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirm = i.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) { confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); try { c.startActivity(confirm); } catch (Exception ignored) { } }
            } else if (status != PackageInstaller.STATUS_SUCCESS) {
                String m = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                android.widget.Toast.makeText(c, Ui.L("Chưa cập nhật được", "Update not installed") + (m != null ? ": " + m : ""), android.widget.Toast.LENGTH_LONG).show();
            }
        }
    }
}
