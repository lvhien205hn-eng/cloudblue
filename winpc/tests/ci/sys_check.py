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

# ---- 5. duong dan theo TEN VOLUME (Volume{GUID}) - bo cai 21.11d ghi ket qua lenh cai lai len phan vung cuu ho bang kieu duong dan nay
#         (chu o cua phan vung cuu ho bi doi giua chung: ban <= 21.11c tinh duong dan theo chu o cu -> "No such file ... job-result.json.tmp")
if os.name == "nt":
    import json
    vols = s.volumes()
    drv = os.path.splitdrive(tmp)[0][:1].upper()
    v5 = next((v for v in vols if drv in v.letters), None)
    ck("tim duoc volume cua o dang chay thu + ten volume dung dang Volume{GUID}", v5 is not None and v5.path.startswith("\\\\?\\Volume{") and v5.path.endswith("}\\"), (drv, [(x.letters, x.path) for x in vols][:6]))
    if v5 is not None:
        rel5 = os.path.splitdrive(os.path.join(tmp, "theo-ten-volume"))[1].lstrip("\\")
        gp = v5.path + rel5 + "\\cb\\job-result.json"
        os.makedirs(os.path.join(tmp, "theo-ten-volume", "cb"))                  # nhu phan vung cuu ho: thu muc cb da co san
        try:
            s.write_text(gp, json.dumps({"id": 77, "ok": True}))
            e1 = s.exists(gp); t1 = s.read_text(gp)
            s.write_text(gp, json.dumps({"id": 78, "ok": False}))            # ghi de (di qua tep tam .tmp + doi ten)
            t2 = s.read_text(gp)
            same = open(os.path.join(tmp, "theo-ten-volume", "cb", "job-result.json"), encoding="utf-8").read()
            s.remove(gp); e2 = s.exists(gp)
            ck("WinSys ghi / doc / ghi de / xoa tep qua duong dan ten volume (kieu bo cai dung cho job-result.json)", e1 and json.loads(t1)["id"] == 77 and json.loads(t2)["id"] == 78 and same == t2 and not e2
               and not os.path.exists(os.path.join(tmp, "theo-ten-volume", "cb", "job-result.json.tmp")), (e1, t1, t2, e2))
        except Exception as e:
            ck("WinSys ghi / doc / ghi de / xoa tep qua duong dan ten volume (kieu bo cai dung cho job-result.json)", False, repr(e))

# ---- 6. bo cai trong boot.wim GOI TIEP 1 bo cai MOI HON nam tren phan vung cuu ho (cb/pe-next) - chay bang python that, dung cach goi that
#         (nho co che nay, sua loi bo cai khong can tao lai ISO roi di cai lai tung may: agent tu cap nhat qua mang va dat ban moi len phan vung cuu ho)
if os.name == "nt":
    import json
    sys.path.insert(0, os.path.join(root, "pe"))
    try:
        import cb_pe
        rec6 = os.path.join(tmp, "rec6"); x6 = os.path.join(tmp, "x6"); out6 = os.path.join(tmp, "chain-out.json"); rc6 = os.path.join(tmp, "chain-rc.txt")
        new_main = ("import json, os, sys\n"
                    "HERE = os.path.dirname(os.path.abspath(__file__))\n"
                    "sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', 'lib')))\n"
                    "import cbnew\n"
                    "json.dump({'argv': sys.argv[1:], 'here': HERE, 'lib': cbnew.MARK, 'chained': os.environ.get('CB_CHAINED'), 'base': os.environ.get('CB_CHAIN_BASE'),\n"
                    "           'flags': [sys.flags.isolated, sys.flags.dont_write_bytecode]}, open(%r, 'w'))\n"
                    "print('   (bo cai moi gia lap dang chay)', flush=True)\n"
                    "sys.exit(int(open(%r).read()))\n" % (out6, rc6)).encode("utf-8")
        files6 = {"pe/cb_pe.py": new_main, "lib/cbnew.py": b"MARK = 'thu vien cua ban moi'\n"}
        for rel, data in files6.items(): put(os.path.join(rec6, "cb", "pe-next", *rel.split("/")), data)
        put(os.path.join(rec6, "cb", "pe-next", "next.json"), json.dumps({"seq": cb_pe.PE_SEQ + 1, "ver": "thu-ci", "files": {r: hashlib.sha256(d).hexdigest() for r, d in files6.items()}}).encode())

        class Rec6:
            root = rec6 + "\\"
            def p(self, rel): return self.root + rel

        def chain6(code):
            put(rc6, str(code).encode())
            if os.path.exists(out6): os.remove(out6)
            old_sd = os.environ.get("SystemDrive")
            os.environ["SystemDrive"] = x6                               # o tam (trong WinPE la X:) -> thu muc thu
            try:
                inst = cb_pe.Installer(cbsys.WinSys(log=lambda *a: None))
                r = inst.chain([Rec6()])
            finally:
                if old_sd is None: os.environ.pop("SystemDrive", None)
                else: os.environ["SystemDrive"] = old_sd
            return r, (json.load(open(out6)) if os.path.exists(out6) else None), inst.lines

        r, o, lg = chain6(0)
        ck("goi tiep bo cai moi: python that chay dung ban chep sang o tam (…\\cb-next\\pe\\cb_pe.py --chained), ban moi nap duoc thu vien rieng cua no", r == 0 and o is not None and o["argv"] == ["--chained"]
           and os.path.normcase(o["here"]) == os.path.normcase(os.path.join(x6, "cb-next", "pe")) and o["lib"] == "thu vien cua ban moi", (r, o, lg[-2:]))
        ck("goi tiep bo cai moi: dung co cach ly cua Python (-I -B) + bao cho ban moi biet ban goc so may / nam o dau", o is not None and o["flags"] == [1, 1] and o["chained"] == str(cb_pe.PE_SEQ)
           and os.path.normcase(o["base"] or "") == os.path.normcase(os.path.abspath(root)), o)
        r, o, lg = chain6(10)
        ck("ban moi tra ma 10 -> bo cai goc coi la xong (tra 10)", r == 10 and o is not None, (r, lg[-2:]))
        r, o, lg = chain6(5)
        ck("ban moi chet giua chung (ma 5) -> bo cai goc nhan ra, tu lam tiep (tra None), co ghi nhat ky", r is None and o is not None and any("khong lam xong (ma thoat 5)" in x for x in lg), (r, lg[-2:]))
        put(os.path.join(rec6, "cb", "pe-next", "lib", "cbnew.py"), b"MARK = 'bi sua'\n")
        r, o, lg = chain6(0)
        ck("1 tep cua ban moi bi sua (sai ma bam) -> KHONG chay ban moi", r is None and o is None and any("sai ma bam" in x for x in lg), (r, o, lg[-2:]))
    except Exception as e:
        import traceback
        ck("goi tiep bo cai moi (cb/pe-next) chay duoc", False, traceback.format_exc()[-600:])

# ---- 7. AGENT dat bo cai ban moi len phan vung cuu ho (cb/pe-next) bang WinSys that, qua duong dan TEN VOLUME (phan vung cuu ho khong co chu o)
#         + bo cai that (cb_pe.next_installer) doc lai dung ban do -> sua bo cai khong can tao lai ISO (21.11e)
if os.name == "nt":
    import json
    try:
        sys.path.insert(0, os.path.join(root, "pe")); sys.path.insert(0, os.path.join(root, "agent"))
        import cb_pe, pcagent
        v7 = next((v for v in s.volumes() if os.path.splitdrive(tmp)[0][:1].upper() in v.letters), None)
        ag7, rec7 = os.path.join(tmp, "agent7"), os.path.join(tmp, "rec7")
        os.makedirs(os.path.join(rec7, "cb"))
        files7 = {"pe/cb_pe.py": ('# bo cai thu\nPE_VER = "thu-ci"\nPE_SEQ = %d\n' % (cb_pe.PE_SEQ + 1)).encode(), "lib/cbcore.py": b"# core\n", "lib/cbrec.py": b"# rec\n", "lib/cbsys.py": b"# sys\n"}
        for rel, data in files7.items(): put(os.path.join(ag7, *rel.split("/")), data)

        class Rec7:
            root = v7.path + os.path.splitdrive(rec7)[1].lstrip("\\") + "\\"
            def p(self, rel): return self.root + rel

        lg7 = []
        a7 = pcagent.Agent(cbsys.WinSys(log=lambda *a: None), None, None, ag7, lg7.append)
        seq7 = a7.pe_next(Rec7())
        nx7 = os.path.join(rec7, "cb", "pe-next")
        def rd7(rel): return open(os.path.join(nx7, *rel.split("/")), "rb").read()
        ck("agent dat bo cai len phan vung cuu ho qua duong dan ten volume: du 4 tep + next.json, dung so thu tu + ma bam", seq7 == cb_pe.PE_SEQ + 1 and all(rd7(r) == d for r, d in files7.items())
           and json.loads(rd7("next.json")) == {"seq": seq7, "ver": "thu-ci", "files": {r: hashlib.sha256(d).hexdigest() for r, d in files7.items()}}, (seq7, lg7[-2:]))
        seen7 = cb_pe.Installer(cbsys.WinSys(log=lambda *a: None)).next_installer(Rec7())
        ck("bo cai THAT trong WinPE doc lai ban agent vua dat: nhan ban so moi hon, du tep, dung ma bam (se goi tiep ban nay)", seen7 is not None and seen7[0] == seq7 and seen7[2] == files7, seen7 and seen7[:2])
        st7 = os.stat(os.path.join(nx7, "next.json")).st_mtime_ns
        a7b = pcagent.Agent(cbsys.WinSys(log=lambda *a: None), None, None, ag7, lg7.append)
        ck("agent chay lai, ban da dat dung roi -> khong ghi lai", a7b.pe_next(Rec7()) == seq7 and os.stat(os.path.join(nx7, "next.json")).st_mtime_ns == st7)
        put(os.path.join(ag7, "pe", "cb_pe.py"), b"# bo cai cu, chua co so thu tu\n")
        r7 = pcagent.Agent(cbsys.WinSys(log=lambda *a: None), None, None, ag7, lg7.append).pe_next(Rec7())
        ck("quay ve bo cai cu (chua co so thu tu) -> go next.json, bo cai trong WinPE khong goi ban nao nua", r7 is None and not os.path.exists(os.path.join(nx7, "next.json"))
           and cb_pe.Installer(cbsys.WinSys(log=lambda *a: None)).next_installer(Rec7()) is None, (r7, lg7[-2:]))
    except Exception:
        import traceback
        ck("agent dat bo cai len phan vung cuu ho (cb/pe-next) chay duoc", False, traceback.format_exc()[-600:])

for d, _, fs in os.walk(tmp):
    for f in fs:
        try: os.chmod(os.path.join(d, f), stat.S_IWRITE | stat.S_IREAD)
        except OSError: pass
shutil.rmtree(tmp, ignore_errors=True)
note("xong: %d OK, %d XX" % (N["ok"], N["xx"]))
sys.exit(0)
