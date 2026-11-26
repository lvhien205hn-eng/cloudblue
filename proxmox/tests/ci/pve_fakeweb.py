#!/usr/bin/env python3
"""Web GIẢ cho CI ISO Proxmox tự cài: nhận các lời gọi RPC của cbhost (vm_host_hello / vm_host_poll), trả lời "máy chủ chờ duyệt", ghi lại lời gọi
(mã riêng của máy được che). Không phải web thật, không lưu gì ngoài file nhật ký.   pve_fakeweb.py <cổng> <file nhật ký>"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT, LOG = int(sys.argv[1]), sys.argv[2]
seen = {}
n = [0]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        try: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8") or "{}")
        except Exception: body = {}
        fn = self.path.rsplit("/", 1)[-1]
        if isinstance(body, dict) and "p_secret" in body: body["p_secret"] = "<%d ky tu>" % len(str(body["p_secret"]))
        txt = json.dumps(body, ensure_ascii=False, sort_keys=True)
        key = json.dumps({k: v for k, v in body.items() if k != "p_metrics"} if isinstance(body, dict) else body, sort_keys=True) + json.dumps(
            {k: v for k, v in ((body.get("p_metrics") or {}) if isinstance(body, dict) else {}).items() if k in ("iso", "tpl", "tpl_auto", "ver")}, sort_keys=True)
        if seen.get(fn) != key and n[0] < 120:
            seen[fn] = key; n[0] += 1
            open(LOG, "a", encoding="utf-8").write("%s %s\n" % (fn, txt[:1800]))
        name = ((body.get("p_info") or {}).get("host") if isinstance(body, dict) else None) or "ci"
        if fn == "vm_host_hello": r = {"ok": True, "id": "ci-1", "status": "new", "name": name}
        elif fn == "vm_host_poll": r = {"ok": True, "status": "new", "name": "ci", "vps": [], "tpl": [], "tpl_jobs": [], "poll_s": 10}
        else: r = None
        out = json.dumps(r).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


HTTPServer(("127.0.0.1", PORT), H).serve_forever()
