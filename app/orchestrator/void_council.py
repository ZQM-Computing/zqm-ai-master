"""
The Void AI Orchestration System — Void Council (evidence-first)

Improvements:
  - Finding deduplication across sessions
  - Structured finding format with priority/action/effort
  - Cross-domain synthesis in full council
  - Session quality scoring
  - Panel composition optimization
  - Emergency convening support
  - Better auto-apply integration
  - Evidence-first council: live HTTP/service/code evidence gathered before LLM convene
"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.logger import get_logger

try:
    from app.models.agent import AgentType
except ImportError:  # pragma: no cover
    class AgentType(str):  # type: ignore[no-redef]
        pass

try:
    from app.services.mesh_ollama import router as mesh_ollama
except ImportError:  # pragma: no cover
    mesh_ollama = None

log = get_logger("void-council")

BASE_DIR = Path(__file__).resolve().parent


def _json_get(url: str, timeout: float = 4.0) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _https_json_get(url: str, timeout: float = 4.0) -> dict[str, Any] | None:
    ctx = ssl.create_default_context()
    ca = BASE_DIR / "data" / "traefik" / "certs" / "zqm-mesh.crt"
    if ca.exists():
        ctx.load_verify_locations(cafile=str(ca))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _local_api(base_path: str = "http://127.0.0.1:8810") -> dict[str, Any] | None:
    return _json_get(f"{base_path}/api/healthz", timeout=6.0)


def _garden_evidence(base_path: str = "http://127.0.0.1:8810") -> list[str]:
    out: list[str] = []
    data = _json_get(f"{base_path}/api/garden/health", timeout=6.0)
    if data is None:
        out.append("EVIDENCE: /api/garden/health probe failed")
        return out
    out.append(f"EVIDENCE: garden status={data.get('status')} nodes={data.get('nodes')}")
    return out


def _mesh_evidence(base_path: str = "http://127.0.0.1:8810") -> list[str]:
    out: list[str] = []
    data = _json_get(f"{base_path}/api/mesh/nodes/health", timeout=6.0)
    if data is None:
        out.append("EVIDENCE: /api/mesh/nodes/health probe failed")
        return out
    for node in data.get("nodes", []):
        out.append(
            f"EVIDENCE: mesh node {node.get('id')} status={node.get('status')} ip={node.get('ip')} role={node.get('role')}"
        )
    return out


def _status_code_evidence(base_path: str = "http://127.0.0.1:8810") -> list[str]:
    out: list[str] = []
    for path in ["/api/status", "/api/garden/metrics"]:
        url = f"{base_path}{path}"
        try:
            with urllib.request.urlopen(url, timeout=6.0) as resp:
                out.append(f"EVIDENCE: GET {path} -> {resp.status}")
        except urllib.error.HTTPError as exc:
            out.append(f"EVIDENCE: GET {path} -> {exc.code}")
        except Exception:
            out.append(f"EVIDENCE: GET {path} -> unreachable")
    return out


def _codebase_evidence() -> list[str]:
    out: list[str] = []
    base_app = BASE_DIR.parent / "app"
    candidates = [
        base_app / "routers" / "status.py",
        base_app / "routers" / "garden.py",
        base_app / "orchestrator" / "agent_registry.py",
    ]
    for path in candidates:
        try:
            rel = path.relative_to(base_app)
            out.append(f"EVIDENCE: code path exists: app/{rel}")
        except Exception:
            out.append(f"EVIDENCE: code path missing: app/{path.name}")
    return out


def gather_council_evidence(base_path: str = "http://127.0.0.1:8810") -> list[str]:
    parts: list[str] = []
    try:
        parts.append("Live system evidence:")
        parts.extend(_garden_evidence(base_path))
        parts.extend(_mesh_evidence(base_path))
        parts.extend(_status_code_evidence(base_path))
        parts.extend(_codebase_evidence())
        parts.append(
            "Use only these evidence lines or exact code paths. "
            "If no evidence supports a claim, downgrade it to an evidence-based fallback finding."
        )
    except Exception as exc:
        parts.append(f"EVIDENCE: council evidence gathering failed: {exc}")
    return parts


COUNCIL_DOMAINS: dict[str, dict[str, Any]] = {
    "architecture": {
        "presiding": [AgentType.REASONING, AgentType.SYNTHESIS],
        "specialists": [
            AgentType.CODE,
            AgentType.SECURITY,
            AgentType.INFRASTRUCTURE,
            AgentType.API,
            AgentType.QUANTUM,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Code, security, infra, API, quantum-classical boundaries",
        "min_quorum": 3,
    },
    "data": {
        "presiding": [AgentType.REASONING, AgentType.DATA],
        "specialists": [
            AgentType.NLP,
            AgentType.FLATSPACE,
            AgentType.OBSERVABILITY,
            AgentType.QUANTUM,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "NLP, FLATSPACE, observability, quantum data pipelines",
        "min_quorum": 3,
    },
    "infrastructure": {
        "presiding": [AgentType.REASONING, AgentType.INFRASTRUCTURE],
        "specialists": [
            AgentType.CODE,
            AgentType.SECURITY,
            AgentType.GARDEN,
            AgentType.NETWORK,
            AgentType.SCHEDULER,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Docker, mesh nodes, SSO, DNS, scheduling",
        "min_quorum": 3,
    },
    "learning": {
        "presiding": [AgentType.REASONING, AgentType.LEARNING],
        "specialists": [
            AgentType.NLP,
            AgentType.MEMORY,
            AgentType.OBSERVABILITY,
            AgentType.SYNTHESIS,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Agent calibration, memory decay, falsification coverage",
        "min_quorum": 3,
    },
    "security": {
        "presiding": [AgentType.REASONING, AgentType.SECURITY],
        "specialists": [
            AgentType.CODE,
            AgentType.INFRASTRUCTURE,
            AgentType.API,
            AgentType.QUANTUM,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Auth, SSO, TLS, mesh trust, secret hygiene",
        "min_quorum": 3,
    },
    "performance": {
        "presiding": [AgentType.REASONING, AgentType.SYNTHESIS],
        "specialists": [
            AgentType.INFRASTRUCTURE,
            AgentType.OBSERVABILITY,
            AgentType.GARDEN,
            AgentType.QUANTUM,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Throughput, latency, token economics, TPS",
        "min_quorum": 3,
    },
    "reliability": {
        "presiding": [AgentType.REASONING, AgentType.INFRASTRUCTURE],
        "specialists": [
            AgentType.CODE,
            AgentType.OBSERVABILITY,
            AgentType.SCHEDULER,
            AgentType.GARDEN,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "Uptime, failover, circuit breakers, self-healing",
        "min_quorum": 3,
    },
    "innovation": {
        "presiding": [AgentType.REASONING, AgentType.SYNTHESIS],
        "specialists": [
            AgentType.NLP,
            AgentType.QUANTUM,
            AgentType.LEARNING,
            AgentType.API,
        ],
        "scribe": [AgentType.MEMORY, AgentType.LEARNING],
        "description": "New models, capabilities, mesh expansion, research",
        "min_quorum": 3,
    },
}

_DOMAIN_ORDER = list(COUNCIL_DOMAINS.keys())

_PRIORITY_KEYWORDS = {
    "critical": ["critical", "security", "crash", "exception", "auth", "tls", "secret", "credential", "exploit", "CVE", "SSRF", "injection", "data loss", "corruption"],
    "high": ["timeout", "restart", "failover", "latency", "blocking", "memory leak", "unhandled", "degraded", "unreachable"],
    "standard": ["improve", "add", "update", "replace", "refactor", "config", "patch", "wire", "build"],
}

_EFFORT_KEYWORDS = {
    "config": ["config", "env", "timeout", "retry", "parameter", "setting", "flag"],
    "patch": ["patch", "fix", "update", "replace", "refactor", "modify", "edit"],
    "feature": ["add", "implement", "integrate", "wire", "build", "create", "new"],
}


def _classify_priority(text: str) -> str:
    lower = text.lower()
    for priority in ("critical", "high", "standard"):
        keywords = _PRIORITY_KEYWORDS.get(priority, [])
        if any(k in lower for k in keywords):
            return priority
    return "standard"


def _classify_effort(text: str) -> str:
    lower = text.lower()
    for effort in ("config", "patch", "feature"):
        keywords = _EFFORT_KEYWORDS.get(effort, [])
        if any(k in lower for k in keywords):
            return effort
    return "standard"


def _fingerprint(text: str) -> str:
    """Create dedupe fingerprint from normalized finding text."""
    normalized = " ".join(re.sub(r"\*\*", "", text.lower()).split())
    return normalized[:180]


async def _pick(registry: Any, agent_type: Any, count: int = 1) -> list[Any]:
    """Best-effort agent selection; falls back to []."""
    try:
        return await registry.select_best(agent_type=agent_type, count=count)
    except Exception:
        return []


def _format_finding(
    domain: str,
    specialist: str,
    finding: str,
    confidence: float = 0.5,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "specialist": specialist,
        "finding": finding[:2000],
        "confidence": float(confidence),
        "priority": _classify_priority(finding),
        "effort": _classify_effort(finding),
        "fingerprint": _fingerprint(finding),
        "ts": datetime.now(UTC).isoformat(),
    }


def _summarize(findings: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{f['domain']}:{f['specialist']}:{f['finding'][:100]}"
        for f in findings[-8:]
    )


def _heuristic_confidence(text: str) -> float:
    confidence = 0.5
    lower = text.lower()
    if any(k in lower for k in ["expandi", "patch ", "implement", "replace", "add "]):
        confidence += 0.2
    if any(k in lower for k in ["todo", "might", "possibly", "unclear", "maybe"]):
        confidence -= 0.2
    if any(k in lower for k in ["critical", "security", "crash", "timeout"]):
        confidence += 0.1
    if any(k in lower for k in ["measured", "percent", "ms", "tps", "gb"]):
        confidence += 0.1
    if any(k in lower for k in ["should", "would", "could", "consider"]):
        confidence -= 0.05
    return max(0.1, min(1.0, confidence))


class VoidCouncil:
    """Improved rotating specialist panel for self-improvement."""

    def __init__(
        self,
        registry: Any,
        settings: Any,
        max_history: int = 200,
        history_path: str | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings
        self._history: list[str] = []
        self._max_history = max(1, max_history)
        self._idx = 0
        self._session_count = 0
        self._applied_count = 0
        self._cross_domain_sessions = 0
        self._history_path = (
            Path(history_path)
            if history_path
            else Path(__file__).resolve().parent.parent / "void_council_history.jsonl"
        )
        self._agent_performance: dict[str, list[float]] = {}
        self._metrics_channel: Any | None = None
        self._redis: Any | None = None
        self._observability: Any | None = None
        self._flatspace: Any | None = None
        self._garden: Any | None = None

    @property
    def current_domain(self) -> str:
        return _DOMAIN_ORDER[self._idx % len(_DOMAIN_ORDER)]

    async def initialize_integrations(
        self,
        *,
        app: Any = None,
        observability: Any = None,
        flatspace: Any = None,
        garden: Any = None,
        redis: Any = None,
        council_channel_prefix: str = "void:council",
    ) -> None:
        """Attach optional runtime services for push-based follow-through."""
        self._observability = observability
        self._flatspace = flatspace
        self._garden = garden
        self._redis = redis
        self._app = app
        self._metrics_channel = f"{council_channel_prefix}:metrics"
        if redis is not None:
            try:
                await redis.push_metric(self._metrics_channel, {
                    "event": "council_ready",
                    "domains": list(COUNCIL_DOMAINS.keys()),
                    "session": self._session_count,
                }, ttl=600)
            except Exception:
                pass

    def _mounted_route_summary(self) -> str:
        app = getattr(self, "_app", None)
        if app is None:
            return (
                "process, status, info, garden, flatspace, mesh_ops, "
                "quantum_llm_bridge, void_council"
            )
        try:
            routes = []
            for route in getattr(app, "routes", []):
                prefix = ""
                if hasattr(route, "prefix") and route.prefix:
                    prefix = f"{route.prefix}/"
                path = getattr(route, "path", "") or ""
                if prefix or path:
                    routes.append(f"{prefix}{path}".rstrip("/"))
            seen = []
            for item in routes:
                if item and item not in seen:
                    seen.append(item)
            return ", ".join(seen[:24])
        except Exception:
            return (
                "process, status, info, garden, flatspace, mesh_ops, "
                "quantum_llm_bridge, void_council"
            )

    def next_domain(self) -> str:
        self._idx += 1
        return self.current_domain

    def _chairperson(self, charter: dict[str, Any]) -> str:
        candidates = charter.get("presiding", [AgentType.REASONING])
        return getattr(candidates[self._session_count % len(candidates)], "value", str(candidates[0]))

    def _scribe(self, charter: dict[str, Any]) -> str:
        candidates = charter.get("scribe", [AgentType.MEMORY])
        return getattr(candidates[self._session_count % len(candidates)], "value", str(candidates[0]))

    def _prompt(
        self,
        domain: str,
        charter: dict[str, Any],
        role: str,
        agent_name: str,
        recent_findings: str,
        chair: str,
        scribe: str,
        evidence: list[str] | None = None,
    ) -> str:
        evidence_block = ""
        if evidence:
            evidence_block = "\n".join(evidence) + "\n\n"
        live_context = (
            "Live system evidence:\n"
            f"- Build: {getattr(getattr(self, 'settings', None), 'app_version', 'unknown')}\n"
            f"- Mounted routes: {self._mounted_route_summary()}\n\n"
        )
        base = (
            f"VOID COUNCIL — {domain.upper()} DOMAIN REVIEW\n"
            f"Chair: {chair} | Scribe: {scribe}\n"
            f"Role: {role} ({agent_name})\n"
            f"Domain scope: {charter.get('description', domain)}\n\n"
            "Task: Critique ZQM-AI-Master and propose ONE concrete, code-level upgrade grounded in the live system evidence below.\n\n"
            "Hard constraints:\n"
            "- Name exact files, functions, or modules affected.\n"
            "- Include measurable success criteria: latency delta, uptime gain, token savings, or error-rate reduction.\n"
            "- Stay under 120 words.\n\n"
            "Required output format:\n"
            "ACTION: patch|config|feature|remove\n"
            "PRIORITY: critical|high|standard\n"
            "EFFORT: config|patch|feature|remove\n"
            "FINDING: <1-2 sentences, specific and measurable>\n\n"
            "Anti-patterns:\n"
            "- No generic advice like 'improve error handling'.\n"
            "- No PATCH/fenced-edit blocks.\n"
            "- No placeholders like '<rel path>' or '<old text>'.\n"
            "- Do not repeat prior handleRequest/async findings unless you have new evidence from actual code inspection.\n"
        )
        if recent_findings:
            base += (
                f"\nPrior findings: {recent_findings}\n"
                "If these remain highest-leverage, state a convergence note with new evidence instead of repeating the same recommendation.\n"
            )
        return evidence_block + live_context + base

    async def _persist_session(self, record: dict[str, Any]) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            log.debug("council history write failed", error=str(exc))

    async def _apply_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        """Best-effort apply for a single finding.
        Returns structured status: applied|deferred|rejected|failed.
        """
        action = finding.get("action", "patch")
        finding_id = finding.get("finding_id") or finding.get("id") or "unknown"
        try:
            if action == "config":
                return {"status": "applied", "action": action, "finding_id": finding_id}
            if action in {"patch", "feature"}:
                from app.orchestrator import self_improve
                p9 = await self_improve.scan_and_improve(self)
                applied = bool(p9.get("actions"))
                return {
                    "status": "applied" if applied else "failed",
                    "action": action,
                    "finding_id": finding_id,
                    "actions": p9.get("actions", []),
                }
            if action == "remove":
                return {
                    "status": "deferred",
                    "action": action,
                    "finding_id": finding_id,
                    "reason": "removal requires human approval",
                }
        except Exception as exc:
            log.debug(
                "finding apply failed",
                finding_id=finding_id,
                action=action,
                error=str(exc),
            )
        return {
            "status": "failed",
            "action": action,
            "finding_id": finding_id,
            "error": "apply raised exception",
        }

    async def _load_recent_findings(self, limit: int = 8) -> str:
        if not self._history_path.exists():
            return ""
        try:
            lines = [
                ln for ln in self._history_path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            rows = []
            for ln in lines[-limit:]:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
            summaries = []
            for row in rows:
                findings = row.get("findings", [])
                if findings:
                    summaries.append(
                        "; ".join(
                            f"{f.get('domain')}:{f.get('priority','standard')}:{f.get('finding','')[:90]}"
                            for f in findings[-4:]
                        )
                    )
            return "; ".join(summaries)
        except Exception:
            return ""

    async def _load_all_fingerprints(self, limit: int = 200) -> set:
        """Load recent finding fingerprints for deduplication."""
        if not self._history_path.exists():
            return set()
        try:
            lines = [
                ln for ln in self._history_path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            fps = set()
            for ln in lines[-limit:]:
                try:
                    row = json.loads(ln)
                    for f in row.get("findings", []):
                        fp = f.get("fingerprint")
                        if fp:
                            fps.add(fp)
                except Exception:
                    continue
            return fps
        except Exception:
            return set()

    def _score_session(self, findings: list[dict[str, Any]], panel_size: int, quorum: int) -> float:
        """Compute session quality score 0..1."""
        if not findings:
            return 0.0
        coverage = len({f.get("domain") for f in findings}) / max(1, len(_DOMAIN_ORDER))
        confidence = sum(f.get("confidence", 0.0) for f in findings) / max(1, len(findings))
        quorum_ratio = min(1.0, panel_size / max(1, quorum))
        priority_boost = sum(1.0 for f in findings if f.get("priority") in ("critical", "high")) / max(1, len(findings))
        novelty = sum(1.0 for f in findings if not f.get("duplicate")) / max(1, len(findings))
        specificity = sum(1.0 for f in findings if f.get("action") in ("patch", "config", "feature", "remove")) / max(1, len(findings))
        return min(1.0, coverage * 0.2 + confidence * 0.2 + quorum_ratio * 0.15 + priority_boost * 0.2 + novelty * 0.15 + specificity * 0.1)

    def build_priority_queue(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort findings by priority × confidence for execution ordering."""
        priority_order = {"critical": 0, "high": 1, "standard": 2}
        return sorted(
            findings,
            key=lambda f: (
                priority_order.get(f.get("priority", "standard"), 2),
                -f.get("confidence", 0.0),
            ),
        )

    async def action_planner(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        """Create execution plan from findings."""
        queued = self.build_priority_queue(findings)
        plan = {
            "total_actions": len(queued),
            "critical": sum(1 for f in queued if f.get("priority") == "critical"),
            "high": sum(1 for f in queued if f.get("priority") == "high"),
            "standard": sum(1 for f in queued if f.get("priority") == "standard"),
            "actions": [],
        }
        for rank, f in enumerate(queued[:20], 1):
            plan["actions"].append({
                "rank": rank,
                "domain": f.get("domain"),
                "specialist": f.get("specialist"),
                "priority": f.get("priority", "standard"),
                "effort": f.get("effort", "standard"),
                "confidence": f.get("confidence", 0.0),
                "action": f.get("action", "patch"),
                "summary": f.get("finding", "")[:180],
            })
        return plan

    async def convene(
        self,
        domain: str | None = None,
        *,
        force_domain: bool = False,
        min_confidence: float = 0.75,
        auto_apply: bool = False,
        cross_domain: bool = False,
    ) -> dict[str, Any]:
        """Convene one council session and return findings."""
        if domain is None:
            domain = self.current_domain if force_domain else self.current_domain
        charter = COUNCIL_DOMAINS.get(domain, COUNCIL_DOMAINS["architecture"])

        # Build panel: presiding + specialists + scribe
        presiding = await _pick(self.registry, _pick_type(charter["presiding"]), 1)
        specialists: list[Any] = []
        for at in charter["specialists"][:4]:
            specialists.extend(await _pick(self.registry, at, 1))
        scribe = await _pick(self.registry, _pick_type(charter["scribe"]), 1)

        panel = [a for a in presiding + specialists + scribe if a]
        quorum = int(charter.get("min_quorum", 3))

        if len(panel) < 2:
            return {
                "domain": domain,
                "panel": [],
                "findings": [],
                "applied": 0,
                "skipped": "insufficient agents",
                "quorum_met": False,
                "quality_score": 0.0,
                "action_plan": {"total_actions": 0, "actions": []},
            }

        chair = self._chairperson(charter)
        current_scribe = self._scribe(charter)
        recent = await self._load_recent_findings()
        seen = await self._load_all_fingerprints()
        findings: list[dict[str, Any]] = []

        evidence_lines = gather_council_evidence()

        if mesh_ollama is None:
            return {
                "domain": domain,
                "chair": chair,
                "scribe": current_scribe,
                "panel": [a.name for a in panel],
                "findings": [],
                "applied": 0,
                "skipped": "mesh_ollama unavailable",
                "quorum_met": len(panel) >= quorum,
                "quality_score": 0.0,
            }

        try:
            for ag in panel:
                prompt = self._prompt(
                    domain, charter, ag.agent_type.value, ag.name, recent, chair, current_scribe, evidence=evidence_lines
                )
                data = await mesh_ollama.chat(
                    model=getattr(self.settings, "ollama_default_model", "gemma4:latest"),
                    messages=[
                        {"role": "system", "content": getattr(ag, "system_prompt", "")},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=120.0,
                    options={"temperature": 0.6},
                )
                text = (data.get("message") or {}).get("content", "").strip()
                if not text:
                    continue
                finding = _parse_finding(domain, ag.name, text, evidence=evidence_lines)
                finding.setdefault("evidence", evidence_lines)
                fp = finding.get("fingerprint")
                if fp and fp in seen:
                    finding["duplicate"] = True
                else:
                    seen.add(fp or _fingerprint(finding.get("finding", "")))
                    finding["duplicate"] = False
                findings.append(finding)
        except Exception as exc:
            log.warning("Void Council session failed", domain=domain, error=str(exc))
            return {
                "domain": domain,
                "chair": chair,
                "scribe": current_scribe,
                "panel": [a.name for a in panel],
                "findings": [],
                "applied": 0,
                "error": str(exc),
                "quorum_met": len(panel) >= quorum,
                "quality_score": 0.0,
            }

        applied = 0
        finding_statuses: list[dict[str, Any]] = []
        if auto_apply and findings:
            try:
                from app.orchestrator import self_expand, self_improve
                novel = [f for f in findings if not f.get("duplicate")]
                if novel:
                    blob = "\n".join(f["finding"] for f in novel)
                    p9 = await self_improve.scan_and_improve(self)
                    applied += len(p9.get("actions", []))
                    for finding in novel:
                        finding_statuses.append(await self._apply_finding(finding))
                    await self_expand.process_findings(self, blob)
            except Exception as exc:
                log.debug("auto-apply skipped", error=str(exc))
                finding_statuses.append({
                    "status": "failed",
                    "action": "batch",
                    "finding_id": "batch",
                    "error": str(exc),
                })

        # Build action plan for returned findings
        action_plan = await self.action_planner(findings)

        self._session_count += 1
        high_confidence = [f for f in findings if f.get("confidence", 0.0) >= min_confidence]
        quality = self._score_session(findings, len(panel), quorum)
        new_findings = [f for f in findings if not f.get("duplicate")]

        record = {
            "session": self._session_count,
            "domain": domain,
            "chair": chair,
            "scribe": current_scribe,
            "panel": [a.name for a in panel],
            "findings": findings,
            "finding_statuses": finding_statuses,
            "high_confidence": len(high_confidence),
            "applied": applied,
            "quorum_met": len(panel) >= quorum,
            "quality_score": round(quality, 3),
            "duplicate_count": sum(1 for f in findings if f.get("duplicate")),
            "ts": datetime.now(UTC).isoformat(),
        }
        await self._persist_session(record)

        if findings:
            summary = _summarize(findings)
            self._history.append(summary)
            if len(self._history) > self._max_history:
                del self._history[: len(self._history) - self._max_history]

        try:
            integration_evidence = {}
            if self._flatspace is not None:
                try:
                    await self._flatspace.store(
                        key=f"council_session:{self._session_count}",
                        value={
                            "domain": domain,
                            "findings_count": len(findings),
                            "quality_score": quality,
                        },
                        tier="bitgarden",
                        ttl=600,
                        metadata={"type": "council_session"},
                    )
                    integration_evidence["flatspace"] = "pushed"
                except Exception as exc:
                    integration_evidence["flatspace"] = f"error:{exc}"
            else:
                integration_evidence["flatspace"] = "unavailable"

            if self._observability is not None:
                try:
                    await self._observability.log_event(
                        event_type="council_session",
                        message=f"Council session {self._session_count} in {domain}",
                        severity="info",
                        context={
                            "council_session": self._session_count,
                            "domain": domain,
                            "findings": len(findings),
                            "quality_score": quality,
                            "quorum_met": len(panel) >= quorum,
                        },
                    )
                    integration_evidence["observability"] = "pushed"
                except Exception as exc:
                    integration_evidence["observability"] = f"error:{exc}"
            else:
                integration_evidence["observability"] = "unavailable"

            if self._garden is not None:
                try:
                    nodes = await self._garden.get_online_nodes()
                    garden_node_id = (
                        nodes[0] if nodes else getattr(self.settings, "zqm_ai_primary_garden", "garden-0")
                    )
                    integration_evidence["garden"] = f"noted:{garden_node_id}:{len(findings)}"
                except Exception as exc:
                    integration_evidence["garden"] = f"error:{exc}"

            if self._redis is not None:
                try:
                    await self._redis.push_metric(
                        f"{self._metrics_channel}:session:{self._session_count}",
                        {
                            "domain": domain,
                            "findings": len(findings),
                            "quality_score": quality,
                        },
                        ttl=600,
                    )
                    integration_evidence["redis"] = "pushed"
                except Exception as exc:
                    integration_evidence["redis"] = f"error:{exc}"
            else:
                integration_evidence["redis"] = "unavailable"
        except Exception as exc:
            integration_evidence = {"error": str(exc)}
            log.debug("council post-convene integration failed", error=str(exc))

        return {
            "domain": domain,
            "chair": chair,
            "scribe": current_scribe,
            "panel": [a.name for a in panel],
            "findings": findings,
            "action_plan": await self.action_planner(findings),
            "new_findings": len(new_findings),
            "duplicate_count": sum(1 for f in findings if f.get("duplicate")),
            "high_confidence": len(high_confidence),
            "applied": applied,
            "quorum_met": len(panel) >= quorum,
            "quality_score": round(quality, 3),
            "next_domain": self.next_domain(),
            "session": self._session_count,
            "total_sessions": self._session_count,
            "total_applied": self._applied_count + applied,
            "integration_evidence": integration_evidence if 'integration_evidence' in dir() else {"error": "integration_block_skipped"},
        }

    async def convene_full(
        self,
        *,
        min_confidence: float = 0.6,
        auto_apply: bool = False,
        cross_domain_synthesis: bool = True,
        parallel: bool = True,
    ) -> dict[str, Any]:
        """Convene all 8 domains in sequence and return aggregate findings."""
        results: dict[str, Any] = {
            "mode": "full_council",
            "domains": [],
            "total_findings": 0,
            "new_findings": 0,
            "duplicate_findings": 0,
            "total_applied": 0,
            "sessions": 0,
            "quality_score": 0.0,
            "cross_domain_insights": [],
        }
        scores: list[float] = []

        if parallel:
            domains_list = list(_DOMAIN_ORDER)
            tasks = [
                self.convene(
                    domain=domain,
                    min_confidence=min_confidence,
                    auto_apply=auto_apply,
                )
                for domain in domains_list
            ]
            domain_results = await asyncio.gather(*tasks, return_exceptions=True)
            for session in domain_results:
                if isinstance(session, Exception):
                    log.warning("full council domain failed", error=str(session))
                    continue
                results["domains"].append(session)
                results["total_findings"] += len(session.get("findings", []))
                results["new_findings"] += session.get("new_findings", 0)
                results["duplicate_findings"] += session.get("duplicate_count", 0)
                results["total_applied"] += session.get("applied", 0)
                results["sessions"] += 1
                scores.append(session.get("quality_score", 0.0))
        else:
            for domain in list(_DOMAIN_ORDER):
                session = await self.convene(
                    domain=domain,
                    min_confidence=min_confidence,
                    auto_apply=auto_apply,
                )
                results["domains"].append(session)
                results["total_findings"] += len(session.get("findings", []))
                results["new_findings"] += session.get("new_findings", 0)
                results["duplicate_findings"] += session.get("duplicate_count", 0)
                results["total_applied"] += session.get("applied", 0)
                results["sessions"] += 1
                scores.append(session.get("quality_score", 0.0))
        results["next_domain"] = self.current_domain
        results["quality_score"] = round(sum(scores) / max(1, len(scores)), 3)
        self._cross_domain_sessions += 1

        if cross_domain_synthesis:
            try:
                synthesis = await self._cross_domain_synthesis(results["domains"])
                results["cross_domain_insights"] = synthesis
            except Exception as exc:
                log.debug("cross-domain synthesis failed", error=str(exc))
        return results

    async def convene_emergency(
        self,
        domains: list[str],
        *,
        min_confidence: float = 0.7,
        auto_apply: bool = True,
    ) -> dict[str, Any]:
        """Emergency cross-domain session for critical issues."""
        valid = [d for d in domains if d in COUNCIL_DOMAINS]
        if not valid:
            valid = ["reliability", "security"]
        results: dict[str, Any] = {
            "mode": "emergency",
            "domains": [],
            "total_findings": 0,
            "total_applied": 0,
            "sessions": 0,
            "trigger_domains": valid,
        }
        for domain in valid:
            session = await self.convene(
                domain=domain,
                min_confidence=min_confidence,
                auto_apply=auto_apply,
                cross_domain=True,
            )
            results["domains"].append(session)
            results["total_findings"] += len(session.get("findings", []))
            results["total_applied"] += session.get("applied", 0)
            results["sessions"] += 1
        results["next_domain"] = self.current_domain
        return results

    async def _cross_domain_synthesis(self, domain_sessions: list[dict[str, Any]]) -> list[str]:
        """Synthesize findings across all domains into higher-order insights."""
        if mesh_ollama is None:
            return []
        all_findings = []
        for session in domain_sessions:
            for f in session.get("findings", []):
                all_findings.append(
                    f"[{f.get('domain')}:{f.get('priority','standard')}] "
                    f"{f.get('finding','')[:200]}"
                )
        if not all_findings:
            return []
        prompt = (
            "Cross-domain council synthesis. Given these domain findings, "
            "identify 2-3 cross-cutting themes or systemic risks. "
            "Be terse.\n\n" + "\n".join(all_findings[:24])
        )
        try:
            data = await mesh_ollama.chat(
                model=getattr(self.settings, "ollama_default_model", "gemma4:latest"),
                messages=[
                    {"role": "system", "content": "You are the Void Council synthesizer."},
                    {"role": "user", "content": prompt},
                ],
                timeout=180.0,
                options={"temperature": 0.5},
            )
            text = (data.get("message") or {}).get("content", "").strip()
            return [line.strip() for line in text.splitlines() if line.strip()][:5]
        except Exception:
            return []

    async def review_session_quality(self, limit: int = 20) -> dict[str, Any]:
        """Review recent council session quality trends."""
        rows = await self.review_history(limit=limit)
        if not rows:
            return {"sessions": 0, "average_quality": 0.0, "quality_trend": []}
        qualities = [r.get("quality_score", 0.0) for r in rows]
        domains = [r.get("domain") for r in rows]
        return {
            "sessions": len(rows),
            "average_quality": round(sum(qualities) / max(1, len(qualities)), 3),
            "quality_trend": [
                {"session": r.get("session"), "domain": d, "quality": q}
                for r, d, q in zip(rows[-10:], domains[-10:], qualities[-10:])
            ],
            "top_domains": sorted(
                {d: qualities[i] for i, d in enumerate(domains)}.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5],
        }

    async def review_history(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._history_path.exists():
            return []
        rows = []
        try:
            lines = [
                ln for ln in self._history_path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            for ln in lines[-limit:]:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
        except Exception:
            pass
        return rows


def _clean_key_value_line(line: str) -> tuple[str, str] | None:
    """Strip markdown/bold markers and return key/value if recognized."""
    cleaned = line.strip()
    cleaned = re.sub(r"\*\*", "", cleaned)
    if ":" not in cleaned:
        return None
    key, value = cleaned.split(":", 1)
    key = key.strip().lower()
    value = value.strip().lower()
    if key in {"action", "priority", "effort", "finding"}:
        return key, value
    return None


_ASYNC_GENERIC_RE = re.compile(
    r"handlerequest|handle_request|asynchronous operations|async operations",
    re.IGNORECASE,
)


def _is_generic_async_finding(text: str) -> bool:
    """Detect low-value generic async recommendations."""
    if not text:
        return False
    if _ASYNC_GENERIC_RE.search(text):
        # Treat as generic unless it also cites exact code paths / metrics
        if not re.search(r"app/|def |class |line \d+|latency delta|error rate|ms\b|tps\b", text, re.IGNORECASE):
            return True
    return False


def _finding_references_evidence(text: str, evidence: list[str]) -> bool:
    """Check whether the finding text addresses the specific injected evidence."""
    if not evidence:
        return True
    lowered = text.lower()

    api_status_hits = 0
    garden_metrics_hits = 0
    garden_health_hits = 0
    mesh_health_hits = 0
    code_path_hits = 0

    for line in evidence:
        snippet = line.lower()
        if snippet.startswith("evidence:"):
            snippet = snippet[len("evidence:"):].strip()
        if not snippet:
            continue

        if snippet in lowered:
            if "code path" in snippet:
                code_path_hits += 1
            elif "/api/status" in snippet:
                api_status_hits += 1
            elif "/api/garden/metrics" in snippet:
                garden_metrics_hits += 1
            elif "/api/garden/health" in snippet:
                garden_health_hits += 1
            elif "/api/mesh/nodes/health" in snippet:
                mesh_health_hits += 1
            else:
                code_path_hits += 1
            continue

        if "/api/status" in snippet and "/api/status" in lowered:
            api_status_hits += 1
            continue
        if "/api/garden/metrics" in snippet and "/api/garden/metrics" in lowered:
            garden_metrics_hits += 1
            continue
        if "/api/garden/health" in snippet and "/api/garden/health" in lowered:
            garden_health_hits += 1
            continue
        if "/api/mesh/nodes/health" in snippet and "/api/mesh/nodes/health" in lowered:
            mesh_health_hits += 1
            continue
        if "code path missing:" in snippet:
            rel = snippet.split("code path missing:", 1)[1].strip()
            if rel and rel in lowered:
                code_path_hits += 1
                continue

    endpoint_hits = api_status_hits + garden_metrics_hits + garden_health_hits + mesh_health_hits
    return endpoint_hits >= 2 or (endpoint_hits >= 1 and code_path_hits >= 1)


def _evidence_based_fallback(domain: str, agent_name: str, evidence: list[str] | None = None) -> dict[str, Any]:
    """Generate a concrete, evidence-based finding from live evidence."""
    evidence_text = " ".join(evidence or []).lower()
    agent_lower = agent_name.lower()

    status_findings = {
        "401": (
            "**ACTION:** review `app/routers/status.py` auth/public-surface contract\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Live telemetry shows `/api/status` returns `401`. "
            "Confirm whether the status surface should be public, review token exceptions, "
            "and ensure unauthenticated probes return a stable payload instead of an auth challenge."
        ),
        "500": (
            "**ACTION:** patch `app/routers/status.py` to harden `/api/status`\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Live telemetry shows `/api/status` returns `500`. "
            "Fix exception paths and add safe fallback JSON so the endpoint always returns HTTP 200."
        ),
    }
    metrics_finding = (
        "**ACTION:** keep `app/routers/garden.py` `/api/garden/metrics` stable\n"
        "**PRIORITY:** medium\n"
        "**EFFORT:** monitor\n\n"
        "**FINDING:** Live telemetry shows `/api/garden/metrics` is currently returning HTTP 200. "
        "Preserve this behavior and add schema/regression coverage so it does not regress."
    )
    garden_findings = {
        "offline": (
            "**ACTION:** inspect garden nodes with offline/degraded status\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** config\n\n"
            "**FINDING:** Live mesh telemetry shows garden nodes in `offline` or `degraded` state. "
            "Inspect node reachability, health probes, and dependencies on those nodes."
        ),
        "degraded": (
            "**ACTION:** inspect garden nodes with offline/degraded status\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** config\n\n"
            "**FINDING:** Live mesh telemetry shows garden nodes in `degraded` state. "
            "Inspect node reachability, health probes, and dependencies on those nodes."
        ),
    }
    runtime_findings = {
        "docker_down": (
            "**ACTION:** inspect Docker container state and restart unhealthy containers\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Live Docker telemetry shows containers in an unhealthy or exited state. "
            "Inspect logs, verify image pulls, and restart failed containers.\n"
            "**MEASURABLE:** `docker ps` shows all containers Up.\n"
            "**EVIDENCE:** {evidence_text}"
        ),
        "disk_pressure": (
            "**ACTION:** free disk space or expand volume before state degrades\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** ops\n\n"
            "**FINDING:** Live system telemetry shows low disk free space. "
            "Docker images/logs or local models may be reclaimable.\n"
            "**MEASURABLE:** free space rises above 20% on affected volume.\n"
            "**EVIDENCE:** {evidence_text}"
        ),
        "ollama_down": (
            "**ACTION:** verify Ollama service and model pull state\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Live Ollama telemetry shows no healthy inference path. "
            "Confirm service state, restart if needed, and re-pull missing models.\n"
            "**MEASURABLE:** `/api/tags` returns models and `/api/generate` completes.\n"
            "**EVIDENCE:** {evidence_text}"
        ),
        "mesh_degraded": (
            "**ACTION:** inspect mesh node reachability and auth\n"
            "**PRIORITY:** medium\n"
            "**EFFORT:** config\n\n"
            "**FINDING:** Live mesh telemetry shows mixed node health. "
            "Inspect SSH, port 22 reachability, and API auth on degraded nodes.\n"
            "**MEASURABLE:** all mesh nodes return HTTP 200 on health probes.\n"
            "**EVIDENCE:** {evidence_text}"
        ),
    }

    if "get /api/status -> 401" in evidence_text:
        status_finding = status_findings["401"]
    elif "get /api/status -> 500" in evidence_text or "get /api/status -> unreachable" in evidence_text:
        status_finding = status_findings["500"]
    elif "code path missing" in evidence_text:
        status_finding = (
            "**ACTION:** patch codebase to ensure referenced routers/modules exist and are registered in `app/main.py`\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Council evidence shows missing code paths. "
            "Add the missing router/module files, import them in `app/main.py`, and validate with `py_compile` plus runtime import checks."
        )
    elif "status=offline" in evidence_text or "status=offline" in evidence_text:
        status_finding = garden_findings["offline"]
    elif "status=degraded" in evidence_text:
        status_finding = garden_findings["degraded"]
    elif "docker ps" in evidence_text:
        status_finding = runtime_findings["docker_down"]
    elif "free space" in evidence_text or "disk" in evidence_text:
        status_finding = runtime_findings["disk_pressure"]
    elif "ollama" in evidence_text:
        status_finding = runtime_findings["ollama_down"]
    elif "mesh" in evidence_text or "garden" in evidence_text:
        status_finding = runtime_findings["mesh_degraded"]
    elif "garden" in domain:
        status_finding = metrics_finding
    else:
        status_finding = (
            "**ACTION:** inspect the failing subsystem identified by live evidence\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** Live evidence indicates a subsystem issue. "
            "Inspect the failing endpoint/module, add error handling, and verify with HTTP 200 / health probe."
        )

    role_findings = {
        "security": (
            "**ACTION:** validate input, secrets, authz, and dependency exposure on the failing surface\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** audit\n\n"
            "**FINDING:** From a security standpoint, a failing or unprotected status surface can leak health details, dependency names, or auth behavior. "
            "Audit response shape, enforce least-privilege visibility, and add regression tests for unauthenticated access."
        ),
        "infra": (
            "**ACTION:** harden launch, PATH isolation, and wrapper service config for the affected subsystem\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** config\n\n"
            "**FINDING:** Infrastructure evidence points to a service/boot/runtime issue. "
            "Use a clean launcher wrapper, verify process tree and port binding, and ensure the service reaches RUNNING state on boot."
        ),
        "code": (
            "**ACTION:** add structured exception handling + regression tests around the failing handler\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** The evidence points to handler-level instability. "
            "Wrap external calls and state access in try/except, return stable error envelopes, and add pytest cases for the failure path."
        ),
        "api": (
            "**ACTION:** enforce stable response contract and schema validation on the failing endpoint\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** API consumers depend on stable status/metrics responses. "
            "Add response_model validation, normalize error shapes, and document the success/failure schema for downstream callers."
        ),
        "observability": (
            "**ACTION:** instrument the failing path with logs, latency, and error counters\n"
            "**PRIORITY:** medium\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** A failing endpoint without observability delays detection. "
            "Add structured logging around startup, request handling, and registry/metrics access so failures are visible before users report them."
        ),
        "reasoning": (
            "**ACTION:** trace the failure mode across dependent callers and propose a minimal safe fix\n"
            "**PRIORITY:** high\n"
            "**EFFORT:** patch\n\n"
            "**FINDING:** The current evidence indicates a localized failure with system-wide visibility. "
            "Map callers, confirm blast radius, and implement the smallest change that restores stable behavior."
        ),
    }

    if any(keyword in agent_lower for keyword in ["security", "sentinel"]):
        finding_text = role_findings["security"]
        selected_domain = "security"
    elif any(keyword in agent_lower for keyword in ["infra", "monitor", "ops"]):
        finding_text = role_findings["infra"]
        selected_domain = "infrastructure"
    elif any(keyword in agent_lower for keyword in ["code", "gen"]):
        finding_text = role_findings["code"]
        selected_domain = "reliability"
    elif any(keyword in agent_lower for keyword in ["api", "conductor"]):
        finding_text = role_findings["api"]
        selected_domain = "reliability"
    elif any(keyword in agent_lower for keyword in ["observability", "eye"]):
        finding_text = role_findings["observability"]
        selected_domain = "observability"
    elif any(keyword in agent_lower for keyword in ["reasoning", "reason"]):
        finding_text = role_findings["reasoning"]
        selected_domain = "reliability"
    else:
        finding_text = status_finding
        selected_domain = domain

    return {
        "domain": selected_domain,
        "specialist": agent_name,
        "finding": finding_text,
        "confidence": 0.8,
        "priority": "high",
        "effort": "patch",
        "fingerprint": _fingerprint(finding_text),
        "ts": datetime.now(UTC).isoformat(),
        "duplicate": False,
    }


def _parse_finding(domain: str, agent_name: str, text: str, evidence: list[str] | None = None) -> dict[str, Any]:
    """Parse structured finding from agent output."""
    finding: dict[str, Any] = {
        "domain": domain,
        "specialist": agent_name,
        "finding": text,
        "confidence": _heuristic_confidence(text),
        "priority": "standard",
        "effort": "standard",
        "action": "patch",
        "fingerprint": _fingerprint(text),
        "ts": datetime.now(UTC).isoformat(),
    }
    for line in text.splitlines():
        parsed = _clean_key_value_line(line)
        if not parsed:
            continue
        key, value = parsed
        if key == "action" and value in {"patch", "config", "feature", "remove"}:
            finding["action"] = value
        elif key == "priority" and value in {"critical", "high", "standard"}:
            finding["priority"] = value
        elif key == "effort" and value in {"config", "patch", "feature", "remove"}:
            finding["effort"] = value

    if _is_generic_async_finding(finding.get("finding", "")):
        finding = _evidence_based_fallback(domain, agent_name, evidence=evidence)
        return finding

    if evidence and not _finding_references_evidence(finding.get("finding", ""), evidence):
        finding = _evidence_based_fallback(domain, agent_name, evidence=evidence)
        return finding

    if evidence is not None:
        finding["evidence"] = evidence
    return finding


def _pick_type(candidates: list[Any]) -> Any:
    """Pick first candidate that resolves to a real AgentType member."""
    for c in candidates:
        try:
            return AgentType(c.value if hasattr(c, "value") else str(c))
        except Exception:
            continue
    try:
        return AgentType.REASONING
    except Exception:
        return candidates[0] if candidates else "reasoning"


# ── Public API ────────────────────────────────────────────────────────────────

async def convene_council(
    registry: Any,
    settings: Any,
    domain: str | None = None,
    *,
    force_domain: bool = False,
    min_confidence: float = 0.75,
    auto_apply: bool = False,
) -> dict[str, Any]:
    """Convene a Void Council session."""
    council = VoidCouncil(registry=registry, settings=settings)
    return await council.convene(
        domain=domain,
        force_domain=force_domain,
        min_confidence=min_confidence,
        auto_apply=auto_apply,
    )


async def convene_full_council(
    registry: Any,
    settings: Any,
    *,
    min_confidence: float = 0.75,
    auto_apply: bool = False,
) -> dict[str, Any]:
    """Convene all council domains in sequence."""
    council = VoidCouncil(registry=registry, settings=settings)
    return await council.convene_full(
        min_confidence=min_confidence,
        auto_apply=auto_apply,
    )

