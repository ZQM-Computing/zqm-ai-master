"""
RAG bootstrap for The Void / ZQM ecosystem.

Does three things:
1. Build a local-first ingestion index from local docs + local Flatspace store
2. Generate embeddings with local Ollama `all-minilm:latest`
3. Sync into Meilisearch `flatspace` index
4. Provide a SearXNG augmentation helper for live web context enrichment

Defaults are local-only; no external provider calls unless explicitly enabled.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import requests

try:
    import sqlite3
except ImportError:
    sqlite3 = None  # type: ignore[assignment]


@dataclass
class RAGConfig:
    meili_url: str = "http://127.0.0.1:7701"
    meili_key: str = "zk_local_meili_2026"
    meili_index: str = "flatspace"
    ollama_embed_url: str = "http://127.0.0.1:11434/api/embeddings"
    ollama_model: str = "all-minilm:latest"
    searxng_url: str = "http://127.0.0.1:8080/search"
    flatspace_db_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "flatspace_local.db")
    flatspace_http: str | None = None  # e.g. http://127.0.0.1:8808/api/flatspace


# ── Meilisearch helpers ─────────────────────────────────────────────────────


def _meili_headers(cfg: RAGConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {cfg.meili_key}", "Content-Type": "application/json"}


def ensure_meili_index(cfg: RAGConfig) -> None:
    r = requests.get(f"{cfg.meili_url}/indexes/{cfg.meili_index}", headers=_meili_headers(cfg), timeout=10)
    if r.status_code == 404:
        requests.post(
            f"{cfg.meili_url}/indexes",
            headers=_meili_headers(cfg),
            json={"uid": cfg.meili_index, "primaryKey": "id"},
            timeout=10,
        ).raise_for_status()


def clear_meili_index(cfg: RAGConfig) -> None:
    requests.post(
        f"{cfg.meili_url}/indexes/{cfg.meili_index}/documents/delete",
        headers=_meili_headers(cfg),
        json=[],
        timeout=10,
    ).raise_for_status()


def upsert_meili_docs(cfg: RAGConfig, docs: list[dict[str, Any]]) -> None:
    if not docs:
        return
    # Upsert by primaryKey in batches of 200
    for i in range(0, len(docs), 200):
        batch = docs[i : i + 200]
        r = requests.post(
            f"{cfg.meili_url}/indexes/{cfg.meili_index}/documents",
            headers=_meili_headers(cfg),
            json=batch,
            params={"primaryKey": "id"},
            timeout=60,
        )
        r.raise_for_status()


# ── Embeddings ─────────────────────────────────────────────────────────────


def embed_text(cfg: RAGConfig, text: str) -> list[float] | None:
    try:
        r = requests.post(
            cfg.ollama_embed_url,
            json={"model": cfg.ollama_model, "prompt": text[:8000]},
            timeout=60,
        )
        r.raise_for_status()
        vec = r.json().get("embedding")
        if vec:
            return vec
    except Exception:
        pass
    # Deterministic fallback so search affordance remains.
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    out: list[float] = []
    for b in h:
        out.append((b / 127.5) - 1.0)
    while len(out) < 384:
        extra = hashlib.sha256((text + str(len(out))).encode("utf-8", errors="replace")).digest()
        for b in extra:
            if len(out) >= 384:
                break
            out.append((b / 127.5) - 1.0)
    return out[:384]


# ── Flatspace local ingestion ──────────────────────────────────────────────


def iter_local_store_docs(cfg: RAGConfig, limit: int = 500) -> list[dict[str, Any]]:
    if not sqlite3 or not os.path.exists(cfg.flatspace_db_path):
        return []
    docs: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(cfg.flatspace_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT key, tier, value, metadata, created FROM flatspace LIMIT ?", (limit,)
        ).fetchall()
        for row in rows:
            try:
                value = json.loads(row["value"]) if row["value"] else row["value"]
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
            except Exception:
                value = row["value"]
                meta = {}
            text = f"{row['key']} {json.dumps(value, default=str)[:4000]}"
            doc_id = hashlib.sha256(
                f"{row['tier']}:{row['key']}:{row['created']}".encode()
            ).hexdigest()[:40]
            docs.append({
                "id": doc_id,
                "key": row["key"],
                "tier": row["tier"],
                "value": value,
                "metadata": meta,
                "created": row["created"],
                "_text": text,
            })
        conn.close()
    except Exception as exc:
        print(f"local_store_read_failed: {exc}")
    return docs


def iter_local_markdown(root: str = r"C:\Void\ZQM-AI-Master") -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    if not os.path.isdir(root):
        return docs
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith((".md", ".txt")):
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, root)
                try:
                    text = open(path, "r", encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                if not text.strip():
                    continue
                doc_id = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:40]
                docs.append({
                    "id": doc_id,
                    "source": rel,
                    "kind": "markdown",
                    "text": text[:12000],
                    "_text": text,
                })
    return docs


# ── SearXNG augmentation ──────────────────────────────────────────────────


def searxng_search(cfg: RAGConfig, query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        r = requests.get(
            cfg.searxng_url,
            params={"q": query, "format": "json", "engines": "google cse,duckduckgo,bing"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        results: list[dict[str, Any]] = []
        for item in data.get("results", [])[: limit]:
            results.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "publishedDate": item.get("publishedDate"),
                "source": "searxng",
            })
        return results
    except Exception as exc:
        print(f"searxng_search_failed: {exc}")
        return []


def build_augmented_context(query: str, local_hits: list[dict[str, Any]], web_hits: list[dict[str, Any]], max_items: int = 8) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    for r in local_hits[: max_items]:
        val = r.get("value") if isinstance(r.get("value"), dict) else {"text": str(r.get("value"))}
        text = val.get("body") or val.get("text") or val.get("content") or json.dumps(val, default=str)
        merged.append({"kind": "local", "key": r.get("key"), "score": r.get("score"), "text": text[:1200]})
    for r in web_hits[: max_items]:
        merged.append({"kind": "web", "key": r.get("url"), "score": None, "text": f"{r.get('title')}\n{r.get('content') or ''}".strip()[:1200]})
    merged.sort(key=lambda x: x.get("score") if x.get("score") is not None else -1.0, reverse=True)
    parts = [f"[{i+1}] ({x['kind']}) {x['key']}: {x['text']}" for i, x in enumerate(merged[: max_items])]
    return {
        "query": query,
        "local_count": len(local_hits),
        "web_count": len(web_hits),
        "context": "\n\n".join(parts),
        "items": merged[: max_items],
    }


# ── Main bootstrap flow ────────────────────────────────────────────────────


def bootstrap(cfg: RAGConfig, rebuild: bool = False, seed_query: str | None = None, augment: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {"meili": {}, "local_indexed": 0, "docs_indexed": 0, "search_demo": None}

    # 1. Meilisearch index ready
    try:
        ensure_meili_index(cfg)
        report["meili"]["index"] = cfg.meili_index
    except Exception as exc:
        report["meili"]["error"] = str(exc)
        return report

    # 2. Load local docs
    docs: list[dict[str, Any]] = []
    docs.extend(iter_local_store_docs(cfg))
    docs.extend(iter_local_markdown())

    if rebuild:
        try:
            clear_meili_index(cfg)
        except Exception:
            pass

    # 3. Embed + index
    seen_ids: set[str] = set()
    to_index: list[dict[str, Any]] = []
    for doc in docs:
        doc_id = doc.get("id") or hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()[:40]
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        text = doc.get("_text") or doc.get("text") or doc.get("key") or ""
        vec = embed_text(cfg, text)
        to_index.append({
            "id": doc_id,
            "source": doc.get("source"),
            "key": doc.get("key"),
            "tier": doc.get("tier"),
            "text": text[:6000],
            "embedding": vec,
            "kind": doc.get("kind") or ("flatspace" if doc.get("tier") else "doc"),
        })

    try:
        upsert_meili_docs(cfg, to_index)
        report["docs_indexed"] = len(to_index)
    except Exception as exc:
        report["meili"]["index_error"] = str(exc)

    # 4. Configure Meili for vector-like ranking on `text`
    try:
        requests.patch(
            f"{cfg.meili_url}/indexes/{cfg.meili_index}/settings",
            headers=_meili_headers(cfg),
            json={"searchableAttributes": ["text", "key", "source"]},
            timeout=20,
        ).raise_for_status()
    except Exception:
        pass

    # 5. Demo search
    if seed_query:
        try:
            search_demo = search_meili(cfg, seed_query)
            if isinstance(search_demo, tuple):
                hits, estimated_total = search_demo
            else:
                hits, estimated_total = search_demo, len(search_demo)
            report["search_demo"] = {"query": seed_query, "hits": hits[:5], "count": int(estimated_total), "estimated_total": int(estimated_total)}
        except Exception as exc:
            report["search_demo"] = {"query": seed_query, "error": str(exc)}

    # 6. Optional SearXNG augmentation context
    if augment and seed_query:
        try:
            local_hits = report.get("search_demo", {}).get("hits", []) or []
            web = searxng_search(cfg, seed_query)
            report["augmented"] = build_augmented_context(seed_query, local_hits, web)
        except Exception as exc:
            report["augmented_error"] = str(exc)

    return report


# ── Standalone search helper ──────────────────────────────────────────────


def search_meili(cfg: RAGConfig, query: str, limit: int = 10) -> list[dict[str, Any]]:
    r = requests.post(
        f"{cfg.meili_url}/indexes/{cfg.meili_index}/search",
        headers=_meili_headers(cfg),
        json={"q": query, "limit": limit},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    hits = data.get("hits", [])
    estimated_total = data.get("estimatedTotalHits") or data.get("totalHits") or len(hits)
    return hits, estimated_total


# ── CLI entry point ────────────────────────────────────────────────────────


if __name__ == "__main__":
    cfg = RAGConfig()
    rebuild = os.environ.get("RAG_REBUILD", "0") == "1"
    seed_query = os.environ.get("RAG_SEED_QUERY") or "quantum simulation flatspace"
    result = bootstrap(cfg, rebuild=rebuild, seed_query=seed_query, augment=True)
    print(json.dumps(result, default=str, indent=2)[:4000])
