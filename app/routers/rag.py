"""
The Void AI Orchestration System — /api/rag Router
Version: 2.1.0 | ZQM Computing LLC

End-to-end retrieval-augmented generation over local FLATSPACE memory.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import get_current_token_payload
from app.models.response import ZQM_AIResponse

router = APIRouter(prefix="/api/rag", tags=["RAG"])
log = get_logger("router.rag")


async def _searxng_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch web results from SearXNG for query augmentation."""
    base = (settings.searxng_url or "").rstrip("/")
    if not base:
        return []
    url = f"{base}/search?q={urllib.parse.quote(query)}&format=json&engines=google,bing,duckduckgo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "zqm-rag/2.1"})
        with urllib.request.urlopen(req, timeout=12) as r:
            payload = json.loads(r.read().decode())
        results = payload.get("results", [])[:limit]
        out = []
        for item in results:
            title = item.get("title") or ""
            snippet = item.get("content") or item.get("snippet") or ""
            url_item = item.get("url") or item.get("link") or ""
            if title or snippet:
                out.append({"title": title, "snippet": snippet, "url": url_item})
        return out
    except Exception:
        return []


def _build_context(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
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
        if not isinstance(text, str):
            text = str(text)
        parts.append(f"[{i}] {r.get('key')}: {text[:1500]}")
    return "\n\n".join(parts)


def _embed_text(text: str) -> list[float] | None:
    if not text:
        return None
    backend = os.getenv("RAG_RERANK_EMBEDDING_BACKEND", "ollama").lower()
    if backend == "chroma" and settings.chroma_enabled:
        try:
            from app.services.chroma_service import _chroma_url
            url = _chroma_url("/api/v1/embeddings")
            if not url:
                return None
            payload = json.dumps({"model": "bge-m3", "prompt": text[:8000]}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                emb_data = json.loads(r.read().decode())
            vec = emb_data.get("embedding")
            if isinstance(vec, list) and vec:
                return [float(x) for x in vec]
        except Exception:
            return None
    try:
        payload = json.dumps({"model": "bge-m3", "input": text[:8000]}).encode()
        req = urllib.request.Request(
            f"{(settings.ollama_base_url or 'http://127.0.0.1:11434').rstrip('/')}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            emb_data = json.loads(r.read().decode())
        vec = (emb_data.get("embeddings") or [None])[0]
        if isinstance(vec, list) and vec:
            return [float(x) for x in vec]
    except Exception:
        return None
    return None


async def _rerank_results(
    query: str,
    results: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Stage-2 rerank using configured embedding backend, with fallback policy."""
    if not results:
        return []
    if not os.getenv("RAG_RERANK_ENABLED", "true").lower() in ("1", "true", "yes"):
        return results[: max(1, limit)]

    query_vec = _embed_text(query)
    if not query_vec:
        fallback = os.getenv("RAG_RERANK_FALLBACK", "preserve_order").lower()
        if fallback == "none":
            return []
        return results[: max(1, limit)]

    def _cosine(a, b):
        if not a or not b or len(a) != len(b):
            return None
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return None
        return dot / (na * nb)

    scored: list[tuple[float, dict[str, Any]]] = []
    provenance: dict[str, Any] = {"backend": os.getenv("RAG_RERANK_EMBEDDING_BACKEND", "ollama"), "query_chars": len(query)}
    for item in results:
        vec_raw = item.get("embedding")
        vec = [float(x) for x in vec_raw] if isinstance(vec_raw, list) else None
        if not vec:
            vec = _embed_text(str(item.get("value") or item.get("text") or item.get("output") or ""))
        score = _cosine(query_vec, vec)
        scored.append((score if score is not None else -1.0, item))
    provenance["scored_items"] = len(scored)
    scored.sort(key=lambda x: x[0], reverse=True)
    out = [it for _, it in scored[: max(1, limit)]]
    for it in out:
        it.setdefault("rerank", provenance)
    return out


@router.post("/search")
async def hybrid_search(
    request: Request,
    body: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Hybrid RAG search: Meilisearch full-text + Chroma vector, reranked by bge-m3."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not ready"}, status_code=503)

    query_text = (body.get("query") or "").strip()
    if not query_text:
        return JSONResponse(
            ZQM_AIResponse.ok(data={"sources": []}, message="missing query").model_dump(mode="json")
        )
    try:
        limit = int(body.get("limit", 5))
    except Exception:
        limit = 5
    tier = body.get("tier")
    if tier is not None:
        tier = str(tier).strip() or None

    # Build parallel retrieval tasks.
    meili_limit = max(limit * 2, 20)
    chroma_limit = max(limit * 2, 20)

    async def _meili():
        hits = []
        try:
            from app.services.meilisearch_service import search as meili_search
            hits = meili_search(settings.meilisearch_default_index, query_text, meili_limit)
        except Exception as exc:
            log.debug("Hybrid RAG Meilisearch failed", error=str(exc))
        return hits

    async def _chroma():
        hits = []
        try:
            if settings.chroma_enabled:
                from app.services.chroma_service import search as chroma_search
                hits = chroma_search(query_text, collection=settings.chroma_collection, limit=chroma_limit)
        except Exception as exc:
            log.debug("Hybrid RAG Chroma failed", error=str(exc))
        return hits

    meili_hits, chroma_hits = await asyncio.gather(_meili(), _chroma())

    merged: dict[str, dict[str, Any]] = {}

    def _ingest(hit: dict[str, Any], score_source: str) -> None:
        key = hit.get("key")
        if not key:
            return
        raw = hit.get("value") or hit.get("text") or hit.get("output") or ""
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        entry = merged.setdefault(
            str(key),
            {
                "key": str(key),
                "text": text,
                "score": 0.0,
                "tier": hit.get("tier") or (tier or "flatspace"),
            },
        )
        if score_source == "meili":
            score = hit.get("score")
            if isinstance(score, (int, float)):
                entry["score"] += float(score)
                if not entry.get("tier"):
                    entry["tier"] = hit.get("tier") or "flatspace"
        elif score_source == "chroma":
            score = hit.get("score")
            if isinstance(score, (int, float)):
                entry["score"] += float(score)
            chroma_tier = hit.get("tier")
            if chroma_tier:
                entry["tier"] = chroma_tier

    for hit in meili_hits:
        _ingest(hit, "meili")
    for hit in chroma_hits:
        _ingest(hit, "chroma")

    merged_items = list(merged.values())
    merged_items.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    candidates = merged_items[: max(limit * 2, 1)]

    # Fallback to rerank path: preserve embedding key names expected by _rerank_results.
    reranked = []
    try:
        prepared = []
        for item in candidates:
            prepared.append(
                {
                    "key": item.get("key"),
                    "value": item.get("text"),
                    "text": item.get("text"),
                    "score": item.get("score"),
                    "tier": item.get("tier"),
                }
            )
        reranked = await _rerank_results(query_text, prepared, limit=max(1, limit))
    except Exception as exc:
        log.debug("Hybrid RAG rerank skipped", error=str(exc))
        reranked = candidates[: max(1, limit)]

    sources = []
    for r in reranked[: max(1, limit)]:
        text = r.get("text") or r.get("value") or ""
        if not isinstance(text, str):
            text = json.dumps(text, default=str)
        sources.append(
            {
                "key": r.get("key"),
                "text": text[:4000],
                "score": r.get("score"),
                "tier": r.get("tier") or (tier or "flatspace"),
            }
        )

    return JSONResponse(
        ZQM_AIResponse.ok(
            data={"sources": sources, "count": len(sources)},
            message=f"Hybrid RAG search complete: {len(sources)} sources",
        ).model_dump(mode="json")
    )


@router.get("/diag")
async def diag(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Diagnostic RAG path: retrieval + generation without web augmentation."""
    orch = getattr(request.app.state, "orchestrator", None)
    fs = getattr(orch, "flatspace", None) if orch else None
    results: list[dict[str, Any]] = []
    context = ""
    sources: list[dict[str, Any]] = []
    answer = ""
    model_used = None
    error: str | None = None
    if fs is None:
        error = "orchestrator or flatspace missing"
    else:
        try:
            q = "quantum simulation flatspace"
            results = await fs.search(query=q, tier="bitgarden", limit=3)
            context = _build_context(results)
            sources = [
                {"key": r.get("key"), "score": r.get("score"), "tier": r.get("tier")}
                for r in results
            ]
            if context:
                try:
                    from app.core.config import settings as _rag_settings
                    from app.services.mesh_ollama import router as mesh_ollama
                    mesh = getattr(orch, "mesh", None) or mesh_ollama
                    prompt = (
                        "You are a careful assistant. "
                        "Use the context below to answer the question. "
                        "Summarize any relevant information from the context. "
                        "If the context mentions related concepts, explain them. "
                        "Be helpful and informative based on what is provided.\n\n"
                        f"Context:\n{context}\n\n"
                        f"Question: {q}\n\n"
                        "Answer:"
                    )
                    data = await mesh.chat(
                        _rag_settings.ollama_default_model,
                        [{"role": "user", "content": prompt}],
                        timeout=120,
                    )
                    answer = (data.get("message") or {}).get("content", "").strip()
                    model_used = data.get("model")
                except Exception as exc:
                    error = f"generation failed: {exc}"
            else:
                answer = "No relevant memory found in FLATSPACE."
        except Exception as exc:
            error = f"retrieval failed: {exc}"
    payload = {
        "results_count": len(results),
        "context_length": len(context),
        "sources": sources,
        "answer": answer,
        "model_used": model_used,
        "error": error,
    }
    if error:
        return JSONResponse(payload, status_code=500)
    return JSONResponse(payload)


@router.post("/query")
async def query(
    request: Request,
    body: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """
    RAG query: retrieve top-k FLATSPACE chunks and generate a grounded answer.
    """
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        return JSONResponse({"error": "orchestrator not ready"}, status_code=503)

    query_text = (body.get("query") or "").strip()
    if not query_text:
        return JSONResponse(ZQM_AIResponse.ok(data={"answer": "", "sources": []}, message="missing query").model_dump(mode="json"))

    tier = body.get("tier", "bitgarden")
    limit = int(body.get("limit", 5))
    web_augment = bool(body.get("web_augment", False))

    # Retrieve local context
    try:
        results = await orch.flatspace.search(query=query_text, tier=tier, limit=limit)
    except Exception as exc:
        log.warning("RAG retrieval failed", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "retrieval_failed", "detail": str(exc)},
        )

    context = _build_context(results)
    sources = [
        {"key": r.get("key"), "score": r.get("score"), "tier": r.get("tier")}
        for r in results
    ]

    # Optional rerank stage using configured reranker backend.
    reranked: list[dict[str, Any]] = []
    try:
        reranked = await _rerank_results(query_text, results, limit=max(1, limit))
    except Exception as exc:
        log.debug("RAG rerank skipped", error=str(exc))
    effective_results = reranked if reranked else results

    context = _build_context(effective_results)
    sources = [
        {"key": r.get("key"), "score": r.get("score"), "tier": r.get("tier")}
        for r in effective_results
    ]

    # Optional web augmentation via SearXNG
    web_context = ""
    web_sources: list[dict[str, Any]] = []
    if web_augment:
        try:
            web_results = await _searxng_search(query_text, limit=settings.searxng_max_results)
            if web_results:
                web_parts = []
                for i, item in enumerate(web_results, 1):
                    web_parts.append(
                        f"[W{i}] {item.get('title','')}: {item.get('snippet','')} ({item.get('url','')})"
                    )
                    web_sources.append(
                        {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("snippet")}
                    )
                web_context = "\n\n".join(web_parts)
        except Exception as exc:
            log.warning("RAG web augmentation failed", error=str(exc))

    # Generate answer
    answer = ""
    model_used = None
    if context or web_context:
        prompt_parts = [
            "You are a careful assistant.",
            "Use the context below to answer the question.",
            "Summarize relevant information from the context.",
            "If the context mentions related concepts, explain them.",
            "Be helpful and informative based on what is provided.",
        ]
        if web_context:
            prompt_parts.append("Web augmentation results may contain supplementary information.")
        prompt_parts.append("\nContext:\n")
        parts = []
        if context:
            parts.append(context)
        if web_context:
            parts.append(web_context)
        prompt_parts.append("\n\n".join(parts))
        prompt_parts.append(f"\n\nQuestion: {query_text}\n\nAnswer:")
        prompt = "\n".join(prompt_parts)
        try:
            from app.core.config import settings as _rag_settings
            from app.services.mesh_ollama import router as mesh_ollama
            mesh = getattr(orch, "mesh", None) or mesh_ollama
            data = await mesh.chat(
                _rag_settings.ollama_default_model,
                [{"role": "user", "content": prompt}],
                timeout=120,
            )
            answer = (data.get("message") or {}).get("content", "").strip()
            model_used = data.get("model")
        except Exception as exc:
            log.warning("RAG generation failed", error=str(exc))
            answer = f"Retrieval succeeded, but generation failed: {exc}"
    else:
        answer = "No relevant memory found in FLATSPACE."

    return JSONResponse(
        ZQM_AIResponse.ok(
            data={
                "answer": answer,
                "sources": sources,
                "model_used": model_used,
                "context_length": len(context),
                "web_augmented": bool(web_context),
                "web_sources": web_sources,
            },
            message=f"RAG query complete: {len(sources)} sources",
        ).model_dump(mode="json")
    )
