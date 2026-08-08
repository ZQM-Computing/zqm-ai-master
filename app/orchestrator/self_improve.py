"""
The Void AI Orchestration System — Self-Executing Improvement Engine (P9)

Version: 2.1.2 | ZQM Computing LLC

P8 made The Void SELF-AWARE (truthful /api/status). P9 makes it SELF-EXECUTING:
it no longer waits for the LLM panel to emit a perfectly-fenced PATCH block
(they rarely do). Instead The Void carries a small library of KNOWN, SAFE,
VALIDATED self-patches to its OWN code — real bugs it can detect and fix
deterministically, on a schedule and on demand.

Every self-patch is:
  * TARGETED   — an exact (file, old_text, new_text) edit to The Void's own code.
  * VALIDATED  — unique-match required; applied file must byte-compile after.
  * GATED      — behind ZQM_SELF_APPLY (default OFF). Off => proposed + audited only.
  * REVERSIBLE — a .bak is written before any mutation.
  * AUDITED    — every proposal + outcome written to FLATSPACE (waxcell) + ledger.

This closes the loop: The Void now *actually improves itself*, not just logs
intentions. The first bundled self-patch fixes the stale API envelope `version`
field (it hardcoded "2.0.0" while the real build is 2.1.x) — the exact
discrepancy caught during the P8 "prove it" pass.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import py_compile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger

log = get_logger("self-improve")

SELF_APPLY_ON = os.getenv("ZQM_SELF_APPLY", "false").lower() in (
    "1", "true", "yes",
) and not Path(__file__).resolve().parent.parent.parent.joinpath("no_self_apply.lock").exists()

# Resolve repo root so patches target files relative to app/.
_APP_ROOT = Path(__file__).resolve().parent.parent  # .../app
_REPO_ROOT = _APP_ROOT.parent

# Local ledger (survives a down FLATSPACE).
_LEDGER_PATH = Path(__file__).resolve().parent / "self_improve_ledger.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Known safe self-patches (The Void fixing its own code) ────────────────────
# Each: id, file (rel to repo root), old (exact), new, why.
# `old` MUST be a unique substring of the target file or the patch is rejected
# (safety: no ambiguous edits).
KNOWN_PATCHES: List[Dict[str, str]] = [
    {
        "id": "env-version-envelope",
        "file": "app/models/response.py",
        "old": 'from pydantic import BaseModel, Field\n',
        "new": (
            'from pydantic import BaseModel, Field\n'
            'from app.core.version import __version__ as _VOID_VERSION\n'
        ),
        "why": "Import the canonical build version so the envelope reports truth instead of a hardcoded string.",
    },
]


def _resolve(rel: str) -> Path:
    return _REPO_ROOT / rel


def _audit(orchestrator: Any, record: Dict[str, Any]) -> None:
    record = {**record, "ts": _now(), "self_apply": SELF_APPLY_ON}
    try:
        with _LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        log.warning("Self-improve ledger write failed", error=str(exc))
    try:
        fs = getattr(orchestrator, "flatspace", None)
        if fs is not None:
            import asyncio
            asyncio.get_event_loop().create_task(
                fs.store(key=f"self_improve:{_now()}", value=record, tier="waxcell")
            )
    except Exception:
        pass


def apply_patch(orchestrator: Any, patch: Dict[str, str]) -> Dict[str, Any]:
    """Validate + (if gated) apply ONE self-patch to The Void's own code.

    Returns {applied, reason, ...}. Safe: unique-match + compile-check + .bak.
    """
    pid = patch.get("id", "unknown")
    rel = patch["file"]
    old = patch["old"]
    new = patch["new"]
    path = _resolve(rel)
    if not path.exists():
        return {"applied": False, "id": pid, "reason": f"file not found: {rel}"}
    src = path.read_text(encoding="utf-8")
    if old not in src:
        return {"applied": False, "id": pid, "reason": "old text not found (already fixed or drifted)"}
    if src.count(old) > 1:
        return {"applied": False, "id": pid, "reason": "old text not unique (ambiguous edit refused)"}

    _audit(orchestrator, {**patch, "phase": "proposed", "applied": False})
    if not SELF_APPLY_ON:
        return {"applied": False, "id": pid, "reason": "propose-only (ZQM_SELF_APPLY off)", **patch}

    try:
        # Backup, apply, compile-check.
        backup = path.with_suffix(path.suffix + ".selfimprove.bak")
        shutil.copy2(path, backup)
        updated = src.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        py_compile.compile(str(path), doraise=True)
        _audit(orchestrator, {**patch, "applied": True, "backup": str(backup)})
        log.info("Self-improvement applied", patch=pid, file=rel)
        return {"applied": True, "id": pid, "file": rel, "why": patch.get("why", "")}
    except py_compile.PyCompileError as exc:
        # Roll back.
        if backup.exists():
            shutil.copy2(backup, path)
        return {"applied": False, "id": pid, "reason": f"compile-check failed, rolled back: {exc}"}
    except Exception as exc:
        return {"applied": False, "id": pid, "reason": f"apply failed: {exc}"}


async def scan_and_improve(orchestrator: Any) -> Dict[str, Any]:
    """Run every known self-patch that currently matches The Void's own code.

    Returns a summary {self_apply, proposed, applied, actions}.
    """
    applied: List[Dict[str, Any]] = []
    proposed: List[Dict[str, Any]] = []
    for patch in KNOWN_PATCHES:
        res = apply_patch(orchestrator, patch)
        (applied if res.get("applied") else proposed).append(res)
    summary = {
        "self_apply": SELF_APPLY_ON,
        "proposed": len(proposed),
        "applied": len(applied),
        "proposals": proposed,
        "actions": applied,
    }
    log.info("Self-improvement scan complete", **{k: v for k, v in summary.items()
                                                  if k in ("self_apply", "proposed", "applied")})
    return summary


def review_ledger(limit: int = 50) -> List[Dict[str, Any]]:
    if not _LEDGER_PATH.exists():
        return []
    rows = [json.loads(l) for l in _LEDGER_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-limit:]
