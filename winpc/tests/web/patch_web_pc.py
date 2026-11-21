# -*- coding: utf-8 -*-
"""Gắn thẻ "💻 Máy PC" (kho máy PC cho thuê, SQL v41) vào blueroblox-site/index.html.
   python3 patch_web_pc.py <index gốc> <index ra>
   Mỗi mốc phải có ĐÚNG 1 lần trong file gốc; file đã gắn rồi thì báo và dừng (không gắn 2 lần)."""
import hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = 'id="pane-pc"'
RENTBAR = '\n    <div class="xp-host" id="pca-rentbar" hidden></div>'      # 🔔 2 ô máy sắp / đã hết hạn (VPS / Máy PC · ĐT đám mây) — hiện ở mọi tab của Bảng quản trị


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8", newline="") as f:
        return f.read()


def insert(s, anchor, text, after=False):
    n = s.count(anchor)
    if n != 1:
        raise SystemExit("MỐC không đúng 1 lần (%d): %r" % (n, anchor[:70]))
    i = s.index(anchor)
    if after:
        i += len(anchor)
    return s[:i] + text + s[i:]


def main(src, dst):
    with open(src, encoding="utf-8", newline="") as f:
        s = f.read()
    if MARK in s:
        raise SystemExit("File này đã có thẻ Máy PC — không gắn lần 2.")
    if "\r\n" in s:
        raise SystemExit("File gốc dùng CRLF — dừng để khỏi trộn kiểu xuống dòng.")
    base_len = len(s)
    pane, dlg, script = read("pc_pane.html"), read("pc_dialogs.html"), read("pc_script.html") + read("pc_shop.html")
    for name, t in (("pc_pane.html", pane), ("pc_dialogs.html", dlg), ("pc_script.html", read("pc_script.html")), ("pc_shop.html", read("pc_shop.html"))):
        if "\r" in t or not t.endswith("\n"):
            raise SystemExit("%s: phải dùng LF và kết thúc bằng xuống dòng" % name)
    s = insert(s, '<button data-tab="vps">🖥️ Máy VPS <span class="badge" id="vps-badge" hidden></span></button>',
               '<button data-tab="pc">💻 Máy PC <span class="badge" id="pc-badge" hidden></span></button>', after=True)
    s = insert(s, '    <div class="dbody" id="pane-biz" hidden>', pane)
    s = insert(s, '<div class="admalert" id="adm-alert" hidden></div>', RENTBAR, after=True)
    s = insert(s, '<!-- ADMIN: SỬA MÁY VPS -->\n<div class="modal" id="vmdlg" hidden>', "<!-- ADMIN: MÁY PC CHO THUÊ (SQL v41) -->\n" + dlg + "\n")
    s = insert(s, "</body>", script)
    added = len('<button data-tab="pc">💻 Máy PC <span class="badge" id="pc-badge" hidden></span></button>') + len(pane) + len(dlg) + len(script) \
        + len("<!-- ADMIN: MÁY PC CHO THUÊ (SQL v41) -->\n") + 1 + len(RENTBAR)
    assert len(s) == base_len + added, (len(s), base_len, added)
    data = s.encode("utf-8")
    with open(dst, "wb") as f:
        f.write(data)
    print("đã ghi %s: %d byte · sha256 %s" % (dst, len(data), hashlib.sha256(data).hexdigest()))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
