"""
Mesh-aware distributed inference for Phase 3.

Routes inference requests across available mesh nodes based on:
- Model size
- Node capabilities
- Current load
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional


MESH_NODES = [
    {"id": "n1", "ip": "192.168.1.218", "port": 8808},
    {"id": "n3", "ip": "192.168.1.78", "port": 8808},
    {"id": "n4", "ip": "192.168.1.228", "port": 8808},
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


# Authoritative IP map from N1 control plane /nodes endpoint, reconciled with
# live ARP/SSH probes from N4 on 2026-08-07.
NODE_IP_MAP = {
    "N1": "192.168.1.218",
    "N2": "192.168.1.196",
    "N3": "192.168.1.78",
    "N4": "192.168.1.228",
    "N4TABLE": "192.168.1.242",
}


def resolve_node_ip(node_id: str, fallback: str) -> str:
    """Return authoritative mesh IP for a node ID, with safe fallback."""
    return NODE_IP_MAP.get(node_id.upper(), fallback)


async def discover_mesh_nodes() -> List[Dict[str, Any]]:
    """Discover live mesh nodes via /healthz."""
    import urllib.request
    live = []
    for node in MESH_NODES:
        try:
            req = urllib.request.Request(f"http://{node['ip']}:{node['port']}/healthz", method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    live.append(node)
        except Exception:
            pass
    return live


def estimate_model_vram_gb(model_params_b: float, quant: str = "fp16") -> float:
    bytes_per_param = {"fp32": 4, "fp16": 2, "q4": 0.5, "q8": 1}
    return model_params_b * bytes_per_param.get(quant, 2)


def route_inference(model_params_b: float, quant: str = "fp16") -> Optional[Dict[str, Any]]:
    """Route inference to best available node."""
    needed_vram = estimate_model_vram_gb(model_params_b, quant)
    # Placeholder: real routing checks node GPU memory/load
    for node in MESH_NODES:
        # Simplified: assume all nodes can handle small models
        return node
    return None


async def distributed_chat(node: Dict[str, Any], model: str, messages: List[Dict[str, str]], timeout: int = 120) -> Dict[str, Any]:
    """Send chat request to a specific mesh node."""
    import urllib.request
    url = f"http://{node['ip']}:{node['port']}/api/chat"
    payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())
