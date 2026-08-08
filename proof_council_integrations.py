"""Proof script for Void Council integrations."""
import asyncio
import json
import urllib.request
from datetime import UTC, datetime

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
    # 1) Auth
    login = urllib.request.Request(
        BASE + "/api/users/login",
        data=json.dumps({"username": "admin", "password": ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(login, timeout=20) as r:
        token = json.loads(r.read())["data"]["access_token"]

    # 2) Convene council
    conv = post("/api/void-council/convene", token, {"domain": "architecture", "min_confidence": 0.6, "auto_apply": False})
    data = conv.get("data", {})
    print(f"convene domain={data.get('domain')} findings={len(data.get('findings',[]))} quality={data.get('quality_score')} session={data.get('session')}")
    print(f"integration_evidence={data.get('integration_evidence')}")

    # 3) Check Redis for council keys
    try:
        from app.services.redis_service import RedisService
        rs = RedisService()
        await rs.connect()
        print('redis_connected=', rs._client is not None)
        keys = []
        if rs._client is not None:
            async for k in rs._client.scan_iter("void:council:*"):
                keys.append(k)
        print(f"redis_keys={keys[:10]} total_matched={len(keys)}")
        await rs.close()
    except Exception as exc:
        print(f"redis_check=error {exc}")

    # 4) Check Flatspace for council_session via POST /search
    try:
        flat = post("/api/flatspace/search", token, {"query": "council_session", "limit": 10})
        results = flat.get("data", {}).get("results", [])
        print(f"flatspace_council_sessions={len(results)}")
        if results:
            print("flatspace_keys=", [r.get("key") for r in results[:3]])
    except Exception as exc:
        print(f"flatspace_check=error {exc}")

    # 5) Check quality/history
    q = get("/api/void-council/quality?limit=10", token)
    qdata = q.get("data", {})
    print(f"quality_sessions={qdata.get('sessions')} avg_quality={qdata.get('average_quality')}")

    # 6) Verify status endpoint still healthy
    s = get("/api/status", token)
    status_data = s.get("data", {})
    print(f"status={status_data.get('status')} redis={status_data.get('redis')}")

    # 7) Write proof file
    proof = {
        "ts": datetime.now(UTC).isoformat(),
        "convene": data,
        "quality": qdata,
        "status_redis": status_data.get("redis"),
        "status_status": status_data.get("status"),
    }
    path = "C:/Void/ZQM-AI-Master/council_integration_proof.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(proof, f, indent=2)
    print(f"proof_written={path}")

if __name__ == "__main__":
    asyncio.run(main())
