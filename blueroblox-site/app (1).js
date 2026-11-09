/* BLUEROBLOX – giao diện khách + admin, nối Supabase */
"use strict";
const CFG = window.BR_CONFIG || {};
const $ = id => document.getElementById(id);

if (!CFG.supabaseUrl || CFG.supabaseUrl.includes("YOUR-")) {
  document.body.insertAdjacentHTML("afterbegin",
    '<div style="background:#ff5d73;color:#fff;padding:10px 16px;font-weight:600;text-align:center">Chưa cấu hình Supabase. Mở file config.js và dán Project URL + anon key.</div>');
}
const sb = window.supabase.createClient(CFG.supabaseUrl || "https://invalid.supabase.co", CFG.supabaseAnonKey || "x");

const CATS = [{ id: "all", name: "Tất cả" }, { id: "clone", name: "Clone Roblox" }, { id: "vps", name: "VPS GPU" }];
const HUES = { clone: 210, vps: 265 };
const BANKS = [["970422","MB Bank"],["970436","Vietcombank"],["970407","Techcombank"],["970416","ACB"],["970432","VPBank"],["970418","BIDV"],["970415","VietinBank"],["970423","TPBank"],["970403","Sacombank"],["970405","Agribank"],["970441","VIB"],["970443","SHB"],["970448","OCB"],["970426","MSB"]];
const DEF_SITE = {
  eyebrow: "// Clone Roblox · VPS GPU · Giao tự động 24/7", h1a: "Clone giá rẻ. VPS mạnh.", h1b: "Giao ngay.",
  desc: "Clone Roblox đủ loại từ acc trắng đến acc aged, cùng VPS GPU RTX để treo game, farm nhiều tab. Thanh toán xong là nhận thông tin trong mục Đơn hàng, không phải chờ admin.",
  sta: "0", stb: "0",
  n1: "ĐỌC CHÍNH SÁCH trước khi mua để biết điều kiện bảo hành và hoàn tiền.",
  n2: "DISCORD: nhận thông báo hàng mới, giveaway và cập nhật kho.",
  n3: "LIÊN HỆ: Zalo / Facebook / Email ở cuối trang.",
  zalo: "", email: "", discord: "", rate: 25000, linkDc: "", linkTg: "", linkZl: "", afterBuy: true, joinDc: "",
  about: "Chuyên Clone Roblox và VPS GPU giá rẻ, giao tự động, hỗ trợ 24/7.",
  policy: "Bảo hành đăng nhập trong 24 giờ kể từ lúc mua. Lỗi do shop sẽ được đổi hàng hoặc hoàn tiền vào số dư.\nTài khoản bị khoá do người mua vi phạm điều khoản của game không được bảo hành.",
  bankBin: "970422", bankAcc: "", bankName: "", prefix: "BR", minTop: 10000
};
const ERR = {
  INSUFFICIENT_BALANCE: "Số dư không đủ.", OUT_OF_STOCK: "Kho không còn đủ số lượng bạn chọn.", LOCKED: "Tài khoản đã bị khoá. Liên hệ hỗ trợ.",
  NOT_LOGGED_IN: "Hãy đăng nhập trước.", MIN_AMOUNT: "Số tiền thấp hơn mức nạp tối thiểu.", TOO_MANY: "Bạn có quá nhiều lệnh nạp đang chờ. Thử lại sau ít phút.",
  BAD_QTY: "Số lượng không hợp lệ.", EMPTY: "Hãy dán thông tin cần giao.", BAD_PLAN: "Gói thời gian này không còn bán. Chọn gói khác.", NO_PRODUCT: "Sản phẩm không còn tồn tại.", NOT_ADMIN: "Bạn không có quyền admin.", SELF: "Không thể tự khoá tài khoản của mình."
};
const errMsg = e => { const m = String(e && (e.message || e.error_description || e)); for (const k in ERR) if (m.includes(k)) return ERR[k]; return m || "Có lỗi, thử lại sau."; };

let SITE = { ...DEF_SITE }, P = [], cur = "VND", cat = "all", sel = null, selDays = null, editId = null;
let session = null, profile = null, curTop = null, pollT = null, stockFor = null, pfImage = "", pfFile = null;
let ADM = { users: [], topups: [], orders: [] };

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rate = () => +SITE.rate || 25000;
const fmt = v => cur === "VND" ? Math.round(v).toLocaleString("vi-VN") + "đ" : "$" + (v / rate()).toFixed(2);
const vnd = v => Math.round(+v || 0).toLocaleString("vi-VN") + "đ";
const catName = id => (CATS.find(c => c.id === id) || { name: id }).name;
const ago = t => { const s = (Date.now() - new Date(t).getTime()) / 1000; if (s < 60) return "vừa xong"; if (s < 3600) return Math.floor(s / 60) + " phút trước"; if (s < 86400) return Math.floor(s / 3600) + " giờ trước"; return new Date(t).toLocaleString("vi-VN"); };
const show = (id, on = true) => { $(id).hidden = !on; };
const plansOf = p => (Array.isArray(p.plans) ? p.plans : []).filter(x => +x.days > 0 && +x.price >= 0).sort((a, b) => a.days - b.days);
const minPrice = p => { const pl = plansOf(p); return pl.length ? Math.min(...pl.map(x => +x.price)) : +p.price; };
const isAdmin = () => !!(profile && profile.role === "admin" && !profile.locked);
function toast(t, err) { const e = $("toast"); e.textContent = t; e.className = "toast" + (err ? " err" : ""); e.hidden = false; clearTimeout(e._t); e._t = setTimeout(() => e.hidden = true, 3800); }
async function busy(btn, fn) { if (btn) btn.disabled = true; try { return await fn(); } finally { if (btn) btn.disabled = false; } }

/* ---------- VietQR (chuẩn EMVCo / NAPAS 247) ---------- */
const tlv = (id, v) => id + String(v.length).padStart(2, "0") + v;
function crc16(s) { let c = 0xFFFF; for (let i = 0; i < s.length; i++) { c ^= s.charCodeAt(i) << 8; for (let j = 0; j < 8; j++) c = (c & 0x8000) ? ((c << 1) ^ 0x1021) & 0xFFFF : (c << 1) & 0xFFFF; } return c.toString(16).toUpperCase().padStart(4, "0"); }
function vietqr(bin, acc, amount, memo) {
  const cons = tlv("00", "A000000727") + tlv("01", tlv("00", bin) + tlv("01", acc)) + tlv("02", "QRIBFTTA");
  const p = tlv("00", "01") + tlv("01", "12") + tlv("38", cons) + tlv("53", "704") + tlv("54", String(Math.round(amount))) + tlv("58", "VN") + tlv("62", tlv("08", memo)) + "6304";
  return p + crc16(p);
}

/* ---------- tải dữ liệu ---------- */
async function loadSettings() { const { data } = await sb.from("settings").select("data").eq("id", 1).maybeSingle(); SITE = { ...DEF_SITE, ...((data && data.data) || {}) }; renderSite(); renderGrid(); }
async function loadProducts() { const { data, error } = await sb.from("product_list").select("*").order("sort"); if (error) { $("grid").innerHTML = `<div class="empty">Không tải được sản phẩm. Tải lại trang để thử lại.</div>`; return; } P = data || []; renderCats(); renderGrid(); if (isAdmin()) renderTable(); }
async function loadProfile() { if (!session) { profile = null; return; } const { data } = await sb.from("profiles").select("*").eq("id", session.user.id).maybeSingle(); profile = data || null; }

/* ---------- trang khách ---------- */
function drawThumb(cv, seed, h) {
  const w = cv.width = 460, ht = cv.height = 260, x = cv.getContext("2d");
  const g = x.createLinearGradient(0, 0, w, ht); g.addColorStop(0, `hsl(${h} 80% 22%)`); g.addColorStop(1, `hsl(${(h + 40) % 360} 85% 12%)`);
  x.fillStyle = g; x.fillRect(0, 0, w, ht);
  let r = seed * 9301 + 49297; const rnd = () => ((r = (r * 9301 + 49297) % 233280) / 233280);
  for (let i = 0; i < 14; i++) { const s = 12 + rnd() * 50; x.save(); x.translate(rnd() * w, rnd() * ht); x.rotate(rnd() * .8 - .4); x.fillStyle = `hsla(${h + rnd() * 40} 90% ${50 + rnd() * 25}% / ${.15 + rnd() * .35})`; x.fillRect(-s / 2, -s / 2, s, s); x.restore(); }
  x.save(); x.translate(w / 2, ht / 2); x.rotate(.2); x.fillStyle = `hsl(${h} 95% 60%)`; x.fillRect(-38, -38, 76, 76); x.fillStyle = `hsl(${h} 80% 12%)`; x.fillRect(-12, -12, 24, 24); x.restore();
}
const seedOf = id => [...String(id)].reduce((a, c) => a + c.charCodeAt(0), 0);
function renderSite() {
  $("h-eyebrow").textContent = SITE.eyebrow;
  $("h-title").innerHTML = esc(SITE.h1a) + " <em>" + esc(SITE.h1b) + "</em>";
  $("h-desc").textContent = SITE.desc;
  $("st-a").textContent = SITE.sta; $("st-b").textContent = SITE.stb;
  $("notices").innerHTML = [SITE.n1, SITE.n2, SITE.n3].filter(Boolean).map(n => { const m = String(n).match(/^([^:]{1,30}:|[A-ZÀ-Ỹ\s]{4,}(?=\s))/u); return m ? `<div><b style="color:var(--gold)">${esc(m[0])}</b>${esc(n.slice(m[0].length))}</div>` : `<div>${esc(n)}</div>`; }).join("");
  $("ft-about").textContent = SITE.about; $("policy-text").textContent = SITE.policy;
  $("ct-zalo").textContent = SITE.zalo ? "Zalo: " + SITE.zalo : ""; $("ct-email").textContent = SITE.email ? "Email: " + SITE.email : ""; $("ct-discord").textContent = SITE.discord ? "Discord: " + SITE.discord : "";
  const jd = SITE.joinDc && /^https?:\/\//i.test(SITE.joinDc); $("join-wrap").hidden = !jd; if (jd) $("join-band").href = SITE.joinDc;
  $("year").textContent = new Date().getFullYear();
}
function renderCats() { $("cats").innerHTML = CATS.map(c => { const n = c.id === "all" ? P.length : P.filter(p => p.cat === c.id).length; return `<button data-c="${c.id}" class="${c.id === cat ? "on" : ""}">${c.name}<small>${n}</small></button>`; }).join(""); }
function renderGrid() {
  const q = $("q").value.trim().toLowerCase(), so = $("sort").value;
  let l = P.filter(p => (cat === "all" || p.cat === cat) && String(p.name).toLowerCase().includes(q));
  if (so === "asc") l.sort((a, b) => minPrice(a) - minPrice(b)); else if (so === "desc") l.sort((a, b) => minPrice(b) - minPrice(a)); else l.sort((a, b) => (b.hot ? 1 : 0) - (a.hot ? 1 : 0) || a.sort - b.sort);
  $("cat-title").textContent = cat === "all" ? "Tất cả sản phẩm" : catName(cat);
  if (!l.length) { $("grid").innerHTML = `<div class="empty">${P.length ? "Không có sản phẩm khớp “" + esc(q) + "”." : "Chưa có sản phẩm nào."}</div>`; return; }
  $("grid").innerHTML = l.map(p => {
    const s = +p.stock || 0, st = s === 0 ? ["out", "Hết hàng"] : s < 15 ? ["low", "Còn " + s] : ["ok", "Còn " + s];
    return `<article class="card"><div class="thumb">${p.image ? `<img class="thumb-img" src="${esc(p.image)}" alt="" loading="lazy">` : `<canvas data-id="${esc(p.id)}" data-c="${esc(p.thumb || p.cat)}"></canvas>`}<span class="tag">${esc(catName(p.cat).toUpperCase())}</span>${p.hot ? '<span class="hot">HOT</span>' : ""}</div>
    <div class="body"><h4>${esc(p.name)}</h4><div class="feats">${(p.features || []).map(f => `<span>${esc(f)}</span>`).join("")}</div>
    ${plansOf(p).length ? `<div class="days-chip">Gói: ${plansOf(p).map(x => x.days).join(" · ")} ngày</div>` : ""}
    <div class="row"><span class="price">${plansOf(p).length ? '<small style="font-size:12px;color:var(--muted);font-family:var(--body)">từ </small>' : ""}${fmt(minPrice(p))}</span><span class="stock ${st[0]}">${st[1]}</span></div>
    <button class="btn" data-buy="${esc(p.id)}" ${s === 0 ? "disabled" : ""}>${s === 0 ? "Hết hàng" : "Mua ngay"}</button></div></article>`;
  }).join("");
  document.querySelectorAll("canvas[data-id]").forEach(cv => drawThumb(cv, seedOf(cv.dataset.id), HUES[cv.dataset.c] ?? 210));
}
function renderUser() {
  const u = profile;
  show("guest-acts", !u); show("user-acts", !!u);
  if (u) { $("bal").textContent = fmt(u.balance); $("who-name").textContent = u.username; $("who-av").textContent = u.username[0].toUpperCase(); }
  show("admin-open", isAdmin());
  if (!isAdmin()) show("drawer", false);
}
function setCur(c) { cur = c; $("cur-vnd").classList.toggle("on", c === "VND"); $("cur-usd").classList.toggle("on", c === "USD"); renderGrid(); renderUser(); if (sel) upd(); }

/* ---------- mua hàng ---------- */
const selP = () => P.find(p => p.id === sel);
const unitPrice = p => { const pl = plansOf(p); if (!pl.length) return +p.price; const x = pl.find(x => +x.days === +selDays) || pl[0]; return +x.price; };
function renderPlans() {
  const p = selP(), pl = p ? plansOf(p) : [];
  show("m-plans-box", pl.length > 0);
  $("m-plans").innerHTML = pl.map(x => `<button type="button" data-d="${x.days}" class="${+x.days === +selDays ? "on" : ""}"><b>${x.days} ngày</b><small>${fmt(+x.price)}</small></button>`).join("");
}
$("m-plans").onclick = e => { const b = e.target.closest("button"); if (!b) return; selDays = +b.dataset.d; renderPlans(); upd(); };
function upd() {
  const p = selP(); if (!p) return; const tot = unitPrice(p) * Math.max(1, +$("m-qty").value || 1);
  $("m-total").textContent = fmt(tot);
  const u = profile; $("m-bal").textContent = u ? fmt(u.balance) : "Chưa đăng nhập";
  $("m-err").textContent = u && u.balance < tot ? "Số dư không đủ. Cần nạp thêm " + fmt(tot - u.balance) + "." : "";
  $("m-ok").textContent = !u ? "Đăng nhập để mua" : u.balance < tot ? "Nạp tiền" : "Thanh toán";
}
function openBuy(id) { sel = id; const p = selP(); const pl = plansOf(p); selDays = pl.length ? +(pl.find(x => +x.days === 30) || pl[0]).days : null;
  $("m-name").textContent = p.name; $("m-qty").value = 1; $("m-qty").max = p.stock; renderPlans(); upd(); show("modal"); }
function closeBuy() { show("modal", false); sel = null; }
async function doBuy() {
  const p = selP(); if (!p) return;
  if (!profile) { closeBuy(); openAuth("login"); return; }
  const q = Math.max(1, Math.min(+p.stock || 1, Math.floor(+$("m-qty").value || 1))), tot = unitPrice(p) * q;
  if (profile.balance < tot) { closeBuy(); openTopup(Math.max(+SITE.minTop || 10000, Math.ceil((tot - profile.balance) / 1000) * 1000)); return; }
  await busy($("m-ok"), async () => {
    const { data: ord, error } = await sb.rpc("buy_product", { p_product: p.id, p_qty: q, p_days: plansOf(p).length ? selDays : null });
    if (error) { $("m-err").textContent = errMsg(error); return; }
    closeBuy(); await Promise.all([loadProfile(), loadProducts()]); renderUser();
    if (ord && ord.status === "pending") watchMine();
    openThanks(ord, p, q, tot);
  });
}

/* ---------- đăng nhập / đăng ký / quên mật khẩu ---------- */
function authTab(t) {
  $("at-login").classList.toggle("on", t === "login"); $("at-reg").classList.toggle("on", t === "reg");
  show("f-login", t === "login"); show("f-reg", t === "reg"); show("f-forgot", t === "forgot"); show("f-newpw", t === "newpw");
  show("atabs", t === "login" || t === "reg");
  ["li-err", "rg-err", "fg-err", "np-err"].forEach(i => $(i).textContent = "");
}
function openAuth(t) { authTab(t); show("auth"); setTimeout(() => { const f = { reg: "rg-u", login: "li-e", forgot: "fg-e", newpw: "np-p" }[t]; if (f) $(f).focus(); }, 30); }
$("f-reg").onsubmit = e => { e.preventDefault(); busy($("rg-btn"), async () => {
  const u = $("rg-u").value.trim(), em = $("rg-e").value.trim(), pw = $("rg-p").value;
  if (pw !== $("rg-p2").value) { $("rg-err").textContent = "Hai mật khẩu không khớp."; return; }
  const { data: ok } = await sb.rpc("username_available", { p_username: u });
  if (ok === false) { $("rg-err").textContent = "Tên đăng nhập đã có người dùng."; return; }
  const { data, error } = await sb.auth.signUp({ email: em, password: pw, options: { data: { username: u }, emailRedirectTo: location.origin } });
  if (error) { $("rg-err").textContent = /registered/i.test(error.message) ? "Email này đã đăng ký. Dùng Quên mật khẩu nếu bạn không nhớ." : errMsg(error); return; }
  $("f-reg").reset();
  if (!data.session) { authTab("login"); $("li-e").value = em; $("li-err").textContent = ""; toast("Đã tạo tài khoản. Mở email để xác nhận rồi đăng nhập."); }
  else { show("auth", false); toast("Tạo tài khoản thành công. Chào " + u + "!"); }
}); };
$("f-login").onsubmit = e => { e.preventDefault(); busy($("li-btn"), async () => {
  const { error } = await sb.auth.signInWithPassword({ email: $("li-e").value.trim(), password: $("li-p").value });
  if (error) { $("li-err").textContent = /confirm/i.test(error.message) ? "Email chưa được xác nhận. Kiểm tra hộp thư của bạn." : "Sai email hoặc mật khẩu."; return; }
  await loadProfile();
  if (profile && profile.locked) { await sb.auth.signOut(); $("li-err").textContent = ERR.LOCKED; return; }
  $("f-login").reset(); show("auth", false); renderUser();
  if (isAdmin()) openAdmin(); else toast("Đăng nhập thành công.");
}); };
let fgEmail = "";
$("fg-send").onclick = () => busy($("fg-send"), async () => {
  fgEmail = $("fg-e").value.trim(); $("fg-err").textContent = "";
  if (!fgEmail.includes("@")) { $("fg-err").textContent = "Nhập email đã đăng ký."; return; }
  const { error } = await sb.auth.resetPasswordForEmail(fgEmail, { redirectTo: location.origin });
  if (error) { $("fg-err").textContent = /rate|seconds/i.test(error.message) ? "Bạn vừa yêu cầu mã. Chờ 1 phút rồi thử lại." : errMsg(error); return; }
  $("fg-to").textContent = fgEmail; show("fg-step1", false); show("fg-step2"); $("fg-c").focus();
});
$("fg-ok").onclick = () => busy($("fg-ok"), async () => {
  const token = $("fg-c").value.trim(), pw = $("fg-p").value;
  if (pw.length < 8) { $("fg-err").textContent = "Mật khẩu mới cần ít nhất 8 ký tự."; return; }
  const { error } = await sb.auth.verifyOtp({ email: fgEmail, token, type: "recovery" });
  if (error) { $("fg-err").textContent = "Mã không đúng hoặc đã hết hạn."; return; }
  const { error: e2 } = await sb.auth.updateUser({ password: pw });
  if (e2) { $("fg-err").textContent = errMsg(e2); return; }
  show("fg-step1"); show("fg-step2", false); $("f-forgot").reset(); show("auth", false); toast("Đã đặt lại mật khẩu. Bạn đã được đăng nhập.");
});
$("f-newpw").onsubmit = async e => { e.preventDefault();
  const { error } = await sb.auth.updateUser({ password: $("np-p").value });
  if (error) { $("np-err").textContent = errMsg(error); return; }
  show("auth", false); toast("Đã lưu mật khẩu mới.");
};
$("go-forgot").onclick = () => { authTab("forgot"); show("fg-step1"); show("fg-step2", false); };
$("fg-back").onclick = () => authTab("login");
$("at-login").onclick = () => authTab("login"); $("at-reg").onclick = () => authTab("reg");
$("auth-close").onclick = () => show("auth", false);
$("btn-login").onclick = () => openAuth("login"); $("btn-reg").onclick = () => openAuth("reg");
async function logout() { await sb.auth.signOut(); profile = null; renderUser(); toast("Đã đăng xuất."); }
$("btn-logout").onclick = logout;

/* ---------- nạp tiền ---------- */
function openTopup(pre) {
  if (!profile) { openAuth("login"); toast("Đăng nhập để nạp tiền.", 1); return; }
  if (!SITE.bankAcc) { toast("Shop chưa cài tài khoản nhận tiền. Liên hệ hỗ trợ.", 1); return; }
  $("tp-amts").innerHTML = [20000, 50000, 100000, 200000, 500000, 1000000, 2000000, 5000000].map(v => `<button data-v="${v}">${(v / 1000).toLocaleString("vi-VN")}k</button>`).join("");
  $("tp-amt").value = pre || 50000; $("tp-amt").min = +SITE.minTop || 10000; markAmt();
  show("tp-step1"); show("tp-step2", false); $("tp-err").textContent = ""; show("topup");
}
function markAmt() { document.querySelectorAll("#tp-amts button").forEach(b => b.classList.toggle("on", +b.dataset.v === +$("tp-amt").value)); }
$("tp-amts").onclick = e => { const b = e.target.closest("button"); if (!b) return; $("tp-amt").value = b.dataset.v; markAmt(); };
$("tp-amt").oninput = markAmt;
$("tp-make").onclick = () => busy($("tp-make"), async () => {
  const a = Math.round(+$("tp-amt").value || 0), mn = +SITE.minTop || 10000;
  if (a < mn) { $("tp-err").textContent = "Số tiền tối thiểu là " + vnd(mn) + "."; return; }
  const { data, error } = await sb.rpc("create_topup", { p_amount: a });
  if (error) { $("tp-err").textContent = errMsg(error); return; }
  curTop = data;
  const bank = BANKS.find(b => b[0] === SITE.bankBin);
  $("tp-bank").textContent = bank ? bank[1] : SITE.bankBin; $("tp-acc").textContent = SITE.bankAcc; $("tp-name").textContent = SITE.bankName;
  $("tp-money").textContent = vnd(a); $("tp-money-raw").textContent = String(a); $("tp-memo").textContent = data.memo;
  try { const qr = qrcode(0, "M"); qr.addData(vietqr(SITE.bankBin, String(SITE.bankAcc).replace(/\D/g, ""), a, data.memo)); qr.make(); $("tp-qr").innerHTML = qr.createSvgTag(4, 0); }
  catch (e) { $("tp-qr").innerHTML = '<div style="color:#333;font-size:12px;padding:12px">Không tạo được QR. Chuyển khoản theo thông tin bên cạnh.</div>'; }
  $("tp-wait").className = "wait"; $("tp-wait-t").textContent = "Đang chờ ngân hàng báo có… Giữ đúng nội dung chuyển khoản.";
  show("tp-step1", false); show("tp-step2"); startPoll();
});
function startPoll() {
  clearInterval(pollT); const started = Date.now();
  pollT = setInterval(async () => {
    if (!curTop || Date.now() - started > 20 * 60 * 1000 || $("topup").hidden) { clearInterval(pollT); return; }
    const { data } = await sb.from("topups").select("status,amount").eq("id", curTop.id).maybeSingle();
    if (data && data.status === "done") {
      clearInterval(pollT); $("tp-wait").className = "wait done"; $("tp-wait-t").textContent = "Đã nhận " + vnd(data.amount) + ". Số dư đã được cộng.";
      await loadProfile(); renderUser(); toast("Nạp thành công +" + vnd(data.amount));
    }
  }, 4000);
}
$("tp-back").onclick = () => { clearInterval(pollT); show("tp-step1"); show("tp-step2", false); };
$("tp-close").onclick = () => { clearInterval(pollT); show("topup", false); };
document.querySelectorAll("[data-copy]").forEach(b => b.onclick = async () => {
  const t = $(b.dataset.copy).textContent;
  try { await navigator.clipboard.writeText(t); b.textContent = "Đã chép"; setTimeout(() => b.textContent = "Chép", 1500); }
  catch (e) { const r = document.createRange(); r.selectNodeContents($(b.dataset.copy === "tp-money-raw" ? "tp-money" : b.dataset.copy)); getSelection().removeAllRanges(); getSelection().addRange(r); }
});

/* ---------- cảm ơn sau khi mua ---------- */
function contactsHTML() {
  const list = [["dc", "Discord", "🎮", SITE.linkDc], ["tg", "Telegram", "✈️", SITE.linkTg], ["zl", "Zalo", "💬", SITE.linkZl]].filter(x => x[3] && /^https?:\/\//i.test(x[3]));
  return list.map(x => `<a class="${x[0]}" href="${esc(x[3])}" target="_blank" rel="noopener"><span class="ci">${x[2]}</span>Nhắn qua ${x[1]}<small>mở ${x[0] === "zl" ? "Zalo" : x[1]}</small></a>`).join("");
}
const safeName = s => String(s || "file").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "file";
function downloadTxt(filename, text) {
  try { const blob = new Blob([text], { type: "text/plain;charset=utf-8" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
  catch (e) { toast("Trình duyệt chặn tải file. Hãy copy thủ công.", 1); }
}
let thMsg = "", thDl = null;
function openThanks(ord, p, q, tot) {
  const label = `${p.name}${plansOf(p).length ? " · " + selDays + " ngày" : ""}`;
  $("th-sum").textContent = `${label} × ${q} · ${fmt(tot)}`;
  const auto = ord && ord.status === "done" && ord.items;
  if (auto) {
    // giao tự động: hiện tài khoản + nút tải .txt
    const n = ord.items.split("\n").filter(l => l.trim()).length;
    thMsg = ord.items; thDl = { name: `BLUEROBLOX-${safeName(p.name)}-${Date.now()}.txt`, text: ord.items };
    $("th-title").textContent = "Mua thành công!";
    $("th-info").textContent = `✓ Đã giao ${n} tài khoản`;
    $("th-copy").textContent = "📋 Copy tất cả"; show("th-dl");
    $("th-note").innerHTML = "Bấm <b>Tải file .txt</b> để lưu về máy. Xem lại bất cứ lúc nào trong mục <b>Đơn hàng</b>.";
    $("th-contacts").innerHTML = ""; show("thanks"); return;
  }
  // giao thủ công: dẫn tới kênh liên hệ
  const c = contactsHTML();
  thMsg = `[BLUEROBLOX] Mình vừa mua hàng, cần nhận:\n• Sản phẩm: ${label} × ${q}\n• Đã thanh toán: ${fmt(tot)}\n• Khách: ${profile ? profile.username : ""}${ord && ord.id ? "\n• Mã đơn: " + ord.id : ""}`;
  thDl = null; show("th-dl", false);
  if (!SITE.afterBuy || !c) { toast("Đặt hàng thành công. Xem mục Đơn hàng."); openOrders(); return; }
  $("th-title").textContent = "Đặt hàng thành công!";
  $("th-info").textContent = thMsg; $("th-copy").textContent = "📋 Copy thông tin đơn";
  $("th-note").innerHTML = "Bấm <b>Copy</b>, rồi bấm một kênh bên dưới và <b>dán + gửi</b> cho shop để nhận hàng.";
  $("th-contacts").innerHTML = c; show("thanks");
}
$("th-dl").onclick = () => { if (thDl) downloadTxt(thDl.name, thDl.text); };
$("th-copy").onclick = async () => {
  const base = $("th-copy").textContent;
  try { await navigator.clipboard.writeText(thMsg); $("th-copy").textContent = "✓ Đã copy"; setTimeout(() => $("th-copy").textContent = base, 2000); }
  catch (e) { const r = document.createRange(); r.selectNodeContents($("th-info")); getSelection().removeAllRanges(); getSelection().addRange(r); toast("Bôi đen sẵn rồi, bấm Ctrl+C để copy.", 0); }
};
$("th-close").onclick = () => show("thanks", false);
$("th-orders").onclick = () => { show("thanks", false); openOrders(); };

/* ---------- đơn hàng của khách ---------- */
const ordPill = s => s === "pending" ? '<span class="pill wt">Đang chuẩn bị</span>' : s === "refunded" ? '<span class="pill bad">Đã huỷ · hoàn tiền</span>' : '<span class="pill ok">Đã giao</span>';
let minePending = null, mineT = null, myOrders = [];
async function watchMine() {
  clearInterval(mineT); if (!profile) return;
  const check = async () => {
    if (!profile) { clearInterval(mineT); return; }
    const { data } = await sb.from("orders").select("id,status,product_name").eq("user_id", profile.id).eq("status", "pending");
    const now = new Set((data || []).map(x => x.id));
    if (minePending) for (const id of minePending) if (!now.has(id)) {
      const { data: o } = await sb.from("orders").select("status,product_name").eq("id", id).maybeSingle();
      if (o && o.status === "done") toast("Đơn " + o.product_name + " đã được giao! Mở mục Đơn hàng để xem.");
      if (o && o.status === "refunded") toast("Đơn " + o.product_name + " đã huỷ, tiền đã hoàn vào số dư.", 1);
      await loadProfile(); renderUser(); if (!$("orders").hidden) openOrders();
    }
    minePending = now; if (!now.size) clearInterval(mineT);
  };
  await check(); if (minePending && minePending.size) mineT = setInterval(check, 15000);
}
async function openOrders() {
  if (!profile) { openAuth("login"); return; }
  $("or-list").innerHTML = `<div class="empty">Đang tải…</div>`; show("orders");
  const [o, t] = await Promise.all([
    sb.from("orders").select("*").eq("user_id", profile.id).order("created_at", { ascending: false }).limit(100),
    sb.from("topups").select("*").eq("user_id", profile.id).order("created_at", { ascending: false }).limit(50)]);
  myOrders = o.data || [];
  const rows = [...(o.data || []).map(x => {
    const done = x.status === "done" && x.items, n = done ? x.items.split("\n").filter(l => l.trim()).length : 0;
    const body = done
      ? `<div class="oacts"><span class="okt">✓ ${n} tài khoản</span><button class="btn okb sm" data-dl="${x.id}">⬇ Tải .txt</button><button class="btn ghost sm" data-cp="${x.id}">📋 Copy</button><button class="btn ghost sm" data-view="${x.id}">👁 Xem</button></div><pre id="opre-${x.id}" hidden>${esc(x.items)}</pre>`
      : `<div class="hint">${esc(x.items || "")}</div>`;
    return { t: x.created_at, h: `<div class="oi"><div class="h"><b>${esc(x.product_name)} × ${x.qty}</b><span style="color:${x.status === "refunded" ? "var(--muted)" : "var(--bad)"};font-family:var(--mono)">${x.status === "refunded" ? "Đã hoàn" : "−" + vnd(x.total)}</span></div><div class="hint">${ago(x.created_at)} · ${ordPill(x.status)}</div>${body}</div>` };
  }),
    ...(t.data || []).map(x => ({ t: x.created_at, h: `<div class="oi"><div class="h"><b>Nạp tiền · ${esc(x.memo)}</b><span style="color:${x.status === "done" ? "var(--ok)" : "var(--gold)"};font-family:var(--mono)">${x.status === "done" ? "+" : ""}${vnd(x.amount)}</span></div><div class="hint">${ago(x.created_at)} · ${x.status === "done" ? "Thành công" : "Đang chờ chuyển khoản"}</div></div>` }))]
    .sort((a, b) => new Date(b.t) - new Date(a.t));
  $("or-list").innerHTML = rows.length ? rows.map(r => r.h).join("") : `<div class="empty">Bạn chưa có đơn hàng hay lệnh nạp nào.</div>`;
}
$("or-close").onclick = () => show("orders", false);
$("or-list").onclick = async e => {
  const dl = e.target.closest("[data-dl]"), cp = e.target.closest("[data-cp]"), vw = e.target.closest("[data-view]");
  if (dl) { const o = myOrders.find(x => x.id === dl.dataset.dl); if (o && o.items) downloadTxt(`BLUEROBLOX-${safeName(o.product_name)}-${Date.now()}.txt`, o.items); }
  if (cp) { const o = myOrders.find(x => x.id === cp.dataset.cp); if (!o) return;
    try { await navigator.clipboard.writeText(o.items); cp.textContent = "✓ Đã copy"; setTimeout(() => cp.textContent = "📋 Copy", 1800); }
    catch (err) { const pre = $("opre-" + o.id); if (pre) { pre.hidden = false; const r = document.createRange(); r.selectNodeContents(pre); getSelection().removeAllRanges(); getSelection().addRange(r); } toast("Bôi đen sẵn, bấm Ctrl+C.", 0); } }
  if (vw) { const pre = $("opre-" + vw.dataset.view); if (pre) { pre.hidden = !pre.hidden; vw.textContent = pre.hidden ? "👁 Xem" : "🙈 Ẩn"; } }
};

/* ---------- ADMIN ---------- */
async function openAdmin() { if (!isAdmin()) return; fillSite(); resetForm(); show("drawer"); await loadAdmin(); }
async function loadAdmin() {
  if (!isAdmin()) return;
  const [u, t, o] = await Promise.all([
    sb.from("profiles").select("*").order("created_at", { ascending: false }).limit(1000),
    sb.from("topups").select("*").order("created_at", { ascending: false }).limit(100),
    sb.from("orders").select("*").order("created_at", { ascending: false }).limit(100)]);
  const pend = await sb.from("orders").select("*").eq("status", "pending").order("created_at");
  const seen = new Set(), orders = [...(pend.data || []), ...(o.data || [])].filter(x => !seen.has(x.id) && seen.add(x.id));
  ADM = { users: u.data || [], topups: t.data || [], orders };
  renderTable(); renderCust(); renderTx(); renderOrd();
}
const uname = id => { const u = ADM.users.find(x => x.id === id); return u ? u.username : "?"; };
function renderTable() {
  const sp = P.slice().sort((a, b) => a.sort - b.sort);
  $("ptbl").innerHTML = sp.length ? sp.map(p => `<tr><td>${esc(p.name)}${p.hot ? ' <span class="pill wt">HOT</span>' : ""}</td>
    <td><span class="pill">${esc(catName(p.cat))}</span></td><td class="num">${plansOf(p).length ? plansOf(p).map(x => `${x.days}n: ${vnd(x.price)}`).join("<br>") : vnd(p.price)}</td>
    <td class="num" style="color:${(+p.stock || 0) === 0 ? "var(--bad)" : "inherit"}">${+p.stock || 0}<div class="hint">${p.manual ? "số lượng" : "kho .txt"}</div></td>
    <td style="white-space:nowrap;text-align:right">${p.manual ? "" : `<button class="btn okb sm" data-stock="${esc(p.id)}">Nhập kho</button> `}<button class="btn ghost sm" data-edit="${esc(p.id)}">Sửa</button> <button class="btn danger sm" data-del="${esc(p.id)}">Xoá</button></td></tr>`).join("")
    : `<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px">Chưa có sản phẩm. Điền form phía trên để thêm.</td></tr>`;
}
function renderCust() {
  const q = $("cq").value.trim().toLowerCase(), us = ADM.users.filter(u => !q || u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
  $("k-users").textContent = ADM.users.length; $("k-bal").textContent = vnd(ADM.users.reduce((s, u) => s + (+u.balance || 0), 0));
  $("k-rev").textContent = vnd(ADM.topups.filter(t => t.status === "done").reduce((s, t) => s + (+t.amount || 0), 0));
  $("ctbl").innerHTML = us.length ? us.map(u => `<tr><td><b>${esc(u.username)}</b>${u.role === "admin" ? ' <span class="pill wt">ADMIN</span>' : ""}<div class="hint">${ago(u.created_at)}</div></td><td>${esc(u.email)}</td>
    <td class="num">${vnd(u.balance)}</td><td>${u.locked ? '<span class="pill bad">Đã khoá</span>' : '<span class="pill ok">Hoạt động</span>'}</td>
    <td style="white-space:nowrap;text-align:right"><input class="in" style="width:110px;display:inline-block;padding:5px 8px" type="number" step="1000" placeholder="± số tiền" id="adj-${u.id}" aria-label="Điều chỉnh số dư">
    <button class="btn ghost sm" data-adj="${u.id}">Cộng/trừ</button>${u.id === profile.id ? "" : ` <button class="btn ${u.locked ? "ghost" : "danger"} sm" data-lock="${u.id}" data-to="${u.locked ? 0 : 1}">${u.locked ? "Mở khoá" : "Khoá"}</button>`}</td></tr>`).join("")
    : `<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px">Chưa có khách nào.</td></tr>`;
}
function renderTx() {
  $("ttbl").innerHTML = ADM.topups.length ? ADM.topups.map(t => `<tr><td>${ago(t.created_at)}</td><td>${esc(uname(t.user_id))}</td><td class="num">${esc(t.memo)}</td><td class="num">${vnd(t.amount)}</td>
    <td>${t.status === "done" ? '<span class="pill ok">Thành công</span>' : '<span class="pill wt">Chờ</span>'}</td>
    <td style="text-align:right">${t.status === "pending" ? `<button class="btn ghost sm" data-approve="${t.id}">Duyệt tay</button>` : ""}</td></tr>`).join("")
    : `<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px">Chưa có lệnh nạp nào.</td></tr>`;
}
function renderOrd() {
  $("otbl").innerHTML = ADM.orders.length ? ADM.orders.map(o => `<tr${o.status === "pending" ? ' style="background:rgba(255,203,69,.06)"' : ""}><td>${ago(o.created_at)}</td><td>${esc(uname(o.user_id))}</td><td>${esc(o.product_name)}</td><td class="num">${o.qty}</td><td class="num">${vnd(o.total)}</td>
    <td>${ordPill(o.status)}</td><td style="text-align:right;white-space:nowrap">${o.status === "pending" ? `<button class="btn sm" data-deliver="${o.id}">Giao hàng</button>` : `<button class="btn ghost sm" data-view="${o.id}">Xem</button>`}</td></tr>`).join("")
    : `<tr><td colspan="7" style="color:var(--muted);text-align:center;padding:24px">Chưa có đơn hàng nào.</td></tr>`;
  setBadge(ADM.orders.filter(o => o.status === "pending").length);
}
function setBadge(n) { for (const id of ["ord-badge", "adm-badge"]) { $(id).textContent = n; show(id, n > 0); } document.title = (n > 0 ? `(${n}) ` : "") + document.title.replace(/^\(\d+\) /, ""); }
let delOrder = null, refundArm = false;
$("otbl").onclick = e => {
  const d = e.target.closest("[data-deliver]"), v = e.target.closest("[data-view]");
  const o = ADM.orders.find(x => x.id === (d || v || {}).dataset?.deliver || x.id === (v || {}).dataset?.view); if (!o) return;
  delOrder = o; refundArm = false; $("dl-refund").textContent = "Huỷ đơn & hoàn tiền";
  $("dl-info").textContent = `${uname(o.user_id)} · ${o.product_name} × ${o.qty} · ${vnd(o.total)} · ${ago(o.created_at)}`;
  const pending = o.status === "pending";
  $("dl-items").value = pending ? "" : o.items; $("dl-items").readOnly = !pending; $("dl-err").textContent = "";
  $("dl-title").textContent = pending ? "Giao đơn hàng" : "Chi tiết đơn"; show("dl-save", pending); show("dl-refund", pending);
  show("deldlg"); if (pending) $("dl-items").focus();
};
$("dl-cancel").onclick = () => show("deldlg", false);
$("dl-save").onclick = () => busy($("dl-save"), async () => {
  const items = $("dl-items").value; if (!items.trim()) { $("dl-err").textContent = ERR.EMPTY; return; }
  const { data, error } = await sb.rpc("admin_deliver_order", { p_order: delOrder.id, p_items: items });
  if (error) { $("dl-err").textContent = errMsg(error); return; }
  show("deldlg", false); toast(data ? "Đã giao cho khách." : "Đơn này đã được xử lý trước đó."); await loadAdmin();
});
$("dl-refund").onclick = () => busy($("dl-refund"), async () => {
  if (!refundArm) { refundArm = true; $("dl-refund").textContent = "Bấm lần nữa để hoàn tiền"; setTimeout(() => { refundArm = false; $("dl-refund").textContent = "Huỷ đơn & hoàn tiền"; }, 3000); return; }
  const { data, error } = await sb.rpc("admin_refund_order", { p_order: delOrder.id });
  if (error) { $("dl-err").textContent = errMsg(error); return; }
  show("deldlg", false); toast(data ? "Đã huỷ đơn và hoàn tiền cho khách." : "Đơn này đã được xử lý trước đó."); await loadAdmin(); await loadProducts();
});
async function pollPending() {
  if (!isAdmin()) return;
  const { count } = await sb.from("orders").select("id", { count: "exact", head: true }).eq("status", "pending");
  const prev = +($("adm-badge").textContent || 0);
  setBadge(count || 0);
  if ((count || 0) > prev) toast(`Có ${count} đơn đang chờ giao.`);
  if (!$("drawer").hidden && (count || 0) !== prev) loadAdmin();
}
setInterval(pollPending, 30000);
$("cq").oninput = renderCust;
$("ctbl").onclick = async e => {
  const a = e.target.closest("[data-adj]"), l = e.target.closest("[data-lock]");
  if (a) { const v = Math.round(+$("adj-" + a.dataset.adj).value || 0); if (!v) return;
    await busy(a, async () => { const { error } = await sb.rpc("admin_adjust_balance", { p_user: a.dataset.adj, p_delta: v }); if (error) return toast(errMsg(error), 1); toast((v > 0 ? "Đã cộng " : "Đã trừ ") + vnd(Math.abs(v))); await loadAdmin(); if (a.dataset.adj === profile.id) { await loadProfile(); renderUser(); } }); }
  if (l) await busy(l, async () => { const { error } = await sb.rpc("admin_set_locked", { p_user: l.dataset.lock, p_locked: l.dataset.to === "1" }); if (error) return toast(errMsg(error), 1); toast(l.dataset.to === "1" ? "Đã khoá tài khoản." : "Đã mở khoá."); await loadAdmin(); });
};
$("ttbl").onclick = async e => { const b = e.target.closest("[data-approve]"); if (!b) return;
  await busy(b, async () => { const { data, error } = await sb.rpc("admin_approve_topup", { p_id: +b.dataset.approve }); if (error) return toast(errMsg(error), 1); toast(data ? "Đã duyệt và cộng tiền." : "Lệnh này đã được xử lý."); await loadAdmin(); }); };

function planRow(d = "", pr = "") {
  const r = document.createElement("div"); r.className = "plan-row";
  r.innerHTML = `<input type="number" min="1" max="365" step="1" placeholder="Số ngày" value="${esc(d)}" aria-label="Số ngày"><input type="number" min="0" step="1000" placeholder="Giá (VND)" value="${esc(pr)}" aria-label="Giá gói"><button class="btn danger sm" type="button" aria-label="Xoá gói">Xoá</button><div class="per"></div>`;
  const [di, pi, rm] = r.querySelectorAll("input,button"), per = r.querySelector(".per");
  const calc = () => { per.textContent = +di.value > 0 && +pi.value > 0 ? "≈ " + vnd(+pi.value / +di.value) + " / ngày" : ""; };
  di.oninput = pi.oninput = calc; rm.onclick = () => { r.remove(); syncPlanUI(); }; calc();
  $("pf-plans").appendChild(r); syncPlanUI();
}
function readPlans() {
  const out = [], seen = new Set();
  for (const r of $("pf-plans").querySelectorAll(".plan-row")) {
    const [di, pi] = r.querySelectorAll("input"); if (!di.value && !pi.value) continue;
    const d = Math.round(+di.value), pr = Math.round(+pi.value);
    if (!(d >= 1 && d <= 365)) throw new Error("Số ngày của mỗi gói phải từ 1 đến 365.");
    if (!(pr >= 0) || pi.value === "") throw new Error("Nhập giá cho gói " + d + " ngày.");
    if (seen.has(d)) throw new Error("Gói " + d + " ngày bị trùng."); seen.add(d);
    out.push({ days: d, price: pr });
  }
  return out.sort((a, b) => a.days - b.days);
}
function syncPlanUI() { const has = $("pf-plans").querySelectorAll(".plan-row").length > 0; $("pf-vnd-l").textContent = has ? "Giá gốc (không dùng khi có gói)" : "Giá (VND)"; $("pf-vnd").required = !has; show("pf-plans-box", $("pf-c").value === "vps" || has); }
$("pf-plan-add").onclick = () => planRow();
$("pf-plan-quick").onclick = () => { $("pf-plans").innerHTML = ""; [7, 15, 30].forEach(d => planRow(d, "")); $("pf-plans").querySelector("input[placeholder='Giá (VND)']").focus(); };
function syncMode() { const auto = $("pf-mode").value === "auto"; show("pf-ms-wrap", !auto); }
$("pf-mode").onchange = syncMode;
$("pf-c").onchange = syncPlanUI;
$("pf-img-file").onchange = () => {
  const f = $("pf-img-file").files[0]; if (!f) return;
  if (!/^image\//.test(f.type)) { toast("Hãy chọn một file ảnh.", 1); $("pf-img-file").value = ""; return; }
  if (f.size > 4 * 1024 * 1024) { toast("Ảnh tối đa 4MB. Chọn ảnh nhỏ hơn.", 1); $("pf-img-file").value = ""; return; }
  pfFile = f; try { $("pf-img-prev").src = URL.createObjectURL(f); show("pf-img-row"); } catch (e) {}
};
$("pf-img-clear").onclick = () => { pfImage = ""; pfFile = null; $("pf-img-file").value = ""; show("pf-img-row", false); };
function resetForm() { editId = null; $("pf").reset(); $("pf-plans").innerHTML = ""; $("pf-ms").value = 10; $("pf-mode").value = "auto"; $("pf-thumb").value = ""; syncMode(); pfImage = ""; pfFile = null; $("pf-img-file").value = ""; show("pf-img-row", false); syncPlanUI(); $("pf-o").value = P.length ? Math.max(...P.map(p => +p.sort || 0)) + 1 : 1; $("pf-title").textContent = "Thêm sản phẩm"; $("pf-save").textContent = "Thêm sản phẩm"; }
function fillForm(p) { editId = p.id; $("pf-n").value = p.name; $("pf-c").value = p.cat; $("pf-vnd").value = p.price; $("pf-o").value = p.sort; $("pf-f").value = (p.features || []).join(", "); $("pf-h").checked = !!p.hot; $("pf-ms").value = +p.stock || 0; $("pf-mode").value = p.manual ? "manual" : "auto"; $("pf-thumb").value = p.thumb || ""; syncMode(); pfImage = p.image || ""; pfFile = null; $("pf-img-file").value = ""; if (pfImage) { $("pf-img-prev").src = pfImage; show("pf-img-row"); } else show("pf-img-row", false); $("pf-plans").innerHTML = ""; plansOf(p).forEach(x => planRow(x.days, x.price)); syncPlanUI(); $("pf-title").textContent = "Sửa sản phẩm"; $("pf-save").textContent = "Lưu thay đổi"; $("pane-prod").scrollTop = 0; $("pf-n").focus(); }
$("pf").onsubmit = e => { e.preventDefault(); busy($("pf-save"), async () => {
  const body = { cat: $("pf-c").value, name: $("pf-n").value.trim(), price: Math.max(0, Math.round(+$("pf-vnd").value || 0)), sort: Math.round(+$("pf-o").value || 100),
    features: $("pf-f").value.split(",").map(s => s.trim()).filter(Boolean).slice(0, 6), hot: $("pf-h").checked,
    manual: $("pf-mode").value === "manual", manual_stock: Math.max(0, Math.round(+$("pf-ms").value || 0)), thumb: $("pf-thumb").value || null };
  if (!body.name) return toast("Hãy nhập tên sản phẩm.", 1);
  try { body.plans = readPlans(); } catch (err) { return toast(err.message, 1); }
  if (body.plans.length) body.price = Math.min(...body.plans.map(x => x.price));
  if (pfFile) {
    const ext = (pfFile.name.split(".").pop() || "jpg").toLowerCase().replace(/[^a-z0-9]/g, "") || "jpg";
    const path = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "" + Math.random().toString(36).slice(2)) + "." + ext;
    const up = await sb.storage.from("products").upload(path, pfFile, { cacheControl: "3600", upsert: false });
    if (up.error) return toast("Tải ảnh lên thất bại: " + (up.error.message || ""), 1);
    body.image = sb.storage.from("products").getPublicUrl(path).data.publicUrl;
  } else body.image = pfImage || null;
  const { error } = editId ? await sb.from("products").update(body).eq("id", editId) : await sb.from("products").insert(body);
  if (error) return toast(errMsg(error), 1);
  toast(editId ? "Đã lưu thay đổi." : "Đã thêm sản phẩm."); resetForm(); await loadProducts();
}); };
$("pf-reset").onclick = resetForm;
let delArm = null;
$("ptbl").onclick = async e => {
  const ed = e.target.closest("[data-edit]"), dl = e.target.closest("[data-del]"), sk = e.target.closest("[data-stock]");
  if (sk) return openStock(sk.dataset.stock);
  if (ed) { const p = P.find(x => x.id === ed.dataset.edit); if (p) fillForm(p); }
  if (dl) { const id = dl.dataset.del;
    if (delArm !== id) { delArm = id; dl.textContent = "Bấm lần nữa để xoá"; setTimeout(() => { if (delArm === id) { delArm = null; renderTable(); } }, 3000); return; }
    delArm = null; const { error } = await sb.from("products").delete().eq("id", id); if (error) return toast(errMsg(error), 1); toast("Đã xoá sản phẩm."); if (editId === id) resetForm(); await loadProducts(); }
};
function skCount() { $("sk-count").textContent = $("sk-lines").value.split("\n").filter(l => l.trim()).length + " tài khoản"; }
function openStock(id) { stockFor = id; const p = P.find(x => x.id === id); $("sk-name").textContent = p.name + " · đang còn " + (+p.stock || 0) + " tài khoản"; $("sk-lines").value = ""; $("sk-file").value = ""; skCount(); $("sk-err").textContent = ""; show("stockdlg"); }
$("sk-file").onchange = () => { const f = $("sk-file").files[0]; if (!f) return;
  if (f.size > 8 * 1024 * 1024) { $("sk-err").textContent = "File tối đa 8MB."; return; }
  const rd = new FileReader(); rd.onload = () => { const t = String(rd.result || "").replace(/\r/g, ""); $("sk-lines").value = $("sk-lines").value.trim() ? ($("sk-lines").value.replace(/\s+$/,"") + "\n" + t) : t; skCount(); $("sk-err").textContent = ""; }; rd.readAsText(f); };
$("sk-lines").oninput = skCount;
$("sk-cancel").onclick = () => show("stockdlg", false);
$("sk-save").onclick = () => busy($("sk-save"), async () => {
  const lines = $("sk-lines").value; if (!lines.trim()) { $("sk-err").textContent = "Dán ít nhất 1 dòng."; return; }
  const { data, error } = await sb.rpc("admin_add_stock", { p_product: stockFor, p_lines: lines });
  if (error) { $("sk-err").textContent = errMsg(error); return; }
  show("stockdlg", false); toast("Đã thêm " + data + " sản phẩm vào kho."); await loadProducts();
});
let clearArm = false;
$("sk-clear").onclick = () => busy($("sk-clear"), async () => {
  if (!clearArm) { clearArm = true; $("sk-clear").textContent = "Bấm lần nữa để xoá hết"; setTimeout(() => { clearArm = false; $("sk-clear").textContent = "Xoá hàng chưa bán"; }, 3000); return; }
  clearArm = false; $("sk-clear").textContent = "Xoá hàng chưa bán";
  const { data, error } = await sb.rpc("admin_clear_stock", { p_product: stockFor }); if (error) { $("sk-err").textContent = errMsg(error); return; }
  show("stockdlg", false); toast("Đã xoá " + data + " dòng chưa bán."); await loadProducts();
});

function fillSite() {
  for (const k of Object.keys(DEF_SITE)) { const el = $("sf-" + k); if (el) { if (el.type === "checkbox") el.checked = !!SITE[k]; else el.value = SITE[k] ?? ""; } }
  $("bf-bin").innerHTML = BANKS.map(b => `<option value="${b[0]}">${b[1]}</option>`).join(""); $("bf-bin").value = SITE.bankBin;
  $("bf-acc").value = SITE.bankAcc; $("bf-name").value = SITE.bankName; $("bf-prefix").value = SITE.prefix; $("bf-min").value = SITE.minTop;
}
async function saveSettings(patch, btn, msg) { await busy(btn, async () => {
  const body = { ...SITE, ...patch }; const { error } = await sb.from("settings").update({ data: body }).eq("id", 1);
  if (error) return toast(errMsg(error), 1); SITE = body; renderSite(); toast(msg);
}); }
$("sf").onsubmit = e => { e.preventDefault(); const p = {}; for (const k of Object.keys(DEF_SITE)) { const el = $("sf-" + k); if (el) p[k] = el.type === "checkbox" ? el.checked : k === "rate" ? (+el.value || 25000) : el.value.trim(); } saveSettings(p, $("sf-save"), "Đã lưu nội dung trang."); };
$("bf").onsubmit = e => { e.preventDefault(); const acc = $("bf-acc").value.replace(/\D/g, ""); if (acc.length < 6) return toast("Số tài khoản chưa đúng.", 1);
  saveSettings({ bankBin: $("bf-bin").value, bankAcc: acc, bankName: $("bf-name").value.trim().toUpperCase(), prefix: ($("bf-prefix").value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "") || "BR"), minTop: Math.max(1000, +$("bf-min").value || 10000) }, $("bf-save"), "Đã lưu tài khoản ngân hàng."); };
function setTab(t) { document.querySelectorAll("#adm-tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t)); ["prod", "cust", "tx", "ord", "bank", "site"].forEach(x => show("pane-" + x, x === t)); }
$("adm-tabs").onclick = e => { const b = e.target.closest("button"); if (!b) return; if (b.dataset.tab === "site" || b.dataset.tab === "bank") fillSite(); setTab(b.dataset.tab); };
$("admin-open").onclick = openAdmin; $("admin-close").onclick = () => show("drawer", false);
$("adm-refresh").onclick = () => busy($("adm-refresh"), async () => { await Promise.all([loadProducts(), loadSettings(), loadAdmin()]); toast("Đã tải lại."); });
$("adm-logout").onclick = async () => { show("drawer", false); await logout(); };
$("drawer").onclick = e => { if (e.target.id === "drawer") show("drawer", false); };

/* ---------- sự kiện chung ---------- */
$("cats").onclick = e => { const b = e.target.closest("button"); if (!b) return; cat = b.dataset.c; renderCats(); renderGrid(); };
$("q").oninput = renderGrid; $("sort").onchange = renderGrid;
$("cur-vnd").onclick = () => setCur("VND"); $("cur-usd").onclick = () => setCur("USD");
$("grid").onclick = e => { const b = e.target.closest("[data-buy]"); if (b) openBuy(b.dataset.buy); };
$("m-plus").onclick = () => { const p = selP(); $("m-qty").value = Math.min(+p.stock || 1, +$("m-qty").value + 1); upd(); };
$("m-minus").onclick = () => { $("m-qty").value = Math.max(1, +$("m-qty").value - 1); upd(); };
$("m-qty").oninput = upd; $("m-cancel").onclick = closeBuy; $("m-ok").onclick = doBuy;
$("btn-topup").onclick = () => openTopup(); $("nav-topup").onclick = () => openTopup(); $("pay-bank").onclick = () => openTopup();
$("nav-orders").onclick = openOrders;
document.querySelectorAll(".modal").forEach(m => m.addEventListener("click", e => { if (e.target === m && m.id !== "stockdlg") { m.hidden = true; if (m.id === "modal") sel = null; if (m.id === "topup") clearInterval(pollT); } }));
document.addEventListener("keydown", e => { if (e.key === "Escape") { show("drawer", false); document.querySelectorAll(".modal").forEach(m => m.hidden = true); sel = null; clearInterval(pollT); } });

/* ---------- khởi động ---------- */
renderSite(); renderCats();
sb.auth.onAuthStateChange((ev, s) => {
  session = s;
  setTimeout(async () => { await loadProfile(); renderUser(); if (ev === "PASSWORD_RECOVERY") openAuth("newpw"); if (profile) { minePending = null; watchMine(); pollPending(); } }, 0);
});
loadSettings(); loadProducts();
setInterval(() => { if (!document.hidden) loadProducts(); }, 60000);

/* ===== công tắc hiệu ứng ===== */
window.BRfxOn = (function () { let v = null; try { v = localStorage.getItem("br_fx"); } catch (e) {}
  if (location.hash === "#fxon") return true; if (location.hash === "#fxoff") return false;
  if (v === "on") return true; if (v === "off") return false;
  return true; })();
document.documentElement.classList.toggle("fx-off", !window.BRfxOn);
(function () {
  const b = document.createElement("button"); b.type = "button"; b.id = "fx-toggle";
  b.className = window.BRfxOn ? "" : "off"; b.textContent = window.BRfxOn ? "✨ Hiệu ứng: Bật" : "✨ Bật hiệu ứng";
  b.title = "Bật hoặc tắt chuyển động trên trang";
  b.onclick = () => { const next = window.BRfxOn ? "off" : "on"; try { localStorage.setItem("br_fx", next); } catch (e) {}
    try { history.replaceState(null, "", "#fx" + next); } catch (e) { location.hash = "fx" + next; } location.reload(); };
  document.body.appendChild(b);
})();

/* ===== hiệu ứng ===== */
(function () {
  const reduce = !window.BRfxOn;
  const grid = document.getElementById("grid");
  if (grid) {
    const tag = () => grid.querySelectorAll(".card").forEach((c, i) => c.style.setProperty("--i", Math.min(i, 12)));
    new MutationObserver(tag).observe(grid, { childList: true }); tag();
    grid.addEventListener("pointermove", e => {
      const c = e.target.closest(".card"); if (!c) return;
      const r = c.getBoundingClientRect();
      c.style.setProperty("--mx", (e.clientX - r.left) + "px"); c.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  }
  const top = document.querySelector(".top");
  if (top) addEventListener("scroll", () => top.classList.toggle("scrolled", scrollY > 8), { passive: true });

  function countUp(el) {
    if (reduce || el._busy) return;
    const raw = el.textContent, m = raw.match(/^([\d.,]+)(.*)$/); if (!m) return;
    const target = +m[1].replace(/[.,]/g, ""); if (!target) return;
    el._busy = true; const t0 = performance.now(), d = 1200;
    const step = t => {
      const k = Math.min(1, (t - t0) / d), v = Math.round(target * (1 - Math.pow(1 - k, 3)));
      el.textContent = v.toLocaleString("vi-VN") + m[2];
      if (k < 1) requestAnimationFrame(step); else { el.textContent = raw; el._busy = false; }
    };
    requestAnimationFrame(step);
  }
  ["st-a", "st-b"].forEach(id => {
    const el = document.getElementById(id); if (!el) return;
    let last = el.textContent; countUp(el);
    new MutationObserver(() => { if (el._busy || el.textContent === last) return; last = el.textContent; countUp(el); })
      .observe(el, { childList: true, characterData: true, subtree: true });
  });

  if (reduce) return;
  const hero = document.querySelector(".hero"); if (!hero) return;
  const cv = document.createElement("canvas"); cv.className = "fx-cv"; cv.setAttribute("aria-hidden", "true"); hero.prepend(cv);
  const x = cv.getContext("2d"), dpr = 1;
  let W = 0, H = 0;
  const size = () => { const r = hero.getBoundingClientRect(); W = cv.width = Math.max(1, r.width * dpr); H = cv.height = Math.max(1, r.height * dpr); };
  size(); addEventListener("resize", size);
  const ps = Array.from({ length: 34 }, () => ({ x: Math.random(), y: Math.random(), s: 4 + Math.random() * 11, v: .00018 + Math.random() * .00045,
    r: Math.random() * 6, vr: (Math.random() - .5) * .012, h: 195 + Math.random() * 45, a: .12 + Math.random() * .35, hollow: Math.random() < .35 }));
  let mx = .5, my = .5;
  hero.addEventListener("pointermove", e => { const r = hero.getBoundingClientRect(); mx = (e.clientX - r.left) / r.width; my = (e.clientY - r.top) / r.height; });
  let lastF = 0;
  function frame(t) {
    if (t - lastF < 33) { requestAnimationFrame(frame); return; } lastF = t;
    x.clearRect(0, 0, W, H);
    for (const p of ps) {
      p.y -= p.v; p.r += p.vr; if (p.y < -.06) { p.y = 1.06; p.x = Math.random(); }
      const px = (p.x + (mx - .5) * p.s * .004) * W, py = (p.y + (my - .5) * p.s * .003) * H, s = p.s * dpr;
      x.save(); x.translate(px, py); x.rotate(p.r);
      if (p.hollow) { x.strokeStyle = `hsla(${p.h} 95% 65% / ${p.a})`; x.lineWidth = 1.5 * dpr; x.strokeRect(-s / 2, -s / 2, s, s); }
      else { x.fillStyle = `hsla(${p.h} 95% 60% / ${p.a})`; x.fillRect(-s / 2, -s / 2, s, s); }
      x.restore();
    }
    if (document.hidden) setTimeout(() => requestAnimationFrame(frame), 400); else requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();

/* ===== nền trống đồng Đông Sơn + sao rơi + sao băng + kim tuyến ===== */
(function () {
  const reduce = !window.BRfxOn;
  const cv = document.createElement("canvas"); cv.id = "fx-bg"; cv.setAttribute("aria-hidden", "true"); document.body.prepend(cv);
  const x = cv.getContext("2d"), TAU = Math.PI * 2;
  let dpr = .65, lowQ = false;
  let W = 0, H = 0, mobile = false;
  const LAYERS = [[0, .39, true, .00005], [.39, .55, false, .00016], [.55, .68, false, -.00007], [.68, .84, false, .00011], [.84, 1, false, -.00004]];

  /* --- vẽ mặt trống đồng một lần ra canvas phụ --- */
  function buildDrum(R, from = 0, to = 1, star = true) {
    const c = document.createElement("canvas"); c.width = c.height = Math.ceil(R * 2) + 4;
    const g = c.getContext("2d"); g.translate(c.width / 2, c.height / 2);
    const gold = g.createRadialGradient(0, 0, 0, 0, 0, R);
    gold.addColorStop(0, "#fff1c2"); gold.addColorStop(.35, "#f0be5c"); gold.addColorStop(.75, "#d4973a"); gold.addColorStop(1, "#a26b24");
    g.strokeStyle = gold; g.fillStyle = gold; g.lineCap = "round"; g.lineJoin = "round";
    const lw = Math.max(1, R / 380);
    const ring = (r, w = 1.4) => { g.beginPath(); g.arc(0, 0, r, 0, TAU); g.lineWidth = lw * w; g.stroke(); };
    // ngôi sao 14 cánh ở tâm
    const n = 14, rs = R * .17, ri = R * .055;
    if (star) {
    g.beginPath(); for (let i = 0; i < n * 2; i++) { const a = i * Math.PI / n - Math.PI / 2, r = i % 2 ? ri : rs; g.lineTo(Math.cos(a) * r, Math.sin(a) * r); } g.closePath(); g.fill();
    g.lineWidth = lw;
    for (let i = 0; i < n; i++) { const a = (i + .5) * TAU / n - Math.PI / 2; g.save(); g.rotate(a); g.beginPath(); g.moveTo(ri * 1.4, 0); g.lineTo(rs * .92, -rs * .11); g.lineTo(rs * .92, rs * .11); g.closePath(); g.stroke();
      for (let k = 1; k < 4; k++) { const px = ri * 1.4 + (rs * .92 - ri * 1.4) * k / 4, hy = rs * .11 * k / 4; g.beginPath(); g.moveTo(px, -hy); g.lineTo(px, hy); g.stroke(); } g.restore(); }
    ring(R * .19, 2); ring(R * .205);
    }
    const bird = (s, flip) => {
      g.save(); if (flip) g.scale(1, -1);
      g.beginPath(); g.ellipse(0, 0, s * 1.1, s * .28, 0, 0, TAU); g.fill();
      g.beginPath(); g.moveTo(s * .95, -s * .1); g.lineTo(s * 2.5, -s * .02); g.lineTo(s * .95, s * .14); g.closePath(); g.fill();
      g.beginPath(); g.moveTo(s * .85, -s * .18); g.quadraticCurveTo(s * .55, -s * .75, s * .1, -s * .85); g.stroke();
      g.beginPath(); g.moveTo(s * .35, -s * .1); g.lineTo(-s * .45, -s * 1.15); g.lineTo(-s * .05, -s * .18); g.closePath(); g.fill();
      g.beginPath(); g.moveTo(s * .35, s * .1); g.lineTo(-s * .45, s * 1.15); g.lineTo(-s * .05, s * .18); g.closePath(); g.fill();
      g.beginPath(); g.moveTo(-s, 0); g.lineTo(-s * 2.1, -s * .5); g.moveTo(-s, 0); g.lineTo(-s * 2.25, 0); g.moveTo(-s, 0); g.lineTo(-s * 2.1, s * .5); g.stroke();
      g.restore();
    };
    const bands = [[.205, .27, "circles"], [.27, .31, "hatch"], [.31, .37, "zigzag"], [.37, .39, "lines"], [.39, .55, "birds", 8],
      [.55, .57, "lines"], [.57, .63, "circles"], [.63, .68, "ladder"], [.68, .84, "birds", 13], [.84, .88, "hatch"], [.88, .945, "circles"], [.945, .965, "lines"]];
    for (const [a, b, t, cnt] of bands) {
      if (a < from - 1e-6 || b > to + 1e-6) continue;
      const r0 = R * a, r1 = R * b, rm = (r0 + r1) / 2, h = r1 - r0; ring(r0); ring(r1); g.lineWidth = lw;
      if (t === "circles") { const k = Math.floor(TAU * rm / (h * 1.1)); g.beginPath(); g.arc(0, 0, rm, 0, TAU); g.stroke();
        for (let i = 0; i < k; i++) { const an = i / k * TAU, cx = Math.cos(an) * rm, cy = Math.sin(an) * rm;
          g.save(); g.fillStyle = "#060c1f"; g.beginPath(); g.arc(cx, cy, h * .36, 0, TAU); g.fill(); g.restore(); g.beginPath(); g.arc(cx, cy, h * .36, 0, TAU); g.stroke(); g.beginPath(); g.arc(cx, cy, h * .11, 0, TAU); g.fill(); } }
      if (t === "hatch") { const k = Math.floor(TAU * rm / (h * .4)); for (let i = 0; i < k; i++) { const an = i / k * TAU, an2 = an + .7 * h / rm; g.beginPath(); g.moveTo(Math.cos(an) * r0, Math.sin(an) * r0); g.lineTo(Math.cos(an2) * r1, Math.sin(an2) * r1); g.stroke(); } }
      if (t === "zigzag") { const k = Math.floor(TAU * rm / (h * .9)); g.beginPath(); for (let i = 0; i <= k * 2; i++) { const an = i / (k * 2) * TAU, r = i % 2 ? r1 - h * .15 : r0 + h * .15; g.lineTo(Math.cos(an) * r, Math.sin(an) * r); } g.stroke(); }
      if (t === "lines") { const k = Math.floor(TAU * rm / (lw * 5)); for (let i = 0; i < k; i++) { const an = i / k * TAU; g.beginPath(); g.moveTo(Math.cos(an) * r0, Math.sin(an) * r0); g.lineTo(Math.cos(an) * r1, Math.sin(an) * r1); g.stroke(); } }
      if (t === "ladder") { ring(rm, 1); const k = Math.floor(TAU * rm / (h * .55)); for (let i = 0; i < k; i++) { const an = i / k * TAU; g.beginPath(); g.moveTo(Math.cos(an) * r0, Math.sin(an) * r0); g.lineTo(Math.cos(an) * r1, Math.sin(an) * r1); g.stroke(); } }
      if (t === "birds") { for (let i = 0; i < cnt; i++) { const an = i / cnt * TAU; g.save(); g.rotate(an); g.translate(rm, 0); g.rotate(Math.PI / 2); bird(h * .36, i % 2); g.restore(); } }
    }
    if (to >= 1) ring(R * .985, 2.4);
    return c;
  }
  window.BRbuildDrum = buildDrum;

  /* --- sao --- */
  let stars = [], falls = [], shoots = [], sparks = [], nextShoot = 0;
  function seed() {
    const ns = lowQ ? 40 : mobile ? 45 : 90, nf = lowQ ? 10 : mobile ? 12 : 22;
    stars = Array.from({ length: ns }, () => ({ x: Math.random() * W, y: Math.random() * H, r: (.4 + Math.random() * 1.3) * dpr, b: .25 + Math.random() * .6, sp: .0008 + Math.random() * .002, ph: Math.random() * TAU, gold: Math.random() < .25 }));
    falls = Array.from({ length: nf }, () => newFall(true));
  }
  function newFall(any) { return { x: Math.random() * W, y: any ? Math.random() * H : -20 * dpr, s: (2 + Math.random() * 4) * dpr, vy: (.015 + Math.random() * .045) * dpr, sw: Math.random() * TAU, swa: (6 + Math.random() * 18) * dpr, rot: Math.random() * TAU, vr: (Math.random() - .5) * .002, gold: Math.random() < .55, a: .35 + Math.random() * .5 }; }
  function spawnShoot(t) {
    const ang = (200 + Math.random() * 25) * Math.PI / 180, sp = (.9 + Math.random() * .8) * dpr;
    shoots.push({ x: W * (.35 + Math.random() * .8), y: -H * .05 + Math.random() * H * .35, vx: Math.cos(ang) * sp, vy: -Math.sin(ang) * sp, len: (140 + Math.random() * 180) * dpr, life: 0, max: 1400 + Math.random() * 900 });
    nextShoot = t + (mobile ? 3500 : 2200) + Math.random() * 4000;
  }
  function sparkle(px, py, s, rot, col, a) {
    x.save(); x.translate(px, py); x.rotate(rot); x.globalAlpha = a; x.fillStyle = col;
    x.beginPath(); for (let i = 0; i < 8; i++) { const r = i % 2 ? s * .28 : s, an = i * Math.PI / 4; x.lineTo(Math.cos(an) * r, Math.sin(an) * r); } x.closePath(); x.fill();
    x.restore();
  }

  const host = document.createElement("div"); host.className = "fx-drums"; host.setAttribute("aria-hidden", "true");
  document.body.prepend(host);
  function size() {
    mobile = innerWidth < 760; dpr = lowQ ? .42 : mobile ? .5 : .62;
    W = cv.width = Math.max(1, Math.round(innerWidth * dpr)); H = cv.height = Math.max(1, Math.round(innerHeight * dpr));
    // trống đồng: vẽ 1 lần, để card đồ hoạ tự xoay bằng CSS
    const Rc = Math.round((mobile ? Math.max(innerWidth, innerHeight) * .55 : Math.max(innerWidth, innerHeight) * .42));
    const res = Math.min(1, (window.devicePixelRatio || 1)) * (mobile ? .75 : .8), Rp = Math.round(Rc * res);
    const cx = mobile ? innerWidth * .5 : innerWidth * .74, cy = mobile ? innerHeight * .26 : innerHeight * .42;
    host.innerHTML = "";
    const main = document.createElement("div"); main.className = "fx-drum";
    main.style.cssText = `left:${cx}px;top:${cy}px;width:${Rc * 2}px;height:${Rc * 2}px`;
    main.innerHTML = '<div class="fx-glow"></div>';
    for (const [a, b, st, sp] of LAYERS) {
      const c = buildDrum(Rp, a, b, st); c.className = "fx-ring";
      c.style.animationDuration = (TAU / Math.abs(sp) / 1000).toFixed(1) + "s"; if (sp < 0) c.style.animationDirection = "reverse";
      main.appendChild(c);
    }
    main.insertAdjacentHTML("beforeend", '<div class="fx-sweep"></div><div class="fx-core"></div>');
    const small = document.createElement("div"); small.className = "fx-drum fx-small";
    const sR = Rc * .55; small.style.cssText = `left:${mobile ? innerWidth * .1 : innerWidth * .08}px;top:${innerHeight * .92}px;width:${sR * 2}px;height:${sR * 2}px`;
    const sc = buildDrum(Math.round(sR * res)); sc.className = "fx-ring"; sc.style.animationDuration = "105s"; sc.style.animationDirection = "reverse"; small.appendChild(sc);
    host.append(main, small);
    seed(); if (reduce) draw(0, 0);
  }

  let last = 0;
  function draw(t, dt) {
    x.clearRect(0, 0, W, H);
    // sao lấp lánh
    for (const s of stars) { const a = s.b * (.45 + .55 * Math.sin(t * s.sp + s.ph)); x.globalAlpha = a; x.fillStyle = s.gold ? "#ffe29a" : "#dfe9ff"; x.beginPath(); x.arc(s.x, s.y, s.r, 0, TAU); x.fill(); }
    x.globalAlpha = 1;
    // sao rơi
    for (const f of falls) {
      f.y += f.vy * dt; f.sw += dt * .0012; f.rot += f.vr * dt; if (f.y > H + 20 * dpr) Object.assign(f, newFall(false));
      sparkle(f.x + Math.sin(f.sw) * f.swa, f.y, f.s, f.rot, f.gold ? "#ffd56b" : "#ffffff", f.a * (.6 + .4 * Math.sin(t * .004 + f.sw)));
    }
    // sao băng
    if (!reduce && t > nextShoot) spawnShoot(t);
    for (let i = shoots.length - 1; i >= 0; i--) {
      const s = shoots[i]; s.life += dt; s.x += s.vx * dt; s.y += s.vy * dt;
      const k = s.life / s.max, fade = k < .15 ? k / .15 : 1 - Math.max(0, (k - .6) / .4);
      const mag = Math.hypot(s.vx, s.vy), tx = s.x - s.vx / mag * s.len, ty = s.y - s.vy / mag * s.len;
      const gr = x.createLinearGradient(s.x, s.y, tx, ty); gr.addColorStop(0, `rgba(255,248,220,${.95 * fade})`); gr.addColorStop(.25, `rgba(255,205,110,${.55 * fade})`); gr.addColorStop(1, "rgba(63,224,255,0)");
      x.strokeStyle = gr; x.lineWidth = 2 * dpr; x.lineCap = "round"; x.beginPath(); x.moveTo(s.x, s.y); x.lineTo(tx, ty); x.stroke();
      const hg = x.createRadialGradient(s.x, s.y, 0, s.x, s.y, 10 * dpr); hg.addColorStop(0, `rgba(255,255,255,${fade})`); hg.addColorStop(1, "rgba(255,220,140,0)");
      x.fillStyle = hg; x.beginPath(); x.arc(s.x, s.y, 10 * dpr, 0, TAU); x.fill();
      if (k >= 1 || s.x < -s.len || s.y > H + s.len) shoots.splice(i, 1);
    }
    // kim tuyến theo chuột
    for (let i = sparks.length - 1; i >= 0; i--) { const p = sparks[i]; p.life += dt; p.x += p.vx * dt; p.y += p.vy * dt; p.vy += .00008 * dt * dpr;
      const k = p.life / p.max; if (k >= 1) { sparks.splice(i, 1); continue; } sparkle(p.x, p.y, p.s * (1 - k * .5), p.rot + k * 2, p.col, 1 - k); }
  }
  let slow = 0, cnt = 0;
  function frame(t) {
    if (document.hidden) { last = 0; setTimeout(() => requestAnimationFrame(frame), 500); return; }
    const gap = t - (last || t);
    if (last && gap < 33) { requestAnimationFrame(frame); return; }
    const dt = Math.min(60, gap); last = t;
    const t0 = performance.now(); draw(t, dt); const cost = performance.now() - t0;
    // tự hạ chất lượng nếu máy yếu
    if (!lowQ) { cnt++; if (cost > 12 || dt > 50) slow++; if (cnt >= 90) { if (slow > 30) { lowQ = true; size(); } cnt = 0; slow = 0; } }
    requestAnimationFrame(frame);
  }

  size(); addEventListener("resize", () => { clearTimeout(size._t); size._t = setTimeout(size, 150); });
  if (reduce) return;
  if (window.matchMedia && matchMedia("(pointer: fine)").matches) {
    let lx = 0, ly = 0;
    addEventListener("pointermove", e => {
      const px = e.clientX * dpr, py = e.clientY * dpr; if (Math.hypot(px - lx, py - ly) < 14 * dpr) return; lx = px; ly = py;
      if (sparks.length > 60) return;
      sparks.push({ x: px, y: py, vx: (Math.random() - .5) * .05 * dpr, vy: (Math.random() - .7) * .05 * dpr, s: (3 + Math.random() * 4) * dpr, rot: Math.random() * TAU, life: 0, max: 600 + Math.random() * 500, col: Math.random() < .7 ? "#ffd56b" : "#bff4ff" });
    }, { passive: true });
  }
  nextShoot = performance.now() + 1200;
  requestAnimationFrame(frame);
})();

/* ===== ảnh sản phẩm động: trống đồng xoay + khối 3D (Clone) / chip GPU (VPS) ===== */
(function () {
  const reduce = !window.BRfxOn;
  const TAU = Math.PI * 2, W = 460, H = 260;
  let medal = null;
  const getMedal = () => (medal || !window.BRbuildDrum) ? medal : (medal = window.BRbuildDrum(220));
  const seedOf = s => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  const vis = new Set();
  const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => e.isIntersecting ? vis.add(e.target) : vis.delete(e.target))) : null;

  function scan() {
    document.querySelectorAll(".thumb canvas[data-id]").forEach(c => {
      if (c._fx) return; c._fx = 1; c._seed = seedOf(c.dataset.id); c._kind = c.dataset.c === "vps" ? "vps" : "clone";
      c._card = c.closest(".card"); if (io) io.observe(c); else vis.add(c); draw(c, performance.now());
    });
    for (const c of vis) if (!c.isConnected) vis.delete(c);
  }

  /* --- khối lập phương 3D --- */
  const V = Array.from({ length: 8 }, (_, i) => [i & 1 ? 1 : -1, i & 2 ? 1 : -1, i & 4 ? 1 : -1]);
  const F = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 2, 6, 4], [1, 5, 7, 3], [0, 4, 5, 1], [2, 3, 7, 6]];
  const LIGHT = (() => { const v = [-.45, -.7, -.55], m = Math.hypot(...v); return v.map(a => a / m); })();
  function cube(x, cx, cy, s, ay, ax, hue, glow) {
    const ca = Math.cos(ay), sa = Math.sin(ay), cb = Math.cos(ax), sb = Math.sin(ax), f = 4;
    const R = V.map(([X, Y, Z]) => { const x1 = X * ca + Z * sa, z1 = -X * sa + Z * ca, y2 = Y * cb - z1 * sb, z2 = Y * sb + z1 * cb; return [x1, y2, z2]; });
    const P = R.map(([X, Y, Z]) => [cx + X * s * f / (f + Z), cy + Y * s * f / (f + Z)]);
    const faces = F.map(fc => {
      const [a, b, , d] = fc.map(i => R[i]);
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [d[0] - a[0], d[1] - a[1], d[2] - a[2]];
      let n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; const m = Math.hypot(...n); n = n.map(q => q / m);
      return { fc, z: fc.reduce((q, i) => q + R[i][2], 0) / 4, l: Math.abs(n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]) };
    }).sort((p, q) => q.z - p.z);
    x.save();
    for (const fa of faces) {
      const pts = fa.fc.map(i => P[i]);
      x.beginPath(); pts.forEach(([px, py], i) => i ? x.lineTo(px, py) : x.moveTo(px, py)); x.closePath();
      x.fillStyle = `hsl(${hue} 85% ${28 + fa.l * 38}%)`; x.fill();
      x.strokeStyle = `hsla(${hue + 20} 100% 75% / .9)`; x.lineWidth = 1.6; x.stroke();
      // ô khối bên trong mỗi mặt
      const c0 = pts.reduce((q, p) => [q[0] + p[0] / 4, q[1] + p[1] / 4], [0, 0]);
      x.beginPath(); pts.forEach(([px, py], i) => { const qx = c0[0] + (px - c0[0]) * .45, qy = c0[1] + (py - c0[1]) * .45; i ? x.lineTo(qx, qy) : x.moveTo(qx, qy); }); x.closePath();
      x.strokeStyle = `hsla(${hue + 20} 100% 80% / .45)`; x.lineWidth = 1.2; x.stroke();
    }
    x.restore();
  }

  /* --- chip GPU với quạt --- */
  function chip(x, cx, cy, t, k, fast) {
    const S = 74;
    // đường mạch + xung điện
    x.save(); x.lineWidth = 1.4;
    for (let i = 0; i < 12; i++) {
      const side = i % 4, off = ((i >> 2) - 1) * 22, len = 70 + ((k >> i) & 31);
      const sx = side === 0 ? cx - S : side === 1 ? cx + S : cx + off, sy = side === 2 ? cy - S : side === 3 ? cy + S : cy + off;
      const dx = side === 0 ? -1 : side === 1 ? 1 : 0, dy = side === 2 ? -1 : side === 3 ? 1 : 0;
      const ex = sx + dx * len, ey = sy + dy * len, bx = ex + (dy ? (i % 3 - 1) * 26 : 0), by = ey + (dx ? (i % 3 - 1) * 20 : 0);
      x.strokeStyle = "rgba(255,203,69,.35)"; x.beginPath(); x.moveTo(sx, sy); x.lineTo(ex, ey); x.lineTo(bx, by); x.stroke();
      x.fillStyle = "rgba(255,203,69,.6)"; x.beginPath(); x.arc(bx, by, 2.6, 0, TAU); x.fill();
      const ph = ((t * (fast ? .0016 : .0007) + i * .17) % 1), seg1 = len, seg2 = Math.hypot(bx - ex, by - ey), tot = seg1 + seg2, d = ph * tot;
      const px = d < seg1 ? sx + dx * d : ex + (bx - ex) * ((d - seg1) / (seg2 || 1)), py = d < seg1 ? sy + dy * d : ey + (by - ey) * ((d - seg1) / (seg2 || 1));
      x.fillStyle = "rgba(160,245,255,.28)"; x.beginPath(); x.arc(px, py, 6, 0, TAU); x.fill();
      x.fillStyle = "#c8f9ff"; x.beginPath(); x.arc(px, py, 2.4, 0, TAU); x.fill();
    }
    x.restore();
    // thân chip
    x.save();
    const rr = (X, Y, w, h, r) => { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); };
    rr(cx - S, cy - S, S * 2, S * 2, 12); const bg = x.createLinearGradient(cx - S, cy - S, cx + S, cy + S); bg.addColorStop(0, "#1b1540"); bg.addColorStop(1, "#0b0a22");
    x.fillStyle = bg; x.fill(); x.strokeStyle = "#e0a948"; x.lineWidth = 2; x.stroke();
    for (let i = -3; i <= 3; i++) { x.fillStyle = "#c9923c"; [[cx - S - 7, cy + i * 18 - 2, 7, 4], [cx + S, cy + i * 18 - 2, 7, 4], [cx + i * 18 - 2, cy - S - 7, 4, 7], [cx + i * 18 - 2, cy + S, 4, 7]].forEach(r => x.fillRect(...r)); }
    // quạt
    const fr = S * .72, rot = t * (fast ? .022 : .008);
    x.beginPath(); x.arc(cx, cy, fr + 4, 0, TAU); x.fillStyle = "#07061a"; x.fill(); x.strokeStyle = "rgba(255,203,69,.5)"; x.lineWidth = 1.5; x.stroke();
    x.save(); x.translate(cx, cy); x.rotate(rot);
    for (let b = 0; b < 7; b++) { x.rotate(TAU / 7); x.beginPath(); x.moveTo(6, 0); x.quadraticCurveTo(fr * .55, -fr * .42, fr, -fr * .08); x.quadraticCurveTo(fr * .6, fr * .05, 6, 6); x.closePath();
      const bgr = x.createLinearGradient(0, 0, fr, 0); bgr.addColorStop(0, "#5b3df5"); bgr.addColorStop(1, "#b68bff"); x.fillStyle = bgr; x.globalAlpha = .9; x.fill(); }
    x.restore();
    x.beginPath(); x.arc(cx, cy, 9, 0, TAU); x.fillStyle = "#e0a948"; x.fill();
    x.fillStyle = "rgba(255,226,154,.9)"; x.font = "600 11px ui-monospace,monospace"; x.textAlign = "left"; x.fillText("GPU", cx - S + 9, cy - S + 17);
    x.restore();
  }

  function draw(c, t) {
    const x = c.getContext("2d"); if (c.width !== W) { c.width = W; c.height = H; }
    const k = c._seed, vps = c._kind === "vps", hue = vps ? 262 : 212, fast = !!(c._card && c._card.matches(":hover"));
    c._t = (c._t || 0) + (c._last ? (t - c._last) * (fast ? 2.4 : 1) : 0); c._last = t; const T = c._t + (k % 5000);
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, `hsl(${hue} 75% 20%)`); g.addColorStop(1, `hsl(${hue + 35} 80% 9%)`);
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    // lưới phối cảnh chạy
    x.save(); x.strokeStyle = `hsla(${hue + 10} 90% 70% / .12)`; x.lineWidth = 1;
    const off = (T * .03) % 26; for (let i = -2; i < 14; i++) { const y = H * .62 + Math.pow((i * 26 + off) / 26, 1.6) * 9; if (y > H) break; x.beginPath(); x.moveTo(0, y); x.lineTo(W, y); x.stroke(); }
    for (let i = -10; i <= 10; i++) { x.beginPath(); x.moveTo(W / 2 + i * 14, H * .62); x.lineTo(W / 2 + i * 70, H); x.stroke(); }
    x.restore();
    // trống đồng xoay phía sau
    const m = getMedal();
    if (m) { const R = H * .66; x.save(); x.globalAlpha = .30 + (fast ? .12 : 0); x.translate(W / 2, H / 2); x.rotate(T * .00035 * (k % 2 ? 1 : -1)); x.drawImage(m, -R, -R, R * 2, R * 2); x.restore(); }
    // hào quang
    const halo = x.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, H * .55); halo.addColorStop(0, `hsla(${hue} 100% 65% / ${fast ? .38 : .22})`); halo.addColorStop(1, `hsla(${hue} 100% 65% / 0)`);
    x.fillStyle = halo; x.fillRect(0, 0, W, H);
    if (vps) chip(x, W / 2, H / 2, T, k, fast);
    else {
      const bob = Math.sin(T * .002) * 7;
      x.save(); x.fillStyle = "rgba(0,0,0,.35)"; x.beginPath(); x.ellipse(W / 2, H * .82, 52 - bob * 1.5, 9, 0, 0, TAU); x.fill(); x.restore();
      for (let i = 0; i < 5; i++) { const a = T * .0011 + i * TAU / 5, ox = W / 2 + Math.cos(a) * 130, oy = H / 2 + Math.sin(a) * 42, front = Math.sin(a) > 0;
        if (!front) cube(x, ox, oy, 9 + (i % 2) * 3, T * .002 + i, .6, hue + 25, 6); }
      cube(x, W / 2, H / 2 + bob - 4, 44, T * .0012 + k, .55 + Math.sin(T * .0007) * .25, hue, fast ? 28 : 14);
      for (let i = 0; i < 5; i++) { const a = T * .0011 + i * TAU / 5, ox = W / 2 + Math.cos(a) * 130, oy = H / 2 + Math.sin(a) * 42;
        if (Math.sin(a) > 0) cube(x, ox, oy, 11 + (i % 2) * 3, T * .002 + i, .6, hue + 25, 8); }
    }
    // sao lấp lánh
    for (let i = 0; i < 9; i++) { const sx = ((k >> (i % 13)) * 37 + i * 97) % W, sy = ((k >> (i % 11)) * 53 + i * 61) % H, a = .5 + .5 * Math.sin(T * .003 + i * 1.7), s = 2 + (i % 3);
      x.save(); x.globalAlpha = a; x.fillStyle = i % 3 ? "#fff" : "#ffd56b"; x.translate(sx, sy); x.rotate(T * .001);
      x.beginPath(); for (let j = 0; j < 8; j++) { const r = j % 2 ? s * .3 : s * 1.6, an = j * Math.PI / 4; x.lineTo(Math.cos(an) * r, Math.sin(an) * r); } x.closePath(); x.fill(); x.restore(); }
  }

  const grid = document.getElementById("grid");
  if (grid) new MutationObserver(() => setTimeout(scan, 0)).observe(grid, { childList: true });
  scan();
  if (reduce) return;
  let last = 0;
  (function loop(t) {
    if (!document.hidden && t - last > 32) { last = t;
      for (const c of vis) { const hot = c._card && c._card.matches(":hover"); if (hot || t >= (c._next || 0)) { draw(c, t); c._next = t + (hot ? 0 : 80); } } }
    requestAnimationFrame(loop);
  })(0);
})();
