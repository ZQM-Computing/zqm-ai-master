"""
The Void AI Orchestration System — ZQM FLATSPACE Service
Version: 2.0.0 | ZQM Computing LLC

Client for the ZQM FLATSPACE tiered memory management system.

FLATSPACE Memory Tiers:
  pollenstore   — Cold storage (long-term archive)
  bitgarden       — Hot storage (rapid recall)
  waxcell       — Immutable audit log
  entangle      — Distributed sync across Queens
  quantumcell   — Predictive prefetch
  voidcache    — Local volatile (managed by VoidCache directly)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logger import get_logger
from app.services.flatspace_local import LocalFlatSpaceStore

log = get_logger("flatspace-service")

# Backend fail-over mode:
#   remote  — always use the remote FLATSPACE API (never local)
#   local   — always use the local SQLite store (never remote)
#   auto    — try remote; on transport failure, fall back to local (default)
FLATSPACE_MODE = os.getenv("FLATSPACE_MODE", "auto").lower()


class FlatSpaceService:
    """
    ZQM FLATSPACE tiered memory integration.

    Provides read/write/delete access to the 6-tier FLATSPACE memory system.
    VoidCache (Level 6) is managed directly by the orchestrator.
    This service handles Levels 1–5 via the remote FLATSPACE API, with a
    transparent fail-over to a local SQLite store (LocalFlatSpaceStore) when the
    remote backend is unreachable (so memory/self-improve/task-history
    stay durable and real even when FLATSPACE is down).
    """

    def __init__(self) -> None:
        self._timeout = max(int(
            os.getenv("ZQM_FLATSPACE_TIMEOUT", "5")
        ), 2)
        self._local = LocalFlatSpaceStore()
        self._remote_known_down = False

    # ── Health ──────────────────────────────────────────────────────
    async def health_check(self) -> bool:
        """Ping FLATSPACE endpoint. Returns True if reachable (or local store active)."""
        if FLATSPACE_MODE == "local":
            return True
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    settings.flatspace_endpoint.replace("/store", "/health")
                )
                return resp.status_code < 500
        except Exception as exc:
            log.debug("FLATSPACE health check failed", error=str(exc))
            # In auto mode the local store covers us; report healthy locally.
            if FLATSPACE_MODE == "auto":
                self._remote_known_down = True
            return FLATSPACE_MODE == "auto"

    def _local_active(self) -> bool:
        return FLATSPACE_MODE == "local"

    # ── Embeddings (best-effort, for semantic store/search) ────────────
    async def _embed_text(self, text: str) -> Optional[list]:
        """Embed text for semantic search. Returns None on any failure."""
        # Prefer direct local Ollama embeddings to avoid mesh model availability issues.
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/embeddings",
                    json={"model": "all-minilm:latest", "prompt": text[:8000]},
                )
                r.raise_for_status()
                vec = r.json().get("embedding")
                if vec:
                    return vec
        except Exception as exc:
            log.debug("FLATSPACE local embed failed", error=str(exc))

        # Fallback to mesh router if local backend is unavailable.
        try:
            from app.services.mesh_ollama import router as mesh_ollama
            data = await mesh_ollama.embed(settings.ollama_default_model, text[:8000])
            vec = data.get("embedding")
            if vec:
                return vec
        except Exception as exc:
            log.debug("FLATSPACE mesh embed failed", error=str(exc))
        try:
            from app.services.mesh_ollama import router as mesh_ollama
            data = await mesh_ollama.embed(settings.ollama_default_model, text[:8000])
            vec = data.get("embedding")
            if vec:
                return vec
        except Exception as exc:
            log.debug("FLATSPACE mesh embed failed", error=str(exc))

        # Standalone fallback: deterministic pseudo-embedding from content hash.
        # Not semantically meaningful, but preserves search affordance without
        # requiring an external Ollama backend.
        try:
            import hashlib
            h = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
            # 384-dim float vector in [-1,1]
            out: List[float] = []
            for b in h:
                out.append((b / 127.5) - 1.0)
            # Extend to 384 by re-hashing shifted slices
            while len(out) < 384:
                extra = hashlib.sha256((text + str(len(out))).encode("utf-8", errors="replace")).digest()
                for b in extra:
                    if len(out) >= 384:
                        break
                    out.append((b / 127.5) - 1.0)
            return out[:384]
        except Exception as exc:
            log.debug("FLATSPACE local fallback embed failed", error=str(exc))
            return None

    async def _embed_for(self, key: str, value: Any) -> Optional[list]:
        """Build an embedding for a stored record (key + value)."""
        text = f"{key} {json.dumps(value, default=str)[:4000]}"
        return await self._embed_text(text)

    # ── Write ─────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def store(
        self,
        key: str,
        value: Any,
        tier: str = "bitgarden",
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Store a value in the specified FLATSPACE memory tier.

        Args:
            key: Storage key
            value: Value to store (must be JSON-serializable)
            tier: Memory tier (pollenstore | bitgarden | waxcell | entangle)
            ttl: Optional TTL in seconds (0 = permanent)
            metadata: Optional metadata to store alongside the value

        Returns:
            FLATSPACE store response
        """
        endpoint = settings.flatspace_endpoint
        payload = {
            "key": key,
            "value": value,
            "tier": tier,
            "ttl": ttl or 0,
            "metadata": metadata or {},
            "zqm_ai_id": settings.zqm_ai_id,
        }

        if FLATSPACE_MODE != "remote" and self._remote_known_down:
            emb = await self._embed_for(key, value)
            return self._local.store(key, value, tier, ttl, metadata, embedding=emb)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                log.debug("FLATSPACE store successful", key=key, tier=tier)
                self._remote_known_down = False
                return resp.json()
        except httpx.HTTPError as exc:
            # In auto mode a dead remote is EXPECTED degradation — local
            # fallback covers us, so don't log it as a failure.
            if FLATSPACE_MODE != "remote":
                self._remote_known_down = True
                log.debug("FLATSPACE remote store unreachable (falling back to local)", key=key, tier=tier)
            else:
                log.warning("FLATSPACE store failed", key=key, tier=tier, error=str(exc))
            if FLATSPACE_MODE != "remote":
                # Best-effort semantic embedding for local semantic search.
                emb = await self._embed_for(key, value)
                return self._local.store(key, value, tier, ttl, metadata, embedding=emb)
            return {"success": False, "error": str(exc), "key": key}

    # ── Read ──────────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        key: str,
        tier: str = "bitgarden",
    ) -> Optional[Any]:
        """
        Retrieve a value from the specified FLATSPACE memory tier.

        Returns:
            Stored value, or None if not found
        """
        endpoint = settings.flatspace_endpoint
        if FLATSPACE_MODE != "remote" and self._remote_known_down:
            return self._local.retrieve(key, tier)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    endpoint.replace("/store", f"/retrieve/{key}"),
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                log.debug("FLATSPACE retrieve successful", key=key, tier=tier)
                self._remote_known_down = False
                return data.get("value")
        except httpx.HTTPError as exc:
            if FLATSPACE_MODE != "remote":
                self._remote_known_down = True
                log.debug("FLATSPACE remote retrieve unreachable (falling back to local)", key=key, tier=tier)
                return self._local.retrieve(key, tier)
            log.warning("FLATSPACE retrieve failed", key=key, tier=tier, error=str(exc))
            return None

    async def retrieve_multi(
        self,
        keys: list[str],
        tier: str = "bitgarden",
    ) -> Dict[str, Any]:
        """Batch retrieve multiple keys from FLATSPACE."""
        endpoint = settings.flatspace_endpoint
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    endpoint.replace("/store", "/retrieve/batch"),
                    json={"keys": keys, "tier": tier},
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                return resp.json().get("results", {})
        except Exception as exc:
            log.warning("FLATSPACE batch retrieve failed", error=str(exc))
            if FLATSPACE_MODE != "remote":
                return self._local.retrieve_multi(keys, tier)
            return {}

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, key: str, tier: str = "bitgarden") -> bool:
        """Delete a key from FLATSPACE. Returns True on success."""
        endpoint = settings.flatspace_endpoint.replace("/store", f"/{key}")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.delete(
                    endpoint,
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                return resp.status_code in (200, 204)
        except Exception as exc:
            log.warning("FLATSPACE delete failed", key=key, error=str(exc))
            if FLATSPACE_MODE != "remote":
                return self._local.delete(key, tier)
            return False

    # ── Search ────────────────────────────────────────────────────────────────

    async def list_keys(
        self, prefix: str, tier: str = "bitgarden", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Prefix-key listing (no embedding). Local-only: the remote FLATSPACE
        has no key-prefix endpoint, so this always uses the local store."""
        return self._local.list_keys(prefix, tier, limit)

    async def search(
        self,
        query: str,
        tier: str = "bitgarden",
        limit: int = 10,
    ) -> list[Dict[str, Any]]:
        """
        Search FLATSPACE memory by query string (semantic or key-based).
        Returns matched records.
        """
        # Prefer local semantic search when embeddings are available.
        try:
            qv = await self._embed_text(query)
        except Exception:
            qv = None
        if qv:
            try:
                return self._local.search(query, tier, limit, query_embedding=qv)
            except Exception:
                pass

        # Meilisearch full-text fallback when configured.
        try:
            from app.services.meilisearch_service import search as meili_search
            meili_hits = meili_search(tier, query, limit)
            if meili_hits:
                return meili_hits[:limit]
        except Exception:
            pass

        # Chroma vector fallback when enabled.
        try:
            from app.services.chroma_service import search as chroma_search
            chroma_hits = chroma_search(query, limit=limit)
            if chroma_hits:
                return chroma_hits[:limit]
        except Exception:
            pass

        base = settings.flatspace_endpoint.rsplit("/store", 1)[0]
        if FLATSPACE_MODE != "remote" and self._remote_known_down:
            return self._local.search(query, tier, limit)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{base}/search",
                    json={"query": query, "tier": tier, "limit": limit},
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                return resp.json().get("results", [])
        except Exception as exc:
            log.warning("FLATSPACE search failed", query=query, error=str(exc))
            if FLATSPACE_MODE != "remote":
                return self._local.search(query, tier, limit)
            return []

    # ── Tier info ─────────────────────────────────────────────────────────────

    async def get_tier_stats(self) -> Dict[str, Any]:
        """Fetch usage statistics for all FLATSPACE tiers.

        Prefers the remote tier store; on any failure (the remote is almost
        always down in this deployment) falls back to the local SQLite store,
        which is the source of truth for what's actually persisted here.
        """
        base = settings.flatspace_endpoint.rsplit("/store", 1)[0]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{base}/stats",
                    headers={"X-ZQM_AI-ID": settings.zqm_ai_id},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.debug("FLATSPACE remote stats unavailable, using local store", error=str(exc))
            try:
                # LocalFlatSpaceStore.get_tier_stats is a synchronous method.
                return self._local.get_tier_stats()
            except Exception as lex:
                return {
                    "tiers": ["pollenstore", "bitgarden", "waxcell", "entangle"],
                    "status": "unreachable",
                    "error": str(lex),
                }
