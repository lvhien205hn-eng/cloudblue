// Cảnh báo MÁY PC CHO THUÊ về mail + Telegram của admin (SQL v42 · web 21/11a).
// POST /api/pc-notify
//   {}               → gửi các cảnh báo máy PC ĐANG CHỜ trong cơ sở dữ liệu (hết hạn thuê, máy đang thuê mất kết nối, việc lạ trên máy…):
//                      gộp thành 1 thư + 1 tin Telegram. KHÔNG cần đăng nhập: chỉ gửi cho admin những gì đang chờ, mỗi cảnh báo đúng 1 lần
//                      → gọi thừa không sinh thêm thư, người gọi không đọc được nội dung cảnh báo (chỉ nhận số lượng).
//                      Ai gọi: cơ sở dữ liệu (pg_cron + pg_net, mỗi phút khi còn cảnh báo chờ) và trang quản trị khi đang mở.
//   { test: true }   → admin đã đăng nhập: gửi 1 thư + 1 tin THỬ, trả kết quả từng kênh (nút "Gửi thư thử" ở Máy PC › 🔔 Cảnh báo).
// Biến môi trường (Vercel): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY · mail: ADMIN_EMAIL + RESEND_API_KEY (+ MAIL_FROM) · Telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
// Gửi được ít nhất 1 kênh là xong. Cả 2 kênh đều lỗi → trả cảnh báo về hàng chờ (pc_alerts_unsend), cơ sở dữ liệu tự gọi lại sau 15 phút.
const { rpc, body, tgTo, mail, esc, rateLimit, whoAmI } = require("./_lib");

const KIND = {
  pc_rent_soon: "Sắp hết hạn thuê", pc_rent_end: "Hết hạn thuê", pc_rent_boot: "Máy hết hạn bị bật lại", pc_offline: "Máy đang thuê mất kết nối",
  pc_new: "Máy mới đăng ký", pc_clock: "Đồng hồ trên máy bị chỉnh", pc_sec: "Bảo mật trên máy bị đổi", pc_hw: "Phần cứng thay đổi",
  pc_reinstall_fail: "Cài lại thất bại", pc_bad_token: "Nghi dò mã máy" };
const cut = (s, n) => String(s ?? "").slice(0, n);
const one = s => String(s ?? "").replace(/\s+/g, " ").trim();
const vnTime = t => { try { return new Date(t).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }); } catch (e) { return ""; } };
const why = (r, dflt) => { const m = r && (r.message || r.description || r.name || r.error); return cut(typeof m === "string" ? m : m ? JSON.stringify(m) : dflt, 160); };
const plain = s => String(s).replace(/<[^>]*>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

async function sendMail(subject, html) {
  const to = process.env.ADMIN_EMAIL;
  if (!to) return { ok: false, reason: "chưa đặt ADMIN_EMAIL trên Vercel" };
  if (!process.env.RESEND_API_KEY) return { ok: false, reason: "chưa đặt RESEND_API_KEY trên Vercel" };
  try { const r = await mail(to, subject, html); return r && r.id ? { ok: true } : { ok: false, reason: why(r, "dịch vụ gửi thư không nhận") }; }
  catch (e) { return { ok: false, reason: cut((e && e.message) || e, 160) }; }
}

async function sendTg(text) {
  const chat = process.env.TELEGRAM_CHAT_ID;
  if (!process.env.TELEGRAM_BOT_TOKEN || !chat) return { ok: false, reason: "chưa đặt TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trên Vercel" };
  try {
    let r = await tgTo(chat, text);
    if (r && !r.ok && /parse|entit/i.test(r.description || "")) r = await tgTo(chat, plain(text), { parse_mode: undefined });
    return r && r.ok ? { ok: true } : { ok: false, reason: why(r, "Telegram không nhận tin") };
  } catch (e) { return { ok: false, reason: cut((e && e.message) || e, 160) }; }
}

// Chữ trong cảnh báo có phần do MÁY CHO THUÊ gửi lên (tên máy, tên khách…) → luôn esc() trước khi đưa vào thư / tin.
function build(alerts) {
  const crit = alerts.filter(a => a.level === "crit").length;
  const head = alerts.length === 1 ? one(cut(alerts[0].msg, 110)) || KIND[alerts[0].kind] || "Cảnh báo máy PC" : `${alerts.length} cảnh báo máy PC${crit ? ` (${crit} khẩn)` : ""}`;
  const rows = alerts.map(a => `<tr><td style="padding:6px 12px 6px 0;white-space:nowrap;color:#667;vertical-align:top">${esc(vnTime(a.at))}</td>`
    + `<td style="padding:6px 0;vertical-align:top">${a.level === "crit" ? '<b style="color:#c0392b">KHẨN</b> · ' : ""}<b>${esc(KIND[a.kind] || cut(a.kind, 40))}</b><br>${esc(cut(a.msg, 600))}</td></tr>`).join("");
  const html = `<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b2540;line-height:1.5">`
    + `<h3 style="margin:0 0 8px">${crit ? "🚨 " : ""}Cảnh báo máy PC cho thuê</h3><table style="border-collapse:collapse">${rows}</table>`
    + `<p style="color:#667;font-size:12.5px;margin-top:14px">Xem và xử lý: <a href="https://cloudblue.vn/admin">cloudblue.vn/admin</a> › 💻 Máy PC (gia hạn, bàn giao) · 🛡️ Bảo mật (toàn bộ cảnh báo).<br>`
    + `Thư tự động của hệ thống CloudBlue — đổi / tắt ở Máy PC › 🔔 Cảnh báo.</p></div>`;
  const tg = `${crit ? "🚨" : "🔔"} <b>MÁY PC CHO THUÊ — ${alerts.length} cảnh báo</b>\n` + alerts.map(a => `• ${esc(cut(a.msg, 600))} <i>(${esc(vnTime(a.at))})</i>`).join("\n");
  return { subject: `[CloudBlue PC] ${crit && alerts.length > 1 ? "🚨 " : ""}${head}`, html, tg: cut(tg, 3900) };
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "method" });
  if (!(await rateLimit(req, "pc-notify", 30, 60))) return res.status(429).json({ ok: false, error: "slow" });
  let b = {};
  try { b = body(req) || {}; } catch (e) { b = {}; }

  if (b && b.test === true) {                                   // nút "Gửi thư thử": chỉ admin
    const who = await whoAmI(req);
    if (!who || !who.admin) return res.status(401).json({ ok: false, error: "unauthorized" });
    const when = new Date().toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
    const [ml, tg] = await Promise.all([
      sendMail("[CloudBlue PC] Thư thử — cảnh báo máy PC về mail đang chạy",
        `<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b2540;line-height:1.5"><h3 style="margin:0 0 8px">Thư thử</h3>`
        + `Cảnh báo máy PC cho thuê (hết hạn thuê, máy mất kết nối, việc lạ trên máy…) sẽ gửi về địa chỉ này.<br><span style="color:#667">${esc(when)}</span></div>`),
      sendTg(`🔔 <b>MÁY PC CHO THUÊ — tin thử</b>\nCảnh báo máy PC về Telegram đang chạy. ${esc(when)}`)]);
    return res.status(200).json({ ok: ml.ok || tg.ok, mail: ml, tg });
  }

  let take;
  try { take = await rpc("pc_alerts_take", { p_max: 20 }); }
  catch (e) { console.error("pc-notify take", e && e.message); return res.status(200).json({ ok: false, error: "db" }); }      // chưa chạy cloud-pc-v42.sql / cơ sở dữ liệu lỗi
  const alerts = (take && Array.isArray(take.alerts) ? take.alerts : []).filter(a => a && a.id != null);
  const waiting = Math.max(0, +(take && take.waiting) || 0);
  if (!alerts.length) return res.status(200).json({ ok: true, sent: 0, waiting });

  const m = build(alerts), wantMail = !(take && take.email === false), ids = alerts.map(a => a.id);
  const [tg, ml] = await Promise.all([sendTg(m.tg), wantMail ? sendMail(m.subject, m.html) : Promise.resolve({ ok: false, reason: "đang tắt" })]);
  if (!tg.ok && !ml.ok) {                                       // không kênh nào gửi được → trả về hàng chờ + ghi lý do (hiện ở Máy PC › 🔔 Cảnh báo)
    const reason = cut((wantMail ? "mail: " + ml.reason : "mail đang tắt") + " · Telegram: " + tg.reason, 200);
    try { await rpc("pc_alerts_unsend", { p_ids: ids, p_reason: reason }); } catch (e) { console.error("pc-notify unsend", e && e.message); }
    return res.status(200).json({ ok: false, sent: 0, error: "send", waiting: waiting + alerts.length });
  }
  if (wantMail && !ml.ok) {                                     // Telegram đã nhận nhưng mail thì chưa → không gửi lại (khỏi lặp tin), chỉ ghi chú để admin biết mail chưa chạy
    try { await rpc("pc_alerts_unsend", { p_ids: [], p_reason: cut("mail chưa gửi được (" + ml.reason + ") — cảnh báo đã gửi qua Telegram", 200) }); } catch (e) {}
  }
  return res.status(200).json({ ok: true, sent: alerts.length, mail: !!ml.ok, tg: !!tg.ok, waiting });
};
