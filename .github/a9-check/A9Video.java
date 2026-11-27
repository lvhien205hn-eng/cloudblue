package com.cloudblue;

import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.media.Image;
import android.media.ImageReader;
import android.media.MediaCodec;
import android.media.MediaFormat;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.view.Surface;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * CloudBlue cbvideo (27/11f) — máy chủ HÌNH riêng cho Android 9 (LDPlayer 9). Thay phần hình của scrcpy-server 2.4, CÙNG giao thức
 * (byte 0 · "h264" + rộng + cao · mỗi gói: 8 byte pts|cờ + 4 byte độ dài + dữ liệu) nên bluestream đọc y như scrcpy.
 *
 * Vì sao: Android 9 đưa hình vào bộ nén OMX.google.h264.encoder qua "bề mặt" → bộ nén tự đọc ngược hình từ GPU NGAY trong luồng mã hoá
 * (đo CI simpleperf: ~70% thời gian luồng nén nằm ở ống goldfish, mã hoá thật ~3%) → chỉ ~15 khung/giây dù hình nhỏ cỡ nào.
 * Ở đây: màn ảo → ImageReader (RGBA) đọc TRONG tiến trình này → đổi sang NV12 → nạp bộ nén bằng ByteBuffer. Đọc hình và mã hoá
 * chạy song song (2 tiến trình), không chờ nhau.
 *
 * Thêm: bluestream gửi 1 byte 'K' → khung IDR ngay (Android 9 không tự ra khung khoá định kỳ dùng được → trước phải bật lại bộ nén).
 * Màn đứng yên: nén lại khung cuối thêm vài lần (nét dần, như scrcpy lặp khung) rồi thôi.
 *
 * Chạy: CLASSPATH=/data/local/tmp/cbvideo.jar app_process / com.cloudblue.A9Video scid=… max_size=… max_fps=… video_bit_rate=… i_frame=… [stats=giây]
 */
public final class A9Video {
    static String scid = "0";
    static int maxSize = 0, bitRate = 3000000, statsS = 0;
    static float maxFps = 0, iFrame = 5f;
    static volatile boolean stop = false;
    static volatile MediaCodec cur;
    static OutputStream out;
    static final Object LOCK = new Object();

    public static void main(String[] args) {
        for (String a : args) {
            int i = a.indexOf('=');
            if (i <= 0) continue;
            String k = a.substring(0, i), v = a.substring(i + 1);
            try {
                if (k.equals("scid")) scid = v;
                else if (k.equals("max_size")) maxSize = Integer.parseInt(v);
                else if (k.equals("max_fps")) maxFps = Float.parseFloat(v);
                else if (k.equals("video_bit_rate")) bitRate = Integer.parseInt(v);
                else if (k.equals("i_frame")) iFrame = Float.parseFloat(v);
                else if (k.equals("stats")) statsS = Integer.parseInt(v);
            } catch (NumberFormatException e) {
                System.err.println("cbvideo: bad arg " + a);
            }
        }
        int code = 0;
        try {
            run();
        } catch (Throwable t) {
            System.err.println("cbvideo error: " + t);
            t.printStackTrace();
            code = 1;
        }
        System.exit(code);
    }

    static void run() throws Exception {
        LocalServerSocket ss = new LocalServerSocket("scrcpy_" + scid);
        LocalSocket s;
        try {
            s = ss.accept();
        } finally {
            ss.close();
        }
        out = s.getOutputStream();
        final InputStream in = s.getInputStream();
        synchronized (LOCK) { out.write(0); }
        Thread cmd = new Thread(new Runnable() {
            public void run() {
                try {
                    int c;
                    while (!stop && (c = in.read()) >= 0) {
                        if (c == 'K') {
                            MediaCodec m = cur;
                            if (m != null) {
                                Bundle b = new Bundle();
                                b.putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0);
                                try { m.setParameters(b); } catch (Exception e) { /* bộ nén đang bật lại */ }
                            }
                        }
                    }
                } catch (Exception e) { /* socket đóng */ }
                stop = true;
            }
        }, "cb-cmd");
        cmd.setDaemon(true);
        cmd.start();
        HandlerThread ht = new HandlerThread("cb-img");
        ht.start();
        Handler h = new Handler(ht.getLooper());
        boolean meta = false;
        int fails = 0;
        while (!stop) {
            Disp d = Disp.get();
            int[] vs = videoSize(d.w, d.h, maxSize);
            if (!meta) {
                ByteBuffer hb = ByteBuffer.allocate(12);
                hb.putInt(0x68323634).putInt(vs[0]).putInt(vs[1]);
                synchronized (LOCK) { out.write(hb.array()); }
                meta = true;
            }
            Cap c = new Cap(d, vs[0], vs[1], h);
            try {
                c.start();
                long t0 = System.nanoTime();
                while (!stop && !c.dead) {
                    Thread.sleep(250);
                    Disp d2 = Disp.get();
                    if (d2.w != d.w || d2.h != d.h || d2.layerStack != d.layerStack) break;     // xoay màn hình → bật lại cỡ mới
                    if (System.nanoTime() - t0 > 5000000000L) fails = 0;
                }
                if (c.dead) {
                    fails++;
                    if (fails >= 3) throw new IOException("encoder keeps failing");
                }
            } finally {
                c.stop();
            }
        }
    }

    static int[] videoSize(int w, int h, int max) {        // y hệt scrcpy 2.4 (ScreenInfo.computeVideoSize)
        w &= ~7;
        h &= ~7;
        if (max > 0) {
            boolean portrait = h > w;
            int major = portrait ? h : w, minor = portrait ? w : h;
            if (major > max) {
                int me = minor * max / major;
                minor = (me + 4) & ~7;
                major = max;
            }
            w = portrait ? minor : major;
            h = portrait ? major : minor;
        }
        return new int[]{w, h};
    }

    static final class Disp {
        int w, h, layerStack;
        static Object dmg;
        static Method gi;

        static Disp get() throws Exception {
            if (dmg == null) {
                Class<?> g = Class.forName("android.hardware.display.DisplayManagerGlobal");
                dmg = g.getMethod("getInstance").invoke(null);
                gi = g.getMethod("getDisplayInfo", int.class);
            }
            Object info = gi.invoke(dmg, 0);
            Class<?> c = info.getClass();
            Disp d = new Disp();
            d.w = c.getField("logicalWidth").getInt(info);
            d.h = c.getField("logicalHeight").getInt(info);
            d.layerStack = c.getField("layerStack").getInt(info);
            return d;
        }
    }

    static final class SC {
        static Class<?> k() throws Exception { return Class.forName("android.view.SurfaceControl"); }

        static IBinder create() throws Exception {
            return (IBinder) k().getMethod("createDisplay", String.class, boolean.class).invoke(null, "cbvideo", Build.VERSION.SDK_INT < 30);
        }

        static void setSurface(IBinder t, Surface s, Rect dev, Rect dst, int ls) throws Exception {
            Class<?> c = k();
            c.getMethod("openTransaction").invoke(null);
            try {
                c.getMethod("setDisplaySurface", IBinder.class, Surface.class).invoke(null, t, s);
                c.getMethod("setDisplayProjection", IBinder.class, int.class, Rect.class, Rect.class).invoke(null, t, 0, dev, dst);
                c.getMethod("setDisplayLayerStack", IBinder.class, int.class).invoke(null, t, ls);
            } finally {
                c.getMethod("closeTransaction").invoke(null);
            }
        }

        static void destroy(IBinder t) throws Exception { k().getMethod("destroyDisplay", IBinder.class).invoke(null, t); }
    }

    /** 1 lần quay: màn ảo → ImageReader → (luồng cb-img) đổi màu + nạp bộ nén · (luồng cb-drain) lấy gói H.264 → socket. */
    static final class Cap implements ImageReader.OnImageAvailableListener, Runnable {
        final Disp d;
        final int vw, vh;
        final Handler h;
        final long minNs;
        ImageReader rd;
        MediaCodec mc;
        IBinder disp;
        Thread drain;
        volatile boolean dead, stopped;
        Image pending;
        boolean posted;
        long lastNs, lastPts;
        int[] px;
        byte[] yuv;
        int fmt, rep;
        // thống kê (stats=giây)
        long stT = System.nanoTime(), stRead, stConv;
        int stIn, stSub, stRep, stOut;

        Cap(Disp d, int vw, int vh, Handler h) {
            this.d = d; this.vw = vw; this.vh = vh; this.h = h;
            minNs = maxFps > 0 ? (long) (1e9 / maxFps) : 0;
        }

        void start() throws Exception {
            mc = MediaCodec.createEncoderByType("video/avc");
            fmt = pickFormat(mc);
            MediaFormat f = MediaFormat.createVideoFormat("video/avc", vw, vh);
            f.setInteger(MediaFormat.KEY_BIT_RATE, bitRate);
            f.setInteger(MediaFormat.KEY_FRAME_RATE, maxFps > 0 ? Math.max(1, Math.round(maxFps)) : 30);
            f.setInteger(MediaFormat.KEY_COLOR_FORMAT, fmt);
            if (Build.VERSION.SDK_INT >= 25) f.setFloat(MediaFormat.KEY_I_FRAME_INTERVAL, iFrame);
            else f.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, Math.max(1, Math.round(iFrame)));
            mc.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            mc.start();
            cur = mc;
            yuv = new byte[vw * vh * 3 / 2];
            rd = ImageReader.newInstance(vw, vh, PixelFormat.RGBA_8888, 3);
            rd.setOnImageAvailableListener(this, h);
            drain = new Thread(new Runnable() { public void run() { drainLoop(); } }, "cb-drain");
            drain.start();
            disp = SC.create();
            SC.setSurface(disp, rd.getSurface(), new Rect(0, 0, d.w, d.h), new Rect(0, 0, vw, vh), d.layerStack);
            System.err.println("cbvideo: " + vw + "x" + vh + " fmt " + fmt + " max_fps " + maxFps + " " + mc.getName());
        }

        static int pickFormat(MediaCodec mc) {
            try {
                int[] cf = mc.getCodecInfo().getCapabilitiesForType("video/avc").colorFormats;
                boolean p = false, sp = false;
                for (int x : cf) {
                    if (x == 21) sp = true;
                    if (x == 19) p = true;
                }
                if (sp) return 21;
                if (p) return 19;
                return 0x7F420888;      // YUV420Flexible → ghi qua getInputImage
            } catch (Exception e) {
                return 21;
            }
        }

        public void onImageAvailable(ImageReader r) {
            if (stopped) return;
            Image im = null;
            try { im = r.acquireLatestImage(); } catch (Exception e) { /* đã giữ đủ ảnh */ }
            if (im != null) {
                stIn++;
                if (pending != null) pending.close();
                pending = im;
            }
            submit();
        }

        private final Runnable refine = new Runnable() {
            public void run() { refineOnce(); }
        };

        public void run() {             // hẹn nạp lại (giới hạn khung/giây hoặc bộ nén chưa rảnh)
            posted = false;
            submit();
        }

        void later(long ns) {
            if (!posted) {
                posted = true;
                h.postDelayed(this, Math.max(1, ns / 1000000L));
            }
        }

        long nextPts(long want) {
            long p = Math.max(want, lastPts + 1);
            lastPts = p;
            return p;
        }

        void submit() {
            if (pending == null || stopped) return;
            long now = System.nanoTime();
            if (minNs > 0 && lastNs != 0) {
                long w = lastNs + minNs - 2000000L - now;
                if (w > 0) { later(w); return; }
            }
            int ix;
            try { ix = mc.dequeueInputBuffer(0); } catch (Exception e) { dead = true; return; }
            if (ix < 0) { later(3000000L); return; }
            Image im = pending;
            pending = null;
            try {
                long t0 = System.nanoTime();
                Image.Plane pl = im.getPlanes()[0];
                IntBuffer ib = pl.getBuffer().order(ByteOrder.LITTLE_ENDIAN).asIntBuffer();      // 1 điểm ảnh = 1 int (R | G<<8 | B<<16 | A<<24)
                int rs = pl.getRowStride() >> 2;
                int need = rs * (vh - 1) + vw;
                if (px == null || px.length < need) px = new int[need];
                ib.position(0);
                ib.get(px, 0, Math.min(need, ib.remaining()));
                long t1 = System.nanoTime();
                toNv12(px, rs, yuv, vw, vh);
                long t2 = System.nanoTime();
                stRead += t1 - t0;
                stConv += t2 - t1;
                queue(ix, nextPts(im.getTimestamp() / 1000L));
                lastNs = now;
                stSub++;
                rep = 0;
                h.removeCallbacks(refine);
                h.postDelayed(refine, 150);
            } catch (Exception e) {
                System.err.println("cbvideo: feed error " + e);
                dead = true;
            } finally {
                im.close();
            }
            stats();
        }

        void refineOnce() {              // màn đứng yên: nén lại khung cuối (P nét dần) tối đa 3 lần, mỗi 150 ms
            if (stopped || pending != null || rep >= 3 || lastNs == 0) return;
            int ix;
            try { ix = mc.dequeueInputBuffer(0); } catch (Exception e) { return; }
            if (ix < 0) { h.postDelayed(refine, 20); return; }
            try {
                queue(ix, nextPts(System.nanoTime() / 1000L));
                rep++;
                stRep++;
                if (rep < 3) h.postDelayed(refine, 150);
            } catch (Exception e) {
                dead = true;
            }
        }

        void queue(int ix, long pts) {
            int n = vw * vh * 3 / 2;
            if (fmt == 0x7F420888) {
                Image ii = mc.getInputImage(ix);
                Image.Plane[] p = ii.getPlanes();
                ByteBuffer yb = p[0].getBuffer();
                int yrs = p[0].getRowStride();
                for (int r = 0; r < vh; r++) { yb.position(r * yrs); yb.put(yuv, r * vw, vw); }
                ByteBuffer ub = p[1].getBuffer(), vb = p[2].getBuffer();
                int urs = p[1].getRowStride(), ups = p[1].getPixelStride(), vrs = p[2].getRowStride(), vps = p[2].getPixelStride();
                int uv = vw * vh;
                for (int r = 0; r < vh / 2; r++) {
                    int so = uv + r * vw;
                    for (int c = 0; c < vw / 2; c++) {
                        ub.put(r * urs + c * ups, yuv[so + 2 * c]);
                        vb.put(r * vrs + c * vps, yuv[so + 2 * c + 1]);
                    }
                }
            } else {
                ByteBuffer ib = mc.getInputBuffer(ix);
                ib.clear();
                if (fmt == 19) {         // I420: Y rồi U rồi V
                    ib.put(yuv, 0, vw * vh);
                    int uv = vw * vh, q = uv / 4;
                    byte[] u = new byte[q], v = new byte[q];
                    for (int i = 0, j = uv; i < q; i++, j += 2) { u[i] = yuv[j]; v[i] = yuv[j + 1]; }
                    ib.put(u).put(v);
                } else {
                    ib.put(yuv, 0, n);
                }
            }
            mc.queueInputBuffer(ix, 0, n, pts, 0);
        }

        /** RGBA (mỗi điểm 1 int, little-endian) → NV12 (BT.601 giới hạn 16–235, như scrcpy) — chroma = trung bình khối 2×2. */
        static void toNv12(int[] s, int rs, byte[] d, int w, int h) {
            int uv = w * h;
            for (int y = 0; y < h; y += 2) {
                int s0 = y * rs, s1 = s0 + rs, d0 = y * w, d1 = d0 + w, du = uv + (y >> 1) * w;
                for (int x = 0; x < w; x += 2) {
                    int p0 = s[s0 + x], p1 = s[s0 + x + 1], p2 = s[s1 + x], p3 = s[s1 + x + 1];
                    int r0 = p0 & 255, g0 = (p0 >> 8) & 255, b0 = (p0 >> 16) & 255;
                    int r1 = p1 & 255, g1 = (p1 >> 8) & 255, b1 = (p1 >> 16) & 255;
                    int r2 = p2 & 255, g2 = (p2 >> 8) & 255, b2 = (p2 >> 16) & 255;
                    int r3 = p3 & 255, g3 = (p3 >> 8) & 255, b3 = (p3 >> 16) & 255;
                    d[d0 + x] = (byte) (((66 * r0 + 129 * g0 + 25 * b0 + 128) >> 8) + 16);
                    d[d0 + x + 1] = (byte) (((66 * r1 + 129 * g1 + 25 * b1 + 128) >> 8) + 16);
                    d[d1 + x] = (byte) (((66 * r2 + 129 * g2 + 25 * b2 + 128) >> 8) + 16);
                    d[d1 + x + 1] = (byte) (((66 * r3 + 129 * g3 + 25 * b3 + 128) >> 8) + 16);
                    int R = r0 + r1 + r2 + r3, G = g0 + g1 + g2 + g3, B = b0 + b1 + b2 + b3;
                    d[du + x] = (byte) (((-38 * R - 74 * G + 112 * B + 512) >> 10) + 128);
                    d[du + x + 1] = (byte) (((112 * R - 94 * G - 18 * B + 512) >> 10) + 128);
                }
            }
        }

        void stats() {
            if (statsS <= 0) return;
            long now = System.nanoTime();
            if (now - stT < statsS * 1000000000L) return;
            double sec = (now - stT) / 1e9;
            System.err.println(String.format(java.util.Locale.US,
                    "cbvideo stats: %.1fs in %d sub %d rep %d out %d (%.1f fps) read %.1f ms conv %.1f ms",
                    sec, stIn, stSub, stRep, stOut, stOut / sec, stSub > 0 ? stRead / 1e6 / stSub : 0, stSub > 0 ? stConv / 1e6 / stSub : 0));
            stT = now; stIn = 0; stSub = 0; stRep = 0; stOut = 0; stRead = 0; stConv = 0;
        }

        void drainLoop() {
            MediaCodec.BufferInfo bi = new MediaCodec.BufferInfo();
            byte[] pkt = new byte[1 << 16];
            try {
                while (!stopped) {
                    int o = mc.dequeueOutputBuffer(bi, 100000);
                    if (o < 0) continue;
                    try {
                        if (bi.size > 0) {
                            ByteBuffer ob = mc.getOutputBuffer(o);
                            ob.position(bi.offset);
                            ob.limit(bi.offset + bi.size);
                            boolean cfg = (bi.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0;
                            boolean key = (bi.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0;
                            long pf = cfg ? (1L << 63) : ((bi.presentationTimeUs & 0x3FFFFFFFFFFFFFFFL) | (key ? (1L << 62) : 0));
                            int n = 12 + bi.size;
                            if (pkt.length < n) pkt = new byte[Math.max(n, pkt.length * 2)];
                            for (int i = 0; i < 8; i++) pkt[i] = (byte) (pf >>> (56 - 8 * i));
                            pkt[8] = (byte) (bi.size >>> 24);
                            pkt[9] = (byte) (bi.size >>> 16);
                            pkt[10] = (byte) (bi.size >>> 8);
                            pkt[11] = (byte) bi.size;
                            ob.get(pkt, 12, bi.size);
                            synchronized (LOCK) { out.write(pkt, 0, n); }
                            if (!cfg) stOut++;
                        }
                    } finally {
                        mc.releaseOutputBuffer(o, false);
                    }
                }
            } catch (IOException e) {
                stop = true;            // bluestream đóng socket → thoát
            } catch (Exception e) {
                if (!stopped) {
                    System.err.println("cbvideo: drain error " + e);
                    dead = true;
                }
            }
        }

        void stop() {
            stopped = true;
            try { if (rd != null) rd.setOnImageAvailableListener(null, null); } catch (Exception e) { /* */ }
            final CountDownLatch l = new CountDownLatch(1);
            h.post(new Runnable() {
                public void run() {
                    h.removeCallbacks(Cap.this);
                    h.removeCallbacks(refine);
                    if (pending != null) { pending.close(); pending = null; }
                    l.countDown();
                }
            });
            try { l.await(1, TimeUnit.SECONDS); } catch (InterruptedException e) { /* */ }
            try { if (disp != null) SC.destroy(disp); } catch (Exception e) { /* */ }
            try { if (drain != null) drain.join(1000); } catch (Exception e) { /* */ }
            if (cur == mc) cur = null;
            try { if (mc != null) mc.stop(); } catch (Exception e) { /* */ }
            try { if (mc != null) mc.release(); } catch (Exception e) { /* */ }
            try { if (rd != null) rd.close(); } catch (Exception e) { /* */ }
        }
    }
}
