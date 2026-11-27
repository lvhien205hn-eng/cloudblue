// 28/11 bản 4 · CHỈ HỌ XANH CỦA LOGO — bỏ vàng, ít màu, không màu mè, GIỮ NGUYÊN HIỆU ỨNG.
// Khách chê bản 3: "thay màu khác đi đừng chọn màu vàng · phối chỉ vài màu thôi · đừng màu mè". Bản 4 lấy NGUYÊN bản cũ (nền tươi, nút, mọi hoạt ảnh) rồi:
//   · nền xanh đêm · xanh dương = nút, tab, nhãn HOT / MỚI · XANH TRỜI = điểm nhấn duy nhất (tiền & ưu đãi) · chữ trắng
//   · đèn neon chạy viền: xanh ngọc + xanh dương (bỏ tím) · vàng / cam trang trí cũ → xanh trời · xanh lá / đỏ / vàng cam chỉ còn ở trạng thái
// Áp cho web + app PC + app Android. Chạy: node winpc/tests/web/test_web_mau.js
const fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "..", "..");
const read = p => fs.readFileSync(path.join(R, p), "utf8");
let ok = 0, all = 0;
const ck = (name, cond, extra) => { all++; if (cond) { ok++; console.log("  ✓", name); } else console.log("  ✗", name, "→", String(extra || "").slice(0, 400)); };
const block = (src, head) => { const i = src.indexOf(head + "\n"); if (i < 0) return ""; return src.slice(i, src.indexOf("\n}", i)); };
const v = (blk, k) => { const m = blk.match(new RegExp("--" + k + ":\\s*([^;]+);")); return m ? m[1].trim() : null; };
const count = (s, x) => s.split(x).length - 1;
const hue = (r, g, b) => { r /= 255; g /= 255; b /= 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn, l = (mx + mn) / 2;
  if (d < 0.08) return { h: -1, s: 0, l }; let h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; if (h < 0) h += 360; return { h, s: d / (1 - Math.abs(2 * l - 1)), l }; };

const web = read("blueroblox-site/index.html");
const i0 = web.indexOf("/* ===== 28/11 · BẢN 4: CHỈ HỌ XANH CỦA LOGO"), i1 = web.indexOf("</style>", i0);
const acc = i0 >= 0 ? web.slice(i0, i1) : "";

console.log("1. web — nền + hiệu ứng y như bản cũ");
const D = block(web, "html[data-theme=dark]{"), L = block(web, "html[data-theme=light]{");
ck("tối: nền #071226 · thẻ #0d1d3d · xanh #3d86ff / #2b6ef0", v(D, "bg") === "#071226" && v(D, "card") === "#0d1d3d" && v(D, "blue") === "#3d86ff" && v(D, "blue2") === "#2b6ef0", D);
ck("sáng: nền #f3f7fc · thẻ trắng · xanh #2b6ef0", v(L, "bg") === "#f3f7fc" && v(L, "card") === "#ffffff" && v(L, "blue") === "#2b6ef0", L);
ck("nút xanh bóng như cũ (#5c9dff → #2b6ef0, 7 chỗ)", count(web, "linear-gradient(180deg,#5c9dff,#2b6ef0)") === 7);
const KF = ["admIn", "cbdIn", "cbfloat", "cblbub", "cblfloat", "cblsheen", "cblsheensq", "cblspin", "cblswoosh", "cbltw", "ccw", "chIn", "chWave", "chWaveM", "cpv-hl", "cpv-pop", "cpv-sheen", "cw", "cw0", "dotpulse", "emGlow", "emIn", "fade", "fbmove", "fxbreathe", "fxcore", "fxspin", "goldflow", "goldline", "lineIn", "lwbulb", "lwchase", "lwdrop", "lwflash", "lwhalo", "lwhsheen", "lwhspin", "lwlid", "lwpop", "lwq", "lwray", "lwshake", "lwsheen", "lwsink", "lwtitle", "lwturn", "lwwin", "m3vpulse", "npulse", "nrun", "pcsrun", "pop", "ppshine", "pulse", "rise", "shine", "slidein", "spin", "spk", "sweep3d", "wob"];
const miss = KF.filter(k => !new RegExp("@keyframes\\s+" + k.replace("-", "\\-") + "\\b").test(web));
ck("đủ 61 hoạt ảnh của bản cũ (neon chạy, ánh lướt, vòng quay, cá voi…)", miss.length === 0, miss.join(" "));
ck("khối bản 4 KHÔNG đụng hoạt ảnh / filter / chữ hero / nút", acc && !/animation|filter|h1 em|#5c9dff|\.btn\b/.test(acc), acc.slice(0, 200));
ck("bỏ hết dấu vết bản 2 + bản 3 (nhãn MỚI riêng màu, nút 3 nấc, vàng kim --gia)",
   !web.includes('<span class="hot new">') && !web.includes("#63b6ff,#3b82f6") && !web.includes("--gia:") && !web.includes("--money:#ffc45e"));

console.log("2. web — chỉ họ xanh: xanh dương (nút / nhãn) + xanh trời (điểm nhấn) + neon xanh ngọc–xanh dương");
ck("đèn neon chạy viền: xanh ngọc 64,214,255 + xanh dương 92,157,255 (sáng: xanh trời 14,165,233 + xanh dương 37,110,240) — bỏ tím, đặt SAU luật cũ",
   acc.includes("html[data-theme]{--nc:64,214,255;--nc2:92,157,255;") && acc.includes("html[data-theme=light]{--nc:14,165,233;--nc2:37,110,240;")
   && web.indexOf("html[data-theme]{--nc:64,214,255;--nc2:176,124,255;") < i0);
ck("điểm nhấn xanh trời: tối #6fd3ff · sáng #0369a1 (tương phản 5.9:1 trên nền trắng)",
   acc.includes("html[data-theme=dark]{--ac:#6fd3ff;--ac-bt:#38bdf8;--ac-on:#04263f;") && acc.includes("html[data-theme=light]{--ac:#0369a1;--ac-bt:#0284c7;--ac-on:#ffffff;"));
ck("TIỀN = xanh trời: giá sản phẩm, giá gói (thẻ + hộp mua), 'Giá thuê từ', số dư, tổng tiền, giá ĐT đám mây, giá VPS NVMe",
   acc.includes("html[data-theme] .price,html[data-theme] .m3-plan .pp,html[data-theme] #hf-price,html[data-theme] #st-price,html[data-theme] .bal b,")
   && acc.includes("html[data-theme] .sum b,html[data-theme] .cpt-price b,html[data-theme] .vms-price b,html[data-theme] .plans button small{color:var(--ac)}")
   && acc.includes("html[data-theme] #cporderdlg .cpfoot #cp-total{color:var(--ac);"));
ck("ƯU ĐÃI = xanh trời: % giảm, 'Rẻ nhất' (thẻ sản phẩm · hộp mua · VPS NVMe)",
   acc.includes("html[data-theme] .m3-plan small em{color:var(--ac)}") && acc.includes("html[data-theme] .m3-plan.best{border-color:var(--ac-bd);background:var(--ac-bg)}")
   && acc.includes("html[data-theme] .m3-plan .tag,html[data-theme] #modal.pcauto #m-plans button .sv,html[data-theme] .vmb-d .sv{background:var(--ac-bt);color:var(--ac-on)}"));
ck("thẻ Kiếm tiền + Ưu đãi cùng 1 kiểu xanh trời (trước: xanh ngọc + vàng) · vé may mắn xanh trời",
   acc.includes("html[data-theme] :is(.cbt-earn,.cbt-ofr) .cbt-go{background:var(--ac-bt);color:var(--ac-on)}") && acc.includes("html[data-theme] .lwh-chips span.lk{"));
ck("vàng / cam trang trí cũ → xanh trời: phát mã giảm giá, nút trợ giúp, dùng thử miễn phí, đếm ngược ưu đãi, nút vòng quay, nhãn đã trả",
   ["html[data-theme] .cbd-pill{", "html[data-theme] .cbd-go{", "html[data-theme] .helpbtn{", "html[data-theme] .cpfree{", "html[data-theme=dark] .freebar .fb-cd{",
    "html[data-theme] .cpchip.help{", "html[data-theme] .lwfab b{", "html[data-theme=dark] .paidtag{", "html[data-theme] .cbo-card.cbo-drop{"].every(x => acc.includes(x)));
ck("cảnh báo trạng thái GIỮ vàng cam (còn ít hàng, đang chờ, bảo trì, trễ hạn) — không bị đổi",
   !/\.stock\.wt|\.stock\.low|\.ctvchip\.wait|\.cpwarn|\.restock|pcs-maint|\.ph-pill\.wt|pcs-prog\.late/.test(acc));
ck("nhãn HOT / MỚI: cùng 1 kiểu xanh dương + ánh lướt (hoạt ảnh goldline có sẵn)",
   acc.includes("html[data-theme] .m3-row .thumb .hot,html[data-theme] .m3-li .thumb .hot{background:linear-gradient(100deg,#2b6ef0") && count(web, '<span class="hot">') >= 2);
ck("gạch nhấn dưới tiêu đề = 2 màu đèn neon (xanh ngọc → xanh dương)", count(acc, "linear-gradient(90deg,rgb(var(--nc)),rgb(var(--nc2)))") === 2);
const cols = [...acc.matchAll(/#[0-9a-fA-F]{6}\b/g)].map(m => [parseInt(m[0].slice(1, 3), 16), parseInt(m[0].slice(3, 5), 16), parseInt(m[0].slice(5, 7), 16), m[0]])
  .concat([...acc.matchAll(/rgba?\((\d+),(\d+),(\d+)/g)].map(m => [+m[1], +m[2], +m[3], m[0]]))
  .concat([...acc.matchAll(/--nc2?:(\d+),(\d+),(\d+)/g)].map(m => [+m[1], +m[2], +m[3], m[0]]));
const bad = cols.filter(([r, g, b]) => { const x = hue(r, g, b); return x.h >= 0 && x.s > 0.25 && x.l > 0.06 && x.l < 0.97 && !(x.h >= 185 && x.h <= 232); }).map(c => c[3]);
ck("khối bản 4 chỉ có họ xanh (sắc 185°–232°) + trắng / đen — không vàng, không tím, không màu lạ", cols.length > 20 && !bad.length, bad.join(" "));
ck("KHÔNG đụng nút đang chọn, nhãn số ngày, dòng kv", !/\.vps-opts|\.shmode|\.amts|\.days-chip|\.kv b/.test(acc));
ck("giữ nguyên màu thương hiệu Discord / Telegram / Zalo + cờ Việt Nam", web.includes(".contacts a.dc{background:#5865F2}.contacts a.tg{background:#229ED9}.contacts a.zl{background:#0068ff}") && web.includes('fill="#da251d"'));

console.log("3. app PC (CloudBlue PC)");
const pc = read("pc-client/bluepc.py");
ck("bộ màu cũ: nền #071226 · thẻ #0d1d3d · xanh #3d86ff", /^BG, CARD, LINE, TXT, DIM, ACC, OK, WARN, BAD = "#071226", "#0d1d3d", "#244978", "#e8f1ff", "#9fb4d8", "#3d86ff"/m.test(pc));
ck("MONEY = #6fd3ff (xanh trời của web, bỏ vàng)", /^MONEY = "#6fd3ff"/m.test(pc) && !pc.includes('MONEY = "#ffcf4a"'));
ck("tiền = xanh trời: giá / ngày, tổng tiền (3 trang), số dư đầu cửa sổ",
   pc.includes('bg=bg, fg=MONEY, anchor="e")') && pc.includes('self.total = self.label(r, "", ("Segoe UI", 18, "bold"), MONEY)')
   && count(pc, 'self.tot_l = self.label(left, "", ("Segoe UI", 17, "bold"), MONEY)') === 2 && pc.includes('fg=MONEY, bg=CARD, cursor="hand2")'));
ck("ưu đãi = xanh trời: nhãn −x% / ngày, giá / ngày có giảm, mức nạp → mã giảm",
   pc.includes('font=("Segoe UI", 8, "bold"), tint=MONEY, padx=8, pady=1)') && pc.includes('fg=MONEY if sv >= 1 else DIM)]') && pc.includes('mã giảm {int(num(x.get(\'pct\')))}%", ("Segoe UI", 10, "bold"), MONEY)'));
ck("nhãn gói: nói về giá → xanh trời, còn lại (Bán chạy / Đề xuất) → xanh dương như HOT / MỚI của web",
   /^def deal_badge\(t\):/m.test(pc) && pc.includes('bg="#38bdf8" if deal_badge(t["badge"]) else "#2b6ef0", fg="#04263f" if deal_badge(t["badge"]) else "white"'));
ck("giữ màu phân loại gói (TIER_COLORS, admin chọn)", pc.includes('TIER_COLORS = {"blue": "#6f8cff", "teal": "#2fd3c5", "amber": "#ffb547", "violet": "#a77bff"'));

console.log("4. app Android");
const A = "android-app/app/src/main/java/shop/blueroblox/app/";
const ui = read(A + "Ui.java");
ck("Ui.apply: bộ màu cũ — sáng nền (243, 247, 252) · xanh (43, 110, 240) — tối nền (7, 18, 38) · xanh (61, 134, 255)",
   ui.includes("BG = Color.rgb(243, 247, 252)") && ui.includes("BLUE = Color.rgb(43, 110, 240)") && ui.includes("BG = Color.rgb(7, 18, 38)") && ui.includes("BLUE = Color.rgb(61, 134, 255)"));
ck("Ui.MONEY = xanh trời của web: (3, 105, 161) sáng · (111, 211, 255) tối", ui.includes("MONEY = Color.rgb(3, 105, 161);") && ui.includes("MONEY = Color.rgb(111, 211, 255);"));
ck("nút bóng như cũ (92, 157, 255) → (43, 110, 240)", ui.includes("new int[]{Color.rgb(92, 157, 255), Color.rgb(43, 110, 240)}"));
const ma = read(A + "MainActivity.java"), ti = read(A + "Tiers.java"), of = read(A + "Offers.java");
ck("tiền = xanh trời: số dư (chip đầu + trang tài khoản), tổng tiền khi thuê, giá gói",
   count(ma, "Ui.MONEY") === 3 && ti.includes("TextView p = Ui.text(c, Ui.vnd(perDay), 17, Ui.MONEY, true);"));
ck("ưu đãi = xanh trời: mã giảm của bạn, mức nạp → mã, −x% ở VPS GPU / VPS NVMe",
   of.includes("15, ok ? Ui.MONEY : Ui.MUTED, true);") && count(of, "Ui.MONEY") === 3
   && read(A + "PcVps.java").includes('Ui.L(" / ngày", " / day"), Ui.MONEY)') && read(A + "VmNvme.java").includes('"−" + save + "%", Ui.MONEY)'));
ck("nhãn gói: nói về giá → xanh trời, còn lại → xanh dương (bỏ đỏ–cam, bỏ vàng)",
   ti.includes("static boolean deal(String b)") && ti.includes("deal ? new int[]{Color.rgb(125, 211, 252), Color.rgb(56, 189, 248)} : new int[]{Color.rgb(92, 157, 255), Color.rgb(43, 110, 240)}"));
ck("phát mã giảm giá (Drop) = xanh trời như web", read(A + "Drop.java").includes("AMBER = Color.rgb(56, 189, 248), AMBER_HI = Color.rgb(125, 211, 252), INK = Color.rgb(4, 38, 63);"));
ck("colors.xml: màu cũ nền #FF060A1C", read("android-app/app/src/main/res/values/colors.xml").includes("#FF060A1C"));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
