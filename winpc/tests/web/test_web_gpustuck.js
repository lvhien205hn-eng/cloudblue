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
console.log("4. thẻ máy chủ · tối ưu như ISO + phần mềm trên máy (cloudphoned 27/11k báo metrics.sw.tune / inv)");
eval(grab(/function nodeTune\(s\) \{[\s\S]*?\n\}/));
const t1 = nodeTune({ tune: { ok: true, did: ["chế độ điện hiệu năng cao nhất", "Defender bỏ qua 2 thư mục + 8 chương trình"], miss: [], defender: "ok", av: [], whea: 0 },
  inv: { os: "Windows 10 Pro 22H2 (build 19045.5131)", emu: ["MuMu 4.1.21.3240"], vga: ["NVIDIA GeForce GTX 1080 · driver 560.94 (2024-08-14)"], adb: "35.0.2", tools: [] } });
ck("máy cũ vừa được tối ưu → 'Tối ưu như ISO: ✓ vừa làm …' + 'Trên máy: Windows · MuMu · card driver · adb'",
   /Tối ưu như ISO<\/span><em>✓ vừa làm: chế độ điện hiệu năng cao nhất · Defender bỏ qua 2 thư mục/.test(t1) && /Trên máy<\/span><em>Windows 10 Pro 22H2 \(build 19045\.5131\) · MuMu 4\.1\.21\.3240 · GTX 1080 · driver 560\.94 · adb 35\.0\.2/.test(t1), t1);
const t2 = nodeTune({ tune: { ok: true, did: [], miss: ["chế độ điện"], defender: "none", av: ["Kaspersky <b>"], whea: 3 }, inv: { tools: ["MSI Afterburner"] } });
ck("còn thiếu / diệt virus khác / RAM lỗi / phần mềm chỉnh card → tô vàng, chữ được thoát HTML",
   /còn thiếu: chế độ điện · không có Defender · diệt virus khác: Kaspersky &lt;b&gt; · ⚠ RAM báo lỗi 3 lần/.test(t2) && /gold-hi/.test(t2) && /Phần mềm chỉnh card<\/span><em>MSI Afterburner/.test(t2), t2);
ck("đã đủ → '✓ đủ'; máy chủ chưa lên bản 27/11j (không có tune / inv) → không hiện gì", /✓ đủ/.test(nodeTune({ tune: { ok: true, did: [], miss: [] } })) && nodeTune({}) === "" && nodeTune(null) === "" && nodeTune({ tune: { ok: false } }) === "");
const fat = 1764230400, fd = new Date(fat * 1000), p2 = x => String(x).padStart(2, "0");
const fstamp = `${p2(fd.getDate())}/${p2(fd.getMonth() + 1)} ${p2(fd.getHours())}:${p2(fd.getMinutes())}`;
const t3 = nodeTune({ tune: { ok: true, did: [], miss: [], fix: { at: fat, did: ["chế độ điện hiệu năng cao nhất", "tắt Game DVR <i>"] } } });
ck("27/11l · máy cũ đã được sửa ở lần trước, nay ✓ đủ → thêm dòng 'Đã sửa ngày giờ: …' (chữ được thoát HTML)",
   /✓ đủ/.test(t3) && t3.includes(`Đã sửa ${fstamp}</span><em>chế độ điện hiệu năng cao nhất · tắt Game DVR &lt;i&gt;</em>`), t3);
const t4 = nodeTune({ tune: { ok: true, did: ["tắt Game DVR"], miss: [], fix: { at: fat, did: ["tắt Game DVR"] } } });
ck("… lần này vừa sửa (đã hiện '✓ vừa làm') → không lặp dòng 'Đã sửa'; fix hỏng (không phải object / did rỗng) → bỏ qua",
   /✓ vừa làm: tắt Game DVR/.test(t4) && !/Đã sửa/.test(t4) && !/Đã sửa/.test(nodeTune({ tune: { ok: true, did: [], fix: "x" } }))
   && !/Đã sửa/.test(nodeTune({ tune: { ok: true, did: [], fix: { at: fat, did: [] } } })) && /<span>Đã sửa<\/span>/.test(nodeTune({ tune: { ok: true, did: [], fix: { did: ["không ngủ"] } } })), t4);
ck("nodeSw gắn thêm nodeTune (cùng chỗ dòng Phần mềm máy chủ)", src.includes("<em>${esc(txt)}</em></div>` + nodeTune(s);"));
console.log(`${ok}/${all} dat`);
process.exit(ok === all ? 0 : 1);
