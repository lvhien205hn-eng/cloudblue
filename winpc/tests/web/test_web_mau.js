// 28/11 bản 3 · MÀU NHẤN CÓ QUY TẮC + GIỮ NGUYÊN HIỆU ỨNG.
// Bản 2 bị chê "màu nhấn lôm côm, mất hiệu ứng" → lấy NGUYÊN bản cũ (nền tươi, nút, neon xanh ngọc–tím, mọi hoạt ảnh) rồi chỉ thêm màu nhấn theo 1 quy tắc:
//   · xanh logo = thương hiệu, nút, tab, nhãn HOT / MỚI (cùng 1 kiểu)
//   · vàng kim  = TIỀN & ƯU ĐÃI (giá, số dư, tổng tiền, % giảm, "Rẻ nhất", thẻ Kiếm tiền + Ưu đãi, vé may mắn) — tông vàng của thẻ Ưu đãi có sẵn
//   · xanh lá   = trạng thái tốt · đỏ = lỗi
// Áp cho web + app PC + app Android. Chạy: node winpc/tests/web/test_web_mau.js
const fs = require("fs"), path = require("path");
const R = path.join(__dirname, "..", "..", "..");
const read = p => fs.readFileSync(path.join(R, p), "utf8");
let ok = 0, all = 0;
const ck = (name, cond, extra) => { all++; if (cond) { ok++; console.log("  ✓", name); } else console.log("  ✗", name, "→", String(extra || "").slice(0, 400)); };
const block = (src, head) => { const i = src.indexOf(head + "\n"); if (i < 0) return ""; return src.slice(i, src.indexOf("\n}", i)); };
const v = (blk, k) => { const m = blk.match(new RegExp("--" + k + ":\\s*([^;]+);")); return m ? m[1].trim() : null; };
const count = (s, x) => s.split(x).length - 1;

const web = read("blueroblox-site/index.html");
const i0 = web.indexOf("/* ===== 28/11 · MÀU NHẤN CÓ QUY TẮC (bản 3)"), i1 = web.indexOf("</style>", i0);
const acc = i0 >= 0 ? web.slice(i0, i1) : "";

console.log("1. web — nền + hiệu ứng y như bản cũ");
const D = block(web, "html[data-theme=dark]{"), L = block(web, "html[data-theme=light]{");
ck("tối: nền #071226 · thẻ #0d1d3d · xanh #3d86ff / #2b6ef0", v(D, "bg") === "#071226" && v(D, "card") === "#0d1d3d" && v(D, "blue") === "#3d86ff" && v(D, "blue2") === "#2b6ef0", D);
ck("sáng: nền #f3f7fc · thẻ trắng · xanh #2b6ef0", v(L, "bg") === "#f3f7fc" && v(L, "card") === "#ffffff" && v(L, "blue") === "#2b6ef0", L);
ck("đèn neon chạy viền: xanh ngọc 64,214,255 + tím 176,124,255 (sáng: 37,110,240 + 139,92,246) như cũ",
   web.includes("html[data-theme]{--nc:64,214,255;--nc2:176,124,255;") && web.includes("html[data-theme=light]{--nc:37,110,240;--nc2:139,92,246;"));
ck("nút xanh bóng như cũ (#5c9dff → #2b6ef0, 7 chỗ)", count(web, "linear-gradient(180deg,#5c9dff,#2b6ef0)") === 7);
const KF = ["admIn", "cbdIn", "cbfloat", "cblbub", "cblfloat", "cblsheen", "cblsheensq", "cblspin", "cblswoosh", "cbltw", "ccw", "chIn", "chWave", "chWaveM", "cpv-hl", "cpv-pop", "cpv-sheen", "cw", "cw0", "dotpulse", "emGlow", "emIn", "fade", "fbmove", "fxbreathe", "fxcore", "fxspin", "goldflow", "goldline", "lineIn", "lwbulb", "lwchase", "lwdrop", "lwflash", "lwhalo", "lwhsheen", "lwhspin", "lwlid", "lwpop", "lwq", "lwray", "lwshake", "lwsheen", "lwsink", "lwtitle", "lwturn", "lwwin", "m3vpulse", "npulse", "nrun", "pcsrun", "pop", "ppshine", "pulse", "rise", "shine", "slidein", "spin", "spk", "sweep3d", "wob"];
const miss = KF.filter(k => !new RegExp("@keyframes\\s+" + k.replace("-", "\\-") + "\\b").test(web));
ck("đủ 61 hoạt ảnh của bản cũ (neon chạy, ánh kim, vòng quay, cá voi…)", miss.length === 0, miss.join(" "));
ck("khối màu nhấn KHÔNG đụng hiệu ứng: không animation / filter / đổi màu neon / chữ hero / nút", acc && !/animation|filter|--nc\s*:|--nc2\s*:|h1 em|#5c9dff|\.btn\b/.test(acc), acc.slice(0, 200));
ck("bỏ hết dấu vết bản 2 (nhãn MỚI riêng màu, nút 3 nấc, --money vàng, gạch xanh → cam)",
   !web.includes('<span class="hot new">') && !web.includes("#63b6ff,#3b82f6") && !web.includes("--money:#ffc45e") && !web.includes("var(--glow),var(--acc)"));

console.log("2. web — màu nhấn theo đúng 1 quy tắc");
ck("có khối quy tắc bản 3, vàng kim tối #ffcf4a / sáng #a86200 (đủ tương phản 4.7:1 trên nền trắng)",
   acc.includes("html[data-theme=dark]{--gia:#ffcf4a;--gia-bt:#ffc400;--gia-on:#2a1c00;") && acc.includes("html[data-theme=light]{--gia:#a86200;--gia-bt:#ffc400;--gia-on:#2a1c00;"));
ck("TIỀN = vàng: giá sản phẩm, giá gói, 'Giá thuê từ', số dư, tổng tiền, giá ĐT đám mây, giá VPS NVMe",
   acc.includes("html[data-theme] .price,html[data-theme] .m3-plan .pp,html[data-theme] #hf-price,html[data-theme] #st-price,html[data-theme] .bal b,")
   && acc.includes("html[data-theme] .sum b,html[data-theme] .cpt-price b,html[data-theme] .vms-price b{color:var(--gia)}")
   && acc.includes("html[data-theme] #cporderdlg .cpfoot #cp-total{color:var(--gia);"));
ck("ƯU ĐÃI = vàng: % giảm, 'Rẻ nhất' ở thẻ sản phẩm + hộp mua + VPS NVMe (trước là xanh lá, trùng 'còn hàng')",
   acc.includes("html[data-theme] .m3-plan small em{color:var(--gia)}") && acc.includes("html[data-theme] .m3-plan.best{border-color:var(--gia-bd);background:var(--gia-bg)}")
   && acc.includes("html[data-theme] .m3-plan .tag,html[data-theme] #modal.pcauto #m-plans button .sv,html[data-theme] .vmb-d .sv{background:var(--gia-bt);color:var(--gia-on)}"));
ck("thẻ Kiếm tiền cùng kiểu thẻ Ưu đãi (vàng) + vé may mắn vàng",
   acc.includes("html[data-theme] .cbt-earn .cbt-go{background:#ffc400;color:#2a1c00}") && acc.includes("html[data-theme] .lwh-chips span.lk{"));
ck("nhãn HOT / MỚI: cùng 1 kiểu xanh logo + ánh lướt (hoạt ảnh goldline có sẵn)",
   acc.includes("html[data-theme] .m3-row .thumb .hot,html[data-theme] .m3-li .thumb .hot{background:linear-gradient(100deg,#2b6ef0") && count(web, '<span class="hot">') >= 2);
ck("gạch nhấn dưới tiêu đề = đúng 2 màu đèn neon", count(acc, "linear-gradient(90deg,rgb(var(--nc)),rgb(var(--nc2)))") === 2);
ck("KHÔNG tô vàng chỗ không phải tiền: nút đang chọn, nhãn số ngày, dòng kv",
   !/\.vps-opts|\.shmode|\.amts|\.days-chip|\.kv b/.test(acc));
const OKC = new Set(["#ffcf4a", "#ffc400", "#2a1c00", "#a86200", "#fff3cf", "#2b6ef0", "#8cc4ff"]);
const hexes = [...acc.matchAll(/#[0-9a-fA-F]{6}\b/g)].map(m => m[0].toLowerCase()).filter(h => !OKC.has(h));
const rg = [...acc.matchAll(/rgba\((\d+),(\d+),(\d+),/g)].map(m => m.slice(1, 4).join(",")).filter(x => !["255,196,0", "214,150,0", "255,207,74", "150,100,0", "0,0,0"].includes(x));
ck("khối màu nhấn chỉ dùng họ vàng kim + xanh logo (không thêm màu lạ)", !hexes.length && !rg.length, hexes.concat(rg).join(" "));
ck("giữ nguyên màu thương hiệu Discord / Telegram / Zalo + cờ Việt Nam", web.includes(".contacts a.dc{background:#5865F2}.contacts a.tg{background:#229ED9}.contacts a.zl{background:#0068ff}") && web.includes('fill="#da251d"'));

console.log("3. app PC (CloudBlue PC)");
const pc = read("pc-client/bluepc.py");
ck("bộ màu cũ: nền #071226 · thẻ #0d1d3d · xanh #3d86ff", /^BG, CARD, LINE, TXT, DIM, ACC, OK, WARN, BAD = "#071226", "#0d1d3d", "#244978", "#e8f1ff", "#9fb4d8", "#3d86ff"/m.test(pc));
ck("MONEY = #ffcf4a (đúng tông vàng của web)", /^MONEY = "#ffcf4a"/m.test(pc));
ck("tiền = vàng: giá / ngày, tổng tiền (3 trang), số dư đầu cửa sổ",
   pc.includes('bg=bg, fg=MONEY, anchor="e")') && pc.includes('self.total = self.label(r, "", ("Segoe UI", 18, "bold"), MONEY)')
   && count(pc, 'self.tot_l = self.label(left, "", ("Segoe UI", 17, "bold"), MONEY)') === 2 && pc.includes('fg=MONEY, bg=CARD, cursor="hand2")'));
ck("ưu đãi = vàng: nhãn −x% / ngày, giá / ngày có giảm, mức nạp → mã giảm",
   pc.includes('font=("Segoe UI", 8, "bold"), tint=MONEY, padx=8, pady=1)') && pc.includes('fg=MONEY if sv >= 1 else DIM)]') && pc.includes('mã giảm {int(num(x.get(\'pct\')))}%", ("Segoe UI", 10, "bold"), MONEY)'));
ck("nhãn gói: nói về giá → vàng, còn lại (Bán chạy / Đề xuất) → xanh logo như HOT / MỚI của web",
   /^def deal_badge\(t\):/m.test(pc) && pc.includes('bg="#ffc400" if deal_badge(t["badge"]) else "#2b6ef0", fg="#2a1c00" if deal_badge(t["badge"]) else "white"'));
ck("giữ màu phân loại gói (TIER_COLORS)", pc.includes('TIER_COLORS = {"blue": "#6f8cff", "teal": "#2fd3c5", "amber": "#ffb547", "violet": "#a77bff"'));

console.log("4. app Android");
const A = "android-app/app/src/main/java/shop/blueroblox/app/";
const ui = read(A + "Ui.java");
ck("Ui.apply: bộ màu cũ — sáng nền (243, 247, 252) · xanh (43, 110, 240) — tối nền (7, 18, 38) · xanh (61, 134, 255)",
   ui.includes("BG = Color.rgb(243, 247, 252)") && ui.includes("BLUE = Color.rgb(43, 110, 240)") && ui.includes("BG = Color.rgb(7, 18, 38)") && ui.includes("BLUE = Color.rgb(61, 134, 255)"));
ck("Ui.MONEY = vàng của web: (168, 98, 0) sáng · (255, 207, 74) tối", ui.includes("MONEY = Color.rgb(168, 98, 0);") && ui.includes("MONEY = Color.rgb(255, 207, 74);"));
ck("nút bóng như cũ (92, 157, 255) → (43, 110, 240)", ui.includes("new int[]{Color.rgb(92, 157, 255), Color.rgb(43, 110, 240)}") && !ui.includes("Color.rgb(99, 182, 255)"));
const ma = read(A + "MainActivity.java"), ti = read(A + "Tiers.java"), of = read(A + "Offers.java");
ck("tiền = vàng: số dư (chip đầu + trang tài khoản), tổng tiền khi thuê, giá gói",
   count(ma, "Ui.MONEY") === 3 && ti.includes("TextView p = Ui.text(c, Ui.vnd(perDay), 17, Ui.MONEY, true);"));
ck("ưu đãi = vàng: mã giảm của bạn, mức nạp → mã, −x% ở VPS GPU / VPS NVMe",
   of.includes("15, ok ? Ui.MONEY : Ui.MUTED, true);") && count(of, "Ui.MONEY") === 3
   && read(A + "PcVps.java").includes('Ui.L(" / ngày", " / day"), Ui.MONEY)') && read(A + "VmNvme.java").includes('"−" + save + "%", Ui.MONEY)'));
ck("nhãn gói: nói về giá → vàng, còn lại → xanh logo (bỏ đỏ–cam)",
   ti.includes("static boolean deal(String b)") && ti.includes("deal ? new int[]{Color.rgb(255, 207, 74), Color.rgb(255, 196, 0)} : new int[]{Color.rgb(92, 157, 255), Color.rgb(43, 110, 240)}") && !ti.includes("Color.rgb(255, 79, 109)"));
ck("colors.xml: màu cũ nền #FF060A1C · xanh #FF3D7BFF", read("android-app/app/src/main/res/values/colors.xml").includes("#FF060A1C"));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
