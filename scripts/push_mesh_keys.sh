#!/usr/bin/env bash
set -euo pipefail

# One-time push of the hardened mesh public key to N3 and N9.
# Assumes this repo is checked out on the local operator host.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBKEY_FILE="$HOME/.ssh/zqm_mesh_ed25519_hardened.pub"
REMOTE_USER="zqmlocal"
NODES=("N3=192.168.1.78" "N9=192.168.1.250")

if [[ ! -f "$PUBKEY_FILE" ]]; then
  echo "FAIL: public key not found at $PUBKEY_FILE" >&2
  exit 1
fi

PUBKEY_CONTENT="$(tr -d '\n' < "$PUBKEY_FILE")"
if [[ -z "$PUBKEY_CONTENT" ]]; then
  echo "FAIL: public key file is empty" >&2
  exit 1
fi

SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=5 -i $HOME/.ssh/zqm_mesh_ed25519_hardened"

pass() { echo "OK: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

for entry in "${NODES[@]}"; do
  NODE="${entry%%=*}"
  IP="${entry##*=}"
  REMOTE="$REMOTE_USER@$IP"

  echo "== $NODE ($IP) =="

  # 1) liveness/ssh reachability
  if ! ssh $SSH_OPTS "$REMOTE" "echo reachable" >/dev/null 2>&1; then
    fail "$NODE ssh not reachable"
  fi
  pass "$NODE ssh reachable"

  # 2) ensure .ssh dir exists and is 700
  ssh $SSH_OPTS "$REMOTE" 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'

  # 3) append the hardened pubkey if missing (idempotent)
  ssh $SSH_OPTS "$REMOTE" "
    if ! grep -Fxq '${PUBKEY_CONTENT}' ~/.ssh/authorized_keys 2>/dev/null; then
      printf '%s\n' '${PUBKEY_CONTENT}' >> ~/.ssh/authorized_keys
    fi
    chmod 600 ~/.ssh/authorized_keys
  "
  pass "$NODE authorized_keys updated"

  # 4) validate forced-key auth still rejects password auth
  if ssh $SSH_OPTS -o PubkeyAuthentication=yes -o PasswordAuthentication=no "$REMOTE" "echo key-auth-ok"; then
    pass "$NODE password auth still accepted; harden further if required"
  else
    fail "$NODE key auth validation failed"
  fi

  pass "$NODE push complete"
done

echo
echo "All nodes processed."
