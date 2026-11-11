package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.android.billingclient.api.AccountIdentifiers;
import com.android.billingclient.api.BillingClient;
import com.android.billingclient.api.BillingClientStateListener;
import com.android.billingclient.api.BillingFlowParams;
import com.android.billingclient.api.BillingResult;
import com.android.billingclient.api.ConsumeParams;
import com.android.billingclient.api.PendingPurchasesParams;
import com.android.billingclient.api.ProductDetails;
import com.android.billingclient.api.Purchase;
import com.android.billingclient.api.PurchasesUpdatedListener;
import com.android.billingclient.api.QueryProductDetailsParams;
import com.android.billingclient.api.QueryPurchasesParams;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** ▶️ NẠP TIỀN QUA GOOGLE PLAY — chỉ bản CH Play (src/play). Bản web dùng file cùng tên ở src/web (không làm gì).
 *  Khách chọn gói "50.000đ" → Google Play thu tiền (giá shop đặt trong Play Console) → app gửi mã giao dịch lên máy chủ
 *  (WEB/api/play-topup) → máy chủ HỎI GOOGLE xác nhận thật + đúng tài khoản rồi mới cộng số dư → app báo Google "đã giao" (consume).
 *  App KHÔNG tự cộng tiền. Mất mạng / tắt app giữa chừng → lần mở app sau tự gửi lại (Google giữ giao dịch chưa xong, máy chủ chỉ
 *  cộng 1 lần cho 1 giao dịch). Quá 3 ngày chưa xác nhận được → Google tự hoàn tiền cho khách — khách không bao giờ mất tiền oan.
 *  Thư viện: Google Play Billing 8.3.0 (build.gradle: playImplementation). */
final class PlayPay implements PurchasesUpdatedListener {
    static final boolean ON = true;
    /** Gói nạp app hỏi Google — gói nào chưa tạo / đang tắt trong Play Console thì tự ẩn. Mã gói: cb_nap_<số nghìn>k. */
    static final String[] IDS = {"cb_nap_20k", "cb_nap_50k", "cb_nap_100k", "cb_nap_200k", "cb_nap_500k", "cb_nap_1000k"};
    private static final Pattern PACK = Pattern.compile("^cb_nap_(\\d{1,4})k$");

    private static PlayPay me;
    private final Context app;
    private BillingClient bc;
    private boolean connecting = false;
    private long downAt = 0;                                   // lần cuối Google Play báo không dùng được (đỡ hỏi lại liên tục)
    private final List<Object[]> waiting = new ArrayList<>();  // {Runnable ok, Api.Err fail} chờ nối xong
    private final Set<String> busy = new HashSet<>();          // giao dịch đang gửi máy chủ
    private final Map<String, Long> later = new HashMap<>();   // giao dịch gửi lỗi → hẹn lúc gửi lại
    private Activity act;                                      // màn đang mở (hiện thông báo)
    private Runnable onCredit;                                 // cộng tiền xong → màn chính tải lại số dư
    private Dialog sheet;                                      // bảng chọn gói đang mở

    private PlayPay(Context c) { app = c.getApplicationContext(); }

    private static synchronized PlayPay get(Context c) { if (me == null) me = new PlayPay(c); return me; }

    /** Mã tài khoản gửi kèm giao dịch (Google không thấy mã thật). PHẢI giống acctHash() trong api/_play.js. */
    static String acct() {
        try {
            byte[] h = java.security.MessageDigest.getInstance("SHA-256").digest(("cb-play:" + Api.uid).getBytes(StandardCharsets.UTF_8));
            StringBuilder s = new StringBuilder();
            for (byte b : h) s.append(String.format("%02x", b & 0xff));
            return s.substring(0, 40);
        } catch (Exception e) { return ""; }
    }

    /** cb_nap_100k → 100.000 (đ). Mã lạ → 0. Giống packAmount() trên máy chủ. */
    static long amountOf(String id) {
        Matcher m = PACK.matcher(id == null ? "" : id);
        if (!m.matches()) return 0;
        long k = Long.parseLong(m.group(1));
        return k >= 10 && k <= 5000 ? k * 1000 : 0;
    }

    // ---------------- dùng từ MainActivity ----------------

    /** Mở bảng nạp tiền. balance = số dư hiện tại, need > 0 = số tiền còn thiếu cho đơn đang mua. */
    static void open(Activity a, double balance, double need, Runnable credited) {
        PlayPay p = get(a);
        p.act = a; p.onCredit = credited;
        p.showSheet(a, balance, need);
    }

    /** Mở app / quay lại app: giao dịch đã trả tiền mà chưa cộng (mất mạng, tắt app giữa chừng) → gửi lại máy chủ. */
    static void resume(Activity a, Runnable credited) {
        if (!Api.loggedIn()) return;
        PlayPay p = get(a);
        p.act = a; p.onCredit = credited;
        if (System.currentTimeMillis() - p.downAt < 10 * 60_000L) return;
        p.sync(false);
    }

    /** Màn rời đi (mở trang thanh toán của Google, ra ngoài…) → thôi giữ màn đó; quay lại thì resume() gắn lại. */
    static void pause(Activity a) { PlayPay p = me; if (p != null && p.act == a) { p.act = null; p.onCredit = null; } }

    // ---------------- nối Google Play ----------------

    private BillingClient client() {
        if (bc == null)
            bc = BillingClient.newBuilder(app).setListener(this)
                    .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
                    .enableAutoServiceReconnection()
                    .build();
        return bc;
    }

    /** Chạy ok khi đã nối được Google Play Billing (trên luồng giao diện); không nối được → fail(lời nhắn). */
    private void ready(Runnable ok, Api.Err fail) {
        BillingClient b = client();
        if (b.isReady()) { ok.run(); return; }
        waiting.add(new Object[]{ok, fail});
        if (connecting) return;
        connecting = true;
        b.startConnection(new BillingClientStateListener() {
            @Override public void onBillingSetupFinished(BillingResult r) {
                int code = r.getResponseCode();
                Api.ui(() -> {
                    // máy không có / không dùng được Google Play Billing → 10 phút sau mới tự hỏi lại (đỡ tốn pin)
                    if (code == BillingClient.BillingResponseCode.BILLING_UNAVAILABLE || code == BillingClient.BillingResponseCode.FEATURE_NOT_SUPPORTED)
                        downAt = System.currentTimeMillis();
                    else if (code == BillingClient.BillingResponseCode.OK) downAt = 0;
                    flush(code == BillingClient.BillingResponseCode.OK ? null : why(r));
                });
            }
            @Override public void onBillingServiceDisconnected() {     // thư viện tự nối lại (enableAutoServiceReconnection)
                Api.ui(() -> flush(Ui.L("Mất kết nối với Google Play — thử lại.", "Lost connection to Google Play — try again.")));
            }
        });
    }

    private void flush(String err) {
        connecting = false;
        List<Object[]> w = new ArrayList<>(waiting);
        waiting.clear();
        for (Object[] x : w) {
            if (err == null) ((Runnable) x[0]).run();
            else if (x[1] != null) ((Api.Err) x[1]).fail(err);
        }
    }

    /** Lời nhắn dễ hiểu cho mã lỗi của Google Play. */
    private static String why(BillingResult r) {
        switch (r.getResponseCode()) {
            case BillingClient.BillingResponseCode.USER_CANCELED: return Ui.L("Đã huỷ thanh toán.", "Payment cancelled.");
            case BillingClient.BillingResponseCode.BILLING_UNAVAILABLE:
                return Ui.L("Google Play trên máy này chưa thanh toán được — đăng nhập tài khoản Google trong CH Play, cập nhật CH Play rồi thử lại.",
                        "Google Play billing isn't available on this device — sign in to the Play Store, update it and try again.");
            case BillingClient.BillingResponseCode.SERVICE_UNAVAILABLE:
            case BillingClient.BillingResponseCode.SERVICE_DISCONNECTED:
            case BillingClient.BillingResponseCode.NETWORK_ERROR:
                return Ui.L("Không kết nối được Google Play — kiểm tra mạng rồi thử lại.", "Can't reach Google Play — check your connection and try again.");
            case BillingClient.BillingResponseCode.FEATURE_NOT_SUPPORTED:
                return Ui.L("CH Play trên máy đã cũ — cập nhật CH Play rồi thử lại.", "Your Play Store is outdated — update it and try again.");
            case BillingClient.BillingResponseCode.ITEM_UNAVAILABLE: return Ui.L("Gói này đang tạm ngưng — chọn gói khác.", "This pack isn't available — pick another.");
            case BillingClient.BillingResponseCode.DEVELOPER_ERROR: return Ui.L("Gói nạp đang được shop cài đặt — thử lại sau.", "This pack is being set up — try again later.");
            default: return Ui.L("Google Play báo lỗi (mã " + r.getResponseCode() + ") — thử lại sau.", "Google Play error (" + r.getResponseCode() + ") — try again later.");
        }
    }

    // ---------------- bảng chọn gói ----------------

    private void showSheet(Activity a, double balance, double need) {
        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, Ui.L("Số dư hiện tại: ", "Balance: ") + Ui.vnd(balance) + (need > 0 ? Ui.L("  ·  Cần thêm ", "  ·  Need ") + Ui.vnd(need) : "")));
        LinearLayout list = Ui.col(a, 10);
        c.addView(list, Ui.fill());
        TextView st = Ui.muted(a, Ui.L("Đang tải các gói nạp từ Google Play…", "Loading top-up packs from Google Play…"));
        list.addView(st, Ui.fill());
        c.addView(Ui.muted(a, Ui.L("▶️ Thanh toán qua Google Play (thẻ, ví điện tử, số dư Google Play…). Tiền vào số dư ngay khi Google xác nhận, thường chỉ vài giây.",
                "▶️ Paid through Google Play (card, e-wallet, Play balance…). Your balance is credited as soon as Google confirms — usually seconds.")), Ui.fill());
        TextView fix = Ui.text(a, Ui.L("Đã trả tiền mà chưa thấy cộng? Bấm để kiểm tra lại", "Paid but not credited? Tap to check again"), 13.5f, Ui.SKY, true);
        fix.setPadding(0, Ui.dp(4), 0, Ui.dp(4));
        fix.setOnClickListener(v -> { Ui.toast(a, Ui.L("Đang kiểm tra giao dịch với Google…", "Checking with Google…")); sync(true); });
        c.addView(fix, Ui.fill());
        Button close = Ui.button(a, Ui.L("Đóng", "Close"), Ui.GHOST);
        c.addView(close, Ui.fill());
        Dialog d = Ui.sheet(a, "💳 " + Ui.L("Nạp tiền", "Top up"), c);
        close.setOnClickListener(v -> d.dismiss());
        d.setOnDismissListener(z -> { if (sheet == d) sheet = null; });
        sheet = d;
        d.show();
        Runnable[] load = new Runnable[1];
        Api.Err fail = m -> {
            if (!d.isShowing()) return;
            list.removeAllViews();
            TextView e = Ui.text(a, m, 14, Ui.BAD, false);
            list.addView(e, Ui.fill());
            Button again = Ui.button(a, Ui.L("Thử lại", "Try again"), Ui.GHOST);
            again.setOnClickListener(v -> load[0].run());
            list.addView(again, Ui.fill());
        };
        load[0] = () -> {
            list.removeAllViews();
            list.addView(st, Ui.fill());
            ready(() -> query(ps -> { if (d.isShowing()) fill(a, d, list, ps, need); }, fail), fail);
        };
        load[0].run();
    }

    private void query(Api.Cb<List<ProductDetails>> ok, Api.Err fail) {
        List<QueryProductDetailsParams.Product> ps = new ArrayList<>();
        for (String id : IDS)
            ps.add(QueryProductDetailsParams.Product.newBuilder().setProductId(id).setProductType(BillingClient.ProductType.INAPP).build());
        client().queryProductDetailsAsync(QueryProductDetailsParams.newBuilder().setProductList(ps).build(), (r, res) -> Api.ui(() -> {
            if (r.getResponseCode() != BillingClient.BillingResponseCode.OK) { fail.fail(why(r)); return; }
            List<ProductDetails> l = new ArrayList<>();
            List<ProductDetails> got = res == null ? null : res.getProductDetailsList();
            if (got != null) for (ProductDetails x : got) if (x != null && amountOf(x.getProductId()) > 0 && offer(x) != null) l.add(x);
            Collections.sort(l, (x, y) -> Long.compare(amountOf(x.getProductId()), amountOf(y.getProductId())));
            ok.ok(l);
        }));
    }

    /** Giá để mua: gói có nhiều ưu đãi → ưu đãi đầu tiên Google trả (đúng người dùng được hưởng), không thì giá thường. */
    private static ProductDetails.OneTimePurchaseOfferDetails offer(ProductDetails p) {
        List<ProductDetails.OneTimePurchaseOfferDetails> l = p.getOneTimePurchaseOfferDetailsList();
        if (l != null && !l.isEmpty() && l.get(0) != null) return l.get(0);
        return p.getOneTimePurchaseOfferDetails();
    }

    private void fill(Activity a, Dialog d, LinearLayout list, List<ProductDetails> ps, double need) {
        list.removeAllViews();
        if (ps.isEmpty()) {
            list.addView(Ui.text(a, Ui.L("Chưa có gói nạp nào trên Google Play — shop đang cài đặt, quay lại sau nhé.",
                    "No top-up packs on Google Play yet — check back soon."), 14, Ui.WAIT, false), Ui.fill());
            return;
        }
        ProductDetails pick = null;                              // gói nhỏ nhất đủ cho đơn đang mua
        if (need > 0) for (ProductDetails p : ps) if (amountOf(p.getProductId()) >= need) { pick = p; break; }
        for (ProductDetails p : ps) {
            final ProductDetails pd = p;
            long amt = amountOf(p.getProductId());
            ProductDetails.OneTimePurchaseOfferDetails o = offer(p);
            boolean best = p == pick;
            LinearLayout row = Ui.row(a, 12);
            row.setPadding(Ui.dp(16), Ui.dp(12), Ui.dp(12), Ui.dp(12));
            row.setBackground(Ui.round(best ? (Ui.LIGHT ? Color.argb(20, 43, 110, 240) : Color.argb(34, 90, 175, 255)) : Ui.PANEL2, 16,
                    best ? Ui.SKY : Ui.LINE));
            LinearLayout col = Ui.col(a, 2);
            col.addView(Ui.text(a, Ui.vnd(amt), 20, Ui.FG, true));
            col.addView(Ui.text(a, best ? Ui.L("✓ Đủ cho đơn này", "✓ Covers this order") : Ui.L("cộng vào số dư", "added to balance"),
                    12.5f, best ? Ui.OK : Ui.MUTED, best));
            row.addView(col, Ui.weight(1));
            Button b = Ui.button(a, o.getFormattedPrice(), best ? Ui.PRIMARY : Ui.GHOST);
            b.setMinWidth(Ui.dp(116));
            b.setOnClickListener(v -> buy(a, pd));
            row.setOnClickListener(v -> buy(a, pd));
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.addView(b, Ui.wrap());
            list.addView(row, Ui.fill());
        }
    }

    private void buy(Activity a, ProductDetails pd) {
        if (Api.uid == null || Api.uid.isEmpty()) { Ui.toast(a, Ui.L("Hãy đăng nhập lại.", "Please log in again.")); return; }
        ready(() -> {
            BillingFlowParams.ProductDetailsParams.Builder pb = BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(pd);
            List<ProductDetails.OneTimePurchaseOfferDetails> l = pd.getOneTimePurchaseOfferDetailsList();
            if (l != null && !l.isEmpty() && l.get(0) != null && l.get(0).getOfferToken() != null && !l.get(0).getOfferToken().isEmpty())
                pb.setOfferToken(l.get(0).getOfferToken());
            BillingFlowParams fp = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(Collections.singletonList(pb.build()))
                    .setObfuscatedAccountId(acct())                 // giao dịch gắn với tài khoản CloudBlue đang đăng nhập
                    .build();
            BillingResult r = client().launchBillingFlow(a, fp);
            int code = r.getResponseCode();
            if (code == BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED) sync(true);       // còn giao dịch gói này chưa cộng → xử lý trước
            else if (code != BillingClient.BillingResponseCode.OK && code != BillingClient.BillingResponseCode.USER_CANCELED) Ui.toast(a, why(r));
        }, m -> Ui.toast(a, m));
    }

    // ---------------- kết quả thanh toán ----------------

    @Override public void onPurchasesUpdated(BillingResult r, List<Purchase> list) {
        final List<Purchase> ps = list == null ? new ArrayList<>() : new ArrayList<>(list);
        Api.ui(() -> {
            int code = r.getResponseCode();
            if (code == BillingClient.BillingResponseCode.OK) { for (Purchase p : ps) handle(p, true); return; }
            if (code == BillingClient.BillingResponseCode.USER_CANCELED) return;
            if (code == BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED) { sync(true); return; }
            note(why(r));
        });
    }

    /** Giao dịch còn đó (chưa consume) → gửi máy chủ. loud = khách đang chờ (hiện thông báo), không thì lặng lẽ. */
    private void sync(boolean loud) {
        ready(() -> client().queryPurchasesAsync(
                QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.INAPP).build(),
                (r, list) -> {
                    final List<Purchase> ps = list == null ? new ArrayList<>() : new ArrayList<>(list);
                    Api.ui(() -> {
                        if (r.getResponseCode() != BillingClient.BillingResponseCode.OK) { if (loud) note(why(r)); return; }
                        int n = 0;
                        for (Purchase p : ps) if (amountOf(first(p)) > 0) { n++; handle(p, loud); }
                        if (loud && n == 0) note(Ui.L("Không có giao dịch nào đang chờ — mọi lần nạp đã được cộng.", "Nothing pending — all top-ups are credited."));
                    });
                }), m -> { if (loud) note(m); });
    }

    private static String first(Purchase p) {
        List<String> l = p.getProducts();
        return l == null || l.isEmpty() ? "" : l.get(0);
    }

    private void handle(Purchase p, boolean loud) {
        final String tok = p.getPurchaseToken(), prod = first(p);
        if (tok == null || tok.isEmpty() || amountOf(prod) <= 0) return;      // không phải gói nạp của app
        if (p.getPurchaseState() == Purchase.PurchaseState.PENDING) {
            if (loud) note(Ui.L("⏳ Giao dịch đang chờ thanh toán — khi Google xác nhận, app tự cộng tiền (không cần mua lại).",
                    "⏳ Payment pending — once Google confirms, the app credits you automatically (don't buy again)."));
            return;
        }
        if (p.getPurchaseState() != Purchase.PurchaseState.PURCHASED) return;
        AccountIdentifiers ai = p.getAccountIdentifiers();
        String oa = ai == null ? null : ai.getObfuscatedAccountId();
        if (oa != null && !oa.isEmpty() && !oa.equals(acct())) {              // mua lúc đăng nhập tài khoản CloudBlue khác
            if (loud) note(Api.friendly(new Api.ApiError(403, "PLAY_OTHER_ACCOUNT")));
            return;
        }
        if (busy.contains(tok)) return;
        Long at = later.get(tok);
        if (!loud && at != null && System.currentTimeMillis() < at) return;
        busy.add(tok);
        if (loud) note(Ui.L("⏳ Đang xác nhận thanh toán với Google…", "⏳ Confirming your payment with Google…"));
        Api.<JSONObject>bg(() -> Api.webPost("/api/play-topup", new JSONObject().put("token", tok).put("product", prod)), j -> {
            busy.remove(tok);
            String s = j.optString("status");
            if (!j.optBoolean("ok")) {
                later.put(tok, System.currentTimeMillis() + 60_000L);
                if (loud) note("cancelled".equals(s) ? Ui.L("Giao dịch đã bị huỷ — bạn không bị trừ tiền.", "The payment was cancelled — you weren't charged.")
                        : Ui.L("⏳ Google chưa xác nhận thanh toán — app sẽ tự kiểm tra lại.", "⏳ Google hasn't confirmed the payment yet — the app will check again."));
                return;
            }
            later.remove(tok);
            if (!j.optBoolean("consumed")) consume(tok);                     // máy chủ đã cộng nhưng chưa báo Google được → app báo
            long got = j.optLong("credited", 0);
            if ("credited".equals(s) && got > 0) done(Ui.L("✅ Đã nạp +", "✅ Topped up +") + Ui.vnd(got) + Ui.L(" vào số dư", " to your balance"));
            else if ("test".equals(s)) done(Ui.L("🧪 Giao dịch THỬ thành công — tài khoản thường không được cộng tiền khi mua thử.",
                    "🧪 Test purchase OK — regular accounts aren't credited for test purchases."));
            else done(loud ? Ui.L("✓ Giao dịch này đã được cộng vào số dư trước đó.", "✓ This payment was already credited.") : null);
        }, m -> {
            busy.remove(tok);
            boolean fin = m.equals(Api.friendly(new Api.ApiError(403, "PLAY_OTHER_ACCOUNT"))) || m.equals(Api.friendly(new Api.ApiError(400, "PLAY_TOKEN_INVALID")))
                    || m.equals(Api.friendly(new Api.ApiError(403, "LOCKED")));
            later.put(tok, System.currentTimeMillis() + (fin ? 30 * 60_000L : 60_000L));   // lỗi hẳn → lâu lâu mới thử lại
            if (loud) note(fin || m.contains(Ui.L("KHÔNG cần mua lại", "don't buy again")) ? m
                    : m + Ui.L(" — Bạn đã trả tiền thì app sẽ tự gửi lại, KHÔNG cần mua lại.", " — If you paid, the app retries automatically; don't buy again."));
        });
    }

    private void consume(String tok) {
        ready(() -> client().consumeAsync(ConsumeParams.newBuilder().setPurchaseToken(tok).build(), (r, t) -> { }), null);
    }

    /** Cộng xong: đóng bảng chọn gói, báo khách, màn chính tải lại số dư + lịch sử nạp. */
    private void done(String msg) {
        Dialog d = sheet;
        if (d != null && msg != null) { try { d.dismiss(); } catch (Exception ignored) { } }
        if (msg != null) note(msg);
        Runnable r = onCredit;
        if (r != null) r.run();
    }

    private void note(String m) {
        if (m == null || m.isEmpty()) return;
        Activity a = act;
        Ui.toast(a != null && !a.isFinishing() ? a : app, m);
    }
}
