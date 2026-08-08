"""
The Void AI Orchestration System — Autonomous Self Systems Integration (P4)

Version: 2.0.0 | ZQM Computing LLC

Connects the self-improvement loop + agent pool to the wider ZQM system:

  • run_roundtable(topic, panel, rounds) — convene a multi-agent
    dialogue IN-VOID (same Ollama backend + agent defs the Void uses),
    returning the full transcript. Exposed via /api/roundtable.

  • integrate_findings(orchestrator) — read self-improvement findings
    from FLATSPACE, extract lightweight TUNE: directives, and apply them
    to the LIVE agent-registry load weights (ATRM). Runtime, reversible,
    audited to FLATSPACE waxcell. Gated by ZQM_SELF_APPLY (propose-only
    log if off; live re-weight if on). This closes the loop: the Void's
    own critique now tunes its own routing — no file patching required.

Directive format (emitted optionally by the self-improve Synthesis agent):
    TUNE: <agent_name> weight <+N|-N>
e.g.  TUNE: API-Conductor weight +2
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.orchestrator.agent_registry import DEFAULT_AGENTS

log = get_logger("system-integration")

SELF_APPLY_ON = os.getenv("ZQM_SELF_APPLY", "false").lower() in (
    "1", "true", "yes",
) and not Path(__file__).resolve().parent.parent.parent.joinpath("no_self_apply.lock").exists()

_TUNE_RE = re.compile(
    r"TUNE:\s*([A-Za-z0-9\-_ ]+?)\s+weight\s*([+-]?\d+)", re.IGNORECASE
)

DEFAULT_PANEL = [
    "ZQM-Reasoning-001", "ZQM-Code-Gen", "ZQM-Infra-Monitor",
    "ZQM-Network-Ops", "ZQM-Data-Forge", "ZQM-Synthesis-Core",
]

# Topic-aware specialist injection: if the topic concerns geography, water,
# or spatial systems, the geo/hydro domain specialists join the table so the
# panel can still give expert answers there — without skewing GENERAL topics
# toward a water-resources framing (the previous hardcoded panel bug).
_GEO_KEYWORDS = [
    "gis", "geograph", "map", "spatial", "hydro", "water", "river", "flood",
    "watershed", "hydrolog", "terrain", "elevation", "satellite imagery",
    "land use", "drainage", "sea level", "basin",
]


def _panel_for_topic(topic: str | None) -> list[str] | None:
    if not topic:
        return None
    t = topic.lower()
    if any(kw in t for kw in _GEO_KEYWORDS):
        # Geo/hydro topic: generalists + the two domain specialists.
        return DEFAULT_PANEL + ["ZQM-GIS-Analyst", "ZQM-Hydro-Expert"]
    return None  # general topic -> default generalist panel


def _panel_defs(panel: list[str] | None) -> list[dict[str, Any]]:
    names = panel or DEFAULT_PANEL
    by_name = {a["name"]: a for a in DEFAULT_AGENTS}
    chosen = [by_name[n] for n in names if n in by_name]
    # Always ensure a synthesis agent closes the table if available.
    if not any(a.get("agent_type") == "synthesis" for a in chosen):
        synth = next((a for a in DEFAULT_AGENTS
                      if a.get("agent_type") == "synthesis"), None)
        if synth:
            chosen.append(synth)
    return chosen


async def run_roundtable(
    topic: str,
    panel: list[str] | None = None,
    rounds: int = 2,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Run a multi-agent roundtable IN-VOID. Each agent hears the prior
    transcript (real multi-agent dialogue). Returns
    {topic, rounds, agents, transcript}.
    """
    agents = _panel_defs(panel or _panel_for_topic(topic))
    if not agents:
        return {"error": "no valid agents in panel"}
    model = model or settings.ollama_default_model
    transcript_lines: list[str] = [f"TOPIC: {topic}"]

    # Panelists route through the mesh Ollama router (failover + degraded
    # substitution), not the bare localhost base_url — so a crashed Ollama
    # degrades gracefully instead of 500'ing the roundtable.
    for rnd in range(1, max(1, rounds) + 1):
        for ag in agents:
            # Synthesizer speaks last each round (except it summaries at end).
            if ag.get("agent_type") == "synthesis" and rnd < max(1, rounds):
                continue
            instr = (
                "Give your opening position."
                if rnd == 1
                else "React to the others' points — build on agreements, "
                     "resolve conflicts, add your specialist view."
            )
            # Tier 1.5: each panelist speaks with its OWN model (diverse
            # ensemble) instead of the shared default — once agents are
            # repointed to fit-for-purpose mesh models, the roundtable
            # becomes a genuine multi-model consensus, not 3B×N.
            utt = await _agent_speak(ag.get("model") or model, ag, transcript_lines, instr)
            transcript_lines.append(f"\n[{ag['name']}]\n{utt}\n")

    # Final synthesis
    synth = next((a for a in agents if a.get("agent_type") == "synthesis"), None)
    if synth:
        utt = await _agent_speak(
            synth.get("model") or model, synth, transcript_lines,
            "Synthesize the panel's discussion into a unified, prioritized "
            "action plan.",
        )
        transcript_lines.append(f"\n[{synth['name']} — SYNTHESIS]\n{utt}\n")

    return {
        "topic": topic,
        "rounds": rounds,
        "agents": [a["name"] for a in agents],
        "transcript": "\n".join(transcript_lines),
    }


async def _agent_speak(model, agent, transcript_lines, instr) -> str:
    user_msg = (
        f"TOPIC: {transcript_lines[0].replace('TOPIC: ', '')}\n\n"
        f"CONVERSATION SO FAR:\n{chr(10).join(transcript_lines[1:])}\n\n"
        f"You are {agent['name']} ({agent['agent_type']}). {instr}"
    )
    try:
        # Mesh router: failover, localhost escape hatch, degraded substitution.
        from app.services.mesh_ollama import router as mesh_ollama
        data = await mesh_ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": agent.get("system_prompt", "")},
                {"role": "user", "content": user_msg},
            ],
            timeout=90.0,
            options={"temperature": 0.7},
        )
        content = data.get("message", {}).get("content", "")
        return content.strip() or "[EMPTY]"
    except Exception as exc:
        return f"[ERR {exc}]"


async def integrate_findings(orchestrator: Any) -> dict[str, Any]:
    """
    Read self-improvement findings from FLATSPACE, extract TUNE: directives,
    and apply them to the LIVE agent-registry load weights. Runtime + reversible
    (weights reset on restart from DEFAULT_AGENTS). Audited to waxcell.
    Gated by ZQM_SELF_APPLY: if off, only logs (propose-only).
    """
    try:
        findings = await orchestrator.flatspace.search(
            "self_improvement", tier="bitgarden", limit=50
        )
    except Exception as exc:
        return {"applied": False, "reason": f"flatspace search failed: {exc}"}

    applied: list[dict[str, Any]] = []
    for rec in findings:
        text = str(rec.get("value", ""))
        if isinstance(rec.get("value"), dict):
            text = " ".join(str(v) for v in rec["value"].values())
        for m in _TUNE_RE.finditer(text):
            name = m.group(1).strip()
            delta = int(m.group(2))
            res = _apply_weight(orchestrator, name, delta)
            applied.append({"agent": name, "delta": delta, **res})

    if not applied:
        return {"applied": 0, "note": "no TUNE directives found in recent findings"}

    # Audit
    try:
        await orchestrator.flatspace.store(
            key=f"integration:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}",
            value={"applied": applied, "live": SELF_APPLY_ON},
            tier="waxcell",
        )
    except Exception:
        pass
    return {"applied": len(applied), "tweaks": applied, "live": SELF_APPLY_ON}


def _apply_weight(orchestrator: Any, name: str, delta: int) -> dict[str, Any]:
    """Adjust a live agent's ATRM load weight. No-op (propose) unless SELF_APPLY_ON."""
    reg = getattr(orchestrator, "registry", None)
    if reg is None:
        return {"ok": False, "reason": "no registry"}
    agent = reg.agents.get(name) if hasattr(reg, "agents") else None
    if agent is None:
        return {"ok": False, "reason": f"agent {name} not found"}
    if not SELF_APPLY_ON:
        return {"ok": False, "reason": "propose-only (ZQM_SELF_APPLY off)", "current": getattr(agent, "load_score", None)}
    before = getattr(agent, "load_score", 0.0)
    agent.load_score = max(0.0, before + delta * 0.05)
    return {"ok": True, "before": before, "after": agent.load_score}
