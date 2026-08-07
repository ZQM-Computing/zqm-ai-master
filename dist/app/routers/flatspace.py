"""
The Void AI Orchestration System — /api/flatspace Router
Version: 2.1.0 | ZQM Computing LLC

Exposes the ZQM FLATSPACE tiered memory store as a REST API so external
tools/agents can read/write The Void's long-term memory. The underlying
FlatSpaceService already handles remote→local SQLite failover; this router
just makes it reachable over HTTP (search/retrieve/stats are token-gated;
store/delete are admin-gated to avoid memory pollution).

Wired to the orchestrator's singleton at request.app.state.orchestrator.flatspace.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.core.security import get_current_token_payload, require_admin
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/flatspace", tags=["FLATSPACE"])


def _fs(request: Request):
    return request.app.state.orchestrator.flatspace


@router.post(
    "/store",
    summary="Store a memory record",
    description="Write a value into a FLATSPACE tier. Admin-gated.",
)
async def store(
    request: Request,
    body: Dict[str, Any],
    auth: Dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    fs = _fs(request)
    key = body.get("key")
    if not key:
        return ZQM_AIResponse.ok(data={"success": False}, message="missing 'key'")
    result = await fs.store(
        key=key,
        value=body.get("value"),
        tier=body.get("tier", "bitgarden"),
        ttl=body.get("ttl"),
        metadata=body.get("metadata"),
    )
    return ZQM_AIResponse.ok(data=result, message=f"Stored '{key}'")


@router.post(
    "/search",
    summary="Search memory",
    description="Semantic/key search across a FLATSPACE tier. Token-gated.",
)
async def search(
    request: Request,
    body: Dict[str, Any],
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    fs = _fs(request)
    results = await fs.search(
        query=body.get("query", ""),
        tier=body.get("tier", "bitgarden"),
        limit=int(body.get("limit", 10)),
    )
    return ZQM_AIResponse.ok(
        data={"count": len(results), "results": results},
        message="Search complete",
    )


@router.get(
    "/retrieve/{key}",
    summary="Retrieve a memory record",
    description="Fetch one key from a tier. Token-gated.",
)
async def retrieve(
    key: str,
    request: Request,
    tier: str = "bitgarden",
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    fs = _fs(request)
    value = await fs.retrieve(key, tier=tier)
    if value is None:
        return ZQM_AIResponse.ok(data={"found": False, "key": key}, message="Not found")
    return ZQM_AIResponse.ok(data={"found": True, "key": key, "value": value}, message="Retrieved")


@router.delete(
    "/delete/{key}",
    summary="Delete a memory record",
    description="Remove a key from a tier. Admin-gated.",
)
async def delete(
    key: str,
    request: Request,
    tier: str = "bitgarden",
    auth: Dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    fs = _fs(request)
    ok = await fs.delete(key, tier=tier)
    return ZQM_AIResponse.ok(data={"deleted": ok, "key": key}, message="Delete complete")


@router.get(
    "/stats",
    summary="FLATSPACE tier statistics",
    description="Usage stats across memory tiers. Token-gated.",
)
async def stats(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    fs = _fs(request)
    data = await fs.get_tier_stats()
    return ZQM_AIResponse.ok(data=data, message="Tier stats")
