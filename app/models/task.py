"""
The Void AI Orchestration System — Task Models
Version: 2.0.0 | ZQM Computing LLC

Pydantic schemas for AI task lifecycle: request → execution → result.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Enumerations ──────────────────────────────────────────────────────────────

class CognitiveLevel(str, Enum):
    """Processing depth level for the CognitiveProcessor."""
    BASIC = "basic"           # Level 1: Single-agent direct response
    ADVANCED = "advanced"     # Level 2: Multi-agent synthesis
    NEURAL = "neural"         # Level 3: Deep processing with memory
    AUTONOMOUS = "autonomous" # Level 4: Self-directed with learning


class TaskStatus(str, Enum):
    """Lifecycle states for a task."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    """Scheduling priority for ZQM Garden distribution."""
    CRITICAL = "critical"   # weight=100, max_wait=5s
    HIGH = "high"           # weight=75,  max_wait=30s
    NORMAL = "normal"       # weight=50,  max_wait=120s
    LOW = "low"             # weight=25,  max_wait=600s


class InputMethod(str, Enum):
    """Source input method — maps to ZQM Garden compute task types."""
    CHAT = "chat"
    MAP_INPUT = "map_input"
    FILE_UPLOAD = "file_upload"
    CALCULATORS = "calculators"
    WIZARDS = "wizards"
    VIDEO_CONSULTATION = "video_consultation"
    API_INTEGRATIONS = "api_integrations"
    EMAIL_PARSER = "email_parser"
    SMS_SERVICE = "sms_service"
    QR_CODE_SYSTEM = "qr_code_system"
    MOBILE_FIELD = "mobile_field_collection"
    DIRECT_API = "direct_api"


# ── Request Models ────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    """Incoming task submission payload."""

    task_id: str = Field(
        default_factory=lambda: f"task-{uuid.uuid4().hex[:12]}",
        description="Unique task identifier (auto-generated if not provided)",
    )
    input: str = Field(..., description="Primary task input / prompt / instruction")
    context: dict[str, Any] | None = Field(
        default=None,
        description="Additional context, metadata, or parameters",
    )
    cognitive_level: CognitiveLevel = Field(
        default=CognitiveLevel.AUTONOMOUS,
        description="Processing depth level",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL,
        description="Task scheduling priority",
    )
    input_method: InputMethod = Field(
        default=InputMethod.DIRECT_API,
        description="Source system that originated this task",
    )
    agents: list[str] | None = Field(
        default=None,
        description="Specific agent IDs to use (auto-selected if None)",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=128000,
        description="Max tokens for AI response",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="AI sampling temperature",
    )
    stream: bool = Field(default=False, description="Stream response tokens")
    timeout: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Task timeout in seconds",
    )
    model: str | None = Field(
        default=None,
        description="Preferred Ollama model from the mesh catalog (e.g. phi3:mini)",
    )
    provider: str | None = Field(
        default=None,
        description="Override AI provider for this task (ollama | openai | anthropic | local_deterministic)",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID for multi-turn conversations",
    )
    user_id: str | None = Field(
        default=None,
        description="User ID for attribution and personalization",
    )
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags for filtering")
    tool_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional explicit JSON Schema for tool-format outputs. If provided, model outputs are validated against this schema before execution.",
    )

    @field_validator("input")
    @classmethod
    def input_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Task input cannot be empty")
        return stripped


class TaskUpdate(BaseModel):
    """Partial update for an existing task (e.g., cancel)."""

    status: TaskStatus | None = None
    context: dict[str, Any] | None = None
    tags: list[str] | None = None


# ── Domain Models ─────────────────────────────────────────────────────────────

class AgentExecution(BaseModel):
    """Record of a single agent's contribution to a task."""

    agent_id: str
    agent_type: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    output: Any | None = None
    tokens_used: int | None = None
    error: str | None = None
    efficiency_score: float | None = Field(default=None, ge=0.0, le=1.0)
    tool_trace: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool/integration actions this agent took to reach The Void's systems "
                    "(e.g. flatspace_search, ollama_models). Each entry: {tool, args, ok, result}.",
    )
    # reconstruction runtime metrics
    step_hashes: list[str] = Field(default_factory=list, description="Short hashes of intermediate reasoning/output snapshots for variance probing")
    reconstruction_variance: float | None = Field(default=None, ge=0.0, le=1.0, description="Cross-reconstruction semantic variance; low values indicate static-norm collapse")
    reasoning_step_count: int | None = Field(default=None, description="Number of explicit reasoning steps detected in the trace")
    reasoning_step_density: float | None = Field(default=None, ge=0.0, description="Reasoning steps per 100 output tokens; low density flags output-only behavior")


class CognitiveTrace(BaseModel):
    """Full cognitive processing audit trail for a task."""

    level: CognitiveLevel
    agents_used: list[str] = Field(default_factory=list)
    executions: list[AgentExecution] = Field(default_factory=list)
    synthesis_applied: bool = False
    memory_reads: int = 0
    memory_writes: int = 0
    garden_nodes_used: list[str] = Field(default_factory=list)
    total_tokens: int = 0
    routing: dict[str, Any] = Field(
        default_factory=dict,
        description="Routing decision metadata: original_level, routed_level, reason, input_method, keyword_triggers",
    )
    input_truncated: bool = False
    input_truncation_reason: str | None = None


class Task(BaseModel):
    """Full task entity including status and results."""

    task_id: str
    input: str
    context: dict[str, Any] | None = None
    cognitive_level: CognitiveLevel = CognitiveLevel.ADVANCED
    priority: TaskPriority = TaskPriority.NORMAL
    input_method: InputMethod = InputMethod.DIRECT_API
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    session_id: str | None = None
    user_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    result: TaskResult | None = None
    cognitive_trace: CognitiveTrace | None = None
    error: str | None = None
    retry_count: int = 0
    falsification_report: dict[str, Any] | None = Field(default=None, description="Falsification protocol audit result for this task")


class TaskResult(BaseModel):
    """The output/result of a completed task."""

    task_id: str
    output: Any = Field(..., description="Primary output — text, data, or structured object")
    output_type: str = Field(default="text", description="text | json | binary | stream")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Model-reported confidence in this output")
    outcome_verified: bool | None = Field(default=None, description="Whether the result was checked against ground truth or a deterministic validator")
    calibration_offset: float | None = Field(default=None, description="|confidence - accuracy| after verification; lower is better calibrated")
    diversity_ratio: float | None = Field(default=None, ge=0.0, le=1.0, description="Unique-token ratio across recent agent outputs for this task; low values may indicate attractor collapse")
    reconstruction_variance: float | None = Field(default=None, ge=0.0, le=1.0, description="Cross-reconstruction semantic variance; low values indicate static-norm collapse")
    reasoning_step_count: int | None = Field(default=None, description="Number of explicit reasoning steps detected in the trace")
    reasoning_step_density: float | None = Field(default=None, ge=0.0, description="Reasoning steps per 100 output tokens; low density flags output-only behavior")
    model_used: str | None = None
    provider_used: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    learned: bool = Field(default=False, description="Whether ZQM_AI learned from this result")


# ── Prediction Models ─────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """Request for AI inference/prediction."""

    input: str = Field(..., description="Input text or data to run inference on")
    model: str | None = None
    provider: str | None = None
    task_type: str = Field(default="completion", description="completion | classification | embedding | extraction")
    parameters: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class PredictResult(BaseModel):
    """Prediction/inference output."""

    output: Any
    model: str
    provider: str
    tokens_used: int | None = None
    latency_ms: int | None = None
    confidence: float | None = None


# ── Training Models ───────────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    """Request to train/fine-tune or feed knowledge to ZQM_AI."""

    data: list[dict[str, Any]] = Field(..., description="Training examples or knowledge records")
    domain: str = Field(default="general", description="Knowledge domain (e.g. gis, hydrology, network)")
    method: str = Field(default="memory", description="memory | fine-tune | few-shot | rag")
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainResult(BaseModel):
    """Training job result."""

    job_id: str = Field(default_factory=lambda: f"train-{uuid.uuid4().hex[:8]}")
    status: str = "accepted"
    records_processed: int = 0
    domain: str
    method: str
    message: str = "Training job submitted successfully"


# Rebuild forward refs
Task.model_rebuild()
