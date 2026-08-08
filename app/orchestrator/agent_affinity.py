
"""
The Void — Agent Affinity Dispatcher
Routes agents to their assigned garden nodes via mesh publish/submit.
Wires the declared `garden_node` metadata to actual distributed execution.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger

log = get_logger("agent-affinity")

# Garden node -> backend host/IP mapping (from config)
_GARDEN_NODES = {
    "garden_node_0": "192.168.1.225",
    "garden_node_1": "192.168.1.172",
    "garden_node_2": "192.168.1.38",
    "garden_node_3": "192.168.1.64",
    "garden_node_4": "192.168.1.144",
}

# Node types: compute (runs Void API) vs storage (Synology DSM)
_COMPUTE_NODES = {"garden_node_0"}
_STORAGE_NODES = {"garden_node_1", "garden_node_2", "garden_node_3", "garden_node_4"}


def resolve_node(agent: Any) -> Optional[str]:
    """Resolve an agent's garden_node field to an IP address."""
    gnode = getattr(agent, "garden_node", None)
    if not gnode:
        return None
    return _GARDEN_NODES.get(gnode)


def node_type(agent: Any) -> str:
    gnode = getattr(agent, "garden_node", "")
    if gnode in _COMPUTE_NODES:
        return "compute"
    if gnode in _STORAGE_NODES:
        return "storage"
    return "local"


async def dispatch_agent_task(
    agent: Any,
    task_input: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Dispatch a task to the agent's assigned garden node.
    - Compute nodes: submit via garden_submit (runs on Void API)
    - Storage nodes: store task in FLATSPACE for later retrieval
    - Local fallback: run on N4 directly
    """
    ntype = node_type(agent)
    ip = resolve_node(agent)

    if ntype == "compute" and ip:
        try:
            from app.services.garden_service import GardenService
            gs = GardenService()
            result = await gs.submit_job(
                task_id=f"affinity-{agent.agent_id}-{int(time.time())}",
                task_type="ai_inference",
                payload={"agent_id": agent.agent_id, "input": task_input, "context": context or {}},
                gpu_required=False,
            )
            return {"dispatched": True, "node": ip, "type": ntype, "result": result}
        except Exception as exc:
            log.warning("Affinity dispatch failed, falling back to local", error=str(exc))

    # Storage or fallback: persist to FLATSPACE for retrieval
    try:
        from app.services.flatspace_service import FlatSpaceService
        fs = FlatSpaceService()
        key = f"affinity:{agent.agent_id}:{int(time.time())}"
        await fs.store(
            key=key,
            value={"agent_id": agent.agent_id, "input": task_input, "context": context or {}},
            tier="bitgarden",
            metadata={"node": ip or "local", "type": ntype},
        )
        return {"dispatched": True, "node": ip or "local", "type": ntype, "storage_key": key}
    except Exception as exc:
        return {"dispatched": False, "error": str(exc), "node": "local", "type": ntype}


async def affinity_health() -> Dict[str, Any]:
    """Return affinity mapping status for observability."""
    nodes: Dict[str, Any] = {}
    for key, ip in _GARDEN_NODES.items():
        ntype = "compute" if key in _COMPUTE_NODES else "storage"
        nodes[key] = {"ip": ip, "type": ntype, "reachable": False}
    try:
        from app.services.garden_service import GardenService
        gs = GardenService()
        online = await gs.get_online_nodes()
        for node in online:
            nodes[node.get("node_id", "")] = {**nodes.get(node.get("node_id", ""), {}), "reachable": True}
    except Exception:
        pass
    return {"nodes": nodes, "total": len(nodes)}
