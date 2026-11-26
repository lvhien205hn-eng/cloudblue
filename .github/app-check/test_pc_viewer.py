# Thử nhanh phần chế độ máy PC của cửa sổ máy (bluepc.Viewer._input) bằng pygame GIẢ — không cần màn hình
import os, sys, types, tempfile
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # máy Windows CI dùng cp1252
except Exception: pass
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1])
import bluepc as B
OK = FAIL = 0
def ck(n, c, x=""):
    global OK, FAIL
    if c: OK += 1; print("  ✓", n)
    else: FAIL += 1; print("  ✗", n, "→", x)
pg = types.SimpleNamespace(MOUSEMOTION=1, MOUSEBUTTONDOWN=2, MOUSEBUTTONUP=3, MOUSEWHEEL=4, TEXTINPUT=5, KEYDOWN=6, KEYUP=7, WINDOWFOCUSGAINED=8, WINDOWFOCUSLOST=9,
                           KMOD_CTRL=64, KMOD_SHIFT=1, KMOD_ALT=256, K_F11=1073741892, K_F10=1073741891, K_F5=1073741886, K_F3=1073741884, K_r=114, K_u=117, K_k=107, K_v=118,
                           K_a=97, K_b=98, K_1=49, K_LSHIFT=1073742049, K_LCTRL=1073742048, K_LALT=1073742050, K_ESCAPE=27, K_TAB=9, K_F1=1073741882, K_F12=1073741893,
                           K_RETURN=13, K_SPACE=32, K_KP_ENTER=1073741912, K_LGUI=1073742051)
for i in range(26): setattr(pg, "K_" + chr(97 + i), 97 + i)
for i in range(10): setattr(pg, "K_%d" % i, 48 + i)
for i in range(1, 13): setattr(pg, "K_F%d" % i, 1073741881 + i)
mods = [0]
pg.key = types.SimpleNamespace(get_mods=lambda: mods[0], name=lambda k: "")
pg.mouse = types.SimpleNamespace(get_pos=lambda: (100, 100))
class FakeCli:
    def __init__(self): self.ev = []
    def mouse(self, a, b, x, y): self.ev.append(("m", a, b, round(x, 2), round(y, 2)))
    def key(self, a, code, meta=0): self.ev.append(("k", a, code, meta))
    def text(self, s): self.ev.append(("t", s))
    def cmd(self, n): self.ev.append(("c", n))
    def touch(self, *a): self.ev.append(("touch",) + a)
    def scroll(self, *a): self.ev.append(("s",) + a)
    def clip_set(self, t, p=True): self.ev.append(("clip", t) if p is True else ("clip", t, p))
    def quality(self, q, fps=None, kbps=None, fpsx=None): self.ev.append(("q", q, fpsx))
v = B.Viewer("22222222-2222-4222-8222-222222222222", None, pc=True)
cli = FakeCli()
v._cx = lambda: cli; v._tool_at = lambda pos: None; v._norm = lambda pos: (0.25, 0.5); v._clamp = lambda pos: (0.25, 0.5)
v.state = ("connected", ""); v.docked = False; v.notice_rect = None; v.notice = None
E = lambda **k: types.SimpleNamespace(**k)
import time
v._input(E(type=1, pos=(10, 10)), pg); time.sleep(0.01)
v._input(E(type=2, pos=(10, 10), button=1), pg); v._input(E(type=3, pos=(10, 10), button=1), pg)
v._input(E(type=2, pos=(10, 10), button=3), pg); v._input(E(type=3, pos=(10, 10), button=3), pg)
v._input(E(type=2, pos=(10, 10), button=2), pg); v._input(E(type=3, pos=(10, 10), button=2), pg)
ck("rê chuột + trái / phải / giữa → C_MOUSE đúng nút, nhấn + nhả", cli.ev == [("m", 0, 0, 0.25, 0.5), ("m", 1, 0, 0.25, 0.5), ("m", 2, 0, 0.25, 0.5), ("m", 1, 1, 0.25, 0.5), ("m", 2, 1, 0.25, 0.5),
                                                                        ("m", 1, 2, 0.25, 0.5), ("m", 2, 2, 0.25, 0.5)], cli.ev)
ck("máy PC: không gửi chạm (touch) và không biến chuột phải thành Back", not any(e[0] in ("touch", "c") for e in cli.ev))
cli.ev.clear()
for k in (pg.K_LCTRL, pg.K_LSHIFT, pg.K_ESCAPE): v._input(E(type=6, key=k), pg)
for k in (pg.K_ESCAPE, pg.K_LSHIFT, pg.K_LCTRL): v._input(E(type=7, key=k), pg)
v._input(E(type=6, key=pg.K_F5), pg); v._input(E(type=7, key=pg.K_F5), pg)
v._input(E(type=6, key=pg.K_a), pg); v._input(E(type=5, text="a"), pg); v._input(E(type=7, key=pg.K_a), pg)
v._input(E(type=5, text="ế"), pg)
ck("phím thật: Ctrl+Shift+Esc, F5 (không bị app giữ để tải lại hình), chữ a không gửi 2 lần, chữ có dấu gửi bằng TEXT",
   cli.ev == [("k", 0, 113, 0), ("k", 0, 59, 0), ("k", 0, 111, 0), ("k", 1, 111, 0), ("k", 1, 59, 0), ("k", 1, 113, 0), ("k", 0, 135, 0), ("k", 1, 135, 0),
              ("k", 0, 29, 0), ("k", 1, 29, 0), ("t", "ế")], cli.ev)
cli.ev.clear()
v._input(E(type=7, key=pg.K_b), pg)
ck("nhả phím chưa từng nhấn (nhấn lúc cửa sổ khác đang được chọn) → bỏ qua", cli.ev == [], cli.ev)
mods[0] = pg.KMOD_CTRL
B.clip_get = lambda: "chu dan"
v._input(E(type=6, key=pg.K_v), pg); mods[0] = 0
ck("Ctrl+V → dán chữ của máy mình sang máy PC", cli.ev == [("clip", "chu dan")], cli.ev)
cli.ev.clear()
mods[0] = pg.KMOD_CTRL | pg.KMOD_SHIFT
v._input(E(type=6, key=pg.K_v), pg); v._input(E(type=7, key=pg.K_v), pg); mods[0] = 0
ck("23/11b Ctrl+Shift+V (Konsole máy Linux…) → cũng dán chữ của máy mình, kiểu 2 (máy bấm đúng Ctrl+Shift+V), không gửi phím V", cli.ev == [("clip", "chu dan", 2)], cli.ev)
cli.ev.clear()
v._input(E(type=6, key=pg.K_LSHIFT), pg); v._input(E(type=2, pos=(1, 1), button=1), pg)
v._input(E(type=9), pg)
ck("mất tiêu điểm khi đang giữ Shift + chuột trái → nhả hết", ("k", 1, 59, 0) in cli.ev and ("m", 2, 0, 0.5, 0.5) in cli.ev and not v.pc_keys and not v.pc_down, cli.ev)
cli.ev.clear()
for n in ("win", "alttab", "taskmgr", "back", "recents"): v._tool(n, pg)
ck("thanh công cụ máy PC: Windows / Alt+Tab / Task Manager / Esc / Win+Tab", cli.ev == [("c", "win"), ("c", "alttab"), ("c", "taskmgr"), ("c", "back"), ("c", "recents")], cli.ev)
ck("thanh công cụ máy PC không có nút Android (xoay, chụp, công cụ APK)", [n for n, _, _ in v._tool_rects(1280, 800)] == [n for n, _ in B.PC_TOOLS]
   and not {"rotate", "shot", "tools", "home"} & {n for n, _ in B.PC_TOOLS})
v2 = B.Viewer("33333333-3333-4333-8333-333333333333", None)
cli2 = FakeCli(); v2._cx = lambda: cli2; v2._tool_at = lambda pos: None; v2._norm = lambda pos: (0.5, 0.5); v2._clamp = lambda pos: (0.5, 0.5); v2.state = ("connected", ""); v2.docked = False
v2._input(E(type=2, pos=(1, 1), button=3), pg); v2._input(E(type=2, pos=(1, 1), button=1), pg)
ck("điện thoại đám mây (không --pc): chuột phải vẫn là Back, chuột trái vẫn là chạm như cũ", cli2.ev[0] == ("c", "back") and cli2.ev[1][0] == "touch" and not v2.pc, cli2.ev)
# ---- 21.11k: máy PC — Siêu nét + khách tự chọn khung hình/giây · đồng bộ chuột giữa các máy PC
cli.ev.clear(); v.q = "auto"; v.fpsx = 0; v._say = lambda *a, **k: None
v._tool("quality", pg); v._tool("quality", pg)
ck("máy PC: nút Chất lượng có Siêu nét (Tự động → Siêu nét → Nét …), nhớ riêng cho máy PC", [e[1] for e in cli.ev] == ["uhd", "hd"] and B.prefs().get("pcq") == "hd"
   and [k for k, _ in B.PC_QUALITIES] == ["auto", "uhd", "hd", "bal", "eco"], (cli.ev, B.prefs().get("pcq")))
cli.ev.clear()
for _ in range(4): v._tool("fps", pg)
ck("máy PC: nút FPS → Mặc định → 30 → 60 → 120 → Mặc định, mỗi lần gửi kèm fpsx, nhớ lựa chọn", [e[2] for e in cli.ev] == [30, 60, 120, 0] and B.prefs().get("pcf") == 0
   and "fps" in [n for n, _ in B.PC_TOOLS], cli.ev)
v2.q = "auto"; cli2.ev.clear(); v2._tool("quality", pg)
ck("điện thoại đám mây: nút Chất lượng như cũ (không có Siêu nét 2K, không gửi fpsx)", cli2.ev == [("q", "hd", None)] and B.prefs().get("q") == "hd", cli2.ev)
import struct
sl = B.SyLink.__new__(B.SyLink); sl.pc = True; sl.mdown = {}; sl.down = {}; sl.txt = {}
c3 = FakeCli()
sl._apply("t1", c3, B.SY_MOUSE, 0, 0, struct.pack("<HH", 32768, 16384)); sl._apply("t1", c3, B.SY_MOUSE, 1, 0, struct.pack("<HH", 32768, 16384))
sl._apply("t1", c3, B.SY_MOUSE, 2, 0, struct.pack("<HH", 32768, 16384)); sl._apply("t1", c3, B.SY_MOUSE, 2, 1, struct.pack("<HH", 1, 1))
sl._apply("t1", c3, B.SY_MOUSE, 1, 1, struct.pack("<HH", 0, 65535)); sl._release("t1", c3)
ck("đồng bộ chuột máy PC: rê / nhấn / nhả theo máy bạn; nhả nút chưa nhấn thì bỏ; máy bạn rời nhóm → nhả hộ nút đang giữ",
   c3.ev == [("m", 0, 0, 0.5, 0.25), ("m", 1, 0, 0.5, 0.25), ("m", 2, 0, 0.5, 0.25), ("m", 1, 1, 0.0, 1.0), ("m", 2, 1, 0.0, 1.0)], c3.ev)
sl.pc = False; c4 = FakeCli(); sl._apply("t1", c4, B.SY_MOUSE, 1, 0, struct.pack("<HH", 1, 1))
ck("cửa sổ điện thoại đám mây KHÔNG làm theo chuột máy PC", c4.ev == [], c4.ev)
class _S:
    def __init__(self): self.ev = []
    def mouse(self, *a): self.ev.append(a)
sy = _S(); c5 = FakeCli(); tee = B._SyTee(c5, sy); tee.mouse(1, 0, 0.5, 0.5)
ck("đang đồng bộ: chuột của máy PC đang thao tác vừa gửi cho máy này vừa ghi cho các máy bạn", c5.ev == [("m", 1, 0, 0.5, 0.5)] and sy.ev == [(1, 0, 0.5, 0.5)], (c5.ev, sy.ev))
# ---- 22/11 · SQL v48: ⏻ Nguồn máy — trạng thái theo lệnh khởi động lại / tắt máy gần nhất (giống web)
import datetime
_now = B.now_utc()
_iso = lambda s: (_now + datetime.timedelta(seconds=s)).isoformat()
def _it(online, p, until=3 * 86400): return {"rental": 1, "state": "active", "until": _iso(until), "pc": {"id": "x", "online": online, "job": None, "last_job": None, "pow": p}}
_P = lambda cmd, st, ago, by="customer": {"cmd": cmd, "state": st, "at": _iso(-ago), "by": by}
cases = [("run", _it(True, None)), ("boot", _it(True, _P("reboot", "done", 60))), ("run", _it(True, _P("reboot", "done", 200))),
         ("boot", _it(False, _P("reboot", "done", 300, "admin"))), ("off", _it(False, _P("reboot", "done", 1200))), ("boot", _it(True, _P("reboot", "queued", 30))),
         ("off", _it(False, _P("reboot", "queued", 30, "admin"))), ("down", _it(True, _P("shutdown", "done", 20))), ("run", _it(True, _P("shutdown", "done", 400))),
         ("offd", _it(False, _P("shutdown", "done", 1200))), ("offd", _it(False, _P("shutdown", "sent", 90, "admin"))), ("down", _it(True, _P("shutdown", "queued", 30, "admin"))),
         ("exp", _it(False, _P("shutdown", "done", 1200), until=-60)), ("run", _it(True, {"cmd": "x", "at": _iso(-5)})), ("run", _it(True, "la"))]
got = [B.vps_state(x)[0] for _, x in cases]
ck("⏻ Nguồn máy (v48): đang khởi động lại (3 phút đầu; máy chưa báo về thì tới 15 phút) · đang tắt · đã tắt hẳn · lệnh chưa tới máy đang tắt thì bỏ · hết hạn vẫn ưu tiên",
   got == [w for w, _ in cases], got)
w1, w2 = B.vps_state(cases[9][1])[3], B.vps_state(cases[10][1])[3]
ck("đã tắt: ghi ai tắt + giờ tắt (khách / shop)", ("Bạn đã tắt máy lúc" in w1 or "You shut it down at" in w1) and ("Shop đã tắt máy lúc" in w2 or "The shop shut it down at" in w2), (w1, w2))
ck("lỗi OFFLINE / BAD_CMD có câu dễ hiểu (không hiện mã lỗi)", "OFFLINE" not in B.vps_err("P0001: OFFLINE") and "BAD_CMD" not in B.vps_err("BAD_CMD"))
ck("dấu vân tay thẻ VPS đổi khi có lệnh nguồn (vẽ lại thẻ)", B.vps_sig({"items": [cases[0][1]]}) != B.vps_sig({"items": [cases[1][1]]}))
# ---- 22/11 · SQL v49: đổi Android giữ cấu hình ĐÃ MUA (paid_ram / paid_cpu) — hết "rớt nhân"
_pr = {"android_versions": "9,12,15", "android_limits": {"9": {"ram": 8, "cpu": 8}, "12": {"ram": 16, "cpu": 32}, "15": {"ram": 16, "cpu": 32}}, "max_ram": 16, "max_cpu": 32}
_p9 = {"ram": 8, "cpu": 8, "paid_ram": 8, "paid_cpu": 12, "android": "9"}
ck("cấu hình đã mua = lớn hơn của (đang chạy, paid) · chưa chạy v49 (không có cột) = đang chạy", B.paid_cfg(_p9) == (8, 12) and B.paid_cfg({"ram": 4, "cpu": 6}) == (4, 6))
ck("máy tạm hạ: thẻ ghi '(đã mua 12 nhân)' · máy đủ: không ghi gì", B.paid_tag(_p9) in (" (đã mua 12 nhân)", " (bought 12 cores)")
   and B.paid_tag({"ram": 8, "cpu": 12, "paid_ram": 8, "paid_cpu": 12}) == "" and B.paid_tag({"ram": 6, "cpu": 6}) == "", B.paid_tag(_p9))
ck("bản Android chạy ĐỦ cấu hình đã mua: Android 12 / 15", B.full_and(_pr, _p9) == ["12", "15"], B.full_and(_pr, _p9))
_sw = types.SimpleNamespace(pr=_pr, p=_p9)
ck("hộp đổi Android: máy Android 9 (tạm 8 nhân) → Android 12 được trả đủ 8GB · 12 nhân; → Android 9 vẫn 8 · 8",
   B.SwitchDlg.new_cfg(_sw, "12")[:2] == (8, 12) and B.SwitchDlg.new_cfg(_sw, "9")[:2] == (8, 8), (B.SwitchDlg.new_cfg(_sw, "12"), B.SwitchDlg.new_cfg(_sw, "9")))
_sw2 = types.SimpleNamespace(pr=_pr, p={"ram": 16, "cpu": 16, "android": "12"})
ck("máy 16GB · 16 nhân → Android 9 tạm 8 · 8 (cấu hình đã mua vẫn 16 · 16)", B.SwitchDlg.new_cfg(_sw2, "9")[:2] == (8, 8) and B.paid_cfg(_sw2.p) == (16, 16))
# ---- 22/11 · "Mất kết nối — đang nối lại" trên máy PC: hết phiên thì không còn tưởng "máy đang được bật lên"
_v = B.Viewer("44444444-4444-4444-8444-444444444444", None, pc=True)
_v.auto_at = 0.0; _v.fixing = False; _v.stall = False; _v.slow = False
_v.cli = types.SimpleNamespace(last_rx=time.time(), hello_t=0.0); _v.state = ("reconnecting", "Mất kết nối — đang nối lại…")
_v._watch()
ck("vừa mất kết nối (phiên cũ đã hết, hello_t = 0) → KHÔNG hiện 'đang chờ máy bật lên'", _v.slow is False)
_v.cli.hello_t = time.time() - 10; _v._watch()
ck("phiên mới chờ máy chủ cho vào > 8 giây (máy chủ vẫn giữ kết nối) → hiện câu chờ", _v.slow is True)
import brstream as _BS
ck("brstream: TLS an toàn nhiều luồng (Tls qua MemoryBIO) dùng cho cả đường thẳng lẫn đường vòng",
   hasattr(_BS, "Tls") and "Tls(raw, ctx" in open(_BS.__file__, encoding="utf-8").read() and "wrap_socket" not in open(_BS.__file__, encoding="utf-8").read())
# ---- 22/11 · 🌐 Proxy riêng của máy (thẻ Proxy trong Công cụ — chỉ Cloud Phone)
ck("Công cụ có thẻ Proxy (sau Root), 8 thẻ chia 2 hàng", [k for k, _ in B.ToolsDlg.TABS][5:7] == ["root", "proxy"] and len(B.ToolsDlg.TABS) == 8)
_ps = lambda j: B.px_status(j)
ck("chưa dùng proxy → 'Chưa dùng proxy'", _ps({"set": False})[0] in ("Chưa dùng proxy", "No proxy"))
_j = {"set": True, "kind": "auto", "show": "9.8.7.6:1080:khach:••••", "online": True, "state": {"mode": "proxy", "kind": "socks5", "ip": "5.6.7.8", "ms": 80, "alive": True}}
ck("đang qua proxy: che mật khẩu + kiểu thật SOCKS5 + IP ra + ms, màu OK",
   _ps(_j)[0] == "9.8.7.6:1080:khach:•••• · SOCKS5" and _ps(_j)[2] in ("✅ Đang chạy qua proxy · IP ra 5.6.7.8 · 80 ms", "✅ Running through the proxy · exit IP 5.6.7.8 · 80 ms") and _ps(_j)[3] == B.OK, _ps(_j))
_j2 = dict(_j, state={"mode": "direct", "err": "proxy báo SAI user / mật khẩu", "alive": True})
ck("proxy lỗi → báo lý do + đang đi mạng thường, màu cảnh báo", "SAI user" in _ps(_j2)[2] and _ps(_j2)[3] == B.WARN, _ps(_j2))
ck("máy tắt → proxy tự bật khi máy bật", "proxy" in _ps(dict(_j, online=False, state=None))[2])
ck("proxy dừng hẳn → nhắc Áp dụng lại, màu đỏ", _ps(dict(_j, state={"mode": "crashed", "err": "iptables lỗi"}))[3] == B.BAD)
_src = open(B.__file__, encoding="utf-8").read()
ck("ô proxy xoá ngay sau khi gửi (không giữ mật khẩu) + gửi {do:set, url, kind}", 'self.px_ent.delete(0, "end")' in _src and '{"do": "set", "url": url, "kind": self.px_kind}' in _src)
# ---- 22.11f · SQL v50: Linux CachyOS
ck("vps_lin: cachyos (cả chữ hoa) là Linux; 22h2 / 1511 / rỗng không", B.vps_lin("cachyos") and B.vps_lin("CachyOS") and not B.vps_lin("22h2") and not B.vps_lin(None))
ck("tên hệ điều hành: lấy theo danh sách bán, thiếu thì 'Linux CachyOS' / 'Windows 22H2'", B.vps_os_name("cachyos", [{"id": "cachyos", "name": "Linux CachyOS"}]) == "Linux CachyOS"
   and B.vps_os_name("cachyos") == "Linux CachyOS" and B.vps_os_name("22h2") == "Windows 22H2")
_ji = {"rental": 1, "state": "active", "until": _iso(3 * 86400), "pc": {"id": "x", "online": True, "job": {"state": "sent", "os": "cachyos", "at": _iso(-60)}, "last_job": None}}
_st = B.vps_state(_ji)
ck("thẻ máy đang cài CachyOS: 'Đang cài Linux CachyOS' + 30–60 phút", _st[0] == "inst" and "Linux CachyOS" in _st[1] and ("30–60 phút" in _st[3] or "30–60 min" in _st[3]), _st)
_jw = {"rental": 1, "state": "active", "until": _iso(3 * 86400), "pc": {"id": "x", "online": True, "job": {"state": "sent", "os": "1511", "at": _iso(-60)}, "last_job": None}}
ck("đang cài Windows vẫn ghi 15–30 phút", "15–30" in B.vps_state(_jw)[3], B.vps_state(_jw))
ck("lỗi CANT_OS có câu dễ hiểu", "CANT_OS" not in B.vps_err("P0001: CANT_OS") and ("Secure Boot" in B.vps_err("CANT_OS") or "edition" in B.vps_err("CANT_OS")))
_rt = B.vps_report_text(types.SimpleNamespace(prof={"username": "khach"}), dict(_ji, os_name="Linux CachyOS"))
ck("nội dung báo admin: 'Hệ điều hành: Linux CachyOS', việc 'Cài lại Linux CachyOS'", ("Hệ điều hành: Linux CachyOS" in _rt or "OS: Linux CachyOS" in _rt) and "Linux CachyOS — " in _rt, _rt)
ck("hộp đổi hệ điều hành lọc theo 'can' (v50) · máy chủ cũ ẩn Linux · lời cảnh báo đổi theo bản chọn",
   'if can is not None' in _src and 'not vps_lin(o.get("id"))' in _src and "def warn_upd(self)" in _src and "VPS_LIN_NOTE" in _src)
print(f"\n{OK}/{OK + FAIL} đạt"); sys.exit(1 if FAIL else 0)
