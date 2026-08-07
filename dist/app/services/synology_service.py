"""
The Void AI Orchestration System — Synology Service
Version: 2.0.0 | ZQM Computing LLC

Client for the Synology NAS fleet backing the ZQM Garden cluster.
Provides DSM discovery, health, and maintenance operations.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("synology-service")


class SynologyService:
    """Minimal DSM/WebAPI client for the Synology Garden fleet."""

    GARDEN_NODES = [
        {"id": "garden-0", "ip": settings.garden_node_0, "api_port": settings.garden_node_0_port, "queen": "Queen"},
        {"id": "garden-1", "ip": settings.garden_node_1, "api_port": settings.garden_node_1_port, "queen": "Queen 10"},
        {"id": "garden-2", "ip": settings.garden_node_2, "api_port": settings.garden_node_2_port, "queen": "garden-2"},
        {"id": "garden-3", "ip": settings.garden_node_3, "api_port": settings.garden_node_3_port, "queen": "garden-3"},
        {"id": "garden-4", "ip": settings.garden_node_4, "api_port": settings.garden_node_4_port, "queen": "garden-4"},
    ]

    def __init__(self) -> None:
        self._base = "https://{ip}:{port}/webapi"
        self._timeout = settings.garden_timeout

    def _auth_headers(self, account: Optional[str] = None, passwd: Optional[str] = None) -> Dict[str, str]:
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-SYNO-TOKEN": "",
        }

    async def health_check(self) -> bool:
        """Return True if any node answers /entry.cgi successfully."""
        results = await asyncio.gather(
            *[self._probe(node) for node in self.GARDEN_NODES],
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def _probe(self, node: Dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2, verify=False) as client:
                r = await client.get(
                    f"https://{node['ip']}:{node['api_port']}/webapi/entry.cgi",
                    params={"api": "SYNO.API.Info", "version": "1", "method": "query", "query": "all"},
                    headers=self._auth_headers(),
                )
                return r.status_code == 200
        except Exception:
            return False

    async def get_node_system_info(self) -> List[Dict[str, Any]]:
        """Fetch DSM system info from every reachable node."""
        results = await asyncio.gather(
            *[self._get_info(node) for node in self.GARDEN_NODES],
            return_exceptions=True,
        )
        out: List[Dict[str, Any]] = []
        for node, result in zip(self.GARDEN_NODES, results):
            if isinstance(result, Exception):
                out.append({
                    "id": node.get("id"),
                    "ip": node.get("ip"),
                    "status": "unreachable",
                    "error": str(result),
                })
            else:
                out.append(result)
        return out

    async def _get_info(self, node: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3, verify=False) as client:
                r = await client.get(
                    f"https://{node['ip']}:{node['api_port']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.NAS.Ctl",
                        "version": "1",
                        "method": "systeminfo",
                        "_sid": "",
                    },
                    headers=self._auth_headers(),
                )
                if r.status_code == 200:
                    data = r.json()
                    data.setdefault("queen", node.get("queen"))
                    return data
                return {
                    "id": node.get("id"),
                    "ip": node.get("ip"),
                    "status": "degraded",
                    "http_status": r.status_code,
                }
        except Exception as exc:
            return {
                "id": node.get("id"),
                "ip": node.get("ip"),
                "status": "offline",
                "error": str(exc),
            }
