import json
import statistics
import time
import urllib.request

BASE = "http://127.0.0.1:8808"

def login():
    req = urllib.request.Request(
        BASE + "/api/users/login",
        data=json.dumps({"username":"admin","password":""}).encode(),
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["data"]["access_token"]

def bench_get(token, path, n=10):
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    times = []
    for _ in range(n):
        req = urllib.request.Request(BASE + path, headers=h, method="GET")
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                r.read()
                times.append(time.time() - start)
        except Exception:
            times.append(None)
    return times

def bench_process(token, n=5):
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    payload = json.dumps({
        "input": "ping",
        "cognitive_level": "basic",
        "stream": False,
        "timeout": 180,
        "model": "qwen2.5:0.5b",
    }).encode()
    times = []
    for _ in range(n):
        req = urllib.request.Request(BASE + "/api/process", headers=h, method="POST", data=payload)
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=220) as r:
                r.read()
                times.append(time.time() - start)
        except Exception:
            times.append(None)
    return times

def summarize(name, times):
    ok = [t for t in times if t is not None]
    if not ok:
        print(f"{name:45} 0/{len(times)} ok")
        return
    p95 = sorted(ok)[int(len(ok)*0.95)] if len(ok) > 1 else ok[0]
    print(f"{name:45} {len(ok)}/{len(times)} ok  min={min(ok):.2f}  avg={statistics.mean(ok):.2f}  p95={p95:.2f}  max={max(ok):.2f}")

def main():
    token = login()
    print("=== GET endpoint latency (n=10) ===")
    for path in [
        "/api/status",
        "/api/garden/health",
        "/api/garden/metrics",
        "/api/observability/health",
        "/api/agents",
        "/api/dashboard/agents",
        "/api/settings",
        "/api/quantum/health",
        "/api/quantum/models",
        "/api/quantum/nodes",
        "/api/mesh/backends",
        "/api/mesh/ollama",
        "/api/internal/selfcheck",
    ]:
        summarize(path, bench_get(token, path, n=10))
    print("\n=== /api/process throughput (n=5) ===")
    summarize("/api/process", bench_process(token, n=5))

if __name__ == "__main__":
    main()
