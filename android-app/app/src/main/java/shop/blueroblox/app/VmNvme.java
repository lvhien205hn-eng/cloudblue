package shop.blueroblox.app;

import android.app.Dialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** ⚡ VPS NVMe (27/11 · SQL v56 · v59 · v61) — máy ảo Windows riêng trên máy chủ của shop, giống web / app máy tính.
 *  · "Máy của tôi": mục "⚡ VPS NVMe của bạn" (Ẩn / Hiện, nhớ trên máy) — mỗi VPS: ▶ Điều khiển · ⏱ Gia hạn · ⋯ (bật / tắt · khởi động lại ·
 *    ⬆ nâng cấp · 💿 cài lại · ✏️ đổi tên · 🗑 xoá).
 *  · Tab "⚡ VPS NVMe": trang thuê — thẻ nổi bật · ① gói / 🛠 tự chọn cấu hình (+ ổ) · ② Windows · ③ số ngày · mã giảm giá · thanh thanh toán dưới màn hình.
 *  Giá tính ĐÚNG như web / máy chủ (_vm_month · _vm_tier: làm tròn 1.000đ, tối thiểu 1.000đ, dưới 30 ngày cộng short_up %; ổ chỉ tính phần vượt
 *  mức miễn phí — của gói (v61) hoặc mức chung). Bấm thuê → đọc lại giá mới nhất rồi mới hỏi. Máy chủ chưa có hàm vm_* → không hiện gì. */
final class VmNvme {
    private VmNvme() { }

    static final String NAME = "VPS NVMe";
    static JSONObject mine = null, info = null;
    static long mineAt = 0, infoAt = 0, infoErrAt = 0;
    static boolean missing = false, infoLoading = false, mineLoading = false;
    static String infoErr = "";
    private static String pcSig = "";

    // ---------------------------------------------------------------- giá (cùng công thức với web / máy chủ)
    static JSONObject cu(JSONObject src) { JSONObject c = src == null ? null : src.optJSONObject("custom"); return c == null ? new JSONObject() : c; }
    static long r1k(double v) { return Math.round(v / 1000.0) * 1000L; }
    static long month(JSONObject c, double cores, double ramGb, double extraGb) {
        return r1k(cores * c.optDouble("unit_cpu", 0) + ramGb * c.optDouble("unit_ram", 0) + Math.max(0, extraGb) * c.optDouble("unit_disk", 0));
    }
    static long tier(JSONObject c, double month, int days) {
        if (month <= 0 || days < 1) return 0;
        return Math.max(1000, r1k(month * days / 30.0 * (days < 30 ? 1 + c.optDouble("short_up", 0) / 100.0 : 1)));
    }
    static int freeGb(JSONObject src) { JSONObject c = cu(src); return c.has("disk_free_gb") ? c.optInt("disk_free_gb", 20) : 20; }
    static boolean custOn(JSONObject src) { JSONObject c = cu(src); return c.optBoolean("on") && c.optDouble("unit_cpu", 0) > 0 && c.optDouble("unit_ram", 0) > 0; }
    static boolean diskOn(JSONObject src) { return cu(src).optDouble("unit_disk", 0) > 0; }
    /** SQL v61: ổ TỚI mức này không tính thêm tiền cho gói p (≥ ổ của gói; máy chủ chưa chạy v61 = ổ của gói). */
    static int inc(JSONObject p) { int d = p == null ? 0 : p.optInt("disk_gb"); return p != null && p.has("free_gb") ? Math.max(d, p.optInt("free_gb")) : d; }

    static java.util.List<JSONObject> plans() {
        java.util.ArrayList<JSONObject> out = new java.util.ArrayList<>();
        JSONArray a = info == null ? null : info.optJSONArray("plans");
        if (a != null) for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && !p.optString("id").isEmpty() && prices(p).length > 0) out.add(p);
        }
        return out;
    }
    /** [[ngày, giá]] của 1 gói, xếp theo số ngày. */
    static long[][] prices(JSONObject p) {
        java.util.ArrayList<long[]> out = new java.util.ArrayList<>();
        JSONArray a = p == null ? null : p.optJSONArray("prices");
        if (a != null) for (int i = 0; i < a.length(); i++) {
            JSONObject x = a.optJSONObject(i);
            if (x != null && x.optInt("days") > 0 && x.optLong("price", -1) >= 0) out.add(new long[]{x.optInt("days"), x.optLong("price")});
        }
        java.util.Collections.sort(out, (u, w) -> Long.compare(u[0], w[0]));
        return out.toArray(new long[0][]);
    }
    static long[] p30(JSONObject p) { long[][] pr = prices(p); for (long[] x : pr) if (x[0] == 30) return x; return pr.length > 0 ? pr[pr.length - 1] : null; }
    static double lowDay() {
        double best = 0;
        for (JSONObject p : plans()) for (long[] x : prices(p)) if (x[1] > 0) { double d = x[1] / (double) Math.max(1, x[0]); if (best == 0 || d < best) best = d; }
        return best;
    }
    static JSONObject plan(String id) { for (JSONObject p : plans()) if (p.optString("id").equals(id)) return p; return null; }
    static String gb(double mb) { double g = mb / 1024.0; return (Math.abs(g - Math.round(g)) < 0.05 ? String.valueOf(Math.round(g)) : String.format(java.util.Locale.ROOT, "%.1f", g)) + " GB"; }
    static String shortOs(String n) { return n == null ? "" : n.trim().replaceFirst("(?i)^windows\\s+", ""); }
    /** "Windows Server 2012 R2" → ["Windows Server", "2012 R2"] · "Windows 10 LTSC 2021" → ["Windows", "10 LTSC 2021"]. */
    static String[] osKey(String n) {
        String x = shortOs(n);
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("^(Server)\\s+(.+)$", java.util.regex.Pattern.CASE_INSENSITIVE).matcher(x);
        return m.matches() ? new String[]{"Windows " + m.group(1), m.group(2)} : new String[]{"Windows", x};
    }
    static String span(java.util.List<Double> a) {
        if (a.isEmpty()) return "";
        double lo = a.get(0), hi = a.get(0);
        for (double v : a) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
        return lo == hi ? fmt(lo) : fmt(lo) + "–" + fmt(hi);
    }
    private static String fmt(double v) { return Math.abs(v - Math.round(v)) < 1e-9 ? String.valueOf(Math.round(v)) : String.format(java.util.Locale.ROOT, "%.1f", v); }

    /** Bảo trì riêng VPS NVMe (admin bật trên web) → câu cho khách thường; admin / không bảo trì → "". */
    static String maint(MainActivity a) {
        JSONObject d = Api.siteData;
        boolean on = (d != null && d.optBoolean("vm_maint", false)) || (info != null && info.optBoolean("maint")) || (mine != null && mine.optBoolean("maint"));
        if (!on || a.isAdmin()) return "";
        String m = d == null ? "" : d.optString("vm_maint_msg", "").trim();
        if (m.length() > 200) m = m.substring(0, 200);
        return Ui.L("🛠️ VPS NVMe đang bảo trì", "🛠️ VPS NVMe is under maintenance") + (m.isEmpty() ? "" : " — " + m) + ". "
                + Ui.L("VPS đang chạy vẫn dùng + gia hạn bình thường.", "Running VPS keep working and can be renewed.");
    }

    static String err(String m) {
        if (m == null) return "";
        String[][] t = {
                {"NOT_OPEN", "VPS NVMe chưa mở bán.", "VPS NVMe is not on sale yet."},
                {"BAD_PLAN", "Gói / số ngày không hợp lệ — mở lại trang rồi thử lại.", "Invalid plan or duration — reopen and try again."},
                {"BAD_OS", "Bản Windows này không dùng được cho cấu hình này.", "That Windows image can't be used with this configuration."},
                {"NO_CAPACITY", "Máy chủ đang hết chỗ cho cấu hình / bản Windows này — chọn cấu hình khác hoặc nhắn shop. Không trừ tiền.", "No capacity right now — pick another configuration or contact the shop. No charge."},
                {"SLOW_DOWN", "Thao tác hơi nhiều — chờ ít phút rồi thử lại.", "Too many attempts — wait a few minutes."},
                {"EXPIRED", "VPS đã hết hạn — gia hạn trước.", "This VPS has expired — renew first."},
                {"BUSY", "VPS đang được tạo / cài lại / đổi cấu hình — chờ xong rồi thử lại.", "The VPS is busy — try again when it finishes."},
                {"NO_REINSTALL_LEFT", "Đã hết lượt cài lại. Nhắn shop nếu cần thêm.", "No reinstalls left. Contact the shop."},
                {"NOT_ALLOWED", "VPS này không thuộc tài khoản của bạn.", "This VPS is not on your account."},
                {"MAINT", "VPS NVMe đang bảo trì — tạm chưa thuê mới / nâng cấp / cài lại được.", "VPS NVMe is under maintenance — new rentals, upgrades and reinstalls are paused."},
                {"BAD_CONFIG", "Cấu hình chưa hợp lệ (vượt giới hạn, hoặc nâng cấp mà không tăng gì).", "Invalid configuration."},
                {"BAD_DISK", "Dung lượng ổ không hợp lệ.", "Invalid disk size."},
                {"NO_PRICE", "Shop chưa đặt giá cho phần này — nhắn shop.", "No price set for this yet — contact the shop."},
                {"HOST_OFF", "Máy chủ của VPS đang mất kết nối — thử lại sau ít phút.", "The VPS host is offline — try again in a few minutes."},
                {"INSUFFICIENT_BALANCE", "Số dư không đủ — nạp thêm rồi thử lại.", "Not enough balance — top up first."},
                {"BAD_CMD", "Lệnh không hợp lệ — cập nhật app rồi thử lại.", "Invalid command — update the app and try again."}};
        for (String[] x : t) if (m.contains(x[0])) return Ui.L(x[1], x[2]);
        return m;
    }
    static boolean isMissing(String m) { return m != null && (m.contains("PGRST202") || m.contains("Could not find the function")); }

    // ---------------------------------------------------------------- dữ liệu của khách
    static JSONArray items() {
        JSONArray a = mine == null ? null : mine.optJSONArray("items"), out = new JSONArray();
        if (a != null) for (int i = 0; i < a.length(); i++) { JSONObject x = a.optJSONObject(i); if (x != null && x.has("id")) out.put(x); }
        return out;
    }
    /** Máy PC (pc_machines) của các VPS NVMe — để mục VPS GPU không vẽ lặp máy ảo. */
    static java.util.Set<String> pcIds() {
        java.util.HashSet<String> s = new java.util.HashSet<>();
        JSONArray it = items();
        for (int i = 0; i < it.length(); i++) { String p = it.optJSONObject(i).optString("pc", ""); if (!p.isEmpty() && !"null".equals(p)) s.add(p); }
        return s;
    }
    static int live() { return items().length(); }
    static String name(JSONObject v) { String l = v.optString("label", "").trim(); return !l.isEmpty() && !"null".equals(l) ? l : v.optString("name", "VPS"); }
    static String spec(JSONObject v) {
        StringBuilder b = new StringBuilder();
        String pn = v.optString("plan_name", "");
        if (!pn.isEmpty() && !"null".equals(pn)) b.append(pn).append(" · ");
        b.append(v.optInt("cores")).append(" vCPU · ").append(gb(v.optDouble("ram_mb", 0))).append(" RAM · SSD NVMe ").append(v.optInt("disk_gb")).append(" GB");
        String os = shortOs(v.optString("image_name", ""));
        if (!os.isEmpty() && !"null".equals(os)) b.append(" · ").append(os);
        return b.toString();
    }
    /** [mã, chữ, câu] — run · boot · off · inst · cfg · exp · warn (như web / app máy tính). */
    static String[] state(JSONObject v) {
        if (v.optBoolean("expired")) {
            long da = MainActivity.parseTime(v.optString("delete_at", ""));
            return new String[]{"exp", "⛔ " + Ui.L("Hết hạn", "Expired"), da > 0
                    ? Ui.L("Gia hạn trước " + MainActivity.fdate(da) + " để giữ VPS + dữ liệu — quá giờ đó VPS bị xoá.", "Renew before " + MainActivity.fdate(da) + " to keep the VPS and its data.")
                    : Ui.L("Gia hạn để dùng tiếp.", "Renew to keep using it.")};
        }
        if (v.optBoolean("err")) return new String[]{"warn", "⚠️ " + Ui.L("Đang lỗi", "Error"),
                Ui.L("Máy chủ báo lỗi khi tạo / chạy VPS — shop đã được báo. Lâu quá thì nhắn shop kèm tên VPS.", "The host reported an error — the shop has been notified.")};
        if (v.optBoolean("cfg_busy")) return new String[]{"cfg", "⚙️ " + Ui.L("Đang đổi cấu hình", "Applying new specs"),
                Ui.L("Máy chủ đang đặt cấu hình mới — VPS tự khởi động lại khoảng 1–2 phút, dữ liệu giữ nguyên.", "Applying the new specs — the VPS restarts in about 1–2 min.")};
        if (v.optBoolean("busy") || "creating".equals(v.optString("status"))) return new String[]{"inst", "⚙️ " + Ui.L("Đang tạo / cài Windows", "Setting up"),
                Ui.L("Máy chủ đang dựng VPS (thường 3–10 phút). Xong là bấm Điều khiển được.", "The VPS is being prepared (usually 3–10 min).")};
        if ("stopped".equals(v.optString("want")) || "stopped".equals(v.optString("status"))) return new String[]{"off", "⏻ " + Ui.L("Đã tắt", "Stopped"),
                Ui.L("Bấm ⋯ → Bật VPS để chạy lại.", "Tap ⋯ → Start to run it again.")};
        if (!v.optBoolean("online")) return new String[]{"boot", "○ " + Ui.L("Đang khởi động…", "Starting…"), Ui.L("Windows đang lên (1–2 phút).", "Windows is starting (1–2 min).")};
        return new String[]{"run", "● " + Ui.L("Đang chạy", "Running"), ""};
    }

    interface Done { void run(); }

    /** Đọc lại "VPS NVMe của tôi" (vm_my). Máy chủ chưa có hàm → missing (không hiện gì). */
    static void loadMine(MainActivity a, Done then) {
        mineLoading = true;                                                     // nhiều nơi gọi cùng lúc cũng được (mỗi nơi vẽ lại phần của mình)
        Api.bg(() -> Api.rpc("vm_my", new JSONObject()), r -> {
            mineLoading = false;
            if (r instanceof JSONObject) { mine = (JSONObject) r; missing = false; }
            mineAt = System.currentTimeMillis();
            String sig = String.valueOf(pcIds());
            if (!sig.equals(pcSig)) { pcSig = sig; PcVps.refill(a); }          // máy ảo không vẽ lặp ở mục VPS GPU
            if (then != null) then.run();
        }, m -> {
            mineLoading = false; mineAt = System.currentTimeMillis();
            if (isMissing(m)) { missing = true; mine = null; }
            if (then != null) then.run();
        });
    }

    // ================================================================ "Máy của tôi": ⚡ VPS NVMe của bạn
    static SharedPreferences sp(MainActivity a) { return a.getSharedPreferences("ui", android.content.Context.MODE_PRIVATE); }

    static void section(MainActivity a, LinearLayout body) {
        final LinearLayout box = Ui.col(a, 10);
        body.addView(box, Ui.fill());
        if (mine != null) fill(a, box);
        if (mine == null || System.currentTimeMillis() - mineAt > 15000) loadMine(a, () -> { if (box.getParent() != null && !a.isFinishing()) fill(a, box); });
    }

    private static void fill(MainActivity a, LinearLayout box) {
        box.removeAllViews();
        JSONArray it = items();
        if (missing || it.length() == 0) return;
        final boolean mini = sp(a).getBoolean("vm_min", false);
        int run = 0;
        for (int i = 0; i < it.length(); i++) if ("run".equals(state(it.optJSONObject(i))[0])) run++;
        LinearLayout head = Ui.row(a, 8);
        head.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout ht = Ui.col(a, 0);
        ht.addView(Ui.h2(a, "⚡ " + Ui.L("VPS NVMe của bạn", "Your VPS NVMe")));
        ht.addView(Ui.text(a, it.length() + " VPS · " + run + Ui.L(" đang chạy", " running"), 12, Ui.SKY, false));
        head.addView(ht, Ui.weight(1));
        if (Api.SHOP) {
            TextView more = Ui.pill(a, "+ " + Ui.L("Thuê thêm", "Rent more"), Ui.SKY);
            more.setOnClickListener(v -> a.show(4));
            head.addView(more, Ui.wrap());
        }
        TextView tg = Ui.pill(a, mini ? Ui.L("Hiện ▾", "Show ▾") : Ui.L("Ẩn ▴", "Hide ▴"), Ui.MUTED);
        tg.setContentDescription(mini ? Ui.L("Hiện các VPS NVMe", "Show VPS NVMe") : Ui.L("Ẩn các VPS NVMe", "Hide VPS NVMe"));
        tg.setOnClickListener(v -> { sp(a).edit().putBoolean("vm_min", !mini).apply(); fill(a, box); });
        head.addView(tg, Ui.wrap());
        box.addView(head, Ui.fill());
        if (mini) return;
        String mt = maint(a);
        if (!mt.isEmpty()) box.addView(note(a, mt, Ui.WAIT), Ui.fill());
        boolean busy = false;
        for (int i = 0; i < it.length(); i++) {
            JSONObject v = it.optJSONObject(i);
            box.addView(card(a, v, box), Ui.fill());
            String c = state(v)[0];
            if ("inst".equals(c) || "cfg".equals(c) || "boot".equals(c)) busy = true;
        }
        if (busy) box.postDelayed(() -> { if (box.getParent() != null && !a.isFinishing()) loadMine(a, () -> { if (box.getParent() != null) fill(a, box); }); }, 15000);
    }

    static TextView note(MainActivity a, String m, int color) {
        TextView t = Ui.text(a, m, 13.5f, Ui.FG, true);
        t.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(14), Ui.dp(11));
        t.setBackground(Ui.round(Color.argb(34, Color.red(color), Color.green(color), Color.blue(color)), 14, Color.argb(150, Color.red(color), Color.green(color), Color.blue(color))));
        return t;
    }

    private static View card(MainActivity a, JSONObject v, LinearLayout box) {
        String[] st = state(v);
        String code = st[0];
        boolean run = "run".equals(code);
        LinearLayout c = Ui.card(a);
        if (run) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(130, 60, 224, 176)));
        else if (!"off".equals(code)) c.setBackground(Ui.round(Ui.PANEL, 18, Color.argb(150, 255, 200, 97)));
        LinearLayout top = Ui.row(a, 8);
        top.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout nm = Ui.col(a, 0);
        TextView t1 = Ui.text(a, name(v), 16, Ui.FG, true);
        nm.addView(t1);
        String lb = v.optString("label", "").trim();
        if (!lb.isEmpty() && !"null".equals(lb)) nm.addView(Ui.text(a, v.optString("name"), 11.5f, Ui.MUTED, false));
        top.addView(nm, Ui.weight(1));
        top.addView(Ui.pill(a, st[1], run ? Ui.OK : "exp".equals(code) ? Ui.BAD : Ui.WAIT), Ui.wrap());
        c.addView(top, Ui.fill());
        c.addView(Ui.muted(a, spec(v)));
        if (!st[2].isEmpty()) c.addView(Ui.text(a, st[2], 13, "exp".equals(code) || "warn".equals(code) ? Ui.BAD : Ui.WAIT, false));
        long until = MainActivity.parseTime(v.optString("until", ""));
        if (until > System.currentTimeMillis()) c.addView(Ui.text(a, MainActivity.left(until) + "  ·  " + Ui.L("hết hạn ", "expires ") + MainActivity.fdate(until), 13, Ui.FG, false));
        LinearLayout acts = Ui.row(a, 8);
        Button open = Ui.button(a, "▶ " + Ui.L("Điều khiển", "Control"), Ui.PRIMARY);
        final String pc = v.optString("pc", "");
        boolean ctl = !pc.isEmpty() && !"null".equals(pc) && ("run".equals(code) || "boot".equals(code) || "cfg".equals(code));
        open.setEnabled(ctl);
        open.setAlpha(ctl ? 1f : 0.5f);
        open.setOnClickListener(x -> PcVps.control(a, pc, name(v)));
        acts.addView(open, Ui.weight(1));
        if (Api.SHOP && v.optJSONArray("prices") != null && v.optJSONArray("prices").length() > 0 && !"inst".equals(code)) {
            Button rn = Ui.button(a, "⏱ " + Ui.L("Gia hạn", "Renew"), Ui.GHOST);
            rn.setOnClickListener(x -> renew(a, v));
            acts.addView(rn, Ui.wrap());
        }
        Button mo = Ui.button(a, "⋯", Ui.GHOST);
        mo.setContentDescription(Ui.L("Khác: bật / tắt, khởi động lại, nâng cấp, cài lại, đổi tên, xoá", "More: start / stop, reset, upgrade, reinstall, rename, delete"));
        mo.setOnClickListener(x -> more(a, v, st));
        acts.addView(mo, Ui.wrap());
        c.addView(acts, Ui.fill());
        return c;
    }

    private static void reload(MainActivity a) { mineAt = 0; loadMine(a, a::vmMineChanged); a.refresh(); }

    /** "⋯" của 1 VPS NVMe: bật / tắt · khởi động lại · ⬆ nâng cấp · 💿 cài lại · ✏️ đổi tên · 🗑 xoá. */
    private static void more(MainActivity a, JSONObject v, String[] st) {
        String code = st[0];
        boolean on = "run".equals(code) || "boot".equals(code) || "cfg".equals(code);
        String mt = maint(a);
        JSONObject c = cu(mine);
        boolean up = mine != null && mine.optBoolean("upgrade") && (c.optDouble("unit_cpu", 0) > 0 || c.optDouble("unit_ram", 0) > 0 || c.optDouble("unit_disk", 0) > 0 || v.optInt("free_gb") > v.optInt("disk_gb"));
        LinearLayout box = Ui.col(a, 10);
        final Dialog[] d = new Dialog[1];
        java.util.ArrayList<Object[]> rows = new java.util.ArrayList<>();
        if ("off".equals(code)) rows.add(new Object[]{"⏻ " + Ui.L("Bật VPS", "Start"), true, (Runnable) () -> power(a, v, "start")});
        else rows.add(new Object[]{"⏻ " + Ui.L("Tắt VPS", "Stop"), on, (Runnable) () -> power(a, v, "stop")});
        rows.add(new Object[]{"🔁 " + Ui.L("Khởi động lại (khi Windows treo)", "Reset (when Windows hangs)"), on, (Runnable) () -> power(a, v, "reset")});
        if (up) rows.add(new Object[]{"⬆ " + Ui.L("Nâng cấp vCPU / RAM / ổ", "Upgrade vCPU / RAM / disk"),
                !("inst".equals(code) || "exp".equals(code) || "cfg".equals(code) || "warn".equals(code)) && mt.isEmpty(), (Runnable) () -> upgrade(a, v)});
        rows.add(new Object[]{"💿 " + Ui.L("Cài lại / đổi Windows", "Reinstall / switch Windows") + " (" + v.optInt("left") + ")",
                !("inst".equals(code) || "exp".equals(code)) && v.optInt("left") > 0 && mt.isEmpty(), (Runnable) () -> reinstall(a, v)});
        rows.add(new Object[]{"✏️ " + Ui.L("Đổi tên VPS", "Rename VPS"), true, (Runnable) () -> rename(a, v)});
        for (Object[] r : rows) {
            Button b = Ui.button(a, (String) r[0], Ui.GHOST);
            boolean en = (Boolean) r[1];
            b.setEnabled(en);
            b.setAlpha(en ? 1f : 0.5f);
            final Runnable go = (Runnable) r[2];
            b.setOnClickListener(x -> { d[0].dismiss(); go.run(); });
            box.addView(b, Ui.fill());
        }
        Button del = Ui.button(a, "🗑 " + Ui.L("Xoá VPS (xoá hẳn, không hoàn tiền)", "Delete VPS (permanent, no refund)"), Ui.DANGER);
        del.setOnClickListener(x -> { d[0].dismiss(); remove(a, v); });
        box.addView(del, Ui.fill());
        if (!mt.isEmpty()) box.addView(Ui.muted(a, mt));
        d[0] = Ui.sheet(a, name(v), box);
        d[0].show();
    }

    private static void power(MainActivity a, JSONObject v, String act) {
        Runnable go = () -> Api.bg(() -> Api.rpc("vm_my_power", new JSONObject().put("p_id", v.optLong("id")).put("p_act", act)), r -> {
            Ui.toast(a, "start".equals(act) ? Ui.L("Đang bật VPS — khoảng 1–2 phút là vào được.", "Starting — ready in about 1–2 min.")
                    : "stop".equals(act) ? Ui.L("Đang tắt VPS. Bấm ⋯ → Bật VPS khi cần dùng lại.", "Stopping. Tap ⋯ → Start when you need it again.")
                    : Ui.L("Đang khởi động lại VPS — khoảng 1–2 phút.", "Resetting — about 1–2 min."));
            reload(a);
        }, m -> Ui.toast(a, err(m)));
        if ("start".equals(act)) { go.run(); return; }
        Ui.confirm(a, ("stop".equals(act) ? "⏻ " + Ui.L("Tắt ", "Stop ") : "🔁 " + Ui.L("Khởi động lại ", "Reset ")) + name(v) + "?",
                "stop".equals(act) ? Ui.L("Windows tắt hẳn (thời gian thuê vẫn tính). Bật lại bất cứ lúc nào ở ⋯ → Bật VPS.", "Windows shuts down (rental time keeps counting). Start it again anytime.")
                        : Ui.L("Như rút điện cắm lại: chương trình đang mở bị đóng, dữ liệu đã lưu giữ nguyên. Dùng khi Windows treo.", "Like a power cycle: open programs close, saved data is kept."),
                "stop".equals(act) ? Ui.L("Tắt VPS", "Stop") : Ui.L("Khởi động lại", "Reset"), go::run);
    }

    private static void rename(MainActivity a, JSONObject v) {
        LinearLayout box = Ui.col(a, 12);
        final EditText in = Ui.input(a, Ui.L("Tên mới (VD: Treo game)", "New name (e.g. Farm 1)"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        in.setFilters(new InputFilter[]{new InputFilter.LengthFilter(32)});
        String lb = v.optString("label", "").trim();
        if (!lb.isEmpty() && !"null".equals(lb)) in.setText(lb);
        box.addView(in, Ui.fill());
        box.addView(Ui.muted(a, Ui.L("Chỉ bạn thấy tên này. Để trống = về tên gốc ", "Only you see this name. Empty = back to ") + v.optString("name")));
        Button ok = Ui.button(a, "💾 " + Ui.L("Lưu tên", "Save"), Ui.PRIMARY);
        box.addView(ok, Ui.fill());
        final Dialog d = Ui.sheet(a, "✏️ " + Ui.L("Đổi tên ", "Rename ") + name(v), box);
        ok.setOnClickListener(x -> {
            ok.setEnabled(false);
            String n = in.getText().toString().trim();
            Api.bg(() -> Api.rpc("vm_my_label", new JSONObject().put("p_id", v.optLong("id")).put("p_label", n)), r -> {
                d.dismiss(); Ui.toast(a, Ui.L("Đã đổi tên.", "Renamed.")); reload(a);
            }, m -> { ok.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    private static void renew(MainActivity a, JSONObject v) {
        if (!Api.SHOP) return;
        JSONArray pa = v.optJSONArray("prices");
        if (pa == null || pa.length() == 0) { Ui.toast(a, Ui.L("VPS này chưa có bảng giá gia hạn — nhắn shop.", "No renewal price for this VPS — contact the shop.")); return; }
        final java.util.ArrayList<long[]> pl = new java.util.ArrayList<>();
        for (int i = 0; i < pa.length(); i++) { JSONObject x = pa.optJSONObject(i); if (x != null && x.optInt("days") > 0) pl.add(new long[]{x.optInt("days"), x.optLong("price")}); }
        java.util.Collections.sort(pl, (u, w) -> Long.compare(u[0], w[0]));
        if (pl.isEmpty()) { Ui.toast(a, Ui.L("VPS này chưa có bảng giá gia hạn — nhắn shop.", "No renewal price for this VPS — contact the shop.")); return; }
        final int[] pick = {(int) pl.get(0)[0]};
        for (long[] x : pl) if (x[0] == 30) pick[0] = 30;
        LinearLayout box = Ui.col(a, 12);
        long until = MainActivity.parseTime(v.optString("until", ""));
        box.addView(Ui.muted(a, spec(v) + (until > 0 ? "\n" + Ui.L("Hạn hiện tại: ", "Current expiry: ") + MainActivity.fdate(until) : "")));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        final java.util.ArrayList<TextView> chips = new java.util.ArrayList<>();
        final TextView sum = Ui.text(a, "", 14, Ui.FG, true);
        final EditText promo = Ui.input(a, "🏷️ " + Ui.L("Mã giảm giá (nếu có)", "Promo code (optional)"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        final Runnable paint = () -> {
            for (TextView t : chips) Ui.setChip(t, (Integer) t.getTag() == pick[0]);
            long p = 0; for (long[] x : pl) if (x[0] == pick[0]) p = x[1];
            double t0 = a.ctv(p), bal = a.prof.optDouble("balance", 0);
            sum.setText(Ui.L("Thêm ", "Add ") + pick[0] + Ui.L(" ngày · ", " days · ") + Ui.vnd(t0) + Ui.L("  ·  số dư ", "  ·  balance ") + Ui.vnd(bal));
        };
        for (long[] x : pl) {
            TextView t = Ui.chip(a, "+" + x[0] + Ui.L(" ngày", " days") + "\n" + Ui.vnd(a.ctv(x[1])), x[0] == pick[0]);
            t.setTag((int) x[0]);
            t.setOnClickListener(q -> { pick[0] = (Integer) q.getTag(); paint.run(); });
            chips.add(t);
            w.addView(t);
        }
        box.addView(w, Ui.fill());
        box.addView(promo, Ui.fill());
        box.addView(sum, Ui.fill());
        Button go = Ui.button(a, "⏱ " + Ui.L("Gia hạn", "Renew"), Ui.PRIMARY);
        box.addView(go, Ui.fill());
        paint.run();
        final Dialog d = Ui.sheet(a, "⏱ " + Ui.L("Gia hạn ", "Renew ") + name(v), box);
        go.setOnClickListener(x -> {
            long p = 0; for (long[] y : pl) if (y[0] == pick[0]) p = y[1];
            double t0 = a.ctv(p), bal = a.prof.optDouble("balance", 0);
            final String code = promo.getText().toString().trim().replaceAll("[^A-Za-z0-9_-]", "");
            if (code.isEmpty() && bal < t0) { d.dismiss(); a.openTopup(t0 - bal); return; }
            go.setEnabled(false);
            JSONObject args = new JSONObject();
            try { args.put("p_id", v.optLong("id")).put("p_days", pick[0]); if (!code.isEmpty()) args.put("p_promo", code); } catch (Exception ignored) { }
            Api.bg(() -> Api.rpc("vm_my_renew", args), r -> {
                d.dismiss();
                JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                long nu = MainActivity.parseTime(o.optString("until", ""));
                Ui.toast(a, Ui.L("Đã gia hạn", "Renewed") + (nu > 0 ? Ui.L(" — hạn mới ", " — new expiry ") + MainActivity.fdate(nu) : "") + ".");
                reload(a);
            }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    // ---- ô số − / + (vCPU · RAM · ổ)
    interface IntCb { void set(int v); }
    static final class Step {
        int v; final int lo, hi, step; final TextView val; final Button minus, plus; final IntCb cb; final LinearLayout view;
        Step(MainActivity a, String title, String sub, int value, int lo, int hi, int step, boolean enabled, IntCb cb) {
            this.lo = lo; this.hi = Math.max(lo, hi); this.step = step; this.cb = cb;
            this.v = Math.max(this.lo, Math.min(this.hi, value));
            view = Ui.row(a, 8);
            view.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout tx = Ui.col(a, 0);
            tx.addView(Ui.text(a, title, 14, Ui.FG, true));
            if (sub != null && !sub.isEmpty()) tx.addView(Ui.text(a, sub, 11.5f, Ui.MUTED, false));
            view.addView(tx, Ui.weight(1));
            minus = Ui.button(a, "−", Ui.GHOST);
            plus = Ui.button(a, "+", Ui.GHOST);
            val = Ui.text(a, String.valueOf(this.v), 17, Ui.FG, true);
            val.setGravity(Gravity.CENTER);
            val.setMinWidth(Ui.dp(52));
            view.addView(minus, new LinearLayout.LayoutParams(Ui.dp(48), Ui.dp(46)));
            view.addView(val, Ui.wrap());
            view.addView(plus, new LinearLayout.LayoutParams(Ui.dp(48), Ui.dp(46)));
            minus.setPadding(0, 0, 0, 0);
            plus.setPadding(0, 0, 0, 0);
            minus.setOnClickListener(x -> set(this.v - this.step));
            plus.setOnClickListener(x -> set(this.v + this.step));
            if (!enabled) { minus.setEnabled(false); plus.setEnabled(false); minus.setAlpha(.4f); plus.setAlpha(.4f); }
            else paint();
        }
        void paint() {
            minus.setEnabled(v > lo); minus.setAlpha(v > lo ? 1f : .4f);
            plus.setEnabled(v < hi); plus.setAlpha(v < hi ? 1f : .4f);
            val.setText(String.valueOf(v));
        }
        void set(int x) {
            x = Math.max(lo, Math.min(hi, x));
            if (x == v) { paint(); return; }
            v = x; paint();
            if (cb != null) cb.set(v);
        }
    }

    /** ⬆ Nâng cấp sau khi thuê (vm_my_upgrade): chỉ tăng; giá hỏi máy chủ (p_dry) — đúng số sẽ trừ. Ổ trong mức miễn phí (v61) → 0đ. */
    private static void upgrade(MainActivity a, JSONObject v) {
        JSONObject c = cu(mine);
        final int cc = v.optInt("cores"), cr = (int) Math.ceil(v.optDouble("ram_mb", 0) / 1024.0), cd = v.optInt("disk_gb"), fr = v.optInt("free_gb");
        boolean dOn = c.optDouble("unit_disk", 0) > 0;
        int hiC = Math.max(cc, c.optInt("max_cores", 16)), hiR = Math.max(cr, c.optInt("max_ram_gb", 32)),
                hiD = dOn ? Math.max(Math.max(cd, c.optInt("max_disk_gb", 200)), fr) : Math.max(cd, fr);
        String mo = Ui.L("tháng", "month");
        LinearLayout box = Ui.col(a, 10);
        box.addView(Ui.muted(a, Ui.L("Hiện tại: ", "Now: ") + cc + " vCPU · " + gb(v.optDouble("ram_mb", 0)) + " RAM · SSD NVMe " + cd + " GB"));
        final TextView sum = Ui.text(a, "", 14, Ui.FG, true);
        final Button go = Ui.button(a, "⬆ " + Ui.L("Nâng cấp", "Upgrade"), Ui.PRIMARY);
        final long[] price = {-1};
        final int[] seq = {0};
        final Step[] s = new Step[3];
        final Runnable quote = () -> {
            final int q = ++seq[0];
            price[0] = -1; go.setEnabled(false); go.setAlpha(.5f);
            if (s[0].v == cc && s[1].v == cr && s[2].v == cd) { sum.setText(Ui.L("Bấm + để chọn mức cao hơn hiện tại.", "Tap + to pick more than you have now.")); return; }
            sum.setText(Ui.L("Đang hỏi giá…", "Getting the price…"));
            final int w0 = s[0].v, w1 = s[1].v, w2 = s[2].v;
            box.postDelayed(() -> {
                if (q != seq[0]) return;
                Api.bg(() -> Api.rpc("vm_my_upgrade", new JSONObject().put("p_id", v.optLong("id")).put("p_cores", w0).put("p_ram_gb", w1).put("p_disk_gb", w2).put("p_dry", true)), r -> {
                    if (q != seq[0]) return;
                    JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                    price[0] = o.optLong("price");
                    sum.setText(Ui.L("Phải trả: ", "To pay: ") + (price[0] > 0 ? Ui.vnd(price[0]) : Ui.L("0đ — miễn phí", "free"))
                            + Ui.L(" (còn " + o.optInt("days_left") + " ngày)", " (" + o.optInt("days_left") + " days left)")
                            + "\n" + (o.optBoolean("restart") ? Ui.L("VPS tự khởi động lại ~1–2 phút", "The VPS restarts (~1–2 min)") : Ui.L("Không cần khởi động lại", "No restart")));
                    go.setEnabled(true); go.setAlpha(1f);
                }, m -> { if (q == seq[0]) sum.setText(err(m)); });
            }, 350);
        };
        s[0] = new Step(a, "⚙️ vCPU", c.optDouble("unit_cpu", 0) > 0 ? Ui.vnd(c.optDouble("unit_cpu")) + " / vCPU / " + mo : Ui.L("shop chưa bán thêm vCPU", "not for sale"),
                cc, cc, hiC, 1, c.optDouble("unit_cpu", 0) > 0, x -> quote.run());
        s[1] = new Step(a, "🧠 RAM (GB)", c.optDouble("unit_ram", 0) > 0 ? Ui.vnd(c.optDouble("unit_ram")) + " / GB / " + mo : Ui.L("shop chưa bán thêm RAM", "not for sale"),
                cr, cr, hiR, 1, c.optDouble("unit_ram", 0) > 0, x -> quote.run());
        String sd = (fr > cd ? Ui.L("miễn phí tới " + fr + " GB", "free up to " + fr + " GB") : "")
                + (dOn ? (fr > cd ? " · " : "") + Ui.vnd(c.optDouble("unit_disk")) + " / GB / " + mo : fr > cd ? "" : Ui.L("shop chưa bán thêm ổ", "not for sale"));
        s[2] = new Step(a, "💾 SSD NVMe (GB)", sd, cd, cd, hiD, 10, dOn || fr > cd, x -> quote.run());
        LinearLayout cfg = Ui.card(a);
        for (Step x : s) cfg.addView(x.view, Ui.fill());
        box.addView(cfg, Ui.fill());
        box.addView(Ui.text(a, Ui.L("Chỉ tăng được. Tiền = phần chênh giá tháng × số ngày còn lại / 30. Tăng vCPU / RAM: VPS tự khởi động lại ~1–2 phút. Chỉ thêm ổ: không cần khởi động lại, ổ C tự nới. Dữ liệu giữ nguyên.",
                "Increase only. Price = monthly difference × days left / 30. More vCPU / RAM restarts the VPS (~1–2 min). Disk only: no restart. Data is kept."), 12, Ui.MUTED, false));
        final EditText promo = Ui.input(a, "🏷️ " + Ui.L("Mã giảm giá (nếu có)", "Promo code (optional)"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        box.addView(promo, Ui.fill());
        box.addView(sum, Ui.fill());
        box.addView(go, Ui.fill());
        quote.run();
        final Dialog d = Ui.sheet(a, "⬆ " + Ui.L("Nâng cấp ", "Upgrade ") + name(v), box);
        go.setOnClickListener(x -> {
            if (price[0] < 0) return;
            final String code = promo.getText().toString().trim().replaceAll("[^A-Za-z0-9_-]", "");
            double bal = a.prof.optDouble("balance", 0);
            if (code.isEmpty() && price[0] > bal) { d.dismiss(); a.openTopup(price[0] - bal); return; }
            final int w0 = s[0].v, w1 = s[1].v, w2 = s[2].v;
            Ui.confirm(a, "⬆ " + Ui.L("Nâng cấp ", "Upgrade ") + name(v), w0 + " vCPU · " + w1 + " GB RAM · SSD NVMe " + w2 + " GB\n"
                            + (price[0] > 0 ? Ui.L("Trừ ", "Charge ") + Ui.vnd(price[0]) + Ui.L(" từ số dư.", " from your balance.") : Ui.L("Miễn phí (0đ).", "Free (0đ).")) + (code.isEmpty() ? "" : "\n🏷️ " + code),
                    Ui.L("Nâng cấp", "Upgrade"), () -> {
                        go.setEnabled(false);
                        JSONObject args = new JSONObject();
                        try { args.put("p_id", v.optLong("id")).put("p_cores", w0).put("p_ram_gb", w1).put("p_disk_gb", w2); if (!code.isEmpty()) args.put("p_promo", code); } catch (Exception ignored) { }
                        Api.bg(() -> Api.rpc("vm_my_upgrade", args), r -> {
                            d.dismiss();
                            boolean rs = r instanceof JSONObject && ((JSONObject) r).optBoolean("restart");
                            Ui.toast(a, rs ? Ui.L("Đã nâng cấp — VPS tự khởi động lại ~1–2 phút để nhận cấu hình mới.", "Upgraded — the VPS restarts in ~1–2 min.")
                                    : Ui.L("Đã nâng cấp — ổ mới tự nới trong ~1 phút.", "Upgraded — the new disk space appears in ~1 min."));
                            reload(a);
                        }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
                    });
        });
        d.show();
    }

    /** 💿 Cài lại / đổi Windows: XOÁ SẠCH ổ rồi dựng lại (vài phút), giới hạn số lần mỗi lượt thuê; tick "Tôi hiểu" mới bấm được. */
    private static void reinstall(MainActivity a, JSONObject v) {
        JSONArray im = mine == null ? null : mine.optJSONArray("images");
        final java.util.ArrayList<JSONObject> os = new java.util.ArrayList<>();
        if (im != null) for (int i = 0; i < im.length(); i++) {
            JSONObject o = im.optJSONObject(i);
            if (o != null && !o.optString("id").isEmpty() && o.optDouble("min_ram", 0) <= v.optDouble("ram_mb", 0) && o.optDouble("min_disk", 0) <= v.optDouble("disk_gb", 0)) os.add(o);
        }
        if (os.isEmpty()) { Ui.toast(a, Ui.L("Chưa có bản Windows nào dùng được — nhắn shop.", "No Windows image available — contact the shop.")); return; }
        final String[] pick = {v.optString("image", os.get(0).optString("id"))};
        LinearLayout box = Ui.col(a, 12);
        box.addView(Ui.muted(a, Ui.L("Còn " + v.optInt("left") + " lần cài lại trong lượt thuê này.", v.optInt("left") + " reinstall(s) left for this rental.")));
        Ui.Wrap w = new Ui.Wrap(a, 8);
        final java.util.ArrayList<TextView> chips = new java.util.ArrayList<>();
        for (JSONObject o : os) {
            String id = o.optString("id");
            TextView t = Ui.chip(a, shortOs(o.optString("name", id)) + (id.equals(v.optString("image")) ? Ui.L(" (đang dùng)", " (current)") : ""), id.equals(pick[0]));
            t.setTag(id);
            t.setOnClickListener(q -> { pick[0] = String.valueOf(q.getTag()); for (TextView z : chips) Ui.setChip(z, pick[0].equals(z.getTag())); });
            chips.add(t);
            w.addView(t);
        }
        box.addView(w, Ui.fill());
        box.addView(note(a, Ui.L("⚠️ Cài lại = XOÁ SẠCH ổ của VPS rồi dựng Windows mới (vài phút). Dữ liệu trong VPS mất hết, hạn giữ nguyên.",
                "⚠️ Reinstall ERASES the VPS disk and sets up a fresh Windows (a few minutes). All data inside is lost; the expiry stays the same."), Ui.BAD), Ui.fill());
        final CheckBox ok = new CheckBox(a);
        ok.setText(Ui.L("Tôi hiểu: mất hết dữ liệu trong VPS", "I understand: all data in the VPS is erased"));
        ok.setTextColor(Ui.FG);
        ok.setTextSize(14);
        box.addView(ok, Ui.fill());
        final Button go = Ui.button(a, "💿 " + Ui.L("Cài lại", "Reinstall"), Ui.DANGER);
        go.setEnabled(false); go.setAlpha(.5f);
        ok.setOnCheckedChangeListener((b, on) -> { go.setEnabled(on); go.setAlpha(on ? 1f : .5f); });
        box.addView(go, Ui.fill());
        final Dialog d = Ui.sheet(a, "💿 " + Ui.L("Cài lại / đổi Windows · ", "Reinstall Windows · ") + name(v), box);
        go.setOnClickListener(x -> {
            if (!ok.isChecked()) return;
            go.setEnabled(false);
            Api.bg(() -> Api.rpc("vm_my_reinstall", new JSONObject().put("p_id", v.optLong("id")).put("p_image", pick[0])), r -> {
                d.dismiss(); Ui.toast(a, Ui.L("Đang cài lại Windows — vài phút là xong.", "Reinstalling Windows — done in a few minutes.")); reload(a);
            }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    /** 🗑 Xoá VPS: xoá hẳn khỏi máy chủ, không hoàn tiền phần còn lại — tick "Tôi hiểu" mới bấm được. */
    private static void remove(MainActivity a, JSONObject v) {
        LinearLayout box = Ui.col(a, 12);
        box.addView(note(a, Ui.L("⚠️ VPS bị xoá hẳn khỏi máy chủ, dữ liệu mất hết, KHÔNG hoàn tiền phần hạn còn lại. Không hoàn tác được.",
                "⚠️ The VPS is deleted from the host, all data is lost and the remaining time is NOT refunded. This cannot be undone."), Ui.BAD), Ui.fill());
        final CheckBox ok = new CheckBox(a);
        ok.setText(Ui.L("Tôi hiểu: xoá hẳn, không hoàn tiền", "I understand: permanent, no refund"));
        ok.setTextColor(Ui.FG);
        ok.setTextSize(14);
        box.addView(ok, Ui.fill());
        final Button go = Ui.button(a, "🗑 " + Ui.L("Xoá VPS", "Delete VPS"), Ui.DANGER);
        go.setEnabled(false); go.setAlpha(.5f);
        ok.setOnCheckedChangeListener((b, on) -> { go.setEnabled(on); go.setAlpha(on ? 1f : .5f); });
        Button keep = Ui.button(a, Ui.L("Giữ VPS", "Keep it"), Ui.GHOST);
        box.addView(go, Ui.fill());
        box.addView(keep, Ui.fill());
        final Dialog d = Ui.sheet(a, "🗑 " + Ui.L("Xoá ", "Delete ") + name(v) + "?", box);
        keep.setOnClickListener(x -> d.dismiss());
        go.setOnClickListener(x -> {
            if (!ok.isChecked()) return;
            go.setEnabled(false);
            Api.bg(() -> Api.rpc("vm_my_cancel", new JSONObject().put("p_id", v.optLong("id"))), r -> {
                d.dismiss(); Ui.toast(a, Ui.L("Đã xoá VPS.", "VPS deleted.")); reload(a);
            }, m -> { go.setEnabled(true); Ui.toast(a, err(m)); });
        });
        d.show();
    }

    // ================================================================ TAB "⚡ VPS NVMe": trang thuê
    static String bPlan = "", bImage = "", bPromo = "";
    static boolean bCust = false;
    static int bDays = 0, bDisk = 0, bCc = 2, bCr = 4, bCd = 20;

    static void loadInfo(MainActivity a) {
        if (infoLoading) return;
        infoLoading = true;
        Api.bg(() -> {
            try { Api.site(); } catch (Exception ignored) { }                     // bảo trì VPS NVMe (settings.data.vm_maint) luôn mới khi mở trang
            return Api.rpc("vm_shop_info", new JSONObject());
        }, r -> {
            infoLoading = false; infoErr = "";
            if (r instanceof JSONObject) { info = (JSONObject) r; infoAt = System.currentTimeMillis(); missing = false; }
            a.vmChanged();
        }, m -> {
            infoLoading = false; infoErrAt = System.currentTimeMillis();
            if (isMissing(m)) { missing = true; infoErr = Ui.L("Máy chủ chưa mở VPS NVMe.", "VPS NVMe isn't available on the server yet."); }
            else infoErr = m == null ? "?" : m;
            a.vmChanged();
        });
    }

    static int[] lim() {
        JSONObject c = cu(info), r = c.optJSONObject("room");
        int[] mx = {Math.max(1, c.optInt("max_cores", 16)), Math.max(1, c.optInt("max_ram_gb", 32)), Math.max(20, c.optInt("max_disk_gb", 200))};
        if (r != null) {
            if (r.optInt("cores") > 0) mx[0] = Math.max(1, Math.min(mx[0], r.optInt("cores")));
            if (r.optInt("ram_gb") > 0) mx[1] = Math.max(1, Math.min(mx[1], r.optInt("ram_gb")));
            if (r.optInt("disk_gb") > 0) mx[2] = Math.max(20, Math.min(mx[2], r.optInt("disk_gb")));
        }
        return mx;
    }

    /** Giá 1 kỳ của cấu hình đang chọn (null = không bán). */
    static Long priceFor(int days) {
        JSONObject c = cu(info);
        if (bCust) {
            boolean ok = false;
            JSONArray ds = c.optJSONArray("days");
            if (ds != null) for (int i = 0; i < ds.length(); i++) if (ds.optInt(i) == days) ok = true;
            if (!ok) return null;
            int ex = Math.max(0, bCd - freeGb(info));
            if (ex > 0 && !diskOn(info)) return null;
            long t = tier(c, month(c, bCc, bCr, ex), days);
            return t > 0 ? t : null;
        }
        JSONObject p = plan(bPlan);
        if (p == null) return null;
        Long x = null;
        for (long[] y : prices(p)) if (y[0] == days) x = y[1];
        if (x == null) return null;
        int ex = bDisk - inc(p);                                     // v61: chỉ phần VƯỢT mức miễn phí của gói mới tính tiền
        if (ex <= 0) return x;
        if (!diskOn(info)) return null;
        return x + tier(c, ex * c.optDouble("unit_disk", 0), days);
    }

    static java.util.List<Integer> daysList() {
        java.util.TreeSet<Integer> s = new java.util.TreeSet<>();
        if (bCust) { JSONArray ds = cu(info).optJSONArray("days"); if (ds != null) for (int i = 0; i < ds.length(); i++) if (ds.optInt(i) > 0) s.add(ds.optInt(i)); }
        else for (long[] y : prices(plan(bPlan))) s.add((int) y[0]);
        java.util.ArrayList<Integer> out = new java.util.ArrayList<>();
        for (int d : s) if (priceFor(d) != null) out.add(d);
        return out;
    }

    /** Ổ / RAM của cấu hình đang chọn → các bản Windows cài được. */
    static int ramMb() { if (bCust) return bCr * 1024; JSONObject p = plan(bPlan); return p == null ? 0 : p.optInt("ram_mb"); }
    static int diskGb() { if (bCust) return bCd; JSONObject p = plan(bPlan); return p == null ? 0 : Math.max(p.optInt("disk_gb"), bDisk); }

    static void pick(MainActivity a, String id) {
        if ("custom".equals(id)) { if (!custOn(info)) return; bCust = true; }
        else {
            JSONObject p = plan(id);
            if (p == null || !p.optBoolean("free")) return;
            if (!id.equals(bPlan)) bDisk = inc(p);                    // v61: mặc định lấy hết phần ổ miễn phí của gói
            bCust = false; bPlan = id; bDisk = Math.max(p.optInt("disk_gb"), bDisk);
        }
        a.vmChanged();
    }

    /** Dựng trang thuê vào body. Trả thanh thanh toán (gắn dưới màn hình) hoặc null (đang tải / chưa mở bán). */
    static View tab(MainActivity a, LinearLayout body) {
        LinearLayout head = Ui.row(a, 10);
        head.addView(Ui.h1(a, "⚡ " + NAME), Ui.weight(1));
        body.addView(head, Ui.fill());
        body.addView(Ui.muted(a, Ui.L("Máy ảo Windows riêng trên SSD NVMe, chạy 24/7. Chọn cấu hình + Windows + thời gian — thanh toán xong máy chủ tự tạo VPS (thường 3–10 phút).",
                "Your own Windows VM on NVMe SSD, on 24/7. Pick specs, Windows and time — the VPS is created automatically after payment (3–10 min).")), Ui.fill());
        String mt = maint(a);
        if (!mt.isEmpty()) body.addView(note(a, mt, Ui.WAIT), Ui.fill());
        int n = live();
        if (n > 0) {
            LinearLayout r = Ui.row(a, 12);
            r.setGravity(Gravity.CENTER_VERTICAL);
            r.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(12), Ui.dp(11));
            r.setBackground(Ui.round(Ui.LIGHT ? Color.argb(24, 62, 122, 221) : Color.argb(40, 115, 162, 230), 16, Color.argb(120, 115, 162, 230)));
            r.addView(Ui.text(a, "⚡", 22, Ui.FG, false), Ui.wrap());
            LinearLayout tx = Ui.col(a, 2);
            tx.addView(Ui.text(a, Ui.L("Bạn đang có " + n + " VPS NVMe", "You have " + n + " VPS NVMe"), 15, Ui.FG, true));
            tx.addView(Ui.muted(a, Ui.L("Điều khiển · gia hạn · nâng cấp · cài lại ở Máy của tôi", "Control · renew · upgrade · reinstall in My devices")));
            r.addView(tx, Ui.weight(1));
            r.addView(Ui.text(a, "›", 26, Ui.SKY, true), Ui.wrap());
            r.setClickable(true);
            r.setOnClickListener(v -> a.show(0));
            body.addView(r, Ui.fill());
        }
        if (mine == null || System.currentTimeMillis() - mineAt > 30000) loadMine(a, null);
        boolean stale = info == null || System.currentTimeMillis() - infoAt > 45000;
        if (stale && System.currentTimeMillis() - infoErrAt > 15000) loadInfo(a);
        if (info == null) {
            LinearLayout c = Ui.card(a);
            boolean bad = !infoErr.isEmpty() && !infoLoading;
            c.addView(Ui.muted(a, bad ? "⚠ " + Ui.L("Chưa tải được bảng giá: ", "Couldn't load prices: ") + infoErr : "⏳ " + Ui.L("Đang tải bảng giá…", "Loading prices…")));
            if (bad && !missing) {
                Button r = Ui.button(a, Ui.L("Thử lại", "Retry"), Ui.GHOST);
                r.setOnClickListener(v -> { infoErrAt = 0; loadInfo(a); });
                c.addView(r, Ui.fill());
            }
            body.addView(c, Ui.fill());
            return null;
        }
        final java.util.List<JSONObject> ps = plans();
        boolean sell = info.optBoolean("sell") || (info.optBoolean("admin") && a.isAdmin());
        if (!sell || ps.isEmpty()) {
            LinearLayout c = Ui.card(a);
            c.addView(Ui.text(a, "⚡ " + Ui.L("VPS NVMe tạm chưa mở bán", "VPS NVMe isn't on sale right now"), 16.5f, Ui.FG, true));
            c.addView(Ui.muted(a, Ui.L("Shop đang chuẩn bị máy chủ — quay lại sau ít phút, hoặc xem trên web.", "Please check back soon, or visit the website.")));
            body.addView(c, Ui.fill());
            return null;
        }
        // ---- mặc định: gói rẻ nhất còn chỗ · cấu hình tự chọn kẹp trong giới hạn
        if (bCust && !custOn(info)) bCust = false;
        if (!bCust && plan(bPlan) == null) {
            JSONObject best = null;
            for (JSONObject p : ps) if (p.optBoolean("free")) { long[] q = p30(p); if (best == null || (q != null && p30(best) != null && q[1] < p30(best)[1])) best = p; }
            if (best == null) best = ps.get(0);
            bPlan = best.optString("id"); bDisk = inc(best);
        }
        JSONObject p0 = plan(bPlan);
        if (p0 != null && bDisk < p0.optInt("disk_gb")) bDisk = inc(p0);
        int[] lm = lim();
        bCc = Math.max(1, Math.min(bCc, lm[0])); bCr = Math.max(1, Math.min(bCr, lm[1])); bCd = Math.max(Math.max(20, Math.min(bCd, lm[2])), 10);
        final JSONObject c = cu(info);
        final boolean light = Ui.LIGHT;
        final int heroFg = light ? Ui.FG : Color.WHITE, heroSub = light ? Ui.MUTED : Color.rgb(207, 224, 251);

        // ---- thẻ nổi bật
        LinearLayout hero = Ui.col(a, 10);
        hero.setPadding(Ui.dp(18), Ui.dp(16), Ui.dp(18), Ui.dp(16));
        GradientDrawable hg = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                light ? new int[]{Color.rgb(224, 235, 253), Color.rgb(233, 238, 250)} : new int[]{Color.rgb(26, 71, 146), Color.rgb(28, 57, 118), Color.rgb(11, 26, 58)});
        hg.setCornerRadius(Ui.dp(Ui.rad(22)));
        hg.setStroke(Math.max(2, Ui.dp(1.5f)), light ? Color.argb(90, 62, 122, 221) : Color.argb(150, 144, 181, 235));
        hero.setBackground(hg);
        hero.setElevation(Ui.dp(4));
        LinearLayout top = Ui.row(a, 12);
        top.setGravity(Gravity.CENTER_VERTICAL);
        TextView ic = Ui.text(a, "⚡", 28, heroFg, false);
        ic.setGravity(Gravity.CENTER);
        GradientDrawable ig = new GradientDrawable();
        ig.setShape(GradientDrawable.OVAL);
        ig.setColor(light ? Color.argb(36, 62, 122, 221) : Color.argb(56, 157, 190, 238));
        ic.setBackground(ig);
        top.addView(ic, new LinearLayout.LayoutParams(Ui.dp(56), Ui.dp(56)));
        LinearLayout tt = Ui.col(a, 2);
        tt.addView(Ui.text(a, NAME + " BLUE", 21, heroFg, true));
        tt.addView(Ui.text(a, Ui.L("Máy ảo Windows riêng · SSD NVMe · chạy 24/7", "Your own Windows VM · NVMe SSD · on 24/7"), 12.5f, heroSub, false));
        top.addView(tt, Ui.weight(1));
        hero.addView(top, Ui.fill());
        java.util.ArrayList<Double> cores = new java.util.ArrayList<>(), rams = new java.util.ArrayList<>(), frs = new java.util.ArrayList<>();
        boolean anyFree = false;
        for (JSONObject p : ps) { cores.add((double) p.optInt("cores")); rams.add(Math.round(p.optDouble("ram_mb", 0) / 102.4) / 10.0); frs.add((double) inc(p)); if (p.optBoolean("free")) anyFree = true; }
        if (custOn(info)) frs.add((double) freeGb(info));
        Ui.Wrap fw = new Ui.Wrap(a, 6);
        for (String f : new String[]{"⚙️ " + span(cores) + " vCPU", "🧠 " + span(rams) + " GB RAM", "💾 " + Ui.L("SSD NVMe " + span(frs) + " GB miễn phí", span(frs) + " GB NVMe SSD free")}) {
            TextView t = Ui.text(a, f, 13, light ? Ui.FG : Color.WHITE, true);
            t.setPadding(Ui.dp(11), Ui.dp(6), Ui.dp(11), Ui.dp(7));
            t.setBackground(Ui.round(light ? Color.argb(215, 255, 255, 255) : Color.argb(40, 255, 255, 255), 99, light ? Color.argb(70, 62, 122, 221) : Color.argb(80, 255, 255, 255)));
            fw.addView(t);
        }
        hero.addView(fw, Ui.fill());
        Ui.Wrap bw = new Ui.Wrap(a, 6);
        int mx = info.optInt("reinstall_max");
        java.util.ArrayList<String> perks = new java.util.ArrayList<>();
        perks.add("⚡ " + Ui.L("Tự tạo 3–10 phút", "Ready in 3–10 min"));
        perks.add("🖥 " + Ui.L("Web · app ĐT · app máy tính", "Web · phone · PC app"));
        if (info.optBoolean("upgrade")) perks.add("⬆ " + Ui.L("Nâng cấp sau khi thuê", "Upgrade anytime"));
        else if (mx > 0) perks.add("🔁 " + Ui.L("Cài lại " + mx + " lần", mx + " reinstalls"));
        perks.add("🔒 " + Ui.L("Máy riêng của bạn", "Your own VM"));
        for (String f : perks) bw.addView(Ui.text(a, f, 11.5f, heroSub, true));
        hero.addView(bw, Ui.fill());
        LinearLayout pr = Ui.row(a, 10);
        pr.setGravity(Gravity.CENTER_VERTICAL);
        double low = lowDay();
        LinearLayout pc0 = Ui.col(a, 0);
        if (low > 0) {
            pc0.addView(Ui.text(a, Ui.L("chỉ từ", "from"), 12, heroSub, false));
            pc0.addView(Ui.text(a, Ui.vnd(a.ctv(low)) + Ui.L(" / ngày", " / day"), 23, light ? Ui.SKY : Color.WHITE, true));
        }
        pr.addView(pc0, Ui.weight(1));
        pr.addView(Ui.pill(a, !mt.isEmpty() ? "🛠 " + Ui.L("Bảo trì", "Maintenance") : anyFree ? "⚡ " + Ui.L("Còn chỗ", "Available") : "⏳ " + Ui.L("Tạm hết chỗ", "Sold out"),
                !mt.isEmpty() || !anyFree ? Ui.WAIT : Ui.OK), Ui.wrap());
        hero.addView(pr, Ui.fill());
        body.addView(hero, Ui.fill());

        // ---- ① cấu hình
        LinearLayout s1 = Ui.card(a);
        java.util.TreeSet<Integer> dks = new java.util.TreeSet<>();
        for (JSONObject p : ps) dks.add(inc(p));
        final boolean oneDisk = dks.size() == 1;
        s1.addView(a.stepHead("1", Ui.L("Chọn cấu hình", "Choose a plan"), oneDisk ? Ui.L("Mọi gói có SSD NVMe " + dks.first() + " GB miễn phí.", "Every plan has a free " + dks.first() + " GB NVMe SSD.") : ""), Ui.fill());
        LinearLayout row = null;
        for (int i = 0; i < ps.size(); i++) {
            if (i % 2 == 0) { row = Ui.row(a, 8); s1.addView(row, Ui.fill()); }
            final JSONObject p = ps.get(i);
            boolean on = !bCust && p.optString("id").equals(bPlan), free = p.optBoolean("free");
            LinearLayout t = Ui.col(a, 2);
            t.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(12), Ui.dp(10));
            if (on) t.setBackground(Ui.gloss(16)); else t.setBackground(Ui.round(Ui.PANEL2, 16, Ui.RING));
            int fg = on ? Color.WHITE : free ? Ui.FG : Ui.MUTED;
            t.addView(Ui.text(a, (on ? "✓ " : "") + p.optString("name", p.optString("id")), 14.5f, fg, true));
            t.addView(Ui.text(a, "⚙️ " + p.optInt("cores") + " vCPU · 🧠 " + gb(p.optDouble("ram_mb", 0)) + (oneDisk ? "" : "\n💾 SSD NVMe " + inc(p) + " GB"), 11.5f, on ? Color.rgb(224, 235, 253) : Ui.MUTED, false));
            long[] q = p30(p);
            t.addView(Ui.text(a, free ? (q == null ? "" : Ui.vnd(a.ctv(q[1])) + (q[0] == 30 ? "/" + Ui.L("tháng", "month") : "/" + q[0] + Ui.L(" ngày", " days"))) : Ui.L("tạm hết chỗ", "sold out"),
                    13, on ? Color.WHITE : free ? Ui.SKY : Ui.MUTED, true));
            if (free) { t.setClickable(true); t.setOnClickListener(v -> pick(a, p.optString("id"))); Ui.press(t); } else t.setAlpha(.6f);
            row.addView(t, Ui.weight(1));
        }
        if (ps.size() % 2 == 1 && row != null) row.addView(new View(a), Ui.weight(1));
        if (custOn(info)) {
            LinearLayout t = Ui.col(a, 2);
            t.setPadding(Ui.dp(12), Ui.dp(10), Ui.dp(12), Ui.dp(10));
            if (bCust) t.setBackground(Ui.gloss(16)); else t.setBackground(Ui.round(Ui.PANEL2, 16, Ui.RING));
            LinearLayout r1 = Ui.row(a, 8);
            r1.addView(Ui.text(a, (bCust ? "✓ " : "") + "🛠 " + Ui.L("Tự chọn cấu hình", "Custom specs"), 14.5f, bCust ? Color.WHITE : Ui.FG, true), Ui.weight(1));
            long cm = bCust ? Math.max(1000, month(c, bCc, bCr, Math.max(0, bCd - freeGb(info)))) : month(c, 1, 1, 0);
            r1.addView(Ui.text(a, (bCust ? "" : Ui.L("từ ", "from ")) + Ui.vnd(a.ctv(cm)) + "/" + Ui.L("tháng", "month"), 13, bCust ? Color.WHITE : Ui.SKY, true), Ui.wrap());
            t.addView(r1, Ui.fill());
            t.addView(Ui.text(a, bCust ? "⚙️ " + bCc + " vCPU · 🧠 " + bCr + " GB RAM · 💾 SSD NVMe " + bCd + " GB" : Ui.L("Chọn vCPU, RAM, ổ theo ý bạn", "Pick vCPU, RAM and disk"),
                    11.5f, bCust ? Color.rgb(224, 235, 253) : Ui.MUTED, false));
            t.setClickable(true);
            t.setOnClickListener(v -> pick(a, "custom"));
            Ui.press(t);
            LinearLayout.LayoutParams lp = Ui.fill();
            lp.topMargin = Ui.dp(2);
            s1.addView(t, lp);
        }
        // ô cấu hình tự chọn / ổ của gói
        if (bCust) {
            int fr = freeGb(info);
            String mo = Ui.L("tháng", "month");
            s1.addView(new Step(a, "⚙️ vCPU", Ui.vnd(c.optDouble("unit_cpu", 0)) + " / vCPU / " + mo + " · " + Ui.L("tối đa ", "max ") + lm[0], bCc, 1, lm[0], 1, true, x -> { bCc = x; a.vmChanged(); }).view, Ui.fill());
            s1.addView(new Step(a, "🧠 RAM (GB)", Ui.vnd(c.optDouble("unit_ram", 0)) + " / GB / " + mo + " · " + Ui.L("tối đa ", "max ") + lm[1] + " GB", bCr, 1, lm[1], 1, true, x -> { bCr = x; a.vmChanged(); }).view, Ui.fill());
            s1.addView(new Step(a, "💾 SSD NVMe (GB)", Ui.L(fr + " GB đầu miễn phí", "first " + fr + " GB free") + (diskOn(info) ? " · " + Ui.L("thêm ", "extra ") + Ui.vnd(c.optDouble("unit_disk", 0)) + " / GB / " + mo : " · " + Ui.L("chưa bán ổ thêm", "no extra disk yet")),
                    bCd, 20, diskOn(info) ? lm[2] : Math.max(20, fr), 10, true, x -> { bCd = x; a.vmChanged(); }).view, Ui.fill());
        } else if (p0 != null && (diskOn(info) || inc(p0) > p0.optInt("disk_gb"))) {
            int d0 = p0.optInt("disk_gb"), ic0 = inc(p0);
            String sub = ic0 > d0 ? (diskOn(info) ? Ui.L("Miễn phí tới " + ic0 + " GB · vượt thì thêm " + Ui.vnd(c.optDouble("unit_disk", 0)) + " / GB / tháng", "Free up to " + ic0 + " GB · then " + Ui.vnd(c.optDouble("unit_disk", 0)) + " / GB / month")
                    : Ui.L("Miễn phí tới " + ic0 + " GB", "Free up to " + ic0 + " GB"))
                    : Ui.L("Gói có sẵn " + d0 + " GB · thêm " + Ui.vnd(c.optDouble("unit_disk", 0)) + " / GB / tháng", "Plan includes " + d0 + " GB · extra " + Ui.vnd(c.optDouble("unit_disk", 0)) + " / GB / month");
            s1.addView(new Step(a, "💾 " + Ui.L("Ổ SSD NVMe (GB)", "SSD NVMe disk (GB)"), sub, Math.max(d0, bDisk), d0, diskOn(info) ? Math.max(ic0, lm[2]) : ic0, 10, true, x -> { bDisk = x; a.vmChanged(); }).view, Ui.fill());
        }
        body.addView(s1, Ui.fill());

        // ---- ② Windows (bản máy chủ đã có máy mẫu; thiếu RAM / ổ → mờ kèm lý do)
        LinearLayout s2 = Ui.card(a);
        s2.addView(a.stepHead("2", Ui.L("Chọn Windows", "Choose Windows"), Ui.L("Cài sẵn — thuê xong là dùng.", "Pre-installed — ready to use.")), Ui.fill());
        JSONArray im = info.optJSONArray("images");
        java.util.ArrayList<JSONObject> ok = new java.util.ArrayList<>(), no = new java.util.ArrayList<>();
        int ram = ramMb(), dsk = diskGb();
        if (im != null) for (int i = 0; i < im.length(); i++) {
            JSONObject o = im.optJSONObject(i);
            if (o == null || o.optString("id").isEmpty() || !o.optBoolean("ready")) continue;
            if (o.optDouble("min_ram", 0) <= ram && o.optDouble("min_disk", 0) <= dsk) ok.add(o); else no.add(o);
        }
        boolean has = false;
        for (JSONObject o : ok) if (o.optString("id").equals(bImage)) has = true;
        if (!has) bImage = ok.isEmpty() ? "" : ok.get(0).optString("id");
        if (ok.isEmpty() && no.isEmpty()) s2.addView(Ui.text(a, Ui.L("Chưa có bản Windows nào sẵn sàng — nhắn shop.", "No Windows image is ready yet."), 13, Ui.WAIT, false));
        LinearLayout orow = null;
        java.util.ArrayList<JSONObject> all = new java.util.ArrayList<>(ok);
        all.addAll(no);
        for (int i = 0; i < all.size(); i++) {
            if (i % 2 == 0) { orow = Ui.row(a, 8); s2.addView(orow, Ui.fill()); }
            final JSONObject o = all.get(i);
            boolean can = ok.contains(o), on = can && o.optString("id").equals(bImage);
            String[] k = osKey(o.optString("name", o.optString("id")));
            LinearLayout t = Ui.col(a, 1);
            t.setGravity(Gravity.CENTER);
            t.setPadding(Ui.dp(8), Ui.dp(10), Ui.dp(8), Ui.dp(10));
            if (on) t.setBackground(Ui.gloss(16)); else t.setBackground(Ui.round(Ui.PANEL2, 16, Ui.RING));
            TextView k1 = Ui.text(a, (on ? "✓ " : "") + k[0], 11, on ? Color.rgb(224, 235, 253) : Ui.MUTED, true);
            TextView k2 = Ui.text(a, k[1], 17, on ? Color.WHITE : can ? Ui.FG : Ui.MUTED, true);
            TextView k3 = Ui.text(a, can ? "⚡ " + Ui.L("có sẵn", "ready") : o.optDouble("min_ram", 0) > ram ? Ui.L("cần gói từ " + gb(o.optDouble("min_ram", 0)) + " RAM", "needs " + gb(o.optDouble("min_ram", 0)) + " RAM")
                    : Ui.L("cần ổ từ " + o.optInt("min_disk") + " GB", "needs a " + o.optInt("min_disk") + " GB disk"), 11, on ? Color.WHITE : can ? Ui.OK : Ui.MUTED, true);
            for (TextView x : new TextView[]{k1, k2, k3}) { x.setGravity(Gravity.CENTER); t.addView(x, Ui.fill()); }
            if (can) { t.setClickable(true); t.setOnClickListener(v -> { bImage = o.optString("id"); a.vmChanged(); }); Ui.press(t); } else t.setAlpha(.6f);
            orow.addView(t, Ui.weight(1));
        }
        if (all.size() % 2 == 1 && orow != null) orow.addView(new View(a), Ui.weight(1));
        body.addView(s2, Ui.fill());

        // ---- ③ thời gian
        LinearLayout s3 = Ui.card(a);
        s3.addView(a.stepHead("3", Ui.L("Chọn thời gian thuê", "Choose rental time"), Ui.L("Thuê dài rẻ hơn · gia hạn ngay trong app.", "Longer is cheaper · renew in the app.")), Ui.fill());
        java.util.List<Integer> ds = daysList();
        if (!ds.contains(bDays)) bDays = ds.contains(30) ? 30 : ds.isEmpty() ? 0 : ds.get(0);
        double base = ds.isEmpty() ? 0 : priceFor(ds.get(0)) / (double) ds.get(0);
        for (final int d : ds) {
            long p = priceFor(d);
            boolean on = d == bDays;
            LinearLayout r = Ui.row(a, 10);
            r.setGravity(Gravity.CENTER_VERTICAL);
            r.setPadding(Ui.dp(14), Ui.dp(11), Ui.dp(14), Ui.dp(11));
            GradientDrawable g = Ui.round(on ? (light ? Color.rgb(234, 241, 253) : Color.rgb(24, 57, 112)) : Ui.PANEL, 16, 0);
            g.setStroke(Math.max(2, Ui.dp(on ? 2f : 1f)), on ? Ui.BLUE : Ui.LINE2);
            r.setBackground(g);
            r.addView(Ui.text(a, on ? "✓" : "○", 18, on ? Ui.BLUE : Ui.MUTED, true), Ui.wrap());
            LinearLayout l = Ui.col(a, 1);
            double pd = a.ctv(p) / (double) d;
            l.addView(Ui.text(a, d + Ui.L(" ngày", " days"), 15.5f, Ui.FG, true));
            l.addView(Ui.text(a, Ui.vnd(pd) + Ui.L(" / ngày", " / day"), 12, Ui.MUTED, false));
            r.addView(l, Ui.weight(1));
            LinearLayout rr = Ui.col(a, 3);
            rr.setGravity(Gravity.END);
            TextView pv = Ui.text(a, Ui.vnd(a.ctv(p)), 16.5f, Ui.SKY, true);
            pv.setGravity(Gravity.END);
            rr.addView(pv, Ui.wrap());
            int save = base > 0 ? (int) Math.round((1 - (p / (double) d) / base) * 100) : 0;
            if (save >= 1) rr.addView(Ui.pill(a, "−" + save + "%", Ui.OK), Ui.wrap());
            r.addView(rr, Ui.wrap());
            r.setClickable(true);
            r.setOnClickListener(v -> { bDays = d; a.vmChanged(); });
            Ui.press(r);
            LinearLayout.LayoutParams lp = Ui.fill();
            lp.topMargin = Ui.dp(6);
            s3.addView(r, lp);
        }
        if (ds.isEmpty()) s3.addView(Ui.text(a, Ui.L("Chưa có giá cho cấu hình này — chọn lại.", "No price for this configuration."), 13, Ui.BAD, false));
        body.addView(s3, Ui.fill());

        // ---- 🏷️ mã giảm giá (máy chủ kiểm khi thanh toán, như web)
        final EditText promo = Ui.input(a, "🏷️ " + Ui.L("Mã giảm giá (nếu có)", "Promo code (optional)"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        promo.setFilters(new InputFilter[]{new InputFilter.LengthFilter(40)});
        promo.setText(bPromo);
        promo.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int st, int co, int af) { }
            @Override public void onTextChanged(CharSequence s, int st, int be, int co) { }
            @Override public void afterTextChanged(Editable e) { bPromo = e.toString(); }
        });
        body.addView(promo, Ui.fill());
        body.addView(Ui.text(a, Ui.L("✅ Thanh toán xong máy chủ tự tạo VPS (thường 3–10 phút) — xem ở ⚡ VPS NVMe của bạn (Máy của tôi). Hạn tính từ lúc VPS lên. Hết chỗ thì không trừ tiền.",
                "✅ After payment the VPS is created automatically (usually 3–10 min) — see Your VPS NVMe in My devices. Time starts when it is up. No capacity → no charge."), 12, Ui.MUTED, false), Ui.fill());

        // ---- thanh thanh toán dưới màn hình
        final Long pr0 = bDays > 0 ? priceFor(bDays) : null;
        final double t0 = pr0 == null ? 0 : a.ctv(pr0), bal = a.prof.optDouble("balance", 0);
        JSONObject img = null;
        for (JSONObject o : ok) if (o.optString("id").equals(bImage)) img = o;
        String specS;
        if (bCust) specS = "🛠 " + bCc + " vCPU · " + bCr + " GB RAM · SSD NVMe " + bCd + " GB";
        else {
            int d0 = p0 == null ? 0 : p0.optInt("disk_gb"), ic0 = inc(p0);
            specS = (p0 == null ? "" : p0.optString("name")) + (bDisk > d0 ? " + " + (bDisk - d0) + " GB " + Ui.L("ổ", "disk") + " (SSD NVMe " + bDisk + " GB"
                    + (bDisk <= ic0 ? " · " + Ui.L("miễn phí", "free") : ic0 > d0 ? " · " + Ui.L("tính tiền ", "charged ") + (bDisk - ic0) + " GB" : "") + ")" : "");
        }
        final TextView sumL = Ui.text(a, specS + (img != null ? " · " + shortOs(img.optString("name")) : "") + (bDays > 0 ? " · " + bDays + Ui.L(" ngày", " days") : ""), 12, Ui.MUTED, true);
        sumL.setMaxLines(2);
        sumL.setEllipsize(android.text.TextUtils.TruncateAt.END);
        final TextView total = Ui.text(a, pr0 == null ? "—" : Ui.vnd(t0), 22, Ui.SKY, true);
        final TextView calc = Ui.text(a, Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal) + (a.isCtv() ? "  ·  CTV −" + a.prof.optInt("ctv_discount") + "%" : "")
                + (pr0 != null && bal < t0 ? Ui.L("  ·  thiếu ", "  ·  short by ") + Ui.vnd(t0 - bal) : ""), 11.5f, Ui.MUTED, false);
        calc.setMaxLines(2);
        final Button buy = Ui.button(a, pr0 != null && bal < t0 && bPromo.trim().isEmpty() ? Ui.L("Nạp tiền", "Top up") : Ui.L("Thuê ngay", "Rent now"), Ui.PRIMARY);
        boolean can = pr0 != null && !bImage.isEmpty() && mt.isEmpty();
        buy.setEnabled(can);
        buy.setAlpha(can ? 1f : .5f);
        LinearLayout sum = Ui.col(a, 6);
        sum.setPadding(Ui.dp(16), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        GradientDrawable sbg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                light ? new int[]{Color.WHITE, Color.rgb(239, 245, 254)} : new int[]{Color.rgb(22, 48, 104), Color.rgb(9, 22, 50)});
        sbg.setCornerRadius(Ui.dp(Ui.rad(20)));
        sbg.setStroke(Math.max(2, Ui.dp(1.5f)), light ? Color.argb(80, 62, 122, 221) : Color.argb(120, 144, 181, 235));
        sum.setBackground(sbg);
        sum.setElevation(Ui.dp(10));
        if (!mt.isEmpty()) sum.addView(Ui.text(a, mt, 12, Ui.WAIT, false), Ui.fill());
        LinearLayout sr = Ui.row(a, 10);
        sr.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout st = Ui.col(a, 0);
        st.addView(sumL);
        st.addView(total);
        st.addView(calc);
        sr.addView(st, Ui.weight(1));
        buy.setMinWidth(Ui.dp(120));
        sr.addView(buy, Ui.wrap());
        sum.addView(sr, Ui.fill());
        buy.setOnClickListener(v -> pay(a, buy));
        return sum;
    }

    /** Bấm Thuê: đọc lại bảng giá + số dư NGAY trước khi hỏi (giá đổi → báo xem lại), rồi vm_buy / vm_buy_custom. */
    private static void pay(MainActivity a, Button buy) {
        if (!maint(a).isEmpty()) { Ui.toast(a, maint(a)); return; }
        final Long shown = bDays > 0 ? priceFor(bDays) : null;
        if (shown == null || bImage.isEmpty()) return;
        final String code = bPromo.trim().replaceAll("[^A-Za-z0-9_-]", "");
        buy.setEnabled(false);
        Api.bg(() -> {
            try { Api.site(); } catch (Exception ignored) { }
            return new Object[]{Api.rpc("vm_shop_info", new JSONObject()), Api.profile()};
        }, r -> {
            buy.setEnabled(true);
            if (r[0] instanceof JSONObject) { info = (JSONObject) r[0]; infoAt = System.currentTimeMillis(); }
            if (r[1] instanceof JSONObject) a.prof = (JSONObject) r[1];
            Long pr = priceFor(bDays);
            if (pr == null || Math.abs(pr - shown) > 0) {
                Ui.toast(a, Ui.L("Bảng giá vừa được shop cập nhật — xem lại rồi bấm thuê.", "The price list just changed — please review."));
                a.vmChanged();
                return;
            }
            double t = a.ctv(pr), bal = a.prof.optDouble("balance", 0);
            if (code.isEmpty() && bal < t) { a.openTopup(t - bal); return; }
            JSONObject p = plan(bPlan);
            String spec = bCust ? "🛠 " + bCc + " vCPU · " + bCr + " GB RAM · SSD NVMe " + bCd + " GB" : (p == null ? "" : p.optString("name")) + " · SSD NVMe " + diskGb() + " GB";
            String osn = "";
            JSONArray im = info.optJSONArray("images");
            if (im != null) for (int i = 0; i < im.length(); i++) { JSONObject o = im.optJSONObject(i); if (o != null && bImage.equals(o.optString("id"))) osn = o.optString("name"); }
            Ui.confirm(a, Ui.L("Thuê VPS NVMe", "Rent VPS NVMe"), spec + "\n" + osn + " · " + bDays + Ui.L(" ngày", " days") + "\n" + (code.isEmpty() ? "" : "🏷️ " + code + "\n")
                            + Ui.L("Trừ ", "Charge ") + Ui.vnd(t) + (code.isEmpty() ? "" : Ui.L(" (trước giảm giá)", " (before discount)")) + Ui.L(" từ số dư.", " from your balance."),
                    Ui.L("Thanh toán", "Pay"), () -> place(a, buy, code, p));
        }, m -> { buy.setEnabled(true); Ui.toast(a, err(m)); });
    }

    private static void place(MainActivity a, Button buy, String code, JSONObject p) {
        buy.setEnabled(false);
        final boolean cust = bCust;
        final JSONObject args = new JSONObject();
        try {
            if (cust) args.put("p_cores", bCc).put("p_ram_gb", bCr).put("p_disk_gb", bCd).put("p_image", bImage).put("p_days", bDays);
            else {
                args.put("p_plan", bPlan).put("p_image", bImage).put("p_days", bDays);
                if (p != null && bDisk > p.optInt("disk_gb")) args.put("p_disk_gb", bDisk);
            }
            if (!code.isEmpty()) args.put("p_promo", code);
        } catch (Exception ignored) { }
        Api.bg(() -> Api.rpc(cust ? "vm_buy_custom" : "vm_buy", args), r -> {
            buy.setEnabled(true);
            JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
            Ui.toast(a, Ui.L("🎉 Đã thuê VPS-" + o.optLong("id") + " — máy chủ đang tạo (thường 3–10 phút). Xem ở ⚡ VPS NVMe của bạn.",
                    "🎉 VPS-" + o.optLong("id") + " rented — it is being created (3–10 min)."));
            bPromo = ""; mineAt = 0; infoAt = 0;
            loadMine(a, a::vmMineChanged);
            a.refresh();
            a.show(0);
        }, m -> { buy.setEnabled(true); Ui.toast(a, err(m)); });
    }
}
