"""
The Void AI Orchestration System — Multi-Tenant Isolation Layer
Version: 2.2.0 | ZQM Computing LLC

Provides tenant resolution, namespace isolation, and quota enforcement
for Business/Enterprise deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    customer_name: str
    plan: str
    allowed_origins: tuple[str, ...] = ()
    quota_records: int = 1000
    quota_models: int = 5


class TenantResolver:
    """
    Resolve tenant context from request metadata.

    In production, replace with JWT claims, API hostname mapping,
    or an external identity provider.
    """

    def __init__(self) -> None:
        self._default = TenantContext(
            tenant_id="default",
            customer_name=os.getenv("CUSTOMER_NAME", "Customer"),
            plan=os.getenv("CUSTOMER_PLAN", "starter"),
            allowed_origins=tuple(os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []),
            quota_records=int(os.getenv("TENANT_QUOTA_RECORDS", "1000")),
            quota_models=int(os.getenv("TENANT_QUOTA_MODELS", "5")),
        )

    def resolve(self, request: object) -> TenantContext:
        try:
            host = getattr(request, "url", None)
            if host is not None:
                host = getattr(host, "host", None)
            if host:
                mapped = self._map_host(host)
                if mapped:
                    return mapped
        except Exception:
            pass
        return self._default

    def _map_host(self, host: str) -> Optional[TenantContext]:
        mapping = {
            "localhost": self._default,
        }
        return mapping.get(host)


tenant_resolver = TenantResolver()
