"""
The Void AI Orchestration System — Customer release packaging
Version: 2.2.0 | ZQM Computing LLC

Builds a customer-facing archive from the current repo checkout by
copying only the artifacts listed in release.manifest.toml.
"""

from __future__ import annotations

import shutil
import sys
from configparser import ConfigParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST = BASE_DIR / "release.manifest.toml"
DIST = BASE_DIR / "dist"

# Minimal TOML parser for flat sections without external deps
# Only supports the subset used by release.manifest.toml
def _read_manifest(path: Path) -> dict:
    out: dict = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            out.setdefault(current, {})
            continue
        if "=" in line and current is not None:
            key, value = line.split("=", 1)
            out[current][key.strip()] = value.strip()
    return out


def _parse_csv_list(value: str) -> list[str]:
    value = value.strip().strip("[]")
    return [item.strip().strip('"').strip("'") for item in value.split(",") if item.strip()]


def main() -> int:
    if not MANIFEST.exists():
        print(f"manifest_missing={MANIFEST}")
        return 1
    manifest = _read_manifest(MANIFEST)
    artifacts = _parse_csv_list(manifest.get("artifacts", {}).get("required", ""))
    installers = _parse_csv_list(manifest.get("installers", {}).get("windows", ""))

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    copied = []
    for rel in artifacts + installers:
        src = BASE_DIR / rel
        if not src.exists():
            print(f"missing_artifact={rel}")
            continue
        dst = DIST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(rel)

    print(f"dist_dir={DIST}")
    print(f"packaged={len(copied)}")
    for item in copied:
        print(f"artifact={item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
