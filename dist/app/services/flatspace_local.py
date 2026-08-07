"""
The Void AI Orchestration System — Local FLATSPACE Store (SQLite fallback)

Version: 2.0.0 | ZQM Computing LLC

When the remote FLATSPACE tiered-memory backend (192.168.1.225:8808) is
unreachable, FlatSpaceService fails over to this local SQLite store so that:

  - memory tools (flatspace_search / flatspace_retrieve / flatspace_store) stay REAL
  - self-improvement findings persist durably (not lost on restart)
  - task-history / MCP audit records survive a process restart

This is a drop-in backend: it mirrors the method surface and return
shapes of FlatSpaceService so callers need no changes. Data lives in
`app/flatspace_local.db` (one table, JSON-serialized values).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logger import get_logger
log = get_logger("flatspace-local")


def _safe_json(text: Optional[str]) -> Optional[List[float]]:
    """Parse a stored embedding JSON blob back into a vector."""
    if not text:
        return None
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else None
    except Exception:
        return None


def _cosine(a: Optional[List[float]], b: Optional[List[float]]) -> Optional[float]:
    """Cosine similarity; None if either vector is missing/incompatible."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)
log = get_logger("flatspace-local")


def _db_path() -> str:
    # app/flatspace_local.db  (this file is app/services/flatspace_local.py)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "flatspace_local.db")


class LocalFlatSpaceStore:
    """
    Local, persistent stand-in for the remote FLATSPACE tiered memory system.

    Mirrors FlatSpaceService's public surface:
        store(key, value, tier, ttl, metadata) -> Dict
        retrieve(key, tier) -> Optional[Any]
        retrieve_multi(keys, tier) -> Dict[str, Any]
        delete(key, tier) -> bool
        search(query, tier, limit) -> List[Dict[str, Any]]
        get_tier_stats() -> Dict[str, Any]
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db = db_path or _db_path()
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS flatspace (
                key      TEXT NOT NULL,
                tier     TEXT NOT NULL,
                value    TEXT NOT NULL,
                metadata TEXT,
                ttl      INTEGER DEFAULT 0,
                created  REAL,
                embedding TEXT,
                PRIMARY KEY (key, tier)
            )
            """
        )
        # Migration: older flatspace_local.db files predate the embedding
        # column. ADD it if missing (CREATE TABLE IF NOT EXISTS won't
        # alter an existing table, and store() would otherwise throw
        # "table flatspace has no column named embedding".
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(flatspace)").fetchall()}
        if "embedding" not in cols:
            self._conn.execute("ALTER TABLE flatspace ADD COLUMN embedding TEXT")
        self._conn.commit()
        log.info("LocalFlatSpaceStore initialized", db=self._db)

    # ── Write ──────────────────────────────────────────────────────────
    def store(
        self,
        key: str,
        value: Any,
        tier: str = "bitgarden",
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        try:
            self._conn.execute(
                """
                INSERT INTO flatspace (key, tier, value, metadata, ttl, created, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key, tier) DO UPDATE SET
                    value=excluded.value,
                    metadata=excluded.metadata,
                    ttl=excluded.ttl,
                    created=excluded.created,
                    embedding=excluded.embedding
                """,
                (
                    key,
                    tier,
                    json.dumps(value, default=str),
                    json.dumps(metadata or {}, default=str),
                    int(ttl or 0),
                    time.time(),
                    json.dumps(embedding) if embedding else None,
                ),
            )
            self._conn.commit()
            return {"success": True, "key": key, "tier": tier, "local": True,
                    "embedded": embedding is not None}
        except Exception as exc:
            log.warning("LocalFlatSpaceStore store failed", key=key, error=str(exc))
            return {"success": False, "error": str(exc), "key": key, "local": True}

    # ── Read ───────────────────────────────────────────────────────────
    def retrieve(self, key: str, tier: str = "bitgarden") -> Optional[Any]:
        try:
            cur = self._conn.execute(
                "SELECT value FROM flatspace WHERE key=? AND tier=?", (key, tier)
            )
            row = cur.fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except Exception as exc:
            log.warning("LocalFlatSpaceStore retrieve failed", key=key, error=str(exc))
            return None

    def retrieve_multi(
        self, keys: List[str], tier: str = "bitgarden"
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            placeholders = ",".join("?" for _ in keys) or "?"
            cur = self._conn.execute(
                f"SELECT key, value FROM flatspace WHERE tier=? AND key IN ({placeholders})",
                (tier, *keys),
            )
            for k, v in cur.fetchall():
                try:
                    out[k] = json.loads(v)
                except Exception:
                    out[k] = v
        except Exception as exc:
            log.warning("LocalFlatSpaceStore retrieve_multi failed", error=str(exc))
        return out

    def delete(self, key: str, tier: str = "bitgarden") -> bool:
        try:
            self._conn.execute(
                "DELETE FROM flatspace WHERE key=? AND tier=?", (key, tier)
            )
            self._conn.commit()
            return True
        except Exception as exc:
            log.warning("LocalFlatSpaceStore delete failed", key=key, error=str(exc))
            return False

    # ── Search ────────────────────────────────────────────────────────
    def search(
        self, query: str, tier: str = "bitgarden", limit: int = 10,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            cur = self._conn.execute(
                "SELECT key, tier, value, metadata, created, embedding "
                "FROM flatspace WHERE tier=?", (tier,)
            )
            rows = cur.fetchall()

            # Semantic path: rank by cosine similarity to the query vector.
            if query_embedding:
                scored = []
                for key, t, v, meta, created, emb in rows:
                    sim = _cosine(query_embedding, _safe_json(emb))
                    if sim is None:
                        continue
                    scored.append((sim, key, t, v, meta, created))
                if scored:
                    scored.sort(key=lambda x: x[0], reverse=True)
                    out = []
                    for sim, key, t, v, meta, created in scored[: int(limit)]:
                        try:
                            val = json.loads(v)
                        except Exception:
                            val = v
                        out.append({
                            "key": key, "tier": t, "value": val,
                            "metadata": json.loads(meta) if meta else {},
                            "created": created, "local": True, "score": round(sim, 4),
                        })
                    return out

            # Substring fallback (original behaviour).
            q = f"%{query.lower()}%"
            cur = self._conn.execute(
                "SELECT key, tier, value, metadata, created "
                "FROM flatspace WHERE tier=? "
                "AND (lower(key) LIKE ? OR lower(value) LIKE ?) "
                "ORDER BY created DESC LIMIT ?",
                (tier, q, q, int(limit)),
            )
            results = []
            for key, t, v, meta, created in cur.fetchall():
                try:
                    val = json.loads(v)
                except Exception:
                    val = v
                results.append({
                    "key": key, "tier": t, "value": val,
                    "metadata": json.loads(meta) if meta else {},
                    "created": created, "local": True,
                })
            return results
        except Exception as exc:
            log.warning("LocalFlatSpaceStore search failed", query=query, error=str(exc))
            return []

    # ── Key listing (prefix scan, no embedding) ─────────────────────
    def list_keys(
        self, prefix: str, tier: str = "bitgarden", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List records whose key starts with `prefix` (exact prefix scan,
        no embedding / no substring value match). Used for history/replay
        without paying the Ollama embedding cost."""
        try:
            cur = self._conn.execute(
                "SELECT key, value, metadata, created FROM flatspace "
                "WHERE tier=? AND key LIKE ? ORDER BY created DESC LIMIT ?",
                (tier, prefix + "%", int(limit)),
            )
            out = []
            for key, v, meta, created in cur.fetchall():
                try:
                    val = json.loads(v)
                except Exception:
                    val = v
                out.append({
                    "key": key, "value": val,
                    "metadata": json.loads(meta) if meta else {},
                    "created": created, "local": True,
                })
            return out
        except Exception as exc:
            log.warning("LocalFlatSpaceStore list_keys failed", prefix=prefix, error=str(exc))
            return []
    def get_tier_stats(self) -> Dict[str, Any]:
        try:
            cur = self._conn.execute(
                "SELECT tier, COUNT(*) FROM flatspace GROUP BY tier"
            )
            by_tier = {t: c for t, c in cur.fetchall()}
            cur = self._conn.execute("SELECT COUNT(*) FROM flatspace")
            total = cur.fetchone()[0]
            return {
                "backend": "local_sqlite",
                "db": self._db,
                "total_records": total,
                "by_tier": by_tier,
                "status": "online",
            }
        except Exception as exc:
            return {"backend": "local_sqlite", "status": "error", "error": str(exc)}

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
