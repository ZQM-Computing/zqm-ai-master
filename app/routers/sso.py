"""
The Void AI Orchestration System — SSO/OIDC Router

Minimal OIDC-aware auth surface for commercial tenant logins.
Falls back to local JWT when Eden/OIDC is not enabled.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/auth/sso", tags=["SSO"])
log = get_logger("router.sso")


@router.get("/status")
async def sso_status() -> JSONResponse:
    """Report whether OIDC/SSO is configured."""
    enabled = bool(
        settings.eden_enabled
        and settings.eden_endpoint
        and os.getenv("SSO_OIDC_ISSUER")
    )
    return JSONResponse({
        "enabled": enabled,
        "eden_endpoint": settings.eden_endpoint,
        "oidc_issuer": os.getenv("SSO_OIDC_ISSUER", ""),
        "provider": os.getenv("SSO_PROVIDER", ""),
    })


@router.post("/login")
async def sso_login(request: Request) -> JSONResponse:
    """
    Exchange an upstream OIDC identity for a local ZQM access token.

    Expects JSON: {"code": "...", "redirect_uri": "..."}
    Returns ZQM JWT when Eden/OIDC is enabled; otherwise 501.
    """
    if not settings.eden_enabled or not os.getenv("SSO_OIDC_ISSUER"):
        return JSONResponse({
            "error": "SSO not configured",
            "detail": "Set SSO_OIDC_ISSUER and enable eden_enabled",
        }, status_code=501)

    body = await request.json()
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri are required")

    # TODO: perform OIDC token exchange against SSO_OIDC_ISSUER
    return JSONResponse({
        "error": "not_implemented",
        "detail": "OIDC token exchange not yet wired",
    }, status_code=501)


@router.get("/me")
async def sso_me(auth: Dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    """Return current user identity, normalizing SSO and local tokens."""
    return JSONResponse({
        "sub": auth.get("sub"),
        "type": auth.get("type", "user"),
        "username": auth.get("username"),
        "roles": auth.get("roles", []),
        "service": auth.get("service"),
    })
