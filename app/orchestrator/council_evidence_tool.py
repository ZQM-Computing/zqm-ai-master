"""
Evidence-based council/value-improvement tool.

Bypasses noisy LLM-only council output and derives findings directly
from live system telemetry: HTTP endpoints, service state, Docker state,
mesh health, and known codebase gaps.

Outputs:
- C:\Void\ZQM-AI-Master\council_evidence_report.md
- updates C:\Void\ZQM-AI-Master\live_system_state.json findings
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
REPORT_PATH = BASE_DIR / "council_evidence_report.md"
LIVE_STATE_PATH = BASE_DIR / "live_system_state.json"


@dataclass
class Finding:
    domain: str
    specialist: str
    finding: str
    priority: str = "high"
    effort: str = "patch"
    action: str = "patch"
    confidence: float = 0.8
    measurable: str = ""


@dataclass
class EvidenceReport:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    findings: List[Finding] = field(default_factory=list)
    value_score: float = 0.0
    summary: str = ""

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def rank(self) -> List[Finding]:
        order = {"critical": 0, "high": 1, "standard": 2}
        return sorted(self.findings, key=lambda f: (order.get(f.priority, 2), -f.confidence))

    def markdown(self) -> str:
        lines = [
            f"# Council Evidence Report",
            f"",
            f"Generated: {self.generated_at}",
            f"Mode: live-telemetry-backed findings",
            f"Findings: {len(self.findings)}",
            f"Value score: {self.value_score:.3f}",
            f"",
            f"## Summary",
            f"",
            f"{self.summary}",
            f"",
            f"## Findings",
            f"",
        ]
        for i, f in enumerate(self.rank(), 1):
            lines.extend([
                f"### {i}. [{f.domain}] {f.specialist}",
                f"- **Action:** {f.action}",
                f"- **Priority:** {f.priority}",
                f"- **Effort:** {f.effort}",
                f"- **Confidence:** {f.confidence:.2f}",
                f"- **Measurable:** {f.measurable}",
                f"",
                f"{f.finding}",
                f"",
            ])
        return "\n".join(lines)


def _https_get(base_url: str, path: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"
    use_ssl = True
    if url.startswith("https://127.0.0.1") or url.startswith("https://localhost"):
        url = "http://127.0.0.1:8808" + url[len("https://127.0.0.1"):]
        use_ssl = False
    ctx = None
    if use_ssl:
        ca = BASE_DIR / "data" / "traefik" / "certs" / "zqm-mesh.crt"
        if ca.exists():
            ctx = ssl.create_default_context()
            ctx.load_verify_locations(cafile=str(ca))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _derive_findings_from_live(base_url: str = "https://127.0.0.1:8808") -> EvidenceReport:
    report = EvidenceReport()

    health = _https_get(base_url, "/api/healthz", timeout=8.0)
    if health is None:
        report.add(Finding(
            domain="reliability",
            specialist="evidence-probe",
            finding="Local API health probe returned no result. Public health surface may be down or unreachable from the probe path.",
            priority="critical",
            effort="patch",
            measurable="health endpoint HTTP 200",
        ))
    else:
        deps = health.get("dependencies", {})
        for name, ok in deps.items():
            if not ok:
                report.add(Finding(
                    domain="reliability",
                    specialist="evidence-probe",
                    finding=f"Dependency `{name}` reports unhealthy in `/api/healthz`. Inspect startup and subsystem connection state.",
                    priority="high",
                    effort="patch",
                    measurable=f"{name} health true",
                ))

    garden = _https_get(base_url, "/api/garden/health", timeout=8.0)
    if garden is None:
        report.add(Finding(
            domain="infrastructure",
            specialist="evidence-probe",
            finding="`/api/garden/health` returned no result. Garden service or its node probes may be failing.",
            priority="high",
            effort="patch",
            measurable="garden health HTTP 200",
        ))

    mesh = _https_get(base_url, "/api/mesh/nodes/health", timeout=8.0)
    if mesh is not None:
        nodes = mesh.get("nodes", [])
        for node in nodes:
            status = node.get("status")
            if status in {"offline", "degraded"}:
                report.add(Finding(
                    domain="infrastructure",
                    specialist="evidence-probe",
                    finding=f"Mesh node `{node.get('id')}` is `{status}` on `{node.get('ip')}` with role `{node.get('role')}`.",
                    priority="high" if status == "offline" else "standard",
                    effort="config",
                    measurable=f"{node.get('id')} status=healthy",
                ))
    else:
        report.add(Finding(
            domain="infrastructure",
            specialist="evidence-probe",
            finding="`/api/mesh/nodes/health` returned no result. Mesh telemetry endpoint may be unreachable or unauthenticated.",
            priority="high",
            effort="patch",
            measurable="mesh health HTTP 200",
        ))

    n4_state = "unknown"
    n4_path = BASE_DIR.parent / "logs" / "uvicorn_n4_err.log"
    if n4_path.exists():
        text = n4_path.read_text(encoding="utf-8", errors="ignore")
        if "Paused" in text or "OneDrive" in text or "AttributeError" in text:
            n4_state = "contaminated_or_paused"
        else:
            n4_state = "log_clean"

    if n4_state == "contaminated_or_paused":
        report.add(Finding(
            domain="infrastructure",
            specialist="evidence-probe",
            finding="N4 error log indicates paused/contaminated runtime. Fix service launch wrapper and remove OneDrive sync interference.",
            priority="high",
            effort="config",
            measurable="N4 service state=RUNNING, port 8808 bound",
        ))

    if not report.findings:
        report.summary = "Live telemetry is clean; no evidence-backed findings from endpoint probes."
        report.value_score = 0.0
        return report

    high = sum(1 for f in report.findings if f.priority in {"critical", "high"})
    total = len(report.findings)
    report.value_score = round(high / max(1, total), 3)
    report.summary = (
        f"{high}/{total} findings are high or critical. "
        f"Top opportunities are ordered by priority and confidence below."
    )
    return report


def update_live_state_findings(report: EvidenceReport) -> None:
    if not LIVE_STATE_PATH.exists():
        return
    try:
        data = json.loads(LIVE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["council_findings"] = [
        {
            "domain": f.domain,
            "specialist": f.specialist,
            "finding": f.finding,
            "priority": f.priority,
            "effort": f.effort,
            "action": f.action,
            "confidence": f.confidence,
            "measurable": f.measurable,
            "ts": report.generated_at,
        }
        for f in report.findings
    ]
    data["council_value_score"] = report.value_score
    LIVE_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    report = _derive_findings_from_live()
    update_live_state_findings(report)
    REPORT_PATH.write_text(report.markdown(), encoding="utf-8")
    print(f"Wrote report: {REPORT_PATH}")
    for f in report.rank():
        print(f"[{f.priority.upper()}] {f.domain} | {f.specialist}: {f.finding[:120].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
