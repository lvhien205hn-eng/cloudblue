#!/usr/bin/env bash
# =====================================================================================================
#  cb-post.sh — CloudBlue PC: phần CloudBlue trên máy CachyOS vừa cài. cb-install.sh gọi khi máy mới còn gắn ở $1 (/mnt/cbroot).
#  Lỗi ở đây chỉ là cảnh báo (máy vẫn dùng được).
#    · /opt/cloudblue/state/seed.json (CHỈ root đọc): số lệnh, tên máy, vé đăng ký lại (ticket) + dấu phần cứng từ cb/job.json
#      → agent CloudBlue bản Linux dùng 1 lần để tự đăng ký lại đúng máy cũ trên web (vé chỉ nằm ở đây, đã gỡ khỏi phân vùng cứu hộ)
#    · agent CloudBlue bản Linux (cb/linux/agent trên phân vùng cứu hộ — khi có) → /opt/cloudblue + dịch vụ cloudblue.service
#    · CI_MODE=1 (GitHub CI): dịch vụ báo "máy mới đã khởi động tới giao diện" (ghi cb/linux-firstboot.ok lên phân vùng cứu hộ) rồi tắt máy
# =====================================================================================================
set -u
T="${1:-/mnt/cbroot}"
R="${CB_REC:-/run/archiso/img_dev}"
JOB="${CB_JOB:-$R/cb/job.json}"
say() { printf '[cloudblue post] %s\n' "$*"; }
[ -d "$T/etc" ] || { say "khong thay may moi o $T"; exit 0; }
REC_UUID=$(blkid -s UUID -o value "$(findmnt -no SOURCE "$R" 2>/dev/null)" 2>/dev/null)

install -d -m 0755 "$T/opt/cloudblue"
install -d -m 0700 "$T/opt/cloudblue/state"
python3 - "$JOB" "$T/opt/cloudblue/state/seed.json" "${REC_UUID:-}" <<'PYEOF'
import json, os, sys, time
try: job = json.load(open(sys.argv[1], encoding="utf-8-sig"))
except Exception: job = {}
seed = {k: job.get(k) for k in ("id", "os", "name", "ticket", "enroll_key", "hw") if job.get(k) is not None}
seed.update({"from": "job", "order": job.get("id"), "rec_uuid": sys.argv[3], "user": (job.get("linux") or {}).get("user"), "ts": int(time.time())})
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(seed, f, ensure_ascii=False)
PYEOF
chmod 600 "$T/opt/cloudblue/state/seed.json" 2>/dev/null && say "da ghi seed.json (chi root doc duoc)"

if [ -d "$R/cb/linux/agent" ]; then
    cp -a "$R/cb/linux/agent/." "$T/opt/cloudblue/" && say "da chep agent CloudBlue (Linux)"
    if [ -f "$T/opt/cloudblue/cloudblue.service" ]; then
        install -m 0644 "$T/opt/cloudblue/cloudblue.service" "$T/etc/systemd/system/cloudblue.service"
        arch-chroot "$T" systemctl enable cloudblue.service >/dev/null 2>&1 && say "da bat dich vu cloudblue"
    fi
else
    say "chua co agent CloudBlue ban Linux tren phan vung cuu ho (cb/linux/agent)"
fi

if [ "${CI_MODE:-0}" = 1 ] && [ -n "${REC_UUID:-}" ]; then
    install -d -m 0755 "$T/usr/local/sbin"
    cat > "$T/usr/local/sbin/cb-ci-firstboot" <<EOF
#!/bin/bash
# CloudBlue CI: máy CachyOS vừa cài đã khởi động → ghi kết quả lên phân vùng cứu hộ rồi tắt máy (chỉ có trên máy thử của GitHub CI)
for i in \$(seq 1 90); do systemctl is-active -q display-manager.service && break; sleep 2; done
sleep 25
mkdir -p /run/cbrec
mount -t ntfs3 UUID=$REC_UUID /run/cbrec 2>/dev/null || mount -t ntfs-3g UUID=$REC_UUID /run/cbrec 2>/dev/null || mount UUID=$REC_UUID /run/cbrec
{
  echo "CB_FIRSTBOOT_OK"
  echo "kernel=\$(uname -r)"
  echo "host=\$(cat /etc/hostname)"
  echo "dm=\$(systemctl is-active display-manager.service) \$(readlink /etc/systemd/system/display-manager.service)"
  echo "state=\$(systemctl is-system-running)"
  echo "user=\$(getent passwd 1000 | cut -d: -f1,7) groups=\$(id -nG \$(getent passwd 1000 | cut -d: -f1) 2>/dev/null | tr ' ' ',')"
  echo "sessions=\$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$3"@"\$5}' | tr '\n' ' ')"
  echo "nm=\$(systemctl is-active NetworkManager.service) ip=\$(ip -4 -o addr show scope global 2>/dev/null | awk '{print \$4}' | tr '\n' ' ')"
  echo "root=\$(findmnt -no SOURCE,FSTYPE,OPTIONS /)"
  echo "boot=\$(findmnt -no SOURCE,FSTYPE /boot)"
  echo "failed=\$(systemctl --failed --no-legend 2>/dev/null | awk '{print \$2}' | tr '\n' ' ')"
  echo "sudo_nopasswd=\$(grep -rls NOPASSWD /etc/sudoers.d 2>/dev/null | tr '\n' ' ')"
  echo "liveuser=\$(getent passwd liveuser >/dev/null && echo CON || echo khong)"
  echo "pkgs=\$(pacman -Qq | wc -l)"
} > /run/cbrec/cb/linux-firstboot.ok 2>&1
sync; umount /run/cbrec
systemctl poweroff
EOF
    chmod 755 "$T/usr/local/sbin/cb-ci-firstboot"
    printf '[Unit]\nDescription=CloudBlue CI firstboot probe\nAfter=display-manager.service network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/cb-ci-firstboot\n\n[Install]\nWantedBy=graphical.target\n' \
        > "$T/etc/systemd/system/cb-ci-firstboot.service"
    arch-chroot "$T" systemctl enable cb-ci-firstboot.service >/dev/null 2>&1 && say "CI: da bat dich vu bao khoi dong"
fi
echo "CloudBlue PC - cai bang cb-install $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$T/etc/cloudblue-release"
exit 0
