package shop.blueroblox.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Shader;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Build;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.ImageView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.NumberFormat;
import java.util.Locale;

/** Màu, chữ, nút, thẻ… dùng chung cho mọi màn hình.
 *  Giao diện CLOUD BLUE (mệnh Thuỷ) giống web: 2 chế độ Sáng / Tối, nền chấm bong bóng, viền xanh neon. */
public final class Ui {
    public static int BG, PANEL, PANEL2, LINE, LINE2, FG, MUTED, BLUE, SKY, OK, WAIT, BAD, SUNK, RING, HINT, MONEY;   // MONEY: màu tiền & ưu đãi (28/11 bản 5 "Arctic Glow": băng #a7f3ff tối · xanh điện #0b5fff sáng — cùng web)
    public static boolean LIGHT;
    static { apply(false); }

    /** Đổi bảng màu. light = Thuỷ ngày (nền trắng bạc), ngược lại = Thuỷ đêm (xanh mực). */
    public static void apply(boolean light) {
        LIGHT = light;
        if (light) {
            BG = Color.rgb(243, 247, 252); PANEL = Color.rgb(255, 255, 255); PANEL2 = Color.rgb(238, 245, 255);
            LINE = Color.argb(41, 43, 110, 240); LINE2 = Color.argb(77, 43, 110, 240);
            FG = Color.rgb(10, 26, 58); MUTED = Color.rgb(74, 93, 130); BLUE = Color.rgb(43, 110, 240); SKY = Color.rgb(15, 63, 179);
            OK = Color.rgb(14, 159, 116); WAIT = Color.rgb(178, 107, 0); BAD = Color.rgb(224, 53, 79); MONEY = Color.rgb(11, 95, 255);
            SUNK = Color.rgb(238, 244, 252); RING = Color.argb(77, 70, 165, 255); HINT = Color.argb(150, 74, 93, 130);
        } else {
            BG = Color.rgb(7, 18, 38); PANEL = Color.rgb(13, 29, 61); PANEL2 = Color.rgb(16, 36, 74);
            LINE = Color.argb(56, 90, 175, 255); LINE2 = Color.argb(92, 90, 175, 255);
            FG = Color.rgb(232, 241, 255); MUTED = Color.rgb(159, 180, 216); BLUE = Color.rgb(61, 134, 255); SKY = Color.rgb(140, 196, 255);
            OK = Color.rgb(60, 224, 176); WAIT = Color.rgb(255, 214, 102); BAD = Color.rgb(255, 107, 129); MONEY = Color.rgb(167, 243, 255);
            SUNK = Color.rgb(6, 17, 42); RING = Color.argb(77, 90, 175, 255); HINT = Color.argb(150, 159, 180, 216);
        }
        bubbles = null;
    }

    /** Lưu lựa chọn Sáng/Tối (lần đầu: theo cài đặt của máy). */
    public static void setLight(Context c, boolean light) {
        c.getSharedPreferences("ui", Context.MODE_PRIVATE).edit().putString("theme", light ? "light" : "dark").apply();
        apply(light);
    }

    // 16/11c · NGÔN NGỮ do khách chọn (màn đăng nhập / Tài khoản › Giao diện): "vi" | "en" · chưa chọn → theo ngôn ngữ của máy
    public static volatile String lang = null;
    public static void loadLang(Context c) { try { lang = c.getSharedPreferences("ui", Context.MODE_PRIVATE).getString("lang", null); } catch (Exception ignored) { } }
    public static void setLang(Context c, String l) { lang = l; c.getSharedPreferences("ui", Context.MODE_PRIVATE).edit().putString("lang", l).apply(); }
    public static boolean vi() { String l = lang; return l != null ? "vi".equals(l) : "vi".equals(Locale.getDefault().getLanguage()); }
    public static String L(String vi, String en) { return vi() ? vi : en; }
    /** Câu MÁY CHỦ (luôn tiếng Việt) theo ngôn ngữ khách chọn: English → bảng dịch Srv, không có → câu tiếng Anh chung. */
    public static String srv(String s) { return vi() ? s : Srv.en(s, false, null); }
    /** Như srv cho câu của VIỆC (tiến độ / kết quả): không có trong bảng → fbEn. */
    public static String srvJob(String s, String fbEn) { if (vi()) return s; String t = Srv.en(s, true, null); return t != null ? t : fbEn; }
    public static String srvJob(String s) { return srvJob(s, "Working on it…"); }

    private static float density = 3f;
    // 16/11 · CỠ GIAO DIỆN do khách tự chỉnh (Tài khoản › Giao diện): 80–130%, nhớ theo máy. Mọi kích thước (dp) + cỡ chữ (text / button /
    // input) của app đều đi qua lớp này nên chỉ cần nhân 1 hệ số ở đây — không đụng cài đặt hệ thống, không cần quyền gì. 100% = y như cũ.
    public static final int SCALE_MIN = 80, SCALE_MAX = 130, SCALE_STEP = 5;
    private static float scale = 1f;
    public static int scalePct(Context c) {
        int v = 100;
        try { v = c.getSharedPreferences("ui", Context.MODE_PRIVATE).getInt("scale", 100); } catch (Exception ignored) { }
        return Math.max(SCALE_MIN, Math.min(SCALE_MAX, v));
    }
    /** Lưu cỡ giao diện (%). Màn đang mở phải vẽ lại (recreate) mới thấy. */
    public static void setScale(Context c, int pct) {
        int v = Math.max(SCALE_MIN, Math.min(SCALE_MAX, Math.round(pct / (float) SCALE_STEP) * SCALE_STEP));
        c.getSharedPreferences("ui", Context.MODE_PRIVATE).edit().putInt("scale", v).apply();
    }
    /** Cỡ chữ (sp) đã nhân cỡ giao diện — cho những chỗ tự gọi setTextSize. */
    public static float sp(float v) { return v * scale; }
    public static void init(Context c) {
        loadLang(c);
        scale = scalePct(c) / 100f;
        density = c.getResources().getDisplayMetrics().density * scale; Api.init(c);
        if (c instanceof Activity) Guard.gate((Activity) c);         // 🔒 app bị sửa → hộp chặn (Guard.java)
        String t = c.getSharedPreferences("ui", Context.MODE_PRIVATE).getString("theme", null);
        boolean light = t != null ? "light".equals(t)
                : (c.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) != Configuration.UI_MODE_NIGHT_YES;
        apply(light);
    }
    public static int dp(float v) { return Math.round(v * density); }

    public static String vnd(double v) {
        return NumberFormat.getInstance(new Locale("vi", "VN")).format(Math.round(v)) + "đ";
    }

    // ---------------- Hình nền ----------------
    /** 16/11c · BO TRÒN mượt hơn: mọi góc ×1,3 (0 giữ vuông · ≥ 99 = viên thuốc). */
    public static int rad(int r) { return r <= 0 ? 0 : r >= 99 ? 999 : Math.round(r * 1.3f); }

    public static GradientDrawable round(int fill, int radius, int stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(rad(radius)));
        if (stroke != 0) g.setStroke(dp(1), stroke);
        return g;
    }

    public static void ripple(View v, int fill, int radius, int stroke) {
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(Color.argb(60, 143, 208, 255)), round(fill, radius, stroke), null));
    }

    /** Nút xanh bóng (chuyển màu từ trên xuống, như web). */
    public static GradientDrawable gloss(int radius) {
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{Color.rgb(61, 134, 255), Color.rgb(11, 95, 255)});
        g.setCornerRadius(dp(rad(radius)));
        return g;
    }

    public static void glossy(View v, int radius) {
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(Color.argb(70, 255, 255, 255)), gloss(radius), null));
    }

    /** Thẻ: nền trắng/mực + viền neon xanh 1.5dp, bo 20dp. */
    public static GradientDrawable ringed(int fill, int radius) {
        GradientDrawable g = round(fill, radius, 0);
        g.setStroke(Math.max(2, dp(1.5f)), RING);
        return g;
    }

    /** Nền "bảng bong bóng" như logo: chấm tròn nhỏ lặp lại, vẽ 1 lần, rất nhẹ. */
    private static BitmapDrawable bubbles;
    public static Drawable bubbles(Context c) {
        if (bubbles == null) {
            int s = Math.max(24, dp(30));
            Bitmap b = Bitmap.createBitmap(s, s, Bitmap.Config.ARGB_8888);
            Canvas cv = new Canvas(b);
            cv.drawColor(BG);
            Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
            float r = s * .23f;
            p.setColor(LIGHT ? Color.argb(20, 12, 40, 100) : Color.argb(70, 0, 0, 0)); cv.drawCircle(s / 2f + 1, s / 2f + 2, r + 1, p);
            p.setColor(LIGHT ? Color.WHITE : Color.argb(22, 120, 180, 255)); cv.drawCircle(s / 2f, s / 2f, r, p);
            p.setColor(LIGHT ? Color.argb(230, 255, 255, 255) : Color.argb(26, 160, 205, 255)); cv.drawCircle(s / 2f - r * .3f, s / 2f - r * .32f, r * .32f, p);
            bubbles = new BitmapDrawable(c.getResources(), b);
            bubbles.setTileModeXY(Shader.TileMode.REPEAT, Shader.TileMode.REPEAT);
        }
        return bubbles.getConstantState().newDrawable(c.getResources());
    }

    /** Logo cá voi Cloud Blue (ảnh nét). */
    public static ImageView whale(Context c, int heightDp) {
        ImageView v = new ImageView(c);
        v.setImageBitmap(Brand.whale());
        v.setAdjustViewBounds(true);
        v.setScaleType(ImageView.ScaleType.FIT_CENTER);
        v.setMaxHeight(dp(heightDp));
        return v;
    }

    // ---------------- Chữ ----------------
    public static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp * scale);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        t.setLineSpacing(0, 1.15f);
        return t;
    }

    public static TextView h1(Context c, String s) { return text(c, s, 24, FG, true); }
    public static TextView h2(Context c, String s) { return text(c, s, 17, FG, true); }
    public static TextView muted(Context c, String s) { return text(c, s, 13.5f, MUTED, false); }

    public static TextView pill(Context c, String s, int color) {
        TextView t = text(c, s, 12, color, true);
        t.setPadding(dp(10), dp(3), dp(10), dp(4));
        t.setBackground(round(Color.argb(30, Color.red(color), Color.green(color), Color.blue(color)), 99,
                Color.argb(110, Color.red(color), Color.green(color), Color.blue(color))));
        return t;
    }

    // ---------------- Nút ----------------
    public static final int PRIMARY = 0, GHOST = 1, DANGER = 2;

    public static Button button(Context c, String s, int kind) {
        Button b = new Button(c);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15 * scale);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        b.setStateListAnimator(null);
        b.setMinHeight(dp(46));
        b.setMinimumHeight(dp(46));
        b.setPadding(dp(16), 0, dp(16), 0);
        if (kind == PRIMARY) { b.setTextColor(Color.WHITE); glossy(b, 99); }                       // 16/11c: nút viên thuốc
        else if (kind == DANGER) { b.setTextColor(BAD); ripple(b, Color.argb(20, 255, 107, 129), 99, Color.argb(110, 255, 107, 129)); }
        else { b.setTextColor(FG); ripple(b, PANEL, 99, RING); }
        press(b);
        return b;
    }

    /** Nút nhỏ có biểu tượng chữ (emoji) + nhãn, dùng cho thanh công cụ. */
    public static LinearLayout tool(Context c, String icon, String label, View.OnClickListener on) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setGravity(Gravity.CENTER);
        l.setPadding(dp(4), dp(8), dp(4), dp(8));
        TextView i = text(c, icon, 20, FG, false);
        i.setGravity(Gravity.CENTER);
        TextView t = text(c, label, 11.5f, MUTED, false);
        t.setGravity(Gravity.CENTER);
        t.setMaxLines(2);
        l.addView(i);
        l.addView(t);
        l.setClickable(true);
        l.setFocusable(true);
        l.setContentDescription(label);
        ripple(l, Color.TRANSPARENT, 12, 0);
        l.setOnClickListener(on);
        press(l);
        return l;
    }

    // ---------------- Ô nhập ----------------
    public static EditText input(Context c, String hint, int type) {
        EditText e = new EditText(c);
        e.setHint(hint);
        e.setHintTextColor(HINT);
        e.setTextColor(FG);
        e.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16 * scale);
        e.setInputType(type);
        e.setSingleLine(type != (InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE));
        e.setPadding(dp(14), dp(12), dp(14), dp(12));
        e.setBackground(round(SUNK, 14, LINE2));
        e.setMinHeight(dp(48));
        return e;
    }

    // ---------------- Bố cục ----------------
    public static LinearLayout col(Context c, int gapDp) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        if (gapDp > 0) {
            l.setShowDividers(LinearLayout.SHOW_DIVIDER_MIDDLE);
            GradientDrawable d = new GradientDrawable();
            d.setSize(1, dp(gapDp));
            d.setColor(Color.TRANSPARENT);
            l.setDividerDrawable(d);
        }
        return l;
    }

    public static LinearLayout row(Context c, int gapDp) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        if (gapDp > 0) {
            l.setShowDividers(LinearLayout.SHOW_DIVIDER_MIDDLE);
            GradientDrawable d = new GradientDrawable();
            d.setSize(dp(gapDp), 1);
            d.setColor(Color.TRANSPARENT);
            l.setDividerDrawable(d);
        }
        return l;
    }

    public static LinearLayout card(Context c) {
        LinearLayout l = col(c, 10);
        l.setPadding(dp(16), dp(16), dp(16), dp(16));
        l.setBackground(ringed(PANEL, 20));
        return l;
    }

    public static LinearLayout.LayoutParams wrap() { return new LinearLayout.LayoutParams(-2, -2); }
    public static LinearLayout.LayoutParams fill() { return new LinearLayout.LayoutParams(-1, -2); }
    public static LinearLayout.LayoutParams weight(float w) { return new LinearLayout.LayoutParams(0, -2, w); }

    public static ScrollView scroll(Context c, View child) {
        ScrollView s = new ScrollView(c);
        s.setFillViewport(true);
        s.setClipToPadding(false);
        s.addView(child, new FrameLayout.LayoutParams(-1, -2));
        return s;
    }

    /** Chừa chỗ cho thanh trạng thái / điều hướng / bàn phím (Android 15+ vẽ tràn viền). */
    public static void insets(View v, boolean top, boolean bottom) {
        final int l = v.getPaddingLeft(), t = v.getPaddingTop(), r = v.getPaddingRight(), b = v.getPaddingBottom();
        v.setOnApplyWindowInsetsListener((view, in) -> {
            int it, ib, il, ir;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets s = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                android.graphics.Insets k = in.getInsets(WindowInsets.Type.ime());
                it = s.top; ib = Math.max(s.bottom, k.bottom); il = s.left; ir = s.right;
            } else {
                it = in.getSystemWindowInsetTop(); ib = in.getSystemWindowInsetBottom();
                il = in.getSystemWindowInsetLeft(); ir = in.getSystemWindowInsetRight();
            }
            view.setPadding(l + il, t + (top ? it : 0), r + ir, b + (bottom ? ib : 0));
            return in;
        });
        v.requestApplyInsets();
    }

    public static void edgeToEdge(Activity a) {
        Window w = a.getWindow();
        if (Build.VERSION.SDK_INT >= 30) w.setDecorFitsSystemWindows(false);
        else w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        if (Build.VERSION.SDK_INT < 35) { w.setStatusBarColor(Color.TRANSPARENT); w.setNavigationBarColor(BG); }
        w.getDecorView().setBackgroundColor(BG);
        // chữ/biểu tượng thanh trạng thái: tối khi nền sáng, sáng khi nền tối
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController ic = w.getInsetsController();
            int m = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            if (ic != null) ic.setSystemBarsAppearance(LIGHT ? m : 0, m);
        } else if (Build.VERSION.SDK_INT >= 23) {
            View d = w.getDecorView(); int f = d.getSystemUiVisibility();
            int m = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | (Build.VERSION.SDK_INT >= 26 ? View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR : 0);
            d.setSystemUiVisibility(LIGHT ? (f | m) : (f & ~m));
        }
    }

    // ---------------- Thông báo nhanh / hộp thoại ----------------
    public static void toast(Context c, String s) { Toast.makeText(c, s, s.length() > 60 ? Toast.LENGTH_LONG : Toast.LENGTH_SHORT).show(); }

    /** 23/11e · Thông báo có NÚT nằm ngay trong màn (không chặn thao tác, tự ẩn sau ms): VD "🖼 Vừa khung" sau khi thu nhỏ game.
     *  Không gắn được vào màn (màn đang đóng…) → thông báo thường. */
    public static void snack(Activity a, String msg, String action, Runnable run, int ms) {
        try {
            final ViewGroup root = a == null || a.isFinishing() ? null : (ViewGroup) a.findViewById(android.R.id.content);
            if (root == null) { if (a != null) toast(a, msg); return; }
            final View old = root.findViewWithTag("cb_snack");
            if (old != null) root.removeView(old);
            final LinearLayout box = row(a, 10);
            box.setTag("cb_snack");
            box.setGravity(Gravity.CENTER_VERTICAL);
            box.setPadding(dp(14), dp(10), dp(10), dp(10));
            box.setBackground(ringed(PANEL, 18));
            box.setElevation(dp(10));
            box.addView(text(a, msg, 13.5f, FG, false), weight(1));
            Button b = button(a, action, PRIMARY);
            box.addView(b, wrap());
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM);
            lp.setMargins(dp(12), dp(12), dp(12), dp(76));
            root.addView(box, lp);
            final Runnable hide = () -> { try { root.removeView(box); } catch (Exception ignored) { } };
            b.setOnClickListener(v -> { hide.run(); run.run(); });
            box.postDelayed(hide, ms);
        } catch (Exception e) { try { toast(a, msg); } catch (Exception ignored) { } }
    }

    /** Hộp thoại kiểu "tấm trượt từ dưới lên" với nội dung tuỳ ý. */
    public static Dialog sheet(Activity a, String title, View content) {
        Dialog d = new Dialog(a);
        d.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout box = col(a, 14);
        box.setPadding(dp(20), dp(10), dp(20), dp(20));
        box.setBackground(ringed(PANEL, 24));
        View grip = new View(a);
        grip.setBackground(round(LINE2, 99, 0));
        LinearLayout.LayoutParams gp = new LinearLayout.LayoutParams(dp(40), dp(4));
        gp.gravity = Gravity.CENTER_HORIZONTAL;
        box.addView(grip, gp);
        if (title != null) box.addView(h2(a, title));
        box.addView(content, fill());
        ScrollView sv = scroll(a, box);
        d.setContentView(sv);
        Window w = d.getWindow();
        if (w != null) {
            w.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            w.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            w.setGravity(Gravity.BOTTOM);
            w.setDimAmount(0.6f);
            w.getAttributes().windowAnimations = android.R.style.Animation_InputMethod;
        }
        return d;
    }

    public interface Yes { void run(); }

    public static void confirm(Activity a, String title, String msg, String yes, Yes onYes) {
        LinearLayout c = col(a, 16);
        c.addView(muted(a, msg));
        LinearLayout r = row(a, 10);
        Button no = button(a, L("Huỷ", "Cancel"), GHOST);
        Button ok = button(a, yes, PRIMARY);
        r.addView(no, weight(1));
        r.addView(ok, weight(1));
        c.addView(r, fill());
        Dialog d = sheet(a, title, c);
        no.setOnClickListener(v -> d.dismiss());
        ok.setOnClickListener(v -> { d.dismiss(); onYes.run(); });
        d.show();
    }

    // ---------------- Bố cục xếp chip tự xuống dòng ----------------
    public static class Wrap extends ViewGroup {
        private final int gap;
        public Wrap(Context c, int gapDp) { super(c); gap = dp(gapDp); }

        @Override protected void onMeasure(int ws, int hs) {
            int max = MeasureSpec.getSize(ws), x = 0, y = 0, lineH = 0;
            for (int i = 0; i < getChildCount(); i++) {
                View ch = getChildAt(i);
                if (ch.getVisibility() == GONE) continue;
                measureChild(ch, MeasureSpec.makeMeasureSpec(max, MeasureSpec.AT_MOST), hs);
                int w = ch.getMeasuredWidth(), h = ch.getMeasuredHeight();
                if (x > 0 && x + w > max) { x = 0; y += lineH + gap; lineH = 0; }
                x += w + gap;
                lineH = Math.max(lineH, h);
            }
            setMeasuredDimension(max, y + lineH);
        }

        @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
            int max = r - l, x = 0, y = 0, lineH = 0;
            for (int i = 0; i < getChildCount(); i++) {
                View ch = getChildAt(i);
                if (ch.getVisibility() == GONE) continue;
                int w = ch.getMeasuredWidth(), h = ch.getMeasuredHeight();
                if (x > 0 && x + w > max) { x = 0; y += lineH + gap; lineH = 0; }
                ch.layout(x, y, x + w, y + h);
                x += w + gap;
                lineH = Math.max(lineH, h);
            }
        }
    }

    // ---------------- Đầu trang tự xếp (16/11): tên thương hiệu KHÔNG BAO GIỜ bị che ----------------
    /** 3 phần: [trái: logo + tên] [giữa: các ô số dư / Blue] [phải: nút Sáng/Tối].
     *  Đủ chỗ → 1 hàng như cũ. Không đủ (màn hẹp, số dư dài, khách chỉnh giao diện to) → các ô ở giữa tự xuống hàng 2 (canh phải);
     *  phần trái luôn được đo trước với đủ bề rộng của nó — chữ "CloudBlue" không còn bị cắt thành "Clo…" như trước. */
    public static class Head extends ViewGroup {
        private final int gap, rowGap;
        private boolean two;
        public Head(Context c, int gapDp, int rowGapDp) { super(c); gap = dp(gapDp); rowGap = dp(rowGapDp); }
        /** Đang xếp 2 hàng? */
        public boolean twoRows() { return two; }
        private static boolean shown(View v) { return v != null && v.getVisibility() != GONE; }
        private View kid(int i) { return getChildCount() > i ? getChildAt(i) : null; }

        @Override protected void onMeasure(int ws, int hs) {
            int W = MeasureSpec.getSize(ws), in = Math.max(0, W - getPaddingLeft() - getPaddingRight()), free = MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED);
            View a = kid(0), m = kid(1), z = kid(2);
            int zw = 0, zh = 0, aw = 0, ah = 0, mw = 0, mh = 0;
            if (shown(z)) {
                LayoutParams lp = z.getLayoutParams();
                z.measure(lp != null && lp.width > 0 ? MeasureSpec.makeMeasureSpec(Math.min(lp.width, in), MeasureSpec.EXACTLY) : MeasureSpec.makeMeasureSpec(in, MeasureSpec.AT_MOST),
                        lp != null && lp.height > 0 ? MeasureSpec.makeMeasureSpec(lp.height, MeasureSpec.EXACTLY) : free);
                zw = z.getMeasuredWidth(); zh = z.getMeasuredHeight();
            }
            int zs = zw > 0 ? zw + gap : 0;
            if (shown(a)) {                                               // logo + tên: đo TRƯỚC, được hết chỗ còn lại của hàng 1
                a.measure(MeasureSpec.makeMeasureSpec(Math.max(0, in - zs), MeasureSpec.AT_MOST), free);
                aw = a.getMeasuredWidth(); ah = a.getMeasuredHeight();
            }
            two = false;
            if (shown(m)) {
                m.measure(free, free);                                    // bề rộng tự nhiên của các ô
                mw = m.getMeasuredWidth(); mh = m.getMeasuredHeight();
                if (mw > 0 && mw > in - zs - aw - (aw > 0 ? gap : 0)) {   // không đủ chỗ cùng hàng → xuống hàng 2
                    two = true;
                    m.measure(MeasureSpec.makeMeasureSpec(in, MeasureSpec.AT_MOST), free);
                    mh = m.getMeasuredHeight();
                }
            }
            int h1 = Math.max(ah, Math.max(zh, two ? 0 : mh));
            setMeasuredDimension(W, getPaddingTop() + h1 + (two ? rowGap + mh : 0) + getPaddingBottom());
        }

        @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
            int W = r - l, pl = getPaddingLeft(), pr = getPaddingRight(), pt = getPaddingTop();
            View a = kid(0), m = kid(1), z = kid(2);
            int ah = shown(a) ? a.getMeasuredHeight() : 0, zh = shown(z) ? z.getMeasuredHeight() : 0, mh = shown(m) ? m.getMeasuredHeight() : 0;
            int h1 = Math.max(ah, Math.max(zh, two ? 0 : mh)), right = W - pr;
            if (shown(z)) { int w = z.getMeasuredWidth(), y = pt + (h1 - zh) / 2; z.layout(right - w, y, right, y + zh); right -= w + gap; }
            if (shown(a)) { int y = pt + (h1 - ah) / 2; a.layout(pl, y, pl + a.getMeasuredWidth(), y + ah); }
            if (shown(m)) {
                int w = m.getMeasuredWidth();
                if (two) { int y = pt + h1 + rowGap; m.layout(W - pr - w, y, W - pr, y + mh); }
                else { int y = pt + (h1 - mh) / 2; m.layout(right - w, y, right, y + mh); }
            }
        }
    }

    /** Chip chọn 1 trong nhiều (VD: 2GB / 4GB / 8GB). */
    public static TextView chip(Context c, String s, boolean on) {
        TextView t = text(c, s, 14, on ? Color.WHITE : FG, on);
        t.setGravity(Gravity.CENTER);
        t.setMinWidth(dp(64));
        t.setPadding(dp(14), dp(10), dp(14), dp(10));
        t.setClickable(true);
        t.setFocusable(true);
        setChip(t, on);
        press(t);
        return t;
    }

    public static void setChip(TextView t, boolean on) {
        t.setSelected(on);
        t.setTextColor(on ? Color.WHITE : FG);
        if (on) glossy(t, 99); else ripple(t, PANEL, 99, RING);                     // 16/11c: chip viên thuốc
    }

    /** 16/11c · bấm → hơi lún (96%) rồi bật lại: cảm giác mượt, không đổi bố cục, không chặn cú bấm. */
    @SuppressLint("ClickableViewAccessibility")
    public static void press(View v) {
        v.setOnTouchListener((x, e) -> {
            int a = e.getActionMasked();
            if (a == MotionEvent.ACTION_DOWN && x.isEnabled()) x.animate().scaleX(.96f).scaleY(.96f).setDuration(90).start();
            else if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) x.animate().scaleX(1f).scaleY(1f).setDuration(150).start();
            return false;
        });
    }

    /** 16/11c · CÔNG TẮC bật / tắt (thay dòng chữ "Đang hiện / Đang ẩn"): chữ bên trái, công tắc bên phải, bấm cả dòng cũng đổi. */
    public interface OnToggle { void set(boolean on); }
    public static LinearLayout toggle(Context c, String label, String sub, boolean on, OnToggle cb) {
        LinearLayout r = row(c, 10);
        r.setPadding(0, dp(6), 0, dp(6));
        LinearLayout t = col(c, 2);
        t.addView(text(c, label, 15, FG, false));
        if (sub != null && !sub.isEmpty()) t.addView(muted(c, sub));
        r.addView(t, weight(1));
        android.widget.Switch s = new android.widget.Switch(c);
        s.setChecked(on);
        s.setContentDescription(label);
        int[][] st = {{android.R.attr.state_checked}, {}};
        s.setThumbTintList(new ColorStateList(st, new int[]{BLUE, LIGHT ? Color.WHITE : Color.rgb(200, 214, 240)}));
        s.setTrackTintList(new ColorStateList(st, new int[]{Color.argb(140, Color.red(BLUE), Color.green(BLUE), Color.blue(BLUE)), LINE2}));
        s.setOnCheckedChangeListener((b, v) -> cb.set(v));
        r.addView(s, wrap());
        r.setOnClickListener(v -> s.toggle());
        return r;
    }
}
