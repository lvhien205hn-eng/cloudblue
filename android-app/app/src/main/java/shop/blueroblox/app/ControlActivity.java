package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputConnectionWrapper;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.util.Locale;
import java.util.Random;
import java.util.regex.Pattern;

/** Màn điều khiển máy ảo: hình máy (trình phát gốc, giao thức v2) ở giữa, thanh nút Android + công cụ bằng giao diện app. */
public class ControlActivity extends Activity {
    private static final int REQ_APK = 51;
    private static final String[][] QUAL = {{"auto", "Tự động", "Auto"}, {"eco", "Tiết kiệm", "Saver"}, {"bal", "Cân bằng", "Balanced"}, {"hd", "Siêu nét", "Ultra HD"}};
    private static final Pattern UUID = Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    private static final int META_CTRL = 0x1000;

    private final Handler h = new Handler(Looper.getMainLooper());
    private FrameLayout stage;
    private StreamView screen;
    private StreamClient client;
    private LinearLayout topBar, navBar, veil, mini;
    private TextView title, info, veilText, stats, ball;
    // Ẩn thanh (toàn màn): nút nổi tròn hiện độ trễ mạng (kéo để dời chỗ) · bấm → thanh nút nhỏ ◁ ○ ▢ 🔄 ⋯ ⤢
    // Xoay: máy cloud ngang → app tự xoay ngang + ẩn thanh cho hình to nhất; về dọc → trả lại (tắt được trong menu Xoay màn)
    private Object backCb;                                   // Android 13+: Back qua OnBackInvokedDispatcher (kiểu Object: máy cũ không nạp lớp mới)
    private boolean autoRot = true, streamLand = false, haveSize = false, autoFull = false;
    private int ping = -1;
    private ProgressBar veilSpin;
    private Button veilBtn;
    private Runnable veilAct;
    private JSONObject phone = new JSONObject();
    private String id;
    private String api = "";                 // stream.api của máy chủ đang giữ máy (rỗng = máy chủ mặc định)
    private String quality = "bal";
    private boolean full = false, loaded = false, resumed = false, kicked = false, stopped = false, showStats = false;
    private long rebootUntil = 0;
    private SharedPreferences pref;
    // Bàn phím: máy cloud mở bàn phím (bấm vào ô nhập) → bật bàn phím điện thoại vào 1 ô gõ vô hình, gõ tới đâu gửi tới đó
    private ImeSink sink;
    private String mirror = "";              // chữ đang có trong ô gõ vô hình = phần đã gửi sang máy
    private boolean sinkMute = false, kbOpen = false, kbBusy = false, kbDead = false, remoteIme = false, imeUp = false;
    private int kbOff = 0;
    // chữ app vừa dán sang máy (máy báo copy lại đúng chữ đó thì không đưa về điện thoại)
    private final java.util.LinkedHashMap<String, Long> sentClips = new java.util.LinkedHashMap<>();

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Ui.init(this);
        id = phoneId(getIntent());
        if (!Api.loggedIn()) {                   // mở từ link blueroblox://phone/… khi chưa đăng nhập → đăng nhập trước, xong tự mở lại máy này
            Intent i = new Intent(this, LoginActivity.class);
            if (id != null) i.putExtra("open_phone", id);
            startActivity(i);
            finish();
            return;
        }
        if (id == null) { Ui.toast(this, Ui.L("Link máy không hợp lệ.", "Invalid phone link.")); finish(); return; }
        Ui.edgeToEdge(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        pref = getSharedPreferences("control", MODE_PRIVATE);
        // Điện thoại: mặc định TỰ ĐỘNG — máy chủ đo mạng thật (app báo đã nhận khung nào) rồi tự chọn độ nét + khung/giây:
        // 4G yếu → nhẹ, ít trễ; wifi khoẻ → 60 FPS. Bản cũ đang để Cân bằng (mặc định trước đây) → chuyển sang Tự động 1 lần;
        // khách đã tự chọn Tiết kiệm / Siêu nét thì giữ nguyên.
        if (!pref.getBoolean("q_auto_v4", false)) {
            String old = pref.getString("q", "bal");
            pref.edit().putBoolean("q_auto_v4", true).putBoolean("q_bal_v3", true).putString("q", "bal".equals(old) ? "auto" : old).apply();
        }
        quality = pref.getString("q", "auto");
        if (!"auto".equals(quality) && !"eco".equals(quality) && !"bal".equals(quality) && !"hd".equals(quality)) quality = "auto";
        showStats = pref.getBoolean("stats", false);
        autoRot = pref.getBoolean("auto_rot", true);

        LinearLayout root = Ui.col(this, 0);
        root.setBackgroundColor(Color.BLACK);

        // Thanh trên (gọn): quay lại · tên máy · chất lượng · ⛶ ẩn thanh
        topBar = Ui.row(this, 6);
        topBar.setPadding(Ui.dp(4), Ui.dp(3), Ui.dp(6), Ui.dp(3));
        topBar.setBackgroundColor(Ui.BG);
        TextView back = Ui.text(this, "‹", 28, Ui.FG, false);
        back.setPadding(Ui.dp(10), 0, Ui.dp(8), Ui.dp(3));
        back.setContentDescription(Ui.L("Quay lại danh sách máy", "Back to phones"));
        back.setOnClickListener(v -> finish());
        topBar.addView(back, Ui.wrap());
        LinearLayout tt = Ui.col(this, 0);
        title = Ui.text(this, "…", 15, Ui.FG, true);
        title.setSingleLine(true);
        info = Ui.text(this, "", 11, Ui.MUTED, false);
        info.setSingleLine(true);
        tt.addView(title);
        tt.addView(info);
        topBar.addView(tt, Ui.weight(1));
        TextView q = Ui.pill(this, "", Ui.SKY);
        q.setOnClickListener(v -> pickQuality());
        q.setTag("q");
        topBar.addView(q, Ui.wrap());
        topBar.addView(barBtn("⛶", Ui.L("Ẩn thanh — hình to hết màn", "Hide bars — full screen"), v -> { autoFull = false; setFull(true); }),
                new LinearLayout.LayoutParams(Ui.dp(40), Ui.dp(40)));
        root.addView(topBar, Ui.fill());

        // Màn hình máy (SurfaceView + bộ giải mã phần cứng)
        stage = new FrameLayout(this);
        stage.setBackgroundColor(Color.BLACK);
        screen = new StreamView(this);
        screen.setEvents(new StreamView.Events() {
            @Override public void onFirstFrame() { frameShown(); }
            @Override public void onTouchDown() { touchedScreen(); }
            @Override public void onVideoSize(int w, int h) { videoSized(w, h); }
        });
        stage.addView(screen, new FrameLayout.LayoutParams(-1, -1));

        sink = new ImeSink(this);
        sink.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        sink.setImeOptions(EditorInfo.IME_FLAG_NO_EXTRACT_UI | EditorInfo.IME_FLAG_NO_FULLSCREEN | EditorInfo.IME_FLAG_NO_ENTER_ACTION);
        sink.setAlpha(0f);
        sink.setCursorVisible(false);
        sink.setBackground(null);
        sink.setTextColor(Color.TRANSPARENT);
        sink.setFocusable(false);
        sink.setFocusableInTouchMode(false);
        sink.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        if (Build.VERSION.SDK_INT >= 26) sink.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        sink.onEmptyDelete = n -> { for (int i = 0; i < n; i++) press(KeyEvent.KEYCODE_DEL); };
        sink.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int st, int c, int a) { }
            @Override public void onTextChanged(CharSequence s, int st, int bf, int c) { }
            @Override public void afterTextChanged(Editable s) { if (!sinkMute) sinkChanged(s); }
        });
        sink.setOnKeyListener((v, code, e) -> sinkKey(code, e));
        sink.setOnEditorActionListener((v, a, e) -> {
            if (e == null) { press(KeyEvent.KEYCODE_ENTER); h.post(this::resetSink); }   // nút Enter/Gửi của bàn phím (phím thật đã qua sinkKey)
            return true;
        });
        stage.addView(sink, new FrameLayout.LayoutParams(1, 1, Gravity.TOP | Gravity.START));

        stats = Ui.text(this, "", 11, Color.WHITE, false);
        stats.setTypeface(Typeface.MONOSPACE);
        stats.setBackground(Ui.round(Color.argb(150, 0, 0, 0), 6, 0));
        stats.setPadding(Ui.dp(6), Ui.dp(2), Ui.dp(6), Ui.dp(2));
        stats.setVisibility(showStats ? View.VISIBLE : View.GONE);
        FrameLayout.LayoutParams sp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        sp.setMargins(Ui.dp(8), Ui.dp(8), 0, 0);
        stage.addView(stats, sp);

        veil = Ui.col(this, 12);
        veil.setGravity(Gravity.CENTER);
        veil.setPadding(Ui.dp(28), Ui.dp(28), Ui.dp(28), Ui.dp(28));
        veil.setBackgroundColor(Ui.LIGHT ? Color.argb(242, 243, 247, 252) : Color.argb(238, 7, 18, 38));
        veil.setClickable(true);                 // đang chờ / báo lỗi: chạm không lọt xuống màn hình máy
        veilSpin = new ProgressBar(this);
        veil.addView(veilSpin, Ui.wrap());
        veilText = Ui.text(this, Ui.L("Đang kết nối…", "Connecting…"), 15, Ui.FG, false);
        veilText.setGravity(Gravity.CENTER);
        veil.addView(veilText, Ui.fill());
        veilBtn = Ui.button(this, Ui.L("Thử lại", "Retry"), Ui.PRIMARY);
        veilBtn.setOnClickListener(v -> { Runnable r = veilAct; if (r != null) r.run(); });
        veilBtn.setVisibility(View.GONE);
        veil.addView(veilBtn, Ui.wrap());
        stage.addView(veil, new FrameLayout.LayoutParams(-1, -1));

        // Nút nổi (khi ẩn thanh): tròn, hiện độ trễ mạng như app cloud phone lớn · bấm = hiện/ẩn thanh nút nhỏ · giữ kéo = dời chỗ
        ball = Ui.text(this, "", 11, Color.WHITE, true);
        ball.setGravity(Gravity.CENTER);
        ball.setLineSpacing(0, 0.85f);
        ball.setContentDescription(Ui.L("Nút điều khiển — bấm để hiện các nút", "Controls — tap to show buttons"));
        ball.setVisibility(View.GONE);
        ball.setOnTouchListener(new BallDrag());
        ball.setOnClickListener(v -> toggleMini());
        stage.addView(ball, new FrameLayout.LayoutParams(Ui.dp(48), Ui.dp(48), Gravity.TOP | Gravity.START));
        mini = Ui.row(this, 0);
        mini.setBackground(Ui.round(Color.argb(225, 10, 16, 30), 24, Color.argb(90, 120, 160, 255)));
        mini.setPadding(Ui.dp(4), 0, Ui.dp(4), 0);
        mini.addView(miniBtn("◁", Ui.L("Quay lại", "Back"), () -> cmd("back")));
        mini.addView(miniBtn("○", Ui.L("Màn chính", "Home"), () -> cmd("home")));
        mini.addView(miniBtn("▢", Ui.L("Đa nhiệm", "Recents"), () -> cmd("recents")));
        mini.addView(miniBtn("🔄", Ui.L("Xoay ngang / dọc", "Rotate"), this::quickRotate));
        mini.addView(miniBtn("⋯", Ui.L("Công cụ", "Tools"), () -> { hideMini(); tools(); }));
        mini.addView(miniBtn("⤢", Ui.L("Hiện thanh", "Show bars"), () -> { autoFull = false; setFull(false); }));
        mini.setVisibility(View.GONE);
        stage.addView(mini, new FrameLayout.LayoutParams(-2, Ui.dp(48), Gravity.TOP | Gravity.START));
        paintBall();
        stage.addOnLayoutChangeListener((v, l, t, r, bt, ol, ot, or, ob) -> {   // xoay điện thoại / đổi cỡ → đặt lại nút nổi đúng chỗ đã lưu
            if (r - l != or - ol || bt - t != ob - ot) h.post(() -> { restoreBall(); if (mini.getVisibility() == View.VISIBLE) placeMini(); });
        });
        stage.setOnApplyWindowInsetsListener((v, in) -> {      // biết bàn phím điện thoại đang hiện hay không
            imeUp = Build.VERSION.SDK_INT >= 30 ? in.isVisible(WindowInsets.Type.ime()) : in.getSystemWindowInsetBottom() > Ui.dp(120);
            return in;
        });
        root.addView(stage, new LinearLayout.LayoutParams(-1, 0, 1));

        // Thanh nút Android (gọn: chỉ biểu tượng, giữ lâu hiện tên)
        navBar = Ui.row(this, 0);
        navBar.setBackgroundColor(Ui.BG);
        navBar.setPadding(Ui.dp(6), 0, Ui.dp(6), 0);
        navBar.addView(barBtn("◁", Ui.L("Quay lại", "Back"), v -> cmd("back")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("○", Ui.L("Màn chính", "Home"), v -> cmd("home")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("▢", Ui.L("Đa nhiệm", "Recents"), v -> cmd("recents")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("🔄", Ui.L("Xoay ngang / dọc", "Rotate"), v -> quickRotate()), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("⋯", Ui.L("Công cụ", "Tools"), v -> tools()), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        root.addView(navBar, Ui.fill());

        Ui.insets(root, true, true);
        setContentView(root);
        updQ();
        if (pref.getBoolean("full", false)) setFull(true);     // lần trước khách để ẩn thanh → mở lại vẫn ẩn
        if (Build.VERSION.SDK_INT >= 33) {                    // Android 16 + targetSdk 36: hệ thống KHÔNG gọi onBackPressed nữa → Back đi qua đây
            android.window.OnBackInvokedCallback cb = () -> { if (!handleBack()) finish(); };
            backCb = cb;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, cb);
        }
        load();
    }

    /** Nút chỉ có biểu tượng (thanh trên / thanh dưới): giữ lâu hiện tên nút. */
    private TextView barBtn(String icon, String desc, View.OnClickListener on) {
        TextView t = Ui.text(this, icon, 19, Ui.FG, false);
        t.setGravity(Gravity.CENTER);
        t.setContentDescription(desc);
        t.setClickable(true);
        t.setFocusable(true);
        if (Build.VERSION.SDK_INT >= 26) t.setTooltipText(desc);
        else t.setOnLongClickListener(v -> { Ui.toast(this, desc); return true; });
        Ui.ripple(t, Color.TRANSPARENT, 12, 0);
        t.setOnClickListener(on);
        return t;
    }

    private TextView miniBtn(String icon, String desc, Runnable act) {
        TextView t = barBtn(icon, desc, v -> { act.run(); armMini(); });
        t.setTextColor(Color.WHITE);
        t.setLayoutParams(new LinearLayout.LayoutParams(Ui.dp(44), Ui.dp(48)));
        return t;
    }

    /** Mã máy: từ màn danh sách (extra "id") hoặc từ link blueroblox://phone/<uuid>. */
    private static String phoneId(Intent it) {
        if (it == null) return null;
        String s = it.getStringExtra("id");
        Uri d = it.getData();
        if ((s == null || s.isEmpty()) && d != null && "blueroblox".equalsIgnoreCase(d.getScheme()) && "phone".equalsIgnoreCase(d.getHost()))
            s = d.getLastPathSegment();
        return cleanId(s);
    }

    private static String cleanId(String s) {
        if (s == null) return null;
        s = s.trim();
        return UUID.matcher(s).matches() ? s.toLowerCase(Locale.ROOT) : null;
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        if (loaded && !kicked && !stopped && client == null) connect();
        h.removeCallbacks(kbPoll);
        h.postDelayed(kbPoll, 1500);
        Api.onOutdated = () -> { if (!isFinishing()) Updater.check(this, false); };   // máy chủ báo app cũ → hộp bắt buộc cập nhật
        Updater.check(this, false);
    }

    @Override protected void onPause() {
        super.onPause();
        resumed = false;
        h.removeCallbacks(kbPoll);
        stopStream();                            // rời màn hình → đóng phiên (BYE); quay lại tự nối lại
    }

    @Override protected void onDestroy() {
        if (Build.VERSION.SDK_INT >= 33 && backCb != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback((android.window.OnBackInvokedCallback) backCb);
        h.removeCallbacksAndMessages(null);
        stopStream();
        if (screen != null) screen.release();
        super.onDestroy();
    }

    // ---------------- Kết nối ----------------
    private void load() {
        stopStream();
        loaded = false;
        kicked = false;
        stopped = false;
        api = "";
        showVeil(Ui.L("Đang mở máy…", "Opening phone…"), true, null, null);
        final String pid = id;
        Api.bg(() -> {
            JSONArray a = (JSONArray) Api.get("cloud_phones?id=eq." + pid + "&select=*");
            if (a.length() == 0) throw new Exception(Ui.L("Không tìm thấy máy.", "Phone not found."));
            return a.getJSONObject(0);
        }, p -> {
            if (!pid.equals(id) || isFinishing()) return;
            phone = p;
            title.setText(phone.optString("name"));
            String res = phone.optString("res", "720x1280");
            try {
                String[] wh = res.split("x");
                if (wh.length == 2) screen.setVideoSize(Integer.parseInt(wh[0].trim()), Integer.parseInt(wh[1].trim()));   // đoán tỉ lệ trước khi có hình
            } catch (Exception ignored) { }
            info.setText(phone.optInt("ram") + "GB · " + phone.optInt("cpu") + Ui.L(" nhân · ", " cores · ") + res + " · " + phone.optInt("fps", 30) + " FPS");
            if (!"active".equals(phone.optString("status"))) { fail(Ui.L("Máy chưa chạy (đang tạo hoặc đã hết hạn).", "This phone is not running.")); return; }
            loaded = true;
            if (resumed) connect();
        }, m -> { if (pid.equals(id)) fail(m); });
    }

    /** Mở phiên phát hình mới (đóng phiên cũ nếu có). */
    private void connect() {
        if (id == null) return;
        if (!loaded) { load(); return; }
        stopStream();
        kicked = false;
        stopped = false;
        if (!rebooting()) showVeil(Ui.L("Đang kết nối…", "Connecting…"), true, null, null);
        client = new StreamClient(this, id, quality, net);
        screen.attach(client);
        client.start();
    }

    private void stopStream() {
        if (client != null) { client.close(); client = null; }
        if (screen != null) screen.attach(null);
    }

    private final StreamClient.Listener net = new StreamClient.Listener() {
        @Override public void onConnecting(int attempt, String why) {
            if (rebooting()) return;
            if (attempt <= 0) showVeil(Ui.L("Đang kết nối…", "Connecting…"), true, null, null);
            else showVeil(Ui.L("Đang kết nối lại… (lần " + attempt + ")", "Reconnecting… (attempt " + attempt + ")")
                    + (why == null || why.isEmpty() ? "" : "\n" + why), true, Ui.L("Mở lại", "Reopen"), ControlActivity.this::connect);
        }

        @Override public void onEndpoint(JSONObject ep) {
            JSONObject s = ep.optJSONObject("stream");
            String a = s == null || s.isNull("api") ? "" : s.optString("api", "").trim();
            api = a.startsWith("https://") ? a : "";
            Api.direct(api, s);                          // công cụ máy (cài APK, clone, khởi động lại…) đi thẳng tới máy chủ, không cần tên miền
        }

        @Override public void onWelcome(JSONObject w, boolean direct) {
            if (stats.getVisibility() == View.VISIBLE) stats.setText(direct ? Ui.L("trực tiếp", "direct") : "Cloudflare");
            // màn chờ ẩn khi khung hình đầu tiên hiện (StreamView báo)
        }

        @Override public void onClipboard(String text) { phoneCopied(text); }

        @Override public void onStats(int fps, int kbps, int ping, boolean direct, JSONObject server) {
            if (ControlActivity.this.ping != ping) { ControlActivity.this.ping = ping; paintBall(); }   // nút nổi: độ trễ mạng
            if (stats.getVisibility() != View.VISIBLE) return;
            stats.setText(fps + " fps · " + kbps + " kbps · " + (ping >= 0 ? ping + " ms" : "– ms") + " · "
                    + (direct ? Ui.L("trực tiếp", "direct") : "Cloudflare"));
        }

        @Override public void onProblem(String code, String msg) {
            if (rebooting()) return;
            showVeil(msg + "\n" + Ui.L("Đang thử lại…", "Retrying…"), true, null, null);
        }

        @Override public void onStopped(String code, String msg) { streamStopped(code, msg); }
    };

    private void streamStopped(String code, String msg) {
        stopStream();
        if ("KICKED".equals(code)) {
            kicked = true;
            showVeil("📱 " + Ui.L("Máy đang được mở ở nơi khác", "This phone is open somewhere else") + "\n\n"
                            + Ui.L("Mỗi máy chỉ xem được ở 1 nơi (app, máy tính…) để hình luôn mượt.", "A phone can only be viewed in one place at a time."),
                    false, Ui.L("Mở lại tại đây", "Open here"), this::connect);
            return;
        }
        if ("LOGIN".equals(code)) { Api.logout(); toLogin(); return; }
        stopped = true;
        if ("AUTH".equals(code)) {
            showVeil(msg, false, Ui.L("Đăng nhập lại", "Log in again"), () -> { Api.logout(); toLogin(); });
            return;
        }
        showVeil(msg, false, Ui.L("Thử lại", "Retry"), this::connect);
    }

    private void toLogin() {
        Intent i = new Intent(this, LoginActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        if (id != null) i.putExtra("open_phone", id);
        startActivity(i);
        finish();
    }

    /** Khung hình đầu tiên đã lên → ẩn màn chờ. */
    private void frameShown() {
        if (kicked || stopped || rebooting() || client == null) return;
        veil.setVisibility(View.GONE);
    }

    private boolean rebooting() { return rebootUntil > SystemClock.uptimeMillis(); }

    private void showVeil(String t, boolean spin, String btn, Runnable act) {
        veil.setVisibility(View.VISIBLE);
        veilText.setText(t);
        veilSpin.setVisibility(spin ? View.VISIBLE : View.GONE);
        veilAct = act;
        if (btn != null && act != null) { veilBtn.setText(btn); veilBtn.setVisibility(View.VISIBLE); }
        else veilBtn.setVisibility(View.GONE);
    }

    private void fail(String m) {
        Runnable again = loaded ? this::connect : this::load;
        showVeil(m, false, Ui.L("Thử lại", "Retry"), again);
    }

    /** Máy ảo vừa copy chữ → đưa vào bộ nhớ copy của điện thoại. */
    private void phoneCopied(String text) {
        if (text == null || text.isEmpty()) return;
        if (ownClip(text)) return;                                    // chính chữ app vừa dán sang
        try {
            ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Cloud Phone", text));
            Ui.toast(this, "📋 " + Ui.L("Đã copy từ máy ảo: ", "Copied from cloud phone: ") + (text.length() > 60 ? text.substring(0, 60) + "…" : text));
        } catch (Exception ignored) { }
    }

    private void rememberClip(String t) {
        sentClips.remove(t);
        sentClips.put(t, SystemClock.uptimeMillis());
        while (sentClips.size() > 16) sentClips.remove(sentClips.keySet().iterator().next());
    }

    private boolean ownClip(String t) {
        Long at = sentClips.get(t);
        return at != null && SystemClock.uptimeMillis() - at < 15000;
    }

    private boolean live() {
        if (client != null && client.isLive()) return true;
        Ui.toast(this, Ui.L("Đang kết nối máy, thử lại sau giây lát.", "Still connecting, try again in a moment."));
        return false;
    }

    // ---------------- Phím / lệnh Android ----------------
    private void cmd(String name) { if (live()) client.cmd(name); }

    private void press(int code) { if (client != null) client.press(code, 0); }

    /** Phím thật (bàn phím Bluetooth / USB) khi không gõ vào ô vô hình → gửi thẳng sang máy cloud. */
    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        if (client != null && client.isLive() && hardwareKey(e)) return true;
        return super.dispatchKeyEvent(e);
    }

    private boolean hardwareKey(KeyEvent e) {
        if (sink != null && sink.hasFocus()) return false;
        InputDevice d = e.getDevice();
        if (d == null || d.isVirtual() || d.getKeyboardType() != InputDevice.KEYBOARD_TYPE_ALPHABETIC) return false;
        if ((e.getSource() & InputDevice.SOURCE_KEYBOARD) != InputDevice.SOURCE_KEYBOARD) return false;
        int k = e.getKeyCode();
        if (k == KeyEvent.KEYCODE_BACK || k == KeyEvent.KEYCODE_VOLUME_UP || k == KeyEvent.KEYCODE_VOLUME_DOWN
                || k == KeyEvent.KEYCODE_VOLUME_MUTE || k == KeyEvent.KEYCODE_POWER || k == KeyEvent.KEYCODE_HOME) return false;
        if (e.getAction() == KeyEvent.ACTION_DOWN) client.key(StreamClient.KEY_DOWN, k, e.getMetaState());
        else if (e.getAction() == KeyEvent.ACTION_UP) client.key(StreamClient.KEY_UP, k, e.getMetaState());
        else return false;
        return true;
    }

    // ---------------- Bàn phím: ô gõ vô hình ----------------
    /** Hỏi máy cloud mỗi ~1 giây: có đang chờ gõ chữ không → tự hiện / ẩn bàn phím điện thoại (máy chủ không có /ime thì thôi hỏi). */
    private final Runnable kbPoll = new Runnable() {
        @Override public void run() {
            if (!resumed || id == null || kbDead) return;
            if (kbBusy || client == null) { h.postDelayed(this, 1200); return; }        // cả khi ẩn thanh / màn ngang (chat trong game)
            kbBusy = true;
            final String pid = id, base = api;
            Api.bg(() -> {
                try { return Api.cpAt(base, "GET", pid + "/ime", null); }
                catch (Api.ApiError e) { if (e.status == 404 || e.status == 405 || e.status == 501) return null; throw e; }
            }, j -> {
                kbBusy = false;
                if (j == null) { kbDead = true; return; }
                if (pid.equals(id)) {
                    boolean on = j.optBoolean("shown");
                    if (on) { kbOff = 0; if (!remoteIme) kbShow(true); remoteIme = true; }
                    else { remoteIme = false; if (kbOpen && ++kbOff >= 2) kbShow(false); }
                }
                if (resumed) h.postDelayed(this, 1000);
            }, m -> { kbBusy = false; if (resumed) h.postDelayed(this, 4000); });
        }
    };

    private void kbShow(boolean on) {
        kbOpen = on;
        InputMethodManager im = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (on) {
            sink.setFocusable(true);
            sink.setFocusableInTouchMode(true);
            sink.requestFocus();
            h.postDelayed(() -> { if (im != null && kbOpen) im.showSoftInput(sink, 0); }, 120);
        } else {
            if (im != null) im.hideSoftInputFromWindow(sink.getWindowToken(), 0);
            resetSink();
            sink.clearFocus();
            sink.setFocusable(false);
            sink.setFocusableInTouchMode(false);
        }
    }

    /** Chạm vào hình: chỗ gõ trên máy có thể đã đổi → làm trống ô gõ; máy vẫn đang chờ gõ mà bàn phím đã bị ẩn → bật lại. */
    private void touchedScreen() {
        if (!mirror.isEmpty() || sink.length() > 0) resetSink();
        if (remoteIme && kbOpen && !imeUp) h.postDelayed(() -> { if (remoteIme && kbOpen && !imeUp) kbShow(true); }, 350);
    }

    /** Ô gõ đổi chữ → so với phần đã gửi: gửi phím Xoá cho phần bị sửa + gõ phần mới (bộ gõ Telex / tự sửa chữ vẫn đúng). */
    private void sinkChanged(Editable e) {
        String now = e.toString(), old = mirror;
        int n = Math.min(old.length(), now.length()), p = 0;
        while (p < n && old.charAt(p) == now.charAt(p)) p++;
        if (p > 0 && p < Math.max(old.length(), now.length()) && Character.isHighSurrogate(now.charAt(p - 1))) p--;   // không cắt đôi emoji
        int dels = old.codePointCount(p, old.length());
        String add = now.substring(p);
        mirror = now;
        for (int i = 0; i < dels; i++) press(KeyEvent.KEYCODE_DEL);
        typeRemote(add);
        if (now.indexOf('\n') >= 0 || (now.length() > 64 && BaseInputConnection.getComposingSpanStart(e) < 0)) h.post(this::resetSink);
    }

    /** Gõ sang máy: chữ thường (ASCII) gõ bằng TEXT; chữ có dấu / emoji dán qua bộ nhớ copy để giữ dấu; xuống dòng = phím Enter. */
    private void typeRemote(String s) {
        if (s.isEmpty() || client == null) return;
        int i = 0;
        while (i < s.length()) {
            int nl = s.indexOf('\n', i);
            String part = nl < 0 ? s.substring(i) : s.substring(i, nl);
            if (!part.isEmpty()) {
                if (ascii(part)) client.text(part);
                else { rememberClip(part); client.clipSet(part, true); }
            }
            if (nl < 0) break;
            press(KeyEvent.KEYCODE_ENTER);
            i = nl + 1;
        }
    }

    private static boolean ascii(String s) {
        for (int i = 0; i < s.length(); i++) if (s.charAt(i) >= 0x80) return false;
        return true;
    }

    /** Phím từ bàn phím (ảo / thật) khi đang gõ vào ô vô hình. */
    private boolean sinkKey(int code, KeyEvent e) {
        boolean down = e.getAction() == KeyEvent.ACTION_DOWN;
        switch (code) {
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_NUMPAD_ENTER:
                if (down) { press(KeyEvent.KEYCODE_ENTER); h.post(this::resetSink); }
                return true;
            case KeyEvent.KEYCODE_DEL:
                if (sink.length() > 0) return false;               // ô còn chữ → ô tự xoá, phần so sánh gửi phím Xoá
                if (down) press(KeyEvent.KEYCODE_DEL);
                return true;
            case KeyEvent.KEYCODE_FORWARD_DEL:
            case KeyEvent.KEYCODE_TAB:
            case KeyEvent.KEYCODE_ESCAPE:
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_DPAD_DOWN:
            case KeyEvent.KEYCODE_DPAD_LEFT:
            case KeyEvent.KEYCODE_DPAD_RIGHT:
            case KeyEvent.KEYCODE_MOVE_HOME:
            case KeyEvent.KEYCODE_MOVE_END:
            case KeyEvent.KEYCODE_PAGE_UP:
            case KeyEvent.KEYCODE_PAGE_DOWN:
                if (client != null) client.key(down ? StreamClient.KEY_DOWN : StreamClient.KEY_UP, code, e.getMetaState());
                if (down) h.post(this::resetSink);                 // con trỏ trên máy đã dời → làm trống ô gõ
                return true;
            default:
                return false;
        }
    }

    private void resetSink() {
        if (sink == null || (mirror.isEmpty() && sink.length() == 0)) return;
        sinkMute = true;
        sink.setText("");
        sinkMute = false;
        mirror = "";
        InputMethodManager im = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (im != null && sink.hasFocus()) im.restartInput(sink);
    }

    /** Ô gõ vô hình: xoá khi ô đã trống vẫn báo ra để gửi phím Xoá sang máy cloud. */
    static final class ImeSink extends EditText {
        interface Deleter { void delete(int n); }
        Deleter onEmptyDelete;

        ImeSink(Context c) { super(c); }

        @Override public InputConnection onCreateInputConnection(EditorInfo out) {
            InputConnection ic = super.onCreateInputConnection(out);
            if (out != null) out.imeOptions |= EditorInfo.IME_FLAG_NO_EXTRACT_UI | EditorInfo.IME_FLAG_NO_FULLSCREEN;
            if (ic == null) return null;
            return new InputConnectionWrapper(ic, true) {
                @Override public boolean deleteSurroundingText(int before, int after) {
                    beyond(before);
                    return super.deleteSurroundingText(before, after);
                }

                @Override public boolean deleteSurroundingTextInCodePoints(int before, int after) {
                    beyond(before);
                    return super.deleteSurroundingTextInCodePoints(before, after);
                }
            };
        }

        private void beyond(int before) {
            int s = getSelectionStart(), e = getSelectionEnd();
            if (s != e) return;
            int n = before - Math.max(0, s);
            if (n > 0 && onEmptyDelete != null) onEmptyDelete.delete(n);
        }
    }

    // ---------------- Công cụ ----------------
    private void tools() {
        Ui.Wrap g = new Ui.Wrap(this, 6);
        final Dialog[] d = new Dialog[1];
        int w = (getResources().getDisplayMetrics().widthPixels - Ui.dp(64)) / 4;
        Object[][] items = {
                {"🔊", Ui.L("Tăng âm", "Vol +"), (Runnable) () -> cmd("volup")},
                {"🔉", Ui.L("Giảm âm", "Vol −"), (Runnable) () -> cmd("voldown")},
                {"⏻", Ui.L("Tắt/mở màn", "Power"), (Runnable) () -> cmd("power")},
                {"🔄", Ui.L("Xoay màn", "Rotate"), (Runnable) this::rotateMenu},
                {"📐", Ui.L("Độ rộng nhỏ nhất", "Smallest width"), (Runnable) this::smallestWidth},
                {"🔔", Ui.L("Thông báo", "Notifications"), (Runnable) () -> cmd("notif")},
                {"📷", Ui.L("Chụp màn", "Screenshot"), (Runnable) this::shot},
                {"⌨️", Ui.L("Bàn phím", "Keyboard"), (Runnable) () -> kbShow(!(kbOpen && imeUp))},
                {"📋", Ui.L("Dán chữ vào máy", "Paste into phone"), (Runnable) this::pasteFromPhone},
                {"📄", Ui.L("Copy từ máy", "Copy out"), (Runnable) this::copyFromPhone},
                {"📝", Ui.L("Gõ chữ", "Type text"), (Runnable) this::typeText},
                {"🌐", Ui.L("Mở web", "Open link"), (Runnable) this::openUrl},
                {"📦", Ui.L("Cài APK", "Install APK"), (Runnable) this::pickApk},
                {"🔗", Ui.L("Cài từ link", "From link"), (Runnable) this::fromLink},
                {"▦", Ui.L("Ứng dụng", "Apps"), (Runnable) this::apps},
                {"🧬", "Clone tab", (Runnable) this::cloneTab},
                {"📍", Ui.L("Vị trí GPS", "GPS"), (Runnable) this::gps},
                {"🔓", Ui.L("Root máy", "Root"), (Runnable) this::root},
                {"✨", Ui.L("Chất lượng", "Quality"), (Runnable) this::pickQuality},
                {"📊", Ui.L("Thông số", "Stats"), (Runnable) this::toggleStats},
                {"⛶", Ui.L("Ẩn thanh", "Hide bars"), (Runnable) () -> { autoFull = false; setFull(true); }},
                {"📱", Ui.L("Đổi máy", "Switch"), (Runnable) this::switchPhone},
                {"🤖", Ui.L("Đổi Android", "Android ver."), (Runnable) this::switchAndroid},
                {"↻", Ui.L("Tải lại hình", "Reload"), (Runnable) this::connect},
                {"⚡", Ui.L("Khởi động lại", "Reboot"), (Runnable) this::reboot},
        };
        for (Object[] it : items) {
            Runnable r = (Runnable) it[2];
            LinearLayout t = Ui.tool(this, (String) it[0], (String) it[1], v -> { if (d[0] != null) d[0].dismiss(); r.run(); });
            t.setLayoutParams(new FrameLayout.LayoutParams(w, -2));
            t.setMinimumWidth(w);
            g.addView(t, new android.view.ViewGroup.LayoutParams(w, -2));
        }
        d[0] = Ui.sheet(this, Ui.L("Công cụ", "Tools"), g);
        d[0].show();
    }

    private void toggleStats() {
        showStats = !showStats;
        pref.edit().putBoolean("stats", showStats).apply();
        stats.setText("…");
        stats.setVisibility(showStats ? View.VISIBLE : View.GONE);
    }

    private void cpPost(String path, JSONObject body, String okMsg) {
        final String base = api, pid = id;
        Api.bg(() -> Api.cpAt(base, "POST", pid + "/" + path, body), r -> { if (okMsg != null) Ui.toast(this, okMsg); }, m -> Ui.toast(this, m));
    }

    private void shot() {
        Ui.toast(this, Ui.L("Đang chụp…", "Capturing…"));
        final String base = api, pid = id;
        Api.bg(() -> Api.cpBytesAt(base, pid + "/shot?fresh=1"), png -> {          // fresh=1: luôn ảnh mới (máy chủ cũ bỏ qua)
            if (Build.VERSION.SDK_INT < 29) { Ui.toast(this, Ui.L("Cần Android 10 trở lên để lưu ảnh.", "Android 10+ required to save.")); return; }
            try {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.MediaColumns.DISPLAY_NAME, "cloudphone_" + System.currentTimeMillis() + ".png");
                cv.put(MediaStore.MediaColumns.MIME_TYPE, "image/png");
                cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/CloudBlue");
                Uri u = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cv);
                if (u == null) throw new Exception();
                try (OutputStream o = getContentResolver().openOutputStream(u)) { if (o != null) o.write(png); }
                Ui.toast(this, Ui.L("Đã lưu ảnh vào Thư viện › Pictures/CloudBlue", "Saved to Pictures/CloudBlue"));
            } catch (Exception e) { Ui.toast(this, Ui.L("Không lưu được ảnh.", "Could not save.")); }
        }, m -> Ui.toast(this, m));
    }

    private void askText(String title, String hint, String okLabel, int type, Api.Cb<String> on) {
        LinearLayout c = Ui.col(this, 12);
        EditText e = Ui.input(this, hint, type);
        c.addView(e, Ui.fill());
        Button ok = Ui.button(this, okLabel, Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, title, c);
        ok.setOnClickListener(v -> { String s = e.getText().toString(); if (s.trim().isEmpty()) return; d.dismiss(); on.ok(s); });
        d.show();
        e.requestFocus();
    }

    private void typeText() {
        askText(Ui.L("Gõ chữ vào máy", "Type into phone"), Ui.L("Nội dung (bấm vào ô nhập trên máy trước)", "Text (tap an input on the phone first)"),
                Ui.L("Gửi vào máy", "Send"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE,
                this::pasteText);
    }

    /** Dán chữ vào máy ảo (giữ được chữ có dấu): đặt bộ nhớ copy của máy + dán luôn (CLIP_SET paste = 1). */
    private void pasteText(String text) {
        if (!live()) return;
        rememberClip(text);
        client.clipSet(text, true);
        Ui.toast(this, Ui.L("Đang dán vào máy…", "Pasting…"));
    }

    /** "Dán chữ vào máy": lấy chữ trong bộ nhớ copy của điện thoại dán sang máy cloud. */
    private void pasteFromPhone() {
        ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        String text = "";
        try {
            if (cm != null && cm.hasPrimaryClip() && cm.getPrimaryClip() != null && cm.getPrimaryClip().getItemCount() > 0) {
                CharSequence c = cm.getPrimaryClip().getItemAt(0).coerceToText(this);
                if (c != null) text = c.toString();
            }
        } catch (Exception ignored) { }
        if (text.isEmpty()) { Ui.toast(this, Ui.L("Bộ nhớ copy của điện thoại đang trống — gõ chữ ở đây.", "Your clipboard is empty — type it here.")); typeText(); return; }
        pasteText(text);
    }

    /** Copy chữ đang bôi đen trên máy (Ctrl+C) — máy báo bộ nhớ copy mới → chữ tự về điện thoại. */
    private void copyFromPhone() {
        if (!live()) return;
        client.press(KeyEvent.KEYCODE_C, META_CTRL);
        Ui.toast(this, Ui.L("Đã copy chữ đang bôi đen trên máy — chữ tự về điện thoại. (Hoặc bôi đen chữ trên máy rồi bấm Copy)",
                "Copied the selected text — it comes to your phone automatically."));
    }

    private void openUrl() {
        askText(Ui.L("Mở link trên máy", "Open link on phone"), "https://…", Ui.L("Mở", "Open"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI,
                s -> { try { cpPost("url", new JSONObject().put("url", s.trim()), Ui.L("Đã mở trên máy.", "Opened.")); } catch (Exception ignored) { } });
    }

    private void fromLink() {
        askText(Ui.L("Cài APK từ link", "Install APK from link"), Ui.L("Link tải trực tiếp file .apk", "Direct .apk link"), Ui.L("Tải & cài", "Install"),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI, s -> {
                    Dialog[] pd = progress(Ui.L("Máy chủ đang tải file…", "Downloading on server…"));
                    final String base = api, pid = id;
                    Api.bg(() -> {
                        JSONObject j = Api.cpAt(base, "POST", pid + "/fromurl", new JSONObject().put("url", s.trim()));
                        return waitJob(base, j.optString("job"), pd);
                    }, msg -> { pd[0].dismiss(); Ui.toast(this, msg); }, m -> { pd[0].dismiss(); Ui.toast(this, m); });
                });
    }

    private void reboot() {
        Ui.confirm(this, Ui.L("Khởi động lại máy?", "Reboot phone?"), Ui.L("Máy tắt khoảng 1 phút rồi tự bật lại. Dữ liệu vẫn giữ.", "The phone restarts in about a minute. Data is kept."),
                Ui.L("Khởi động lại", "Reboot"), () -> {
                    cpPost("reboot", new JSONObject(), Ui.L("Đang khởi động lại…", "Rebooting…"));
                    rebootUntil = SystemClock.uptimeMillis() + 45000;
                    showVeil(Ui.L("Máy đang khởi động lại, khoảng 1 phút…", "Rebooting, about a minute…"), true, null, null);
                    h.removeCallbacks(afterReboot);
                    h.postDelayed(afterReboot, 45000);
                });
    }

    private final Runnable afterReboot = () -> {
        rebootUntil = 0;
        if (resumed && loaded) connect();
    };

    private void pickQuality() {
        LinearLayout c = Ui.col(this, 10);
        final Dialog[] d = new Dialog[1];
        String[] desc = {Ui.L("Tự đo mạng, chọn độ nét + khung hình hợp lý — khuyên dùng", "Measures your network, picks sharpness + FPS — recommended"),
                Ui.L("Nhẹ nhất, 30 FPS — mạng 4G/wifi yếu", "Lightest, 30 FPS — weak 4G/wifi"),
                Ui.L("Mượt 60 FPS, nét vừa", "Smooth 60 FPS"),
                Ui.L("Nét nhất, 60 FPS — cần mạng khoẻ", "Sharpest, 60 FPS — needs a fast network")};
        for (int i = 0; i < QUAL.length; i++) {
            final String k = QUAL[i][0];
            Button b = Ui.button(this, Ui.L(QUAL[i][1], QUAL[i][2]) + " — " + desc[i], k.equals(quality) ? Ui.PRIMARY : Ui.GHOST);
            b.setOnClickListener(v -> {
                d[0].dismiss();
                quality = k;
                pref.edit().putString("q", k).apply();
                updQ();
                if (client != null) client.quality(k);
            });
            c.addView(b, Ui.fill());
        }
        d[0] = Ui.sheet(this, Ui.L("Chất lượng hình", "Video quality"), c);
        d[0].show();
    }

    private void updQ() {
        View v = topBar.findViewWithTag("q");
        for (String[] q : QUAL) if (q[0].equals(quality) && v instanceof TextView) ((TextView) v).setText("✨ " + Ui.L(q[1], q[2]));
    }

    /** 🤖 Đổi Android 9 / 12 / 15 (chỉ chủ máy, SQL v24): máy mới giữ hạn còn lại; máy mới chạy xong thì máy cũ + dữ liệu cũ tự xoá. */
    private void switchAndroid() {
        final String pid = id;
        Api.<Object[]>bg(() -> {
            JSONArray a = (JSONArray) Api.get("cloud_phones?id=eq." + pid + "&select=*");
            if (a.length() == 0) throw new Exception(Ui.L("Không tìm thấy máy.", "Phone not found."));
            return new Object[]{a.getJSONObject(0), MainActivity.clampHard(Api.pricing()), Api.status(), Api.phones(), Api.profile()};
        }, r -> {
            if (!pid.equals(id) || isFinishing()) return;
            JSONObject p = (JSONObject) r[0];
            if (!Api.uid.equals(p.optString("user_id"))) { Ui.toast(this, Ui.L("Chỉ chủ máy mới đổi Android được.", "Only the owner can switch Android.")); return; }
            if (SwitchAndroid.switching(p, (JSONArray) r[3]) != null) { Ui.toast(this, Api.friendly(new Exception("SWITCHING"))); return; }
            if (!"active".equals(p.optString("status")) || MainActivity.locked(p)) { Ui.toast(this, Api.friendly(new Exception(MainActivity.locked(p) ? "PHONE_LOCKED" : "PHONE_NOT_ACTIVE"))); return; }
            boolean admin = "admin".equals(((JSONObject) r[4]).optString("role"));
            SwitchAndroid.open(this, p, (JSONObject) r[1], (JSONObject) r[2], admin, () -> {
                if (isTaskRoot()) startActivity(new Intent(this, MainActivity.class));     // mở từ link → về danh sách máy xem máy mới đang tạo
                finish();
            });
        }, m -> Ui.toast(this, m));
    }

    private void switchPhone() {
        Api.bg(Api::phones, list -> {
            LinearLayout c = Ui.col(this, 10);
            final Dialog[] d = new Dialog[1];
            for (int i = 0; i < list.length(); i++) {
                JSONObject p = list.optJSONObject(i);
                if (!"active".equals(p.optString("status")) || MainActivity.locked(p)) continue;
                boolean me = p.optString("id").equals(id);
                Button b = Ui.button(this, (me ? "● " : "") + p.optString("name") + " · " + p.optInt("ram") + "GB", me ? Ui.PRIMARY : Ui.GHOST);
                b.setOnClickListener(v -> {
                    d[0].dismiss();
                    if (me) return;
                    String nid = cleanId(p.optString("id"));
                    if (nid == null) return;
                    if (kbOpen) kbShow(false);
                    resetSink();
                    remoteIme = false;
                    id = nid;
                    load();
                });
                c.addView(b, Ui.fill());
            }
            if (c.getChildCount() == 0) c.addView(Ui.muted(this, Ui.L("Không có máy nào đang chạy.", "No running phones.")));
            d[0] = Ui.sheet(this, Ui.L("Chọn máy", "Choose phone"), c);
            d[0].show();
        }, m -> Ui.toast(this, m));
    }

    private void apps() {
        final String base = api, pid = id;
        Api.bg(() -> Api.cpAt(base, "GET", pid + "/apps", null), j -> {
            JSONArray a = j.optJSONArray("apps");
            LinearLayout c = Ui.col(this, 8);
            if (a == null || a.length() == 0) c.addView(Ui.muted(this, Ui.L("Chưa có ứng dụng nào do bạn cài.", "No user-installed apps.")));
            else for (int i = 0; i < a.length(); i++) {
                String pkg = a.optString(i);
                LinearLayout r = Ui.row(this, 6);
                TextView n = Ui.text(this, pkg, 13, Ui.FG, false);
                n.setSingleLine(true);
                n.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
                r.addView(n, Ui.weight(1));
                Button open = Ui.button(this, Ui.L("Mở", "Open"), Ui.GHOST);
                open.setMinWidth(0);
                open.setOnClickListener(v -> { try { cpPost("launch", new JSONObject().put("pkg", pkg), Ui.L("Đã mở ", "Opened ") + pkg); } catch (Exception ignored) { } });
                r.addView(open, Ui.wrap());
                Button stop = Ui.button(this, Ui.L("Dừng", "Stop"), Ui.GHOST);
                stop.setMinWidth(0);
                stop.setOnClickListener(v -> { try { cpPost("stop", new JSONObject().put("pkg", pkg), Ui.L("Đã dừng ", "Stopped ") + pkg); } catch (Exception ignored) { } });
                r.addView(stop, Ui.wrap());
                Button del = Ui.button(this, Ui.L("Gỡ", "Remove"), Ui.DANGER);
                del.setMinWidth(0);
                del.setOnClickListener(v -> Ui.confirm(this, Ui.L("Gỡ ứng dụng?", "Uninstall?"), pkg, Ui.L("Gỡ", "Remove"), () -> {
                    try { cpPost("uninstall", new JSONObject().put("pkg", pkg), Ui.L("Đã gỡ ", "Removed ") + pkg); r.setVisibility(View.GONE); } catch (Exception ignored) { }
                }));
                r.addView(del, Ui.wrap());
                c.addView(r, Ui.fill());
            }
            Ui.sheet(this, Ui.L("Ứng dụng trên máy", "Apps on phone"), c).show();
        }, m -> Ui.toast(this, m));
    }


    // ---------------- Clone tab: chạy thêm bản của 1 app (game…) để đăng nhập acc khác ----------------
    private void cloneTab() {
        Dialog[] pd = progress(Ui.L("Đang tải danh sách app…", "Loading apps…"));
        final String base = api, pid = id;
        Api.bg(() -> new JSONObject[]{Api.cpAt(base, "GET", pid + "/apps", null), Api.cpAt(base, "GET", pid + "/clone", null)}, js -> {
            pd[0].dismiss();
            JSONArray a = js[0].optJSONArray("apps");
            JSONObject cnt = js[1].optJSONObject("counts");
            int mx = js[1].optInt("max", 4);
            LinearLayout c = Ui.col(this, 10);
            final Dialog[] d = new Dialog[1];
            c.addView(Ui.muted(this, Ui.L("Tạo thêm bản của app (VD game) để đăng nhập acc khác, chạy song song bản chính. Bản clone hiện thành biểu tượng \"Clone 1, 2…\" trên màn hình chính của máy, hoặc bấm ▶ ở đây.",
                    "Make extra copies of an app (e.g. a game) for other accounts. Clones show as \"Clone 1, 2…\" icons on the phone's home screen, or tap ▶ here.")));
            if (a == null || a.length() == 0) c.addView(Ui.muted(this, Ui.L("Chưa có app nào. Cài app (VD game từ CH Play) trước.", "No apps yet. Install one first (e.g. a game from Play Store).")));
            else for (int i = 0; i < a.length(); i++) {
                String pkg = a.optString(i);
                int k = cnt != null ? cnt.optInt(pkg, 0) : 0;
                LinearLayout card = Ui.card(this);
                TextView n = Ui.text(this, (k > 0 ? "🧬 " : "") + pkg + (k > 0 ? Ui.L("  ·  " + k + " bản clone", "  ·  " + k + " clone(s)") : ""), 13, Ui.FG, k > 0);
                n.setSingleLine(true); n.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
                card.addView(n, Ui.fill());
                Ui.Wrap w = new Ui.Wrap(this, 6);
                for (int x = 1; x <= k; x++) {
                    final int ci = x;
                    Button op = Ui.button(this, "▶ " + Ui.L("Mở ", "Open ") + ci, Ui.PRIMARY);
                    op.setMinWidth(0);
                    op.setOnClickListener(v -> { try { cpPost("clone", new JSONObject().put("pkg", pkg).put("open", ci), Ui.L("Đang mở bản clone ", "Opening clone ") + ci + "…"); if (d[0] != null) d[0].dismiss(); } catch (Exception ignored) { } });
                    w.addView(op);
                }
                // SỐ BẢN CLONE muốn có (tổng): chọn 1…mx rồi bấm Tạo
                final int[] want = {Math.min(mx, k + 1)};
                Ui.Wrap qn = new Ui.Wrap(this, 6);
                Button add = Ui.button(this, "", Ui.PRIMARY);
                add.setMinWidth(0);
                Runnable paint = () -> {
                    for (int z = 0; z < qn.getChildCount(); z++) Ui.setChip((TextView) qn.getChildAt(z), (int) qn.getChildAt(z).getTag() == want[0]);
                    boolean more = want[0] > k;
                    add.setText(more ? Ui.L("Tạo " + want[0] + " bản clone", "Make " + want[0] + " clone(s)") : Ui.L("Đã có " + k + " bản", k + " already"));
                    add.setEnabled(more); add.setAlpha(more ? 1f : .5f);
                };
                for (int q = 1; q <= mx; q++) {
                    TextView ch = Ui.chip(this, q + Ui.L(" bản", ""), q == want[0]);
                    ch.setTag(q);
                    ch.setOnClickListener(v -> { want[0] = (int) v.getTag(); paint.run(); });
                    qn.addView(ch);
                }
                card.addView(Ui.text(this, Ui.L("Số bản clone muốn có (tổng, tối đa " + mx + ")", "Total clones wanted (max " + mx + ")"), 12, Ui.MUTED, false), Ui.fill());
                card.addView(qn, Ui.fill());
                add.setOnClickListener(v -> {
                    if (d[0] != null) d[0].dismiss();
                    final int nWant = want[0];
                    Dialog[] p2 = progress(Ui.L("Đang tạo " + nWant + " bản clone (mỗi bản ~20 giây)…", "Creating " + nWant + " clone(s) (~20s each)…"));
                    Api.bg(() -> {
                        JSONObject j = Api.cpAt(base, "POST", pid + "/clone", new JSONObject().put("pkg", pkg).put("n", nWant));
                        return waitJob(base, j.optString("job"), p2);
                    }, msg -> { p2[0].dismiss(); Ui.toast(this, msg); }, m -> { p2[0].dismiss(); Ui.toast(this, m); });
                });
                paint.run();
                w.addView(add);
                if (k > 0) {
                    Button rm = Ui.button(this, Ui.L("Bỏ clone", "Remove"), Ui.DANGER);
                    rm.setMinWidth(0);
                    rm.setOnClickListener(v -> Ui.confirm(this, Ui.L("Bỏ tất cả bản clone?", "Remove all clones?"),
                            Ui.L("Acc đăng nhập trong các bản clone sẽ bị xoá.", "Accounts signed in to the clones will be removed."), Ui.L("Bỏ clone", "Remove"), () -> {
                                try { cpPost("clone", new JSONObject().put("pkg", pkg).put("remove", true), Ui.L("Đã bỏ bản clone.", "Clones removed.")); if (d[0] != null) d[0].dismiss(); } catch (Exception ignored) { }
                            }));
                    w.addView(rm);
                }
                card.addView(w, Ui.fill());
                c.addView(card, Ui.fill());
            }
            android.widget.ScrollView sv = new android.widget.ScrollView(this);
            sv.addView(c);
            d[0] = Ui.sheet(this, "🧬 Clone tab", sv);
            d[0].show();
        }, m -> { pd[0].dismiss(); Ui.toast(this, m); });
    }

    // ---------------- Vị trí GPS giả ----------------
    private void gps() {
        String last = getSharedPreferences("cp", MODE_PRIVATE).getString("gps_" + id, "");
        LinearLayout c = Ui.col(this, 10);
        c.addView(Ui.muted(this, Ui.L("Nhập toạ độ dạng: vĩ độ, kinh độ (lấy trên Google Maps: giữ tay vào 1 điểm → copy số). VD Hà Nội: 21.0285, 105.8542",
                "Enter: latitude, longitude (from Google Maps). E.g. 21.0285, 105.8542")));
        EditText e = Ui.input(this, "21.0285, 105.8542", InputType.TYPE_CLASS_TEXT);
        e.setText(last);
        c.addView(e, Ui.fill());
        LinearLayout r = Ui.row(this, 10);
        Button off = Ui.button(this, Ui.L("Tắt vị trí giả", "Turn off"), Ui.GHOST);
        Button ok = Ui.button(this, Ui.L("Đặt vị trí", "Set location"), Ui.PRIMARY);
        r.addView(off, Ui.weight(1)); r.addView(ok, Ui.weight(1));
        c.addView(r, Ui.fill());
        Dialog d = Ui.sheet(this, "📍 " + Ui.L("Vị trí GPS", "GPS location"), c);
        ok.setOnClickListener(v -> {
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("(-?\\d+(?:\\.\\d+)?)\\s*[,; ]\\s*(-?\\d+(?:\\.\\d+)?)").matcher(e.getText().toString());
            if (!m.find()) { Ui.toast(this, Ui.L("Nhập dạng: 21.0285, 105.8542", "Format: 21.0285, 105.8542")); return; }
            try {
                getSharedPreferences("cp", MODE_PRIVATE).edit().putString("gps_" + id, m.group(1) + ", " + m.group(2)).apply();
                cpPost("gps", new JSONObject().put("lat", Double.parseDouble(m.group(1))).put("lng", Double.parseDouble(m.group(2))), Ui.L("Đã đặt vị trí. Mở lại app cần vị trí.", "Location set."));
            } catch (Exception ignored) { }
            d.dismiss();
        });
        off.setOnClickListener(v -> { try { cpPost("gps", new JSONObject().put("off", true), Ui.L("Đã tắt vị trí giả.", "Mock location off.")); } catch (Exception ignored) { } d.dismiss(); });
        d.show();
    }

    // ---------------- Root máy ----------------
    private void root() {
        Dialog[] pd = progress(Ui.L("Đang kiểm tra / bật root…", "Checking root…"));
        final String base = api, pid = id;
        Api.bg(() -> {
            JSONObject j = Api.cpAt(base, "POST", pid + "/root", new JSONObject());
            return waitJob(base, j.optString("job"), pd);
        }, msg -> { pd[0].dismiss(); Ui.toast(this, msg); }, m -> { pd[0].dismiss(); Ui.toast(this, m); });
    }

    // ---------------- Cài APK / gửi file từ điện thoại ----------------
    private void pickApk() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        try { startActivityForResult(i, REQ_APK); }
        catch (Exception e) { Ui.toast(this, Ui.L("Không mở được trình chọn file.", "Cannot open file picker.")); }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req != REQ_APK || res != RESULT_OK || data == null || data.getData() == null) return;
        Uri u = data.getData();
        String name = "file";
        long size = -1;
        try (Cursor c = getContentResolver().query(u, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME), si = c.getColumnIndex(OpenableColumns.SIZE);
                if (ni >= 0) name = c.getString(ni);
                if (si >= 0) size = c.getLong(si);
            }
        } catch (Exception ignored) { }
        if (size <= 0) { Ui.toast(this, Ui.L("Không đọc được file.", "Cannot read file.")); return; }
        if (size > 4L * 1073741824L) { Ui.toast(this, Ui.L("File lớn hơn 4GB.", "File larger than 4GB.")); return; }
        upload(u, name, size);
    }

    private void upload(Uri u, String name, long size) {
        boolean apk = name.toLowerCase(java.util.Locale.ROOT).endsWith(".apk");
        Dialog[] pd = progress(Ui.L("Đang gửi ", "Uploading ") + name);
        final String fname = name, base = api, pid = id;
        Api.bg(() -> {
            String upid = Long.toString(System.currentTimeMillis(), 36) + Integer.toString(new Random().nextInt(1 << 30), 36);
            int CH = 8 * 1024 * 1024;
            long off = 0;
            String job = null;
            try (InputStream in = getContentResolver().openInputStream(u)) {
                if (in == null) throw new Exception(Ui.L("Không đọc được file.", "Cannot read file."));
                byte[] buf = new byte[CH];
                while (off < size) {
                    int n = 0;
                    while (n < CH) { int k = in.read(buf, n, CH - n); if (k < 0) break; n += k; }
                    if (n == 0) break;
                    byte[] chunk = n == CH ? buf : java.util.Arrays.copyOf(buf, n);
                    String path = pid + "/upload?id=" + upid + "&name=" + URLEncoder.encode(fname, "UTF-8") + "&total=" + size + "&off=" + off;
                    JSONObject j = null;
                    for (int t = 1; ; t++) {
                        try { j = Api.cpUploadAt(base, path, chunk); break; }
                        catch (Api.ApiError e) { if (e.status < 500 || t > 4) throw e; Thread.sleep(1500L * t); }
                        catch (java.io.IOException e) { if (t > 4) throw e; Thread.sleep(1500L * t); }
                    }
                    off += n;
                    final int pct = (int) (off * 100 / size);
                    Api.ui(() -> setProgress(pd, Ui.L("Đang gửi ", "Uploading ") + fname + " · " + pct + "%"));
                    if (j.has("job")) { job = j.optString("job"); break; }
                }
            }
            if (job == null) throw new Exception(Ui.L("Gửi file chưa xong, thử lại.", "Upload incomplete, retry."));
            Api.ui(() -> setProgress(pd, apk ? Ui.L("Đang cài ứng dụng…", "Installing…") : Ui.L("Đang chép vào máy…", "Copying…")));
            return waitJob(base, job, pd);
        }, msg -> { pd[0].dismiss(); Ui.toast(this, msg); }, m -> { pd[0].dismiss(); Ui.toast(this, m); });
    }

    private String waitJob(String base, String job, Dialog[] pd) throws Exception {
        for (int i = 0; i < 900; i++) {
            Thread.sleep(1500);
            JSONObject j = Api.cpAt(base, "GET", "job?id=" + job, null);
            String st = j.optString("state"), msg = j.optString("msg");
            Api.ui(() -> setProgress(pd, msg));
            if ("done".equals(st)) return "✅ " + msg;
            if ("error".equals(st)) throw new Exception(msg);
        }
        throw new Exception(Ui.L("Quá lâu, kiểm tra lại trên máy.", "Timed out."));
    }

    private Dialog[] progress(String text) {
        LinearLayout c = Ui.col(this, 12);
        ProgressBar pb = new ProgressBar(this);
        c.addView(pb, Ui.wrap());
        TextView t = Ui.text(this, text, 14, Ui.FG, false);
        t.setTag("ptext");
        c.addView(t, Ui.fill());
        Dialog d = Ui.sheet(this, null, c);
        d.setCancelable(false);
        d.show();
        return new Dialog[]{d};
    }

    private void setProgress(Dialog[] pd, String text) {
        try {
            View v = pd[0].getWindow().getDecorView().findViewWithTag("ptext");
            if (v instanceof TextView) ((TextView) v).setText(text);
        } catch (Exception ignored) { }
    }

    // ---------------- Xoay màn: máy cloud ngang / dọc ↔ app điện thoại ----------------
    /** Máy chủ báo cỡ hình. Đổi hướng (ngang ↔ dọc) → app xoay theo (nếu bật) — khỏi phải nghiêng đầu xem màn ngang. */
    private void videoSized(int w, int h) {
        if (w <= 0 || h <= 0) return;
        boolean land = w > h;
        if (haveSize && land == streamLand) return;                 // chỉ đổi độ nét (cùng hướng) → thôi
        haveSize = true;
        streamLand = land;
        applyRotation();
    }

    private void applyRotation() {
        if (!autoRot) {                                              // tắt: app xoay theo cách khách cầm điện thoại (như trước)
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);
            if (autoFull && full) setFull(false);
            autoFull = false;
            return;
        }
        if (!haveSize) return;
        setRequestedOrientation(streamLand ? ActivityInfo.SCREEN_ORIENTATION_USER_LANDSCAPE : ActivityInfo.SCREEN_ORIENTATION_USER_PORTRAIT);
        if (streamLand && !full) { autoFull = true; setFull(true); }              // ngang: ẩn thanh → hình to hết màn, còn nút nổi
        else if (!streamLand && full && autoFull) { setFull(false); autoFull = false; }   // về dọc: trả thanh (nếu do app tự ẩn)
    }

    /** Nút 🔄: đổi sang hướng kia. */
    private void quickRotate() { rotateTo(!streamLand); }

    /** Khoá màn máy cloud ngang / dọc qua cổng công cụ (mọi máy chủ đều có); không tới được thì gửi qua luồng hình. */
    private void rotateTo(boolean land) {
        if (id == null || !live()) return;
        Ui.toast(this, land ? Ui.L("Đang xoay ngang…", "Rotating to landscape…") : Ui.L("Đang xoay dọc…", "Rotating to portrait…"));
        final String base = api, pid = id, to = land ? "land" : "port";
        final JSONObject b = new JSONObject();
        try { b.put("to", to).put("dir", land ? 1 : 0); } catch (Exception ignored) { }
        Api.bg(() -> Api.cpAt(base, "POST", pid + "/rotate", b), r -> checkRotated(land), m -> {
            if (client != null && client.isLive()) { client.rotate(to); checkRotated(land); }
            else Ui.toast(this, m);
        });
    }

    /** 3,5 giây sau hình vẫn chưa đổi hướng: app đang mở trên máy chỉ chạy 1 hướng → nói rõ cho khách (khỏi tưởng nút hỏng). */
    private void checkRotated(boolean land) {
        h.postDelayed(() -> {
            if (isFinishing() || client == null || streamLand == land) return;
            Ui.toast(this, land ? Ui.L("Đã khoá màn NGANG. App đang mở chỉ chạy màn dọc nên chưa xoay — mở game / app hỗ trợ ngang là tự ngang.",
                            "Landscape is locked. The open app is portrait-only — apps that support landscape will rotate.")
                    : Ui.L("Đã khoá màn DỌC. App đang mở chỉ chạy màn ngang nên chưa xoay.", "Portrait is locked. The open app is landscape-only."));
        }, 3500);
    }

    private void rotateMenu() {
        LinearLayout c = Ui.col(this, 10);
        final Dialog[] d = new Dialog[1];
        c.addView(Ui.muted(this, Ui.L("Khoá màn máy cloud theo hướng bạn chọn (giữ luôn cả khi tắt app). Game cần màn ngang vẫn tự xoay ngang.",
                "Locks the cloud phone's orientation (kept after you leave). Landscape games still rotate by themselves.")));
        LinearLayout r = Ui.row(this, 10);
        Button land = Ui.button(this, "▭  " + Ui.L("Màn ngang", "Landscape"), streamLand ? Ui.PRIMARY : Ui.GHOST);
        Button port = Ui.button(this, "▯  " + Ui.L("Màn dọc", "Portrait"), streamLand ? Ui.GHOST : Ui.PRIMARY);
        r.addView(land, Ui.weight(1));
        r.addView(port, Ui.weight(1));
        c.addView(r, Ui.fill());
        Button auto = Ui.button(this, "", Ui.GHOST);
        Runnable paint = () -> auto.setText((autoRot ? "✓  " : "✗  ") + Ui.L("App tự xoay theo máy: ", "Follow the cloud phone: ") + (autoRot ? Ui.L("BẬT", "ON") : Ui.L("TẮT", "OFF")));
        paint.run();
        c.addView(auto, Ui.fill());
        c.addView(Ui.muted(this, Ui.L("BẬT: máy cloud ngang thì app cũng ngang + ẩn thanh cho hình to nhất. TẮT: app xoay theo cách bạn cầm điện thoại.",
                "ON: when the cloud phone turns landscape, this app turns too and hides the bars. OFF: the app follows how you hold your phone.")));
        land.setOnClickListener(v -> { d[0].dismiss(); rotateTo(true); });
        port.setOnClickListener(v -> { d[0].dismiss(); rotateTo(false); });
        auto.setOnClickListener(v -> { autoRot = !autoRot; pref.edit().putBoolean("auto_rot", autoRot).apply(); paint.run(); applyRotation(); });
        d[0] = Ui.sheet(this, "🔄 " + Ui.L("Xoay màn", "Rotate"), c);
        d[0].show();
    }

    // ---------------- Độ rộng nhỏ nhất (Smallest width / DPI) ----------------
    private void smallestWidth() {
        if (id == null) return;
        Dialog[] pd = progress(Ui.L("Đang đọc màn hình máy…", "Reading the screen…"));
        final String base = api, pid = id;
        Api.bg(() -> Api.cpAt(base, "GET", pid + "/density", null), j -> {
            pd[0].dismiss();
            final int sw = j.optInt("sw"), def = j.optInt("sw_default");
            LinearLayout c = Ui.col(this, 10);
            final Dialog[] d = new Dialog[1];
            c.addView(Ui.muted(this, Ui.L("Như \"Độ rộng nhỏ nhất\" trong Tuỳ chọn nhà phát triển: số càng LỚN thì chữ, biểu tượng, cửa sổ app càng NHỎ — màn chứa được nhiều hơn (VD xếp nhiều tab clone). Mặc định của máy: ",
                    "Like \"Smallest width\" in Developer options: a BIGGER number makes text, icons and app windows SMALLER. Default: ") + def + " dp."));
            c.addView(Ui.text(this, Ui.L("Đang dùng: ", "Current: ") + sw + " dp", 15, Ui.FG, true), Ui.fill());
            Ui.Wrap g = new Ui.Wrap(this, 6);
            for (int v : new int[]{320, 360, 411, 480, 540, 600, 720, 800}) {
                TextView ch = Ui.chip(this, v + " dp", v == sw);
                ch.setOnClickListener(x -> { d[0].dismiss(); setDensity(v, false); });
                g.addView(ch);
            }
            c.addView(g, Ui.fill());
            LinearLayout r = Ui.row(this, 8);
            EditText e = Ui.input(this, Ui.L("Số khác, VD 450", "Other, e.g. 450"), InputType.TYPE_CLASS_NUMBER);
            r.addView(e, Ui.weight(1));
            Button ok = Ui.button(this, Ui.L("Đặt", "Set"), Ui.PRIMARY);
            r.addView(ok, Ui.wrap());
            c.addView(r, Ui.fill());
            Button reset = Ui.button(this, Ui.L("Trả về mặc định", "Reset to default") + " (" + def + " dp)", Ui.GHOST);
            c.addView(reset, Ui.fill());
            ok.setOnClickListener(x -> {
                int v;
                try { v = Integer.parseInt(e.getText().toString().trim()); } catch (Exception ex) { v = 0; }
                if (v < 240 || v > 1600) { Ui.toast(this, Ui.L("Nhập từ 240 đến 1600 dp.", "Enter 240–1600 dp.")); return; }
                d[0].dismiss();
                setDensity(v, false);
            });
            reset.setOnClickListener(x -> { d[0].dismiss(); setDensity(0, true); });
            d[0] = Ui.sheet(this, "📐 " + Ui.L("Độ rộng nhỏ nhất", "Smallest width"), c);
            d[0].show();
        }, m -> { pd[0].dismiss(); Ui.toast(this, missing(m)); });
    }

    private void setDensity(int sw, boolean reset) {
        Dialog[] pd = progress(Ui.L("Đang đổi…", "Applying…"));
        final String base = api, pid = id;
        final JSONObject b = new JSONObject();
        try { if (reset) b.put("reset", true); else b.put("sw", sw); } catch (Exception ignored) { }
        Api.bg(() -> Api.cpAt(base, "POST", pid + "/density", b), j -> { pd[0].dismiss(); Ui.toast(this, j.optString("msg", Ui.L("Đã đổi.", "Done."))); },
                m -> { pd[0].dismiss(); Ui.toast(this, missing(m)); });
    }

    /** Máy chủ chưa lên bản có chức năng này → nói rõ thay vì lỗi khó hiểu. */
    private static String missing(String m) {
        return m != null && m.contains("Không có chức năng") ? Ui.L("Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau.",
                "This phone's server doesn't have this feature yet — try again later.") : m;
    }

    // ---------------- Nút nổi + thanh nút nhỏ (khi ẩn thanh) ----------------
    private final Runnable hideMiniR = this::hideMini;

    private void paintBall() {
        if (ball == null) return;
        int ring = ping < 0 ? Color.rgb(140, 150, 170) : ping < 80 ? Color.rgb(46, 204, 113) : ping < 160 ? Color.rgb(255, 196, 61) : Color.rgb(255, 92, 108);
        ball.setText(ping < 0 ? "•••" : ping + "\nms");
        ball.setTextColor(ring);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(Color.argb(200, 8, 12, 22));
        g.setStroke(Ui.dp(2), ring);
        ball.setBackground(g);
    }

    private void restoreBall() {
        int bs = Ui.dp(48), W = stage.getWidth() - bs, H = stage.getHeight() - bs;
        if (W <= 0 || H <= 0) return;
        ball.setX(W * Math.max(0f, Math.min(1f, pref.getFloat("ball_x", 0f))));
        ball.setY(H * Math.max(0f, Math.min(1f, pref.getFloat("ball_y", 0.3f))));
    }

    private void saveBall() {
        int bs = Ui.dp(48), W = stage.getWidth() - bs, H = stage.getHeight() - bs;
        if (W > 0 && H > 0) pref.edit().putFloat("ball_x", ball.getX() / W).putFloat("ball_y", ball.getY() / H).apply();
    }

    /** Thanh nút nhỏ nằm cạnh nút nổi (bên phải nếu nút ở nửa trái màn, ngược lại bên trái). */
    private void placeMini() {
        mini.measure(View.MeasureSpec.UNSPECIFIED, View.MeasureSpec.UNSPECIFIED);
        int mw = mini.getMeasuredWidth(), bs = Ui.dp(48), gap = Ui.dp(6), W = stage.getWidth(), H = stage.getHeight();
        float bx = ball.getX();
        float x = bx + bs / 2f < W / 2f ? bx + bs + gap : bx - mw - gap;
        mini.setX(Math.max(0, Math.min(Math.max(0, W - mw), x)));
        mini.setY(Math.max(0, Math.min(Math.max(0, H - bs), ball.getY())));
    }

    private void toggleMini() {
        if (mini.getVisibility() == View.VISIBLE) { hideMini(); return; }
        mini.setVisibility(View.VISIBLE);
        placeMini();
        armMini();
    }

    /** Thanh nút nhỏ tự ẩn sau 5 giây không bấm (bấm nút nào cũng tính lại từ đầu — bấm Quay lại liên tiếp được). */
    private void armMini() {
        h.removeCallbacks(hideMiniR);
        if (mini != null && mini.getVisibility() == View.VISIBLE) h.postDelayed(hideMiniR, 5000);
    }

    private void hideMini() {
        h.removeCallbacks(hideMiniR);
        if (mini != null) mini.setVisibility(View.GONE);
    }

    /** Kéo nút nổi để dời chỗ (nhớ chỗ cho lần sau); chạm nhẹ = bấm. */
    private final class BallDrag implements View.OnTouchListener {
        private float sx, sy, ox, oy;
        private boolean moved;

        @Override public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    sx = e.getRawX(); sy = e.getRawY(); ox = v.getX(); oy = v.getY(); moved = false;
                    return true;
                case MotionEvent.ACTION_MOVE: {
                    float dx = e.getRawX() - sx, dy = e.getRawY() - sy;
                    if (!moved && Math.hypot(dx, dy) < ViewConfiguration.get(ControlActivity.this).getScaledTouchSlop()) return true;
                    moved = true;
                    v.setX(Math.max(0, Math.min(Math.max(0, stage.getWidth() - v.getWidth()), ox + dx)));
                    v.setY(Math.max(0, Math.min(Math.max(0, stage.getHeight() - v.getHeight()), oy + dy)));
                    if (mini.getVisibility() == View.VISIBLE) { placeMini(); armMini(); }
                    return true;
                }
                case MotionEvent.ACTION_UP:
                    if (moved) saveBall(); else v.performClick();
                    return true;
                case MotionEvent.ACTION_CANCEL:
                    if (moved) saveBall();
                    return true;
                default:
                    return false;
            }
        }
    }

    // ---------------- Ẩn / hiện thanh (toàn màn hình) ----------------
    private void setFull(boolean on) {
        full = on;
        if (!autoFull) pref.edit().putBoolean("full", on).apply();   // khách tự bấm ẩn / hiện → nhớ cho lần mở sau (tự ẩn khi máy ngang thì không nhớ)
        topBar.setVisibility(on ? View.GONE : View.VISIBLE);
        navBar.setVisibility(on ? View.GONE : View.VISIBLE);
        ball.setVisibility(on ? View.VISIBLE : View.GONE);
        if (on) ball.post(this::restoreBall);
        else hideMini();
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                if (on) { c.hide(WindowInsets.Type.systemBars()); c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE); }
                else c.show(WindowInsets.Type.systemBars());
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(on ? View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    : View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {                                     // Android 15 trở xuống (16 + targetSdk 36 dùng backCb)
        if (!handleBack()) super.onBackPressed();
    }

    /** Back khi đang ẩn thanh: đóng thanh nút nhỏ / hiện lại thanh — không thoát màn điều khiển (game ngang tự ẩn thanh, vuốt nhầm mép màn rất hay gặp). */
    private boolean handleBack() {
        if (!full) return false;
        if (mini.getVisibility() == View.VISIBLE) { hideMini(); return true; }
        autoFull = false;
        setFull(false);
        return true;
    }
}
