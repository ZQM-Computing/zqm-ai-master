"""
The Void AI Orchestration System — ZQM Garden Service
Version: 2.0.0 | ZQM Computing LLC

Client for the ZQM Garden distributed compute cluster.
Manages job submission, node health, and task coordination.

ZQM Garden Nodes (live mesh nodes with /api/garden/* available):
  Garden-0 = N4 / ZQM-Void-N4    192.168.1.228  (primary/Queen)
  Garden-1 = N1 / ZQM-Void-N1    192.168.1.224  (backup/Queen 10)
  Garden-2 = N3 / ZQM-Node-3     192.168.1.78
  Garden-3 = N2 / ZQM-Node-2     192.168.1.31
  Garden-4 = COMB / zqm-void-pve 192.168.1.225
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("garden-service")


class GardenService:
    """
    ZQM Garden distributed compute integration.

    Provides:
    - Job submission and monitoring
    - Node health checking
    - Load balancing hints
    - Task coordination with ZQM_AIOrchestrator
    - Node health snapshots, metrics aggregation, failover selection
    """

    GARDEN_NODES = [
        {"id": "garden-0", "ip": settings.garden_node_0, "api_port": settings.garden_node_0_port, "role": "primary", "gpu": True,  "queen": "Queen"},
        {"id": "garden-1", "ip": settings.garden_node_1, "api_port": settings.garden_node_1_port, "role": "backup",  "gpu": False, "queen": "Queen 10"},
        {"id": "garden-2", "ip": settings.garden_node_2, "api_port": settings.garden_node_2_port, "role": "worker",  "gpu": False, "queen": "garden-2"},
        {"id": "garden-3", "ip": settings.garden_node_3, "api_port": settings.garden_node_3_port, "role": "worker",  "gpu": False, "queen": "garden-3"},
        {"id": "garden-4", "ip": settings.garden_node_4, "api_port": settings.garden_node_4_port, "role": "worker",  "gpu": False, "queen": "garden-4"},
    ]

    def __init__(self) -> None:
        self._base_url = settings.garden_endpoint.rsplit("/api/", 1)[0]
        self._timeout = settings.garden_timeout
        self._online_nodes: List[str] = []

    # ── Health ────────────────────────────────────────────────────────────────

    def _endpoint(self, node: Dict[str, Any], path: str) -> str:
        port = node.get("api_port", "8808")
        return f"http://{node['ip']}:{port}{path}"

    async def health_check(self) -> bool:
        """Ping all configured Garden nodes; True if ANY reachable."""
        try:
            results = await asyncio.gather(
                *[self._ping_node(node) for node in self.GARDEN_NODES],
                return_exceptions=True,
            )
            return any(r is True for r in results)
        except Exception:
            return False

    async def get_online_nodes(self) -> List[str]:
        """Return IDs of currently reachable Garden nodes with caching."""
        try:
            results = await asyncio.gather(
                *[self._ping_node(node) for node in self.GARDEN_NODES],
                return_exceptions=True,
            )
            online = [
                self.GARDEN_NODES[i]["id"]
                for i, r in enumerate(results)
                if r is True
            ]
            self._online_nodes = online
            return online
        except Exception:
            return self._online_nodes or []

    async def _ping_node(self, node: Dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(self._endpoint(node, "/api/garden/health"))
                return resp.status_code == 200
        except Exception:
            return False

    # ── Node Operations ───────────────────────────────────────────────────────

    async def get_node_health_snapshot(self) -> List[Dict[str, Any]]:
        """Return richer health snapshots for every configured node."""
        results = await asyncio.gather(
            *[self._probe_node(node) for node in self.GARDEN_NODES],
            return_exceptions=True,
        )
        snapshot: List[Dict[str, Any]] = []
        for node, result in zip(self.GARDEN_NODES, results):
            if isinstance(result, Exception):
                snapshot.append({
                    "id": node.get("id"),
                    "ip": node.get("ip"),
                    "status": "unreachable",
                    "error": str(result),
                })
            else:
                snapshot.append(result)
        return snapshot

    async def _probe_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = self._endpoint(node, "/api/garden/health")
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
                    "status": "healthy" if resp.status_code == 200 else ("unsupported" if resp.status_code == 404 else "degraded"),
                    "http_status": resp.status_code,
                    "role": node.get("role"),
                    "gpu": node.get("gpu", False),
                    "queen": node.get("queen"),
                    "api_port": node.get("api_port", "8808"),
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
                "api_port": node.get("api_port", "8808"),
            }

    async def collect_node_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics across all nodes with per-node fallback."""
        raw = await self.get_node_metrics()
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
            for n in self.GARDEN_NODES:
                if n.get("id") == preferred_node:
                    healthy = await self._ping_node(n)
                    if healthy:
                        return n
        candidates: List[tuple[bool, Dict[str, Any]]] = []
        for n in self.GARDEN_NODES:
            if gpu_required and not n.get("gpu"):
                continue
            try:
                healthy = await self._ping_node(n)
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
        return await self.submit_job(
            task_id=task_id,
            task_type=action.get("task_type", "generic"),
            payload=action.get("payload", {}),
            strategy="gpu_priority" if gpu_required else "round_robin",
            preferred_node=node.get("id"),
            gpu_required=gpu_required,
        )

    # ── Job Submission ────────────────────────────────────────────────────────

    async def submit_job(
        self,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        strategy: str = "round_robin",
        preferred_node: Optional[str] = None,
        gpu_required: bool = False,
    ) -> Dict[str, Any]:
        """
        Submit a compute job to the ZQM Garden.

        Args:
            task_id: ZQM_AI task ID
            task_type: Garden task type (e.g. ai_inference, geometry_processing)
            payload: Task data
            strategy: Distribution strategy (round_robin, gpu_priority, etc.)
            preferred_node: Preferred garden node ID
            gpu_required: Whether GPU is required

        Returns:
            Garden job response dict
        """
        job = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": payload,
            "strategy": strategy,
            "gpu_required": gpu_required,
            "preferred_node": preferred_node or ("garden-0" if gpu_required else None),
            "zqm_ai_id": settings.zqm_ai_id,
        }

        async def _post_to(node_ip: str, port: str) -> Dict[str, Any]:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"http://{node_ip}:{port}/api/garden/coordinate",
                    json=job,
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                result = resp.json()
                log.info(
                    "Garden job submitted",
                    task_id=task_id,
                    task_type=task_type,
                    job_id=result.get("job_id"),
                    node=node_ip,
                )
                return result

        # 1) Try preferred or primary first.
        primary_ip = settings.garden_node_0
        if preferred_node:
            for n in self.GARDEN_NODES:
                if n.get("id") == preferred_node:
                    primary_ip = n["ip"]
                    break
        try:
            return await _post_to(primary_ip, str(settings.garden_node_0_port))
        except httpx.HTTPError as exc:
            log.warning("Garden primary node submission failed", task_id=task_id, error=str(exc))
        except Exception as exc:
            log.warning("Garden primary node unexpected error", task_id=task_id, error=str(exc))

        # 2) Fallback: any online node in round-robin order.
        try:
            online = await self.get_online_nodes()
        except Exception:
            online = []
        candidates = [
            (n["ip"], n.get("api_port", "8808"))
            for n in self.GARDEN_NODES
            if n["id"] != "garden-0" and n["id"] in online and not (gpu_required and not n.get("gpu"))
        ]
        if not candidates:
            # 3) Final local fallback.
            return {
                "job_id": f"local-{task_id}",
                "status": "local_fallback",
                "node": "local",
                "message": "Garden unavailable: primary and online fallbacks exhausted",
            }

        for ip, port in candidates:
            try:
                return await _post_to(ip, port)
            except Exception as exc:
                log.warning("Garden fallback node failed", task_id=task_id, node=ip, error=str(exc))
                continue

        return {
            "job_id": f"local-{task_id}",
            "status": "local_fallback",
            "node": "local",
            "message": "Garden unavailable: all online fallback nodes errored",
        }

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Check the status of a submitted Garden job."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    self._endpoint(self.GARDEN_NODES[0], f"/api/garden/jobs/{job_id}"),
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("Garden job status check failed", job_id=job_id, error=str(exc))
            return {"job_id": job_id, "status": "unknown", "error": str(exc)}

    async def get_node_metrics(self) -> List[Dict[str, Any]]:
        """Fetch resource metrics from all Garden nodes with resilience."""
        nodes = getattr(self, "GARDEN_NODES", [])
        if not nodes:
            return []
        results = await asyncio.gather(
            *[self._get_node_metrics(node) for node in nodes],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, dict)]

    async def _get_node_metrics(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    self._endpoint(node, "/api/garden/metrics"),
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"raw": resp.text[:200]}
                    data["node_id"] = node["id"]
                    data["http_status"] = resp.status_code
                    return data
                return {
                    "node_id": node["id"],
                    "status": "degraded",
                    "http_status": resp.status_code,
                }
        except Exception as exc:
            return {
                "node_id": node["id"],
                "status": "offline",
                "error": str(exc)[:200],
            }
