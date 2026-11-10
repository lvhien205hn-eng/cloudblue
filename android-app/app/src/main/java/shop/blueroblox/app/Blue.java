package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** 💎 TÍCH BLUE (SQL v27): điểm danh mỗi ngày, nhiệm vụ hằng ngày, Blue dùng trả tiền thuê / gia hạn máy (1 Blue = 1đ).
 *  blue_info() → info {on, blue, can_use, need_topup, today, streak, next_got, tasks[{id, got, done, ready}], cfg, items}.
 *  Máy chủ chưa chạy SQL v27 / admin tắt → info = null hoặc on = false → app ẩn hết, chạy như cũ.
 *  Bản CH Play: chỉ điểm danh + nhiệm vụ mở máy; không nói chuyện trả tiền / mời bạn (luật thanh toán Google Play). */
final class Blue {
    static volatile JSONObject info = null;
    static volatile long at = 0;

    static boolean on() { JSONObject i = info; return i != null && i.optBoolean("on"); }
    static long bal() { JSONObject i = info; return i == null ? 0 : i.optLong("blue"); }
    static boolean canUse() { JSONObject i = info; return !Api.PLAY && i != null && i.optBoolean("on") && i.optBoolean("can_use"); }
    static int maxPct() {
        JSONObject i = info, c = i == null ? null : i.optJSONObject("cfg");
        return c == null ? 100 : Math.max(0, Math.min(100, c.optInt("max_pct", 100)));
    }
    /** Số Blue sẽ trừ cho đơn giá `pay` (giống _blue_take của SQL): tối đa max_pct% đơn, không quá số đang có. */
    static long use(double pay) {
        if (!canUse()) return 0;
        return Math.max(0, Math.min(bal(), (long) Math.floor(Math.max(0, pay) * maxPct() / 100.0)));
    }
    static String n(long v) { return String.format(Locale.US, "%,d", v).replace(',', '.'); }
    static JSONArray tasks() {
        JSONObject i = info; JSONArray t = i == null ? null : i.optJSONArray("tasks");
        if (t == null) return new JSONArray();
        if (!Api.PLAY) return t;
        JSONArray o = new JSONArray();                      // bản CH Play: bỏ nhiệm vụ mời bạn / chia sẻ link
        for (int k = 0; k < t.length(); k++) { JSONObject x = t.optJSONObject(k); if (x != null && !"share".equals(x.optString("id")) && !"invite".equals(x.optString("id"))) o.put(x); }
        return o;
    }
    /** Số nhiệm vụ nhận được ngay (chấm đỏ). */
    static int todo() {
        if (!on()) return 0;
        JSONArray t = tasks(); int c = 0;
        for (int k = 0; k < t.length(); k++) { JSONObject x = t.optJSONObject(k); if (x != null && !x.optBoolean("done") && x.optBoolean("ready")) c++; }
        return c;
    }

    interface Done { void run(); }

    /** Tải lại blue_info ở nền → done() trên luồng giao diện (lỗi / chưa có SQL v27 → info = null). */
    static void load(Done done) {
        Api.bg(() -> {
            try { Object r = Api.rpc("blue_info", new JSONObject()); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); }
            catch (Exception e) { return new JSONObject(); }
        }, r -> {
            info = r.has("on") ? r : null; at = System.currentTimeMillis();
            if (done != null) done.run();
        }, m -> { if (done != null) done.run(); });
    }

    static String vnDay() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        f.setTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
        return f.format(new Date());
    }

    /** Nhiệm vụ "mở máy đám mây" — ControlActivity gọi khi vào máy. Mỗi ngày thử 1 lần / tài khoản; đã nhận / chưa bật thì im lặng. */
    static void playTask(Activity a) {
        final SharedPreferences sp = a.getSharedPreferences("blue", Context.MODE_PRIVATE);
        final String k = "play_" + Api.uid, day = vnDay();
        if (Api.uid.isEmpty() || day.equals(sp.getString(k, ""))) return;
        Api.bg(() -> {
            try { Object r = Api.rpc("blue_task", new JSONObject().put("p_task", "play")); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); }
            catch (Exception e) {
                String m = String.valueOf(e.getMessage());
                if (m.contains("TASK_DONE") || m.contains("TASK_OFF") || m.contains("BLUE_OFF") || m.contains("blue_task")) return new JSONObject().put("skip", true);
                throw e;
            }
        }, o -> {
            sp.edit().putString(k, day).apply();
            long got = o.optLong("got");
            if (got > 0 && !a.isFinishing()) Ui.toast(a, "💎 +" + n(got) + " Blue — " + Ui.L("nhiệm vụ mở máy hôm nay", "today's open-a-phone mission"));
        }, m -> { });
    }

    static String taskName(String id) {
        switch (id) {
            case "checkin": return Ui.L("Điểm danh hôm nay", "Daily check-in");
            case "play": return Ui.L("Mở máy đám mây", "Open a cloud phone");
            case "share": return Ui.L("Chia sẻ link mời", "Share your invite link");
            case "invite": return Ui.L("Mời 1 bạn đăng ký", "Invite a friend to sign up");
            default: return id;
        }
    }
    static String taskIcon(String id) {
        switch (id) { case "checkin": return "📅"; case "play": return "📱"; case "share": return "📣"; case "invite": return "🤝"; default: return "⭐"; }
    }
    static String taskSub(JSONObject t) {
        String id = t.optString("id");
        if ("checkin".equals(id)) return Ui.L("Ngày nào cũng ghé là có Blue", "Drop by every day to earn");
        if ("play".equals(id)) return t.optBoolean("ready") || t.optBoolean("done") ? Ui.L("Mở 1 máy bất kỳ là tự nhận", "Open any phone — claimed automatically")
                : Ui.L("Cần có 1 máy đang chạy", "You need a running phone");
        if ("share".equals(id)) return Ui.L("Gửi link CloudBlue cho bạn bè hoặc nhóm", "Send your CloudBlue link to friends");
        if ("invite".equals(id)) return t.optBoolean("ready") ? Ui.L("Đã có bạn đăng ký qua link của bạn hôm nay 🎉", "A friend signed up with your link today 🎉")
                : Ui.L("Có bạn đăng ký qua link của bạn trong hôm nay", "A friend signs up with your link today");
        return "";
    }
    static String kindName(String k) {
        switch (k) {
            case "checkin": return Ui.L("Điểm danh", "Check-in"); case "streak": return Ui.L("Thưởng chuỗi", "Streak bonus");
            case "task": return Ui.L("Nhiệm vụ", "Mission"); case "ref": return Ui.L("Mời bạn", "Invite");
            case "cashback": return Ui.L("Hoàn đơn", "Cashback"); case "spend": return Ui.L("Đã dùng", "Spent");
            case "refund": return Ui.L("Hoàn lại", "Refund"); case "clawback": return Ui.L("Thu lại", "Reversed");
            default: return "Admin";
        }
    }

    /** Hộp 💎 Tích Blue: số Blue, chuỗi điểm danh, nhiệm vụ hôm nay, cách nhận thêm, lịch sử. */
    /** Cách nhận / dùng Blue theo cấu hình admin đang bật (con số đổi theo admin) — cho hộp giới thiệu lần đầu. */
    static String introText() {
        JSONObject i = info, c = i == null ? null : i.optJSONObject("cfg");
        if (c == null) c = new JSONObject();
        StringBuilder s = new StringBuilder();
        long ck = c.optLong("checkin"), sb = c.optLong("streak_bonus"); int sd = c.optInt("streak_days");
        if (ck > 0) s.append("📅 ").append(Ui.L("Điểm danh mỗi ngày: +", "Daily check-in: +")).append(n(ck)).append(" Blue")
                .append(sb > 0 && sd > 0 ? Ui.L(" (đủ " + sd + " ngày liền thưởng thêm +" + n(sb) + ")", " (+" + n(sb) + " bonus every " + sd + " days in a row)") : "").append("\n");
        JSONArray t = tasks();
        for (int k = 0; k < t.length(); k++) {
            JSONObject x = t.optJSONObject(k);
            if (x == null || "checkin".equals(x.optString("id")) || x.optLong("got") <= 0) continue;
            s.append(taskIcon(x.optString("id"))).append(" ").append(taskName(x.optString("id"))).append(": +").append(n(x.optLong("got")))
                    .append(Ui.L(" Blue mỗi ngày", " Blue a day")).append("\n");
        }
        if (!Api.PLAY) {
            if (c.optLong("ref") > 0) s.append("🎁 ").append(Ui.L("Bạn được mời nạp tiền / mua lần đầu: +", "An invited friend's first top-up / purchase: +")).append(n(c.optLong("ref"))).append(" Blue\n");
            if (c.optDouble("cashback") > 0) s.append("💸 ").append(Ui.L("Mỗi đơn trả bằng tiền: hoàn ", "Every paid order: ")).append(fmtPct(c.optDouble("cashback"))).append(Ui.L("% thành Blue\n", "% back in Blue\n"));
            s.append("\n").append(Ui.L("Dùng Blue: bật \"💎 Trả bằng Blue\" khi thuê / gia hạn máy — 1 Blue = 1đ", "Spend: turn on \"💎 Pay with Blue\" when renting / renewing — 1 Blue = 1đ"))
                    .append(maxPct() < 100 ? Ui.L(", tối đa " + maxPct() + "% mỗi đơn.", ", up to " + maxPct() + "% per order.") : Ui.L(", trả được cả đơn.", ", up to the whole order."));
            if (i != null && !i.optBoolean("can_use") && i.optBoolean("need_topup", true))
                s.append("\n🔒 ").append(Ui.L("Nạp tiền ít nhất 1 lần để mở khoá trả bằng Blue (vẫn tích bình thường).", "Top up once to unlock paying with Blue (you still earn as usual)."));
        }
        s.append("\n\n").append(Ui.L("Xem lại bất cứ lúc nào: bấm 💎 ở trên cùng.", "Tap 💎 at the top any time to see this again."));
        return s.toString().trim();
    }

    /** 🎉 Hộp giới thiệu "Tích Blue" — hiện 1 lần / tài khoản / máy (MainActivity.blueChanged gọi). */
    static void intro(MainActivity a) {
        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.text(a, Api.PLAY ? Ui.L("Ghé app mỗi ngày để tích Blue. Cách nhận:", "Drop by every day to earn Blue. How:")
                : Ui.L("Tích Blue để thuê / gia hạn máy rẻ hơn — 1 Blue = 1đ. Cách nhận:", "Earn Blue to pay less for phones — 1 Blue = 1đ. How to earn:"), 14.5f, Ui.FG, true), Ui.fill());
        c.addView(Ui.text(a, introText(), 14, Ui.FG, false), Ui.fill());
        Button later = Ui.button(a, Ui.L("Để sau", "Later"), Ui.GHOST);
        Button go = Ui.button(a, "💎 " + Ui.L("Nhận Blue ngay", "Get Blue now"), Ui.PRIMARY);
        LinearLayout r = Ui.row(a, 10);
        r.addView(later, Ui.weight(1));
        r.addView(go, Ui.weight(1));
        c.addView(r, Ui.fill());
        Dialog d = Ui.sheet(a, "🎉 " + Ui.L("Mới: Tích Blue", "New: Blue rewards"), c);
        later.setOnClickListener(v -> d.dismiss());
        go.setOnClickListener(v -> { d.dismiss(); sheet(a); });
        d.show();
    }

    static void sheet(MainActivity a) {
        final Dialog[] d = new Dialog[1];
        LinearLayout c = Ui.col(a, 12);
        Runnable[] draw = new Runnable[1];
        draw[0] = () -> {
            c.removeAllViews();
            JSONObject i = info;
            if (i == null || !i.optBoolean("on")) {
                c.addView(Ui.muted(a, i == null ? Ui.L("Chưa mở được Tích Blue — thử lại sau.", "Couldn't load Blue rewards — try again later.")
                        : Ui.L("Tích Blue đang tạm tắt.", "Blue rewards are paused.")), Ui.fill());
                return;
            }
            JSONObject cfg = i.optJSONObject("cfg"); if (cfg == null) cfg = new JSONObject();
            // số Blue
            LinearLayout hero = Ui.card(a);
            hero.addView(Ui.text(a, "💎 " + n(i.optLong("blue")) + " Blue", 26, Ui.SKY, true));
            hero.addView(Ui.muted(a, Api.PLAY ? Ui.L("Blue tích từ điểm danh và nhiệm vụ hằng ngày.", "Earn Blue from daily check-ins and missions.")
                    : Ui.L("1 Blue = 1đ khi thuê / gia hạn điện thoại đám mây", "1 Blue = 1đ on cloud phone rentals / renewals")
                      + (maxPct() < 100 ? Ui.L(" (tối đa " + maxPct() + "% mỗi đơn)", " (max " + maxPct() + "% per order)") : "")));
            if (!Api.PLAY && !i.optBoolean("can_use") && i.optBoolean("need_topup"))
                hero.addView(Ui.text(a, "🔒 " + Ui.L("Nạp tiền lần đầu để mở khoá trả bằng Blue. Blue vẫn được tích bình thường.",
                        "Top up once to unlock paying with Blue. You keep earning meanwhile."), 12.5f, Ui.WAIT, false), Ui.fill());
            c.addView(hero, Ui.fill());
            // chuỗi điểm danh
            int sd = cfg.optInt("streak_days"), st = i.optInt("streak"); boolean today = i.optBoolean("today");
            if (sd > 0 && sd <= 14 && cfg.optLong("checkin") > 0) {
                int filled = today ? ((st - 1) % sd) + 1 : st % sd, now = today ? filled : filled + 1;
                c.addView(Ui.text(a, Ui.L("Chuỗi điểm danh: ", "Check-in streak: ") + (st > 0 ? st + Ui.L(" ngày liền", " day(s)") : Ui.L("bắt đầu hôm nay", "starts today")), 14, Ui.FG, true));
                LinearLayout wk = Ui.row(a, 4);
                for (int k = 1; k <= sd; k++) {
                    boolean got = k <= filled, big = k == sd;
                    TextView t = Ui.text(a, (k == now ? Ui.L("Nay", "Today") : "N" + k) + "\n" + (got ? "✓" : "+" + n(cfg.optLong("checkin") + (big ? cfg.optLong("streak_bonus") : 0))),
                            11, got ? Ui.OK : big ? Ui.SKY : Ui.MUTED, k == now);
                    t.setGravity(Gravity.CENTER);
                    t.setPadding(0, Ui.dp(6), 0, Ui.dp(6));
                    t.setBackground(Ui.round(got ? 0x1A3CE0B0 : Ui.PANEL2, 10, k == now ? Ui.SKY : Ui.LINE));
                    wk.addView(t, Ui.weight(1));
                }
                c.addView(wk, Ui.fill());
            }
            // nhiệm vụ hôm nay
            JSONArray ts = tasks(); int done = 0;
            for (int k = 0; k < ts.length(); k++) if (ts.optJSONObject(k).optBoolean("done")) done++;
            c.addView(Ui.text(a, Ui.L("Nhiệm vụ hôm nay", "Today's missions") + "  ·  " + done + "/" + ts.length(), 14, Ui.FG, true));
            for (int k = 0; k < ts.length(); k++) {
                final JSONObject t = ts.optJSONObject(k); final String id = t.optString("id");
                LinearLayout r = Ui.row(a, 10);
                r.setBackground(Ui.round(Ui.PANEL2, 14, Ui.LINE));
                r.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(10), Ui.dp(10));
                TextView ic = Ui.text(a, taskIcon(id), 18, Ui.FG, false);
                r.addView(ic, Ui.wrap());
                LinearLayout tx = Ui.col(a, 2);
                tx.addView(Ui.text(a, taskName(id) + "  +" + n(t.optLong("got")), 14.5f, Ui.FG, true));
                tx.addView(Ui.text(a, taskSub(t), 12, Ui.MUTED, false));
                r.addView(tx, Ui.weight(1));
                if (t.optBoolean("done")) r.addView(Ui.text(a, "✓ " + Ui.L("Đã nhận", "Claimed"), 12.5f, Ui.OK, true), Ui.wrap());
                else {
                    String label; final Runnable act;
                    if ("checkin".equals(id)) { label = Ui.L("Điểm danh", "Check in"); act = () -> checkin(a, draw[0]); }
                    else if ("play".equals(id)) {
                        label = t.optBoolean("ready") ? Ui.L("Mở máy", "Open") : (Api.PLAY ? null : Ui.L("Thuê máy", "Rent"));
                        act = () -> { if (d[0] != null) d[0].dismiss(); a.show(t.optBoolean("ready") ? 0 : 1); };
                    }
                    else if ("share".equals(id)) { label = Ui.L("Chia sẻ", "Share"); act = () -> share(a, draw[0]); }
                    else { label = t.optBoolean("ready") ? Ui.L("Nhận", "Claim") : Ui.L("Mời bạn", "Invite");
                        act = t.optBoolean("ready") ? () -> task(a, "invite", draw[0]) : () -> share(a, draw[0]); }
                    if (label != null) {
                        Button b = Ui.button(a, label, "checkin".equals(id) || "share".equals(id) || t.optBoolean("ready") ? Ui.PRIMARY : Ui.GHOST);
                        b.setOnClickListener(v -> { b.setEnabled(false); act.run(); });
                        r.addView(b, Ui.wrap());
                    }
                }
                c.addView(r, Ui.fill());
            }
            // nhận thêm
            if (!Api.PLAY) {
                StringBuilder more = new StringBuilder();
                if (cfg.optLong("ref") > 0) more.append("• ").append(Ui.L("Bạn bè bạn mời nạp tiền / mua lần đầu: +", "Each invited friend's first top-up or purchase: +")).append(n(cfg.optLong("ref"))).append(" Blue\n");
                if (cfg.optDouble("cashback") > 0) more.append("• ").append(Ui.L("Mỗi đơn trả bằng tiền: hoàn ", "Every paid order: ")).append(fmtPct(cfg.optDouble("cashback"))).append(Ui.L("% bằng Blue\n", "% back in Blue\n"));
                more.append("• ").append(Ui.L("Nhiệm vụ làm mới lúc 0 giờ mỗi ngày (giờ Việt Nam)", "Missions reset at midnight (Vietnam time)"));
                c.addView(Ui.muted(a, more.toString()), Ui.fill());
            }
            // lịch sử
            JSONArray it = i.optJSONArray("items");
            if (it != null && it.length() > 0) {
                c.addView(Ui.text(a, Ui.L("Lịch sử Blue", "Blue history"), 14, Ui.FG, true));
                SimpleDateFormat f = new SimpleDateFormat("dd/MM HH:mm", Locale.US);
                for (int k = 0; k < Math.min(15, it.length()); k++) {
                    JSONObject x = it.optJSONObject(k); if (x == null) continue;
                    long dv = x.optLong("delta"); long t = MainActivity.parseTime(x.optString("t"));
                    LinearLayout r = Ui.row(a, 8);
                    String note = x.optString("note", ""); if (note.isEmpty() || "null".equals(note)) note = kindName(x.optString("kind"));
                    r.addView(Ui.text(a, (t > 0 ? f.format(new Date(t)) + " · " : "") + note, 12.5f, Ui.MUTED, false), Ui.weight(1));
                    r.addView(Ui.text(a, (dv >= 0 ? "+" : "−") + n(Math.abs(dv)), 13, dv >= 0 ? Ui.OK : Ui.BAD, true), Ui.wrap());
                    c.addView(r, Ui.fill());
                }
            }
        };
        draw[0].run();
        d[0] = Ui.sheet(a, "💎 " + Ui.L("Tích Blue", "Blue rewards"), c);
        d[0].show();
        load(() -> { if (d[0].isShowing()) draw[0].run(); a.blueChanged(); });
    }

    /** Dòng "💎 Trả bằng Blue" trong bảng thuê / gia hạn máy (chỉ bản web). use(pay) = số Blue sẽ trừ cho đơn. */
    static final class Pay {
        final LinearLayout view; final android.widget.Switch sw; final TextView sub; final Button earn;
        boolean on;
        Pay(MainActivity a, boolean startOn, Runnable changed) {
            on = startOn;
            view = Ui.row(a, 10);
            view.setBackground(Ui.round(Ui.PANEL2, 14, Ui.LINE));
            view.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(10), Ui.dp(10));
            LinearLayout tx = Ui.col(a, 2);
            tx.addView(Ui.text(a, "💎 " + Ui.L("Trả bằng Blue", "Pay with Blue"), 14.5f, Ui.FG, true));
            sub = Ui.text(a, "", 12.5f, Ui.MUTED, false);
            tx.addView(sub);
            view.addView(tx, Ui.weight(1));
            earn = Ui.button(a, Ui.L("Tích Blue", "Earn Blue"), Ui.GHOST);
            earn.setOnClickListener(v -> sheet(a));
            view.addView(earn, Ui.wrap());
            sw = new android.widget.Switch(a);
            sw.setChecked(startOn);
            sw.setContentDescription(Ui.L("Trả bằng Blue", "Pay with Blue"));
            sw.setOnCheckedChangeListener((b, c) -> { if (on != c) { on = c; changed.run(); } });
            view.addView(sw, Ui.wrap());
            view.setOnClickListener(v -> { if (sw.isEnabled()) sw.toggle(); });
        }
        long use(double pay) { return on ? Blue.use(pay) : 0; }
        void paint(double pay, boolean hide) {
            if (hide || Api.PLAY || !Blue.on()) { view.setVisibility(View.GONE); return; }
            view.setVisibility(View.VISIBLE);
            boolean can = Blue.canUse(); long have = Blue.bal(), u = use(pay);
            boolean ok = can && have > 0;
            sw.setEnabled(ok); sw.setVisibility(ok ? View.VISIBLE : View.GONE); earn.setVisibility(ok ? View.GONE : View.VISIBLE);
            if (!ok && sw.isChecked()) sw.setChecked(false);
            sub.setText(!can ? "🔒 " + Ui.L("Nạp tiền lần đầu để dùng Blue", "Top up once to unlock Blue")
                    : have <= 0 ? Ui.L("Chưa có Blue — điểm danh, làm nhiệm vụ để tích", "No Blue yet — check in and do missions")
                    : u > 0 ? Ui.L("Trừ " + n(u) + " Blue (= " + Ui.vnd(u) + ") · còn " + n(have - u) + " Blue", "Uses " + n(u) + " Blue (= " + Ui.vnd(u) + ") · " + n(have - u) + " left")
                    : Ui.L("Bạn có " + n(have) + " Blue · 1 Blue = 1đ", "You have " + n(have) + " Blue · 1 Blue = 1đ"));
        }
    }

    static String fmtPct(double v) { return v == Math.floor(v) ? String.valueOf((long) v) : String.valueOf(v); }

    static void checkin(MainActivity a, Runnable redraw) {
        Api.bg(() -> {
            try { Object r = Api.rpc("blue_checkin", new JSONObject()); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); }
            catch (Exception e) { return new JSONObject().put("err", String.valueOf(e.getMessage())); }
        }, o -> {
            if (o.has("err")) Ui.toast(a, Api.friendly(new Exception(o.optString("err"))));
            else if (o.optLong("bonus") > 0) Ui.toast(a, "🎉 +" + n(o.optLong("got") + o.optLong("bonus")) + " Blue — " + Ui.L("đủ chuỗi ", "") + o.optInt("streak") + Ui.L(" ngày!", "-day streak!"));
            else Ui.toast(a, "💎 +" + n(o.optLong("got")) + " Blue — " + Ui.L("điểm danh ngày ", "check-in day ") + o.optInt("streak"));
            load(() -> { redraw.run(); a.blueChanged(); });
        }, m -> { Ui.toast(a, m); redraw.run(); });
    }

    static void task(MainActivity a, String id, Runnable redraw) {
        Api.bg(() -> {
            try { Object r = Api.rpc("blue_task", new JSONObject().put("p_task", id)); return r instanceof JSONObject ? (JSONObject) r : new JSONObject(); }
            catch (Exception e) { return new JSONObject().put("err", String.valueOf(e.getMessage())); }
        }, o -> {
            if (o.has("err")) { if (!o.optString("err").contains("TASK_DONE")) Ui.toast(a, Api.friendly(new Exception(o.optString("err")))); }
            else if (o.optLong("got") > 0) Ui.toast(a, "💎 +" + n(o.optLong("got")) + " Blue · " + taskName(id));
            load(() -> { redraw.run(); a.blueChanged(); });
        }, m -> { Ui.toast(a, m); redraw.run(); });
    }

    /** Chia sẻ link mời qua bảng chia sẻ của Android → nhận nhiệm vụ "chia sẻ link mời". */
    static void share(MainActivity a, Runnable redraw) {
        Api.bg(() -> {
            try { Object r = Api.rpc("ref_info", new JSONObject()); if (r instanceof JSONObject && !((JSONObject) r).optString("code").isEmpty()) return Api.WEB + "/?ref=" + ((JSONObject) r).optString("code"); }
            catch (Exception ignored) { }
            return Api.WEB + "/";
        }, link -> {
            String text = Ui.L("Thuê điện thoại Android đám mây chạy 24/7 ở CloudBlue — đăng ký qua link của mình nhé: ", "Rent a 24/7 cloud Android phone at CloudBlue — sign up with my link: ") + link;
            try {
                ClipboardManager cm = (ClipboardManager) a.getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("ref", text));
                a.startActivity(Intent.createChooser(new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text), Ui.L("Gửi link mời", "Share invite link")));
            } catch (Exception ignored) { }
            task(a, "share", redraw);
        }, m -> { Ui.toast(a, m); redraw.run(); });
    }
}
