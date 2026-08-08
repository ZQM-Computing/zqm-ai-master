
"""
The Void AI Orchestration System — Support Router
Ticket creation and status for commercial customers.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.logger import get_logger
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/support", tags=["Support"])
log = get_logger("router.support")


@router.get("/status")
async def support_status() -> JSONResponse:
    """Support system status and contact info."""
    return JSONResponse({
        "product": os.getenv("BRAND_PRODUCT_NAME", "The Void AI Orchestration System"),
        "support_email": os.getenv("BRAND_SUPPORT_EMAIL", "zqmcomputing@gmail.com"),
        "docs_url": os.getenv("BRAND_PORTAL_URL", "http://localhost:8808/docs"),
        "status": "operational",
        "timestamp": datetime.now(UTC).isoformat(),
    })


@router.get("/metrics")
async def support_metrics(auth: dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    """Support ticket volume and resolution metrics."""
    try:
        from app.services.flatspace_service import FlatSpaceService
        fs = FlatSpaceService()
        tickets = await fs.list_keys("support_ticket:", tier="waxcell", limit=1000)
        total = len(tickets)
        open_tickets = sum(1 for t in tickets if t.get("value", {}).get("status") == "open")
        return JSONResponse({
            "total_tickets": total,
            "open": open_tickets,
            "resolved": total - open_tickets,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc), "total_tickets": 0, "open": 0})


@router.post("/ticket")
async def create_ticket(request: Request, auth: dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    """
    Create a support ticket.
    Body: {"subject": "...", "priority": "low|medium|high|critical", "body": "..."}
    """
    body = await request.json()
    subject = body.get("subject", "")
    priority = body.get("priority", "medium")
    body_text = body.get("body", "")

    if not subject or not body_text:
        raise HTTPException(status_code=400, detail="subject and body are required")

    ticket_id = f"support-{int(datetime.now(UTC).timestamp())}"
    ticket = {
        "ticket_id": ticket_id,
        "subject": subject,
        "priority": priority,
        "body": body_text,
        "status": "open",
        "created_by": auth.get("username", "unknown"),
        "created_at": datetime.now(UTC).isoformat(),
    }

    try:
        from app.services.flatspace_service import FlatSpaceService
        fs = FlatSpaceService()
        await fs.store(
            key=f"support_ticket:{ticket_id}",
            value=ticket,
            tier="waxcell",
            metadata={"type": "support_ticket", "priority": priority},
        )
    except Exception as exc:
        log.warning("Support ticket persistence failed", error=str(exc))

    log.info("Support ticket created", ticket_id=ticket_id, priority=priority)
    return JSONResponse(ticket, status_code=201)
