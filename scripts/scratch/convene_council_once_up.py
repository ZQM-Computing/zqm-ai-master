"""Convene the Void Council live once ZQM-Void-N4 is up on :8808.
Run AFTER: Restart-Service -Name 'ZQM-Void-N4' -Force (elevated PowerShell).
Auth: /api/users/login with ZQM_ADMIN_PASSWORD from .env -> Bearer -> POST /api/void-council/convene-full.
convene-full takes no body; reads findings from orchestrator state.
"""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, r"C:\Void\ZQM-AI-Master")
from pathlib import Path

BASE = "http://127.0.0.1:8808"

def env_val(name):
    p = Path(r"C:\Void\ZQM-AI-Master\.env")
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(name + "=") and not line.startswith("#"):
            return line.split("=", 1)[1]
    return ""

def post(path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:800]
    except Exception as e:
        return None, repr(e)

# 1) login
pw = env_val("ZQM_ADMIN_PASSWORD") or "zqm-ai-admin"
login = post("/api/users/login", {"username": "admin", "password": pw})
print("LOGIN", login[0])
if login[0] != 200:
    print("LOGIN BODY:", login[1][:300])
    sys.exit(1)
token = json.loads(login[1])["data"]["access_token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 2) domains (sanity)
print("DOMAINS", post("/api/void-council/domains", headers=H)[0])

# 3) convene-full
code, resp = post("/api/void-council/convene-full", body={}, headers=H)
print("CONVENE-FULL", code)
print(resp[:2000])
