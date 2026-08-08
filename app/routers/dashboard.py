"""
The Void AI Orchestration System — /api/dashboard Router
Version: 2.0.0 | ZQM Computing LLC

Real-time dashboard statistics and agent management.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.logger import get_logger
from app.core.security import get_current_token_payload, require_admin
from app.models.agent import AgentCreate, AgentUpdate
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Alias: /api/agents -> /api/dashboard/agents
alias_router = APIRouter(prefix="/api", tags=["Agents Alias"])


@alias_router.get(
    "/agents",
    include_in_schema=False,
    summary="Alias for /api/dashboard/agents",
    description="Passes through pagination query params.",
)
async def agents_alias(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    auth: dict[str, Any] = Depends(get_current_token_payload),
):
    return await list_agents(request, auth=auth, page=page, page_size=page_size)
log = get_logger("router.dashboard")


@router.get(
    "",
    response_model=ZQM_AIResponse,
    summary="Real-time dashboard statistics",
)
async def get_dashboard(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """
    Returns comprehensive real-time statistics for the The Void dashboard:
    - Task counts (active, completed, failed, success rate)
    - Agent pool status (idle, busy, offline)
    - Token usage
    - Cache hit rate
    - Garden nodes online
    - System uptime
    """
    orchestrator = request.app.state.orchestrator
    stats = await orchestrator.get_dashboard()
    return ZQM_AIResponse.ok(
        data=stats.model_dump(),
        message="Dashboard data retrieved",
    )


# ── Agent management ──────────────────────────────────────────────────────────

@router.get(
    "/agents",
    response_model=ZQM_AIResponse,
    summary="List all agents with status",
    description="Paginated view of the live agent pool. Use ?page and ?page_size to paginate.",
)
async def list_agents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return paginated agents in the registry with their current status and metrics."""
    from app.models.response import PaginatedResponse
    orchestrator = request.app.state.orchestrator
    summaries = await orchestrator.registry.list_summaries()
    total = len(summaries)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = summaries[start:end]
    payload = PaginatedResponse.of(
        items=[s.model_dump() for s in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return ZQM_AIResponse.ok(
        data=payload.model_dump(),
        message=f"{total} agent(s) registered",
    )


@router.get(
    "/agents/{agent_id}",
    response_model=ZQM_AIResponse,
    summary="Get agent details",
)
async def get_agent(
    agent_id: str,
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return full details for a specific agent including performance metrics."""
    orchestrator = request.app.state.orchestrator
    agent = await orchestrator.registry.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )
    return ZQM_AIResponse.ok(data=agent.model_dump(), message="Agent found")


@router.post(
    "/agents",
    response_model=ZQM_AIResponse,
    summary="Register a new agent",
    status_code=status.HTTP_201_CREATED,
)
async def register_agent(
    agent_data: AgentCreate,
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    """Register a new autonomous agent in the The Void pool."""
    orchestrator = request.app.state.orchestrator
    agent = await orchestrator.registry.register(agent_data)
    log.info("Agent registered via API", agent_id=agent.agent_id, name=agent.name)
    return ZQM_AIResponse.ok(
        data=agent.model_dump(),
        message=f"Agent {agent.name} registered successfully",
    )


@router.patch(
    "/agents/{agent_id}",
    response_model=ZQM_AIResponse,
    summary="Update agent configuration",
)
async def update_agent(
    agent_id: str,
    update: AgentUpdate,
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    """Update an agent's configuration (status, system prompt, limits, etc.)."""
    orchestrator = request.app.state.orchestrator
    agent = await orchestrator.registry.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # Apply updates
    if update.status is not None:
        await orchestrator.registry.set_status(agent_id, update.status)
    if update.system_prompt is not None:
        agent.system_prompt = update.system_prompt
    if update.max_concurrent is not None:
        agent.max_concurrent = update.max_concurrent
    if update.priority_weight is not None:
        agent.priority_weight = update.priority_weight
    if update.provider is not None:
        agent.provider = update.provider
    if update.config is not None:
        agent.config.update(update.config)
    if update.tags is not None:
        agent.tags = update.tags

    return ZQM_AIResponse.ok(data=agent.model_dump(), message="Agent updated")


@router.delete(
    "/agents/{agent_id}",
    response_model=ZQM_AIResponse,
    summary="Deregister an agent",
)
async def deregister_agent(
    agent_id: str,
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    """Remove an agent from the registry."""
    orchestrator = request.app.state.orchestrator
    removed = await orchestrator.registry.deregister(agent_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )
    return ZQM_AIResponse.ok(message=f"Agent {agent_id} deregistered")


# ── Cache management ──────────────────────────────────────────────────────────

@router.get(
    "/cache",
    response_model=ZQM_AIResponse,
    summary="VoidCache statistics",
)
async def get_cache_stats(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return VoidCache performance statistics."""
    orchestrator = request.app.state.orchestrator
    stats = orchestrator.cache.stats()
    return ZQM_AIResponse.ok(data=stats, message="Cache statistics")


@router.delete(
    "/cache",
    response_model=ZQM_AIResponse,
    summary="Flush VoidCache",
)
async def flush_cache(
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> ZQM_AIResponse:
    """Flush all entries from VoidCache (volatile memory only)."""
    orchestrator = request.app.state.orchestrator
    await orchestrator.cache.clear()
    return ZQM_AIResponse.ok(message="VoidCache flushed")


# ── Garden overview ─────────────────────────────────────────────────────────────

@router.get(
    "/garden",
    response_model=ZQM_AIResponse,
    summary="ZQM Garden node status",
)
async def get_garden_status(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return status and metrics for all ZQM Garden nodes."""
    orchestrator = request.app.state.orchestrator
    metrics = await orchestrator.garden.get_node_metrics()
    online = [m["node_id"] for m in metrics if m.get("status") != "offline"]
    return ZQM_AIResponse.ok(
        data={"online_nodes": online, "node_metrics": metrics},
        message=f"{len(online)} of {len(metrics)} Garden nodes online",
    )
