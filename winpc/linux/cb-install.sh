#!/usr/bin/env bash
# =====================================================================================================
#  cb-install.sh — CloudBlue PC: CÀI CachyOS KHÔNG NGƯỜI. Chạy trong máy sống CachyOS (mở thẳng từ file ISO trên phân vùng cứu hộ
#  bằng GRUB, xem grub.cfg), systemd gọi bằng tham số nhân  systemd.run=/usr/bin/bash /run/archiso/img_dev/cb/linux/cb-install.sh
#    · /run/archiso/img_dev   = phân vùng cứu hộ CBRECOVERY (NTFS) — archiso gắn sẵn (chỉ đọc) → gắn lại có ghi
#    · /run/archiso/bootmnt   = chính file ISO CachyOS (archiso gắn) — lấy hệ thống từ arch/x86_64/airootfs.sfs
#    · cb/job.json            = việc WinPE giao: mục "linux" = vị trí 2 phân vùng (EFI Linux + gốc), tài khoản khách, múi giờ…
#
#  CÁCH CÀI (giống chế độ "offline" của bộ cài Calamares của CachyOS — KHÔNG dùng cachyos-installer: chế độ không người của nó luôn XOÁ CẢ Ổ,
#  sẽ mất phân vùng cứu hộ đang chứa chính ISO này + EFI của Windows):
#    định dạng 2 phân vùng WinPE đã tạo (FAT32 + btrfs có subvolume như CachyOS) → bung airootfs.sfs → bỏ phần chỉ dành cho máy sống
#    → nhân + initramfs → tài khoản khách, tên máy, múi giờ, tự đăng nhập → khoá pacman, gỡ gói của máy sống
#    → KHÔNG dùng driver NVIDIA (22.11e: chủ shop chốt — Linux chỉ cần điều khiển từ xa, không cần card hình; card NVIDIA chạy driver nouveau
#      có sẵn) · công cụ quay màn hình (gst-plugin-pipewire) thiếu thì tải ĐÚNG phiên bản PipeWire đang có (cần mạng; không có thì agent tự cài sau)
#    → systemd-boot trên EFI Linux (mục "Linux Boot Manager" lên đầu BootOrder) → cb-post.sh (agent CloudBlue) → báo xong → khởi động lại.
#  Lỗi → ghi lý do (cb/job-result.json + cb/job.json "linux_fail") → lần khởi động sau vào Windows Boot Manager = WinPE cứu hộ: thử lại,
#  quá 2 lần thì WinPE cài lại Windows mặc định (máy không bao giờ "mất").
#  Kết quả: cb/job-result.json · cb/job.done.json · cb/linux/installed.json · nhật ký cb/logs/linux-install-<giờ>.log
#
#  Thử trên GitHub CI (QEMU):  job.json "test": true → chỉ chứng minh đường GRUB → ISO → script (ghi cb/linux-test.ok) rồi tắt máy
#                              job.json "ci": true   → cài THẬT như máy thật + thêm cổng nối tiếp + dịch vụ báo "đã khởi động" (cb/linux-firstboot.ok)
# =====================================================================================================
set -u
CB_VER="22.11f"
R=/run/archiso/img_dev
ISO=/run/archiso/bootmnt
W=/tmp/cb
T=/mnt/cbroot
mkdir -p "$W"
LOG="$W/install.log"
exec > >(tee -a "$LOG" /dev/console) 2>&1
say() { printf '[cloudblue %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
T0=$(date +%s)

say "cb-install $CB_VER bat dau ($(uname -r)) · $(findmnt -no FSTYPE,OPTIONS "$R" 2>/dev/null)"
mount -o remount,rw "$R" 2>/dev/null || mount -o remount,rw,force "$R" 2>/dev/null || say "!! khong gan lai duoc phan vung cuu ho de ghi (van tiep tuc)"
say "phan vung cuu ho sau khi gan lai: $(findmnt -no FSTYPE,OPTIONS "$R" 2>/dev/null)"
date +"%s cb-install $CB_VER da chay" > "$R/cb/linux-started.txt" 2>/dev/null && sync || say "!! chua ghi duoc len phan vung cuu ho"
# systemd.run= cho máy sống chỉ chạy tới basic.target + script này → bật thêm multi-user.target (KHÔNG chờ, KHÔNG isolate — script vẫn chạy tiếp):
# NetworkManager (tải driver card đồ hoạ), pacman-init (khoá ký gói), logind… như máy sống khởi động bình thường (trừ màn hình đồ hoạ).
systemctl start --no-block multi-user.target 2>/dev/null || say "!! chua bat duoc multi-user.target"

net_wait() {   # net_wait <số giây> → 0 khi tới được kho gói CachyOS / Arch
    local end=$(( $(date +%s) + $1 ))
    while [ "$(date +%s)" -lt "$end" ]; do
        if curl -fsS -m 8 -o /dev/null https://mirror.cachyos.org/ 2>/dev/null || curl -fsS -m 8 -o /dev/null https://geo.mirror.pkgbuild.com/ 2>/dev/null; then return 0; fi
        sleep 5
    done
    return 1
}
keyring_wait() {   # khoá ký gói của pacman (máy sống) đã dựng xong (pacman-init.service) → 0 · chờ tối đa 5 phút
    local i
    for i in $(seq 1 60); do
        if systemctl cat pacman-init.service >/dev/null 2>&1; then
            [ "$(systemctl is-active pacman-init.service 2>/dev/null)" = active ] && return 0
        elif [ -s /etc/pacman.d/gnupg/pubring.gpg ] || [ -s /etc/pacman.d/gnupg/pubring.kbx ]; then
            return 0
        fi
        sleep 5
    done
    return 1
}
JOB="$R/cb/job.json"
RES="$R/cb/job-result.json"

py() { python3 - "$@"; }

result() {   # result <done|failed|running> <thông điệp> — ghi kết quả cho agent / WinPE (giống bộ cài WinPE: id, ok, msg, os, secs)
    py "$JOB" "$RES" "$1" "$2" "$T0" "$CB_VER" <<'PYEOF'
import json, os, sys, time
job_p, res_p, st, msg, t0, ver = sys.argv[1:7]
try: job = json.load(open(job_p, encoding="utf-8-sig"))
except Exception: job = {}
res = {"id": job.get("id"), "ok": st == "done", "msg": msg[:300], "os": job.get("os"), "pe": "cb-install " + ver, "secs": int(time.time() - int(t0)),
       "ts": int(time.time()), "state": st}
def save(p, obj):
    with open(p + ".tmp", "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)
save(res_p, res)
if st == "done":                                   # xong: đóng lệnh như WinPE (job.done.json, KHÔNG còn vé / mã bí mật) → WinPE không bao giờ làm lại
    done = {k: v for k, v in job.items() if k not in ("ticket", "enroll_key")}
    done["state"] = "done"; done.get("linux", {}).pop("pass", None)
    save(os.path.join(os.path.dirname(job_p), "job.done.json"), done)
    try: os.remove(job_p)
    except OSError: pass
elif st == "failed":                               # lỗi: GIỮ lệnh (state running) để WinPE thử lại; quá 2 lần WinPE cài lại Windows
    job["linux_fail"] = int(job.get("linux_fail") or 0) + 1; job["linux_msg"] = msg[:300]
    save(job_p, job)
PYEOF
    sync
}

save_log() {
    mkdir -p "$R/cb/logs" 2>/dev/null
    sed -E 's/("(user_pass|root_pass|pass)": *")[^"]*"/\1***"/g' "$LOG" > "$R/cb/logs/linux-install-$(date +%Y%m%d-%H%M%S).log" 2>/dev/null
    sync
}

undo_mounts() { sync; umount -R "$T" 2>/dev/null || umount -lR "$T" 2>/dev/null; true; }

back_to_pe() {   # lỗi: về WinPE cứu hộ (Windows Boot Manager mặc định = WinPE) để thử lại / cài lại Windows
    say "!! $1"
    undo_mounts
    result failed "$1"
    local wbm
    wbm=$(efibootmgr 2>/dev/null | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\)\*\{0,1\} Windows Boot Manager.*/\1/p' | head -1)
    [ -n "$wbm" ] && efibootmgr -q -n "$wbm" && say "lan khoi dong sau: Windows Boot Manager ($wbm) -> WinPE cuu ho"
    save_log
    sleep 15
    if [ "${CI_MODE:-0}" = 1 ]; then systemctl poweroff; else systemctl reboot; fi
    exit 1
}

[ -f "$JOB" ] || back_to_pe "khong thay cb/job.json tren phan vung cuu ho"

# ---------------------------------------------------------------- chế độ THỬ (GitHub CI): chỉ chứng minh đường khởi động
if py "$JOB" <<'PYEOF'
import json, sys
sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8-sig")).get("test") else 1)
PYEOF
then
    ( sleep 480; say "!! che do thu: qua 8 phut -> tat may"; sync; systemctl poweroff -ff ) &      # máy thử không bao giờ treo tới hết giờ CI
    say "che do thu: cho mang (toi da 3 phut) + khoa pacman (toi da 5 phut)"
    NETOK=no; net_wait 180 && NETOK=yes
    say "mang: $NETOK"
    KEYOK=no; keyring_wait && KEYOK=yes
    say "khoa pacman: $KEYOK"
    {
        echo "CB_TEST_OK $CB_VER"
        echo "kernel=$(uname -r)"
        echo "img_dev=$(findmnt -no SOURCE "$R") fstype=$(findmnt -no FSTYPE "$R") rw=$(findmnt -no OPTIONS "$R" | grep -qw rw && echo yes || echo no)"
        echo "sfs=$(ls "$ISO"/arch/x86_64/airootfs.* 2>/dev/null | head -1)"
        echo "unsquashfs=$(command -v unsquashfs || echo none)"
        echo "efibootmgr=$(command -v efibootmgr || echo none)"
        echo "efi=$([ -d /sys/firmware/efi ] && echo yes || echo no)"
        echo "python=$(python3 -V 2>&1)"
        echo "net=$NETOK"
        echo "keyring=$KEYOK"
        echo "nm=$(systemctl is-active NetworkManager.service 2>/dev/null)"
        echo "disk=$(lsblk -no PKNAME "$(findmnt -no SOURCE "$R")" 2>/dev/null | head -1)"
    } > "$R/cb/linux-test.ok"
    sync
    say "CB_TEST_OK — da ghi cb/linux-test.ok, tat may"
    save_log
    sleep 2
    systemctl poweroff
    exit 0
fi

result running "dang cai CachyOS"
[ -d /sys/firmware/efi ] || back_to_pe "may khoi dong kieu BIOS - CachyOS cua CloudBlue chi cai tren may UEFI"

# ---------------------------------------------------------------- việc được giao: tìm ổ + 2 phân vùng Linux theo VỊ TRÍ (WinPE ghi trong job.json)
SRC=$(findmnt -no SOURCE "$R")
DISK=/dev/$(lsblk -no PKNAME "$SRC" | head -1)
[ -b "$DISK" ] || back_to_pe "khong xac dinh duoc o cung chua phan vung cuu ho ($SRC)"
py "$JOB" "$DISK" > "$W/job.env" <<'PYEOF' || back_to_pe "cb/job.json hong (khong doc duoc muc linux)"
import json, os, re, secrets, shlex, sys
job = json.load(open(sys.argv[1], encoding="utf-8-sig")); disk = sys.argv[2]
L = job.get("linux") or {}
if not isinstance(L, dict) or not L.get("esp") or not L.get("root"): sys.exit(1)
name = os.path.basename(disk)
def find(off):
    for p in sorted(os.listdir("/sys/class/block")):
        sp = "/sys/class/block/%s" % p
        if not os.path.exists(sp + "/partition") or os.path.realpath(sp).split("/")[-2] != name: continue
        if int(open(sp + "/start").read()) * 512 == int(off): return "/dev/" + p, int(open(sp + "/size").read()) * 512
    return "", 0
esp, esz = find((L.get("esp") or {}).get("offset", -1))
root, rsz = find((L.get("root") or {}).get("offset", -1))
host = re.sub(r"[^A-Za-z0-9-]", "", str(job.get("name") or "cachyos"))[:15].strip("-") or "cachyos"
user = str(L.get("user") or "khach")
if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user) or user in ("root", "liveuser"): user = "khach"
tz = str(L.get("tz") or "Asia/Ho_Chi_Minh")
if not re.fullmatch(r"[A-Za-z0-9_+/-]{1,60}", tz) or ".." in tz: tz = "Asia/Ho_Chi_Minh"
loc = str(L.get("locale") or "en_US"); loc = loc if re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}", loc) else "en_US"
kmap = str(L.get("keymap") or "us"); kmap = kmap if re.fullmatch(r"[a-z]{2,8}", kmap) else "us"
out = {"ESP": esp, "ROOT": root, "ESP_MB": esz >> 20, "ROOT_MB": rsz >> 20, "HOST": host, "CUSER": user, "UPASS": str(L.get("pass") or ""),
       "ADMIN": "1" if L.get("admin") else "0", "AUTO": "1" if L.get("autologin", True) else "0", "TZONE": tz, "LOC": loc, "KMAP": kmap,
       "CI_MODE": "1" if job.get("ci") else "0", "JOBID": str(job.get("id") or "")}
for k, v in out.items(): print("%s=%s" % (k, shlex.quote(str(v))))
PYEOF
# shellcheck disable=SC1091
. "$W/job.env"
[ -b "${ESP:-/x}" ] || back_to_pe "khong thay phan vung EFI Linux dung vi tri WinPE da ghi"
[ -b "${ROOT:-/x}" ] || back_to_pe "khong thay phan vung goc Linux dung vi tri WinPE da ghi"
[ "$ESP" != "$SRC" ] && [ "$ROOT" != "$SRC" ] || back_to_pe "vi tri phan vung Linux trung phan vung cuu ho - dung lai de khong xoa nham"
[ "$ROOT_MB" -ge 20000 ] || back_to_pe "phan vung Linux qua nho (${ROOT_MB} MB)"
say "o $DISK · EFI Linux $ESP (${ESP_MB} MB) · goc $ROOT (${ROOT_MB} MB) · may $HOST · khach $CUSER (admin=$ADMIN, tu dang nhap=$AUTO) · $TZONE · ci=$CI_MODE"
if [ "$CI_MODE" = 1 ]; then ( sleep 5400; say "!! CI: qua 90 phut -> tat may"; sync; systemctl poweroff -ff ) & fi

SFS=$(ls "$ISO"/arch/x86_64/airootfs.sfs 2>/dev/null | head -1)
[ -f "$SFS" ] || back_to_pe "ISO CachyOS khong co arch/x86_64/airootfs.sfs (ban ISO nay chua ho tro)"
command -v unsquashfs >/dev/null || back_to_pe "may song thieu unsquashfs"

# mạng: KHÔNG bắt buộc để cài (hệ thống bung từ ISO) — chỉ để tải công cụ quay màn hình nếu ISO thiếu. Chờ song song trong lúc bung.
( net_wait 420 && touch "$W/net.ok" ) &
NETPID=$!

# ---------------------------------------------------------------- 1. định dạng (CHỈ 2 phân vùng WinPE đã tạo cho Linux)
say "1/9 dinh dang: $ESP -> FAT32, $ROOT -> btrfs"
undo_mounts
swapoff -a 2>/dev/null
for p in "$ESP" "$ROOT"; do umount "$p" 2>/dev/null; done
wipefs -aq "$ESP" "$ROOT" 2>/dev/null
mkfs.fat -F 32 -n CACHYEFI "$ESP" >/dev/null || back_to_pe "dinh dang EFI Linux loi (mkfs.fat)"
mkfs.btrfs -q -f -L CachyOS "$ROOT" >/dev/null || back_to_pe "dinh dang phan vung Linux loi (mkfs.btrfs)"
udevadm settle 2>/dev/null
ROOT_UUID=$(blkid -s UUID -o value "$ROOT")
[ -n "$ROOT_UUID" ] || back_to_pe "khong doc duoc UUID phan vung Linux"

# ---------------------------------------------------------------- 2. subvolume btrfs (giống CachyOS) + gắn
say "2/9 btrfs subvolume @ @home @root @srv @cache @tmp @log"
mkdir -p "$T"
mount "$ROOT" "$T" || back_to_pe "khong gan duoc phan vung Linux"
for sv in @ @home @root @srv @cache @tmp @log; do btrfs -q subvolume create "$T/$sv" >/dev/null || back_to_pe "tao subvolume $sv loi"; done
umount "$T"
OPT="noatime,compress=zstd:1"
mount -o "$OPT,subvol=/@" "$ROOT" "$T" || back_to_pe "gan subvolume @ loi"
for pair in home:@home root:@root srv:@srv var/cache:@cache var/tmp:@tmp var/log:@log; do
    mkdir -p "$T/${pair%%:*}"
    mount -o "$OPT,subvol=/${pair#*:}" "$ROOT" "$T/${pair%%:*}" || back_to_pe "gan subvolume ${pair#*:} loi"
done
mkdir -p "$T/boot"
mount -o umask=0077 "$ESP" "$T/boot" || back_to_pe "gan EFI Linux loi"

# ---------------------------------------------------------------- 3. bung hệ thống từ ISO (airootfs.sfs — đã có sẵn KDE)
say "3/9 bung he thong tu ISO ($(du -m "$SFS" | cut -f1) MB nen) - vai phut"
unsquashfs -f -n -d "$T" "$SFS" > "$W/unsquashfs.log" 2>&1 || { tail -5 "$W/unsquashfs.log"; back_to_pe "bung he thong loi (unsquashfs)"; }
[ -x "$T/usr/bin/bash" ] && [ -f "$T/etc/os-release" ] || back_to_pe "bung xong nhung thieu he thong (usr/bin/bash)"
say "   da bung: $(du -sh "$T" --exclude="$T/boot" 2>/dev/null | cut -f1)"

# ---------------------------------------------------------------- 4. bỏ phần chỉ dành cho máy sống
say "4/9 bo phan cua may song (tai khoan liveuser, sudo khong mat khau, ssh root, tu dang nhap, dich vu livecd)"
rm -f "$T"/etc/sudoers.d/g_wheel "$T"/etc/polkit-1/rules.d/49-nopasswd_global.rules "$T"/etc/ssh/sshd_config.d/10-archiso.conf \
      "$T"/etc/systemd/journald.conf.d/volatile-storage.conf "$T"/etc/systemd/system-generators/systemd-gpt-auto-generator \
      "$T"/etc/modprobe.d/nvidia-loader.conf "$T"/etc/modules-load.d/zfs.conf "$T"/etc/mkinitcpio.conf.d/archiso.conf "$T"/etc/mkinitcpio.d/linux.preset \
      "$T"/etc/pacman.d/hooks/90-cachyos-live-kwin-keyboard.hook "$T"/etc/pacman.d/hooks/uncomment-mirrors.hook \
      "$T"/etc/pacman.d/hooks/zzzz99-remove-custom-hooks-from-airootfs.hook \
      "$T"/etc/systemd/system/livecd-talk.service "$T"/etc/systemd/system/livecd-alsa-unmuter.service "$T"/etc/systemd/system/pacman-init.service \
      "$T"/etc/systemd/system/etc-pacman.d-gnupg.mount "$T"/etc/systemd/system/multi-user.target.wants/livecd-talk.service \
      "$T"/etc/systemd/system/multi-user.target.wants/pacman-init.service "$T"/etc/systemd/system/multi-user.target.wants/sshd.service \
      "$T"/etc/systemd/system/multi-user.target.wants/systemd-networkd.service "$T"/etc/systemd/system/sockets.target.wants/systemd-networkd.socket \
      "$T"/etc/systemd/system/sound.target.wants/livecd-alsa-unmuter.service "$T"/etc/systemd/system/sysinit.target.wants/systemd-time-wait-sync.service \
      "$T"/etc/plasmalogin.conf.d/autologin.conf "$T"/etc/sddm.conf.d/autologin.conf \
      "$T"/root/.automated_script.sh "$T"/root/.zlogin \
      "$T"/usr/local/bin/choose-mirror "$T"/usr/local/bin/prepare-live-desktop.sh "$T"/usr/local/bin/removeun "$T"/usr/local/bin/removeun-online \
      "$T"/usr/local/bin/remove-nvidia "$T"/usr/local/bin/dmcheck "$T"/usr/local/bin/calamares-online.sh "$T"/usr/local/bin/nvidia-module-loader \
      "$T"/usr/local/bin/pkexec-wrapper 2>/dev/null
rm -rf "$T"/etc/systemd/system/getty@tty1.service.d "$T"/etc/systemd/system/systemd-time-wait-sync.service.d "$T"/usr/local/share/livecd-sound \
       "$T"/etc/pacman.d/gnupg "$T"/home/liveuser 2>/dev/null
if [ -f "$T/etc/plasmalogin.conf" ] && grep -q '^\[Autologin\]' "$T/etc/plasmalogin.conf"; then
    printf '[Users]\nMinimumUid=1000\nMaximumUid=60000\n' > "$T/etc/plasmalogin.conf"
fi
if [ "$(systemd-detect-virt 2>/dev/null)" = none ]; then           # máy thật: bỏ dịch vụ của máy ảo (Hyper-V, VirtualBox, VMware)
    rm -f "$T"/etc/systemd/system/multi-user.target.wants/hv_*_daemon.service "$T"/etc/systemd/system/multi-user.target.wants/vboxservice.service \
          "$T"/etc/systemd/system/multi-user.target.wants/vmtoolsd.service "$T"/etc/systemd/system/multi-user.target.wants/vmware-vmblock-fuse.service
fi
ln -sf /usr/lib/systemd/system/graphical.target "$T/etc/systemd/system/default.target"

# ---------------------------------------------------------------- 5. tên máy, ngôn ngữ, bàn phím, múi giờ, fstab, machine-id
say "5/9 ten may $HOST, $LOC.UTF-8, ban phim $KMAP, mui gio $TZONE"
echo "$HOST" > "$T/etc/hostname"
printf '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 %s.localdomain %s\n' "$HOST" "$HOST" > "$T/etc/hosts"
for l in "$LOC.UTF-8 UTF-8" "en_US.UTF-8 UTF-8" "vi_VN.UTF-8 UTF-8"; do
    grep -q "^${l}\$" "$T/etc/locale.gen" 2>/dev/null || { sed -i "s/^#${l}\$/${l}/" "$T/etc/locale.gen" 2>/dev/null; grep -q "^${l}\$" "$T/etc/locale.gen" || echo "$l" >> "$T/etc/locale.gen"; }
done
echo "LANG=$LOC.UTF-8" > "$T/etc/locale.conf"
echo "KEYMAP=$KMAP" > "$T/etc/vconsole.conf"
mkdir -p "$T/etc/X11/xorg.conf.d"
printf 'Section "InputClass"\n    Identifier "system-keyboard"\n    MatchIsKeyboard "on"\n    Option "XkbLayout" "%s"\nEndSection\n' "$KMAP" > "$T/etc/X11/xorg.conf.d/00-keyboard.conf"
[ -f "$T/usr/share/zoneinfo/$TZONE" ] || TZONE=Asia/Ho_Chi_Minh
ln -sf "/usr/share/zoneinfo/$TZONE" "$T/etc/localtime"
rm -f "$T/etc/machine-id"; systemd-machine-id-setup --root="$T" >/dev/null 2>&1 || dbus-uuidgen > "$T/etc/machine-id"
genfstab -U "$T" > "$T/etc/fstab" || back_to_pe "tao fstab loi (genfstab)"
grep -q "subvol=/@[,[:space:]]" "$T/etc/fstab" || grep -q "subvol=/@$" "$T/etc/fstab" || say "!! fstab chua thay subvol=/@ - xem lai"
arch-chroot "$T" locale-gen >/dev/null 2>&1 || say "!! locale-gen loi"
arch-chroot "$T" systemd-sysusers >/dev/null 2>&1

# ---------------------------------------------------------------- 6. tài khoản khách + root, sudo, tự đăng nhập
say "6/9 tai khoan khach '$CUSER'"
arch-chroot "$T" userdel -r liveuser >/dev/null 2>&1; rm -rf "$T/home/liveuser"
G=""
for g in users video audio network lp rfkill sys input; do arch-chroot "$T" getent group "$g" >/dev/null 2>&1 && G="$G,$g"; done
[ "$ADMIN" = 1 ] && G="$G,wheel"
G=${G#,}
if arch-chroot "$T" id "$CUSER" >/dev/null 2>&1; then arch-chroot "$T" usermod -G "$G" -s /bin/bash "$CUSER"
else arch-chroot "$T" useradd -m -G "$G" -s /bin/bash "$CUSER" || back_to_pe "tao tai khoan $CUSER loi"; fi
if [ -n "$UPASS" ]; then printf '%s:%s\n' "$CUSER" "$UPASS" | arch-chroot "$T" chpasswd || back_to_pe "dat mat khau cho $CUSER loi"
else arch-chroot "$T" passwd -d "$CUSER" >/dev/null; fi
ROOTPASS=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
printf 'root:%s\n' "$ROOTPASS" | arch-chroot "$T" chpasswd; unset ROOTPASS
install -d -m 0750 "$T/etc/sudoers.d"
printf '%%wheel ALL=(ALL:ALL) ALL\n' > "$T/etc/sudoers.d/10-installer"; chmod 0440 "$T/etc/sudoers.d/10-installer"
DM=""
for s in plasmalogin sddm lightdm gdm; do [ -f "$T/usr/lib/systemd/system/$s.service" ] && { DM=$s; break; }; done
if [ -n "$DM" ]; then
    ln -sf "/usr/lib/systemd/system/$DM.service" "$T/etc/systemd/system/display-manager.service"
    if [ "$AUTO" = 1 ]; then
        case "$DM" in
            plasmalogin) mkdir -p "$T/etc/plasmalogin.conf.d"; printf '[Autologin]\nUser=%s\nSession=plasma.desktop\nRelogin=true\n' "$CUSER" > "$T/etc/plasmalogin.conf.d/autologin.conf" ;;
            sddm)        mkdir -p "$T/etc/sddm.conf.d"; printf '[Autologin]\nUser=%s\nSession=plasma.desktop\nRelogin=true\n' "$CUSER" > "$T/etc/sddm.conf.d/autologin.conf" ;;
            lightdm)     sed -i "s/^#\?autologin-user=.*/autologin-user=$CUSER/" "$T/etc/lightdm/lightdm.conf" 2>/dev/null ;;
            gdm)         mkdir -p "$T/etc/gdm"; printf '[daemon]\nAutomaticLoginEnable=True\nAutomaticLogin=%s\n' "$CUSER" > "$T/etc/gdm/custom.conf" ;;
        esac
    fi
fi
say "   man hinh dang nhap: ${DM:-khong co} · tu dang nhap: $AUTO"
for u in NetworkManager.service bluetooth.service systemd-timesyncd.service systemd-resolved.service fstrim.timer; do
    arch-chroot "$T" systemctl enable "$u" >/dev/null 2>&1
done
arch-chroot "$T" systemctl disable sshd.service systemd-networkd.service systemd-networkd.socket >/dev/null 2>&1

# nhân: bản trên ISO (live) nằm trong /usr/lib/modules/<bản>/vmlinuz → /boot/vmlinuz-<gói>; preset mkinitcpio chuẩn (bỏ preset của máy sống)
KERNELS=""
for d in "$T"/usr/lib/modules/*/; do
    [ -f "$d/vmlinuz" ] && [ -f "$d/pkgbase" ] || continue
    pb=$(cat "$d/pkgbase")
    install -m 0644 "$d/vmlinuz" "$T/boot/vmlinuz-$pb"
    sed "s|%PKGBASE%|$pb|g" "$T/usr/share/mkinitcpio/hook.preset" > "$T/etc/mkinitcpio.d/$pb.preset"
    KERNELS="$KERNELS $pb"
done
[ -n "$KERNELS" ] || back_to_pe "khong thay nhan Linux nao trong he thong vua bung"
if [ -f "$T/etc/mkinitcpio.conf" ]; then
    sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf keyboard sd-vconsole block filesystems fsck)/' "$T/etc/mkinitcpio.conf"
fi

# ---------------------------------------------------------------- 7. pacman: khoá ký gói, gỡ gói của máy sống + driver NVIDIA, công cụ quay màn hình
say "7/9 khoa ky goi pacman + go goi cua may song"
arch-chroot "$T" pacman-key --init >/dev/null 2>&1 && arch-chroot "$T" pacman-key --populate >/dev/null 2>&1 || say "!! dung khoa pacman loi (cai tiep, cap nhat sau)"
arch-chroot "$T" pacman -Qq > "$W/pkgs.txt" 2>/dev/null
installed() { local p out=""; for p in "$@"; do grep -qx -- "$p" "$W/pkgs.txt" && out="$out $p"; done; echo "$out"; }
DROP="cachyos-calamares-next cachyos-calamares cachyos-calamares-config cachyos-calamares-grub cachyos-calamares-systemd cachyos-calamares-refind
      cachyos-cli-installer-new gparted grsync edk2-shell clonezilla memtest86+ memtest86+-efi mkinitcpio-archiso syslinux elinks
      doxygen expect gpart tcpdump extra-cmake-modules cmake"
DROP="$DROP linux-cachyos-lts-nvidia-open linux-cachyos-nvidia-open linux-cachyos-lts-nvidia linux-cachyos-nvidia nvidia-utils lib32-nvidia-utils
      nvidia-settings opencl-nvidia libva-nvidia-driver egl-wayland nvidia-prime"           # card NVIDIA → driver nouveau có sẵn (gỡ nvidia-utils = bỏ chặn nouveau)
[ "$(systemd-detect-virt 2>/dev/null)" = none ] && DROP="$DROP virtualbox-guest-utils open-vm-tools qemu-guest-agent spice-vdagent"
GONE=$(installed $DROP)
KEEP=$(installed python efibootmgr pciutils ntfs-3g libnotify ffmpeg gstreamer gst-plugins-base gst-plugin-pipewire pipewire wireplumber \
             xdg-desktop-portal xdg-desktop-portal-kde libkscreen)          # agent + điều khiển từ xa cần → "cài chủ động" để pacman -Rns không gỡ theo
[ -n "$KEEP" ] && arch-chroot "$T" pacman -D --asexplicit $KEEP >/dev/null 2>&1
if [ -n "$GONE" ]; then
    arch-chroot "$T" pacman -Rns --noconfirm $GONE >/dev/null 2>&1 || for p in $GONE; do arch-chroot "$T" pacman -Rns --noconfirm "$p" >/dev/null 2>&1; done
fi
arch-chroot "$T" pacman -Qq > "$W/pkgs.txt" 2>/dev/null
sed -i '/^[[:space:]]*blacklist[[:space:]]\+nouveau/d' "$T"/etc/modprobe.d/*.conf 2>/dev/null       # card NVIDIA dùng nouveau (không còn driver NVIDIA)
say "   da go:$(for p in $GONE; do grep -qx -- "$p" "$W/pkgs.txt" || printf ' %s' "$p"; done)"
gst_ok() { arch-chroot "$T" sh -c 'for e in pipewiresrc videoconvert videoscale videorate fdsink; do gst-inspect-1.0 --exists $e || exit 1; done; ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264' >/dev/null 2>&1; }
# gst-plugin-pipewire ĐÚNG phiên bản PipeWire đang có trong máy đích: gói lấy từ kho lưu trữ Arch (pacman kiểm chữ ký), -dd = không kéo PipeWire
# mới. (22.11f CI: "pacman -Sy gst-plugin-pipewire" đòi PipeWire mới hơn → vỡ pipewire-pulse / pipewire-jack đang cài → không cài được.)
# Agent (cbagent.py gst_install) làm y như vậy khi máy đã cài mà vẫn thiếu.
GST_ALA="https://archive.archlinux.org/packages/g/gst-plugin-pipewire"
gst_pw() {
    local ver base c tried="" url
    ver=$(arch-chroot "$T" pacman -Q libpipewire 2>/dev/null | awk '{print $2}')
    case "$ver" in ''|*[!0-9A-Za-z.:+_-]*) say "   khong ro phien ban PipeWire ('$ver')"; return 1;; esac
    base=${ver%-*}
    for c in "$ver" "$base-1" "$base-2" "$base-3"; do
        case " $tried " in *" $c "*) continue;; esac
        tried="$tried $c"
        url="$GST_ALA/gst-plugin-pipewire-$c-x86_64.pkg.tar.zst"
        say "   tai gst-plugin-pipewire $c (dung ban PipeWire $ver dang co)"
        timeout 600 arch-chroot "$T" pacman -U --noconfirm --needed -dd "$url" >> "$W/gst.log" 2>&1 && return 0
        tail -3 "$W/gst.log"
    done
    return 1
}
if gst_ok; then
    say "   cong cu quay man hinh (GStreamer PipeWire + ffmpeg x264): co san"
else
    wait "$NETPID" 2>/dev/null
    if [ -f "$W/net.ok" ]; then
        gst_pw
        gst_ok && say "   cong cu quay man hinh: da cai" || say "!! chua cai duoc cong cu quay man hinh - agent se tu cai lai khi may co mang"
    else
        say "!! thieu cong cu quay man hinh va chua co mang - agent se tu cai khi may co mang"
    fi
fi

# ---------------------------------------------------------------- 8. initramfs + systemd-boot
say "8/9 initramfs + systemd-boot"
arch-chroot "$T" mkinitcpio -P > "$W/mkinitcpio.log" 2>&1 || { tail -15 "$W/mkinitcpio.log"; say "!! mkinitcpio bao loi - kiem file initramfs"; }
for pb in $KERNELS; do [ -s "$T/boot/initramfs-$pb.img" ] || back_to_pe "thieu initramfs-$pb.img (mkinitcpio loi)"; done
arch-chroot "$T" env SYSTEMD_RELAX_ESP_CHECKS=1 bootctl install --esp-path=/boot > "$W/bootctl.log" 2>&1 || { cat "$W/bootctl.log"; back_to_pe "cai systemd-boot loi (bootctl install)"; }
[ -f "$T/boot/EFI/systemd/systemd-bootx64.efi" ] || back_to_pe "bootctl xong nhung thieu EFI/systemd/systemd-bootx64.efi"
CMDL="root=UUID=$ROOT_UUID rootflags=subvol=/@ rw quiet nowatchdog"
[ "$CI_MODE" = 1 ] && CMDL="$CMDL console=ttyS0,115200 console=tty0 systemd.show_status=1"
mkdir -p "$T/boot/loader/entries"
DEF=""
for pb in $KERNELS; do
    name=CachyOS; [ "$pb" = linux-cachyos ] || name="CachyOS (${pb#linux-})"
    printf 'title   %s\nlinux   /vmlinuz-%s\ninitrd  /initramfs-%s.img\noptions %s\n' "$name" "$pb" "$pb" "$CMDL" > "$T/boot/loader/entries/$pb.conf"
    if [ -s "$T/boot/initramfs-$pb-fallback.img" ]; then
        printf 'title   %s (fallback)\nlinux   /vmlinuz-%s\ninitrd  /initramfs-%s-fallback.img\noptions %s\n' "$name" "$pb" "$pb" "$CMDL" > "$T/boot/loader/entries/$pb-fallback.conf"
    fi
    if [ -z "$DEF" ] || [ "$pb" = linux-cachyos ]; then DEF=$pb; fi
done
printf 'default %s.conf\ntimeout 2\nconsole-mode keep\neditor no\n' "$DEF" > "$T/boot/loader/loader.conf"
if ! efibootmgr 2>/dev/null | grep -q "Linux Boot Manager"; then                # bootctl không ghi được NVRAM (trong chroot) → tự tạo bằng efibootmgr (mục mới tự lên đầu BootOrder)
    say "!! bootctl chua tao muc 'Linux Boot Manager' trong NVRAM -> tao bang efibootmgr"
    efibootmgr -q -c -d "$DISK" -p "$(cat "/sys/class/block/$(basename "$ESP")/partition")" -L "Linux Boot Manager" -l '\EFI\systemd\systemd-bootx64.efi' \
        || back_to_pe "khong tao duoc muc khoi dong UEFI cho CachyOS"
fi
say "   nhan:$KERNELS · mac dinh $DEF · $(efibootmgr 2>/dev/null | grep -m1 '^BootOrder' || echo 'BootOrder ?')"

# ---------------------------------------------------------------- 9. phần CloudBlue (agent) + dấu "máy đang chạy CachyOS"
say "9/9 phan mem CloudBlue"
if [ -f "$R/cb/linux/cb-post.sh" ]; then
    CB_REC="$R" CB_JOB="$JOB" CI_MODE="$CI_MODE" bash "$R/cb/linux/cb-post.sh" "$T" || say "!! cb-post.sh bao loi (van tiep tuc)"
fi
cat > "$W/udev.rules" <<'EOF'
# CloudBlue: không cho người dùng gắn phân vùng cứu hộ / EFI của Windows trong trình quản lý file (chỉ root đọc được)
ENV{ID_FS_LABEL}=="CBRECOVERY", ENV{UDISKS_IGNORE}="1"
ENV{ID_PART_ENTRY_TYPE}=="c12a7328-f81f-11d2-ba4b-00a0c93ec93b", ENV{UDISKS_IGNORE}="1"
ENV{ID_PART_ENTRY_TYPE}=="e3c9e316-0b5c-4db8-817d-f92df00215ae", ENV{UDISKS_IGNORE}="1"
EOF
install -D -m 0644 "$W/udev.rules" "$T/etc/udev/rules.d/90-cloudblue-hide.rules"
py "$R/cb/linux/installed.json" "$ESP" "$ROOT" "$ROOT_UUID" "$CB_VER" "$JOBID" "$DEF" <<'PYEOF'
import json, os, sys, time
p, esp, root, uuid, ver, jid, kern = sys.argv[1:8]
d = {"os": "cachyos", "boot": "Linux Boot Manager", "esp": esp, "root": root, "root_uuid": uuid, "kernel": kern, "by": "cb-install " + ver, "job": jid, "ts": int(time.time())}
with open(p + ".tmp", "w", encoding="utf-8") as f: json.dump(d, f)
os.replace(p + ".tmp", p)
PYEOF
undo_mounts
SECS=$(( $(date +%s) - T0 ))
say "XONG: da cai CachyOS sau $((SECS / 60)) phut ($HOST)"
result done "da cai CachyOS sau $((SECS / 60)) phut ($HOST, khach $CUSER)"
save_log
rm -f "$R/cb/linux/job.cfg" 2>/dev/null; sync
sleep 3
systemctl reboot
