package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** 🤖 Đổi Android 9 / 12 / 15 cho máy đang thuê (SQL v24 + v28: cloudphone_switch_android — v28 xoá máy cũ TRƯỚC rồi mới tạo máy mới).
 *  Máy chủ tạo 1 máy MỚI bản Android khác, giữ nguyên hạn còn lại + RAM/CPU (vượt trần bản mới thì tự hạ), miễn phí, tối đa 3 lần / 24 giờ.
 *  Máy mới chạy xong → máy cũ và TOÀN BỘ dữ liệu cũ tự xoá. Dùng chung ở danh sách máy (MainActivity) và màn điều khiển (ControlActivity). */
final class SwitchAndroid {
    private SwitchAndroid() { }

    /** Các bản Android admin đang bán (đúng thứ tự admin nhập, VD "9,12,15"). */
    static java.util.List<String> versions(JSONObject price) {
        java.util.List<String> l = new java.util.ArrayList<>();
        String s = price == null ? "9" : price.optString("android_versions", "9");
        for (String v : s.split(",")) { v = v.trim(); if (v.matches("\\d{1,2}") && !l.contains(v)) l.add(v); }
        if (l.isEmpty()) l.add("9");
        return l;
    }

    /** Trần 1 máy của bản v → {RAM GB, nhân} (giống MainActivity.andLim). */
    static int[] lim(JSONObject price, String v) {
        int r = "9".equals(v) ? 8 : 16, c = "9".equals(v) ? 8 : "7".equals(v) ? 16 : 32;
        JSONObject al = price == null ? null : price.optJSONObject("android_limits");
        JSONObject x = al == null ? null : al.optJSONObject(v);
        if (x != null) { r = x.optInt("ram", r); c = x.optInt("cpu", c); }
        int gr = price == null ? r : price.optInt("max_ram", r), gc = price == null ? c : price.optInt("max_cpu", c);
        return new int[]{Math.max(1, Math.min(Math.min(r, gr <= 0 ? r : gr), 16)), Math.max(1, Math.min(Math.min(c, gc <= 0 ? c : gc), 32))};
    }

    /** "" = còn chỗ · "off" = bản này bảo trì / chưa có máy chủ · "full" = không đủ RAM/CPU (giống MainActivity.andWhy). */
    static String why(JSONObject status, String v, int ram, int cpu, boolean admin) {
        if (admin || status == null) return "";
        JSONObject m = status.optJSONObject("android");
        if (m == null) return "";
        JSONObject a = m.optJSONObject(v);
        if (a == null || !a.optBoolean("online", true)) return "off";
        return a.optDouble("free_ram", 0) < ram || a.optDouble("free_cpu", 0) < cpu ? "full" : "";
    }

    static String cur(JSONObject p) {
        String a = p.optString("android", "").trim();
        return a.isEmpty() || "null".equals(a) ? "9" : a;
    }

    /** Máy p đang đổi Android? → trả về dòng máy MỚI đang tạo (null = không đổi). */
    static JSONObject switching(JSONObject p, JSONArray phones) {
        String to = p == null ? "" : p.optString("switch_to", "");
        if (to.isEmpty() || "null".equals(to) || phones == null) return null;
        for (int i = 0; i < phones.length(); i++) {
            JSONObject x = phones.optJSONObject(i);
            if (x != null && to.equals(x.optString("id")) && ("pending".equals(x.optString("status")) || "creating".equals(x.optString("status")))) return x;
        }
        return null;
    }

    /** Dòng máy mới sinh ra từ lệnh đổi Android (đang tạo). */
    static boolean isNewFromSwitch(JSONObject p) {
        String r = p.optString("replaces", "");
        return !r.isEmpty() && !"null".equals(r) && ("pending".equals(p.optString("status")) || "creating".equals(p.optString("status")));
    }

    /** Dòng chữ cho máy MỚI của lệnh đổi Android (SQL v28: máy cũ bị xoá TRƯỚC, xoá xong mới tạo máy mới). */
    static String newNote(JSONObject p, JSONArray phones) {
        String v = cur(p), old = p.optString("replaces", "");
        if (phones != null) for (int i = 0; i < phones.length(); i++) {        // đổi kiểu cũ (trước v28): máy cũ còn chạy song song
            JSONObject x = phones.optJSONObject(i);
            if (x != null && old.equals(x.optString("id")) && ("active".equals(x.optString("status")) || "expired".equals(x.optString("status"))))
                return Ui.L("Máy mới đổi sang Android " + v + " — đang tạo (2–5 phút). Xong thì máy cũ và dữ liệu cũ tự xoá.",
                        "New Android " + v + " phone — being created (2–5 min). The old phone and its data are then removed.");
        }
        if ("wait-old".equals(p.optString("node")))
            return Ui.L("Đang xoá máy cũ… xoá xong tự tạo máy Android " + v + " (2–5 phút).",
                    "Deleting the old phone… the Android " + v + " phone is created right after (2–5 min).");
        String e = p.optString("error", "");
        return Ui.L("Máy cũ đã xoá — đang tạo máy Android " + v + " (2–5 phút).", "Old phone deleted — creating the Android " + v + " phone (2–5 min).")
                + (e.startsWith("Đổi Android:") ? "\n" + e : "");
    }

    /** Ghi chú lỗi đổi Android còn lưu trên máy cũ (máy vẫn chạy) — null nếu không có. */
    static String failNote(JSONObject p) {
        String e = p.optString("error", "");
        return "active".equals(p.optString("status")) && e.startsWith("Đổi Android") ? e : null;
    }

    /** Mở hộp thoại đổi Android. done chạy sau khi máy chủ nhận lệnh (tải lại danh sách / rời màn điều khiển). */
    static void open(Activity a, JSONObject p, JSONObject price, JSONObject status, boolean admin, Runnable done) {
        final String now = cur(p), pid = p.optString("id");
        final int R0 = p.optInt("ram"), C0 = p.optInt("cpu");
        final String[] sel = {null};
        java.util.List<String> vs = versions(price);
        vs.remove(now);

        LinearLayout c = Ui.col(a, 12);
        long exp = MainActivity.parseTime(p.optString("expires_at"));
        c.addView(Ui.muted(a, Ui.L("Đang chạy: Android ", "Now: Android ") + now + " · " + R0 + "GB · " + C0 + Ui.L(" nhân", " cores")
                + (exp > 0 ? " · " + MainActivity.left(exp) : "")));
        if (vs.isEmpty()) {
            c.addView(Ui.text(a, Ui.L("Hiện chưa có bản Android nào khác để đổi.", "No other Android version is available right now."), 14, Ui.FG, false));
            Ui.sheet(a, "🤖 " + Ui.L("Đổi Android", "Switch Android"), c).show();
            return;
        }
        c.addView(Ui.text(a, Ui.L("Chọn bản Android mới", "Pick the new Android version"), 14, Ui.FG, true));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        c.addView(w, Ui.fill());
        TextView note = Ui.text(a, "", 13.5f, Ui.FG, false);
        LinearLayout nb = Ui.card(a);
        nb.addView(note, Ui.fill());
        c.addView(nb, Ui.fill());

        // Cảnh báo mất dữ liệu: viền đỏ, chữ đỏ
        LinearLayout warn = Ui.col(a, 6);
        warn.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(12));
        warn.setBackground(Ui.round(Color.argb(28, 255, 107, 129), 14, Color.argb(170, 255, 107, 129)));
        warn.addView(Ui.text(a, "⚠️ " + Ui.L("Đổi Android = máy MỚI, mất sạch dữ liệu", "Switching Android = a NEW phone, all data is lost"), 15, Ui.BAD, true));
        warn.addView(Ui.text(a, Ui.L("Bấm Đổi là máy cũ bị XOÁ NGAY cùng TOÀN BỘ dữ liệu trong máy (app đã cài, tài khoản, game đã đăng nhập, ảnh, tệp) — không mở được nữa, không khôi phục được. Xoá xong mới tạo máy mới. Hãy sao lưu / ghi lại tài khoản trước khi đổi.",
                "The old phone and ALL its data (installed apps, accounts, logged-in games, photos, files) are DELETED RIGHT AWAY — it can't be opened any more and can't be recovered. The new phone is created after that. Back up / note your accounts first."), 13.5f, Ui.BAD, false));
        c.addView(warn, Ui.fill());
        CheckBox ok = new CheckBox(a);
        ok.setText(Ui.L("Tôi hiểu, toàn bộ dữ liệu trong máy sẽ bị xoá", "I understand all data on this phone will be erased"));
        ok.setTextColor(Ui.FG);
        ok.setTextSize(14);
        ok.setButtonTintList(ColorStateList.valueOf(Ui.BAD));
        c.addView(ok, Ui.fill());
        c.addView(Ui.muted(a, Ui.L("Miễn phí · giữ nguyên hạn còn lại · tối đa 3 lần / 24 giờ. Máy mới có sau khoảng 2–5 phút.",
                "Free · keeps the remaining time · up to 3 times / 24 hours. The new phone is ready in about 2–5 minutes.")));
        TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        Button go = Ui.button(a, Ui.L("Chọn bản Android", "Pick a version"), Ui.DANGER);
        c.addView(go, Ui.fill());

        Runnable draw = () -> {
            for (int i = 0; i < w.getChildCount(); i++) {
                TextView ch = (TextView) w.getChildAt(i);
                String v = (String) ch.getTag();
                int[] l = lim(price, v);
                String y = why(status, v, Math.min(R0, l[0]), Math.min(C0, l[1]), admin);
                ch.setText("Android " + v + "\n" + ("off".equals(y) ? Ui.L("Bảo trì", "Unavailable") : "full".equals(y) ? Ui.L("Hết chỗ", "Full") : MainActivity.andHint(v)));
                Ui.setChip(ch, v.equals(sel[0]));
                ch.setEnabled(y.isEmpty());
                ch.setAlpha(y.isEmpty() ? 1f : .4f);
            }
            if (sel[0] == null) {
                note.setText(Ui.L("Máy mới giữ nguyên RAM, CPU, độ phân giải, FPS và hạn còn lại.", "The new phone keeps RAM, CPU, resolution, FPS and the remaining time."));
            } else {
                int[] l = lim(price, sel[0]);
                int nr = Math.min(R0, l[0]), nc = Math.min(C0, l[1]);
                StringBuilder s = new StringBuilder();
                s.append(Ui.L("Máy mới: Android ", "New phone: Android ")).append(sel[0]).append(" · ").append(nr).append("GB · ").append(nc).append(Ui.L(" nhân", " cores"))
                        .append(exp > 0 ? Ui.L(" · hạn đến ", " · until ") + MainActivity.fdate(exp) : "");
                if (nr < R0 || nc < C0)
                    s.append("\n").append(Ui.L("Android " + sel[0] + " tối đa " + l[0] + "GB · " + l[1] + " nhân mỗi máy → máy mới tự hạ còn " + nr + "GB · " + nc + " nhân (không hoàn tiền phần chênh).",
                            "Android " + sel[0] + " allows up to " + l[0] + "GB · " + l[1] + " cores per phone → the new phone is reduced to " + nr + "GB · " + nc + " cores (no refund for the difference)."));
                if ("15".equals(sel[0]))
                    s.append("\n").append(Ui.L("💡 Android 15 có máy chưa vào được Google / Play Store — cần Google thì chọn Android 12.",
                            "💡 Google / Play Store may not work on Android 15 — pick Android 12 if you need Google."));
                note.setText(s.toString());
            }
            boolean can = sel[0] != null && ok.isChecked();
            go.setText(sel[0] == null ? Ui.L("Chọn bản Android", "Pick a version") : Ui.L("Đổi sang Android ", "Switch to Android ") + sel[0]);
            go.setEnabled(can);
            go.setAlpha(can ? 1f : .45f);
        };
        for (String v : vs) {
            TextView ch = Ui.chip(a, "Android " + v, false);
            ch.setTextSize(13);
            ch.setTag(v);
            ch.setOnClickListener(x -> { sel[0] = (String) x.getTag(); err.setVisibility(View.GONE); draw.run(); });
            w.addView(ch);
        }
        ok.setOnCheckedChangeListener((b, on) -> draw.run());
        Dialog d = Ui.sheet(a, "🤖 " + Ui.L("Đổi Android — ", "Switch Android — ") + p.optString("name"), c);
        go.setOnClickListener(v -> {
            if (sel[0] == null || !ok.isChecked()) return;
            final String to = sel[0];
            go.setEnabled(false);
            go.setText(Ui.L("Đang gửi lệnh…", "Sending…"));
            Api.bg(() -> Api.rpc("cloudphone_switch_android", new JSONObject().put("p_id", pid).put("p_android", to)), r -> {
                d.dismiss();
                JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                String cfg = o.optInt("ram", Math.min(R0, lim(price, to)[0])) + "GB · " + o.optInt("cpu", Math.min(C0, lim(price, to)[1]));
                Ui.toast(a, Ui.L("🤖 Đang xoá máy cũ… xoá xong tự tạo máy Android " + to + " (" + cfg + " nhân), khoảng 2–5 phút.",
                        "🤖 Deleting the old phone… then creating the Android " + to + " phone (" + cfg + " cores), about 2–5 minutes."));
                if (done != null) done.run();
            }, m -> {
                err.setText(m);
                err.setVisibility(View.VISIBLE);
                draw.run();
            });
        });
        draw.run();
        d.show();
    }
}
