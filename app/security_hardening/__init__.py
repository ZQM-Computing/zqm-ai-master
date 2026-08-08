"""
The Void AI Orchestration System — Security Hardening Utilities
Version: 2.2.0 | ZQM Computing LLC

Provides helpers for secret rotation, debug-log stripping,
and IP redaction for customer deliveries.
"""

from __future__ import annotations

import os
import re
from typing import List


def redact_internal_ips(text: str) -> str:
    return re.sub(r"192\.168\.\d+\.\d+", "[REDACTED]", text)


def strip_debug_logs(log_dir: str) -> list[str]:
    removed = []
    for root, dirs, files in os.walk(log_dir):
        for name in files:
            path = os.path.join(root, name)
            if path.endswith(".log") or path.endswith(".jsonl"):
                try:
                    os.remove(path)
                    removed.append(path)
                except OSError:
                    pass
    return removed


def require_secret_rotation(env_path: str) -> list[str]:
    warnings = []
    if not os.path.exists(env_path):
        return warnings
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "SECRET_KEY" in line and "changeme" in line:
                warnings.append("SECRET_KEY is using an insecure default.")
    return warnings
