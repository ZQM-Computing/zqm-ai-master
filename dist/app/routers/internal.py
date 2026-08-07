"""
The Void AI Orchestration System — /api/internal Router
Version: 2.1.0 | ZQM Computing LLC

No-auth metadata surface for build diagnostics. Reveals no secrets, tokens,
or key material — only lengths, lengths, lengths, and structural metadata.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(prefix="/api/internal", tags=["Internal"])


def _redacted_summary() -> Dict[str, Any]:
    """Summarize live configuration lengths without revealing values."""
    def ln(name: str) -> int:
        v = os.getenv(name, "")
        return len(v)

    return {
        "SECRET_KEY_len": ln("SECRET_KEY"),
        "ZQM_INTERNAL_KEY_len": ln("ZQM_INTERNAL_KEY"),
        "GITHUB_WEBHOOK_SECRET_len": ln("GITHUB_WEBHOOK_SECRET"),
        "ZQM_ADMIN_PASSWORD_len": ln("ZQM_ADMIN_PASSWORD"),
        "ZQM_GARDEN_SERVICE_KEY_len": ln("ZQM_GARDEN_SERVICE_KEY"),
        "ZQM_FLATSPACE_SERVICE_KEY_len": ln("ZQM_FLATSPACE_SERVICE_KEY"),
        "ZQM_OBSERVABILITY_SERVICE_KEY_len": ln("ZQM_OBSERVABILITY_SERVICE_KEY"),
        "OLLAMA_API_KEY_len": ln("OLLAMA_API_KEY"),
    }


@router.get("/selfcheck")
async def internal_selfcheck(request: Request) -> JSONResponse:
    """Zero-auth health/identity probe for build verification.

    Returns:
      - process identity (pid, hostname)
      - build/version/env/self_apply
      - route table method breakdown
      - config redaction summary (lengths only)
    """
    import socket
    from datetime import datetime

    fastapi_app = request.app
    host = socket.gethostname()
    pid = os.getpid()
    start = datetime.utcnow().isoformat() + "Z"
    methods: Dict[str, int] = {}
    for rt in fastapi_app.routes:
        ms = getattr(rt, "methods", None)
        if ms:
            for m in (x for x in ms if x != "HEAD"):
                methods[m] = methods.get(m, 0) + 1
    payload = {
        "process": {"pid": pid, "host": host, "start_iso": start},
        "build": {
            "app_version": settings.app_version,
            "environment": settings.environment,
            "zqm_ai_id": settings.zqm_ai_id,
            "self_apply": getattr(settings, "self_apply", None),
        },
        "routes": {
            "total_http": sum(1 for rt in fastapi_app.routes if getattr(rt, "methods", None)),
            "methods": methods,
        },
        "configuration": _redacted_summary(),
    }
    return JSONResponse(payload)
