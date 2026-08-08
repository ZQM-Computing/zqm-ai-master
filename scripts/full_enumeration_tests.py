"""
Full enumerative test suite for The Void / ZQM-AI-Master.
Covers: OpenAPI schema, public endpoints, auth flow, protected endpoints,
commercial layer, mesh/probe, packaging, compile, and service state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

BASE = "http://127.0.0.1:8808"
REPO = Path(r"C:\Void\ZQM-AI-Master")
PY = r"C:\Program Files\Python312\python.exe"

# Endpoints that are POST-only
POST_ONLY = {
    "/api/rag/query",
    "/api/reasoning/query",
    "/api/void/talk",
    "/api/support/ticket",
    "/api/users/login",
}

# Mesh endpoints that do not exist in schema
MESH_BAD_PATHS = {
    "/api/mesh/nodes",
    "/api/mesh/ollama",
}


class TestSuite:
    def __init__(self) -> None:
        self.results: List[Dict[str, Any]] = []
        self.token: str | None = None

    def _record(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append({"name": name, "passed": passed, "detail": detail})
        print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")

    def run(self) -> None:
        self.test_compile()
        self.test_packaging()
        self.test_service_state()
        self.test_openapi_enumeration()
        self.test_public_endpoints()
        self.test_auth_flow()
        self.test_protected_endpoints()
        self.test_commercial_layer()
        self.test_mesh_and_probe()
        self.test_security_hardening()
        self.summary()

    def test_compile(self) -> None:
        py_files = list(REPO.glob("app/**/*.py"))
        ok = True
        bad = []
        for py in py_files:
            r = subprocess.run([PY, "-m", "py_compile", str(py)], capture_output=True, text=True)
            if r.returncode != 0:
                ok = False
                bad.append(str(py))
        self._record("py_compile_all", ok, f"files={len(py_files)} bad={len(bad)}")

    def test_packaging(self) -> None:
        dist = REPO / "dist"
        manifest = REPO / "release.manifest.toml"
        self._record("release_manifest_exists", manifest.exists(), str(manifest))
        self._record("dist_dir_exists", dist.exists(), str(dist))
        if dist.exists():
            artifacts = list(dist.rglob("*"))
            self._record("dist_artifacts_count", len(artifacts) > 0, f"count={len(artifacts)}")

    def test_service_state(self) -> None:
        try:
            r = requests.get(f"{BASE}/healthz", timeout=2)
            r.raise_for_status()
        except Exception:
            self._record("service_healthz", False, "skipped: service not running")
            self._record("service_api_healthz", False, "skipped: service not running")
            self._record("service_version", False, "skipped: service not running")
            return
        self._record("service_healthz", r.status_code == 200, f"status={r.status_code}")
        r = requests.get(f"{BASE}/api/healthz", timeout=5)
        self._record("service_api_healthz", r.status_code == 200, f"status={r.status_code}")
        r = requests.get(f"{BASE}/api/version", timeout=5)
        self._record("service_version", r.status_code == 200, f"status={r.status_code}")

    def test_openapi_enumeration(self) -> None:
        r = requests.get(f"{BASE}/openapi.json", timeout=10)
        self._record("openapi_available", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            paths = list(data.get("paths", {}).keys())
            self._record("openapi_path_count", len(paths) > 0, f"count={len(paths)}")
            self._record("support_route_in_schema", "/api/support/status" in paths, f"paths={paths[:5]}...")

    def test_public_endpoints(self) -> None:
        public = ["/healthz", "/api/healthz", "/api/version", "/docs", "/redoc", "/openapi.json"]
        for p in public:
            try:
                r = requests.get(f"{BASE}{p}", timeout=5)
                self._record(f"public_{p}", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self._record(f"public_{p}", False, f"ERROR={e}")

    def test_auth_flow(self) -> None:
        env_path = REPO / ".env"
        env = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        username = env.get("ZQM_ADMIN_USERNAME", "admin")
        password = env.get("ZQM_ADMIN_PASSWORD", "")
        if not password:
            self._record("login_with_env_password", False, "ZQM_ADMIN_PASSWORD is empty in .env")
            return
        r = requests.post(f"{BASE}/api/users/login", json={"username": username, "password": password}, timeout=5)
        self._record("login_with_env_password", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            try:
                body = r.json()
                self.token = body.get("data", {}).get("access_token") or body.get("data", {}).get("token")
                self._record("token_extracted", bool(self.token), f"token_prefix={str(self.token)[:10] if self.token else 'none'}")
            except Exception:
                self._record("token_extracted", False, "invalid_json")

    def test_protected_endpoints(self) -> None:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        protected = [
            ("/api/rag/query", "post", {"query": "test"}, 8),
            ("/api/reasoning/query", "post", {"query": "test"}, 30),
            ("/api/void/talk", "post", {"message": "ping"}, 30),
            ("/api/flatspace/stats", "get", None, 8),
            ("/api/task-audit", "get", None, 8),
            ("/api/mcp-audit", "get", None, 8),
            ("/api/self-improvement", "get", None, 8),
        ]
        for p, method, payload, timeout in protected:
            try:
                if method == "post":
                    r = requests.post(f"{BASE}{p}", json=payload or {}, headers=headers, timeout=timeout)
                else:
                    r = requests.get(f"{BASE}{p}", headers=headers, timeout=timeout)
                self._record(f"protected_{p}", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self._record(f"protected_{p}", False, f"ERROR={e}")

    def test_commercial_layer(self) -> None:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        commercial_paths = [
            ("/api/support/status", "get", None),
            ("/api/support/metrics", "get", None),
            ("/api/support/ticket", "post", {}),
        ]
        for p, method, payload in commercial_paths:
            try:
                if method == "post":
                    r = requests.post(f"{BASE}{p}", json=payload or {}, headers=headers, timeout=5)
                else:
                    r = requests.get(f"{BASE}{p}", headers=headers, timeout=5)
                self._record(f"commercial_{p}", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self._record(f"commercial_{p}", False, f"ERROR={e}")

    def test_mesh_and_probe(self) -> None:
        mesh_paths = [
            ("/api/mesh/nodes/health", "get"),
            ("/api/mesh/nodes/metrics", "get"),
            ("/api/mesh/nodes/best", "get"),
            ("/api/mesh/nodes/promote", "post"),
        ]
        for p, method in mesh_paths:
            try:
                if method == "post":
                    r = requests.post(f"{BASE}{p}", json={}, timeout=10)
                else:
                    r = requests.get(f"{BASE}{p}", timeout=10)
                self._record(f"mesh_{p}", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self._record(f"mesh_{p}", False, f"ERROR={e}")

    def test_security_hardening(self) -> None:
        dist = REPO / "dist"
        bad = []
        if dist.exists():
            for txt in dist.rglob("*.env"):
                bad.append(str(txt))
        self._record("no_env_in_dist", len(bad) == 0, f"env_files={bad}")
        gi = REPO / ".gitignore"
        ignored = False
        if gi.exists():
            ignored = ".env" in gi.read_text().splitlines()
        self._record("env_gitignored", ignored, str(gi))

    def summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        print(f"\n=== SUMMARY === passed={passed}/{total}")
        for r in self.results:
            if not r["passed"]:
                print(f"FAIL: {r['name']} | {r['detail']}")


if __name__ == "__main__":
    TestSuite().run()
