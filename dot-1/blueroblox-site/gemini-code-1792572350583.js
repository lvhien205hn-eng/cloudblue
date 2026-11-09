// Hàm tự động kiểm tra và đếm số lượng acc theo từng định dạng
function skCount() {
  const raw = $("sk-lines").value || "";
  const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  
  let totalValid = 0;
  let withCookie = 0;
  let userPassOnly = 0;
  let invalid = 0;

  lines.forEach(line => {
    const parts = line.split(":");
    // Ít nhất phải có user và pass (không được để trống)
    if (parts.length >= 2 && parts[0].trim() !== "" && parts[1].trim() !== "") {
      totalValid++;
      // Nếu có từ 3 phần trở lên (user:pass:cookie) và phần cookie không trống
      if (parts.length >= 3 && parts.slice(2).join(":").trim() !== "") {
        withCookie++;
      } else {
        userPassOnly++;
      }
    } else {
      invalid++;
    }
  });

  // Tự động tìm thẻ hiển thị số lượng trên web của bạn để in kết quả chi tiết
  const countEl = document.getElementById("sk-count") || document.getElementById("sk-info") || document.querySelector(".sk-count");
  if (countEl) {
    countEl.innerHTML = `Tổng hợp lệ: <b>${totalValid}</b> acc (Có cookie: <b>${withCookie}</b> | Chỉ user:pass: <b>${userPassOnly}</b>)` + 
                        (invalid > 0 ? ` | <span style="color:#ff4d4f;">Lỗi định dạng: <b>${invalid}</b> dòng</span>` : "");
  }

  return { totalValid, withCookie, userPassOnly, invalid, validLines: lines };
}

// 1. Khi gõ hoặc dán trực tiếp vào ô text -> tự động đếm ngay lập tức
$("sk-lines").oninput = () => skCount();

// 2. Khi chọn file .txt -> tự động đọc file, ghép vào ô và báo số lượng acc
$("sk-file").onchange = () => {
  const f = $("sk-file").files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    const t = String(rd.result || "").replace(/\r/g, "");
    $("sk-lines").value = $("sk-lines").value.trim() ? ($("sk-lines").value.trim() + "\n" + t) : t;
    const stats = skCount();
    toast(`Đã đọc file! Phát hiện ${stats.totalValid} acc hợp lệ (${stats.withCookie} có cookie)` + (stats.invalid ? `, ${stats.invalid} dòng lỗi` : ""));
  };
  rd.readAsText(f);
};

// 3. Khi bấm "Thêm vào kho" -> kiểm tra lần cuối rồi gửi lên server
$("sk-save").onclick = async () => {
  const stats = skCount();
  if (stats.totalValid === 0) {
    return toast("Không có tài khoản hợp lệ nào để thêm vào kho!");
  }
  if (stats.invalid > 0) {
    if (!confirm(`Có ${stats.invalid} dòng bị sai định dạng (thiếu ':'). Bạn có muốn tự động bỏ qua dòng lỗi và chỉ nạp ${stats.totalValid} acc hợp lệ không?`)) {
      return;
    }
  }

  // Chỉ lọc lấy những dòng đúng định dạng (user:pass hoặc user:pass:cookie) để gửi lên kho
  const cleanLines = ($("sk-lines").value || "")
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(l => {
      const p = l.split(":");
      return p.length >= 2 && p[0].trim() !== "" && p[1].trim() !== "";
    })
    .join("\n");

  const { data } = await sb.rpc("admin_add_stock", { p_product: stockFor, p_lines: cleanLines });
  toast("Đã thêm " + data + " sản phẩm vào kho");
  
  // Xóa trắng ô nhập sau khi nạp thành công và đặt lại bộ đếm
  $("sk-lines").value = "";
  $("sk-file").value = "";
  skCount();
};