# cpsu — per-app superuser for MuMu / Android x86_64 emulator VMs

`cpsu` gives root to **selected** Android apps on a MuMu Player VM (x86_64
Android 12/15) through a per-app allowlist. It is a minimal "su + root daemon"
in the spirit of Magisk's superuser, but configured entirely **from outside**:
a server pushes the binary and the allowlist over `adb shell` (root), flips a
per-phone Root switch, and lists which apps may obtain root.

The built-in MuMu `su` only works from `adb`, not from inside apps (so Termux
reports *"No su program found"*). `cpsu` fixes that for the apps you choose.

> **Scope / non-goals.** The allowlist decides **who may OBTAIN root**. It
> hides nothing: any app can still see that an `su` binary exists. There is no
> deny list, no per-app unmounting of `su`, no `getenforce`/SELinux spoofing —
> all out of scope by design. `cpsu` never calls `setenforce`.

One C file (`cpsu.c`), multi-call by `argv[0]`:

| invocation | role |
|---|---|
| `su …` (basename is `su`) | **client** — asks the daemon to run a shell as root |
| `cpsu daemon …` | root **daemon** — holds root, checks the allowlist, runs children |
| `cpsu stop` / `status` / `install` / `uninstall` / `version` | lifecycle |

---

## Build

```sh
sh build.sh          # -> cpsu-su-x86_64 (client) + cpsu-x86_64 (daemon/lifecycle)
```

Two binaries are shipped to a device:

| file | source | runs where | libc |
|---|---|---|---|
| `cpsu-su-x86_64` | `cpsu-su.c` | **inside Android app processes** (Termux…) as `su` | **none** — raw syscalls, `-nostdlib -ffreestanding` (~15 KB) |
| `cpsu-x86_64` | `cpsu.c` | as root from `adb shell` (daemon, install, stop, status) — outside the app sandbox | musl if available, else glibc `-static` (fine here) |

Why the client has no libc: it runs under the **app seccomp filter**. glibc's static startup
issues `rseq` / `set_robust_list` (and glibc may use `clone3`, `faccessat2`…), which an app
filter can answer with **SIGSYS**, killing `su` before `main()`. No musl toolchain was
reachable in this build container, so the client was written freestanding instead: it makes
**only** the syscalls listed below, all of which bionic itself uses.

`cpsu-x86_64` still has a built-in `su` mode (basename `su`) — **for local tests only**.
`cpsu install` copies `DIR/su` (the libc-free client) to `<ramdisk>/su` by default; it only
falls back to `/proc/self/exe` when `DIR/su` is missing.

---

## Commands

### Client `su` (Magisk / util-linux subset)

```
su [options] [USER] [ARGS...]
```

| option | meaning |
|---|---|
| `-c, --command CMD` | run `CMD` with the shell (`sh -c CMD`) |
| `-s, --shell SHELL` | shell to use (default: daemon's `--shell`) |
| `-l, --login, -` | login shell: `argv[0]`=`-sh`, cwd=`/` |
| `-p, -m, --preserve-environment` | keep env; don't force `USER`/`LOGNAME`/`SHELL` |
| `-mm, -M, --mount-master` | accepted, **no-op** |
| `-v, --version` | print `2.0:CPSU` |
| `-V` | print `200` |
| `-Z, --context X`, `-t, --target PID` | accepted, **ignored** |
| `-h, --help` | usage |
| `--` | end of options |

`USER` is the first positional: `root`/`0` (default), `shell`/`2000`,
`system`/`1000`, or a numeric uid. Further positionals are passed to the shell
**after** the command (util-linux style: `su -c CMD root A B` → `sh -c CMD A B`,
so `$0=A`, `$1=B`).

Behaviour:

* **`getuid()==0` shortcut** — if already root, the shell is exec'd **locally**
  without contacting the daemon, so `adb root` keeps working when the daemon is
  down.
* **Terminal** — if any of stdin/stdout/stderr is a tty, the session runs over a
  pty: stdin goes raw (always restored, even on signals), `SIGWINCH` is
  forwarded, **Ctrl+C reaches the root child as `0x03`** through the pty and does
  **not** kill the client. Without a tty (pipes), fds are passed straight through.
* **Environment sent** — the client's full env, plus (unless `-p`)
  `USER`/`LOGNAME`=target name and `SHELL`=shell; `HOME` unchanged; `PATH` gets
  `/system/bin` appended if missing.

The default socket is the abstract name `cpsu`; override with `CPSU_SOCK` (used
by the tests).

### `cpsu daemon [--fg] [--sock NAME] [--dir DIR] [--packages FILE] [--shell PATH] [--notify] [--notify-cmd PATH]`

Defaults: socket `cpsu` (abstract, `SOCK_STREAM`), `DIR=/data/adb/cpsu` (created
`0700`), `packages=/data/system/packages.list`, `shell=/system/bin/sh`.
Daemonises unless `--fg`; writes `DIR/daemon.pid`; `SIGTERM` → clean exit;
`SIGPIPE` ignored; everything `O_CLOEXEC`. If the socket name is already bound it
prints a message and exits **2**. Forks one handler per connection (cap 64
concurrent, children reaped); the accept loop never blocks on a client. Each
request is read with a 10 s timeout and hard limits (≤256 KB body, ≤4096 argv,
≤4096 env).

### `cpsu stop`

Sends a control request honoured only from uid 0 / 2000; falls back to killing
the pid in `DIR/daemon.pid`. Prints `STOP_OK` / `STOP_NONE`.

### `cpsu status`

`RUNNING pid=<n> version=2.0:CPSU selinux=<Enforcing|Permissive|none>`
(exit 0) or `STOPPED` (exit 3). SELinux is read from `/sys/fs/selinux/enforce`.

### `cpsu install [--dir D] [--ramdisk /debug_ramdisk] [--bind P1,P2] [--src FILE] [--sock N] [--packages F] [--shell P] [--notify]`

If `--ramdisk` exists and is **not** a mountpoint, mounts a `tmpfs` there
(`mode=0755`); copies the binary (`--src`, default `/proc/self/exe`) to
`<ramdisk>/su` (`0755`) — Termux's `su` wrapper looks for `/debug_ramdisk/su`;
bind-mounts `<ramdisk>/su` over each existing `--bind` file (e.g.
`/system/xbin/su,/system/bin/su`); records what it mounted in `D/mounts`; starts
the daemon if not running. Prints `INSTALL_OK …` or `INSTALL_FAIL <reason>`
(non-zero). Every path is overridable for testing. Never touches SELinux.

### `cpsu uninstall [--dir D]`

Stops the daemon, lazily unmounts (`MNT_DETACH`) every bind and tmpfs recorded
in `D/mounts`, prints `UNINSTALL_OK`.

---

## Device files

| path | contents |
|---|---|
| `DIR/allow` | allowlist: one package per line; `#` comment; `*` = every uid mapping to ≥1 package. **Re-read on every request.** |
| `DIR/log` | one line per decision; truncated to the last ~32 KB past 64 KB |
| `DIR/daemon.pid` | daemon pid |
| `DIR/mounts` | install bookkeeping (`tmpfs <path>`, `bind <path>`) |
| `DIR/notify/<pkg>` | per-package notify rate-limit stamps |
| `packages.list` | Android's `/data/system/packages.list` — col 2 = appId |

**Permission rule** (per request, nothing cached): peer uid from `SO_PEERCRED`.
uid **0** and **2000** (adb shell) are always allowed. Otherwise
`appId = uid % 100000`; `appId < 10000` or `appId ≥ 90000` (isolated / app-zygote)
→ **deny**. Otherwise collect every package in `packages.list` whose appId matches
(shared uids → several) and allow if `DIR/allow` contains any of them (or is `*`
and the uid maps to ≥1 package). An **unreadable** `packages.list` → deny.

**Log line** (local ISO time; never logs commands or env):
```
2026-11-09T16:25:00+0000 uid=10123 pkgs=com.termux ALLOW
2026-11-09T16:25:00+0000 uid=10124 pkgs=com.foo.bar DENY
```

**`--notify`** (on DENY only): double-forks
`/system/bin/cmd notification post -t 'Quyền root' cpsu '<pkg> xin quyền root — bật trong CloudBlue: Công cụ → 🔓 Root'`,
at most once per package per 60 s (command path overridable via `--notify-cmd`).

---

## Wire protocol

Abstract `AF_UNIX` / `SOCK_STREAM` socket (default name `cpsu`). All integers are
host-order fixed-width (client and daemon are the same arch; local IPC only).

**Request** (client → daemon), one `sendmsg` carrying the header + the 3 std fds
via `SCM_RIGHTS`, then the body:

```
struct req_hdr {               magic   = "CPS1"
  char magic[4]; u32 version;  flags bit0..2 = stdin/stdout/stderr is a tty
  u32 target_uid; u32 flags;         bit3 = login, bit4 = preserve-env
  u16 ws_row,ws_col,ws_xpix,ws_ypix; n_args = argv count, n_env = env count
  u32 n_args, n_env, body_len; }      body_len = bytes of the NUL-joined body
body = shell '\0' cwd '\0' argv[0..n_args) '\0'… env[0..n_env) '\0'…
```
Empty `shell` → the daemon's `--shell` default.

**Response** (daemon → client): `struct resp_hdr { u32 code; u32 flags; }` with
`code` = `ALLOW(1)` / `DENY(2)` / `ERR(3)`; if a pty was allocated, `flags` bit0
is set and the pty **master** fd rides along via `SCM_RIGHTS`. After the child
exits the daemon writes the exit status as `int32` (`128+signal` if signalled).

**Control** (`cpsu stop`): a `req_hdr` with `magic="CPSC"`, `target_uid`=cmd, no
fds; honoured only from uid 0/2000.

On **ALLOW** the daemon forks the child: `setsid`; if a pty, open the slave +
`TIOCSCTTY` and apply the client window size; std fds = pty slave for the tty
ones else the received fds; close everything else; if target uid ≠ 0
`setgroups`/`setresgid`/`setresuid`; reset signal dispositions and mask;
`chdir(cwd)` (fallback `/`); `execve`.

---

## Output lines & exit codes

| situation | output | exit |
|---|---|---|
| client: connect failed | `su: root chưa bật / daemon không chạy (CloudBlue: Công cụ → 🔓 Root)` | 1 |
| client: denied | `su: app này chưa được cấp quyền root — bật trong CloudBlue: Công cụ → 🔓 Root` | 1 |
| client: allowed | — | child's exit status (`128+sig` if signalled) |
| `cpsu daemon`: socket in use | `cpsu: socket @<name> already in use` | 2 |
| `cpsu status` | `RUNNING …` / `STOPPED` | 0 / 3 |
| `cpsu stop` | `STOP_OK` / `STOP_NONE` | 0 / 3 |
| `cpsu install` | `INSTALL_OK …` / `INSTALL_FAIL <reason>` | 0 / 1 |
| `cpsu uninstall` | `UNINSTALL_OK` | 0 |
| `su -v` / `-V` / `cpsu version` | `2.0:CPSU` / `200` / `2.0:CPSU` | 0 |

---

## Syscalls made by the client (`cpsu-su-x86_64`)

Recorded with `strace` from the `execve` of `su` onwards, running as app uid 10123/10124:

| path | syscalls |
|---|---|
| no tty (`echo hi \| su -c cat`) | `close connect dup exit_group getcwd getuid ioctl read recvmsg rt_sigaction sendmsg socket write` |
| pty session | same + `ppoll` |
| denied | `close connect dup exit_group getcwd getuid ioctl recvmsg rt_sigaction sendmsg socket write` |

Plus `rt_sigreturn` when a signal arrives (SIGWINCH). Only when already root (adb root shortcut,
outside the app sandbox): `chdir setgroups setresgid setresuid execve`.

---

## Tests

`python3 test_cpsu.py` (run as root). Uses the built binary with a temp dir, a
fake `packages.list`/`allow`, and a daemon with `--shell /bin/sh` (or a
`/system/bin/sh` → `/bin/sh` symlink). App uids are simulated by dropping
privileges (`setresuid`) in forked children; pty tests use Python's `pty`.

**Result: 49 / 49 passing with either client** (`CPSU_SU_BIN=$PWD/cpsu-su-x86_64 python3 test_cpsu.py` runs the suite with the libc-free client; repeated 4×, stable). Coverage:

* allow/deny by uid; 0 and 2000 always allowed; shared uid (10200 → two
  packages); multi-user uid 1010123 → appId 10123; isolated/app-zygote
  (≥90000) denied; appId < 10000 denied; `*` wildcard (mapped allowed, unmapped
  denied); `#` comments; **hot reload** of `allow` with no restart.
* exit-code passthrough (42) and signals (SIGKILL→137, SIGINT→130); pipe without
  tty (`echo hi | su -c cat`); stdout capture; extra positional args; cwd.
* target user root/shell/system/numeric; env rules (USER/LOGNAME/SHELL, PATH gets
  `/system/bin`, no duplication, `-p` preserve, custom vars); login (`cwd=/`,
  `argv0=-sh`).
* every CLI form (`-v`/`-V`/`-h`/`-c`/`-s`/`-l`/`-p`/`-mm`/`-Z`/`-t`/`--`,
  `cpsu version`).
* **pty session**: `id` → uid 0; `stty size` shows the client window (37×123);
  **Ctrl+C interrupts `sleep 100` but the interactive shell survives** and the
  client keeps running; exit status returned over the pty.
* client with daemon down (app uid → message, exit 1); `getuid()==0` shortcut
  works when the daemon is down.
* logging: decisions logged, **commands never logged**, truncation past 64 KB.
* 20 parallel clients; malformed / oversized / wrong-version requests don't kill
  the daemon; `stop`/`status`; socket-in-use → exit 2; non-root `stop` refused.
* `install`/`uninstall` against temp paths (tmpfs + bind mounts, with the copy
  and `D/mounts` bookkeeping verified; the mount assertions self-skip where
  mounting isn't permitted); unreadable `packages.list` → apps denied, uid 2000
  still allowed; `--notify` fires once and is rate-limited.

---

## Server integration (not built here)

Over `adb shell` as root:

1. push `cpsu-x86_64` → `/data/adb/cpsu/cpsu` and `cpsu-su-x86_64` → `/data/adb/cpsu/su` (both `0755`);
2. `/data/adb/cpsu/cpsu install --bind /system/xbin/su,/system/bin/su [--notify]` — copies `DIR/su`
   to `/debug_ramdisk/su` (Termux looks there first), binds it over existing `su` files, starts the daemon;
3. write the per-phone allowlist to `/data/adb/cpsu/allow` (edits apply on the next request);
4. `cpsu uninstall` = Root switch off. After every VM boot the server re-runs step 2 if Root is on.

The daemon must run as root and be able to open `/dev/ptmx` and `setresuid`; it is started
from the (already-root) adb context. Whether apps can exec `/debug_ramdisk/su` and connect to
the daemon's socket depends on the VM's SELinux mode — check on a real VM first.

---

## Known limits

* The **daemon** binary is glibc-static here (no musl in the build container) — acceptable because
  it never runs inside the app sandbox. The **client** is libc-free.
* **aarch64** not built (no aarch64 musl cross here).
* On-device behaviour under real Android **seccomp/SELinux** could not be tested
  in this Linux container (no Android, no app sandbox); the test suite validates
  the protocol, permission logic, pty/exec semantics and lifecycle on Linux.
* Protocol is same-arch, host-endian local IPC (by design — client and daemon
  are the same binary on the same VM).
* The allowlist governs who may obtain root only; it does not and will not hide
  root from other apps.
