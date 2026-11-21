package shop.blueroblox.app;

import android.app.Dialog;
import android.content.Intent;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * 21/11 · VPS GPU (máy PC thật cho thuê — SQL v43): mua tự động (khách chọn bản Windows, hệ thống tự giao máy + cài),
 * danh sách "VPS GPU của bạn", cài lại / đổi Windows (giới hạn mỗi lượt thuê), gia hạn, mở màn điều khiển (ControlActivity chế độ PC).
 * Cơ sở dữ liệu chưa có phần này (hàm pc_my_vps / pc_shop_info chưa có) → không hiện gì, app chạy như cũ.
 */
final class PcVps {
    private PcVps() { }

    static JSONObject mine = null, info = null, prod = null;
    static long mineAt = 0, infoAt = 0;

    // ---------------------------------------------------------------- "Máy của tôi": khung VPS GPU
    /** Thêm 1 hộp vào trang "Máy của tôi"; có dữ liệu cũ thì vẽ ngay, rồi tải mới ngầm (tối đa 1 lần / 15 giây) và vẽ lại. */
    static void section(MainActivity a, LinearLayout body) {
        final LinearLayout box = Ui.col(a, 10);
        body.addView(box, Ui.fill());
        if (mine != null) fill(a, box);
        if (mine == null || System.currentTimeMillis() - mineAt > 15000) {
            Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> {
                if (!(r instanceof JSONObject) || a.isFinishing()) return;
                mine = (JSONObject) r; mineAt = System.currentTimeMillis();
                if (box.getParent() != null) fill(a, box);
            }, m -> { });
        }
    }

    private static JSONArray items() { return mine == null ? new JSONArray() : mine.optJSONArray("items") == null ? new JSONArray() : mine.optJSONArray("items"); }

    private static void fill(MainActivity a, LinearLayout box) {
        box.removeAllViews();
        JSONArray it = items();
        if (it.length() == 0) return;
        LinearLayout head = Ui.row(a, 10);
        head.addView(Ui.h2(a, "🖥️ " + Ui.L("VPS GPU của bạn", "Your GPU VPS")), Ui.weight(1));
        if (Api.SHOP) {
            TextView more = Ui.pill(a, "+ " + Ui.L("Thuê thêm", "Rent more"), Ui.SKY);
            more.setOnClickListener(v -> buy(a));
            head.addView(more, Ui.wrap());
        }
        box.addView(head, Ui.fill());
        boolean busy = false;
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i);
            if (x == null) continue;
            box.addView(card(a, x), Ui.fill());
            JSONObject pc = x.optJSONObject("pc");
            if ("waiting".equals(x.optString("state")) || (pc != null && pc.optJSONObject("job") != null)) busy = true;
        }
        if (busy) box.postDelayed(() -> { if (box.getParent() != null && !a.isFinishing()) { mineAt = 0; Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> {
            if (r instanceof JSONObject && box.getParent() != null) { mine = (JSONObject) r; mineAt = System.currentTimeMillis(); fill(a, box); } }, m -> { }); } }, 15000);
    }

    /** [mã trạng thái, chữ, câu giải thích] */
    private static String[] state(JSONObject x) {
        JSONObject pc = x.optJSONObject("pc"), job = pc == null ? null : pc.optJSONObject("job");
        long until = MainActivity.parseTime(x.optString("until", "")), now = System.currentTimeMillis();
        String st = x.optString("state");
        if ("waiting".equals(st)) return new String[]{"wait", "⏳ " + Ui.L("Đang chờ máy", "Waiting for a machine"),
                Ui.L("Shop đã nhận đơn. Có máy là tự giao + cài Windows — không cần nhắn shop.", "Order received — a machine will be assigned and installed automatically.")};
        if ("cancelled".equals(st)) return new String[]{"end", "✕ " + Ui.L("Đã huỷ", "Cancelled"), Ui.L("Tiền hoàn (nếu có) đã về số dư.", "Any refund went to your balance.")};
        if ("ended".equals(st)) return new String[]{"end", "■ " + Ui.L("Đã kết thúc", "Ended"), ""};
        if (job != null) return new String[]{"inst", "⚙️ " + Ui.L("Đang cài Windows", "Installing Windows"),
                "sent".equals(job.optString("state")) ? Ui.L("Máy đang cài " + job.optString("os").toUpperCase() + " (15–30 phút), xong là vào được.", "Installing " + job.optString("os").toUpperCase() + " (15–30 min).")
                        : Ui.L("Máy sắp khởi động lại để cài Windows…", "The machine will restart to install Windows…")};
        if (until > 0 && until <= now) return new String[]{"exp", "⛔ " + Ui.L("Hết hạn", "Expired"),
                pc != null && pc.optBoolean("off") ? Ui.L("Máy đã tự tắt. Gia hạn để dùng tiếp — shop bật lại máy cho bạn.", "The machine shut down. Renew and the shop turns it back on.")
                        : Ui.L("Gia hạn để dùng tiếp.", "Renew to keep using it.")};
        if (pc == null || !pc.optBoolean("online")) return new String[]{"off", "○ " + Ui.L("Máy đang tắt / mất mạng", "Offline"),
                Ui.L("Máy chưa báo về. Lâu quá 5 phút thì nhắn shop kèm tên máy.", "Not reporting — contact the shop if it lasts over 5 minutes.")};
        return new String[]{"run", "● " + Ui.L("Sẵn sàng", "Ready"), ""};
    }

    private static View card(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        String[] st = state(x);
        LinearLayout c = Ui.card(a);
        boolean run = "run".equals(st[0]);
        if (run) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(130, 60, 224, 176)));
        else if ("exp".equals(st[0]) || "wait".equals(st[0])) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(150, 255, 200, 97)));
        LinearLayout top = Ui.row(a, 8);
        top.addView(Ui.pill(a, st[1], run ? Ui.OK : "exp".equals(st[0]) ? Ui.BAD : Ui.SKY), Ui.wrap());
        if (pc != null && !pc.optString("code").isEmpty()) top.addView(Ui.pill(a, "№ " + pc.optString("code"), Ui.MUTED), Ui.wrap());
        c.addView(top, Ui.fill());
        c.addView(Ui.text(a, (pc == null ? Ui.L("VPS GPU", "GPU VPS") : pc.optString("name")) + (x.optInt("days") > 0 ? "  ·  " + x.optInt("days") + Ui.L(" ngày", " days") : ""), 16, Ui.FG, true));
        StringBuilder spec = new StringBuilder(x.optString("os_name"));
        if (pc != null) {
            JSONArray g = pc.optJSONArray("gpus");
            if (g != null && g.length() > 0 && !g.optString(0).isEmpty()) spec.append(" · ").append(g.optString(0));
            if (pc.optDouble("ram_gb", 0) > 0) spec.append(" · ").append(Math.round(pc.optDouble("ram_gb"))).append("GB RAM");
        }
        c.addView(Ui.muted(a, spec.toString()));
        if (!st[2].isEmpty()) c.addView(Ui.text(a, st[2], 13, "exp".equals(st[0]) ? Ui.BAD : "off".equals(st[0]) ? Ui.WAIT : Ui.MUTED, false));
        long until = MainActivity.parseTime(x.optString("until", ""));
        if ("active".equals(x.optString("state")) && until > System.currentTimeMillis())
            c.addView(Ui.text(a, MainActivity.left(until) + "  ·  " + Ui.L("hết hạn ", "expires ") + MainActivity.fdate(until), 13, Ui.FG, false));
        if (pc != null && "active".equals(x.optString("state"))) {
            LinearLayout acts = Ui.row(a, 8);
            Button open = Ui.button(a, "▶ " + Ui.L("Điều khiển", "Control"), Ui.PRIMARY);
            open.setEnabled(run);
            open.setAlpha(run ? 1f : 0.5f);
            open.setOnClickListener(v -> control(a, pc.optString("id"), pc.optString("name")));
            acts.addView(open, Ui.weight(1));
            if (!x.isNull("rental")) {
                int left = x.optInt("left"), max = mine == null ? 2 : mine.optInt("reinstall_max", 2);
                Button re = Ui.button(a, "🔄 " + left + "/" + max, Ui.GHOST);
                boolean canRe = left > 0 && !"inst".equals(st[0]) && !"exp".equals(st[0]);
                re.setEnabled(canRe);
                re.setAlpha(canRe ? 1f : 0.5f);
                re.setOnClickListener(v -> reinstall(a, x));
                acts.addView(re, Ui.wrap());
                if (Api.SHOP) {
                    Button rn = Ui.button(a, "⏱", Ui.GHOST);
                    rn.setContentDescription(Ui.L("Gia hạn", "Renew"));
                    rn.setOnClickListener(v -> renew(a, x));
                    acts.addView(rn, Ui.wrap());
                }
            }
            c.addView(acts, Ui.fill());
        }
        return c;
    }

    static void control(MainActivity a, String id, String name) {
        try { a.startActivity(new Intent(a, ControlActivity.class).putExtra("pc", id).putExtra("name", name)); }
        catch (Exception e) { Ui.toast(a, Ui.L("Chưa mở được màn điều khiển.", "Couldn't open the control screen.")); }
    }

    private static String err(String m) {
        if (m == null) return "";
        if (m.contains("NO_LEFT")) return Ui.L("Máy này đã hết lượt cài lại trong lượt thuê. Nhắn shop nếu cần thêm.", "No reinstalls left for this rental.");
        if (m.contains("BUSY")) return Ui.L("Máy đang cài Windows — chờ xong rồi thử lại.", "Windows is being installed — try again later.");
        if (m.contains("EXPIRED")) return Ui.L("Máy đã hết hạn — gia hạn trước.", "Expired — renew first.");
        if (m.contains("NOT_AUTO")) return Ui.L("Sản phẩm này chưa bật giao tự động.", "Automatic delivery is off.");
        if (m.contains("INSUFFICIENT_BALANCE")) return Ui.L("Số dư không đủ — nạp thêm rồi thử lại.", "Not enough balance — top up first.");
        if (m.contains("SLOW_DOWN")) return Ui.L("Bạn thao tác hơi nhanh — thử lại sau ít phút.", "Too many requests — try again later.");
        return m;
    }

    // ---------------------------------------------------------------- cài lại / đổi Windows
    private static void reinstall(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        if (pc == null) return;
        JSONArray os = mine == null ? null : mine.optJSONArray("os");
        if (os == null || os.length() == 0) return;
        final String[] pick = {x.optString("os")};
        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, Ui.L("Còn ", "") + x.optInt("left") + "/" + (mine == null ? 2 : mine.optInt("reinstall_max", 2)) + Ui.L(" lượt trong lượt thuê này", " reinstalls left in this rental")));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        for (int i = 0; i < os.length(); i++) {
            JSONObject o = os.optJSONObject(i);
            if (o == null) continue;
            TextView ch = Ui.chip(a, o.optString("name"), o.optString("id").equals(pick[0]));
            ch.setTag(o.optString("id"));
            ch.setOnClickListener(v -> { pick[0] = (String) v.getTag(); for (int k = 0; k < w.getChildCount(); k++) Ui.setChip((TextView) w.getChildAt(k), pick[0].equals(w.getChildAt(k).getTag())); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        LinearLayout note = Ui.card(a);
        note.addView(Ui.muted(a, Ui.L("⚠️ Chỉ xoá ổ C: (Windows) — ổ khác giữ nguyên. Máy khởi động lại và cài trong 15–30 phút. Dữ liệu ổ C: không lấy lại được.",
                "⚠️ Only drive C: (Windows) is erased — other drives are kept. Takes 15–30 minutes. Data on C: cannot be recovered.")));
        c.addView(note, Ui.fill());
        Button ok = Ui.button(a, Ui.L("Cài lại ngay", "Reinstall now"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(a, "🔄 " + Ui.L("Cài lại / đổi Windows", "Reinstall / switch Windows") + " · " + pc.optString("name"), c);
        ok.setOnClickListener(v -> Ui.confirm(a, Ui.L("Cài lại máy?", "Reinstall?"), Ui.L("Máy " + pc.optString("name") + " sẽ cài lại " + pick[0].toUpperCase() + ". Ổ C: bị xoá.",
                pc.optString("name") + " will be reinstalled with " + pick[0].toUpperCase() + ". Drive C: is erased."), Ui.L("Cài lại", "Reinstall"), () -> {
            ok.setEnabled(false);
            Api.bg(() -> Api.rpc("pc_my_reinstall", new JSONObject().put("p_pc", pc.optString("id")).put("p_os", pick[0])), r -> {
                d.dismiss();
                Ui.toast(a, Ui.L("Đã gửi lệnh cài lại — máy sẽ khởi động lại trong ít giây.", "Reinstall started."));
                mineAt = 0; a.refresh();
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        }));
        d.show();
    }

    // ---------------------------------------------------------------- bảng giá (sản phẩm bán tự động)
    private interface Done { void run(); }

    private static void loadShop(MainActivity a, Done then) {
        Api.bg(() -> {
            JSONObject i = (JSONObject) Api.rpc("pc_shop_info", new JSONObject());
            JSONObject p = null;
            if (i != null && i.optBoolean("on") && !i.optString("product").isEmpty()) {
                Object o = Api.get("product_list?id=eq." + i.optString("product") + "&select=id,name,plans,price");
                if (o instanceof JSONArray && ((JSONArray) o).length() > 0) p = ((JSONArray) o).getJSONObject(0);
            }
            return new JSONObject[]{i, p};
        }, r -> { info = r[0]; prod = r[1]; infoAt = System.currentTimeMillis(); then.run(); },
                m -> Ui.toast(a, Ui.L("Chưa tải được bảng giá VPS GPU: ", "Couldn't load GPU VPS prices: ") + m));
    }

    private static int[][] plans() {
        JSONArray pl = prod == null ? null : prod.optJSONArray("plans");
        java.util.ArrayList<int[]> out = new java.util.ArrayList<>();
        if (pl != null) for (int i = 0; i < pl.length(); i++) {
            JSONObject x = pl.optJSONObject(i);
            if (x != null && x.optInt("days") > 0 && x.optLong("price", -1) >= 0) out.add(new int[]{x.optInt("days"), (int) Math.min(Integer.MAX_VALUE, x.optLong("price"))});
        }
        java.util.Collections.sort(out, (p, q) -> p[0] - q[0]);
        return out.toArray(new int[0][]);
    }

    // ---------------------------------------------------------------- "Thuê máy": thẻ VPS GPU + hộp mua
    /** Thẻ ở đầu trang "Thuê máy" (chỉ bản app có mua hàng). Bán tự động chưa bật → không hiện. */
    static void rentCard(MainActivity a, LinearLayout body) {
        if (!Api.SHOP) return;
        final LinearLayout box = Ui.col(a, 0);
        body.addView(box, Ui.fill());
        Done draw = () -> {
            box.removeAllViews();
            if (info == null || !info.optBoolean("on") || prod == null) return;
            LinearLayout c = Ui.card(a);
            c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(150, 90, 175, 255)));
            c.addView(Ui.text(a, "🖥️ " + prod.optString("name", "VPS GPU"), 17, Ui.FG, true));
            int[][] pl = plans();
            c.addView(Ui.muted(a, Ui.L("Máy PC thật, card đồ hoạ rời · chọn Windows 22H2 / 1511 · tự giao + tự cài · điều khiển ngay trong app.",
                    "Real PC with a dedicated GPU · Windows 22H2 / 1511 · instant delivery · control it right in the app.")
                    + (pl.length > 0 ? "\n" + Ui.L("Từ ", "From ") + Ui.vnd(a.ctv(pl[0][1])) + " / " + pl[0][0] + Ui.L(" ngày", " days") : "")));
            Button go = Ui.button(a, Ui.L("Mua VPS GPU", "Buy GPU VPS"), Ui.PRIMARY);
            go.setOnClickListener(v -> buy(a));
            c.addView(go, Ui.fill());
            box.addView(c, Ui.fill());
        };
        if (info != null && System.currentTimeMillis() - infoAt < 60000) draw.run();
        else Api.bg(() -> {
            JSONObject i = (JSONObject) Api.rpc("pc_shop_info", new JSONObject());
            JSONObject p = null;
            if (i != null && i.optBoolean("on") && !i.optString("product").isEmpty()) {
                Object o = Api.get("product_list?id=eq." + i.optString("product") + "&select=id,name,plans,price");
                if (o instanceof JSONArray && ((JSONArray) o).length() > 0) p = ((JSONArray) o).getJSONObject(0);
            }
            return new JSONObject[]{i, p};
        }, r -> { info = r[0]; prod = r[1]; infoAt = System.currentTimeMillis(); if (box.getParent() != null) draw.run(); }, m -> { });
    }

    static void buy(MainActivity a) {
        if (!Api.SHOP) return;
        if (info == null || prod == null || System.currentTimeMillis() - infoAt > 30000) { loadShop(a, () -> { if (info != null && info.optBoolean("on") && prod != null) buySheet(a);
            else Ui.toast(a, Ui.L("VPS GPU tạm chưa bán trong app — xem trên cloudblue.vn.", "GPU VPS isn't on sale in the app right now.")); }); return; }
        buySheet(a);
    }

    private static void buySheet(MainActivity a) {
        final int[][] pl = plans();
        final JSONArray os = info.optJSONArray("os");
        if (pl.length == 0 || os == null || os.length() == 0) { Ui.toast(a, Ui.L("Chưa có gói / bản Windows để bán.", "Nothing on sale yet.")); return; }
        final int[] days = {pl[0][0]};
        for (int[] p : pl) if (p[0] == 30) days[0] = 30;
        final String[] pick = {""};
        for (int i = 0; i < os.length(); i++) { JSONObject o = os.optJSONObject(i); if (o != null && o.optBoolean("fast")) { pick[0] = o.optString("id"); break; } }
        if (pick[0].isEmpty()) pick[0] = os.optJSONObject(0).optString("id");
        LinearLayout c = Ui.col(a, 12);
        c.addView(Ui.muted(a, Ui.L("Chọn thời gian thuê", "Rental period")));
        Ui.Wrap wd = new Ui.Wrap(a, 8);
        c.addView(wd, Ui.fill());
        c.addView(Ui.muted(a, Ui.L("Chọn bản Windows", "Choose Windows")));
        Ui.Wrap wo = new Ui.Wrap(a, 8);
        c.addView(wo, Ui.fill());
        TextView hint = Ui.text(a, "", 13, Ui.MUTED, false);
        c.addView(hint, Ui.fill());
        LinearLayout sb = Ui.card(a);
        TextView sum = Ui.text(a, "", 14, Ui.FG, false);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        Button ok = Ui.button(a, Ui.L("Thanh toán", "Pay"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Runnable draw = () -> {
            for (int k = 0; k < wd.getChildCount(); k++) Ui.setChip((TextView) wd.getChildAt(k), (int) wd.getChildAt(k).getTag() == days[0]);
            boolean fast = false;
            for (int k = 0; k < wo.getChildCount(); k++) Ui.setChip((TextView) wo.getChildAt(k), pick[0].equals(wo.getChildAt(k).getTag()));
            for (int k = 0; k < os.length(); k++) { JSONObject o = os.optJSONObject(k); if (o != null && pick[0].equals(o.optString("id"))) fast = o.optBoolean("fast"); }
            hint.setText(fast ? Ui.L("⚡ Có máy sẵn — giao ngay sau khi thanh toán.", "⚡ In stock — delivered right after payment.")
                    : info.optBoolean("ready") ? Ui.L("⏳ Máy tự cài bản này cho bạn (~20 phút).", "⏳ This version is installed for you (~20 min).")
                    : Ui.L("⏳ Shop đang chuẩn bị máy — có máy là tự giao, không cần nhắn shop.", "⏳ Preparing a machine — delivered automatically."));
            int price = 0;
            for (int[] p : pl) if (p[0] == days[0]) price = p[1];
            double total = a.ctv(price), bal = a.prof.optDouble("balance", 0);
            sum.setText(Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(total) + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + "\n" + Ui.L("Được tự cài lại / đổi Windows ", "Free reinstalls / Windows switches: ") + info.optInt("reinstall_max", 2) + Ui.L(" lần", ""));
            ok.setText(bal < total ? Ui.L("Nạp thêm tiền", "Top up") : Ui.L("Thanh toán " + Ui.vnd(total), "Pay " + Ui.vnd(total)));
        };
        for (int[] p : pl) {
            TextView ch = Ui.chip(a, p[0] + Ui.L(" ngày", " days") + "\n" + Ui.vnd(a.ctv(p[1])), false);
            ch.setTag(p[0]);
            ch.setOnClickListener(v -> { days[0] = (int) v.getTag(); draw.run(); });
            wd.addView(ch);
        }
        for (int i = 0; i < os.length(); i++) {
            JSONObject o = os.optJSONObject(i);
            if (o == null) continue;
            TextView ch = Ui.chip(a, o.optString("name"), false);
            ch.setTag(o.optString("id"));
            ch.setOnClickListener(v -> { pick[0] = (String) v.getTag(); draw.run(); });
            wo.addView(ch);
        }
        draw.run();
        Dialog d = Ui.sheet(a, "🖥️ " + prod.optString("name", "VPS GPU"), c);
        ok.setOnClickListener(v -> {
            int price = 0;
            for (int[] p : pl) if (p[0] == days[0]) price = p[1];
            double total = a.ctv(price), bal = a.prof.optDouble("balance", 0);
            if (bal < total) { d.dismiss(); a.openTopup(total - bal); return; }
            ok.setEnabled(false);
            final String prodId = prod.optString("id"), os0 = pick[0];
            final int dd = days[0];
            Api.bg(() -> Api.rpc("pc_buy", new JSONObject().put("p_product", prodId).put("p_days", dd).put("p_os", os0)), r -> {
                d.dismiss();
                JSONObject res = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                boolean act = "active".equals(res.optString("state"));
                Ui.toast(a, act ? (res.optBoolean("reinstall") ? Ui.L("🎉 Đã giao máy " + res.optString("name") + " — máy đang tự cài Windows (~20 phút).", "🎉 Machine assigned — installing Windows (~20 min).")
                                : Ui.L("🎉 Đã giao máy " + res.optString("name") + " — vào điều khiển được ngay.", "🎉 Your machine is ready."))
                        : Ui.L("⏳ Đã nhận đơn — có máy là tự giao + cài Windows, không cần nhắn shop.", "⏳ Order received — delivered automatically."));
                mineAt = 0; infoAt = 0;
                a.refresh();
                a.show(0);
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    // ---------------------------------------------------------------- gia hạn
    private static void renew(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        if (pc == null) return;
        if (prod == null || System.currentTimeMillis() - infoAt > 60000) { loadShop(a, () -> { if (prod != null) renewSheet(a, x, pc); }); return; }
        renewSheet(a, x, pc);
    }

    private static void renewSheet(MainActivity a, JSONObject x, JSONObject pc) {
        final int[][] pl = plans();
        if (pl.length == 0) return;
        final int[] days = {pl[0][0]};
        LinearLayout c = Ui.col(a, 12);
        long until = MainActivity.parseTime(x.optString("until", ""));
        c.addView(Ui.muted(a, Ui.L("Hết hạn hiện tại: ", "Current expiry: ") + (until > 0 ? MainActivity.fdate(until) : "—")));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        TextView sum = Ui.text(a, "", 14, Ui.FG, false);
        Button ok = Ui.button(a, Ui.L("Gia hạn", "Renew"), Ui.PRIMARY);
        Runnable draw = () -> {
            for (int k = 0; k < w.getChildCount(); k++) Ui.setChip((TextView) w.getChildAt(k), (int) w.getChildAt(k).getTag() == days[0]);
            int price = 0;
            for (int[] p : pl) if (p[0] == days[0]) price = p[1];
            double total = a.ctv(price), bal = a.prof.optDouble("balance", 0);
            long base = Math.max(System.currentTimeMillis(), until);
            sum.setText(Ui.L("Hạn mới: ", "New expiry: ") + MainActivity.fdate(base + days[0] * 86400000L) + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(total));
            ok.setText(bal < total ? Ui.L("Nạp thêm tiền", "Top up") : Ui.L("Gia hạn " + days[0] + " ngày", "Renew " + days[0] + " days"));
        };
        for (int[] p : pl) {
            TextView ch = Ui.chip(a, "+" + p[0] + Ui.L(" ngày", " days"), false);
            ch.setTag(p[0]);
            ch.setOnClickListener(v -> { days[0] = (int) v.getTag(); draw.run(); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        LinearLayout sb = Ui.card(a);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        c.addView(ok, Ui.fill());
        draw.run();
        Dialog d = Ui.sheet(a, "⏱ " + Ui.L("Gia hạn ", "Renew ") + pc.optString("name"), c);
        ok.setOnClickListener(v -> {
            int price = 0;
            for (int[] p : pl) if (p[0] == days[0]) price = p[1];
            double total = a.ctv(price), bal = a.prof.optDouble("balance", 0);
            if (bal < total) { d.dismiss(); a.openTopup(total - bal); return; }
            ok.setEnabled(false);
            final int dd = days[0];
            Api.bg(() -> Api.rpc("pc_my_renew", new JSONObject().put("p_pc", pc.optString("id")).put("p_days", dd)), r -> {
                d.dismiss();
                boolean off = r instanceof JSONObject && ((JSONObject) r).optBoolean("was_off");
                Ui.toast(a, off ? Ui.L("Đã gia hạn. Máy đã tắt lúc hết hạn — shop sẽ bật lại cho bạn.", "Renewed. The shop will turn the machine back on.") : Ui.L("Đã gia hạn.", "Renewed."));
                mineAt = 0; a.refresh();
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }
}
