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

module.exports = { sb, rpc, userOf, esc, vnd, body, tg, tgTo, mail, clientIp, rateLimit };
