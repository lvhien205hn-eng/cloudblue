package shop.blueroblox.app;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/** 🏷️ Ô MÃ GIẢM GIÁ dùng chung cho thuê / gia hạn / nâng cấp máy — giống web (SQL v23 promo_check, gửi kèm p_promo):
 *  bấm Áp dụng → kiểm mã cho ĐÚNG đơn đang chọn · đổi đơn (ngày, RAM…) → tự kiểm lại sau 0,6 giây
 *  · ô có chữ mà mã sai → không cho thanh toán (xoá mã để thanh toán bình thường). Mã sai không kiểm lại khi đổi đơn (khỏi bị tính nhập sai). */
final class Promo {
    interface Ctx { JSONObject get() throws Exception; }        // tham số promo_check của đơn đang chọn (null = chưa đủ thông tin)
    private static final List<String> RECHECK = Arrays.asList("PROMO_MIN_ORDER", "PROMO_CTX", "BAD_PLAN", "NO_PHONE", "NO_MACHINE", "NO_PRODUCT");

    final Activity a; final String scope; final Ctx ctx; final Runnable changed;
    final LinearLayout view; final EditText in; final TextView res; final Button ap;
    private final Handler h = new Handler(Looper.getMainLooper());
    String code = "", key = "";
    JSONObject r = null;
    boolean busy = false;
    int seq = 0;

    Promo(Activity a, String scope, Ctx ctx, Runnable changed) {
        this.a = a; this.scope = scope; this.ctx = ctx; this.changed = changed;
        view = Ui.col(a, 6);
        LinearLayout row = Ui.row(a, 8);
        in = Ui.input(a, Ui.L("🏷️ Mã giảm giá (nếu có)", "🏷️ Discount code (optional)"),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        ap = Ui.button(a, Ui.L("Áp dụng", "Apply"), Ui.GHOST);
        row.addView(in, Ui.weight(1));
        row.addView(ap, Ui.wrap());
        res = Ui.text(a, "", 12.5f, Ui.MUTED, false);
        res.setVisibility(View.GONE);
        view.addView(row, Ui.fill());
        view.addView(res, Ui.fill());
        ap.setOnClickListener(v -> check(null));
        in.addTextChangedListener(new MainActivity.Simple(() -> {
            String c = norm(in.getText().toString());
            if (c.equals(code)) return;
            code = c; r = null; key = ""; seq++; busy = false;   // sửa / xoá mã → bỏ kết quả cũ, tổng tiền về giá thường
            paint(); changed.run();
        }));
    }

    static String norm(String s) { return s == null ? "" : s.toUpperCase(Locale.ROOT).replaceAll("[^A-Z0-9]", ""); }

    private String keyNow() {
        try { JSONObject c = ctx.get(); return c == null ? "" : code + "|" + scope + "|" + c; } catch (Exception e) { return ""; }
    }
    /** Kết quả kiểm mã còn đúng cho đơn đang chọn (không đang kiểm, đơn không đổi) · không thì null. */
    JSONObject live() { return r != null && !busy && !key.isEmpty() && key.equals(keyNow()) ? r : null; }
    static boolean use(JSONObject x) { return x != null && x.optBoolean("ok") && "discount".equals(x.optString("kind")) && x.optBoolean("use_promo"); }
    /** Giá sau mã (chỉ khi mã đã kiểm đúng cho chính đơn này), không thì giá thường. */
    double price(double normal) { JSONObject x = live(); return use(x) ? Math.max(0, x.optDouble("price", normal)) : normal; }
    /** Mã gửi kèm p_promo (null = không gửi). */
    String send() { return use(live()) ? code : null; }

    /** Đơn vừa đổi → mã đã áp dụng (dùng được / thiếu điều kiện đơn) tự kiểm lại. Mã sai hẳn thì thôi. */
    void onOrderChanged() {
        if (code.isEmpty() || r == null || busy) return;
        String err = r.optString("err", "");
        if (!(r.optBoolean("ok") && "discount".equals(r.optString("kind"))) && !r.optBoolean("net") && !RECHECK.contains(err)) return;
        if (keyNow().equals(key)) return;
        final int s = ++seq;
        busy = true; paint();
        h.postDelayed(() -> { if (s == seq) { busy = false; check(null); } }, 600);
    }

    void check(Runnable then) {
        final String c = norm(in.getText().toString());
        code = c;
        if (c.isEmpty()) { r = null; key = ""; busy = false; paint(); changed.run(); if (then != null) then.run(); return; }
        final JSONObject cx;
        try { cx = ctx.get(); } catch (Exception e) { return; }
        if (cx == null) {
            try { r = new JSONObject().put("ok", false).put("err", "PROMO_CTX"); } catch (Exception ignored) { }
            key = ""; busy = false; paint(); changed.run(); if (then != null) then.run(); return;
        }
        final String k = c + "|" + scope + "|" + cx;
        final int s = ++seq;
        busy = true; paint();
        Api.bg(() -> {
            JSONObject args = new JSONObject(cx.toString()).put("p_code", c).put("p_scope", scope);
            try {
                Object o = Api.rpc("promo_check", args);
                return o instanceof JSONObject ? (JSONObject) o : new JSONObject().put("ok", false).put("err", "PROMO_INVALID");
            } catch (Exception e) {
                String m = String.valueOf(e.getMessage());
                boolean off = m.contains("promo_check") || m.contains("schema cache") || m.contains("Could not find");
                return new JSONObject().put("ok", false).put("err", off ? "PROMO_OFF" : m).put("net", !off);
            }
        }, o -> {
            if (s != seq) return;
            busy = false; r = o; key = k;
            paint(); changed.run();
            if (then != null) then.run();
        }, m -> { if (s == seq) { busy = false; r = null; key = ""; show("⚠ " + m, Ui.BAD); } });
    }

    String errText(JSONObject x) {
        String e = x.optString("err", "");
        if (x.optBoolean("ok") && "gift".equals(x.optString("kind")))
            return Ui.L("Đây là mã TẶNG MÁY — nhập ở nút \"🎟 Nhập mã\" trong Máy của tôi (không dùng khi thanh toán).", "This is a gift-phone code — enter it with \"🎟 Enter code\" in My phones.");
        if ("PROMO_OFF".equals(e)) return Ui.L("Tính năng mã giảm giá chưa bật.", "Discount codes aren't available yet.");
        if ("PROMO_MIN_ORDER".equals(e) && x.has("min_order"))
            return Ui.L("Mã chỉ dùng cho đơn từ " + Ui.vnd(x.optDouble("min_order")) + " (đơn này " + Ui.vnd(x.optDouble("base")) + ").",
                    "This code needs an order of at least " + Ui.vnd(x.optDouble("min_order")) + " (this one is " + Ui.vnd(x.optDouble("base")) + ").");
        if ("PROMO_NOT_STARTED".equals(e) && x.has("starts_at"))
            return Ui.L("Mã chưa đến ngày dùng — dùng được từ ", "This code starts on ") + MainActivity.fdate(MainActivity.parseTime(x.optString("starts_at"))) + ".";
        return Api.friendly(new Exception(e.isEmpty() ? "PROMO_INVALID" : e));
    }

    private void show(String t, int color) { res.setText(t); res.setTextColor(color); res.setVisibility(View.VISIBLE); }

    void paint() {
        if (busy) { show("⏳ " + Ui.L("Đang kiểm tra mã…", "Checking the code…"), Ui.MUTED); return; }
        if (code.isEmpty() || r == null) { res.setVisibility(View.GONE); return; }
        if (use(r)) show("✓ " + Ui.L("Giảm ", "You save ") + Ui.vnd(r.optDouble("discount")) + " → " + Ui.L("còn ", "you pay ") + Ui.vnd(r.optDouble("price")), Ui.OK);
        else if (r.optBoolean("ok") && "discount".equals(r.optString("kind")))
            show("ℹ " + Ui.L("Giá CTV của bạn đã rẻ hơn — mã sẽ không được dùng (không mất lượt).", "Your reseller price is already lower — the code won't be used."), Ui.MUTED);
        else show("⚠ " + errText(r), Ui.BAD);
    }

    /** Trước khi trả tiền: ô trống → mua bình thường; có chữ → phải là mã dùng được cho chính đơn này (kiểm lại nếu cần). */
    void ensure(Runnable ok) {
        if (norm(in.getText().toString()).isEmpty()) { code = ""; ok.run(); return; }
        Runnable decide = () -> {
            JSONObject y = live();
            if (y != null && y.optBoolean("ok") && "discount".equals(y.optString("kind"))) ok.run();
            else Ui.toast(a, (y != null ? errText(y) : Ui.L("Chưa kiểm tra được mã, thử lại.", "Couldn't check the code, try again."))
                    + " " + Ui.L("Sửa hoặc xoá mã giảm giá để thanh toán.", "Fix or clear the discount code to pay."));
        };
        if (live() != null) decide.run(); else check(decide);
    }

    /** Đơn bị từ chối vì mã (PROMO_…) → hiện lỗi dưới ô mã. */
    boolean fail(String msg) {
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("PROMO_[A-Z_]+").matcher(msg == null ? "" : msg);
        if (!m.find()) return false;
        try { r = new JSONObject().put("ok", false).put("err", m.group()); } catch (Exception ignored) { }
        key = keyNow(); busy = false; paint(); changed.run();
        return true;
    }
}
