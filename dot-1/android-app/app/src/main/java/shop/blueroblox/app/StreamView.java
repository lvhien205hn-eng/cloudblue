package shop.blueroblox.app;

import android.content.Context;
import android.graphics.Color;
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

    private static final String MIME = "video/avc";

    private final SurfaceView sv;
    private final boolean preview;                // ô xem trước: không nhận chạm (bấm ô = mở màn điều khiển), giải mã ưu tiên thường, ít bộ nhớ
    private final Handler main = new Handler(Looper.getMainLooper());
    private final HandlerThread thread;
    private final Handler dec;
    private volatile StreamClient client;
    private volatile boolean released = false;
    private Events events;

    // ---- luồng giao diện: bố cục + chạm ----
    private int vidW = 9, vidH = 16;
    private int picX, picY, picW, picH;
    private int downMask = 0;
    private final float[] lastX = new float[10], lastY = new float[10];

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
    public StreamView(Context c, boolean preview) {
        super(c);
        this.preview = preview;
        maxIn = preview ? 256 << 10 : 1 << 20;        // hình xem trước ≤ 480: ô nhập nhỏ (nhiều ô cùng lúc đỡ tốn bộ nhớ); khung to hơn tự nới
        setBackgroundColor(Color.BLACK);
        sv = new SurfaceView(c);
        sv.getHolder().addCallback(this);
        addView(sv);
        thread = new HandlerThread(preview ? "BRS-preview" : "BRS-decode");
        thread.start();
        dec = new Handler(thread.getLooper());
        final int prio = preview ? android.os.Process.THREAD_PRIORITY_DEFAULT : android.os.Process.THREAD_PRIORITY_URGENT_DISPLAY;
        dec.post(() -> {
            try { android.os.Process.setThreadPriority(prio); } catch (Throwable ignored) { }
        });
    }

    public void setEvents(Events e) { events = e; }

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
        sv.measure(MeasureSpec.makeMeasureSpec(picW, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(picH, MeasureSpec.EXACTLY));
    }

    @Override protected void onLayout(boolean changed, int l, int t, int r, int b) {
        fit(r - l, b - t);
        sv.layout(picX, picY, picX + picW, picY + picH);
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
        StreamClient c = client;
        int act = e.getActionMasked();
        switch (act) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_POINTER_DOWN: {
                int i = e.getActionIndex(), id = e.getPointerId(i);
                if (id < 0 || id > 9 || picW <= 0 || picH <= 0) break;
                float x = e.getX(i) - picX, y = e.getY(i) - picY;
                if (x < 0 || y < 0 || x > picW || y > picH) break;       // chạm vào viền đen → bỏ qua ngón này
                if (act == MotionEvent.ACTION_DOWN && events != null) events.onTouchDown();
                downMask |= 1 << id;
                lastX[id] = x / picW;
                lastY[id] = y / picH;
                if (c != null) c.touch(StreamClient.TOUCH_DOWN, id, lastX[id], lastY[id]);
                break;
            }
            case MotionEvent.ACTION_MOVE: {
                for (int i = 0; i < e.getPointerCount(); i++) {
                    int id = e.getPointerId(i);
                    if (id < 0 || id > 9 || (downMask & (1 << id)) == 0) continue;
                    lastX[id] = nx(e.getX(i));
                    lastY[id] = ny(e.getY(i));
                    if (c != null) c.touch(StreamClient.TOUCH_MOVE, id, lastX[id], lastY[id]);
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
        for (int id = 0; id < 10; id++) {
            if ((downMask & (1 << id)) != 0 && c != null) c.touch(StreamClient.TOUCH_CANCEL, id, lastX[id], lastY[id]);
        }
        downMask = 0;
    }

    private float nx(float x) { return picW <= 0 ? 0f : Math.max(0f, Math.min(1f, (x - picX) / picW)); }
    private float ny(float y) { return picH <= 0 ? 0f : Math.max(0f, Math.min(1f, (y - picY) / picH)); }

    /** Lăn chuột (máy tính bảng / DeX / Chromebook). */
    @Override public boolean onGenericMotionEvent(MotionEvent e) {
        if (!preview && (e.getSource() & InputDevice.SOURCE_CLASS_POINTER) != 0 && e.getActionMasked() == MotionEvent.ACTION_SCROLL) {
            StreamClient c = client;
            float x = e.getX() - picX, y = e.getY() - picY;
            if (c != null && picW > 0 && picH > 0 && x >= 0 && y >= 0 && x <= picW && y <= picH) {
                int v = Math.round(e.getAxisValue(MotionEvent.AXIS_VSCROLL) * 120f);
                int hh = Math.round(e.getAxisValue(MotionEvent.AXIS_HSCROLL) * 120f);
                if (v != 0 || hh != 0) c.scroll(x / picW, y / picH, hh, v);
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
