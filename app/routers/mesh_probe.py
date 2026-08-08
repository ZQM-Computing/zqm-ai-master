"""
The Void AI Orchestration System — /api/mesh Probe Router
Version: 2.1.0 | ZQM Computing LLC

Lightweight diagnostic surface for mesh backends + inference probes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import get_current_token_payload
from app.services.mesh_ollama import DEFAULT_BACKENDS, MeshOllamaRouter

router = APIRouter(prefix="/api/mesh", tags=["Mesh"])


@router.get("/backends")
async def mesh_backends(
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Return the canonical backend map + current health flags from a fresh
    MeshOllamaRouter refresh. Does NOT call inference — cheap and safe."""
    router = MeshOllamaRouter()
    await router.refresh(force=True)
    out: list[dict[str, Any]] = []
    for b in DEFAULT_BACKENDS:
        out.append({
            "name": b["name"],
            "url": b["url"],
            "local": b.get("local", False),
            "healthy": router._health.get(b["name"], False),
            "models": len(router._models.get(b["name"], [])),
            "down_until": router._down_until.get(b["name"], 0.0),
            "status_failures": router._status_failures.get(b["name"], 0),
        })
    return JSONResponse({"backends": out, "model_index_size": len(router._model_index)})


@router.post("/probe")
async def mesh_probe_infer(
    request: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Probe actual inference on every backend that can serve `model`.
    Returns per-backend status + first successful chat payload, or the last
    failure seen. Safe short timeout (8s) so this endpoint never hangs."""
    model = str(request.get("model") or "phi3:mini")
    prompt = str(request.get("prompt") or "ping")
    router = MeshOllamaRouter()
    await router.refresh(force=True)
    backends = router._ranked_backends(model)
    if not backends:
        backends = [b for b in DEFAULT_BACKENDS if b.get("local")]
    results = []
    last_err = None
    first_ok = None
    for b in backends[:6]:
        try:
            data = await router._post(
                b, model,
                [{"role": "user", "content": prompt}],
                timeout=8.0,
                opts={},
            )
            last_err = None
            entry = {
                "backend": b["name"],
                "url": b["url"],
                "ok": True,
                "model": model,
                "message": data.get("message", {}).get("content", "")[:80],
            }
            results.append(entry)
            first_ok = entry
            break
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:120]}"
            results.append({
                "backend": b["name"],
                "url": b["url"],
                "ok": False,
                "model": model,
                "error": last_err,
            })
            continue
    payload = {
        "probe": {
            "model": model,
            "prompt": prompt,
            "results": results,
            "first_ok": first_ok,
            "last_err": last_err,
        }
    }
    status = 200 if first_ok else 503
    return JSONResponse(payload, status_code=status)
