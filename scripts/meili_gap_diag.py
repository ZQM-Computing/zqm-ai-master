"""
Diagnose the Meilisearch vs local FLATSPACE indexing gap and print report.

- If MEILISEARCH_MASTER_KEY is set, query Meilisearch flatspace doc count.
- If local app/flatspace_local.db exists, print its row count by tier.
- Print the gap between Meilisearch docs and local records.
- If Chroma is referenced in config but not deployed, report that too.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "app" / "flatspace_local.db"
MEILI_BASE = os.getenv("MEILISEARCH_URL", "http://127.0.0.1:7701").rstrip("/")
MEILI_KEY = os.getenv("MEILISEARCH_MASTER_KEY", "")


def meili_get(path: str) -> dict:
    url = f"{MEILI_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if MEILI_KEY:
        headers["Authorization"] = f"Bearer {MEILI_KEY}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode() or "{}"
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        return {"_http_status": exc.code, "_http_reason": exc.reason}
    except Exception as exc:
        return {"_error": str(exc)}


def main() -> int:
    print("MEILI_BASE:", MEILI_BASE)
    print("MEILI_KEY:", "set" if MEILI_KEY else "missing")

    info = meili_get("/indexes/flatspace")
    if "_error" in info or "_http_status" in info:
        print("MEILI_STATUS: unreachable or unauthorized")
        meili_docs = None
    else:
        stats = meili_get("/indexes/flatspace/stats")
        if "_error" in stats or "_http_status" in stats:
            print("MEILI_STATUS: index missing or unauthorized")
            meili_docs = 0 if info.get("uid") else None
        else:
            meili_docs = stats.get("numberOfDocuments")
            print("MEILI_STATUS: ok")
            print("MEILI_INDEX_UID:", info.get("uid"))
            print("MEILI_DOCS:", meili_docs)

    print("LOCAL_DB_PATH:", DB_PATH)
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM flatspace").fetchone()[0]
        by_tier = conn.execute("SELECT tier, COUNT(*) FROM flatspace GROUP BY tier").fetchall()
        conn.close()
        print("LOCAL_DB_TOTAL:", total)
        print("LOCAL_DB_BY_TIER:", [dict(r) for r in by_tier])
    else:
        print("LOCAL_DB_TOTAL: missing")
        total = None

    if meili_docs is not None and total is not None:
        gap = int(total) - int(meili_docs or 0)
        print("GAP_local_minus_meili:", gap)
        if gap > 0:
            print("RECOMMENDATION: reindex into Meilisearch")
        else:
            print("RECOMMENDATION: Meilisearch is in sync or ahead")
    else:
        print("GAP_local_minus_meili: unknown")

    chroma_url = os.getenv("CHROMA_URL", "")
    chroma_coll = os.getenv("CHROMA_COLLECTION", "")
    chroma_enabled = os.getenv("CHROMA_ENABLED", "false").lower() == "true"
    print("CHROMA_URL:", chroma_url)
    print("CHROMA_COLLECTION:", chroma_coll)
    print("CHROMA_ENABLED:", chroma_enabled)
    if chroma_enabled or chroma_url:
        try:
            urllib.request.urlopen(chroma_url.rstrip("/"), timeout=5)
            print("CHROMA_STATUS: reachable")
        except Exception as exc:
            print("CHROMA_STATUS: unreachable:", exc)
    else:
        print("CHROMA_STATUS: not configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
