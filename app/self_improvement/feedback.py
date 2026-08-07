"""Feedback collection and summarization."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def _feedback_path() -> str:
    return os.path.join("data", "feedback.jsonl")


def collect_feedback(
    query: str,
    response: str,
    rating: Optional[int] = None,
    feedback_text: Optional[str] = None,
    user_id: str = "anonymous",
) -> Dict[str, Any]:
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "query": query,
        "response": response,
        "rating": rating,
        "feedback_text": feedback_text,
    }
    path = _feedback_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {"status": "recorded", "record": record}


def summarize_feedback(limit: int = 100) -> Dict[str, Any]:
    path = _feedback_path()
    if not os.path.exists(path):
        return {"count": 0, "average_rating": None}
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    ratings = [r["rating"] for r in records if r.get("rating") is not None]
    avg = sum(ratings) / len(ratings) if ratings else None
    return {"count": len(records), "average_rating": avg, "recent": records[-5:]}
