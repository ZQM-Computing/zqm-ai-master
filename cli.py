"""zqm-ai-master CLI

Usage:
  zqm-ai-master serve [--host HOST] [--port PORT] [--reload]
  zqm-ai-master health [--host HOST] [--port PORT]
  zqm-ai-master status [--host HOST] [--port PORT]
  zqm-ai-master info [--host HOST] [--port PORT]
  zqm-ai-master agents [--host HOST] [--port PORT]
  zqm-ai-master routes [--host HOST] [--port PORT] [--offline]
  zqm-ai-master config [--host HOST] [--port PORT] [--offline]
  zqm-ai-master logs [--tail N] [--follow]
  zqm-ai-master test [paths ...]
  zqm-ai-master version
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import List, Optional

try:
    import requests
except Exception:  # pragma: no cover - optional at runtime
    requests = None

APP_DIR = Path(__file__).resolve().parent

_SECRET_KEYS = (
    "secret",
    "password",
    "master_key",
    "api_key",
    "token",
    "redis_password",
    "meilisearch_master_key",
)


def _mask(value: str) -> str:
    if not value:
        return value
    return value[:4] + "****" if len(value) > 4 else "****"


def _mask_dict(d: dict) -> dict:
    return {k: ("****" if any(s in k.lower() for s in _SECRET_KEYS) else v) for k, v in d.items()}


def _http_get(path: str, host: str, port: int) -> Optional[requests.Response]:
    url = f"http://{host}:{port}{path}"
    if requests is None:
        print(f"requests not installed; cannot call {url}")
        return None
    try:
        return requests.get(url, timeout=5)
    except Exception as exc:
        print(f"request failed: {exc}")
        return None


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except Exception:
        print("uvicorn is not installed")
        return 1
    print(f"starting app at {args.host}:{args.port} reload={args.reload}")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _request(args: argparse.Namespace, path: str) -> int:
    r = _http_get(path, args.host, args.port)
    if r is None:
        return 2
    print(f"GET {path} -> {r.status_code}")
    print(r.text[:4000])
    return 0 if r.ok else 1


def cmd_health(args: argparse.Namespace) -> int:
    return _request(args, "/health")


def cmd_status(args: argparse.Namespace) -> int:
    if not _port_open(args.host, args.port):
        print(f"nothing listening on {args.host}:{args.port}")
        return 2
    return _request(args, "/status")


def cmd_info(args: argparse.Namespace) -> int:
    return _request(args, "/api/info")


def cmd_agents(args: argparse.Namespace) -> int:
    return _request(args, "/api/info/agents")


def cmd_routes(args: argparse.Namespace) -> int:
    if getattr(args, "offline", False):
        print("offline route scan not implemented yet")
        return 1
    r = _http_get("/openapi.json", args.host, args.port)
    if r is None:
        print("openapi unavailable")
        return 2
    if not r.ok:
        print(f"openapi -> {r.status_code}")
        return 1
    data = r.json()
    paths = sorted(data.get("paths", {}).keys())
    print(f"routes={len(paths)}")
    for p in paths:
        methods = sorted(m.upper() for m in data["paths"][p].keys())
        print(f"  {' '.join(methods):12} {p}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if getattr(args, "offline", False):
        print("offline config read not implemented yet")
        return 1
    r = _http_get("/api/settings", args.host, args.port)
    if r is None:
        print("settings endpoint unavailable")
        return 2
    if not r.ok:
        print(f"/api/settings -> {r.status_code}")
        print(r.text[:2000])
        return 1
    try:
        data = r.json()
    except Exception:
        print(r.text[:2000])
        return 0
    if isinstance(data, dict):
        data = _mask_dict(data)
    print(json.dumps(data, indent=2, default=str)[:6000])
    return 0


def _find_log_file() -> Optional[Path]:
    candidates = [
        APP_DIR / "logs" / "zqm-void.log",
        APP_DIR / "zqm-void.log",
        APP_DIR / "logs" / "app.log",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def cmd_logs(args: argparse.Namespace) -> int:
    path = _find_log_file()
    if path is None:
        print("log file not found")
        return 2
    n = int(getattr(args, "tail", 100) or 100)
    follow = bool(getattr(args, "follow", False))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
            sys.stdout.write("".join(lines))
            if follow:
                print("--- follow active, Ctrl+C to stop ---")
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        sys.stdout.write(line)
                    else:
                        import time
                        time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"log read failed: {exc}")
        return 1
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    paths: List[str] = args.paths or ["tests"]
    cmd = [sys.executable, "-m", "pytest", *paths]
    print(" ".join(cmd))
    return int(subprocess.call(cmd, cwd=str(APP_DIR)))


def cmd_version(_: argparse.Namespace) -> int:
    try:
        from app.core.version import __version__
        print(__version__)
    except Exception:
        try:
            from app.main import app
            print(getattr(app, "version", "unknown"))
        except Exception as exc:
            print(f"unknown: {exc}")
            return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="zqm-ai-master")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8808)
    sub = ap.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--reload", action="store_true")

    p_health = sub.add_parser("health")
    p_status = sub.add_parser("status")
    p_info = sub.add_parser("info")
    p_agents = sub.add_parser("agents")
    p_routes = sub.add_parser("routes")
    p_routes.add_argument("--offline", action="store_true")
    p_config = sub.add_parser("config")
    p_config.add_argument("--offline", action="store_true")
    p_logs = sub.add_parser("logs")
    p_logs.add_argument("--tail", type=int, default=100)
    p_logs.add_argument("--follow", action="store_true")
    p_test = sub.add_parser("test")
    p_test.add_argument("paths", nargs="*")
    sub.add_parser("version")

    ns = ap.parse_args(argv)
    if not ns.command:
        ap.print_help()
        return 0

    mapping = {
        "serve": cmd_serve,
        "health": cmd_health,
        "status": cmd_status,
        "info": cmd_info,
        "agents": cmd_agents,
        "routes": cmd_routes,
        "config": cmd_config,
        "logs": cmd_logs,
        "test": cmd_test,
        "version": cmd_version,
    }
    fn = mapping.get(ns.command)
    if fn is None:
        ap.print_help()
        return 1
    return int(fn(ns))


if __name__ == "__main__":
    raise SystemExit(main())
