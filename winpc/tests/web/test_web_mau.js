// 27/11 · PHỐI MÀU THEO LOGO (cá voi xanh mây): web + app PC + app Android dùng chung 1 họ màu — xanh cá voi #4A80DB, xanh mây #A2BFE9,
// nền mây #E5EEF9 (sáng) / đêm mây #0D1C42 (tối), xanh trời #4FB3F0 cho vệt neon. Không còn xanh "điện" #2B6EF0 / tím neon.
// Chạy: node winpc/tests/web/test_web_mau.js
const fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "..", "..");
const read = p => fs.readFileSync(path.join(R, p), "utf8");
let ok = 0, all = 0;
const ck = (name, cond, extra) => { all++; if (cond) { ok++; console.log("  ✓", name); } else console.log("  ✗", name, "→", String(extra || "").slice(0, 400)); };
const hsl = hex => { const n = parseInt(hex.slice(1), 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn; if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1)); let h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; if (h < 0) h += 360; return [h, s, l]; };
const block = (src, head) => { const i = src.indexOf(head + "\n"); if (i < 0) return ""; return src.slice(i, src.indexOf("\n}", i)); };
const v = (blk, k) => { const m = blk.match(new RegExp("--" + k + ":\\s*([^;]+);")); return m ? m[1].trim() : null; };

console.log("1. web — 2 bộ màu theo logo");
const web = read("blueroblox-site/index.html");
const D = block(web, "html[data-theme=dark]{"), L = block(web, "html[data-theme=light]{");
ck("tối 'đêm mây': nền #0d1c42 · thẻ #132a5a · xanh #5b8fe6 / #4a80db · trời #9cc3f0", v(D, "bg") === "#0d1c42" && v(D, "card") === "#132a5a" && v(D, "blue") === "#5b8fe6" && v(D, "blue2") === "#4a80db" && v(D, "sky") === "#9cc3f0", D);
ck("sáng 'ngày mây': nền #e5eef9 · thẻ trắng · xanh cá voi #4a80db · chữ #12284f", v(L, "bg") === "#e5eef9" && v(L, "card") === "#ffffff" && v(L, "blue") === "#4a80db" && v(L, "fg") === "#12284f", L);
ck("vệt neon: xanh mây 127,173,231 + xanh trời 79,179,240 (tối) · xanh cá voi 74,128,219 (sáng) — hết xanh ngọc / tím",
   web.includes("html[data-theme]{--nc:127,173,231;--nc2:79,179,240;") && web.includes("html[data-theme=light]{--nc:74,128,219;--nc2:79,179,240;") && !/--nc2?:176,124,255|--nc:64,214,255/.test(web));
const css = [...web.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const hexes = [...css.matchAll(/#[0-9a-fA-F]{6}(?![\w-])/g)].map(m => m[0].toLowerCase());
const BRAND = new Set(["#5865f2", "#229ed9", "#0068ff"]);            // Discord / Telegram / Zalo — màu thương hiệu, giữ nguyên
const loud = hexes.filter(h => { const [hh, s, l] = hsl(h); return !BRAND.has(h) && hh >= 212 && hh < 246 && s > 0.76 && l >= 0.25 && l < 0.72; });
ck("CSS không còn màu xanh 'điện' (xanh dương bão hoà > 76%, không tính màu nhạt) — chỉ còn họ xanh cá voi", loud.length === 0, [...new Set(loud)].join(" "));
const vio = hexes.filter(h => { const [hh, s, l] = hsl(h); return hh >= 246 && hh < 292 && s >= 0.35 && l >= 0.25; });
ck("CSS không còn tím", vio.length === 0, [...new Set(vio)].join(" "));
ck("giữ nguyên màu thương hiệu Discord / Telegram / Zalo + cờ Việt Nam", web.includes(".contacts a.dc{background:#5865F2}.contacts a.tg{background:#229ED9}.contacts a.zl{background:#0068ff}") && web.includes('fill="#da251d"'));
ck("giữ nguyên màu phân loại gói ĐT đám mây (admin chọn màu: xanh / ngọc / tím …)", web.includes('const CPT_COLORS = { blue: "#6f8cff", teal: "#2fd3c5", amber: "#ffb547", violet: "#a77bff"'));
for (const f of ["play.html", "phone.html"]) {
  const s = read("blueroblox-site/" + f), hx = [...s.matchAll(/#[0-9a-fA-F]{6}(?![\w-])/g)].map(m => m[0].toLowerCase());
  const bad = hx.filter(h => { const [hh, s2, l] = hsl(h); return ((hh >= 212 && hh < 246 && s2 > 0.76 && l < 0.72) || (hh >= 246 && hh < 292 && s2 >= 0.35 && l < 0.88)) && l >= 0.25; });
  ck(f + ": cùng họ màu (không còn xanh điện / tím)", bad.length === 0, [...new Set(bad)].join(" "));
}

console.log("2. app PC (CloudBlue PC)");
const pc = read("pc-client/bluepc.py");
ck("nền / thẻ / viền như web tối: #0d1c42 · #132a5a · #2a4b82 · nút #74a1e7 → #3e7add", /^BG, CARD, LINE, TXT, DIM, ACC, OK, WARN, BAD = "#0d1c42", "#132a5a", "#2a4b82"/m.test(pc)
   && /^BTN_TOP, BTN_BOT = "#74a1e7", "#3e7add"/m.test(pc));
ck("cửa sổ máy (pygame) cùng tông: nền (13, 28, 66) · thanh (19, 42, 90)", /^C_BG, C_BAR, [^=]+= \(13, 28, 66\), \(19, 42, 90\)/m.test(pc));
ck("giữ màu phân loại gói (TIER_COLORS)", pc.includes('TIER_COLORS = {"blue": "#6f8cff", "teal": "#2fd3c5", "amber": "#ffb547", "violet": "#a77bff"'));

console.log("3. app Android");
const ui = read("android-app/app/src/main/java/shop/blueroblox/app/Ui.java");
ck("Ui.apply: sáng nền (229, 238, 249) · xanh (74, 128, 219) — tối nền (13, 28, 66) · thẻ (19, 42, 90) · xanh (91, 143, 230)",
   ui.includes("BG = Color.rgb(229, 238, 249)") && ui.includes("BLUE = Color.rgb(74, 128, 219)") && ui.includes("BG = Color.rgb(13, 28, 66)") && ui.includes("PANEL = Color.rgb(19, 42, 90)") && ui.includes("BLUE = Color.rgb(91, 143, 230)"));
const cx = read("android-app/app/src/main/res/values/colors.xml");
ck("colors.xml: nền #FF0D1C42 · xanh #FF4A80DB", cx.includes("#FF0D1C42") && cx.includes("#FF4A80DB"));
const tiers = read("android-app/app/src/main/java/shop/blueroblox/app/Tiers.java");
ck("Tiers.java (màu phân loại gói) giữ nguyên", tiers.includes('case "teal": return Color.rgb(47, 211, 197);'));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
