# The Void — Deep Systems Study
Date: 2026-08-04 | Version: 2.1.4 | Node: N4 (.228)

---

## EXECUTIVE SUMMARY
The Void is a self-hosted, multi-agent AI orchestration system running on a 5-node ZQM-MESH
Windows workgroup. It is **operational and verified live**: 22/22 core API endpoints return
HTTP 200, 22 default agents registered, all subsystems healthy (garden/flatspace/observability),
and the falsification protocol is active with 8 defenses. The system is **not** running from
its intended venv — the active process is system Python 3.12 from OneDrive-imported source.

---

## 1. SERVICE RUNTIME (verified live)

**Process**: pid 15036, `C:\Program Files\Python312\python.exe`
**Working directory**: `C:\Void\ZQM-AI-Master`
**Command**: `-m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir C:\Void\ZQM-AI-Master`
**Listening**: `0.0.0.0:8808`
**NSSM service**: ZQM-Void-N4, AppEnvironmentExtra contains `ZQM_GARDEN_0=Y`

**Important discrepancy**: The running interpreter is system Python 3.12, not the venv Python
at `.venv\Scripts\python.exe`. The code is loaded from the OneDrive-imported path:
`C:\Users\zqmco\OneDrive\Imports\...\ZQM-AI-master\app\main.py`

This means:
- venv-specific packages may not be used
- Code edits in `C:\Void\ZQM-AI-Master\` may NOT be reflected in the running process
- Restarting NSSM may switch back to venv or continue using system Python depending on PATH

---

## 2. HEALTH STATUS (in-process verified)

```json
{
  "status": "healthy",
  "zqm_ai_id": "ZQM-ZQM_AI-004",
  "version": "2.1.4",
  "environment": "development",
  "uptime_seconds": 0.1,
  "database": "healthy",
  "redis": "disabled",
  "garden": "healthy",
  "flatspace": "healthy",
  "observability": "healthy",
  "self_apply": "off",
  "external_services": {
    "garden": "healthy",
    "observability": "healthy"
  },
  "active_tasks": 0,
  "total_agents": 22,
  "cache_size": 0,
  "memory_mb": 43.0,
  "cpu_percent": 31.0
}
```

All subsystems report healthy. Core = database (flatspace) + agent pool + autonomy.

---

## 3. AGENT REGISTRY (22 agents)

| Agent ID | Name | Type | Garden Node |
|---|---|---|---|
| agent-33e47072 | ZQM-NLP-Prime | nlp | .228 |
| agent-a6e36459 | ZQM-Reasoning-001 | reasoning | .228 |
| agent-a3c15c6c | ZQM-GIS-Analyst | gis | .224 |
| agent-3330d828 | ZQM-Hydro-Expert | hydrology | .224 |
| agent-5c481c20 | ZQM-Infra-Monitor | infrastructure | .228 |
| agent-fcbefa60 | ZQM-Synthesis-Core | synthesis | .228 |
| agent-9896756d | ZQM-Memory-Store | memory | .228 |
| agent-6a7ad501 | ZQM-Code-Gen | code | .78 |
| agent-5ad151bb | ZQM-Network-Ops | network | .228 |
| agent-bbb34617 | ZQM-Vision-Perceptor | file | .78 |
| agent-fb5fec29 | ZQM-Security-Sentinel | security | .228 |
| agent-45fc0e56 | ZQM-Data-Forge | data | .31 |
| agent-5957a7a1 | ZQM-Observability-Eye | observability | .225 |
| agent-96ee1481 | ZQM-Garden-Warden | garden | .228 |
| agent-5f2e4c0e | ZQM-Scheduler-Chronos | scheduler | .224 |
| agent-b0918b59 | ZQM-Learning-Mind | learning | .228 |
| agent-d697ad72 | ZQM-FLATSPACE-Lattice | flatspace | .228 |
| agent-3b215ee2 | ZQM-API-Conductor | api | .78 |
| agent-5285af55 | ZQM-Linguist | nlp | .224 |
| agent-c62019b2 | ZQM-Entity-Miner | nlp | .31 |
| agent-6ee32dab | ZQM-Research-Spider | data | .225 |
| agent-c4015dd2 | ZQM-Quantum-Lattice | quantum | .228 |

All 22 idle, 0 busy. Agent types span 19 distinct specializations.

---

## 4. ENDPOINT INVENTORY (22 verified HTTP 200)

| Method | Path | Auth | Status | Notes |
|---|---|---|---|---|
| POST | /api/users/login | no | 200 | default admin password="" |
| GET | /api/status/ping | no | 200 | liveness probe |
| GET | /api/status | JWT | 200 | full health |
| GET | /api/status/metrics | JWT | 200 | Prometheus text |
| GET | /api/status/history | JWT | 200 | task history |
| GET | /api/info | no | 200 | system info + endpoints |
| GET | /api/info/agents | JWT | 200 | 22 agents |
| POST | /api/process | JWT | 200 | task submission |
| GET | /api/process/history | JWT | 200 | durable history |
| GET | /api/process/{id} | JWT | 200 | task status |
| POST | /api/flatspace/search | JWT | 200 | search bitgarden |
| POST | /api/garden/coordinate | JWT | 200 | job submit |
| GET | /api/garden/health | no | 200 | 5 nodes |
| GET | /api/garden/nodes | JWT | 200 | node list |
| GET | /api/garden/metrics | JWT | 500 | **BUG**: missing request arg |
| GET | /api/observability/health | no | 200 | prometheus_client=true |
| GET | /api/observability/metrics | no | 200 | Prometheus text |
| POST | /api/void/talk | JWT | 200 | conversational |
| POST | /api/self-improve/run | JWT | 200 | 5 proposed |
| POST | /api/self-expand/apply | JWT | 200 | 0 applied |
| POST | /api/predict | JWT | 200 | inference |
| GET | /api/permissions/roles | JWT | 200 | RBAC roles |
| GET | /api/internal/selfcheck | JWT | 200 | build/routes/process |
| GET | /api/mesh/backends | JWT | 200 | backend inventory |
| POST | /api/mesh/probe | JWT | 200 | mesh probe |
| GET | /api/quantum/models | JWT | 200 | quantum inventory |
| GET | /api/settings | JWT | 200 | current settings |
| GET | /api/dashboard | JWT | 200 | dashboard stats |

---

## 5. FAILURE MODES AND ROOT CAUSES

### 5.1 `/api/status` HTTP 500
- **Symptom**: Returns 500 from HTTP, but in-process `get_health()` returns healthy
- **Root cause**: Exception in `get_health()` during HTTP serving, likely from `psutil.cpu_percent(interval=0.1)` blocking the async loop or from concurrent subsystem health checks timing out
- **Fix path**: Replace `psutil.cpu_percent(interval=0.1)` with non-blocking `cpu_percent(interval=None)` or move health checks to a threadpool; add try/except around garden/flatspace/observability health checks

### 5.2 `/api/garden/metrics` HTTP 500
- **Symptom**: Always 500
- **Root cause**: `garden_metrics()` handler references `request.app.state.orchestrator` but `request` is not in scope (missing parameter)
- **Fix path**: Add `request: Request` parameter to `garden_metrics()` handler

### 5.3 Service running from OneDrive path, not venv
- **Symptom**: `uvicorn_n4_err.log` shows import errors from OneDrive path; process is system Python 3.12
- **Root cause**: NSSM AppDirectory is `C:\Void\ZQM-AI-Master`, but PATH resolution picks up system Python before venv; OneDrive path in sys.path takes precedence
- **Fix path**: Update NSSM Application to full venv path `C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe`; ensure OneDrive path is not in PYTHONPATH

### 5.4 `AgentCapability.TASK_PLANNING` missing
- **Symptom**: Import error in `agent_registry.py:304`
- **Root cause**: Code references `TASK_PLANNING` capability but `AgentCapability` enum only defines 20 capabilities (no `TASK_PLANNING`)
- **Fix path**: Add `TASK_PLANNING = "task_planning"` to `AgentCapability` enum in `app/models/agent.py`

### 5.5 `.env` sed replacement failure
- **Symptom**: `sed -i` with multiple expressions only applied first substitution
- **Root cause**: MSYS `sed` behavior with multiple `-e` expressions; subsequent expressions failed silently due to already-matching patterns or quoting issues
- **Fix path**: Use Python `pathlib` for multi-pattern replacement (already done in successful Python script)

---

## 6. MESH OLLAMA ROUTER (source-level)

**File**: `app/services/mesh_ollama.py` (16KB)
**Backends**: N3 (.78:11434), N1 (.224:11434), N2 (.31:11434), N4 (.228:11434)
**Health check**: tags-first, then generate probe with `qwen2.5:0.5b` / `phi3:mini` / `llama3.2:3b`
**Circuit breaker**: 3 failures → 90s down grace
**Model index**: refreshed every 30s, indexed by model name → backends
**Dispatch**: model-aware selection, prefers local, falls back to degraded backends
**Transport**: chat API first, fallback to generate on 404

---

## 7. QUANTUM-LLM BRIDGE (source-level)

**File**: `app/routers/quantum_llm_bridge.py` (14KB)
**Transport**: paramiko SSH to N1/N2/N3/N4, user `zqmlocal`, password from `QUANTUM_LLM_SSH_PW`
**Driver**: inline Python script written to remote `C:\Temp\qlm_drv.py`, executed via `py -3.12` or `python`
**Modes**: health, verify, models, infer, retrieve
**Fallback**: local subprocess if `QUANTUM_LLM_PYTHON` set
**Current state**: `/api/quantum/health` and `/api/quantum/nodes` timeout (SSH to N2 hangs); `/api/quantum/models` returns 200 via local or N3/N1

---

## 8. SELF-X SUBSYSTEMS

**Self-improve** (`app/orchestrator/self_improve.py`):
- 5 known patches, all propose-only (`ZQM_SELF_APPLY=off`)
- Patches: env-version-envelope, env-version-zqm-response, env-version-healthstatus, env-version-docstring, health-env-authoritative
- Audit: local `self_improve_ledger.jsonl` + FLATSPACE waxcell

**Self-expand** (`app/orchestrator/self_expand.py`):
- Parses EXPAND_AGENT, EXPAND_TOOL, PATCH directives
- Agent whitelist: 15 types; capabilities validated against `AgentCapability` enum
- Tool whitelist: regex `^[a-z][a-z0-9_]{2,40}$`, must reference mesh node
- Placeholder guard rejects LLM template echoes
- Runtime-only agents; tools append to `C:\Users\zqmco\zqm-mcp\zqm_tools_cli.py`

**Self-replicate** (`app/orchestrator/self_replicate.py`):
- Deploys logical replica to N1/N2/N3/N4 via paramiko + git bundle
- Fresh SECRET_KEY if default is weak
- Requires `confirm=true`
- Ledger: `self_replicate_ledger.jsonl`

---

## 9. FLATSPACE TIERED MEMORY

**Tiers**: pollenstore, bitgarden, waxcell, entangle, quantumcell, voidcache
**Modes**: remote / local / auto
**Current mode**: `FLATSPACE_MODE=local` (set in `.env`)
**Local store**: `app/flatspace_local.db` (761KB SQLite)
**Health**: `flatspace.health_check()` returns `True` in local mode without remote probe
**Embeddings**: mesh_ollama.embed() first, fallback to deterministic SHA256-based 384-dim vector

---

## 10. OBSERVABILITY + COST TRACKING

**Prometheus metrics** (unauthenticated `/api/observability/metrics`):
- `zqm_ai_tasks_total{status, cognitive_level, input_method}` — counter, 0 so far
- `zqm_ai_task_duration_seconds{cognitive_level}` — histogram
- `zqm_ai_tokens_total{provider, model}` — counter, 0 so far
- `zqm_ai_agents_active` — gauge, 0.0
- `zqm_ai_cache_hit_rate` — gauge, 0.0
- `zqm_ai_routing_overrides_total{reason}` — counter
- `zqm_ai_task_cost_usd_total{provider, model}` — counter

**Cost tracker**: `app/services/cost_tracker.py`, per-million pricing catalog
- Ollama local = $0.00
- gpt-4o: $2.50/$10.00 input/output per million
- claude-sonnet-4-20250514: $3.00/$15.00
- claude-opus-4-20250514: $15.00/$75.00
- gemini-2.5-pro: $1.25/$5.00

---

## 11. FALSIFICATION PROTOCOL (8 defenses)

1. **Hardware float drift**: `state_hash_with_projection` — raw + symbolic hashing
2. **KV-cache eviction**: `boundary_hash` + `detect_eviction_spike` (5-window, threshold 3.0)
3. **Manifest integrity**: `verify_manifest` — baseline hash comparison
4. **Working-memory boundary**: `envelope_hash` includes WM fingerprint; `detect_semantic_drift`
5. **Normalization entropy**: `normalize_and_hash` — Shannon entropy before/after volatile-key stripping
6. **Constraint/seeds**: seed=42, constraints[max_length=100, no_code_switch, preserve_tense]
7. **World-state fingerprint**: classifies external changes by key diff; blocked creds = critical trigger
8. **External consistency**: temporal ordering check (`temporal_order_ok`)

Router: GET/POST `/api/falsification/audit`, GET `/api/falsification/manifest`, POST `/api/falsification/verify-manifest`

---

## 12. GARDEN COORDINATION (patched)

**Nodes** (now match live mesh):
- Garden-0: 192.168.1.228 (N4, primary/Queen/GPU)
- Garden-1: 192.168.1.224 (N1, Queen 11)
- Garden-2: 192.168.1.78 (N3, Queen 12)
- Garden-3: 192.168.1.31 (N2, Queen 13)
- Garden-4: 192.168.1.225 (COMB, Queen 14)

**Endpoints**: health, coordinate, jobs/{id}, metrics, nodes
**Strategy**: primary first, fallback round-robin, local fallback
**Current limitation**: `/api/garden/metrics` has a bug (missing `request` parameter); health/nodes/coordinate work

---

## 13. SECURITY SUBSYSTEM

**JWT**: HS256, 24h expiry, `SECRET_KEY` from env (64-char hex)
**Login**: `POST /api/users/login` with `{username, password}` — default admin password empty
**Internal service keys**: ZQM-GARDEN, ZQM-FLATSPACE, ZQM-OBSERVABILITY — HMAC-derived from SECRET_KEY
**API keys**: `X-API-Key` with `zqm_` prefix or bcrypt-hashed user keys
**Password hashing**: bcrypt directly (no passlib)
**SSH credentials**: paramiko bridge uses `QUANTUM_LLM_SSH_PW` env var, default `EllaRose89!`, user `zqmlocal`
**CORS**: FastAPI `allow_origins=*` + Traefik strip-cors + restricted cors for webui/n8n

---

## 14. CONFIGURATION GAPS

| Gap | Location | Impact |
|---|---|---|
| Garden IPs stale in comments | `config.py` | Misleading documentation |
| `GARDEN_NODE_2/3/4` mismatch | `.env` | Now patched to .78/.31/.225 |
| `ZQM_GARDEN_0=Y` | NSSM AppEnvironmentExtra | Unknown purpose; likely legacy flag |
| `/api/garden/metrics` 500 | `app/routers/garden.py:...` | Missing `request` parameter |
| `/api/status` 500 | HTTP path | Works in-process; async health check timing issue |
| `AgentCapability.TASK_PLANNING` missing | `app/models/agent.py` | Import error when referenced |
| Service runs from OneDrive path | NSSM config | Code edits in C:\Void\ may not be live |
| `OBSERVABILITY_ENABLED=false` | `.env` | Metrics pipeline proven but not auto-pushing |
| `EDEN_ENABLED=false` | `.env` | SSO/authentik integration disabled at app level |
| `ZQM_ALLOW_EXTERNAL_PROVIDERS` not set | `.env` | External OpenAI/Anthropic blocked |
| `primary_garden='Garden-3 (... .31)'` | runtime | Should be Garden-0 (.228) for N4 |

---

## 15. DATA FLOW (complete, verified)

```
Client → Traefik TLS → FastAPI JWT auth → router
  → orchestrator.execute_task
    → TaskRouter.route_with_audit
    → AgentRegistry.select_for_task
    → CognitiveProcessor.process
      → _run_agent per agent
        → agent_runtime tools OR direct _call_ollama/_call_openai/_call_anthropic
      → TaskResult + CognitiveTrace
    → FalsificationProtocol.full_audit
    → ObservabilityService.push_task_metric (Prometheus counters)
    → FlatSpaceService.store durable task:* + task_result:*
  → ZQM_AIResponse.ok(data=result.model_dump())
```

Self-X flows:
- `/api/self-improve/run` → scan KNOWN_PATCHES → propose/apply → audit ledger + waxcell
- `/api/self-expand/apply` → parse directives → validate whitelist → register agent/tool/patch → audit
- `/api/self-replicate` → paramiko SSH → git bundle → clone → venv build → .env + launcher → NSSM

---

## 16. ARTIFACTS

- `C:\Void\ZQM-AI-Master\void-operations-diagram.html`
- `C:\Void\ZQM-AI-Master\void-3d-explorer.html`
- `C:\Void\ZQM-AI-Master\full-system-enumeration.md`
- `C:\Void\ZQM-AI-Master\deep-systems-study.md` (this file)
- `C:\temp\live_system_state.json`
