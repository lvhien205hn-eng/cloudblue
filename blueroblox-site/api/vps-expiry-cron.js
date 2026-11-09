// Quét máy VPS sắp/đã hết hạn → nhắn về Telegram của shop. Chạy tự động mỗi ngày (Vercel Cron).
// Biến môi trường: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, (CRON_SECRET)
// Lịch đặt trong vercel.json. Vercel tự gửi header Authorization: Bearer <CRON_SECRET> khi chạy cron.
const { sb, tg } = require("./_lib");

const vnDate = iso => new Date(iso).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
const daysLeft = iso => Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);

module.exports = async (req, res) => {
  // Bảo vệ: nếu đã đặt CRON_SECRET thì bắt buộc đúng (Vercel Cron tự gửi kèm; test tay thì ?key=)
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const ok = req.headers.authorization === `Bearer ${secret}` || (req.query && req.query.key === secret);
    if (!ok) return res.status(401).json({ error: "unauthorized" });
  }
  try {
    const nowIso = new Date().toISOString();
    const in2d = new Date(Date.now() + 2 * 86400000).toISOString();

    // Sắp hết hạn (còn ≤2 ngày, chưa báo)
    const warn = await sb(`/rest/v1/vps_machines?select=id,machine_name,expires_at,user_id,product_name,profiles(username)` +
      `&status=eq.active&notified_warn=eq.false&expires_at=gt.${nowIso}&expires_at=lte.${in2d}&order=expires_at`);
    // Đã hết hạn (chưa báo)
    const expd = await sb(`/rest/v1/vps_machines?select=id,machine_name,expires_at,user_id,product_name,profiles(username)` +
      `&status=eq.active&notified_exp=eq.false&expires_at=lte.${nowIso}&order=expires_at`);

    const nameOf = m => (m.profiles && m.profiles.username) || m.user_id;
    let sent = 0;

    if (warn.length) {
      const body = warn.map(m => `• 🖥 <b>${m.machine_name}</b> — khách <b>${nameOf(m)}</b>\n   Hạn: ${vnDate(m.expires_at)} (còn ${daysLeft(m.expires_at)} ngày)`).join("\n");
      await tg(`⏰ <b>VPS SẮP HẾT HẠN (≤2 ngày) — ${warn.length} máy</b>\n${body}`);
      await sb(`/rest/v1/vps_machines?id=in.(${warn.map(m => m.id).join(",")})`, { method: "PATCH", headers: { Prefer: "return=minimal" }, body: JSON.stringify({ notified_warn: true }) });
      sent += warn.length;
    }
    if (expd.length) {
      const body = expd.map(m => `• 🖥 <b>${m.machine_name}</b> — khách <b>${nameOf(m)}</b>\n   Hết hạn: ${vnDate(m.expires_at)}`).join("\n");
      await tg(`🚨 <b>VPS ĐÃ HẾT HẠN — ${expd.length} máy</b>\n${body}`);
      await sb(`/rest/v1/vps_machines?id=in.(${expd.map(m => m.id).join(",")})`, { method: "PATCH", headers: { Prefer: "return=minimal" }, body: JSON.stringify({ notified_exp: true }) });
      sent += expd.length;
    }
    return res.status(200).json({ ok: true, warned: warn.length, expired: expd.length, sent });
  } catch (e) {
    console.error("vps-expiry-cron", e);
    return res.status(500).json({ error: String(e && e.message || e) });
  }
};
