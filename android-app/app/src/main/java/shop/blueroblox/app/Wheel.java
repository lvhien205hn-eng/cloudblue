package shop.blueroblox.app;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.app.Dialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.animation.OvershootInterpolator;
import android.view.animation.PathInterpolator;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/** 🎡 VÒNG QUAY MAY MẮN (SQL v34c) — giống web: nạp 100.000đ = 2 lượt, hết lượt quay thêm 15.000đ/lượt (luôn hỏi lại, trừ số dư).
 *  Máy chủ rút số (wheel_spin) → app chỉ quay hình tới ĐÚNG ô mã khách nhận. Khi quay: ẩn hết số + màu ô (dấu ?) → kim dừng →
 *  màn mở quà: hộp quà rơi · rung · nổ (nắp bay, tia sáng, pháo giấy + bong bóng) → thẻ mã. Khách không thấy tỷ lệ.
 *  Bản CH Play (Api.PLAY) KHÔNG có vòng quay: Google cấm quay thưởng trả tiền mà không công khai tỷ lệ.
 *  Máy chủ chưa chạy SQL v34c / admin tắt → wheel_status lỗi hoặc state off → ẩn hết, app như cũ. */
final class Wheel {
    static volatile JSONObject st = null;
    private static final int INK = Color.rgb(11, 23, 51), PEARL = Color.rgb(243, 247, 254), PEARL2 = Color.rgb(201, 215, 238),
            TXT = Color.rgb(236, 242, 253), SUB = Color.rgb(185, 203, 234);

    static boolean on() { return !Api.PLAY; }
    static boolean live() {
        JSONObject s = st; if (s == null) return false;
        String x = s.optString("state"); JSONArray p = s.optJSONArray("prizes");
        return ("on".equals(x) || "soon".equals(x)) && p != null && p.length() > 0;
    }
    static int per() { JSONObject s = st; return s == null ? 1 : Math.max(1, s.optInt("spins_per", 1)); }
    /** [nạp bao nhiêu, được mấy lượt] cho câu "Nạp 100.000đ = 2 lượt". */
    static long[] first() {
        JSONObject s = st; long pa = s == null ? 100000 : Math.max(1, s.optLong("per", 100000)), a = Math.max(s == null ? 0 : s.optLong("min"), pa);
        return new long[]{a, (a / pa) * per()};
    }
    static int spinsFor(long amount) {
        JSONObject s = st; if (s == null || amount < s.optLong("min")) return 0;
        return (int) (amount / Math.max(1, s.optLong("per", 100000))) * per();
    }
    static int topPct() {
        JSONObject s = st; JSONArray p = s == null ? null : s.optJSONArray("prizes"); int m = 0, any = 0;
        for (int i = 0; p != null && i < p.length(); i++) { JSONObject x = p.optJSONObject(i); any = Math.max(any, x.optInt("pct"));
            if (x.isNull("left") || x.optInt("left") > 0) m = Math.max(m, x.optInt("pct")); }
        return m > 0 ? m : any;
    }

    /** 🍀 vé may mắn: {giá, % trúng nhóm cao, mức thấp nhất nhóm cao, mức cao nhất, mức còn lại (-1 = không có)} · null = không bán vé (SQL cũ / admin tắt). */
    static double[] lucky() {
        JSONObject s = st; if (s == null || s.optLong("lucky_price") <= 0) return null;
        JSONArray p = s.optJSONArray("lucky_pool"); if (p == null || p.length() == 0) return null;
        int lo = Integer.MAX_VALUE; for (int i = 0; i < p.length(); i++) lo = Math.min(lo, p.optJSONObject(i).optInt("pct"));
        double rate = 0, all = 0; int gl = Integer.MAX_VALUE, gh = 0; boolean up = false;
        for (int i = 0; i < p.length(); i++) { JSONObject x = p.optJSONObject(i); int q = x.optInt("pct"); double r = x.optDouble("rate", 0); all += r;
            if (q > lo) { up = true; rate += r; gl = Math.min(gl, q); gh = Math.max(gh, q); } }
        if (!up) { rate = all; gl = lo; gh = lo; }
        return new double[]{s.optLong("lucky_price"), Math.round(rate * 100) / 100.0, gl, gh, up ? lo : -1};
    }
    static String rate(double v) {
        String t = v == Math.rint(v) ? String.valueOf((long) v) : String.format(java.util.Locale.US, "%.2f", v).replaceAll("0+$", "");
        return Ui.L(t.replace('.', ','), t);
    }
    static String luckyLine(double[] k) {
        String rg = k[2] == k[3] ? (int) k[2] + "%" : (int) k[2] + "–" + (int) k[3] + "%";
        return Ui.L(rate(k[1]) + "% trúng mã " + rg + (k[4] >= 0 ? " · còn lại mã " + (int) k[4] + "%" : ""),
                rate(k[1]) + "% chance of a " + rg + " code" + (k[4] >= 0 ? " · otherwise " + (int) k[4] + "%" : ""));
    }
    /** [5, 10] → "5% hoặc 10%" */
    static String pcts(JSONArray a) {
        List<Integer> v = new ArrayList<>();
        for (int i = 0; a != null && i < a.length(); i++) if (!v.contains(a.optInt(i))) v.add(a.optInt(i));
        java.util.Collections.sort(v);
        if (v.isEmpty()) return "";
        if (v.size() == 1) return v.get(0) + "%";
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < v.size() - 1; i++) b.append(i > 0 ? "%, " : "").append(v.get(i));
        return b + "%" + Ui.L(" hoặc ", " or ") + v.get(v.size() - 1) + "%";
    }
    /** mặt vé: các mức giải của vé lặp lại cho đủ ~8 ô */
    static List<JSONObject> luckySlices() {
        List<JSONObject> out = new ArrayList<>(); JSONObject s = st; JSONArray p = s == null ? null : s.optJSONArray("lucky_pool");
        if (p == null || p.length() == 0) return out;
        int rep = Math.max(1, (int) Math.ceil(8.0 / p.length()));
        for (int r = 0; r < rep; r++) for (int i = 0; i < p.length() && out.size() < 12; i++) {
            JSONObject x = new JSONObject(); try { x.put("pct", p.optJSONObject(i).optInt("pct")); x.put("left", JSONObject.NULL); } catch (Exception ignored) { } out.add(x); }
        return out;
    }

    static void load(Runnable cb) {
        if (!on()) return;
        Api.bg(() -> Api.rpc("wheel_status", new JSONObject()), r -> { st = r instanceof JSONObject ? (JSONObject) r : null; stAt = SystemClock.elapsedRealtime(); if (cb != null) cb.run(); },
                m -> { st = null; if (cb != null) cb.run(); });
    }

    // ================================================================ thẻ mở vòng quay (trang Tài khoản + hộp Nạp tiền)
    static View card(MainActivity a) {
        LinearLayout c = Ui.col(a, 8);
        c.setPadding(Ui.dp(16), Ui.dp(14), Ui.dp(16), Ui.dp(14));
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{Color.rgb(28, 67, 140), Color.rgb(11, 23, 54)});
        bg.setCornerRadius(Ui.dp(18)); bg.setStroke(Ui.dp(1), Color.argb(80, 223, 234, 252));
        c.setBackground(bg);
        TextView t = Ui.text(a, "", 16, Color.WHITE, true), s = Ui.text(a, "", 13, SUB, false);
        Button b = Ui.button(a, "", Ui.PRIMARY);
        c.addView(t, Ui.fill()); c.addView(s, Ui.fill()); c.addView(b, Ui.fill());
        c.setVisibility(View.GONE);
        Runnable fill = () -> {
            if (a.isFinishing() || !live()) { c.setVisibility(View.GONE); return; }
            JSONObject w = st; int left = w.optInt("left"); long[] f = first();
            t.setText("🎡 " + Ui.L("Vòng quay may mắn · mã giảm đến ", "Lucky wheel · codes up to ") + topPct() + "%");
            if ("soon".equals(w.optString("state"))) {
                s.setText(Ui.L("Bắt đầu ", "Starts ") + when(w.optString("starts_at")) + Ui.L(" · nạp ", " · top up ") + Ui.vnd(f[0]) + " = " + f[1] + Ui.L(" lượt quay", " spins"));
                b.setText(Ui.L("Xem giải", "See prizes"));
            } else if (left > 0) {
                s.setText(Ui.L("Bạn đang có " + left + " lượt quay — lượt nào cũng trúng 1 mã giảm giá", "You have " + left + " spins — every spin wins a discount code"));
                b.setText("🎡 " + Ui.L("Quay ngay · ", "Spin now · ") + left);
            } else {
                double[] lk = lucky();
                s.setText(Ui.L("Nạp ", "Top up ") + Ui.vnd(f[0]) + " = " + f[1] + Ui.L(" lượt quay", " spins")
                        + (w.optLong("price") > 0 ? Ui.L(" · mua lượt " + Ui.vnd(w.optLong("price")), " · buy a spin " + Ui.vnd(w.optLong("price"))) : "")
                        + (lk != null ? Ui.L(" · 🍀 vé may mắn " + Ui.vnd(lk[0]), " · 🍀 lucky ticket " + Ui.vnd(lk[0])) : ""));
                b.setText("🎡 " + Ui.L("Mở vòng quay", "Open the wheel"));
            }
            c.setVisibility(View.VISIBLE);
        };
        b.setOnClickListener(v -> open(a));
        c.setOnClickListener(v -> open(a));
        if (on()) load(fill);
        return c;
    }

    /** Dải 🎡 gọn ở đầu trang Máy của tôi + Thuê máy — khách thấy ngay vòng quay, bấm là mở. Ẩn khi vòng quay tắt / bản CH Play.
     *  Trạng thái đã tải trong 60 giây → vẽ ngay (khỏi nháy), không gọi máy chủ lại. */
    static long stAt = 0;
    static View strip(MainActivity a) { return strip(a, null); }
    /** after (16/11): gọi mỗi lần dải vừa được vẽ lại (hiện / ẩn) — trang chủ dùng để cập nhật dòng "Ẩn / Hiện ưu đãi". */
    static View strip(MainActivity a, Runnable after) {
        LinearLayout c = Ui.row(a, 12);
        c.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{Color.rgb(40, 90, 182), Color.rgb(20, 44, 100), Color.rgb(11, 23, 54)});
        bg.setCornerRadius(Ui.dp(18));
        bg.setStroke(Ui.dp(1), Color.argb(110, 223, 234, 252));
        c.setBackground(bg);
        TextView ic = Ui.text(a, "🎡", 24, Color.WHITE, false);
        ic.setGravity(Gravity.CENTER);
        ic.setBackground(Ui.round(Color.argb(38, 255, 255, 255), 14, Color.argb(90, 223, 234, 252)));
        c.addView(ic, new LinearLayout.LayoutParams(Ui.dp(46), Ui.dp(46)));
        LinearLayout tx = Ui.col(a, 1);
        TextView t = Ui.text(a, "", 15, Color.WHITE, true), s = Ui.text(a, "", 12.5f, SUB, false);
        t.setMaxLines(1);
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        s.setMaxLines(2);
        tx.addView(t, Ui.fill());
        tx.addView(s, Ui.fill());
        c.addView(tx, Ui.weight(1));
        TextView go = Ui.text(a, "", 13.5f, INK, true);
        go.setGravity(Gravity.CENTER);
        go.setPadding(Ui.dp(12), Ui.dp(8), Ui.dp(12), Ui.dp(8));
        GradientDrawable gg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{PEARL, PEARL2});
        gg.setCornerRadius(Ui.dp(99));
        go.setBackground(gg);
        c.addView(go, Ui.wrap());
        c.setClickable(true);
        c.setFocusable(true);
        c.setOnClickListener(v -> open(a));
        c.setVisibility(View.GONE);
        Runnable fill = () -> {
            if (a.isFinishing() || !live()) { c.setVisibility(View.GONE); if (after != null) after.run(); return; }
            JSONObject w = st; int left = w.optInt("left"); long[] f = first();
            t.setText(Ui.L("Vòng quay may mắn", "Lucky wheel"));
            String up = Ui.L("Mã giảm đến ", "Codes up to ") + topPct() + "% · ";
            c.setContentDescription(t.getText() + " · " + up);
            if ("soon".equals(w.optString("state"))) {
                s.setText(up + Ui.L("bắt đầu ", "starts ") + when(w.optString("starts_at")));
                go.setText(Ui.L("Xem giải", "Prizes"));
            } else if (left > 0) {
                s.setText(Ui.L("Bạn đang có " + left + " lượt quay — lượt nào cũng trúng mã giảm giá", "You have " + left + " spins — every spin wins a discount code"));
                go.setText(Ui.L("Quay · ", "Spin · ") + left);
            } else {
                s.setText(up + Ui.L("nạp ", "top up ") + Ui.vnd(f[0]) + " = " + f[1] + Ui.L(" lượt", " spins")
                        + (w.optLong("price") > 0 ? Ui.L(" · mua lượt " + Ui.vnd(w.optLong("price")), " · buy one " + Ui.vnd(w.optLong("price"))) : ""));
                go.setText(Ui.L("Mở ›", "Open ›"));
            }
            c.setVisibility(View.VISIBLE);
            if (after != null) after.run();
        };
        if (on()) {
            if (st != null) fill.run();
            if (st == null || SystemClock.elapsedRealtime() - stAt > 60_000L) load(fill);
        }
        return c;
    }

    /** Dòng "🎡 Lệnh nạp này được +N lượt quay" dưới số tiền trong hộp Nạp tiền. */
    static TextView hint(MainActivity a) {
        TextView t = Ui.text(a, "", 13.5f, Ui.SKY, true);
        t.setVisibility(View.GONE);
        return t;
    }
    static void hint(TextView t, long amount) {
        if (t == null) return;
        JSONObject w = st;
        if (!live()) { t.setVisibility(View.GONE); return; }
        int n = spinsFor(amount); long[] f = first();
        t.setText("soon".equals(w.optString("state")) ? Ui.L("🎡 Vòng quay bắt đầu " + when(w.optString("starts_at")) + " — lệnh nạp từ lúc đó mới được tính lượt.", "🎡 The wheel starts " + when(w.optString("starts_at")) + " — only top-ups from then on earn spins.")
                : n > 0 ? Ui.L("🎡 Lệnh nạp này được +" + n + " lượt quay may mắn", "🎡 This top-up earns +" + n + " lucky-wheel spins")
                : Ui.L("🎡 Nạp từ " + Ui.vnd(f[0]) + " để được " + f[1] + " lượt quay may mắn", "🎡 Top up " + Ui.vnd(f[0]) + "+ to earn " + f[1] + " lucky-wheel spins"));
        t.setVisibility(View.VISIBLE);
    }

    static String when(String iso) {
        long ms = MainActivity.parseTime(iso);
        return ms <= 0 ? "" : new java.text.SimpleDateFormat("HH:mm dd/MM", java.util.Locale.getDefault()).format(new java.util.Date(ms));
    }
    static boolean calm(Context c) {          // máy tắt hiệu ứng chuyển động (Tuỳ chọn nhà phát triển / Hỗ trợ tiếp cận) → bỏ hoạt ảnh dài
        try { return Settings.Global.getFloat(c.getContentResolver(), Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f; } catch (Exception e) { return false; }
    }
    static List<JSONObject> order(JSONArray pz) {   // xen kẽ giải nhỏ / giải lớn: 5 · 40 · 10 · 50 · 15 · 60 · 20 · 80 · 25 (giống web)
        List<JSONObject> a = new ArrayList<>(), lo = new ArrayList<>(), hi = new ArrayList<>(), out = new ArrayList<>();
        for (int i = 0; pz != null && i < pz.length(); i++) a.add(pz.optJSONObject(i));
        a.sort((x, y) -> x.optInt("pct") - y.optInt("pct"));
        for (JSONObject x : a) (x.optInt("pct") < 40 ? lo : hi).add(x);
        while (!lo.isEmpty() || !hi.isEmpty()) { if (!lo.isEmpty()) out.add(lo.remove(0)); if (!hi.isEmpty()) out.add(hi.remove(0)); }
        return out;
    }
    static void copy(Context c, String code) {
        try { ((ClipboardManager) c.getSystemService(Context.CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("code", code)); Ui.toast(c, Ui.L("Đã chép mã ", "Copied ") + code); }
        catch (Exception e) { Ui.toast(c, code); }
    }

    // ================================================================ hộp quay
    static void open(MainActivity a) {
        if (!on() || a.isFinishing()) return;
        new Sheet(a).show();
    }

    static final class Sheet {
        final MainActivity a; final Dialog d; final WheelView wv;
        final TextView left, sub, err, rulesT, luckT; final Button go, luckB; final LinearLayout guide, mine, rules, luckBox;
        boolean busy = false, paidAny = false, luck = false;
        JSONObject last = null;

        Sheet(MainActivity a) {
            this.a = a;
            d = new Dialog(a);
            d.requestWindowFeature(Window.FEATURE_NO_TITLE);
            LinearLayout box = Ui.col(a, 14);
            box.setPadding(Ui.dp(18), Ui.dp(16), Ui.dp(18), Ui.dp(22));
            GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(22, 47, 104), Color.rgb(12, 26, 62), Color.rgb(7, 16, 38)});
            box.setBackground(bg);

            LinearLayout head = Ui.row(a, 8);
            TextView title = Ui.text(a, Ui.L("Vòng quay may mắn", "Lucky wheel"), 21, Color.WHITE, true);
            TextView vip = Ui.text(a, "VIP", 11, INK, true);
            vip.setPadding(Ui.dp(7), Ui.dp(2), Ui.dp(7), Ui.dp(3));
            GradientDrawable vb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.WHITE, PEARL2}); vb.setCornerRadius(Ui.dp(7));
            vip.setBackground(vb);
            left = Ui.text(a, "", 13, INK, true);
            left.setPadding(Ui.dp(12), Ui.dp(5), Ui.dp(12), Ui.dp(6));
            head.addView(title); head.addView(vip, Ui.wrap());
            View sp = new View(a); head.addView(sp, Ui.weight(1)); head.addView(left, Ui.wrap());
            box.addView(head, Ui.fill());
            sub = Ui.text(a, "", 13, SUB, false);
            box.addView(sub, Ui.fill());

            wv = new WheelView(a);
            int sw = a.getResources().getDisplayMetrics().widthPixels;
            int size = Math.min(sw - Ui.dp(56), Ui.dp(340));
            LinearLayout.LayoutParams wl = new LinearLayout.LayoutParams(size, Math.round(size * WheelView.H / 200f));
            wl.gravity = Gravity.CENTER_HORIZONTAL;
            box.addView(wv, wl);
            wv.onHub = this::hub;

            go = Ui.button(a, "", Ui.PRIMARY);
            go.setTextSize(Ui.sp(16));
            go.setMinHeight(Ui.dp(52));
            box.addView(go, Ui.fill());
            go.setOnClickListener(v -> main());
            // 🍀 vé may mắn (SQL v34d): 1 lượt quay riêng, công khai tỷ lệ, luôn hỏi lại trước khi trừ tiền
            luckBox = Ui.row(a, 12);
            luckBox.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(12), Ui.dp(12));
            GradientDrawable lbg = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{Color.argb(80, 28, 150, 112), Color.argb(110, 8, 58, 56)});
            lbg.setCornerRadius(Ui.dp(14)); lbg.setStroke(Ui.dp(1), Color.argb(130, 122, 240, 200)); luckBox.setBackground(lbg);
            luckBox.addView(Ui.text(a, "🍀", 26, Color.WHITE, false), Ui.wrap());
            luckT = Ui.text(a, "", 13, Color.rgb(169, 220, 201), false);
            luckBox.addView(luckT, Ui.weight(1));
            luckB = Ui.button(a, Ui.L("Dùng vé", "Use ticket"), Ui.PRIMARY);
            GradientDrawable lb2 = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(92, 240, 194), Color.rgb(20, 169, 125)}); lb2.setCornerRadius(Ui.dp(12));
            luckB.setBackground(lb2); luckB.setTextColor(Color.rgb(3, 38, 27));
            luckB.setOnClickListener(v -> askLucky());
            luckBox.addView(luckB, Ui.wrap());
            luckBox.setVisibility(View.GONE);
            box.addView(luckBox, Ui.fill());
            err = Ui.text(a, "", 13.5f, Ui.BAD, true);
            err.setVisibility(View.GONE);
            box.addView(err, Ui.fill());

            guide = Ui.col(a, 8); box.addView(guide, Ui.fill());
            mine = Ui.col(a, 6); box.addView(mine, Ui.fill());
            rulesT = Ui.text(a, "📜 " + Ui.L("Thể lệ  ▸", "Rules  ▸"), 14.5f, Color.WHITE, true);
            rulesT.setPadding(0, Ui.dp(4), 0, Ui.dp(4));
            rules = Ui.col(a, 8); rules.setVisibility(View.GONE);
            rulesT.setOnClickListener(v -> { boolean o = rules.getVisibility() != View.VISIBLE; rules.setVisibility(o ? View.VISIBLE : View.GONE);
                rulesT.setText("📜 " + Ui.L("Thể lệ  ", "Rules  ") + (o ? "▾" : "▸")); });
            box.addView(rulesT, Ui.fill()); box.addView(rules, Ui.fill());
            Button close = Ui.button(a, Ui.L("Đóng", "Close"), Ui.GHOST);
            close.setOnClickListener(v -> d.dismiss());
            box.addView(close, Ui.fill());

            ScrollView sv = new ScrollView(a);
            sv.setFillViewport(true);
            sv.addView(box, new ViewGroup.LayoutParams(-1, -2));
            d.setContentView(sv);
            Ui.insets(sv, true, true);                                      // không lấn thanh trạng thái / thanh điều hướng
            Window win = d.getWindow();
            if (win != null) { win.setBackgroundDrawable(new ColorDrawable(Color.rgb(7, 16, 38))); win.setLayout(-1, -1); }
            d.setOnDismissListener(x -> { wv.alive = false; if (paidAny && !a.isFinishing()) a.refresh(); });
            render();
            load(this::render);
        }
        void show() { d.show(); }

        void render() {
            JSONObject w = st;
            int l = w == null ? 0 : w.optInt("left"); long[] f = first();
            left.setText(Ui.L(l + " lượt", l + (l == 1 ? " spin" : " spins")));
            boolean has = w != null && "on".equals(w.optString("state")) && l > 0;
            GradientDrawable lb = has ? new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.WHITE, PEARL2}) : new GradientDrawable();
            if (!has) { lb.setColor(Color.argb(150, 8, 17, 40)); lb.setStroke(Ui.dp(1), Color.argb(80, 223, 234, 252)); }
            lb.setCornerRadius(Ui.dp(99)); left.setBackground(lb); left.setTextColor(has ? INK : Color.rgb(211, 226, 251));
            String state = w == null ? "off" : w.optString("state");
            sub.setText(w == null ? Ui.L("Vòng quay đang tạm tắt.", "The lucky wheel is off.")
                    : "soon".equals(state) ? Ui.L("Bắt đầu ", "Starts ") + when(w.optString("starts_at")) + ". " + Ui.L("Nạp ", "Top up ") + Ui.vnd(f[0]) + " = " + f[1] + Ui.L(" lượt quay.", " spins.")
                    : "on".equals(state) ? Ui.L("Nạp ", "Top up ") + Ui.vnd(f[0]) + " = " + f[1] + Ui.L(" lượt · lượt nào cũng trúng mã giảm giá · số dư ", " spins · every spin wins a code · balance ") + Ui.vnd(bal())
                    : "ended".equals(state) ? Ui.L("Chương trình đã kết thúc. Mã đã trúng vẫn dùng được đến hết hạn.", "This event has ended. Codes you won stay valid until they expire.")
                    : Ui.L("Vòng quay đang tạm tắt. Mã đã trúng vẫn dùng được đến hết hạn.", "The wheel is off. Codes you won stay valid until they expire."));
            if (!busy) { wv.lucky = luck; wv.set(luck ? luckySlices() : order(w == null ? null : w.optJSONArray("prizes"))); }
            buttons();
            double[] lk = lucky();
            boolean showLk = lk != null && w != null && "on".equals(state);
            luckBox.setVisibility(showLk ? View.VISIBLE : View.GONE);
            if (showLk) { luckT.setText(Ui.L("Vé may mắn · ", "Lucky ticket · ") + Ui.vnd(lk[0]) + "\n" + luckyLine(lk)); luckB.setEnabled(!busy); luckB.setAlpha(busy ? .6f : 1f); }
            fillGuide(); fillMine(); fillRules();
        }
        double bal() { JSONObject w = st; return a.prof.has("balance") ? a.prof.optDouble("balance", 0) : (w == null ? 0 : w.optDouble("balance", 0)); }

        String act = "spin";
        void buttons() {
            JSONObject w = st; int l = w == null ? 0 : w.optInt("left"); String state = w == null ? "off" : w.optString("state"); long[] f = first();
            boolean dis = false; String txt; act = "spin"; int kind = 0;   // 0 thường · 1 ngọc trai (mua) · 2 viền
            if (busy) { txt = Ui.L("Đang quay…", "Spinning…"); dis = true; }
            else if ("off".equals(state)) { txt = Ui.L("Vòng quay đang tạm tắt", "The wheel is off"); dis = true; }
            else if ("ended".equals(state)) { txt = Ui.L("Chương trình đã kết thúc", "This event has ended"); dis = true; }
            else if ("soon".equals(state)) { txt = Ui.L("Bắt đầu lúc ", "Starts ") + when(w.optString("starts_at")); dis = true; }
            else if (l > 0) txt = Ui.L("Quay ngay · còn " + l + " lượt", "Spin now · " + l + " left");
            else if (w.optBoolean("can_buy")) { txt = "➕ " + (w.optInt("earned") > 0 ? Ui.L("Quay thêm · " + Ui.vnd(w.optLong("price")) + "/lượt", "Extra spin · " + Ui.vnd(w.optLong("price")))
                    : Ui.L("Mua lượt quay · " + Ui.vnd(w.optLong("price")), "Buy a spin · " + Ui.vnd(w.optLong("price")))); act = "buy"; kind = 1; }
            else if (w.optLong("price") > 0 && w.optBoolean("qualified") && !w.isNull("buy_left") && w.optInt("buy_left") == 0) {
                txt = Ui.L("Hôm nay đã mua đủ lượt — nạp thêm để nhận lượt mới", "Daily extra-spin limit reached — top up for more"); act = "top"; kind = 2; }
            else { txt = "💳 " + Ui.L("Nạp " + Ui.vnd(f[0]) + " để nhận " + f[1] + " lượt quay", "Top up " + Ui.vnd(f[0]) + " to get " + f[1] + " spins"); act = "top"; kind = 2; }
            go.setText(txt); go.setEnabled(!dis); go.setAlpha(dis ? .6f : 1f);
            if (kind == 1) { GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.WHITE, PEARL2}); g.setCornerRadius(Ui.dp(14)); go.setBackground(g); go.setTextColor(INK); }
            else if (kind == 2) { Ui.ripple(go, Color.argb(120, 8, 17, 40), 14, Color.argb(110, 223, 234, 252)); go.setTextColor(Color.WHITE); }
            else { Ui.glossy(go, 14); go.setTextColor(Color.WHITE); }
            wv.hubOn = !busy && !luck && w != null && "on".equals(state) && (l > 0 || w.optBoolean("can_buy"));
            wv.invalidate();
        }
        void main() { if ("top".equals(act)) { d.dismiss(); a.openTopup(); } else if ("buy".equals(act)) ask(); else spin(false); }
        void hub() { JSONObject w = st; if (w == null || busy) return; if (w.optInt("left") > 0) spin(false); else if (w.optBoolean("can_buy")) ask(); }

        /** Quay thêm có tính phí: LUÔN hỏi lại, ghi rõ giá + số dư còn lại. Thiếu tiền → mời nạp thêm. */
        void ask() {
            JSONObject w = st; if (w == null || busy) return;
            long price = w.optLong("price"); double b = bal();
            String more = w.isNull("buy_left") ? "" : Ui.L(" · hôm nay còn mua được " + w.optInt("buy_left") + " lượt", " · " + w.optInt("buy_left") + " extra spins left today");
            if (b < price) {
                Ui.confirm(a, Ui.L("Số dư chưa đủ", "Not enough balance"), Ui.L("Số dư " + Ui.vnd(b) + " chưa đủ " + Ui.vnd(price) + " — nạp thêm để quay tiếp.", "Your balance " + Ui.vnd(b) + " is below " + Ui.vnd(price) + " — top up to keep spinning."),
                        "💳 " + Ui.L("Nạp thêm", "Top up"), () -> { d.dismiss(); a.openTopup(price - b); });
                return;
            }
            String note = w.isNull("paid_max") ? "" : "🎯 " + Ui.L("Lượt mua chỉ trúng mã " + pcts(w.optJSONArray("paid_pcts")) + " — mã lớn hơn có ở lượt nạp tiền" + (lucky() != null ? " và 🍀 vé may mắn" : "") + ".",
                    "Bought spins only win " + pcts(w.optJSONArray("paid_pcts")) + " codes — bigger codes come from top-up spins" + (lucky() != null ? " and 🍀 lucky tickets" : "") + ".") + "\n\n";
            Ui.confirm(a, w.optInt("earned") > 0 ? Ui.L("Quay thêm 1 lượt?", "One more spin?") : Ui.L("Mua 1 lượt quay?", "Buy a spin?"),
                    note + Ui.L("Trừ " + Ui.vnd(price) + " vào số dư · còn lại " + Ui.vnd(b - price), Ui.vnd(price) + " from your balance · " + Ui.vnd(b - price) + " left") + more,
                    Ui.L("Trả " + Ui.vnd(price) + " & quay", "Pay " + Ui.vnd(price) + " & spin"), () -> spin(true, false));
        }

        /** 🍀 dùng vé: LUÔN hỏi lại, ghi đủ từng mức giải + tỷ lệ, giá, số dư còn lại. */
        void askLucky() {
            JSONObject w = st; double[] k = lucky(); if (w == null || k == null || busy || !"on".equals(w.optString("state"))) return;
            long price = (long) k[0]; double b = bal();
            if (w.has("can_lucky") && !w.optBoolean("can_lucky")) { Ui.toast(a, Ui.L("Hôm nay bạn đã mua đủ số lượt / vé — mai quay tiếp nhé.", "You've reached today's limit for spins / tickets — come back tomorrow.")); return; }
            if (b < price) {
                Ui.confirm(a, Ui.L("Số dư chưa đủ", "Not enough balance"), Ui.L("Số dư " + Ui.vnd(b) + " chưa đủ " + Ui.vnd(price) + " — nạp thêm để dùng vé.", "Your balance " + Ui.vnd(b) + " is below " + Ui.vnd(price) + " — top up to use a ticket."),
                        "💳 " + Ui.L("Nạp thêm", "Top up"), () -> { d.dismiss(); a.openTopup(price - b); });
                return;
            }
            StringBuilder odds = new StringBuilder();
            List<JSONObject> pool = new ArrayList<>(); JSONArray p = w.optJSONArray("lucky_pool");
            for (int i = 0; p != null && i < p.length(); i++) pool.add(p.optJSONObject(i));
            pool.sort((x, y) -> y.optInt("pct") - x.optInt("pct"));
            for (JSONObject x : pool) odds.append(Ui.L("Mã ", "Code ")).append(x.optInt("pct")).append("% · ").append(rate(x.optDouble("rate", 0))).append("%\n");
            String more = w.isNull("buy_left") ? "" : Ui.L(" · hôm nay còn mua được " + w.optInt("buy_left") + " lượt / vé", " · " + w.optInt("buy_left") + " spins / tickets left today");
            Ui.confirm(a, "🍀 " + Ui.L("Dùng 1 vé may mắn?", "Use a lucky ticket?"),
                    odds + "\n" + Ui.L("Trừ " + Ui.vnd(price) + " vào số dư · còn lại " + Ui.vnd(b - price), Ui.vnd(price) + " from your balance · " + Ui.vnd(b - price) + " left") + more,
                    Ui.L("Trả " + Ui.vnd(price) + " & quay", "Pay " + Ui.vnd(price) + " & spin"), () -> spin(true, true));
        }

        void spin(boolean pay) { spin(pay, false); }
        void spin(boolean pay, boolean lucky) {
            JSONObject w = st;
            if (busy || w == null || !"on".equals(w.optString("state"))) return;
            int l = w.optInt("left"); double[] k = lucky ? lucky() : null;
            if (lucky && k == null) return;
            if (!lucky && l <= 0 && !pay) { if (w.optBoolean("can_buy")) ask(); return; }
            luck = lucky; wv.lucky = lucky; wv.set(lucky ? luckySlices() : order(w.optJSONArray("prizes")));
            busy = true; err.setVisibility(View.GONE); wv.win = -1; wv.mys = true; buttons();     // ẨN hết số + màu ô khi quay
            final long price = w.optLong("price");
            JSONObject args = new JSONObject();
            try {
                if (lucky) { args.put("p_lucky", true); args.put("p_price", (long) k[0]); args.put("p_terms", w.optString("terms")); }
                else if (l <= 0) { args.put("p_pay", true); args.put("p_price", price); if (w.has("terms")) args.put("p_terms", w.optString("terms")); }   // SQL cũ (chưa có terms) → gửi như bản 3
            } catch (Exception ignored) { }
            Api.bg(() -> Api.rpc("wheel_spin", args), r -> {
                if (!(r instanceof JSONObject) || ((JSONObject) r).optString("code").isEmpty()) { fail(Ui.L("Vòng quay đã hết giải.", "All prizes are gone.")); return; }
                JSONObject x = (JSONObject) r; last = x;
                if (x.optLong("paid") > 0) { paidAny = true; try { a.prof.put("balance", x.optDouble("balance")); } catch (Exception ignored) { } }
                try { x.put("lucky", lucky); } catch (Exception ignored) { }
                List<JSONObject> pz = wv.pz; List<Integer> ks = new ArrayList<>();
                for (int i = 0; i < pz.size(); i++) if (pz.get(i).optInt("pct") == x.optInt("pct")) ks.add(i);       // kim dừng đúng ô mã khách NHẬN
                if (ks.isEmpty()) for (int i = 0; i < pz.size(); i++) if (pz.get(i).optInt("pct") == x.optInt("drawn")) ks.add(i);
                final int kk = ks.isEmpty() ? 0 : ks.get((int) (Math.random() * ks.size()));                        // mặt vé: ô trùng → chọn ngẫu nhiên 1 ô
                wv.spinTo(kk, calm(a), () -> {
                    busy = false; wv.win = kk;
                    try { JSONObject s = st; if (s != null) { s.put("left", x.optInt("left")); if (x.has("buy_left")) s.put("buy_left", x.opt("buy_left"));
                        if (x.optLong("paid") > 0) s.put("balance", x.optDouble("balance"));
                        if (!s.isNull("buy_left") && s.optInt("buy_left") == 0) { s.put("can_buy", false); s.put("can_lucky", false); } } } catch (Exception ignored) { }
                    buttons();
                    wv.postDelayed(() -> reveal(x), calm(a) ? 0 : 380);
                    load(() -> { if (!busy) render(); });
                });
            }, this::fail);
        }
        void fail(String m) { busy = false; wv.mys = false; luck = false; err.setText(m); err.setVisibility(View.VISIBLE); buttons(); load(this::render); }

        void reveal(JSONObject r) {
            if (a.isFinishing()) return;
            JSONObject w = st; boolean lk = r.optBoolean("lucky"); int l = w == null || lk ? 0 : w.optInt("left");
            boolean buy = !lk && l <= 0 && w != null && w.optBoolean("can_buy");
            double[] k = lucky(); long more = lk && k != null && (w == null || !w.has("can_lucky") || w.optBoolean("can_lucky")) ? (long) k[0] : 0;
            new Reveal(a, r, l, buy ? w.optLong("price") : 0, more, again -> {
                wv.mys = false;                                                         // hết bất ngờ → hiện lại số, ô vừa trúng sáng lên
                if (luck) { luck = false; wv.win = -1; render(); } else wv.invalidate();  // xong vé may mắn → về mặt vòng chính
                if ("again".equals(again)) spin(false); else if ("buy".equals(again)) ask(); else if ("lucky".equals(again)) askLucky();
            }).show();
        }

        // ---------- hướng dẫn · mã của tôi · thể lệ ----------
        void fillGuide() {
            guide.removeAllViews();
            JSONObject w = st; if (w == null) return;
            long[] f = first(); int sp = per();
            guide.addView(Ui.text(a, "📖 " + Ui.L("Hướng dẫn chơi", "How to play"), 15, Color.WHITE, true));
            step("💳", Ui.L("Nạp " + Ui.vnd(f[0]) + " = " + f[1] + " lượt", "Top up " + Ui.vnd(f[0]) + " = " + f[1] + " spins"),
                    Ui.L("Cứ " + Ui.vnd(w.optLong("per")) + " nạp được " + sp + " lượt quay miễn phí. Nạp ngân hàng hay crypto đều tính.", "Every " + Ui.vnd(w.optLong("per")) + " topped up gives " + sp + " free spins. Bank and crypto both count."));
            step("🎡", Ui.L("Bấm Quay", "Tap Spin"), Ui.L("Đang quay, số trên vòng ẩn hết. Kim dừng là hộp quà mở ra mã của bạn.", "While it spins the numbers hide. When it stops, a gift box opens with your code."));
            step("🏷️", Ui.L("Dùng mã khi thanh toán", "Use the code at checkout"), Ui.L("Nhập ở ô \"🏷️ Mã giảm giá\" khi thuê / gia hạn máy. Mã dùng 1 lần, hạn " + w.optInt("days", 7) + " ngày.",
                    "Enter it in the \"🏷️ Discount code\" box when renting or renewing. One use, valid " + w.optInt("days", 7) + " days."));
            if (w.optLong("price") > 0) step("➕", Ui.L("Mua lượt " + Ui.vnd(w.optLong("price")), "Buy a spin " + Ui.vnd(w.optLong("price"))),
                    (w.optBoolean("need_topup") ? Ui.L("Hết lượt miễn phí vẫn quay tiếp được.", "Out of free spins? Keep going.") : Ui.L("Không cần nạp đủ " + Ui.vnd(f[0]) + " — có số dư là mua được.", "No need to top up " + Ui.vnd(f[0]) + " — any balance works."))
                    + (w.isNull("paid_max") ? "" : Ui.L(" Lượt mua trúng mã " + pcts(w.optJSONArray("paid_pcts")) + ".", " Bought spins win " + pcts(w.optJSONArray("paid_pcts")) + " codes."))
                    + Ui.L(" Luôn hỏi lại trước khi trừ tiền.", " Always confirmed before paying."));
            double[] lk = lucky();
            if (lk != null) step("🍀", Ui.L("Vé may mắn " + Ui.vnd(lk[0]), "Lucky ticket " + Ui.vnd(lk[0])),
                    luckyLine(lk) + Ui.L(". Vòng đổi sang mặt vé riêng, trừ vào số dư, luôn hỏi lại trước khi trừ.", ". The wheel switches to the ticket face; paid from your balance, always confirmed first."));
            TextView apps = Ui.text(a, "💻 " + Ui.L("Chơi được cả trên web (vòng quay ngay trang chủ) và app máy tính CloudBlue PC. Lượt quay, vé và mã dùng chung cho cả tài khoản.",
                    "Also on the website and the CloudBlue PC app (Top up → 🎡 Lucky wheel). Spins and codes are shared across your account."), 12.5f, SUB, false);
            apps.setPadding(Ui.dp(11), Ui.dp(9), Ui.dp(11), Ui.dp(9));
            apps.setBackground(Ui.round(Color.TRANSPARENT, 12, Color.argb(60, 223, 234, 252)));
            guide.addView(apps, Ui.fill());
        }
        void step(String icon, String title, String text) {
            LinearLayout r = Ui.row(a, 10);
            r.setGravity(Gravity.TOP);
            r.setPadding(Ui.dp(10), Ui.dp(10), Ui.dp(10), Ui.dp(10));
            r.setBackground(Ui.round(Color.argb(12, 255, 255, 255), 12, Color.argb(34, 223, 234, 252)));
            TextView i = Ui.text(a, icon, 15, Color.WHITE, false);
            i.setGravity(Gravity.CENTER);
            GradientDrawable ib = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(62, 120, 221), Color.rgb(22, 50, 106)}); ib.setCornerRadius(Ui.dp(9));
            i.setBackground(ib);
            r.addView(i, new LinearLayout.LayoutParams(Ui.dp(30), Ui.dp(30)));
            LinearLayout tx = Ui.col(a, 2);
            tx.addView(Ui.text(a, title, 13.5f, Color.WHITE, true));
            tx.addView(Ui.text(a, text, 12.5f, SUB, false));
            r.addView(tx, Ui.weight(1));
            guide.addView(r, Ui.fill());
        }
        void fillMine() {
            mine.removeAllViews();
            JSONObject w = st; JSONArray cs = w == null ? null : w.optJSONArray("codes");
            if (cs == null || cs.length() == 0) { mine.addView(Ui.text(a, Ui.L("Mã bạn quay trúng sẽ nằm ở đây.", "Codes you win will show up here."), 13, SUB, false)); return; }
            mine.addView(Ui.text(a, "🎟️ " + Ui.L("Mã của tôi", "My codes"), 15, Color.WHITE, true));
            for (int i = 0; i < cs.length(); i++) {
                JSONObject c = cs.optJSONObject(i); final String code = c.optString("code");
                long exp = MainActivity.parseTime(c.optString("expires_at"));
                boolean used = c.optBoolean("used"), act = c.optBoolean("active", true), gone = exp > 0 && exp <= System.currentTimeMillis(), live = !used && act && !gone;
                LinearLayout r = Ui.row(a, 10);
                r.setPadding(Ui.dp(10), Ui.dp(8), Ui.dp(10), Ui.dp(8));
                r.setBackground(Ui.round(Color.argb(8, 255, 255, 255), 12, Color.argb(36, 223, 234, 252)));
                r.setAlpha(live ? 1f : .5f);
                TextView p = Ui.text(a, c.optInt("pct") + "%", 14, c.optInt("pct") >= 40 ? INK : Color.WHITE, true);
                p.setGravity(Gravity.CENTER);
                GradientDrawable pb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, c.optInt("pct") >= 40 ? new int[]{Color.WHITE, PEARL2} : new int[]{Color.rgb(62, 120, 221), Color.rgb(22, 50, 106)});
                pb.setCornerRadius(Ui.dp(8)); p.setBackground(pb);
                r.addView(p, new LinearLayout.LayoutParams(Ui.dp(52), Ui.dp(30)));
                LinearLayout tx = Ui.col(a, 1);
                TextView ct = Ui.text(a, code, 13.5f, Color.WHITE, true); ct.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
                tx.addView(ct);
                tx.addView(Ui.text(a, (used ? Ui.L("Đã dùng", "Used") : !act ? Ui.L("Đã tắt", "Disabled") : gone ? Ui.L("Hết hạn", "Expired") : Ui.L("Dùng được đến ", "Valid until ") + MainActivity.fdate(exp))
                        + (live && c.optBoolean("share") ? " · " + Ui.L("🤝 tặng bạn bè được", "🤝 shareable") : ""), 12, SUB, false));
                r.addView(tx, Ui.weight(1));
                if (live) { TextView cp = Ui.text(a, Ui.L("Chép", "Copy"), 13, Ui.SKY, true); cp.setPadding(Ui.dp(8), Ui.dp(6), Ui.dp(4), Ui.dp(6)); cp.setOnClickListener(v -> copy(a, code)); r.addView(cp, Ui.wrap()); }
                mine.addView(r, Ui.fill());
                if (i >= 29) break;
            }
        }
        void fillRules() {
            rules.removeAllViews();
            JSONObject w = st; if (w == null) return;
            int sp = per(); long pa = w.optLong("per", 100000);
            rule("⏰ " + Ui.L("Thời gian: từ " + when(w.optString("starts_at")) + (w.isNull("ends_at") ? " đến khi có thông báo kết thúc." : " đến " + when(w.optString("ends_at")) + "."),
                    "When: from " + when(w.optString("starts_at")) + (w.isNull("ends_at") ? " until further notice." : " to " + when(w.optString("ends_at")) + ".")));
            rule("💳 " + Ui.L("Mỗi lệnh nạp thành công từ " + Ui.vnd(w.optLong("min")) + " trong thời gian chương trình: cứ " + Ui.vnd(pa) + " = " + sp + " lượt quay (ví dụ nạp " + Ui.vnd(pa * 2.5) + " = " + (2 * sp) + " lượt). Tính nạp ngân hàng và crypto; nạp qua Google Play không tính lượt.",
                    "Each successful top-up of " + Ui.vnd(w.optLong("min")) + "+ during the event: every " + Ui.vnd(pa) + " = " + sp + " spins (e.g. " + Ui.vnd(pa * 2.5) + " = " + (2 * sp) + "). Bank and crypto count; Google Play top-ups don't."));
            boolean hasLk = lucky() != null;
            if (w.optLong("price") > 0) rule("➕ " + Ui.L("Mua lượt: " + Ui.vnd(w.optLong("price")) + "/lượt, trừ vào số dư" + (w.optBoolean("need_topup") ? ", dành cho tài khoản đã nạp từ " + Ui.vnd(w.optLong("min")) + " trong chương trình" : "")
                    + (w.optInt("buy_max") > 0 ? ", tối đa " + w.optInt("buy_max") + " lượt mua + vé/ngày" : "") + "."
                    + (w.isNull("paid_max") ? "" : " Lượt mua chỉ trúng mã " + pcts(w.optJSONArray("paid_pcts")) + "; mã lớn hơn có ở lượt nạp tiền" + (hasLk ? " và vé may mắn" : "") + ".") + " Luôn hỏi lại trước khi trừ tiền.",
                    "Buy a spin: " + Ui.vnd(w.optLong("price")) + " each from your balance" + (w.optInt("buy_max") > 0 ? ", up to " + w.optInt("buy_max") + " spins + tickets per day" : "") + "."
                    + (w.isNull("paid_max") ? "" : " Bought spins only win " + pcts(w.optJSONArray("paid_pcts")) + " codes; bigger codes come from top-up spins" + (hasLk ? " and lucky tickets" : "") + ".") + " You're always asked before paying."));
            double[] lk = lucky();
            if (lk != null) {
                StringBuilder o = new StringBuilder(); List<JSONObject> pool = new ArrayList<>(); JSONArray lp = w.optJSONArray("lucky_pool");
                for (int i = 0; lp != null && i < lp.length(); i++) pool.add(lp.optJSONObject(i));
                pool.sort((x, y) -> y.optInt("pct") - x.optInt("pct"));
                for (JSONObject x : pool) o.append(o.length() > 0 ? " · " : "").append(Ui.L("mã ", "")).append(x.optInt("pct")).append(Ui.L("%: ", "% code: ")).append(rate(x.optDouble("rate", 0))).append("%");
                rule("🍀 " + Ui.L("Vé may mắn: " + Ui.vnd(lk[0]) + "/vé = 1 lượt quay riêng (không dùng lượt miễn phí), trừ vào số dư. Tỷ lệ công khai: " + o + ". Mã từ vé không giới hạn số lượng.",
                        "Lucky ticket: " + Ui.vnd(lk[0]) + " each = one separate spin (doesn't use free spins), paid from your balance. Published odds: " + o + ". Ticket codes are unlimited."));
            }
            rule("🎟️ " + Ui.L("Lượt nào cũng trúng 1 mã giảm giá: dùng 1 lần cho 1 đơn, hạn " + w.optInt("days", 7) + " ngày, " + (w.optBoolean("share") ? "giữ dùng sau hoặc tặng bạn bè dùng đều được" : "chỉ tài khoản quay trúng dùng được") + (w.optLong("max_disc") > 0 ? ", giảm tối đa " + Ui.vnd(w.optLong("max_disc")) : "") + ".",
                    "Every spin wins a discount code: one use on one order, valid " + w.optInt("days", 7) + " days, " + (w.optBoolean("share") ? "keep it for later or give it to a friend." : "only for the winning account.")));
            rule("🎲 " + Ui.L("Kết quả quay hoàn toàn ngẫu nhiên do máy chủ quyết định. Mỗi ô có tỷ lệ trúng khác nhau — giải càng lớn càng hiếm. Giải có số lượng giới hạn; ô ghi HẾT là đã có người trúng hết.",
                    "Results are completely random and decided by the server. Each slice has a different chance — the bigger the prize, the rarer it is. Prizes are limited; a slice marked GONE has been fully won."));
            List<JSONObject> pz = order(w.optJSONArray("prizes"));
            pz.sort((x, y) -> y.optInt("pct") - x.optInt("pct"));
            for (JSONObject p : pz) {
                LinearLayout r = Ui.row(a, 8);
                r.addView(Ui.text(a, Ui.L("Mã giảm ", "Code −") + p.optInt("pct") + "%", 13, TXT, false), Ui.weight(1));
                r.addView(Ui.text(a, p.isNull("stock") ? Ui.L("Không giới hạn", "Unlimited") : Ui.L(p.optInt("stock") + " giải · còn " + p.optInt("left"), p.optInt("stock") + " · " + p.optInt("left") + " left"), 13, SUB, false), Ui.wrap());
                rules.addView(r, Ui.fill());
            }
        }
        void rule(String s) { rules.addView(Ui.text(a, s, 13, SUB, false), Ui.fill()); }
    }

    // ================================================================ vẽ vòng quay (đơn vị 200 × H, tâm 100,108)
    static final class WheelView extends View {
        static final float H = 214f, C = 100f, CY = 108f, R = 85f;
        List<JSONObject> pz = new ArrayList<>();
        float rot = 0; boolean mys = false, spinning = false, hubOn = false, alive = true, lucky = false; int win = -1;
        Runnable onHub;
        final long t0 = SystemClock.uptimeMillis();
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG), tp = new Paint(Paint.ANTI_ALIAS_FLAG);
        final RectF oval = new RectF(C - R, CY - R, C + R, CY + R);
        Shader lo1, lo2, mid, hi, gone, m1, m2, rim, gloss, hub, gem, glow, pinG, k1, k2, k3, k4, km1, km2, kglow;
        final Path pin = new Path();

        WheelView(Context c) {
            super(c);
            tp.setTextAlign(Paint.Align.CENTER); tp.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
            lo1 = rg(Color.rgb(13, 29, 68), Color.rgb(38, 74, 143)); lo2 = rg(Color.rgb(9, 23, 55), Color.rgb(26, 56, 114)); mid = rg(Color.rgb(32, 86, 183), Color.rgb(116, 159, 230));
            hi = rg(Color.rgb(195, 209, 232), Color.WHITE); gone = rg(Color.rgb(23, 31, 51), Color.rgb(44, 55, 82));
            m1 = rg(Color.rgb(10, 25, 64), Color.rgb(34, 66, 127)); m2 = rg(Color.rgb(15, 34, 82), Color.rgb(44, 86, 166));
            k1 = rg(Color.rgb(122, 90, 16), Color.rgb(255, 224, 138)); k2 = rg(Color.rgb(13, 122, 95), Color.rgb(92, 240, 194));      // 🍀 mặt vé: cao nhất vàng · xanh ngọc · thấp nhất xanh đậm
            k3 = rg(Color.rgb(10, 85, 70), Color.rgb(32, 185, 140)); k4 = rg(Color.rgb(6, 42, 40), Color.rgb(17, 82, 74));
            km1 = rg(Color.rgb(4, 38, 31), Color.rgb(15, 90, 74)); km2 = rg(Color.rgb(7, 58, 48), Color.rgb(19, 122, 99));
            kglow = new RadialGradient(C, CY, 112, new int[]{Color.argb(95, 60, 224, 176), Color.argb(30, 19, 120, 90), Color.argb(0, 0, 0, 0)}, new float[]{0, .46f, 1}, Shader.TileMode.CLAMP);
            rim = new LinearGradient(0, 0, 200, 216, new int[]{Color.WHITE, Color.rgb(174, 187, 210), Color.rgb(244, 247, 252), Color.rgb(142, 156, 182), Color.rgb(233, 239, 248)}, null, Shader.TileMode.CLAMP);
            gloss = new RadialGradient(C - 22, CY - 40, 120, new int[]{Color.argb(66, 255, 255, 255), Color.argb(0, 255, 255, 255)}, new float[]{0, .5f}, Shader.TileMode.CLAMP);
            hub = new RadialGradient(C - 8, CY - 11, 32, new int[]{Color.WHITE, Color.rgb(181, 204, 242), Color.rgb(90, 140, 226), Color.rgb(30, 80, 171), Color.rgb(13, 43, 112)}, new float[]{0, .1f, .4f, .72f, 1}, Shader.TileMode.CLAMP);
            gem = new RadialGradient(98.6f, 6.4f, 4.6f, new int[]{Color.rgb(211, 227, 251), Color.rgb(90, 140, 226), Color.rgb(24, 64, 139)}, new float[]{0, .5f, 1}, Shader.TileMode.CLAMP);
            glow = new RadialGradient(C, CY, 112, new int[]{Color.argb(95, 116, 159, 230), Color.argb(30, 48, 110, 218), Color.argb(0, 0, 0, 0)}, new float[]{0, .46f, 1}, Shader.TileMode.CLAMP);
            pinG = new LinearGradient(C - 8, -1, C + 8, 30, new int[]{Color.WHITE, Color.rgb(174, 187, 210), Color.rgb(238, 243, 251)}, null, Shader.TileMode.CLAMP);
            pin.moveTo(C, 30); pin.lineTo(C - 7.6f, 10); pin.lineTo(C + 7.6f, 10); pin.close(); pin.addCircle(C, 6.6f, 7.6f, Path.Direction.CW);
            setContentDescription(Ui.L("Vòng quay may mắn", "Lucky wheel"));
        }
        static Shader rg(int in, int out) { return new RadialGradient(C, CY, R, new int[]{in, in, out}, new float[]{0, .22f, 1}, Shader.TileMode.CLAMP); }

        final List<Integer> ranks = new ArrayList<>();                   // mặt vé: các mức % từ cao xuống thấp (tính 1 lần khi đổi ô, không tính mỗi khung hình)
        void set(List<JSONObject> list) {
            pz = list; ranks.clear();
            for (JSONObject x : list) if (!ranks.contains(x.optInt("pct"))) ranks.add(x.optInt("pct"));
            ranks.sort((x, y) -> y - x); invalidate();
        }

        @Override protected void onDraw(Canvas c) {
            float k = getWidth() / 200f; if (k <= 0) return;
            long t = SystemClock.uptimeMillis() - t0;
            c.save(); c.scale(k, k);
            int n = Math.max(1, pz.size()); float seg = 360f / n;
            // quầng sáng sân khấu
            p.setStyle(Paint.Style.FILL); p.setShader(lucky ? kglow : glow); c.drawCircle(C, CY, 112, p); p.setShader(null);
            // các ô (quay)
            c.save(); c.rotate(rot, C, CY);
            int lo = 0;
            for (int i = 0; i < pz.size(); i++) {
                JSONObject x = pz.get(i); int pct = x.optInt("pct"); boolean out = !x.isNull("left") && x.optInt("left") == 0;
                int kr = lucky ? (ranks.indexOf(pct) == ranks.size() - 1 && ranks.size() > 1 ? 3 : Math.min(2, ranks.indexOf(pct))) : -1;
                Shader f = mys ? (lucky ? (i % 2 == 1 ? km2 : km1) : (i % 2 == 1 ? m2 : m1)) : lucky ? (kr == 0 ? k1 : kr == 1 ? k2 : kr == 2 ? k3 : k4)
                        : out ? gone : pct >= 40 ? hi : pct >= 20 ? mid : (lo++ % 2 == 1 ? lo2 : lo1);
                p.setStyle(Paint.Style.FILL); p.setShader(f);
                c.drawArc(oval, -90 + (i - .5f) * seg, seg, true, p);
                p.setShader(null);
                if (!mys && i == win) { p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(2.2f); p.setColor(Color.argb((int) (170 + 85 * Math.abs(Math.sin(t / 330.0))), 255, 255, 255));
                    c.drawArc(oval, -90 + (i - .5f) * seg, seg, true, p); }
                c.save(); c.rotate(i * seg, C, CY);
                if (mys) { tp.setTextSize(19); tp.setColor(Color.argb((int) (150 + 80 * Math.abs(Math.sin(t / 500.0 + i))), 223, 233, 255)); c.drawText("?", C, CY - 54, tp); }
                else {
                    tp.setTextSize(n <= 8 ? 16 : n <= 10 ? 14.5f : 12.5f);
                    tp.setColor(lucky ? (kr == 0 ? Color.rgb(42, 28, 0) : Color.rgb(239, 255, 249)) : out ? Color.rgb(111, 125, 163) : pct >= 40 ? INK : TXT);
                    c.drawText(pct + "%", C, CY - 56, tp);
                    if (out) { tp.setTextSize(7.5f); c.drawText(Ui.L("HẾT", "GONE"), C, CY - 43, tp); }
                }
                c.restore();
            }
            p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(.8f); p.setColor(Color.argb(150, 230, 238, 252));
            for (int i = 0; i < pz.size(); i++) { double a = Math.toRadians(-90 + (i - .5f) * seg); c.drawLine(C, CY, C + R * (float) Math.cos(a), CY + R * (float) Math.sin(a), p); }
            p.setStyle(Paint.Style.FILL);
            for (int i = 0; i < pz.size(); i++) { double a = Math.toRadians(-90 + (i + .5f) * seg); p.setColor(PEARL); c.drawCircle(C + 80 * (float) Math.cos(a), CY + 80 * (float) Math.sin(a), 1.5f, p); }
            c.restore();
            // kính bóng + viền bạch kim + 24 bóng đèn
            p.setShader(gloss); c.drawCircle(C, CY, R, p); p.setShader(null);
            p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(12); p.setShader(rim); c.drawCircle(C, CY, 91.5f, p); p.setShader(null);
            p.setStrokeWidth(1.6f); p.setColor(INK); c.drawCircle(C, CY, 85.6f, p); p.setStrokeWidth(1); c.drawCircle(C, CY, 97.6f, p);
            p.setStyle(Paint.Style.FILL);
            for (int i = 0; i < 24; i++) {
                double a = Math.toRadians(i * 15 - 90); float x = C + 91.5f * (float) Math.cos(a), y = CY + 91.5f * (float) Math.sin(a);
                float on = spinning ? (((t / 150) + i) % 2 == 0 ? 1f : .12f) : (float) (.3 + .7 * (.5 + .5 * Math.cos((t / 2400.0) * 2 * Math.PI + (i % 2) * Math.PI)));
                p.setColor(Color.argb((int) (55 * on), 255, 231, 168)); c.drawCircle(x, y, 4.4f, p);         // quầng sáng (2 vòng mờ, không tạo shader mới)
                p.setColor(Color.argb((int) (95 * on), 255, 231, 168)); c.drawCircle(x, y, 3.2f, p);
                p.setColor(Color.argb((int) (60 + 195 * on), 255, 250, 240)); c.drawCircle(x, y, 2.1f, p);
            }
            // kim chỉ (bạch kim + đá sapphire)
            p.setShader(pinG); c.drawPath(pin, p); p.setShader(null);
            p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1.4f); p.setColor(INK); c.drawPath(pin, p); p.setStyle(Paint.Style.FILL);
            p.setShader(gem); c.drawCircle(C, 6.6f, 3.6f, p); p.setShader(null);
            p.setColor(Color.argb(220, 255, 255, 255)); c.drawCircle(C - 1.1f, 5.4f, 1f, p);
            // núm QUAY ở giữa
            if (hubOn) { float ph = (t % 1900) / 1900f; p.setColor(Color.argb((int) (150 * (1 - ph)), 143, 208, 255)); c.drawCircle(C, CY, 32.5f + 18 * ph, p); }
            p.setColor(Color.rgb(11, 23, 51)); c.drawCircle(C, CY, 32.5f, p);
            p.setColor(Color.rgb(142, 156, 182)); c.drawCircle(C, CY, 31f, p);
            p.setColor(Color.rgb(233, 239, 248)); c.drawCircle(C, CY, 29f, p);
            p.setShader(hub); c.drawCircle(C, CY, 25f, p); p.setShader(null);
            if (!hubOn) { p.setColor(Color.argb(120, 8, 17, 40)); c.drawCircle(C, CY, 25f, p); }
            tp.setTextSize(11); tp.setColor(Color.WHITE); tp.setShadowLayer(1.5f, 0, .8f, Color.argb(130, 0, 0, 0));
            c.drawText(Ui.L("QUAY", "SPIN"), C, CY + 4, tp); tp.clearShadowLayer();
            c.restore();
            if (alive && isShown()) postInvalidateOnAnimation();          // đèn viền nhấp nháy / chạy · ô trúng sáng · núm phát sáng
        }

        @Override protected void onMeasure(int ws, int hs) {
            int w = MeasureSpec.getSize(ws);
            setMeasuredDimension(w, Math.round(w * H / 200f));
        }

        @Override public boolean onTouchEvent(MotionEvent e) {
            float k = getWidth() / 200f; if (k <= 0) return false;
            float dx = e.getX() / k - C, dy = e.getY() / k - CY;
            boolean inHub = dx * dx + dy * dy <= 31 * 31;
            if (e.getAction() == MotionEvent.ACTION_DOWN) return inHub;
            if (e.getAction() == MotionEvent.ACTION_UP && inHub && hubOn && onHub != null) { performClick(); onHub.run(); }
            return true;
        }
        @Override public boolean performClick() { return super.performClick(); }

        /** Quay tới ô k (kim ở 12 giờ), lệch ngẫu nhiên trong ô cho tự nhiên. calm = máy tắt hiệu ứng → quay ngắn. */
        void spinTo(int k, boolean calm, Runnable done) {
            int n = Math.max(1, pz.size()); float seg = 360f / n;
            float want = (((-k * seg + (float) ((Math.random() - .5) * seg * .6)) % 360) + 360) % 360, cur = ((rot % 360) + 360) % 360;
            final float from = rot, to = rot + 360 * (calm ? 2 : 8) + ((want - cur + 360) % 360);
            ValueAnimator va = ValueAnimator.ofFloat(from, to);
            va.setDuration(calm ? 900 : 5600);
            va.setInterpolator(new PathInterpolator(.12f, .67f, .06f, 1f));
            va.addUpdateListener(an -> { rot = (float) an.getAnimatedValue(); invalidate(); });
            va.addListener(new AnimatorListenerAdapter() { @Override public void onAnimationEnd(Animator an) { spinning = false; rot = to; invalidate(); if (done != null) done.run(); } });
            spinning = true; va.start();
        }
    }

    // ================================================================ màn mở quà: hộp rơi · rung · nổ · pháo giấy + bong bóng → thẻ mã
    interface Next { void go(String what); }

    static final class Reveal {
        final Dialog d; final FrameLayout root; final FxView fx; final LinearLayout card;
        String result = "done";
        Reveal(MainActivity a, JSONObject r, int left, long buyPrice, long luckPrice, Next next) {
            final boolean big = r.optInt("pct") >= 40, calm = calm(a);
            d = new Dialog(a);
            d.requestWindowFeature(Window.FEATURE_NO_TITLE);
            root = new FrameLayout(a);
            fx = new FxView(a, big, calm);
            root.addView(fx, new FrameLayout.LayoutParams(-1, -1));
            card = Ui.col(a, 12);
            card.setGravity(Gravity.CENTER_HORIZONTAL);
            card.setPadding(Ui.dp(20), Ui.dp(22), Ui.dp(20), Ui.dp(18));
            GradientDrawable cb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(21, 42, 92), Color.rgb(11, 23, 51)});
            cb.setCornerRadius(Ui.dp(22)); cb.setStroke(Ui.dp(big ? 1.5f : 1), big ? Color.argb(200, 243, 247, 254) : Color.argb(80, 223, 234, 252));
            card.setBackground(cb);
            TextView t1 = Ui.text(a, (big ? "🎉 " : "🎁 ") + Ui.L("Chúc mừng! Bạn nhận được", "Congratulations! You got"), 15, Ui.SKY, true); t1.setGravity(Gravity.CENTER);
            TextView v = Ui.text(a, "−" + r.optInt("pct") + "%", 54, PEARL, true); v.setGravity(Gravity.CENTER);
            TextView v2 = Ui.text(a, Ui.L("mã giảm giá", "discount code"), 15, SUB, true); v2.setGravity(Gravity.CENTER);
            final String code = r.optString("code");
            LinearLayout cr = Ui.row(a, 8); cr.setGravity(Gravity.CENTER);
            TextView ct = Ui.text(a, code, 17, Color.WHITE, true); ct.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
            ct.setPadding(Ui.dp(12), Ui.dp(7), Ui.dp(12), Ui.dp(7)); ct.setBackground(Ui.round(Color.argb(150, 6, 13, 28), 10, Color.argb(90, 223, 234, 252)));
            ct.setTextIsSelectable(true);
            Button cp = Ui.button(a, Ui.L("Chép mã", "Copy code"), Ui.GHOST);
            cp.setOnClickListener(x -> copy(a, code));
            cr.addView(ct, Ui.wrap()); cr.addView(cp, Ui.wrap());
            TextView h = Ui.text(a, Ui.L("Dùng 1 lần · hạn đến " + MainActivity.fdate(MainActivity.parseTime(r.optString("expires_at"))) + " · " + (r.optBoolean("share") ? "giữ dùng sau hoặc tặng bạn bè dùng đều được" : "chỉ tài khoản của bạn dùng được") + ". Nhập ở ô \"🏷️ Mã giảm giá\" khi thanh toán.",
                    "One use · valid until " + MainActivity.fdate(MainActivity.parseTime(r.optString("expires_at"))) + " · " + (r.optBoolean("share") ? "keep it or give it to a friend" : "only your account can use it") + ". Enter it in the \"🏷️ Discount code\" box at checkout."), 12.5f, SUB, false);
            h.setGravity(Gravity.CENTER);
            if (r.optBoolean("lucky")) {
                TextView lt = Ui.text(a, "🍀 " + Ui.L("Vé may mắn", "Lucky ticket"), 13, Color.rgb(3, 38, 27), true);
                lt.setPadding(Ui.dp(12), Ui.dp(4), Ui.dp(12), Ui.dp(5));
                GradientDrawable lg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(122, 240, 200), Color.rgb(34, 195, 154)}); lg.setCornerRadius(Ui.dp(99));
                lt.setBackground(lg); card.addView(lt, Ui.wrap());
            }
            card.addView(t1, Ui.fill()); card.addView(v, Ui.fill()); card.addView(v2, Ui.fill()); card.addView(cr, Ui.fill()); card.addView(h, Ui.fill());
            if (r.optLong("paid") > 0) { TextView pd = Ui.text(a, Ui.L("Đã trừ " + Ui.vnd(r.optLong("paid")) + " · số dư còn " + Ui.vnd(r.optDouble("balance")), Ui.vnd(r.optLong("paid")) + " paid · balance " + Ui.vnd(r.optDouble("balance"))), 12.5f, SUB, false);
                pd.setGravity(Gravity.CENTER); card.addView(pd, Ui.fill()); }
            if (left > 0) { Button g = Ui.button(a, "🎡 " + Ui.L("Quay tiếp · còn " + left + " lượt", "Spin again · " + left + " left"), Ui.PRIMARY); g.setOnClickListener(x -> { result = "again"; d.dismiss(); }); card.addView(g, Ui.fill()); }
            else if (buyPrice > 0) { Button g = Ui.button(a, "➕ " + Ui.L("Quay thêm · " + Ui.vnd(buyPrice), "Extra spin · " + Ui.vnd(buyPrice)), Ui.PRIMARY);
                GradientDrawable gb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.WHITE, PEARL2}); gb.setCornerRadius(Ui.dp(14)); g.setBackground(gb); g.setTextColor(INK);
                g.setOnClickListener(x -> { result = "buy"; d.dismiss(); }); card.addView(g, Ui.fill()); }
            else if (luckPrice > 0) { Button g = Ui.button(a, "🍀 " + Ui.L("Dùng thêm vé · " + Ui.vnd(luckPrice), "Another ticket · " + Ui.vnd(luckPrice)), Ui.PRIMARY);
                GradientDrawable gb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(92, 240, 194), Color.rgb(20, 169, 125)}); gb.setCornerRadius(Ui.dp(14)); g.setBackground(gb); g.setTextColor(Color.rgb(3, 38, 27));
                g.setOnClickListener(x -> { result = "lucky"; d.dismiss(); }); card.addView(g, Ui.fill()); }
            Button done = Ui.button(a, Ui.L("Xong", "Done"), left > 0 || buyPrice > 0 || luckPrice > 0 ? Ui.GHOST : Ui.PRIMARY);
            done.setOnClickListener(x -> d.dismiss());
            card.addView(done, Ui.fill());
            int sw = a.getResources().getDisplayMetrics().widthPixels;
            FrameLayout.LayoutParams cl = new FrameLayout.LayoutParams(Math.min(sw - Ui.dp(40), Ui.dp(400)), -2, Gravity.CENTER);
            root.addView(card, cl);
            card.setAlpha(0f); card.setScaleX(.3f); card.setScaleY(.3f); card.setTranslationY(Ui.dp(40));
            d.setContentView(root);
            Ui.insets(root, true, true);
            d.setOnDismissListener(x -> { fx.alive = false; next.go(result); });          // đóng kiểu nào cũng chỉ báo đúng 1 lần
            Window w = d.getWindow();
            if (w != null) { w.setBackgroundDrawable(new ColorDrawable(Color.rgb(3, 5, 12))); w.setLayout(-1, -1); w.setWindowAnimations(android.R.style.Animation_Dialog); }
            final long burstAt = calm ? 0 : 1250;
            card.postDelayed(() -> {
                fx.burst();
                card.animate().alpha(1f).scaleX(1f).scaleY(1f).translationY(0).setStartDelay(calm ? 0 : 160).setDuration(calm ? 1 : 620).setInterpolator(new OvershootInterpolator(1.6f)).start();
            }, burstAt);
        }
        void show() { d.show(); }
    }

    /** Nền sâu xanh + hộp quà (rơi, rung, nổ) + chớp sáng + tia sáng xoay + pháo giấy rơi / bong bóng bay lên. Tất cả vẽ trên 1 Canvas. */
    static final class FxView extends View {
        final boolean big, calm; boolean alive = true; long t0 = SystemClock.uptimeMillis(), tb = -1;
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        final List<float[]> parts = new ArrayList<>();         // x, y, vx, vy, rot, vr, w, h, màu, bóng(1/0)
        final int[] cols;
        final Random rnd = new Random();
        final Path ray = new Path();
        Shader back;
        @Override protected void onSizeChanged(int w, int h, int ow, int oh) {
            back = new RadialGradient(w / 2f, h / 2f * .92f, Math.max(1, Math.max(w, h) * .62f), new int[]{Color.rgb(22, 58, 122), Color.rgb(6, 13, 29), Color.rgb(3, 5, 12)}, new float[]{0, .62f, 1}, Shader.TileMode.CLAMP);
        }
        FxView(Context c, boolean big, boolean calm) {
            super(c); this.big = big; this.calm = calm;
            cols = big ? new int[]{Color.WHITE, PEARL, PEARL2, Color.rgb(152, 201, 246), Color.rgb(90, 140, 226), Color.rgb(255, 231, 168)}
                       : new int[]{Color.rgb(152, 201, 246), Color.rgb(90, 140, 226), PEARL, PEARL2, Color.rgb(60, 224, 176)};
        }
        void burst() {
            tb = SystemClock.uptimeMillis();
            if (calm) { invalidate(); return; }
            float d = getResources().getDisplayMetrics().density;
            for (int i = 0, n = big ? 200 : 140; i < n; i++) {
                double a = rnd.nextDouble() * Math.PI * 2, sp = (3 + rnd.nextDouble() * (big ? 12 : 9)) * d / 1.6;
                parts.add(new float[]{getWidth() / 2f, getHeight() / 2f, (float) (Math.cos(a) * sp), (float) (Math.sin(a) * sp - (3 + rnd.nextDouble() * 3) * d / 1.6),
                        (float) (rnd.nextDouble() * 6), (float) ((rnd.nextDouble() - .5) * .4), (5 + rnd.nextFloat() * 6) * d / 1.6f, (9 + rnd.nextFloat() * 8) * d / 1.6f, cols[i % cols.length], rnd.nextDouble() < .3 ? 1 : 0});
            }
            invalidate();
        }
        @Override protected void onDraw(Canvas c) {
            float W = getWidth(), Hh = getHeight(), cx = W / 2f, cy = Hh / 2f, dd = getResources().getDisplayMetrics().density;
            long now = SystemClock.uptimeMillis(), t = now - t0, b = tb < 0 ? -1 : now - tb;
            if (back != null) { p.setShader(back); c.drawRect(0, 0, W, Hh, p); p.setShader(null); } else c.drawColor(Color.rgb(3, 5, 12));
            if (b >= 0) {                                       // tia sáng xoay
                float s = Math.min(1f, b / 900f), rr = 280 * dd * (.2f + .8f * s);
                c.save(); c.rotate((now % 18000) / 18000f * 360f, cx, cy);
                p.setShader(new RadialGradient(cx, cy, Math.max(1, rr), new int[]{Color.argb((int) (90 * s), 143, 208, 255), Color.argb(0, 152, 201, 246)}, new float[]{.16f, 1}, Shader.TileMode.CLAMP));
                for (int i = 0; i < 18; i++) { ray.reset(); double a0 = Math.toRadians(i * 20), a1 = Math.toRadians(i * 20 + 8);
                    ray.moveTo(cx, cy); ray.lineTo(cx + rr * (float) Math.cos(a0), cy + rr * (float) Math.sin(a0)); ray.lineTo(cx + rr * (float) Math.cos(a1), cy + rr * (float) Math.sin(a1)); ray.close(); c.drawPath(ray, p); }
                p.setShader(null); c.restore();
            }
            if (!calm) drawGift(c, cx, cy, t, b, dd);
            if (b >= 0 && b < 600 && !calm) {                   // chớp sáng
                float fl = b < 96 ? b / 96f : 1f - (b - 96) / 504f;
                p.setShader(new RadialGradient(cx, cy, Math.max(W, Hh) * .58f, new int[]{Color.argb((int) (230 * fl), 255, 255, 255), Color.argb((int) (70 * fl), 143, 208, 255), Color.argb(0, 0, 0, 0)}, new float[]{0, .45f, 1}, Shader.TileMode.CLAMP));
                c.drawRect(0, 0, W, Hh, p); p.setShader(null);
            }
            if (b >= 0 && b < 2800 && !parts.isEmpty()) {       // pháo giấy rơi xuống · bong bóng nước bay lên · ~3 giây tự tắt
                float ga = Math.max(0f, 1f - Math.max(0f, b / 1000f - 1.7f) / 1.1f);
                for (float[] q : parts) {
                    q[2] *= .982f; q[3] = q[9] > 0 ? q[3] * .965f - .06f * dd / 1.6f : q[3] * .985f + .24f * dd / 1.6f; q[0] += q[2]; q[1] += q[3]; q[4] += q[5];
                    int col = (int) q[8];
                    if (q[9] > 0) { p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1.6f * dd / 1.6f); p.setColor(col); p.setAlpha((int) (255 * ga)); c.drawCircle(q[0], q[1], q[6] * .6f, p); p.setStyle(Paint.Style.FILL); }
                    else { float f = Math.abs((float) Math.cos(q[4] * 1.7)); c.save(); c.translate(q[0], q[1]); c.rotate((float) Math.toDegrees(q[4]));
                        p.setColor(col); p.setAlpha((int) (255 * ga)); c.drawRect(-q[6] / 2, -q[7] * f / 2, q[6] / 2, q[7] * f / 2 + 1, p); c.restore(); }
                }
                p.setAlpha(255);
            }
            if (alive) postInvalidateOnAnimation();
        }
        void drawGift(Canvas c, float cx, float cy, long t, long b, float dd) {
            float s = dd * 1.0f, bw = 126 * s, bh = 92 * s, lw = 150 * s, lh = 34 * s;
            float drop = Math.min(1f, t / 420f), ease = 1f - (float) Math.pow(1 - drop, 3);
            float y0 = cy + 40 * s - 70 * s * (1 - ease), sc = .55f + .45f * ease;
            float ang = 0;
            if (b < 0 && t > 500 && t < 1280) ang = (float) (8 * Math.sin((t - 500) / 260.0 * 2 * Math.PI));
            float lidDx = 0, lidDy = 0, lidRot = 0, lidA = 1, bodyDy = 0, bodySc = 1, bodyA = 1;
            if (b >= 0) { float u = Math.min(1f, b / 750f), e2 = 1f - (float) Math.pow(1 - u, 3); lidDx = -34 * s * e2; lidDy = -200 * s * e2; lidRot = -40 * e2; lidA = 1 - u;
                float v = Math.max(0f, Math.min(1f, (b - 120) / 500f)); bodyDy = 46 * s * v * v; bodySc = 1 - .3f * v; bodyA = 1 - v; }
            if (bodyA <= 0 && lidA <= 0) return;
            int a0 = (int) (255 * Math.min(1f, drop * 1.5f));
            int top = big ? Color.WHITE : Color.rgb(105, 152, 229), bot = big ? PEARL2 : Color.rgb(48, 110, 218), rib = big ? Color.rgb(90, 140, 226) : PEARL;
            c.save(); c.translate(cx, y0); c.scale(sc, sc); c.rotate(ang);
            if (bodyA > 0) {                                    // thân hộp + ruy băng dọc
                c.save(); c.translate(0, bodyDy); c.scale(bodySc, bodySc);
                p.setShader(new LinearGradient(0, -bh / 2, 0, bh / 2, top, bot, Shader.TileMode.CLAMP)); p.setAlpha((int) (a0 * bodyA));
                c.drawRoundRect(new RectF(-bw / 2, -bh / 2, bw / 2, bh / 2), 12 * s, 12 * s, p); p.setShader(null);
                p.setColor(rib); p.setAlpha((int) (a0 * bodyA)); c.drawRect(-11 * s, -bh / 2, 11 * s, bh / 2, p);
                c.restore();
            }
            if (lidA > 0) {                                     // nắp + nơ
                c.save(); c.translate(lidDx, -bh / 2 - lh / 2 + 6 * s + lidDy); c.rotate(lidRot);
                p.setShader(new LinearGradient(0, -lh / 2, 0, lh / 2, big ? Color.WHITE : Color.rgb(142, 178, 235), big ? Color.rgb(221, 232, 250) : Color.rgb(90, 140, 226), Shader.TileMode.CLAMP)); p.setAlpha((int) (a0 * lidA));
                c.drawRoundRect(new RectF(-lw / 2, -lh / 2, lw / 2, lh / 2), 10 * s, 10 * s, p); p.setShader(null);
                p.setColor(rib); p.setAlpha((int) (a0 * lidA)); c.drawRect(-11 * s, -lh / 2, 11 * s, lh / 2, p);
                p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(7 * s); p.setColor(big ? Color.rgb(90, 140, 226) : PEARL); p.setAlpha((int) (a0 * lidA));
                c.save(); c.rotate(-24, -18 * s, -lh / 2 - 10 * s); c.drawOval(new RectF(-34 * s, -lh / 2 - 22 * s, -4 * s, -lh / 2 + 1 * s), p); c.restore();
                c.save(); c.rotate(24, 18 * s, -lh / 2 - 10 * s); c.drawOval(new RectF(4 * s, -lh / 2 - 22 * s, 34 * s, -lh / 2 + 1 * s), p); c.restore();
                p.setStyle(Paint.Style.FILL);
                c.restore();
            }
            p.setAlpha(255);
            c.restore();
        }
    }
}
