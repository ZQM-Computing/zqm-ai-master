"""
The Void AI Orchestration System — FastAPI Application
Version: 2.0.0 | ZQM Computing LLC

Entry point for the The Void REST API.
Runs on port 8808 — the central AI coordination hub for the ZQM ecosystem.

Start:
    uvicorn app.main:app --host 0.0.0.0 --port 8808 --reload
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import settings
from app.core.logger import configure_logging, get_logger
from app.core.security import get_current_token_payload, require_admin
from app.models.response import ErrorResponse
from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator
from app.routers import (
    dashboard,
    events,
    falsification,
    flatspace,
    garden,
    info,
    internal,
    mesh_ops,
    mesh_probe,
    moltbook,
    observability,
    permissions,
    predict,
    process,
    quantum_llm_bridge,
    sso,
    train,
    users,
    void_council,
    webhooks,
)
from app.routers import (
    settings as settings_router,
)
from app.routers import (
    status as status_router,
)
from app.services.mesh_ollama import OllamaUnavailable

# ── Configure logging first ───────────────────────────────────────────────────
configure_logging(
    level=settings.log_level,
    fmt=settings.log_format,
    log_file=settings.log_file if not settings.is_development else None,
)
log = get_logger("app")


# ── Lifespan context manager ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application startup and shutdown lifecycle.

    Startup:
      - Initialize ZQM_AIOrchestrator (registers default agent pool)
      - Warm up ZQM subsystem connections
      - Log startup banner

    Shutdown:
      - Graceful orchestrator shutdown (wait for active tasks)
      - Flush VoidCache
    """
    # ── STARTUP ───────────────────────────────────────────────────────────────
    log.info(
        "═══════════════════════════════════════════",
    )
    log.info(
        "  The Void AI Orchestration System",
        version=settings.app_version,
        environment=settings.environment,
    )
    log.info(
        "  ZQM_AI ID: %s | Garden: %s",
        settings.zqm_ai_id,
        settings.zqm_ai_primary_garden,
    )
    log.info(
        "═══════════════════════════════════════════",
    )

    orchestrator = ZQM_AIOrchestrator()
    await orchestrator.startup()
    app.state.orchestrator = orchestrator
    app.state.started_at = time.time()

    # Redis lifecycle
    try:
        from app.services.redis_service import RedisService
        redis = RedisService()
        await redis.connect()
        app.state.redis = redis
    except Exception as exc:
        log.warning("Redis startup failed", error=str(exc))
        app.state.redis = None

    # Council integrations after app state is available
    try:
        await orchestrator._void_council.initialize_integrations(
            app=app,
            observability=orchestrator.observability,
            flatspace=orchestrator.flatspace,
            garden=orchestrator.garden,
            redis=getattr(app.state, "redis", None),
        )
    except Exception as exc:
        log.debug("council integrations init skipped", error=str(exc))

    # Startup sanity checks
    try:
        db_path = Path(__file__).resolve().parent / "flatspace_local.db"
        if not db_path.exists():
            log.warning("Local FLATSPACE DB missing", path=str(db_path))
        else:
            log.info("Local FLATSPACE DB present", path=str(db_path))
    except Exception as exc:
        log.debug("FLATSPACE startup check failed", error=str(exc))

    # Wire the webhook receiver to this orchestrator instance.
    from app.routers import webhooks as _webhooks
    _webhooks.set_orchestrator(orchestrator)

    log.info(
        "The Void ready",
        docs=f"http://{settings.host}:{settings.port}/docs",
    )

    yield  # ← Application runs here

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    log.info("The Void shutting down...")
    await orchestrator.shutdown()
    log.info("The Void offline. Goodbye.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="The Void AI Orchestration System",
    description=(
        "Central AI orchestration engine for the ZQM ecosystem. "
        "Self-optimizing, multi-agent, cognitive processing platform by "
        "ZQM Computing LLC.\n\n"
        "**ZQM_AI ID:** ZQM-ZQM_AI-004 | **Employee ID:** ZQM_AI-001 | "
        "**Primary Garden:** Garden-0 (ZQM-Garden-00, 192.168.1.225)\n\n"
        "## Cognitive Processing Levels\n"
        "- **basic** — Single-agent direct response\n"
        "- **advanced** — Multi-agent parallel synthesis\n"
        "- **neural** — Deep processing with memory (VoidCache + FLATSPACE)\n"
        "- **autonomous** — Self-directed execution with learning loop"
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "ZQM Computing LLC",
        "url": "https://zqmlabs.com",
        "email": "zqmcomputing@gmail.com",
    },
    license_info={
        "name": "Proprietary — ZQM Computing LLC",
    },
)


# ── Middleware ────────────────────────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip compression for large responses
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Request timing middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add X-Process-Time header to all responses."""
    t0 = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - t0) * 1000)
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    response.headers["X-ZQM_AI-ID"] = settings.zqm_ai_id
    return response


# ── Request logging middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Structured request logging: method, path, status, latency, client IP."""
    t0 = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "request_error",
            method=request.method,
            path=request.url.path,
            client=getattr(request.client, "host", None),
            user_agent=request.headers.get("user-agent"),
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise
    duration_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        client=getattr(request.client, "host", None),
        user_agent=request.headers.get("user-agent"),
    )
    return response


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error="Not Found",
            detail=f"Path {request.url.path} not found",
        ).model_dump(mode="json"),
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Any) -> JSONResponse:
    log.error("Unhandled exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal Server Error",
            detail="An unexpected error occurred. Check logs for details.",
        ).model_dump(mode="json"),
    )


@app.exception_handler(OllamaUnavailable)
async def ollama_unavailable_handler(request: Request, exc: OllamaUnavailable) -> JSONResponse:
    """Mesh/Local Ollama is down — answer 503 'degraded' (retryable), not 500.

    The orchestrator stays up and keeps serving status/flatspace/webhooks;
    only inference is unavailable until the Ollama pool recovers.
    """
    log.warning("Ollama unavailable (degraded)", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error="Service Degraded",
            detail="Inference backend (Ollama mesh) unavailable — retry shortly.",
        ).model_dump(mode="json"),
    )


# ── Root endpoint ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root(request: Request):
    """Root redirect — returns quick identity info."""
    uptime = time.time() - getattr(request.app.state, "started_at", time.time())
    return {
        "system": "The Void AI Orchestration System",
        "zqm_ai_id": settings.zqm_ai_id,
        "version": settings.app_version,
        "status": "online",
        "uptime_seconds": round(uptime),
        "docs": f"http://{settings.host}:{settings.port}/docs",
        "health": f"http://{settings.host}:{settings.port}/healthz",
        "process": f"http://{settings.host}:{settings.port}/api/process",
    }


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    """Minimal liveness probe for load balancers / containers."""
    return JSONResponse({"status": "ok"})


@app.get("/api/healthz", include_in_schema=False)
async def api_healthz(request: Request):
    """Readiness probe: checks process + key dependencies."""
    orch = getattr(request.app.state, "orchestrator", None)
    deps = {
        "orchestrator": orch is not None,
    }
    if orch is not None:
        try:
            deps["flatspace"] = bool(await orch.flatspace.health_check() if hasattr(orch, "flatspace") else None)
        except Exception:
            deps["flatspace"] = False
        try:
            from app.services.mesh_ollama import router as mesh_ollama
            catalog = await mesh_ollama.list_models()
            deps["ollama"] = bool(catalog)
        except Exception:
            deps["ollama"] = False
    else:
        deps["flatspace"] = False
        deps["ollama"] = False
    healthy = all(deps.values())
    payload = {
        "status": "ok" if healthy else "degraded",
        "zqm_ai_id": settings.zqm_ai_id,
        "dependencies": deps,
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)


# ── Self-improvement findings (local fallback store) ─────────────────────
@app.get("/api/self-improvement", tags=["Self-Improvement"])
async def self_improvement_findings(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    limit: int = 50,
) -> JSONResponse:
    """
    Return self-improvement findings persisted locally (app/self_improvement_log.jsonl)
    when the FLATSPACE backend is unreachable. Newest first. Requires a valid token.
    """
    import json as _json
    from pathlib import Path

    log_path = Path(__file__).resolve().parent / "self_improvement_log.jsonl"
    if not log_path.exists():
        return JSONResponse({
            "zqm_ai_id": settings.zqm_ai_id,
            "source": "local_jsonl",
            "count": 0,
            "findings": [],
            "note": "No local findings log yet (FLATSPACE may be up, or no cycles run).",
        })
    try:
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        records = []
        for ln in lines:
            try:
                records.append(_json.loads(ln))
            except Exception:
                continue
        records = records[-max(1, limit):][::-1]
        return JSONResponse({
            "zqm_ai_id": settings.zqm_ai_id,
            "source": "local_jsonl",
            "count": len(records),
            "findings": records,
        })
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Read failed",
                detail=f"self_improvement_log.jsonl: {exc}",
            ).model_dump(mode="json"),
        )


# ── Self-Apply live proof (P2) ──────────────────────────────────────────────
@app.get("/api/self-apply/status", tags=["Self-Improvement"])
async def self_apply_status(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Report the RUNNING process's self-apply gate state (live, not a fresh interpreter)."""
    from app.orchestrator import self_apply
    orch = getattr(request.app.state, "orchestrator", None)
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "module_flag_SELF_APPLY_ON": self_apply.SELF_APPLY_ON,
        "orchestrator_needs_restart": getattr(orch, "_needs_restart", None),
        "env_ZQM_SELF_APPLY": os.getenv("ZQM_SELF_APPLY", "unset"),
        "live_process": True,
    })


# ── Self-Expansion (P6) ─────────────────────────────────────────────────────
@app.get("/api/self-expand/status", tags=["Self-Expansion"])
async def self_expand_status(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Report the self-expansion gate state + ledger length (live)."""
    from app.orchestrator import self_expand
    orch = getattr(request.app.state, "orchestrator", None)
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "module_flag_SELF_APPLY_ON": self_expand.SELF_APPLY_ON,
        "env_ZQM_SELF_APPLY": os.getenv("ZQM_SELF_APPLY", "unset"),
        "ledger_entries": len(self_expand.review_ledger(100000)),
        "live_process": True,
    })


@app.get("/api/self-expand/ledger", tags=["Self-Expansion"])
async def self_expand_ledger(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Return the expansion ledger (the human-review approval queue)."""
    from app.orchestrator import self_expand
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "ledger": self_expand.review_ledger(50),
    })


@app.post("/api/self-expand/apply", tags=["Self-Expansion"])
async def self_expand_apply(
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """ADMIN: replay the RAW self-improvement findings through process_findings
    (applies any pending expansions IF ZQM_SELF_APPLY is on; otherwise
    re-proposes/audits). Scans self_improvement_log.jsonl — the actual source
    of EXPAND_AGENT/EXPAND_TOOL/PATCH directives — not the ledger (which stores
    results, not source text)."""
    from app.orchestrator import self_expand
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    # Gather raw findings text from the source log (the real EXPAND_* source).
    # Robust path resolution: the on-disk dir casing can differ from __file__
    # (e.g. ZQM-AI-master vs ZQM-AI-Master under OneDrive), so try candidates.
    findings_blob = ""
    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "self_improvement_log.jsonl",
        Path("self_improvement_log.jsonl"),
        Path("app/self_improvement_log.jsonl"),
        repo_root / "app" / "self_improvement_log.jsonl",
    ]
    src = next((c for c in candidates if c.exists()), None)
    if src:
        import json as _json
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = _json.loads(line)
                f = rec.get("findings")
                if isinstance(f, list):
                    findings_blob += "\n".join(str(x) for x in f) + "\n"
                else:
                    findings_blob += str(f) + "\n"
            except Exception:
                findings_blob += line + "\n"
    summary = await self_expand.process_findings(orch, findings_blob)
    return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, **summary})


@app.post("/api/self-improve/run", tags=["Self-Improvement"])
async def self_improve_run(
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """ADMIN: run The Void's SELF-EXECUTING improvement engine (P9) now.

    Scans The Void's own code for known safe self-patches (e.g. the stale API
    envelope `version` field) and applies them when ZQM_SELF_APPLY is on.
    Returns {self_apply, proposed, applied, actions}."""
    from app.orchestrator import self_improve
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    summary = await self_improve.scan_and_improve(orch)
    return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, **summary})


@app.get("/api/self-improve/ledger", tags=["Self-Improvement"])
async def self_improve_ledger(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Return the self-improvement (P9) ledger of proposed + applied patches."""
    from app.orchestrator import self_improve
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "self_apply": self_improve.SELF_APPLY_ON,
        "ledger": self_improve.review_ledger(50),
    })



@app.post("/api/void/talk", tags=["The Void"])
async def void_talk(
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
    message: str = Body("", embed=True),
) -> JSONResponse:
    """Speak with The Void — conversational surface + continuous self-improvement hook."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})
    try:
        health = await orch.get_health(request)
        # model_dump(mode="json") makes datetimes ISO-string serializable
        health_dict = health.model_dump(mode="json") if hasattr(health, "model_dump") else (dict(health) if health else None)
    except Exception:
        health = None
        health_dict = None
    try:
        from app.orchestrator import self_improve
        ledger = self_improve.review_ledger(10)
        sa_on = self_improve.SELF_APPLY_ON
    except Exception:
        ledger, sa_on = [], False
    applied = [{"id": r.get("id"), "why": r.get("why")} for r in ledger if r.get("applied")]
    summary = {
        "zqm_ai_id": settings.zqm_ai_id,
        "build": f"{settings.app_version}",
        "health": health_dict,
        "self_apply": sa_on,
        "recent_self_improvements": applied,
    }
    inference_error = None
    reply = None
    if message:
        try:
            from app.services.mesh_ollama import MeshOllamaRouter, OllamaUnavailable
            mesh = getattr(orch, "mesh", None) or MeshOllamaRouter()
            data = await mesh.chat(
                settings.ollama_default_model,
                [{"role": "user", "content": message}],
                timeout=30,
            )
            reply = data.get("message", {}).get("content") if isinstance(data, dict) else None
        except OllamaUnavailable as exc:
            inference_error = f"inference unavailable: {exc}"
        except Exception as exc:
            inference_error = f"inference error: {type(exc).__name__}: {exc}"
    if not reply:
        parts = [
            f"I am The Void (build {summary['build']}).",
            f"Core: {health_dict.get('status') if health_dict else 'unknown'}.",
            f"self-apply: {'ON' if sa_on else 'OFF'}.",
            f"session improvements: {len(applied)}.",
        ]
        if inference_error:
            parts.append(f"{inference_error}. Answering from telemetry, not fabricated thought.")
        else:
            parts.append("No inference reply produced.")
        reply = " ".join(parts)
    return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, "echo": message, "reply": reply, "state": summary})


async def self_apply_selftest(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """
    Perform a REAL apply through the RUNNING orchestrator to prove the
    self-apply pipeline is live: writes a sentinel file, promotes a
    structured patch, audits to FLATSPACE waxcell, flags restart. The
    sentinel is then removed (audit row remains as proof). Fails safely
    if the gate is OFF.
    """
    from pathlib import Path

    from app.orchestrator import self_apply

    if not self_apply.SELF_APPLY_ON:
        return JSONResponse({
            "zqm_ai_id": settings.zqm_ai_id,
            "applied": False,
            "reason": "SELF_APPLY gate is OFF (set ZQM_SELF_APPLY=true to enable)",
        })

    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})

    sentinel = Path(__file__).resolve().parent / "_selftest_sentinel.py"
    sentinel.write_text("OLD_MARKER = False\n", encoding="utf-8")
    try:
        finding = (
            "PATCH:\n"
            "file: _selftest_sentinel.py\n"
            "<<<<<<< SEARCH\nOLD_MARKER = False\n=======\nOLD_MARKER = True\n>>>>>>> REPLACE\n"
        )
        await self_apply.try_apply_findings(orch, [finding])
        applied = sentinel.read_text(encoding="utf-8").strip() == "OLD_MARKER = True"
        rows = await orch.flatspace.search("self_apply", tier="waxcell", limit=5)
        return JSONResponse({
            "zqm_ai_id": settings.zqm_ai_id,
            "applied": applied,
            "sentinel_after": sentinel.read_text(encoding="utf-8").strip(),
            "orchestrator_needs_restart": getattr(orch, "_needs_restart", None),
            "waxcell_audit_keys": [r.get("key", "")[:40] for r in rows],
        })
    finally:
        # Clean up the sentinel; the audit row in waxcell remains as proof.
        try:
            sentinel.unlink()
        except Exception:
            pass
        try:
            sentinel.with_suffix(".py.bak").unlink()
        except Exception:
            pass


@app.get("/api/self-replicate/status", tags=["Self-Replication"])
async def self_replicate_status(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Report the self-replication gate state + ledger length (live)."""
    from app.orchestrator import self_replicate
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "module_flag_SELF_APPLY_ON": self_replicate.SELF_APPLY_ON,
        "known_nodes": list(self_replicate.KNOWN_NODES),
        "ledger_entries": len(self_replicate.review_ledger(100000)),
        "live_process": True,
    })


@app.get("/api/self-replicate/ledger", tags=["Self-Replication"])
async def self_replicate_ledger(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Return the replication ledger (the audit trail of proposed/applied replicas)."""
    from app.orchestrator import self_replicate
    return JSONResponse({
        "zqm_ai_id": settings.zqm_ai_id,
        "ledger": self_replicate.review_ledger(50),
    })


@app.post("/api/self-replicate", tags=["Self-Replication"])
async def self_replicate_apply(
    request: Request,
    auth: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """ADMIN: replicate The Void to a mesh node. Body: {"node": "N3", "confirm": true}.

    GATED + CONFIRMED: even with ZQM_SELF_APPLY on, a real cross-node deploy
    requires explicit confirm=true (high blast-radius: SSH service install on
    another host). Without confirm, it validates + proposes + audits only.
    """
    from app.orchestrator import self_replicate
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    node = str(body.get("node", "N3")).upper()
    confirm = bool(body.get("confirm", False))
    res = await self_replicate.replicate_to(orch, node, confirm=confirm)
    return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, **res})


@app.get("/api/version", tags=["Meta"])
async def version_info() -> dict[str, Any]:
    """Return The Void version manifest (see app/core/version.py)."""
    from app.core.version import get_version
    return get_version()


# ── Self Systems Integration (P4) ─────────────────────────────────────────
@app.get("/api/flatspace", tags=["Integration"])
async def flatspace_search(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    query: str = "",
    tier: str = "bitgarden",
    limit: int = 20,
) -> JSONResponse:
    """Search the live FLATSPACE store (memory / audit). Requires a valid token."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})
    try:
        rows = await orch.flatspace.search(query, tier=tier, limit=limit)
        return JSONResponse({
            "zqm_ai_id": settings.zqm_ai_id,
            "tier": tier,
            "count": len(rows),
            "rows": rows,
        })
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"flatspace search failed: {exc}"})


@app.get("/api/task-audit", tags=["Integration"])
async def task_audit(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    limit: int = 20,
) -> JSONResponse:
    """Return recent task-result audit records from FLATSPACE bitgarden."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})
    try:
        rows = await orch.flatspace.search("task_result", tier="bitgarden", limit=limit)
        return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, "count": len(rows), "tasks": rows})
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"task audit failed: {exc}"})


@app.get("/api/mcp-audit", tags=["Integration"])
async def mcp_audit(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    limit: int = 20,
) -> JSONResponse:
    """Return Machine-Checkable Proof audit records from FLATSPACE waxcell."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})
    try:
        rows = await orch.flatspace.search("mcp", tier="waxcell", limit=limit)
        return JSONResponse({"zqm_ai_id": settings.zqm_ai_id, "count": len(rows), "mcps": rows})
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"mcp audit failed: {exc}"})


@app.post("/api/roundtable", tags=["Integration"])
async def roundtable(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    body: dict[str, Any] = None,
) -> JSONResponse:
    """
    Convene a multi-agent roundtable IN-VOID. Body: {topic, panel?, rounds?}.
    Returns the full transcript; audits it to FLATSPACE bitgarden.
    """
    body = body or {}
    topic = str(body.get("topic", "")).strip()
    if not topic:
        return JSONResponse(status_code=400, content={"error": "topic required"})
    panel = body.get("panel")
    rounds = int(body.get("rounds", 2))
    from app.orchestrator import system_integration
    result = await system_integration.run_roundtable(topic, panel, rounds)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    # Audit the roundtable to FLATSPACE for durable recall.
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is not None:
        try:
            await orch.flatspace.store(
                key=f"roundtable:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}",
                value=result,
                tier="bitgarden",
            )
        except Exception:
            pass
        # Publish to the live event bus (SSE consumers).
        try:
            from app.core.event_bus import bus
            await bus.publish("roundtable", {
                "topic": result.get("topic"),
                "agents": result.get("agents"),
                "transcript_len": len(result.get("transcript", "")),
            })
        except Exception:
            pass
    return JSONResponse(result)


@app.post("/api/integrate", tags=["Integration"])
async def integrate(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """
    Trigger P4a: read self-improvement findings and tune the LIVE agent pool.
    Gated by ZQM_SELF_APPLY (propose-only log if off; live re-weight if on).
    """
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse(status_code=503, content={"error": "orchestrator not ready"})
    from app.orchestrator import system_integration
    result = await system_integration.integrate_findings(orch)
    return JSONResponse(result)


@app.get("/api/stream/stats", tags=["Streaming"])
async def stream_stats(
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> dict[str, Any]:
    from app.core.event_bus import bus

    snapshot = {
        "history_count": len(bus._history),
        "subscribers": len(bus._subscribers),
        "latest_ts": bus._history[-1].get("ts") if bus._history else None,
        "latest_event": bus._history[-1].get("event") if bus._history else None,
        "lag_counter": bus._lag_counter,
    }
    return snapshot


@app.get("/api/stream", tags=["Streaming"])
async def stream_events(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    since: str = Query(None),
) -> StreamingResponse:
    """
    Server-Sent Events stream of ALL The Void internal events
    (webhooks, self-improve cycles, roundtables, self-apply, agent actions).
    Hardened: retry field, 15s heartbeat, client-disconnect detection,
    structured error/done events. Replays recent history on connect.
    """
    from app.core.event_bus import bus
    from app.core.sse import enhanced_sse_stream

    sub = bus.subscribe(history=True)

    async def _upstream():
        async with sub as gen:
            async for evt in gen:
                if since:
                    evt_ts = evt.get("ts")
                    if evt_ts:
                        try:
                            if datetime.fromisoformat(evt_ts).timestamp() < float(since):
                                continue
                        except (TypeError, ValueError):
                            pass
                yield evt

    return StreamingResponse(
        enhanced_sse_stream(_upstream(), request=request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/stream/webhooks", tags=["Streaming"])
async def stream_webhooks(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
    since: str = Query(None),
) -> StreamingResponse:
    """SSE stream of webhook events only."""
    from app.core.event_bus import bus
    from app.core.sse import enhanced_sse_stream

    sub = bus.subscribe_by_topic("webhook", history=True)

    async def _upstream():
        async with sub as gen:
            async for evt in gen:
                if since:
                    evt_ts = evt.get("ts")
                    if evt_ts:
                        try:
                            if datetime.fromisoformat(evt_ts).timestamp() < float(since):
                                continue
                        except (TypeError, ValueError):
                            pass
                yield evt

    return StreamingResponse(
        enhanced_sse_stream(_upstream(), request=request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/mesh/ollama", tags=["Mesh"])
async def mesh_ollama_status(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> dict[str, Any]:
    """Mesh Ollama federation status: backend health + aggregated model catalog."""
    from app.services.mesh_ollama import router as mesh_ollama
    catalog = await mesh_ollama.list_models()
    return catalog


# ── Register routers ──────────────────────────────────────────────────────────

app.include_router(process.router)
app.include_router(status_router.router)
app.include_router(dashboard.router)
app.include_router(dashboard.alias_router)
app.include_router(garden.router)
app.include_router(predict.router)
app.include_router(train.router)
app.include_router(settings_router.router)
app.include_router(users.router)
app.include_router(sso.router)
app.include_router(events.router)
app.include_router(permissions.router)
app.include_router(info.router)
app.include_router(webhooks.router)
app.include_router(flatspace.router)
app.include_router(falsification.router)
app.include_router(quantum_llm_bridge.router)
app.include_router(mesh_probe.router)
app.include_router(internal.router)
app.include_router(observability.router)
app.include_router(moltbook.router)
app.include_router(void_council.router)
app.include_router(mesh_ops.router)
from app.routers.rag import router as rag_router

app.include_router(rag_router)
from app.routers.reasoning import router as reasoning_router

app.include_router(reasoning_router)
from app.routers.train import router as train_router

app.include_router(train_router)
from app.routers.support import router as support_router

app.include_router(support_router)


# ── Dev server entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        workers=1 if settings.is_development else settings.workers,
        log_level=settings.log_level.lower(),
        access_log=settings.is_development,
    )
