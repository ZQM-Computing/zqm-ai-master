"""Proof: /api/status redis=ok after redis_service.py logging fix."""
import json
import urllib.request

BASE = "http://127.0.0.1:8808"

# 1. Login
login = urllib.request.Request(
    BASE + "/api/users/login",
    data=json.dumps({"username": "admin", "password": ""}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(login, timeout=20) as r:
    token = json.loads(r.read())["data"]["access_token"]

# 2. /api/status
req = urllib.request.Request(
    BASE + "/api/status",
    headers={"Authorization": f"Bearer {token}"},
    method="GET",
)
with urllib.request.urlopen(req, timeout=20) as r:
    data = json.loads(r.read())["data"]

print("=== /api/status proof ===")
print(f"status     = {data.get('status')}")
print(f"redis      = {data.get('redis')}")
print(f"garden     = {data.get('garden')}")
print(f"flatspace  = {data.get('flatspace')}")
print(f"observability = {data.get('observability')}")
print(f"uptime_s   = {data.get('uptime_seconds')}")

assert data.get("status") == "healthy", "status not healthy"
assert data.get("redis") == "ok", "redis not ok"
print("\nPASS: redis=ok on /api/status")
