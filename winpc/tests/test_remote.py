# -*- coding: utf-8 -*-
"""Thử agent/pcremote.py (điều khiển từ xa trên máy PC thuê) — chạy được trên mọi máy có Python (+ ffmpeg cho phần quay / nén thử).
   Máy chủ phát hình được thay bằng 1 máy chủ TLS giả trong tiến trình; chuột / phím đi vào NullIO (chỉ ghi lại).
   Chạy:  python3 tests/test_remote.py
"""
import datetime, hashlib, io, json, os, shutil, socket, ssl, struct, subprocess, sys, tempfile, threading, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "agent"))
import pcremote as R                                               # noqa: E402

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
OK = FAIL = 0
FF = shutil.which("ffmpeg")


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:700])


def wait(fn, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(step)
    return fn()


# ------------------------------------------------------------------ 1. chọn chất lượng
print("1. Chọn cỡ hình / khung giây / bitrate")
ck("fit: không phóng to, giữ tỉ lệ, cạnh chẵn", R.fit(1920, 1080, 1280) == (1280, 720) and R.fit(1366, 768, 1920) == (1366, 768) and R.fit(1080, 1920, 960) == (540, 960)
   and R.fit(1365, 767, 0) == (1364, 766) and R.fit(3440, 1440, 1600) == (1600, 670), (R.fit(1365, 767, 0), R.fit(3440, 1440, 1600)))
ck("Tự động / Cân bằng: màn 1080p giữ nguyên 1080p, 30 khung, 4500 kbps", R.plan("auto", 0, 0, 0, 0, 1920, 1080) == (1920, 1080, 30, 4500, 4500) and R.plan("bal", 0, 0, 0, 0, 1920, 1080)[:3] == (1920, 1080, 30)
   and R.plan("auto", 60, 0, 0, 0, 1920, 1080)[:3] == (1920, 1080, 30))
ck("Tiết kiệm: cạnh dài 1280 · Nét: 60 khung, 9000 kbps", R.plan("eco", 0, 0, 0, 0, 1920, 1080) == (1280, 720, 30, 2000, 2000) and R.plan("hd", 0, 0, 0, 0, 2560, 1440) == (1920, 1080, 60, 9000, 9000))
ck("app xin ít khung / hình nhỏ hơn (điện thoại) → theo app", R.plan("hd", 30, 1280, 0, 0, 1920, 1080)[:3] == (1280, 720, 30) and R.plan("auto", 15, 0, 0, 0, 1920, 1080)[2] == 15)
ck("nén bằng CPU, Tự động: tối đa cạnh 1600, 30 khung · khách tự chọn: tối đa 1920, 60 khung", R.plan("auto", 0, 0, 0, 0, 1920, 1080, cpu=True)[:3] == (1600, 900, 30)
   and R.plan("hd", 0, 0, 0, 0, 1920, 1080, cpu=True)[:3] == (1920, 1080, 60) and R.plan("uhd", 120, 0, 0, 0, 2560, 1440, cpu=True)[:3] == (1920, 1080, 60))
ck("21.11g Siêu nét: màn 2K giữ nguyên 2560×1440, 60 khung, 16000 kbps · màn 1080p giữ 1080p", R.plan("uhd", 0, 0, 0, 0, 2560, 1440) == (2560, 1440, 60, 16000, 16000)
   and R.plan("uhd", 0, 0, 0, 0, 1920, 1080) == (1920, 1080, 60, 16000, 16000) and "uhd" in R.QS)
ck("app báo máy chỉ chịu 60 khung (fps) với Cân bằng → vẫn 30 khung như cũ (fps chỉ để HẠ)", R.plan("bal", 60, 0, 0, 0, 1920, 1080)[:3] == (1920, 1080, 30))
ck("21.11g khách tự chọn khung/giây (fpsx): đúng như chọn (5–120), kể cả cao hơn mặc định của mức nét; máy người xem chịu ít hơn thì theo máy",
   R.plan("bal", 0, 0, 0, 0, 1920, 1080, fps_fix=60)[2] == 60 and R.plan("hd", 0, 0, 0, 0, 1920, 1080, fps_fix=30)[2] == 30 and R.plan("uhd", 0, 0, 0, 0, 1920, 1080, fps_fix=120)[2] == 120
   and R.plan("hd", 0, 0, 0, 0, 1920, 1080, fps_fix=500)[2] == 120 and R.plan("eco", 0, 0, 0, 0, 1920, 1080, fps_fix=2)[2] == 5 and R.plan("hd", 30, 0, 0, 0, 1920, 1080, fps_fix=60)[2] == 30
   and R.plan("auto", 0, 0, 0, 0, 1920, 1080, fps_fix=60)[2] == 60 and R.plan("auto", 0, 0, 0, 2000, 1920, 1080, fps_fix=60)[2] == 30)
ck("21.11g tự chọn độ nét: mạng tụt vẫn GIỮ độ phân giải (không mờ), dưới 900 kbps mới bớt", R.plan("hd", 0, 0, 0, 2000, 1920, 1080)[:2] == (1920, 1080)
   and R.plan("bal", 0, 0, 0, 1200, 1920, 1080, fps_fix=60)[:3] == (1920, 1080, 60) and R.plan("uhd", 0, 0, 0, 800, 2560, 1440)[:3] == (1280, 720, 30))
ck("bitrate bị kéo xuống → bớt điểm ảnh + khung (hình không vỡ ô)", R.plan("auto", 0, 0, 0, 800, 1920, 1080)[:4] == (1280, 720, 20, 800) and R.plan("auto", 0, 0, 0, 400, 1920, 1080)[:4] == (960, 540, 15, 400)
   and R.plan("auto", 0, 0, 0, 2000, 1920, 1080)[:4] == (1600, 900, 30, 2000) and R.plan("auto", 0, 0, 0, 50, 1920, 1080)[3] == R.MIN_KBPS, R.plan("auto", 0, 0, 0, 800, 1920, 1080))
ck("app tự đặt bitrate: làm trần (trong khoảng 300–20000)", R.plan("auto", 0, 0, 12000, 0, 1920, 1080)[3:] == (12000, 12000) and R.plan("auto", 0, 0, 10 ** 9, 0, 1920, 1080)[4] == 20000 and R.plan("auto", 0, 0, 10, 0, 1920, 1080)[4] == 300)
ck("bắt đầu nhẹ khi người xem dùng 4G / đi đường vòng / app báo mạng chậm", R.kbps_start(4500, "auto", "c") == 1500 and R.kbps_start(4500, "auto", "w", "ws") == 1500 and R.kbps_start(4500, "auto", "w", "direct") == 4500
   and R.kbps_start(4500, "hd", "c") == 4500 and R.kbps_start(4500, "auto", "", "", 1000) == 600 and R.kbps_start(4500, "auto", "", "", 100) == 300)

# ------------------------------------------------------------------ 2. tự chỉnh bitrate
print("2. Tự chỉnh bitrate theo người xem")
r = R.Rate(4500, 4500)
ck("người xem không gửi ACK → không tính là chậm", r.behind_ms(100.0) == 0.0)
for i in range(10): r.sent(1000 + i, 20000, 100.0 + i * 0.033)
r.ack(1004, 100.2, 2000000)
ck("ACK: bỏ các khung đã nhận khỏi hàng chờ, đo trễ nền", len(r.inflight) == 5 and 0 < r.base_ms < 250 and r.goodput(100.2) > 0, (len(r.inflight), r.base_ms))
ck("khung cũ nhất chưa báo nhận đã lâu → tính là chậm", r.behind_ms(101.2) > 800 and r.behind_ms(100.2) < 60, (r.behind_ms(101.2), r.behind_ms(100.2)))
r = R.Rate(4500, 4500)
ck("1–2 lần giật lẻ: chưa hạ bitrate", r.congested(100.0) is None and r.congested(101.0) is None)
n3 = r.congested(102.0)
ck("lặp lại 3 lần trong 20 giây → hạ (≤ 70%), không dưới mức sàn", n3 is not None and R.MIN_KBPS <= n3 <= 4500 * 0.7 and r.cur == n3, n3)
ck("vừa hạ xong: chưa hạ tiếp ngay + chưa tăng lại ngay", r.congested(103.0) is None and r.congested(104.0) is None and r.raise_(110.0) is None)
up = r.raise_(102.0 + 46 + 5)
ck("yên > 45 giây → tăng 1 bước, không vượt trần", up is not None and n3 < up <= 4500, up)
r = R.Rate(4500, 4500); r.congested(10.0, hard=True)
ck("nghẽn thật (đường lên của máy / máy chủ báo khách chậm): 2 lần là hạ", r.congested(11.0, hard=True) is not None)
r = R.Rate(4500, 320)
for t in (1, 2, 3, 20, 21, 22, 40, 41, 42): r.congested(float(t), hard=True)
ck("hạ mãi cũng không dưới 300 kbps", r.cur >= R.MIN_KBPS, r.cur)

# ------------------------------------------------------------------ 3. ghép RTP
print("3. Ghép gói RTP thành khung H.264")


def rtp(seq, payload, marker=False): return bytes([0x80, 0x60 | (0x80 if marker else 0)]) + struct.pack(">H", seq & 0xFFFF) + bytes(8) + payload


a = R.RtpAssembler(); SC = b"\x00\x00\x00\x01"
ck("1 NAL / gói, bit marker = hết khung", a.feed(rtp(1, b"\x41abc")) is None and a.feed(rtp(2, b"\x41def", True)) == (SC + b"\x41abc" + SC + b"\x41def", False, False))
stap = b"\x78" + struct.pack(">H", 3) + b"\x67\x01\x02" + struct.pack(">H", 2) + b"\x68\x03"
ck("STAP-A (SPS + PPS gộp) rồi khung khoá chia FU-A", a.feed(rtp(3, stap)) is None and a.feed(rtp(4, b"\x7c\x85AAA")) is None and a.feed(rtp(5, b"\x7c\x05BBB")) is None
   and a.feed(rtp(6, b"\x7c\x45CCC", True)) == (SC + b"\x67\x01\x02" + SC + b"\x68\x03" + SC + b"\x65AAABBBCCC", True, True))
ck("mất 1 gói giữa khung → báo khung hỏng (chờ khung khoá), khung sau lại bình thường", a.feed(rtp(8, b"\x41x", True)) == (None, False, False) and a.feed(rtp(9, b"\x41y", True)) == (SC + b"\x41y", False, False))
ck("số thứ tự quay vòng 65535 → 0 không tính là mất gói", R.RtpAssembler().feed(rtp(65535, b"\x41a")) is None and (lambda z: (z.feed(rtp(65535, b"\x41a")), z.feed(rtp(0, b"\x41b", True)))[1])(R.RtpAssembler()) == (SC + b"\x41a" + SC + b"\x41b", False, False))
ck("gói rác / quá ngắn bị bỏ qua", a.feed(b"") is None and a.feed(b"\x00" * 20) is None)

# ------------------------------------------------------------------ 4. phím
print("4. Phím")
io_ = R.NullIO(); k = R.Keys(io_)
k.key(0, 29, 0); k.key(1, 29, 0)
ck("phím chữ A (mã Android 29) → phím ảo 0x41 nhấn rồi nhả", io_.ev == [("key", 0x41, True, False), ("key", 0x41, False, False)], io_.ev)
io_.ev.clear(); k.key(0, 29, 0x1000); k.key(0, 29, 0x1000); k.key(1, 29, 0x1000)
ck("app cũ: Ctrl+A gửi kèm meta → tự nhấn Ctrl trước, giữ phím lặp không nhấn Ctrl lần 2, nhả A rồi nhả Ctrl",
   io_.ev == [("key", 0xA2, True, False), ("key", 0x41, True, False), ("key", 0x41, True, False), ("key", 0x41, False, False), ("key", 0xA2, False, False)], io_.ev)
io_.ev.clear(); k.key(0, 113, 0); k.key(0, 31, 0x1000); k.key(1, 31, 0x1000); k.key(1, 113, 0)
ck("app mới gửi riêng phím Ctrl rồi C (meta kèm theo) → không nhấn Ctrl 2 lần", io_.ev == [("key", 0xA2, True, False), ("key", 0x43, True, False), ("key", 0x43, False, False), ("key", 0xA2, False, False)], io_.ev)
io_.ev.clear(); k.key(0, 21, 0); k.key(1, 21, 0); k.key(0, 117, 0); k.key(1, 117, 0); k.key(0, 141, 0); k.key(1, 141, 0)
ck("mũi tên trái + phím Windows là phím mở rộng; F11 = 0x7A", io_.ev == [("key", 0x25, True, True), ("key", 0x25, False, True), ("key", 0x5B, True, True), ("key", 0x5B, False, True),
   ("key", 0x7A, True, False), ("key", 0x7A, False, False)], io_.ev)
io_.ev.clear()
ck("mã phím lạ bị bỏ qua (không làm gì)", k.key(0, 99999, 0) is False and k.key(0, 26, 0) is False and io_.ev == [])
k.key(0, 59, 0); k.key(0, 47, 0x1); k.key(0, 22, 0x1003); io_.ev.clear(); k.release_all()
ck("đóng phiên: NHẢ HẾT phím đang giữ (kể cả phím bổ trợ tự nhấn kèm)", sorted(e[1] for e in io_.ev) == sorted([0xA0, 0x53, 0x27, 0xA4, 0xA2]) and all(e[2] is False for e in io_.ev) and not k.down and not k.auto_held, io_.ev)
io_.ev.clear(); k.tap(*R.CMDS["taskmgr"])
ck("lệnh nút bấm: Trình quản lý tác vụ = Ctrl+Shift+Esc (nhấn theo thứ tự, nhả ngược lại)", [e[1] for e in io_.ev] == [0xA2, 0xA0, 0x1B, 0x1B, 0xA0, 0xA2] and [e[2] for e in io_.ev] == [True] * 3 + [False] * 3, io_.ev)
class _S:
    pass


class _LIO(R.NullIO):
    def paste(self, mode): self.ev.append(("paste", mode))


s_ = _S(); s_.io = R.NullIO(); s_.keys = R.Keys(s_.io)
s_.keys.key(0, 113, 0); s_.io.ev.clear(); R.Session._paste(s_, 1)                 # khách bấm Ctrl+V: Ctrl đã gửi sang máy, V thì không (app / web đổi thành gói Dán)
ck("23.11b dán lúc khách còn giữ Ctrl: nhả Ctrl → Ctrl+V sạch → nhấn lại Ctrl (máy khớp phím khách đang giữ, bấm tiếp Ctrl+C vẫn là copy)",
   s_.io.ev == [("key", 0xA2, False, False), ("key", 0xA2, True, False), ("key", 0x56, True, False), ("key", 0x56, False, False), ("key", 0xA2, False, False),
                ("key", 0xA2, True, False)], s_.io.ev)
s_.keys.key(0, 59, 0); s_.io.ev.clear(); R.Session._paste(s_, 2)
ck("23.11b khách bấm Ctrl+Shift+V (gói dán kiểu 2) → máy Windows bấm đúng Ctrl+Shift+V, rồi nhấn lại Ctrl + Shift đang giữ",
   [e[1:3] for e in s_.io.ev] == [(0xA0, False), (0xA2, False), (0xA2, True), (0xA0, True), (0x56, True), (0x56, False), (0xA0, False), (0xA2, False), (0xA0, True), (0xA2, True)],
   s_.io.ev)
s2_ = _S(); s2_.io = _LIO(); s2_.keys = R.Keys(s2_.io); R.Session._paste(s2_, 1); R.Session._paste(s2_, 2)
ck("23.11b máy Linux (io có paste): không tự bấm Ctrl+V — để cbcap chọn phím dán theo cửa sổ (Konsole: Ctrl+Shift+V…)", s2_.io.ev == [("paste", 1), ("paste", 2)], s2_.io.ev)
ck("bảng phím đủ: chữ, số, F1–F12, bàn phím số, dấu câu, phím bổ trợ", len(R.VK) >= 110 and all(c in R.VK for c in list(range(29, 55)) + list(range(7, 17)) + list(range(131, 143)) + list(range(144, 154)) + [55, 56, 68, 69, 70, 71, 72, 73, 74, 75, 76, 57, 58, 59, 60, 113, 114, 117]))

# ------------------------------------------------------------------ 5. chạm → chuột
print("5. Chạm (điện thoại) → chuột")
io_ = R.NullIO(); t = R.Touch(io_)
t.touch(0, 0, 30000, 20000, 10.0); t.touch(1, 0, 30010, 20005, 10.1)
ck("chạm nhanh = bấm chuột trái đúng chỗ chạm", io_.ev == [("move", 30000, 20000), ("move", 30000, 20000), ("btn", 0, True), ("btn", 0, False)], io_.ev)
io_.ev.clear(); t.touch(0, 0, 30800, 20600, 10.3); t.touch(1, 0, 30800, 20600, 10.35)
ck("chạm lần 2 sát lần 1 trong 0,45 giây = BẤM ĐÚP: lần 2 trúng đúng điểm lần 1 (mở được biểu tượng)", io_.ev[-3:] == [("move", 30000, 20000), ("btn", 0, True), ("btn", 0, False)], io_.ev)
io_.ev.clear(); t.touch(0, 0, 5000, 5000, 20.0); t.tick(20.3)
ck("giữ yên chưa đủ 0,55 giây: chưa làm gì", io_.ev == [("move", 5000, 5000)], io_.ev)
t.tick(20.6); t.touch(2, 0, 9000, 9000, 20.7); t.touch(1, 0, 9000, 9000, 20.8)
ck("giữ yên 0,55 giây = bấm chuột PHẢI (1 lần), nhả tay không bấm thêm", io_.ev == [("move", 5000, 5000), ("btn", 1, True), ("btn", 1, False)], io_.ev)
io_.ev.clear(); t.touch(0, 0, 1000, 1000, 30.0); t.touch(2, 0, 1400, 1300, 30.02); t.touch(2, 0, 3000, 3000, 30.05); t.touch(2, 0, 6000, 6000, 30.1); t.touch(1, 0, 6100, 6100, 30.2)
ck("chạm rồi kéo = giữ chuột trái từ ĐIỂM CHẠM ĐẦU rồi rê theo, nhả tay = nhả chuột", io_.ev == [("move", 1000, 1000), ("move", 1000, 1000), ("btn", 0, True), ("move", 3000, 3000),
   ("move", 6000, 6000), ("move", 6100, 6100), ("btn", 0, False)], io_.ev)
io_.ev.clear(); t.touch(0, 0, 20000, 20000, 40.0); t.touch(0, 1, 30000, 20000, 40.02); t.touch(2, 0, 20000, 30000, 40.1); t.touch(2, 1, 30000, 30000, 40.1); t.touch(1, 0, 20000, 30000, 40.2); t.touch(1, 1, 30000, 30000, 40.2)
wh = [e for e in io_.ev if e[0] == "wheel"]
ck("2 ngón vuốt xuống = lăn chuột lên (nội dung đi theo tay), không bấm nút nào", wh and all(e[1] > 0 and e[2] is False for e in wh) and 200 <= sum(e[1] for e in wh) <= 320 and not any(e[0] == "btn" for e in io_.ev), io_.ev)
io_.ev.clear(); t.touch(0, 0, 1000, 1000, 50.0); t.touch(2, 0, 5000, 5000, 50.05); t.touch(3, 0, 5000, 5000, 50.1)
ck("đang kéo mà bị huỷ (app mất tiêu điểm) → nhả chuột trái", io_.ev[-1] == ("btn", 0, False) and not t.left, io_.ev)
io_.ev.clear(); t.touch(0, 0, 1000, 1000, 60.0); t.touch(2, 0, 5000, 5000, 60.05); t.reset()
ck("đóng phiên lúc đang kéo → nhả chuột trái", io_.ev[-1] == ("btn", 0, False) and t.st is None, io_.ev)
io_ = R.NullIO(); p = R.Pointer(io_)
p.mouse(0, 0, 100, 200); p.mouse(1, 1, 100, 200); p.mouse(2, 1, 150, 250); p.mouse(1, 0, 5, 5); p.mouse(1, 9, 1, 1)
ck("chuột thật (C_MOUSE): rê không bấm, nút phải nhấn / nhả, nút lạ bị bỏ", io_.ev == [("move", 100, 200), ("move", 100, 200), ("btn", 1, True), ("move", 150, 250), ("btn", 1, False),
   ("move", 5, 5), ("btn", 0, True), ("move", 1, 1)], io_.ev)
io_.ev.clear(); p.release_all()
ck("đóng phiên: nhả nút chuột đang giữ", io_.ev == [("btn", 0, False)] and not p.held, io_.ev)
ck("chữ gõ vào máy: bỏ ký tự điều khiển, giữ xuống dòng / tab / chữ có dấu, cắt bớt khi quá dài", R.clean_text("a\x00b\r\nc\td\x1b[31m é") == "ab\nc\td[31m é" and len(R.clean_text("x" * 100000)) == 65536)

# ------------------------------------------------------------------ 6. lệnh ffmpeg + đường nối
print("6. Lệnh ffmpeg · đường nối")
c = R.ff_cmd("ff", "gdi", "nvenc", 1920, 1080, 1920, 1080, 60, 9000, 5004)
ck("quay GDI + card NVIDIA: chỉ quay màn hình chính, vẽ con trỏ, không đổi màu bằng CPU, khung khoá mỗi giây, RTP về 127.0.0.1",
   c[:5] == ["ff", "-hide_banner", "-loglevel", "error", "-nostdin"] and "gdigrab" in c and c[c.index("-video_size") + 1] == "1920x1080" and c[c.index("-draw_mouse") + 1] == "1"
   and "-vf" not in c and c[c.index("-c:v") + 1] == "h264_nvenc" and c[c.index("-g") + 1] == "60" and c[c.index("-b:v") + 1] == "9000k" and c[-1] == "rtp://127.0.0.1:5004?pkt_size=1300", c)
c = R.ff_cmd("ff", "dda", "x264", 1920, 1080, 1280, 720, 30, 2000, 5004)
ck("quay Desktop Duplication + CPU: thu cỡ + đổi sang yuv420p trong cùng chuỗi lọc", c[c.index("-filter_complex") + 1] == "ddagrab=output_idx=0:framerate=30:draw_mouse=1,hwdownload,format=bgra,scale=1280:720:flags=bicubic,format=yuv420p"
   and c[c.index("-c:v") + 1] == "libx264" and "-vf" not in c, c)
ck("card Intel / AMD nhận nv12", "format=nv12" in R.ff_cmd("ff", "gdi", "qsv", 1920, 1080, 1920, 1080, 30, 4500, 1)[R.ff_cmd("ff", "gdi", "qsv", 1920, 1080, 1920, 1080, 30, 4500, 1).index("-vf") + 1]
   and "h264_amf" in R.ff_cmd("ff", "gdi", "amf", 1920, 1080, 1920, 1080, 30, 4500, 1))
ck("bitrate rất thấp: khung khoá thưa gấp đôi", R.enc_args("x264", 15, 400)[R.enc_args("x264", 15, 400).index("-x264-params") + 1].startswith("sliced-threads=0:keyint=30:min-keyint=30"))
pp, cert = R.parse_paths({"direct": [{"host": "1.54.69.205", "port": 8189}, {"host": "192.168.1.6", "port": 8189, "lan": True}], "cert": "AB" * 32, "ws": "wss://d4.cloudblue.vn/v2/stream"})
ck("đường nối: trong mạng nhà trước (1,5 giây), IP ngoài (4 giây), cuối cùng đường vòng", pp == [("direct", "192.168.1.6", 8189, 1.5), ("direct", "1.54.69.205", 8189, 4.0), ("ws", "wss://d4.cloudblue.vn/v2/stream", 0, 8.0)] and cert == "ab" * 32, pp)
ck("không có mã chứng chỉ → không nối thẳng; đường vòng phải là wss:// đúng dạng",
   R.parse_paths({"direct": [{"host": "1.2.3.4", "port": 8189}], "cert": "", "ws": "ws://a.b/x"}) == ([], "")
   and R.parse_paths({"direct": [{"host": "a b; rm", "port": 1}, {"host": "ok.vn", "port": 0}, {"host": "ok.vn", "port": 99999}, "x"], "cert": "cd" * 32, "ws": "wss://a.b/x?y=1 z"}) == ([], "cd" * 32)
   and R.parse_paths(None) == ([], "") and R.parse_paths({"direct": "x", "cert": 5}) == ([], ""))

# ------------------------------------------------------------------ 7. tải ffmpeg có kiểm mã
print("7. Tải ffmpeg + kiểm mã")
tmp = tempfile.mkdtemp(prefix="cbrem-")
exe_data = b"MZ" + os.urandom(5000)
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w") as z:
    z.writestr("ffmpeg-x/bin/ffmpeg.exe", exe_data); z.writestr("ffmpeg-x/README.txt", "x")
zdata = zbuf.getvalue(); zsha, esha = hashlib.sha256(zdata).hexdigest(), hashlib.sha256(exe_data).hexdigest()
logs = []; calls = []


def fetch_ok(url, dst):
    calls.append(url); open(dst, "wb").write(zdata)


def fetch_bad(url, dst):
    calls.append(url); open(dst, "wb").write(zdata + b"x")


kw = dict(base=tmp, log=logs.append, zip_sha=zsha, exe_sha=esha, zip_size=len(zdata))
ck("file tải về SAI mã kiểm → không dùng, không để lại file", R.ensure_ffmpeg(fetch=fetch_bad, **kw) is None and not os.path.exists(os.path.join(tmp, "bin", "ffmpeg.exe"))
   and not os.path.exists(os.path.join(tmp, "bin", "ffmpeg.zip.tmp")) and any("SAI ma kiem" in x for x in logs), logs)
ck("file zip đúng nhưng ffmpeg.exe bên trong sai mã → không dùng", R.ensure_ffmpeg(fetch=fetch_ok, **dict(kw, exe_sha="0" * 64)) is None and not os.path.exists(os.path.join(tmp, "bin", "ffmpeg.exe")))
p1 = R.ensure_ffmpeg(fetch=fetch_ok, **kw)
ck("đúng cả 2 mã → ghi bin\\ffmpeg.exe", p1 == os.path.join(tmp, "bin", "ffmpeg.exe") and open(p1, "rb").read() == exe_data and calls[-1] == R.FF_URL, p1)
n = len(calls)
ck("lần sau: dùng lại, không tải nữa", R.ensure_ffmpeg(fetch=fetch_ok, **kw) == p1 and len(calls) == n)
open(p1, "ab").write(b"virus")
ck("ffmpeg.exe bị sửa (khác cỡ) → phát hiện, tải lại bản đúng", R.ensure_ffmpeg(fetch=fetch_ok, **kw) == p1 and len(calls) == n + 1 and open(p1, "rb").read() == exe_data)
os.remove(os.path.join(tmp, "bin", "ffmpeg.ok"))
ck("mất dấu đã-kiểm → tự kiểm lại mã (không tải)", R.ensure_ffmpeg(fetch=fetch_ok, **kw) == p1 and len(calls) == n + 1 and os.path.isfile(os.path.join(tmp, "bin", "ffmpeg.ok")))


def fetch_fail(url, dst): raise OSError("mat mang")


shutil.rmtree(os.path.join(tmp, "bin"))
ck("không tải được (mất mạng) → None, lần sau thử lại", R.ensure_ffmpeg(fetch=fetch_fail, **kw) is None)
ck("mã đã ghim trong chương trình: đúng dạng sha256, đúng địa chỉ GitHub của bản 6.1.1", len(R.FF_ZIP_SHA) == 64 and len(R.FF_EXE_SHA) == 64 and R.FF_ZIP_SHA != R.FF_EXE_SHA
   and R.FF_URL == "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip" and R.FF_ZIP_SIZE == 87520045)
shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------------------------ 8. vòng hỏi web
print("8. Hỏi web nối máy chủ nào")
ident = {"id": "11111111-1111-4111-8111-111111111111", "token": "tok-1"}
ans = {}
rm = R.Remote(lambda: ans.get("ident"), lambda fn, body: (ans.setdefault("calls", []).append((fn, body)), ans.get("r"))[1], R.NullIO(), lambda: None)
ck("máy chưa đăng ký → chưa nối, nghỉ 60 giây, không gọi web", rm.where() == (None, 60) and "calls" not in ans)
ans["ident"] = ident
ck("không gọi được web → nghỉ 60 giây", rm.where() == (None, 60) and ans["calls"][-1] == ("pc_relay_where", {"p_id": ident["id"], "p_token": "tok-1"}))
ans["r"] = {"ok": False, "err": "BAD_TOKEN"}; ck("mã máy hết dùng → nghỉ 10 phút (agent tự đăng ký lại)", rm.where() == (None, 600))
ans["r"] = {"ok": False, "err": "SLOW_DOWN"}; ck("web bảo hỏi chậm lại → nghỉ 5 phút", rm.where() == (None, 300))
ans["r"] = {"ok": True, "on": False}; ck("admin chưa bật / máy chưa duyệt → không nối, 5 phút hỏi lại", rm.where() == (None, 300) and "TAT" in rm.state)
ans["r"] = {"ok": True, "on": True, "node": None}; ck("chưa có máy chủ nào nhận → 90 giây hỏi lại", rm.where() == (None, 90))
ans["r"] = {"ok": True, "on": True, "node": "win4", "stream": {"direct": [], "cert": "", "ws": None}}
ck("có máy chủ → trả đường nối, nhớ tên máy chủ", rm.where() == ({"direct": [], "cert": "", "ws": None}, 0) and rm.node == "win4")

# ------------------------------------------------------------------ 9. nối máy chủ phát hình giả (TLS thật) + 1 phiên xem
# ------------------------------------------------------------------ 8b. 26.11a — máy chỉ nén bằng CPU (VPS NVMe): phần thuần
print("8b. 26.11a · máy chỉ nén bằng CPU: kiểu nén theo số nhân, gộp lệnh rê chuột, bitrate không bị bóp oan, 1920×1080 lần đầu")
ck("kiểu nén theo số nhân: 1 nhân → ultrafast 15 khung · 2 nhân → ultrafast 20 khung · 4 nhân → 24 khung · 8 nhân → superfast 30 khung; số lạ không làm lỗi",
   R.cpu_tune(1) == ("ultrafast", "partitions=i4x4", 15) and R.cpu_tune(2)[2] == 20 and R.cpu_tune(4)[2] == 24 and R.cpu_tune(8) == ("superfast", "", 30)
   and R.cpu_tune(None)[2] == 15 and R.cpu_tune("x")[2] == 15, [R.cpu_tune(n) for n in (1, 2, 4, 8)])
ck("máy nén bằng CPU kiểu mới: Tự động giữ NGUYÊN cỡ màn hình 1920×1080 (không thu về 1600), khung/giây theo số nhân; khách tự chọn 60 khung thì tối đa 30",
   R.plan("auto", 0, 0, 0, 0, 1920, 1080, cpu=True, cpu_fps=20, cpu_side=1920, fps_max=30)[:3] == (1920, 1080, 20)
   and R.plan("auto", 0, 0, 0, 0, 1920, 1080, cpu=True, fps_fix=60, cpu_fps=20, cpu_side=1920, fps_max=30)[2] == 30
   and R.plan("auto", 0, 0, 0, 0, 1920, 1080, cpu=True)[:3] == (1600, 900, 30), R.plan("auto", 0, 0, 0, 0, 1920, 1080, cpu=True, cpu_fps=20, cpu_side=1920, fps_max=30))
a = R.enc_args("x264", 20, 4500, x264_preset="ultrafast", x264_extra="partitions=i4x4", crf=22, key_s=8)
ck("x264 kiểu mới: nén theo CHẤT LƯỢNG (crf 22, không -b:v), bitrate chỉ là trần, 1 khung không quá ~150 KB (bufsize 1200k), khung khoá ép theo giây thật (8 giây), không khung khoá định kỳ theo số khung",
   "-crf" in a and a[a.index("-crf") + 1] == "22" and "-b:v" not in a and a[a.index("-maxrate") + 1] == "4500k" and a[a.index("-bufsize") + 1] == "1200k"
   and a[a.index("-force_key_frames") + 1] == "expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+8))" and "keyint=100000" in a[a.index("-x264-params") + 1]
   and "partitions=i4x4" in a[a.index("-x264-params") + 1] and a[a.index("-preset") + 1] == "ultrafast" and a[a.index("-threads") + 1] == "1", a)
ck("… bitrate bị hạ (mạng yếu) thì cỡ 1 khung cũng nhỏ theo; bộ nén cũ (không crf) + card nén GIỮ NGUYÊN tham số",
   R.enc_args("x264", 20, 600, crf=22)[-1] == "180k" and "-b:v" in R.enc_args("x264", 30, 4000) and "keyint=30" in " ".join(R.enc_args("x264", 30, 4000))
   and "-crf" not in R.enc_args("nvenc", 60, 9000, crf=22), (R.enc_args("x264", 20, 600, crf=22)[-4:], R.enc_args("nvenc", 60, 9000, crf=22)[:6]))
c = R.ff_cmd("ffmpeg", "pipe", "x264", 1920, 1080, 1920, 1080, 20, 4500, 5004, {"x264_preset": "ultrafast", "crf": 22, "key_s": 8})
ck("lệnh ffmpeg cách quay 'pipe': nhận khung BGR0 qua ống (không gdigrab / ddagrab), đồng hồ thật + passthrough (không tự nhân đôi khung), KHÔNG -fflags nobuffer (nuốt khung đầu), cùng cỡ thì không thu phóng",
   c[c.index("-i") + 1] == "pipe:0" and c[c.index("-pix_fmt") + 1] == "bgr0" and c[c.index("-video_size") + 1] == "1920x1080" and "gdigrab" not in c and "ddagrab" not in " ".join(c)
   and c[c.index("-use_wallclock_as_timestamps") + 1] == "1" and c[c.index("-fps_mode") + 1] == "passthrough" and "nobuffer" not in " ".join(c)
   and c[c.index("-vf") + 1] == "format=yuv420p" and c[-1] == "rtp://127.0.0.1:5004?pkt_size=1300", c)
c = R.ff_cmd("ffmpeg", "pipe", "x264", 1920, 1080, 852, 480, 8, 350, 5004, {"crf": 22, "key_s": 2})
ck("… khác cỡ (ô xem trước 480) → thu nhỏ kiểu nhanh (fast_bilinear); ô xem trước: khung khoá 2 giây / lần", c[c.index("-vf") + 1] == "scale=852:480:flags=fast_bilinear,format=yuv420p"
   and "prev_forced_t+2)" in c[c.index("-force_key_frames") + 1], c)
mk = R.move_key
ck("lệnh CHỈ rê (chuột không đổi nút / ngón tay đang kéo) mới được gộp; bấm, nhả, chạm xuống, phím thì không", mk(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 5, 6)) == ("m",)
   and mk(R.C_MOUSE, struct.pack(">BBHH", 1, 0, 5, 6)) is None and mk(R.C_MOUSE, struct.pack(">BBHH", 2, 0, 5, 6)) is None and mk(R.C_TOUCH, struct.pack(">BBHH", 2, 1, 5, 6)) == ("t", 1)
   and mk(R.C_TOUCH, struct.pack(">BBHH", 0, 1, 5, 6)) is None and mk(R.C_KEY, struct.pack(">BII", 0, 29, 0)) is None and mk(R.C_MOUSE, b"\x00") is None)


class _R0: pass


class _C0:
    def __init__(self): self.out = []
    def send(self, t, p=b""): self.out.append((t, p))


def _sess(io=None):
    r = _R0(); r.log = lambda m: None; r.io = io or R.NullIO(); r.caps = {"enc": ["x264"], "cap": "test"}; r.bad = {}; r.ff = None; r.ncpu = 2
    return R.Session(r, _C0(), {"sid": 1})


s_ = _sess()
for i in range(60): s_.iq.put((R.C_MOUSE, struct.pack(">BBHH", 0, 0, 100 + i, 200 + i)))        # máy bận: 60 lệnh rê dồn lại
s_.iq.put((R.C_MOUSE, struct.pack(">BBHH", 1, 0, 500, 600)))                                     # rồi bấm
for i in range(5): s_.iq.put((R.C_MOUSE, struct.pack(">BBHH", 0, 0, 700 + i, 800 + i)))          # giữ nút, kéo
s_.iq.put((R.C_MOUSE, struct.pack(">BBHH", 2, 0, 710, 810)))                                     # nhả
s_.iq.put((R.C_KEY, struct.pack(">BII", 0, 29, 0))); s_.iq.put((R.C_KEY, struct.pack(">BII", 1, 29, 0)))
for i in range(8): s_.iq.put((R.C_MOUSE, struct.pack(">BBHH", 0, 0, 900 + i, 900 + i)))
th_ = threading.Thread(target=s_._input, daemon=True); th_.start()
wait(lambda: s_.iq.empty() and len(s_.io.ev) >= 9, 3); time.sleep(0.15); s_.closed = True; th_.join(1)
ck("80 lệnh chuột dồn lại → rê thẳng tới điểm MỚI NHẤT của từng đoạn (không chiếu lại đường đi cũ), bấm / kéo / nhả / phím vẫn đủ và đúng thứ tự",
   s_.io.ev == [("move", 159, 259), ("move", 500, 600), ("btn", 0, True), ("move", 704, 804), ("move", 710, 810), ("btn", 0, False),
                ("key", 0x41, True, False), ("key", 0x41, False, False), ("move", 907, 907)] and s_.skip == 59 + 4 + 7, (s_.io.ev, s_.skip))
s_ = _sess()
for i in range(10): s_.iq.put((R.C_TOUCH, struct.pack(">BBHH", 2, 0, 100 + i, 100))); s_.iq.put((R.C_TOUCH, struct.pack(">BBHH", 2, 1, 300 + i, 300)))
got_ = []; s_._apply = lambda t, p: got_.append(struct.unpack(">BBHH", p[:6]))
th_ = threading.Thread(target=s_._input, daemon=True); th_.start(); wait(lambda: s_.iq.empty(), 2); time.sleep(0.1); s_.closed = True; th_.join(1)
ck("2 ngón tay kéo xen kẽ (cuộn): KHÔNG gộp lệnh của ngón này vào ngón kia — đủ 20 lệnh, đúng thứ tự", len(got_) == 20 and got_[0] == (2, 0, 100, 100) and got_[-1] == (2, 1, 309, 300), got_[:4])

r_ = R.Rate(4500, 4500); t_ = 1000.0
for i in range(30): r_.sent(i, 1250, t_ + i * 0.1); r_.ack(i, t_ + i * 0.1 + 0.02)              # màn hình ít đổi: chỉ ~100 kbps, người xem nhận đủ
t_ += 3.0
x_ = [r_.congested(t_), r_.congested(t_ + 0.5), r_.congested(t_ + 1.0)]
ck("nén theo chất lượng: đang phát ~100 kbps (màn hình ít đổi) mà nghẽn 3 lần → hạ trần ×0,7 (3150), KHÔNG bóp xuống theo 100 kbps đang nhận",
   x_[:2] == [None, None] and x_[2] == 3150 and r_.cur == 3150 and 50 < r_.outrate(1002.9) < 200, (x_, r_.outrate(1002.9)))
r_ = R.Rate(4500, 4500); t_ = 2000.0
for i in range(30):
    r_.sent(i, 56250, t_ + i * 0.1)                                                               # đang phát đúng trần 4500 kbps
    if i % 2 == 0: r_.ack(i, t_ + i * 0.1 + 0.02)
r_.delivered.clear(); r_.delivered.extend((t_ + 1.0 + k * 0.1, 25000) for k in range(20))         # người xem thật sự chỉ nhận ~2000 kbps
t_ += 3.0; r_.ack_t = t_
x_ = [r_.congested(t_), r_.congested(t_ + 0.5), r_.congested(t_ + 1.0)]
ck("… còn đang phát sát trần mà người xem nhận chậm → vẫn hạ theo tốc độ nhận thật như trước (≤ 0,8 × tốc độ nhận)", x_[2] is not None and x_[2] < 2000, (x_, r_.goodput(t_ + 1.0)))


class _M0:
    def __init__(self, cur, ok): self.cur, self.ok, self.done = cur, set(ok), []
    def modes(self): return self.cur, self.ok
    def set_mode(self, w, h): self.done.append((w, h)); self.cur = (w, h); return True


d_ = tempfile.mkdtemp(prefix="cbmode-"); lg_ = []
m_ = _M0((1024, 768), [(800, 600), (1024, 768), (1920, 1080)])
ck("máy ảo mới giao đang 1024×768 → đặt 1920×1080", R.vm_default_mode(m_, "pc-1", d_, lg_.append, qemu=True) == "set" and m_.done == [(1920, 1080)], (m_.done, lg_))
m_.cur = (1280, 720)
ck("… đúng 1 LẦN cho mỗi mã máy: khách tự đổi cỡ khác rồi thì lần chạy sau giữ theo khách", R.vm_default_mode(m_, "pc-1", d_, qemu=True) == "da dat truoc" and m_.done == [(1920, 1080)], m_.done)
m_ = _M0((1024, 768), [(1024, 768), (1920, 1080)])
ck("máy ảo khác nhân ra từ cùng máy mẫu (mã máy khác, thư mục có sẵn dấu của máy mẫu) → vẫn được đặt", R.vm_default_mode(m_, "pc-2", d_, qemu=True) == "set" and m_.done == [(1920, 1080)], m_.done)
m_ = _M0((1024, 768), [(1024, 768), (1920, 1080)]); d2_ = tempfile.mkdtemp(prefix="cbmode-")
ck("máy PC THẬT (không phải máy ảo) → không đụng cỡ màn hình, không ghi dấu", R.vm_default_mode(m_, "pc-3", d2_, qemu=False) == "khong phai may ao" and m_.done == []
   and not os.path.exists(os.path.join(d2_, "logs", "mode.done")), m_.done)
m_ = _M0((1600, 900), [(1600, 900), (1920, 1080)])
ck("máy ảo đang ở cỡ ≥ 1280 (đã có người chỉnh) → giữ nguyên; máy không có cỡ 1920×1080 → báo, không lỗi; chưa có mã máy → chờ",
   R.vm_default_mode(m_, "pc-4", d2_, qemu=True) == "giu nguyen" and m_.done == [] and R.vm_default_mode(_M0((1024, 768), [(1024, 768)]), "pc-5", d2_, qemu=True) == "khong co co nay"
   and R.vm_default_mode(m_, None, d2_, qemu=True) == "chua co ma may", m_.done)
shutil.rmtree(d_, ignore_errors=True); shutil.rmtree(d2_, ignore_errors=True)
g_ = R.FakeGrab(R.NullIO(64, 32)); b1_, c1_ = g_.grab(); b2_, c2_ = g_.grab(); g_.io.tick = 3; b3_, c3_ = g_.grab()
ck("bộ chụp giả của bộ thử: khung đầu 'đổi', chụp lại không đổi, đổi io.tick → đổi; đúng cỡ BGR0", c1_ and not c2_ and c3_ and len(b1_) == 64 * 32 * 4 and b1_ is b2_ and b3_ != b1_)

# ------------------------------------------------------------------ 9. nối máy chủ + phiên (cần ffmpeg + cryptography)
print("9. Nối máy chủ (TLS, kiểm mã chứng chỉ) + phiên có người xem")
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    HAVE_TLS = True
except ImportError:
    HAVE_TLS = False
if not (HAVE_TLS and FF):
    print("  (bỏ qua: máy thử thiếu %s)" % ("thư viện cryptography" if not HAVE_TLS else "ffmpeg"))
else:
    tmp = tempfile.mkdtemp(prefix="cbrem-")
    key = ec.generate_private_key(ec.SECP256R1()); nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bluestream test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    crt = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(key.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    open(os.path.join(tmp, "k.pem"), "wb").write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    open(os.path.join(tmp, "c.pem"), "wb").write(crt.public_bytes(serialization.Encoding.PEM))
    fp = hashlib.sha256(crt.public_bytes(serialization.Encoding.DER)).hexdigest()
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); sctx.load_cert_chain(os.path.join(tmp, "c.pem"), os.path.join(tmp, "k.pem"))
    lsock = socket.socket(); lsock.bind(("127.0.0.1", 0)); lsock.listen(8); port = lsock.getsockname()[1]

    class Peer:
        """1 kết nối phía máy chủ giả."""
        def __init__(self, s): self.s = s; self.rx = []; self.lock = threading.Lock(); self.alive = True; threading.Thread(target=self._loop, daemon=True).start()

        def _rd(self, n):
            b = b""
            while len(b) < n:
                x = self.s.recv(n - len(b))
                if not x: raise EOFError()
                b += x
            return b

        def _loop(self):
            try:
                while True:
                    n = struct.unpack(">I", self._rd(4))[0]; b = self._rd(n)
                    if b[0] == R.C_PING: self.send(R.S_PONG, b[1:9]); continue
                    with self.lock: self.rx.append((b[0], b[1:]))
            except Exception:
                self.alive = False

        def send(self, t, payload=b""):
            if isinstance(payload, dict): payload = json.dumps(payload).encode()
            self.s.sendall(struct.pack(">IB", 1 + len(payload), t) + payload)

        def take(self, t, timeout=8.0):
            """Gói đầu tiên loại t (lấy ra khỏi hàng) hoặc None."""
            def f():
                with self.lock:
                    for i, m in enumerate(self.rx):
                        if m[0] == t: return self.rx.pop(i)
                return None
            return wait(f, timeout)

        def count(self, t):
            with self.lock: return sum(1 for m in self.rx if m[0] == t)

    peers = []

    def acceptor():
        while True:
            try: c, _ = lsock.accept()
            except OSError: return
            try: peers.append(Peer(sctx.wrap_socket(c, server_side=True)))
            except Exception: pass
    threading.Thread(target=acceptor, daemon=True).start()
    stream = {"direct": [{"host": "127.0.0.1", "port": port, "lan": True}], "cert": fp, "ws": None}

    try:
        R.DirectConn("127.0.0.1", port, "00" * 32, 2.0); bad = False
    except ssl.SSLError: bad = True
    except Exception as e: bad = repr(e)
    ck("mã chứng chỉ máy chủ KHÔNG khớp mã web báo → không nối (chống máy chủ giả)", bad is True, bad)

    logs = []; naps = []
    state = {"r": {"ok": True, "on": True, "node": "wintest", "stream": stream}}
    io_ = R.NullIO(1920, 1080)
    imew = {"cb": None, "stopped": 0}                               # 22.11b: theo dõi ô nhập chữ giả (máy thật dùng ImeWatch)

    class FakeIme:
        def stop(self): imew["stopped"] += 1

    def fake_ime_watch(cb, log=None):
        imew["cb"] = cb; return FakeIme()
    io_.ime_watch = fake_ime_watch
    rm = R.Remote(lambda: ident, lambda fn, body: state["r"], io_, lambda: FF, logs.append, None, caps={"enc": ["x264"], "cap": "test"})

    def fake_sleep(s):
        naps.append(s)
        time.sleep(0.05)
    rm.sleep = fake_sleep
    th = threading.Thread(target=rm.run, daemon=True); th.start()
    pr = wait(lambda: next((p for p in peers if p.count(R.P_HELLO)), None), 6)
    hello = json.loads(pr.take(R.P_HELLO)[1]) if pr else {}
    ck("máy tự nối tới máy chủ, gửi gói chào: mã máy + mã riêng + bản + cỡ màn hình + bộ nén", hello == {"v": 1, "pc": ident["id"], "token": "tok-1", "ver": R.REMOTE_VER, "w": 1920, "h": 1080, "enc": "x264", "cap": "test"}, hello)
    pr.send(R.R_OK, {"ok": True, "name": "Máy thử", "node": "wintest", "ping_s": 2})
    ck("được nhận → trạng thái 'đã nối, chờ người xem'; chưa có người xem thì KHÔNG chạy ffmpeg", wait(lambda: "cho nguoi xem" in rm.state, 3) and rm.sess is None, rm.state)

    pr.send(R.R_START, {"sid": 7, "q": "eco", "fps": 30, "maxh": 0, "kbps": 0, "net": "w", "dl": 0, "client": "web", "link": "direct", "admin": True, "owner": False})
    m = pr.take(R.P_INFO)
    info = json.loads(m[1]) if m else {}
    ck("có người xem → bật bộ quay, báo P_INFO đúng số phiên + cỡ hình theo chất lượng", info == {"sid": 7, "w": 1280, "h": 720, "fps": 30, "kbps": 2000, "enc": "x264", "cap": "test", "q": "eco"}, info)
    ck("admin (không phải khách của máy) vào xem → hiện hộp báo cho người ngồi máy; giữ máy không ngủ", ("notify", "CloudBlue: quan tri vien dang ho tro / dieu khien may nay tu xa.") in io_.ev and ("awake", True) in io_.ev, io_.ev)
    v1 = pr.take(R.S_VIDEO, 12)
    ck("khung hình đầu là khung khoá có SPS/PPS, dữ liệu H.264 Annex-B", v1 is not None and v1[1][0] & 3 == 3 and v1[1][9:13] == b"\x00\x00\x00\x01", v1 and v1[1][:16])
    ck("hình chảy đều (≥ 40 khung trong vài giây)", wait(lambda: pr.count(R.S_VIDEO) >= 40, 10), pr.count(R.S_VIDEO))
    with pr.lock: vids = [v1[1]] + [m[1] for m in pr.rx if m[0] == R.S_VIDEO]
    h264 = os.path.join(tmp, "a.h264"); open(h264, "wb").write(b"".join(v[9:] for v in vids))
    rr = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,nb_read_frames,profile",
                         "-of", "json", h264], capture_output=True, timeout=60)
    try: sj = json.loads(rr.stdout)["streams"][0]
    except Exception: sj = {"err": rr.stderr[-300:]}
    ck("ffprobe giải mã được đúng số khung, đúng cỡ 1280x720, H.264 Baseline", sj.get("codec_name") == "h264" and sj.get("width") == 1280 and sj.get("height") == 720
       and int(sj.get("nb_read_frames") or 0) == len(vids) and "Baseline" in str(sj.get("profile")), (sj, len(vids)))
    pts = [struct.unpack(">Q", v[1:9])[0] for v in vids]
    ck("mốc thời gian mỗi khung tăng dần (app dùng để báo đã nhận)", all(b > a for a, b in zip(pts, pts[1:])))
    st = pr.take(R.S_STATS, 5)
    sj = json.loads(st[1]) if st else {}
    ck("gửi số liệu mỗi 2 giây (khung/giây, kbps, bộ nén, cỡ hình)", sj.get("enc") == "x264" and sj.get("w") == 1280 and sj.get("fps", 0) > 5 and sj.get("kbps", 0) > 0 and sj.get("q") == "eco", sj)
    ck("22.11b: phiên bật theo dõi ô nhập chữ; chưa biết thì số liệu KHÔNG có ô 'ime'", imew["cb"] is not None and "ime" not in sj, (imew, sj))

    def stats_after(fn, timeout=1.2):
        with pr.lock: pr.rx[:] = [m for m in pr.rx if m[0] != R.S_STATS]
        t0 = time.time(); fn(); m = pr.take(R.S_STATS, timeout)
        return (json.loads(m[1]) if m else {}), time.time() - t0
    j1, dt1 = stats_after(lambda: imew["cb"]((1, 0)))
    ck("22.11b: khách bấm vào ô nhập chữ → báo NGAY (dưới 1 giây, không chờ nhịp 2 giây) ime = 1, kèm số liệu cũ", j1.get("ime") == 1 and "pw" not in j1 and j1.get("enc") == "x264" and dt1 < 1.0, (j1, dt1))
    j2, _ = stats_after(lambda: imew["cb"]((1, 1)))
    ck("22.11b: ô mật khẩu → pw = 1", j2.get("ime") == 1 and j2.get("pw") == 1, j2)
    j3, _ = stats_after(lambda: imew["cb"]((0, 0)))
    ck("22.11b: rời ô nhập chữ → ime = 0", j3.get("ime") == 0 and "pw" not in j3, j3)
    j4, _ = stats_after(lambda: None, 3.0)
    ck("22.11b: số liệu định kỳ sau đó vẫn mang trạng thái ô nhập chữ", j4.get("ime") == 0 and j4.get("fps", 0) > 0, j4)

    io_.ev.clear()
    pr.send(R.C_MOUSE, struct.pack(">BBHH", 1, 0, 1000, 2000)); pr.send(R.C_MOUSE, struct.pack(">BBHH", 2, 0, 1000, 2000))
    pr.send(R.C_KEY, struct.pack(">BII", 0, 59, 0)); pr.send(R.C_KEY, struct.pack(">BII", 0, 29, 1))
    pr.send(R.C_TEXT, "xin chào\x07".encode()); pr.send(R.C_SCROLL, struct.pack(">HHhh", 5, 6, 0, -120))
    pr.send(R.C_CMD, b'{"cmd":"home"}'); pr.send(R.C_CMD, b'{"cmd":"power"}'); pr.send(R.C_CMD, b"khong phai json"); pr.send(R.C_CLIP, b"\x01dan vao")
    pr.send(R.C_TOUCH, struct.pack(">BBHH", 0, 0, 40000, 40000))
    want = [("move", 1000, 2000), ("btn", 0, True), ("move", 1000, 2000), ("btn", 0, False), ("key", 0xA0, True, False), ("key", 0x41, True, False), ("text", "xin chào"),
            ("move", 5, 6), ("wheel", -120, False), ("key", 0x5B, True, True), ("key", 0x44, True, False), ("key", 0x44, False, False), ("key", 0x5B, False, True),
            ("clip", "dan vao"), ("key", 0xA0, False, False), ("key", 0xA2, True, False), ("key", 0x56, True, False), ("key", 0x56, False, False),
            ("key", 0xA2, False, False), ("key", 0xA0, True, False), ("move", 40000, 40000)]
    ck("chuột / phím / chữ / cuộn / lệnh / dán của người xem được làm đúng thứ tự (dán lúc khách giữ Shift: nhả Shift → Ctrl+V → nhấn lại Shift); "
       "lệnh lạ + gói hỏng bị bỏ", wait(lambda: io_.ev == want, 4), io_.ev)
    ck("giữ yên 0,55 giây sau khi chạm → bấm phải (đồng hồ của luồng nhập liệu)", wait(lambda: io_.ev[-2:] == [("btn", 1, True), ("btn", 1, False)], 3), io_.ev[-3:])

    pr.send(R.C_QUALITY, b'{"q":"bal","fps":20}')
    m = pr.take(R.P_INFO, 8); info = json.loads(m[1]) if m else {}
    ck("người xem đổi chất lượng → bật lại bộ nén, báo P_INFO mới (cỡ hình + khung/giây mới, cùng số phiên)", info.get("sid") == 7 and (info.get("w"), info.get("h"), info.get("fps"), info.get("q")) == (1920, 1080, 20, "bal"), info)
    with pr.lock: pr.rx[:] = [m for m in pr.rx if m[0] != R.S_VIDEO]
    v = pr.take(R.S_VIDEO, 10)
    ck("sau khi bật lại: khung đầu lại là khung khoá", v is not None and v[1][0] & 1 == 1, v and v[1][:10])
    for i in range(3):
        pr.send(R.R_SLOW, b'{"buf": 300, "n": %d}' % (i + 1)); time.sleep(0.1)
    m = pr.take(R.P_INFO, 8); info = json.loads(m[1]) if m else {}
    ck("máy chủ báo khách nhận chậm nhiều lần → máy tự hạ bitrate (P_INFO mới, kbps thấp hơn)", info.get("sid") == 7 and 0 < info.get("kbps", 0) < 4500, info)
    io_.w, io_.h = 1280, 1024
    m = pr.take(R.P_INFO, 8); info = json.loads(m[1]) if m else {}
    ck("màn hình máy đổi độ phân giải → phát lại đúng cỡ mới", info.get("h") is not None and (info["w"] / info["h"]) == 1.25, info)
    pr.send(R.C_QUALITY, b'{"q":"uhd","fps":0,"fpsx":45,"maxh":960}')
    info, end = {}, time.time() + 8
    while time.time() < end and info.get("q") != "uhd":
        m = pr.take(R.P_INFO, max(0.2, end - time.time())); info = json.loads(m[1]) if m else info
        if not m: break
    ck("21.11g khách chọn Siêu nét + 45 khung (fpsx) + cạnh tối đa 960 → bật lại đúng (uhd, 45 khung, cạnh dài 960)",
       (info.get("q"), info.get("fps"), max(info.get("w") or 0, info.get("h") or 0)) == ("uhd", 45, 960), info)

    io_.ev.clear(); sess = rm.sess; enc = sess.enc
    pr.send(R.C_KEY, struct.pack(">BII", 0, 62, 0)); pr.send(R.C_MOUSE, struct.pack(">BBHH", 1, 2, 9, 9)); time.sleep(0.4)
    pr.send(R.R_STOP)
    ck("hết người xem (R_STOP) → tắt ffmpeg, phiên đóng", wait(lambda: rm.sess is None and enc.exited(), 5), (rm.sess, enc.proc.poll()))
    ck("22.11b: phiên đóng → tắt luôn theo dõi ô nhập chữ", imew["stopped"] >= 1, imew)
    ck("… NHẢ phím / nút chuột đang giữ, cho máy ngủ lại bình thường", ("key", 0x20, False, False) in io_.ev and ("btn", 2, False) in io_.ev and io_.ev[-1] == ("awake", False), io_.ev[-6:])
    n0 = pr.count(R.S_VIDEO); time.sleep(1.2)
    ck("… không còn gửi hình", pr.count(R.S_VIDEO) == n0)
    pr.send(R.R_START, {"sid": 8, "q": "auto", "link": "ws", "net": "c", "admin": False, "owner": True})
    m = pr.take(R.P_INFO, 8); info = json.loads(m[1]) if m else {}
    ck("phiên mới: người xem dùng 4G đi đường vòng → bắt đầu nhẹ 1500 kbps (cạnh dài 1280), khách của máy vào thì không hiện hộp báo",
       info.get("sid") == 8 and info.get("kbps") == 1500 and max(info.get("w", 0), info.get("h", 0)) == 1280 and not any(e[0] == "notify" for e in io_.ev), (info, io_.ev))
    sess = rm.sess; enc = sess.enc
    pr.s.close()
    ck("đứt kết nối giữa phiên → tắt ffmpeg, rồi tự nối lại máy chủ", wait(lambda: enc.exited() and any(p is not pr and p.count(R.P_HELLO) for p in peers), 8), [p.count(R.P_HELLO) for p in peers])
    pr2 = next(p for p in peers if p is not pr and p.count(R.P_HELLO))
    pr2.send(R.S_ERROR, {"code": "OFF", "msg": "tat"})
    ck("máy chủ từ chối OFF (chưa bật điều khiển từ xa) → nghỉ ~5 phút mới thử lại", wait(lambda: any(240 <= x <= 360 for x in naps), 4), naps)
    pr3 = wait(lambda: next((p for p in peers if p not in (pr, pr2) and p.count(R.P_HELLO)), None), 4)
    pr3.send(R.S_ERROR, {"code": "AUTH", "msg": "sai ma"})
    ck("máy chủ từ chối AUTH (sai mã máy) → nghỉ ~10 phút (không dò lại liên tục làm cả phòng bị chặn)", wait(lambda: any(480 <= x <= 720 for x in naps), 4), naps)
    pr4 = wait(lambda: next((p for p in peers if p not in (pr, pr2, pr3) and p.count(R.P_HELLO)), None), 4)
    pr4.take(R.P_HELLO); pr4.send(R.R_OK, {"ok": True, "ping_s": 2})
    rm.ff = None; rm.caps = {}; rm.ff_fn = lambda: None
    pr4.send(R.R_START, {"sid": 9, "q": "auto"})
    m = pr4.take(R.S_ERROR, 5)
    ck("chưa có ffmpeg (đang tải lần đầu) → báo người xem 'đang chuẩn bị', không treo", m is not None and "chuẩn bị" in json.loads(m[1])["msg"] and rm.sess is None, m)
    rm.WHERE_S = 0.5; rm.t_where = 0; state["r"] = {"ok": True, "on": False}
    ck("đang rảnh, hỏi lại web thấy admin TẮT điều khiển từ xa → tự ngắt kết nối", wait(lambda: not pr4.alive, 6), rm.state)
    rm.stop = True

    print("10. 26.11a · máy CHỈ nén bằng CPU: tự chụp màn hình, chỉ nén khung ĐỔI (ffmpeg thật nhận khung qua ống)")
    io3 = R.NullIO(640, 360); io3.tick = 0; au = []
    e3 = R.Encoder(FF, "pipe", "x264", 640, 360, 640, 360, 20, 2000, lambda d, k, c, pts: au.append((time.time(), len(d) if d else -1, bool(k))), grab_fn=io3.grabber,
                   tune={"x264_preset": "ultrafast", "x264_extra": "partitions=i4x4", "crf": 22, "key_s": 2})
    e3.start()
    ck("bộ nén kiểu 'pipe' chạy: khung đầu là khung khoá", wait(lambda: au and au[0][2], 8), au[:2])
    time.sleep(1.0); n0 = len(au); g0 = e3.grabs; time.sleep(3.0)
    idle = au[n0:]; gr = e3.grabs - g0
    ck("màn hình ĐỨNG YÊN 3 giây: chỉ ~1 khung / giây giữ nhịp + vài khung quanh khung khoá định kỳ (2–8 khung, không phải 60) và chỉ xem lại màn hình ~3 lần / giây (7–12 lần, không phải 60)",
       2 <= len(idle) <= 8 and 7 <= gr <= 12, (len(idle), gr))
    ck("… khung giữ nhịp chỉ vài chục byte (trừ khung khoá định kỳ 2 giây / lần của ô xem trước) — đứng yên gần như không tốn mạng",
       all(x[1] < 300 for x in idle if not x[2]) and any(x[2] for x in au[1:]), [(x[1], x[2]) for x in idle])
    time.sleep(0.4); n0 = len(au); io3.tick = 1; t0 = time.time()
    ck("màn hình tự đổi (không ai thao tác) → khung mới tới trong ≤ 0,6 giây", wait(lambda: len(au) > n0, 1.0, 0.005) and au[n0][0] - t0 <= 0.6, (len(au) - n0, au[n0][0] - t0 if len(au) > n0 else None))
    time.sleep(1.3); burst = au[n0:]
    ck("… khung đổi NHỎ sau lúc yên (con trỏ chữ nháy, đồng hồ) đã nét sẵn → KHÔNG gửi lại khung nào cho bộ nén (bản đầu gửi mù 6 khung sau mỗi lần đổi): 1–5 khung trong 1,3 giây",
       1 <= len(burst) <= 5 and burst[0][1] < R.PIPE_FINE, [x[1] for x in burst])
    time.sleep(0.5); n0 = len(au); f0 = e3.fed; g0 = e3.grabs; io3.noise = True; io3.tick = 1001
    wait(lambda: len(au) > n0, 1.0, 0.005); time.sleep(1.6); burst = au[n0:]; big = [x for x in burst if x[1] >= R.PIPE_SMALL]
    ck("… khung đổi NẶNG (cả màn hình, bộ nén bị ép cỡ) → gửi lại chính khung đó cho nét dần (không chụp thêm), mỗi lần chờ khung trước nén xong, tối đa %d lần rồi thôi: %d khung nặng"
       % (R.PIPE_SETTLE, len(big)), 4 <= len(big) <= R.PIPE_SETTLE + 3 and e3.fed - f0 <= R.PIPE_SETTLE + 5 and e3.grabs - g0 <= 9, ([x[1] for x in burst], e3.fed - f0, e3.grabs - g0))
    io3.noise = False; io3.tick = 1; time.sleep(0.8)
    lat = []
    for k in range(2, 8):
        time.sleep(0.45); n0 = len(au); e3.kick(); io3.tick = k; t0 = time.time()          # người xem vừa thao tác → màn hình đổi
        if wait(lambda: len(au) > n0, 1.0, 0.003): lat.append(au[n0][0] - t0)
    ck("người xem thao tác (kick) → chụp NGAY, khung mới tới sau ≤ 0,15 giây (6 lần thử, không lần nào phải chờ nhịp đứng yên 0,33 giây)", len(lat) == 6 and max(lat) <= 0.15, [round(x, 3) for x in lat])
    n0 = len(au); g0 = e3.grabs; t0 = time.time()
    while time.time() - t0 < 2.0: io3.tick += 1; e3.kick(); time.sleep(0.02)
    time.sleep(0.2); mov = len(au) - n0
    ck("màn hình đổi liên tục 2 giây: chạy đủ nhịp ~20 khung / giây (30–46 khung), không vượt nhịp đã chọn", 30 <= mov <= 46 and e3.grabs - g0 <= 46, (mov, e3.grabs - g0))
    io3.grab_fail = True; e3.kick()
    ck("bộ chụp lỗi giữa chừng → dừng ffmpeg + ghi lý do (luồng canh phiên sẽ đổi sang cách quay cũ)", wait(lambda: e3.exited() and "chup man hinh" in e3.err, 4), (e3.exited(), e3.err))
    e3.stop()

    time.sleep(0.3); known = list(peers)
    io2 = R.NullIO(1280, 720); io2.tick = 0; logs2 = []
    rm2 = R.Remote(lambda: ident, lambda fn, body: {"ok": True, "on": True, "node": "wintest", "stream": stream}, io2, lambda: FF, logs2.append, None, caps={"enc": ["x264"], "cap": "gdi"})
    rm2.sleep = lambda s: time.sleep(0.05); rm2.ncpu = 2
    threading.Thread(target=rm2.run, daemon=True).start()
    q = wait(lambda: next((p for p in peers if p not in known and p.count(R.P_HELLO)), None), 6)
    q.take(R.P_HELLO); q.send(R.R_OK, {"ok": True, "ping_s": 2}); wait(lambda: "cho nguoi xem" in rm2.state, 3)
    q.send(R.R_START, {"sid": 21, "q": "auto", "link": "direct", "net": "w", "admin": False, "owner": True})
    m = q.take(R.P_INFO, 8); info = json.loads(m[1]) if m else {}
    ck("phiên trên máy CHỈ có bộ nén CPU, 2 nhân: cách quay 'pipe', GIỮ nguyên cỡ màn hình 1280×720, 20 khung / giây, trần 4500 kbps",
       (info.get("cap"), info.get("w"), info.get("h"), info.get("fps"), info.get("kbps"), info.get("enc")) == ("pipe", 1280, 720, 20, 4500, "x264"), info)
    s2 = rm2.sess; e2 = s2.enc; cl = " ".join(e2.proc.args)
    ck("… ffmpeg nhận khung qua ống, nén theo chất lượng kiểu nhẹ nhất (ultrafast), khung khoá định kỳ 4 giây / lần (theo giây thật)", "pipe:0" in cl and "-crf 22" in cl and "ultrafast" in cl and "prev_forced_t+%d)" % R.PIPE_KEY_S in cl and s2.long_gop, cl[-400:])
    v1 = q.take(R.S_VIDEO, 10)
    ck("… khung đầu là khung khoá có SPS/PPS", v1 is not None and v1[1][0] & 3 == 3, v1 and v1[1][:10])
    time.sleep(2.2)                                                # qua đoạn mở đầu (1 giây chụp đủ nhịp + mấy khung làm nét)
    with q.lock: q.rx[:] = [m for m in q.rx if m[0] not in (R.S_VIDEO, R.S_STATS)]
    time.sleep(3.0); nv = q.count(R.S_VIDEO)
    wait(lambda: q.count(R.S_STATS) >= 2, 3)
    with q.lock: sts = [json.loads(m[1]) for m in q.rx if m[0] == R.S_STATS]
    sj = sts[-1] if sts else {}
    ck("đứng yên 3 giây: người xem chỉ nhận ~1–2 khung / giây (2–7 khung, không phải 60); số liệu ghi rõ kiểu tiết kiệm (eco = 1, số lần chụp ~3 / giây)", 2 <= nv <= 7 and sj.get("eco") == 1 and sj.get("cap") == "pipe"
       and 1 <= sj.get("grab", 0) <= 5, (nv, sj))
    with q.lock: q.rx[:] = [m for m in q.rx if m[0] != R.S_VIDEO]
    io2.ev.clear(); q.send(R.C_MOUSE, struct.pack(">BBHH", 0, 0, 3000, 4000)); io2.tick = 5; t0 = time.time()
    ck("người xem rê chuột → máy rê + chụp ngay: khung mới về tới người xem sau ≤ 0,25 giây", wait(lambda: q.count(R.S_VIDEO) >= 1, 1.0, 0.005) and time.time() - t0 <= 0.25 and ("move", 3000, 4000) in io2.ev,
       (time.time() - t0, io2.ev[:2]))
    k0 = s2.t_key; e_old = s2.enc
    s2.wait_key = True; s2.t_key = time.time() - 3                 # vừa phải bỏ khung (người xem chậm) → đang chờ khung khoá, mà khung khoá định kỳ còn xa
    ck("đang chờ khung khoá → tự bật lại bộ nén lấy khung khoá ngay (không chờ khung khoá định kỳ): có bộ nén mới + khung khoá mới trong ≤ 3 giây",
       wait(lambda: rm2.sess is s2 and s2.enc is not None and s2.enc is not e_old and not s2.wait_key and s2.t_key > time.time() - 2.5, 4), (s2.wait_key, s2.enc is e_old))
    q.send(R.R_SLOW, b'{"buf": 300, "n": 1}')
    ck("trạm báo người xem nhận chậm → 5 giây tới bảo đảm có khung khoá dày hơn (key_until)", wait(lambda: s2.key_until > time.time() + 3, 2), s2.key_until - time.time())
    q.send(R.R_START, {"sid": 22, "q": "eco", "fps": 8, "maxh": 480, "kbps": 350, "client": "preview", "link": "direct", "admin": False, "owner": True, "preview": True})
    info, end = {}, time.time() + 8
    while time.time() < end and info.get("sid") != 22:              # bỏ qua các P_INFO của phiên 21 (mỗi lần bật lại bộ nén báo 1 lần)
        m = q.take(R.P_INFO, 1.0); info = json.loads(m[1]) if m else info
    cl = " ".join(rm2.sess.enc.proc.args) if rm2.sess and rm2.sess.enc else ""
    ck("ô xem trước (luồng nhỏ của trạm): vẫn cách quay 'pipe', thu nhỏ 480, 8 khung / giây, khung khoá 2 giây / lần (ô mới mở có hình nhanh)",
       (info.get("sid"), info.get("cap"), max(info.get("w", 0), info.get("h", 0)), info.get("fps")) == (22, "pipe", 480, 8) and "prev_forced_t+2)" in cl and "fast_bilinear" in cl, (info, cl[-300:]))
    io2.grab_fail = True
    m = None; end = time.time() + 14
    while time.time() < end:
        m = q.take(R.P_INFO, 1.0)
        if m and json.loads(m[1]).get("cap") != "pipe": break
    info = json.loads(m[1]) if m else {}
    ck("máy không tự chụp được (bộ chụp lỗi) → tự về cách quay CŨ (ffmpeg tự quay), phiên không chết; 30 phút sau mới thử lại kiểu mới",
       info.get("cap") in ("gdi", "test") and rm2.bad.get("pipe", 0) > time.time() + 1000, (info, rm2.bad))
    q.send(R.R_STOP); wait(lambda: rm2.sess is None, 4)
    rm2.stop = True; q.s.close()
    lsock.close()
    ck("nhật ký không ghi mã riêng của máy", not any("tok-1" in x for x in logs), [x for x in logs if "tok-1" in x][:2])
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
