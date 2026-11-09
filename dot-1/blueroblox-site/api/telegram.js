// Bot Telegram: bạn Reply tin nhắn "ĐƠN CẦN GIAO" bằng thông tin VPS → web tự giao cho khách.
// Đăng ký webhook (mở 1 lần trên trình duyệt, thay TOKEN và SECRET):
// https://api.telegram.org/botTOKEN/setWebhook?url=https://blueroblox.shop/api/telegram&secret_token=SECRET
const { rpc, esc, body, tgTo } = require("./_lib");
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(200).send("ok");
  if (!process.env.TELEGRAM_WEBHOOK_SECRET || req.headers["x-telegram-bot-api-secret-token"] !== process.env.TELEGRAM_WEBHOOK_SECRET) return res.status(401).end();

  const m = (body(req) || {}).message;
  if (!m || !m.chat) return res.status(200).json({ ok: true });
  const chat = String(m.chat.id), text = String(m.text || "").trim();

  try {
    // Lấy Chat ID để điền vào Vercel (dùng được cả khi chưa cài TELEGRAM_CHAT_ID)
    if (/^\/(start|id)\b/i.test(text)) {
      await tgTo(chat, `Chat ID của bạn là: <code>${esc(chat)}</code>\nDán số này vào biến <b>TELEGRAM_CHAT_ID</b> trên Vercel.`);
      return res.status(200).json({ ok: true });
    }
    // Chỉ nhận lệnh từ đúng tài khoản admin
    if (chat !== String(process.env.TELEGRAM_CHAT_ID || "")) return res.status(200).json({ ok: true });

    const ref = (m.reply_to_message && (m.reply_to_message.text || m.reply_to_message.caption)) || "";
    const id = (ref.match(UUID) || [])[0];
    if (!id) {
      await tgTo(chat, "Để giao hàng, hãy <b>Reply (trả lời)</b> đúng tin nhắn <b>ĐƠN CẦN GIAO</b> rồi dán thông tin VPS.");
      return res.status(200).json({ ok: true });
    }

    if (/^\/hoantien\b/i.test(text)) {
      const ok = await rpc("_refund", { p_order: id });
      if (!ok) await tgTo(chat, `Đơn <code>${id}</code> không còn ở trạng thái chờ giao.`);
      // tin "Đã hoàn tiền" sẽ do /api/notify gửi
    } else if (text) {
      const ok = await rpc("_deliver", { p_order: id, p_items: text });
      if (!ok) await tgTo(chat, `Đơn <code>${id}</code> đã được giao hoặc huỷ trước đó.`);
      // tin "Đã giao" sẽ do /api/notify gửi
    }
  } catch (e) {
    console.error("telegram", e);
    await tgTo(chat, "Có lỗi khi xử lý. Thử lại, hoặc giao trong trang quản trị.");
  }
  return res.status(200).json({ ok: true });
};
