"""
The Void — Agent Tool / Integration Runtime
============================================

Bridges the gap between an agent's DECLARED capabilities
(API_CALL, DATABASE_QUERY, MONITORING, FILE_PROCESSING, VECTOR_SEARCH, …)
and The Void's REAL backend systems (FLATSPACE memory, Garden compute, the local
Ollama model server, the observability pipeline, and — gated — external HTTP).

Previously `CognitiveProcessor._run_agent` only called the model and returned
text; the capability enums were decorative. This runtime lets an agent
actually *act*: the model emits a structured ACTION block, the runtime
executes the matching tool against the real service, and the result is fed
back so the agent can answer with grounded, system-sourced data.

Design:
  • ToolRegistry maps AgentCapability -> list[Tool].
  • run_agent_with_tools() injects an available-tools spec into the system
    prompt, parses the first ACTION:/ARGS: block from the model output,
    executes it, then calls the model again with the tool result to produce
    the final answer.
  • Fail-soft: if the model emits no ACTION, or a tool errors, we degrade
    gracefully (return the raw text, or a tool-error note) — never crash.
  • External HTTP is gated behind settings.allow_external_providers (the
    Void's self-hosted mandate is preserved).

Tool-call protocol the model is instructed to use (one block, anywhere in
its first response):

    ACTION: <tool_name>
    ARGS: <json object>

The runtime executes exactly one action per turn, then re-prompts with the
result so the agent can synthesize. (Multi-step could be added later.)
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from app.core.config import settings
from app.core.logger import get_logger
from app.models.agent import AgentCapability
from app.services.flatspace_service import FlatSpaceService
from app.services.garden_service import GardenService
from app.services.observability_service import ObservabilityService

log = get_logger("agent-runtime")

# ── Types ────────────────────────────────────────────────────────────────────

ToolFn = Callable[[Dict[str, Any]], Awaitable[Any]]
CallModelFn = Callable[..., Awaitable[str]]


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        capability: AgentCapability,
        run: ToolFn,
    ) -> None:
        self.name = name
        self.description = description
        self.capability = capability
        self.run = run

    def spec(self) -> str:
        return f"- {self.name}: {self.description}"


# ── Tool implementations (real system reach) ──────────────────────────────────

_flatspace = FlatSpaceService()
_garden = GardenService()
_obs = ObservabilityService()


async def _t_flatspace_search(args: Dict[str, Any]) -> Any:
    return await _flatspace.search(
        query=str(args.get("query", "")),
        tier=str(args.get("tier", "bitgarden")),
        limit=int(args.get("limit", 5)),
    )


async def _t_flatspace_retrieve(args: Dict[str, Any]) -> Any:
    return await _flatspace.retrieve(
        key=str(args.get("key", "")),
        tier=str(args.get("tier", "bitgarden")),
    )


async def _t_flatspace_store(args: Dict[str, Any]) -> Any:
    return await _flatspace.store(
        key=str(args.get("key", f"agent:{datetime.now(timezone.utc).isoformat()}")),
        value=args.get("value", {}),
        tier=str(args.get("tier", "bitgarden")),
    )


# ── quantum_llm bridge tools (in-process via the /api/quantum router) ──
def _quantum_bridge():
    from app.routers import quantum_llm_bridge as _b
    return _b


async def _t_quantum_verify(args: Dict[str, Any]) -> Any:
    return _quantum_bridge()._run("verify")


async def _t_quantum_infer(args: Dict[str, Any]) -> Any:
    return _quantum_bridge()._run("infer", json.dumps(args or {}))


async def _t_quantum_retrieve(args: Dict[str, Any]) -> Any:
    return _quantum_bridge()._run("retrieve", json.dumps(args or {}))


async def _t_quantum_models(args: Dict[str, Any]) -> Any:
    return _quantum_bridge()._run("models")


async def _t_quantum_nodes(args: Dict[str, Any]) -> Any:
    return _quantum_bridge()._run("nodes")


async def _t_garden_metrics(args: Dict[str, Any]) -> Any:
    return await _garden.get_node_metrics()


async def _t_garden_submit(args: Dict[str, Any]) -> Any:
    return await _garden.submit_job(
        task_id=str(args.get("task_id", "agent-task")),
        task_type=str(args.get("task_type", "ai_inference")),
        payload=args.get("payload", {}),
        gpu_required=bool(args.get("gpu_required", False)),
    )


async def _t_ollama_models(args: Dict[str, Any]) -> Any:
    """Mesh-wide model catalog (aggregated across N1/N2/N3/N4 Ollama)."""
    from app.services.mesh_ollama import router as mesh_ollama
    try:
        catalog = await mesh_ollama.list_models()
        return {
            "backends": catalog["backends"],
            "unique_models": catalog["unique_models"],
            "count": catalog["unique_models"],
        }
    except Exception as exc:
        # Fallback to local only if the mesh check fails.
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models, "count": len(models), "error": str(exc)}


async def _t_observability_log(args: Dict[str, Any]) -> Any:
    await _obs.log_event(
        event_type=str(args.get("event", "agent_action")),
        payload=args.get("payload", {}),
    )
    return {"logged": True}


async def _t_http_get(args: Dict[str, Any]) -> Any:
    """External reach — gated by the self-hosted mandate."""
    if not settings.allow_external_providers:
        raise PermissionError(
            "External HTTP is blocked: The Void is self-hosted. "
            "Set ZQM_ALLOW_EXTERNAL_PROVIDERS=true to enable."
        )
    url = str(args.get("url", ""))
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValueError("http_get requires an absolute http(s) URL")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        return {
            "status_code": resp.status_code,
            "body": resp.text[:2000],
            "headers": dict(resp.headers),
        }


# ── zqm-local-tools bridge (agents reach the host + ZQM-MESH via the toolkit) ──
# Shells out to C:/temp/zqm_tools_cli.py (run via the zqm-mcp venv python, which
# has paramiko + mcp) — the same proven subprocess pattern as the mesh_op.py tools.
# The CLI imports the zqm-local-tools server module and returns JSON
# {"ok":true,"result":<str>} / {"ok":false,"error":<str>}.
_ZQM_MCP_VENV_PY = r"C:/Users/zqmco/zqm-mcp/.venv/Scripts/python.exe"
_ZQM_TOOLS_CLI = r"C:/temp/zqm_tools_cli.py"


async def _t_zqm_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """Generic executor for any zqm-local-tools bridge tool."""
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [_ZQM_MCP_VENV_PY, _ZQM_TOOLS_CLI, tool_name, json.dumps(args)],
            capture_output=True, text=True, timeout=180,
        )
        out = (proc.stdout or proc.stderr).strip()
        if not out:
            return {"error": f"{tool_name} produced no output", "rc": proc.returncode}
        try:
            return json.loads(out)
        except Exception:
            return {"raw": out, "rc": proc.returncode}
    except Exception as exc:
        return {"error": f"{tool_name} bridge failed: {exc}"}


def _zqm_tool_fn(tool_name: str):
    async def _fn(args: Dict[str, Any]) -> Any:
        return await _t_zqm_tool(tool_name, args)
    return _fn


# ── Mesh action tools (agents ACT across the ZQM-MESH, not just reason) ──────
# These shell out to C:/temp/mesh_op.py (run via the Hermes venv python, which
# has paramiko + docker) so the Void can write/read state on peer nodes via the
# SMB broker share and publish to zqm-redis. Reuses the proven mesh_connect
# transport — no new services, no LAN-binding mutations.
_HERMES_VENV_PY = (
    r"C:/Users/zqmco/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
)
_MESH_OP = r"C:/temp/mesh_op.py"


async def _t_mesh_publish(args: Dict[str, Any]) -> Any:
    """Publish a state/message to the mesh (SMB broker share + redis pub).

    args: {topic: str, payload: any, target: "ALL"|"N1"|"N2"|"N3"|"N4"}
    Lets an agent drop cross-node state any peer (or the N4 aggregator) reads.
    """
    topic = str(args.get("topic", "void_message"))
    payload = args.get("payload", {})
    target = str(args.get("target", "ALL"))
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [_HERMES_VENV_PY, _MESH_OP, "publish", topic, json.dumps(payload), target],
            capture_output=True, text=True, timeout=120,
        )
        out = proc.stdout.strip() or proc.stderr.strip()
        return json.loads(out) if out.startswith("{") else {"raw": out}
    except Exception as exc:
        return {"error": f"mesh_publish failed: {exc}"}


async def _t_mesh_read(args: Dict[str, Any]) -> Any:
    """Read a mesh state/message doc written by a peer or this Void.

    args: {topic: str, target: "N1"|"N2"|"N3"|"N4" (default N4)}
    """
    topic = str(args.get("topic", "void_message"))
    target = str(args.get("target", "N4"))
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [_HERMES_VENV_PY, _MESH_OP, "read", topic, target],
            capture_output=True, text=True, timeout=60,
        )
        out = proc.stdout.strip() or proc.stderr.strip()
        return json.loads(out) if out.startswith("{") else {"raw": out}
    except Exception as exc:
        return {"error": f"mesh_read failed: {exc}"}


# ── Registry: capability -> tools ─────────────────────────────────────────────

TOOLS: Dict[str, Tool] = {
    "flatspace_search": Tool("flatspace_search", "Search FLATSPACE tiered memory by query.", AgentCapability.VECTOR_SEARCH, _t_flatspace_search),
    "flatspace_retrieve": Tool("flatspace_retrieve", "Retrieve a stored FLATSPACE record by key.", AgentCapability.DATABASE_QUERY, _t_flatspace_retrieve),
    "flatspace_store": Tool("flatspace_store", "Store a record into a FLATSPACE tier.", AgentCapability.DATABASE_QUERY, _t_flatspace_store),
    "garden_metrics": Tool("garden_metrics", "Fetch resource metrics from all Garden nodes.", AgentCapability.MONITORING, _t_garden_metrics),
    "garden_submit": Tool("garden_submit", "Submit a compute job to the ZQM Garden.", AgentCapability.API_CALL, _t_garden_submit),
    "ollama_models": Tool("ollama_models", "List models available on the local Ollama server.", AgentCapability.API_CALL, _t_ollama_models),
    "observability_log": Tool("observability_log", "Emit an observability event.", AgentCapability.MONITORING, _t_observability_log),
    "http_get": Tool("http_get", "Fetch an external URL (gated by self-hosted mandate).", AgentCapability.WEB_SEARCH, _t_http_get),
    "mesh_publish": Tool("mesh_publish", "Publish state/message to the ZQM mesh (SMB broker share across nodes + redis pub). Args: {topic, payload, target:'ALL'|node}.", AgentCapability.API_CALL, _t_mesh_publish),
    "mesh_read": Tool("mesh_read", "Read a mesh state/message doc from a peer node via the SMB broker. Args: {topic, target:node}.", AgentCapability.API_CALL, _t_mesh_read),
    # ── zqm-local-tools bridge (host + ZQM-MESH reach) ──
    "mesh_overview": Tool("mesh_overview", "Whole-mesh snapshot: SERVICE MATRIX (which ports open where) + per-node recon. Args: {compact:bool}.", AgentCapability.MONITORING, _zqm_tool_fn("mesh_overview")),
    "mesh_node_recon": Tool("mesh_node_recon", "One-shot full recon of a mesh node (identity/procs/ports/docker/disk). Args: {node:'N1'..'N4'}.", AgentCapability.MONITORING, _zqm_tool_fn("mesh_node_recon")),
    "mesh_ping_sweep": Tool("mesh_ping_sweep", "ICMP liveness sweep of the 4 mesh nodes. Args: {}.", AgentCapability.MONITORING, _zqm_tool_fn("mesh_ping_sweep")),
    "host_inventory": Tool("host_inventory", "WMI host inventory of this Void host (model/RAM/OS/uptime/CPU). Args: {}.", AgentCapability.MONITORING, _zqm_tool_fn("host_inventory")),
    "win_disk_inventory": Tool("win_disk_inventory", "Local fixed-disk free/total + low-free flag. Args: {}.", AgentCapability.MONITORING, _zqm_tool_fn("win_disk_inventory")),
    "win_event_errors": Tool("win_event_errors", "Tail Error/Warning Windows event-log entries. Args: {log:'System',count:20}.", AgentCapability.MONITORING, _zqm_tool_fn("win_event_errors")),
    "file_hash": Tool("file_hash", "sha256/sha1/md5 of a local file (forensics). Args: {path, algo:'sha256'}.", AgentCapability.FILE_PROCESSING, _zqm_tool_fn("file_hash")),
    "ollama_model_list": Tool("ollama_model_list", "List local Ollama models + free RAM. Args: {}.", AgentCapability.API_CALL, _zqm_tool_fn("ollama_model_list")),
    # ── quantum_llm bridge (mesh hybrid inference) — in-process via router ──
    "quantum_verify": Tool("quantum_verify", "Run quantum_llm.admin.verify() on the active mesh node. Args: {}.", AgentCapability.API_CALL, _t_quantum_verify),
    "quantum_infer": Tool("quantum_infer", "Hybrid quantum-classical forward pass. Args: {prompt, vocab, qubits, seq_len, d_model, n_layers, hidden}.", AgentCapability.API_CALL, _t_quantum_infer),
    "quantum_retrieve": Tool("quantum_retrieve", "Quantum retrieval query. Args: {query, top_k}.", AgentCapability.API_CALL, _t_quantum_retrieve),
    "quantum_models": Tool("quantum_models", "List installed quantum_llm inventory. Args: {}.", AgentCapability.API_CALL, _t_quantum_models),
    "quantum_nodes": Tool("quantum_nodes", "Sweep all mesh quantum nodes (health/verify). Args: {}.", AgentCapability.API_CALL, _t_quantum_nodes),
}

# Which capabilities unlock which tools
CAPABILITY_TOOLS: Dict[AgentCapability, List[str]] = {
    AgentCapability.VECTOR_SEARCH: ["flatspace_search"],
    AgentCapability.DATABASE_QUERY: ["flatspace_retrieve", "flatspace_store", "flatspace_search"],
    AgentCapability.API_CALL: ["garden_submit", "ollama_models", "garden_metrics", "mesh_publish", "mesh_read", "ollama_model_list",
                            "quantum_verify", "quantum_infer", "quantum_retrieve", "quantum_models", "quantum_nodes"],
    AgentCapability.MONITORING: ["garden_metrics", "ollama_models", "observability_log", "mesh_overview", "mesh_node_recon", "mesh_ping_sweep", "host_inventory", "win_disk_inventory", "win_event_errors"],
    AgentCapability.FILE_PROCESSING: ["file_hash"],  # file_read reserved (sandbox pending)
    AgentCapability.WEB_SEARCH: ["http_get"],
}


def tools_for_agent(capabilities: List[AgentCapability]) -> List[Tool]:
    """Resolve the tools an agent may use from its declared capabilities."""
    names: List[str] = []
    for cap in capabilities:
        names.extend(CAPABILITY_TOOLS.get(cap, []))
    # de-dup, preserve order
    seen = set()
    out: List[Tool] = []
    for n in names:
        if n not in seen and n in TOOLS:
            seen.add(n)
            out.append(TOOLS[n])
    return out


# ── Action parsing ─────────────────────────────────────────────────────────────

_ACTION_RE = re.compile(
    r"ACTION:\s*(?P<name>[A-Za-z0-9_]+)\s*\n\s*ARGS:\s*(?P<args>\{.*?\})",
    re.DOTALL,
)


def parse_action(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    m = _ACTION_RE.search(text)
    if not m:
        return None
    name = m.group("name")
    try:
        args = json.loads(m.group("args"))
    except json.JSONDecodeError:
        args = {}
    return name, args


def _tool_spec_block(tools: List[Tool], request_input: str = "") -> str:
    if not tools:
        return ""
    lines = "\n".join(t.spec() for t in tools)

    # Advisory trigger hints: when the request clearly concerns a reachable
    # system, tell the agent which tool is the obvious fit. Advisory only —
    # if the model still answers plainly, that is allowed (fail-soft).
    hint = ""
    text = (request_input or "").lower()
    triggers = {
        "ollama_models": ["model", "ollama", "list models", "available model", "what can i run"],
        "garden_metrics": ["garden", "node metric", "gpu", "compute node", "cluster status", "resource"],
        "garden_submit": ["submit job", "run job", "distribute", "inference job"],
        "flatspace_search": ["search memory", "flatspace", "recall", "what do we know", "prior"],
        "flatspace_retrieve": ["retrieve", "fetch record", "get key"],
        "flatspace_store": ["save", "store", "remember this", "persist"],
        "observability_log": ["log event", "emit metric", "record event"],
        "http_get": ["fetch url", "http get", "download from", "scrape"],
        "mesh_publish": ["publish to mesh", "broadcast", "notify mesh", "drop state", "mesh message", "send to node"],
        "mesh_read": ["read mesh", "read from node", "check node state", "mesh state", "peer state"],
        "mesh_overview": ["mesh overview", "mesh status", "service matrix", "overview", "mesh health", "what's the mesh", "what is the mesh", "node status", "all nodes"],
        "mesh_node_recon": ["recon", "node recon", "inspect node", "deep dive", "full recon"],
        "mesh_ping_sweep": ["ping sweep", "who is up", "node alive", "mesh liveness"],
        "host_inventory": ["host inventory", "this host", "system info", "hardware", "my machine"],
        "win_disk_inventory": ["disk space", "free disk", "drive space", "storage"],
        "win_event_errors": ["event errors", "event log", "system errors", "windows errors"],
        "file_hash": ["hash file", "checksum", "sha256", "file integrity"],
    }
    matched = [name for name, kws in triggers.items()
               if name in TOOLS and any(kw in text for kw in kws)]
    if matched:
        hint = (
            "\n\nHINT: This request likely calls for one of these tools — "
            "prefer using it rather than answering from memory: "
            + ", ".join(matched)
            + "."
        )

    # Attractor-frame hint: when the request looks like an open-ended headline
    # or prompt, offer a deterministic reframe with more engagement leverage.
    # Pattern harvested from Moltbook high-attention corpus: [concept] +
    # [failure_mode] + [anthropomorphic_verb]. Fail-soft: only emit when
    # the input is short and doesn't already have a tool match.
    attractor = ""
    words = text.split()
    if len(words) >= 3 and len(words) <= 25 and not matched:
        candidate = " ".join(words)
        attractor = (
            "\n\nATTRACTOR FRAME OPTION: "
            "Restate this as a system-facing observation with the shape "
            f"'{candidate} — [concept] + [failure mode] + [verb]'. "
            "For example: 'Timeout behavior is where your system's manners live'. "
            "Use a concrete system concept from the prompt, name a failure mode, "
            "and use an anthropomorphic verb."
        )

    return (
        "\n\nYou have access to these tools to reach The Void's systems:\n"
        f"{lines}\n"
        "To use one, respond with a single block:\n"
        "ACTION: <tool_name>\n"
        'ARGS: {"key": "value"}\n'
        "After the tool runs, you will receive its result and may answer. "
        "If no tool is needed, just answer normally."
        + hint
        + attractor
    )


# ── Main entry: run an agent with tool reach ───────────────────────────────────

_TRIGGER_KEYWORDS: Dict[str, List[str]] = {
    "ollama_models": ["model", "ollama", "list models", "available model", "what can i run", "which models"],
    "garden_metrics": ["garden", "node metric", "gpu", "compute node", "cluster status", "resource", "node status"],
    "garden_submit": ["submit job", "run job", "distribute", "inference job"],
    "flatspace_search": ["search memory", "flatspace", "recall", "what do we know", "prior", "search our"],
    "flatspace_retrieve": ["retrieve", "fetch record", "get key"],
    "flatspace_store": ["save", "store", "remember this", "persist"],
    "observability_log": ["log event", "emit metric", "record event"],
    "http_get": ["fetch url", "http get", "download from", "scrape"],
    "mesh_publish": ["publish to mesh", "broadcast", "notify mesh", "drop state", "mesh message", "send to node"],
    "mesh_read": ["read mesh", "read from node", "check node state", "mesh state", "peer state"],
    # ── zqm-local-tools bridge triggers (deterministic, server-side) ──
    "mesh_overview": ["mesh overview", "mesh status", "service matrix", "overview", "mesh health", "what's the mesh", "what is the mesh", "node status", "all nodes"],
    "mesh_node_recon": ["recon", "node recon", "inspect node", "deep dive", "full recon"],
    "mesh_ping_sweep": ["ping sweep", "who is up", "node alive", "mesh liveness"],
    "host_inventory": ["host inventory", "this host", "system info", "hardware", "my machine"],
    "win_disk_inventory": ["disk space", "free disk", "drive space", "storage"],
    "win_event_errors": ["event errors", "event log", "system errors", "windows errors"],
    "file_hash": ["hash file", "checksum", "sha256", "file integrity"],
}


def resolve_preferred_tool(request_input: str, available: List[Tool]) -> Optional[Tool]:
    """
    Deterministic tool trigger: if the request clearly matches a tool AND
    that tool is in the agent's available set, return it. This guarantees
    reliable tool use for obvious domain requests instead of depending on
    the model's spontaneity (small models often skip prompt-injected calls).
    Fail-soft: returns None if no confident match.
    """
    text = (request_input or "").lower()
    avail_names = {t.name for t in available}
    for name, kws in _TRIGGER_KEYWORDS.items():
        if name in avail_names and any(kw in text for kw in kws):
            return TOOLS.get(name)
    return None


def _system_tools_for_text(request_input: str) -> List[Tool]:
    """
    Return the zqm-local-tools system Tools implied by the request text, using
    the same keyword map as resolve_preferred_tool. Used by run_agent_with_tools
    to augment ANY agent's reach so a system-intent request (mesh overview,
    host inventory, disk space, event errors, file hash, ping sweep, node recon)
    acts even on the default/basic routing path (which otherwise selects only
    NLP/Reasoning agents with no capabilities). Empty list if no match.
    """
    text = (request_input or "").lower()
    out: List[Tool] = []
    for name, kws in _TRIGGER_KEYWORDS.items():
        if name in TOOLS and any(kw in text for kw in kws):
            t = TOOLS.get(name)
            if t and t.name not in {x.name for x in out}:
                out.append(t)
    return out



async def _retrieve_memory_context(query: str, limit: int = 5) -> str:
    """Retrieval-augmented grounding: top-k semantic FLATSPACE hits for the
    request, formatted as a context block. Fail-soft: '' on any error."""
    try:
        hits = await _flatspace.search(query=query, tier="bitgarden", limit=limit)
        if not hits:
            return ""
        lines = []
        for h in hits:
            score = h.get("score")
            score_s = f" (score={score})" if isinstance(score, (int, float)) else ""
            try:
                val = json.dumps(h.get("value"), default=str)[:600]
            except Exception:
                val = str(h.get("value"))[:600]
            lines.append(f"- [{h.get('key')}{score_s}] {val}")
        return (
            "\n\nRELEVANT MEMORY (retrieved from FLATSPACE, most similar first):\n"
            + "\n".join(lines)
        )
    except Exception as exc:
        log.debug("memory retrieval skipped", error=str(exc))
        return ""


async def run_agent_with_tools(
    agent,
    request_input: str,
    context: Optional[Dict[str, Any]],
    call_model: CallModelFn,
    max_tool_rounds: int = 2,
    tools: Optional[List[Tool]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run one agent, giving it real reach into The Void's systems via tools.

    Args:
        agent: the Agent instance (needs .system_prompt, .capabilities).
        request_input: the user/task text.
        context: optional task context (session history, etc.).
        call_model: callback -> str, the model invoker
            (CognitiveProcessor._call_ai_provider bound method).
        max_tool_rounds: how many action→result→re-prompt cycles to allow.
        tools: optional explicit tool set. If omitted, derived from the
            agent's capabilities. Callers may pass an AUGMENTED set (e.g. the
            zqm-local-tools system tools) so a system-intent request can act
            even when the base agent lacks those capabilities.
        input_schema: optional JSON Schema for validating tool `args` against
            before execution. If provided, mismatches are surfaced as tool
            errors instead of crashing or silently ignoring bad inputs.

    Returns:
        (final_output_text, tool_trace) where tool_trace is a list of
        {tool, args, result, ok} dicts for audit.
    """
    if tools is None:
        tools = tools_for_agent(getattr(agent, "capabilities", []))

    # System-reach augmentation: if the request text clearly implies one of the
    # zqm-local-tools system tools (mesh/host/disk/event/hash), make that tool
    # available to THIS agent regardless of its base capabilities. This lets a
    # plain NLP agent act on "give me the mesh overview" / "host inventory" via
    # the deterministic pre-tool inside run_agent_with_tools (fail-soft: empty if
    # no match). Mirrors resolve_preferred_tool but yields the full tool set.
    system_tools = _system_tools_for_text(request_input)
    if system_tools:
        known = {t.name for t in tools}
        tools = tools + [t for t in system_tools if t.name not in known]
    tool_trace: List[Dict[str, Any]] = []

    system_prompt = (agent.system_prompt or "") + _tool_spec_block(tools, request_input)

    # Retrieval-augmented grounding: pull top-k relevant memory so the agent
    # is grounded in past context even if it doesn't emit an ACTION block.
    memory_ctx = await _retrieve_memory_context(request_input, limit=5)
    if memory_ctx:
        system_prompt += memory_ctx

    # Deterministic pre-tool: if the request clearly matches an available
    # tool, execute it first and hand the result to the model. This makes
    # tool use reliable for obvious domain asks (independent of model
    # spontaneity). Fail-soft: tool error is noted, model still answers.
    pref = resolve_preferred_tool(request_input, tools)
    if pref is not None:
        try:
            if input_schema:
                args_valid, args_error = _validate_tool_args(pref.name, {}, input_schema)
                if not args_valid:
                    raise ValueError(f"Input schema validation failed: {args_error}")
            presult = await pref.run({})
            ok = True
            presult_str = json.dumps(presult, default=str)[:1500]
        except Exception as exc:
            ok = False
            presult_str = f"ERROR: {exc}"
            log.warning("Preferred tool execution failed", tool=pref.name, error=str(exc))
        tool_trace.append({"tool": pref.name, "args": {}, "ok": ok, "result": presult_str})
        system_prompt += (
            f"\n\nA tool was already run for this request. Its result:\n"
            f"TOOL RESULT ({pref.name}): {presult_str}\n"
            "Use this result to answer the user's request directly."
        )

    # First model call
    messages = [{"role": "system", "content": system_prompt}]
    if context and context.get("session_history"):
        messages.append({
            "role": "system",
            "content": f"Previous conversation:\n{context['session_history']}",
        })
    messages.append({"role": "user", "content": request_input})

    raw = await call_model(agent=agent, messages=messages)
    current = raw

    for _ in range(max_tool_rounds):
        parsed = parse_action(current)
        if not parsed:
            break
        name, args = parsed
        if name not in TOOLS:
            tool_trace.append({"tool": name, "args": args, "ok": False, "result": "unknown tool"})
            # let the model know and re-prompt once
            messages.append({"role": "assistant", "content": current})
            messages.append({"role": "user", "content": f"Tool '{name}' is not available. Answer without it."})
            current = await call_model(agent=agent, messages=messages)
            continue

        try:
            if input_schema:
                args_valid, args_error = _validate_tool_args(name, args, input_schema)
                if not args_valid:
                    raise ValueError(f"Input schema validation failed: {args_error}")
            result = await TOOLS[name].run(args)
            ok = True
            result_str = json.dumps(result, default=str)
            if len(result_str) > 1500:
                truncation_note = f"tool_result_truncated:{name}:{len(result_str)}"
                result_str = result_str[:1500]
            else:
                truncation_note = None
        except Exception as exc:
            ok = False
            result_str = f"ERROR: {exc}"
            truncation_note = None
            log.warning("Tool execution failed", tool=name, error=str(exc))

        tool_trace.append({"tool": name, "args": args, "ok": ok, "result": result_str})
        # Feed the result back so the agent can synthesize a grounded answer
        messages.append({"role": "assistant", "content": current})
        messages.append({
            "role": "user",
            "content": f"TOOL RESULT ({name}): {result_str}\n\nNow answer the original request using this result.",
        })
        current = await call_model(agent=agent, messages=messages)
        if truncation_note:
            return current, tool_trace, truncation_note

    return current, tool_trace, None


def _validate_tool_args(tool_name: str, args: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Best-effort input-schema validation for tool arguments.

    schema shape:
      {
        "type": "object",
        "properties": {
          "<arg_name>": {"type": "string", "required": true, ...}
        }
      }

    Always returns (valid, error_message). Does not raise.
    """
    if not isinstance(schema, dict) or not isinstance(args, dict):
        return False, "schema/args must be dicts"
    properties = schema.get("properties") or {}
    if not properties:
        return True, ""
    for name, rule in properties.items():
        required = rule.get("required", False)
        if required and name not in args:
            return False, f"missing required arg: {name}"
        if name in args:
            value = args[name]
            expected = (rule.get("type") or "").lower()
            if expected == "string" and not isinstance(value, str):
                return False, f"arg {name} must be string"
            if expected == "integer" and not isinstance(value, int):
                return False, f"arg {name} must be integer"
            if expected == "boolean" and not isinstance(value, bool):
                return False, f"arg {name} must be boolean"
            if expected == "array" and not isinstance(value, list):
                return False, f"arg {name} must be array"
    return True, ""


_OFFPLATFORM_RE = re.compile(
    r"(?P<url>https?://[^\s\"'<>]+)"
    r"|(?P<handle>@[A-Za-z0-9_]{2,40})"
    r"|(?P<addr40>0x[a-fA-F0-9]{40})"
    r"|(?P<tx64>\b[a-fA-F0-9]{64}\b)"
    r"|(?P<invoice>invoice[-_]?\w+)"
    r"|(?P<contract>contract[-_]?\w+)"
    r"|(?P<ticket>[A-Z]{2,6}\d{4,})"
)


def scan_off_platform_refs(text: str) -> List[Dict[str, Any]]:
    """
    Extract off-platform references from free text: URLs, @handles,
    hex addresses, invoice/contract/ticket IDs. Used for audit, not blocking.
    Returns unique hits capped at 50.
    """
    if not text:
        return []
    hits = []
    seen = set()
    for m in _OFFPLATFORM_RE.finditer(text):
        label = m.lastgroup or "match"
        val = m.group(0)
        if val not in seen:
            seen.add(val)
            hits.append({"label": label, "match": val[:120]})
    return hits[:50]
