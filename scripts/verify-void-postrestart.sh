#!/usr/bin/env bash
# verify-void-postrestart.sh
# Run AFTER:  nssm restart "ZQM-Void-N4"   (Admin)
# Proves the hot-patch is live: status healthy, quantum verify works, agent mesh runs.
#
# FIX (2026-08-19): the token is now actually sent. Previous version read the
# token from .env into $TOKEN but then transmitted the literal string "***" in
# every -H header, so every call 401'd. Now $TOKEN is used, and only its
# LENGTH is printed (value never hits logs).
set -u
cd "$(dirname "$0")/.."   # repo root

ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi
TOKEN="$(grep -E '^ZQM_OBSERVABILITY_SERVICE_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [ -z "$TOKEN" ]; then
  echo "ERROR: ZQM_OBSERVABILITY_SERVICE_KEY missing in $ENV_FILE" >&2
  exit 1
fi
echo "token length: ${#TOKEN} (32 = good)"

AUTH="-H X-API-Key:${TOKEN}"

echo
echo "=== 1) /api/status (expect HTTP 200 after restart) ==="
curl -s -m 10 -w "\nHTTP %{http_code}\n" $AUTH http://127.0.0.1:8808/api/status | head -c 1500

echo
echo "=== 2) /api/quantum/verify GET (proves load_dotenv + QUANTUM_LLM_PYTHON resolve) ==="
echo "    Pre-patch: returns 'QUANTUM_LLM_PYTHON not set'. Post-patch: 'ok':true + real tests."
curl -s -m 60 -w "\nHTTP %{http_code}\n" $AUTH http://127.0.0.1:8808/api/quantum/verify | head -c 1200

echo
echo "=== 3) /api/quantum/models (capability inventory) ==="
curl -s -m 30 -w "\nHTTP %{http_code}\n" $AUTH http://127.0.0.1:8808/api/quantum/models | head -c 800

echo
echo "=== 4) /deploy webhook -> create a task, then retrieve + check output_type ==="
RESP="$(curl -s -m 30 -X POST http://127.0.0.1:8808/api/webhook/deploy \
        -H "Content-Type: application/json" \
        -d '{"name":"post_restart_verify","objective":"ping agent mesh","plan":"ack"}')"
echo "deploy resp: $RESP" | head -c 600
TASK_ID="$(echo "$RESP" | grep -oE '"task_id":"[^"]+"' | head -1 | cut -d'"' -f4)"
echo "task_id=$TASK_ID"
if [ -n "$TASK_ID" ]; then
  sleep 4
  curl -s -m 20 $AUTH "http://127.0.0.1:8808/api/tasks/$TASK_ID" | grep -oE '"output_type":"[^"]+"' | head -1
fi

echo
echo "=== DONE — paste this output back to Hermes ==="
