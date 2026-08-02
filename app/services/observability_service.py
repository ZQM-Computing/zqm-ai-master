"""
The Void AI Orchestration System — ZQM Observability Service
Version: 2.0.0 | ZQM Computing LLC

Pushes metrics, logs, and traces to the ZQM Observability system.
Also provides a Prometheus metrics endpoint for scraping.

ZQM Observability endpoint: http://192.168.1.225:9090/api/metrics
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from app.core.config import settings
from app.core.logger import get_logger
from app.models.task import Task, TaskResult

log = get_logger("observability-service")


# ── Prometheus Metrics (if available) ────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    _registry = CollectorRegistry()

    TASKS_TOTAL = Counter(
        "zqm_ai_tasks_total",
        "Total tasks processed",
        ["status", "cognitive_level", "input_method"],
        registry=_registry,
    )
    TASKS_DURATION = Histogram(
        "zqm_ai_task_duration_seconds",
        "Task execution duration",
        ["cognitive_level"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
        registry=_registry,
    )
    TOKENS_USED = Counter(
        "zqm_ai_tokens_total",
        "Total AI tokens consumed",
        ["provider", "model"],
        registry=_registry,
    )
    AGENTS_ACTIVE = Gauge(
        "zqm_ai_agents_active",
        "Number of currently active agents",
        registry=_registry,
    )
    CACHE_HIT_RATE = Gauge(
        "zqm_ai_cache_hit_rate",
        "VoidCache hit rate (0.0–1.0)",
        registry=_registry,
    )
    ROUTING_OVERRIDES = Counter(
        "zqm_ai_routing_overrides_total",
        "Routing decisions that changed cognitive level or reason counts",
        ["reason"],
        registry=_registry,
    )


class ObservabilityService:
    """
    ZQM Observability integration for The Void.

    Pushes:
    - Task metrics (count, duration, status)
    - Token usage
    - Agent performance
    - System health events

    Exposes Prometheus metrics at /metrics.
    """

    def __init__(self) -> None:
        self._endpoint = settings.observability_endpoint
        self._enabled = settings.observability_enabled
        self._timeout = 5
        self._batch: List[Dict[str, Any]] = []
        self._batch_size = 10

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Ping Observability endpoint."""
        if not self._enabled:
            return True  # No-op if disabled
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(
                    self._endpoint.replace("/metrics", "/health")
                )
                return resp.status_code < 500
        except Exception as exc:
            log.debug("Observability health check failed", error=str(exc))
            return False

    # ── Task metrics ──────────────────────────────────────────────────────────

    async def push_task_metric(self, task: Task, result: Optional[TaskResult] = None) -> None:
        """Push a task completion metric to ZQM Observability."""
        if not self._enabled:
            return

        # co-task pair topology summary
        co_task_pairs = []
        try:
            if hasattr(self, "_registry") and self._registry is not None:
                co_task_pairs = await self._registry.get_top_co_task_pairs(limit=10)
        except Exception:
            pass

        metric = {
            "type": "task",
            "zqm_ai_id": settings.zqm_ai_id,
            "task_id": task.task_id,
            "status": task.status,
            "cognitive_level": task.cognitive_level,
            "input_method": task.input_method,
            "duration_ms": task.duration_ms,
            "timestamp": task.completed_at.isoformat() if task.completed_at else None,
            "tokens": result.total_tokens if result else None,
            "model": result.model_used if result else None,
            "provider": result.provider_used if result else None,
            "agents": (
                task.cognitive_trace.agents_used
                if task.cognitive_trace else []
            ),
            "routing": (
                task.cognitive_trace.routing
                if task.cognitive_trace and getattr(task.cognitive_trace, "routing", None) else None
            ),
            "diversity_ratio": getattr(result, "diversity_ratio", None),
            "co_task_pairs": co_task_pairs,
        }

        # Update Prometheus counters
        if PROMETHEUS_AVAILABLE:
            try:
                TASKS_TOTAL.labels(
                    status=task.status,
                    cognitive_level=task.cognitive_level,
                    input_method=task.input_method,
                ).inc()

                if task.duration_ms:
                    TASKS_DURATION.labels(
                        cognitive_level=task.cognitive_level,
                    ).observe(task.duration_ms / 1000)

                if result and result.total_tokens and result.provider_used and result.model_used:
                    TOKENS_USED.labels(
                        provider=result.provider_used,
                        model=result.model_used,
                    ).inc(result.total_tokens)

                routing = None
                if task.cognitive_trace and getattr(task.cognitive_trace, "routing", None):
                    routing = task.cognitive_trace.routing
                if routing:
                    ROUTING_OVERRIDES.labels(
                        reason=routing.get("reason", ""),
                    ).inc()
            except Exception as exc:
                log.debug("Prometheus metric update failed", error=str(exc))

        # Add to batch and flush if full
        self._batch.append(metric)
        if len(self._batch) >= self._batch_size:
            await self._flush_batch()

    async def push_agent_metric(self, agent_stats: Dict[str, Any]) -> None:
        """Push agent pool statistics."""
        if not self._enabled:
            return

        if PROMETHEUS_AVAILABLE:
            try:
                AGENTS_ACTIVE.set(agent_stats.get("busy", 0))
            except Exception:
                pass

        metric = {
            "type": "agents",
            "zqm_ai_id": settings.zqm_ai_id,
            "stats": agent_stats,
            "timestamp": time.time(),
        }
        self._batch.append(metric)

    async def push_cache_metric(self, hit_rate: float, size: int) -> None:
        """Push VoidCache statistics."""
        if not self._enabled:
            return

        if PROMETHEUS_AVAILABLE:
            try:
                CACHE_HIT_RATE.set(hit_rate)
            except Exception:
                pass

    # ── Event logging ─────────────────────────────────────────────────────────

    async def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Push a structured event log to ZQM Observability."""
        if not self._enabled:
            return

        event = {
            "type": "event",
            "event_type": event_type,
            "message": message,
            "severity": severity,
            "zqm_ai_id": settings.zqm_ai_id,
            "context": context or {},
            "timestamp": time.time(),
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await client.post(
                    self._endpoint.replace("/metrics", "/events"),
                    json=event,
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
        except Exception as exc:
            log.debug("Observability event push failed", error=str(exc))

    # ── Prometheus endpoint ───────────────────────────────────────────────────

    def get_prometheus_metrics(self) -> bytes:
        """Return Prometheus metrics as bytes for the /metrics endpoint."""
        if PROMETHEUS_AVAILABLE:
            return generate_latest(_registry)
        return b"# Prometheus client not available\n"

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _flush_batch(self) -> None:
        """Flush the metrics batch to ZQM Observability."""
        if not self._batch:
            return

        batch = list(self._batch)
        self._batch.clear()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await client.post(
                    f"{self._endpoint}/batch",
                    json={"metrics": batch, "zqm_ai_id": settings.zqm_ai_id},
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                log.debug("Observability batch flushed", count=len(batch))
        except Exception as exc:
            log.debug("Observability batch flush failed", error=str(exc))
            # Don't lose metrics — re-add to batch on failure
            # (but cap to avoid unbounded growth)
            if len(self._batch) < 100:
                self._batch.extend(batch[:20])
