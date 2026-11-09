// Tạo yêu cầu thanh toán USDT qua NOWPayments.
// Frontend gọi: POST /api/crypto-create  body { order_id }  (order_id = memo của lệnh nạp đã tạo)
// Biến môi trường Vercel: NOWPAYMENTS_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, (SITE_URL)
const { sb, body, rateLimit } = require("./_lib");
const SITE = process.env.SITE_URL || "https://cloudblue.vn";
const PAY_CURRENCY = process.env.CRYPTO_PAY_CURRENCY || "usdttrc20"; // USDT mạng TRC20

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  // Chống spam: mỗi IP tối đa 8 lần tạo thanh toán / phút
  if (!(await rateLimit(req, "crypto-create", 8, 60))) {
    return res.status(429).json({ error: "Bạn thao tác quá nhanh. Chờ một chút rồi thử lại." });
  }
  const key = process.env.NOWPAYMENTS_API_KEY;
  if (!key) return res.status(500).json({ error: "NOWPAYMENTS_API_KEY chưa cấu hình" });

  const { order_id, coin } = body(req);
  if (!order_id || !/^[A-Za-z0-9]{3,40}$/.test(String(order_id))) return res.status(400).json({ error: "order_id" });
  const ALLOWED = { usdttrc20: "usdttrc20", ltc: "ltc" };
  const payCur = ALLOWED[String(coin || "").toLowerCase()] || PAY_CURRENCY;

  try {
    // Lấy lệnh nạp đang chờ theo order_id (memo) — số tiền VND lấy từ DB, không tin client
    const rows = await sb(`/rest/v1/topups?select=amount,status,user_id&memo=eq.${encodeURIComponent(order_id)}&limit=1`);
    const tp = rows[0];
    if (!tp || tp.status !== "pending") return res.status(400).json({ error: "Lệnh nạp không tồn tại hoặc đã xử lý" });

    const st = (await sb(`/rest/v1/settings?select=data&id=eq.1`))[0];
    const rate = Number(st && st.data && st.data.rate) || 25000;
    const usd = Math.max(1, Math.round((tp.amount / rate) * 100) / 100);
    // Cộng % phí sàn vào số khách phải gửi (shop nhận đủ). Mặc định 5%, chỉnh qua CRYPTO_FEE_PCT.
    const FEE_PCT = Number(process.env.CRYPTO_FEE_PCT) || 5;
    const payUsd = Math.round(usd * (1 + FEE_PCT / 100) * 100) / 100;

    // Hỏi NOWPayments mức tối thiểu THẬT của coin này (quy ra USD) để báo rõ cho khách
    try {
      const mr = await fetch(`https://api.nowpayments.io/v1/min-amount?currency_from=${payCur}&currency_to=${payCur}&fiat_equivalent=usd`, { headers: { "x-api-key": key } });
      const mj = await mr.json();
      const minUsd = Number(mj && mj.fiat_equivalent);
      if (minUsd && usd < minUsd) {
        const need = Math.ceil(minUsd * 1.05);
        return res.status(400).json({ error: `Số tiền quá nhỏ cho ${payCur.toUpperCase().replace("TRC20", " TRC20")}. Tối thiểu khoảng $${need}. Hãy nạp nhiều hơn, hoặc dùng tab Ngân hàng cho số nhỏ/lẻ.` });
      }
    } catch (e) { /* bỏ qua nếu không lấy được, để NOWPayments tự kiểm tra */ }

    const r = await fetch("https://api.nowpayments.io/v1/payment", {
      method: "POST",
      headers: { "x-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify({
        price_amount: payUsd,       // đã gồm % phí sàn → khách trả phí, shop nhận đủ
        price_currency: "usd",
        pay_currency: payCur,
        order_id: String(order_id),
        order_description: "CloudBlue top-up",
        ipn_callback_url: SITE + "/api/crypto-webhook",
      }),
    });
    const p = await r.json();
    if (!r.ok || !p.pay_address) {
      return res.status(400).json({ error: p.message || "NOWPayments từ chối. Có thể số tiền quá nhỏ — hãy nạp nhiều hơn hoặc dùng tab Ngân hàng." });
    }
    // Ghi loại coin + số USD vào lệnh nạp để admin phân biệt (bank vs USDT/LTC)
    try {
      await sb(`/rest/v1/topups?memo=eq.${encodeURIComponent(order_id)}`, {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({ coin: payCur, usd }),
      });
    } catch (e) { /* không chặn thanh toán nếu ghi phụ lỗi */ }
    return res.status(200).json({
      payment_id: p.payment_id,
      pay_address: p.pay_address,
      pay_amount: p.pay_amount,
      pay_currency: p.pay_currency,
      network: payCur === "ltc" ? "Litecoin" : "TRC20",
      usd,
    });
  } catch (e) {
    console.error("crypto-create", e);
    return res.status(500).json({ error: "Lỗi tạo thanh toán, thử lại sau." });
  }
};
