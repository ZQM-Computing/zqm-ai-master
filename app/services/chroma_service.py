"""
Chroma vector-store fallback for FLATSPACE semantic search.

Uses settings.chroma_url and settings.chroma_collection.
Returns empty list when Chroma is not configured or unavailable.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("chroma-service")


def _chroma_url(path: str) -> str:
    base = (settings.chroma_url or "").rstrip("/")
    if not base:
        return ""
    return f"{base}{path}"


def search(query: str, collection: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Query Chroma collection by embedding text and returning top hits."""
    if not settings.chroma_enabled:
        return []

    coll = collection or settings.chroma_collection
    embed_url = _chroma_url("/api/v1/embeddings")
    query_url = _chroma_url(f"/api/v1/collections/{coll}/query")

    if not embed_url or not query_url:
        return []

    try:
        import urllib.request
        embed_payload = json.dumps({"model": "all-minilm:latest", "prompt": query[:8000]}).encode()
        req = urllib.request.Request(embed_url, data=embed_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            emb_data = json.loads(r.read().decode())
        vector = emb_data.get("embedding")
        if not vector:
            return []

        query_payload = json.dumps({"query_embeddings": [vector], "n_results": limit}).encode()
        req2 = urllib.request.Request(query_url, data=query_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req2, timeout=20) as r2:
            chroma_result = json.loads(r2.read().decode())

        hits = []
        ids = chroma_result.get("ids", [[]])[0]
        docs = chroma_result.get("documents", [[]])[0]
        dists = chroma_result.get("distances", [[]])[0]
        for i in range(min(limit, len(ids))):
            hits.append({
                "key": ids[i],
                "value": docs[i] if i < len(docs) else "",
                "score": 1.0 - float(dists[i]) if i < len(dists) else None,
                "tier": "chroma",
            })
        return hits
    except Exception as exc:
        log.debug("Chroma search failed", error=str(exc))
        return []


def health() -> bool:
    """Light Chroma health probe."""
    try:
        import urllib.request
        req = urllib.request.Request(_chroma_url("/api/v1/heartbeat"), method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 500
    except Exception:
        return False
