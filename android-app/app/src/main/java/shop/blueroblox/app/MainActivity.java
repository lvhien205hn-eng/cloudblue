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

/** Màn chính: Máy của tôi · Cloud Phone (thuê điện thoại đám mây) · VPS GPU (máy PC thật — 21/11e) · Tài khoản.
 *  Số thứ tự tab: 0 Máy của tôi · 1 Cloud Phone · 2 Tài khoản · 3 VPS GPU · 4 VPS NVMe (27/11) — thanh dưới xếp 0 · 1 · 3 · 4 · 2. */
public class MainActivity extends Activity {
    static final int[] RAM = {2, 4, 6, 8, 12, 16}, CPU = {2, 4, 6, 8, 12, 16, 24, 32}, DAYS = {1, 3, 7, 15, 30, 60}, FPS = {30, 60, 90, 120}, QTY = {1, 2, 3, 5, 10};
    static final String[][] RES = {{"540x960", "Nhẹ máy"}, {"720x1280", "HD"}, {"720x1600", "HD+ dài"}, {"1080x1920", "Full HD"}, {"1080x2400", "FHD+ 20:9"}, {"1280x720", "HD ngang"}};

    private FrameLayout content;
    private TextView balTop, blueTop;
    private TextView tickerV;                         // 📣 dòng chữ chạy ưu đãi (SQL v35) — bản CH Play không có
    LinearLayout dropV;                               // ⚡ ô phát mã nhanh tay (SQL v38) — ngay dưới dải chữ chạy
    private String offersSig = "";                    // ưu đãi đang vẽ trên màn (đổi mới vẽ lại)
    private TextView blueAcc;                         // dòng 💎 trong thẻ Tài khoản (cập nhật tại chỗ, không vẽ lại cả trang)
    boolean bluePayRent = false;                      // khách đã bật "Trả bằng Blue" ở bảng thuê (giữ khi bảng vẽ lại)
    String rentPromo = "";                            // mã giảm giá đang gõ ở bảng thuê (giữ khi bảng vẽ lại)
    private Runnable rentUpd;                         // tính lại tổng tiền bảng thuê (Blue tải xong → cập nhật)
    private final TextView[] nav = new TextView[5];
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
    boolean rentCustom = false;                       // ⚙️ Tự chỉnh cấu hình (RAM · CPU · FPS · độ phân giải) đang mở
    boolean rentPicked = false;                       // khách ĐÃ bấm 1 gói / tự chỉnh — chưa thì trang Thuê máy không hiện số tiền
    private ScrollView rentSv = null;                 // trang Thuê máy đang hiện (giữ chỗ cuộn khi vẽ lại)
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
        // 16/11: Ui.Head — tên "CloudBlue" luôn hiện ĐỦ; ô số dư / Blue không đủ chỗ thì tự xuống hàng 2 (trước đây chúng đè, tên chỉ còn "Clo…")
        Ui.Head top = new Ui.Head(this, 10, 6);
        top.setPadding(Ui.dp(14), Ui.dp(10), Ui.dp(14), Ui.dp(10));
        top.setBackground(Ui.round(Ui.LIGHT ? Color.argb(246, 243, 247, 252) : Color.argb(246, 7, 18, 38), 0, 0));
        LinearLayout logo = Ui.row(this, 10);
        logo.addView(Ui.whale(this, 34), new LinearLayout.LayoutParams(Ui.dp(50), Ui.dp(34)));
        SpannableString bn = new SpannableString("CloudBlue");          // "Cloud" màu chữ thường + "Blue" xanh (giống logo web)
        bn.setSpan(new ForegroundColorSpan(Ui.LIGHT ? Ui.BLUE : Color.rgb(90, 168, 255)), 5, 9, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        TextView brand = Ui.text(this, "", 19, Ui.FG, true);
        brand.setText(bn);
        brand.setSingleLine(true);
        logo.addView(brand, Ui.wrap());
        top.addView(logo, new ViewGroup.LayoutParams(-2, -2));
        LinearLayout chips = Ui.row(this, 8);
        balTop = Ui.pill(this, "…", Ui.MONEY);
        balTop.setSingleLine(true);
        balTop.setOnClickListener(v -> openTopup());
        if (!Api.SHOP) balTop.setVisibility(View.GONE);  // không mua trong app → không hiện số dư / nạp tiền
        chips.addView(balTop, Ui.wrap());
        blueTop = Ui.pill(this, "💎", Ui.SKY);              // 💎 Tích Blue (SQL v27) — hiện khi máy chủ đã bật
        blueTop.setSingleLine(true);
        blueTop.setVisibility(View.GONE);
        blueTop.setContentDescription(Ui.L("Tích Blue", "Blue rewards"));
        blueTop.setOnClickListener(v -> Blue.sheet(this));
        chips.addView(blueTop, Ui.wrap());
        top.addView(chips, new ViewGroup.LayoutParams(-2, -2));
        TextView th = Ui.text(this, Ui.LIGHT ? "🌙" : "☀️", 17, Ui.FG, false);
        th.setGravity(Gravity.CENTER);
        th.setContentDescription(Ui.L("Đổi chế độ Sáng / Tối", "Switch light / dark mode"));
        Ui.ripple(th, Ui.PANEL, 99, Ui.RING);
        th.setOnClickListener(v -> { Ui.setLight(this, !Ui.LIGHT); recreate(); });
        top.addView(th, new ViewGroup.LayoutParams(Ui.dp(40), Ui.dp(40)));
        root.addView(top, Ui.fill());
        tickerV = Offers.ticker(this);
        LinearLayout.LayoutParams tkLp = Ui.fill();
        tkLp.setMargins(Ui.dp(12), Ui.dp(2), Ui.dp(12), Ui.dp(4));
        root.addView(tickerV, tkLp);
        Offers.fillTicker(tickerV);
        dropV = Drop.bar(this);
        LinearLayout.LayoutParams dpLp = Ui.fill();
        dpLp.setMargins(Ui.dp(12), Ui.dp(2), Ui.dp(12), Ui.dp(4));
        root.addView(dropV, dpLp);

        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));

        // Thanh điều hướng dưới
        LinearLayout bar = Ui.row(this, 0);
        bar.setBackground(Ui.ringed(Ui.PANEL, 99));                   // 16/11c: thanh điều hướng nổi, bo tròn hẳn
        bar.setPadding(Ui.dp(6), Ui.dp(5), Ui.dp(6), Ui.dp(5));
        bar.setElevation(Ui.dp(6));
        String[][] items = {{"📱", Ui.L("Máy của tôi", "My devices")}, {"☁️", "Cloud Phone"}, {"👤", Ui.L("Tài khoản", "Account")}, {"🖥️", "VPS GPU"}, {"⚡", "VPS NVMe"}};
        for (int i : new int[]{0, 1, 3, 4, 2}) {                      // 21/11e: tab VPS GPU (số 3) · 27/11: tab VPS NVMe (số 4) — đứng trước Tài khoản
            final int t = i;
            TextView n = Ui.text(this, items[i][0] + "\n" + items[i][1], Api.SHOP ? 10 : 12, Ui.MUTED, true);   // 5 tab → chữ nhỏ hơn chút cho vừa màn hẹp
            n.setMaxLines(2);
            n.setEllipsize(android.text.TextUtils.TruncateAt.END);
            n.setGravity(Gravity.CENTER);
            n.setPadding(0, Ui.dp(8), 0, Ui.dp(8));
            n.setOnClickListener(v -> show(t));
            Ui.ripple(n, Color.TRANSPARENT, 99, 0);
            Ui.press(n);
            nav[i] = n;
            if (!Api.SHOP && (i == 1 || i == 3 || i == 4)) n.setVisibility(View.GONE);  // không mua trong app → không có tab Cloud Phone / VPS GPU / VPS NVMe (máy đã thuê vẫn ở Máy của tôi)
            bar.addView(n, Ui.weight(1));
        }
        LinearLayout.LayoutParams barLp = Ui.fill();
        barLp.setMargins(Ui.dp(12), Ui.dp(4), Ui.dp(12), Ui.dp(8));
        root.addView(bar, barLp);
        Ui.insets(root, true, true);
        setContentView(root);

        askNotifyPermission();
        Updater.check(this, false);                 // có bản app mới → hiện thông báo cập nhật ngay trong app
        show(getIntent().getIntExtra("tab", 0));
        refresh();
    }

    private final Reboots.Watch rbWatch = (pid, done, ok, msg) -> {      // 16/11c: máy bắt đầu / xong khởi động lại → vẽ lại thẻ máy
        if (destroyed) return;
        phonesSig = null;
        if (tab == 0) renderPhones();
        if (done && resumed) Ui.toast(this, (ok ? "✅ " : "⚠ ") + msg);
    };

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        Reboots.visible++;
        Reboots.listen(rbWatch);
        Api.onOutdated = () -> { if (!isFinishing()) Updater.check(this, false); };   // máy chủ báo app cũ → hộp bắt buộc cập nhật
        if (Api.loggedIn()) refresh();
        Updater.check(this, false);
        PlayPay.resume(this, this::credited);       // ▶️ bản CH Play: đã trả tiền Google Play mà chưa cộng (mất mạng / tắt app) → gửi lại
        h.removeCallbacks(vis);
        h.postDelayed(vis, 400);                    // quay lại màn này → bật lại hình các ô đang hiện
    }

    @Override protected void onPause() {
        super.onPause();
        resumed = false;
        Reboots.visible = Math.max(0, Reboots.visible - 1);
        Reboots.unlisten(rbWatch);
        PlayPay.pause(this);
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
            if (System.currentTimeMillis() - Blue.at > 60_000L) Blue.load(this::blueChanged);
            if (System.currentTimeMillis() - Offers.at > 120_000L) Offers.load(this::offersChanged);
            if (Drop.on() && System.currentTimeMillis() - Drop.at > (Drop.live() ? 15_000L : 45_000L)) Drop.load(this::dropChanged);   // ⚡ đợt phát mã
            if (Api.SHOP && System.currentTimeMillis() - RealPhone.at > 60_000L) RealPhone.load(this::realChanged);   // 📱 máy thật (SQL v70)
            ExpiryAlarm.schedule(this, phones);
            if (tab == 0) {
                if (phonesSig().equals(phonesSig)) tick();      // không có gì đổi → chỉ cập nhật chữ thời hạn (ô xem trước chạy liền, không nháy)
                else renderPhones();
            }
            else if (tab == 2) { if (!uiDrag) renderAccount(); }   // đang kéo thanh cỡ giao diện → khoan vẽ lại (thanh kéo biến mất dưới tay)
            else if (tab == 3) { if (!loaded || prof.optDouble("balance", 0) != vpsBal) renderVps(); }   // VPS GPU: vẽ lại khi số dư đổi (nạp / mua xong)
            else if (tab == 4) { if (!loaded || prof.optDouble("balance", 0) != vmBal) renderVm(); }     // VPS NVMe: như trên
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

    /** 📱 Danh mục máy thật vừa tải lại (SQL v70): nội dung ĐỔI → vẽ lại trang Thuê máy (thẻ BlueReal) / danh sách máy (tên mẫu máy). */
    private String realSig = null;
    void realChanged() {
        if (destroyed) return;
        String sig = String.valueOf(RealPhone.cat);
        if (sig.equals(realSig)) return;
        realSig = sig;
        if (!loaded) return;
        boolean mine = false;
        for (int i = 0; i < phones.length(); i++) if (RealPhone.isReal(phones.optJSONObject(i))) mine = true;
        if (tab == 1) renderRent(); else if (tab == 0 && mine) renderPhones();
    }

    /** Vừa thuê máy thật → về "Máy của tôi" xem máy đang chuẩn bị, tải lại vài lần cho tới khi máy chạy. */
    void afterRealBuy() {
        phonesSig = null;
        show(0);
        reloadSoon();
    }

    /** Tải lại ngay + 5 giây + 20 giây sau (máy chủ ghi hạn / trạng thái mới trong ít giây). */
    void reloadSoon() {
        phonesSig = null;
        refresh();
        h.postDelayed(this::refresh, 5000);
        h.postDelayed(this::refresh, 20000);
    }

    /** ⚡ Đợt phát mã vừa tải lại → vẽ lại ô (đổi số mã còn lại tại chỗ, không nháy). */
    void dropChanged() { if (!destroyed) Drop.fill(this, dropV); }

    /** 🎁 Ưu đãi vừa tải lại (SQL v35) → dòng chữ chạy; nội dung ĐỔI thì vẽ lại trang đang mở (ô Kiếm tiền / Ưu đãi, chữ dùng thử, mã của tôi). */
    void offersChanged() {
        if (destroyed) return;
        Offers.fillTicker(tickerV);
        String sig = String.valueOf(Offers.pub) + "|" + String.valueOf(Offers.my);
        if (sig.equals(offersSig)) return;
        offersSig = sig;
        if (!loaded) return;
        if (tab == 0) renderPhones(); else if (tab == 1 && Api.SHOP) renderRent();
    }
    /** Mở trang Thuê máy ở chế độ dùng thử. */
    void openTrial() {
        if (!Api.SHOP || !freeLive()) { show(Api.SHOP ? 1 : 0); return; }
        sFree = true; sQty = 1;
        sRam = Math.min(sRam, price.optInt("free_max_ram", 4)); sCpu = Math.min(sCpu, price.optInt("free_max_cpu", 4));
        show(1);
    }
    /** 🔁 Máy mới của lệnh ĐỔI ANDROID đang "Lỗi" → khách tự xếp lại lệnh tạo máy (hạn dùng vẫn giữ). */
    void switchRetry(JSONObject p, Button b) {
        b.setEnabled(false);
        Api.bg(() -> Api.rpc("cloudphone_switch_retry", new JSONObject().put("p_id", p.optString("id"))), r -> {
            Ui.toast(this, Ui.L("Đã xếp lại lệnh tạo máy — máy mới sẽ có sau ít phút. Hạn dùng của bạn vẫn giữ nguyên.", "Queued again — your new phone will be ready in a few minutes. Your expiry is unchanged."));
            phonesSig = null; refresh();
        }, m -> { b.setEnabled(true); Ui.toast(this, m); });
    }

    /** Blue vừa tải lại / đổi → chip 💎 trên đầu + dòng trong thẻ Tài khoản + bảng thuê (nếu đang mở) · nhắc điểm danh 1 lần / ngày. */
    void blueChanged() {
        if (destroyed) return;
        boolean on = Blue.on(); int todo = Blue.todo();
        blueTop.setVisibility(on ? View.VISIBLE : View.GONE);
        if (on) blueTop.setText("💎 " + Blue.n(Blue.bal()) + (todo > 0 ? " •" : ""));
        if (blueAcc != null && blueAcc.isAttachedToWindow())
            blueAcc.setText(on ? "💎 " + Blue.n(Blue.bal()) + " Blue" + (todo > 0 ? Ui.L("  ·  " + todo + " nhiệm vụ nhận được", "  ·  " + todo + " mission(s) ready") : "") : "");
        if (tab == 1 && loaded && Api.SHOP && rentUpd != null) rentUpd.run();
        JSONObject i = Blue.info;
        if (on && i != null && resumed) {
            android.content.SharedPreferences sp = getSharedPreferences("blue", MODE_PRIVATE);
            String k = "nudge_" + Api.uid, d = Blue.vnDay(), ki = "intro_" + Api.uid;
            if (!sp.getBoolean(ki, false)) {             // lần đầu thấy Tích Blue → hộp hướng dẫn cách nhận (1 lần / tài khoản / máy)
                sp.edit().putBoolean(ki, true).putString(k, d).apply();
                getWindow().getDecorView().postDelayed(() -> { if (!destroyed && !isFinishing()) Blue.intro(this); }, 700);
            } else if (!i.optBoolean("today") && !d.equals(sp.getString(k, ""))) {
                sp.edit().putString(k, d).apply();
                Ui.toast(this, Ui.L("💎 Hôm nay chưa điểm danh — bấm 💎 ở trên để nhận +" + Blue.n(i.optLong("next_got")) + " Blue",
                        "💎 Check in today — tap 💎 at the top for +" + Blue.n(i.optLong("next_got")) + " Blue"));
            }
        }
    }

    private static boolean vpsAutoDone = false;
    /** 21/11f · Khách chỉ thuê VPS GPU (chưa có cloud phone) → lần đầu mở app tự sang tab VPS GPU (1 lần mỗi lần mở app). */
    void vpsAuto() {
        if (vpsAutoDone || destroyed || !loaded) return;
        vpsAutoDone = true;
        if (Api.SHOP && tab == 0 && phones.length() == 0 && PcVps.live() > 0) show(3);
    }

    void show(int t) {
        if (!Api.SHOP && (t == 1 || t == 3 || t == 4)) t = 0;     // không mua trong app → không có màn Cloud Phone / VPS GPU / VPS NVMe
        if (t == 1 && tab != 1) rentPicked = false;     // vào lại trang Thuê máy → chưa chọn gói, chưa hiện tiền
        tab = t;
        try { getIntent().putExtra("tab", t); } catch (Exception ignored) { }   // 16/11: màn vẽ lại (Sáng/Tối, cỡ giao diện, xoay máy) → ở lại tab này
        for (int i = 0; i < nav.length; i++) {
            nav[i].setTextColor(i == t ? Ui.SKY : Ui.MUTED);
            nav[i].setBackground(i == t ? Ui.round(Ui.LIGHT ? Color.argb(28, 43, 110, 240) : Color.argb(40, 90, 175, 255), 99, 0) : null);
        }
        if (t != 0) { releasePreviews(); phonesSig = null; ticks.clear(); }     // sang tab khác → tắt hẳn hình xem trước (đỡ pin + mạng)
        if (t == 3) PcVps.tErrAt = 0;                    // vào tab VPS GPU → đọc lại bảng giá (kể cả lần trước lỗi)
        if (t == 4) VmNvme.infoErrAt = 0;                // vào tab VPS NVMe → như trên
        if (t == 0) renderPhones(); else if (t == 1) renderRent(); else if (t == 3) renderVps(); else if (t == 4) renderVm(); else renderAccount();
    }

    // ---------------- TAB VPS GPU (21/11e) ----------------
    private ScrollView vpsSv = null;
    private double vpsBal = -1;

    /** 🖥️ Trang mua VPS GPU (máy PC thật, 1 cấu hình) — PcVps.tab dựng nội dung, ở đây gắn trang cuộn + thanh thanh toán dưới màn hình. */
    void renderVps() {
        final int keepY = tab == 3 && vpsSv != null && vpsSv.getParent() != null ? vpsSv.getScrollY() : 0;
        vpsBal = prof.optDouble("balance", 0);
        LinearLayout body = Ui.col(this, 14);
        View bar = PcVps.tab(this, body);
        final ScrollView sv = page(body);
        vpsSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        if (bar != null) {
            body.setPadding(body.getPaddingLeft(), body.getPaddingTop(), body.getPaddingRight(), Ui.dp(150));
            FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
            blp.setMargins(Ui.dp(10), 0, Ui.dp(10), Ui.dp(8));
            content.addView(bar, blp);
        }
    }

    /** Bảng giá VPS GPU vừa tải / vừa mua xong → vẽ lại nếu đang ở tab VPS GPU. */
    void vpsChanged() { if (!destroyed && tab == 3) renderVps(); vpsGrid(); }      // 22.11c: + lưới "Xem tất cả" (ô VPS GPU)

    // ---------------- TAB VPS NVMe (27/11) — VmNvme.tab dựng nội dung (như tab VPS GPU) ----------------
    private ScrollView vmSv = null;
    private double vmBal = -1;

    void renderVm() {
        final int keepY = tab == 4 && vmSv != null && vmSv.getParent() != null ? vmSv.getScrollY() : 0;
        vmBal = prof.optDouble("balance", 0);
        LinearLayout body = Ui.col(this, 14);
        View bar = VmNvme.tab(this, body);
        final ScrollView sv = page(body);
        vmSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        if (bar != null) {
            body.setPadding(body.getPaddingLeft(), body.getPaddingTop(), body.getPaddingRight(), Ui.dp(150));
            FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
            blp.setMargins(Ui.dp(10), 0, Ui.dp(10), Ui.dp(8));
            content.addView(bar, blp);
        }
    }

    /** Bảng giá / lựa chọn VPS NVMe vừa đổi → vẽ lại nếu đang ở tab VPS NVMe. */
    void vmChanged() { if (!destroyed && tab == 4) renderVm(); }

    /** "VPS NVMe của tôi" vừa tải lại sau 1 thao tác (gia hạn, nâng cấp, đổi tên…) → vẽ lại trang đang mở. */
    void vmMineChanged() {
        if (destroyed) return;
        if (tab == 0) { phonesSig = null; renderPhones(); } else if (tab == 4) renderVm();
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
                    : msg.isEmpty() || msg.equals("null") ? Ui.L("Máy của bạn vẫn được giữ, không bị tính hết hạn trong lúc bảo trì.", "Your phones are kept during maintenance.")
                    : Ui.vi() ? msg : Srv.en(msg, false, "Your phones are kept during maintenance. Please try again later.")));
            body.addView(m, Ui.fill());
        }
        LinearLayout head = Ui.row(this, 10);
        head.addView(Ui.h1(this, Ui.L("Máy của tôi", "My phones")), Ui.weight(1));
        if (phones.length() > 0 || !PcVps.gridItems().isEmpty()) {     // 22.11c: cả VPS GPU
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
        if (ctlCount() >= 2) body.addView(multiRow(), Ui.fill());       // 18/11: 🎮 điều khiển nhiều máy cùng lúc (từ 2 máy đang chạy)
        promo(body, true);                          // 🎡 vòng quay · 🎬 Kiếm tiền · 🎁 Ưu đãi — khách bấm ẩn / hiện được (16/11)

        // Nhập mã: mã TẶNG MÁY (12 ký tự) · mã chia sẻ / chuyển nhượng (8 ký tự)
        LinearLayout cr = Ui.row(this, 8);
        EditText code = Ui.input(this, Ui.L("🔑 Mã tặng máy / chia sẻ / chuyển nhượng", "🔑 Gift / share / transfer code"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        cr.addView(code, Ui.weight(1));
        Button cb = Ui.button(this, Ui.L("Nhập mã", "Redeem"), Ui.GHOST);
        cb.setOnClickListener(v -> claim(code, cb));
        cr.addView(cb, Ui.wrap());
        body.addView(cr, Ui.fill());
        PcVps.link(this, body);                     // 21/11f · VPS GPU là mục riêng (tab 🖥️ VPS GPU) — ở đây chỉ 1 dòng dẫn sang khi khách có VPS
        VmNvme.section(this, body);                 // 27/11 · ⚡ VPS NVMe của bạn (Ẩn / Hiện) — ngay dưới VPS GPU

        if (phones.length() == 0) {
            LinearLayout e = Ui.card(this);
            e.setGravity(Gravity.CENTER_HORIZONTAL);
            TextView ic = Ui.text(this, "📱", 44, Ui.FG, false);
            ic.setGravity(Gravity.CENTER);
            e.addView(ic, Ui.fill());
            TextView t = Ui.h2(this, !Api.SHOP ? Ui.L("Bạn chưa có máy nào", "You have no phones yet") : Ui.L("Bạn chưa thuê máy nào", "You have no phones yet"));
            t.setGravity(Gravity.CENTER);
            e.addView(t, Ui.fill());
            TextView d = Ui.muted(this, !Api.SHOP
                    ? Ui.L("Máy Android đám mây của bạn và máy được chia sẻ cho bạn sẽ hiện ở đây.", "Your cloud Android phones and phones shared with you appear here.")
                    : Ui.L("Chọn RAM, CPU, số ngày — máy Android sẵn sàng sau khoảng 2–3 phút.", "Pick RAM, CPU and days — your Android phone is ready in 2–3 minutes."));
            d.setGravity(Gravity.CENTER);
            e.addView(d, Ui.fill());
            if (Api.SHOP) {                             // không mua trong app → không có nút thuê máy
                Button go = Ui.button(this, Ui.L("Thuê máy ngay", "Rent a phone"), Ui.PRIMARY);
                go.setOnClickListener(v -> show(1));
                e.addView(go, Ui.fill());
            }
            body.addView(e, Ui.fill());
        }
        java.util.HashSet<String> live = new java.util.HashSet<>();
        for (int i = 0; i < phones.length(); i++) {
            JSONObject p = phones.optJSONObject(i);
            if (p == null) continue;
            if (canCtl(p)) live.add(p.optString("id"));
            body.addView(phoneCard(p), Ui.fill());
        }
        for (JSONObject x : PcVps.gridItems())                 // 22.11c: ô xem trước VPS GPU (trong "Xem tất cả") được giữ khi vẽ lại
            if (PcVps.liveNow(this, x)) live.add("pc:" + x.optJSONObject("pc").optString("id"));
        final ScrollView sv = page(body);
        phonesSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        prunePreviews(live);                        // máy không còn chạy (hết hạn, khoá, bảo trì, đã xoá) → bỏ ô xem trước
        if (gridOpen()) fillGrid();                 // đang mở "Xem tất cả" → vẽ lại lưới luôn (ô xem trước nằm bên đó)
        phonesSig = phonesSig();
        h.removeCallbacks(vis);
        if (resumed) h.postDelayed(vis, 300);
    }

    // ---------------- 16/11 · khách tự ẨN / HIỆN các ô ưu đãi đầu trang ----------------
    boolean promoHidden() { return getSharedPreferences("ui", MODE_PRIVATE).getBoolean("promo_hide", false); }
    void setPromoHidden(boolean hide) { getSharedPreferences("ui", MODE_PRIVATE).edit().putBoolean("promo_hide", hide).apply(); }

    /** Các ô 🎡 Vòng quay · 🎬 Kiếm tiền · 🎁 Ưu đãi ở đầu trang "Máy của tôi" (offers = true) / "Thuê máy": 1 dòng nhỏ để ẩn / hiện, nhớ theo máy.
     *  Ẩn chỉ để gọn màn hình — dòng chữ chạy, thẻ vòng quay ở Tài khoản và hộp Nạp tiền vẫn như cũ. Không có ô nào → không hiện dòng này. */
    private void promo(LinearLayout body, boolean offers) {
        final View os = offers ? Offers.strip(this) : null;
        final boolean wheel = Api.SHOP && Wheel.on();
        if (!wheel && os == null) return;
        final LinearLayout wrap = Ui.col(this, 6), box = Ui.col(this, 14);
        final TextView bar = Ui.text(this, "", 12.5f, Ui.MUTED, true);
        bar.setGravity(Gravity.CENTER);
        bar.setPadding(Ui.dp(12), Ui.dp(4), Ui.dp(12), Ui.dp(5));
        Ui.ripple(bar, Color.TRANSPARENT, 99, 0);
        bar.setTag("promo_bar");
        final View[] ws = {null};
        final Runnable upd = () -> {
            boolean hide = promoHidden(), any = os != null || (ws[0] != null && ws[0].getVisibility() == View.VISIBLE);
            wrap.setVisibility(any ? View.VISIBLE : View.GONE);
            box.setVisibility(hide ? View.GONE : View.VISIBLE);
            bar.setText(hide ? "🎁 " + Ui.L("Hiện ưu đãi · vòng quay", "Show offers · lucky wheel") + "  ▾" : Ui.L("Ẩn ưu đãi", "Hide offers") + "  ▴");
            bar.setTextColor(hide ? Ui.SKY : Ui.MUTED);
            bar.setContentDescription(hide ? Ui.L("Hiện các ô ưu đãi và vòng quay", "Show offers and the lucky wheel") : Ui.L("Ẩn các ô ưu đãi và vòng quay", "Hide offers and the lucky wheel"));
        };
        if (wheel) { ws[0] = Wheel.strip(this, upd); box.addView(ws[0], Ui.fill()); }
        if (os != null) box.addView(os, Ui.fill());
        bar.setOnClickListener(v -> { setPromoHidden(!promoHidden()); upd.run(); });
        LinearLayout.LayoutParams bl = Ui.wrap();       // chỉ chữ bấm được (canh phải) — chạm chỗ trống bên trái không đổi gì
        bl.gravity = Gravity.END;
        wrap.addView(bar, bl);
        wrap.addView(box, Ui.fill());
        body.addView(wrap, Ui.fill());
        upd.run();
    }

    /** Máy điều khiển được (đang chạy, không bị khoá — admin bỏ qua khoá — và không bảo trì). */
    boolean canCtl(JSONObject p) {
        return "active".equals(p.optString("status")) && (!locked(p) || isAdmin()) && !maintBlocks();
    }

    /** Số máy điều khiển được ngay lúc này. */
    int ctlCount() {
        int n = 0;
        for (int i = 0; i < phones.length(); i++) {
            JSONObject p = phones.optJSONObject(i);
            if (p != null && canCtl(p)) n++;
        }
        return n;
    }

    /** 18/11 · dòng mở màn 🎮 "Điều khiển nhiều máy cùng lúc" (MultiActivity): chia ô các máy, vuốt qua máy khác, đồng bộ thao tác. */
    private View multiRow() {
        LinearLayout r = Ui.row(this, 10);
        r.setPadding(Ui.dp(14), Ui.dp(10), Ui.dp(12), Ui.dp(10));
        Ui.ripple(r, Ui.PANEL2, 14, Ui.LINE);
        r.addView(Ui.text(this, "🎮", 20, Ui.FG, false), Ui.wrap());
        LinearLayout tx = Ui.col(this, 1);
        tx.addView(Ui.text(this, Ui.L("Điều khiển nhiều máy cùng lúc", "Control several phones at once"), 14.5f, Ui.FG, true));
        tx.addView(Ui.text(this, Ui.L("Chia ô các máy · vuốt qua máy khác · đồng bộ thao tác", "Grid of phones · swipe to switch · mirror your taps"), 12, Ui.MUTED, false));
        r.addView(tx, Ui.weight(1));
        r.addView(Ui.text(this, "›", 22, Ui.MUTED, false), Ui.wrap());
        r.setContentDescription(Ui.L("Điều khiển nhiều máy cùng lúc", "Control several phones at once"));
        r.setOnClickListener(v -> openMulti());
        return r;
    }

    void openMulti() {
        try { startActivity(new Intent(this, MultiActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP)); }
        catch (Exception e) { Ui.toast(this, Ui.L("Chưa mở được màn nhiều máy — cập nhật app rồi thử lại.", "Couldn't open multi-control — update the app and try again.")); }
    }

    /** Dấu vân tay những gì danh sách đang hiện: giống lần trước → khỏi vẽ lại (thời hạn tự cập nhật bằng tick()). */
    String phonesSig() {
        StringBuilder b = new StringBuilder(256);
        b.append(status.optBoolean("maint", false)).append('|').append(status.optString("maint_msg", "")).append('|')
                .append(isAdmin()).append('|').append(maintBlocks());
        String[] keys = {"id", "name", "status", "ram", "cpu", "res", "fps", "expires_at", "lock_reason", "shared", "share_expires", "owner_name", "share_id",
                "android", "switch_to", "replaces", "error"};
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

    /** 22.11c · dữ liệu VPS GPU vừa tải lại → đang mở "Xem tất cả" thì vẽ lại lưới (ô xem trước chạy tiếp). */
    private void vpsGrid() {
        if (destroyed || isFinishing()) return;
        if (gridOpen()) fillGrid();
        h.removeCallbacks(vis);
        if (resumed) h.postDelayed(vis, 300);
    }

    /** 22.11c · ô tĩnh của 1 VPS GPU: biểu tượng máy tính + trạng thái (máy không chạy, hoặc phủ trên ô xem trước lúc chưa có hình). */
    private View vpsTile(JSONObject x, float iconSp) {
        String[] st = PcVps.state(x);
        boolean live = PcVps.liveNow(this, x), mt = !PcVps.maint(this).isEmpty();
        LinearLayout t = Ui.col(this, 4);
        t.setGravity(Gravity.CENTER);
        t.setPadding(Ui.dp(8), Ui.dp(6), Ui.dp(8), Ui.dp(6));
        TextView ic = Ui.text(this, "🖥️", iconSp, Color.WHITE, false);
        ic.setGravity(Gravity.CENTER);
        t.addView(ic, Ui.fill());
        String s = live ? "● " + Ui.L("Đang chạy", "Running") : mt && ("run".equals(st[0]) || "warn".equals(st[0])) ? "🛠 " + Ui.L("Đang bảo trì", "Maintenance") : st[1];
        TextView tx = Ui.text(this, s, 12, live ? Color.rgb(60, 224, 176) : "exp".equals(st[0]) ? Color.rgb(255, 120, 140) : Color.rgb(255, 200, 97), true);
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

    /** 22.11c · ô xem trước của 1 VPS GPU (khoá "pc:" + mã máy — không lẫn với Cloud Phone), lấy lại ô cũ nếu có. */
    private LivePreview vpsPreview(JSONObject x, float iconSp) {
        String id = x.optJSONObject("pc").optString("id"), key = "pc:" + id;
        LivePreview lp = previews.get(key);
        if (lp == null) {
            lp = new LivePreview(this, id, 1920, 1080, "c".equals(StreamClient.netTag(this)) ? 320 : 480, true);    // máy PC: màn ngang 16:9
            previews.put(key, lp);
        }
        lp.setCover(vpsTile(x, iconSp));
        ViewParent vp = lp.getParent();
        if (vp instanceof ViewGroup) ((ViewGroup) vp).removeView(lp);
        lp.hiddenAt = 0;
        return lp;
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
        final java.util.List<JSONObject> vps = PcVps.gridItems();       // 22.11c: VPS GPU (ô ngang 16:9) nằm trên Cloud Phone
        for (JSONObject x : vps) if (PcVps.liveNow(this, x)) run++; else other++;
        LinearLayout tt = Ui.col(this, 2);
        tt.addView(Ui.h2(this, Ui.L("Tất cả máy (", "All machines (") + (phones.length() + vps.size()) + ")"));
        tt.addView(Ui.muted(this, "● " + run + Ui.L(" đang chạy", " running") + (pause > 0 ? " · ⏸ " + pause + Ui.L(" tạm dừng", " paused") : "")
                + (other > 0 ? " · " + other + Ui.L(" khác", " other") : "") + Ui.L(" · bấm ô: điều khiển", " · tap a machine to control")));
        top.addView(tt, Ui.weight(1));
        if (ctlCount() >= 2) {                                           // 18/11: từ lưới xem → sang lưới ĐIỀU KHIỂN nhiều máy
            TextView mc = Ui.pill(this, "🎮 " + Ui.L("Điều khiển", "Control"), Ui.OK);
            mc.setOnClickListener(v -> { closeGrid(); openMulti(); });
            top.addView(mc, Ui.wrap());
        }
        TextView close = Ui.pill(this, "✕ " + Ui.L("Đóng", "Close"), Ui.SKY);
        top.addView(close, Ui.wrap());
        root.addView(top, Ui.fill());

        LinearLayout grid = Ui.col(this, gap);
        LinearLayout row = null;
        if (!vps.isEmpty()) {
            final int vc = wdp >= 900 ? 4 : wdp >= 600 ? 3 : 2;
            int vw = (dm.widthPixels - pad * 2 - gap * (vc - 1)) / vc, vh = vw * 9 / 16 + Ui.dp(7);
            if (phones.length() > 0) grid.addView(Ui.text(this, "🖥️ VPS GPU (" + vps.size() + ")", 15, Ui.FG, true), Ui.fill());
            for (int i = 0; i < vps.size(); i++) {
                final JSONObject x = vps.get(i), pc = x.optJSONObject("pc");
                if (i % vc == 0) { row = Ui.row(this, gap); grid.addView(row, Ui.fill()); }
                boolean live = PcVps.liveNow(this, x);
                String code = PcVps.state(x)[0];
                LinearLayout cell = Ui.col(this, 4);
                FrameLayout box = new FrameLayout(this);
                box.setBackground(Ui.round(Color.rgb(2, 4, 12), 8, live ? Color.argb(90, 61, 220, 132) : "exp".equals(code) ? Color.argb(70, 255, 93, 108) : Color.argb(80, 255, 200, 97)));
                int bz = Ui.dp(3.5f);
                box.setPadding(bz, bz, bz, bz);
                box.addView(live ? vpsPreview(x, 22) : vpsTile(x, 22), new FrameLayout.LayoutParams(-1, -1));
                TextView dot = Ui.text(this, live ? "●" : "○", 12, live ? Ui.OK : "exp".equals(code) ? Ui.BAD : Ui.WAIT, true);
                dot.setShadowLayer(3, 0, 0, Color.BLACK);
                FrameLayout.LayoutParams dlp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.END);
                dlp.setMargins(0, Ui.dp(4), Ui.dp(6), 0);
                box.addView(dot, dlp);
                if (live) box.setOnClickListener(v -> PcVps.control(this, pc.optString("id"), pc.optString("name")));   // bấm: vào điều khiển máy PC
                cell.addView(box, new LinearLayout.LayoutParams(-1, vh));
                TextView nm = Ui.text(this, pc.optString("name", "VPS GPU") + (pc.optString("code").isEmpty() || pc.optString("name").contains(pc.optString("code")) ? "" : " · " + pc.optString("code")), 12, Ui.FG, true);
                nm.setSingleLine(true); nm.setEllipsize(android.text.TextUtils.TruncateAt.END);
                cell.addView(nm, Ui.fill());
                long until = parseTime(x.optString("until", ""));
                TextView sub = Ui.text(this, x.optString("os_name") + (until > 0 ? " · ⏱ " + left(until) : ""), 11, until > 0 && until - System.currentTimeMillis() < 86400000L ? Ui.WAIT : Ui.MUTED, false);
                sub.setSingleLine(true); sub.setEllipsize(android.text.TextUtils.TruncateAt.END);
                cell.addView(sub, Ui.fill());
                row.addView(cell, new LinearLayout.LayoutParams(0, -2, 1f));
            }
            for (int k = vps.size() % vc; k > 0 && k < vc; k++) row.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1f));
            row = null;
            if (phones.length() > 0) grid.addView(Ui.text(this, "📱 Cloud Phone (" + phones.length() + ")", 15, Ui.FG, true), Ui.fill());
        }
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
            TextView nm = Ui.text(this, p.optString("name", Ui.L("Máy", "Phone")), 12, Ui.FG, true);
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
        r1.addView(Ui.text(this, p.optString("name", Ui.L("Máy", "Phone")), 17, Ui.FG, true), Ui.weight(1));
        String label; int col;
        if (lk) { label = "🔒 " + Ui.L("Bị khoá", "Locked"); col = Ui.BAD; }
        else if ("active".equals(st) && Reboots.active(this, p.optString("id"))) { label = "🔄 " + Ui.L("Đang khởi động lại…", "Restarting…"); col = Ui.WAIT; }   // 16/11c
        else if ("active".equals(st)) { label = "● " + Ui.L("Đang chạy", "Running"); col = Ui.OK; }
        else if ("pending".equals(st)) { label = "◌ " + Ui.L("Đang tạo…", "Creating…"); col = Ui.WAIT; }
        else if ("expired".equals(st)) { label = "⏸ " + Ui.L("Tạm dừng", "Paused"); col = Ui.BAD; }
        else { label = Ui.L("Lỗi", "Error"); col = Ui.BAD; }
        r1.addView(Ui.pill(this, label, col), Ui.wrap());
        c.addView(r1, Ui.fill());

        String av = p.optString("android", "").trim();
        final boolean real = RealPhone.isReal(p);           // 28/11 · SQL v70: 📱 máy THẬT (BlueReal)
        c.addView(Ui.muted(this, real ? RealPhone.info(p)
                : (av.isEmpty() || "null".equals(av) ? "" : "Android " + av + " · ") + p.optInt("ram") + "GB RAM · " + p.optInt("cpu") + Ui.L(" nhân", " cores") + SwitchAndroid.paidTag(p) + " · " + p.optString("res", "") + " · " + p.optInt("fps", 30) + " FPS"), Ui.fill());

        if (exp > 0) c.addView(expiryText(p, true, ticks), Ui.fill());
        if (lk) {
            String why = p.optString("lock_reason", "");
            c.addView(Ui.text(this, Ui.L("Máy đang bị khoá", "This phone is locked") + (why.isEmpty() || why.equals("null") ? "" : ": " + why), 13, Ui.BAD, false), Ui.fill());
        }
        if (SwitchAndroid.isNewFromSwitch(p))             // máy MỚI của lệnh đổi Android (v28: máy cũ bị xoá trước)
            c.addView(Ui.text(this, "🤖 " + SwitchAndroid.newNote(p, phones), 13, Ui.WAIT, false), Ui.fill());
        else if ("pending".equals(st)) c.addView(Ui.muted(this, real ? RealPhone.pendingNote()
                : Ui.L("Máy đang khởi động và cài app sẵn, khoảng 2–3 phút. Trang tự cập nhật.", "Booting and installing apps, about 2–3 minutes.")), Ui.fill());
        JSONObject swTo = SwitchAndroid.switching(p, phones);
        if (swTo != null)                                // máy CŨ đang chờ máy mới
            c.addView(Ui.text(this, "🤖 " + Ui.L("Đang đổi sang Android " + SwitchAndroid.cur(swTo) + ": máy mới đang tạo, máy này vẫn dùng được tới lúc đó rồi tự xoá.",
                    "Switching to Android " + SwitchAndroid.cur(swTo) + ": the new phone is being created; this one keeps working until then."), 13, Ui.WAIT, false), Ui.fill());
        if ("error".equals(st)) {                        // lỗi tạo máy / đổi Android lỗi hẳn → nói rõ lý do (đã hoàn tiền / admin sẽ tạo lại)
            String er = p.optString("error", "");
            if (!er.isEmpty() && !"null".equals(er)) c.addView(Ui.text(this, Ui.srv(er), 13, Ui.BAD, false), Ui.fill());
            if (!p.isNull("replaces") && !p.optBoolean("shared", false)) {       // máy mới của lệnh đổi Android → khách tự thử lại (SQL doi-android-1511)
                Button rt = Ui.button(this, "🔁 " + Ui.L("Thử tạo lại máy", "Try again"), Ui.GHOST);
                rt.setOnClickListener(v -> switchRetry(p, rt));
                c.addView(rt, Ui.fill());
            }
        }
        { String tn = Offers.phoneNote(p); if (tn != null && !"error".equals(st)) c.addView(Ui.text(this, tn, 13, Ui.WAIT, false), Ui.fill()); }
        String swFail = SwitchAndroid.failNote(p);
        if (swFail != null && swTo == null) c.addView(Ui.text(this, swFail, 13, Ui.BAD, false), Ui.fill());
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
        if (Api.SHOP) {                                 // gia hạn (trả bằng số dư)
            Button rn = Ui.button(this, Ui.L("Gia hạn", "Renew"), Ui.GHOST);
            rn.setOnClickListener(v -> renew(p));
            rn.setEnabled(!lk && ("active".equals(st) || "expired".equals(st)));
            acts.addView(rn, Ui.weight(1));
        }
        Button more = Ui.button(this, "⋯", Ui.GHOST);
        more.setOnClickListener(v -> moreMenu(p));
        acts.addView(more, Ui.wrap());
        c.addView(acts, Ui.fill());
        return c;
    }

    void renew(JSONObject p) {
        if (RealPhone.isReal(p)) { RealPhone.renew(this, p); return; }      // 28/11 · SQL v70: máy thật gia hạn theo giá / ngày của mẫu máy
        int max = price.optInt("max_days", 365);
        final int[] days = {Math.min(30, max)};
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, p.optInt("ram") + "GB · " + p.optInt("cpu") + Ui.L(" nhân", " cores") + SwitchAndroid.paidTag(p) + " · " + left(parseTime(p.optString("expires_at")))));
        if (!SwitchAndroid.paidTag(p).isEmpty()) {          // 22/11 · SQL v49b: gia hạn lúc TẠM hạ → cấu hình đã mua hạ theo cấu hình đang chạy
            int[] q = SwitchAndroid.paid(p);
            String full = SwitchAndroid.fullAnd(price, p), cur = p.optInt("ram") + "GB · " + p.optInt("cpu");
            c.addView(Ui.text(this, "⚠️ " + Ui.L("Máy đang TẠM chạy " + cur + " nhân (đã mua " + q[0] + "GB · " + q[1] + " nhân). Gia hạn bây giờ tính theo cấu hình đang chạy và cấu hình đã mua hạ còn " + cur + " nhân."
                            + (full.isEmpty() ? "" : " Muốn giữ " + q[0] + "GB · " + q[1] + " nhân: đổi sang " + full + " trước rồi hãy gia hạn."),
                    "This phone TEMPORARILY runs " + cur + " cores (you bought " + q[0] + "GB · " + q[1] + " cores). Renewing now is priced on the running config and your bought config drops to " + cur + " cores."
                            + (full.isEmpty() ? "" : " To keep " + q[0] + "GB · " + q[1] + " cores, switch to " + full + " first, then renew.")), 13.5f, Ui.WAIT, false), Ui.fill());
        }
        Ui.Wrap w = new Ui.Wrap(this, 8);
        int[] opts = {1, 3, 7, 15, 30, 60, 90};
        TextView sum = Ui.text(this, "", 14, Ui.FG, false);
        EditText x = Ui.input(this, Ui.L("Hoặc tự nhập số ngày", "Or type days"), InputType.TYPE_CLASS_NUMBER);
        Button ok = Ui.button(this, Ui.L("Gia hạn", "Renew"), Ui.PRIMARY);
        final Promo[] pr = new Promo[1];                // 🏷️ mã giảm giá · 💎 trả bằng Blue (bản web)
        final Blue.Pay[] bp = new Blue.Pay[1];
        Runnable draw = () -> {
            for (int i = 0; i < w.getChildCount(); i++) Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == days[0]);
            double per = ctv(perDay(p.optInt("ram"), p.optInt("cpu"))), total0 = per * days[0], bal = prof.optDouble("balance", 0);
            if (pr[0] != null) pr[0].onOrderChanged();
            double pay = pr[0] == null ? total0 : pr[0].price(total0);
            long bu = bp[0] == null ? 0 : bp[0].use(pay);
            if (bp[0] != null) bp[0].paint(pay, false);
            double total = pay - bu;
            long base = Math.max(System.currentTimeMillis(), parseTime(p.optString("expires_at")));
            sum.setText(Ui.L("Đơn giá: ", "Price: ") + Ui.vnd(per) + Ui.L(" / ngày", " / day") + (isCtv() ? " (CTV −" + prof.optInt("ctv_discount") + "%)" : "")
                    + "\n" + Ui.L("Hạn mới: ", "New expiry: ") + fdate(base + days[0] * 86400000L)
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + "\n" + Ui.L("Thanh toán: ", "Total: ") + Ui.vnd(total)
                    + (pay < total0 ? "  (🏷️ −" + Ui.vnd(total0 - pay) + ")" : "") + (bu > 0 ? "  (💎 −" + Blue.n(bu) + " Blue)" : ""));
            boolean enough = bal >= total;
            ok.setText(!enough ? Ui.L("Nạp thêm tiền", "Top up") : total <= 0 && bu > 0 ? Ui.L("💎 Gia hạn " + days[0] + " ngày bằng Blue", "💎 Renew " + days[0] + " days with Blue")
                    : Ui.L("Gia hạn " + days[0] + " ngày", "Renew " + days[0] + " days"));
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
        if (Api.SHOP) {
            pr[0] = new Promo(this, "cp_renew", () -> new JSONObject().put("p_phone", p.optString("id")).put("p_days", days[0]), draw);
            bp[0] = new Blue.Pay(this, false, draw);
            c.addView(pr[0].view, Ui.fill());
            c.addView(bp[0].view, Ui.fill());
        }
        LinearLayout sb = Ui.card(this);
        sb.addView(sum);
        c.addView(sb, Ui.fill());
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, Ui.L("Gia hạn ", "Renew ") + p.optString("name"), c);
        ok.setOnClickListener(v -> {
            Runnable go = () -> {
                double total0 = ctv(perDay(p.optInt("ram"), p.optInt("cpu"))) * days[0];
                double pay = pr[0] == null ? total0 : pr[0].price(total0);
                long bu = bp[0] == null ? 0 : bp[0].use(pay);
                double total = pay - bu;
                if (prof.optDouble("balance", 0) < total) { d.dismiss(); openTopup(total - prof.optDouble("balance", 0)); return; }
                final String code = pr[0] == null ? null : pr[0].send();
                final boolean blue = bu > 0;
                ok.setEnabled(false);
                Api.bg(() -> {
                    JSONObject a = new JSONObject().put("p_id", p.optString("id")).put("p_days", days[0]);
                    if (code != null) a.put("p_promo", code);
                    if (blue) a.put("p_blue", true);
                    try { return Api.rpc("cloudphone_renew", a); }
                    catch (Exception e) { String m = String.valueOf(e.getMessage()); if (pr[0] != null && m.contains("PROMO_")) Api.ui(() -> pr[0].fail(m)); throw e; }
                }, r -> {
                    d.dismiss();
                    Ui.toast(this, Ui.L("Đã gia hạn +" + days[0] + " ngày cho ", "Renewed +" + days[0] + " days: ") + p.optString("name"));
                    Blue.at = 0;
                    refresh();
                    h.postDelayed(this::refresh, 5000);
                }, m -> { ok.setEnabled(true); Ui.toast(this, m); });
            };
            if (pr[0] == null) go.run(); else pr[0].ensure(go);
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
        final Promo[] pr = new Promo[1];                // 🏷️ mã giảm giá cho nâng cấp (bản web)
        LinearLayout pzu = Ui.col(this, 0);
        c.addView(pzu, Ui.fill());
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
                    r -> { if (qr == nr[0] && qc == nc[0]) { long v = quoteOf(r); cost[0] = v >= 0 ? v : localQuote(p, qr, qc); draw[0].run(); } },
                    m -> { });
        };
        draw[0] = () -> {
            for (int i = 0; i < wr.getChildCount(); i++) Ui.setChip((TextView) wr.getChildAt(i), (int) wr.getChildAt(i).getTag() == nr[0]);
            for (int i = 0; i < wc.getChildCount(); i++) Ui.setChip((TextView) wc.getChildAt(i), (int) wc.getChildAt(i).getTag() == nc[0]);
            boolean same = nr[0] == R0 && nc[0] == C0;
            double bal = prof.optDouble("balance", 0);
            if (pr[0] != null) { pr[0].view.setVisibility(same ? View.GONE : View.VISIBLE); if (!same) pr[0].onOrderChanged(); }
            double pay = same || pr[0] == null ? cost[0] : pr[0].price(cost[0]);
            String how = same ? "" : upgradeHow(p, nr[0], nc[0]);
            sum.setText(same ? Ui.L("Chọn RAM hoặc CPU muốn nâng.", "Pick more RAM or CPU.")
                    : Ui.L("Cấu hình mới: ", "New: ") + nr[0] + "GB · " + nc[0] + Ui.L(" nhân", " cores")
                    + (how.isEmpty() ? "" : "\n" + how)
                    + "\n" + Ui.L("Trả thêm cho thời gian còn lại: ", "Pay for the remaining time: ") + Ui.vnd(pay)
                    + (pay < cost[0] ? "  (🏷️ −" + Ui.vnd(cost[0] - pay) + ")" : "")
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + (bal >= pay ? Ui.L(" → còn ", " → left ") + Ui.vnd(bal - pay) + Ui.L(" sau khi trừ", " after paying") : ""));
            ok.setEnabled(!same);
            ok.setText(!same && bal < pay ? Ui.L("Nạp thêm tiền", "Top up") : Ui.L("Nâng cấp ngay", "Upgrade now"));
        };
        int[] rams = {2, 3, 4, 6, 8, 10, 12, 16}, cpus = {2, 3, 4, 6, 8, 10, 12, 16};
        java.util.TreeSet<Integer> rs = new java.util.TreeSet<>(), cs = new java.util.TreeSet<>();
        rs.add(R0); for (int v : rams) if (v > R0 && v <= maxR) rs.add(v); if (maxR > R0) rs.add(maxR);
        cs.add(C0); for (int v : cpus) if (v > C0 && v <= maxC) cs.add(v); if (maxC > C0) cs.add(maxC);
        for (int v : rs) { TextView ch = Ui.chip(this, (v == R0 ? Ui.L("Giữ ", "Keep ") : "") + v + "GB", false); ch.setTag(v);
            ch.setOnClickListener(x -> { nr[0] = (int) x.getTag(); draw[0].run(); quote.run(); }); wr.addView(ch); }
        for (int v : cs) { TextView ch = Ui.chip(this, (v == C0 ? Ui.L("Giữ ", "Keep ") : "") + v + Ui.L(" nhân", " cores"), false); ch.setTag(v);
            ch.setOnClickListener(x -> { nc[0] = (int) x.getTag(); draw[0].run(); quote.run(); }); wc.addView(ch); }
        if (Api.SHOP) {
            pr[0] = new Promo(this, "cp_upgrade", () -> nr[0] == R0 && nc[0] == C0 ? null
                    : new JSONObject().put("p_phone", p.optString("id")).put("p_ram", nr[0]).put("p_cpu", nc[0]), () -> draw[0].run());
            pzu.addView(pr[0].view, Ui.fill());
        }
        Dialog d = Ui.sheet(this, "⬆️ " + Ui.L("Nâng cấp ", "Upgrade ") + p.optString("name"), c);
        ok.setOnClickListener(v -> { if (pr[0] == null) upgradeGo(d, ok, p, nr, nc, cost, null); else pr[0].ensure(() -> upgradeGo(d, ok, p, nr, nc, cost, pr[0])); });
        draw[0].run();
        d.show();
    }

    private void upgradeGo(Dialog d, Button ok, JSONObject p, int[] nr, int[] nc, long[] cost, Promo pr) {
        {
            double pay = pr == null ? cost[0] : pr.price(cost[0]);
            if (prof.optDouble("balance", 0) < pay) { d.dismiss(); openTopup(pay - prof.optDouble("balance", 0)); return; }
            final String code = pr == null ? null : pr.send();
            ok.setEnabled(false);
            Api.bg(() -> {
                JSONObject a = new JSONObject().put("p_id", p.optString("id")).put("p_ram", nr[0]).put("p_cpu", nc[0]);
                if (code != null) a.put("p_promo", code);
                try { return Api.rpc("cloudphone_upgrade", a); }
                catch (Exception e) { String m = String.valueOf(e.getMessage()); if (pr != null && m.contains("PROMO_")) Api.ui(() -> pr.fail(m)); throw e; }
            }, r -> {
                d.dismiss();
                Ui.toast(this, Ui.L("Đã nâng lên " + nr[0] + "GB · " + nc[0] + " nhân — máy nhận cấu hình mới trong giây lát.", "Upgraded to " + nr[0] + "GB · " + nc[0] + " cores."));
                refresh(); h.postDelayed(this::refresh, 5000);
            }, m -> {
                ok.setEnabled(true);
                Ui.toast(this, m.contains("UPGRADE_PENDING") ? Ui.L("Máy đang nâng cấp, đợi chút rồi thử lại.", "An upgrade is already in progress.")
                        : m.contains("FREE_NO_UPGRADE") ? Ui.L("Máy miễn phí không nâng cấp được.", "Free phones can't be upgraded.")
                        : m.contains("PHONE_NOT_ACTIVE") ? Ui.L("Máy phải đang chạy mới nâng cấp được.", "The phone must be running.") : m);
            });
        }
    }

    /** Số tiền máy chủ báo (cloudphone_upgrade_quote). Api.parse đọc số JSON thành Double (2122 → 2122.0): KHÔNG được bỏ ký tự
     *  không phải số rồi ghép lại (2122.0 → "21220" = gấp 10 lần — lỗi khách báo 12/11). Đọc không được → -1 (dùng giá tự tính). */
    static long quoteOf(Object r) {
        try {
            if (r instanceof Number) return Math.max(0, Math.round(((Number) r).doubleValue()));
            if (r != null) return Math.max(0, Math.round(Double.parseDouble(String.valueOf(r).trim())));
        } catch (Exception ignored) { }
        return -1;
    }

    /** Dòng cách tính cho khách tự kiểm: (phần THÊM × giá admin đặt cho 1GB RAM / 1 nhân mỗi ngày) × số ngày còn lại.
     *  Chưa đọc được bảng giá → "" (không đoán giá). Máy chủ vẫn là nơi tính và trừ tiền thật (cloudphone_upgrade). */
    String upgradeHow(JSONObject p, int nr, int nc) {
        if (!price.has("price_ram_gb_day") || !price.has("price_cpu_day")) return "";
        int dr = nr - p.optInt("ram"), dc = nc - p.optInt("cpu");
        StringBuilder s = new StringBuilder();
        if (dr > 0) s.append("+").append(dr).append("GB × ").append(Ui.vnd(price.optDouble("price_ram_gb_day", 0)));
        if (dc > 0) s.append(s.length() > 0 ? " + " : "").append("+").append(dc).append(Ui.L(" nhân × ", " cores × ")).append(Ui.vnd(price.optDouble("price_cpu_day", 0)));
        if (s.length() == 0) return "";
        double left = Math.max(0, (parseTime(p.optString("expires_at")) - System.currentTimeMillis()) / 86400000.0);
        String d = String.format(java.util.Locale.US, "%.1f", left);
        return Ui.L("Cách tính: (", "How: (") + s + Ui.L(")/ngày × ", ")/day × ") + Ui.L(d.replace('.', ','), d) + Ui.L(" ngày còn lại", " days left")
                + (isCtv() ? Ui.L(" · giảm CTV ", " · reseller −") + Math.round(prof.optDouble("ctv_discount", 0)) + "%" : "");
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
        if (RealPhone.isReal(p)) { RealPhone.giveBack(this, p); return; }     // 28/11: máy thật → "Trả máy sớm" (máy chủ dọn máy rồi trả cửa hàng)
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
        if (RealPhone.isReal(p)) {                      // 28/11 · SQL v70: 📱 máy THẬT — không nâng cấp / đổi Android / đổi FPS
            boolean canShare = ("active".equals(p.optString("status")) || "pending".equals(p.optString("status"))) && !locked(p);
            sh.setEnabled(canShare); sh.setAlpha(canShare ? 1f : .45f);
            Button back = Ui.button(this, "📤 " + Ui.L("Trả máy sớm (app, file của bạn sẽ bị xoá)", "Return early (your apps and files are erased)"), Ui.DANGER);
            c.addView(Ui.muted(this, RealPhone.limitsNote()), Ui.fill());
            c.addView(sh, Ui.fill()); c.addView(rn, Ui.fill()); c.addView(back, Ui.fill());
            Dialog d = Ui.sheet(this, p.optString("name"), c);
            sh.setOnClickListener(v -> { d.dismiss(); share(p); });
            rn.setOnClickListener(v -> { d.dismiss(); rename(p); });
            back.setOnClickListener(v -> { d.dismiss(); RealPhone.giveBack(this, p); });
            d.show();
            return;
        }
        Button up = Ui.button(this, "⬆️ " + Ui.L("Nâng cấp RAM / CPU", "Upgrade RAM / CPU"), Ui.GHOST);
        boolean canUp = "active".equals(p.optString("status")) && !locked(p) && !p.optBoolean("is_free") && !p.optBoolean("shared");
        up.setEnabled(canUp); up.setAlpha(canUp ? 1f : .45f);
        boolean canShare = ("active".equals(p.optString("status")) || "pending".equals(p.optString("status"))) && !locked(p);
        sh.setEnabled(canShare); sh.setAlpha(canShare ? 1f : .45f);
        boolean swing = SwitchAndroid.switching(p, phones) != null;
        Button sw = Ui.button(this, "🤖 " + (swing ? Ui.L("Đang đổi Android… (chờ máy mới)", "Switching Android… (wait for the new phone)")
                : Ui.L("Đổi Android / máy chủ", "Switch Android / server")), Ui.GHOST);
        boolean canSw = "active".equals(p.optString("status")) && !locked(p) && !p.optBoolean("shared") && !swing && !andList().isEmpty();   // SQL v67: còn 1 bản vẫn đổi máy chủ được
        sw.setEnabled(canSw); sw.setAlpha(canSw ? 1f : .45f);
        Button del = Ui.button(this, "🗑 " + Ui.L("Huỷ máy (xoá vĩnh viễn)", "Delete phone"), Ui.DANGER);
        final int fpsNow = p.optInt("fps", 30);          // 16/11: khách tự đổi FPS máy đang thuê (không tạo máy mới, không tốn tiền)
        Button fp = Ui.button(this, "🎞 " + Ui.L("Đổi FPS (đang " + fpsNow + " FPS)", "Change FPS (now " + fpsNow + ")"), Ui.GHOST);
        boolean canFps = "active".equals(p.optString("status")) && !locked(p) && !p.optBoolean("shared") && !swing;
        fp.setEnabled(canFps); fp.setAlpha(canFps ? 1f : .45f);
        if (Api.SHOP) c.addView(up, Ui.fill());        // nâng cấp (trả bằng số dư)
        c.addView(fp, Ui.fill());
        c.addView(sw, Ui.fill()); c.addView(sh, Ui.fill()); c.addView(rn, Ui.fill()); c.addView(del, Ui.fill());
        Dialog d = Ui.sheet(this, p.optString("name"), c);
        fp.setOnClickListener(v -> { d.dismiss(); changeFps(p); });
        sw.setOnClickListener(v -> { d.dismiss(); SwitchAndroid.open(this, p, price, status, isAdmin(), () -> { phonesSig = null; refresh(); h.postDelayed(this::refresh, 5000); }); });
        del.setOnClickListener(v -> { d.dismiss(); cancelPhone(p); });
        up.setOnClickListener(v -> { d.dismiss(); upgrade(p); });
        sh.setOnClickListener(v -> { d.dismiss(); share(p); });
        rn.setOnClickListener(v -> { d.dismiss(); rename(p); });
        d.show();
    }

    // ---------------- 16/11 · KHÁCH TỰ ĐỔI FPS (SQL doi-fps-1611 → cloudphone_set_fps) ----------------
    static final int[] FPS_PICK = {15, 20, 30, 45, 60, 90, 120};
    static String fpsTip(int f) {
        return f < 20 ? Ui.L("tiết kiệm nhất", "lightest") : f < 30 ? Ui.L("mạng yếu", "weak network") : f <= 30 ? Ui.L("treo game", "idling")
                : f <= 45 ? Ui.L("cân bằng", "balanced") : f <= 60 ? Ui.L("mượt", "smooth") : Ui.L("rất mượt", "very smooth");
    }

    /** Đổi FPS của máy đang thuê: cùng máy đó, giữ nguyên dữ liệu, không tốn tiền. Hình truyền về đổi ở lần mở máy kế tiếp;
     *  máy Android 12 · 15 cần khởi động lại 1 lần để FPS mới có tác dụng trong game (máy chủ trả reboot = true → hỏi khách). */
    void changeFps(JSONObject p) {
        final String pid = p.optString("id");
        final int cur = p.optInt("fps", 30), lo = price.optInt("min_fps", 10), hi = Math.min(price.optInt("max_fps", 60), p.optInt("cpu") < 4 ? 60 : 120);
        final int[] pick = {cur};
        LinearLayout c = Ui.col(this, 12);
        String av = p.optString("android", "").trim();
        c.addView(Ui.muted(this, "📱 " + p.optString("name") + (av.isEmpty() || "null".equals(av) ? "" : " · Android " + av) + " · " + p.optInt("ram") + "GB · "
                + p.optInt("cpu") + Ui.L(" nhân · đang dùng ", " cores · now ") + cur + " FPS"), Ui.fill());
        final Ui.Wrap w = new Ui.Wrap(this, 8);
        java.util.TreeSet<Integer> opts = new java.util.TreeSet<>();
        for (int x : FPS_PICK) if (x >= lo && x <= hi) opts.add(x);
        opts.add(cur);
        final Button ok = Ui.button(this, "", Ui.PRIMARY);
        final TextView err = Ui.text(this, "", 13, Ui.BAD, false);
        err.setVisibility(View.GONE);
        final boolean[] busy = {false};
        final Runnable draw = () -> {
            for (int i = 0; i < w.getChildCount(); i++) Ui.setChip((TextView) w.getChildAt(i), (int) w.getChildAt(i).getTag() == pick[0]);
            boolean ch = pick[0] != cur && !busy[0];
            ok.setText(busy[0] ? Ui.L("Đang lưu…", "Saving…") : pick[0] != cur ? Ui.L("Lưu " + pick[0] + " FPS", "Save " + pick[0] + " FPS") : Ui.L("Chọn số FPS khác để đổi", "Pick a different FPS"));
            ok.setEnabled(ch); ok.setAlpha(ch ? 1f : .45f);
        };
        for (int x : opts) {
            TextView ch = Ui.chip(this, x + " FPS\n" + fpsTip(x), false);
            ch.setTextSize(Ui.sp(13));
            ch.setTag(x);
            ch.setOnClickListener(v -> { if (busy[0]) return; pick[0] = (int) v.getTag(); err.setVisibility(View.GONE); draw.run(); });
            w.addView(ch);
        }
        c.addView(w, Ui.fill());
        c.addView(Ui.muted(this, Ui.L("FPS càng cao hình càng mượt nhưng máy chạy nặng hơn và tốn mạng hơn. Treo game cả ngày nên để 30 FPS (mạng yếu: 20 FPS).",
                "Higher FPS looks smoother but loads the phone and your network more. For idling all day use 30 FPS (weak network: 20 FPS).")
                + (p.optInt("cpu") < 4 ? " " + Ui.L("Máy dưới 4 nhân chọn tối đa 60 FPS.", "Phones under 4 cores go up to 60 FPS.") : "")), Ui.fill());
        c.addView(Ui.muted(this, "✔ " + Ui.L("Không tạo máy mới · không mất dữ liệu · không tốn tiền.", "Same phone · data kept · free.")), Ui.fill());
        c.addView(err, Ui.fill());
        c.addView(ok, Ui.fill());
        final Dialog d = Ui.sheet(this, "🎞 " + Ui.L("Đổi FPS", "Change FPS"), c);
        ok.setOnClickListener(v -> {
            final int want = pick[0];
            if (want == cur || busy[0]) return;
            busy[0] = true; draw.run();
            Api.bg(() -> Api.rpc("cloudphone_set_fps", new JSONObject().put("p_id", pid).put("p_fps", want)), r -> {
                busy[0] = false;
                try { d.dismiss(); } catch (Exception ignored) { }
                if (destroyed) return;
                try { p.put("fps", want); } catch (Exception ignored) { }
                phonesSig = null; refresh();
                JSONObject j = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                if (j.optBoolean("reboot", false)) fpsReboot(p, want);
                else Ui.toast(this, Ui.L("Đã đổi sang " + want + " FPS — mở lại màn hình máy là thấy.", "Changed to " + want + " FPS — reopen the phone screen to see it."));
            }, m -> { busy[0] = false; err.setText(m); err.setVisibility(View.VISIBLE); draw.run(); });
        });
        draw.run();
        d.show();
    }

    /** Đã lưu FPS mới mà máy cần khởi động lại 1 lần (Android 12 · 15) → khách chọn: khởi động lại ngay, hay để sau (lần bật kế tiếp tự áp dụng). */
    void fpsReboot(JSONObject p, int fps) {
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.text(this, "✅ " + Ui.L("Đã lưu " + fps + " FPS. Hình truyền về đổi ngay ở lần mở máy kế tiếp.",
                "Saved " + fps + " FPS. The picture you see changes the next time you open the phone."), 14.5f, Ui.OK, true), Ui.fill());
        c.addView(Ui.muted(this, Ui.L("Để FPS mới có tác dụng BÊN TRONG GAME, máy cần khởi động lại 1 lần (khoảng 1–2 phút). App đang mở trong máy sẽ tắt, dữ liệu giữ nguyên. Chưa tiện thì để sau — lần máy bật lại kế tiếp sẽ tự áp dụng.",
                "For the new FPS to apply INSIDE GAMES the phone must restart once (about 1–2 minutes). Apps running on the phone will close; your data is kept. Not now? It applies by itself the next time the phone starts.")), Ui.fill());
        final TextView st = Ui.text(this, "", 13.5f, Ui.SKY, false);
        st.setVisibility(View.GONE);
        c.addView(st, Ui.fill());
        LinearLayout r = Ui.row(this, 10);
        final Button later = Ui.button(this, Ui.L("Để sau", "Later"), Ui.GHOST), now = Ui.button(this, "⚡ " + Ui.L("Khởi động lại ngay", "Restart now"), Ui.PRIMARY);
        r.addView(later, Ui.weight(1));
        r.addView(now, Ui.weight(1.6f));
        c.addView(r, Ui.fill());
        final Dialog d = Ui.sheet(this, "🎞 " + Ui.L("Đổi FPS", "Change FPS"), c);
        later.setOnClickListener(v -> d.dismiss());
        now.setOnClickListener(v -> {
            // 16/11c: KHỞI ĐỘNG LẠI CHẠY NGẦM — đóng hộp ngay, thẻ máy hiện "🔄 Đang khởi động lại…"; khách thoát app vẫn được,
            // xong mà không mở app → thông báo (Reboots). Kết quả báo bằng toast (rbWatch) khi đang mở app.
            d.dismiss();
            Ui.toast(this, "🔄 " + Ui.L("Đang khởi động lại máy (1–2 phút). Cứ thoát app — máy vẫn tự khởi động, xong sẽ có thông báo.",
                    "Restarting the phone (1–2 minutes). You can leave the app — it keeps restarting and you'll get a notification."));
            rebootPhone(p.optString("id"), p.optString("name"), null, null, null);
        });
        d.show();
    }

    /** Khởi động lại 1 máy từ danh sách: hỏi máy đang ở máy chủ nào (cloudphone_endpoint) → POST …/reboot → chờ máy chủ làm xong.
     *  step = câu tiến độ máy chủ báo · done = câu kết quả · fail = câu lỗi (đã dễ hiểu). */
    void rebootPhone(String pid, String name, Api.Cb<String> step, Api.Cb<String> done, Api.Err fail) {
        Reboots.start(this, pid, name, null, step, done, fail);          // 16/11c: theo dõi ở Reboots (không gắn với màn này)
        phonesSig = null;
        if (tab == 0) renderPhones();
    }

    /** (cũ, giữ để đối chiếu — không dùng nữa) */
    void rebootPhoneOld(String pid, Api.Cb<String> step, Api.Cb<String> done, Api.Err fail) {
        Api.bgLong(() -> {
            Object o = Api.rpc("cloudphone_endpoint", new JSONObject().put("p_id", pid));
            JSONObject ep = o instanceof JSONObject ? (JSONObject) o : new JSONObject(), s = ep.optJSONObject("stream");
            String a = s == null || s.isNull("api") ? "" : s.optString("api", "").trim();
            final String base = a.startsWith("https://") ? a : "";
            Api.direct(base, s);
            JSONObject j = Api.cpAt(base, "POST", pid + "/reboot", new JSONObject());
            String job = j.optString("job", "");
            if (job.isEmpty()) return Ui.L("Máy đang khởi động lại — khoảng 1–2 phút.", "The phone is restarting — about 1–2 minutes.");
            int miss = 0;
            for (int i = 0; i < 200; i++) {                                    // tối đa ~5 phút
                Thread.sleep(1500);
                JSONObject q;
                try { q = Api.cpAt(base, "GET", "job?id=" + job, null); miss = 0; }
                catch (Exception e) { if (++miss >= 8) throw e; continue; }    // mạng chập chờn lúc hỏi → hỏi lại
                String stt = q.optString("state"), msg = q.optString("msg");
                if ("done".equals(stt)) return msg.isEmpty() ? Ui.L("Máy đã khởi động lại xong.", "The phone has restarted.") : msg;
                if ("error".equals(stt)) throw new Exception(msg.isEmpty() ? Ui.L("máy chủ báo lỗi", "server error") : msg);
                if (!msg.isEmpty() && step != null) Api.ui(() -> step.ok(msg));
            }
            return Ui.L("Máy vẫn đang khởi động — mở máy sau ít phút.", "Still restarting — open the phone in a few minutes.");
        }, done, fail);
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
    /** 3 bước giống web: ① hệ điều hành (ô to, chia đều) · ② chọn gói (danh sách dọc gọn) · ③ số ngày & số máy.
     *  CHƯA chọn gói thì KHÔNG hiện số tiền — thanh dưới chỉ nhắc "Chọn gói" (bấm → cuộn tới bước 2). */
    void renderRent() {
        final int keepY = tab == 1 && rentSv != null && rentSv.getParent() != null ? rentSv.getScrollY() : 0;   // chọn gói / đổi bản → giữ chỗ đang cuộn
        LinearLayout body = Ui.col(this, 14);
        body.addView(Ui.h1(this, Ui.L("Thuê điện thoại đám mây", "Rent a cloud phone")), Ui.fill());
        if (isAdmin() && status.optBoolean("maint", false))
            body.addView(Ui.text(this, Ui.L("⚠ Đang bật BẢO TRÌ — khách không thuê được. Tài khoản admin vẫn thuê được để thử máy.",
                    "⚠ Maintenance is ON — customers can't rent. Admin can still rent to test."), 13, Ui.WAIT, true), Ui.fill());
        body.addView(Ui.muted(this, Ui.L("3 bước: chọn hệ điều hành → chọn gói → số ngày. Máy mới tinh, có Play Store.",
                "3 steps: Android version → plan → days. Fresh device with Play Store.")), Ui.fill());
        promo(body, false);                         // 🎡 vòng quay may mắn — dải gọn, bấm là mở · khách ẩn / hiện được (16/11)
        if (Api.SHOP) {                             // 28/11 · SQL v70: 📱 BlueReal — thuê điện thoại THẬT (admin mở bán ≥ 1 mẫu máy)
            if (RealPhone.on()) body.addView(RealPhone.card(this), Ui.fill());
            if (System.currentTimeMillis() - RealPhone.at > 60_000L) RealPhone.load(this::realChanged);
        }

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
            rentSv = page(body);
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
        final LinearLayout aw = Ui.row(this, 8);                 // ô hệ điều hành chia đều 1 hàng
        final TextView andTip = Ui.text(this, "", 12.5f, Ui.WAIT, false);

        TextView total = Ui.text(this, "", 22, Ui.MONEY, true);
        TextView calc = Ui.text(this, "", 11.5f, Ui.MUTED, false);
        calc.setMaxLines(3);
        final TextView sumL = Ui.text(this, "", 12, Ui.MUTED, true);    // "Blue Plus · Android 9 · 7 ngày" / "Chưa chọn gói"
        sumL.setMaxLines(1);
        sumL.setEllipsize(android.text.TextUtils.TruncateAt.END);
        final Promo[] prm = new Promo[1];                // 🏷️ mã giảm giá (SQL v23) · 💎 trả bằng Blue (SQL v27) — bản web
        final Blue.Pay[] bp = new Blue.Pay[1];
        final View[] pzBox = new View[1];
        TextView err = Ui.text(this, "", 12.5f, Ui.BAD, false);
        Button buy = Ui.button(this, "", Ui.PRIMARY);

        // 🎴 gói cấu hình (cùng danh sách với web) — máy miễn phí không dùng gói
        final java.util.List<Tiers.T> tl = sFree ? new java.util.ArrayList<Tiers.T>() : Tiers.list();
        final java.util.List<Tiers.Card> tcs = new java.util.ArrayList<>();
        final TextView[] csum = new TextView[1];
        final boolean[] need = new boolean[1];

        Runnable upd = () -> {
            need[0] = !sFree && !rentPicked && !tl.isEmpty();      // còn gói mà khách chưa chọn → chưa hiện số tiền nào
            for (int i = 0; i < tcs.size(); i++) tcs.get(i).setOn(tierOn(tl.get(i), minR, minC, minF, maxF));
            if (csum[0] != null) csum[0].setText(need[0] ? "" : sRam + "GB · " + sCpu + Ui.L(" nhân · ", " cores · ") + sRes + " · " + sFps + " FPS");
            paintAndTiles(aw);
            andTip.setVisibility("15".equals(sAnd) ? View.VISIBLE : View.GONE);
            if (pzBox[0] != null) pzBox[0].setVisibility(sFree || need[0] ? View.GONE : View.VISIBLE);
            if (need[0]) {
                sumL.setText(Ui.L("Chưa chọn gói", "No plan yet"));
                total.setTextSize(Ui.sp(15));
                total.setText(Ui.L("Chọn 1 gói ở bước 2 để xem giá", "Pick a plan in step 2 to see the price"));
                calc.setVisibility(View.GONE);
                err.setVisibility(View.GONE);
                buy.setText(Ui.L("Chọn gói", "Pick a plan"));
                buy.setEnabled(true);
                buy.setAlpha(1f);
                return;
            }
            total.setTextSize(Ui.sp(22));
            calc.setVisibility(View.VISIBLE);
            Tiers.T cur = null;
            for (int i = 0; i < tl.size(); i++) if (tierOn(tl.get(i), minR, minC, minF, maxF)) { cur = tl.get(i); break; }
            sumL.setText((sFree ? Offers.freeName(price) : cur != null ? cur.name : Ui.L("⚙️ Tự chọn", "⚙️ Custom"))
                    + " · Android " + sAnd + " · " + (sFree ? Offers.dur(price) : sDays + Ui.L(" ngày", "d")) + (!sFree && sQty > 1 ? " × " + sQty + Ui.L(" máy", "") : ""));
            double t0 = sFree ? 0 : ctv(perDay(sRam, sCpu) * sDays) * sQty, bal = prof.optDouble("balance", 0);
            if (prm[0] != null) { prm[0].view.setVisibility(sFree ? View.GONE : View.VISIBLE); rentPromo = prm[0].code; if (!sFree) prm[0].onOrderChanged(); }
            double pay = sFree || prm[0] == null ? t0 : prm[0].price(t0);
            long bu = sFree || bp[0] == null ? 0 : bp[0].use(pay);
            if (bp[0] != null) bp[0].paint(pay, sFree);
            double t = pay - bu;
            total.setText(Ui.vnd(t));
            calc.setText("(" + sRam + "GB × " + Ui.vnd(price.optDouble("price_ram_gb_day", 2500)) + " + " + sCpu + Ui.L(" nhân × ", " cores × ")
                    + Ui.vnd(price.optDouble("price_cpu_day", 2000)) + ") × " + sDays + Ui.L(" ngày", " days")
                    + (isCtv() ? " − " + prof.optInt("ctv_discount") + "% CTV" : "") + (sQty > 1 ? " × " + sQty + Ui.L(" máy", " phones") : "")
                    + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal)
                    + (pay < t0 ? "  ·  🏷️ −" + Ui.vnd(t0 - pay) : "") + (bu > 0 ? "  ·  💎 −" + Blue.n(bu) + " Blue" : ""));
            String bad = check();
            err.setText(bad.isEmpty() && bal < t ? Ui.L("Số dư không đủ — cần nạp thêm ", "Not enough balance — top up ") + Ui.vnd(t - bal) : bad);
            if (sFree) calc.setText(Ui.L("🎁 Dùng thử miễn phí " + Offers.dur(price), "🎁 Free trial · " + Offers.dur(price)) + "\n" + Ui.L("Số dư: ", "Balance: ") + Ui.vnd(bal));
            buy.setText(sFree ? Offers.freeBtn(price) : bad.isEmpty() && bal < t ? Ui.L("Nạp tiền", "Top up")
                    : t <= 0 && bu > 0 ? Ui.L("💎 Thuê bằng Blue", "💎 Rent with Blue") : Ui.L("Thuê ngay", "Rent now") + (sQty > 1 ? " " + sQty + Ui.L(" máy", " phones") : ""));
            buy.setEnabled(bad.isEmpty());
            buy.setAlpha(bad.isEmpty() ? 1f : .5f);
            err.setVisibility(err.getText().length() == 0 ? View.GONE : View.VISIBLE);
        };

        // 🎁 Miễn phí ưu đãi (khi admin bật)
        if (freeLive()) {
            LinearLayout fc = Ui.card(this);
            TextView fch = Ui.chip(this, Offers.freeTitle(price), sFree);
            fc.addView(fch, Ui.fill());
            fc.addView(Ui.muted(this, Offers.freeNote(price)));
            if (Offers.trialNeedsTopup(price, isAdmin())) {          // chưa nạp đủ → nói rõ + nút nạp đúng số tiền
                final long nd = Offers.need(price);
                fc.addView(Ui.text(this, "🔒 " + Ui.L("Nạp 1 lần từ " + Ui.vnd(nd) + " để mở dùng thử miễn phí.", "Top up " + Ui.vnd(nd) + "+ once to unlock the free trial."), 13, Ui.WAIT, true), Ui.fill());
                Button tb = Ui.button(this, Ui.L("Nạp ", "Top up ") + Ui.vnd(nd), Ui.GHOST);
                tb.setOnClickListener(v -> openTopup(nd));
                fc.addView(tb, Ui.fill());
            }
            fch.setOnClickListener(v -> { sFree = !sFree; if (sFree) { sQty = 1; sRam = Math.min(sRam, price.optInt("free_max_ram", 4)); sCpu = Math.min(sCpu, price.optInt("free_max_cpu", 4)); } renderRent(); });
            body.addView(fc, Ui.fill());
        }

        // ① Hệ điều hành — ô to, bấm là chọn
        LinearLayout s1 = Ui.col(this, 12);
        s1.addView(stepHead("1", Ui.L("Chọn hệ điều hành", "Choose Android version"),
                avs.size() > 1 && avs.contains("9") ? Ui.L("Chưa chắc thì chọn Android 9 — ổn định, chạy được nhiều app nhất.", "Not sure? Android 9 is the most stable and runs the most apps.") : ""), Ui.fill());
        for (String v : avs) {
            FrameLayout tile = andTile(v);
            tile.setOnClickListener(x -> {
                if (!andWhy((String) x.getTag()).isEmpty()) return;      // bản đang bảo trì / hết chỗ
                String nv = (String) x.getTag();
                int[] a0 = andLim(sAnd), a1 = andLim(nv);
                sAnd = nv;
                if (a0[0] != a1[0] || a0[1] != a1[1]) { sRam = Math.min(sRam, a1[0]); sCpu = Math.min(sCpu, a1[1]); renderRent(); }   // trần khác → vẽ lại danh sách RAM/CPU
                else upd.run();
            });
            aw.addView(tile, new LinearLayout.LayoutParams(0, Ui.dp(88), 1));
        }
        s1.addView(aw, Ui.fill());
        if (avs.contains("15")) {                        // khách báo Android 15 có máy không vào được Google → chỉ cách chọn / đổi sang 12
            andTip.setText(Ui.L("💡 Android 15 không vào được Google / Play Store? Chọn Android 12. Máy đang thuê thì vào ⋯ → 🤖 Đổi Android (giữ nguyên hạn, miễn phí).",
                    "💡 Google / Play Store not working on Android 15? Pick Android 12. For a phone you already rent: ⋯ → 🤖 Switch Android (same expiry, free)."));
            s1.addView(andTip, Ui.fill());
        }
        body.addView(boxed(s1), Ui.fill());

        // ② Chọn gói — danh sách dọc: bấm hàng nào chọn hàng đó, hàng đang chọn mở thêm chi tiết · ⚙️ Tự chỉnh ngay dưới
        LinearLayout s2 = Ui.col(this, 10);
        boolean hasT = !tl.isEmpty();
        s2.addView(stepHead("2", sFree ? Ui.L("Cấu hình máy miễn phí", "Free phone setup") : hasT ? Ui.L("Chọn gói", "Choose a plan") : Ui.L("Cấu hình máy", "Phone setup"),
                sFree ? Ui.L("Tối đa " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " nhân — để mặc định là dùng được.",
                        "Up to " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " cores — the defaults work fine.")
                        : hasT ? Ui.L("Bấm 1 gói để xem giá — muốn khác thì tự chỉnh ở dưới.", "Tap a plan to see the price — or customize below.")
                        : Ui.L("Chọn RAM · CPU · FPS cho máy.", "Pick RAM · CPU · FPS.")), Ui.fill());
        for (int i = 0; i < tl.size(); i++) {
            final Tiers.T t = tl.get(i);
            final java.util.List<String> ands = new java.util.ArrayList<>(), busy = new java.util.ArrayList<>();
            for (String v : avs) { int[] l2 = andLim(v); if (t.ram <= l2[0] && t.cpu <= l2[1]) { ands.add(v); if (!andWhy(v, t.ram, t.cpu).isEmpty()) busy.add(v); } }
            Tiers.Card cd = new Tiers.Card(this, t, perDay(t.ram, t.cpu), ands, busy, ands.size() < avs.size() || !busy.isEmpty(), () -> pickTier(t, ands, busy));
            tcs.add(cd);
            s2.addView(cd.view, Ui.fill());
        }
        final LinearLayout cust = Ui.col(this, 14);
        boolean anyTier = false;
        for (Tiers.T t : tl) if (tierMatch(t, minR, minC, minF, maxF)) { anyTier = true; break; }
        if (tl.isEmpty() || (rentPicked && !anyTier)) rentCustom = true;
        if (hasT) {
            LinearLayout ch = Ui.row(this, 8);
            ch.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(12));
            ch.setBackground(Ui.round(Ui.LIGHT ? Ui.SUNK : Color.argb(20, 255, 255, 255), 14, Ui.LINE2));
            ch.addView(Ui.text(this, "⚙️ " + Ui.L("Tự chỉnh cấu hình", "Customize"), 14, Ui.FG, true), Ui.wrap());
            csum[0] = Ui.text(this, "", 12, Ui.SKY, true);
            csum[0].setMaxLines(1);
            csum[0].setEllipsize(android.text.TextUtils.TruncateAt.END);
            ch.addView(csum[0], Ui.weight(1));
            final TextView arw = Ui.text(this, rentCustom ? "▴" : "▾", 16, Ui.MUTED, true);
            ch.addView(arw, Ui.wrap());
            ch.setClickable(true);
            ch.setOnClickListener(v -> { rentCustom = !rentCustom; cust.setVisibility(rentCustom ? View.VISIBLE : View.GONE); arw.setText(rentCustom ? "▴" : "▾"); });
            s2.addView(ch, Ui.fill());
        }
        cust.setVisibility(rentCustom ? View.VISIBLE : View.GONE);
        cust.addView(group(Ui.L("RAM", "RAM"), RAM, minR, maxR, "GB", v -> { sRam = v; rentPicked = true; upd.run(); }, () -> sRam), Ui.fill());
        cust.addView(group(Ui.L("CPU (nhân)", "CPU cores"), CPU, minC, maxC, "", v -> { sCpu = v; rentPicked = true; upd.run(); }, () -> sCpu), Ui.fill());
        cust.addView(group("FPS", FPS, minF, maxF, "", v -> { sFps = v; rentPicked = true; upd.run(); }, () -> sFps), Ui.fill());
        LinearLayout rc = Ui.col(this, 8);                // Độ phân giải
        rc.addView(Ui.text(this, Ui.L("Độ phân giải", "Resolution"), 14, Ui.MUTED, true));
        Ui.Wrap rw = new Ui.Wrap(this, 8);
        for (String[] r : RES) {
            TextView ch = Ui.chip(this, Ui.L(r[1], "Nhẹ máy".equals(r[1]) ? "Light" : "HD+ dài".equals(r[1]) ? "HD+ tall" : r[1]) + "\n" + r[0], r[0].equals(sRes));
            ch.setTextSize(Ui.sp(13));
            ch.setTag(r[0]);
            ch.setOnClickListener(v -> {
                sRes = (String) v.getTag();
                rentPicked = true;
                for (int i = 0; i < rw.getChildCount(); i++) Ui.setChip((TextView) rw.getChildAt(i), rw.getChildAt(i).getTag().equals(sRes));
                upd.run();
            });
            rw.addView(ch);
        }
        rc.addView(rw, Ui.fill());
        cust.addView(rc, Ui.fill());
        s2.addView(cust, Ui.fill());
        final View step2 = boxed(s2);
        body.addView(step2, Ui.fill());

        // ③ Số ngày & số máy (máy miễn phí: số ngày cố định, 1 máy → bỏ bước này)
        if (!sFree) {
            LinearLayout s3 = Ui.col(this, 14);
            s3.addView(stepHead("3", left > 1 ? Ui.L("Số ngày & số máy", "Days & phones") : Ui.L("Số ngày thuê", "Rental days"), ""), Ui.fill());
            s3.addView(group(Ui.L("Số ngày", "Days"), DAYS, minD, maxD, Ui.L(" ngày", "d"), v -> { sDays = v; upd.run(); }, () -> sDays), Ui.fill());
            if (left > 1) s3.addView(group(Ui.L("Số lượng máy", "Quantity"), QTY, 1, Math.min(20, left), Ui.L(" máy", ""), v -> { sQty = v; upd.run(); }, () -> sQty), Ui.fill());
            body.addView(boxed(s3), Ui.fill());
        }

        // 🏷️ Mã giảm giá + 💎 Trả bằng Blue (máy miễn phí không dùng mã / Blue · chưa chọn gói thì ẩn)
        if (Api.SHOP) {
            prm[0] = new Promo(this, "cp_new", () -> sFree ? null : new JSONObject().put("p_ram", sRam).put("p_cpu", sCpu).put("p_days", sDays).put("p_qty", sQty), upd);
            bp[0] = new Blue.Pay(this, bluePayRent, () -> { bluePayRent = bp[0].on; upd.run(); });
            LinearLayout pz = Ui.col(this, 10);
            pz.addView(prm[0].view, Ui.fill());
            pz.addView(bp[0].view, Ui.fill());
            pzBox[0] = boxed(pz);
            body.addView(pzBox[0], Ui.fill());
            if (!rentPromo.isEmpty()) { prm[0].in.setText(rentPromo); prm[0].check(null); }
        }

        // Thanh dưới màn hình: gói đang chọn + tổng tiền + nút — chưa chọn gói thì chỉ nhắc chọn gói
        LinearLayout sum = Ui.col(this, 6);
        sum.setPadding(Ui.dp(16), Ui.dp(10), Ui.dp(10), Ui.dp(10));
        android.graphics.drawable.GradientDrawable sbg = new android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
                Ui.LIGHT ? new int[]{Color.WHITE, Color.rgb(238, 244, 255)} : new int[]{Color.rgb(22, 44, 104), Color.rgb(9, 19, 50)});
        sbg.setCornerRadius(Ui.dp(Ui.rad(20)));
        sbg.setStroke(Math.max(2, Ui.dp(1.5f)), Ui.LIGHT ? Color.argb(80, 43, 110, 240) : Color.argb(120, 124, 188, 255));
        sum.setBackground(sbg);
        sum.setElevation(Ui.dp(10));
        sum.addView(err, Ui.fill());
        LinearLayout sr = Ui.row(this, 10);
        LinearLayout st = Ui.col(this, 0);
        st.addView(sumL);
        st.addView(total);
        st.addView(calc);
        sr.addView(st, Ui.weight(1));
        buy.setMinWidth(Ui.dp(124));
        sr.addView(buy, Ui.wrap());
        sum.addView(sr, Ui.fill());

        final ScrollView[] svr = new ScrollView[1];
        buy.setOnClickListener(v -> {
            if (need[0]) {                               // chưa chọn gói → cuộn tới bước 2
                if (svr[0] != null) svr[0].smoothScrollTo(0, Math.max(0, step2.getTop() - Ui.dp(8)));
                return;
            }
            Runnable go = () -> {
                double t0 = sFree ? 0 : ctv(perDay(sRam, sCpu) * sDays) * sQty;
                double pay = sFree || prm[0] == null ? t0 : prm[0].price(t0);
                long bu = sFree || bp[0] == null ? 0 : bp[0].use(pay);
                double t = pay - bu;
                if (prof.optDouble("balance", 0) < t) { openTopup(t - prof.optDouble("balance", 0)); return; }
                final String code = sFree || prm[0] == null ? null : prm[0].send();
                Ui.confirm(this, Ui.L("Xác nhận thuê máy", "Confirm"),
                        "Android " + sAnd + " · " + sQty + Ui.L(" máy · ", " phone(s) · ") + sRam + "GB · " + sCpu + Ui.L(" nhân · ", " cores · ") + sDays + Ui.L(" ngày · ", " days · ") + sRes + " · " + sFps + " FPS\n"
                                + (code != null ? "🏷️ " + code + "  −" + Ui.vnd(t0 - pay) + "\n" : "")
                                + (bu > 0 ? "💎 " + Ui.L("Trả ", "Pay ") + Blue.n(bu) + " Blue\n" : "")
                                + Ui.L("Trừ ", "Charge ") + Ui.vnd(t) + Ui.L(" từ số dư.", " from balance."),
                        Ui.L("Thanh toán", "Pay"), () -> order(buy, code, bu > 0, prm[0]));
            };
            if (sFree || prm[0] == null) go.run(); else prm[0].ensure(go);
        });
        rentUpd = upd;
        upd.run();
        body.setTag("rent");
        final ScrollView sv = page(body);
        svr[0] = sv;
        rentSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
        body.setPadding(body.getPaddingLeft(), body.getPaddingTop(), body.getPaddingRight(), Ui.dp(150));
        FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        blp.setMargins(Ui.dp(10), 0, Ui.dp(10), Ui.dp(8));
        content.addView(sum, blp);
    }

    /** Đầu mỗi bước: số tròn xanh bóng + tiêu đề + 1 dòng gợi ý (giống web). */
    View stepHead(String n, String title, String sub) {
        LinearLayout r = Ui.row(this, 10);
        r.setGravity(Gravity.CENTER_VERTICAL);
        TextView b = Ui.text(this, n, 14, Ui.LIGHT ? Color.WHITE : Color.rgb(4, 18, 46), true);
        b.setGravity(Gravity.CENTER);
        android.graphics.drawable.GradientDrawable g = new android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
                Ui.LIGHT ? new int[]{Color.rgb(91, 152, 255), Color.rgb(31, 95, 224)} : new int[]{Color.rgb(227, 241, 255), Color.rgb(159, 208, 255), Color.rgb(61, 123, 255)});
        g.setShape(android.graphics.drawable.GradientDrawable.OVAL);
        b.setBackground(g);
        r.addView(b, new LinearLayout.LayoutParams(Ui.dp(28), Ui.dp(28)));
        LinearLayout t = Ui.col(this, 1);
        t.addView(Ui.text(this, title, 16.5f, Ui.FG, true));
        if (sub != null && !sub.isEmpty()) t.addView(Ui.text(this, sub, 12.5f, Ui.MUTED, false));
        r.addView(t, Ui.weight(1));
        return r;
    }

    /** 1 ô hệ điều hành: "Android" nhỏ · số bản TO · gợi ý ngắn. Màu / dấu ✓ vẽ ở paintAndTiles. */
    private FrameLayout andTile(String v) {
        FrameLayout f = new FrameLayout(this);
        f.setTag(v);
        f.setClickable(true);
        f.setFocusable(true);
        f.setContentDescription("Android " + v);
        LinearLayout c = Ui.col(this, 0);
        c.setGravity(Gravity.CENTER);
        c.setPadding(Ui.dp(2), Ui.dp(6), Ui.dp(2), Ui.dp(6));
        TextView k = Ui.text(this, "Android", 12, Ui.MUTED, true);
        TextView n = Ui.text(this, v, 28, Ui.FG, true);
        TextView h = Ui.text(this, "", 11, Ui.WAIT, true);
        for (TextView x : new TextView[]{k, n, h}) { x.setGravity(Gravity.CENTER); x.setMaxLines(1); }
        n.setIncludeFontPadding(false);
        c.addView(k, Ui.fill());
        c.addView(n, Ui.fill());
        c.addView(h, Ui.fill());
        f.addView(c, new FrameLayout.LayoutParams(-1, -1));
        return f;
    }

    /** Tô lại các ô hệ điều hành theo bản đang chọn + chỗ trống (đổi RAM/CPU là cập nhật ngay). */
    void paintAndTiles(LinearLayout aw) {
        if (!andList().contains(sAnd) || "off".equals(andWhy(sAnd))) {         // bản đang chọn bảo trì → tự đổi (hết chỗ thì giữ, báo lỗi để khách chọn lại)
            sAnd = andPick(); int[] l = andLim(sAnd); sRam = Math.min(sRam, l[0]); sCpu = Math.min(sCpu, l[1]);
        }
        for (int i = 0; i < aw.getChildCount(); i++) {
            if (!(aw.getChildAt(i) instanceof FrameLayout)) continue;
            FrameLayout f = (FrameLayout) aw.getChildAt(i);
            LinearLayout c = (LinearLayout) f.getChildAt(0);
            TextView k = (TextView) c.getChildAt(0), n = (TextView) c.getChildAt(1), hn = (TextView) c.getChildAt(2);
            String v = (String) f.getTag(), why = andWhy(v);
            boolean on = v.equals(sAnd), ok = why.isEmpty();
            String hint = "off".equals(why) ? Ui.L("Bảo trì", "Unavailable") : "full".equals(why) ? Ui.L("Hết chỗ", "Full") : andHint(v);
            int dot = hint.indexOf(" · ");
            hn.setText(dot > 0 ? hint.substring(0, dot) : hint);                 // ô hẹp → chỉ giữ ý đầu ("Ổn định")
            hn.setTextColor(ok ? Ui.WAIT : Ui.BAD);
            k.setText(on ? "✓ Android" : "Android");
            k.setTextColor(on ? (Ui.LIGHT ? Ui.BLUE : Color.rgb(207, 228, 255)) : Ui.MUTED);
            n.setTextColor(on ? (Ui.LIGHT ? Ui.SKY : Color.WHITE) : Ui.FG);
            android.graphics.drawable.GradientDrawable g = on
                    ? new android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
                            Ui.LIGHT ? new int[]{Color.rgb(238, 244, 255), Color.rgb(221, 233, 255)} : new int[]{Color.rgb(36, 78, 168), Color.rgb(13, 32, 80)})
                    : new android.graphics.drawable.GradientDrawable();
            if (!on) g.setColor(Ui.LIGHT ? Color.WHITE : Ui.SUNK);
            g.setCornerRadius(Ui.dp(Ui.rad(16)));
            g.setStroke(on ? Ui.dp(2) : Math.max(1, Ui.dp(1)), on ? (Ui.LIGHT ? Ui.BLUE : Color.rgb(124, 188, 255)) : Ui.LINE2);
            f.setBackground(new android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(Color.argb(60, 143, 208, 255)), g, null));
            f.setElevation(on ? Ui.dp(5) : 0);
            f.setEnabled(ok);
            f.setAlpha(ok ? 1f : .45f);
            f.setSelected(on);
        }
    }

    /** Bọc 1 nhóm lựa chọn vào thẻ viền neon cho gọn mắt. */
    View boxed(View v) {                        // 28/11f: RealPhone dùng chung (hộp thuê máy thật y hệt ĐT đám mây)
        LinearLayout c = Ui.card(this);
        c.setPadding(Ui.dp(14), Ui.dp(12), Ui.dp(14), Ui.dp(14));
        c.addView(v, Ui.fill());
        return c;
    }

    private void order(Button buy, String code, boolean blue, Promo pr) {
        buy.setEnabled(false);
        Api.bg(() -> {
            JSONObject a = new JSONObject().put("p_ram", sRam).put("p_cpu", sCpu).put("p_days", sDays)
                    .put("p_res", sRes).put("p_name", JSONObject.NULL).put("p_fps", sFps).put("p_qty", sFree ? 1 : sQty)
                    .put("p_android", sAnd.isEmpty() ? "9" : sAnd).put("p_free", sFree);
            if (code != null) a.put("p_promo", code);
            if (blue) a.put("p_blue", true);
            try { return Api.rpc("cloudphone_order_custom", a); }
            catch (Exception e) { String m = String.valueOf(e.getMessage()); if (pr != null && m.contains("PROMO_")) Api.ui(() -> pr.fail(m)); throw e; }
        }, r -> {
            Ui.toast(this, Ui.L("Đã đặt máy! Máy đang khởi tạo, khoảng 2–3 phút.", "Ordered! Your phone is being created (2–3 min)."));
            bluePayRent = false; rentPromo = "";
            Blue.at = 0; Offers.at = 0;
            show(0);
            refresh();
        }, m -> { buy.setEnabled(true); Ui.toast(this, m); if (m.contains("Blue")) Blue.load(this::blueChanged); });
    }

    String check() {
        if (status.optBoolean("maint", false) && !isAdmin()) return Ui.L("Hệ thống đang bảo trì, vui lòng quay lại sau.", "Under maintenance, please come back later.");
        if (status.has("online") && !status.optBoolean("online", true) && !isAdmin()) return Ui.L("Máy chủ đang tạm ngưng.", "Server is offline.");
        if (sFree && !isAdmin() && (sRam > price.optInt("free_max_ram", 4) || sCpu > price.optInt("free_max_cpu", 4)))
            return Ui.L("Máy miễn phí tối đa " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " nhân — chọn nhỏ hơn.",
                    "Free phones are limited to " + price.optInt("free_max_ram", 4) + "GB RAM · " + price.optInt("free_max_cpu", 4) + " cores.");
        if (sFree) { String te = Offers.trialErr(price, isAdmin()); if (!te.isEmpty()) return te; }        // v35: chưa nạp đủ / đã dùng thử rồi
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

    /** Gói t đang được chọn: khách ĐÃ chọn + cấu hình khớp gói. */
    boolean tierOn(Tiers.T t, int minR, int minC, int minF, int maxF) { return rentPicked && tierMatch(t, minR, minC, minF, maxF); }

    /** Cấu hình đang chọn khớp gói t (sau khi kẹp theo trần của bản Android đang chọn). */
    boolean tierMatch(Tiers.T t, int minR, int minC, int minF, int maxF) {
        int[] l = andLim(sAnd);
        return sRam == clamp(t.ram, minR, l[0]) && sCpu == clamp(t.cpu, minC, l[1]) && sFps == clamp(t.fps, minF, maxF)
                && (t.res == null || t.res.isEmpty() || t.res.equals(sRes));
    }

    /** Bấm 1 thẻ gói → điền RAM · CPU · FPS (· độ phân giải). Bản Android đang chọn không đủ trần (VD Android 9 tối đa 8GB) → chuyển bản. */
    void pickTier(Tiers.T t, java.util.List<String> ands, java.util.List<String> busy) {
        rentPicked = true;
        if (!ands.isEmpty() && !ands.contains(sAnd)) {
            String nv = ands.get(0);
            for (String v : ands) if (!busy.contains(v)) { nv = v; break; }
            sAnd = nv;
            String all = android.text.TextUtils.join(" / ", ands);
            Ui.toast(this, Ui.L("Gói " + t.name + " chạy trên Android " + all + " — đã chuyển sang Android " + nv + ".",
                    t.name + " runs on Android " + all + " — switched to Android " + nv + "."));
        }
        int[] l = andLim(sAnd);
        sRam = clamp(t.ram, price.optInt("min_ram", 1), l[0]);
        sCpu = clamp(t.cpu, price.optInt("min_cpu", 1), l[1]);
        sFps = clamp(t.fps, price.optInt("min_fps", 10), price.optInt("max_fps", 120));
        if (t.res != null && !t.res.isEmpty()) for (String[] r : RES) if (r[0].equals(t.res)) { sRes = t.res; break; }
        renderRent();
    }

    interface IntSet { void set(int v); }
    interface IntGet { int get(); }

    View group(String title, int[] vals, int min, int max, String suf, IntSet set, IntGet get) {
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
    /** Thẻ "Giới thiệu bạn bè": link mời + số liệu hoa hồng; tài khoản mới (≤ 7 ngày, chưa nạp) nhập được mã mời của bạn.
     *  Trang tài khoản vẽ lại mỗi lần tự tải (30 giây) → giữ kết quả 2 phút, khỏi gọi máy chủ liên tục. */
    private Object[] refCache;
    private long refAt = 0;

    void loadRef(TextView info, LinearLayout box) {
        if (refCache != null && SystemClock.elapsedRealtime() - refAt < 120_000L) { drawRef(info, box, refCache); return; }
        Api.<Object[]>bg(() -> {
            Object r = Api.rpc("ref_info", new JSONObject());
            JSONObject me = null;
            try {
                JSONArray a = (JSONArray) Api.get("profiles?id=eq." + Api.uid + "&select=ref_by,created_at");
                if (a.length() > 0) me = a.getJSONObject(0);
            } catch (Exception ignored) { }
            return new Object[]{r, me};
        }, res -> {
            refCache = res; refAt = SystemClock.elapsedRealtime();
            if (destroyed || tab != 2 || !info.isAttachedToWindow()) return;
            drawRef(info, box, res);
        }, m -> { if (!destroyed && tab == 2) info.setText(m.contains("ref_info") || m.contains("schema cache") ? Ui.L("Tính năng này chưa bật.", "Not available yet.") : m); });
    }

    private void drawRef(TextView info, LinearLayout box, Object[] res) {
        JSONObject d = res[0] instanceof JSONObject ? (JSONObject) res[0] : null;
        if (d == null || d.optString("code", "").isEmpty()) { info.setText(Ui.L("Tính năng này chưa bật.", "Not available yet.")); return; }
        double pct = d.optDouble("pct", 0);
        String pc = pct == Math.floor(pct) ? String.valueOf((long) pct) : String.valueOf(pct);
        final String link = Api.WEB + "/?ref=" + d.optString("code");
        final boolean buy = "buy".equals(d.optString("mode"));          // SQL v26: hoa hồng tính khi bạn bè MUA (bản cũ: khi nạp)
        final int days = d.optInt("days", 7) > 0 ? d.optInt("days", 7) : 7;
        info.setText(pct <= 0 ? Ui.L("Chương trình hoa hồng đang tạm dừng.", "The referral programme is paused.")
                : buy ? Ui.L("Gửi link cho bạn bè. Bạn bè đăng ký qua link rồi MUA (thuê máy, gia hạn, nâng cấp, mua sản phẩm) → bạn được cộng " + pc
                        + "% số tiền họ mua vào số dư, mỗi lần mua. Bạn bè chỉ nạp tiền mà chưa mua thì chưa được cộng.",
                        "Share your link. When friends sign up through it and BUY (rent, renew, upgrade a phone or buy a product), you get " + pc
                        + "% of every purchase added to your balance. Top-ups alone don't count.")
                : Ui.L("Gửi link cho bạn bè. Bạn bè đăng ký qua link rồi nạp tiền → bạn được cộng " + pc + "% số tiền họ nạp vào số dư, mỗi lần nạp.",
                        "Share your link. When friends sign up through it and top up, you get " + pc + "% of every top-up added to your balance."));
        box.removeAllViews();
        TextView lk = Ui.text(this, link, 14, Ui.SKY, true);
        lk.setTextIsSelectable(true);
        box.addView(lk, Ui.fill());
        LinearLayout br = Ui.row(this, 8);
        Button cp = Ui.button(this, "📋 " + Ui.L("Copy link", "Copy link"), Ui.GHOST);
        cp.setOnClickListener(v -> {
            android.content.ClipboardManager cm = (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm != null) cm.setPrimaryClip(android.content.ClipData.newPlainText("ref", link));
            Ui.toast(this, Ui.L("Đã copy link mời.", "Invite link copied."));
        });
        Button sh = Ui.button(this, "📤 " + Ui.L("Gửi link", "Share"), Ui.PRIMARY);
        sh.setOnClickListener(v -> {
            try {
                startActivity(Intent.createChooser(new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,
                        Ui.L("Thuê điện thoại Android đám mây treo game 24/7 — đăng ký qua link này: ", "Rent a 24/7 cloud Android phone — sign up here: ") + link), Ui.L("Gửi link mời", "Share invite link")));
            } catch (Exception e) { Ui.toast(this, e.getMessage() == null ? "?" : e.getMessage()); }
        });
        br.addView(cp, Ui.weight(1)); br.addView(sh, Ui.weight(1));
        box.addView(br, Ui.fill());
        box.addView(Ui.text(this, Ui.L("Đã mời: ", "Invited: ") + d.optInt("invited") + "  ·  "
                + (buy ? Ui.L("Đã mua: ", "Bought: ") + d.optInt("buyers", d.optInt("paid_users")) : Ui.L("Đã nạp: ", "Topped up: ") + d.optInt("paid_users"))
                + "  ·  " + Ui.L("Đã nhận: ", "Earned: ") + Ui.vnd(d.optDouble("earned", 0)), 14, Ui.FG, true), Ui.fill());
        JSONArray it = d.optJSONArray("items");
        if (it != null) for (int i = 0; i < Math.min(5, it.length()); i++) {
            JSONObject x = it.optJSONObject(i);
            if (x == null) continue;
            long at = parseTime(x.optString("at"));
            boolean xb = "buy".equals(x.optString("kind"));
            box.addView(Ui.muted(this, (at > 0 ? fdate(at) + " · " : "") + x.optString("who") + (xb ? Ui.L(" mua ", " bought ") : Ui.L(" nạp ", " topped up ")) + Ui.vnd(x.optDouble("topup", 0))
                    + "  →  +" + Ui.vnd(x.optDouble("amount", 0))), Ui.fill());
        }
        box.addView(Ui.muted(this, buy
                ? Ui.L("Chỉ tính tài khoản mới đăng ký qua link của bạn (nhận lời mời trong " + days + " ngày đầu, trước lần nạp đầu tiên). Chỉ tính phần tiền bạn bè nạp thật: tiền khuyến mãi, tiền được hoàn không tính; mỗi đồng tính 1 lần. Không tính tự mời chính mình.",
                       "Only new accounts that sign up through your link count (within their first " + days + " days, before their first top-up). Only money they actually topped up counts — promo credit and refunds don't, and each amount counts once. Self-invites don't count.")
                : Ui.L("Chỉ tính tài khoản mới đăng ký qua link của bạn (nhận lời mời trong 7 ngày đầu, trước lần nạp đầu tiên). Không tính tự mời chính mình.",
                       "Only new accounts that sign up through your link count (within their first 7 days, before their first top-up). Self-invites don't count.")), Ui.fill());
        JSONObject me = res[1] instanceof JSONObject ? (JSONObject) res[1] : null;
        boolean fresh = me != null && me.isNull("ref_by") && parseTime(me.optString("created_at")) > System.currentTimeMillis() - days * 86400000L;
        if (fresh) {                                     // tài khoản mới, chưa nhận lời mời → nhập mã của người mời (trong hộp thoại: trang vẽ lại không xoá chữ đang gõ)
            Button inv = Ui.button(this, "🎟 " + Ui.L("Được bạn mời? Nhập mã mời", "Invited? Enter the invite code"), Ui.GHOST);
            inv.setOnClickListener(v -> refClaimDlg(days));
            box.addView(inv, Ui.fill());
        }
    }

    void refClaimDlg(int days) {
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, Ui.L("Mã mời là 8 ký tự cuối trong link bạn bè gửi (…/?ref=ABCD1234). Chỉ tài khoản mới (tạo trong " + days + " ngày, chưa nạp tiền) nhận được.",
                "The invite code is the last 8 characters of your friend's link (…/?ref=ABCD1234). Only new accounts (under " + days + " days, no top-ups) can use it.")));
        EditText code = Ui.input(this, Ui.L("Mã mời", "Invite code"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        c.addView(code, Ui.fill());
        Button go = Ui.button(this, Ui.L("Nhận lời mời", "Accept invite"), Ui.PRIMARY);
        c.addView(go, Ui.fill());
        Dialog d = Ui.sheet(this, "🎟 " + Ui.L("Nhập mã mời", "Invite code"), c);
        go.setOnClickListener(v -> {
            String s = code.getText().toString().replaceFirst("(?i)^.*[?&]ref=", "").toUpperCase(Locale.US).replaceAll("[^A-Z0-9]", "");
            if (s.isEmpty()) return;
            go.setEnabled(false);
            Api.bg(() -> Api.rpc("ref_claim", new JSONObject().put("p_code", s)), r -> {
                go.setEnabled(true);
                JSONObject o = r instanceof JSONObject ? (JSONObject) r : new JSONObject();
                if (o.optBoolean("ok")) {
                    d.dismiss();
                    refCache = null;
                    Ui.toast(this, Ui.L("✓ Đã nhận lời mời.", "✓ Invite accepted."));
                    if (tab == 2) renderAccount();
                } else Ui.toast(this, Api.friendly(new Exception(o.optString("err", "REF_INVALID"))));
            }, m -> { go.setEnabled(true); Ui.toast(this, m); });
        });
        d.show();
    }

    private ScrollView accSv = null;                  // trang Tài khoản đang hiện (16/11: tự vẽ lại mỗi 30 giây vẫn giữ chỗ đang cuộn)
    private boolean uiDrag = false;                   // khách đang kéo thanh cỡ giao diện

    /** 16/11 · thẻ 🎨 Giao diện: thanh chỉnh CỠ CHỮ & NÚT 80–130% (thả tay là áp dụng, nhớ theo máy) · ẩn / hiện ô ưu đãi đầu trang. */
    private View lookCard() {
        LinearLayout s = Ui.card(this);
        s.setTag("look_card");
        s.addView(Ui.h2(this, "🎨 " + Ui.L("Giao diện", "Appearance")));
        final int n = (Ui.SCALE_MAX - Ui.SCALE_MIN) / Ui.SCALE_STEP, cur = Ui.scalePct(this);
        final TextView lab = Ui.text(this, "", 15, Ui.FG, false);
        s.addView(lab, Ui.fill());
        LinearLayout r = Ui.row(this, 6);
        final TextView minus = Ui.text(this, "A−", 13, Ui.FG, true), plus = Ui.text(this, "A+", 18, Ui.FG, true);
        final android.widget.SeekBar sb = new android.widget.SeekBar(this);
        sb.setMax(n);
        sb.setProgress((cur - Ui.SCALE_MIN) / Ui.SCALE_STEP);
        sb.setTag("scale_bar");
        try {
            sb.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.BLUE));
            sb.setThumbTintList(android.content.res.ColorStateList.valueOf(Ui.BLUE));
        } catch (Exception ignored) { }
        sb.setContentDescription(Ui.L("Cỡ chữ và nút của app", "App text and button size"));
        final Runnable txt = () -> {
            int v = Ui.SCALE_MIN + sb.getProgress() * Ui.SCALE_STEP;
            lab.setText("🔍 " + Ui.L("Cỡ chữ & nút: ", "Text & button size: ") + v + "%" + (v == 100 ? Ui.L(" (mặc định)", " (default)") : ""));
        };
        final Runnable apply = () -> {
            int v = Ui.SCALE_MIN + sb.getProgress() * Ui.SCALE_STEP;
            if (destroyed || isFinishing() || v == Ui.scalePct(this)) return;
            Ui.setScale(this, v);
            recreate();                                 // vẽ lại cả màn với cỡ mới (show() đã nhớ tab đang xem)
        };
        sb.setOnSeekBarChangeListener(new android.widget.SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(android.widget.SeekBar x, int pr, boolean user) {
                txt.run();
                if (user && !uiDrag) { h.removeCallbacks(apply); h.postDelayed(apply, 600); }     // chỉnh bằng phím / trợ năng (không kéo)
            }
            @Override public void onStartTrackingTouch(android.widget.SeekBar x) { uiDrag = true; h.removeCallbacks(apply); }
            @Override public void onStopTrackingTouch(android.widget.SeekBar x) { uiDrag = false; apply.run(); }
        });
        for (TextView b : new TextView[]{minus, plus}) { b.setGravity(Gravity.CENTER); Ui.ripple(b, Ui.PANEL, 12, Ui.RING); }
        minus.setContentDescription(Ui.L("Nhỏ hơn", "Smaller"));
        plus.setContentDescription(Ui.L("To hơn", "Bigger"));
        minus.setOnClickListener(v -> { if (sb.getProgress() > 0) { sb.setProgress(sb.getProgress() - 1); txt.run(); h.removeCallbacks(apply); h.postDelayed(apply, 350); } });
        plus.setOnClickListener(v -> { if (sb.getProgress() < n) { sb.setProgress(sb.getProgress() + 1); txt.run(); h.removeCallbacks(apply); h.postDelayed(apply, 350); } });
        r.addView(minus, new LinearLayout.LayoutParams(Ui.dp(44), Ui.dp(40)));
        r.addView(sb, Ui.weight(1));
        r.addView(plus, new LinearLayout.LayoutParams(Ui.dp(44), Ui.dp(40)));
        s.addView(r, Ui.fill());
        s.addView(Ui.muted(this, Ui.L("Kéo sang phải cho chữ và nút TO hơn, sang trái cho NHỎ hơn — thả tay là đổi ngay.",
                "Drag right for bigger text and buttons, left for smaller — it applies when you let go.")));
        txt.run();
        // 16/11c: NGÔN NGỮ — Tiếng Việt / English (nhớ cho cả app, vẽ lại ngay, ở lại tab Tài khoản)
        LinearLayout lr = Ui.row(this, 8);
        lr.setPadding(0, Ui.dp(8), 0, Ui.dp(2));
        lr.addView(Ui.text(this, "🌐 " + Ui.L("Ngôn ngữ", "Language"), 15, Ui.FG, false), Ui.weight(1));
        final String curL = Ui.vi() ? "vi" : "en";
        for (String[] o : new String[][]{{"vi", "Tiếng Việt"}, {"en", "English"}}) {
            TextView ch = Ui.chip(this, o[1], o[0].equals(curL));
            ch.setMinWidth(0);
            ch.setPadding(Ui.dp(12), Ui.dp(7), Ui.dp(12), Ui.dp(8));
            ch.setOnClickListener(v -> { if (!o[0].equals(curL)) { Ui.setLang(this, o[0]); recreate(); } });
            lr.addView(ch, Ui.wrap());
        }
        s.addView(lr, Ui.fill());
        if (Api.SHOP && Offers.on())                    // bản có ô ưu đãi / vòng quay ở đầu trang — công tắc thật (16/11c)
            s.addView(Ui.toggle(this, "🎁 " + Ui.L("Ô ưu đãi · vòng quay ở đầu trang", "Offers · lucky wheel on top"),
                    Ui.L("Tắt nếu muốn trang gọn hơn.", "Turn off for a cleaner screen."), !promoHidden(), on -> setPromoHidden(!on)), Ui.fill());
        return s;
    }

    void renderAccount() {
        final int keepY = tab == 2 && accSv != null && accSv.getParent() != null ? accSv.getScrollY() : 0;
        LinearLayout body = Ui.col(this, 14);
        LinearLayout c = Ui.card(this);
        String name = prof.optString("username", "");
        c.addView(Ui.h1(this, "👤 " + (name.isEmpty() || name.equals("null") ? Ui.L("Tài khoản", "Account") : name)));
        c.addView(Ui.muted(this, Api.email));
        if (Api.SHOP) {                                 // số dư + Nạp tiền (bản CH Play: nạp qua Google Play — PlayPay)
            c.addView(Ui.text(this, Ui.L("Số dư: ", "Balance: ") + Ui.vnd(prof.optDouble("balance", 0)), 18, Ui.MONEY, true));
            if (isCtv()) c.addView(Ui.pill(this, "🤝 CTV −" + prof.optInt("ctv_discount") + "%", Ui.OK), Ui.wrap());
            Button top = Ui.button(this, "💳 " + Ui.L("Nạp tiền", "Top up"), Ui.PRIMARY);
            top.setOnClickListener(v -> openTopup());
            c.addView(top, Ui.fill());
        }
        body.addView(c, Ui.fill());
        body.addView(lookCard(), Ui.fill());            // 🎨 16/11: cỡ chữ & nút · ẩn / hiện ô ưu đãi
        if (Api.SHOP && Wheel.on()) body.addView(Wheel.card(this), Ui.fill());    // 🎡 vòng quay may mắn (SQL v34c) — bản CH Play không có

        if (Api.SHOP) {                                 // 🧾 1.115: lịch sử nạp tiền — đọc THẲNG từ máy chủ, cùng nguồn với web
            LinearLayout hc = Ui.card(this);
            hc.addView(Ui.h2(this, "🧾 " + Ui.L("Lịch sử nạp tiền", "Top-up history")));
            TextView hInfo = Ui.muted(this, Ui.L("Đang tải…", "Loading…"));
            hc.addView(hInfo, Ui.fill());
            LinearLayout hBox = Ui.col(this, 8);
            hc.addView(hBox, Ui.fill());
            body.addView(hc, Ui.fill());
            loadTopups(hInfo, hBox);
        }

        if (Blue.on()) {                                // 💎 Tích Blue (SQL v27)
            LinearLayout bc = Ui.card(this);
            bc.addView(Ui.h2(this, "💎 " + Ui.L("Tích Blue", "Blue rewards")));
            blueAcc = Ui.text(this, "", 16, Ui.SKY, true);
            bc.addView(blueAcc, Ui.fill());
            bc.addView(Ui.muted(this, !Api.SHOP ? Ui.L("Điểm danh mỗi ngày, mở máy đám mây để tích Blue.", "Check in daily and open your cloud phone to earn Blue.")
                    : Api.PLAY ? Ui.L("Điểm danh, làm nhiệm vụ hằng ngày để tích Blue — 1 Blue = 1đ khi thuê / gia hạn máy.",
                           "Check in and do daily missions to earn Blue — 1 Blue = 1đ on rentals and renewals.")
                    : Ui.L("Điểm danh, làm nhiệm vụ hằng ngày, mời bạn để tích Blue — 1 Blue = 1đ khi thuê / gia hạn máy.",
                           "Check in, do daily missions and invite friends to earn Blue — 1 Blue = 1đ on rentals and renewals.")));
            Button ob = Ui.button(this, "💎 " + Ui.L("Mở Tích Blue · điểm danh", "Open Blue rewards · check in"), Ui.PRIMARY);
            ob.setOnClickListener(v -> Blue.sheet(this));
            bc.addView(ob, Ui.fill());
            body.addView(bc, Ui.fill());
            blueChanged();
        }

        if (!Api.PLAY) {                                // bản CH Play: không giới thiệu bạn bè (link mời dẫn ra web)
            LinearLayout rf = Ui.card(this);            // 🎁 Giới thiệu bạn bè (SQL v24: ref_info / ref_claim)
            rf.addView(Ui.h2(this, "🎁 " + Ui.L("Giới thiệu bạn bè", "Invite friends")));
            TextView rfInfo = Ui.muted(this, Ui.L("Đang tải…", "Loading…"));
            rf.addView(rfInfo, Ui.fill());
            LinearLayout rfBox = Ui.col(this, 10);
            rf.addView(rfBox, Ui.fill());
            body.addView(rf, Ui.fill());
            loadRef(rfInfo, rfBox);
        }

        LinearLayout s = Ui.card(this);
        s.addView(Ui.h2(this, Ui.L("Cài đặt", "Settings")));
        s.addView(Ui.toggle(this, "🔔 " + Ui.L("Nhắc khi máy sắp hết hạn", "Expiry reminders"),
                Ui.L("Nhắc trước 1 ngày và 1 giờ khi máy sắp hết hạn.", "Reminds you 1 day and 1 hour before a phone expires."),
                ExpiryAlarm.enabled(this), on -> { ExpiryAlarm.setEnabled(this, on); ExpiryAlarm.schedule(this, phones); }), Ui.fill());
        body.addView(s, Ui.fill());

        LinearLayout l = Ui.card(this);
        l.addView(Ui.h2(this, Ui.L("Hỗ trợ", "Support")));
        if (!Api.PLAY) {                                // bản CH Play: không link ra trang mua hàng
            Button web = Ui.button(this, "🌐 " + Ui.L("Mở website ", "Open ") + Api.webHost(), Ui.GHOST);
            web.setOnClickListener(v -> openWeb(Api.WEB));
            l.addView(web, Ui.fill());
        }
        // 23/11 · link NHÓM Zalo + server Discord của shop (admin nhập trên web: Cài đặt › Nội dung trang) → bấm là mở
        final JSONObject sd = Api.siteData;
        final String[][] grp = {{"joinZl", "💬 " + Ui.L("Tham gia nhóm Zalo CloudBlue", "Join the CloudBlue Zalo group")},
                {"joinDc", "🎮 " + Ui.L("Tham gia Discord CloudBlue", "Join the CloudBlue Discord")}};
        for (String[] k : grp) {
            final String u = sd == null ? "" : sd.optString(k[0], "").trim();
            if (u.length() > 200 || !u.matches("(?i)https?://[^\\s\"'<>]+")) continue;
            Button g = Ui.button(this, k[1], Ui.PRIMARY);
            g.setOnClickListener(v -> openWeb(u));
            l.addView(g, Ui.fill());
        }
        Button pol = Ui.button(this, "📄 " + Ui.L("Chính sách & điều khoản", "Policy & terms"), Ui.GHOST);
        pol.setOnClickListener(v -> openWeb(Api.policyUrl()));
        l.addView(pol, Ui.fill());
        // Xoá tài khoản (Google Play bắt buộc với app cho tạo tài khoản): trang hướng dẫn gửi yêu cầu xoá
        Button del = Ui.button(this, "🗑 " + Ui.L("Xoá tài khoản", "Delete account"), Ui.GHOST);
        del.setOnClickListener(v -> openWeb(Api.WEB + "/xoa-tai-khoan.html"));
        l.addView(del, Ui.fill());
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
        final ScrollView sv = page(body);
        accSv = sv;
        if (keepY > 0) sv.post(() -> sv.scrollTo(0, keepY));
    }

    // ---------------- Nạp tiền ngay trong app: chuyển khoản + mã VietQR, ngân hàng báo có là tự cộng số dư (giống web) ----------------
    static final long[] TOP_AMTS = {50000, 100000, 200000, 500000, 1000000};
    static final String[][] BANKS = {{"970422", "MB Bank"}, {"970436", "Vietcombank"}, {"970407", "Techcombank"}, {"970416", "ACB"}, {"970432", "VPBank"},
            {"970418", "BIDV"}, {"970415", "VietinBank"}, {"970423", "TPBank"}, {"970403", "Sacombank"}, {"970405", "Agribank"}, {"970441", "VIB"},
            {"970443", "SHB"}, {"970448", "OCB"}, {"970426", "MSB"}};

    /** 🧾 Lịch sử nạp tiền (1.115): đọc THẲNG bảng topups trên máy chủ (chỉ lệnh của chính mình) — cùng nguồn với web,
     *  KHÔNG lưu gì trên máy. Số tiền "đã cộng" là số ngân hàng / crypto thật sự báo về, không phải số khách gõ.
     *  Nhớ tạm 60 giây (màn Tài khoản tự vẽ lại mỗi 30 giây) — tạo mã nạp / nạp xong thì xoá nhớ tạm để hiện ngay. */
    private JSONArray topCache = null;
    private long topAt = 0;

    void loadTopups(TextView info, LinearLayout box) {
        final String me = Api.uid;
        if (me == null || me.isEmpty()) { info.setText(Ui.L("Đăng nhập lại để xem lịch sử nạp.", "Log in again to see your top-ups.")); return; }
        if (topCache != null && SystemClock.elapsedRealtime() - topAt < 60_000L) { drawTopups(info, box, topCache); return; }
        Api.bg(() -> Api.get("topups?user_id=eq." + me + (Api.PLAY ? "&via=eq.play" : "")      // bản CH Play: chỉ lệnh nạp qua Google Play
                + "&select=memo,amount,asked,status,via,created_at,done_at&order=created_at.desc&limit=20"), r -> {
            JSONArray a = r instanceof JSONArray ? (JSONArray) r : new JSONArray();
            topCache = a; topAt = SystemClock.elapsedRealtime();
            if (destroyed || tab != 2 || !info.isAttachedToWindow()) return;
            drawTopups(info, box, a);
        }, m -> { if (!destroyed && info.isAttachedToWindow()) info.setText(m); });
    }

    private void drawTopups(TextView info, LinearLayout box, JSONArray a) {
        box.removeAllViews();
        long sum = 0;
        for (int i = 0; i < a.length(); i++) {
            JSONObject t = a.optJSONObject(i);
            if (t == null) continue;
            boolean ok = "done".equals(t.optString("status")), back = "reversed".equals(t.optString("status"));
            boolean gp = "play".equals(t.optString("via"));
            double amt = ok || back ? t.optDouble("amount", 0) : t.optDouble("asked", t.optDouble("amount", 0));
            if (ok) sum += Math.round(amt);
            long at = parseTime(t.optString(ok && !t.isNull("done_at") ? "done_at" : "created_at"));
            LinearLayout row = Ui.row(this, 8);
            LinearLayout col = Ui.col(this, 2);
            col.addView(Ui.text(this, (gp ? "▶️ Google Play · " : Ui.L("Nạp tiền · ", "Top-up · ")) + t.optString("memo"), 14, Ui.FG, true));
            col.addView(Ui.muted(this, (at > 0 ? fdate(at) + " · " : "") + (ok ? Ui.L("✓ Đã cộng vào số dư", "✓ Credited")
                    : back ? Ui.L("↩️ Google Play đã hoàn tiền — đã trừ lại", "↩️ Refunded by Google Play — deducted")
                    : Ui.L("⏳ Chưa thấy tiền về (chỉ là lệnh tạo mã, chưa cộng)", "⏳ No payment yet (code only, not credited)"))));
            row.addView(col, Ui.weight(1));
            TextView av = Ui.text(this, (ok ? "+" : "") + Ui.vnd(amt), 15, ok ? Ui.OK : Ui.MUTED, ok);
            if (back) av.setPaintFlags(av.getPaintFlags() | android.graphics.Paint.STRIKE_THRU_TEXT_FLAG);
            row.addView(av, Ui.wrap());
            box.addView(row, Ui.fill());
        }
        info.setText(a.length() == 0 ? (Api.PLAY ? Ui.L("Chưa nạp lần nào qua Google Play.", "No Google Play top-ups yet.") : Ui.L("Chưa có lệnh nạp nào.", "No top-ups yet."))
                : Api.PLAY ? Ui.L("Lấy trực tiếp từ máy chủ. 20 lần nạp gần nhất · đã cộng: ", "Straight from the server. Latest 20 · credited: ") + Ui.vnd(sum)
                : Ui.L("Lấy trực tiếp từ máy chủ, giống hệt trên web. 20 lệnh gần nhất · đã cộng: ", "Straight from the server, same as the website. Latest 20 · credited: ") + Ui.vnd(sum));
    }

    void openTopup() { openTopup(0); }

    /** need > 0: số tiền còn thiếu (điền sẵn, làm tròn lên 1.000đ). Bản CH Play: chọn gói nạp qua Google Play (PlayPay). */
    void openTopup(double need) {
        if (Api.PLAY) {
            if (PlayPay.ON) PlayPay.open(this, prof.optDouble("balance", 0), need, this::credited);
            return;                                      // bản CH Play KHÔNG BAO GIỜ hiện QR ngân hàng / crypto
        }
        Api.<JSONObject>bg(Api::site, site -> topupSheet(site, need), m -> Ui.toast(this, m));
    }

    /** ▶️ Nạp qua Google Play xong (PlayPay) → tải lại số dư + lịch sử nạp. */
    void credited() {
        if (destroyed) return;
        topCache = null;
        refresh();
    }

    void topupSheet(JSONObject site, double need) {
        final long min = Math.max(1000, site.optLong("minTop", 10000));
        final String acc = site.optString("bankAcc", "").replaceAll("\\D", "");
        final long[] amt = {need > 0 ? Math.max(min, (long) Math.ceil(need / 1000.0) * 1000) : Math.max(min, 50000)};
        LinearLayout c = Ui.col(this, 12);
        if (Wheel.on()) c.addView(Wheel.card(this), Ui.fill());           // 🎡 vòng quay may mắn hiện ngay trong hộp nạp
        final TextView wh = Wheel.hint(this);                              // "🎡 Lệnh nạp này được +N lượt quay"
        final TextView oh = Offers.topupHint(this);                        // "🎁 Lần nạp này được tặng mã giảm N%" (SQL v35)
        final Offers.Amt[] pickAmt = new Offers.Amt[1];
        { View ob = Offers.topupBox(this, v -> { if (pickAmt[0] != null) pickAmt[0].set(v); }); if (ob != null) c.addView(ob, Ui.fill()); }
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
            Wheel.hint(wh, amt[0]);
            Offers.topupHint(this, oh, amt[0]);
        };
        pickAmt[0] = v -> { amt[0] = Math.max(min, v); x.setText(""); draw.run(); };
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
        c.addView(wh, Ui.fill());
        c.addView(oh, Ui.fill());
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
                topCache = null;                                  // 🧾 lịch sử nạp: hiện ngay lệnh vừa tạo
                Offers.at = 0;                                    // nạp xong → tải lại ưu đãi (mã vừa tặng, lượt dùng thử)
                d.dismiss();
                if (r instanceof JSONObject) paySheet(site, (JSONObject) r);
            }, m -> { make.setEnabled(true); err.setText(m); err.setVisibility(View.VISIBLE); });
        });
        draw.run();
        d.show();
        if (Wheel.on()) Wheel.load(draw);                                  // có trạng thái vòng quay → vẽ lại dòng "+N lượt"
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
                    topCache = null;                              // 🧾 lịch sử nạp: hiện ngay "đã cộng"
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
