"""
The Void AI Orchestration System — /api/observability Router
Version: 2.2.0 | ZQM Computing LLC

Prometheus metrics exposition + observability health.
/metrics is unauthenticated for scrape targets; all other endpoints require auth.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.core.logger import get_logger

router = APIRouter(prefix="/api/observability", tags=["Observability"])
log = get_logger("router.observability")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_call(coro):
    """Run an async callable and return a tuple(bool, value)."""
    try:
        import asyncio

        return True, asyncio.get_event_loop().run_until_complete(coro())
    except Exception as exc:
        log.debug("observability dependency check failed", error=str(exc))
        return False, str(exc)


@router.get(
    "/health",
    summary="Observability service health",
)
async def observability_health(request: Request) -> Dict[str, Any]:
    """Quick health check for the observability pipeline."""
    orch = getattr(request.app.state, "orchestrator", None)
    deps: Dict[str, Any] = {
        "orchestrator": orch is not None,
        "observability_service": False,
        "prometheus_client": False,
    }

    prometheus_available = False
    try:
        from prometheus_client import CollectorRegistry, generate_latest  # noqa: F401

        prometheus_available = True
    except Exception:
        pass
    deps["prometheus_client"] = prometheus_available

    if orch is None:
        return {
            "status": "degraded",
            "dependencies": deps,
            "endpoint": None,
            "enabled": False,
        }

    obs = getattr(orch, "observability", None)
    if obs is None:
        return {
            "status": "degraded",
            "dependencies": deps,
            "endpoint": None,
            "enabled": False,
        }

    deps["observability_service"] = True
    ok = False
    try:
        ok = bool(await obs.health_check())
    except Exception as exc:
        log.debug("observability health check failed", error=str(exc))

    # Best-effort dependency health from the orchestrator itself.
    dependency_health = {}
    try:
        # Prefer explicit method if available.
        if hasattr(orch, "get_dependency_health"):
            dependency_health = await orch.get_dependency_health()  # type: ignore[attr-defined]
        elif hasattr(orch, "health_report"):
            dependency_health = await orch.health_report()  # type: ignore[attr-defined]
    except Exception:
        pass

    deps["dependency_health"] = dependency_health

    endpoint = getattr(obs, "_endpoint", None)
    enabled = getattr(obs, "_enabled", False)
    return {
        "status": "ok" if ok else "unreachable",
        "dependencies": deps,
        "endpoint": endpoint,
        "enabled": enabled,
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
    orch = getattr(request.app.state, "orchestrator", None)

    # 1) Preferred: existing observability_service metrics, if available.
    metrics_bytes = b""
    if orch is not None:
        obs = getattr(orch, "observability", None)
        if obs is not None:
            try:
                getter = getattr(obs, "get_prometheus_metrics", None)
                if callable(getter):
                    metrics_bytes = getter() or b""
            except Exception as exc:
                log.debug("metrics endpoint error", error=str(exc))
                metrics_bytes = b""

    # 2) Fallback: synthesize metrics from dependency health when the service
    #    path is unavailable or returned nothing.
    if not metrics_bytes:
        try:
            dependency_health = {}
            if orch is not None:
                if hasattr(orch, "get_dependency_health"):
                    dependency_health = await orch.get_dependency_health()  # type: ignore[attr-defined]
                elif hasattr(orch, "health_report"):
                    dependency_health = await orch.health_report()  # type: ignore[attr-defined]

            deps = dependency_health.get("dependencies", {}) if isinstance(dependency_health, dict) else {}
            ts = int(time.time())
            up = int(all(v is True for v in deps.values()))

            lines = [
                "# HELP zqm_ai_up 1 if all known dependencies are healthy",
                "# TYPE zqm_ai_up gauge",
                f"zqm_ai_up {up}",
                "",
                "# HELP zqm_ai_dependency_up 1 if dependency health check passed",
                "# TYPE zqm_ai_dependency_up gauge",
            ]
            for name, value in deps.items():
                lines.append(f'zqm_ai_dependency_up{{dependency="{name}"}} {int(bool(value))}')

            lines.extend([
                "",
                "# HELP zqm_ai_scrape_timestamp_seconds Unix timestamp of last scrape",
                "# TYPE zqm_ai_scrape_timestamp_seconds gauge",
                f"zqm_ai_scrape_timestamp_seconds {ts}",
                "",
            ])
            metrics_bytes = ("\n".join(lines)).encode("utf-8")
        except Exception as exc:
            log.debug("fallback metrics generation failed", error=str(exc))
            metrics_bytes = b"# metrics unavailable\n"

    if not metrics_bytes:
        metrics_bytes = b"# No metrics collected yet\n"

    return Response(
        content=metrics_bytes,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
