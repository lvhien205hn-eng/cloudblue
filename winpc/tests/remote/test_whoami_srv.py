# -*- coding: utf-8 -*-
"""Thử whoami() của máy chủ phát hình (windows/bluestream.py, 21.11l): quyền admin trên trạm = hàm SQL is_admin() hỏi bằng CHÍNH phiên người xem
   (admin đã bật xác minh 2 bước mà phiên chưa nhập mã 6 số → không phải admin). Supabase giả, không gọi mạng.
   Chạy:  python3 winpc/tests/remote/test_whoami_srv.py"""
import importlib, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import SRV as SRC                                       # noqa: E402
OK = FAIL = 0


def ck(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1; print("  ✓", name)
    else: FAIL += 1; print("  ✗", name, "→", str(extra)[:600])


tmp = tempfile.mkdtemp(prefix="cbwho-")
shutil.copy(os.path.join(SRC, "bluestream.py"), os.path.join(tmp, "bluestream.py"))
open(os.path.join(tmp, "cloudphone.conf"), "w", encoding="utf-8").write("NODE_ID=whotest\nPC_RELAY=0\n")
sys.path.insert(0, tmp); sys.argv = ["bluestream.py"]
H = importlib.import_module("bluestream"); H.log = lambda *a: None
S = {}


def fake_sb(method, path, body=None, token=None, timeout=15, extra=None):
    S["calls"].append((method, path, token))
    if path == "/auth/v1/user": return {"id": S["uid"]} if token in S["good"] else (_ for _ in ()).throw(OSError("401"))
    if path.startswith("/rest/v1/profiles?"): return [S["profile"]]
    if path == "/rest/v1/rpc/is_admin":
        if S.get("rpc_err"): raise OSError("mạng lỗi")
        return S["is_admin"]
    return None


H.sb = fake_sb


def who(token="jwt-1", **sc):
    S.clear(); S.update(dict(calls=[], uid="u-1", good={"jwt-1", "jwt-2", "jwt-3", "jwt-4", "jwt-5"}, profile={"role": "admin", "locked": False}, is_admin=True), **sc)
    H._ucache.clear(); return H.whoami(token)


print("whoami trên máy chủ phát hình + xác minh 2 bước")
me = who()
rpc = [c for c in S["calls"] if c[1] == "/rest/v1/rpc/is_admin"]
ck("admin, is_admin() = true → admin; hỏi is_admin() bằng CHÍNH mã đăng nhập người xem", me == {"uid": "u-1", "admin": True} and rpc == [("POST", "/rest/v1/rpc/is_admin", "jwt-1")], (me, S["calls"]))
ck("admin đã bật 2 bước, phiên chưa nhập mã (is_admin() = false) → không phải admin", who(is_admin=False) == {"uid": "u-1", "admin": False})
ck("hỏi is_admin() lỗi mạng → không phải admin (chặn chứ không mở)", who(rpc_err=True) == {"uid": "u-1", "admin": False})
me = who(profile={"role": "user", "locked": False})
ck("khách thường → admin = false, không hỏi is_admin() (đỡ tốn)", me == {"uid": "u-1", "admin": False} and not [c for c in S["calls"] if c[1] == "/rest/v1/rpc/is_admin"], S["calls"])
ck("tài khoản bị khoá → None", who(profile={"role": "admin", "locked": True}) is None)
ck("mã đăng nhập sai → None", who("sai") is None)
who(); S["calls"] = []; me1 = H.whoami("jwt-1"); n1 = len(S["calls"])
ck("phiên vừa hỏi xong → dùng lại 2 phút (không hỏi lại Supabase)", me1 and n1 == 0, (me1, n1))
print(f"\n{OK}/{OK + FAIL} đạt")
sys.exit(1 if FAIL else 0)
