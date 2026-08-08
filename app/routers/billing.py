"""
The Void AI Orchestration System — Billing Router
Version: 2.2.0 | ZQM Computing LLC

Exposes billing/subscription endpoints for commercial tenants.
Wraps app.billing.BillingGateway; adapter is configured via BILLING_ADAPTER.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.billing import BillingGateway, SubscriptionStatus, UsageEvent
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/billing", tags=["Billing"])


def _gw() -> BillingGateway:
    return BillingGateway()


@router.get("/summary")
async def billing_summary(auth: Dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    g = _gw()
    return JSONResponse(g.summary())


@router.get("/subscription/{customer_id}")
async def get_subscription(customer_id: str, auth: Dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    g = _gw()
    sub = g.get_subscription(customer_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return JSONResponse({
        "customer_id": sub.customer_id,
        "plan": sub.plan,
        "status": sub.status.value,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "seats": sub.seats,
        "metadata": sub.metadata,
    })


@router.post("/subscription/{customer_id}/trial")
async def create_trial(
    customer_id: str,
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    body = await request.json()
    plan = body.get("plan", "starter")
    days = int(body.get("days", 14))
    g = _gw()
    sub = g.create_trial(customer_id=customer_id, plan=plan, days=days)
    return JSONResponse({
        "customer_id": sub.customer_id,
        "plan": sub.plan,
        "status": sub.status.value,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "seats": sub.seats,
    })


@router.post("/usage")
async def record_usage(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    body = await request.json()
    event = UsageEvent(
        customer_id=body.get("customer_id", ""),
        event_type=body.get("event_type", "api_call"),
        quantity=int(body.get("quantity", 1)),
        unit=body.get("unit", "event"),
        properties=body.get("properties", {}),
    )
    g = _gw()
    g.record_usage(event)
    return JSONResponse({"recorded": True, "event": event.event_type, "quantity": event.quantity})
