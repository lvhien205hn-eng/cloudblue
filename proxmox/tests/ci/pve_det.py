#!/usr/bin/env python3
"""CI: tạo 2 "ISO máy mẫu" giả với nội dung CỐ ĐỊNH (giống nhau trên mọi máy) để so file ISO ghép trên Windows với file ghép trên Linux.
   pve_det.py <thư mục>  → CloudBlue-MayMau-det1.iso (2 MiB + 123 byte), CloudBlue-MayMau-det2.iso (3 MiB + 4567 byte)"""
import hashlib, os, sys

d = sys.argv[1]
os.makedirs(d, exist_ok=True)
for name, seed, n in (("CloudBlue-MayMau-det1.iso", "cloudblue-det-1", 2 * 1024 * 1024 + 123), ("CloudBlue-MayMau-det2.iso", "cloudblue-det-2", 3 * 1024 * 1024 + 4567)):
    open(os.path.join(d, name), "wb").write(hashlib.shake_256(seed.encode()).digest(n))
    print(name, n)
