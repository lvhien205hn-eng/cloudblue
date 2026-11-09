// Đọc số liệu tổng của shop (JSON) — CHỈ ADMIN. Khoá luôn, kể cả khi chưa đặt biến môi trường nào.
// Mở được bằng 1 trong 2 cách:
//   • GET /api/stats?key=XXX  (hoặc header Authorization: Bearer XXX) — XXX = STATS_KEY hoặc CRON_SECRET trên Vercel
//   • Gửi kèm mã đăng nhập của tài khoản admin (Authorization: Bearer <mã đăng nhập>)
const { rpc, whoAmI, same } = require("./_lib");
module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const given = (req.query && req.query.key) || String(req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  let ok = [process.env.STATS_KEY, process.env.CRON_SECRET].some(s => s && same(given, s));
  if (!ok) { const who = await whoAmI(req); ok = !!(who && who.admin); }
  if (!ok) return res.status(401).json({ error: "unauthorized" });
  try {
    const data = await rpc("_stats", {});
    return res.status(200).json(data);
  } catch (e) {
    return res.status(500).json({ error: "stats" });
  }
};
