"""
Canonical mesh connectivity helper for ZQM-MESH.

This module centralizes the authoritative node IP map and provides helpers
for port/protocol checks. It is intentionally a thin convenience wrapper;
do not hardcode node IPs elsewhere in the codebase.
"""
from __future__ import annotations

import socket
from typing import Dict, Iterable, Tuple

# Canonical node IPs as of 2026-08-08.
NODE_IPS: Dict[str, str] = {
    "N1": "192.168.1.224",
    "N2": "192.168.1.196",
    "N3": "192.168.1.78",
    "N4": "192.168.1.228",
    "N9": "192.168.1.250",
}


def node_ip(node_id: str, fallback: str | None = None) -> str:
    return NODE_IPS.get(node_id.upper(), fallback or "")


def all_node_ips() -> Iterable[Tuple[str, str]]:
    return sorted(NODE_IPS.items())


def is_loopback(host: str) -> bool:
    try:
        return socket.gethostbyname(host) in (
            "127.0.0.1",
            "::1",
            "0.0.0.0",
        )
    except socket.gaierror:
        return False
