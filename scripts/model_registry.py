"""
Model registry + checkpoint manager for Phase 1.

Stores model metadata in JSON and tracks adapter/merged checkpoints.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


REGISTRY_PATH = "models/registry.json"
CHECKPOINT_ROOT = "models"


@dataclass
class ModelRecord:
    model_id: str
    base_model: str
    variant: str = "base"
    adapter_dir: Optional[str] = None
    merged_dir: Optional[str] = None
    created_at: str = ""
    metrics: Dict[str, Any] = None  # type: ignore
    tags: List[str] = None  # type: ignore
    note: str = ""

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
        if self.tags is None:
            self.tags = []
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_registry() -> Dict[str, ModelRecord]:
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for k, v in raw.items():
        out[k] = ModelRecord(**v)
    return out


def _save_registry(reg: Dict[str, ModelRecord]) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH) or ".", exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump({k: asdict(v) for k, v in reg.items()}, f, indent=2)


def register_model(
    model_id: str,
    base_model: str,
    variant: str = "base",
    adapter_dir: Optional[str] = None,
    merged_dir: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    note: str = "",
) -> ModelRecord:
    reg = _load_registry()
    rec = ModelRecord(
        model_id=model_id,
        base_model=base_model,
        variant=variant,
        adapter_dir=adapter_dir,
        merged_dir=merged_dir,
        metrics=metrics or {},
        tags=tags or [],
        note=note,
    )
    reg[model_id] = rec
    _save_registry(reg)
    return rec


def list_models() -> List[ModelRecord]:
    return list(_load_registry().values())


def best_model(metric: str = "mmlu", higher_is_better: bool = True) -> Optional[ModelRecord]:
    reg = list(_load_registry().values())
    scored = [r for r in reg if metric in (r.metrics or {})]
    if not scored:
        return None
    scored.sort(key=lambda r: r.metrics.get(metric, 0), reverse=higher_is_better)
    return scored[0]


def stage_checkpoint(src_dir: str, model_id: str, kind: str = "adapter") -> str:
    """Copy a checkpoint into models/<kind>/<model_id>."""
    dest = os.path.join(CHECKPOINT_ROOT, kind, model_id)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(src_dir, dest)
    return dest
