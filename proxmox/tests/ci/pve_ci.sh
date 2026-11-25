#!/usr/bin/env bash
# CI (Ubuntu, GitHub Actions) cho ISO PROXMOX TU CAI cua CloudBlue. Khong dung may that nao, khong goi web that.
#   pve_ci.sh tai       -> tai ISO Proxmox VE chinh thuc vao $W/pve.iso
#   pve_ci.sh explore   -> soi cau truc ISO goc + ISO do cong cu chinh thuc cua Proxmox tao (de doi chieu)
# Ket qua ghi vao thu muc kq/ (workflow day len nhanh pve-shots).
set -uo pipefail
W=${W:-/mnt/w}
KQ=${KQ:-$PWD/kq}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$KQ"

tai() {
  sudo mkdir -p "$W" && sudo chown "$(id -u)" "$W"
  if [ -s "$W/pve.iso" ] && [ -s "$W/pve.ver" ]; then echo "da co ISO $(cat "$W/pve.ver")"; return 0; fi
  for v in 9.3-1 9.2-1; do
    if curl -fL --retry 3 --connect-timeout 20 -o "$W/pve.iso.part" "https://enterprise.proxmox.com/iso/proxmox-ve_$v.iso"; then
      mv "$W/pve.iso.part" "$W/pve.iso"; echo "$v" > "$W/pve.ver"; echo "da tai $v"; return 0
    fi
  done
  echo "KHONG tai duoc ISO Proxmox"; return 1
}

soi() {   # soi <iso> : in cau truc
  local I=$1
  echo "== file"; ls -l "$I"; sha256sum "$I"
  echo "== isoinfo -d"; isoinfo -d -i "$I" 2>&1
  echo "== fdisk"; fdisk -l "$I" 2>&1
  echo "== xorriso plain"; xorriso -indev "$I" -report_el_torito plain -report_system_area plain 2>&1 | grep -v '^$'
  echo "== xorriso cmd"; xorriso -indev "$I" -report_el_torito cmd -report_system_area cmd 2>&1 | grep -v '^$'
  echo "== ls /"; xorriso -indev "$I" -lsl / 2>&1 | grep -v '^xorriso\|^$\|^Drive\|^Media\|^Boot\|^Volume'
  echo "== hex"; python3 "$HERE/pve_hex.py" "$I" 2>&1
}

explore() {
  sudo apt-get update -q >/dev/null 2>&1
  sudo apt-get install -y -q xorriso genisoimage mtools >/dev/null 2>&1
  local I=$W/pve.iso
  {
    echo "ver: $(cat "$W/pve.ver")"
    echo "== may CI"; ls -l /dev/kvm 2>&1; nproc; free -m | head -2; df -h / /mnt 2>&1
    soi "$I"
    echo "== ls /boot /boot/grub"; xorriso -indev "$I" -lsl /boot -lsl /boot/grub 2>&1 | grep -v '^xorriso\|^$\|^Drive\|^Media\|^Boot\|^Volume' | head -60
    echo "== thu muc"; xorriso -indev "$I" -find / -type d 2>/dev/null | head -80
  } > "$KQ/pve-goc.txt" 2>&1
  xorriso -osirrox on -indev "$I" -extract /boot/grub/grub.cfg "$KQ/pve-grub.cfg.txt" -extract /.cd-info "$KQ/pve-cd-info.txt" \
          -extract /.pve-cd-id.txt "$KQ/pve-cd-id.txt" -extract /efi.img /tmp/efi.img >/dev/null 2>&1
  chmod u+w "$KQ"/* /tmp/efi.img 2>/dev/null
  {
    echo "== efi.img"; mdir -i /tmp/efi.img -/ :: 2>&1 | head -60
    for f in EFI/BOOT/grub.cfg EFI/boot/grub.cfg boot/grub/grub.cfg; do echo "-- $f"; mtype -i /tmp/efi.img "::/$f" 2>&1 | head -40; done
    mcopy -i /tmp/efi.img ::/EFI/BOOT/grubx64.efi /tmp/g.efi 2>/dev/null || mcopy -i /tmp/efi.img ::/EFI/BOOT/BOOTX64.EFI /tmp/g.efi 2>/dev/null
    echo "-- chuoi trong grub efi"; strings /tmp/g.efi 2>/dev/null | grep -n "search \|prefix\|pve-cd\|fs-uuid\|configfile" | head -20
    echo "-- module grub"; xorriso -indev "$I" -ls /boot/grub/x86_64-efi 2>/dev/null | tr -d "'" | grep -E "^(lvm|ext2|ntfs|zfs|search|test|part_gpt|part_msdos|chain|regexp|probe|fat|exfat)\.mod" | tr '\n' ' '
    echo; xorriso -indev "$I" -ls /boot/grub/i386-pc 2>/dev/null | tr -d "'" | grep -E "^(lvm|ext2|ntfs|zfs|search|test|part_gpt|part_msdos|chain|regexp|probe|fat|exfat)\.mod" | tr '\n' ' '
  } > "$KQ/pve-efi.txt" 2>&1

  # ISO do cong cu chinh thuc cua Proxmox tao (proxmox-auto-install-assistant, trong Debian 13) -> doi chieu
  cat > "$W/answer.toml" <<'EOF'
[global]
keyboard = "en-us"
country = "vn"
fqdn = "cbvps.lan"
mailto = "root@cbvps.lan"
timezone = "Asia/Ho_Chi_Minh"
root-password-hashed = "$6$cbthu2611$f/E0E88wcetQEiEUYlTyWFTUy6Z7TbfRVRumzXvH6Y7PrcDqL/zDnnrZbu/Y3U6C2jgRc7NYkg2APNr17bDyX1"
reboot-mode = "power-off"

[network]
source = "from-dhcp"

[disk-setup]
filesystem = "ext4"
filter.DEVNAME = "/dev/*"

[first-boot]
source = "from-iso"
ordering = "fully-up"
EOF
  printf '#!/bin/bash\necho cloudblue-first-boot\n' > "$W/fb.sh"
  docker run --rm -v "$W":/w debian:trixie bash -c '
    set -e
    apt-get update -q >/dev/null; apt-get install -y -q wget ca-certificates xorriso >/dev/null
    wget -q https://enterprise.proxmox.com/debian/proxmox-archive-keyring-trixie.gpg -O /usr/share/keyrings/proxmox-archive-keyring.gpg
    printf "Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: trixie\nComponents: pve-no-subscription\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n" > /etc/apt/sources.list.d/pve.sources
    apt-get update -q >/dev/null; apt-get install -y -q proxmox-auto-install-assistant >/dev/null
    dpkg -l proxmox-auto-install-assistant xorriso | tail -2
    echo "-- validate-answer"; proxmox-auto-install-assistant validate-answer /w/answer.toml
    echo "-- prepare-iso"; proxmox-auto-install-assistant prepare-iso /w/pve.iso --fetch-from iso --answer-file /w/answer.toml --on-first-boot /w/fb.sh --output /w/ref.iso
    chmod a+rw /w/ref.iso
  ' > "$KQ/pve-chinh-thuc.txt" 2>&1
  if [ -s "$W/ref.iso" ]; then
    {
      soi "$W/ref.iso"
      echo "== auto-installer-mode.toml"; xorriso -osirrox on -indev "$W/ref.iso" -extract /auto-installer-mode.toml /tmp/aim.toml >/dev/null 2>&1; cat /tmp/aim.toml; echo "<het>"; od -c /tmp/aim.toml | head -8
      echo "== sector (2048) bi doi trong phan cu"; cmp -l "$I" "$W/ref.iso" 2>/dev/null | awk '{ s = int(($1 - 1) / 2048); if (s != p) { print s; p = s } }' | head -60
    } > "$KQ/pve-ref.txt" 2>&1
  fi
  ls -la "$KQ"
}

case "${1:-}" in
  tai) tai ;;
  explore) explore ;;
  ghep|win|bios|uefi)
    if [ ! -e /tmp/pve-apt-xong ]; then
      sudo apt-get update -q >/dev/null 2>&1
      sudo apt-get install -y -q xorriso genisoimage mtools qemu-system-x86 qemu-utils ovmf ntfs-3g parted openssh-client >/dev/null 2>&1
      touch /tmp/pve-apt-xong
    fi
    python3 "$HERE/pve_ci.py" "$1" ;;
  *) echo "dung: pve_ci.sh tai|explore|ghep|win|bios|uefi"; exit 2 ;;
esac
