"""A/B testing framework."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class ABTestResult:
    variant: str
    sample_count: int
    pass_count: int
    fail_count: int
    metric: float = 0.0


class ABTest:
    def __init__(self, name: str, variants: list[str], traffic_split: list[float] | None = None) -> None:
        self.name = name
        self.variants = variants
        self.traffic_split = traffic_split or [1.0 / len(variants)] * len(variants)
        self.results: dict[str, list[bool]] = {v: [] for v in variants}

    def assign(self) -> str:
        return random.choices(self.variants, weights=self.traffic_split, k=1)[0]

    def record(self, variant: str, passed: bool) -> None:
        if variant not in self.results:
            raise ValueError(f"Unknown variant: {variant}")
        self.results[variant].append(bool(passed))

    def summary(self) -> dict[str, Any]:
        summaries = {}
        for variant, outcomes in self.results.items():
            passed = sum(outcomes)
            failed = len(outcomes) - passed
            summaries[variant] = ABTestResult(
                variant=variant,
                sample_count=len(outcomes),
                pass_count=passed,
                fail_count=failed,
                metric=passed / max(len(outcomes), 1),
            )
        return {"name": self.name, "summaries": summaries}
