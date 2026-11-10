package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.widget.Button;
import android.widget.LinearLayout;

import com.google.android.play.core.appupdate.AppUpdateInfo;
import com.google.android.play.core.appupdate.AppUpdateManager;
import com.google.android.play.core.appupdate.AppUpdateManagerFactory;
import com.google.android.play.core.install.model.AppUpdateType;
import com.google.android.play.core.install.model.UpdateAvailability;

/**
 * BẢN CH PLAY (vn.cloudblue.app) — cập nhật QUA GOOGLE PLAY.
 * Luật Google Play: app tải từ CH Play không được tự tải / cài APK, chỉ cập nhật bằng cơ chế của Google Play. Nên bản này:
 *  1) Hỏi Google Play xem có bản mới cho máy này không (thư viện In-App Updates).
 *  2) Có → hộp "Có bản cập nhật mới" (giống bản web) → bấm Cập nhật ngay → màn cập nhật của Google Play (tải, cài, mở lại app).
 *  3) App đã cũ (máy chủ báo APP_OUTDATED / thấp hơn mức admin đặt) → hộp "Bắt buộc cập nhật" không tắt được.
 *  Ngoài ra CH Play tự cập nhật app theo cài đặt của điện thoại (mặc định bật).
 * Cùng tên lớp + cùng hàm check(Activity, boolean) với bản web (src/web) → MainActivity / ControlActivity không phải sửa.
 */
public final class Updater {
    private static long lastCheck = 0, shownCode = 0, shownAt = 0;
    private static Dialog forcedDlg = null;
    private static final String P = "upd";
    private static final int REQ = 7301;

    /** Gọi khi mở app. manual = true: bấm "Kiểm tra cập nhật" (luôn báo kết quả). */
    public static void check(Activity a, boolean manual) {
        long now = System.currentTimeMillis();
        if (forcedDlg != null && forcedDlg.isShowing()) return;
        if (!manual && !Api.outdated && now - lastCheck < 10 * 60_000L) return;      // tự kiểm tra tối đa 10 phút/lần
        lastCheck = now;
        Api.bg(() -> {
            try { Api.site(); } catch (Exception ignored) { }          // bản tối thiểu admin đặt (settings.min_app_android)
            return Boolean.TRUE;
        }, ok -> ask(a, manual), m -> ask(a, manual));
    }

    private static void ask(Activity a, boolean manual) {
        if (a.isFinishing()) return;
        final AppUpdateManager m;
        try { m = AppUpdateManagerFactory.create(a.getApplicationContext()); }
        catch (Throwable t) { noPlay(a, manual); return; }
        try {
            m.getAppUpdateInfo().addOnSuccessListener(info -> {
                if (a.isFinishing()) return;
                boolean forced = Api.mustUpdate();
                int av = info.updateAvailability();
                if (av == UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS) { start(a, m, info); return; }   // đang cập nhật dở → mở lại màn cập nhật
                if (av != UpdateAvailability.UPDATE_AVAILABLE) {
                    if (forced) store(a, true);           // máy chủ bắt cập nhật mà CH Play chưa có bản mới cho máy này
                    else if (manual) Ui.toast(a, Ui.L("Bạn đang dùng bản mới nhất (v" + Api.version + ").", "You're on the latest version (v" + Api.version + ")."));
                    return;
                }
                long code = info.availableVersionCode();
                SharedPreferences sp = a.getSharedPreferences(P, Context.MODE_PRIVATE);
                if (!forced && !manual) {
                    if (sp.getLong("later_" + code, 0) > System.currentTimeMillis()) return;          // "Để sau" → 3 giờ không hỏi lại
                    if (shownCode == code && System.currentTimeMillis() - shownAt < 30 * 60_000L) return;
                }
                shownCode = code; shownAt = System.currentTimeMillis();
                offer(a, m, info, code, sp, forced);
            }).addOnFailureListener(e -> { if (!a.isFinishing()) noPlay(a, manual); });
        } catch (Throwable t) { noPlay(a, manual); }
    }

    /** Không hỏi được Google Play (máy không có CH Play / app không cài từ CH Play). */
    private static void noPlay(Activity a, boolean manual) {
        if (a.isFinishing()) return;
        if (Api.mustUpdate()) store(a, true);
        else if (manual) store(a, false);
    }

    private static void offer(Activity a, AppUpdateManager m, AppUpdateInfo info, long code, SharedPreferences sp, boolean forced) {
        LinearLayout c = Ui.col(a, 12);
        if (forced) c.addView(Ui.text(a, Ui.L("Bản app v" + Api.version + " đã cũ và không dùng được nữa.",
                "App version v" + Api.version + " is outdated and can no longer be used."), 14, 0xFFFF8A8A, true), Ui.fill());
        c.addView(Ui.muted(a, Ui.L("Đã có bản mới v1." + code + " trên CH Play. Bấm Cập nhật ngay — Google Play tải và cài, tài khoản và máy của bạn giữ nguyên.",
                "Version v1." + code + " is available on Google Play. Tap Update now — Google Play downloads and installs it; your account and phones stay the same.")));
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
            d.dismiss(); forcedDlg = null;
            if (!start(a, m, info)) openStore(a);        // không mở được màn cập nhật → mở trang app trên CH Play
        });
        d.show();
    }

    /** Màn cập nhật toàn màn hình của Google Play: tải + cài + tự mở lại app. */
    @SuppressWarnings("deprecation")
    private static boolean start(Activity a, AppUpdateManager m, AppUpdateInfo info) {
        try {
            if (!info.isUpdateTypeAllowed(AppUpdateType.IMMEDIATE)) return false;
            return m.startUpdateFlowForResult(info, AppUpdateType.IMMEDIATE, a, REQ);
        } catch (Exception e) { return false; }
    }

    /** Hộp mời mở CH Play (bắt buộc: không tắt được, chỉ Mở CH Play / Thoát app). */
    private static void store(Activity a, boolean forced) {
        if (forced && forcedDlg != null && forcedDlg.isShowing()) return;
        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, forced
                ? Ui.L("Bản app v" + Api.version + " đã cũ. Mở CH Play và bấm Cập nhật để dùng tiếp (bản mới có thể cần vài giờ mới hiện trên CH Play).",
                       "App version v" + Api.version + " is outdated. Open Google Play and tap Update to continue (a new version can take a few hours to appear).")
                : Ui.L("Mở CH Play để xem và cài bản mới nhất của CloudBlue.", "Open Google Play to get the latest CloudBlue version.")));
        LinearLayout r = Ui.row(a, 10);
        Button no = Ui.button(a, forced ? Ui.L("Thoát app", "Quit app") : Ui.L("Đóng", "Close"), Ui.GHOST);
        Button go = Ui.button(a, "▶ " + Ui.L("Mở CH Play", "Open Google Play"), Ui.PRIMARY);
        r.addView(no, Ui.weight(1));
        r.addView(go, Ui.weight(1.4f));
        c.addView(r, Ui.fill());
        Dialog d = Ui.sheet(a, forced ? "⛔ " + Ui.L("Bắt buộc cập nhật", "Update required") : "🔄 " + Ui.L("Cập nhật", "Updates"), c);
        if (forced) {
            d.setCancelable(false); d.setCanceledOnTouchOutside(false); forcedDlg = d;
            no.setOnClickListener(v -> { d.dismiss(); forcedDlg = null; a.finishAffinity(); });
        } else no.setOnClickListener(v -> d.dismiss());
        go.setOnClickListener(v -> openStore(a));       // bắt buộc: giữ hộp, quay lại app mà chưa cập nhật vẫn thấy hộp
        d.show();
    }

    /** Trang CloudBlue trên CH Play (ứng dụng CH Play; máy không có thì mở trên web). */
    static void openStore(Activity a) {
        String id = a.getPackageName();
        try { a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + id)).setPackage("com.android.vending")); return; }
        catch (Exception ignored) { }
        try { a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=" + id))); }
        catch (Exception e) { Ui.toast(a, Ui.L("Không mở được CH Play.", "Couldn't open Google Play.")); }
    }
}
