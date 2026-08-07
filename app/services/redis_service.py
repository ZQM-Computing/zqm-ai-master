"""
The Void AI Orchestration System — Redis Service
Version: 2.1.0 | ZQM Computing LLC

Lightweight async Redis client wrapper for optional telemetry buffering,
mesh pub/sub, and distributed cache backing. Falls back gracefully when
Redis is unreachable.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

try:
    from redis.asyncio import Redis as AsyncRedis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

log = logging.getLogger("redis-service")


class RedisService:
    """
    Async Redis client wrapper with fail-soft behavior.

    If Redis is unreachable or misconfigured, operations return None/False
    rather than raising, keeping The Void operational without Redis.
    """

    def __init__(self) -> None:
        self._url: str = settings.redis_url
        self._client: Optional[Any] = None
        self._enabled: bool = bool(self._url and _REDIS_AVAILABLE)

    async def connect(self) -> bool:
        """Initialize Redis connection pool."""
        if not self._enabled or not _REDIS_AVAILABLE:
            return False
        try:
            self._client = AsyncRedis.from_url(
                self._url,
                password=settings.redis_password or None,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._client.ping()
            log.info("Redis connected")
            return True
        except Exception as exc:
            with open("C:/Void/ZQM-AI-Master/debug_redis_connect.txt", "a", encoding="utf-8") as f:
                f.write(f"connect_error={type(exc).__name__}: {exc}\n")
            log.debug("Redis connect failed", error=str(exc))
            self._client = None
            return False

    async def close(self) -> None:
        """Close connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def health_check(self) -> Dict[str, Any]:
        """Return Redis health status."""
        with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
            dbg.write(f"health_check called enabled={self._enabled} available={_REDIS_AVAILABLE} client={self._client}\n")
        if not self._enabled or not _REDIS_AVAILABLE:
            return {"status": "disabled", "redis_url": self._url or ""}
        try:
            if self._client is None:
                with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                    dbg.write("client is None, connecting...\n")
                connected = await self.connect()
                with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                    dbg.write(f"connected={connected} client={self._client}\n")
            else:
                try:
                    await self._client.ping()
                    connected = True
                    with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                        dbg.write("ping ok\n")
                except Exception as exc:
                    connected = False
                    with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                        dbg.write(f"ping failed: {exc}\n")
            if connected and self._client is not None:
                try:
                    info = await self._client.info("server")
                    version = info.get("redis_version", "unknown")
                    with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                        dbg.write(f"info ok version={version}\n")
                except Exception as exc:
                    version = "unknown"
                    with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                        dbg.write(f"info failed: {exc}\n")
                return {"status": "ok", "redis_url": self._url, "version": version}
            return {"status": "unreachable", "redis_url": self._url}
        except Exception as exc:
            with open("C:/Void/ZQM-AI-Master/debug_redis_service.txt", "a", encoding="utf-8") as dbg:
                dbg.write(f"exception: {exc}\n")
            return {"status": "error", "redis_url": self._url, "error": str(exc)[:200]}

    async def push_metric(self, key: str, payload: Dict[str, Any], ttl: int = 300) -> bool:
        """
        Push a metric/message to Redis.

        Used for optional observability buffering and mesh pub/sub.
        Returns True on success, False on failure.
        """
        if not self._enabled or self._client is None:
            return False
        try:
            await self._client.lpush(key, json.dumps(payload))
            await self._client.expire(key, ttl)
            return True
        except Exception as exc:
            log.debug("Redis push failed", key=key, error=str(exc))
            return False

    async def get_list(self, key: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve up to `limit` items from a Redis list."""
        if not self._enabled or self._client is None:
            return []
        try:
            raw = await self._client.lrange(key, 0, limit - 1)
            return [json.loads(item) for item in raw if item]
        except Exception as exc:
            log.debug("Redis get_list failed", key=key, error=str(exc))
            return []
