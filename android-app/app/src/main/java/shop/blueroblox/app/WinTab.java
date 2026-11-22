package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.os.Build;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;

import org.json.JSONObject;

/**
 * 🗗 TAB CỬA SỔ NHỎ (23/11, như Redfinger): app đang mở trong Cloud Phone (VD Roblox, bản clone) → cửa sổ nhỏ NGAY TRÊN MÀN HÌNH MÁY,
 * vẫn chạy + điều khiển được; mở tab khác rồi thu nhỏ tiếp; kéo thanh trên cùng của cửa sổ để dời, kéo mép để đổi cỡ (Android trong máy lo).
 * Máy chủ (cpapi 23/11a, /cpapi/&lt;máy&gt;/win): "mini" thu nhỏ app đang mở toàn màn · "tile" xếp mọi cửa sổ thành lưới · "full" phóng to
 * cửa sổ trên cùng. Nút ở thanh trên màn điều khiển (bấm = thu nhỏ, giữ = bảng 3 nút) + 3 ô trong Công cụ.
 */
final class WinTab {
    private WinTab() { }

    /** Làm 1 việc với tab của máy (mini · tile · full) rồi báo kết quả bằng câu của máy chủ. */
    static void run(Activity a, String base, String pid, String what) {
        Ui.toast(a, "mini".equals(what) ? Ui.L("Đang thu nhỏ tab…", "Minimizing the tab…")
                : "tile".equals(what) ? Ui.L("Đang sắp xếp tab…", "Arranging tabs…") : Ui.L("Đang phóng to tab…", "Maximizing the tab…"));
        JSONObject b = new JSONObject();
        try { b.put("do", what); } catch (Exception ignored) { }
        Api.bg(() -> Api.cpAt(base, "POST", pid + "/win", b),
                j -> Ui.toast(a, Ui.srvJob(j.optString("msg", Ui.L("Xong.", "Done.")), "mini".equals(what)
                        ? "The app is now a small window. Drag its top bar to move it, drag an edge to resize. Open another tab and tap Minimize tab again — then tap Arrange tabs."
                        : "tile".equals(what) ? "Small tabs arranged." : "The tab is full screen again.")),
                m -> Ui.toast(a, missing(m)));
    }

    /** Máy chủ chưa lên bản có tab cửa sổ nhỏ → nói rõ. */
    static String missing(String m) {
        return m != null && (m.contains("Không có chức năng") || m.contains("feature isn't available"))
                ? Ui.L("Máy chủ của máy này chưa có tính năng này — đang được cập nhật, thử lại sau.", "This phone's server doesn't have this feature yet — try again later.")
                : m;
    }

    /** Bảng "Tab cửa sổ nhỏ": cách dùng + 3 nút (giữ nút thu nhỏ trên thanh trên / Công cụ). */
    static void menu(Activity a, String base, String pid) {
        LinearLayout c = Ui.col(a, 10);
        c.addView(Ui.muted(a, Ui.L("Mở app (VD Roblox) → bấm Thu nhỏ tab: app thành cửa sổ nhỏ ngay trên màn hình máy, vẫn chạy và bấm được. "
                        + "Mở tab khác (VD bản clone trong 🧬 Clone tab) rồi thu nhỏ tiếp. Kéo thanh trên cùng của cửa sổ để dời, kéo mép để đổi cỡ. "
                        + "Sắp xếp tab: xếp mọi cửa sổ gọn thành lưới. Màn ngang (🔄 Xoay màn) xếp được nhiều tab to hơn.",
                "Open an app (e.g. Roblox) → tap Minimize tab: it becomes a small window right on the phone's screen, still running and tappable. "
                        + "Open another tab (e.g. a clone from 🧬 Clone tab) and minimize it too. Drag a window's top bar to move it, drag an edge to resize. "
                        + "Arrange tabs: lays all windows out in a neat grid. Landscape (🔄 Rotate) fits more, bigger tabs.")));
        final Dialog[] d = new Dialog[1];
        String[][] acts = {{"mini", "↙️  " + Ui.L("Thu nhỏ tab đang mở", "Minimize the open tab")},
                {"tile", "🔲  " + Ui.L("Sắp xếp tab", "Arrange tabs")},
                {"full", "↗️  " + Ui.L("Phóng to tab trên cùng", "Maximize the top tab")}};
        for (String[] it : acts) {
            Button bt = Ui.button(a, it[1], "mini".equals(it[0]) ? Ui.PRIMARY : Ui.GHOST);
            bt.setOnClickListener(v -> { if (d[0] != null) d[0].dismiss(); run(a, base, pid, it[0]); });
            c.addView(bt, Ui.fill());
        }
        d[0] = Ui.sheet(a, "↙️ " + Ui.L("Tab cửa sổ nhỏ", "Small tab windows"), c);
        d[0].show();
    }

    /** Nút có biểu tượng cửa sổ nhỏ (thanh trên màn điều khiển): bấm = thu nhỏ tab, giữ = bảng 3 nút. */
    static ImageView button(Activity a, int color, View.OnClickListener tap, View.OnLongClickListener hold) {
        ImageView v = new ImageView(a);
        v.setImageDrawable(new Icon(color));
        v.setScaleType(ImageView.ScaleType.CENTER);
        String desc = Ui.L("Thu nhỏ tab (giữ: sắp xếp / phóng to)", "Minimize tab (hold: arrange / maximize)");
        v.setContentDescription(desc);
        v.setClickable(true);
        v.setFocusable(true);
        if (Build.VERSION.SDK_INT >= 26) v.setTooltipText(desc);
        Ui.ripple(v, Color.TRANSPARENT, 12, 0);
        v.setOnClickListener(tap);
        v.setOnLongClickListener(hold);
        return v;
    }

    /** Biểu tượng: khung màn hình + 1 cửa sổ nhỏ ở góc. */
    private static final class Icon extends Drawable {
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF r = new RectF();

        Icon(int color) { p.setColor(color); }

        @Override public void draw(Canvas c) {
            Rect b = getBounds();
            float s = Math.min(b.width(), b.height()), u = s / 24f, x = b.left + (b.width() - s) / 2f, y = b.top + (b.height() - s) / 2f;
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(2f * u);
            r.set(x + 3 * u, y + 5 * u, x + 21 * u, y + 19 * u);
            c.drawRoundRect(r, 2.5f * u, 2.5f * u, p);
            p.setStyle(Paint.Style.FILL);
            r.set(x + 11.5f * u, y + 11.5f * u, x + 18.5f * u, y + 16.5f * u);
            c.drawRoundRect(r, 1.2f * u, 1.2f * u, p);
        }

        @Override public int getIntrinsicWidth() { return Ui.dp(22); }
        @Override public int getIntrinsicHeight() { return Ui.dp(22); }
        @Override public void setAlpha(int a) { p.setAlpha(a); invalidateSelf(); }
        @Override public void setColorFilter(ColorFilter cf) { p.setColorFilter(cf); invalidateSelf(); }
        @SuppressWarnings("deprecation") @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }
}
