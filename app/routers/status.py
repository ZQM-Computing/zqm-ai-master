"""
The Void AI Orchestration System — /api/status Router
Version: 2.0.0 | ZQM Computing LLC

System health and status endpoints.
"""

from __future__ import annotations

from collections import deque
from statistics import mean
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.logger import get_logger
from app.core.security import get_current_token_payload
from app.models.response import ZQM_AIResponse
from app.core.config import settings

router = APIRouter(prefix="/api/status", tags=["Status"])
log = get_logger("router.status")

_recent_latency: deque[float] = deque(maxlen=20)


@router.get(
    "",
    response_model=ZQM_AIResponse,
    summary="System health status",
    description="Returns full health status of The Void and all connected subsystems.",
)
async def get_status(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """
    Returns the health status of The Void and all connected ZQM subsystems:
    - ZQM Garden (distributed compute)
    - ZQM FLATSPACE (tiered memory)
    - ZQM Observability (metrics)
    - VoidCache
    - Agent pool
    """
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return ZQM_AIResponse.ok(
            data={
                "status": "degraded",
                "reason": "orchestrator not initialized",
            },
            message="System status: degraded",
        )

    try:
        health = await orchestrator.get_health(request)
    except Exception as exc:
        log.warning("get_health failed", error=str(exc))
        return ZQM_AIResponse.ok(
            data={
                "status": "degraded",
                "reason": f"health probe failed: {exc}",
            },
            message="System status: degraded",
        )

    log.debug("Health status checked", status=getattr(health, "status", "unknown"))

    try:
        payload = health.model_dump()
    except Exception:
        payload = {
            "status": getattr(health, "status", "unknown"),
            "raw": str(health),
        }

    return ZQM_AIResponse.ok(
        data=payload,
        message=f"System status: {payload.get('status', 'unknown')}",
    )


@router.get(
    "/ping",
    summary="Quick liveness check",
    response_model=dict,
)
async def ping() -> dict:
    """Simple liveness probe — returns immediately without heavy computation."""
    return {
        "status": "ok",
        "zqm_ai_id": settings.zqm_ai_id,
        "message": "The Void is alive",
    }


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    include_in_schema=False,
)
async def prometheus_metrics(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> Response:
    """Prometheus metrics endpoint for scraping."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None or not hasattr(orchestrator, "observability"):
        return Response(
            content="# no orchestrator/observability bound\n",
            media_type="text/plain; version=0.0.4",
        )

    try:
        metrics_bytes = orchestrator.observability.get_prometheus_metrics()
    except Exception as exc:
        log.warning("prometheus_metrics failed", error=str(exc))
        return Response(
            content=f"# metrics collection failed: {exc}\n",
            media_type="text/plain; version=0.0.4",
        )

    return Response(
        content=metrics_bytes,
        media_type="text/plain; version=0.0.4",
    )


@router.get(
    "/history",
    response_model=ZQM_AIResponse,
    summary="Task execution history",
)
async def get_history(
    request: Request,
    limit: int = 50,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return recent task execution history."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return ZQM_AIResponse.ok(
            data=[],
            message="orchestrator not initialized",
        )

    tasks = await orchestrator.get_history(limit=min(limit, 500))
    return ZQM_AIResponse.ok(
        data=[t.model_dump() for t in tasks],
        message=f"{len(tasks)} task(s) in history",
    )
