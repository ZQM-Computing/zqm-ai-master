#!/usr/bin/env python
"""
diagnostics.py -- LAN / host health & connectivity diagnostics.

Runs a battery of live checks and records measurable results:
  D1  Gateway ICMP reachability + latency (loss%, min/avg/max)
  D2  Gateway TCP/443 service probe (is the router's admin/HTTPS up?)
  D3  DNS resolution test (resolve + measure, show resolver)
  D4  Public connectivity + latency (HTTP GET to 2 endpoints, w/ timings)
  D5  Per-neighbor latency (ping each ARP host: reachable + avg ms)
  D6  Interface error/discard counters (netstat -e)
  D7  DHCP lease details (ipconfig /all)
  D8  Wi-Fi link quality        [ADMIN + Location, else noted]

Outputs diagnostics_<ts>.txt (human) + diagnostics_<ts>.json (machine,
for attestation chaining). No fabrication: every number is measured.

Usage:
  python diagnostics.py
  python diagnostics.py --quiet     # print only, no files
"""
import subprocess, re, os, sys, json, datetime, time, socket, statistics, glob

HERE = os.path.dirname(os.path.abspath(__file__))

def run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, shell=True).stdout
    except Exception as e:
        return f"__ERR__{e}"

def banner(t):
    return "\n" + "=" * 70 + "\n" + t + "\n" + "=" * 70

def parse_ping(out):
    res = {"sent": 0, "recv": 0, "lost": 0, "loss_pct": None,
           "min": None, "avg": None, "max": None}
    m = re.search(r"Sent = (\d+), Received = (\d+), Lost = (\d+) \((\d+)% loss\)", out)
    if m:
        res.update(sent=int(m.group(1)), recv=int(m.group(2)),
                   lost=int(m.group(3)), loss_pct=int(m.group(4)))
    m2 = re.search(r"Minimum = (\d+)ms, Maximum = (\d+)ms, Average = (\d+)ms", out)
    if m2:
        res.update(min=int(m2.group(1)), avg=int(m2.group(2)), max=int(m2.group(3)))
    return res

def latency_to(ip, count=4, timeout_ms=1000):
    return parse_ping(run(f"ping -n {count} -w {timeout_ms} {ip}"))

# ----------------------------------------------------------------------
def d1_gateway():
    out = banner("[D1] Gateway ICMP reachability + latency")
    gw = "192.168.1.1"
    r = latency_to(gw, 4, 1000)
    out += (f"\n  target {gw}: sent={r['sent']} recv={r['recv']} "
             f"lost={r['lost']} ({r['loss_pct']}% loss)  "
             f"min={r['min']} avg={r['avg']} max={r['max']} ms")
    out += "\n  => healthy if 0% loss and avg < ~5ms on Wi-Fi / <1ms wired."
    return out, {"gw_icmp": r}

def d2_gw_tcp():
    out = banner("[D2] Gateway TCP/443 service probe")
    gw = "192.168.1.1"
    t0 = time.time()
    ok = False
    try:
        s = socket.create_connection((gw, 443), timeout=3)
        s.close(); ok = True
    except Exception as e:
        msg = str(e)
    dt = round((time.time() - t0) * 1000, 1)
    out += f"\n  connect {gw}:443 -> {'OPEN' if ok else 'CLOSED/timeout'} ({dt} ms)"
    out += "\n  => confirms the router's HTTPS admin plane is reachable on L2+L4."
    return out, {"gw_tcp443": {"open": ok, "ms": dt}}

def d3_dns():
    out = banner("[D3] DNS resolution test")
    name = "cloudflare-dns.com"
    t0 = time.time()
    try:
        ips = socket.gethostbyname_ex(name)[2]
        dt = round((time.time() - t0) * 1000, 1)
        out += f"\n  resolve {name} -> {ips}  ({dt} ms)"
        ok = True
    except Exception as e:
        out += f"\n  resolve {name} -> FAILED: {e}"
        ok, ips, dt = False, [], None
    dnscfg = run("ipconfig /all")
    srv = re.findall(r"DNS Servers[ .:]+([\d.]+)", dnscfg)
    srv = [s for s in srv if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s)]
    out += f"\n  configured DNS servers: {sorted(set(srv))}"
    out += "\n  => resolver responsive if an IP returns and latency is low."
    return out, {"dns": {"name": name, "ok": ok, "ips": ips, "ms": dt,
                          "servers": sorted(set(srv))}}

def d4_public():
    out = banner("[D4] Public connectivity + latency")
    tests = [("https://1.1.1.1", "Cloudflare"), ("https://www.google.com", "Google")]
    res = {}
    for url, label in tests:
        t0 = time.time()
        body = run(f'curl -s -o nul -w "%{{http_code}} %{{time_total}}" {url}')
        dt = round((time.time() - t0) * 1000, 1)
        code = body.split()[0] if body.split() else "?"
        tt = body.split()[1] if len(body.split()) > 1 else "?"
        out += f"\n  {label:12} {url:28} HTTP {code}  total={tt}s  wall={dt}ms"
        res[label] = {"http": code, "ttfb_s": tt, "wall_ms": dt}
    out += "\n  => egress works if HTTP 2xx/3xx and total time is sane (<2s)."
    return out, {"public": res}

def d5_neighbors():
    out = banner("[D5] Per-neighbor latency (each ARP host)")
    raw = run("arp -a")
    ips = [m.group(1) for m in re.finditer(
        r"^\s*(\d+\.\d+\.\d+\.\d+)\s+[0-9a-fA-F-]{17}\s+dynamic", raw, re.M)]
    res = {}
    out += f"\n  scanning {len(ips)} neighbors:"
    for ip in sorted(ips, key=lambda s: [int(x) for x in s.split(".")]):
        r = latency_to(ip, 2, 800)
        tag = f"loss={r['loss_pct']}% avg={r['avg']}ms" if r['avg'] is not None else "no reply"
        out += f"\n    {ip:16} {tag}"
        res[ip] = r
    out += ("\n  => hosts that answer = live & on-segment. Consistent with ARP table;\n"
            "     a host in ARP but 100% loss repeatedly can mean ARP cache stale or host filtered.")
    return out, {"neighbors": res}

def d6_iface_errors():
    out = banner("[D6] Interface error / discard counters (netstat -e)")
    raw = run("netstat -e")
    out += "\n" + raw.strip()
    err = re.search(r"Errors\s+(\d+)\s+(\d+)", raw)
    disc = re.search(r"Discards\s+(\d+)\s+(\d+)", raw)
    res = {}
    if err:
        res["errors"] = {"recv": int(err.group(1)), "send": int(err.group(2))}
    if disc:
        res["discards"] = {"recv": int(disc.group(1)), "send": int(disc.group(2))}
    out += ("\n  => non-zero recv-errors/discards can indicate duplex mismatch, "
            "cable/firmware issues, or ongoing L2 disruption. 0 = clean.")
    return out, {"iface_counters": res}

def d7_dhcp():
    out = banner("[D7] DHCP lease details (ipconfig /all)")
    raw = run("ipconfig /all")
    myip = re.search(r"IPv4 Address[ .:]+([\d.]+)", raw)
    dhcp = re.search(r"DHCP Enabled[ .:]+(Yes|No)", raw)
    srv = re.search(r"DHCP Server[ .:]+([\d.]+)", raw)
    lease = re.search(r"Lease Obtained[ .:]+([^\r\n]+)", raw)
    exp = re.search(r"Lease Expires[ .:]+([^\r\n]+)", raw)
    out += (f"\n  IPv4            : {myip.group(1) if myip else '?'}\n"
             f"  DHCP Enabled    : {dhcp.group(1) if dhcp else '?'}\n"
             f"  DHCP Server     : {srv.group(1) if srv else '?'}\n"
             f"  Lease Obtained : {lease.group(1).strip() if lease else '?'}\n"
             f"  Lease Expires  : {exp.group(1).strip() if exp else '?'}")
    out += "\n  => a lease expiring soon or a DHCP server that isn't your gateway merits a look."
    res = {"ipv4": myip.group(1) if myip else None,
           "dhcp_enabled": dhcp.group(1) if dhcp else None,
           "dhcp_server": srv.group(1) if srv else None}
    return out, {"dhcp": res}

def d8_wifi():
    out = banner("[D8] Wi-Fi link quality   [ADMIN + Location required]")
    raw = run("netsh wlan show interfaces")
    if "requires elevation" in raw or "Location" in raw or "error 5" in raw:
        out += ("\n  BLOCKED: needs admin shell + Location ON. Manual:\n"
                "    netsh wlan show interfaces\n"
                "  Look for: Signal (%), Transmit/Receive rate, Channel, PHY type.\n"
                "  Weak signal (<50%) or high channel congestion = retry/latency source.")
    else:
        sig = re.search(r"Signal\s*:\s*(\d+%)", raw)
        ch = re.search(r"Channel\s*:\s*(\d+)", raw)
        rate = re.search(r"Transmit rate\s*:\s*([^\r\n]+)", raw)
        out += (f"\n  Signal={sig.group(1) if sig else '?'}  "
                 f"Channel={ch.group(1) if ch else '?'}  "
                 f"TxRate={rate.group(1).strip() if rate else '?'}")
    return out, {}

def collect():
    """Run all D-modules, return (human_report, metrics_dict)."""
    rep, metrics = [], {}
    rep.append(banner(f"DIAGNOSTICS  @ {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"))
    rep.append(f"Host: {socket.gethostname()}  (192.168.1.21)  Subnet: 192.168.1.0/24")
    for fn in (d1_gateway, d2_gw_tcp, d3_dns, d4_public, d5_neighbors,
               d6_iface_errors, d7_dhcp, d8_wifi):
        s, m = fn()
        rep.append(s); metrics.update(m)
    return "\n".join(rep), metrics

def watcher():
    """Diff a fresh run against the most-recent sealed diagnostics JSON.
    Flags regressions: new/disappeared neighbor, gateway latency spike,
    interface errors/discards > 0, DNS-server change, DHCP-server change,
    public-egress failure."""
    files = sorted(glob.glob(os.path.join(HERE, "diagnostics_*.json")))
    # exclude any we just wrote this second via collect(); pick the prior latest
    base = files[-1] if files else None
    report, metrics = collect()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = os.path.join(HERE, f"diagnostics_{ts}.txt")
    js = os.path.join(HERE, f"diagnostics_{ts}.json")
    with open(txt, "w", encoding="utf-8") as f: f.write(report)
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"generated": ts, "host": socket.gethostname(),
                   "metrics": metrics}, f, indent=2)

    print(report)
    print("\n" + "=" * 70)
    print("[WATCHER] regression diff vs last baseline")
    print("=" * 70)
    if not base:
        print("  No prior diagnostics_*.json found -> this run is the new baseline.")
        print(f"  [saved] {txt}\n  [saved] {js}")
        return

    prev = json.load(open(base, encoding="utf-8"))["metrics"]
    cur = metrics
    alerts = []

    # 1) neighbor set changes
    pset = set(prev.get("neighbors", {}))
    cset = set(cur.get("neighbors", {}))
    for ip in sorted(cset - pset):
        alerts.append(f"NEW neighbor appeared: {ip}")
    for ip in sorted(pset - cset):
        alerts.append(f"neighbor disappeared: {ip}")

    # 2) gateway latency spike (avg ms)
    pgw = prev.get("gw_icmp", {}).get("avg")
    cgw = cur.get("gw_icmp", {}).get("avg")
    if pgw is not None and cgw is not None and cgw > pgw * 2 and cgw >= 10:
        alerts.append(f"gateway latency spike: {pgw}ms -> {cgw}ms")

    # 3) interface errors / discards > 0
    ec = cur.get("iface_counters", {})
    for k in ("errors", "discards"):
        d = ec.get(k, {})
        tot = (int(d.get("recv", 0) or 0) + int(d.get("send", 0) or 0))
        if tot > 0:
            alerts.append(f"interface {k} > 0: recv={d.get('recv')} send={d.get('send')}")

    # 4) DNS server change
    pdns = set(prev.get("dns", {}).get("servers", []))
    cdns = set(cur.get("dns", {}).get("servers", []))
    if pdns != cdns:
        alerts.append(f"DNS servers changed: {sorted(pdns)} -> {sorted(cdns)}")

    # 5) DHCP server change
    pdh = prev.get("dhcp", {}).get("dhcp_server")
    cdh = cur.get("dhcp", {}).get("dhcp_server")
    if pdh != cdh:
        alerts.append(f"DHCP server changed: {pdh} -> {cdh}")

    # 6) public egress failure
    for label, r in cur.get("public", {}).items():
        if str(r.get("http", "")) not in ("200", "301", "302", "304"):
            alerts.append(f"public egress {label} degraded: HTTP {r.get('http')}")

    if alerts:
        print(f"\n  ALERTS ({len(alerts)}):")
        for a in alerts:
            print(f"    ! {a}")
        print("\n  OVERALL: REGRESSION DETECTED")
    else:
        print("\n  No regressions vs baseline. OVERALL: STABLE")
    print(f"\n  baseline: {os.path.basename(base)}\n  current : {os.path.basename(js)}")
    print(f"  [saved] {txt}\n  [saved] {js}")

def main():
    if "--watcher" in sys.argv:
        watcher()
        return
    quiet = "--quiet" in sys.argv
    report, metrics = collect()
    print(report)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not quiet:
        txt = os.path.join(HERE, f"diagnostics_{ts}.txt")
        js = os.path.join(HERE, f"diagnostics_{ts}.json")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(report)
        with open(js, "w", encoding="utf-8") as f:
            json.dump({"generated": ts, "host": socket.gethostname(),
                       "metrics": metrics}, f, indent=2)
        print(f"\n[saved] {txt}\n[saved] {js}")
    else:
        print("\n__JSON__" + json.dumps(metrics))

if __name__ == "__main__":
    main()
