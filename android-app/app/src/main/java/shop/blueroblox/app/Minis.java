package shop.blueroblox.app;

import android.content.Context;
import android.content.SharedPreferences;
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
import android.widget.ImageView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * ⊟ THU NHỎ (22/11 · khách xin "kiểu Redfinger"): các máy khách đã thu nhỏ. Mỗi máy là 1 ô nhỏ có thanh tên (● tên · ⤢ phóng to · ✕ bỏ)
 * và hình máy chạy trực tiếp; các ô xếp hàng ở dải ngay trên thanh điều hướng của màn chính (MainActivity).
 *  • Hình ô nhỏ là phiên XEM TRƯỚC của máy chủ (cạnh dài ≤ 320 điểm ảnh, 8 khung/giây, CHỈ XEM) → nhẹ máy, ít mạng; không đá phiên điều khiển.
 *  • Bấm ô / ⤢ = mở điều khiển đầy đủ máy đó (chỉ 1 máy phát hình nét tại 1 lúc). Trong màn điều khiển, nút ⊟ = thu nhỏ máy đang mở.
 *  • Mỗi máy chỉ 1 phiên xem trước trong app: máy đang ở dải thì thẻ máy trong danh sách hiện ô tĩnh (không phát 2 lần).
 * Danh sách chỉ lưu trên điện thoại này, riêng từng tài khoản; không gửi gì lên máy chủ, không có khoá / mật khẩu nào ở đây.
 */
final class Minis {
    private Minis() { }

    /** Tối đa số máy trong dải (đủ cho khách treo nhiều máy; mỗi ô ~120 kbps). */
    static final int MAX = 12;
    /** Cạnh dài hình ô nhỏ (điểm ảnh) — máy chủ nhận 160…480. */
    static final int PREVIEW_MAXH = 320;

    static final class Item {
        final String id;
        final boolean pc;              // true = VPS GPU (máy PC thật), false = Cloud Phone
        String name;
        int w, h;                      // cỡ hình lần cuối thấy (biết ô ngang hay dọc trước khi có hình)

        Item(String id, boolean pc, String name, int w, int h) {
            this.id = id;
            this.pc = pc;
            this.name = name == null ? "" : name;
            this.w = w > 0 ? w : (pc ? 1920 : 720);
            this.h = h > 0 ? h : (pc ? 1080 : 1280);
        }

        String key() { return Minis.key(id, pc); }
        boolean land() { return w > h; }
    }

    static String key(String id, boolean pc) { return pc ? "pc:" + id : id; }

    private static SharedPreferences sp(Context c) { return c.getApplicationContext().getSharedPreferences("minis", Context.MODE_PRIVATE); }

    private static String lk() { return "l_" + (Api.uid == null ? "" : Api.uid); }

    static List<Item> list(Context c) {
        ArrayList<Item> out = new ArrayList<>();
        try {
            JSONArray a = new JSONArray(sp(c).getString(lk(), "[]"));
            for (int i = 0; i < a.length() && out.size() < MAX; i++) {
                JSONObject o = a.optJSONObject(i);
                if (o == null) continue;
                String id = o.optString("id", "");
                if (!id.matches("[0-9a-fA-F-]{8,64}")) continue;            // chỉ mã máy (uuid) — dữ liệu lạ thì bỏ
                Item it = new Item(id, o.optBoolean("pc", false), o.optString("n", ""), o.optInt("w", 0), o.optInt("h", 0));
                if (find(out, it.key()) == null) out.add(it);
            }
        } catch (Exception ignored) { }
        return out;
    }

    private static void save(Context c, List<Item> l) {
        JSONArray a = new JSONArray();
        try {
            for (Item it : l) {
                JSONObject o = new JSONObject().put("id", it.id).put("n", it.name.length() > 80 ? it.name.substring(0, 80) : it.name).put("w", it.w).put("h", it.h);
                if (it.pc) o.put("pc", true);
                a.put(o);
            }
        } catch (Exception ignored) { }
        sp(c).edit().putString(lk(), a.toString()).apply();
    }

    static Item find(List<Item> l, String key) {
        for (Item it : l) if (it.key().equals(key)) return it;
        return null;
    }

    static boolean has(Context c, String key) { return find(list(c), key) != null; }

    /** Thu nhỏ 1 máy: chưa có → thêm cuối hàng; đã có → giữ chỗ cũ, cập nhật tên + cỡ hình. false = dải đã đủ MAX máy. */
    static boolean add(Context c, String id, boolean pc, String name, int w, int h) {
        if (id == null || id.isEmpty()) return false;
        List<Item> l = list(c);
        Item it = find(l, key(id, pc));
        if (it == null) {
            if (l.size() >= MAX) return false;
            l.add(new Item(id, pc, name, w, h));
        } else {
            if (name != null && !name.isEmpty()) it.name = name;
            if (w > 0 && h > 0) { it.w = w; it.h = h; }
        }
        save(c, l);
        return true;
    }

    static void remove(Context c, String key) {
        List<Item> l = list(c);
        Item it = find(l, key);
        if (it == null) return;
        l.remove(it);
        save(c, l);
    }

    static void clear(Context c) { sp(c).edit().remove(lk()).apply(); }

    /** Giữ lại các máy còn trong tài khoản (máy đã xoá / chuyển đi / hết quyền → tự bỏ khỏi dải). */
    static boolean retain(Context c, java.util.Set<String> alive, boolean phonesKnown, boolean pcsKnown) {
        List<Item> l = list(c);
        boolean ch = false;
        for (int i = l.size() - 1; i >= 0; i--) {
            Item it = l.get(i);
            if ((it.pc ? pcsKnown : phonesKnown) && !alive.contains(it.key())) { l.remove(i); ch = true; }
        }
        if (ch) save(c, l);
        return ch;
    }

    /** Máy xoay ngang / dọc → nhớ cỡ hình mới (ô đổi hình dạng theo). true = đổi hướng. */
    static boolean setWH(Context c, String key, int w, int h) {
        if (w <= 0 || h <= 0) return false;
        List<Item> l = list(c);
        Item it = find(l, key);
        if (it == null) return false;
        boolean turned = (w > h) != it.land();
        if (it.w == w && it.h == h) return false;
        it.w = w;
        it.h = h;
        save(c, l);
        return turned;
    }

    static void rename(Context c, String key, String name) {
        if (name == null || name.isEmpty()) return;
        List<Item> l = list(c);
        Item it = find(l, key);
        if (it == null || name.equals(it.name)) return;
        it.name = name;
        save(c, l);
    }

    // ---- cách hiện dải (nhớ theo điện thoại) ----
    static boolean collapsed(Context c) { return sp(c).getBoolean("col", false); }
    static void setCollapsed(Context c, boolean v) { sp(c).edit().putBoolean("col", v).apply(); }
    /** Cỡ ô: 0 Nhỏ · 1 Vừa · 2 To. */
    static int size(Context c) { return Math.max(0, Math.min(2, sp(c).getInt("sz", 0))); }        // mặc định Nhỏ (điện thoại chật chỗ)
    static void setSize(Context c, int v) { sp(c).edit().putInt("sz", Math.max(0, Math.min(2, v))).apply(); }
    static String sizeName(int s) { return s == 0 ? Ui.L("Nhỏ", "S") : s == 2 ? Ui.L("To", "L") : Ui.L("Vừa", "M"); }

    // ---- biểu tượng "thu nhỏ": khung lớn + ô nhỏ ở góc dưới phải (như nút cửa sổ nhỏ của trình phát video) ----
    static Drawable icon(int color) { return new Icon(color); }

    /** Nút chỉ có biểu tượng thu nhỏ (thanh trên màn điều khiển / nút nổi / thẻ máy): giữ lâu hiện tên nút. */
    static ImageView button(Context c, int color, String desc, View.OnClickListener on) {
        ImageView v = new ImageView(c);
        v.setImageDrawable(icon(color));
        v.setScaleType(ImageView.ScaleType.CENTER);
        v.setContentDescription(desc);
        v.setClickable(true);
        v.setFocusable(true);
        if (Build.VERSION.SDK_INT >= 26) v.setTooltipText(desc);
        else v.setOnLongClickListener(x -> { Ui.toast(c, desc); return true; });
        Ui.ripple(v, Color.TRANSPARENT, 12, 0);
        v.setOnClickListener(on);
        return v;
    }

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
