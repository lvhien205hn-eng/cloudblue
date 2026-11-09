# -*- coding: utf-8 -*-
# =====================================================================================================
#  blueserver.py → BlueRobloxServer.exe  (bảng máy chủ BlueRoblox, KHÔNG cần cài Python)
#
#  Giải nén thư mục BlueRobloxServer vào C:\blue  →  C:\blue\BlueRobloxServer\BlueRobloxServer.exe (các file .py vẫn ở C:\blue)
#   • Bấm đúp            → mở bảng máy chủ (panel.py)
#   • exe script.py …    → chạy 1 file .py bằng Python có sẵn bên trong exe (bảng dùng cách này để chạy các dịch vụ)
#  Các file .py vẫn tải/cập nhật từ GitHub như cũ — sửa .py KHÔNG cần build lại exe.
#  CHỈ dành cho admin: build ở GitHub Actions → Artifacts (không đưa lên web).
# =====================================================================================================
import os, runpy, sys

# ---- thư viện các dịch vụ dùng (PyInstaller chỉ đóng gói thứ được import ở đây) ----
import argparse, asyncio, base64, builtins, codecs, collections, concurrent.futures, csv, ctypes, datetime, email, email.utils  # noqa: F401,E401
import glob, hashlib, hmac, html, http.client, http.cookies, http.server, io, ipaddress, json, locale, logging, math, mimetypes  # noqa: F401,E401
import platform, queue, random, re, secrets, selectors, shlex, shutil, signal, socket, socketserver, ssl, statistics, string  # noqa: F401,E401
import struct, subprocess, tempfile, textwrap, threading, time, traceback, typing, unicodedata, urllib.error, urllib.parse  # noqa: F401,E401
import urllib.request, uuid, zipfile, zlib, webbrowser, getpass, pathlib, fnmatch, copy, functools, itertools, operator  # noqa: F401,E401
if os.name == "nt":
    import ctypes.wintypes, msvcrt, winreg  # noqa: F401,E401
try:
    import tkinter, tkinter.ttk, tkinter.messagebox, tkinter.simpledialog, tkinter.filedialog  # noqa: F401,E401
except ImportError:
    pass
for _m in ("numpy", "PIL.Image", "windows_capture", "cryptography.x509", "cryptography.hazmat.primitives.asymmetric.ec",
           "cryptography.hazmat.primitives.serialization", "cryptography.hazmat.primitives.hashes", "cryptography.x509.oid"):
    try: __import__(_m)
    except Exception: pass

FROZEN = getattr(sys, "frozen", False)
B = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
if not os.path.isfile(os.path.join(B, "panel.py")) and os.path.isfile(os.path.join(os.path.dirname(B), "panel.py")):
    B = os.path.dirname(B)                     # exe nằm trong C:\blue\BlueRobloxServer\ → các file .py ở C:\blue


def _unbuffered():
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
        except Exception: pass


def main():
    args = sys.argv[1:]
    while args and args[0] in ("-u", "-B", "-E", "-s", "-S", "-I"):   # cờ của python.exe → bỏ qua (luôn không đệm)
        args = args[1:]
    _unbuffered()
    if args and args[0] == "-c" and len(args) >= 2:                  # python -c "mã"
        sys.argv = ["-c"] + args[2:]
        exec(compile(args[1], "<string>", "exec"), {"__name__": "__main__"}); return
    if args and args[0] == "-m" and len(args) >= 2:                  # python -m …  (pip không dùng được trong exe: thư viện đã có sẵn)
        if args[1] == "pip":
            print("(bản exe đã có sẵn thư viện — bỏ qua pip)"); return
        sys.argv = [args[1]] + args[2:]; runpy.run_module(args[1], run_name="__main__", alter_sys=True); return
    if args and args[0].lower().endswith((".py", ".pyw")):           # exe script.py …
        sc = args[0]
        if not os.path.isabs(sc): sc = os.path.join(os.getcwd(), sc) if os.path.isfile(os.path.join(os.getcwd(), sc)) else os.path.join(B, sc)
        sys.argv = [sc] + args[1:]; sys.path.insert(0, os.path.dirname(sc))
        runpy.run_path(sc, run_name="__main__"); return
    # không có tham số (bấm đúp) / --auto → mở bảng máy chủ
    panel = os.path.join(B, "panel.py")
    if os.name == "nt":                                            # bảng là cửa sổ → ẩn khung đen của exe
        try:
            h = ctypes.windll.kernel32.GetConsoleWindow()
            if h: ctypes.windll.user32.ShowWindow(h, 0)
        except Exception: pass
    if not os.path.isfile(panel):
        try:
            import tkinter.messagebox as mb
            mb.showerror("BlueRoblox", f"Thiếu {panel}\nĐặt BlueRobloxServer.exe trong thư mục C:\\blue (cùng các file .py của BlueRoblox).")
        except Exception: print("Thiếu", panel)
        return
    sys.argv = [panel] + args; sys.path.insert(0, B)
    runpy.run_path(panel, run_name="__main__")


if __name__ == "__main__":
    main()
