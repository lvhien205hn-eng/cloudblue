// BlueRoblox Admin — app máy tính Windows CHỈ CHO ADMIN (không phát hành cho khách).
// Mở thẳng web blueroblox.shop trong cửa sổ riêng (Edge WebView2): luôn là bản web mới nhất, không cần cập nhật app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{WebviewUrl, WebviewWindowBuilder};

// Chạy trong mọi trang: báo web "đang ở app PC", mở link "tab mới" ngay trong cửa sổ app,
// trang điều khiển máy có nút "← Danh sách máy" để quay lại.
const INIT: &str = r#"
(function () {
  window.__BR_PC = 1;
  var same = function (u) { try { var x = new URL(u, location.href); if (/(^|\.)blueroblox\.shop$/.test(x.hostname)) { location.href = x.href; return true; } } catch (e) {} return false; };
  var _open = window.open;
  window.open = function (u, n, f) { if (u && same(u)) return window; return _open ? _open.apply(window, arguments) : null; };
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a[target=_blank]") : null;
    if (a && a.href && same(a.href)) e.preventDefault();
  }, true);
  document.addEventListener("DOMContentLoaded", function () {
    if (!/\/phone\.html/.test(location.pathname)) return;
    var b = document.createElement("button");
    b.textContent = "← Danh sách máy";
    b.style.cssText = "position:fixed;left:10px;bottom:10px;z-index:2147483647;padding:8px 14px;border-radius:10px;border:1px solid rgba(255,255,255,.25);background:rgba(10,20,45,.85);color:#fff;font:600 13px system-ui;cursor:pointer";
    b.onclick = function () { if (history.length > 1) history.back(); else location.href = "https://blueroblox.shop/"; };
    document.body.appendChild(b);
  });
})();
"#;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External("https://blueroblox.shop/?app=pc".parse().unwrap()))
                .title("BlueRoblox Admin")
                .inner_size(1280.0, 820.0)
                .min_inner_size(900.0, 600.0)
                .center()
                .initialization_script(INIT)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("không mở được BlueRoblox Cloud");
}
