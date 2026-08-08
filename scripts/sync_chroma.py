"""
Sync Flatspace local SQLite records into Chroma 'flatspace' collection.

Reads all rows from app/flatspace_local.db and upserts into the v2 API
collection identified by a fixed UUID, using deterministic UUIDs derived
from each document's key.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
import uuid

# Ensure local package imports work when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

DB_PATH = "app/flatspace_local.db"
COLLECTION_ID = "477b326c-f754-454f-8842-dd4247a4630a"
COLLECTION_PATH = f"/api/v2/tenants/default_tenant/databases/default_database/collections/{COLLECTION_ID}"
BATCH = 20
MAX_RETRIES = 3
EMBED_MODEL = "bge-m3:latest"
EMBED_URL = "http://127.0.0.1:11434/api/embeddings"


def _chroma_base() -> str:
    base = (settings.chroma_url or "").rstrip("/")
    if not base:
        raise RuntimeError("CHROMA_URL is not configured")
    return base


def _chroma_url(path: str) -> str:
    return f"{_chroma_base()}{path}"


def _headers() -> dict:
    return {"Content-Type": "application/json"}


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = _chroma_url(path)
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


def ensure_collection() -> None:
    r = _request("GET", "/api/v2/tenants/default_tenant/databases/default_database/collections")
    if "_error" in r or "_http_status" in r:
        raise RuntimeError(f"Collection listing failed: {r}")
    names = [c.get("id") for c in r if isinstance(c, dict)]
    if COLLECTION_ID not in names:
        raise RuntimeError(
            f"Missing collection {COLLECTION_ID}; create it once with: "
            f"curl -s -X POST 'http://{_chroma_base('/')}/api/v2/collections' "
            f"-H 'Content-Type: application/json' -d '{{\"name\":\"flatspace\"}}'"
        )
    print("verified collection", COLLECTION_ID)


def _deterministic_uuid(raw_key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"flatspace://{raw_key}"))


def docs_from_db() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT `key`, `tier`, `value`, `metadata`, `created` FROM `flatspace`"
    ).fetchall()
    out: list[dict] = []
    for i, row in enumerate(rows):
        try:
            val = json.loads(row["value"])
        except Exception:
            val = {"text": row["value"]}
        raw_key = row["key"]
        doc = {
            "id": _deterministic_uuid(raw_key),
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


def _upsert_batch(docs: list[dict]) -> None:
    texts = []
    for doc in docs:
        texts.append(doc.get("text", "") or "")

    embeddings = []
    if texts:
        try:
            import urllib.request as _urllib_request
            for text in texts:
                payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
                req = _urllib_request.Request(
                    EMBED_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with _urllib_request.urlopen(req, timeout=120) as r:
                    emb_data = json.loads(r.read().decode())
                embeddings.append(emb_data.get("embedding", []))
        except Exception as exc:
            print("embed_failed", exc)
            embeddings = None
    if embeddings is None or len(embeddings) != len(docs):
        print("skip_batch embedding unavailable for this batch")
        return

    ids = []
    documents = []
    metadatas = []

    for idx, doc in enumerate(docs):
        ids.append(doc["id"])
        documents.append(doc.get("text", json.dumps(doc.get("value", "")) if isinstance(doc.get("value"), (dict, list)) else str(doc.get("value", ""))))
        meta = {
            "key": doc.get("key"),
            "tier": doc.get("tier"),
            "created": doc.get("created"),
        }
        raw_meta = doc.get("metadata")
        if isinstance(raw_meta, dict):
            for mkey, mval in raw_meta.items():
                if isinstance(mval, (str, int, float, bool)):
                    meta[str(mkey)] = mval
        metadatas.append(meta)

    payload = {
        "ids": ids,
        "embeddings": embeddings,
        "documents": documents,
        "metadatas": metadatas,
    }
    r = _request("POST", f"{COLLECTION_PATH}/upsert", payload)
    if "_error" in r or ("_http_status" in r and r["_http_status"] >= 400):
        raise RuntimeError(f"Chroma upsert failed: {r}")


def main() -> int:
    if not settings.chroma_url:
        print("CHROMA_URL missing; abort sync")
        return 1

    try:
        ensure_collection()
    except Exception as exc:
        print("ensure_collection_failed", exc)
        return 1

    docs = docs_from_db()
    print("docs_from_db", len(docs))
    t0 = time.time()
    failed = []
    for i in range(0, len(docs), BATCH):
        batch = docs[i:i + BATCH]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _upsert_batch(batch)
                break
            except Exception as exc:
                print(f"upsert_failed {i} attempt {attempt} {exc}")
                if attempt >= MAX_RETRIES:
                    failed.append(i)
                    break
                time.sleep(2**attempt)
        print("upserted", min(i + BATCH, len(docs)), "elapsed", round(time.time() - t0, 1))
    if failed:
        print("failed_batches", failed)
    print("DONE elapsed", round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
