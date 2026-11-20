# -*- coding: utf-8 -*-
"""Máy Windows GIẢ cho bộ thử: ổ đĩa, phân vùng, volume, tệp, diskpart (bộ thông dịch nhỏ), dism / bcdboot / bcdedit.
   Cùng các hàm với cbsys.WinSys → chạy NGUYÊN mã cb_pe.py / cb_stage.py / pcagent.py trên Linux."""
import os, re, sys, uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import cbsys                                                            # noqa: E402
from cbsys import GPT_DATA, GPT_ESP, GPT_MSR, Disk, Part, Vol          # noqa: E402

MB = 1024 * 1024
GB = 1024 * MB


class FVol:
    def __init__(self, fs="", label="", kind=3):
        self.guid = "\\\\?\\Volume{%s}\\" % uuid.uuid4()
        self.fs, self.label, self.kind, self.letter = fs, label, kind, None
        self.files, self.dirs = {}, set()

    def put(self, rel, data=b"x"):
        rel = rel.strip("\\").lower()
        self.files[rel] = data
        parts = rel.split("\\")
        for i in range(1, len(parts)): self.dirs.add("\\".join(parts[:i]))


class FPart:
    def __init__(self, offset, size, type, attrs=0, active=False, vol=None):
        self.offset, self.size, self.type, self.attrs, self.active, self.vol = offset, size, type, attrs, active, vol


class FDisk:
    def __init__(self, index, size_gb, bus=11, removable=False, model="DISK", serial=None, ssd=None, style="raw"):
        self.index, self.size, self.bus, self.removable, self.model, self.ssd, self.style = index, int(size_gb * GB), bus, removable, model, ssd, style
        self.serial = serial or "SN%04d" % index
        self.slots = []

    def add(self, size_mb, type, fs="", label="", letter=None, attrs=0, active=False, files=None, offset=None):
        """Thêm phân vùng (theo thứ tự tạo = số phân vùng). size_mb=0 → hết phần còn lại."""
        end = max([MB] + [p.offset + p.size for p in self.slots])
        off = offset if offset is not None else end
        tail = self.size - (2 * MB if self.style == "gpt" else MB)
        size = size_mb * MB if size_mb else tail - off
        vol = None if type == GPT_MSR else FVol(fs, label)
        if vol and letter: vol.letter = letter
        for rel, data in (files or {}).items(): vol.put(rel, data)
        p = FPart(off, size, type, attrs, active, vol)
        self.slots.append(p)
        return p


class FakeSys:
    dry = False

    def __init__(self, fw="uefi"):
        self.fw = fw
        self.fdisks, self.cds = [], []                 # cds: volume không nằm trên ổ cứng (đĩa CD / ISO ảo)
        self.x = FVol("NTFS", "Boot"); self.x.letter = "X"
        self.logs, self.cmds, self.dp_scripts, self.bcd = [], [], [], {}
        self.keys, self.prompts = [], []
        self.clock, self.rebooted = 1_800_000_000.0, False
        self.fail_dism = self.fail_shrink = self.fail_bcdboot = False
        self.late = []                                 # volume chỉ hiện sau khi gọi wpeinit (USB lên chậm)
        self.sel_disk = self.sel_part = None

    # ---------------------------------------------------------------- dựng máy
    def disk(self, *a, **k):
        d = FDisk(*a, **k); self.fdisks.append(d); return d

    def cd(self, label="CB", letter="D", files=None):
        v = FVol("UDF", label, kind=5); v.letter = letter
        for rel, data in (files or {}).items(): v.put(rel, data)
        self.cds.append(v); return v

    # ---------------------------------------------------------------- giống WinSys
    def log(self, *a): self.logs.append(" ".join(str(x) for x in a))
    def firmware(self): return self.fw
    def now(self): return self.clock
    def sleep(self, s): self.clock += s
    def reboot(self): self.rebooted = True

    def key_wait(self, seconds):
        self.clock += seconds
        return self.keys.pop(0) if self.keys else None

    def _allvols(self):
        out = [(None, None, self.x)]
        for d in self.fdisks:
            for p in d.slots:
                if p.vol is not None: out.append((d, p, p.vol))
        for v in self.cds: out.append((None, None, v))
        return out

    def disks(self):
        out = []
        for d in self.fdisks:
            parts = [Part(i + 1, p.offset, p.size, p.type, attrs=p.attrs, active=p.active) for i, p in enumerate(d.slots)]
            parts.sort(key=lambda p: p.offset)
            out.append(Disk(d.index, d.size, d.bus, d.removable, d.model, d.serial, d.ssd, d.style if d.slots or d.style != "raw" else "raw", parts, "sig%d" % d.index))
        return out

    def volumes(self):
        out = []
        for d, p, v in self._allvols():
            if v is self.x: continue
            out.append(Vol(v.guid, [v.letter] if v.letter else [], v.fs, v.label, v.kind, d.index if d else None, p.offset if p else 0, p.size if p else 0))
        return out

    def used_letters(self): return {v.letter for _, _, v in self._allvols() if v.letter}

    def mount(self, vol_path, letter):
        if letter in self.used_letters(): return False
        for _, _, v in self._allvols():
            if v.guid == (vol_path if vol_path.endswith("\\") else vol_path + "\\"): v.letter = letter; return True
        return False

    def unmount(self, letter):
        for _, _, v in self._allvols():
            if v.letter == letter: v.letter = None; return True
        return False

    def free_bytes(self, root):
        v, _ = self._res(root)
        return 500 * GB if v else 0

    def nt_device(self, vol_path):
        n = 0
        for d in self.fdisks:
            for p in d.slots:
                n += 1
                if p.vol and p.vol.guid == vol_path: return "\\Device\\HarddiskVolume%d" % n
        return ""

    def read_bytes(self, p):
        v, rel = self._res(p)
        if not v or rel not in v.files: raise FileNotFoundError(p)
        d = v.files[rel]
        return d if isinstance(d, bytes) else d.encode("utf-8")

    def write_bytes(self, p, b):
        v, rel = self._need_fs(p); v.put(rel, bytes(b))

    # ---------------------------------------------------------------- tệp
    def _res(self, path):
        """đường dẫn → (volume, đường tương đối chữ thường) hoặc (None, None)"""
        p = path.replace("/", "\\")
        m = re.match(r"^(\\\\\?\\Volume\{[0-9a-fA-F-]+\}\\)(.*)$", p)
        if m:
            for _, _, v in self._allvols():
                if v.guid.lower() == m.group(1).lower(): return v, m.group(2).strip("\\").lower()
            return None, None
        m = re.match(r"^([A-Za-z]):\\?(.*)$", p)
        if m:
            for _, _, v in self._allvols():
                if v.letter == m.group(1).upper(): return v, m.group(2).strip("\\").lower()
        return None, None

    def exists(self, p):
        v, rel = self._res(p)
        return bool(v) and v.fs != "" and (rel == "" or rel in v.files or rel in v.dirs)

    def isdir(self, p):
        v, rel = self._res(p)
        return bool(v) and v.fs != "" and (rel == "" or rel in v.dirs)

    def listdir(self, p):
        v, rel = self._res(p)
        if not v: return []
        pre = (rel + "\\") if rel else ""
        return sorted({k[len(pre):].split("\\")[0] for k in list(v.files) + list(v.dirs) if k.startswith(pre) and k != rel})

    def size(self, p):
        v, rel = self._res(p)
        return len(v.files[rel]) if v and rel in v.files else 0

    def read_text(self, p):
        v, rel = self._res(p)
        if not v or rel not in v.files: raise FileNotFoundError(p)
        d = v.files[rel]
        return d.decode("utf-8-sig") if isinstance(d, bytes) else d

    def _need_fs(self, p):
        v, rel = self._res(p)
        if not v or v.fs == "": raise OSError("khong ghi duoc: " + p)
        if v.fs in ("UDF", "CDFS"): raise OSError("dia chi doc: " + p)
        return v, rel

    def write_text(self, p, s, encoding="utf-8"):
        v, rel = self._need_fs(p); v.put(rel, s)

    def makedirs(self, p):
        v, rel = self._need_fs(p)
        parts = rel.split("\\")
        for i in range(1, len(parts) + 1): v.dirs.add("\\".join(parts[:i]))

    def remove(self, p):
        v, rel = self._res(p)
        if v: v.files.pop(rel, None)

    def rename(self, a, b):
        va, ra = self._res(a); vb, rb = self._need_fs(b)
        vb.put(rb, va.files.pop(ra))

    def copy_file(self, src, dst, show=None):
        vs, rs = self._res(src)
        if not vs or rs not in vs.files: raise FileNotFoundError(src)
        vd, rd = self._need_fs(dst); vd.put(rd, vs.files[rs])
        if show: show(1, 1, 1)

    def copy_tree(self, src, dst, skip=None):
        vs, rs = self._res(src)
        if not vs: return 0
        vd, rd = self._need_fs(dst)
        n = 0
        for k, data in list(vs.files.items()):
            if k.startswith(rs + "\\"):
                dirs = k[len(rs) + 1:].split("\\")[:-1]
                if skip and any(skip("\\".join(dirs[:i + 1])) for i in range(len(dirs))): continue
                vd.put(rd + k[len(rs):], data); n += 1
        return n

    # ---------------------------------------------------------------- lệnh
    def run(self, argv, timeout=3600, show=False, input=None, change=True):
        self.cmds.append(list(argv))
        exe = os.path.basename(argv[0].replace("\\", "/")).lower().replace(".exe", "")
        if exe == "wpeinit":
            for v in self.late: self.cds.append(v)
            self.late = []
            return 0, ""
        if exe == "dism":
            a = {x.split(":", 1)[0].lower(): x.split(":", 1)[1] for x in argv[1:] if x.startswith("/") and ":" in x}
            if "/Apply-Image" in argv:
                if self.fail_dism: return 5, "Error: 5"
                if not self.exists(a["/imagefile"]): return 2, "Error: 2 khong thay file"
                v, rel = self._res(a["/applydir"])
                if not v or v.fs != "NTFS": return 3, "Error: 3 o dich khong hop le"
                v.put("windows\\system32\\config\\system", b"hive")
                v.put("windows\\system32\\bcdboot.exe", b"exe")
                v.put("windows\\cb-image.txt", "%s|%s" % (a["/imagefile"].split("\\")[-1].lower(), a["/index"]))
                return 0, ""
            return 0, ""
        if exe == "bcdboot":
            if self.fail_bcdboot: return 1, "BFSVC Error"
            vw, _ = self._res(argv[1]); s_letter = argv[3][0]
            fw = argv[5].lower()
            if not self.exists(argv[1] + "\\System32\\config\\SYSTEM"): return 1, "khong thay Windows"
            store = ("%s:\\EFI\\Microsoft\\Boot\\BCD" if fw == "uefi" else "%s:\\Boot\\BCD") % s_letter
            try: self.write_text(store, "bcd")
            except OSError: return 1, "khong ghi duoc phan vung khoi dong"
            self.bcd[store.lower()] = {"default": "windows@" + vw.guid, "entries": {}, "made": self.clock}
            return 0, ""
        if exe == "bcdedit":
            a = list(argv[1:]); key = "(system)"
            if a and a[0] == "/store":
                key = a[1].lower(); a = a[2:]
                if not self.exists(argv[2]): return 1, "khong mo duoc kho BCD"
            st = self.bcd.setdefault(key, {"default": "windows", "entries": {}})
            if a[0] == "/delete":
                return (0, "") if st["entries"].pop(a[1], None) is not None else (1, "khong co muc nay")
            if a[0] == "/create":
                if a[1] in st["entries"]: return 1, "da co"
                st["entries"][a[1]] = {"kind": a[-1] if a[-1] == "/device" else a[-1]}; return 0, ""
            if a[0] == "/set":
                if a[1] not in st["entries"]: return 1, "khong co muc"
                st["entries"][a[1]][a[2]] = a[3]; return 0, ""
            if a[0] in ("/default", "/bootsequence", "/timeout", "/displayorder"):
                st[a[0][1:]] = a[1]; return 0, ""
            return 0, ""
        if exe in ("shutdown", "wpeutil"):
            self.rebooted = True; return 0, ""
        return 0, ""

    # ---------------------------------------------------------------- diskpart
    def _free(self, d):
        lo, hi = MB, d.size - (2 * MB if d.style == "gpt" else MB)
        out, cur = [], lo
        for p in sorted(d.slots, key=lambda p: p.offset):
            if p.offset > cur: out.append((cur, p.offset - cur))
            cur = max(cur, p.offset + p.size)
        if hi > cur: out.append((cur, hi - cur))
        return out

    def diskpart(self, lines):
        self.dp_scripts.append(list(lines))
        for raw in lines:
            ln = raw.strip()
            noerr = ln.lower().endswith(" noerr")
            if noerr: ln = ln[:-6].strip()
            err = self._dp(ln)
            if err and not noerr: return 1, "DiskPart: %s  (dong: %s)" % (err, raw)
        return 0, ""

    def _dp(self, ln):
        t = ln.split(); low = ln.lower()
        kv = {m.group(1).lower(): m.group(2).strip('"') for m in re.finditer(r'(\w+)=("[^"]*"|\S+)', ln)}
        d, p = self.sel_disk, self.sel_part
        if low.startswith("select disk"):
            self.sel_disk = next((x for x in self.fdisks if x.index == int(t[2])), None); self.sel_part = None
            return None if self.sel_disk else "khong co o nay"
        if low.startswith("select volume"):
            for dd in self.fdisks:
                for pp in dd.slots:
                    if pp.vol and pp.vol.letter == t[2].upper().rstrip(":"): self.sel_disk, self.sel_part = dd, pp; return None
            return "khong co volume nay"
        if low in ("online disk", "attributes disk clear readonly", "exit", "rescan"): return None if d or low in ("exit", "rescan") else "chua chon o"
        if d is None: return "chua chon o"
        if low.startswith("select partition"):
            n = int(t[2])
            if not 1 <= n <= len(d.slots): return "khong co phan vung %d" % n
            self.sel_part = d.slots[n - 1]; return None
        if low == "clean":
            d.slots, d.style, self.sel_part = [], "raw", None; return None
        if low.startswith("convert "):
            if d.slots: return "o chua trong"
            d.style = t[1].lower(); return None
        if low.startswith("create partition"):
            kind = t[2].lower()
            if d.style == "raw": d.style = "mbr"
            if kind in ("efi", "msr") and d.style != "gpt": return "chi GPT moi co %s" % kind
            if d.style == "mbr" and len(d.slots) >= 4: return "MBR da du 4 phan vung"
            size = int(kv["size"]) * MB if "size" in kv else 0
            free = self._free(d)
            if "offset" in kv:
                off = int(kv["offset"]) * 1024
                ext = next(((s, n) for s, n in free if s <= off and off + max(size, MB) <= s + n), None)
                if not ext: return "vi tri khong trong"
                if not size: size = ext[0] + ext[1] - off
            else:
                ext = next(((s, n) for s, n in free if n >= max(size, MB)), None)
                if not ext: return "khong du cho trong"
                off = ext[0]
                if not size: size = ext[1]
            typ = {"efi": GPT_ESP, "msr": GPT_MSR}.get(kind, GPT_DATA if d.style == "gpt" else 0x07)
            np_ = FPart(off, size, typ, vol=None if kind == "msr" else FVol())
            d.slots.append(np_); self.sel_part = np_; return None
        if p is None: return "chua chon phan vung"
        if low.startswith("format"):
            if p.vol is None: return "phan vung khong co volume"
            p.vol.fs, p.vol.label, p.vol.files, p.vol.dirs = kv.get("fs", "ntfs").upper(), kv.get("label", ""), {}, set(); return None
        if low.startswith("assign"):
            if p.vol is None: return "khong co volume"
            L = kv.get("letter", "").upper()
            if L in self.used_letters() and p.vol.letter != L: return "chu o %s dang duoc dung" % L
            p.vol.letter = L; return None
        if low.startswith("remove"):
            if p.vol is None or not p.vol.letter: return "khong co chu o"
            p.vol.letter = None; return None
        if low == "active":
            if d.style != "mbr": return "chi MBR"
            for q in d.slots: q.active = False
            p.active = True; return None
        if low.startswith("delete partition"):
            if "override" not in low and (p.type in (GPT_ESP, GPT_MSR) or p.attrs & 1): return "can override"
            d.slots.remove(p); self.sel_part = None; return None
        if low.startswith("set id="):
            if d.style != "mbr": return "chi MBR"
            p.type = int(kv["id"], 16)
            if p.type == 0x27 and p.vol: p.vol.letter = None
            return None
        if low.startswith("gpt attributes="):
            if d.style != "gpt": return "chi GPT"
            p.attrs = int(kv["attributes"], 16); return None
        if low.startswith("shrink"):
            if self.fail_shrink: return "khong thu nho duoc"
            want = int(kv["desired"]) * MB
            if want >= p.size - 20 * GB: return "khong du cho"
            p.size -= want; return None
        return "lenh la: " + ln

    # ---------------------------------------------------------------- tiện cho bộ thử
    def part_of(self, letter):
        for d in self.fdisks:
            for i, p in enumerate(d.slots):
                if p.vol and p.vol.letter == letter: return d, i + 1, p
        return None, None, None

    def vol_labeled(self, label):
        return next((v for _, _, v in self._allvols() if v.label == label), None)

    def file(self, letter_or_vol, rel):
        v = letter_or_vol if isinstance(letter_or_vol, FVol) else next((x for _, _, x in self._allvols() if x.letter == letter_or_vol), None)
        if v is None: return None
        d = v.files.get(rel.lower())
        return d.decode("utf-8", "replace") if isinstance(d, bytes) else d


class ScriptUI:
    """Bàn phím theo kịch bản: keys = ['2', '\\r'] … hết phím thì coi như hết giờ (None)."""
    def __init__(self, keys=()):
        self.keys, self.prompts, self.held = list(keys), [], 0

    def ask(self, secs, prompt):
        self.prompts.append((secs, prompt))
        if self.keys: return self.keys.pop(0)
        if secs <= 0: raise AssertionError("bộ thử: màn hình chờ phím mãi mà kịch bản hết phím: " + prompt)
        return None

    def shell(self): self.prompts.append((0, "<shell>"))
    def hold(self, prompt): self.held += 1; self.prompts.append((0, "<hold> " + prompt))
