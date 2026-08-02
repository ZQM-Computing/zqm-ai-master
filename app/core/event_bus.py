"""
The Void AI Orchestration System — In-process Event Bus

Version: 2.1.0 | ZQM Computing LLC

Lightweight async pub/sub that lets the orchestrator, webhook receiver,
self-improve loop, roundtable, and self-apply pipeline all publish
structured events to any number of subscribers (SSE streams, log sinks,
in-process consumers). Fail-soft: a slow/dead subscriber never blocks
publishers (bounded per-subscriber queue, drops oldest on overflow).

Events are dicts: {"event": <type>, "data": <payload>, "ts": <iso>}.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from app.core.logger import get_logger

log = get_logger("event-bus")

_HISTORY_MAX = 200  # ring buffer of recent events for late SSE joiners
_BACKLOG_MAX = 128  # max events retained when subscriber falls behind


class EventBus:
    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue] = []
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._lag_counter: int = 0

    async def publish(
        self, event: str, data: Any, ts: Optional[str] = None
    ) -> None:
        record = {
            "event": event,
            "data": data,
            "ts": ts or datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._history.append(record)
            if len(self._history) > _HISTORY_MAX:
                self._history.pop(0)
            subs = list(self._subscribers)
        dropped = 0
        enqueued = 0
        for q in subs:
            try:
                q.put_nowait(record)
                enqueued += 1
            except asyncio.QueueFull:
                dropped += 1
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(record)
                    enqueued += 1
                except asyncio.QueueFull:
                    continue
        if dropped:
            self._lag_counter += dropped
        if dropped and self._lag_counter % 32 == 0:
            log.warning(
                "SSE backpressure", enqueued=enqueued, dropped=dropped, lag_counter=self._lag_counter
            )

    def subscribe(
        self, history: bool = True, maxlen: int = 256
    ) -> "EventBusSubscription":
        return EventBusSubscription(self, history=history, maxlen=maxlen)

    def subscribe_by_topic(
        self, topic: str, history: bool = True, maxlen: int = 256
    ) -> "EventBusTopicSubscription":
        return EventBusTopicSubscription(self, topic=topic, history=history, maxlen=maxlen)

    def iter_recent(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        snap = list(self._history)
        if limit is not None:
            if len(snap) > limit:
                snap = snap[-limit:]
        return snap


class EventBusSubscription:
    def __init__(self, bus: EventBus, history: bool, maxlen: int) -> None:
        self._bus = bus
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxlen)
        self._history = history

    async def __aenter__(self) -> AsyncIterator[Dict[str, Any]]:
        async with self._bus._lock:
            self._bus._subscribers.append(self._q)
            backlog = list(self._bus._history) if self._history else []
        for rec in backlog:
            try:
                self._q.put_nowait(rec)
            except asyncio.QueueFull:
                break
        return self._gen()

    async def __aexit__(self, *exc) -> None:
        async with self._bus._lock:
            if self._q in self._bus._subscribers:
                self._bus._subscribers.remove(self._q)

    async def _gen(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            try:
                yield await self._q.get()
            except asyncio.CancelledError:
                break


class EventBusTopicSubscription:
    def __init__(self, bus: EventBus, topic: str, history: bool, maxlen: int) -> None:
        self._bus = bus
        self._topic = topic
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxlen)
        self._history = history

    async def __aenter__(self) -> AsyncIterator[Dict[str, Any]]:
        async with self._bus._lock:
            self._bus._subscribers.append(self._q)
            if self._history:
                for rec in self._bus._history:
                    if rec.get("event") == self._topic:
                        try:
                            self._q.put_nowait(rec)
                        except asyncio.QueueFull:
                            break
        return self._gen()

    async def __aexit__(self, *exc) -> None:
        async with self._bus._lock:
            if self._q in self._bus._subscribers:
                self._bus._subscribers.remove(self._q)

    async def _gen(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            try:
                rec = await self._q.get()
                if rec.get("event") == self._topic:
                    yield rec
            except asyncio.CancelledError:
                break


# Module-level singleton (one bus per process).
bus = EventBus()
