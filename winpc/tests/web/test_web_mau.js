// 27/11 bản 2 · MÀU TƯƠI + ĐIỂM NHẤN: bản phối "xanh mây" phẳng (bản 1) bị chê "thô, không có màu nhấn" → quay về bộ màu
// tươi cũ (xanh điện #3d86ff / #2b6ef0, nền đêm #071226) rồi thêm điểm nhấn cho cả web + app PC + app Android:
//   · tiền (giá, tổng, số dư) màu vàng cam   · nhãn HOT cam ấm · nhãn MỚI xanh trời   · nút xanh bóng 3 nấc
//   · vệt neon xanh trời + xanh logo (không còn tím)   · tiêu đề mục có gạch nhấn xanh trời → cam
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
const count = (s, x) => s.split(x).length - 1;

console.log("1. web — nền tươi như bản cũ");
const web = read("blueroblox-site/index.html");
const D = block(web, "html[data-theme=dark]{"), L = block(web, "html[data-theme=light]{");
ck("tối: nền #071226 · thẻ #0d1d3d · xanh #3d86ff / #2b6ef0 · trời #8cc4ff", v(D, "bg") === "#071226" && v(D, "card") === "#0d1d3d" && v(D, "blue") === "#3d86ff" && v(D, "blue2") === "#2b6ef0" && v(D, "sky") === "#8cc4ff", D);
ck("sáng: nền #f3f7fc · thẻ trắng · xanh #2b6ef0 · chữ #0a1a3a", v(L, "bg") === "#f3f7fc" && v(L, "card") === "#ffffff" && v(L, "blue") === "#2b6ef0" && v(L, "fg") === "#0a1a3a", L);
ck("không còn bộ màu phẳng của bản 1 (#0d1c42 / #e5eef9 / #4a80db làm nền-chữ-nút)", !web.includes("--bg:#0d1c42") && !web.includes("--bg:#e5eef9") && !web.includes("--blue:#4a80db"));

console.log("2. web — điểm nhấn");
ck("vệt neon: xanh trời 98,214,255 + xanh logo 79,141,255 (tối) · 14,165,233 + 37,99,235 (sáng) — hết tím",
   web.includes("html[data-theme]{--nc:98,214,255;--nc2:79,141,255;") && web.includes("html[data-theme=light]{--nc:14,165,233;--nc2:37,99,235;") && !/--nc2?:(176,124,255|139,92,246)/.test(web));
ck("màu tiền: vàng cam #ffc45e (tối) · cam đậm #b85c00 (sáng) — giá ở thẻ chính + dải số liệu",
   web.includes("html[data-theme=dark]{--money:#ffc45e;--acc:#ffb547;--glow:#62d6ff}") && web.includes("html[data-theme=light]{--money:#b85c00;--acc:#e07800;--glow:#0ea5e9}")
   && web.includes("html[data-theme] #hf-price,html[data-theme] #st-price{color:var(--money)}"));
ck("nút chính xanh bóng 3 nấc #63b6ff → #3b82f6 → #2563eb (thay #5c9dff → #2b6ef0)",
   count(web, "linear-gradient(180deg,#63b6ff,#3b82f6 48%,#2563eb)") === 7 && !web.includes("linear-gradient(180deg,#5c9dff,#2b6ef0)"));
ck("nhãn HOT cam ấm · nhãn MỚI xanh trời (3 chỗ dùng 'hot new')",
   web.includes("linear-gradient(180deg,#ffd27a,#ff9a3c)") && web.includes("linear-gradient(180deg,#8fe6ff,#2bb8f3)") && count(web, '<span class="hot new">') === 3);
ck("chữ nổi bật ở hero chuyển xanh trời → xanh logo (tối + sáng)",
   web.includes("html[data-theme] .hero.m3h h1 em{background:linear-gradient(100deg,#8ce8ff 0%,#5cc2ff 42%,#4f8dff 100%)") && web.includes("html[data-theme=light] .hero.m3h h1 em{background:linear-gradient(100deg,#0ea5e9 0%,#2563eb 68%,#1d4ed8 100%)"));
ck("tiêu đề mục + 'Sản phẩm' có gạch nhấn xanh trời → cam",
   web.includes("html[data-theme] .m3-sh h2::after{") && web.includes("html[data-theme] #cat-title::after{") && count(web, "background:linear-gradient(90deg,var(--glow),var(--acc))") === 2);
const css = [...web.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const hexes = [...css.matchAll(/#[0-9a-fA-F]{6}(?![\w-])/g)].map(m => m[0].toLowerCase());
const vio = hexes.filter(h => { const [hh, s, l] = hsl(h); return hh >= 246 && hh < 292 && s >= 0.35 && l >= 0.25; });
ck("CSS không còn tím", vio.length === 0, [...new Set(vio)].join(" "));
ck("giữ nguyên màu thương hiệu Discord / Telegram / Zalo + cờ Việt Nam", web.includes(".contacts a.dc{background:#5865F2}.contacts a.tg{background:#229ED9}.contacts a.zl{background:#0068ff}") && web.includes('fill="#da251d"'));
ck("giữ nguyên màu phân loại gói ĐT đám mây (admin chọn màu: xanh / ngọc / tím …)", web.includes('const CPT_COLORS = { blue: "#6f8cff", teal: "#2fd3c5", amber: "#ffb547", violet: "#a77bff"'));
for (const f of ["play.html", "phone.html"]) {
  const s = read("blueroblox-site/" + f);
  ck(f + ": về bộ màu tươi cũ (không còn nền phẳng #0d1c42 của bản 1)", !s.includes("#0d1c42"));
}

console.log("3. app PC (CloudBlue PC)");
const pc = read("pc-client/bluepc.py");
ck("bộ màu tươi cũ: nền #071226 · thẻ #0d1d3d · viền #244978 · xanh #3d86ff", /^BG, CARD, LINE, TXT, DIM, ACC, OK, WARN, BAD = "#071226", "#0d1d3d", "#244978", "#e8f1ff", "#9fb4d8", "#3d86ff"/m.test(pc));
ck("có màu tiền MONEY = #ffc45e", /^MONEY = "#ffc45e"/m.test(pc));
ck("giá / ngày ở bước chọn gói + tổng tiền + số dư đầu cửa sổ dùng MONEY",
   pc.includes('pr = tk.Label(rt, text=vnd(per), font=("Segoe UI", 13, "bold"), bg=bg, fg=MONEY, anchor="e")')
   && pc.includes('self.total = self.label(r, "", ("Segoe UI", 18, "bold"), MONEY)')
   && pc.includes('self.bal = tk.Label(bp, text="…", font=("Segoe UI", 11, "bold"), fg=MONEY, bg=CARD, cursor="hand2")'));
ck("nhãn gói (🔥 Bán chạy / ⭐ Đề xuất) cam ấm như nhãn HOT của web", pc.includes('bg="#ffa53c", fg="#3a1d00", padx=8, pady=2, pill=True') && !pc.includes('bg="#ff5f6d", fg="white", padx=8'));
ck("giữ màu phân loại gói (TIER_COLORS)", pc.includes('TIER_COLORS = {"blue": "#6f8cff", "teal": "#2fd3c5", "amber": "#ffb547", "violet": "#a77bff"'));

console.log("4. app Android");
const ui = read("android-app/app/src/main/java/shop/blueroblox/app/Ui.java");
ck("Ui.apply: bộ màu tươi cũ — sáng nền (243, 247, 252) · xanh (43, 110, 240) — tối nền (7, 18, 38) · xanh (61, 134, 255)",
   ui.includes("BG = Color.rgb(243, 247, 252)") && ui.includes("BLUE = Color.rgb(43, 110, 240)") && ui.includes("BG = Color.rgb(7, 18, 38)") && ui.includes("BLUE = Color.rgb(61, 134, 255)"));
ck("Ui.MONEY: cam đậm (184, 92, 0) sáng · vàng cam (255, 196, 94) tối", ui.includes("MONEY = Color.rgb(184, 92, 0);") && ui.includes("MONEY = Color.rgb(255, 196, 94);") && ui.includes(" HINT, MONEY;"));
ck("nút xanh bóng 3 nấc như web", ui.includes("new int[]{Color.rgb(99, 182, 255), Color.rgb(59, 130, 246), Color.rgb(37, 99, 235)}"));
const ma = read("android-app/app/src/main/java/shop/blueroblox/app/MainActivity.java");
ck("số dư (chip đầu trang + trang tài khoản) + tổng tiền khi thuê dùng Ui.MONEY",
   ma.includes('balTop = Ui.pill(this, "…", Ui.MONEY);') && ma.includes('TextView total = Ui.text(this, "", 22, Ui.MONEY, true);') && count(ma, "Ui.MONEY") === 3);
const cx = read("android-app/app/src/main/res/values/colors.xml");
ck("colors.xml: về màu cũ nền #FF060A1C · xanh #FF3D7BFF", cx.includes("#FF060A1C") && cx.includes("#FF3D7BFF"));
const tiers = read("android-app/app/src/main/java/shop/blueroblox/app/Tiers.java");
ck("Tiers.java (màu phân loại gói) giữ nguyên", tiers.includes('case "teal": return Color.rgb(47, 211, 197);'));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
