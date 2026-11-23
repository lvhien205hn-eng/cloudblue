# -*- coding: utf-8 -*-
"""Máy chủ GIẢ cho bộ thử ISO máy chủ Cloud Phone (maychu_check.ps1): giả API Cloudflare (đường hầm + tên miền) và bảng cloud_nodes của Supabase.
   Chạy: python fake_cf.py <cổng> <tên miền> <khoá supabase đúng>      Mã Cloudflare: 'tok-ok' (đủ quyền) · 'tok-notunnel' (không có quyền đường hầm).
   GET /_state → toàn bộ trạng thái (để bộ thử soát) · POST /_reset → về trạng thái đầu · POST /_nodes [{"id", "age"}] → đổi danh sách máy chủ."""
import json, sys, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, DOMAIN, SBKEY = int(sys.argv[1]), sys.argv[2], sys.argv[3]
S = {}


def reset():
    S.clear()
    S.update(tunnels=[], configs={}, dns=[], calls=[], seq=0,
             nodes=[{"id": "win1", "age": 20}, {"id": "win5", "age": 99999}, {"id": "win8", "age": 15}],     # age = giây từ lần báo gần nhất
             phones=[{"node": "win5", "status": "active"}, {"node": "win5", "status": "expired"}, {"node": "win5", "status": "cancelled"}, {"node": "win8", "status": "active"}])


reset()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def out(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: return json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        except ValueError: return {}

    def cf_err(self, code, msg): self.out(code, {"success": False, "errors": [{"code": 10000, "message": msg}], "result": None})

    def handle_any(self, method):
        u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query)); p = u.path
        body = self.body() if method in ("POST", "PUT") else {}
        if p == "/_state": return self.out(200, S)
        if p == "/_reset": reset(); return self.out(200, {"ok": True})
        if p == "/_nodes": S["nodes"] = body if isinstance(body, list) else S["nodes"]; return self.out(200, {"ok": True})     # đổi danh sách máy chủ "đang báo về web"
        if p.startswith("/rest/v1/"):                                             # ---- Supabase giả
            # Giống Supabase thật: khoá sb_secret_… gửi từ thứ tự xưng là TRÌNH DUYỆT (User-Agent "Mozilla/…" — mặc định của PowerShell) → 401 dù khoá đúng
            if (self.headers.get("apikey") or "").startswith("sb_secret_") and (self.headers.get("User-Agent") or "").lower().startswith("mozilla/"):
                S["browser_block"] = S.get("browser_block", 0) + 1
                return self.out(401, {"message": "Forbidden use of secret API key in browser",
                                      "hint": "Secret API keys can only be used in a protected environment and should never be used in a browser. Delete this secret API key immediately!"})
        if p.startswith("/rest/v1/cloud_nodes"):
            if self.headers.get("apikey") != SBKEY or self.headers.get("Authorization") != "Bearer " + SBKEY: return self.out(401, {"message": "Invalid API key"})
            now = time.time()
            return self.out(200, [{"id": n["id"], "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - n["age"]))} for n in S["nodes"]])
        if p.startswith("/rest/v1/cloud_phones"):                                 # ---- máy khách theo máy chủ (node=eq.winN&status=in.(…))
            if self.headers.get("apikey") != SBKEY: return self.out(401, {"message": "Invalid API key"})
            node = (q.get("node") or "").replace("eq.", "")
            want = (q.get("status") or "").replace("in.(", "").rstrip(")").split(",")
            return self.out(200, [{"status": x["status"]} for x in S["phones"] if x["node"] == node and x["status"] in want])
        if not p.startswith("/client/v4/"): return self.out(404, {"error": "?"})
        tok = (self.headers.get("Authorization") or "").replace("Bearer ", "")
        S["calls"].append(method + " " + p)
        if tok not in ("tok-ok", "tok-notunnel"):                                 # như Cloudflare thật: mã sai dạng → 400 (6003 / 6111) · mã đúng dạng nhưng không tồn tại → 401 (1000)
            import re
            if not re.match(r"^[A-Za-z0-9_-]{40}$", tok):
                return self.out(400, {"success": False, "errors": [{"code": 6003, "message": "Invalid request headers",
                                      "error_chain": [{"code": 6111, "message": "Invalid format for Authorization header"}]}], "result": None})
            return self.out(401, {"success": False, "errors": [{"code": 1000, "message": "Invalid API Token"}], "result": None})
        p = p[len("/client/v4"):]
        if p == "/zones":
            return self.out(200, {"success": True, "result": [{"id": "z1", "name": DOMAIN, "account": {"id": "acc1"}}] if q.get("name") == DOMAIN else []})
        if p.startswith("/accounts/acc1/cfd_tunnel"):
            if tok != "tok-ok": return self.cf_err(403, "Authentication error")
            rest = p[len("/accounts/acc1/cfd_tunnel"):].strip("/")
            if not rest and method == "GET":
                return self.out(200, {"success": True, "result": [t for t in S["tunnels"] if not q.get("name") or t["name"] == q["name"]]})
            if not rest and method == "POST":
                if any(t["name"] == body.get("name") for t in S["tunnels"]): return self.cf_err(409, "tunnel name already exists")
                S["seq"] += 1
                t = {"id": "t-%d" % S["seq"], "name": body.get("name"), "config_src": body.get("config_src")}
                S["tunnels"].append(t); return self.out(200, {"success": True, "result": t})
            tid, _, tail = rest.partition("/")
            if not any(t["id"] == tid for t in S["tunnels"]): return self.cf_err(404, "tunnel not found")
            if tail == "configurations" and method == "PUT": S["configs"][tid] = body.get("config"); return self.out(200, {"success": True, "result": {"tunnel_id": tid}})
            if tail == "token" and method == "GET": return self.out(200, {"success": True, "result": "eyJ" + ("T0KEN" + tid.replace("-", "")) * 9})
            return self.cf_err(404, "?")
        if p.startswith("/zones/z1/dns_records"):
            rid = p[len("/zones/z1/dns_records"):].strip("/")
            if method == "GET": return self.out(200, {"success": True, "result": [r for r in S["dns"] if not q.get("name") or r["name"] == q["name"]]})
            if method == "POST":
                S["seq"] += 1
                r = dict(body, id="r-%d" % S["seq"]); S["dns"].append(r); return self.out(200, {"success": True, "result": r})
            if method == "PUT":
                for i, r in enumerate(S["dns"]):
                    if r["id"] == rid: S["dns"][i] = dict(body, id=rid); return self.out(200, {"success": True, "result": S["dns"][i]})
                return self.cf_err(404, "record not found")
        return self.cf_err(404, "?")

    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
