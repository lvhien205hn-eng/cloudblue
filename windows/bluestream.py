# -*- coding: utf-8 -*-
# =====================================================================================================
#  bluestream.py — PHÁT HÌNH v2 cho APP PC + APP ANDROID (web không phát hình nữa)
#
#  Đường hình:  cửa sổ giả lập trên Windows (quay bằng Windows Graphics Capture, chạy ngầm vẫn quay được)
#               → nén bằng card NVIDIA (NVENC; card hết phiên → CPU x264) → mỗi khung 1 gói → app giải mã bằng phần cứng
#               Windows không quay được cửa sổ (Windows 10 trước 1903, VD 1511) → hình lấy THẲNG từ Android: scrcpy-server 2.4
#               (video=true) mã hoá H.264 ngay trong máy → không cần quay cửa sổ / ffmpeg (CAPTURE=scrcpy | gdi | wgc để ép)
#  Đường chạm:  app → máy chủ → scrcpy-server 2.4 (chỉ điều khiển, không phát hình) chạy trong máy Android
#  Kết nối:     TRỰC TIẾP  TLS cổng STREAM_PORT (8189, modem phải mở cổng TCP về máy này)   ← nhanh nhất
#               DỰ PHÒNG   WebSocket 127.0.0.1:STREAM_WS_PORT (8020) qua đường hầm Cloudflare (STREAM_WS=wss://…)
#  Giao thức:   BRS2 — docs/STREAM-PROTOCOL.md
#
#  Mở cổng:     máy chủ TỰ mở cổng TCP STREAM_PORT trên modem bằng UPnP-IGD (lúc chạy + mỗi 30 phút) — modem tắt UPnP thì mở tay
#  Máy ngủ:     ghi redroid/viewers.json (máy nào đang có người xem) cho `phonectl idle`; khách mở máy đang NGỦ → `phonectl wake`
#               (web / app Android: "đang thức dậy", tự thử lại · app PC: giữ kết nối tới khi máy lên) — bản 11/12a
#  Web thẳng:   trình duyệt (web, iPhone) nối THẲNG vào chính cổng TLS của app: wss://dN.<miền>:STREAM_PORT/v2/stream —
#               SNI dN.<miền> → chứng chỉ Let's Encrypt (tự xin / gia hạn bằng mã Cloudflare CF_DNS_TOKEN), tên tự trỏ IP nhà
#               mạng; app nối bằng IP vẫn chứng chỉ tự ký cũ. Bật 1 lần: python bluestream.py --webdirect — bản 11/12b
#  Chạy:  python bluestream.py            (bảng BlueRoblox tự chạy — dịch vụ "phat-hinh")
#         python bluestream.py --selftest (máy Linux/thử: nguồn hình giả, không cần đăng nhập)
#         python bluestream.py --upnp     (thử mở cổng trên modem bằng UPnP 1 lần, in kết quả — không chạy máy chủ)
#         python bluestream.py --netcheck [--fix]  (chẩn đoán đường nối thẳng: IP modem / CGNAT / cổng; --fix: tự đổi sang cổng mở được)
#  cloudphone.conf:  STREAM_PORT=8189 · STREAM_WS_PORT=8020 · STREAM_WS=wss://stream.blueroblox.shop/v2/stream
#                    STREAM_PUBLIC_IP= (trống = tự dò) · STREAM_CPU=1 (luôn nén CPU) · NVENC_MAX=5 · UPNP=0 (không tự mở cổng)
# =====================================================================================================
import asyncio, base64, collections, ctypes, datetime, hashlib, json, logging, os, queue, random, re, select, socket, ssl, struct, subprocess, sys, threading, time
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

WIN = os.name == "nt"
B = os.path.dirname(os.path.abspath(__file__))
RTC = os.path.join(B, "rtc"); os.makedirs(RTC, exist_ok=True)
NOWIN = 0x08000000 if WIN else 0
SELFTEST = "--selftest" in sys.argv


def log(*a):
    try: print(time.strftime("%H:%M:%S"), *a, flush=True)
    except Exception: pass


def load_conf():
    c = {}
    for f in (os.path.join(B, "cloudphone.conf"), os.path.expanduser("~/cloudphone.conf")):
        try:
            for line in open(f, encoding="utf-8-sig"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1); c.setdefault(k.strip(), v.strip())
        except FileNotFoundError:
            pass
    return c


C = load_conf()
SB = (C.get("SUPABASE_URL") or "").rstrip("/")
KEY = C.get("SUPABASE_SERVICE_KEY") or ""
NODE_ID = C.get("NODE_ID") or socket.gethostname()
PRIMARY = C.get("PRIMARY", "1") == "1"
PORT = int(C.get("STREAM_PORT") or 8189)
WS_PORT = int(C.get("STREAM_WS_PORT") or 8020)
WS_URL = (C.get("STREAM_WS") or "").strip()
API_BASE = (C.get("PUBLIC_BASE") or "https://phone.blueroblox.shop").rstrip("/")
ALWAYS_CPU = C.get("STREAM_CPU", "0") == "1"
NVENC_MAX = int(C.get("NVENC_MAX") or 5)
FF_URL = "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip"   # 6.1: hợp driver NVENC 12.x (GTX 10xx)
FF = next((p for p in (os.path.join(RTC, "ffmpeg.exe"), os.path.join(RTC, "ffmpeg")) if os.path.isfile(p)), None) or ("ffmpeg" if not WIN else os.path.join(RTC, "ffmpeg.exe"))


def ensure_ffmpeg():
    """Tải FFmpeg 6.1.1 (bản chính thức của Gyan trên GitHub) vào rtc\\ffmpeg.exe nếu chưa có."""
    global FF
    if not WIN or (os.path.isfile(os.path.join(RTC, "ffmpeg.exe")) and os.path.isfile(os.path.join(RTC, "ff61.ok"))): return
    import io, zipfile
    try:
        log("tải FFmpeg 6.1.1 (~80MB, 1 lần)…")
        data = urllib.request.urlopen(urllib.request.Request(FF_URL, headers={"User-Agent": "BlueRoblox"}), timeout=600).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        tmp = os.path.join(RTC, "ffmpeg.exe.tmp")
        open(tmp, "wb").write(z.read(next(x for x in z.namelist() if x.endswith("/bin/ffmpeg.exe"))))
        os.replace(tmp, os.path.join(RTC, "ffmpeg.exe")); open(os.path.join(RTC, "ff61.ok"), "w").write("1")
        FF = os.path.join(RTC, "ffmpeg.exe"); log("✓ đã có FFmpeg")
    except Exception as e:
        log("không tải được FFmpeg:", e)
ADB = next((p for p in (os.path.join(B, "platform-tools", "adb.exe"),) if os.path.isfile(p)), None) or "adb"
JAR = os.path.join(RTC, "scrcpy-server-v2.4")
JAR_URL = "https://github.com/Genymobile/scrcpy/releases/download/v2.4/scrcpy-server-v2.4"
JAR_DEV = "/data/local/tmp/br-scrcpy-2.4.jar"
CERT, CKEY = os.path.join(RTC, "stream-cert.pem"), os.path.join(RTC, "stream-key.pem")
PHONES_JSON = os.path.join(B, "redroid", "phones.json")

PRESETS = {"eco": (960, 30, 1500), "bal": (1280, 60, 3000), "hd": (1600, 60, 6000)}     # cạnh dài tối đa, FPS, kbps
# Chế độ TỰ ĐỘNG: bitrate tự hạ / tự tăng theo tốc độ app nhận thật (ACK). Bitrate thấp → giảm luôn độ nét + khung/giây
# (ít điểm ảnh = ít dữ liệu, máy ảo mã hoá + điện thoại giải mã kịp → hết giật, hết trễ dồn). Mạng khoẻ thì về đủ 1280 · 60 FPS.
AUTO_TIERS = ((300, 480, 15), (450, 640, 20), (800, 854, 24), (1300, 1024, 30), (2000, 1280, 30))      # (dưới kbps, cạnh dài tối đa, FPS tối đa)
AUTO_CELL_KBPS = 1500                     # app báo đang dùng 4G/5G → bắt đầu nhẹ (1280 · 30 FPS), mạng ổn thì tự tăng sau ~20 giây
# Đường VÒNG qua Cloudflare (WebSocket — web luôn đi đường này, app khi không nối thẳng được) chậm hơn đường thẳng nhiều
# (09/11 đo ~300–600 kbps) → Tự động bắt đầu nhẹ, khỏi 5 giây đầu hình đứng / bỏ khung. Đổi: STREAM_WS_START_KBPS trong conf.
def _int_conf(k, d):
    try: return int(float(str(C.get(k, d)).strip() or d))
    except (TypeError, ValueError): return d
WS_START_KBPS = max(300, _int_conf("STREAM_WS_START_KBPS", 1500))
# Nghẽn → hạ bitrate rồi GIỮ mức đó ≥ RATE_HOLD_MIN giây (nghẽn lại trong 3 phút → giữ gấp đôi, tối đa RATE_HOLD_MAX) mới thử tăng,
# và tăng từng bước nhỏ (×1,15). Trước đây cứ yên 10 giây là tăng ×1,3 → vượt sức đường truyền → nghẽn → hạ → tăng… (log 09/11:
# mỗi ~35 giây 1 vòng, phiên đứt rồi nối lại). Mức đã dò được nhớ 15 phút theo khách + máy + loại đường → nối lại bắt đầu đúng mức.
RATE_HOLD_MIN, RATE_HOLD_MAX, RATE_MEM_S = 40.0, 600.0, 900.0
# 11/11 (kiemlag.py trên 4 máy chủ): đường vòng đổi chất lượng ~110 lần / giờ xem (≈ 30 giây 1 lần), mỗi lần đổi = bật lại bộ nén
# (MuMu: scrcpy trong máy Android) → đứng hình 1–3 giây = "ping thấp mà lag". Nay: 1–2 lần app báo nhận chậm chỉ bỏ tới khung khoá
# (≤ 1 giây), KHÔNG đổi chất lượng; chỉ hạ khi chậm LẶP LẠI (≥ CONG_REPEAT lần trong CONG_WIN giây kể từ lần đổi trước) hoặc máy chủ
# đẩy hình ra không kịp (nghẽn thật); hạ cách nhau > RATE_DOWN_GAP giây; tăng lại khi yên > RATE_UP_GAP giây, bước lớn hơn.
# Đường vòng Cloudflare (trạm HKG + 4G/5G) hay giật ngắn → ngưỡng "app chậm" 700 ms (đường thẳng giữ 350 ms).
LAG_DROP_MS = {"direct": max(150, _int_conf("STREAM_LAG_MS", 350)), "ws": max(150, _int_conf("STREAM_WS_LAG_MS", 700))}
RATE_DOWN_GAP, RATE_UP_GAP, CONG_REPEAT, CONG_WIN = 8.0, 45.0, 3, 20.0
BS_VER = "11/12b"
BS_SUB = "27/11f"                         # bản phụ (giữ BS_VER cho capnhat-ngu.ps1 / kiemlag.py): 17/11e dán vào Termux + hết kẹt hình vỡ sau mạng yếu
                                          # · 27/11e ANDROID 9 MƯỢT: hình ≤ 960, khung I thưa, bỏ khung → bật lại bộ nén ngay, khó bỏ khung oan,
                                          #   không dumpsys sau mỗi cú bấm; Thông số có "bộ nén Android ra … khung/s" + bỏ khung vì đâu (máy MuMu không đổi)
                                          # · 21/11a TRẠM TRUNG CHUYỂN máy PC cho thuê (pcrelay.py) — phần máy điện thoại KHÔNG đổi
                                          # · 17/11f không gửi khung thiếu lát (hình vỡ) + máy chủ vừa khởi động lại: khách mở máy nào máy đó lên trước
                                          # · 17/11g máy thức dậy lâu: báo thật cho khách + bật lỗi thì tự "khám máy" ghi vào nhật ký (phần hình không đổi)
                                          # · 17/11a: Android 9 khung khoá dày + tự lấy khung khoá · máy chủ LDPlayer lấy hình thẳng từ Android
                                          # · 13/11b: giữ app chờ khi bật hình lâu + cửa sổ quay lỗi / ra hình đen → lấy hình thẳng từ Android
                                          # · 13/11c: bật sáng màn hình Android mỗi lần khách mở máy (màn tắt = khách thấy MÀN ĐEN)
                                          # · 16/11a: máy tắt / Android chưa lên → tự gọi bật + báo rõ (hết quay mãi "chưa bật được hình")
                                          #           · mạng yếu: khung khoá theo giây thật, đo sức đường truyền, nhớ trần, bắt đầu nhẹ
def _float_conf(k, d):
    try: return float(str(C.get(k, d)).strip() or d)
    except (TypeError, ValueError): return d
# 21/11a — TRẠM TRUNG CHUYỂN MÁY PC CHO THUÊ (pcrelay.py, đợt 2). Máy PC thuê tự nối RA cổng phát hình này rồi chờ; khách mở điều khiển
# máy PC (web / app) cũng nối vào đây → pcrelay ghép 2 kết nối (hình máy PC → khách, chuột phím khách → máy PC). Thiếu file pcrelay.py /
# file lỗi / PC_RELAY=0 trong cloudphone.conf → trạm TẮT, phần máy điện thoại chạy y như cũ.
PCRELAY = None; PCRELAY_ERR = ""
if str(C.get("PC_RELAY", "1")).strip() != "0":
    try:
        if B not in sys.path: sys.path.insert(0, B)
        import pcrelay as PCRELAY
    except Exception as _e:
        PCRELAY = None; PCRELAY_ERR = "thiếu file pcrelay.py" if isinstance(_e, ModuleNotFoundError) else repr(_e)[:200]
else: PCRELAY_ERR = "PC_RELAY=0"
# Android 9 (LDPlayer 9) lấy hình bằng scrcpy: bộ nén trong máy là PHẦN MỀM (OMX.google.h264.encoder) và KHÔNG lặp khung khi màn đứng
# yên → "khung khoá mỗi 1 giây" thật ra là mỗi 60 khung (scrcpy đặt KEY_FRAME_RATE 60): lúc vuốt chỉ ~15–20 khung/giây → 3–4 giây mới
# có 1 khung khoá, màn đứng yên thì KHÔNG bao giờ có. Lỡ bỏ 1 khung (mạng chậm, app báo nhận chậm) là đứng hình tới khung khoá kế →
# khách thấy "vuốt xong 3–4 giây mới lên" (13/11, win1). 13/11a: Android 9 khung khoá mỗi 0,25 giây (= 15 khung) + chờ khung khoá quá
# 1,2 giây thì bật lại bộ nén (khung đầu luôn là khung khoá, hình đúng màn hiện tại) — 27/11e thay bằng cách dưới (khung I đó không phải khoá).
# 27/11e — ANDROID 9 MƯỢT NHƯ 12 / 15. Đo trên máy ảo Android THẬT trong CI (.github/a9-check, scrcpy-server 2.4 + ScrcpyVideo này):
#   Android 9  (OMX.google.h264.encoder — bộ nén duy nhất của LDPlayer 9): khoảng khoá 0,25 lúc cuộn → 6 khung I, chỉ 1 IDR (khung đầu),
#              chỉ 1 có cờ khoá → khung I định kỳ KHÔNG phải khung khoá (AOSP SoftAVCEnc: IDR mặc định mỗi 1000 khung); khung I ~3× khung P.
#              Khung/giây khi cuộn: cỡ 1280 → 10,6–10,9 · cỡ 960 → 14–16,5 · cỡ 800 → 15. Bật lại bộ nén → khung đầu sau ~0,4–0,5 giây.
#   Android 12 (c2.android.avc.encoder — như MuMu): 11 khung I = 11 IDR = 11 có cờ khoá → chờ khung khoá là đúng.
# → Máy Android 9 lỡ bỏ 1 khung (mạng giật, nghẽn) là đứng hình tới khi bật lại bộ nén (cũ: chờ 1,2 giây + khởi động scrcpy) = khách
#   thấy "nhấp xong 2–3 giây mới lên"; khung I dày (0,25) không giúp gì mà làm khung to dồn dập (dễ nghẽn → lại bỏ khung).
# Nay Android 9: khung I thưa (SCRCPY_IFRAME_S_A9 = 5) · bỏ khung → bật lại bộ nén ngay (SCRCPY_KEY_WAIT_S_A9 = 0,2) · khó bỏ khung hơn
# (ngưỡng "app chậm" × STREAM_A9_LAG_MUL = 2, hàng chờ STREAM_A9_QWAIT_S = 0,5 giây) · hình tối đa STREAM_A9_MAXH = 960 (trừ mức Nét;
# 0 = như cũ) → +40–50% khung/giây, khung nhỏ hơn. Máy MuMu (Android 12/15) KHÔNG đổi.
SCR_IFRAME = max(0.1, min(5.0, _float_conf("SCRCPY_IFRAME_S", 1.0)))
SCR_IFRAME_A9 = max(0.1, min(5.0, _float_conf("SCRCPY_IFRAME_S_A9", 5.0)))
KEY_WAIT_S = max(0.0, _float_conf("SCRCPY_KEY_WAIT_S", 0.0))           # 0 = tắt
KEY_WAIT_S_A9 = max(0.0, _float_conf("SCRCPY_KEY_WAIT_S_A9", 0.2))
A9_MAXH = max(0, _int_conf("STREAM_A9_MAXH", 960))                      # cạnh dài tối đa của hình Android 9 (trừ mức Nét) · 0 = theo mức chất lượng
A9_LAG_MUL = max(1.0, min(4.0, _float_conf("STREAM_A9_LAG_MUL", 2.0)))  # Android 9: ngưỡng "app chậm" (bỏ khung) gấp mấy lần máy khác
A9_QWAIT = max(0.15, min(2.0, _float_conf("STREAM_A9_QWAIT_S", 0.5)))   # Android 9: khung chờ gửi quá chừng này giây mới nhảy cóc (máy khác 0,15)
# 27/11f — CBVIDEO: máy chủ hình RIÊNG cho Android 9 (windows/cbvideo.jar · nguồn .github/a9-check/A9Video.java · dựng trong CI a9-check).
# Đo CI (simpleperf, máy ảo Android 9 4 nhân): scrcpy chỉ ~14 khung/giây vì bộ nén OMX tự ĐỌC NGƯỢC hình từ GPU ngay trong luồng nén
# (~70% thời gian luồng nén nằm ở ống goldfish, mã hoá thật ~3%); hình nhỏ hơn không giúp (800 / 640 / 480 đều ~12–16 trên máy 4GB thật).
# cbvideo: màn ảo → ImageReader (đọc hình trong tiến trình riêng) → NV12 → cùng bộ nén bằng ByteBuffer — đọc và nén chạy song song.
# Cùng giao thức scrcpy 2.4 (ScrcpyVideo đọc y nguyên) + 1 byte 'K' qua socket hình = khung IDR NGAY → bỏ khung không còn phải bật lại
# bộ nén (≈ 0,5 giây đứng hình) nên Android 9 dùng lại ngưỡng bỏ khung bình thường (bớt trễ dồn). Lỗi / thiếu file → tự quay về scrcpy.
# Chế độ (STREAM_A9_CBVIDEO): test (mặc định bản 27/11f) = chỉ phiên xin ?cbv=1 trên web — kiểm trên máy thật trước khi bật cho khách ·
# 1 / on = mọi máy Android 9 (phiên ?cbv=0 vẫn dùng scrcpy để so) · 0 / off = tắt hẳn.
_cbvm = str(C.get("STREAM_A9_CBVIDEO", "test")).strip().lower()
A9_CBV_MODE = "off" if _cbvm in ("0", "off", "false", "no") else ("on" if _cbvm in ("1", "on", "true", "yes", "auto") else "test")
A9_CBV = A9_CBV_MODE != "off"
CBV_FILE = ("cbvideo.jar", "bf8403f16395162ae5de3c0e4abe5215")                        # md5 ghim: file lạ / sai bản không bao giờ chạy trong máy khách
CBV_DEV = "/data/local/tmp/cb-cbvideo-" + CBV_FILE[1][:8] + ".jar"
CBV_RAW = (C.get("REPO_RAW") or "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main").rstrip("/") + "/windows/"
CBV_API = (C.get("REPO_API") or "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents").rstrip("/") + "/windows/"
CBV_STATS = max(0, _int_conf("STREAM_CBV_STATS_S", 120))                # cbvideo ghi 1 dòng thống kê vào nhật ký mỗi chừng này giây (0 = tắt)
CBV_KEY_GAP = 0.25                                                       # xin khung khoá tối đa 4 lần / giây
CBV_KEY_MAX_S = 2.5                                                      # xin rồi mà quá chừng này giây chưa có khung khoá → bật lại bộ nén như cũ
CBV_BAD_S = 1800                                                         # cbvideo lỗi ở 1 máy → máy đó dùng scrcpy 30 phút
# 16/11 — MẠNG YẾU VẪN MƯỢT. Máy lấy hình bằng scrcpy (Android 12/15): scrcpy 2.4 đặt KEY_FRAME_RATE = 60 nên bộ nén trong máy ĐẾM KHUNG
# — "khung khoá mỗi 1 giây" thật ra là mỗi 60 khung: phát 30 khung/giây → 2 giây, 20 khung/giây (mạng yếu) → 3 giây, màn đứng yên
# (lặp 10 khung/giây) → 6 giây. Mạng khách giật 1 nhịp = máy chủ bỏ khung tới khung khoá kế = ĐỨNG HÌNH 2–6 giây. Nay khoảng khung khoá
# tính theo khung/giây THẬT đang phát → khung khoá mỗi SCRCPY_KEY_EVERY_S giây (1) → hồi hình ≤ ~1 giây. 0 = như cũ.
# Bộ nén của máy nào không nhận kiểu này (scrcpy chết khi chưa ra khung nào) → máy đó tự quay về kiểu cũ 6 giờ.
SCR_KEY_S = max(0.0, min(5.0, _float_conf("SCRCPY_KEY_EVERY_S", 1.0)))
LOW_KEY_KBPS = _int_conf("STREAM_LOW_KEY_KBPS", 450)        # dưới mức này khung khoá thưa gấp đôi (mỗi khung khoá ăn gần hết 1 giây dữ liệu → hình khựng từng giây)
def key_every(kbps):
    """Hệ số khoảng khung khoá theo bitrate: 1 (bình thường) · 2 khi bitrate rất thấp."""
    return 2.0 if 0 < int(kbps or 0) < LOW_KEY_KBPS else 1.0
# 16/11c — HÌNH SẠCH KHI LƯỚT (máy chủ nén bằng ffmpeg: NVENC / x264). Đo trên video cuộn trang web 540x960 · 30 khung · 1500 kbps
# (SSIM lúc cuộn, 1 = y hệt gốc): x264 ultrafast (cũ) 0,938 · khung xấu nhất 0,870 → superfast 0,962 · xấu nhất 0,929 — CÙNG cỡ khung,
# cùng độ trễ (CPU +36%, ~3 ms/khung). Khung khoá 2 giây / bộ đệm to hơn còn đẹp thêm (0,975) nhưng thử mạng giật: đứng hình nhiều
# và lâu hơn → GIỮ như cũ (đổi được bằng conf nếu muốn thử).
KEY_S = max(0.5, min(5.0, _float_conf("STREAM_KEY_S", 1.0)))          # khung khoá mỗi KEY_S giây (như cũ: 1)
VBV_S = max(0.0, min(1.0, _float_conf("STREAM_VBV_S", 0.0)))          # bộ đệm bitrate (giây) · 0 = công thức cũ (~6 khung)
X264_PRESET = str(C.get("STREAM_X264_PRESET") or "superfast").strip() or "superfast"   # trước ultrafast (không lọc khối → vỡ ô khi lướt)
if X264_PRESET not in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium"): X264_PRESET = "superfast"
NVENC_PRESET = str(C.get("NVENC_PRESET") or "p4").strip().lower() or "p4"              # trước p1; ffmpeg / card không nhận → tự về p1
if not re.fullmatch(r"p[1-7]", NVENC_PRESET): NVENC_PRESET = "p4"
_KF_LEGACY = {}                           # "127.0.0.1:cổng" → tới lúc nào máy đó dùng lại khoảng khung khoá kiểu cũ
MIN_KBPS = max(120, _int_conf("STREAM_MIN_KBPS", 180))      # mức thấp nhất của Tự động (trước 16/11: 250)
DL_HINT_MAX = 2500                        # app / web báo tốc độ tải ước lượng (kbps) dưới mức này → bắt đầu ~60% tốc độ đó (chỉ để BẮT ĐẦU nhẹ)
CELL_LAG_MS = max(150, _int_conf("STREAM_CELL_LAG_MS", 500))   # khách dùng 4G/5G: ngưỡng "app chậm" tối thiểu (4G hay giật ngắn)
# Trần vừa đo: hạ vì nghẽn ở mức X → trong CEIL_S giây không thử tăng quá 0,9·X (hết vòng tăng → nghẽn → hạ mỗi 1–2 phút); thử lại rồi
# nghẽn tiếp → giữ trần gấp đôi (tối đa CEIL_MAX_S). Khách mạng yếu THƯỜNG XUYÊN (đã hạ ≥ 2 lần) → nhớ mức RATE_MEM_LONG_S (6 giờ)
# thay vì 15 phút: lần mở sau bắt đầu đúng mức, khỏi 3 lần đứng hình đầu phiên.
CEIL_S, CEIL_MAX_S = 600.0, 3600.0
RATE_MEM_LONG_S = max(RATE_MEM_S, _float_conf("RATE_MEM_LONG_MIN", 360.0) * 60)
# 17/11e — HẾT KẸT HÌNH VỠ Ô SAU KHI MẠNG YẾU (ticket 17/11: app Android, "Mạng yếu — đã giảm nét", hạ FPS + khởi động lại máy vẫn vỡ ô).
# Mạng khách giật vài lần → hạ dần tới mức rất thấp (180–300 kbps: hình 272x480 phóng to = vỡ ô) + nhớ mức đó tới 6 GIỜ + nhớ "trần" tới
# 1 giờ + cứ có 1 lần app nhận chậm là không được tăng → mạng đã khoẻ lại vẫn kẹt ở mức thấp; khởi động lại máy / đổi FPS / đổi máy
# (mức nhớ theo KHÁCH) đều nạp lại đúng mức thấp đó. Nay: (1) mức nhớ cũ hơn RATE_FRESH_S giây → phiên mới bắt đầu ≥ RATE_FRESH_KBPS và
# KHÔNG giữ trần / thời gian giữ cũ (mạng còn yếu thật thì vài giây sau tự hạ lại) · (2) khách TỰ chọn chất lượng → bỏ mức đã nhớ, dò lại
# từ đầu · (3) yên CEIL_CALM_S giây không phải hạ → bỏ trần cũ + thời gian giữ, được thử tăng · (4) mạng 4G hay giật lẻ: ≤ 1 lần chậm
# trong 90 giây vẫn tính là yên để tăng.
RATE_FRESH_S = max(30.0, _float_conf("RATE_FRESH_S", 180.0))
RATE_FRESH_KBPS = max(300, _int_conf("RATE_FRESH_KBPS", 700))
CEIL_CALM_S = max(60.0, _float_conf("CEIL_CALM_S", 180.0))
# 17/11e — DÁN CHỮ VÀO TERMUX: dán = đặt bộ nhớ copy của máy + phím PASTE. Termux (dòng lệnh) BỎ QUA phím PASTE → khách bấm "Dán chữ"
# mà Termux đứng im (ticket 17/11). App đang mở là Termux → đặt bộ nhớ copy rồi bấm Ctrl+Alt+V = phím tắt dán của chính Termux (dán
# thật: giữ chữ có dấu, nhiều dòng, bracketed paste). Tắt: PASTE_TERMUX=0. Thêm app khác dán bằng Ctrl+Alt+V: PASTE_CTRL_ALT_V=gói1,gói2
PASTE_TERMUX = str(C.get("PASTE_TERMUX", "1")).strip() != "0"
PASTE_CAV_PKGS = tuple(p.strip() for p in ("com.termux," + str(C.get("PASTE_CTRL_ALT_V") or "")).split(",") if p.strip())
_FG_RE = re.compile(r"\bu\d+\s+([A-Za-z][\w.]*)/")
_CAV_SAID = set()
# 16/11 — HẾT QUAY MÃI "Máy chủ chưa bật được hình": lỗi lặt vặt lúc bật hình lần đầu → thử lại tại chỗ (app được giữ kết nối);
# adb KHÔNG thấy máy (máy đang tắt mà không phải "ngủ", Android treo / chưa lên) → gọi `phonectl wake` (CHỈ bật máy đang TẮT, không
# bao giờ khởi động lại máy đang chạy) + báo khách đúng tình trạng + trường fix="reboot" để app hiện nút "Khởi động lại máy".
FIRST_TRIES = 3                           # số lần thử bật hình lúc mở máy
FIRST_NEW_TRY_S = 18.0                    # quá chừng này giây thì không thử thêm lần mới (web chờ WELCOME tối đa 45 giây)
BOOT_IF_OFF = str(C.get("BOOT_IF_OFF", "1")).strip() != "0"
HUNG_S = max(20.0, _float_conf("BOOT_HUNG_S", 90.0))        # máy ĐANG CHẠY mà Android chưa trả lời quá chừng này giây → gợi ý khởi động lại
BOOT_AGAIN_S = 120.0                      # phonectl vừa báo máy lên xong mà adb vẫn không thấy → không gọi bật vòng lặp
MSG_NOVIDEO = "Máy chủ chưa lấy được hình của máy này. Bấm “Khởi động lại máy” để sửa (1–2 phút, dữ liệu giữ nguyên) — vẫn lỗi thì báo hỗ trợ."
# Cửa sổ giả lập của 1 máy quay lỗi (không ra khung / ngừng vẽ / chỉ ra hình đen) → trong WGC_BAD_MIN phút sau, mở máy đó lấy hình
# THẲNG từ Android luôn (khỏi chờ quay cửa sổ 6–15 giây mỗi lần mở). 0 = tắt (lần nào cũng thử quay cửa sổ trước như cũ).
WGC_BAD_S = max(0.0, _float_conf("WGC_BAD_MIN", 30.0)) * 60
# 14/11: khách mở máy mà màn hình Android đang TẮT (khách bấm nút nguồn, Android tự tắt, máy vừa tạo / vừa thức dậy) → scrcpy chạy với
# power_on=false và cửa sổ giả lập đều chỉ ra MÀN ĐEN. Mỗi lần mở máy: màn tắt → bật sáng (KEYCODE_WAKEUP, máy đang sáng thì không gửi
# phím) + bỏ màn khoá + giữ màn luôn sáng (Android quên khi khởi động lại / ảnh mẫu cũ). WAKE_ON_OPEN=0 → tắt.
WAKE_ON_OPEN = str(C.get("WAKE_ON_OPEN", "1")).strip() != "0"
_WGC_BAD = {}                                 # tên máy → lúc hết "quay cửa sổ lỗi"
def wgc_mark_bad(name):
    if WGC_BAD_S > 0 and name: _WGC_BAD[name] = time.time() + WGC_BAD_S
def wgc_is_bad(name):
    t = _WGC_BAD.get(name or "", 0)
    if t and t <= time.time(): _WGC_BAD.pop(name, None); return False
    return bool(t)
def _is_black(a):
    """Khung (numpy BGRA) gần như đen hết: lấy mẫu 1/8 mỗi chiều, không điểm nào sáng quá 24."""
    try: return a is not None and int(a[::8, ::8, :3].max()) < 25
    except Exception: return False
_RATE_MEM = {}                            # (uid, mã máy, loại đường) → {"k": kbps, "until": giữ tới lúc, "hs": số giây giữ, "lc": lúc nghẽn, "t": lúc ghi}
KEYCODE = {"back": 4, "home": 3, "recents": 187, "power": 26, "volup": 24, "voldown": 25, "menu": 82}

# loại tin nhắn (docs/STREAM-PROTOCOL.md)
C_HELLO, C_TOUCH, C_KEY, C_TEXT, C_SCROLL, C_CMD, C_PING, C_QUALITY, C_KEYFRAME, C_CLIP, C_BYE, C_ACK = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A
S_WELCOME, S_VIDEO, S_SIZE, S_CLIP, S_PONG, S_ERROR, S_STATS = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87


# ================================================================ Supabase (khoá service — chỉ nằm trên máy chủ)
def sb(method, path, body=None, token=None, timeout=15, extra=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + (token or KEY), "Content-Type": "application/json"}
    if extra: h.update(extra)
    req = urllib.request.Request(SB + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip() else None


_ucache, _mcache = {}, {"t": 0, "v": {}}


def whoami(token):
    if not token or len(token) > 4096: return None
    k = hashlib.sha256(token.encode()).hexdigest(); now = time.time(); c = _ucache.get(k)
    if c and c[1] > now: return c[0]
    try: u = sb("GET", "/auth/v1/user", token=token)
    except Exception: return None
    uid = u.get("id") if isinstance(u, dict) else None
    if not uid: return None
    try: p = (sb("GET", f"/rest/v1/profiles?id=eq.{uid}&select=role,locked") or [{}])[0]
    except Exception: p = {}
    if p.get("locked"): return None
    me = {"uid": uid, "admin": False}
    if p.get("role") == "admin":            # 21.11l: admin = hàm SQL is_admin() của CHÍNH phiên này → đã bật xác minh 2 bước mà chưa nhập mã 6 số thì không phải admin
        try: me["admin"] = sb("POST", "/rest/v1/rpc/is_admin", {}, token=token) is True
        except Exception: me["admin"] = False                           # hỏi không được → không cho quyền admin (chặn chứ không mở)
    if len(_ucache) > 5000: _ucache.clear()
    _ucache[k] = (me, now + 120)
    return me


def maint():
    if time.time() - _mcache["t"] > 20:
        try: _mcache["v"] = sb("POST", "/rest/v1/rpc/cloudphone_status", {}) or {}
        except Exception: pass
        _mcache["t"] = time.time()
    return _mcache["v"]


def shared_with(pid, uid):
    try:
        rows = sb("GET", f"/rest/v1/cloud_phone_shares?phone_id=eq.{pid}&grantee_id=eq.{uid}&kind=eq.share&revoked=is.false&select=expires_at") or []
    except Exception:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in rows:
        e = r.get("expires_at")
        if not e: return True
        try:
            if datetime.datetime.fromisoformat(e.replace("Z", "+00:00")) > now: return True
        except Exception: pass
    return False


REAUTH_S = 20            # phiên đang mở: kiểm lại quyền mỗi 20 giây (chủ máy TẮT CHIA SẺ / chuyển máy / admin khoá máy → ngắt ngay)
def _share_now(pid, uid):
    """Còn được chia sẻ không: True / False / None (lỗi mạng — không kết luận, không ngắt oan)."""
    try: rows = sb("GET", f"/rest/v1/cloud_phone_shares?phone_id=eq.{pid}&grantee_id=eq.{uid}&kind=eq.share&revoked=is.false&select=expires_at")
    except Exception: return None
    now = datetime.datetime.now(datetime.timezone.utc)
    for r in rows or []:
        e = r.get("expires_at")
        if not e: return True
        try:
            if datetime.datetime.fromisoformat(e.replace("Z", "+00:00")) > now: return True
        except Exception: return True
    return False


def recheck(pid, me):
    """Phiên đang mở còn quyền không → None (còn) hoặc Deny (ngắt). Admin không bị kiểm."""
    if SELFTEST or not me or me.get("admin"): return None
    try: rows = sb("GET", f"/rest/v1/cloud_phones?id=eq.{pid}&select=user_id,locked,locked_until,lock_reason")
    except Exception: return None
    if rows is None: return None
    if not rows: return Deny("NOT_YOURS", "Máy không còn tồn tại.")
    p = rows[0]
    if p.get("user_id") != me.get("uid") and _share_now(pid, me.get("uid")) is False:
        return Deny("REVOKED", "Chủ máy đã tắt chia sẻ hoặc đã chuyển máy — bạn không còn quyền dùng máy này.")
    if locked(p): return Deny("LOCKED", "Máy đang bị khoá: " + (p.get("lock_reason") or "liên hệ hỗ trợ."))
    return None


def locked(p):
    if not p.get("locked"): return False
    u = p.get("locked_until")
    if not u: return True
    try: return datetime.datetime.fromisoformat(u.replace("Z", "+00:00")) > datetime.datetime.now(datetime.timezone.utc)
    except Exception: return True


def phones_json():
    try: return {p["name"]: p for p in json.load(open(PHONES_JSON, encoding="utf-8")).get("phones", [])}
    except Exception: return {}


class Deny(Exception):
    def __init__(self, code, msg, **extra): super().__init__(msg); self.code, self.msg, self.extra = code, msg, extra


class NoWindow(Deny):
    """Không thấy cửa sổ giả lập của máy (máy đang TẮT — hoặc cửa sổ bị ẩn / đổi tên trong khi Android vẫn chạy)."""


class WinBad(Deny):
    """Cửa sổ máy có nhưng kích thước lỗi (đang khởi động / thu nhỏ) → thử lấy hình thẳng từ Android."""


class CapGone(Deny):
    """17/11a: Windows ĐÓNG phiên quay cửa sổ ngay khi vừa bắt đầu (cửa sổ ẩn, màn hình máy chủ không vẽ, máy đang tắt…).
       Android còn chạy → phiên lấy hình thẳng từ Android; máy tắt thật → báo khách như cũ."""


class AdbGone(RuntimeError):
    """adb không thấy máy (máy tắt, Android treo / chưa lên, adb đứt) — thử bật hình lại ngay là vô ích."""


def err_json(code, msg, **extra):
    """Gói S_ERROR. Trường phụ (app mới đọc, app cũ bỏ qua): fix="reboot" → hiện nút Khởi động lại máy · boot=1 → máy đang được bật."""
    d = {"code": code, "msg": msg}; d.update({k: v for k, v in extra.items() if v})
    return json.dumps(d, ensure_ascii=False).encode()


class CaptureBlocked(Exception):
    """Windows không cho quay cửa sổ giả lập (hoặc quay mà không ra khung nào) → phiên này lấy hình THẲNG từ Android (scrcpy)."""


def authorize(hello):
    """Kiểm tra quyền xem máy. Trả về (me, phone row)."""
    pid = str(hello.get("phone") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", pid): raise Deny("BAD", "Thiếu mã máy.")
    if SELFTEST: return {"uid": "test", "admin": True}, {"id": pid, "name": "Máy thử", "container": "selftest", "port": 0, "android": "9", "status": "active"}
    me = whoami(hello.get("token") or "")
    if not me: raise Deny("AUTH", "Phiên đăng nhập hết hạn, hãy đăng nhập lại.")
    rows = sb("GET", f"/rest/v1/cloud_phones?id=eq.{pid}&select=id,user_id,name,container,port,node,status,locked,locked_until,lock_reason,android,fps") or []
    if not rows: raise Deny("NOT_YOURS", "Không tìm thấy máy.")
    p = rows[0]
    if not (me["admin"] or p.get("user_id") == me["uid"] or shared_with(pid, me["uid"])): raise Deny("NOT_YOURS", "Đây không phải máy của bạn.")
    n = p.get("node")
    if not (n == NODE_ID or (not n and PRIMARY)): raise Deny("OFFLINE", "Máy nằm ở máy chủ khác — hãy mở lại.")
    if p.get("status") != "active": raise Deny("OFFLINE", "Máy chưa chạy (đang tạo, tạm dừng hoặc đã hết hạn).")
    if locked(p) and not me["admin"]: raise Deny("LOCKED", "Máy đang bị khoá: " + (p.get("lock_reason") or "liên hệ hỗ trợ."))
    if (maint().get("maint")) and not me["admin"]: raise Deny("MAINT", maint().get("maint_msg") or "Hệ thống đang bảo trì, quay lại sau ít phút.")
    ps = phones_json().get(p.get("container") or "")
    if ps and ps.get("port") and str(ps["port"]) != str(p.get("port") or ""):
        p["port"] = ps["port"]          # cổng adb THẬT trên máy này (phonectl sửa khi giả lập đổi số máy) — web có thể chưa kịp cập nhật
    if not p.get("container") or not p.get("port"): raise Deny("OFFLINE", "Máy chưa sẵn sàng, thử lại sau ít giây.")
    return me, p


# ================================================================ Quay cửa sổ (Windows Graphics Capture)
if WIN:
    import ctypes.wintypes as wt
    U32 = ctypes.windll.user32
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)      # toạ độ điểm ảnh thật (không bị phóng to Windows làm lệch)
    except Exception:
        try: U32.SetProcessDPIAware()
        except Exception: pass
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def win_title(h):
        n = U32.GetWindowTextLengthW(h)
        if not n: return ""
        b = ctypes.create_unicode_buffer(n + 1); U32.GetWindowTextW(h, b, n + 1); return b.value

    GWL_STYLE, GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, GW_OWNER = -16, -20, 0x80, 0x40000, 4
    _K32 = ctypes.WinDLL("kernel32")
    _K32.OpenProcess.restype = ctypes.c_void_p; _K32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _K32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    _K32.CloseHandle.argtypes = [ctypes.c_void_p]
    # Cửa sổ có chữ trùng tên máy nhưng KHÔNG phải giả lập (PowerShell đang chạy lệnh, Notepad mở file nhật ký…) → bỏ qua
    NOT_EMU = {"python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe", "cmd.exe", "conhost.exe", "windowsterminal.exe", "openconsole.exe",
               "notepad.exe", "notepad++.exe", "explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "code.exe", "taskmgr.exe",
               "mmc.exe", "blueserver.exe", "bluerobloxpc.exe"}

    def proc_of(h):
        """(tên tiến trình viết thường, pid) của cửa sổ."""
        pid = wt.DWORD(); U32.GetWindowThreadProcessId(h, ctypes.byref(pid)); name = ""
        hp = _K32.OpenProcess(0x1000, False, pid.value)                     # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            try:
                buf = ctypes.create_unicode_buffer(520); n = wt.DWORD(520)
                if _K32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)): name = re.split(r"[\\/]", buf.value)[-1].lower()
            finally: _K32.CloseHandle(hp)
        return name, pid.value

    def _same_name(name):
        exact, prefix = [], []
        def cb(h, _):
            t = win_title(h)
            if t == name: exact.append(h)
            elif t and (t.startswith(name) or (name in t and len(name) >= 8)): prefix.append(h)
            return True
        U32.EnumWindows(EnumProc(cb), 0)
        return [h for h in exact if proc_of(h)[0] not in NOT_EMU], [h for h in prefix if proc_of(h)[0] not in NOT_EMU]

    def _rank(h):                 # cửa sổ THẬT của máy: đang hiện, có phần vẽ Android, to nhất (giả lập có thể có cửa sổ ẩn phụ trùng tên)
        l, t, r, b = rect_of(h)
        return (bool(U32.IsWindowVisible(h)), render_child(h) is not None, max(0, r - l) * max(0, b - t))

    def find_window(name):
        for hs in _same_name(name):
            if hs:
                h = max(hs, key=_rank); return h, win_title(h)
        return None, None

    def win_info(h):
        """1 dòng mô tả cửa sổ (ghi nhật ký khi Windows không cho quay)."""
        try:
            cls = ctypes.create_unicode_buffer(256); U32.GetClassNameW(h, cls, 256)
            ex = U32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF; st = U32.GetWindowLongW(h, GWL_STYLE) & 0xFFFFFFFF
            cloak = ctypes.c_int(0); ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloak), 4)    # DWMWA_CLOAKED
            l, t, r, b = rect_of(h); pn, pid = proc_of(h)
            fl = [k for k, on in (("đang hiện", U32.IsWindowVisible(h)), ("thu nhỏ", U32.IsIconic(h)), ("chạy ngầm/tool", ex & WS_EX_TOOLWINDOW),
                                   ("app", ex & WS_EX_APPWINDOW), ("cửa sổ con", st & 0x40000000), ("có cửa sổ chủ", U32.GetWindow(h, GW_OWNER)),
                                   ("bị che (cloaked)", cloak.value)) if on]
            return f"hwnd={int(h):#x} '{win_title(h)}' lớp={cls.value} {pn or '?'}:{pid} {r - l}x{b - t} tại ({l},{t}) [{', '.join(fl) or '-'}]"
        except Exception as e:
            return f"hwnd={h} ({e!r})"

    def rect_of(h):
        r = wt.RECT(); U32.GetWindowRect(h, ctypes.byref(r)); return r.left, r.top, r.right, r.bottom

    # Chỗ đỗ cửa sổ máy khách chạy ngầm — GIỐNG HỆT park_xy trong phonectl.py (phonectl đỗ, bluestream quay).
    # KHÔNG dùng (-32000, -32000) = toạ độ cửa sổ thu nhỏ: Windows Graphics Capture báo "The parameter is incorrect".
    PARK = (C.get("PARK") or "corner").strip().lower()       # corner: góc phải dưới màn hình chính, lộ PARK_SHOW điểm ảnh · screen: nằm hẳn trong màn hình
    PARK_SHOW = max(4, int(C.get("PARK_SHOW") or 24))
    KEEP_PROP = "CloudBlueKeep"                              # cửa sổ phải nằm hẳn trong màn hình mới quay được → phonectl không dời đi

    def park_xy(rc, mode=None):
        sw, sh = U32.GetSystemMetrics(0), U32.GetSystemMetrics(1)
        if (mode or PARK) == "screen": return max(0, sw - (rc[2] - rc[0])), max(0, sh - (rc[3] - rc[1]))
        return sw - PARK_SHOW, sh - PARK_SHOW

    def park(h, mode=None):
        x, y = park_xy(rect_of(h), mode)
        U32.SetWindowPos(h, 1, x, y, 0, 0, 0x0001 | 0x0010)                  # HWND_BOTTOM, giữ kích thước, không lấy focus
        return x, y

    def on_screen(h):
        l, t, r, b = rect_of(h)
        return l >= 0 and t >= 0 and r <= U32.GetSystemMetrics(0) and b <= U32.GetSystemMetrics(1)

    def frame_bounds(h):          # vùng Windows Graphics Capture quay thật (không gồm bóng đổ)
        r = wt.RECT()
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0: return r.left, r.top, r.right, r.bottom
        return rect_of(h)

    def render_child(h):          # cửa sổ con LỚN NHẤT = phần màn hình Android (LDPlayer / MuMu / MEmu đều vậy)
        kids = []
        def cb(c, _):
            if U32.IsWindowVisible(c):
                l, t, r_, b_ = rect_of(c)
                if r_ - l > 50 and b_ - t > 50: kids.append(((r_ - l) * (b_ - t), (l, t, r_, b_)))
            return True
        U32.EnumChildWindows(h, EnumProc(cb), 0)
        return max(kids)[1] if kids else None


class WindowSource:
    """Giữ KHUNG MỚI NHẤT của phần màn hình Android trong cửa sổ giả lập."""
    def __init__(self, name):
        self.name, self.latest, self.n, self.size_change = name, None, 0, None
        self.cond = threading.Condition(); self.stopping = False; self.ctl = None; self.closed = False; self.gen = 0

    def open(self):
        """Tìm cửa sổ máy → quay. Không quay được ở chỗ đỗ hiện tại → thử lại với cửa sổ nằm HẲN trong màn hình (đánh dấu để
           phonectl không dời đi). Vẫn không được → CaptureBlocked (phiên chuyển sang lấy hình thẳng từ Android)."""
        import numpy as np  # noqa: F401  (windows_capture trả numpy)
        from windows_capture import WindowsCapture
        h, title = find_window(self.name)
        if not h: raise NoWindow("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
        if U32.IsIconic(h): U32.ShowWindow(h, 4); time.sleep(0.6)       # thu nhỏ thì Windows không vẽ → hiện lại (không cướp chuột)
        elif not U32.IsWindowVisible(h): U32.ShowWindow(h, 4); time.sleep(0.4)   # bị ẩn hẳn → Windows không cho quay → hiện lại
        l, t, r, b = rect_of(h)
        if l <= -30000 and t <= -30000:              # chỗ đỗ CŨ = toạ độ cửa sổ thu nhỏ → Windows không quay được → dời về chỗ đỗ mới
            x, y = park(h); time.sleep(0.3)
            log(f"  {self.name}: dời cửa sổ từ ({l},{t}) về chỗ đỗ mới ({x},{y}) — ở (-32000,-32000) Windows không quay được")
        try:
            return self._open_at(h, title, WindowsCapture)
        except CaptureBlocked:
            if self.stopping or on_screen(h): raise
        x, y = park(h, "screen"); U32.SetPropW(h, KEEP_PROP, 1); time.sleep(0.4)
        log(f"  {self.name}: thử lại với cửa sổ nằm hẳn trong màn hình ({x},{y})")
        try:
            wh = self._open_at(h, title, WindowsCapture)
        except CaptureBlocked:
            U32.RemovePropW(h, KEEP_PROP); park(h)   # trong màn hình cũng không quay được → trả về chỗ đỗ cho gọn
            raise
        log(f"  {self.name}: ✓ cửa sổ nằm hẳn trong màn hình thì quay được → giữ ở đó (muốn mọi máy đỗ như vậy: PARK=screen trong cloudphone.conf)")
        return wh

    def _halt(self):
        """Dừng phiên quay đang chạy (khung đến muộn của phiên cũ bị bỏ qua nhờ số thế hệ gen)."""
        self.gen += 1
        ctl, self.ctl = self.ctl, None
        try:
            if ctl is not None and hasattr(ctl, "stop"): ctl.stop()
        except Exception: pass

    def _open_at(self, h, title, WindowsCapture):
        self.latest = None; self.closed = False; self.size_change = None
        fb = frame_bounds(h); ch = render_child(h) or fb
        self.cx, self.cy = max(0, ch[0] - fb[0]), max(0, ch[1] - fb[1])
        self.cw, self.ch = (ch[2] - ch[0]) & ~1, (ch[3] - ch[1]) & ~1
        self.fw, self.fh = fb[2] - fb[0], fb[3] - fb[1]
        if self.cw < 64 or self.ch < 64: raise WinBad("OFFLINE", "Cửa sổ máy đang lỗi kích thước — thử lại sau ít giây.")
        src = self; my = self.gen

        def make():
            # Quay theo SỐ CỬA SỔ (hwnd): tìm theo tên thì windows-capture bỏ qua cửa sổ "chạy ngầm" (tool window)
            try: cap = WindowsCapture(cursor_capture=None, draw_border=None, window_hwnd=int(h))
            except TypeError: cap = WindowsCapture(cursor_capture=None, draw_border=None, window_name=title)   # windows-capture bản cũ

            @cap.event
            def on_frame_arrived(frame, ictl):
                if src.stopping or src.gen != my:
                    try: ictl.stop()
                    except Exception: pass
                    return
                a = frame.frame_buffer                       # (cao, rộng, 4) BGRA
                if abs(a.shape[1] - src.fw) > 6 or abs(a.shape[0] - src.fh) > 6:
                    src.size_change = (a.shape[1], a.shape[0], time.time()); return
                src.size_change = None
                sub = a[src.cy:src.cy + src.ch, src.cx:src.cx + src.cw]
                if sub.shape[0] != src.ch or sub.shape[1] != src.cw: return
                buf = sub.copy()                             # thư viện dùng lại bộ nhớ khung → phải chép
                with src.cond:
                    src.latest = buf; src.n += 1; src.cond.notify_all()

            @cap.event
            def on_closed():
                if src.gen != my: return
                src.closed = True
                with src.cond: src.cond.notify_all()
            return cap

        # Windows CHỈ cho quay cửa sổ có trong Alt+Tab (CreateForWindow báo lỗi → "Failed to convert item to GraphicsCaptureItem").
        # Cửa sổ máy khách "chạy ngầm" (phonectl hide: kiểu tool window) → tạm thành cửa sổ thường lúc bắt đầu quay,
        # có hình rồi trả lại kiểu cũ (đổi kiểu SAU khi đã bắt đầu quay không làm dừng quay).
        ex0 = U32.GetWindowLongW(h, GWL_EXSTYLE)
        ex_cap = (ex0 | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        changed = False; errs = []
        try:
            if ex0 != ex_cap and ((ex0 & WS_EX_TOOLWINDOW) or U32.GetWindow(h, GW_OWNER)):
                U32.SetWindowLongW(h, GWL_EXSTYLE, ex_cap); changed = True
            for k in range(2):
                try:
                    self.ctl = make().start_free_threaded(); errs = []; break
                except Exception as e:
                    errs.append(str(e).replace("Capture session threw an exception: ", "")[:110])
                    if k or "GraphicsCaptureItem" not in str(e): break
                    # lần 2: ẩn → đổi kiểu → hiện lại không lấy focus (như phonectl hide) để Windows tính lại cửa sổ có trong Alt+Tab
                    U32.ShowWindow(h, 0); U32.SetWindowLongW(h, GWL_EXSTYLE, ex_cap); U32.ShowWindow(h, 4); changed = True; time.sleep(0.5)
            if not errs:
                t0 = time.time()
                with self.cond:
                    while self.latest is None and time.time() - t0 < 6 and not self.closed and not self.stopping:
                        self.cond.wait(0.2)
        finally:
            if changed: U32.SetWindowLongW(h, GWL_EXSTYLE, ex0)
        if errs:
            log(f"  {self.name}: Windows không cho quay cửa sổ ({' | '.join(errs)})")
            for x in [y for hs in _same_name(self.name) for y in hs][:4]: log(f"    · {win_info(x)}")
            raise CaptureBlocked("Windows không cho quay cửa sổ giả lập")
        if self.latest is None:
            gone, stopping = self.closed, self.stopping
            self._halt()
            if stopping: raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
            if gone: raise CapGone("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
            log(f"  {self.name}: cửa sổ không ra khung hình nào sau 6 giây — {win_info(h)}")
            raise CaptureBlocked("cửa sổ giả lập không ra hình")
        # Phải RA HÌNH LIÊN TỤC: giả lập ở cửa sổ khuất / chạy ngầm có thể ngừng vẽ (MuMu: chỉ 1 khung đầu rồi 0 khung/giây)
        # → app thấy hình ĐỨNG. Giả lập đang vẽ thì vẽ đều mỗi khung dù màn hình Android đứng yên.
        n1, t1 = self.n, time.time()
        with self.cond:
            while self.n < n1 + 4 and time.time() - t1 < 2.5 and not self.closed and not self.stopping:
                self.cond.wait(0.2)
        if self.n < n1 + 4:
            k, gone, stopping = self.n - n1, self.closed, self.stopping
            self._halt()
            if stopping: raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
            if gone: raise CapGone("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
            log(f"  {self.name}: cửa sổ chỉ ra {k} khung mới trong 2,5 giây (giả lập ngừng vẽ khi cửa sổ khuất?) — {win_info(h)}")
            raise CaptureBlocked("giả lập không vẽ hình liên tục ở cửa sổ này")
        # Ra hình đều mà TOÀN ĐEN (giả lập mất hình sau khi card đồ hoạ treo / cửa sổ khuất…) → khách thấy màn đen. Chờ thêm 2 giây
        # (màn đen thật lúc chuyển cảnh thì sẽ hết); vẫn đen → lấy hình thẳng từ Android (đen thật thì scrcpy cũng ra đúng màn đó).
        if _is_black(self.latest):
            t2 = time.time()
            with self.cond:
                while _is_black(self.latest) and time.time() - t2 < 2.0 and not self.closed and not self.stopping:
                    self.cond.wait(0.25)
            if _is_black(self.latest) and not self.closed and not self.stopping:
                self._halt()
                log(f"  {self.name}: cửa sổ giả lập chỉ ra hình ĐEN — {win_info(h)}")
                raise CaptureBlocked("cửa sổ giả lập chỉ ra hình đen")
        return self.cw, self.ch

    def resized(self):
        s = self.size_change
        return bool(s and time.time() - s[2] < 2 and abs(s[0] - self.fw) + abs(s[1] - self.fh) > 6)

    def stop(self):
        self.stopping = True
        with self.cond: self.cond.notify_all()
        self._halt()


# ================================================================ Quay bằng PrintWindow (Windows 10 bản cũ, VD 1511)
# Windows Graphics Capture (thư viện windows-capture) chỉ có từ Windows 10 bản 1903. Bản cũ hơn → import báo
# "DLL load failed … specified procedure could not be found" → quay bằng PrintWindow(PW_RENDERFULLCONTENT) thay thế:
# chạy từ Windows 8.1, lấy được cả phần vẽ DirectX/OpenGL, cửa sổ đã đẩy ra ngoài màn hình vẫn quay được (chỉ không được thu nhỏ).
_WGC = {"ok": None, "why": ""}
def wgc_ok():
    """Dùng được Windows Graphics Capture? (thử import 1 lần rồi nhớ). Ép quay PrintWindow: CAPTURE=gdi trong cloudphone.conf."""
    if _WGC["ok"] is None:
        if (C.get("CAPTURE") or "").strip().lower() == "gdi": _WGC.update(ok=False, why="CAPTURE=gdi")
        else:
            try:
                import windows_capture  # noqa: F401
                _WGC["ok"] = True
            except Exception as e:
                _WGC.update(ok=False, why=repr(e)[:160])
        if not _WGC["ok"]: log(f"⚠ Windows này không dùng được Windows Graphics Capture ({_WGC['why']})")
    return _WGC["ok"]

if WIN:
    _G32 = ctypes.WinDLL("gdi32"); _U32 = ctypes.WinDLL("user32"); _HP = ctypes.c_void_p
    for _n, _r, _a in (("CreateCompatibleDC", _HP, [_HP]), ("DeleteDC", wt.BOOL, [_HP]), ("SelectObject", _HP, [_HP, _HP]), ("DeleteObject", wt.BOOL, [_HP])):
        _f = getattr(_G32, _n); _f.restype = _r; _f.argtypes = _a
    _G32.CreateDIBSection.restype = _HP
    _G32.CreateDIBSection.argtypes = [_HP, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), _HP, wt.DWORD]
    for _n, _r, _a in (("GetDC", _HP, [_HP]), ("ReleaseDC", ctypes.c_int, [_HP, _HP]), ("PrintWindow", wt.BOOL, [_HP, _HP, wt.UINT]),
                       ("IsWindow", wt.BOOL, [_HP]), ("IsIconic", wt.BOOL, [_HP])):
        _f = getattr(_U32, _n); _f.restype = _r; _f.argtypes = _a

    class _BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class GdiSource:
    """Giữ KHUNG MỚI NHẤT của phần màn hình Android trong cửa sổ giả lập — quay bằng PrintWindow (Windows 10 bản cũ)."""
    def __init__(self, name, fps=60):
        self.name, self.latest, self.n, self.size_change = name, None, 0, None
        self.cond = threading.Condition(); self.stopping = False; self.closed = False
        self.fps = max(10, min(int(fps or 60), 60)); self.h = None

    def open(self):
        import numpy as np
        self.np = np
        h, title = find_window(self.name)
        if not h: raise NoWindow("OFFLINE", "Máy đang tắt hoặc đang khởi động lại — chờ ít giây rồi mở lại.")
        if _U32.IsIconic(h): U32.ShowWindow(h, 4); time.sleep(0.6)       # thu nhỏ thì Windows không vẽ → hiện lại
        self.h = h
        wl, wtp, wr, wb = rect_of(h)                                       # PrintWindow vẽ cả cửa sổ, gốc = góc cửa sổ
        rc = render_child(h) or (wl, wtp, wr, wb)
        self.fw, self.fh = wr - wl, wb - wtp
        self.cx, self.cy = max(0, rc[0] - wl), max(0, rc[1] - wtp)
        self.cw = (min(rc[2], wr) - max(rc[0], wl)) & ~1
        self.ch = (min(rc[3], wb) - max(rc[1], wtp)) & ~1
        if self.cw < 64 or self.ch < 64: raise WinBad("OFFLINE", "Cửa sổ máy đang lỗi kích thước — thử lại sau ít giây.")
        threading.Thread(target=self._run, daemon=True).start()
        t0 = time.time()
        with self.cond:
            while self.latest is None and time.time() - t0 < 6 and not self.closed and not self.stopping:
                self.cond.wait(0.2)
        if self.latest is None:
            self.stop(); raise Deny("OFFLINE", "Không lấy được hình từ cửa sổ máy — thử mở lại.")
        return self.cw, self.ch

    def _alloc(self, w, h):
        bi = _BIH(); bi.biSize = ctypes.sizeof(_BIH); bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32
        sdc = _U32.GetDC(None)
        mdc = _G32.CreateCompatibleDC(sdc)
        _U32.ReleaseDC(None, sdc)
        bits = ctypes.c_void_p()
        bmp = _G32.CreateDIBSection(mdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0) if mdc else None
        if not mdc or not bmp or not bits.value:
            if bmp: _G32.DeleteObject(bmp)
            if mdc: _G32.DeleteDC(mdc)
            raise OSError("không tạo được vùng nhớ hình (CreateDIBSection)")
        old = _G32.SelectObject(mdc, bmp)
        arr = self.np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_ubyte)), shape=(h, w, 4))   # BGRA, hàng trên cùng trước
        return mdc, bmp, old, arr

    def _free(self, g):
        if not g: return
        mdc, bmp, old, _ = g
        try: _G32.SelectObject(mdc, old)
        except Exception: pass
        try: _G32.DeleteObject(bmp); _G32.DeleteDC(mdc)
        except Exception: pass

    def _run(self):
        g = None; size = None; step = 1.0 / self.fps; dark_since = None; warned = False
        try:
            while not self.stopping:
                t0 = time.perf_counter()
                if not _U32.IsWindow(self.h): self.closed = True; break             # cửa sổ máy đã đóng (máy tắt / khởi động lại)
                l, t, r, b = rect_of(self.h); w, hh = r - l, b - t
                if w < 64 or hh < 64 or _U32.IsIconic(self.h): time.sleep(0.2); continue
                if abs(w - self.fw) > 6 or abs(hh - self.fh) > 6:                     # đổi cỡ (xoay máy…) → phiên bật lại bộ quay
                    self.size_change = (w, hh, time.time()); time.sleep(0.1); continue
                self.size_change = None
                if size != (w, hh):
                    self._free(g); g = None
                    g = self._alloc(w, hh); size = (w, hh)
                if _U32.PrintWindow(self.h, g[0], 2):                                 # 2 = PW_RENDERFULLCONTENT
                    sub = g[3][self.cy:self.cy + self.ch, self.cx:self.cx + self.cw]
                    if sub.shape[0] == self.ch and sub.shape[1] == self.cw:
                        buf = sub.copy()
                        if self.n % 30 == 0:                                          # hình đen mãi → ghi nhật ký 1 lần (để đổi chế độ vẽ)
                            if int(buf[::24, ::24, :3].max()) < 8:
                                dark_since = dark_since or time.time()
                                if not warned and time.time() - dark_since > 8:
                                    warned = True
                                    log(f"  ⚠ {self.name}: PrintWindow chỉ lấy được hình ĐEN — đổi chế độ vẽ của máy MEmu (DirectX ↔ OpenGL) rồi thử lại")
                            else: dark_since = None
                        with self.cond:
                            self.latest = buf; self.n += 1; self.cond.notify_all()
                d = step - (time.perf_counter() - t0)
                if d > 0: time.sleep(d)
        except Exception as e:
            if not self.stopping: log("  lỗi quay hình (PrintWindow):", repr(e)); self.closed = True
        finally:
            self._free(g)
            with self.cond: self.cond.notify_all()

    def resized(self):
        s = self.size_change
        return bool(s and time.time() - s[2] < 2 and abs(s[0] - self.fw) + abs(s[1] - self.fh) > 6)

    def stop(self):
        self.stopping = True
        with self.cond: self.cond.notify_all()


_VMODE = {"v": None}
def video_mode():
    """Cách lấy hình: wgc (Windows Graphics Capture, Windows 10 1903+) · scrcpy (lấy THẲNG từ Android) · gdi (PrintWindow) · fake (chạy thử).
       Mặc định: wgc nếu Windows có, không thì scrcpy (PrintWindow chỉ ra màn đen với MEmu). Ép: CAPTURE=scrcpy | gdi | wgc trong cloudphone.conf."""
    if _VMODE["v"] is None:
        c = (C.get("CAPTURE") or "").strip().lower()
        if SELFTEST or not WIN: v = "scrcpy" if c == "scrcpy" else "fake"
        elif c in ("scrcpy", "gdi"): v = c
        # 17/11a: máy chủ LDPlayer (EMU=ld) không ghi CAPTURE → lấy thẳng từ Android. Quay cửa sổ LDPlayer: quảng cáo LDPlayer lọt vào
        # hình của khách (win1 13/11) + Windows có thể đóng phiên quay ngay → khách mở máy chỉ thấy OFFLINE (win8 17/11). Ép quay cửa sổ: CAPTURE=wgc
        elif c != "wgc" and (C.get("EMU") or "").strip().lower() == "ld": v = "scrcpy"
        else: v = "wgc" if wgc_ok() else "scrcpy"
        _VMODE["v"] = v
        log("cách lấy hình: " + {"wgc": "quay cửa sổ giả lập (Windows Graphics Capture)", "scrcpy": "lấy thẳng từ Android (scrcpy-server mã hoá H.264 trong máy)",
                                  "gdi": "quay cửa sổ bằng PrintWindow", "fake": "hình giả (chạy thử)"}[v])
    return _VMODE["v"]


def make_source(name, fps=60):
    """Bộ quay hình cho 1 máy: Windows Graphics Capture (Windows 10 1903+) · PrintWindow (Windows cũ) · hình giả (chạy thử)."""
    if SELFTEST or not WIN: return FakeSource(name)
    return WindowSource(name) if wgc_ok() else GdiSource(name, fps)


class FakeSource:
    """Nguồn hình giả (chạy thử trên Linux / không có giả lập)."""
    def __init__(self, name, w=540, h=960):
        self.name, self.cw, self.ch, self.latest, self.n, self.closed = name, w, h, None, 0, False
        self.cond = threading.Condition(); self.stopping = False; self.size_change = None

    def open(self):
        import numpy as np
        self.np = np
        threading.Thread(target=self._run, daemon=True).start()
        with self.cond:
            while self.latest is None: self.cond.wait(0.1)
        return self.cw, self.ch

    def _run(self):
        np = self.np; t = 0
        base = np.zeros((self.ch, self.cw, 4), np.uint8)
        base[..., 0] = np.linspace(40, 200, self.cw, dtype=np.uint8)[None, :]
        base[..., 1] = np.linspace(30, 120, self.ch, dtype=np.uint8)[:, None]
        while not self.stopping:
            f = base.copy(); y = (t * 7) % (self.ch - 40)
            f[y:y + 40, :, :3] = 255
            with self.cond:
                self.latest = f; self.n += 1; self.cond.notify_all()
            t += 1; time.sleep(1 / 60)

    def resized(self): return False
    def stop(self): self.stopping = True


# ================================================================ Nén hình: FFmpeg → RTP nội bộ → khung H.264
class _NvencSlots:
    def __init__(self): self.n = 0; self.lock = threading.Lock()
    def take(self):
        with self.lock:
            if self.n >= NVENC_MAX: return False
            self.n += 1; return True
    def give(self):
        with self.lock: self.n = max(0, self.n - 1)


NVENC = _NvencSlots()
_nvenc_broken = {"until": 0}
_NV_PRE = {"v": None, "retry": 0.0, "lock": threading.Lock()}


def nvenc_preset():
    """16/11c: preset NVENC. Lần đầu thử NVENC_PRESET (mặc định p4 — nén đẹp hơn p1 rõ khi lướt, card vẫn dư sức) bằng 5 khung giả;
       ffmpeg / card / driver không nhận → p1 như cũ (10 phút sau thử lại: lúc thử có thể card đang đủ phiên)."""
    v = _NV_PRE["v"]
    if v and (v != "p1" or NVENC_PRESET == "p1" or time.time() < _NV_PRE["retry"]): return v
    with _NV_PRE["lock"]:
        v = _NV_PRE["v"]
        if v and (v != "p1" or NVENC_PRESET == "p1" or time.time() < _NV_PRE["retry"]): return v
        ok = NVENC_PRESET == "p1"
        if not ok:
            try:
                r = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=30", "-frames:v", "5",
                                    "-c:v", "h264_nvenc", "-preset", NVENC_PRESET, "-tune", "ull", "-zerolatency", "1", "-rc", "cbr",
                                    "-b:v", "500k", "-f", "null", "-"], capture_output=True, timeout=20, creationflags=NOWIN)
                ok = r.returncode == 0
                if not ok: log(f"  NVENC preset {NVENC_PRESET} không chạy được ({(r.stderr or b'').decode('utf-8', 'replace').strip()[-120:]}) → dùng p1, 10 phút sau thử lại")
            except Exception as e:
                log(f"  NVENC preset {NVENC_PRESET}: thử lỗi {e!r} → dùng p1")
        _NV_PRE["v"] = NVENC_PRESET if ok else "p1"; _NV_PRE["retry"] = time.time() + 600
        if ok and NVENC_PRESET != "p1": log(f"  NVENC: dùng preset {NVENC_PRESET} (đẹp hơn p1 khi lướt)")
        return _NV_PRE["v"]


class Encoder:
    """Mỗi phiên xem 1 bộ nén. Trả từng KHUNG (access unit) qua on_au(bytes|None, key, cfg, pts_us) — None = mất khung (chờ khung khoá)."""
    def __init__(self, src, out_w, out_h, fps, kbps, on_au, cpu=False):
        self.src, self.ow, self.oh, self.fps, self.kbps, self.on_au = src, out_w, out_h, fps, kbps, on_au
        self.cpu = cpu or ALWAYS_CPU or time.time() < _nvenc_broken["until"]
        self.proc = None; self.sock = None; self.alive = False; self.slot = False; self.stopped = False
        self.lock = threading.Lock()
        self.enc = "x264" if self.cpu else "nvenc"; self.frames_in = 0; self.started = 0.0

    def _cmd(self, rtp_port):
        sw, sh, fps, k = self.src.cw, self.src.ch, self.fps, self.kbps
        cmd = [FF, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{sw}x{sh}", "-framerate", str(fps), "-i", "-"]
        vf = []
        if (self.ow, self.oh) != (sw, sh): vf.append(f"scale={self.ow}:{self.oh}:flags=area")      # 16/11c: area (trước fast_bilinear) → chữ nét, ít răng cưa khi cuộn
        gop = str(max(int(fps * KEY_S * key_every(k)), 15))     # khung khoá mỗi ~1 giây (bitrate rất thấp: 2 giây): mạng chập chờn → hình hồi lại nhanh
        buf = f"{max(int(k * VBV_S) if VBV_S > 0 else k * 6 // max(fps, 1), min(250, max(96, k // 2)))}k"   # bộ đệm ~6 khung — nhỏ = ít trễ (STREAM_VBV_S để thử to hơn)
        if self.enc == "nvenc":
            if vf: cmd += ["-vf", ",".join(vf)]
            cmd += ["-c:v", "h264_nvenc", "-preset", nvenc_preset(), "-tune", "ull", "-zerolatency", "1", "-delay", "0", "-rc", "cbr",
                    "-profile:v", "baseline", "-bf", "0", "-g", gop, "-forced-idr", "1", "-strict_gop", "1",
                    "-b:v", f"{k}k", "-maxrate", f"{k}k", "-bufsize", buf]
        else:
            vf.append("format=yuv420p")
            cmd += ["-vf", ",".join(vf), "-c:v", "libx264", "-preset", X264_PRESET, "-tune", "zerolatency", "-profile:v", "baseline",
                    "-threads", "1", "-x264-params", f"sliced-threads=0:keyint={gop}:min-keyint={gop}:scenecut=0:bframes=0:rc-lookahead=0:sync-lookahead=0:repeat-headers=1",
                    "-b:v", f"{k}k", "-maxrate", f"{k}k", "-bufsize", buf]
        cmd += ["-an", "-bsf:v", "dump_extra=freq=keyframe", "-f", "rtp", "-rtpflags", "skip_rtcp", "-payload_type", "96",
                f"rtp://127.0.0.1:{rtp_port}?pkt_size=1300"]
        return cmd

    def start(self):
        with self.lock:
            if self.stopped: return
            if self.enc == "nvenc":
                if not NVENC.take(): self.enc = "x264"
                else: self.slot = True
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try: self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            except OSError: pass
            self.sock.bind(("127.0.0.1", 0)); self.sock.settimeout(0.5)
            port = self.sock.getsockname()[1]
            self.proc = subprocess.Popen(self._cmd(port), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                         creationflags=NOWIN, bufsize=0)
            self.alive = True; self.started = time.time()
        threading.Thread(target=self._feed, daemon=True).start()
        threading.Thread(target=self._rtp, daemon=True).start()
        threading.Thread(target=self._errlog, daemon=True).start()

    def _errlog(self):
        p = self.proc; lines = []
        try:
            for ln in iter(p.stderr.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if s: lines.append(s)
        except Exception: pass
        if not self.stopped and lines: log(f"  [ffmpeg {self.enc}] " + " | ".join(lines[-3:])[:300])

    def _feed(self):
        """Gửi đều đặn KHUNG MỚI NHẤT vào bộ nén (không xếp hàng khung cũ → không trễ dồn)."""
        step = 1.0 / self.fps; nxt = time.perf_counter(); last_n = -1; src = self.src; p = self.proc
        try:
            while self.alive and p.poll() is None:
                with src.cond:
                    if src.n == last_n and not src.stopping: src.cond.wait(step)
                    buf, last_n = src.latest, src.n
                if buf is None or src.stopping: 
                    if src.stopping: break
                    continue
                mv = memoryview(buf).cast("B")
                while mv:
                    n = p.stdin.write(mv)
                    if not n: raise BrokenPipeError
                    mv = mv[n:]
                self.frames_in += 1
                nxt += step; d = nxt - time.perf_counter()
                if d > 0: time.sleep(d)
                elif d < -0.25: nxt = time.perf_counter()
        except (BrokenPipeError, OSError, ValueError, AttributeError):
            pass

    def _rtp(self):
        """Ghép gói RTP (RFC 6184) thành từng khung H.264 Annex-B. Bit marker = hết khung → gửi NGAY (không chờ khung sau)."""
        SC = b"\x00\x00\x00\x01"; au = []; key = cfg = False; bad = False; last_seq = None; fu = None; sock = self.sock
        while self.alive:
            try: pkt, _ = sock.recvfrom(65536)
            except socket.timeout:
                if self.proc and self.proc.poll() is not None: break
                continue
            except OSError: break
            if len(pkt) < 13 or (pkt[0] >> 6) != 2: continue
            cc = pkt[0] & 0x0F; ext = pkt[0] & 0x10; pad = pkt[0] & 0x20
            marker = pkt[1] & 0x80; seq = (pkt[2] << 8) | pkt[3]
            off = 12 + 4 * cc
            if ext and len(pkt) >= off + 4: off += 4 + 4 * struct.unpack(">H", pkt[off + 2:off + 4])[0]
            end = len(pkt) - (pkt[-1] if pad else 0)
            pl = pkt[off:end]
            if last_seq is not None and seq != (last_seq + 1) & 0xFFFF: bad = True       # mất gói (hiếm, nội bộ) → bỏ khung, chờ khung khoá
            last_seq = seq
            if not pl: continue
            t = pl[0] & 0x1F
            if 1 <= t <= 23:
                au.append(SC + pl)
                if t == 5: key = True
                elif t in (7, 8): cfg = True
            elif t == 24:                                   # STAP-A
                i = 1
                while i + 2 <= len(pl):
                    n = (pl[i] << 8) | pl[i + 1]; i += 2
                    nal = pl[i:i + n]; i += n
                    if nal:
                        au.append(SC + nal); nt = nal[0] & 0x1F
                        if nt == 5: key = True
                        elif nt in (7, 8): cfg = True
            elif t == 28 and len(pl) >= 2:                  # FU-A
                s, e, nt = pl[1] & 0x80, pl[1] & 0x40, pl[1] & 0x1F
                if s: fu = bytearray(SC + bytes([(pl[0] & 0xE0) | nt])) + pl[2:]
                elif fu is not None: fu += pl[2:]
                else: bad = True
                if e and fu is not None:
                    au.append(bytes(fu)); fu = None
                    if nt == 5: key = True
            if marker:
                if au and not bad: self.on_au(b"".join(au), key, cfg, int(time.monotonic() * 1e6))
                elif bad: self.on_au(None, False, False, 0)
                au = []; key = cfg = bad = False; fu = None

    def stop(self):
        """Tắt hẳn (an toàn khi gọi nhiều lần / gọi trước khi start chạy xong)."""
        with self.lock:
            self.stopped = True; self.alive = False
            p, s = self.proc, self.sock
        try:
            if p and p.poll() is None: p.kill()                 # tắt TRƯỚC rồi mới đóng ống (Windows: đóng ống đang ghi dở sẽ bị chờ)
        except Exception: pass
        try:
            if p and p.stdin: p.stdin.close()
        except Exception: pass
        try:
            if s: s.close()
        except Exception: pass
        with self.lock:
            if self.slot: NVENC.give(); self.slot = False

    def failed_early(self):
        return self.proc is not None and self.proc.poll() is not None and time.time() - self.started < 6 and not self.stopped


# ================================================================ Điều khiển: scrcpy-server 2.4 (chỉ điều khiển)
def adb(serial, *args, timeout=20):
    try:
        r = subprocess.run([ADB, "-s", serial, *args], capture_output=True, timeout=timeout, creationflags=NOWIN)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace"), (r.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "no adb"


def ensure_jar():
    if os.path.isfile(JAR) and os.path.getsize(JAR) > 50000: return True
    try:
        log("tải scrcpy-server 2.4 (điều khiển chạm)…")
        req = urllib.request.Request(JAR_URL, headers={"User-Agent": "BlueRoblox"})
        data = urllib.request.urlopen(req, timeout=120).read()
        if len(data) < 50000: return False
        open(JAR + ".tmp", "wb").write(data); os.replace(JAR + ".tmp", JAR); return True
    except Exception as e:
        log("không tải được scrcpy-server:", e); return False


_devsize = {}
_devsize_warned = set()


def device_size(serial):
    """Kích thước màn hình Android theo hướng TỰ NHIÊN (wm size)."""
    c = _devsize.get(serial)
    if c and c[1] > time.time(): return c[0]
    code, out, _ = adb(serial, "shell", "wm", "size", timeout=10)
    size = None
    for pat in (r"Override size:\s*(\d+)x(\d+)", r"Physical size:\s*(\d+)x(\d+)"):      # cỡ 0x0 (MEmu Android 12 có lúc báo vậy) → bỏ qua
        m = re.search(pat, out)
        if m and int(m.group(1)) > 0 and int(m.group(2)) > 0: size = (int(m.group(1)), int(m.group(2))); break
    if size: _devsize[serial] = (size, time.time() + 600)
    elif serial not in _devsize_warned:
        _devsize_warned.add(serial); log(f"  [{serial}] wm size không dùng được: {' '.join(out.split())[:120] or '(trống)'}")
    return size


def device_size_cur(serial):
    """Cỡ màn hình ĐANG HIỆN (logic, theo hướng hiện tại) — đúng số scrcpy dùng để nhận cú chạm. dumpsys window displays: "cur=720x1280"."""
    code, out, _ = adb(serial, "shell", "dumpsys", "window", "displays", timeout=10)
    m = re.search(r"\bcur=(\d+)x(\d+)", out or "")
    if m and int(m.group(1)) > 0 and int(m.group(2)) > 0: return int(m.group(1)), int(m.group(2))
    return None


def adb_connect(serial):
    """Nối adb tới máy (giả lập mở adb TCP 127.0.0.1:cổng). Chưa nối thì adb báo "device … not found"."""
    if ":" not in serial: return
    try: subprocess.run([ADB, "connect", serial], capture_output=True, timeout=8, creationflags=NOWIN)
    except Exception: pass


_ADB_GONE = ("offline", "not found", "no devices", "unauthorized", "connection reset", "closed", "protocol fault")


def adb_ready(serial, wait=12.0):
    """Chờ adb thấy máy ở trạng thái "device". Máy vừa khởi động lại giao diện (cài app sẵn, đổi ảnh nền…) hoặc adb vừa nối lại
       → "offline" / "not found" vài giây: lệnh adb chạy lúc đó hỏng (push lỗi → chạm rơi xuống lệnh input chậm, hoặc mất hẳn).
       Quá nửa thời gian vẫn chưa được → ngắt + nối lại 1 lần (adb TCP hay kẹt "offline"). True = sẵn sàng."""
    if SELFTEST: return True
    t0 = time.time(); kicked = False
    while True:
        adb_connect(serial)
        code, out, _ = adb(serial, "get-state", timeout=5)
        if code == 0 and out.strip() == "device": return True
        if code == -2: return True                         # không có chương trình adb → không kết luận "máy không thấy" (lệnh sau tự báo lỗi thật)
        if time.time() - t0 >= wait: return False
        if not kicked and ":" in serial and time.time() - t0 > wait / 2:
            kicked = True
            try: subprocess.run([ADB, "disconnect", serial], capture_output=True, timeout=8, creationflags=NOWIN)
            except Exception: pass
        time.sleep(0.6)


def push_jar(serial):
    """Chép scrcpy-server vào máy (đã có đúng bản thì thôi). Máy đang "offline" → chờ adb sẵn sàng rồi thử lại 1 lần."""
    for i in range(2):
        code, out, err = adb(serial, "shell", "ls", "-l", JAR_DEV, timeout=10)
        if code == 0 and str(os.path.getsize(JAR)) in out: return
        if code == 0 or not any(w in (err or out).lower() for w in _ADB_GONE):
            code, out, err = adb(serial, "push", JAR, JAR_DEV, timeout=60)
            if code == 0: return
        gone = any(w in (err or out).lower() for w in _ADB_GONE)
        if i == 0 and gone and adb_ready(serial, 12): continue
        raise (AdbGone if gone else RuntimeError)("push: " + (err or out).strip()[-200:])


_CBV = {"ok": None, "t": 0.0, "lock": threading.Lock()}
_CBV_BAD = {}                                     # serial → lúc hết "cbvideo lỗi ở máy này" (dùng scrcpy tới lúc đó)


def _md5_file(fp):
    try:
        with open(fp, "rb") as f: return hashlib.md5(f.read()).hexdigest()
    except OSError: return ""


def ensure_cbv():
    """27/11f: windows/cbvideo.jar trên máy chủ (tải từ GitHub nếu thiếu / sai md5 — md5 ghim ở CBV_FILE). True = dùng được.
       Tải hỏng → 10 phút sau mới thử lại (Android 9 tạm dùng scrcpy như cũ)."""
    if not A9_CBV or len(CBV_FILE[1]) != 32: return False
    fn, want = CBV_FILE; fp = os.path.join(RTC, fn)
    if _CBV["ok"] and os.path.isfile(fp): return True
    with _CBV["lock"]:
        if _md5_file(fp) == want: _CBV["ok"] = True; return True
        if _CBV["ok"] is False and time.time() - _CBV["t"] < 600: return False
        _CBV["t"] = time.time()
        for url, hdr in ((CBV_API + fn, {"Accept": "application/vnd.github.raw", "User-Agent": "BlueRoblox"}),
                         (CBV_RAW + fn + f"?t={int(time.time())}", {"User-Agent": "BlueRoblox", "Cache-Control": "no-cache"})):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60) as r: d = r.read()
                if hashlib.md5(d).hexdigest() == want:
                    with open(fp + ".tmp", "wb") as f: f.write(d)
                    os.replace(fp + ".tmp", fp); _CBV["ok"] = True
                    log(f"cbvideo: đã tải {fn} ({len(d)} byte) — máy Android 9 lấy hình bằng cbvideo")
                    return True
            except Exception: pass
        _CBV["ok"] = False
        log(f"cbvideo: chưa tải được {fn} đúng bản (md5 {want[:8]}…) → Android 9 tạm lấy hình bằng scrcpy, 10 phút sau thử lại")
        return False


def push_cbv(serial):
    """Chép cbvideo.jar vào máy (tên file có md5 → đúng bản thì thôi). Máy "offline" → chờ adb rồi thử lại 1 lần."""
    fp = os.path.join(RTC, CBV_FILE[0])
    for i in range(2):
        code, out, err = adb(serial, "shell", "ls", "-l", CBV_DEV, timeout=10)
        if code == 0 and str(os.path.getsize(fp)) in out: return
        if code == 0 or not any(w in (err or out).lower() for w in _ADB_GONE):
            code, out, err = adb(serial, "push", fp, CBV_DEV, timeout=60)
            if code == 0: return
        gone = any(w in (err or out).lower() for w in _ADB_GONE)
        if i == 0 and gone and adb_ready(serial, 12): continue
        raise (AdbGone if gone else RuntimeError)("push cbvideo: " + (err or out).strip()[-200:])


def cbv_ok_for(serial):
    """Máy này có nên lấy hình bằng cbvideo không (bật trong conf + chưa bị đánh dấu lỗi gần đây)."""
    return A9_CBV and _CBV_BAD.get(serial, 0) < time.time()


def _recv_exact(s, n):
    b = bytearray()
    while len(b) < n:
        x = s.recv(n - len(b))
        if not x: raise EOFError
        b += x
    return bytes(b)


class _Bits:
    def __init__(self, b): self.b, self.i = b, 0
    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.i >> 3] >> (7 - (self.i & 7))) & 1); self.i += 1
        return v
    def ue(self):
        z = 0
        while self.u(1) == 0:
            z += 1
            if z > 31: raise ValueError("ue")
        return (1 << z) - 1 + (self.u(z) if z else 0)
    def se(self):
        k = self.ue(); return (k + 1) // 2 if k & 1 else -(k // 2)


def _sps_dims(cfg):
    """(rộng, cao) của hình đọc từ SPS H.264 trong gói cấu hình Annex-B. Không đọc được → None."""
    try:
        sps = next((n.rstrip(b"\x00") for n in re.split(b"\x00\x00\x01", cfg) if n and (n[0] & 0x1F) == 7), None)
        if not sps: return None
        rb = bytearray(); z = 0
        for x in sps[1:]:                                    # bỏ byte chống giả mã bắt đầu (00 00 03)
            if z >= 2 and x == 3: z = 0; continue
            rb.append(x); z = z + 1 if x == 0 else 0
        r = _Bits(bytes(rb)); prof = r.u(8); r.u(16); r.ue(); cf = 1
        if prof in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
            cf = r.ue()
            if cf == 3: r.u(1)
            r.ue(); r.ue(); r.u(1)
            if r.u(1):
                for k in range(8 if cf != 3 else 12):
                    if r.u(1):
                        last = nxt = 8
                        for _ in range(16 if k < 6 else 64):
                            if nxt: nxt = (last + r.se() + 256) % 256
                            last = nxt or last
        r.ue(); t = r.ue()
        if t == 0: r.ue()
        elif t == 1:
            r.u(1); r.se(); r.se()
            for _ in range(r.ue()): r.se()
        r.ue(); r.u(1)
        wm, hm = r.ue() + 1, r.ue() + 1; fmo = r.u(1)
        if not fmo: r.u(1)
        r.u(1)
        w, h = wm * 16, (2 - fmo) * hm * 16
        if r.u(1):
            cl, cr, ct, cb = r.ue(), r.ue(), r.ue(), r.ue()
            cx = 1 if cf in (0, 3) else 2; cy = (2 if cf == 1 else 1) * (2 - fmo)
            w -= (cl + cr) * cx; h -= (ct + cb) * cy
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


class ScrcpySource:
    """Nguồn hình "ảo" khi lấy hình thẳng từ Android: không quay cửa sổ, chỉ giữ kích thước màn hình máy (wm size → độ phân giải đã mua)."""
    def __init__(self, serial, res=None):
        self.serial = serial; self.res = res; self.cw = self.ch = 0; self.closed = False; self.stopping = False

    def open(self):
        adb_connect(self.serial)
        sz = device_size(self.serial)
        if not sz:
            time.sleep(1); adb_connect(self.serial); sz = device_size(self.serial)
        if not sz:
            m = re.match(r"^\s*(\d{3,4})\s*x\s*(\d{3,4})\s*$", str(self.res or ""))
            sz = (int(m.group(1)), int(m.group(2))) if m else None
        self.cw, self.ch = sz or (720, 1280)
        return self.cw, self.ch

    def resized(self): return False
    def stop(self): self.stopping = True


# ---------- 16/11k: HÌNH VỠ / NHIỄU MÀU khi đổi FPS ----------
# Khách đổi FPS (máy chạy 60–120 khung) mà xem bằng iPhone (xin 30) → bộ nén trong máy ảo bỏ qua giới hạn khung → máy chủ tưởng mạng
# yếu, hạ bậc độ phân giải → scrcpy ra cỡ 360x640 / 536x960 … (cạnh KHÔNG chia hết 16). Bộ nén trong máy ảo + bộ giải mã iPhone
# (VideoToolbox) dễ ra hình nhiễu màu / sọc ngang với cỡ lẻ như vậy. Giờ: (1) max_size cho scrcpy chọn sao cho CẢ HAI cạnh chia hết 16
# (lệch tỉ lệ < 2%) · (2) bộ nén chia 1 khung thành nhiều gói (nhiều lát) → ghép lại đủ khung rồi mới gửi (trước: gửi từng lát như 1
# khung → app giải mã khung thiếu → sọc / nhiễu; còn bị đếm gấp đôi khung → tưởng Android gửi thừa khung → hạ độ phân giải oan)
# · (3) bộ scrcpy cũ được dọn hẳn trong máy khi bật bộ mới. Tắt (1): STREAM_ALIGN16=0 · tắt (2): STREAM_SLICE_JOIN=0.
SCR_ALIGN = 8 if str(C.get("STREAM_ALIGN16", "1")).strip() == "0" else 16
SLICE_JOIN = str(C.get("STREAM_SLICE_JOIN", "1")).strip() != "0"
SLICE_WAIT = 0.03                         # giây chờ lát tiếp theo của khung đang ghép (chỉ khi chưa biết khung có mấy lát)
SLICE_WAIT_MAX = 0.25                     # đã TIN cách chia lát mà khung còn thiếu lát → chờ lát kế tối đa chừng này giây (17/11e: 0,12 rồi gửi khung
                                          # thiếu; 17/11f: 0,25 rồi BỎ khung — máy ảo khựng dưới 0,25 giây giữa khung không còn làm vỡ / đứng hình)
_SLICE_SAID = set()
# 17/11f — HÌNH VẪN VỠ trên nhiều máy (admin báo 23:01 17/11). Bản 16/11k / 17/11e còn 3 lỗ:
#   (a) cách chia lát chỉ nhớ trong 1 lần chạy bộ nén → mỗi lần bộ nén bật lại (đổi chất lượng, mạng yếu, xoay máy…) KHUNG ĐẦU bị gửi
#       thiếu lát → hình vỡ tới khung khoá kế;
#   (b) "cách chia lát" học từ BẤT KỲ khung nào, kể cả khung bị gửi thiếu do hết giờ chờ → học sai 1 lần là MỌI khung sau bị cắt cụt
#       (hình vỡ mãi, không tự hết);
#   (c) hết giờ chờ mà khung còn thiếu lát vẫn gửi → app giải mã khung thiếu → nhiễu màu.
# Giờ: chỉ học cách chia lát từ khung CHẮC CHẮN đủ (gói đầu của khung kế đã tới), lặp lại SLICE_CONFIRM khung liền mới tin; nhớ theo
# (máy, cỡ hình) qua các lần bật lại bộ nén; hết giờ chờ mà thiếu lát cuối theo cách chia đã tin → KHÔNG gửi (báo phiên xem chờ khung khoá
# kế — đứng hình ≤ ~1 giây thay vì hình vỡ); bộ nén chia lát không cố định (số lát đổi theo nội dung) → nhận ra và thôi gửi sớm theo cách
# chia; khung ĐẦU của mỗi lần bật bộ nén được giữ lại 1 nhịp xem có lát kế không.
SLICE_WAIT_NEW = 0.06                     # chưa biết cách chia lát: chờ lát kế tối đa chừng này giây rồi mới coi khung là đủ
SLICE_CONFIRM = 3                         # cách chia lát lặp lại ngần này khung liền mới tin (gửi sớm khi đủ lát)
SLICE_CONFIRM_VAR = 30                    # bộ nén từng đổi cách chia giữa chừng → phải lặp lại ngần này khung liền mới tin lại
SLICE_CUT_RUN = 3                         # ngần này khung liền bị coi là "thiếu lát" → cách chia đã đổi → học lại (không đứng hình mãi)
_SLICE_MEM = {}                           # (máy, rộng, cao) → {"multi", "layout", "var", "t"}: nhớ qua các lần bật lại bộ nén + lần bật lại phát hình
_SLICE_CUT_SAID = {}
_SLICE_F = os.path.join(B, "redroid", "slice_mem.json")
_SLICE_DIRTY = [False]
def _slice_mem_get(serial, w, h):
    m = _SLICE_MEM.get((serial, int(w or 0), int(h or 0)))
    return m if m and time.time() - m.get("t", 0) < 6 * 3600 else None
def _slice_mem_put(serial, w, h, multi, layout, var=False):
    if not serial or not w or not h: return
    if len(_SLICE_MEM) > 4000: _SLICE_MEM.clear()
    _SLICE_MEM[(serial, int(w), int(h))] = {"multi": bool(multi), "layout": tuple(layout) if layout else None, "var": bool(var), "t": time.time()}
    _SLICE_DIRTY[0] = True
def _slice_mem_save():
    """Ghi cái đã nhớ ra redroid/slice_mem.json (phát hình bật lại không phải học lại → không có khung vỡ đầu tiên). Gọi 30 giây / lần."""
    if not _SLICE_DIRTY[0] or SELFTEST: return
    _SLICE_DIRTY[0] = False
    try:
        now = time.time()
        d = {f"{k[0]}|{k[1]}|{k[2]}": {"multi": v["multi"], "layout": list(v["layout"]) if v.get("layout") else None, "var": bool(v.get("var")), "t": v["t"]}
             for k, v in list(_SLICE_MEM.items()) if now - v.get("t", 0) < 6 * 3600}
        os.makedirs(os.path.dirname(_SLICE_F), exist_ok=True)
        with open(_SLICE_F + ".tmp", "w", encoding="utf-8") as f: json.dump(d, f)
        os.replace(_SLICE_F + ".tmp", _SLICE_F)
    except (OSError, TypeError, ValueError): pass
def _slice_mem_load():
    try:
        with open(_SLICE_F, encoding="utf-8") as f: d = json.load(f)
        now = time.time()
        for k, v in d.items():
            ser, w, h = k.rsplit("|", 2)
            if now - float(v.get("t") or 0) < 6 * 3600:
                _SLICE_MEM[(ser, int(w), int(h))] = {"multi": bool(v.get("multi")), "layout": tuple(int(x) for x in v["layout"]) if v.get("layout") else None,
                                                     "var": bool(v.get("var")), "t": float(v["t"])}
    except Exception: pass
_slice_mem_load()


def _scr_out(nw, nh, m):
    """Cỡ hình scrcpy 2.4 sẽ phát cho màn nw×nh với max_size m (y như ScreenInfo.computeVideoSize của scrcpy)."""
    w, h = int(nw) & ~7, int(nh) & ~7
    if m > 0:
        portrait = h > w
        major, minor = (h, w) if portrait else (w, h)
        if major > m:
            minor = (minor * int(m) // major + 4) & ~7
            major = int(m)
        w, h = (minor, major) if portrait else (major, minor)
    return w, h


def _scr_max(nw, nh, want):
    """max_size cho scrcpy: LỚN NHẤT ≤ want mà hình ra có CẢ HAI cạnh chia hết 16 (không có thì trả want như cũ)."""
    try: nw, nh, want = int(nw), int(nh), int(want)
    except (TypeError, ValueError): return want
    if SCR_ALIGN <= 8 or nw <= 0 or nh <= 0: return want
    major = max(nw, nh) & ~7
    top = major if want <= 0 or want >= major else want
    if top >= major:
        w, h = _scr_out(nw, nh, 0)
        if w % 16 == 0 and h % 16 == 0: return want
        top = major - 1
    m = top & ~15
    while m >= max(160, int(top * 0.8)):
        w, h = _scr_out(nw, nh, m)
        if w % 16 == 0 and h % 16 == 0 and abs(w / h - nw / nh) <= 0.02 * (nw / nh): return m
        m -= 16
    return want


def _first_mb(au):
    """first_mb_in_slice của lát hình ĐẦU TIÊN trong gói Annex-B: 0 = đầu khung · > 0 = lát tiếp theo của khung trước · None = không có lát."""
    try:
        i = 0; n = len(au)
        while True:
            j = au.find(b"\x00\x00\x01", i)
            if j < 0 or j + 4 >= n: return None
            if au[j + 3] & 0x1F in (1, 5):
                raw = au[j + 4:j + 16]; rb = bytearray(); z = 0
                for x in raw:                                    # bỏ byte chống giả mã (00 00 03)
                    if z >= 2 and x == 3: z = 0; continue
                    rb.append(x); z = z + 1 if x == 0 else 0
                return _Bits(bytes(rb)).ue()
            i = j + 3
    except Exception:
        return None


class ScrcpyVideo:
    """Hình lấy THẲNG từ Android: scrcpy-server 2.4 (video=true, control=false) mã hoá H.264 ngay trong máy → từng khung Annex-B → on_au.
       Dùng khi Windows không quay được cửa sổ giả lập (Windows 10 trước 1903: PrintWindow chỉ ra màn ĐEN với MEmu).
       Cùng giao diện với Encoder (start / stop / proc / enc / failed_early). Khung khoá mỗi ~1 giây; máy xoay → on_size(rộng, cao)."""
    def __init__(self, serial, max_size, fps, kbps, on_au, on_size=None, iframe=1.0, quick=False, ready_wait=12.0, kind="scrcpy"):
        self.serial, self.max_size, self.fps, self.kbps, self.on_au, self.on_size = serial, int(max_size), int(fps), int(kbps), on_au, on_size
        self.quick, self.ready_wait = bool(quick), float(ready_wait)   # quick: phiên này vừa chạy scrcpy tốt → bật lại khỏi hỏi adb / kiểm file (đỡ ~0,3 giây đứng hình)
        try: self.iframe = max(0.1, min(5.0, float(iframe)))
        except (TypeError, ValueError): self.iframe = 1.0
        self.kind = "cbv" if kind == "cbv" else "scrcpy"                 # 27/11f: "cbv" = cbvideo.jar (Android 9) — cùng giao thức, khác chương trình trong máy
        self.enc = "cbvideo" if self.kind == "cbv" else "scrcpy"; self.proc = None; self.sock = None; self.fport = None; self.stopped = False
        self.lock = threading.Lock(); self.w = self.h = 0; self.frames_in = 0; self.started = 0.0
        self.scid = 0; self.pk_in = 0; self.cont_in = 0; self.multi = False; self.layout = None   # 16/11k: gói / lát tiếp theo / khung nhiều lát
        self.cut_in = 0; self._lay_c = None; self._lay_n = 0; self._cut_run = 0                  # 17/11f: khung thiếu lát đã bỏ · cách chia đang kiểm
        self._prev = ""; self._mem_t = 0.0; self._var = False; self._cut_to = False              # khung trước: "emit" đã gửi · "cut" đã bỏ · chia lát không cố định

    def start(self):
        """Bật scrcpy-server + nối socket hình → (rộng, cao) THẬT của hình. Lỗi → RuntimeError."""
        self.started = time.time()
        if not self.quick:
            if self.ready_wait > 0 and not adb_ready(self.serial, self.ready_wait): raise AdbGone(f"adb không thấy máy {self.serial}")
            if self.kind == "cbv":
                if not ensure_cbv(): raise RuntimeError("thiếu cbvideo.jar")
                push_cbv(self.serial)
            else:
                if not ensure_jar(): raise RuntimeError("thiếu scrcpy-server")
                push_jar(self.serial)
        scid = random.randint(1, 0x7FFFFFFF); self.scid = scid
        if self.kind == "cbv":
            cmd = (f"CLASSPATH={CBV_DEV} app_process / com.cloudblue.A9Video scid={scid:08x} max_size={self.max_size} "
                   f"max_fps={self.fps} video_bit_rate={self.kbps * 1000} i_frame={self.iframe:g} stats={CBV_STATS}")
        else:
            cmd = (f"CLASSPATH={JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 scid={scid:08x} log_level=warn "
                   "video=true audio=false control=false tunnel_forward=true send_device_meta=false send_dummy_byte=true "
                   "send_codec_meta=true send_frame_meta=true cleanup=false power_on=false video_codec=h264 "
                   f"max_size={self.max_size} max_fps={self.fps} video_bit_rate={self.kbps * 1000} video_codec_options="
                   + ("i-frame-interval=1" if abs(self.iframe - 1.0) < 1e-6 else f"i-frame-interval:float={self.iframe:g}"))
        with self.lock:
            if self.stopped: raise RuntimeError("đã dừng")
            self.proc = subprocess.Popen([ADB, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=NOWIN)
        threading.Thread(target=self._srvlog, args=(self.proc,), daemon=True).start()
        code, out, err = adb(self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid:08x}", timeout=10)
        with self.lock: self.fport = int(out.strip()) if out.strip().isdigit() else None
        if not self.fport:
            self._kill()
            raise (AdbGone if any(w in (err or out).lower() for w in _ADB_GONE) else RuntimeError)("forward: " + (err or out)[-200:])
        t0 = time.time(); sock = None
        while time.time() - t0 < 10 and not self.stopped:
            if self.proc.poll() is not None: break               # máy chủ scrcpy thoát ngay (VD máy không có bộ mã hoá) → xem nhật ký [scrcpy …]
            try:
                s = socket.create_connection(("127.0.0.1", self.fport), timeout=2); s.settimeout(3)
                if s.recv(1) == b"\x00": sock = s; break
                s.close()
            except OSError: pass
            time.sleep(0.15)
        if not sock: self._kill(); raise RuntimeError(("cbvideo" if self.kind == "cbv" else "scrcpy") + " (hình) không nối được")
        return self.attach(sock)

    def attach(self, sock):
        """Đọc thông tin hình (mã H.264 + rộng × cao) rồi chạy luồng đọc khung → (rộng, cao)."""
        try:
            sock.settimeout(10)
            codec, w, h = struct.unpack(">III", _recv_exact(sock, 12))
            if codec != 0x68323634: raise RuntimeError(f"scrcpy gửi mã hình lạ {codec:#x}")
            sock.settimeout(None)
            try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError: pass
        except Exception:
            try: sock.close()
            except Exception: pass
            self._kill(); raise
        with self.lock: self.sock = sock; self.w, self.h = w, h
        m = _slice_mem_get(self.serial, w, h) if SLICE_JOIN else None        # 17/11f: máy này + cỡ hình này đã biết chia lát thế nào
        if m: self.multi = bool(m.get("multi")); self.layout = m.get("layout"); self._var = bool(m.get("var"))
        threading.Thread(target=self._reader, args=(sock,), daemon=True).start()
        return w, h

    def _srvlog(self, p):
        try:
            for ln in iter(p.stdout.readline, b""):
                t = ln.decode("utf-8", "replace").strip()
                if t and not self.stopped: log(f"  [{'cbvideo' if self.kind == 'cbv' else 'scrcpy hình'} {self.serial}] {t[:200]}")
        except Exception: pass

    def _emit(self, it, natural=False):
        """it = [dữ liệu, khung khoá?, có SPS/PPS?, pts, [các first_mb]] → gửi 1 khung. natural = khung kết thúc TỰ NHIÊN (gói đầu của khung
           kế đã tới → chắc chắn đủ lát): chỉ khung như vậy mới dùng để học cách chia lát, và phải lặp lại SLICE_CONFIRM khung liền mới tin
           (17/11f — trước: tin ngay khung đầu, kể cả khung bị gửi thiếu do hết giờ chờ → cắt cụt mọi khung sau)."""
        lay = tuple(it[4])
        if len(lay) > 1:
            if natural:
                if lay == self._lay_c: self._lay_n += 1
                else: self._lay_c, self._lay_n = lay, 1
                if self._lay_n >= (SLICE_CONFIRM_VAR if self._var else SLICE_CONFIRM) and self.layout != lay:
                    self.layout = lay; self._var = False; _slice_mem_put(self.serial, self.w, self.h, True, lay, False)
            if time.time() - self._mem_t > 600:                    # còn thấy khung nhiều lát → giữ cái đã nhớ (hết hạn 6 giờ sau lần thấy cuối)
                self._mem_t = time.time(); _slice_mem_put(self.serial, self.w, self.h, True, self.layout, self._var)
        else: self._lay_c, self._lay_n = None, 0
        self._cut_run = 0; self._prev = "emit"
        self.on_au(bytes(it[0]), it[1], it[2], it[3])

    def _unlearn(self, var=False):
        """Bỏ cách chia lát đã tin. var=True: bộ nén chia lát KHÔNG cố định (số lát đổi theo nội dung) → từ giờ không gửi sớm theo cách chia
           nữa, chỉ chốt khung khi khung kế tới / hết giờ chờ."""
        self.layout = None; self._lay_c = None; self._lay_n = 0; self._cut_run = 0
        if var: self._var = True
        _slice_mem_put(self.serial, self.w, self.h, self.multi, None, self._var)

    def _cut(self):
        """Khung thiếu lát / lát lẻ → KHÔNG gửi khung vỡ: báo phiên xem chờ khung khoá kế (đứng hình ≤ ~1 giây thay vì hình nhiễu)."""
        self.cut_in += 1; self._cut_run += 1; self._prev = "cut"
        now = time.time(); c = _SLICE_CUT_SAID.setdefault(self.serial, [0.0, 0]); c[1] += 1
        if now - c[0] > 300:
            log(f"  [hình {self.serial}] {c[1]} khung thiếu lát (máy ảo đang bận / bộ nén gửi dở) → KHÔNG gửi khung vỡ, chờ khung khoá kế")
            c[0] = now; c[1] = 0
        self.on_au(None, False, False, int(time.monotonic() * 1e6))

    def _flush(self, held, natural=False):
        """Chốt khung đang ghép. natural=True: gói đầu của khung kế (hoặc gói cấu hình) đã tới → khung chắc chắn đủ lát → gửi; khác cách
           chia đã tin = bộ nén chia lát không cố định → thôi tin. natural=False (hết giờ chờ): thiếu lát cuối theo cách chia ĐÃ TIN → bỏ."""
        lay = self.layout; got = tuple(held[4])
        if lay and got != lay:
            if not natural and got == lay[:len(got)] and self._cut_run + 1 < SLICE_CUT_RUN:
                self._cut(); self._cut_to = True; return          # bỏ vì hết giờ chờ: gói kế là KHUNG MỚI (không phải lát còn thiếu) = bỏ oan → thôi tin cách chia
            self._unlearn(var=True)
        self._emit(held, natural)

    def _reader(self, s):
        cfg = b""; held = None; first = SLICE_JOIN               # 17/11f: khung ĐẦU luôn giữ 1 nhịp (chưa biết bộ nén có chia lát không)
        try:
            while not self.stopped:
                if held is not None:                                 # đang ghép khung nhiều lát: chờ lát kế
                    lay = self.layout
                    hint = lay or self._lay_c                                   # cách chia đã tin, hoặc mới thấy ở khung trước (chưa tin) → chỉ dùng để CHỜ thêm
                    if hint and len(held[4]) < len(hint) and tuple(held[4]) == hint[:len(held[4])]:    # còn thiếu lát → chờ thêm (máy ảo bận)
                        w = max(SLICE_WAIT, SLICE_WAIT_MAX - (time.monotonic() - held[3] / 1e6))
                    else: w = SLICE_WAIT if lay else SLICE_WAIT_NEW
                    try: rd = select.select([s], [], [], w)[0]
                    except (OSError, ValueError): rd = [s]
                    if not rd: self._flush(held); held = None; continue
                pf, n = struct.unpack(">QI", _recv_exact(s, 12))
                data = _recv_exact(s, n)
                if pf & (1 << 63):                                   # gói cấu hình (SPS/PPS) → ghép trước mỗi khung khoá
                    if held is not None: self._flush(held, True); held = None
                    cfg = data
                    d = _sps_dims(cfg)
                    if d and d != (self.w, self.h):                  # máy xoay / đổi cỡ → báo app cỡ mới TRƯỚC khung khoá mới
                        self.w, self.h = d
                        m = _slice_mem_get(self.serial, d[0], d[1]) if SLICE_JOIN else None      # cỡ mới → cách chia lát của cỡ đó (chưa biết → học lại)
                        self.layout = m.get("layout") if m else None; self._var = bool(m and m.get("var"))
                        self._lay_c = None; self._lay_n = 0; self._cut_run = 0
                        if m and m.get("multi"): self.multi = True
                        if self.on_size: self.on_size(*d)
                    continue
                key = bool(pf & (1 << 62)); self.pk_in += 1
                fm = _first_mb(data) if SLICE_JOIN else None
                if fm:                                               # lát TIẾP THEO của cùng 1 khung (16/11k)
                    self.cont_in += 1
                    if not self.multi:
                        self.multi = True; _slice_mem_put(self.serial, self.w, self.h, True, None, self._var)
                        if self.serial not in _SLICE_SAID:
                            _SLICE_SAID.add(self.serial)
                            log(f"  [hình {self.serial}] bộ nén trong máy chia mỗi khung thành nhiều gói → ghép đủ khung rồi mới gửi (hết sọc / nhiễu)")
                    if held is not None:
                        if key and not held[1] and cfg: held[0][0:0] = cfg; held[2] = True      # cờ khung khoá nằm ở lát sau
                        held[0] += data; held[1] = held[1] or key; held[4].append(fm)
                        lay = self.layout
                        if lay:
                            got = tuple(held[4])
                            if got == lay: self._emit(held); held = None                       # đủ lát theo cách chia đã tin → gửi ngay
                            elif got != lay[:len(got)]: self._unlearn(var=True)                 # không khớp → chia lát không cố định, ghép tiếp theo giờ chờ
                        continue
                    if self.layout and self._prev == "emit": self._unlearn(var=True)     # vừa GỬI SỚM mà khung đó còn lát → cách chia đã tin là SAI
                    self._cut_to = False                             # lát còn thiếu tới thật (trễ) → lần bỏ khung vừa rồi là đúng
                    self._cut()                                      # lát lẻ của khung đã gửi / đã bỏ → chờ khung khoá kế
                    continue
                if held is not None: self._flush(held, True); held = None
                if self._cut_to:                                     # vừa bỏ 1 khung "thiếu lát" mà gói kế lại là khung MỚI → khung đó vốn đủ (bộ nén chia
                    self._cut_to = False; self._unlearn(var=True)    # lát không cố định) → thôi tin cách chia, không bỏ oan nữa
                self.frames_in += 1
                au = cfg + data if key and cfg else data; ts = int(time.monotonic() * 1e6)
                if self.multi or first: held = [bytearray(au), key, key and bool(cfg), ts, [0]]
                else: self.on_au(au, key, key and bool(cfg), ts)
                first = False
        except Exception:
            pass
        if held is not None and not self.stopped:
            try: self._flush(held)
            except Exception: pass
        if not self.stopped:
            log(f"  [hình {self.serial}] scrcpy ngừng gửi hình → bật lại")
            self._kill()                                             # tiến trình dừng → phiên xem tự bật lại hình

    def _kill(self):
        with self.lock:
            s, p, fp = self.sock, self.proc, self.fport
            self.sock = None; self.fport = None
        if p is not None and self.scid and not getattr(self, "_swept", False):   # 16/11k: dọn hẳn bộ scrcpy này TRONG máy (không để 2 bộ nén chạy chồng)
            self._swept = True
            threading.Thread(target=adb, args=(self.serial, "shell", f"pkill -f scid={self.scid:08x}"), kwargs={"timeout": 8}, daemon=True).start()
        try:
            if s: s.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        try:
            if s: s.close()
        except Exception: pass
        try:
            if p and p.poll() is None: p.kill()
        except Exception: pass
        if fp: threading.Thread(target=adb, args=(self.serial, "forward", "--remove", f"tcp:{fp}"), daemon=True).start()

    def stop(self):
        with self.lock: self.stopped = True
        self._kill()

    def failed_early(self): return False

    def request_key(self):
        """27/11f: cbvideo → xin khung IDR NGAY (1 byte 'K' qua socket hình; cbvideo gọi MediaCodec PARAMETER_KEY_REQUEST_SYNC_FRAME).
           scrcpy không có lệnh này → False (phiên tự bật lại bộ nén như cũ)."""
        if self.kind != "cbv": return False
        s = self.sock
        if not s: return False
        try: s.sendall(b"K"); return True
        except OSError: return False


# GIỮ CÚ BẤM (MẶC ĐỊNH TẮT): nhận "đặt ngón" → chờ tối đa TAP_HOLD giây xem có "nhấc ngón" không. Có → gửi đặt + nhấc
# LIỀN NHAU vào máy = 1 cú bấm chắc chắn (mạng khách giật làm lệnh "nhấc" tới trễ > 0,4 giây → Android hiểu là BẤM GIỮ).
# Kéo / vuốt (nhích quá TAP_SLOP điểm) thì gửi ngay; giữ yên quá TAP_HOLD thì gửi "đặt ngón".
# 09/11 17:45 TẮT mặc định: mọi "đặt ngón" đứng yên bị trễ tới lúc nhấc tay (tối đa TAP_HOLD) → chơi game trên điện thoại
# (nút nhảy, cần điều khiển Roblox) thấy trễ. Lỗi "bấm app không mở" hôm 09/11 thật ra do MuMu "giữ app chạy nền"
# (app_keptlive, xem phonectl.py), không phải do cú bấm. Muốn bật lại: TAP_HOLD_MS=250 trong cloudphone.conf.
try: TAP_HOLD = max(0.0, min(0.5, float(str(C.get("TAP_HOLD_MS", "0")).strip() or 0) / 1000.0))
except Exception: TAP_HOLD = 0.0
TAP_SLOP = 16        # điểm ảnh của máy (≈ 1,5 mm trên màn 1080p): nhích ít hơn vẫn tính là bấm
LATE_UP = 0.35       # nhả tay tới máy chủ trễ hơn mức này (không nhích) → đếm "chạm trễ" để báo trong nhật ký

# MÀN ẢO (Android 14/15, máy MuMu): mỗi luồng hình scrcpy là 1 màn hình ảo trong máy. Android có lúc mở app lên MÀN ẢO
# thay vì màn chính → khách bấm app chỉ thấy icon phóng to rồi thôi (app chạy trên màn không ai thấy, lỗi khách báo 09/11).
# Sau mỗi cú bấm (1,2 giây) + 15 giây/lần: app thường nào nằm ở màn khác #0 → đưa về màn chính. DISPLAY_FIX=0 để tắt.
DISPLAY_FIX = str(C.get("DISPLAY_FIX", "1")).strip().lower() not in ("0", "off", "false", "no")
_TASK_RE = re.compile(r"\s+\* Task\{\S+ #(\d+) type=standard A=\d+:(\S+)")


def fix_displays(serial):
    """App lỡ mở trên màn hình ảo → đưa về màn chính #0. Trả về [(gói, màn)] đã đưa về. Không bao giờ ném lỗi."""
    try:
        code, out, _ = adb(serial, "shell", "dumpsys activity activities | grep -e '^Display #' -e 'type=standard A=' -e '^ActivityTaskSupervisor'",
                           timeout=12)
        if code != 0 or not out: return []
        moved, disp = [], 0
        for ln in out.splitlines():
            if ln.startswith("ActivityTaskSupervisor"): break
            m = re.match(r"Display #(\d+)", ln)
            if m: disp = int(m.group(1)); continue
            m = _TASK_RE.match(ln)
            if m and disp != 0:
                adb(serial, "shell", f"am display move-stack {m.group(1)} 0", timeout=10)
                moved.append((m.group(2), disp))
        return moved
    except Exception:
        return []


class Control:
    """Chạm / phím / chữ → máy Android qua scrcpy-server 2.4 (chỉ điều khiển). Mọi lệnh đi qua 1 hàng đợi + 1 luồng gửi
       (không bao giờ chặn vòng chính), giữ đúng thứ tự; chữ có dấu dán qua bộ nhớ copy và chờ máy dán xong rồi mới gửi tiếp."""
    dfix = True                                             # 27/11e: canh "app mở nhầm màn ảo" (Android 9 không có lỗi này → tắt, đỡ dumpsys nặng sau mỗi cú bấm)

    def __init__(self, serial, on_clip, dfix=True):
        self.serial, self.on_clip, self.dfix = serial, on_clip, bool(dfix)
        self.sock = None; self.proc = None; self.fport = None; self.ready = threading.Event(); self.dead = False
        self.q = queue.Queue(maxsize=4000); self.lock = threading.Lock()
        self.nat = None; self.vw = self.vh = 0; self.mode = "scrcpy"; self.down = {}
        self.seq = 1; self.retrying = False; self.nat_t = 0.0
        self.tlock = threading.Lock(); self.held = {}; self.active = set(); self.hgen = 0      # cú bấm đang giữ chờ "nhấc ngón"
        self.n_tap = 0; self.n_late = 0; self.stat_t = time.time(); self.dpos = {}
        self.dfix_at = 0.0; self.dfix_busy = False                                              # đưa app từ màn ảo về màn chính
        self.miss_t = 0.0; self.miss_log = 0.0; self.n_miss = 0; self.miss_same = 0             # scrcpy bỏ cú chạm vì sai cỡ màn hình
        self.fg = ""; self.fg_t = 0.0                                                           # 17/11e: app đang mở (để dán vào Termux)

    # ---------- khởi động (luồng nền) ----------
    def start(self):
        threading.Thread(target=self._writer, daemon=True).start()
        if SELFTEST:
            self.mode = "none"; self.ready.set(); return
        if DISPLAY_FIX and self.dfix: threading.Thread(target=self._dfix_loop, daemon=True).start()
        try:
            adb_ready(self.serial, 12)                      # máy vừa "offline" (đang cài app sẵn / adb vừa nối lại) → chờ, đừng hỏng ngay
            self.nat = device_size(self.serial); self.nat_t = time.time()
            if self.dead: return self._cleanup()
            self._open_scrcpy()
            self.mode = "scrcpy"; self.ready.set()
        except Exception as e:
            if self.dead: return self._cleanup()
            log(f"  [điều khiển {self.serial}] scrcpy lỗi ({str(e).strip()[:160]}) → tạm dùng lệnh input, đang nối lại scrcpy…")
            self._cleanup(keep_queue=True); self.mode = "input"; self.ready.set()
            self._kick_retry()

    def _open_scrcpy(self):
        """Bật scrcpy-server 2.4 (chỉ điều khiển) trong máy + nối socket điều khiển. Lỗi → RuntimeError (phần dở dang: _cleanup)."""
        if not ensure_jar(): raise RuntimeError("thiếu scrcpy-server")
        push_jar(self.serial)
        if self.dead: raise RuntimeError("đã dừng")
        if True:
            scid = random.randint(1, 0x7FFFFFFF)
            cmd = (f"CLASSPATH={JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 scid={scid:08x} log_level=warn "
                   "video=false audio=false control=true tunnel_forward=true send_device_meta=false cleanup=false "
                   "clipboard_autosync=true power_on=false")
            with self.lock:
                if self.dead: raise RuntimeError("đã dừng")
                self.proc = subprocess.Popen([ADB, "-s", self.serial, "shell", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
            threading.Thread(target=self._srvlog, args=(self.proc,), daemon=True).start()
            code, out, err = adb(self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid:08x}", timeout=10)
            with self.lock: self.fport = int(out.strip()) if out.strip().isdigit() else None
            if self.dead: raise RuntimeError("đã dừng")
            if not self.fport: raise RuntimeError("forward: " + (err or out)[-200:])
            t0 = time.time(); sock = None
            while time.time() - t0 < 8 and not self.dead:
                try:
                    s = socket.create_connection(("127.0.0.1", self.fport), timeout=2)
                    s.settimeout(3)
                    if s.recv(1) == b"\x00":
                        s.settimeout(3); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # gửi treo > 3 s → coi như hỏng
                        sock = s; break
                    s.close()
                except OSError:
                    pass
                time.sleep(0.15)
            if self.dead:
                if sock: sock.close()
                raise RuntimeError("đã dừng")
            if not sock: raise RuntimeError("scrcpy không nối được")
            with self.lock: self.sock = sock
            threading.Thread(target=self._reader, args=(sock,), daemon=True).start()

    def _kick_retry(self):
        """Đang chạm bằng lệnh input (chậm, adb hỏng là mất chạm) → luồng nền thử nối lại scrcpy cho tới khi được."""
        with self.lock:
            if self.retrying or self.dead: return
            self.retrying = True
        threading.Thread(target=self._retry_loop, daemon=True).start()

    def _retry_loop(self):
        delay = 2.0
        try:
            while not self.dead and self.mode == "input":
                time.sleep(delay); delay = min(delay * 2, 20.0)
                if self.dead: break
                try:
                    if not adb_ready(self.serial, 10): continue
                    if not self.nat: self.nat = device_size(self.serial); self.nat_t = time.time()
                    self._open_scrcpy()
                    if self.dead: break
                    with self.tlock: self.held.clear(); self.active.clear()
                    self.mode = "scrcpy"; self.down.clear()
                    log(f"  [điều khiển {self.serial}] đã nối lại scrcpy → chạm nhanh trở lại")
                    return
                except Exception:
                    self._cleanup(keep_queue=True)
        finally:
            with self.lock: self.retrying = False
            if self.dead: self._cleanup()

    def _srvlog(self, p):
        try:
            for ln in iter(p.stdout.readline, b""):
                s = ln.decode("utf-8", "replace").strip()
                if not s or self.dead: continue
                if "different device size" in s:             # "Ignore touch event, it was generated for a different device size"
                    self._size_miss(); continue
                log(f"  [scrcpy {self.serial}] {s[:200]}")
        except Exception: pass

    # scrcpy BỎ cú chạm khi cỡ màn hình gửi kèm ≠ cỡ máy đang có (máy đổi độ phân giải, wm size cũ trong bộ nhớ 10 phút, máy vừa
    # khởi động…) → khách bấm không ăn (log 09/11 win5 cổng 16864 lặp lại hàng loạt). Giờ: thấy cảnh báo đó → đo lại cỡ màn hình ngay.
    def _size_miss(self):
        self.n_miss += 1; now = time.time()
        if now - self.miss_t < 1.5: return
        self.miss_t = now
        threading.Thread(target=self._size_refresh, daemon=True).start()

    def _size_refresh(self):
        same = lambda a, b: bool(a) and bool(b) and sorted(a) == sorted(b)
        old = self.nat
        _devsize.pop(self.serial, None)
        try: n = device_size(self.serial)
        except Exception: n = None
        if not n or same(n, old):                                # wm size vẫn ra số cũ → hỏi cỡ màn hình đang hiện (dumpsys)
            try: n2 = device_size_cur(self.serial)
            except Exception: n2 = None
            if n2: n = n2
        if n: self.nat = n; self.nat_t = time.time()
        if n and not same(n, old):
            self.miss_same = 0
        else:
            self.miss_same += 1
            if self.miss_same >= 2 and self.mode == "scrcpy" and not self.dead:
                # cỡ đo lại vẫn thế mà scrcpy vẫn bỏ chạm → scrcpy trong máy còn nhớ cỡ CŨ (máy đổi độ phân giải lúc đang mở) → nối lại scrcpy
                self.miss_same = 0
                log(f"  [điều khiển {self.serial}] scrcpy vẫn bỏ cú chạm với cỡ {n} → nối lại scrcpy (tạm chạm bằng lệnh input)")
                self._cleanup(keep_queue=True); self.mode = "input"; self._kick_retry()
        if time.time() - self.miss_log > 60:
            self.miss_log = time.time()
            log(f"  [điều khiển {self.serial}] scrcpy bỏ {self.n_miss} cú chạm (sai cỡ màn hình) → đo lại: {old} → {self.nat}")
            self.n_miss = 0

    def _reader(self, s):
        def rd(n):
            b = b""
            while len(b) < n:
                try: x = s.recv(n - len(b))
                except socket.timeout: continue
                if not x: raise EOFError
                b += x
            return b
        try:
            while not self.dead:
                t = rd(1)[0]
                if t == 0:                       # máy vừa copy chữ → gửi về app
                    n = struct.unpack(">I", rd(4))[0]; txt = rd(n).decode("utf-8", "replace")
                    try: self.on_clip(txt)
                    except Exception: pass
                elif t == 1: rd(8)               # xác nhận đã đặt bộ nhớ copy
                elif t == 2:                     # uhid output
                    rd(2); n = struct.unpack(">H", rd(2))[0]; rd(n)
                else: break
        except Exception:
            pass

    def _cleanup(self, keep_queue=False):
        """Dọn scrcpy-server + adb forward + socket ĐANG có (gọi nhiều lần không sao)."""
        with self.lock:
            s, p, fp = self.sock, self.proc, self.fport
            self.sock = None; self.proc = None; self.fport = None
        try:
            if s: s.close()
        except Exception: pass
        try:
            if p and p.poll() is None: p.kill()
        except Exception: pass
        if fp: threading.Thread(target=adb, args=(self.serial, "forward", "--remove", f"tcp:{fp}"), daemon=True).start()

    def stop(self):
        self.dead = True; self.ready.set()
        try: self.q.put_nowait(None)
        except queue.Full: pass
        self._cleanup()

    # ---------- luồng gửi ----------
    def _writer(self):
        carry = None
        while not self.dead:
            it = carry if carry is not None else self.q.get()
            carry = None
            if it is None or self.dead: break
            self.ready.wait()
            if self.dead: break
            kind, val = it
            if kind == "paste":                              # gom chữ gõ liên tiếp trong 40 ms → 1 lần dán
                text = val; t_end = time.time() + 0.04
                while True:
                    try: nx = self.q.get(timeout=max(0.0, t_end - time.time()))
                    except queue.Empty: break
                    if nx is not None and nx[0] == "paste": text += nx[1]; continue
                    carry = nx; break
                b = text.encode("utf-8")[:200000]; self.seq += 1
                pkg = self._fg_pkg() if PASTE_TERMUX else ""
                if pkg and self._cav_app(pkg):                   # 17/11e: Termux bỏ qua phím PASTE → đặt bộ nhớ copy rồi Ctrl+Alt+V (dán của Termux)
                    self._raw(struct.pack(">BqBI", 9, self.seq, 0, len(b)) + b)
                    time.sleep(0.12)
                    self._raw(self._cav_pkt(0) + self._cav_pkt(1))
                    if self.serial not in _CAV_SAID:
                        _CAV_SAID.add(self.serial); log(f"  [điều khiển {self.serial}] dán vào {pkg} bằng Ctrl+Alt+V (app này bỏ qua phím PASTE)")
                else:
                    self._raw(struct.pack(">BqBI", 9, self.seq, 1, len(b)) + b)
                time.sleep(0.15)                             # chờ app trong máy dán xong (dán là bất đồng bộ) rồi mới gửi lệnh sau
            elif kind == "raw":
                self._raw(val)
            elif kind == "shell":
                cmd, t0 = val if isinstance(val, tuple) else (val, 0.0)
                if t0 and cmd.startswith("input ") and time.time() - t0 > 4: continue      # chạm đã cũ (adb kẹt) → bỏ, khỏi bấm nhầm muộn
                adb(self.serial, "shell", cmd, timeout=8 if cmd.startswith("input ") else 15)

    # ---------- 17/11e: dán vào app dòng lệnh (Termux) ----------
    def _fg_pkg(self):
        """Gói app đang hiện trên màn máy ('' = không đọc được). Nhớ 2 giây (dán liên tiếp khỏi hỏi lại). Chỉ gọi từ luồng gửi."""
        now = time.time()
        if now - self.fg_t < 2.0: return self.fg
        pkg = ""
        try:
            rc, out, _ = adb(self.serial, "shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'", timeout=4)
            if rc == 0:
                for key in ("mCurrentFocus", "mFocusedApp"):          # cửa sổ đang nhận phím trước; popup / bàn phím → app đang mở
                    for ln in (out or "").splitlines():
                        if key in ln:
                            m = _FG_RE.search(ln)
                            if m: pkg = m.group(1); break
                    if pkg: break
        except Exception:
            pkg = ""
        self.fg, self.fg_t = pkg, time.time()
        return pkg

    @staticmethod
    def _cav_app(pkg):
        """App dán bằng Ctrl+Alt+V (Termux + bản Termux khác tên gói con) thay cho phím PASTE."""
        return any(pkg == p or pkg.startswith(p + ".") for p in PASTE_CAV_PKGS)

    @staticmethod
    def _cav_pkt(action):
        # phím V (50) kèm Ctrl + Alt bên trái: META_CTRL_ON | META_CTRL_LEFT_ON | META_ALT_ON | META_ALT_LEFT_ON
        return struct.pack(">BBiii", 0, action, 50, 0, 0x1000 | 0x2000 | 0x02 | 0x10)

    def _raw(self, b):
        s = self.sock
        if not s or self.mode != "scrcpy": return
        try: s.sendall(b)
        except OSError:
            log(f"  [điều khiển {self.serial}] mất kết nối scrcpy → tạm dùng lệnh input, đang nối lại scrcpy…")
            self._cleanup(keep_queue=True); self.mode = "input"; self._kick_retry()

    def _put(self, kind, val):
        try: self.q.put_nowait((kind, val))
        except queue.Full: pass

    def _send(self, b):
        if self.mode in ("scrcpy",) or not self.ready.is_set(): self._put("raw", b)

    def _shell(self, c): self._put("shell", (c, time.time()))

    # ---------- toạ độ ----------
    def set_view(self, vw, vh):
        self.vw, self.vh = vw, vh

    def screen(self):
        """Kích thước màn hình máy theo hướng HIỆN TẠI (đoán hướng theo tỉ lệ hình đang quay) — scrcpy đòi đúng số này."""
        vw, vh = self.vw or 720, self.vh or 1280
        if not self.nat and time.time() - self.nat_t > 3 and not SELFTEST:
            self.nat_t = time.time(); threading.Thread(target=self._nat_bg, daemon=True).start()
        w, h = self.nat if self.nat and min(self.nat) > 0 else (vw, vh)
        if (vw > vh) != (w > h): w, h = h, w
        return w & ~7, h & ~7

    # ---------- app mở nhầm lên màn ảo → đưa về màn chính ----------
    def _dfix_run(self, delay=0.0):
        try:
            if delay: time.sleep(delay)
            if self.dead: return
            self.dfix_at = time.time()
            for pkg, disp in fix_displays(self.serial):
                log(f"  [điều khiển {self.serial}] app {pkg} mở nhầm trên màn ảo #{disp} → đã đưa về màn chính")
        finally:
            self.dfix_busy = False

    def _dfix_soon(self):
        """Sau cú bấm: 1,2 giây sau xem app vừa mở có nằm nhầm màn ảo không (tối đa 1 lần / 2 giây)."""
        if not DISPLAY_FIX or not self.dfix or SELFTEST or self.dead or self.dfix_busy or time.time() - self.dfix_at < 2: return
        self.dfix_busy = True
        threading.Thread(target=self._dfix_run, args=(1.2,), daemon=True).start()

    def _dfix_loop(self):
        time.sleep(3)
        while not self.dead:
            if not self.dfix_busy and time.time() - self.dfix_at >= 14:
                self.dfix_busy = True; self._dfix_run()
            time.sleep(15)

    def _nat_bg(self):
        """Hỏi cỡ màn hình máy ở luồng nền (adb chậm / chập chờn không làm đứng phiên xem)."""
        try:
            n = device_size(self.serial)
            if n: self.nat = n
        except Exception: pass

    def _xy(self, nx, ny):
        w, h = self.screen()
        return min(w - 1, max(0, int(nx * w / 65536))), min(h - 1, max(0, int(ny * h / 65536))), w, h

    # ---------- lệnh ----------
    def touch(self, action, pointer, nx, ny):
        x, y, w, h = self._xy(nx, ny)
        if action == 3: action = 1
        if action == 1: self._dfix_soon()
        if self.mode == "input":
            if action == 0: self.down[pointer] = (x, y, time.time())
            elif action == 1 and pointer in self.down:
                x0, y0, t0 = self.down.pop(pointer)
                dur = int((time.time() - t0) * 1000)
                still = abs(x - x0) + abs(y - y0) < TAP_SLOP
                self._count(still, dur / 1000.0)
                if still and dur < 400 + TAP_HOLD * 1000: self._shell(f"input tap {x} {y}")      # nhả tay tới trễ vì mạng → vẫn là bấm
                else: self._shell(f"input swipe {x0} {y0} {x} {y} {max(80, min(dur, 1500))}")
            return
        if action == 0: self.dpos[pointer] = (x, y, time.monotonic())
        elif action == 1:
            d = self.dpos.pop(pointer, None)
            if d: self._count(abs(x - d[0]) + abs(y - d[1]) <= TAP_SLOP, time.monotonic() - d[2])
        pkt = self._pkt(action, pointer, x, y, w, h)
        if not TAP_HOLD:
            self._send(pkt); return
        with self.tlock:
            hd = self.held.get(pointer)
            if action == 0:
                if hd: self.held.pop(pointer, None); self.active.add(pointer); self._send(hd["pkt"])
                if self.held or self.active:                 # đang có ngón khác (đa điểm, chơi game) → gửi ngay, không giữ
                    self._flush_held()
                    self.active.add(pointer); self._send(pkt); return
                self.hgen += 1; g = self.hgen
                self.held[pointer] = {"pkt": pkt, "x": x, "y": y, "g": g, "t": time.monotonic()}
                t = threading.Timer(TAP_HOLD, self._hold_due, args=(pointer, g)); t.daemon = True; t.start()
                return
            if hd:
                moved = abs(x - hd["x"]) + abs(y - hd["y"]) > TAP_SLOP
                if action == 2:
                    if not moved: return                     # nhích nhẹ lúc bấm → bỏ qua, vẫn là "bấm"
                    self.held.pop(pointer, None); self.active.add(pointer)
                    self._send(hd["pkt"] + pkt); return      # bắt đầu kéo → gửi "đặt ngón" + "kéo" ngay
                self.held.pop(pointer, None)                 # NHẤC NGÓN khi "đặt ngón" còn đang giữ → gửi liền nhau = 1 cú bấm
                if moved: self._send(hd["pkt"] + self._pkt(2, pointer, x, y, w, h) + pkt)      # vuốt nhanh không kịp có lệnh kéo
                else: self._send(hd["pkt"] + self._pkt(1, pointer, hd["x"], hd["y"], w, h))   # nhả đúng chỗ bấm
                return
            if action == 1:
                self.active.discard(pointer)
            self._send(pkt)

    @staticmethod
    def _pkt(action, pointer, x, y, w, h):
        return struct.pack(">BBqiiHHHii", 2, action, pointer, x, y, w, h, 0 if action == 1 else 0xFFFF, 0, 0)

    def _flush_held(self):
        """(đang giữ self.tlock) gửi ngay mọi "đặt ngón" còn giữ — đúng thứ tự trước lệnh mới."""
        for p, hd in list(self.held.items()):
            self.held.pop(p, None); self.active.add(p); self._send(hd["pkt"])

    def _hold_due(self, pointer, g):
        """Giữ yên quá TAP_HOLD mà chưa nhấc → khách đang BẤM GIỮ thật → gửi "đặt ngón"."""
        with self.tlock:
            hd = self.held.get(pointer)
            if not hd or hd["g"] != g or self.dead: return
            self.held.pop(pointer, None); self.active.add(pointer); self._send(hd["pkt"])

    def _count(self, still, gap):
        """Đếm cú bấm + số lần "nhả tay" tới máy chủ trễ (mạng khách giật) → 5 phút ghi nhật ký 1 lần nếu có."""
        if not still: return
        self.n_tap += 1
        if gap >= LATE_UP: self.n_late += 1
        if time.time() - self.stat_t >= 300:
            if self.n_late:
                log(f"  [điều khiển {self.serial}] 5 phút qua: {self.n_tap} cú bấm, {self.n_late} lần lệnh nhả tay tới máy chủ trễ ≥ {LATE_UP:.2f} giây "
                    f"(mạng khách giật) · {f'giữ cú bấm {int(TAP_HOLD * 1000)} ms' if TAP_HOLD else 'không giữ cú bấm'}")
            self.n_tap = self.n_late = 0; self.stat_t = time.time()

    def scroll(self, nx, ny, hv, vv):
        x, y, w, h = self._xy(nx, ny)
        if self.held:
            with self.tlock: self._flush_held()
        f = lambda v: max(-0x8000, min(0x7FFF, int(max(-1.0, min(1.0, v / 120.0)) * 0x8000)))
        if self.mode == "input":
            if vv: self._shell(f"input swipe {x} {y} {x} {max(0, min(h - 1, y + (300 if vv > 0 else -300)))} 120")
            return
        self._send(struct.pack(">BiiHHhhi", 3, x, y, w, h, f(hv), f(vv), 0))

    def key(self, action, code, meta=0):
        if self.mode == "input":
            if action == 0: self._shell(f"input keyevent {int(code)}")
            return
        self._send(struct.pack(">BBiii", 0, action, int(code), 0, int(meta)))

    def press(self, code):
        if self.mode == "input": self._shell(f"input keyevent {int(code)}"); return
        self.key(0, code); self.key(1, code)

    def text(self, s):
        if not s: return
        if self.mode != "input" and any(ord(ch) > 126 or (ord(ch) < 32 and ch not in "\n\t") for ch in s):
            self._put("paste", s); return                   # chữ có dấu (tiếng Việt…): scrcpy không gõ được → dán qua bộ nhớ copy
        if self.mode == "input":
            safe = re.sub(r"([\\\"'`$&|;<>()* ])", r"\\\1", s.replace("%", "\\%")).replace(" ", "%s")
            self._shell(f"input text {safe}"); return
        b = s.encode("utf-8")
        while b:
            cut = min(len(b), 300)
            part, b = b[:cut], b[cut:]
            self._send(struct.pack(">BI", 1, len(part)) + part)

    def clip_set(self, s, paste):
        if self.mode == "input": self.text(s); return
        if paste: self._put("paste", s); return
        b = s.encode("utf-8")[:200000]; self.seq += 1
        self._send(struct.pack(">BqBI", 9, self.seq, 0, len(b)) + b)

    def rotate(self, to=None):
        """Xoay màn máy: to = "land" (ngang) | "port" (dọc); không ghi → đổi sang hướng kia của hình đang phát.
           Khoá hướng bằng cài đặt Android (tắt tự xoay + user_rotation). Lệnh xoay của scrcpy chỉ đổi rồi TRẢ LẠI hướng cũ
           khi máy đang bật tự xoay → khách bấm "Xoay" mà máy đứng im."""
        if to not in ("land", "port"): to = "port" if (self.vw or 0) > (self.vh or 0) else "land"
        r = 1 if to == "land" else 0
        self._shell(f"settings put system accelerometer_rotation 0; settings put system user_rotation {r}; wm user-rotation lock {r} >/dev/null 2>&1")

    def notif(self):
        if self.mode != "input": self._send(bytes([5]))
        else: self._shell("cmd statusbar expand-notifications")


# ================================================================ Đường truyền: TLS trực tiếp / WebSocket
def _small_buffers(writer):
    """Bộ đệm gửi NHỎ: mạng khách chậm → lộ ra ngay ở máy chủ để BỎ KHUNG, thay vì dồn hàng giây hình cũ trong bộ đệm (trễ dần)."""
    try: writer.transport.set_write_buffer_limits(high=64 * 1024, low=16 * 1024)
    except Exception: pass
    try:
        s = writer.get_extra_info("socket")
        if s is not None:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 128 * 1024)
    except Exception: pass


class Link:
    kind = "?"
    closed = False
    welcomed = False                   # đã gửi WELCOME (hello_keepalive thôi gửi PONG giữ chỗ)
    async def recv(self): raise NotImplementedError
    def write(self, t, payload=b""): raise NotImplementedError

    def dead(self):
        """App / trình duyệt đã ngắt (kết nối đang đóng) — 13/11d: thôi ghi ngay, kết thúc phiên."""
        if self.closed: return True
        try: return bool(self.w.is_closing())
        except AttributeError: return False                 # kiểu kết nối không có is_closing → coi như còn sống (như trước 13/11d)
        except Exception: return True

    async def send(self, t, payload=b"", timeout=5.0):
        """Gửi + chờ mạng nhận bớt (tối đa `timeout` giây — app treo/không đọc → báo lỗi để đóng phiên)."""
        if self.dead(): raise ConnectionResetError("app đã ngắt kết nối")
        self.write(t, payload)
        await asyncio.wait_for(self.w.drain(), timeout)

    def send_nowait(self, t, payload=b""):
        """Gói nhỏ (PONG, STATS, chữ copy…): ghi luôn, KHÔNG chờ — không để hình đang nghẽn làm chậm lệnh khác."""
        if self.dead(): return
        try: self.write(t, payload)
        except Exception: pass

    async def close(self):
        if self.closed: return
        self.closed = True
        try: self.w.close()
        except Exception: pass


class DirectLink(Link):
    kind = "direct"
    def __init__(self, reader, writer, pre=b""):
        self.r, self.w, self.pre = reader, writer, pre                 # pre: 4 byte đầu đã đọc để phân biệt app ↔ công cụ (HTTP)
        _small_buffers(writer)

    async def _read(self, n):
        if self.pre:
            b, self.pre = self.pre[:n], self.pre[n:]
            return b + (await self.r.readexactly(n - len(b)) if len(b) < n else b"")
        return await self.r.readexactly(n)

    async def recv(self):
        n = struct.unpack(">I", await self._read(4))[0]
        if n < 1 or n > 8 * 1024 * 1024: raise ValueError("bad frame")
        b = await self._read(n)
        return b[0], b[1:]

    def write(self, t, payload=b""):
        if len(payload) < 4096: self.w.write(struct.pack(">IB", 1 + len(payload), t) + payload)
        else: self.w.write(struct.pack(">IB", 1 + len(payload), t)); self.w.write(payload)


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ---- Đẩy app cũ từ Cloudflare về đường thẳng ----
# App (Android ≤ 1.48, PC ≤ 1.102) nhớ đường nối được lần trước và thử nó ĐẦU TIÊN: đã từng đi Cloudflare (lúc modem chưa mở cổng)
# thì mở cổng rồi vẫn đi Cloudflare mãi (trễ ~100 ms, giật). Khi đã có máy ở NGOÀI mạng nhà nối thẳng được vào cổng phát hình
# (= modem đã mở cổng), lần đầu mỗi IP vào bằng WebSocket sẽ nhận 503 trong 20 giây → app tự thử đường thẳng và nhớ nó.
# Sau đó IP đó đi WebSocket bình thường 6 giờ (máy không nối thẳng được chỉ chậm ~20 giây, 6 giờ 1 lần).
# Chỉ đẩy app CloudBlue (User-Agent BlueRobloxApp/ · BlueRobloxPC/) — trình duyệt (play.html) không có đường thẳng, không đụng.
# Tắt: WS_NUDGE=0 trong cloudphone.conf.
WS_NUDGE = str(C.get("WS_NUDGE", "1")).strip() != "0"
NUDGE_WIN, NUDGE_COOL, NUDGE_PROOF = 20, 6 * 3600, 24 * 3600
_DIRECT_OK_F = os.path.join(RTC, "direct-ok.txt")          # giữ mốc qua khởi động lại (đường thẳng web chỉ báo khi cổng đã mở)
try: _direct_ok_t = float(open(_DIRECT_OK_F).read().strip() or 0)   # lúc gần nhất có máy ở ngoài mạng nhà nối được vào cổng phát hình
except (OSError, ValueError): _direct_ok_t = 0.0
_nudge = {}                         # IP khách → (hết trả 503 lúc, hết miễn lúc)


def _global_ip(host):
    try:
        import ipaddress
        ip = ipaddress.ip_address(str(host).split("%")[0])
        if getattr(ip, "ipv4_mapped", None): ip = ip.ipv4_mapped
        return ip.is_global
    except ValueError:
        return False


def note_direct_peer(writer):
    """Có kết nối vào cổng phát hình từ IP công khai → cổng modem chắc chắn đã mở."""
    global _direct_ok_t
    try: host = (writer.get_extra_info("peername") or ("",))[0]
    except Exception: host = ""
    if _global_ip(host):
        save = time.time() - _direct_ok_t > 600
        _direct_ok_t = time.time()
        if save:
            try:
                with open(_DIRECT_OK_F, "w") as fh: fh.write(str(int(_direct_ok_t)))
            except OSError: pass


def ws_should_nudge(hdr, now=None):
    if not WS_NUDGE: return False
    ua = hdr.get("user-agent", "")
    if not (ua.startswith("BlueRobloxApp/") or ua.startswith("BlueRobloxPC/")): return False
    now = time.time() if now is None else now
    if now - _direct_ok_t > NUDGE_PROOF: return False                 # chưa thấy ai ở ngoài nối thẳng được → cổng có thể chưa mở
    ip = (hdr.get("cf-connecting-ip") or "").strip()
    if not ip: return False
    if len(_nudge) > 50000:
        for k in [k for k, v in _nudge.items() if v[1] < now]: _nudge.pop(k, None)
    until, cool = _nudge.get(ip, (0.0, 0.0))
    if now < until: return True
    if now < cool: return False
    _nudge[ip] = (now + NUDGE_WIN, now + NUDGE_COOL)
    return True


# ---- Đo tốc độ đường vòng Cloudflare: GET /v2/speed?kb=N&t=MÃ → N KB dữ liệu ngẫu nhiên (ketnoi.py đo QUIC ↔ HTTP/2) ----
# Chỉ trả khi đúng MÃ (băm từ khoá máy chủ — người ngoài không đoán được), tối đa 8 MB/lần, 1 lần đo một lúc.
SPEED_TOKEN = hashlib.sha256(((KEY or "") + "|" + NODE_ID + "|cb-speed").encode()).hexdigest()[:24]
_SPEED_CHUNK = os.urandom(65536)
_speed_busy = [False]


async def speed_reply(first_line, writer):
    """Dòng đầu yêu cầu HTTP là GET /v2/speed… đúng mã → gửi dữ liệu đo rồi đóng, trả True. Không phải → False (xử lý như cũ)."""
    try: path = first_line.split(" ")[1]
    except IndexError: return False
    if not path.startswith("/v2/speed"): return False
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
    if not hmac_eq((q.get("t") or [""])[0], SPEED_TOKEN) or _speed_busy[0]:
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"); await writer.drain(); writer.close(); return True
    try: n = max(1, min(8192, int((q.get("kb") or ["64"])[0]))) * 1024
    except ValueError: n = 65536
    _speed_busy[0] = True
    try:
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nCache-Control: no-store, no-transform\r\n"
                     b"Content-Length: %d\r\nConnection: close\r\n\r\n" % n)
        sent = 0
        while sent < n:
            part = _SPEED_CHUNK[:min(len(_SPEED_CHUNK), n - sent)]
            writer.write(part); sent += len(part)
            await asyncio.wait_for(writer.drain(), 30)
    except Exception:
        pass
    finally:
        _speed_busy[0] = False
        try: writer.close()
        except Exception: pass
    return True


def hmac_eq(a, b):
    import hmac
    return hmac.compare_digest(str(a).encode(), str(b).encode())


class WSLink(Link):
    kind = "ws"
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer; self.frag = None; self.op = 0
        _small_buffers(writer)

    @staticmethod
    async def accept(reader, writer, first=b"", direct=False):
        """direct=True: TRÌNH DUYỆT nối thẳng vào cổng TLS của app (wss://dN.<miền>:PORT/v2/stream) — first = dòng đầu đã đọc."""
        head = first + await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin-1").split("\r\n")
        hdr = {}
        for ln in lines[1:]:
            if ":" in ln: k, v = ln.split(":", 1); hdr[k.strip().lower()] = v.strip()
        if hdr.get("upgrade", "").lower() != "websocket" or "sec-websocket-key" not in hdr:
            if await speed_reply(lines[0], writer): return None
            body = b"BlueRoblox stream v2"
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
            await writer.drain(); writer.close(); return None
        if not direct and ws_should_nudge(hdr):                      # app cũ đang dính Cloudflare → bảo nó thử đường thẳng
            writer.write(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain(); writer.close(); return None
        acc = base64.b64encode(hashlib.sha1((hdr["sec-websocket-key"] + WS_GUID).encode()).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode())
        await writer.drain()
        lk = WSLink(reader, writer)
        if direct: lk.kind = "wsd"                                 # web đi THẲNG: ngưỡng chậm / bitrate như app đi thẳng
        else: lk.ip = (hdr.get("cf-connecting-ip") or "").strip()[:45]   # 21/11a: IP khách do Cloudflare ghi (pcrelay chặn dò mã theo IP)
        return lk

    async def _frame(self):
        b0, b1 = await self.r.readexactly(2)
        fin, op, masked, n = b0 & 0x80, b0 & 0x0F, b1 & 0x80, b1 & 0x7F
        if n == 126: n = struct.unpack(">H", await self.r.readexactly(2))[0]
        elif n == 127: n = struct.unpack(">Q", await self.r.readexactly(8))[0]
        if n > 8 * 1024 * 1024: raise ValueError("ws frame too big")
        mk = await self.r.readexactly(4) if masked else None
        data = await self.r.readexactly(n) if n else b""
        if mk and n:
            m = (mk * (n // 4 + 1))[:n]
            data = (int.from_bytes(data, "little") ^ int.from_bytes(m, "little")).to_bytes(n, "little")
        return fin, op, data

    async def recv(self):
        while True:
            fin, op, data = await self._frame()
            if op == 8: raise EOFError("ws close")
            if op == 9: self._wframe(10, data); continue
            if op == 10: continue
            if op in (1, 2):
                if fin:
                    if op == 2 and data: return data[0], data[1:]
                    continue
                self.frag, self.op = bytearray(data), op; continue
            if op == 0 and self.frag is not None:
                self.frag += data
                if fin:
                    d, o = bytes(self.frag), self.op; self.frag = None
                    if o == 2 and d: return d[0], d[1:]

    def _wframe(self, op, data):
        n = len(data)
        hdr = bytes([0x80 | op]) + (bytes([n]) if n < 126 else (b"\x7e" + struct.pack(">H", n)) if n < 65536 else (b"\x7f" + struct.pack(">Q", n)))
        self.w.write(hdr)
        if n: self.w.write(data)

    def write(self, t, payload=b""):
        if len(payload) < 4096: self._wframe(2, bytes([t]) + payload)
        else:                                               # khung lớn: ghi đầu khung + dữ liệu riêng (không chép cả khung hình)
            n = 1 + len(payload)
            hdr = b"\x82" + ((b"\x7e" + struct.pack(">H", n)) if n < 65536 else (b"\x7f" + struct.pack(">Q", n)))
            self.w.write(hdr + bytes([t])); self.w.write(payload)

    async def close(self):
        if self.closed: return
        try: self.w.write(b"\x88\x00")
        except Exception: pass
        await Link.close(self)


# ================================================================ Phiên xem 1 máy
SESSIONS = {}


class Closed(Exception):
    pass


class Session:
    is_preview = False
    a9 = False; _wk_t = 0.0; n_keyfix = 0          # mặc định cho mọi phiên (kể cả phiên dựng thiếu __init__) — __init__ đặt lại theo máy
    fps_over = 1.0; _fw = None                     # 16/11c: Android gửi nhiều khung hơn đã xin bao nhiêu lần · cửa sổ đo
    dl = 0; net = ""; ceil_kbps = 0; ceil_until = 0.0; ceil_s = 0.0; t_rate0 = 0.0; prodlog = None      # 16/11 (như trên)
    kf_legacy = False; kf_probe = False; vid_ok_t = 0.0
    n_in = 0; n_restart = 0; dr = None             # 27/11e: số khung bộ nén ra · số lần bật lại bộ nén · bỏ khung vì đâu (thông số cho app / web)
    n_kreq = 0; _kq_t = 0.0                        # 27/11f: số lần xin khung khoá cbvideo · lúc xin gần nhất
    cbv_req = ""                                   # 27/11f: "1" / "0" = phiên ép cbvideo / scrcpy (web ?cbv=)

    def _want_cbv(self):
        """Phiên này có lấy hình bằng cbvideo không: máy Android 9 + chế độ (on: mọi phiên trừ ?cbv=0 · test: chỉ phiên ?cbv=1)."""
        if not self.a9 or self.is_preview or A9_CBV_MODE == "off" or self.cbv_req == "0": return False
        return A9_CBV_MODE == "on" or self.cbv_req == "1"

    def _cbv(self):
        """27/11f: phiên đang lấy hình bằng cbvideo (xin được khung IDR ngay → bỏ khung rẻ)."""
        return getattr(self.enc, "enc", "") == "cbvideo"

    def _a9slow(self):
        """Android 9 lấy hình bằng scrcpy: bỏ 1 khung = bật lại bộ nén (đắt) → ngưỡng bỏ khung nới ra (27/11e). cbvideo: như máy khác."""
        return self.a9 and not self._cbv()

    def _cbv_key(self, force=False):
        """cbvideo: xin khung IDR (tối đa 4 lần / giây). True = đã gửi lệnh."""
        now = time.time()
        if not self._cbv() or (not force and now - self._kq_t < CBV_KEY_GAP): return False
        self._kq_t = now
        try: ok = bool(self.enc.request_key())
        except Exception: ok = False
        if ok: self.n_kreq += 1
        return ok

    def __init__(self, link, me, phone, hello, t_hello):
        self.link, self.me, self.phone, self.hello, self.t_hello = link, me, phone, hello, t_hello
        self.pid = phone["id"]; self.name = phone["container"]; self.serial = f"127.0.0.1:{phone['port']}"
        self.q = hello.get("q") if hello.get("q") in ("eco", "bal", "hd", "auto") else "auto"
        self.cur_q = "bal" if self.q == "auto" else self.q
        try: self.fps_req = int(hello.get("fps") or 0); self.maxh_req = int(hello.get("maxh") or 0)
        except (TypeError, ValueError): self.fps_req = self.maxh_req = 0
        self.cbv_req = str(hello.get("cbv") or "").strip()[:1]        # 27/11f: web ?cbv=1 / 0 → ép cbvideo / scrcpy cho phiên này
        self.kbps_req = 0
        self.loop = asyncio.get_running_loop()
        self.aq = asyncio.Queue(); self.src = None; self.enc = None; self.ctl = None; self.vlock = asyncio.Lock()
        self.closed = False; self.last_rx = time.time()
        self.sent = 0; self.bytes = 0; self.drop = 0; self.wait_key = True; self.last_restart = 0.0; self.last_key_sent = 0.0
        self.congest = collections.deque(maxlen=20); self.calm_since = time.time(); self.restart_req = None
        self.vw = self.vh = 0; self.gen = 0; self.fps = 30; self.kbps = 0
        self.ack_pts = None; self.ack_t = 0.0; self.lag_ms = 0; self.base_ms = 0.0
        self.kbps_cur = None; self.kbps_cap = PRESETS[self.cur_q][2]; self.rate_t = 0.0
        self.net = str(hello.get("net") or "")[:2]           # app điện thoại báo loại mạng: w = wifi · c = 4G/5G
        try: self.dl = max(0, min(10 ** 6, int(float(hello.get("dl") or 0))))      # app / web báo tốc độ tải ước lượng (kbps) — chỉ để bắt đầu nhẹ
        except (TypeError, ValueError, OverflowError): self.dl = 0
        self.hold_until = 0.0; self.hold_s = 0.0; self.last_cong = 0.0
        self.ceil_kbps = 0; self.ceil_until = 0.0; self.ceil_s = 0.0             # trần vừa đo (kbps) · còn hiệu lực tới lúc · số giây giữ trần
        self.prodlog = collections.deque(); self.t_rate0 = time.time()           # (lúc, byte) bộ nén vừa ra · lúc bắt đầu mức bitrate hiện tại
        self.kf_legacy = _KF_LEGACY.get(self.serial, 0) > time.time(); self.kf_probe = False; self.vid_ok_t = 0.0
        self.kbps_cur = self._kbps_start()
        self._rate_load()
        self.inflight = collections.deque(); self.delivered = collections.deque(); self.lat = collections.deque()
        self.key_grace = 0.0
        self.from_android = False          # True: Windows không quay được cửa sổ máy này → cả phiên lấy hình thẳng từ Android (scrcpy)
        self.dead = 0                      # số lần scrcpy chết khi CHƯA gửi được khung nào
        self._wn, self._wn_t = -1, time.time()   # số khung cửa sổ lần trước + lúc đổi (canh cửa sổ ngừng ra hình)
        self.t_auth = time.time()          # lần kiểm lại quyền gần nhất (REAUTH_S)
        self.t_start = time.time(); self.why = ""   # lúc mở phiên · lý do đóng (ghi nhật ký cho kiemlag.py)
        self.fail_n = 0; self.fail_t = 0.0  # bật lại hình lỗi liên tiếp (thử lại tại chỗ, không đóng phiên)
        self.a9 = str(phone.get("android") or "").strip() == "9"     # Android 9 = LDPlayer 9 (bộ nén phần mềm, không lặp khung)
        self._wk_t = 0.0; self.n_keyfix = 0  # lúc bắt đầu chờ khung khoá · số lần bật lại bộ nén để lấy khung khoá

    # ---------- hình ----------
    def _kbps_start(self):
        """Bitrate lúc bắt đầu (None = trần của mức chất lượng). Tự động + 4G/5G → bắt đầu nhẹ, mạng ổn tự tăng dần.
           Tự động + đường vòng Cloudflare → bắt đầu WS_START_KBPS."""
        k = AUTO_CELL_KBPS if self.q == "auto" and self.net == "c" else None
        if self.q == "auto" and getattr(self.link, "kind", "") == "ws": k = min(k or WS_START_KBPS, WS_START_KBPS)
        if self.q == "auto" and 0 < self.dl < DL_HINT_MAX:     # app / web tự báo mạng đang yếu → bắt đầu ~60% tốc độ đó, mạng ổn tự tăng
            k = min(k or 10 ** 9, max(MIN_KBPS + 120, int(self.dl * 0.6)))
        return k

    def _rate_key(self, any_phone=False):
        """(khách, máy, loại đường[:loại mạng]). any_phone: mức chung của khách trên loại đường đó (máy nào cũng dùng — mạng của khách là một)."""
        kind = getattr(self.link, "kind", "?") + (":" + self.net if self.net else "")
        return (str((self.me or {}).get("uid") or ""), "*" if any_phone else self.pid, kind)

    @staticmethod
    def _mem_ok(m, now):
        """Mức nhớ còn dùng được: 15 phút; khách mạng yếu thường xuyên (đã hạ ≥ 2 lần) → RATE_MEM_LONG_S."""
        return bool(m) and (now - m["t"] <= RATE_MEM_S or (int(m.get("n", 0)) >= 2 and now - m["t"] <= RATE_MEM_LONG_S))

    def _rate_load(self):
        """Nối lại (cùng khách + máy + loại đường; máy chưa có mức nhớ thì lấy mức của khách ở máy khác) → bắt đầu ở mức đã dò được,
           giữ nguyên lịch giữ mức + trần vừa đo."""
        if self.q != "auto": return
        now = time.time()
        m = _RATE_MEM.get(self._rate_key())
        if not self._mem_ok(m, now):
            m = _RATE_MEM.get(self._rate_key(any_phone=True))
            if not self._mem_ok(m, now): return
        cur = self.kbps_cur or PRESETS[self.cur_q][2]
        age = now - float(m.get("t", now))
        if age > RATE_FRESH_S:                                 # 17/11e: mức nhớ đã cũ (mạng có thể đã khoẻ) → bắt đầu ≥ RATE_FRESH_KBPS, bỏ trần / giữ cũ
            k = max(int(m["k"]), min(int(cur), RATE_FRESH_KBPS))
            if k < cur: self.kbps_cur = k
            if int(m["k"]) < k:
                log(f"  {self.name}: mức mạng yếu đã nhớ ({int(m['k'])} kbps, {int(age // 60)} phút trước) → bắt đầu {k} kbps, không giữ trần cũ")
            return
        if m["k"] < cur: self.kbps_cur = m["k"]
        self.hold_until, self.hold_s, self.last_cong = m["until"], m["hs"], m["lc"]
        self.ceil_kbps, self.ceil_until, self.ceil_s = int(m.get("ck", 0)), float(m.get("cu", 0.0)), float(m.get("cs", 0.0))

    def _rate_forget(self):
        """17/11e: khách TỰ chọn chất lượng → bỏ mức đã nhớ + trần + thời gian giữ của khách này (trên loại đường này): dò lại từ đầu.
           Trả về True nếu trước đó đang có mức nhớ."""
        had = False
        for k in (self._rate_key(), self._rate_key(any_phone=True)):
            had = _RATE_MEM.pop(k, None) is not None or had
        had = had or bool(self.ceil_kbps)
        self.ceil_kbps = 0; self.ceil_until = 0.0; self.ceil_s = 0.0
        self.hold_until = 0.0; self.hold_s = 0.0; self.last_cong = 0.0
        return had

    def _rate_save(self, bump=0):
        """bump=1: vừa phải hạ vì nghẽn (đếm số lần → biết khách mạng yếu thường xuyên) · bump=-1: đã lên lại gần trần (mạng khoẻ) → xoá đếm."""
        if self.q != "auto" or self.kbps_cur is None: return
        now = time.time()
        if len(_RATE_MEM) > 5000:
            for k in [k for k, v in _RATE_MEM.items() if not self._mem_ok(v, now)]: _RATE_MEM.pop(k, None)
        key = self._rate_key(); n = 0 if bump < 0 else int((_RATE_MEM.get(key) or {}).get("n", 0)) + bump
        rec = {"k": int(self.kbps_cur), "until": self.hold_until, "hs": self.hold_s, "lc": self.last_cong, "t": now, "n": n,
               "ck": int(self.ceil_kbps), "cu": self.ceil_until, "cs": self.ceil_s}
        _RATE_MEM[key] = rec; _RATE_MEM[self._rate_key(any_phone=True)] = dict(rec)

    def _may_raise(self, now):
        """Được thử tăng bitrate chưa: dưới trần, yên > RATE_UP_GAP giây, đổi mức gần nhất > RATE_UP_GAP giây, hết thời gian giữ mức sau nghẽn.
           (Mỗi lần đổi = bật lại bộ nén → đứng hình 1–3 giây; trước 11/11 là 10 giây.)"""
        cur = self.kbps_cur or self.kbps_cap
        long_calm = now - self.last_cong > CEIL_CALM_S and now - self.calm_since > RATE_UP_GAP / 3       # 17/11e: lâu không phải hạ → hết giữ mức
        if not (cur < self.kbps_cap and self._calm(now) and now - self.rate_t > RATE_UP_GAP and (now >= self.hold_until or long_calm)): return False
        new = self._raise_to(now)
        return new >= cur * 1.15 or new >= self.kbps_cap      # 16/11: trần vừa đo còn hiệu lực mà đã sát trần → KHÔNG bật lại bộ nén vì vài %

    def _calm(self, now):
        """Đủ yên để thử tăng: không lần chậm nào trong RATE_UP_GAP giây — hoặc (17/11e, 4G hay giật lẻ) chỉ ≤ 1 lần chậm trong 90 giây gần
           đây và đã ≥ 90 giây chưa phải hạ (trước: cứ 1 lần chậm là chờ lại từ đầu → mạng giật lẻ 30 giây/lần thì không bao giờ được tăng)."""
        if now - self.calm_since > RATE_UP_GAP: return True
        since = max(self.last_cong, self.rate_t, float(getattr(self, "t_start", now) or now))     # lần hạ / đổi mức / mở phiên gần nhất
        return now - since > 90 and sum(1 for t in self.congest if now - t <= 90) <= 1

    def _raise_to(self, now):
        cur = self.kbps_cur or self.kbps_cap
        new = min(self.kbps_cap, int(cur * 1.25) + 50) if now - self.last_cong < 600 else min(self.kbps_cap, int(cur * 1.5) + 100)   # vừa nghẽn trong 10 phút → bước vừa
        if self.ceil_kbps and now < self.ceil_until and now - self.last_cong < CEIL_CALM_S:
            new = min(new, int(self.ceil_kbps * 0.9))          # không thử lại mức vừa làm nghẽn (17/11e: yên ≥ CEIL_CALM_S giây thì thôi giữ trần)
        return new

    def _dims(self):
        maxh, fps, kbps = PRESETS[self.cur_q]
        if self.a9 and A9_MAXH and self.cur_q != "hd": maxh = min(maxh, max(480, A9_MAXH))   # 27/11e: Android 9 nén phần mềm → hình ≤ 960
        if self.maxh_req: maxh = min(maxh, max(320, self.maxh_req))
        if self.fps_req: fps = max(10, min(fps, self.fps_req))
        try: fps = max(10, min(fps, int(self.phone.get("fps") or 60)))         # không vượt FPS khách đã mua
        except (TypeError, ValueError): pass
        if self.kbps_req: kbps = max(300, min(20000, self.kbps_req))
        self.kbps_cap = kbps
        if self.kbps_cur is None or self.kbps_cur > kbps: self.kbps_cur = kbps
        kbps = self.kbps_cur                                   # tự hạ theo mạng khách (đo bằng ACK)
        if kbps < 700: fps = min(fps, 20)
        elif kbps < 1400: fps = min(fps, 30)
        kbe = kbps / max(1.0, float(getattr(self, "fps_over", 1.0) or 1.0))   # 16/11c: Android gửi nhiều khung hơn đã xin → mỗi khung ít dữ liệu hơn
        if self.q == "auto":                                   # Tự động: mạng yếu → giảm cả độ nét
            for lim, mh, mf in AUTO_TIERS:
                if kbe < lim: maxh, fps = min(maxh, mh), min(fps, mf); break
        else:                                                  # 16/11c: Tiết kiệm / Cân bằng / Nét mà mạng kéo bitrate xuống DƯỚI mức gói
            for lim, mh, mf in AUTO_TIERS:                     # → bớt điểm ảnh / khung theo bậc như Tự động: mỗi điểm nhiều dữ liệu hơn → hết vỡ ô
                if kbe < lim: maxh, fps = min(maxh, mh), min(fps, mf); break      # (đo: 600 kbps 960 → 640: SSIM khi cuộn 0,84 → 0,89 · 450 kbps 0,74 → 0,87)
        sw, sh = self.src.cw, self.src.ch
        sc = min(1.0, maxh / max(sw, sh, 1))
        ow, oh = (sw, sh) if sc >= 0.999 else (max(16, int(sw * sc) & ~7), max(16, int(sh * sc) & ~7))
        return ow, oh, fps, kbps

    def _on_au(self, gen, data, key, cfg, pts):                # luồng bộ nén → vòng chính
        if gen != self.gen or self.closed: return
        t = time.monotonic()
        try: self.loop.call_soon_threadsafe(self._enqueue, (gen, data, key, cfg, pts, t))
        except RuntimeError: pass

    def _dropx(self, why, n=1):
        """27/11e: đếm khung bỏ theo lý do — lag: app báo nhận chậm · q: khung chờ gửi quá lâu (nghẽn) · wk: đang chờ khung khoá ·
           full: hàng chờ đầy · cut: bộ nén gửi khung thiếu lát. Hiện ở Thông số của web / app."""
        d = self.__dict__.get("dr")
        if d is None: d = self.dr = {}
        d[why] = d.get(why, 0) + n
        if self._cbv(): self._cbv_key()                       # 27/11f: cbvideo → xin khung IDR ngay, khỏi đứng hình chờ / bật lại bộ nén

    def _enqueue(self, it):
        pl = self.prodlog
        if pl is not None and it[1] is not None:               # 16/11: bộ nén ra bao nhiêu (kể cả khung sẽ bị bỏ) → so với sức đường truyền
            now = time.time(); pl.append((now, len(it[1])))
            while pl and now - pl[0][0] > 6: pl.popleft()
        if it[1] is not None: self.n_in += 1
        if self.aq.qsize() > 240: self.drop += 1; self._dropx("full"); self.wait_key = True; return     # app không đọc nữa → đừng tích hình vô hạn
        self.aq.put_nowait(it)

    def _iframe(self, fps, kbps=0):
        """Khoảng khung khoá đưa cho scrcpy — tính bằng "giây ở 60 khung/giây" (scrcpy 2.4 đặt KEY_FRAME_RATE = 60, bộ nén đếm KHUNG).
           Android 9: SCR_IFRAME_A9 · xem trước: như cũ · còn lại: khung khoá mỗi SCR_KEY_S giây THẬT ở số khung/giây đang phát."""
        if self.is_preview: return SCR_IFRAME
        if self.a9: return SCR_IFRAME_A9
        if SCR_KEY_S <= 0 or self.kf_legacy: return SCR_IFRAME
        return max(0.1, min(5.0, SCR_KEY_S * key_every(kbps) * max(10, int(fps)) / 60.0))       # 16/11c: trần 5 (trước SCR_IFRAME = 1 → 60 khung)

    def _start_video_scrcpy(self):
        """Hình lấy thẳng từ Android (scrcpy). Tắt bộ cũ TRƯỚC (máy ảo chỉ nên chạy 1 bộ mã hoá) rồi bật bộ mới → (rộng, cao) thật."""
        if self.closed: raise Closed()
        wait = 5.0 if self.is_preview else 10.0
        if not isinstance(self.src, ScrcpySource):
            if self.src: self.src.stop()
            self.src = None
            if not adb_ready(self.serial, wait): raise AdbGone(f"adb không thấy máy {self.serial}")   # máy tắt / Android chưa lên → khỏi chờ thêm 10–20 giây vô ích
            src = ScrcpySource(self.serial, self.phone.get("res")); src.open(); self.src = src
            if self.closed: raise Closed()
            wait = 0.0                                         # vừa hỏi adb xong → bộ scrcpy khỏi hỏi lại
        ow, oh, fps, kbps = self._dims()
        self.gen += 1; g = self.gen
        old_enc = self.enc
        kind = "cbv" if (self._want_cbv() and cbv_ok_for(self.serial) and ensure_cbv()) else "scrcpy"     # 27/11f
        op = getattr(old_enc, "proc", None)                   # bộ scrcpy cũ đang chạy tốt (đã ra khung, tiến trình adb còn sống) → máy thấy được, file có sẵn
        quick = (bool(self.vid_ok_t) and getattr(old_enc, "enc", "") in ("scrcpy", "cbvideo") and getattr(old_enc, "kind", "scrcpy") == kind
                 and getattr(old_enc, "frames_in", 0) > 0 and op is not None and op.poll() is None)
        self.vid_ok_t = 0.0                                    # bật lỗi → lần sau kiểm adb + file đầy đủ
        msz = _scr_max(self.src.cw, self.src.ch, max(ow, oh))       # 16/11k: cả hai cạnh hình chia hết 16
        def mk(kd, qk):
            return ScrcpyVideo(self.serial, msz, fps, kbps, lambda d, k, c, p: self._on_au(g, d, k, c, p), lambda w, h: self._on_vsize(g, w, h),
                               iframe=self._iframe(fps, kbps), quick=qk, ready_wait=wait, kind=kd)
        enc = mk(kind, quick)
        self.enc = enc
        if old_enc: old_enc.stop()
        if self.closed: enc.stop(); raise Closed()
        try:
            w, h = enc.start()
        except (Closed, Deny, AdbGone):
            raise
        except Exception as e:
            if kind != "cbv" or self.closed: raise
            _CBV_BAD[self.serial] = time.time() + CBV_BAD_S           # cbvideo không chạy được ở máy này → scrcpy 30 phút, phiên này đổi ngay
            log(f"  {self.name}: cbvideo lỗi ({str(e).strip()[:160] or type(e).__name__}) → lấy hình bằng scrcpy {CBV_BAD_S // 60} phút")
            enc.stop()
            enc = mk("scrcpy", False); self.enc = enc
            w, h = enc.start()
        if self.closed: enc.stop(); raise Closed()
        self.vid_ok_t = time.time()
        self.vw, self.vh, self.fps, self.kbps = w, h, fps, kbps
        if self.ctl: self.ctl.set_view(w, h)
        return w, h

    def _on_vsize(self, gen, w, h):                            # luồng đọc hình (scrcpy) → vòng chính: máy xoay → cỡ hình mới
        def apply():
            if gen != self.gen or self.closed or (w, h) == (self.vw, self.vh): return
            self.vw, self.vh = w, h
            if self.ctl: self.ctl.set_view(w, h)
            self.wait_key = True
            self.link.send_nowait(S_SIZE, json.dumps({"w": w, "h": h}).encode())
        try: self.loop.call_soon_threadsafe(apply)
        except RuntimeError: pass

    def _start_video(self, cpu=False):
        """(Bật lại) bộ quay + bộ nén. Chạy trong luồng nền; phiên đã đóng giữa chừng → dọn sạch thứ vừa tạo."""
        if video_mode() != "scrcpy" and not self.from_android and wgc_is_bad(self.name):
            self.from_android = True
            log(f"  {self.name}: cửa sổ máy này vừa quay lỗi / ra hình đen → lấy hình thẳng từ Android ngay (WGC_BAD_MIN)")
        if video_mode() == "scrcpy" or self.from_android: return self._start_video_scrcpy()
        if self.closed: raise Closed()
        if self.src is None or self.src.resized() or getattr(self.src, "closed", False):
            old = self.src
            if old: old.stop()
            src = make_source(self.name, int(self.phone.get("fps") or 30))
            self.src = src
            try:
                src.open()
            except (CaptureBlocked, WinBad, CapGone) as e:
                src.stop()
                if self.closed: raise Closed()
                if isinstance(e, CapGone):
                    # 17/11a: trước đây lỗi này đi thẳng tới khách = "OFFLINE" ngay lập tức, không ghi nhật ký, mở mãi không vào (win8)
                    if not adb_ready(self.serial, 3.0): self.src = None; raise e      # máy tắt thật / Android chưa lên → báo như cũ
                    log(f"  {self.name}: Windows đóng phiên quay cửa sổ ngay mà Android vẫn chạy → lấy hình thẳng từ Android (scrcpy, {self.serial})")
                else:
                    log(f"  {self.name}: {e} → lấy hình thẳng từ Android (scrcpy, {self.serial})")
                self.from_android = True
                if isinstance(e, (CaptureBlocked, CapGone)): wgc_mark_bad(self.name)
                try:
                    return self._start_video_scrcpy()
                except (Closed, Deny, AdbGone):                # AdbGone: máy tắt / Android chưa lên → nơi gọi quyết định (gọi bật máy, báo khách)
                    raise
                except Exception as e2:
                    log(f"  {self.name}: lấy hình thẳng từ Android cũng lỗi: {e2!r}")
                    raise Deny("OFFLINE", MSG_NOVIDEO, fix="reboot")
            except BaseException:
                self.src = None                                # nguồn hình chưa mở được → lần thử sau tạo lại từ đầu
                try: src.stop()
                except Exception: pass
                raise
            if self.closed: src.stop(); raise Closed()
        old_enc = self.enc
        ow, oh, fps, kbps = self._dims()
        self.gen += 1; g = self.gen
        enc = Encoder(self.src, ow, oh, fps, kbps, lambda d, k, c, p: self._on_au(g, d, k, c, p), cpu=cpu)
        self.enc = enc
        if old_enc: old_enc.stop()
        if self.closed: enc.stop(); raise Closed()
        enc.start()
        if self.closed: enc.stop(); raise Closed()
        self.vw, self.vh, self.fps, self.kbps = ow, oh, fps, kbps
        if self.ctl: self.ctl.set_view(ow, oh)
        return ow, oh

    async def restart_video(self, size_msg=False, cpu=False):
        async with self.vlock:
            if self.closed: return
            self.wait_key = True; self.n_restart += 1
            old = (self.vw, self.vh)
            try: w, h = await asyncio.to_thread(self._start_video, cpu)
            finally: self.last_restart = time.time(); self.t_rate0 = time.time()
            if size_msg or (w, h) != old: self.link.send_nowait(S_SIZE, json.dumps({"w": w, "h": h}).encode())

    # ---------- vòng chính ----------
    def _wake(self):
        """Màn hình Android đang tắt → bật sáng TRƯỚC khi lấy hình (khỏi màn đen). Đang sáng thì không gửi phím (không đổi gì)."""
        rc, o, _ = adb(self.serial, "shell", "dumpsys power | grep -m1 mWakefulness=", timeout=6)
        if rc == 0 and "mWakefulness=" in o and "Awake" not in o:
            adb(self.serial, "shell", "input keyevent 224", timeout=6)
            log(f"  {self.name}: ☀ màn hình Android đang tắt → đã bật sáng trước khi mở")
        adb(self.serial, "shell", "wm dismiss-keyguard; settings put system screen_off_timeout 2147483647; svc power stayon true", timeout=8)

    async def run(self):
        old = SESSIONS.get(self.pid)
        if old and not old.closed and old.t_hello > self.t_hello:     # HELLO cũ đến muộn → không đá phiên mới hơn
            self.link.send_nowait(S_ERROR, json.dumps({"code": "BUSY", "msg": "Đang mở máy ở kết nối khác."}).encode())
            await self.link.close(); return
        SESSIONS[self.pid] = self
        mark_seen(self.phone, write=True)                    # máy có người xem → phonectl idle không cho ngủ
        if old and old is not self: await old.kick()
        log(f"▶ {self.name} ← {self.me['uid'][:8]} ({self.link.kind}, {self.hello.get('client', '?')})")
        if WAKE_ON_OPEN:
            try: await asyncio.wait_for(asyncio.to_thread(self._wake), 15)
            except Exception: pass
        self.ctl = Control(self.serial, self._on_clip, dfix=not self.a9)
        threading.Thread(target=self.ctl.start, daemon=True).start()
        try:
            w, h = await self._first_video()
        except Closed:
            await self.finish(); return
        except Deny as d:
            self.why = self.why or f"báo app {d.code}"
            self.link.send_nowait(S_ERROR, err_json(d.code, d.msg, **getattr(d, "extra", {}))); await self.finish(); return
        except Exception as e:                                 # không được rơi vào đây (mọi lỗi đã đổi thành Deny) — phòng hờ, vẫn báo rõ
            log("  lỗi bật hình:", repr(e))
            self.link.send_nowait(S_ERROR, err_json("OFFLINE", MSG_NOVIDEO, fix="reboot"))
            await self.finish(); return
        if self.closed: return
        self.wait_key = True
        self.link.welcomed = True
        self.t_rate0 = time.time()
        dt = time.monotonic() - self.t_hello
        if dt > 5: log(f"  {self.name}: mở máy mất {dt:.0f} giây (app được giữ kết nối trong lúc chờ)")
        self.link.send_nowait(S_WELCOME, json.dumps({"ok": True, "w": w, "h": h, "fps": self.fps, "kbps": self.kbps, "codec": "h264",
                                                      "enc": self.enc.enc, "name": self.phone.get("name") or self.name,
                                                      "android": str(self.phone.get("android") or ""), "q": self.q}, ensure_ascii=False).encode())
        tasks = [asyncio.create_task(x) for x in (self._sender(), self._receiver(), self._monitor())]
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pend: t.cancel()
        for t in done:
            ex = t.exception() if not t.cancelled() else None
            if ex and not isinstance(ex, (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, EOFError, OSError, ssl.SSLError, Closed)):
                log(f"  {self.name}: lỗi phiên {ex!r}")
            if not self.why: self.why = self._why(tasks.index(t), ex)
        await self.finish()

    async def _first_video(self):
        """Bật hình LẦN ĐẦU của phiên → (rộng, cao). Không bao giờ trả lỗi chung chung để app quay mãi:
           · lỗi lặt vặt (scrcpy chưa nối kịp, adb chập chờn) → thử lại tại chỗ tối đa FIRST_TRIES lần (app được giữ bằng PONG rỗng);
           · không thấy cửa sổ máy mà Android vẫn chạy → lấy hình thẳng từ Android;
           · adb KHÔNG thấy máy → boot_if_off (phonectl wake: chỉ bật máy đang TẮT) → báo khách đúng tình trạng (app PC được giữ chờ);
           · thử hết vẫn lỗi → OFFLINE + fix="reboot" (app hiện nút Khởi động lại máy)."""
        t0 = time.time(); n = 0; held = False
        while True:
            n += 1; err = None; gone = False
            try:
                async with self.vlock:
                    w, h = await asyncio.to_thread(self._start_video)
                self.last_restart = time.time()
                if n > 1: log(f"  {self.name}: bật hình được ở lần thử {n}")
                if self.kf_probe and self.kf_legacy:              # kiểu khung khoá mới lỗi, kiểu cũ chạy → máy này dùng kiểu cũ 6 giờ
                    _KF_LEGACY[self.serial] = time.time() + 6 * 3600
                    log(f"  {self.name}: bộ nén trong máy chỉ chạy với khoảng khung khoá kiểu cũ → giữ kiểu cũ 6 giờ (SCRCPY_KEY_EVERY_S)")
                return w, h
            except Closed:
                raise
            except NoWindow as e:
                err = e; gone = None                           # máy TẮT hay chỉ cửa sổ ẩn / đổi tên? → hỏi adb
            except Deny:
                raise
            except AdbGone as e:
                err = e; gone = True
            except Exception as e:
                err = e
            if self.closed or self.link.dead(): raise Closed()
            log(f"  {self.name}: lỗi bật hình (lần {n}): {str(err).strip()[:180] or type(err).__name__}")
            if gone is not True and not SELFTEST:
                alive = await asyncio.to_thread(adb_ready, self.serial, 3.0)
                if self.closed: raise Closed()
                if isinstance(err, NoWindow) and alive and not self.from_android:
                    self.from_android = True; wgc_mark_bad(self.name); n -= 1
                    log(f"  {self.name}: không thấy cửa sổ máy nhưng Android vẫn chạy → lấy hình thẳng từ Android (scrcpy, {self.serial})")
                    continue
                gone = not alive
                if alive and not await asyncio.to_thread(boot_done, self.serial):
                    gone = True                                # 16/11c: adb thấy máy nhưng Android CHƯA khởi động xong (vừa khởi động lại) → chờ như máy đang bật
            if isinstance(err, NoWindow) and SELFTEST: raise err
            if not gone:
                e_ = self.enc                                  # scrcpy lỗi với khoảng khung khoá kiểu mới → lần sau thử kiểu cũ
                if (getattr(e_, "enc", "") == "scrcpy" and not self.kf_legacy and not self.a9
                        and abs(getattr(e_, "iframe", SCR_IFRAME) - SCR_IFRAME) > 1e-6):
                    self.kf_legacy = self.kf_probe = True
                if n < FIRST_TRIES and time.time() - t0 < FIRST_NEW_TRY_S:
                    if not self.from_android and not SELFTEST and video_mode() != "scrcpy" and getattr(e_, "enc", "") != "scrcpy":
                        self.from_android = True               # quay cửa sổ / bộ nén trên Windows lỗi mà Android vẫn chạy → lần sau lấy hình thẳng từ Android
                        log(f"  {self.name}: quay cửa sổ / nén trên Windows lỗi, Android vẫn chạy → thử lấy hình thẳng từ Android (scrcpy, {self.serial})")
                    await asyncio.sleep(min(3.0, 1.0 * n)); continue
                raise Deny("OFFLINE", MSG_NOVIDEO, fix="reboot")
            rs = await asyncio.to_thread(restarting, getattr(self, "phone", None))
            wk = ("kdl", rs) if rs is not None else await asyncio.to_thread(boot_if_off, self.phone)
            if wk[0] in ("bat", "kdl") and not held and str(self.hello.get("client") or "") == "pc":
                held = True                                    # app PC gặp lỗi là dừng → giữ kết nối tới khi máy lên rồi vào luôn
                if not await hold_for_wake(self.link, self.phone, wk): raise Closed()
                self._reserial(); n = 0; t0 = time.time(); continue
            raise Deny("OFFLINE", wake_msg(wk), **wake_extra(wk))

    def _reserial(self):
        """Máy vừa được bật lại: cổng adb có thể đổi → dùng cổng mới cho hình + điều khiển."""
        s = f"127.0.0.1:{self.phone['port']}"
        if s == self.serial: return
        self.serial = s
        old, self.ctl = self.ctl, Control(self.serial, self._on_clip, dfix=not getattr(self, "a9", False))
        threading.Thread(target=self.ctl.start, daemon=True).start()
        if old: threading.Thread(target=old.stop, daemon=True).start()
        if self.src:
            try: self.src.stop()
            except Exception: pass
            self.src = None

    @staticmethod
    def _why(i, ex):
        """Lý do phiên đóng: i = 0 bộ gửi hình · 1 bộ nhận lệnh của app · 2 bộ canh phiên."""
        name = type(ex).__name__ if ex else ""
        if i == 0:
            if isinstance(ex, asyncio.TimeoutError): return "gửi hình kẹt quá 10 giây"
            return f"lỗi gửi hình {name}" if ex else "dừng gửi hình"
        if i == 1:
            if ex is None: return "app đóng"
            if isinstance(ex, asyncio.TimeoutError): return "15 giây app không gửi gì"
            if isinstance(ex, (asyncio.IncompleteReadError, ConnectionError, EOFError, OSError, ssl.SSLError)): return "app ngắt kết nối"
            return f"lỗi nhận {name}"
        return f"lỗi canh phiên {name}" if ex else "canh phiên dừng"

    async def _sender(self):
        while not self.closed:
            it = await self.aq.get()
            if it[0] != self.gen: continue
            if not self.aq.empty():                    # có khung chờ (vừa nghẽn): khung cũ nhất đã đợi > 150 ms → nhảy tới khung khoá mới nhất
                items = [it]
                while not self.aq.empty(): items.append(self.aq.get_nowait())
                items = [x for x in items if x[0] == self.gen]
                if not items: continue
                if time.monotonic() - items[0][5] > (A9_QWAIT if self._a9slow() else 0.15):     # 27/11e: Android 9 (scrcpy) bỏ khung rất đắt → chịu lâu hơn
                    ki = max((i for i, x in enumerate(items) if x[2] and x[1] is not None), default=None)
                    if ki is None:
                        self.drop += len(items); self._dropx("q", len(items)); self.wait_key = True; self._congested(hard=True); continue
                    self.drop += ki; items = items[ki:]; self.wait_key = False
                    if ki: self._dropx("q", ki)
                for x in items: await self._consider(x)
                continue
            await self._consider(it)

    async def _consider(self, it):
        gen, data, key, cfg, pts, tp = it
        if gen != self.gen: return
        if data is None: self._dropx("cut"); self.wait_key = True; return          # mất khung → chờ khung khoá (tối đa ~1 giây), không hiện hình vỡ
        lim = 1500 if time.time() < self.key_grace else LAG_DROP_MS.get(getattr(self.link, "kind", ""), 350)
        if self.net == "c" and lim < CELL_LAG_MS: lim = CELL_LAG_MS           # 16/11: khách dùng 4G/5G (hay giật ngắn) → bớt bỏ khung oan
        if self._a9slow() and time.time() >= self.key_grace: lim = int(lim * A9_LAG_MUL)   # 27/11e: Android 9 (scrcpy) bỏ 1 khung = bật lại bộ nén → chỉ bỏ khi chậm thật
        if self._behind_ms() > lim:                            # app chậm quá ngưỡng (thẳng 0,35 s · vòng 0,7 s) → bỏ khung cho kịp (không để trễ dồn)
            if not self.wait_key: self._congested()
            self.drop += 1; self._dropx("lag"); self.wait_key = True
            return
        if self.wait_key and not key:
            self.drop += 1; self._dropx("wk"); return
        self.wait_key = False
        await self._send_au(it)

    def _behind_ms(self):
        """Khung CŨ NHẤT app chưa báo nhận đã đi bao lâu, trừ độ trễ nền của mạng (ms). App không gửi ACK → 0."""
        if self.ack_pts is None or not self.inflight: return 0
        return max(0.0, (time.time() - self.inflight[0][2]) * 1000 - self.base_ms)

    async def _send_au(self, it):
        gen, data, key, cfg, pts, tp = it
        await self.link.send(S_VIDEO, struct.pack(">BQ", (1 if key else 0) | (2 if cfg else 0), pts) + data, timeout=10)
        self.sent += 1; self.bytes += len(data)
        self.inflight.append((pts, len(data), time.time()))
        if len(self.inflight) > 3000: self.inflight.popleft()
        if key: self.key_grace = time.time() + 1.0; self.last_key_sent = time.time()

    def goodput_kbps(self):
        now = time.time(); b = sum(n for t, n in self.delivered if now - t <= 2.0)
        return b * 8 / 2.0 / 1000

    def _link_est(self, now):
        """Sức đường truyền vừa thể hiện: (đỉnh, ra) kbps — đỉnh = tốc độ app NHẬN cao nhất trong các cửa sổ 1,5 giây của 5 giây gần đây
           (chỉ tính từ lúc bắt đầu mức bitrate hiện tại), ra = tốc độ bộ nén xuất 3 giây gần đây. Chưa đủ số liệu (< 2,5 giây) → None.
           đỉnh < 0,85·ra: đường truyền CHƯA TỪNG tải nổi mức đang phát (yếu thật) · đỉnh ≥ 0,97·ra: tải được, có chậm cũng chỉ là giật ngắn."""
        pl = self.prodlog
        if not pl or not self.delivered: return None
        t_from = max(self.t_rate0 + 0.3, now - 5.0)
        dv = [(t, n) for t, n in self.delivered if t >= t_from]
        if not dv or now - dv[0][0] < 2.5: return None
        wins = []
        for i in range(len(dv)):
            t_end = dv[i][0]; b = 0
            if t_end - dv[0][0] < 1.5: continue                # chỉ tính cửa sổ nằm trọn trong phần đã đo
            for j in range(i, -1, -1):
                if t_end - dv[j][0] >= 1.5: break
                b += dv[j][1]
            wins.append(b * 8 / 1.5 / 1000)
        if len(wins) < 3: return None
        wins.sort(); peak = wins[min(len(wins) - 1, int(len(wins) * 0.8))]      # mức cao thứ ~80% (1 nhịp ACK dồn không đẩy "đỉnh" lên oan)
        pr = [(t, n) for t, n in pl if now - t <= 3.0]
        span = min(3.0, max(1.0, now - max(self.t_rate0, pl[0][0])))
        prod = sum(n for _, n in pr) * 8 / span / 1000
        if peak <= 0 or prod <= 0: return None
        return peak, prod

    def _fps_watch(self):
        """16/11c: máy Android gửi NHIỀU khung hơn đã xin (bộ nén trong máy bỏ qua giới hạn khung/giây — VD máy đặt 60 FPS mà xem
           ở Tiết kiệm 30) → cùng bitrate chia cho gấp đôi số khung = mỗi khung ít dữ liệu → vỡ ô khi lướt. Đo mỗi 4 giây; vượt ≥ 35%
           2 lần liền → coi bitrate "mỗi khung" thấp tương ứng để chọn bậc độ phân giải (_dims) rồi bật lại hình 1 lần."""
        e = self.enc; now = time.time(); n = getattr(e, "frames_in", 0) or 0
        w = self._fw
        if not w or w[0] is not e: self._fw = [e, now, n, 0]; return
        if now - w[1] < 4.0: return
        got = (n - w[2]) / (now - w[1]); want = max(1, int(getattr(e, "fps", 0) or 30))
        hits = w[3] + 1 if got > want * 1.35 else 0
        self._fw = [e, now, n, hits]
        if hits >= 2 and got / want > (self.fps_over or 1.0) + 0.2:
            self.fps_over = round(min(4.0, got / want), 2)
            log(f"  {self.name}: Android gửi ~{got:.0f} khung/giây dù xin {want} (bộ nén trong máy bỏ qua giới hạn) → mỗi khung ít dữ liệu"
                f" hơn ×{self.fps_over} → chọn độ phân giải theo đó")
            self.restart_req = self.restart_req or "quality"

    def _congested(self, hard=False):
        """Mạng khách không kịp: hạ bitrate theo tốc độ app THẬT SỰ nhận được (đo bằng ACK).
           hard=True: máy chủ đẩy hình ra không kịp (nghẽn thật) → hạ ngay. Còn lại (app báo nhận chậm): chỉ hạ khi chậm LẶP LẠI
           ≥ CONG_REPEAT lần trong CONG_WIN giây kể từ lần đổi mức trước — 1–2 lần giật ngắn chỉ bỏ tới khung khoá, không bật lại bộ nén.
           16/11 — đo sức đường truyền (_link_est): CHƯA TỪNG tải nổi mức đang phát → hạ NGAY lần đầu xuống 0,85 × sức đo được (khỏi
           3 lần đứng hình mới hạ); tải dư mà vẫn chậm (giật ngắn) → rất khó hạ (hạ không giúp gì, chỉ thêm 1 lần bật lại bộ nén);
           chậm thưa nhưng dai dẳng (≥ 4 lần / 2 phút) → cũng hạ. Mức vừa làm nghẽn được nhớ làm TRẦN (xem _raise_to)."""
        now = time.time(); self.congest.append(now); self.calm_since = now
        ev20 = sum(1 for t in self.congest if now - t <= CONG_WIN and t > self.rate_t)
        ev120 = sum(1 for t in self.congest if now - t <= 120 and t > self.rate_t)
        est = self._link_est(now)
        limited = bool(est) and est[0] < 0.85 * est[1]
        proven = bool(est) and est[0] >= 0.97 * est[1]
        if limited: go = True
        elif proven: go = ev20 >= CONG_REPEAT + 2 or ev120 >= 8 or (hard and ev20 >= 2)
        else: go = hard or ev20 >= CONG_REPEAT or ev120 >= 4
        if not go: return
        if now - self.rate_t > RATE_DOWN_GAP and self.ack_t and now - self.ack_t < 3: self._lower(now, est, limited)

    def _lower(self, now, est, limited, early=False):
        """Hạ bitrate + nhớ trần + giữ mức. limited: theo sức đường truyền đo được (0,82 × đỉnh) · còn lại: theo tốc độ app nhận 2 giây gần đây."""
        gp = self.goodput_kbps(); cur = self.kbps_cur or self.kbps_cap
        if limited:                                            # 0,82 × đỉnh 5 giây; đường truyền vừa TỤT (2 giây gần đây nhận ít hơn hẳn) → theo mức vừa tụt
            new = int(max(MIN_KBPS, min(cur * 0.85, est[0] * 0.82, gp * 0.9 if gp > 50 else cur)))
        else: new = int(max(MIN_KBPS, min(cur * 0.7, gp * 0.8 if gp > 50 else cur * 0.5)))
        if new >= cur * 0.92: return False
        # trần = sức đường truyền vừa đo (yếu thật) · hoặc mức bộ nén THẬT SỰ xuất lúc nghẽn (hình đơn giản xuất ít hơn mức đặt)
        self.ceil_kbps = int(min(cur, est[0] * 0.95)) if limited else int(min(cur, est[1]) if est else cur)
        self.ceil_s = min(CEIL_MAX_S, self.ceil_s * 2) if self.ceil_s and now < self.ceil_until + 300 else CEIL_S
        self.ceil_until = now + self.ceil_s
        self.kbps_cur = new; self.rate_t = now; self.restart_req = "quality"
        self.hold_s = min(RATE_HOLD_MAX, self.hold_s * 2) if self.hold_s and now - self.last_cong < 180 else RATE_HOLD_MIN
        self.hold_until = now + self.hold_s; self.last_cong = now; self.calm_since = now; self._rate_save(1)
        log(f"  {self.name}: mạng khách ~{(est[0] if limited else gp):.0f} kbps" + (" (đường truyền chưa tải nổi mức đang phát" + (", hạ sớm trước khi phải bỏ khung)" if early else ")") if limited else "")
            + f" → hạ còn {new} kbps (giữ ≥ {int(self.hold_s)} giây, trần {self.ceil_kbps} trong {int(self.ceil_s // 60)} phút)")
        return True

    def _early_down(self, now):
        """Hạ SỚM, không chờ tới lúc phải bỏ khung (đứng hình): đường truyền CHƯA TỪNG tải nổi mức đang phát (đỉnh nhận < 0,85 × bộ nén
           xuất, đo ≥ 2,5 giây) mà app đang chậm dần (> 0,4 giây) → hạ ngay xuống 0,82 × sức đo được. Gọi mỗi nhịp canh (0,25 giây)."""
        if self.prodlog is None or not self.ack_t or now - self.ack_t > 1.5 or now - self.rate_t <= RATE_DOWN_GAP or self.restart_req: return False
        if self._behind_ms() < 400: return False
        est = self._link_est(now)
        if not est or est[0] >= 0.85 * est[1]: return False
        return self._lower(now, est, True, early=True)

    def _on_ack(self, ack):
        now = time.time(); self.ack_pts = ack; self.ack_t = now
        self.lag_ms = int(time.monotonic() * 1000 - ack / 1000)
        got = 0; last_t = None
        while self.inflight and self.inflight[0][0] <= ack:
            _, n, last_t = self.inflight.popleft(); got += n
        if got: self.delivered.append((now, got))
        while self.delivered and now - self.delivered[0][0] > 7: self.delivered.popleft()
        if last_t is not None:
            self.lat.append((now, (now - last_t) * 1000))
            while self.lat and now - self.lat[0][0] > 10: self.lat.popleft()
            self.base_ms = min(250.0, min(s for _, s in self.lat))     # trễ nền của mạng (tối đa 0,25 s — lớn hơn là đang nghẽn, không phải mạng xa)

    async def _receiver(self):
        c = self.ctl
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), 15)
            self.last_rx = time.time()
            try:
                if t == C_TOUCH and len(p) >= 6:
                    a, ptr, x, y = struct.unpack(">BBHH", p[:6]); c.touch(a, ptr, x, y)
                elif t == C_ACK and len(p) >= 8:
                    self._on_ack(struct.unpack(">Q", p[:8])[0])
                elif t == C_PING:
                    self.link.send_nowait(S_PONG, p[:8])
                elif t == C_KEY and len(p) >= 9:
                    a, code, meta = struct.unpack(">BII", p[:9]); c.key(1 if a else 0, code, meta)
                elif t == C_TEXT:
                    c.text(p.decode("utf-8", "replace"))
                elif t == C_SCROLL and len(p) >= 8:
                    x, y, h, v = struct.unpack(">HHhh", p[:8]); c.scroll(x, y, h, v)
                elif t == C_CMD:
                    jc = json.loads(p.decode() or "{}"); cmd = str(jc.get("cmd") or "")
                    if cmd in KEYCODE: c.press(KEYCODE[cmd])
                    elif cmd == "rotate": c.rotate(jc.get("to"))
                    elif cmd == "notif": c.notif()
                elif t == C_CLIP and len(p) >= 1:
                    c.clip_set(p[1:].decode("utf-8", "replace"), bool(p[0]))
                elif t == C_KEYFRAME:                       # khung khoá tự có mỗi ~1 giây; quá lâu chưa có thì mới bật lại bộ nén
                    if time.time() - self.last_key_sent > 1.5 and time.time() - self.last_restart > 1.5: self.restart_req = "key"
                elif t == C_QUALITY:
                    j = json.loads(p.decode() or "{}")
                    old_q = self.q
                    if j.get("q") in PRESETS or j.get("q") == "auto":
                        self.q = j["q"]; self.cur_q = "bal" if self.q == "auto" else self.q
                    self.fps_req = int(j.get("fps") or self.fps_req or 0); self.kbps_req = int(j.get("kbps") or 0)
                    self.kbps_cur = self._kbps_start(); self.restart_req = "quality"
                    if "fps" not in j or self.q != old_q:        # 17/11e: khách TỰ chọn chất lượng (không phải app tự xin 30 khung) → dò lại từ đầu
                        if self._rate_forget(): log(f"  {self.name}: khách tự chọn chất lượng → bỏ mức mạng yếu đã nhớ, dò lại từ đầu")
                    else:
                        self.ceil_kbps = 0; self._rate_load()    # app tự xin 30 khung (máy khách giải mã không kịp) → giữ mức đã dò
                elif t == C_BYE:
                    return
            except (ValueError, TypeError, struct.error, json.JSONDecodeError, AttributeError):
                pass

    async def _monitor(self):
        t_stat = time.time(); s0 = b0 = 0; i0 = self.n_in
        while not self.closed:
            await asyncio.sleep(0.25)
            if time.time() - self.last_rx > 15: self.why = self.why or "15 giây app không gửi gì"; return
            try:
                if time.time() - self.t_auth >= REAUTH_S:
                    self.t_auth = time.time()
                    d = await asyncio.to_thread(recheck, self.pid, self.me)
                    if d:
                        log(f"  {self.name}: hết quyền ({d.code}) → ngắt phiên của {str(self.me.get('uid'))[:8]}")
                        raise d
                if self.src and (self.src.resized() or getattr(self.src, "closed", False)):
                    if self.src.resized():
                        await asyncio.sleep(0.35)               # chờ cửa sổ xoay xong
                        log(f"  {self.name}: xoay màn hình → phát lại")
                    else: log(f"  {self.name}: cửa sổ máy đóng/mở lại → quay lại")
                    await self.restart_video(size_msg=True); continue
                if isinstance(self.src, WindowSource):         # cửa sổ ngừng ra hình giữa chừng (giả lập thôi vẽ) → app thấy hình đứng → lấy hình từ Android
                    if self.src.n != self._wn: self._wn, self._wn_t = self.src.n, time.time()
                    elif time.time() - self._wn_t > 5 and time.time() - self.last_restart > 5:
                        log(f"  {self.name}: cửa sổ giả lập ngừng ra hình 5 giây → lấy hình thẳng từ Android (scrcpy)")
                        self.from_android = True; self._wn = -1; wgc_mark_bad(self.name)
                        await self.restart_video(size_msg=True); continue
                if self.enc and self.enc.failed_early() and self.enc.enc == "nvenc":
                    log(f"  {self.name}: card NVIDIA không nén được → CPU x264")
                    _nvenc_broken["until"] = time.time() + 120
                    await self.restart_video(cpu=True); continue
                if self.enc and self.enc.proc and self.enc.proc.poll() is not None and time.time() - self.last_restart > 3:
                    if self._cbv() and (self.sent == 0 or getattr(self.enc, "frames_in", 0) == 0):
                        _CBV_BAD[self.serial] = time.time() + CBV_BAD_S       # 27/11f: cbvideo thoát khi chưa ra hình → máy này dùng scrcpy 30 phút
                        log(f"  {self.name}: cbvideo dừng khi chưa ra hình → lấy hình bằng scrcpy {CBV_BAD_S // 60} phút")
                        await self.restart_video(); continue
                    if self.sent == 0 and getattr(self.enc, "enc", "") == "scrcpy":
                        if (not self.kf_legacy and not self.a9 and not self.is_preview
                                and abs(getattr(self.enc, "iframe", SCR_IFRAME) - SCR_IFRAME) > 1e-6):
                            self.kf_legacy = True; _KF_LEGACY[self.serial] = time.time() + 6 * 3600     # có thể bộ nén không nhận khoảng khung khoá kiểu mới
                            log(f"  {self.name}: scrcpy dừng khi chưa ra khung nào → máy này dùng lại khoảng khung khoá kiểu cũ 6 giờ rồi bật lại")
                        else:
                            self.dead += 1                      # Android không xuất được hình (VD MEmu Android 12 màn 0x0) → đừng bật lại mãi
                        if self.dead >= 3:
                            log(f"  {self.name}: Android không xuất được hình (scrcpy lỗi {self.dead} lần, 0 khung) → báo app")
                            raise Deny("OFFLINE", "Màn hình Android của máy này đang lỗi (máy chủ không lấy được hình). Bấm “Khởi động lại máy” để sửa — vẫn lỗi thì báo hỗ trợ.", fix="reboot")
                    log(f"  {self.name}: bộ nén dừng → bật lại"); await self.restart_video(); continue
                kw = 0.0 if self.is_preview else (KEY_WAIT_S_A9 if self.a9 else KEY_WAIT_S)
                if not getattr(self, "wait_key", False): self._wk_t = 0.0
                elif not self._wk_t:
                    self._wk_t = time.time()
                    if self._cbv(): self._cbv_key()                      # 27/11f: chờ khung khoá (bỏ khung / xoay / mạng) → xin IDR ngay
                elif self._cbv():
                    wt = time.time() - self._wk_t
                    if wt > CBV_KEY_MAX_S and not self.restart_req and time.time() - self.last_restart > 2.0:
                        self.restart_req = "key"; self.n_keyfix += 1; self._wk_t = time.time()   # xin mãi không có khung khoá → bật lại như cũ
                    elif wt > 0.5: self._cbv_key()                       # nhắc lại (lệnh trước có thể tới lúc bộ nén đang bật lại)
                elif (kw > 0 and getattr(self, "sent", 0) > 0 and getattr(self.enc, "enc", "") == "scrcpy" and not self.restart_req
                      and time.time() - self._wk_t > kw and time.time() - self.last_restart > max(2.0, kw)):
                    self.restart_req = "key"; self.n_keyfix += 1; self._wk_t = time.time()   # bỏ khung rồi chờ khung khoá quá lâu → bật lại bộ nén
                if not self.is_preview and getattr(self.enc, "enc", "") == "scrcpy": self._fps_watch()
                if self.restart_req and time.time() - self.last_restart > 1.0:
                    self.restart_req = None; await self.restart_video()
                if not self.is_preview and self._early_down(time.time()): continue      # nhịp sau bật lại bộ nén ở mức mới
                if self._may_raise(time.time()):
                    self.kbps_cur = self._raise_to(time.time()); self.rate_t = time.time()
                    self._rate_save(-1 if self.kbps_cur >= self.kbps_cap * 0.9 else 0)
                    log(f"  {self.name}: mạng ổn → tăng lên {self.kbps_cur} kbps"); await self.restart_video()
            except Closed:
                return
            except Deny as d:
                self.why = self.why or f"báo app {d.code}"
                self.link.send_nowait(S_ERROR, err_json(d.code, d.msg, **getattr(d, "extra", {}))); return
            except Exception as e:                       # bật lại hình lỗi (scrcpy chưa nối được, adb chập chờn…) → thử lại tại chỗ, KHÔNG đóng phiên
                now = time.time()
                self.fail_n = self.fail_n + 1 if now - self.fail_t < 90 else 1; self.fail_t = now
                log(f"  {self.name}: bật lại hình lỗi (lần {self.fail_n}): {str(e).strip()[:160] or type(e).__name__}")
                rs = None if self.is_preview else await asyncio.to_thread(restarting, getattr(self, "phone", None))
                if rs is not None:                       # 16/11c: máy đang khởi động lại → báo chờ (app tự vào lại khi máy lên)
                    self.why = "máy đang khởi động lại"
                    self.link.send_nowait(S_ERROR, err_json("OFFLINE", wake_msg(("kdl", rs)), **wake_extra(("kdl", rs))))
                    return
                if isinstance(e, AdbGone) and self.fail_n >= 2 and not self.is_preview:
                    # adb không thấy máy 2 lần liền (máy vừa tắt / treo giữa chừng) → không thử mù tới 6 lần: gọi bật máy đang TẮT + báo rõ
                    wk = await asyncio.to_thread(boot_if_off, self.phone)
                    self.why = "adb không thấy máy (máy tắt / Android treo)"
                    self.link.send_nowait(S_ERROR, err_json("OFFLINE", wake_msg(wk), **wake_extra(wk)))
                    return
                if self.fail_n >= 6:
                    self.why = "bật lại hình lỗi 6 lần"
                    self.link.send_nowait(S_ERROR, err_json("OFFLINE", MSG_NOVIDEO, fix="reboot"))
                    return
                self.restart_req = self.restart_req or "retry"
                await asyncio.sleep(min(8.0, 1.5 * self.fail_n)); continue
            if time.time() - t_stat >= 2:
                dt = time.time() - t_stat
                st = {"fps": round((self.sent - s0) / dt, 1), "kbps": int((self.bytes - b0) * 8 / dt / 1000), "drop": self.drop,
                      "enc": self.enc.enc if self.enc else "", "q": self.cur_q, "w": self.vw, "h": self.vh, "lag": self.lag_ms,
                      "ctl": self.ctl.mode if self.ctl and self.ctl.ready.is_set() else "…"}
                kc = getattr(self, "kbps_cur", None)
                if (getattr(self, "q", "") == "auto" and kc and kc < getattr(self, "kbps_cap", 0) * 0.6
                        and time.time() - getattr(self, "last_cong", 0.0) < 900):
                    st["weak"] = 1; st["tgt"] = int(kc)                 # app mới: hiện "mạng yếu — đã giảm nét để mượt"
                st["efps"] = round((self.n_in - i0) / dt, 1)           # 27/11e: bộ nén ra bao nhiêu khung/giây (kể cả khung bị bỏ)
                st["rs"] = self.n_restart; st["rk"] = self.n_keyfix   # số lần bật lại bộ nén · trong đó vì chờ khung khoá
                if self.dr: st["dr"] = dict(self.dr)                  # bỏ khung vì đâu (lag / q / wk / full / cut)
                if self.a9: st["a9"] = 1
                if self.n_kreq: st["kq"] = self.n_kreq                # 27/11f: số lần xin khung khoá cbvideo
                self.link.send_nowait(S_STATS, json.dumps(st).encode())
                t_stat = time.time(); s0, b0, i0 = self.sent, self.bytes, self.n_in

    def _on_clip(self, text):                                  # luồng điều khiển → vòng chính
        if not self.closed:
            try: self.loop.call_soon_threadsafe(self.link.send_nowait, S_CLIP, text.encode("utf-8"))
            except RuntimeError: pass

    async def kick(self):
        self.why = self.why or "mở ở nơi khác"
        self.link.send_nowait(S_ERROR, json.dumps({"code": "KICKED", "msg": "Máy đang được mở ở nơi khác."}, ensure_ascii=False).encode())
        await self.finish()

    async def finish(self):
        if self.closed: return
        self.closed = True
        if SESSIONS.get(self.pid) is self: SESSIONS.pop(self.pid, None)
        mark_seen(self.phone, write=True)                    # lúc rời máy = mốc tính "rảnh" của máy
        objs = [x for x in (self.enc, self.src, self.ctl) if x]
        def stop_all():
            for x in objs:
                try: x.stop()
                except Exception: pass
        threading.Thread(target=stop_all, daemon=True).start()    # tắt ffmpeg / quay / scrcpy ở luồng riêng (không chặn máy chủ)
        await self.link.close()
        try: self._rate_save()
        except Exception: pass
        if self.n_keyfix: log(f"  {self.name}: bật lại bộ nén {self.n_keyfix} lần để lấy khung khoá (chờ quá lâu sau khi bỏ khung)")
        log(f"■ {self.name} đóng (gửi {self.sent} khung, bỏ {self.drop}" + (f", {self.kbps_cur} kbps" if self.kbps_cur else "") + ")"
            + f" · {int(time.time() - getattr(self, 't_start', time.time()))} giây" + (f" · {self.why}" if getattr(self, "why", "") else ""))


# ================================================================ XEM TRƯỚC TRỰC TIẾP (ô máy trong danh sách / "Xem tất cả" của app)
PREVIEW_MAX = int(C.get("PREVIEW_MAX") or 40)            # tối đa số ô xem trước cùng lúc trên máy chủ này
PREVIEW_PER_PHONE = 3                                    # mỗi máy tối đa 3 ô (chủ máy + người được chia sẻ trên vài thiết bị)
PREVIEW_FPS = 8
PREVIEWS = {}                                            # mã máy → [Preview…]


class Preview(Session):
    """Hình NHỎ (cạnh dài ≤ 480), 8 khung/giây, ít dữ liệu; KHÔNG điều khiển; KHÔNG đá phiên điều khiển đang mở và không bị
       phiên điều khiển đá (nhiều thiết bị xem cùng lúc). Hình lấy THẲNG từ Android (scrcpy-server nén ngay trong máy): không đụng
       tới cửa sổ giả lập (phiên điều khiển đang quay cửa sổ không bị xê dịch / mất hình) và không tốn ffmpeg của máy chủ."""
    is_preview = True

    def __init__(self, link, me, phone, hello, t_hello):
        super().__init__(link, me, phone, hello, t_hello)
        try: self.pmax = max(160, min(480, int(hello.get("maxh") or 480)))
        except (TypeError, ValueError): self.pmax = 480
        self.q = self.cur_q = "eco"

    def _dims(self):
        try: fps = max(2, min(PREVIEW_FPS, int(self.phone.get("fps") or 30)))
        except (TypeError, ValueError): fps = PREVIEW_FPS
        sw, sh = self.src.cw, self.src.ch
        sc = min(1.0, self.pmax / max(sw, sh, 1))
        ow, oh = (sw, sh) if sc >= 0.999 else (max(16, int(sw * sc) & ~7), max(16, int(sh * sc) & ~7))
        kbps = max(120, int(320 * (max(ow, oh) / 480) ** 2))
        self.kbps_cap = self.kbps_cur = kbps
        return ow, oh, fps, kbps

    def _start_video(self, cpu=False):
        if video_mode() == "fake": return super()._start_video(cpu=True)     # chạy thử (không có Android) → hình giả
        return self._start_video_scrcpy()

    def _congested(self, hard=False):                    # mạng chậm → chỉ bỏ khung (không bật lại bộ nén cho ô nhỏ)
        self.calm_since = time.time()

    async def _receiver(self):
        while not self.closed:
            t, p = await asyncio.wait_for(self.link.recv(), 15)
            self.last_rx = time.time()
            try:
                if t == C_ACK and len(p) >= 8: self._on_ack(struct.unpack(">Q", p[:8])[0])
                elif t == C_PING: self.link.send_nowait(S_PONG, p[:8])
                elif t == C_KEYFRAME:
                    if time.time() - self.last_key_sent > 1.5 and time.time() - self.last_restart > 1.5: self.restart_req = "key"
                elif t == C_BYE: return
            except (ValueError, TypeError, struct.error):
                pass

    async def run(self):
        if sum(len(v) for v in PREVIEWS.values()) >= PREVIEW_MAX:
            self.link.send_nowait(S_ERROR, json.dumps({"code": "BUSY", "msg": "Máy chủ đang bận — tạm tắt hình xem trước."}, ensure_ascii=False).encode())
            await self.link.close(); return
        lst = PREVIEWS.setdefault(self.pid, [])
        while len(lst) >= PREVIEW_PER_PHONE:                                # ô cũ nhất nhường chỗ — báo để app đó thôi nối lại (không giành qua lại)
            old = lst[0]
            try: old.link.send_nowait(S_ERROR, json.dumps({"code": "PREVIEW_LIMIT", "msg": "Máy đang được xem trước ở nhiều nơi."}, ensure_ascii=False).encode())
            except Exception: pass
            await old.finish()
            if old in lst: lst.remove(old)
        lst = PREVIEWS.setdefault(self.pid, []); lst.append(self)
        mark_seen(self.phone, write=True)
        log(f"▷ xem trước {self.name} ← {self.me['uid'][:8]} ({self.link.kind})")
        try:
            async with self.vlock:
                w, h = await asyncio.to_thread(self._start_video)
            self.last_restart = time.time()
        except Closed:
            await self.finish(); return
        except Deny as d:
            self.link.send_nowait(S_ERROR, err_json(d.code, d.msg, **getattr(d, "extra", {}))); await self.finish(); return
        except AdbGone:                                        # máy tắt / Android chưa lên: ô đứng yên, thử lại sau (xem trước KHÔNG bật máy)
            self.link.send_nowait(S_ERROR, err_json("OFFLINE", "Máy đang tắt hoặc đang khởi động lại.")); await self.finish(); return
        except Exception as e:
            log("  lỗi bật hình xem trước:", repr(e))
            self.link.send_nowait(S_ERROR, json.dumps({"code": "INTERNAL", "msg": "Chưa bật được hình xem trước."}, ensure_ascii=False).encode())
            await self.finish(); return
        if self.closed: return
        self.wait_key = True
        self.link.welcomed = True
        self.link.send_nowait(S_WELCOME, json.dumps({"ok": True, "w": w, "h": h, "fps": self.fps, "kbps": self.kbps, "codec": "h264",
                                                      "enc": self.enc.enc, "name": self.phone.get("name") or self.name,
                                                      "android": str(self.phone.get("android") or ""), "q": "preview", "preview": True},
                                                     ensure_ascii=False).encode())
        tasks = [asyncio.create_task(x) for x in (self._sender(), self._receiver(), self._monitor())]
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pend: t.cancel()
        await self.finish()

    async def finish(self):
        if self.closed: return
        self.closed = True
        lst = PREVIEWS.get(self.pid) or []
        if self in lst: lst.remove(self)
        if not lst: PREVIEWS.pop(self.pid, None)
        mark_seen(self.phone, write=True)
        objs = [x for x in (self.enc, self.src) if x]
        def stop_all():
            for x in objs:
                try: x.stop()
                except Exception: pass
        threading.Thread(target=stop_all, daemon=True).start()
        await self.link.close()
        log(f"▫ xem trước {self.name} đóng ({self.sent} khung)")


# ================================================================ MÁY NGỦ: ghi ai đang xem · khách mở máy đang ngủ → bật lại
# phonectl idle (cloudphoned gọi ~2 phút/lần) cho máy rảnh lâu NGỦ và đọc redroid/viewers.json (ghi mỗi 30 giây) để KHÔNG BAO GIỜ
# tắt máy đang có người xem. Khách mở máy đang ngủ → gọi `phonectl wake TÊN`: web / app Android nhận OFFLINE "đang thức dậy" (tự thử
# lại vài giây / lần, tự vào khi máy lên) · app PC (gặp lỗi là dừng) được GIỮ kết nối tới khi máy lên rồi vào luôn · ô xem trước của
# máy đang ngủ đứng yên (mở danh sách máy KHÔNG đánh thức cả loạt máy).
VIEW_F = os.path.join(B, "redroid", "viewers.json")
PHONECTL = os.path.join(B, "phonectl.py")
WAKE_HOLD_S = 240              # app PC chờ máy thức dậy tối đa 4 phút
WAKE_RETRY_S = 60              # bật lại lỗi → 1 phút sau khách mở mới thử bật lần nữa
WAKE_SLOW_S = 150              # 17/11g: thức dậy / bật lại quá ngần này giây → câu báo "lâu hơn bình thường"
_SEEN = {}                     # "cổng adb" → lúc có người xem gần nhất
_WAKING = {}                   # tên máy → lần bật lại gần nhất {proc, t, ready, done, ok, msg, end}


def mark_seen(phone, write=False):
    port = str((phone or {}).get("port") or "")
    if port and port != "0": _SEEN[port] = time.time()
    if write and not SELFTEST: write_seen()


def write_seen():
    t = time.time()
    for s in list(SESSIONS.values()) + [x for lst in list(PREVIEWS.values()) for x in lst]:
        if not s.closed: mark_seen(s.phone)
    for k in [k for k, v in _SEEN.items() if t - v > 3 * 86400]: _SEEN.pop(k, None)
    try:
        os.makedirs(os.path.dirname(VIEW_F), exist_ok=True)
        with open(VIEW_F + ".tmp", "w", encoding="utf-8") as f: json.dump({"t": t, "wake": 1, "ver": BS_VER, "seen": _SEEN}, f)
        os.replace(VIEW_F + ".tmp", VIEW_F)
    except OSError:
        pass                   # phonectl đang đọc đúng lúc (Windows không cho thay file đang mở) → lượt sau ghi lại


async def seen_loop():
    try:
        with open(VIEW_F, encoding="utf-8") as f: _SEEN.update({str(k): float(v) for k, v in (json.load(f).get("seen") or {}).items()})
    except Exception:
        pass                   # chưa có file / hỏng → bắt đầu trống
    while True:
        write_seen()
        try: _slice_mem_save()                         # 17/11f: nhớ cách chia lát của từng máy qua lần bật lại phát hình
        except Exception: pass
        await asyncio.sleep(30)


def _pid_alive(pid):
    if WIN:                    # KHÔNG dùng os.kill(pid, 0) trên Windows (= tắt tiến trình)
        try:
            h = _K32.OpenProcess(0x1000, False, int(pid))
            if not h: return False
            try:
                c = ctypes.c_ulong(); ok = ctypes.windll.kernel32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(c))
                return not ok or c.value == 259                  # STILL_ACTIVE
            finally: _K32.CloseHandle(h)
        except Exception:
            return True
    try: os.kill(int(pid), 0); return True
    except (OSError, ValueError): return False


def _proc_ct(pid):
    """16/11e: giờ (giây, Unix) chương trình số pid được chạy — khác giờ ghi trong dấu = số PID đã bị Windows dùng lại cho chương trình khác."""
    try:
        pid = int(pid)
        if WIN:
            h = _K32.OpenProcess(0x1000, False, pid)
            if not h: return None
            try:
                c, e_, kt, ut = (ctypes.c_ulonglong() for _ in range(4))
                if not ctypes.windll.kernel32.GetProcessTimes(ctypes.c_void_p(h), ctypes.byref(c), ctypes.byref(e_), ctypes.byref(kt), ctypes.byref(ut)):
                    return None
                return c.value / 1e7 - 11644473600.0
            finally: _K32.CloseHandle(h)
        st = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
        bt = next(float(l.split()[1]) for l in open("/proc/stat") if l.startswith("btime"))
        return bt + int(st[19]) / os.sysconf("SC_CLK_TCK")
    except Exception:
        return None


def _alive_who(pid, ct=None):
    """Chương trình số pid (chạy lúc ct, nếu dấu có ghi) CÒN đang chạy? Cùng số mà khác giờ chạy → chương trình khác → False."""
    pid = str(pid or "").strip()
    if not pid.isdigit() or not _pid_alive(pid): return False
    try:
        if ct not in (None, ""):
            now_ct = _proc_ct(pid)
            if now_ct is not None and abs(now_ct - float(ct)) > 3: return False
    except (TypeError, ValueError):
        pass
    return True


_PRIO_T = {}
def _prio_touch(name):
    """17/11f: khách đang CHỜ đúng máy mà lệnh khác (đợt bật hàng loạt sau khi máy chủ khởi động lại) đang giữ máy đó trong hàng chờ
       → ghi redroid/prio_<tên>.flag: phonectl thấy dấu thì cho máy đó lên TRƯỚC (không chờ hết hàng). Mỗi máy tối đa 20 giây / lần."""
    if not name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(name)): return
    now = time.time()
    if now - _PRIO_T.get(name, 0) < 20: return
    _PRIO_T[name] = now
    try:
        with open(os.path.join(B, "redroid", f"prio_{name}.flag"), "w") as f: f.write(str(int(now)))
    except OSError: pass


def boot_wave():
    """Đợt bật hàng loạt (phonectl bootall, 17/11f) đang chạy? → {"total", "left": [tên máy chưa lên]} · không → None."""
    try:
        with open(os.path.join(B, "redroid", "bootall.json"), encoding="utf-8") as fh: d = json.load(fh)
        if time.time() - float(d.get("t") or 0) > 45 or not _pid_alive(d.get("pid") or 0): return None
        return d if isinstance(d.get("left"), list) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _wake_lock_alive(name):
    """`phonectl wake` (vd do bluestream TRƯỚC khi khởi động lại gọi) còn đang bật máy này?"""
    f = os.path.join(B, "redroid", f"wake_{name}.lock")
    try:
        if time.time() - os.path.getmtime(f) > 900: return False
        with open(f) as fh: pid = fh.read().strip()
        return pid.isdigit() and _pid_alive(pid)
    except OSError:
        return False


KDL_SLOW_S = 180                   # 16/11e: đang khởi động lại quá chừng này giây → câu báo "máy chủ đang bận nên lâu hơn bình thường"
RESTART_WIN_S = 300                # phonectl ghi redroid/restart_<tên>.json lúc khởi động lại → trong 5 phút: Android chưa xong = "đang khởi động lại"
_RS_OK = {}                        # tên máy → lúc đã thấy Android lên xong sau lần khởi động lại gần nhất


def boot_done(serial):
    """Android đã khởi động XONG (sys.boot_completed = 1)? adb không trả lời → False."""
    if SELFTEST: return True
    adb_connect(serial)
    code, out, _ = adb(serial, "shell", "getprop", "sys.boot_completed", timeout=6)
    if code == -2: return True                             # không có chương trình adb → không kết luận
    return code == 0 and out.strip() == "1"


def _op_mark_t(iv):
    """phonectl (16/11b) đang làm dở với máy số iv (vừa TẮT máy để khởi động lại / đổi cấu hình / root…) → lúc ghi dấu; không → None."""
    f = os.path.join(B, "redroid", f"op_{iv}.mark")
    try:
        t = os.path.getmtime(f)
        if time.time() - t > 900: return None
        with open(f) as fh: w = fh.read().split()                # "PID GIỜ_CHẠY" (phonectl 16/11e) · "PID" (bản cũ)
        return t if w and _alive_who(w[0], w[1] if len(w) > 1 else None) else None
    except (OSError, ValueError):
        return None


def restarting(phone):
    """16/11c: máy đang được KHỞI ĐỘNG LẠI (khách / admin bấm, đổi FPS…) → số giây đã chờ; không → None.
       Trước: khách thoát app rồi mở lại giữa chừng → máy chủ cố lấy hình từ Android chưa lên → báo lỗi "không lấy được hình" + nút
       Khởi động lại (bấm nữa → càng lâu). Giờ: lệnh khởi động lại còn chạy, hoặc vừa khởi động lại (≤ 5 phút) mà Android chưa xong
       → báo "đang khởi động lại, tự vào khi máy lên" (app / web tự thử lại, app PC được giữ chờ)."""
    phone = phone if isinstance(phone, dict) else {}
    name = phone.get("container") or ""
    if not name or SELFTEST: return None
    ps = phones_json().get(name) or {}
    now = time.time(); t0 = None; alive = False
    try:
        with open(os.path.join(B, "redroid", f"restart_{name}.json"), encoding="utf-8") as fh: d = json.load(fh)
        t = float(d.get("t") or 0)
        if 0 <= now - t < RESTART_WIN_S:
            t0 = t; pid = str(d.get("pid") or "")
            alive = _alive_who(pid, d.get("ct"))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if alive: return max(0, int(now - t0))                 # phonectl restart còn đang tắt / bật máy
    port = ps.get("port") or phone.get("port")
    iv = str(ps.get("idx", "")).strip()
    m = _op_mark_t(iv) if iv.isdigit() else None           # lệnh khác (đổi cấu hình, root…) vừa tắt máy và còn làm dở
    if m is None and (t0 is None or _RS_OK.get(name, 0) >= t0): return None
    if port and not boot_done(f"127.0.0.1:{port}"): return max(0, int(now - min(x for x in (t0, m) if x is not None)))
    if t0 is not None: _RS_OK[name] = now                   # Android đã lên sau lần khởi động lại này
    return None


def _wake_reader(name, w):
    p = w["proc"]; last = ""
    try:
        for ln in p.stdout:
            ln = ln.strip()
            if not ln: continue
            last = ln
            if ln.startswith("WAKE_RUNNING"): w["running"] = True      # phonectl 16/11: máy ĐANG CHẠY sẵn (không bật gì) → chỉ chờ Android trả lời
            if ln.startswith("WAKE_READY"):
                w["ready"] = True; log(f"☀ {name}: Android đã lên sau {int(time.time() - w['t'])} giây → khách vào được")
    except Exception:
        pass
    rc = p.wait()
    w["ok"] = rc == 0 and (w["ready"] or last.startswith("WAKE_OK"))
    w["msg"], w["end"], w["done"] = last[:200], time.time(), True
    how = "xong" if w["ok"] else "chờ lệnh khác" if last.startswith("WAKE_BUSY") else "LỖI"     # WAKE_BUSY: lệnh khác đang làm dở với máy đó → vài giây sau thử lại
    log(f"☀ {name}: {how} — {last[:160] or f'mã {rc}'} ({int(w['end'] - w['t'])} giây)")
    if how == "LỖI" and not last.startswith("WAKE_NO"): _diag_async(name)


_DIAG_T = {}                   # tên máy → lần khám gần nhất
def _diag_async(name):
    """17/11g: bật máy LỖI → gọi `phonectl khammay TÊN` (CHỈ ĐỌC, không sửa / không tắt bật gì) ở luồng nền, ghi dòng kết luận vào nhật ký
       (lệnh A đọc lại để báo admin VÌ SAO máy không lên). Mỗi máy tối đa 1 lần / 10 phút. Không bao giờ ném lỗi."""
    try:
        now = time.time()
        if now - _DIAG_T.get(name, 0) < 600: return
        _DIAG_T[name] = now
        def run():
            try:
                r = subprocess.run([sys.executable, PHONECTL, "khammay", name], cwd=B, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=180, creationflags=NOWIN)
                for ln in (r.stdout or "").splitlines():
                    ln = ln.strip()
                    if ln.startswith("KHAMMAY " + name + ":") or ln.startswith("dấu hiệu sập:"): log("🩺 " + ln[:300])
            except Exception as e:
                log(f"🩺 {name}: không khám được ({e!r})"[:200])
        threading.Thread(target=run, daemon=True).start()
    except Exception:
        pass


def _start_wake(name, why=""):
    """why="off": adb không thấy máy lúc khách mở (không phải máy ngủ) — thông báo cho khách khác đi."""
    t = time.time()
    try:
        p = subprocess.Popen([sys.executable, PHONECTL, "wake", name], cwd=B, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, creationflags=NOWIN, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        _WAKING[name] = {"proc": None, "t": t, "ready": False, "done": True, "ok": False, "msg": f"không chạy được phonectl: {e}", "end": t,
                         "why": why, "running": False}
        log(f"☀ {name}: không gọi được phonectl wake: {e!r}"); return
    w = _WAKING[name] = {"proc": p, "t": t, "ready": False, "done": False, "ok": False, "msg": "", "end": 0.0, "why": why, "running": False}
    log(f"☀ {name}: khách mở máy đang NGỦ → bật lại" if why != "off" else
        f"☀ {name}: khách mở máy mà adb không thấy máy (máy tắt / Android chưa lên) → gọi phonectl wake (chỉ bật máy đang TẮT, không khởi động lại máy đang chạy)")
    threading.Thread(target=_wake_reader, args=(name, w), daemon=True).start()


def _wk_live(w):
    """Lệnh bật máy đang chạy → tình trạng báo khách: máy ngủ "day" · máy tắt "bat" · máy đang chạy mà Android chưa trả lời quá lâu "treo"."""
    el = time.time() - w["t"]; s = int(el)
    if w.get("why") != "off": return ("day", s)
    return ("treo", s) if w.get("running") and el > HUNG_S else ("bat", s)


def boot_if_off(phone):
    """adb KHÔNG thấy máy lúc khách mở / đang xem (máy tắt mà không phải "ngủ", Android treo, máy không có trên máy chủ này…).
       Gọi `phonectl wake TÊN`: phonectl CHỈ bật máy đang TẮT (máy đang chạy thì chỉ chờ Android — không bao giờ khởi động lại máy
       đang chạy của khách), máy admin tạm dừng thì không bật. Trả (tình trạng, giây đã chờ | lý do):
       "bat" đang bật · "treo" máy chạy mà Android không trả lời · "loi" bật lỗi · "khoa" máy đang tạm dừng · "mat" máy chủ không có máy này."""
    name = phone.get("container") or ""
    if SELFTEST or not name: return ("loi", "")
    now = time.time(); w = _WAKING.get(name)
    if w and not w["done"]:
        return ("treo", int(now - w["t"])) if w["ready"] else _wk_live(w)     # phonectl báo máy lên rồi mà adb ở đây vẫn không thấy → gợi ý khởi động lại
    if _wake_lock_alive(name): _prio_touch(name); return ("bat", 0)          # 17/11f: lệnh khác đang bật (đợt bật hàng loạt) → cho máy này lên trước
    if w:
        age = now - w["end"]
        if not w["ok"] and age < WAKE_RETRY_S and not w["msg"].startswith("WAKE_BUSY"):
            if w["msg"].startswith("WAKE_NO"): return ("khoa", w["msg"])
            return ("treo" if w.get("running") else "loi", w["msg"])
        if w["ok"] and age < BOOT_AGAIN_S: return ("treo", 0)
    pj = phones_json()
    if pj and name not in pj: return ("mat", "")
    if not BOOT_IF_OFF: return ("loi", "BOOT_IF_OFF=0")
    _start_wake(name, why="off")
    return ("bat", 0)


def wake_check(phone, start=True):
    """None = máy thức → mở bình thường. Không thì ("ngu" | "day" | "loi" | "kdl", giây đã chờ | lý do).
       start=True (phiên điều khiển): máy đang ngủ → tự gọi bật lại. Xem trước (start=False) không đánh thức máy."""
    name = phone.get("container") or ""
    if not name: return None
    rs = restarting(phone)                             # 16/11c: đang khởi động lại → chờ, khỏi cố lấy hình rồi báo lỗi
    if rs is not None: return ("kdl", rs)
    w = _WAKING.get(name)
    if w and not w["done"]:
        return None if w["ready"] else _wk_live(w)
    ps = phones_json().get(name) or {}
    if not (ps.get("sleep") and ps.get("hold")):        # dấu ngủ + hold = đang ngủ thật (dấu sót mà hold đã gỡ → máy thức)
        if not _wake_lock_alive(name): return None
        if start: _prio_touch(name)                     # 17/11f: khách đang chờ máy này → lên trước trong đợt bật
        return ("day", 0)
    if not start: return ("ngu", 0)
    if _wake_lock_alive(name): return ("day", 0)
    if w and not w["ok"] and time.time() - w["end"] < WAKE_RETRY_S and not w["msg"].startswith("WAKE_BUSY"):
        return ("loi", w["msg"])                       # vừa bật lỗi → chưa thử lại ngay (WAKE_BUSY = lệnh khác đang bật máy này: chờ tiếp)
    _start_wake(name)
    return ("day", 0)


def wake_msg(wk):
    k = wk[0]; s = wk[1] if isinstance(wk[1], int) else 0
    t = f", đã {s} giây" if s >= 5 else ""
    if k == "loi": return "Máy chưa bật lại được — máy chủ sẽ tự thử lại. Bấm “Khởi động lại máy” để sửa nhanh; quá 5 phút vẫn vậy thì báo hỗ trợ."
    if k in ("bat", "day") and boot_wave():             # 17/11f: máy chủ vừa khởi động lại, đang bật lại hàng loạt
        return "🔄 Máy chủ vừa khởi động lại và đang bật lại các máy — máy của bạn được ưu tiên vì bạn đang mở" + t + ". Khoảng 1–3 phút, tự vào khi máy lên; dữ liệu giữ nguyên."
    if k in ("bat", "day") and s >= WAKE_SLOW_S:        # 17/11g: quá 2,5 phút → nói thật (máy chủ bận / đang tự sửa máy), dặn cứ chờ
        return ("⏳ Máy lên lâu hơn bình thường" + t + " — máy chủ đang bận hoặc đang tự sửa máy sau sự cố. Cứ để yên: máy tự vào khi lên "
                "(tối đa khoảng 5 phút), dữ liệu giữ nguyên.")
    if k == "bat": return "🔄 Máy đang được bật lại — khoảng 1–2 phút" + t + ". Tự vào khi máy lên."
    if k == "kdl" and s >= KDL_SLOW_S:                 # 16/11e: quá 3 phút → nói thật là máy chủ đang bận (trước cứ "khoảng 1–2 phút, đã 348 giây")
        return "🔄 Máy đang khởi động lại — máy chủ đang bận nên lâu hơn bình thường" + t + ". Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào."
    if k == "kdl": return "🔄 Máy đang khởi động lại — khoảng 1–2 phút" + t + ". Bạn có thể thoát ra, máy vẫn tự khởi động; mở lại là vào."
    if k == "treo": return "Máy đang bật nhưng Android chưa trả lời" + t + ". Chờ thêm ít phút, hoặc bấm “Khởi động lại máy” để sửa nhanh (1–2 phút, dữ liệu giữ nguyên)."
    if k == "khoa": return "Máy đang tạm dừng trên máy chủ. Bấm “Khởi động lại máy” để bật lại; không được thì báo hỗ trợ."
    if k == "mat": return "Máy chủ chưa có máy này (có thể đang được tạo lại). Chờ ít phút; vẫn vậy thì báo hỗ trợ kèm tên máy."
    return "💤 Máy đang thức dậy sau khi tự nghỉ (lâu không dùng) — thường 1–2 phút" + t + ". Tự vào khi máy lên."


def wake_extra(wk):
    """Trường phụ của S_ERROR cho app mới: boot=1 máy đang được bật (cứ chờ) · fix="reboot" nên hiện nút Khởi động lại máy."""
    k = wk[0]
    return {"boot": 1 if k in ("day", "bat", "treo", "kdl") else 0, "fix": "reboot" if k in ("loi", "treo", "khoa") else ""}


async def hold_for_wake(link, phone, wk):
    """App PC gặp lỗi là dừng hẳn → GIỮ kết nối (trả lời ping: app không tưởng mất mạng) tới khi máy thức dậy rồi vào luôn."""
    t0 = time.time()
    while wk:
        bad = wk[0] in ("loi", "khoa", "treo", "mat")           # không phải cứ chờ là lên → báo luôn (app PC hiện nút Khởi động lại máy)
        if bad or time.time() - t0 > WAKE_HOLD_S:
            if bad: msg, ex = wake_msg(wk), wake_extra(wk)
            elif wk[0] == "kdl": msg, ex = wake_msg(wk), wake_extra(wk)   # 16/11e: đang khởi động lại → báo chờ (app tự thử lại), KHÔNG bảo bấm khởi động lại lần nữa
            elif wk[0] == "day": msg, ex = "Máy chưa thức dậy sau 4 phút — mở lại sau ít phút hoặc báo hỗ trợ.", {"fix": "reboot"}
            else: msg, ex = "Máy chưa lên sau 4 phút — bấm “Khởi động lại máy” hoặc báo hỗ trợ.", {"fix": "reboot"}
            link.send_nowait(S_ERROR, err_json("OFFLINE", msg, **ex)); await link.close(); return False
        mark_seen(phone)
        try:
            t, p = await asyncio.wait_for(link.recv(), 2.5)
            if t == C_PING: link.send_nowait(S_PONG, p[:8])
            elif t == C_BYE: await link.close(); return False
        except asyncio.TimeoutError:
            pass
        wk = await asyncio.to_thread(wake_check, phone, True)
    ps = phones_json().get(phone.get("container") or "") or {}
    if ps.get("port"): phone["port"] = ps["port"]          # cổng adb thật sau khi bật lại
    log(f"☀ {phone.get('container')}: app PC chờ {int(time.time() - t0)} giây → vào máy")
    return True


async def hello_keepalive(link):
    """Từ lúc nhận HELLO tới lúc gửi WELCOME (kiểm quyền qua Supabase, đánh thức máy, quay cửa sổ giả lập chờ 6–15 giây rồi mới
       sang scrcpy…) có thể quá 6 giây = ngưỡng app (web / Android / PC) coi là đứt → app nối lại → phiên mới bắt đầu lại từ đầu
       → khách quay mãi "Đang kết nối lại" không vào được. 2 giây gửi 1 PONG RỖNG: app nào cũng tính là 'có nhận', bỏ qua vì ngắn
       hơn 8 byte (web / Android / PC đều kiểm độ dài từ bản đầu) → app chờ tới khi có hình."""
    n = 0
    try:
        while True:
            await asyncio.sleep(2)
            if link.closed or link.welcomed: break
            link.send_nowait(S_PONG, b""); n += 1
    except asyncio.CancelledError:
        pass
    return n


async def serve_link(link):
    ka = None
    try:
        t, p = await asyncio.wait_for(link.recv(), 10)
        t_hello = time.monotonic()
        if PCRELAY and t == PCRELAY.P_HELLO: return await PCRELAY.serve_source(sys.modules[__name__], link, p)     # 21/11a: máy PC cho thuê xin vào trạm
        if t != C_HELLO: raise ValueError("no hello")
        hello = json.loads(p.decode("utf-8"))
        if PCRELAY and isinstance(hello, dict) and hello.get("pc"): return await PCRELAY.serve_viewer(sys.modules[__name__], link, hello)   # 21/11a: khách mở điều khiển máy PC
        ka = asyncio.ensure_future(hello_keepalive(link))
        try:
            me, phone = await asyncio.to_thread(authorize, hello)
        except Deny as d:
            link.send_nowait(S_ERROR, err_json(d.code, d.msg, **getattr(d, "extra", {}))); await link.close(); return
        preview = str(hello.get("mode") or "") == "preview"
        wk = None if SELFTEST else await asyncio.to_thread(wake_check, phone, not preview)
        if wk:
            if preview:                                    # máy ngủ: ô đứng yên (app thôi nối lại) · đang thức dậy: app thử lại sau
                code, msg = ("PREVIEW_LIMIT", "Máy đang nghỉ — mở máy để bật lại.") if wk[0] == "ngu" else ("OFFLINE", wake_msg(wk))
                link.send_nowait(S_ERROR, err_json(code, msg)); await link.close(); return
            if str(hello.get("client") or "") == "pc":
                if not await hold_for_wake(link, phone, wk): return
            else:
                mark_seen(phone)
                link.send_nowait(S_ERROR, err_json("OFFLINE", wake_msg(wk), **wake_extra(wk))); await link.close(); return
        if preview: await Preview(link, me, phone, hello, t_hello).run()
        else: await Session(link, me, phone, hello, t_hello).run()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, EOFError, ssl.SSLError, ValueError, OSError):
        await link.close()
    except Exception as e:
        log("lỗi phiên:", repr(e)); await link.close()
    finally:
        if ka: ka.cancel()


CPAPI_LOCAL = ("127.0.0.1", int(C.get("CPAPI_PORT") or 8010))
HTTP_VERBS = (b"GET ", b"POST", b"PUT ", b"HEAD", b"OPTI", b"DELE", b"PATC")


async def http_to_cpapi(head, reader, writer, line=None):
    """CÔNG CỤ MÁY qua chính cổng TLS này (cài APK, clone tab, khởi động lại, chụp màn…): chuyển thẳng tới cpapi 127.0.0.1:8010.
       App không cần tên miền / Cloudflare. cpapi tự kiểm phiên đăng nhập + quyền với từng máy như khi đi qua web."""
    uw = None
    try:
        if line is None: line = head + await asyncio.wait_for(reader.readuntil(b"\r\n"), 15)
        parts = line.split(b" ")
        if len(parts) != 3 or not parts[1].startswith(b"/cpapi/"):
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"); await writer.drain(); return
        ur, uw = await asyncio.wait_for(asyncio.open_connection(*CPAPI_LOCAL), 5)
        uw.write(line)
        async def pipe(r, w):
            while True:
                b = await r.read(256 * 1024)
                if not b: return
                w.write(b); await w.drain()
        tasks = {asyncio.ensure_future(pipe(reader, uw)), asyncio.ensure_future(pipe(ur, writer))}
        done, pend = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)   # 1 chiều xong (cpapi trả lời xong / app đóng) → đóng cả 2
        for t in pend: t.cancel()
        for t in done:
            try: t.exception()
            except BaseException: pass
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
        if uw is None:                                        # cpapi (đèn "Cổng bảo vệ :8010") đang tắt
            try:
                body = json.dumps({"error": "Công cụ máy đang tắt trên máy chủ (cổng bảo vệ :8010) — thử lại sau ít phút."}, ensure_ascii=False).encode()
                writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\nConnection: close\r\n"
                             + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
            except Exception: pass
    except Exception as e:
        log("công cụ (HTTP) lỗi:", repr(e))
    finally:
        for w in (uw, writer):
            if w is None: continue
            try: w.close()
            except Exception: pass


async def on_direct(reader, writer):
    note_direct_peer(writer)
    try: head = await asyncio.wait_for(reader.readexactly(4), 20)
    except Exception:
        try: writer.close()
        except Exception: pass
        return
    if head in HTTP_VERBS:
        try: line = head + await asyncio.wait_for(reader.readuntil(b"\r\n"), 15)
        except Exception:
            try: writer.close()
            except Exception: pass
            return
        p = line.split(b" ")
        if head == b"GET " and len(p) == 3 and p[1].split(b"?")[0] == b"/v2/stream":         # TRÌNH DUYỆT đi thẳng (WebSocket)
            try: link = await WSLink.accept(reader, writer, first=line, direct=True)
            except Exception:
                try: writer.close()
                except Exception: pass
                return
            if link: await serve_link(link)
            return
        return await http_to_cpapi(head, reader, writer, line=line)              # app gọi công cụ máy (HTTP)
    await serve_link(DirectLink(reader, writer, head))                          # app xem / điều khiển (BRS2)


async def on_ws(reader, writer):
    try: link = await WSLink.accept(reader, writer)
    except Exception:
        try: writer.close()
        except Exception: pass
        return
    if link: await serve_link(link)


# ================================================================ Chứng chỉ TLS (tự ký, app kiểm bằng mã SHA-256)
def ensure_cert():
    if not (os.path.isfile(CERT) and os.path.isfile(CKEY)):
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            log("cài thư viện cryptography (tạo chứng chỉ)…")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "cryptography"], creationflags=NOWIN)
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.generate_private_key(ec.SECP256R1())
        nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bluestream " + NODE_ID)])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(k.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650)).sign(k, hashes.SHA256()))
        open(CKEY, "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        open(CERT, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    pem = open(CERT, encoding="ascii").read()
    der = ssl.PEM_cert_to_DER_cert(pem)
    return hashlib.sha256(der).hexdigest()


# ================================================================ Báo đường nối lên Supabase (app đọc qua cloudphone_endpoint)
def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except OSError:
        return None


def public_ip():
    if C.get("STREAM_PUBLIC_IP"): return C["STREAM_PUBLIC_IP"]
    for u in ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"):
        try:
            ip = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "BlueRoblox"}), timeout=8).read().decode().strip()
            if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip): return ip
        except Exception: pass
    return None


def publish_loop(fp):
    warned = False; last = None
    while True:
        try:
            direct = []
            lip, pip_ = lan_ip(), public_ip()
            if lip: direct.append({"host": lip, "port": PORT, "lan": True})
            if pip_ and pip_ != lip: direct.append({"host": pip_, "port": PORT})
            stream = {"direct": direct, "cert": fp, "ws": WS_URL or None, "api": API_BASE, "v": 2,
                      "preview": 1}          # có hình xem trước trực tiếp (app chỉ bật ô xem trước khi máy chủ báo có — máy chủ cũ sẽ đá phiên điều khiển)
            wss = web_url(pip_)
            if wss: stream["wss"] = wss       # web / iPhone đi THẲNG (play.html web-1.2 thử trước, không được thì đi "ws")
            if PCRELAY: stream["pc"] = 1      # 21/11a: máy chủ này nhận trung chuyển máy PC cho thuê (SQL v43 chỉ giao máy PC cho máy chủ có cờ này)
            if stream != last:
                log(f"đường nối: trực tiếp {', '.join(d['host'] + ':' + str(d['port']) for d in direct) or '—'}"
                    + (f" · web thẳng {wss}" if wss else "")
                    + (f" · dự phòng {WS_URL}" if WS_URL else " · (chưa có dự phòng Cloudflare STREAM_WS)"))
            sb("PATCH", f"/rest/v1/cloud_nodes?id=eq.{urllib.parse.quote(NODE_ID)}", {"stream": stream}, extra={"Prefer": "return=minimal"})
            last = stream
        except urllib.error.HTTPError as e:
            if not warned: log(f"chưa báo được đường nối lên web (HTTP {e.code}) — đã chạy SQL v20 chưa?"); warned = True
        except Exception as e:
            if not warned: log("chưa báo được đường nối lên web:", e); warned = True
        time.sleep(60)


# ================================================================ ĐƯỜNG THẲNG CHO WEB / iPhone (wss://dN.<miền>:PORT/v2/stream)
# Trình duyệt chỉ nói WebSocket + chứng chỉ thật → trước đây web/iPhone luôn đi vòng Cloudflare (đo 11/11: 7,5 hình/s, bỏ 13–29 %
# khung) trong khi app đi thẳng (27 hình/s, bỏ 0 %). Giờ CHÍNH cổng phát hình của app (STREAM_PORT, modem đã mở) nhận luôn trình
# duyệt: tên dN.<miền> (bản ghi A, mây XÁM) trỏ IP nhà mạng (tự cập nhật khi IP đổi) + chứng chỉ Let's Encrypt (DNS-01 bằng mã
# Cloudflare CF_DNS_TOKEN, tự gia hạn). Trình duyệt gửi SNI dN.<miền> → chứng chỉ thật; app nối bằng IP (không SNI) → chứng chỉ tự
# ký cũ (app vẫn kiểm mã SHA-256). Chỉ báo web (stream.wss) khi có chứng chỉ, tên đã trỏ đúng IP và cổng modem đã mở (có máy ở
# ngoài mạng nối thẳng trong 7 ngày). Web thử đường thẳng trước 3,5 giây, không được thì đi Cloudflare như cũ.
# Bật lần đầu (hỏi mã Cloudflare + đồng ý điều khoản Let's Encrypt):  python bluestream.py --webdirect      Tắt: WEB_DIRECT=0
CF_TOKEN = (C.get("CF_DNS_TOKEN") or "").strip()
CF_API = (C.get("CF_API") or "https://api.cloudflare.com/client/v4").rstrip("/")
WEB_DIRECT = str(C.get("WEB_DIRECT", "1")).strip().lower() not in ("0", "off", "false", "no")
LE_AGREE = str(C.get("LE_AGREE", "")).strip() == "1"
ACME_DIR = (C.get("ACME_DIRECTORY") or "https://acme-v02.api.letsencrypt.org/directory").strip()
DOH_URL = (C.get("DOH_URL") or "https://cloudflare-dns.com/dns-query").strip()
ACME_TXT_WAIT = float(C.get("ACME_TXT_WAIT") or 10)
WEB_PROOF = 7 * 86400                # cổng modem coi là đã mở nếu có máy ngoài mạng nối thẳng trong 7 ngày


def _zone_of(h):
    p = [x for x in (h or "").split(":")[0].split(".") if x]
    n = 3 if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ("com", "net", "org", "edu", "gov", "co", "ac", "info", "biz") else 2
    return ".".join(p[-n:]).lower() if len(p) >= n else ""


ZONE = (C.get("CF_ZONE") or _zone_of(urllib.parse.urlparse(API_BASE).hostname or "") or "cloudblue.vn").strip().lower()
WEB_HOST = (C.get("WEB_DIRECT_HOST") or ("d" + (re.sub(r"\D", "", NODE_ID) or re.sub(r"[^a-z0-9-]", "", NODE_ID.lower())) + "." + ZONE)).strip().lower()
LE_DIR = os.path.join(B, "le")
LE_ACC = os.path.join(LE_DIR, "account-key.pem")
LE_KEY = os.path.join(LE_DIR, WEB_HOST + "-key.pem")
LE_CRT = os.path.join(LE_DIR, WEB_HOST + "-fullchain.pem")
WEB = {"ctx": None, "mtime": 0.0, "dns_ip": None, "dns_t": 0.0, "err": ""}


class CfError(RuntimeError):
    pass


class AcmeError(RuntimeError):
    pass


def _cf_msg(d):
    return "; ".join(f"{x.get('code')}: {x.get('message')}" for x in (d.get("errors") or []) if isinstance(x, dict))


def cf_api(method, path, body=None):
    req = urllib.request.Request(CF_API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + CF_TOKEN, "Content-Type": "application/json",
                                          "User-Agent": "CloudBlue-bluestream"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r: d = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: d = json.loads(e.read().decode() or "{}")
        except Exception: d = {}
        raise CfError("Cloudflare " + (_cf_msg(d) or f"HTTP {e.code}")) from None
    if not d.get("success"): raise CfError("Cloudflare " + (_cf_msg(d) or "báo lỗi"))
    return d.get("result")


_CF_Z = {}


def cf_zone():
    if ZONE not in _CF_Z:
        r = cf_api("GET", "/zones?name=" + urllib.parse.quote(ZONE))
        if not r: raise CfError(f"mã Cloudflare không thấy tên miền {ZONE} (cần quyền Zone · Zone · Read + Zone · DNS · Edit cho {ZONE})")
        _CF_Z[ZONE] = r[0]["id"]
    return _CF_Z[ZONE]


def web_dns(ip):
    """dN.<miền> → IP nhà mạng (bản ghi A, mây XÁM: trình duyệt nói thẳng với máy chủ). True = vừa đổi."""
    body = {"type": "A", "name": WEB_HOST, "content": ip, "ttl": 60, "proxied": False}
    recs = cf_api("GET", f"/zones/{cf_zone()}/dns_records?type=A&name={urllib.parse.quote(WEB_HOST)}") or []
    if recs and recs[0].get("content") == ip and not recs[0].get("proxied"): return False
    if recs: cf_api("PUT", f"/zones/{cf_zone()}/dns_records/{recs[0]['id']}", body)
    else: cf_api("POST", f"/zones/{cf_zone()}/dns_records", body)
    return True


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _write_private(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as f: f.write(data)
    os.replace(path + ".tmp", path)


def _ec_key(path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    if os.path.isfile(path):
        with open(path, "rb") as f: return serialization.load_pem_private_key(f.read(), None)
    k = ec.generate_private_key(ec.SECP256R1())
    _write_private(path, k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return k


def _acme_why(d):
    errs = [d.get("error")] + [c.get("error") for c in d.get("challenges") or []]
    msg = "; ".join(f"{(e.get('type') or '').split(':')[-1]} {e.get('detail') or ''}".strip() for e in errs if isinstance(e, dict))
    if "caa" in msg.lower(): msg += f" → tên miền có bản ghi CAA chặn: thêm CAA  0 issue \"letsencrypt.org\"  cho {ZONE}"
    return msg or f"trạng thái {d.get('status')}"


class Acme:
    """ACME v2 (RFC 8555) tối giản: khoá EC P-256 (ES256), chỉ DNS-01. Chỉ cần thư viện cryptography (đã có để tạo chứng chỉ app)."""
    def __init__(self, key, directory=None):
        self.key, self.kid, self.nonce = key, None, None
        with urllib.request.urlopen(urllib.request.Request(directory or ACME_DIR, headers=self._h()), timeout=30) as r:
            self.dir = json.loads(r.read().decode())

    @staticmethod
    def _h(extra=None):
        h = {"User-Agent": "CloudBlue-bluestream/" + BS_VER}
        h.update(extra or {})
        return h

    def jwk(self):
        n = self.key.public_key().public_numbers()
        return {"crv": "P-256", "kty": "EC", "x": _b64u(n.x.to_bytes(32, "big")), "y": _b64u(n.y.to_bytes(32, "big"))}

    def thumbprint(self):                # RFC 7638: các khoá bắt buộc, xếp theo tên, không khoảng trắng
        return _b64u(hashlib.sha256(json.dumps(self.jwk(), sort_keys=True, separators=(",", ":")).encode()).digest())

    def _new_nonce(self):
        with urllib.request.urlopen(urllib.request.Request(self.dir["newNonce"], method="HEAD", headers=self._h()), timeout=30) as r:
            return r.headers["Replay-Nonce"]

    def post(self, url, payload):
        """payload None = POST-as-GET. Trả (headers, bytes)."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        for tries in range(4):
            nonce, self.nonce = (self.nonce or self._new_nonce()), None
            prot = {"alg": "ES256", "nonce": nonce, "url": url}
            if self.kid: prot["kid"] = self.kid
            else: prot["jwk"] = self.jwk()
            p64 = "" if payload is None else _b64u(json.dumps(payload).encode())
            h64 = _b64u(json.dumps(prot).encode())
            r_, s_ = decode_dss_signature(self.key.sign(f"{h64}.{p64}".encode(), ec.ECDSA(hashes.SHA256())))
            body = json.dumps({"protected": h64, "payload": p64, "signature": _b64u(r_.to_bytes(32, "big") + s_.to_bytes(32, "big"))}).encode()
            req = urllib.request.Request(url, data=body, method="POST", headers=self._h({"Content-Type": "application/jose+json"}))
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    self.nonce = r.headers.get("Replay-Nonce")
                    return r.headers, r.read()
            except urllib.error.HTTPError as e:
                self.nonce = e.headers.get("Replay-Nonce")
                raw = e.read()
                try: err = json.loads(raw.decode() or "{}")
                except Exception: err = {}
                if str(err.get("type", "")).endswith(":badNonce") and tries < 3: continue
                raise AcmeError(f"Let's Encrypt {e.code}: {err.get('detail') or raw[:200]!r}") from None
        raise AcmeError("Let's Encrypt: mã dùng một lần (nonce) sai liên tục")

    def get(self, url):
        return json.loads(self.post(url, None)[1].decode() or "{}")

    def poll(self, url, ok, bad=("invalid",), timeout=120):
        t0 = time.time()
        while True:
            d = self.get(url)
            if d.get("status") in ok: return d
            if d.get("status") in bad: raise AcmeError("Let's Encrypt từ chối: " + _acme_why(d))
            if time.time() - t0 > timeout: raise AcmeError(f"Let's Encrypt: chờ quá {timeout} giây (trạng thái {d.get('status')})")
            time.sleep(3)


def _wait_txt(name, val):
    """Chờ bản ghi TXT hiện trên DNS công cộng (DoH), rồi chờ thêm cho mọi máy chủ tên của Cloudflare."""
    t0 = time.time()
    while time.time() - t0 < 90:
        try:
            u = f"{DOH_URL}?name={urllib.parse.quote(name)}&type=TXT"
            with urllib.request.urlopen(urllib.request.Request(u, headers={"Accept": "application/dns-json"}), timeout=10) as r:
                d = json.loads(r.read().decode() or "{}")
            if any(val in str(x.get("data", "")) for x in d.get("Answer") or []): break
        except Exception:
            pass
        time.sleep(4)
    time.sleep(ACME_TXT_WAIT)


def le_issue():
    """Xin chứng chỉ Let's Encrypt cho WEB_HOST (DNS-01: bản ghi TXT tạm qua mã Cloudflare) → le/<tên>-fullchain.pem + -key.pem."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    if not LE_AGREE: raise AcmeError("chưa đồng ý điều khoản Let's Encrypt — chạy 1 lần: python bluestream.py --webdirect")
    a = Acme(_ec_key(LE_ACC))
    h, _ = a.post(a.dir["newAccount"], {"termsOfServiceAgreed": True})
    a.kid = h["Location"]
    h, b = a.post(a.dir["newOrder"], {"identifiers": [{"type": "dns", "value": WEB_HOST}]})
    order_url, order = h["Location"], json.loads(b.decode())
    made = []                                        # bản ghi TXT tạm → xoá sau cùng
    try:
        todo = []
        for az_url in order.get("authorizations") or []:
            az = a.get(az_url)
            if az.get("status") == "valid": continue
            ch = next((c for c in az.get("challenges") or [] if c.get("type") == "dns-01"), None)
            if not ch: raise AcmeError("Let's Encrypt không cho kiểu xác minh DNS-01")
            name = "_acme-challenge." + az["identifier"]["value"]
            val = _b64u(hashlib.sha256(f"{ch['token']}.{a.thumbprint()}".encode()).digest())
            made.append(cf_api("POST", f"/zones/{cf_zone()}/dns_records", {"type": "TXT", "name": name, "content": val, "ttl": 60})["id"])
            todo.append((az_url, ch, name, val))
        for az_url, ch, name, val in todo:
            _wait_txt(name, val)
            a.post(ch["url"], {})
            a.poll(az_url, ok=("valid",), bad=("invalid", "deactivated", "expired", "revoked"))
        a.poll(order_url, ok=("ready", "valid"))
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)       # RSA: chuỗi R1x → ISRG Root X1, máy / trình duyệt cũ cũng tin
        csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, WEB_HOST)]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(WEB_HOST)]), critical=False).sign(k, hashes.SHA256()))
        a.post(order["finalize"], {"csr": _b64u(csr.public_bytes(serialization.Encoding.DER))})
        done = a.poll(order_url, ok=("valid",))
        pem = a.post(done["certificate"], None)[1]
        if b"BEGIN CERTIFICATE" not in pem: raise AcmeError("Let's Encrypt trả về chứng chỉ không đọc được")
        _write_private(LE_KEY, k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        _write_private(LE_CRT, pem)
    finally:
        for rid in made:
            try: cf_api("DELETE", f"/zones/{cf_zone()}/dns_records/{rid}")
            except Exception: pass


def le_cert_days():
    """(ngày còn lại, tổng số ngày) của chứng chỉ đường thẳng web; None = chưa có / hỏng / sai tên."""
    try:
        from cryptography import x509
        with open(LE_CRT, "rb") as f: c = x509.load_pem_x509_certificate(f.read())
        names = [n.lower() for n in c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)]
        if WEB_HOST not in names: return None
        utc = datetime.timezone.utc
        na = getattr(c, "not_valid_after_utc", None) or c.not_valid_after.replace(tzinfo=utc)
        nb = getattr(c, "not_valid_before_utc", None) or c.not_valid_before.replace(tzinfo=utc)
        return (na - datetime.datetime.now(utc)).total_seconds() / 86400, (na - nb).total_seconds() / 86400
    except Exception:
        return None


def le_need_renew():
    d = le_cert_days()
    return d is None or d[0] < max(2.0, min(30.0, d[1] / 3))


def web_ctx_load():
    """Nạp (lại) chứng chỉ thật cho SNI dN.<miền>; file đang ghi dở / hỏng / hết hạn → giữ bản đang dùng."""
    try: m = os.path.getmtime(LE_CRT)
    except OSError: return WEB["ctx"]
    if WEB["ctx"] is not None and m == WEB["mtime"]: return WEB["ctx"]
    d = le_cert_days()
    if not d or d[0] <= 0: return WEB["ctx"]
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(LE_CRT, LE_KEY)
    except (OSError, ssl.SSLError):
        return WEB["ctx"]
    WEB["ctx"], WEB["mtime"] = ctx, m
    return ctx


def sni_pick(sslobj, name, ctx):
    """Trình duyệt hỏi dN.<miền> → chứng chỉ Let's Encrypt; còn lại (app nối bằng IP, không SNI) → chứng chỉ tự ký app đã biết mã."""
    if name and WEB["ctx"] is not None and name.lower().rstrip(".") == WEB_HOST:
        sslobj.context = WEB["ctx"]


def web_url(pip_=None):
    """wss://dN.<miền>:PORT/v2/stream khi đường thẳng web dùng được — None thì web đi Cloudflare như cũ."""
    if not (WEB_DIRECT and CF_TOKEN) or WEB["ctx"] is None or not WEB["dns_ip"]: return None
    if pip_ and pip_ != WEB["dns_ip"]: return None                        # IP nhà mạng vừa đổi, tên chưa trỏ lại
    if time.time() - _direct_ok_t > WEB_PROOF: return None               # chưa chắc cổng modem đã mở
    return f"wss://{WEB_HOST}:{PORT}/v2/stream"


def web_direct_loop():
    """15 phút / lần: IP nhà mạng đổi → trỏ lại dN.<miền>; chứng chỉ sắp hết (còn < 1/3) → xin mới. Lỗi → lùi 30 phút … 12 giờ."""
    fails = 0
    while True:
        wait = 900
        try:
            ip = public_ip()
            if ip and (ip != WEB["dns_ip"] or time.time() - WEB["dns_t"] > 6 * 3600):
                if web_dns(ip): log(f"đường thẳng web: {WEB_HOST} → {ip} (mây xám)")
                WEB["dns_ip"], WEB["dns_t"] = ip, time.time()
            if le_need_renew():
                if not LE_AGREE: raise AcmeError("chưa đồng ý điều khoản Let's Encrypt — chạy 1 lần: python bluestream.py --webdirect")
                log(f"đường thẳng web: xin chứng chỉ Let's Encrypt cho {WEB_HOST}…")
                le_issue()
                d = le_cert_days()
                log(f"đường thẳng web: ✓ chứng chỉ {WEB_HOST} còn {int(d[0]) if d else '?'} ngày")
            web_ctx_load()
            fails, WEB["err"] = 0, ""
        except Exception as e:
            fails += 1; wait = min(12 * 3600, 1800 * 2 ** (fails - 1))
            if str(e) != WEB["err"]: log(f"đường thẳng web: ✗ {e} — thử lại sau {wait // 60} phút")
            WEB["err"] = str(e)
        time.sleep(wait)


def set_conf(key, val):
    """Ghi KEY=giá trị vào cloudphone.conf (giữ nguyên các dòng khác)."""
    f = os.path.join(B, "cloudphone.conf")
    try:
        with open(f, encoding="utf-8-sig") as fh: lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = []
    out, done = [], False
    for ln in lines:
        if not ln.lstrip().startswith("#") and ln.split("=", 1)[0].strip() == key:
            if not done: out.append(f"{key}={val}"); done = True
            continue
        out.append(ln)
    if not done: out.append(f"{key}={val}")
    with open(f + ".tmp", "w", encoding="utf-8") as fh: fh.write("\n".join(out) + "\n")
    os.replace(f + ".tmp", f)


def cmd_webdirect():
    """Bật / kiểm đường thẳng cho web + iPhone trên máy chủ này (PowerShell Admin, chạy tay): mã Cloudflare → điều khoản Let's
       Encrypt (người dùng tự gõ đồng ý) → trỏ dN.<miền> → xin chứng chỉ → nhắc mở cổng modem. Đã bật rồi thì chỉ kiểm."""
    global CF_TOKEN, LE_AGREE
    import getpass
    print(f"ĐƯỜNG THẲNG CHO WEB / iPhone — máy chủ {NODE_ID}: wss://{WEB_HOST}:{PORT}/v2/stream", flush=True)
    if not WEB_DIRECT: print("Đang tắt (WEB_DIRECT=0 trong cloudphone.conf) — xoá dòng đó để bật."); return 0
    if not CF_TOKEN or "--ma-moi" in sys.argv:
        print(f"Cần 1 mã Cloudflare (API Token) quyền Zone · DNS · Edit + Zone · Zone · Read cho {ZONE} — cách tạo: tài liệu, Bước 2.")
        print("Dán mã rồi bấm Enter. Mã KHÔNG hiện ra khi dán (bình thường). Enter trống = bỏ qua.", flush=True)
        try: tok = getpass.getpass("Mã Cloudflare: ").strip()
        except (EOFError, KeyboardInterrupt): tok = ""
        if not tok: print("→ Bỏ qua: web vẫn đi Cloudflare như cũ."); return 1
        CF_TOKEN = tok; _CF_Z.clear()
    try:
        cf_zone(); print(f"✓ Mã Cloudflare dùng được cho {ZONE}")
    except Exception as e:
        print(f"✗ Mã Cloudflare chưa dùng được: {e}")
        print("   Tạo lại mã theo Bước 2 rồi chạy lại:  python bluestream.py --webdirect --ma-moi"); return 2
    if (C.get("CF_DNS_TOKEN") or "").strip() != CF_TOKEN: set_conf("CF_DNS_TOKEN", CF_TOKEN)
    if not LE_AGREE:
        print("Chứng chỉ HTTPS miễn phí do Let's Encrypt cấp. Điều khoản: https://letsencrypt.org/repository/")
        try: ans = input("Gõ  dong y  rồi Enter nếu bạn đồng ý (Enter trống = bỏ qua): ").strip().lower()
        except (EOFError, KeyboardInterrupt): ans = ""
        if ans not in ("dong y", "đồng ý", "dongy", "dong ý", "đồng y"): print("→ Chưa đồng ý: chưa bật đường thẳng web."); return 3
        set_conf("LE_AGREE", "1"); LE_AGREE = True
    ip = public_ip()
    if not ip: print("✗ Không lấy được IP nhà mạng — máy có vào được Internet không?"); return 4
    try: print(f"✓ {WEB_HOST} → {ip} (mây xám)" + ("" if web_dns(ip) else " — đã đúng từ trước"))
    except Exception as e: print(f"✗ Trỏ tên {WEB_HOST} lỗi: {e}"); return 5
    if le_need_renew():
        print("Đang xin chứng chỉ Let's Encrypt (thường 30–90 giây)…", flush=True)
        try: le_issue()
        except Exception as e: print(f"✗ Xin chứng chỉ lỗi: {e}"); return 6
    d = le_cert_days()
    print(f"✓ Chứng chỉ {WEB_HOST} còn {int(d[0])} ngày (máy chủ tự gia hạn)" if d else "✗ Chứng chỉ chưa dùng được")
    lip = lan_ip() or "?"
    if time.time() - _direct_ok_t < WEB_PROOF: print(f"✓ Cổng modem TCP {PORT} đã mở (đã có máy ở ngoài mạng nối thẳng)")
    else: print(f"⚠ Chưa thấy máy ở ngoài mạng nối thẳng vào cổng {PORT}: mở cổng modem TCP {PORT} → {lip} (web tự đi thẳng khi cổng mở)")
    print(f"MODEM: TCP {PORT} -> {lip}")
    return 0 if d else 7


def firewall():
    if not WIN: return
    nm = "BlueRoblox Stream TCP"
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nm}"], capture_output=True, creationflags=NOWIN)
    subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={nm}", "dir=in", "action=allow", "protocol=TCP",
                    f"localport={PORT}"], capture_output=True, creationflags=NOWIN)


# ================================================================ UPnP-IGD: máy chủ TỰ MỞ CỔNG TCP PORT trên modem
# Trước đây admin mỗi máy chủ phải vào trang modem (FPT…) mở cổng bằng tay — máy nào chưa mở thì khách phải đi đường hầm
# Cloudflare (chậm). Giờ máy chủ tự xin modem: SSDP tìm modem → đọc mô tả thiết bị → AddPortMapping TCP PORT → IP LAN:PORT.
# Làm lúc chạy + mỗi 30 phút (gia hạn, modem khởi động lại, máy đổi IP LAN: cổng cũ mang tên "CloudBlue <NODE_ID>" tự xoá rồi mở lại).
# Nhật ký chỉ ghi khi kết quả đổi ("UPnP: ✓ …" / "UPnP: ✗ …"). Tắt: UPNP=0 trong cloudphone.conf.
# Thử tay (không chạy máy chủ):  python bluestream.py --upnp
UPNP = str(C.get("UPNP", "1")).strip().lower() not in ("0", "off", "false", "no")
UPNP_EVERY = 30 * 60                 # mở được → làm lại sau 30 phút
UPNP_RETRY = 120                     # chưa được → thử lại sau 2, 4, 8, 16 phút… (tối đa 30) — mới bật máy, modem đang khởi động lại
UPNP_BUDGET = 18.0                   # 1 lần thử tối đa ~18 giây (mỗi lần gọi modem ≤ 4 giây)
SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_ST = ("urn:schemas-upnp-org:device:InternetGatewayDevice:1", "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
           "urn:schemas-upnp-org:service:WANIPConnection:1", "urn:schemas-upnp-org:service:WANPPPConnection:1")
UPNP_NO_ANSWER = "modem không trả lời UPnP (UPnP đang tắt trên modem hoặc modem không hỗ trợ) — mở cổng bằng tay trong trang modem"
_UPNP_NAT = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
_UPNP_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # nói thẳng với modem: proxy hệ thống không xen vào


class UpnpFault(Exception):
    """Modem báo lỗi / không trả lời. code = mã lỗi UPnP (718 = cổng đã có người giữ, 725…) hoặc None (mạng, HTTP)."""
    def __init__(self, code, desc):
        super().__init__(f"lỗi {code} {desc}" if code else desc); self.code, self.desc = code, desc


def _upnp_why(e):
    r = getattr(e, "reason", None) if isinstance(e, urllib.error.URLError) else None
    if isinstance(e, (socket.timeout, TimeoutError)) or isinstance(r, (socket.timeout, TimeoutError)): return "hết giờ chờ modem"
    if isinstance(e, ConnectionRefusedError) or isinstance(r, ConnectionRefusedError): return "modem từ chối kết nối"
    return str(r or e) or e.__class__.__name__


def _ip4(s):
    """'1.2.3.4' → IPv4Address · rỗng / 0.0.0.0 / sai → None."""
    import ipaddress
    try: a = ipaddress.IPv4Address(str(s or "").strip())
    except ValueError: return None
    return None if a.is_unspecified else a


def _upnp_http(url, deadline, data=None, headers=None):
    """GET (data=None) / POST tới modem → (mã HTTP, nội dung ≤ 256 KB). Mỗi lần chờ ≤ 4 giây và không quá `deadline`.
       HTTP 500 (lỗi SOAP) vẫn trả nội dung để đọc errorCode."""
    left = deadline - time.monotonic()
    if left < 0.1: raise TimeoutError("hết giờ")
    h = {"User-Agent": "CloudBlue UPnP/1.1"}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="GET" if data is None else "POST")
    try:
        with _UPNP_HTTP.open(req, timeout=min(4.0, left)) as r: return r.status, r.read(262144)
    except urllib.error.HTTPError as e:
        try: return e.code, e.read(262144)
        except Exception: return e.code, b""
        finally: e.close()


def _xml_vals(b):
    """Mọi phần tử lá của 1 trả lời XML → {tên bỏ namespace: chữ}. XML hỏng (modem rẻ tiền) → dò bằng regex."""
    b = (b or b"").strip(b" \t\r\n\x00"); out = {}
    if b"<!DOCTYPE" not in b and b"<!ENTITY" not in b:
        try:
            for el in ET.fromstring(b).iter():
                if len(el) == 0 and isinstance(el.tag, str): out.setdefault(el.tag.rsplit("}", 1)[-1], (el.text or "").strip())
            return out
        except ET.ParseError: pass
    for k, v in re.findall(r"<(?:[\w.-]+:)?([\w.-]+)(?:\s[^<>]*)?>([^<]*)</", b.decode("utf-8", "replace")):
        out.setdefault(k, v.strip().replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
    return out


def ssdp_find(lan=None, target=SSDP_ADDR, wait=2.5):
    """Tìm modem UPnP: M-SEARCH (4 loại ST) tới `target` (mặc định nhóm multicast SSDP; thử nghiệm: modem giả unicast), gửi qua
       ĐÚNG card mạng LAN `lan` (máy giả lập có nhiều card ảo), gom các LOCATION (URL mô tả thiết bị) trong `wait` giây."""
    locs = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        if lan:
            try: s.bind((lan, 0))
            except OSError: pass                                  # IP vừa đổi… → để hệ điều hành tự chọn card
            try: s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(lan))
            except OSError: pass
        try: s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        except OSError: pass
        for st in SSDP_ST:
            try: s.sendto(f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: {st}\r\n\r\n'.encode(), target)
            except OSError: pass
        end = time.monotonic() + wait
        while len(locs) < 16:
            left = end - time.monotonic()
            if left <= 0: break
            s.settimeout(left)
            try: data, _ = s.recvfrom(8192)
            except socket.timeout: break
            except ConnectionResetError: continue                 # Windows: ICMP "cổng đóng" của lần gửi trước — bỏ qua
            except OSError: break
            m = re.search(rb"(?im)^location[ \t]*:[ \t]*(\S+)", data)
            loc = m.group(1).decode("latin-1") if m else ""
            if loc.lower().startswith("http://") and loc not in locs: locs.append(loc)
    finally:
        s.close()
    return locs


def igd_services(xml, location):
    """Mô tả thiết bị UPnP → [(serviceType, controlURL tuyệt đối)] các dịch vụ WANIPConnection / WANPPPConnection theo thứ tự trong file
       (không phụ thuộc namespace, thiết bị lồng nhau bao nhiêu tầng cũng được; controlURL tương đối → ghép với URLBase hoặc `location`)."""
    xml = (xml or b"").strip(b" \t\r\n\x00"); base, found = "", []
    try:
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml: raise ET.ParseError("DTD")
        root = ET.fromstring(xml)
        ln = lambda e: e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""
        for e in root:
            if ln(e) == "URLBase": base = (e.text or "").strip()
        for e in root.iter():
            if ln(e) == "service":
                f = {ln(c): (c.text or "").strip() for c in e}
                found.append((f.get("serviceType", ""), f.get("controlURL", "")))
    except ET.ParseError:                                         # XML hỏng (VD dấu "&" trần trong tên modem) → dò bằng regex
        t = xml.decode("utf-8", "replace")
        tag = lambda n: r"<(?:[\w.-]+:)?" + n + r"\b[^>]*>\s*([^<]*?)\s*</"
        m = re.search(tag("URLBase"), t); base = m.group(1) if m else ""
        for blk in re.findall(r"<(?:[\w.-]+:)?service\b[^>]*>(.*?)</(?:[\w.-]+:)?service\s*>", t, re.S):
            a, c = re.search(tag("serviceType"), blk), re.search(tag("controlURL"), blk)
            found.append((a.group(1) if a else "", c.group(1) if c else ""))
    return [(st, urllib.parse.urljoin(base or location, ctl)) for st, ctl in found
            if ctl and ("WANIPConnection" in st or "WANPPPConnection" in st)]


def upnp_soap(ctl, st, action, args=(), deadline=None):
    """Gọi lệnh SOAP `action` của dịch vụ `st` tại `ctl` → {tên: giá trị} modem trả về. Lỗi (HTTP 500 + errorCode / mạng) → UpnpFault."""
    deadline = deadline or time.monotonic() + 4
    x = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    body = ('<?xml version="1.0"?>\r\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{x(st)}">' + "".join(f"<{k}>{x(v)}</{k}>" for k, v in args)
            + f"</u:{action}></s:Body></s:Envelope>\r\n").encode("utf-8")
    try: code, resp = _upnp_http(ctl, deadline, body, {"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{st}#{action}"'})
    except Exception as e: raise UpnpFault(None, _upnp_why(e))
    v = _xml_vals(resp)
    if code == 200 and "errorCode" not in v: return v
    ec = v.get("errorCode", "")
    raise UpnpFault(int(ec) if ec.isdigit() else None, v.get("errorDescription") or f"HTTP {code}")


def _upnp_nat_warn(ext, pub):
    """IP ngoài của modem là IP nội bộ / CGNAT, hoặc khác IP ra Internet → phía trên còn 1 lớp NAT: mở cổng trên modem không đủ."""
    import ipaddress
    a = _ip4(ext)
    if not a: return ""
    if a in ipaddress.IPv4Network("100.64.0.0/10"):
        return (f"⚠ IP modem {a} là IP dùng chung của nhà mạng (CGNAT) — nhà mạng NAT thêm 1 lớp nên mở cổng trên modem KHÔNG giúp "
                "khách nối thẳng được: cần xin nhà mạng IP công khai (IP public / IP tĩnh)")
    if any(a in ipaddress.IPv4Network(n) for n in _UPNP_NAT):
        return (f"⚠ IP modem {a} là IP nội bộ — phía trên còn 1 lớp NAT nữa (nhà mạng, hoặc modem/router khác) nên mở cổng ở đây KHÔNG "
                "giúp khách nối thẳng được: cần IP công khai từ nhà mạng (hoặc chuyển thiết bị phía trên sang bridge)")
    p = _ip4(pub)
    if p and p != a:
        return (f"⚠ IP modem {a} khác IP ra Internet {p} — mạng còn đi qua 1 lớp NAT nữa của nhà mạng nên mở cổng KHÔNG giúp khách "
                "nối thẳng được: cần xin nhà mạng IP công khai")
    return ""


def upnp_open(port=None, lan=None, ssdp=None, wait=2.5, pub=None):
    """Mở cổng TCP `port` (mặc định PORT) trên modem → `lan` (mặc định lan_ip()):port bằng UPnP-IGD → (ok, thông báo tiếng Việt).
       ssdp: nơi gửi M-SEARCH (mặc định 239.255.255.250:1900; thử nghiệm: modem giả) · pub: IP công khai để so với IP modem
       (None = tự hỏi public_ip() song song, "" = không so). KHÔNG BAO GIỜ ném lỗi; cả lần thử ≤ ~18 giây."""
    try:
        return _upnp_open(int(port or PORT), lan or lan_ip(), ssdp or SSDP_ADDR, wait, pub)
    except Exception as e:
        return False, f"lỗi UPnP: {e!r}"


def _upnp_open(port, lan, target, wait, pub):
    if not lan: return False, "không biết IP mạng LAN của máy này (chưa nối mạng?) — chưa mở được cổng bằng UPnP"
    deadline = time.monotonic() + UPNP_BUDGET
    got, th = {"pub": pub}, None
    if pub is None:                                               # hỏi IP công khai song song lúc chờ modem trả lời
        def ask():
            try: got["pub"] = public_ip()
            except Exception: pass
        th = threading.Thread(target=ask, daemon=True); th.start()
    locs = ssdp_find(lan, target, wait)
    if not locs: return False, UPNP_NO_ANSWER
    svcs, errs = [], []
    for loc in locs[:6]:
        if svcs and time.monotonic() > deadline - 8: break         # để dành thời gian cho lệnh mở cổng
        try:
            code, xml = _upnp_http(loc, deadline)
            if code != 200: raise ValueError(f"HTTP {code}")
            svcs += [sv for sv in igd_services(xml, loc) if sv not in svcs]
        except Exception as e:
            errs.append(f"{urllib.parse.urlsplit(loc).netloc}: {_upnp_why(e)}")
    if not svcs:
        why = errs[0] if errs else "không có dịch vụ mở cổng WANIPConnection / WANPPPConnection"
        return False, f"modem trả lời UPnP nhưng không dùng được ({why}) — mở cổng bằng tay trong trang modem"
    # modem nhà mạng hay có nhiều đường WAN (Internet, quản lý TR-069, IPTV…) → chọn đường có IP Internet thật
    best, rank, ext = svcs[0], -1, ""
    for i, sv in enumerate(svcs[:4]):
        if i and time.monotonic() > deadline - 8: break
        try: ip = upnp_soap(sv[1], sv[0], "GetExternalIPAddress", (), deadline).get("NewExternalIPAddress", "")
        except UpnpFault: ip = ""
        a = _ip4(ip); r = 0 if not a else 2 if a.is_global else 1
        if r > rank: best, rank, ext = sv, r, (str(a) if a else "")
        if r == 2: break
    st, ctl = best
    me = f"CloudBlue {NODE_ID}"
    key = (("NewRemoteHost", ""), ("NewExternalPort", port), ("NewProtocol", "TCP"))

    def add():
        """Hạn 0 (vĩnh viễn); modem không nhận (lỗi khác 718) → thử lại 1 lần hạn 7200 giây (vẫn được gia hạn mỗi 30 phút)."""
        f = None
        for lease in (0, 7200):
            try:
                upnp_soap(ctl, st, "AddPortMapping", key + (("NewInternalPort", port), ("NewInternalClient", lan), ("NewEnabled", 1),
                                                           ("NewPortMappingDescription", me), ("NewLeaseDuration", lease)), deadline)
                return None
            except UpnpFault as e:
                f = e
                if e.code == 718: break
        return f

    f = add()
    if f:                                                         # cổng đã có người giữ? → hỏi modem cổng đang chuyển tới đâu
        try: cur = upnp_soap(ctl, st, "GetSpecificPortMappingEntry", key, deadline)
        except UpnpFault: cur = {}
        who, desc = cur.get("NewInternalClient", "").strip(), cur.get("NewPortMappingDescription", "").strip()
        iport, lease = cur.get("NewInternalPort", "").strip(), cur.get("NewLeaseDuration", "").strip()
        on = cur.get("NewEnabled", "1").strip().lower() not in ("0", "false")
        here = bool(who) and (who == lan or _ip4(who) is not None and _ip4(who) == _ip4(lan))
        if here and on and iport in ("", str(port)) and not (desc == me and lease.isdigit() and 0 < int(lease) < UPNP_EVERY + 300):
            f = None                                              # đã chuyển đúng về máy này (mở tay / lần trước) → xong
        elif who and desc == me:                                  # cổng của chính máy chủ này nhưng IP LAN cũ / sắp hết hạn → xoá, mở lại
            try: upnp_soap(ctl, st, "DeletePortMapping", key, deadline)
            except UpnpFault: pass
            f = add()
        elif here:
            return False, (f"cổng TCP {port} trên modem chuyển về máy này nhưng sai ({who}:{iport or '?'}{'' if on else ', đang tắt'}) "
                           f"— sửa trong trang modem: TCP {port} → {lan}:{port}")
        elif who:
            return False, f"cổng TCP {port} trên modem đang chuyển tới máy khác ({who}{' · ' + desc[:40] if desc else ''}) — sửa trong trang modem"
        elif f.code == 718:
            return False, (f"cổng TCP {port} trên modem đã bị chiếm (modem không cho biết chuyển tới máy nào — có thể đã mở tay) "
                           f"— kiểm tra trang modem: TCP {port} phải chuyển tới {lan}:{port}")
    if f: return False, f"không mở được cổng TCP {port} qua UPnP ({f}) — mở cổng bằng tay trong trang modem"
    a = _ip4(ext)
    if th and a and a.is_global: th.join(max(0.0, min(6.0, deadline - time.monotonic())))
    w = _upnp_nat_warn(ext, got.get("pub"))
    return True, f"đã mở cổng TCP {port} → {lan}:{port}" + (f" · IP modem {ext}" if ext else "") + (f" · {w}" if w else "")


def upnp_loop():
    """Luồng nền (main): mở cổng lúc chạy + mỗi 30 phút; chưa được thì thử lại sớm hơn. Nhật ký chỉ ghi khi kết quả đổi. Không bao giờ ném lỗi."""
    last, fails = None, 0
    while True:
        try: ok, msg = upnp_open()
        except Exception as e: ok, msg = False, f"lỗi UPnP: {e!r}"
        if (ok, msg) != last:
            log(("UPnP: ✓ " if ok else "UPnP: ✗ ") + str(msg)); last = (ok, msg)
        fails = 0 if ok else fails + 1
        time.sleep(UPNP_EVERY if ok else min(UPNP_EVERY, UPNP_RETRY * 2 ** min(fails - 1, 10)))


def upnp_cli():
    """python bluestream.py --upnp → thử mở cổng PORT trên modem 1 lần (KHÔNG chạy máy chủ), in kết quả. Trả 0 = mở được."""
    print(f"== UPnP: mở cổng TCP {PORT} trên modem về máy chủ {NODE_ID}" + ("" if UPNP else "   (UPNP=0: máy chủ sẽ KHÔNG tự mở cổng)"))
    lip = lan_ip(); print("  IP LAN máy này:", lip or "? (chưa nối mạng)")
    pip_ = public_ip(); print("  IP công khai:  ", pip_ or "? (không hỏi được)")
    ok, msg = upnp_open(lan=lip, pub=pip_ or "")
    print(("  ✓ " if ok else "  ✗ ") + msg)
    if not ok and lip: print(f"  → mở tay: trang modem (thường http://192.168.1.1) → NAT / Port Forwarding: TCP {PORT} → {lip}:{PORT}")
    return 0 if ok else 1


# ================================================================ KIỂM ĐƯỜNG NỐI THẲNG:  python bluestream.py --netcheck [--fix]
# In: IP LAN · IP công khai · IP WAN của modem (phát hiện CGNAT / 2 lớp NAT) · cổng modem đang chuyển · phiên gần đây đi thẳng hay
# vòng Cloudflare. --fix: cổng hiện tại KHÔNG mở được bằng UPnP (VD 8193 "đã bị chiếm" bởi luật mở tay trỏ sai máy) → tìm cổng trống
# khác, mở bằng UPnP, ghi STREAM_PORT mới vào cloudphone.conf (bản cũ .bak) và in dòng NEWPORT=… (ketnoi.py khởi động lại phát hình).
NET_PORTS = (8195, 8196, 8197, 8198, 8199, 8291, 8293, 8295, 8297, 8299, 18195, 18197, 18199)


def _port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", int(port))); return True
    except OSError:
        return False
    finally:
        s.close()


def igd_info(lan, target=None, wait=2.5):
    """Modem UPnP → (serviceType, controlURL, IP WAN của modem) · không dùng được → (None, None, lý do)."""
    deadline = time.monotonic() + UPNP_BUDGET
    locs = ssdp_find(lan, target or SSDP_ADDR, wait)
    if not locs: return None, None, UPNP_NO_ANSWER
    svcs = []
    for loc in locs[:6]:
        try:
            code, xml = _upnp_http(loc, deadline)
            if code == 200: svcs += [sv for sv in igd_services(xml, loc) if sv not in svcs]
        except Exception:
            pass
    if not svcs: return None, None, "modem trả lời UPnP nhưng không có dịch vụ mở cổng"
    best, rank, ext = svcs[0], -1, ""
    for sv in svcs[:4]:
        try: ip = upnp_soap(sv[1], sv[0], "GetExternalIPAddress", (), deadline).get("NewExternalIPAddress", "")
        except UpnpFault: ip = ""
        a = _ip4(ip); r = 0 if not a else 2 if a.is_global else 1
        if r > rank: best, rank, ext = sv, r, (str(a) if a else "")
        if r == 2: break
    return best[0], best[1], ext


def igd_mappings(st, ctl, limit=64):
    """Các cổng modem CHO XEM (cổng mở tay trong trang modem thường bị giấu) → [dict]."""
    out, deadline = [], time.monotonic() + 15
    for i in range(limit):
        try: out.append(upnp_soap(ctl, st, "GetGenericPortMappingEntry", (("NewPortMappingIndex", i),), deadline))
        except UpnpFault: break
    return out


def set_conf(key, val, path=None):
    """Sửa / thêm 1 dòng KHOÁ=GIÁ_TRỊ trong cloudphone.conf tại chỗ (giữ BOM, CRLF, các dòng khác; bỏ dòng trùng; bản cũ .bak)."""
    f = path or os.path.join(B, "cloudphone.conf")
    data = open(f, "rb").read() if os.path.isfile(f) else b""
    bom = data[:3] == b"\xef\xbb\xbf"; raw = data[3 if bom else 0:].decode("utf-8", errors="replace")
    nl = "\r\n" if "\r\n" in raw else "\n"; lines, done = [], False
    for ln in raw.splitlines():
        if "=" in ln and not ln.lstrip().startswith("#") and ln.split("=", 1)[0].strip() == key:
            if done: continue
            ln = f"{key}={val}"; done = True
        lines.append(ln)
    if not done: lines.append(f"{key}={val}")
    if data: open(f + ".bak", "wb").write(data)
    open(f + ".tmp", "wb").write((b"\xef\xbb\xbf" if bom else b"") + (nl.join(lines) + nl).encode("utf-8"))
    os.replace(f + ".tmp", f)


def log_tail(n=6000):
    p = os.path.join(B, "logs", "phat-hinh.log")
    try:
        with open(p, "rb") as fh:
            fh.seek(0, 2); size = fh.tell(); fh.seek(max(0, size - 900_000))
            return fh.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []


def session_mix(lines):
    """Đếm phiên trong nhật ký: {(đường, loại app): số} — đường = direct (thẳng) / ws (vòng Cloudflare)."""
    mix = collections.Counter()
    for ln in lines:
        m = re.search(r"▶ \S+ ← \S+ \((direct|ws), ([^)]*)\)", ln)
        if m: mix[(m.group(1), m.group(2).strip() or "?")] += 1
    return mix


def netcheck(fix=False, lan=None, pub=None, target=None):
    """In chẩn đoán đường nối thẳng. Trả: 0 = cổng mở được · 1 = chưa · 3 = (--fix) đã đổi sang cổng mới (in NEWPORT=…)."""
    print(f"== Đường nối THẲNG · máy chủ {NODE_ID} · cổng phát hình TCP {PORT}")
    lip = lan or lan_ip(); pip_ = public_ip() if pub is None else pub
    print(f"  IP LAN máy này:   {lip or '? (chưa nối mạng?)'}")
    print(f"  IP công khai:     {pip_ or '? (không hỏi được)'}")
    st = ctl = None; ext = ""; cg = ""
    if lip:
        st, ctl, ext = igd_info(lip, target)
        if st:
            print(f"  IP WAN của modem: {ext or '?'}")
            cg = _upnp_nat_warn(ext, pip_ or "")
            if cg: print("  " + cg)
            maps = igd_mappings(st, ctl)
            if maps:
                print(f"  Modem cho xem {len(maps)} cổng đang mở:")
                for m in maps[:20]:
                    print(f"    · {m.get('NewProtocol', '?')} {m.get('NewExternalPort', '?')} → {m.get('NewInternalClient', '?')}:{m.get('NewInternalPort', '?')}"
                          f"  ({(m.get('NewPortMappingDescription') or '')[:32]})")
            else:
                print("  Modem không cho xem danh sách cổng (cổng mở tay trong trang modem thường bị giấu)")
        else:
            print(f"  ✗ UPnP: {ext}"); ext = ""
    ok, msg = upnp_open(lan=lip, pub=pip_ or "", ssdp=target) if lip else (False, "không biết IP LAN")
    print(("  ✓ " if ok else "  ✗ ") + f"cổng TCP {PORT}: {msg}")
    lines = log_tail(); mix = session_mix(lines)
    if mix:
        print("  Phiên trong nhật ký gần đây: " + " · ".join(f"{'thẳng' if k[0] == 'direct' else 'vòng Cloudflare'} ({k[1]}) {v}" for k, v in sorted(mix.items())))
        apps = sum(v for k, v in mix.items() if k[1] in ("android", "pc"))
        if apps and not sum(v for k, v in mix.items() if k[0] == "direct"):
            print("  ⚠ App điện thoại / PC CHƯA phiên nào đi thẳng → đường thẳng hỏng (cổng modem / nhà mạng) → mọi khách đi vòng Cloudflare (chậm, giật)")
    if ok and not cg: return 0
    if cg:
        print("  → Nhà mạng NAT thêm 1 lớp: đổi cổng hay mở cổng đều KHÔNG giúp. Gọi tổng đài nhà mạng (FPT 1900 6600) xin \"IP công khai / tắt CGNAT\".")
        return 1
    if not st:
        print(f"  → Modem không dùng được UPnP: vào trang modem (thường http://192.168.1.1) → NAT / Port Forwarding: TCP {PORT} → {lip}:{PORT}")
        return 1
    if not fix:
        print(f"  → Chạy lại với --fix để tự chuyển sang cổng trống khác (mở bằng UPnP), hoặc vào trang modem sửa: TCP {PORT} → {lip}:{PORT}")
        return 1
    for cand in NET_PORTS:
        if cand in (PORT, WS_PORT) or not _port_free(cand): continue
        ok2, msg2 = upnp_open(port=cand, lan=lip, pub=pip_ or "", ssdp=target)
        print(("  ✓ " if ok2 else "  · ") + f"thử cổng {cand}: {msg2}")
        if ok2:
            set_conf("STREAM_PORT", str(cand))
            print(f"  ✓ ĐÃ ĐỔI cổng phát hình {PORT} → {cand} (cloudphone.conf, bản cũ cloudphone.conf.bak) — khởi động lại phát hình để dùng.")
            print(f"NEWPORT={cand}")
            return 3
    print(f"  ✗ Không mở được cổng nào bằng UPnP → vào trang modem: NAT / Port Forwarding: TCP {PORT} → {lip}:{PORT}")
    return 1


def _save_png(frame, name):
    if frame is None: return "(không có khung nào)"
    p = os.path.join(B, "logs", "captest_" + re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".png")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        from PIL import Image
        Image.fromarray(frame[:, :, 2::-1].copy()).save(p)          # BGRA → RGB
        return p
    except Exception as e:
        return f"(không lưu được ảnh: {e!r})"


def captest(name, port=None):
    """THỬ LẤY HÌNH 1 máy ngay trên máy chủ — không cần app, không cần đăng nhập, không đụng phiên khách đang xem:
         python bluestream.py --captest cp_xxx [cổng adb]
       Quay cửa sổ giả lập 3 giây → in cỡ + khung/giây + lưu ảnh logs\\captest_<tên>.png. Windows không cho quay / không ra khung
       → thử lấy hình thẳng từ Android (scrcpy) 3 giây. Trả 0 = lấy được hình."""
    print(f"== Thử lấy hình máy {name}")
    ok = False
    if WIN:
        hs = [y for xs in _same_name(name) for y in xs]
        print("  cửa sổ:" if hs else "  ✗ không thấy cửa sổ nào mang tên này (máy đang tắt? sai tên?)")
        for x in hs[:6]: print("   ·", win_info(x))
    if WIN and wgc_ok() and (C.get("CAPTURE") or "").strip().lower() not in ("scrcpy", "gdi"):
        src = WindowSource(name)
        try:
            w, h = src.open(); n0, t0 = src.n, time.time()
            time.sleep(3)
            fps = (src.n - n0) / max(0.1, time.time() - t0); fr = src.latest
            dark = fr is not None and int(fr[::16, ::16, :3].max()) < 8
            print(f"  ✓ quay cửa sổ được: phần Android {w}x{h}, {fps:.0f} khung/giây")
            print(f"    ảnh: {_save_png(fr, name)} — " + ("TOÀN ĐEN (giả lập không vẽ hình?)" if dark else "có hình"))
            hw, _ = find_window(name)
            if hw: print("    cửa sổ giờ ở:", win_info(hw))
            ok = not dark
        except CaptureBlocked as e: print("  ✗ quay cửa sổ:", e)
        except Deny as d: print("  ✗ quay cửa sổ:", d.msg)
        except Exception as e: print("  ✗ quay cửa sổ lỗi:", repr(e))
        finally: src.stop()
    if ok: return 0
    port = port or (phones_json().get(name) or {}).get("port")
    if not port:
        print("  ✗ không biết cổng adb của máy này → thêm cổng: --captest TÊN CỔNG"); return 1
    serial = f"127.0.0.1:{port}"; got = []; sv = None
    print(f"== Thử lấy hình thẳng từ Android (scrcpy) {serial}")
    try:
        print("  màn hình Android: %dx%d" % ScrcpySource(serial).open())
        sv = ScrcpyVideo(serial, 1280, 30, 3000, lambda d, k, c, p: got.append(len(d)))
        w, h = sv.start(); time.sleep(3)
        print(f"  {'✓' if got else '✗'} scrcpy: {w}x{h}, {len(got)} khung trong 3 giây")
        ok = bool(got)
    except Exception as e:
        print("  ✗ scrcpy lỗi:", repr(e))
    finally:
        if sv: sv.stop()
    return 0 if ok else 1


def _png_size(path):
    try:
        b = open(path, "rb").read(24)
        return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else None
    except OSError: return None


def _shot(serial, path):
    """Chụp màn hình THẬT của Android (không qua bộ nén) → file PNG. True = được."""
    try:
        p = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"], capture_output=True, timeout=20, creationflags=NOWIN)
        if p.returncode == 0 and p.stdout[:8] == b"\x89PNG\r\n\x1a\n": open(path, "wb").write(p.stdout); return True
    except Exception: pass
    return False


def _ffrun(args, timeout=60):
    try:
        p = subprocess.run([FF, "-hide_banner"] + args, capture_output=True, timeout=timeout, creationflags=NOWIN)
        return p.returncode, (p.stderr or b"").decode("utf-8", "replace")
    except Exception as e: return -1, str(e)


def _ssim(a, b):
    """Độ giống 2 ảnh (SSIM 0–1) bằng FFmpeg; ảnh b được co về cỡ ảnh a. Không đo được → None."""
    z = _png_size(a)
    if not z or not os.path.isfile(b): return None
    code, err = _ffrun(["-i", a, "-i", b, "-lavfi", f"[1:v]scale={z[0]}:{z[1]}:flags=area,format=yuv420p[r];[0:v]format=yuv420p[m];[m][r]ssim",
                        "-f", "null", "-"], 60)
    m = re.search(r"All:([0-9.]+)", err)
    return float(m.group(1)) if m else None


def _sps_info(au):
    """(profile, level) đọc từ SPS trong gói Annex-B."""
    for n in re.split(b"\x00\x00\x01", au or b""):
        if n and (n[0] & 0x1F) == 7 and len(n) >= 4: return n[1], n[3]
    return None


def _kh_ready(serial, wait=2.0):
    """Máy dùng được để chẩn đoán: adb nối, Android đã lên xong, đọc được cỡ màn hình. → (True, "") / (False, lý do)."""
    adb_connect(serial)
    if not adb_ready(serial, wait): return False, "adb không thấy máy (máy tắt / đang khởi động lại)"
    _, o, _ = adb(serial, "shell", "getprop sys.boot_completed", timeout=10)
    if (o or "").strip() != "1": return False, "Android chưa lên xong (đang khởi động / đang sập)"
    _devsize.pop(serial, None)
    if not device_size(serial): return False, "Android chưa trả lời (giao diện đang sập / khởi động lại)"
    return True, ""


def kiemhinh(name=None, port=None):
    """16/11k: CHẨN ĐOÁN HÌNH VỠ / NHIỄU MÀU (máy MuMu, đường scrcpy) ngay trên máy chủ — không cần app, không đụng phiên khách:
         python bluestream.py --kiemhinh TÊN_MÁY [CỔNG_ADB]
       Để máy ở MÀN HÌNH CHÍNH (đứng yên) rồi chạy. Ghi hình thẳng từ Android 4 lần, mỗi lần ~4 giây:
         A cỡ 1280 như thường · B cỡ 640 kiểu cũ (rộng 360, không chia hết 16) · C cỡ 1280 + 1 ô xem trước chạy cùng lúc · D xin 60 khung.
       Mỗi lần: khung/giây thật, số lát mỗi khung, cỡ, profile/level, số lỗi giải mã (FFmpeg), độ giống ảnh chụp màn hình thật (SSIM).
       In KẾT LUẬN; ảnh lưu ở logs\\kiemhinh_<tên>_*.png để tự xem."""
    if not name:                                             # không ghi tên → chọn máy khách đang chạy, ưu tiên FPS cao (máy đã đổi FPS)
        cand = sorted(((n, p) for n, p in phones_json().items() if str(n).startswith("cp_") and p.get("port")),
                      key=lambda x: -int(x[1].get("fps") or 30))
        for n, p in cand:
            if _kh_ready(f"127.0.0.1:{p['port']}")[0]: name, port = n, p["port"]; break
        if not name: print("  ✗ không có máy khách nào đang chạy ỔN để thử (máy tắt / chưa lên / đang sập) — chạy lại sau, hoặc ghi tên máy: --kiemhinh TÊN_MÁY"); return 1
    print(f"== Chẩn đoán hình máy {name} (bản {BS_SUB}) — để máy đứng yên ở màn hình chính trong lúc chạy (~40 giây)")
    port = port or (phones_json().get(name) or {}).get("port")
    if not port: print("  ✗ không biết cổng adb của máy này → thêm cổng: --kiemhinh TÊN CỔNG"); return 1
    serial = f"127.0.0.1:{port}"
    okr, why = _kh_ready(serial, 15)
    if not okr:
        print(f"  ✗ {why} → KHÔNG chẩn đoán được hình máy này. Máy đang sập thì chạy lệnh sửa máy trước (lệnh A / phonectl ksfix), rồi thử lại.")
        return 1
    if not ensure_jar(): print("  ✗ thiếu scrcpy-server"); return 1
    push_jar(serial)
    ld = os.path.join(B, "logs"); os.makedirs(ld, exist_ok=True)
    base = os.path.join(ld, "kiemhinh_" + re.sub(r"[^A-Za-z0-9_.-]", "_", name))
    nat = device_size(serial) or (0, 0)
    _, disp, _ = adb(serial, "shell", "dumpsys display | grep -m6 -o -E 'fps=[0-9.]+|renderFrameRate [0-9.]+'", timeout=15)
    _, ver, _ = adb(serial, "shell", "getprop ro.build.version.release", timeout=10)
    fr = sorted(set(float(x) for x in re.findall(r"(?:fps=|renderFrameRate )([0-9]+(?:\.[0-9]+)?)", disp or "")))
    print(f"  Android {ver.strip() or '?'} · màn {nat[0]}x{nat[1]} · khung/giây màn hình: {' / '.join(f'{x:g}' for x in fr) or '?'}")
    code, enc_out, _ = adb(serial, "shell", f"CLASSPATH={JAR_DEV} app_process / com.genymobile.scrcpy.Server 2.4 list_encoders=true log_level=info", timeout=25)
    encs = re.findall(r"--video-codec=h264\s+--video-encoder='?([\w.\-]+)'?", enc_out or "")
    print(f"  bộ nén H.264 trong máy: {', '.join(encs) or '?'}" + (f"  (mặc định: {encs[0]})" if encs else ""))
    try: ensure_ffmpeg()                                       # máy chủ phát hình đã tải sẵn lúc bật — thiếu thì tải 1 lần
    except Exception: pass
    ff_ok = os.path.isfile(FF) or FF == "ffmpeg"
    if not ff_ok: print("  (máy chủ chưa có FFmpeg → chỉ đếm khung, không đo lỗi giải mã / độ giống)")
    res = {}

    def one(tag, msz, fps, kbps, with_preview=False):
        got = []; lock = threading.Lock(); sv = pv = None; out = {"tag": tag}
        def on_au(d, k, c, p):
            if d is not None:
                with lock: got.append(bytes(d))
        shot0 = base + f"_{tag}_truoc.png"; s0 = _shot(serial, shot0)
        try:
            sv = ScrcpyVideo(serial, msz, fps, kbps, on_au, iframe=1.0)
            w, h = sv.start(); out["size"] = (w, h)
            if with_preview:
                try: pv = ScrcpyVideo(serial, 480, 8, 400, lambda *a: None, iframe=1.0); pv.start()
                except Exception as e: out["pv_err"] = repr(e)[:80]
            t0 = time.time(); time.sleep(4.0); dt = max(0.5, time.time() - t0)
            out.update(frames=sv.frames_in, pk=sv.pk_in, cont=sv.cont_in, cut=getattr(sv, "cut_in", 0), fps=sv.frames_in / dt)
        except Exception as e:
            out["err"] = repr(e)[:160]
        finally:
            if pv: pv.stop()
            if sv: sv.stop()
        with lock: aus = list(got)
        if not aus: return out
        si = next((_sps_info(a) for a in aus if _sps_info(a)), None)
        if si: out["prof"] = si
        f264 = base + f"_{tag}.h264"; open(f264, "wb").write(b"".join(aus))
        shot = base + f"_{tag}_man.png"; out["shot"] = _shot(serial, shot)
        if ff_ok:
            code, err = _ffrun(["-v", "error", "-i", f264, "-f", "null", "-"], 90)
            out["dec_err"] = len([x for x in err.splitlines() if x.strip()])
            last = base + f"_{tag}_hinh.png"
            _ffrun(["-v", "error", "-i", f264, "-update", "1", "-y", last], 90)
            st_ = _ssim(shot, shot0) if s0 and out["shot"] else None
            out["static"] = st_ is not None and st_ >= 0.9
            if out["static"] and os.path.isfile(last): out["ssim"] = _ssim(last, shot)
        return out

    tests = [("A", 1280, 30, 3000, False), ("B", 640, 30, 1500, False), ("C", 1280, 30, 3000, True), ("D", 1280, 60, 3000, False)]
    for tag, msz, fps, kbps, pv in tests:
        r = one(tag, msz, fps, kbps, pv); res[tag] = r; time.sleep(1.0)
        nm = {"A": "1280 như thường", "B": "640 kiểu cũ (cỡ lẻ)", "C": "1280 + ô xem trước cùng lúc", "D": "1280 xin 60 khung"}[tag]
        if "err" in r and "frames" not in r: print(f"  {tag} {nm}: ✗ lỗi {r['err']}"); continue
        sz = r.get("size") or (0, 0); pr = r.get("prof")
        print(f"  {tag} {nm}: {sz[0]}x{sz[1]}" + ("" if sz[0] % 16 == 0 and sz[1] % 16 == 0 else " (KHÔNG chia hết 16)")
              + f" · {r.get('fps', 0):.0f} khung/giây (xin {fps}) · {r.get('pk', 0)} gói / {r.get('frames', 0)} khung"
              + (f" · {r['cont']} lát tách rời" if r.get("cont") else "") + (f" · {r['cut']} khung thiếu lát đã bỏ" if r.get("cut") else "")
              + (f" · {({66: 'Baseline', 77: 'Main', 100: 'High'}).get(pr[0], 'profile ' + str(pr[0]))} {pr[1] / 10:g}" if pr else "")
              + (f" · lỗi giải mã {r['dec_err']}" if "dec_err" in r else "")
              + (f" · giống màn thật {r['ssim']:.2f}" if r.get("ssim") is not None else " · màn đang thay đổi (không so độ giống)" if "static" in r else "")
              + (f" · ô xem trước lỗi {r['pv_err']}" if r.get("pv_err") else ""))

    def dirty(r):
        if not r or "frames" not in r: return None
        if r.get("dec_err", 0) > 0: return True
        if r.get("ssim") is not None: return r["ssim"] < 0.6
        return None
    vA, vB, vC, vD = (dirty(res.get(t)) for t in "ABCD")
    print("== KẾT LUẬN")
    said = False
    got = [t for t in "ABCD" if (res.get(t) or {}).get("frames")]
    if not got:
        print("  ✗ KHÔNG lấy được khung hình nào ở cả 4 lần thử → máy vừa sập / mất adb giữa chừng → không kết luận được. "
              "Sửa máy trước (lệnh A / phonectl ksfix) rồi chạy lại lệnh này.")
        return 1
    miss = [t for t in "ABCD" if t not in got]
    if miss: print(f"  ⚠ lần thử {', '.join(miss)} không lấy được hình (máy chập chờn) — kết luận chỉ dựa trên {', '.join(got)}")
    if any((res.get(t) or {}).get("cont") for t in "ABCD"):
        print("  • Bộ nén trong máy chia 1 khung thành nhiều gói → bản 16/11k ĐÃ ghép lại đủ khung trước khi gửi (hết sọc / nhiễu do khung thiếu)."); said = True
    if vA is False and vB: print("  • Cỡ hình lẻ (không chia hết 16) làm hỏng hình → bản 16/11k ĐÃ luôn chọn cỡ chia hết 16."); said = True
    if vA is False and vC: print("  • 2 bộ nén chạy cùng lúc (xem trước + điều khiển) làm hỏng hình → gửi dòng này cho Claude."); said = True
    if vA is False and vD: print("  • Xin 60 khung làm hỏng hình → gửi dòng này cho Claude."); said = True
    if vA:
        print("  • Ngay cả cỡ thường cũng hỏng → bộ nén / màn hình trong máy ảo đang lỗi ở FPS hiện tại của máy. Xem ảnh "
              f"{os.path.basename(base)}_A_man.png (màn hình thật): ảnh đó cũng nhiễu = lỗi giả lập, ảnh đẹp = lỗi bộ nén → gửi Claude cả phần này."); said = True
    if not said and "A" not in got:
        print("  • Lần thử A (cỡ thường) không lấy được hình → chưa kết luận được, chạy lại lệnh khi máy đứng yên ở màn hình chính."); said = True
    if not said:
        print("  • Hình phát ra từ máy SẠCH ở mọi kiểu thử → lỗi nằm ở đường truyền / trình duyệt của khách (gửi Claude phần này + ảnh khách chụp).")
    print(f"  (file: {base}_*.h264 / *_hinh.png / *_man.png)")
    return 0


class _QuietNet(logging.Filter):
    """13/11d: bỏ cảnh báo của asyncio khi app ngắt ngang ("SSL connection is closed", "socket.send() raised exception.")."""
    def filter(self, rec):
        m = rec.getMessage()
        return not (m.startswith("SSL connection is closed") or m.startswith("socket.send() raised exception"))

_NET_QUIET = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)
_net_noise = [0, 0.0]
def _loop_err(loop, ctx):
    """13/11d: app / trình duyệt ngắt ngang (WinError 10054 / 10053, TLS đóng dở, máy quét cổng…) là chuyện thường → không in traceback
       đỏ đầy nhật ký phát hình (admin tưởng lỗi). Lỗi khác vẫn in như cũ. 30 phút ghi 1 dòng đếm."""
    e = ctx.get("exception"); msg = str(ctx.get("message") or "")
    noise = isinstance(e, _NET_QUIET) or (isinstance(e, OSError) and getattr(e, "winerror", None) in (64, 121, 1236, 10053, 10054, 10060)) \
        or (isinstance(e, ssl.SSLError) and msg.startswith(("SSL handshake failed", "Fatal error on SSL transport", "Error on reading from the event loop")))
    if not noise:
        try: loop.default_exception_handler(ctx)
        except Exception: pass
        return
    _net_noise[0] += 1
    if time.time() - _net_noise[1] > 1800:
        if _net_noise[1]: log(f"  (30 phút qua: {_net_noise[0]} lần app / trình duyệt ngắt ngang — bình thường, không in chi tiết)")
        _net_noise[0] = 0; _net_noise[1] = time.time()

async def main():
    logging.getLogger("asyncio").addFilter(_QuietNet())
    asyncio.get_running_loop().set_exception_handler(_loop_err)
    if not SELFTEST and (not SB or not KEY):
        log("THIẾU SUPABASE_URL / SUPABASE_SERVICE_KEY trong cloudphone.conf"); sys.exit(1)
    if WIN:
        try: import numpy, windows_capture  # noqa: F401
        except ModuleNotFoundError:
            log("cài thư viện quay cửa sổ (windows-capture, numpy)…")
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "windows-capture", "numpy"], creationflags=NOWIN)
        except ImportError:
            pass                                         # Windows 10 trước bản 1903: không có Windows Graphics Capture → quay bằng PrintWindow
        video_mode()                                     # ghi nhật ký cách lấy hình đang dùng (wgc / scrcpy / gdi)
        await asyncio.to_thread(ensure_ffmpeg)
        threading.Thread(target=ensure_jar, daemon=True).start()
    fp = ensure_cert()
    firewall()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, CKEY)
    ctx.sni_callback = sni_pick                           # trình duyệt hỏi dN.<miền> → chứng chỉ Let's Encrypt (đường thẳng web)
    web_ctx_load()
    srv1 = await asyncio.start_server(on_direct, "0.0.0.0", PORT, ssl=ctx, limit=1 << 20)
    srv2 = await asyncio.start_server(on_ws, "127.0.0.1", WS_PORT, limit=1 << 20)
    log(f"bluestream chạy · trực tiếp TLS :{PORT} (modem mở cổng TCP {PORT} về máy này) · WebSocket 127.0.0.1:{WS_PORT} · máy chủ {NODE_ID}"
        f" · {f'giữ cú bấm {int(TAP_HOLD * 1000)} ms' if TAP_HOLD else 'chạm gửi ngay'} · {'sửa app mở nhầm màn ảo' if DISPLAY_FIX else 'TẮT sửa màn ảo'}")
    log(f"mã chứng chỉ: {fp[:16]}…  · bộ nén: {'CPU x264' if ALWAYS_CPU else f'NVENC (tối đa {NVENC_MAX}) → x264'} · ffmpeg: {FF}"
        f" · bản {BS_VER}+{BS_SUB} (ngưỡng app chậm thẳng {LAG_DROP_MS['direct']} ms / vòng {LAG_DROP_MS['ws']} ms, vòng bắt đầu {WS_START_KBPS} kbps)")
    log(f"bật hình: giữ app chờ khi bật lâu · cửa sổ quay lỗi / ra hình đen → {WGC_BAD_S / 60:g} phút sau mở máy đó lấy hình thẳng từ Android (WGC_BAD_MIN)")
    log(f"lấy hình 17/11a: {video_mode()} · máy chủ LDPlayer mặc định lấy thẳng từ Android (ép quay cửa sổ: CAPTURE=wgc) · "
        "Windows đóng phiên quay cửa sổ ngay mà máy vẫn chạy → tự lấy thẳng từ Android")
    log("bản 17/11g: máy thức dậy / bật lại lâu thì báo thật cho khách · bật lỗi → tự khám máy (🩺) ghi vào nhật ký này")
    log("bản 21/11a: trạm trung chuyển máy PC cho thuê " + (f"BẬT (pcrelay {PCRELAY.PCRELAY_VER} — máy PC thuê nối vào cổng này, khách điều khiển qua web / app)"
        if PCRELAY else f"TẮT ({PCRELAY_ERR}) — phần máy điện thoại chạy như cũ"))
    log(f"bản 17/11f: KHÔNG gửi khung hình thiếu lát (chờ khung khoá kế thay vì hình vỡ) · cách chia lát phải lặp lại {SLICE_CONFIRM} khung mới tin, nhớ qua lần bật lại bộ nén · máy chủ vừa khởi động lại: khách mở máy nào máy đó lên trước")
    log(f"nén 16/11k: hình scrcpy cạnh chia hết 16 {'BẬT' if SCR_ALIGN == 16 else 'TẮT'} · ghép lát {'BẬT' if SLICE_JOIN else 'TẮT'} (chẩn đoán hình vỡ: python bluestream.py --kiemhinh TÊN_MÁY)")
    log(f"nén 16/11e: x264 {X264_PRESET} · NVENC {NVENC_PRESET} (thử khi bật bộ nén đầu tiên, lỗi → p1) · khung khoá mỗi {KEY_S:g} giây"
        + (f" · bộ đệm {VBV_S:g} giây" if VBV_S > 0 else "") + " · mạng kéo bitrate xuống thì bớt điểm ảnh / khung (mọi chất lượng)"
        " · máy Android gửi nhiều khung hơn đã xin thì tính bù · máy đang khởi động lại → báo khách chờ, tự vào khi máy lên")
    log("mở máy: " + ("màn hình Android đang tắt → tự bật sáng trước khi lấy hình (WAKE_ON_OPEN)" if WAKE_ON_OPEN else "KHÔNG tự bật sáng màn hình (WAKE_ON_OPEN=0)"))
    log(f"bản 17/11e: dán vào Termux bằng Ctrl+Alt+V {'BẬT' if PASTE_TERMUX else 'TẮT (PASTE_TERMUX=0)'} · mạng yếu: mức nhớ cũ hơn "
        f"{RATE_FRESH_S / 60:g} phút → bắt đầu ≥ {RATE_FRESH_KBPS} kbps, khách tự chọn chất lượng → dò lại, yên {CEIL_CALM_S / 60:g} phút → bỏ trần cũ")
    log(f"bản 27/11f: Android 9 cbvideo — " + ((f"lấy hình bằng cbvideo.jar (md5 {CBV_FILE[1][:8]}, đọc hình song song với nén, xin khung khoá tức thì) "
        + ("cho MỌI máy Android 9 (web ?cbv=0 = scrcpy)" if A9_CBV_MODE == "on" else "CHỈ phiên web ?cbv=1 (chế độ thử — STREAM_A9_CBVIDEO=1 để bật cho khách)")
        + f", lỗi thì tự quay về scrcpy {CBV_BAD_S // 60} phút") if A9_CBV and len(CBV_FILE[1]) == 32 else "TẮT (STREAM_A9_CBVIDEO=0) → scrcpy như 27/11e"))
    log(f"bản 27/11e: Android 9 mượt — hình ≤ {A9_MAXH or 'theo mức'} (trừ mức Nét), khung I mỗi {SCR_IFRAME_A9:g} giây, bỏ khung → bật lại bộ nén "
        f"sau {KEY_WAIT_S_A9:g} giây, ngưỡng app chậm ×{A9_LAG_MUL:g}, hàng chờ {A9_QWAIT:g} giây (khi dùng scrcpy), không dumpsys sau cú bấm · máy MuMu không đổi")
    if A9_CBV and (C.get("EMU") or "").strip().lower() == "ld":
        threading.Thread(target=ensure_cbv, daemon=True).start()        # máy chủ LDPlayer: tải sẵn cbvideo.jar (khách mở máy khỏi chờ tải)
    log(f"khung khoá scrcpy: Android 9 mỗi {SCR_IFRAME_A9:g} giây, chờ quá {KEY_WAIT_S_A9:g} giây thì bật lại bộ nén · máy khác mỗi "
        + (f"{SCR_KEY_S:g} giây THẬT theo khung/giây đang phát (SCRCPY_KEY_EVERY_S)" if SCR_KEY_S > 0 else f"{SCR_IFRAME:g} giây ở 60 khung/giây (kiểu cũ)")
        + (f", chờ quá {KEY_WAIT_S:g} giây thì bật lại" if KEY_WAIT_S else ""))
    log("máy tắt / Android chưa lên lúc khách mở: " + ("tự gọi bật máy đang TẮT + báo khách rõ + gợi ý nút Khởi động lại máy (BOOT_IF_OFF)" if BOOT_IF_OFF
        else "KHÔNG tự bật (BOOT_IF_OFF=0) — chỉ báo khách") + f" · mạng yếu: thấp nhất {MIN_KBPS} kbps, nhớ trần {CEIL_S / 60:g}–{CEIL_MAX_S / 60:g} phút,"
        f" khách mạng yếu thường xuyên nhớ mức {RATE_MEM_LONG_S / 3600:g} giờ")
    if not SELFTEST: threading.Thread(target=publish_loop, args=(fp,), daemon=True).start()
    if not SELFTEST and WEB_DIRECT and CF_TOKEN: threading.Thread(target=web_direct_loop, daemon=True).start()
    elif not SELFTEST: log(f"đường thẳng web: chưa bật — chạy 1 lần: python bluestream.py --webdirect (web / iPhone đang đi Cloudflare)")
    seen_task = None if SELFTEST else asyncio.create_task(seen_loop())          # ghi máy nào đang có người xem (máy ngủ) — giữ biến: task không bị dọn
    if not SELFTEST and UPNP: threading.Thread(target=upnp_loop, daemon=True).start()        # tự mở cổng TCP PORT trên modem (UPnP)
    elif not SELFTEST: log(f"UPnP: tắt (UPNP=0) — nhớ mở cổng TCP {PORT} về máy này bằng tay trong trang modem")
    async with srv1, srv2:
        await asyncio.gather(srv1.serve_forever(), srv2.serve_forever())


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    if "--captest" in sys.argv:
        _a = sys.argv[sys.argv.index("--captest") + 1:]
        if not _a: print("Cách dùng: python bluestream.py --captest TÊN_MÁY [CỔNG_ADB]"); sys.exit(2)
        sys.exit(captest(_a[0], _a[1] if len(_a) > 1 else None))
    if "--kiemhinh" in sys.argv:                                 # 16/11k: chẩn đoán hình vỡ / nhiễu màu của 1 máy
        _a = sys.argv[sys.argv.index("--kiemhinh") + 1:]
        sys.exit(kiemhinh(_a[0] if _a else None, _a[1] if len(_a) > 1 else None))
    if "--upnp" in sys.argv:                                     # thử mở cổng trên modem bằng UPnP (không chạy máy chủ)
        sys.exit(upnp_cli())
    if "--webdirect" in sys.argv:                                # bật / kiểm đường thẳng cho web + iPhone (mã Cloudflare, chứng chỉ)
        sys.exit(cmd_webdirect())
    if "--netcheck" in sys.argv:                                 # chẩn đoán đường nối thẳng (+ --fix: tự đổi sang cổng mở được)
        sys.exit(netcheck(fix="--fix" in sys.argv))
    if WIN:
        try: ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000)   # ABOVE_NORMAL (ffmpeg con cũng vậy)
        except Exception: pass
    asyncio.run(main())
