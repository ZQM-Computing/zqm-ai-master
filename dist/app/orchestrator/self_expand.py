"""
The Void AI Orchestration System — Self-Expansion Engine (P6)

Version: 2.1.0 | ZQM Computing LLC

Makes The Void SELF-EXPANDING: the self-improvement panel can now emit three
structured, parseable directives (not just vague prose):

    EXPAND_AGENT:            spawn a NEW agent into the live registry
    EXPAND_TOOL:             wire a NEW zqm-local-tools capability (mesh probe)
    PATCH:                   exact code edit (handled by self_apply, reused here)

Each expansion is:
  * VALIDATED  — agent type / capability must be whitelisted; tool name must
                 match ^[a-z_]+$; PATCH must be unique-match + compile-clean.
  * GATED      — behind ZQM_SELF_APPLY (default OFF). When off, every proposal
                 is recorded (audited) but NOT applied (propose-only).
  * AUDITED    — every proposal + outcome is written immutably to FLATSPACE
                 (waxcell tier) and to the local expansion ledger JSONL.
  * REVERSIBLE — agents are runtime-only (reset on restart from DEFAULT_AGENTS);
                 tools are staged with a .bak; patches carry a .bak.

This turns the dormant self-improvement loop into a real, safe growth mechanism.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.logger import get_logger

log = get_logger("self-expand")

SELF_APPLY_ON = os.getenv("ZQM_SELF_APPLY", "false").lower() in ("1", "true", "yes")

# ── Whitelists (defense-in-depth) ─────────────────────────────────────────────
# Capabilities are validated against the ACTUAL AgentCapability enum (source of
# truth) so only genuinely-valid caps pass AgentCreate. Agent types are
# restricted to a safe subset the registry knows how to route.
ALLOWED_AGENT_TYPES = {
    "nlp", "reasoning", "synthesis", "memory", "learning",
    "gis", "hydrology", "observability", "api", "data", "data_analysis",
    "code", "security", "infrastructure", "garden",
}
try:
    from app.models.agent import AgentCapability
    ALLOWED_CAPABILITIES = {c.value for c in AgentCapability}
except Exception:
    ALLOWED_CAPABILITIES = {"text_generation", "summarization", "question_answering",
                            "sentiment_analysis", "data_analysis", "code_review",
                            "code_generation", "spatial_analysis", "web_search",
                            "monitoring", "api_call", "database_query"}
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


# Placeholder / template guard (P9)
# The self-critique LLM sometimes echoes the *prompt template* itself as a
# "finding" (literal text such as "<rel path under app/>" or "<exact old text>").
# Reject any directive that still contains template placeholders / angle
# brackets so it never reaches the ledger as a bogus entry.
_PLACEHOLDER_RE = re.compile(r"<[^>]+>|rel path under app|exact old text|exact new text", re.I)
def _is_placeholder(text):
    return bool(_PLACEHOLDER_RE.search(text or ""))

_EXPAND_AGENT_RE = re.compile(
    r"EXPAND_AGENT:\s*\n(.*?)(?=\n(?:EXPAND_TOOL:|PATCH:)|\Z)",
    re.DOTALL,
)
_EXPAND_TOOL_RE = re.compile(
    r"EXPAND_TOOL:\s*\n(.*?)(?=\n(?:EXPAND_AGENT:|PATCH:)|\Z)",
    re.DOTALL,
)
_PATCH_RE = re.compile(
    r"PATCH:\s*\nfile:\s*([^\n]+)\n"
    r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE",
    re.DOTALL,
)

# Local ledger (survives a down FLATSPACE, like self_improvement_log.jsonl).
_LEDGER_PATH = Path(__file__).resolve().parent.parent / "self_expand_ledger.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(orchestrator: Any, kind: str, record: Dict[str, Any]) -> None:
    """Write an expansion event immutably to FLATSPACE (waxcell) + local ledger."""
    record = {**record, "kind": kind, "ts": _now(), "self_apply": SELF_APPLY_ON}
    # Local ledger (always, best-effort).
    try:
        with _LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        log.warning("Expansion ledger write failed", error=str(exc))
    # FLATSPACE (best-effort; never fail the proposal on this).
    try:
        fs = getattr(orchestrator, "flatspace", None)
        if fs is not None:
            import asyncio
            asyncio.get_event_loop().create_task(
                fs.store(key=f"self_expand:{_now()}", value=record, tier="waxcell")
            )
    except Exception:
        pass


# ── Agent expansion ───────────────────────────────────────────────────────────

def _parse_kv(block: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in block.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


async def expand_agent(orchestrator: Any, block: str) -> Dict[str, Any]:
    """Validate + (if gated on) register a new agent from an EXPAND_AGENT block."""
    kv = _parse_kv(block)
    name = kv.get("name", "").strip()
    atype = (kv.get("agent_type") or kv.get("type") or "").strip().lower()
    caps_raw = kv.get("capabilities", "")
    prompt = kv.get("system_prompt") or kv.get("prompt") or ""

    # Validate.
    if not name:
        return {"applied": False, "reason": "missing name"}
    if _is_placeholder(name) or _is_placeholder(prompt):
        return {"applied": False, "reason": "placeholder/template rejected"}
    if atype not in ALLOWED_AGENT_TYPES:
        return {"applied": False, "reason": f"agent_type not allowed: {atype!r}"}
    caps = [c.strip().lower() for c in caps_raw.replace(";", ",").split(",") if c.strip()]
    bad = [c for c in caps if c not in ALLOWED_CAPABILITIES]
    if bad:
        return {"applied": False, "reason": f"capabilities not allowed: {bad}"}
    if not prompt:
        return {"applied": False, "reason": "missing system_prompt"}

    proposal = {
        "name": name, "agent_type": atype, "capabilities": caps,
        "system_prompt": prompt[:2000],
    }
    _audit(orchestrator, "agent", {**proposal, "applied": False, "phase": "proposed"})

    if not SELF_APPLY_ON:
        return {"applied": False, "reason": "propose-only (ZQM_SELF_APPLY off)", **proposal}

    # Apply: register into the live registry (runtime-only; resets on restart).
    try:
        from app.models.agent import AgentCreate, AgentType as AT
        from app.core.config import settings as _settings
        reg = getattr(orchestrator, "registry", None)
        if reg is None:
            return {"applied": False, "reason": "no registry"}
        create = AgentCreate(
            name=name, agent_type=AT(atype), capabilities=caps,
            system_prompt=prompt[:2000],
            provider="ollama",
            model=getattr(_settings, "ollama_default_model", "qwen2.5:3b"),
        )
        agent = await reg.register(create)
        _audit(orchestrator, "agent", {**proposal, "applied": True, "agent_id": agent.agent_id})
        log.info("Self-expanded agent pool", agent=name, agent_id=agent.agent_id)
        return {"applied": True, "agent_id": agent.agent_id, **proposal}
    except Exception as exc:
        return {"applied": False, "reason": f"register failed: {exc}", **proposal}


# ── Tool expansion ─────────────────────────────────────────────────────────────

# The zqm-local-tools CLI this host actually runs (C:\Users\zqmco\zqm-mcp\server.py
# is served via zqm_tools_cli.py). New tools are appended to the CLI as @tool funcs.
_TOOLS_CLI = Path(r"C:\Users\zqmco\zqm-mcp\zqm_tools_cli.py")


async def expand_tool(orchestrator: Any, block: str) -> Dict[str, Any]:
    """Validate + (if gated on) append a new mesh-probe tool to the zqm-tools CLI."""
    kv = _parse_kv(block)
    tname = (kv.get("name") or "").strip().lower()
    probe = kv.get("probe") or kv.get("target") or ""
    desc = kv.get("description") or kv.get("desc") or ""

    if not TOOL_NAME_RE.match(tname):
        return {"applied": False, "reason": f"tool name invalid: {tname!r}"}
    if not probe:
        return {"applied": False, "reason": "missing probe/target"}
    # Safety: a tool probe must be a known mesh node token or a whitelisted pattern.
    if not re.search(r"\b(N1|N2|N3|N4|node|mesh)\b", probe, re.I) and "MESH_PORTS" not in probe:
        return {"applied": False, "reason": "probe must reference a mesh node/port (safety)"}

    proposal = {"tool": tname, "probe": probe[:200], "description": desc[:200]}
    _audit(orchestrator, "tool", {**proposal, "applied": False, "phase": "proposed"})

    if not SELF_APPLY_ON:
        return {"applied": False, "reason": "propose-only (ZQM_SELF_APPLY off)", **proposal}

    try:
        if not _TOOLS_CLI.exists():
            return {"applied": False, "reason": f"CLI not found: {_TOOLS_CLI}"}
        src = _TOOLS_CLI.read_text(encoding="utf-8")
        if f"def {tname}(" in src:
            return {"applied": False, "reason": f"tool already exists: {tname}"}
        # Stage with backup, append a new @mcp.tool() function.
        backup = _TOOLS_CLI.with_suffix(_TOOLS_CLI.suffix + ".bak")
        shutil.copy2(_TOOLS_CLI, backup)
        new_fn = (
            f"\n\n@mcp.tool()\n"
            f"def {tname}(node: str = \"N4\") -> str:\n"
            f"    \"\"\"Auto-expanded tool: {desc[:120]}. Probes {probe[:80]}.\"\"\"\n"
            f"    out, err = _ssh(node, \"{probe.replace(chr(34), '')}\", timeout=30)\n"
            f"    if err and not out:\n"
            f"        return f\"[{node}] {tname} failed: {err}\"\n"
            f"    return f\"===== {tname}: {{node}} =====\\n{{out}}\"\n"
        )
        _TOOLS_CLI.write_text(src + new_fn, encoding="utf-8")
        _audit(orchestrator, "tool", {**proposal, "applied": True, "cli": str(_TOOLS_CLI)})
        log.info("Self-expanded tool set", tool=tname)
        # The bridge must reload to pick up the new tool (handled by the CLI caller).
        return {"applied": True, "tool": tname, "note": "CLI updated; bridge reload required", **proposal}
    except Exception as exc:
        return {"applied": False, "reason": f"tool write failed: {exc}", **proposal}


# ── PATCH expansion (reuses self_apply) ────────────────────────────────────────

async def expand_patch(orchestrator: Any, patch: Dict[str, str]) -> Dict[str, Any]:
    """Route a structured PATCH to the existing safe self-apply pipeline."""
    from app.orchestrator.self_apply import self_apply
    _audit(orchestrator, "patch", {**patch, "applied": False, "phase": "proposed"})
    if not SELF_APPLY_ON:
        return {"applied": False, "reason": "propose-only (ZQM_SELF_APPLY off)", **patch}
    res = await self_apply(orchestrator, patch)
    _audit(orchestrator, "patch", {**patch, **res})
    return res


# ── Orchestration: scan findings for all three directive types ────────────────

async def process_findings(orchestrator: Any, findings_text: str) -> Dict[str, Any]:
    """Parse a self-improvement findings blob and apply/expand every directive.

    Returns a summary of proposals + applied actions. Safe by default:
    with ZQM_SELF_APPLY off, nothing is mutated — only proposed + audited.
    """
    applied: List[Dict[str, Any]] = []
    proposed: List[Dict[str, Any]] = []

    # EXPAND_AGENT
    for m in _EXPAND_AGENT_RE.finditer(findings_text):
        res = await expand_agent(orchestrator, m.group(1))
        (applied if res.get("applied") else proposed).append(res)
    # EXPAND_TOOL
    for m in _EXPAND_TOOL_RE.finditer(findings_text):
        res = await expand_tool(orchestrator, m.group(1))
        (applied if res.get("applied") else proposed).append(res)
    # PATCH
    for m in _PATCH_RE.finditer(findings_text):
        res = await expand_patch(orchestrator, {
            "file": m.group(1).strip(), "old": m.group(2), "new": m.group(3),
        })
        (applied if res.get("applied") else proposed).append(res)

    return {
        "self_apply": SELF_APPLY_ON,
        "proposed": len(proposed),
        "applied": len(applied),
        "proposals": proposed,
        "actions": applied,
    }


def review_ledger(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the local expansion ledger for human review (the approval queue)."""
    if not _LEDGER_PATH.exists():
        return []
    rows = [json.loads(l) for l in _LEDGER_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-limit:]
