"""Automatic fine-tuning triggers."""
from __future__ import annotations

import os
from typing import Any


class AutomaticFineTuningTrigger:
    def __init__(
        self,
        feedback_path: str = "data/feedback.jsonl",
        threshold: int = 50,
        min_avg_rating: float = 3.0,
    ) -> None:
        self.feedback_path = feedback_path
        self.threshold = threshold
        self.min_avg_rating = min_avg_rating

    def should_trigger(self) -> dict[str, Any]:
        if not os.path.exists(self.feedback_path):
            return {"trigger": False, "reason": "no_feedback_file"}
        ratings = []
        with open(self.feedback_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("rating") is not None:
                    ratings.append(rec["rating"])
        count = len(ratings)
        avg = sum(ratings) / count if count else None
        trigger = False
        reason = "no_ratings"
        if count >= self.threshold and avg is not None and avg < self.min_avg_rating:
            trigger = True
            reason = "rating_threshold_breach"
        return {
            "trigger": trigger,
            "reason": reason,
            "count": count,
            "average_rating": avg,
            "threshold": self.threshold,
            "min_avg_rating": self.min_avg_rating,
        }
