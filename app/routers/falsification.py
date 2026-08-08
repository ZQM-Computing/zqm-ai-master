"""
The Void AI Orchestration System — /api/falsification Router
Version: 2.0.0 | ZQM Computing LLC

Runtime introspection for the falsification protocol defenses.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.logger import get_logger
from app.core.security import get_current_token_payload

router = APIRouter(prefix="/api/falsification", tags=["Falsification Protocol"])
log = get_logger("router.falsification")


class AuditResponse(BaseModel):
    timestamp: str
    challenge_1_hardware_drift: dict
    challenge_2_kv_cache: dict
    challenge_3_manifest: dict
    challenge_4_working_memory: dict
    challenge_5_normalization: dict
    challenge_6_constraint_seeds: dict
    challenge_7_world_state: dict
    challenge_8_external_consistency: dict
    all_passed: bool


class AuditRequest(BaseModel):
    envelope: dict[str, Any] | None = None
    working_memory: list[str] | None = None
    kv_cache: list[float] | None = None
    cumulative_error: float | None = None
    last_tool_output: dict[str, Any] | None = None
    error_curve: list[float] | None = None
    seed: int | None = None
    constraints: list[str] | None = None
    world_snapshot: dict[str, Any] | None = None
    world_baseline: dict[str, Any] | None = None
    world_staleness_s: float | None = None
    world_staleness_threshold_s: float | None = None
    last_observation: dict[str, Any] | None = None
    last_action: dict[str, Any] | None = None
    action_world_delta: dict[str, Any] | None = None

AuditRequest.model_rebuild()


@router.get(
    "/audit",
    response_model=AuditResponse,
    summary="Run falsification protocol audit against current app state",
    description="Executes all 6 falsification-protocol defenses against live orchestrator state and returns structured evidence.",
)
async def run_audit(
    request: Request,
    auth: dict = Depends(get_current_token_payload),
) -> AuditResponse:
    orchestrator = request.app.state.orchestrator
    protocol = orchestrator.falsification
    app_state = _build_app_state(orchestrator)
    report = protocol.full_audit(app_state)
    return AuditResponse(**report)


@router.post(
    "/audit",
    response_model=AuditResponse,
    summary="Run falsification protocol audit against provided app_state",
    description="Accepts a custom app_state payload and executes all 6 defenses.",
)
async def run_audit_custom(
    body: AuditRequest,
    request: Request,
    auth: dict = Depends(get_current_token_payload),
) -> AuditResponse:
    orchestrator = request.app.state.orchestrator
    protocol = orchestrator.falsification
    app_state = _build_app_state(orchestrator)
    if body.envelope is not None:
        app_state["envelope"] = body.envelope
    if body.working_memory is not None:
        app_state["working_memory"] = body.working_memory
    if body.kv_cache is not None:
        app_state["kv_cache"] = body.kv_cache
    if body.cumulative_error is not None:
        app_state["cumulative_error"] = body.cumulative_error
    if body.last_tool_output is not None:
        app_state["last_tool_output"] = body.last_tool_output
    if body.error_curve is not None:
        app_state["error_curve"] = body.error_curve
    if body.seed is not None:
        app_state["seed"] = body.seed
    if body.constraints is not None:
        app_state["constraints"] = body.constraints
    if body.world_snapshot is not None:
        app_state["world_snapshot"] = body.world_snapshot
    if body.world_baseline is not None:
        app_state["world_baseline"] = body.world_baseline
    if body.world_staleness_s is not None:
        app_state["world_staleness_s"] = body.world_staleness_s
    if body.world_staleness_threshold_s is not None:
        app_state["world_staleness_threshold_s"] = body.world_staleness_threshold_s
    if body.last_observation is not None:
        app_state["last_observation"] = body.last_observation
    if body.last_action is not None:
        app_state["last_action"] = body.last_action
    if body.action_world_delta is not None:
        app_state["action_world_delta"] = body.action_world_delta
    report = protocol.full_audit(app_state)
    return AuditResponse(**report)


@router.get(
    "/manifest",
    summary="Read current falsification manifest baseline",
    description="Returns the current normalization manifest hash and volatile keys.",
)
async def read_manifest(
    request: Request,
    auth: dict = Depends(get_current_token_payload),
) -> dict:
    orchestrator = request.app.state.orchestrator
    protocol = orchestrator.falsification
    return {
        "baseline_hash": protocol.manifest_baseline,
        "volatile_keys": sorted(protocol.volatile_keys),
        "boundary_history_count": len(protocol.boundary_history),
    }


@router.post(
    "/verify-manifest",
    summary="Verify current manifest against baseline",
    description="Recomputes manifest hash and compares to baseline. Returns mutation status.",
)
async def verify_manifest(
    request: Request,
    auth: dict = Depends(get_current_token_payload),
) -> dict:
    orchestrator = request.app.state.orchestrator
    protocol = orchestrator.falsification
    return protocol.verify_manifest()


def _build_app_state(orchestrator) -> dict:
    """Build app_state dict from live orchestrator state."""
    active = list(orchestrator._active_tasks.values())
    recent = list(orchestrator._task_history.values())[-8:]
    all_tasks = active + recent

    wm: list[str] = []
    kv_cache: list[float] = []
    error_curve: list[float] = []
    tool_output: dict = {}
    seed = 42
    constraints = ["max_length=100", "no_code_switch", "preserve_tense"]

    for task in all_tasks:
        if task.input:
            wm.append(task.input[:120])
        if task.cognitive_trace:
            for exec_rec in task.cognitive_trace.executions:
                step_text = (exec_rec.output or "").strip()
                if step_text:
                    wm.append(step_text[:120])
                if getattr(exec_rec, "tool_trace", None):
                    for action in exec_rec.tool_trace:
                        if action.get("ok"):
                            tool_output = action.get("result", tool_output)
                            break
                if getattr(exec_rec, "step_hashes", None):
                    try:
                        kv_cache.extend([int(h, 16) / 0xFFFFFFFF for h in exec_rec.step_hashes[-20:]])
                    except Exception:
                        pass
            if getattr(task.cognitive_trace, "reconstruction_variance", None) is not None:
                error_curve = [float(task.cognitive_trace.reconstruction_variance)] * 20
        if len(wm) > 20:
            break

    latest = all_tasks[0] if all_tasks else None
    envelope = {}
    if latest:
        envelope = {
            "task_id": latest.task_id,
            "status": latest.status.value if hasattr(latest.status, "value") else str(latest.status),
            "cognitive_level": latest.cognitive_level.value if hasattr(latest.cognitive_level, "value") else str(latest.cognitive_level),
        }

    return {
        "envelope": envelope,
        "working_memory": wm[:10],
        "kv_cache": kv_cache[:100],
        "cumulative_error": float(error_curve[-1]) if error_curve else 0.0,
        "last_tool_output": tool_output,
        "error_curve": error_curve,
        "seed": seed,
        "constraints": constraints,
        "world_snapshot": _latest_world_snapshot(orchestrator),
        "world_baseline": _baseline_world_snapshot(orchestrator),
        "world_staleness_s": _world_staleness_s(orchestrator),
        "world_staleness_threshold_s": 600.0,
        "last_observation": _latest_observation(orchestrator),
        "last_action": _latest_action(orchestrator),
        "action_world_delta": _latest_world_delta(orchestrator),
    }


def _latest_world_snapshot(orchestrator) -> dict:
    return getattr(orchestrator, "_last_world_snapshot", {}) or {}


def _baseline_world_snapshot(orchestrator) -> dict:
    return getattr(orchestrator, "_world_baseline", {}) or {}


def _world_staleness_s(orchestrator) -> float:
    ts = getattr(orchestrator, "_last_world_snapshot_ts", None)
    if ts is None:
        return 0.0
    return max(0.0, time.time() - ts)


def _latest_observation(orchestrator) -> dict:
    return getattr(orchestrator, "_last_observation", {}) or {}


def _latest_action(orchestrator) -> dict:
    return getattr(orchestrator, "_last_action", {}) or {}


def _latest_world_delta(orchestrator) -> dict:
    return getattr(orchestrator, "_last_world_delta", {}) or {}
