"""
Reasoning router: /api/reasoning/query

Apply a reasoning pattern to a question with retrieved context.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import get_current_token_payload
from app.reasoning.patterns import get_pattern

router = APIRouter(prefix="/api/reasoning", tags=["Reasoning"])
log = get_logger("router.reasoning")


@router.post("/query")
async def query(
    request: Request,
    body: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not ready"}, status_code=503)

    question = (body.get("query") or "").strip()
    if not question:
        return JSONResponse({"error": "missing query"}, status_code=400)

    tier = body.get("tier", "bitgarden")
    limit = int(body.get("limit", 5))
    pattern_name = body.get("pattern", "chain_of_thought")

    # Retrieve context
    try:
        results = await orch.flatspace.search(query=question, tier=tier, limit=limit)
    except Exception as exc:
        log.warning("reasoning retrieval failed", error=str(exc))
        return JSONResponse({"error": "retrieval_failed", "detail": str(exc)}, status_code=500)

    # Build context
    parts = []
    for i, r in enumerate(results, 1):
        val = r.get("value")
        if isinstance(val, dict):
            text = (
                val.get("output")
                or val.get("input")
                or val.get("body")
                or val.get("text")
                or val.get("content")
                or str(val)
            )
        else:
            text = str(val)
        parts.append(f"[{i}] {r.get('key')}: {text[:1500]}")
    context = "\n\n".join(parts) if parts else ""

    # Apply reasoning pattern
    pattern = get_pattern(pattern_name)
    try:
        result = await pattern.apply(question, context, settings.ollama_default_model)
    except Exception as exc:
        log.warning("reasoning pattern failed", pattern=pattern_name, error=str(exc))
        return JSONResponse({"error": "reasoning_failed", "detail": str(exc)}, status_code=500)

    payload = {
        "query": question,
        "pattern": pattern_name,
        "context_length": len(context),
        "sources": [
            {"key": r.get("key"), "score": r.get("score"), "tier": r.get("tier")}
            for r in results
        ],
        "result": result,
    }
    return JSONResponse(payload)
