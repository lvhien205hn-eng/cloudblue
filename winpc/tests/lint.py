# -*- coding: utf-8 -*-
"""Soát tĩnh mọi file Python của winpc: cú pháp + cảnh báo (chuỗi thoát sai…) coi như lỗi."""
import ast, os, sys, warnings
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
bad = 0
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.endswith(".py"): continue
        p = os.path.join(dp, f); src = open(p, encoding="utf-8").read()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            try: compile(src, p, "exec")
            except (SyntaxError, SyntaxWarning, DeprecationWarning) as e:
                bad += 1; print("✗", os.path.relpath(p, root), "→", e)
                continue
        print("✓", os.path.relpath(p, root), "(%d dòng)" % (src.count("\n") + 1))
sys.exit(1 if bad else 0)
