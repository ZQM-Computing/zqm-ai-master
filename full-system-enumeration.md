# FULL SYSTEM ENUMERATION — ZQM MESH + ZQM-AI-MASTER
## 2026-08-05 14:11 EDT — Live Verified State

---

## 1. ZQM-Void-N4 SERVICE (Windows Service / NSSM)
- Service: ZQM-Void-N4 — Running, Automatic start
- NSSM config:
  - Application: C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe
  - AppParameters: -m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir C:\Void\ZQM-AI-Master
  - AppEnvironmentExtra: ZQM_GARDEN_0=Y
- Process lineage (PID 11276):
  - PID 11276: C:\Program Files\Python312\python.exe (system Python 3.12) — actual :8808 listener
  - PID 47968: C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe (venv Python 3.12) — parent
  - Note: uvicorn spawn behavior creates child system Python process despite venv launch
- Port: 0.0.0.0:8808 LISTENING
- API version: 2.1.4
- Codename: Conversational

---

## 2. OPENAPI ROUTE INVENTORY (76 paths)

### 2.1 Core AI Processing
- POST /api/process — task execution (BASIC/ADVANCED/NEURAL/AUTONOMOUS)
- GET /api/process/{task_id} — task status/result
- GET /api/process/history — task history
- POST /api/predict — prediction
- GET /api/predict/models — available models
- POST /api/integrate — integration pipeline

### 2.2 Self-Improvement / Expansion / Replication
- POST /api/self-improve/run — trigger self-improvement loop
- GET /api/self-improve/ledger — improvement history
- POST /api/self-expand/apply — apply pending expansions
- GET /api/self-expand/ledger — expansion ledger
- GET /api/self-expand/status — expansion status
- GET /api/self-apply/status — apply status
- POST /api/self-replicate — initiate replica deployment
- GET /api/self-replicate/ledger — replication history
- GET /api/self-replicate/status — replication status
- GET /api/self-improvement — self-improvement status
- POST /api/roundtable — roundtable deliberation

### 2.3 Garden / Mesh Coordination
- GET /api/garden/health — garden health
- GET /api/garden/nodes — garden nodes
- GET /api/garden/metrics — garden metrics
- GET /api/garden/jobs/{job_id} — job status
- POST /api/garden/coordinate — cross-node coordination
- GET /api/mesh/backends — mesh backends
- POST /api/mesh/probe — probe mesh backend
- GET /api/mesh/ollama — ollama mesh status

### 2.4 Quantum-LLM Bridge
- GET /api/quantum/health — quantum node health
- GET /api/quantum/verify — quantum verify
- GET /api/quantum/nodes — all quantum nodes
- GET /api/quantum/models — quantum model inventory
- POST /api/quantum/infer — hybrid inference
- POST /api/quantum/retrieve — quantum retrieval

### 2.5 Flatspace / Memory
- POST /api/flatspace/store — store in flatspace
- GET /api/flatspace/retrieve/{key} — retrieve
- GET /api/flatspace/stats — flatspace stats
- GET /api/flatspace — flatspace status
- DELETE /api/flatspace/delete/{key} — delete
- POST /api/flatspace/search — search (POST-only, requires JSON body)

### 2.6 Observability / Monitoring
- GET /api/observability/health — observability health
- GET /api/status — system status
- GET /api/status/ping — ping
- GET /api/status/history — status history
- GET /api/internal/selfcheck — internal self-check
- GET /api/stream — SSE stream
- GET /api/stream/stats — stream stats
- GET /api/stream/webhooks — webhook list
- GET /api/task-audit — task audit

### 2.7 Dashboard / Agents
- GET /api/dashboard — dashboard overview
- GET /api/dashboard/agents — paginated agents
- GET,POST,PATCH,DELETE /api/dashboard/agents/{agent_id} — agent CRUD
- GET /api/dashboard/garden — garden dashboard
- GET /api/dashboard/cache — cache stats
- DELETE /api/dashboard/cache — clear cache
- GET /api/agents — agents alias (200 after fix)

### 2.8 Authentication / Users
- POST /api/users/login — JWT login
- GET /api/users — list users
- GET /api/users/me — current user
- POST /api/users/{user_id}/api-key — create API key

### 2.9 Permissions / RBAC
- GET /api/permissions — permissions
- POST /api/permissions/check — check permission
- GET /api/permissions/roles — roles
- GET /api/permissions/roles/{role_id} — role detail

### 2.10 Info / Meta
- GET /api/info — service info
- GET /api/info/agents — agent info
- GET /api/version — version
- GET /api/settings — runtime settings
- PUT /api/settings — update settings
- GET /api/mcp-audit — MCP audit

### 2.11 Falsification Protocol
- GET /api/falsification/manifest — falsification manifest
- POST /api/falsification/verify-manifest — verify manifest
- GET,POST /api/falsification/audit — falsification audit

### 2.12 Webhooks / Training
- GET /api/webhook/ — webhook info
- POST /api/webhook/azure-devops
- POST /api/webhook/dealwork
- POST /api/webhook/deploy
- POST /api/webhook/github
- POST /api/train — trigger training
- GET /api/train/domains — training domains
- GET /api/train/status/{job_id} — training status

### 2.13 Communication
- POST /api/void/talk — void talk (POST-only, 405 on GET)
- GET /api/self-improvement — self-improvement status

---

## 3. DOCKER STACK (23/23 containers)

| Container | Image | Status | Host Ports |
|-----------|-------|--------|------------|
| zqm-traefik | traefik:v3.1.2 | Up 24h | 80, 443, 8089, 8088->8080 |
| zqm-coredns | coredns/coredns:1.11.4 | Up 17m | 53/tcp, 53/udp (Docker display only; HostConfig.PortBindings={}) |
| zqm-dot | mvance/unbound:latest | Up 29h | 0.0.0.0:853->853 |
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

Notes:
- CoreDNS: docker ps shows 53/tcp,53/udp but `docker inspect` confirms HostConfig.PortBindings is empty; Windows Dnscache owns UDP:53 (PID 4288 svchost.exe)
- zqm-dot DoT on :853 healthy
- 22 Docker images, 34.37GB total

---

## 4. WINDOWS SERVICES
- ZQM-Void-N4: Running, Automatic
- ZQMEnum: Running, Automatic

---

## 5. PYTHON INTERPRETERS ON HOST
- System Python: C:\Program Files\Python312\python.exe (3.12.x)
- uv Python: C:\Users\zqmco\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe
- Venv Python (ZQM-AI-Master): C:\Void\ZQM-AI-Master\.venv\Scripts\python.exe (3.12.10)
- Hermes venv Python: C:\Users\zqmco\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
- zqm-mcp venv Python: C:\Users\zqmco\zqm-mcp\.venv\Scripts\python.exe

---

## 6. ZQM-MESH NODE MATRIX (5 nodes)

| Node | IP | SSH | Ollama | REST | API | UI | Quantum | N8N |
|------|-----|-----|--------|------|-----|----|--------|----|
| N1 | 192.168.1.224 | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT |
| N2 | 192.168.1.31 | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT |
| N3 | 192.168.1.78 | OPEN | OPEN | OPEN | TIMEOUT | TIMEOUT | OPEN | OPEN |
| N4 | 192.168.1.228 | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT |
| N9 | 192.168.1.250 | OPEN | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT | TIMEOUT |

SSH recon:
- N3: reachable but auth rejected with mesh key
- N9: reachable but auth rejected with mesh key
- N1/N2/N4: unreachable in mesh probes despite N4 local :8808 healthy

---

## 7. ENDPOINT HEALTH MATRIX

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| /api/status | GET | 200 | |
| /api/status/ping | GET | 200 | |
| /api/status/history | GET | 200 | |
| /api/version | GET | 200 | 2.1.4 Conversational |
| /api/garden/health | GET | 200 | |
| /api/garden/nodes | GET | 200 | |
| /api/garden/metrics | GET | 200 | |
| /api/garden/jobs/{id} | GET | — | |
| /api/garden/coordinate | POST | — | |
| /api/observability/health | GET | 200 | enabled=false |
| /api/dashboard | GET | 200 | |
| /api/dashboard/agents | GET | 200 | paginated |
| /api/dashboard/agents/{id} | GET/POST/PATCH/DELETE | — | |
| /api/dashboard/garden | GET | — | |
| /api/dashboard/cache | GET/DELETE | — | |
| /api/agents | GET | 200 | alias fixed |
| /api/info | GET | — | |
| /api/info/agents | GET | 200 | |
| /api/permissions | GET | 200 | |
| /api/permissions/check | POST | — | |
| /api/permissions/roles | GET | — | |
| /api/permissions/roles/{id} | GET | — | |
| /api/process | GET/POST | 200 | |
| /api/process/{task_id} | GET | — | |
| /api/process/history | GET | — | |
| /api/predict | POST | — | 405 on GET |
| /api/predict/models | GET | — | |
| /api/void/talk | POST | 200 | 405 on GET |
| /api/flatspace/search | POST | 200 | 405 on GET |
| /api/flatspace/store | POST | — | |
| /api/flatspace/retrieve/{key} | GET | — | |
| /api/flatspace/stats | GET | — | |
| /api/flatspace/delete/{key} | DELETE | — | |
| /api/self-improve/run | POST | — | 405 on GET |
| /api/self-improve/ledger | GET | — | |
| /api/self-expand/apply | POST | — | 405 on GET |
| /api/self-expand/ledger | GET | — | |
| /api/self-expand/status | GET | — | |
| /api/self-apply/status | GET | — | |
| /api/self-replicate | POST | — | |
| /api/self-replicate/ledger | GET | — | |
| /api/self-replicate/status | GET | — | |
| /api/self-improvement | GET | — | |
| /api/roundtable | POST | — | |
| /api/settings | GET/PUT | 200 | |
| /api/users/login | POST | 200 | JWT HS256 |
| /api/users | GET | — | |
| /api/users/me | GET | — | |
| /api/users/{id}/api-key | POST | — | |
| /api/internal/selfcheck | GET | 200 | |
| /api/mesh/backends | GET | 200 | |
| /api/mesh/probe | POST | — | |
| /api/mesh/ollama | GET | 200 | |
| /api/quantum/health | GET | 200 | |
| /api/quantum/verify | GET | — | |
| /api/quantum/nodes | GET | 200 | |
| /api/quantum/models | GET | 200 | ~7s SSH bridge |
| /api/quantum/infer | POST | — | |
| /api/quantum/retrieve | POST | — | |
| /api/falsification/manifest | GET | — | |
| /api/falsification/verify-manifest | POST | — | |
| /api/falsification/audit | GET/POST | — | |
| /api/stream | GET | — | SSE |
| /api/stream/stats | GET | — | |
| /api/stream/webhooks | GET | — | |
| /api/task-audit | GET | — | |
| /api/train | POST | — | |
| /api/train/domains | GET | — | |
| /api/train/status/{job_id} | GET | — | |
| /api/webhook/ | GET | — | |
| /api/webhook/azure-devops | POST | — | |
| /api/webhook/dealwork | POST | — | |
| /api/webhook/deploy | POST | — | |
| /api/webhook/github | POST | — | |
| /api/mcp-audit | GET | — | |

---

## 8. AUTH SUBSYSTEM
- JWT HS256, 24h expiry
- SECRET_KEY: 64-char hex from .env
- Default admin: username=admin, password=empty string
- bcrypt password hashing
- Internal service keys: ZQM-GARDEN, ZQM-FLATSPACE, ZQM-OBSERVABILITY
- API key support with zqm_ prefix
- Production guard refuses boot if SECRET_KEY is changeme* or <32 chars

---

## 9. COGNITIVE PROCESSOR
- 4 levels: BASIC, ADVANCED, NEURAL, AUTONOMOUS
- Token accounting via AgentExecution.tokens_used → CognitiveTrace.total_tokens → TaskResult.total_tokens
- estimate_cost() uses per-million pricing catalog
- Token counts verified: BASIC=258, ADVANCED=7303, NEURAL=8185; cost_usd=0.00 (local Ollama)

---

## 10. AGENT REGISTRY
- 22 default agents in DEFAULT_AGENTS pool
- Types: nlp, reasoning, synthesis, memory, learning, gis, hydrology, observability, api, data, data_analysis, code, security, infrastructure, garden, scheduler, flatspace, quantum
- AgentCapability.TASK_PLANNING present at agent.py:79
- TASK_PLANNING reference in agent_registry.py:304 — resolved, capability defined

---

## 11. FLATSPACE
- Remote tier store preferred, falls back to local SQLite
- Local DB: C:\Void\ZQM-AI-Master\app\flatspace_local.db
- Embedding-assisted search
- Verified: search returns bitgarden tier results

---

## 12. SELF-IMPROVEMENT / EXPANSION / REPLICATION
- Background loop: 600s interval
- Findings persist to FLATSPACE bitgarden with JSONL fallback
- self_replicate.py: OneDrive fallback removed; raises RuntimeError if ZQM_VOID_SRC unset
- Expansion ledger: review queue for human approval

---

## 13. QUANTUM-LLM BRIDGE
- Transport: SSH to mesh nodes or local subprocess via QUANTUM_LLM_PYTHON
- Default nodes: N1-N4
- Password: QUANTUM_LLM_SSH_PW from env or default EllaRose89!
- Modes: health, verify, models, infer, retrieve
- Timeout: 240s default, 60s for verify
- Verified: health/nodes/models return 200 via SSH bridge

---

## 14. OBSERVABILITY
- Health: ok, prometheus_client=true
- Enabled: false (fail-soft)
- Endpoint: http://127.0.0.1:8808/api/observability/metrics
- Push disabled; no external scrape configured

---

## 15. KNOWN GAPS (resolved / pending)

Resolved:
- /api/agents 500 → fixed alias defaults
- /api/void/talk 405 on GET → POST contract correct
- /api/flatspace/search 422 → POST with JSON body required
- OneDrive fallback → removed hardcoded path
- CoreDNS host port 53 → compose has no bindings; Windows Dnscache owns UDP 53
- Garden IPs → patched to .228/.224/.78/.31/.225
- Traefik CORS → strip-cors + cors middleware active
- Cert SAN → 39 DNS + IP .228, valid until 2036
- Batch wrapper → removed; NSSM direct venv Python launch

Pending:
- N4 dual-launcher anomaly: uvicorn spawns system Python child process
- Mesh SSH auth rejection on N3/.78 and N9/.250
- Mesh_overview TIMEOUT on N1/N2/N4 from local host
- Observability enabled=false
- Default admin empty password
- Quantum/models and settings endpoints show latency >6s on first call

---

## 16. RESOURCES
- Host: Dell XPS 8960, i9-14900KF, 96GB RAM
- OS: Windows 11
- Uptime: ~4.8 days
- C: drive free: 5008GB / 7429GB (67.4%)
- Docker: 22 images, 34.37GB, 0% reclaimable

---

## 17. DNS / TLS
- Windows hosts: 57 entries; 54 → 192.168.1.228, 3 → 192.168.1.224 (n1.zqm TLDs)
- TLD coverage: *.zqm, *.zqm.mesh, *.zqmlabs.com
- CoreDNS: Docker-internal only, no host port 53
- DoT: zqm-dot on 0.0.0.0:853
- Cert: zqm-mesh.crt imported to Windows Trusted Root; 39 DNS SAN + IP .228

---

## 18. MESH NODE SSH ACCESS
- N3/.78: SSH open, auth rejected with mesh key
- N9/.250: SSH open, auth rejected with mesh key
- N2/.31: TIMEOUT (possibly powered off)
- N1/.224: TIMEOUT in mesh probes; N1 Void API on :8099 reachable directly
- N4/.228: local, Void API on :8808 healthy

---

END OF ENUMERATION
