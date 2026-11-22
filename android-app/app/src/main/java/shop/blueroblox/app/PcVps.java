package shop.blueroblox.app;

import android.app.Dialog;
import android.content.Intent;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * 21/11 · VPS GPU (máy PC thật cho thuê — SQL v43): mua tự động (khách chọn bản Windows, hệ thống tự giao máy + cài),
 * danh sách "VPS GPU của bạn", cài lại / đổi Windows (giới hạn mỗi lượt thuê), gia hạn, mở màn điều khiển (ControlActivity chế độ PC).
 * 21/11e: tab riêng "VPS GPU" (tab(...)) — trang mua cho 1 cấu hình; giá / gói / tên / cấu hình đọc từ web (admin chỉnh).
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
                a.vpsChanged();                                   // 22.11c: đang mở "Xem tất cả" → ô VPS vẽ theo dữ liệu mới
            }, m -> { });
        }
    }

    /** 22.11c · các VPS hiện trong lưới "Xem tất cả" (đang thuê, đã giao máy). */
    static java.util.List<JSONObject> gridItems() {
        java.util.ArrayList<JSONObject> out = new java.util.ArrayList<>();
        JSONArray it = items();
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i), pc = x == null ? null : x.optJSONObject("pc");
            if (pc != null && !pc.optString("id").isEmpty() && "active".equals(x.optString("state"))) out.add(x);
        }
        return out;
    }

    /** 22/11 · dải ⊟ thu nhỏ: VPS của khách có máy PC mã này không (đã tải danh sách, kể cả máy hết hạn đang giữ). */
    static boolean knows(String pcId) {
        JSONArray it = items();
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i), pc = x == null ? null : x.optJSONObject("pc");
            if (pc != null && pcId.equals(pc.optString("id"))) return true;
        }
        return false;
    }

    private static long ensureAt = 0;

    /** 22/11 · dải ⊟ thu nhỏ có VPS GPU mà chưa có dữ liệu mới (khách chưa mở tab nào tải) → tải ngầm, tối đa 1 lần / 15 giây. */
    static void ensureMine(MainActivity a) {
        long now = System.currentTimeMillis();
        if ((mine != null && now - mineAt < 15000) || now - ensureAt < 15000) return;
        ensureAt = now;
        Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> {
            if (!(r instanceof JSONObject) || a.isFinishing()) return;
            mine = (JSONObject) r; mineAt = System.currentTimeMillis();
            a.vpsChanged();
        }, m -> { });
    }

    /** 22.11c · VPS xem trước / điều khiển được ngay (máy sẵn sàng, không bảo trì riêng VPS GPU). */
    static boolean liveNow(MainActivity a, JSONObject x) {
        String c = state(x)[0];
        return ("run".equals(c) || "warn".equals(c)) && maint(a).isEmpty();
    }

    /** 21/11f · bảo trì riêng VPS GPU (khách thường) → câu báo; không bảo trì / admin → "". */
    static String maint(MainActivity a) { return a.isAdmin() ? "" : Api.pcMaintMsg(); }

    private static View maintCard(MainActivity a, String m) {
        TextView t = Ui.text(a, m, 13.5f, Ui.FG, true);
        t.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(14), Ui.dp(11));
        t.setBackground(Ui.round(Color.argb(34, 255, 200, 97), 14, Color.argb(150, 255, 200, 97)));
        return t;
    }

    private static JSONArray items() {
        JSONArray all = mine == null ? null : mine.optJSONArray("items"), out = new JSONArray();
        if (all == null) return out;
        long now = System.currentTimeMillis();
        for (int i = 0; i < all.length(); i++) {                 // 21.11k: thẻ "Đã kết thúc" quá giờ tự ẩn (SQL v45b: hide_at) → không hiện nữa
            JSONObject x = all.optJSONObject(i);
            if (x == null) continue;
            long h = MainActivity.parseTime(x.optString("hide_at", ""));
            if (h > 0 && h <= now) continue;
            out.put(x);
        }
        return out;
    }

    /** 21.11k · mã các VPS đang thuê + máy đang bật (điều khiển được ngay) — cho nút ▦ Nhiều máy. */
    static int controllable() {
        JSONArray it = items(); int n = 0;
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i), pc = x == null ? null : x.optJSONObject("pc");
            if (pc != null && "active".equals(x.optString("state")) && pc.optBoolean("online") && !pc.optBoolean("lock")) n++;
        }
        return n;
    }

    /** 21/11f · Số VPS GPU đang thuê / đang chờ máy (theo dữ liệu đã tải). */
    static int live() {
        JSONArray it = items(); int n = 0;
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i);
            if (x != null && ("active".equals(x.optString("state")) || "waiting".equals(x.optString("state")))) n++;
        }
        return n;
    }

    /** 21/11f · "Máy của tôi" = cloud phone; VPS GPU là MỤC RIÊNG (tab 🖥️ VPS GPU) → ở đây chỉ 1 dòng gọn dẫn sang tab đó khi khách có VPS.
     *  Bản không bán trong app (không có tab VPS GPU) → vẫn hiện đủ thẻ VPS ở đây như cũ. */
    static void link(MainActivity a, LinearLayout body) {
        if (true) { section(a, body); return; }               // 21.11k: Máy của tôi hiện đủ thẻ VPS GPU (▶ Điều khiển · ⏱ · ⋯) như Cloud Phone — tab VPS GPU chỉ để mua
        final LinearLayout box = Ui.col(a, 0);
        body.addView(box, Ui.fill());
        final Runnable paint = () -> {
            box.removeAllViews();
            int n = live();
            if (n == 0) return;
            LinearLayout r = Ui.row(a, 12);
            r.setGravity(Gravity.CENTER_VERTICAL);
            r.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(12), Ui.dp(11));
            r.setBackground(Ui.round(Ui.LIGHT ? Color.argb(24, 43, 110, 240) : Color.argb(40, 90, 175, 255), 16, Color.argb(120, 90, 175, 255)));
            r.addView(Ui.text(a, "🖥️", 22, Ui.FG, false), Ui.wrap());
            LinearLayout tx = Ui.col(a, 2);
            tx.addView(Ui.text(a, Ui.L("VPS GPU của bạn · " + n + " máy", "Your GPU VPS · " + n), 15, Ui.FG, true));
            tx.addView(Ui.muted(a, Ui.L("Điều khiển · cài lại · gia hạn ở tab VPS GPU", "Control · reinstall · renew in the GPU VPS tab")));
            r.addView(tx, Ui.weight(1));
            r.addView(Ui.text(a, "›", 26, Ui.SKY, true), Ui.wrap());
            r.setClickable(true);
            r.setContentDescription(Ui.L("Mở tab VPS GPU", "Open the GPU VPS tab"));
            r.setOnClickListener(v -> a.show(3));
            box.addView(r, Ui.fill());
        };
        if (mine != null) paint.run();
        if (mine == null || System.currentTimeMillis() - mineAt > 15000) {
            Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> {
                if (!(r instanceof JSONObject) || a.isFinishing()) return;
                mine = (JSONObject) r; mineAt = System.currentTimeMillis();
                if (box.getParent() != null) paint.run();
                a.vpsAuto();
            }, m -> { });
        } else a.vpsAuto();
    }

    private static void fill(MainActivity a, LinearLayout box) {
        box.removeAllViews();
        JSONArray it = items();
        if (it.length() == 0) return;
        LinearLayout head = Ui.row(a, 10);
        head.addView(Ui.h2(a, "🖥️ " + Ui.L("VPS GPU của bạn", "Your GPU VPS")), Ui.weight(1));
        if (Api.SHOP) {
            TextView more = Ui.pill(a, "+ " + Ui.L("Thuê thêm", "Rent more"), Ui.SKY);
            more.setOnClickListener(v -> a.show(3));
            head.addView(more, Ui.wrap());
        }
        if (!gridItems().isEmpty()) {                               // 22.11c: lưới XEM trực tiếp mọi VPS GPU (+ Cloud Phone) — như "Xem tất cả" của Cloud Phone
            TextView all = Ui.pill(a, "▦ " + Ui.L("Xem tất cả", "View all"), Ui.OK);
            all.setContentDescription(Ui.L("Xem trực tiếp màn hình mọi máy", "Watch every machine's screen live"));
            all.setOnClickListener(v -> a.openGrid());
            head.addView(all, Ui.wrap());
        }
        if (controllable() >= 2 && maint(a).isEmpty()) {           // 21.11k: điều khiển nhiều VPS cùng lúc (lưới + 🔗 đồng bộ)
            TextView mu = Ui.pill(a, "▦ " + Ui.L("Nhiều máy", "Multi"), Ui.OK);
            mu.setContentDescription(Ui.L("Điều khiển nhiều máy cùng lúc", "Control several machines at once"));
            mu.setOnClickListener(v -> {
                try { a.startActivity(new Intent(a, MultiActivity.class).putExtra("pc", true).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP)); }
                catch (Exception e) { Ui.toast(a, Ui.L("Chưa mở được màn nhiều máy.", "Couldn't open multi-control.")); }
            });
            head.addView(mu, Ui.wrap());
        }
        box.addView(head, Ui.fill());
        String mt = maint(a);
        if (!mt.isEmpty()) box.addView(maintCard(a, mt), Ui.fill());
        boolean busy = false;
        for (int i = 0; i < it.length(); i++) {
            JSONObject x = it.optJSONObject(i);
            if (x == null) continue;
            box.addView(card(a, x), Ui.fill());
            JSONObject pc = x.optJSONObject("pc");
            String code = state(x)[0];                                                // 22/11 · đang khởi động lại / đang tắt → đọc lại sau 15 giây
            if ("waiting".equals(x.optString("state")) || (pc != null && pc.optJSONObject("job") != null) || "boot".equals(code) || "down".equals(code)) busy = true;
        }
        if (busy) box.postDelayed(() -> { if (box.getParent() != null && !a.isFinishing()) { mineAt = 0; Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> {
            if (r instanceof JSONObject && box.getParent() != null) { mine = (JSONObject) r; mineAt = System.currentTimeMillis(); fill(a, box); a.vpsChanged(); } }, m -> { }); } }, 15000);
    }

    /** 22.11f · bản Linux CachyOS (KDE): điều khiển như máy Windows, không dùng card NVIDIA. */
    static boolean lin(String os) { return os != null && "cachyos".equalsIgnoreCase(os.trim()); }

    static String osName(String id) {
        JSONArray l = mine == null ? null : mine.optJSONArray("os");
        if (l == null && info != null) l = info.optJSONArray("os");
        JSONObject o = osOf(l, id);
        if (o != null && !o.optString("name").isEmpty()) return o.optString("name");
        return lin(id) ? "Linux CachyOS" : "Windows " + (id == null ? "" : id.toUpperCase());
    }

    static String instTime(String os) { return lin(os) ? Ui.L("30–60 phút", "30–60 min") : Ui.L("15–30 phút", "15–30 min"); }

    static String linNote() {
        return Ui.L("🐧 Linux CachyOS (KDE): điều khiển từ xa như máy Windows. Bản Linux không dùng card đồ hoạ NVIDIA và không chạy phần mềm / game Windows.",
                "🐧 Linux CachyOS (KDE): remote control just like Windows. The Linux edition doesn't use the NVIDIA GPU and can't run Windows apps / games.");
    }

    /** [mã trạng thái, chữ, câu giải thích] */
    static String[] state(JSONObject x) {
        JSONObject pc = x.optJSONObject("pc"), job = pc == null ? null : pc.optJSONObject("job");
        long until = MainActivity.parseTime(x.optString("until", "")), now = System.currentTimeMillis();
        String st = x.optString("state");
        if ("waiting".equals(st)) return new String[]{"wait", "⏳ " + Ui.L("Đang chờ máy", "Waiting for a machine"),
                Ui.L("Shop đã nhận đơn. Có máy là tự giao + cài " + (x.optString("os_name").isEmpty() ? "Windows" : x.optString("os_name")) + " — không cần nhắn shop.",
                        "Order received — a machine will be assigned and installed automatically.")};
        if ("cancelled".equals(st)) return new String[]{"end", "✕ " + Ui.L("Đã huỷ", "Cancelled"), Ui.L("Tiền hoàn (nếu có) đã về số dư.", "Any refund went to your balance.")};
        if ("ended".equals(st)) return new String[]{"end", "■ " + Ui.L("Đã kết thúc", "Ended"), "expired".equals(x.optString("end_why", ""))      // 21/11f · v44 tự thu hồi
                ? Ui.L("Hết hạn không gia hạn — máy đã được thu hồi và xoá sạch. Muốn dùng tiếp: thuê máy mới.", "Expired without renewal — the machine was reclaimed and wiped.") : ""};
        if (job != null) {
            String jo = job.optString("os"), jn = osName(jo);
            return new String[]{"inst", "⚙️ " + (lin(jo) ? Ui.L("Đang cài Linux CachyOS", "Installing Linux CachyOS") : Ui.L("Đang cài Windows", "Installing Windows")),
                    "sent".equals(job.optString("state")) ? Ui.L("Máy đang cài " + jn + " (" + instTime(jo) + "), xong là vào được.", "Installing " + jn + " (" + instTime(jo) + ").")
                            : Ui.L("Máy sắp khởi động lại để cài " + jn + "…", "The machine will restart to install " + jn + "…")};
        }
        long gu = MainActivity.parseTime(x.optString("grace_until", ""));          // 21/11f · v44: hết hạn nhưng máy còn giữ cho khách tới lúc này
        if (until > 0 && until <= now && gu > now) return new String[]{"exp", "⛔ " + Ui.L("Hết hạn — đang giữ máy", "Expired — on hold"),
                (pc != null && pc.optBoolean("lock") ? Ui.L("🔒 Máy đã khoá. ", "🔒 Locked. ") : pc != null && pc.optBoolean("off") ? Ui.L("Máy đã tự tắt. ", "Shut down. ") : "")
                        + Ui.L("Gia hạn trước " + MainActivity.fdate(gu) + " để giữ máy + dữ liệu — gia hạn xong máy tự mở lại sau 1–2 phút. Quá giờ đó máy bị thu hồi và xoá sạch.",
                        "Renew before " + MainActivity.fdate(gu) + " to keep the machine and data — it unlocks 1–2 min after renewal. After that it is reclaimed and wiped.")};
        if (until > 0 && until <= now) return new String[]{"exp", "⛔ " + Ui.L("Hết hạn", "Expired"),
                pc != null && pc.optBoolean("off") ? Ui.L("Máy đã tự tắt. Gia hạn để dùng tiếp — shop bật lại máy cho bạn.", "The machine shut down. Renew and the shop turns it back on.")
                        : Ui.L("Gia hạn để dùng tiếp.", "Renew to keep using it.")};
        String[] pw = pow(pc, now);                                                 // 22/11 · v48: đang khởi động lại / đang tắt / đã tắt
        if (pw != null) return pw;
        if (pc == null || !pc.optBoolean("online")) return new String[]{"off", "○ " + Ui.L("Máy đang tắt / mất mạng", "Offline"),
                Ui.L("Máy chưa báo về. Lâu quá 5 phút thì nhắn shop kèm tên máy.", "Not reporting — contact the shop if it lasts over 5 minutes.")};
        JSONObject lj = pc.optJSONObject("last_job");                               // 21/11f · lần cài lại gần nhất bị lỗi (như web)
        if (lj != null && "failed".equals(lj.optString("state"))) return new String[]{"warn", "⚠️ " + Ui.L("Cài lại chưa xong", "Reinstall failed"),
                Ui.L("Lần cài lại vừa rồi bị lỗi — bấm 📋 Báo admin để shop xử lý.", "The last reinstall failed — tap 📋 Report to the admin.")};
        return new String[]{"run", "● " + Ui.L("Sẵn sàng", "Ready"), ""};
    }

    /** 22/11 · SQL v48: lệnh khởi động lại / tắt máy gần nhất (khách hoặc shop bấm) → [mã, chữ, câu] hoặc null — giống web / app máy tính:
     *  boot = đang khởi động lại (3 phút đầu luôn hiện; máy chưa báo về thì hiện tiếp tới 15 phút) · down = đang tắt · offd = đã tắt hẳn.
     *  Lệnh chưa tới máy (queued) chỉ tính khi máy đang bật. */
    private static String[] pow(JSONObject pc, long now) {
        JSONObject p = pc == null ? null : pc.optJSONObject("pow");
        if (p == null) return null;
        String cmd = p.optString("cmd"), st = p.optString("state");
        long at = MainActivity.parseTime(p.optString("at", ""));
        if (at <= 0 || !("reboot".equals(cmd) || "shutdown".equals(cmd))) return null;
        long age = now - at;
        boolean online = pc.optBoolean("online"), got = "sent".equals(st) || "done".equals(st), shop = !"customer".equals(p.optString("by"));
        if ("reboot".equals(cmd)) {
            String t = "🔁 " + Ui.L("Đang khởi động lại…", "Restarting…");
            if (!got) return online && age < 600_000 ? new String[]{"boot", t,
                    Ui.L("Đang gửi lệnh tới máy — máy nhận là khởi động lại ngay.", "Sending the command — the machine restarts as soon as it gets it.")} : null;
            if (age < 180_000 || (!online && age < 900_000)) return new String[]{"boot", t,
                    (shop ? Ui.L("Shop vừa khởi động lại máy. ", "The shop restarted the machine. ") : "")
                            + Ui.L("Thường 1–3 phút là dùng lại được. Quá 10 phút chưa lên thì nhắn shop kèm tên máy.",
                            "Usually back in 1–3 minutes. Not back after 10 minutes? Contact the shop with the machine name.")};
            return null;
        }
        String t = "⏻ " + Ui.L("Đang tắt máy…", "Shutting down…");
        if (!got) return online && age < 600_000 ? new String[]{"down", t,
                Ui.L("Đang gửi lệnh tới máy — máy nhận là tắt ngay.", "Sending the command — the machine turns off as soon as it gets it.")} : null;
        if (online) return age < 180_000 ? new String[]{"down", t, Ui.L("Máy tắt sau khoảng 10 giây.", "It turns off in about 10 seconds.")} : null;
        String hm = new java.text.SimpleDateFormat("HH:mm", java.util.Locale.ROOT).format(new java.util.Date(at));
        return new String[]{"offd", "⏻ " + Ui.L("Đã tắt máy", "Shut down"), shop
                ? Ui.L("Shop đã tắt máy lúc " + hm + ". Cần dùng thì nhắn shop bật lại.", "The shop shut it down at " + hm + ". Contact the shop to turn it back on.")
                : Ui.L("Bạn đã tắt máy lúc " + hm + " — máy tắt hẳn. Cần dùng lại thì nhắn shop bật nguồn (shop đã được báo).",
                "You shut it down at " + hm + " — it stays off. Ask the shop to turn it back on (they have been notified).")};
    }

    private static boolean powSt(String code) { return "boot".equals(code) || "down".equals(code) || "offd".equals(code); }

    private static View card(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        String[] st = state(x);
        LinearLayout c = Ui.card(a);
        boolean run = "run".equals(st[0]);
        if (run) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(130, 60, 224, 176)));
        else if ("exp".equals(st[0]) || "wait".equals(st[0]) || "warn".equals(st[0]) || powSt(st[0])) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(150, 255, 200, 97)));
        LinearLayout top = Ui.row(a, 8);
        top.addView(Ui.pill(a, st[1], run ? Ui.OK : "exp".equals(st[0]) ? Ui.BAD : "warn".equals(st[0]) || powSt(st[0]) ? Ui.WAIT : Ui.SKY), Ui.wrap());
        if (pc != null && !pc.optString("code").isEmpty()) top.addView(Ui.pill(a, "№ " + pc.optString("code"), Ui.MUTED), Ui.wrap());
        c.addView(top, Ui.fill());
        c.addView(Ui.text(a, (pc == null ? Ui.L("VPS GPU", "GPU VPS") : pc.optString("name")) + (x.optInt("days") > 0 ? "  ·  " + x.optInt("days") + Ui.L(" ngày", " days") : ""), 16, Ui.FG, true));
        StringBuilder spec = new StringBuilder(x.optString("os_name"));
        if (pc != null) {
            JSONArray g = pc.optJSONArray("gpus");
            if (g != null && g.length() > 0 && !g.optString(0).isEmpty() && !lin(pc.optString("os"))) spec.append(" · ").append(g.optString(0));   // Linux không dùng card đồ hoạ
            if (pc.optDouble("ram_gb", 0) > 0) spec.append(" · ").append(Math.round(pc.optDouble("ram_gb"))).append("GB RAM");
        }
        c.addView(Ui.muted(a, spec.toString()));
        if (!st[2].isEmpty()) c.addView(Ui.text(a, st[2], 13, "exp".equals(st[0]) || "warn".equals(st[0]) ? Ui.BAD : "off".equals(st[0]) || powSt(st[0]) ? Ui.WAIT : Ui.MUTED, false));
        if ("warn".equals(st[0]) && pc != null) {                                  // 21/11f · cài lại lỗi → lý do + Báo admin
            JSONObject lj = pc.optJSONObject("last_job");
            String why = lj == null ? "" : lj.optString("msg", "").trim();
            if (!why.isEmpty()) c.addView(Ui.text(a, why, 12.5f, Ui.BAD, false));
            c.addView(repBtn(a, x), Ui.fill());
        }
        if ("inst".equals(st[0]) || "wait".equals(st[0])) {                         // 21/11f · thanh tiến độ có đếm giờ (mỗi giây)
            JSONObject job = pc == null ? null : pc.optJSONObject("job");
            long t0 = MainActivity.parseTime("inst".equals(st[0]) ? (job == null ? "" : job.optString("at", "")) : x.optString("created_at", ""));
            c.addView(progress(a, x, "inst".equals(st[0]), t0, job == null ? "" : job.optString("os", "")), Ui.fill());
        }
        long until = MainActivity.parseTime(x.optString("until", ""));
        if ("active".equals(x.optString("state")) && until > System.currentTimeMillis())
            c.addView(Ui.text(a, MainActivity.left(until) + "  ·  " + Ui.L("hết hạn ", "expires ") + MainActivity.fdate(until), 13, Ui.FG, false));
        long hide = MainActivity.parseTime(x.optString("hide_at", ""));
        if ("end".equals(st[0]) && hide > 0)                                         // 21.11k: thẻ đã kết thúc tự ẩn sau 30 phút
            c.addView(Ui.muted(a, "🕒 " + Ui.L("Thẻ này tự ẩn lúc ", "This card disappears at ") + new java.text.SimpleDateFormat("HH:mm", java.util.Locale.ROOT).format(new java.util.Date(hide))));
        if (pc != null && "active".equals(x.optString("state"))) {
            LinearLayout acts = Ui.row(a, 8);
            Button open = Ui.button(a, "▶ " + Ui.L("Điều khiển", "Control"), Ui.PRIMARY);
            final boolean mtOn = !maint(a).isEmpty();                               // 21/11f · bảo trì riêng VPS GPU → khoá điều khiển
            final boolean ctl = (run || "warn".equals(st[0]) || "boot".equals(st[0])) && !mtOn;   // đang khởi động lại: vẫn mở được (máy lên là vào)
            open.setEnabled(ctl);
            open.setAlpha(ctl ? 1f : 0.5f);
            open.setOnClickListener(v -> control(a, pc.optString("id"), pc.optString("name")));
            acts.addView(open, Ui.weight(1));
            if (!x.isNull("rental") && Api.SHOP) {
                Button rn = Ui.button(a, "⏱ " + Ui.L("Gia hạn", "Renew"), Ui.GHOST);
                rn.setOnClickListener(v -> renew(a, x));
                acts.addView(rn, Ui.wrap());
            }
            Button mo = Ui.button(a, "⋯", Ui.GHOST);                                // 21.11k: Khác — (22/11: 🔁 khởi động lại · ⏻ tắt máy) · cài lại Windows · báo admin · 🗑 Huỷ máy
            mo.setContentDescription(mine != null && mine.optBoolean("power") ? Ui.L("Khác: khởi động lại, tắt máy, cài lại, báo admin", "More: restart, shut down, reinstall, report")
                    : Ui.L("Khác", "More"));
            mo.setOnClickListener(v -> more(a, x, st));
            acts.addView(mo, Ui.wrap());
            c.addView(acts, Ui.fill());
        }
        return c;
    }

    /** 21.11k · "⋯" của 1 VPS: 🔄 cài lại / đổi Windows · 📋 báo admin · 🗑 Huỷ máy (trả máy, xoá sạch, không hoàn tiền). */
    private static void more(MainActivity a, JSONObject x, String[] st) {
        LinearLayout c = Ui.col(a, 10);
        final Dialog[] d = new Dialog[1];
        if (mine != null && mine.optBoolean("power")) {                              // 22/11 · SQL v48: khách tự khởi động lại / tắt máy (máy phải đang bật)
            boolean canPow = ("run".equals(st[0]) || "warn".equals(st[0])) && maint(a).isEmpty();
            Button rb = Ui.button(a, "🔁 " + Ui.L("Khởi động lại máy", "Restart the machine"), Ui.GHOST);
            Button sd = Ui.button(a, "⏻ " + Ui.L("Tắt máy", "Shut down"), Ui.GHOST);
            for (Button b : new Button[]{rb, sd}) { b.setEnabled(canPow); b.setAlpha(canPow ? 1f : 0.5f); }
            rb.setOnClickListener(v -> { d[0].dismiss(); power(a, x, "reboot"); });
            sd.setOnClickListener(v -> { d[0].dismiss(); power(a, x, "shutdown"); });
            c.addView(rb, Ui.fill());
            c.addView(sd, Ui.fill());
            if (!canPow) c.addView(Ui.muted(a, Ui.L("Khởi động lại / tắt máy dùng được khi máy đang bật.", "Restart / shut down works while the machine is on.")));
        }
        if (!x.isNull("rental")) {
            int left = x.optInt("left"), max = mine == null ? 2 : mine.optInt("reinstall_max", 2);
            Button re = Ui.button(a, "🔄 " + Ui.L("Cài lại / đổi hệ điều hành", "Reinstall / switch the OS") + " (" + left + "/" + max + ")", Ui.GHOST);
            boolean canRe = left > 0 && !"inst".equals(st[0]) && !"exp".equals(st[0]) && maint(a).isEmpty();
            re.setEnabled(canRe);
            re.setAlpha(canRe ? 1f : 0.5f);
            re.setOnClickListener(v -> { d[0].dismiss(); reinstall(a, x); });
            c.addView(re, Ui.fill());
        }
        Button rp = Ui.button(a, "📋 " + Ui.L("Báo admin (copy nội dung gửi shop)", "Report to the admin"), Ui.GHOST);
        rp.setOnClickListener(v -> { d[0].dismiss(); report(a, x); });
        c.addView(rp, Ui.fill());
        if (mine != null && mine.optBoolean("cancel")) {                              // SQL v45: khách tự huỷ máy
            Button cx = Ui.button(a, "🗑 " + Ui.L("Huỷ máy (trả máy, xoá sạch, không hoàn tiền)", "Cancel machine (wipe, no refund)"), Ui.DANGER);
            cx.setOnClickListener(v -> { d[0].dismiss(); cancel(a, x); });
            c.addView(cx, Ui.fill());
        }
        JSONObject pc = x.optJSONObject("pc");
        d[0] = Ui.sheet(a, pc == null ? Ui.L("VPS GPU", "GPU VPS") : pc.optString("name"), c);
        d[0].show();
    }

    /** 21.11k · 🗑 Huỷ máy: hộp xác nhận — nút Huỷ chỉ bấm được sau khi tick "Tôi hiểu" (khỏi bấm nhầm). Gỡ máy khỏi tài khoản ngay, shop thu hồi,
     *  xoá sạch mọi ổ, về kho — KHÔNG hoàn tiền (SQL v45 pc_my_cancel). */
    private static void cancel(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        if (pc == null) return;
        LinearLayout c = Ui.col(a, 12);
        long until = MainActivity.parseTime(x.optString("until", ""));
        String rest = until > System.currentTimeMillis() ? MainActivity.left(until) : "";
        LinearLayout warn = Ui.card(a);
        warn.setBackground(Ui.round(Color.argb(26, 255, 107, 129), 16, Color.argb(130, 255, 107, 129)));
        warn.addView(Ui.text(a, Ui.L("⚠️ Máy bị GỠ KHỎI TÀI KHOẢN của bạn ngay.", "⚠️ The machine is REMOVED from your account right away."), 14, Ui.FG, true));
        warn.addView(Ui.text(a, Ui.L("Shop thu hồi máy và XOÁ SẠCH toàn bộ dữ liệu (mọi ổ đĩa) để giao khách khác.", "The shop takes it back and ERASES all data (every drive)."), 13.5f, Ui.FG, false));
        warn.addView(Ui.text(a, "💸 " + Ui.L("KHÔNG hoàn tiền", "NO refund") + (rest.isEmpty() ? "" : Ui.L(" phần thời gian còn lại (" + rest + ")", " for the remaining time (" + rest + ")"))
                + Ui.L(". Không hoàn tác được.", ". This cannot be undone."), 13.5f, Ui.BAD, true));
        c.addView(warn, Ui.fill());
        final CheckBox ok = new CheckBox(a);
        ok.setText(Ui.L("Tôi hiểu: mất hết dữ liệu, không hoàn tiền", "I understand: all data is erased, no refund"));
        ok.setTextColor(Ui.FG);
        ok.setTextSize(14);
        c.addView(ok, Ui.fill());
        final Button go = Ui.button(a, "🗑 " + Ui.L("Huỷ máy", "Cancel machine"), Ui.DANGER);
        go.setEnabled(false);
        go.setAlpha(0.5f);
        ok.setOnCheckedChangeListener((b, on) -> { go.setEnabled(on); go.setAlpha(on ? 1f : 0.5f); });
        Button keep = Ui.button(a, Ui.L("Giữ máy", "Keep it"), Ui.GHOST);
        c.addView(go, Ui.fill());
        c.addView(keep, Ui.fill());
        final Dialog d = Ui.sheet(a, "🗑 " + Ui.L("Huỷ máy ", "Cancel ") + pc.optString("name") + "?", c);
        keep.setOnClickListener(v -> d.dismiss());
        go.setOnClickListener(v -> {
            if (!ok.isChecked()) return;
            go.setEnabled(false);
            Api.bg(() -> Api.rpc("pc_my_cancel", new JSONObject().put("p_pc", pc.optString("id"))), r -> {
                d.dismiss();
                Ui.toast(a, Ui.L("Đã huỷ máy — máy đang được xoá sạch và trả về shop.", "Machine cancelled — it is being wiped and returned to the shop."));
                mineAt = 0; a.refresh();
            }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    /** 22/11 · 🔁 Khởi động lại / ⏻ Tắt máy (SQL v48 pc_my_power) — giống web / app máy tính. Tắt = tắt HẲN (shop bật nguồn lại giúp, shop được báo ngay)
     *  → nút Tắt chỉ bấm được sau khi tick "Tôi hiểu". */
    private static void power(MainActivity a, JSONObject x, String cmd) {
        final JSONObject pc = x.optJSONObject("pc");
        if (pc == null) return;
        final boolean off = "shutdown".equals(cmd);
        LinearLayout c = Ui.col(a, 12);
        LinearLayout box = Ui.card(a);
        if (off) box.setBackground(Ui.round(Color.argb(26, 255, 107, 129), 16, Color.argb(130, 255, 107, 129)));
        box.addView(Ui.text(a, off ? Ui.L("⚠️ Máy TẮT HẲN, không tự bật lại.", "⚠️ The machine STAYS OFF — it does not turn back on by itself.")
                : Ui.L("Máy tắt rồi TỰ BẬT LẠI — thường 1–3 phút là dùng tiếp được.", "The machine turns off and BACK ON by itself — usually ready in 1–3 minutes."), 14, Ui.FG, true));
        box.addView(Ui.text(a, off ? Ui.L("Muốn dùng lại phải nhắn shop bật nguồn giúp — thời gian thuê vẫn tính.", "To use it again, ask the shop to power it on. Rental time keeps counting.")
                : Ui.L("Chương trình đang mở bị đóng, dữ liệu đã lưu giữ nguyên.", "Open programs are closed; saved data is kept."), 13.5f, Ui.FG, false));
        c.addView(box, Ui.fill());
        final CheckBox ok = new CheckBox(a);
        final Button go = Ui.button(a, off ? "⏻ " + Ui.L("Tắt máy", "Shut down") : "🔁 " + Ui.L("Khởi động lại ngay", "Restart now"), off ? Ui.DANGER : Ui.PRIMARY);
        if (off) {
            ok.setText(Ui.L("Tôi hiểu: máy tắt hẳn, cần nhắn shop bật lại", "I understand: it stays off until the shop powers it on"));
            ok.setTextColor(Ui.FG);
            ok.setTextSize(14);
            c.addView(ok, Ui.fill());
            go.setEnabled(false);
            go.setAlpha(0.5f);
            ok.setOnCheckedChangeListener((b, on) -> { go.setEnabled(on); go.setAlpha(on ? 1f : 0.5f); });
        }
        Button keep = Ui.button(a, Ui.L("Để sau", "Not now"), Ui.GHOST);
        c.addView(go, Ui.fill());
        c.addView(keep, Ui.fill());
        final Dialog d = Ui.sheet(a, (off ? "⏻ " + Ui.L("Tắt máy ", "Shut down ") : "🔁 " + Ui.L("Khởi động lại ", "Restart ")) + pc.optString("name") + "?", c);
        keep.setOnClickListener(v -> d.dismiss());
        go.setOnClickListener(v -> {
            if (off && !ok.isChecked()) return;
            go.setEnabled(false);
            Api.bg(() -> Api.rpc("pc_my_power", new JSONObject().put("p_pc", pc.optString("id")).put("p_cmd", off ? "shutdown" : "reboot")), r -> {
                d.dismiss();
                boolean dup = r instanceof JSONObject && ((JSONObject) r).optBoolean("dup");
                Ui.toast(a, dup ? Ui.L("Máy đang có lệnh chờ nhận — đợi chút là chạy.", "A command is already on its way — it runs in a moment.")
                        : off ? Ui.L("Đã gửi lệnh tắt máy — máy tắt sau khoảng 10 giây. Cần dùng lại thì nhắn shop bật nguồn.", "Shutdown sent — it turns off in about 10 seconds. Ask the shop to power it back on.")
                        : Ui.L("Đã gửi lệnh khởi động lại — máy lên lại sau khoảng 1–3 phút.", "Restart sent — the machine is back in about 1–3 minutes."));
                mineAt = 0; a.refresh();
            }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    static void control(MainActivity a, String id, String name) {
        try { a.startActivity(new Intent(a, ControlActivity.class).putExtra("pc", id).putExtra("name", name)); }
        catch (Exception e) { Ui.toast(a, Ui.L("Chưa mở được màn điều khiển.", "Couldn't open the control screen.")); }
    }

    private static String err(String m) {
        if (m == null) return "";
        if (m.contains("NO_LEFT")) return Ui.L("Máy này đã hết lượt cài lại trong lượt thuê. Nhắn shop nếu cần thêm.", "No reinstalls left for this rental.");
        if (m.contains("BUSY")) return Ui.L("Máy đang cài hệ điều hành — chờ xong rồi thử lại.", "The OS is being installed — try again later.");
        if (m.contains("CANT_OS")) return Ui.L("Máy của bạn chưa đổi được sang bản này (Linux cần máy UEFI đã tắt Secure Boot). Nhắn shop nếu cần.",   // 22.11f · SQL v50
                "Your machine can't switch to this edition yet. Contact the shop.");
        if (m.contains("EXPIRED")) return Ui.L("Máy đã hết hạn — gia hạn trước.", "Expired — renew first.");
        if (m.contains("NOT_AUTO")) return Ui.L("Sản phẩm này chưa bật giao tự động.", "Automatic delivery is off.");
        if (m.contains("INSUFFICIENT_BALANCE")) return Ui.L("Số dư không đủ — nạp thêm rồi thử lại.", "Not enough balance — top up first.");
        if (m.contains("SLOW_DOWN")) return Ui.L("Bạn thao tác hơi nhanh — thử lại sau ít phút.", "Too many requests — try again later.");
        if (m.contains("NOT_ALLOWED")) return Ui.L("Máy này không thuộc tài khoản của bạn.", "This machine is not on your account.");
        if (m.contains("OFFLINE")) return Ui.L("Máy đang tắt / mất kết nối nên không nhận được lệnh. Cần bật lại thì nhắn shop kèm tên máy.",   // 22/11 · SQL v48
                "The machine is offline and can't get the command. Contact the shop to turn it back on.");
        if (m.contains("BAD_CMD")) return Ui.L("Lệnh không hợp lệ — cập nhật app rồi thử lại.", "Invalid command — update the app and try again.");
        return m;
    }

    // ---------------------------------------------------------------- 21/11f · thanh tiến độ có đếm giờ + Báo admin

    private static String mmss(long sec) {
        sec = Math.max(0, sec);
        long h = sec / 3600, m = sec % 3600 / 60, x = sec % 60;
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") + m : String.valueOf(m)) + ":" + (x < 10 ? "0" : "") + x;
    }

    /** Thanh % ước tính theo thời gian thường mất (cài Windows ~25 phút, chờ máy ~10 phút), tự đếm mỗi giây; quá lâu → vàng + nút Báo admin. */
    private static View progress(MainActivity a, JSONObject x, boolean inst, long t0, String os) {
        final LinearLayout box = Ui.col(a, 4);
        final android.widget.ProgressBar bar = new android.widget.ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.SKY));
        box.addView(bar, new LinearLayout.LayoutParams(-1, Ui.dp(10)));
        final TextView t = Ui.text(a, "", 12.5f, Ui.MUTED, false);
        box.addView(t, Ui.fill());
        final Button rep = repBtn(a, x);
        rep.setVisibility(View.GONE);
        box.addView(rep, Ui.fill());
        final boolean lx = inst && lin(os);
        final long start = t0 > 0 ? t0 : System.currentTimeMillis(), exp = (lx ? 45 : inst ? 25 : 10) * 60L;
        final String osU = os == null ? "" : os.toUpperCase();
        final Runnable[] tick = new Runnable[1];
        tick[0] = () -> {
            long sec = Math.max(0, (System.currentTimeMillis() - start) / 1000);
            int pct = (int) Math.min(inst ? 96 : 90, Math.max(2, Math.round(100 * (1 - Math.exp(-sec / (exp * .55))))));
            boolean late = sec > exp * (inst ? 2 : 3);
            String stage = !inst ? Ui.L("Đang chờ máy — có máy là tự giao + tự cài", "Waiting — assigned automatically")
                    : sec < 150 ? Ui.L("Khởi động lại vào bộ cài", "Restarting into setup")
                    : lx ? (sec < 45 * 60 ? Ui.L("Đang cài Linux CachyOS", "Installing Linux CachyOS") : Ui.L("Sắp xong…", "Almost done…"))
                    : sec < 15 * 60 ? Ui.L("Đang cài Windows ", "Installing Windows ") + osU
                    : sec < 26 * 60 ? Ui.L("Cài driver · khởi động lần đầu", "Drivers · first boot") : Ui.L("Sắp xong…", "Almost done…");
            bar.setProgress(pct);
            bar.setProgressTintList(android.content.res.ColorStateList.valueOf(late ? Ui.WAIT : Ui.SKY));
            t.setText(stage + " · " + pct + "% · " + Ui.L("đã chạy ", "elapsed ") + mmss(sec)
                    + (late ? Ui.L(" · lâu hơn bình thường", " · taking longer than usual") : Ui.L(" · thường ~", " · usually ~") + (exp / 60) + Ui.L(" phút", " min")));
            t.setTextColor(late ? Ui.WAIT : Ui.MUTED);
            rep.setVisibility(late ? View.VISIBLE : View.GONE);
            if (box.isAttachedToWindow() && !a.isFinishing()) box.postDelayed(tick[0], 1000);
        };
        box.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener() {
            @Override public void onViewAttachedToWindow(View v) { box.removeCallbacks(tick[0]); tick[0].run(); }
            @Override public void onViewDetachedFromWindow(View v) { box.removeCallbacks(tick[0]); }
        });
        tick[0].run();
        return box;
    }

    /** 📋 Báo admin: nội dung soạn sẵn (máy · việc / lỗi · tài khoản · lượt thuê · giờ) → copy + mở kênh liên hệ shop (web cài ở Cài đặt). */
    private static Button repBtn(MainActivity a, JSONObject x) {
        Button b = Ui.button(a, "📋 " + Ui.L("Báo admin", "Report to the admin"), Ui.GHOST);
        b.setOnClickListener(v -> report(a, x));
        return b;
    }

    private static void report(MainActivity a, JSONObject x) {
        JSONObject pc = x.optJSONObject("pc"), job = pc == null ? null : pc.optJSONObject("job"), lj = pc == null ? null : pc.optJSONObject("last_job");
        String[] st = state(x);
        long now = System.currentTimeMillis();
        String what = "warn".equals(st[0]) ? Ui.L("Cài lại hệ điều hành bị LỖI", "OS reinstall FAILED") + (lj != null && !lj.optString("msg").isEmpty() ? ": " + lj.optString("msg") : "")
                : "inst".equals(st[0]) && job != null ? Ui.L("Cài lại ", "Reinstall ") + osName(job.optString("os"))
                        + Ui.L(" — đã chạy ", " — running for ") + mmss((now - MainActivity.parseTime(job.optString("at", ""))) / 1000) + Ui.L(" chưa xong", "")
                : "wait".equals(st[0]) ? Ui.L("Chờ giao máy — đã chờ ", "Waiting for a machine — ") + mmss((now - MainActivity.parseTime(x.optString("created_at", ""))) / 1000)
                : st[1];
        String user = a.prof == null ? "" : a.prof.optString("username", "").trim();
        if (user.isEmpty()) user = a.prof == null || a.prof.optString("email", "").isEmpty() ? Api.email : a.prof.optString("email");
        final String msg = Ui.L("[CLOUDBLUE] VPS GPU CẦN HỖ TRỢ", "[CLOUDBLUE] GPU VPS NEEDS HELP")
                + "\n• " + Ui.L("Máy: ", "Machine: ") + (pc == null ? "—" : pc.optString("name")) + (pc != null && !pc.optString("code").isEmpty() ? " (№ " + pc.optString("code") + ")" : "")
                + "\n• " + Ui.L("Việc: ", "Problem: ") + what
                + "\n• " + Ui.L("Hệ điều hành: ", "OS: ") + x.optString("os_name")
                + "\n• " + Ui.L("Tài khoản: ", "Account: ") + user
                + "\n• " + Ui.L("Lượt thuê: #", "Rental: #") + (x.isNull("rental") ? "—" : x.optString("rental"))
                + "\n• " + Ui.L("Lúc: ", "Time: ") + MainActivity.fdate(now);
        try {
            android.content.ClipboardManager cm = (android.content.ClipboardManager) a.getSystemService(android.content.Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(android.content.ClipData.newPlainText("CloudBlue", msg));
        } catch (Exception ignored) { }
        LinearLayout c = Ui.col(a, 10);
        c.addView(Ui.muted(a, Ui.L("✓ Đã copy nội dung dưới đây. Bấm 1 kênh để mở, dán và gửi cho admin — shop xử lý ngay.",
                "✓ Copied. Open a channel, paste and send it to the admin.")));
        TextView m = Ui.text(a, msg, 12.5f, Ui.FG, false);
        m.setTypeface(android.graphics.Typeface.MONOSPACE);
        m.setTextIsSelectable(true);
        m.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(12), Ui.dp(10));
        m.setBackground(Ui.round(Color.argb(40, 0, 0, 0), 12, Color.argb(60, 159, 180, 216)));
        c.addView(m, Ui.fill());
        JSONObject d = Api.siteData;
        String[][] ch = {{"linkDc", "🎮 Discord"}, {"linkZl", "💬 Zalo"}, {"linkTg", "✈️ Telegram"}};
        for (String[] k : ch) {
            final String u = d == null ? "" : d.optString(k[0], "").trim();
            if (!u.matches("(?i)https?://.+")) continue;
            Button go = Ui.button(a, k[1], Ui.PRIMARY);
            go.setOnClickListener(v -> a.openWeb(u));
            c.addView(go, Ui.fill());
        }
        if (!Api.PLAY) {
            Button web = Ui.button(a, "🌐 " + Ui.L("Mở website ", "Open ") + Api.webHost(), Ui.GHOST);
            web.setOnClickListener(v -> a.openWeb(Api.WEB));
            c.addView(web, Ui.fill());
        }
        Ui.sheet(a, "📋 " + Ui.L("Báo admin", "Report to the admin"), c).show();
    }

    // ---------------------------------------------------------------- cài lại / đổi Windows
    private static void reinstall(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        if (pc == null) return;
        JSONArray os0 = mine == null ? null : mine.optJSONArray("os");
        if (os0 == null || os0.length() == 0) return;
        JSONArray can = pc.optJSONArray("can");                                    // 22.11f · SQL v50: máy đổi được sang bản nào (máy chủ cũ: ẩn Linux)
        JSONArray os = new JSONArray();
        boolean anyLin = lin(pc.optString("os"));
        for (int i = 0; i < os0.length(); i++) {
            JSONObject o = os0.optJSONObject(i);
            if (o == null) continue;
            String id = o.optString("id");
            boolean ok = can == null ? !lin(id) : id.equals(x.optString("os")) || has(can, id);
            if (ok) { os.put(o); anyLin |= lin(id); }
        }
        if (os.length() == 0) return;
        final String[] pick = {osOf(os, x.optString("os")) != null ? x.optString("os") : os.optJSONObject(0).optString("id")};
        LinearLayout c = Ui.col(a, 12);
        final TextView[] noteT = new TextView[1];
        c.addView(Ui.muted(a, Ui.L("Còn ", "") + x.optInt("left") + "/" + (mine == null ? 2 : mine.optInt("reinstall_max", 2)) + Ui.L(" lượt trong lượt thuê này", " reinstalls left in this rental")));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        for (int i = 0; i < os.length(); i++) {
            JSONObject o = os.optJSONObject(i);
            if (o == null) continue;
            TextView ch = Ui.chip(a, o.optString("name"), o.optString("id").equals(pick[0]));
            ch.setTag(o.optString("id"));
            ch.setOnClickListener(v -> { pick[0] = (String) v.getTag(); for (int k = 0; k < w.getChildCount(); k++) Ui.setChip((TextView) w.getChildAt(k), pick[0].equals(w.getChildAt(k).getTag()));
                noteT[0].setText(reNote(pick[0], pc.optString("os"))); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        LinearLayout note = Ui.card(a);
        noteT[0] = Ui.muted(a, reNote(pick[0], pc.optString("os")));
        note.addView(noteT[0]);
        c.addView(note, Ui.fill());
        Button ok = Ui.button(a, Ui.L("Cài lại ngay", "Reinstall now"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(a, "🔄 " + (anyLin ? Ui.L("Cài lại / đổi hệ điều hành", "Reinstall / switch the OS") : Ui.L("Cài lại / đổi Windows", "Reinstall / switch Windows")) + " · " + pc.optString("name"), c);
        final boolean curLin = lin(pc.optString("os"));
        ok.setOnClickListener(v -> Ui.confirm(a, Ui.L("Cài lại máy?", "Reinstall?"), Ui.L("Máy " + pc.optString("name") + " sẽ cài lại " + osName(pick[0]) + ". " + (curLin ? "Phần hệ điều hành Linux" : "Ổ C:") + " bị xoá.",
                pc.optString("name") + " will be reinstalled with " + osName(pick[0]) + ". " + (curLin ? "The Linux system" : "Drive C:") + " is erased."), Ui.L("Cài lại", "Reinstall"), () -> {
            ok.setEnabled(false);
            Api.bg(() -> Api.rpc("pc_my_reinstall", new JSONObject().put("p_pc", pc.optString("id")).put("p_os", pick[0])), r -> {
                d.dismiss();
                Ui.toast(a, Ui.L("Đã gửi lệnh cài lại — máy sẽ khởi động lại trong ít giây.", "Reinstall started."));
                mineAt = 0; a.refresh();
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        }));
        d.show();
    }

    static boolean has(JSONArray a, String v) {
        for (int i = 0; a != null && i < a.length(); i++) if (v.equals(a.optString(i))) return true;
        return false;
    }

    /** Lời cảnh báo hộp đổi hệ điều hành theo bản đang chọn (xoá phần nào, cài bao lâu, lưu ý Linux). */
    static String reNote(String to, String cur) {
        String sys = lin(cur) ? Ui.L("phần hệ điều hành Linux", "the Linux system") : Ui.L("ổ C: (Windows)", "drive C: (Windows)");
        return Ui.L("⚠️ Chỉ xoá " + sys + " — ổ khác giữ nguyên. Máy khởi động lại và cài trong " + instTime(to) + ". Dữ liệu đã xoá không lấy lại được.",
                "⚠️ Only " + sys + " is erased — other drives are kept. Takes " + instTime(to) + ". Erased data cannot be recovered.")
                + (lin(to) ? "\n" + linNote() : "");
    }

    // ---------------------------------------------------------------- bảng giá (sản phẩm bán tự động — admin chỉnh trên web)
    interface Done { void run(); }

    /** [pc_shop_info, sản phẩm] — đọc thẳng từ web: giá, gói ngày, tên, cấu hình, bản Windows bán đều do admin đặt. */
    static JSONObject[] fetchShop() throws Exception {
        try { Api.site(); } catch (Exception ignored) { }                        // 21/11f · trạng thái bảo trì VPS GPU luôn mới khi mở mục
        Object io = Api.rpc("pc_shop_info", new JSONObject());
        JSONObject i = io instanceof JSONObject ? (JSONObject) io : new JSONObject();
        JSONObject p = null;
        if (i.optBoolean("on") && !i.optString("product").isEmpty()) {
            Object o = Api.get("product_list?id=eq." + i.optString("product") + "&select=*");
            if (o instanceof JSONArray && ((JSONArray) o).length() > 0) p = ((JSONArray) o).getJSONObject(0);
        }
        return new JSONObject[]{i, p};
    }

    static void loadShop(MainActivity a, Done then) {
        Api.bg(PcVps::fetchShop, r -> { info = r[0]; prod = r[1]; infoAt = System.currentTimeMillis(); then.run(); },
                m -> Ui.toast(a, Ui.L("Chưa tải được bảng giá VPS GPU: ", "Couldn't load GPU VPS prices: ") + m));
    }

    static int[][] plans() {
        JSONArray pl = prod == null ? null : prod.optJSONArray("plans");
        java.util.ArrayList<int[]> out = new java.util.ArrayList<>();
        if (pl != null) for (int i = 0; i < pl.length(); i++) {
            JSONObject x = pl.optJSONObject(i);
            if (x != null && x.optInt("days") > 0 && x.optLong("price", -1) >= 0) out.add(new int[]{x.optInt("days"), (int) Math.min(Integer.MAX_VALUE, x.optLong("price"))});
        }
        java.util.Collections.sort(out, (p, q) -> p[0] - q[0]);
        return out.toArray(new int[0][]);
    }

    // ================================================================ 🖥️ TAB "VPS GPU" (21/11e) — trang mua riêng cho 1 cấu hình
    //  Thẻ cấu hình nổi bật · ① chọn Windows · ② chọn thời gian · mã giảm giá · thanh thanh toán dưới màn hình · VPS GPU của bạn ở đầu trang.
    //  Mọi con số / chữ của sản phẩm lấy từ web (admin sửa trên web → app đổi theo khi mở trang); bấm mua → đọc lại giá mới nhất trước khi hỏi.
    static final String VIDEO = "/video/vps-gpu.mp4";       // video hướng dẫn 3 cách điều khiển (app điện thoại · app máy tính · web)
    static String tOs = "", tCode = "";
    static int tDays = 0;
    static boolean tLoading = false;
    static String tErr = "";
    static long tErrAt = 0;
    static double tShown = -1;                               // tổng tiền đang hiện (so với giá đọc lại lúc bấm mua)
    static Promo tPromo = null;

    /** Đọc lại bảng giá rồi vẽ lại tab (lỗi → thử lại tối đa 1 lần / 15 giây khi trang vẽ lại). */
    static void loadTab(MainActivity a) {
        if (tLoading) return;
        tLoading = true;
        Api.bg(PcVps::fetchShop, r -> { tLoading = false; tErr = ""; info = r[0]; prod = r[1]; infoAt = System.currentTimeMillis(); a.vpsChanged(); },
                m -> { tLoading = false; tErr = m == null ? "?" : m; tErrAt = System.currentTimeMillis(); a.vpsChanged(); });
    }

    static String pName() {
        if (prod == null) return "VPS GPU";
        String en = prod.optString("name_en", "");
        return !Ui.vi() && !en.isEmpty() && !"null".equals(en) ? en : prod.optString("name", "VPS GPU");
    }

    static String pDesc() {
        if (prod == null) return "";
        String en = prod.optString("description_en", ""), vi = prod.optString("description", "");
        String d = !Ui.vi() && !en.isEmpty() && !"null".equals(en) ? en : vi;
        return d == null || "null".equals(d) ? "" : d.trim();
    }

    static JSONArray pFeats() {
        if (prod == null) return new JSONArray();
        JSONArray en = prod.optJSONArray("features_en"), vi = prod.optJSONArray("features");
        if (!Ui.vi() && en != null && en.length() > 0) return en;
        return vi == null ? new JSONArray() : vi;
    }

    static JSONObject osOf(JSONArray os, String id) {
        if (os == null || id == null) return null;
        for (int i = 0; i < os.length(); i++) { JSONObject o = os.optJSONObject(i); if (o != null && id.equals(o.optString("id"))) return o; }
        return null;
    }

    static int priceOf(int[][] pl, int days) { for (int[] p : pl) if (p[0] == days) return p[1]; return -1; }

    /** "Windows 10 Pro 22H2" → ["Windows 10 Pro", "22H2"]. */
    static String[] osSplit(JSONObject o) {
        String n = o == null ? "" : o.optString("name", o.optString("id")).trim();
        if (n.isEmpty()) n = o == null ? "" : o.optString("id");
        int k = n.lastIndexOf(' ');
        return k > 0 ? new String[]{n.substring(0, k), n.substring(k + 1)} : new String[]{"Windows", n};
    }

    private static TextView specChip(MainActivity a, String f) {
        String l = f.toLowerCase(java.util.Locale.ROOT), ic = "✨";
        if (l.contains("ram")) ic = "🧠";
        else if (l.matches(".*(gtx|rtx|gpu|vga|radeon|quadro|card).*")) ic = "🎮";
        else if (l.matches(".*(ssd|nvme|hdd|disk|ổ).*")) ic = "💾";
        else if (l.matches(".*(xeon|core|ryzen|cpu|nhân|luồng|i[3579]-|\\d{4} ?v\\d).*")) ic = "⚙️";
        else if (l.matches(".*(mbps|gbps|mạng|wifi|lan|net).*")) ic = "🌐";
        else if (l.matches(".*(win|windows).*")) ic = "🪟";
        TextView t = Ui.text(a, ic + " " + f, 13, Ui.LIGHT ? Ui.FG : Color.WHITE, true);
        t.setPadding(Ui.dp(11), Ui.dp(6), Ui.dp(11), Ui.dp(7));
        t.setBackground(Ui.round(Ui.LIGHT ? Color.argb(215, 255, 255, 255) : Color.argb(40, 255, 255, 255), 99,
                Ui.LIGHT ? Color.argb(70, 43, 110, 240) : Color.argb(80, 255, 255, 255)));
        return t;
    }

    private static View benefit(MainActivity a, String icon, String title, String sub) {
        LinearLayout r = Ui.row(a, 10);
        r.setGravity(Gravity.TOP);
        TextView ic = Ui.text(a, icon, 20, Ui.FG, false);
        r.addView(ic, Ui.wrap());
        LinearLayout t = Ui.col(a, 1);
        t.addView(Ui.text(a, title, 13.5f, Ui.FG, true));
        t.addView(Ui.text(a, sub, 12, Ui.MUTED, false));
        r.addView(t, Ui.weight(1));
        return r;
    }

    /** Dựng trang VPS GPU vào body. Trả thanh thanh toán (gắn dưới màn hình) hoặc null (đang tải / chưa mở bán). */
    static View tab(MainActivity a, LinearLayout body) {
        LinearLayout head = Ui.row(a, 10);
        head.addView(Ui.h1(a, Ui.L("VPS GPU", "GPU VPS")), Ui.weight(1));
        TextView vid = Ui.pill(a, "🎬 " + Ui.L("Hướng dẫn", "How to use"), Ui.SKY);
        vid.setPadding(Ui.dp(12), Ui.dp(6), Ui.dp(12), Ui.dp(7));
        vid.setContentDescription(Ui.L("Video hướng dẫn", "Video guide"));
        vid.setOnClickListener(v -> a.openWeb(Api.WEB + VIDEO));
        head.addView(vid, Ui.wrap());
        body.addView(head, Ui.fill());
        body.addView(Ui.muted(a, Ui.L("Máy tính thật có card đồ hoạ rời — cả máy chỉ mình bạn dùng. Chọn Windows + thời gian thuê, hệ thống tự giao máy và cài sẵn cho bạn.",
                "A real PC with a dedicated graphics card — the whole machine is yours. Pick Windows and a rental time; a machine is assigned and set up for you.")), Ui.fill());
        if (!maint(a).isEmpty()) body.addView(maintCard(a, maint(a)), Ui.fill());   // 21/11f · bảo trì riêng VPS GPU
        int nMine = live();                                                     // 21.11k: tab này chỉ để MUA — quản lý / điều khiển ở Máy của tôi (như Cloud Phone)
        if (nMine > 0) {
            LinearLayout r = Ui.row(a, 12);
            r.setGravity(Gravity.CENTER_VERTICAL);
            r.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(12), Ui.dp(11));
            r.setBackground(Ui.round(Ui.LIGHT ? Color.argb(24, 43, 110, 240) : Color.argb(40, 90, 175, 255), 16, Color.argb(120, 90, 175, 255)));
            r.addView(Ui.text(a, "🖥️", 22, Ui.FG, false), Ui.wrap());
            LinearLayout tx = Ui.col(a, 2);
            tx.addView(Ui.text(a, Ui.L("Bạn đang có " + nMine + " VPS GPU", "You have " + nMine + " GPU VPS"), 15, Ui.FG, true));
            tx.addView(Ui.muted(a, Ui.L("Điều khiển · gia hạn · cài lại · huỷ máy ở Máy của tôi", "Control · renew · reinstall · cancel in My machines")));
            r.addView(tx, Ui.weight(1));
            r.addView(Ui.text(a, "›", 26, Ui.SKY, true), Ui.wrap());
            r.setClickable(true);
            r.setOnClickListener(v -> a.show(0));
            body.addView(r, Ui.fill());
        }
        if (mine == null || System.currentTimeMillis() - mineAt > 15000)          // số máy của khách (cho dòng trên) — tải ngầm
            Api.bg(() -> Api.rpc("pc_my_vps", new JSONObject()), r -> { if (r instanceof JSONObject) { boolean was = mine == null; mine = (JSONObject) r; mineAt = System.currentTimeMillis(); if (was && live() > 0 && !a.isFinishing()) a.refresh(); } }, m -> { });
        boolean stale = info == null || System.currentTimeMillis() - infoAt > 45000;
        if (stale && System.currentTimeMillis() - tErrAt > 15000) loadTab(a);   // mở trang / quá 45 giây → đọc lại giá admin đặt
        if (info == null) {
            LinearLayout c = Ui.card(a);
            boolean bad = !tErr.isEmpty() && !tLoading;
            c.addView(Ui.muted(a, bad ? "⚠ " + Ui.L("Chưa tải được bảng giá: ", "Couldn't load prices: ") + tErr : "⏳ " + Ui.L("Đang tải bảng giá…", "Loading prices…")));
            if (bad) {
                Button r = Ui.button(a, Ui.L("Thử lại", "Retry"), Ui.GHOST);
                r.setOnClickListener(v -> { tErrAt = 0; loadTab(a); });
                c.addView(r, Ui.fill());
            }
            body.addView(c, Ui.fill());
            return null;
        }
        final int[][] pl = plans();
        final JSONArray os = info.optJSONArray("os");
        if (!info.optBoolean("on") || prod == null || pl.length == 0 || os == null || os.length() == 0) {
            LinearLayout c = Ui.card(a);
            c.addView(Ui.text(a, "🖥️ " + Ui.L("VPS GPU tạm chưa mở bán", "GPU VPS isn't on sale right now"), 16.5f, Ui.FG, true));
            c.addView(Ui.muted(a, Ui.L("Shop đang chuẩn bị máy — quay lại sau ít phút, hoặc xem trên web.", "Please check back soon, or visit the website.")));
            body.addView(c, Ui.fill());
            return null;
        }
        if (osOf(os, tOs) == null) {                                            // mặc định: bản đang có máy giao ngay
            tOs = "";
            for (int i = 0; i < os.length(); i++) { JSONObject o = os.optJSONObject(i); if (o != null && o.optBoolean("fast") && !o.optString("id").isEmpty()) { tOs = o.optString("id"); break; } }
            if (tOs.isEmpty()) for (int i = 0; i < os.length(); i++) { JSONObject o = os.optJSONObject(i); if (o != null && !o.optString("id").isEmpty()) { tOs = o.optString("id"); break; } }
        }
        if (priceOf(pl, tDays) < 0) { tDays = pl[0][0]; for (int[] p : pl) if (p[0] == 30) tDays = 30; }
        final int mx = info.optInt("reinstall_max", 2);
        final boolean ready = info.optBoolean("ready");
        final boolean light = Ui.LIGHT;
        final int heroFg = light ? Ui.FG : Color.WHITE, heroSub = light ? Ui.MUTED : Color.rgb(203, 222, 255);

        // ---- thẻ cấu hình (1 cấu hình duy nhất → làm to, nổi bật)
        LinearLayout hero = Ui.col(a, 12);
        hero.setPadding(Ui.dp(18), Ui.dp(18), Ui.dp(18), Ui.dp(18));
        android.graphics.drawable.GradientDrawable hg = new android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
                light ? new int[]{Color.rgb(222, 236, 255), Color.rgb(233, 228, 255)} : new int[]{Color.rgb(22, 64, 150), Color.rgb(46, 28, 118), Color.rgb(11, 22, 58)});
        hg.setCornerRadius(Ui.dp(Ui.rad(22)));
        hg.setStroke(Math.max(2, Ui.dp(1.5f)), light ? Color.argb(90, 43, 110, 240) : Color.argb(150, 124, 188, 255));
        hero.setBackground(hg);
        hero.setElevation(Ui.dp(4));
        LinearLayout top = Ui.row(a, 12);
        TextView ic = Ui.text(a, "🖥️", 30, heroFg, false);
        ic.setGravity(Gravity.CENTER);
        android.graphics.drawable.GradientDrawable ig = new android.graphics.drawable.GradientDrawable();
        ig.setShape(android.graphics.drawable.GradientDrawable.OVAL);
        ig.setColor(light ? Color.argb(36, 43, 110, 240) : Color.argb(56, 140, 196, 255));
        ig.setStroke(Math.max(2, Ui.dp(1.5f)), light ? Color.argb(60, 43, 110, 240) : Color.argb(90, 190, 225, 255));
        ic.setBackground(ig);
        top.addView(ic, new LinearLayout.LayoutParams(Ui.dp(60), Ui.dp(60)));
        LinearLayout tt = Ui.col(a, 2);
        tt.addView(Ui.text(a, pName(), 21, heroFg, true));
        tt.addView(Ui.text(a, Ui.L("Máy PC thật · 1 cấu hình · tự giao + tự cài Windows", "Real PC · one configuration · auto delivery + Windows setup"), 12.5f, heroSub, false));
        top.addView(tt, Ui.weight(1));
        hero.addView(top, Ui.fill());
        JSONArray ft = pFeats();
        if (ft.length() > 0) {
            Ui.Wrap fw = new Ui.Wrap(a, 6);
            for (int i = 0; i < ft.length(); i++) { String f = ft.optString(i, "").trim(); if (!f.isEmpty() && !"null".equals(f)) fw.addView(specChip(a, f)); }
            hero.addView(fw, Ui.fill());
        }
        String desc = pDesc();
        if (!desc.isEmpty()) hero.addView(Ui.text(a, desc, 13, heroSub, false), Ui.fill());
        int best = 0;                                                           // gói rẻ nhất tính theo ngày
        for (int k = 1; k < pl.length; k++) if ((double) pl[k][1] / pl[k][0] < (double) pl[best][1] / pl[best][0]) best = k;
        LinearLayout pr = Ui.row(a, 10);
        LinearLayout pc0 = Ui.col(a, 0);
        pc0.addView(Ui.text(a, Ui.L("chỉ từ", "from"), 12, heroSub, false));
        pc0.addView(Ui.text(a, Ui.vnd(a.ctv(pl[best][1]) / (double) pl[best][0]) + Ui.L(" / ngày", " / day"), 23, light ? Ui.SKY : Color.WHITE, true));
        pr.addView(pc0, Ui.weight(1));
        pr.addView(Ui.pill(a, ready ? "⚡ " + Ui.L("Có máy sẵn", "In stock") : "⏳ " + Ui.L("Đặt trước — có máy là giao", "Pre-order"), ready ? Ui.OK : Ui.WAIT), Ui.wrap());
        hero.addView(pr, Ui.fill());
        body.addView(hero, Ui.fill());

        // ---- quyền lợi
        LinearLayout bn = Ui.card(a);
        String[][] bl = {
                {"⚡", Ui.L("Tự giao + cài Windows", "Auto delivery + setup"), Ui.L("Không cần nhắn shop", "No need to message the shop")},
                {"🎮", Ui.L("Chuột + phím thật", "Real mouse + keyboard"), Ui.L("Web · app điện thoại · app máy tính", "Web · phone app · PC app")},
                {"🔁", Ui.L("Đổi / cài lại Windows", "Switch / reinstall Windows"), mx + Ui.L(" lần mỗi lượt thuê", " times per rental")},
                {"🔒", Ui.L("Máy riêng của bạn", "Your own machine"), Ui.L("Trả máy là xoá sạch dữ liệu", "Wiped clean when returned")}};
        for (int i = 0; i < bl.length; i += 2) {
            LinearLayout r = Ui.row(a, 12);
            r.setGravity(Gravity.TOP);
            for (int k = i; k < Math.min(i + 2, bl.length); k++) r.addView(benefit(a, bl[k][0], bl[k][1], bl[k][2]), Ui.weight(1));
            bn.addView(r, Ui.fill());
        }
        body.addView(bn, Ui.fill());

        final Runnable[] upd = new Runnable[1];
        final Runnable changed = () -> { if (upd[0] != null) upd[0].run(); };

        // ---- ① Windows
        LinearLayout s1 = Ui.card(a);
        boolean anyLin = false;
        for (int i = 0; i < os.length(); i++) { JSONObject o = os.optJSONObject(i); if (o != null && (o.optBoolean("linux") || lin(o.optString("id")))) anyLin = true; }
        s1.addView(a.stepHead("1", anyLin ? Ui.L("Chọn hệ điều hành", "Choose the OS") : Ui.L("Chọn Windows", "Choose Windows"), Ui.L("Đổi được trong lượt thuê (" + mx + " lần).", "Switchable during the rental (" + mx + " times).")), Ui.fill());
        final LinearLayout ow = Ui.row(a, 8);
        for (int i = 0; i < os.length(); i++) {
            final JSONObject o = os.optJSONObject(i);
            if (o == null || o.optString("id").isEmpty()) continue;
            String[] nm = osSplit(o);
            LinearLayout t = Ui.col(a, 2);
            t.setGravity(Gravity.CENTER);
            t.setPadding(Ui.dp(8), Ui.dp(12), Ui.dp(8), Ui.dp(12));
            t.setTag(o.optString("id"));
            t.setClickable(true);
            t.setFocusable(true);
            t.setContentDescription(nm[0] + " " + nm[1]);
            TextView k1 = Ui.text(a, nm[0], 11.5f, Ui.MUTED, true);
            TextView k2 = Ui.text(a, nm[1], 24, Ui.FG, true);
            boolean rdy = o.has("ready") ? o.optBoolean("ready") : ready;              // SQL v50: có máy trống cài được ĐÚNG bản này
            String inst = lin(o.optString("id")) ? Ui.L("Cài ~45 phút", "~45 min setup") : Ui.L("Cài ~20 phút", "~20 min setup");
            TextView k3 = Ui.text(a, o.optBoolean("fast") ? "⚡ " + Ui.L("Giao ngay", "Instant") : "⏳ " + (rdy ? inst : Ui.L("Chờ máy", "Waiting")), 11.5f, o.optBoolean("fast") ? Ui.OK : Ui.WAIT, true);
            for (TextView x : new TextView[]{k1, k2, k3}) { x.setGravity(Gravity.CENTER); t.addView(x, Ui.fill()); }
            t.setOnClickListener(v -> { tOs = String.valueOf(v.getTag()); changed.run(); });
            Ui.press(t);
            ow.addView(t, Ui.weight(1));
        }
        s1.addView(ow, Ui.fill());
        final TextView osHint = Ui.text(a, "", 12.5f, Ui.MUTED, false);
        s1.addView(osHint, Ui.fill());
        body.addView(s1, Ui.fill());
        final Runnable paintOs = () -> {
            for (int k = 0; k < ow.getChildCount(); k++) {
                LinearLayout t = (LinearLayout) ow.getChildAt(k);
                boolean on = tOs.equals(t.getTag());
                if (on) t.setBackground(Ui.gloss(18)); else t.setBackground(Ui.round(Ui.PANEL2, 18, Ui.RING));
                ((TextView) t.getChildAt(0)).setTextColor(on ? Color.rgb(222, 236, 255) : Ui.MUTED);
                ((TextView) t.getChildAt(1)).setTextColor(on ? Color.WHITE : Ui.FG);
                JSONObject o = osOf(os, String.valueOf(t.getTag()));
                ((TextView) t.getChildAt(2)).setTextColor(on ? Color.WHITE : o != null && o.optBoolean("fast") ? Ui.OK : Ui.WAIT);
            }
            JSONObject o = osOf(os, tOs);
            boolean rdy = o != null && o.has("ready") ? o.optBoolean("ready") : ready, lx = o != null && lin(o.optString("id"));
            osHint.setText((o != null && o.optBoolean("fast") ? Ui.L("⚡ Có máy sẵn bản này — thanh toán xong vào điều khiển được ngay.", "⚡ A machine with this version is ready — use it right after payment.")
                    : rdy && lx ? Ui.L("⏳ Máy tự cài bản này cho bạn khoảng 30–60 phút (hạn thuê được cộng thêm 60 phút).", "⏳ Installed for you in ~30–60 min (60 min added to your time).")
                    : rdy ? Ui.L("⏳ Máy tự cài bản này cho bạn khoảng 20 phút (hạn thuê được cộng thêm 30 phút).", "⏳ This version is installed for you in ~20 min (30 min added to your time).")
                    : Ui.L("⏳ Shop đang chuẩn bị máy — có máy là tự giao + cài, không cần nhắn shop.", "⏳ Preparing a machine — delivered and installed automatically."))
                    + (lx ? "\n" + linNote() : ""));
            osHint.setTextColor(o != null && o.optBoolean("fast") ? Ui.OK : Ui.WAIT);
        };

        // ---- ② thời gian thuê
        LinearLayout s2 = Ui.card(a);
        s2.addView(a.stepHead("2", Ui.L("Chọn thời gian thuê", "Choose rental time"), Ui.L("Hết hạn thì gia hạn ngay trong app.", "Renew anytime in the app.")), Ui.fill());
        final LinearLayout plw = Ui.col(a, 8);
        final double base = a.ctv(pl[0][1]) / (double) pl[0][0];                  // giá / ngày của gói ngắn nhất
        for (final int[] p : pl) {
            LinearLayout r = Ui.row(a, 10);
            r.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(12));
            r.setTag(p[0]);
            r.setClickable(true);
            r.setFocusable(true);
            TextView chk = Ui.text(a, "○", 18, Ui.MUTED, true);
            r.addView(chk, Ui.wrap());
            LinearLayout l = Ui.col(a, 1);
            double pd = a.ctv(p[1]) / (double) p[0];
            l.addView(Ui.text(a, p[0] + Ui.L(" ngày", " days"), 16, Ui.FG, true));
            l.addView(Ui.text(a, Ui.vnd(pd) + Ui.L(" / ngày", " / day"), 12.5f, Ui.MUTED, false));
            r.addView(l, Ui.weight(1));
            LinearLayout rr = Ui.col(a, 3);
            rr.setGravity(Gravity.END);
            TextView pv = Ui.text(a, Ui.vnd(a.ctv(p[1])), 17, Ui.SKY, true);
            pv.setGravity(Gravity.END);
            rr.addView(pv, Ui.wrap());
            int save = base > 0 ? (int) Math.round((1 - pd / base) * 100) : 0;
            if (save >= 1) rr.addView(Ui.pill(a, "−" + save + "%" + Ui.L(" / ngày", " / day"), Ui.OK), Ui.wrap());
            r.addView(rr, Ui.wrap());
            r.setOnClickListener(v -> { tDays = (int) v.getTag(); changed.run(); });
            Ui.press(r);
            plw.addView(r, Ui.fill());
        }
        s2.addView(plw, Ui.fill());
        body.addView(s2, Ui.fill());
        final Runnable paintPl = () -> {
            for (int k = 0; k < plw.getChildCount(); k++) {
                LinearLayout r = (LinearLayout) plw.getChildAt(k);
                boolean on = ((int) r.getTag()) == tDays;
                android.graphics.drawable.GradientDrawable g = Ui.round(on ? (light ? Color.rgb(232, 241, 255) : Color.rgb(24, 52, 112)) : Ui.PANEL, 16, 0);
                g.setStroke(Math.max(2, Ui.dp(on ? 2f : 1f)), on ? Ui.BLUE : Ui.LINE2);
                r.setBackground(g);
                TextView chk = (TextView) r.getChildAt(0);
                chk.setText(on ? "✓" : "○");
                chk.setTextColor(on ? Ui.BLUE : Ui.MUTED);
            }
        };

        // ---- 🏷️ mã giảm giá (kiểm theo đúng đơn đang chọn, như web)
        tPromo = new Promo(a, "vps_new", () -> prod == null ? null : new JSONObject().put("p_product", prod.optString("id")).put("p_days", tDays).put("p_qty", 1), changed);
        LinearLayout pz = Ui.card(a);
        pz.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(14));
        pz.addView(tPromo.view, Ui.fill());
        body.addView(pz, Ui.fill());
        body.addView(Ui.text(a, Ui.L("Giá theo bảng giá shop (giảm CTV tự áp dụng). Hạn thuê tính từ lúc giao máy.", "Prices follow the shop's price list (reseller discount applied). Time starts when the machine is assigned."),
                12, Ui.MUTED, false), Ui.fill());

        // ---- thanh thanh toán dưới màn hình
        final TextView sumL = Ui.text(a, "", 12, Ui.MUTED, true);
        sumL.setMaxLines(1);
        sumL.setEllipsize(android.text.TextUtils.TruncateAt.END);
        final TextView total = Ui.text(a, "", 22, Ui.SKY, true);
        final TextView calc = Ui.text(a, "", 11.5f, Ui.MUTED, false);
        calc.setMaxLines(2);
        final TextView err = Ui.text(a, "", 12.5f, Ui.BAD, false);
        final Button buy = Ui.button(a, "", Ui.PRIMARY);
        upd[0] = () -> {
            paintOs.run();
            paintPl.run();
            double t0 = a.ctv(Math.max(0, priceOf(pl, tDays)));
            if (tPromo != null) { tCode = tPromo.code; tPromo.onOrderChanged(); }
            double t = tPromo == null ? t0 : tPromo.price(t0), bal = a.prof.optDouble("balance", 0);
            tShown = t;
            String[] nm = osSplit(osOf(os, tOs));
            sumL.setText(pName() + " · " + nm[1] + " · " + tDays + Ui.L(" ngày", " days"));
            total.setText(Ui.vnd(t));
            calc.setText(Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal) + (t < t0 ? "  ·  🏷️ −" + Ui.vnd(t0 - t) : "")
                    + (a.isCtv() ? "  ·  CTV −" + a.prof.optInt("ctv_discount") + "%" : ""));
            err.setText(bal < t ? Ui.L("Số dư không đủ — cần nạp thêm ", "Not enough balance — top up ") + Ui.vnd(t - bal) : "");
            err.setVisibility(err.getText().length() == 0 ? View.GONE : View.VISIBLE);
            buy.setText(bal < t ? Ui.L("Nạp tiền", "Top up") : Ui.L("Mua ngay", "Buy now"));
        };
        LinearLayout sum = Ui.col(a, 6);
        sum.setPadding(Ui.dp(16), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        android.graphics.drawable.GradientDrawable sbg = new android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
                light ? new int[]{Color.WHITE, Color.rgb(238, 244, 255)} : new int[]{Color.rgb(22, 44, 104), Color.rgb(9, 19, 50)});
        sbg.setCornerRadius(Ui.dp(Ui.rad(20)));
        sbg.setStroke(Math.max(2, Ui.dp(1.5f)), light ? Color.argb(80, 43, 110, 240) : Color.argb(120, 124, 188, 255));
        sum.setBackground(sbg);
        sum.setElevation(Ui.dp(10));
        sum.addView(err, Ui.fill());
        LinearLayout sr = Ui.row(a, 10);
        LinearLayout st = Ui.col(a, 0);
        st.addView(sumL);
        st.addView(total);
        st.addView(calc);
        sr.addView(st, Ui.weight(1));
        buy.setMinWidth(Ui.dp(124));
        sr.addView(buy, Ui.wrap());
        sum.addView(sr, Ui.fill());
        buy.setOnClickListener(v -> {
            if (!maint(a).isEmpty()) { Ui.toast(a, maint(a)); return; }               // 21/11f · bảo trì riêng VPS GPU → không mua mới
            Runnable go = () -> {
                buy.setEnabled(false);
                Api.bg(PcVps::fetchShop, r -> {                                 // đọc lại giá admin đặt NGAY trước khi hỏi
                    buy.setEnabled(true);
                    info = r[0]; prod = r[1]; infoAt = System.currentTimeMillis();
                    int[][] pl2 = plans();
                    JSONObject o2 = osOf(info.optJSONArray("os"), tOs);
                    int price = priceOf(pl2, tDays);
                    if (!info.optBoolean("on") || prod == null || price < 0 || o2 == null) {
                        Ui.toast(a, Ui.L("Bảng giá vừa được shop cập nhật — xem lại rồi bấm mua.", "The price list just changed — please review."));
                        a.vpsChanged();
                        return;
                    }
                    double t0 = a.ctv(price), t = tPromo == null ? t0 : tPromo.price(t0), bal = a.prof.optDouble("balance", 0);
                    if (Math.abs(t - tShown) > 0.5) {
                        Ui.toast(a, Ui.L("Giá vừa được shop cập nhật: ", "Price updated: ") + Ui.vnd(t) + Ui.L(" — xem lại rồi bấm mua.", " — please review."));
                        a.vpsChanged();
                        return;
                    }
                    if (bal < t) { a.openTopup(t - bal); return; }
                    final String code = tPromo == null ? null : tPromo.send();
                    String[] nm = osSplit(o2);
                    Ui.confirm(a, Ui.L("Xác nhận mua VPS GPU", "Confirm GPU VPS"),
                            pName() + "\n" + nm[0] + " " + nm[1] + " · " + tDays + Ui.L(" ngày", " days") + "\n"
                                    + (code != null ? "🏷️ " + code + "  −" + Ui.vnd(t0 - t) + "\n" : "")
                                    + Ui.L("Trừ ", "Charge ") + Ui.vnd(t) + Ui.L(" từ số dư.", " from balance."),
                            Ui.L("Thanh toán", "Pay"), () -> place(a, buy, code));
                }, m -> { buy.setEnabled(true); Ui.toast(a, err(m)); });
            };
            if (tPromo == null) go.run(); else tPromo.ensure(go);
        });
        if (!tCode.isEmpty()) { tPromo.in.setText(tCode); tPromo.check(null); }
        upd[0].run();
        return sum;
    }

    private static void place(MainActivity a, Button buy, String code) {
        if (prod == null) return;
        buy.setEnabled(false);
        final String prodId = prod.optString("id"), os0 = tOs;
        final int dd = tDays;
        Api.bg(() -> {
            JSONObject args = new JSONObject().put("p_product", prodId).put("p_days", dd).put("p_os", os0);
            if (code != null) args.put("p_promo", code);
            return Api.rpc("pc_buy", args);
        }, r -> {
            buy.setEnabled(true);
            JSONObject res = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
            boolean act = "active".equals(res.optString("state"));
            Ui.toast(a, act ? (res.optBoolean("reinstall") ? (lin(tOs) ? Ui.L("🎉 Đã giao máy " + res.optString("name") + " — máy đang tự cài Linux CachyOS (30–60 phút), xem ở đầu trang.", "🎉 Machine assigned — installing Linux CachyOS (30–60 min).")
                            : Ui.L("🎉 Đã giao máy " + res.optString("name") + " — máy đang tự cài Windows (~20 phút), xem ở đầu trang.", "🎉 Machine assigned — installing Windows (~20 min)."))
                            : Ui.L("🎉 Đã giao máy " + res.optString("name") + " — bấm ▶ Điều khiển ở đầu trang.", "🎉 Your machine is ready — tap ▶ Control at the top."))
                    : Ui.L("⏳ Đã nhận đơn — có máy là tự giao + cài Windows, không cần nhắn shop.", "⏳ Order received — delivered automatically."));
            tCode = ""; mineAt = 0; infoAt = 0;
            a.refresh();
            a.vpsChanged();
        }, m -> {
            buy.setEnabled(true);
            if (tPromo != null && tPromo.fail(m)) return;
            Ui.toast(a, err(m));
        });
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
                boolean held = MainActivity.parseTime(x.optString("grace_until", "")) > 0;          // 21/11f · đang giữ máy (đã khoá) → tự mở lại
                Ui.toast(a, off ? Ui.L("Đã gia hạn. Máy đã tắt lúc hết hạn — shop sẽ bật lại cho bạn.", "Renewed. The shop will turn the machine back on.")
                        : held ? Ui.L("Đã gia hạn — máy tự mở lại sau khoảng 1–2 phút, dữ liệu giữ nguyên.", "Renewed — the machine unlocks in about 1–2 minutes.") : Ui.L("Đã gia hạn.", "Renewed."));
                mineAt = 0; a.refresh();
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }
}
