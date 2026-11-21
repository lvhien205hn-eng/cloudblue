# -*- coding: utf-8 -*-
"""Dựng máy giả dùng chung cho các bộ thử (USB bộ cài, ổ có phân vùng cứu hộ, lệnh cài lại)."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import cbcore as C                                    # noqa: E402
from cbsys import GPT_DATA, GPT_ESP, GPT_MSR          # noqa: E402
from fakesys import GB, MB                            # noqa: E402

TPL = open(os.path.join(HERE, "..", "os", "unattend.tpl.xml"), encoding="utf-8").read()


def cfg0(**kw):
    c = {"ver": "20.11a", "default": "22h2", "user": "PC", "password": "", "countdown": 30, "sb_url": "https://x.supabase.co", "sb_key": "pub",
         "images": [{"id": "22h2", "file": "sources\\install.wim", "index": 6, "name": "Windows 10 Pro 22H2", "edition": "Professional",
                     "version": "10.0.19045.3803", "lang": "en-US", "bytes": 5 * GB},
                    {"id": "1511", "file": "cb\\images\\1511.wim", "index": 1, "name": "Windows 10 Pro 1511", "edition": "Professional",
                     "version": "10.0.10586.0", "lang": "en-US", "bytes": 4 * GB}]}
    c.update(kw); return c


def media_files(cfg, key="cbpc_" + "a" * 40):
    f = {"cb\\media.tag": "1", "cb\\cb.json": json.dumps(cfg), "sources\\boot.wim": b"BOOTWIM", "boot\\boot.sdi": b"SDI",
         "sources\\install.wim": b"I22", "cb\\images\\1511.wim": b"I15", "cb\\os\\unattend.tpl.xml": TPL, "cb\\os\\provision.cmd": "p",
         "cb\\agent\\pcagent.py": "a", "cb\\agent\\pcremote.py": "r", "cb\\lib\\cbsys.py": "l", "cb\\pe\\cb_pe.py": "pe", "cb\\py\\python.exe": b"py"}
    if key: f["cb\\enroll.key"] = key + "\r\n"
    return f


def usb(fs, cfg, index=9, letter="E", **kw):
    d = fs.disk(index, 32, bus=7, removable=True, model="SanDisk Ultra", style="mbr")
    d.add(0, 0x07, "NTFS", "CLOUDBLUE", letter, files=media_files(cfg, **kw))
    return d


def rec_files(cfg, job=None):
    r = C.recovery_cfg(cfg)
    f = {"cb\\recovery.tag": "1", "cb\\cb.json": json.dumps(r), "cb\\boot\\boot.wim": b"BOOTWIM", "cb\\boot\\boot.sdi": b"SDI",
         "cb\\images\\22h2.wim": b"I22", "cb\\images\\1511.wim": b"I15", "cb\\os\\unattend.tpl.xml": TPL, "cb\\os\\provision.cmd": "p",
         "cb\\agent\\pcagent.py": "a", "cb\\agent\\pcremote.py": "r", "cb\\lib\\cbsys.py": "l", "cb\\pe\\cb_pe.py": "pe", "cb\\py\\python.exe": b"py",
         "cb\\identity.json": json.dumps({"id": "11111111-1111-1111-1111-111111111111", "hw": "h" * 64, "name": "CB-OLD001"})}
    if job is not None: f["cb\\job.json"] = json.dumps(job)
    return f


WINFILES = {"windows\\system32\\config\\system": b"old", "users\\khach\\bi-mat.txt": "du lieu khach cu"}


def cb_layout(fs, cfg, job=None, index=0, size=480, fw="uefi", extra_data=False, model="Samsung SSD 870"):
    """Ổ hệ thống đúng kiểu bộ cài CloudBlue tạo ra. Trả (ổ, phân vùng cứu hộ, phân vùng Windows)."""
    if fw == "uefi":
        d = fs.disk(index, size, model=model, ssd=True, style="gpt")
        d.add(260, GPT_ESP, "FAT32", "System", files={"efi\\microsoft\\boot\\bcd": "oldbcd"})
        d.add(16, GPT_MSR)
        rec = d.add(12 * 1024, GPT_DATA, "NTFS", "CBRECOVERY", attrs=0x8000000000000001, files=rec_files(cfg, job))
        win = d.add(200 * 1024 if extra_data else 0, GPT_DATA, "NTFS", "Windows", "C", files=dict(WINFILES))
        if extra_data: d.add(0, GPT_DATA, "NTFS", "Data", "D", files={"game\\save.dat": "cua khach"})
    else:
        d = fs.disk(index, size, model=model, ssd=True, style="mbr")
        d.add(500, 0x07, "NTFS", "System", active=True, files={"boot\\bcd": "oldbcd"})
        rec = d.add(12 * 1024, 0x27, "NTFS", "CBRECOVERY", files=rec_files(cfg, job))
        win = d.add(200 * 1024 if extra_data else 0, 0x07, "NTFS", "Windows", "C", files=dict(WINFILES))
        if extra_data: d.add(0, 0x07, "NTFS", "Data", "D", files={"game\\save.dat": "cua khach"})
    return d, rec, win


def job0(win=None, **kw):
    j = {"id": 77, "os": "1511", "wipe": "all", "ticket": "t" * 32, "name": "CB-OLD001", "hw": "h" * 64, "state": "queued", "attempts": 0, "ts": 1}
    if win is not None: j["win"] = win if isinstance(win, dict) else {"offset": win.offset, "size": win.size}
    j.update(kw); return j
