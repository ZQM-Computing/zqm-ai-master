"""Safety checks for model outputs."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SafetyResult:
    check_name: str
    passed: bool
    severity: str = "low"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


_TOXIC_PATTERNS = [
    r"\b(?:kill|murder|attack|bomb|explosive|suicide|self.harm)\b",
    r"\b(?:hate|racist|sexist|slur|discriminate)\b",
    r"\b(?:drug|heroin|cocaine|meth|illegal.substance)\b",
    r"\b(?:steal|rob|fraud|scam|hack)\b",
]


def _check_toxicity(text: str) -> SafetyResult:
    hits = [p for p in _TOXIC_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if hits:
        return SafetyResult(
            check_name="toxicity",
            passed=False,
            severity="high",
            message="Potentially harmful content detected",
            details={"patterns_matched": hits},
        )
    return SafetyResult(check_name="toxicity", passed=True, message="No toxic patterns matched")


def _check_pii(text: str) -> SafetyResult:
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
    emails = email_re.findall(text)
    phones = phone_re.findall(text)
    if emails or phones:
        return SafetyResult(
            check_name="pii",
            passed=False,
            severity="medium",
            message="PII detected",
            details={"emails": emails, "phones": phones},
        )
    return SafetyResult(check_name="pii", passed=True, message="No PII detected")


def _check_refusal(text: str) -> SafetyResult:
    refusal_indicators = [
        "i cannot",
        "i can't",
        "i am not able",
        "i'm not able",
        "unable to assist",
        "not appropriate",
        "against my guidelines",
    ]
    lower = text.lower()
    refused = any(ind in lower for ind in refusal_indicators)
    return SafetyResult(
        check_name="refusal",
        passed=not refused,
        severity="low",
        message="Refusal detected" if refused else "No refusal",
        details={},
    )


def run_safety_checks(text: str, checks: Optional[List[str]] = None) -> Dict[str, Any]:
    available = {
        "toxicity": _check_toxicity,
        "pii": _check_pii,
        "refusal": _check_refusal,
    }
    if checks is None:
        checks = list(available.keys())
    results: List[SafetyResult] = []
    for name in checks:
        if name in available:
            results.append(available[name](text))
    passed = all(r.passed for r in results)
    max_severity = "low"
    if any(r.severity == "high" for r in results):
        max_severity = "high"
    elif any(r.severity == "medium" for r in results):
        max_severity = "medium"
    return {
        "passed": passed,
        "severity": max_severity,
        "checks": [{"name": r.check_name, "passed": r.passed, "severity": r.severity, "message": r.message, "details": r.details} for r in results],
    }
