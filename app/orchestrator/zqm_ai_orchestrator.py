"""
The Void AI Orchestration System — ZQM_AIOrchestrator
Version: 2.0.0 | ZQM Computing LLC

The ZQM_AIOrchestrator is the central coordination engine.
It receives tasks, routes them, selects agents, dispatches to the
CognitiveProcessor, records results, and triggers learning.

Exposes:
  execute_task(request)  → TaskResult
  get_status()           → system status dict
  learn_from_execution() → update internal knowledge
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.memory.void_cache import get_void_cache
from app.models.response import DashboardStats, HealthStatus
from app.models.task import (
    CognitiveLevel, Task, TaskRequest, TaskResult, TaskStatus,
)
from app.orchestrator.agent_registry import AgentRegistry, AgentType
from app.orchestrator.cognitive_processor import CognitiveProcessor
from app.orchestrator.task_router import TaskRouter
from app.services.garden_service import GardenService
from app.services.flatspace_service import FlatSpaceService
from app.services.synology_service import SynologyService
from app.services.mesh_node_ops import MeshNodeOperations
from app.orchestrator import self_apply
from app.orchestrator import system_integration
from app.orchestrator import void_council
from app.services.observability_service import ObservabilityService
from app.services.falsification_protocol import FalsificationProtocol

log = get_logger("zqm_ai-orchestrator")


def _task_app_state(task: Optional["Task"], cognitive_trace: Any) -> Dict[str, Any]:
    """Build app_state dict for falsification protocol from task + trace."""
    if task is None:
        task = type("Task", (), {"task_id": "unknown", "status": "unknown", "cognitive_level": "unknown"})()
    wm: List[str] = []
    kv_cache: List[float] = []
    error_curve: List[float] = []
    tool_output: Dict[str, Any] = {}
    seed = 42
    constraints = ["max_length=100", "no_code_switch", "preserve_tense"]

    if cognitive_trace is not None:
        for exec_rec in getattr(cognitive_trace, "executions", []):
            step_text = (getattr(exec_rec, "output", None) or "").strip()
            if step_text:
                wm.append(step_text[:120])
            tool_trace = getattr(exec_rec, "tool_trace", None)
            if tool_trace:
                for action in tool_trace:
                    if action.get("ok"):
                        tool_output = action.get("result", tool_output)
                        break
            step_hashes = getattr(exec_rec, "step_hashes", None)
            if step_hashes:
                try:
                    kv_cache.extend([int(h, 16) / 0xFFFFFFFF for h in step_hashes[-20:]])
                except Exception:
                    pass
        reconstruction_variance = getattr(cognitive_trace, "reconstruction_variance", None)
        if reconstruction_variance is not None:
            error_curve = [float(reconstruction_variance)] * 20

    return {
        "envelope": {
            "task_id": task.task_id if hasattr(task, "task_id") else "unknown",
            "status": task.status.value if hasattr(task.status, "value") else str(getattr(task, "status", "unknown")),
            "cognitive_level": task.cognitive_level.value if hasattr(task.cognitive_level, "value") else str(getattr(task, "cognitive_level", "unknown")),
        },
        "working_memory": wm[:10],
        "kv_cache": kv_cache[:100],
        "cumulative_error": float(error_curve[-1]) if error_curve else 0.0,
        "last_tool_output": tool_output,
        "error_curve": error_curve,
        "seed": seed,
        "constraints": constraints,
        "world_snapshot": getattr(task, "world_snapshot", None) or {},
        "world_baseline": getattr(task, "world_baseline", None) or {},
        "world_staleness_s": float(getattr(task, "world_staleness_s", 0.0) or 0.0),
        "world_staleness_threshold_s": float(getattr(task, "world_staleness_threshold_s", 600.0) or 600.0),
        "last_observation": getattr(task, "last_observation", None) or {},
        "last_action": getattr(task, "last_action", None) or {},
        "action_world_delta": getattr(task, "action_world_delta", None) or {},
    }


class ZQM_AIOrchestrator:
    """
    Central AI task coordinator for the The Void system.

    Lifecycle:
        orchestrator = ZQM_AIOrchestrator()
        await orchestrator.startup()
        result = await orchestrator.execute_task(request)
        await orchestrator.shutdown()
    """

    # Identity constants
    ZQM_AI_ID = settings.zqm_ai_id
    EMPLOYEE_ID = settings.zqm_ai_employee_id
    PRIMARY_GARDEN = settings.zqm_ai_primary_garden

    def __init__(self) -> None:
        self.registry = AgentRegistry()
        self.processor = CognitiveProcessor()
        self.router = TaskRouter()
        self.cache = get_void_cache()
        self.garden = GardenService()
        self.flatspace = FlatSpaceService()
        self.node_ops = MeshNodeOperations(garden=self.garden)
        self.observability = ObservabilityService()
        self.falsification = FalsificationProtocol()
        # Allow observability to read co-task pair topology from registry.
        self.observability._registry = self.registry

        # Runtime state
        self._active_tasks: Dict[str, Task] = {}
        self._task_history: Dict[str, Task] = {}
        self._background_tasks: set = set()
        self._started_at: Optional[datetime] = None
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._total_tokens: int = 0
        self._lock = asyncio.Lock()
        self._self_improve_task: Optional[asyncio.Task] = None
        self._council_task: Optional[asyncio.Task] = None
        self._void_council = void_council.VoidCouncil(
            registry=self.registry,
            settings=settings,
        )
        log.info(
            "ZQM_AIOrchestrator created",
            zqm_ai_id=self.ZQM_AI_ID,
            employee_id=self.EMPLOYEE_ID,
            primary_garden=self.PRIMARY_GARDEN,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Initialize all subsystems."""
        log.info("ZQM_AIOrchestrator starting up...")
        self._started_at = datetime.now(timezone.utc)

        # Start agent pool
        await self.registry.startup()
        await self.observability.push_agent_metric(
            agent_stats=self.registry.stats() | {"family_counts": await self.registry.get_family_counts()}
        )

        # Warm up connections (non-blocking)
        asyncio.create_task(self._warm_up_connections())

        # Constant self-improvement loop (convenes panel via live backend)
        self._self_improve_task = asyncio.create_task(self._self_improvement_loop())

        # Council integrations
        try:
            await self._void_council.initialize_integrations(
                observability=self.observability,
                flatspace=self.flatspace,
                garden=self.garden,
                redis=getattr(app.state, "redis", None),
            )
        except Exception as exc:
            log.debug("council integrations init skipped", error=str(exc))

        # Optional scheduled council loop
        council_interval = getattr(settings, "council_interval_minutes", 0)
        if council_interval and council_interval > 0:
            self._council_task = asyncio.create_task(self._council_loop(council_interval))

        log.info(
            "ZQM_AIOrchestrator online",
            zqm_ai_id=self.ZQM_AI_ID,
            agents=self.registry.stats()["total"],
        )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        log.info("ZQM_AIOrchestrator shutting down...")

        # Stop constant self-improvement loop
        if self._self_improve_task and not self._self_improve_task.done():
            self._self_improve_task.cancel()
            try:
                await self._self_improve_task
            except (asyncio.CancelledError, Exception):
                pass

        # Wait for active tasks (with timeout)
        if self._active_tasks:
            log.warning("Active tasks during shutdown", count=len(self._active_tasks))
            try:
                await asyncio.wait_for(
                    self._wait_for_active_tasks(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                log.warning("Shutdown timeout — forcing close")

        await self.registry.shutdown()
        await self.cache.clear()
        log.info("ZQM_AIOrchestrator offline")

    # ── Core: Execute Task ────────────────────────────────────────────────────

    async def execute_task(self, request: TaskRequest) -> TaskResult:
        """
        Main entry point. Accepts a TaskRequest and returns a TaskResult.

        Pipeline:
          1. Route (determine cognitive level + priority)
          2. Analyze requirements
          3. Select agents
          4. Dispatch to CognitiveProcessor
          5. Record result + learn
        """
        t0 = time.monotonic()

        # 1. Route with audit metadata
        routed, routing_meta = self.router.route_with_audit(request)

        # 2. Create task record
        task = Task(
            task_id=routed.task_id,
            input=routed.input,
            context=routed.context,
            cognitive_level=routed.cognitive_level,
            priority=routed.priority,
            input_method=routed.input_method,
            status=TaskStatus.PROCESSING,
            started_at=datetime.now(timezone.utc),
            session_id=routed.session_id,
            user_id=routed.user_id,
            tags=routed.tags,
        )

        async with self._lock:
            self._active_tasks[task.task_id] = task

        log.info(
            "Task execution started",
            task_id=task.task_id,
            level=task.cognitive_level,
            priority=task.priority,
            method=task.input_method,
            routing_reason=routing_meta.get("reason"),
            routing_original=routing_meta.get("original_level"),
        )

        try:
            # 3. Select agents with routing context
            agents = await self.registry.select_for_task(
                cognitive_level=task.cognitive_level,
                input_method=task.input_method,
                context=task.context,
                input_text=task.input,
                routed_level=routed.cognitive_level.value,
                routing_meta=routing_meta,
            )

            if not agents:
                raise RuntimeError("No agents available to handle this task")

            # Apply explicit provider override from request when supplied.
            # This lets /api/process run fully standalone without changing
            # the global default_ai_provider or agent registry.
            if getattr(routed, "provider", None):
                for a in agents:
                    a.provider = routed.provider
                    if not a.model:
                        a.model = settings.ollama_default_model

            # 4. Execute with timeout circuit + cancellation scope.
            # Split budget: 70% for model/tool execution, 30% reserved for
            # cancellation/cleanup so a hung downstream call doesn't leak.
            exec_budget = int((routed.timeout or settings.task_timeout_seconds) * 0.7)
            exec_timeout = max(exec_budget, 5)
            try:
                result, cognitive_trace = await asyncio.wait_for(
                    asyncio.shield(self.processor.process(routed, agents, self.registry)),
                    timeout=exec_timeout,
                )
            except asyncio.TimeoutError:
                # Mark all selected agents as failed/timeout so they aren't
                # reused while hung work is still pending underneath.
                for a in agents:
                    try:
                        await registry.mark_idle(a.agent_id, success=False, latency_ms=exec_timeout * 1000)
                    except Exception:
                        pass
                raise

            # Attach routing metadata to cognitive trace so it persists
            cognitive_trace.routing = routing_meta

            # Compute optional calibration metrics
            if hasattr(result, "confidence") and getattr(result, "confidence", None) is not None:
                calibration_offset = None
                for exec_rec in cognitive_trace.executions:
                    if getattr(exec_rec, "error", None):
                        calibration_offset = abs(result.confidence - 0.0)
                        break
                if calibration_offset is None and getattr(result, "outcome_verified", None) is True:
                    calibration_offset = abs(result.confidence - 1.0)
                if calibration_offset is not None:
                    result = result.model_copy(update={"calibration_offset": calibration_offset})

            # 5. Finalize task record
            duration_ms = int((time.monotonic() - t0) * 1000)
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            task.duration_ms = duration_ms
            task.result = result
            task.cognitive_trace = cognitive_trace

            # 5a. Run falsification protocol audit on task state
            try:
                falsification_report = self.falsification.full_audit(
                    app_state=_task_app_state(task, cognitive_trace)
                )
                task.falsification_report = falsification_report
            except Exception as exc:
                log.warning("Falsification audit failed", task_id=task.task_id, error=str(exc))
                task.falsification_report = {"error": str(exc)}

            # 5b. Surface agent tool/integration actions in the response
            #     (so callers can see which systems the agents reached).
            agent_actions: List[Dict[str, Any]] = []
            for exec_rec in cognitive_trace.executions:
                for action in getattr(exec_rec, "tool_trace", []) or []:
                    agent_actions.append({
                        "agent_id": exec_rec.agent_id,
                        "agent_type": exec_rec.agent_type,
                        **action,
                    })
            if agent_actions:
                meta = dict(result.metadata or {})
                meta["agent_actions"] = agent_actions
                result = result.model_copy(update={"metadata": meta})

            async with self._lock:
                self._tasks_completed += 1
                self._total_tokens += result.total_tokens or 0

            log.info(
                "Task completed",
                task_id=task.task_id,
                duration_ms=duration_ms,
                tokens=result.total_tokens,
                cognitive_level=task.cognitive_level,
            )

            # 6. Async: persist to FLATSPACE, push observability metrics
            asyncio.create_task(self._post_execution(task, result))

            return result

        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = f"Task timed out after {routed.timeout or settings.task_timeout_seconds}s"
            async with self._lock:
                self._tasks_failed += 1
            log.error("Task timed out", task_id=task.task_id)
            raise

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            async with self._lock:
                self._tasks_failed += 1
            log.exception("Task failed", task_id=task.task_id, error=str(exc))
            raise

        finally:
            async with self._lock:
                self._active_tasks.pop(task.task_id, None)
                self._task_history[task.task_id] = task
            # Durable: persist terminal task to FLATSPACE so lookups
            # survive a process restart (in-memory maps are lost on exit).
            asyncio.create_task(self._persist_task(task))

    # ── Task retrieval / durable persistence ───────────────────────────────────

    async def _persist_task(self, task: "Task") -> None:
        """Durably store a terminal task record in FLATSPACE (local SQLite
        fallback survives a process restart). Fail-soft."""
        try:
            await self.flatspace.store(
                key=f"task:{task.task_id}",
                value=task.model_dump(mode="json"),
                tier="bitgarden",
                metadata={"status": str(getattr(task, "status", ""))},
            )
        except Exception as exc:
            log.debug("task persist skipped", task_id=task.task_id, error=str(exc))

    async def get_task(self, task_id: str) -> Optional["Task"]:
        task = self._active_tasks.get(task_id) or self._task_history.get(task_id)
        if task is not None:
            return task
        # Restart-survival fallback: read the durable FLATSPACE record.
        try:
            rec = await self.flatspace.retrieve(f"task:{task_id}", tier="bitgarden")
            if rec:
                from app.models.task import Task
                return Task(**rec)
        except Exception as exc:
            log.debug("task retrieve from FLATSPACE failed", task_id=task_id, error=str(exc))
        return None

    async def get_active_tasks(self) -> List[Task]:
        return list(self._active_tasks.values())

    async def get_history(self, limit: int = 100) -> List[Task]:
        tasks = list(self._task_history.values())
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    async def get_durable_history(self, limit: int = 100) -> List[Task]:
        """History that survives a process restart: reads the durable
        `task:*` records persisted to FLATSPACE (local SQLite fallback).
        Merges with in-memory history, deduped by task_id. Fail-soft."""
        merged: Dict[str, Task] = {t.task_id: t for t in self._task_history.values()}
        try:
            from app.models.task import Task as _Task
            # Prefix-key listing (no embedding) — history must not depend on
            # Ollama being up.
            hits = await self.flatspace.list_keys("task:", tier="bitgarden", limit=max(limit * 3, 50))
            for h in hits or []:
                if not h.get("key", "").startswith("task:"):
                    continue
                rec = h.get("value")
                if not isinstance(rec, dict):
                    continue
                try:
                    t = _Task(**rec)
                    merged.setdefault(t.task_id, t)
                except Exception:
                    continue
        except Exception as exc:
            log.debug("durable history read failed", error=str(exc))
        return sorted(merged.values(), key=lambda t: getattr(t, "created_at", 0), reverse=True)[:limit]

    # ── Status & Dashboard ────────────────────────────────────────────────────

    async def get_health(self, request: Request) -> HealthStatus:
        """Return system health check."""
        import os

        mem = None
        cpu = None
        try:
            import psutil
            try:
                mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
                cpu = psutil.cpu_percent(interval=None) or psutil.cpu_percent(interval=0.1)
            except Exception:
                pass
        except ImportError:
            pass

        agent_stats = self.registry.stats()
        cache_stats = self.cache.stats()
        uptime = (
            (datetime.now(timezone.utc) - self._started_at).total_seconds()
            if self._started_at
            else 0.0
        )

        # Check ZQM subsystem connectivity (concurrent, with overall timeout)
        try:
            garden_ok, flatspace_ok, obs_ok = await asyncio.wait_for(
                asyncio.gather(
                    self.garden.health_check(),
                    self.flatspace.health_check(),
                    self.observability.health_check(),
                ),
                timeout=6.0,
            )
        except (asyncio.TimeoutError, Exception):
            garden_ok, flatspace_ok, obs_ok = False, False, False

        database_ok = flatspace_ok
        self_apply_on = self_apply.SELF_APPLY_ON
        core_ok = database_ok and agent_stats["total"] > 0
        status = "healthy" if core_ok else "degraded"

        redis_state = getattr(request.app.state, "redis", None)
        redis_status = "disabled"
        if redis_state is not None:
            try:
                health = await redis_state.health_check()
                redis_status = health.get("status", "disabled")
            except Exception:
                redis_status = "error"
        else:
            try:
                from app.services.redis_service import RedisService
                rs = RedisService()
                health = await rs.health_check()
                redis_status = health.get("status", "disabled")
            except Exception:
                redis_status = "disabled"

        # Always cross-check with a fresh RedisService instance to avoid stale app.state.redis
        fresh_redis_status = "disabled"
        try:
            from app.services.redis_service import RedisService
            fresh = RedisService()
            fresh_health = await fresh.health_check()
            fresh_redis_status = fresh_health.get("status", "disabled")
            with open("C:/Void/ZQM-AI-Master/debug_redis_status.txt", "a", encoding="utf-8") as f:
                f.write(f"fresh_redis_status={fresh_redis_status} health={fresh_health}\n")
            if fresh_redis_status == "ok":
                redis_status = fresh_redis_status
        except Exception as exc:
            with open("C:/Void/ZQM-AI-Master/debug_redis_status.txt", "a", encoding="utf-8") as f:
                f.write(f"fresh redis exception: {exc}\n")
            pass

        external_services = {
            "garden": "healthy" if garden_ok else "unreachable",
            "observability": "healthy" if obs_ok else "unreachable",
        }

        return HealthStatus(
            status=status,
            zqm_ai_id=self.ZQM_AI_ID,
            version=settings.app_version,
            environment=os.getenv("ENVIRONMENT", settings.environment),
            uptime_seconds=round(uptime, 1),
            database="healthy" if database_ok else "unreachable",
            redis=redis_status,
            garden="healthy" if garden_ok else "unreachable",
            flatspace="healthy" if flatspace_ok else "unreachable",
            observability="healthy" if obs_ok else "unreachable",
            self_apply="on" if self_apply_on else "off",
            external_services=external_services,
            active_tasks=len(self._active_tasks),
            total_agents=agent_stats["total"],
            cache_size=cache_stats["current_size"],
            memory_mb=round(mem, 1) if mem else None,
            cpu_percent=round(cpu, 1) if cpu else None,
        )

    async def get_dashboard(self) -> DashboardStats:
        """Return dashboard statistics."""
        agent_stats = self.registry.stats()
        cache_stats = self.cache.stats()
        uptime = (
            (datetime.now(timezone.utc) - self._started_at).total_seconds()
            if self._started_at
            else 0.0
        )

        try:
            garden_nodes = await asyncio.wait_for(
                self.garden.get_online_nodes(), timeout=6.0
            )
        except (asyncio.TimeoutError, Exception):
            garden_nodes = []

        total = self._tasks_completed + self._tasks_failed
        success_rate = self._tasks_completed / total if total > 0 else 1.0

        return DashboardStats(
            tasks_total=total,
            tasks_active=len(self._active_tasks),
            tasks_completed_today=self._tasks_completed,
            tasks_failed_today=self._tasks_failed,
            task_success_rate=round(success_rate, 4),
            agents_total=agent_stats["total"],
            agents_idle=agent_stats["idle"],
            agents_busy=agent_stats["busy"],
            agents_offline=agent_stats["offline"],
            tokens_used_today=self._total_tokens,
            uptime_seconds=round(uptime, 1),
            cache_hit_rate=round(cache_stats["hit_rate"], 4),
            garden_nodes_online=len(garden_nodes),
            recent_tasks=[
                t.model_dump() for t in await self.get_durable_history(limit=10)
            ],
        )

    async def get_info(self) -> Dict[str, Any]:
        """Return system identity and configuration info."""
        return {
            "zqm_ai_id": self.ZQM_AI_ID,
            "employee_id": self.EMPLOYEE_ID,
            "primary_garden": self.PRIMARY_GARDEN,
            "version": settings.app_version,
            "environment": settings.environment,
            "default_cognitive_level": settings.default_cognitive_level,
            "default_ai_provider": settings.default_ai_provider,
            "garden_nodes": settings.garden_nodes,
            "capabilities": [
                "task_orchestration",
                "multi_agent_processing",
                "cognitive_processing",
                "memory_caching",
                "garden_distribution",
                "flatspace_persistence",
                "observability_reporting",
            ],
        }

    # ── Learning ──────────────────────────────────────────────────────────────

    async def learn_from_execution(self, task: Task) -> None:
        """
        Extract learning signals from completed tasks and update
        VoidCache / FLATSPACE knowledge stores.
        """
        if task.status != TaskStatus.COMPLETED or not task.result:
            return

        if task.cognitive_trace:
            trace = task.cognitive_trace
            log.info(
                "Learning from execution",
                task_id=task.task_id,
                agents=len(trace.agents_used),
                tokens=trace.total_tokens,
                level=trace.level,
            )

        # Store in FLATSPACE BitGarden for hot recall
        try:
            await self.flatspace.store(
                key=f"task_result:{task.task_id}",
                value={
                    "input": task.input,
                    "output": task.result.output if task.result else None,
                    "cognitive_level": task.cognitive_level,
                    "duration_ms": task.duration_ms,
                },
                tier="bitgarden",
            )
        except Exception as exc:
            log.warning("FLATSPACE store failed during learning", error=str(exc))

    async def generate_mcp(self, task_id: str) -> Dict[str, Any]:
        """
        Generate a Machine-Checkable Proof (MCP) for a completed task.
        Returns a signed audit record suitable for WaxCell immutable storage.
        """
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        mcp = {
            "mcp_id": f"mcp-{uuid.uuid4().hex[:12]}",
            "task_id": task_id,
            "zqm_ai_id": self.ZQM_AI_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": task.status,
            "cognitive_level": task.cognitive_level,
            "agents_used": task.cognitive_trace.agents_used if task.cognitive_trace else [],
            "duration_ms": task.duration_ms,
            "verified": task.status == TaskStatus.COMPLETED,
        }

        # Store in WaxCell immutable audit tier
        try:
            await self.flatspace.store(
                key=f"mcp:{mcp['mcp_id']}",
                value=mcp,
                tier="waxcell",  # Immutable audit storage
            )
        except Exception as exc:
            log.warning("MCP WaxCell store failed", error=str(exc))

        return mcp

    # ── Constant Self-Improvement ─────────────────────────────────────────────

    def _persist_self_improvement_local(self, record: Dict[str, Any]) -> None:
        """
        Fallback persistence for self-improvement findings when FLATSPACE is
        unreachable. Appends one JSON line to self_improvement_log.jsonl
        beside the app package so findings are never lost.
        """
        try:
            from pathlib import Path
            base = Path(__file__).resolve().parent.parent  # app/
            log_path = base / "self_improvement_log.jsonl"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    **record,
                }, default=str) + "\n")
            log.info("Self-improvement finding persisted locally", path=str(log_path))
        except Exception as exc:
            log.warning("Self-improvement local persist failed", error=str(exc))

    async def _self_improvement_loop(self) -> None:
        """
        Background loop: The Void continuously critiques and proposes upgrades
        to itself. Each cycle convenes a real agent panel via the live Ollama
        backend, grounded in recent task history, and persists findings to the
        FLATSPACE bitgarden tier for durable recall. Runs on a configurable cadence
        (env ZQM_SELF_IMPROVE_INTERVAL_S, default 600). Fail-soft: any error in
        a cycle is logged and skipped; the loop never crashes the orchestrator.
        """
        interval = max(60, int(os.getenv("ZQM_SELF_IMPROVE_INTERVAL_S", "600")))
        log.info("Self-improvement loop started", interval_s=interval)
        # Rotate the specialist so different facets get reviewed over time.
        cycle = [
            AgentType.CODE, AgentType.SECURITY, AgentType.INFRASTRUCTURE,
            AgentType.GARDEN, AgentType.LEARNING, AgentType.HYDROLOGY,
        ]
        idx = 0
        last_findings_summary: List[str] = []
        while True:
            try:
                await asyncio.sleep(interval)
                await self._self_critique(cycle[idx % len(cycle)], last_findings_summary)
                idx += 1
            except asyncio.CancelledError:
                log.info("Self-improvement loop cancelled")
                raise
            except Exception as exc:
                log.warning("Self-improvement cycle failed (skipping)", error=str(exc))
                await asyncio.sleep(30)

    async def _self_critique(self, specialist: AgentType, last_findings_summary: List[str]) -> None:
        """
        One self-improvement cycle: convene Reasoning + a rotating specialist +
        Synthesis to critique The Void and propose ONE concrete, code-level
        upgrade. Findings are persisted to FLATSPACE and logged.
        """
        panel = []
        for at in (AgentType.REASONING, specialist, AgentType.SYNTHESIS):
            ags = await self.registry.select_best(agent_type=at, count=1)
            if ags:
                panel.append(ags[0])
        if len(panel) < 2:
            return

        # Ground the critique in real recent activity.
        recent = list(self._task_history.values())[-8:]
        history_blob = "; ".join(
            f"[{t.cognitive_level}] {t.input[:100]} -> {t.status.value}"
            for t in recent
        ) or "(no tasks executed yet)"

        # Suppress duplicate-finding loops: reuse the prior finding categories
        # when no actionable patch was applied in the last cycle.
        applied_recently = bool(last_findings_summary)
        reuse_note = ""
        if applied_recently:
            reuse_note = (
                "Prior cycle finding categories: "
                + ", ".join(last_findings_summary[-5:])
                + ". If these are still the highest-leverage issues, return a short confirmation instead of repeating them."
            )

        topic = (
            "Self-improvement critique of The Void AI orchestrator. "
            f"Recent task history: {history_blob}. "
            f"Agent pool size: {self.registry.stats()['total']}. "
            "Identify the single highest-leverage weakness in architecture, "
            "agent pool, or task routing, and propose ONE concrete code-level "
            "upgrade. Be specific and terse (under 120 words). "
            "Describe the change in plain prose: do NOT emit any PATCH/fenced-edit "
            "syntax or template placeholders. Never output sample text like "
            "<rel path under app/> or <exact old text>. Only emit structured "
            "EXPAND_AGENT / EXPAND_TOOL directives when you are certain the "
            "agent type and capabilities are valid. "
            + reuse_note
        )

        try:
            # Route through the mesh Ollama router (failover + degraded
            # substitution) instead of the bare localhost base_url, so a
            # crashed Ollama degrades gracefully rather than 500'ing the
            # autonomous self-improve loop.
            from app.services.mesh_ollama import router as mesh_ollama
            findings = []
            for ag in panel:
                msg = (
                    f"TOPIC: {topic}\n\n"
                    f"You are {ag.name} ({ag.agent_type}). "
                    "Give your critique + one concrete upgrade proposal."
                )
                data = await mesh_ollama.chat(
                    model=settings.ollama_default_model,
                    messages=[
                        {"role": "system", "content": ag.system_prompt},
                        {"role": "user", "content": msg},
                    ],
                    timeout=90.0,
                    options={"temperature": 0.6},
                )
                text = data.get("message", {}).get("content", "").strip()
                if text:
                    findings.append(f"[{ag.name}] {text[:800]}")
            if not findings:
                return
                try:
                    result = await self.flatspace.store(
                        key=f"self_improvement:{datetime.now(timezone.utc).isoformat()}",
                        value={
                            "cycle_specialist": specialist.value,
                            "panel": [a.name for a in panel],
                            "findings": findings,
                        },
                        tier="bitgarden",
                    )
                    # FlatSpaceService fails SOFT (returns a dict, does not raise)
                    # when the backend is unreachable — detect that too.
                    if isinstance(result, dict) and not result.get("success", True):
                        raise RuntimeError(str(result.get("error", "FLATSPACE store returned failure")))
                except Exception as exc:
                    log.warning("Self-improvement FLATSPACE store failed", error=str(exc))
                    # Fallback: persist locally so findings survive a down FLATSPACE.
                    self._persist_self_improvement_local({
                        "cycle_specialist": specialist.value,
                        "panel": [a.name for a in panel],
                        "findings": findings,
                    })
                log.info(
                    "Self-improvement cycle complete",
                    specialist=specialist.value,
                    panel=[a.name for a in panel],
                    findings=len(findings),
                )
                # Publish cycle completion to the live event bus (SSE).
                try:
                    from app.core.event_bus import bus
                    await bus.publish("self_improve", {
                        "specialist": specialist.value,
                        "panel": [a.name for a in panel],
                        "findings": len(findings),
                    })
                except Exception:
                    pass
                # P2: if the panel emitted a structured PATCH block and
                # ZQM_SELF_APPLY is on, validate + promote safely.
                await self_apply.try_apply_findings(self, findings)
                # P4a: consume findings to tune the LIVE agent pool (gated).
                await system_integration.integrate_findings(self)
                # P6: SCAN findings for self-expansion directives
                # (EXPAND_AGENT / EXPAND_TOOL / PATCH) and apply if gated on.
                try:
                    from app.orchestrator import self_expand
                    blob = "\n".join(findings) if isinstance(findings, list) else str(findings)
                    summary = await self_expand.process_findings(self, blob)
                    log.info("Self-expansion scan", **{k: v for k, v in summary.items()
                                                        if k in ("self_apply", "proposed", "applied")})
                except Exception as exc:
                    log.warning("Self-expansion scan failed", error=str(exc))
                # P9: SELF-EXECUTING improvement — run The Void's own library of
                # known safe self-patches (deterministic; does not depend on the
                # LLM panel emitting fenced blocks). Appliable fixes are applied
                # + audited; the rest stay propose-only.
                try:
                    from app.orchestrator import self_improve
                    p9 = await self_improve.scan_and_improve(self)
                    log.info("Self-improvement (P9) scan", **{k: v for k, v in p9.items()
                                                              if k in ("self_apply", "proposed", "applied")})
                except Exception as exc:
                    log.warning("Self-improvement (P9) scan failed", error=str(exc))
                # P7: SCAN findings for REPLICATE: directives (self-replication).
                try:
                    from app.orchestrator import self_replicate
                    blob = "\n".join(findings) if isinstance(findings, list) else str(findings)
                    rsummary = await self_replicate.process_findings(self, blob, confirm=False)
                    log.info("Self-replication scan", **{k: v for k, v in rsummary.items()
                                                          if k in ("self_apply", "proposed", "applied")})
                except Exception as exc:
                    log.warning("Self-replication scan failed", error=str(exc))

                # Track concise finding categories to suppress duplicate loops.
                if findings:
                    last_findings_summary.append("; ".join(findings[-3:])[:180])
                    if len(last_findings_summary) > 50:
                        del last_findings_summary[: len(last_findings_summary) - 50]
        except Exception as exc:
            log.warning("Self-critique backend call failed", error=str(exc))

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _post_execution(self, task: Task, result: TaskResult) -> None:
        """Fire-and-forget post-execution tasks."""
        try:
            await self.learn_from_execution(task)
        except Exception as exc:
            log.warning("Post-execution learning failed", error=str(exc))

        try:
            await self.observability.push_task_metric(task, result)
        except Exception as exc:
            log.warning("Observability push failed", error=str(exc))

    async def _warm_up_connections(self) -> None:
        """Non-blocking connection warmup at startup."""
        try:
            await self.garden.health_check()
            await self.flatspace.health_check()
            await self.observability.health_check()
            log.info("ZQM subsystem connections warmed up")
        except Exception as exc:
            log.warning("Subsystem warmup failed (will retry on demand)", error=str(exc))

    async def _wait_for_active_tasks(self) -> None:
        while self._active_tasks:
            await asyncio.sleep(0.5)
