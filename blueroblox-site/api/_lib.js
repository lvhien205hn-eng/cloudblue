// Hàm dùng chung cho các API (file bắt đầu bằng "_" không thành đường dẫn web)
const SB = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const H = { apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

async function sb(path, opt = {}) {
  const r = await fetch(SB + path, { ...opt, headers: { ...H, ...(opt.headers || {}) } });
  const t = await r.text();
  if (!r.ok) throw new Error(`${path} ${r.status} ${t}`);
  return t ? JSON.parse(t) : null;
}
const rpc = (fn, args) => sb(`/rest/v1/rpc/${fn}`, { method: "POST", body: JSON.stringify(args) });
const userOf = async id => (await sb(`/rest/v1/profiles?select=username,email&id=eq.${encodeURIComponent(id)}`))[0] || {};

// IP thật của khách (Vercel đặt trong x-forwarded-for / x-real-ip)
function clientIp(req) {
  const h = req.headers || {};
  const xff = String(h["x-forwarded-for"] || "").split(",")[0].trim();
  return xff || h["x-real-ip"] || h["cf-connecting-ip"] || "unknown";
}
// Giới hạn tần suất theo IP: trả về true nếu ĐƯỢC phép, false nếu vượt hạn mức.
// Lỗi kết nối DB → không chặn (tránh tự khoá web khi DB chập chờn).
async function rateLimit(req, action, limit, windowSec) {
  try {
    const ok = await rpc("rl_hit", { p_key: `${action}:${clientIp(req)}`, p_limit: limit, p_window: windowSec });
    return ok === true;
  } catch (e) { return true; }
}

// Giới hạn tần suất theo 1 khoá tự đặt (VD theo tài khoản). Lỗi DB → không chặn.
async function rateLimitKey(key, limit, windowSec) {
  try { return (await rpc("rl_hit", { p_key: key, p_limit: limit, p_window: windowSec })) === true; }
  catch (e) { return true; }
}

// So 2 chuỗi bí mật không lộ thời gian (chống dò từng ký tự). Rỗng → luôn sai.
function same(a, b) {
  const x = Buffer.from(String(a ?? "")), y = Buffer.from(String(b ?? ""));
  return x.length > 0 && x.length === y.length && require("crypto").timingSafeEqual(x, y);
}

// Người gọi là ai? Đọc "Authorization: Bearer <mã đăng nhập Supabase>" → hỏi Supabase mã còn hạn không → đọc hồ sơ.
// Trả { uid, email, username, admin, locked } hoặc null (không có / sai / hết hạn). admin = giống hàm SQL is_admin().
async function whoAmI(req) {
  const m = String((req.headers || {}).authorization || "").match(/^Bearer\s+(\S+)$/i);
  if (!m || m[1].split(".").length !== 3) return null;          // chỉ nhận mã đăng nhập (JWT), không nhận khoá khác
  try {
    const r = await fetch(SB + "/auth/v1/user", { headers: { apikey: KEY, Authorization: "Bearer " + m[1] } });
    if (!r.ok) return null;
    const u = await r.json();
    if (!u || !u.id) return null;
    const p = (await sb(`/rest/v1/profiles?select=username,email,role,locked&id=eq.${encodeURIComponent(u.id)}`))[0] || {};
    return { uid: u.id, email: p.email || u.email || "", username: p.username || "", locked: !!p.locked, admin: p.role === "admin" && !p.locked };
  } catch (e) { return null; }
}

const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const vnd = n => Math.round(+n || 0).toLocaleString("vi-VN") + "đ";
const body = req => typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});

async function tgTo(chatId, text, extra = {}) {
  const T = process.env.TELEGRAM_BOT_TOKEN; if (!T || !chatId) return null;
  const r = await fetch(`https://api.telegram.org/bot${T}/sendMessage`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true, ...extra })
  });
  return r.json();
}
const tg = (text, extra) => tgTo(process.env.TELEGRAM_CHAT_ID, text, extra);

async function mail(to, subject, html) {
  const K = process.env.RESEND_API_KEY; if (!K || !to) return null;
  const from = process.env.MAIL_FROM || "CloudBlue <no-reply@cloudblue.vn>";
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST", headers: { Authorization: `Bearer ${K}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from, to: [to], subject, html })
  });
  return r.json();
}

module.exports = { sb, rpc, userOf, esc, vnd, body, tg, tgTo, mail, clientIp, rateLimit, rateLimitKey, same, whoAmI };
