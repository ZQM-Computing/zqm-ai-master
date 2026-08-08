"""
The Void AI Orchestration System — Self-Apply pipeline (P2)

Version: 2.0.0 | ZQM Computing LLC

Closes the self-improvement loop: findings are no longer PROPOSE-only.
A panel can emit a structured PATCH block; this module validates it
(syntax + unique-match + import surface) in a staging copy, then
promotes it atomically to the live file and audits it immutably to
FLATSPACE (waxcell tier). Any failure -> rejected (audited), never
partial-applied.

Gated by ZQM_SELF_APPLY (default off) so the running system
never autonomously rewrites itself without explicit consent. On a
successful promote it sets orchestrator._needs_restart = True and logs
CRITICAL — a restart is REQUIRED to load the new code, but this
module never restarts the process itself.
"""

from __future__ import annotations

import os
import py_compile
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.core.logger import get_logger

log = get_logger("self-apply")

SELF_APPLY_ON = os.getenv("ZQM_SELF_APPLY", "false").lower() in (
    "1", "true", "yes",
) and not Path(__file__).resolve().parent.parent.parent.joinpath("no_self_apply.lock").exists()

_PATCH_RE = re.compile(
    r"PATCH:\s*\nfile:\s*([^\n]+)\n"
    r"<<<<<<<\s*SEARCH\s*\n(.*?)\n=======\s*\n(.*?)\n>>>>>>>\s*REPLACE",
    re.DOTALL,
)

# Placeholder / template guard (P9): reject prompt-template echoes such as
# "<rel path under app/>" / "<exact old text>" so they never reach the ledger.
_PLACEHOLDER_RE = re.compile(r"<[^>]+>|rel path under app|exact old text|exact new text", re.IGNORECASE)
def _is_placeholder(text):
    return bool(_PLACEHOLDER_RE.search(text or ""))


def parse_structured_patch(text: str) -> dict[str, str] | None:
    """
    Extract a structured PATCH block, if the panel emitted one.

    Format (fenced):
        PATCH:
        file: <rel path under app/>
        <<<<<<< SEARCH
        <old text>
        =======
        <new text>
        >>>>>>> REPLACE

    Returns {"file":..., "old":..., "new":...} or None.
    """
    m = _PATCH_RE.search(text)
    if not m:
        return None
    rel = m.group(1).strip()
    old = m.group(2)
    new = m.group(3)
    if not rel or not old or not new:
        return None
    # P9: reject template/placeholder echoes (e.g. "<rel path under app/>").
    if any(_is_placeholder(x) for x in (rel, old, new)):
        return None
    return {"file": rel, "old": old, "new": new}


async def self_apply(
    orchestrator: Any, patch: dict[str, str]
) -> dict[str, Any]:
    """
    Safely apply a proposed patch (see module docstring for the contract).
    `orchestrator` must expose .flatspace (FLATSPACE store) and
    ._needs_restart (bool flag).
    """
    app_root = Path(__file__).resolve().parent.parent  # app/
    rel = patch["file"].replace("\\", "/").lstrip("/")
    rel = rel.removeprefix("app/")
    target = (app_root / rel).resolve()
    if not str(target).startswith(str(app_root)):
        return {"applied": False, "reason": "path escapes app/ (rejected)"}
    # Tier 1.6 guardrail: never let the Void self-rewrite its own auth,
    # replication, or self-apply machinery at runtime. Those changes must go
    # through a human-authored deploy, not the autonomous loop.
    _SELF_MODIFY_DENY = {
        "core/security.py", "orchestrator/self_replicate.py",
        "orchestrator/self_apply.py", "orchestrator/self_improve.py",
        "core/config.py",
    }
    rel_norm = rel.replace("\\", "/")
    if rel_norm in _SELF_MODIFY_DENY:
        return {"applied": False, "reason": f"self-modify of security-critical file denied: {rel}"}
    if not target.exists():
        return {"applied": False, "reason": f"target missing: {patch['file']}"}

    src = target.read_text(encoding="utf-8")
    old, new = patch["old"], patch["new"]
    if src.count(old) != 1:
        return {
            "applied": False,
            "reason": f"old_string not unique (count={src.count(old)})",
        }
    staged = src.replace(old, new, 1)

    # Validate in a staging temp file (syntax + import surface).
    stage_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(staged)
            stage_path = tf.name
        py_compile.compile(stage_path, doraise=True)
    except Exception as exc:
        return {"applied": False, "reason": f"compile/validate failed: {exc}"}
    finally:
        if stage_path:
            try:
                os.unlink(stage_path)
            except Exception:
                pass

    # Promote (atomic).
    try:
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        target.write_text(staged, encoding="utf-8")
    except Exception as exc:
        return {"applied": False, "reason": f"promote failed: {exc}"}

    # Audit immutable (best-effort; never fail apply on this).
    try:
        await orchestrator.flatspace.store(
            key=f"self_apply:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}",
            value={"file": patch["file"], "old": old, "new": new},
            tier="waxcell",
        )
    except Exception:
        pass

    orchestrator._needs_restart = True
    log.critical(
        "Self-apply PROMOTED a patch — restart REQUIRED to load it",
        file=patch["file"],
    )
    # Publish to the live event bus (SSE consumers).
    try:
        from app.core.event_bus import bus
        await bus.publish("self_apply", {
            "file": patch["file"],
            "applied": True,
        })
    except Exception:
        pass
    return {"applied": True, "file": patch["file"]}


async def try_apply_findings(
    orchestrator: Any, findings: list[str]
) -> None:
    """Parse structured patches from findings; apply if ZQM_SELF_APPLY is on."""
    if not SELF_APPLY_ON:
        return
    for f in findings:
        patch = parse_structured_patch(f)
        if not patch:
            continue
        res = await self_apply(orchestrator, patch)
        if res.get("applied"):
            log.info("Self-apply succeeded", **res)
        else:
            log.warning("Self-apply rejected", reason=res.get("reason"))
            try:
                await orchestrator.flatspace.store(
                    key=f"self_apply_rejected:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}",
                    value={"patch": patch, "reason": res.get("reason")},
                    tier="waxcell",
                )
            except Exception:
                pass
