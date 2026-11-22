#!/usr/bin/env bash
# =====================================================================================================
#  cb-post.sh — CloudBlue PC: phần CloudBlue trên máy CachyOS vừa cài. cb-install.sh gọi khi máy mới còn gắn ở $1 (/mnt/cbroot).
#  Lỗi ở đây chỉ là cảnh báo (máy vẫn dùng được).
#    · /opt/cloudblue (CHỈ root vào được):
#        seed.json   số lệnh, tên máy, VÉ đăng ký lại (ticket) + dấu phần cứng từ cb/job.json → agent dùng 1 lần để đăng ký lại ĐÚNG máy cũ trên web
#                    (vé chỉ nằm ở đây, đã gỡ khỏi phân vùng cứu hộ; agent xoá vé ngay khi đăng ký xong)
#        cb.json     cấu hình của phân vùng cứu hộ (địa chỉ máy chủ + khoá CÔNG KHAI, các bản cài…; không có mã đăng ký)
#        agent/pcagent.py  lib/cbcore.py cbrec.py cbsys.py  linux/cbagent.py   agent CloudBlue bản Linux (dùng lại lõi agent Windows)
#        agent/pcremote.py  linux/cbremote.py  linux/cbcap.py                  điều khiển từ xa (giao thức của máy Windows + quay màn hình KDE)
#    · dịch vụ cloudblue.service (root, tự chạy lại khi thoát / cập nhật) — agent tự mở cbremote.py
#    · tài khoản khách: KDE không tự khoá màn hình / không tắt màn hình / không ngủ (máy cho thuê điều khiển từ xa)
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
NR=0
for f in agent/pcremote.py linux/cbremote.py linux/cbcap.py; do
    [ -f "$R/cb/$f" ] && install -m 0644 "$R/cb/$f" "$O/$f" && NR=$((NR + 1))
done
[ "$NR" = 3 ] && say "da chep dieu khien tu xa (pcremote + cbremote + cbcap)" || say "!! thieu file dieu khien tu xa ($NR/3) - may chua dieu khien tu xa duoc"
CU=$(python3 -c "import json,sys; print((json.load(open(sys.argv[1])).get('linux') or {}).get('user') or '')" "$JOB" 2>/dev/null)
CH=$(awk -F: -v u="$CU" '$1 == u {print $6}' "$T/etc/passwd" 2>/dev/null)
if [ -n "$CU" ] && [ -n "$CH" ] && [ -d "$T$CH" ]; then
    install -d -m 0755 "$T$CH/.config"
    printf '[Daemon]\nAutolock=false\nLockOnResume=false\nTimeout=0\n' > "$T$CH/.config/kscreenlockerrc"
    printf '[AC][Display]\nDimDisplayWhenIdle=false\nTurnOffDisplayWhenIdle=false\n\n[AC][SuspendAndShutdown]\nAutoSuspendAction=0\n' > "$T$CH/.config/powerdevilrc"
    arch-chroot "$T" chown -R "$CU:$CU" "$CH/.config" >/dev/null 2>&1
    say "KDE cua khach $CU: khong tu khoa / tat man hinh / ngu"
fi
# Con trỏ chuột VẼ BẰNG PHẦN MỀM: KWin dùng lớp con trỏ phần cứng thì rê chuột KHÔNG sinh khung hình mới cho luồng quay màn hình
# (người xem thấy con trỏ đứng yên tới khi màn hình đổi chỗ khác — CI 22.11f thấy rõ) · máy ảo QEMU còn mất hẳn con trỏ (KDE bug 482362).
install -d -m 0755 "$T/etc/environment.d"
# 22.11g: KWin cho chương trình điều khiển từ xa dùng THẲNG zkde_screencast + fake_input (không qua cổng XDG → không hộp hỏi trên màn hình máy;
# máy thật 139: cổng XDG treo chờ người bấm). Máy cho thuê 1 khách, phiên là của khách → tắt kiểm quyền giao diện hạn chế của KWin.
printf '# CloudBlue: dieu khien tu xa can con tro ve bang phan mem + quay man hinh / bam phim thang qua KWin\nKWIN_FORCE_SW_CURSOR=1\nKWIN_WAYLAND_NO_PERMISSION_CHECKS=1\n' > "$T/etc/environment.d/90-cloudblue-kwin.conf"
grep -q '^KWIN_FORCE_SW_CURSOR=' "$T/etc/environment" 2>/dev/null || echo 'KWIN_FORCE_SW_CURSOR=1' >> "$T/etc/environment"
grep -q '^KWIN_WAYLAND_NO_PERMISSION_CHECKS=' "$T/etc/environment" 2>/dev/null || echo 'KWIN_WAYLAND_NO_PERMISSION_CHECKS=1' >> "$T/etc/environment"
say "con tro chuot ve bang phan mem + KWin cho quay man hinh / bam phim truc tiep (khong hop hoi)"
install -d -m 0755 "$T/usr/share/applications"
printf '[Desktop Entry]\nType=Application\nName=CloudBlue - dieu khien tu xa\nExec=/usr/bin/true\nNoDisplay=true\n' > "$T/usr/share/applications/vn.cloudblue.remote.desktop"
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
for i in \$(seq 1 150); do grep -qs "het nguoi xem" /opt/cloudblue/logs/remote.log && break; sleep 2; done      # máy CI: người xem thử trên máy CI xem xong
sleep 10
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
  echo "--- agent.log"
  tail -n 12 /opt/cloudblue/logs/agent.log 2>/dev/null | cut -c1-200
  echo "input=\$(grep '^N: Name=' /proc/bus/input/devices 2>/dev/null | cut -d'"' -f2 | tr '\n' ',' | cut -c1-400)"
  echo "kwin_sw_cursor=\$(tr '\\0' '\\n' < /proc/\$(pidof kwin_wayland | cut -d' ' -f1)/environ 2>/dev/null | grep -c '^KWIN_FORCE_SW_CURSOR=1') kwin_noperm=\$(tr '\\0' '\\n' < /proc/\$(pidof kwin_wayland | cut -d' ' -f1)/environ 2>/dev/null | grep -c '^KWIN_WAYLAND_NO_PERMISSION_CHECKS=1')"
  echo "--- remote.log"
  tail -n 25 /opt/cloudblue/logs/remote.log 2>/dev/null | cut -c1-220
  tail -n 5 /opt/cloudblue/logs/remote.out 2>/dev/null | cut -c1-220
  echo "--- quyen KWin (22.11g)"
  echo "desktop=\$(grep -c '^X-KDE-Wayland-Interfaces=zkde_screencast_unstable_v1,org_kde_kwin_fake_input' /usr/share/applications/vn.cloudblue.cbcap.desktop 2>/dev/null) cbcap_py=\$(stat -c %a /usr/local/lib/cloudblue/cbcap-py 2>/dev/null) venv=\$(cat /usr/local/lib/cloudblue/pyvenv.cfg 2>/dev/null | head -1)"
  grep -a -E "KWin|kbuildsycoca|cbcap-py|cong XDG|mo duoc man hinh" /opt/cloudblue/logs/remote.log 2>/dev/null | tail -n 8 | cut -c1-260
  echo "--- cbcap probe (KWin truc tiep, cbcap-py)"
  install -D -m 0644 /opt/cloudblue/linux/cbcap.py /usr/local/lib/cloudblue/cbcap.py
  U=\$(getent passwd 1000 | cut -d: -f1)
  PY=/usr/local/lib/cloudblue/cbcap-py; [ -x "\$PY" ] || PY=python3
  timeout 120 runuser -u "\$U" -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus WAYLAND_DISPLAY=wayland-0 \
      "\$PY" -I -B /usr/local/lib/cloudblue/cbcap.py probe 4 2>&1 | tail -n 3 | cut -c1-1500
  echo "--- cbcap probe (man hinh ao: may khong cam man hinh, 22.11h)"
  timeout 120 runuser -u "\$U" -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus WAYLAND_DISPLAY=wayland-0 CBCAP_VIRTUAL=1 \
      "\$PY" -I -B /usr/local/lib/cloudblue/cbcap.py probe 4 2>&1 | tail -n 3 | cut -c1-1500
  echo "--- cbcap probe (cong XDG, duong phu)"
  timeout 120 runuser -u "\$U" -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus WAYLAND_DISPLAY=wayland-0 CBCAP_NO_KWIN=1 \
      python3 -I -B /usr/local/lib/cloudblue/cbcap.py probe 4 2>&1 | tail -n 3 | cut -c1-1500
  echo "--- app cho khach (23/11: khach bao khong co trinh duyet, khong mo duoc terminal)"
  echo "nguoi xem CI da mo qua menu: konsole=\$(pgrep -u "\$U" -c -x konsole || true) firefox=\$(pgrep -u "\$U" -c -f /usr/lib/firefox/firefox || true) units=\$(runuser -u "\$U" -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user list-units --no-legend 'app-*konsole*' 'app-*firefox*' 2>/dev/null | awk '{print \$1}' | tr '\n' ' ' | cut -c1-300)"
  for p in firefox chromium konsole dolphin kate alacritty spectacle ark gwenview okular plasma-desktop plasma-workspace kactivitymanagerd kio systemsettings cachyos-hello octopi shelly; do
    printf '%s=%s ' "\$p" "\$(pacman -Q "\$p" 2>/dev/null | cut -d' ' -f2 || true)"; done; echo
  echo "desktop_files=\$(ls /usr/share/applications/*.desktop 2>/dev/null | wc -l) co: \$(ls /usr/share/applications 2>/dev/null | grep -i -E 'firefox|konsole|dolphin|kate|alacritty|systemsettings' | tr '\n' ' ')"
  SP=\$(pgrep -u "\$U" -x plasmashell | head -1)
  echo "plasmashell=\$SP kactivity=\$(pgrep -u "\$U" -c kactivitymanage) user_systemd=\$(pgrep -u "\$U" -cx systemd) krunner=\$(pgrep -u "\$U" -c krunner)"
  if [ -n "\$SP" ]; then
    tr '\\0' '\\n' < /proc/\$SP/environ | grep -E '^(WAYLAND_DISPLAY|DISPLAY|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP|XDG_DATA_DIRS|XDG_CONFIG_DIRS|PATH|KDE_FULL_SESSION|QT_QPA_PLATFORM|XDG_MENU_PREFIX|HOME|LANG)=' > /run/cb-senv
    cut -c1-300 /run/cb-senv
  fi
  SE=\$(tr '\n' ' ' < /run/cb-senv 2>/dev/null)
  echo "systemd_user=\$(runuser -u "\$U" -- env \$SE systemctl --user is-system-running 2>&1 | head -1) failed_user=\$(runuser -u "\$U" -- env \$SE systemctl --user --failed --no-legend 2>/dev/null | awk '{print \$2}' | tr '\n' ' ' | cut -c1-300)"
  echo "menu_entries=\$(timeout 60 runuser -u "\$U" -- env \$SE kbuildsycoca6 --menutest 2>/dev/null | wc -l) menu_co: \$(timeout 60 runuser -u "\$U" -- env \$SE kbuildsycoca6 --menutest 2>/dev/null | grep -i -E 'firefox|konsole|dolphin' | cut -c1-80 | tr '\n' ';')"
  echo "favorites: \$(grep -h -i -E '^favorites|^favoriteApps|preferred://' /home/\$U/.config/plasma-org.kde.plasma.desktop-appletsrc /etc/xdg/kickoffrc /usr/share/plasma/plasmoids/org.kde.plasma.kickoff/contents/config/main.xml 2>/dev/null | cut -c1-200 | tr '\n' ';')"
  echo "skel: \$(ls -A /etc/skel 2>/dev/null | tr '\n' ' ') home: \$(ls -A /home/\$U 2>/dev/null | tr '\n' ' ') config: \$(ls /home/\$U/.config 2>/dev/null | tr '\n' ' ' | cut -c1-600)"
  for app in konsole firefox dolphin; do
    command -v \$app >/dev/null || { echo "mo_\$app=khong_co_lenh"; continue; }
    runuser -u "\$U" -- env \$SE \$app >/run/cb-\$app.out 2>&1 &
    sleep 12
    echo "mo_\$app (chay thang)=\$(pgrep -u "\$U" -c -x \$app || true) \$(pgrep -u "\$U" -c -f /usr/lib/firefox/firefox 2>/dev/null | head -1) | \$(tail -n 3 /run/cb-\$app.out 2>/dev/null | tr '\n' ' ' | cut -c1-300)"
    pkill -u "\$U" -x \$app 2>/dev/null; pkill -u "\$U" -f /usr/lib/firefox/firefox 2>/dev/null; sleep 2
  done
  if [ -f /usr/share/applications/org.kde.konsole.desktop ]; then        # đường của menu KDE: KIO → systemd --user (giống bấm trong menu)
    timeout 30 runuser -u "\$U" -- env \$SE kioclient exec /usr/share/applications/org.kde.konsole.desktop > /run/cb-kio.out 2>&1
    sleep 8; echo "mo_konsole (qua KIO nhu menu)=\$(pgrep -u "\$U" -c -x konsole || true) units=\$(runuser -u "\$U" -- env \$SE systemctl --user list-units --no-legend 'app-*' 2>/dev/null | awk '{print \$1}' | tr '\n' ' ' | cut -c1-300) | \$(tail -n 3 /run/cb-kio.out | tr '\n' ' ' | cut -c1-300)"
    pkill -u "\$U" -x konsole 2>/dev/null
  fi
  echo "journal: \$(journalctl -b _UID=1000 --no-pager -o cat 2>/dev/null | grep -i -E 'launch|kioexec|failed to start|could not|konsole|firefox' | tail -n 8 | cut -c1-200 | tr '\n' ';')"
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
