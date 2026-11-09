#!/bin/sh
# Build cpsu (x86_64).
#   cpsu-su-x86_64 : the "su" CLIENT that runs inside Android app processes (Termux…).
#                    Built WITHOUT libc (cpsu-su.c, raw syscalls) so it makes only syscalls bionic uses —
#                    app seccomp cannot kill it with SIGSYS (glibc static startup calls rseq/set_robust_list).
#   cpsu-x86_64    : daemon + install/uninstall/stop/status (cpsu.c). Runs as root from adb, OUTSIDE the
#                    app sandbox, so glibc -static is acceptable; musl is used when available.
#                    Its built-in "su" mode is for local tests only — on a device ramdisk/su must be cpsu-su.
set -eu
cd "$(dirname "$0")"

echo "[build] cpsu-su-x86_64 (libc-free client)"
gcc -O2 -static -nostdlib -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns \
    -fno-stack-protector -no-pie -fno-asynchronous-unwind-tables -Wall -Wextra \
    -o cpsu-su-x86_64 cpsu-su.c
strip cpsu-su-x86_64 2>/dev/null || true

CFLAGS="-O2 -static -Wall -Wextra -Wno-unused-parameter -o cpsu-x86_64 cpsu.c"
if command -v musl-gcc >/dev/null 2>&1; then
	echo "[build] cpsu-x86_64 with musl-gcc"; musl-gcc $CFLAGS
elif python3 -c 'import ziglang' >/dev/null 2>&1; then
	echo "[build] cpsu-x86_64 with zig (musl)"; python3 -m ziglang cc -target x86_64-linux-musl -O2 -Wall -o cpsu-x86_64 cpsu.c
else
	echo "[build] cpsu-x86_64 with glibc -static (daemon runs outside the app sandbox: OK)"; cc $CFLAGS
fi
strip cpsu-x86_64 2>/dev/null || true
file cpsu-su-x86_64 cpsu-x86_64 || true
md5sum cpsu-su-x86_64 cpsu-x86_64
