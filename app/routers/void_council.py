from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.logger import get_logger
from app.core.security import get_current_token_payload, require_admin
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/void-council", tags=["Void Council"])
log = get_logger("router.void-council")


@router.get("/domains")
async def list_domains(
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    domains_mod = __import__("app.orchestrator.void_council", fromlist=["COUNCIL_DOMAINS"])
    domains = [
        {
            "id": domain_id,
            "presiding": [p.value for p in cfg["presiding"]],
            "specialists": [p.value for p in cfg["specialists"]],
            "scribe": [p.value for p in cfg["scribe"]],
            "description": cfg["description"],
            "min_quorum": cfg.get("min_quorum", 3),
        }
        for domain_id, cfg in domains_mod.COUNCIL_DOMAINS.items()
    ]
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=domains,
            message=f"{len(domains)} council domain(s)",
        ).model_dump(mode="json")
    )


@router.post("/convene")
async def convene_council(
    request: Request,
    auth: Dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}

    domain = body.get("domain")
    try:
        result = await orch._void_council.convene(
            domain=domain,
            min_confidence=float(body.get("min_confidence", 0.6)),
            auto_apply=bool(body.get("auto_apply", False)),
        )
    except Exception as exc:
        log.exception("Void Council convene failed", error=str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "convene_failed",
                "detail": str(exc),
            },
            status_code=500,
        )
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=result,
            message=f"Void Council convened: {result.get('domain')}",
        ).model_dump(mode="json")
    )


@router.post("/convene-full")
async def convene_full_council(
    request: Request,
    auth: Dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        result = await orch._void_council.convene_full(
            min_confidence=float(body.get("min_confidence", 0.6)),
            auto_apply=bool(body.get("auto_apply", False)),
        )
    except Exception as exc:
        log.exception("Void Council full session failed", error=str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "convene_full_failed",
                "detail": str(exc),
            },
            status_code=500,
        )
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=result,
            message=f"Full council complete: {result.get('sessions')} domains",
        ).model_dump(mode="json")
    )


@router.get("/history")
async def council_history(
    request: Request,
    limit: int = 20,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None or not hasattr(orch, "_void_council"):
        return JSONResponse({"error": "council not available"}, status_code=503)
    try:
        rows = await orch._void_council.review_history(limit=min(limit, 200))
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": "history_read_failed", "detail": str(exc)},
            status_code=500,
        )
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=rows,
            message=f"{len(rows)} council session(s)",
        ).model_dump(mode="json")
    )


@router.post("/emergency")
async def emergency_council(
    request: Request,
    auth: Dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None or not hasattr(orch, "_void_council"):
        return JSONResponse({"error": "council not available"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    domains = body.get("domains", ["reliability", "security"])
    try:
        result = await orch._void_council.convene_emergency(
            domains=domains,
            min_confidence=float(body.get("min_confidence", 0.7)),
            auto_apply=bool(body.get("auto_apply", True)),
        )
    except Exception as exc:
        log.exception("Void Council emergency session failed", error=str(exc))
        return JSONResponse(
            {
                "success": False,
                "error": "emergency_session_failed",
                "detail": str(exc),
            },
            status_code=500,
        )
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=result,
            message=f"Emergency council complete: {result.get('sessions')} sessions",
        ).model_dump(mode="json")
    )


@router.get("/quality")
async def council_quality(
    request: Request,
    limit: int = 20,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None or not hasattr(orch, "_void_council"):
        return JSONResponse({"error": "council not available"}, status_code=503)
    try:
        quality = await orch._void_council.review_session_quality(limit=min(limit, 200))
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": "quality_review_failed", "detail": str(exc)},
            status_code=500,
        )
    return JSONResponse(
        ZQM_AIResponse.ok(
            data=quality,
            message=f"Council quality review: {quality.get('sessions')} sessions",
        ).model_dump(mode="json")
    )


@router.get("/evidence")
async def council_evidence(
    request: Request,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None or not hasattr(orch, "_void_council"):
        return JSONResponse({"error": "council not available"}, status_code=503)
    try:
        from app.orchestrator.void_council import gather_council_evidence
        evidence = gather_council_evidence()
    except Exception as exc:
        return JSONResponse({"success": False, "error": "evidence_gather_failed", "detail": str(exc)}, status_code=500)
    return JSONResponse(
        ZQM_AIResponse.ok(
            data={"evidence": evidence},
            message=f"{len(evidence)} evidence line(s)",
        ).model_dump(mode="json")
    )


@router.get("/sessions")
async def council_sessions(
    request: Request,
    limit: int = 20,
    auth: Dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None or not hasattr(orch, "_void_council"):
        return JSONResponse({"error": "council not available"}, status_code=503)
    try:
        rows = await orch._void_council.review_history(limit=min(limit, 200))
    except Exception as exc:
        return JSONResponse({"success": False, "error": "sessions_read_failed", "detail": str(exc)}, status_code=500)
    return JSONResponse(
        ZQM_AIResponse.ok(
            data={"sessions": rows, "count": len(rows)},
            message=f"{len(rows)} council session(s)",
        ).model_dump(mode="json")
    )
