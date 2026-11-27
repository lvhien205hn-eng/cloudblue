// 27/11j · Card đồ hoạ KẸT XUNG NGHỈ trên thẻ máy chủ (web admin): win3 27/11 bận 98% mà 139/1974 MHz, 9/180 W, card báo "SW Power Cap".
// Trước đây web hiện "98% (thật ~7%)" = hiểu nhầm là card rảnh. Nay: báo đỏ ở thẻ + dòng cảnh báo đỏ đầu trang quản trị.
// Chạy: node winpc/tests/web/test_web_gpustuck.js
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "..", "blueroblox-site", "index.html"), "utf8");
let ok = 0, all = 0;
const ck = (name, cond, extra) => { all++; if (cond) { ok++; console.log("  ✓", name); } else console.log("  ✗", name, "→", String(extra || "").slice(0, 600)); };
const grab = re => { const m = src.match(re); if (!m) throw new Error("không thấy: " + re); return m[0]; };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
eval(grab(/function gpuStuck\(x\) \{[\s\S]*?\n\}/));
eval(grab(/const nAge = n => [^\n]+/).replace("const nAge", "var nAge"));
eval(grab(/function nodeAlerts\(nodes\) \{[\s\S]*?\n\}/));
const now = new Date().toISOString();
const node = (name, gpu, extra) => Object.assign({ name, enabled: true, updated_at: now, alloc_ram: 40, cap_ram: 100, ram_total: 128, alloc_cpu: 30, cap_cpu: 100, cpu_total: 100, limit_pct: 85,
  metrics: { gpus: [gpu], disk_data: { used: 100, total: 476 } } }, extra || {});
const win3 = { name: "NVIDIA GeForce GTX 1080", util: 98, clk: 139, clk_max: 1974, pwr: 9.35, pwr_max: 180, mem_used: 4128, mem_total: 8192, temp: 37 };
const ok1 = { name: "NVIDIA GeForce GTX 1080", util: 16, clk: 1708, clk_max: 2012, pwr: 43, pwr_max: 200, mem_used: 3057, mem_total: 8192, temp: 48 };
const idle = { name: "NVIDIA GeForce GTX 1080", util: 30, clk: 139, clk_max: 1974, pwr: 9, pwr_max: 180 };
const ramp = { name: "NVIDIA GeForce GTX 1070", util: 95, clk: 300, clk_max: 1987, pwr: 150, pwr_max: 230 };
console.log("1. gpuStuck");
ck("win3: bận 98% · 139/1974 MHz · 9/180 W → KẸT", gpuStuck(win3) === true);
ck("card khoẻ 1708/2012 MHz → không kẹt", gpuStuck(ok1) === false);
ck("card đang nghỉ thật (bận 30% ở xung nghỉ) → không kẹt", gpuStuck(idle) === false);
ck("card vừa lên tải (xung chưa kịp lên nhưng điện đã cao) → không kẹt", gpuStuck(ramp) === false);
ck("máy chủ cũ không báo xung / điện → không kết luận", gpuStuck({ util: 99 }) === false && gpuStuck(null) === false);
console.log("2. cảnh báo đầu trang quản trị (nodeAlerts)");
const al = nodeAlerts([node("Server-3 120", win3), node("Server 2", ok1)]);
const st = al.filter(a => /KẸT XUNG NGHỈ/.test(a[1]));
ck("máy chủ có card kẹt → 1 dòng ĐỎ: tên máy chủ + xung + cách sửa (khởi động lại · dây nguồn 8 pin · ngừng nhận máy)",
   st.length === 1 && st[0][0] === "r" && /Server-3 120/.test(st[0][1]) && /139\/1974 MHz, 9 W/.test(st[0][1]) && /Khởi động lại/.test(st[0][1]) && /8 pin/.test(st[0][1]) && /Ngừng nhận máy/.test(st[0][1]), JSON.stringify(al));
ck("máy chủ card khoẻ → không có dòng kẹt xung", !al.some(a => /Server 2/.test(a[1]) && /KẸT/.test(a[1])));
const off = node("Server-3 120", win3, { updated_at: new Date(Date.now() - 10 * 60000).toISOString() });
ck("máy chủ mất kết nối → chỉ báo mất kết nối (số card cũ không tính)", !nodeAlerts([off]).some(a => /KẸT/.test(a[1])) && nodeAlerts([off]).some(a => /mất kết nối/.test(a[1])));
console.log("3. thẻ máy chủ");
ck("dòng card dùng gpuStuck: nhãn ⚠ KẸT XUNG, ghi 'chỉ xung/xung MHz · W', thanh theo % bận (đỏ), chú thích cách sửa",
   /const sk = gpuStuck\(x\)/.test(src) && src.includes("⚠ KẸT XUNG</b>") && src.includes("` · chỉ ${Math.round(x.clk)}/${Math.round(x.clk_max)} MHz`")
   && src.includes("sk ? x.util : x.eff ?? x.util") && src.includes("⚠ CARD KẸT XUNG NGHỈ"));
ck("không còn chú thích sai 'xung thấp = card đang nghỉ: % báo cao nhưng còn dư nhiều'", !src.includes("% báo cao nhưng còn dư nhiều"));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
