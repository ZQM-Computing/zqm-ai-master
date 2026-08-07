"""
The Void AI Orchestration System — /api/garden Router
Version: 2.1.4 | ZQM Computing LLC

Minimal Garden coordination surface for the ZQM-MESH.
Exposes the endpoints GardenService expects:
  GET  /api/garden/health
  POST /api/garden/coordinate
  GET  /api/garden/jobs/{job_id}
  GET  /api/garden/metrics
  GET  /api/garden/nodes
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logger import get_logger

router = APIRouter(prefix="/api/garden", tags=["Garden"])
log = get_logger("router.garden")

# ── In-memory job store ──────────────────────────────────────────────────────
# In production this would be backed by flatspace or a real queue.
_jobs: Dict[str, Dict[str, Any]] = {}


class CoordinateRequest(BaseModel):
    task_id: str
    task_type: str = "generic"
    payload: Dict[str, Any] = Field(default_factory=dict)
    strategy: str = "round_robin"
    preferred_node: Optional[str] = None
    gpu_required: bool = False
    zqm_ai_id: Optional[str] = None


class CoordinateResponse(BaseModel):
    job_id: str
    status: str
    node: str
    message: str


class NodeInfo(BaseModel):
    id: str
    ip: str
    role: str
    gpu: bool
    queen: str
    status: str = "online"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _garden_nodes() -> List[NodeInfo]:
    nodes = []
    for i, node_ip in enumerate(
        [
            settings.garden_node_0,
            settings.garden_node_1,
            settings.garden_node_2,
            settings.garden_node_3,
            settings.garden_node_4,
        ]
    ):
        if not node_ip:
            continue
        role = "primary" if i == 0 else "worker"
        gpu = i == 0
        queen = "Queen" if i == 0 else f"Queen {10 + i}"
        nodes.append(
            NodeInfo(
                id=f"garden-{i}",
                ip=node_ip,
                role=role,
                gpu=gpu,
                queen=queen,
            )
        )
    return nodes


def _pick_node(req: CoordinateRequest) -> str:
    if req.gpu_required:
        return settings.garden_node_0
    if req.preferred_node:
        for n in _garden_nodes():
            if n.id == req.preferred_node or n.ip == req.preferred_node:
                return n.ip
    return settings.garden_node_0 or "127.0.0.1"


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def garden_health() -> Dict[str, Any]:
    return {
        "service": "garden",
        "zqm_ai_id": settings.zqm_ai_id,
        "status": "ok",
        "nodes": len(_garden_nodes()),
        "uptime_s": int(time.time() - getattr(router, "_start", time.time())),
    }


@router.post("/coordinate", response_model=CoordinateResponse)
async def coordinate(req: CoordinateRequest, request: Request) -> CoordinateResponse:
    zqm_id = req.zqm_ai_id or settings.zqm_ai_id
    node_ip = _pick_node(req)
    job_id = f"g-{int(time.time()*1000)}-{req.task_id}"
    _jobs[job_id] = {
        "task_id": req.task_id,
        "task_type": req.task_type,
        "status": "accepted",
        "node": node_ip,
        "zqm_ai_id": zqm_id,
        "created_at": time.time(),
    }
    log.info(
        "Garden job accepted",
        job_id=job_id,
        task_id=req.task_id,
        node=node_ip,
    )
    return CoordinateResponse(
        job_id=job_id,
        status="accepted",
        node=node_ip,
        message="Job queued to Garden coordinator",
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "unknown", "error": "not found"}
    return {
        "job_id": job_id,
        "task_id": job["task_id"],
        "task_type": job["task_type"],
        "status": job["status"],
        "node": job["node"],
        "zqm_ai_id": job["zqm_ai_id"],
        "created_at": job["created_at"],
    }


@router.get("/metrics")
async def garden_metrics(request: Request) -> Dict[str, Any]:
    orch = getattr(request.app.state, "orchestrator", None)
    agents: List[Dict[str, Any]] = []
    if orch and hasattr(orch, "registry"):
        try:
            registry = orch.registry
            all_agents = registry.list_all()
            try:
                iterator = iter(all_agents)
                first = next(iterator)
                rest = list(iterator)
            except StopIteration:
                first = None
                rest = []
            agents = [
                {
                    "agent_id": a.agent_id,
                    "type": a.agent_type.value,
                    "status": a.status.value,
                    "model": a.model,
                    "provider": a.provider,
                    "garden_node": a.garden_node,
                }
                for a in ([first] + rest)
            ]
        except Exception as exc:
            log.warning("Garden metrics live registry lookup failed", error=str(exc))
            try:
                from app.orchestrator.agent_registry import DEFAULT_AGENTS
                agents = [
                    {
                        "agent_id": a.get("name"),
                        "type": a.get("agent_type"),
                        "status": "configured",
                        "model": a.get("model"),
                        "provider": a.get("provider"),
                        "garden_node": None,
                    }
                    for a in DEFAULT_AGENTS
                ]
            except Exception:
                agents = []
    return {
        "nodes": [n.model_dump() for n in _garden_nodes()],
        "jobs_pending": len(_jobs),
        "agents": agents,
        "agents_source": "live" if agents and agents[0].get("agent_id", "").startswith("agent-") else "default",
    }


@router.get("/nodes")
async def garden_nodes() -> List[NodeInfo]:
    return _garden_nodes()


# ── Lifespan marker ──────────────────────────────────────────────────────────

def _on_startup() -> None:
    router._start = time.time()  # type: ignore[attr-defined]
    log.info("Garden router initialized", nodes=len(_garden_nodes()))
