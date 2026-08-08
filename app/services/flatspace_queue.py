
"""
The Void — FLATSPACE Write Queue
Background retry queue for FLATSPACE store operations.
When remote is down, writes are queued and retried with backoff
instead of being silently dropped.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logger import get_logger

log = get_logger("flatspace-queue")

MAX_QUEUE = 500
RETRY_INTERVAL = 30
MAX_RETRIES = 5


class WriteQueue:
    def __init__(self) -> None:
        self._queue: list[dict[str, Any]] = []
        self._retries: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._flatspace = None

    def start(self, flatspace_service: Any) -> None:
        self._flatspace = flatspace_service
        self._task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def enqueue(self, record: dict[str, Any]) -> None:
        if len(self._queue) >= MAX_QUEUE:
            self._queue.pop(0)
        self._queue.append(record)

    async def _drain_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(RETRY_INTERVAL)
                if not self._queue or not self._flatspace:
                    continue
                batch = self._queue[:10]
                self._queue = self._queue[10:]
                for rec in batch:
                    k = rec.get("key", "")
                    retries = self._retries.get(k, 0)
                    if retries >= MAX_RETRIES:
                        continue
                    try:
                        await self._flatspace.store(
                            key=rec["key"],
                            value=rec["value"],
                            tier=rec.get("tier", "bitgarden"),
                            metadata=rec.get("metadata"),
                        )
                        self._retries.pop(k, None)
                    except Exception as exc:
                        self._retries[k] = retries + 1
                        self._queue.append(rec)
                        log.debug("FLATSPACE write requeued", key=k, retry=retries + 1, error=str(exc))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("FLATSPACE drain loop error", error=str(exc))


write_queue = WriteQueue()
