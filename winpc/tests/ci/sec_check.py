# -*- coding: utf-8 -*-
"""Chạy trên máy Windows thử của GitHub Actions (quyền Admin, máy dùng 1 lần rồi huỷ) — thử THẬT phần bảo mật của máy cho thuê:
     1. dựng C:\\CloudBluePC y như bộ cài làm, khoá quyền bằng đúng các lệnh icacls của cbcore / cb_provision
     2. tạo 1 ổ ảo NTFS không chữ ổ (đóng vai phân vùng cứu hộ), khoá gốc ổ qua đường \\\\?\\Volume{…}\\
     3. tạo 1 TÀI KHOẢN THƯỜNG thật rồi cho nó thử đọc / ghi / xoá từng chỗ — TRƯỚC khi khoá (phải làm được: chứng minh lỗ hổng có thật và phép thử nhạy)
        và SAU khi khoá (phải bị chặn, trừ đọc + chạy py\\ và os\\)
     4. hạ 1 tài khoản khách thật từ Admin xuống tài khoản thường bằng cb_provision.harden()
   Dùng:  python sec_check.py <thư mục cb của cây bộ cài> <thư mục tạm>
   In ra từng dòng:  OK <tên>  |  XX <tên> -> <chi tiết>  |  .. <ghi chú>      (check.ps1 đọc các dòng này)"""
import json, os, re, secrets, shutil, subprocess, sys, time

CB, TMP = sys.argv[1], sys.argv[2]
BASE = r"C:\CloudBluePC"
OUT = os.path.join(TMP, "secout")
KEY = "cbpc_" + "c" * 40


def sh(argv, timeout=300):
    try:
        r = subprocess.run(argv, capture_output=True, timeout=timeout)
        return r.returncode, ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
    except Exception as e:
        return 127, repr(e)


def ck(name, cond, extra=""):
    print(("OK  " if cond else "XX  ") + name + ("" if cond else "   -> " + str(extra).replace("\r", " ").replace("\n", " | ")[:700]), flush=True)
    return bool(cond)


def info(t): print(".. " + str(t).replace("\r", " ").replace("\n", " | ")[:900], flush=True)


def pw(): return "Cb1!" + secrets.token_urlsafe(8)[:10]


PROBE = r'''
import ctypes, json, os, subprocess, sys
def rd(p):
    try:
        with open(p, "rb") as f: f.read(16)
        return True
    except OSError: return False
def wr(p):
    try:
        with open(p, "ab") as f: f.write(b"x")
        return True
    except OSError: return False
def ls(p):
    try: os.listdir(p); return True
    except OSError: return False
def rm(p):
    try: os.remove(p); return True
    except OSError: return False
res = {}
for name, kind, path in json.load(open(sys.argv[1], encoding="utf-8")):
    res[name] = {"r": rd, "w": wr, "l": ls, "d": rm}[kind](path)
res["_user"] = os.environ.get("USERNAME", "")
try: res["_admin"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
except Exception: res["_admin"] = None
if len(sys.argv) > 3 and sys.argv[3] == "logon":            # chạy đúng lệnh mà Windows chạy lúc tài khoản thường đăng nhập
    try:
        r = subprocess.run(["cmd.exe", "/c", r"C:\CloudBluePC\os\provision.cmd", "logon"], capture_output=True, timeout=180)
        res["_prov_rc"] = r.returncode
    except Exception as e:
        res["_prov_rc"] = repr(e)
    la = os.environ.get("LOCALAPPDATA", "")
    res["_prov_out"] = os.path.isfile(os.path.join(la, "CloudBluePC", "provision.out")) if la else False
    try: res["_prov_log"] = open(os.path.join(la, "CloudBluePC", "provision.log"), encoding="utf-8").read()[-400:]
    except OSError: res["_prov_log"] = ""
with open(sys.argv[2], "w", encoding="utf-8") as f: json.dump(res, f)
'''


def grant_batch(user):
    """Cho tài khoản quyền 'Log on as a batch job' (để tác vụ theo lịch chạy được bằng tài khoản thường). True nếu secedit báo xong."""
    rc, out = sh(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                  "(New-Object System.Security.Principal.NTAccount('%s')).Translate([System.Security.Principal.SecurityIdentifier]).Value" % user], 120)
    sid = (out or "").strip().splitlines()[-1].strip() if (out or "").strip() else ""
    if not sid.startswith("S-1-5-21-"): return False
    inf, db = os.path.join(TMP, "ur.inf"), os.path.join(TMP, "ur.sdb")
    sh(["secedit", "/export", "/cfg", inf, "/areas", "USER_RIGHTS"], 180)
    try:
        with open(inf, encoding="utf-16") as f: txt = f.read()
    except Exception:
        return False
    if re.search(r"(?m)^SeBatchLogonRight\s*=", txt): txt = re.sub(r"(?m)^(SeBatchLogonRight\s*=.*)$", lambda m: m.group(1).rstrip() + ",*" + sid, txt)
    else: txt = txt.replace("[Privilege Rights]", "[Privilege Rights]\nSeBatchLogonRight = *" + sid)
    with open(inf, "w", encoding="utf-16") as f: f.write(txt)
    return sh(["secedit", "/configure", "/db", db, "/cfg", inf, "/areas", "USER_RIGHTS"], 300)[0] == 0


def run_as(user, password, checks, tag, extra="", high=False):
    """Chạy probe.py bằng tài khoản `user` (tác vụ theo lịch có lưu mật khẩu; không được thì Start-Process -Credential). Trả kết quả (dict) hoặc None."""
    cj, rj = os.path.join(OUT, tag + "-in.json"), os.path.join(OUT, tag + "-out.json")
    with open(cj, "w", encoding="utf-8") as f: json.dump(checks, f)
    if os.path.exists(rj): os.remove(rj)
    py = os.path.join(BASE, "py", "python.exe")
    cmdline = '"%s" -I -B "%s" "%s" "%s"%s' % (py, os.path.join(OUT, "probe.py"), cj, rj, (" " + extra) if extra else "")
    tn = "cbsec-" + tag
    rc, out = sh(["schtasks", "/create", "/tn", tn, "/tr", cmdline, "/sc", "once", "/st", "23:59", "/ru", user, "/rp", password, "/f"] + (["/rl", "HIGHEST"] if high else []))
    how = "tac vu theo lich"
    if rc == 0:
        sh(["schtasks", "/run", "/tn", tn])
        for _ in range(90):
            if os.path.exists(rj): break
            time.sleep(1)
        if not os.path.exists(rj):
            rcq, outq = sh(["schtasks", "/query", "/tn", tn, "/v", "/fo", "list"])
            info("tac vu %s khong ra ket qua: %s" % (tn, " ".join(l.strip() for l in outq.splitlines() if "Result" in l or "Status" in l)))
        sh(["schtasks", "/delete", "/tn", tn, "/f"])
    else:
        info("schtasks /create loi: " + out)
    if not os.path.exists(rj) and not high:                     # cách 2 (không nâng quyền được → bỏ, để phép thử báo đúng là chưa chạy được)
        how = "Start-Process -Credential"
        ps = ("$p = ConvertTo-SecureString '%s' -AsPlainText -Force; $c = New-Object System.Management.Automation.PSCredential('.\\%s', $p); "
              "Start-Process -FilePath '%s' -ArgumentList '-I','-B','\"%s\"','\"%s\"','\"%s\"'%s -Credential $c -WorkingDirectory '%s' -WindowStyle Hidden -Wait"
              % (password, user, py, os.path.join(OUT, "probe.py"), cj, rj, (",'%s'" % extra) if extra else "", OUT))
        rc, out = sh(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], 240)
        if rc != 0: info("Start-Process -Credential loi: " + out[-300:])
    if not os.path.exists(rj): return None
    try:
        with open(rj, encoding="utf-8") as f: res = json.load(f)
    except Exception as e:
        info("doc ket qua loi: %r" % (e,)); return None
    res["_how"] = how
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    sh(["icacls", OUT, "/grant", "*S-1-1-0:(OI)(CI)F"])          # thư mục kết quả: ai cũng ghi được
    with open(os.path.join(OUT, "probe.py"), "w", encoding="utf-8") as f: f.write(PROBE)

    # ---- 1. dựng C:\CloudBluePC như bộ cài làm
    if os.path.exists(BASE): shutil.rmtree(BASE, ignore_errors=True)
    for sub in ("os", "agent", "lib", "py"): shutil.copytree(os.path.join(CB, sub), os.path.join(BASE, sub))
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "os", "firstboot.d"), exist_ok=True)
    files = {"identity.json": json.dumps({"id": "may-thu", "token": "BI-MAT-MA-MAY"}), "seed.json": json.dumps({"enroll_key": KEY}),
             "logs\\agent.log": "nhat ky", "os\\firstboot.d\\10-khoa.cmd": "rem khoa ban quyen cua chu shop"}
    for rel, txt in files.items():
        with open(os.path.join(BASE, rel), "w", encoding="utf-8") as f: f.write(txt)
    sys.path.insert(0, os.path.join(BASE, "lib")); sys.path.insert(0, os.path.join(BASE, "os"))
    import cbcore, cb_provision
    info("ban: cbcore %s · cb_provision %s · Python %s" % (cbcore.CORE_VER, cb_provision.PROV_VER, sys.version.split()[0]))

    # ---- 2. ổ ảo NTFS không chữ ổ = phân vùng cứu hộ
    vhd = os.path.join(TMP, "cuuho.vhd")
    dp = os.path.join(TMP, "dp.txt")
    with open(dp, "w") as f: f.write('create vdisk file="%s" maximum=120 type=expandable\nattach vdisk\ncreate partition primary\nformat fs=ntfs quick label=CBRECTEST\n' % vhd)
    rc, out = sh(["diskpart", "/s", dp], 300)
    rc2, vp = sh(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "(Get-Volume | Where-Object { $_.FileSystemLabel -eq 'CBRECTEST' } | Select-Object -First 1).Path"], 120)
    vol = (vp or "").strip().splitlines()[-1].strip() if (vp or "").strip() else ""
    have_vol = vol.startswith("\\\\?\\Volume{") and vol.endswith("\\")
    ck("tao duoc o ao NTFS khong chu o (dong vai phan vung cuu ho)", have_vol, "diskpart ma %s: %s | duong dan: %r" % (rc, out[-200:], vol))
    if have_vol:
        os.makedirs(vol + "cb", exist_ok=True)
        with open(vol + "cb\\job.json", "w") as f: f.write(json.dumps({"ticket": "VE-BI-MAT"}))
        with open(vol + "cb\\pe.py", "w") as f: f.write("# bo cai chay quyen SYSTEM")
        info("quyen mac dinh cua goc o NTFS moi: " + " ; ".join(l.strip() for l in sh(["icacls", vol])[1].splitlines()[:6]))
    info("quyen mac dinh cua C:\\CloudBluePC (thua huong tu C:\\): " + " ; ".join(l.strip() for l in sh(["icacls", BASE])[1].splitlines()[:7]))

    # ---- 3. tài khoản thường thật
    user, upw = "cbthuong", pw()
    sh(["net", "user", user, "/delete"])
    rc, out = sh(["net", "user", user, upw, "/add"])
    ck("tao duoc tai khoan thuong de thu", rc == 0, out)
    info("cap quyen chay tac vu theo lich cho tai khoan thu: %s" % grant_batch(user))
    checks = [["doc_ma_may", "r", BASE + "\\identity.json"], ["doc_ma_dang_ky", "r", BASE + "\\seed.json"], ["liet_ke_goc", "l", BASE],
              ["doc_agent", "r", BASE + "\\agent\\pcagent.py"], ["doc_lib", "r", BASE + "\\lib\\cbcore.py"], ["doc_nhat_ky", "r", BASE + "\\logs\\agent.log"],
              ["doc_script_chu_shop", "r", BASE + "\\os\\firstboot.d\\10-khoa.cmd"], ["doc_os", "r", BASE + "\\os\\cb_provision.py"],
              ["doc_py", "r", BASE + "\\py\\python.exe"], ["ghi_os", "w", BASE + "\\os\\cay.txt"], ["ghi_py", "w", BASE + "\\py\\cay.txt"],
              ["sua_provision", "w", BASE + "\\os\\cb_provision.py"], ["sua_agent", "w", BASE + "\\agent\\pcagent.py"], ["ghi_goc", "w", BASE + "\\cay.txt"]]
    if have_vol: checks += [["doc_cuu_ho", "r", vol + "cb\\job.json"], ["sua_bo_cai_cuu_ho", "w", vol + "cb\\pe.py"], ["ghi_cuu_ho", "w", vol + "cb\\cay.txt"]]
    before = run_as(user, upw, checks, "truoc")
    if before is None:
        ck("chay duoc lenh bang tai khoan thuong (de thu that)", False, "ca 2 cach deu khong chay duoc - chi con soat danh sach quyen")
    else:
        info("chay bang tai khoan thuong qua: %s (USERNAME=%s, co quyen quan tri=%s)" % (before.get("_how"), before.get("_user"), before.get("_admin")))
        ck("phep thu dung la tai khoan THUONG", before.get("_user", "").lower() == user and before.get("_admin") is False, before)
        hole = [k for k in ("doc_ma_may", "doc_ma_dang_ky", "sua_agent", "sua_provision", "ghi_goc") if before.get(k)]
        info("TRUOC khi khoa, tai khoan thuong lam duoc: " + ", ".join(k for k, v in before.items() if v is True and not k.startswith("_")))
        ck("TRUOC khi khoa: tai khoan thuong doc duoc ma may / ma dang ky va SUA duoc file agent (lo hong co that, phep thu nhay)", len(hole) == 5, before)
        if have_vol: ck("TRUOC khi khoa: tai khoan thuong DOC duoc phan vung cuu ho va TAO duoc file moi trong do (qua duong \\\\?\\Volume)", before.get("doc_cuu_ho") and before.get("ghi_cuu_ho"), before)
    # KHÔNG dọn các file cay.txt tài khoản thường vừa tạo (nó đang là chủ sở hữu): sau khi khoá nó phải mất quyền với cả các file đó

    # ---- khoá bằng đúng mã của bộ cài: cb_provision.lockdown() (thư mục) + cbcore.acl_vol_cmds (phân vùng cứu hộ)
    with open(os.path.join(BASE, "cb.json"), "w") as f: json.dump({"user": "cbkhach", "password": ""}, f)
    P = cb_provision.Prov(BASE, rec=lambda: vol if have_vol else "")
    ck("is_admin() nhan ra dang co quyen quan tri", P.is_admin() is True)
    ok = P.lockdown()
    ck("cb_provision.lockdown(): moi lenh icacls deu xong + dat moc lock.done", ok and os.path.isfile(os.path.join(BASE, "logs", "lock.done")), P.lines[-4:])
    acl_root = sh(["icacls", BASE])[1]
    acl_os = sh(["icacls", os.path.join(BASE, "os")])[1]
    acl_fb = sh(["icacls", os.path.join(BASE, "os", "firstboot.d")])[1]
    info("quyen SAU khi khoa - goc: " + " ; ".join(l.strip() for l in acl_root.splitlines()[:5]))
    info("quyen SAU khi khoa - os: " + " ; ".join(l.strip() for l in acl_os.splitlines()[:5]))
    weak = ("Authenticated Users", "BUILTIN\\Users", "Everyone", "INTERACTIVE")
    ck("goc C:\\CloudBluePC: khong con dong quyen nao cho Users / Authenticated Users / Everyone", not any(w in acl_root for w in weak) and "NT AUTHORITY\\SYSTEM" in acl_root, acl_root)
    ck("os\\: Users chi co quyen doc + chay (RX), khong co quyen ghi", "BUILTIN\\Users:(OI)(CI)(RX)" in acl_os and "Authenticated Users" not in acl_os and "(M)" not in acl_os.split("BUILTIN\\Users")[-1].split("\n")[0], acl_os)
    ck("os\\firstboot.d: khong co Users", not any(w in acl_fb for w in weak), acl_fb)
    if have_vol:
        acl_vol = sh(["icacls", vol])[1]
        info("quyen SAU khi khoa - goc phan vung cuu ho: " + " ; ".join(l.strip() for l in acl_vol.splitlines()[:5]))
        ck("goc phan vung cuu ho (duong \\\\?\\Volume): chi con SYSTEM + Administrators", not any(w in acl_vol for w in weak) and "BUILTIN\\Administrators" in acl_vol, acl_vol)
    after = run_as(user, upw, checks, "sau", "logon")
    if after is None:
        ck("chay lai bang tai khoan thuong SAU khi khoa", False, "khong chay duoc")
    else:
        deny = ["doc_ma_may", "doc_ma_dang_ky", "liet_ke_goc", "doc_agent", "doc_lib", "doc_nhat_ky", "doc_script_chu_shop", "ghi_os", "ghi_py", "sua_provision", "sua_agent", "ghi_goc"]
        ck("SAU khi khoa: tai khoan thuong KHONG doc duoc ma may, ma dang ky, agent, lib, nhat ky, script cua chu shop; KHONG ghi / sua duoc gi",
           all(after.get(k) is False for k in deny), {k: after.get(k) for k in deny})
        ck("SAU khi khoa: tai khoan thuong VAN doc duoc os\\cb_provision.py va chay duoc py\\python.exe (de dat anh nen luc dang nhap)", after.get("doc_os") is True and after.get("doc_py") is True, after)
        if have_vol: ck("SAU khi khoa: tai khoan thuong KHONG doc / sua / ghi duoc phan vung cuu ho (ke ca file chinh no tao truoc do)", after.get("doc_cuu_ho") is False and after.get("sua_bo_cai_cuu_ho") is False and after.get("ghi_cuu_ho") is False,
                        {k: after.get(k) for k in ("doc_cuu_ho", "sua_bo_cai_cuu_ho", "ghi_cuu_ho")})
        ck("tai khoan thuong chay provision.cmd logon (lenh luc dang nhap): chay duoc, nhat ky chuyen sang ho so nguoi dung", after.get("_prov_rc") == 0 and after.get("_prov_out") is True, {k: v for k, v in after.items() if k.startswith("_")})
        info("nhat ky pha logon cua tai khoan thuong: " + str(after.get("_prov_log")))

    # ---- 4. hạ quyền tài khoản khách thật (tài khoản Administrator có sẵn được thay bằng 1 tài khoản thế vai để không khoá chính máy chạy thử)
    adm, usr, bia = P.names()
    info("ten nhom theo may nay (hoi bang SID): Administrators=%r Users=%r tai khoan Administrator co san=%r" % (adm, usr, bia))
    ck("names(): hoi duoc ten nhom + tai khoan co san bang PowerShell", bool(adm and usr and bia) and adm.lower().startswith("admin"), (adm, usr, bia))
    for u in ("cbkhach", "cbadm0"):
        sh(["net", "user", u, "/delete"]); sh(["net", "user", u, pw(), "/add"])
    sh(["net", "localgroup", adm, "cbkhach", "/add"])
    ck("chuan bi: tai khoan khach dang la Admin", P.in_group(adm, "cbkhach"))
    P.names = lambda: (adm, usr, "cbadm0")
    P.lines.clear()
    changed = P.harden()
    u_out, a_out = sh(["net", "user", "cbkhach"])[1], sh(["net", "user", "cbadm0"])[1]
    yn = lambda txt, label: next((l.split(label)[-1].strip() for l in txt.splitlines() if l.startswith(label)), "?")
    ck("harden(): go tai khoan khach khoi nhom Administrators, van o nhom Users", changed is True and not P.in_group(adm, "cbkhach") and P.in_group(usr, "cbkhach"), P.lines)
    ck("harden(): tai khoan khach khong tu doi duoc mat khau", yn(u_out, "User may change password") == "No", u_out[-400:])
    ck("harden(): tai khoan the vai Administrator bi tat + dat moc harden.done", yn(a_out, "Account active") == "No" and os.path.isfile(os.path.join(BASE, "logs", "harden.done")), a_out[-400:])
    ck("nhat ky khong chua mat khau", not any("Cb1!" in l for l in P.lines), P.lines)
    ck("harden() lan 2: khong con gi de doi", P.harden() is False)

    # ---- 4b. 21.11h: shop BẬT "Cho khách quyền Admin" (cb.json user_admin) → harden() cấp quyền Admin; guard() chặn RIÊNG tài khoản khách sửa / xoá phần mềm shop
    with open(os.path.join(BASE, "cb.json"), "w") as f: json.dump({"user": "cbkhach", "password": "", "user_admin": True}, f)
    P.lines.clear()
    P.harden()
    ck("user_admin: harden() dua tai khoan khach VAO nhom Administrators + dat moc admin.granted", P.in_group(adm, "cbkhach") and os.path.isfile(os.path.join(BASE, "logs", "admin.granted")), P.lines)
    ck("user_admin: harden() lan 2 khong doi gi, khach van la Admin", P.harden() is False and P.in_group(adm, "cbkhach"), P.lines[-3:])
    ok_g = P.guard()
    acl_g = sh(["icacls", BASE])[1]
    deny_l = [l.strip() for l in acl_g.splitlines() if "cbkhach" in l.lower()]
    info("quyen goc sau guard(): " + " ; ".join(l.strip() for l in acl_g.splitlines()[:6]))
    ck("guard(): C:\\CloudBluePC co dong TU CHOI rieng cho tai khoan khach; SYSTEM + Administrators van Full",
       ok_g and any("(DENY)" in l for l in deny_l) and "NT AUTHORITY\\SYSTEM:(OI)(CI)(F)" in acl_g and "BUILTIN\\Administrators:(OI)(CI)(F)" in acl_g, (P.lines[-2:], acl_g))
    if have_vol:
        acl_gv = sh(["icacls", vol])[1]
        ck("guard(): goc phan vung cuu ho cung co dong TU CHOI rieng cho tai khoan khach", any("cbkhach" in l.lower() and "(DENY)" in l for l in acl_gv.splitlines()), acl_gv)
    kpw = pw(); sh(["net", "user", "cbkhach", kpw])
    hi = run_as("cbkhach", kpw, [["doc_ma_may", "r", BASE + "\\identity.json"], ["sua_agent", "w", BASE + "\\agent\\pcagent.py"], ["sua_provision", "w", BASE + "\\os\\cb_provision.py"],
                                 ["ghi_goc", "w", BASE + "\\cay2.txt"], ["xoa_agent", "d", BASE + "\\agent\\pcagent.py"]], "admin-khach", "", True)
    if hi is None:
        ck("tai khoan khach co quyen Admin chay duoc phep thu o che do NANG QUYEN (tac vu theo lich /rl HIGHEST)", False, "khong chay duoc")
    else:
        info("khach Admin (nang quyen) lam duoc: " + ", ".join(k for k, v in hi.items() if v is True and not k.startswith("_")) + " | _admin=%s" % hi.get("_admin"))
        ck("khach CO quyen Admin that (tien trinh nang quyen) nhung KHONG sua / ghi / xoa duoc agent + script cua shop (bi dong TU CHOI chan)",
           hi.get("_admin") is True and all(hi.get(k) is False for k in ("sua_agent", "sua_provision", "ghi_goc", "xoa_agent")), hi)
    with open(os.path.join(BASE, "cb.json"), "w") as f: json.dump({"user": "cbkhach", "password": ""}, f)
    P.lines.clear()
    ck("shop TAT cong tac: harden() ha khach ve tai khoan thuong, KHONG bao nham vi pham bao mat",
       P.harden() is True and not P.in_group(adm, "cbkhach") and not any("VIEC LA" in l for l in P.lines) and not os.path.isfile(os.path.join(BASE, "logs", "sec.event"))
       and not os.path.isfile(os.path.join(BASE, "logs", "admin.granted")), P.lines)

    # ---- dọn (máy thử dùng 1 lần, dọn cho gọn)
    for u in ("cbthuong", "cbkhach", "cbadm0"): sh(["net", "user", u, "/delete"])
    with open(dp, "w") as f: f.write('select vdisk file="%s"\ndetach vdisk\n' % vhd)
    sh(["diskpart", "/s", dp], 120)
    shutil.rmtree(BASE, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:
        import traceback
        print("XX  sec_check loi khong ngo   -> " + traceback.format_exc().replace("\n", " | ")[-900:], flush=True)
        sys.exit(0)
