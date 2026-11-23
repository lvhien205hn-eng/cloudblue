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
 * cửa sổ trên cùng · (cpapi 23/11b) "refit" mở lại game của cửa sổ trên cùng NGAY TRONG cửa sổ cho game vẽ vừa khung (game khởi động lại)
 * · (cpapi 23/11c) "grow" / "shrink" cửa sổ trên cùng to / nhỏ hơn · "wide" màn ngang rộng (600 dp + khoá ngang) · "narrow" màn dọc như cũ.
 * Nút ở thanh trên màn điều khiển (bấm = thu nhỏ, giữ = bảng 4 nút) + 4 ô trong Công cụ.
 */
final class WinTab {
    private WinTab() { }

    /** Làm 1 việc với tab của máy (mini · tile · full) rồi báo kết quả bằng câu của máy chủ. */
    static void run(Activity a, String base, String pid, String what) {
        Ui.toast(a, "mini".equals(what) ? Ui.L("Đang thu nhỏ tab…", "Minimizing the tab…")
                : "tile".equals(what) ? Ui.L("Đang sắp xếp tab…", "Arranging tabs…")
                : "refit".equals(what) ? Ui.L("Đang mở lại game trong cửa sổ…", "Reopening the game in its window…")
                : "grow".equals(what) ? Ui.L("Đang cho cửa sổ to hơn…", "Making the window bigger…")
                : "shrink".equals(what) ? Ui.L("Đang cho cửa sổ nhỏ hơn…", "Making the window smaller…")
                : "wide".equals(what) ? Ui.L("Đang bật màn ngang rộng…", "Turning on the wide landscape screen…")
                : "narrow".equals(what) ? Ui.L("Đang trả màn dọc như cũ…", "Going back to normal portrait…") : Ui.L("Đang phóng to tab…", "Maximizing the tab…"));
        JSONObject b = new JSONObject();
        try { b.put("do", what); } catch (Exception ignored) { }
        Api.bg(() -> Api.cpAt(base, "POST", pid + "/win", b),
                j -> {
                    String msg = Ui.srvJob(j.optString("msg", Ui.L("Xong.", "Done.")), "mini".equals(what)
                            ? "The app is now a small window. Drag its top bar to move it, drag an edge to resize. Open another tab and tap Minimize tab again — then tap Arrange tabs."
                            : "tile".equals(what) ? "Small tabs arranged." : "refit".equals(what) ? "The game was reopened inside its window and now fits."
                            : "grow".equals(what) ? "The window is bigger." : "shrink".equals(what) ? "The window is smaller."
                            : "wide".equals(what) ? "Wide landscape is on." : "narrow".equals(what) ? "Back to the normal portrait screen."
                            : "The tab is full screen again.");
                    // 23/11d: game chưa chắc vẽ lại theo cỡ cửa sổ (máy chủ báo fit = "ask") → nút Vừa khung ngay trong thông báo (game mở lại đúng cỡ cửa sổ)
                    if ("ask".equals(j.optString("fit")) && !"refit".equals(what))
                        Ui.snack(a, msg, "🖼 " + Ui.L("Vừa khung", "Refit"), () -> run(a, base, pid, "refit"), 10000);
                    else Ui.toast(a, msg);
                },
                m -> Ui.toast(a, missing(m)));
    }

    /** 🖼️ Mở lại vừa khung (23/11b): game "cũ" dựng khung 1 lần → thu nhỏ bị tràn viền → mở lại game ngay trong cửa sổ. Hỏi trước vì game khởi động lại. */
    static void refit(Activity a, String base, String pid) {
        Ui.confirm(a, "🖼️ " + Ui.L("Mở lại vừa khung", "Refit to window"),
                Ui.L("Mở lại game của cửa sổ trên cùng (cửa sổ bạn vừa bấm vào) ngay trong cửa sổ đó cho vừa khung? Game sẽ khởi động lại — vào lại trận nếu cần.",
                        "Reopen the game in the top window (the one you last tapped) inside that window so it fits? The game restarts — rejoin your match if needed."),
                Ui.L("Mở lại", "Reopen"), () -> run(a, base, pid, "refit"));
    }

    /** 🖥 Màn ngang rộng (23/11c): độ rộng nhỏ nhất 600 dp + khoá ngang → màn chính nằm ngang, chứa nhiều tab clone. App đang mở có thể vẽ lại → hỏi trước. */
    static void wide(Activity a, String base, String pid) {
        Ui.confirm(a, "🖥 " + Ui.L("Màn ngang rộng", "Wide landscape"),
                Ui.L("Bật màn ngang rộng? Màn chính nằm ngang, chữ / biểu tượng nhỏ lại để xếp được nhiều tab clone hơn. App đang mở có thể tải lại giao diện. "
                        + "Bấm Màn dọc như cũ để trả lại.",
                        "Turn on the wide landscape screen? The home screen turns landscape and text / icons get smaller so more clone tabs fit. "
                        + "Open apps may reload their layout. Tap Normal portrait to undo."),
                Ui.L("Bật", "Turn on"), () -> run(a, base, pid, "wide"));
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
                        + "Sắp xếp tab: xếp mọi cửa sổ gọn thành lưới. Bấm vào 1 cửa sổ rồi bấm Cửa sổ to hơn / nhỏ hơn để đổi cỡ. "
                        + "Màn ngang rộng: màn chính nằm ngang, chữ nhỏ lại, xếp được nhiều tab clone. "
                        + "Game bị tràn viền trong cửa sổ: bấm vào cửa sổ đó rồi bấm Mở lại vừa khung (game khởi động lại, vẽ đúng cỡ cửa sổ).",
                "Open an app (e.g. Roblox) → tap Minimize tab: it becomes a small window right on the phone's screen, still running and tappable. "
                        + "Open another tab (e.g. a clone from 🧬 Clone tab) and minimize it too. Drag a window's top bar to move it, drag an edge to resize. "
                        + "Arrange tabs: lays all windows out in a neat grid. Tap a window, then Bigger / Smaller window to resize it. "
                        + "Wide landscape: the home screen turns landscape, text gets smaller and more clone tabs fit. "
                        + "A game spills out of its window? Tap that window, then Refit to window (the game restarts and draws at the window's size).")));
        final Dialog[] d = new Dialog[1];
        String[][] acts = {{"mini", "↙️  " + Ui.L("Thu nhỏ tab đang mở", "Minimize the open tab")},
                {"tile", "🔲  " + Ui.L("Sắp xếp tab", "Arrange tabs")},
                {"full", "↗️  " + Ui.L("Phóng to tab trên cùng", "Maximize the top tab")},
                {"refit", "🖼️  " + Ui.L("Mở lại vừa khung (game tràn viền)", "Refit to window (game spills out)")},
                {"grow", "➕  " + Ui.L("Cửa sổ to hơn", "Bigger window")},
                {"shrink", "➖  " + Ui.L("Cửa sổ nhỏ hơn", "Smaller window")},
                {"wide", "🖥  " + Ui.L("Màn ngang rộng (nhiều tab hơn)", "Wide landscape (fits more tabs)")},
                {"narrow", "📱  " + Ui.L("Màn dọc như cũ", "Normal portrait")}};
        for (String[] it : acts) {
            Button bt = Ui.button(a, it[1], "mini".equals(it[0]) ? Ui.PRIMARY : Ui.GHOST);
            bt.setOnClickListener(v -> {
                if (d[0] != null) d[0].dismiss();
                if ("refit".equals(it[0])) refit(a, base, pid); else if ("wide".equals(it[0])) wide(a, base, pid); else run(a, base, pid, it[0]);
            });
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
        String desc = Ui.L("Thu nhỏ tab (giữ: sắp xếp / phóng to / vừa khung)", "Minimize tab (hold: arrange / maximize / refit)");
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
