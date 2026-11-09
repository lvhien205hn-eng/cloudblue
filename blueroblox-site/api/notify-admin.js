// Gửi 1 tin nhắn Telegram về cho admin (shop) — dùng cho báo thay đổi + nút Test bot.
// POST /api/notify-admin  body { text }
const { body, tg, rateLimit } = require("./_lib");
module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  if (!(await rateLimit(req, "notify-admin", 30, 60))) return res.status(429).json({ error: "slow" });
  const { text } = body(req);
  const t = String(text || "").slice(0, 1500);
  if (!t) return res.status(400).json({ error: "empty" });
  if (!process.env.TELEGRAM_BOT_TOKEN || !process.env.TELEGRAM_CHAT_ID)
    return res.status(200).json({ ok: false, reason: "Chưa cài TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trên Vercel" });
  try { const r = await tg(t); return res.status(200).json({ ok: !!(r && r.ok), reason: (r && r.description) || "" }); }
  catch (e) { return res.status(200).json({ ok: false, reason: String(e && e.message || e) }); }
};
