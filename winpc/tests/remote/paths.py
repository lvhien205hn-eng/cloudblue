# -*- coding: utf-8 -*-
"""Tìm gốc kho mã (thư mục có windows/bluestream.py) cho các bộ thử điều khiển máy PC — chúng thử chung mã của máy chủ phát hình (windows/)
   và của máy PC thuê (winpc/agent/). Đặt biến môi trường CB_ROOT để chỉ thẳng."""
import os


def root():
    r = os.environ.get("CB_ROOT")
    if r and os.path.isfile(os.path.join(r, "windows", "bluestream.py")): return os.path.abspath(r)
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isfile(os.path.join(d, "windows", "bluestream.py")): return d
        d = os.path.dirname(d)
    raise SystemExit("Khong tim thay windows/bluestream.py - chay tu trong kho ma cloudblue hoac dat CB_ROOT")


ROOT = root()
SRV = os.path.join(ROOT, "windows")                # bluestream.py + pcrelay.py
AGENT = os.path.join(ROOT, "winpc", "agent")       # pcremote.py
CLIENT = os.path.join(ROOT, "pc-client")           # brstream.py (mã nối mạng của app PC)
