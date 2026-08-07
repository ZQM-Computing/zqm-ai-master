"""
Build a supervised fine-tuning dataset from Flatspace + optional web augmentation.

Outputs JSONL with fields:
  - prompt: input text
  - completion: target text
  - metadata: source info
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from typing import Any, Dict, List, Optional

# Ensure local package imports work when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


DB_PATH = "app/flatspace_local.db"
DEFAULT_OUTPUT = "data/training_data.jsonl"


def _chunks_from_flatspace(tier: str = "bitgarden", limit: int = 10000) -> List[Dict[str, Any]]:
    """Extract (prompt, completion) pairs from Flatspace local DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT key, tier, value, metadata, created FROM flatspace WHERE tier=? LIMIT ?",
        (tier, limit),
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            val = json.loads(row["value"]) if row["value"] else {}
        except Exception:
            val = {"text": row["value"] or ""}
        text = ""
        if isinstance(val, dict):
            text = (
                val.get("output")
                or val.get("input")
                or val.get("body")
                or val.get("text")
                or val.get("content")
                or ""
            )
            if not text:
                text = " ".join(str(v) for v in val.values() if isinstance(v, str))
        else:
            text = str(val)
        text = (text or "").strip()
        if not text:
            continue
        # Heuristic Q/A: use first sentence as prompt, rest as completion.
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        if len(sentences) >= 3:
            prompt = ". ".join(sentences[:2]) + "."
            completion = ". ".join(sentences[2:]) + "."
        else:
            prompt = sentences[0] if sentences else text[:80]
            completion = text[len(prompt):].strip()
        out.append(
            {
                "prompt": prompt,
                "completion": completion,
                "metadata": {
                    "source": "flatspace",
                    "key": row["key"],
                    "tier": row["tier"],
                    "created": row["created"],
                },
            }
        )
    return out


def _write_jsonl(records: List[Dict[str, Any]], path: str) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count


def build_dataset(output: str, tier: str, limit: int) -> int:
    print(f"Building dataset from Flatspace tier={tier} limit={limit}")
    records = _chunks_from_flatspace(tier=tier, limit=limit)
    if not records:
        print("No records found")
        return 0
    # Basic dedupe by prompt+completion
    seen = set()
    deduped = []
    for rec in records:
        key = (rec["prompt"], rec["completion"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    n = _write_jsonl(deduped, output)
    print(f"Wrote {n} examples to {output}")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Build training dataset from Flatspace")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--tier", default="bitgarden")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    return build_dataset(args.output, args.tier, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
