// NOWPayments IPN: tự cộng tiền khi khách thanh toán USDT xong.
// URL đặt trong NOWPayments (Store/IPN callback): https://www.blueroblox.shop/api/crypto-webhook
// Biến môi trường Vercel: NOWPAYMENTS_IPN_SECRET, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
const crypto = require("crypto");
const { rpc } = require("./_lib");

// NOWPayments ký HMAC-SHA512 trên body đã sort key theo thứ tự chữ cái
function sortObj(o) {
  if (Array.isArray(o)) return o.map(sortObj);
  if (o && typeof o === "object") {
    const r = {};
    for (const k of Object.keys(o).sort()) r[k] = sortObj(o[k]);
    return r;
  }
  return o;
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ ok: false });
  const secret = process.env.NOWPAYMENTS_IPN_SECRET;
  if (!secret) return res.status(500).json({ ok: false });

  const data = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  const sig = req.headers["x-nowpayments-sig"];
  const expect = crypto.createHmac("sha512", secret).update(JSON.stringify(sortObj(data))).digest("hex");
  if (!sig || sig !== expect) return res.status(401).json({ ok: false });

  try {
    const status = data.payment_status;
    const order_id = data.order_id;
    const ref = "NOW-" + (data.payment_id || "");
    if (!order_id) return res.status(200).json({ ok: true });

    // Chỉ cộng khi thanh toán hoàn tất; cộng đúng số VND của lệnh nạp (không theo số crypto)
    if (status === "finished" || status === "confirmed") {
      await rpc("credit_crypto", { p_memo: String(order_id), p_ref: ref });
    }
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("crypto-webhook", e);
    return res.status(500).json({ ok: false });
  }
};
