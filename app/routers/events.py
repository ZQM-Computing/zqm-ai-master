
"""
The Void — SSE Events Router
External SSE stream for dashboard/CLI/mesh subscribers.
Wires the in-process EventBus to an HTTP endpoint.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.event_bus import bus
from app.core.sse import enhanced_sse_stream
from app.core.logger import get_logger

router = APIRouter()
log = get_logger("router.events")


@router.get("/api/events")
async def events_stream(request: Request, topics: str = "") -> StreamingResponse:
    """
    SSE stream of live system events.
    ?topics=self_improve,task_completed,falsification
    """
    topic_filter = [t.strip() for t in topics.split(",") if t.strip()]

    async def _gen():
        async with bus.subscribe(history=True, maxlen=512) as sub:
            try:
                async for rec in sub:
                    if topic_filter and rec.get("event") not in topic_filter:
                        continue
                    yield rec
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        enhanced_sse_stream(_gen(), request=request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/events/recent")
async def events_recent(limit: int = 50):
    """Recent event history for late joiners."""
    return {"events": bus.iter_recent(limit=min(limit, 200))}
