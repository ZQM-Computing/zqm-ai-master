"""
The Void AI Orchestration System — Support and Observability Endpoints
Version: 2.2.0 | ZQM Computing LLC

Provides status, metrics, support ticket creation, and onboarding info
for customer deployments.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/support", tags=["Support"])


@router.get("/status")
async def support_status() -> JSONResponse:
    return JSONResponse({
        "product": os.getenv("BRAND_PRODUCT_NAME", "The Void AI Orchestration System"),
        "support_email": os.getenv("BRAND_SUPPORT_EMAIL", "zqmcomputing@gmail.com"),
        "docs_url": os.getenv("BRAND_PORTAL_URL", "http://localhost:8808/docs"),
    })


@router.get("/metrics")
async def support_metrics(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    metrics: Dict[str, Any] = {"uptime_seconds": None}
    if orch is not None:
        try:
            metrics["orchestrator"] = bool(orch)
            metrics["flatspace"] = bool(await orch.flatspace.health_check() if hasattr(orch, "flatspace") else None)
        except Exception:
            metrics["flatspace"] = False
    return JSONResponse(metrics)


@router.post("/ticket")
async def support_ticket(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
    body: Dict[str, Any] = None,
) -> JSONResponse:
    payload = body or {}
    ticket = {
        "customer_id": auth.get("sub"),
        "subject": payload.get("subject", ""),
        "detail": payload.get("detail", ""),
        "received_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    return JSONResponse({"status": "accepted", "ticket": ticket})
