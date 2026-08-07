# Council Evidence Report

Generated: 2026-08-06T19:28:18.628848+00:00
Mode: live-telemetry-backed findings
Findings: 3
Value score: 1.000

## Summary

3/3 findings are high or critical. Top opportunities are ordered by priority and confidence below.

## Findings

### 1. [reliability] evidence-probe
- **Action:** patch
- **Priority:** critical
- **Effort:** patch
- **Confidence:** 0.80
- **Measurable:** health endpoint HTTP 200

Local API health probe returned no result. Public health surface may be down or unreachable from the probe path.

### 2. [infrastructure] evidence-probe
- **Action:** patch
- **Priority:** high
- **Effort:** patch
- **Confidence:** 0.80
- **Measurable:** garden health HTTP 200

`/api/garden/health` returned no result. Garden service or its node probes may be failing.

### 3. [infrastructure] evidence-probe
- **Action:** patch
- **Priority:** high
- **Effort:** patch
- **Confidence:** 0.80
- **Measurable:** mesh health HTTP 200

`/api/mesh/nodes/health` returned no result. Mesh telemetry endpoint may be unreachable or unauthenticated.
