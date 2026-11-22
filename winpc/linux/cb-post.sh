#!/usr/bin/env bash
# =====================================================================================================
#  cb-post.sh — CloudBlue PC: việc làm thêm SAU KHI cachyos-installer cài xong, máy mới còn gắn ở $1 (vd /mnt).
#  cachyos-installer gọi (khoá "post_install" trong settings.json do cb-install.sh viết). Lỗi ở đây chỉ là cảnh báo.
#    · chép agent CloudBlue bản Linux (cb/linux/agent trên phân vùng cứu hộ) → /opt/cloudblue + bật dịch vụ
#    · ghi thông tin máy (tên, số máy, mã đăng ký 1 lần lấy từ cb/job.json) → /opt/cloudblue/state (chỉ root đọc được)
# =====================================================================================================
set -u
T="${1:-/mnt}"
R="${CB_REC:-/run/archiso/img_dev}"
JOB="${CB_JOB:-$R/cb/job.json}"
say() { printf '[cloudblue post] %s\n' "$*"; }
[ -d "$T/etc" ] || { say "khong thay may moi o $T"; exit 0; }

install -d -m 0755 "$T/opt/cloudblue"
install -d -m 0700 "$T/opt/cloudblue/state"
if [ -d "$R/cb/linux/agent" ]; then
    cp -a "$R/cb/linux/agent/." "$T/opt/cloudblue/" && say "da chep agent CloudBlue"
fi
python3 - "$JOB" "$T/opt/cloudblue/state/seed.json" <<'PYEOF'
import json, os, sys
try: job = json.load(open(sys.argv[1], encoding="utf-8-sig"))
except Exception: job = {}
seed = {k: job.get(k) for k in ("id", "os", "name", "code", "ticket", "enroll_key", "hw") if job.get(k) is not None}
seed["installed_by"] = "cb-install"
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(seed, f, ensure_ascii=False)
PYEOF
chmod 600 "$T/opt/cloudblue/state/seed.json"
if [ -f "$T/opt/cloudblue/cloudblue.service" ]; then
    install -m 0644 "$T/opt/cloudblue/cloudblue.service" "$T/etc/systemd/system/cloudblue.service"
    arch-chroot "$T" systemctl enable cloudblue.service >/dev/null 2>&1 && say "da bat dich vu cloudblue"
fi
echo "CloudBlue PC - cai bang cb-install $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$T/etc/cloudblue-release"
exit 0
