# -*- coding: utf-8 -*-
"""28/11 · KHÁCH KHÔNG THẤY CÁCH MÁY CHỦ LÀM — kiểm tĩnh mọi chỗ khách nhìn thấy (web, app PC, app Android, câu lỗi máy chủ):
   không còn tên nhà cung cấp đường truyền / bộ nén / giả lập trong CHỮ HIỆN RA (chú thích trong mã không tính).
   Chạy: python3 winpc/tests/web/test_no_leak.py"""
import os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OK = FAIL = 0


def ck(name, cond, info=None):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "" if info is None else f"→ {info!r}"[:400])


def rd(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def js_strings(src):
    """Chuỗi '...' "..." `...` của JS/HTML, bỏ chú thích // /* */ <!-- --> (thô, đủ cho kiểm tĩnh)."""
    out = []; i = 0; n = len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i) and (i == 0 or src[i - 1] not in ":\\"):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2; continue
        if src.startswith("<!--", i):
            j = src.find("-->", i + 4); i = n if j < 0 else j + 3; continue
        if c in "'\"`":
            q = c; j = i + 1; buf = []
            while j < n and src[j] != q:
                if src[j] == "\\": buf.append(src[j:j + 2]); j += 2; continue
                if src[j] == "\n" and q != "`": break
                buf.append(src[j]); j += 1
            out.append("".join(buf)); i = j + 1; continue
        i += 1
    return out


VENDOR = re.compile(r"Cloudflare|scrcpy|MuMu|MEmu|LDPlayer|NVENC|x264|openh264|cbvideo|broadway\.js", re.I)

print("1. Web điều khiển máy (play.html)")
play = rd("blueroblox-site/play.html")
cands = re.findall(r'add\("([^"]+)",', play)
ck("tên đường (Thông số, dòng đang nối, báo lỗi) không nêu nhà cung cấp", cands and not any(VENDOR.search(c) for c in cands), cands)
ck("đường vòng tên 'trung chuyển' (+ 2 / 3 cho cổng phụ) — dịch EN 'relay'",
   {"trung chuyển", "trung chuyển 2", "trung chuyển 3"} <= set(cands) and '["trung chuyển", "relay"]' in play)
ck("Thông số: chỉ hiện 'nén:' khi máy chủ gửi (máy chủ chỉ gửi cho admin)",
   '${s.enc ? " · nén: " + s.enc : ""}' in play and 'nén: ${s.enc || "?"}' not in play)
vis = [s for s in js_strings(play) if VENDOR.search(s)]
# còn lại được phép: dòng cbvideo / openh264 (CHỈ hiện khi máy chủ gửi cbs — chỉ admin) + tên file thư viện tải về (không hiện)
allow = re.compile(r"^(/broadway\.js|Broadway\.js - Worker init|\\ncbvideo: màn ảo .*| · nén \$\{ss\.cbs\.enc\} ms \(openh264\)|cbvideo: màn ảo |cbvideo: display )$")
bad = [s for s in vis if not allow.match(s)]
ck("không chữ hiện ra nào khác nêu nhà cung cấp / bộ nén (trừ dòng chỉ admin thấy)", not bad, bad[:6])
ck("lỗi tải bộ giải mã phần mềm không nêu tên thư viện", "không tải được bộ giải mã phần mềm" in play and "không tải được /broadway.js" not in play)
ck("dòng cbvideo / bộ nén Android chỉ hiện khi có dữ liệu admin (ss.cbs / ss.efps)",
   "(ss && ss.cbs ?" in play and "(ss && ss.efps != null ?" in play)
ck("câu lỗi mới của máy chủ có bản EN", "Máy chủ chưa lấy được hình của máy này — thử mở lại" in play)
ck("bản web-2.9", 'const VER = "web-2.9"' in play)

print("2. Trang điều khiển cũ (phone.html) + trang chính (index.html)")
ph = rd("blueroblox-site/phone.html")
ck("phone.html: không còn 'Chữ từ máy ảo'", "Chữ từ máy ảo" not in ph and 'L("Chữ từ máy", "Text from the cloud phone")' in ph)
ck("phone.html: chữ 'cpapi' chỉ hiện cho admin", 'main.legacy && !$("adminlink").hidden' in ph)
idx = rd("blueroblox-site/index.html")
ck("index.html: giới thiệu app không nói 'máy ảo'", "copy từ máy ảo ra" not in idx and "copy chữ từ máy ra" in idx)
ck("index.html: gói Game nặng 3D không nói 'máy ảo không có card'", "máy ảo không có card đồ hoạ" not in idx and "(no GPU)" not in idx)

print("3. App PC")
brs = rd("pc-client/brstream.py"); bpc = rd("pc-client/bluepc.py"); ben = rd("pc-client/bluepc_en.py")
ck("brstream: đường vòng tên 'trung chuyển' (không 'Cloudflare')",
   'self.path = ("trực tiếp" if kind == "direct" else "trung chuyển")' in brs and '"Cloudflare")' not in brs)
ck("bluepc: dòng thông số chỉ thêm tên bộ nén khi máy chủ gửi", 'enc = str(d.get("enc") or "").upper()' in bpc
   and "{str(d.get('enc', '')).upper()}" not in bpc and '(f" · {enc}" if enc else "")' in bpc)
sys.path.insert(0, os.path.join(ROOT, "pc-client"))
import bluepc_en as E
ck("EN: 'trung chuyển' → relay · 'trực tiếp' → direct · dòng 4 phần dịch được",
   E.tr("trung chuyển") == "relay" and E.tr("trực tiếp") == "direct"
   and E.tr("60 khung/s · 3.2 Mbps · trễ mạng 40 ms · relay") == "60 fps · 3.2 Mbps · latency 40 ms · relay")
ck("EN: câu lỗi mới của máy chủ", E.tr("Máy chủ chưa lấy được hình của máy này — thử mở lại.").startswith("The server couldn't get"))

print("4. App Android")
ca = rd("android-app/app/src/main/java/shop/blueroblox/app/ControlActivity.java")
srv = rd("android-app/app/src/main/java/shop/blueroblox/app/Srv.java")
ck("ControlActivity: không còn ': \"Cloudflare\"' trong Thông số", ': "Cloudflare")' not in ca and ca.count('Ui.L("trung chuyển", "relay")') == 2)
ck("Srv.java: câu lỗi mới của máy chủ có bản EN", "Máy chủ chưa lấy được hình của máy này — thử mở lại" in srv)

print("5. Máy chủ phát hình (bluestream.py)")
bs = rd("windows/bluestream.py")
denies = re.findall(r'Deny\("[A-Z_]+",\s*"([^"]+)"', bs)
ck("mọi câu Deny gửi khách không nêu cửa sổ / giả lập / tên phần mềm",
   denies and not any(re.search(r"cửa sổ|giả lập|MuMu|LDPlayer|MEmu|scrcpy|adb|Windows", d) for d in denies), [d for d in denies if re.search(r"cửa sổ|giả lập", d)])
ck("WELCOME (điều khiển + xem trước) gửi enc qua _enc_name() (khách = '')", bs.count('"enc": self._enc_name()') == 3 and '"enc": self.enc.enc' not in bs)
blk = bs[bs.index("if self._adm():                                        # 28/11a"):]
blk = blk[:blk.index("self.link.send_nowait(S_STATS")]
ck("S_STATS: ctl / efps / rs / rk / dr / a9 / kq / cbs nằm trong 'if self._adm()'",
   all(f'st["{k}"]' in blk for k in ("ctl", "efps", "rs", "rk", "dr", "a9", "kq", "cbs")))
ck("_adm() dựa trên me['admin'] (đã qua is_admin + mã 2 bước)", 'return bool((self.me or {}).get("admin"))' in bs)

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
