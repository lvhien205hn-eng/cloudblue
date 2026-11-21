# -*- coding: utf-8 -*-
# =====================================================================================================
#  cbsys.py — lớp nói chuyện với Windows (ổ đĩa, phân vùng, chữ ổ, firmware, bàn phím, chạy lệnh)
#  Dùng chung cho: bộ cài trong WinPE (cb_pe.py) · chuẩn bị cài lại từ trong Windows (cb_stage.py) · agent (pcagent.py)
#  Chỉ dùng thư viện chuẩn + ctypes (chạy được bằng Python nhúng, kể cả trong WinPE của bộ cài Windows).
#  Mọi thứ đọc ổ đĩa đi qua DeviceIoControl → không phụ thuộc ngôn ngữ Windows, không cần wmic / PowerShell.
#
#  Tự kiểm (chỉ ĐỌC, không đổi gì):   python cbsys.py --selftest
# =====================================================================================================
import ctypes, json, os, re, subprocess, sys, time

SYS_VER = "21.11d"
WIN = os.name == "nt"
COPY_BLOCK = 4 << 20                      # chép tệp theo khối 4MB
COPY_SAY = 64 << 20                       # tệp từ 64MB trở lên: in tên + dung lượng để biết máy đang chép, không phải treo

BUS_NAMES = {0: "?", 1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre", 7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS",
             11: "SATA", 12: "SD", 13: "MMC", 14: "Virtual", 15: "FileVirtual", 16: "Spaces", 17: "NVMe", 18: "SCM", 19: "UFS"}
BUS_EXTERNAL = (4, 7, 12)                 # 1394, USB, thẻ SD → không bao giờ là ổ cài Windows
BUS_NOT_REAL = (14, 15, 16)               # ổ ảo (VHD đang gắn, Storage Spaces) → không tự chọn

GPT_ESP = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
GPT_MSR = "e3c9e316-0b5c-4db8-817d-f92df00215ae"
GPT_DATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
GPT_WINRE = "de94bba4-06d1-4d40-a16a-bfd50179d6ac"
GPT_ATTR_REQUIRED = 0x0000000000000001
GPT_ATTR_NO_LETTER = 0x8000000000000000
GPT_ATTR_HIDDEN = 0x4000000000000000
MBR_HIDDEN_NTFS = 0x27                    # phân vùng khôi phục (không gán chữ ổ)
MBR_EXTENDED = (0x05, 0x0F)


class Part:
    """1 phân vùng trên ổ. type: GUID (chữ thường) với GPT · số (0x07, 0x27…) với MBR."""
    def __init__(self, number, offset, size, type, attrs=0, active=False, name="", guid=""):
        self.number, self.offset, self.size, self.type, self.attrs, self.active, self.name, self.guid = number, offset, size, type, attrs, active, name, guid

    def as_dict(self):
        return {"number": self.number, "offset": self.offset, "size": self.size, "type": self.type if isinstance(self.type, str) else "0x%02x" % self.type,
                "attrs": "0x%x" % self.attrs, "active": self.active, "name": self.name}


class Disk:
    def __init__(self, index, size, bus=0, removable=False, model="", serial="", ssd=None, style="raw", parts=None, sig=""):
        self.index, self.size, self.bus, self.removable, self.model, self.serial, self.ssd, self.style = index, size, bus, removable, model, serial, ssd, style
        self.parts = parts or []
        self.sig = sig                           # GPT: mã ổ (GUID) · MBR: chữ ký 8 ký tự hex

    @property
    def bus_name(self): return BUS_NAMES.get(self.bus, str(self.bus))

    @property
    def gb(self): return self.size / 1e9

    def label(self):
        kind = "SSD" if self.ssd else ("HDD" if self.ssd is False else "")
        return "o %d - %s - %.0f GB - %s%s" % (self.index, (self.model or "?").strip()[:40], self.gb, self.bus_name, (" " + kind) if kind else "")

    def as_dict(self):
        return {"index": self.index, "size": self.size, "bus": self.bus_name, "removable": self.removable, "model": self.model, "serial": self.serial,
                "ssd": self.ssd, "style": self.style, "sig": self.sig, "parts": [p.as_dict() for p in self.parts]}


class Vol:
    """1 ổ đĩa lôgic (volume). path = \\\\?\\Volume{GUID}\\ (luôn có) · letters = ['C'] (có thể rỗng)."""
    def __init__(self, path, letters=None, fs="", label="", kind=3, disk=None, offset=0, size=0):
        self.path, self.letters, self.fs, self.label, self.kind, self.disk, self.offset, self.size = path, letters or [], fs, label, kind, disk, offset, size

    @property
    def root(self):
        """Đường dẫn gốc dùng được ngay: 'D:\\' nếu có chữ ổ, không thì đường Volume{GUID}."""
        return (self.letters[0] + ":\\") if self.letters else self.path

    def as_dict(self):
        return {"path": self.path, "letters": self.letters, "fs": self.fs, "label": self.label, "kind": self.kind, "disk": self.disk, "offset": self.offset, "size": self.size}


# ====================================================================================== phân tích bộ đệm (thử được trên mọi máy)
def _u32(b, o): return int.from_bytes(b[o:o + 4], "little")
def _u64(b, o): return int.from_bytes(b[o:o + 8], "little")
def _i64(b, o): return int.from_bytes(b[o:o + 8], "little", signed=True)


def _guid(b, o):
    """GUID kiểu Windows (3 phần đầu little-endian) → chuỗi chữ thường."""
    d1, d2, d3 = _u32(b, o), int.from_bytes(b[o + 4:o + 6], "little"), int.from_bytes(b[o + 6:o + 8], "little")
    return "%08x-%04x-%04x-%s-%s" % (d1, d2, d3, b[o + 8:o + 10].hex(), b[o + 10:o + 16].hex())


def _cstr(b, o):
    if not o or o >= len(b): return ""
    e = b.find(b"\0", o)
    return b[o:e if e >= 0 else len(b)].decode("ascii", "replace").strip()


def parse_device_descriptor(b):
    """STORAGE_DEVICE_DESCRIPTOR → dict(bus, removable, model, serial)."""
    if len(b) < 36: return {"bus": 0, "removable": False, "model": "", "serial": ""}
    vendor, product, serial = _cstr(b, _u32(b, 12)), _cstr(b, _u32(b, 16)), _cstr(b, _u32(b, 24))
    return {"bus": _u32(b, 28), "removable": bool(b[10]), "model": (vendor + " " + product).strip(), "serial": serial}


def parse_drive_layout(b):
    """DRIVE_LAYOUT_INFORMATION_EX → (style, sig, [Part…]).  Đầu 48 byte, mỗi phân vùng 144 byte."""
    if len(b) < 48: return "raw", "", []
    style_n, count = _u32(b, 0), _u32(b, 4)
    style = {0: "mbr", 1: "gpt"}.get(style_n, "raw")
    sig = "%08x" % _u32(b, 8) if style == "mbr" else (_guid(b, 8) if style == "gpt" else "")
    parts = []
    for i in range(count):
        o = 48 + i * 144
        if o + 144 > len(b): break
        ps, start, length, number = _u32(b, o), _i64(b, o + 8), _i64(b, o + 16), _u32(b, o + 24)
        if length <= 0: continue
        if ps == 1:                                       # GPT
            ptype, pid, attrs = _guid(b, o + 32), _guid(b, o + 48), _u64(b, o + 64)
            name = b[o + 72:o + 144].decode("utf-16-le", "replace").split("\0")[0]
            if ptype == "00000000-0000-0000-0000-000000000000": continue
            parts.append(Part(number, start, length, ptype, attrs=attrs, name=name, guid=pid))
        elif ps == 0:                                     # MBR
            ptype, boot = b[o + 32], bool(b[o + 33])
            if ptype == 0 or ptype in MBR_EXTENDED: continue
            parts.append(Part(number, start, length, ptype, active=boot))
    parts.sort(key=lambda p: p.offset)
    return style, sig, parts


def parse_disk_extents(b):
    """VOLUME_DISK_EXTENTS → [(ổ, vị trí, dài)…]"""
    if len(b) < 8: return []
    n, out = _u32(b, 0), []
    for i in range(n):
        o = 8 + i * 24
        if o + 24 > len(b): break
        out.append((_u32(b, o), _i64(b, o + 8), _i64(b, o + 16)))
    return out


# ====================================================================================== Windows thật
class WinSys:
    """Giao tiếp Windows thật. Bộ thử dùng lớp giả có cùng các hàm (tests/fakesys.py)."""
    dry = False                                   # dry=True: chỉ in lệnh sẽ chạy (diskpart / dism / bcdedit…), không chạy

    def __init__(self, log=None):
        self._log = log or (lambda *a: print(*a, flush=True))
        if WIN:
            from ctypes import wintypes as wt
            self.wt = wt
            k = self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
            k.CreateFileW.restype = wt.HANDLE
            k.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
            k.DeviceIoControl.restype = wt.BOOL
            k.CloseHandle.argtypes = [wt.HANDLE]; k.CloseHandle.restype = wt.BOOL
            k.FindFirstVolumeW.argtypes = [wt.LPWSTR, wt.DWORD]; k.FindFirstVolumeW.restype = wt.HANDLE
            k.FindNextVolumeW.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD]; k.FindNextVolumeW.restype = wt.BOOL
            k.FindVolumeClose.argtypes = [wt.HANDLE]; k.FindVolumeClose.restype = wt.BOOL
            k.GetVolumePathNamesForVolumeNameW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD)]
            k.GetVolumePathNamesForVolumeNameW.restype = wt.BOOL
            k.GetVolumeInformationW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD),
                                                ctypes.POINTER(wt.DWORD), wt.LPWSTR, wt.DWORD]
            k.GetVolumeInformationW.restype = wt.BOOL
            k.GetDriveTypeW.argtypes = [wt.LPCWSTR]; k.GetDriveTypeW.restype = wt.UINT
            k.GetLogicalDrives.argtypes = []; k.GetLogicalDrives.restype = wt.DWORD
            k.SetVolumeMountPointW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]; k.SetVolumeMountPointW.restype = wt.BOOL
            k.DeleteVolumeMountPointW.argtypes = [wt.LPCWSTR]; k.DeleteVolumeMountPointW.restype = wt.BOOL
            k.GetDiskFreeSpaceExW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
            k.GetDiskFreeSpaceExW.restype = wt.BOOL
            k.QueryDosDeviceW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD]; k.QueryDosDeviceW.restype = wt.DWORD
            k.SetErrorMode.argtypes = [wt.UINT]; k.SetErrorMode.restype = wt.UINT
            try: k.SetErrorMode(0x0001 | 0x8000)          # không bật hộp thoại "No disk in drive" khi dò ổ trống (đầu đọc thẻ…)
            except Exception: pass
            self.INVALID = wt.HANDLE(-1).value

    def log(self, *a):
        try: self._log(*a)
        except Exception: pass

    # ------------------------------------------------------------------ thiết bị
    def _open(self, path, access=0x80000000):
        h = self.k32.CreateFileW(path, access, 0x1 | 0x2, None, 3, 0, None)          # chia sẻ đọc+ghi, OPEN_EXISTING
        return None if (h is None or h == self.INVALID) else h

    def _ioctl(self, h, code, inbuf=b"", outsize=4096):
        out = ctypes.create_string_buffer(outsize)
        got = self.wt.DWORD(0)
        ib = ctypes.create_string_buffer(inbuf, len(inbuf)) if inbuf else None
        ok = self.k32.DeviceIoControl(h, code, ib, len(inbuf), out, outsize, ctypes.byref(got), None)
        return out.raw[:got.value] if ok else None

    def firmware(self):
        """'uefi' hoặc 'bios' (máy đang khởi động kiểu nào)."""
        if not WIN: return "bios"
        try:
            t = self.wt.DWORD(0)
            self.k32.GetFirmwareType.argtypes = [ctypes.POINTER(self.wt.DWORD)]; self.k32.GetFirmwareType.restype = self.wt.BOOL
            if self.k32.GetFirmwareType(ctypes.byref(t)) and t.value in (1, 2): return "uefi" if t.value == 2 else "bios"
        except Exception: pass
        try:                                               # WinPE: wpeutil UpdateBootInfo ghi PEFirmwareType (1 = BIOS, 2 = UEFI)
            import winreg
            subprocess.run(["wpeutil", "UpdateBootInfo"], capture_output=True, timeout=30)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Control") as k:
                return "uefi" if int(winreg.QueryValueEx(k, "PEFirmwareType")[0]) == 2 else "bios"
        except Exception: pass
        return "uefi" if os.path.isdir(os.path.join(os.environ.get("SystemRoot", r"X:\Windows"), "Boot", "EFI")) and not os.environ.get("CB_FORCE_BIOS") else "bios"

    def disks(self):
        out = []
        miss = 0
        for i in range(64):
            h = self._open(r"\\.\PhysicalDrive%d" % i)
            if h is None:
                miss += 1
                if miss > 16: break                        # số ổ có thể không liền nhau (rút USB) → chỉ dừng khi hụt 16 số liền
                continue
            miss = 0
            try:
                size = 0
                b = self._ioctl(h, 0x0007405C, b"", 16)                          # IOCTL_DISK_GET_LENGTH_INFO
                if b and len(b) >= 8: size = _i64(b, 0)
                d = {"bus": 0, "removable": False, "model": "", "serial": ""}
                b = self._ioctl(h, 0x002D1400, bytes(12), 2048)                  # IOCTL_STORAGE_QUERY_PROPERTY · StorageDeviceProperty
                if b: d = parse_device_descriptor(b)
                ssd = None
                b = self._ioctl(h, 0x002D1400, (7).to_bytes(4, "little") + bytes(8), 64)   # StorageDeviceSeekPenaltyProperty
                if b and len(b) >= 9: ssd = not bool(b[8])
                if d["bus"] == 17: ssd = True
                style, sig, parts = "raw", "", []
                b = self._ioctl(h, 0x00070050, b"", 48 + 144 * 128)              # IOCTL_DISK_GET_DRIVE_LAYOUT_EX (tối đa 128 phân vùng)
                if b: style, sig, parts = parse_drive_layout(b)
                if size > 0:
                    out.append(Disk(i, size, d["bus"], d["removable"], d["model"], d["serial"], ssd, style, parts, sig))
            finally:
                self.k32.CloseHandle(h)
        return out

    def volumes(self):
        out = []
        buf = ctypes.create_unicode_buffer(512)
        h = self.k32.FindFirstVolumeW(buf, 512)
        if h is None or h == self.INVALID: return out
        try:
            while True:
                path = buf.value                                       # \\?\Volume{GUID}\
                v = Vol(path)
                names = ctypes.create_unicode_buffer(2048); n = self.wt.DWORD(0)
                if self.k32.GetVolumePathNamesForVolumeNameW(path, names, 2048, ctypes.byref(n)):
                    for p in names[:max(0, n.value)].split("\0"):
                        if len(p) == 3 and p[1:] == ":\\": v.letters.append(p[0].upper())
                v.kind = int(self.k32.GetDriveTypeW(path))
                lab = ctypes.create_unicode_buffer(261); fs = ctypes.create_unicode_buffer(261)
                if v.kind != 2 or v.letters:                           # ổ rời không có đĩa (đầu đọc thẻ trống) → bỏ qua phần hỏi nhãn
                    if self.k32.GetVolumeInformationW(path, lab, 261, None, None, None, fs, 261):
                        v.label, v.fs = lab.value, fs.value
                hv = self._open(path.rstrip("\\"), 0)
                if hv is not None:
                    try:
                        b = self._ioctl(hv, 0x00560000, b"", 8 + 24 * 8)          # IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS
                        ex = parse_disk_extents(b) if b else []
                        if ex: v.disk, v.offset, v.size = ex[0]
                    finally:
                        self.k32.CloseHandle(hv)
                out.append(v)
                if not self.k32.FindNextVolumeW(h, buf, 512): break
        finally:
            self.k32.FindVolumeClose(h)
        return out

    def used_letters(self):
        m = self.k32.GetLogicalDrives()
        return {chr(65 + i) for i in range(26) if m & (1 << i)}

    def mount(self, vol_path, letter):
        """Gán chữ ổ cho 1 volume (đường \\\\?\\Volume{GUID}\\)."""
        if self.dry: self.log("  [thu] gan chu %s: cho %s" % (letter, vol_path)); return True
        return bool(self.k32.SetVolumeMountPointW(letter + ":\\", vol_path if vol_path.endswith("\\") else vol_path + "\\"))

    def unmount(self, letter):
        if self.dry: self.log("  [thu] bo chu %s:" % letter); return True
        return bool(self.k32.DeleteVolumeMountPointW(letter + ":\\"))

    def free_bytes(self, root):
        f = ctypes.c_ulonglong(0)
        return f.value if self.k32.GetDiskFreeSpaceExW(root, ctypes.byref(f), None, None) else 0

    def nt_device(self, vol_path):
        """Đường Volume{GUID} → tên thiết bị kiểu /Device/HarddiskVolumeN (để ghi vào BCD mà không cần gán chữ ổ). Không được → ''."""
        name = vol_path.strip("\\")
        if name.startswith("?\\"): name = name[2:]
        buf = ctypes.create_unicode_buffer(512)
        n = self.k32.QueryDosDeviceW(name, buf, 512)
        return buf.value if n and buf.value.lower().startswith("\\device\\") else ""

    # ------------------------------------------------------------------ tệp
    def exists(self, p): return os.path.exists(p)
    def isdir(self, p): return os.path.isdir(p)
    def listdir(self, p):
        try: return os.listdir(p)
        except OSError: return []
    def size(self, p):
        try: return os.path.getsize(p)
        except OSError: return 0

    def read_text(self, p):
        with open(p, "r", encoding="utf-8-sig") as f: return f.read()

    def write_text(self, p, s, encoding="utf-8"):
        if self.dry: self.log("  [thu] ghi %s (%d ky tu)" % (p, len(s))); return
        try: os.makedirs(os.path.dirname(p), exist_ok=True)
        except OSError: pass                                   # thư mục đã có trên đường Volume{GUID} → cứ ghi
        tmp = p + ".tmp"
        with open(tmp, "w", encoding=encoding, newline="") as f: f.write(s)
        os.replace(tmp, p)

    def read_bytes(self, p):
        with open(p, "rb") as f: return f.read()

    def write_bytes(self, p, b):
        if self.dry: self.log("  [thu] ghi %s (%d byte)" % (p, len(b))); return
        try: os.makedirs(os.path.dirname(p), exist_ok=True)
        except OSError: pass
        tmp = p + ".tmp"
        with open(tmp, "wb") as f: f.write(b)
        if os.path.exists(p):
            try: os.chmod(p, 0o666)
            except OSError: pass
        os.replace(tmp, p)

    def makedirs(self, p):
        if self.dry: return
        try: os.makedirs(p, exist_ok=True)
        except OSError:
            if not os.path.isdir(p): raise

    def remove(self, p):
        if self.dry: self.log("  [thu] xoa %s" % p); return
        try:
            if os.path.isfile(p):
                try: os.chmod(p, 0o666)
                except OSError: pass
                os.remove(p)
        except OSError: pass

    def rename(self, a, b):
        if self.dry: self.log("  [thu] doi ten %s -> %s" % (a, b)); return
        self.remove(b); os.replace(a, b)

    def copy_file(self, src, dst, show=None):
        """Chép 1 tệp lớn theo khối 8MB (có % tiến độ)."""
        if self.dry: self.log("  [thu] chep %s -> %s" % (src, dst)); return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        total, done, t0, last = max(1, os.path.getsize(src)), 0, time.time(), 0.0
        tmp = dst + ".part"
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                b = fi.read(8 << 20)
                if not b: break
                fo.write(b); done += len(b)
                if show and time.time() - last > 1.0:
                    last = time.time(); show(done, total, done / max(0.5, last - t0))
            fo.flush(); os.fsync(fo.fileno())
        if os.path.exists(dst):
            try: os.chmod(dst, 0o666)
            except OSError: pass
            os.remove(dst)
        os.replace(tmp, dst)
        if show: show(total, total, total / max(0.5, time.time() - t0))

    def copy_tree(self, src, dst, skip=None):
        """Chép cả thư mục, TỪNG TỆP THEO KHỐI 4MB — tệp to cỡ nào cũng không ngốn RAM (WinPE không có tệp hoán trang:
           đọc nguyên 1 gói driver 700MB vào bộ nhớ là hết RAM). Trả số tệp.
           skip(đường dẫn thư mục con tính từ src, dùng dấu \\) trả True → bỏ cả thư mục con đó."""
        if self.dry: self.log("  [thu] chep thu muc %s -> %s" % (src, dst)); return 0
        n = 0
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            if skip:
                dirs[:] = [x for x in dirs if not skip((x if rel == "." else os.path.join(rel, x)).replace("/", "\\"))]
            to = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(to, exist_ok=True)
            for f in files:
                s, d = os.path.join(root, f), os.path.join(to, f)
                try: big = os.path.getsize(s)
                except OSError: big = 0
                if big >= COPY_SAY: self.log("      %s (%.0f MB) ..." % (f, big / 1e6))
                if os.path.exists(d):
                    try: os.chmod(d, 0o666)
                    except OSError: pass
                with open(s, "rb") as fi, open(d, "wb") as fo:
                    while True:
                        b = fi.read(COPY_BLOCK)
                        if not b: break
                        fo.write(b)
                n += 1
        return n

    # ------------------------------------------------------------------ chạy lệnh
    def run(self, argv, timeout=3600, show=False, input=None, change=True):
        """Chạy 1 lệnh. show=True: in thẳng ra màn hình (thanh tiến độ của dism). Trả (mã thoát, chữ in ra).
           change=False: lệnh chỉ đọc → chạy cả khi đang chạy thử (dry)."""
        if self.dry and change:
            self.log("  [thu] " + " ".join(('"%s"' % a) if " " in a else a for a in argv)); return 0, ""
        try:
            if show:
                r = subprocess.run(argv, timeout=timeout, input=input.encode() if input else None)
                return r.returncode, ""
            r = subprocess.run(argv, capture_output=True, timeout=timeout, input=input.encode() if input else None)
            out = (r.stdout or b"") + (r.stderr or b"")
            try: txt = out.decode("utf-8")
            except UnicodeDecodeError: txt = out.decode("mbcs" if WIN else "latin-1", "replace")
            return r.returncode, txt
        except subprocess.TimeoutExpired:
            return 124, "qua thoi gian"
        except OSError as e:
            return 127, "khong chay duoc %s: %s" % (argv[0], e)

    def diskpart(self, lines):
        """Chạy 1 kịch bản diskpart. Lệnh nào lỗi thì diskpart dừng và trả mã khác 0."""
        script = "\r\n".join(lines) + "\r\nexit\r\n"
        if self.dry:
            self.log("  [thu] diskpart:"); [self.log("      " + ln) for ln in lines]; return 0, ""
        tmp = os.path.join(os.environ.get("TEMP") or os.environ.get("SystemDrive", "X:") + "\\", "cb-dp-%d.txt" % int(time.time() * 1000))
        with open(tmp, "w", encoding="ascii", newline="") as f: f.write(script)
        try:
            return self.run(["diskpart", "/s", tmp], timeout=1800)
        finally:
            try: os.remove(tmp)
            except OSError: pass

    def reboot(self):
        if self.dry: self.log("  [thu] khoi dong lai"); return
        for cmd in (["wpeutil", "reboot"], ["shutdown", "/r", "/t", "0", "/f"]):
            try:
                if subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0: return
            except Exception: pass

    # ------------------------------------------------------------------ bàn phím (đếm ngược)
    def key_wait(self, seconds):
        """Chờ tối đa `seconds` giây; có phím bấm → trả phím (chữ thường), không → None."""
        try: import msvcrt
        except ImportError:
            time.sleep(min(seconds, 0.01)); return None
        end = time.time() + seconds
        while time.time() < end:
            if msvcrt.kbhit():
                c = msvcrt.getwch()
                if c in ("\x00", "\xe0"): msvcrt.getwch(); continue        # phím mũi tên / F1… (2 mã) → bỏ
                return c.lower()
            time.sleep(0.05)
        return None

    def now(self): return time.time()
    def sleep(self, s): time.sleep(s)


# ====================================================================================== thiết bị + driver (Windows đang chạy)
def pnp_devices(limit=1500):
    """Mọi thiết bị ĐANG CẮM của máy — như danh sách của Device Manager, hỏi thẳng SetupAPI + cfgmgr32 (không cần WMI / PowerShell, không phụ thuộc ngôn ngữ):
       [{"name", "cls" (tên lớp: Net, Display… — rỗng khi chưa có driver), "id" (mã thiết bị), "problem" (0 = chạy tốt, 28 = chưa có driver…), "service", "compat" [mã tương thích]}]."""
    from ctypes import wintypes
    sa, cm = ctypes.WinDLL("setupapi", use_last_error=True), ctypes.WinDLL("cfgmgr32")

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    class DEVINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID), ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, wintypes.DWORD]
    sa.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DEVINFO)]
    sa.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DEVINFO), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
                                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    sa.SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DEVINFO), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    cm.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG), wintypes.DWORD, wintypes.ULONG]
    h = sa.SetupDiGetClassDevsW(None, None, None, 0x2 | 0x4)         # DIGCF_PRESENT | DIGCF_ALLCLASSES
    if not h or h == ctypes.c_void_p(-1).value: raise OSError("SetupDiGetClassDevs loi %d" % ctypes.get_last_error())
    chars = 4096
    buf = ctypes.create_unicode_buffer(chars)

    def prop(d, code, multi=False):
        need = wintypes.DWORD(0)
        if not sa.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(d), code, None, buf, chars * 2, ctypes.byref(need)): return [] if multi else ""
        txt = ctypes.wstring_at(ctypes.addressof(buf), max(0, min(need.value // 2, chars)))
        return [x for x in txt.split("\0") if x] if multi else txt.split("\0", 1)[0]

    out = []
    try:
        i = 0
        while i < limit:
            d = DEVINFO(); d.cbSize = ctypes.sizeof(DEVINFO)
            if not sa.SetupDiEnumDeviceInfo(h, i, ctypes.byref(d)): break
            i += 1
            st, pb = wintypes.ULONG(0), wintypes.ULONG(0)
            ok = cm.CM_Get_DevNode_Status(ctypes.byref(st), ctypes.byref(pb), d.DevInst, 0) == 0
            did = buf.value if sa.SetupDiGetDeviceInstanceIdW(h, ctypes.byref(d), buf, chars, None) else ""
            out.append({"name": prop(d, 12) or prop(d, 0), "cls": prop(d, 7), "id": did, "problem": pb.value if (ok and st.value & 0x400) else 0,     # DN_HAS_PROBLEM
                        "service": prop(d, 4), "compat": prop(d, 2, True)[:8]})      # 12 FRIENDLYNAME · 0 DEVICEDESC · 7 CLASS · 4 SERVICE · 2 COMPATIBLEIDS
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    return out


def pnp_retry():
    """Bảo Windows DÒ LẠI PHẦN CỨNG + thử cài lại mọi thiết bị chưa có driver từ kho driver (đúng việc nút "Scan for hardware changes" của Device Manager làm).
       Dùng sau khi bộ cài đã nạp sẵn driver vào kho (dism /Add-Driver) mà thiết bị vẫn chưa nhận. Trả mã cfgmgr32: 0 = đã ra lệnh được."""
    from ctypes import wintypes
    cm = ctypes.WinDLL("cfgmgr32")
    cm.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wintypes.DWORD), ctypes.c_wchar_p, wintypes.ULONG]
    cm.CM_Reenumerate_DevNode.argtypes = [wintypes.DWORD, wintypes.ULONG]
    dev = wintypes.DWORD(0)
    cr = cm.CM_Locate_DevNodeW(ctypes.byref(dev), None, 0)           # gốc cây thiết bị
    return cr if cr != 0 else cm.CM_Reenumerate_DevNode(dev, 0x2)   # CM_REENUMERATE_RETRY_INSTALLATION


def staged_infs(limit=600, how=None, root=None):
    """Gói driver BÊN THỨ BA đang nằm trong kho driver của Windows (bộ cài nạp bằng dism /Add-Driver, hoặc ai đó đã cài): [{"pub": "oem3.inf", "inf": đường dẫn
       file .inf gốc trong kho}]. Đường dẫn này đưa được cho `pnputil -i -a` để cài ngay lên thiết bị khớp.
       Cách tìm (không phụ thuộc ngôn ngữ lẫn registry — gói mới NẠP mà chưa thiết bị nào dùng thì KHÔNG có trong HKLM\\SYSTEM\\DriverDatabase, đã thử trên Windows thật):
       mỗi gói bên thứ ba có 1 bản chép file .inf tên oemN.inf trong %SystemRoot%\\INF → tìm trong kho (System32\\DriverStore\\FileRepository\\<tên>.inf_<máy>_<mã>\\<tên>.inf)
       file .inf GIỐNG HỆT bản chép đó (so cỡ trước, giống cỡ mới so nội dung). Gói kiểu cũ không nằm trong kho (vài driver máy in có sẵn) thì bỏ qua.
       how (nếu đưa vào, kiểu dict): nhận {"pub": số file oemN.inf, "repo": số gói trong kho, "match": số gói khớp} — để bộ thử in ra."""
    root = root or os.environ.get("SystemRoot") or "C:\\Windows"
    inf_dir, repo = os.path.join(root, "INF"), os.path.join(root, "System32", "DriverStore", "FileRepository")
    num = lambda pub: int(re.sub(r"\D", "", pub) or 0)
    try: pubs = sorted(((n.lower(), n) for n in os.listdir(inf_dir) if re.fullmatch(r"oem\d+\.inf", n, re.I)), key=lambda t: num(t[0]))
    except OSError: pubs = []
    by_size, n_repo = {}, 0
    try: dirs = os.listdir(repo)
    except OSError: dirs = []
    for d in dirs:
        m = re.match(r"^(.+\.inf)_", d, re.I)
        if not m: continue
        path = os.path.join(repo, d, m.group(1))
        try: size = os.path.getsize(path)
        except OSError: continue
        n_repo += 1
        by_size.setdefault(size, []).append(path)
    out = []
    for pub, real in pubs:
        if len(out) >= limit: break
        src = os.path.join(inf_dir, real)
        try:
            cands = by_size.get(os.path.getsize(src)) or []
            if not cands: continue
            with open(src, "rb") as f: raw = f.read()
        except OSError:
            continue
        for path in cands:
            try:
                with open(path, "rb") as f: same = f.read() == raw
            except OSError:
                same = False
            if same:
                out.append({"pub": pub, "inf": path}); break
    if how is not None: how.update(pub=len(pubs), repo=n_repo, match=len(out))
    return out


# ====================================================================================== phiên màn hình (điều khiển từ xa — bản 21.11d)
def console_session():
    """Số của PHIÊN MÀN HÌNH đang hiện (phiên của người ngồi trước máy). Chưa có phiên nào (đang đổi phiên) → None."""
    k = ctypes.WinDLL("kernel32")
    k.WTSGetActiveConsoleSessionId.restype = ctypes.c_uint32
    sid = k.WTSGetActiveConsoleSessionId()
    return None if sid == 0xFFFFFFFF else int(sid)


def mutex_exists(name):
    """Có chương trình nào đang giữ khoá tên này không (vd "Global\\CloudBluePCRemote" = chương trình điều khiển từ xa đang chạy)."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]; k.OpenMutexW.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.OpenMutexW(0x00100000, 0, name)                             # SYNCHRONIZE
    if not h: return False
    k.CloseHandle(h)
    return True


def spawn_console(argv, cwd=None, desktop="winsta0\\default", sid=None):
    """Chạy 1 chương trình bằng CHÍNH tài khoản đang chạy (agent = SYSTEM) nhưng nằm TRONG phiên màn hình đang hiện, không cửa sổ.
       Chương trình chạy từ tác vụ hệ thống nằm ở phiên 0 — không thấy màn hình, không gửi được chuột / phím; muốn quay màn hình + điều khiển
       thì phải nằm trong phiên của người ngồi máy. Cách làm chuẩn của Windows: nhân bản thẻ quyền của mình, đổi số phiên, CreateProcessAsUser.
       Cần quyền SeTcbPrivilege (SYSTEM có sẵn) — tài khoản khác gọi sẽ lỗi 1314. Trả (pid, số phiên). Lỗi → OSError."""
    from ctypes import wintypes as wt
    k = ctypes.WinDLL("kernel32", use_last_error=True); a = ctypes.WinDLL("advapi32", use_last_error=True)

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

    class TOKPRIV(ctypes.Structure):
        _fields_ = [("Count", wt.DWORD), ("Luid", LUID), ("Attr", wt.DWORD)]

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                    ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD), ("lpReserved2", ctypes.c_void_p),
                    ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]

    class PROCINFO(ctypes.Structure):
        _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]

    k.GetCurrentProcess.restype = wt.HANDLE
    k.CloseHandle.argtypes = [wt.HANDLE]
    a.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]; a.OpenProcessToken.restype = wt.BOOL
    a.LookupPrivilegeValueW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.POINTER(LUID)]; a.LookupPrivilegeValueW.restype = wt.BOOL
    a.AdjustTokenPrivileges.argtypes = [wt.HANDLE, wt.BOOL, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, ctypes.c_void_p]; a.AdjustTokenPrivileges.restype = wt.BOOL
    a.DuplicateTokenEx.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wt.HANDLE)]; a.DuplicateTokenEx.restype = wt.BOOL
    a.SetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]; a.SetTokenInformation.restype = wt.BOOL
    a.CreateProcessAsUserW.argtypes = [wt.HANDLE, wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                                       ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCINFO)]
    a.CreateProcessAsUserW.restype = wt.BOOL
    if sid is None: sid = console_session()
    if sid is None: raise OSError("chua co phien man hinh nao")
    tok, dup = wt.HANDLE(), wt.HANDLE()
    if not a.OpenProcessToken(k.GetCurrentProcess(), 0xF01FF, ctypes.byref(tok)): raise OSError("OpenProcessToken loi %d" % ctypes.get_last_error())
    try:
        for name in ("SeTcbPrivilege", "SeAssignPrimaryTokenPrivilege", "SeIncreaseQuotaPrivilege"):      # bật các quyền SYSTEM có sẵn (không có thì bước sau báo lỗi rõ)
            tp = TOKPRIV(); tp.Count = 1; tp.Attr = 2
            if a.LookupPrivilegeValueW(None, name, ctypes.byref(tp.Luid)): a.AdjustTokenPrivileges(tok, False, ctypes.byref(tp), 0, None, None)
        if not a.DuplicateTokenEx(tok, 0x02000000, None, 2, 1, ctypes.byref(dup)): raise OSError("DuplicateTokenEx loi %d" % ctypes.get_last_error())
        try:
            n = wt.DWORD(int(sid))
            if not a.SetTokenInformation(dup, 12, ctypes.byref(n), 4):                                    # TokenSessionId
                raise OSError("khong doi duoc phien cua the quyen (loi %d) - chi tai khoan SYSTEM lam duoc" % ctypes.get_last_error())
            si = STARTUPINFO(); si.cb = ctypes.sizeof(STARTUPINFO); si.lpDesktop = desktop
            pi = PROCINFO()
            cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in argv]))
            if not a.CreateProcessAsUserW(dup, None, cmd, None, None, False, 0x08000000, None, cwd, ctypes.byref(si), ctypes.byref(pi)):   # CREATE_NO_WINDOW
                raise OSError("CreateProcessAsUser loi %d" % ctypes.get_last_error())
            k.CloseHandle(pi.hThread); k.CloseHandle(pi.hProcess)
            return int(pi.dwProcessId), int(sid)
        finally:
            k.CloseHandle(dup)
    finally:
        k.CloseHandle(tok)


# ====================================================================================== tự kiểm (chỉ đọc)
def selftest():
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass
    s = WinSys()
    if not WIN:
        print("cbsys %s: chi chay tu kiem tren Windows" % SYS_VER); return 2
    print("cbsys %s - Python %s - firmware: %s" % (SYS_VER, sys.version.split()[0], s.firmware()))
    ds = s.disks()
    print("So o cung thay duoc: %d" % len(ds))
    for d in ds:
        print("  " + d.label() + " - kieu %s%s - so serial %s" % (d.style.upper(), " - thao duoc" if d.removable else "", d.serial or "?"))
        for p in d.parts:
            t = p.type if isinstance(p.type, str) else "0x%02x" % p.type
            print("      phan vung %d: bat dau %.1f MB - %.1f GB - %s%s%s" % (p.number, p.offset / 1048576, p.size / 1e9, t,
                  " - khoi dong" if p.active else "", (" - " + p.name) if p.name else ""))
    vs = s.volumes()
    print("So o logic (volume): %d" % len(vs))
    for v in vs:
        print("  %-4s %-8s %-18s o %s - bat dau %.1f MB - %.1f GB - loai %d" % (",".join(v.letters) or "-", v.fs or "?", (v.label or "")[:18],
              "?" if v.disk is None else v.disk, v.offset / 1048576, v.size / 1e9, v.kind))
    print("Chu o dang dung: " + "".join(sorted(s.used_letters())))
    ok = bool(ds) and all(d.size > 0 for d in ds) and any(v.letters for v in vs)
    print("TU KIEM: " + ("DAT" if ok else "CHUA DAT - gui man hinh nay cho ho tro"))
    if "--json" in sys.argv:
        print(json.dumps({"disks": [d.as_dict() for d in ds], "volumes": [v.as_dict() for v in vs]}, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv: sys.exit(selftest())
    print("cbsys %s" % SYS_VER)
