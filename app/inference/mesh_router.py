"""
Mesh-aware distributed inference for Phase 3.

Routes inference requests across available mesh nodes based on:
- Model size
- Node capabilities
- Current load
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from mesh_connect import resolve_node_ip


MESH_NODES = [
    {"id": "n1", "ip": resolve_node_ip("N1"), "port": 8808},
    {"id": "n2", "ip": resolve_node_ip("N2"), "port": 8808},
    {"id": "n3", "ip": resolve_node_ip("N3"), "port": 8808},
    {"id": "n4", "ip": resolve_node_ip("N4"), "port": 8808},
]


def _exclude_stale_sync_paths() -> None:
    """Exclude OneDrive-synced stale copies from import/sync paths."""
    import pathlib
    stale = pathlib.Path(
        r"C:\Users\zqmco\OneDrive\Imports\zqmcomputing@gmail.com - Google Drive"
        r"\ZQM Computing\05_Quantum_Computing\Software\ZQM-AI-master"
    )
    if str(stale) in sys.path:
        sys.path.remove(str(stale))
    # Best-effort: do not sync from OneDrive shadow copies
    os.environ.setdefault("ZQM_IGNORE_ONEDRIVE_SYNC", "1")


# Authoritative IP map is provided by `mesh_connect.py`; keep as a view here for
# downstream consumers that still reference `NODE_IP_MAP`.
NODE_IP_MAP = {
    "N1": resolve_node_ip("N1"),
    "N2": resolve_node_ip("N2"),
    "N3": resolve_node_ip("N3"),
    "N4": resolve_node_ip("N4"),
}


def resolve_node_ip(node_id: str, fallback: str) -> str:
    """Thin compatibility wrapper so imports from this module keep working."""
    from mesh_connect import node_ip as _node_ip

    return _node_ip(node_id) or fallback


async def discover_mesh_nodes() -> list[dict[str, Any]]:
    """Discover live mesh nodes via multiple possible health paths with latency scoring."""
    import urllib.request
    health_paths = ["/healthz", "/api/healthz", "/api/version"]
    scored: list[dict[str, Any]] = []
    for node in MESH_NODES:
        for hp in health_paths:
            try:
                t0 = __import__("time").monotonic()
                req = urllib.request.Request(f"http://{node['ip']}:{node['port']}{hp}", method="GET")
                with urllib.request.urlopen(req, timeout=5) as r:
                    if r.status == 200:
                        latency_ms = (__import__("time").monotonic() - t0) * 1000
                        scored.append({
                            "id": node["id"],
                            "ip": node["ip"],
                            "port": node["port"],
                            "latency_ms": round(latency_ms, 2),
                            "healthy": True,
                            "health_path": hp,
                        })
                        break
            except Exception:
                continue
    scored.sort(key=lambda n: n.get("latency_ms") or float("inf"))
    return scored


def estimate_model_vram_gb(model_params_b: float, quant: str = "fp16") -> float:
    bytes_per_param = {"fp32": 4, "fp16": 2, "q4": 0.5, "q8": 1}
    return model_params_b * bytes_per_param.get(quant, 2)


def route_inference(model_params_b: float, quant: str = "fp16") -> dict[str, Any] | None:
    """Route inference to the healthiest/lowest-latency available node."""
    try:
        live = __import__("asyncio").get_event_loop().run_until_complete(discover_mesh_nodes())
    except Exception:
        live = []
    if not live:
        return None
    needed_vram = estimate_model_vram_gb(model_params_b, quant)
    # TODO: compare needed_vram against reported node memory/GPU metrics
    return live[0]


async def distributed_chat(node: dict[str, Any], model: str, messages: list[dict[str, str]], timeout: int = 120) -> dict[str, Any]:
    """Send chat request to a specific mesh node."""
    import urllib.request
    url = f"http://{node['ip']}:{node['port']}/api/chat"
    payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())
