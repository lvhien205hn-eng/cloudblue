package shop.blueroblox.app;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.os.SystemClock;
import android.view.View;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.VelocityTracker;
import android.view.ViewGroup;

import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Màn hình máy cloud: SurfaceView + bộ giải mã H.264 phần cứng (MediaCodec chế độ callback, chạy trên luồng riêng "BRS-decode").
 * Khung nào tới là đưa vào giải mã ngay, giải mã xong là hiện ngay (không đệm, không canh giờ).
 * Hình luôn đúng tỉ lệ (viền đen hai bên / trên dưới); chạm được đổi về toạ độ 0..1 trên khung hình rồi gửi qua StreamClient.
 */
public final class StreamView extends ViewGroup implements SurfaceHolder.Callback, StreamClient.VideoSink {
    public interface Events {
        /** Khung hình đầu tiên đã hiện (sau mỗi lần dựng lại bộ giải mã). Luồng giao diện. */
        void onFirstFrame();
        /** Ngón đầu tiên vừa chạm vào hình. Luồng giao diện. */
        void onTouchDown();
        /** Máy chủ báo cỡ hình (mở phiên / máy xoay ngang-dọc / đổi độ nét). Luồng giao diện. */
        default void onVideoSize(int w, int h) { }
    }

    /** 18/11 · màn "nhiều máy": nhận lại MỌI lệnh chạm / lăn mà ô này vừa gửi cho máy của nó — để gửi y hệt sang các máy khác khi
     *  khách bật Đồng bộ. Gọi trên luồng giao diện, ngay sau lệnh gửi cho máy của ô. Không đặt (mặc định) → ô chạy y như trước. */
    public interface Mirror {
        void touch(int action, int pointer, float nx, float ny);
        void scroll(float nx, float ny, int h, int v);
    }

    private static final String MIME = "video/avc";

    private final SurfaceView sv;
    private final boolean preview;                // ô xem trước: không nhận chạm (bấm ô = mở màn điều khiển), giải mã ưu tiên thường, ít bộ nhớ
    private final Handler main = new Handler(Looper.getMainLooper());
    private final HandlerThread thread;
    private final Handler dec;
    private volatile StreamClient client;
    private volatile boolean released = false;
    private Events events;
    private Mirror mirror;

    // ---- luồng giao diện: bố cục + chạm ----
    private int vidW = 9, vidH = 16;
    private int picX, picY, picW, picH;
    private int downMask = 0;
    private final float[] lastX = new float[10], lastY = new float[10];

    // ---- 21/11f · máy PC: KIỂU CHẠM (như Chrome Remote Desktop) + phóng to / kéo hình tại chỗ (chỉ trong app, máy PC không biết) ----
    public static final int IN_TOUCH = 0, IN_PAD = 1, IN_ZOOM2 = 2, IN_ZOOM3 = 3;
    private int inMode = IN_TOUCH;
    private int vX, vY, vW, vH, lastW = -1, lastH = -1;     // hình đang hiện (đã phóng / kéo); không phóng = đúng khung vừa màn
    private float zs = 1f, zSpan0 = 1f, zS0 = 1f, zU = .5f, zV = .5f;
    private boolean zooming = false;
    private Cursor cursor;                                   // con trỏ tại chỗ (kiểu Bàn di chuột) — hiện ngay, không chờ hình về
    private float curX = .5f, curY = .5f, pLastX, pLastY, pDownX, pDownY, pMoved, sAcc;
    private long pDownT, pLastTapT, mvAt;
    private boolean pDrag, pTwo, pTwoMoved, pLong, mvPend;

    // ---- luồng giải mã (chỉ BRS-decode đụng vào) ----
    private Surface surface;
    private MediaCodec codec;
    private volatile int gen = 0;                 // đời bộ giải mã: callback của bộ cũ bị bỏ qua (luồng giao diện đọc để bỏ báo "khung đầu" cũ)
    private boolean parked = false;               // dropSurface(): tạm không dựng bộ giải mã (ô sắp bị gỡ / chuyển chỗ)
    private int fmtW = 0, fmtH = 0;
    private byte[] sps, pps;
    private boolean wantKey = true, shown = false;
    private int maxIn;
    private int fails = 0, okFrames = 0;
    private long lastPts = 0;
    private final ArrayDeque<Integer> inputs = new ArrayDeque<>();
    private final ArrayDeque<Frame> pend = new ArrayDeque<>();

    public StreamView(Context c) { this(c, false); }

    /** preview = ô xem trước nhỏ (chạm đi thẳng xuống ô cha để mở màn điều khiển). */
    public StreamView(Context c, boolean preview) { this(c, preview, preview); }

    /** 18/11 · small = ô NHỎ đứng chung nhiều ô (xem trước, hoặc ô điều khiển trong màn "nhiều máy"): ô nhập nhỏ + giải mã ưu tiên
     *  thường. preview = không nhận chạm. Ô "nhiều máy": preview = false (điều khiển được), small = true. */
    public StreamView(Context c, boolean preview, boolean small) {
        super(c);
        this.preview = preview;
        maxIn = small ? 256 << 10 : 1 << 20;          // hình nhỏ: ô nhập nhỏ (nhiều ô cùng lúc đỡ tốn bộ nhớ); khung to hơn tự nới
        setBackgroundColor(Color.BLACK);
        sv = new SurfaceView(c);
        sv.getHolder().addCallback(this);
        addView(sv);
        thread = new HandlerThread(preview ? "BRS-preview" : small ? "BRS-tile" : "BRS-decode");
        thread.start();
        dec = new Handler(thread.getLooper());
        final int prio = small ? android.os.Process.THREAD_PRIORITY_DEFAULT : android.os.Process.THREAD_PRIORITY_URGENT_DISPLAY;
        dec.post(() -> {
            try { android.os.Process.setThreadPriority(prio); } catch (Throwable ignored) { }
        });
    }

    public void setEvents(Events e) { events = e; }

    /** 18/11 · màn "nhiều máy": nơi nhận lại lệnh chạm / lăn của ô này (null = thôi). Luồng giao diện. */
    public void setMirror(Mirror m) { mirror = m; }

    /** 18/11 · màn "nhiều máy": ẩn / hiện HẲN mặt vẽ của ô (ẩn → Surface bị huỷ, bộ giải mã dừng; hiện → dựng lại ở khung khoá tới).
     *  Phải đặt trên chính SurfaceView: chỉ ẩn ô cha thì Android 7 vẫn để hình cũ nằm lại trên màn, các bản sau vẫn giải mã ngầm. */
    public void setSurfaceShown(boolean on) {
        int v = on ? VISIBLE : GONE;
        if (sv.getVisibility() != v) sv.setVisibility(v);
    }

    /** Gắn client (null = bỏ): chạm gửi về client này, hình của client này vẽ ra đây. */
    public void attach(StreamClient c) {
        StreamClient old = client;
        if (old == c) return;
        if (old != null) old.setVideoSink(null);
        client = c;
        downMask = 0;
        if (c != null) c.setVideoSink(this);
        dec.post(this::resetStream);
    }

    /** Tỉ lệ hình (độ phân giải máy lúc đầu, rồi WELCOME / SIZE). Luồng giao diện. */
    public void setVideoSize(int w, int h) {
        if (w <= 0 || h <= 0 || (w == vidW && h == vidH)) return;
        vidW = w;
        vidH = h;
        requestLayout();
    }

    /** Ô sắp bị gỡ khỏi chỗ (chuyển hàng loạt ô xem trước): dừng bộ giải mã NGAY ở luồng giải mã của ô này, không chờ — các ô dừng
     *  song song, lúc Surface bị huỷ khỏi phải đợi từng ô một (giao diện đứng). Không bị gỡ thật thì 1,5 giây sau tự vẽ tiếp. */
    public void dropSurface() {
        if (released) return;
        dec.post(() -> { releaseCodec(); wantKey = true; parked = true; });
        dec.postDelayed(() -> parked = false, 1500);
    }

    /** Gọi ở onDestroy: dừng bộ giải mã + luồng giải mã. */
    public void release() {
        if (released) return;
        tCancel();
        if (tVt != null) { tVt.recycle(); tVt = null; }
        attach(null);
        released = true;
        dec.post(() -> { releaseCodec(); surface = null; });
        thread.quitSafely();
    }

    // ================================================================ bố cục: hình giữa, đúng tỉ lệ

    @Override protected void onMeasure(int ws, int hs) {
        int w = MeasureSpec.getSize(ws), h = MeasureSpec.getSize(hs);
        setMeasuredDimension(w, h);
        fit(w, h);
        view(w, h);
        sv.measure(MeasureSpec.makeMeasureSpec(Math.max(1, vW), MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(Math.max(1, vH), MeasureSpec.EXACTLY));
        if (cursor != null) cursor.measure(MeasureSpec.makeMeasureSpec(cursor.w, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(cursor.h, MeasureSpec.EXACTLY));
    }

    @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
        int w = r - l, h = b - t;
        fit(w, h);
        view(w, h);
        sv.layout(vX, vY, vX + vW, vY + vH);
        placeCursor();
    }

    /** 21/11f · khung hình đang hiện: không phóng = vừa màn (viền đen); phóng to = to hơn khung, kéo được, không lòi mép trống. */
    private void view(int w, int h) {
        if (w != lastW || h != lastH) { if (lastW > 0) zs = 1f; lastW = w; lastH = h; }    // xoay máy / đổi cỡ → về vừa màn
        if (zs <= 1.001f) { zs = 1f; vX = picX; vY = picY; vW = picW; vH = picH; return; }
        int nw = Math.round(picW * zs), nh = Math.round(picH * zs);
        if (vW <= 0) { vX = (w - nw) / 2; vY = (h - nh) / 2; }
        vW = nw; vH = nh;
        vX = vW <= w ? (w - vW) / 2 : Math.max(w - vW, Math.min(0, vX));
        vY = vH <= h ? (h - vH) / 2 : Math.max(h - vH, Math.min(0, vY));
    }

    @Override public boolean shouldDelayChildPressedState() { return false; }

    private void fit(int w, int h) {
        if (w <= 0 || h <= 0) { picX = 0; picY = 0; picW = Math.max(0, w); picH = Math.max(0, h); return; }
        long vw = vidW, vh = vidH;
        if (w * vh > h * vw) { picH = h; picW = (int) Math.max(1, h * vw / vh); }
        else { picW = w; picH = (int) Math.max(1, w * vh / vw); }
        picX = (w - picW) / 2;
        picY = (h - picH) / 2;
    }

    // ================================================================ chạm (nhiều ngón) → toạ độ 0..1 trên khung hình

    @Override public boolean onInterceptTouchEvent(MotionEvent e) { return !preview; }

    @Override public boolean onTouchEvent(MotionEvent e) {
        if (preview) return false;                                       // ô xem trước: để ô cha nhận bấm
        if (inMode == IN_PAD) return padTouch(e);                        // 21/11f · bàn di chuột
        if ((inMode == IN_ZOOM2 || inMode == IN_ZOOM3) && zoomTouch(e)) return true;   // 21/11f · 2 / 3 ngón = phóng to / kéo hình
        if (pcInput) return pcTouch(e);                                 // 22/11 · máy PC: vuốt = cuộn, giữ rồi kéo = bôi đen (xử lý ngay trên điện thoại)
        StreamClient c = client;
        final Mirror mr = mirror;
        int act = e.getActionMasked();
        switch (act) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_POINTER_DOWN: {
                int i = e.getActionIndex(), id = e.getPointerId(i);
                if (id < 0 || id > 9 || vW <= 0 || vH <= 0) break;
                float x = e.getX(i) - vX, y = e.getY(i) - vY;
                if (x < 0 || y < 0 || x > vW || y > vH) break;           // chạm vào viền đen → bỏ qua ngón này
                if (act == MotionEvent.ACTION_DOWN && events != null) events.onTouchDown();
                downMask |= 1 << id;
                lastX[id] = x / vW;
                lastY[id] = y / vH;
                if (c != null) c.touch(StreamClient.TOUCH_DOWN, id, lastX[id], lastY[id]);
                if (mr != null) mr.touch(StreamClient.TOUCH_DOWN, id, lastX[id], lastY[id]);
                break;
            }
            case MotionEvent.ACTION_MOVE: {
                for (int i = 0; i < e.getPointerCount(); i++) {
                    int id = e.getPointerId(i);
                    if (id < 0 || id > 9 || (downMask & (1 << id)) == 0) continue;
                    lastX[id] = nx(e.getX(i));
                    lastY[id] = ny(e.getY(i));
                    if (c != null) c.touch(StreamClient.TOUCH_MOVE, id, lastX[id], lastY[id]);
                    if (mr != null) mr.touch(StreamClient.TOUCH_MOVE, id, lastX[id], lastY[id]);
                }
                break;
            }
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_POINTER_UP: {
                int i = e.getActionIndex(), id = e.getPointerId(i);
                if (id >= 0 && id <= 9 && (downMask & (1 << id)) != 0) {
                    downMask &= ~(1 << id);
                    lastX[id] = nx(e.getX(i));
                    lastY[id] = ny(e.getY(i));
                    if (c != null) c.touch(StreamClient.TOUCH_UP, id, lastX[id], lastY[id]);
                    if (mr != null) mr.touch(StreamClient.TOUCH_UP, id, lastX[id], lastY[id]);
                }
                if (act == MotionEvent.ACTION_UP && downMask != 0) cancelAll(c);   // ngón nào còn kẹt (lỡ mất sự kiện) → huỷ
                break;
            }
            case MotionEvent.ACTION_CANCEL:
                cancelAll(c);
                break;
            default:
                break;
        }
        return true;
    }

    private void cancelAll(StreamClient c) {
        final Mirror mr = mirror;
        for (int id = 0; id < 10; id++) {
            if ((downMask & (1 << id)) == 0) continue;
            if (c != null) c.touch(StreamClient.TOUCH_CANCEL, id, lastX[id], lastY[id]);
            if (mr != null) mr.touch(StreamClient.TOUCH_CANCEL, id, lastX[id], lastY[id]);
        }
        downMask = 0;
    }

    private float nx(float x) { return vW <= 0 ? 0f : Math.max(0f, Math.min(1f, (x - vX) / vW)); }
    private float ny(float y) { return vH <= 0 ? 0f : Math.max(0f, Math.min(1f, (y - vY) / vH)); }

    // ================================================================ 21/11f · kiểu chạm cho máy PC

    /** IN_TOUCH chạm trực tiếp · IN_PAD bàn di chuột · IN_ZOOM2 / IN_ZOOM3 chạm trực tiếp + 2 / 3 ngón kéo-phóng to hình (tại chỗ). */
    public void setInputMode(int m) {
        if (m < IN_TOUCH || m > IN_ZOOM3) m = IN_TOUCH;
        cancelAll(client);
        tCancel();
        if (pDrag) { StreamClient c = client; if (c != null) c.mouse(2, 0, curX, curY); }
        zooming = false; pDrag = false; pTwo = false;
        removeCallbacks(longPress);
        inMode = m;
        if (m == IN_TOUCH || m == IN_PAD) zs = 1f;                   // 2 kiểu này không phóng to → trả hình về vừa màn
        if (m == IN_PAD) { if (cursor == null) { cursor = new Cursor(getContext()); addView(cursor); } cursor.setVisibility(VISIBLE); }
        else if (cursor != null) cursor.setVisibility(GONE);
        requestLayout();
    }

    public int inputMode() { return inMode; }
    public boolean zoomed() { return zs > 1.01f; }
    public void resetZoom() { zs = 1f; requestLayout(); }

    private float dp(float v) { return v * getResources().getDisplayMetrics().density; }

    /** Tâm + độ xoè của các ngón đang chạm (bỏ ngón skip — ngón vừa nhấc). out = {x, y, xoè}. */
    private static void spread(MotionEvent e, int skip, float[] out) {
        float sx = 0, sy = 0; int n = 0;
        for (int i = 0; i < e.getPointerCount(); i++) { if (i == skip) continue; sx += e.getX(i); sy += e.getY(i); n++; }
        if (n == 0) { out[0] = e.getX(); out[1] = e.getY(); out[2] = 1; return; }
        sx /= n; sy /= n; float d = 0;
        for (int i = 0; i < e.getPointerCount(); i++) { if (i == skip) continue; d += (float) Math.hypot(e.getX(i) - sx, e.getY(i) - sy); }
        out[0] = sx; out[1] = sy; out[2] = Math.max(1f, d / n);
    }

    private final float[] sp = new float[3];

    private void zAnchor(MotionEvent e, int skip) {
        spread(e, skip, sp);
        zSpan0 = sp[2]; zS0 = zs;
        zU = vW <= 0 ? .5f : (sp[0] - vX) / vW;
        zV = vH <= 0 ? .5f : (sp[1] - vY) / vH;
    }

    /** true = sự kiện dùng để phóng to / kéo hình (không gửi máy PC). */
    private boolean zoomTouch(MotionEvent e) {
        int need = inMode == IN_ZOOM2 ? 2 : 3, act = e.getActionMasked();
        if (!zooming) {
            if (act == MotionEvent.ACTION_POINTER_DOWN && e.getPointerCount() >= need) {
                cancelAll(client);                                    // các ngón đã gửi máy → huỷ (không thành bấm / kéo)
                tCancel();
                zooming = true;
                zAnchor(e, -1);
                return true;
            }
            return false;                                             // ít ngón hơn → chạm thẳng vào máy như thường
        }
        switch (act) {
            case MotionEvent.ACTION_MOVE: {
                spread(e, -1, sp);
                float z = Math.max(1f, Math.min(6f, zS0 * sp[2] / Math.max(1f, zSpan0)));
                if (e.getPointerCount() < 2) z = zs;                   // còn 1 ngón → chỉ kéo
                zs = z;
                int nw = Math.round(picW * zs), nh = Math.round(picH * zs);
                vW = nw; vH = nh;
                vX = Math.round(sp[0] - zU * nw);
                vY = Math.round(sp[1] - zV * nh);
                requestLayout();
                break;
            }
            case MotionEvent.ACTION_POINTER_DOWN: zAnchor(e, -1); break;
            case MotionEvent.ACTION_POINTER_UP: zAnchor(e, e.getActionIndex()); break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL: zooming = false; break;
            default: break;
        }
        return true;
    }

    // ================================================================ 22/11 · MÁY PC — CHẠM TRỰC TIẾP xử lý NGAY trên điện thoại
    //  chạm = bấm trái · chạm 2 lần = bấm đúp · VUỐT 1 ngón = CUỘN trang (có trớn như điện thoại) · giữ yên rồi nhả = bấm phải
    //  giữ ~0,4 giây (rung nhẹ) rồi kéo = kéo thả / BÔI ĐEN chữ / kéo cửa sổ · 2 ngón vuốt = cuộn · 2 ngón chạm = bấm phải.
    //  Gửi máy PC chuột / lăn chuột thật (C_MOUSE / C_SCROLL). Trước đây gửi chạm thô để máy PC tự đoán: kéo 1 ngón = giữ chuột trái
    //  kéo → vuốt trang lên xuống lại thành BÔI ĐEN chữ; giữ / bấm đúp tính theo giờ máy PC nhận gói (mạng giật là sai).
    private boolean pcInput = false;

    /** Máy PC thật (ControlActivity gọi khi mở máy PC). Máy Android vẫn gửi chạm thô như cũ. */
    public void setPcInput(boolean on) { if (pcInput != on) { tCancel(); pcInput = on; } }

    private static final int T_NONE = 0, T_PEND = 1, T_SCROLL = 2, T_ARMED = 3, T_DRAG = 4, T_TWO = 5, T_SKIP = 6;
    private static final long T_LONG_MS = 420, T_DBL_MS = 350;
    private int tSt = T_NONE, tAxis = 0;
    private float tDx, tDy, tLx, tLy, tNx, tNy, tTapNx = -1f, tTapNy = -1f, tAccV, tAccH, tCx, tCy, tC0x, tC0y, tMx, tMy, flV, flH;
    private long tDownT, tTapT, tMvAt, flT;
    private boolean tTwoMoved, tMvPend;
    private VelocityTracker tVt;

    private final Runnable tLong = () -> {                    // giữ yên đủ lâu → sẵn sàng: nhả = chuột phải, kéo = kéo thả / bôi đen
        if (tSt != T_PEND) return;
        tSt = T_ARMED;
        performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS);
        StreamClient c = client; if (c != null) c.mouse(0, 0, tNx, tNy);
    };

    private final Runnable tMvSend = () -> { tMvPend = false; tMvAt = SystemClock.uptimeMillis(); StreamClient c = client; if (c != null) c.mouse(0, 0, tMx, tMy); };

    private void tMove(float x, float y) {                    // kéo: gửi vị trí tối đa ~80 lần / giây
        tMx = x; tMy = y;
        if (tMvPend) return;
        long wait = 12 - (SystemClock.uptimeMillis() - tMvAt);
        if (wait <= 0) tMvSend.run(); else { tMvPend = true; postDelayed(tMvSend, wait); }
    }

    private void tClick(int button, float x, float y) {
        StreamClient c = client; if (c == null) return;
        c.mouse(0, 0, x, y); c.mouse(1, button, x, y); c.mouse(2, button, x, y);
    }

    /** Đơn vị lăn chuột cho 1 điểm ảnh ngón tay: 120 (1 nấc) ≈ 100 điểm ảnh máy PC → trang đi đúng theo ngón (kể cả lúc phóng to hình). */
    private float wheelK() { return 1.25f * Math.max(1, vidW) / Math.max(1f, vW); }

    private void tWheel(float dv, float dh) {                 // cộng dồn, đủ ~1/10 nấc mới gửi (đỡ dồn gói)
        tAccV += dv; tAccH += dh;
        int v = (int) tAccV, h = (int) tAccH;
        if (Math.abs(v) < 12) v = 0;
        if (Math.abs(h) < 12) h = 0;
        if (v == 0 && h == 0) return;
        v = Math.max(-30000, Math.min(30000, v)); h = Math.max(-30000, Math.min(30000, h));
        tAccV -= v; tAccH -= h;
        StreamClient c = client; if (c != null) c.scroll(tNx, tNy, h, v);
        final Mirror mr = mirror; if (mr != null) mr.scroll(tNx, tNy, h, v);
    }

    private void tScroll(float dx, float dy) {                // ngón đi xuống → trang đi xuống theo ngón (lăn lên) · ngón sang phải → trang sang phải
        if (tAxis == 1) dx = 0; else if (tAxis == 2) dy = 0;
        float k = wheelK();
        tWheel(dy * k, -dx * k);
    }

    private static int axisOf(float ax, float ay) { return ay > ax * 1.3f ? 1 : ax > ay * 1.3f ? 2 : 3; }

    private final Runnable tFling = new Runnable() {          // vuốt nhanh rồi nhấc ngón → trang trôi tiếp, chậm dần (~1 giây)
        @Override public void run() {
            if (tSt != T_NONE && tSt != T_SKIP) return;               // ngón mới chạm xuống → dừng trớn (2 ngón: ngón cuối chưa nhấc vẫn trôi)
            long now = SystemClock.uptimeMillis();
            float dt = Math.max(0.004f, Math.min(0.05f, (now - flT) / 1000f));
            flT = now;
            tWheel(flV * dt, flH * dt);
            float f = (float) Math.pow(0.004, dt);
            flV *= f; flH *= f;
            if (Math.abs(flV) + Math.abs(flH) > 100) postOnAnimation(this);
        }
    };

    private void tFlingStart() {
        if (tVt == null) return;
        tVt.computeCurrentVelocity(1000);
        float vx = tAxis == 1 ? 0 : tVt.getXVelocity(), vy = tAxis == 2 ? 0 : tVt.getYVelocity(), min = dp(160);
        if (Math.abs(vx) < min) vx = 0;
        if (Math.abs(vy) < min) vy = 0;
        if (vx == 0 && vy == 0) return;
        float k = wheelK();
        flV = vy * k; flH = -vx * k; flT = SystemClock.uptimeMillis();
        postOnAnimation(tFling);
    }

    /** Huỷ cử chỉ đang dở (đổi kiểu chạm, bắt đầu phóng to hình, hệ thống huỷ chạm): đang giữ chuột trái thì nhả ra. */
    private void tCancel() {
        removeCallbacks(tLong); removeCallbacks(tFling); removeCallbacks(tMvSend); tMvPend = false;
        if (tSt == T_DRAG) { StreamClient c = client; if (c != null) c.mouse(2, 0, tMx, tMy); }
        tSt = T_NONE; flV = flH = 0; tAccV = tAccH = 0;
    }

    private boolean pcTouch(MotionEvent e) {
        StreamClient c = client;
        int act = e.getActionMasked();
        long now = SystemClock.uptimeMillis();
        float slop = dp(9);
        if (tVt == null) tVt = VelocityTracker.obtain();
        switch (act) {
            case MotionEvent.ACTION_DOWN: {
                removeCallbacks(tFling); flV = flH = 0;               // chạm vào trang đang trôi → dừng ngay (như điện thoại)
                float x = e.getX() - vX, y = e.getY() - vY;
                if (vW <= 0 || vH <= 0 || x < 0 || y < 0 || x > vW || y > vH) { tSt = T_SKIP; return true; }   // chạm viền đen → bỏ
                if (events != null) events.onTouchDown();
                tVt.clear(); tVt.addMovement(e);
                tSt = T_PEND; tAxis = 0; tAccV = tAccH = 0;
                tDx = tLx = e.getX(); tDy = tLy = e.getY(); tDownT = now;
                tNx = x / vW; tNy = y / vH; tMx = tNx; tMy = tNy;
                postDelayed(tLong, T_LONG_MS);
                break;
            }
            case MotionEvent.ACTION_POINTER_DOWN: {
                removeCallbacks(tLong);
                if (tSt == T_DRAG) { removeCallbacks(tMvSend); tMvPend = false; if (c != null) c.mouse(2, 0, tMx, tMy); }   // đang kéo mà thêm ngón → thả
                if (tSt == T_SKIP || tSt == T_NONE || tSt == T_TWO) break;
                if (e.getPointerCount() == 2) {
                    spread(e, -1, sp);
                    tSt = T_TWO; tTwoMoved = false; tAxis = 0; tAccV = tAccH = 0;
                    tCx = tC0x = sp[0]; tCy = tC0y = sp[1];
                    tVt.clear();
                } else tSt = T_SKIP;
                break;
            }
            case MotionEvent.ACTION_MOVE: {
                if (tSt == T_SKIP || tSt == T_NONE) break;
                tVt.addMovement(e);
                if (tSt == T_TWO) {
                    spread(e, -1, sp);
                    float dx = sp[0] - tCx, dy = sp[1] - tCy;
                    tCx = sp[0]; tCy = sp[1];
                    if (!tTwoMoved) {
                        float ax = Math.abs(sp[0] - tC0x), ay = Math.abs(sp[1] - tC0y);
                        if (Math.hypot(ax, ay) <= slop) break;
                        tTwoMoved = true; tAxis = axisOf(ax, ay);
                    }
                    tScroll(dx, dy);
                    break;
                }
                float x = e.getX(), y = e.getY(), dx = x - tLx, dy = y - tLy;
                if (tSt == T_PEND) {
                    float ax = Math.abs(x - tDx), ay = Math.abs(y - tDy);
                    if (Math.hypot(ax, ay) <= slop) break;
                    removeCallbacks(tLong);
                    tSt = T_SCROLL; tAxis = axisOf(ax, ay);
                    tLx = x; tLy = y;                                   // cuộn tính từ chỗ vừa vượt ngưỡng → không giật
                    break;
                }
                tLx = x; tLy = y;
                if (tSt == T_SCROLL) tScroll(dx, dy);
                else if (tSt == T_ARMED) {
                    if (Math.hypot(x - tDx, y - tDy) > slop) {
                        tSt = T_DRAG;
                        if (c != null) { c.mouse(0, 0, tNx, tNy); c.mouse(1, 0, tNx, tNy); }   // nhấn chuột trái ĐÚNG chỗ đã giữ rồi kéo
                        tMove(nx(x), ny(y));
                    }
                } else if (tSt == T_DRAG) tMove(nx(x), ny(y));
                break;
            }
            case MotionEvent.ACTION_POINTER_UP: {
                if (tSt == T_TWO) {
                    if (!tTwoMoved && now - tDownT < 450) tClick(1, tNx, tNy);       // 2 ngón chạm nhanh = bấm phải
                    else if (tTwoMoved) tFlingStart();
                    tSt = T_SKIP;                                       // ngón còn lại: bỏ qua tới khi nhấc hết
                }
                break;
            }
            case MotionEvent.ACTION_UP: {
                removeCallbacks(tLong);
                if (tSt != T_SKIP && tSt != T_NONE) tVt.addMovement(e);
                switch (tSt) {
                    case T_PEND: {                                      // chạm nhanh = bấm trái · lần 2 gần chỗ cũ, trong 0,35 giây = bấm đúp ĐÚNG chỗ cũ
                        float x = tNx, y = tNy;
                        if (now - tTapT < T_DBL_MS && Math.hypot((x - tTapNx) * vW, (y - tTapNy) * vH) < dp(30)) { x = tTapNx; y = tTapNy; }
                        tClick(0, x, y);
                        tTapT = now; tTapNx = x; tTapNy = y;
                        break;
                    }
                    case T_ARMED: tClick(1, tNx, tNy); tTapT = 0; break;                  // giữ yên rồi nhả = bấm phải
                    case T_DRAG: {
                        removeCallbacks(tMvSend); tMvPend = false;
                        if (c != null) c.mouse(2, 0, nx(e.getX()), ny(e.getY()));
                        tTapT = 0;
                        break;
                    }
                    case T_SCROLL: tTapT = 0; tSt = T_NONE; tFlingStart(); break;
                    default: break;
                }
                tSt = T_NONE;
                break;
            }
            case MotionEvent.ACTION_CANCEL: tCancel(); break;
            default: break;
        }
        return true;
    }

    // ---- bàn di chuột: kéo 1 ngón = di con trỏ · chạm = bấm trái · chạm 2 lần rồi giữ kéo = kéo thả · giữ yên = bấm phải
    //      2 ngón chạm = bấm phải · 2 ngón kéo = cuộn
    private final Runnable longPress = () -> {
        if (pTwo || pDrag || pMoved > dp(10)) return;
        pLong = true;
        click(1);
        performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS);
    };

    private void click(int button) {
        StreamClient c = client; if (c == null) return;
        c.mouse(0, 0, curX, curY); c.mouse(1, button, curX, curY); c.mouse(2, button, curX, curY);
    }

    private final Runnable mvSend = () -> { mvPend = false; mvAt = SystemClock.uptimeMillis(); StreamClient c = client; if (c != null) c.mouse(0, 0, curX, curY); };

    private void moveTo() {
        placeCursor();
        if (mvPend) return;
        long wait = 12 - (SystemClock.uptimeMillis() - mvAt);
        if (wait <= 0) mvSend.run(); else { mvPend = true; postDelayed(mvSend, wait); }
    }

    private boolean padTouch(MotionEvent e) {
        StreamClient c = client;
        int act = e.getActionMasked();
        long now = SystemClock.uptimeMillis();
        switch (act) {
            case MotionEvent.ACTION_DOWN: {
                if (events != null) events.onTouchDown();
                pDownT = now; pDownX = pLastX = e.getX(); pDownY = pLastY = e.getY(); pMoved = 0; pTwo = false; pTwoMoved = false; pLong = false;
                if (now - pLastTapT < 300) { pDrag = true; if (c != null) { c.mouse(0, 0, curX, curY); c.mouse(1, 0, curX, curY); } }   // chạm 2 lần rồi giữ → kéo thả
                else { pDrag = false; postDelayed(longPress, 550); }
                break;
            }
            case MotionEvent.ACTION_POINTER_DOWN: {
                removeCallbacks(longPress);
                if (e.getPointerCount() == 2 && !pDrag) { pTwo = true; pTwoMoved = false; spread(e, -1, sp); pLastX = sp[0]; pLastY = sp[1]; sAcc = 0; }
                break;
            }
            case MotionEvent.ACTION_MOVE: {
                if (pTwo) {
                    spread(e, -1, sp);
                    float dy = sp[1] - pLastY, dx = sp[0] - pLastX;
                    pLastX = sp[0]; pLastY = sp[1];
                    if (Math.abs(dx) + Math.abs(dy) > 0) pTwoMoved |= Math.hypot(sp[0] - pDownX, sp[1] - pDownY) > dp(12);
                    sAcc += dy;
                    float step = dp(18);
                    while (Math.abs(sAcc) >= step && c != null) {             // ngón đi xuống → trang đi xuống theo ngón (như điện thoại)
                        c.scroll(curX, curY, 0, sAcc > 0 ? 120 : -120);
                        sAcc += sAcc > 0 ? -step : step;
                    }
                    break;
                }
                float dx = e.getX() - pLastX, dy = e.getY() - pLastY;
                pLastX = e.getX(); pLastY = e.getY();
                pMoved += Math.abs(dx) + Math.abs(dy);
                if (pMoved > dp(10)) removeCallbacks(longPress);
                float v = (float) Math.hypot(dx, dy), k = 1f + Math.min(2.2f, v / dp(6)) * .55f;      // ngón đi nhanh → con trỏ đi xa hơn
                float base = Math.max(1, Math.min(picW, picH * 16 / 9f));
                curX = Math.max(0f, Math.min(1f, curX + dx * k * 1.15f / base));
                curY = Math.max(0f, Math.min(1f, curY + dy * k * 1.15f / (base * (vidH / (float) Math.max(1, vidW)))));
                moveTo();
                break;
            }
            case MotionEvent.ACTION_POINTER_UP: {
                if (pTwo && e.getPointerCount() == 2) {
                    if (!pTwoMoved && now - pDownT < 400) click(1);          // 2 ngón chạm nhanh = bấm phải
                    pTwo = false;
                    int keep = e.getActionIndex() == 0 ? 1 : 0;
                    pLastX = e.getX(keep); pLastY = e.getY(keep); pMoved = dp(20);   // ngón còn lại kéo tiếp chỉ di con trỏ, không thành bấm
                }
                break;
            }
            case MotionEvent.ACTION_UP: {
                removeCallbacks(longPress);
                if (pDrag) { if (c != null) c.mouse(2, 0, curX, curY); pDrag = false; pLastTapT = 0; }
                else if (!pTwo && !pLong && pMoved <= dp(10) && now - pDownT < 300) { click(0); pLastTapT = now; }
                pTwo = false;
                break;
            }
            case MotionEvent.ACTION_CANCEL: {
                removeCallbacks(longPress);
                if (pDrag && c != null) c.mouse(2, 0, curX, curY);
                pDrag = false; pTwo = false;
                break;
            }
            default: break;
        }
        return true;
    }

    private void placeCursor() {
        Cursor cu = cursor; if (cu == null || cu.getVisibility() != VISIBLE) return;
        int x = vX + Math.round(curX * vW), y = vY + Math.round(curY * vH);
        cu.layout(x - cu.hx, y - cu.hy, x - cu.hx + cu.w, y - cu.hy + cu.h);
    }

    /** Mũi tên chuột vẽ tại chỗ (trắng viền đen). */
    private static final class Cursor extends View {
        final int w, h, hx, hy;
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG), line = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        Cursor(android.content.Context c) {
            super(c);
            float d = c.getResources().getDisplayMetrics().density;
            w = Math.round(18 * d); h = Math.round(26 * d); hx = Math.round(2 * d); hy = Math.round(2 * d);
            fill.setColor(Color.WHITE); fill.setStyle(Paint.Style.FILL);
            line.setColor(Color.BLACK); line.setStyle(Paint.Style.STROKE); line.setStrokeWidth(1.6f * d); line.setStrokeJoin(Paint.Join.ROUND);
            float u = d;
            path.moveTo(2 * u, 2 * u); path.lineTo(2 * u, 21 * u); path.lineTo(7 * u, 16.5f * u); path.lineTo(10.5f * u, 24 * u);
            path.lineTo(13.5f * u, 22.6f * u); path.lineTo(10.2f * u, 15.4f * u); path.lineTo(16.5f * u, 15 * u); path.close();
            setElevation(6 * d);
        }
        @Override protected void onDraw(Canvas cv) { cv.drawPath(path, fill); cv.drawPath(path, line); }
    }

    /** Lăn chuột (máy tính bảng / DeX / Chromebook). */
    @Override public boolean onGenericMotionEvent(MotionEvent e) {
        if (!preview && (e.getSource() & InputDevice.SOURCE_CLASS_POINTER) != 0 && e.getActionMasked() == MotionEvent.ACTION_SCROLL) {
            StreamClient c = client;
            float x = e.getX() - vX, y = e.getY() - vY;
            if (c != null && vW > 0 && vH > 0 && x >= 0 && y >= 0 && x <= vW && y <= vH) {
                int v = Math.round(e.getAxisValue(MotionEvent.AXIS_VSCROLL) * 120f);
                int hh = Math.round(e.getAxisValue(MotionEvent.AXIS_HSCROLL) * 120f);
                if (v != 0 || hh != 0) {
                    c.scroll(x / vW, y / vH, hh, v);
                    final Mirror mr = mirror;
                    if (mr != null) mr.scroll(x / vW, y / vH, hh, v);
                }
            }
            return true;
        }
        return super.onGenericMotionEvent(e);
    }

    // ================================================================ Surface

    @Override public void surfaceCreated(SurfaceHolder holder) {
        final Surface s = holder.getSurface();
        dec.post(() -> {
            surface = s;
            releaseCodec();
            wantKey = true;
            parked = false;
            askKey();                                                    // đang xem dở → xin khung khoá để vẽ lại ngay
        });
    }

    @Override public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) { }

    @Override public void surfaceDestroyed(SurfaceHolder holder) {
        // bộ giải mã phải thôi vẽ vào Surface trước khi hàm này trả về
        final CountDownLatch done = new CountDownLatch(1);
        boolean posted = dec.post(() -> {
            surface = null;
            releaseCodec();
            wantKey = true;
            done.countDown();
        });
        if (!posted) return;
        try { done.await(1500, TimeUnit.MILLISECONDS); } catch (InterruptedException ignored) { }
    }

    // ================================================================ StreamClient.VideoSink (luồng mạng → chuyển sang luồng giải mã)

    @Override public void onVideoFormat(int w, int h) {
        main.post(() -> {
            setVideoSize(w, h);
            Events e = events;
            if (e != null && !released) e.onVideoSize(w, h);
        });
        dec.post(() -> {
            fmtW = w;
            fmtH = h;
            sps = null;
            pps = null;
            releaseCodec();                                              // kích thước đổi / phiên mới → dựng lại ở khung khoá tới
            wantKey = true;
        });
    }

    @Override public void onVideoFrame(byte[] buf, int off, int len, boolean keyframe) {
        dec.post(() -> frame(buf, off, len, keyframe));
    }

    // ================================================================ giải mã (luồng BRS-decode)

    private void resetStream() {
        releaseCodec();
        sps = null;
        pps = null;
        wantKey = true;
    }

    private void frame(byte[] b, int off, int len, boolean key) {
        if (released || client == null) return;                          // đã tách client (khung đến muộn sau khi tắt) → bỏ, không dựng lại bộ giải mã
        if (key) {
            byte[][] ps = paramSets(b, off, len);
            if (ps[0] != null && ps[1] != null) {
                if (codec != null && (!Arrays.equals(ps[0], sps) || !Arrays.equals(ps[1], pps))) releaseCodec();   // tham số nén đổi → dựng lại
                sps = ps[0];
                pps = ps[1];
            }
            if (codec == null) {
                if (parked || surface == null || !surface.isValid()) { wantKey = true; return; }   // chưa có chỗ vẽ: có Surface sẽ tự xin khung khoá
                if (sps == null || pps == null) { wantKey = true; askKey(); return; }
                if (!configure()) { wantKey = true; askKey(); return; }
            }
            wantKey = false;
        }
        if (wantKey || codec == null) return;                            // bỏ khung cho tới khung khoá
        if (len > maxIn) {                                               // khung to hơn ô nhập → dựng lại với ô to hơn
            maxIn = Math.min(16 << 20, len + (len >> 1));
            releaseCodec();
            wantKey = true;
            askKey();
            return;
        }
        if (pend.size() > 30) { fail(); return; }                        // bộ giải mã không theo kịp → làm lại từ khung khoá
        pend.addLast(new Frame(b, off, len));
        feed();
    }

    private boolean configure() {
        releaseCodec();
        int w = fmtW > 0 ? fmtW : Math.max(16, vidW), h = fmtH > 0 ? fmtH : Math.max(16, vidH);
        maxIn = Math.max(maxIn, Math.min(16 << 20, w * h * 3 / 2 + 4096));
        // lần 0: phần cứng + chế độ ít trễ · lần 1: phần cứng, cấu hình gốc · lần 2: giải mã phần mềm (máy lỗi phần cứng)
        for (int attempt = fails >= 3 ? 2 : 0; attempt < 3; attempt++) {
            MediaCodec c = null;
            try {
                c = attempt < 2 ? MediaCodec.createDecoderByType(MIME) : software();
                if (c == null) continue;
                MediaFormat f = MediaFormat.createVideoFormat(MIME, w, h);
                f.setByteBuffer("csd-0", ByteBuffer.wrap(sps));
                f.setByteBuffer("csd-1", ByteBuffer.wrap(pps));
                f.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, maxIn);
                if (attempt != 1) lowLatency(f, c);
                final int g = ++gen;
                inputs.clear();
                pend.clear();
                c.setCallback(new Cb(g), dec);                           // phải đặt trước configure()
                c.configure(f, surface, null, 0);
                c.start();
                codec = c;
                shown = false;
                return true;
            } catch (Exception e) {
                if (c != null) stopCodec(c);
            }
        }
        return false;
    }

    /** Chế độ ít trễ: KEY_PRIORITY 0 (thời gian thực), KEY_LOW_LATENCY (Android 11+), khoá riêng của hãng chip cho máy cũ. */
    private static void lowLatency(MediaFormat f, MediaCodec c) {
        if (Build.VERSION.SDK_INT >= 23) f.setInteger(MediaFormat.KEY_PRIORITY, 0);
        boolean native11 = false;
        if (Build.VERSION.SDK_INT >= 30) {
            f.setInteger(MediaFormat.KEY_LOW_LATENCY, 1);
            try {
                native11 = c.getCodecInfo().getCapabilitiesForType(MIME).isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency);
            } catch (Exception ignored) { }
        }
        if (native11 || Build.VERSION.SDK_INT < 26) return;
        String n = String.valueOf(c.getName()).toLowerCase(Locale.ROOT);
        if (n.startsWith("omx.qcom") || n.startsWith("c2.qti")) {
            f.setInteger("vendor.qti-ext-dec-picture-order.enable", 1);
            f.setInteger("vendor.qti-ext-dec-low-latency.enable", 1);
        } else if (n.startsWith("omx.hisi") || n.startsWith("c2.hisi")) {
            f.setInteger("vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1);
            f.setInteger("vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-rdy", -1);
        } else if (n.startsWith("omx.exynos") || n.startsWith("c2.exynos")) {
            f.setInteger("vendor.rtc-ext-dec-low-latency.enable", 1);
        } else if (n.startsWith("omx.amlogic") || n.startsWith("c2.amlogic")) {
            f.setInteger("vendor.low-latency.enable", 1);
        }
    }

    private static MediaCodec software() {
        for (String n : new String[]{"c2.android.avc.decoder", "OMX.google.h264.decoder"}) {
            try { return MediaCodec.createByCodecName(n); } catch (Exception ignored) { }
        }
        return null;
    }

    private void feed() {
        MediaCodec c = codec;
        while (c != null && !pend.isEmpty() && !inputs.isEmpty()) {
            Frame f = pend.pollFirst();
            int idx = inputs.pollFirst();
            try {
                ByteBuffer ib = c.getInputBuffer(idx);
                if (ib == null) { fail(); return; }
                ((java.nio.Buffer) ib).clear();
                if (ib.remaining() < f.len) { maxIn = Math.min(16 << 20, f.len + (f.len >> 1)); fail(); return; }
                ib.put(f.b, f.off, f.len);
                long t = System.nanoTime() / 1000;
                if (t <= lastPts) t = lastPts + 1;
                lastPts = t;
                c.queueInputBuffer(idx, 0, f.len, t, 0);
            } catch (Exception e) {
                fail();
                return;
            }
        }
    }

    private final class Cb extends MediaCodec.Callback {
        private final int g;
        Cb(int g) { this.g = g; }

        @Override public void onInputBufferAvailable(MediaCodec mc, int index) {
            if (g != gen || mc != codec) return;
            inputs.addLast(index);
            feed();
        }

        @Override public void onOutputBufferAvailable(MediaCodec mc, int index, MediaCodec.BufferInfo info) {
            if (g != gen || mc != codec) return;
            try { mc.releaseOutputBuffer(index, true); }                 // hiện ngay
            catch (Exception e) { fail(); return; }
            if (++okFrames > 300) fails = 0;
            if (!shown) {
                shown = true;
                final int g0 = g;
                main.post(() -> { if (g0 == gen) firstFrame(); });       // bộ giải mã này đã bị bỏ (ô vừa chuyển chỗ…) → báo cũ, bỏ qua
            }
        }

        @Override public void onError(MediaCodec mc, MediaCodec.CodecException e) {
            if (g != gen || mc != codec) return;
            fail();
        }

        @Override public void onOutputFormatChanged(MediaCodec mc, MediaFormat format) { }
    }

    private void firstFrame() {
        Events e = events;
        if (e != null && !released) e.onFirstFrame();
    }

    /** Bộ giải mã lỗi: bỏ nó (giải phóng ở lượt sau, không làm ngay trong callback), dựng lại ở khung khoá tới + xin khung khoá. */
    private void fail() {
        final MediaCodec c = codec;
        codec = null;
        gen++;
        inputs.clear();
        pend.clear();
        wantKey = true;
        fails++;
        okFrames = 0;
        if (c != null) dec.post(() -> stopCodec(c));
        askKey();
    }

    private void releaseCodec() {
        MediaCodec c = codec;
        codec = null;
        gen++;
        inputs.clear();
        pend.clear();
        if (c != null) stopCodec(c);
    }

    private static void stopCodec(MediaCodec c) {
        try { c.stop(); } catch (Exception ignored) { }
        try { c.release(); } catch (Exception ignored) { }
    }

    private void askKey() {
        StreamClient c = client;
        if (c != null) c.requestKeyframe();
    }

    // ================================================================ tách SPS / PPS (Annex-B)

    /** SPS (NAL 7) và PPS (NAL 8) đầu tiên trong 1 AU, kèm mã đầu 00 00 00 01 (dùng làm csd-0 / csd-1). */
    private static byte[][] paramSets(byte[] b, int off, int len) {
        byte[] s = null, p = null;
        int end = off + len;
        int i = nextStart(b, off, end);
        while (i >= 0 && i < end) {
            int nx = nextStart(b, i, end);
            int e = nx < 0 ? end : nx - 3;
            while (e > i && b[e - 1] == 0) e--;                          // bỏ số 0 của mã đầu 4 byte phía sau
            int t = b[i] & 0x1F;
            if (t == 7 && s == null) s = nal(b, i, e);
            else if (t == 8 && p == null) p = nal(b, i, e);
            if ((s != null && p != null) || t == 1 || t == 5) break;    // đủ rồi / tới phần hình
            i = nx;
        }
        return new byte[][]{s, p};
    }

    /** Vị trí ngay sau mã đầu 00 00 01 kế tiếp, −1 nếu hết. */
    private static int nextStart(byte[] b, int from, int end) {
        for (int i = from; i + 2 < end; i++) {
            if (b[i] == 0 && b[i + 1] == 0 && b[i + 2] == 1) return i + 3;
        }
        return -1;
    }

    private static byte[] nal(byte[] b, int s, int e) {
        byte[] r = new byte[4 + (e - s)];
        r[3] = 1;
        System.arraycopy(b, s, r, 4, e - s);
        return r;
    }

    private static final class Frame {
        final byte[] b;
        final int off, len;
        Frame(byte[] b, int off, int len) { this.b = b; this.off = off; this.len = len; }
    }
}
