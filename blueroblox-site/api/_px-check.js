// 27/11h · 🔎 KIỂM TRA PROXY cho khách (mục Proxy dân cư): khách dán danh sách proxy → máy chủ web thử từng cái qua SOCKS5 / HTTP CONNECT
// rồi vào trang trả IP (api64.ipify.org — có cả IPv4 lẫn IPv6, nên proxy IPv6 không bị báo chết oan như nhiều trang check khác).
//   POST /api/px-check   Header: Authorization: Bearer <mã đăng nhập>
//   (file bắt đầu bằng "_" nên KHÔNG phải 1 hàm API riêng: vercel.json chuyển /api/px-check → /api/notify-admin?px=1, notify-admin.js
//    thấy px=1 thì giao cho file này — gói Vercel đang dùng chỉ cho 12 hàm API, thêm hàm thứ 13 thì cả lần đưa web lên bị từ chối)
//   body: { items: [{ h: "host", p: 8899, u?: "user", w?: "pass", t?: "socks5" | "http" }], mode: "auto" | "socks5" | "http" }
//   → { ok: true, results: [{ live, s5?, http?, ip?, fam?, ms?, cc?, org?, city?, err? }] }      (s5 / http: { ok, ms } hoặc { ok: false, err })
// An toàn: chỉ người đã đăng nhập · tối đa 20 proxy / lần · giới hạn tần suất theo tài khoản + IP · KHÔNG nối tới IP nội bộ / riêng /
// dành riêng (chống dùng máy chủ web dò mạng trong) · trang đích cố định (khách không chọn được) · mật khẩu chỉ dùng để thử, không lưu, không ghi log.
// Proxy CỦA CLOUDBLUE (đúng IP:cổng khách nối) → xem trước trong cơ sở dữ liệu: sai mật khẩu / hết hạn / bị thu hồi thì báo luôn, KHÔNG nối
// tới máy chủ proxy (máy chủ tự chặn IP gõ sai nhiều lần → không để máy kiểm tra bị chặn oan vì vài dòng hết hạn).
const net = require("net"), tls = require("tls"), dns = require("dns").promises;
const { whoAmI, rateLimit, rateLimitKey, body, sb } = require("./_lib");

const MAX_ITEMS = 20;
const UA = "CloudBlue-ProxyCheck/1.0 (+https://cloudblue.vn)";
const PROD = {
  targets: [{ host: "api64.ipify.org", port: 443, path: "/?format=json" }, { host: "api.ip.sb", port: 443, path: "/ip" }],
  allowPrivate: false, tls: {},
  deadline: 7000,          // mỗi proxy (2 kiểu chạy song song) tối đa 7 giây (cả lần gọi < 10 giây — giới hạn mặc định của hàm Vercel)
  conn: 4000,              // nối TCP tới proxy
  greet: 3000              // SOCKS5 không trả lời lời chào trong 3 giây → coi như không phải SOCKS5 (proxy HTTP hay im chờ)
};

// ------------------------------------------------------------------ IP nội bộ / dành riêng → không nối
function v4n(a) { const p = String(a).split(".").map(Number); return (((p[0] << 24) >>> 0) + (p[1] << 16) + (p[2] << 8) + p[3]) >>> 0; }
const V4BAD = [["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8], ["169.254.0.0", 16], ["172.16.0.0", 12], ["192.0.0.0", 24],
  ["192.0.2.0", 24], ["192.88.99.0", 24], ["192.168.0.0", 16], ["198.18.0.0", 15], ["198.51.100.0", 24], ["203.0.113.0", 24], ["224.0.0.0", 4], ["240.0.0.0", 4]];
function bad4(a) { if (!net.isIPv4(a)) return true; const n = v4n(a); return V4BAD.some(([b, m]) => ((n ^ v4n(b)) >>> (32 - m)) === 0); }
function v6words(a) {
  let s = String(a).toLowerCase().split("%")[0];
  const m = s.match(/^(.*:)(\d{1,3}(?:\.\d{1,3}){3})$/);
  if (m) { if (!net.isIPv4(m[2])) return null; const n = v4n(m[2]); s = m[1] + (n >>> 16).toString(16) + ":" + (n & 0xffff).toString(16); }
  const parts = s.split("::"); if (parts.length > 2) return null;
  const L = parts[0] ? parts[0].split(":") : [], R = parts.length === 2 ? (parts[1] ? parts[1].split(":") : []) : null;
  const w = R === null ? L : [...L, ...Array(Math.max(0, 8 - L.length - R.length)).fill("0"), ...R];
  if (w.length !== 8 || w.some(x => !/^[0-9a-f]{1,4}$/.test(x))) return null;
  return w.map(x => parseInt(x, 16));
}
function bad6(a) {
  if (!net.isIPv6(a)) return true;
  const w = v6words(a); if (!w) return true;
  if ((w[0] & 0xe000) !== 0x2000) return true;                                 // chỉ nhận địa chỉ toàn cầu 2000::/3 (loại ::1, fc00::/7, fe80::/10, ::ffff:…)
  if (w[0] === 0x2001 && w[1] < 0x0200) return true;                           // 2001::/23 (Teredo, …)
  if (w[0] === 0x2001 && w[1] === 0x0db8) return true;                         // 2001:db8::/32 tài liệu
  if (w[0] === 0x2002) return true;                                            // 6to4
  if (w[0] === 0x3fff && w[1] < 0x1000) return true;                           // 3fff::/20 tài liệu
  return false;
}
const badIp = a => net.isIPv4(a) ? bad4(a) : bad6(a);

// ------------------------------------------------------------------ chuẩn hoá 1 mục khách gửi
const HOST_RX = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.?$/i;
function normItem(x) {
  if (!x || typeof x !== "object") return null;
  let h = String(x.h == null ? "" : x.h).trim(); if (h.startsWith("[") && h.endsWith("]")) h = h.slice(1, -1);
  const p = Number(x.p), u = x.u == null ? "" : String(x.u), w = x.w == null ? "" : String(x.w);
  if (!h || !(net.isIP(h) || HOST_RX.test(h))) return null;
  if (!Number.isInteger(p) || p < 1 || p > 65535) return null;
  if (Buffer.byteLength(u) > 255 || Buffer.byteLength(w) > 255 || /[\r\n\0]/.test(u + w)) return null;
  const t = x.t === "socks5" || x.t === "http" ? x.t : null;
  return { h: h.toLowerCase(), p, u, w, t };
}

// ------------------------------------------------------------------ đọc dần từ 1 ổ cắm
const E = code => { const e = new Error(code); e.code = code; return e; };
function reader(sock) {
  let buf = Buffer.alloc(0), ended = false; const waits = [];
  const pump = () => {
    while (waits.length) {
      const w = waits[0], r = w.test(buf, ended);
      if (r === null && !ended) return;
      waits.shift(); if (w.t) clearTimeout(w.t);
      if (r === null) w.rej(E("CLOSED")); else { buf = buf.subarray(r.used); w.res(r.val); }
    }
  };
  const onData = d => { buf = Buffer.concat([buf, d]); if (buf.length > 262144) ended = true; pump(); };
  const onEnd = () => { ended = true; pump(); };
  sock.on("data", onData); sock.on("end", onEnd); sock.on("close", onEnd); sock.on("error", onEnd);
  const wait = (test, ms, code) => new Promise((res, rej) => {
    const w = { test, res, rej };
    if (ms) w.t = setTimeout(() => { const i = waits.indexOf(w); if (i >= 0) waits.splice(i, 1); rej(E(code || "TIMEOUT")); }, ms);
    waits.push(w); pump();
  });
  return {
    wait,
    bytes: (n, ms, code) => wait(b => b.length >= n ? { used: n, val: b.subarray(0, n) } : null, ms, code),
    until: (sep, max) => wait(b => { const i = b.indexOf(sep); if (i >= 0) return { used: i + sep.length, val: b.subarray(0, i + sep.length) };
      return b.length > max ? { used: b.length, val: null } : null; }),
    detach: () => { sock.pause(); sock.removeListener("data", onData); sock.removeListener("end", onEnd); sock.removeListener("close", onEnd); sock.removeListener("error", onEnd); return buf; }
  };
}

// ------------------------------------------------------------------ nối tới proxy
function connectOnce(addr, port, ms, ctx) {
  return new Promise((res, rej) => {
    if (ctx.dead) return rej(E("TIMEOUT"));
    const s = net.connect({ host: addr.address, port, family: addr.family }); ctx.socks.push(s);
    const t = setTimeout(() => { s.destroy(); rej(E("TIMEOUT_CONN")); }, ms);
    s.once("connect", () => { clearTimeout(t); s.setNoDelay(true); res(s); });
    s.once("error", e => { clearTimeout(t); s.destroy();
      const c = String((e && e.code) || "");
      rej(E(c === "ECONNREFUSED" ? "REFUSED" : addr.family === 6 && /ENETUNREACH|EHOSTUNREACH|EADDRNOTAVAIL|EAFNOSUPPORT/.test(c) ? "NO_V6" : "CONN")); });
  });
}
async function resolve(h, opt) {
  let addrs;
  if (net.isIP(h)) addrs = [{ address: h, family: net.isIP(h) }];
  else {
    try { addrs = await (opt.lookup || dns.lookup)(h, { all: true, verbatim: true }); } catch (e) { throw E("DNS"); }
    if (!addrs || !addrs.length) throw E("DNS");
  }
  const ok = addrs.filter(a => opt.allowPrivate || !badIp(a.address));
  if (!ok.length) throw E("PRIVATE");
  return ok.sort((a, b) => a.family - b.family).slice(0, 3);                  // IPv4 trước (máy chủ web thường chưa có IPv6 đi ra)
}
async function dial(addrs, port, opt, ctx) {
  let last;
  for (const a of addrs) { try { return await connectOnce(a, port, opt.conn, ctx); } catch (e) { last = e; if (e.code === "REFUSED" || ctx.dead) break; } }
  throw last || E("CONN");
}

// ------------------------------------------------------------------ bắt tay SOCKS5 / HTTP CONNECT
async function socks5(sock, R, it, host, port, opt) {
  const auth = !!(it.u || it.w);
  sock.write(Buffer.from(auth ? [5, 2, 0, 2] : [5, 1, 0]));
  const g = await R.bytes(2, opt.greet, "NOT_SOCKS5");
  if (g[0] !== 5) throw E("NOT_SOCKS5");
  if (g[1] === 2) {
    if (!auth) throw E("NEED_AUTH");
    const u = Buffer.from(it.u), w = Buffer.from(it.w);
    sock.write(Buffer.concat([Buffer.from([1, u.length]), u, Buffer.from([w.length]), w]));
    const a = await R.bytes(2);
    if (a[1] !== 0) throw E("BAD_AUTH");
  } else if (g[1] === 0xff) throw E(auth ? "BAD_AUTH" : "NEED_AUTH");
  else if (g[1] !== 0) throw E("NOT_SOCKS5");
  const hb = Buffer.from(host);
  sock.write(Buffer.concat([Buffer.from([5, 1, 0, 3, hb.length]), hb, Buffer.from([port >> 8, port & 255])]));
  const r = await R.bytes(4);
  if (r[0] !== 5) throw E("NOT_SOCKS5");
  if (r[1] !== 0) throw E("S5_" + r[1]);
  const al = r[3] === 1 ? 4 : r[3] === 4 ? 16 : r[3] === 3 ? (await R.bytes(1))[0] : -1;
  if (al < 0) throw E("NOT_SOCKS5");
  await R.bytes(al + 2);
}
async function httpConnect(sock, R, it, host, port) {
  let q = `CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\nUser-Agent: ${UA}\r\n`;
  if (it.u || it.w) q += `Proxy-Authorization: Basic ${Buffer.from(`${it.u}:${it.w}`).toString("base64")}\r\n`;
  sock.write(q + "\r\n");
  let head;
  try { head = await R.until(Buffer.from("\r\n\r\n"), 16384); } catch (e) { throw E(e.code === "CLOSED" ? "NOT_HTTP" : e.code); }
  const m = head && head.toString("latin1").match(/^HTTP\/1\.[01] (\d{3})/);
  if (!m) throw E("NOT_HTTP");
  const st = +m[1];
  if (st === 407) throw E(it.u || it.w ? "BAD_AUTH" : "NEED_AUTH");
  if (st < 200 || st > 299) throw E("HTTP_" + st);
}

// ------------------------------------------------------------------ qua đường hầm: TLS + GET trang trả IP
function tlsOver(sock, servername, extra) {
  return new Promise((res, rej) => {
    const t = tls.connect({ socket: sock, servername, ALPNProtocols: ["http/1.1"], ...extra });
    t.once("secureConnect", () => res(t));
    t.once("error", () => rej(E("TLS")));
  });
}
function dechunk(b) {
  const out = []; let i = 0;
  while (i < b.length) {
    const j = b.indexOf("\r\n", i); if (j < 0) break;
    const n = parseInt(b.subarray(i, j).toString("latin1"), 16); if (!(n > 0)) break;
    out.push(b.subarray(j + 2, j + 2 + n)); i = j + 2 + n + 2;
  }
  return Buffer.concat(out);
}
function respDone(b, ended) {                                                   // đủ 1 câu trả lời HTTP chưa (không đợi máy chủ đóng kết nối)
  const k = b.indexOf("\r\n\r\n"); if (k < 0) return ended || b.length > 65536 ? { used: b.length, val: b } : null;
  const head = b.subarray(0, k).toString("latin1"), rest = b.length - k - 4;
  const cl = head.match(/\r\ncontent-length:\s*(\d+)/i);
  if (cl && rest >= +cl[1]) return { used: b.length, val: b };
  if (/\r\ntransfer-encoding:\s*chunked/i.test(head) && b.indexOf("\r\n0\r\n\r\n", k) >= 0) return { used: b.length, val: b };
  return ended || b.length > 65536 ? { used: b.length, val: b } : null;
}
async function getIp(ts, tg) {
  ts.write(`GET ${tg.path} HTTP/1.1\r\nHost: ${tg.host}\r\nUser-Agent: ${UA}\r\nAccept: application/json, text/plain, */*\r\nConnection: close\r\n\r\n`);
  const raw = await reader(ts).wait(respDone);
  const k = raw.indexOf("\r\n\r\n"); if (k < 0) throw E("NO_IP");
  const head = raw.subarray(0, k).toString("latin1"), st = +((head.match(/^HTTP\/1\.[01] (\d{3})/) || [])[1] || 0);
  if (st !== 200) throw E("NO_IP");
  let b = raw.subarray(k + 4); if (/\r\ntransfer-encoding:\s*chunked/i.test(head)) b = dechunk(b);
  const txt = b.toString("utf8").trim();
  let ip = ""; try { ip = String(JSON.parse(txt).ip || ""); } catch (e) { ip = txt.split(/\s+/)[0] || ""; }
  if (!net.isIP(ip)) throw E("NO_IP");
  return ip;
}

// ------------------------------------------------------------------ thử 1 proxy theo 1 kiểu (socks5 | http)
async function tryProto(it, addrs, proto, opt, ctx) {
  const t0 = Date.now(); let lastErr = null;
  for (const tg of opt.targets) {
    if (ctx.dead) break;
    const sock = await dial(addrs, it.p, opt, ctx), R = reader(sock);
    if (proto === "socks5") await socks5(sock, R, it, tg.host, tg.port, opt); else await httpConnect(sock, R, it, tg.host, tg.port);   // lỗi bắt tay = lỗi của proxy → dừng
    R.detach();
    try {
      const ts = await tlsOver(sock, tg.host, opt.tls || {}); ctx.socks.push(ts);
      const ip = await getIp(ts, tg);
      return { ok: true, ms: Date.now() - t0, ip };
    } catch (e) { lastErr = e; sock.destroy(); }                                   // trang trả IP lỗi → thử trang dự phòng
  }
  throw lastErr || E("TIMEOUT");
}
function guarded(fn, ms) {                                                      // chạy có hạn giờ; hết giờ → đóng hết ổ cắm của lần thử
  const ctx = { socks: [], dead: false }; let t;
  return Promise.race([fn(ctx), new Promise((_, rej) => { t = setTimeout(() => { ctx.dead = true; rej(E("TIMEOUT")); }, ms); })])
    .finally(() => { clearTimeout(t); ctx.dead = true; for (const s of ctx.socks) s.destroy(); });
}
async function checkItem(it, mode, opt) {
  const m = it.t || mode, protos = m === "socks5" ? ["socks5"] : m === "http" ? ["http"] : ["socks5", "http"];
  let addrs; try { addrs = await resolve(it.h, opt); } catch (e) { return { live: false, err: e.code || "CONN" }; }   // tên miền sai / IP nội bộ → báo ngay
  const runs = await Promise.all(protos.map(p => guarded(ctx => tryProto(it, addrs, p, opt, ctx), opt.deadline)
    .catch(e => ({ ok: false, err: (e && e.code) || "CONN" }))));
  const out = { live: false };
  protos.forEach((p, i) => { out[p === "socks5" ? "s5" : "http"] = runs[i].ok ? { ok: true, ms: runs[i].ms } : { ok: false, err: runs[i].err }; });
  const best = runs.filter(r => r.ok).sort((a, b) => a.ms - b.ms)[0];
  if (best) { out.live = true; out.ip = best.ip; out.fam = net.isIP(best.ip); out.ms = best.ms; }
  else out.err = runs.map(r => r.err).find(c => c && !/^(NOT_SOCKS5|NOT_HTTP)$/.test(c)) || runs[0].err;
  return out;
}

// ------------------------------------------------------------------ quốc gia / nhà mạng của IP ra (không bắt buộc — lỗi thì bỏ qua)
const GEO = new Map();
async function geoOf(ip) {
  const c = GEO.get(ip); if (c && Date.now() - c.t < 6 * 3600e3) return c.v;
  let v = null;
  const get = async url => { const r = await fetch(url, { headers: { "User-Agent": UA, Accept: "application/json" }, signal: AbortSignal.timeout(1400) }); if (!r.ok) throw E("GEO"); return r.json(); };
  try { const tk = process.env.IPINFO_TOKEN ? "?token=" + encodeURIComponent(process.env.IPINFO_TOKEN) : "";
    const j = await get(`https://ipinfo.io/${encodeURIComponent(ip)}/json${tk}`);
    if (j && j.country && !j.bogon) v = { cc: String(j.country).slice(0, 2), org: String(j.org || "").replace(/^AS\d+\s+/, "").slice(0, 60), city: String(j.city || "").slice(0, 40) };
  } catch (e) {}
  if (!v) try { const j = await get(`https://api.ip.sb/geoip/${encodeURIComponent(ip)}`);
    if (j && j.country_code) v = { cc: String(j.country_code).slice(0, 2), org: String(j.isp || j.organization || j.asn_organization || "").slice(0, 60), city: String(j.city || "").slice(0, 40) };
  } catch (e) {}
  if (GEO.size > 2000) GEO.clear();
  if (v) GEO.set(ip, { t: Date.now(), v });
  return v;
}
async function addGeo(results, geo) {
  const ips = [...new Set(results.filter(r => r && r.live && r.ip).map(r => r.ip))];
  const got = await Promise.all(ips.map(ip => (geo || geoOf)(ip).catch(() => null)));
  const m = new Map(ips.map((ip, i) => [ip, got[i]]));
  for (const r of results) { const g = r && r.ip && m.get(r.ip); if (g) { r.cc = g.cc; r.org = g.org; if (g.city) r.city = g.city; } }
}

// ------------------------------------------------------------------ proxy của CloudBlue: trả lời từ cơ sở dữ liệu khi được
const OWN_RX = /^px[a-z0-9]{6,30}$/;
async function ownState(its, q) {
  const out = new Map(); q = q || sb;                                          // chỉ số dòng → mã lỗi (dòng không có trong map = thử qua mạng như thường)
  try {
    const st = A0(await q("/rest/v1/px_settings?select=pub_host,pub_port&id=eq.1")); if (!st) return out;
    const port = Number(st.pub_port) || 8899;
    const cand = its.map((it, i) => ({ it, i })).filter(x => x.it && x.it.p === port); if (!cand.length) return out;
    const eps = new Set(); if (st.pub_host) eps.add(String(st.pub_host).trim().toLowerCase().replace(/^\[|\]$/g, ""));
    for (const h of Arr(await q("/rest/v1/vm_hosts?select=pub_ip,pub4:metrics->px->>pub4&metrics->px=not.is.null"))) {
      if (h.pub4) eps.add(String(h.pub4).toLowerCase()); if (h.pub_ip) eps.add(String(h.pub_ip).toLowerCase()); }
    const mine = cand.filter(x => eps.has(x.it.h)); if (!mine.length) return out;
    const users = [...new Set(mine.map(x => x.it.u).filter(u => OWN_RX.test(u)))];
    const rows = users.length ? Arr(await q(`/rest/v1/px_proxies?select=username,password,expires_at,status&username=in.(${users.join(",")})`)) : [];
    for (const { it, i } of mine) {
      if (!it.u && !it.w) { out.set(i, "NEED_AUTH"); continue; }
      const r = rows.find(x => x.username === it.u);
      if (!r || String(r.password) !== it.w) { out.set(i, "BAD_AUTH"); continue; }
      if (r.status !== "active") out.set(i, "REVOKED");
      else if (!(new Date(r.expires_at).getTime() > Date.now())) out.set(i, "EXPIRED");
    }
  } catch (e) {}                                                                 // chưa có bảng (chưa chạy SQL v63) / lỗi → thử qua mạng như thường
  return out;
}
const Arr = v => Array.isArray(v) ? v : [];
const A0 = v => Arr(v)[0] || null;

// ------------------------------------------------------------------ đường dẫn web
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "METHOD" });
  const me = await whoAmI(req);
  if (!me || me.locked) return res.status(401).json({ ok: false, error: "NOT_LOGGED_IN" });
  let b; try { b = body(req); } catch (e) { return res.status(400).json({ ok: false, error: "BAD_BODY" }); }
  const items = Array.isArray(b && b.items) ? b.items : [];
  if (!items.length || items.length > MAX_ITEMS) return res.status(400).json({ ok: false, error: "BAD_ITEMS" });
  const mode = ["auto", "socks5", "http"].includes(b.mode) ? b.mode : "auto";
  if (!me.admin && (!(await rateLimitKey(`pxchk:u:${me.uid}`, 90, 3600)) || !(await rateLimit(req, "pxchk", 180, 3600))))
    return res.status(429).json({ ok: false, error: "SLOW_DOWN" });
  const its = items.map(normItem), own = await ownState(its);
  const results = await Promise.all(its.map((it, i) => !it ? { live: false, err: "BAD_LINE" } : own.has(i) ? { live: false, err: own.get(i), own: true }
    : checkItem(it, mode, PROD).catch(() => ({ live: false, err: "CONN" }))));
  try { await guarded(() => addGeo(results), 1500); } catch (e) {}
  return res.status(200).json({ ok: true, results });
};
module.exports._t = { normItem, badIp, bad4, bad6, checkItem, addGeo, resolve, respDone, ownState, MAX_ITEMS, PROD };
