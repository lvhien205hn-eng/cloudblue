# -*- coding: utf-8 -*-
# =====================================================================================================
#  winpc/tests/ci/sys_check.py   —   thu ham chep tep THAT cua cbsys.WinSys (khong phai lop gia)
#    python sys_check.py <thu muc cb cua bo cai, hoac thu muc winpc>  <thu muc tam>
#  Ly do co bo thu nay: ban 20.11c chep thu muc bang cach doc NGUYEN tung tep vao bo nho -> goi VGA 700MB
#  lam bo cai trong WinPE het RAM (MemoryError). Bo thu do bo nho that su dung khi chep tep lon.
#  In ra:  "OK  ..." / "XX  ..." / ".. ghi chu"   (check.ps1 doc lai). Chay duoc tren ca Windows lan Linux.
# =====================================================================================================
import hashlib, os, shutil, stat, sys, tracemalloc

root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
tmp = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(root, "_sys_check_tmp")
sys.path.insert(0, os.path.join(root, "lib"))
import cbsys                                                        # noqa: E402

N = {"ok": 0, "xx": 0}
MB = 1 << 20


def ck(name, cond, extra=""):
    if cond: N["ok"] += 1; print("OK  " + name, flush=True)
    else: N["xx"] += 1; print("XX  " + name + ("   -> " + str(extra)[:300] if extra != "" else ""), flush=True)


def note(s): print(".. " + s, flush=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(MB)
            if not b: break
            h.update(b)
    return h.hexdigest()


def put(p, data=b"x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)


def big(p, mb):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        for _ in range(mb // 4): f.write(os.urandom(4 * MB))


def tree(d):
    out = {}
    for r, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, d).replace("/", "\\")] = os.path.getsize(p)
    return out


def peak_of(fn):
    tracemalloc.start()
    try: res = fn()
    finally:
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    return res, peak


note("cbsys %s ; Python %s ; khoi chep %s MB" % (cbsys.SYS_VER, sys.version.split()[0], getattr(cbsys, "COPY_BLOCK", 0) // MB or "?"))
shutil.rmtree(tmp, ignore_errors=True)
src, dst = os.path.join(tmp, "src"), os.path.join(tmp, "dst")
logs = []
s = cbsys.WinSys(log=lambda *a: logs.append(" ".join(str(x) for x in a)))

# ---- cay nguon giong thu muc cb\os cua bo cai: tep nho, tep rong, thu muc long nhau, 1 goi "VGA" 64MB
put(os.path.join(src, "provision.cmd"), b"@echo off\r\n")
put(os.path.join(src, "rong.txt"), b"")
put(os.path.join(src, "firstboot.d", "10 chung.cmd"), b"echo chung\r\n")
put(os.path.join(src, "firstboot.d", "22h2", "20-app.cmd"), b"echo 22h2\r\n")
put(os.path.join(src, "firstboot.d", "1511", "10-nvidia-vga.cmd"), b"echo vga\r\n")
big(os.path.join(src, "firstboot.d", "1511", "nvidia-vga-466.77.exe"), 64)
put(os.path.join(src, "firstboot.d", "cong-cu", "sau", "hon", "tool.bin"), os.urandom(70000))
BIG = os.path.join("firstboot.d", "1511", "nvidia-vga-466.77.exe")

# ---- 1. chep ca cay: dung tung byte, bo nho dung it
put(os.path.join(dst, "provision.cmd"), b"cu - chi doc")
os.chmod(os.path.join(dst, "provision.cmd"), stat.S_IREAD)
n, peak = peak_of(lambda: s.copy_tree(src, dst))
ck("copy_tree: chep du 7 tep, tra dung so tep", n == 7 and tree(dst) == tree(src), (n, tree(dst)))
ck("copy_tree: tep 64MB giong het ban goc (sha256)", sha(os.path.join(dst, BIG)) == sha(os.path.join(src, BIG)))
ck("copy_tree: chep tep 64MB chi dung duoi 16MB bo nho (truoc day doc nguyen tep -> het RAM trong WinPE)", peak < 16 * MB, "dinh %.1f MB" % (peak / MB))
note("bo nho dinh khi chep cay co tep 64MB: %.1f MB" % (peak / MB))
ck("copy_tree: ghi de duoc tep dich dang o che do chi-doc", open(os.path.join(dst, "provision.cmd"), "rb").read() == b"@echo off\r\n")
ck("copy_tree: tep rong + thu muc long nhau + ten co dau cach van chep dung", os.path.getsize(os.path.join(dst, "rong.txt")) == 0
   and sha(os.path.join(dst, "firstboot.d", "cong-cu", "sau", "hon", "tool.bin")) == sha(os.path.join(src, "firstboot.d", "cong-cu", "sau", "hon", "tool.bin"))
   and os.path.isfile(os.path.join(dst, "firstboot.d", "10 chung.cmd")))
ck("copy_tree: tep lon co in ten + dung luong (de biet may dang chep, khong phai treo)", any("nvidia-vga-466.77.exe" in ln and "67 MB" in ln for ln in logs), logs)
ck("copy_tree: tep nho khong in gi", not any("provision.cmd" in ln or "tool.bin" in ln for ln in logs), logs)

# ---- 2. bo thu muc con theo dieu kien (bo cai dung de KHONG chep goi cua ban Windows khac vao o C:)
dst2, seen = os.path.join(tmp, "dst2"), []
def skip(rel):
    seen.append(rel)
    return rel.lower() == "firstboot.d\\1511"
n2, peak2 = peak_of(lambda: s.copy_tree(src, dst2, skip))
ck("copy_tree(skip): bo dung thu muc firstboot.d\\1511, giu cac thu muc khac", n2 == 5 and sorted(tree(dst2)) == sorted(k for k in tree(src) if not k.lower().startswith("firstboot.d\\1511\\")), (n2, sorted(tree(dst2))))
ck("copy_tree(skip): duong dan dua cho ham loc dung dau \\ va tinh tu goc nguon", "firstboot.d" in seen and "firstboot.d\\1511" in seen and "firstboot.d\\cong-cu\\sau" in seen
   and not any("/" in x or x.startswith(".") for x in seen), seen)
ck("copy_tree(skip): thu muc bi bo thi khong di vao ben trong", not any(x.lower().startswith("firstboot.d\\1511\\") for x in seen), seen)

# ---- 3. copy_file (dung cho anh Windows vai GB)
out = os.path.join(tmp, "anh", "22h2.wim")
calls = []
put(out, b"cu"); os.chmod(out, stat.S_IREAD)
_, peak3 = peak_of(lambda: s.copy_file(os.path.join(src, BIG), out, show=lambda d, t, sp: calls.append((d, t))))
ck("copy_file: tep 64MB giong het ban goc, khong con tep .part", sha(out) == sha(os.path.join(src, BIG)) and not os.path.exists(out + ".part"))
ck("copy_file: dung duoi 32MB bo nho", peak3 < 32 * MB, "dinh %.1f MB" % (peak3 / MB))
ck("copy_file: co bao tien do, lan cuoi = 100%", bool(calls) and calls[-1][0] == calls[-1][1] == 64 * MB, calls[-3:])

# ---- 4. che do chay thu (dry) khong ghi gi
s.dry = True
dst4 = os.path.join(tmp, "dst4")
r4 = s.copy_tree(src, dst4); s.copy_file(os.path.join(src, BIG), os.path.join(dst4, "x.bin"))
s.dry = False
ck("che do chay thu: khong tao tep nao", r4 == 0 and not os.path.exists(dst4))

for d, _, fs in os.walk(tmp):
    for f in fs:
        try: os.chmod(os.path.join(d, f), stat.S_IWRITE | stat.S_IREAD)
        except OSError: pass
shutil.rmtree(tmp, ignore_errors=True)
note("xong: %d OK, %d XX" % (N["ok"], N["xx"]))
sys.exit(0)
