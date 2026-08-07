"""Final proof for live council integrations."""
import asyncio
import json
import urllib.request
from datetime import datetime, timezone

BASE = "http://127.0.0.1:8808"

def post(path, token, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())

def get(path, token):
    req = urllib.request.Request(
        BASE + path, method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

async def main():
    login = urllib.request.Request(
        BASE + "/api/users/login",
        data=json.dumps({"username": "admin", "password": ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(login, timeout=20) as r:
        token = json.loads(r.read())["data"]["access_token"]

    # 1) Convene council and inspect integration_evidence
    conv = post("/api/void-council/convene", token, {"domain": "architecture"})
    cdata = conv.get("data", {})
    print("CONVENE")
    print("  domain:", cdata.get("domain"))
    print("  findings:", len(cdata.get("findings", [])))
    print("  quality:", cdata.get("quality_score"))
    print("  session:", cdata.get("session"))
    print("  integration_evidence:", cdata.get("integration_evidence"))

    # 2) Verify Redis list contains council session event
    from app.services.redis_service import RedisService
    rs = RedisService()
    await rs.connect()
    keys = []
    if rs._client is not None:
        async for k in rs._client.scan_iter("void:council:*"):
            keys.append(k)
    print("\nREDIS")
    print("  connected:", rs._client is not None)
    print("  council keys:", keys)
    await rs.close()

    # 3) Verify Flatspace has council_session records
    flat = post("/api/flatspace/search", token, {"query": "council_session", "limit": 10})
    results = flat.get("data", {}).get("results", [])
    print("\nFLATSPACE")
    print("  council_session records:", len(results))
    for r in results[:3]:
        print("  -", r.get("key"), "tier=", r.get("tier"))

    # 4) Verify quality/history enriched
    q = get("/api/void-council/quality?limit=10", token)
    qdata = q.get("data", {})
    print("\nQUALITY")
    print("  sessions:", qdata.get("sessions"))
    print("  avg_quality:", qdata.get("average_quality"))
    print("  top_domains:", qdata.get("top_domains"))

    # 5) Service health
    s = get("/api/status", token)
    status_data = s.get("data", {})
    print("\nSTATUS")
    print("  status:", status_data.get("status"))

    # 6) Write proof artifact
    proof = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "convene": cdata,
        "redis_keys": keys,
        "flatspace_sessions": len(results),
        "quality": qdata,
        "status": status_data.get("status"),
    }
    path = "C:/Void/ZQM-AI-Master/council_live_proof.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(proof, f, indent=2)
    print(f"\nPROOF_WRITTEN={path}")

if __name__ == "__main__":
    asyncio.run(main())
