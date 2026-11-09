// Vercel Serverless Function: SePay gọi vào đây mỗi khi tài khoản ngân hàng có tiền vào.
// URL đặt trong SePay: https://blueroblox.shop/api/sepay-webhook
// Biến môi trường cần đặt trên Vercel: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SEPAY_API_KEY

const SB = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const headers = { apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ success: false });

  // SePay gửi: Authorization: Apikey <khoá bạn đặt>
  if (!process.env.SEPAY_API_KEY || req.headers.authorization !== `Apikey ${process.env.SEPAY_API_KEY}`) {
    return res.status(401).json({ success: false });
  }

  const tx = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {});
  if (tx.transferType !== "in") return res.status(200).json({ success: true });

  const content = String(tx.content || tx.description || "").toUpperCase().replace(/\s+/g, "");
  const amount = Math.round(Number(tx.transferAmount) || 0);
  const ref = String(tx.id || tx.referenceCode || "");
  if (!content || amount <= 0 || !ref) return res.status(200).json({ success: true });

  try {
    // Lấy các lệnh nạp đang chờ trong 3 ngày gần nhất, tìm lệnh có nội dung khớp
    const since = new Date(Date.now() - 3 * 864e5).toISOString();
    const r = await fetch(`${SB}/rest/v1/topups?select=memo&status=eq.pending&created_at=gte.${encodeURIComponent(since)}&limit=1000`, { headers });
    if (!r.ok) throw new Error("load " + r.status);
    const pending = await r.json();
    const hit = pending.find(t => content.includes(String(t.memo).toUpperCase()));
    if (!hit) return res.status(200).json({ success: true, matched: false });

    const c = await fetch(`${SB}/rest/v1/rpc/credit_topup`, {
      method: "POST", headers,
      body: JSON.stringify({ p_memo: hit.memo, p_amount: amount, p_ref: ref })
    });
    if (!c.ok) throw new Error("credit " + c.status);
    const credited = await c.json();
    return res.status(200).json({ success: true, matched: true, credited });
  } catch (e) {
    console.error("sepay-webhook", e);
    // Trả lỗi để SePay tự gửi lại sau
    return res.status(500).json({ success: false });
  }
};
