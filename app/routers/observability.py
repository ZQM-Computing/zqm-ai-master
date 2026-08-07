"""
The Void AI Orchestration System — /api/observability Router
Version: 2.1.0 | ZQM Computing LLC

Prometheus metrics exposition + observability health.
/metrics is unauthenticated for scrape targets; all other endpoints require auth.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.logger import get_logger
from app.services.observability_service import PROMETHEUS_AVAILABLE

router = APIRouter(prefix="/api/observability", tags=["Observability"])
log = get_logger("router.observability")


@router.get(
    "/health",
    summary="Observability service health",
)
async def observability_health(request: Request) -> Dict[str, Any]:
    """Quick health check for the observability pipeline."""
    obs = request.app.state.orchestrator.observability
    ok = await obs.health_check()
    try:
        from prometheus_client import CollectorRegistry, generate_latest
        prometheus_available = True
    except Exception:
        prometheus_available = False
    return {
        "status": "ok" if ok else "unreachable",
        "prometheus_client": prometheus_available,
        "endpoint": obs._endpoint,
        "enabled": obs._enabled,
    }


@router.get(
    "/metrics",
    summary="Prometheus metrics (scrape endpoint)",
    response_class=Response,
    include_in_schema=False,
)
async def prometheus_metrics(request: Request) -> Response:
    """
    Prometheus exposition format.
    No auth required — scrape targets (Prometheus, Uptime Kuma) cannot carry JWTs.
    """
    orchestrator = request.app.state.orchestrator
    try:
        metrics_bytes = orchestrator.observability.get_prometheus_metrics()
        if not metrics_bytes:
            metrics_bytes = b"# No metrics collected yet\n"
    except Exception as exc:
        log.debug("metrics endpoint error", error=str(exc))
        metrics_bytes = b"# metrics unavailable\n"

    return Response(
        content=metrics_bytes,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
