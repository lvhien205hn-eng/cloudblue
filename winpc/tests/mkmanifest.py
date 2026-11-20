# -*- coding: utf-8 -*-
"""Ghi repo/winpc/manifest.json: mã kiểm sha256 của mọi file bộ công cụ (tao-iso.ps1 kiểm sau khi tải)
   + bản kê cập nhật agent (trang quản trị bấm 'Công bố bản agent' sẽ đọc phần ver/base/files)."""
import hashlib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "lib")); sys.path.insert(0, os.path.join(REPO, "agent"))
import cb_build, pcagent
BASE = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/winpc"
ps1 = open(os.path.join(REPO, "tao-iso.ps1"), encoding="ascii").read()
tool = re.search(r"\$TOOLFILES = @\((.*?)\)", ps1, re.S).group(1)
files = re.findall(r'"([^"]+)"', tool)
sha = {}
for f in files + ["tao-iso.ps1"]:
    with open(os.path.join(REPO, *f.split("/")), "rb") as fh: sha[f] = hashlib.sha256(fh.read()).hexdigest()
m = cb_build.manifest(REPO, BASE, pcagent.AGENT_VER)
m["sha256"] = sha
assert all(pcagent.UPDATE_REL.match(k) for k in m["files"]), "tên file bản kê agent không hợp lệ"
assert set(k for k in m["files"]) <= set(files) | {"os/unattend.tpl.xml"}, sorted(set(m["files"]) - set(files))
out = os.path.join(REPO, "manifest.json")
with open(out, "w", encoding="utf-8", newline="\n") as f: json.dump(m, f, indent=1, sort_keys=True); f.write("\n")
print("manifest.json: bản %s · %d file công cụ · %d file agent" % (m["ver"], len(sha), len(m["files"])))
