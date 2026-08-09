#!/usr/bin/env python
"""
Live ARP gateway spoofing monitor.

Resolves the current default gateway IP, reads its MAC from `arp -a`, and
re-checks it every INTERVAL seconds. If the gateway's MAC ever changes (the
classic ARP-spoofing / MITM signal), it prints an ALERT and (optionally)
can run a custom command.

Stays within L2: it never trusts a single reading — it samples twice with a
short gap and only flags when BOTH agree on a changed MAC, to avoid
false positives from transient cache flushes.

Usage:
  python gateway_monitor.py [interval_seconds] [duration_seconds]
  duration 0 or omitted = run forever (Ctrl-C to stop)

Example:
  python gateway_monitor.py 10 0
"""
import subprocess, re, sys, time, datetime

def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True).stdout
    except Exception:
        return ""

def gateway_ip():
    out = run("ipconfig")
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "Default Gateway" in line:
            # IPv4 gateway is usually on the next 1-2 indented lines
            for nxt in lines[i:i+3]:
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", nxt)
                if m and m.group(1) != "0.0.0.0":
                    return m.group(1)
    return None

def arp_mac(ip):
    out = run(f"arp -a {ip}")
    m = re.search(rf"{re.escape(ip)}\s+([0-9a-fA-F-]{{17}})", out)
    return m.group(1).upper() if m else None

def main():
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    gw = gateway_ip()
    if not gw:
        print("ERROR: could not determine default gateway")
        sys.exit(1)
    print(f"[monitor] gateway IP = {gw}  interval = {interval}s  "
          f"{'forever' if duration == 0 else str(duration)+'s'}")
    baseline = arp_mac(gw)
    print(f"[monitor] baseline gateway MAC = {baseline}")
    if not baseline:
        print("[monitor] WARNING: gateway MAC not in ARP cache yet; will learn on first sample")
    start = time.time()
    seen = baseline
    while True:
        time.sleep(interval)
        m1 = arp_mac(gw)
        time.sleep(1.5)
        m2 = arp_mac(gw)
        # require two agreeing samples to flag (avoid cache-flush false positives)
        if m1 and m2 and m1 == m2 and m1 != seen:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n!!! ARP SPOOF ALERT @ {ts} !!!")
            print(f"    Gateway {gw} MAC CHANGED:")
            print(f"    previous = {seen}")
            print(f"    current  = {m1}")
            print(f"    This is the signature of an ARP man-in-the-middle attack.\n")
            seen = m1
        elif m1 == seen and m1 is not None:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] OK  gateway {gw} = {m1}")
        else:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] WARN gateway MAC not readable right now ({m1}/{m2})")
        if duration and (time.time() - start) >= duration:
            print("[monitor] duration reached, exiting")
            break

if __name__ == "__main__":
    main()
