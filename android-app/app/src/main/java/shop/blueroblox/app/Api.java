package shop.blueroblox.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Kết nối Supabase (tài khoản, máy, giá) + máy chủ điện thoại (cpapi). Mọi lệnh mạng chạy nền, trả kết quả về luồng giao diện. */
public final class Api {
    public static final String SB = "https://nprftgodswlpzomcttal.supabase.co";
    public static final String KEY = "sb_publishable_qfNcnOMv70nq5LIlYXDJzg_UtdWHVze";
    /** cpapi mặc định — chỉ dùng khi máy chủ chưa báo đường riêng (stream.api). */
    public static final String PHONE = "https://phone.cloudblue.vn";
    public static final String CPAPI = PHONE + "/cpapi";
    /** Web chính. Admin đổi được trong Supabase (settings.data.web) → lần sau đổi tên miền không cần cập nhật app. */
    public static volatile String WEB = "https://cloudblue.vn";
    /** File app trên GitHub (app.json + APK) — dùng khi web không vào được. */
    public static final String GH_DL = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/blueroblox-site/download";
    private static volatile boolean siteOk = false;

    /** Nhận tên miền web mới (chỉ link https hợp lệ, không có đường dẫn). */
    static void setWeb(String u) {
        if (u == null) return;
        u = u.trim();
        while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        if (u.matches("(?i)https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\\.[a-z]{2,}")) WEB = u;
    }

    /** Tên miền để hiện cho người dùng (VD cloudblue.vn). */
    public static String webHost() { return WEB.replaceFirst("(?i)^https://(www\\.)?", ""); }

    /** Bảng settings (ngân hàng, tên miền web…). Chạy nền. */
    public static JSONObject site() throws Exception {
        Object o = get("settings?id=eq.1&select=data");
        JSONArray a = o instanceof JSONArray ? (JSONArray) o : new JSONArray();
        JSONObject d = a.length() > 0 ? a.getJSONObject(0).optJSONObject("data") : null;
        if (d == null) d = new JSONObject();
        setWeb(d.optString("web", null));
        minAndroid = d.optString("min_app_android", "").trim();
        tiers = d.optJSONArray("cp_tiers");                 // 🎴 thẻ gói cấu hình (admin chỉnh trên web)
        siteOk = true;
        return d;
    }

    /** 1 lần mỗi lần mở app (nền): lấy tên miền web hiện tại. Lỗi thì bỏ qua, dùng tên miền mặc định. */
    public static void siteOnce() { if (!siteOk) try { site(); } catch (Exception ignored) { } }

    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static SharedPreferences prefs;

    public static String access = "", refresh = "", uid = "", email = "", version = "1";
    /** Máy chủ báo app đã cũ (lỗi APP_OUTDATED) → bắt buộc cập nhật. minAndroid = bản tối thiểu admin đặt (settings.data.min_app_android). */
    public static volatile boolean outdated = false;
    public static volatile String minAndroid = "";
    /** 🎴 Thẻ gói cấu hình (settings.data.cp_tiers) — null = dùng 5 gói mặc định. */
    public static volatile JSONArray tiers = null;
    /** Màn đang mở đăng ký: có APP_OUTDATED → hiện ngay hộp "Bắt buộc cập nhật". */
    public static volatile Runnable onOutdated = null;

    /** "1.44" < "1.45" (so từng số, thiếu số = 0: "1.45" = "1.45.0" — giống máy chủ). Chuỗi lạ → false (không chặn nhầm). */
    public static boolean verLt(String a, String b) {
        java.util.regex.Matcher ma = java.util.regex.Pattern.compile("\\d+").matcher(a == null ? "" : a);
        java.util.regex.Matcher mb = java.util.regex.Pattern.compile("\\d+").matcher(b == null ? "" : b);
        java.util.List<Long> x = new java.util.ArrayList<>(), y = new java.util.ArrayList<>();
        try { while (ma.find()) x.add(Long.parseLong(ma.group())); while (mb.find()) y.add(Long.parseLong(mb.group())); } catch (Exception e) { return false; }
        if (x.isEmpty() || y.isEmpty()) return false;
        for (int i = 0; i < Math.max(x.size(), y.size()); i++) {
            long p = i < x.size() ? x.get(i) : 0, q = i < y.size() ? y.get(i) : 0;
            if (p != q) return p < q;
        }
        return false;
    }

    /** App phải cập nhật mới dùng tiếp: máy chủ đã báo APP_OUTDATED, hoặc bản đang chạy thấp hơn mức admin đặt. */
    public static boolean mustUpdate() { return outdated || (minAndroid != null && !minAndroid.isEmpty() && verLt(version, minAndroid)); }
    public static long expiresAt = 0;

    public interface Cb<T> { void ok(T v); }
    public interface Err { void fail(String msg); }
    public interface Job<T> { T run() throws Exception; }

    public static class ApiError extends Exception {
        public final int status;
        public ApiError(int status, String msg) { super(msg); this.status = status; }
    }

    /** Bản CH Play (tên gói vn.cloudblue.app): không nạp / thuê / gia hạn / hoa hồng trong app, không link ra trang mua trên web,
     *  ẩn Clone + Root, cập nhật qua Google Play. Bản web (shop.blueroblox.app) giữ nguyên đủ tính năng. */
    public static boolean PLAY = false;

    /** Trang chính sách: bản CH Play mở trang riêng (quyền riêng tư + điều khoản, không có chỗ mua hàng). */
    public static String policyUrl() { return PLAY ? WEB + "/privacy.html" : WEB + "/#policy"; }

    /** Mã thiết bị gửi kèm mọi yêu cầu lên Supabase (header x-cb-dev, SQL v29): nhiều tài khoản trên CÙNG 1 máy là bot gác nhận ra
     *  (chống cày Blue bằng tài khoản clone). Là bản BĂM của Android ID (không gửi mã gốc), chỉ dùng để chống gian lận. */
    public static String DEV = null;

    private static String devId(Context c) {
        String aid = null;
        try { aid = android.provider.Settings.Secure.getString(c.getContentResolver(), android.provider.Settings.Secure.ANDROID_ID); } catch (Exception ignored) { }
        if (aid == null || aid.isEmpty() || "9774d56d682e549c".equals(aid)) {
            aid = prefs.getString("dev_rand", null);
            if (aid == null) { aid = java.util.UUID.randomUUID().toString(); prefs.edit().putString("dev_rand", aid).apply(); }
        }
        try {
            byte[] h = java.security.MessageDigest.getInstance("SHA-256").digest(("cloudblue-dev:" + aid).getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder("a-");
            for (int k = 0; k < 16; k++) sb.append(String.format("%02x", h[k] & 0xff));
            return sb.toString();
        } catch (Exception e) { return null; }
    }

    public static void init(Context c) {
        PLAY = "vn.cloudblue.app".equals(c.getPackageName());
        Guard.check(c);                                  // 🔒 1.115: app bị sửa / ký lại → chặn mọi kết nối (Guard.java)
        if (prefs != null) return;
        prefs = c.getApplicationContext().getSharedPreferences("auth", Context.MODE_PRIVATE);
        DEV = devId(c.getApplicationContext());
        access = prefs.getString("access", "");
        refresh = prefs.getString("refresh", "");
        uid = prefs.getString("uid", "");
        email = prefs.getString("email", "");
        expiresAt = prefs.getLong("exp", 0);
        try { version = c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName; } catch (Exception ignored) { }
    }

    public static boolean loggedIn() { return refresh != null && !refresh.isEmpty(); }

    /** Chạy việc mạng ở luồng nền. */
    public static <T> void bg(Job<T> job, Cb<T> ok, Err err) {
        POOL.execute(() -> {
            try {
                T v = job.run();
                MAIN.post(() -> { if (ok != null) ok.ok(v); });
            } catch (Exception e) {
                String m = friendly(e);
                MAIN.post(() -> { if (err != null) err.fail(m); });
            }
        });
    }

    public static void ui(Runnable r) { MAIN.post(r); }

    // ---------------- HTTP ----------------
    public static class Res {
        public int code; public byte[] body; public String cookie;
        public String text() { return new String(body, StandardCharsets.UTF_8); }
    }

    // ---------------- 🔒 1.115: GHIM CHỨNG CHỈ máy chủ tiền (Supabase) ----------------
    /** Công cụ bắt / sửa gói tin (HttpCanary, Reqable, mitmproxy chạy trong Termux…) phải cài một "chứng chỉ giả" vào máy (máy root cài
     *  thẳng vào kho hệ thống) để đọc / sửa dữ liệu máy chủ gửi về. Với Supabase, app CHỈ nhận chuỗi chứng chỉ đi lên các tổ chức cấp
     *  chứng chỉ công khai lớn bên dưới (Cloudflare / Supabase / AWS đang dùng) → chứng chỉ giả bị từ chối, app báo "Kết nối không an toàn".
     *  Mã pin = SHA-256 (base64) khoá công khai (SPKI) của chứng chỉ GỐC — công khai, không bí mật.
     *  An toàn: máy vẫn kiểm chứng chỉ như thường trước; tới PIN_UNTIL thì tự bỏ ghim (không bao giờ khoá chết app — nhớ ra bản mới gia hạn);
     *  dựng bộ ghim lỗi trên máy lạ → dùng kết nối thường (không chặn nhầm khách thật). Không ghim cloudblue.vn / máy chủ điện thoại. */
    private static final String SB_HOST = SB.replaceFirst("^https://", "");
    private static final long PIN_UNTIL = 1817078400000L;                  // 01/08/2027 00:00 UTC
    private static final java.util.Set<String> PINS = new java.util.HashSet<>(java.util.Arrays.asList(
            "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=", "diGVwiVYbubAI3RW4hB9xU8e/CH2GnkuvVFZE8zmgzI=",     // Let's Encrypt ISRG X1, X2
            "hxqRlPTu1bMS/0DITB1SSu0vd4u/8l8TjPgfaAp63Gc=", "QXnt2YHvdHR3tJYmQIr0Paosp6t/nggsEGD4QJZ3Q0g=",     // Google Trust Services R1, R3
            "mEflZT5enoR1FuXLgYYGqnVEoZvmf9c2bVBpiOjYQ0c=",                                                     // GTS R4 (Cloudflare WE1)
            "cGuxAXyFXFkWm61cF4HPWX8S0srS9j0aSqN0k4AP+4A=", "aCdH+LpiG4fN07wpXtXKvOciocDANj0daLOJKNJ4fx4=",     // GlobalSign R3, R6
            "rn+WLLnmp9v3uDP7GPqbcaiRdd+UnCMrap73yz3yu/w=", "4EoCLOMvTM8sf2BGKHuCijKpCfXnUUR/g/0scfb9gXM=",     // GlobalSign R46, E46
            "CLOmM1/OXvSPjw5UOYbAf9GKOxImEp9hhku9W90fHMk=", "fg6tdrtoGdwvVFEahDVPboswe53YIFjqbABPAdndpd8=",     // GlobalSign ECC R4, R5
            "0cRTd+vc1hjNFlHcLgLCHXUeWqn80bNDH/bs9qMTSPo=", "oyD01TTXvpfBro3QSZc1vIlcMjrdLTiL/M9mLCPX+Zo=",     // SSL.com RSA, ECC
            "K89VOmb1cJAN3TK6bf4ezAbJGC1mLcG2Dh97dnwr3VQ=", "G/ANXI8TwJTdF+AFBM8IiIUPEv0Gf6H5LA/b9guG4yE=",     // SSL.com TLS RSA / ECC 2022
            "x4QzPSC810K5/cMjb05Qm4k3Bw5zBn4lTdO/nEW/Td4=", "ICGRfpgmOUXIWcQ/HXPLQTkFPEFPoDyjvH7ohhQpjzs=",     // Sectigo USERTrust RSA, ECC
            "grX4Ta9HpZx6tSHkmCrvpApTQGo67CYDnvprLg5yRME=", "58qRu/uxh4gFezqAcERupSkRYBlBAvfcw7mEjGPLnNU=",     // COMODO RSA, ECC
            "Douxi77vs4G+Ib/BogbTFymEYq0QSFXwSgVCaZcI09Q=", "sLVjNUaFYfW7n6EtgBeEpjOlcnBdNPMrZDRF36iwBdE=",     // Sectigo Public Server R46, E46
            "i7WTqTvh0OioIruIfFR4kMPnBqrS2rdiVPl/s2uC/CY=", "uUwZgwDOxcBXrQcntwu+kYFpkiVkOaezL0WYEZ3anJc=",     // DigiCert Global G2, G3
            "ape1HIIZ6T5d7GS61YBs3rD4NVvkfnVwELcCRW4Bqv0=", "oC+voZLIy4HLE0FVT5wFtxzKKokLDRKY1oNkfJYe+98=",     // DigiCert TLS RSA4096 / ECC P384 G5
            "++MBgDH5WGvL9Bcn5Be30cRcL0f5O+NyoXuWtQdX1aI=", "f0KW/FtqTjs108NpYj42SrGvOB2PpxIVM8nWxjPqJGE=",     // Amazon Root CA 1, 2
            "NqvDJlas/GRcYbcWE8S/IceH9cq77kg0jVhZeAPXq8k=", "9+ze1cZgR9KO1kZrVDxA4HQ6voHRCSVNz4RdTCx4U8U=",     // Amazon Root CA 3, 4
            "KwccWaCgrnaw6tsrrSO61FgLacNgG2MMLq8GE6+oP5I="));                                                   // Starfield Services G2 (AWS)
    private static volatile javax.net.ssl.SSLSocketFactory sbSsl = null;
    private static volatile boolean sbSslTried = false;

    /** Bộ kết nối có ghim cho Supabase (dựng 1 lần). Dựng lỗi → null → dùng kết nối thường. */
    private static javax.net.ssl.SSLSocketFactory sbSsl() {
        if (sbSslTried) return sbSsl;
        synchronized (Api.class) {
            if (!sbSslTried) {
                try {
                    javax.net.ssl.TrustManagerFactory f = javax.net.ssl.TrustManagerFactory.getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm());
                    f.init((java.security.KeyStore) null);
                    javax.net.ssl.X509TrustManager sys = null;
                    for (javax.net.ssl.TrustManager t : f.getTrustManagers()) if (t instanceof javax.net.ssl.X509TrustManager) { sys = (javax.net.ssl.X509TrustManager) t; break; }
                    if (sys != null) {
                        javax.net.ssl.SSLContext ctx = javax.net.ssl.SSLContext.getInstance("TLS");
                        ctx.init(null, new javax.net.ssl.TrustManager[]{new SbPin(sys)}, null);
                        sbSsl = ctx.getSocketFactory();
                    }
                } catch (Exception e) { sbSsl = null; }
                sbSslTried = true;
            }
            return sbSsl;
        }
    }

    /** Máy kiểm chứng chỉ như bình thường (kho chứng chỉ hệ thống, không nhận chứng chỉ người dùng tự cài) + dựng chuỗi tới gốc tin cậy,
     *  rồi đòi chuỗi đó có ít nhất 1 chứng chỉ thuộc bộ ghim. */
    private static final class SbPin implements javax.net.ssl.X509TrustManager {
        private final javax.net.ssl.X509TrustManager sys;
        private final android.net.http.X509TrustManagerExtensions ext;
        SbPin(javax.net.ssl.X509TrustManager sys) { this.sys = sys; this.ext = new android.net.http.X509TrustManagerExtensions(sys); }
        @Override public void checkClientTrusted(java.security.cert.X509Certificate[] c, String a) throws java.security.cert.CertificateException { sys.checkClientTrusted(c, a); }
        @Override public void checkServerTrusted(java.security.cert.X509Certificate[] chain, String authType) throws java.security.cert.CertificateException {
            java.util.List<java.security.cert.X509Certificate> path = ext.checkServerTrusted(chain, authType, SB_HOST);
            if (System.currentTimeMillis() > PIN_UNTIL) return;
            if (path != null) for (java.security.cert.X509Certificate x : path) if (PINS.contains(spki(x))) return;
            throw new java.security.cert.CertificateException("Pin verification failed: " + SB_HOST);
        }
        @Override public java.security.cert.X509Certificate[] getAcceptedIssuers() { return sys.getAcceptedIssuers(); }
    }

    static String spki(java.security.cert.X509Certificate x) {
        try {
            byte[] h = java.security.MessageDigest.getInstance("SHA-256").digest(x.getPublicKey().getEncoded());
            return android.util.Base64.encodeToString(h, android.util.Base64.NO_WRAP);
        } catch (Exception e) { return ""; }
    }

    public static Res http(String method, String url, String ctype, byte[] body, String[][] headers) throws Exception {
        if (Guard.bad) throw new ApiError(0, "APP_TAMPERED");     // 🔒 app không chính thức → không gửi gì lên máy chủ
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        if (url.startsWith(SB + "/") && c instanceof javax.net.ssl.HttpsURLConnection) {     // 🔒 máy chủ tiền → kết nối có ghim
            javax.net.ssl.SSLSocketFactory f = sbSsl();
            if (f != null) ((javax.net.ssl.HttpsURLConnection) c).setSSLSocketFactory(f);
        }
        c.setConnectTimeout(15000);
        c.setReadTimeout(120000);
        c.setRequestMethod(method);
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("User-Agent", "BlueRobloxApp/" + version);
        if (DEV != null && url.startsWith(SB)) c.setRequestProperty("x-cb-dev", DEV);       // chỉ gửi cho Supabase
        if (headers != null) for (String[] h : headers) if (h[1] != null) c.setRequestProperty(h[0], h[1]);
        if (body != null) {
            c.setDoOutput(true);
            if (ctype != null) c.setRequestProperty("Content-Type", ctype);
            c.setFixedLengthStreamingMode(body.length);
            try (OutputStream o = c.getOutputStream()) { o.write(body); }
        }
        Res r = new Res();
        r.code = c.getResponseCode();
        InputStream in = r.code >= 400 ? c.getErrorStream() : c.getInputStream();
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        if (in != null) {
            byte[] buf = new byte[16384]; int n;
            while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
            in.close();
        }
        r.body = bo.toByteArray();
        r.cookie = c.getHeaderField("Set-Cookie");
        c.disconnect();
        return r;
    }

    private static byte[] js(JSONObject o) { return o.toString().getBytes(StandardCharsets.UTF_8); }

    private static String errorText(Res r) {
        try {
            JSONObject o = new JSONObject(r.text());
            for (String k : new String[]{"error_description", "msg", "message", "error"}) {
                String v = o.optString(k, "");
                if (!v.isEmpty()) return v;
            }
        } catch (Exception ignored) { }
        return "Lỗi " + r.code;
    }

    // ---------------- Đăng nhập ----------------
    private static void saveSession(JSONObject o) {
        access = o.optString("access_token", "");
        refresh = o.optString("refresh_token", refresh);
        expiresAt = System.currentTimeMillis() + o.optLong("expires_in", 3600) * 1000L - 60000L;
        JSONObject u = o.optJSONObject("user");
        if (u != null) { uid = u.optString("id", uid); email = u.optString("email", email); }
        prefs.edit().putString("access", access).putString("refresh", refresh).putString("uid", uid)
                .putString("email", email).putLong("exp", expiresAt).apply();
    }

    public static void logout() {
        access = refresh = uid = email = ""; expiresAt = 0;
        if (prefs != null) prefs.edit().clear().apply();
    }

    public static void login(String mail, String pass) throws Exception {
        JSONObject b = new JSONObject().put("email", mail).put("password", pass);
        Res r = http("POST", SB + "/auth/v1/token?grant_type=password", "application/json", js(b), new String[][]{{"apikey", KEY}});
        if (r.code != 200) throw new ApiError(r.code, errorText(r));
        saveSession(new JSONObject(r.text()));
    }

    /** Đăng ký. Trả về true nếu đăng nhập luôn được, false nếu phải xác nhận email trước. */
    public static boolean signup(String user, String mail, String pass) throws Exception {
        Object ok = rpcAnon("username_available", new JSONObject().put("p_username", user));
        if (Boolean.FALSE.equals(ok)) throw new ApiError(400, "USERNAME_TAKEN");
        JSONObject b = new JSONObject().put("email", mail).put("password", pass)
                .put("data", new JSONObject().put("username", user));
        Res r = http("POST", SB + "/auth/v1/signup?redirect_to=" + URLEncoder.encode(WEB, "UTF-8"), "application/json", js(b), new String[][]{{"apikey", KEY}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        JSONObject o = new JSONObject(r.text());
        if (o.has("access_token")) { saveSession(o); return true; }
        return false;
    }

    public static void recover(String mail) throws Exception {
        Res r = http("POST", SB + "/auth/v1/recover?redirect_to=" + URLEncoder.encode(WEB, "UTF-8"), "application/json",
                js(new JSONObject().put("email", mail)), new String[][]{{"apikey", KEY}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
    }

    /** Lấy mã truy cập còn hạn (tự làm mới khi sắp hết). */
    public static synchronized String token() throws Exception {
        if (!access.isEmpty() && System.currentTimeMillis() < expiresAt) return access;
        if (refresh.isEmpty()) throw new ApiError(401, "NOT_LOGGED_IN");
        Res r = http("POST", SB + "/auth/v1/token?grant_type=refresh_token", "application/json",
                js(new JSONObject().put("refresh_token", refresh)), new String[][]{{"apikey", KEY}});
        if (r.code != 200) {
            if (r.code == 400 || r.code == 401) { logout(); throw new ApiError(401, "SESSION_EXPIRED"); }
            throw new ApiError(r.code, errorText(r));
        }
        saveSession(new JSONObject(r.text()));
        return access;
    }

    // ---------------- Dữ liệu (REST + RPC) ----------------
    public static Object get(String path) throws Exception {
        Res r = http("GET", SB + "/rest/v1/" + path, null, null,
                new String[][]{{"apikey", KEY}, {"Authorization", "Bearer " + token()}});
        if (r.code == 401) { expiresAt = 0; r = http("GET", SB + "/rest/v1/" + path, null, null, new String[][]{{"apikey", KEY}, {"Authorization", "Bearer " + token()}}); }
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        String t = r.text().trim();
        return t.startsWith("[") ? new JSONArray(t) : new JSONObject(t);
    }

    public static Object rpc(String fn, JSONObject args) throws Exception {
        Res r = http("POST", SB + "/rest/v1/rpc/" + fn, "application/json", js(args),
                new String[][]{{"apikey", KEY}, {"Authorization", "Bearer " + token()}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return parse(r.text());
    }

    public static Object rpcAnon(String fn, JSONObject args) throws Exception {
        Res r = http("POST", SB + "/rest/v1/rpc/" + fn, "application/json", js(args), new String[][]{{"apikey", KEY}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return parse(r.text());
    }

    private static Object parse(String t) throws Exception {
        t = t.trim();
        if (t.isEmpty() || t.equals("null")) return null;
        if (t.startsWith("{")) return new JSONObject(t);
        if (t.startsWith("[")) return new JSONArray(t);
        if (t.equals("true")) return Boolean.TRUE;
        if (t.equals("false")) return Boolean.FALSE;
        if (t.startsWith("\"")) return new JSONArray("[" + t + "]").getString(0);
        try { return Double.parseDouble(t); } catch (Exception e) { return t; }
    }

    public static JSONObject profile() throws Exception {
        JSONArray a = (JSONArray) get("profiles?id=eq." + uid + "&select=username,email,balance,ctv_status,ctv_discount,locked,role");
        return a.length() > 0 ? a.getJSONObject(0) : new JSONObject();
    }

    /** Máy của tôi + máy người khác chia sẻ cho tôi (có "shared": true, "owner_name", "share_id"). */
    public static JSONArray phones() throws Exception {
        JSONArray own = (JSONArray) get("cloud_phones?user_id=eq." + uid + "&status=in.(active,pending,expired,error)&order=created_at.asc&select=*");
        try {
            Object sh = rpc("cp_shared_with_me", new JSONObject());
            if (sh instanceof JSONArray) {
                JSONArray s = (JSONArray) sh;
                for (int i = 0; i < s.length(); i++) own.put(s.getJSONObject(i));
            }
        } catch (Exception ignored) { }        // máy chủ chưa chạy SQL v9 → bỏ qua
        return own;
    }

    public static JSONObject pricing() throws Exception {
        JSONArray a = (JSONArray) get("cloudphone_pricing?id=eq.1&select=*");
        return a.length() > 0 ? a.getJSONObject(0) : new JSONObject();
    }

    public static JSONObject status() {
        try { Object o = rpc("cloudphone_status", new JSONObject()); return o instanceof JSONObject ? (JSONObject) o : new JSONObject(); }
        catch (Exception e) { return new JSONObject(); }
    }

    // ---------------- Máy chủ điện thoại (cpapi) ----------------
    public static JSONObject cp(String method, String path, JSONObject body) throws Exception {
        Res r = http(method, CPAPI + "/" + path, "application/json", body == null ? null : js(body),
                new String[][]{{"Authorization", "Bearer " + token()}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        String t = r.text().trim();
        return t.startsWith("{") ? new JSONObject(t) : new JSONObject();
    }

    public static byte[] cpBytes(String path) throws Exception {
        Res r = http("GET", CPAPI + "/" + path, null, null, new String[][]{{"Authorization", "Bearer " + token()}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return r.body;
    }

    public static JSONObject cpUpload(String path, byte[] chunk) throws Exception {
        Res r = http("POST", CPAPI + "/" + path, "application/octet-stream", chunk, new String[][]{{"Authorization", "Bearer " + token()}});
        JSONObject o;
        try { o = new JSONObject(r.text()); } catch (Exception e) { o = new JSONObject(); }
        if (r.code == 409 && o.has("size")) return o;
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return o;
    }

    // ---------------- cpapi trên máy chủ đang giữ máy (stream.api của cloudphone_endpoint) ----------------
    /** Gốc cpapi: base = stream.api (VD https://phone.cloudblue.vn); rỗng / không phải https → máy chủ mặc định. */
    public static String cpRoot(String base) {
        String b = base == null ? "" : base.trim();
        if (!b.startsWith("https://")) b = PHONE;
        while (b.endsWith("/")) b = b.substring(0, b.length() - 1);
        return b.endsWith("/cpapi") ? b : b + "/cpapi";
    }

    // ---- đường THẲNG tới máy chủ cho công cụ máy (cùng cổng TLS với phát hình, ghim chứng chỉ) — không cần tên miền / Cloudflare ----
    private static final java.util.Map<String, JSONObject> DIRECT = new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.Map<String, String> GOOD = new java.util.concurrent.ConcurrentHashMap<>();

    /** Màn điều khiển gọi khi đọc cloudphone_endpoint: base = stream.api, st = stream {direct:[{host,port,lan}], cert}. */
    public static void direct(String base, JSONObject st) {
        if (st != null && st.optString("cert", "").replace(":", "").length() >= 32) DIRECT.put(base == null ? "" : base, st);
    }

    private static final class RouteDown extends java.io.IOException { RouteDown(Exception e) { super(e); } }

    /** Chỉ nhận đúng chứng chỉ có SHA-256 (DER) = stream.cert (máy chủ tự ký). */
    private static final class Pin implements javax.net.ssl.X509TrustManager {
        private final String want;
        Pin(String hex) { want = hex.trim().toLowerCase(java.util.Locale.ROOT).replace(":", ""); }
        @Override public void checkClientTrusted(java.security.cert.X509Certificate[] c, String a) throws java.security.cert.CertificateException {
            throw new java.security.cert.CertificateException("no client certs");
        }
        @Override public void checkServerTrusted(java.security.cert.X509Certificate[] c, String a) throws java.security.cert.CertificateException {
            if (c == null || c.length == 0) throw new java.security.cert.CertificateException("no server cert");
            try {
                byte[] d = java.security.MessageDigest.getInstance("SHA-256").digest(c[0].getEncoded());
                StringBuilder sb = new StringBuilder();
                for (byte x : d) sb.append(String.format(java.util.Locale.ROOT, "%02x", x));
                if (!sb.toString().equals(want)) throw new java.security.cert.CertificateException("wrong server cert");
            } catch (java.security.NoSuchAlgorithmException e) { throw new java.security.cert.CertificateException(e); }
        }
        @Override public java.security.cert.X509Certificate[] getAcceptedIssuers() { return new java.security.cert.X509Certificate[0]; }
    }

    private static Res pinned(String url, String cert, int connectMs, String method, String ctype, byte[] body, String[][] headers) throws Exception {
        if (Guard.bad) throw new ApiError(0, "APP_TAMPERED");
        javax.net.ssl.HttpsURLConnection c = (javax.net.ssl.HttpsURLConnection) new URL(url).openConnection();
        javax.net.ssl.SSLContext ctx = javax.net.ssl.SSLContext.getInstance("TLS");
        ctx.init(null, new javax.net.ssl.TrustManager[]{new Pin(cert)}, null);
        c.setSSLSocketFactory(ctx.getSocketFactory());
        c.setHostnameVerifier((h, s) -> true);           // đã ghim đúng chứng chỉ bằng SHA-256 → không cần tên miền
        c.setConnectTimeout(connectMs);
        c.setReadTimeout(300000);
        c.setRequestMethod(method);
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("Connection", "close");
        c.setRequestProperty("User-Agent", "BlueRobloxApp/" + version);
        if (headers != null) for (String[] h : headers) if (h[1] != null) c.setRequestProperty(h[0], h[1]);
        if (body != null) {
            c.setDoOutput(true);
            if (ctype != null) c.setRequestProperty("Content-Type", ctype);
            c.setFixedLengthStreamingMode(body.length);
        }
        try { c.connect(); } catch (java.io.IOException e) { c.disconnect(); throw new RouteDown(e); }   // chưa gửi gì → thử đường khác được
        try {
            if (body != null) try (OutputStream o = c.getOutputStream()) { o.write(body); }
            Res r = new Res();
            r.code = c.getResponseCode();
            InputStream in = r.code >= 400 ? c.getErrorStream() : c.getInputStream();
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            if (in != null) {
                byte[] buf = new byte[16384]; int n;
                while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
                in.close();
            }
            r.body = bo.toByteArray();
            return r;
        } finally { c.disconnect(); }
    }

    /** Gọi cpapi: thử đường thẳng (mạng nhà trước, rồi IP ngoài) → không được mới qua tên miền của máy chủ. */
    private static Res cpHttp(String base, String method, String path, String ctype, byte[] body) throws Exception {
        String[][] h = {{"Authorization", "Bearer " + token()}};
        String key = base == null ? "" : base;
        JSONObject st = DIRECT.get(key);
        if (st != null) {
            JSONArray d = st.optJSONArray("direct");
            java.util.List<JSONObject> rs = new java.util.ArrayList<>();
            if (d != null) for (int i = 0; i < d.length(); i++) { JSONObject x = d.optJSONObject(i); if (x != null && !x.optString("host").isEmpty()) rs.add(x); }
            java.util.Collections.sort(rs, (a, b) -> {
                String g = GOOD.get(key);
                int ga = (a.optString("host") + ":" + a.optInt("port")).equals(g) ? 0 : 1, gb = (b.optString("host") + ":" + b.optInt("port")).equals(g) ? 0 : 1;
                if (ga != gb) return ga - gb;
                return (a.optBoolean("lan") ? 0 : 1) - (b.optBoolean("lan") ? 0 : 1);
            });
            for (JSONObject x : rs) {
                String hp = x.optString("host") + ":" + x.optInt("port");
                try {
                    Res r = pinned("https://" + hp + "/cpapi/" + path, st.optString("cert"), x.optBoolean("lan") ? 900 : 4000, method, ctype, body, h);
                    GOOD.put(key, hp);
                    return r;
                } catch (RouteDown e) { /* đường này chưa nối được → thử đường sau */ }
            }
        }
        return http(method, cpRoot(base) + "/" + path, ctype, body, h);
    }

    public static JSONObject cpAt(String base, String method, String path, JSONObject body) throws Exception {
        Res r = cpHttp(base, method, path, "application/json", body == null ? null : js(body));
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        String t = r.text().trim();
        return t.startsWith("{") ? new JSONObject(t) : new JSONObject();
    }

    public static byte[] cpBytesAt(String base, String path) throws Exception {
        Res r = cpHttp(base, "GET", path, null, null);
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return r.body;
    }

    public static JSONObject cpUploadAt(String base, String path, byte[] chunk) throws Exception {
        Res r = cpHttp(base, "POST", path, "application/octet-stream", chunk);
        JSONObject o;
        try { o = new JSONObject(r.text()); } catch (Exception e) { o = new JSONObject(); }
        if (r.code == 409 && o.has("size")) return o;
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return o;
    }

    /** Mở phiên điều khiển: lấy cookie cho trình phát hình. */
    public static String cpSession() throws Exception {
        Res r = http("POST", CPAPI + "/session", "application/json", "{}".getBytes(StandardCharsets.UTF_8),
                new String[][]{{"Authorization", "Bearer " + token()}});
        if (r.code >= 300) throw new ApiError(r.code, errorText(r));
        return r.cookie;
    }

    /** Lỗi do CHỨNG CHỈ (bị chặn / sửa giữa đường, chứng chỉ lạ, sai giờ máy) — không tính lỗi mạng chập chờn thông thường. */
    private static boolean certProblem(Throwable e) {
        int n = 0;
        for (Throwable t = e; t != null && n < 8; t = t.getCause(), n++) {
            if (t instanceof java.security.cert.CertificateException || t instanceof java.security.cert.CertPathValidatorException
                    || t instanceof javax.net.ssl.SSLPeerUnverifiedException) return true;
            String s = t.getMessage();
            if (s != null && (s.contains("Pin verification failed") || s.contains("Trust anchor") || s.contains("CertPathValidator"))) return true;
        }
        return false;
    }

    // ---------------- Lỗi dễ hiểu ----------------
    public static String friendly(Exception e) {
        String m = e.getMessage() == null ? "" : e.getMessage();
        if (m.contains("APP_OUTDATED")) {
            outdated = true;
            Runnable r = onOutdated;
            if (r != null) MAIN.post(r);
            return Ui.L("Bản app này đã cũ — phải cập nhật bản mới nhất mới dùng tiếp được.", "This app version is outdated — update to the latest version to continue.");
        }
        if (m.contains("APP_TAMPERED"))
            return Ui.L("⛔ App này đã bị sửa, không phải bản chính thức. Gỡ ra rồi tải bản chính thức tại " + webHost() + ".",
                        "⛔ This app has been modified. Uninstall it and get the official app from " + webHost() + ".");
        // 🔒 1.115 ghim chứng chỉ (res/xml/network_security_config.xml): có app chặn / sửa dữ liệu mạng → kết nối bị từ chối
        if (certProblem(e))
            return Ui.L("🔒 Kết nối không an toàn nên app đã chặn: có app đang chặn / sửa dữ liệu mạng (VPN lọc HTTPS, app bắt gói tin, chứng chỉ lạ) hoặc giờ trên máy bị sai. Tắt app đó / chỉnh lại giờ rồi thử lại.",
                        "🔒 Insecure connection blocked: an app is intercepting your traffic (HTTPS-filtering VPN, packet capture, unknown certificate) or your clock is wrong. Turn it off / fix the time and try again.");
        if (e instanceof java.net.UnknownHostException || e instanceof java.net.ConnectException)
            return Ui.L("Không có kết nối mạng.", "No internet connection.");
        if (e instanceof java.net.SocketTimeoutException) return Ui.L("Mạng chậm, thử lại.", "Network timeout, try again.");
        String[][] map = {
                // mã tặng máy (SQL v23) — đặt TRƯỚC "TOO_MANY" để PROMO_TOO_MANY không bị hiểu nhầm
                {"PROMO_TOO_MANY", "Bạn nhập sai mã quá nhiều lần — thử lại sau 10 phút.", "Too many wrong codes — try again in 10 minutes."},
                {"PROMO_INVALID", "Mã không đúng hoặc đã bị tắt.", "Wrong or disabled code."},
                {"PROMO_EXPIRED", "Mã đã hết hạn.", "This code has expired."},
                {"PROMO_NOT_STARTED", "Mã chưa đến ngày sử dụng.", "This code isn't active yet."},
                {"PROMO_USED_UP", "Mã này đã được dùng rồi.", "This code has already been used."},
                {"PROMO_IS_DISCOUNT", PLAY ? "Đây là mã giảm giá, không dùng để nhận máy được." : "Đây là mã giảm giá — nhập ở ô \"🏷️ Mã giảm giá\" khi thuê / gia hạn / nâng cấp máy.", PLAY ? "This is a discount code — it can't be used to get a phone." : "This is a discount code — enter it in the \"🏷️ Discount code\" box when you rent, renew or upgrade."},
                {"PROMO_EMPTY", "Hãy nhập mã.", "Enter a code."},
                {"PROMO_USER_LIMIT", "Bạn đã dùng hết số lượt của mã này.", "You've used this code the maximum number of times."},
                {"PROMO_SCOPE", "Mã này không áp dụng cho loại đơn này.", "This code doesn't apply to this kind of order."},
                {"PROMO_MIN_ORDER", "Đơn chưa đạt giá trị tối thiểu để dùng mã này.", "Your order is below this code's minimum."},
                {"PROMO_IS_GIFT", "Đây là mã TẶNG MÁY — nhập ở nút \"🎟 Nhập mã\" trong Máy của tôi.", "This is a gift-phone code — use \"🎟 Enter code\" in My phones."},
                {"PROMO_NOT_FOR_FREE", "Máy miễn phí không dùng mã giảm giá được.", "Discount codes can't be used on free phones."},
                {"PROMO_CTX", "Chọn cấu hình / số ngày trước rồi bấm Áp dụng.", "Choose the setup / days first, then Apply."},
                // 🛡️ bảo mật (SQL v29) — đặt TRƯỚC các mã ngắn để khớp đúng
                {"BLUE_DAY_CAP", "Hôm nay bạn đã nhận đủ Blue tối đa — mai quay lại nhé.", "You've reached today's Blue limit — come back tomorrow."},
                {"BLUE_HOLD", "Blue của bạn đang được tạm giữ để kiểm tra — liên hệ hỗ trợ.", "Your Blue is on hold for review — contact support."},
                {"BLUE_NEW_ACCOUNT", "Tài khoản mới — sau 24 giờ mới tích Blue được.", "New account — you can earn Blue after 24 hours."},
                {"MONEY_GUARD", "Bị chặn: không được tự cộng tiền.", "Blocked: you can't add money to yourself."},
                {"BLUE_GUARD", "Bị chặn: Blue chỉ đổi qua sổ Blue.", "Blocked."},
                {"MAX_AMOUNT", "Số tiền quá lớn.", "Amount too large."},
                {"banned", "⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng (gian lận / cày clone / lợi dụng lỗi). Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.", "⛔ This account is banned for breaking the terms of use. If this is a mistake, contact support with your username."},
                // 💎 Tích Blue (SQL v27)
                {"BLUE_DONE", "Hôm nay bạn đã điểm danh rồi — quay lại ngày mai nhé.", "You've already checked in today — come back tomorrow."},
                {"BLUE_IP_LIMIT", "Mạng (wifi / 4G) này đã đủ số tài khoản nhận Blue hôm nay — mai thử lại nhé.", "Enough accounts on this network have claimed Blue today — try tomorrow."},
                {"BLUE_NEED_TOPUP", "Nạp tiền từ 10.000đ để mở khoá trả bằng Blue (Blue vẫn được tích bình thường).", "Top up to unlock paying with Blue."},
                {"BLUE_EMPTY", "Bạn chưa có Blue để trả.", "You don't have any Blue yet."},
                {"BLUE_NOT_FOR_FREE", "Máy miễn phí không trả bằng Blue được.", "Free phones can't be paid with Blue."},
                {"BLUE_OFF", "Tích Blue đang tạm tắt.", "Blue rewards are paused."},
                {"TASK_DONE", "Hôm nay bạn đã nhận nhiệm vụ này rồi.", "You've already claimed this mission today."},
                {"TASK_NOT_YET", "Chưa xong nhiệm vụ — làm xong rồi bấm nhận nhé.", "Mission not done yet — finish it, then claim."},
                {"TASK_OFF", "Nhiệm vụ này đang tạm tắt.", "This mission is paused."},
                {"BAD_TASK", "Nhiệm vụ không hợp lệ.", "Unknown mission."},
                // đổi Android (SQL v24)
                {"SWITCHING", "Máy đang đổi Android — chờ máy mới tạo xong (2–5 phút).", "This phone is switching Android — wait for the new phone (2–5 min)."},
                {"SWITCH_EXPIRING", "Máy còn dưới 30 phút — gia hạn trước rồi hãy đổi Android.", "Less than 30 minutes left — renew first, then switch Android."},
                {"SWITCH_BUSY", "Máy đang nâng cấp / gia hạn — chờ 1–2 phút rồi đổi Android.", "An upgrade or renewal is in progress — wait 1–2 minutes, then switch."},
                {"SWITCH_SAME", "Máy đang chạy bản Android này rồi.", "The phone already runs this Android version."},
                {"SWITCH_LIMIT", "Mỗi tài khoản đổi Android tối đa 3 lần trong 24 giờ.", "You can switch Android up to 3 times per 24 hours."},
                {"cloudphone_switch_android", "Máy chủ chưa bật tính năng đổi Android.", "Switching Android isn't enabled on the server yet."},
                // giới thiệu bạn bè (SQL v24)
                {"REF_ALREADY", "Tài khoản đã nhận lời mời trước đó.", "This account has already accepted an invite."},
                {"REF_EMPTY", "Hãy nhập mã mời.", "Enter the invite code."},
                {"REF_INVALID", "Mã mời không đúng.", "Invalid invite code."},
                {"REF_SELF", "Không thể tự mời chính mình.", "You can't invite yourself."},
                {"REF_TOO_LATE", "Chỉ tài khoản mới (tạo trong 7 ngày, chưa nạp tiền) mới nhận lời mời.", "Only new accounts (under 7 days old, no top-ups yet) can accept an invite."},
                {"promo_redeem_gift", "Máy chủ chưa bật mã tặng máy.", "Gift codes aren't enabled yet."},
                {"cp_share_stop", "Máy chủ chưa hỗ trợ tắt chia sẻ — thu hồi từng mã bên dưới.", "Turning sharing off isn't available yet — revoke codes one by one."},
                {"Invalid login credentials", "Sai email hoặc mật khẩu.", "Wrong email or password."},
                {"Email not confirmed", "Email chưa xác nhận — mở hộp thư để xác nhận.", "Please confirm your email first."},
                {"USERNAME_TAKEN", "Tên đăng nhập đã có người dùng.", "This username is taken."},
                {"already registered", "Email này đã đăng ký.", "This email is already registered."},
                {"Password should be", "Mật khẩu phải từ 6 ký tự.", "Password must be at least 6 characters."},
                {"SESSION_EXPIRED", "Phiên đăng nhập hết hạn, hãy đăng nhập lại.", "Session expired, please log in again."},
                {"NOT_LOGGED_IN", "Hãy đăng nhập.", "Please log in."},
                {"INSUFFICIENT_BALANCE", "Số dư không đủ.", "Not enough balance."},
                {"MIN_AMOUNT", "Số tiền thấp hơn mức nạp tối thiểu.", "The amount is below the minimum top-up."},
                {"TOO_MANY", "Bạn có quá nhiều lệnh nạp đang chờ. Thử lại sau ít phút.", "Too many pending top-ups. Try again in a few minutes."},
                {"FREE_NO_RENEW", "Máy miễn phí không gia hạn được — hãy thuê máy mới.", "Free phones can't be renewed — rent a new one."},
                {"FREE_NO_UPGRADE", "Máy miễn phí không nâng cấp được.", "Free phones can't be upgraded."},
                {"UPGRADE_PENDING", "Máy đang được nâng cấp, đợi khoảng 1 phút.", "An upgrade is in progress, wait about a minute."},
                {"BAD_UPGRADE", "Cấu hình nâng cấp không hợp lệ.", "Invalid upgrade."},
                {"FREE_ONE", "Máy miễn phí chỉ nhận 1 máy mỗi lần.", "Only one free phone at a time."},
                {"NO_PHONE", "Không tìm thấy máy (hoặc máy không phải của bạn).", "Phone not found (or not yours)."},
                {"MAINTENANCE", "Hệ thống đang bảo trì.", "Under maintenance."},
                {"OUT_OF_CAPACITY", "Máy chủ đã hết chỗ cho cấu hình này.", "Server is full for this configuration."},
                {"MAX_PER_USER", "Tài khoản đã đủ số máy cho phép — gia hạn hoặc xoá máy cũ để thuê máy khác.", "You already have the maximum number of phones."},
                {"FREE_USED", "Mỗi tài khoản chỉ được dùng thử 1 máy miễn phí — bạn đã nhận rồi.", "Only one free phone per account — already claimed."},
                {"FREE_OFF", "Ưu đãi miễn phí đã kết thúc.", "The free offer has ended."},
                {"FREE_LIMIT", "Máy miễn phí vượt cấu hình tối đa cho phép.", "The free phone exceeds the allowed configuration."},
                {"BAD_ANDROID", "Phiên bản Android này đang tạm ngưng — chọn bản khác.", "This Android version isn't available — pick another."},
                {"SERVER_OFFLINE", "Máy chủ điện thoại đang tạm ngưng.", "Phone server is offline."},
                {"PHONE_GONE", "Máy đã bị xoá vì hết hạn quá 30 phút.", "This phone was deleted after expiring."},
                {"PHONE_LOCKED", "Máy đang bị khoá.", "This phone is locked."},
                {"LOCKED", "⛔ Tài khoản đã bị cấm do vi phạm điều khoản sử dụng. Nếu là nhầm lẫn, liên hệ hỗ trợ kèm tên đăng nhập.", "⛔ This account is banned for breaking the terms of use. If this is a mistake, contact support with your username."},
                {"BAD_RAM", "RAM ngoài giới hạn.", "RAM out of range."},
                {"BAD_CPU", "CPU ngoài giới hạn.", "CPU out of range."},
                {"BAD_DAYS", "Số ngày ngoài giới hạn.", "Days out of range."},
                {"BAD_FPS", "FPS ngoài giới hạn.", "FPS out of range."},
                {"FPS_TOO_HIGH", "Máy dưới 4 nhân chỉ chọn tối đa 60 FPS.", "Under 4 cores: max 60 FPS."},
                {"BAD_RES", "Độ phân giải không hợp lệ.", "Invalid resolution."},
                {"BAD_QTY", "Số lượng không hợp lệ.", "Invalid quantity."},
                {"OUT_OF_STOCK", "Đã hết hàng.", "Sold out."},
                {"BAD_CODE", "Mã không đúng, đã bị huỷ hoặc đã hết hạn.", "Wrong, cancelled or expired code."},
                {"CODE_USED", "Mã này đã có người dùng rồi.", "This code has already been used."},
                {"OWN_PHONE", "Đây là máy của chính bạn.", "This is your own phone."},
                {"ALREADY_SHARED", "Bạn đã được chia sẻ máy này rồi.", "This phone is already shared with you."},
                {"SHARE_LIMIT", "Máy đã có quá nhiều mã chia sẻ (tối đa 20).", "Too many share codes (max 20)."},
                {"PHONE_NOT_ACTIVE", "Máy phải đang chạy mới làm được việc này.", "The phone must be running to do this."},
                {"NOT_ALLOWED", "Bạn không có quyền làm việc này.", "Not allowed."},
                {"cp_share", "Tính năng chia sẻ chưa bật trên máy chủ.", "Sharing is not enabled yet."},
        };
        for (String[] k : map) if (m.contains(k[0])) return Ui.L(k[1], k[2]);
        return m.isEmpty() ? Ui.L("Có lỗi, thử lại.", "Something went wrong.") : m;
    }
}
