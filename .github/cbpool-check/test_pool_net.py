#!/usr/bin/env python3
# Thử THẬT cbpool trên CI (root): mạng giả lập máy chủ Proxmox + modem nhà mạng.
#
#   netns "pve" (máy chủ Proxmox)                      netns "isp" (modem + nhà mạng)
#   vmbr0 (bridge) ── vp0 ═══════ veth ═══════ vp1      2001:db8:1::1/64 · 192.168.77.1/24 (cổng mạng nội bộ)
#     2001:db8:1::100/64 (như SLAAC)                    198.51.100.1 (máy đích "Internet", trả lại IP người hỏi)
#     192.168.77.2/24, mặc định qua .1                   pppoe-server: AC "cbtest-ac", cấp 203.0.113.10+ (mỗi phiên 1 IP)
#     cbpool: 4 ô, 3 phiên PPPoE (macvlan trên vmbr0)
#
# Dùng: sudo python3 test_pool_net.py ./cbpool-x86_64
import json, os, signal, subprocess, sys, time

BIN = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "./cbpool-x86_64")
D = "/tmp/cbp"
CONF = D + "/cbpool.json"
SECRET = D + "/ppp.secret"
results = []


def sh(cmd, check=True, ns=None, timeout=60, inp=None):
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, input=inp)
    if check and r.returncode != 0:
        raise RuntimeError("lệnh lỗi (%d): %s\n%s\n%s" % (r.returncode, cmd, r.stdout[-2000:], r.stderr[-2000:]))
    return r


def ok(name, cond, info=""):
    results.append((name, bool(cond), info))
    print(("✓ " if cond else "✗ ") + name + ((" — " + str(info)) if info else ""), flush=True)
    return cond


def status():
    r = sh("%s status -c %s" % (BIN, CONF), ns="pve", check=False)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def curl(user, pw, url, socks_host=False):
    opt = "--socks5-hostname" if socks_host else "--socks5"
    r = sh("curl -s --max-time 12 %s 127.0.0.1:8899 --proxy-user '%s:%s' '%s'" % (opt, user, pw, url), ns="pve", check=False, timeout=30)
    return r.stdout.strip()


def setup():
    for ns in ("pve", "isp"):
        sh("ip netns del %s" % ns, check=False)
    sh("modprobe pppoe", check=False)
    sh("modprobe macvlan", check=False)
    sh("ip netns add pve")
    sh("ip netns add isp")
    for ns in ("pve", "isp"):
        for k in ("all", "default"):
            sh("sysctl -qw net.ipv6.conf.%s.accept_dad=0" % k, ns=ns)
            sh("sysctl -qw net.ipv6.conf.%s.disable_ipv6=0" % k, ns=ns)
        sh("ip link set lo up", ns=ns)
    sh("ip link add vp0 netns pve type veth peer name vp1 netns isp")
    sh("ip link add vmbr0 type bridge", ns="pve")
    sh("ip link set vp0 master vmbr0", ns="pve")
    for c in ("ip link set vmbr0 up", "ip link set vp0 up", "ip addr add 2001:db8:1::100/64 dev vmbr0 nodad",
              "ip addr add 192.168.77.2/24 dev vmbr0", "ip route add default via 192.168.77.1"):
        sh(c, ns="pve")
    for c in ("ip link set vp1 up", "ip addr add 2001:db8:1::1/64 dev vp1 nodad", "ip addr add 192.168.77.1/24 dev vp1",
              "ip link add dummy0 type dummy", "ip link set dummy0 up", "ip addr add 198.51.100.1/32 dev dummy0"):
        sh(c, ns="isp")
    # máy đích: HTTP trả lại IP người kết nối (nghe cả IPv4 + IPv6)
    who = D + "/who.py"
    os.makedirs(D, exist_ok=True)
    open(who, "w").write(
        "import socket, http.server, socketserver\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        ip = self.client_address[0]\n"
        "        ip = ip[7:] if ip.startswith('::ffff:') else ip\n"
        "        b = ip.encode(); self.send_response(200); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)\n"
        "    def log_message(self, *a): pass\n"
        "class S(socketserver.ThreadingMixIn, http.server.HTTPServer):\n"
        "    address_family = socket.AF_INET6\n"
        "    daemon_threads = True\n"
        "    def server_bind(self):\n"
        "        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0); super().server_bind()\n"
        "S(('::', 8080), H).serve_forever()\n")
    subprocess.Popen("ip netns exec isp python3 %s" % who, shell=True)
    # tên miền thử (cbpool phân giải qua /etc/hosts)
    hosts = open("/etc/hosts").read()
    if "dual.cbtest" not in hosts:
        open("/etc/hosts", "a").write("\n198.51.100.1 dual.cbtest\n2001:db8:1::1 dual.cbtest\n198.51.100.1 v4.cbtest\n")
    # nhà mạng: pppoe-server có mật khẩu
    for f in ("/etc/ppp/pap-secrets", "/etc/ppp/chap-secrets"):
        t = open(f).read() if os.path.exists(f) else ""
        if "cbtest" not in t:
            open(f, "a").write('\n"cbtest" * "pw-cb-123" *\n')
    open("/etc/ppp/pppoe-server-options", "w").write("require-pap\nlcp-echo-interval 5\nlcp-echo-failure 3\nnoipdefault\nnodefaultroute\nnoccp\nnovj\nmtu 1492\nmru 1492\n")
    r = sh("pppoe-server -k -I vp1 -L 203.0.113.1 -R 203.0.113.10 -N 12 -C cbtest-ac -S internet -O /etc/ppp/pppoe-server-options", ns="isp", check=False)
    if r.returncode != 0:
        print("pppoe-server -k lỗi, dùng chế độ thường:", r.stderr.strip())
        sh("pppoe-server -I vp1 -L 203.0.113.1 -R 203.0.113.10 -N 12 -C cbtest-ac -S internet -O /etc/ppp/pppoe-server-options", ns="isp")
    time.sleep(1)


def main():
    setup()
    json.dump({"listen": "127.0.0.1:8899", "iface6": "vmbr0", "slots": 4, "bw_kbps": -1, "state_dir": D + "/st", "ctl": D + "/ctl.sock",
               "ppp": {"iface": "vmbr0", "secret": SECRET}}, open(CONF, "w"))
    json.dump({"user": "cbtest", "pass": "pw-cb-123", "sessions": 3}, open(SECRET, "w"))
    os.chmod(SECRET, 0o600)

    r = sh("%s ppp-test -c %s -i vmbr0" % (BIN, CONF), ns="pve", check=False)
    ok("ppp-test: dò thấy máy chủ PPPoE (không mật khẩu)", r.returncode == 0 and "cbtest-ac" in r.stdout, r.stdout.strip().splitlines()[0:2])

    log = open(D + "/cbpool.log", "w")
    proc = subprocess.Popen("exec ip netns exec pve %s run -c %s" % (BIN, CONF), shell=True, stdout=log, stderr=subprocess.STDOUT)
    st = {}
    for _ in range(90):
        time.sleep(1)
        st = status()
        if st.get("ppp", {}).get("up") == 3 and all(s.get("ip6") for s in st.get("slots", [])):
            break
    ok("cbpool chạy: 3 phiên PPPoE lên + 4 ô có IPv6", st.get("ppp", {}).get("up") == 3 and len(st.get("slots", [])) == 4,
       "ppp up %s, v6 %s" % (st.get("ppp", {}).get("up"), st.get("v6", {}).get("prefix")))
    slots = {s["id"]: s for s in st.get("slots", [])}
    if len(slots) != 4:
        print(open(D + "/cbpool.log").read())
        return

    # IPv6 riêng từng ô (qua NDP thật trên veth: máy đích phải hỏi được địa chỉ /128 của ô)
    seen6 = {}
    for sid, s in sorted(slots.items()):
        got = curl(sid, s["pass"], "http://[2001:db8:1::1]:8080/")
        seen6[sid] = got
        ok("%s ra IPv6 riêng %s" % (sid, got), got == s["ip6"] and got.startswith("2001:db8:1:"), "muốn " + s["ip6"])
    ok("4 ô = 4 IPv6 khác nhau", len(set(seen6.values())) == 4)

    # IPv4 theo phiên PPPoE: p01..p03 = 3 IP khác nhau, p04 dùng chung phiên 0 với p01
    seen4 = {}
    for sid, s in sorted(slots.items()):
        seen4[sid] = curl(sid, s["pass"], "http://198.51.100.1:8080/")
        ok("%s ra IPv4 phiên PPPoE %s" % (sid, seen4[sid]), seen4[sid] == s.get("ip4") and seen4[sid].startswith("203.0.113."), "muốn %s" % s.get("ip4"))
    ok("p01/p02/p03 = 3 IPv4 khác nhau, p04 chung phiên với p01",
       len({seen4["p01"], seen4["p02"], seen4["p03"]}) == 3 and seen4["p04"] == seen4["p01"])

    s1 = slots["p01"]
    ok("tên miền có AAAA → IPv6 của ô", curl("p01", s1["pass"], "http://dual.cbtest:8080/", True) == s1["ip6"])
    ok("tên miền chỉ có A → IPv4 phiên của ô", curl("p01", s1["pass"], "http://v4.cbtest:8080/", True) == s1["ip4"])
    ok("sai mật khẩu → không qua được", curl("p01", "sai-mat-khau", "http://198.51.100.1:8080/") == "")
    r = sh("curl -s --max-time 8 -x http://p02:%s@127.0.0.1:8899 http://198.51.100.1:8080/" % slots["p02"]["pass"], ns="pve", check=False)
    ok("proxy HTTP (http://) cùng cổng", r.stdout.strip() == slots["p02"]["ip4"], r.stdout.strip())
    r = sh("curl -s --max-time 8 -p -x http://p03:%s@127.0.0.1:8899 http://[2001:db8:1::1]:8080/" % slots["p03"]["pass"], ns="pve", check=False)
    ok("proxy HTTP CONNECT tới IPv6", r.stdout.strip() == slots["p03"]["ip6"], r.stdout.strip())

    # đổi IPv6 bằng link
    r = sh("curl -s --max-time 8 'http://127.0.0.1:8899/rotate?key=%s&what=v6'" % slots["p02"]["rot"], ns="pve", check=False)
    try:
        rj = json.loads(r.stdout)
    except Exception:
        rj = {}
    new6 = curl("p02", slots["p02"]["pass"], "http://[2001:db8:1::1]:8080/")
    ok("link /rotate đổi IPv6 của p02", rj.get("ok") and new6 == rj.get("ip6") and new6 != seen6["p02"], "%s → %s" % (seen6["p02"], new6))

    # đổi IPv4: quay lại phiên của p03 (phiên 2)
    since0 = [x for x in st["ppp"]["sess"] if x["k"] == 2][0].get("since")
    r = sh("%s rotate p03 v4 -c %s" % (BIN, CONF), ns="pve", check=False, timeout=70)
    try:
        rj = json.loads(r.stdout)
    except Exception:
        rj = {}
    st2 = status()
    s2 = [x for x in st2.get("ppp", {}).get("sess", []) if x["k"] == 2]
    got = curl("p03", slots["p03"]["pass"], "http://198.51.100.1:8080/")
    ok("đổi IPv4 p03: phiên 2 quay lại xong, vẫn ra Internet", rj.get("ok") and s2 and s2[0].get("since") != since0 and got == rj.get("ip4"),
       "%s → %s" % (seen4["p03"], got))

    # nhà mạng cắt phiên 0 → cbpool tự quay lại
    ip0 = [x for x in status()["ppp"]["sess"] if x["k"] == 0][0].get("ip")
    sh("pkill -f 'pppd.*%s' || true" % ip0, ns="isp", check=False)
    back = False
    for _ in range(45):
        time.sleep(1)
        s = status()
        x = [y for y in s.get("ppp", {}).get("sess", []) if y["k"] == 0]
        if s.get("ppp", {}).get("up") == 3 and x and x[0].get("since", 0) > int(time.time()) - 40:
            back = True
            break
    ok("phiên bị nhà mạng cắt → tự quay lại", back)

    # quay thử 2 phiên riêng (lệnh cho admin), không đụng phiên đang chạy
    r = sh("%s ppp-test -c %s -i vmbr0 --dial 2 </dev/null" % (BIN, CONF), ns="pve", check=False, timeout=90)
    ok("ppp-test --dial 2: 2 phiên thử lên, 2 IP khác nhau", r.returncode == 0 and "2/2 phiên lên, 2 IP khác nhau" in r.stdout,
       [l for l in r.stdout.splitlines() if "phiên" in l][:3])
    ok("phiên thật vẫn chạy sau khi thử", status().get("ppp", {}).get("up") == 3)

    # tắt PPPoE → IPv4 ra bằng IP chung (192.168.77.2)
    json.dump({"user": "cbtest", "pass": "pw-cb-123", "sessions": 0}, open(SECRET, "w"))
    sh("%s reload -c %s" % (BIN, CONF), ns="pve", check=False)
    time.sleep(2)
    got = curl("p01", s1["pass"], "http://198.51.100.1:8080/")
    ok("PPPoE tắt → IPv4 ra bằng IP chung", got == "192.168.77.2", got)
    links = sh("ip -o link", ns="pve").stdout
    rules = sh("ip rule", ns="pve").stdout
    ok("tắt PPPoE: gỡ sạch macvlan + luật định tuyến", "cbpp" not in links and "lookup 210" not in rules, rules.strip().splitlines()[-3:])

    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=20)
    ok("cbpool dừng sạch", proc.returncode == 0, proc.returncode)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        ok("chạy hết bộ thử", False, e)
    print("\n## cbpool thử thật: %d/%d đạt\n" % (sum(1 for r in results if r[1]), len(results)))
    print("| | Phép thử | Chi tiết |\n|---|---|---|")
    for n, c, i in results:
        print("| %s | %s | %s |" % ("✓" if c else "✗", n, str(i).replace("|", "/")[:160]))
    if os.path.exists(D + "/cbpool.log"):
        print("\n<details><summary>nhật ký cbpool</summary>\n\n```\n" + open(D + "/cbpool.log").read()[-6000:] + "\n```\n</details>")
    sys.exit(0 if results and all(r[1] for r in results) else 1)
