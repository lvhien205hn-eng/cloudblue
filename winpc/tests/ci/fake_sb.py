# -*- coding: utf-8 -*-
"""Máy chủ Supabase GIẢ cho CI linux-check (chỉ chạy trên máy CI, không đụng máy chủ thật): agent CachyOS trong máy ảo QEMU gọi
   http://10.0.2.2:<cổng>/rest/v1/rpc/<hàm> (10.0.2.2 = máy CI). Mỗi lần gọi ghi 1 dòng JSON (hàm + thân) vào file nhật ký,
   trả lời như máy chủ thật ở mức tối thiểu: pc_enroll → mã máy ci-pc-1 · pc_poll → ok.
   Chạy:  python3 fake_sb.py <cổng> <file nhật ký>      ·  Kiểm:  python3 fake_sb.py --check <file nhật ký> <vé>"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PC_ID, PC_TOKEN = "ci-pc-1", "ci-token"


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(min(n, 1 << 20)) if n > 0 else b""
        fn = self.path.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        try: body = json.loads(raw or b"{}")
        except ValueError: body = {"raw": raw.decode("utf-8", "replace")[:300]}
        with open(self.server.log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "fn": fn, "body": body, "ua": self.headers.get("User-Agent")}, ensure_ascii=False) + "\n")
        if fn == "pc_enroll":
            r = {"ok": True, "id": PC_ID, "token": PC_TOKEN, "name": "CB-CI01", "approved": True, "poll_s": 10}
        elif fn == "pc_poll":
            r = {"ok": True, "poll_s": 10} if (body.get("p_id"), body.get("p_token")) == (PC_ID, PC_TOKEN) else {"ok": False, "err": "BAD_TOKEN"}
        else:
            r = {"ok": False, "err": "NO_FN"}
        out = json.dumps(r).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a): pass


def check(log, ticket):
    """In tóm tắt các lần agent gọi máy chủ giả; trả 0 khi agent đăng ký bằng ĐÚNG vé của lệnh + báo đúng là CachyOS + hỏi máy chủ được."""
    rows = []
    if os.path.isfile(log):
        for ln in open(log, encoding="utf-8"):
            try: rows.append(json.loads(ln))
            except ValueError: pass
    en = [r for r in rows if r.get("fn") == "pc_enroll"]
    po = [r for r in rows if r.get("fn") == "pc_poll" and (r.get("body") or {}).get("p_id") == PC_ID]
    ok_en = [r for r in en if r["body"].get("p_key") == ticket and (r["body"].get("p_info") or {}).get("os") == "cachyos"]
    info = (ok_en[0]["body"].get("p_info") if ok_en else (en[0]["body"].get("p_info") if en else None)) or {}
    print("- agent goi may chu gia: %d lan dang ky (%d dung ve), %d lan hoi may chu" % (len(en), len(ok_en), len(po)))
    if info:
        keep = ("host", "os", "os_name", "os_ver", "agent", "linux", "fw", "cpu", "cores", "ram_gb", "gpus", "board", "rec", "sec", "rmt", "err")
        print("- thong tin may agent gui: " + json.dumps({k: info.get(k) for k in keep if k in info}, ensure_ascii=False)[:900])
    if rows: print("- User-Agent: %s" % rows[-1].get("ua"))
    good = bool(ok_en) and bool(po) and info.get("linux") is True
    print("- AGENT: " + ("DAT" if good else "CHUA DAT"))
    return 0 if good else 1


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
    srv = ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), H)
    srv.log = sys.argv[2]
    srv.serve_forever()
