#!/usr/bin/env python3
"""Diagnostics for N2 Ollama hang and N1/N4 SSH channel issues."""
import json
import os
import time
import urllib.request

import paramiko

N2 = "192.168.1.31"
N1 = "192.168.1.224"
N4 = "192.168.1.228"
SSH_PW = os.environ.get("QUANTUM_LLM_SSH_PW", "EllaRose89!")
VOID_BASE = "http://127.0.0.1:8808"

# Auth to Void
login = urllib.request.Request(
    VOID_BASE + "/api/users/login",
    data=json.dumps({"username": "admin", "password": ""}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(login, timeout=20) as r:
    token = json.loads(r.read())["data"]["access_token"]
VOID_H = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

def get_json(path, timeout=60):
    req = urllib.request.Request(VOID_BASE + path, headers=VOID_H, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# 1. N2 generate hang root cause
print("=== N2 Ollama generate probe ===")
for model in ["phi3:mini", "gemma4:latest", "llava:7b", "hermes3:latest"]:
    url = f"http://{N2}:11434/api/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps({"model": model, "prompt": "ping", "stream": False, "options": {"num_predict": 8}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            print(f"N2 generate {model}: {r.status} {round(time.time()-start,2)}s -> {d.get('response','')[:60]}")
    except Exception as e:
        print(f"N2 generate {model}: FAIL {type(e).__name__}: {str(e)[:80]} {round(time.time()-start,2)}s")

# 2. N1/N4 SSH channel closed
print("\n=== N1/N4 SSH channel tests ===")
for name, host in [("N1", N1), ("N4", N4)]:
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(host, username="zqmlocal", password=SSH_PW, timeout=15, look_for_keys=False)
        _, o, _ = c.exec_command("cmd /c echo BASIC_OK", timeout=10)
        print(name, "basic:", o.read().decode(errors="replace").strip())
        # sftp
        try:
            sftp = c.open_sftp()
            sftp.stat("C:\\Temp")
            print(name, "sftp: OK")
            sftp.close()
        except Exception as e:
            print(name, "sftp FAIL:", type(e).__name__, str(e)[:100])
        c.close()
    except Exception as e:
        print(name, "SSH FAIL:", type(e).__name__, str(e)[:120])

# 3. N2 Ollama service health via SSH
print("\n=== N2 Ollama service via SSH ===")
try:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(N2, username="zqmlocal", password=SSH_PW, timeout=15, look_for_keys=False)
    for cmd in [
        "cmd /c \"curl -s http://127.0.0.1:11434/api/version\"",
        "cmd /c \"curl -s http://127.0.0.1:11434/api/tags\"",
        "cmd /c \"tasklist /fi \"imagename eq ollama.exe\" /fo table\"",
        "cmd /c \"sc query ollama\"",
    ]:
        try:
            _, o, e = c.exec_command(cmd, timeout=20)
            out = o.read().decode(errors="replace").strip()
            err = e.read().decode(errors="replace").strip()
            print("CMD:", cmd[:40], "OUT:", out[:200], "ERR:", err[:100])
        except Exception as e:
            print("CMD:", cmd[:40], "FAIL:", type(e).__name__, str(e)[:100])
    c.close()
except Exception as e:
    print("N2 SSH FAIL:", type(e).__name__, str(e)[:120])

# 4. Live mesh catalog summary
print("\n=== Live mesh catalog ===")
backends = get_json("/api/mesh/ollama")["backends"]
for b in backends:
    print(b["name"], "healthy=", b["healthy"], "models=", len(b.get("models", [])), "failures=", b.get("status_failures"), "recovery=", b.get("recovery_in_s"))
