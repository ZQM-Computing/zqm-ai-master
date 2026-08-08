"""Performance regression detection."""
from __future__ import annotations

import json
import os
from typing import Any


class PerformanceRegressionDetector:
    def __init__(self, history_path: str = "data/performance_history.jsonl", window: int = 20) -> None:
        self.history_path = history_path
        self.window = window

    def record(self, metric_name: str, value: float, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        record = {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "metric": metric_name,
            "value": value,
            "metadata": metadata or {},
        }
        os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return {"status": "recorded", "metric": metric_name, "value": value}

    def detect(self, metric_name: str, tolerance: float = 0.05) -> dict[str, Any]:
        if not os.path.exists(self.history_path):
            return {"regression": False, "reason": "no_history"}
        values: list[float] = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("metric") == metric_name:
                    values.append(float(rec["value"]))
        if len(values) < 2:
            return {"regression": False, "reason": "insufficient_data", "count": len(values)}
        if len(values) <= self.window:
            split = len(values) // 2
            baseline = values[:split] if split > 0 else values[:1]
            recent = values[split:]
        else:
            baseline = values[:-self.window]
            recent = values[-self.window:]
        baseline_avg = sum(baseline) / len(baseline)
        recent_avg = sum(recent) / len(recent)
        regression = abs(recent_avg - baseline_avg) > tolerance
        return {
            "regression": regression,
            "metric": metric_name,
            "baseline_avg": baseline_avg,
            "recent_avg": recent_avg,
            "delta": baseline_avg - recent_avg,
            "tolerance": tolerance,
            "count": len(values),
        }
