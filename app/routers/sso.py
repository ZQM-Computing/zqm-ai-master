"""
The Void AI Orchestration System — SSO/OIDC Router

Azure AD OIDC integration for commercial tenant logins.
Falls back to local JWT when SSO is not enabled.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.logger import get_logger
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/auth/sso", tags=["SSO"])
log = get_logger("router.sso")


@router.get("/status")
async def sso_status() -> JSONResponse:
    """Report whether OIDC/SSO is configured."""
    enabled = bool(
        os.getenv("SSO_OIDC_ISSUER")
        and os.getenv("SSO_OIDC_CLIENT_ID")
        and os.getenv("SSO_OIDC_SECRET")
        and os.getenv("SSO_OIDC_REDIRECT_URI")
    )
    return JSONResponse({
        "enabled": enabled,
        "oidc_issuer": os.getenv("SSO_OIDC_ISSUER", ""),
        "provider": os.getenv("SSO_PROVIDER", "azure_ad"),
        "redirect_uri": os.getenv("SSO_OIDC_REDIRECT_URI", ""),
    })


@router.get("/authorize")
async def sso_authorize() -> JSONResponse:
    """Return the Azure AD authorization URL for frontend redirect."""
    issuer = os.getenv("SSO_OIDC_ISSUER", "")
    client_id = os.getenv("SSO_OIDC_CLIENT_ID", "")
    redirect_uri = os.getenv("SSO_OIDC_REDIRECT_URI", "")
    tenant = os.getenv("SSO_OIDC_TENANT", "common")

    if not all([issuer, client_id, redirect_uri]):
        raise HTTPException(status_code=501, detail="SSO not configured")

    auth_url = (
        f"{issuer}/oauth2/v2.0/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&response_mode=query"
        f"&scope=openid+profile+email+offline_access"
        f"&state=zqm_void"
    )
    return JSONResponse({"authorization_url": auth_url})


@router.post("/login")
async def sso_login(request: Request) -> JSONResponse:
    """
    Exchange an upstream OIDC authorization code for a local ZQM access token.
    Expects JSON: {"code": "...", "redirect_uri": "..."}
    """
    issuer = os.getenv("SSO_OIDC_ISSUER", "")
    client_id = os.getenv("SSO_OIDC_CLIENT_ID", "")
    client_secret = os.getenv("SSO_OIDC_SECRET", "")
    redirect_uri = os.getenv("SSO_OIDC_REDIRECT_URI", "")

    if not all([issuer, client_id, client_secret, redirect_uri]):
        return JSONResponse({
            "error": "SSO not configured",
            "detail": "Set SSO_OIDC_ISSUER, SSO_OIDC_CLIENT_ID, SSO_OIDC_SECRET, SSO_OIDC_REDIRECT_URI",
        }, status_code=501)

    body = await request.json()
    code = body.get("code")
    req_redirect_uri = body.get("redirect_uri", redirect_uri)

    if not code:
        raise HTTPException(status_code=400, detail="code is required")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Exchange authorization code for tokens
            token_resp = await client.post(
                f"{issuer}/oauth2/v2.0/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": req_redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "openid profile email",
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            # Fetch user profile
            user_resp = await client.get(
                f"{issuer}/oauth2/v2.0/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            user_resp.raise_for_status()
            user = user_resp.json()

        # Issue local ZQM JWT
        from app.routers.users import create_access_token
        zqm_token = create_access_token({
            "sub": user.get("sub", user.get("email")),
            "username": user.get("preferred_username", user.get("email")),
            "email": user.get("email"),
            "type": "sso",
            "roles": ["user"],
            "service": os.getenv("SSO_PROVIDER", "azure_ad"),
        })
        return JSONResponse({"access_token": zqm_token, "token_type": "bearer"})
    except httpx.HTTPStatusError as exc:
        log.error("SSO token exchange failed", status=exc.response.status_code, body=exc.response.text[:200])
        raise HTTPException(status_code=502, detail="SSO provider rejected token exchange")
    except Exception as exc:
        log.error("SSO login failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"SSO provider error: {exc}")


@router.get("/me")
async def sso_me(auth: dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
    """Return current user identity, normalizing SSO and local tokens."""
    user_id = auth.get("sub")
    username = auth.get("username")
    email = auth.get("email")
    return JSONResponse({
        "user_id": user_id,
        "sub": user_id,
        "type": auth.get("type", "user"),
        "username": username,
        "email": email,
        "roles": auth.get("roles", []),
        "service": auth.get("service"),
        "auth_source": auth.get("type", "local"),
    })
