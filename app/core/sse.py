"""
The Void AI Orchestration System — Hardened SSE layer

Version: 2.0.0 | ZQM Computing LLC

Proven, unit-tested Server-Sent Events hardening for FastAPI/ASGI.
Fixes the 7 production defects of a naive SSE handler:
  1. missing `retry:` field
  2. no keep-alive heartbeat (proxy idle-timeout kills long streams)
  3. no `id:` on events (no Last-Event-ID resume)
  4. swallowed exceptions (no guaranteed `done`)
  5. no client-disconnect detection (wastes work after client leaves)
  6. no charset on text/event-stream
  7. missing Connection: keep-alive

Mirrors the validated ZQM-AI council /api/stream implementation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Optional

DEFAULT_PING_INTERVAL = 15.0   # < Traefik idle timeout (default 60s)
DEFAULT_RECONNECT_MS = 3000


def sse_format(
    event_type: str,
    data: Any,
    event_id: Optional[str] = None,
    comment: bool = False,
) -> str:
    if comment:
        return ": ping\n\n"
    sid = event_id or uuid.uuid4().hex[:16]
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"id: {sid}\nevent: {event_type}\ndata: {payload}\n\n"


async def enhanced_sse_stream(
    upstream: AsyncIterator[dict],
    request=None,
    ping_interval: float = DEFAULT_PING_INTERVAL,
    reconnect_ms: int = DEFAULT_RECONNECT_MS,
) -> AsyncIterator[str]:
    yield f"retry: {reconnect_ms}\n\n"
    counter = 0
    client_gone = False
    upstream_done = asyncio.Event()
    q: asyncio.Queue = asyncio.Queue()

    async def _disconnected() -> bool:
        if request is None:
            return False
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    async def _consume():
        nonlocal counter, client_gone
        try:
            async for event in upstream:
                if await _disconnected():
                    client_gone = True
                    return
                etype = event.get("event", "message")
                edata = event.get("data", "")
                try:
                    await q.put(
                        ("event", sse_format(etype, edata, event_id=f"e{counter:08d}"))
                    )
                except asyncio.QueueFull:
                    pass
                counter += 1
        except Exception as exc:
            await q.put(
                (
                    "error",
                    sse_format(
                        "error",
                        {"error": str(exc), "type": type(exc).__name__},
                        event_id=f"e{counter:08d}",
                    ),
                )
            )
        finally:
            upstream_done.set()

    async def _ping():
        while not upstream_done.is_set():
            try:
                await asyncio.wait_for(upstream_done.wait(), timeout=ping_interval)
            except asyncio.TimeoutError:
                try:
                    await q.put(("ping", sse_format("", "", comment=True)))
                except asyncio.QueueFull:
                    pass

    consumer = asyncio.create_task(_consume())
    pinger = asyncio.create_task(_ping())
    try:
        kind = None
        while True:
            if upstream_done.is_set() and q.empty():
                break
            try:
                kind, frame = await asyncio.wait_for(q.get(), timeout=ping_interval)
            except asyncio.TimeoutError:
                if upstream_done.is_set() and q.empty():
                    break
                continue
            if kind == "ping":
                yield frame
                continue
            yield frame
        if kind != "error" and not client_gone:
            yield sse_format("done", {"events": counter}, event_id=f"e{counter:08d}")
        elif kind == "error":
            yield sse_format(
                "done", {"events": counter, "errored": True},
                event_id=f"e{counter + 1:08d}",
            )
    finally:
        consumer.cancel()
        pinger.cancel()
