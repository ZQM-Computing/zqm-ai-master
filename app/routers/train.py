"""
Training router: /api/train/lora

Accepts distributed training jobs and runs LoRA fine-tuning.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.logger import get_logger
from app.core.security import get_current_token_payload, require_admin

router = APIRouter(prefix="/api/train", tags=["Training"])
log = get_logger("router.train")

# In-memory job registry (replace with DB in production)
_TRAIN_JOBS: dict[str, dict[str, Any]] = {}


def _run_training_job(job_id: str, params: dict[str, Any]) -> None:
    """Background training runner."""
    _TRAIN_JOBS[job_id]["status"] = "running"
    _TRAIN_JOBS[job_id]["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        # Ensure local package imports are used, not OneDrive/.venv cached paths.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, root)
        os.chdir(root)
        for mod in ["app.orchestrator.agent_registry", "app.orchestrator.zqm_ai_orchestrator"]:
            sys.modules.pop(mod, None)
        from scripts.train_lora import train_lora as _train_lora
        
        def _safe_train_lora(**kwargs):
            base_model = kwargs.get("base_model", "distilgpt2")
            target_modules = kwargs.get("target_modules")
            if target_modules:
                return _train_lora(**kwargs)
            candidate_sets = [
                ["q_proj", "v_proj", "k_proj", "o_proj"],
                ["c_attn", "c_proj"],
                ["qkv_proj", "out_proj"],
                ["query", "key", "value", "dense"],
            ]
            last_err = None
            for cand in candidate_sets:
                try:
                    kwargs["target_modules"] = cand
                    return _train_lora(**kwargs)
                except Exception as exc:
                    last_err = exc
            raise last_err or RuntimeError("LoRA target-module selection failed")
        
        output_dir = params.get("output_dir", f"models/{job_id}")
        result = _safe_train_lora(
            base_model=params.get("base_model", "distilgpt2"),
            dataset_path=params.get("dataset_path", "data/training_data_all.jsonl"),
            output_dir=output_dir,
            epochs=int(params.get("epochs", 1)),
            batch_size=int(params.get("batch_size", 4)),
            lora_rank=int(params.get("lora_rank", 8)),
            lora_alpha=int(params.get("lora_alpha", 16)),
            learning_rate=float(params.get("learning_rate", 2e-4)),
            target_modules=params.get("target_modules"),
        )
        _TRAIN_JOBS[job_id]["status"] = "completed"
        _TRAIN_JOBS[job_id]["result"] = result
        _TRAIN_JOBS[job_id]["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception as exc:
        _TRAIN_JOBS[job_id]["status"] = "failed"
        _TRAIN_JOBS[job_id]["error"] = str(exc)
        _TRAIN_JOBS[job_id]["failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@router.post("/lora")
async def submit_lora_job(
    request: Request,
    body: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Submit a LoRA fine-tuning job."""
    job_id = str(uuid.uuid4())
    _TRAIN_JOBS[job_id] = {
        "job_id": job_id,
        "params": body,
        "status": "queued",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    # Launch in background
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_training_job, job_id, dict(body))
    
    return JSONResponse({
        "job_id": job_id,
        "status": "queued",
        "params": body,
        "message": "Training job submitted",
    })


@router.get("/lora/{job_id}")
async def get_job_status(
    job_id: str,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """Get status of a training job."""
    job = _TRAIN_JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "job_not_found"}, status_code=404)
    return JSONResponse(job)


@router.get("/lora")
async def list_jobs(
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> JSONResponse:
    """List all training jobs."""
    return JSONResponse({"jobs": list(_TRAIN_JOBS.values())})


@router.delete("/lora/{job_id}")
async def cancel_job(
    job_id: str,
    auth: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Cancel a training job."""
    job = _TRAIN_JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "job_not_found"}, status_code=404)
    if job["status"] in ("completed", "failed", "cancelled"):
        return JSONResponse({"error": f"job_already_{job['status']}"}, status_code=400)
    job["status"] = "cancelled"
    job["cancelled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return JSONResponse({"job_id": job_id, "status": "cancelled"})
