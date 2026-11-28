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
 *  realphone_order(p_model, p_days, p_name[, p_promo, p_blue, p_qty]): giá / ngày × số ngày × số máy (giá CTV, mã giảm giá, 💎 Blue — SQL v71),
 *  trừ số dư → máy chủ đang cắm máy đó giao máy (thường dưới 1 phút). realphone_promo_check: kiểm mã cho đơn máy thật.
 *  realphone_renew(p_id, p_days[, p_promo, p_blue]): cộng thêm ngày, máy giữ nguyên app / dữ liệu.
 *  Máy thật = 1 dòng cloud_phones có real_device / real_model: không nâng RAM / CPU, đổi Android / máy chủ, đổi FPS, Root, Proxy,
 *  khởi động lại. Web chưa chạy SQL v70 → cat = null, app ẩn hết phần máy thật (chạy như cũ). */
final class RealPhone {
    private RealPhone() { }

    static volatile JSONObject cat = null;
    static volatile long at = 0;
    static final int[] DAYS = {1, 3, 7, 15, 30}, QTY = {1, 2, 3, 5, 10};

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

    /** Hộp thuê y hệt trang thuê ĐT đám mây (28/11f): ① mẫu máy · ② số ngày & số máy · 🏷️ mã giảm giá + 💎 trả bằng Blue · khung tổng tiền
     *  (giá CTV, giảm giá, Blue, số dư) · hỏi xác nhận rồi mới trừ tiền. Mã giảm giá kiểm bằng realphone_promo_check (giá theo mẫu máy). */
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
        final int[] days = {Math.min(7, mx)}, qty = {1}, qmx = {0};
        final boolean[] busy = {false};
        final String[] se = {""};                         // lỗi máy chủ trả về (xoá khi khách đổi đơn)
        final Promo[] pr = new Promo[1];                  // 🏷️ mã giảm giá · 💎 trả bằng Blue (như trang thuê ĐT đám mây)
        final Blue.Pay[] bp = new Blue.Pay[1];
        final Runnable[] draw = new Runnable[1];

        LinearLayout c = Ui.col(a, 12);
        // ① Chọn mẫu máy
        LinearLayout s1 = Ui.col(a, 10);
        s1.addView(a.stepHead("1", Ui.L("Chọn mẫu máy", "Choose a model"), desc()), Ui.fill());
        final Ui.Wrap wm = new Ui.Wrap(a, 8);
        s1.addView(wm, Ui.fill());
        final TextView note = Ui.muted(a, "");
        s1.addView(note, Ui.fill());
        c.addView(a.boxed(s1), Ui.fill());
        // ② Số ngày & số máy
        LinearLayout s2 = Ui.col(a, 14);
        s2.addView(a.stepHead("2", Ui.L("Số ngày & số máy", "Days & phones"), ""), Ui.fill());
        s2.addView(a.group(Ui.L("Số ngày", "Days"), DAYS, 1, mx, Ui.L(" ngày", "d"), v -> { days[0] = v; se[0] = ""; draw[0].run(); }, () -> days[0]), Ui.fill());
        final LinearLayout qb = Ui.col(a, 0);            // số máy: tối đa = số máy rảnh của mẫu đang chọn (≤ 10) → vẽ lại khi đổi mẫu
        s2.addView(qb, Ui.fill());
        final EditText nm = Ui.input(a, Ui.L("Tên máy (tuỳ chọn)", "Phone name (optional)"), InputType.TYPE_CLASS_TEXT);
        nm.setFilters(new InputFilter[]{new InputFilter.LengthFilter(40)});
        s2.addView(nm, Ui.fill());
        c.addView(a.boxed(s2), Ui.fill());
        // 🏷️ Mã giảm giá + 💎 Trả bằng Blue
        if (Api.SHOP) {
            pr[0] = new Promo(a, "cp_new", () -> new JSONObject().put("p_model", sel[0]).put("p_days", days[0]).put("p_qty", qty[0]), () -> draw[0].run())
                    .rpc("realphone_promo_check");
            bp[0] = new Blue.Pay(a, false, () -> draw[0].run());
            LinearLayout pz = Ui.col(a, 10);
            pz.addView(pr[0].view, Ui.fill());
            pz.addView(bp[0].view, Ui.fill());
            c.addView(a.boxed(pz), Ui.fill());
        }
        // Khung tổng tiền
        final TextView sumL = Ui.text(a, "", 12, Ui.MUTED, true);
        final TextView total = Ui.text(a, "", 22, Ui.MONEY, true);
        final TextView calc = Ui.text(a, "", 11.5f, Ui.MUTED, false);
        LinearLayout sb = Ui.card(a);
        sb.addView(sumL);
        sb.addView(total);
        sb.addView(calc);
        sb.addView(Ui.muted(a, Ui.L("Hạn tính từ lúc máy giao cho bạn (thường dưới 1 phút). Hết hạn máy tạm dừng; không gia hạn trong 30 phút thì app + dữ liệu của bạn bị xoá, máy về lại shop.",
                "Time starts when the phone is handed to you (usually under a minute). When it expires it pauses; if not renewed within 30 minutes your apps and data are wiped.")));
        c.addView(sb, Ui.fill());
        final TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        final Button go = Ui.button(a, "", Ui.PRIMARY);
        c.addView(go, Ui.fill());

        final Runnable fillQty = () -> {
            JSONObject md = pick(ms, sel[0]);
            int m = admin ? 10 : Math.max(1, Math.min(10, md.optInt("stock", 0)));
            if (m == qmx[0]) return;
            qmx[0] = m;
            if (qty[0] > m) qty[0] = m;
            qb.removeAllViews();
            if (m > 1) qb.addView(a.group(Ui.L("Số lượng máy (cùng mẫu)", "Phones (same model)"), QTY, 1, m, Ui.L(" máy", ""), v -> { qty[0] = v; se[0] = ""; draw[0].run(); }, () -> qty[0]), Ui.fill());
        };
        draw[0] = () -> {
            fillQty.run();
            JSONObject md = pick(ms, sel[0]);
            for (int i = 0; i < wm.getChildCount(); i++) Ui.setChip((TextView) wm.getChildAt(i), sel[0].equals(wm.getChildAt(i).getTag()));
            String n = md.optString("note", "").trim();
            boolean hasNote = !n.isEmpty() && !"null".equals(n);
            note.setText(hasNote ? n : "");
            note.setVisibility(hasNote ? View.VISIBLE : View.GONE);
            double per = md.optDouble("price_day", 0), t0 = a.ctv(per * days[0] * qty[0]);
            boolean out = md.optInt("stock", 0) <= 0 && !admin;
            if (pr[0] != null) pr[0].onOrderChanged();
            double pay = pr[0] == null ? t0 : pr[0].price(t0);
            long bu = bp[0] == null ? 0 : bp[0].use(pay);
            if (bp[0] != null) bp[0].paint(pay, out);
            double t = pay - bu;
            sumL.setText(md.optString("name") + " · Android " + md.optString("android") + " · " + days[0] + Ui.L(" ngày", "d") + (qty[0] > 1 ? " × " + qty[0] + Ui.L(" máy", "") : ""));
            total.setText(Ui.vnd(t));
            calc.setText(Ui.vnd(per) + Ui.L(" / ngày × ", " / day × ") + days[0] + Ui.L(" ngày", " days") + (qty[0] > 1 ? " × " + qty[0] + Ui.L(" máy", " phones") : "")
                    + (a.isCtv() ? " − " + prof.optInt("ctv_discount") + "% CTV" : "")
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + (pay < t0 ? "  ·  🏷️ −" + Ui.vnd(t0 - pay) : "") + (bu > 0 ? "  ·  💎 −" + Blue.n(bu) + " Blue" : ""));
            String e = out ? Ui.L("Mẫu này vừa hết máy — chọn mẫu khác hoặc quay lại sau ít phút.", "This model just sold out — pick another or come back later.")
                    : !se[0].isEmpty() ? se[0] : bal < t ? Ui.L("Số dư không đủ — cần nạp thêm ", "Not enough balance — top up ") + Ui.vnd(t - bal) : "";
            err.setText(e);
            err.setVisibility(e.isEmpty() ? View.GONE : View.VISIBLE);
            go.setText(busy[0] ? Ui.L("Đang thuê…", "Renting…") : out ? Ui.L("Mẫu này đang hết máy", "This model is sold out")
                    : bal < t ? Ui.L("Nạp thêm tiền", "Top up") : t <= 0 && bu > 0 ? Ui.L("💎 Thuê bằng Blue", "💎 Rent with Blue")
                    : Ui.L("Thuê ngay", "Rent now") + (qty[0] > 1 ? " " + qty[0] + Ui.L(" máy", " phones") : "") + " · " + Ui.vnd(t));
            boolean can = !busy[0] && !out;
            go.setEnabled(can);
            go.setAlpha(can ? 1f : .45f);
        };
        for (JSONObject m : ms) {
            int s = m.optInt("stock", 0);
            TextView ch = Ui.chip(a, m.optString("name") + "\nAndroid " + m.optString("android") + " · " + m.optInt("ram") + "GB · "
                    + Ui.vnd(a.ctv(m.optDouble("price_day", 0))) + Ui.L("/ngày", "/day") + " · " + left(s), false);
            ch.setTextSize(Ui.sp(13));
            ch.setTag(m.optString("id"));
            boolean en = s > 0 || admin;
            ch.setEnabled(en);
            ch.setAlpha(en ? 1f : .45f);
            ch.setOnClickListener(v -> { if (busy[0]) return; sel[0] = (String) v.getTag(); se[0] = ""; draw[0].run(); });
            wm.addView(ch);
        }
        final Dialog d = Ui.sheet(a, "📲 " + Ui.L("Thuê điện thoại thật · ", "Rent a real phone · ") + name(), c);
        go.setOnClickListener(v -> {
            if (busy[0]) return;
            Runnable run = () -> {
                final JSONObject md = pick(ms, sel[0]);
                final int dd = days[0], qq = qty[0];
                final double t0 = a.ctv(md.optDouble("price_day", 0) * dd * qq);
                final double pay = pr[0] == null ? t0 : pr[0].price(t0);
                final long bu = bp[0] == null ? 0 : bp[0].use(pay);
                final double t = pay - bu;
                if (bal < t) { d.dismiss(); a.openTopup(t - bal); return; }
                final String code = pr[0] == null ? null : pr[0].send();
                final String mid = sel[0], nmv = nm.getText().toString().trim();
                Ui.confirm(a, Ui.L("Xác nhận thuê máy thật", "Confirm"),
                        md.optString("name") + " · Android " + md.optString("android") + " · " + qq + Ui.L(" máy · ", " phone(s) · ") + dd + Ui.L(" ngày", " days") + "\n"
                                + (code != null ? "🏷️ " + code + "  −" + Ui.vnd(t0 - pay) + "\n" : "")
                                + (bu > 0 ? "💎 " + Ui.L("Trả ", "Pay ") + Blue.n(bu) + " Blue\n" : "")
                                + Ui.L("Trừ ", "Charge ") + Ui.vnd(t) + Ui.L(" từ số dư.", " from balance."),
                        Ui.L("Thanh toán", "Pay"), () -> {
                            busy[0] = true;
                            se[0] = "";
                            draw[0].run();
                            Api.bg(() -> {
                                JSONObject args = new JSONObject().put("p_model", mid).put("p_days", dd).put("p_name", nmv.isEmpty() ? JSONObject.NULL : nmv);
                                if (qq > 1) args.put("p_qty", qq);
                                if (code != null) args.put("p_promo", code);
                                if (bu > 0) args.put("p_blue", true);
                                try { return Api.rpc("realphone_order", args); }
                                catch (Exception e) { String m = String.valueOf(e.getMessage()); if (pr[0] != null && m.contains("PROMO_")) Api.ui(() -> pr[0].fail(m)); throw e; }
                            }, r -> {
                                busy[0] = false;
                                try { d.dismiss(); } catch (Exception ignored) { }
                                Ui.toast(a, Ui.L("Đã thuê " + (qq > 1 ? qq + " máy " : "") + md.optString("name") + " · " + dd + " ngày — máy đang được chuẩn bị (thường dưới 1 phút).",
                                        "Rented " + (qq > 1 ? qq + " × " : "") + md.optString("name") + " for " + dd + " days — getting it ready (usually under a minute)."));
                                Blue.at = 0;
                                load(null);
                                a.afterRealBuy();
                            }, m -> {
                                busy[0] = false;
                                se[0] = m;
                                draw[0].run();
                            });
                        });
            };
            if (pr[0] == null) run.run(); else pr[0].ensure(run);
        });
        draw[0].run();
        d.show();
    }

    // ---------------------------------------------------------------- gia hạn
    /** Gia hạn máy thật: số ngày × giá / ngày HIỆN TẠI của mẫu máy (realphone_renew) — máy giữ nguyên app, dữ liệu. */
    static void renew(MainActivity a, JSONObject p) {
        Api.bg(() -> { fetch(); return Api.profile(); }, prof -> { if (!a.isFinishing()) renewSheet(a, p, prof); }, m -> Ui.toast(a, m));
    }

    /** Hộp gia hạn như ĐT đám mây (28/11f): giá CTV · 🏷️ mã giảm giá (realphone_promo_check, cp_renew) · 💎 trả bằng Blue. */
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
        final String[] se = {""};
        final long exp = MainActivity.parseTime(p.optString("expires_at"));
        final Promo[] pr = new Promo[1];
        final Blue.Pay[] bp = new Blue.Pay[1];
        final Runnable[] draw = new Runnable[1];

        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, tag(p) + (exp > 0 ? " · " + MainActivity.left(exp) : "")), Ui.fill());
        final Ui.Wrap wd = new Ui.Wrap(a, 8);
        c.addView(wd, Ui.fill());
        final EditText dx = Ui.input(a, Ui.L("Hoặc tự nhập số ngày (1–" + mx + ")", "Or type days (1–" + mx + ")"), InputType.TYPE_CLASS_NUMBER);
        c.addView(dx, Ui.fill());
        if (Api.SHOP) {
            pr[0] = new Promo(a, "cp_renew", () -> new JSONObject().put("p_phone", p.optString("id")).put("p_days", days[0]), () -> draw[0].run())
                    .rpc("realphone_promo_check");
            bp[0] = new Blue.Pay(a, false, () -> draw[0].run());
            c.addView(pr[0].view, Ui.fill());
            c.addView(bp[0].view, Ui.fill());
        }
        final TextView sum = Ui.text(a, "", 14, Ui.FG, false);
        LinearLayout sb = Ui.card(a);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        final TextView err = Ui.text(a, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        c.addView(err, Ui.fill());
        final Button go = Ui.button(a, "", Ui.PRIMARY);
        c.addView(go, Ui.fill());

        draw[0] = () -> {
            for (int i = 0; i < wd.getChildCount(); i++) Ui.setChip((TextView) wd.getChildAt(i), (int) wd.getChildAt(i).getTag() == days[0]);
            double t0 = a.ctv(per * days[0]);
            if (pr[0] != null) pr[0].onOrderChanged();
            double pay = pr[0] == null ? t0 : pr[0].price(t0);
            long bu = bp[0] == null ? 0 : bp[0].use(pay);
            if (bp[0] != null) bp[0].paint(pay, false);
            double t = pay - bu;
            long base = Math.max(System.currentTimeMillis(), exp);
            sum.setText(Ui.L("Đơn giá: ", "Price: ") + Ui.vnd(a.ctv(per)) + Ui.L(" / ngày", " / day") + (a.isCtv() ? " (CTV −" + prof.optInt("ctv_discount") + "%)" : "")
                    + "\n" + Ui.L("Hạn mới: ", "New expiry: ") + MainActivity.fdate(base + days[0] * 86400000L)
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(t)
                    + (pay < t0 ? "  (🏷️ −" + Ui.vnd(t0 - pay) + ")" : "") + (bu > 0 ? "  (💎 −" + Blue.n(bu) + " Blue)" : "")
                    + "\n" + Ui.L("Cộng thêm vào hạn đang có — máy giữ nguyên app, dữ liệu.", "Added to the current expiry — apps and data are kept."));
            String e = !se[0].isEmpty() ? se[0] : bal < t ? Ui.L("Số dư không đủ — cần nạp thêm ", "Not enough balance — top up ") + Ui.vnd(t - bal) : "";
            err.setText(e);
            err.setVisibility(e.isEmpty() ? View.GONE : View.VISIBLE);
            go.setText(busy[0] ? Ui.L("Đang gia hạn…", "Renewing…") : bal < t ? Ui.L("Nạp thêm tiền", "Top up")
                    : t <= 0 && bu > 0 ? Ui.L("💎 Gia hạn " + days[0] + " ngày bằng Blue", "💎 Renew " + days[0] + " days with Blue")
                    : Ui.L("Gia hạn " + days[0] + " ngày · ", "Renew " + days[0] + " days · ") + Ui.vnd(t));
            go.setEnabled(!busy[0]);
            go.setAlpha(busy[0] ? .45f : 1f);
        };
        for (int d : DAYS) {
            if (d > mx) continue;
            TextView ch = Ui.chip(a, d + Ui.L(" ngày", "d"), false);
            ch.setTag(d);
            ch.setOnClickListener(v -> { if (busy[0]) return; days[0] = (int) v.getTag(); se[0] = ""; dx.setText(""); draw[0].run(); });
            wd.addView(ch);
        }
        dx.addTextChangedListener(new MainActivity.Simple(() -> {
            try { int v = Integer.parseInt(dx.getText().toString().trim()); if (v >= 1 && v <= mx && !busy[0]) { days[0] = v; se[0] = ""; draw[0].run(); } } catch (Exception ignored) { }
        }));
        final Dialog d = Ui.sheet(a, "🔄 " + Ui.L("Gia hạn máy thật — ", "Renew real phone — ") + p.optString("name"), c);
        go.setOnClickListener(v -> {
            if (busy[0]) return;
            Runnable run = () -> {
                final int dd = days[0];
                final double t0 = a.ctv(per * dd);
                final double pay = pr[0] == null ? t0 : pr[0].price(t0);
                final long bu = bp[0] == null ? 0 : bp[0].use(pay);
                final double t = pay - bu;
                if (bal < t) { d.dismiss(); a.openTopup(t - bal); return; }
                final String code = pr[0] == null ? null : pr[0].send();
                busy[0] = true;
                se[0] = "";
                draw[0].run();
                Api.bg(() -> {
                    JSONObject args = new JSONObject().put("p_id", p.optString("id")).put("p_days", dd);
                    if (code != null) args.put("p_promo", code);
                    if (bu > 0) args.put("p_blue", true);
                    try { return Api.rpc("realphone_renew", args); }
                    catch (Exception e) { String m = String.valueOf(e.getMessage()); if (pr[0] != null && m.contains("PROMO_")) Api.ui(() -> pr[0].fail(m)); throw e; }
                }, r -> {
                    busy[0] = false;
                    try { d.dismiss(); } catch (Exception ignored) { }
                    Ui.toast(a, Ui.L("Đã gia hạn +" + dd + " ngày — máy chủ ghi hạn mới trong ít giây.", "Renewed +" + dd + " days — the new expiry shows in a few seconds."));
                    Blue.at = 0;
                    a.reloadSoon();
                }, m -> {
                    busy[0] = false;
                    se[0] = m;
                    draw[0].run();
                });
            };
            if (pr[0] == null) run.run(); else pr[0].ensure(run);
        });
        draw[0].run();
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
