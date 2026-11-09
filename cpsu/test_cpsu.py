#!/usr/bin/env python3
# Test suite for cpsu. Run as root:  python3 test_cpsu.py
#
# Uses the built ./cpsu-x86_64 with a temp dir, fake packages.list / allow,
# and a daemon whose shell is /bin/sh (or /system/bin/sh symlink). App uids
# are simulated by dropping privileges (setresuid) in a forked child.
import os, sys, socket, struct, subprocess, tempfile, time, shutil, signal
import select, pty, fcntl, termios, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BIN  = os.path.join(HERE, "cpsu-x86_64")

# packages.list: appId is the 2nd column.
PKGS = """\
com.termux 10123 0 /data/user/0/com.termux default:targetSdkVersion=28 3003
com.foo.bar 10124 0 /data/user/0/com.foo.bar default 3003
com.shared.a 10200 0 /data/user/0/com.shared.a default 1
com.shared.b 10200 0 /data/user/0/com.shared.b default 1
com.high.app 10500 0 /data/user/0/com.high.app default 1
"""

WORK = None
BINDIR = None
SU = None
MAIN_SOCK = "cpsu_t_main"
MAIN_DIR = None
PKGS_PATH = None
daemons = []   # (sock, dir, popen)


def sh_path():
    if os.path.exists("/system/bin/sh"):
        return "/system/bin/sh"
    return "/bin/sh"


def setUpModule():
    global WORK, BINDIR, SU, MAIN_DIR, PKGS_PATH
    assert os.geteuid() == 0, "run as root"
    assert os.path.exists(BIN), "build cpsu-x86_64 first (sh build.sh)"
    WORK = tempfile.mkdtemp(prefix="cpsu_test_")
    os.chmod(WORK, 0o755)                 # let dropped uids traverse to exec su
    BINDIR = os.path.join(WORK, "bin")
    os.makedirs(BINDIR)
    os.chmod(BINDIR, 0o755)
    SU = os.path.join(BINDIR, "su")
    shutil.copy2(os.environ.get("CPSU_SU_BIN") or BIN, SU)   # client: multi-call binary, or the libc-free cpsu-su-x86_64
    os.chmod(SU, 0o755)
    PKGS_PATH = os.path.join(WORK, "packages.list")
    with open(PKGS_PATH, "w") as f:
        f.write(PKGS)
    MAIN_DIR = os.path.join(WORK, "main")
    os.makedirs(MAIN_DIR, 0o700)
    start_daemon(MAIN_SOCK, MAIN_DIR, PKGS_PATH)


def tearDownModule():
    for sock, d, p in daemons:
        try:
            subprocess.run([BIN, "stop", "--sock", sock, "--dir", d],
                           capture_output=True, timeout=5)
        except Exception:
            pass
        if p:
            try: p.wait(timeout=3)
            except Exception: p.kill()
    if WORK:
        shutil.rmtree(WORK, ignore_errors=True)


def start_daemon(sock, d, pkgs, shell=None, notify=False, notify_cmd=None, fg=False):
    os.makedirs(d, exist_ok=True)
    args = [BIN, "daemon", "--sock", sock, "--dir", d, "--packages", pkgs,
            "--shell", shell or sh_path()]
    if notify: args.append("--notify")
    if notify_cmd: args += ["--notify-cmd", notify_cmd]
    if fg: args.append("--fg")
    p = subprocess.Popen(args)
    daemons.append((sock, d, p if fg else None))
    # wait until status reports RUNNING
    for _ in range(200):
        r = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        if r.returncode == 0 and b"RUNNING" in r.stdout:
            if not fg:
                try: p.wait(timeout=2)   # reap the intermediate (already double-forked away)
                except Exception: pass
            return p
        time.sleep(0.02)
    raise RuntimeError("daemon did not start: %s" % sock)


def _drop(uid):
    if uid is None:
        return None
    def f():
        os.setgroups([uid])
        os.setresgid(uid, uid, uid)
        os.setresuid(uid, uid, uid)
    return f


def run_su(args, uid=None, sock=MAIN_SOCK, env=None, input=None, timeout=15):
    e = {"PATH": "/usr/bin:/bin", "CPSU_SOCK": sock}
    if env:
        e.update(env)
    if isinstance(input, str):
        input = input.encode()
    p = subprocess.run([SU] + args, input=input, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=e, preexec_fn=_drop(uid),
                       timeout=timeout)
    return p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")


def write_allow(d, text):
    with open(os.path.join(d, "allow"), "w") as f:
        f.write(text)


def read_log(d):
    try:
        with open(os.path.join(d, "log")) as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ---- pty helper: run su on a pty, return (master_fd, child_pid) ----

def spawn_pty(args, uid=None, sock=MAIN_SOCK, rows=37, cols=123, env=None):
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            for i in range(3):
                os.dup2(slave, i)
            if slave > 2:
                os.close(slave)
            os.close(master)
            if uid is not None:
                os.setgroups([uid]); os.setresgid(uid, uid, uid); os.setresuid(uid, uid, uid)
            e = {"PATH": "/usr/bin:/bin", "CPSU_SOCK": sock}
            if env: e.update(env)
            os.execve(SU, ["su"] + args, e)
        except Exception:
            os._exit(127)
    os.close(slave)
    return master, pid


def pread_until(master, marker, timeout=8, acc=None):
    """Poll the pty in short slices until marker appears or timeout elapses."""
    if acc is None:
        acc = bytearray()
    if marker in bytes(acc):
        return True, acc
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([master], [], [], 0.2)
        if r:
            try:
                d = os.read(master, 4096)
            except OSError:
                break
            if not d:
                break
            acc += d
            if marker in bytes(acc):
                return True, acc
    return (marker in bytes(acc)), acc


def pdrain(master, timeout=6):
    """Read until the master reaches EOF (client closed) or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([master], [], [], max(0.0, end - time.time()))
        if not r:
            break
        try:
            d = os.read(master, 4096)
        except OSError:
            break
        if not d:
            break


# ============================= tests =============================

class TestPermissions(unittest.TestCase):
    def test_uid0_always_allowed(self):
        write_allow(MAIN_DIR, "")           # empty allowlist
        rc, out, err = run_su(["-c", "id -u"], uid=None)   # uid 0 -> local shortcut
        self.assertEqual(rc, 0); self.assertEqual(out.strip(), "0")

    def test_uid2000_always_allowed(self):
        write_allow(MAIN_DIR, "")
        rc, out, err = run_su(["-c", "id -u"], uid=2000)
        self.assertEqual(rc, 0, err); self.assertEqual(out.strip(), "0")

    def test_app_allow_and_deny(self):
        write_allow(MAIN_DIR, "com.termux\n")
        rc, out, _ = run_su(["-c", "id -u"], uid=10123)
        self.assertEqual(rc, 0); self.assertEqual(out.strip(), "0")
        rc, out, err = run_su(["-c", "id -u"], uid=10124)
        self.assertEqual(rc, 1); self.assertIn("chưa được cấp", err)

    def test_shared_uid(self):
        # uid 10200 maps to com.shared.a AND com.shared.b
        write_allow(MAIN_DIR, "com.shared.b\n")
        rc, out, _ = run_su(["-c", "id -u"], uid=10200)
        self.assertEqual(rc, 0); self.assertEqual(out.strip(), "0")
        write_allow(MAIN_DIR, "com.other\n")
        rc, _, _ = run_su(["-c", "id -u"], uid=10200)
        self.assertEqual(rc, 1)

    def test_multiuser_uid(self):
        write_allow(MAIN_DIR, "com.termux\n")
        rc, out, _ = run_su(["-c", "id -u"], uid=1010123)   # user 10 -> appId 10123
        self.assertEqual(rc, 0); self.assertEqual(out.strip(), "0")

    def test_isolated_and_zygote_denied(self):
        write_allow(MAIN_DIR, "*\n")
        for uid in (99005, 90000, 99999):   # isolated / app-zygote range
            rc, _, _ = run_su(["-c", "id -u"], uid=uid)
            self.assertEqual(rc, 1, "uid %d should be denied" % uid)

    def test_low_appid_denied(self):
        write_allow(MAIN_DIR, "*\n")
        rc, _, _ = run_su(["-c", "id -u"], uid=9999)   # appId<10000
        self.assertEqual(rc, 1)

    def test_wildcard(self):
        write_allow(MAIN_DIR, "*\n")
        rc, _, _ = run_su(["-c", "true"], uid=10124)   # mapped -> allow
        self.assertEqual(rc, 0)
        rc, _, _ = run_su(["-c", "true"], uid=10999)   # unmapped -> deny
        self.assertEqual(rc, 1)

    def test_hot_reload(self):
        write_allow(MAIN_DIR, "")
        rc, _, _ = run_su(["-c", "true"], uid=10123)
        self.assertEqual(rc, 1)
        write_allow(MAIN_DIR, "com.termux\n")          # no daemon restart
        rc, _, _ = run_su(["-c", "true"], uid=10123)
        self.assertEqual(rc, 0)

    def test_comments_in_allow(self):
        write_allow(MAIN_DIR, "# a comment\n   com.termux   \n#com.foo.bar\n")
        self.assertEqual(run_su(["-c", "true"], uid=10123)[0], 0)
        self.assertEqual(run_su(["-c", "true"], uid=10124)[0], 1)


class TestExecSemantics(unittest.TestCase):
    def setUp(self):
        write_allow(MAIN_DIR, "*\n")

    def test_exit_code(self):
        rc, _, _ = run_su(["-c", "exit 42"], uid=10123)
        self.assertEqual(rc, 42)

    def test_signal_exit_codes(self):
        self.assertEqual(run_su(["-c", "kill -9 $$"], uid=10123)[0], 137)
        self.assertEqual(run_su(["-c", "kill -INT $$"], uid=10123)[0], 130)

    def test_pipe_no_tty(self):
        rc, out, _ = run_su(["-c", "cat"], uid=10123, input="hi\n")
        self.assertEqual(rc, 0); self.assertEqual(out, "hi\n")

    def test_stdout_capture(self):
        rc, out, _ = run_su(["-c", "echo hello world"], uid=10123)
        self.assertEqual(out.strip(), "hello world")

    def test_extra_positional_args(self):
        # su -c CMD root AA BB  ->  sh -c CMD AA BB  (AA=$0, BB=$1)
        rc, out, _ = run_su(["-c", "echo $0-$1", "root", "AA", "BB"], uid=10123)
        self.assertEqual(out.strip(), "AA-BB")

    def test_cwd_preserved(self):
        rc, out, _ = run_su(["-c", "pwd"], uid=10123, timeout=15)
        # child chdir to client cwd (this process cwd = HERE)
        self.assertEqual(out.strip(), os.getcwd())


class TestTargetUser(unittest.TestCase):
    def setUp(self):
        write_allow(MAIN_DIR, "*\n")

    def test_target_shell(self):
        rc, out, _ = run_su(["shell", "-c", "id -u"], uid=10123)
        self.assertEqual(out.strip(), "2000")

    def test_target_system_numeric(self):
        rc, out, _ = run_su(["1000", "-c", "id -u"], uid=10123)
        self.assertEqual(out.strip(), "1000")

    def test_target_root_default(self):
        rc, out, _ = run_su(["-c", "id -u"], uid=10123)
        self.assertEqual(out.strip(), "0")


class TestEnvRules(unittest.TestCase):
    def setUp(self):
        write_allow(MAIN_DIR, "*\n")

    def test_user_logname_shell_set(self):
        rc, out, _ = run_su(["-c", "echo $USER:$LOGNAME:$SHELL"], uid=10123,
                            env={"USER": "app", "LOGNAME": "app"})
        self.assertEqual(out.strip(), "root:root:%s" % sh_path())

    def test_path_gets_system_bin(self):
        rc, out, _ = run_su(["-c", "echo $PATH"], uid=10123, env={"PATH": "/usr/bin"})
        self.assertIn("/system/bin", out)

    def test_path_not_duplicated(self):
        rc, out, _ = run_su(["-c", "echo $PATH"], uid=10123,
                            env={"PATH": "/system/bin:/x"})
        self.assertEqual(out.strip().count("/system/bin"), 1)

    def test_preserve_environment(self):
        rc, out, _ = run_su(["-p", "-c", "echo $USER"], uid=10123, env={"USER": "keepme"})
        self.assertEqual(out.strip(), "keepme")

    def test_custom_env_passed(self):
        rc, out, _ = run_su(["-c", "echo $MYVAR"], uid=10123, env={"MYVAR": "xyzzy"})
        self.assertEqual(out.strip(), "xyzzy")


class TestLogin(unittest.TestCase):
    def setUp(self):
        write_allow(MAIN_DIR, "*\n")

    def test_login_cwd_and_arg0(self):
        rc, out, _ = run_su(["-l", "-c", "echo $0 @ $(pwd)"], uid=10123)
        self.assertEqual(out.strip(), "-sh @ /")


class TestCLIForms(unittest.TestCase):
    def test_version_strings(self):
        self.assertEqual(run_su(["-v"])[1].strip(), "2.0:CPSU")
        self.assertEqual(run_su(["--version"])[1].strip(), "2.0:CPSU")
        self.assertEqual(run_su(["-V"])[1].strip(), "200")

    def test_help(self):
        rc, out, _ = run_su(["-h"])
        self.assertEqual(rc, 0); self.assertIn("usage", out.lower())

    def test_cpsu_version_subcommand(self):
        r = subprocess.run([BIN, "version"], capture_output=True)
        self.assertEqual(r.stdout.decode().strip(), "2.0:CPSU")

    def test_shell_option(self):
        write_allow(MAIN_DIR, "*\n")
        rc, out, _ = run_su(["-s", "/bin/sh", "-c", "echo $0"], uid=10123)
        self.assertEqual(rc, 0)

    def test_double_dash(self):
        write_allow(MAIN_DIR, "*\n")
        rc, out, _ = run_su(["-c", "echo done", "--"], uid=10123)
        self.assertEqual(out.strip(), "done")

    def test_mount_master_noop(self):
        write_allow(MAIN_DIR, "*\n")
        self.assertEqual(run_su(["-mm", "-c", "true"], uid=10123)[0], 0)
        self.assertEqual(run_su(["-M", "-c", "true"], uid=10123)[0], 0)

    def test_ignore_context_target(self):
        write_allow(MAIN_DIR, "*\n")
        rc, out, _ = run_su(["-Z", "u:r:x:s0", "-t", "1234", "-c", "id -u"], uid=10123)
        self.assertEqual(out.strip(), "0")


class TestDaemonDownAndShortcut(unittest.TestCase):
    def test_daemon_down_message(self):
        rc, out, err = run_su(["-c", "id"], uid=10123, sock="no_such_sock_zzz")
        self.assertEqual(rc, 1)
        self.assertIn("root chưa bật", err)

    def test_getuid0_shortcut_when_down(self):
        # root bypasses the daemon entirely (adb root keeps working)
        rc, out, _ = run_su(["-c", "id -u"], uid=None, sock="no_such_sock_zzz")
        self.assertEqual(rc, 0); self.assertEqual(out.strip(), "0")


class TestPty(unittest.TestCase):
    def setUp(self):
        write_allow(MAIN_DIR, "*\n")

    def test_id_and_window_size(self):
        master, pid = spawn_pty(["-c", "id -u; stty size"], uid=10123, rows=37, cols=123)
        ok, acc = pread_until(master, b"37 123", 8)
        os.waitpid(pid, 0); os.close(master)
        text = acc.decode(errors="replace")
        self.assertIn("0", text)            # id -u -> root
        self.assertIn("37 123", text)       # client window size seen by the root child

    def test_exit_status_over_pty(self):
        master, pid = spawn_pty(["-c", "exit 7"], uid=10123)
        pdrain(master, 5)
        _, st = os.waitpid(pid, 0); os.close(master)
        self.assertEqual(os.waitstatus_to_exitcode(st), 7)

    def test_ctrlc_interrupts_but_shell_survives(self):
        # interactive shell on a pty; Ctrl+C must kill `sleep 100`, not the shell,
        # and must not kill the client (which keeps pumping afterwards).
        master, pid = spawn_pty([], uid=10123)       # interactive sh
        time.sleep(0.4)                              # let the shell print its prompt
        acc = bytearray()
        os.write(master, b"echo R$((1+1))\n")
        ok, acc = pread_until(master, b"R2", 5, acc)
        self.assertTrue(ok, "shell not responding before Ctrl+C")
        os.write(master, b"sleep 100\n")
        time.sleep(0.6)
        os.write(master, b"\x03")                    # Ctrl+C -> SIGINT via pty line discipline
        time.sleep(0.3)
        os.write(master, b"echo S$((6*7))\n")        # S42 appears only if sleep was interrupted
        ok, acc = pread_until(master, b"S42", 8, acc)
        self.assertTrue(ok, "shell did not survive Ctrl+C / sleep not interrupted")
        os.write(master, b"exit 5\n")
        pdrain(master, 5)
        _, st = os.waitpid(pid, 0); os.close(master)
        self.assertEqual(os.waitstatus_to_exitcode(st), 5)


class TestLogging(unittest.TestCase):
    def test_log_has_decision_not_command(self):
        write_allow(MAIN_DIR, "com.termux\n")
        run_su(["-c", "echo SECRET_MARKER_XYZ"], uid=10123)
        run_su(["-c", "echo SECRET_MARKER_XYZ"], uid=10124)
        log = read_log(MAIN_DIR)
        self.assertIn("ALLOW", log); self.assertIn("DENY", log)
        self.assertIn("uid=10123", log)
        self.assertNotIn("SECRET_MARKER_XYZ", log)     # commands never logged

    def test_log_truncation(self):
        logp = os.path.join(MAIN_DIR, "log")
        with open(logp, "w") as f:
            f.write("x" * 70000 + "\n")                 # > 64 KB
        write_allow(MAIN_DIR, "com.termux\n")
        run_su(["-c", "true"], uid=10123)               # triggers truncation
        sz = os.path.getsize(logp)
        self.assertLessEqual(sz, 64 * 1024)
        self.assertIn("ALLOW", read_log(MAIN_DIR))


class TestConcurrency(unittest.TestCase):
    def test_20_parallel_clients(self):
        write_allow(MAIN_DIR, "*\n")
        results = [None] * 20
        def worker(i):
            rc, out, _ = run_su(["-c", "echo ok%d" % i], uid=10123)
            results[i] = (rc, out.strip())
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join(30)
        for i in range(20):
            self.assertEqual(results[i], (0, "ok%d" % i), "client %d failed" % i)


class TestMalformed(unittest.TestCase):
    def _send_raw(self, payload):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect("\0" + MAIN_SOCK)
        s.sendall(payload)
        s.close()

    def test_garbage_does_not_kill_daemon(self):
        self._send_raw(b"\xff" * 10)
        self._send_raw(b"garbage-not-a-header-at-all")
        # oversized claimed body: valid magic, body_len huge
        hdr = b"CPS1" + struct.pack("<IIIHHHHIII", 1, 0, 0, 0, 0, 0, 0, 1, 1, 0x7fffffff)
        self._send_raw(hdr)
        # short header then close
        self._send_raw(b"CPS1")
        time.sleep(0.2)
        # daemon must still be alive and answer normally
        write_allow(MAIN_DIR, "*\n")
        rc, out, _ = run_su(["-c", "echo survived"], uid=10123)
        self.assertEqual(out.strip(), "survived")

    def test_wrong_version_rejected(self):
        write_allow(MAIN_DIR, "*\n")
        # still alive after a bad-version header
        hdr = b"CPS1" + struct.pack("<IIIHHHHIII", 999, 0, 0, 0, 0, 0, 0, 1, 1, 4)
        self._send_raw(hdr + b"a\0b\0")
        self.assertEqual(run_su(["-c", "true"], uid=10123)[0], 0)


class TestUnreadablePackages(unittest.TestCase):
    def test_unreadable_packages_denies_apps(self):
        d = os.path.join(WORK, "nopkg")
        start_daemon("cpsu_t_nopkg", d, os.path.join(WORK, "does_not_exist.list"))
        write_allow(d, "*\n")
        rc, _, _ = run_su(["-c", "true"], uid=10123, sock="cpsu_t_nopkg")
        self.assertEqual(rc, 1)                          # packages.list unreadable -> deny
        rc, out, _ = run_su(["-c", "id -u"], uid=2000, sock="cpsu_t_nopkg")
        self.assertEqual(out.strip(), "0")               # uid 2000 still allowed


class TestStopStatus(unittest.TestCase):
    def test_status_and_stop(self):
        d = os.path.join(WORK, "ss")
        start_daemon("cpsu_t_ss", d, PKGS_PATH)
        r = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"RUNNING", r.stdout)
        self.assertIn(b"version=2.0:CPSU", r.stdout)
        r = subprocess.run([BIN, "stop", "--sock", "cpsu_t_ss", "--dir", d], capture_output=True)
        self.assertEqual(r.returncode, 0); self.assertIn(b"STOP_OK", r.stdout)
        time.sleep(0.3)
        r = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        self.assertEqual(r.returncode, 3); self.assertIn(b"STOPPED", r.stdout)

    def test_socket_in_use_exits_2(self):
        d = os.path.join(WORK, "inuse")
        start_daemon("cpsu_t_inuse", d, PKGS_PATH)
        r = subprocess.run([BIN, "daemon", "--fg", "--sock", "cpsu_t_inuse",
                            "--dir", d, "--packages", PKGS_PATH], capture_output=True, timeout=5)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"already in use", r.stdout + r.stderr)

    def test_stop_nonroot_denied(self):
        # control stop from an app uid is refused; daemon stays up
        d = os.path.join(WORK, "ss2")
        start_daemon("cpsu_t_ss2", d, PKGS_PATH)
        def stop_as_app():
            os.setgroups([10123]); os.setresgid(10123,10123,10123); os.setresuid(10123,10123,10123)
        r = subprocess.run([BIN, "stop", "--sock", "cpsu_t_ss2", "--dir", "/nonexistent_dir_zzz"],
                           capture_output=True, preexec_fn=stop_as_app, timeout=5)
        time.sleep(0.2)
        s = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        self.assertIn(b"RUNNING", s.stdout)              # survived app stop attempt


class TestInstallUninstall(unittest.TestCase):
    def _can_mount(self):
        probe = tempfile.mkdtemp(prefix="cpsu_mnt_")
        try:
            subprocess.run(["mount", "-t", "tmpfs", "tmpfs", probe], check=True,
                           capture_output=True)
            subprocess.run(["umount", "-l", probe], capture_output=True)
            return True
        except Exception:
            return False
        finally:
            shutil.rmtree(probe, ignore_errors=True)

    def test_install_uninstall(self):
        d = os.path.join(WORK, "inst")
        os.makedirs(d, 0o700)
        ramdisk = os.path.join(WORK, "ramdisk")
        os.makedirs(ramdisk)
        bindfile = os.path.join(WORK, "fake_xbin_su")
        with open(bindfile, "w") as f:
            f.write("ORIGINAL")
        sock = "cpsu_t_inst"
        can_mount = self._can_mount()

        r = subprocess.run([BIN, "install", "--dir", d, "--sock", sock,
                            "--ramdisk", ramdisk, "--bind", bindfile,
                            "--src", BIN, "--packages", PKGS_PATH,
                            "--shell", sh_path()], capture_output=True, timeout=10)
        self.assertIn(b"INSTALL_OK", r.stdout, r.stdout + r.stderr)

        # copy always happens
        subin = os.path.join(ramdisk, "su")
        self.assertTrue(os.path.exists(subin))
        self.assertEqual(os.path.getsize(subin), os.path.getsize(BIN))
        self.assertEqual(os.stat(subin).st_mode & 0o777, 0o755)

        # daemon started
        s = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        self.assertIn(b"RUNNING", s.stdout)

        if can_mount:
            mounts = open(os.path.join(d, "mounts")).read()
            self.assertIn("tmpfs", mounts)
            self.assertIn("bind %s" % bindfile, mounts)
            # bind-mount replaced the file content with the binary
            with open(bindfile, "rb") as f:
                self.assertEqual(f.read(4), b"\x7fELF")

        r = subprocess.run([BIN, "uninstall", "--dir", d, "--sock", sock,
                            "--ramdisk", ramdisk], capture_output=True, timeout=10)
        self.assertIn(b"UNINSTALL_OK", r.stdout)
        time.sleep(0.3)
        s = subprocess.run([BIN, "status", "--dir", d], capture_output=True)
        self.assertEqual(s.returncode, 3)                # daemon stopped
        if can_mount:
            with open(bindfile) as f:
                self.assertEqual(f.read(), "ORIGINAL")   # bind undone


    def test_install_default_src_and_busy_su(self):
        """No --src: install copies DIR/su (the libc-free client). Re-install while that
        su is still running must not fail with ETXTBSY (temp file + rename)."""
        d = os.path.join(WORK, "inst2")
        os.makedirs(d, 0o700)
        client = os.environ.get("CPSU_SU_BIN") or BIN
        shutil.copy2(client, os.path.join(d, "su")); os.chmod(os.path.join(d, "su"), 0o755)
        ramdisk = os.path.join(WORK, "ramdisk2")
        os.makedirs(ramdisk)
        sock = "cpsu_t_inst2"
        args = [BIN, "install", "--dir", d, "--sock", sock, "--ramdisk", ramdisk,
                "--packages", PKGS_PATH, "--shell", sh_path()]
        r = subprocess.run(args, capture_output=True, timeout=10)
        self.assertIn(b"INSTALL_OK", r.stdout, r.stdout + r.stderr)
        subin = os.path.join(ramdisk, "su")
        self.assertEqual(open(subin, "rb").read(), open(client, "rb").read())
        # keep the installed su busy (root shortcut -> exec sleep keeps the inode mapped only
        # until exec, so run it through the daemon as an app uid: client stays alive)
        with open(os.path.join(d, "allow"), "w") as f:
            f.write("com.termux\n")
        env = dict(os.environ, CPSU_SOCK=sock)
        pid = os.fork()
        if pid == 0:
            try:
                os.setgroups([]); os.setresgid(10123, 10123, 10123); os.setresuid(10123, 10123, 10123)
                os.execve(subin, [subin, "-c", "sleep 2"], env)
            finally:
                os._exit(99)
        time.sleep(0.5)
        r2 = subprocess.run(args, capture_output=True, timeout=10)      # re-install while busy
        self.assertIn(b"INSTALL_OK", r2.stdout, r2.stdout + r2.stderr)
        _, st = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(st), 0)
        self.assertFalse(os.path.exists(os.path.join(ramdisk, ".su.new")))
        subprocess.run([BIN, "uninstall", "--dir", d, "--sock", sock, "--ramdisk", ramdisk],
                       capture_output=True, timeout=10)


class TestNotify(unittest.TestCase):
    def test_notify_on_deny(self):
        # --notify-cmd points at a wrapper that records its argv
        d = os.path.join(WORK, "notify")
        os.makedirs(d, 0o700)
        marker = os.path.join(WORK, "notify_out.txt")
        wrapper = os.path.join(WORK, "fake_cmd.sh")
        with open(wrapper, "w") as f:
            f.write("#!/bin/sh\nprintf '%s\\n' \"$*\" >> " + marker + "\n")
        os.chmod(wrapper, 0o755)
        start_daemon("cpsu_t_notify", d, PKGS_PATH, notify=True, notify_cmd=wrapper)
        write_allow(d, "")
        run_su(["-c", "true"], uid=10124, sock="cpsu_t_notify")   # deny -> notify
        time.sleep(0.6)
        self.assertTrue(os.path.exists(marker), "notify command not invoked")
        content = open(marker).read()
        self.assertIn("com.foo.bar", content)
        self.assertIn("root", content)
        # rate-limit: a second deny within 60s should NOT notify again
        n1 = len(open(marker).read().splitlines())
        run_su(["-c", "true"], uid=10124, sock="cpsu_t_notify")
        time.sleep(0.6)
        n2 = len(open(marker).read().splitlines())
        self.assertEqual(n1, n2, "notify not rate-limited")


if __name__ == "__main__":
    unittest.main(verbosity=2)
