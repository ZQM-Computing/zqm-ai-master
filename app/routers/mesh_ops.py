"""
The Void AI Orchestration System — Mesh Operations Router
Version: 2.0.0 | ZQM Computing LLC

Exposes mesh-wide node/garden operations endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.garden_service import GardenService
from app.services.mesh_node_ops import MeshNodeOperations
from app.services.synology_service import SynologyService

router = APIRouter()

_garden = GardenService()
_node_ops = MeshNodeOperations(garden=_garden)
_synology = SynologyService()


@router.get("/api/mesh/nodes/health")
async def mesh_nodes_health() -> Dict[str, Any]:
    """Return health snapshot for all configured mesh/garden nodes."""
    try:
        snapshot = await _node_ops.get_node_health_snapshot()
        return {
            "count": len(snapshot),
            "nodes": snapshot,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/mesh/nodes/metrics")
async def mesh_nodes_metrics() -> Dict[str, Any]:
    """Aggregate metrics across all mesh/garden nodes."""
    try:
        return await _node_ops.collect_node_metrics()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/mesh/nodes/best")
async def mesh_best_node(gpu_required: bool = False) -> Dict[str, Any]:
    """Select the best available node by health + capability."""
    try:
        node = await _node_ops.select_best_node(gpu_required=gpu_required)
        if not node:
            raise HTTPException(status_code=503, detail="no healthy node available")
        return {
            "id": node.get("id"),
            "ip": node.get("ip"),
            "role": node.get("role"),
            "gpu": node.get("gpu", False),
            "queen": node.get("queen"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/mesh/nodes/promote")
async def mesh_promote_backup() -> Dict[str, Any]:
    """If primary is unhealthy, reroute coordination to a healthy backup."""
    try:
        result = await _node_ops.promote_backup_if_needed()
        if not result:
            raise HTTPException(status_code=503, detail="no nodes configured")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/mesh/synology/info")
async def mesh_synology_info() -> Dict[str, Any]:
    """Return DSM/system info for the Synology Garden fleet."""
    try:
        info = await _synology.get_node_system_info()
        return {
            "count": len(info),
            "nodes": info,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
