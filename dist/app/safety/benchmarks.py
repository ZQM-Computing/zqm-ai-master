"""Safety benchmark datasets and evaluation."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def load_toxicity_dataset(path: Optional[str] = None) -> Dict[str, Any]:
    if path is None:
        path = os.path.join("data", "safety_toxicity.jsonl")
    if not os.path.exists(path):
        return {"count": 0, "samples": []}
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"count": len(samples), "samples": samples}


def evaluate_on_dataset(samples: List[Dict[str, Any]], text_key: str = "text") -> Dict[str, Any]:
    from app.safety.checks import run_safety_checks

    results = []
    passed = 0
    failed = 0
    for sample in samples:
        text = sample.get(text_key, "")
        check = run_safety_checks(text)
        if check["passed"]:
            passed += 1
        else:
            failed += 1
        results.append({"text": text[:80], "passed": check["passed"], "severity": check["severity"]})
    return {
        "total": len(samples),
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / max(len(samples), 1),
        "details": results,
    }
