package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.widget.Button;
import android.widget.LinearLayout;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/** 🔒 Chống app bị sửa / đóng gói lại (bản 1.115 — 10/11/2026).
 *  App chính thức (bản web shop.blueroblox.app tải từ cloudblue.vn) luôn được ký bằng khoá của shop. Ai sửa app (đổi chữ số dư,
 *  đổi số tài khoản trong mã QR nạp tiền, gắn mã độc…) rồi phát tán thì BẮT BUỘC phải ký lại bằng khoá khác → app nhận ra,
 *  CHẶN mọi kết nối tới máy chủ (Api.http) và hiện hộp báo khách gỡ ra cài bản chính thức.
 *  Hai mã dưới là dấu vân tay SHA-256 của CHỨNG CHỈ ký — công khai, ai cũng đọc được từ file APK, KHÔNG phải khoá bí mật.
 *  Bản CH Play (vn.cloudblue.app) do Google ký lại nên không kiểm ở đây — Google Play tự bảo vệ bản của họ.
 *  An toàn cho khách thật: chỉ chặn khi đọc được chữ ký và chắc chắn sai; đọc lỗi → coi như chính thức (không bao giờ chặn nhầm). */
final class Guard {
    private static final String[] OFFICIAL = {
            "c1c3f3bf64d4672091d43da7edbecfbf260b6d886d8438e7d247284ee816fc24",   // khoá mới — app 1.101 trở đi
            "1a48230206ea270211c562613489cd788daef26aff6115ecf15c6b0451cc804a",   // khoá cũ — khi GitHub "xoay khoá" (Android 7–8 thấy khoá này)
    };

    /** true = chắc chắn app đã bị ký lại → Api.http từ chối mọi yêu cầu (lỗi APP_TAMPERED). */
    static volatile boolean bad = false;
    private static volatile boolean done = false;

    private Guard() { }

    /** Kiểm 1 lần mỗi lần mở app (gọi trong Api.init, sau khi biết bản web / CH Play). */
    static void check(Context c) {
        if (done) return;
        done = true;
        if (Api.PLAY) return;
        try {
            List<byte[]> now = signers(c);
            if (now.isEmpty()) return;
            for (byte[] cert : now) if (!official(cert)) { bad = true; return; }
        } catch (Throwable ignored) { }
    }

    @SuppressWarnings("deprecation")
    private static List<byte[]> signers(Context c) throws Exception {
        List<byte[]> out = new ArrayList<>();
        PackageManager pm = c.getPackageManager();
        String pkg = c.getPackageName();
        if (Build.VERSION.SDK_INT >= 28) {
            PackageInfo pi = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
            android.content.pm.SigningInfo si = pi.signingInfo;
            if (si == null) return out;
            if (si.hasMultipleSigners()) {
                Signature[] s = si.getApkContentsSigners();
                if (s != null) for (Signature x : s) out.add(x.toByteArray());
            } else {
                Signature[] h = si.getSigningCertificateHistory();          // [khoá cũ…, khoá ĐANG ký] → xét khoá đang ký (cuối)
                if (h != null && h.length > 0) out.add(h[h.length - 1].toByteArray());
            }
        } else {
            PackageInfo pi = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
            if (pi.signatures != null) for (Signature x : pi.signatures) out.add(x.toByteArray());
        }
        return out;
    }

    private static boolean official(byte[] cert) throws Exception {
        byte[] h = MessageDigest.getInstance("SHA-256").digest(cert);
        StringBuilder sb = new StringBuilder();
        for (byte b : h) sb.append(String.format("%02x", b & 0xff));
        String hex = sb.toString();
        for (String o : OFFICIAL) if (o.equals(hex)) return true;
        return false;
    }

    /** Màn vừa mở mà app bị sửa → hộp chặn KHÔNG tắt được: chỉ có Tải bản chính thức / Thoát. */
    static void gate(Activity a) {
        if (!bad) return;
        Api.ui(() -> {
            if (a.isFinishing() || a.isDestroyed()) return;
            LinearLayout c = Ui.col(a, 12);
            c.addView(Ui.text(a, Ui.L("App này KHÔNG phải bản chính thức của CloudBlue: nó đã bị sửa hoặc bị đóng gói lại. "
                            + "Để bảo vệ tài khoản và tiền của bạn, app đã ngừng kết nối máy chủ.",
                    "This is NOT the official CloudBlue app: it has been modified or repackaged. "
                            + "To protect your account and balance, it has stopped connecting to our servers."), 15, Ui.FG, false), Ui.fill());
            c.addView(Ui.text(a, Ui.L("Cách sửa: gỡ app này, rồi tải và cài bản chính thức tại " + Api.webHost() + ". Tài khoản, số dư và máy của bạn vẫn giữ nguyên.",
                    "Fix: uninstall this app, then install the official one from " + Api.webHost() + ". Your account, balance and phones are kept."), 14, Ui.MUTED, false), Ui.fill());
            Button dl = Ui.button(a, "⬇️ " + Ui.L("Tải bản chính thức", "Get the official app"), Ui.PRIMARY);
            dl.setOnClickListener(v -> {
                try { a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Api.WEB + "/download/blueroblox-cloud.apk"))); }
                catch (Exception ignored) { }
            });
            c.addView(dl, Ui.fill());
            Button out = Ui.button(a, Ui.L("Thoát", "Exit"), Ui.GHOST);
            out.setOnClickListener(v -> a.finishAffinity());
            c.addView(out, Ui.fill());
            Dialog d = Ui.sheet(a, "⛔ " + Ui.L("Bản app không chính thức", "Unofficial app"), c);
            d.setCancelable(false);
            d.setCanceledOnTouchOutside(false);
            d.show();
        });
    }
}
