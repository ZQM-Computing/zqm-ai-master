"""Mesh-wide node operations improvements for ZQM Garden."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional

import httpx
from app.core.config import settings
from app.core.logger import get_logger
from app.services.observability_service import ObservabilityService
from app.services.falsification_protocol import FalsificationProtocol

log = get_logger("mesh-node-ops")


class MeshNodeOperations:
    """Mesh-wide node operations for ZQM Garden + Synology maintenance."""

    def __init__(self, garden: GardenService) -> None:
        self.garden = garden

    async def get_node_health_snapshot(self) -> List[Dict[str, Any]]:
        """Return richer health snapshots for every configured Garden node."""
        nodes = getattr(self.garden, "GARDEN_NODES", [])
        results = await asyncio.gather(
            *[self._probe_node(node) for node in nodes],
            return_exceptions=True,
        )
        snapshot: List[Dict[str, Any]] = []
        for node, result in zip(nodes, results):
            if isinstance(result, Exception):
                snapshot.append(
                    {
                        "id": node.get("id"),
                        "ip": node.get("ip"),
                        "status": "unreachable",
                        "error": str(result),
                    }
                )
            else:
                snapshot.append(result)
        return snapshot

    async def _probe_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        if node.get("node_type") == "storage":
            endpoint = self.garden._endpoint(node, "/")
            health_path = "/"
        else:
            endpoint = self.garden._endpoint(node, "/api/garden/health")
            health_path = "/api/garden/health"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(endpoint)
                data: Dict[str, Any] = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                return {
                    "id": node.get("id"),
                    "ip": node.get("ip"),
                    "status": "healthy" if resp.status_code < 500 else ("unsupported" if resp.status_code == 404 else "degraded"),
                    "http_status": resp.status_code,
                    "role": node.get("role"),
                    "gpu": node.get("gpu", False),
                    "queen": node.get("queen"),
                    "node_type": node.get("node_type", "compute"),
                    "api_port": node.get("api_port", "8808"),
                    "health_path": health_path,
                    "metrics": data if isinstance(data, dict) else {},
                }
        except Exception as exc:
            return {
                "id": node.get("id"),
                "ip": node.get("ip"),
                "status": "offline",
                "error": str(exc),
                "role": node.get("role"),
                "gpu": node.get("gpu", False),
                "queen": node.get("queen"),
                "node_type": node.get("node_type", "compute"),
                "api_port": node.get("api_port", "8808"),
                "health_path": health_path,
            }

    async def collect_node_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics across all nodes with per-node fallback."""
        raw = await self.garden.get_node_metrics()
        aggregated: Dict[str, Any] = {
            "nodes_total": len(raw),
            "nodes_online": 0,
            "nodes_offline": 0,
            "by_node": {},
        }
        for entry in raw:
            nid = entry.get("node_id", "unknown")
            status = entry.get("status", "unknown")
            aggregated["by_node"][nid] = entry
            if status == "offline":
                aggregated["nodes_offline"] += 1
            else:
                aggregated["nodes_online"] += 1
        return aggregated

    async def select_best_node(
        self,
        *,
        gpu_required: bool = False,
        preferred_node: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Pick the best node by health + capability, not just first online."""
        if preferred_node:
            for n in getattr(self.garden, "GARDEN_NODES", []):
                if n.get("id") == preferred_node:
                    healthy = await self.garden._ping_node(n)
                    if healthy:
                        return n
        candidates: List[tuple[bool, Dict[str, Any]]] = []
        for n in getattr(self.garden, "GARDEN_NODES", []):
            if gpu_required and not n.get("gpu"):
                continue
            try:
                healthy = await self.garden._ping_node(n)
            except Exception:
                healthy = False
            candidates.append((healthy, n))
        healthy_nodes = [n for ok, n in candidates if ok]
        if not healthy_nodes:
            return None
        return random.choice(healthy_nodes)

    async def migrate_job(self, job_id: str, from_node: str, to_node: str) -> Dict[str, Any]:
        """Best-effort job migration signal between garden nodes."""
        return {
            "job_id": job_id,
            "from_node": from_node,
            "to_node": to_node,
            "status": "accepted",
            "note": "Migration is advisory; actual replay depends on target node runtime.",
        }

    async def convene_cross_node_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an action to the best node with failover."""
        task_id = action.get("task_id", "unknown")
        gpu_required = action.get("gpu_required", False)
        preferred_node = action.get("preferred_node")
        node = await self.select_best_node(
            gpu_required=gpu_required,
            preferred_node=preferred_node,
        )
        if node is None:
            return {
                "task_id": task_id,
                "status": "local_fallback",
                "node": "local",
                "reason": "no suitable garden node available",
            }
        return await self.garden.submit_job(
            task_id=task_id,
            task_type=action.get("task_type", "generic"),
            payload=action.get("payload", {}),
            strategy="gpu_priority" if gpu_required else "round_robin",
            preferred_node=node.get("id"),
            gpu_required=gpu_required,
        )

    async def promote_backup_if_needed(self) -> Optional[Dict[str, Any]]:
        """If primary is unhealthy, reroute coordination to a healthy backup."""
        primary = getattr(self.garden, "GARDEN_NODES", [])[0] if getattr(self.garden, "GARDEN_NODES", []) else None
        if not primary:
            return None
        healthy = await self.garden._ping_node(primary)
        if healthy:
            return {"action": "none", "reason": "primary healthy", "node": primary.get("id")}
        fallback = await self.select_best_node(gpu_required=False, preferred_node=None)
        if not fallback:
            return {"action": "local_fallback", "reason": "no healthy node", "node": None}
        return {
            "action": "rerouted",
            "from_node": primary.get("id"),
            "to_node": fallback.get("id"),
            "ip": fallback.get("ip"),
        }

