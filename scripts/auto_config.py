"""
The Void AI Orchestration System — First-run auto-configuration
Version: 2.2.0 | ZQM Computing LLC

Idempotent setup invoked by the customer installer.
Creates .env if missing, generates secrets, ensures directories exist,
and runs one-time initialization for local services.
"""

from __future__ import annotations

import secrets
import string
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE = BASE_DIR / ".env.example"


def _rand_hex(n: int = 32) -> str:
    return secrets.token_hex(n // 2)


def _rand_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_env() -> Path:
    if ENV_PATH.exists():
        return ENV_PATH

    template = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else ""
    lines = []
    for line in template.splitlines():
        if line.startswith("SECRET_KEY="):
            lines.append(f"SECRET_KEY={_rand_hex(32)}")
        elif line.startswith("ZQM_ADMIN_PASSWORD="):
            lines.append(f"ZQM_ADMIN_PASSWORD={_rand_password(24)}")
        elif line.startswith("ZQM_INTERNAL_KEY="):
            lines.append(f"ZQM_INTERNAL_KEY={_rand_hex(32)}")
        elif line.startswith("ZQM_GARDEN_SERVICE_KEY="):
            lines.append(f"ZQM_GARDEN_SERVICE_KEY={_rand_hex(32)}")
        elif line.startswith("ZQM_FLATSPACE_SERVICE_KEY="):
            lines.append(f"ZQM_FLATSPACE_SERVICE_KEY={_rand_hex(32)}")
        elif line.startswith("ZQM_OBSERVABILITY_SERVICE_KEY="):
            lines.append(f"ZQM_OBSERVABILITY_SERVICE_KEY={_rand_hex(32)}")
        elif line.startswith("MEILISEARCH_MASTER_KEY="):
            lines.append(f"MEILISEARCH_MASTER_KEY={_rand_hex(32)}")
        else:
            lines.append(line)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ENV_PATH


def ensure_dirs() -> None:
    for rel in ["logs", "data", "models"]:
        p = BASE_DIR / rel
        p.mkdir(parents=True, exist_ok=True)


def main() -> None:
    env_path = ensure_env()
    ensure_dirs()
    print(f"env_ready={env_path}")
    print("dirs_ready=logs,data,models")
    print("auto_config=complete")


if __name__ == "__main__":
    main()
