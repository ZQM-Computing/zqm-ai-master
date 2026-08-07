"""
The Void AI Orchestration System — Version manifest (single source of truth)

Version: 2.1.0 | ZQM Computing LLC

This module is the canonical version for The Void. Bump __version__ and
RELEASE_NOTES together on each release, and keep pyproject.toml in sync.
"""

from __future__ import annotations

__version__ = "2.1.4"
__codename__ = "Conversational"
__build_epoch__ = "2026-07-28"

# Components shipped in this release (what 'version the void' captured).
RELEASE_NOTES = {
    "2.1.4": [
        "P10: Conversational Surface — The Void can now be spoken to over HTTP via "
        "POST /api/void/talk (admin). It reflects on its own live health, self-improvement "
        "ledger, and build, and answers truthfully; if a live Ollama model is reachable it "
        "routes through an agent for genuine inference, otherwise it returns an honest "
        "self-reflection from its telemetry (no fabricated thought when local inference is "
        "offline). This is the dialogue surface that, combined with /api/self-improve/run, "
        "drives continuous self-improvement. Bump to 2.1.4 'Conversational'.",
    ],
    "2.1.3": [
        "P9: Security hardening (applied 2026-07-28). (1) Self-replication no longer bakes the "
        "hardcoded weak default SECRET_KEY into replicas — it derives the key from the live "
        "process (or mints a fresh per-node key if the default is still in use), so a cloned "
        "Void is not trivially JWT-forgeable from the public repo. (2) Replica launcher now binds "
        "0.0.0.0 (was 127.0.0.1, which trapped replicas on localhost and made them mesh-unreachable). "
        "(3) Self-improvement critique prompt no longer emits a literal PATCH/SEARCH/REPLACE template "
        "that the 3B model parroted back as 'findings'; added a <placeholder>/template guard in "
        "self_expand + self_apply so template echoes are rejected instead of polluting the ledger.",
    ],
    "2.1.2": [
        "P8: Self-Aware Health — /api/status now reports TRUTHFULLY. Fixed version drift "
        "(settings.app_version now sourced from version.py, so status==version). database field "
        "reflects The Void's real datastore (FLATSPACE SQLite: healthy/unreachable) instead of "
        "frozen 'unknown'; redis honestly reported 'disabled' (not used). Added self_apply gate "
        "visibility. Core status (database + agent pool) is now SEPARATED from optional external "
        "deps (ZQM Garden, Observability) via a new external_services field — a down garden host "
        "no longer falsely marks The Void 'degraded'. environment sourced from ENVIRONMENT.",
    ],
    "2.1.1": [
        "P5: Mesh Ollama federation — The Void routes inference across the ZQM-MESH Ollama pool (N1/N2/N3/N4) instead of local only. Model-aware selection (local N4 preferred), parallel health-check, failover, aggregated 65-model catalog. /api/mesh/ollama status endpoint. Concurrency-safe (asyncio.Lock + atomic index swap) + force-refresh-on-404 retry. Verified: qwen2.5:3b->N4-local, gemma4:latest->N3, triage-bounty-zqm:latest->N1.",
    ],
    "2.1.0": [
        "A-D: 21-agent pool, ATRM load-aware routing, tools (flatspace/ollama real; "
        "garden/observability fail-soft on dead remote; http_get gated by self-hosted mandate).",
        "P1: Local FlatSpace SQLite store (flatspace_local.db renamed -> flatspace_local.db) so "
        "memory/audit work offline when the remote flatspace host (dead) is down.",
        "P2: Self-apply pipeline — panel can emit a structured PATCH; validated in staging "
        "(compile+import), promoted atomically, audited to waxcell, sets _needs_restart. "
        "Gated by ZQM_SELF_APPLY (default off).",
        "P3-corrected: Webhook receivers (GitHub/Azure/deploy) now actually ingest — publish "
        "to event bus + audit to waxcell + create orchestrator task (replaces dead edge-connector raise).",
        "P4: Autonomous self systems integration — findings->live pool tuning, native "
        "roundtable (in-Void multi-agent), and system state surfaced via API "
        "(/api/flatspace, /api/task-audit, /api/mcp-audit).",
        "SSE: Hardened Server-Sent Events (/api/stream, /api/stream/webhooks) with retry "
        "field, 15s heartbeat, client-disconnect detection, structured error/done. In-process "
        "event bus (app/core/event_bus.py) feeds it.",
        "Bug fixes: removed `await` on sync submit_task; downgraded misleading FLATSPACE "
        "store/retrieve warnings in auto mode + added _remote_known_down short-circuit.",
    ],
    "2.0.0": [
        "Initial The Void AI Orchestration System — 21-agent pool, cognitive processor, "
        "self-improvement loop (propose-only), FlatSpace tiered memory (remote flatspace).",
    ],
}


def get_version() -> dict:
    """Return the full version manifest (also exposed at /api/version)."""
    return {
        "name": "The Void",
        "product": "zqm-void",
        "version": __version__,
        "codename": __codename__,
        "build_epoch": __build_epoch__,
        "zqm_ai_id": "ZQM-ZQM_AI-004",
        "components": RELEASE_NOTES.get(__version__, []),
    }

