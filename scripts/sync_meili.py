"""
Sync Flatspace local SQLite records into Meilisearch 'flatspace' index.

Reads all rows from app/flatspace_local.db and upserts into Meilisearch.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

# Ensure local package imports work when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

DB_PATH = "app/flatspace_local.db"
INDEX = "flatspace"
BATCH = 100


_MEILI_ID_INVALID = re.compile(r'[^A-Za-z0-9_-]')


def _safe_meili_id(raw: str, fallback_index: int) -> str:
    candidate = _MEILI_ID_INVALID.sub('_', raw)
    candidate = re.sub(r'_+', '_', candidate).strip('_')
    if not candidate:
        candidate = f'doc_{fallback_index}'
    return candidate[:255]


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if settings.meilisearch_master_key:
        h["Authorization"] = f"Bearer {settings.meilisearch_master_key}"
    return h


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{(settings.meilisearch_url or '').rstrip('/')}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        return {"_http_status": exc.code, "_http_reason": exc.reason}
    except Exception as exc:
        return {"_error": str(exc)}


def ensure() -> None:
    r = _request("GET", f"/indexes/{INDEX}")
    if "_http_status" in r:
        _request("POST", "/indexes", {"uid": INDEX, "primaryKey": "key"})
        print("created index", INDEX)


def docs_from_db() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, tier, value, metadata, created FROM flatspace").fetchall()
    out = []
    for i, row in enumerate(rows):
        try:
            val = json.loads(row["value"])
        except Exception:
            val = {"text": row["value"]}
        raw_key = row["key"]
        doc = {
            "id": _safe_meili_id(raw_key, i),
            "key": raw_key,
            "tier": row["tier"],
            "value": val,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "created": row["created"],
        }
        if "text" not in val:
            if isinstance(val, dict):
                txt = " ".join(str(v) for v in val.values() if isinstance(v, str))
            else:
                txt = str(val)
            doc["text"] = txt
        out.append(doc)
    conn.close()
    return out


def main() -> int:
    if not settings.meilisearch_master_key:
        print("MEILISEARCH_MASTER_KEY missing; abort sync")
        return 1
    ensure()
    docs = docs_from_db()
    print("docs_from_db", len(docs))
    t0 = time.time()
    for i in range(0, len(docs), BATCH):
        batch = docs[i:i + BATCH]
        r = _request("POST", f"/indexes/{INDEX}/documents", batch)
        if "_error" in r or "_http_status" in r:
            print("upsert_failed", i, r)
            continue
        print("upserted", i + len(batch), "elapsed", round(time.time() - t0, 1))
    print("DONE elapsed", round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
