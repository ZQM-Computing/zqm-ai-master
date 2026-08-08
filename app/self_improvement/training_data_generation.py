"""Training data generation from feedback."""
from __future__ import annotations

import json
import os
from typing import Any


def generate_training_data_from_feedback(min_rating: int = 4, limit: int = 100) -> dict[str, Any]:
    path = os.path.join("data", "feedback.jsonl")
    if not os.path.exists(path):
        return {"count": 0, "path": path}
    records: list[dict[str, Any]] = []
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
    examples = []
    for rec in records:
        if rec.get("rating") is not None and rec["rating"] >= min_rating:
            examples.append({
                "prompt": rec.get("query", ""),
                "completion": rec.get("response", ""),
                "metadata": {"source": "feedback", "rating": rec["rating"], "user_id": rec.get("user_id", "anonymous")},
            })
    out_path = os.path.join("data", "generated_from_feedback.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(ex) + "\n" for ex in examples)
    return {"count": len(examples), "path": out_path}
