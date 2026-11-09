/* cpsu-su.c — client "su" của cpsu, KHÔNG dùng libc (x86_64 Linux / Android).
 *
 * Vì sao không dùng libc: "su" chạy BÊN TRONG tiến trình app Android (Termux…), dưới bộ lọc seccomp của app.
 * Mã khởi động của glibc tĩnh gọi rseq / set_robust_list… — app seccomp có thể giết tiến trình bằng SIGSYS
 * trước cả main(). Bản này chỉ gọi đúng các syscall liệt kê ở SYSCALLS dưới đây (đều là syscall bionic dùng).
 *
 * Giao thức: giống hệt client trong cpsu.c (struct req_hdr / resp_hdr, magic "CPS1", version 1).
 * Build: gcc -O2 -static -nostdlib -ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns \
 *            -fno-stack-protector -no-pie -fno-asynchronous-unwind-tables -o cpsu-su-x86_64 cpsu-su.c
 *
 * SYSCALLS: read write close ioctl rt_sigaction rt_sigreturn dup socket connect sendmsg recvmsg ppoll
 *           getcwd getuid exit_group  (+ chỉ khi đã là root: chdir setgroups setresgid setresuid execve)
 */

typedef unsigned long size_t;
typedef long ssize_t;
typedef unsigned int u32;
typedef unsigned short u16;

/* ------------------------------------------------------------------ syscall */
#define SYS_read 0
#define SYS_write 1
#define SYS_close 3
#define SYS_rt_sigaction 13
#define SYS_ioctl 16
#define SYS_dup 32
#define SYS_socket 41
#define SYS_connect 42
#define SYS_sendmsg 46
#define SYS_recvmsg 47
#define SYS_execve 59
#define SYS_getcwd 79
#define SYS_chdir 80
#define SYS_getuid 102
#define SYS_setgroups 116
#define SYS_setresuid 117
#define SYS_setresgid 119
#define SYS_exit_group 231
#define SYS_ppoll 271

static long sc6(long n, long a1, long a2, long a3, long a4, long a5, long a6) {
	register long r10 __asm__("r10") = a4;
	register long r8 __asm__("r8") = a5;
	register long r9 __asm__("r9") = a6;
	long ret;
	__asm__ volatile ("syscall"
	                  : "=a"(ret)
	                  : "a"(n), "D"(a1), "S"(a2), "d"(a3), "r"(r10), "r"(r8), "r"(r9)
	                  : "rcx", "r11", "memory");
	return ret;
}
#define sc0(n)             sc6(n, 0, 0, 0, 0, 0, 0)
#define sc1(n, a)          sc6(n, (long)(a), 0, 0, 0, 0, 0)
#define sc2(n, a, b)       sc6(n, (long)(a), (long)(b), 0, 0, 0, 0)
#define sc3(n, a, b, c)    sc6(n, (long)(a), (long)(b), (long)(c), 0, 0, 0)
#define sc4(n, a, b, c, d) sc6(n, (long)(a), (long)(b), (long)(c), (long)(d), 0, 0)
#define sc5(n, a, b, c, d, e) sc6(n, (long)(a), (long)(b), (long)(c), (long)(d), (long)(e), 0)

#define EINTR 4
#define EAGAIN 11

__attribute__((noreturn)) static void sys_exit(int code) {
	for (;;) sc1(SYS_exit_group, code);
}

/* điểm vào: căn ngăn xếp 16 byte rồi gọi cstart(sp) */
__asm__(
	".text\n"
	".global _start\n"
	"_start:\n"
	"  xor %rbp, %rbp\n"
	"  mov %rsp, %rdi\n"
	"  and $-16, %rsp\n"
	"  call cstart\n"
	"  hlt\n"
	".global cp_restore_rt\n"
	"cp_restore_rt:\n"
	"  mov $15, %rax\n"          /* rt_sigreturn */
	"  syscall\n"
	"  hlt\n");
void cp_restore_rt(void);

/* gcc có thể tự sinh lời gọi memcpy/memset/memmove/memcmp ngay cả khi -ffreestanding */
void *memcpy(void *d, const void *s, size_t n) { char *a = d; const char *b = s; while (n--) *a++ = *b++; return d; }
void *memmove(void *d, const void *s, size_t n) {
	char *a = d; const char *b = s;
	if (a < b) while (n--) *a++ = *b++; else { a += n; b += n; while (n--) *--a = *--b; }
	return d;
}
void *memset(void *d, int c, size_t n) { char *a = d; while (n--) *a++ = (char)c; return d; }
int memcmp(const void *x, const void *y, size_t n) {
	const unsigned char *a = x, *b = y;
	for (; n; n--, a++, b++) if (*a != *b) return *a - *b;
	return 0;
}

static size_t slen(const char *s) { size_t n = 0; while (s[n]) n++; return n; }
static int seq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static int spre(const char *s, const char *p) { while (*p) if (*s++ != *p++) return 0; return 1; }
static int shas(const char *h, const char *n) {          /* = strstr(h, n) != 0 */
	size_t ln = slen(n), lh = slen(h);
	for (size_t i = 0; i + ln <= lh; i++) if (!memcmp(h + i, n, ln)) return 1;
	return 0;
}

static int write_all(int fd, const void *b, size_t n) {
	const char *p = b;
	while (n) {
		long k = sc3(SYS_write, fd, p, n);
		if (k == -EINTR || k == -EAGAIN) continue;
		if (k <= 0) return -1;
		p += k; n -= (size_t)k;
	}
	return 0;
}
static int read_all(int fd, void *b, size_t n) {
	char *p = b;
	while (n) {
		long k = sc3(SYS_read, fd, p, n);
		if (k == -EINTR) continue;
		if (k <= 0) return -1;
		p += k; n -= (size_t)k;
	}
	return 0;
}
static void eput(const char *s) { write_all(2, s, slen(s)); }
static void oput(const char *s) { write_all(1, s, slen(s)); }

/* ------------------------------------------------------------- terminal */
#define TCGETS 0x5401
#define TCSETS 0x5402
#define TIOCGWINSZ 0x5413
#define TIOCSWINSZ 0x5414
struct ktermios { u32 c_iflag, c_oflag, c_cflag, c_lflag; unsigned char c_line; unsigned char c_cc[19]; };
struct kwinsize { u16 row, col, xpix, ypix; };

static int is_tty(int fd) { struct ktermios t; return sc3(SYS_ioctl, fd, TCGETS, &t) == 0; }

static struct ktermios g_saved;
static volatile int g_raw = 0;
static volatile int g_master = -1;

static void restore_tty(void) {
	if (g_raw) { sc3(SYS_ioctl, 0, TCSETS, &g_saved); g_raw = 0; }
}
static void make_raw(struct ktermios *t) {      /* = cfmakeraw() */
	t->c_iflag &= ~(0000001u | 0000002u | 0000010u | 0000040u | 0000100u | 0000200u | 0000400u | 0002000u);
	t->c_oflag &= ~0000001u;
	t->c_lflag &= ~(0000010u | 0000100u | 0000002u | 0000001u | 0100000u);
	t->c_cflag &= ~(0000060u | 0000400u);
	t->c_cflag |= 0000060u;
	t->c_cc[6] = 1;   /* VMIN */
	t->c_cc[5] = 0;   /* VTIME */
}

/* ------------------------------------------------------------- signals */
#define SIGHUP 1
#define SIGINT 2
#define SIGQUIT 3
#define SIGPIPE 13
#define SIGTERM 15
#define SIGWINCH 28
#define SA_RESTART 0x10000000ul
#define SA_RESTORER 0x04000000ul
struct ksigaction { void (*handler)(int); unsigned long flags; void (*restorer)(void); unsigned long mask; };

static void set_sig(int sig, void (*h)(int), unsigned long flags) {
	struct ksigaction a;
	a.handler = h; a.flags = flags | SA_RESTORER; a.restorer = cp_restore_rt; a.mask = 0;
	sc4(SYS_rt_sigaction, sig, &a, 0, 8);
}
static void on_fatal(int sig) { restore_tty(); sys_exit(128 + sig); }
static void on_winch(int sig) {
	(void)sig; struct kwinsize ws;
	if (g_master >= 0 && sc3(SYS_ioctl, 0, TIOCGWINSZ, &ws) == 0) sc3(SYS_ioctl, g_master, TIOCSWINSZ, &ws);
}

/* ------------------------------------------------------------- socket */
struct iovec_ { void *base; size_t len; };
struct msghdr_ {
	void *name; u32 namelen; u32 pad0;
	struct iovec_ *iov; size_t iovlen;
	void *control; size_t controllen;
	int flags; int pad1;
};
struct cmsg3 { size_t len; int level; int type; int fds[4]; };   /* đủ chỗ cho 3–4 fd */
#define SOL_SOCKET 1
#define SCM_RIGHTS 1
#define MSG_NOSIGNAL 0x4000
#define CMSG_HDR 16                      /* sizeof(struct cmsghdr) trên x86_64 */

static int send_with_fds(int s, const void *data, size_t len, const int *fds, int nfd) {
	struct iovec_ io; io.base = (void *)data; io.len = len;
	struct cmsg3 cm; memset(&cm, 0, sizeof cm);
	struct msghdr_ m; memset(&m, 0, sizeof m);
	m.iov = &io; m.iovlen = 1;
	if (nfd > 0) {
		cm.len = CMSG_HDR + sizeof(int) * (size_t)nfd; cm.level = SOL_SOCKET; cm.type = SCM_RIGHTS;
		for (int i = 0; i < nfd; i++) cm.fds[i] = fds[i];
		m.control = &cm; m.controllen = cm.len;
	}
	for (;;) {
		long k = sc3(SYS_sendmsg, s, &m, MSG_NOSIGNAL);
		if (k == -EINTR) continue;
		return (k == (long)len) ? 0 : -1;
	}
}
/* nhận đúng len byte; lấy tối đa 1 fd đi kèm */
static int recv_with_fd(int s, void *data, size_t len, int *fd) {
	struct iovec_ io; io.base = data; io.len = len;
	struct cmsg3 cm; memset(&cm, 0, sizeof cm);
	struct msghdr_ m; memset(&m, 0, sizeof m);
	m.iov = &io; m.iovlen = 1; m.control = &cm; m.controllen = sizeof cm;
	long k;
	for (;;) { k = sc3(SYS_recvmsg, s, &m, 0); if (k == -EINTR) continue; break; }
	if (k <= 0) return -1;
	*fd = -1;
	if (m.controllen >= CMSG_HDR + sizeof(int) && cm.level == SOL_SOCKET && cm.type == SCM_RIGHTS) {
		int n = (int)((cm.len - CMSG_HDR) / sizeof(int));
		for (int i = 0; i < n && i < 4; i++) { if (*fd < 0) *fd = cm.fds[i]; else sc1(SYS_close, cm.fds[i]); }
	}
	if ((size_t)k < len) return read_all(s, (char *)data + k, len - (size_t)k);
	return 0;
}

/* ------------------------------------------------------------- giao thức (giống cpsu.c) */
#define CPSU_VERSION "2.0:CPSU"
#define CPSU_VCODE "200"
#define DEF_SOCK "cpsu"
#define DEF_SHELL "/system/bin/sh"
#define MAX_BODY (256 * 1024)
#define MAX_ITEMS 4096
#define F_STDIN_TTY 1
#define F_STDOUT_TTY 2
#define F_STDERR_TTY 4
#define F_LOGIN 8
#define F_PRESERVE 16
#define R_ALLOW 1
#define R_DENY 2
#define R_HASPTY 1

struct req_hdr {
	char magic[4]; u32 version; u32 target_uid; u32 flags;
	u16 ws_row, ws_col, ws_xpix, ws_ypix;
	u32 n_args, n_env, body_len;
};
struct resp_hdr { u32 code; u32 flags; };

/* bộ đệm tĩnh (không có malloc) */
static char g_args[MAX_BODY];  static size_t g_args_len;  static u32 g_nargs;
static char g_env[MAX_BODY];   static size_t g_env_len;   static u32 g_nenv;
static char g_body[MAX_BODY];  static size_t g_body_len;
static char *g_av[MAX_ITEMS + 2], *g_ev[MAX_ITEMS + 2];
static char g_io[8192];

static void too_big(void) { eput("su: lệnh / biến môi trường quá dài\n"); sys_exit(1); }
static void put(char *buf, size_t *len, const char *s) {
	size_t k = slen(s) + 1;
	if (*len + k > MAX_BODY) too_big();
	memcpy(buf + *len, s, k); *len += k;
}
static void put2(char *buf, size_t *len, const char *a, const char *b) {   /* a + b + NUL */
	size_t ka = slen(a), kb = slen(b);
	if (*len + ka + kb + 1 > MAX_BODY) too_big();
	memcpy(buf + *len, a, ka); memcpy(buf + *len + ka, b, kb); buf[*len + ka + kb] = 0; *len += ka + kb + 1;
}
static void add_arg(const char *s) { if (g_nargs >= MAX_ITEMS) too_big(); put(g_args, &g_args_len, s); g_nargs++; }
static void add_env(const char *s) { if (g_nenv >= MAX_ITEMS) too_big(); put(g_env, &g_env_len, s); g_nenv++; }
static void add_env2(const char *a, const char *b) { if (g_nenv >= MAX_ITEMS) too_big(); put2(g_env, &g_env_len, a, b); g_nenv++; }

static const char *getenv_(char **envp, const char *name) {
	size_t n = slen(name);
	for (char **e = envp; *e; e++) if (!memcmp(*e, name, n) && (*e)[n] == '=') return *e + n + 1;
	return 0;
}
static u32 atou(const char *s) { u32 v = 0; while (*s >= '0' && *s <= '9') v = v * 10 + (u32)(*s++ - '0'); return v; }
static void utoa_(u32 v, char *out) {
	char t[16]; int n = 0;
	do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
	for (int i = 0; i < n; i++) out[i] = t[n - 1 - i];
	out[n] = 0;
}
static void split(char *blob, u32 n, char **out) {
	for (u32 i = 0; i < n; i++) { out[i] = blob; blob += slen(blob) + 1; }
	out[n] = 0;
}

static void usage(void) {
	oput("usage: su [-c CMD] [-s SHELL] [-l|--login|-] [-p|--preserve-environment]\n"
	     "          [-mm|--mount-master] [-v|-V] [USER] [ARGS...]\n");
}

int cstart(long *sp);
int cstart(long *sp) {
	int argc = (int)sp[0];
	char **argv = (char **)(sp + 1);
	char **envp = argv + argc + 1;

	const char *command = 0, *shellopt = 0, *user = 0;
	int login = 0, preserve = 0, i = 1;
	static char *extra[MAX_ITEMS + 1]; int nextra = 0;

	for (; i < argc; i++) {
		const char *a = argv[i];
		if (seq(a, "--")) { i++; break; }
		else if (seq(a, "-c") || seq(a, "--command")) { if (i + 1 < argc) command = argv[++i]; }
		else if (spre(a, "--command=")) command = a + 10;
		else if (seq(a, "-s") || seq(a, "--shell")) { if (i + 1 < argc) shellopt = argv[++i]; }
		else if (spre(a, "--shell=")) shellopt = a + 8;
		else if (seq(a, "-l") || seq(a, "--login") || seq(a, "-")) login = 1;
		else if (seq(a, "-p") || seq(a, "-m") || seq(a, "--preserve-environment")) preserve = 1;
		else if (seq(a, "-mm") || seq(a, "-M") || seq(a, "--mount-master")) { /* không cần */ }
		else if (seq(a, "-v") || seq(a, "--version")) { oput(CPSU_VERSION "\n"); sys_exit(0); }
		else if (seq(a, "-V")) { oput(CPSU_VCODE "\n"); sys_exit(0); }
		else if (seq(a, "-h") || seq(a, "--help")) { usage(); sys_exit(0); }
		else if (seq(a, "-Z") || seq(a, "--context") || seq(a, "-t") || seq(a, "--target")) { if (i + 1 < argc) i++; }
		else if (a[0] == '-' && a[1]) { /* cờ lạ: bỏ qua như Magisk */ }
		else { if (!user) user = a; else if (nextra < MAX_ITEMS) extra[nextra++] = (char *)a; }
	}
	for (; i < argc; i++) { if (!user) user = argv[i]; else if (nextra < MAX_ITEMS) extra[nextra++] = argv[i]; }

	u32 target = 0;
	if (user) {
		if (seq(user, "root")) target = 0;
		else if (seq(user, "shell")) target = 2000;
		else if (seq(user, "system")) target = 1000;
		else if (user[0] >= '0' && user[0] <= '9') target = atou(user);
	}
	const char *tname = target == 0 ? "root" : target == 2000 ? "shell" : target == 1000 ? "system" : 0;
	char tnum[16];
	if (!tname) { utoa_(target, tnum); tname = tnum; }

	const char *reqshell = shellopt ? shellopt : "";
	const char *dispshell = shellopt ? shellopt : DEF_SHELL;
	const char *base = dispshell;
	for (const char *p = dispshell; *p; p++) if (*p == '/') base = p + 1;

	/* argv của shell */
	if (login) { if (g_nargs >= MAX_ITEMS) too_big(); put2(g_args, &g_args_len, "-", base); g_nargs++; }
	else add_arg(base);
	if (command) { add_arg("-c"); add_arg(command); }
	for (int k = 0; k < nextra; k++) add_arg(extra[k]);

	/* thư mục hiện tại */
	static char cwd[4096];
	if (login || sc2(SYS_getcwd, cwd, sizeof cwd) <= 0) { cwd[0] = '/'; cwd[1] = 0; }

	/* môi trường: như cpsu.c — bỏ USER/LOGNAME/SHELL (trừ -p) rồi thêm lại; PATH luôn có /system/bin */
	int have_path = 0;
	for (char **e = envp; *e; e++) {
		if (!preserve && (spre(*e, "USER=") || spre(*e, "LOGNAME=") || spre(*e, "SHELL="))) continue;
		if (spre(*e, "PATH=")) {
			have_path = 1;
			if (!shas(*e + 5, "/system/bin")) { add_env2(*e, ":/system/bin"); continue; }
		}
		add_env(*e);
	}
	if (!preserve) { add_env2("USER=", tname); add_env2("LOGNAME=", tname); add_env2("SHELL=", dispshell); }
	if (!have_path) add_env("PATH=/system/bin:/system/xbin:/vendor/bin");

	/* đã là root (adb root / shell root): chạy luôn, không cần daemon */
	if (sc0(SYS_getuid) == 0) {
		split(g_args, g_nargs, g_av); split(g_env, g_nenv, g_ev);
		if (sc1(SYS_chdir, cwd) != 0) sc1(SYS_chdir, "/");
		if (target != 0) {
			u32 g = target;
			if (sc2(SYS_setgroups, 1, &g) || sc3(SYS_setresgid, g, g, g) || sc3(SYS_setresuid, target, target, target)) {
				eput("su: không đổi được người dùng\n"); sys_exit(1);
			}
		}
		sc3(SYS_execve, dispshell, g_av, g_ev);
		eput("su: không chạy được "); eput(dispshell); eput("\n");
		sys_exit(127);
	}

	set_sig(SIGPIPE, (void (*)(int))1, 0);      /* SIG_IGN: daemon đóng sớm thì báo lỗi, không chết */

	/* kết nối daemon (socket trừu tượng) */
	const char *sockname = getenv_(envp, "CPSU_SOCK");
	if (!sockname || !*sockname) sockname = DEF_SOCK;
	struct { u16 family; char path[108]; } addr;
	memset(&addr, 0, sizeof addr);
	addr.family = 1;                              /* AF_UNIX */
	size_t nl = slen(sockname); if (nl > 100) nl = 100;
	memcpy(addr.path + 1, sockname, nl);
	long s = sc3(SYS_socket, 1, 1 | 0x80000, 0);  /* SOCK_STREAM | SOCK_CLOEXEC */
	if (s < 0 || sc3(SYS_connect, s, &addr, 2 + 1 + nl) != 0) {
		eput("su: root chưa bật / daemon không chạy (CloudBlue: Công cụ → 🔓 Root)\n");
		sys_exit(1);
	}

	u32 flags = 0;
	int t0 = is_tty(0), t1 = is_tty(1), t2 = is_tty(2);
	if (t0) flags |= F_STDIN_TTY;
	if (t1) flags |= F_STDOUT_TTY;
	if (t2) flags |= F_STDERR_TTY;
	if (login) flags |= F_LOGIN;
	if (preserve) flags |= F_PRESERVE;
	struct kwinsize ws; memset(&ws, 0, sizeof ws);
	for (int f = 0; f < 3; f++) if ((flags & (1u << f)) && sc3(SYS_ioctl, f, TIOCGWINSZ, &ws) == 0) break;

	struct req_hdr h;
	memcpy(h.magic, "CPS1", 4); h.version = 1; h.target_uid = target; h.flags = flags;
	h.ws_row = ws.row; h.ws_col = ws.col; h.ws_xpix = ws.xpix; h.ws_ypix = ws.ypix;
	h.n_args = g_nargs; h.n_env = g_nenv;

	/* thân = shell\0 cwd\0 argv… env… */
	put(g_body, &g_body_len, reqshell); put(g_body, &g_body_len, cwd);
	if (g_body_len + g_args_len + g_env_len > MAX_BODY) too_big();
	memcpy(g_body + g_body_len, g_args, g_args_len); g_body_len += g_args_len;
	memcpy(g_body + g_body_len, g_env, g_env_len); g_body_len += g_env_len;
	h.body_len = (u32)g_body_len;

	int std3[3] = { (int)sc1(SYS_dup, 0), (int)sc1(SYS_dup, 1), (int)sc1(SYS_dup, 2) };
	if (std3[0] < 0 || std3[1] < 0 || std3[2] < 0
	    || send_with_fds((int)s, &h, sizeof h, std3, 3) || write_all((int)s, g_body, g_body_len)) {
		eput("su: không gửi được yêu cầu\n"); sys_exit(1);
	}
	for (int k = 0; k < 3; k++) sc1(SYS_close, std3[k]);

	struct resp_hdr rp; int mfd = -1;
	if (recv_with_fd((int)s, &rp, sizeof rp, &mfd)) { eput("su: daemon không trả lời\n"); sys_exit(1); }
	if (rp.code == R_DENY) {
		eput("su: app này chưa được cấp quyền root — bật trong CloudBlue: Công cụ → 🔓 Root\n");
		sys_exit(1);
	}
	if (rp.code != R_ALLOW) { eput("su: lỗi\n"); sys_exit(1); }

	int st = 0;
	if (!(rp.flags & R_HASPTY) || mfd < 0) {        /* không có tty: con dùng thẳng fd của mình */
		if (mfd >= 0) sc1(SYS_close, mfd);
		if (read_all((int)s, &st, sizeof st)) sys_exit(1);
		sys_exit(st & 0xff);
	}

	/* phiên pty: stdin (nếu là tty) → master; master → stdout/stderr (nếu là tty) */
	g_master = mfd;
	if (t0 && sc3(SYS_ioctl, 0, TCGETS, &g_saved) == 0) {
		struct ktermios raw = g_saved;
		make_raw(&raw);
		if (sc3(SYS_ioctl, 0, TCSETS, &raw) == 0) g_raw = 1;
	}
	set_sig(SIGHUP, on_fatal, 0); set_sig(SIGTERM, on_fatal, 0);
	set_sig(SIGQUIT, on_fatal, 0); set_sig(SIGINT, on_fatal, 0);
	set_sig(SIGWINCH, on_winch, SA_RESTART);
	on_winch(0);

	int out_fd = t1 ? 1 : (t2 ? 2 : -1);
	int have_st = 0, stdin_on = t0, master_on = 1;
	struct pollfd_ { int fd; short events, revents; } pf[3];
	for (;;) {
		int np = 0, im = -1, is = -1, ii = -1;
		if (master_on) { pf[np].fd = mfd; pf[np].events = 1; pf[np].revents = 0; im = np++; }
		pf[np].fd = (int)s; pf[np].events = 1; pf[np].revents = 0; is = np++;
		if (stdin_on) { pf[np].fd = 0; pf[np].events = 1; pf[np].revents = 0; ii = np++; }
		long r = sc5(SYS_ppoll, pf, np, 0, 0, 8);
		if (r == -EINTR) continue;
		if (r < 0) break;
		if (ii >= 0 && (pf[ii].revents & (1 | 0x10 | 8))) {          /* POLLIN | POLLHUP | POLLERR */
			long k = sc3(SYS_read, 0, g_io, sizeof g_io);
			if (k > 0) write_all(mfd, g_io, (size_t)k);
			else if (k != -EINTR && k != -EAGAIN) stdin_on = 0;
		}
		if (im >= 0 && (pf[im].revents & (1 | 0x10 | 8))) {
			long k = sc3(SYS_read, mfd, g_io, sizeof g_io);
			if (k > 0) { if (out_fd >= 0) write_all(out_fd, g_io, (size_t)k); }
			else if (k != -EINTR && k != -EAGAIN) master_on = 0;     /* EIO: phía con đã đóng — chờ mã thoát */
		}
		if (pf[is].revents & (1 | 0x10 | 8)) {
			if (!read_all((int)s, &st, sizeof st)) have_st = 1;
			/* vét nốt chữ còn trong pty (tối đa 50 ms mỗi lượt) */
			for (;;) {
				struct pollfd_ dp; dp.fd = mfd; dp.events = 1; dp.revents = 0;
				struct { long sec, nsec; } ts = { 0, 50 * 1000 * 1000 };
				if (sc5(SYS_ppoll, &dp, 1, &ts, 0, 8) <= 0 || !(dp.revents & 1)) break;
				long k = sc3(SYS_read, mfd, g_io, sizeof g_io);
				if (k <= 0) break;
				if (out_fd >= 0) write_all(out_fd, g_io, (size_t)k);
			}
			break;
		}
	}
	restore_tty();
	sys_exit(have_st ? (st & 0xff) : 1);
}
