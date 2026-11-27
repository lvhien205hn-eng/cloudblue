// Thử blueroblox-site/api/px-check.js (27/11h — 🔎 kiểm tra proxy cho khách): proxy SOCKS5 / HTTP giả + "trang trả IP" HTTPS giả
// (chứng chỉ tự ký cho api64.ipify.org / api.ip.sb) chạy trên 127.0.0.1 → không gọi ra ngoài. Cần openssl.
//   node test_api_pxcheck.js <đường dẫn tới px-check.js>
const path = require("path"), fs = require("fs"), os = require("os"), net = require("net"), https = require("https"), cp = require("child_process");
const src = process.argv[2];
if (!src || !fs.existsSync(src)) { console.error("Cách dùng: node test_api_pxcheck.js <px-check.js>"); process.exit(2); }
process.env.SUPABASE_URL = "https://sb.test"; process.env.SUPABASE_SERVICE_ROLE_KEY = "SERVICE";
let OK = 0, FAIL = 0;
const ck = (name, cond, extra) => { if (cond) { OK++; console.log("  ✓", name); } else { FAIL++; console.log("  ✗", name, "→", JSON.stringify(extra === undefined ? null : extra).slice(0, 700)); } };

// ---------------------------------------------------------------- fetch giả (Supabase: đăng nhập + rl_hit; geo)
let F = { rl: true, calls: [] };
global.fetch = async (url, opt = {}) => {
  const h = opt.headers || {}; F.calls.push(url);
  const res = (status, b) => ({ ok: status < 300, status, json: async () => b, text: async () => JSON.stringify(b) });
  if (url === "https://sb.test/auth/v1/user") return h.Authorization === "Bearer a.b.c" ? res(200, { id: "u1", email: "k@x.vn" }) : res(401, {});
  if (url.startsWith("https://sb.test/rest/v1/profiles?")) return res(200, [{ username: "khach", email: "k@x.vn", role: "user", locked: false }]);
  if (url === "https://sb.test/rest/v1/rpc/rl_hit") return res(200, F.rl);
  if (url === "https://sb.test/rest/v1/px_settings?select=pub_host,pub_port&id=eq.1") return F.noSql ? res(404, { code: "PGRST205" }) : res(200, [{ pub_host: null, pub_port: 18899 }]);
  if (url === "https://sb.test/rest/v1/vm_hosts?select=pub_ip,pub4:metrics->px->>pub4&metrics->px=not.is.null") return res(200, [{ pub_ip: "203.0.113.50", pub4: "203.0.113.51" }]);
  if (url.startsWith("https://sb.test/rest/v1/px_proxies?select=username,password,expires_at,status&username=in.(")) {
    const want = decodeURIComponent(url.split("username=in.(")[1].replace(/\)$/, "")).split(",");
    const all = [{ username: "pxgood0001", password: "goodpass", expires_at: new Date(Date.now() + 864e5).toISOString(), status: "active" },
      { username: "pxold00001", password: "oldpass", expires_at: new Date(Date.now() - 3600e3).toISOString(), status: "active" },
      { username: "pxrev00001", password: "revpass", expires_at: new Date(Date.now() + 864e5).toISOString(), status: "revoked" }];
    return res(200, all.filter(r => want.includes(r.username)));
  }
  if (url.startsWith("https://ipinfo.io/")) throw new Error("không ra mạng trong bộ thử");
  if (url.startsWith("https://api.ip.sb/geoip/")) throw new Error("không ra mạng trong bộ thử");
  return res(404, {});
};
const H = require(path.resolve(src)), T = H._t;

// ---------------------------------------------------------------- chứng chỉ + trang trả IP giả
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pxchk-"));
cp.execFileSync("openssl", ["req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-keyout", path.join(dir, "k.pem"),
  "-out", path.join(dir, "c.pem"), "-days", "1", "-subj", "/CN=pxchk-test", "-addext", "subjectAltName=DNS:api64.ipify.org,DNS:api.ip.sb"], { stdio: "ignore" });
const KEY = fs.readFileSync(path.join(dir, "k.pem")), CERT = fs.readFileSync(path.join(dir, "c.pem"));
let TG = { down: false, hits: [] };
const target = https.createServer({ key: KEY, cert: CERT }, (req, res) => {
  TG.hits.push(req.headers.host + req.url);
  if (req.url === "/?format=json") { if (TG.down) { res.writeHead(503); return res.end("busy"); } res.writeHead(200, { "Content-Type": "application/json" }); return res.end(JSON.stringify({ ip: TG.ip || "198.51.100.7" })); }
  if (req.url === "/ip") { res.writeHead(200, { "Content-Type": "text/plain", "Transfer-Encoding": "chunked" }); res.write("2001:db8:5::"); return res.end("77\n"); }
  res.writeHead(404); res.end();
});

// ---------------------------------------------------------------- proxy giả
const pipeTo = (c, onOk) => { const up = net.connect(target.address().port, "127.0.0.1", () => { onOk(); c.pipe(up); up.pipe(c); }); up.on("error", () => c.destroy()); c.on("error", () => up.destroy()); };
function socksSrv({ user, pass, rep = 0 } = {}) {
  return net.createServer(c => {
    let st = 0, buf = Buffer.alloc(0);
    c.on("error", () => {});
    c.on("data", function on(d) {
      buf = Buffer.concat([buf, d]);
      for (;;) {
        if (st === 0) { if (buf.length < 2 || buf.length < 2 + buf[1]) return; if (buf[0] !== 5) return c.destroy();
          const ms = [...buf.subarray(2, 2 + buf[1])]; buf = buf.subarray(2 + buf[1]);
          if (user) { if (!ms.includes(2)) { c.end(Buffer.from([5, 0xff])); return; } c.write(Buffer.from([5, 2])); st = 1; }
          else { c.write(Buffer.from([5, 0])); st = 2; } continue; }
        if (st === 1) { if (buf.length < 2) return; const ul = buf[1]; if (buf.length < 3 + ul) return; const pl = buf[2 + ul]; if (buf.length < 3 + ul + pl) return;
          const u = buf.subarray(2, 2 + ul).toString(), p = buf.subarray(3 + ul, 3 + ul + pl).toString(); buf = buf.subarray(3 + ul + pl);
          if (u !== user || p !== pass) { c.end(Buffer.from([1, 1])); return; } c.write(Buffer.from([1, 0])); st = 2; continue; }
        if (st === 2) { if (buf.length < 5) return; const hl = buf[4]; if (buf.length < 7 + hl) return; buf = buf.subarray(7 + hl); st = 3;
          c.removeListener("data", on);
          if (rep) { c.end(Buffer.from([5, rep, 0, 1, 0, 0, 0, 0, 0, 0])); return; }
          pipeTo(c, () => c.write(Buffer.from([5, 0, 0, 1, 127, 0, 0, 1, 0, 80]))); return; }
        return;
      }
    });
  });
}
function httpSrv({ user, pass } = {}) {
  return net.createServer(c => {
    let buf = ""; c.on("error", () => {});
    c.on("data", function on(d) {
      buf += d.toString("latin1"); const k = buf.indexOf("\r\n\r\n"); if (k < 0) return;
      c.removeListener("data", on);
      if (!/^CONNECT [^ ]+ HTTP\/1\.1\r\n/.test(buf)) { c.end("HTTP/1.1 400 Bad Request\r\n\r\n"); return; }
      const a = (buf.match(/\r\nProxy-Authorization: Basic ([^\r]+)/i) || [])[1];
      if (user && (!a || Buffer.from(a, "base64").toString() !== `${user}:${pass}`)) { c.end("HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic\r\n\r\n"); return; }
      pipeTo(c, () => c.write("HTTP/1.1 200 Connection established\r\n\r\n"));
    });
  });
}
function dualSrv(cred) {                                                     // như cbpool: 1 cổng, byte đầu 0x05 → SOCKS5, khác → HTTP
  const s5 = socksSrv(cred), h = httpSrv(cred);
  return net.createServer(c => { c.on("error", () => {}); c.once("data", d => { c.pause(); c.unshift(d); (d[0] === 5 ? s5 : h).emit("connection", c); c.resume(); }); });
}
const junkSrv = () => net.createServer(c => { c.on("error", () => {}); c.end("SSH-2.0-OpenSSH_9.6\r\n"); });
const listen = s => new Promise(r => s.listen(0, "127.0.0.1", () => r(s.address().port)));

(async () => {
  await listen(target);
  const P = {
    s5: await listen(socksSrv({ user: "u1", pass: "p1" })), s5open: await listen(socksSrv()), s5deny: await listen(socksSrv({ rep: 2 })),
    http: await listen(httpSrv({ user: "u2", pass: "p:2" })), dual: await listen(dualSrv({ user: "u3", pass: "p3" })), junk: await listen(junkSrv())
  };
  const cs = net.createServer(), closed = await listen(cs); await new Promise(r => cs.close(r));   // mở rồi đóng ngay → cổng đóng
  const OPT = { ...T.PROD, allowPrivate: true, tls: { ca: CERT }, deadline: 4000, conn: 1500, greet: 700 };
  const it = (p, u, w, t) => T.normItem({ h: "127.0.0.1", p, u, w, t });

  console.log("IP nội bộ / dành riêng (không cho nối)");
  for (const a of ["192.168.77.10", "10.1.2.3", "172.20.0.1", "127.0.0.1", "100.64.1.1", "169.254.169.254", "0.0.0.0", "203.0.113.9", "224.0.0.1", "255.255.255.255"])
    ck("chặn " + a, T.badIp(a) === true);
  for (const a of ["::1", "fe80::1", "fc00::5", "fd12:3456::1", "::ffff:127.0.0.1", "::ffff:8.8.8.8", "2001:db8::1", "64:ff9b::808:808", "2002:c0a8:101::1", "ff02::1", "::"])
    ck("chặn " + a, T.badIp(a) === true);
  for (const a of ["8.8.8.8", "1.1.1.1", "14.161.20.5", "113.160.1.1", "2400:cb00:2048:1::5", "2606:4700:4700::1111", "2001:4860:4860::8888"])
    ck("cho phép " + a, T.badIp(a) === false);

  console.log("Chuẩn hoá dòng");
  ck("host:port", JSON.stringify(T.normItem({ h: "Proxy.Example.com", p: 8899 })) === JSON.stringify({ h: "proxy.example.com", p: 8899, u: "", w: "", t: null }));
  ck("[IPv6] bỏ ngoặc", T.normItem({ h: "[2606:4700::1]", p: 1080 }).h === "2606:4700::1");
  ck("cổng 0 / 70000 / chữ → bỏ", !T.normItem({ h: "1.2.3.4", p: 0 }) && !T.normItem({ h: "1.2.3.4", p: 70000 }) && !T.normItem({ h: "1.2.3.4", p: "abc" }));
  ck("host lạ (dấu cách / gạch chéo / @) → bỏ", !T.normItem({ h: "a b", p: 1 }) && !T.normItem({ h: "a/b", p: 1 }) && !T.normItem({ h: "u@h", p: 1 }));
  ck("mật khẩu có xuống dòng (chèn header) → bỏ", !T.normItem({ h: "1.2.3.4", p: 1, u: "a", w: "b\r\nX-Evil: 1" }));
  ck("user / pass > 255 byte → bỏ", !T.normItem({ h: "1.2.3.4", p: 1, u: "x".repeat(256) }));

  console.log("Thử proxy thật trên máy (SOCKS5 / HTTP / cả hai)");
  let r = await T.checkItem(it(P.s5, "u1", "p1"), "socks5", OPT);
  ck("SOCKS5 đúng mật khẩu → LIVE + IP ra + ms", r.live && r.ip === "198.51.100.7" && r.fam === 4 && r.s5.ok && r.ms >= 0 && !r.http, r);
  ck("trang trả IP được gọi qua TLS đúng tên (SNI api64.ipify.org)", TG.hits.some(h => h.startsWith("api64.ipify.org")), TG.hits);
  r = await T.checkItem(it(P.s5, "u1", "sai"), "socks5", OPT);
  ck("SOCKS5 sai mật khẩu → DIE · BAD_AUTH", !r.live && r.err === "BAD_AUTH", r);
  r = await T.checkItem(it(P.s5), "socks5", OPT);
  ck("SOCKS5 đòi mật khẩu mà không nhập → NEED_AUTH", !r.live && r.err === "NEED_AUTH", r);
  r = await T.checkItem(it(P.s5open), "socks5", OPT);
  ck("SOCKS5 không mật khẩu → LIVE", r.live && r.s5.ok, r);
  r = await T.checkItem(it(P.s5deny, "", ""), "socks5", OPT);
  ck("SOCKS5 trả 'không cho phép' → DIE · S5_2", !r.live && r.err === "S5_2", r);
  r = await T.checkItem(it(P.http, "u2", "p:2"), "http", OPT);
  ck("HTTP CONNECT đúng mật khẩu (mật khẩu có ':') → LIVE", r.live && r.http.ok && r.ip === "198.51.100.7", r);
  r = await T.checkItem(it(P.http, "u2", "x"), "http", OPT);
  ck("HTTP sai mật khẩu → BAD_AUTH", !r.live && r.err === "BAD_AUTH", r);
  r = await T.checkItem(it(P.http), "http", OPT);
  ck("HTTP không nhập mật khẩu → NEED_AUTH", !r.live && r.err === "NEED_AUTH", r);
  let t0 = Date.now();
  r = await T.checkItem(it(P.http, "u2", "p:2"), "auto", OPT);
  ck("Tự nhận với proxy chỉ HTTP → LIVE (HTTP ✓, SOCKS5 ✗ 'không phải SOCKS5')", r.live && r.http.ok && !r.s5.ok && r.s5.err === "NOT_SOCKS5", r);
  ck("…không phải đợi hết 4 giây (lời chào SOCKS5 chờ tối đa 0,7 giây)", Date.now() - t0 < 2500, Date.now() - t0);
  r = await T.checkItem(it(P.s5, "u1", "p1"), "auto", OPT);
  ck("Tự nhận với proxy chỉ SOCKS5 → LIVE (SOCKS5 ✓, HTTP ✗)", r.live && r.s5.ok && !r.http.ok && r.http.err === "NOT_HTTP", r);
  r = await T.checkItem(it(P.dual, "u3", "p3"), "auto", OPT);
  ck("Proxy 2 kiểu cùng cổng (như CloudBlue) → SOCKS5 ✓ + HTTP ✓", r.live && r.s5.ok && r.http.ok, r);
  r = await T.checkItem(it(P.dual, "u3", "p3", "http"), "socks5", OPT);
  ck("dòng có http:// → chỉ thử HTTP dù chọn SOCKS5", r.live && r.http && r.http.ok && !r.s5, r);
  r = await T.checkItem(it(P.junk, "a", "b"), "auto", OPT);
  ck("cổng không phải proxy (SSH) → DIE", !r.live && /NOT_SOCKS5|NOT_HTTP/.test(r.err), r);
  r = await T.checkItem(it(closed, "a", "b"), "auto", OPT);
  ck("cổng đóng → REFUSED", !r.live && r.err === "REFUSED", r);
  TG.down = true;
  r = await T.checkItem(it(P.s5, "u1", "p1"), "socks5", OPT);
  ck("trang trả IP chính lỗi → dùng trang dự phòng (api.ip.sb, chunked) → IPv6", r.live && r.ip === "2001:db8:5::77" && r.fam === 6, r);
  TG.down = false;
  r = await T.checkItem(T.normItem({ h: "192.168.77.10", p: 8899, u: "p01", w: "x" }), "auto", T.PROD);
  ck("IP mạng nhà (192.168…) → PRIVATE ngay, không nối", !r.live && r.err === "PRIVATE", r);
  r = await T.checkItem(T.normItem({ h: "proxy.test", p: 8899 }), "auto", { ...T.PROD, lookup: async () => [{ address: "10.0.0.5", family: 4 }] });
  ck("tên miền trỏ về IP nội bộ → PRIVATE", !r.live && r.err === "PRIVATE", r);
  r = await T.checkItem(T.normItem({ h: "khong-co.test", p: 8899 }), "auto", { ...T.PROD, lookup: async () => { throw new Error("ENOTFOUND"); } });
  ck("tên miền không có → DNS", !r.live && r.err === "DNS", r);
  t0 = Date.now();
  const many = await Promise.all(Array.from({ length: 20 }, (_, i) => T.checkItem(it(P.dual, "u3", "p3"), "auto", OPT)));
  ck("20 proxy song song → LIVE cả 20", many.every(x => x.live), many.filter(x => !x.live));
  ck("…trong vài giây", Date.now() - t0 < 4000, Date.now() - t0);
  const res2 = [{ live: true, ip: "198.51.100.7" }, { live: false }, { live: true, ip: "198.51.100.7" }];
  await T.addGeo(res2, async ip => ({ cc: "VN", org: "FPT Telecom", city: "Hanoi" }));
  ck("thêm quốc gia / nhà mạng theo IP ra (gộp IP trùng)", res2[0].cc === "VN" && res2[2].org === "FPT Telecom" && !res2[1].cc, res2);
  ck("respDone: Content-Length đủ → xong không đợi đóng", !!T.respDone(Buffer.from("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"), false));
  ck("respDone: thiếu thân → chờ tiếp", T.respDone(Buffer.from("HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nok"), false) === null);

  console.log("Đường dẫn /api/px-check");
  const call = async (b, auth = "Bearer a.b.c", method = "POST") => {
    const out = {}; const res = { setHeader: (k, v) => (out[k] = v), status(c) { out.code = c; return this; }, json(j) { out.j = j; return this; } };
    await H({ method, headers: auth ? { authorization: auth } : {}, body: b }, res); return out;
  };
  let o = await call({ items: [{ h: "8.8.8.8", p: 1 }] }, "");
  ck("chưa đăng nhập → 401", o.code === 401 && o.j.error === "NOT_LOGGED_IN", o);
  o = await call({ items: [] }, "Bearer a.b.c", "GET");
  ck("GET → 405", o.code === 405, o);
  o = await call({ items: [] });
  ck("danh sách rỗng → 400", o.code === 400, o);
  o = await call({ items: Array.from({ length: 21 }, () => ({ h: "8.8.8.8", p: 1 })) });
  ck("> 20 proxy / lần → 400", o.code === 400 && o.j.error === "BAD_ITEMS", o);
  F.rl = false; o = await call({ items: [{ h: "192.168.77.10", p: 8899 }] }); F.rl = true;
  ck("quá tần suất → 429", o.code === 429 && o.j.error === "SLOW_DOWN", o);
  o = await call(JSON.stringify({ items: [{ h: "192.168.77.10", p: 8899, u: "p01", w: "x" }, { h: "1.2.3.4", p: 0 }, null] }));
  ck("thân dạng chuỗi JSON → 200; IP nhà → PRIVATE; dòng sai → BAD_LINE", o.code === 200 && o.j.ok && o.j.results.length === 3 && o.j.results[0].err === "PRIVATE"
    && o.j.results[1].err === "BAD_LINE" && o.j.results[2].err === "BAD_LINE", o);
  ck("Cache-Control: no-store", o["Cache-Control"] === "no-store", o);

  console.log("Proxy của CloudBlue: trả lời từ cơ sở dữ liệu, không nối tới máy chủ proxy khi chắc chắn hỏng");
  o = await call({ items: [
    { h: "203.0.113.50", p: 18899, u: "pxold00001", w: "oldpass" },     // 0 hết hạn
    { h: "203.0.113.51", p: 18899, u: "pxgood0001", w: "sai" },         // 1 sai mật khẩu (IP pub4)
    { h: "203.0.113.50", p: 18899 },                                     // 2 không nhập user/pass
    { h: "203.0.113.50", p: 18899, u: "pxrev00001", w: "revpass" },     // 3 bị thu hồi
    { h: "203.0.113.50", p: 18899, u: "pxgood0001", w: "goodpass" },    // 4 đúng → thử qua mạng như thường
    { h: "203.0.113.50", p: 8080, u: "pxold00001", w: "oldpass" },      // 5 khác cổng → không phải của mình
    { h: "203.0.113.50", p: 18899, u: "pxnope0001", w: "x" },           // 6 tài khoản không có
    { h: "203.0.113.50", p: 18899, u: "pxold00001", w: "doan-bua" }     // 7 hết hạn nhưng sai mật khẩu → chỉ báo sai mật khẩu (không lộ)
  ] });
  const R = o.j && o.j.results || [];
  ck("hết hạn → EXPIRED (không nối)", R[0] && R[0].err === "EXPIRED" && R[0].own, R[0]);
  ck("sai mật khẩu (nối bằng IP pub4) → BAD_AUTH (không nối)", R[1] && R[1].err === "BAD_AUTH" && R[1].own, R[1]);
  ck("không nhập user / pass → NEED_AUTH (không nối)", R[2] && R[2].err === "NEED_AUTH" && R[2].own, R[2]);
  ck("bị thu hồi → REVOKED", R[3] && R[3].err === "REVOKED" && R[3].own, R[3]);
  ck("tài khoản đúng + còn hạn → thử qua mạng như thường (ở đây IP tài liệu nên PRIVATE)", R[4] && !R[4].own && R[4].err === "PRIVATE", R[4]);
  ck("khác cổng → không coi là proxy của mình", R[5] && !R[5].own, R[5]);
  ck("tài khoản không có trên máy mình → BAD_AUTH", R[6] && R[6].err === "BAD_AUTH" && R[6].own, R[6]);
  ck("hết hạn mà sai mật khẩu → chỉ báo BAD_AUTH (không lộ tài khoản có tồn tại / hết hạn)", R[7] && R[7].err === "BAD_AUTH", R[7]);
  F.noSql = true; o = await call({ items: [{ h: "203.0.113.50", p: 18899, u: "pxold00001", w: "oldpass" }] }); F.noSql = false;
  ck("chưa chạy SQL v63 → bỏ qua phần này, thử như thường", o.code === 200 && o.j.results[0].err === "PRIVATE" && !o.j.results[0].own, o);
  ck("có giới hạn tần suất theo tài khoản + IP (gọi rl_hit 2 lần / lần thử)", F.calls.filter(u => u.endsWith("/rpc/rl_hit")).length >= 2, F.calls);
  ck("mã nguồn không ghi log mật khẩu (không có console.log trong px-check.js)", !/console\.(log|error|warn)\(/.test(fs.readFileSync(src, "utf8")));

  console.log(`\n${OK}/${OK + FAIL} đạt`);
  fs.rmSync(dir, { recursive: true, force: true });
  process.exit(FAIL ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
