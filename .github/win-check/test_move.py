# -*- coding: utf-8 -*-
"""27/11n · 🚚 CHUYỂN MÁY KHÁCH SANG MÁY CHỦ KHÁC (giữ nguyên dữ liệu) — thử trọn đường bằng đồ giả (chạy được ở mọi máy, không cần Windows /
   giả lập / Supabase): 2–3 máy chủ GIẢ trong cùng 1 tiến trình, mỗi máy chủ có phonectl + cloudphoned THẬT (giả lập MuMu / LDPlayer giả,
   Supabase giả làm đúng các hàm SQL v65), máy chủ cũ chạy cpapi THẬT (cổng TLS ghim chứng chỉ giống cổng phát hình + cổng http thay Cloudflare).
   Thử: chuyển 3 máy (đang chạy · chờ gia hạn · root + proxy) đúng từng byte ổ dữ liệu; máy đang chuyển không bật lại được; đứt mạng giữa chừng
   tải tiếp; chứng chỉ không khớp → không tải từ máy lạ; máy chủ mới bật máy lỗi → máy cũ về như cũ; máy chủ mới chết giữa chừng → máy chủ cũ
   tự bật lại máy; admin dừng; admin chọn máy chủ đích; LDPlayer (sao lưu / khôi phục).
   Chạy: python3 .github/win-check/test_move.py"""
import argparse, contextlib, copy, datetime, hashlib, importlib.util, io, json, os, re, runpy, shutil, ssl, subprocess, sys, tempfile, threading, time
import urllib.parse, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OK = [0, 0]
REAL_OUT = sys.stdout


def ck(name, cond, extra=""):
    OK[1] += 1
    if cond: OK[0] += 1; print("  ✓", name, flush=True)
    else: print("  ✗", name, "→", str(extra)[:1500], flush=True)


# ---------------------------------------------------------------- stdout + argv riêng từng luồng (phonectl chạy trong tiến trình, nhiều luồng)
TL = threading.local()
class _TLOut:
    def write(self, s):
        b = getattr(TL, "buf", None)
        return (b or REAL_OUT).write(s)
    def flush(self):
        try: REAL_OUT.flush()
        except Exception: pass
    def reconfigure(self, **k): pass
sys.stdout = _TLOut()
_orig_parse = argparse.ArgumentParser.parse_args
def _parse(self, args=None, namespace=None):
    if args is None and getattr(TL, "argv", None) is not None: args = TL.argv
    return _orig_parse(self, args, namespace)
argparse.ArgumentParser.parse_args = _parse
LOG = []
def say(*a):
    LOG.append(" ".join(str(x) for x in a))


# ---------------------------------------------------------------- Supabase GIẢ (PostgREST + hàm SQL v65)
def now(): return datetime.datetime.now(datetime.timezone.utc)
def iso(t=None): return (t or now()).isoformat()
class DB:
    def __init__(self):
        self.t = {"cloud_phones": [], "cloud_nodes": [], "cp_moves": []}; self.lk = threading.RLock(); self.calls = []
    # ---- bộ lọc PostgREST tối thiểu ----
    @staticmethod
    def _val(v):
        v = urllib.parse.unquote(v)
        return v[1:-1] if len(v) >= 2 and v[0] == '"' and v[-1] == '"' else v
    def _cond(self, row, col, op):
        x = row.get(col)
        if op.startswith("eq."): return str(x) == self._val(op[3:]) if not isinstance(x, bool) else str(x).lower() == self._val(op[3:])
        if op.startswith("neq."): return str(x) != self._val(op[4:])
        if op == "is.null": return x is None
        if op == "not.is.null": return x is not None
        if op == "is.false": return x is False
        if op == "is.true": return x is True
        if op.startswith("in.("): return str(x) in [self._val(v) for v in op[4:-1].split(",")]
        if op.startswith("lt."): return x is not None and str(x) < self._val(op[3:])
        raise ValueError("bộ lọc chưa hỗ trợ: " + col + "=" + op)
    @staticmethod
    def _split(s):
        out, d, cur = [], 0, ""
        for ch in s:
            if ch == "(": d += 1
            elif ch == ")": d -= 1
            if ch == "," and d == 0: out.append(cur); cur = ""
            else: cur += ch
        if cur: out.append(cur)
        return out
    def _logic(self, row, kind, inner):
        parts = self._split(inner); res = []
        for p in parts:
            m = re.match(r"^(and|or)\((.*)\)$", p)
            if m: res.append(self._logic(row, m.group(1), m.group(2))); continue
            col, op = p.split(".", 1)
            res.append(self._cond(row, col, op))
        return all(res) if kind == "and" else any(res)
    def _match(self, row, qs):
        for k, v in qs:
            if k in ("select", "order", "limit"): continue
            if k in ("or", "and"):
                if not self._logic(row, k, urllib.parse.unquote(v)[1:-1]): return False
            elif not self._cond(row, k, v): return False
        return True
    def __call__(self, method, path, body=None, extra=None):
        with self.lk:
            self.calls.append((method, path))
            if path.startswith("rpc/"): return copy.deepcopy(getattr(self, "rpc_" + path[4:].split("?")[0])(**(body or {})))
            tb, _, q = path.partition("?")
            qs = [tuple(x.split("=", 1)) for x in q.split("&") if x]
            rows = self.t[tb]
            if method == "GET":
                out = [r for r in rows if self._match(r, qs)]
                if dict(qs).get("order", "").startswith("created_at"): out.sort(key=lambda r: r.get("created_at") or "")
                return copy.deepcopy(out)
            if method == "PATCH":
                hit = [r for r in rows if self._match(r, qs)]
                for r in hit: r.update(copy.deepcopy(body))
                return copy.deepcopy(hit) if "representation" in str((extra or {}).get("Prefer", "")) else None
            if method == "POST": rows.append(copy.deepcopy(body)); return None
            raise ValueError(method)
    def job(self, jid): return next(r for r in self.t["cp_moves"] if r["id"] == jid)
    def phone(self, pid): return next(r for r in self.t["cloud_phones"] if r["id"] == pid)
    # ---- hàm SQL v65 (làm y như file SQL) ----
    def admin_start(self, node, target=None, ids=None):
        with self.lk:
            nd = next(n for n in self.t["cloud_nodes"] if n["id"] == node); b = str(uuid.uuid4()); n = 0
            for m in sorted(self.t["cloud_phones"], key=lambda x: x["created_at"]):
                if m["node"] != node or m["status"] not in ("active", "expired") or (ids and m["id"] not in ids): continue
                if any(x["phone_id"] == m["id"] and x["status"] not in ("done", "failed", "cancelled") for x in self.t["cp_moves"]): continue
                self.t["cp_moves"].append({"id": str(uuid.uuid4()), "batch": b, "phone_id": m["id"], "src": node, "want": target, "dst": None,
                    "src_name": m.get("container") or "cp_" + m["id"].replace("-", "")[:10], "dst_name": None, "android": m.get("android") or "9",
                    "engine": nd.get("engine"), "ram": m["ram"], "cpu": m["cpu"], "status": "queued", "token": None, "files": None, "bytes_total": None,
                    "bytes_done": None, "size_hint": None, "prev_lock": None, "error": None, "note": None, "tries": 0,
                    "created_at": iso(), "updated_at": iso(), "step_at": iso(), "done_at": None,
                    "src_fin": False, "dst_fin": False, "rate_kbs": None})
                n += 1
            if n: nd.update(enabled=False, pause_hard=True)
            return b, n
    def admin_cancel(self, node):
        with self.lk:
            for j in self.t["cp_moves"]:
                if j["src"] == node and j["status"] in ("queued", "claimed", "ready"): j.update(status="cancelled", error="Admin dừng chuyển", step_at=iso())
    def rpc_cp_move_lock(self, p_id, p_node, p_reason, p_min=240):
        j = self.job(p_id)
        if j["src"] != p_node or j["status"] != "ready": return {"ok": False, "why": "STATUS", "status": j["status"]}
        m = self.phone(j["phone_id"])
        if m["node"] != j["src"] or m["status"] not in ("active", "expired") or (m.get("container") or "cp_" + m["id"].replace("-", "")[:10]) != j["src_name"]:
            j.update(status="failed", error="Máy khách đã đổi"); return {"ok": False, "why": "PHONE_CHANGED"}
        if str(m.get("lock_reason") or "").startswith("🚚"):          # còn khoá 🚚 của lượt trước → giữ khoá THẬT cũ (như SQL v65)
            old = [x for x in self.t["cp_moves"] if x["phone_id"] == j["phone_id"] and x["id"] != j["id"] and x.get("prev_lock") is not None]
            prev = j["prev_lock"] or (sorted(old, key=lambda x: x["created_at"])[-1]["prev_lock"] if old else None) or \
                {"locked": False, "locked_until": None, "lock_reason": None}
        else: prev = {"locked": m["locked"], "locked_until": m.get("locked_until"), "lock_reason": m.get("lock_reason")}
        j.update(status="stopping", tries=j["tries"] + 1, step_at=iso(), prev_lock=prev)
        m.update(locked=True, locked_until=iso(now() + datetime.timedelta(minutes=p_min)), lock_reason=p_reason[:300])
        return {"ok": True, "status": m["status"], "expires_at": m["expires_at"]}
    def rpc_cp_move_fail(self, p_id, p_node, p_err):
        j = self.job(p_id)
        if p_node not in (j["src"], j["dst"]): return {"ok": False, "why": "NOT_MINE", "status": j["status"]}
        if j["status"] in ("done", "failed", "cancelled"): return {"ok": False, "status": j["status"]}
        j.update(status="failed", error=p_err[:500], step_at=iso()); return {"ok": True, "status": "failed"}
    def rpc_cp_move_unlock(self, p_id, p_node):
        j = self.job(p_id)
        if j["src"] != p_node: return {"ok": False, "why": "NOT_SRC"}
        if j["status"] not in ("failed", "cancelled"): return {"ok": False, "why": "STATUS", "status": j["status"]}
        if j["prev_lock"] is not None:
            m = self.phone(j["phone_id"])
            if m["node"] == j["src"] and str(m.get("lock_reason") or "").startswith("🚚"):
                m.update(locked=bool(j["prev_lock"].get("locked")), locked_until=j["prev_lock"].get("locked_until"), lock_reason=j["prev_lock"].get("lock_reason"))
        j.update(prev_lock=None, src_fin=True, token=None); return {"ok": True}
    def rpc_cp_move_commit(self, p_id, p_node, p_name, p_port, p_stream_url):
        j = self.job(p_id)
        if j["dst"] != p_node or j["status"] != "booting": return {"ok": False, "why": "STATUS", "status": j["status"]}
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", p_name or "") or not p_port: return {"ok": False, "why": "BAD_ARGS"}
        m = self.phone(j["phone_id"])
        if m["node"] != j["src"] or m["status"] not in ("active", "expired"):
            j.update(status="failed", error="Máy khách đã đổi trong lúc chuyển"); return {"ok": False, "why": "PHONE_CHANGED"}
        if any(x is not m and x["node"] == p_node and x["port"] == p_port and x["status"] in ("pending", "creating", "active", "expired", "cancelling")
               for x in self.t["cloud_phones"]):
            j.update(status="failed", error="TAKEN"); return {"ok": False, "why": "TAKEN"}
        ours = str(m.get("lock_reason") or "").startswith("🚚"); pl = j["prev_lock"] or {}
        m.update(node=p_node, container=p_name, port=p_port, stream_url=p_stream_url)
        if ours: m.update(locked=bool(pl.get("locked")), locked_until=pl.get("locked_until"), lock_reason=pl.get("lock_reason"))
        j.update(status="done", done_at=iso(), step_at=iso(), token=None, prev_lock=None, bytes_done=j.get("bytes_total"))
        return {"ok": True, "status": m["status"], "expires_at": m["expires_at"]}


DBX = DB()


# ---------------------------------------------------------------- 1 máy chủ GIẢ: phonectl + cloudphoned THẬT, giả lập giả
TPL_DATA = b"TEMPLATE-DATA-" * 64
class Server:
    def __init__(self, node, emu="mumu", androids="12,15"):
        self.node, self.emu = node, emu
        self.home = tempfile.mkdtemp(prefix=f"mv_{node}_"); os.makedirs(os.path.join(self.home, "redroid"))
        open(os.path.join(self.home, "cloudphone.conf"), "w").write(
            f"SUPABASE_URL=http://127.0.0.1:9\nSUPABASE_SERVICE_KEY=x\nPUBLIC_BASE=https://phone-{node}.test\nNODE_ID={node}\nEMU={emu}\nANDROIDS={androids}\n")
        os.environ["HOME"] = self.home; os.environ["BLUE_HOME"] = self.home
        self.G = runpy.run_path(os.path.join(ROOT, "windows", "phonectl.py"), run_name=f"pc_{node}")["main"].__globals__   # dict THẬT của module (run_path trả bản sao)
        spec = importlib.util.spec_from_file_location(f"cpd_{node}", os.path.join(ROOT, "cloudphoned.py"))
        self.D = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.D)
        self.vmroot = os.path.join(self.home, "emu"); os.makedirs(os.path.join(self.vmroot, "vms"))
        self.EM = {}; self.started = []; self.boot_ok = True; self.lk = threading.RLock(); self.tpl = TPL_DATA
        self._fake_pc(); self._fake_cpd()
        self.add_vm("MuMu Android Device" if emu == "mumu" else "LDPlayer", 0)
        self.add_vm("tpl_a12", 1)
    # ---- giả lập ----
    def vmdir(self, i):
        return os.path.join(self.vmroot, "vms", (f"MuMuPlayerGlobal-12.0-{i}" if self.emu == "mumu" else f"leidian{i}"))
    def add_vm(self, name, i=None, data=None, running=False):
        with self.lk:
            i = max(self.EM) + 1 if i is None else i
            os.makedirs(self.vmdir(i), exist_ok=True)
            fn = "data.vdi" if self.emu == "mumu" else "data.vmdk"
            open(os.path.join(self.vmdir(i), fn), "wb").write(self.tpl if data is None else data)
            self.EM[i] = {"name": name, "running": running}
            return i
    def data_of(self, i): return open(os.path.join(self.vmdir(i), "data.vdi" if self.emu == "mumu" else "data.vmdk"), "rb").read()
    def idx_of(self, name): return next((i for i, x in self.EM.items() if x["name"] == name), None)
    def _fake_pc(self):
        G, S = self.G, self
        CP = subprocess.CompletedProcess
        G["MEMU"] = S.vmroot; G["MUMU"] = S.vmroot if S.emu == "mumu" else ""; G["LD"] = S.vmroot if S.emu == "ld" else ""
        G["NOWIN"] = 0
        def vms():
            with S.lk: return {i: {"name": x["name"], "running": x["running"]} for i, x in S.EM.items()}
        G["vms"] = vms; G["vms_sure"] = lambda tries=3: vms()
        G["_mumu_info"] = lambda fresh=True: {i: {"name": x["name"], "adb_port": 16384 + 32 * i, "is_process_started": x["running"]} for i, x in vms().items()}
        G["mem"] = lambda: (64.0, 48.0)
        G["_priv_block"] = lambda: ""; G["_priv_main_fix"] = lambda: None
        G["adb"] = lambda *a, timeout=60: CP([], 0, "", "")
        G["configure"] = lambda *a, **k: None; G["apply_template"] = lambda *a, **k: None
        G["hide_window"] = lambda *a, **k: 0
        def start(iv, timeout=0, locked=False):
            with S.lk:
                if int(iv) not in S.EM: return CP([], 1, "", "no vm")
                S.EM[int(iv)]["running"] = True; S.started.append(S.EM[int(iv)]["name"]); return CP([], 0, "start ok", "")
        def stop(iv, timeout=0, locked=False):
            with S.lk:
                if int(iv) in S.EM: S.EM[int(iv)]["running"] = False
            return CP([], 0, "stop ok", "")
        G["_mumu_start"] = start; G["_mumu_stop"] = stop
        G["_mumu_locked"] = lambda fn, wait=0, long_op=False: fn()
        def fake_cmd(a, timeout=0):
            a = [str(x) for x in a]; c = a[0]
            ix = lambda: int(a[a.index("-i") + 1])
            if c == "listvms": return CP([], 0, "\n".join(f"{i},{x['name']},0,{1 if x['running'] else 0},1" for i, x in sorted(vms().items())), "")
            if c == "create":
                i = S.add_vm("MuMu Android Device-new" if S.emu == "mumu" else "new_x"); return CP([], 0, f"index: {i}", "")
            if c == "rename":
                with S.lk: S.EM[ix()]["name"] = a[-1]
                return CP([], 0, "ok", "")
            if c == "remove":
                with S.lk:
                    i = ix(); S.EM.pop(i, None); shutil.rmtree(S.vmdir(i), ignore_errors=True)
                return CP([], 0, "remove ok", "")
            if c == "start": return start(ix())
            if c == "stop": return stop(ix())
            return CP([], 0, "ok", "")
        G["_mumu"] = fake_cmd
        G["_ld"] = fake_cmd
        def ldrun(args, timeout=0):                                  # ldconsole giả: backup / restore = chép ổ dữ liệu của máy
            args = [str(x) for x in args]
            if args[0] == "backup":
                i = int(args[args.index("--index") + 1]); f = args[args.index("--file") + 1]
                nm = S.EM[i]["name"].encode(); open(f, "wb").write(b"LDBK" + bytes([len(nm)]) + nm + S.data_of(i)); return CP([], 0, "backup ok", "")
            if args[0] == "restore":
                i = int(args[args.index("--index") + 1]); f = args[args.index("--file") + 1]
                d = open(f, "rb").read()
                if not d.startswith(b"LDBK"): return CP([], 1, "", "restore failed")
                n = d[4]; open(os.path.join(S.vmdir(i), "data.vmdk"), "wb").write(d[5 + n:])
                with S.lk: S.EM[i]["name"] = d[5:5 + n].decode()                     # LDPlayer khôi phục cả tên máy cũ
                return CP([], 0, "restore ok", "")
            return CP([], 0, "", "")
        G["_ldrun"] = ldrun
        G["ld_cfg"] = lambda *a, **k: None
        G["_guest_sync"] = lambda i: None
        def wait_boot(name, port, apps=True):
            G["_boot_done"](name); return S.boot_ok
        G["wait_boot"] = wait_boot
    def pc(self, args, timeout=None):
        """cloudphoned gọi phonectl → chạy main() của phonectl GIẢ trong tiến trình (stdout / argv riêng của luồng)."""
        buf = io.StringIO(); TL.buf, TL.argv = buf, [str(x) for x in args]; code = 0
        os.environ["HOME"] = self.home
        try:
            try: self.G["main"]()
            except SystemExit as e: code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception as e: buf.write(f"\nLỖI {e!r}\n"); code = 99
        finally:
            TL.buf = None; TL.argv = None
        return subprocess.CompletedProcess(["phonectl"] + list(args), code, buf.getvalue(), "")
    def _fake_cpd(self):
        D, S = self.D, self
        D.sb = DBX; D.phonectl = S.pc; D.MV_ON = True; D._mv["sup"] = True
        D.engine = lambda refresh=False: {"emu": S.emu, "androids": (["9"] if S.emu == "ld" else ["12", "15"]), "none": False, "missing": []}
        D.node_enabled = lambda: True
        D.local_load = lambda: (0.1, 64.0, 64.0)
        D.disk_full = lambda: False
        D.notify = lambda t: say(f"[TG {S.node}]", t)
        D.print = lambda *a, **k: say(f"[{S.node}]", *a)
        D.MV_STALL_S = 600.0; D.MV_HTTP_OK = True; D.MV_IO_T = 10
    def phones(self):
        try: return {p["name"]: p for p in json.load(open(os.path.join(self.home, "redroid", "phones.json"), encoding="utf-8"))["phones"]}
        except Exception: return {}
    def put_phone(self, name, idx, **kw):
        st = {"phones": list(self.phones().values())}
        st["phones"].append(dict({"name": name, "idx": idx, "port": 16384 + 32 * idx, "ram": 4, "cpu": 4, "res": "720x1280", "fps": 30, "dpi": 320,
                                  "android": "12", "kind": self.emu, "created": "01/11/2026 10:00", "expires": iso(now() + datetime.timedelta(days=3))}, **kw))
        json.dump(st, open(os.path.join(self.home, "redroid", "phones.json"), "w", encoding="utf-8"))


def node_row(s, cert=None, lan="127.0.0.1", tls_port=None, http_port=None):
    st = {"direct": ([{"host": lan, "port": tls_port, "lan": True}] if tls_port else []), "cert": cert, "api": f"http://127.0.0.1:{http_port}" if http_port else None}
    return {"id": s.node, "updated_at": iso(), "enabled": True, "pause_hard": False, "engine": s.emu, "androids": "9" if s.emu == "ld" else "12,15",
            "stream": st, "metrics": {"move": 1}}


def run_until(servers, cond, limit=60, step=0.05):
    t0 = time.time()
    while time.time() - t0 < limit:
        for s in servers:
            for n in DBX.t["cloud_nodes"]:
                if n["id"] == s.node: n["updated_at"] = iso()
            os.environ["HOME"] = s.home
            try: s.D.mv_tick()
            except Exception as e: say(f"[{s.node}] tick lỗi", repr(e))
        if cond(): return True
        time.sleep(step)
    return False


def idle(servers, sec=2.0):
    t0 = time.time()
    while time.time() - t0 < sec:
        if not any(t.is_alive() for s in servers for t in list(s.D._mv["th"].values())): return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- dựng 2 máy chủ MuMu + cpapi của máy chủ cũ
A = Server("win3"); B = Server("win5")
os.environ["HOME"] = A.home
cps = importlib.util.spec_from_file_location("cpapi_mv", os.path.join(ROOT, "cpapi.py"))
CP = importlib.util.module_from_spec(cps); cps.loader.exec_module(CP)
CP.log = lambda *a: say("[cpapi win3]", *a)
srv_http = CP.Server(("127.0.0.1", 0), CP.H); threading.Thread(target=srv_http.serve_forever, daemon=True).start()
# cổng TLS (giống cổng phát hình của bluestream: TLS → cpapi) với chứng chỉ tự ký
tdir = tempfile.mkdtemp(prefix="mv_tls_")
subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "2", "-subj", "/CN=bluestream win3",
                "-keyout", os.path.join(tdir, "k.pem"), "-out", os.path.join(tdir, "c.pem")], check=True, capture_output=True)
der = ssl.PEM_cert_to_DER_cert(open(os.path.join(tdir, "c.pem")).read()); PIN = hashlib.sha256(der).hexdigest()
srv_tls = CP.Server(("127.0.0.1", 0), CP.H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(os.path.join(tdir, "c.pem"), os.path.join(tdir, "k.pem"))
srv_tls.socket = ctx.wrap_socket(srv_tls.socket, server_side=True)
srv_tls.handle_error = lambda req, addr: None        # máy nhận đóng kết nối khi chứng chỉ không khớp → khỏi in traceback (thật: bluestream lo TLS)
threading.Thread(target=srv_tls.serve_forever, daemon=True).start()
TLS_PORT, HTTP_PORT = srv_tls.server_address[1], srv_http.server_address[1]
DBX.t["cloud_nodes"] += [node_row(A, PIN, "127.0.0.1", TLS_PORT, HTTP_PORT), node_row(B, "0" * 64, "127.0.0.2", 1, None)]

# máy khách ở win3: X đang chạy (4 MB dữ liệu ngẫu nhiên), Y chờ gia hạn (tắt), Z đang chạy + root theo app + proxy riêng + bộ nhớ đã mua
RND = lambda n: os.urandom(n)
PH = {}
def mk_phone(key, status, running, data, rec_extra=None, lock=None):
    pid = str(uuid.uuid4()); name = "cp_" + pid.replace("-", "")[:10]
    i = A.add_vm(name, data=data, running=running)
    A.put_phone(name, i, **(rec_extra or {}))
    row = {"id": pid, "name": f"Máy {key}", "status": status, "node": "win3", "container": name, "port": 16384 + 32 * i, "ram": 4, "cpu": 4,
           "res": "720x1280", "fps": 30, "android": "12", "expires_at": iso(now() + (datetime.timedelta(days=3) if status == "active" else -datetime.timedelta(minutes=5))),
           "locked": bool(lock), "locked_until": None, "lock_reason": lock, "stream_url": "x", "created_at": iso(now() - datetime.timedelta(days=1))}
    DBX.t["cloud_phones"].append(row); PH[key] = (pid, name, data)
    return pid
mk_phone("X", "active", True, RND(4 * 2**20 + 123))
mk_phone("Y", "expired", False, RND(1 * 2**20 + 7))
mk_phone("Z", "active", True, RND(2 * 2**20 + 1), {"root_on": True, "root_apps": ["com.roblox.client"], "proxy": {"kind": "socks5", "host": "px.test", "port": 1080, "user": "u", "pass": "p"},
                                                     "disk_gb": 24, "disk_buy": 8})

# =================================================================== 1. chuyển hết 3 máy win3 → win5
print("1. Chuyển hết máy khách win3 → win5 (tự chia) — đúng từng byte, root / proxy / bộ nhớ đi theo, máy cũ xoá sau khi máy mới chạy")
# đứt mạng 1 lần giữa lúc tải data.vdi của X → phải tải tiếp từ chỗ đứt (không tải lại từ đầu)
_orig_open = B.D.mv_open; CUT = {"n": 0, "offs": []}
def cut_open(path, jid, fn, off, tok, z):
    c, resp = _orig_open(path, jid, fn, off, tok, z)
    if fn == "data.vdi": CUT["offs"].append((path[0], off))
    if fn == "data.vdi" and CUT["n"] == 0 and DBX.job(jid)["src_name"] == PH["X"][1]:
        CUT["n"] = 1; real = resp.read; sent = {"n": 0}
        def rd(n=-1):
            if sent["n"] >= 1500000: raise ConnectionResetError("giả lập đứt mạng")
            b = real(min(n if n and n > 0 else 1 << 20, 1500000 - sent["n"])); sent["n"] += len(b); return b
        resp.read = rd
    return c, resp
B.D.mv_open = cut_open
batch, n = DBX.admin_start("win3")
ck("tạo 3 việc, máy chủ cũ sang Ngừng hẳn", n == 3 and DBX.t["cloud_nodes"][0]["enabled"] is False, n)
# trong lúc chuyển: máy đang chuyển đi KHÔNG bật lại được ở máy chủ cũ
seen_block = {"v": None}
def watch():
    t0 = time.time()
    while time.time() - t0 < 60 and seen_block["v"] is None:
        for m in [x for x in os.listdir(os.path.join(A.home, "redroid")) if x == "move"]:
            for f in os.listdir(os.path.join(A.home, "redroid", "move")):
                if f.startswith("out_") and f.endswith(".json"):
                    try: d = json.load(open(os.path.join(A.home, "redroid", "move", f)))
                    except Exception: continue
                    os.environ["HOME"] = A.home
                    r = A.G["memuc"]("start", "-i", d["idx"], timeout=10)
                    seen_block["v"] = (r.returncode, r.stderr); return
        time.sleep(0.02)
th = threading.Thread(target=watch, daemon=True); th.start()
done = run_until([A, B], lambda: all(j["status"] == "done" and j["src_fin"] and j["dst_fin"] for j in DBX.t["cp_moves"] if j["batch"] == batch), 90)
idle([A, B])
ck("cả 3 việc xong (done, máy chủ cũ + mới đều chốt)", done, [(j["status"], j["error"], j["src_fin"], j["dst_fin"]) for j in DBX.t["cp_moves"]] + LOG[-30:])
th.join(1)
ck("máy đang chuyển đi: lệnh bật máy ở máy chủ cũ bị chặn (MOVING)", seen_block["v"] and seen_block["v"][0] == 1 and "MOVING" in seen_block["v"][1], seen_block["v"])
for key in ("X", "Y", "Z"):
    pid, old, data = PH[key]; ph = DBX.phone(pid)
    i = B.idx_of(ph["container"])
    ck(f"máy {key}: web ghi máy chủ win5, tên máy mới, cổng + link mới, mở khoá", ph["node"] == "win5" and ph["container"].startswith(old + "m") and i is not None
       and ph["port"] == 16384 + 32 * i and ph["stream_url"].startswith("https://phone-win5.test") and not ph["locked"] and ph["lock_reason"] is None, ph)
    ck(f"máy {key}: ổ dữ liệu ở win5 GIỐNG HỆT bản cũ (từng byte)", i is not None and B.data_of(i) == data, len(B.data_of(i)) if i is not None else None)
    ck(f"máy {key}: bản cũ ở win3 đã xoá (giả lập + danh sách máy)", A.idx_of(old) is None and old not in A.phones(), A.EM)
ck("máy đang chạy (X, Z) đã bật ở win5 · máy chờ gia hạn (Y) để tắt", B.EM[B.idx_of(DBX.phone(PH["X"][0])["container"])]["running"]
   and B.EM[B.idx_of(DBX.phone(PH["Z"][0])["container"])]["running"] and not B.EM[B.idx_of(DBX.phone(PH["Y"][0])["container"])]["running"], B.EM)
bz = B.phones()[DBX.phone(PH["Z"][0])["container"]]
ck("máy Z: root theo app + proxy riêng + bộ nhớ đã mua đi theo sang win5", bz.get("root_on") is True and bz.get("root_apps") == ["com.roblox.client"]
   and (bz.get("proxy") or {}).get("host") == "px.test" and bz.get("disk_gb") == 24 and bz.get("disk_buy") == 8, bz)
ck("máy mới ở win5 không còn dấu 'đang nhận' (move_in), hạn theo web", all("move_in" not in p for p in B.phones().values())
   and bz.get("expires", "")[:16] == DBX.phone(PH["Z"][0])["expires_at"][:16], [(n_, p.get("move_in"), p.get("expires")) for n_, p in B.phones().items()])
ck("máy chủ cũ không còn file / dấu đang chuyển nào", not [f for f in os.listdir(os.path.join(A.home, "redroid", "move")) if f != "in.json"],
   os.listdir(os.path.join(A.home, "redroid", "move")))
ck("máy chủ mới không còn file tải dở", not [f for f in os.listdir(os.path.join(B.home, "redroid", "move")) if f.startswith("in_")]
   and not any(f.endswith(".cbmove") for d, _, fs in os.walk(B.vmroot) for f in fs) and B.D.mv_reg() == {}, os.listdir(os.path.join(B.home, "redroid", "move")))
ck("tải THẲNG qua cổng TLS (ghim đúng chứng chỉ máy chủ cũ, cùng mạng LAN)", any(k == "lan" for k, o in CUT["offs"]), CUT["offs"])
xo = [o for k, o in CUT["offs"]]
ck("đứt mạng giữa chừng → tải TIẾP từ chỗ đứt (không tải lại từ đầu)", CUT["n"] == 1 and any(o >= 1400000 for o in xo), CUT["offs"])
tg = [x for x in LOG if "[TG win3]" in x]
ck("nhắn admin 1 tin tóm tắt: chuyển xong 3/3 máy sang win5", any("chuyển xong 3/3" in x and "win5: 3" in x for x in tg), tg)
jx = [j for j in DBX.t["cp_moves"] if j["batch"] == batch]
ck("việc xong: xoá mã tải, ghi đủ byte đã chép, tries = 1", all(j["token"] is None and j["bytes_done"] == j["bytes_total"] and j["tries"] == 1 for j in jx), jx[0])
B.D.mv_open = _orig_open

# =================================================================== 2. máy chủ mới bật máy lỗi → máy cũ về như cũ
print("2. Máy chủ mới bật máy lỗi (Android không lên) → máy cũ tự bật lại ở máy chủ cũ, mở khoá, máy nhận dở bị xoá")
LOG.clear()
pid = mk_phone("W", "active", True, RND(512 * 1024 + 3))
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
B.boot_ok = False
batch, n = DBX.admin_start("win3")
ok = run_until([A, B], lambda: (lambda j: j["status"] == "failed" and j["src_fin"] and j["dst_fin"])(next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)), 90)
idle([A, B])
j = next(j for j in DBX.t["cp_moves"] if j["batch"] == batch); ph = DBX.phone(pid); old = PH["W"][1]
ck("việc failed, có lý do từ máy chủ mới", ok and "win5" in (j["error"] or "") and "Android" in (j["error"] or ""), [j["status"], j["error"]] + LOG[-20:])
ck("máy W vẫn ở win3, mở khoá, máy ảo đang CHẠY lại (bật lại sau khi tắt để chuyển)", ph["node"] == "win3" and not ph["locked"] and A.EM[A.idx_of(old)]["running"]
   and A.started.count(old) >= 1, [ph, A.EM.get(A.idx_of(old))])
ck("máy chủ cũ bỏ dấu đang chuyển (máy bật lại được như thường)", not A.D.mv_busy(old) and A.G["_mv_moving_idx"](A.idx_of(old)) is None)
ck("máy nhận dở ở win5 đã xoá, không còn trong danh sách", not any(nm.startswith(old) for nm in B.phones()) and not any(x["name"].startswith(old + "m") for x in B.EM.values()), B.phones().keys())
ck("dữ liệu máy W ở win3 không đổi", A.data_of(A.idx_of(old)) == PH["W"][2])
ck("nhắn admin: chuyển chưa được, máy đã về như cũ", any("chưa được" in x and "về như cũ" in x for x in LOG if "[TG win3]" in x), [x for x in LOG if "[TG" in x])
B.boot_ok = True

# =================================================================== 3. chứng chỉ không khớp → không tải từ máy lạ, đi đường dự phòng
print("3. Cổng thẳng trả chứng chỉ KHÁC (không phải máy chủ cũ) → không tải từ đó, đi đường dự phòng (Cloudflare) vẫn xong")
LOG.clear()
DBX.t["cloud_nodes"][0]["stream"]["cert"] = "f" * 64
seen = []
def spy_open(path, jid, fn, off, tok, z):
    try: r = _orig_open(path, jid, fn, off, tok, z); seen.append((path[0], "ok")); return r
    except Exception as e: seen.append((path[0], type(e).__name__)); raise
B.D.mv_open = spy_open
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
batch, n = DBX.admin_start("win3", ids=[pid])
ok = run_until([A, B], lambda: next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["status"] == "done" and next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["src_fin"], 90)
idle([A, B])
ck("chuyển xong qua đường dự phòng", ok and DBX.phone(pid)["node"] == "win5" and B.data_of(B.idx_of(DBX.phone(pid)["container"])) == PH["W"][2], LOG[-15:])
ck("đường thẳng bị từ chối vì chứng chỉ không khớp (MvPinErr), tải qua cf", ("lan", "MvPinErr") in seen and ("cf", "ok") in seen, seen)
DBX.t["cloud_nodes"][0]["stream"]["cert"] = PIN; B.D.mv_open = _orig_open

# =================================================================== 4. máy chủ mới chết giữa lúc chép → máy chủ cũ tự bật lại máy
print("4. Máy chủ mới chết giữa lúc chép (không báo tiến độ) → máy chủ cũ tự bật lại máy, mở khoá; máy chủ mới sống lại thì dọn máy nhận dở")
LOG.clear()
pid = mk_phone("V", "active", True, RND(3 * 2**20 + 5)); old = PH["V"][1]
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
batch, n = DBX.admin_start("win3")
jid = next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["id"]
ok = run_until([A, B], lambda: DBX.job(jid)["status"] == "serving", 60)
ck("tới bước máy chủ cũ mở file (serving), máy cũ đã tắt + khoá", ok and not A.EM[A.idx_of(old)]["running"] and DBX.phone(pid)["locked"], DBX.job(jid)["status"])
DBX.job(jid)["step_at"] = iso(now() - datetime.timedelta(seconds=700))       # máy chủ mới im ~12 phút
ok = run_until([A], lambda: DBX.job(jid)["status"] == "failed" and DBX.job(jid)["src_fin"], 30)
idle([A])
ck("máy chủ cũ báo lỗi 'không báo tiến độ', bật lại máy, mở khoá", ok and "không báo tiến độ" in (DBX.job(jid)["error"] or "") and A.EM[A.idx_of(old)]["running"]
   and not DBX.phone(pid)["locked"] and DBX.phone(pid)["node"] == "win3", [DBX.job(jid), LOG[-10:]])
ok = run_until([B], lambda: DBX.job(jid)["dst_fin"], 30); idle([B])
ck("máy chủ mới sống lại → thấy việc đã lỗi → xoá máy trống đã tạo", ok and not any(x["name"].startswith(old + "m") for x in B.EM.values()), B.EM)

# =================================================================== 5. admin dừng · admin chọn máy chủ đích
print("5. Admin dừng trước khi bắt đầu · admin chọn máy chủ đích khác (máy chủ không phải đích không nhận)")
LOG.clear()
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
batch, n = DBX.admin_start("win3", target="win9")
run_until([A, B], lambda: False, 1.5); idle([A, B])
ck("admin chọn win9 → win5 không nhận việc (vẫn chờ)", all(j["status"] == "queued" and not j["dst"] for j in DBX.t["cp_moves"] if j["batch"] == batch), [j["status"] for j in DBX.t["cp_moves"] if j["batch"] == batch])
DBX.admin_cancel("win3")
ok = run_until([A, B], lambda: all(j["src_fin"] for j in DBX.t["cp_moves"] if j["batch"] == batch), 20); idle([A, B])
ck("admin dừng → việc cancelled, máy chủ cũ chốt, máy vẫn chạy ở win3", ok and all(j["status"] == "cancelled" for j in DBX.t["cp_moves"] if j["batch"] == batch)
   and A.EM[A.idx_of(old)]["running"] and DBX.phone(pid)["node"] == "win3")
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
batch, n = DBX.admin_start("win3")
ok = run_until([A, B], lambda: any(j["status"] == "ready" for j in DBX.t["cp_moves"] if j["batch"] == batch) or
               any(j["status"] in ("stopping", "serving") for j in DBX.t["cp_moves"] if j["batch"] == batch), 30)
# dừng khi máy chủ mới đã tạo máy trống (ready) nhưng máy cũ chưa tắt
j = next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)
if j["status"] == "ready":
    DBX.admin_cancel("win3")
    ok2 = run_until([A, B], lambda: j["src_fin"] and j["dst_fin"], 30); idle([A, B])
    ck("dừng lúc máy chủ mới đã tạo máy trống → máy trống bị xoá, máy cũ không bị đụng", ok2 and not any(x["name"].startswith(old + "m") for x in B.EM.values())
       and A.EM[A.idx_of(old)]["running"] and not DBX.phone(pid)["locked"], [j, B.EM])
else:
    ok2 = run_until([A, B], lambda: j["status"] in ("done", "failed") and j["src_fin"] and j["dst_fin"], 60); idle([A, B])
    ck("(máy chủ chạy nhanh hơn lệnh dừng) việc vẫn kết thúc gọn", ok2, j)

# =================================================================== 6. LDPlayer (Android 9): sao lưu / khôi phục chính thức
print("6. Máy chủ LDPlayer (Android 9): sao lưu ở máy chủ cũ → khôi phục ở máy chủ mới")
LOG.clear()
C = Server("win1", emu="ld", androids="9"); E = Server("win8", emu="ld", androids="9")
os.environ["HOME"] = C.home
cps2 = importlib.util.spec_from_file_location("cpapi_mv2", os.path.join(ROOT, "cpapi.py"))
CP2 = importlib.util.module_from_spec(cps2); cps2.loader.exec_module(CP2); CP2.log = lambda *a: None
s2 = CP2.Server(("127.0.0.1", 0), CP2.H); threading.Thread(target=s2.serve_forever, daemon=True).start()
DBX.t["cloud_nodes"] += [node_row(C, None, None, None, s2.server_address[1]), node_row(E, None, None, None, None)]
data = RND(2 * 2**20 + 11); pid9 = str(uuid.uuid4()); name9 = "cp_" + pid9.replace("-", "")[:10]
i9 = C.add_vm(name9, data=data, running=True); C.put_phone(name9, i9, android="9", port=5555 + 2 * i9)
DBX.t["cloud_phones"].append({"id": pid9, "name": "Máy LD", "status": "active", "node": "win1", "container": name9, "port": 5555 + 2 * i9, "ram": 4, "cpu": 4,
                              "res": "720x1280", "fps": 30, "android": "9", "expires_at": iso(now() + datetime.timedelta(days=2)), "locked": False,
                              "locked_until": None, "lock_reason": None, "stream_url": "x", "created_at": iso()})
batch, n = DBX.admin_start("win1")
ok = run_until([C, E, B], lambda: next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["status"] == "done"
               and next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["src_fin"], 90)
idle([C, E, B])
ph = DBX.phone(pid9); i = E.idx_of(ph["container"]) if ph["node"] == "win8" else None
ck("máy Android 9 chỉ chuyển sang máy chủ LDPlayer (win8), không sang MuMu (win5)", ok and ph["node"] == "win8", [ph["node"], LOG[-15:]])
ck("khôi phục đúng dữ liệu ở win8, máy chạy, bản cũ ở win1 đã xoá", i is not None and E.data_of(i) == data and E.EM[i]["running"] and C.idx_of(name9) is None,
   [i, C.EM, E.EM])
ck("không còn file sao lưu tạm ở máy chủ cũ", not [f for f in os.listdir(os.path.join(C.home, "redroid", "move")) if f.endswith(".ldbk")])

# =================================================================== 7. cpapi /cpapi/move: chỉ đúng mã mới tải được
print("7. cpapi /cpapi/move — chỉ đúng mã việc + mã tải mới đọc được, chỉ file có tên trong dấu")
import urllib.request, urllib.error
os.makedirs(os.path.join(A.home, "redroid", "move"), exist_ok=True)
fake = os.path.join(A.home, "redroid", "move", "secret.bin"); open(fake, "wb").write(b"S" * 1000)
J = str(uuid.uuid4()); TOK = "ab" * 32
json.dump({"job": J, "token": TOK, "name": "cp_t", "idx": 99, "stage": "serving", "files": [{"n": "rec.json", "path": fake, "size": 1000, "sha256": "x"}]},
          open(os.path.join(A.home, "redroid", "move", "out_cp_t.json"), "w"))
def get(path, tok=None):
    req = urllib.request.Request(f"http://127.0.0.1:{HTTP_PORT}{path}", headers=({"X-CB-Move": tok} if tok else {}))
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
ck("đúng mã → 200, đủ byte", get(f"/cpapi/move/{J}/rec.json", TOK) == (200, b"S" * 1000))
ck("đúng mã, tải tiếp từ vị trí 600 → 400 byte cuối", get(f"/cpapi/move/{J}/rec.json?off=600", TOK) == (200, b"S" * 400))
ck("sai mã tải → 404 (như không có)", get(f"/cpapi/move/{J}/rec.json", "cd" * 32)[0] == 404)
ck("không có mã tải → 404", get(f"/cpapi/move/{J}/rec.json")[0] == 404)
ck("tên file không có trong danh sách (data.vdi) → 404", get(f"/cpapi/move/{J}/data.vdi", TOK)[0] == 404)
ck("tên file lạ (../) → 404", get(f"/cpapi/move/{J}/..%2Fcloudphone.conf", TOK)[0] == 404)
ck("vị trí vượt cỡ file → 416", get(f"/cpapi/move/{J}/rec.json?off=5000", TOK)[0] == 416)
d = json.load(open(os.path.join(A.home, "redroid", "move", "out_cp_t.json"))); d["stage"] = "stopping"
json.dump(d, open(os.path.join(A.home, "redroid", "move", "out_cp_t.json"), "w"))
ck("máy chưa tắt xong (stopping) → 404", get(f"/cpapi/move/{J}/rec.json", TOK)[0] == 404)
d["stage"] = "serving"; json.dump(d, open(os.path.join(A.home, "redroid", "move", "out_cp_t.json"), "w"))
open(fake, "ab").write(b"!")
ck("file bị đổi sau khi mở (cỡ khác) → 409", get(f"/cpapi/move/{J}/rec.json", TOK)[0] == 409)
st_, body = get(f"/cpapi/move/{J}/rec.json?z=1", TOK) if False else (None, None)

# =================================================================== 8. phonectl: máy nhận dở chỉ xoá đúng máy của lượt đó
print("8. phonectl — moveabort chỉ xoá máy mang đúng dấu của lượt chuyển; máy khách thật không bao giờ bị xoá")
os.environ["HOME"] = B.home
anyc = next(nm for nm in B.phones())
r = B.pc(["moveabort", anyc, "--job", str(uuid.uuid4())])
ck("máy khách thật (không có dấu move_in) → KHÔNG xoá (mã 6)", r.returncode == 6 and B.idx_of(anyc) is not None, r.stdout[-300:])
r = B.pc(["moveset", anyc, "--file", "/tmp/x", "--job", str(uuid.uuid4())])
ck("moveset vào máy khách thật → từ chối (mã 6)", r.returncode == 6, r.stdout[-200:])
os.environ["HOME"] = A.home
r = A.pc(["moveout", "cp_khongco", "--job", str(uuid.uuid4()), "--token", "ab" * 32])
ck("moveout máy không có → MOVEOUT_FAIL mã 3", r.returncode == 3 and "MOVEOUT_FAIL" in r.stdout, r.stdout[-200:])
r = A.pc(["moveout", "cp_x", "--job", "khong-phai-uuid", "--token", "ab" * 32])
ck("mã việc sai dạng → từ chối", r.returncode == 2, r.stdout[-200:])

# =================================================================== 9. MuMu: ổ dữ liệu VDI thật → máy nhận giữ mã ổ (UUID) của mình
print("9. MuMu: ổ dữ liệu là file VDI → máy nhận GIỮ MÃ Ổ của mình (khớp sổ máy ảo), dữ liệu Android giống hệt máy cũ")
def vdi(u, body=b""):
    h = bytearray(0x200); h[0:40] = b"<<< Oracle VM VirtualBox Disk Image >>>\n"
    h[0x40:0x44] = (0xBEDA107F).to_bytes(4, "little"); h[0x44:0x48] = (0x00010001).to_bytes(4, "little")
    h[0x48:0x4C] = (0x190).to_bytes(4, "little"); h[0x4C:0x50] = (1).to_bytes(4, "little"); h[0x188:0x198] = u
    return bytes(h) + body
U_SRC, U_TPL = os.urandom(16), os.urandom(16)
B.tpl = vdi(U_TPL, b"\0" * 4096)
LOG.clear()
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
pidu = mk_phone("U", "active", True, vdi(U_SRC, RND(1 * 2**20 + 77)))
batch, n = DBX.admin_start("win3", ids=[pidu])
ok = run_until([A, B], lambda: next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["status"] == "done"
               and next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)["src_fin"], 90)
idle([A, B])
ph = DBX.phone(pidu); src = PH["U"][2]; i = B.idx_of(ph["container"]) if ph["node"] == "win5" else None
got = B.data_of(i) if i is not None else b""
ck("chuyển xong", ok and i is not None, LOG[-15:])
ck("mã ổ ở máy nhận = mã ổ máy trống của máy chủ mới (không mang mã ổ máy cũ)", got[0x188:0x198] == U_TPL, got[0x188:0x198].hex())
ck("mọi byte khác giống hệt ổ máy cũ", len(got) == len(src) and got[:0x188] == src[:0x188] and got[0x198:] == src[0x198:])
ck("nhật ký máy chủ mới ghi đã dùng mã ổ của máy nhận", any("mã ổ của máy nhận" in x for x in LOG), [x for x in LOG if "win5" in x][-8:])
os.environ["HOME"] = B.home
nv = os.path.join(B.home, "x.vdi"); open(nv, "wb").write(vdi(U_SRC, b"abc"))
h = B.G["_vdi_hdr"](nv); B.G["_vdi_set_uuid"](nv, U_TPL); h2 = B.G["_vdi_hdr"](nv)
ck("_vdi_hdr đọc đúng kiểu + mã ổ · _vdi_set_uuid chỉ đổi 16 byte mã ổ", h == {"type": 1, "uuid": U_SRC} and h2 == {"type": 1, "uuid": U_TPL}
   and open(nv, "rb").read()[0x198:] == vdi(U_SRC, b"abc")[0x198:], [h, h2])
open(nv, "wb").write(b"khong phai vdi" * 100)
ck("file không phải VDI → _vdi_hdr = None (không đụng)", B.G["_vdi_hdr"](nv) is None)

# =================================================================== 10. máy chủ mới thiếu ổ cứng → không nhận, trả việc
print("10. Máy chủ mới không đủ chỗ ổ cứng cho ổ dữ liệu sắp chép → không tạo máy, trả việc về hàng chờ (máy cũ không bị tắt)")
LOG.clear()
_du = shutil.disk_usage
def du_small(pth):
    r = _du(pth)
    return type(r)(r.total, r.total - 2**30, 2**30) if os.path.abspath(str(pth)).startswith(B.vmroot) else r      # ổ máy ảo của win5 còn 1 GB
shutil.disk_usage = du_small
for n_ in DBX.t["cloud_nodes"]: n_["enabled"] = True
pidd = mk_phone("D", "active", True, RND(3 * 2**20))
batch, n = DBX.admin_start("win3", ids=[pidd]); jd = next(j for j in DBX.t["cp_moves"] if j["batch"] == batch)
ok = run_until([A, B], lambda: "hết chỗ" in str(jd.get("note") or ""), 40); idle([A, B])
shutil.disk_usage = _du
ck("win5 báo hết chỗ ổ cứng → trả việc về hàng chờ (ghi lý do), không giữ máy trống", ok and jd["status"] == "queued" and not jd["dst"]
   and not any(x["name"].startswith(PH["D"][1] + "m") for x in B.EM.values()), [jd, LOG[-8:]])
ck("máy D ở win3 vẫn chạy, không bị khoá / tắt", A.EM[A.idx_of(PH["D"][1])]["running"] and not DBX.phone(pidd)["locked"] and DBX.phone(pidd)["node"] == "win3")
ck("đã báo cỡ ổ dữ liệu (size_hint) trước khi máy chủ mới tạo máy", int(jd.get("size_hint") or 0) == 3 * 2**20, jd.get("size_hint"))
DBX.admin_cancel("win3"); run_until([A, B], lambda: jd["src_fin"], 20); idle([A, B])
B.D._FULL["until"] = 0

print(f"\n{OK[0]}/{OK[1]} đạt")
sys.stdout = REAL_OUT
if OK[0] != OK[1]:
    print("\n--- nhật ký (40 dòng cuối) ---"); print("\n".join(LOG[-40:]))
sys.exit(0 if OK[0] == OK[1] else 1)
