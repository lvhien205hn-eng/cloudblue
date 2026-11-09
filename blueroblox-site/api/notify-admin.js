// Gửi 1 tin nhắn Telegram về cho admin (shop) — dùng cho báo thay đổi + nút Test bot.
// POST /api/notify-admin  body { text }
// Chỉ nhận từ 3 nguồn (còn lại trả 401):
//   1. Admin đã đăng nhập (web gửi kèm mã đăng nhập)  → gửi nguyên văn.
//   2. Khách đã đăng nhập (đơn mới, nhận máy tặng, đăng ký CTV) → ghi rõ tên khách, lọc chữ, tối đa 6 tin / 10 phút.
//   3. Máy chủ của shop (cloudphoned) → nhận ra bằng IP công khai mà máy chủ tự báo trong bảng cloud_nodes,
//      hoặc header x-notify-key đúng biến NOTIFY_KEY trên Vercel (nếu có đặt).
const { body, tgTo, rateLimit, rateLimitKey, whoAmI, clientIp, sb, esc, same } = require("./_lib");

const normIp = ip => String(ip || "").trim().toLowerCase().replace(/^::ffff:/, "");
let ipCache = { t: 0, set: new Set() };
async function serverIps() {
  if (Date.now() - ipCache.t < 60000) return ipCache.set;
  const rows = await sb("/rest/v1/cloud_nodes?select=stream");
  const set = new Set();
  for (const r of rows || []) for (const d of ((r && r.stream && r.stream.direct) || [])) if (d && d.host && !d.lan) set.add(normIp(d.host));
  ipCache = { t: Date.now(), set };
  return set;
}

// Chữ của khách: bỏ hết thẻ HTML, chỉ giữ <b> <i> <code> trơn (không thuộc tính).
const safeHtml = s => esc(s).replace(/&lt;(\/?)(b|i|code)&gt;/g, "<$1$2>");
const plain = s => String(s).replace(/<[^>]*>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

async function send(text) {
  const chat = process.env.TELEGRAM_CHAT_ID;
  let r = await tgTo(chat, text);
  if (r && !r.ok && /parse|entit/i.test(r.description || "")) r = await tgTo(chat, plain(text), { parse_mode: undefined });
  return r;
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  if (!(await rateLimit(req, "notify-admin", 30, 60))) return res.status(429).json({ error: "slow" });
  const raw = String((body(req) || {}).text || "").slice(0, 1500);
  if (!raw) return res.status(400).json({ error: "empty" });

  let text = null;
  const who = await whoAmI(req);
  if (who && who.admin) {
    text = raw;
  } else if (who && !who.locked) {
    if (!(await rateLimitKey(`notify-user:${who.uid}`, 6, 600))) return res.status(429).json({ error: "slow" });
    text = `👤 Khách <b>${esc(who.username || who.email || who.uid.slice(0, 8))}</b>\n` + safeHtml(raw).slice(0, 900);
  } else {
    const key = process.env.NOTIFY_KEY, given = (req.headers || {})["x-notify-key"];
    let server = !!(key && given && same(given, key));
    if (!server) { try { server = (await serverIps()).has(normIp(clientIp(req))); } catch (e) { server = false; } }
    if (server) text = raw;
  }
  if (!text) return res.status(401).json({ ok: false, error: "unauthorized", reason: "Cần đăng nhập" });

  if (!process.env.TELEGRAM_BOT_TOKEN || !process.env.TELEGRAM_CHAT_ID)
    return res.status(200).json({ ok: false, reason: "Chưa cài TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trên Vercel" });
  try { const r = await send(text); return res.status(200).json({ ok: !!(r && r.ok), reason: (r && r.description) || "" }); }
  catch (e) { return res.status(200).json({ ok: false, reason: String(e && e.message || e) }); }
};
