package shop.blueroblox.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * 🎮 ĐIỀU KHIỂN NHIỀU MÁY CÙNG LÚC (18/11) — như ô "mở nhiều máy" của app máy tính.
 *  • LƯỚI: mỗi máy đang chạy 1 ô, tự chia cột / hàng sao cho màn các máy to nhất; chạm ô nào là điều khiển máy đó.
 *  • 1 MÁY TO: bấm ⤢ trên ô → máy đó phủ hết chỗ; thanh số bên phải: vuốt LÊN / XUỐNG (hoặc bấm số) để qua máy khác.
 *  • 🔗 ĐỒNG BỘ: bật lên thì mọi cú chạm / phím / chữ trên 1 máy được gửi y hệt sang các máy còn lại (cài đặt hàng loạt).
 *
 * AN TOÀN: màn này KHÔNG thêm đường nào tới máy chủ. Mỗi ô là 1 phiên điều khiển bình thường (StreamClient) mở bằng chính phiên
 * đăng nhập của khách; máy chủ phát hình kiểm quyền TỪNG máy như trước giờ. Đồng bộ chỉ là app gửi cùng 1 lệnh vào các phiên
 * của chính khách. Không có khoá, mật khẩu hay thông tin quản trị nào nằm trong file này. Màn không mở được từ app khác
 * (exported = false).
 */
public class MultiActivity extends Activity {
    /** Tối đa số máy mở cùng lúc (bằng app máy tính). */
    static final int MAX = 9;
    private static final Pattern UUID = Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    private static final int C_HEAD = Color.rgb(11, 20, 40), C_EDGE = Color.argb(80, 120, 160, 255),
            C_ACT = Color.rgb(61, 134, 255), C_SYNC = Color.rgb(60, 224, 176), C_DIM = Color.rgb(150, 164, 190);

    private final Handler h = new Handler(Looper.getMainLooper());
    private final ArrayList<Tile> tiles = new ArrayList<>();
    private final Fan fan = new Fan();
    private JSONArray all = new JSONArray();                 // mọi máy điều khiển được của tài khoản (đang chạy, không bị khoá)
    private SharedPreferences pref;
    private LinearLayout topBar, navBar, note;
    private FrameLayout stage;
    private Board board;
    private Rail rail;
    private TextView title, sub, syncPill, modeBtn, noteText;
    private Button noteBtn;
    private Runnable noteAct;
    private boolean resumed = false, loading = false, sync = false, focusMode = false, dead = false, blueDone = false;
    private int focus = 0, active = 0;
    private String userQ = "auto", wantFocus = null;
    private Object backCb;                                   // Android 13+: Back qua OnBackInvokedDispatcher (kiểu Object: máy cũ không nạp lớp mới)

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Ui.init(this);
        if (!Api.loggedIn()) {
            startActivity(new Intent(this, LoginActivity.class));
            finish();
            return;
        }
        Ui.edgeToEdge(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        pref = getSharedPreferences("multi", MODE_PRIVATE);
        String q = getSharedPreferences("control", MODE_PRIVATE).getString("q", "auto");
        userQ = "eco".equals(q) || "bal".equals(q) || "hd".equals(q) ? q : "auto";     // máy đang xem to: đúng mức khách đã chọn ở màn 1 máy
        wantFocus = cleanId(getIntent() == null ? null : getIntent().getStringExtra("focus"));

        LinearLayout root = Ui.col(this, 0);
        root.setBackgroundColor(Color.BLACK);

        // Thanh trên: quay lại · tên màn + 1 dòng trạng thái · 🔗 Đồng bộ · đổi kiểu xem
        topBar = Ui.row(this, 6);
        topBar.setPadding(Ui.dp(4), Ui.dp(3), Ui.dp(6), Ui.dp(3));
        topBar.setBackgroundColor(Ui.BG);
        TextView back = Ui.text(this, "‹", 28, Ui.FG, false);
        back.setPadding(Ui.dp(10), 0, Ui.dp(8), Ui.dp(3));
        back.setContentDescription(Ui.L("Quay lại danh sách máy", "Back to phones"));
        back.setOnClickListener(v -> finish());
        topBar.addView(back, Ui.wrap());
        LinearLayout tt = Ui.col(this, 0);
        title = Ui.text(this, Ui.L("Nhiều máy", "Multi-control"), 15, Ui.FG, true);
        title.setSingleLine(true);
        title.setEllipsize(TextUtils.TruncateAt.END);
        sub = Ui.text(this, "", 11, Ui.MUTED, false);
        sub.setSingleLine(true);
        sub.setEllipsize(TextUtils.TruncateAt.END);
        tt.addView(title);
        tt.addView(sub);
        topBar.addView(tt, Ui.weight(1));
        syncPill = Ui.text(this, "", 12, Ui.MUTED, true);
        syncPill.setPadding(Ui.dp(10), Ui.dp(5), Ui.dp(10), Ui.dp(6));
        syncPill.setSingleLine(true);
        syncPill.setClickable(true);
        syncPill.setFocusable(true);
        syncPill.setOnClickListener(v -> toggleSync());
        topBar.addView(syncPill, Ui.wrap());
        modeBtn = barBtn("▭", "", v -> { if (!tiles.isEmpty()) setFocusMode(!focusMode, active); });
        topBar.addView(modeBtn, new LinearLayout.LayoutParams(Ui.dp(40), Ui.dp(40)));
        root.addView(topBar, Ui.fill());

        // Giữa: bảng các ô máy + thanh số (chỉ hiện ở kiểu 1 máy to) + ô báo (đang tải / chưa có máy / lỗi)
        stage = new FrameLayout(this);
        stage.setBackgroundColor(Color.BLACK);
        LinearLayout mid = Ui.row(this, 0);
        board = new Board(this);
        mid.addView(board, new LinearLayout.LayoutParams(0, -1, 1f));
        rail = new Rail(this);
        rail.setVisibility(View.GONE);
        mid.addView(rail, new LinearLayout.LayoutParams(Ui.dp(40), -1));
        stage.addView(mid, new FrameLayout.LayoutParams(-1, -1));

        note = Ui.col(this, 12);
        note.setGravity(Gravity.CENTER);
        note.setPadding(Ui.dp(28), Ui.dp(28), Ui.dp(28), Ui.dp(28));
        note.setBackgroundColor(Ui.LIGHT ? Color.argb(246, 243, 247, 252) : Color.argb(244, 7, 18, 38));
        note.setClickable(true);
        noteText = Ui.text(this, "", 15, Ui.FG, false);
        noteText.setGravity(Gravity.CENTER);
        note.addView(noteText, Ui.fill());
        noteBtn = Ui.button(this, "", Ui.PRIMARY);
        noteBtn.setOnClickListener(v -> { Runnable r = noteAct; if (r != null) r.run(); });
        note.addView(noteBtn, Ui.wrap());
        stage.addView(note, new FrameLayout.LayoutParams(-1, -1));
        root.addView(stage, new LinearLayout.LayoutParams(-1, 0, 1));

        // Thanh dưới: nút Android gửi cho máy đang chọn — bật Đồng bộ thì gửi cho mọi máy
        navBar = Ui.row(this, 0);
        navBar.setBackgroundColor(Ui.BG);
        navBar.setPadding(Ui.dp(6), 0, Ui.dp(6), 0);
        navBar.addView(barBtn("◁", Ui.L("Quay lại", "Back"), v -> cmd("back")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("○", Ui.L("Màn chính", "Home"), v -> cmd("home")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("▢", Ui.L("Đa nhiệm", "Recents"), v -> cmd("recents")), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("⌨", Ui.L("Gõ chữ vào máy", "Type into phone"), v -> typeText()), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        navBar.addView(barBtn("⋯", Ui.L("Thêm", "More"), v -> more()), new LinearLayout.LayoutParams(0, Ui.dp(44), 1));
        root.addView(navBar, Ui.fill());

        Ui.insets(root, true, true);
        setContentView(root);
        paintBars();
        if (Build.VERSION.SDK_INT >= 33) {                    // Android 16 + targetSdk 36: hệ thống không gọi onBackPressed nữa → Back đi qua đây
            android.window.OnBackInvokedCallback cb = () -> { if (!handleBack()) finish(); };
            backCb = cb;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, cb);
        }
        load();
    }

    /** Nút chỉ có biểu tượng: giữ lâu hiện tên nút (như màn điều khiển 1 máy). */
    private TextView barBtn(String icon, String desc, View.OnClickListener on) {
        TextView t = Ui.text(this, icon, 19, Ui.FG, false);
        t.setGravity(Gravity.CENTER);
        t.setContentDescription(desc);
        t.setClickable(true);
        t.setFocusable(true);
        if (!desc.isEmpty()) {
            if (Build.VERSION.SDK_INT >= 26) t.setTooltipText(desc);
            else t.setOnLongClickListener(v -> { Ui.toast(this, desc); return true; });
        }
        Ui.ripple(t, Color.TRANSPARENT, 12, 0);
        t.setOnClickListener(on);
        return t;
    }

    private static String cleanId(String s) {
        if (s == null) return null;
        s = s.trim();
        return UUID.matcher(s).matches() ? s.toLowerCase(Locale.ROOT) : null;
    }

    /** Màn này đang mở sẵn mà được gọi lại (từ màn 1 máy bấm 🎮): chọn luôn máy vừa xem. */
    @Override protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        setIntent(i);
        String f = cleanId(i == null ? null : i.getStringExtra("focus"));
        if (f == null || board == null) return;
        int k = indexOf(f);
        if (k < 0) { wantFocus = f; load(); return; }       // máy đó chưa có trong các ô → tải lại danh sách, đưa máy đó vào
        if (focusMode) go(k); else setActive(k);
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        Api.onOutdated = () -> { if (!isFinishing()) Updater.check(this, false); };   // máy chủ báo app cũ → hộp bắt buộc cập nhật
        Updater.check(this, false);
        if (board != null) applyAll();                       // quay lại màn → các ô tự nối lại
    }

    @Override protected void onPause() {
        super.onPause();
        resumed = false;
        h.removeCallbacks(applyR);
        fan.release(port, tiles.size());                     // đang giữ ngón lúc rời màn → nhấc ngón trên các máy đồng bộ
        for (Tile t : tiles) t.stop();                       // rời màn → đóng mọi phiên (BYE); quay lại tự nối lại
    }

    @Override protected void onDestroy() {
        dead = true;
        if (Build.VERSION.SDK_INT >= 33 && backCb != null)
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback((android.window.OnBackInvokedCallback) backCb);
        h.removeCallbacksAndMessages(null);
        for (Tile t : tiles) t.stop();
        for (Tile t : tiles) t.screen.release();
        tiles.clear();
        super.onDestroy();
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {                            // Android 15 trở xuống (16 + targetSdk 36 dùng backCb)
        if (!handleBack()) super.onBackPressed();
    }

    /** Back khi đang xem 1 máy to: về lại lưới (không thoát màn). */
    private boolean handleBack() {
        if (focusMode && tiles.size() > 1) { setFocusMode(false, focus); return true; }
        return false;
    }

    // ---------------- Danh sách máy ----------------
    private void load() {
        if (loading) return;
        loading = true;
        if (tiles.isEmpty()) showNote(Ui.L("Đang tải danh sách máy…", "Loading your phones…"), null, null);
        else Ui.toast(this, Ui.L("Đang tải lại danh sách máy…", "Reloading your phones…"));
        Api.bg(() -> {
            JSONArray list = Api.phones();
            boolean admin = false;
            try { admin = "admin".equals(Api.profile().optString("role")); } catch (Exception ignored) { }
            JSONArray ok = new JSONArray();
            for (int i = 0; i < list.length(); i++) {
                JSONObject p = list.optJSONObject(i);
                if (p == null || cleanId(p.optString("id")) == null) continue;
                if (!"active".equals(p.optString("status"))) continue;
                if (MainActivity.locked(p) && !admin) continue;           // máy bị khoá: chỉ admin điều khiển được (máy chủ cũng tự kiểm)
                ok.put(p);
            }
            return ok;
        }, ok -> {
            loading = false;
            if (dead || isFinishing()) return;
            all = ok;
            if (all.length() == 0) {
                clearTiles();
                showNote("📱 " + Ui.L("Chưa có máy nào đang chạy.", "No running phones."), Ui.L("Về danh sách máy", "Back to phones"), this::finish);
                paintBars();
                return;
            }
            build(pick());
        }, m -> {
            loading = false;
            if (dead || isFinishing()) return;
            if (tiles.isEmpty()) showNote(m, Ui.L("Thử lại", "Retry"), this::load);
            else Ui.toast(this, m);
        });
    }

    /** Máy sẽ mở: lựa chọn đã nhớ của khách (còn chạy) · chưa chọn bao giờ → các máy đầu danh sách, tối đa MAX. */
    private ArrayList<String> pick() {
        LinkedHashSet<String> have = new LinkedHashSet<>();
        for (int i = 0; i < all.length(); i++) have.add(cleanId(all.optJSONObject(i).optString("id")));
        ArrayList<String> out = new ArrayList<>();
        String saved = pref.getString("sel_" + Api.uid, "");
        if (!saved.isEmpty()) {
            for (String s : saved.split(",")) {
                String id = cleanId(s);
                if (id != null && have.contains(id) && !out.contains(id) && out.size() < MAX) out.add(id);
            }
        }
        if (wantFocus != null && have.contains(wantFocus) && !out.contains(wantFocus)) {     // mở từ màn 1 máy → máy đó phải có mặt
            if (out.size() >= MAX) out.remove(out.size() - 1);
            out.add(0, wantFocus);
        }
        if (out.size() < 2) {                                // chưa chọn / lựa chọn cũ không còn máy nào chạy → mặc định
            out.clear();
            if (wantFocus != null && have.contains(wantFocus)) out.add(wantFocus);
            for (String id : have) { if (out.size() >= MAX) break; if (!out.contains(id)) out.add(id); }
        }
        return out;
    }

    private JSONObject phone(String id) {
        for (int i = 0; i < all.length(); i++) {
            JSONObject p = all.optJSONObject(i);
            if (p != null && id.equals(cleanId(p.optString("id")))) return p;
        }
        return null;
    }

    private void clearTiles() {
        fan.release(port, tiles.size());
        for (Tile t : tiles) { t.stop(); t.screen.dropSurface(); }
        board.removeAllViews();
        for (Tile t : tiles) t.screen.release();
        tiles.clear();
        focus = 0;
        active = 0;
        focusMode = false;
    }

    /** Dựng (lại) các ô theo danh sách mã máy: ô của máy còn giữ thì dùng lại (không phải nối lại), máy bỏ chọn thì đóng. */
    private void build(ArrayList<String> ids) {
        fan.release(port, tiles.size());
        String keepActive = active < tiles.size() ? tiles.get(active).id : null, keepFocus = focus < tiles.size() ? tiles.get(focus).id : null;
        ArrayList<Tile> next = new ArrayList<>(), gone = new ArrayList<>(tiles);
        for (String id : ids) {
            JSONObject p = phone(id);
            if (p == null) continue;
            Tile t = null;
            for (Tile x : tiles) if (x.id.equals(id)) { t = x; break; }
            if (t == null) t = new Tile(this, id, p);
            else { gone.remove(t); t.rename(p); }
            next.add(t);
        }
        for (Tile t : gone) { t.stop(); t.screen.dropSurface(); }           // dừng bộ giải mã song song trước khi gỡ ô
        for (Tile t : gone) board.removeView(t);
        for (Tile t : gone) t.screen.release();
        tiles.clear();
        tiles.addAll(next);
        for (int i = 0; i < tiles.size(); i++) {
            Tile t = tiles.get(i);
            t.index = i;
            if (t.getParent() == null) board.addView(t);           // ô còn giữ nằm nguyên chỗ (hình không chớp)
        }
        active = Math.max(0, indexOf(keepActive));
        focus = Math.max(0, indexOf(keepFocus));
        if (wantFocus != null) {                             // mở từ màn 1 máy: máy đó là máy đang chọn
            int i = indexOf(wantFocus);
            if (i >= 0) { active = i; focus = i; }
            wantFocus = null;
        }
        if (tiles.size() <= 1) { focusMode = false; sync = false; }
        note.setVisibility(tiles.isEmpty() ? View.VISIBLE : View.GONE);
        if (tiles.isEmpty()) showNote("📱 " + Ui.L("Chưa có máy nào đang chạy.", "No running phones."), Ui.L("Về danh sách máy", "Back to phones"), this::finish);
        paintBars();
        applyAll();
        tip(false);
    }

    /** Hộp chỉ cách dùng: tự hiện 1 lần ở lần đầu vào màn (từ 2 máy), xem lại ở ⋯ Thêm › Cách dùng. */
    private void tip(boolean always) {
        if (dead || isFinishing()) return;
        if (!always && (tiles.size() < 2 || pref.getBoolean("tip1", false))) return;
        pref.edit().putBoolean("tip1", true).apply();
        LinearLayout c = Ui.col(this, 10);
        String[] lines = {
                "👆  " + Ui.L("Chạm vào máy nào là điều khiển máy đó (ô có viền xanh là máy đang chọn).", "Touch a phone to control it (the blue border marks the selected one)."),
                "⤢  " + Ui.L("Bấm ⤢ trên ô để xem máy đó to. Khi đó vuốt LÊN / XUỐNG ở thanh số bên phải (hoặc bấm số) để qua máy khác.", "Tap ⤢ on a tile to make that phone big. Then swipe UP / DOWN on the number rail at the right (or tap a number) to switch phones."),
                "🔗  " + Ui.L("Đồng bộ: bật lên thì thao tác trên 1 máy, mọi máy làm theo — hợp khi cài đặt nhiều máy giống nhau.", "Sync: when on, what you do on one phone happens on all of them — handy for setting up many phones the same way."),
                "◁ ○ ▢ ⌨  " + Ui.L("Các nút dưới gửi cho máy đang chọn; đang đồng bộ thì gửi cho mọi máy.", "The bottom buttons go to the selected phone, or to every phone while sync is on."),
                "↗  " + Ui.L("Mở riêng 1 máy để dùng đủ công cụ (cài app, bàn phím, xoay màn, chụp màn…).", "Open one phone alone for all tools (install apps, keyboard, rotate, screenshot…)."),
        };
        for (String t : lines) c.addView(Ui.text(this, t, 14, Ui.FG, false), Ui.fill());
        Button ok = Ui.button(this, Ui.L("Đã hiểu", "Got it"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, "🎮 " + Ui.L("Điều khiển nhiều máy", "Multi-control"), c);
        ok.setOnClickListener(v -> d.dismiss());
        try { d.show(); } catch (Exception ignored) { }        // màn vừa bị đóng → thôi
    }

    private int indexOf(String id) {
        if (id == null) return -1;
        for (int i = 0; i < tiles.size(); i++) if (tiles.get(i).id.equals(id)) return i;
        return -1;
    }

    private void showNote(String text, String btn, Runnable act) {
        note.setVisibility(View.VISIBLE);
        noteText.setText(text);
        noteAct = act;
        if (btn != null && act != null) { noteBtn.setText(btn); noteBtn.setVisibility(View.VISIBLE); }
        else noteBtn.setVisibility(View.GONE);
    }

    // ---------------- Kiểu xem + phiên của từng ô ----------------
    private final Runnable applyR = this::applyNow;

    /** Đặt lại ô nào hiện / phiên nào mở. Gộp lại 1 lần sau 250 ms: vuốt nhanh qua nhiều máy không mở / đóng phiên liên tục. */
    private void applyAll() {
        int n = tiles.size();
        for (int i = 0; i < n; i++) tiles.get(i).setShown(!focusMode || i == focus);
        for (int i = 0; i < n; i++) tiles.get(i).paint();
        board.requestLayout();
        rail.setVisibility(focusMode && n > 1 ? View.VISIBLE : View.GONE);
        rail.invalidate();
        h.removeCallbacks(applyR);
        h.postDelayed(applyR, 250);
    }

    private void applyNow() {
        if (dead) return;
        int n = tiles.size();
        boolean cell = "c".equals(StreamClient.netTag(this));
        int gMaxh = n >= 5 ? 640 : 0, gFps = n >= 5 ? 20 : 30, gKbps = cell ? 600 : n >= 5 ? 900 : 0;   // ô lưới: nhẹ dần khi nhiều máy / đang dùng 4G
        for (int i = 0; i < n; i++) {
            Tile t = tiles.get(i);
            if (!resumed) { t.stop(); continue; }
            if (!focusMode) t.want("eco", gMaxh, gFps, gKbps);
            else if (i == focus) t.want(userQ, 0, 0, 0);                 // máy đang xem to: hình như màn điều khiển 1 máy
            else if (sync) t.keep("eco", gMaxh, 10, 300);                // khuất nhưng đang đồng bộ: giữ phiên để nhận lệnh, hình nhẹ nhất
            else t.stop();                                               // khuất + không đồng bộ: đóng phiên (đỡ tốn mạng + máy chủ)
        }
    }

    private void setFocusMode(boolean on, int index) {
        int n = tiles.size();
        if (n == 0) return;
        if (on && n <= 1) on = false;
        fan.release(port, n);
        focus = Math.max(0, Math.min(n - 1, index));
        if (on) for (int i = 0; i < n; i++) if (i != focus) tiles.get(i).screen.dropSurface();   // ô sắp khuất: dừng bộ giải mã song song (giao diện không đứng)
        focusMode = on;
        if (on) active = focus;
        paintBars();
        applyAll();
    }

    /** Thanh số: qua máy kế (d = +1) / máy trước (d = −1), hết thì quay vòng. */
    private void step(int d) {
        int n = tiles.size();
        if (!focusMode || n <= 1) return;
        go(((focus + d) % n + n) % n);
    }

    private void go(int index) {
        int n = tiles.size();
        if (!focusMode || index < 0 || index >= n || index == focus) return;
        fan.release(port, n);
        tiles.get(focus).screen.dropSurface();
        focus = index;
        active = index;
        paintBars();
        applyAll();
    }

    private void setActive(int index) {
        if (index < 0 || index >= tiles.size() || index == active) return;
        active = index;
        for (Tile t : tiles) t.paint();
        paintBars();
    }

    private void paintBars() {
        int n = tiles.size();
        boolean on = sync && n > 1;
        int c = on ? C_SYNC : Ui.MUTED;
        syncPill.setText("🔗 " + (on ? Ui.L("Đồng bộ: BẬT", "Sync: ON") : Ui.L("Đồng bộ: tắt", "Sync: off")));
        syncPill.setTextColor(on ? (Ui.LIGHT ? Ui.OK : C_SYNC) : Ui.MUTED);
        Ui.ripple(syncPill, Color.argb(on ? 40 : 22, Color.red(c), Color.green(c), Color.blue(c)), 99, Color.argb(on ? 150 : 90, Color.red(c), Color.green(c), Color.blue(c)));
        syncPill.setContentDescription(Ui.L("Đồng bộ: thao tác 1 máy gửi sang mọi máy", "Sync: mirror one phone to all"));
        syncPill.setVisibility(n > 1 ? View.VISIBLE : View.GONE);
        modeBtn.setText(focusMode ? "▦" : "▭");
        String md = focusMode ? Ui.L("Về lưới nhiều máy", "Back to the grid") : Ui.L("Xem 1 máy to", "One phone, big");
        modeBtn.setContentDescription(md);
        if (Build.VERSION.SDK_INT >= 26) modeBtn.setTooltipText(md);
        modeBtn.setVisibility(n > 1 ? View.VISIBLE : View.GONE);
        title.setText(n > 0 ? Ui.L("Nhiều máy (" + n + ")", "Multi-control (" + n + ")") : Ui.L("Nhiều máy", "Multi-control"));
        String nm = active < n ? tiles.get(active).name : "";
        sub.setText(n == 0 ? "" : on ? Ui.L("Đồng bộ: thao tác 1 máy → cả " + n + " máy", "Sync: one phone → all " + n)
                : focusMode ? Ui.L("Vuốt lên / xuống ở thanh số để qua máy khác", "Swipe the number rail to switch")
                : Ui.L("Đang chọn: ", "Selected: ") + nm);
    }

    // ---------------- 🔗 Đồng bộ ----------------
    private void toggleSync() {
        if (tiles.size() < 2) return;
        if (sync) { setSync(false); return; }
        if (pref.getBoolean("sync_tip", false)) { setSync(true); return; }
        Ui.confirm(this, "🔗 " + Ui.L("Bật đồng bộ?", "Turn sync on?"),
                Ui.L("Mọi cú chạm, phím và chữ bạn gõ trên 1 máy sẽ được gửi y hệt sang TẤT CẢ máy đang mở ở đây. Hợp nhất khi các máy cùng độ phân giải và đang ở cùng một màn hình (ví dụ cùng ở màn chính).\n\nNhớ TẮT đồng bộ trước khi đăng nhập tài khoản riêng cho từng máy.",
                        "Every touch, key and text you send to one phone is sent to ALL phones open here. Works best when the phones share a resolution and show the same screen.\n\nTurn sync OFF before signing in to a different account on each phone."),
                Ui.L("Bật đồng bộ", "Turn on"), () -> { pref.edit().putBoolean("sync_tip", true).apply(); setSync(true); });
    }

    private void setSync(boolean on) {
        if (sync == on) return;
        if (!on) fan.release(port, tiles.size());            // đang giữ ngón → nhấc ngón trên các máy đang theo
        sync = on;
        paintBars();
        for (Tile t : tiles) t.paint();
        applyAll();                                          // kiểu 1 máy to: bật → mở phiên các máy khuất · tắt → đóng
        Ui.toast(this, on ? Ui.L("Đã BẬT đồng bộ — thao tác 1 máy, mọi máy làm theo.", "Sync ON — all phones follow.")
                : Ui.L("Đã tắt đồng bộ.", "Sync off."));
    }

    /** Cổng gửi của bộ đồng bộ: ô thứ i có đang vào phiên không + gửi 1 lệnh chạm vào phiên của ô đó. */
    private final Fan.Port port = new Fan.Port() {
        @Override public boolean live(int i) { return i >= 0 && i < tiles.size() && tiles.get(i).live(); }
        @Override public void touch(int i, int action, int pointer, float x, float y) {
            if (i < 0 || i >= tiles.size()) return;
            StreamClient c = tiles.get(i).client;
            if (c != null) c.touch(action, pointer, x, y);
        }
    };

    /** Các phiên nhận lệnh nút / phím / chữ: đồng bộ → mọi máy đang vào phiên · không → máy đang chọn. */
    private ArrayList<StreamClient> targets() {
        ArrayList<StreamClient> out = new ArrayList<>();
        if (sync) { for (Tile t : tiles) if (t.live()) out.add(t.client); }
        else if (active < tiles.size() && tiles.get(active).live()) out.add(tiles.get(active).client);
        return out;
    }

    private ArrayList<StreamClient> targetsOrToast() {
        ArrayList<StreamClient> l = targets();
        if (l.isEmpty()) Ui.toast(this, tiles.isEmpty() ? Ui.L("Chưa có máy nào đang mở.", "No phone is open.")
                : Ui.L("Máy đang kết nối, thử lại sau giây lát.", "Still connecting, try again in a moment."));
        return l;
    }

    private void cmd(String name) {
        for (StreamClient c : targetsOrToast()) c.cmd(name);
    }

    /** Phím thật (bàn phím Bluetooth / USB) → máy đang chọn (đồng bộ: mọi máy). Như màn điều khiển 1 máy. */
    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        if (hardwareKey(e)) return true;
        return super.dispatchKeyEvent(e);
    }

    private boolean hardwareKey(KeyEvent e) {
        InputDevice d = e.getDevice();
        if (d == null || d.isVirtual() || d.getKeyboardType() != InputDevice.KEYBOARD_TYPE_ALPHABETIC) return false;
        if ((e.getSource() & InputDevice.SOURCE_KEYBOARD) != InputDevice.SOURCE_KEYBOARD) return false;
        int k = e.getKeyCode();
        if (k == KeyEvent.KEYCODE_BACK || k == KeyEvent.KEYCODE_VOLUME_UP || k == KeyEvent.KEYCODE_VOLUME_DOWN
                || k == KeyEvent.KEYCODE_VOLUME_MUTE || k == KeyEvent.KEYCODE_POWER || k == KeyEvent.KEYCODE_HOME) return false;
        int a = e.getAction();
        if (a != KeyEvent.ACTION_DOWN && a != KeyEvent.ACTION_UP) return false;
        ArrayList<StreamClient> l = targets();
        if (l.isEmpty()) return false;
        for (StreamClient c : l) c.key(a == KeyEvent.ACTION_DOWN ? StreamClient.KEY_DOWN : StreamClient.KEY_UP, k, e.getMetaState());
        return true;
    }

    // ---------------- ⌨ Gõ chữ · ⋯ Thêm ----------------
    private void typeText() {
        if (tiles.isEmpty()) return;
        LinearLayout c = Ui.col(this, 12);
        c.addView(Ui.muted(this, sync && tiles.size() > 1
                ? Ui.L("Đang đồng bộ: chữ được dán vào ô đang nhập của MỌI máy. Bấm vào ô nhập trên máy trước.", "Sync is on: the text is pasted into the focused field on EVERY phone. Tap a field first.")
                : Ui.L("Chữ được dán vào ô đang nhập của máy đang chọn. Bấm vào ô nhập trên máy trước.", "The text is pasted into the focused field of the selected phone. Tap a field first.")));
        EditText e = Ui.input(this, Ui.L("Nội dung", "Text"), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        c.addView(e, Ui.fill());
        Button ok = Ui.button(this, Ui.L("Gửi vào máy", "Send"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        LinearLayout r = Ui.row(this, 10);
        Button ent = Ui.button(this, "↵ Enter", Ui.GHOST), del = Ui.button(this, "⌫ " + Ui.L("Xoá", "Delete"), Ui.GHOST);
        r.addView(ent, Ui.weight(1));
        r.addView(del, Ui.weight(1));
        c.addView(r, Ui.fill());
        Dialog d = Ui.sheet(this, "⌨ " + Ui.L("Gõ chữ vào máy", "Type into phone"), c);
        ok.setOnClickListener(v -> {
            String s = e.getText().toString();
            if (s.isEmpty()) return;
            ArrayList<StreamClient> l = targetsOrToast();
            if (l.isEmpty()) return;
            for (StreamClient x : l) x.clipSet(s, true);     // dán qua bộ nhớ copy của máy: giữ được chữ có dấu
            e.setText("");
            Ui.toast(this, Ui.L("Đang dán vào ", "Pasting into ") + (l.size() > 1 ? l.size() + Ui.L(" máy…", " phones…") : Ui.L("máy…", "the phone…")));
        });
        ent.setOnClickListener(v -> { for (StreamClient x : targetsOrToast()) x.press(KeyEvent.KEYCODE_ENTER, 0); });
        del.setOnClickListener(v -> { for (StreamClient x : targetsOrToast()) x.press(KeyEvent.KEYCODE_DEL, 0); });
        d.show();
        e.requestFocus();
    }

    private void more() {
        Ui.Wrap g = new Ui.Wrap(this, 6);
        final Dialog[] d = new Dialog[1];
        int w = (getResources().getDisplayMetrics().widthPixels - Ui.dp(64)) / 4;
        Object[][] items = {
                {"🔊", Ui.L("Tăng âm", "Vol +"), (Runnable) () -> cmd("volup")},
                {"🔉", Ui.L("Giảm âm", "Vol −"), (Runnable) () -> cmd("voldown")},
                {"⏻", Ui.L("Tắt/mở màn", "Power"), (Runnable) () -> cmd("power")},
                {"🔔", Ui.L("Thông báo", "Notifications"), (Runnable) () -> cmd("notif")},
                {"☑", Ui.L("Chọn máy", "Choose phones"), (Runnable) this::choose},
                {"↗", Ui.L("Mở riêng máy này", "Open alone"), (Runnable) () -> openAlone(active)},
                {"↻", Ui.L("Nối lại tất cả", "Reconnect all"), (Runnable) this::reconnectAll},
                {"⟳", Ui.L("Tải lại danh sách", "Reload list"), (Runnable) this::load},
                {"❓", Ui.L("Cách dùng", "How to use"), (Runnable) () -> tip(true)},
        };
        for (Object[] it : items) {
            Runnable r = (Runnable) it[2];
            LinearLayout t = Ui.tool(this, (String) it[0], (String) it[1], v -> { if (d[0] != null) d[0].dismiss(); r.run(); });
            t.setMinimumWidth(w);
            g.addView(t, new ViewGroup.LayoutParams(w, -2));
        }
        LinearLayout c = Ui.col(this, 10);
        c.addView(Ui.muted(this, sync && tiles.size() > 1 ? Ui.L("Đang đồng bộ: 4 nút đầu gửi cho mọi máy.", "Sync is on: the first four go to every phone.")
                : Ui.L("4 nút đầu gửi cho máy đang chọn (ô có viền xanh).", "The first four go to the selected phone (blue border).")));
        c.addView(g, Ui.fill());
        d[0] = Ui.sheet(this, Ui.L("Thêm", "More"), c);
        d[0].show();
    }

    private void reconnectAll() {
        for (Tile t : tiles) t.retry();
        applyAll();
    }

    /** Mở màn điều khiển đầy đủ của 1 máy (cài app, bàn phím, xoay, chụp màn…). Quay lại đây các ô tự nối lại. */
    private void openAlone(int index) {
        if (index < 0 || index >= tiles.size()) return;
        try { startActivity(new Intent(this, ControlActivity.class).putExtra("id", tiles.get(index).id)); }
        catch (Exception e) { Ui.toast(this, Ui.L("Chưa mở được máy này.", "Couldn't open this phone.")); }
    }

    /** ☑ Chọn máy mở trong màn này (tối đa MAX) — nhớ theo tài khoản. */
    private void choose() {
        if (all.length() == 0) { load(); return; }
        final LinkedHashSet<String> sel = new LinkedHashSet<>();
        for (Tile t : tiles) sel.add(t.id);
        LinearLayout c = Ui.col(this, 8);
        final TextView head = Ui.muted(this, "");
        final Runnable upd = () -> head.setText(Ui.L("Đã chọn " + sel.size() + " / tối đa " + MAX + " máy.", sel.size() + " selected · up to " + MAX + "."));
        upd.run();
        c.addView(head, Ui.fill());
        for (int i = 0; i < all.length(); i++) {
            JSONObject p = all.optJSONObject(i);
            final String id = p == null ? null : cleanId(p.optString("id"));
            if (id == null) continue;
            final String nm = p.optString("name", Ui.L("Máy", "Phone"));
            final TextView row = Ui.chip(this, "", sel.contains(id));
            row.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            row.setSingleLine(true);
            row.setEllipsize(TextUtils.TruncateAt.END);
            row.setText((sel.contains(id) ? "☑  " : "☐  ") + nm);
            row.setOnClickListener(v -> {
                if (sel.contains(id)) sel.remove(id);
                else if (sel.size() >= MAX) { Ui.toast(this, Ui.L("Tối đa " + MAX + " máy cùng lúc — bỏ bớt 1 máy trước.", "Up to " + MAX + " phones — unselect one first.")); return; }
                else sel.add(id);
                Ui.setChip(row, sel.contains(id));
                row.setText((sel.contains(id) ? "☑  " : "☐  ") + nm);
                upd.run();
            });
            c.addView(row, Ui.fill());
        }
        Button ok = Ui.button(this, Ui.L("Xong", "Done"), Ui.PRIMARY);
        c.addView(ok, Ui.fill());
        Dialog d = Ui.sheet(this, "☑ " + Ui.L("Chọn máy", "Choose phones"), c);
        ok.setOnClickListener(v -> {
            if (sel.isEmpty()) { Ui.toast(this, Ui.L("Chọn ít nhất 1 máy.", "Pick at least one phone.")); return; }
            d.dismiss();
            ArrayList<String> ids = new ArrayList<>();
            for (int i = 0; i < all.length(); i++) {             // giữ thứ tự của danh sách máy
                JSONObject p = all.optJSONObject(i);
                String id = p == null ? null : cleanId(p.optString("id"));
                if (id != null && sel.contains(id)) ids.add(id);
            }
            pref.edit().putString("sel_" + Api.uid, TextUtils.join(",", ids)).apply();
            build(ids);
        });
        d.show();
    }

    // ================================================================ 1 ô máy
    /** 1 máy trong màn nhiều máy: thanh tên nhỏ + hình (StreamView điều khiển được) + màn chờ. Mỗi ô 1 phiên điều khiển riêng. */
    private final class Tile extends LinearLayout implements StreamClient.Listener, StreamView.Events, StreamView.Mirror {
        final String id;
        final StreamView screen;
        String name;
        int index = 0;
        float ar = 9f / 16f;                                 // rộng / cao của hình (đoán theo độ phân giải máy, rồi theo máy chủ báo)
        StreamClient client;
        private final LinearLayout head;
        private final TextView dot, label, alone, zoom;
        private final FrameLayout body, veil;
        private final TextView veilText, veilBtn;
        private Runnable veilAct;
        private String q = "", srvMsg = "";
        private int maxh = 0, fps = 0, kbps = 0;
        private boolean halted = false, frame = false, shown = true;

        Tile(Context c, String phoneId, JSONObject p) {
            super(c);
            id = phoneId;
            name = p.optString("name", Ui.L("Máy", "Phone"));
            setOrientation(VERTICAL);
            int bz = Ui.dp(2);
            setPadding(bz, bz, bz, bz);

            head = Ui.row(c, 4);
            head.setPadding(Ui.dp(6), 0, Ui.dp(2), 0);
            dot = Ui.text(c, "●", 9, C_DIM, false);
            head.addView(dot, Ui.wrap());
            label = Ui.text(c, name, 11.5f, Color.WHITE, true);
            label.setSingleLine(true);
            label.setEllipsize(TextUtils.TruncateAt.END);
            head.addView(label, Ui.weight(1));
            alone = headBtn(c, "↗", Ui.L("Mở riêng máy này (đủ công cụ)", "Open this phone alone (all tools)"), v -> openAlone(index));
            head.addView(alone, new LayoutParams(Ui.dp(30), -1));
            zoom = headBtn(c, "⤢", "", v -> { if (focusMode) setFocusMode(false, index); else setFocusMode(true, index); });
            head.addView(zoom, new LayoutParams(Ui.dp(30), -1));
            head.setOnClickListener(v -> setActive(index));
            addView(head, new LayoutParams(-1, Ui.dp(26)));

            body = new FrameLayout(c);
            body.setBackgroundColor(Color.BLACK);
            screen = new StreamView(c, false, true);
            screen.setEvents(this);
            screen.setMirror(this);
            int[] wh = MainActivity.resWH(p);
            screen.setVideoSize(wh[0], wh[1]);
            ar = wh[0] / (float) wh[1];
            body.addView(screen, new FrameLayout.LayoutParams(-1, -1));
            veil = new FrameLayout(c);
            veil.setBackgroundColor(Color.argb(236, 6, 12, 26));
            veil.setClickable(true);                         // đang chờ / báo lỗi: chạm không lọt xuống màn hình máy
            LinearLayout vb = Ui.col(c, 6);
            vb.setGravity(Gravity.CENTER);
            vb.setPadding(Ui.dp(8), Ui.dp(6), Ui.dp(8), Ui.dp(6));
            veilText = Ui.text(c, "", 12, Color.WHITE, false);
            veilText.setGravity(Gravity.CENTER);
            veilText.setMaxLines(6);
            veilText.setEllipsize(TextUtils.TruncateAt.END);
            vb.addView(veilText, Ui.fill());
            veilBtn = Ui.text(c, "", 12, Color.WHITE, true);
            veilBtn.setGravity(Gravity.CENTER);
            veilBtn.setPadding(Ui.dp(12), Ui.dp(6), Ui.dp(12), Ui.dp(7));
            veilBtn.setClickable(true);
            veilBtn.setFocusable(true);
            Ui.ripple(veilBtn, Color.argb(60, 61, 134, 255), 99, Color.argb(160, 120, 170, 255));
            veilBtn.setOnClickListener(v -> { Runnable r = veilAct; if (r != null) r.run(); });
            LayoutParams bl = Ui.wrap();
            bl.gravity = Gravity.CENTER_HORIZONTAL;
            vb.addView(veilBtn, bl);
            veil.addView(vb, new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER));
            body.addView(veil, new FrameLayout.LayoutParams(-1, -1));
            addView(body, new LayoutParams(-1, 0, 1f));
            showVeil(Ui.L("Đang kết nối…", "Connecting…"), null, null);
            paint();
        }

        private TextView headBtn(Context c, String icon, String desc, OnClickListener on) {
            TextView t = Ui.text(c, icon, 14, Color.WHITE, false);
            t.setGravity(Gravity.CENTER);
            t.setClickable(true);
            t.setFocusable(true);
            if (!desc.isEmpty()) {
                t.setContentDescription(desc);
                if (Build.VERSION.SDK_INT >= 26) t.setTooltipText(desc);
            }
            Ui.ripple(t, Color.TRANSPARENT, 8, 0);
            t.setOnClickListener(on);
            return t;
        }

        void rename(JSONObject p) {
            name = p.optString("name", name);
            paint();
        }

        boolean live() { return client != null && client.isLive(); }

        /** Viền + thanh tên theo trạng thái: ô đang chọn viền xanh dương; đang đồng bộ mọi ô viền xanh lá. */
        void paint() {
            boolean act = index == active, sy = sync && tiles.size() > 1;
            android.graphics.drawable.GradientDrawable bg = new android.graphics.drawable.GradientDrawable();
            bg.setColor(C_HEAD);
            bg.setCornerRadius(Ui.dp(7));
            bg.setStroke(Ui.dp(sy || act ? 2 : 1), sy ? C_SYNC : act ? C_ACT : C_EDGE);
            setBackground(bg);
            dot.setTextColor(halted ? Color.rgb(255, 107, 129) : frame && live() ? Color.rgb(60, 224, 176) : Color.rgb(255, 214, 102));
            label.setText((index + 1) + " · " + name);       // số thứ tự = số trên thanh đổi máy (kiểu 1 máy to)
            label.setTextColor(act || sy ? Color.WHITE : C_DIM);
            zoom.setText(focusMode ? "▦" : "⤢");
            String zd = focusMode ? Ui.L("Về lưới nhiều máy", "Back to the grid") : Ui.L("Xem máy này to", "Make this phone big");
            zoom.setContentDescription(zd);
            if (Build.VERSION.SDK_INT >= 26) zoom.setTooltipText(zd);
            zoom.setVisibility(tiles.size() > 1 ? VISIBLE : GONE);
        }

        @Override protected void onSizeChanged(int w, int hh, int ow, int oh) {
            super.onSizeChanged(w, hh, ow, oh);
            final boolean wide = w >= Ui.dp(150);                 // ô hẹp: giấu nút ↗ cho tên máy có chỗ (vẫn mở riêng được ở ⋯ Thêm)
            if ((alone.getVisibility() == VISIBLE) != wide) post(() -> alone.setVisibility(wide ? VISIBLE : GONE));
        }

        void setShown(boolean on) {
            if (shown == on && (getVisibility() == VISIBLE) == on) return;
            shown = on;
            setVisibility(on ? VISIBLE : GONE);
            screen.setSurfaceShown(on);
        }

        /** Phiên ô này cần có: mức chất lượng q, cạnh dài tối đa, khung/giây, trần kbps. Khác q / cạnh dài → mở phiên mới;
         *  chỉ khác khung / kbps → đổi ngay trên phiên đang chạy. Ô đã dừng hẳn (bị đá, máy tắt…) thì chờ khách bấm nút trên ô. */
        void want(String nq, int nMaxh, int nFps, int nKbps) {
            if (halted) return;
            if (client != null && nq.equals(q) && nMaxh == maxh) {
                if (nFps != fps || nKbps != kbps) { fps = nFps; kbps = nKbps; client.limit(nFps, nKbps); }
                return;
            }
            q = nq; maxh = nMaxh; fps = nFps; kbps = nKbps;
            connect();
        }

        /** Ô KHUẤT nhưng vẫn phải nhận lệnh (đang đồng bộ): còn phiên thì giữ nguyên phiên đó, chỉ hạ khung / kbps cho nhẹ;
         *  chưa có phiên → mở phiên nhẹ. (Không đóng mở lại chỉ để đổi cỡ hình của 1 ô không ai nhìn.) */
        void keep(String nq, int nMaxh, int nFps, int nKbps) {
            if (halted) return;
            if (client == null) { want(nq, nMaxh, nFps, nKbps); return; }
            if (nFps != fps || nKbps != kbps) { fps = nFps; kbps = nKbps; client.limit(nFps, nKbps); }
        }

        private void connect() {
            drop();
            halted = false;
            frame = false;
            srvMsg = "";
            showVeil(Ui.L("Đang kết nối…", "Connecting…"), null, null);
            client = new StreamClient(MultiActivity.this, id, q, this);
            if (maxh > 0 || fps > 0 || kbps > 0) client.tile(maxh, fps, kbps);
            screen.attach(client);
            client.start();
            paint();
        }

        private void drop() {
            fan.drop(port, tiles.size(), index);             // ô này đang dẫn 1 cú chạm đồng bộ → nhấc ngón trên các máy theo
            if (client != null) { client.close(); client = null; }
            screen.attach(null);
        }

        /** Đóng phiên, giữ ô (want() mở lại). */
        void stop() {
            boolean had = client != null;
            drop();
            frame = false;
            if (had && !halted) showVeil(Ui.L("Đang tạm nghỉ", "Paused"), null, null);
            paint();
        }

        /** Cho ô đã dừng hẳn nối lại (nút trên ô / "Nối lại tất cả"). */
        void retry() {
            halted = false;
            if (client != null) { String keep = q; q = ""; want(keep, maxh, fps, kbps); }
        }

        private void again() {
            halted = false;
            q = q.isEmpty() ? "eco" : q;
            connect();
            applyAll();                                      // đặt lại đúng mức hình theo kiểu xem hiện tại
        }

        private void showVeil(String t, String btn, Runnable act) {
            veil.setVisibility(VISIBLE);
            veilText.setText(t);
            veilAct = act;
            if (btn != null && act != null) { veilBtn.setText(btn); veilBtn.setVisibility(VISIBLE); }
            else veilBtn.setVisibility(GONE);
        }

        private void halt(String t, String btn, Runnable act) {
            drop();
            halted = true;
            frame = false;
            showVeil(t, btn, act);
            paint();
        }

        // ---- StreamView.Events (luồng giao diện) ----
        @Override public void onFirstFrame() {
            if (client == null || halted || dead) return;
            frame = true;
            srvMsg = "";
            veil.setVisibility(GONE);
            paint();
            if (!blueDone) { blueDone = true; Blue.playTask(MultiActivity.this); }     // 💎 nhiệm vụ "mở máy đám mây" hôm nay (như màn 1 máy)
        }

        @Override public void onTouchDown() { setActive(index); }

        @Override public void onVideoSize(int w, int hh) {
            if (w <= 0 || hh <= 0) return;
            float n = w / (float) hh;
            if (Math.abs(n - ar) < 0.01f) return;
            ar = n;                                          // máy xoay ngang / dọc → chia lại lưới
            board.requestLayout();
        }

        // ---- StreamView.Mirror: ô này vừa gửi 1 lệnh cho máy của nó → đang đồng bộ thì gửi y hệt sang các máy khác ----
        @Override public void touch(int action, int pointer, float nx, float ny) {
            if (sync) fan.touch(port, tiles.size(), index, action, pointer, nx, ny);
        }

        @Override public void scroll(float nx, float ny, int sh, int sv) {
            if (!sync) return;
            for (Tile t : tiles) if (t != this && t.live()) t.client.scroll(nx, ny, sh, sv);
        }

        // ---- StreamClient.Listener (luồng giao diện; không gọi nữa sau close()) ----
        @Override public void onConnecting(int attempt, String why) {
            if (halted) return;
            frame = false;
            if (attempt <= 0) showVeil(Ui.L("Đang kết nối…", "Connecting…"), null, null);
            else showVeil(!srvMsg.isEmpty() ? srvMsg : Ui.L("Đang kết nối lại…", "Reconnecting…") + (why == null || why.isEmpty() ? "" : "\n" + why), null, null);
            paint();
        }

        @Override public void onEndpoint(JSONObject ep) { }
        @Override public void onWelcome(JSONObject welcome, boolean direct) {      // vào phiên: ô khuất (đang đồng bộ) bắt đầu nhận lệnh → vẽ lại thanh số
            rail.invalidate();
        }
        @Override public void onClipboard(String text) { }       // nhiều máy cùng báo → không đụng bộ nhớ copy của điện thoại
        @Override public void onStats(int f, int k, int pingMs, boolean direct, JSONObject server) { }
        @Override public void onProblem(String code, String msg) { onProblemX(code, msg, null); }

        @Override public void onProblemX(String code, String msg, JSONObject x) {
            if (halted) return;
            boolean fix = x != null && "reboot".equals(x.optString("fix", ""));
            srvMsg = msg == null ? "" : Ui.srv(msg);
            if (fix) showVeil(srvMsg, Ui.L("Mở riêng để sửa", "Open alone to fix"), () -> openAlone(index));   // khởi động lại máy nằm ở màn 1 máy
            else showVeil(srvMsg, null, null);
        }

        @Override public void onStopped(String code, String msg) {
            if (dead || isFinishing()) return;               // ô khác vừa báo hết phiên đăng nhập → màn đang đóng
            if ("LOGIN".equals(code)) {                      // phiên đăng nhập hết hẳn → đăng nhập lại
                Api.logout();
                startActivity(new Intent(MultiActivity.this, LoginActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
                finish();
                return;
            }
            if ("KICKED".equals(code)) {
                halt("📱 " + Ui.L("Máy đang được mở ở nơi khác", "Open somewhere else"), Ui.L("Mở lại tại đây", "Open here"), this::again);
                return;
            }
            halt(msg == null || msg.isEmpty() ? Ui.L("Không mở được máy.", "Couldn't open this phone.") : Ui.srv(msg), Ui.L("Thử lại", "Retry"), this::again);
        }
    }

    // ================================================================ Bảng xếp ô
    /** Xếp các ô đang hiện: 1 ô → phủ kín · nhiều ô → lưới có tổng diện tích màn máy lớn nhất (hàng cuối thiếu ô thì nằm giữa). */
    private final class Board extends ViewGroup {
        private int[][] rects = new int[0][];
        private final ArrayList<Tile> vis = new ArrayList<>();

        Board(Context c) { super(c); setBackgroundColor(Color.BLACK); }

        @Override public boolean shouldDelayChildPressedState() { return false; }

        private void plan(int W, int H) {
            vis.clear();
            for (Tile t : tiles) if (t.getParent() == this && t.getVisibility() != GONE) vis.add(t);   // theo thứ tự danh sách máy
            float[] ars = new float[vis.size()];
            for (int i = 0; i < ars.length; i++) ars[i] = vis.get(i).ar;
            rects = Grid.rects(ars, W, H, Ui.dp(4), Ui.dp(4), Ui.dp(30));
        }

        @Override protected void onMeasure(int ws, int hs) {
            int W = MeasureSpec.getSize(ws), H = MeasureSpec.getSize(hs);
            setMeasuredDimension(W, H);
            plan(W, H);
            for (int i = 0; i < vis.size(); i++) {
                int[] r = rects[i];
                vis.get(i).measure(MeasureSpec.makeMeasureSpec(Math.max(1, r[2] - r[0]), MeasureSpec.EXACTLY),
                        MeasureSpec.makeMeasureSpec(Math.max(1, r[3] - r[1]), MeasureSpec.EXACTLY));
            }
        }

        @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
            if (rects.length != vis.size()) plan(r - l, b - t);
            for (int i = 0; i < vis.size() && i < rects.length; i++) {
                int[] q = rects[i];
                vis.get(i).layout(q[0], q[1], Math.max(q[0] + 1, q[2]), Math.max(q[1] + 1, q[3]));
            }
        }
    }

    /** Tính lưới (thuần số, không đụng giao diện — chạy thử được ngoài điện thoại). */
    static final class Grid {
        private Grid() { }

        /** Diện tích hình tỉ lệ ar (rộng / cao) đặt vừa khung vw × vh. */
        static double fit(double vw, double vh, double ar) {
            if (vw <= 0 || vh <= 0 || ar <= 0) return 0;
            return vw / vh > ar ? (vh * ar) * vh : vw * (vw / ar);
        }

        /** Số cột tốt nhất cho n ô trong khung W × H: thử mọi số cột, chọn cách cho TỔNG diện tích màn máy lớn nhất.
         *  gap = khe giữa các ô · cw / ch = phần viền + thanh tên của mỗi ô (không phải hình). */
        static int cols(float[] ars, int W, int H, int gap, int cw, int ch) {
            int n = ars.length, best = 1;
            double bestArea = -1;
            for (int c = 1; c <= n; c++) {
                int r = (n + c - 1) / c;
                double tw = (W - (double) gap * (c - 1)) / c, th = (H - (double) gap * (r - 1)) / r;
                double vw = tw - cw, vh = th - ch;
                if (vw < 24 || vh < 24) continue;
                double area = 0;
                for (float ar : ars) area += fit(vw, vh, ar);
                if (area > bestArea * 1.0001) { bestArea = area; best = c; }
            }
            if (bestArea < 0) best = Math.max(1, Math.min(n, (int) Math.ceil(Math.sqrt(n))));   // chật quá mức: chia đều
            return best;
        }

        /** Khung (trái, trên, phải, dưới) của từng ô. */
        static int[][] rects(float[] ars, int W, int H, int gap, int cw, int ch) {
            int n = ars.length;
            int[][] out = new int[n][4];
            if (n == 0 || W <= 0 || H <= 0) return out;
            if (n == 1) { out[0] = new int[]{0, 0, W, H}; return out; }
            int c = cols(ars, W, H, gap, cw, ch), r = (n + c - 1) / c;
            if (W - gap * (c - 1) < c || H - gap * (r - 1) < r) gap = 0;   // khung còn nhỏ hơn cả khe (lúc chưa đo xong màn) → bỏ khe
            double tw = Math.max(1, (W - (double) gap * (c - 1)) / c), th = Math.max(1, (H - (double) gap * (r - 1)) / r);
            for (int i = 0; i < n; i++) {
                int row = i / c, col = i % c, inRow = Math.min(c, n - row * c);
                double x0 = inRow < c ? (W - (inRow * tw + gap * (inRow - 1))) / 2 : 0;
                int x = (int) Math.round(x0 + col * (tw + gap)), y = (int) Math.round(row * (th + gap));
                int x2 = (int) Math.round(x0 + col * (tw + gap) + tw), y2 = (int) Math.round(row * (th + gap) + th);
                x = Math.max(0, Math.min(W - 1, x));
                y = Math.max(0, Math.min(H - 1, y));
                out[i] = new int[]{x, y, Math.max(x + 1, Math.min(W, x2)), Math.max(y + 1, Math.min(H, y2))};
            }
            return out;
        }
    }

    // ================================================================ Bộ đồng bộ cú chạm
    /** Gửi lại cú chạm của 1 ô sang các ô khác (thuần logic, chạy thử được ngoài điện thoại).
     *  Quy tắc: chỉ chuyển tiếp KÉO / NHẤC của ngón mà lần CHẠM XUỐNG đã được chuyển tiếp (bật đồng bộ giữa chừng không sinh
     *  "nhấc ngón" lạc) · tắt đồng bộ / rời màn / ô dẫn đổi phiên lúc đang giữ ngón → nhấc ngón đó trên các máy đang theo. */
    static final class Fan {
        interface Port {
            boolean live(int i);
            void touch(int i, int action, int pointer, float x, float y);
        }

        private final int[] src = new int[10];
        private final float[] lx = new float[10], ly = new float[10];
        private int mask = 0;

        /** Ô "from" vừa gửi 1 lệnh chạm cho máy của nó. n = số ô. */
        void touch(Port port, int n, int from, int action, int pointer, float x, float y) {
            if (pointer < 0 || pointer > 9) return;
            int bit = 1 << pointer;
            if (action == StreamClient.TOUCH_DOWN) {
                if ((mask & bit) != 0) lift(port, n, pointer);           // ngón cũ chưa nhấc (lỡ mất sự kiện) → nhấc trước
                mask |= bit;
                src[pointer] = from;
            } else if ((mask & bit) == 0 || src[pointer] != from) {
                return;
            }
            lx[pointer] = x;
            ly[pointer] = y;
            for (int i = 0; i < n; i++) if (i != from && port.live(i)) port.touch(i, action, pointer, x, y);
            if (action == StreamClient.TOUCH_UP || action == StreamClient.TOUCH_CANCEL) mask &= ~bit;
        }

        private void lift(Port port, int n, int pointer) {
            int from = src[pointer];
            for (int i = 0; i < n; i++) if (i != from && port.live(i)) port.touch(i, StreamClient.TOUCH_CANCEL, pointer, lx[pointer], ly[pointer]);
            mask &= ~(1 << pointer);
        }

        /** Thôi đồng bộ: nhấc mọi ngón đang giữ trên các máy đang theo. */
        void release(Port port, int n) {
            for (int p = 0; p < 10; p++) if ((mask & (1 << p)) != 0) lift(port, n, p);
            mask = 0;
        }

        /** Ô "from" sắp đổi / đóng phiên: các ngón nó đang dẫn → nhấc trên các máy đang theo. */
        void drop(Port port, int n, int from) {
            for (int p = 0; p < 10; p++) if ((mask & (1 << p)) != 0 && src[p] == from) lift(port, n, p);
        }

        boolean idle() { return mask == 0; }
    }

    // ================================================================ Thanh số (kiểu 1 máy to)
    /** Thanh dọc bên phải: ▲ · số thứ tự các máy · ▼. Vuốt LÊN = máy kế, vuốt XUỐNG = máy trước (kéo dài thì qua nhiều máy);
     *  bấm số = tới máy đó. Nằm ngoài hình của máy nên không đụng thao tác vuốt bên trong máy. */
    private final class Rail extends View {
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Rect self = new Rect();
        private float anchor, downY;
        private boolean moved;

        Rail(Context c) {
            super(c);
            setBackgroundColor(Color.rgb(6, 12, 26));
            setContentDescription(Ui.L("Thanh đổi máy: vuốt lên hoặc xuống để qua máy khác", "Phone switcher: swipe up or down"));
            p.setTextAlign(Paint.Align.CENTER);
            p.setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD));
        }

        private float arrowH() { return Math.min(Ui.dp(40), getHeight() * 0.16f); }

        private float itemH(int n) { return n <= 0 ? 0 : Math.min(Ui.dp(40), (getHeight() - 2 * arrowH()) / n); }

        /** Mép trên của dãy số: dãy số nằm GIỮA ▲ và ▼ (ít máy thì không dồn hết lên trên). */
        private float itemsTop(int n) { return arrowH() + Math.max(0f, (getHeight() - 2 * arrowH() - itemH(n) * n) / 2f); }

        @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
            super.onLayout(changed, l, t, r, b);
            if (Build.VERSION.SDK_INT >= 29) {                // vuốt dọc sát mép phải: không để hệ thống hiểu là cử chỉ Quay lại
                self.set(0, 0, r - l, Math.min(b - t, Ui.dp(200)));
                setSystemGestureExclusionRects(Collections.singletonList(self));
            }
        }

        @Override protected void onDraw(Canvas cv) {
            int n = tiles.size(), W = getWidth();
            if (n <= 0 || W <= 0) return;
            float ah = arrowH(), ih = itemH(n), top = itemsTop(n), cx = W / 2f;
            p.setStyle(Paint.Style.FILL);
            p.setColor(C_DIM);
            p.setTextSize(Math.min(Ui.dp(15), ah * 0.5f));
            cv.drawText("▲", cx, ah / 2f - (p.descent() + p.ascent()) / 2f, p);
            cv.drawText("▼", cx, getHeight() - ah / 2f - (p.descent() + p.ascent()) / 2f, p);
            float rad = Math.min(W * 0.36f, ih * 0.42f);
            p.setTextSize(Math.max(Ui.dp(8), Math.min(Ui.dp(13), rad * 1.15f)));
            for (int i = 0; i < n; i++) {
                float cy = top + ih * (i + 0.5f);
                boolean cur = i == focus;
                Tile t = tiles.get(i);
                p.setStyle(Paint.Style.FILL);
                p.setColor(cur ? C_ACT : Color.argb(60, 120, 160, 255));
                cv.drawCircle(cx, cy, rad, p);
                if (!cur && sync && t.live()) {              // đang đồng bộ: máy khuất vẫn nhận lệnh → viền xanh lá
                    p.setStyle(Paint.Style.STROKE);
                    p.setStrokeWidth(Ui.dp(1.5f));
                    p.setColor(C_SYNC);
                    cv.drawCircle(cx, cy, rad, p);
                    p.setStyle(Paint.Style.FILL);
                }
                p.setColor(cur ? Color.WHITE : C_DIM);
                cv.drawText(String.valueOf(i + 1), cx, cy - (p.descent() + p.ascent()) / 2f, p);
            }
        }

        @Override public boolean onTouchEvent(MotionEvent e) {
            int n = tiles.size();
            if (n <= 1) return false;
            final float stepPx = Ui.dp(40);
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    downY = anchor = e.getY();
                    moved = false;
                    if (getParent() != null) getParent().requestDisallowInterceptTouchEvent(true);
                    return true;
                case MotionEvent.ACTION_MOVE: {
                    float y = e.getY();
                    while (y - anchor <= -stepPx) { anchor -= stepPx; moved = true; step(1); }      // vuốt lên → máy kế
                    while (y - anchor >= stepPx) { anchor += stepPx; moved = true; step(-1); }      // vuốt xuống → máy trước
                    return true;
                }
                case MotionEvent.ACTION_UP: {
                    if (moved || Math.abs(e.getY() - downY) > Ui.dp(12)) return true;
                    float y = e.getY(), ah = arrowH(), ih = itemH(n), top = itemsTop(n);
                    if (y < ah) step(-1);
                    else if (y > getHeight() - ah) step(1);
                    else if (ih > 0 && y >= top && y < top + ih * n) go(Math.max(0, Math.min(n - 1, (int) ((y - top) / ih))));
                    performClick();
                    return true;
                }
                case MotionEvent.ACTION_CANCEL:
                    return true;
                default:
                    return false;
            }
        }

        @Override public boolean performClick() { return super.performClick(); }
    }
}
