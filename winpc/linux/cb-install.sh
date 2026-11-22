#!/usr/bin/env bash
# =====================================================================================================
#  cb-install.sh — CloudBlue PC: CÀI CachyOS KHÔNG NGƯỜI. Chạy trong máy sống CachyOS (mở thẳng từ file ISO trên phân vùng cứu hộ
#  bằng GRUB, xem grub.cfg), systemd gọi bằng tham số nhân  systemd.run=/run/archiso/img_dev/cb/linux/cb-install.sh
#    · /run/archiso/img_dev        = phân vùng cứu hộ CBRECOVERY (NTFS) — archiso gắn sẵn (chỉ đọc) → gắn lại có ghi
#    · cb/job.json                 = việc WinPE giao: os "cachyos", vị trí 2 phân vùng Linux (EFI + gốc), tên máy, tài khoản khách
#    · kết quả → cb/job-result.json + cb/logs/linux-install-<giờ>.log; xong thì khởi động lại vào CachyOS
#  Thử trên GitHub CI (QEMU): job.json có "test": true → chỉ ghi cb/linux-test.ok (chứng minh đường GRUB → ISO → script) rồi tắt máy.
# =====================================================================================================
set -u
CB_VER="22.11c"
R=/run/archiso/img_dev
W=/tmp/cb
mkdir -p "$W"
LOG="$W/install.log"
exec > >(tee -a "$LOG" /dev/console) 2>&1
say() { printf '[cloudblue %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

say "cb-install $CB_VER bat dau ($(uname -r))"
mount -o remount,rw "$R" 2>/dev/null || mount -o remount,rw,force "$R" 2>/dev/null || say "!! khong gan lai duoc phan vung cuu ho de ghi (van tiep tuc)"
# systemd.run= cho máy sống chỉ chạy tới basic.target + script này → bật thêm multi-user.target (KHÔNG chờ, KHÔNG isolate — script vẫn chạy tiếp):
# NetworkManager (bộ cài tải gói qua mạng), pacman-init (khoá ký gói), logind… như máy sống khởi động bình thường (trừ màn hình đồ hoạ).
systemctl start --no-block multi-user.target 2>/dev/null || say "!! chua bat duoc multi-user.target"

net_wait() {   # net_wait <số giây> → 0 khi tới được kho gói CachyOS / Arch
    local end=$(( $(date +%s) + $1 ))
    while [ "$(date +%s)" -lt "$end" ]; do
        if curl -fsS -m 8 -o /dev/null https://mirror.cachyos.org/ 2>/dev/null || curl -fsS -m 8 -o /dev/null https://geo.mirror.pkgbuild.com/ 2>/dev/null; then return 0; fi
        sleep 5
    done
    return 1
}
keyring_wait() {   # khoá ký gói của pacman đã dựng xong (pacman-init.service của máy sống) → 0 · chờ tối đa 5 phút
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

result() {   # result <state> <thông điệp>
    local st="$1" msg="$2"
    py "$JOB" "$RES" "$st" "$msg" <<'PYEOF'
import json, sys, time
job_p, res_p, st, msg = sys.argv[1:5]
try: job = json.load(open(job_p, encoding="utf-8-sig"))
except Exception: job = {}
res = {"id": job.get("id"), "os": job.get("os"), "state": st, "msg": msg[:2000], "ts": int(time.time()), "by": "cb-install"}
with open(res_p + ".tmp", "w", encoding="utf-8") as f: json.dump(res, f, ensure_ascii=False)
import os; os.replace(res_p + ".tmp", res_p)
if st in ("done", "failed"):
    job["state"] = "linux-" + st; job["linux_msg"] = msg[:500]
    with open(job_p + ".tmp", "w", encoding="utf-8") as f: json.dump(job, f, ensure_ascii=False)
    os.replace(job_p + ".tmp", job_p)
PYEOF
}

save_log() {
    mkdir -p "$R/cb/logs" 2>/dev/null
    cp -f "$LOG" "$R/cb/logs/linux-install-$(date +%Y%m%d-%H%M%S).log" 2>/dev/null
    [ -f /var/log/cachyos/cli-installer.log ] && cp -f /var/log/cachyos/cli-installer.log "$R/cb/logs/" 2>/dev/null
    sync
}

back_to_pe() {   # lỗi: về WinPE cứu hộ (Windows Boot Manager mặc định = WinPE) để thử lại / cài Windows mặc định
    say "$1"
    result failed "$1"
    save_log
    local wbm
    wbm=$(efibootmgr 2>/dev/null | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\)\*\{0,1\} Windows Boot Manager.*/\1/p' | head -1)
    [ -n "$wbm" ] && efibootmgr -q -n "$wbm" && say "lan khoi dong sau: Windows Boot Manager ($wbm) -> WinPE cuu ho"
    sleep 15
    systemctl reboot
    exit 1
}

[ -f "$JOB" ] || back_to_pe "khong thay cb/job.json tren phan vung cuu ho"

# ---------------------------------------------------------------- chế độ THỬ (GitHub CI): chỉ chứng minh đường khởi động
if py "$JOB" <<'PYEOF'
import json, sys
sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8-sig")).get("test") else 1)
PYEOF
then
    NETOK=no; net_wait 180 && NETOK=yes
    KEYOK=no; keyring_wait && KEYOK=yes
    {
        echo "CB_TEST_OK $CB_VER"
        echo "kernel=$(uname -r)"
        echo "img_dev=$(findmnt -no SOURCE "$R") fstype=$(findmnt -no FSTYPE "$R") rw=$(findmnt -no OPTIONS "$R" | grep -qw rw && echo yes || echo no)"
        echo "installer=$(command -v cachyos-installer || echo none)"
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
    sleep 2
    systemctl poweroff
    exit 0
fi

result running "dang cai CachyOS"
[ -d /sys/firmware/efi ] || back_to_pe "may khoi dong kieu BIOS - CachyOS cua CloudBlue chi cai tren may UEFI"

# ---------------------------------------------------------------- tìm ổ + 2 phân vùng Linux theo VỊ TRÍ (WinPE ghi trong job.json)
SRC=$(findmnt -no SOURCE "$R")
DISK=/dev/$(lsblk -no PKNAME "$SRC" | head -1)
[ -b "$DISK" ] || back_to_pe "khong xac dinh duoc o cung chua phan vung cuu ho ($SRC)"
read -r ESP ROOT ESP_MB ROOT_MB HOST USER UPASS AUTO DESK TZ LOC KMAP < <(py "$JOB" "$DISK" <<'PYEOF'
import json, os, sys, secrets
job = json.load(open(sys.argv[1], encoding="utf-8-sig")); disk = sys.argv[2]
L = job.get("linux") or {}
name = os.path.basename(disk)
def find(off):
    for p in sorted(os.listdir("/sys/class/block")):
        sp = "/sys/class/block/%s" % p
        if not os.path.exists(sp + "/partition") or not os.path.realpath(sp).split("/")[-2] == name: continue
        if int(open(sp + "/start").read()) * 512 == int(off): return "/dev/" + p, int(open(sp + "/size").read()) * 512
    return "-", 0
esp, esz = find((L.get("esp") or {}).get("offset", -1))
root, rsz = find((L.get("root") or {}).get("offset", -1))
host = "".join(c for c in str(job.get("name") or "cachyos") if c.isalnum() or c == "-")[:15].strip("-") or "cachyos"
user = str(L.get("user") or "pc")
upass = str(L.get("pass") or secrets.token_urlsafe(9))
print(esp, root, esz >> 20, rsz >> 20, host, user, upass, "1" if L.get("autologin", True) else "0", L.get("desktop") or "kde",
      L.get("tz") or "Asia/Ho_Chi_Minh", L.get("locale") or "en_US", L.get("keymap") or "us")
PYEOF
)
[ -b "${ESP:-/x}" ] || back_to_pe "khong thay phan vung EFI Linux dung vi tri WinPE da ghi"
[ -b "${ROOT:-/x}" ] || back_to_pe "khong thay phan vung goc Linux dung vi tri WinPE da ghi"
[ "$ROOT_MB" -ge 20000 ] || back_to_pe "phan vung Linux qua nho (${ROOT_MB} MB)"
say "o $DISK · EFI Linux $ESP (${ESP_MB} MB) · goc $ROOT (${ROOT_MB} MB) · may $HOST · khach $USER"

# ---------------------------------------------------------------- mạng (bộ cài CachyOS tải gói qua mạng)
net_wait 300 || back_to_pe "chua co mang sau 5 phut (bo cai CachyOS can Internet)"
say "co mang"
keyring_wait || say "!! khoa ky goi pacman chua dung xong sau 5 phut (van thu cai)"

# ---------------------------------------------------------------- settings.json cho cachyos-installer (chế độ không người)
ROOTPASS=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
cp -f "$R/cb/linux/cb-post.sh" "$W/cb-post.sh" 2>/dev/null && chmod 755 "$W/cb-post.sh"
py "$W/settings.json" "$DISK" "$ESP" "$ROOT" "$ESP_MB" "$ROOT_MB" "$HOST" "$USER" "$UPASS" "$ROOTPASS" "$AUTO" "$DESK" "$TZ" "$LOC" "$KMAP" "$W/cb-post.sh" <<'PYEOF'
import json, os, sys
(out, disk, esp, root, esp_mb, root_mb, host, user, upass, rootpass, auto, desk, tz, loc, kmap, post) = sys.argv[1:17]
cfg = {"install_type": "simple", "headless_mode": True, "device": disk, "fs_name": "btrfs", "subvolumes": "default",
       "partitions": [{"name": esp, "mountpoint": "/boot", "size": "%sM" % esp_mb, "fs_name": "vfat", "type": "boot"},
                      {"name": root, "mountpoint": "/", "size": "%sM" % root_mb, "type": "root"}],
       "hostname": host, "locale": loc, "xkbmap": kmap, "timezone": tz,
       "user_name": user, "user_pass": upass, "user_shell": "/bin/bash", "root_pass": rootpass,
       "kernel": "linux-cachyos", "desktop": desk, "bootloader": "systemd-boot", "autologin": auto == "1",
       "chwd": True, "os_prober": False, "carry_network": True}
if os.path.exists(post): cfg["post_install"] = post
with open(out, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)
PYEOF
say "settings.json: $(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); c["user_pass"]=c["root_pass"]="***"; print(json.dumps(c))' "$W/settings.json")"

# ---------------------------------------------------------------- cài (tối đa 120 phút)
command -v cachyos-installer >/dev/null || back_to_pe "ISO CachyOS nay khong co cachyos-installer (can ban ISO desktop moi)"
export CB_JOB="$JOB" CB_REC="$R"
cd "$W" || exit 1
timeout 7200 cachyos-installer --config "$W/settings.json"
rc=$?
[ "$rc" = 0 ] || back_to_pe "cachyos-installer loi (ma $rc) - xem cb/logs/linux-install-*.log"

say "cai xong CachyOS"
result done "da cai CachyOS ($HOST)"
save_log
sleep 3
systemctl reboot
