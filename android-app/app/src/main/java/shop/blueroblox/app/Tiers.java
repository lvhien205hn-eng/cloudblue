package shop.blueroblox.app;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
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

    private static final String[][] DEF = {
            // id, icon, name, mô tả VI, mô tả EN, ram, cpu, fps, nhãn, màu, phù hợp VI (|), phù hợp EN (|)
            {"lite", "💬", "Blue Lite", "Treo app · nuôi acc", "Apps · account farming", "2", "2", "30", "", "blue",
                    "Zalo, Facebook, TikTok, Telegram|Chạy 24/7 kể cả khi tắt máy tính", "Zalo, Facebook, TikTok, Telegram|Runs 24/7 even when your PC is off"},
            {"game", "🎮", "Blue Game", "Game nhẹ · treo cả ngày", "Light games · all-day idle", "4", "2", "30", "", "teal",
                    "Game 2D, nhàn rỗi, cờ, bài|Treo game nhẹ ổn định", "2D, idle, card & board games|Stable for light games"},
            {"roblox", "🕹️", "Blue Roblox", "Treo Roblox 1 tab mượt", "Smooth Roblox · 1 tab", "4", "4", "30", "🔥 Bán chạy", "amber",
                    "Roblox 1 tab, đồ hoạ thấp|Roblox dùng ~2GB RAM — vẫn còn dư", "Roblox · 1 tab, low graphics|Roblox uses ~2GB RAM — room to spare"},
            {"pro", "🚀", "Blue Pro", "Treo Roblox 2–4 tab", "Roblox · 2–4 tabs", "8", "8", "30", "⭐ Đề xuất", "violet",
                    "2–4 tab Roblox cùng lúc|Mỗi tab thêm cần ~1,5–2GB RAM", "2–4 Roblox tabs at once|Each extra tab needs ~1.5–2GB RAM"},
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
                t.id = o.optString("id", "t" + i); t.icon = o.optString("icon", "📱"); t.name = o.optString("name", "").trim();
                String vi = o.optString("vi", ""), en = o.optString("en", "");
                t.tag = Ui.L(vi, en.isEmpty() ? vi : en);
                t.ram = o.optInt("ram", 0); t.cpu = o.optInt("cpu", 0); t.fps = o.optInt("fps", 30);
                t.res = o.optString("res", ""); t.badge = o.optString("badge", ""); t.color = o.optString("color", "blue");
                JSONArray f = o.optJSONArray(Ui.L("fvi", "fen"));
                if (f == null || f.length() == 0) f = o.optJSONArray("fvi");
                if (f != null) for (int j = 0; j < f.length() && t.fit.size() < 3; j++) { String s = f.optString(j, "").trim(); if (!s.isEmpty()) t.fit.add(s); }
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

    /** 1 thẻ gói. setOn(true/false) đổi viền + nút "Đã chọn" mà không vẽ lại cả trang. */
    static final class Card {
        final LinearLayout view;
        private final TextView btn;
        private final int acc;
        private final GradientDrawable bg;

        Card(Context c, T t, double perDay, List<String> ands, List<String> busy, Runnable pick) {
            acc = color(t.color);
            view = Ui.col(c, 8);
            view.setPadding(Ui.dp(14), Ui.dp(14), Ui.dp(14), Ui.dp(13));
            bg = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{mix(acc, Ui.PANEL, Ui.LIGHT ? .16f : .26f), Ui.PANEL});
            bg.setCornerRadius(Ui.dp(18));
            view.setBackground(bg);
            view.setClickable(true);
            view.setFocusable(true);
            view.setOnClickListener(v -> pick.run());

            LinearLayout h = Ui.row(c, 8);
            TextView ic = Ui.text(c, t.icon == null || t.icon.isEmpty() ? "📱" : t.icon, 17, Ui.FG, false);
            ic.setGravity(Gravity.CENTER);
            ic.setBackground(Ui.round(Color.argb(55, Color.red(acc), Color.green(acc), Color.blue(acc)), 11, Color.argb(110, Color.red(acc), Color.green(acc), Color.blue(acc))));
            h.addView(ic, new LinearLayout.LayoutParams(Ui.dp(34), Ui.dp(34)));
            TextView nm = Ui.text(c, t.name, 18, Ui.LIGHT ? mix(acc, Color.rgb(10, 26, 58), .62f) : mix(acc, Color.WHITE, .55f), true);
            nm.setMaxLines(1);
            h.addView(nm, Ui.weight(1));
            view.addView(h, Ui.fill());
            if (t.badge != null && !t.badge.isEmpty()) {
                TextView b = Ui.text(c, t.badge, 11.5f, Color.WHITE, true);
                b.setPadding(Ui.dp(9), Ui.dp(2), Ui.dp(9), Ui.dp(3));
                GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{Color.rgb(255, 79, 109), Color.rgb(255, 154, 68)});
                g.setCornerRadius(Ui.dp(99));
                b.setBackground(g);
                LinearLayout br = Ui.row(c, 0);
                br.addView(b, Ui.wrap());
                view.addView(br, 0, Ui.wrap());              // nhãn nằm trên cùng thẻ
            }
            if (t.tag != null && !t.tag.isEmpty()) view.addView(Ui.text(c, t.tag, 12.5f, Ui.MUTED, false), Ui.fill());

            LinearLayout sp = Ui.row(c, 4);
            String[][] S = {{"⚙️", String.valueOf(t.cpu), Ui.L("nhân", "cores")}, {"🧠", t.ram + "GB", "RAM"}, {"🎞️", String.valueOf(t.fps), "FPS"}};
            for (String[] s : S) {
                LinearLayout k = Ui.col(c, 0);
                k.setGravity(Gravity.CENTER_HORIZONTAL);
                TextView e = Ui.text(c, s[0], 13, Ui.FG, false); e.setGravity(Gravity.CENTER);
                e.setBackground(Ui.round(Ui.LIGHT ? Color.argb(14, 10, 26, 58) : Color.argb(20, 255, 255, 255), 99, 0));
                k.addView(e, new LinearLayout.LayoutParams(Ui.dp(28), Ui.dp(28)));
                TextView v = Ui.text(c, s[1], 14.5f, Ui.FG, true); v.setGravity(Gravity.CENTER);
                k.addView(v, Ui.fill());
                TextView l = Ui.text(c, s[2], 11.5f, Ui.MUTED, false); l.setGravity(Gravity.CENTER);
                k.addView(l, Ui.fill());
                sp.addView(k, Ui.weight(1));
            }
            view.addView(sp, Ui.fill());

            View line = new View(c);
            line.setBackgroundColor(Color.argb(60, Color.red(acc), Color.green(acc), Color.blue(acc)));
            view.addView(line, new LinearLayout.LayoutParams(-1, Math.max(1, Ui.dp(1))));
            StringBuilder an = new StringBuilder();
            for (String v : ands) an.append(an.length() == 0 ? "" : " · ").append(v).append(busy.contains(v) ? Ui.L(" (hết chỗ)", " (full)") : "");
            view.addView(Ui.text(c, "Android  " + (an.length() == 0 ? Ui.L("vượt trần cấu hình", "over the limit") : an.toString()), 12, Ui.FG, true), Ui.fill());
            for (String f : t.fit) {
                TextView ft = Ui.text(c, "✓  " + f, 12, Ui.FG, false);
                view.addView(ft, Ui.fill());
            }
            TextView pr = Ui.text(c, Ui.vnd(perDay) + Ui.L(" / ngày", " / day"), 18, Ui.FG, true);
            view.addView(pr, Ui.fill());
            view.addView(Ui.text(c, "≈ " + Ui.vnd(perDay * 30) + Ui.L(" / 30 ngày", " / 30 days"), 11.5f, Ui.MUTED, false), Ui.fill());
            btn = Ui.text(c, "", 14, Ui.FG, true);
            btn.setGravity(Gravity.CENTER);
            btn.setPadding(Ui.dp(10), Ui.dp(10), Ui.dp(10), Ui.dp(10));
            view.addView(btn, Ui.fill());
        }

        void setOn(boolean on) {
            bg.setStroke(on ? Ui.dp(2.5f) : Math.max(1, Ui.dp(1)), on ? acc : Color.argb(95, Color.red(acc), Color.green(acc), Color.blue(acc)));
            btn.setText(on ? "✓ " + Ui.L("Đã chọn", "Selected") : Ui.L("Chọn gói này", "Choose"));
            btn.setTextColor(on ? (Ui.LIGHT ? Color.WHITE : Color.rgb(6, 17, 43)) : Ui.FG);
            btn.setBackground(Ui.round(on ? acc : (Ui.LIGHT ? Color.argb(12, 10, 26, 58) : Color.argb(16, 255, 255, 255)), 12,
                    on ? 0 : Color.argb(110, Color.red(acc), Color.green(acc), Color.blue(acc))));
            btn.setTypeface(Typeface.DEFAULT_BOLD);
        }
    }
}
