"""Diagnose why /api/status reports redis=unreachable despite healthy container."""
import asyncio
import json
import urllib.request

from app.core.config import Settings
from app.services.redis_service import RedisService


async def main():
    settings = Settings()
    print(f"settings.redis_url={settings.redis_url!r}")
    print(f"settings.redis_password={'***' if settings.redis_password else ''!r}")

    # Direct RedisService check
    rs = RedisService()
    health = await rs.health_check()
    print(f"direct_redis_health={health}")
    await rs.close()

    # Live endpoint check
    base = "http://127.0.0.1:8808"
    login = urllib.request.Request(
        base + "/api/users/login",
        data=json.dumps({"username": "admin", "password": ""}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login, timeout=20) as r:
        token = json.loads(r.read())["data"]["access_token"]

    req = urllib.request.Request(
        base + "/api/status",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())["data"]

    print(f"status_endpoint_redis={data.get('redis')!r}")
    print(f"status_endpoint_status={data.get('status')!r}")

    # Check app.state.redis via test client
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    redis_state = getattr(app.state, "redis", None)
    print(f"testclient_app_state_redis={redis_state}")
    if redis_state is not None:
        try:
            loop = asyncio.get_event_loop()
            h = loop.run_until_complete(redis_state.health_check())
            print(f"testclient_redis_health={h}")
        except Exception as exc:
            print(f"testclient_redis_health_error={exc}")

if __name__ == "__main__":
    asyncio.run(main())
