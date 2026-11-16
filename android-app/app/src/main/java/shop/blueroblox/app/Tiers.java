package shop.blueroblox.app;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** 🎴 Thẻ gói cấu hình trong trang Thuê máy — cùng danh sách với web (settings.cp_tiers, admin chỉnh ở
 *  📱 ĐT đám mây › 💰 Giá & thẻ bán). Admin chưa chỉnh thì dùng 5 gói mặc định giống web. */
final class Tiers {
    private Tiers() { }

    static final class T {
        String id, icon, name, tag, badge, res, color;
        int ram, cpu, fps;
        List<String> fit = new ArrayList<>();
    }

    /** 16/11c: nhãn gói (admin gõ tiếng Việt) theo ngôn ngữ khách chọn; English mà không dịch được → ẩn nhãn. */
    static String badge(String b) {
        if (b == null || Ui.vi()) return b == null ? "" : b;
        String s = b;
        String[][] m = {{"Bán chạy", "Popular"}, {"Đề xuất", "Recommended"}, {"Khuyên dùng", "Recommended"}, {"Mới", "New"}, {"Giá tốt", "Best value"},
                {"Tiết kiệm", "Saver"}, {"Mạnh nhất", "Most powerful"}, {"Hot", "Hot"}, {"Giảm giá", "Sale"}};
        for (String[] x : m) s = s.replace(x[0], x[1]);
        return Srv.hasVi(s) ? "" : s;
    }

    private static final String[][] DEF = {
            // id, icon, name, mô tả VI, mô tả EN, ram, cpu, fps, nhãn, màu, phù hợp VI (|), phù hợp EN (|)
            {"lite", "💬", "Blue Lite", "Treo app · nuôi acc", "Apps · account farming", "2", "2", "30", "", "blue",
                    "Zalo, Facebook, TikTok, Telegram|Chạy 24/7 kể cả khi tắt máy tính", "Zalo, Facebook, TikTok, Telegram|Runs 24/7 even when your PC is off"},
            {"game", "🎮", "Blue Game", "Game nhẹ · treo cả ngày", "Light games · all-day idle", "4", "2", "30", "", "teal",
                    "Game 2D, nhàn rỗi, cờ, bài|Treo game nhẹ ổn định", "2D, idle, card & board games|Stable for light games"},
            {"roblox", "🕹️", "Blue Plus", "Treo game 1 tab mượt", "Smooth gaming · 1 tab", "4", "4", "30", "🔥 Bán chạy", "amber",
                    "1 tab game, đồ hoạ thấp|Game dùng ~2GB RAM — vẫn còn dư", "1 game tab, low graphics|Games use ~2GB RAM — room to spare"},
            {"pro", "🚀", "Blue Pro", "Treo 2–4 tab game", "2–4 game tabs", "8", "8", "30", "⭐ Đề xuất", "violet",
                    "2–4 tab game cùng lúc|Mỗi tab thêm cần ~1,5–2GB RAM", "2–4 game tabs at once|Each extra tab needs ~1.5–2GB RAM"},
            {"max", "🔥", "Blue Max", "Game nặng 3D · 60 FPS", "Heavy 3D games · 60 FPS", "12", "8", "60", "", "rose",
                    "Free Fire, Liên Quân, PUBG Mobile…|Không có card đồ hoạ — game nặng có thể giật", "Free Fire, PUBG Mobile, Genshin…|No GPU — heavy games may stutter"},
    };

    /** Bản CH Play: gói gợi ý viết trung tính (không nêu tên game / ứng dụng của hãng khác — chính sách Google Play).
     *  Giá vẫn tính theo bảng giá thật của máy chủ (perDay), chỉ khác chữ trên thẻ. */
    private static final String[][] PLAY_DEF = {
            {"p-lite", "💬", "Blue Lite", "Ứng dụng nhẹ · chạy 24/7", "Light apps · runs 24/7", "2", "2", "30", "", "blue",
                    "Nhắn tin, mạng xã hội, đọc tin|Vẫn chạy khi bạn tắt điện thoại", "Messaging, social, news|Keeps running when your phone is off"},
            {"p-std", "📱", "Blue Standard", "Dùng hằng ngày · đa nhiệm", "Everyday use · multitasking", "4", "2", "30", "", "teal",
                    "Mở nhiều ứng dụng cùng lúc|Game 2D, cờ, bài", "Several apps at once|2D, card & board games"},
            {"p-plus", "⚡", "Blue Plus", "Mượt hơn · 4 nhân", "Smoother · 4 cores", "4", "4", "30", "", "amber",
                    "Ứng dụng nặng hơn vẫn mượt|Còn dư RAM để đa nhiệm", "Heavier apps stay smooth|Spare RAM for multitasking"},
            {"p-pro", "🚀", "Blue Pro", "8GB · 8 nhân · nhiều việc cùng lúc", "8GB · 8 cores · heavy multitasking", "8", "8", "30", "⭐ Đề xuất", "violet",
                    "Nhiều ứng dụng chạy song song|Phù hợp làm việc cả ngày", "Many apps side by side|Built for all-day work"},
            {"p-max", "🔥", "Blue Max", "Mạnh nhất · 60 FPS", "Most power · 60 FPS", "12", "8", "60", "", "rose",
                    "Ứng dụng & game 3D nặng|Không có card đồ hoạ — game rất nặng có thể giật", "Heavy apps & 3D games|No GPU — very heavy games may stutter"},
    };

    static int color(String k) {
        if (k == null) k = "";
        switch (k) {
            case "teal": return Color.rgb(47, 211, 197);
            case "amber": return Color.rgb(255, 181, 71);
            case "violet": return Color.rgb(167, 123, 255);
            case "rose": return Color.rgb(255, 107, 138);
            case "green": return Color.rgb(70, 217, 137);
            case "sky": return Color.rgb(56, 189, 248);
            case "gold": return Color.rgb(245, 196, 81);
            default:
                if (k.matches("#[0-9a-fA-F]{6}")) try { return Color.parseColor(k); } catch (Exception ignored) { }
                return Color.rgb(111, 140, 255);
        }
    }

    /** Danh sách gói đang bật (tối đa 8). Bản CH Play: luôn dùng gói trung tính PLAY_DEF. */
    static List<T> list() {
        List<T> out = new ArrayList<>();
        JSONArray a = Api.PLAY ? null : Api.tiers;
        if (a != null && a.length() > 0) {
            for (int i = 0; i < a.length() && out.size() < 8; i++) {
                JSONObject o = a.optJSONObject(i);
                if (o == null || !o.optBoolean("on", true)) continue;
                T t = new T();
                t.id = o.optString("id", "t" + i); t.icon = o.optString("icon", "📱"); t.name = clean(o.optString("name", "").trim());
                String vi = o.optString("vi", ""), en = o.optString("en", "");
                t.tag = clean(Ui.L(vi, en.isEmpty() ? vi : en));
                t.ram = o.optInt("ram", 0); t.cpu = o.optInt("cpu", 0); t.fps = o.optInt("fps", 30);
                t.res = o.optString("res", ""); t.badge = clean(o.optString("badge", "")); t.color = o.optString("color", "blue");
                JSONArray f = o.optJSONArray(Ui.L("fvi", "fen"));
                if (f == null || f.length() == 0) f = o.optJSONArray("fvi");
                if (f != null) for (int j = 0; j < f.length() && t.fit.size() < 3; j++) { String s = clean(f.optString(j, "").trim()); if (!s.isEmpty()) t.fit.add(s); }
                if (t.ram > 0 && t.cpu > 0 && !t.name.isEmpty()) out.add(t);
            }
            return out;
        }
        for (String[] d : Api.PLAY ? PLAY_DEF : DEF) {
            T t = new T();
            t.id = d[0]; t.icon = d[1]; t.name = d[2]; t.tag = Ui.L(d[3], d[4]);
            t.ram = Integer.parseInt(d[5]); t.cpu = Integer.parseInt(d[6]); t.fps = Integer.parseInt(d[7]);
            t.badge = d[8]; t.color = d[9]; t.res = "";
            for (String s : Ui.L(d[10], d[11]).split("\\|")) t.fit.add(s);
            out.add(t);
        }
        return out;
    }

    private static int mix(int a, int b, float k) {         // a·k + b·(1−k)
        return Color.rgb(Math.round(Color.red(a) * k + Color.red(b) * (1 - k)), Math.round(Color.green(a) * k + Color.green(b) * (1 - k)),
                Math.round(Color.blue(a) * k + Color.blue(b) * (1 - k)));
    }

    /** Thẻ hiện cho khách không nhắc tên game: "Roblox" → "game", "Blue Roblox" → "Blue Plus" (gói admin lưu từ trước cũng tự đổi — giống web). */
    static String clean(String s) {
        if (s == null || !s.toLowerCase(java.util.Locale.ROOT).contains("roblox")) return s;
        String r = s.replaceAll("(?i)blue\\s*roblox", "Blue Plus").replaceAll("(?i)roblox", "game")
                .replaceAll("(?i)\\bgame(\\s+game)+\\b", "game").replaceAll("\\s{2,}", " ").trim();
        if (!r.isEmpty() && Character.isUpperCase(s.charAt(0))) r = Character.toUpperCase(r.charAt(0)) + r.substring(1);
        return r;
    }

    private static int a(int alpha, int c) { return Color.argb(alpha, Color.red(c), Color.green(c), Color.blue(c)); }

    /** 1 hàng gói trong danh sách dọc: biểu tượng · tên + nhãn · công dụng · "4 nhân · 4GB RAM · 30 FPS" · giá / ngày bên phải.
     *  Hàng đang chọn: viền màu gói + dấu ✓ + mở thêm "phù hợp" và giá 30 ngày. setOn() đổi tại chỗ, không vẽ lại trang. */
    static final class Card {
        final LinearLayout view;
        private final TextView ck;
        private final LinearLayout more;
        private final int acc;
        private final GradientDrawable bg;

        Card(Context c, T t, double perDay, List<String> ands, List<String> busy, boolean partial, Runnable pick) {
            acc = color(t.color);
            view = Ui.col(c, 8);
            view.setPadding(Ui.dp(12), Ui.dp(12), Ui.dp(12), Ui.dp(12));
            bg = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{mix(acc, Ui.PANEL, Ui.LIGHT ? .12f : .22f), Ui.PANEL});
            bg.setCornerRadius(Ui.dp(Ui.rad(16)));
            view.setBackground(bg);
            view.setClickable(true);
            view.setFocusable(true);
            view.setContentDescription(t.name);
            view.setOnClickListener(v -> pick.run());

            LinearLayout top = Ui.row(c, 10);
            top.setGravity(Gravity.CENTER_VERTICAL);
            FrameLayout ib = new FrameLayout(c);                       // biểu tượng + huy hiệu ✓ ở góc khi đang chọn
            TextView ic = Ui.text(c, t.icon == null || t.icon.isEmpty() ? "📱" : t.icon, 16, Ui.FG, false);
            ic.setGravity(Gravity.CENTER);
            ic.setBackground(Ui.round(a(55, acc), 10, a(110, acc)));
            ib.addView(ic, new FrameLayout.LayoutParams(Ui.dp(34), Ui.dp(34)));
            ck = Ui.text(c, "✓", 10, Ui.LIGHT ? Color.WHITE : Color.rgb(6, 17, 43), true);
            ck.setGravity(Gravity.CENTER);
            GradientDrawable cg = new GradientDrawable();
            cg.setShape(GradientDrawable.OVAL);
            cg.setColor(acc);
            cg.setStroke(Ui.dp(2), Ui.PANEL);
            ck.setBackground(cg);
            ib.addView(ck, new FrameLayout.LayoutParams(Ui.dp(18), Ui.dp(18), Gravity.END | Gravity.BOTTOM));
            top.addView(ib, new LinearLayout.LayoutParams(Ui.dp(40), Ui.dp(40)));

            LinearLayout mid = Ui.col(c, 2);
            LinearLayout nr = Ui.row(c, 6);
            TextView nm = Ui.text(c, t.name, 16.5f, Ui.LIGHT ? mix(acc, Color.rgb(10, 26, 58), .62f) : mix(acc, Color.WHITE, .55f), true);
            nm.setMaxLines(1);
            nm.setEllipsize(android.text.TextUtils.TruncateAt.END);
            nr.addView(nm, Ui.fill());
            mid.addView(nr, Ui.fill());
            if (t.tag != null && !t.tag.isEmpty()) {
                TextView tg = Ui.text(c, t.tag, 12.5f, Ui.MUTED, false);
                tg.setMaxLines(1);
                tg.setEllipsize(android.text.TextUtils.TruncateAt.END);
                mid.addView(tg, Ui.fill());
            }
            TextView spc = Ui.text(c, t.cpu + Ui.L(" nhân · ", " cores · ") + t.ram + "GB · " + t.fps + " FPS", 12.5f, Ui.FG, true);
            spc.setMaxLines(2);
            mid.addView(spc, Ui.fill());
            top.addView(mid, Ui.weight(1));

            LinearLayout pr = Ui.col(c, 0);
            pr.setGravity(Gravity.END);
            if (t.badge != null && !badge(t.badge).isEmpty()) {      // nhãn 🔥 Bán chạy · ⭐ Đề xuất nằm trên giá
                TextView b = Ui.text(c, badge(t.badge), 10.5f, Color.WHITE, true);
                b.setPadding(Ui.dp(7), Ui.dp(1), Ui.dp(7), Ui.dp(2));
                b.setMaxLines(1);
                GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{Color.rgb(255, 79, 109), Color.rgb(255, 154, 68)});
                g.setCornerRadius(Ui.dp(99));
                b.setBackground(g);
                LinearLayout.LayoutParams bl = Ui.wrap();
                bl.gravity = Gravity.END;
                bl.bottomMargin = Ui.dp(3);
                pr.addView(b, bl);
            }
            TextView p = Ui.text(c, Ui.vnd(perDay), 17, Ui.FG, true);
            p.setGravity(Gravity.END);
            pr.addView(p, Ui.wrap());
            TextView pd = Ui.text(c, Ui.L("/ ngày", "/ day"), 11.5f, Ui.MUTED, false);
            pd.setGravity(Gravity.END);
            pr.addView(pd, Ui.wrap());
            top.addView(pr, Ui.wrap());
            view.addView(top, Ui.fill());

            if (partial) {                                           // gói không chạy đủ mọi bản Android → luôn nói rõ
                StringBuilder an = new StringBuilder();
                for (String v : ands) an.append(an.length() == 0 ? "" : " · ").append(v).append(busy.contains(v) ? Ui.L(" (hết chỗ)", " (full)") : "");
                TextView al = Ui.text(c, "Android  " + (an.length() == 0 ? Ui.L("vượt trần cấu hình", "over the limit") : an.toString()), 12, Ui.WAIT, true);
                al.setPadding(Ui.dp(50), 0, 0, 0);
                view.addView(al, Ui.fill());
            }
            more = Ui.col(c, 3);                                     // chỉ hàng đang chọn mới mở phần này
            more.setPadding(Ui.dp(50), 0, 0, 0);
            for (String f : t.fit) more.addView(Ui.text(c, "✓  " + f, 12.5f, Ui.FG, false), Ui.fill());
            more.addView(Ui.text(c, "≈ " + Ui.vnd(perDay * 30) + Ui.L(" / 30 ngày", " / 30 days"), 11.5f, Ui.MUTED, false), Ui.fill());
            view.addView(more, Ui.fill());
        }

        void setOn(boolean on) {
            bg.setStroke(on ? Ui.dp(2.5f) : Math.max(1, Ui.dp(1)), on ? acc : a(90, acc));
            ck.setVisibility(on ? View.VISIBLE : View.GONE);
            more.setVisibility(on ? View.VISIBLE : View.GONE);
            view.setElevation(on ? Ui.dp(6) : 0);
            view.setSelected(on);
        }
    }
}
