// Hàm dùng chung cho NẠP TIỀN QUA GOOGLE PLAY (bản app CH Play vn.cloudblue.app). File bắt đầu bằng "_" không thành đường dẫn web.
// Đăng nhập Google Play Developer API bằng TÀI KHOẢN DỊCH VỤ Google Cloud:
//   biến môi trường PLAY_SA_JSON = toàn bộ nội dung file khoá .json (chỉ dán trên Vercel — KHÔNG đưa lên GitHub, không gửi cho ai).
//   (tuỳ chọn) PLAY_PACKAGE = tên gói app, mặc định vn.cloudblue.app
const crypto = require("crypto");

const PKG = process.env.PLAY_PACKAGE || "vn.cloudblue.app";
const API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/" + encodeURIComponent(PKG);
let tok = null, tokExp = 0;

const sha256 = s => crypto.createHash("sha256").update(String(s)).digest("hex");
// Mã tài khoản gửi kèm giao dịch (setObfuscatedAccountId trong app): băm 1 chiều — Google không thấy mã tài khoản thật.
// PHẢI giống hệt PlayPay.acct() trong app.
const acctHash = uid => sha256("cb-play:" + uid).slice(0, 40);

// Gói nạp: mã sản phẩm "cb_nap_<số nghìn>k" → số tiền cộng vào số dư. VD cb_nap_100k → 100.000đ.
// Giá khách trả do bạn đặt trong Play Console (đổi giá lúc nào cũng được, không cần sửa code).
function packAmount(id) {
  const m = /^cb_nap_(\d{1,4})k$/.exec(String(id || ""));
  if (!m) return 0;
  const k = parseInt(m[1], 10);
  return k >= 10 && k <= 5000 ? k * 1000 : 0;          // 10.000đ – 5.000.000đ
}

function sa() {
  const raw = process.env.PLAY_SA_JSON;
  if (!raw) { const e = new Error("PLAY_NOT_SETUP"); e.code = "PLAY_NOT_SETUP"; throw e; }
  let j;
  try { j = JSON.parse(raw); } catch (e) { const x = new Error("PLAY_SA_JSON_BAD"); x.code = "PLAY_NOT_SETUP"; throw x; }
  if (!j || !j.client_email || !j.private_key) { const x = new Error("PLAY_SA_JSON_BAD"); x.code = "PLAY_NOT_SETUP"; throw x; }
  return j;
}
const b64u = b => Buffer.from(b).toString("base64").replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");

// Mã truy cập Google (sống 1 giờ, giữ lại dùng chung trong lúc máy chủ còn chạy)
async function accessToken() {
  if (tok && Date.now() < tokExp - 120000) return tok;
  const s = sa(), now = Math.floor(Date.now() / 1000);
  const head = b64u(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64u(JSON.stringify({ iss: s.client_email, scope: "https://www.googleapis.com/auth/androidpublisher",
                                      aud: "https://oauth2.googleapis.com/token", iat: now, exp: now + 3600 }));
  const sig = b64u(crypto.createSign("RSA-SHA256").update(head + "." + claim).sign(s.private_key));
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: head + "." + claim + "." + sig }).toString()
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.access_token) {
    const e = new Error("GOOGLE_AUTH " + r.status + " " + (j.error_description || j.error || ""));
    e.code = "PLAY_NOT_SETUP"; throw e;
  }
  tok = j.access_token; tokExp = Date.now() + (+j.expires_in || 3600) * 1000;
  return tok;
}

// Gọi Google Play Developer API. Trả { ok, status, j } — không ném lỗi khi Google trả 4xx/5xx.
async function gp(path, opt = {}) {
  const r = await fetch(API + path, { ...opt, headers: { Authorization: "Bearer " + await accessToken(), Accept: "application/json", ...(opt.headers || {}) } });
  const t = await r.text();
  let j = {};
  try { j = t ? JSON.parse(t) : {}; } catch (e) { j = { raw: t.slice(0, 300) }; }
  return { ok: r.ok, status: r.status, j };
}

const productPath = (product, token) => `/purchases/products/${encodeURIComponent(product)}/tokens/${encodeURIComponent(token)}`;

module.exports = { PKG, sha256, acctHash, packAmount, gp, productPath };
