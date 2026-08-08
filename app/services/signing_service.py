"""
Unified signing abstraction for ZQM attestation and shield workflows.

Supports:
- CMS/PKCS7 signing via external attestation toolkit
- Authenticode signing via PowerShell / signtool
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional


def _run(cmd: List[str], **kwargs) -> Dict[str, Any]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=kwargs.get("timeout", 60))
        return {"ok": out.returncode == 0, "stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "code": -1}


def cms_sign(file_path: str, cert_path: str, key_path: str, output_path: str) -> Dict[str, Any]:
    """Sign a file/deliverable with CMS/PKCS7 via external toolkit."""
    script = os.getenv("ZQM_CMS_SIGN_SCRIPT", "")
    if not script or not os.path.exists(script):
        return {"ok": False, "error": "ZQM_CMS_SIGN_SCRIPT not configured"}
    return _run(["python", script, "--input", file_path, "--cert", cert_path, "--key", key_path, "--out", output_path])


def authenticode_sign(file_path: str, cert_thumbprint: str, timestamp_url: str = "http://timestamp.digicert.com") -> Dict[str, Any]:
    """Sign a PE/binary with Authenticode via signtool."""
    signtool = os.getenv("ZQM_SIGNTOOL", "signtool")
    cmd = [signtool, "sign", "/sha1", cert_thumbprint, "/t", timestamp_url, file_path]
    return _run(cmd)


def sign_bundle(files: List[str], mode: str = "cms", **kwargs) -> Dict[str, Any]:
    """Sign one or more files using the requested backend."""
    results = []
    for path in files:
        if mode == "authenticode":
            res = authenticode_sign(path, **{k: v for k, v in kwargs.items() if k in ["cert_thumbprint", "timestamp_url"]})
        else:
            res = cms_sign(
                path,
                kwargs.get("cert_path", ""),
                kwargs.get("key_path", ""),
                kwargs.get("output_path", path + ".p7s"),
            )
        results.append({"file": path, **res})
    return {"mode": mode, "results": results}
