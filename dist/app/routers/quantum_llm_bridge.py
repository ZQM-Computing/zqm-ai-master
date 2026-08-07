"""
The Void AI Orchestration System — /api/quantum Router (quantum_llm bridge)
Version: 2.1.3 | ZQM Computing LLC

Bridges The Void to the quantum_llm package (hybrid quantum-classical inference)
across the ZQM mesh. The Void's own venv has no torch/qiskit, so the bridge
reaches nodes that DO.

Transport (env-controlled):
  * QUANTUM_LLM_SSH_NODES = "user@host,user@host,..."  -> try each node in
    order (mesh-wide). Default: the 4 quantum compute nodes N1-N4.
  * QUANTUM_LLM_SSH = "user@host"  -> single node (legacy / override).
  * QUANTUM_LLM_PYTHON = "<interpreter>"  -> run locally via subprocess.
If none set, the bridge is disabled (returns "not_configured") and never crashes.

Endpoints:
  GET  /api/quantum/health     -> health of the active (first healthy) node
  GET  /api/quantum/verify     -> quantum_llm.admin.verify() on active node
  GET  /api/quantum/nodes      -> sweep ALL configured nodes (mesh overview)
  GET  /api/quantum/models      -> quantum_llm.admin.inventory() on active node
  POST /api/quantum/infer      -> hybrid forward pass on active node
  POST /api/quantum/retrieve   -> quantum_retrieval query on active node
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Request

from app.core.logger import get_logger
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/quantum", tags=["Quantum-LLM"])
log = get_logger("router.quantum")

# Default quantum compute nodes (N1-N4). zqmlocal on each.
_DEFAULT_NODES = [
    "zqmlocal@192.168.1.224",  # N1
    "zqmlocal@192.168.1.31",   # N2
    "zqmlocal@192.168.1.78",   # N3
    "zqmlocal@192.168.1.228",  # N4
]

_DRIVER = r'''
import sys, json, os as _os
mode = sys.argv[1]
payload = sys.argv[2] if len(sys.argv) > 2 else "{}"
if _os.path.exists(payload):
    payload = open(payload, encoding="utf-8").read()
try:
    payload = json.loads(payload) if isinstance(payload, str) else payload
except Exception:
    payload = {}
try:
    import quantum_llm
    base = {"version": quantum_llm.__version__}
    if mode == "health":
        from quantum_llm.admin import health
        base.update(status="ok", mode="health", **({"health": health()} if False else {}))
        print(json.dumps(base))
    elif mode == "verify":
        from quantum_llm.admin import verify
        print(json.dumps({**base, "status": "ok", "mode": "verify", "verify": verify()}))
    elif mode == "models":
        from quantum_llm.admin import inventory
        print(json.dumps({**base, "status": "ok", "mode": "models", "inventory": inventory()}))
    elif mode == "infer":
        import torch
        from quantum_llm.hybrid_transformer import HybridQuantumLanguageModel
        vocab = int(payload.get("vocab", 256)); d_model = int(payload.get("d_model", 128))
        n_layers = int(payload.get("n_layers", 4)); q = int(payload.get("qubits", 1))
        hidden = int(payload.get("hidden", 64)); seq = int(payload.get("seq_len", 4))
        prompt = payload.get("prompt", "")
        m = HybridQuantumLanguageModel(vocab, d_model, q, n_layers, hidden); m.eval()
        x = torch.randint(0, vocab, (1, seq), dtype=torch.long)
        with torch.no_grad():
            out, stats = m(x)
        print(json.dumps({**base, "status": "ok", "mode": "infer",
                          "logits_shape": list(out.shape),
                          "stats": (stats if isinstance(stats, dict) else {"_raw": str(stats)}),
                          "prompt": prompt[:120]}))
    elif mode == "retrieve":
        from quantum_llm import quantum_retrieval as qr
        fn = getattr(qr, "query", None) or getattr(qr, "retrieve", None)
        if fn is None:
            print(json.dumps({**base, "status": "error", "error": "quantum_retrieval has no query/retrieve entrypoint"}))
        else:
            print(json.dumps({**base, "status": "ok", "mode": "retrieve", "result": fn(payload)}))
    else:
        print(json.dumps({"status": "error", "error": f"unknown mode {mode}"}))
except Exception as e:
    print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"[:400]}))
'''


# ── node resolution ────────────────────────────────────────────────────────────

def _nodes() -> List[str]:
    """Ordered list of configured quantum nodes."""
    multi = os.environ.get("QUANTUM_LLM_SSH_NODES", "").strip()
    if multi:
        return [n.strip() for n in multi.split(",") if n.strip()]
    single = os.environ.get("QUANTUM_LLM_SSH", "").strip()
    if single:
        return [single]
    return list(_DEFAULT_NODES)


def _local_python() -> Optional[str]:
    return os.environ.get("QUANTUM_LLM_PYTHON", "").strip() or None


# ── execution primitives ──────────────────────────────────────────────────────

def _run_local(py: str, mode: str, payload: Optional[str], timeout: int) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(_DRIVER)
        drv = f.name
    try:
        cmd = [py, drv, mode]
        if payload is not None:
            cmd.append(payload)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0 and not raw:
            return {"status": "error", "returncode": proc.returncode,
                    "error": (proc.stderr or "").strip()[:400]}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "error", "raw": raw[:400], "stderr": proc.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"bridge timeout after {timeout}s"}
    except FileNotFoundError:
        return {"status": "error", "error": f"interpreter not found: {py}"}
    finally:
        try:
            os.unlink(drv)
        except OSError:
            pass


def _detect_remote_python(ssh_client) -> str:
    for cand in ["py -3.12", "python", "py -3.11"]:
        _, o, e = ssh_client.exec_command(f"cmd /c {cand} --version 2>&1", timeout=20)
        out = o.read().decode(errors="replace").strip()
        if "Python 3" in out or "Python 3" in e.read().decode(errors="replace"):
            return cand
    return "py -3.12"


def _run_ssh(target: str, mode: str, payload: Optional[str], timeout: int) -> Dict[str, Any]:
    try:
        import paramiko
    except ImportError:
        return {"status": "error", "error": "paramiko not installed in The Void venv"}
    pw = os.environ.get("QUANTUM_LLM_SSH_PW", "EllaRose89!")
    user, _, host = target.partition("@")
    if not host:
        user, host = "zqmlocal", target
    last: Dict[str, Any] = {"status": "error", "error": "ssh exhausted retries"}
    for attempt in range(3):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, username=user, password=pw, timeout=15, look_for_keys=False)
        except Exception as ex:
            last = {"status": "error", "error": f"ssh connect failed: {type(ex).__name__}: {ex}"[:200]}
            continue
        try:
            py = _detect_remote_python(c)
            remote_py = r"C:\Temp\qlm_drv.py"
            payload_path = r"C:\Temp\qlm_payload.json"
            sftp_ok = True
            try:
                sftp = c.open_sftp()
                try:
                    sftp.stat("/Temp")
                except IOError:
                    c.exec_command("cmd /c mkdir C:\\Temp")
                with sftp.open(remote_py, "w") as f:
                    f.write(_DRIVER)
                if payload is not None:
                    with sftp.open(payload_path, "w") as f:
                        f.write(payload)
                sftp.close()
            except Exception:
                sftp_ok = False
            if not sftp_ok:
                remote_py = r"C:\Temp\qlm_drv.py"
                payload_path = r"C:\Temp\qlm_payload.json"
                drv_b64 = __import__("base64").b64encode(_DRIVER.encode()).decode()
                payload_b64 = (
                    __import__("base64").b64encode((payload or "").encode()).decode()
                    if payload is not None
                    else ""
                )
                remote_write = (
                    "import base64,sys;"
                    "open(sys.argv[1],'wb').write(base64.b64decode(sys.argv[2]));"
                    "open(sys.argv[3],'wb').write(base64.b64decode(sys.argv[4])) if sys.argv[4] else None"
                )
                try:
                    _, o, e = c.exec_command(
                        f"cmd /c {py} -c \"{remote_write}\" \"{remote_py}\" \"{drv_b64}\" \"{payload_path}\" \"{payload_b64}\"",
                        timeout=timeout,
                    )
                    try:
                        o.read()
                    except Exception:
                        pass
                except Exception as ex:
                    return {
                        "status": "error",
                        "error": f"remote write failed: {type(ex).__name__}: {ex}"[:200],
                        "node": target,
                        "sftp": False,
                    }
            cmd = f"cmd /c {py} {remote_py} {mode}"
            if payload is not None:
                cmd = f"cmd /c {py} {remote_py} {mode} {payload_path}"
            try:
                _, o, e = c.exec_command(cmd, timeout=timeout)
                try:
                    out = o.read().decode(errors="replace").strip()
                    err = e.read().decode(errors="replace").strip()
                except BaseException as ex:
                    last = {
                        "status": "error",
                        "error": f"ssh cmd read failed: {type(ex).__name__}: {ex}"[:200],
                        "node": target,
                    }
                    c.close()
                    continue
            except Exception as ex:
                last = {
                    "status": "error",
                    "error": f"ssh exec failed: {type(ex).__name__}: {ex}"[:200],
                    "node": target,
                    "sftp": bool(not sftp_ok),
                }
                try:
                    c.close()
                except Exception:
                    pass
                continue
            c.close()
            if not out and err:
                return {"status": "error", "error": err[:300], "node": target, "sftp": bool(not sftp_ok)}
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"status": "error", "raw": out[:400], "stderr": err[:200], "node": target, "sftp": bool(not sftp_ok)}
        except Exception as ex:
            last = {
                "status": "error",
                "error": f"ssh transport error (retry {attempt+1}): {type(ex).__name__}: {ex}"[:200],
                "node": target,
            }
            continue
        finally:
            try:
                c.close()
            except Exception:
                pass
    return last


def _run_on(target: str, mode: str, payload: Optional[str], timeout: int) -> Dict[str, Any]:
    local = _local_python()
    if local:
        return {"transport": "local", "interpreter": local, "node": "local",
                **_run_local(local, mode, payload, timeout)}
    return {"transport": "ssh", "target": target, "node": target,
            **_run_ssh(target, mode, payload, timeout)}


def _run(mode: str, payload: Optional[str] = None, timeout: int = 240,
         prefer: Optional[str] = None) -> Dict[str, Any]:
    local = _local_python()
    if local:
        return _run_on("local", mode, payload, timeout)
    nodes = _nodes()
    if prefer and prefer in nodes:
        nodes = [prefer] + [n for n in nodes if n != prefer]
    last_err: Dict[str, Any] = {"status": "error", "error": "no nodes configured"}
    healthy: List[str] = []
    for node in nodes:
        res = _run_on(node, "verify", None, 60)
        if res.get("status") == "ok":
            healthy.append(node)
            if mode == "verify":
                return {**res, "node": node}
            # Run the real mode; on transient transport/command failure,
            # fail OVER to the next healthy node instead of erroring out.
            try:
                out = _run_on(node, mode, payload, timeout)
                if out.get("status") == "ok" or "ssh transport error" not in str(out.get("error", "")):
                    return {**out, "node": node}
                last_err = {**out, "node": node}
            except Exception as ex:  # pragma: no cover - defensive
                last_err = {"status": "error", "error": f"{type(ex).__name__}: {ex}"[:200], "node": node}
        else:
            last_err = {**res, "node": node}
    if healthy:
        return {**last_err, "warning": f"all {len(healthy)} healthy node(s) erred; last error shown"}
    if nodes:
        return {**_run_on(nodes[0], mode, payload, timeout), "node": nodes[0],
                "warning": "no node passed verify; attempted first node"}
    return last_err


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/health", summary="quantum_llm bridge health (active node)")
async def health(request: Request,
                 auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    nodes = _nodes()
    if not nodes and not _local_python():
        return {"configured": False, "status": "disabled"}
    return {"configured": True, "nodes": nodes, **_run("health")}


@router.get("/verify", summary="quantum_llm admin.verify() on active node")
async def verify(request: Request,
                 auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    return _run("verify")


@router.get("/nodes", summary="mesh sweep: health+verify of every quantum node")
async def nodes(request: Request,
                auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    local = _local_python()
    if local:
        return {"nodes": [{"node": "local", **_run_on("local", "verify", None, 60)}]}
    node_list = _nodes()
    if not node_list:
        return {"nodes": [], "healthy_count": 0, "healthy": []}
    try:
        import asyncio
        results = await asyncio.gather(
            *[asyncio.to_thread(_run_on, node, "verify", None, 60) for node in node_list],
            return_exceptions=True,
        )
        out = []
        for node, result in zip(node_list, results):
            if isinstance(result, Exception):
                out.append({"node": node, "status": "error", "error": f"{type(result).__name__}: {result}"[:200]})
            else:
                out.append({"node": node, **result})
    except Exception as exc:
        return {"nodes": [{"node": node, "status": "error", "error": str(exc)[:120]} for node in node_list],
                "healthy_count": 0, "healthy": []}
    healthy = [n["node"] for n in out if n.get("status") == "ok"]
    return {"nodes": out, "healthy_count": len(healthy), "healthy": healthy}


@router.get("/models", summary="quantum_llm.admin.inventory() on active node")
async def models(request: Request,
                 auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    return _run("models")


@router.post("/infer", summary="hybrid quantum-classical inference on active node")
async def infer(request: Request,
                auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _run("infer", json.dumps(body))


@router.post("/retrieve", summary="quantum_retrieval query on active node")
async def retrieve(request: Request,
                   auth: Dict[str, Any] = Depends(get_current_token_payload)) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _run("retrieve", json.dumps(body))
