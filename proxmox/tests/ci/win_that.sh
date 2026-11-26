#!/usr/bin/env bash
# CI (Ubuntu, GitHub Actions, co KVM): THU THAT ISO may mau Windows (proxmox/tests/ci/win_that.py). Khong dung may that nao, khong goi web that.
#   win_that.sh chuanbi   -> chon cho lam viec du rong (ghi W vao $GITHUB_ENV), cai QEMU
#   win_that.sh chay      -> gom ket qua job ghep (Windows) + chay win_that.py; ket qua trong kq/ va nhanh win-shots-<tag>
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TAG=${TAG:-win2016}
KQ=${KQ:-$PWD/kq}
mkdir -p "$KQ"

chuanbi() {
  df -h / /mnt 2>&1 | sed 's/^/   /'
  local need=36 w=""
  local a_mnt a_root
  a_mnt=$(df --output=avail -BG /mnt 2>/dev/null | tail -1 | tr -dc 0-9); a_root=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
  if [ "${a_mnt:-0}" -ge "$need" ] && [ "$(stat -c %d /mnt)" != "$(stat -c %d /)" ]; then w=/mnt/w
  else
    if [ "${a_root:-0}" -lt "$need" ]; then
      echo "   o / con ${a_root} GB - don bot bo cong cu cai san cua may CI"
      sudo rm -rf /usr/local/lib/android /opt/hostedtoolcache/CodeQL /usr/share/dotnet /opt/ghc /usr/local/.ghcup /usr/share/swift 2>/dev/null
      df -h / | sed 's/^/   /'
    fi
    w=/home/runner/w
  fi
  sudo mkdir -p "$w" && sudo chown "$(id -u)" "$w"
  echo "   cho lam viec: $w"
  [ -n "${GITHUB_ENV:-}" ] && echo "W=$w" >> "$GITHUB_ENV"
  sudo apt-get update -q >/dev/null 2>&1
  sudo apt-get install -y -q qemu-system-x86 qemu-utils ntfs-3g parted >/dev/null 2>&1
  [ -w /dev/kvm ] || sudo chmod 666 /dev/kvm
  ls -l /dev/kvm; qemu-system-x86_64 --version | head -1
}

chay() {
  local res="$KQ/win-$TAG-ketqua.txt"
  : > "$res"
  # ket qua job ghep tren Windows (file do win_that_build.ps1 ghi, da loc)
  for f in "$KQ"/win-"$TAG"-ghep.txt; do
    [ -s "$f" ] && { sed 's/^\xEF\xBB\xBF//' "$f" | tr -d '\r' | grep -E '^(OK|XX|\.\.|==)' >> "$res"; }
  done
  [ -s "$res" ] || echo "XX  job ghep ISO tren Windows khong de lai ket qua" >> "$res"
  bash "$HERE/win_that_push.sh" "$TAG" "$KQ" "bat dau cai" || true
  W=${W:-/mnt/w} KQ="$KQ" TAG="$TAG" python3 "$HERE/win_that.py"
  local rc=$?
  ls -la "$KQ"
  return $rc
}

case "${1:-}" in
  chuanbi) chuanbi ;;
  chay) chay ;;
  *) echo "dung: win_that.sh chuanbi|chay"; exit 2 ;;
esac
