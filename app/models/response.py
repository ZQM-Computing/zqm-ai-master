"""
The Void AI Orchestration System — Standard Response Models
Version: 2.1.2 | ZQM Computing LLC

Consistent envelope for all API responses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.version import __version__ as _VOID_VERSION

T = TypeVar("T")


class ZQM_AIResponse(BaseModel, Generic[T]):
    """
    Standard The Void API response envelope.

    All endpoints return this structure so clients can
    uniformly handle success, errors, and metadata.
    """

    success: bool = True
    data: T | None = None
    message: str | None = None
    zqm_ai_id: str = "ZQM-ZQM_AI-004"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = None
    duration_ms: int | None = None
    version: str = _VOID_VERSION

    @classmethod
    def ok(
        cls,
        data: Any = None,
        message: str = "Success",
        request_id: str | None = None,
        duration_ms: int | None = None,
    ) -> ZQM_AIResponse:
        return cls(
            success=True,
            data=data,
            message=message,
            request_id=request_id,
            duration_ms=duration_ms,
        )

    @classmethod
    def fail(
        cls,
        message: str = "An error occurred",
        data: Any = None,
        request_id: str | None = None,
    ) -> ZQM_AIResponse:
        return cls(
            success=False,
            data=data,
            message=message,
            request_id=request_id,
        )


class ErrorDetail(BaseModel):
    """Structured error detail."""

    code: str
    message: str
    field: str | None = None
    context: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response body."""

    success: bool = False
    error: str
    detail: str | None = None
    errors: list[ErrorDetail] = Field(default_factory=list)
    zqm_ai_id: str = "ZQM-ZQM_AI-004"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    success: bool = True
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 1
    zqm_ai_id: str = "ZQM-ZQM_AI-004"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def of(
        cls,
        items: list[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        import math
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


class HealthStatus(BaseModel):
    """System health check response.

    `status` reflects CORE health only (The Void's own datastore, memory, agent
    pool, self-apply gate). Optional EXTERNAL dependencies (ZQM Garden,
    Observability) are reported in `external_services` — a down garden host does
    NOT falsely mark The Void "degraded".
    """

    status: str = "healthy"           # healthy | degraded | unhealthy (CORE only)
    zqm_ai_id: str = "ZQM-ZQM_AI-004"
    version: str = _VOID_VERSION
    environment: str = "development"
    uptime_seconds: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Component health
    database: str = "unknown"          # The Void's real datastore (FLATSPACE SQLite)
    redis: str = "disabled"            # not used by The Void (honest, not "unknown")
    garden: str = "unknown"            # EXTERNAL optional dependency
    flatspace: str = "unknown"         # local tiered memory (core)
    observability: str = "unknown"     # EXTERNAL optional dependency
    self_apply: str = "unknown"        # autonomy gate (core)

    # External optional dependencies, surfaced separately from core status.
    external_services: dict[str, str] = Field(default_factory=dict)

    # Stats
    active_tasks: int = 0
    total_agents: int = 0
    cache_size: int = 0
    memory_mb: float | None = None
    cpu_percent: float | None = None


class DashboardStats(BaseModel):
    """Real-time dashboard statistics."""

    # Task metrics
    tasks_total: int = 0
    tasks_active: int = 0
    tasks_completed_today: int = 0
    tasks_failed_today: int = 0
    task_success_rate: float = 1.0
    avg_task_duration_ms: float = 0.0

    # Agent metrics
    agents_total: int = 0
    agents_idle: int = 0
    agents_busy: int = 0
    agents_offline: int = 0

    # Performance
    tokens_used_today: int = 0
    avg_cognitive_level: str = "advanced"

    # System
    uptime_seconds: float = 0.0
    cache_hit_rate: float = 0.0
    garden_nodes_online: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Recent task history (restart-surviving, from FLATSPACE durable store)
    recent_tasks: list[dict[str, Any]] = []
