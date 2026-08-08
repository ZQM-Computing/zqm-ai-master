"""
The Void AI Orchestration System — Security & Authentication
Version: 2.0.0 | ZQM Computing LLC

JWT-based authentication with role-based access control.
Supports: Bearer tokens, API keys, service-to-service tokens.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("security")

# ── Password hashing ──────────────────────────────────────────────────────────
# Note: Using bcrypt directly instead of passlib (passlib 1.7.4 is incompatible with bcrypt 4.x/5.x)

# ── HTTP security schemes ─────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Built-in service API keys (for internal ZQM system calls) ─────────────────
# Each internal service must have its OWN independent secret stored in the
# environment (ZQM Eden / .env).  We NEVER derive service keys by
# slicing the user-facing JWT secret — that leaks the master secret if any
# service key is ever exposed.
import os as _os

def _load_service_key(env_var: str, fallback_name: str) -> str:
    """Load a service key from env; generate a stable fallback for dev only."""
    val = _os.environ.get(env_var, "")
    if val:
        return val
    # Dev-mode fallback: derive a HMAC of the secret with a fixed label so
    # different services still get different, non-overlapping keys.
    import hmac, hashlib
    return hmac.new(
        settings.secret_key.encode(),
        fallback_name.encode(),
        hashlib.sha256,
    ).hexdigest()

INTERNAL_SERVICE_KEYS: Dict[str, str] = {
    "ZQM-GARDEN":          _load_service_key("ZQM_GARDEN_SERVICE_KEY",          "zqm-garden"),
    "ZQM-FLATSPACE":          _load_service_key("ZQM_FLATSPACE_SERVICE_KEY",          "zqm-flatspace"),
    "ZQM-OBSERVABILITY": _load_service_key("ZQM_OBSERVABILITY_SERVICE_KEY", "zqm-observability"),
}


# ── JWT utilities ─────────────────────────────────────────────────────────────

def create_access_token(
    subject: str | Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: User ID or dict of claims to encode as `sub`
        expires_delta: Custom expiry (defaults to settings value)
        extra_claims: Additional claims to embed in the token

    Returns:
        Encoded JWT string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload: Dict[str, Any] = {
        "sub": str(subject) if not isinstance(subject, dict) else None,
        "iat": now,
        "exp": expire,
        "zqm_ai_id": settings.zqm_ai_id,
        "iss": settings.jwt_issuer or "zqm-void",
        "aud": settings.jwt_audience or "zqm-void",
    }

    typed = (subject.get("type") if isinstance(subject, dict) else None) or "local"
    payload.setdefault("type", typed)

    if isinstance(subject, dict):
        payload.update(subject)

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises:
        HTTPException(401) if token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError as exc:
        log.warning("JWT decode failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_service_token(service_name: str, ttl_hours: int = 24) -> str:
    """Create a long-lived service-to-service JWT."""
    return create_access_token(
        subject={"sub": service_name, "type": "service", "service": service_name},
        expires_delta=timedelta(hours=ttl_hours),
    )


# ── Password utilities ────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt directly (passlib-free)."""
    import bcrypt
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash directly (passlib-free)."""
    import bcrypt
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return f"zqm_{secrets.token_urlsafe(32)}"


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> Dict[str, Any]:
    """
    FastAPI dependency: extract & validate auth from Bearer token or API key.

    Returns decoded token payload dict.
    """
    # Try Bearer JWT first
    if credentials and credentials.scheme.lower() == "bearer":
        return decode_token(credentials.credentials)

    # Check API key
    if api_key:
        # Check internal service keys
        for service, key in INTERNAL_SERVICE_KEYS.items():
            if secrets.compare_digest(api_key, key):
                return {"sub": service, "type": "service", "service": service}

        # Check user-scoped API keys (stored as bcrypt hashes).
        from app.routers.users import _users

        for user in _users.values():
            if user.api_key_hash and verify_password(api_key, user.api_key_hash):
                return {
                    "sub": user.user_id,
                    "username": user.username,
                    "roles": user.roles,
                    "type": "user",
                }

        # Check if it looks like a ZQM API key (zqm_<token>)
        if api_key.startswith("zqm_"):
            # In production: validate against DB/Eden
            # For now, decode as JWT if applicable
            try:
                return decode_token(api_key[4:])
            except HTTPException:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    payload: Dict[str, Any] = Depends(get_current_token_payload),
) -> Dict[str, Any]:
    """Dependency: returns current authenticated user/service info."""
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )
    return payload


async def require_admin(
    payload: Dict[str, Any] = Depends(get_current_token_payload),
) -> Dict[str, Any]:
    """Dependency: requires admin role in token."""
    roles = payload.get("roles", [])
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return payload


# ── Optional auth (returns None if not provided) ──────────────────────────────

async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[Dict[str, Any]]:
    """Dependency: returns token payload OR None — does not raise on missing auth."""
    try:
        return await get_current_token_payload(credentials, api_key)
    except HTTPException:
        return None
