# FULL COMPREHENSIVE ANALYSIS — ZQM-AI-Master + ZQM-MESH
## 2026-08-05 18:45 EDT — Live Verified State

---

## EXECUTIVE SUMMARY
- N4 Void API healthy: 94 HTTP routes, 200 OK on all core endpoints, version 2.1.4
- 23/23 Docker containers up
- 22 agents configured and idle
- 5 garden nodes online per API
- Mesh Ollama catalog: 65 models across N1/N3/N4; N2 unhealthy
- Quantum-LLM bridge v1.0.3 active on N2/.31 and N3/.78; N1/.224 and N4/.228 SSH channel closed
- OneDrive path contamination removed
- Known runtime quirks: dual-launcher venv→system Python, null memory/cpu in status, slow mesh sweeps

---

## 1. API ROUTE INVENTORY (76 paths, 94 HTTP methods)

### 1.1 Status/Health
- GET /api/status — system health; memory_mb/cpu_percent currently null
- GET /api/status/ping — fast liveness
- GET /api/status/history — task history
- GET /api/internal/selfcheck — process, build, routes, config lengths

### 1.2 Dashboard/Agents
- GET /api/dashboard — full dashboard stats (~5.4s)
- GET /api/dashboard/agents — paginated agent list
- GET /api/agents — alias for dashboard/agents (fixed)
- GET/POST/PATCH/DELETE /api/dashboard/agents/{id}
- GET /api/dashboard/garden
- GET/DELETE /api/dashboard/cache

### 1.3 Task Processing
- GET/POST /api/process — execute task
- GET /api/process/{task_id}
- GET /api/process/history
- POST /api/predict — prediction
- GET /api/predict/models

### 1.4 Self-Improvement/Expansion/Replication
- POST /api/self-improve/run
- GET /api/self-improve/ledger
- POST /api/self-expand/apply
- GET /api/self-expand/ledger
- GET /api/self-expand/status
- GET /api/self-apply/status
- POST /api/self-replicate
- GET /api/self-replicate/ledger
- GET /api/self-replicate/status
- GET /api/self-improvement
- POST /api/roundtable

### 1.5 Garden/Mesh
- GET /api/garden/health
- GET /api/garden/nodes — returns raw list of 5 garden nodes
- GET /api/garden/metrics
- GET /api/garden/jobs/{job_id}
- POST /api/garden/coordinate
- GET /api/mesh/backends — mesh Ollama backends (~22s)
- POST /api/mesh/probe
- GET /api/mesh/ollama — aggregated catalog (~22s)

### 1.6 Quantum-LLM Bridge
- GET /api/quantum/health (~5.8s)
- GET /api/quantum/verify
- GET /api/quantum/nodes (~8.8s)
- GET /api/quantum/models (~5.8s)
- POST /api/quantum/infer
- POST /api/quantum/retrieve

### 1.7 Flatspace
- GET /api/flatspace
- POST /api/flatspace/store
- GET /api/flatspace/retrieve/{key}
- GET /api/flatspace/stats
- DELETE /api/flatspace/delete/{key}
- POST /api/flatspace/search — POST-only, requires JSON body

### 1.8 Communication
- POST /api/void/talk — POST-only
- GET /api/stream — SSE
- GET /api/stream/stats
- GET /api/stream/webhooks

### 1.9 Auth/Permissions
- POST /api/users/login — JWT HS256
- GET /api/users
- GET /api/users/me
- POST /api/users/{id}/api-key
- GET /api/permissions
- POST /api/permissions/check
- GET /api/permissions/roles
- GET /api/permissions/roles/{role_id}

### 1.10 Info/Settings
- GET /api/info
- GET /api/info/agents
- GET /api/version
- GET /api/settings
- PUT /api/settings
- GET /api/mcp-audit

### 1.11 Falsification
- GET /api/falsification/manifest
- POST /api/falsification/verify-manifest
- GET/POST /api/falsification/audit

### 1.12 Webhooks/Training
- GET /api/webhook/
- POST /api/webhook/azure-devops
- POST /api/webhook/dealwork
- POST /api/webhook/deploy
- POST /api/webhook/github
- POST /api/train
- GET /api/train/domains
- GET /api/train/status/{job_id}

---

## 2. PROCESS / RUNTIME

### 2.1 Service
- Windows service: ZQM-Void-N4
- Start type: Automatic
- NSSM Application: C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe
- NSSM AppParameters: -m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir C:\Void\ZQM-AI-Master
- AppEnvironmentExtra: ZQM_GARDEN_0=Y

### 2.2 Process Lineage (as of latest restart)
- PID 11276: C:\Program Files\Python312\python.exe — actual :8808 listener
- PID 47968: C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe — parent
- PID 44964: nssm.exe — grandparent
- Observation: uvicorn spawns a system Python child despite being launched from venv Python. This is a known Windows/uvicorn behavior quirk, not a functional bug.

### 2.3 Runtime Notes
- Venv Python: 3.12.10
- System Python: 3.12.x
- uv Python: 3.11 (used by Hermes/zqm-mcp)
- __pycache__ cleared before last restart

---

## 3. DOCKER STACK (23/23 containers)

| Container | Image | Status | Notes |
|-----------|-------|--------|-------|
| zqm-traefik | traefik:v3.1.2 | Up 25h | 80, 443, 8089, 8088->8080 |
| zqm-coredns | coredns/coredns:1.11.4 | Up 28m | Host port 53 bindings: none in HostConfig; Windows Dnscache owns UDP 53 |
| zqm-dot | mvance/unbound:latest | Up 29h | DoT on :853 |
| zqm-web | nginx:alpine | Up 5d | 127.0.0.1:8090->80 |
| searxng | searxng/searxng:latest | Up 5d | 127.0.0.1:8080->8080 |
| zqm-quantum-api | 9724e4be9235 | Up 5d | 0.0.0.0:8891->8891 |
| zqm-mesh-api | 330908a296d6 | Up 5d (healthy) | 8899/tcp |
| anythingllm | de3b7dfdb25b | Up 5d (healthy) | — |
| open-webui | ghcr.io/open-webui/open-webui:main | Up 5d (healthy) | 8080/tcp |
| n8n | 9cb60554716a | Up 5d (healthy) | 5678/tcp |
| zqm-traefik-outpost | ghcr.io/goauthentik/proxy:2024.10.2 | Up 5d (healthy) | 9000, 9300, 9443 |
| zqm-whisper | fedirz/faster-whisper-server:latest-cpu | Up 5d (healthy) | — |
| zqm-chat | ghcr.io/mckaywrigley/chatbot-ui:main | Up 5d (healthy) | 3000/tcp |
| zqm-stirling | frooodle/s-pdf:latest | Up 5d (healthy) | 8080/tcp |
| authentik-server | ghcr.io/goauthentik/server:2024.10.2 | Up 5d (healthy) | — |
| zqm-litellm | cc51c4c10fb6 | Up 5d (healthy) | 4000/tcp |
| authentik-worker | ghcr.io/goauthentik/server:2024.10.2 | Up 5d (healthy) | — |
| zqm-flowise | flowiseai/flowise:latest | Up 5d (healthy) | — |
| zqm-status | louislam/uptime-kuma:latest | Up 5d (healthy) | 127.0.0.1:3001->3001 |
| one-api | a55fb5181854 | Up 5d (healthy) | 3000/tcp |
| zqm-home | ghcr.io/gethomepage/homepage:latest | Up 5d (healthy) | 3000/tcp |
| zqm-redis | redis:7-alpine | Up 5d (healthy) | 6379/tcp |
| zqm-postgres | postgres:16-alpine | Up 5d (healthy) | 5432/tcp |

- 22 images, 34.37GB total
- TLS: zqm-mesh.crt with 39 DNS SAN + IP .228, valid until 2036, imported into Windows Trusted Root

---

## 4. WINDOWS HOST/SERVICES
- Services: ZQM-Void-N4 (Running), ZQMEnum (Running)
- Hosts file: 57 entries; 54 → 192.168.1.228, 3 → 192.168.1.224
- Port 53: Windows Dnscache owns UDP 53 exclusively; CoreDNS Docker-internal only
- DoT: 0.0.0.0:853

---

## 5. ZQM-MESH NODE MATRIX

| Node | IP | HTTP :8808/:8099 | Quantum SSH | Ollama | Notes |
|------|-----|-------------------|-------------|--------|-------|
| N1 | 192.168.1.224 | direct reach | Channel closed | 9 models | Void API on :8099 |
| N2 | 192.168.1.31 | — | ok | unhealthy | 0 models, 5 failures |
| N3 | 192.168.1.78 | — | ok | 25 models | |
| N4 | 192.168.1.228 | healthy local | Channel closed | 47 models | :8808 listener |
| N9 | 192.168.1.250 | — | — | — | SSH open, auth rejected |

- Garden API reports all 5 garden nodes online
- Dashboard reports garden_nodes_online=2

---

## 6. OLLAMA MESH CATALOG (65 unique models)

### N4 (47 models)
- Large: deepseek-r1:70b, llama3.3:70b, llama3.1:70b, qwen2.5:72b, qwen3:32b, qwq:32b
- Mid: deepseek-r1:32b, qwen3:14b/8b/4b/1.7b/0.6b, qwen2.5:14b/7b/3b/1.5b, llama3.1:8b, llama3.2:3b/1b, gemma3:12b/4b, gemma2:9b, phi4, phi3.5, mistral-nemo:12b, mixtral:8x7b
- Small: qwen2.5:0.5b, smollm2:360m
- Vision/embed: llava:13b, llava-phi3, qwen2.5vl:7b/3b, minicpm-v, bge-m3, mxbai-embed-large, nomic-embed-text
- Specialized: deepseek-r1:14b/8b/7b/1.5b, qwen2.5-coder:32b/14b/7b

### N3 (25 models)
- Tuned: gemma4-tuned, qwen2.5-coder-14b-tuned, deepseek-r1-8b-tuned, llama3.1-8b-tuned, qwen3.6-tuned, qwen2.5-3b-tuned, phi3-mini-tuned, nomic-embed-text-tuned, llama3.2-3b-tuned
- Base: gemma4:latest, qwen3.6:latest, qwen3:8b, qwen2.5:14b, qwen2.5-coder:14b, deepseek-r1:8b, llama3.1:8b, llama3.2:3b, mistral:7b, moondream, nomic-embed-text

### N1 (9 models)
- Specialized: triage-bounty-zqm:latest, extbounty-scope:latest, extbounty-scope-zqm:latest
- Base: qwen2.5:3b, llama3.2:3b, moondream:latest, nomic-embed-text:latest, qwen3:8b, qwen3.6:latest

### N2 (0 models)
- unhealthy; status_failures=5; recovery_in_s ~90s

---

## 7. QUANTUM-LLM BRIDGE

### 7.1 Package Inventory (active node N2/.31)
- Package: quantum_llm v1.0.3
- Path: C:\Users\zqmlocal\AppData\Roaming\Python\Python312\site-packages\quantum_llm
- 13 files, 90,636 bytes
- Files: __init__.py, admin.py, bench_result.json, cli.py, deep_bench.json, deep_bench.py, hybrid_transformer.py, install.py, operations.py, quantum_inference.py, quantum_retrieval.py, retrieval_index.jsonl, warmup.py
- No standalone model checkpoint files; model instantiated at runtime via HybridQuantumLanguageModel

### 7.2 Node Health
- N1/.224: error — ssh transport error (retry 3): Channel closed.
- N2/.31: ok — import 1.0.3, forward [2,4,256], retrieval hits=2, warmup q2/q3/q4 statevector_ok + model_warm + inference_warm + retrieval_warm
- N3/.78: ok — same profile as N2
- N4/.228: error — ssh transport error (retry 3): Channel closed.

### 7.3 Tools exposed to agents
- quantum_verify, quantum_infer, quantum_retrieve, quantum_models, quantum_nodes

---

## 8. AGENT RUNTIME TOOLS

From agent_runtime.py:
- FLATSPACE: flatspace_search, flatspace_retrieve, flatspace_store
- GARDEN: garden_metrics, garden_submit
- OLLAMA: ollama_models — returns mesh catalog with fallback to local
- OBSERVABILITY: observability_log
- HTTP: http_get — gated by ZQM_ALLOW_EXTERNAL_PROVIDERS
- ZQM-LOCAL-TOOLS: generic bridge to zqm_tools_cli.py via zqm-mcp venv

---

## 9. AUTH/CONFIG

### 9.1 Live selfcheck config lengths
- SECRET_KEY: 64 bytes
- ZQM_INTERNAL_KEY: 48 bytes
- GITHUB_WEBHOOK_SECRET: 48 bytes
- ZQM_ADMIN_PASSWORD: 0 bytes (empty)
- ZQM_GARDEN_SERVICE_KEY: 48 bytes
- ZQM_FLATSPACE_SERVICE_KEY: 48 bytes
- ZQM_OBSERVABILITY_SERVICE_KEY: 48 bytes
- OLLAMA_API_KEY: 0 bytes

### 9.2 Production guard
- Refuses boot if SECRET_KEY is changeme* or <32 chars
- Does not enforce admin password non-empty

---

## 10. RESOLVED ISSUES
- /api/agents 500 — fixed alias defaults
- /api/void/talk 405 on GET — POST contract correct
- /api/flatspace/search 422 — POST with JSON body required
- OneDrive fallback — removed hardcoded path; raises if ZQM_VOID_SRC unset
- CoreDNS host port 53 — compose has no bindings; Windows Dnscache owns UDP 53
- Garden IPs — patched to .228/.224/.78/.31/.225
- Traefik CORS — strip-cors + cors middleware active
- Cert SAN — 39 DNS + IP .228, valid until 2036
- NSSM Application — set to venv Python directly

---

## 11. OPEN ISSUES / GAPS

### 11.1 memory_mb and cpu_percent null in /api/status
- Code uses psutil in orchestrator.get_health()
- Likely cause: psutil not installed in venv, so except ImportError sets mem/cpu to None
- Fix: pip install psutil in venv

### 11.2 Slow endpoints
- /api/dashboard ~5.4s
- /api/quantum/* ~6-9s
- /api/mesh/* ~22s
- Cause: external SSH probes and concurrent health checks with 6s timeout

### 11.3 N2 Ollama unhealthy
- 5 failures, recovery_in_s ~90s, 0 models
- N2 is healthy for quantum SSH; this is Ollama-specific

### 11.4 Mesh_overview TIMEOUT on N4 local
- mesh_peer_discover/mesh_overview times out on N4 despite local :8808 healthy
- mesh_overview uses canonical NODES map; N4 may be probed via stale IP or wrong port

### 11.5 N1/N4 Quantum SSH Channel closed
- SSH transport error for quantum bridge on N1/.224 and N4/.228
- N3/.31 and N2/.78 healthy via same SSH path

### 11.6 Dual-launcher anomaly
- Venv Python spawns system Python child for uvicorn
- No functional impact observed, but complicates process management

### 11.7 Observability enabled=false
- Health checks work, but Prometheus push disabled

---

## 12. RECOMMENDATIONS (priority order)

1. Install psutil in venv to populate memory_mb/cpu_percent
2. Profile /api/mesh/backends and /api/mesh/ollama to reduce 22s latency
3. Fix N2 Ollama health — check service/runtime on N2/.31
4. Investigate N1/N4 quantum SSH channel closed — possible SSH config or firewall
5. Consider enabling observability or removing dead code paths
6. Enforce admin password policy in non-development environments

---

END OF ANALYSIS
