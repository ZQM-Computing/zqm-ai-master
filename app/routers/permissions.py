"""
The Void AI Orchestration System — /api/permissions Router
Version: 2.0.0 | ZQM Computing LLC

Role-based access control and permission management.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.logger import get_logger
from app.core.security import get_current_token_payload, require_admin
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/permissions", tags=["Permissions"])
log = get_logger("router.permissions")


# ── Permission definitions ────────────────────────────────────────────────────

ROLES: dict[str, dict[str, Any]] = {
    "admin": {
        "name": "Administrator",
        "description": "Full access to all The Void features and settings",
        "permissions": [
            "tasks:read", "tasks:write", "tasks:cancel",
            "agents:read", "agents:write", "agents:delete",
            "users:read", "users:write", "users:delete",
            "settings:read", "settings:write",
            "training:write",
            "cache:flush",
            "mcp:generate",
        ],
    },
    "user": {
        "name": "Standard User",
        "description": "Can submit tasks and view own results",
        "permissions": [
            "tasks:read", "tasks:write",
            "agents:read",
        ],
    },
    "service": {
        "name": "Service Account",
        "description": "Internal ZQM system integration account",
        "permissions": [
            "tasks:read", "tasks:write",
            "agents:read",
            "training:write",
            "mcp:generate",
        ],
    },
    "readonly": {
        "name": "Read-Only Observer",
        "description": "Can only view tasks and agent status",
        "permissions": [
            "tasks:read",
            "agents:read",
        ],
    },
}

PERMISSIONS: dict[str, str] = {
    "tasks:read": "View tasks and results",
    "tasks:write": "Submit and cancel tasks",
    "tasks:cancel": "Cancel in-progress tasks",
    "agents:read": "View agent pool status",
    "agents:write": "Register and configure agents",
    "agents:delete": "Deregister agents",
    "users:read": "View user accounts",
    "users:write": "Create and update users",
    "users:delete": "Delete user accounts",
    "settings:read": "View system settings",
    "settings:write": "Modify runtime settings",
    "training:write": "Submit training data",
    "cache:flush": "Clear VoidCache",
    "mcp:generate": "Generate Machine-Checkable Proofs",
}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=ZQM_AIResponse,
    summary="List all permissions",
)
async def list_permissions(
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return all defined permissions in the The Void RBAC system."""
    perms = [{"id": k, "description": v} for k, v in PERMISSIONS.items()]
    return ZQM_AIResponse.ok(data=perms, message=f"{len(perms)} permissions defined")


@router.get(
    "/roles",
    response_model=ZQM_AIResponse,
    summary="List all roles",
)
async def list_roles(
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return all roles and their associated permissions."""
    roles_out = []
    for role_id, role in ROLES.items():
        roles_out.append({
            "id": role_id,
            "name": role["name"],
            "description": role["description"],
            "permission_count": len(role["permissions"]),
            "permissions": role["permissions"],
        })
    return ZQM_AIResponse.ok(data=roles_out, message=f"{len(roles_out)} roles defined")


@router.get(
    "/roles/{role_id}",
    response_model=ZQM_AIResponse,
    summary="Get role details",
)
async def get_role(
    role_id: str,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return details for a specific role."""
    from fastapi import HTTPException, status
    role = ROLES.get(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_id}' not found. Available: {list(ROLES.keys())}",
        )
    return ZQM_AIResponse.ok(
        data={"id": role_id, **role},
        message=f"Role '{role_id}'",
    )


@router.post(
    "/check",
    response_model=ZQM_AIResponse,
    summary="Check permissions for a user",
)
async def check_permissions(
    request_body: dict[str, Any],
    auth: dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    """
    Check whether given roles grant specific permissions.

    ```json
    {"roles": ["user"], "permissions": ["tasks:write", "settings:write"]}
    ```
    """
    roles: list[str] = request_body.get("roles", [])
    check_perms: list[str] = request_body.get("permissions", [])

    # Collect all granted permissions for given roles
    granted: set = set()
    for role_id in roles:
        role_def = ROLES.get(role_id, {})
        granted.update(role_def.get("permissions", []))

    result = {
        "roles": roles,
        "checked_permissions": {
            perm: perm in granted for perm in check_perms
        },
        "all_granted": all(p in granted for p in check_perms),
        "granted_permissions": list(granted),
    }
    return ZQM_AIResponse.ok(data=result, message="Permission check complete")
