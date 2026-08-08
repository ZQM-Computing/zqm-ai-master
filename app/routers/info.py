"""
The Void AI Orchestration System — /api/info Router
Version: 2.0.0 | ZQM Computing LLC

System identity and capability information.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.security import get_current_token_payload
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/info", tags=["Info"])


@router.get(
    "/agents",
    response_model=ZQM_AIResponse,
    summary="List configured agent roster",
    description="Read-only view of The Void's agent pool (name, model, capabilities, cognitive level). Token-gated.",
)
async def list_agents(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return the live agent registry as configured (no secrets, no internals)."""
    from app.orchestrator.agent_registry import DEFAULT_AGENTS
    agents = [
        {
            "name": a.get("name"),
            "model": a.get("model"),
            "agent_type": a.get("agent_type"),
            "capabilities": a.get("capabilities", []),
            "provider": a.get("provider"),
        }
        for a in DEFAULT_AGENTS
    ]
    return ZQM_AIResponse.ok(
        data={"total": len(agents), "agents": agents},
        message=f"Agent roster: {len(agents)} agents",
    )



@router.get(
    "",
    response_model=ZQM_AIResponse,
    summary="The Void system information",
    description="Returns system identity, capabilities, version, and ecosystem integration info.",
)
async def get_info(request: Request) -> ZQM_AIResponse:
    """
    Returns comprehensive The Void system information:
    - ZQM_AI identity (ID, employee ID, queen, garden)
    - Version and environment
    - Registered capabilities
    - ZQM ecosystem integration status
    - AI provider configuration
    - Cognitive levels available
    """
    from app.core.config import settings as _info_settings
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        try:
            from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator
            orchestrator = ZQM_AIOrchestrator()
            await orchestrator.startup()
            request.app.state.orchestrator = orchestrator
        except Exception as exc:
            return ZQM_AIResponse.ok(
                data={"system": "The Void AI Orchestration System", "note": f"mini-orchestrator bootstrap failed: {exc}"},
                message="System information retrieved successfully",
            )
    info = await orchestrator.get_info()

    # Add extra static info (api_endpoints introspected below)
    eps = []
    for rt in request.app.routes:
        methods = getattr(rt, "methods", None)
        if methods and getattr(rt, "path", "").startswith("/api"):
            eps.append({
                "path": rt.path,
                "method": ",".join(sorted(m for m in methods if m != "HEAD")),
                "description": (rt.summary or rt.description or "").split("\n")[0][:80],
            })
    info.update({
        "system": "The Void AI Orchestration System",
            "author": "ZQM Computing LLC",
            "description": (
                "Central AI orchestration engine for the ZQM ecosystem. "
                "Self-optimizing, multi-agent, cognitive processing platform."
            ),
            "cognitive_levels": {
                "basic": "Single-agent direct response",
                "advanced": "Multi-agent parallel synthesis",
                "neural": "Deep processing with memory (VoidCache + FLATSPACE)",
                "autonomous": "Self-directed execution with learning loop",
            },
            "input_methods": [
                "chat", "map_input", "file_upload", "calculators", "wizards",
                "video_consultation", "api_integrations", "email_parser",
                "sms_service", "qr_code_system", "mobile_field_collection", "direct_api",
            ],
            "ecosystem": {
                "garden": {
                    "description": "ZQM Garden distributed compute cluster",
                    "endpoint": _info_settings.garden_endpoint,
                    "nodes": _info_settings.garden_nodes,
                },
                "flatspace": {
                    "description": "ZQM FLATSPACE 6-tier memory management",
                    "endpoint": _info_settings.flatspace_endpoint,
                    "tiers": ["pollenstore", "bitgarden", "waxcell", "entangle", "quantumcell", "voidcache"],
                },
                "observability": {
                    "description": "ZQM Observability monitoring",
                    "endpoint": _info_settings.observability_endpoint,
                },
                "network": {
                    "description": "ZQM Network infrastructure management",
                    "endpoint": _info_settings.network_endpoint,
                },
            },
            "api_endpoints": eps,
        })

    return ZQM_AIResponse.ok(
        data=info,
        message="System information retrieved successfully",
    )


@router.get(
    "/integration/status",
    response_model=ZQM_AIResponse,
    summary="Integration readiness",
    description="Public view of runtime config for optional ZQM ecosystem integrations.",
)
async def integration_status(request: Request) -> ZQM_AIResponse:
    from app.core.config import settings as _integration_settings

    try:
        eps = []
        for rt in request.app.routes:
            path = getattr(rt, "path", "")
            methods = getattr(rt, "methods", None)
            if methods and path.startswith("/api"):
                methods_clean = ",".join(sorted(m for m in methods if m != "HEAD"))
                summary = (rt.summary or rt.description or "").split("\n")[0][:80]
                eps.append({"path": path, "method": methods_clean, "summary": summary})
    except Exception:
        eps = []

    base_payload = {
        "ready": True,
        "mounts": eps,
        "endpoints": {
            "garden": _integration_settings.garden_endpoint,
            "flatspace": _integration_settings.flatspace_endpoint,
            "observability": _integration_settings.observability_endpoint,
            "network": _integration_settings.network_endpoint,
            "intel_platforms": _integration_settings.zqm_intel_platforms_url,
            "redis": _integration_settings.redis_url,
        },
        "settings": {
            "version": _integration_settings.app_version,
            "host": _integration_settings.host,
            "port": _integration_settings.port,
        },
    }
    return ZQM_AIResponse.ok(
        data=base_payload,
        message="Integration status retrieved successfully",
    )
