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

    public static void init(Context c) {
        PLAY = "vn.cloudblue.app".equals(c.getPackageName());
        if (prefs != null) return;
        prefs = c.getApplicationContext().getSharedPreferences("auth", Context.MODE_PRIVATE);
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

    public static Res http(String method, String url, String ctype, byte[] body, String[][] headers) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(120000);
        c.setRequestMethod(method);
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("User-Agent", "BlueRobloxApp/" + version);
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

    // ---------------- Lỗi dễ hiểu ----------------
    public static String friendly(Exception e) {
        String m = e.getMessage() == null ? "" : e.getMessage();
        if (m.contains("APP_OUTDATED")) {
            outdated = true;
            Runnable r = onOutdated;
            if (r != null) MAIN.post(r);
            return Ui.L("Bản app này đã cũ — phải cập nhật bản mới nhất mới dùng tiếp được.", "This app version is outdated — update to the latest version to continue.");
        }
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
                {"PROMO_IS_DISCOUNT", PLAY ? "Đây là mã giảm giá, không dùng để nhận máy được." : "Đây là mã giảm giá — nhập ở ô \"Mã giảm giá\" khi thanh toán trên web " + webHost() + ".", PLAY ? "This is a discount code — it can't be used to get a phone." : "This is a discount code — enter it at checkout on " + webHost() + "."},
                {"PROMO_EMPTY", "Hãy nhập mã.", "Enter a code."},
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
                {"LOCKED", "Tài khoản bị khoá.", "Account locked."},
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
