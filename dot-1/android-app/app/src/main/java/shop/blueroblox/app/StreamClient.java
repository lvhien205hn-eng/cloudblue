package shop.blueroblox.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SNIServerName;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Phát hình v2 (BRS2 — docs/STREAM-PROTOCOL.md): hỏi máy nằm ở máy chủ nào (cloudphone_endpoint) → nối TLS trực tiếp
 * (LAN trước, rồi IP công khai) hoặc WebSocket qua Cloudflare → HELLO → nhận hình H.264 (đưa thẳng cho bộ giải mã,
 * không qua luồng giao diện) và gửi chạm / phím / chữ về máy.
 *
 * Luồng: "BRS-net" nối + đọc (sống suốt đời client, tự nối lại), "BRS-tx" ghi cho từng phiên (1 hàng đợi, gộp lệnh kéo,
 * PING 2 giây, ACK ~0,1 giây). Mọi lệnh gửi chỉ bỏ vào hàng đợi → không bao giờ chặn luồng giao diện.
 * Listener được gọi trên luồng giao diện; VideoSink được gọi trên luồng mạng.
 */
public final class StreamClient {
    // ---- kiểu tin (xem STREAM-PROTOCOL.md mục 3) ----
    static final int C_HELLO = 0x01, C_TOUCH = 0x10, C_KEY = 0x11, C_TEXT = 0x12, C_SCROLL = 0x13, C_CMD = 0x14, C_PING = 0x15,
            C_QUALITY = 0x16, C_KEYFRAME = 0x17, C_CLIP = 0x18, C_BYE = 0x19, C_ACK = 0x1A;
    static final int S_WELCOME = 0x81, S_VIDEO = 0x82, S_SIZE = 0x83, S_CLIP = 0x84, S_PONG = 0x85, S_ERROR = 0x86, S_STATS = 0x87;

    public static final int TOUCH_DOWN = 0, TOUCH_UP = 1, TOUCH_MOVE = 2, TOUCH_CANCEL = 3;
    public static final int KEY_DOWN = 0, KEY_UP = 1;

    private static final int MAX_MSG = 8 * 1024 * 1024;
    private static final int DEAD_MS = 6000;                       // 6 giây không nhận được gì = đứt
    private static final long[] BACKOFF = {500, 1000, 2000, 4000, 5000};
    private static final long[] BACKOFF_PREVIEW = {1000, 3000, 8000, 15000, 30000};   // ô xem trước: lỗi thì nối lại thưa dần (đỡ tốn máy chủ)
    private static final SecureRandom RND = new SecureRandom();

    /** Báo cho giao diện (luôn chạy trên luồng giao diện, không gọi nữa sau close()). */
    public interface Listener {
        /** Đang nối: attempt = 0 lần đầu, ≥ 1 là lần nối lại thứ mấy; why = lý do lần trước (có thể rỗng). */
        void onConnecting(int attempt, String why);
        /** Kết quả cloudphone_endpoint (có stream.api cho các lệnh cpapi). */
        void onEndpoint(JSONObject ep);
        /** Máy chủ nhận phiên (WELCOME). direct = TLS trực tiếp, false = WebSocket qua Cloudflare. */
        void onWelcome(JSONObject welcome, boolean direct);
        /** Máy ảo vừa copy chữ. */
        void onClipboard(String text);
        /** Thông số ~1 giây/lần: hình/giây, kbps nhận được, ping (−1 = chưa có), đường đi, STATS của máy chủ (có thể null). */
        void onStats(int fps, int kbps, int pingMs, boolean direct, JSONObject server);
        /** Lỗi tạm (máy chủ báo / mạng) — client tự thử lại. */
        void onProblem(String code, String msg);
        /** Dừng hẳn, không tự nối lại: KICKED, LOGIN (phải đăng nhập lại), AUTH, NOT_YOURS, LOCKED, BAD, NOT_FOUND, NOT_ALLOWED, NOT_ACTIVE, NO_RPC;
         *  ô xem trước thêm: NO_PREVIEW (máy chủ chưa hỗ trợ), PREVIEW_LIMIT (máy đang được xem trước ở quá nhiều nơi). */
        void onStopped(String code, String msg);
    }

    /** Nơi nhận hình (StreamView). Gọi trên luồng mạng — phải trả về ngay. */
    public interface VideoSink {
        /** WELCOME / SIZE: kích thước hình mới → bỏ trạng thái giải mã cũ, chờ khung khoá có SPS/PPS. */
        void onVideoFormat(int w, int h);
        /** 1 khung H.264 (Annex-B) nằm ở buf[off, off+len). buf không bị dùng lại sau đó (giữ được). */
        void onVideoFrame(byte[] buf, int off, int len, boolean keyframe);
    }

    private final Context app;
    private final SharedPreferences prefs;
    private final String phone;
    private final Listener ui;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile String q;
    private volatile VideoSink sink;
    private volatile boolean closed = false;
    private volatile Session cur;
    private volatile Socket dialing;               // socket đang nối dở (close() đóng luôn cho nhanh)
    private volatile long lastKeyReq = 0;
    private volatile boolean preview = false;      // ô xem trước: hình nhỏ, chỉ xem (xem preview())
    private volatile int previewMax = 480;
    private Thread net;
    // chỉ luồng mạng dùng
    private String node = "";
    private boolean hadVideo = false;

    public StreamClient(Context c, String phoneId, String quality, Listener listener) {
        app = c.getApplicationContext();
        prefs = app.getSharedPreferences("stream", Context.MODE_PRIVATE);
        phone = phoneId;
        q = quality == null || quality.isEmpty() ? "auto" : quality;
        ui = listener;
    }

    public void setVideoSink(VideoSink s) { sink = s; }

    /** Chế độ ô xem trước (danh sách máy / "Xem tất cả"): hình nhỏ (cạnh dài ≤ maxh, 160–480), ~8 khung/giây, chỉ xem — không đá
     *  phiên điều khiển đang mở, không bị phiên điều khiển đá. Gọi trước start(). Máy chủ chưa hỗ trợ → onStopped("NO_PREVIEW"). */
    public StreamClient preview(int maxh) {
        preview = true;
        previewMax = Math.max(160, Math.min(480, maxh));
        return this;
    }

    public void start() {
        if (net != null || closed) return;
        net = new Thread(this::run, "BRS-net");
        net.start();
    }

    /** Đã vào phiên (nhận WELCOME) → gửi lệnh được. */
    public boolean isLive() {
        Session s = cur;
        return s != null && s.ready && !s.dead && !closed;
    }

    /** Đóng hẳn: gửi BYE rồi cắt kết nối (làm ở luồng nền, gọi từ luồng giao diện được). */
    public void close() {
        if (closed) return;
        closed = true;
        final Session s = cur;
        final Socket d = dialing;
        if (s != null) synchronized (s.lock) { s.bye = true; s.lock.notifyAll(); }
        Thread t = net;
        if (t != null) t.interrupt();
        new Thread(() -> {
            if (s != null) { try { Thread.sleep(400); } catch (InterruptedException ignored) { } }
            kill(s);                                   // luồng ghi chưa kịp gửi BYE (mạng nghẽn) → cắt luôn
            closeQuietly(d);
        }, "BRS-close").start();
    }

    // ================================================================ lệnh gửi máy (gọi từ luồng nào cũng được)

    /** Chạm: nx, ny = 0..1 trên khung hình đã giải mã; pointer 0–9. Lệnh kéo được gộp: tối đa 1 lệnh / ngón / 8 ms. */
    public void touch(int action, int pointer, float nx, float ny) {
        if (pointer < 0 || pointer > 9) return;
        Session s = cur;
        if (s == null || !s.ready || s.dead || closed) return;
        int x = u16(nx), y = u16(ny);
        synchronized (s.lock) {
            if (action == TOUCH_MOVE) {
                Move m = s.moving[pointer];
                if (m != null) { m.x = x; m.y = y; return; }          // lệnh kéo chưa gửi → chỉ cập nhật toạ độ mới nhất
                m = new Move(pointer, x, y);
                s.moving[pointer] = m;
                s.q.addLast(m);
            } else {
                s.moving[pointer] = null;                              // lệnh kéo đang chờ giữ nguyên toạ độ, đi trước lệnh này
                s.q.addLast(new Out(C_TOUCH, touchBytes(action, pointer, x, y)));
            }
            s.lock.notifyAll();
        }
    }

    /** Phím Android: action 0 nhấn · 1 nhả; meta = trạng thái Shift/Ctrl… của Android. */
    public void key(int action, int code, int meta) {
        send(C_KEY, new byte[]{(byte) action, (byte) (code >>> 24), (byte) (code >>> 16), (byte) (code >>> 8), (byte) code,
                (byte) (meta >>> 24), (byte) (meta >>> 16), (byte) (meta >>> 8), (byte) meta});
    }

    /** Nhấn + nhả 1 phím. */
    public void press(int code, int meta) { key(KEY_DOWN, code, meta); key(KEY_UP, code, meta); }

    /** Gõ chữ (máy chủ tự chia chữ dài). */
    public void text(String t) {
        if (t != null && !t.isEmpty()) send(C_TEXT, t.getBytes(StandardCharsets.UTF_8));
    }

    /** Lăn chuột: h, v theo nấc 120; v > 0 = lăn lên. */
    public void scroll(float nx, float ny, int h, int v) {
        int x = u16(nx), y = u16(ny), hh = Math.max(-32768, Math.min(32767, h)), vv = Math.max(-32768, Math.min(32767, v));
        send(C_SCROLL, new byte[]{(byte) (x >>> 8), (byte) x, (byte) (y >>> 8), (byte) y, (byte) (hh >>> 8), (byte) hh, (byte) (vv >>> 8), (byte) vv});
    }

    /** Lệnh hệ thống: back · home · recents · power · volup · voldown · rotate · notif · menu. */
    public void cmd(String name) {
        try { send(C_CMD, new JSONObject().put("cmd", name).toString().getBytes(StandardCharsets.UTF_8)); } catch (Exception ignored) { }
    }

    /** Xoay máy: "land" (khoá ngang) · "port" (khoá dọc). Máy chủ cũ chỉ hiểu "rotate" (đổi qua lại) — vẫn chạy. */
    public void rotate(String to) {
        try { send(C_CMD, new JSONObject().put("cmd", "rotate").put("to", to).toString().getBytes(StandardCharsets.UTF_8)); } catch (Exception ignored) { }
    }

    /** Đổi chất lượng: eco · bal · hd · auto (nhớ luôn cho lần nối lại). */
    public void quality(String nq) {
        if (nq == null || nq.isEmpty()) return;
        q = nq;
        try { send(C_QUALITY, new JSONObject().put("q", nq).toString().getBytes(StandardCharsets.UTF_8)); } catch (Exception ignored) { }
    }

    /** Đặt bộ nhớ copy của máy ảo; paste = dán luôn vào ô đang nhập. */
    public void clipSet(String text, boolean paste) {
        if (text == null) return;
        byte[] t = text.getBytes(StandardCharsets.UTF_8);
        byte[] p = new byte[t.length + 1];
        p[0] = (byte) (paste ? 1 : 0);
        System.arraycopy(t, 0, p, 1, t.length);
        send(C_CLIP, p);
    }

    /** Xin khung khoá mới (bộ giải mã lỗi / vừa có Surface mới). Tối đa 1 lần / giây. */
    public void requestKeyframe() {
        long now = SystemClock.uptimeMillis();
        if (now - lastKeyReq < 1000) return;
        if (send(C_KEYFRAME, null)) lastKeyReq = now;
    }

    private boolean send(int type, byte[] p) {
        Session s = cur;
        if (s == null || !s.ready || s.dead || closed) return false;
        synchronized (s.lock) {
            if (s.q.size() > 3000) return false;
            s.q.addLast(new Out(type, p));
            s.lock.notifyAll();
        }
        return true;
    }

    // ================================================================ vòng nối / nối lại (luồng BRS-net)

    private void run() {
        try { android.os.Process.setThreadPriority(prio()); } catch (Throwable ignored) { }
        final long[] bo = preview ? BACKOFF_PREVIEW : BACKOFF;
        JSONObject ep = null;
        boolean refetch = true, authRetried = false;
        int attempt = 0;
        String why = "";
        while (!closed) {
            final int a = attempt;
            final String w = why;
            post(() -> ui.onConnecting(a, w));
            long delay = bo[Math.min(attempt, bo.length - 1)];
            boolean opened = false;
            hadVideo = false;
            try {
                if (ep == null || refetch) {
                    ep = endpoint();
                    refetch = false;
                    final JSONObject e = ep;
                    post(() -> ui.onEndpoint(e));
                }
                String token = token();
                Session s = open(ep);
                opened = true;
                session(s, token);
                why = Ui.L("Mất kết nối với máy chủ.", "Lost connection to the server.");
            } catch (Stop e) {
                if (!"AUTH".equals(e.code) || authRetried) { stop(e.code, e.msg); break; }
                authRetried = true;                                    // mã đăng nhập hết hạn → làm mới 1 lần rồi nối lại ngay
                boolean fresh = false;
                try {
                    Api.expiresAt = 0;
                    Api.token();
                    fresh = true;
                } catch (Exception t) {
                    if (!Api.loggedIn()) { stop("LOGIN", Api.friendly(t)); break; }   // refresh token bị từ chối → đăng nhập lại
                    why = Api.friendly(t);                                         // chỉ là lỗi mạng → thử lại sau
                }
                if (fresh) { why = ""; continue; }
            } catch (Retry e) {
                if (e.refetch) refetch = true;
                if (e.delay > 0) delay = preview ? Math.max(delay, e.delay) : e.delay;
                why = e.msg;
                final String c = e.code, m = e.msg;
                post(() -> ui.onProblem(c, m));
            } catch (Exception e) {
                if (closed) break;
                if (!opened) refetch = true;                          // không nối được đường nào → lần sau hỏi lại máy chủ
                why = opened ? Ui.L("Mất kết nối với máy chủ.", "Lost connection to the server.")
                        : Ui.L("Không nối được máy chủ phát hình — kiểm tra mạng.", "Can't reach the stream server — check your network.");
            }
            if (closed) break;
            if (hadVideo) { attempt = 0; authRetried = false; delay = bo[0]; }
            try { Thread.sleep(delay); } catch (InterruptedException ie) { if (closed) break; }
            attempt++;
        }
    }

    private void stop(String code, String msg) {
        post(() -> ui.onStopped(code, msg));
    }

    /** Ô xem trước chạy nền (nhường giao diện + phiên điều khiển); phiên điều khiển ưu tiên như luồng vẽ. */
    private int prio() {
        return preview ? android.os.Process.THREAD_PRIORITY_BACKGROUND : android.os.Process.THREAD_PRIORITY_DISPLAY;
    }

    private String token() throws Exception {
        try { return Api.token(); }
        catch (Api.ApiError e) {
            if (e.status == 401) throw new Stop("LOGIN", Api.friendly(e));
            throw e;
        }
    }

    /** Hỏi máy này đang nằm ở máy chủ nào + cách nối (RPC cloudphone_endpoint). */
    private JSONObject endpoint() throws Exception {
        for (int t = 0; ; t++) {
            try {
                Object o = Api.rpc("cloudphone_endpoint", new JSONObject().put("p_id", phone));
                if (o instanceof JSONObject) return (JSONObject) o;
                throw new Stop("NOT_FOUND", Ui.L("Không tìm thấy máy.", "Phone not found."));
            } catch (Api.ApiError e) {
                String m = String.valueOf(e.getMessage());
                if (m.contains("NOT_LOGGED_IN") || m.contains("SESSION_EXPIRED")) throw new Stop("LOGIN", Api.friendly(e));
                if (m.contains("NOT_FOUND")) throw new Stop("NOT_FOUND", Ui.L("Không tìm thấy máy.", "Phone not found."));
                if (m.contains("NOT_ALLOWED")) throw new Stop("NOT_ALLOWED", Ui.L("Bạn không có quyền mở máy này.", "You are not allowed to open this phone."));
                if (e.status == 401 && t == 0) { Api.expiresAt = 0; continue; }          // mã truy cập hết hạn → làm mới rồi hỏi lại
                if (e.status == 404 && m.contains("cloudphone_endpoint"))
                    throw new Stop("NO_RPC", Ui.L("Máy chủ chưa cập nhật giao thức phát hình mới.", "The server hasn't been updated for the new stream yet."));
                throw new Retry("NET", Ui.L("Không lấy được thông tin máy chủ: ", "Couldn't get server info: ") + Api.friendly(e), true, 0);
            }
        }
    }

    /** Thử lần lượt: LAN trực tiếp (400 ms) → IP công khai (2 s) → WebSocket (8 s); đường nối được lần trước thử đầu tiên. */
    private Session open(JSONObject ep) throws Exception {
        String st = str(ep, "status");
        if (!st.isEmpty() && !"active".equals(st))
            throw new Stop("NOT_ACTIVE", Ui.L("Máy chưa chạy (đang tạo, tạm dừng hoặc đã hết hạn).", "This phone is not running."));
        node = str(ep, "node");
        JSONObject stream = ep.optJSONObject("stream");
        String cert = str(stream, "cert").trim();
        List<Path> paths = paths(stream, cert);
        if (!ep.optBoolean("online", false) || paths.isEmpty())
            throw new Retry("OFFLINE", Ui.L("Máy chủ đang bảo trì / offline", "Server under maintenance / offline"), true, 10000);
        if (preview && !truthy(stream.opt("preview")))                // máy chủ cũ: phiên xem trước sẽ đá phiên điều khiển → không mở
            throw new Stop("NO_PREVIEW", Ui.L("Máy chủ chưa hỗ trợ xem trước.", "This server has no live preview yet."));
        Exception last = null;
        for (Path p : paths) {
            if (closed) throw new IOException("closed");
            try { return p.ws ? dialWs(p) : dialDirect(p, cert); }
            catch (Exception e) { last = e; }
        }
        if (last instanceof IOException) throw (IOException) last;
        throw new IOException(last == null ? "no path" : String.valueOf(last.getMessage()), last);
    }

    private List<Path> paths(JSONObject st, String cert) {
        List<Path> out = new ArrayList<>();
        if (st == null) return out;
        JSONArray d = st.optJSONArray("direct");
        if (!cert.isEmpty() && d != null) {                           // không có mã chứng chỉ → bỏ đường trực tiếp
            for (int pass = 0; pass < 2; pass++) {
                for (int i = 0; i < d.length(); i++) {
                    JSONObject e = d.optJSONObject(i);
                    if (e == null) continue;
                    boolean lan = e.optBoolean("lan", false);
                    if (lan != (pass == 0)) continue;
                    String host = str(e, "host").trim();
                    int port = e.optInt("port", 0);
                    if (host.isEmpty() || port <= 0 || port > 65535) continue;
                    out.add(new Path(false, host, port, lan ? 400 : 2000, "d:" + host + ":" + port));
                }
            }
        }
        String ws = str(st, "ws").trim();
        if (ws.startsWith("wss://") || ws.startsWith("ws://")) out.add(new Path(true, ws, 0, 8000, "ws"));
        String last = prefs.getString(pathKey(), "");
        for (int i = 1; i < out.size(); i++) {
            if (out.get(i).key.equals(last)) { out.add(0, out.remove(i)); break; }
        }
        return out;
    }

    /** Nhớ đường nối được theo máy chủ + loại mạng (wifi / di động): ở nhà dùng LAN, ra ngoài dùng đường đã chạy được. */
    private String pathKey() { return "path_" + node + "_" + netTag(); }

    private String netTag() { return netTag(app); }

    /** Loại mạng đang dùng: w = wifi / dây · c = 4G/5G · x = không rõ. */
    static String netTag(Context app) {
        try {
            ConnectivityManager cm = (ConnectivityManager) app.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) return "x";
            Network n = cm.getActiveNetwork();
            NetworkCapabilities nc = n == null ? null : cm.getNetworkCapabilities(n);
            if (nc == null) return "x";
            if (nc.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || nc.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) return "w";
            if (nc.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) return "c";
            return "x";
        } catch (Exception e) { return "x"; }
    }

    // ---- đường trực tiếp: TCP + TLS, kiểm SHA-256 của chứng chỉ máy chủ (không kiểm CA / tên máy) ----
    private Session dialDirect(Path p, String cert) throws Exception {
        Socket raw = new Socket();
        dialing = raw;
        try {
            try { raw.setReceiveBufferSize(1 << 20); } catch (Exception ignored) { }
            raw.connect(new InetSocketAddress(p.host, p.port), p.timeout);
            if (closed) throw new IOException("closed");
            raw.setTcpNoDelay(true);
            raw.setSoTimeout(Math.max(3000, p.timeout * 2));               // chờ bắt tay TLS
            SSLContext ctx = SSLContext.getInstance("TLS");
            ctx.init(null, new TrustManager[]{new Pin(cert)}, null);
            SSLSocket ss = (SSLSocket) ctx.getSocketFactory().createSocket(raw, p.host, p.port, true);
            ss.startHandshake();                                            // sai chứng chỉ → CertificateException → thử đường sau
            raw.setSoTimeout(DEAD_MS);
            ss.setSoTimeout(DEAD_MS);
            return new Session(raw, ss, new BufferedInputStream(ss.getInputStream(), 65536), ss.getOutputStream(), false, p.key);
        } catch (Exception e) {
            closeQuietly(raw);
            throw e;
        } finally {
            dialing = null;
        }
    }

    /** Chỉ chấp nhận đúng chứng chỉ có SHA-256 (DER) = stream.cert. */
    private static final class Pin implements X509TrustManager {
        private final String want;
        Pin(String hex) { want = hex.trim().toLowerCase(Locale.ROOT).replace(":", ""); }

        @Override public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            throw new CertificateException("client certificates not supported");
        }

        @Override public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            if (chain == null || chain.length == 0) throw new CertificateException("no server certificate");
            byte[] d;
            try { d = MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded()); }
            catch (NoSuchAlgorithmException e) { throw new CertificateException(e); }
            if (want.isEmpty() || !hex(d).equals(want)) throw new CertificateException("server certificate does not match stream.cert");
        }

        @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
    }

    // ---- WebSocket (RFC 6455) qua Cloudflare: kiểm chứng chỉ bình thường (CA + tên miền) ----
    private Session dialWs(Path p) throws Exception {
        URI u = new URI(p.host);
        String scheme = u.getScheme() == null ? "wss" : u.getScheme().toLowerCase(Locale.ROOT);
        boolean tls = !"ws".equals(scheme);
        String host = u.getHost();
        if (host == null || host.isEmpty()) throw new IOException("bad ws url");
        int port = u.getPort() > 0 ? u.getPort() : (tls ? 443 : 80);
        String path = u.getRawPath() == null || u.getRawPath().isEmpty() ? "/" : u.getRawPath();
        if (u.getRawQuery() != null) path += "?" + u.getRawQuery();
        Socket raw = new Socket();
        dialing = raw;
        try {
            raw.connect(new InetSocketAddress(host, port), p.timeout);
            if (closed) throw new IOException("closed");
            raw.setTcpNoDelay(true);
            raw.setSoTimeout(p.timeout);
            Socket sock = raw;
            if (tls) {
                SSLSocketFactory f = (SSLSocketFactory) SSLSocketFactory.getDefault();
                SSLSocket ss = (SSLSocket) f.createSocket(raw, host, port, true);
                try {                                                   // SNI (Cloudflare cần) — hầu hết máy tự gửi, đặt thêm cho chắc
                    SSLParameters sp = ss.getSSLParameters();
                    List<SNIServerName> names = new ArrayList<>();
                    names.add(new SNIHostName(host));
                    sp.setServerNames(names);
                    ss.setSSLParameters(sp);
                } catch (Exception ignored) { }
                ss.startHandshake();
                if (!HttpsURLConnection.getDefaultHostnameVerifier().verify(host, ss.getSession()))
                    throw new SSLPeerUnverifiedException("certificate does not match " + host);
                ss.setSoTimeout(p.timeout);
                sock = ss;
            }
            InputStream in = new BufferedInputStream(sock.getInputStream(), 65536);
            OutputStream out = sock.getOutputStream();
            byte[] k = new byte[16];
            RND.nextBytes(k);
            String key = Base64.encodeToString(k, Base64.NO_WRAP);
            String hostHdr = port == (tls ? 443 : 80) ? host : host + ":" + port;
            String req = "GET " + path + " HTTP/1.1\r\n"
                    + "Host: " + hostHdr + "\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Key: " + key + "\r\n"
                    + "Sec-WebSocket-Version: 13\r\n"
                    + "User-Agent: BlueRobloxApp/" + Api.version + "\r\n\r\n";
            out.write(req.getBytes(StandardCharsets.ISO_8859_1));
            out.flush();
            String[] lines = readHead(in).split("\r\n");
            String[] status = lines.length > 0 ? lines[0].split(" ") : new String[0];
            if (status.length < 2 || !status[0].startsWith("HTTP/") || !"101".equals(status[1]))
                throw new IOException("WebSocket: " + (lines.length > 0 ? lines[0] : "?"));
            String accept = Base64.encodeToString(MessageDigest.getInstance("SHA-1")
                    .digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").getBytes(StandardCharsets.ISO_8859_1)), Base64.NO_WRAP);
            boolean ok = false;
            for (int i = 1; i < lines.length; i++) {
                int c = lines[i].indexOf(':');
                if (c <= 0) continue;
                if ("sec-websocket-accept".equals(lines[i].substring(0, c).trim().toLowerCase(Locale.ROOT))
                        && accept.equals(lines[i].substring(c + 1).trim())) ok = true;
            }
            if (!ok) throw new IOException("WebSocket: bad Sec-WebSocket-Accept");
            raw.setSoTimeout(DEAD_MS);
            sock.setSoTimeout(DEAD_MS);
            return new Session(raw, sock, in, out, true, p.key);
        } catch (Exception e) {
            closeQuietly(raw);
            throw e;
        } finally {
            dialing = null;
        }
    }

    /** Đọc phần đầu HTTP tới dòng trống (đọc từng byte để không nuốt mất khung WebSocket phía sau). */
    private static String readHead(InputStream in) throws IOException {
        StringBuilder b = new StringBuilder(256);
        while (b.length() < 16384) {
            int c = in.read();
            if (c < 0) throw new EOFException("WebSocket: server closed the connection");
            b.append((char) c);
            int n = b.length();
            if (n >= 4 && b.charAt(n - 1) == '\n' && b.charAt(n - 2) == '\r' && b.charAt(n - 3) == '\n' && b.charAt(n - 4) == '\r')
                return b.substring(0, n - 4);
        }
        throw new IOException("WebSocket: response header too long");
    }

    // ================================================================ 1 phiên

    private void session(Session s, String token) throws Exception {
        cur = s;
        try {
            if (closed) return;
            JSONObject hello = new JSONObject().put("v", 2).put("token", token).put("phone", phone)
                    .put("client", "android").put("ver", Api.version).put("q", q)
                    .put("net", netTag());                       // w = wifi · c = 4G/5G → chế độ Tự động bắt đầu nhẹ hơn khi dùng 4G
            if (preview) hello.put("mode", "preview").put("maxh", previewMax);
            writeMsg(s, C_HELLO, hello.toString().getBytes(StandardCharsets.UTF_8));
            s.lastRx = SystemClock.uptimeMillis();
            Thread tx = new Thread(() -> writer(s), "BRS-tx");
            tx.start();
            DataInputStream in = new DataInputStream(s.in);
            long statT = SystemClock.uptimeMillis();
            int frames = 0;
            long bytes = 0;
            while (!closed && !s.dead) {
                byte[] m;
                try { m = s.ws ? wsMessage(s, in) : directMessage(in); }
                catch (SocketTimeoutException te) { throw new IOException("no data for 6 s"); }
                long now = SystemClock.uptimeMillis();
                s.lastRx = now;
                if (m != null && m.length > 0) {
                    int type = m[0] & 0xFF;
                    if (type == S_VIDEO) {
                        if (m.length > 10) {
                            boolean key = (m[1] & 1) != 0;
                            long pts = u64(m, 2);
                            synchronized (s.lock) {                    // ACK: báo khung mới nhất đã nhận (luồng ghi gửi ~0,1 s/lần)
                                boolean wake = !s.ptsNew || key;
                                s.pts = pts;
                                s.ptsNew = true;
                                if (key) s.ackNow = true;
                                if (wake) s.lock.notifyAll();
                            }
                            hadVideo = true;
                            frames++;
                            bytes += m.length - 10;
                            VideoSink vs = sink;
                            if (vs != null && !closed) vs.onVideoFrame(m, 10, m.length - 10, key);
                        }
                    } else {
                        handle(s, type, m);
                    }
                }
                if (now - statT >= 1000) {
                    long dt = now - statT;
                    final int fps = (int) Math.round(frames * 1000.0 / dt), kbps = (int) (bytes * 8 / dt), ping = s.ping;
                    final boolean direct = !s.ws;
                    final JSONObject sv = s.server;
                    post(() -> ui.onStats(fps, kbps, ping, direct, sv));
                    statT = now;
                    frames = 0;
                    bytes = 0;
                }
            }
        } finally {
            kill(s);
            if (cur == s) cur = null;
        }
    }

    private void handle(Session s, int type, byte[] m) throws Exception {
        switch (type) {
            case S_WELCOME: {
                final JSONObject j = json(m);
                int w = j.optInt("w", 0), h = j.optInt("h", 0);
                VideoSink vs = sink;
                if (vs != null && w > 0 && h > 0 && !closed) vs.onVideoFormat(w, h);
                s.ready = true;
                try { prefs.edit().putString(pathKey(), s.key).apply(); } catch (Exception ignored) { }
                final boolean direct = !s.ws;
                post(() -> ui.onWelcome(j, direct));
                break;
            }
            case S_SIZE: {
                JSONObject j = json(m);
                int w = j.optInt("w", 0), h = j.optInt("h", 0);
                VideoSink vs = sink;
                if (vs != null && w > 0 && h > 0 && !closed) vs.onVideoFormat(w, h);
                break;
            }
            case S_CLIP: {
                final String t = new String(m, 1, m.length - 1, StandardCharsets.UTF_8);
                post(() -> ui.onClipboard(t));
                break;
            }
            case S_PONG: {
                if (m.length >= 9) {
                    long rtt = SystemClock.elapsedRealtime() - u64(m, 1);
                    if (rtt >= 0 && rtt < 60000) s.ping = (int) rtt;
                }
                break;
            }
            case S_STATS:
                s.server = json(m);
                break;
            case S_ERROR: {
                JSONObject j = json(m);
                String code = j.isNull("code") ? "INTERNAL" : j.optString("code", "INTERNAL");
                String msg = j.isNull("msg") ? "" : j.optString("msg", "");
                if (preview && ("PREVIEW_LIMIT".equals(code) || "KICKED".equals(code))) throw new Stop(code, msg);   // nhường chỗ → thôi, không giành lại
                throw serverError(code, msg);
            }
            default:
                break;                                                     // kiểu tin lạ → bỏ qua
        }
    }

    private static Exception serverError(String code, String msg) {
        switch (code) {
            case "KICKED":
                return new Stop(code, msg.isEmpty() ? Ui.L("Máy đang được mở ở nơi khác.", "This phone was opened somewhere else.") : msg);
            case "AUTH":
                return new Stop(code, msg.isEmpty() ? Ui.L("Phiên đăng nhập hết hạn, hãy đăng nhập lại.", "Session expired, please log in again.") : msg);
            case "NOT_YOURS":
            case "LOCKED":
            case "BAD":
                return new Stop(code, msg.isEmpty() ? Ui.L("Máy chủ từ chối mở máy này.", "The server refused to open this phone.") : msg);
            case "OFFLINE":                                                 // máy có thể đã chuyển máy chủ → hỏi lại đường nối
                return new Retry(code, msg.isEmpty() ? Ui.L("Máy chưa sẵn sàng.", "The phone is not ready.") : msg, true, 0);
            case "MAINT":
                return new Retry(code, msg.isEmpty() ? Ui.L("Hệ thống đang bảo trì.", "Under maintenance.") : msg, false, 10000);
            default:                                                        // BUSY, INTERNAL…
                return new Retry(code, msg.isEmpty() ? Ui.L("Máy chủ đang bận, thử lại…", "Server busy, retrying…") : msg, false, 0);
        }
    }

    private static byte[] directMessage(DataInputStream in) throws IOException {
        int n = in.readInt();
        if (n < 1 || n > MAX_MSG) throw new IOException("bad frame length " + n);
        byte[] m = new byte[n];
        in.readFully(m);
        return m;
    }

    /** 1 tin nhị phân WebSocket (ghép mảnh, tự trả lời ping). null = tin chữ / rỗng (bỏ qua). */
    private byte[] wsMessage(Session s, DataInputStream in) throws IOException {
        ByteArrayOutputStream frag = null;
        int fragOp = 0;
        while (true) {
            int b0 = in.readUnsignedByte(), b1 = in.readUnsignedByte();
            boolean fin = (b0 & 0x80) != 0;
            int op = b0 & 0x0F;
            long n = b1 & 0x7F;
            if (n == 126) n = in.readUnsignedShort();
            else if (n == 127) n = in.readLong();
            if (n < 0 || n > MAX_MSG + 16) throw new IOException("ws frame too big");
            byte[] mask = null;
            if ((b1 & 0x80) != 0) { mask = new byte[4]; in.readFully(mask); }
            byte[] d = new byte[(int) n];
            in.readFully(d);
            if (mask != null) for (int i = 0; i < d.length; i++) d[i] ^= mask[i & 3];
            s.lastRx = SystemClock.uptimeMillis();
            if (op == 8) throw new EOFException("ws closed by server");
            if (op == 9) { control(s, new Out(-10, d)); continue; }         // ping → pong cùng nội dung
            if (op == 10) continue;                                         // pong
            if (op == 1 || op == 2) {
                if (fin) return op == 2 ? d : null;
                frag = new ByteArrayOutputStream(Math.max(4096, d.length * 2));
                frag.write(d, 0, d.length);
                fragOp = op;
                continue;
            }
            if (op == 0) {
                if (frag == null) continue;
                frag.write(d, 0, d.length);
                if (frag.size() > MAX_MSG + 16) throw new IOException("ws message too big");
                if (fin) {
                    byte[] all = frag.toByteArray();
                    frag = null;
                    if (fragOp == 2) return all;
                }
                continue;
            }
            throw new IOException("ws opcode " + op);
        }
    }

    private static void control(Session s, Out o) {
        synchronized (s.lock) { s.q.addFirst(o); s.lock.notifyAll(); }
    }

    // ================================================================ luồng ghi (BRS-tx): hàng đợi + PING + ACK + gộp lệnh kéo

    private void writer(Session s) {
        try { android.os.Process.setThreadPriority(prio()); } catch (Throwable ignored) { }
        long nextPing = SystemClock.uptimeMillis() + 100;
        try {
            while (true) {
                int type;
                byte[] p;
                boolean last = false;
                synchronized (s.lock) {
                    while (true) {
                        if (s.dead) return;
                        long now = SystemClock.uptimeMillis();
                        if (s.bye) { type = C_BYE; p = null; last = true; break; }
                        if (now >= nextPing) {
                            type = C_PING;
                            p = u64b(SystemClock.elapsedRealtime());
                            nextPing = now + 2000;
                            break;
                        }
                        if (now - s.lastRx > DEAD_MS + 1000) throw new IOException("dead link");
                        long wait = nextPing - now;
                        if (s.ptsNew) {
                            long due = s.ackNow ? now : s.ackAt + 100;
                            if (now >= due) {
                                type = C_ACK;
                                p = u64b(s.pts);
                                s.ptsNew = false;
                                s.ackNow = false;
                                s.ackAt = now;
                                break;
                            }
                            wait = Math.min(wait, due - now);
                        }
                        Object head = s.q.peekFirst();
                        if (head instanceof Move) {
                            Move mv = (Move) head;
                            long due = s.moveAt[mv.p] + 8;
                            if (now >= due) {
                                s.q.pollFirst();
                                if (s.moving[mv.p] == mv) s.moving[mv.p] = null;
                                s.moveAt[mv.p] = now;
                                type = C_TOUCH;
                                p = touchBytes(TOUCH_MOVE, mv.p, mv.x, mv.y);
                                break;
                            }
                            wait = Math.min(wait, due - now);
                        } else if (head != null) {
                            Out o = (Out) s.q.pollFirst();
                            type = o.type;
                            p = o.p;
                            break;
                        }
                        s.lock.wait(Math.max(1, wait));
                    }
                }
                writeMsg(s, type, p);
                if (last) return;
            }
        } catch (Exception ignored) {
            // ghi lỗi / đứt → phiên kết thúc (luồng đọc tự thoát vì socket đã đóng)
        } finally {
            kill(s);
        }
    }

    /** Ghi 1 tin: trực tiếp = [len u32][type][payload]; WebSocket = khung nhị phân có mặt nạ [type][payload]. type < 0 = khung điều khiển WS (opcode = −type). */
    private static void writeMsg(Session s, int type, byte[] p) throws IOException {
        int n = p == null ? 0 : p.length;
        byte[] f;
        if (!s.ws) {
            if (type < 0) return;
            int len = n + 1;
            f = new byte[4 + len];
            f[0] = (byte) (len >>> 24);
            f[1] = (byte) (len >>> 16);
            f[2] = (byte) (len >>> 8);
            f[3] = (byte) len;
            f[4] = (byte) type;
            if (n > 0) System.arraycopy(p, 0, f, 5, n);
        } else {
            boolean ctl = type < 0;
            int plen = n + (ctl ? 0 : 1);
            int hl = plen < 126 ? 2 : plen < 65536 ? 4 : 10;
            f = new byte[hl + 4 + plen];
            f[0] = (byte) (0x80 | (ctl ? -type : 2));
            if (plen < 126) {
                f[1] = (byte) (0x80 | plen);
            } else if (plen < 65536) {
                f[1] = (byte) (0x80 | 126);
                f[2] = (byte) (plen >>> 8);
                f[3] = (byte) plen;
            } else {
                f[1] = (byte) (0x80 | 127);
                long L = plen;
                for (int i = 0; i < 8; i++) f[2 + i] = (byte) (L >>> (56 - 8 * i));
            }
            byte[] mk = new byte[4];
            RND.nextBytes(mk);
            System.arraycopy(mk, 0, f, hl, 4);
            int o = hl + 4, i = 0;
            if (!ctl) { f[o] = (byte) (type ^ mk[0]); i = 1; }
            for (int j = 0; j < n; j++, i++) f[o + i] = (byte) (p[j] ^ mk[i & 3]);
        }
        s.out.write(f);
        s.out.flush();
    }

    /** Đóng phiên (không bao giờ gọi trên luồng giao diện: đóng TLS có thể ghi mạng). Đóng TCP trước để gỡ mọi lệnh đọc/ghi đang chờ. */
    private static void kill(Session s) {
        if (s == null) return;
        s.dead = true;
        synchronized (s.lock) { s.lock.notifyAll(); }
        closeQuietly(s.raw);
        closeQuietly(s.sock);
    }

    private static void closeQuietly(Socket s) {
        if (s == null) return;
        try { s.close(); } catch (Exception ignored) { }
    }

    private void post(Runnable r) {
        main.post(() -> { if (!closed) r.run(); });
    }

    // ================================================================ tiện ích

    private static int u16(float v) {
        if (Float.isNaN(v)) v = 0f;
        return Math.max(0, Math.min(65535, (int) (v * 65535f + 0.5f)));
    }

    private static byte[] touchBytes(int action, int pointer, int x, int y) {
        return new byte[]{(byte) action, (byte) pointer, (byte) (x >>> 8), (byte) x, (byte) (y >>> 8), (byte) y};
    }

    private static byte[] u64b(long v) {
        byte[] b = new byte[8];
        for (int i = 0; i < 8; i++) b[i] = (byte) (v >>> (56 - 8 * i));
        return b;
    }

    private static long u64(byte[] b, int off) {
        long v = 0;
        for (int i = 0; i < 8; i++) v = (v << 8) | (b[off + i] & 0xFFL);
        return v;
    }

    private static JSONObject json(byte[] m) {
        try { return new JSONObject(new String(m, 1, m.length - 1, StandardCharsets.UTF_8)); }
        catch (Exception e) { return new JSONObject(); }
    }

    /** 1 / true / "1" / "true" → đúng. */
    private static boolean truthy(Object o) {
        if (o instanceof Boolean) return (Boolean) o;
        if (o instanceof Number) return ((Number) o).intValue() != 0;
        return o != null && ("1".equals(String.valueOf(o).trim()) || "true".equalsIgnoreCase(String.valueOf(o).trim()));
    }

    /** Chuỗi trong JSON; thiếu / null → "". */
    private static String str(JSONObject o, String k) {
        if (o == null || o.isNull(k)) return "";
        return o.optString(k, "");
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder(b.length * 2);
        for (byte x : b) s.append(Character.forDigit((x >> 4) & 0xF, 16)).append(Character.forDigit(x & 0xF, 16));
        return s.toString();
    }

    // ================================================================ kiểu dữ liệu nội bộ

    private static final class Session {
        final Socket raw, sock;
        final InputStream in;
        final OutputStream out;
        final boolean ws;
        final String key;
        final Object lock = new Object();
        final ArrayDeque<Object> q = new ArrayDeque<>();     // Out hoặc Move
        final Move[] moving = new Move[10];                  // lệnh kéo đang chờ gửi của từng ngón
        final long[] moveAt = new long[10];                  // lúc gửi lệnh kéo gần nhất của từng ngón
        volatile boolean ready = false, dead = false;
        volatile long lastRx;
        volatile int ping = -1;
        volatile JSONObject server;
        boolean bye = false, ptsNew = false, ackNow = false; // giữ lock
        long pts = 0, ackAt = 0;                             // giữ lock

        Session(Socket raw, Socket sock, InputStream in, OutputStream out, boolean ws, String key) {
            this.raw = raw;
            this.sock = sock;
            this.in = in;
            this.out = out;
            this.ws = ws;
            this.key = key;
        }
    }

    private static final class Move {
        final int p;
        int x, y;
        Move(int p, int x, int y) { this.p = p; this.x = x; this.y = y; }
    }

    private static final class Out {
        final int type;
        final byte[] p;
        Out(int type, byte[] p) { this.type = type; this.p = p; }
    }

    private static final class Path {
        final boolean ws;
        final String host, key;
        final int port, timeout;
        Path(boolean ws, String host, int port, int timeout, String key) {
            this.ws = ws;
            this.host = host;
            this.port = port;
            this.timeout = timeout;
            this.key = key;
        }
    }

    /** Dừng hẳn (không tự nối lại). */
    private static final class Stop extends Exception {
        final String code, msg;
        Stop(String code, String msg) { super(code + ": " + msg); this.code = code; this.msg = msg; }
    }

    /** Lỗi tạm: tự thử lại (refetch = hỏi lại máy chủ nào; delay > 0 = chờ lâu hơn bình thường). */
    private static final class Retry extends Exception {
        final String code, msg;
        final boolean refetch;
        final long delay;
        Retry(String code, String msg, boolean refetch, long delay) {
            super(code + ": " + msg);
            this.code = code;
            this.msg = msg;
            this.refetch = refetch;
            this.delay = delay;
        }
    }
}
