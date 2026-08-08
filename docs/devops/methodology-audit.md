# ZQM-AI-Master — Methodology Audit

Date: 2026-08-05
Runtime: N4 (192.168.1.228:8808) API version 2.1.4
Status: Verified live; no code changes made during audit

---

## 1. Falsification protocol / 8-challenge audit

Source:
- `app/services/falsification_protocol.py` — `FalsificationProtocol.full_audit()`
- Attached to every completed task as `task.falsification_report`

Method:
- C1 hardware drift: `state_hash_with_projection()` hashes tensor state with symbolic projection to avoid cross-platform float-drift false positives.
- C2 KV-cache eviction: `boundary_hash()` hashes cache tail + cumulative error; `detect_eviction_spike()` scans `error_curve` for nonlinear error compounding.
- C3 manifest integrity: `verify_manifest()` compares current manifest hash against `manifest_baseline`.
- C4 working-memory boundary: `envelope_hash(envelope, wm)` vs `envelope_hash(envelope, [])`; `detect_semantic_drift()` measures boundary leakage.
- C5 normalization entropy: `normalize_and_hash()` strips volatile keys and verifies entropy preservation ≥ 0.8 × raw entropy.
- C6 constraint seeds: `constraint_hash(seed, constraints, mutation)` detects injected constraint mutations by hash delta.
- C7 world-state fingerprint: `_world_fingerprint()` + `_classify_world_change()` with staleness threshold and blocked-key prefixes (`auth`, `secret`, `password`, `key`, `credential`, `token`).
- C8 external consistency: `_verify_external_consistency()` checks `last_observation`, `last_action`, `action_world_delta` for delta completeness, temporal ordering, and state match.

Live evidence:
- `/api/flatspace/search` returns completed tasks with embedded `falsification_report` objects.
- Observed today: `all_passed: False` primarily due to C8 `severity: critical` (`delta_complete: False`) and intermittent C4 semantic drift.
- Self-test inside `full_audit()` injects known working-memory drift and verifies hash change; drift detection logic is exercised on every audit.

Assessment:
- Protocol is implemented end-to-end and attached to real task results.
- C8 external consistency is the dominant failure mode in current runs; this is a runtime-world-model gap, not a code bug.
- C1-C3, C5-C7 routinely pass; C4 occasionally flags drift.

---

## 2. Service-health / observability methodology

Source:
- `app/orchestrator/zqm_ai_orchestrator.py` — `get_health()`
- `app/services/observability_service.py` — `ObservabilityService`

Method:
- Core health = local datastore + agent pool + memory + autonomy.
- External services (`garden`, `flatspace`, `observability`) checked concurrently via `asyncio.wait_for(asyncio.gather(...), timeout=6.0)`.
- External failures do not degrade core status; they are reported under `external_services`.
- Process metrics: `psutil.Process(os.getpid()).memory_info().rss` and `psutil.cpu_percent(interval=None)`.
- Observability service pushes task metrics asynchronously to `http://192.168.1.225:9090/api/metrics` when enabled; Prometheus counters exposed locally if `prometheus_client` is installed.
- Fail-soft: health-check and push errors are logged and skipped; they never crash the orchestrator.

Live evidence:
- `/api/status` returns `200`, `status: healthy`, `database: healthy`, `flatspace: healthy`, `garden: healthy`, `observability: healthy`.
- `/api/observability/health` returns `200`, `prometheus_client: true`, endpoint `http://127.0.0.1:8808/api/observability/metrics`, `enabled: false`.
- `/api/dashboard` returns `22` idle agents.

Assessment:
- Health methodology is sound: core vs external separation prevents false degradation alerts.
- Observability push is disabled in current config; metrics are local-only.
- No code defect found in health path.

---

## 3. Task-execution / routing methodology

Source:
- `app/orchestrator/zqm_ai_orchestrator.py` — `execute_task()`
- `app/orchestrator/task_router.py` — `route_with_audit()`
- `app/orchestrator/cognitive_processor.py` — `process()`

Method:
1. Route task with audit metadata (`cognitive_level`, `priority`, `input_method`, reason).
2. Create `Task` record and insert into `_active_tasks`.
3. Select agents via `registry.select_for_task()` with routing context.
4. Execute with timeout circuit: 70 % model/tool budget, 30 % cleanup reserve; `asyncio.shield()` + `asyncio.wait_for()`.
5. On timeout: mark all selected agents idle/failed so hung work does not leak.
6. Attach routing metadata to `cognitive_trace`.
7. Compute optional calibration offset from `confidence` and `outcome_verified`.
8. Run falsification protocol audit on task state; attach report to task.
9. Surface agent tool/integration actions in `result.metadata["agent_actions"]`.
10. Async post-execution: persist to FLATSPACE + push observability metrics via `_post_execution()`.

Live evidence:
- `/api/flatspace/search` returned completed advanced and basic tasks with full `cognitive_trace`, `routing`, `falsification_report`, token/cost fields.
- `/api/process` BASIC tier returned `output`, `model_used`, `provider_used`, `total_tokens`, `cost_usd`, `duration_ms`, `reasoning_step_count`, `reasoning_step_density`.
- `/api/garden/metrics` returned `200` with agent/node data.

Assessment:
- Pipeline is complete and verified live.
- Timeout circuit + falsification audit + async persistence is the correct ordering; audit captures state before async side effects.
- No code defect found in execution path.

---

## 4. FLATSPACE memory-search methodology

Source:
- `app/services/flatspace_service.py` — `search()`, `store()`, `retrieve()`
- `app/routers/flatspace.py` — `/api/flatspace/search`
- `app/services/flatspace_local.py` — `LocalFlatSpaceStore`

Method:
- Remote-first: POST to `{base}/search` with `{"query", "tier", "limit"}` and `X-ZQM_AI-ID` header.
- Remote failure fallback: local SQLite `flatspace_local.db` with optional embedding-assisted search.
- Store/retrieve/batch/delete all follow the same remote-first, local-fallback pattern.
- `FLATSPACE_MODE=auto` prefers remote; if remote unreachable and local DB missing, ingestion silently fails.
- Local store mirrors remote method surface so callers need no changes.

Live evidence:
- `/api/flatspace/search` with Bearer auth and correct JSON body returned `200`, `count: 5`, all rows `local: True`.
- Results include full task payloads, `score`, `created`, and `falsification_report` for completed tasks.
- `/api/process` BASIC response includes full fields; earlier 401/422 were auth/schema probe errors, not service bugs.

Assessment:
- Search path is functional; remote backend appears unreachable, local SQLite is the active store.
- Important operational note: `FLATSPACE_MODE=auto` plus missing local DB = silent ingestion failure. Always verify `app/flatspace_local.db` exists before relying on fallback.

---

## 5. Self-improvement / self-critique methodology

Source:
- `app/orchestrator/zqm_ai_orchestrator.py` — `_self_improvement_loop()`, `_self_critique()`
- `app/main.py` — `/api/self-improve/run`, `/api/self-expand/apply`

Method:
- Background loop runs on `ZQM_SELF_IMPROVE_INTERVAL_S` (default 600 s).
- Rotates specialist panel: CODE, SECURITY, INFRASTRUCTURE, GARDEN, LEARNING, HYDROLOGY.
- Each cycle convenes REASONING + current specialist + SYNTHESIS via live Ollama calls through `mesh_ollama.chat()`.
- Prompt is grounded in last 8 task history entries; panel members output one concrete, code-level upgrade proposal.
- Findings persisted to FLATSPACE `bitgarden` tier; JSONL fallback at `app/self_improvement_log.jsonl` if remote is unreachable.
- `/api/self-improve/run` triggers one manual cycle; `/api/self-expand/apply` applies pending expansions.

Live evidence:
- `/api/self-improve/run` returned `200`, `proposed: 5`.
- `/api/self-expand/apply` returned `200`, `applied: 0`.
- Self-improvement loop started at service boot with `interval_s=600`.

Assessment:
- Loop is fail-soft; a single cycle failure does not crash the orchestrator.
- Mesh Ollama router provides graceful degradation if local Ollama is unavailable.
- Expansion path exists but was a no-op in current run; no pending expansions were applied.

---

## Cross-methodology summary

| Methodology | Status | Known gap |
|---|---|---|
| Falsification / 8-challenge audit | Implemented, live on every task | C8 external consistency frequently critical due to missing world-model delta |
| Service-health / observability | Healthy, core/external separation sound | Observability push disabled; metrics local-only |
| Task execution / routing | Verified end-to-end | None found |
| FLATSPACE memory search | Functional, local fallback active | Remote backend unreachable; verify local DB exists |
| Self-improvement / self-critique | Running, fail-soft | No pending expansions; mesh Ollama fallback untested under failure |

---

## Methodology selection guide

- Use falsification audit when you need per-task integrity proof.
- Use service-health when you need operational status without false alarms from external deps.
- Use task-execution pipeline when you need routed, timed, audited agent work.
- Use FLATSPACE search when you need durable memory recall across restarts.
- Use self-improvement loop when you want autonomous architectural critique grounded in live task history.
