package shop.blueroblox.app;

import android.app.Activity;

/** Bản web (shop.blueroblox.app): KHÔNG dùng Google Play Billing — nạp tiền bằng chuyển khoản / crypto như cũ.
 *  File thật (nạp qua Google Play) ở src/play/java/…/PlayPay.java, chỉ có trong bản CH Play. */
final class PlayPay {
    static final boolean ON = false;
    private PlayPay() { }
    static void open(Activity a, double balance, double need, Runnable credited) { }
    static void resume(Activity a, Runnable credited) { }
    static void pause(Activity a) { }
}
