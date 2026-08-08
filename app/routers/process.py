"""
The Void AI Orchestration System — /api/process Router
Version: 2.0.0 | ZQM Computing LLC

Primary AI task submission and execution endpoint.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.logger import get_logger
from app.core.security import get_current_token_payload
from app.models.response import ZQM_AIResponse
from app.models.task import TaskRequest, TaskResult

router = APIRouter(prefix="/api/process", tags=["Process"])
log = get_logger("router.process")


@router.post(
    "",
    response_model=ZQM_AIResponse,
    summary="Submit and execute an AI task",
    description=(
        "Submit a task to the The Void orchestration engine. "
        "The request is routed to the appropriate cognitive level, "
        "agents are selected, processing occurs, and results are returned. "
        "Cognitive levels: basic (1 agent) → advanced (multi-agent) → "
        "neural (with memory) → autonomous (self-directed + learning)."
    ),
    responses={
        200: {"description": "Task completed successfully"},
        422: {"description": "Invalid request payload"},
        500: {"description": "Processing error"},
        504: {"description": "Task timeout"},
    },
)
async def process_task(
    request_body: TaskRequest,
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """
    Execute an AI task through The Void cognitive processing pipeline.

    **Examples:**

    Basic chat:
    ```json
    {"input": "What is sea-level rise?", "cognitive_level": "basic"}
    ```

    GIS analysis with neural processing:
    ```json
    {
      "input": "Analyze flood risk for polygon coordinates [...]",
      "cognitive_level": "neural",
      "input_method": "map_input",
      "context": {"coordinates": [...]}
    }
    ```

    Multi-turn conversation:
    ```json
    {"input": "Follow-up: what mitigation options exist?", "session_id": "session-abc123", "cognitive_level": "advanced"}
    ```
    """
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        try:
            from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator
            orchestrator = ZQM_AIOrchestrator()
            await orchestrator.startup()
            request.app.state.orchestrator = orchestrator
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"mini-orchestrator bootstrap failed: {exc}",
            )
    t0 = time.monotonic()

    # Attach user context if authenticated
    if auth and auth.get("sub") and not request_body.user_id:
        request_body = request_body.model_copy(update={"user_id": auth["sub"]})

    try:
        result: TaskResult = await orchestrator.execute_task(request_body)
        duration_ms = int((time.monotonic() - t0) * 1000)

        log.info(
            "Process request complete",
            task_id=result.task_id,
            duration_ms=duration_ms,
        )

        return ZQM_AIResponse.ok(
            data=result.model_dump(),
            message="Task completed successfully",
            request_id=request_body.task_id,
            duration_ms=duration_ms,
        )

    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Task timed out: {exc}",
        )
    except Exception as exc:
        log.exception("Process request failed", task_id=request_body.task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get(
    "/history",
    response_model=ZQM_AIResponse,
    summary="Task history (restart-surviving)",
)
async def task_history(
    request: Request,
    limit: int = 100,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return completed/failed task history. Reads the durable FLATSPACE
    `task:*` records so history survives a process restart (merged with
    in-memory history)."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        try:
            from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator
            orchestrator = ZQM_AIOrchestrator()
            await orchestrator.startup()
            request.app.state.orchestrator = orchestrator
        except Exception as exc:
            return ZQM_AIResponse.ok(data=[], message=f"mini-orchestrator bootstrap failed: {exc}")
    history_fn = getattr(orchestrator, "get_durable_history", None)
    if callable(history_fn):
        tasks = [t for t in (await history_fn(limit=limit)) or []]
    else:
        tasks = []
    return ZQM_AIResponse.ok(
        data=[t.model_dump() for t in tasks],
        message=f"{len(tasks)} task(s) in history",
    )


@router.get(
    "/{task_id}",
    response_model=ZQM_AIResponse,
    summary="Get task status and result",
)
async def get_task(
    task_id: str,
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Retrieve the current status and result of a previously submitted task."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        try:
            from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator
            orchestrator = ZQM_AIOrchestrator()
            await orchestrator.startup()
            request.app.state.orchestrator = orchestrator
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"mini-orchestrator bootstrap failed: {exc}")

    if hasattr(orchestrator, "get_task"):
        task = await orchestrator.get_task(task_id)
    else:
        pool: list = []
        try:
            pool.extend(await orchestrator.get_active_tasks())
        except Exception:
            pass
        try:
            pool.extend(await orchestrator.get_history())
        except Exception:
            pass
        task = next((t for t in pool if getattr(t, "task_id", None) == task_id), None)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return ZQM_AIResponse.ok(
        data=task.model_dump(),
        message=f"Task status: {task.status}",
        request_id=task_id,
    )


@router.get(
    "",
    response_model=ZQM_AIResponse,
    summary="List active tasks",
)
async def list_active_tasks(
    request: Request,
    auth: dict[str, Any] = Depends(get_current_token_payload),
) -> ZQM_AIResponse:
    """Return all currently active (in-progress) tasks."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return ZQM_AIResponse.ok(data=[], message="orchestrator not initialized in this process context")
    tasks = await orchestrator.get_active_tasks()
    return ZQM_AIResponse.ok(
        data=[t.model_dump() for t in tasks],
        message=f"{len(tasks)} active task(s)",
    )
