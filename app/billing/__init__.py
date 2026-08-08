"""
The Void AI Orchestration System — Billing and Subscription Gateway
Version: 2.2.0 | ZQM Computing LLC

Provides subscription lifecycle, metered usage events, and adapter stubs
for billing providers. This module is intentionally provider-agnostic;
integration is configured via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class Subscription:
    customer_id: str
    plan: str
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    seats: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageEvent:
    customer_id: str
    event_type: str
    quantity: int = 1
    unit: str = "event"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    properties: dict[str, Any] = field(default_factory=dict)


class BillingGateway:
    """
    Minimal billing gateway for The Void commercial edition.

    This implementation stores state in-process for demonstration and
    single-node deployment. Multi-tenant SaaS deployments should replace
    storage with a durable backing store.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._events: list[UsageEvent] = []
        self._adapter = os.getenv("BILLING_ADAPTER", "stub").lower()

    def create_trial(self, customer_id: str, plan: str = "starter", days: int = 14) -> Subscription:
        now = datetime.now(UTC)
        sub = Subscription(
            customer_id=customer_id,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            trial_ends_at=now.replace(second=0, microsecond=0),
            current_period_end=now.replace(second=0, microsecond=0),
        )
        if days:
            from datetime import timedelta
            sub.trial_ends_at = now + timedelta(days=days)
        self._subscriptions[customer_id] = sub
        return sub

    def get_subscription(self, customer_id: str) -> Subscription | None:
        return self._subscriptions.get(customer_id)

    def record_usage(self, event: UsageEvent) -> None:
        self._events.append(event)
        if self._adapter == "stub":
            return
        raise NotImplementedError(f"Billing adapter '{self._adapter}' is not implemented in this build.")

    def summary(self) -> dict[str, Any]:
        return {
            "adapter": self._adapter,
            "subscriptions": len(self._subscriptions),
            "events": len(self._events),
            "plans": sorted({s.plan for s in self._subscriptions.values()}),
        }


# Global gateway instance
billing_gateway = BillingGateway()
