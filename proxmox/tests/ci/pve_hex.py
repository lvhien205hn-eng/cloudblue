#!/usr/bin/env python3
"""In cau truc ISO 9660 (de doi chieu khi viet / thu pve_iso.py): volume descriptor, thu muc goc, path table, MBR / GPT, duoi file."""
import os
import struct
import sys

p = sys.argv[1]
size = os.path.getsize(p)
f = open(p, "rb")


def sec(n, c=1):
    f.seek(n * 2048)
    return f.read(2048 * c)


def hexd(b, base=0, limit=None):
    out = []
    for i in range(0, len(b) if limit is None else min(len(b), limit), 16):
        row = b[i:i + 16]
        out.append("%08x  %-47s  %s" % (base + i, row.hex(" "), "".join(chr(c) if 32 <= c < 127 else "." for c in row)))
    return "\n".join(out)


print("size", size, "sectors2048", size / 2048)
i = 16
pvd = None
while i < 64:
    d = sec(i)
    t = d[0]
    print("VD sector", i, "type", t, "id", d[1:6], "ver", d[6], "esc", d[88:120].rstrip(b"\0 ") if t == 2 else "")
    if t == 1:
        pvd = d
    if t == 0:
        print("   boot record:", d[7:39].rstrip(b"\0"), "catalog LBA", struct.unpack("<I", d[71:75])[0])
    if t == 255:
        break
    i += 1
print("sector sau terminator (%d):" % (i + 1), sec(i + 1)[:96])
vss = struct.unpack("<I", pvd[80:84])[0]
pts = struct.unpack("<I", pvd[132:136])[0]
ptl, ptlo = struct.unpack("<II", pvd[140:148])
ptm, ptmo = struct.unpack(">II", pvd[148:156])
rl = struct.unpack("<I", pvd[158:162])[0]
rs = struct.unpack("<I", pvd[166:170])[0]
print("volid", pvd[40:72], "space", vss, "(file sectors %d)" % (size // 2048), "pathtab size", pts, "L", ptl, ptlo, "M", ptm, ptmo)
print("root lba", rl, "len", rs, "root record:", pvd[156:190].hex())
print("dates: creat", pvd[813:830], "modif", pvd[830:847], "exp", pvd[847:864], "eff", pvd[864:881])
print("-- PVD hex (0..200, 800..890)")
print(hexd(pvd[:200]))
print(hexd(pvd[800:890], 800))
root = sec(rl, (rs + 2047) // 2048)[:rs]
print("-- thu muc goc: ban ghi")
o = 0
subdirs = []
while o < len(root):
    ln = root[o]
    if ln == 0:
        o = (o // 2048 + 1) * 2048
        continue
    r = root[o:o + ln]
    ext = struct.unpack("<I", r[2:6])[0]
    dl = struct.unpack("<I", r[10:14])[0]
    nl = r[32]
    name = r[33:33 + nl]
    su = r[33 + nl + (1 - nl % 2):]
    print("@%d len %d ext %d size %d flags %02x date %s name %r SU(%d): %s" % (o, ln, ext, dl, r[25], r[18:25].hex(), name, len(su), su.hex()))
    if r[25] & 2 and name not in (b"\0", b"\1"):
        subdirs.append((name, ext, dl))
    o += ln
print("-- thu muc goc: hex")
print(hexd(root))
for name, ext, dl in subdirs[:3]:
    print("-- thu muc con %r lba %d: 2 ban ghi dau" % (name, ext))
    print(hexd(sec(ext)[:300]))
print("-- CE cua '.' (neu co)")
r0 = root[:root[0]]
su = r0[34:]
k = 0
while k + 4 <= len(su):
    sig, l = su[k:k + 2], su[k + 2]
    if l < 4:
        break
    if sig == b"CE":
        blk, off, cl = struct.unpack("<I", su[k + 4:k + 8])[0], struct.unpack("<I", su[k + 12:k + 16])[0], struct.unpack("<I", su[k + 20:k + 24])[0]
        print("CE -> block", blk, "off", off, "len", cl)
        print(hexd(sec(blk)[off:off + cl]))
    k += l
print("-- path table L (128 byte dau)")
print(hexd(sec(ptl)[:128]))
print("-- path table M (64 byte dau)")
print(hexd(sec(ptm)[:64]))
print("-- MBR (byte 432..512)")
f.seek(0)
mbr = f.read(512)
print(hexd(mbr[432:], 432))
f.seek(512)
g = f.read(92)
print("-- GPT header:", g[:8], "cur %d bak %d first %d last %d entries@%d n %d" % (struct.unpack("<QQQQ", g[24:56]) + (struct.unpack("<Q", g[72:80])[0], struct.unpack("<I", g[80:84])[0])) if g[:8] == b"EFI PART" else "(khong co)")
f.seek(max(0, size - 131072))
tail = f.read()
pos = tail.find(b"EFI PART")
print("-- duoi file: 'EFI PART' o", (size - len(tail) + pos) if pos >= 0 else None, "(sector512 %s)" % ((size - len(tail) + pos) // 512 if pos >= 0 else None))
nz = [n for n in range(len(tail) // 2048) if any(tail[n * 2048:(n + 1) * 2048])]
print("   sector 2048 khac 0 trong 64 sector cuoi:", [(size - len(tail)) // 2048 + n for n in nz])
