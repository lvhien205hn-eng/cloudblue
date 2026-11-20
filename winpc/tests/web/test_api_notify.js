// Thử blueroblox-site/api/pc-notify.js bằng Node, thay ./_lib bằng bản giả (không gọi mạng thật).
//   node test_api_notify.js <đường dẫn tới pc-notify.js>
const fs = require("fs"), os = require("os"), path = require("path");
const src = process.argv[2];
if (!src || !fs.existsSync(src)) { console.error("Cách dùng: node test_api_notify.js <pc-notify.js>"); process.exit(2); }
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pcn-"));
fs.copyFileSync(src, path.join(dir, "pc-notify.js"));
fs.writeFileSync(path.join(dir, "_lib.js"), `
const F = () => global.__F;                    // mỗi phép thử thay global.__F mới → luôn đọc lại
module.exports = {
  rpc: async (fn, args) => { F().rpc.push([fn, args]); const h = F().onRpc[fn]; if (!h) throw new Error("/rest/v1/rpc/" + fn + " 404 no function"); return h(args); },
  body: req => typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body || {}),
  tgTo: async (chat, text, extra) => { F().tg.push([chat, text, extra || null]); return F().onTg(text, extra); },
  mail: async (to, subject, html) => { F().mail.push([to, subject, html]); return F().onMail(); },
  esc: s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])),
  rateLimit: async () => F().allow,
  whoAmI: async () => F().who,
};`);
let OK = 0, FAIL = 0;
const ck = (name, cond, extra) => { if (cond) { OK++; console.log("  ✓", name); } else { FAIL++; console.log("  ✗", name, "→", JSON.stringify(extra === undefined ? null : extra).slice(0, 700)); } };
const ENV = ["ADMIN_EMAIL", "RESEND_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"];
function reset(env) {
  global.__F = { rpc: [], tg: [], mail: [], allow: true, who: null, onRpc: {}, onTg: () => ({ ok: true }), onMail: () => ({ id: "m1" }) };
  for (const k of ENV) delete process.env[k];
  Object.assign(process.env, env === undefined ? { ADMIN_EMAIL: "chu@shop.test", RESEND_API_KEY: "re_x", TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "99" } : env);
  return global.__F;
}
async function call(req) {
  const h = require(path.join(dir, "pc-notify.js"));
  const out = { status: 0, json: null };
  const res = { status(c) { out.status = c; return res; }, json(j) { out.json = j; return res; } };
  await h(Object.assign({ method: "POST", headers: {}, body: {} }, req), res);
  return out;
}
const A1 = { id: 11, at: "2026-11-21T03:00:00+00:00", level: "warn", kind: "pc_rent_end", msg: "⛔ Máy PC «Máy 14-85» [A · 14-85] · khách: anh Tèo đã HẾT HẠN thuê lúc 10:00 21/11 — máy đã tự tắt." };
const A2 = { id: 12, at: "2026-11-21T03:05:00+00:00", level: "crit", kind: "pc_sec", msg: "🔓 Máy PC «<img src=x onerror=alert(1)>»: bảo mật trên máy bị thay đổi (a & b) — phần mềm quản lý đã khoá lại." };
const take = (alerts, email, waiting) => () => ({ alerts, email: email !== false, waiting: waiting || 0 });

(async () => {
  console.log("1. Chặn cơ bản");
  let F = reset(), r = await call({ method: "GET" });
  ck("không phải POST → 405, không đụng cơ sở dữ liệu", r.status === 405 && F.rpc.length === 0, r);
  F = reset(); F.allow = false; r = await call({});
  ck("gọi dồn dập → 429, không đụng cơ sở dữ liệu", r.status === 429 && F.rpc.length === 0, r);

  console.log("2. Không có cảnh báo chờ");
  F = reset(); F.onRpc.pc_alerts_take = take([], true, 0); r = await call({ body: '{"from":"db"}' });
  ck("trả ok, sent 0; không gửi thư / tin nào", r.status === 200 && r.json.ok === true && r.json.sent === 0 && F.mail.length === 0 && F.tg.length === 0 && F.rpc.length === 1 && F.rpc[0][0] === "pc_alerts_take" && F.rpc[0][1].p_max === 20, [r, F.rpc]);
  F = reset(); F.onRpc.pc_alerts_take = take([], true, 0); r = await call({ body: "khong-phai-json" });
  ck("thân yêu cầu không phải JSON → vẫn chạy như {}", r.status === 200 && r.json.ok === true, r);

  console.log("3. Có cảnh báo: gộp 1 thư + 1 tin");
  F = reset(); F.onRpc.pc_alerts_take = take([A1, A2], true, 3); r = await call({});
  ck("gửi đúng 1 thư tới ADMIN_EMAIL + 1 tin Telegram", F.mail.length === 1 && F.mail[0][0] === "chu@shop.test" && F.tg.length === 1 && F.tg[0][0] === "99", [F.mail.length, F.tg.length]);
  ck("tiêu đề thư: có số cảnh báo + số khẩn", F.mail[0][1] === "[CloudBlue PC] 🚨 2 cảnh báo máy PC (1 khẩn)", F.mail[0][1]);
  ck("thân thư: đủ 2 cảnh báo, có nhãn loại + KHẨN + giờ Việt Nam, chữ của máy gửi lên đã được khử thẻ", F.mail[0][2].includes("Hết hạn thuê") && F.mail[0][2].includes("Bảo mật trên máy bị đổi") && F.mail[0][2].includes("KHẨN")
     && F.mail[0][2].includes("10:00") && F.mail[0][2].includes("&lt;img src=x onerror=alert(1)&gt;") && !F.mail[0][2].includes("<img") && F.mail[0][2].includes("a &amp; b") && F.mail[0][2].includes("cloudblue.vn/admin"), F.mail[0][2]);
  ck("tin Telegram: đủ 2 dòng, đã khử thẻ, có 🚨", F.tg[0][1].startsWith("🚨 <b>MÁY PC CHO THUÊ — 2 cảnh báo</b>") && F.tg[0][1].includes("anh Tèo") && F.tg[0][1].includes("&lt;img src=x") && !F.tg[0][1].includes("<img"), F.tg[0][1]);
  ck("trả lời chỉ có số lượng — không lộ nội dung cảnh báo cho người gọi", r.status === 200 && JSON.stringify(r.json) === JSON.stringify({ ok: true, sent: 2, mail: true, tg: true, waiting: 3 }), r.json);
  ck("gửi được → không trả gì về hàng chờ", F.rpc.length === 1, F.rpc);
  F = reset(); F.onRpc.pc_alerts_take = take([A1]); r = await call({});
  ck("1 cảnh báo → tiêu đề thư chính là nội dung cảnh báo (cắt gọn)", F.mail[0][1].startsWith("[CloudBlue PC] ⛔ Máy PC «Máy 14-85»") && F.mail[0][1].length <= 127 && !/\n/.test(F.mail[0][1]) && F.tg[0][1].startsWith("🔔 <b>"), F.mail[0][1]);

  console.log("4. Tắt mail / mail lỗi / Telegram lỗi");
  F = reset(); F.onRpc.pc_alerts_take = take([A1], false); r = await call({});
  ck("admin tắt mail → không gửi thư, chỉ Telegram; không ghi chú lỗi", F.mail.length === 0 && F.tg.length === 1 && r.json.ok === true && r.json.mail === false && r.json.tg === true && F.rpc.length === 1, [r, F.rpc]);
  F = reset({ ADMIN_EMAIL: "chu@shop.test", TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "99" }); F.onRpc.pc_alerts_take = take([A1]); F.onRpc.pc_alerts_unsend = () => 0; r = await call({});
  ck("chưa đặt RESEND_API_KEY mà Telegram gửi được → vẫn tính là đã gửi, chỉ GHI CHÚ (danh sách rỗng) để web báo mail chưa chạy", r.json.ok === true && r.json.sent === 1 && r.json.mail === false && F.mail.length === 0
     && F.rpc.length === 2 && F.rpc[1][0] === "pc_alerts_unsend" && F.rpc[1][1].p_ids.length === 0 && /chưa đặt RESEND_API_KEY trên Vercel/.test(F.rpc[1][1].p_reason) && /đã gửi qua Telegram/.test(F.rpc[1][1].p_reason), [r, F.rpc]);
  F = reset(); F.onRpc.pc_alerts_take = take([A1]); F.onRpc.pc_alerts_unsend = () => 0; F.onMail = () => ({ statusCode: 403, name: "validation_error", message: "The cloudblue.vn domain is not verified" }); r = await call({});
  ck("dịch vụ thư từ chối → ghi đúng lý do dịch vụ trả về", r.json.ok === true && r.json.mail === false && /domain is not verified/.test(F.rpc[1][1].p_reason), F.rpc);
  F = reset({}); F.onRpc.pc_alerts_take = take([A1, A2], true, 1); F.onRpc.pc_alerts_unsend = () => 2; r = await call({});
  ck("cả 2 kênh đều chưa cài → trả CẢ 2 cảnh báo về hàng chờ kèm lý do từng kênh", r.status === 200 && r.json.ok === false && r.json.error === "send" && r.json.sent === 0 && F.rpc[1][0] === "pc_alerts_unsend"
     && JSON.stringify(F.rpc[1][1].p_ids) === "[11,12]" && /mail: chưa đặt ADMIN_EMAIL/.test(F.rpc[1][1].p_reason) && /Telegram: chưa đặt TELEGRAM_BOT_TOKEN/.test(F.rpc[1][1].p_reason) && F.rpc[1][1].p_reason.length <= 200, [r, F.rpc]);
  F = reset(); F.onRpc.pc_alerts_take = take([A1]); F.onRpc.pc_alerts_unsend = () => 1; F.onMail = () => { throw new Error("fetch failed"); }; F.onTg = () => ({ ok: false, description: "Forbidden: bot was blocked by the user" }); r = await call({});
  ck("thư lỗi mạng + Telegram từ chối → trả về hàng chờ, lý do rõ", r.json.ok === false && /fetch failed/.test(F.rpc[1][1].p_reason) && /bot was blocked/.test(F.rpc[1][1].p_reason), F.rpc);
  F = reset(); F.onRpc.pc_alerts_take = take([A2]); let n = 0; F.onTg = (t, extra) => (++n === 1 ? { ok: false, description: "Bad Request: can't parse entities" } : { ok: true }); r = await call({});
  ck("Telegram báo lỗi định dạng → gửi lại dạng chữ trơn", F.tg.length === 2 && !/<b>/.test(F.tg[1][1]) && F.tg[1][2] && "parse_mode" in F.tg[1][2] && F.tg[1][2].parse_mode === undefined && r.json.tg === true, F.tg);
  F = reset(); r = await call({});
  ck("cơ sở dữ liệu chưa có hàm (chưa chạy SQL v42) → trả ok:false 'db', không gửi gì, không lộ chi tiết lỗi", r.status === 200 && JSON.stringify(r.json) === JSON.stringify({ ok: false, error: "db" }) && F.mail.length === 0 && F.tg.length === 0, r);
  F = reset(); F.onRpc.pc_alerts_take = () => ({ alerts: "x", email: true, waiting: "abc" }); r = await call({});
  ck("cơ sở dữ liệu trả dữ liệu lạ → coi như không có gì", r.json.ok === true && r.json.sent === 0 && r.json.waiting === 0, r);

  console.log("5. Nút Gửi thư thử");
  F = reset(); r = await call({ body: { test: true } });
  ck("chưa đăng nhập → 401, không gửi gì", r.status === 401 && F.mail.length === 0 && F.tg.length === 0 && F.rpc.length === 0, r);
  F = reset(); F.who = { uid: "u", admin: false }; r = await call({ body: { test: true } });
  ck("tài khoản thường → 401", r.status === 401 && F.mail.length === 0, r);
  F = reset(); F.who = { uid: "a", admin: true }; r = await call({ body: '{"test":true}' });
  ck("admin → gửi 1 thư thử + 1 tin thử, trả kết quả từng kênh, không đụng hàng chờ", r.status === 200 && r.json.ok === true && r.json.mail.ok === true && r.json.tg.ok === true && F.mail.length === 1 && /Thư thử/.test(F.mail[0][1]) && F.tg.length === 1 && F.rpc.length === 0, r);
  F = reset({ TELEGRAM_BOT_TOKEN: "t", TELEGRAM_CHAT_ID: "99" }); F.who = { uid: "a", admin: true }; r = await call({ body: { test: true } });
  ck("admin, chưa đặt ADMIN_EMAIL → báo đúng kênh mail thiếu gì", r.json.ok === true && r.json.mail.ok === false && /ADMIN_EMAIL/.test(r.json.mail.reason) && r.json.tg.ok === true, r);
  F = reset(); F.onRpc.pc_alerts_take = take([]); r = await call({ body: { test: "true" } });
  ck("test không phải đúng giá trị true → chạy như lời gọi thường", r.json.sent === 0 && F.rpc.length === 1, r);

  console.log("\n%d/%d đạt", OK, OK + FAIL);
  try { fs.rmSync(dir, { recursive: true, force: true }); } catch (e) {}
  process.exit(FAIL ? 1 : 0);
})();
