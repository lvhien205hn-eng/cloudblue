# -*- coding: utf-8 -*-
"""28/11h · 🖥 CPU ĐỦ CẢ 2 CPU + RAM CHÍNH (user 28/11 21:40: "máy x2 CPU mà toàn thấy báo 1 CPU · RAM cứ lấy RAM chính mà dùng,
   đến full mới dùng RAM ảo") — thử bằng Windows API giả:
   1. cloudphoned · đọc GetLogicalProcessorInformationEx → số CPU (socket) + mặt nạ luồng từng CPU (Python 64 / 32 bit)
   2. cloudphoned · đo CPU từng NHÓM (NtQuerySystemInformationEx) rồi cộng: máy 72 luồng = 2 nhóm → % cả máy + % từng CPU
   3. cloudphoned · sức chứa thật (RAM chính + luồng mọi CPU) tách khỏi lý do ngừng nhận (card kẹt xung / ổ / CPU nóng)
   4. cloudphoned · heartbeat thật với đồ giả: cap_*_full không còn = đã cấp khi card kẹt xung, metrics.stop / CPU / RAM ảo lên web
   5. phonectl · giãn lượt bật máy đo CPU đủ mọi nhóm · sua-tat-ca 28/11h tải đúng bản mới
   Chạy: python3 .github/win-check/test_2811h.py"""
import ast, contextlib, ctypes as C, io, json, os, re, struct, sys, tempfile, time as _tm, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True)


CPD = open(os.path.join(ROOT, "cloudphoned.py"), encoding="utf-8").read()
PCS = open(os.path.join(ROOT, "windows", "phonectl.py"), encoding="utf-8").read()
SUA = open(os.path.join(ROOT, "windows", "sua-tat-ca.py"), encoding="utf-8").read()
CPM, PCM = ast.parse(CPD), ast.parse(PCS)


def pick(mod, names, g, src="x.py"):
    for node in mod.body:
        if isinstance(node, (ast.FunctionDef, ast.Assign)) and (getattr(node, "name", None) in names or
                                                               (isinstance(node, ast.Assign) and any(getattr(t, "id", "") in names for t in node.targets))):
            exec(compile(ast.Module(body=[node], type_ignores=[]), src, "exec"), g)
    return g


def win_block(mod, fn, g, src="cloudphoned.py"):
    """Chạy khối `if WIN:` cấp module có định nghĩa hàm fn (ghi đè hàm trên Windows)."""
    for node in mod.body:
        if isinstance(node, ast.If) and getattr(node.test, "id", "") == "WIN" and any(isinstance(b, ast.FunctionDef) and b.name == fn for b in node.body):
            exec(compile(ast.Module(body=[node], type_ignores=[]), src, "exec"), g); return True
    return False


# ---------------------------------------------------------------- Windows API giả
M36 = (1 << 36) - 1


def lpi_rec(rel, groups, psize=8):
    """1 bản ghi SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX (PROCESSOR_RELATIONSHIP) như Windows trả."""
    ga = 16 if psize == 8 else 12
    body = bytes([0, 0]) + bytes(20) + struct.pack("<H", len(groups))       # Flags · EfficiencyClass · Reserved[20] · GroupCount → GroupMask ở byte 24 (thẳng hàng 8 / 4)
    for g, m in groups:
        body += struct.pack("<Q" if psize == 8 else "<I", m) + struct.pack("<H", g) + bytes(ga - psize - 2)
    return struct.pack("<II", rel, 8 + len(body)) + body


def cache_rec():
    return struct.pack("<II", 2, 48) + bytes(40)                           # bản ghi loại khác (bộ nhớ đệm) — phải bỏ qua


class FakeWin:
    """kernel32 + ntdll giả: 2 CPU × 36 luồng = 2 nhóm Windows (máy > 64 luồng)."""
    def __init__(self, groups=(36, 36)):
        self.groups = list(groups); self.t = {}           # (nhóm, luồng) → [rảnh, nhân, người dùng]
        for g, n in enumerate(self.groups):
            for i in range(n): self.t[(g, i)] = [0, 0, 0]
        self.ex_ok = True; self.calls = []
        k, nt = types.SimpleNamespace(), types.SimpleNamespace()

        def GetActiveProcessorGroupCount(): return len(self.groups)

        def GetActiveProcessorCount(g):
            g = getattr(g, "value", g)
            return sum(self.groups) if g == 0xFFFF else (self.groups[g] if g < len(self.groups) else 0)

        def GetLogicalProcessorInformationEx(rel, buf, ln_ref):
            pk = b"".join([cache_rec()] + [lpi_rec(3, [(g, (1 << n) - 1)]) for g, n in enumerate(self.groups)])
            core = b"".join(lpi_rec(0, [(g, 3 << (2 * c))]) for g, n in enumerate(self.groups) for c in range(n // 2))
            raw = pk if rel == 3 else core
            ln = ln_ref._obj
            if buf is None or ln.value < len(raw): ln.value = len(raw); return 0
            C.memmove(buf, raw, len(raw)); ln.value = len(raw); return 1

        def NtQuerySystemInformationEx(cls, gi_ref, gl, buf, size, ret_ref):
            g = gi_ref._obj.value; self.calls.append(("ex", cls, g, gl))
            if not self.ex_ok or cls != 8 or gl != 2: return -1073741821          # 0xC0000003
            rows = [self.t[(g, i)] for i in range(self.groups[g])]
            raw = b"".join(struct.pack("<qqqqqI4x", r[0], r[1], r[2], 0, 0, 0) for r in rows)
            if size < len(raw): return -1073741820                                  # 0xC0000004
            C.memmove(buf, raw, len(raw)); ret_ref._obj.value = len(raw); return 0

        def NtQuerySystemInformation(cls, buf, size, ret_ref):
            if cls != 18: return -1
            name = "\\??\\C:\\pagefile.sys".encode("utf-16-le")
            e1 = struct.pack("<IIII", 0, int(24 * 262144), int(0.5 * 262144), int(1.5 * 262144)) + struct.pack("<HH4xQ", len(name), len(name), 0)
            C.memmove(buf, e1, len(e1)); ret_ref._obj.value = len(e1); return 0
        for f in (GetActiveProcessorGroupCount, GetActiveProcessorCount, GetLogicalProcessorInformationEx): setattr(k, f.__name__, f)
        nt.NtQuerySystemInformationEx = NtQuerySystemInformationEx; nt.NtQuerySystemInformation = NtQuerySystemInformation
        self.windll = types.SimpleNamespace(kernel32=k, ntdll=nt)

    def run(self, g, sec, busy_pct):
        """Cho nhóm g chạy sec giây ở busy_pct % (mỗi luồng)."""
        for (gg, i), r in self.t.items():
            if gg != g: continue
            tot = int(sec * 1e7); b = int(tot * busy_pct / 100)
            r[0] += tot - b; r[1] += (tot - b) + b // 2; r[2] += b - b // 2      # nhân (kernel) đã gồm rảnh

    def module(self):
        m = types.ModuleType("ctypes")
        for n in ("create_string_buffer", "c_ulong", "c_ushort", "c_long", "c_void_p", "byref", "sizeof", "memmove"): setattr(m, n, getattr(C, n))
        m.windll = self.windll
        return m


@contextlib.contextmanager
def fake_ctypes(fw):
    old = sys.modules.get("ctypes"); sys.modules["ctypes"] = fw.module()
    try: yield
    finally: sys.modules["ctypes"] = old


# ============================================================== 1
print("1. cloudphoned · số CPU (socket) + luồng từng CPU từ GetLogicalProcessorInformationEx")
G = {"time": _tm, "os": os, "WIN": True, "_CPU": {"info": None, "t": 0.0, "prev": None, "sock": None, "grp": None}}
pick(CPM, ("_lpi_parse", "_lpi", "win_cpu_info", "cpu_threads", "_win_cpu_times", "_cpu_split", "win_swap", "cpu_hot5"), G, "cloudphoned.py")
raw = cache_rec() + lpi_rec(3, [(0, M36)]) + lpi_rec(0, [(0, 3)]) + lpi_rec(3, [(1, M36)])
ck("2 CPU × 36 luồng (2 nhóm) xen bản ghi khác → đúng 2 CPU, mỗi CPU 1 nhóm, mặt nạ 36 luồng",
   G["_lpi_parse"](raw, 3) == [[(0, M36)], [(1, M36)]], G["_lpi_parse"](raw, 3))
raw32 = lpi_rec(3, [(0, 0xFFFF)], 4) + lpi_rec(3, [(0, 0xFFFF0000)], 4)
ck("Python 32 bit (mặt nạ 4 byte): đọc đúng bố cục", G["_lpi_parse"](raw32, 3, 4) == [[(0, 0xFFFF)], [(0, 0xFFFF0000)]], G["_lpi_parse"](raw32, 3, 4))
ck("dữ liệu hỏng (kích thước 0 / cụt) → dừng, không lỗi", G["_lpi_parse"](struct.pack("<II", 3, 0) + bytes(40), 3) == [] and G["_lpi_parse"](b"\x03\x00", 3) == [])
fw = FakeWin()
with fake_ctypes(fw):
    info = G["win_cpu_info"](force=True)
ck("máy 2 CPU 72 luồng (Windows chia 2 nhóm) → threads 72 · groups 2 · sockets 2 · cores 36",
   info["threads"] == 72 and info["groups"] == 2 and info["sockets"] == 2 and info["cores"] == 36 and len(info["pk"]) == 2, {k: v for k, v in info.items() if k != "pk"})
ck("cpu_threads() = 72 (cộng mọi nhóm, không phải 36 của 1 CPU)", G["cpu_threads"]() == 72)
G["WIN"] = False
ck("máy chủ Linux → os.cpu_count() như cũ", G["cpu_threads"]() == (os.cpu_count() or 1))
G["WIN"] = True

# ============================================================== 2
print("2. cloudphoned · % CPU cả máy = cộng mọi nhóm + % từng CPU")
calls = []
G["_cpu_pct_gst"] = None
G["cpu_pct"] = lambda: calls.append("gst") or 33.0                         # cách cũ (GetSystemTimes qua run.py) — dự phòng
ck("khối `if WIN:` ghi đè cpu_pct có trong cloudphoned", win_block(CPM, "cpu_pct", G))
with fake_ctypes(fw):
    G["_CPU"]["info"] = info; G["_CPU"]["t"] = _tm.time()
    p0 = G["cpu_pct"]()
    fw.run(0, 30, 10); fw.run(1, 30, 90)                                    # CPU 1 rảnh, CPU 2 gánh hết (máy ảo dồn vào 1 nhóm)
    p1 = G["cpu_pct"]()
ck("lần đầu chưa có mốc → None (như bản Linux)", p0 is None, p0)
ck("CPU 1 10% · CPU 2 90% → cả máy 50% (cách cũ chỉ thấy 1 nhóm: 10% hoặc 90%)", p1 == 50.0, p1)
ck("nhóm nóng nhất (90%) ghi vào TB 5 phút cpu_hot5 → 90", G["cpu_hot5"]() == 90.0, G["_CPU"].get("hot_h"))
ck("% từng CPU = [10, 90] · % từng nhóm = [10, 90]", G["_CPU"]["sock"] == [10.0, 90.0] and G["_CPU"]["grp"] == [10.0, 90.0], (G["_CPU"]["sock"], G["_CPU"]["grp"]))
ck("đọc từng nhóm bằng NtQuerySystemInformationEx(SystemProcessorPerformanceInformation, số nhóm 2 byte)",
   ("ex", 8, 0, 2) in fw.calls and ("ex", 8, 1, 2) in fw.calls and "gst" not in calls, fw.calls[-4:])
fw.ex_ok = False
with fake_ctypes(fw): p2 = G["cpu_pct"]()
ck("Windows không đọc được từng nhóm → về cách cũ (không lỗi, không mất số)", p2 == 33.0 and calls == ["gst"] and G["_CPU"]["sock"] is None, (p2, calls))
fw.ex_ok = True
fw1 = FakeWin(groups=(56,))
with fake_ctypes(fw1):
    G["_CPU"].update(prev=None, info={"threads": 56, "groups": 1, "sockets": 2, "cores": 28, "name": "", "pk": [[(0, (1 << 28) - 1)], [(0, ((1 << 56) - 1) ^ ((1 << 28) - 1))]]})
    G["cpu_pct"]()
    for i in range(56): fw1.t[(0, i)][0] += int(3e8 * (0.8 if i < 28 else 0.2)); fw1.t[(0, i)][1] += int(3e8)
    p3 = G["cpu_pct"]()
ck("máy 2 CPU × 28 luồng (56 ≤ 64 → 1 nhóm): % từng CPU theo mặt nạ luồng [20, 80], cả máy 50%",
   p3 == 50.0 and G["_CPU"]["sock"] == [20.0, 80.0] and G["_CPU"]["grp"] is None, (p3, G["_CPU"]["sock"], G["_CPU"]["grp"]))
with fake_ctypes(fw): sw = G["win_swap"]()
ck("RAM ảo (tệp hoán đổi) đọc bằng SystemPageFileInformation → (0.5 GB đang dùng, 24 GB)", sw == (0.5, 24.0), sw)
G["WIN"] = False
ck("máy chủ Linux → win_swap None", G["win_swap"]() is None)
G["WIN"] = True

# ============================================================== 3
print("3. cloudphoned · sức chứa THẬT (RAM chính + mọi CPU) tách khỏi lý do ngừng nhận")
H = {"MEMU_MAX_RAM": 16.0, "MEMU_MAX_CPU": 32.0, "WIN_RESERVE": 3.0, "CPU_OVER": 1.8, "CAP_CPU": 100.0, "CPU_SELL_X": 2.0, "CPU_KEEP": 4.0,
     "WIN_VCPU_OVER": 1.8, "CAP_RAM": 112.0, "RAM_BUSY": 98, "CPU_BUSY": 85, "MEMU_MAX_VMS": 0,
     "meminfo": lambda: (127.9, 85.2), "cpu_threads": lambda: 72, "sleep_reserve": lambda st: (0.0, 0.0, 0),
     "cpu_avg5": lambda: 7.6, "cpu_hot5": lambda: None, "CPU_HOT": 95.0, "disk_full": lambda: False, "gpu_busy": lambda: "gpu"}
pick(CPM, ("caps_stop", "win_caps"), H, "cloudphoned.py")
ST = [{"name": "cp_%d" % i, "ram": r, "cpu": c} for i, (r, c) in enumerate([(6, 4), (6, 4), (4, 3), (4, 4), (4, 4), (4, 4), (5, 3), (4, 3), (4, 2)])]
a_r, a_c = sum(p["ram"] for p in ST), sum(p["cpu"] for p in ST)
full = H["win_caps"](ST, full=True)
ck("Server 8 (card kẹt xung, 9 máy · 41 GB · 31 nhân): sức chứa THẬT 112 GB (trần) · 100 nhân (72 luồng × 2 − 4 = 140 → trần 100) + lý do ['gpu']",
   (a_r, a_c) == (41, 31) and full == (41.0, 31.0, 112.0, 100.0, ["gpu"]), full)
ck("sức chứa BÁN vẫn = đã cấp (đơn mới sang máy chủ khác như cũ): 41 / 31", H["win_caps"](ST) == (41.0, 31.0, 41.0, 31.0), H["win_caps"](ST))
H["gpu_busy"] = lambda: ""
ck("card khoẻ lại → bán tiếp ngay tới sức chứa thật (không chờ tự nhận lại)", H["win_caps"](ST) == (41.0, 31.0, 112.0, 100.0), H["win_caps"](ST))
H["cpu_avg5"] = lambda: 91.0
ck("CPU thật nóng 91% → chỉ hết chỗ NHÂN, RAM vẫn bán · lý do ['cpu']",
   H["win_caps"](ST) == (41.0, 31.0, 112.0, 31.0) and H["win_caps"](ST, full=True)[4] == ["cpu"], H["win_caps"](ST, full=True))
H["cpu_avg5"] = lambda: 7.6; H["meminfo"] = lambda: (127.9, 1.5)
f2 = H["win_caps"](ST, full=True)
ck("RAM chính dùng 99% (≥ 98%) → hết chỗ RAM · lý do ['ram'] · sức chứa thật ≈ đã cấp (RAM chính hết thật)",
   f2[4] == ["ram"] and f2[2] == 41.0 and H["win_caps"](ST)[2] == 41.0, f2)
H["meminfo"] = lambda: (127.9, 85.2); H["cpu_hot5"] = lambda: 97.0
ck("TB cả máy 7.6% nhưng 1 nhóm CPU 97% (máy ảo dồn vào 1 CPU) → ngừng bán NHÂN · lý do ['cpu1']",
   H["win_caps"](ST, full=True)[4] == ["cpu1"] and H["win_caps"](ST)[3] == 31.0 and H["win_caps"](ST)[2] == 112.0, H["win_caps"](ST, full=True))
H["cpu_hot5"] = lambda: 80.0
ck("nhóm nóng nhất 80% (< 95%) → bán bình thường", H["win_caps"](ST, full=True)[4] == [], H["win_caps"](ST, full=True))
H["cpu_hot5"] = lambda: None; H["cpu_threads"] = lambda: 36
ck("máy chỉ 1 CPU (36 luồng) → trần nhân 36 × 2 − 4 = 68", H["win_caps"](ST)[3] == 68.0, H["win_caps"](ST))
ck("caps_stop: ổ đầy → hết RAM · đủ số máy / VRAM / card kẹt → hết cả hai",
   H["caps_stop"](1, 2, 10, 20, ["disk"]) == (1, 20) and H["caps_stop"](1, 2, 10, 20, ["vms"]) == (1, 2) and H["caps_stop"](1, 2, 10, 20, ["gpu_stuck"]) == (1, 2)
   and H["caps_stop"](1, 2, 10, 20, ["vram"]) == (1, 2) and H["caps_stop"](1, 2, 10, 20, []) == (10, 20))

# ============================================================== 4
print("4. cloudphoned · heartbeat thật (đồ giả): Server 8 card kẹt xung")
POST = []
td = tempfile.mkdtemp(); PJ = os.path.join(td, "phones.json"); json.dump({"phones": ST}, open(PJ, "w"))
STUCK = {"name": "NVIDIA GeForce GTX 1080", "util": 95, "eff": 100.0, "clk": 139, "clk_max": 1974, "pwr": 10, "pwr_max": 180, "mem_used": 3324, "mem_total": 8192, "stuck": True}


class _HE(Exception): pass


HB = dict(H)
HB.update({"json": json, "os": os, "time": _tm, "subprocess": types.SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("docker"))),
           "urllib": types.SimpleNamespace(error=types.SimpleNamespace(HTTPError=_HE)), "PHONES_JSON": PJ, "WIN": True, "NODE_ID": "win55",
           "LIMIT_PCT": 90, "RAM_OVER": 1.0, "WIN_RAM_OVER": 1.0, "DISK_BUSY": 90, "GPU_BUSY": 85, "VRAM_BUSY": 90, "FULL_PCT": 100.0, "_FULL": {"until": 0.0},
           "cpu_threads": lambda: 72, "meminfo": lambda: (127.9, 85.2), "gpu_busy": lambda: "gpu", "cpu_avg5": lambda s=None: 7.6,
           "cpu_pct": lambda: 6.7, "disk_full": lambda: False, "gpus": lambda: [dict(STUCK)], "gf_fresh": lambda: None,
           "gpu_avg5": lambda s=None: (100.0, 40.6), "ram_sample": lambda *a: None, "rr_write": lambda st, a, c: (0.0, 0.0, 0),
           "sell_cap": lambda a, c, pct=None: max(a, c * 100.0 / 100), "busy_boot": lambda: "", "sick_why": lambda: "",
           "disk": lambda p: {"used": 110, "total": 456}, "DATA_ROOT": td, "ram_ratio": lambda: 1.0, "sw_info": lambda: {"ver": "28/11h"},
           "MV_ON": False, "mv_support": lambda: False, "clock_off": lambda: 0, "lag_pen": lambda: 25.0, "_CLK": {"last": ""}, "win_build": lambda: 10586,
           "WGC_MIN_BUILD": 18362, "socket": types.SimpleNamespace(gethostname=lambda: "WIN-TEST"), "autopause_tick": lambda lv: {"on": False, "lv": lv},
           "eng_due": lambda: False, "engine": lambda: {"emu": "mumu", "androids": ["12", "15"], "missing": []}, "_hb_old": {"v": False},
           "_alert": {"none": False, "full": None}, "notify": lambda t: None, "sb": lambda m, p, b=None, h=None: POST.append((m, p, b)),
           "now": lambda: __import__("datetime").datetime.now(), "BASE": "https://phone99.cloudblue.vn", "PRIMARY": False, "CPU_BUSY": 85,
           "win_cpu_info": lambda force=False: {"threads": 72, "groups": 2, "sockets": 2, "cores": 36, "name": "Intel(R) Xeon(R) CPU E5-2686 v4 @ 2.30GHz", "pk": []},
           "_CPU": {"sock": [5.1, 8.4], "grp": [5.1, 8.4]}, "win_swap": lambda: (0.5, 24.0), "cpu_temp": lambda: None})
pick(CPM, ("caps_stop", "win_caps", "heartbeat"), HB, "cloudphoned.py")    # chép lại để dùng đồ giả của HB
buf = io.StringIO()
with contextlib.redirect_stdout(buf): HB["heartbeat"]()
body = next((b for m, p, b in POST if m == "POST" and p == "cloud_nodes"), None)
mt = (body or {}).get("metrics", {})
ck("heartbeat chạy hết, gửi cloud_nodes (không lỗi)", body is not None, buf.getvalue()[-800:])
ck("sức chứa báo web = THẬT: 100 nhân · 112 GB (trước: 31 / 41 = đã cấp → web tưởng CPU / RAM đầy)",
   mt.get("cap_cpu_full") == 100.0 and mt.get("cap_ram_full") == 112.0, (mt.get("cap_cpu_full"), mt.get("cap_ram_full")))
ck("sức chứa BÁN vẫn = đã cấp (card kẹt → web không bán thêm vào máy chủ này)", body and body["cap_cpu"] == 31.0 and body["cap_ram"] == 41.0, body and (body["cap_cpu"], body["cap_ram"]))
ck("% đầy thật 37% (41/112) → không còn 'đầy 100%' giả làm máy chủ tự ngừng nhận", mt.get("fill_pct") == 36.6, mt.get("fill_pct"))
ck("lý do ngừng nhận = ['gpu_stuck'] (card kẹt xung nghỉ, không phải CPU / RAM)", mt.get("stop") == ["gpu_stuck"], mt.get("stop"))
ck("CPU lên web: 2 CPU · 72 luồng · 36 nhân · 2 nhóm · tên CPU · % từng CPU · luật trần [100, 2, 4]",
   mt.get("cpu_threads") == 72 and mt.get("cpu_sockets") == 2 and mt.get("cpu_cores") == 36 and mt.get("cpu_groups") == 2 and "E5-2686" in (mt.get("cpu_name") or "")
   and mt.get("cpu_sock_pct") == [5.1, 8.4] and mt.get("cpu_rule") == [100.0, 2.0, 4.0], {k: mt.get(k) for k in ("cpu_threads", "cpu_sockets", "cpu_cores", "cpu_groups", "cpu_name", "cpu_sock_pct", "cpu_rule")})
ck("RAM ảo lên web riêng (0.5 / 24 GB) · cpu_total 72 · RAM chính 127.9", mt.get("swap_used") == 0.5 and mt.get("swap_total") == 24.0 and body["cpu_total"] == 72 and body["ram_total"] == 127.9,
   (mt.get("swap_used"), mt.get("swap_total"), body and body["cpu_total"]))
ck("tự ngừng / tự nhận máy dùng % đầy THẬT", mt.get("autopause") == {"on": False, "lv": 36.6}, mt.get("autopause"))
POST.clear(); HB["gpu_busy"] = lambda: ""; HB["gpus"] = lambda: [dict(STUCK, util=20, eff=20.0, clk=1700, pwr=60, stuck=False)]; HB["busy_boot"] = lambda: "3 máy mới đang khởi động"
with contextlib.redirect_stdout(io.StringIO()): HB["heartbeat"]()
b2 = next((b for m, p, b in POST if m == "POST" and p == "cloud_nodes"), {})
ck("card khoẻ nhưng đang tạo 3 máy mới → lý do ['boot'], bán = đã cấp, sức chứa thật vẫn 100 / 112",
   b2.get("metrics", {}).get("stop") == ["boot"] and b2.get("cap_cpu") == 31.0 and b2["metrics"]["cap_cpu_full"] == 100.0, b2.get("metrics", {}).get("stop"))
POST.clear(); HB["busy_boot"] = lambda: ""
with contextlib.redirect_stdout(io.StringIO()): HB["heartbeat"]()
b3 = next((b for m, p, b in POST if m == "POST" and p == "cloud_nodes"), {})
ck("hết lý do → stop [] · bán tới sức chứa thật (100 nhân · 112 GB)", b3.get("metrics", {}).get("stop") == [] and b3.get("cap_cpu") == 100.0 and b3.get("cap_ram") == 112.0,
   (b3.get("metrics", {}).get("stop"), b3.get("cap_cpu"), b3.get("cap_ram")))
ck("dòng khởi động: 28/11h + in số CPU · luồng · RAM chính", 'print(f"cloudphoned bản 28/11h chạy' in CPD and 'CPU (28/11h): {ci[\'sockets\'] or \'?\'} CPU · {ci[\'threads\']} luồng' in CPD
   and 'CPD_VER = "28/11h"' in CPD)
ck("mọi chỗ tính sức chứa dùng cpu_threads() (không còn os.cpu_count() riêng 1 nhóm)", CPD.count("cpu_t = cpu_threads()") == 3 and "cpu_t = os.cpu_count()" not in CPD)

# ============================================================== 5
print("5. phonectl · giãn lượt bật máy đo CPU đủ mọi nhóm · sua-tat-ca 28/11h")
P = {"os": types.SimpleNamespace(name="nt"), "time": types.SimpleNamespace(sleep=lambda s: fw.run(0, s, 0) or fw.run(1, s, 100))}
pick(PCM, ("_cpu_groups", "_cpu_pct"), P, "phonectl.py")
with fake_ctypes(fw):
    P["ctypes"] = sys.modules["ctypes"]
    v = P["_cpu_pct"](2.0)
ck("CPU 1 rảnh · CPU 2 bận hết → 50% (đo cả 2 nhóm, không chỉ nhóm của lệnh)", v == 50.0, v)
fw.ex_ok = False
gst = types.SimpleNamespace(GetSystemTimes=lambda i, k, u: 1)
P["ctypes"] = types.SimpleNamespace(**{n: getattr(C, n) for n in ("Structure", "c_uint32", "byref", "c_ulong", "c_ushort", "c_long", "create_string_buffer")},
                                    windll=types.SimpleNamespace(kernel32=types.SimpleNamespace(GetSystemTimes=gst.GetSystemTimes, GetActiveProcessorGroupCount=lambda: 2),
                                                                 ntdll=fw.windll.ntdll))
v2 = P["_cpu_pct"](0.01)
ck("không đọc được từng nhóm → cách cũ (GetSystemTimes), lỗi → 0 (không chặn bật máy)", v2 == 0.0, v2)
fw.ex_ok = True
ck("phonectl PCTL_SUB 28/11h", 'PCTL_SUB = "28/11h"' in PCS)
ck("sua-tat-ca VER 28/11h + tải cloudphoned / phonectl 28/11h + chờ dòng khởi động 28/11h",
   re.search(r'^VER = "28/11h"$', SUA, re.M) and '("cloudphoned.py", "cloudphoned.py", "cloudphoned bản 28/11h", "cloudphoned")' in SUA
   and '("windows/phonectl.py", "phonectl.py", \'PCTL_SUB = "28/11h"\', None)' in SUA and 'MARK_RUN = {"cloudphoned": "cloudphoned bản 28/11h"' in SUA)

print(f"\n{OK[0]}/{OK[1]} đạt")
sys.exit(0 if OK[0] == OK[1] else 1)
