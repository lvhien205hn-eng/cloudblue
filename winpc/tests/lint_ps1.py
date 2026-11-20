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
    check_struct(strip_ps1(s), name)


def strip_ps1(s):
    """Thay chú thích bằng khoảng trắng, chuỗi bằng 'S' / "S" (giữ nguyên số dòng) để soát cấu trúc mà không vướng nội dung chuỗi."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "#" and s[i - 1:i] != "`":
            j = s.find("\n", i); j = n if j < 0 else j
            i = j; continue
        if c == "'":
            j = i + 1
            while True:
                j = s.find("'", j)
                if j < 0: return "".join(out)
                if s[j:j + 2] == "''": j += 2; continue
                break
            out.append("'S'" + "\n" * s.count("\n", i, j)); i = j + 1; continue
        if c == '"':
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
            out.append('"S"' + "\n" * s.count("\n", i, j)); i = j + 1; continue
        out.append(c); i += 1
    return "".join(out)


def check_struct(t, name):
    """Soát cấu trúc lệnh (không có PowerShell ở đây để phân tích thật): mỗi if / elseif / while / foreach / for phải là  từ khoá ( … ) { … } ;
       else / try / finally phải đi với { ; elseif / else / catch / finally phải đứng ngay sau dấu } ; foreach phải có ' in ' ;
       toán tử -xx phải là toán tử có thật ; không có 2 chuỗi / biến đứng liền nhau thiếu toán tử."""
    def line(pos): return t.count("\n", 0, pos) + 1

    def match_paren(pos, op="(", cl=")"):
        depth = 0
        for k in range(pos, len(t)):
            if t[k] == op: depth += 1
            elif t[k] == cl:
                depth -= 1
                if depth == 0: return k
        return -1
    for m in re.finditer(r"(?<![A-Za-z0-9_$.:-])(if|elseif|while|foreach|for|else|try|catch|finally|function)(?![A-Za-z0-9_-])", t):
        kw, a, b = m.group(1), m.start(), m.end()
        before = t[:a].rstrip()
        after = t[b:]
        if before.endswith(("|", ",")) or re.match(r"\s*=", after): continue                    # không phải từ khoá (tên tham số, giá trị…)
        if kw in ("elseif", "else", "catch", "finally") and not before.endswith("}"):
            fail(name, "dòng %d: '%s' không đứng ngay sau dấu }" % (line(a), kw)); continue
        if kw in ("if", "elseif", "while", "foreach", "for"):
            mm = re.match(r"\s*\(", after)
            if not mm: fail(name, "dòng %d: sau '%s' không có dấu (" % (line(a), kw)); continue
            op = b + mm.end() - 1
            cl = match_paren(op)
            if cl < 0: fail(name, "dòng %d: ngoặc của '%s' chưa đóng" % (line(a), kw)); continue
            inner = t[op + 1:cl]
            if kw == "foreach" and not re.match(r"\s*\$[A-Za-z_][A-Za-z0-9_]*\s+in\s+\S", inner): fail(name, "dòng %d: foreach thiếu '$biến in …'" % line(a))
            if kw == "for" and inner.count(";") != 2: fail(name, "dòng %d: for cần đúng 2 dấu ;" % line(a))
            if kw in ("if", "elseif", "while") and not inner.strip(): fail(name, "dòng %d: điều kiện rỗng" % line(a))
            if not re.match(r"\s*\{", t[cl + 1:]): fail(name, "dòng %d: sau '%s ( … )' không có dấu {" % (line(a), kw))
        elif kw in ("else", "try", "finally"):
            if not re.match(r"\s*\{", after): fail(name, "dòng %d: sau '%s' không có dấu {" % (line(a), kw))
        elif kw == "catch":
            if not re.match(r"\s*(\[[A-Za-z.]+\]\s*)?\{", after): fail(name, "dòng %d: sau 'catch' không có dấu {" % line(a))
        elif kw == "function":
            if not re.match(r"\s+[A-Za-z][A-Za-z0-9-]*\s*(\(|\{)", after): fail(name, "dòng %d: khai báo function sai dạng" % line(a))
    okops = {"eq", "ne", "gt", "ge", "lt", "le", "and", "or", "not", "match", "notmatch", "replace", "contains", "notcontains", "join", "split", "is", "isnot", "like", "notlike", "in", "notin", "f", "band", "bor", "xor"}
    for m in re.finditer(r"(?<=[\s(])-([a-z]+)(?=\s)", t):
        w = m.group(1)
        prev = t[:m.start()].rstrip()[-1:]
        if w not in okops and prev in (")", "]", "'", '"') and not re.match(r"\s+(\$|\(|'S'|\"S\"|\d)", t[m.end():]) is None:
            fail(name, "dòng %d: toán tử lạ -%s" % (line(m.start()), w))
    for m in re.finditer(r"('S'|\"S\")[ \t]+('S'|\"S\")", t):                              # 2 chuỗi liền nhau: chỉ hợp lệ khi là đối số của 1 lệnh
        ln = t[t.rfind("\n", 0, m.start()) + 1:m.start()]
        if re.search(r"(\+|-eq|-ne|-match|-and|-or|=|\()\s*$", ln): fail(name, "dòng %d: 2 chuỗi đứng liền nhau thiếu toán tử" % line(m.start()))


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
