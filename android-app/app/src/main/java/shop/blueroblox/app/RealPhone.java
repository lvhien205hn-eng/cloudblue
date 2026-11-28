package shop.blueroblox.app;

import android.app.Dialog;
import android.text.InputFilter;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** 📱 BlueReal (28/11 · SQL v70): thuê điện thoại THẬT (Samsung Galaxy S9 / S10…) đặt tại shop — không phải giả lập. Giống web và app PC.
 *  realphone_catalog() → {name, on, max_days, models[{id, name, android, ram, cpu, res, price_day, note, stock, total}]} (stock = máy sẵn sàng).
 *  realphone_order(p_model, p_days, p_name): giá / ngày × số ngày, trừ số dư → máy chủ đang cắm máy đó giao máy (thường dưới 1 phút).
 *  realphone_renew(p_id, p_days): cộng thêm ngày, máy giữ nguyên app / dữ liệu.
 *  Máy thật = 1 dòng cloud_phones có real_device / real_model: không nâng RAM / CPU, đổi Android / máy chủ, đổi FPS, Root, Proxy,
 *  khởi động lại. Web chưa chạy SQL v70 → cat = null, app ẩn hết phần máy thật (chạy như cũ). */
final class RealPhone {
    private RealPhone() { }

    static volatile JSONObject cat = null;
    static volatile long at = 0;
    static final int[] DAYS = {1, 3, 7, 15, 30};

    interface Done { void run(); }

    /** Dòng máy này là máy THẬT (cột real_device của SQL v70)? */
    static boolean isReal(JSONObject p) {
        if (p == null || p.isNull("real_device")) return false;
        String d = p.optString("real_device", "").trim();
        return !d.isEmpty() && !"null".equals(d);
    }

    /** Tải danh mục ở luồng nền. Web chưa chạy SQL v70 → cat = null · lỗi mạng → giữ danh mục cũ. */
    static JSONObject fetch() {
        try {
            Object r = Api.rpc("realphone_catalog", new JSONObject());
            cat = r instanceof JSONObject ? (JSONObject) r : null;
        } catch (Exception e) {
            String m = String.valueOf(e.getMessage());
            if (m.contains("realphone_catalog") || m.contains("schema cache") || m.contains("Could not find")) cat = null;
        }
        at = System.currentTimeMillis();
        return cat;
    }

    static void load(Done done) {
        Api.bg(RealPhone::fetch, r -> { if (done != null) done.run(); }, m -> { if (done != null) done.run(); });
    }

    /** Các mẫu máy đang bán (giá / ngày > 0), đúng thứ tự admin xếp. */
    static java.util.List<JSONObject> models() {
        java.util.List<JSONObject> l = new java.util.ArrayList<>();
        JSONObject c = cat;
        JSONArray a = c == null ? null : c.optJSONArray("models");
        if (a != null) for (int i = 0; i < a.length(); i++) {
            JSONObject m = a.optJSONObject(i);
            if (m != null && m.optDouble("price_day", 0) > 0) l.add(m);
        }
        return l;
    }

    /** Hiện thẻ BlueReal ở trang Thuê máy: admin bật bán + có ≥ 1 mẫu có giá. */
    static boolean on() { JSONObject c = cat; return c != null && c.optBoolean("on", true) && !models().isEmpty(); }

    static String name() {
        JSONObject c = cat;
        String n = c == null ? "" : c.optString("name", "").trim();
        return n.isEmpty() || "null".equals(n) ? "BlueReal" : n;
    }

    static int maxDays() {
        JSONObject c = cat;
        int m = c == null ? 90 : c.optInt("max_days", 90);
        return Math.max(1, Math.min(90, m <= 0 ? 90 : m));
    }

    static double lowDay() {
        double lo = 0;
        for (JSONObject m : models()) { double v = m.optDouble("price_day", 0); if (lo == 0 || v < lo) lo = v; }
        return lo;
    }

    static int stock() { int n = 0; for (JSONObject m : models()) n += Math.max(0, m.optInt("stock", 0)); return n; }

    static JSONObject model(String id) {
        JSONObject c = cat;
        JSONArray a = c == null ? null : c.optJSONArray("models");
        if (a != null && id != null) for (int i = 0; i < a.length(); i++) {
            JSONObject m = a.optJSONObject(i);
            if (m != null && id.equals(m.optString("id"))) return m;
        }
        return null;
    }

    static String mName(String id) {
        JSONObject m = model(id);
        String n = m == null ? "" : m.optString("name", "").trim();
        if (!n.isEmpty() && !"null".equals(n)) return n;
        return id == null || id.trim().isEmpty() || "null".equals(id) ? Ui.L("Máy thật", "Real phone") : id.toUpperCase(java.util.Locale.ROOT);
    }

    /** "📱 Máy thật · Galaxy S10" */
    static String tag(JSONObject p) { return "📱 " + Ui.L("Máy thật", "Real phone") + " · " + mName(p.optString("real_model", "")); }

    /** Dòng thông tin ở thẻ máy / màn điều khiển: "📱 Máy thật · Galaxy S10 · Android 12 · 8GB RAM". */
    static String info(JSONObject p) {
        String av = p.optString("android", "").trim();
        return tag(p) + (av.isEmpty() || "null".equals(av) ? "" : " · Android " + av) + " · " + p.optInt("ram") + "GB RAM";
    }

    static String desc() {
        return Ui.L("Điện thoại Samsung THẬT đặt tại shop — không phải giả lập: chạy game / app y như máy thật, điều khiển bằng app này, web hoặc app PC.",
                "A REAL Samsung phone hosted at our shop — not an emulator. Games and apps run like on a real phone; control it from this app, the web or the PC app.");
    }

    static String pendingNote() {
        return Ui.L("Đang chuẩn bị máy thật (đánh thức, mở khoá) — thường dưới 1 phút. Trang tự cập nhật.",
                "Getting your real phone ready (waking it, unlocking) — usually under a minute. This page updates by itself.");
    }

    static String limitsNote() {
        return Ui.L("📱 Máy thật: không nâng RAM / CPU, đổi Android / máy chủ, đổi FPS, Root, Proxy hay khởi động lại được.",
                "📱 Real phone: no RAM / CPU upgrade, Android / server switch, FPS change, Root, Proxy or restart.");
    }

    private static String soon() { return Ui.L("Tính năng đang cập nhật — thử lại sau ít phút.", "Coming soon — try again in a few minutes."); }

    private static JSONObject pick(java.util.List<JSONObject> ms, String id) {
        for (JSONObject m : ms) if (m.optString("id").equals(id)) return m;
        return ms.get(0);
    }

    private static String left(int s) { return s > 0 ? Ui.L("còn " + s + " máy", s + " left") : Ui.L("hết máy", "sold out"); }

    // ---------------------------------------------------------------- thẻ ở trang Thuê máy
    /** Thẻ "📱 BlueReal" ở trang Thuê máy (MainActivity.renderRent) — chỉ gọi khi on(). */
    static View card(MainActivity a) {
        LinearLayout c = Ui.card(a);
        LinearLayout r1 = Ui.row(a, 10);
        r1.addView(Ui.text(a, "📱 " + name(), 18, Ui.FG, true), Ui.weight(1));
        final int st = stock();
        r1.addView(Ui.pill(a, st > 0 ? Ui.L("Còn máy", "Available") : Ui.L("Hết máy", "Sold out"), st > 0 ? Ui.OK : Ui.BAD), Ui.wrap());
        c.addView(r1, Ui.fill());
        c.addView(Ui.muted(a, desc()), Ui.fill());
        for (JSONObject m : models()) {
            int s = m.optInt("stock", 0);
            c.addView(Ui.text(a, "• " + m.optString("name") + " · Android " + m.optString("android") + " · " + m.optInt("ram") + "GB — "
                    + Ui.vnd(m.optDouble("price_day", 0)) + Ui.L("/ngày", "/day") + " · " + left(s), 13.5f, s > 0 ? Ui.FG : Ui.MUTED, false), Ui.fill());
        }
        boolean ok = st > 0 || a.isAdmin();
        Button b = Ui.button(a, ok ? "📲 " + Ui.L("Thuê máy thật · từ ", "Rent a real phone · from ") + Ui.vnd(lowDay()) + Ui.L("/ngày", "/day")
                : Ui.L("Hết máy — quay lại sau ít phút", "Sold out — check back soon"), Ui.PRIMARY);
        b.setEnabled(ok);
        b.setAlpha(ok ? 1f : .45f);
        b.setOnClickListener(v -> order(a, null));
        c.addView(b, Ui.fill());
        return c;
    }

    // ---------------------------------------------------------------- thuê
    /** Mở hộp thuê máy thật: tải lại danh mục + số dư rồi mới hiện (còn máy / giá luôn mới). pre = mã mẫu máy chọn sẵn (null = tự chọn). */
    static void order(MainActivity a, String pre) {
        Ui.toast(a, Ui.L("Đang tải mẫu máy…", "Loading models…"));
        Api.bg(() -> { fetch(); return Api.profile(); }, prof -> { if (!a.isFinishing()) orderSheet(a, pre, prof); }, m -> Ui.toast(a, m));
    }

    private static void orderSheet(MainActivity a, String pre, JSONObject prof) {
        final java.util.List<JSONObject> ms = models();
        if (ms.isEmpty()) {
            Ui.toast(a, cat == null ? soon() : Ui.L("Chưa có mẫu máy thật nào mở bán — quay lại sau nhé.", "No real phone models are for sale yet."));
            return;
        }
        final boolean admin = "admin".equals(prof.optString("role")) || a.isAdmin();
        final int mx = maxDays();
        final double bal = prof.optDouble("balance", 0);
        final String[] sel = {null};
        for (JSONObject m : ms) if (m.optString("id").equals(pre) && m.optInt("stock", 0) > 0) sel[0] = pre;
        if (sel[0] == null) for (JSONObject m : ms) if (m.optInt("stock", 0) > 0) { sel[0] = m.optString("id"); break; }
        if (sel[0] == null) sel[0] = ms.get(0).optString("id");
        final int[] days = {Math.min(7, mx)};
        final boolean[] busy = {false};

        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, desc()), Ui.fill());
        c.addView(Ui.text(a, Ui.L("Mẫu máy", "Model"), 14, Ui.FG, true), Ui.fill());
        final Ui.Wrap wm = new Ui.Wrap(a, 8);
        c.addView(wm, Ui.fill());
        final TextView note = Ui.muted(a, "");
        c.addView(note, Ui.fill());
        c.addView(Ui.text(a, Ui.L("Số ngày", "Days"), 14, Ui.FG, true), Ui.fill());
        final Ui.Wrap wd = new Ui.Wrap(a, 8);
        c.addView(wd, Ui.fill());
        final EditText dx = Ui.input(a, Ui.L("Hoặc tự nhập số ngày (1–" + mx + ")", "Or type days (1–" + mx + ")"), InputType.TYPE_CLASS_NUMBER);
        c.addView(dx, Ui.fill());
        final EditText nm = Ui.input(a, Ui.L("Tên máy (tuỳ chọn)", "Phone name (optional)"), InputType.TYPE_CLASS_TEXT);
        nm.setFilters(new InputFilter[]{new InputFilter.LengthFilter(40)});
        c.addView(nm, Ui.fill());
        final TextView sum = Ui.text(a, "", 14, Ui.FG, false);
        LinearLayout sb = Ui.card(a);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        final TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        final Button go = Ui.button(a, "", Ui.PRIMARY);
        c.addView(go, Ui.fill());

        final Runnable draw = () -> {
            JSONObject md = pick(ms, sel[0]);
            for (int i = 0; i < wm.getChildCount(); i++) Ui.setChip((TextView) wm.getChildAt(i), sel[0].equals(wm.getChildAt(i).getTag()));
            for (int i = 0; i < wd.getChildCount(); i++) Ui.setChip((TextView) wd.getChildAt(i), (int) wd.getChildAt(i).getTag() == days[0]);
            String n = md.optString("note", "").trim();
            boolean hasNote = !n.isEmpty() && !"null".equals(n);
            note.setText(hasNote ? n : "");
            note.setVisibility(hasNote ? View.VISIBLE : View.GONE);
            double per = md.optDouble("price_day", 0), tot = per * days[0];
            boolean out = md.optInt("stock", 0) <= 0 && !admin;
            sum.setText(md.optString("name") + " · " + Ui.vnd(per) + Ui.L(" / ngày × ", " / day × ") + days[0] + Ui.L(" ngày", " days")
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(tot)
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal) + (bal < tot ? Ui.L(" · thiếu ", " · short ") + Ui.vnd(tot - bal) : "")
                    + "\n" + Ui.L("Hạn tính từ lúc máy giao cho bạn (thường dưới 1 phút).", "Time starts when the phone is handed to you (usually under a minute)."));
            go.setText(busy[0] ? Ui.L("Đang thuê…", "Renting…") : out ? Ui.L("Mẫu này đang hết máy", "This model is sold out")
                    : bal < tot ? Ui.L("Nạp thêm tiền", "Top up") : Ui.L("Thuê ngay · ", "Rent now · ") + Ui.vnd(tot));
            boolean can = !busy[0] && !out;
            go.setEnabled(can);
            go.setAlpha(can ? 1f : .45f);
        };
        for (JSONObject m : ms) {
            int s = m.optInt("stock", 0);
            TextView ch = Ui.chip(a, m.optString("name") + "\nAndroid " + m.optString("android") + " · " + m.optInt("ram") + "GB · "
                    + Ui.vnd(m.optDouble("price_day", 0)) + Ui.L("/ngày", "/day") + " · " + left(s), false);
            ch.setTextSize(Ui.sp(13));
            ch.setTag(m.optString("id"));
            boolean en = s > 0 || admin;
            ch.setEnabled(en);
            ch.setAlpha(en ? 1f : .45f);
            ch.setOnClickListener(v -> { if (busy[0]) return; sel[0] = (String) v.getTag(); err.setVisibility(View.GONE); draw.run(); });
            wm.addView(ch);
        }
        for (int d : DAYS) {
            if (d > mx) continue;
            TextView ch = Ui.chip(a, d + Ui.L(" ngày", "d"), false);
            ch.setTag(d);
            ch.setOnClickListener(v -> { if (busy[0]) return; days[0] = (int) v.getTag(); dx.setText(""); draw.run(); });
            wd.addView(ch);
        }
        dx.addTextChangedListener(new MainActivity.Simple(() -> {
            try { int v = Integer.parseInt(dx.getText().toString().trim()); if (v >= 1 && v <= mx && !busy[0]) { days[0] = v; draw.run(); } } catch (Exception ignored) { }
        }));
        final Dialog d = Ui.sheet(a, "📲 " + Ui.L("Thuê máy thật · ", "Rent a real phone · ") + name(), c);
        go.setOnClickListener(v -> {
            if (busy[0]) return;
            final JSONObject md = pick(ms, sel[0]);
            final double tot = md.optDouble("price_day", 0) * days[0];
            if (bal < tot) { d.dismiss(); a.openTopup(tot - bal); return; }
            final String mid = sel[0], nmv = nm.getText().toString().trim();
            final int dd = days[0];
            busy[0] = true;
            err.setVisibility(View.GONE);
            draw.run();
            Api.bg(() -> Api.rpc("realphone_order", new JSONObject().put("p_model", mid).put("p_days", dd).put("p_name", nmv.isEmpty() ? JSONObject.NULL : nmv)), r -> {
                busy[0] = false;
                try { d.dismiss(); } catch (Exception ignored) { }
                Ui.toast(a, Ui.L("Đã thuê " + md.optString("name") + " · " + dd + " ngày — máy đang được chuẩn bị (thường dưới 1 phút).",
                        "Rented " + md.optString("name") + " for " + dd + " days — getting it ready (usually under a minute)."));
                load(null);
                a.afterRealBuy();
            }, m -> {
                busy[0] = false;
                err.setText(m);
                err.setVisibility(View.VISIBLE);
                draw.run();
            });
        });
        draw.run();
        d.show();
    }

    // ---------------------------------------------------------------- gia hạn
    /** Gia hạn máy thật: số ngày × giá / ngày HIỆN TẠI của mẫu máy (realphone_renew) — máy giữ nguyên app, dữ liệu. */
    static void renew(MainActivity a, JSONObject p) {
        Api.bg(() -> { fetch(); return Api.profile(); }, prof -> { if (!a.isFinishing()) renewSheet(a, p, prof); }, m -> Ui.toast(a, m));
    }

    private static void renewSheet(MainActivity a, JSONObject p, JSONObject prof) {
        JSONObject md = model(p.optString("real_model", ""));
        final double per = md == null ? 0 : md.optDouble("price_day", 0);
        if (per <= 0) {
            Ui.toast(a, cat == null ? soon() : Ui.L("Mẫu máy này tạm ngừng gia hạn — nhắn shop.", "This model can't be renewed right now — contact support."));
            return;
        }
        final int mx = maxDays();
        final double bal = prof.optDouble("balance", 0);
        final int[] days = {Math.min(7, mx)};
        final boolean[] busy = {false};
        final long exp = MainActivity.parseTime(p.optString("expires_at"));

        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, tag(p) + (exp > 0 ? " · " + MainActivity.left(exp) : "")), Ui.fill());
        final Ui.Wrap wd = new Ui.Wrap(a, 8);
        c.addView(wd, Ui.fill());
        final EditText dx = Ui.input(a, Ui.L("Hoặc tự nhập số ngày (1–" + mx + ")", "Or type days (1–" + mx + ")"), InputType.TYPE_CLASS_NUMBER);
        c.addView(dx, Ui.fill());
        final TextView sum = Ui.text(a, "", 14, Ui.FG, false);
        LinearLayout sb = Ui.card(a);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        final TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        final Button go = Ui.button(a, "", Ui.PRIMARY);
        c.addView(go, Ui.fill());

        final Runnable draw = () -> {
            for (int i = 0; i < wd.getChildCount(); i++) Ui.setChip((TextView) wd.getChildAt(i), (int) wd.getChildAt(i).getTag() == days[0]);
            double tot = per * days[0];
            long base = Math.max(System.currentTimeMillis(), exp);
            sum.setText(Ui.vnd(per) + Ui.L(" / ngày × ", " / day × ") + days[0] + Ui.L(" ngày", " days")
                    + "\n" + Ui.L("Hạn mới: ", "New expiry: ") + MainActivity.fdate(base + days[0] * 86400000L)
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal) + (bal < tot ? Ui.L(" · thiếu ", " · short ") + Ui.vnd(tot - bal) : "")
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(tot)
                    + "\n" + Ui.L("Cộng thêm vào hạn đang có — máy giữ nguyên app, dữ liệu.", "Added to the current expiry — apps and data are kept."));
            go.setText(busy[0] ? Ui.L("Đang gia hạn…", "Renewing…") : bal < tot ? Ui.L("Nạp thêm tiền", "Top up")
                    : Ui.L("Gia hạn " + days[0] + " ngày · ", "Renew " + days[0] + " days · ") + Ui.vnd(tot));
            go.setEnabled(!busy[0]);
            go.setAlpha(busy[0] ? .45f : 1f);
        };
        for (int d : DAYS) {
            if (d > mx) continue;
            TextView ch = Ui.chip(a, d + Ui.L(" ngày", "d"), false);
            ch.setTag(d);
            ch.setOnClickListener(v -> { if (busy[0]) return; days[0] = (int) v.getTag(); dx.setText(""); draw.run(); });
            wd.addView(ch);
        }
        dx.addTextChangedListener(new MainActivity.Simple(() -> {
            try { int v = Integer.parseInt(dx.getText().toString().trim()); if (v >= 1 && v <= mx && !busy[0]) { days[0] = v; draw.run(); } } catch (Exception ignored) { }
        }));
        final Dialog d = Ui.sheet(a, "🔄 " + Ui.L("Gia hạn máy thật — ", "Renew real phone — ") + p.optString("name"), c);
        go.setOnClickListener(v -> {
            if (busy[0]) return;
            final double tot = per * days[0];
            if (bal < tot) { d.dismiss(); a.openTopup(tot - bal); return; }
            final int dd = days[0];
            busy[0] = true;
            err.setVisibility(View.GONE);
            draw.run();
            Api.bg(() -> Api.rpc("realphone_renew", new JSONObject().put("p_id", p.optString("id")).put("p_days", dd)), r -> {
                busy[0] = false;
                try { d.dismiss(); } catch (Exception ignored) { }
                Ui.toast(a, Ui.L("Đã gia hạn +" + dd + " ngày — máy chủ ghi hạn mới trong ít giây.", "Renewed +" + dd + " days — the new expiry shows in a few seconds."));
                a.reloadSoon();
            }, m -> {
                busy[0] = false;
                err.setText(m);
                err.setVisibility(View.VISIBLE);
                draw.run();
            });
        });
        draw.run();
        d.show();
    }

    // ---------------------------------------------------------------- trả máy sớm
    /** Trả máy thật sớm (cloudphone_cancel): máy chủ dọn máy (gỡ app khách cài, xoá ảnh / file) rồi trả lại cửa hàng. Không hoàn tiền. */
    static void giveBack(MainActivity a, JSONObject p) {
        Ui.confirm(a, Ui.L("Trả máy ", "Return ") + p.optString("name") + Ui.L(" sớm?", " early?"),
                Ui.L("Máy thật sẽ được trả lại cửa hàng: app bạn đã cài, tài khoản đã đăng nhập, ảnh và file trong máy đều bị XOÁ. Không hoàn tiền những ngày còn lại.",
                        "The real phone goes back to the shop: apps you installed, signed-in accounts, photos and files on it are ERASED. The remaining days are not refunded."),
                Ui.L("Trả máy", "Return it"), () -> Api.bg(() -> Api.rpc("cloudphone_cancel", new JSONObject().put("p_id", p.optString("id"))),
                        r -> { Ui.toast(a, Ui.L("Đang trả máy — máy sẽ biến mất khỏi danh sách trong ít phút.", "Returning — it will disappear from your list shortly.")); a.reloadSoon(); },
                        m -> Ui.toast(a, m)));
    }
}
