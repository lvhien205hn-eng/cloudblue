package shop.blueroblox.app;

import android.app.Dialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** 🎁 ƯU ĐÃI & 🎬 KIẾM TIỀN (SQL v35) — mọi con số / câu chữ do MÁY CHỦ trả về, app chỉ hiển thị:
 *    promo_public() → pub {day_limit, topup{levels[{min,pct}],days,max,vi,en}, trial{hours,need,ram,cpu}, wheel, creator{rate,per,video_max,
 *                          month_max,day_submit,platforms,blue_min}, blue, ticker[{k,vi,en}]}
 *    promo_my()     → my  {day_limit, day_used, topup_got, codes[{code,pct,amount,expires_at,scopes,usable,used,share,src}], trial{on,hours,need,ok,used}}
 *    creator_my / creator_submit / creator_report → video Kiếm tiền của tôi.
 *  Máy chủ chưa chạy SQL v35 → pub = null → app ẩn hết, chạy như cũ.
 *  Bản CH Play (Api.PLAY): KHÔNG có dòng chữ chạy / ưu đãi nạp / Kiếm tiền (nạp qua Google Play không tính ưu đãi nạp, không dẫn ra chương
 *  trình ngoài). Dùng thử theo giờ và "Mã của tôi" thì bản nào cũng có (máy chủ tự kiểm điều kiện). */
final class Offers {
    static volatile JSONObject pub = null, my = null;
    static volatile long at = 0;

    interface Done { void run(); }
    interface Amt { void set(long v); }

    static boolean on() { return Api.SHOP && !Api.PLAY; }
    static String t(JSONObject o) {
        if (o == null) return "";
        String v = o.optString(Ui.vi() ? "vi" : "en", "");
        return v.isEmpty() || "null".equals(v) ? o.optString("vi", "") : v;
    }
    private static JSONObject sec(String k) { JSONObject p = pub; return p == null || p.isNull(k) ? null : p.optJSONObject(k); }
    static JSONObject topup() { JSONObject o = on() ? sec("topup") : null; JSONArray l = o == null ? null : o.optJSONArray("levels"); return l != null && l.length() > 0 ? o : null; }
    static JSONObject creator() { return on() ? sec("creator") : null; }
    static int dayLimit() { JSONObject p = pub; return p == null ? 0 : Math.max(0, p.optInt("day_limit", 0)); }
    static String n(long v) { return Blue.n(v); }

    /** Tải lại ở nền → done() trên luồng giao diện. Lỗi / chưa có SQL v35 → pub = null (app như cũ). */
    static void load(Done done) {
        Api.bg(() -> {
            JSONObject p = null, m = null;
            try { Object r = Api.rpc("promo_public", new JSONObject()); if (r instanceof JSONObject) p = (JSONObject) r; } catch (Exception ignored) { }
            if (p != null) try { Object r = Api.rpc("promo_my", new JSONObject()); if (r instanceof JSONObject) m = (JSONObject) r; } catch (Exception ignored) { }
            return new JSONObject[]{p, m};
        }, r -> { pub = r[0]; my = r[1]; at = System.currentTimeMillis(); if (done != null) done.run(); },
           x -> { if (done != null) done.run(); });
    }

    // ================================================================ 📱 dùng thử theo GIỜ (bảng giá: free_hours · free_need_topup)
    static int hours(JSONObject price) { return price == null ? 0 : Math.max(0, price.optInt("free_hours", 0)); }
    static long need(JSONObject price) { return price == null || price.isNull("free_need_topup") ? 0 : Math.max(0, price.optLong("free_need_topup", 0)); }
    static String dur(JSONObject price) {
        int h = hours(price), d = price == null ? 1 : price.optInt("free_days", 1);
        return h > 0 ? Ui.L(h + " giờ", h + " hour" + (h > 1 ? "s" : "")) : Ui.L(d + " ngày", d + " day(s)");
    }
    static String freeName(JSONObject price) { return hours(price) > 0 ? Ui.L("🎁 Máy dùng thử", "🎁 Trial phone") : Ui.L("🎁 Máy miễn phí", "🎁 Free phone"); }
    static String freeBtn(JSONObject price) { return hours(price) > 0 ? Ui.L("🎁 Nhận máy dùng thử", "🎁 Get trial phone") : Ui.L("🎁 Nhận máy miễn phí", "🎁 Get free phone"); }
    static String freeTitle(JSONObject price) { return Ui.L("🎁 Dùng thử MIỄN PHÍ " + dur(price), "🎁 FREE trial for " + dur(price)); }
    static String freeNote(JSONObject price) {
        long nd = need(price); String h = dur(price);
        return Ui.L("Tối đa " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " nhân · mỗi tài khoản 1 máy"
                        + (nd > 0 ? " · dành cho tài khoản đã nạp 1 lần từ " + Ui.vnd(nd) : "") + ". Hết " + h + " (tính từ lúc máy chạy) máy và dữ liệu tự xoá, không gia hạn được — muốn dùng tiếp thì thuê máy. Bấm lần nữa để tắt nếu muốn thuê trả phí.",
                "Up to " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " cores · 1 per account"
                        + (nd > 0 ? " · for accounts that topped up " + Ui.vnd(nd) + "+ at once" : "") + ". After " + h + " (from when it starts) the phone and its data are deleted; it can't be renewed. Tap again to rent a paid phone instead.");
    }
    /** "" = nhận được · không thì lý do. Chưa có SQL v35 / chưa tải xong → "" (máy chủ tự kiểm khi đặt). */
    static String trialErr(JSONObject price, boolean admin) {
        JSONObject m = my, tr = m == null ? null : m.optJSONObject("trial");
        if (admin || tr == null) return "";
        if (tr.optBoolean("used")) return Ui.L("Mỗi tài khoản chỉ được dùng thử 1 máy miễn phí — bạn đã nhận rồi.", "Only 1 free trial phone per account — already used.");
        long nd = need(price);
        if (!tr.optBoolean("ok") && nd > 0) return Ui.L("Dùng thử miễn phí dành cho tài khoản đã nạp 1 lần từ " + Ui.vnd(nd) + ".", "Free trials are for accounts that topped up " + Ui.vnd(nd) + "+ at once.");
        return "";
    }
    static boolean trialNeedsTopup(JSONObject price, boolean admin) {
        JSONObject m = my, tr = m == null ? null : m.optJSONObject("trial");
        return !admin && tr != null && !tr.optBoolean("used") && !tr.optBoolean("ok") && need(price) > 0;
    }
    /** Dòng ghi trên thẻ máy dùng thử. */
    static String phoneNote(JSONObject p) {
        int h = p.optInt("trial_hours", 0);
        return h <= 0 ? null : Ui.L("🎁 Máy dùng thử " + h + " giờ — hết giờ máy và dữ liệu tự xoá, không gia hạn được.", "🎁 " + h + "-hour trial phone — deleted when time is up; can't be renewed.");
    }

    // ================================================================ 🎫 mã của tôi (chọn nhanh dưới ô Mã giảm giá)
    static List<JSONObject> codes(String scope) {
        List<JSONObject> out = new ArrayList<>();
        JSONObject m = my; JSONArray cs = m == null ? null : m.optJSONArray("codes");
        for (int i = 0; cs != null && i < cs.length() && out.size() < 6; i++) {
            JSONObject c = cs.optJSONObject(i);
            if (c == null || !c.optBoolean("usable")) continue;
            JSONArray sc = c.optJSONArray("scopes"); boolean hit = scope == null;
            for (int k = 0; !hit && sc != null && k < sc.length(); k++) if (scope.equals(sc.optString(k))) hit = true;
            if (hit) out.add(c);
        }
        return out;
    }
    static String codeLabel(JSONObject c) { return c.optString("code") + "  −" + (c.optInt("pct") > 0 ? c.optInt("pct") + "%" : Ui.vnd(c.optDouble("amount"))); }
    static String srcName(String s) {
        return "wheel".equals(s) ? Ui.L("🎡 Vòng quay", "🎡 Lucky wheel") : "topup".equals(s) ? Ui.L("💰 Ưu đãi nạp", "💰 Top-up bonus") : Ui.L("🎁 Quà tặng", "🎁 Gift");
    }
    static void copy(Context c, String code) {
        try { ((ClipboardManager) c.getSystemService(Context.CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("code", code)); } catch (Exception ignored) { }
        Ui.toast(c, Ui.L("Đã chép mã ", "Copied ") + code);
    }

    // ================================================================ 📣 dòng chữ chạy đầu trang
    static TextView ticker(MainActivity a) {
        TextView t = Ui.text(a, "", 13, Ui.LIGHT ? Color.rgb(122, 72, 0) : Color.rgb(255, 226, 150), true);
        t.setSingleLine(true);
        t.setEllipsize(TextUtils.TruncateAt.MARQUEE);
        t.setMarqueeRepeatLimit(-1);
        t.setHorizontallyScrolling(true);
        t.setFocusable(false);
        t.setPadding(Ui.dp(14), Ui.dp(7), Ui.dp(14), Ui.dp(7));
        t.setBackground(Ui.round(Ui.LIGHT ? Color.rgb(255, 244, 214) : Color.rgb(46, 34, 6), 0, 0));
        t.setContentDescription(Ui.L("Ưu đãi đang có — bấm để xem", "Current offers — tap to view"));
        t.setOnClickListener(v -> sheet(a));
        t.setVisibility(View.GONE);
        return t;
    }
    static void fillTicker(TextView t) {
        if (t == null) return;
        JSONObject p = on() ? pub : null; JSONArray tk = p == null ? null : p.optJSONArray("ticker");
        StringBuilder one = new StringBuilder();
        for (int i = 0; tk != null && i < tk.length(); i++) {
            JSONObject x = tk.optJSONObject(i); String s = t(x);
            if (!s.isEmpty()) one.append(one.length() > 0 ? "      •      " : "").append(s);
        }
        if (one.length() == 0) { t.setVisibility(View.GONE); return; }
        StringBuilder all = new StringBuilder(one);
        while (all.length() < 240) all.append("      •      ").append(one);      // đủ dài để chữ luôn chạy (màn ngang / máy tính bảng)
        String s = all.toString();
        if (!s.contentEquals(t.getText())) t.setText(s);
        t.setVisibility(View.VISIBLE);
        t.setSelected(true);                                                     // marquee chỉ chạy khi view "được chọn"
    }

    // ================================================================ 2 ô ở trang "Máy của tôi": 🎬 Kiếm tiền · 🎁 Ưu đãi
    private static LinearLayout tile(MainActivity a, String icon, String title, String sub, int c1, int c2, View.OnClickListener on) {
        LinearLayout c = Ui.row(a, 10);
        c.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{c1, c2});
        bg.setCornerRadius(Ui.dp(18));
        bg.setStroke(Ui.dp(1), Color.argb(90, 220, 232, 255));
        c.setBackground(bg);
        TextView ic = Ui.text(a, icon, 22, Color.WHITE, false);
        ic.setGravity(Gravity.CENTER);
        ic.setBackground(Ui.round(Color.argb(38, 255, 255, 255), 14, Color.argb(80, 220, 232, 255)));
        c.addView(ic, new LinearLayout.LayoutParams(Ui.dp(42), Ui.dp(42)));
        LinearLayout tx = Ui.col(a, 1);
        TextView t1 = Ui.text(a, title, 14.5f, Color.WHITE, true), t2 = Ui.text(a, sub, 12, Color.rgb(214, 226, 250), false);
        t1.setMaxLines(1); t1.setEllipsize(TextUtils.TruncateAt.END);
        t2.setMaxLines(2); t2.setEllipsize(TextUtils.TruncateAt.END);
        tx.addView(t1, Ui.fill());
        tx.addView(t2, Ui.fill());
        c.addView(tx, Ui.weight(1));
        TextView go = Ui.text(a, "›", 20, Color.WHITE, true);
        c.addView(go, Ui.wrap());
        c.setClickable(true);
        c.setFocusable(true);
        c.setContentDescription(title + " · " + sub);
        c.setOnClickListener(on);
        return c;
    }
    /** Trả null nếu không có gì để hiện (chưa có SQL v35 / bản CH Play / admin tắt hết). */
    static View strip(MainActivity a) {
        if (!on() || pub == null) return null;
        LinearLayout box = Ui.col(a, 10);
        JSONObject cr = creator(), tc = topup(), tr = sec("trial");
        if (cr != null)
            box.addView(tile(a, "🎬", Ui.L("Kiếm tiền", "Earn") + " · " + n(cr.optLong("per")) + Ui.L(" view = ", " views = ") + n(cr.optLong("rate")) + " 💎",
                    Ui.L("Làm video về CloudBlue trên TikTok, YouTube… view càng tăng 💎 càng nhiều.", "Make videos about CloudBlue — more views, more 💎."),
                    Color.rgb(12, 96, 86), Color.rgb(8, 44, 62), v -> creatorSheet(a)), Ui.fill());
        String sub = "";
        if (tc != null) { JSONArray l = tc.optJSONArray("levels"); JSONObject lo = l.optJSONObject(0), hi = l.optJSONObject(l.length() - 1);
            if (lo != null && hi != null) sub = Ui.L("Nạp từ " + Ui.vnd(lo.optDouble("min")) + " nhận mã đến " + hi.optInt("pct") + "%", "Top up " + Ui.vnd(lo.optDouble("min")) + "+ for codes up to " + hi.optInt("pct") + "%"); }
        if (tr != null && a.freeLive()) sub += (sub.isEmpty() ? "" : " · ") + (need(a.price) > 0 ? Ui.L("nạp " + Ui.vnd(need(a.price)) + " dùng thử " + dur(a.price), "top up " + Ui.vnd(need(a.price)) + " for a " + dur(a.price) + " trial")
                : Ui.L("dùng thử " + dur(a.price) + " miễn phí", "free " + dur(a.price) + " trial"));
        int mine = codes(null).size();
        if (mine > 0) sub += (sub.isEmpty() ? "" : " · ") + Ui.L("bạn có " + mine + " mã", "you have " + mine + " code(s)");
        if (!sub.isEmpty())
            box.addView(tile(a, "🎁", Ui.L("Ưu đãi cloud phone", "Cloud phone offers"), sub, Color.rgb(122, 78, 8), Color.rgb(52, 30, 8), v -> sheet(a)), Ui.fill());
        return box.getChildCount() == 0 ? null : box;
    }

    // ================================================================ 🎁 hộp Ưu đãi
    private static LinearLayout block(MainActivity a, String title) {
        LinearLayout c = Ui.col(a, 8);
        c.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(12));
        c.setBackground(Ui.round(Ui.SUNK, 16, Ui.LINE2));
        c.addView(Ui.text(a, title, 15, Ui.FG, true), Ui.fill());
        return c;
    }
    private static View codeRow(MainActivity a, JSONObject c) {
        LinearLayout r = Ui.row(a, 10);
        boolean ok = c.optBoolean("usable");
        TextView p = Ui.text(a, c.optInt("pct") > 0 ? c.optInt("pct") + "%" : Ui.vnd(c.optDouble("amount")), 15, ok ? Ui.OK : Ui.MUTED, true);
        r.addView(p, new LinearLayout.LayoutParams(Ui.dp(52), -2));
        long exp = MainActivity.parseTime(c.optString("expires_at"));
        String st = c.optBoolean("used") ? Ui.L("Đã dùng", "Used") : ok ? Ui.L("Dùng được đến ", "Valid until ") + MainActivity.fdate(exp)
                : exp > 0 && exp <= System.currentTimeMillis() ? Ui.L("Hết hạn", "Expired") : Ui.L("Đã tắt", "Disabled");
        LinearLayout tx = Ui.col(a, 0);
        tx.addView(Ui.text(a, c.optString("code"), 14.5f, ok ? Ui.FG : Ui.MUTED, true));
        tx.addView(Ui.text(a, srcName(c.optString("src")) + " · " + st + (ok && c.optBoolean("share") ? " · " + Ui.L("🤝 tặng bạn bè được", "🤝 shareable") : ""), 12, Ui.MUTED, false));
        r.addView(tx, Ui.weight(1));
        if (ok) {
            TextView cp = Ui.pill(a, Ui.L("Chép", "Copy"), Ui.SKY);
            cp.setOnClickListener(v -> copy(a, c.optString("code")));
            r.addView(cp, Ui.wrap());
        }
        r.setAlpha(ok ? 1f : .6f);
        return r;
    }
    static void sheet(MainActivity a) {
        final Dialog[] d = new Dialog[1];
        LinearLayout c = Ui.col(a, 12);
        Runnable[] draw = new Runnable[1];
        draw[0] = () -> {
            c.removeAllViews();
            JSONObject p = pub, m = my;
            if (p == null) { c.addView(Ui.muted(a, Ui.L("Hiện chưa có ưu đãi nào.", "No offers right now.")), Ui.fill()); return; }
            JSONArray cs = m == null ? null : m.optJSONArray("codes");
            LinearLayout mine = null;
            if (m != null) {
                mine = block(a, "🎫 " + Ui.L("Mã của tôi", "My codes"));
                if (cs == null || cs.length() == 0) mine.addView(Ui.muted(a, Ui.L("Chưa có mã nào. Mã từ ưu đãi nạp, vòng quay, quà tặng sẽ nằm ở đây.", "No codes yet. Codes from top-up bonuses, the wheel and gifts show up here.")), Ui.fill());
                for (int i = 0; cs != null && i < cs.length() && i < 12; i++) { JSONObject x = cs.optJSONObject(i); if (x != null) mine.addView(codeRow(a, x), Ui.fill()); }
                if (cs != null && cs.length() > 0) mine.addView(Ui.muted(a, Ui.L("Chỉ dùng cho cloud phone: nhập ở ô “🏷️ Mã giảm giá” khi thuê / gia hạn / nâng cấp máy — hoặc bấm chọn mã ngay dưới ô đó.",
                        "Cloud phones only: enter it in the “🏷️ Discount code” box when renting / renewing / upgrading — or tap a code under that box.")), Ui.fill());
            }
            boolean mineTop = !codes(null).isEmpty();
            if (mine != null && mineTop) c.addView(mine, Ui.fill());
            JSONObject tc = topup();
            if (tc != null) {
                LinearLayout b = block(a, "💰 " + Ui.L("Ưu đãi khi nạp", "Top-up bonus"));
                JSONArray l = tc.optJSONArray("levels");
                for (int i = 0; i < l.length(); i++) { JSONObject x = l.optJSONObject(i); if (x == null) continue;
                    b.addView(Ui.text(a, Ui.L("Nạp 1 lần từ " + Ui.vnd(x.optDouble("min")) + "  →  mã giảm " + x.optInt("pct") + "%", "Top up " + Ui.vnd(x.optDouble("min")) + "+ once  →  " + x.optInt("pct") + "% off"), 14, Ui.OK, true), Ui.fill()); }
                b.addView(Ui.muted(a, Ui.L("Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp đó), dùng 1 lần, hạn " + tc.optInt("days", 7) + " ngày" + (tc.optLong("max") > 0 ? ", giảm tối đa " + Ui.vnd(tc.optLong("max")) : "") + ". Chỉ dùng cho cloud phone: thuê, gia hạn, nâng cấp máy.",
                        "One code per account (the highest level of that top-up), single use, valid " + tc.optInt("days", 7) + " days" + (tc.optLong("max") > 0 ? ", up to " + Ui.vnd(tc.optLong("max")) + " off" : "") + ". Cloud phones only: rent, renew, upgrade.")), Ui.fill());
                Button tb = Ui.button(a, "💳 " + Ui.L("Nạp tiền", "Top up"), Ui.PRIMARY);
                tb.setOnClickListener(v -> { d[0].dismiss(); a.openTopup(); });
                b.addView(tb, Ui.fill());
                c.addView(b, Ui.fill());
            }
            if (a.freeLive()) {
                LinearLayout b = block(a, "📱 " + Ui.L("Dùng thử cloud phone " + dur(a.price) + " miễn phí", "Free " + dur(a.price) + " cloud phone trial"));
                long nd = need(a.price);
                b.addView(Ui.muted(a, Ui.L((nd > 0 ? "Dành cho tài khoản đã nạp 1 lần từ " + Ui.vnd(nd) + ". " : "") + "Mỗi tài khoản 1 máy (tối đa " + a.price.optInt("free_max_ram", 4) + "GB RAM · " + a.price.optInt("free_max_cpu", 4) + " nhân). Hết giờ, máy và dữ liệu tự xoá — muốn dùng tiếp thì thuê máy.",
                        (nd > 0 ? "For accounts that topped up " + Ui.vnd(nd) + "+ at once. " : "") + "One phone per account (up to " + a.price.optInt("free_max_ram", 4) + "GB RAM · " + a.price.optInt("free_max_cpu", 4) + " cores). When time's up the phone and its data are deleted.")), Ui.fill());
                JSONObject tr = m == null ? null : m.optJSONObject("trial");
                if (tr != null && tr.optBoolean("used")) b.addView(Ui.pill(a, "✓ " + Ui.L("Đã dùng thử", "Trial used"), Ui.MUTED), Ui.wrap());
                else if (trialNeedsTopup(a.price, a.isAdmin())) {
                    Button tb = Ui.button(a, Ui.L("Nạp ", "Top up ") + Ui.vnd(nd), Ui.PRIMARY);
                    tb.setOnClickListener(v -> { d[0].dismiss(); a.openTopup(nd); });
                    b.addView(tb, Ui.fill());
                } else {
                    Button tb = Ui.button(a, freeBtn(a.price), Ui.PRIMARY);
                    tb.setOnClickListener(v -> { d[0].dismiss(); a.openTrial(); });
                    b.addView(tb, Ui.fill());
                }
                c.addView(b, Ui.fill());
            }
            JSONObject wh = sec("wheel");
            if (wh != null && Wheel.on() && Wheel.live()) {
                LinearLayout b = block(a, "🎡 " + Ui.L("Vòng quay may mắn", "Lucky wheel"));
                b.addView(Ui.muted(a, t(wh)), Ui.fill());
                Button wb = Ui.button(a, Ui.L("Mở vòng quay", "Open the wheel"), Ui.GHOST);
                wb.setOnClickListener(v -> { d[0].dismiss(); Wheel.open(a); });
                b.addView(wb, Ui.fill());
                c.addView(b, Ui.fill());
            }
            JSONObject cr = creator();
            if (cr != null) {
                LinearLayout b = block(a, "🎬 " + Ui.L("Kiếm tiền", "Earn"));
                b.addView(Ui.muted(a, Ui.L("Làm video về CloudBlue: " + n(cr.optLong("per")) + " view = " + n(cr.optLong("rate")) + " 💎 Blue. View tăng thì nhận thêm.",
                        "Make videos about CloudBlue: " + n(cr.optLong("per")) + " views = " + n(cr.optLong("rate")) + " 💎 Blue. More views, more Blue.")), Ui.fill());
                Button cb = Ui.button(a, Ui.L("Xem cách làm", "How it works"), Ui.GHOST);
                cb.setOnClickListener(v -> { d[0].dismiss(); creatorSheet(a); });
                b.addView(cb, Ui.fill());
                c.addView(b, Ui.fill());
            }
            JSONObject bl = sec("blue");
            if (bl != null && Blue.on()) { LinearLayout b = block(a, "💎 Blue"); b.addView(Ui.muted(a, t(bl)), Ui.fill()); c.addView(b, Ui.fill()); }
            int dl = dayLimit();
            if (dl > 0) c.addView(Ui.muted(a, "🎟️ " + Ui.L("Mỗi tài khoản dùng tối đa " + dl + " mã giảm giá mỗi ngày.", "Each account can use up to " + dl + " discount codes per day.")
                    + (m != null ? Ui.L("  Hôm nay: ", "  Today: ") + m.optInt("day_used") + "/" + dl : "")), Ui.fill());
            if (mine != null && !mineTop) c.addView(mine, Ui.fill());
        };
        draw[0].run();
        d[0] = Ui.sheet(a, "🎁 " + Ui.L("Ưu đãi", "Offers"), c);
        d[0].show();
        load(() -> { if (d[0].isShowing() && !a.isFinishing()) draw[0].run(); });
    }

    // ================================================================ 💳 khối ưu đãi trong hộp Nạp tiền + dòng "lần nạp này được…"
    static View topupBox(MainActivity a, Amt pick) {
        JSONObject tc = topup(); JSONObject m = my;
        boolean trial = a.freeLive() && need(a.price) > 0;
        if (tc == null && !(trial && on())) return null;
        LinearLayout b = block(a, tc != null ? "💰 " + Ui.L("Nạp 1 lần — nhận 1 mã giảm giá cloud phone", "Top up once — get 1 cloud phone discount code")
                : "📱 " + Ui.L("Dùng thử cloud phone", "Cloud phone trial"));
        if (tc != null) {
            JSONArray l = tc.optJSONArray("levels");
            Ui.Wrap w = new Ui.Wrap(a, 8);
            for (int i = 0; i < l.length(); i++) {
                final JSONObject x = l.optJSONObject(i); if (x == null) continue;
                TextView ch = Ui.pill(a, Ui.L("Từ ", "From ") + Ui.vnd(x.optDouble("min")) + " → " + Ui.L("mã ", "") + x.optInt("pct") + "%", Ui.OK);
                ch.setTextSize(Ui.sp(13));
                ch.setPadding(Ui.dp(12), Ui.dp(7), Ui.dp(12), Ui.dp(8));
                ch.setOnClickListener(v -> pick.set(x.optLong("min")));
                w.addView(ch);
            }
            b.addView(w, Ui.fill());
            b.addView(Ui.muted(a, Ui.L("Mỗi tài khoản nhận 1 mã (mức cao nhất của lần nạp) · dùng 1 lần · hạn " + tc.optInt("days", 7) + " ngày · chỉ cho cloud phone (thuê / gia hạn / nâng cấp).",
                    "One code per account (highest level of that top-up) · single use · valid " + tc.optInt("days", 7) + " days · cloud phones only.")), Ui.fill());
            if (m != null && m.optBoolean("topup_got")) {
                String mineCode = null; JSONArray cs = m.optJSONArray("codes");
                for (int i = 0; cs != null && i < cs.length(); i++) { JSONObject x = cs.optJSONObject(i); if (x != null && "topup".equals(x.optString("src")) && x.optBoolean("usable")) { mineCode = codeLabel(x); break; } }
                b.addView(Ui.text(a, "🎫 " + (mineCode != null ? Ui.L("Mã của bạn: ", "Your code: ") + mineCode : Ui.L("Bạn đã nhận mã của đợt này rồi.", "You've already received this round's code.")), 13, Ui.OK, true), Ui.fill());
            }
        }
        if (trial && on()) {
            JSONObject tr = m == null ? null : m.optJSONObject("trial");
            boolean ok = tr != null && tr.optBoolean("ok"), used = tr != null && tr.optBoolean("used");
            b.addView(Ui.text(a, "📱 " + (used ? Ui.L("Bạn đã dùng thử 1 máy rồi.", "You've already used your free trial.")
                    : ok ? Ui.L("Bạn được dùng thử 1 cloud phone " + dur(a.price) + " miễn phí — vào Thuê máy, bật “Dùng thử”.", "You can try 1 cloud phone free for " + dur(a.price) + " — go to Rent and turn on “Free trial”.")
                    : Ui.L("Nạp 1 lần từ " + Ui.vnd(need(a.price)) + " → dùng thử 1 cloud phone " + dur(a.price) + " miễn phí.", "Top up " + Ui.vnd(need(a.price)) + "+ once → try 1 cloud phone free for " + dur(a.price) + ".")), 13, Ui.FG, false), Ui.fill());
        }
        return b;
    }
    static TextView topupHint(MainActivity a) {
        TextView t = Ui.text(a, "", 13, Ui.OK, true);
        t.setVisibility(View.GONE);
        return t;
    }
    static void topupHint(MainActivity a, TextView t, long amount) {
        if (t == null) return;
        StringBuilder s = new StringBuilder();
        JSONObject tc = topup(), m = my;
        if (tc != null && (m == null || !m.optBoolean("topup_got"))) {
            JSONArray l = tc.optJSONArray("levels"); int best = 0;
            for (int i = 0; i < l.length(); i++) { JSONObject x = l.optJSONObject(i); if (x != null && amount >= x.optLong("min")) best = Math.max(best, x.optInt("pct")); }
            if (best > 0) s.append("🎁 ").append(Ui.L("Lần nạp này được tặng mã giảm " + best + "% cloud phone", "This top-up earns a " + best + "% cloud phone code"));
        }
        if (on() && a.freeLive() && trialNeedsTopup(a.price, a.isAdmin()) && amount >= need(a.price))
            s.append(s.length() > 0 ? "\n" : "").append("📱 ").append(Ui.L("Mở dùng thử 1 cloud phone " + dur(a.price) + " miễn phí", "Unlocks a free " + dur(a.price) + " cloud phone trial"));
        t.setText(s.toString());
        t.setVisibility(s.length() == 0 ? View.GONE : View.VISIBLE);
    }

    // ================================================================ 🎬 Kiếm tiền
    static String platformName(String p) {
        switch (p) { case "tiktok": return "TikTok"; case "youtube": return "YouTube"; case "facebook": return "Facebook"; case "instagram": return "Instagram"; default: return Ui.L("nền tảng khác", "other"); }
    }
    static void creatorSheet(MainActivity a) {
        final JSONObject cr = creator();
        if (cr == null) { Ui.toast(a, Ui.L("Chương trình Kiếm tiền đang tạm tắt.", "The Earn program is paused.")); return; }
        final Dialog[] d = new Dialog[1];
        final JSONObject[] data = {null};
        LinearLayout c = Ui.col(a, 12);
        final EditText url = Ui.input(a, "https://www.tiktok.com/@ban/video/…", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        final EditText views = Ui.input(a, Ui.L("Số view hiện tại (nếu có)", "Current views (optional)"), InputType.TYPE_CLASS_NUMBER);
        final EditText note = Ui.input(a, Ui.L("Ghi chú cho admin (không bắt buộc)", "Note for admin (optional)"), InputType.TYPE_CLASS_TEXT);
        final TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        final Button send = Ui.button(a, Ui.L("Gửi video", "Submit video"), Ui.PRIMARY);
        final LinearLayout list = Ui.col(a, 10);
        final TextView sum = Ui.text(a, "", 13, Ui.SKY, true);
        Runnable[] fill = new Runnable[1];
        Runnable reload = () -> Api.bg(() -> { Object r = Api.rpc("creator_my", new JSONObject()); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); },
                r -> { data[0] = r; if (d[0] != null && d[0].isShowing()) fill[0].run(); }, m -> { });
        fill[0] = () -> {
            list.removeAllViews();
            JSONObject o = data[0];
            if (o == null) { list.addView(Ui.muted(a, Ui.L("Đang tải…", "Loading…")), Ui.fill()); return; }
            sum.setText(Ui.L("Đã nhận ", "Earned ") + n(o.optLong("total")) + " 💎  ·  " + Ui.L("tháng này ", "this month ") + n(o.optLong("month")) + " 💎  ·  " + Ui.L("chờ duyệt ", "pending ") + o.optInt("pending"));
            JSONArray vs = o.optJSONArray("videos");
            if (vs == null || vs.length() == 0) { list.addView(Ui.muted(a, Ui.L("Bạn chưa gửi video nào.", "You haven't submitted any videos yet.")), Ui.fill()); return; }
            for (int i = 0; i < vs.length(); i++) {
                final JSONObject v = vs.optJSONObject(i); if (v == null) continue;
                String st = v.optString("status");
                LinearLayout row = Ui.col(a, 6);
                row.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(12), Ui.dp(10));
                row.setBackground(Ui.round(Ui.SUNK, 14, Ui.LINE2));
                LinearLayout h = Ui.row(a, 8);
                h.addView(Ui.pill(a, platformName(v.optString("platform")), Ui.SKY), Ui.wrap());
                h.addView(Ui.pill(a, "ok".equals(st) ? Ui.L("Đã duyệt", "Approved") : "rejected".equals(st) ? Ui.L("Từ chối", "Rejected") : Ui.L("Chờ duyệt", "Pending"),
                        "ok".equals(st) ? Ui.OK : "rejected".equals(st) ? Ui.BAD : Ui.WAIT), Ui.wrap());
                row.addView(h, Ui.fill());
                TextView link = Ui.text(a, v.optString("url"), 12.5f, Ui.MUTED, false);
                link.setMaxLines(1); link.setEllipsize(TextUtils.TruncateAt.MIDDLE);
                row.addView(link, Ui.fill());
                row.addView(Ui.text(a, Ui.L("Đã duyệt ", "Approved ") + n(v.optLong("views")) + " view  ·  " + Ui.L("đã nhận ", "earned ") + n(v.optLong("paid")) + " 💎"
                        + (v.isNull("claimed") ? "" : "  ·  " + Ui.L("bạn báo ", "you reported ") + n(v.optLong("claimed")) + " view"), 13, Ui.FG, false), Ui.fill());
                String an = v.optString("admin_note", "");
                if (!an.isEmpty() && !"null".equals(an)) row.addView(Ui.text(a, "💬 " + an, 12.5f, "rejected".equals(st) ? Ui.BAD : Ui.MUTED, false), Ui.fill());
                if ("ok".equals(st)) {
                    LinearLayout rr = Ui.row(a, 8);
                    final EditText nv = Ui.input(a, Ui.L("Số view mới", "New view count"), InputType.TYPE_CLASS_NUMBER);
                    final Button rb = Ui.button(a, Ui.L("Báo view mới", "Report views"), Ui.GHOST);
                    rr.addView(nv, Ui.weight(1));
                    rr.addView(rb, Ui.wrap());
                    rb.setOnClickListener(x -> {
                        String s = nv.getText().toString().replaceAll("\\D", "");
                        if (s.isEmpty() || s.length() > 11) { Ui.toast(a, Ui.L("Nhập số view đang hiện trên video.", "Enter the views shown on the video.")); return; }
                        rb.setEnabled(false);
                        Api.bg(() -> Api.rpc("creator_report", new JSONObject().put("p_id", v.optLong("id")).put("p_views", Long.parseLong(s))),
                                r -> { Ui.toast(a, Ui.L("Đã báo — admin duyệt xong sẽ cộng 💎 cho phần view mới.", "Reported — you'll get 💎 for the new views once approved.")); reload.run(); },
                                m -> { rb.setEnabled(true); Ui.toast(a, m); });
                    });
                    row.addView(rr, Ui.fill());
                }
                list.addView(row, Ui.fill());
            }
        };
        // đầu hộp: mức thưởng
        LinearLayout hero = Ui.card(a);
        hero.addView(Ui.text(a, n(cr.optLong("per")) + Ui.L(" view = ", " views = ") + n(cr.optLong("rate")) + " 💎", 24, Ui.OK, true));
        hero.addView(Ui.muted(a, Ui.L("1 💎 Blue = 1đ khi thuê / gia hạn cloud phone", "1 💎 Blue = 1đ on cloud phone rentals / renewals")));
        hero.addView(sum, Ui.fill());
        c.addView(hero, Ui.fill());
        StringBuilder pf = new StringBuilder(); JSONArray pl = cr.optJSONArray("platforms");
        for (int i = 0; pl != null && i < pl.length(); i++) pf.append(i > 0 ? ", " : "").append(platformName(pl.optString(i)));
        c.addView(Ui.text(a, Ui.L("Cách làm", "How it works"), 15, Ui.FG, true), Ui.fill());
        c.addView(Ui.text(a, Ui.L("1. Quay video giới thiệu CloudBlue — ví dụ treo game 24/7 trên cloud phone, cách thuê máy, so sánh giá.\n"
                        + "2. Đăng công khai lên " + pf + ". Nói hoặc ghi rõ tên web " + Api.webHost() + ".\n"
                        + "3. Dán link video vào ô bên dưới. Admin mở video kiểm tra rồi cộng 💎 theo số view.\n"
                        + "4. View tăng thì bấm “Báo view mới” — mỗi lần duyệt cộng thêm 💎 cho phần view mới.",
                "1. Record a video about CloudBlue — e.g. running games 24/7 on a cloud phone, how to rent, price comparison.\n"
                        + "2. Post it publicly on " + pf + ". Say or show the website " + Api.webHost() + ".\n"
                        + "3. Paste the video link below. An admin checks the video and adds 💎 by view count.\n"
                        + "4. When views grow, tap “Report views” — each approval adds 💎 for the new views."), 13.5f, Ui.FG, false), Ui.fill());
        c.addView(Ui.muted(a, Ui.L("• Tối đa " + n(cr.optLong("video_max")) + " 💎 / video · " + n(cr.optLong("month_max")) + " 💎 / tháng · gửi tối đa " + cr.optInt("day_submit") + " video / ngày\n"
                        + "• Video của chính bạn, để công khai. Không mua view, không đăng lại video người khác — vi phạm bị từ chối.\n"
                        + "• 💎 Blue chỉ dùng cho cloud phone (thuê / gia hạn), 1 💎 = 1đ" + (cr.optLong("blue_min") > 0 ? ", dùng được khi tài khoản đã nạp từ " + Ui.vnd(cr.optLong("blue_min")) : "") + ". Không dùng cho sản phẩm khác.",
                "• Up to " + n(cr.optLong("video_max")) + " 💎 per video · " + n(cr.optLong("month_max")) + " 💎 per month · " + cr.optInt("day_submit") + " submissions per day\n"
                        + "• Your own public videos only. No bought views, no re-uploads — violations are rejected.\n"
                        + "• 💎 Blue is for cloud phones only (rent / renew), 1 💎 = 1đ" + (cr.optLong("blue_min") > 0 ? ", usable once the account has topped up " + Ui.vnd(cr.optLong("blue_min")) + "+" : "") + ". Not for other products.")), Ui.fill());
        c.addView(Ui.text(a, Ui.L("Gửi video", "Submit a video"), 15, Ui.FG, true), Ui.fill());
        c.addView(url, Ui.fill());
        LinearLayout r2 = Ui.row(a, 8);
        r2.addView(views, Ui.weight(1));
        r2.addView(note, Ui.weight(1.3f));
        c.addView(r2, Ui.fill());
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        c.addView(send, Ui.fill());
        c.addView(Ui.text(a, Ui.L("Video của bạn", "Your videos"), 15, Ui.FG, true), Ui.fill());
        c.addView(list, Ui.fill());
        send.setOnClickListener(v -> {
            String u = url.getText().toString().trim(), vw = views.getText().toString().replaceAll("\\D", "");
            if (!u.matches("(?i)^https://[^\\s/]+\\.[^\\s/]+/.+")) { err.setText(Ui.L("Link video không đúng — dán link đầy đủ bắt đầu bằng https://", "That doesn't look like a video link — paste the full https:// link.")); err.setVisibility(View.VISIBLE); return; }
            err.setVisibility(View.GONE);
            send.setEnabled(false);
            Api.bg(() -> {
                JSONObject args = new JSONObject().put("p_url", u).put("p_views", vw.isEmpty() || vw.length() > 11 ? JSONObject.NULL : (Object) Long.parseLong(vw));
                String nt = note.getText().toString().trim();
                args.put("p_note", nt.isEmpty() ? JSONObject.NULL : nt);
                return Api.rpc("creator_submit", args);
            }, r -> {
                send.setEnabled(true); url.setText(""); views.setText(""); note.setText("");
                Ui.toast(a, Ui.L("Đã gửi — admin duyệt xong sẽ cộng 💎 vào tài khoản.", "Submitted — you'll get 💎 once an admin approves it."));
                reload.run();
            }, m -> { send.setEnabled(true); err.setText(m); err.setVisibility(View.VISIBLE); });
        });
        fill[0].run();
        d[0] = Ui.sheet(a, "🎬 " + Ui.L("Kiếm tiền", "Earn"), c);
        d[0].show();
        reload.run();
    }
}
