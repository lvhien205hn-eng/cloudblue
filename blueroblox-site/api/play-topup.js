// ▶️ NẠP TIỀN QUA GOOGLE PLAY — chỉ bản app CH Play (vn.cloudblue.app).
// App mua gói trên Google Play → gửi { token, product } lên đây kèm mã đăng nhập Supabase (Authorization: Bearer …).
// Máy chủ HỎI GOOGLE giao dịch có thật không (Google Play Developer API), có đúng tài khoản CloudBlue đã mua không
// (obfuscatedAccountId = mã băm tài khoản), rồi mới cộng tiền (SQL v31 credit_play_topup — 1 giao dịch chỉ cộng 1 lần),
// sau đó báo Google "đã giao hàng" (consume) để khách mua tiếp được. App KHÔNG BAO GIỜ tự cộng tiền.
// Biến môi trường Vercel: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PLAY_SA_JSON, (PLAY_PACKAGE), (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
const { rpc, tg, esc, vnd, body, whoAmI, rateLimitKey } = require("./_lib");
const { sha256, acctHash, packAmount, gp, productPath } = require("./_play");

// Chưa cài xong (thiếu PLAY_SA_JSON / tài khoản dịch vụ chưa có quyền) → nhắn Telegram cho shop (tối đa 1 lần / giờ).
// Tiền của khách KHÔNG mất: giao dịch chưa xác nhận thì app giữ lại, gửi lại sau; quá 3 ngày Google tự hoàn tiền cho khách.
async function setupAlert(msg) {
  try {
    if (await rateLimitKey("play-setup-alert", 1, 3600))
      await tg("⚠️ <b>Nạp Google Play chưa chạy được</b>\n" + esc(String(msg).slice(0, 300)) +
               "\nKiểm tra biến PLAY_SA_JSON trên Vercel và quyền của tài khoản dịch vụ trong Play Console (Người dùng và quyền).");
  } catch (e) { /* bỏ qua */ }
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "POST_ONLY" });
  const who = await whoAmI(req);
  if (!who) return res.status(401).json({ error: "NOT_LOGGED_IN" });
  if (who.locked) return res.status(403).json({ error: "LOCKED" });
  if (!(await rateLimitKey("play-topup:" + who.uid, 30, 600))) return res.status(429).json({ error: "PLAY_TOO_MANY" });

  let b = {};
  try { b = body(req); } catch (e) { return res.status(400).json({ error: "BAD_INPUT" }); }
  const token = String(b.token || ""), product = String(b.product || "");
  if (!/^[A-Za-z0-9._:\-]{20,2000}$/.test(token) || !/^[a-z0-9_.]{1,100}$/.test(product)) return res.status(400).json({ error: "BAD_INPUT" });
  const unit = packAmount(product);
  if (!unit) return res.status(400).json({ error: "PLAY_UNKNOWN_PRODUCT" });

  try {
    // 1) Hỏi Google: giao dịch này có thật, đã trả tiền chưa, của tài khoản nào
    const g = await gp(productPath(product, token));
    if (!g.ok) {
      if (g.status === 401 || g.status === 403) {
        await setupAlert("Google trả lỗi " + g.status + ": " + JSON.stringify(g.j).slice(0, 200));
        return res.status(503).json({ error: "PLAY_NOT_READY" });
      }
      if (g.status >= 400 && g.status < 500) return res.status(400).json({ error: "PLAY_TOKEN_INVALID" });
      return res.status(502).json({ error: "PLAY_API_ERROR" });
    }
    const p = g.j || {};
    if (p.productId && p.productId !== product) return res.status(400).json({ error: "PLAY_TOKEN_INVALID" });
    if (p.purchaseState === 2) return res.status(200).json({ ok: false, status: "pending" });      // đang chờ khách thanh toán
    if (p.purchaseState !== 0) return res.status(200).json({ ok: false, status: "cancelled" });    // đã huỷ
    if (p.purchaseType === 2) return res.status(400).json({ error: "PLAY_TOKEN_INVALID" });       // "xem quảng cáo nhận quà" — không phải tiền thật

    // 2) Đúng tài khoản đã mua (mã khuyến mãi Google Play đổi ngoài app thì không có mã tài khoản → người gửi nhận)
    const test = p.purchaseType === 0, promo = p.purchaseType === 1;
    const acct = p.obfuscatedExternalAccountId || "";
    if (acct ? acct !== acctHash(who.uid) : !promo) return res.status(403).json({ error: "PLAY_OTHER_ACCOUNT" });
    const qty = Math.min(Math.max(parseInt(p.quantity, 10) || 1, 1), 20);

    // 3) Cộng tiền (SQL: 1 giao dịch chỉ cộng 1 lần, tài khoản khoá không cộng, giao dịch THỬ chỉ admin được cộng)
    const r = await rpc("credit_play_topup", { p_user: who.uid, p_order: p.orderId || null, p_token_hash: sha256(token),
                                               p_product: product, p_amount: unit * qty, p_test: test });
    if (!r || !r.ok) return res.status(403).json({ error: "PLAY_OTHER_ACCOUNT" });

    // 4) Báo Google đã giao hàng (consume = xác nhận + cho mua lại gói này). Lỗi → app tự consume sau khi nhận "ok".
    let consumed = p.consumptionState === 1;
    if (!consumed) {
      const c = await gp(productPath(product, token) + ":consume", { method: "POST" }).catch(() => ({ ok: false }));
      consumed = !!c.ok;
      if (!consumed && p.acknowledgementState !== 1)
        await gp(productPath(product, token) + ":acknowledge", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => null);
    }

    if (!r.dup && r.credited > 0)
      await tg(`▶️ <b>NẠP GOOGLE PLAY</b>\n👤 ${esc(who.username || who.email)}\n💰 +${vnd(r.credited)} (gói ${esc(product)}${qty > 1 ? " × " + qty : ""})` +
               `${test ? "\n🧪 giao dịch THỬ" : ""}${promo ? "\n🎟 mã khuyến mãi Google Play" : ""}\n🧾 ${esc(p.orderId || "—")}`).catch(() => null);
    return res.status(200).json({ ok: true, status: r.dup ? "dup" : r.status, credited: r.credited || 0, amount: r.amount,
                                  balance: r.balance, consumed });
  } catch (e) {
    const m = String((e && e.message) || e);
    if (e && e.code === "PLAY_NOT_SETUP") { await setupAlert(m); return res.status(503).json({ error: "PLAY_NOT_READY" }); }
    if (m.includes("LOCKED")) return res.status(403).json({ error: "LOCKED" });
    console.error("play-topup", m.slice(0, 500));
    return res.status(500).json({ error: "PLAY_SERVER_ERROR" });
  }
};
