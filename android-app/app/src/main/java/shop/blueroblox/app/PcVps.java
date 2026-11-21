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
            }, m -> { });
        }
    }

    /** 21/11f · bảo trì riêng VPS GPU (khách thường) → câu báo; không bảo trì / admin → "". */
    static String maint(MainActivity a) { return a.isAdmin() ? "" : Api.pcMaintMsg(); }

    private static View maintCard(MainActivity a, String m) {
        TextView t = Ui.text(a, m, 13.5f, Ui.FG, true);
        t.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(14), Ui.dp(11));
        t.setBackground(Ui.round(Color.argb(34, 255, 200, 97), 14, Color.argb(150, 255, 200, 97)));
        return t;
    }

    private static JSONArray items() { return mine == null ? new JSONArray() : mine.optJSONArray("items") == null ? new JSONArray() : mine.optJSONArray("items"); }

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
        if (!Api.SHOP) { section(a, body); return; }
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
        box.addView(head, Ui.fill());
        String mt = maint(a);
        if (!mt.isEmpty()) box.addView(maintCard(a, mt), Ui.fill());
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
        JSONObject lj = pc.optJSONObject("last_job");                               // 21/11f · lần cài lại gần nhất bị lỗi (như web)
        if (lj != null && "failed".equals(lj.optString("state"))) return new String[]{"warn", "⚠️ " + Ui.L("Cài lại chưa xong", "Reinstall failed"),
                Ui.L("Lần cài lại vừa rồi bị lỗi — bấm 📋 Báo admin để shop xử lý.", "The last reinstall failed — tap 📋 Report to the admin.")};
        return new String[]{"run", "● " + Ui.L("Sẵn sàng", "Ready"), ""};
    }

    private static View card(MainActivity a, JSONObject x) {
        final JSONObject pc = x.optJSONObject("pc");
        String[] st = state(x);
        LinearLayout c = Ui.card(a);
        boolean run = "run".equals(st[0]);
        if (run) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(130, 60, 224, 176)));
        else if ("exp".equals(st[0]) || "wait".equals(st[0]) || "warn".equals(st[0])) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(150, 255, 200, 97)));
        LinearLayout top = Ui.row(a, 8);
        top.addView(Ui.pill(a, st[1], run ? Ui.OK : "exp".equals(st[0]) ? Ui.BAD : "warn".equals(st[0]) ? Ui.WAIT : Ui.SKY), Ui.wrap());
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
        if (!st[2].isEmpty()) c.addView(Ui.text(a, st[2], 13, "exp".equals(st[0]) || "warn".equals(st[0]) ? Ui.BAD : "off".equals(st[0]) ? Ui.WAIT : Ui.MUTED, false));
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
        if (pc != null && "active".equals(x.optString("state"))) {
            LinearLayout acts = Ui.row(a, 8);
            Button open = Ui.button(a, "▶ " + Ui.L("Điều khiển", "Control"), Ui.PRIMARY);
            final boolean mtOn = !maint(a).isEmpty();                               // 21/11f · bảo trì riêng VPS GPU → khoá điều khiển
            final boolean ctl = (run || "warn".equals(st[0])) && !mtOn;
            open.setEnabled(ctl);
            open.setAlpha(ctl ? 1f : 0.5f);
            open.setOnClickListener(v -> control(a, pc.optString("id"), pc.optString("name")));
            acts.addView(open, Ui.weight(1));
            if (!x.isNull("rental")) {
                int left = x.optInt("left"), max = mine == null ? 2 : mine.optInt("reinstall_max", 2);
                Button re = Ui.button(a, "🔄 " + left + "/" + max, Ui.GHOST);
                boolean canRe = left > 0 && !"inst".equals(st[0]) && !"exp".equals(st[0]) && maint(a).isEmpty();
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
        final long start = t0 > 0 ? t0 : System.currentTimeMillis(), exp = (inst ? 25 : 10) * 60L;
        final String osU = os == null ? "" : os.toUpperCase();
        final Runnable[] tick = new Runnable[1];
        tick[0] = () -> {
            long sec = Math.max(0, (System.currentTimeMillis() - start) / 1000);
            int pct = (int) Math.min(inst ? 96 : 90, Math.max(2, Math.round(100 * (1 - Math.exp(-sec / (exp * .55))))));
            boolean late = sec > exp * (inst ? 2 : 3);
            String stage = !inst ? Ui.L("Đang chờ máy — có máy là tự giao + cài Windows", "Waiting — assigned automatically")
                    : sec < 150 ? Ui.L("Khởi động lại vào bộ cài", "Restarting into setup")
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
        String what = "warn".equals(st[0]) ? Ui.L("Cài lại Windows bị LỖI", "Windows reinstall FAILED") + (lj != null && !lj.optString("msg").isEmpty() ? ": " + lj.optString("msg") : "")
                : "inst".equals(st[0]) && job != null ? Ui.L("Cài lại Windows ", "Reinstall ") + job.optString("os").toUpperCase()
                        + Ui.L(" — đã chạy ", " — running for ") + mmss((now - MainActivity.parseTime(job.optString("at", ""))) / 1000) + Ui.L(" chưa xong", "")
                : "wait".equals(st[0]) ? Ui.L("Chờ giao máy — đã chờ ", "Waiting for a machine — ") + mmss((now - MainActivity.parseTime(x.optString("created_at", ""))) / 1000)
                : st[1];
        String user = a.prof == null ? "" : a.prof.optString("username", "").trim();
        if (user.isEmpty()) user = a.prof == null || a.prof.optString("email", "").isEmpty() ? Api.email : a.prof.optString("email");
        final String msg = Ui.L("[CLOUDBLUE] VPS GPU CẦN HỖ TRỢ", "[CLOUDBLUE] GPU VPS NEEDS HELP")
                + "\n• " + Ui.L("Máy: ", "Machine: ") + (pc == null ? "—" : pc.optString("name")) + (pc != null && !pc.optString("code").isEmpty() ? " (№ " + pc.optString("code") + ")" : "")
                + "\n• " + Ui.L("Việc: ", "Problem: ") + what
                + "\n• Windows: " + x.optString("os_name")
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
        section(a, body);                                                      // VPS GPU của bạn (nếu có) — lên đầu trang
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
        s1.addView(a.stepHead("1", Ui.L("Chọn Windows", "Choose Windows"), Ui.L("Đổi được trong lượt thuê (" + mx + " lần).", "Switchable during the rental (" + mx + " times).")), Ui.fill());
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
            TextView k3 = Ui.text(a, o.optBoolean("fast") ? "⚡ " + Ui.L("Giao ngay", "Instant") : "⏳ " + Ui.L(ready ? "Cài ~20 phút" : "Chờ máy", ready ? "~20 min setup" : "Waiting"), 11.5f, o.optBoolean("fast") ? Ui.OK : Ui.WAIT, true);
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
            osHint.setText(o != null && o.optBoolean("fast") ? Ui.L("⚡ Có máy sẵn bản này — thanh toán xong vào điều khiển được ngay.", "⚡ A machine with this version is ready — use it right after payment.")
                    : ready ? Ui.L("⏳ Máy tự cài bản này cho bạn khoảng 20 phút (hạn thuê được cộng thêm 30 phút).", "⏳ This version is installed for you in ~20 min (30 min added to your time).")
                    : Ui.L("⏳ Shop đang chuẩn bị máy — có máy là tự giao + cài, không cần nhắn shop.", "⏳ Preparing a machine — delivered and installed automatically."));
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
            Ui.toast(a, act ? (res.optBoolean("reinstall") ? Ui.L("🎉 Đã giao máy " + res.optString("name") + " — máy đang tự cài Windows (~20 phút), xem ở đầu trang.", "🎉 Machine assigned — installing Windows (~20 min).")
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
                Ui.toast(a, off ? Ui.L("Đã gia hạn. Máy đã tắt lúc hết hạn — shop sẽ bật lại cho bạn.", "Renewed. The shop will turn the machine back on.") : Ui.L("Đã gia hạn.", "Renewed."));
                mineAt = 0; a.refresh();
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }
}
