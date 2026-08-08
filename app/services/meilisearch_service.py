"""
Meilisearch search layer for FLATSPACE.

- Uses settings.meilisearch_url and settings.meilisearch_master_key.
- Provides search(query, limit) with graceful fallback when key is missing.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings

_MEILI_HEADERS = {"Content-Type": "application/json"}
if settings.meilisearch_master_key:
    _MEILI_HEADERS["Authorization"] = f"Bearer {settings.meilisearch_master_key}"


def _meili_url(path: str) -> str:
    base = (settings.meilisearch_url or "").rstrip("/")
    return f"{base}{path}"


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _meili_url(path)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_MEILI_HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return {"_http_status": exc.code, "_http_reason": exc.reason}
    except Exception as exc:
        return {"_error": str(exc)}


def ensure_index(index_name: str = "flatspace") -> dict[str, Any]:
    """Create the index if missing."""
    info = _request("GET", f"/indexes/{index_name}")
    if "_http_status" not in info and "indexUid" in info:
        return info
    payload = {"uid": index_name, "primaryKey": "key"}
    return _request("POST", "/indexes", payload)


def search(index_name: str, query: str, limit: int = 10, fields: list[str] | None = None) -> list[dict[str, Any]]:
    """Full-text search Meilisearch index. Returns empty list if not configured."""
    if not settings.meilisearch_master_key:
        return []
    payload: dict[str, Any] = {"q": query, "limit": limit}
    if fields:
        payload["attributesToSearchOn"] = fields
    resp = _request("POST", f"/indexes/{index_name}/search", payload)
    if "_error" in resp or "_http_status" in resp:
        return []
    hits = resp.get("hits", [])
    out = []
    for hit in hits:
        out.append({
            "key": hit.get("key"),
            "tier": hit.get("tier"),
            "value": hit.get("value"),
            "score": hit.get("_rankingScore") or hit.get("rankingScore") or 0.0,
            "metadata": hit.get("metadata") or {},
            "created": hit.get("created"),
            "local": False,
        })
    return out
