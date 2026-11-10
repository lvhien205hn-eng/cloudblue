// Khách bấm "Quên mật khẩu" trên web → nhắn Telegram cho admin NGAY (không cần đăng nhập).
// POST /api/pw-forgot  body { email }
// Chống spam nằm ở SQL (pw_forgot_note, v29c): mỗi mạng 5 lần / giờ, mỗi email 3 lần / giờ, mỗi khách 1 tin / giờ, email lạ không báo.
// Luôn trả về giống nhau → không ai dò được email nào có tài khoản. Dùng biến Vercel sẵn có:
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
const SB = process.env.SUPABASE_URL, KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const esc = s => String(s == null ? "" : s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function readBody(req) {
  if (req.body && typeof req.body === "object") return Promise.resolve(req.body);
  if (typeof req.body === "string") { try { return Promise.resolve(JSON.parse(req.body || "{}")); } catch (e) { return Promise.resolve({}); } }
  return new Promise(ok => { let d = ""; req.on("data", c => { d += c; if (d.length > 4096) req.destroy(); }); req.on("end", () => { try { ok(JSON.parse(d || "{}")); } catch (e) { ok({}); } }); req.on("error", () => ok({})); });
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  const b = await readBody(req);
  const email = String((b && b.email) || "").trim().slice(0, 200);
  if (!email || !SB || !KEY) return res.status(200).json({ ok: true });
  const ip = String(req.headers["x-real-ip"] || String(req.headers["x-forwarded-for"] || "").split(",")[0] || "").trim().slice(0, 64);
  const tg = !!(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID);
  let r = null;
  try {
    const x = await fetch(SB + "/rest/v1/rpc/pw_forgot_note", {
      method: "POST", headers: { apikey: KEY, Authorization: "Bearer " + KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ p_email: email, p_ip: ip || null, p_tg: tg }) });
    r = x.ok ? await x.json() : null;
  } catch (e) { r = null; }
  if (r && r.notify && tg) {
    const text = `🔑 <b>Khách quên mật khẩu</b>\nTài khoản: <b>${esc(r.user)}</b> (${esc(r.email)})\n`
      + `Khách tự đặt lại được bằng link trong email. Nếu khách nhắn KHÔNG nhận được email: web admin › 🛡️ Bảo mật › bấm <b>🔑 Mật khẩu tạm</b> ở cảnh báo này `
      + `(hoặc 👥 Khách hàng › Chi tiết), gửi mật khẩu tạm cho khách — khách đăng nhập xong sẽ phải đổi mật khẩu mới.`;
    try {
      await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: process.env.TELEGRAM_CHAT_ID, text, parse_mode: "HTML", disable_web_page_preview: true }) });
    } catch (e) {}
  }
  return res.status(200).json({ ok: true });
};
