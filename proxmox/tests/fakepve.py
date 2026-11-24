#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proxmox GIẢ cho thử cbhost: đóng vai lệnh `qm` và `pvesh` (tên lệnh = argv[1]), trạng thái ở file JSON $FAKE_PVE_STATE.
   Chỉ làm đủ những gì cbhost gọi: /cluster/resources, /nodes/<node>/storage, agent/file-write, qm config|clone|set|resize|start|stop|
   shutdown|reset|destroy|guest cmd ping. Ghi lại mọi lệnh vào "log" (để thử kiểm tra cbhost gọi gì)."""
import json, os, re, socket, sys

ST = os.environ["FAKE_PVE_STATE"]


def load():
    try: return json.load(open(ST))
    except Exception: return {"vms": {}, "log": [], "linked_ok": True, "guest_after": 1}


def save(d): json.dump(d, open(ST + ".tmp", "w")); os.replace(ST + ".tmp", ST)


def opt(a, k, dflt=None):
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else dflt


def main():
    tool, a = sys.argv[1], sys.argv[2:]
    d = load(); d["log"].append([tool] + a); node = socket.gethostname().split(".")[0]
    vms = d["vms"]
    out, rc = "", 0
    if tool == "pvesh":
        if a[:2] == ["get", "/cluster/resources"]:
            out = json.dumps([{"type": "qemu", "node": node, "vmid": int(k), "name": v["name"], "status": v["status"], "template": 1 if v.get("template") else 0}
                              for k, v in vms.items()] + [{"type": "qemu", "node": "khac", "vmid": 999, "name": "may-node-khac", "status": "running", "template": 0}])
        elif a[:1] == ["get"] and re.fullmatch(r"/nodes/[^/]+/storage", a[1]):
            out = json.dumps([{"storage": "local-lvm", "active": 1, "content": "images,rootdir", "total": 1000 * 1073741824},
                              {"storage": "local", "active": 1, "content": "iso,vztmpl,backup", "total": 100 * 1073741824}])
        elif a[:1] == ["get"] and re.fullmatch(r"/nodes/[^/]+/qemu/\d+/agent/file-read", a[1]):
            vid = a[1].split("/")[4]; v = vms.get(vid); f = (v or {}).get("files") or {}
            if not v or v["status"] != "running": rc, out = 500, "VM not running"
            elif opt(a, "--file") not in f: rc, out = 500, "can't open file"
            else: out = json.dumps({"content": f[opt(a, "--file")], "truncated": False})
        elif a[:1] == ["create"] and re.fullmatch(r"/nodes/[^/]+/qemu/\d+/agent/file-write", a[1]):
            vid = a[1].split("/")[4]; v = vms.get(vid)
            if not v or v["status"] != "running" or v.get("ga", 0) < d.get("guest_after", 1): rc, out = 500, "QEMU guest agent is not running"
            else: v.setdefault("files", {})[opt(a, "--file")] = opt(a, "--content")
        else:
            rc, out = 2, "pvesh giả: không hỗ trợ " + " ".join(a)
    else:
        cmd = a[0] if a else ""
        vid = a[1] if len(a) > 1 else ""
        v = vms.get(vid)
        if cmd == "guest":                                          # qm guest cmd <vmid> ping
            vv = vms.get(a[2]) if len(a) >= 4 and a[1] == "cmd" and a[3] == "ping" else None
            if not vv or vv["status"] != "running": rc, out = 2, "VM not running"
            else:
                vv["ga"] = vv.get("ga", 0) + 1
                if vv["ga"] < d.get("guest_after", 1): rc, out = 2, "QEMU guest agent is not running"
        elif cmd == "config":
            if not v: rc, out = 2, "VM %s không có" % vid
            else: out = "\n".join(["name: " + v["name"]] + ["%s: local-lvm:vm-%s-disk-%d,size=%dG" % (k, vid, i, g) for i, (k, g) in enumerate(sorted(v["disks"].items()))]
                                  + ["boot: order=" + ";".join(sorted(v["disks"]))] + (["template: 1"] if v.get("template") else []))
        elif cmd == "clone":
            src, dst = a[1], a[2]
            if dst in vms: rc, out = 2, "VM %s đã có" % dst
            elif src not in vms or not vms[src].get("template"): rc, out = 2, "không có máy mẫu %s" % src
            elif opt(a, "--full") == "0" and not d.get("linked_ok", True): rc, out = 2, "linked clone feature is not available"
            else: vms[dst] = {"name": opt(a, "--name", "vm"), "status": "stopped", "disks": dict(vms[src]["disks"]), "cfg": {}, "from": src,
                              "full": opt(a, "--full"), "storage": opt(a, "--storage"), "files": dict(vms[src].get("files") or {})}
        elif not v:
            rc, out = 2, "VM %s không có" % vid
        elif cmd == "set":
            for k in ("--cores", "--memory", "--balloon", "--onboot", "--agent", "--tags", "--smbios1", "--sockets"):
                if k in a: v["cfg"][k[2:]] = opt(a, k)
        elif cmd == "resize":
            v["disks"][a[2]] = int(a[3].rstrip("G"))
        elif cmd == "start":
            if v["status"] == "running": rc, out = 2, "already running"
            else: v["status"], v["ga"] = "running", 0
        elif cmd in ("stop", "shutdown"):
            v["status"] = "stopped"
        elif cmd == "reset":
            v["resets"] = v.get("resets", 0) + 1; v["ga"] = 0
        elif cmd == "destroy":
            vms.pop(vid)
        else:
            rc, out = 2, "qm giả: không hỗ trợ " + " ".join(a)
    save(d)
    if out: print(out)
    sys.exit(rc)


main()
