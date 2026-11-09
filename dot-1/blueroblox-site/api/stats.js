// Đọc số liệu tổng của shop (JSON) — cho công cụ ngoài kéo về. Bảo vệ bằng STATS_KEY hoặc CRON_SECRET.
// GET /api/stats?key=XXX
const { rpc } = require("./_lib");
module.exports = async (req, res) => {
  const secret = process.env.STATS_KEY || process.env.CRON_SECRET;
  if (secret) {
    const ok = (req.query && req.query.key === secret) || req.headers.authorization === `Bearer ${secret}`;
    if (!ok) return res.status(401).json({ error: "unauthorized" });
  }
  try {
    const data = await rpc("_stats", {});
    res.setHeader("Cache-Control", "no-store");
    return res.status(200).json(data);
  } catch (e) {
    return res.status(500).json({ error: String(e && e.message || e) });
  }
};
