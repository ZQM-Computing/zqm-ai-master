"""
The Void AI Orchestration System — ZQM Garden Service
Version: 2.0.0 | ZQM Computing LLC

Client for the ZQM Garden distributed compute cluster.
Manages job submission, node health, and task coordination.

ZQM Garden Nodes (per ZQM topology — Queen == Garden):
  Garden-0 (primary, GPU): 192.168.1.225  — ZQM-Garden-00 (Queen)
  Garden-1 (worker):       192.168.1.53   — ZQM-Garden-01.lan (Queen 10)
  Garden-2 (worker):       192.168.1.37   — ZQM-GARDEN-02.lan
  Garden-3 (worker):       192.168.1.64   — ZQM-GARDEN-03.lan
  Garden-4 (worker):       192.168.1.144  — ZQM-GARDEN-04
"""

from __future__ import annotations

import asyncio
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
    """

    GARDEN_NODES = [
        {"id": "garden-0", "ip": settings.garden_node_0, "role": "primary", "gpu": True,  "queen": "Queen"},
        {"id": "garden-1", "ip": settings.garden_node_1, "role": "worker",  "gpu": False, "queen": "Queen 10"},
        {"id": "garden-2", "ip": settings.garden_node_2, "role": "worker",  "gpu": False, "queen": "garden-2"},
        {"id": "garden-3", "ip": settings.garden_node_3, "role": "worker",  "gpu": False, "queen": "garden-3"},
        {"id": "garden-4", "ip": settings.garden_node_4, "role": "worker",  "gpu": False, "queen": "garden-4"},
    ]

    def __init__(self) -> None:
        self._base_url = settings.garden_endpoint.rsplit("/api/", 1)[0]
        self._timeout = settings.garden_timeout
        self._online_nodes: List[str] = []

    # ── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Ping the primary Garden node. Returns True if reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"http://{settings.garden_node_0}:8808/api/garden/health")
                return resp.status_code == 200
        except Exception as exc:
            log.debug("Garden health check failed", error=str(exc))
            return False

    async def get_online_nodes(self) -> List[str]:
        """Return IDs of currently reachable Garden nodes."""
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

    async def _ping_node(self, node: Dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"http://{node['ip']}:8808/api/health")
                return resp.status_code < 500
        except Exception:
            return False

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

        async def _post_to(node_ip: str) -> Dict[str, Any]:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"http://{node_ip}:8808{settings.garden_endpoint.rsplit('://',1)[-1].split('/',1)[1]}",
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

        # 1) Try primary first.
        try:
            return await _post_to(settings.garden_node_0)
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
            n["ip"] for n in self.GARDEN_NODES
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

        for ip in candidates:
            try:
                return await _post_to(ip)
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
                    f"http://{settings.garden_node_0}:8808/api/garden/jobs/{job_id}",
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("Garden job status check failed", job_id=job_id, error=str(exc))
            return {"job_id": job_id, "status": "unknown", "error": str(exc)}

    async def get_node_metrics(self) -> List[Dict[str, Any]]:
        """Fetch resource metrics from all Garden nodes."""
        results = await asyncio.gather(
            *[self._get_node_metrics(node) for node in self.GARDEN_NODES],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, dict)]

    async def _get_node_metrics(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"http://{node['ip']}:8808/api/garden/metrics")
                if resp.status_code == 200:
                    data = resp.json()
                    data["node_id"] = node["id"]
                    return data
        except Exception:
            pass
        return {"node_id": node["id"], "status": "offline"}
