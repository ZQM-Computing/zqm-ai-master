"""
Full enumerative test suite for The Void / ZQM-AI-Master.
Covers: OpenAPI schema, public endpoints, auth flow, protected endpoints,
commercial layer, mesh/probe, packaging, compile, service state,
void council, self-improvement, self-replication.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import requests

BASE = "http://127.0.0.1:8808"
REPO = Path(__file__).resolve().parent.parent
_PY_DEFAULT = r"C:\Program Files\Python312\python.exe"


def _resolve_py() -> str:
    import shutil
    return _PY_DEFAULT if Path(_PY_DEFAULT).exists() else (shutil.which("python") or shutil.which("python3") or "python")


PY = _resolve_py()

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
        self.results: list[dict[str, Any]] = []
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
        self.test_void_council()
        self.test_self_improve()
        self.test_self_replicate()
        self.test_security_hardening()
        self.summary()

    def _get(self, path: str, timeout: int = 5, **kwargs: Any) -> requests.Response | None:
        try:
            return requests.get(f"{BASE}{path}", timeout=timeout, **kwargs)
        except Exception:
            return None

    def _post(self, path: str, payload: dict[str, Any] | None = None, timeout: int = 10, **kwargs: Any) -> requests.Response | None:
        try:
            return requests.post(f"{BASE}{path}", json=payload or {}, timeout=timeout, **kwargs)
        except Exception:
            return None

    def _record_response(self, prefix: str, path: str, response: requests.Response | None, expected: int = 200) -> None:
        if response is None:
            self._record(f"{prefix}_{path}", False, "skipped: service not running")
            return
        self._record(f"{prefix}_{path}", response.status_code == expected, f"status={response.status_code}")

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
        checks = [
            "/healthz",
            "/api/healthz",
            "/api/version",
            "/api/void-council/status",
        ]
        for path in checks:
            try:
                r = requests.get(f"{BASE}{path}", timeout=2)
                self._record(f"service_{path}", r.status_code == 200, f"status={r.status_code}")
            except Exception:
                self._record(f"service_{path}", False, "skipped: service not running")

    def test_openapi_enumeration(self) -> None:
        schema_required = [
            "/api/void-council/status",
            "/api/void-council/domains",
            "/api/void-council/convene",
            "/api/void-council/convene-full",
            "/api/void-council/emergency",
            "/api/void-council/history",
            "/api/void-council/quality",
            "/api/void/talk",
            "/api/self-improve/run",
            "/api/self-replicate",
            "/api/version",
            "/api/users/login",
        ]
        try:
            r = requests.get(f"{BASE}/openapi.json", timeout=10)
            r.raise_for_status()
        except Exception as e:
            self._record("openapi_available", False, f"skipped: {type(e).__name__}")
            return
        if r.status_code == 200:
            data = r.json()
            paths = sorted(data.get("paths", {}).keys())
            self._record("openapi_path_count", len(paths) > 0, f"count={len(paths)}")
            for required in schema_required:
                self._record(f"schema_has_{required.strip('/').replace('/', '_')}", required in paths, f"present={required in paths}")

    def test_public_endpoints(self) -> None:
        public = ["/healthz", "/api/healthz", "/api/version", "/api/void-council/status", "/docs", "/redoc", "/openapi.json"]
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

    def test_void_council(self) -> None:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        public_void = [
            "/api/void-council/status",
        ]
        for p in public_void:
            self._record_response("void", p, self._get(p, timeout=5))

        admin_required = [
            ("/api/void-council/convene", "post", {"domain": "security", "min_confidence": 0.6, "auto_apply": False}),
            ("/api/void-council/convene-full", "post", {"min_confidence": 0.6, "auto_apply": False}),
            ("/api/void-council/emergency", "post", {"domains": ["reliability", "security"], "auto_apply": False}),
        ]
        for p, method, payload in admin_required:
            r = self._post(p, payload=payload, timeout=15, headers=headers)
            if r is not None and r.status_code == 401:
                self._record(f"void_{p}", False, "skipped: admin token required")
            elif r is not None:
                self._record(f"void_{p}", r.status_code == 200, f"status={r.status_code}")
            else:
                self._record(f"void_{p}", False, "skipped: service not running")

        token_required = [
            "/api/void-council/domains",
            "/api/void-council/history",
            "/api/void-council/quality",
        ]
        for p in token_required:
            r = self._get(p, timeout=5, headers=headers)
            if r is not None and r.status_code == 401:
                self._record(f"void_{p}", False, "skipped: auth token required")
            elif r is not None:
                self._record(f"void_{p}", r.status_code == 200, f"status={r.status_code}")
            else:
                self._record(f"void_{p}", False, "skipped: service not running")

    def test_self_improve(self) -> None:
        public_self_improve = [
            "/api/self-improvement",
        ]
        for p in public_self_improve:
            self._record_response("self_improve", p, self._get(p, timeout=5))
        admin_self_improve = [
            ("/api/self-improve/run", "post", {"target": "core"}),
            ("/api/self-improve/ledger", "get", None),
        ]
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for p, method, payload in admin_self_improve:
            if method == "post":
                r = self._post(p, payload=payload, timeout=15, headers=headers)
            else:
                r = self._get(p, timeout=5, headers=headers)
            if r is not None and r.status_code == 401:
                self._record(f"self_improve_{p}", False, "skipped: admin/auth token required")
            elif r is not None:
                self._record(f"self_improve_{p}", r.status_code == 200, f"status={r.status_code}")
            else:
                self._record(f"self_improve_{p}", False, "skipped: service not running")

    def test_self_replicate(self) -> None:
        public_replicate = [
            "/api/self-replicate/status",
            "/api/self-replicate/ledger",
        ]
        for p in public_replicate:
            self._record_response("self_replicate", p, self._get(p, timeout=5))

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = self._post("/api/self-replicate", payload={"node": "N3", "confirm": False}, timeout=15, headers=headers)
        if r is not None and r.status_code == 401:
            self._record("self_replicate_apply", False, "skipped: admin token required")
        elif r is not None:
            self._record("self_replicate_apply", r.status_code == 200, f"status={r.status_code}")
        else:
            self._record("self_replicate_apply", False, "skipped: service not running")

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
