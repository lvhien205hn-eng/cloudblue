// ↩️ Giao dịch Google Play bị HOÀN TIỀN / HUỶ / CHARGEBACK (30 ngày gần nhất) → trừ lại số dư (SQL v31 reverse_play_topup).
// Khách đã tiêu hết tiền nạp rồi mới đòi hoàn → trừ được bao nhiêu thì trừ, TỰ KHOÁ tài khoản + báo đỏ 🛡️.
// Chạy tự động mỗi ngày (Vercel Cron, lịch trong vercel.json). Chạy tay: đăng nhập admin, hoặc ?key=<CRON_SECRET>.
// Biến môi trường: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PLAY_SA_JSON, CRON_SECRET, (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
const { rpc, tg, esc, vnd, whoAmI, same } = require("./_lib");
const { sha256, gp } = require("./_play");

const REASON = ["Khác", "Khách đổi ý", "Không nhận được hàng", "Lỗi sản phẩm", "Mua nhầm", "Gian lận", "Người nhà mua không xin phép",
                "Chargeback (ngân hàng đòi lại)", "Không xác nhận giao hàng trong 3 ngày"];
const SOURCE = ["khách", "shop", "Google"];

module.exports = async (req, res) => {
  const secret = process.env.CRON_SECRET;
  let ok = !!secret && (same(req.headers.authorization, `Bearer ${secret}`) || same(req.query && req.query.key, secret));
  if (!ok) { const who = await whoAmI(req); ok = !!(who && who.admin); }
  if (!ok) return res.status(401).json({ error: secret ? "unauthorized" : "Chưa đặt CRON_SECRET trên Vercel" });
  if (!process.env.PLAY_SA_JSON) return res.status(200).json({ ok: true, skipped: "Chưa đặt PLAY_SA_JSON — chưa bật nạp Google Play" });

  try {
    const start = Date.now() - 30 * 86400000 + 5 * 60000;          // Google chỉ cho xem tối đa 30 ngày
    const keys = new Set(), done = [];
    let page = null, pages = 0, seen = 0;
    do {
      const q = new URLSearchParams({ startTime: String(start), type: "0" });   // type 0 = chỉ giao dịch mua 1 lần (gói nạp)
      if (page) q.set("token", page);
      const g = await gp("/purchases/voidedpurchases?" + q.toString());
      if (!g.ok) throw new Error("Google voidedpurchases " + g.status + " " + JSON.stringify(g.j).slice(0, 300));
      for (const v of g.j.voidedPurchases || []) {
        const key = v.orderId || v.purchaseToken;
        if (!key || keys.has(key)) continue;
        keys.add(key); seen++;
        const why = `${REASON[v.voidedReason] || "Khác"} · do ${SOURCE[v.voidedSource] || "?"}`;
        const r = await rpc("reverse_play_topup", { p_order: v.orderId || null, p_token_hash: v.purchaseToken ? sha256(v.purchaseToken) : null, p_reason: why });
        if (r && r.ok && !r.dup) done.push({ ...r, why });
      }
      page = g.j.tokenPagination && g.j.tokenPagination.nextPageToken;
    } while (page && ++pages < 20);

    if (done.length) {
      const lines = done.map(x => `• ${esc(x.username)} −${vnd(x.taken)}${x.short > 0 ? ` <b>(đã tiêu ${vnd(x.short)} → TỰ KHOÁ)</b>` : ""} — ${esc(x.why)}`);
      await tg(`↩️ <b>GOOGLE PLAY HOÀN TIỀN — ${done.length} giao dịch</b>\n${lines.join("\n")}`).catch(() => null);
    }
    return res.status(200).json({ ok: true, voided: seen, reversed: done.length });
  } catch (e) {
    console.error("play-voided", e);
    return res.status(500).json({ error: String((e && e.message) || e).slice(0, 300) });
  }
};
