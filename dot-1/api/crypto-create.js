// Tạo yêu cầu thanh toán USDT qua NOWPayments.
// Frontend gọi: POST /api/crypto-create  body { order_id }  (order_id = memo của lệnh nạp đã tạo)
// Biến môi trường Vercel: NOWPAYMENTS_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, (SITE_URL)
const { sb, body } = require("./_lib");
const SITE = process.env.SITE_URL || "https://www.blueroblox.shop";
const PAY_CURRENCY = process.env.CRYPTO_PAY_CURRENCY || "usdttrc20"; // USDT mạng TRC20

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  const key = process.env.NOWPAYMENTS_API_KEY;
  if (!key) return res.status(500).json({ error: "NOWPAYMENTS_API_KEY chưa cấu hình" });

  const { order_id } = body(req);
  if (!order_id || !/^[A-Za-z0-9]{3,40}$/.test(String(order_id))) return res.status(400).json({ error: "order_id" });

  try {
    // Lấy lệnh nạp đang chờ theo order_id (memo) — số tiền VND lấy từ DB, không tin client
    const rows = await sb(`/rest/v1/topups?select=amount,status,user_id&memo=eq.${encodeURIComponent(order_id)}&limit=1`);
    const tp = rows[0];
    if (!tp || tp.status !== "pending") return res.status(400).json({ error: "Lệnh nạp không tồn tại hoặc đã xử lý" });

    const st = (await sb(`/rest/v1/settings?select=data&id=eq.1`))[0];
    const rate = Number(st && st.data && st.data.rate) || 25000;
    const usd = Math.max(1, Math.round((tp.amount / rate) * 100) / 100);

    const r = await fetch("https://api.nowpayments.io/v1/payment", {
      method: "POST",
      headers: { "x-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify({
        price_amount: usd,
        price_currency: "usd",
        pay_currency: PAY_CURRENCY,
        order_id: String(order_id),
        order_description: "BLUEROBLOX top-up",
        ipn_callback_url: SITE + "/api/crypto-webhook",
      }),
    });
    const p = await r.json();
    if (!r.ok || !p.pay_address) {
      return res.status(400).json({ error: p.message || "NOWPayments từ chối (có thể số tiền quá nhỏ cho USDT). Hãy nạp số tiền lớn hơn." });
    }
    return res.status(200).json({
      payment_id: p.payment_id,
      pay_address: p.pay_address,
      pay_amount: p.pay_amount,
      pay_currency: p.pay_currency,
      network: "TRC20",
      usd,
    });
  } catch (e) {
    console.error("crypto-create", e);
    return res.status(500).json({ error: "Lỗi tạo thanh toán, thử lại sau." });
  }
};
