"""
The Void AI Orchestration System — /api/status Router
Version: 2.0.0 | ZQM Computing LLC

System health and status endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.logger import get_logger
from app.core.security import get_current_token_payload
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/status", tags=["Status"])
log = get_logger("router.status")


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
    orchestrator = request.app.state.orchestrator
    health = await orchestrator.get_health()

    log.debug("Health status checked", status=health.status)

    return ZQM_AIResponse.ok(
        data=health.model_dump(),
        message=f"System status: {health.status}",
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
        "zqm_ai_id": "ZQM-ZQM_AI-001",
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
    orchestrator = request.app.state.orchestrator
    metrics_bytes = orchestrator.observability.get_prometheus_metrics()
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
    orchestrator = request.app.state.orchestrator
    tasks = await orchestrator.get_history(limit=min(limit, 500))
    return ZQM_AIResponse.ok(
        data=[t.model_dump() for t in tasks],
        message=f"{len(tasks)} task(s) in history",
    )
