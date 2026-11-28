// 28/11c · web admin: máy chủ TỰ ngừng nhận máy khi đầy ≥ ngưỡng, tự nhận lại khi giảm đủ (cloudphoned gửi metrics.autopause)
//         + trang khách: máy mới của lệnh đổi Android đang chờ máy chủ trống → báo "đang xếp hàng chờ" thay vì "2–5 phút".
// Chạy: node winpc/tests/web/test_web_autopause.js
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "..", "blueroblox-site", "index.html"), "utf8");
let ok = 0, all = 0;
const ck = (name, cond, extra) => { all++; if (cond) { ok++; console.log("  ✓", name); } else console.log("  ✗", name, "→", String(extra || "").slice(0, 600)); };
const grab = re => { const m = src.match(re); if (!m) throw new Error("không thấy: " + re); return m[0]; };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const lwWhen = iso => "LÚC(" + iso + ")";
var SITE = {};
eval(grab(/function nresPct\(\) \{[^\n]+/));
eval(grab(/function nresMin\(\) \{[^\n]+/));
eval(grab(/function nodeAp\(n\) \{[^\n]+/));
eval(grab(/function napN\(x\) \{[^\n]+/));
eval(grab(/function nodePausePill\(n, m\) \{[\s\S]*?\n\}/));
eval(grab(/function nodePauseRow\(n\) \{[\s\S]*?\n\}/));
eval(grab(/function napNum\(k, d, lo, hi\) \{[^\n]+/));
eval(grab(/function napCfg\(\) \{[\s\S]*?\n\}/));

console.log("1. thẻ máy chủ: nhãn trạng thái + dòng ngừng");
const ap = { on: true, hold: false, lv: 96.2, pct: 95, back: 75, min: 5, at: "2026-11-28T02:48:00+00:00" };
const auto = { enabled: false, pause_hard: false, paused_at: "2026-11-28T02:48:05+00:00", metrics: { fill_pct: 96.4, autopause: ap } };
ck("tự ngừng vì đầy → nhãn 'Tự ngừng · 96%'", nodePausePill(auto, auto.metrics) === "Tự ngừng · 96%", nodePausePill(auto, auto.metrics));
const row = nodePauseRow(auto);
ck("… dòng: đầy 96.2% · ngưỡng 95% · tự nhận lại khi ≤ 75% liên tục 5 phút · từ lúc tự ngừng",
   /Tự ngừng nhận máy vì đầy 96\.2% \(ngưỡng 95%\) — tự nhận lại khi ≤ 75% liên tục 5 phút/.test(row) && row.includes("LÚC(" + ap.at + ")"), row);
const man = { enabled: false, pause_hard: false, paused_at: "2026-11-28T02:48:05+00:00", metrics: { fill_pct: 96.4 } };
ck("admin ngừng tay (máy chủ chưa có bản 28/11c / không tự ngừng) → 'Ngừng nhận máy · 96%' + luật cũ (≤ 50% sau 10 phút)",
   nodePausePill(man, man.metrics) === "Ngừng nhận máy · 96%" && /Đang ngừng — tự nhận máy lại khi dùng ≤ 50% \(sau 10 phút\)/.test(nodePauseRow(man)), nodePauseRow(man));
const hard = { enabled: false, pause_hard: true, metrics: { fill_pct: 40, autopause: ap } };
ck("⛔ Ngừng hẳn → 'Ngừng hẳn · 40%' + không tự nhận lại (kể cả sổ tự ngừng còn cũ)",
   nodePausePill(hard, hard.metrics) === "Ngừng hẳn · 40%" && /Ngừng hẳn — không tự nhận máy lại/.test(nodePauseRow(hard)) && !/Tự ngừng/.test(nodePauseRow(hard)));
const hold = { enabled: true, metrics: { fill_pct: 96, autopause: { on: false, hold: true, pct: 95, back: 75, min: 5 } } };
ck("admin bấm Nhận máy lại lúc đang đầy → dòng 'tạm không tự ngừng tới khi xuống ≤ 75%'", /tạm không tự ngừng tới khi xuống ≤ 75%/.test(nodePauseRow(hold)), nodePauseRow(hold));
ck("đang nhận máy bình thường → không có dòng ngừng", nodePauseRow({ enabled: true, metrics: { fill_pct: 60, autopause: { on: false, hold: false } } }) === "");
ck("máy chủ cũ không gửi autopause / metrics rỗng → không lỗi", nodePausePill({ enabled: false }, null) === "Ngừng nhận máy" && typeof nodePauseRow({ enabled: false }) === "string");
ck("nhãn thẻ máy chủ: đang ngừng → màu vàng (wt) + nodePausePill, trước nhánh 'Đầy'",
   src.includes('<span class="pill ${off ? "bad" : !n.enabled ? "wt" : full ? "bad" : "ok"}">${off ? "Mất kết nối " + Math.round(age) + " phút" : !n.enabled ? nodePausePill(n, m) : full ? ('));

console.log("2. cài đặt ngưỡng (⚙ Máy chủ › ⏸ Máy chủ đầy tự ngừng nhận máy)");
SITE = {}; let c = napCfg();
ck("mặc định 95% · giảm 20% → nhận lại ≤ 75% · 5 phút (khớp cloudphoned)", c.pct === 95 && c.gap === 20 && c.back === 75 && c.min === 5, JSON.stringify(c));
SITE = { node_autopause_pct: "90", node_autopause_gap: "30", node_autopause_min: "10" }; c = napCfg();
ck("90 · 30 · 10 → nhận lại ≤ 60% liên tục 10 phút", c.pct === 90 && c.back === 60 && c.min === 10, JSON.stringify(c));
SITE = { node_autopause_pct: "9" }; c = napCfg();
ck("gõ nhầm 9% → coi là 50% (như cloudphoned, không để mọi máy chủ tự ngừng)", c.pct === 50 && c.back === 30, JSON.stringify(c));
SITE = { node_autopause_pct: "0" }; c = napCfg();
ck("0% = tắt", c.pct === 0, JSON.stringify(c));
SITE = { node_autopause_pct: "abc", node_autopause_gap: "99" }; c = napCfg();
ck("ô rác → mặc định · giảm quá 50 → 50", c.pct === 95 && c.gap === 50 && c.back === 45, JSON.stringify(c));
ck("ô nhập nap-pct / nap-gap / nap-min + nút Lưu + dòng tóm tắt nằm trên ô 'tự nhận máy lại' cũ",
   /id="nap-box"[\s\S]*?id="nap-pct"[\s\S]*?id="nap-gap"[\s\S]*?id="nap-min"[\s\S]*?id="nap-save"[\s\S]*?id="nap-sum"[\s\S]*?id="nres-box"/.test(src));
ck("Lưu: kiểm số (50–100 hoặc 0 · 5–50 · 1–240) rồi saveSettings node_autopause_pct / gap / min",
   src.includes("+p === 0 || (+p >= 50 && +p <= 100)") && src.includes("saveSettings({ node_autopause_pct: p, node_autopause_gap: g, node_autopause_min: m }, null,"));
ck("mở tab ĐT đám mây (admin) → điền lại ô + tóm tắt", src.includes("const _lc2811 = loadCloudAdm; loadCloudAdm = async function () { const r = await _lc2811.apply(this, arguments); try { napFill(); } catch (e) {} return r; };"));

console.log("3. trang khách: máy mới của lệnh đổi Android đang chờ máy chủ trống");
const L = (vi, en) => vi; var myCloud = [];
eval(grab(/function cpSwNote\(p\) \{[\s\S]*?\n\}/));
const ago = m => new Date(Date.now() - m * 60000).toISOString();
const q = cpSwNote({ id: "n1", replaces: "o1", status: "pending", node: null, android: "15", created_at: ago(7) });
ck("chưa máy chủ nào nhận sau 7 phút → 'các máy chủ Android 15 đang kín chỗ … xếp hàng chờ (đã 7 phút)'",
   /các máy chủ Android 15 đang kín chỗ nên máy mới đang xếp hàng chờ \(đã 7 phút\)/.test(q) && /Máy chủ nào trống trước sẽ tạo máy cho bạn ngay/.test(q), q);
ck("… không nêu tên / loại phần mềm máy chủ", !/MuMu|LDPlayer|MEmu|cloudphoned|node|win-/i.test(q), q);
const f = cpSwNote({ id: "n1", replaces: "o1", status: "pending", node: null, android: "15", created_at: ago(1) });
ck("mới 1 phút → vẫn câu cũ '(2–5 phút)'", /đang tạo máy Android 15 \(2–5 phút\)/.test(f), f);
const w = cpSwNote({ id: "n1", replaces: "o1", status: "pending", node: "wait-old", android: "15", created_at: ago(9) });
ck("đang xoá máy cũ → câu xoá máy cũ (không phải xếp hàng)", /Đang xoá máy cũ/.test(w), w);
const g = cpSwNote({ id: "n1", replaces: "o1", status: "pending", node: "win-a", android: "15", created_at: ago(9) });
ck("đã có máy chủ nhận (đang tạo) → câu đang tạo", /đang tạo máy Android 15/.test(g) && !/xếp hàng/.test(g), g);

console.log(`${ok}/${all} đạt`);
process.exit(ok === all ? 0 : 1);
