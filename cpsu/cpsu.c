/* cpsu - per-app superuser for MuMu / Android x86_64 emulator VMs.
 * Multi-call binary: argv0 "su" = client; "cpsu daemon|stop|status|install|
 * uninstall|version" = the rest. The root daemon (started from adb) checks a
 * connecting app's peer uid against /data/system/packages.list + an allow
 * file; if allowed it forks a root child wired to the client's std fds (pty
 * when on a terminal) and reports the exit status. The allowlist only decides
 * who may OBTAIN root - it hides nothing (no deny lists / unmount / SELinux
 * spoofing). See README.md for the wire protocol and device files. */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>

#define CPSU_VERSION   "2.0:CPSU"
#define CPSU_VCODE     "200"
#define PROTO_MAGIC    "CPS1"
#define CTRL_MAGIC     "CPSC"
#define PROTO_VERSION  1u

#define DEF_SOCK       "cpsu"
#define DEF_DIR        "/data/adb/cpsu"
#define DEF_PKGS       "/data/system/packages.list"
#define DEF_SHELL      "/system/bin/sh"
#define DEF_RAMDISK    "/debug_ramdisk"
#define DEF_NOTIFY_CMD "/system/bin/cmd"

#define MAX_BODY   (256 * 1024)
#define MAX_ITEMS  4096          /* cap on argv and on env entries each */
#define MAX_CONC   64            /* concurrent handlers */
#define REQ_TMO    10            /* seconds to read a whole request */
#define LOG_CAP    (64 * 1024)
#define LOG_KEEP   (32 * 1024)
#define NOTIFY_GAP 60            /* seconds between notifications per package */

/* request flags */
#define F_STDIN_TTY  1
#define F_STDOUT_TTY 2
#define F_STDERR_TTY 4
#define F_LOGIN      8
#define F_PRESERVE   16

/* response codes */
#define R_ALLOW 1
#define R_DENY  2
#define R_ERR   3
#define R_HASPTY 1

/* control commands */
#define C_STOP 1

#pragma pack(push, 1)
struct req_hdr {
	char     magic[4];
	uint32_t version;
	uint32_t target_uid;
	uint32_t flags;
	uint16_t ws_row, ws_col, ws_xpix, ws_ypix;
	uint32_t n_args;
	uint32_t n_env;
	uint32_t body_len;
};
struct resp_hdr { uint32_t code; uint32_t flags; };
#pragma pack(pop)

/* ------------------------------------------------------------------ utils */

static void die(const char *fmt, ...) {
	va_list ap; va_start(ap, fmt);
	vfprintf(stderr, fmt, ap); va_end(ap);
	fputc('\n', stderr);
	exit(1);
}

static void *xmalloc(size_t n) { void *p = malloc(n ? n : 1); if (!p) die("oom"); return p; }

static int write_all(int fd, const void *b, size_t n) {
	const char *p = b;
	while (n) {
		ssize_t k = write(fd, p, n);
		if (k < 0) { if (errno == EINTR) continue; return -1; }
		if (k == 0) return -1;
		p += k; n -= (size_t)k;
	}
	return 0;
}

static int read_all(int fd, void *b, size_t n) {
	char *p = b;
	while (n) {
		ssize_t k = read(fd, p, n);
		if (k < 0) { if (errno == EINTR) continue; return -1; }
		if (k == 0) return -1;
		p += k; n -= (size_t)k;
	}
	return 0;
}

/* read a whole small file into a NUL-terminated buffer; *len excludes NUL. */
static char *read_file(const char *path, size_t *len) {
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) return NULL;
	size_t cap = 4096, n = 0; char *buf = xmalloc(cap);
	for (;;) {
		if (n + 4096 + 1 > cap) { cap *= 2; buf = realloc(buf, cap); if (!buf) die("oom"); }
		ssize_t k = read(fd, buf + n, 4096);
		if (k < 0) { if (errno == EINTR) continue; close(fd); free(buf); return NULL; }
		if (k == 0) break;
		n += (size_t)k;
		if (n > 8 * 1024 * 1024) break; /* sanity */
	}
	close(fd);
	buf[n] = 0; if (len) *len = n;
	return buf;
}

static char *trim(char *s) {
	while (*s && isspace((unsigned char)*s)) s++;
	char *e = s + strlen(s);
	while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
	return s;
}

/* abstract-socket address: sun_path[0]=NUL then name. */
static socklen_t abstract_addr(struct sockaddr_un *a, const char *name) {
	memset(a, 0, sizeof *a);
	a->sun_family = AF_UNIX;
	size_t n = strlen(name);
	if (n > sizeof a->sun_path - 2) n = sizeof a->sun_path - 2;
	memcpy(a->sun_path + 1, name, n);
	return (socklen_t)(offsetof(struct sockaddr_un, sun_path) + 1 + n);
}

/* send data + optional fds in one message. */
static int send_fds(int s, const void *data, size_t len, const int *fds, int nfd) {
	char cbuf[CMSG_SPACE(sizeof(int) * 8)];
	struct iovec io = { (void *)data, len };
	struct msghdr m = {0};
	m.msg_iov = &io; m.msg_iovlen = 1;
	if (nfd > 0) {
		memset(cbuf, 0, sizeof cbuf);
		m.msg_control = cbuf;
		m.msg_controllen = CMSG_SPACE(sizeof(int) * nfd);
		struct cmsghdr *c = CMSG_FIRSTHDR(&m);
		c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS;
		c->cmsg_len = CMSG_LEN(sizeof(int) * nfd);
		memcpy(CMSG_DATA(c), fds, sizeof(int) * nfd);
		m.msg_controllen = c->cmsg_len;
	}
	for (;;) {
		ssize_t k = sendmsg(s, &m, MSG_NOSIGNAL);
		if (k < 0) { if (errno == EINTR) continue; return -1; }
		return (size_t)k == len ? 0 : -1;
	}
}

/* receive exactly len bytes; collect up to maxfd fds (only on first segment). */
static int recv_fds(int s, void *data, size_t len, int *fds, int *nfd, int maxfd) {
	char cbuf[CMSG_SPACE(sizeof(int) * 8)];
	struct iovec io = { data, len };
	struct msghdr m = {0};
	m.msg_iov = &io; m.msg_iovlen = 1;
	m.msg_control = cbuf; m.msg_controllen = sizeof cbuf;
	*nfd = 0;
	ssize_t k;
	for (;;) { k = recvmsg(s, &m, 0); if (k < 0 && errno == EINTR) continue; break; }
	if (k <= 0) return -1;
	struct cmsghdr *c;
	for (c = CMSG_FIRSTHDR(&m); c; c = CMSG_NXTHDR(&m, c)) {
		if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS) {
			int cnt = (int)((c->cmsg_len - CMSG_LEN(0)) / sizeof(int));
			for (int i = 0; i < cnt; i++) {
				int f; memcpy(&f, CMSG_DATA(c) + i * sizeof(int), sizeof(int));
				if (*nfd < maxfd) fds[(*nfd)++] = f; else close(f);
			}
		}
	}
	if ((size_t)k < len) { /* rest arrives without ancillary data */
		if (read_all(s, (char *)data + k, len - (size_t)k)) return -1;
	}
	return 0;
}

static int connect_sock(const char *name) {
	int s = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (s < 0) return -1;
	struct sockaddr_un a; socklen_t al = abstract_addr(&a, name);
	if (connect(s, (struct sockaddr *)&a, al)) { close(s); return -1; }
	return s;
}

/* ------------------------------------------------------- allowlist / rules */

/* collect packages whose appId matches; returns count, fills names (joined
 * caller-owned). pkgs file content in buf. */
struct pkgset { char **name; int n; };

static void pkgset_add(struct pkgset *p, const char *s) {
	p->name = realloc(p->name, sizeof(char *) * (p->n + 1));
	if (!p->name) die("oom");
	p->name[p->n++] = strdup(s);
}
static void pkgset_free(struct pkgset *p) {
	for (int i = 0; i < p->n; i++) free(p->name[i]);
	free(p->name);
}

/* Fill ps with every package name whose appId == appid. Return 0 ok,
 * -1 if packages.list unreadable. */
static int packages_for(const char *pkgs_path, int appid, struct pkgset *ps) {
	size_t len; char *buf = read_file(pkgs_path, &len);
	if (!buf) return -1;
	char *save, *line = strtok_r(buf, "\n", &save);
	while (line) {
		char *name = line; char *sp = strchr(line, ' ');
		if (sp) {
			*sp = 0;
			int uid = atoi(sp + 1);
			if (uid % 100000 == appid && *name) pkgset_add(ps, name);
		}
		line = strtok_r(NULL, "\n", &save);
	}
	free(buf);
	return 0;
}

/* Decide allow for a non-system uid given its packages. allow_path lines:
 * package per line, '#' comment, '*' = any uid mapping to >=1 package. */
static int allow_decides(const char *allow_path, struct pkgset *ps) {
	size_t len; char *buf = read_file(allow_path, &len);
	if (!buf) return 0;
	int ok = 0;
	char *save, *line = strtok_r(buf, "\n", &save);
	while (line && !ok) {
		char *t = trim(line);
		if (*t && *t != '#') {
			if (!strcmp(t, "*")) { if (ps->n > 0) ok = 1; }
			else for (int i = 0; i < ps->n; i++)
				if (!strcmp(t, ps->name[i])) { ok = 1; break; }
		}
		line = strtok_r(NULL, "\n", &save);
	}
	free(buf);
	return ok;
}

/* ------------------------------------------------------------ daemon state */

struct dcfg {
	const char *sock, *dir, *pkgs, *shell, *notify_cmd;
	int notify, fg;
};

static volatile sig_atomic_t g_stop = 0;
static volatile sig_atomic_t g_active = 0;

static void on_term(int sig) { (void)sig; g_stop = 1; }
static void on_chld(int sig) {
	(void)sig; int st;
	while (waitpid(-1, &st, WNOHANG) > 0) if (g_active > 0) g_active--;
}

static void dpath(char *out, size_t n, const char *dir, const char *f) {
	snprintf(out, n, "%s/%s", dir, f);
}

static void log_decision(const struct dcfg *c, uid_t uid, struct pkgset *ps, int allow) {
	char path[512]; dpath(path, sizeof path, c->dir, "log");
	int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
	if (fd < 0) return;
	flock(fd, LOCK_EX);
	char ts[64]; time_t t = time(NULL); struct tm tm;
	localtime_r(&t, &tm);
	strftime(ts, sizeof ts, "%Y-%m-%dT%H:%M:%S%z", &tm);
	/* join package names */
	size_t jl = 1; for (int i = 0; i < ps->n; i++) jl += strlen(ps->name[i]) + 1;
	char *j = xmalloc(jl); j[0] = 0;
	for (int i = 0; i < ps->n; i++) { if (i) strcat(j, ","); strcat(j, ps->name[i]); }
	char line[1024];
	int ln = snprintf(line, sizeof line, "%s uid=%u pkgs=%s %s\n",
	                  ts, (unsigned)uid, ps->n ? j : "-", allow ? "ALLOW" : "DENY");
	free(j);
	if (ln > 0) write_all(fd, line, (size_t)ln);
	/* truncate: keep last ~LOG_KEEP from a line boundary */
	struct stat st;
	if (!fstat(fd, &st) && st.st_size > LOG_CAP) {
		size_t sz; char *all = read_file(path, &sz);
		if (all && sz > LOG_KEEP) {
			char *keep = all + (sz - LOG_KEEP);
			char *nl = strchr(keep, '\n');
			if (nl) keep = nl + 1;
			int t2 = open(path, O_WRONLY | O_TRUNC | O_CLOEXEC, 0600);
			if (t2 >= 0) { write_all(t2, keep, strlen(keep)); close(t2); }
		}
		free(all);
	}
	flock(fd, LOCK_UN);
	close(fd);
}

/* notify at most once per package per NOTIFY_GAP seconds (filesystem stamp). */
static void maybe_notify(const struct dcfg *c, const char *pkg) {
	if (!c->notify) return;
	char ndir[512]; dpath(ndir, sizeof ndir, c->dir, "notify");
	mkdir(ndir, 0700);
	char safe[256]; size_t j = 0;
	for (const char *p = pkg; *p && j < sizeof safe - 1; p++)
		safe[j++] = (isalnum((unsigned char)*p) || *p == '.' || *p == '_') ? *p : '_';
	safe[j] = 0;
	char stamp[800]; snprintf(stamp, sizeof stamp, "%s/%s", ndir, safe);
	struct stat st; time_t now = time(NULL);
	if (!stat(stamp, &st) && now - st.st_mtime < NOTIFY_GAP) return;
	int fd = open(stamp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
	if (fd >= 0) close(fd);
	char msg[512];
	snprintf(msg, sizeof msg,
	         "%s xin quy\u1ec1n root \u2014 b\u1eadt trong CloudBlue: C\u00f4ng c\u1ee5 \u2192 \U0001f513 Root", pkg);
	pid_t p = fork();
	if (p == 0) {                       /* double-fork, detach, never block */
		if (fork() == 0) {
			setsid();
			for (int i = 0; i < 3; i++) { int n = open("/dev/null", O_RDWR); if (n >= 0) { dup2(n, i); if (n > 2) close(n); } }
			execl(c->notify_cmd, "cmd", "notification", "post",
			      "-t", "Quy\u1ec1n root", "cpsu", msg, (char *)NULL);
			_exit(127);
		}
		_exit(0);
	}
	if (p > 0) waitpid(p, NULL, 0);
}

/* ------------------------------------------------------------ exec a child */

/* build final std fds and exec in the (already forked) child. Never returns
 * on success. fds[] are the 3 received client fds; ttymask tells which were
 * ttys; slave is the pty slave or -1. */
static void child_exec(int *fds, int ttymask, int slave,
                       uid_t uid, const char *shell,
                       char **argv, char **envp, const char *cwd) {
	setsid();
	if (slave >= 0) ioctl(slave, TIOCSCTTY, 0);
	for (int i = 0; i < 3; i++) {
		int src = (slave >= 0 && (ttymask & (1 << i))) ? slave : fds[i];
		if (src != i) dup2(src, i);
	}
	/* close everything above 2 */
	for (int i = 3; i < 1024; i++) close(i);
	if (uid != 0) {
		gid_t g = (gid_t)uid;
		if (setgroups(1, &g) || setresgid(g, g, g) || setresuid(uid, uid, uid)) _exit(126);
	}
	for (int s = 1; s < NSIG; s++) signal(s, SIG_DFL);
	sigset_t all; sigemptyset(&all); sigprocmask(SIG_SETMASK, &all, NULL);
	if (chdir(cwd) != 0) { if (chdir("/") != 0) {} }
	execve(shell, argv, envp);
	_exit(127);
}

/* ------------------------------------------------------------ serve client */

static void serve(const struct dcfg *c, int s) {
	/* Handler reaps its OWN child; drop the inherited daemon SIGCHLD reaper
	 * (on_chld) so it cannot steal our child before our waitpid(). */
	signal(SIGCHLD, SIG_DFL);
	struct timeval tv = { REQ_TMO, 0 };
	setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
	setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);

	struct ucred cr; socklen_t crl = sizeof cr;
	if (getsockopt(s, SOL_SOCKET, SO_PEERCRED, &cr, &crl)) return;

	/* first read header + any fds */
	struct req_hdr h; int fds[3], nfd = 0;
	if (recv_fds(s, &h, sizeof h, fds, &nfd, 3)) return;

	if (!memcmp(h.magic, CTRL_MAGIC, 4)) {              /* control request */
		int ok = (cr.uid == 0 || cr.uid == 2000);       /* cmd carried in target_uid */
		struct resp_hdr rp = { ok ? R_ALLOW : R_DENY, 0 };
		send_fds(s, &rp, sizeof rp, NULL, 0);
		if (ok && h.target_uid == C_STOP) kill(getppid(), SIGTERM);
		return;
	}
	if (memcmp(h.magic, PROTO_MAGIC, 4) || h.version != PROTO_VERSION) return;
	if (nfd != 3) { for (int i = 0; i < nfd; i++) close(fds[i]); return; }
	if (h.body_len > MAX_BODY || h.n_args > MAX_ITEMS || h.n_env > MAX_ITEMS
	    || h.n_args == 0) goto deny_fds;

	char *body = xmalloc(h.body_len + 1);
	if (read_all(s, body, h.body_len)) { free(body); goto close_fds; }
	body[h.body_len] = 0;

	/* split body: shell, cwd, argv[n_args], env[n_env] */
	char **item = xmalloc(sizeof(char *) * (2 + h.n_args + h.n_env + 1));
	uint32_t want = 2 + h.n_args + h.n_env, got = 0;
	char *p = body, *end = body + h.body_len;
	while (got < want && p <= end) {
		item[got++] = p;
		size_t rl = strnlen(p, (size_t)(end - p));
		if (p + rl >= end && got < want) break; /* missing NUL */
		p += rl + 1;
	}
	if (got != want) { free(item); free(body); goto deny_fds; }
	const char *req_shell = item[0];
	const char *cwd = item[1];
	char **argv = xmalloc(sizeof(char *) * (h.n_args + 1));
	for (uint32_t i = 0; i < h.n_args; i++) argv[i] = item[2 + i];
	argv[h.n_args] = NULL;
	char **envp = xmalloc(sizeof(char *) * (h.n_env + 1));
	for (uint32_t i = 0; i < h.n_env; i++) envp[i] = item[2 + h.n_args + i];
	envp[h.n_env] = NULL;

	/* ---- permission decision (re-reads files every request) ---- */
	struct pkgset ps = {0};
	int allow = 0, denied_pkgerr = 0, appid = (int)(cr.uid % 100000);
	if (cr.uid == 0 || cr.uid == 2000) allow = 1;        /* always allowed */
	else if (appid < 10000 || appid >= 90000) allow = 0; /* isolated/zygote/system */
	else if (packages_for(c->pkgs, appid, &ps) < 0) denied_pkgerr = 1; /* unreadable -> deny */
	else { char ap[512]; dpath(ap, sizeof ap, c->dir, "allow"); allow = allow_decides(ap, &ps); }
	log_decision(c, cr.uid, &ps, allow);
	if (!allow && c->notify && !denied_pkgerr) {
		if (ps.n > 0) for (int i = 0; i < ps.n; i++) maybe_notify(c, ps.name[i]);
		else { char u[32]; snprintf(u, sizeof u, "uid-%u", (unsigned)cr.uid); maybe_notify(c, u); }
	}

	if (!allow) {
		pkgset_free(&ps);
		struct resp_hdr rp = { R_DENY, 0 };
		send_fds(s, &rp, sizeof rp, NULL, 0);
		free(argv); free(envp); free(item); free(body);
		goto close_fds;
	}
	pkgset_free(&ps);

	/* ---- set up pty if any std fd is a tty ---- */
	int ttymask = 0;
	if (h.flags & F_STDIN_TTY) ttymask |= 1;
	if (h.flags & F_STDOUT_TTY) ttymask |= 2;
	if (h.flags & F_STDERR_TTY) ttymask |= 4;
	int master = -1, slave = -1;
	if (ttymask) {
		master = open("/dev/ptmx", O_RDWR | O_NOCTTY | O_CLOEXEC);
		if (master >= 0) {
			int lock = 0; ioctl(master, TIOCSPTLCK, &lock);
			int ptn = 0; ioctl(master, TIOCGPTN, &ptn);
			char sp[64]; snprintf(sp, sizeof sp, "/dev/pts/%d", ptn);
			slave = open(sp, O_RDWR | O_NOCTTY | O_CLOEXEC);
			if (slave >= 0) {
				struct winsize ws = { h.ws_row, h.ws_col, h.ws_xpix, h.ws_ypix };
				ioctl(slave, TIOCSWINSZ, &ws);
			} else { close(master); master = -1; ttymask = 0; }
		} else ttymask = 0;
	}

	const char *shell = (req_shell && req_shell[0]) ? req_shell : c->shell;
	uid_t tuid = h.target_uid;

	pid_t child = fork();
	if (child == 0) {
		close(s);
		if (master >= 0) close(master);
		child_exec(fds, ttymask, slave, tuid, shell, argv, envp, cwd);
		_exit(127);
	}
	/* parent handler */
	if (slave >= 0) close(slave);
	struct resp_hdr rp = { R_ALLOW, master >= 0 ? R_HASPTY : 0 };
	if (master >= 0) { send_fds(s, &rp, sizeof rp, &master, 1); close(master); }
	else send_fds(s, &rp, sizeof rp, NULL, 0);
	for (int i = 0; i < 3; i++) close(fds[i]);
	nfd = 0;
	free(argv); free(envp); free(item); free(body);

	int st = 0, code = 1;
	if (child > 0 && waitpid(child, &st, 0) > 0)
		code = WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
	int32_t out = code;
	write_all(s, &out, sizeof out);
	return;

deny_fds: {
	struct resp_hdr rp = { R_DENY, 0 };
	send_fds(s, &rp, sizeof rp, NULL, 0);
}
close_fds:
	for (int i = 0; i < nfd; i++) close(fds[i]);
}

/* --------------------------------------------------------------- daemonize */

static void write_pid(const struct dcfg *c) {
	char path[512]; dpath(path, sizeof path, c->dir, "daemon.pid");
	int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
	if (fd < 0) return;
	char b[32]; int n = snprintf(b, sizeof b, "%d\n", (int)getpid());
	if (write_all(fd, b, (size_t)n)) { /* ignore */ }
	close(fd);
}

static int read_pid(const char *dir) {
	char path[512]; dpath(path, sizeof path, dir, "daemon.pid");
	size_t l; char *b = read_file(path, &l);
	if (!b) return -1;
	int pid = atoi(b); free(b);
	return pid > 0 ? pid : -1;
}

static int daemon_running(const char *dir) {
	int pid = read_pid(dir);
	if (pid <= 0) return -1;
	if (kill(pid, 0) == 0 || errno == EPERM) return pid;
	return -1;
}

static int cmd_daemon(const struct dcfg *c) {
	mkdir(c->dir, 0700);

	int l = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (l < 0) die("socket: %s", strerror(errno));
	struct sockaddr_un a; socklen_t al = abstract_addr(&a, c->sock);
	if (bind(l, (struct sockaddr *)&a, al)) {
		if (errno == EADDRINUSE) { fprintf(stderr, "cpsu: socket @%s already in use\n", c->sock); exit(2); }
		die("bind: %s", strerror(errno));
	}
	if (listen(l, 128)) die("listen: %s", strerror(errno));

	if (!c->fg) {
		pid_t p = fork(); if (p < 0) die("fork"); if (p > 0) _exit(0);
		setsid();
		p = fork(); if (p > 0) _exit(0);
		int n = open("/dev/null", O_RDWR);
		if (n >= 0) { dup2(n, 0); dup2(n, 1); dup2(n, 2); if (n > 2) close(n); }
	}
	write_pid(c);

	struct sigaction sa = {0};
	sa.sa_handler = on_chld; sigemptyset(&sa.sa_mask);
	sa.sa_flags = SA_RESTART | SA_NOCLDSTOP;
	sigaction(SIGCHLD, &sa, NULL);
	sa.sa_handler = on_term; sa.sa_flags = 0;        /* no SA_RESTART: break accept */
	sigaction(SIGTERM, &sa, NULL); sigaction(SIGINT, &sa, NULL);
	signal(SIGPIPE, SIG_IGN);

	while (!g_stop) {
		int s = accept4(l, NULL, NULL, SOCK_CLOEXEC);
		if (s < 0) { if (errno == EINTR) continue; continue; }
		if (g_active >= MAX_CONC) { close(s); continue; }
		pid_t p = fork();
		if (p == 0) { close(l); serve(c, s); close(s); _exit(0); }
		if (p > 0) g_active++;
		close(s);
	}
	char path[512]; dpath(path, sizeof path, c->dir, "daemon.pid"); unlink(path);
	close(l);
	return 0;
}

static int cmd_stop(const struct dcfg *c) {
	int s = connect_sock(c->sock);
	if (s >= 0) {
		struct req_hdr ch; memset(&ch, 0, sizeof ch);
		memcpy(ch.magic, CTRL_MAGIC, 4); ch.target_uid = C_STOP;
		struct resp_hdr rp = {0};
		if (!send_fds(s, &ch, sizeof ch, NULL, 0)
		    && !read_all(s, &rp, sizeof rp) && rp.code == R_ALLOW) {
			close(s); puts("STOP_OK"); return 0;
		}
		close(s);
	}
	int pid = read_pid(c->dir);                       /* fallback */
	if (pid > 0 && kill(pid, SIGTERM) == 0) { puts("STOP_OK"); return 0; }
	puts("STOP_NONE"); return 3;
}

static int cmd_status(const struct dcfg *c) {
	int pid = daemon_running(c->dir);
	if (pid <= 0) { puts("STOPPED"); return 3; }
	const char *se = "none";
	size_t l; char *b = read_file("/sys/fs/selinux/enforce", &l);
	if (b) { se = (b[0] == '1') ? "Enforcing" : "Permissive"; free(b); }
	printf("RUNNING pid=%d version=%s selinux=%s\n", pid, CPSU_VERSION, se);
	return 0;
}

/* ------------------------------------------------------------------ client */

static const char *uid_name(uid_t u) {
	switch (u) { case 0: return "root"; case 2000: return "shell"; case 1000: return "system"; }
	return NULL;
}

/* raw-mode terminal state for restore */
static struct termios g_saved_tio;
static int g_raw = 0;
static void restore_tty(void) { if (g_raw) { tcsetattr(0, TCSANOW, &g_saved_tio); g_raw = 0; } }
static void raw_sig(int sig) { restore_tty(); signal(sig, SIG_DFL); raise(sig); }

static int g_master = -1;
static void on_winch(int sig) {
	(void)sig; struct winsize ws;
	if (g_master >= 0 && ioctl(0, TIOCGWINSZ, &ws) == 0) ioctl(g_master, TIOCSWINSZ, &ws);
}

/* append one string to a growing buffer */
struct buf { char *p; size_t len, cap; };
static void buf_put(struct buf *b, const char *s) {
	size_t k = strlen(s) + 1;
	while (b->len + k > b->cap) { b->cap = b->cap ? b->cap * 2 : 4096; b->p = realloc(b->p, b->cap); if (!b->p) die("oom"); }
	memcpy(b->p + b->len, s, k); b->len += k;
}

static void usage_su(void) {
	puts("usage: su [-c CMD] [-s SHELL] [-l|--login|-] [-p|--preserve-environment]\n"
	     "          [-mm|--mount-master] [-v|-V] [USER] [ARGS...]");
}

static int client_main(int argc, char **argv) {
	const char *command = NULL, *shellopt = NULL;
	int login = 0, preserve = 0;
	const char *user = NULL;
	char **extra = xmalloc(sizeof(char *) * (argc + 1)); int nextra = 0;

	int i = 1;
	for (; i < argc; i++) {
		const char *a = argv[i];
		if (!strcmp(a, "--")) { i++; break; }
		else if (!strcmp(a, "-c") || !strcmp(a, "--command")) { if (i + 1 < argc) command = argv[++i]; }
		else if (!strncmp(a, "--command=", 10)) command = a + 10;
		else if (!strcmp(a, "-s") || !strcmp(a, "--shell")) { if (i + 1 < argc) shellopt = argv[++i]; }
		else if (!strncmp(a, "--shell=", 8)) shellopt = a + 8;
		else if (!strcmp(a, "-l") || !strcmp(a, "--login") || !strcmp(a, "-")) login = 1;
		else if (!strcmp(a, "-p") || !strcmp(a, "-m") || !strcmp(a, "--preserve-environment")) preserve = 1;
		else if (!strcmp(a, "-mm") || !strcmp(a, "-M") || !strcmp(a, "--mount-master")) { /* no-op */ }
		else if (!strcmp(a, "-v") || !strcmp(a, "--version")) { puts(CPSU_VERSION); return 0; }
		else if (!strcmp(a, "-V")) { puts(CPSU_VCODE); return 0; }
		else if (!strcmp(a, "-h") || !strcmp(a, "--help")) { usage_su(); return 0; }
		else if (!strcmp(a, "-Z") || !strcmp(a, "--context") || !strcmp(a, "-t") || !strcmp(a, "--target")) { if (i + 1 < argc) i++; }
		else if (a[0] == '-' && a[1]) { /* unknown flag: ignore (Magisk-lenient) */ }
		else { if (!user) user = a; else extra[nextra++] = (char *)a; }
	}
	for (; i < argc; i++) { if (!user) user = argv[i]; else extra[nextra++] = argv[i]; }
	extra[nextra] = NULL;

	/* resolve target uid */
	uid_t target = 0;
	if (user) {
		if (!strcmp(user, "root")) target = 0;
		else if (!strcmp(user, "shell")) target = 2000;
		else if (!strcmp(user, "system")) target = 1000;
		else if (isdigit((unsigned char)user[0])) target = (uid_t)atoi(user);
		else target = 0;                 /* unknown name -> root (Android has no passwd DB) */
	}

	const char *reqshell = shellopt ? shellopt : "";
	const char *dispshell = shellopt ? shellopt : DEF_SHELL;
	const char *base = strrchr(dispshell, '/'); base = base ? base + 1 : dispshell;

	/* build argv for the shell */
	struct buf args = {0}; uint32_t n_args = 0;
	char arg0[256];
	if (login) snprintf(arg0, sizeof arg0, "-%s", base);
	else snprintf(arg0, sizeof arg0, "%s", base);
	buf_put(&args, arg0); n_args++;
	if (command) { buf_put(&args, "-c"); buf_put(&args, command); n_args += 2; }
	for (int k = 0; k < nextra; k++) { buf_put(&args, extra[k]); n_args++; }

	/* cwd */
	char cwd[4096];
	if (login || !getcwd(cwd, sizeof cwd)) strcpy(cwd, "/");

	/* environment: apply client-side rules, build env blob */
	extern char **environ;
	struct buf env = {0}; uint32_t n_env = 0;
	const char *tname = uid_name(target);
	char tnamebuf[32];
	if (!tname) { snprintf(tnamebuf, sizeof tnamebuf, "%u", (unsigned)target); tname = tnamebuf; }
	int have_path = 0, path_has_sysbin = 0;
	for (char **e = environ; *e; e++) {
		if (!preserve && (!strncmp(*e, "USER=", 5) || !strncmp(*e, "LOGNAME=", 8) || !strncmp(*e, "SHELL=", 6)))
			continue;                                       /* re-added below */
		if (!strncmp(*e, "PATH=", 5)) { have_path = 1; if (strstr(*e + 5, "/system/bin")) path_has_sysbin = 1; }
		buf_put(&env, *e); n_env++;
	}
	if (!preserve) {
		char tmp[512];
		snprintf(tmp, sizeof tmp, "USER=%s", tname); buf_put(&env, tmp); n_env++;
		snprintf(tmp, sizeof tmp, "LOGNAME=%s", tname); buf_put(&env, tmp); n_env++;
		snprintf(tmp, sizeof tmp, "SHELL=%s", dispshell); buf_put(&env, tmp); n_env++;
	}
	if (!have_path) { buf_put(&env, "PATH=/system/bin:/system/xbin:/vendor/bin"); n_env++; }
	else if (!path_has_sysbin) {
		/* rebuild PATH with /system/bin appended */
		struct buf e2 = {0}; uint32_t n2 = 0;
		char *bp = env.p; char *bend = env.p + env.len;
		while (bp < bend) {
			if (!strncmp(bp, "PATH=", 5)) { char t[8192]; snprintf(t, sizeof t, "%s:/system/bin", bp); buf_put(&e2, t); }
			else buf_put(&e2, bp);
			n2++; bp += strlen(bp) + 1;
		}
		free(env.p); env = e2; n_env = n2;
	}

	const char *sockname = getenv("CPSU_SOCK"); if (!sockname) sockname = DEF_SOCK;

	/* getuid()==0 shortcut: exec locally, keep adb root working if daemon down */
	if (getuid() == 0) {
		char **cav = xmalloc(sizeof(char *) * (n_args + 1));
		char *bp = args.p; for (uint32_t k = 0; k < n_args; k++) { cav[k] = bp; bp += strlen(bp) + 1; }
		cav[n_args] = NULL;
		char **cev = xmalloc(sizeof(char *) * (n_env + 1));
		bp = env.p; for (uint32_t k = 0; k < n_env; k++) { cev[k] = bp; bp += strlen(bp) + 1; }
		cev[n_env] = NULL;
		if (chdir(cwd) != 0) { if (chdir("/") != 0) {} }
		if (target != 0) { gid_t g = target; if (setgroups(1, &g) || setresgid(g, g, g) || setresuid(target, target, target)) die("su: drop privs failed"); }
		execve(dispshell, cav, cev);
		die("su: exec %s: %s", dispshell, strerror(errno));
	}

	int s = connect_sock(sockname);
	if (s < 0) { fprintf(stderr, "su: root ch\u01b0a b\u1eadt / daemon kh\u00f4ng ch\u1ea1y (CloudBlue: C\u00f4ng c\u1ee5 \u2192 \U0001f513 Root)\n"); return 1; }

	/* flags + window size */
	uint32_t flags = 0;
	if (isatty(0)) flags |= F_STDIN_TTY;
	if (isatty(1)) flags |= F_STDOUT_TTY;
	if (isatty(2)) flags |= F_STDERR_TTY;
	if (login) flags |= F_LOGIN;
	if (preserve) flags |= F_PRESERVE;
	struct winsize ws = {0};
	for (int f = 0; f < 3; f++) if ((flags & (1 << f)) && ioctl(f, TIOCGWINSZ, &ws) == 0) break;

	struct req_hdr h; memcpy(h.magic, PROTO_MAGIC, 4);
	h.version = PROTO_VERSION; h.target_uid = target; h.flags = flags;
	h.ws_row = ws.ws_row; h.ws_col = ws.ws_col; h.ws_xpix = ws.ws_xpixel; h.ws_ypix = ws.ws_ypixel;
	h.n_args = n_args; h.n_env = n_env;

	/* body = shell\0 cwd\0 args env */
	struct buf body = {0};
	buf_put(&body, reqshell); buf_put(&body, cwd);
	/* append args blob then env blob */
	{ char *bp = args.p; for (uint32_t k = 0; k < n_args; k++) { buf_put(&body, bp); bp += strlen(bp) + 1; } }
	{ char *bp = env.p; for (uint32_t k = 0; k < n_env; k++) { buf_put(&body, bp); bp += strlen(bp) + 1; } }
	h.body_len = body.len;

	int stdfds[3] = { dup(0), dup(1), dup(2) };
	if (send_fds(s, &h, sizeof h, stdfds, 3) || write_all(s, body.p, body.len)) {
		fprintf(stderr, "su: send failed\n"); return 1;
	}
	for (int k = 0; k < 3; k++) close(stdfds[k]);

	struct resp_hdr rp; int mfds[1], mn = 0;
	if (recv_fds(s, &rp, sizeof rp, mfds, &mn, 1)) { fprintf(stderr, "su: no response\n"); return 1; }
	if (rp.code == R_DENY) {
		fprintf(stderr, "su: app n\u00e0y ch\u01b0a \u0111\u01b0\u1ee3c c\u1ea5p quy\u1ec1n root \u2014 b\u1eadt trong CloudBlue: C\u00f4ng c\u1ee5 \u2192 \U0001f513 Root\n");
		return 1;
	}
	if (rp.code != R_ALLOW) { fprintf(stderr, "su: error\n"); return 1; }

	if (!(rp.flags & R_HASPTY) || mn < 1) {
		/* no pty: child uses our real std fds; just wait for status */
		if (mn > 0) close(mfds[0]);
		int32_t st; if (read_all(s, &st, sizeof st)) return 1;
		return (int)st;
	}

	/* pty session */
	int master = mfds[0]; g_master = master;
	if (isatty(0)) {
		if (tcgetattr(0, &g_saved_tio) == 0) {
			struct termios raw = g_saved_tio;
			cfmakeraw(&raw);
			tcsetattr(0, TCSANOW, &raw); g_raw = 1;
			atexit(restore_tty);
			struct sigaction sa = {0}; sa.sa_handler = raw_sig; sigemptyset(&sa.sa_mask);
			sigaction(SIGHUP, &sa, NULL); sigaction(SIGTERM, &sa, NULL); sigaction(SIGQUIT, &sa, NULL);
		}
	}
	struct sigaction sw = {0}; sw.sa_handler = on_winch; sigemptyset(&sw.sa_mask); sw.sa_flags = SA_RESTART;
	sigaction(SIGWINCH, &sw, NULL);
	on_winch(0);                               /* push initial size */
	signal(SIGPIPE, SIG_IGN);

	int out_fd = isatty(1) ? 1 : (isatty(2) ? 2 : -1);
	int32_t status = 0; int have_status = 0, stdin_open = isatty(0) || 1;
	char buf[8192];
	for (;;) {
		struct pollfd pf[3]; int np = 0;
		int imaster = -1, isock = -1, istdin = -1;
		pf[np].fd = master; pf[np].events = POLLIN; imaster = np++;
		pf[np].fd = s; pf[np].events = POLLIN; isock = np++;
		if (stdin_open) { pf[np].fd = 0; pf[np].events = POLLIN; istdin = np++; }
		int r = poll(pf, np, -1);
		if (r < 0) { if (errno == EINTR) continue; break; }
		if (istdin >= 0 && (pf[istdin].revents & (POLLIN | POLLHUP))) {
			ssize_t k = read(0, buf, sizeof buf);
			if (k > 0) write_all(master, buf, (size_t)k);
			else { stdin_open = 0; }         /* stop watching stdin */
		}
		if (pf[imaster].revents & (POLLIN | POLLHUP)) {
			ssize_t k = read(master, buf, sizeof buf);
			if (k > 0) { if (out_fd >= 0) write_all(out_fd, buf, (size_t)k); }
			else if (k == 0 || errno != EINTR) { /* EIO/EOF: child gone */
				if (have_status) break;
			}
		}
		if (pf[isock].revents & (POLLIN | POLLHUP)) {
			if (!read_all(s, &status, sizeof status)) { have_status = 1; }
			/* drain remaining pty output briefly */
			struct pollfd dp = { master, POLLIN, 0 };
			while (poll(&dp, 1, 50) > 0 && (dp.revents & POLLIN)) {
				ssize_t k = read(master, buf, sizeof buf);
				if (k <= 0) break;
				if (out_fd >= 0) write_all(out_fd, buf, (size_t)k);
			}
			break;
		}
	}
	restore_tty();
	return have_status ? (int)status : 1;
}

/* ----------------------------------------------------------- install logic */

static int is_mountpoint(const char *path) {
	struct stat a, b; char parent[1024];
	if (lstat(path, &a)) return 0;
	snprintf(parent, sizeof parent, "%s/..", path);
	if (lstat(parent, &b)) return 0;
	return a.st_dev != b.st_dev || a.st_ino == b.st_ino;
}

static int copy_file(const char *src, const char *dst, mode_t mode) {
	int in = open(src, O_RDONLY | O_CLOEXEC); if (in < 0) return -1;
	int out = open(dst, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, mode);
	if (out < 0) { close(in); return -1; }
	char b[65536]; ssize_t k;
	while ((k = read(in, b, sizeof b)) > 0) if (write_all(out, b, (size_t)k)) { k = -1; break; }
	close(in); fchmod(out, mode); close(out);
	return k < 0 ? -1 : 0;
}

static void record_mount(const char *dir, const char *what) {
	char path[512]; dpath(path, sizeof path, dir, "mounts");
	int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
	if (fd < 0) return;
	write_all(fd, what, strlen(what)); write_all(fd, "\n", 1);
	close(fd);
}

static int cmd_install(const struct dcfg *c, const char *ramdisk, const char *src,
                       char **binds, int nbind) {
	mkdir(c->dir, 0700);
	struct stat st;
	int mounted_tmpfs = 0;
	if (!stat(ramdisk, &st) && S_ISDIR(st.st_mode) && !is_mountpoint(ramdisk)) {
		if (mount("tmpfs", ramdisk, "tmpfs", 0, "mode=0755") == 0) {
			char rec[1100]; snprintf(rec, sizeof rec, "tmpfs %s", ramdisk);
			mounted_tmpfs = 1; record_mount(c->dir, rec);
		} else if (errno == EPERM || errno == EACCES) {
			fprintf(stderr, "cpsu: warn: tmpfs mount not permitted (%s); using dir as-is\n", strerror(errno));
		}
	}
	char subin[1024]; snprintf(subin, sizeof subin, "%s/su", ramdisk);
	char subtmp[1100]; snprintf(subtmp, sizeof subtmp, "%s/.su.new", ramdisk);
	/* default client = DIR/su (libc-free cpsu-su build) — never the glibc multi-call binary on a device */
	char defsrc[600];
	if (!src) { dpath(defsrc, sizeof defsrc, c->dir, "su"); src = access(defsrc, X_OK) == 0 ? defsrc : "/proc/self/exe"; }
	/* temp + rename: a running su keeps its old inode (no ETXTBSY) */
	if (copy_file(src, subtmp, 0755) || rename(subtmp, subin)) {
		printf("INSTALL_FAIL copy %s\n", strerror(errno)); unlink(subtmp); return 1;
	}

	/* already bound by an earlier install (recorded in DIR/mounts) -> don't stack another bind */
	char mpath[512]; dpath(mpath, sizeof mpath, c->dir, "mounts");
	size_t mlen = 0; char *mrec = read_file(mpath, &mlen);
	for (int i = 0; i < nbind; i++) {
		char want[1100]; snprintf(want, sizeof want, "bind %s\n", binds[i]);
		if (mrec && strstr(mrec, want)) continue;
		if (!stat(binds[i], &st) && S_ISREG(st.st_mode)) {
			if (mount(subin, binds[i], NULL, MS_BIND, NULL) == 0) {
				char rec[1100]; snprintf(rec, sizeof rec, "bind %s", binds[i]); record_mount(c->dir, rec);
			} else {
				fprintf(stderr, "cpsu: warn: bind %s: %s\n", binds[i], strerror(errno));
			}
		}
	}

	free(mrec);
	int sk = connect_sock(c->sock);
	if (sk >= 0) close(sk);
	if (daemon_running(c->dir) <= 0 || sk < 0) {
		pid_t p = fork();
		if (p == 0) {
			char dirbuf[512]; snprintf(dirbuf, sizeof dirbuf, "%s", c->dir);
			if (c->notify)
				execl("/proc/self/exe", "cpsu", "daemon", "--dir", dirbuf, "--sock", c->sock,
				      "--pkgs", c->pkgs, "--shell", c->shell, "--notify", (char *)NULL);
			else
				execl("/proc/self/exe", "cpsu", "daemon", "--dir", dirbuf, "--sock", c->sock,
				      "--pkgs", c->pkgs, "--shell", c->shell, (char *)NULL);
			_exit(127);
		}
		if (p > 0) { int ms = 0; while (daemon_running(c->dir) <= 0 && ms < 2000) { usleep(20000); ms += 20; } }
	}
	printf("INSTALL_OK ramdisk=%s tmpfs=%d su=%s\n", ramdisk, mounted_tmpfs, subin);
	return 0;
}

static int cmd_uninstall(const struct dcfg *c) {
	cmd_stop(c);
	char path[512]; dpath(path, sizeof path, c->dir, "mounts");
	size_t l; char *b = read_file(path, &l);
	if (b) {
		char *lines[256]; int nl = 0;
		char *save, *ln = strtok_r(b, "\n", &save);
		while (ln && nl < 256) { lines[nl++] = ln; ln = strtok_r(NULL, "\n", &save); }
		/* binds first (reverse), then the tmpfs they sat on */
		for (int i = nl - 1; i >= 0; i--)
			if (!strncmp(lines[i], "bind ", 5)) umount2(lines[i] + 5, MNT_DETACH);
		for (int i = nl - 1; i >= 0; i--)
			if (!strncmp(lines[i], "tmpfs ", 6)) umount2(lines[i] + 6, MNT_DETACH);
		free(b);
		unlink(path);
	}
	puts("UNINSTALL_OK");
	return 0;
}

/* -------------------------------------------------------------------- main */

static void parse_common(int argc, char **argv, int start, struct dcfg *c,
                         const char **ramdisk, const char **src,
                         char ***binds, int *nbind) {
	for (int i = start; i < argc; i++) {
		const char *a = argv[i];
		if (!strcmp(a, "--fg")) c->fg = 1;
		else if (!strcmp(a, "--notify")) c->notify = 1;
		else if (!strcmp(a, "--sock") && i + 1 < argc) c->sock = argv[++i];
		else if (!strcmp(a, "--dir") && i + 1 < argc) c->dir = argv[++i];
		else if ((!strcmp(a, "--packages") || !strcmp(a, "--pkgs")) && i + 1 < argc) c->pkgs = argv[++i];
		else if (!strcmp(a, "--shell") && i + 1 < argc) c->shell = argv[++i];
		else if (!strcmp(a, "--notify-cmd") && i + 1 < argc) c->notify_cmd = argv[++i];
		else if (!strcmp(a, "--ramdisk") && i + 1 < argc && ramdisk) *ramdisk = argv[++i];
		else if (!strcmp(a, "--src") && i + 1 < argc && src) *src = argv[++i];
		else if (!strcmp(a, "--bind") && i + 1 < argc && binds) {
			char *list = strdup(argv[++i]); char *save, *tok = strtok_r(list, ",", &save);
			while (tok && *nbind < 64) { (*binds)[(*nbind)++] = strdup(tok); tok = strtok_r(NULL, ",", &save); }
			free(list);
		}
	}
}

int main(int argc, char **argv) {
	signal(SIGPIPE, SIG_IGN);
	const char *b0 = strrchr(argv[0], '/'); b0 = b0 ? b0 + 1 : argv[0];
	if (!strcmp(b0, "su")) return client_main(argc, argv);

	if (argc < 2) { fprintf(stderr, "usage: cpsu daemon|stop|status|install|uninstall|version\n"); return 1; }
	const char *cmd = argv[1];

	struct dcfg c = { DEF_SOCK, DEF_DIR, DEF_PKGS, DEF_SHELL, DEF_NOTIFY_CMD, 0, 0 };
	const char *ramdisk = DEF_RAMDISK, *src = NULL;
	char **binds = xmalloc(sizeof(char *) * 64); int nbind = 0;

	if (!strcmp(cmd, "version") || !strcmp(cmd, "-v") || !strcmp(cmd, "--version")) { puts(CPSU_VERSION); return 0; }
	if (!strcmp(cmd, "su")) return client_main(argc - 1, argv + 1);

	parse_common(argc, argv, 2, &c, &ramdisk, &src, &binds, &nbind);

	if (!strcmp(cmd, "daemon"))    return cmd_daemon(&c);
	if (!strcmp(cmd, "stop"))      return cmd_stop(&c);
	if (!strcmp(cmd, "status"))    return cmd_status(&c);
	if (!strcmp(cmd, "install"))   return cmd_install(&c, ramdisk, src, binds, nbind);
	if (!strcmp(cmd, "uninstall")) return cmd_uninstall(&c);

	fprintf(stderr, "cpsu: unknown command '%s'\n", cmd);
	return 1;
}
