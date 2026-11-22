#!/usr/bin/env bash
# =====================================================================================================
#  cb-post.sh — CloudBlue PC: phần CloudBlue trên máy CachyOS vừa cài. cb-install.sh gọi khi máy mới còn gắn ở $1 (/mnt/cbroot).
#  Lỗi ở đây chỉ là cảnh báo (máy vẫn dùng được).
#    · /opt/cloudblue (CHỈ root vào được):
#        seed.json   số lệnh, tên máy, VÉ đăng ký lại (ticket) + dấu phần cứng từ cb/job.json → agent dùng 1 lần để đăng ký lại ĐÚNG máy cũ trên web
#                    (vé chỉ nằm ở đây, đã gỡ khỏi phân vùng cứu hộ; agent xoá vé ngay khi đăng ký xong)
#        cb.json     cấu hình của phân vùng cứu hộ (địa chỉ máy chủ + khoá CÔNG KHAI, các bản cài…; không có mã đăng ký)
#        agent/pcagent.py  lib/cbcore.py cbrec.py cbsys.py  linux/cbagent.py   agent CloudBlue bản Linux (dùng lại lõi agent Windows)
#    · dịch vụ cloudblue.service (root, tự chạy lại khi thoát / cập nhật)
#    · CI_MODE=1 (GitHub CI): dịch vụ báo "máy mới đã khởi động tới giao diện" + tình trạng agent (ghi cb/linux-firstboot.ok lên phân vùng cứu hộ) rồi tắt máy
# =====================================================================================================
set -u
T="${1:-/mnt/cbroot}"
R="${CB_REC:-/run/archiso/img_dev}"
JOB="${CB_JOB:-$R/cb/job.json}"
O="$T/opt/cloudblue"
say() { printf '[cloudblue post] %s\n' "$*"; }
[ -d "$T/etc" ] || { say "khong thay may moi o $T"; exit 0; }
REC_UUID=$(blkid -s UUID -o value "$(findmnt -no SOURCE "$R" 2>/dev/null)" 2>/dev/null)

install -d -m 0700 "$O" "$O/agent" "$O/lib" "$O/linux" "$O/logs" "$O/os"
python3 - "$JOB" "$O/seed.json" "${REC_UUID:-}" <<'PYEOF'
import json, os, sys, time
try: job = json.load(open(sys.argv[1], encoding="utf-8-sig"))
except Exception: job = {}
seed = {k: job.get(k) for k in ("id", "os", "name", "ticket", "enroll_key", "hw") if job.get(k) is not None}
seed.update({"from": "job", "order": job.get("id"), "pe": "cb-install", "rec_uuid": sys.argv[3], "user": (job.get("linux") or {}).get("user"), "ts": int(time.time())})
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(seed, f, ensure_ascii=False)
PYEOF
chmod 600 "$O/seed.json" 2>/dev/null && say "da ghi seed.json (chi root doc duoc)"

[ -f "$R/cb/cb.json" ] && install -m 0600 "$R/cb/cb.json" "$O/cb.json"
[ -f "$R/cb/os/cacert.pem" ] && install -m 0644 "$R/cb/os/cacert.pem" "$O/os/cacert.pem"
N=0
for f in agent/pcagent.py lib/cbcore.py lib/cbrec.py lib/cbsys.py linux/cbagent.py; do
    [ -f "$R/cb/$f" ] && install -m 0644 "$R/cb/$f" "$O/$f" && N=$((N + 1))
done
if [ "$N" = 5 ] && [ -f "$O/cb.json" ]; then
    printf '%s\n' '[Unit]' 'Description=CloudBlue PC agent' 'Wants=network-online.target' 'After=network-online.target' '' \
        '[Service]' 'ExecStart=/usr/bin/python3 -I -B /opt/cloudblue/linux/cbagent.py run' 'Restart=always' 'RestartSec=15' '' \
        '[Install]' 'WantedBy=multi-user.target' > "$T/etc/systemd/system/cloudblue.service"
    if arch-chroot "$T" systemctl enable cloudblue.service >/dev/null 2>&1; then
        say "da chep agent CloudBlue (Linux) + bat dich vu cloudblue"
    else
        say "!! khong bat duoc dich vu cloudblue"
    fi
    arch-chroot "$T" /usr/bin/python3 -I -B /opt/cloudblue/linux/cbagent.py selfcheck 2>&1 | tail -n 2 | sed 's/^/[cloudblue post]   /'
else
    say "!! phan vung cuu ho thieu agent CloudBlue ban Linux ($N/5 file agent/pcagent.py lib/*.py linux/cbagent.py, cb.json) - may se KHONG hien tren web"
fi

if [ "${CI_MODE:-0}" = 1 ] && [ -n "${REC_UUID:-}" ]; then
    install -d -m 0755 "$T/usr/local/sbin"
    cat > "$T/usr/local/sbin/cb-ci-firstboot" <<EOF
#!/bin/bash
# CloudBlue CI: máy CachyOS vừa cài đã khởi động → ghi kết quả + tình trạng agent lên phân vùng cứu hộ rồi tắt máy (chỉ có trên máy thử của GitHub CI)
for i in \$(seq 1 90); do systemctl is-active -q display-manager.service && break; sleep 2; done
for i in \$(seq 1 45); do grep -qs "ĐÃ ĐĂNG KÝ" /opt/cloudblue/logs/agent.log && break; sleep 2; done
sleep 15
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
  echo "pkgs=\$(pacman -Qq | wc -l) python=\$(pacman -Q python 2>/dev/null | cut -d' ' -f2) efibootmgr=\$(pacman -Q efibootmgr 2>/dev/null | cut -d' ' -f2)"
  echo "agent=\$(systemctl is-active cloudblue.service) opt=\$(stat -c %a /opt/cloudblue 2>/dev/null) seed_ticket=\$(grep -c ticket /opt/cloudblue/seed.json 2>/dev/null) identity=\$(stat -c %a /opt/cloudblue/identity.json 2>/dev/null)"
  echo "xs=\$(ls /usr/share/xsessions 2>/dev/null | tr '\n' ' ') ws=\$(ls /usr/share/wayland-sessions 2>/dev/null | tr '\n' ' ')"
  echo "stype=\$(for s in \$(loginctl list-sessions --no-legend 2>/dev/null | awk '{print \$1}'); do loginctl show-session \$s -p Type -p Class -p Desktop --value 2>/dev/null | tr '\n' '/'; printf ' '; done)"
  echo "pk=\$(pacman -Q plasma-x11-session xorg-server xorg-xwayland ffmpeg xdotool xclip wl-clipboard libxtst libva-mesa-driver kpipewire krdp kwin plasma-workspace 2>&1 | tr '\n' ',')"
  echo "ff_enc=\$(ffmpeg -hide_banner -encoders 2>/dev/null | grep -Eo '(h264_nvenc|h264_vaapi|h264_qsv|h264_amf|libx264|libopenh264)' | sort -u | tr '\n' ' ') ff_dev=\$(ffmpeg -hide_banner -devices 2>/dev/null | grep -Eo '(x11grab|kmsgrab|pipewiregrab|fbdev)' | sort -u | tr '\n' ' ')"
  echo "xorg=\$(ps -eo args 2>/dev/null | grep -E '^/usr/(lib/)?(Xorg|Xwayland|bin/X)' | head -2 | cut -c1-160 | tr '\n' '|')"
  echo "uinput=\$(ls -l /dev/uinput 2>&1 | cut -c1-60) drm=\$(ls /dev/dri 2>/dev/null | tr '\n' ' ')"
  echo "--- agent.log"
  tail -n 12 /opt/cloudblue/logs/agent.log 2>/dev/null | cut -c1-200
} > /run/cb-firstboot.txt 2>&1
systemctl stop cloudblue.service
{ echo "--- cbagent.py status"; /usr/bin/python3 -I -B /opt/cloudblue/linux/cbagent.py status 2>&1 | tr -s ' \n' ' ' | cut -c1-1500; echo; } >> /run/cb-firstboot.txt
mkdir -p /run/cbrec
mount -t ntfs3 UUID=$REC_UUID /run/cbrec 2>/dev/null || mount -t ntfs-3g UUID=$REC_UUID /run/cbrec 2>/dev/null || mount UUID=$REC_UUID /run/cbrec
cp /run/cb-firstboot.txt /run/cbrec/cb/linux-firstboot.ok
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
