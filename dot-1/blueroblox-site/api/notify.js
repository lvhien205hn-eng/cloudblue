// Supabase gọi vào đây mỗi khi có đơn mới, đơn được giao, hoặc nạp tiền thành công.
// Cài trong Supabase › Database › Webhooks (xem HUONG-DAN.md, bước 9).
// URL: https://cloudblue.vn/api/notify   Header: x-webhook-secret = NOTIFY_SECRET
const { userOf, esc, vnd, body, tg, mail } = require("./_lib");
const SITE = process.env.SITE_URL || "https://cloudblue.vn";

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).end();
  if (!process.env.NOTIFY_SECRET || req.headers["x-webhook-secret"] !== process.env.NOTIFY_SECRET) return res.status(401).json({ ok: false });

  const { type, table, record: r, old_record: o } = body(req);
  try {
    // Đơn mới
    if (table === "orders" && type === "INSERT" && r) {
      const u = await userOf(r.user_id);
      const manual = r.status === "pending";
      const text = (manual ? "🚨 <b>ĐƠN CẦN GIAO THỦ CÔNG</b>" : "🛒 <b>Đơn mới · đã tự giao</b>") +
        `\n\n👤 Khách: <b>${esc(u.username)}</b> (${esc(u.email)})\n📦 ${esc(r.product_name)} × ${r.qty}\n💵 ${vnd(r.total)}\n🆔 Mã đơn: <code>${r.id}</code>` +
        (manual ? "\n\n👉 <b>Trả lời (Reply) tin nhắn này</b> bằng thông tin VPS để giao ngay cho khách. Mỗi dòng 1 VPS, ví dụ:\n<code>103.1.2.3:3389|Administrator|MatKhau</code>\n\nKhông giao được thì Reply <code>/hoantien</code>." : "");
      await tg(text);
      if (manual && process.env.ADMIN_EMAIL) {
        await mail(process.env.ADMIN_EMAIL, `[CloudBlue] Đơn cần giao: ${r.product_name}`,
          `<p>Khách <b>${esc(u.username)}</b> (${esc(u.email)}) vừa mua <b>${esc(r.product_name)} × ${r.qty}</b> – ${vnd(r.total)}.</p>
           <p>Mã đơn: <code>${r.id}</code></p>
           <p>Giao hàng: trả lời tin nhắn trên Telegram, hoặc vào <a href="${SITE}">trang quản trị</a> › Đơn hàng › Giao hàng.</p>`);
      }
    }

    // Đơn thủ công vừa được giao → báo khách qua email
    if (table === "orders" && type === "UPDATE" && r && o && o.status === "pending" && r.status === "done") {
      const u = await userOf(r.user_id);
      await mail(u.email, `Đơn ${r.product_name} đã sẵn sàng`,
        `<p>Chào ${esc(u.username)},</p><p>Đơn <b>${esc(r.product_name)} × ${r.qty}</b> của bạn đã được giao:</p>
         <pre style="background:#f4f6fb;padding:12px;border-radius:8px;white-space:pre-wrap">${esc(r.items)}</pre>
         <p>Bạn xem lại bất cứ lúc nào trong mục <a href="${SITE}">Đơn hàng</a> trên CloudBlue.</p>`);
      await tg(`✅ Đã giao đơn <code>${r.id}</code> cho <b>${esc(u.username)}</b>${u.email && process.env.RESEND_API_KEY ? " (đã gửi email cho khách)" : ""}.`);
    }

    // Đơn bị hoàn tiền
    if (table === "orders" && type === "UPDATE" && r && o && o.status === "pending" && r.status === "refunded") {
      const u = await userOf(r.user_id);
      await tg(`↩️ Đã hoàn <b>${vnd(r.total)}</b> cho <b>${esc(u.username)}</b> · đơn <code>${r.id}</code>.`);
    }

    // Nạp tiền thành công
    if (table === "topups" && type === "UPDATE" && r && o && o.status === "pending" && r.status === "done") {
      const u = await userOf(r.user_id);
      await tg(`💰 <b>Nạp tiền thành công</b>\n👤 ${esc(u.username)}\n💵 +${vnd(r.amount)}\n🧾 ${esc(r.memo)}`);
    }
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("notify", e);
    return res.status(500).json({ ok: false });
  }
};
