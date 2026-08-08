# ZQM Cross-Repo Integration Roadmap
_Generated from live source inspection of `C:\Void\ZQM-AI-Master` on 2026-08-08._

## Summary of Verified State
- SSO router exists at `app/routers/sso.py`, but `/login` currently returns **501 not implemented** and there is no real OIDC discovery/token exchange.
- RAG router exists at `app/routers/rag.py` and already has a partial `_rerank_results()` using Ollama `/api/embed` with model `bge-m3`. No local embedding model guarantee, no retry/fallback config, and no persistence of reranked provenance.
- Inference router exists at `app/inference/mesh_router.py` with `discover_mesh_nodes()` using `/healthz` latency and a `route_inference()` stub. No real memory/VRAM enforcement, no repo-scoped config source, and mesh node list is hardcoded.
- Signing service exists at `app/services/signing_service.py` with CMS/Authenticode wrappers. No FastAPI router/endpoints expose it, and no shield/attestation workflow consumes it.
- Users router at `app/routers/users.py` already has lockout and refresh tokens, but SSO and local JWT are disconnected; `/me` endpoints are duplicated across `users` and `sso`.

## Prioritized Integration Plan

### P1 — SSO Router -> Eden/OIDC Flow
**Goal:** Replace 501 stub with real OIDC login and unify identity surface.
- File target: `app/routers/sso.py`
- Endpoint targets: `POST /api/auth/sso/login`, `GET /api/auth/sso/status`, `GET /api/auth/sso/me`
- Config keys:
  - `EDEN_ENABLED`
  - `EDEN_ENDPOINT`
  - `SSO_OIDC_ISSUER`
  - `SSO_OIDC_CLIENT_ID`
  - `SSO_OIDC_CLIENT_SECRET`
  - `SSO_OIDC_METADATA_URL` or discovery docs path
  - `SSO_DEFAULT_REDIRECT_URI`
  - `SSO_PROVIDER`
- Suggested work:
  1. Add discovery/metadata fetch from `SSO_OIDC_ISSUER/.well-known/openid-configuration`.
  2. Implement token exchange and id-token verification.
  3. Normalize claims into local JWT shape compatible with `app/core/security.py`.
  4. Add `/api/auth/sso/refresh` to align with existing refresh token logic in `app/routers/users.py`.
- Commit sequence:
  - `feat(auth): add SSO_OIDC_* config keys to Settings`
  - `feat(auth): wire OIDC discovery and token exchange in sso router`
  - `feat(auth): unify /me schema between sso and users routers`

### P1 — Missing Auth Hook: Unify Token Issuer/Claims
- File target: `app/core/security.py`, `app/routers/users.py`, `app/routers/sso.py`
- Endpoint target: `POST /api/users/login`, `GET /api/users/me`, `GET /api/auth/sso/me`
- Config keys:
  - `JWT_ISSUER`
  - `JWT_AUDIENCE`
  - `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `REFRESH_TOKEN_TTL_MINUTES`
- Suggested work:
  - Use consistent `iss`/`aud` across local and SSO-issued tokens.
  - Add typed claim `auth_source: local|sso|service`.
- Commit sequence:
  - `feat(auth): add iss/aud claims and auth_source typing`
  - `feat(auth): align users/sso /me response schema`

### P2 — mesh-forensics latency -> mesh_router -> inference routing
**Goal:** Use verified latency source instead of hardcoded `/healthz` probe.
- File target: `app/inference/mesh_router.py`
- Endpoint targets: `GET /healthz`, future `GET /api/mesh_forensics/latency` or equivalent forensics feed
- Config keys:
  - `MESH_NODES`
  - `MESH_LATENCY_SOURCE_URL`
  - `MESH_LATENCY_REFRESH_SECONDS`
  - `MESH_ROUTE_STRATEGY: latency|capacity|hybrid`
  - `MESH_NODE_<ID>_IP`, `MESH_NODE_<ID>_PORT`
  - `MESH_MIN_RAM_GB`, `MESH_MIN_VRAM_GB`
- Suggested work:
  1. Replace inline `MESH_NODES` with config-driven node registry.
  2. Consume mesh forensics latency data rather than only `/healthz`.
  3. Enforce model-to-node capacity checks instead of always returning `live[0]`.
- Commit sequence:
  - `feat(mesh): add MESH_NODE_* config keys and route strategy`
  - `feat(mesh): consume forensics latency source in mesh_router`
  - `feat(mesh): enforce model VRAM/RAM routing constraints`

### P2 — bge-m3 rerank -> RAG pipeline
**Goal:** Make rerank configurable, observable, and locally validated.
- File target: `app/routers/rag.py`
- Endpoint targets: `POST /api/rag/query`, `GET /api/rag/diag`
- Config keys:
  - `RAG_RERANK_ENABLED`
  - `RAG_RERANK_MODEL`
  - `RAG_RERANK_EMBEDDING_BACKEND: ollama|chroma|openai`
  - `RAG_RERANK_TIMEOUT_SECONDS`
  - `RAG_RERANK_FALLBACK: preserve_order|none`
  - `CHROMA_COLLECTION`, `CHROMA_URL`, `CHROMA_ENABLED`
  - `OLLAMA_DEFAULT_MODEL`, `OLLAMA_BASE_URL`
- Suggested work:
  1. Gate rerank behind `RAG_RERANK_ENABLED`.
  2. Make embedding backend explicit; support Chroma collection embedding path.
  3. Preserve rerank provenance in response for debugging.
- Commit sequence:
  - `feat(rag): add RAG_RERANK_* config keys and enable flag`
  - `feat(rag): support chroma-backed embeddings in rerank`
  - `feat(rag): expose rerank provenance in /api/rag/query response`

### P2 — Chroma / Meilisearch integration gaps
- File target: `app/services/chroma_service.py`
- Endpoint target: `GET /api/rag/diag`, future `POST /api/rag/vector/upsert`
- Config keys:
  - `CHROMA_URL`
  - `CHROMA_COLLECTION`
  - `CHROMA_ENABLED`
  - `MEILISEARCH_URL`
  - `MEILISEARCH_MASTER_KEY`
  - `MEILISEARCH_DEFAULT_INDEX`
- Suggested work:
  1. Fix Chroma embedding payload to use configured model instead of hardcoded `all-minilm:latest`.
  2. Add sync path from Meilisearch docs to Chroma for unified vector search.
- Commit sequence:
  - `fix(rag): use configurable Chroma embedding model`
  - `feat(rag): add Meilisearch -> Chroma sync path`

### P3 — signing_service -> shield/attestation-toolkit
**Goal:** Expose signing operations via API and hook them into release/attestation pipelines.
- File target: `app/services/signing_service.py`, new `app/routers/attestation.py`
- Endpoint targets: `POST /api/attestation/sign`, `POST /api/attestation/verify`
- Config keys:
  - `ZQM_CMS_SIGN_SCRIPT`
  - `ZQM_SIGNTOOL`
  - `ATTESTATION_CERT_PATH`
  - `ATTESTATION_KEY_PATH`
  - `ATTESTATION_CERT_THUMBPRINT`
  - `ATTESTATION_TIMESTAMP_URL`
  - `SHIELD_ENABLED`
- Suggested work:
  1. Add FastAPI router around `signing_service`.
  2. Require admin or service token.
  3. Connect to release workflow or bundle artifacts.
- Commit sequence:
  - `feat(security): add attestation router and config keys`
  - `feat(security): wire shield/attestation into release path`

### P3 — Observability / telemetry hooks
- File target: `app/services/observability_service.py`, `app/core/event_bus.py`
- Endpoint target: `GET /api/observability/metrics`
- Config keys:
  - `OBSERVABILITY_ENABLED`
  - `METRICS_PORT`
- Suggested work:
  1. Emit mesh latency, rerank latency, auth failure counts, and signing operation outcomes.
- Commit sequence:
  - `feat(observability): add mesh/auth/rag/signing telemetry events`

### P4 — Repo-wide hygiene
- File target: `app/core/config.py`
- Suggested work:
  1. Centralize node identity resolution instead of scattered validators.
  2. Add `app/core/config.py` fields for SSO, rerank, mesh, and signing.
- Commit sequence:
  - `refactor(config): consolidate mesh/sso/signing config fields`

## Recommended Commit Sequence (high level)
1. `feat(auth): add SSO_OIDC_* config and OIDC discovery`
2. `feat(auth): implement sso/login token exchange`
3. `feat(auth): unify /me and claims schema`
4. `feat(mesh): add MESH_NODE_* config and route strategy`
5. `feat(mesh): consume forensics latency in mesh_router`
6. `feat(rag): add RAG_RERANK_* config and backend selection`
7. `fix(rag): use configurable Chroma embedding model`
8. `feat(rag): expose rerank provenance in query response`
9. `feat(security): add attestation router and config keys`
10. `feat(security): wire shield/attestation into release path`
11. `feat(observability): add mesh/auth/rag/signing telemetry`
12. `refactor(config): consolidate mesh/sso/signing config fields`

## Evidence Basis
- `app/routers/sso.py:40-64` — returns 501 with `OIDC token exchange not yet wired`
- `app/routers/rag.py:69-119` — `_rerank_results()` hardcodes `bge-m3` over Ollama
- `app/inference/mesh_router.py:54-93` — `discover_mesh_nodes()` uses inline node list and `/healthz` only
- `app/services/signing_service.py:24-53` — signing helpers exist but no HTTP exposure
- `app/routers/users.py:76-81` — lockout/refresh constants exist, but no SSO unification
- `app/core/config.py:186-206` — Chroma/Eden config keys exist, SSO/signing/mesh config is partial or missing
