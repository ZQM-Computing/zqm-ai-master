"""
The Void AI Orchestration System — Tenant-Aware Request Middleware
Version: 2.2.0 | ZQM Computing LLC

Adds tenant resolution and branding headers to every response.
"""

from __future__ import annotations

from typing import Dict

from app.branding import branding_layer
from app.tenancy import tenant_resolver


async def tenant_middleware(request, call_next):
    tenant = tenant_resolver.resolve(request)
    request.state.tenant = tenant
    response = await call_next(request)
    try:
        branding_layer.inject_headers(response.headers)
    except Exception:
        pass
    return response
