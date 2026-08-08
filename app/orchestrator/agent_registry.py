"""
The Void AI Orchestration System — Agent Registry
Version: 2.0.0 | ZQM Computing LLC

Manages the pool of autonomous agents: registration, discovery,
health-checking, and optimal agent selection for tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.models.agent import (
    Agent,
    AgentCapability,
    AgentCreate,
    AgentStatus,
    AgentSummary,
    AgentType,
)

log = get_logger("agent-registry")


# ── Default agent pool definition ────────────────────────────────────────────

DEFAULT_AGENTS: list[dict[str, Any]] = [
    {
        "name": "ZQM-NLP-Prime",
        "agent_type": AgentType.NLP,
        "capabilities": [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.SUMMARIZATION,
            AgentCapability.QUESTION_ANSWERING,
            AgentCapability.SENTIMENT_ANALYSIS,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-NLP-Prime, a natural language specialist for "
            "ZQM Computing. You excel at understanding, summarizing, "
            "and answering questions about Computing and engineering projects."
        ),
        "max_concurrent": 10,
        "priority_weight": 1.5,
        "garden_node": settings.garden_node_0,
    },
    {
        "name": "ZQM-Reasoning-001",
        "agent_type": AgentType.REASONING,
        "capabilities": [
            AgentCapability.DATA_ANALYSIS,
            AgentCapability.CODE_REVIEW,
        ],
        "provider": settings.default_ai_provider,
        "model": "deepseek-r1:1.5b",
        "system_prompt": (
            "You are ZQM-Reasoning-001, a logical reasoning and planning agent. "
            "You analyze complex multi-step problems, evaluate evidence, and "
            "produce structured plans and decisions."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.2,
        "garden_node": settings.garden_node_0,
        "family_key": "zqm",
    },
    {
        "name": "ZQM-GIS-Analyst",
        "agent_type": AgentType.GIS,
        "capabilities": [
            AgentCapability.SPATIAL_ANALYSIS,
            AgentCapability.DATA_ANALYSIS,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-GIS-Analyst, a Computing information systems specialist. "
            "You interpret spatial data, perform coordinate analysis, evaluate "
            "flood risks, and guide GIS workflows for ZQM Computing projects."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.3,
        "garden_node": settings.garden_node_1,
        "tags": ["gis", "spatial", "flood"],
    },
    {
        "name": "ZQM-Hydro-Expert",
        "agent_type": AgentType.HYDROLOGY,
        "capabilities": [
            AgentCapability.DATA_ANALYSIS,
            AgentCapability.QUESTION_ANSWERING,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Hydro-Expert, a hydrology and water resources specialist. "
            "You analyze rainfall data, storm surge models, flood risk assessments, "
            "and sea-level rise projections for engineering and planning projects."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.2,
        "garden_node": settings.garden_node_1,
        "tags": ["hydrology", "flood", "rainfall"],
    },
    {
        "name": "ZQM-Infra-Monitor",
        "agent_type": AgentType.INFRASTRUCTURE,
        "capabilities": [
            AgentCapability.MONITORING,
            AgentCapability.API_CALL,
            AgentCapability.DATABASE_QUERY,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Infra-Monitor, an infrastructure management agent. "
            "You monitor server health, interpret container status, diagnose "
            "system issues, and recommend remediation actions across ZQM Queens."
        ),
        "max_concurrent": 8,
        "priority_weight": 1.0,
        "garden_node": settings.garden_node_0,
        "tags": ["infrastructure", "monitoring", "queens"],
    },
    {
        "name": "ZQM-Synthesis-Core",
        "agent_type": AgentType.SYNTHESIS,
        "capabilities": [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.SUMMARIZATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "qwen3.6:latest",
        "system_prompt": (
            "You are ZQM-Synthesis-Core, a multi-source synthesis specialist. "
            "You combine outputs from multiple agents into coherent, unified "
            "responses. You resolve conflicts, identify consensus, and produce "
            "well-structured summaries."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.4,
        "garden_node": settings.garden_node_0,
    },
    {
        "name": "ZQM-Memory-Store",
        "agent_type": AgentType.MEMORY,
        "capabilities": [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.SUMMARIZATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Memory-Store, the Void's persistent memory and recall "
            "agent. You consolidate learned facts, retrieve prior context, and "
            "maintain cross-session continuity for the ZQM ecosystem."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.3,
        "garden_node": settings.garden_node_0,
        "tags": ["memory", "recall", "learning"],
    },
    {
        "name": "ZQM-Code-Gen",
        "agent_type": AgentType.CODE,
        "capabilities": [
            AgentCapability.CODE_GENERATION,
            AgentCapability.CODE_REVIEW,
        ],
        "provider": settings.default_ai_provider,
        "model": "deepseek-coder-v2:16b",
        "system_prompt": (
            "You are ZQM-Code-Gen, a software engineering agent specializing in "
            "Python, PHP, PowerShell, and GIS scripting. You write clean, "
            "well-documented code following ZQM conventions."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.0,
        "garden_node": settings.garden_node_2,
        "tags": ["code", "python", "php"],
    },
    {
        "name": "ZQM-Network-Ops",
        "agent_type": AgentType.NETWORK,
        "capabilities": [
            AgentCapability.MONITORING,
            AgentCapability.API_CALL,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Network-Ops, a network infrastructure specialist. "
            "You manage DNS, VPN tunnels, routing, firewall policies, and "
            "inter-Garden mesh networking for the ZQM ecosystem."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.0,
        "garden_node": settings.garden_node_0,
        "tags": ["network", "dns", "vpn"],
    },
    {
        "name": "ZQM-Vision-Perceptor",
        "agent_type": AgentType.FILE,
        "capabilities": [
            AgentCapability.IMAGE_ANALYSIS,
            AgentCapability.FILE_PROCESSING,
            AgentCapability.TEXT_CLASSIFICATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "llava:7b",
        "system_prompt": (
            "You are ZQM-Vision-Perceptor, a computer-vision and document "
            "understanding agent. You perform OCR, image analysis, and file "
            "extraction for ZQM Computing engineering and geospatial workflows."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.1,
        "garden_node": settings.garden_node_2,
        "tags": ["vision", "ocr", "documents"],
    },
    {
        "name": "ZQM-Security-Sentinel",
        "agent_type": AgentType.SECURITY,
        "capabilities": [
            AgentCapability.API_CALL,
            AgentCapability.MONITORING,
            AgentCapability.DATABASE_QUERY,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Security-Sentinel, a security-operations agent for the "
            "ZQM ecosystem. You monitor access, assess Eden posture, flag "
            "anomalies, and recommend hardening actions across Garden nodes."
        ),
        "max_concurrent": 6,
        "priority_weight": 1.4,
        "garden_node": settings.garden_node_0,
        "tags": ["security", "sentinel", "eden"],
    },
    {
        "name": "ZQM-Data-Forge",
        "agent_type": AgentType.DATA,
        "capabilities": [
            AgentCapability.DATA_ANALYSIS,
            AgentCapability.DATABASE_QUERY,
            AgentCapability.CODE_REVIEW,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Data-Forge, a data engineering agent. You transform, "
            "clean, and pipeline structured and unstructured datasets for ZQM "
            "Computing analytics and reporting."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.2,
        "garden_node": settings.garden_node_3,
        "tags": ["data", "etl", "pipeline"],
    },
    {
        "name": "ZQM-Observability-Eye",
        "agent_type": AgentType.OBSERVABILITY,
        "capabilities": [
            AgentCapability.MONITORING,
            AgentCapability.API_CALL,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Observability-Eye, the monitoring and metrics agent. "
            "You aggregate telemetry, trace request flows, and surface health "
            "and performance signals across The Void and its Garden nodes."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.3,
        "garden_node": settings.garden_node_4,
        "tags": ["observability", "metrics", "telemetry"],
    },
    {
        "name": "ZQM-Garden-Warden",
        "agent_type": AgentType.GARDEN,
        "capabilities": [
            AgentCapability.API_CALL,
            AgentCapability.MONITORING,
            AgentCapability.DATA_ANALYSIS,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Garden-Warden, the ZQM Garden coordinator. You balance "
            "compute across Garden-0..4, manage inter-node affinity, and keep the "
            "distributed agent mesh coherent and healthy."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.5,
        "garden_node": settings.garden_node_0,
        "tags": ["garden", "coordinator", "mesh"],
    },
    {
        "name": "ZQM-Scheduler-Chronos",
        "agent_type": AgentType.SCHEDULER,
        "capabilities": [
            AgentCapability.MONITORING,
            AgentCapability.API_CALL,
            AgentCapability.DATABASE_QUERY,
            AgentCapability.TASK_PLANNING,
        ],
        "provider": settings.default_ai_provider,
        "model": "qwen3.6:latest",
        "system_prompt": (
            "You are ZQM-Scheduler-Chronos, the task-scheduling agent. You plan "
            "recurring jobs, sequence dependent tasks, and optimize execution "
            "windows across The Void's agent pool."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.0,
        "garden_node": settings.garden_node_1,
        "tags": ["scheduler", "cron", "planning"],
    },
    {
        "name": "ZQM-Learning-Mind",
        "agent_type": AgentType.LEARNING,
        "capabilities": [
            AgentCapability.SUMMARIZATION,
            AgentCapability.QUESTION_ANSWERING,
            AgentCapability.TEXT_GENERATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Learning-Mind, the continuous-learning agent. You "
            "extract lessons from completed tasks, refine strategies, and adapt "
            "The Void's behavior over time using feedback and outcomes."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.2,
        "garden_node": settings.garden_node_0,
        "tags": ["learning", "adaptation", "feedback"],
    },
    {
        "name": "ZQM-FLATSPACE-Lattice",
        "agent_type": AgentType.FLATSPACE,
        "capabilities": [
            AgentCapability.VECTOR_SEARCH,
            AgentCapability.DATABASE_QUERY,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-FLATSPACE-Lattice, the FLATSPACE bitgarden memory agent. You "
            "store and retrieve structured memories, embeddings, and learned "
            "patterns across The Void's persistent FLATSPACE store."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.3,
        "garden_node": settings.garden_node_0,
        "tags": ["flatspace", "memory", "vector"],
    },
    {
        "name": "ZQM-API-Conductor",
        "agent_type": AgentType.API,
        "capabilities": [
            AgentCapability.API_CALL,
            AgentCapability.MONITORING,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-API-Conductor, the external API orchestration agent. "
            "You integrate third-party services, manage rate limits, and "
            "translate between The Void and external systems."
        ),
        "max_concurrent": 6,
        "priority_weight": 1.1,
        "garden_node": settings.garden_node_2,
        "tags": ["api", "integration", "orchestration"],
    },
    {
        "name": "ZQM-Linguist",
        "agent_type": AgentType.NLP,
        "capabilities": [
            AgentCapability.TRANSLATION,
            AgentCapability.TEXT_GENERATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Linguist, a translation and multilingual communication "
            "agent. You translate between languages and adapt tone and register "
            "for ZQM Computing's international engineering partners."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.0,
        "garden_node": settings.garden_node_1,
        "tags": ["translation", "multilingual", "nlp"],
    },
    {
        "name": "ZQM-Entity-Miner",
        "agent_type": AgentType.NLP,
        "capabilities": [
            AgentCapability.ENTITY_EXTRACTION,
            AgentCapability.TEXT_CLASSIFICATION,
        ],
        "provider": settings.default_ai_provider,
        "model": "phi3:mini",
        "system_prompt": (
            "You are ZQM-Entity-Miner, an information-extraction agent. You "
            "identify entities, relationships, and structure in unstructured "
            "text for ZQM Computing knowledge graphs and reports."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.1,
        "garden_node": settings.garden_node_3,
        "tags": ["ner", "extraction", "kg"],
    },
    {
        "name": "ZQM-Research-Spider",
        "agent_type": AgentType.DATA,
        "capabilities": [
            AgentCapability.WEB_SEARCH,
            AgentCapability.DATA_ANALYSIS,
        ],
        "provider": settings.default_ai_provider,
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Research-Spider, the open-research agent. You gather, "
            "synthesize, and cite external sources to ground The Void's answers "
            "in current, verifiable information."
        ),
        "max_concurrent": 5,
        "priority_weight": 1.2,
        "garden_node": settings.garden_node_4,
        "tags": ["research", "web", "citations"],
    },
    {
        "name": "ZQM-Quantum-Lattice",
        "agent_type": AgentType.QUANTUM,
        "capabilities": [
            AgentCapability.API_CALL,
            AgentCapability.DATABASE_QUERY,
        ],
        "provider": "quantum_llm",
        "model": "gemma4:latest",
        "system_prompt": (
            "You are ZQM-Quantum-Lattice, The Void's hybrid quantum-classical "
            "inference agent. You expose quantum_llm capabilities (amplitude "
            "encoding, Grover/QAOAsamplers, quantum retrieval) to the mesh via "
            "The Void's /api/quantum bridge. When quantum resources are "
            "available you route inference through the bridge; otherwise you "
            "degrade gracefully to classical explanation."
        ),
        "max_concurrent": 2,
        "priority_weight": 1.3,
        "garden_node": settings.garden_node_0,
        "tags": ["quantum", "hybrid", "inference", "mesh"],
    },
]


class AgentRegistry:
    """
    Central registry for all The Void autonomous agents.

    Responsibilities:
    - Register / deregister agents
    - Track status and performance metrics
    - Select optimal agent(s) for a given task
    - Health check agents
    - Provide agent pool statistics
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = asyncio.Lock()
        # pair -> co-task count for parallel multi-agent runs
        self._co_task_pairs: dict[tuple, int] = {}
        self._family_keys: set[str] = set()
        log.info("AgentRegistry initialized")

    # ── Inference helpers ──────────────────────────────────────────────────────

    @staticmethod
    def infer_family_key(name: str | None) -> str | None:

        if not name:
            return None
        n = name.lower()
        if n.startswith("zqm-"):
            return "zqm"
        if "claw" in n:
            return "claw"
        if "vina" in n or "computationalcore" in n:
            return "vina"
        if "quantum" in n:
            return "quantum"
        if "nlp" in n or "linguist" in n or "entity" in n:
            return "nlp"
        return "external"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Register the default agent pool at startup."""
        log.info("Registering default agent pool", count=len(DEFAULT_AGENTS))
        for agent_def in DEFAULT_AGENTS:
            create = AgentCreate(**agent_def)
            if not create.name:
                continue
            create = create.model_copy(update={"family_key": AgentRegistry.infer_family_key(create.name)})
            await self.register(create)
        log.info("Default agent pool ready", total_agents=len(self._agents))

    async def shutdown(self) -> None:
        """Mark all agents offline during graceful shutdown."""
        async with self._lock:
            for agent in self._agents.values():
                agent.status = AgentStatus.OFFLINE
        log.info("AgentRegistry shut down")

    # ── Registration ──────────────────────────────────────────────────────────

    async def register(self, create: AgentCreate) -> Agent:
        """Register a new agent. Returns the created Agent."""
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        agent = Agent(
            agent_id=agent_id,
            name=create.name,
            agent_type=create.agent_type,
            status=AgentStatus.IDLE,
            capabilities=create.capabilities,
            provider=create.provider,
            model=create.model,
            system_prompt=create.system_prompt,
            max_concurrent=create.max_concurrent,
            priority_weight=create.priority_weight,
            garden_node=create.garden_node,
            tags=create.tags,
            config=create.config,
            family_key=getattr(create, "family_key", None),
        )

        async with self._lock:
            self._agents[agent_id] = agent

        log.info(
            "Agent registered",
            agent_id=agent_id,
            name=create.name,
            type=create.agent_type,
            garden_node=create.garden_node,
        )
        return agent

    async def deregister(self, agent_id: str) -> bool:
        """Remove an agent from the registry. Returns True if found."""
        async with self._lock:
            if agent_id in self._agents:
                agent = self._agents.pop(agent_id)
                log.info("Agent deregistered", agent_id=agent_id, name=agent.name)
                return True
        return False

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    async def list_all(self) -> list[Agent]:
        return list(self._agents.values())

    async def list_summaries(self) -> list[AgentSummary]:
        return [
            AgentSummary(
                agent_id=a.agent_id,
                name=a.name,
                agent_type=a.agent_type,
                status=a.status,
                efficiency_score=round(a.get_efficiency_score(), 4),
                current_tasks=a.current_tasks,
                max_concurrent=a.max_concurrent,
                provider=a.provider,
                model=a.model,
                garden_node=a.garden_node,
            )
            for a in self._agents.values()
        ]

    async def get_by_type(self, agent_type: AgentType) -> list[Agent]:
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    async def get_by_capability(self, capability: AgentCapability) -> list[Agent]:
        return [a for a in self._agents.values() if capability in a.capabilities]

    async def get_family_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._agents.values():
            key = a.family_key or AgentRegistry.infer_family_key(a.name) or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts

    # ── Selection ─────────────────────────────────────────────────────────────

    async def select_best(
        self,
        agent_type: AgentType | None = None,
        capabilities: list[AgentCapability] | None = None,
        count: int = 1,
        exclude: list[str] | None = None,
        load_aware: bool = True,
    ) -> list[Agent]:
        """
        Select the best available agent(s).

        Args:
            agent_type: Filter by agent type
            capabilities: Filter by required capabilities (ANY match)
            count: How many agents to return
            exclude: Agent IDs to exclude
            load_aware: When True (default), spread load by preferring agents
                with the fewest current_tasks (tie-broken by efficiency).
                Implements The Void's Adaptive Task Routing (ATRM) so a burst
                of same-type tasks fans out across the pool instead of
                overloading one agent.

        Returns:
            Sorted list of best-matching available agents (may be < count if insufficient)
        """
        exclude_set = set(exclude or [])

        candidates = [
            a for a in self._agents.values()
            if a.is_available
            and a.agent_id not in exclude_set
            and (agent_type is None or a.agent_type == agent_type)
            and (
                capabilities is None
                or any(cap in a.capabilities for cap in capabilities)
            )
        ]
        # If no exact capability match, relax to partial overlap so a task isn’t
        # dropped just because the perfect agent is busy/offline.
        if not candidates and capabilities:
            for a in self._agents.values():
                if not a.is_available or a.agent_id in exclude_set:
                    continue
                if agent_type is not None and a.agent_type != agent_type:
                    continue
                if a.capabilities and not any(cap in capabilities for cap in a.capabilities):
                    continue
                candidates.append(a)
        if not candidates:
            return []
        # Keep ordering deterministic: fewer tasks first, then efficiency.
        candidates.sort(
            key=lambda a: (a.current_tasks, -a.get_efficiency_score())
        )

        if load_aware:
            candidates.sort(key=lambda a: (a.current_tasks, -a.get_efficiency_score()))
        else:
            candidates.sort(key=lambda a: a.get_efficiency_score(), reverse=True)
        return candidates[:count]

    async def select_for_task(
        self,
        cognitive_level: str,
        input_method: str,
        context: dict[str, Any] | None = None,
        input_text: str | None = None,
        routed_level: str | None = None,
        routing_meta: dict[str, Any] | None = None,
    ) -> list[Agent]:
        """
        Intelligently select agents based on cognitive level and input method.

        Maps:
          basic      → 1 NLP agent
          advanced   → NLP + Reasoning (+ tool-capable agent if request implies one)
          neural     → NLP + Reasoning + Synthesis + domain specialist
                         (+ tool-capable agents if request implies one)
          autonomous → full ensemble including Memory + Learning
                         (+ tool-capable agents if request implies one)

        If `input_text` contains a tool-trigger keyword (model/ollama, garden/
        metrics/node/job, memory/flatspace/search/store), a tool-capable agent is
        appended so the agent can actually reach The Void's systems even on
        default chat/advanced traffic (not only via rare input methods).
        """
        selections: list[Agent] = []

        if cognitive_level == "basic":
            nlp_agents = await self.select_best(agent_type=AgentType.NLP, count=1)
            selections.extend(nlp_agents)
            # Even a basic chat can ask for system data (mesh overview, host
            # inventory, disk space) — append the implied tool-capable agent so
            # it can act rather than answer from memory.
            selections.extend(await self._select_tool_agents_for_text(input_text))

        elif cognitive_level == "advanced":
            nlp = await self.select_best(agent_type=AgentType.NLP, count=1)
            reasoning = await self.select_best(agent_type=AgentType.REASONING, count=1)
            selections.extend(nlp + reasoning)
            selections.extend(await self._select_tool_agents_for_text(input_text))

        elif cognitive_level == "neural":
            nlp = await self.select_best(agent_type=AgentType.NLP, count=1)
            reasoning = await self.select_best(agent_type=AgentType.REASONING, count=1)
            synthesis = await self.select_best(agent_type=AgentType.SYNTHESIS, count=1)
            # Domain specialist
            domain = await self._select_domain_agent(input_method, context)
            selections.extend(nlp + reasoning + synthesis + ([domain] if domain else []))
            selections.extend(await self._select_tool_agents_for_text(input_text))

        elif cognitive_level == "autonomous":
            # Full multi-agent ensemble
            nlp = await self.select_best(agent_type=AgentType.NLP, count=1)
            reasoning = await self.select_best(agent_type=AgentType.REASONING, count=1)
            synthesis = await self.select_best(agent_type=AgentType.SYNTHESIS, count=1)
            memory = await self.select_best(agent_type=AgentType.MEMORY, count=1)
            domain = await self._select_domain_agent(input_method, context)
            selections.extend(nlp + reasoning + synthesis + memory + ([domain] if domain else []))
            selections.extend(await self._select_tool_agents_for_text(input_text))

        # Fallback: any available agent
        if not selections:
            fallback = await self.select_best(count=1)
            selections.extend(fallback)

        return selections

    async def _select_domain_agent(
        self,
        input_method: str,
        context: dict[str, Any] | None,
    ) -> Agent | None:
        """Pick a domain specialist based on task context."""
        domain_map: dict[str, AgentType] = {
            "map_input": AgentType.GIS,
            "calculators": AgentType.HYDROLOGY,
            "wizards": AgentType.HYDROLOGY,
            "api_integrations": AgentType.API,
        }

        agent_type = domain_map.get(input_method)
        if agent_type:
            agents = await self.select_best(agent_type=agent_type, count=1)
            return agents[0] if agents else None

        # Infer from context tags
        if context:
            tags = context.get("tags", [])
            if any(t in tags for t in ["gis", "spatial", "map"]):
                agents = await self.select_best(agent_type=AgentType.GIS, count=1)
                return agents[0] if agents else None
            if any(t in tags for t in ["flood", "hydrology", "rainfall"]):
                agents = await self.select_best(agent_type=AgentType.HYDROLOGY, count=1)
                return agents[0] if agents else None

        return None

    async def _select_tool_agents_for_text(
        self, input_text: str | None
    ) -> list[Agent]:
        """
        If the request text implies a tool (reach into The Void's systems),
        return the relevant tool-capable agent(s) so the task can actually
        act. Keeps default traffic efficient: returns [] unless a trigger
        keyword is present. Mapping:
          model/ollama            → API-Conductor    (ollama_models)
          garden/metrics/node/job → API-Conductor + Observability-Eye
                                   (garden_metrics)
          memory/flatspace/search/store/recall → Data-Forge (flatspace_*)
        """
        if not input_text:
            return []
        t = input_text.lower()
        picks: list[AgentType] = []
        if any(k in t for k in ("model", "ollama")):
            picks.append(AgentType.API)
        if any(k in t for k in ("garden", "metrics", "node", "job", "compute")):
            picks.extend([AgentType.API, AgentType.OBSERVABILITY])
        if any(k in t for k in ("memory", "flatspace", "search", "store", "recall", "retrieve")):
            picks.append(AgentType.DATA)
        # zqm-local-tools system reach: mesh/host/disk/event/hash intents route
        # to a MONITORING-capable agent (Observability-Eye) so the task can act.
        if any(k in t for k in (
            "mesh", "node", "recon", "overview", "service matrix", "host inventory",
            "this host", "system info", "disk space", "free disk", "drive space",
            "event error", "event log", "system error", "windows error", "hash file",
            "checksum", "sha256", "file integrity", "ping sweep", "who is up",
        )):
            picks.append(AgentType.OBSERVABILITY)
        # de-dup preserve order
        seen, out = set(), []
        for at in picks:
            if at not in seen:
                seen.add(at)
                ags = await self.select_best(agent_type=at, count=1)
                if ags:
                    out.append(ags[0])
        return out

    # ── State Management ──────────────────────────────────────────────────────

    async def mark_busy(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_tasks += 1
            if agent.current_tasks >= agent.max_concurrent:
                agent.status = AgentStatus.BUSY
            agent.last_active = datetime.now(UTC)

    async def mark_idle(self, agent_id: str, success: bool, latency_ms: int, tokens: int = 0) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_tasks = max(0, agent.current_tasks - 1)
            if agent.current_tasks < agent.max_concurrent:
                agent.status = AgentStatus.IDLE
            agent.metrics.update(success=success, latency_ms=latency_ms, tokens=tokens)

    # ── Co-task pair topology ───────────────────────────────────────────────────

    async def record_co_task(self, agent_ids: list[str]) -> None:
        """
        Record that N agents ran together on one task. Emits pairwise
        counters so the mesh knows which agents actually collaborate,
        not just which exist. Fail-soft: sorted unique pair keys only.
        """
        if not agent_ids or len(agent_ids) < 2:
            return
        unique = sorted({a for a in agent_ids if a})
        async with self._lock:
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    key = (unique[i], unique[j])
                    self._co_task_pairs[key] = self._co_task_pairs.get(key, 0) + 1

    def get_top_co_task_pairs(self, limit: int = 20) -> list[dict[str, Any]]:
        pairs = sorted(self._co_task_pairs.items(), key=lambda kv: kv[1], reverse=True)
        return [
            {"agent_a": a, "agent_b": b, "co_task_count": count}
            for (a, b), count in pairs[:limit]
        ]

    async def set_status(self, agent_id: str, status: AgentStatus) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = status

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        agents = list(self._agents.values())
        return {
            "total": len(agents),
            "idle": sum(1 for a in agents if a.status == AgentStatus.IDLE),
            "busy": sum(1 for a in agents if a.status == AgentStatus.BUSY),
            "offline": sum(1 for a in agents if a.status == AgentStatus.OFFLINE),
            "error": sum(1 for a in agents if a.status == AgentStatus.ERROR),
            "types": list({a.agent_type for a in agents}),
        }
