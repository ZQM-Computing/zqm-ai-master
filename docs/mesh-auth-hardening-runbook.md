# Mesh Auth Hardening Runbook
*Scope: local operator execution only. Do not modify `.env` or restart ZQM-Void-N4/NSSM.*

## Prerequisites
- OpenSSH client available on Windows PATH (`ssh`, `ssh-keyscan`)
- Git Bash or WSL for shell scripts, PowerShell for `.ps1`
- Hardened key already generated: `C:\Users\zqmco\.ssh\zqm_mesh_ed25519_hardened.pub`

## Step 0 — Verify canonical IP map
**File:** `C:\Void\ZQM-AI-Master\mesh_connect.py`
**Current map:**
```
N1 = 192.168.1.224
N2 = 192.168.1.196
N3 = 192.168.1.78
N4 = 192.168.1.228
N9 = 192.168.1.250
```
Status: Already matches target map. No patch needed.

## Step 1 — Fix known_hosts (one-time, Windows-safe)
Run from an elevated/standard PowerShell session:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Bypass -Force
powershell -ExecutionPolicy Bypass -File C:\Void\ZQM-AI-Master\scripts\fix_mesh_known_hosts.ps1
```

**Success criteria:**
- Output shows `Removed X stale entry/entries for '192.168.1.78'` and same for `.250`
- Output shows `Added fresh ed25519 host key for 192.168.1.78` and same for `.250`
- No exception is thrown
- Verify manually: `ssh-keygen -F 192.168.1.78` and `ssh-keygen -F 192.168.1.250` should return a matching host key block

## Step 2 — Push hardened mesh key to N3 and N9
Run from Git Bash / WSL:
```bash
bash C:/Void/ZQM-AI-Master/scripts/push_mesh_keys.sh
```

**Success criteria:**
- Both nodes print: `OK: <node> ssh reachable`
- Both nodes print: `OK: <node> authorized_keys updated`
- Both nodes print: `OK: <node> push complete`
- Script exits zero with final line: `All nodes processed.`
- If validation says `password auth still accepted`, note it and harden sshd_config on the node manually:
  ```bash
  ssh zqmlocal@<ip> "sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl reload sshd"
  ```

## Step 3 — Post-push validation
From operator host, run these checks:
```bash
ssh -o BatchMode=yes zqmlocal@192.168.1.78 'echo N3-ok'
ssh -o BatchMode=yes zqmlocal@192.168.1.250 'echo N9-ok'
ssh-keygen -F 192.168.1.78 | grep -q ed25519 && echo N3-hostkey-ok || echo N3-hostkey-missing
ssh-keygen -F 192.168.1.250 | grep -q ed25519 && echo N9-hostkey-ok || echo N9-hostkey-missing
```

**Final acceptance criteria:**
- All four checks print `*ok`
- No password prompts or auth failures in output
- No changes to `.env`, no service restarts, no remote node reboots

## Rollback / emergency notes
- If the push script fails halfway, remove the key from `authorized_keys` and re-run after troubleshooting.
- If known_hosts ends up corrupted, restore from `known_hosts.old` or regenerate via `ssh-keyscan` for all nodes.
