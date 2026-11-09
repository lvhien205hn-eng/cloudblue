package shop.blueroblox.app;

import android.Manifest;
import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Màn chính: Máy của tôi · Thuê máy · Tài khoản. */
public class MainActivity extends Activity {
    static final int[] RAM = {2, 4, 6, 8, 12, 16}, CPU = {2, 4, 6, 8, 12, 16, 24, 32}, DAYS = {1, 3, 7, 15, 30, 60}, FPS = {30, 60, 90, 120}, QTY = {1, 2, 3, 5, 10};
    static final String[][] RES = {{"540x960", "Nhẹ máy"}, {"720x1280", "HD"}, {"720x1600", "HD+ dài"}, {"1080x1920", "Full HD"}, {"1080x2400", "FHD+ 20:9"}, {"1280x720", "HD ngang"}};

    private FrameLayout content;
    private TextView balTop;
    private final TextView[] nav = new TextView[3];
    private int tab = 0;
    private boolean loaded = false;
    private final Handler h = new Handler(Looper.getMainLooper());
    private final Runnable poll = this::refresh;
    private Dialog gridDlg = null;                  // màn hình "Xem tất cả máy"
    private LinearLayout gridRoot = null;           // nội dung "Xem tất cả" (vẽ lại tại chỗ khi dữ liệu đổi)
    private ScrollView gridSv = null, phonesSv = null;
    private boolean resumed = false, destroyed = false;

    // Ô xem trước trực tiếp: mỗi máy đang chạy 1 ô, dùng lại giữa thẻ máy và "Xem tất cả". Chỉ ô đang hiện trên màn hình mới phát hình.
    static final int MAX_LIVE = 16;                 // tối đa số ô phát hình cùng lúc
    private final java.util.LinkedHashMap<String, LivePreview> previews = new java.util.LinkedHashMap<>();
    private final Runnable vis = this::checkPreviews;
    private final Rect vr = new Rect();
    // Chữ "Còn … ngày" tự cập nhật mỗi lần tải lại, không vẽ lại cả trang (vẽ lại = ô xem trước nháy + mất vị trí cuộn)
    private final java.util.ArrayList<Runnable> ticks = new java.util.ArrayList<>(), gridTicks = new java.util.ArrayList<>();
    private String phonesSig = null;

    JSONArray phones = new JSONArray();
    JSONObject prof = new JSONObject(), price = new JSONObject(), status = new JSONObject();

    // lựa chọn khi thuê máy
    int sRam = 2, sCpu = 2, sDays = 7, sFps = 30, sQty = 1;
    String sRes = "720x1280", sAnd = "";
    boolean sFree = false;

    /** Phiên bản Android admin đang bán — đúng thứ tự admin nhập (VD "9,12,7"); trống → Android 9.
     *  LDPlayer 9 = Android 9 · MEmu = Android 12 + 7 — đơn tự chạy về đúng máy chủ. */
    java.util.List<String> andList() {
        java.util.List<String> l = new java.util.ArrayList<>();
        for (String v : price.optString("android_versions", "9").split(",")) { v = v.trim(); if (v.matches("\\d{1,2}") && !l.contains(v)) l.add(v); }
        if (l.isEmpty()) l.add("9");
        return l;
    }
    /** "" = còn chỗ · "off" = máy chủ bản này bảo trì / chưa có · "full" = không đủ RAM/CPU cho cấu hình đang chọn. */
    String andWhy(String v, int ram, int cpu) {
        if (isAdmin()) return "";
        JSONObject m = status.optJSONObject("android");
        if (m == null) return "";                       // máy chủ chưa báo theo từng bản → không chặn (SQL vẫn kiểm tra)
        JSONObject a = m.optJSONObject(v);
        if (a == null || !a.optBoolean("online", true)) return "off";
        return a.optDouble("free_ram", 0) < ram || a.optDouble("free_cpu", 0) < cpu ? "full" : "";
    }
    /** So với cấu hình SAU khi kẹp theo trần của bản v (đổi bản thì RAM/CPU tự kẹp lại). */
    String andWhy(String v) { int[] l = andLim(v); return andWhy(v, Math.min(sRam, l[0]), Math.min(sCpu, l[1])); }
    /** Trần 1 máy của bản Android v = min(trần chung, trần của bản đó) → {RAM GB, nhân}. Mặc định Android 9: 8·8 · Android 12 / 15 (MuMu): 16·32 · Android 7: 16·16.
        Trần tuyệt đối 16GB · 32 nhân (MuMu cho tối đa 16GB · 32 nhân 1 máy). */
    int[] andLim(String v) {
        int r = "9".equals(v) ? 8 : 16, c = "9".equals(v) ? 8 : "7".equals(v) ? 16 : 32;
        JSONObject al = price == null ? null : price.optJSONObject("android_limits");
        JSONObject x = al == null ? null : al.optJSONObject(v);
        if (x != null) { r = x.optInt("ram", r); c = x.optInt("cpu", c); }
        int gr = price == null ? r : price.optInt("max_ram", r), gc = price == null ? c : price.optInt("max_cpu", c);
        return new int[]{Math.max(1, Math.min(Math.min(r, gr <= 0 ? r : gr), 16)), Math.max(1, Math.min(Math.min(c, gc <= 0 ? c : gc), 32))};
    }
    /** Mặc định Android 9; bản 9 hết chỗ / bảo trì → bản đầu tiên còn chỗ. */
    String andPick() {
        java.util.List<String> l = andList(), ok = new java.util.ArrayList<>();
        for (String v : l) if (andWhy(v).isEmpty()) ok.add(v);
        return ok.contains("9") ? "9" : !ok.isEmpty() ? ok.get(0) : l.contains("9") ? "9" : l.get(0);
    }
    static String andHint(String v) {
        return "9".equals(v) ? Ui.L("Ổn định · phổ biến", "Stable · popular") : "12".equals(v) ? Ui.L("Mới", "New") : "15".equals(v) ? Ui.L("Mới nhất", "Newest")
                : "7".equals(v) ? Ui.L("Nhẹ", "Light") : "";
    }
    /** Vẽ lại các nút bản Android theo chỗ trống hiện tại (đổi RAM/CPU là cập nhật ngay). */
    void paintAnd(Ui.Wrap aw) {
        if (!andList().contains(sAnd) || "off".equals(andWhy(sAnd))) {         // bản đang chọn bảo trì → tự đổi (hết chỗ thì giữ, báo lỗi để khách chọn lại)
            sAnd = andPick(); int[] l = andLim(sAnd); sRam = Math.min(sRam, l[0]); sCpu = Math.min(sCpu, l[1]);
        }
        for (int i = 0; i < aw.getChildCount(); i++) {
            TextView ch = (TextView) aw.getChildAt(i);
            String v = (String) ch.getTag(), why = andWhy(v);
            ch.setText("Android " + v + "\n" + ("off".equals(why) ? Ui.L("Bảo trì", "Unavailable") : "full".equals(why) ? Ui.L("Hết chỗ", "Full") : andHint(v)));
            Ui.setChip(ch, v.equals(sAnd));
            ch.setEnabled(why.isEmpty());
            ch.setAlpha(why.isEmpty() ? 1f : .4f);
        }
    }
    /** Trần tuyệt đối (trần thật mỗi máy theo bản Android ở andLim) · tối đa 60 FPS (giống web). */
    static JSONObject clampHard(JSONObject p) {
        try {
            String[] k = {"max_ram", "max_cpu", "max_fps", "free_max_ram", "free_max_cpu"};
            int[] hv = {16, 32, 60, 16, 32};
            for (int i = 0; i < k.length; i++) {
                if (p.isNull(k[i])) { if (i < 3) p.put(k[i], hv[i]); continue; }
                int v = p.optInt(k[i], hv[i]);
                p.put(k[i], Math.min(v <= 0 ? hv[i] : v, hv[i]));
            }
        } catch (Exception ignored) { }
        return p;
    }
    boolean isAdmin() { return "admin".equals(prof.optString("role")); }
    /** Đang bảo trì và người dùng KHÔNG phải admin → khoá điều khiển (admin luôn toàn quyền, giống web). */
    boolean maintBlocks() { return status.optBoolean("maint", false) && !isAdmin(); }
    /** Ưu đãi miễn phí đang mở (admin bật + chưa hết giờ). */
    boolean freeLive() {
        if (!price.optBoolean("free_on", false)) return false;
        String u = price.optString("free_until", "");
        if (u.isEmpty() || "null".equals(u)) return true;
        if (android.os.Build.VERSION.SDK_INT < 26) return true;
        try { return java.time.OffsetDateTime.parse(u).toInstant().toEpochMilli() > System.currentTimeMillis(); } catch (Exception e) { return true; }
    }
    /** Số máy của chính tài khoản đang có (đang tạo / chạy / tạm dừng). */
    int myLive() {
        int n = 0;
        for (int i = 0; i < phones.length(); i++) {
            JSONObject p = phones.optJSONObject(i); if (p == null || p.optBoolean("shared", false)) continue;
            if (java.util.Arrays.asList("pending", "creating", "active", "expired", "cancelling").contains(p.optString("status"))) n++;
        }
        return n;
    }
    int maxPerUser() { return isAdmin() ? 0 : price.optInt("max_per_user", 0); }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Ui.init(this);
        if (!Api.loggedIn()) { toLogin(); return; }
        Ui.edgeToEdge(this);

        LinearLayout root = Ui.col(this, 0);
        root.setBackground(Ui.bubbles(this));

        // Đầu trang: cá voi Cloud Blue + tên + số dư + nút Sáng/Tối
        LinearLayout top = Ui.row(this, 10);
        top.setPadding(Ui.dp(14), Ui.dp(10), Ui.dp(14), Ui.dp(10));
        top.setBackground(Ui.round(Ui.LIGHT ? Color.argb(246, 243, 247, 252) : Color.argb(246, 7, 18, 38), 0, 0));
        top.addView(Ui.whale(this, 34), new LinearLayout.LayoutParams(Ui.dp(50), Ui.dp(34)));
        SpannableString bn = new SpannableString("CloudBlue");          // "Cloud" màu chữ thường + "Blue" xanh (giống logo web)
        bn.setSpan(new ForegroundColorSpan(Ui.LIGHT ? Ui.BLUE : Color.rgb(90, 168, 255)), 5, 9, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        TextView brand = Ui.text(this, "", 19, Ui.FG, true);
        brand.setText(bn);
        brand.setSingleLine(true);
        top.addView(brand, Ui.weight(1));
        balTop = Ui.pill(this, "…", Ui.SKY);
        balTop.setOnClickListener(v -> openTopup());
        top.addView(balTop, Ui.wrap());
        TextView th = Ui.text(this, Ui.LIGHT ? "🌙" : "☀️", 17, Ui.FG, false);
        th.setGravity(Gravity.CENTER);
        th.setContentDescription(Ui.L("Đổi chế độ Sáng / Tối", "Switch light / dark mode"));
        Ui.ripple(th, Ui.PANEL, 99, Ui.RING);
        th.setOnClickListener(v -> { Ui.setLight(this, !Ui.LIGHT); recreate(); });
        top.addView(th, new LinearLayout.LayoutParams(Ui.dp(40), Ui.dp(40)));
        root.addView(top, Ui.fill());

        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));

        // Thanh điều hướng dưới
        LinearLayout bar = Ui.row(this, 0);
        bar.setBackground(Ui.ringed(Ui.PANEL, 0));
        bar.setPadding(Ui.dp(6), Ui.dp(4), Ui.dp(6), Ui.dp(4));
        String[][] items = {{"📱", Ui.L("Máy của tôi", "My phones")}, {"➕", Ui.L("Thuê máy", "Rent")}, {"👤", Ui.L("Tài khoản", "Account")}};
        for (int i = 0; i < 3; i++) {
            final int t = i;
            TextView n = Ui.text(this, items[i][0] + "\n" + items[i][1], 12, Ui.MUTED, true);
            n.setGravity(Gravity.CENTER);
            n.setPadding(0, Ui.dp(8), 0, Ui.dp(8));
            n.setOnClickListener(v -> show(t));
            Ui.ripple(n, Color.TRANSPARENT, 14, 0);
            nav[i] = n;
            bar.addView(n, Ui.weight(1));
        }
        root.addView(bar, Ui.fill());
        Ui.insets(root, true, true);
        setContentView(root);

        askNotifyPermission();
        Updater.check(this, false);                 // có bản app mới → hiện thông báo cập nhật ngay trong app
        show(getIntent().getIntExtra("tab", 0));
        refresh();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        Api.onOutdated = () -> { if (!isFinishing()) Updater.check(this, false); };   // máy chủ báo app cũ → hộp bắt buộc cập nhật
        if (Api.loggedIn()) refresh();
        Updater.check(this, false);
        h.removeCallbacks(vis);
        h.postDelayed(vis, 400);                    // quay lại màn này → bật lại hình các ô đang hiện
    }

    @Override protected void onPause() {
        super.onPause();
        resumed = false;
        h.removeCallbacks(poll);
        h.removeCallbacks(vis);
        for (LivePreview lp : previews.values()) lp.pause();   // rời màn (vào điều khiển, ra ngoài…) → tắt hết hình xem trước
    }

    @Override protected void onDestroy() {
        destroyed = true;                           // kết quả tải dữ liệu về muộn (xoay máy, đổi Sáng/Tối…) không vẽ / tạo ô xem trước nữa
        h.removeCallbacksAndMessages(null);
        Dialog d = gridDlg;
        gridDlg = null;
        gridRoot = null;
        for (LivePreview lp : previews.values()) lp.pause();     // tắt hết trước (song song) rồi mới đóng cửa sổ lưới
        if (d != null) { d.setOnDismissListener(null); try { d.dismiss(); } catch (Exception ignored) { } }
        releasePreviews();
        super.onDestroy();
    }

    private void toLogin() {
        startActivity(new Intent(this, LoginActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
        finish();
    }

    private void askNotifyPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 7);
    }

    // ---------------- Tải dữ liệu ----------------
    void refresh() {
        h.removeCallbacks(poll);
        if (destroyed) return;
        Api.<Object[]>bg(() -> {
            Api.siteOnce();                                  // lần đầu: tên miền web hiện tại (settings.data.web)
            JSONObject[] o = {Api.profile(), Api.pricing(), Api.status()};
            JSONArray ps = Api.phones();
            return new Object[]{o, ps};
        }, r -> {
            if (destroyed) return;                   // màn này đã đóng (xoay máy…) → bỏ kết quả, không hẹn tải lại
            JSONObject[] o = (JSONObject[]) r[0];
            prof = o[0]; price = clampHard(o[1]); status = o[2]; phones = (JSONArray) r[1];
            balTop.setText("💰 " + Ui.vnd(prof.optDouble("balance", 0)));
            ExpiryAlarm.schedule(this, phones);
            if (tab == 0) {
                if (phonesSig().equals(phonesSig)) tick();      // không có gì đổi → chỉ cập nhật chữ thời hạn (ô xem trước chạy liền, không nháy)
                else renderPhones();
            }
            else if (tab == 2) renderAccount();
            else if (!loaded) renderRent();          // lần đầu: vẽ lại bảng thuê với giá và giới hạn thật
            loaded = true;
            boolean pending = false;
            for (int i = 0; i < phones.length(); i++) if ("pending".equals(phones.optJSONObject(i).optString("status"))) pending = true;
            if (resumed) h.postDelayed(poll, pending ? 8000 : 30000);    // đang ở màn khác → thôi tự tải lại (quay về onResume tải ngay)
        }, m -> {
            if (destroyed) return;
            if (!Api.loggedIn()) { toLogin(); return; }
            if (!resumed) return;
            Ui.toast(this, m);
            h.postDelayed(poll, 30000);
        });
    }

    void show(int t) {
        tab = t;
        for (int i = 0; i < 3; i++) {
            nav[i].setTextColor(i == t ? Ui.SKY : Ui.MUTED);
            nav[i].setBackground(i == t ? Ui.round(Ui.LIGHT ? Color.argb(28, 43, 110, 240) : Color.argb(40, 90, 175, 255), 14, 0) : null);
        }
        if (t != 0) { releasePreviews(); phonesSig = null; ticks.clear(); }     // sang tab khác → tắt hẳn hình xem trước (đỡ pin + mạng)
        if (t == 0) renderPhones(); else if (t == 1) renderRent(); else renderAccount();
    }

    private ScrollView page(LinearLayout body) {
        body.setPadding(Ui.dp(16), Ui.dp(6), Ui.dp(16), Ui.dp(24));
        ScrollView sv = Ui.scroll(this, body);
        content.removeAllViews();
        content.addView(sv, new FrameLayout.LayoutParams(-1, -1));
        return sv;
    }

    // ---------------- Thời gian / giá ----------------
    static long parseTime(String s) {
        if (s == null || s.isEmpty() || s.equals("null")) return 0;
        try {
            String t = s.replace(" ", "T").replaceAll("\\.\\d+", "");
            if (t.endsWith("Z")) t = t.substring(0, t.length() - 1) + "+00:00";
            if (t.matches(".*[+-]\\d\\d$")) t = t + ":00";
            Date d = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).parse(t);
            return d == null ? 0 : d.getTime();
        } catch (Exception e) { return 0; }
    }

    static String fdate(long ms) { return new SimpleDateFormat("HH:mm dd/MM/yyyy", Locale.getDefault()).format(new Date(ms)); }

    static String left(long ms) {
        long d = ms - System.currentTimeMillis();
        if (d <= 0) return Ui.L("Đã hết hạn", "Expired");
        long m = d / 60000, hh = m / 60, dd = hh / 24;
        if (dd >= 1) return Ui.L("Còn " + dd + " ngày " + (hh % 24) + " giờ", dd + "d " + (hh % 24) + "h left");
        if (hh >= 1) return Ui.L("Còn " + hh + " giờ " + (m % 60) + " phút", hh + "h " + (m % 60) + "m left");
        return Ui.L("Còn " + m + " phút", m + " min left");
    }

    boolean isCtv() { return "approved".equals(prof.optString("ctv_status")) && prof.optDouble("ctv_discount", 0) > 0; }
    double ctv(double v) { return isCtv() ? Math.round(v * (100 - prof.optDouble("ctv_discount", 0)) / 100) : v; }
    double perDay(double ram, double cpu) { return ram * price.optDouble("price_ram_gb_day", 2500) + cpu * price.optDouble("price_cpu_day", 2000); }

    static boolean locked(JSONObject p) {
        if (!p.optBoolean("locked", false)) return false;
        long u = parseTime(p.optString("locked_until", ""));
        return u == 0 || u > System.currentTimeMillis();
    }

    // ---------------- TAB 1: Máy của tôi ----------------
    void renderPhones() {
        if (destroyed) return;
        final int keepY = phonesSv != null && phonesSv.getParent() != null ? phonesSv.getScrollY() : 0;   // vẽ lại giữ nguyên chỗ đang cuộn
        ticks.clear();
        parkPreviews();                             // sắp chuyển mọi ô xem trước sang thẻ mới → dừng bộ giải mã trước, song song
        LinearLayout body = Ui.col(this, 14);
        if (status.optBoolean("maint", false)) {
            LinearLayout m = Ui.card(this);
            m.setBackground(Ui.round(Color.argb(30, 255, 200, 97), 18, Color.argb(120, 255, 200, 97)));
            m.addView(Ui.text(this, "🛠 " + Ui.L("Đang bảo trì", "Under maintenance"), 15, Ui.WAIT, true));
            String msg = status.optString("maint_msg", "");
            m.addView(Ui.muted(this, isAdmin() ? Ui.L("Khách đang không dùng được. Tài khoản admin vẫn toàn quyền: điều khiển, thuê, gia hạn, công cụ.",
                    "Customers are blocked. Admin keeps full access: control, rent, renew, tools.")
                    : msg.isEmpty() || msg.equals("null") ? Ui.L("Máy của bạn vẫn được giữ, không bị tính hết hạn trong lúc bảo trì.", "Your phones are kept during maintenance.") : msg));
            body.addView(m, Ui.fill());
        }
        LinearLayout head = Ui.row(this, 10);
        head.addView(Ui.h1(this, Ui.L("Máy của tôi", "My phones")), Ui.weight(1));
        if (phones.length() > 0) {
            TextView all = Ui.pill(this, "▦ " + Ui.L("Xem tất cả", "View all"), Ui.OK);
            all.setOnClickListener(v -> openGrid());
            head.addView(all, Ui.wrap());
        }
        TextView rf = Ui.pill(this, "⟳ " + Ui.L("Làm mới", "Refresh"), Ui.SKY);
        rf.setOnClickListener(v -> {
            Ui.toast(this, Ui.L("Đang làm mới…", "Refreshing…"));
            for (LivePreview lp : previews.values()) lp.retry();    // ô xem trước đã dừng (máy chủ vừa cập nhật…) → thử lại
            phonesSig = null;
            refresh();
        });
        head.addView(rf, Ui.wrap());
        body.addView(head, Ui.fill());

        // Nhập mã: mã TẶNG MÁY (12 ký tự) · mã chia sẻ / chuyển nhượng (8 ký tự)
        LinearLayout cr = Ui.row(this, 8);
        EditText code = Ui.input(this, Ui.L("🔑 Mã tặng máy / chia sẻ / chuyển nhượng", "🔑 Gift / share / transfer code"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        cr.addView(code, Ui.weight(1));
        Button cb = Ui.button(this, Ui.L("Nhập mã", "Redeem"), Ui.GHOST);
        cb.setOnClickListener(v -> claim(code, cb));
        cr.addView(cb, Ui.wrap());
        body.addView(cr, Ui.fill());

        if (phones.length() == 0) {
            LinearLayout e = Ui.card(this);
            e.setGravity(Gravity.CENTER_HORIZONTAL);
            TextView ic = Ui.text(this, "📱", 44, Ui.FG, false);
            ic.setGravity(Gravity.CENTER);
            e.addView(ic, Ui.fill());
            TextView t = Ui.h2(this, Ui.L("Bạn chưa thuê máy nào", "You have no phones yet"));
            t.setGravity(Gravity.CENTER);
            e.addView(t, Ui.fill());
            TextView d = Ui.muted(this, Ui.L("Chọn RAM, CPU, số ngày — máy Android sẵn sàng sau khoảng 2–3 phút.", "Pick RAM, CPU and days — your Android phone is ready in 2–3 minutes."));
            d.setGravity(Gravity.CENTER);
            e.addView(d, Ui.fill());
            Button go = Ui.button(this, Ui.L("Thuê máy ngay", "Rent a phone"), Ui.PRIMARY);
            go.setOnClickListener(v -> show(1));
            e.addView(go, Ui.fill());
            body.addView(e, Ui.fill());
        }
        java.util.HashSet<String> live = new java.util.HashSet<>();
        for (int i = 0; i < phones.length(); i++) {
            JSONObject p = phones.optJSONObject(i);
            if (p == null) continue;
            if (canCtl(p)) live.add(p.optString("id"));
            body.addView(phoneCard(p), Ui.fill());
        }
        final ScrollView sv = page(body);
        phonesSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        prunePreviews(live);                        // máy không còn chạy (hết hạn, khoá, bảo trì, đã xoá) → bỏ ô xem trước
        if (gridOpen()) fillGrid();                 // đang mở "Xem tất cả" → vẽ lại lưới luôn (ô xem trước nằm bên đó)
        phonesSig = phonesSig();
        h.removeCallbacks(vis);
        if (resumed) h.postDelayed(vis, 300);
    }

    /** Máy điều khiển được (đang chạy, không bị khoá — admin bỏ qua khoá — và không bảo trì). */
    boolean canCtl(JSONObject p) {
        return "active".equals(p.optString("status")) && (!locked(p) || isAdmin()) && !maintBlocks();
    }

    /** Dấu vân tay những gì danh sách đang hiện: giống lần trước → khỏi vẽ lại (thời hạn tự cập nhật bằng tick()). */
    String phonesSig() {
        StringBuilder b = new StringBuilder(256);
        b.append(status.optBoolean("maint", false)).append('|').append(status.optString("maint_msg", "")).append('|')
                .append(isAdmin()).append('|').append(maintBlocks());
        String[] keys = {"id", "name", "status", "ram", "cpu", "res", "fps", "expires_at", "lock_reason", "shared", "share_expires", "owner_name", "share_id"};
        for (int i = 0; i < phones.length(); i++) {
            JSONObject p = phones.optJSONObject(i);
            if (p == null) continue;
            b.append('\n').append(locked(p));
            for (String k : keys) b.append('|').append(p.opt(k));
        }
        return b.toString();
    }

    /** Cập nhật chữ thời hạn của danh sách + lưới (không vẽ lại). */
    void tick() {
        for (Runnable r : ticks) r.run();
        for (Runnable r : gridTicks) r.run();
    }

    /** Độ phân giải máy đã mua → {rộng, cao} (mặc định 720×1280). */
    static int[] resWH(JSONObject p) {
        try {
            String[] wh = p.optString("res", "720x1280").toLowerCase(Locale.ROOT).split("x");
            int w = Integer.parseInt(wh[0].trim()), hh = Integer.parseInt(wh[1].trim());
            if (w >= 100 && hh >= 100 && w <= 8000 && hh <= 8000) return new int[]{w, hh};
        } catch (Exception ignored) { }
        return new int[]{720, 1280};
    }

    // ---------------- Ô xem trước trực tiếp ----------------
    /** Ô xem trước của máy p: lấy lại ô cũ (gỡ khỏi chỗ cũ, hình chạy tiếp) hoặc tạo mới; ô tĩnh vẽ theo trạng thái hiện tại. */
    private LivePreview livePreview(JSONObject p, float iconSp) {
        String id = p.optString("id");
        LivePreview lp = previews.get(id);
        if (lp == null) {
            int[] wh = resWH(p);
            lp = new LivePreview(this, id, wh[0], wh[1], "c".equals(StreamClient.netTag(this)) ? 320 : 480);   // 4G/5G → ô nhỏ hơn, đỡ tốn dữ liệu
            previews.put(id, lp);
        }
        lp.setCover(phoneTile(p, iconSp));
        ViewParent vp = lp.getParent();
        if (vp instanceof ViewGroup) ((ViewGroup) vp).removeView(lp);
        lp.hiddenAt = 0;
        return lp;
    }

    private void prunePreviews(java.util.Set<String> keep) {
        java.util.ArrayList<LivePreview> gone = new java.util.ArrayList<>();
        java.util.Iterator<java.util.Map.Entry<String, LivePreview>> it = previews.entrySet().iterator();
        while (it.hasNext()) {
            java.util.Map.Entry<String, LivePreview> e = it.next();
            if (keep.contains(e.getKey())) continue;
            gone.add(e.getValue());
            it.remove();
        }
        dropAll(gone);
    }

    private void releasePreviews() {
        h.removeCallbacks(vis);
        java.util.ArrayList<LivePreview> all = new java.util.ArrayList<>(previews.values());
        previews.clear();
        dropAll(all);
    }

    /** Bỏ hẳn các ô: tắt hết (bộ giải mã các ô dừng song song) → gỡ khỏi màn hình (Surface huỷ khi đã thôi vẽ) → giải phóng luồng giải mã. */
    private static void dropAll(java.util.List<LivePreview> l) {
        for (LivePreview lp : l) lp.pause();
        for (LivePreview lp : l) {
            ViewParent vp = lp.getParent();
            if (vp instanceof ViewGroup) ((ViewGroup) vp).removeView(lp);
        }
        for (LivePreview lp : l) lp.release();
    }

    /** Trước khi chuyển hàng loạt ô (vẽ lại danh sách, mở / đóng "Xem tất cả"): dừng bộ giải mã mọi ô cùng lúc. */
    private void parkPreviews() {
        for (LivePreview lp : previews.values()) lp.park();
    }

    /** Mỗi giây (khi đang mở màn này): bật ô đang hiện trên màn hình, tạm dừng ô khuất quá 5 giây; tối đa MAX_LIVE ô phát cùng lúc. */
    private void checkPreviews() {
        h.removeCallbacks(vis);
        if (destroyed || !resumed || previews.isEmpty() || isFinishing()) return;
        long now = SystemClock.uptimeMillis();
        int min = Ui.dp(24), n = 0, need = 0;
        java.util.ArrayList<LivePreview> want = new java.util.ArrayList<>();
        for (LivePreview lp : previews.values()) {
            boolean seen = lp.isAttachedToWindow() && lp.isShown() && lp.getGlobalVisibleRect(vr) && vr.width() >= min && vr.height() >= min;
            if (seen) {
                lp.hiddenAt = 0;
                want.add(lp);
                if (!lp.playing() && !lp.ended()) need++;
            } else {
                if (lp.hiddenAt == 0) lp.hiddenAt = now;
                if (lp.playing() && now - lp.hiddenAt > 5000) lp.pause();
            }
            if (lp.playing()) n++;
        }
        if (need > 0 && n + need > MAX_LIVE) {              // hết chỗ → nhường từ các ô đang khuất trước
            for (LivePreview lp : previews.values()) {
                if (n + need <= MAX_LIVE) break;
                if (lp.playing() && lp.hiddenAt != 0) { lp.pause(); n--; }
            }
        }
        for (LivePreview lp : want) {
            if (lp.playing() || lp.ended()) continue;
            if (n >= MAX_LIVE) break;
            lp.play();
            n++;
        }
        h.postDelayed(vis, 1000);
    }

    boolean gridOpen() { return gridDlg != null && gridRoot != null; }

    /** Ô tĩnh: biểu tượng điện thoại + trạng thái — máy không chạy, hoặc phủ trên ô xem trước lúc chưa có hình / máy chủ chưa hỗ trợ xem trước. */
    private View phoneTile(JSONObject p, float iconSp) {
        String st = p.optString("status");
        boolean lk = locked(p) && !isAdmin(), live = "active".equals(st) && !lk && !maintBlocks();
        LinearLayout t = Ui.col(this, 4);
        t.setGravity(Gravity.CENTER);
        t.setPadding(Ui.dp(8), Ui.dp(8), Ui.dp(8), Ui.dp(8));
        TextView ic = Ui.text(this, "📱", iconSp, Color.WHITE, false);
        ic.setGravity(Gravity.CENTER);
        t.addView(ic, Ui.fill());
        String s = lk ? "🔒 " + Ui.L("Bị khoá", "Locked")
                : "active".equals(st) ? (live ? "● " + Ui.L("Đang chạy", "Running") : "🛠 " + Ui.L("Đang bảo trì", "Maintenance"))
                : "pending".equals(st) ? "◌ " + Ui.L("Đang tạo…", "Creating…")
                : "expired".equals(st) ? "⏸ " + Ui.L("Tạm dừng", "Paused") : Ui.L("Lỗi", "Error");
        TextView tx = Ui.text(this, s, 12, live ? Color.rgb(60, 224, 176) : Color.rgb(255, 120, 140), true);
        tx.setGravity(Gravity.CENTER);
        tx.setSingleLine(true);
        t.addView(tx, Ui.fill());
        if (live) {
            TextView hint = Ui.text(this, Ui.L("Bấm để điều khiển", "Tap to control"), 11, Color.argb(190, 255, 255, 255), false);
            hint.setGravity(Gravity.CENTER);
            t.addView(hint, Ui.fill());
        }
        return t;
    }

    // ---------------- XEM TẤT CẢ MÁY: lưới mọi máy phát hình trực tiếp + trạng thái (khách có nhiều máy theo dõi 1 lần) ----------------
    void openGrid() {
        if (destroyed) return;
        Dialog old = gridDlg;
        gridDlg = null;
        parkPreviews();                             // ô xem trước sắp chuyển sang lưới → dừng bộ giải mã trước, song song
        if (old != null) { old.setOnDismissListener(null); old.dismiss(); }
        LinearLayout root = Ui.col(this, 10);
        root.setBackgroundColor(Ui.BG);
        Dialog d = new Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen) {
            @Override public void onBackPressed() { closeGrid(); }      // nút Back = nút Đóng
        };
        d.setContentView(root);
        d.setOnDismissListener(x -> {
            if (gridDlg != d) return;
            gridDlg = null;
            gridRoot = null;
            gridSv = null;
            gridTicks.clear();
            if (!isFinishing() && tab == 0) renderPhones();     // ô xem trước về lại thẻ máy trong danh sách
        });
        gridDlg = d;
        gridRoot = root;
        fillGrid();
        d.show();
        h.removeCallbacks(vis);
        if (resumed) h.postDelayed(vis, 300);
    }

    /** Vẽ (lại) nội dung "Xem tất cả" tại chỗ — giữ chỗ đang cuộn, ô xem trước chuyển sang đây và phát tiếp. */
    private void fillGrid() {
        final LinearLayout root = gridRoot;
        if (root == null || destroyed) return;
        final int keepY = gridSv != null ? gridSv.getScrollY() : 0;
        gridTicks.clear();
        parkPreviews();
        root.removeAllViews();
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        float wdp = dm.widthPixels / dm.density;
        final int cols = wdp >= 900 ? 6 : wdp >= 600 ? 4 : wdp >= 330 ? 3 : 2;
        int gap = Ui.dp(8), pad = Ui.dp(12);
        int cellW = (dm.widthPixels - pad * 2 - gap * (cols - 1)) / cols, cellH = cellW * 16 / 9;   // ô dọc như màn điện thoại

        root.setPadding(pad, Ui.dp(14), pad, Ui.dp(10));
        LinearLayout top = Ui.row(this, 10);
        int run = 0, pause = 0, other = 0;
        for (int i = 0; i < phones.length(); i++) {
            String st = phones.optJSONObject(i).optString("status");
            if ("active".equals(st) && !locked(phones.optJSONObject(i))) run++; else if ("expired".equals(st)) pause++; else other++;
        }
        LinearLayout tt = Ui.col(this, 2);
        tt.addView(Ui.h2(this, Ui.L("Tất cả máy (", "All phones (") + phones.length() + ")"));
        tt.addView(Ui.muted(this, "● " + run + Ui.L(" đang chạy", " running") + (pause > 0 ? " · ⏸ " + pause + Ui.L(" tạm dừng", " paused") : "")
                + (other > 0 ? " · " + other + Ui.L(" khác", " other") : "") + Ui.L(" · bấm ô: điều khiển", " · tap a phone to control")));
        top.addView(tt, Ui.weight(1));
        TextView close = Ui.pill(this, "✕ " + Ui.L("Đóng", "Close"), Ui.SKY);
        top.addView(close, Ui.wrap());
        root.addView(top, Ui.fill());

        LinearLayout grid = Ui.col(this, gap);
        LinearLayout row = null;
        for (int i = 0; i < phones.length(); i++) {
            final JSONObject p = phones.optJSONObject(i);
            if (i % cols == 0) { row = Ui.row(this, gap); grid.addView(row, Ui.fill()); }
            final String pid = p.optString("id");
            boolean live = canCtl(p);
            LinearLayout cell = Ui.col(this, 4);
            FrameLayout box = new FrameLayout(this);
            box.setBackground(Ui.round(Color.rgb(2, 4, 12), 8, live ? Color.argb(90, 61, 220, 132) : Color.argb(70, 255, 93, 108)));
            int bz = Ui.dp(3.5f);
            box.setPadding(bz, bz, bz, bz);                              // viền bo góc bao quanh hình (góc hình vuông nằm gọn trong viền)
            box.addView(live ? livePreview(p, 24) : phoneTile(p, 24), new FrameLayout.LayoutParams(-1, -1));   // máy đang chạy: phát hình trực tiếp
            TextView dot = Ui.text(this, live ? "●" : "○", 12, live ? Ui.OK : Ui.BAD, true);
            dot.setShadowLayer(3, 0, 0, Color.BLACK);                     // nổi trên nền hình
            FrameLayout.LayoutParams dlp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.END);
            dlp.setMargins(0, Ui.dp(4), Ui.dp(6), 0);
            box.addView(dot, dlp);
            if (live) box.setOnClickListener(v -> startActivity(new Intent(this, ControlActivity.class).putExtra("id", pid)));   // bấm: vào điều khiển
            cell.addView(box, new LinearLayout.LayoutParams(-1, cellH));
            TextView nm = Ui.text(this, p.optString("name", "Máy"), 12, Ui.FG, true);
            nm.setSingleLine(true); nm.setEllipsize(android.text.TextUtils.TruncateAt.END);
            cell.addView(nm, Ui.fill());
            if (parseTime(p.optString("expires_at")) > 0) cell.addView(expiryText(p, false, gridTicks), Ui.fill());
            row.addView(cell, new LinearLayout.LayoutParams(0, -2, 1f));
        }
        if (row != null) for (int k = phones.length() % cols; k > 0 && k < cols; k++) row.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1f));   // ô trống cho hàng cuối thẳng cột
        final ScrollView sv = new ScrollView(this);
        sv.addView(grid);
        root.addView(sv, new LinearLayout.LayoutParams(-1, 0, 1f));
        gridSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        close.setOnClickListener(v -> closeGrid());
    }

    /** Đóng "Xem tất cả": dừng bộ giải mã mọi ô trước (song song) rồi mới đóng — đóng cửa sổ huỷ Surface của mọi ô cùng lúc. */
    private void closeGrid() {
        Dialog d = gridDlg;
        if (d == null) return;
        parkPreviews();
        d.dismiss();
    }

    /** Dòng thời hạn của máy (thẻ: đầy đủ · lưới: ngắn); tự cập nhật qua tick() mà không vẽ lại trang. */
    private TextView expiryText(JSONObject p, boolean full, java.util.List<Runnable> into) {
        final long exp = parseTime(p.optString("expires_at"));
        final boolean expired = "expired".equals(p.optString("status"));
        final TextView t = Ui.text(this, "", full ? 13.5f : 11, Ui.MUTED, false);
        if (!full) t.setSingleLine(true);
        final Typeface bold = Typeface.create("sans-serif-medium", Typeface.BOLD);
        Runnable r = () -> {
            long remain = exp - System.currentTimeMillis();
            if (!full) {
                t.setText("⏱ " + left(exp));
                t.setTextColor(remain < 86400000L ? Ui.WAIT : Ui.MUTED);
                return;
            }
            String s = "⏱ " + left(exp) + " · " + Ui.L("hết hạn ", "expires ") + fdate(exp);
            if (expired) {
                long del = exp + 30 * 60000L - System.currentTimeMillis();
                s = "⚠️ " + Ui.L("Đã hết hạn — gia hạn trong " + Math.max(0, del / 60000) + " phút nữa kẻo bị xoá", "Expired — renew within " + Math.max(0, del / 60000) + " min or it will be deleted");
            }
            t.setText(s);
            t.setTextColor(remain <= 0 ? Ui.BAD : remain < 86400000L ? Ui.WAIT : Ui.MUTED);
            t.setTypeface(remain < 86400000L ? bold : Typeface.DEFAULT);
        };
        r.run();
        into.add(r);
        return t;
    }

    private View phoneCard(JSONObject p) {
        LinearLayout c = Ui.card(this);
        String st = p.optString("status");
        boolean lk = locked(p);
        long exp = parseTime(p.optString("expires_at"));
        long remain = exp - System.currentTimeMillis();

        LinearLayout r1 = Ui.row(this, 10);
        r1.addView(Ui.text(this, p.optString("name", "Máy"), 17, Ui.FG, true), Ui.weight(1));
        String label; int col;
        if (lk) { label = "🔒 " + Ui.L("Bị khoá", "Locked"); col = Ui.BAD; }
        else if ("active".equals(st)) { label = "● " + Ui.L("Đang chạy", "Running"); col = Ui.OK; }
        else if ("pending".equals(st)) { label = "◌ " + Ui.L("Đang tạo…", "Creating…"); col = Ui.WAIT; }
        else if ("expired".equals(st)) { label = "⏸ " + Ui.L("Tạm dừng", "Paused"); col = Ui.BAD; }
        else { label = Ui.L("Lỗi", "Error"); col = Ui.BAD; }
        r1.addView(Ui.pill(this, label, col), Ui.wrap());
        c.addView(r1, Ui.fill());

        c.addView(Ui.muted(this, p.optInt("ram") + "GB RAM · " + p.optInt("cpu") + Ui.L(" nhân", " cores") + " · " + p.optString("res", "") + " · " + p.optInt("fps", 30) + " FPS"), Ui.fill());

        if (exp > 0) c.addView(expiryText(p, true, ticks), Ui.fill());
        if (lk) {
            String why = p.optString("lock_reason", "");
            c.addView(Ui.text(this, Ui.L("Máy đang bị khoá", "This phone is locked") + (why.isEmpty() || why.equals("null") ? "" : ": " + why), 13, Ui.BAD, false), Ui.fill());
        }
        if ("pending".equals(st)) c.addView(Ui.muted(this, Ui.L("Máy đang khởi động và cài app sẵn, khoảng 2–3 phút. Trang tự cập nhật.", "Booting and installing apps, about 2–3 minutes.")), Ui.fill());
        boolean shared = p.optBoolean("shared", false);
        if (shared) {
            long se = parseTime(p.optString("share_expires", ""));
            c.addView(Ui.text(this, "👥 " + Ui.L("Được chia sẻ bởi ", "Shared by ") + p.optString("owner_name", "?")
                    + (se > 0 ? Ui.L(" · đến ", " · until ") + fdate(se) : Ui.L(" · theo hạn máy", " · until expiry")), 13, Ui.SKY, false), Ui.fill());
        }

        boolean canCtl = canCtl(p);
        if (canCtl) {                                    // màn hình máy phát TRỰC TIẾP (hình nhỏ, chỉ xem) — bấm vào để điều khiển
            final String pid = p.optString("id");
            FrameLayout box = new FrameLayout(this);
            box.setBackground(Ui.round(Color.rgb(2, 4, 12), 10, Color.argb(60, 120, 160, 255)));
            int bz = Ui.dp(4);
            box.setPadding(bz, bz, bz, bz);              // viền bo góc bao quanh hình (góc hình vuông nằm gọn trong viền)
            box.addView(gridOpen() ? phoneTile(p, 30) : livePreview(p, 30), new FrameLayout.LayoutParams(-1, -1));   // đang mở "Xem tất cả" → hình nằm bên đó
            box.setOnClickListener(v -> startActivity(new Intent(this, ControlActivity.class).putExtra("id", pid)));
            int[] wh = resWH(p);
            int bw, bh, maxW = getResources().getDisplayMetrics().widthPixels - Ui.dp(80);
            if (wh[1] >= wh[0]) { bh = Ui.dp(190); bw = Math.max(Ui.dp(96), bh * wh[0] / wh[1]); }        // máy dọc: cao 190dp, rộng theo tỉ lệ
            else { bw = Math.min(Ui.dp(280), maxW); bh = Math.max(Ui.dp(110), bw * wh[1] / wh[0]); }        // máy ngang
            LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(bw + 2 * bz, bh + 2 * bz);
            blp.gravity = Gravity.CENTER_HORIZONTAL;
            c.addView(box, blp);
        }
        LinearLayout acts = Ui.row(this, 8);
        Button ctl = Ui.button(this, "▶ " + Ui.L("Điều khiển", "Control"), Ui.PRIMARY);
        ctl.setEnabled(canCtl);
        ctl.setAlpha(canCtl ? 1f : .45f);
        ctl.setOnClickListener(v -> startActivity(new Intent(this, ControlActivity.class).putExtra("id", p.optString("id"))));
        acts.addView(ctl, Ui.weight(1.4f));
        if (shared) {
            Button lv = Ui.button(this, "🚪 " + Ui.L("Rời máy", "Leave"), Ui.GHOST);
            lv.setOnClickListener(v -> Ui.confirm(this, Ui.L("Rời máy này?", "Leave this phone?"),
                    Ui.L("Bạn sẽ không điều khiển được máy này nữa (chủ máy có thể chia sẻ lại).", "You will lose access (the owner can share it again)."),
                    Ui.L("Rời máy", "Leave"), () -> Api.bg(() -> Api.rpc("cp_share_revoke", new JSONObject().put("p_id", p.optString("share_id"))),
                            r -> { Ui.toast(this, Ui.L("Đã rời máy.", "You left the phone.")); refresh(); }, msg -> Ui.toast(this, msg))));
            acts.addView(lv, Ui.weight(1));
            c.addView(acts, Ui.fill());
            return c;
        }
        Button rn = Ui.button(this, Ui.L("Gia hạn", "Renew"), Ui.GHOST);
        rn.setOnClickListener(v -> renew(p));
        rn.setEnabled(!lk && ("active".equals(st) || "expired".equals(st)));
        acts.addView(rn, Ui.weight(1));
        Button more = Ui.button(this, "⋯", Ui.GHOST);
        more.setOnClickListener(v -> moreMenu(p));
        acts.addView(more, Ui.wrap());
        c.addView(acts, Ui.fill());
        return c;
    }

    void renew(JSONObject p) {
        int max = price.optInt("max_days", 365);
        final int[] days = {Math.min(30, max)};
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, p.optInt("ram") + "GB · " + p.optInt("cpu") + Ui.L(" nhân · ", " cores · ") + left(parseTime(p.optString("expires_at")))));
        Ui.Wrap w = new Ui.Wrap(this, 8);
        int[] opts = {1, 3, 7, 15, 30, 60, 90};
        TextView sum = Ui.text(this, "", 14, Ui.FG, false);
        EditText x = Ui.input(this, Ui.L("Hoặc tự nhập số ngày", "Or type days"), InputType.TYPE_CLASS_NUMBER);
        Button ok = Ui.button(this, Ui.L("Gia hạn", "Renew"), Ui.PRIMARY);
        Runnable draw = () -> {
            for (int i = 0; i < w.getChildCount(); i++) Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == days[0]);
            double per = ctv(perDay(p.optInt("ram"), p.optInt("cpu"))), total = per * days[0], bal = prof.optDouble("balance", 0);
            long base = Math.max(System.currentTimeMillis(), parseTime(p.optString("expires_at")));
            sum.setText(Ui.L("Đơn giá: ", "Price: ") + Ui.vnd(per) + Ui.L(" / ngày", " / day") + (isCtv() ? " (CTV −" + prof.optInt("ctv_discount") + "%)" : "")
                    + "\n" + Ui.L("Hạn mới: ", "New expiry: ") + fdate(base + days[0] * 86400000L)
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(total));
            boolean enough = bal >= total;
            ok.setText(enough ? Ui.L("Gia hạn " + days[0] + " ngày", "Renew " + days[0] + " days") : Ui.L("Nạp thêm tiền", "Top up"));
        };
        for (int d : opts) {
            if (d > max) continue;
            TextView ch = Ui.chip(this, d + Ui.L(" ngày", "d"), false);
            ch.setTag(d);
            ch.setOnClickListener(v -> { days[0] = (int) v.getTag(); x.setText(""); draw.run(); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        c.addView(x, Ui.fill());
        x.addTextChangedListener(new Simple(() -> {
            try { int v = Integer.parseInt(x.getText().toString()); if (v >= 1 && v <= max) { days[0] = v; draw.run(); } } catch (Exception ignored) { }
        }));
        LinearLayout sb = Ui.card(this);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, Ui.L("Gia hạn ", "Renew ") + p.optString("name"), c);
        ok.setOnClickListener(v -> {
            double total = ctv(perDay(p.optInt("ram"), p.optInt("cpu"))) * days[0];
            if (prof.optDouble("balance", 0) < total) { d.dismiss(); openTopup(total - prof.optDouble("balance", 0)); return; }
            ok.setEnabled(false);
            Api.bg(() -> Api.rpc("cloudphone_renew", new JSONObject().put("p_id", p.optString("id")).put("p_days", days[0])), r -> {
                d.dismiss();
                Ui.toast(this, Ui.L("Đã gia hạn +" + days[0] + " ngày cho ", "Renewed +" + days[0] + " days: ") + p.optString("name"));
                refresh();
                h.postDelayed(this::refresh, 5000);
            }, m -> { ok.setEnabled(true); Ui.toast(this, m); });
        });
        draw.run();
        d.show();
    }

    /** Khách tự nâng RAM / CPU: trả thêm cho phần thời gian còn lại (giá do máy chủ tính, có giảm CTV). */
    void upgrade(JSONObject p) {
        final int R0 = p.optInt("ram"), C0 = p.optInt("cpu");
        final int[] ul = andLim(p.optString("android", "9").isEmpty() ? "9" : p.optString("android", "9"));
        final int maxR = ul[0], maxC = ul[1];                    // trần theo bản Android của máy
        final int[] nr = {R0}, nc = {C0};
        final long[] cost = {0};
        final boolean gpu = p.optInt("port") >= 5600;          // máy GPU / máy MEmu (Windows): đổi cấu hình phải khởi động lại
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, Ui.L("Hiện tại: ", "Now: ") + R0 + "GB RAM · " + C0 + Ui.L(" nhân · ", " cores · ") + left(parseTime(p.optString("expires_at")))));
        TextView lr = Ui.text(this, "RAM", 14, Ui.FG, true); c.addView(lr);
        Ui.Wrap wr = new Ui.Wrap(this, 8); c.addView(wr, Ui.fill());
        TextView lc = Ui.text(this, "CPU", 14, Ui.FG, true); c.addView(lc);
        Ui.Wrap wc = new Ui.Wrap(this, 8); c.addView(wc, Ui.fill());
        TextView sum = Ui.text(this, "", 14, Ui.FG, false);
        LinearLayout sb = Ui.card(this); sb.addView(sum); c.addView(sb, Ui.fill());
        c.addView(Ui.muted(this, gpu
                ? Ui.L("Máy sẽ tự khởi động lại khoảng 1 phút để nhận cấu hình mới — app và dữ liệu giữ nguyên.", "The phone restarts (~1 min) to apply — apps and data stay.")
                : Ui.L("Máy không khởi động lại, app và dữ liệu giữ nguyên — tài nguyên mới có sau khoảng 30 giây.", "No restart, apps and data stay — applies in ~30s.")));
        Button ok = Ui.button(this, Ui.L("Nâng cấp ngay", "Upgrade now"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Runnable[] draw = new Runnable[1];
        Runnable quote = () -> {
            if (nr[0] == R0 && nc[0] == C0) { cost[0] = 0; draw[0].run(); return; }
            final int qr = nr[0], qc = nc[0];
            cost[0] = localQuote(p, qr, qc); draw[0].run();
            Api.bg(() -> Api.rpc("cloudphone_upgrade_quote", new JSONObject().put("p_id", p.optString("id")).put("p_ram", qr).put("p_cpu", qc)),
                    r -> { if (qr == nr[0] && qc == nc[0]) { try { cost[0] = Long.parseLong(String.valueOf(r).replaceAll("[^0-9]", "")); } catch (Exception e) { cost[0] = localQuote(p, qr, qc); } draw[0].run(); } },
                    m -> { });
        };
        draw[0] = () -> {
            for (int i = 0; i < wr.getChildCount(); i++) Ui.setChip((TextView) wr.getChildAt(i), (int) wr.getChildAt(i).getTag() == nr[0]);
            for (int i = 0; i < wc.getChildCount(); i++) Ui.setChip((TextView) wc.getChildAt(i), (int) wc.getChildAt(i).getTag() == nc[0]);
            boolean same = nr[0] == R0 && nc[0] == C0;
            double bal = prof.optDouble("balance", 0);
            sum.setText(same ? Ui.L("Chọn RAM hoặc CPU muốn nâng.", "Pick more RAM or CPU.")
                    : Ui.L("Cấu hình mới: ", "New: ") + nr[0] + "GB · " + nc[0] + Ui.L(" nhân", " cores")
                    + "\n" + Ui.L("Trả thêm cho thời gian còn lại: ", "Pay for the remaining time: ") + Ui.vnd(cost[0])
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal));
            ok.setEnabled(!same);
            ok.setText(!same && bal < cost[0] ? Ui.L("Nạp thêm tiền", "Top up") : Ui.L("Nâng cấp ngay", "Upgrade now"));
        };
        int[] rams = {2, 3, 4, 6, 8, 10, 12, 16}, cpus = {2, 3, 4, 6, 8, 10, 12, 16};
        java.util.TreeSet<Integer> rs = new java.util.TreeSet<>(), cs = new java.util.TreeSet<>();
        rs.add(R0); for (int v : rams) if (v > R0 && v <= maxR) rs.add(v); if (maxR > R0) rs.add(maxR);
        cs.add(C0); for (int v : cpus) if (v > C0 && v <= maxC) cs.add(v); if (maxC > C0) cs.add(maxC);
        for (int v : rs) { TextView ch = Ui.chip(this, (v == R0 ? Ui.L("Giữ ", "Keep ") : "") + v + "GB", false); ch.setTag(v);
            ch.setOnClickListener(x -> { nr[0] = (int) x.getTag(); draw[0].run(); quote.run(); }); wr.addView(ch); }
        for (int v : cs) { TextView ch = Ui.chip(this, (v == C0 ? Ui.L("Giữ ", "Keep ") : "") + v + Ui.L(" nhân", " cores"), false); ch.setTag(v);
            ch.setOnClickListener(x -> { nc[0] = (int) x.getTag(); draw[0].run(); quote.run(); }); wc.addView(ch); }
        Dialog d = Ui.sheet(this, "⬆️ " + Ui.L("Nâng cấp ", "Upgrade ") + p.optString("name"), c);
        ok.setOnClickListener(v -> {
            if (prof.optDouble("balance", 0) < cost[0]) { d.dismiss(); openTopup(cost[0] - prof.optDouble("balance", 0)); return; }
            ok.setEnabled(false);
            Api.bg(() -> Api.rpc("cloudphone_upgrade", new JSONObject().put("p_id", p.optString("id")).put("p_ram", nr[0]).put("p_cpu", nc[0])), r -> {
                d.dismiss();
                Ui.toast(this, Ui.L("Đã nâng lên " + nr[0] + "GB · " + nc[0] + " nhân — máy nhận cấu hình mới trong giây lát.", "Upgraded to " + nr[0] + "GB · " + nc[0] + " cores."));
                refresh(); h.postDelayed(this::refresh, 5000);
            }, m -> {
                ok.setEnabled(true);
                Ui.toast(this, m.contains("UPGRADE_PENDING") ? Ui.L("Máy đang nâng cấp, đợi chút rồi thử lại.", "An upgrade is already in progress.")
                        : m.contains("FREE_NO_UPGRADE") ? Ui.L("Máy miễn phí không nâng cấp được.", "Free phones can't be upgraded.")
                        : m.contains("PHONE_NOT_ACTIVE") ? Ui.L("Máy phải đang chạy mới nâng cấp được.", "The phone must be running.") : m);
            });
        });
        draw[0].run();
        d.show();
    }

    /** Giá nâng cấp dự tính giống web (máy chủ tính lại chính xác lúc trừ tiền). */
    long localQuote(JSONObject p, int nr, int nc) {
        double left = Math.max(0, (parseTime(p.optString("expires_at")) - System.currentTimeMillis()) / 86400000.0);
        double raw = Math.round(((nr - p.optInt("ram")) * price.optDouble("price_ram_gb_day", 2500) + (nc - p.optInt("cpu")) * price.optDouble("price_cpu_day", 2000)) * left);
        double pct = isCtv() ? prof.optDouble("ctv_discount", 0) : 0;
        return (long) Math.ceil(raw * (100 - pct) / 100);
    }

    /** Huỷ máy: xoá máy + toàn bộ dữ liệu, không hoàn tiền (giống web). */
    void cancelPhone(JSONObject p) {
        Ui.confirm(this, Ui.L("Huỷ máy ", "Delete ") + p.optString("name") + "?",
                Ui.L("Máy và TOÀN BỘ dữ liệu trong máy sẽ bị XOÁ vĩnh viễn, không hoàn tiền.", "The phone and ALL its data will be permanently deleted. No refund."),
                Ui.L("Xoá máy", "Delete"), () -> Api.bg(() -> Api.rpc("cloudphone_cancel", new JSONObject().put("p_id", p.optString("id"))),
                        r -> { Ui.toast(this, Ui.L("Đang huỷ máy — máy sẽ biến mất khỏi danh sách trong ít phút.", "Deleting — it will disappear shortly.")); refresh(); },
                        m -> Ui.toast(this, m)));
    }

    void moreMenu(JSONObject p) {
        LinearLayout c = Ui.col(this, 10);
        Button sh = Ui.button(this, "👥 " + Ui.L("Chia sẻ / chuyển nhượng", "Share / transfer"), Ui.GHOST);
        Button rn = Ui.button(this, "✏️ " + Ui.L("Đổi tên", "Rename"), Ui.GHOST);
        Button up = Ui.button(this, "⬆️ " + Ui.L("Nâng cấp RAM / CPU", "Upgrade RAM / CPU"), Ui.GHOST);
        boolean canUp = "active".equals(p.optString("status")) && !locked(p) && !p.optBoolean("is_free") && !p.optBoolean("shared");
        up.setEnabled(canUp); up.setAlpha(canUp ? 1f : .45f);
        boolean canShare = ("active".equals(p.optString("status")) || "pending".equals(p.optString("status"))) && !locked(p);
        sh.setEnabled(canShare); sh.setAlpha(canShare ? 1f : .45f);
        Button del = Ui.button(this, "🗑 " + Ui.L("Huỷ máy (xoá vĩnh viễn)", "Delete phone"), Ui.DANGER);
        c.addView(up, Ui.fill()); c.addView(sh, Ui.fill()); c.addView(rn, Ui.fill()); c.addView(del, Ui.fill());
        Dialog d = Ui.sheet(this, p.optString("name"), c);
        del.setOnClickListener(v -> { d.dismiss(); cancelPhone(p); });
        up.setOnClickListener(v -> { d.dismiss(); upgrade(p); });
        sh.setOnClickListener(v -> { d.dismiss(); share(p); });
        rn.setOnClickListener(v -> { d.dismiss(); rename(p); });
        d.show();
    }

    void claim(EditText code, Button b) {
        String s = code.getText().toString().toUpperCase(Locale.US).replaceAll("[^A-Z0-9]", "");
        if (s.length() < 4) { Ui.toast(this, Ui.L("Nhập mã tặng máy (12 ký tự) hoặc mã chia sẻ / chuyển nhượng (8 ký tự).", "Enter a gift code (12 characters) or a share / transfer code (8 characters).")); return; }
        b.setEnabled(false);
        if (s.length() != 8) {        // MÃ TẶNG MÁY (SQL v23 — luôn ≥ 10 ký tự): nhận 1 máy miễn phí đúng cấu hình admin đặt
            Api.bg(() -> Api.rpc("promo_redeem_gift", new JSONObject().put("p_code", s)), r -> {
                b.setEnabled(true);
                JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                if (!o.optBoolean("ok")) {
                    String e = o.optString("err", "PROMO_INVALID");
                    boolean keep = e.equals("SERVER_OFFLINE") || e.equals("MAINTENANCE") || e.equals("OUT_OF_CAPACITY") || e.equals("OUT_OF_STOCK") || e.equals("MAX_PER_USER") || e.equals("BAD_ANDROID");
                    Ui.toast(this, Api.friendly(new Exception(e)) + (keep ? Ui.L(" Mã của bạn vẫn còn nguyên — thử lại sau.", " Your code is still valid — try again later.") : ""));
                    return;
                }
                code.setText("");
                Ui.toast(this, Ui.L("🎁 Nhận máy tặng thành công — máy đang được tạo (Android " + o.optString("android") + " · " + o.optInt("ram") + "GB · " + o.optInt("cpu") + " nhân · " + o.optInt("days") + " ngày).",
                        "🎁 Gift phone claimed — it's being created (Android " + o.optString("android") + " · " + o.optInt("ram") + "GB · " + o.optInt("cpu") + " cores · " + o.optInt("days") + " days)."));
                phonesSig = null;
                refresh();
            }, msg -> { b.setEnabled(true); Ui.toast(this, msg); });
            return;
        }
        Api.bg(() -> Api.rpc("cp_share_claim", new JSONObject().put("p_code", s)), r -> {
            b.setEnabled(true);
            code.setText("");
            JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
            Ui.toast(this, "transfer".equals(o.optString("kind")) ? Ui.L("🎉 Máy \"" + o.optString("name") + "\" giờ là của bạn!", "🎉 \"" + o.optString("name") + "\" is now yours!")
                    : Ui.L("✓ Đã thêm máy \"" + o.optString("name") + "\" được chia sẻ cho bạn.", "✓ \"" + o.optString("name") + "\" was shared with you."));
            refresh();
        }, msg -> { b.setEnabled(true); Ui.toast(this, msg); });
    }

    private void copyCode(String code) {
        android.content.ClipboardManager cm = (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (cm != null) cm.setPrimaryClip(android.content.ClipData.newPlainText("code", code));
        Ui.toast(this, Ui.L("Đã copy mã: ", "Copied: ") + code);
    }

    private View codeBox(String code, String note) {
        LinearLayout b = Ui.card(this);
        LinearLayout r = Ui.row(this, 10);
        TextView t = Ui.text(this, code, 24, Ui.FG, true);
        t.setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD);
        t.setLetterSpacing(.15f);
        r.addView(t, Ui.weight(1));
        Button cp = Ui.button(this, "📋 Copy", Ui.PRIMARY);
        cp.setOnClickListener(v -> copyCode(code));
        r.addView(cp, Ui.wrap());
        b.addView(r, Ui.fill());
        b.addView(Ui.muted(this, note), Ui.fill());
        return b;
    }

    void share(JSONObject p) {
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.h2(this, Ui.L("Chia sẻ dùng chung", "Share access")));
        c.addView(Ui.muted(this, Ui.L("Người nhập mã được điều khiển máy như bạn (không gia hạn, huỷ hay chia sẻ tiếp được). Mỗi mã cho 1 người, thu hồi lúc nào cũng được.",
                "Whoever enters the code can control this phone like you (not renew, cancel or re-share). One code per person; revoke any time.")));
        final int[] days = {7};
        Ui.Wrap w = new Ui.Wrap(this, 8);
        int[] opts = {1, 3, 7, 30, 0};
        for (int d : opts) {
            TextView ch = Ui.chip(this, d == 0 ? Ui.L("♾ Vĩnh viễn", "♾ Permanent") : d + Ui.L(" ngày", "d"), d == days[0]);
            ch.setTag(d);
            ch.setOnClickListener(v -> { days[0] = (int) v.getTag(); for (int i = 0; i < w.getChildCount(); i++) Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == days[0]); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        c.addView(Ui.muted(this, Ui.L("♾ Vĩnh viễn: mã không tự hết hạn — người nhận dùng tới khi bạn thu hồi hoặc bấm TẮT CHIA SẺ (hoặc máy hết hạn).",
                "♾ Permanent: the code never expires — they keep access until you revoke it or press TURN OFF SHARING (or the phone expires).")), Ui.fill());
        Button mk = Ui.button(this, Ui.L("Tạo mã chia sẻ", "Create share code"), Ui.PRIMARY);
        c.addView(mk, Ui.fill());
        LinearLayout newBox = Ui.col(this, 8), list = Ui.col(this, 8);
        c.addView(newBox, Ui.fill()); c.addView(list, Ui.fill());
        // TẮT CHIA SẺ: thu hồi MỌI chia sẻ + mọi mã chưa ai nhập (người dùng chung mất quyền NGAY) — SQL v23
        Button stop = Ui.button(this, "⛔ " + Ui.L("TẮT CHIA SẺ", "TURN OFF SHARING"), Ui.DANGER);
        stop.setVisibility(View.GONE);
        c.addView(stop, Ui.fill());

        c.addView(Ui.h2(this, Ui.L("Chuyển nhượng máy", "Transfer ownership")));
        c.addView(Ui.muted(this, Ui.L("Người nhập mã thành chủ mới của máy (giữ nguyên hạn còn lại và dữ liệu). Bạn sẽ mất máy này, mọi chia sẻ cũ bị huỷ.",
                "Whoever enters the code becomes the new owner (time left and data are kept). You lose this phone; all shares are cancelled.")));
        Button tr = Ui.button(this, Ui.L("Tạo mã chuyển nhượng", "Create transfer code"), Ui.DANGER);
        c.addView(tr, Ui.fill());
        LinearLayout trBox = Ui.col(this, 8);
        c.addView(trBox, Ui.fill());

        Runnable[] load = new Runnable[1];
        load[0] = () -> Api.bg(() -> Api.rpc("cp_share_list", new JSONObject().put("p_phone", p.optString("id"))), r -> {
            list.removeAllViews();
            JSONArray a = r instanceof JSONArray ? (JSONArray) r : new JSONArray();
            stop.setVisibility(a.length() > 0 ? View.VISIBLE : View.GONE);
            if (a.length() > 0) list.addView(Ui.muted(this, Ui.L("Mã đang hoạt động (", "Active codes (") + a.length() + ")"));
            for (int i = 0; i < a.length(); i++) {
                JSONObject s = a.optJSONObject(i);
                LinearLayout row = Ui.row(this, 8);
                long se = parseTime(s.optString("expires_at", ""));
                String u = s.optString("user", ""); boolean used = !u.isEmpty() && !u.equals("null");
                row.addView(Ui.text(this, s.optString("code") + "\n" + (used ? "👤 " + u : Ui.L("Chưa ai dùng", "Not used yet"))
                        + (se > 0 ? Ui.L(" · đến ", " · until ") + fdate(se) : Ui.L(" · ♾ vĩnh viễn", " · ♾ permanent")), 13, Ui.FG, false), Ui.weight(1));
                Button rv = Ui.button(this, used ? Ui.L("Thu hồi", "Revoke") : Ui.L("Huỷ mã", "Cancel"), Ui.DANGER);
                rv.setOnClickListener(v -> Api.bg(() -> Api.rpc("cp_share_revoke", new JSONObject().put("p_id", s.optString("id"))),
                        x -> { Ui.toast(this, Ui.L("Đã thu hồi.", "Revoked.")); load[0].run(); }, msg -> Ui.toast(this, msg)));
                row.addView(rv, Ui.wrap());
                list.addView(row, Ui.fill());
            }
        }, msg -> { list.removeAllViews(); list.addView(Ui.text(this, msg, 13, Ui.BAD, false)); });
        stop.setOnClickListener(v -> Ui.confirm(this, Ui.L("TẮT CHIA SẺ?", "Turn off sharing?"),
                Ui.L("Mọi người đang dùng chung máy \"" + p.optString("name") + "\" sẽ MẤT QUYỀN ngay, mọi mã chưa ai nhập (kể cả mã chuyển nhượng đang chờ) bị huỷ.",
                        "Everyone sharing \"" + p.optString("name") + "\" loses access immediately; all unused codes (including a pending transfer code) are cancelled."),
                Ui.L("Tắt chia sẻ", "Turn off"), () -> {
                    stop.setEnabled(false);
                    Api.bg(() -> Api.rpc("cp_share_stop", new JSONObject().put("p_phone", p.optString("id"))), r -> {
                        stop.setEnabled(true);
                        int n = r instanceof JSONObject ? ((JSONObject) r).optInt("revoked") : 0;
                        newBox.removeAllViews(); trBox.removeAllViews();
                        Ui.toast(this, n > 0 ? Ui.L("⛔ Đã tắt chia sẻ — thu hồi " + n + " lượt chia sẻ / mã.", "⛔ Sharing turned off — " + n + " revoked.")
                                : Ui.L("Máy này không còn chia sẻ cho ai.", "Nothing to revoke."));
                        load[0].run();
                    }, msg -> { stop.setEnabled(true); Ui.toast(this, msg); });
                }));

        mk.setOnClickListener(v -> {
            mk.setEnabled(false);
            Api.bg(() -> Api.rpc("cp_share_create", new JSONObject().put("p_phone", p.optString("id")).put("p_kind", "share").put("p_days", days[0] == 0 ? JSONObject.NULL : days[0])), r -> {
                mk.setEnabled(true);
                String code = r instanceof JSONObject ? ((JSONObject) r).optString("code") : "";
                newBox.removeAllViews();
                newBox.addView(codeBox(code, Ui.L("Gửi mã cho người cần dùng. Họ vào app hoặc " + Api.webHost() + " → ĐT đám mây → nhập mã.",
                        "Send this code. They open the app or " + Api.webHost() + " → Cloud phones → enter the code.")), Ui.fill());
                load[0].run();
            }, msg -> { mk.setEnabled(true); Ui.toast(this, msg); });
        });
        tr.setOnClickListener(v -> Ui.confirm(this, Ui.L("Tạo mã chuyển nhượng?", "Create transfer code?"),
                Ui.L("Ai nhập mã này sẽ thành chủ máy \"" + p.optString("name") + "\", bạn mất máy. Mã chuyển nhượng cũ (nếu có) bị huỷ.",
                        "Whoever enters it becomes the owner of \"" + p.optString("name") + "\". Any older transfer code is cancelled."),
                Ui.L("Tạo mã", "Create"), () -> Api.bg(() -> Api.rpc("cp_share_create", new JSONObject().put("p_phone", p.optString("id")).put("p_kind", "transfer").put("p_days", JSONObject.NULL)), r -> {
                    String code = r instanceof JSONObject ? ((JSONObject) r).optString("code") : "";
                    trBox.removeAllViews();
                    trBox.addView(codeBox(code, Ui.L("Chỉ đưa mã sau khi đã nhận tiền. Muốn huỷ: tạo mã chuyển nhượng mới (mã cũ mất hiệu lực).",
                            "Only hand this over after you've been paid. To cancel, create a new transfer code.")), Ui.fill());
                }, msg -> Ui.toast(this, msg))));
        Dialog d = Ui.sheet(this, "👥 " + p.optString("name"), c);
        d.setOnDismissListener(x -> refresh());
        load[0].run();
        d.show();
    }

    void rename(JSONObject p) {
        LinearLayout c = Ui.col(this, 12);
        EditText n = Ui.input(this, Ui.L("Tên máy", "Phone name"), InputType.TYPE_CLASS_TEXT);
        n.setText(p.optString("name"));
        c.addView(n, Ui.fill());
        Button ok = Ui.button(this, Ui.L("Lưu tên", "Save"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, Ui.L("Đổi tên máy", "Rename phone"), c);
        ok.setOnClickListener(v -> {
            String s = n.getText().toString().trim();
            if (s.isEmpty()) return;
            Api.bg(() -> Api.rpc("cloudphone_rename", new JSONObject().put("p_id", p.optString("id")).put("p_name", s)),
                    r -> { d.dismiss(); refresh(); }, m -> Ui.toast(this, m));
        });
        d.show();
    }

    // ---------------- TAB 2: Thuê máy ----------------
    void renderRent() {
        LinearLayout body = Ui.col(this, 14);
        body.addView(Ui.h1(this, Ui.L("Thuê điện thoại đám mây", "Rent a cloud phone")), Ui.fill());
        if (isAdmin() && status.optBoolean("maint", false))
            body.addView(Ui.text(this, Ui.L("⚠ Đang bật BẢO TRÌ — khách không thuê được. Tài khoản admin vẫn thuê được để thử máy.",
                    "⚠ Maintenance is ON — customers can't rent. Admin can still rent to test."), 13, Ui.WAIT, true), Ui.fill());
        body.addView(Ui.muted(this, Ui.L("Chọn gợi ý bên dưới là xong — hoặc tự chỉnh RAM, CPU, số ngày. Máy mới tinh, có Play Store.",
                "Pick a preset below — or set RAM, CPU and days yourself. Fresh device with Play Store.")), Ui.fill());

        int minR = price.optInt("min_ram", 1), minC = price.optInt("min_cpu", 1);
        final int mpu = maxPerUser(), left = mpu > 0 ? mpu - myLive() : 20;
        if (mpu > 0 && left <= 0) {            // đã đủ số máy cho phép → không cho thuê thêm
            LinearLayout full = Ui.card(this);
            full.addView(Ui.text(this, Ui.L("Bạn đã có đủ " + mpu + " máy", "You already have " + mpu + " phone(s)"), 17, Ui.FG, true));
            full.addView(Ui.muted(this, Ui.L("Mỗi tài khoản chỉ được thuê tối đa " + mpu + " máy. Gia hạn máy đang có, hoặc xoá máy cũ để thuê máy khác.",
                    "Each account can rent up to " + mpu + " phone(s). Renew your phone, or delete it to rent another.")));
            Button go = Ui.button(this, Ui.L("Xem máy của tôi", "My phones"), Ui.PRIMARY);
            go.setOnClickListener(v -> show(0));
            full.addView(go, Ui.fill());
            body.addView(full, Ui.fill());
            page(body);
            return;
        }
        if (left <= 1) sQty = 1;
        java.util.List<String> avs = andList();
        if (!freeLive()) sFree = false;
        int minD = price.optInt("min_days", 1), maxD = price.optInt("max_days", 90), minF = price.optInt("min_fps", 10), maxF = price.optInt("max_fps", 120);
        if (!avs.contains(sAnd) || !andWhy(sAnd).isEmpty()) sAnd = andPick();
        final int[] lim = andLim(sAnd);
        final int maxR = lim[0], maxC = lim[1];                  // trần theo bản Android đang chọn (Android 9: 8GB · 8 nhân · Android 12 / 7: 16GB · 16 nhân)
        sRam = clamp(sRam, minR, maxR); sCpu = clamp(sCpu, minC, maxC); sDays = clamp(sDays, minD, maxD); sFps = clamp(sFps, minF, maxF);
        final Ui.Wrap aw = new Ui.Wrap(this, 8);

        TextView total = Ui.text(this, "", 22, Ui.SKY, true);
        TextView calc = Ui.text(this, "", 11.5f, Ui.MUTED, false);
        calc.setMaxLines(2);
        TextView err = Ui.text(this, "", 12.5f, Ui.BAD, false);
        Button buy = Ui.button(this, "", Ui.PRIMARY);

        Runnable upd = () -> {
            paintAnd(aw);
            double t = sFree ? 0 : ctv(perDay(sRam, sCpu) * sDays) * sQty, bal = prof.optDouble("balance", 0);
            total.setText(Ui.vnd(t));
            calc.setText("(" + sRam + "GB × " + Ui.vnd(price.optDouble("price_ram_gb_day", 2500)) + " + " + sCpu + Ui.L(" nhân × ", " cores × ")
                    + Ui.vnd(price.optDouble("price_cpu_day", 2000)) + ") × " + sDays + Ui.L(" ngày", " days")
                    + (isCtv() ? " − " + prof.optInt("ctv_discount") + "% CTV" : "") + (sQty > 1 ? " × " + sQty + Ui.L(" máy", " phones") : "")
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal));
            String bad = check();
            err.setText(bad.isEmpty() && bal < t ? Ui.L("Số dư không đủ — cần nạp thêm ", "Not enough balance — top up ") + Ui.vnd(t - bal) : bad);
            if (sFree) calc.setText(Ui.L("🎁 Miễn phí " + price.optInt("free_days", 1) + " ngày", "🎁 Free for " + price.optInt("free_days", 1) + " day(s)") + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal));
            buy.setText(sFree ? Ui.L("🎁 Nhận máy miễn phí", "🎁 Get free phone") : bad.isEmpty() && bal < t ? Ui.L("Nạp tiền", "Top up") : Ui.L("Thuê ngay", "Rent now") + (sQty > 1 ? " " + sQty + Ui.L(" máy", " phones") : ""));
            buy.setEnabled(bad.isEmpty());
            buy.setAlpha(bad.isEmpty() ? 1f : .5f);
            err.setVisibility(err.getText().length() == 0 ? View.GONE : View.VISIBLE);
        };

        // 🎁 Miễn phí ưu đãi (khi admin bật)
        if (freeLive()) {
            LinearLayout fc = Ui.card(this);
            TextView fch = Ui.chip(this, Ui.L("🎁 Nhận máy MIỄN PHÍ " + price.optInt("free_days", 1) + " ngày", "🎁 Get a FREE phone for " + price.optInt("free_days", 1) + " day(s)"), sFree);
            fc.addView(fch, Ui.fill());
            fc.addView(Ui.muted(this, Ui.L("Tối đa " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " nhân · mỗi tài khoản dùng thử 1 máy. Bấm lần nữa để tắt nếu muốn thuê trả phí.",
                    "Up to " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " cores · one free trial per account. Tap again to rent a paid phone instead.")));
            fch.setOnClickListener(v -> { sFree = !sFree; if (sFree) { sQty = 1; sRam = Math.min(sRam, price.optInt("free_max_ram", 4)); sCpu = Math.min(sCpu, price.optInt("free_max_cpu", 4)); } renderRent(); });
            body.addView(fc, Ui.fill());
        }
        // Gợi ý cấu hình — bấm 1 lần là điền RAM + CPU
        if (!sFree) {
            LinearLayout pc = Ui.card(this);
            pc.addView(Ui.text(this, Ui.L("💡 Gợi ý cấu hình — bấm để chọn nhanh", "💡 Presets — tap to fill"), 14, Ui.MUTED, true));
            Ui.Wrap pw = new Ui.Wrap(this, 8);
            String[][] PRE = {{"💬", Ui.L("Treo app", "Idle apps"), "2", "2"}, {"🎮", Ui.L("Game nhẹ", "Light games"), "4", "2"},
                    {"🕹️", Ui.L("Game 3D", "3D games"), "4", "4"}, {"🔥", Ui.L("Game nặng", "Heavy games"), "8", "8"}};
            for (String[] pr : PRE) {
                final int pr0 = clamp(Integer.parseInt(pr[2]), minR, maxR), pc0 = clamp(Integer.parseInt(pr[3]), minC, maxC);
                TextView ch = Ui.chip(this, pr[0] + " " + pr[1] + "\n" + pr0 + "GB · " + pc0 + Ui.L(" nhân", " cores"), sRam == pr0 && sCpu == pc0);
                ch.setTextSize(13);
                ch.setOnClickListener(v -> { sRam = pr0; sCpu = pc0; renderRent(); });
                pw.addView(ch);
            }
            pc.addView(pw, Ui.fill());
            body.addView(pc, Ui.fill());
        }
        // Phiên bản Android
        LinearLayout ac = Ui.col(this, 8);
        ac.addView(Ui.text(this, Ui.L("Hệ điều hành", "Operating system"), 14, Ui.MUTED, true));
        for (String v : avs) {
            TextView ch = Ui.chip(this, "Android " + v + "\n" + andHint(v), v.equals(sAnd));
            ch.setTextSize(13);
            ch.setTag(v);
            ch.setOnClickListener(x -> {
                if (!andWhy((String) x.getTag()).isEmpty()) return;      // bản đang bảo trì / hết chỗ
                String nv = (String) x.getTag();
                int[] a0 = andLim(sAnd), a1 = andLim(nv);
                sAnd = nv;
                if (a0[0] != a1[0] || a0[1] != a1[1]) { sRam = Math.min(sRam, a1[0]); sCpu = Math.min(sCpu, a1[1]); renderRent(); }   // trần khác → vẽ lại danh sách RAM/CPU
                else upd.run();
            });
            aw.addView(ch);
        }
        ac.addView(aw, Ui.fill());
        body.addView(boxed(ac), Ui.fill());

        body.addView(boxed(group(Ui.L("RAM", "RAM"), RAM, minR, maxR, "GB", v -> { sRam = v; upd.run(); }, () -> sRam)), Ui.fill());
        body.addView(boxed(group(Ui.L("CPU (nhân)", "CPU cores"), CPU, minC, maxC, "", v -> { sCpu = v; upd.run(); }, () -> sCpu)), Ui.fill());
        if (!sFree) body.addView(boxed(group(Ui.L("Số ngày", "Days"), DAYS, minD, maxD, Ui.L(" ngày", "d"), v -> { sDays = v; upd.run(); }, () -> sDays)), Ui.fill());
        if (!sFree && left > 1) body.addView(boxed(group(Ui.L("Số lượng máy", "Quantity"), QTY, 1, Math.min(20, left), Ui.L(" máy", ""), v -> { sQty = v; upd.run(); }, () -> sQty)), Ui.fill());
        body.addView(boxed(group("FPS", FPS, minF, maxF, "", v -> { sFps = v; upd.run(); }, () -> sFps)), Ui.fill());

        // Độ phân giải
        LinearLayout rc = Ui.col(this, 8);
        rc.addView(Ui.text(this, Ui.L("Độ phân giải", "Resolution"), 14, Ui.MUTED, true));
        Ui.Wrap rw = new Ui.Wrap(this, 8);
        for (String[] r : RES) {
            TextView ch = Ui.chip(this, Ui.L(r[1], r[0]) + "\n" + r[0], r[0].equals(sRes));
            ch.setTextSize(13);
            ch.setTag(r[0]);
            ch.setOnClickListener(v -> {
                sRes = (String) v.getTag();
                for (int i = 0; i < rw.getChildCount(); i++) Ui.setChip((TextView) rw.getChildAt(i), rw.getChildAt(i).getTag().equals(sRes));
                upd.run();
            });
            rw.addView(ch);
        }
        rc.addView(rw, Ui.fill());
        body.addView(boxed(rc), Ui.fill());

        // Thanh thanh toán ghim dưới màn hình: luôn thấy tổng tiền + nút Thuê ngay
        LinearLayout sum = Ui.col(this, 6);
        sum.setPadding(Ui.dp(14), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        sum.setBackground(Ui.ringed(Ui.PANEL, 20));
        sum.setElevation(Ui.dp(8));
        sum.addView(err, Ui.fill());
        LinearLayout sr = Ui.row(this, 10);
        LinearLayout st = Ui.col(this, 0);
        st.addView(Ui.text(this, Ui.L("Tổng thanh toán", "Total"), 12, Ui.MUTED, false));
        st.addView(total);
        st.addView(calc);
        sr.addView(st, Ui.weight(1));
        buy.setMinWidth(Ui.dp(132));
        sr.addView(buy, Ui.wrap());
        sum.addView(sr, Ui.fill());

        buy.setOnClickListener(v -> {
            double t = sFree ? 0 : ctv(perDay(sRam, sCpu) * sDays) * sQty;
            if (prof.optDouble("balance", 0) < t) { openTopup(t - prof.optDouble("balance", 0)); return; }
            Ui.confirm(this, Ui.L("Xác nhận thuê máy", "Confirm"),
                    "Android " + sAnd + " · " + sQty + Ui.L(" máy · ", " phone(s) · ") + sRam + "GB · " + sCpu + Ui.L(" nhân · ", " cores · ") + sDays + Ui.L(" ngày · ", " days · ") + sRes + " · " + sFps + " FPS\n"
                            + Ui.L("Trừ ", "Charge ") + Ui.vnd(t) + Ui.L(" từ số dư.", " from balance."),
                    Ui.L("Thanh toán", "Pay"), () -> order(buy));
        });
        upd.run();
        body.setTag("rent");
        page(body);
        body.setPadding(body.getPaddingLeft(), body.getPaddingTop(), body.getPaddingRight(), Ui.dp(150));
        FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        blp.setMargins(Ui.dp(10), 0, Ui.dp(10), Ui.dp(8));
        content.addView(sum, blp);
    }

    /** Bọc 1 nhóm lựa chọn vào thẻ viền neon cho gọn mắt. */
    private View boxed(View v) {
        LinearLayout c = Ui.card(this);
        c.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(14));
        c.addView(v, Ui.fill());
        return c;
    }

    private void order(Button buy) {
        buy.setEnabled(false);
        Api.bg(() -> Api.rpc("cloudphone_order_custom", new JSONObject().put("p_ram", sRam).put("p_cpu", sCpu).put("p_days", sDays)
                .put("p_res", sRes).put("p_name", JSONObject.NULL).put("p_fps", sFps).put("p_qty", sFree ? 1 : sQty)
                .put("p_android", sAnd.isEmpty() ? "9" : sAnd).put("p_free", sFree)), r -> {
            Ui.toast(this, Ui.L("Đã đặt máy! Máy đang khởi tạo, khoảng 2–3 phút.", "Ordered! Your phone is being created (2–3 min)."));
            show(0);
            refresh();
        }, m -> { buy.setEnabled(true); Ui.toast(this, m); });
    }

    String check() {
        if (status.optBoolean("maint", false) && !isAdmin()) return Ui.L("Hệ thống đang bảo trì, vui lòng quay lại sau.", "Under maintenance, please come back later.");
        if (status.has("online") && !status.optBoolean("online", true) && !isAdmin()) return Ui.L("Máy chủ đang tạm ngưng.", "Server is offline.");
        if (sFree && !isAdmin() && (sRam > price.optInt("free_max_ram", 4) || sCpu > price.optInt("free_max_cpu", 4)))
            return Ui.L("Máy miễn phí tối đa " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " nhân — chọn nhỏ hơn.",
                    "Free phones are limited to " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " cores.");
        if (!andList().contains(sAnd)) return Ui.L("Hãy chọn hệ điều hành (bản Android).", "Choose an Android version.");
        int[] al = andLim(sAnd);
        if (sRam > al[0] || sCpu > al[1])
            return Ui.L("Android " + sAnd + " tối đa " + al[0] + "GB RAM · " + al[1] + " nhân mỗi máy.", "Android " + sAnd + " allows up to " + al[0] + "GB RAM · " + al[1] + " cores per phone.");
        JSONObject am = isAdmin() ? null : status.optJSONObject("android");
        if (am != null) {
            JSONObject a = am.optJSONObject(sAnd);
            if (a == null || !a.optBoolean("online", true))
                return Ui.L("Máy chủ Android " + sAnd + " đang bảo trì — chọn bản khác.", "The Android " + sAnd + " server is under maintenance — pick another version.");
            int q = sFree ? 1 : sQty;
            if (sRam * q > a.optDouble("free_ram", 0) || sCpu * q > a.optDouble("free_cpu", 0))
                return Ui.L("Máy chủ Android " + sAnd + " chỉ còn trống " + (int) a.optDouble("free_ram", 0) + "GB RAM · " + (int) a.optDouble("free_cpu", 0) + " nhân — chọn cấu hình nhỏ hơn hoặc bản Android khác.",
                        "The Android " + sAnd + " server only has " + (int) a.optDouble("free_ram", 0) + "GB RAM · " + (int) a.optDouble("free_cpu", 0) + " cores free.");
            return "";
        }
        if (!isAdmin() && status.has("free_ram") && (sRam * sQty > status.optDouble("free_ram") || sCpu * sQty > status.optDouble("free_cpu")))
            return Ui.L("Máy chủ chỉ còn trống " + (int) status.optDouble("free_ram") + "GB RAM, " + (int) status.optDouble("free_cpu") + " nhân — chọn ít hơn.",
                    "Server only has " + (int) status.optDouble("free_ram") + "GB RAM, " + (int) status.optDouble("free_cpu") + " cores free.");
        return "";
    }

    static int clamp(int v, int lo, int hi) { return Math.max(lo, Math.min(hi, v)); }

    interface IntSet { void set(int v); }
    interface IntGet { int get(); }

    private View group(String title, int[] vals, int min, int max, String suf, IntSet set, IntGet get) {
        LinearLayout g = Ui.col(this, 8);
        LinearLayout hr = Ui.row(this, 8);
        hr.addView(Ui.text(this, title, 14, Ui.MUTED, true), Ui.weight(1));
        hr.addView(Ui.text(this, min + "–" + max, 12, Ui.MUTED, false), Ui.wrap());
        g.addView(hr, Ui.fill());
        Ui.Wrap w = new Ui.Wrap(this, 8);
        EditText x = Ui.input(this, Ui.L("Khác", "Other"), InputType.TYPE_CLASS_NUMBER);
        x.setMinWidth(Ui.dp(80));
        x.setPadding(Ui.dp(12), Ui.dp(8), Ui.dp(12), Ui.dp(8));
        for (int v : vals) {
            if (v < min || v > max) continue;
            TextView ch = Ui.chip(this, v + suf, v == get.get());
            ch.setTag(v);
            ch.setOnClickListener(c -> {
                set.set((int) c.getTag());
                x.setText("");
                for (int i = 0; i < w.getChildCount(); i++) if (w.getChildAt(i) instanceof TextView && w.getChildAt(i).getTag() != null)
                    Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == get.get());
            });
            w.addView(ch);
        }
        w.addView(x);
        x.addTextChangedListener(new Simple(() -> {
            try {
                int v = Integer.parseInt(x.getText().toString());
                if (v >= min && v <= max) {
                    set.set(v);
                    for (int i = 0; i < w.getChildCount(); i++) if (!(w.getChildAt(i) instanceof EditText) && w.getChildAt(i).getTag() != null)
                        Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == v);
                }
            } catch (Exception ignored) { }
        }));
        g.addView(w, Ui.fill());
        return g;
    }

    // ---------------- TAB 3: Tài khoản ----------------
    void renderAccount() {
        LinearLayout body = Ui.col(this, 14);
        LinearLayout c = Ui.card(this);
        String name = prof.optString("username", "");
        c.addView(Ui.h1(this, "👤 " + (name.isEmpty() || name.equals("null") ? Ui.L("Tài khoản", "Account") : name)));
        c.addView(Ui.muted(this, Api.email));
        c.addView(Ui.text(this, Ui.L("Số dư: ", "Balance: ") + Ui.vnd(prof.optDouble("balance", 0)), 18, Ui.SKY, true));
        if (isCtv()) c.addView(Ui.pill(this, "🤝 CTV −" + prof.optInt("ctv_discount") + "%", Ui.OK), Ui.wrap());
        Button top = Ui.button(this, "💳 " + Ui.L("Nạp tiền", "Top up"), Ui.PRIMARY);
        top.setOnClickListener(v -> openTopup());
        c.addView(top, Ui.fill());
        body.addView(c, Ui.fill());

        LinearLayout s = Ui.card(this);
        s.addView(Ui.h2(this, Ui.L("Cài đặt", "Settings")));
        TextView nt = Ui.text(this, "", 15, Ui.FG, false);
        Runnable ntDraw = () -> nt.setText((ExpiryAlarm.enabled(this) ? "🔔 " : "🔕 ") + Ui.L("Nhắc khi máy sắp hết hạn: ", "Expiry reminders: ")
                + (ExpiryAlarm.enabled(this) ? Ui.L("Bật", "On") : Ui.L("Tắt", "Off")));
        nt.setPadding(0, Ui.dp(8), 0, Ui.dp(8));
        nt.setOnClickListener(v -> { ExpiryAlarm.setEnabled(this, !ExpiryAlarm.enabled(this)); ExpiryAlarm.schedule(this, phones); ntDraw.run(); });
        ntDraw.run();
        s.addView(nt, Ui.fill());
        s.addView(Ui.muted(this, Ui.L("Nhắc trước 1 ngày và 1 giờ khi máy sắp hết hạn.", "Reminds you 1 day and 1 hour before a phone expires.")));
        body.addView(s, Ui.fill());

        LinearLayout l = Ui.card(this);
        l.addView(Ui.h2(this, Ui.L("Hỗ trợ", "Support")));
        Button web = Ui.button(this, "🌐 " + Ui.L("Mở website ", "Open ") + Api.webHost(), Ui.GHOST);
        web.setOnClickListener(v -> openWeb(Api.WEB));
        l.addView(web, Ui.fill());
        Button pol = Ui.button(this, "📄 " + Ui.L("Chính sách & điều khoản", "Policy & terms"), Ui.GHOST);
        pol.setOnClickListener(v -> openWeb(Api.WEB + "/#policy"));
        l.addView(pol, Ui.fill());
        body.addView(l, Ui.fill());

        Button out = Ui.button(this, Ui.L("Đăng xuất", "Log out"), Ui.DANGER);
        out.setOnClickListener(v -> Ui.confirm(this, Ui.L("Đăng xuất?", "Log out?"), Ui.L("Máy của bạn vẫn chạy bình thường.", "Your phones keep running."),
                Ui.L("Đăng xuất", "Log out"), () -> { ExpiryAlarm.cancelAll(this); Api.logout(); toLogin(); }));
        body.addView(out, Ui.fill());
        Button upd = Ui.button(this, "🔄 " + Ui.L("Kiểm tra cập nhật", "Check for updates"), Ui.GHOST);
        upd.setOnClickListener(v -> Updater.check(this, true));
        body.addView(upd, Ui.fill());
        TextView ver = Ui.muted(this, "CloudBlue v" + Api.version);
        ver.setGravity(Gravity.CENTER);
        body.addView(ver, Ui.fill());
        page(body);
    }

    // ---------------- Nạp tiền ngay trong app: chuyển khoản + mã VietQR, ngân hàng báo có là tự cộng số dư (giống web) ----------------
    static final long[] TOP_AMTS = {50000, 100000, 200000, 500000, 1000000};
    static final String[][] BANKS = {{"970422", "MB Bank"}, {"970436", "Vietcombank"}, {"970407", "Techcombank"}, {"970416", "ACB"}, {"970432", "VPBank"},
            {"970418", "BIDV"}, {"970415", "VietinBank"}, {"970423", "TPBank"}, {"970403", "Sacombank"}, {"970405", "Agribank"}, {"970441", "VIB"},
            {"970443", "SHB"}, {"970448", "OCB"}, {"970426", "MSB"}};

    void openTopup() { openTopup(0); }

    /** need > 0: số tiền còn thiếu (điền sẵn, làm tròn lên 1.000đ). */
    void openTopup(double need) {
        Api.<JSONObject>bg(Api::site, site -> topupSheet(site, need), m -> Ui.toast(this, m));
    }

    void topupSheet(JSONObject site, double need) {
        final long min = Math.max(1000, site.optLong("minTop", 10000));
        final String acc = site.optString("bankAcc", "").replaceAll("\\D", "");
        final long[] amt = {need > 0 ? Math.max(min, (long) Math.ceil(need / 1000.0) * 1000) : Math.max(min, 50000)};
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, Ui.L("Số dư hiện tại: ", "Balance: ") + Ui.vnd(prof.optDouble("balance", 0))
                + (need > 0 ? Ui.L("  ·  Cần thêm ", "  ·  Need ") + Ui.vnd(need) : "")));
        Ui.Wrap w = new Ui.Wrap(this, 8);
        java.util.TreeSet<Long> opts = new java.util.TreeSet<>();
        for (long v : TOP_AMTS) if (v >= min) opts.add(v);
        if (need > 0) opts.add(amt[0]);
        EditText x = Ui.input(this, Ui.L("Hoặc nhập số tiền khác (tối thiểu ", "Or type an amount (min ") + Ui.vnd(min) + ")", InputType.TYPE_CLASS_NUMBER);
        TextView err = Ui.text(this, "", 13, Ui.BAD, false);
        Button make = Ui.button(this, "", Ui.PRIMARY);
        Runnable draw = () -> {
            for (int i = 0; i < w.getChildCount(); i++) Ui.setChip((TextView) w.getChildAt(i), (long) w.getChildAt(i).getTag() == amt[0]);
            boolean ok = amt[0] >= min && !acc.isEmpty();
            err.setText(acc.isEmpty() ? Ui.L("Shop chưa cài tài khoản ngân hàng — tạm thời nạp trên web.", "Bank transfer isn't set up yet — please use the website.")
                    : amt[0] < min ? Ui.L("Số tiền tối thiểu là ", "The minimum is ") + Ui.vnd(min) + "." : "");
            err.setVisibility(err.getText().length() == 0 ? View.GONE : View.VISIBLE);
            make.setText(Ui.L("Tạo mã chuyển khoản ", "Create transfer code ") + Ui.vnd(amt[0]));
            make.setEnabled(ok);
            make.setAlpha(ok ? 1f : .5f);
        };
        for (long v : opts) {
            TextView ch = Ui.chip(this, Ui.vnd(v), false);
            ch.setTag(v);
            ch.setOnClickListener(t -> { amt[0] = (long) t.getTag(); x.setText(""); draw.run(); });
            w.addView(ch);
        }
        x.addTextChangedListener(new Simple(() -> {
            String s = x.getText().toString().replaceAll("\\D", "");
            if (s.isEmpty() || s.length() > 12) return;
            amt[0] = Long.parseLong(s);
            draw.run();
        }));
        c.addView(w, Ui.fill());
        c.addView(x, Ui.fill());
        c.addView(Ui.muted(this, Ui.L("Chuyển khoản ngân hàng: quét mã QR bằng app ngân hàng bất kỳ, tiền tự cộng vào số dư sau khoảng 1 phút.",
                "Bank transfer: scan the QR with any banking app; your balance is credited in about a minute.")));
        c.addView(err, Ui.fill());
        c.addView(make, Ui.fill());
        TextView cr = Ui.text(this, Ui.L("Nạp bằng USDT / LTC trên web ↗", "Top up with USDT / LTC on the website ↗"), 14, Ui.SKY, true);
        cr.setPadding(0, Ui.dp(6), 0, Ui.dp(6));
        cr.setOnClickListener(v -> openWeb(Api.WEB + "/?topup=1"));
        c.addView(cr, Ui.fill());
        Dialog d = Ui.sheet(this, "💳 " + Ui.L("Nạp tiền", "Top up"), c);
        make.setOnClickListener(v -> {
            if (amt[0] < min || acc.isEmpty()) return;
            make.setEnabled(false);
            final long a = amt[0];
            Api.bg(() -> Api.rpc("create_topup", new JSONObject().put("p_amount", a)), r -> {
                d.dismiss();
                if (r instanceof JSONObject) paySheet(site, (JSONObject) r);
            }, m -> { make.setEnabled(true); err.setText(m); err.setVisibility(View.VISIBLE); });
        });
        draw.run();
        d.show();
    }

    void paySheet(JSONObject site, JSONObject t) {
        final long amount = t.optLong("amount");
        final String memo = t.optString("memo"), id = t.optString("id");
        final String bin = site.optString("bankBin", "970422"), acc = site.optString("bankAcc", "").replaceAll("\\D", ""), name = site.optString("bankName", "");
        String bank = bin;
        for (String[] b : BANKS) if (b[0].equals(bin)) bank = b[1];
        LinearLayout c = Ui.col(this, 10);
        try {
            android.graphics.drawable.BitmapDrawable bd = new android.graphics.drawable.BitmapDrawable(getResources(), qrBitmap(vietqr(bin, acc, amount, memo), Ui.dp(232)));
            bd.setFilterBitmap(false);                     // giữ cạnh ô vuông sắc nét cho app ngân hàng quét
            android.widget.ImageView qr = new android.widget.ImageView(this);
            qr.setImageDrawable(bd);
            qr.setBackgroundColor(Color.WHITE);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(Ui.dp(232), Ui.dp(232));
            lp.gravity = Gravity.CENTER_HORIZONTAL;
            c.addView(qr, lp);
        } catch (Exception e) {
            c.addView(Ui.muted(this, Ui.L("Không tạo được mã QR — chuyển khoản theo thông tin bên dưới.", "Couldn't create the QR — use the details below.")));
        }
        c.addView(Ui.muted(this, Ui.L("Mở app ngân hàng → Quét mã QR: số tiền và nội dung tự điền. Chuyển tay thì ghi đúng nội dung bên dưới. Mã có hiệu lực 20 phút.",
                "Open your banking app → scan the QR: amount and note fill in automatically. Typing it in? Use the exact note below. Valid for 20 minutes.")));
        LinearLayout box = Ui.card(this);
        payRow(box, Ui.L("Ngân hàng", "Bank"), bank, null, false);
        payRow(box, Ui.L("Số tài khoản", "Account number"), acc, acc, false);
        payRow(box, Ui.L("Chủ tài khoản", "Account name"), name, null, false);
        payRow(box, Ui.L("Số tiền", "Amount"), Ui.vnd(amount), String.valueOf(amount), false);
        payRow(box, Ui.L("Nội dung chuyển khoản (ghi ĐÚNG)", "Transfer note (must match)"), memo, memo, true);
        c.addView(box, Ui.fill());
        TextView st = Ui.text(this, "⏳ " + Ui.L("Đang chờ ngân hàng báo có… (tự kiểm tra, không cần bấm gì)", "Waiting for the bank… (checks automatically)"), 14, Ui.WAIT, true);
        c.addView(st, Ui.fill());
        Button close = Ui.button(this, Ui.L("Đóng", "Close"), Ui.GHOST);
        c.addView(close, Ui.fill());
        Dialog d = Ui.sheet(this, Ui.L("Chuyển khoản ", "Transfer ") + Ui.vnd(amount), c);
        close.setOnClickListener(v -> d.dismiss());
        final long t0 = System.currentTimeMillis();
        final Runnable[] tick = new Runnable[1];
        tick[0] = () -> {
            if (!d.isShowing()) return;
            if (System.currentTimeMillis() - t0 > 25 * 60000L) {
                st.setText(Ui.L("Chưa thấy tiền về. Nếu đã chuyển đúng nội dung mà quá 15 phút chưa cộng, liên hệ hỗ trợ kèm nội dung chuyển khoản.",
                        "No payment seen yet. If you paid with the right note and it isn't credited after 15 minutes, contact support with the note."));
                st.setTextColor(Ui.BAD);
                return;
            }
            Api.bg(() -> Api.get("topups?id=eq." + id + "&select=status,amount"), r -> {
                JSONArray a = r instanceof JSONArray ? (JSONArray) r : new JSONArray();
                JSONObject o = a.length() > 0 ? a.optJSONObject(0) : null;
                if (o != null && "done".equals(o.optString("status"))) {
                    double got = o.optDouble("amount", amount);
                    st.setText("✓ " + Ui.L("Đã nhận ", "Received ") + Ui.vnd(got) + Ui.L(" — số dư đã được cộng.", " — balance credited."));
                    st.setTextColor(Ui.OK);
                    close.setText(Ui.L("Xong", "Done"));
                    Ui.toast(this, Ui.L("Nạp thành công +", "Top-up received +") + Ui.vnd(got));
                    refresh();
                    return;
                }
                h.postDelayed(tick[0], 5000);
            }, m -> h.postDelayed(tick[0], 8000));
        };
        h.postDelayed(tick[0], 5000);
        d.setOnDismissListener(z -> h.removeCallbacks(tick[0]));
        d.show();
    }

    private void payRow(LinearLayout box, String label, String value, String copy, boolean strong) {
        LinearLayout r = Ui.row(this, 8);
        LinearLayout col = Ui.col(this, 0);
        col.addView(Ui.text(this, label, 12, Ui.MUTED, false));
        TextView v = Ui.text(this, value, strong ? 18 : 15, strong ? Ui.WAIT : Ui.FG, true);
        v.setTextIsSelectable(true);
        col.addView(v);
        r.addView(col, Ui.weight(1));
        if (copy != null) {
            Button b = Ui.button(this, Ui.L("Chép", "Copy"), Ui.GHOST);
            b.setOnClickListener(z -> {
                android.content.ClipboardManager cm = (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(android.content.ClipData.newPlainText(label, copy));
                Ui.toast(this, Ui.L("Đã chép: ", "Copied: ") + copy);
            });
            r.addView(b, Ui.wrap());
        }
        box.addView(r, Ui.fill());
    }

    // ---- mã VietQR (chuẩn EMVCo / NAPAS 247) — giống hệt web ----
    static String tlv(String id, String v) { return id + String.format(Locale.US, "%02d", v.length()) + v; }

    static String crc16(String s) {
        int c = 0xFFFF;
        for (int i = 0; i < s.length(); i++) {
            c ^= s.charAt(i) << 8;
            for (int j = 0; j < 8; j++) c = (c & 0x8000) != 0 ? ((c << 1) ^ 0x1021) & 0xFFFF : (c << 1) & 0xFFFF;
        }
        return String.format(Locale.US, "%04X", c);
    }

    static String vietqr(String bin, String acc, long amount, String memo) {
        String cons = tlv("00", "A000000727") + tlv("01", tlv("00", bin) + tlv("01", acc)) + tlv("02", "QRIBFTTA");
        String p = tlv("00", "01") + tlv("01", "12") + tlv("38", cons) + tlv("53", "704") + tlv("54", String.valueOf(amount))
                + tlv("58", "VN") + tlv("62", tlv("08", memo)) + "6304";
        return p + crc16(p);
    }

    /** Vẽ mã QR (viền trắng 4 ô) thành ảnh vuông ~px điểm ảnh. */
    static android.graphics.Bitmap qrBitmap(String text, int px) {
        QrCode q = QrCode.encodeText(text, QrCode.Ecc.MEDIUM);
        int n = q.size, border = 4, total = n + border * 2, sc = Math.max(2, px / total), side = total * sc;
        int[] pix = new int[side * side];
        java.util.Arrays.fill(pix, Color.WHITE);
        for (int y = 0; y < n; y++)
            for (int x = 0; x < n; x++)
                if (q.getModule(x, y))
                    for (int dy = 0; dy < sc; dy++) {
                        int row = ((y + border) * sc + dy) * side + (x + border) * sc;
                        java.util.Arrays.fill(pix, row, row + sc, Color.BLACK);
                    }
        return android.graphics.Bitmap.createBitmap(pix, side, side, android.graphics.Bitmap.Config.ARGB_8888);
    }

    void openWeb(String u) {
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(u))); }
        catch (Exception e) { Ui.toast(this, u); }
    }

    /** TextWatcher gọn. */
    static class Simple implements android.text.TextWatcher {
        private final Runnable r;
        Simple(Runnable r) { this.r = r; }
        public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
        public void onTextChanged(CharSequence s, int a, int b, int c) { }
        public void afterTextChanged(android.text.Editable e) { r.run(); }
    }
}
