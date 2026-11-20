# -*- coding: utf-8 -*-
"""Soát tĩnh mọi file Python của winpc:
     · cú pháp + cảnh báo (chuỗi thoát sai…) coi như lỗi
     · TÊN CHƯA KHAI BÁO: tên được đọc mà cả file không chỗ nào gán / import / định nghĩa (vd dùng re.… mà quên `import re`) — lỗi kiểu này chỉ nổ
       lúc chạy tới đúng dòng đó trên máy thật, bộ thử dùng lớp giả có thể không đi qua."""
import ast, builtins, os, sys, warnings

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # cửa sổ lệnh Windows (cp1252) không in được dấu ✓ / chữ có dấu
except Exception: pass
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KNOWN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__builtins__", "__spec__", "__package__", "__class__"}


def bound_names(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): out.add(n.name)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = n.args
            for x in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []): out.add(x.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for x in n.names: out.add((x.asname or x.name).split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name: out.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)): out.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name: out.add(n.name)
        elif isinstance(n, ast.MatchStar) and n.name: out.add(n.name)
    return out


def undefined(tree):
    have = bound_names(tree) | KNOWN
    return sorted({(n.id, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in have}, key=lambda x: x[1])


def self_test():
    """Bộ soát phải bắt được đúng lỗi 'quên import' và không báo nhầm các kiểu gán thường gặp."""
    bad = ast.parse("import os\ndef f(a, *b, c=1, **d):\n    return re.sub('x', '', a) + os.sep\n")
    good = ast.parse("import os.path as p, json\nfrom x import (y as z)\nclass K: pass\ndef f(a, *b, c=1, **d):\n    global G\n    G = [i for i in b]\n"
                     "    try: pass\n    except OSError as e: print(e)\n    with open(a) as fh: return (lambda q: q)(fh), p, json, z, K, G, d, c, (w := 1), w\n")
    return [x[0] for x in undefined(bad)] == ["re"] and undefined(good) == []


if not self_test():
    print("✗ bộ soát tên chưa khai báo tự thử KHÔNG đạt"); sys.exit(1)
bad = 0
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for f in sorted(fn):
        if not f.endswith(".py"): continue
        p = os.path.join(dp, f); src = open(p, encoding="utf-8").read()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            try: compile(src, p, "exec")
            except (SyntaxError, SyntaxWarning, DeprecationWarning) as e:
                bad += 1; print("✗", os.path.relpath(p, root), "→", e)
                continue
        miss = undefined(ast.parse(src))
        if miss:
            bad += 1; print("✗", os.path.relpath(p, root), "→ tên chưa khai báo:", ", ".join("%s (dòng %d)" % m for m in miss[:12]))
            continue
        print("✓", os.path.relpath(p, root), "(%d dòng)" % (src.count("\n") + 1))
sys.exit(1 if bad else 0)
