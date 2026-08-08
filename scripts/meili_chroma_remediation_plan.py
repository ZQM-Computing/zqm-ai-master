"""
Remediation plan + executable commands for the Meilisearch/Chroma indexing gap.

Findings:
- Meilisearch is running at 127.0.0.1:7701, but `.env` contains an invalid
  `MEILISEARCH_MASTER_KEY`, so indexing/search is failing auth.
- Local SQLite truth: `C:\\Void\\ZQM-AI-Master\app\flatspace_local.db` has 923 records.
- Meilisearch currently only has 200 docs.
- Chroma is configured in code but `chroma_enabled=False` by default and no
  Chroma service is reachable at 127.0.0.1:8001.
- RAG path already falls back correctly: local embedding search -> Meilisearch
  full-text -> Chroma vector -> remote API -> local substring fallback.

Remediation:
1) Make Meilisearch auth consistent.
2) Reindex local SQLite into Meilisearch `flatspace` index.
3) Verify counts match and RAG hits expected records.
4) Optional Chroma path if you want to deploy it.

EXACT COMMANDS:
1. Inspect local SQLite truth:
   python - <<'PY'
   import sqlite3, os
   p=r'C:\\Void\\ZQM-AI-Master\app\flatspace_local.db'
   print('exists', os.path.exists(p))
   if os.path.exists(p):
       c=sqlite3.connect(p)
       print('total', c.execute('select count(*) from flatspace').fetchone()[0])
       print('tiers', c.execute('select tier, count(*) from flatspace group by tier').fetchall())
       c.close()
   PY

2. Confirm Meilisearch is reachable:
   curl -s http://127.0.0.1:7701/health
   curl -s http://127.0.0.1:7701/healthz || true

3. Option A - Use existing master key if known:
   - If you have the real key, edit `C:\\Void\\ZQM-AI-Master\\.env`:
       MEILISEARCH_MASTER_KEY=<existing_valid_key>
   - Verify:
       curl -s http://127.0.0.1:7701/indexes -H "Authorization: Bearer <key>" -H "Content-Type: application/json"

3. Option B - Reset Meilisearch master key to match `.env`:
   # Get current Meilisearch env/config from its process or logs, then:
   curl -X POST http://127.0.0.1:7701/meilisearch/v1/master-key \
     -H "Content-Type: application/json" \
     -d '{"masterKey":"<new_key>"}'
   # Then set the same value in `.env`:
   #   MEILISEARCH_MASTER_KEY=<new_key>

4. Reindex into Meilisearch:
   cd C:\\Void\\ZQM-AI-Master
   python scripts/sync_meili.py
   # or with explicit env:
   set MEILISEARCH_URL=http://127.0.0.1:7701
   set MEILISEARCH_MASTER_KEY=<key>
   python scripts/sync_meili.py

5. Verify post-reindex counts:
   curl -s http://127.0.0.1:7701/indexes/flatspace/stats \
     -H "Authorization: Bearer <key>" -H "Content-Type: application/json"

6. Verify RAG path:
   curl -s -X POST http://127.0.0.1:8808/api/rag/query \
     -H "Authorization: Bearer <jwt>" \
     -H "Content-Type: application/json" \
     -d "{\"query\":\"quantum simulation flatspace\",\"tier\":\"bitgarden\",\"limit\":5}"

CHROMA FALLBACK:
- If Chroma is not deployed: Meilisearch is sufficient for full-text fallback.
- If deploying Chroma later:
   1. Start Chroma on 127.0.0.1:8001.
   2. Set in `.env`:
        CHROMA_URL=http://127.0.0.1:8001
        CHROMA_COLLECTION=flatspace
        CHROMA_ENABLED=true
   3. Verify:
        curl -s http://127.0.0.1:8001/api/v1/heartbeat
   4. Reindex docs into Chroma if desired.
"""
from __future__ import annotations

if __name__ == "__main__":
    print(__doc__)
