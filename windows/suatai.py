# -*- coding: utf-8 -*-
r"""suatai.py — sửa lỗi khách MuMu KHÔNG TẢI ĐƯỢC FILE (09/11/2026).

Canh gác (baomat.py) dọn "thư mục chia sẻ" của MuMu mỗi 2 giây và dời LUÔN CÁC THƯ MỤC CON vào kho cách ly — trong đó
có thư mục mà MuMu dùng làm /sdcard/Download của máy khách → Android báo "No such file or directory", Chrome tải file
0 KB rồi báo lỗi. Lệnh này:
  1) tắt dọn thư mục chia sẻ (BAOMAT_SHARE=0 trong cloudphone.conf) + tắt canh gác;
  2) dựng lại các THƯ MỤC đã bị dời (chỉ thư mục rỗng — file của khách vẫn nằm trong kho cách ly, không trả ra);
  3) bật lại canh gác (vẫn chặn clipboard + mạng nhà như cũ);
  4) thử ghi file vào /sdcard/Download của từng máy;
  5) ghi cấu trúc thư mục chia sẻ (tên thư mục cấp 1 + số đếm, không tên file) + khoá cấu hình MuMu có chữ share/download.
Kết quả in ra màn hình và ghi vào suatai.txt cùng thư mục.
"""
import glob, importlib.util, json, os, re, subprocess, sys

B = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BM = os.path.join(B, "baomat.py")
CONF = os.path.join(B, "cloudphone.conf")
ADB = os.path.join(B, "platform-tools", "adb.exe")
NOWIN = 0x08000000 if os.name == "nt" else 0
OUT = []
PFX = re.compile(r"^\d{6}_\d+_")          # baomat đặt tên "HHMMSS_i_<tên>" khi trong kho đã có mục cùng tên


def say(s=""):
    OUT.append(s)
    try: print(s, flush=True)
    except Exception: pass


def run(args, timeout=120):
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NOWIN)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"{e.__class__.__name__}: {e}"


def share_off():
    """Thêm BAOMAT_SHARE=0 vào cuối cloudphone.conf (baomat đọc dòng CUỐI cùng tên). Không đụng các dòng khác."""
    cur = None
    try:
        for ln in open(CONF, encoding="utf-8-sig", errors="replace"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln and ln.split("=", 1)[0].strip() == "BAOMAT_SHARE":
                cur = ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    if cur != "0":
        with open(CONF, "ab") as f: f.write(b"\r\nBAOMAT_SHARE=0\r\n")
    return cur == "0"


def load_bm():
    spec = importlib.util.spec_from_file_location("baomat_suatai", BM)
    bm = importlib.util.module_from_spec(spec); spec.loader.exec_module(bm)
    return bm


def restore(bm):
    """Dựng lại cây THƯ MỤC (không file) từ kho cách ly về đúng thư mục chia sẻ gốc. Trả (số thư mục dựng, số file còn trong kho, số thư mục chia sẻ)."""
    shares = bm.share_dirs()
    made = kept = 0
    for p, _kind in shares:
        tag = bm._tag(p)
        for r in sorted({bm.CACH, bm._cach_root(p)}):
            try: days = sorted(d for d in os.listdir(r) if re.fullmatch(r"\d{8}", d))
            except OSError: continue
            for d in days:
                q = os.path.join(r, d, tag)
                try: tops = os.listdir(q)
                except OSError: continue
                for top in tops:
                    src = os.path.join(q, top)
                    if os.path.islink(src) or not os.path.isdir(src):
                        kept += 1; continue
                    base = os.path.join(p, PFX.sub("", top))
                    for root, ds, fs in os.walk(src):
                        kept += len(fs)
                        rel = os.path.relpath(root, src)
                        dst = base if rel == "." else os.path.join(base, rel)
                        if not os.path.isdir(dst):
                            try: os.makedirs(dst); made += 1
                            except OSError: pass
    return made, kept, shares


def write_test():
    devs = [ln.split()[0] for ln in run([ADB, "devices"], 30).splitlines()[1:] if ln.strip().endswith("device")]
    ok = 0
    for dv in devs:
        o = run([ADB, "-s", dv, "shell", "(echo x > /sdcard/Download/.br_t && echo GHI_FILE_OK) 2>&1 | tail -n 1; rm -f /sdcard/Download/.br_t"], 30).strip()
        good = "GHI_FILE_OK" in o; ok += good
        say(f"   {dv}: {'✓ ghi file được' if good else '✗ ' + (o.splitlines() or ['?'])[-1][-110:]}")
    return ok, len(devs)


def info(bm, shares):
    for p, kind in shares:
        try: es = list(os.scandir(p))
        except OSError: es = []
        ds = sorted(e.name for e in es if e.is_dir()); nf = sum(1 for e in es if e.is_file())
        say(f"   [{kind}] {p}: {len(ds)} thư mục, {nf} file")
        for n in ds[:15]:
            try: sub = len(os.listdir(os.path.join(p, n)))
            except OSError: sub = -1
            say(f"      - {n} ({sub} mục)")
        if len(ds) > 15: say(f"      … và {len(ds) - 15} thư mục khác")
    md = bm._mumu_dir()
    say(f"   MuMu cài ở: {md or 'không thấy'}")
    roots = [md] if md else []
    roots += [os.path.join(u, "AppData", "Roaming", "Netease") for u in bm._users()]
    keys, files = {}, 0
    for r0 in [r for r in roots if r and os.path.isdir(r)]:
        for root, dirs, fs in os.walk(r0):
            if root[len(r0):].count(os.sep) >= 6: dirs[:] = []
            for f in fs:
                fl = f.lower()
                if not (fl.endswith(".json") and ("config" in fl or "setting" in fl)): continue
                fp = os.path.join(root, f); files += 1
                if files > 1200: break
                try:
                    if os.path.getsize(fp) > 2_000_000: continue
                    j = json.load(open(fp, encoding="utf-8-sig", errors="replace"))
                except Exception: continue
                st = [("", j)]
                while st:
                    k, v = st.pop()
                    if isinstance(v, dict): st += list(v.items())
                    elif isinstance(v, list): st += [(k, x) for x in v]
                    elif "share" in str(k).lower() or "download" in str(k).lower():
                        e = keys.setdefault(str(k), [set(), set()]); e[0].add(str(v)[:120]); e[1].add(os.path.relpath(os.path.dirname(fp), r0))
    if not keys: say("   (không thấy khoá cấu hình MuMu có chữ share/download)")
    for k in sorted(keys)[:25]:
        vs, fd = keys[k]
        say(f"   khoá {k} = {' | '.join(sorted(vs)[:3])}{' …' if len(vs) > 3 else ''}  ({len(vs)} giá trị khác nhau · ở {len(fd)} thư mục cấu hình, vd {sorted(fd)[0]})")


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    had = share_off()
    say("1) Tắt dọn thư mục chia sẻ: BAOMAT_SHARE=0 " + ("(đã có sẵn)" if had else "(đã thêm vào cloudphone.conf)"))
    say("   " + (run([PY, BM, "tatgac"], 150).strip().splitlines() or ["?"])[-1])
    bm = load_bm()
    made, kept, shares = restore(bm)
    say(f"2) Dựng lại {made} thư mục trong {len(shares)} thư mục chia sẻ · file của khách vẫn nằm trong kho cách ly ({kept} mục), không trả ra")
    say("3) Canh gác: " + (run([PY, BM, "start"], 60).strip().splitlines() or ["?"])[-1] + " · vẫn chặn clipboard + mạng nhà như cũ")
    say("4) Thử ghi file vào /sdcard/Download của từng máy:")
    ok, n = write_test()
    say(f"   → {ok}/{n} máy ghi được" + ("" if ok == n else " · máy còn ✗: khởi động lại máy đó (lúc vắng khách) rồi thử lại"))
    say("5) Thư mục chia sẻ + cấu hình MuMu (để làm bản sửa tận gốc):")
    info(bm, shares)
    try:
        with open(os.path.join(B, "suatai.txt"), "w", encoding="utf-8") as f: f.write("\n".join(OUT) + "\n")
    except OSError: pass


if __name__ == "__main__":
    main()
