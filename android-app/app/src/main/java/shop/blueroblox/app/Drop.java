package shop.blueroblox.app;

import android.app.Dialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** ⚡ PHÁT MÃ NHANH TAY (SQL v38) — ô thông báo ngay dưới dải chữ chạy, hiện ở mọi trang:
 *    "−30% · Mã giảm 30% cloud phone · còn 18/50 mã" + nút Nhận mã (ai nhanh thì có, mỗi tài khoản 1 mã / đợt).
 *    promo_drop_now()      → {now, login, drops[{id, state (on·soon·out·ended), pct, max, total, left, days, starts_at, ends_at,
 *                                                 need, old_only, one_dev, why (null·need_dep·new_account·locked), mine{code, expires_at, used, usable}}]}
 *    promo_drop_claim(p_id) → {ok, again, code, pct, max, expires_at, left, total}
 *  Mã là mã RIÊNG của người nhận, chỉ người nhận thấy. Máy chủ chưa chạy SQL v38 → lỗi → ô ẩn, app chạy như cũ.
 *  Bản CH Play: hiện khi app có mua bán (Api.SHOP) — giảm giá cho lần thuê / gia hạn trả bằng số dư trong app. */
final class Drop {
    static volatile JSONObject data = null;
    static volatile long at = 0, skew = 0;
    private static final int AMBER = Color.rgb(245, 165, 36), AMBER_HI = Color.rgb(255, 215, 122), INK = Color.rgb(42, 23, 0);
    private static Runnable ticker = null;

    static boolean on() { return Api.SHOP; }
    static long now() { return System.currentTimeMillis() + skew; }

    /** Đợt hiện ở ô: đang phát > sắp phát > vừa hết. */
    static JSONObject main() {
        JSONObject d = data; JSONArray ds = d == null ? null : d.optJSONArray("drops");
        if (ds == null || ds.length() == 0) return null;
        JSONObject soon = null;
        for (int i = 0; i < ds.length(); i++) {
            JSONObject x = ds.optJSONObject(i); if (x == null) continue;
            if ("on".equals(x.optString("state"))) return x;
            if (soon == null && "soon".equals(x.optString("state"))) soon = x;
        }
        return soon != null ? soon : ds.optJSONObject(0);
    }
    static boolean live() { JSONObject m = main(); return m != null && ("on".equals(m.optString("state")) || "soon".equals(m.optString("state"))); }

    /** Tải lại ở nền → done() trên luồng giao diện. Lỗi mạng: giữ dữ liệu cũ · máy chủ chưa có hàm: ẩn. */
    static void load(Runnable done) {
        if (!on()) { data = null; if (done != null) done.run(); return; }
        Api.bg(() -> { Object r = Api.rpc("promo_drop_now", new JSONObject()); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); }, r -> {
            data = r.has("drops") ? r : null; at = System.currentTimeMillis();
            long n = MainActivity.parseTime(r.optString("now")); if (n > 0) skew = n - System.currentTimeMillis();
            if (done != null) done.run();
        }, m -> {
            at = System.currentTimeMillis();
            if (m != null && (m.contains("promo_drop_now") || m.contains("schema cache") || m.contains("Could not find"))) data = null;
            if (done != null) done.run();
        });
    }

    private static String key(JSONObject d) { return "min_" + d.optLong("id") + ("soon".equals(d.optString("state")) ? "_soon" : ""); }
    private static boolean isMin(Context c, JSONObject d) { return c.getSharedPreferences("drop", Context.MODE_PRIVATE).getBoolean(key(d), false); }
    private static void setMin(Context c, JSONObject d, boolean v) { c.getSharedPreferences("drop", Context.MODE_PRIVATE).edit().putBoolean(key(d), v).apply(); }
    private static JSONObject mine(JSONObject d) { return d == null || d.isNull("mine") ? null : d.optJSONObject("mine"); }
    private static String dur(long ms) {
        long s = Math.max(0, ms / 1000), h = s / 3600, m = s % 3600 / 60, x = s % 60;
        return h > 0 ? String.format(java.util.Locale.US, "%d:%02d:%02d", h, m, x) : String.format(java.util.Locale.US, "%02d:%02d", m, x);
    }
    private static String when(String iso) {
        long t = MainActivity.parseTime(iso);
        return t <= 0 ? "" : new java.text.SimpleDateFormat("HH:mm dd/MM", java.util.Locale.getDefault()).format(new java.util.Date(t));
    }
    private static GradientDrawable amber(int radius) {
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{AMBER_HI, AMBER});
        g.setCornerRadius(Ui.dp(Ui.rad(radius)));
        return g;
    }
    static String terms(JSONObject d) {
        long mx = d.optLong("max", 0);
        return (mx > 0 ? Ui.L("Giảm tối đa " + Ui.vnd(mx) + " · ", "Up to " + Ui.vnd(mx) + " off · ") : "")
                + Ui.L("dùng trong " + d.optInt("days", 3) + " ngày · 1 mã / tài khoản · chỉ cloud phone.", "valid " + d.optInt("days", 3) + " days · 1 per account · cloud phones only.");
    }
    private static String sub(JSONObject d) {
        String st = d.optString("state"), why = d.isNull("why") ? "" : d.optString("why");
        JSONObject mi = mine(d);
        if (mi != null) return mi.optBoolean("used") ? Ui.L("Bạn đã dùng mã này rồi.", "You've already used this code.")
                : Ui.L("Mã riêng của bạn · hạn đến ", "Your own code · valid until ") + when(mi.optString("expires_at"));
        if ("soon".equals(st)) return Ui.L("Mở nhận lúc " + when(d.optString("starts_at")) + " · còn ", "Opens at " + when(d.optString("starts_at")) + " · in ")
                + dur(MainActivity.parseTime(d.optString("starts_at")) - now());
        if ("out".equals(st)) return Ui.L("Đã phát hết " + d.optInt("total") + " mã — chờ đợt sau nhé!", "All " + d.optInt("total") + " codes are gone — catch the next drop!");
        if (!"on".equals(st)) return Ui.L("Đợt phát mã đã kết thúc.", "This drop has ended.");
        if ("need_dep".equals(why)) return Ui.L("Dành cho tài khoản đã nạp từ " + Ui.vnd(d.optLong("need")) + ".", "For accounts that topped up " + Ui.vnd(d.optLong("need")) + "+.");
        if ("new_account".equals(why)) return Ui.L("Dành cho tài khoản tạo trước lúc phát mã — đợt sau nhé!", "For accounts created before the drop — next time!");
        String left = Ui.L("Còn " + d.optInt("left") + "/" + d.optInt("total") + " mã · ai nhanh tay thì có", d.optInt("left") + "/" + d.optInt("total") + " left · first come, first served");
        long end = MainActivity.parseTime(d.optString("ends_at"));
        return end > 0 ? left + Ui.L(" · hết giờ sau ", " · ends in ") + dur(end - now()) : left;
    }

    /** Ô trống (ẩn) để gắn vào màn chính; fill() vẽ nội dung. */
    static LinearLayout bar(MainActivity a) {
        LinearLayout box = Ui.col(a, 0);
        box.setVisibility(View.GONE);
        return box;
    }

    static void fill(MainActivity a, LinearLayout box) {
        if (box == null) return;
        JSONObject d = on() ? main() : null;
        String why = d == null || d.isNull("why") ? "" : d.optString("why");
        if (d == null || "locked".equals(why) || !d.has("pct")) { stopTick(box); box.removeAllViews(); box.setVisibility(View.GONE); box.setTag(null); return; }
        boolean min = isMin(a, d);
        JSONObject mi = mine(d);
        String sig = d.optLong("id") + "|" + d.optString("state") + "|" + why + "|" + (mi == null ? "" : mi.optString("code") + mi.optBoolean("used")) + "|" + min
                + "|" + d.optString("starts_at") + "|" + d.optString("ends_at");
        if (sig.equals(box.getTag())) { refresh(box, d); return; }
        stopTick(box);
        box.setTag(sig);
        box.removeAllViews();
        box.addView(min ? pill(a, box, d) : card(a, box, d), Ui.fill());
        box.setVisibility(View.VISIBLE);
        startTick(a, box);
    }

    /** Chỉ đổi số mã còn lại / đồng hồ → sửa tại chỗ (không vẽ lại, không nháy). */
    private static void refresh(LinearLayout box, JSONObject d) {
        TextView s = box.findViewWithTag("sub"); if (s != null) s.setText(sub(d));
        TextView p = box.findViewWithTag("pill"); if (p != null) p.setText(pillText(d));
        View f = box.findViewWithTag("fill"), r = box.findViewWithTag("rest");
        if (f != null && r != null) {
            int left = Math.max(0, d.optInt("left")), total = Math.max(left, d.optInt("total"));
            ((LinearLayout.LayoutParams) f.getLayoutParams()).weight = left;
            ((LinearLayout.LayoutParams) r.getLayoutParams()).weight = Math.max(0, total - left);
            f.requestLayout();
        }
    }
    private static void stopTick(View box) { if (ticker != null) { box.removeCallbacks(ticker); ticker = null; } }
    private static void startTick(MainActivity a, LinearLayout box) {
        JSONObject d = main(); if (d == null) return;
        boolean soon = "soon".equals(d.optString("state")), timed = "on".equals(d.optString("state")) && !d.isNull("ends_at") && mine(d) == null;
        if (!soon && !timed) return;
        final Runnable[] r = new Runnable[1];
        r[0] = () -> {
            if (!box.isAttachedToWindow() || a.isFinishing()) return;
            JSONObject x = main(); if (x == null) return;
            long due = MainActivity.parseTime(x.optString("soon".equals(x.optString("state")) ? "starts_at" : "ends_at"));
            refresh(box, x);
            if (due > 0 && due - now() <= 0 && System.currentTimeMillis() - at > 3000) { load(() -> { if (!a.isFinishing()) fill(a, box); }); return; }
            box.postDelayed(r[0], 1000);
        };
        ticker = r[0];
        box.postDelayed(r[0], 1000);
    }

    private static String pillText(JSONObject d) {
        String st = d.optString("state");
        return "⚡ −" + d.optInt("pct") + "% · " + (mine(d) != null ? Ui.L("mã của bạn", "your code") : "soon".equals(st) ? Ui.L("sắp phát", "soon")
                : "on".equals(st) ? Ui.L("còn " + d.optInt("left"), d.optInt("left") + " left") : Ui.L("hết mã", "gone")) + "  ›";
    }
    private static View pill(MainActivity a, LinearLayout box, JSONObject d) {
        LinearLayout row = Ui.row(a, 0);
        row.setGravity(Gravity.END);
        TextView p = Ui.text(a, pillText(d), 13, Ui.FG, true);
        p.setTag("pill");
        p.setPadding(Ui.dp(14), Ui.dp(6), Ui.dp(14), Ui.dp(7));
        p.setBackground(Ui.round(Ui.PANEL, 99, Color.argb(170, 245, 165, 36)));
        p.setContentDescription(Ui.L("Mở ô phát mã giảm giá", "Open the code drop"));
        p.setOnClickListener(v -> { setMin(a, d, false); fill(a, box); });
        row.addView(p, Ui.wrap());
        return row;
    }
    private static View card(MainActivity a, LinearLayout box, JSONObject d) {
        LinearLayout c = Ui.row(a, 10);
        c.setGravity(Gravity.CENTER_VERTICAL);
        c.setPadding(Ui.dp(9), Ui.dp(8), Ui.dp(4), Ui.dp(8));
        c.setBackground(Ui.round(Ui.PANEL, 16, Color.argb(170, 245, 165, 36)));
        TextView badge = Ui.text(a, "−" + d.optInt("pct") + "%", 17, INK, true);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(amber(12));
        c.addView(badge, new LinearLayout.LayoutParams(Ui.dp(58), Ui.dp(48)));
        JSONObject mi = mine(d);
        LinearLayout mid = Ui.col(a, 2);
        TextView t1 = Ui.text(a, mi != null ? "🎫 " + mi.optString("code") : Ui.L("Mã giảm " + d.optInt("pct") + "% cloud phone", d.optInt("pct") + "% off cloud phones"), 14, Ui.FG, true);
        t1.setMaxLines(1); t1.setEllipsize(TextUtils.TruncateAt.END);
        if (mi != null) t1.setTextIsSelectable(true);
        TextView t2 = Ui.text(a, sub(d), 12, Ui.MUTED, false);
        t2.setTag("sub"); t2.setMaxLines(2);
        mid.addView(t1, Ui.fill());
        mid.addView(t2, Ui.fill());
        String st = d.optString("state");
        if (mi == null && ("on".equals(st) || "out".equals(st))) {                   // thanh còn mã
            LinearLayout track = Ui.row(a, 0);
            track.setBackground(Ui.round(Color.argb(46, 245, 165, 36), 99, 0));
            int left = Math.max(0, d.optInt("left")), total = Math.max(left, d.optInt("total"));
            View f = new View(a); f.setTag("fill"); f.setBackground(Ui.round(AMBER, 99, 0));
            View r = new View(a); r.setTag("rest");
            track.addView(f, new LinearLayout.LayoutParams(0, -1, left));
            track.addView(r, new LinearLayout.LayoutParams(0, -1, Math.max(0, total - left)));
            LinearLayout.LayoutParams tl = new LinearLayout.LayoutParams(-1, Ui.dp(5));
            tl.topMargin = Ui.dp(4);
            mid.addView(track, tl);
        }
        c.addView(mid, Ui.weight(1));
        View act = action(a, box, d);
        if (act != null) c.addView(act, Ui.wrap());
        TextView x = Ui.text(a, "✕", 15, Ui.MUTED, false);
        x.setGravity(Gravity.CENTER);
        x.setContentDescription(Ui.L("Thu nhỏ", "Minimize"));
        x.setOnClickListener(v -> { setMin(a, d, true); fill(a, box); });
        c.addView(x, new LinearLayout.LayoutParams(Ui.dp(32), Ui.dp(40)));
        return c;
    }
    private static Button small(Context c, String s, boolean hot) {
        Button b = Ui.button(c, s, hot ? Ui.PRIMARY : Ui.GHOST);
        b.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 14 * Ui.sp(1));
        b.setMinHeight(Ui.dp(40)); b.setMinimumHeight(Ui.dp(40));
        b.setPadding(Ui.dp(12), 0, Ui.dp(12), 0);
        if (hot) { b.setTextColor(INK); b.setBackground(amber(99)); }
        return b;
    }
    private static View action(MainActivity a, LinearLayout box, JSONObject d) {
        String st = d.optString("state"), why = d.isNull("why") ? "" : d.optString("why");
        JSONObject mi = mine(d);
        if (mi != null) {
            if (mi.optBoolean("used")) return null;
            Button b = small(a, Ui.L("Chép", "Copy"), false);
            b.setOnClickListener(v -> Offers.copy(a, mi.optString("code")));
            return b;
        }
        if ("soon".equals(st)) { Button b = small(a, "⏰", false); b.setEnabled(false); b.setAlpha(.6f); return b; }
        if (!"on".equals(st) || "new_account".equals(why)) return null;
        if ("need_dep".equals(why)) {
            Button b = small(a, Ui.L("Nạp tiền", "Top up"), false);
            b.setOnClickListener(v -> a.openTopup(d.optLong("need")));
            return b;
        }
        Button b = small(a, Ui.L("⚡ Nhận mã", "⚡ Claim"), true);
        b.setOnClickListener(v -> claim(a, box, d.optLong("id"), b));
        return b;
    }

    static void claim(MainActivity a, LinearLayout box, long id, View btn) {
        if (btn != null) btn.setEnabled(false);
        Api.bg(() -> Api.rpc("promo_drop_claim", new JSONObject().put("p_id", id)), r -> {
            if (btn != null) btn.setEnabled(true);
            if (r instanceof JSONObject && !a.isFinishing()) got(a, (JSONObject) r);
            load(() -> { if (!a.isFinishing()) fill(a, box); });
            Offers.at = 0;
            Offers.load(a::offersChanged);                                           // mã mới vào "Mã của tôi" + ô chọn nhanh dưới "Mã giảm giá"
        }, m -> {
            if (btn != null) btn.setEnabled(true);
            if (!a.isFinishing()) Ui.toast(a, m);
            load(() -> { if (!a.isFinishing()) fill(a, box); });
        });
    }

    /** Hộp chúc mừng: mã to · Chép · Thuê máy ngay. */
    private static void got(MainActivity a, JSONObject r) {
        LinearLayout c = Ui.col(a, 12);
        LinearLayout big = Ui.row(a, 12);
        big.setGravity(Gravity.CENTER_VERTICAL);
        big.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        big.setBackground(Ui.round(Ui.SUNK, 14, Color.argb(190, 245, 165, 36)));
        TextView badge = Ui.text(a, "−" + r.optInt("pct") + "%", 18, INK, true);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(amber(12));
        big.addView(badge, new LinearLayout.LayoutParams(Ui.dp(62), Ui.dp(50)));
        TextView code = Ui.text(a, r.optString("code"), 19, Ui.FG, true);
        code.setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD);
        code.setTextIsSelectable(true);
        big.addView(code, Ui.weight(1));
        Button cp = small(a, Ui.L("Chép mã", "Copy"), false);
        cp.setOnClickListener(v -> Offers.copy(a, r.optString("code")));
        big.addView(cp, Ui.wrap());
        c.addView(big, Ui.fill());
        long mx = r.optLong("max", 0);
        c.addView(Ui.muted(a, Ui.L("Mã giảm " + r.optInt("pct") + "%" + (mx > 0 ? " (tối đa " + Ui.vnd(mx) + ")" : "") + ", dùng 1 lần, hạn đến " + when(r.optString("expires_at"))
                        + ". Chỉ tài khoản của bạn dùng được — người khác nhập mã này sẽ bị từ chối.",
                r.optInt("pct") + "% off" + (mx > 0 ? " (up to " + Ui.vnd(mx) + ")" : "") + ", single use, valid until " + when(r.optString("expires_at")) + ". Only your account can use it.")), Ui.fill());
        c.addView(Ui.muted(a, Ui.L("Dùng khi thuê / gia hạn / nâng cấp cloud phone: bấm chọn mã ngay dưới ô “🏷️ Mã giảm giá”. Mã cũng nằm ở 🎁 Ưu đãi › 🎫 Mã của tôi.",
                "Use it when renting / renewing / upgrading a cloud phone: tap it under the “🏷️ Discount code” box. It's also in 🎁 Offers › 🎫 My codes.")), Ui.fill());
        final Dialog[] dl = new Dialog[1];
        Button go = Ui.button(a, "🛒 " + Ui.L("Thuê máy ngay", "Rent a phone"), Ui.PRIMARY);
        go.setOnClickListener(v -> { dl[0].dismiss(); a.show(1); });
        if (Api.SHOP) c.addView(go, Ui.fill());
        Button later = Ui.button(a, Ui.L("Để sau", "Later"), Ui.GHOST);
        later.setOnClickListener(v -> dl[0].dismiss());
        c.addView(later, Ui.fill());
        dl[0] = Ui.sheet(a, r.optBoolean("again") ? "🎫 " + Ui.L("Mã của bạn", "Your code") : "🎉 " + Ui.L("Bạn đã nhận được mã!", "You got a code!"), c);
        dl[0].show();
    }

    /** Khối đầu hộp 🎁 Ưu đãi (null = không có đợt đang / sắp phát). close = đóng hộp Ưu đãi trước khi làm việc khác. */
    static View offerBlock(MainActivity a, Runnable close) {
        JSONObject d = on() ? main() : null;
        if (d == null || (!live() && mine(d) == null)) return null;
        String why = d.isNull("why") ? "" : d.optString("why");
        if ("locked".equals(why)) return null;
        LinearLayout b = Ui.col(a, 8);
        b.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(12));
        b.setBackground(Ui.round(Ui.SUNK, 16, Color.argb(170, 245, 165, 36)));
        boolean soon = "soon".equals(d.optString("state"));
        b.addView(Ui.text(a, soon ? Ui.L("⏰ " + when(d.optString("starts_at")) + " phát " + d.optInt("total") + " mã giảm " + d.optInt("pct") + "%",
                        "⏰ " + d.optInt("total") + " codes for " + d.optInt("pct") + "% off at " + when(d.optString("starts_at")))
                : Ui.L("⚡ Đang phát mã giảm " + d.optInt("pct") + "% — còn " + d.optInt("left") + "/" + d.optInt("total"),
                        "⚡ Dropping " + d.optInt("pct") + "% off codes — " + d.optInt("left") + "/" + d.optInt("total") + " left"), 15, Ui.FG, true), Ui.fill());
        b.addView(Ui.muted(a, mine(d) != null ? sub(d) : terms(d)), Ui.fill());
        if (mine(d) == null && "on".equals(d.optString("state")) && why.isEmpty()) {
            Button go = small(a, Ui.L("⚡ Nhận mã ngay", "⚡ Claim my code"), true);
            go.setOnClickListener(v -> { if (close != null) close.run(); claim(a, a.dropV, d.optLong("id"), null); });
            b.addView(go, Ui.fill());
        } else if ("need_dep".equals(why) && "on".equals(d.optString("state"))) {
            b.addView(Ui.muted(a, sub(d)), Ui.fill());
            Button go = small(a, Ui.L("Nạp tiền", "Top up"), false);
            go.setOnClickListener(v -> { if (close != null) close.run(); a.openTopup(d.optLong("need")); });
            b.addView(go, Ui.fill());
        } else if (mine(d) == null) b.addView(Ui.muted(a, sub(d)), Ui.fill());
        return b;
    }
}
