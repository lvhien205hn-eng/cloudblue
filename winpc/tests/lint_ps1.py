# -*- coding: utf-8 -*-
"""Soát tĩnh file .ps1 / .cmd (không có PowerShell ở đây): chỉ ASCII, CRLF, ngoặc { } ( ) [ ] cân ngoài chuỗi + chú thích,
   chuỗi đóng đủ, không biến trùng tên khác hoa/thường, không dùng biến tự động làm biến thường."""
import os, re, sys
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
bad = 0


def fail(f, m):
    global bad
    bad += 1; print("✗", f, "→", m)


def check_ps1(path, name):
    raw = open(path, "rb").read()
    if any(b > 127 for b in raw): fail(name, "có ký tự ngoài ASCII (PowerShell 5.1 đọc sai)")
    if b"\r\n" not in raw or re.search(rb"(?<!\r)\n", raw): fail(name, "xuống dòng không phải CRLF")
    s = raw.decode("ascii", "replace")
    stack, i, n, line = [], 0, len(s), 1
    pairs = {")": "(", "}": "{", "]": "["}
    while i < n:
        c = s[i]
        if c == "\n": line += 1
        if c == "#" and (i == 0 or s[i - 1] != "`"):                         # chú thích tới hết dòng
            if s[i - 1:i] == "<":                                           # <# … #>
                j = s.find("#>", i)
                if j < 0: fail(name, "chú thích <# chưa đóng (dòng %d)" % line); return
                line += s.count("\n", i, j); i = j + 2; continue
            j = s.find("\n", i); i = n if j < 0 else j; continue
        if c == "'":                                                        # chuỗi nháy đơn ('' = 1 nháy)
            j = i + 1
            while True:
                j = s.find("'", j)
                if j < 0: fail(name, "chuỗi nháy đơn chưa đóng (dòng %d)" % line); return
                if s[j:j + 2] == "''": j += 2; continue
                break
            line += s.count("\n", i, j); i = j + 1; continue
        if c == '"':                                                        # chuỗi nháy kép (` thoát, "" = 1 nháy, $( … ) lồng)
            j, depth = i + 1, 0
            while j < n:
                if s[j] == "`": j += 2; continue
                if s[j:j + 2] == "$(": depth += 1; j += 2; continue
                if depth and s[j] == "(": depth += 1
                elif depth and s[j] == ")": depth -= 1
                elif s[j] == '"' and not depth:
                    if s[j:j + 2] == '""': j += 2; continue
                    break
                j += 1
            if j >= n: fail(name, "chuỗi nháy kép chưa đóng (dòng %d)" % line); return
            line += s.count("\n", i, j); i = j + 1; continue
        if c in "({[": stack.append((c, line))
        elif c in ")}]":
            if not stack or stack[-1][0] != pairs[c]:
                fail(name, "ngoặc %s ở dòng %d không khớp (đang mở: %s)" % (c, line, stack[-1] if stack else "không có")); return
            stack.pop()
        i += 1
    if stack: fail(name, "ngoặc chưa đóng: %s" % stack[-3:])
    names = {}
    for m in re.finditer(r"\$(?:script:|global:)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|\+=)(?!=)", s):
        names.setdefault(m.group(1).lower(), set()).add(m.group(1))
    for k, v in names.items():
        if len(v) > 1: fail(name, "biến trùng tên khác hoa/thường: %s" % sorted(v))
    auto = {"args", "input", "host", "home", "pid", "matches", "error", "this", "true", "false", "null", "pwd", "event", "foreach", "psitem", "_"}
    for k in names:
        if k in auto: fail(name, "gán vào biến tự động $%s" % k)
    for kw in ("param(", "$ErrorActionPreference", "cloudblue-tao-iso"):
        if name.endswith("tao-iso.ps1") and kw not in s: fail(name, "thiếu " + kw)


def check_cmd(path, name):
    raw = open(path, "rb").read()
    if any(b > 127 for b in raw): fail(name, "có ký tự ngoài ASCII")
    if re.search(rb"(?<!\r)\n", raw): fail(name, "xuống dòng không phải CRLF")
    s = raw.decode("ascii", "replace")
    labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([A-Za-z0-9_]+)", s)}
    for m in re.finditer(r"(?i)\bgoto\s+:?([A-Za-z0-9_]+)", s):
        if m.group(1).lower() not in labels and m.group(1).lower() != "eof": fail(name, "goto tới nhãn không có: " + m.group(1))
    if s.count("(") != s.count(")") and name.endswith(".cmd"):
        opens = sum(ln.count("(") - ln.count(")") for ln in s.splitlines() if not ln.strip().lower().startswith(("rem", "echo")))
        if opens: fail(name, "ngoặc ( ) không cân ngoài dòng rem/echo")


for dp, dn, fn in os.walk(root):
    for f in sorted(fn):
        p = os.path.join(dp, f); rel = os.path.relpath(p, root)
        if f.endswith(".ps1"): check_ps1(p, rel)
        elif f.endswith((".cmd", ".bat", ".ini")): check_cmd(p, rel)
        else: continue
        print("  đã soát", rel)
print("SOÁT .ps1/.cmd:", "ĐẠT" if not bad else "%d LỖI" % bad)
sys.exit(1 if bad else 0)
