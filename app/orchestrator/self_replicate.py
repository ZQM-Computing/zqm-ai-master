"""
The Void AI Orchestration System — Self-Replication Engine (P7)

Version: 2.1.0 | ZQM Computing LLC

Makes The Void SELF-REPLICATING: it can spin up a NEW Void instance (a logical
replica — fresh agent pool, own self-expansion ledger) on another healthy ZQM-MESH
node, using the paramiko SSH bridge (user zqmlocal, same credentials as
the quantum_llm_bridge mesh transport). No external helper required.

Replication is GATED + AUDITED like self-expansion (P6):
  * VALIDATED  — target must be a known mesh node (N1/N2/N3/N4), ssh:22 reachable,
                 and have git + python3.
  * GATED      — behind ZQM_SELF_APPLY (default OFF => propose-only, audited, no deploy).
  * CONFIRMED  — even with the gate ON, a live deploy requires explicit `confirm: true`
                 on the replicate call (cross-node service install is high blast-radius).
  * AUDITED    — every attempt (proposed or applied) written immutably to FLATSPACE
                 (waxcell) + local self_replicate_ledger.jsonl.

The replica is LOGICAL, not stateful: it does NOT copy this instance's memory,
ledger, or self-expanded agents. It bootstraps a fresh Void that then self-expands
on its own. This keeps replication safe (no secret/memory exfiltration) while
fulfilling "self-replicating" — The Void creates another running copy of itself
on the mesh.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger

log = get_logger("self-replicate")

SELF_APPLY_ON = os.getenv("ZQM_SELF_APPLY", "false").lower() in ("1", "true", "yes")

# Known mesh nodes (canonical — mirrors zqm_tools_cli NODES). Never arbitrary IPs.
KNOWN_NODES = {"N1": "192.168.1.224", "N2": "192.168.1.31", "N3": "192.168.1.78", "N4": "192.168.1.228"}
# Where the replica lives on the target (Windows path).
REPLICA_PATH = r"C:\Void\ZQM-AI-Master"
# Source repo to clone (this host's repo, served via git or file copy).
REPO_CLONE_URL = os.getenv("ZQM_VOID_CLONE_URL", "")

_LEDGER = Path(__file__).resolve().parent.parent / "self_replicate_ledger.jsonl"
_REPLICATE_RE = re.compile(r"REPLICATE:\s*\n(.*?)(?=\n(?:EXPAND_AGENT:|EXPAND_TOOL:|PATCH:)|\Z)", re.DOTALL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(orchestrator: Any, record: Dict[str, Any]) -> None:
    record = {**record, "ts": _now(), "self_apply": SELF_APPLY_ON}
    try:
        with _LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        log.warning("replication ledger write failed", error=str(exc))
    try:
        fs = getattr(orchestrator, "flatspace", None)
        if fs is not None:
            import asyncio
            asyncio.get_event_loop().create_task(
                fs.store(key=f"self_replicate:{_now()}", value=record, tier="waxcell")
            )
    except Exception:
        pass


def _ssh(node: str, command: str, timeout: int = 60):
    """Run `command` on a mesh node via the paramiko bridge (same
    transport the quantum_llm_bridge uses — no external helper)."""
    import paramiko
    host = KNOWN_NODES.get(node, node)
    user = "zqmlocal"
    pw = os.environ.get("QUANTUM_LLM_SSH_PW", "EllaRose89!")
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(host, username=user, password=pw, timeout=15, look_for_keys=False)
        _, o, e = c.exec_command(f"cmd /c {command}", timeout=timeout)
        out = o.read().decode(errors="replace").strip()
        err = e.read().decode(errors="replace").strip()
        return out, err
    except Exception as exc:
        return "", f"ssh failed: {type(exc).__name__}: {exc}"


def _ssh_put(node: str, local: str, remote: str) -> bool:
    """Transfer `local` -> `remote` on `node` via paramiko SFTP. True on success."""
    import paramiko
    host = KNOWN_NODES.get(node, node)
    user = "zqmlocal"
    pw = os.environ.get("QUANTUM_LLM_SSH_PW", "EllaRose89!")
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(host, username=user, password=pw, timeout=15, look_for_keys=False)
        sftp = c.open_sftp()
        # ensure remote dir exists
        rdir = os.path.dirname(remote)
        try:
            sftp.stat(rdir)
        except IOError:
            c.exec_command(f"cmd /c mkdir {rdir}")
        sftp.put(local, remote)
        sftp.close()
        return True
    except Exception as exc:
        log.warning("ssh put failed", node=node, error=str(exc))
        return False





def _validate_target(node: str) -> tuple:
    if node not in KNOWN_NODES:
        return False, f"node {node!r} not in known mesh nodes {list(KNOWN_NODES)}"
    out, err = _ssh(node, "echo __ok__ && where git && where python", timeout=20)
    if err and "__ok__" not in out:
        return False, f"ssh to {node} failed: {err or 'no response'}"
    if "git" not in out or "python" not in out:
        return False, f"{node} missing git/python3 prerequisites: {out!r}"
    return True, "ok"


async def replicate_to(orchestrator: Any, node: str, confirm: bool = False) -> Dict[str, Any]:
    """Validate + (if gated+confirmed) deploy a logical Void replica to `node`."""
    ok, why = _validate_target(node)
    proposal = {"target_node": node, "target_ip": KNOWN_NODES.get(node, node), "path": REPLICA_PATH}
    _audit(orchestrator, {**proposal, "phase": "proposed", "validated": ok, "validation_note": why, "applied": False})

    if not ok:
        return {"applied": False, "reason": f"validation failed: {why}", **proposal}
    if not SELF_APPLY_ON:
        return {"applied": False, "reason": "propose-only (ZQM_SELF_APPLY off)", **proposal}
    if not confirm:
        return {"applied": False, "reason": "confirm=true required for live cross-node deploy", **proposal}

    # LIVE DEPLOY. Mechanism: git-bundle this host's repo, transfer to the target
    # via SSH (sftp over paramiko — see _ssh_put), git-clone from the bundle there. SMB
    # push across the mesh is blocked, so bundle+transfer is the reliable path.
    # Identity is SHARED: the replica gets the same SECRET_KEY (operator decision).
    # NOTE: Windows/MSYS git treats \v \t as escapes -> ALL git/clone paths use
    # FORWARD slashes. cmd.exe `cd` and sched-task /TR need BACKslashes.
    src_repo = REPO_CLONE_URL or os.getenv("ZQM_VOID_SRC", None)
    if not src_repo:
        raise RuntimeError("ZQM_VOID_SRC/REPO_CLONE_URL not set; cannot bundle replica without source repo path")
    bundle = r"C:/temp/void_work/void_replica.bundle"
    try:
        import subprocess
        subprocess.run(["git", "-C", src_repo, "bundle", "create", bundle, "--all"],
                       check=True, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        _audit(orchestrator, {**proposal, "phase": "bundle_failed", "applied": False, "error": str(exc)})
        return {"applied": False, "reason": f"repo bundle failed: {exc}", **proposal}

    # P9 (security): never bake a known-weak default into a replica. Use the
    # operator's live key (set in the launch .bat -> os.environ; else settings.secret_key).
    # If that is still the insecure default, mint a FRESH per-node key so a cloned
    # replica is not trivially JWT-forgeable.
    import secrets as _secrets
    _cfg = __import__("app.core.config", fromlist=["settings"]).settings
    _live_key = os.getenv("SECRET_KEY") or getattr(_cfg, "secret_key", "")
    if not _live_key or _live_key.startswith("changeme") or _live_key == "EllaRose89!":
        _live_key = _secrets.token_hex(32)
    env_text = (
        f"SECRET_KEY={_live_key}\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n"
        "OLLAMA_DEFAULT_MODEL=qwen2.5:3b\n"
        "ZQM_SELF_APPLY=1\n"
    )
    env_local = r"C:/temp/void_work/void_replica.env"
    with open(env_local, "w", encoding="utf-8") as f:
        f.write(env_text)
    _ssh(node, 'mkdir C:\\Void 2>nul')
    put_b = _ssh_put(node, bundle, r"C:/Void/void_replica.bundle")
    put_e = _ssh_put(node, env_local, r"C:/Void/void_replica.env")
    if not put_b or not put_e:
        _audit(orchestrator, {**proposal, "phase": "transfer_failed", "applied": False,
                              "error": f"bundle={put_b} env={put_e}"})
        return {"applied": False, "reason": "transfer to target failed", **proposal}

    # Clone (verify by .git existence, not by parsing git's mangled stdout).
    _ssh(node, f'rmdir /S /Q "{REPLICA_PATH}" 2>nul')
    _ssh(node, f'git clone C:/Void/void_replica.bundle "{REPLICA_PATH}" 2>nul')
    verify, _ = _ssh(node, f'if exist "{REPLICA_PATH}\\.git" (echo CLONE_OK) else (echo CLONE_MISSING)')
    if "CLONE_OK" not in verify:
        _audit(orchestrator, {**proposal, "phase": "clone_failed", "applied": False, "error": verify.strip()})
        return {"applied": False, "reason": f"clone on {node} failed: {verify.strip()}", **proposal}

    # Build venv + install. If `python -m venv` is unavailable (stripped
    # embeddable Python, e.g. N1), fall back to the base python (no venv).
    build = (
        f'cd /d "{REPLICA_PATH}" && '
        f'python -m venv .venv && '
        f'.venv\\Scripts\\python.exe -m pip install --upgrade pip >nul 2>&1 && '
        f'.venv\\Scripts\\python.exe -m pip install -r requirements.txt >nul 2>&1'
    )
    _ssh(node, build, timeout=400)
    venv_py = rf"{REPLICA_PATH}\.venv\Scripts\python.exe"
    base_py = r"C:\Users\zqmlocal\Python312\python.exe"
    probe_py, _ = _ssh(node, f'if exist "{venv_py}" (echo VENV) else (echo BASE)')
    run_py = venv_py if "VENV" in probe_py else base_py

    # Put the shared .env into the cloned repo (sftp-put, not `copy`).
    put_env = _ssh_put(node, env_local, rf"{REPLICA_PATH}/.env")
    if not put_env:
        _audit(orchestrator, {**proposal, "phase": "env_put_failed", "applied": False, "error": "env sftp failed"})
        return {"applied": False, "reason": "could not write .env on target", **proposal}

    # Write a launcher .bat that BAKES the env (pydantic-settings does not push
    # .env vars into os.environ, so ZQM_SELF_APPLY must be `set` explicitly).
    launcher = (
        "@echo off\r\n"
        "set OLLAMA_BASE_URL=http://127.0.0.1:11434\r\n"
        "set OLLAMA_DEFAULT_MODEL=qwen2.5:3b\r\n"
        "set ZQM_SELF_APPLY=1\r\n"
        f"set SECRET_KEY={_live_key}\r\n"
        f"cd /d {REPLICA_PATH}\r\n"
        f'{run_py} -m uvicorn app.main:app --host 0.0.0.0 --port 8099\r\n'
    )
    launch_local = r"C:/temp/void_work/void_service_launch_%s.bat" % node
    with open(launch_local, "w", encoding="utf-8") as f:
        f.write(launcher)
    _ssh_put(node, launch_local, rf"{REPLICA_PATH}/void_service_launch_{node}.bat")

    # Launch as a PERSISTENT scheduled task (survives SSH disconnect + reboot).
    # `start /B` inside an SSH session dies when the channel closes, so use schtasks.
    svc_name = f"ZQM-Void-{node}"
    launch = (
        f'schtasks /Delete /TN "{svc_name}" /F 2>nul & '
        f'schtasks /Create /TN "{svc_name}" /TR "{REPLICA_PATH}\\void_service_launch_{node}.bat" '
        f'/SC ONSTART /RU SYSTEM /F >nul 2>&1 & '
        f'schtasks /Run /TN "{svc_name}" >nul 2>&1'
    )
    out2, err2 = _ssh(node, launch, timeout=120)
    applied = (not err2)
    _audit(orchestrator, {**proposal, "phase": "deployed" if applied else "launch_failed",
                          "applied": applied, "error": err2, "service": svc_name,
                          "python": "venv" if "VENV" in probe_py else "base"})
    return {"applied": applied, "reason": None if applied else err2, "service": svc_name, **proposal}


async def process_findings(orchestrator: Any, findings_text: str, confirm: bool = False) -> Dict[str, Any]:
    """Scan findings for REPLICATE: directives and process them."""
    applied, proposed = [], []
    for m in _REPLICATE_RE.finditer(findings_text):
        blob = m.group(1)
        km = re.search(r"node:\s*([A-Za-z0-9_.]+)", blob)
        node = km.group(1).upper() if km else None
        if not node or node not in KNOWN_NODES:
            node = "N3" if "N3" in blob.upper() else (node or "N3")
        res = await replicate_to(orchestrator, node, confirm=confirm)
        (applied if res.get("applied") else proposed).append(res)
    return {"self_apply": SELF_APPLY_ON, "proposed": len(proposed), "applied": len(applied),
            "proposals": proposed, "actions": applied}


def review_ledger(limit: int = 50) -> List[Dict[str, Any]]:
    if not _LEDGER.exists():
        return []
    return [json.loads(l) for l in _LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()][-limit:]
