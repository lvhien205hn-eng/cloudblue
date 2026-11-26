// Thử whoAmI() trong blueroblox-site/api/_lib.js (21.11l): admin phải được hàm SQL is_admin() xác nhận bằng CHÍNH phiên người gọi
// (admin đã bật xác minh 2 bước mà phiên chưa nhập mã 6 số → không phải admin). Không gọi mạng thật (fetch giả).
//   node test_api_whoami.js <đường dẫn tới _lib.js>
const path = require("path"), fs = require("fs");
const src = process.argv[2];
if (!src || !fs.existsSync(src)) { console.error("Cách dùng: node test_api_whoami.js <_lib.js>"); process.exit(2); }
process.env.SUPABASE_URL = "https://sb.test"; process.env.SUPABASE_SERVICE_ROLE_KEY = "SERVICE";
let OK = 0, FAIL = 0;
const ck = (name, cond, extra) => { if (cond) { OK++; console.log("  ✓", name); } else { FAIL++; console.log("  ✗", name, "→", JSON.stringify(extra === undefined ? null : extra).slice(0, 600)); } };
const JWT = "aaa.bbb.ccc";
let S;                                                      // tình huống của phép thử
global.fetch = async (url, opt = {}) => {
  const h = opt.headers || {}; S.calls.push({ url, auth: h.Authorization, apikey: h.apikey, method: opt.method || "GET" });
  const res = (status, body) => ({ ok: status < 300, status, json: async () => body, text: async () => JSON.stringify(body) });
  if (url === "https://sb.test/auth/v1/user") return h.Authorization === "Bearer " + JWT ? res(200, { id: "u1", email: "a@x.vn" }) : res(401, { msg: "bad jwt" });
  if (url.startsWith("https://sb.test/rest/v1/profiles?")) return res(200, [S.profile]);
  if (url === "https://sb.test/rest/v1/rpc/is_admin") { if (S.rpcThrow) throw new Error("mạng lỗi"); return S.rpcStatus ? res(S.rpcStatus, { message: "err" }) : res(200, S.isAdmin); }
  return res(404, {});
};
const { whoAmI } = require(path.resolve(src));
const req = t => ({ headers: { authorization: "Bearer " + t } });
const run = async (sc, t = JWT) => { S = Object.assign({ calls: [], profile: { username: "chu", email: "a@x.vn", role: "admin", locked: false }, isAdmin: true }, sc); return whoAmI(req(t)); };
const rpcCalls = () => S.calls.filter(c => c.url.endsWith("/rpc/is_admin"));
(async () => {
  console.log("whoAmI + xác minh 2 bước");
  let w = await run({});
  ck("admin, is_admin() = true (chưa bật 2 bước hoặc đã nhập mã) → admin", w && w.admin === true && w.uid === "u1", w);
  ck("hỏi is_admin() bằng CHÍNH mã đăng nhập của người gọi (không dùng khoá máy chủ làm Bearer)", rpcCalls().length === 1 && rpcCalls()[0].auth === "Bearer " + JWT && rpcCalls()[0].method === "POST", S.calls);
  w = await run({ isAdmin: false });
  ck("admin đã bật 2 bước mà phiên chưa nhập mã (is_admin() = false) → KHÔNG là admin", w && w.admin === false && w.username === "chu", w);
  w = await run({ rpcThrow: true });
  ck("hỏi is_admin() lỗi mạng → không là admin (chặn chứ không mở)", w && w.admin === false, w);
  w = await run({ rpcStatus: 500 });
  ck("is_admin() trả lỗi 500 → không là admin", w && w.admin === false, w);
  w = await run({ profile: { username: "khach", email: "k@x.vn", role: "user", locked: false } });
  ck("khách thường → admin = false, KHÔNG gọi is_admin() (đỡ tốn)", w && w.admin === false && rpcCalls().length === 0, S.calls);
  w = await run({ profile: { username: "chu", role: "admin", locked: true } });
  ck("admin bị khoá → admin = false, locked = true", w && w.admin === false && w.locked === true, w);
  w = await run({}, "sai.ma.nay");
  ck("mã đăng nhập sai / hết hạn → null", w === null, w);
  w = await run({}, "khong-phai-jwt");
  ck("không phải dạng JWT → null, không gọi mạng", w === null && S.calls.length === 0, S.calls);
  console.log(`\n${OK}/${OK + FAIL} đạt`); process.exit(FAIL ? 1 : 0);
})();
