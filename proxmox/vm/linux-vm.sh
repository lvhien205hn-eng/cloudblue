#!/bin/bash
# =====================================================================================================
#  cloudblue-linux-vm (ban 27.11a) - DUNG MAY MAU VPS NVMe LINUX: Ubuntu 24.04 + giao dien XFCE + CloudBlue (dieu khien trong web / app) + OpenClaw.
#  cbhost (may chu Proxmox) tao may ao tu anh Ubuntu cloud CHINH CHU, cloud-init ghi /opt/cloudblue/cb.json roi chay file nay (root, co mang).
#    - tai khoan khach "vps" (sudo khong hoi mat khau, khong mat khau), tu dang nhap XFCE (LightDM), khong khoa / tat man hinh, 1920x1080
#    - agent CloudBlue ban Linux (/opt/cloudblue, dich vu cloudblue) - CHUA dang ky: moi VPS nhan ban tu may mau nhan ve 1 lan tu cbhost
#    - OpenClaw (bo cai chinh thuc openclaw.ai, --no-onboard) + loi tat "OpenClaw - cai dat" o man hinh nen; Firefox (kho APT cua Mozilla)
#  Xong: ghi /var/lib/cloudblue/maymau.done (cbhost doc qua QEMU guest agent roi tu luu thanh may mau). Nhat ky: /var/log/cloudblue-maymau.log
#  Bien: CB_RAW (kho file, mac dinh GitHub main) · CB_NO_OPENCLAW=1 · CB_NO_FIREFOX=1
# =====================================================================================================
set -u
VER=27.11a
RAW=${CB_RAW:-https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main}
U=vps
O=/opt/cloudblue
D=/var/lib/cloudblue
LOG=/var/log/cloudblue-maymau.log
mkdir -p "$D"
exec >>"$LOG" 2>&1
say() { echo "[cloudblue $(date +%H:%M:%S)] $*"; }
fail() { say "LOI: $*"; echo "$(date '+%F %T') $*" > "$D/maymau.loi"; exit 1; }
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
say "=== dung may mau VPS NVMe Linux (ban $VER) - $(. /etc/os-release; echo "$PRETTY_NAME")"
[ -s "$O/cb.json" ] || fail "thieu $O/cb.json (cloud-init cua cbhost chua ghi)"

apt_try() { for i in 1 2 3; do apt-get -o DPkg::Lock::Timeout=600 "$@" && return 0; say "apt-get $1 loi (lan $i) - thu lai"; sleep 20; done; return 1; }
apt_try update -q || fail "apt-get update loi (chua co mang?)"
PKGS="qemu-guest-agent xserver-xorg xserver-xorg-video-dummy xfce4 xfce4-terminal xfce4-notifyd thunar mousepad lightdm lightdm-gtk-greeter dbus-x11 dbus-user-session
 at-spi2-core gvfs x11-xserver-utils xdg-user-dirs ffmpeg python3 python3-xlib xclip fonts-noto-core fonts-noto-color-emoji fonts-dejavu-core
 curl ca-certificates sudo cloud-guest-utils"
apt_try install -y -q --no-install-recommends $PKGS || fail "cai goi giao dien / cong cu loi"
systemctl enable --now qemu-guest-agent >/dev/null 2>&1 || true
say "da cai XFCE + LightDM + ffmpeg + python3-xlib + QEMU guest agent"

# ---- tai khoan khach + tu dang nhap + man hinh
id "$U" >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo "$U"
passwd -d "$U" >/dev/null
groupadd -f autologin; usermod -aG autologin,sudo "$U"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$U" > /etc/sudoers.d/90-cloudblue-vps; chmod 440 /etc/sudoers.d/90-cloudblue-vps
install -d /etc/lightdm/lightdm.conf.d
printf '[LightDM]\nlogind-check-graphical=false\n[Seat:*]\nautologin-user=%s\nautologin-user-timeout=0\nautologin-session=xfce\nuser-session=xfce\ndisplay-setup-script=/usr/local/bin/cloudblue-res\n' "$U" \
  > /etc/lightdm/lightdm.conf.d/50-cloudblue-autologin.conf
cat > /usr/local/bin/cloudblue-res <<'EOF'
#!/bin/sh
# CloudBlue: man hinh 1920x1080 (may ao khong cam man hinh that)
o=$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')
[ -n "$o" ] && { xrandr --output "$o" --mode 1920x1080 2>/dev/null || { xrandr --newmode 1920x1080_cb 173.00 1920 2048 2248 2576 1080 1083 1088 1120 -hsync +vsync; xrandr --addmode "$o" 1920x1080_cb; xrandr --output "$o" --mode 1920x1080_cb; }; } 2>/dev/null
xset s off -dpms 2>/dev/null
exit 0
EOF
chmod 755 /usr/local/bin/cloudblue-res
install -d /etc/X11/xorg.conf.d
# man hinh AO (driver dummy): anh cloud Ubuntu khong co driver card bochs (VGA std cua Proxmox) -> Xorg khong len.
# Man hinh ao khong can card / driver nhan, luon 1920x1080; khach xem qua CloudBlue (x11grab), khong qua console Proxmox.
cat > /etc/X11/xorg.conf.d/20-cloudblue-dummy.conf <<'EOF'
Section "Device"
    Identifier "cbdummy"
    Driver "dummy"
    VideoRam 65536
EndSection
Section "Monitor"
    Identifier "cbmon"
    HorizSync 28.0-80.0
    VertRefresh 48.0-75.0
    Modeline "1920x1080" 148.50 1920 2008 2052 2200 1080 1084 1089 1125 +hsync +vsync
    Modeline "1600x900" 108.00 1600 1624 1704 1800 900 901 904 1000 +hsync +vsync
    Modeline "1366x768" 85.50 1366 1436 1579 1792 768 771 774 798 +hsync +vsync
    Modeline "1280x720" 74.25 1280 1390 1430 1650 720 725 730 750 +hsync +vsync
EndSection
Section "Screen"
    Identifier "cbscreen"
    Device "cbdummy"
    Monitor "cbmon"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080" "1600x900" "1366x768" "1280x720"
        Virtual 1920 1080
    EndSubSection
EndSection
EOF
printf 'Section "ServerFlags"\n  Option "BlankTime" "0"\n  Option "StandbyTime" "0"\n  Option "SuspendTime" "0"\n  Option "OffTime" "0"\nEndSection\n' > /etc/X11/xorg.conf.d/10-cloudblue-noblank.conf
install -d /etc/xdg/autostart
printf '[Desktop Entry]\nType=Application\nName=CloudBlue - man hinh\nExec=/usr/local/bin/cloudblue-res\nNoDisplay=true\n' > /etc/xdg/autostart/cloudblue-res.desktop
for f in light-locker xfce4-screensaver xfce4-power-manager; do [ -f /etc/xdg/autostart/$f.desktop ] && printf 'Hidden=true\n' >> /etc/xdg/autostart/$f.desktop; done
printf 'blacklist floppy\n' > /etc/modprobe.d/cloudblue-nofloppy.conf      # khong hien "Floppy Disk" tren man hinh nen
timedatectl set-timezone Asia/Ho_Chi_Minh 2>/dev/null || ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime
systemctl set-default graphical.target >/dev/null 2>&1
say "tai khoan khach $U: tu dang nhap XFCE, khong khoa / tat man hinh, 1920x1080, gio Viet Nam"

# ---- Firefox (kho APT chinh thuc cua Mozilla - ban .deb, khong dung snap)
if [ "${CB_NO_FIREFOX:-0}" != 1 ]; then
  install -d -m 0755 /etc/apt/keyrings
  if curl -fsSL --retry 3 https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc; then
    echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list
    printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla
    apt_try update -q && apt_try install -y -q firefox && say "da cai Firefox (Mozilla APT)" || say "!! chua cai duoc Firefox (bo qua)"
  else say "!! khong tai duoc khoa kho Mozilla - bo qua Firefox"; fi
fi

# ---- agent CloudBlue (ban Linux) - chua dang ky
install -d -m 0700 "$O" "$O/agent" "$O/lib" "$O/linux" "$O/logs" "$O/os"
for f in agent/pcagent.py agent/pcremote.py lib/cbcore.py lib/cbrec.py lib/cbsys.py linux/cbagent.py linux/cbremote.py linux/cbcap.py; do
  curl -fsSL --retry 5 "$RAW/winpc/$f" -o "$O/$f.part" && python3 -c "import sys; compile(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1], 'exec')" "$O/$f.part" \
    && mv -f "$O/$f.part" "$O/$f" || fail "tai $f loi"
  chmod 644 "$O/$f"
done
chmod 600 "$O/cb.json"
echo "{}" > "$O/identity.json"; echo "{}" > "$O/seed.json"; chmod 600 "$O/identity.json" "$O/seed.json"
date '+%F %T' > /etc/cloudblue-vm
printf '[Desktop Entry]\nType=Application\nName=CloudBlue - dieu khien tu xa\nExec=/usr/bin/true\nNoDisplay=true\n' > /usr/share/applications/vn.cloudblue.remote.desktop
printf '%s\n' '[Unit]' 'Description=CloudBlue PC agent (VPS NVMe Linux)' 'Wants=network-online.target' 'After=network-online.target' '' \
  '[Service]' 'ExecStart=/usr/bin/python3 -I -B /opt/cloudblue/linux/cbagent.py run' 'Restart=always' 'RestartSec=15' '' \
  '[Install]' 'WantedBy=multi-user.target' > /etc/systemd/system/cloudblue.service
systemctl daemon-reload; systemctl enable cloudblue.service >/dev/null 2>&1 || fail "khong bat duoc dich vu cloudblue"
python3 -I -B "$O/linux/cbagent.py" selfcheck 2>&1 | tail -n 2
say "da cai agent CloudBlue (Linux) + dich vu cloudblue (cho ve dang ky tu may chu)"

# ---- OpenClaw (bo cai chinh thuc, khong chay buoc cai dat ban dau - khach tu chay "openclaw onboard")
OC=""
if [ "${CB_NO_OPENCLAW:-0}" != 1 ]; then
  for i in 1 2; do
    curl -fsSL --retry 3 https://openclaw.ai/install.sh -o /root/openclaw-install.sh && HOME=/root bash /root/openclaw-install.sh --no-onboard </dev/null && break
    say "cai OpenClaw loi (lan $i)"; sleep 20
  done
  OC=$(command -v openclaw || ls /usr/local/bin/openclaw /usr/bin/openclaw 2>/dev/null | head -1)
  [ -n "$OC" ] && say "da cai OpenClaw: $("$OC" --version 2>/dev/null | head -1)" || say "!! chua cai duoc OpenClaw"
fi

# ---- loi tat man hinh nen (1 lan, luc khach dang nhap lan dau: XFCE can danh dau loi tat "tin cay")
cat > /usr/local/bin/cloudblue-desk <<'EOF'
#!/bin/bash
# CloudBlue: loi tat man hinh nen cho khach (1 lan / tai khoan)
M="$HOME/.config/cloudblue-desk.done"; [ -f "$M" ] && exit 0
D=$(xdg-user-dir DESKTOP 2>/dev/null); [ -z "$D" ] || [ "$D" = "$HOME" ] && D="$HOME/Desktop"; mkdir -p "$D"
mk() { f="$D/$1.desktop"; printf '%s\n' '[Desktop Entry]' 'Type=Application' "Name=$2" "Exec=$3" "Icon=$4" 'Terminal=false' > "$f"; chmod +x "$f"
       gio set "$f" metadata::xfce-exe-checksum "$(sha256sum "$f" | cut -d' ' -f1)" 2>/dev/null; }
mk terminal "Terminal" "xfce4-terminal" org.xfce.terminal
command -v firefox >/dev/null && mk firefox "Firefox" "firefox" firefox
command -v openclaw >/dev/null && mk openclaw "OpenClaw - cài đặt" "xfce4-terminal --hold -T OpenClaw -e 'openclaw onboard --install-daemon'" org.xfce.terminal
mkdir -p "$HOME/.config"; date > "$M"
EOF
chmod 755 /usr/local/bin/cloudblue-desk
printf '[Desktop Entry]\nType=Application\nName=CloudBlue - loi tat\nExec=/usr/local/bin/cloudblue-desk\nNoDisplay=true\n' > /etc/xdg/autostart/cloudblue-desk.desktop

# ---- don + bat giao dien de kiem
systemctl disable --now ssh.service ssh.socket >/dev/null 2>&1; rm -f /etc/ssh/ssh_host_*
apt-get clean; rm -f /root/openclaw-install.sh
systemctl start lightdm.service >/dev/null 2>&1
for i in $(seq 1 45); do pgrep -u "$U" -x xfce4-session >/dev/null && break; sleep 2; done
pgrep -u "$U" -x xfce4-session >/dev/null && say "XFCE cua khach $U da len" || say "!! XFCE chua len (van luu may mau - lan bat sau se len)"
{ echo "ok $VER $(date '+%F %T')"; echo "openclaw=${OC:+co}"; echo "firefox=$(command -v firefox >/dev/null && echo co)"; } > "$D/maymau.done"
say "=== XONG may mau ($VER)"
exit 0
