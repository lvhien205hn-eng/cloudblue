# -*- coding: utf-8 -*-
# =====================================================================================================
#  winpc/tests/ci/os_check.py   —   thu tren WINDOWS THAT cac ham ban 21.11a goi thang vao Windows (bo thu thuong dung lop gia):
#       cb_provision: thu mang (real_net), tim card NVIDIA trong registry (real_nvidia_state), cho mang (net_wait), tien do in ra cua so
#       provision.cmd: nhanh "firstlogon" phai de chu in ra man hinh, loi ghi vao provision.out
#       pcagent:      dat dong ho (SetSystemTime), huy hen tat may, hop thong bao, vga_pending
#       cb_pe:        chen dich vu khoi dong vao kho registry OFFLINE (reg load / add / unload that) + doc trang thai ban Windows + dat mui gio loi thi bo qua
#       ban ghost (21.11b): doc danh sach tai khoan (WMI), doi ten tai khoan (ADSI), thu mat khau trong (LogonUser), bo han mat khau (net accounts), doc registry Setup that
#    python os_check.py <thu muc cb cua bo cai, hoac thu muc winpc>  <thu muc tam>
#  In ra:  "OK  ..." / "XX  ..." / ".. ghi chu"   (check.ps1 doc lai). Chay duoc tren ca Windows lan Linux (tren Linux bo qua phan chi-Windows).
# =====================================================================================================
import json, os, shutil, subprocess, sys, time

root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
tmp = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(root, "_os_check_tmp")
for sub in ("lib", "os", "agent", "pe"): sys.path.insert(0, os.path.join(root, sub))
import cb_provision                                                 # noqa: E402
import pcagent                                                      # noqa: E402
import cbcore as C                                                  # noqa: E402
import cbsys                                                        # noqa: E402
import cb_pe                                                        # noqa: E402

WIN = os.name == "nt"
N = {"ok": 0, "xx": 0}


def ck(name, cond, extra=""):
    if cond: N["ok"] += 1; print("OK  " + name, flush=True)
    else: N["xx"] += 1; print("XX  " + name + ("   -> " + str(extra)[:300] if extra != "" else ""), flush=True)


def note(s): print(".. " + s, flush=True)


shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(os.path.join(tmp, "logs"))
note("cb_provision %s, pcagent %s, Python %s tren %s" % (cb_provision.PROV_VER, pcagent.AGENT_VER, sys.version.split()[0], sys.platform))

# ---- 1. thu mang that
t0 = time.time(); up = cb_provision.real_net("github.com", 443); t_up = time.time() - t0
t0 = time.time(); down = cb_provision.real_net("127.0.0.1", 9, 2); t_down = time.time() - t0
ck("real_net: toi duoc github.com:443 (may chay thu co mang)", up is True, "%.1f giay" % t_up)
ck("real_net: cong khong ai nghe -> False, khong treo qua han cho", down is False and t_down < 6, "%.1f giay" % t_down)
t0 = time.time(); bad = cb_provision.real_net("khong-co-ten-mien-nay.invalid", 443, 3); t_bad = time.time() - t0
ck("real_net: ten mien khong ton tai -> False, khong nem loi", bad is False, "%.1f giay" % t_bad)

# ---- 2. cho mang + noi thu lay tu cb.json
with open(os.path.join(tmp, "cb.json"), "w") as f: json.dump({"user": "PC", "password": "", "sb_url": "https://github.com"}, f)
said = []
p = cb_provision.Prov(tmp, run=lambda a, t=0: (0, ""), log=lambda m: None, spi=lambda x: True, admin=False, rec=lambda: "", say=said.append)
ck("net_target doc sb_url trong cb.json", p.net_target() == ("github.com", 443), p.net_target())
t0 = time.time(); w = p.net_wait(20); dt = time.time() - t0
ck("net_wait: may co mang -> tra ngay (khong ngoi cho)", w is not None and w <= 5 and dt < 12, (w, "%.1f giay" % dt))
with open(os.path.join(tmp, "cb.json"), "w") as f: json.dump({"sb_url": "https://127.0.0.1:9"}, f)
p2 = cb_provision.Prov(tmp, run=lambda a, t=0: (0, ""), log=lambda m: None, admin=False, rec=lambda: "", say=said.append)
t0 = time.time(); w2 = p2.net_wait(5); dt2 = time.time() - t0
ck("net_wait: khong toi duoc -> None sau dung han cho (khong cho vo han)", w2 is None and 4 <= dt2 < 30, (w2, "%.1f giay" % dt2))

# ---- 3. tim card NVIDIA trong registry
st = cb_provision.real_nvidia_state()
if WIN:
    ck("real_nvidia_state: doc duoc danh sach thiet bi PCI trong registry (tra dung / sai, khong phai 'khong biet')", st[0] in (True, False) and st[1] in (True, False), st)
    note("may chay thu: co card NVIDIA = %s, da co driver NVIDIA = %s" % st)
    with open(os.path.join(tmp, "cb.json"), "w") as f: json.dump({"sb_url": "https://github.com"}, f)
    os.makedirs(os.path.join(tmp, "os", "firstboot.d"))
    pack = os.path.join(tmp, "os", "firstboot.d", "466.77-notebook-win10-64bit-international-whql.exe")
    with open(pack, "wb") as f: f.write(b"khong phai bo cai that")
    ran, logs = [], []
    p3 = cb_provision.Prov(tmp, run=lambda a, t=0: (ran.append(list(a)), (0, ""))[1], log=logs.append, admin=True, rec=lambda: "", say=said.append)
    v = p3.vga(True)
    if st[0] is False:
        ck("vga(): may KHONG co card NVIDIA -> bo qua, khong chay bo cai, xoa ban chep goi", v == "skip" and not ran and not os.path.exists(pack), (v, ran, logs[-2:]))
    else:
        ck("vga(): may co card NVIDIA -> %s" % v, v in ("done", "fail"), (v, logs[-2:]))
else:
    ck("real_nvidia_state: khong phai Windows -> (None, None), khong nem loi", st == (None, None), st)

# ---- 4. provision.cmd: nhanh firstlogon de chu in ra man hinh, loi vao provision.out (chay that bang cmd.exe voi duong dan tam)
if WIN:
    fake = os.path.join(tmp, "CB")
    for sub in ("py", "os", "logs"): os.makedirs(os.path.join(fake, sub))
    with open(os.path.join(root, "os", "provision.cmd"), "rb") as f: cmd = f.read().decode("ascii")
    n_path = cmd.count("C:\\CloudBluePC")
    cmd = cmd.replace("C:\\CloudBluePC", fake).replace("ping -n 9 127.0.0.1", "ping -n 1 127.0.0.1")
    cmd = cmd.replace('"%s\\py\\python.exe"' % fake, '"%s"' % sys.executable)
    with open(os.path.join(fake, "os", "provision.cmd"), "wb") as f: f.write(cmd.encode("ascii"))
    with open(os.path.join(fake, "os", "cb_provision.py"), "w") as f:
        f.write("import sys\nprint('  TIEN-DO pha=' + (sys.argv[1] if len(sys.argv) > 1 else '?'), flush=True)\nsys.stderr.write('LOI-THU\\n')\n")
    out_file = os.path.join(fake, "logs", "provision.out")
    r1 = subprocess.run(["cmd.exe", "/c", os.path.join(fake, "os", "provision.cmd"), "firstlogon"], capture_output=True, timeout=120)
    o1 = (r1.stdout or b"").decode("ascii", "replace")
    f1 = open(out_file, "rb").read().decode("ascii", "replace") if os.path.exists(out_file) else ""
    ck("provision.cmd firstlogon: chu tien do DI RA man hinh (khong bi nuot vao file), ma thoat 0", r1.returncode == 0 and "TIEN-DO pha=firstlogon" in o1 and "TIEN-DO" not in f1, (r1.returncode, o1[-200:], f1[-100:]))
    ck("provision.cmd firstlogon: loi (stderr) van ghi vao provision.out", "LOI-THU" in f1 and "LOI-THU" not in o1, (f1[-200:], o1[-100:]))
    os.remove(out_file)
    r2 = subprocess.run(["cmd.exe", "/c", os.path.join(fake, "os", "provision.cmd"), "specialize"], capture_output=True, timeout=120)
    o2 = (r2.stdout or b"").decode("ascii", "replace")
    f2 = open(out_file, "rb").read().decode("ascii", "replace") if os.path.exists(out_file) else ""
    ck("provision.cmd cac pha khac (specialize...): moi thu ghi vao provision.out nhu cu, khong in ra man hinh", r2.returncode == 0 and "TIEN-DO pha=specialize" in f2 and "LOI-THU" in f2 and "TIEN-DO" not in o2, (r2.returncode, o2[-100:], f2[-200:]))
    ck("provision.cmd dung dung 1 duong dan goc C:\\CloudBluePC (bo thu thay duoc het)", n_path >= 4 and "C:\\CloudBluePC" not in cmd, n_path)

# ---- 5. agent: dat dong ho, huy hen tat may, hop thong bao
h = pcagent.WinHost()
if WIN:
    before = time.time()
    ok = h.set_clock(before)                                          # dat dung gio hien tai: goi that SetSystemTime ma khong lam lech dong ho may chay thu
    after = time.time()
    ck("WinHost.set_clock: Windows NHAN lenh dat gio (quyen quan tri), dong ho khong bi lech di", ok is True and abs(after - before) < 5, (ok, after - before))
    ck("WinHost.set_clock: gia tri vo ly -> False, khong nem loi", h.set_clock(-10 ** 12) is False)
    try: h.abort_shutdown(); a_ok = True
    except Exception as e: a_ok = repr(e)
    ck("WinHost.abort_shutdown: khong co lenh tat nao dang dem -> khong nem loi", a_ok is True, a_ok)
    try: h.notify("CloudBlue PC: thu hop thong bao (bo thu tu dong).", 5); n_ok = True
    except Exception as e: n_ok = repr(e)
    ck("WinHost.notify: goi msg.exe khong nem loi (ke ca khi may khong co ai dang nhap)", n_ok is True, n_ok)
    ip = h.lan_ip()
    ck("WinHost.lan_ip: may co mang -> co dia chi IP", bool(ip) and ip.count(".") == 3, ip)
else:
    ck("WinHost.set_clock tren may khong phai Windows -> False, khong nem loi", h.set_clock(time.time()) is False)
# ---- 6. bo cai: chen dich vu khoi dong vao kho registry OFFLINE cua "Windows vua bung" (kho that, lenh reg that, o dia gia bang subst)
def reg(*a):
    r = subprocess.run(["reg"] + list(a), capture_output=True, timeout=120)
    return r.returncode, ((r.stdout or b"") + (r.stderr or b"")).decode("mbcs" if WIN else "latin-1", "replace")


if WIN:
    wroot = os.path.join(tmp, "W")
    os.makedirs(os.path.join(wroot, "Windows", "System32", "config"))
    hive = os.path.join(wroot, "Windows", "System32", "config", "SYSTEM")
    rc0, o0 = reg("save", "HKLM\\SYSTEM\\Select", hive, "/y")                      # 1 kho registry nho, hop le (goc = noi dung khoa Select)
    drive = next((d for d in "QRTUVWYZ" if not os.path.exists(d + ":\\")), None)
    ok_subst = drive is not None and subprocess.run(["subst", drive + ":", wroot], capture_output=True).returncode == 0
    ck("(chuan bi) tao duoc kho registry thu + o dia gia", rc0 == 0 and os.path.getsize(hive) > 0 and ok_subst, (rc0, o0[-200:], drive))
    if rc0 == 0 and ok_subst:
        try:
            def shape(setup):                                                      # dung khoa Select + Setup ben trong kho thu
                assert reg("load", "HKLM\\CB_SHAPE", hive)[0] == 0
                try:
                    reg("add", "HKLM\\CB_SHAPE\\Select", "/v", "Default", "/t", "REG_DWORD", "/d", "1", "/f")
                    for k, t, v in setup: reg("add", "HKLM\\CB_SHAPE\\Setup", "/v", k, "/t", t, "/d", v, "/f")
                finally:
                    assert reg("unload", "HKLM\\CB_SHAPE")[0] == 0
            logs = []
            inst = cb_pe.Installer(cbsys.WinSys(log=logs.append))
            shape([("SystemSetupInProgress", "REG_DWORD", "0"), ("SetupType", "REG_DWORD", "0"), ("CmdLine", "REG_SZ", ""), ("OOBEInProgress", "REG_DWORD", "0")])
            inst.boot_hook(drive)
            with open(os.path.join(wroot, "CloudBluePC", "logs", "image.json"), encoding="utf-8") as f: ij = json.load(f)
            ck("boot_hook tren kho registry that (ban kieu ghost): doc dung trang thai, chen dich vu, canh bao", ij == {"oobe": False, "control_set": 1, "boot_svc": True}
               and any("kieu GHOST" in x for x in logs), (ij, logs[-4:]))
            ck("boot_hook nha kho registry sau khi xong (khong de kho bi giu)", reg("query", "HKLM\\CB_OFFSYS")[0] != 0)
            assert reg("load", "HKLM\\CB_CHK", hive)[0] == 0
            try:
                k = "HKLM\\CB_CHK\\ControlSet001\\Services\\" + C.BOOT_SVC
                rc1, o1 = reg("query", k)
                want = '%SystemRoot%\\System32\\cmd.exe /c start "" /b "C:\\CloudBluePC\\py\\pythonw.exe" -I -B "C:\\CloudBluePC\\os\\cb_provision.py" boot'
                ck("dich vu ghi vao kho: Start=2 (tu chay), Type=0x10, ErrorControl=0, chay bang LocalSystem", rc1 == 0 and all(x in o1.replace("\r", "") for x in ("Start    REG_DWORD    0x2", "Type    REG_DWORD    0x10", "ErrorControl    REG_DWORD    0x0",
                   "ObjectName    REG_SZ    LocalSystem")), o1[-600:])
                ck("ImagePath ghi DUNG TUNG KY TU (dau nhay kep long nhau + %SystemRoot% khong bi bien doi)", ("ImagePath    REG_EXPAND_SZ    " + want) in o1.replace("\r", ""), o1[-600:])
            finally:
                assert reg("unload", "HKLM\\CB_CHK")[0] == 0
            shape([("SystemSetupInProgress", "REG_DWORD", "1"), ("SetupType", "REG_DWORD", "2"), ("CmdLine", "REG_SZ", "oobe\\windeploy.exe"), ("OOBEInProgress", "REG_DWORD", "1")])
            logs.clear(); inst.boot_hook(drive)
            with open(os.path.join(wroot, "CloudBluePC", "logs", "image.json"), encoding="utf-8") as f: ij = json.load(f)
            ck("boot_hook (ban chuan, dang o trang thai cai dat lan dau): ghi nhan dung, khong canh bao nham", ij == {"oobe": True, "control_set": 1, "boot_svc": True} and not any("kieu GHOST" in x for x in logs), (ij, logs[-3:]))
            logs.clear(); inst.set_timezone(drive, {"timezone": "SE Asia Standard Time"})
            ck("set_timezone tren thu muc KHONG phai Windows that: dism bao loi -> ghi nhat ky 'bo qua', khong nem loi, don cho tam", any("mui gio SE Asia Standard Time" in x and "bo qua" in x for x in logs)
               and not os.path.exists(os.path.join(wroot, "cb-scratch")), logs[-3:])
        except Exception as e:
            ck("buoc 6 chay het khong nem loi", False, repr(e))
        finally:
            for kk in ("HKLM\\CB_OFFSYS", "HKLM\\CB_SHAPE", "HKLM\\CB_CHK"): reg("unload", kk)
            subprocess.run(["subst", drive + ":", "/d"], capture_output=True)

# ---- 7. ban Windows kieu GHOST (21.11b): cac lenh that dung de nhan tai khoan co san lam tai khoan khach. KHONG doi ten may, KHONG dung toi tai khoan dang chay thu.
if WIN:
    import secrets as _sec
    pg = cb_provision.Prov(tmp, log=lambda m: None, admin=True, rec=lambda: "", say=said.append)
    live = pg.setup_live()
    ck("setup_live: Windows dang chay binh thuong -> False (khong o buoc cai dat lan dau)", live is False, live)
    us = pg.local_users()
    ck("local_users: doc duoc danh sach tai khoan cuc bo qua WMI, co tai khoan Administrator co san (so 500)", isinstance(us, list) and any(u["rid"] == 500 for u in us) and all(u["name"] for u in us),
       None if us is None else [(u["name"], u["rid"], u["off"]) for u in us][:8])
    adm, usr, bia = pg.names()
    ck("names: ten nhom quan tri / nhom Users / tai khoan Administrator lay theo so hieu (khong phu thuoc ngon ngu)", adm and usr and bia and any(u["name"].lower() == bia.lower() and u["rid"] == 500 for u in (us or [])), (adm, usr, bia))
    wl = pg.reg_value(r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "Shell")
    ck("reg_value: doc 1 gia tri registry (Winlogon\\Shell = explorer.exe)", wl.lower().startswith("explorer"), wl)
    ck("reg_value: gia tri khong co -> chuoi rong, khong nem loi", pg.reg_value(r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon", "KhongCoGiaTriNay") == "")
    old, new, pw1 = "cbg" + _sec.token_hex(3), "cbk" + _sec.token_hex(3), "Cb1!" + _sec.token_urlsafe(8)[:10]
    run = lambda *a: subprocess.run(list(a), capture_output=True, text=True)
    made = run("net", "user", old, pw1, "/add").returncode == 0
    if not made: note("khong tao duoc tai khoan thu (khong phai quyen quan tri?) - bo qua phan doi ten tai khoan")
    else:
        try:
            run("net", "localgroup", adm, old, "/add")
            u2 = pg.local_users() or []
            mine = next((u for u in u2 if u["name"].lower() == old), None)
            ck("tai khoan vua tao hien trong local_users: so hieu >= 1000, dang bat", mine is not None and mine["rid"] >= 1000 and mine["off"] is False, mine)
            ck("pick_ghost_user: goi y dung ten tai khoan do -> chon no de nhan", cb_provision.pick_ghost_user(u2, [".\\" + old], new) == (mine["name"], "adopt") if mine else False)
            ck("real_blank_pw: tai khoan dang co mat khau -> False", cb_provision.real_blank_pw(old) is False, cb_provision.real_blank_pw(old))
            ok = pg.rename_user(old, new)
            u3 = pg.local_users() or []
            got = next((u for u in u3 if u["name"].lower() == new), None)
            ck("rename_user (ADSI): doi ten tai khoan THAT, giu nguyen so hieu (= giu ho so), ten cu khong con", ok and got is not None and mine is not None and got["rid"] == mine["rid"] and not any(u["name"].lower() == old for u in u3), (ok, got))
            ck("tai khoan sau khi doi ten van nam trong nhom quan tri (Windows theo doi bang so hieu, khong theo ten)", pg.in_group(adm, new) or any(m.lower().endswith(new) for m in (pg.admin_members(adm) or [])), pg.admin_members(adm))
            r0 = run("net", "user", new, "")
            if r0.returncode == 0:
                b = cb_provision.real_blank_pw(new)
                ck("real_blank_pw: dat mat khau trong xong -> True (ke ca khi Windows chi cho tai khoan mat khau trong dang nhap tai may)", b is True, b)
            else: note("may chay thu khong cho dat mat khau trong (chinh sach mat khau) - bo qua phep thu mat khau trong: " + (r0.stderr or r0.stdout).strip()[:120])
            ck("tat tai khoan + go khoi nhom quan tri bang dung lenh ban ghost dung", pg.sh(["net", "user", new, "/active:no"]) and run("net", "localgroup", adm, new, "/delete").returncode == 0
               and next(u for u in (pg.local_users() or []) if u["name"].lower() == new)["off"] is True)
        except Exception as e:
            ck("buoc 7 (tai khoan) chay het khong nem loi", False, repr(e))
        finally:
            for n in (old, new): run("net", "user", n, "/delete")
        ck("don xong tai khoan thu", not any(u["name"].lower() in (old, new) for u in (pg.local_users() or [])))
    okp = pg.pw_never_expires()
    acc = run("net", "accounts").stdout
    ck("pw_never_expires: 'net accounts /maxpwage:unlimited' chay duoc + dat moc pwage.done", okp and os.path.isfile(os.path.join(tmp, "logs", "pwage.done")), acc[-300:])
    note("net accounts sau khi dat: " + " | ".join(x.strip() for x in acc.splitlines() if "age" in x.lower())[:200])
    ck("seed_name: chi nhan ten may hop le", pg.seed_name() == "" and (open(os.path.join(tmp, "seed.json"), "w").write('{"name": "CB-E3B72F"}') or True) and pg.seed_name() == "CB-E3B72F"
       and (open(os.path.join(tmp, "seed.json"), "w").write('{"name": "ten co dau cach"}') or True) and pg.seed_name() == "")
    ck("rename_pc: ten trung ten may hien tai -> khong lam gi (khong doi ten may chay thu)", pg.rename_pc(os.environ.get("COMPUTERNAME", "")) is False)

# ---- 8. SO MAY (21.11b): ghi so may ra man hinh nen chung + lam sach chu nguoi cai go
_pub = os.path.join(tmp, "public"); _old_pub = os.environ.get("PUBLIC"); os.environ["PUBLIC"] = _pub
try:
    wh = pcagent.WinHost.__new__(pcagent.WinHost)
    r1 = wh.show_code("14-85"); f1 = sorted(os.listdir(os.path.join(_pub, "Desktop")))
    with open(os.path.join(_pub, "Desktop", f1[0]), "rb") as f: raw1 = f.read()
    r2 = wh.show_code("A07"); f2 = sorted(os.listdir(os.path.join(_pub, "Desktop")))
    r3 = wh.show_code(""); f3 = sorted(os.listdir(os.path.join(_pub, "Desktop")))
    ck("show_code: tao file 'May so 14-85 (CloudBlue).txt' (UTF-8 co BOM de Notepad cu doc dung dau)", r1 and f1 == ["May so 14-85 (CloudBlue).txt"] and raw1[:3] == b"\xef\xbb\xbf" and b"14-85" in raw1, f1)
    ck("show_code: doi so may -> thay file; xoa so may -> go file", r2 and f2 == ["May so A07 (CloudBlue).txt"] and r3 and f3 == [], (f2, f3))
finally:
    if _old_pub is None: os.environ.pop("PUBLIC", None)
    else: os.environ["PUBLIC"] = _old_pub
ck("clean_code: lam sach so may nguoi cai go", C.clean_code("  a07 <khu 2> ") == "A07 KHU 2" and C.clean_code("") == "")
if WIN:
    note("thu muc man hinh nen chung that cua may chay thu: " + os.path.join(os.environ.get("PUBLIC", "?"), "Desktop") + (" (co)" if os.path.isdir(os.path.join(os.environ.get("PUBLIC", ""), "Desktop")) else " (KHONG co)"))

with open(os.path.join(tmp, "logs", "vga.json"), "w") as f: f.write('{"state": "wait", "tries": 0}')
ck("pcagent.vga_pending doc logs\\vga.json", pcagent.vga_pending(tmp) is True)
ck("dong tien do la chu khong dau (in duoc tren moi cua so lenh)", all(isinstance(x, str) and x.isascii() for x in said), said[:3])

shutil.rmtree(tmp, ignore_errors=True)
print(".. os_check: %d dat, %d khong dat" % (N["ok"], N["xx"]), flush=True)
sys.exit(0)
