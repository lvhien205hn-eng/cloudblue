// Hỏi trạng thái 1 lệnh thanh toán crypto từ NOWPayments (để hiện tiến trình % cho khách).
// Frontend gọi: POST /api/crypto-status  body { payment_id }
// Biến môi trường: NOWPAYMENTS_API_KEY
const { rateLimit } = require("./_lib");

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "method" });
  // Chống spam: mỗi IP tối đa 40 lần hỏi trạng thái / phút (web tự hỏi mỗi 8 giây)
  if (!(await rateLimit(req, "crypto-status", 40, 60))) {
    return res.status(200).json({ payment_status: "waiting" });
  }
  const key = process.env.NOWPAYMENTS_API_KEY;
  if (!key) return res.status(500).json({ error: "no key" });
  const data = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  const pid = String(data.payment_id || "");
  if (!/^[A-Za-z0-9]{3,40}$/.test(pid)) return res.status(400).json({ error: "payment_id" });
  try {
    const r = await fetch("https://api.nowpayments.io/v1/payment/" + pid, { headers: { "x-api-key": key } });
    const j = await r.json();
    return res.status(200).json({
      payment_status: j.payment_status || "waiting",
      actually_paid: j.actually_paid,
      pay_amount: j.pay_amount,
    });
  } catch (e) {
    return res.status(200).json({ payment_status: "waiting" });
  }
};
