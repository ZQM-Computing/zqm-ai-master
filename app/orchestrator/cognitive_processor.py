"""
The Void AI Orchestration System — Cognitive Processor
Version: 2.0.0 | ZQM Computing LLC

The CognitiveProcessor implements 4 levels of AI task execution:

  Level 1 — basic:      Single-agent direct response
  Level 2 — advanced:   Multi-agent with synthesis
  Level 3 — neural:     Deep processing with memory reads/writes
  Level 4 — autonomous: Self-directed execution with learning loop

Each level builds on the previous, adding sophistication at the cost
of latency and resource usage.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logger import get_logger
from app.memory.void_cache import get_void_cache
from app.models.agent import Agent
from app.models.task import (
    AgentExecution,
    CognitiveLevel,
    CognitiveTrace,
    TaskRequest,
    TaskResult,
)
from app.services.cost_tracker import estimate_cost

log = get_logger("cognitive-processor")


class CognitiveProcessor:
    """
    Executes AI tasks through the appropriate cognitive processing pipeline.

    This class is stateless per-call — all state is carried in the
    task request and returned in the CognitiveTrace.
    """

    def __init__(self) -> None:
        self._cache = get_void_cache()
        log.info("CognitiveProcessor initialized")

    # ── Main entry point ──────────────────────────────────────────────────────

    async def process(
        self,
        request: TaskRequest,
        agents: list[Agent],
        registry,     # AgentRegistry — avoid circular import with type hint
    ) -> tuple[TaskResult, CognitiveTrace]:
        """
        Execute a task at the specified cognitive level.

        Returns:
            (TaskResult, CognitiveTrace) — result and full audit trail
        """
        level = request.cognitive_level
        trace = CognitiveTrace(
            level=level,
            agents_used=[a.agent_id for a in agents],
        )

        log.info(
            "Starting cognitive processing",
            task_id=request.task_id,
            level=level,
            agent_count=len(agents),
        )

        try:
            if level == CognitiveLevel.BASIC:
                result = await self._process_basic(request, agents, trace, registry)
            elif level == CognitiveLevel.ADVANCED:
                result = await self._process_advanced(request, agents, trace, registry)
            elif level == CognitiveLevel.NEURAL:
                result = await self._process_neural(request, agents, trace, registry)
            elif level == CognitiveLevel.AUTONOMOUS:
                result = await self._process_autonomous(request, agents, trace, registry)
            else:
                result = await self._process_advanced(request, agents, trace, registry)
        except Exception as exc:
            log.exception("Cognitive processing failed", task_id=request.task_id, error=str(exc))
            result = TaskResult(
                task_id=request.task_id,
                output=f"Processing failed: {exc}",
                output_type="error",
            )

        return result, trace

    # ── Level 1: Basic ────────────────────────────────────────────────────────

    async def _process_basic(
        self,
        request: TaskRequest,
        agents: list[Agent],
        trace: CognitiveTrace,
        registry,
    ) -> TaskResult:
        """Single-agent direct response. Fastest, lowest resource usage."""
        if not agents:
            raise ValueError("No agents available for basic processing")

        agent = agents[0]
        execution, output = await self._run_agent(agent, request, registry)
        trace.executions.append(execution)
        trace.total_tokens = execution.tokens_used or 0

        return TaskResult(
            task_id=request.task_id,
            output=output,
            output_type="text",
            model_used=agent.model,
            provider_used=agent.provider,
            tokens_input=trace.total_tokens,
            tokens_output=execution.tokens_used,
            total_tokens=(trace.total_tokens or 0) + (execution.tokens_used or 0),
            cost_usd=estimate_cost(
                model=agent.model,
                provider=agent.provider,
                tokens_input=trace.total_tokens,
                tokens_output=execution.tokens_used,
            ),
            reconstruction_variance=getattr(execution, "reconstruction_variance", None),
            reasoning_step_count=getattr(execution, "reasoning_step_count", None),
            reasoning_step_density=getattr(execution, "reasoning_step_density", None),
        )

    # ── Level 2: Advanced ─────────────────────────────────────────────────────

    async def _process_advanced(
        self,
        request: TaskRequest,
        agents: list[Agent],
        trace: CognitiveTrace,
        registry,
    ) -> TaskResult:
        """
        Multi-agent parallel execution with synthesis.
        Each agent processes the request independently, then outputs are combined.
        """
        if not agents:
            raise ValueError("No agents available for advanced processing")

        # Run all agents in parallel
        tasks = [self._run_agent(a, request, registry) for a in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: list[AgentExecution] = []
        outputs: list[str] = []

        for i, res in enumerate(results):
            if isinstance(res, Exception):
                log.warning(
                    "Agent execution failed",
                    agent_id=agents[i].agent_id,
                    error=str(res),
                )
                continue
            execution, output = res
            executions.append(execution)
            outputs.append(output)

        trace.executions.extend(executions)
        trace.total_tokens = sum(e.tokens_used or 0 for e in executions)

        # Record co-task topology for multi-agent runs so the mesh knows
        # which agent combinations actually execute together.
        agent_ids = [a.agent_id for a in agents]
        if agent_ids and registry is not None:
            try:
                await registry.record_co_task(agent_ids)
            except Exception:
                pass

        if len(outputs) == 1:
            final_output = outputs[0]
        elif len(outputs) > 1:
            final_output = await self._synthesize(outputs, request, trace)
            trace.synthesis_applied = True
        else:
            final_output = "No agent outputs produced."

        total_tokens = sum(e.tokens_used or 0 for e in executions)
        primary_agent = agents[0] if agents else None

        # Diversity ratio: how different are the agent outputs?
        diversity_ratio = 0.0
        if len(outputs) > 1:
            # simple lexical diversity: ratio of unique tokens to total tokens
            token_sets = []
            for out in outputs:
                tokens = set(out.lower().split())
                if tokens:
                    token_sets.append(tokens)
            if token_sets:
                union = set()
                for ts in token_sets:
                    union |= ts
                intersection = token_sets[0].copy()
                for ts in token_sets[1:]:
                    intersection &= ts
                diversity_ratio = len(intersection) / len(union) if union else 0.0

        return TaskResult(
            task_id=request.task_id,
            output=final_output,
            output_type="text",
            model_used=primary_agent.model if primary_agent else None,
            provider_used=primary_agent.provider if primary_agent else None,
            total_tokens=total_tokens,
            cost_usd=estimate_cost(
                model=primary_agent.model if primary_agent else None,
                provider=primary_agent.provider if primary_agent else None,
                tokens_input=0,
                tokens_output=total_tokens,
            ),
            diversity_ratio=round(diversity_ratio, 4),
            reconstruction_variance=round(sum(v for v in [getattr(e, "reconstruction_variance", None) for e in executions if getattr(e, "reconstruction_variance", None) is not None]) / max(1, sum(1 for e in executions if getattr(e, "reconstruction_variance", None) is not None)), 6) if any(getattr(e, "reconstruction_variance", None) is not None for e in executions) else None,
            reasoning_step_count=sum(getattr(e, "reasoning_step_count", 0) or 0 for e in executions) or None,
            reasoning_step_density=round(sum(v for v in [getattr(e, "reasoning_step_density", None) for e in executions if getattr(e, "reasoning_step_density", None) is not None]) / max(1, sum(1 for e in executions if getattr(e, "reasoning_step_density", None) is not None)), 6) if any(getattr(e, "reasoning_step_density", None) is not None for e in executions) else None,
        )

    # ── Level 3: Neural ───────────────────────────────────────────────────────

    async def _process_neural(
        self,
        request: TaskRequest,
        agents: list[Agent],
        trace: CognitiveTrace,
        registry,
    ) -> TaskResult:
        """
        Deep processing with VoidCache memory reads/writes.
        Retrieves relevant context from cache before running agents,
        and stores results back for future use.
        """
        # 1. Check cache for similar recent results
        cache_key = f"neural:{request.session_id or 'anon'}:{hash(request.input) % 100000}"
        cached = await self._cache.get(cache_key)
        if cached:
            trace.memory_reads += 1
            log.info("Neural cache hit", task_id=request.task_id, key=cache_key)
            return TaskResult(
                task_id=request.task_id,
                output=cached,
                output_type="text",
                cost_usd=0.0,
                metadata={"cache_hit": True},
            )

        # 2. Retrieve session context
        context_key = f"session:{request.session_id}" if request.session_id else None
        session_context: str | None = None
        if context_key:
            session_context = await self._cache.get(context_key)
            if session_context:
                trace.memory_reads += 1

        # 3. Build enriched request with context
        enriched_request = request
        if session_context:
            ctx = dict(request.context or {})
            ctx["session_history"] = session_context
            enriched_request = request.model_copy(update={"context": ctx})

        # 4. Run advanced multi-agent processing
        result = await self._process_advanced(enriched_request, agents, trace, registry)

        # 5. Store result and update session cache
        await self._cache.set(
            cache_key,
            result.output,
            ttl=1800,
            tags=[f"task:{request.task_id}"],
            task_id=request.task_id,
        )
        trace.memory_writes += 1

        if request.session_id:
            history = f"Q: {request.input}\nA: {result.output}"
            await self._cache.set(
                f"session:{request.session_id}",
                history,
                ttl=3600,
                tags=[f"session:{request.session_id}"],
            )
            trace.memory_writes += 1

        return result

    # ── Level 4: Autonomous ───────────────────────────────────────────────────

    async def _process_autonomous(
        self,
        request: TaskRequest,
        agents: list[Agent],
        trace: CognitiveTrace,
        registry,
    ) -> TaskResult:
        """
        Self-directed execution with learning loop.
        Runs neural processing, then evaluates result quality and
        optionally re-runs with refined prompts if confidence is low.
        """
        # Phase 1: Neural processing
        result = await self._process_neural(request, agents, trace, registry)

        # Phase 2: Self-evaluation
        confidence = await self._evaluate_confidence(result.output, request)
        result = result.model_copy(update={"confidence": confidence})

        # Phase 3: Refinement loop if confidence < threshold
        refinement_threshold = 0.65
        max_refinements = 2

        for attempt in range(max_refinements):
            if confidence >= refinement_threshold:
                break

            log.info(
                "Autonomous refinement triggered",
                task_id=request.task_id,
                confidence=confidence,
                attempt=attempt + 1,
            )

            refined_prompt = await self._build_refinement_prompt(
                original_input=request.input,
                current_output=result.output,
                confidence=confidence,
            )
            refined_request = request.model_copy(update={"input": refined_prompt})

            # Re-run with neural level
            result = await self._process_neural(refined_request, agents, trace, registry)
            confidence = await self._evaluate_confidence(result.output, request)
            result = result.model_copy(update={"confidence": confidence})

        # Phase 4: Mark learned
        result = result.model_copy(update={"learned": True})

        # Store high-confidence results in long-term cache
        if confidence >= refinement_threshold:
            await self._cache.set(
                f"learned:{hash(request.input) % 1000000}",
                {"input": request.input, "output": result.output, "confidence": confidence},
                ttl=86400,  # 24 hours
                tags=["learned", "autonomous"],
            )
            trace.memory_writes += 1

        return result

    # ── Agent execution ───────────────────────────────────────────────────────

    def _extract_interaction_texts(self, output: str, tool_trace: list[dict[str, Any]]) -> list[str]:
        if tool_trace:
            return [entry.get("result") or "" for entry in tool_trace] + [output or ""]
        # For plain model outputs, derive pseudo-steps from text structure.
        chunks = [c.strip() for c in (output or "").split("\n\n") if c.strip()]
        if len(chunks) <= 1:
            chunks = [c.strip() for c in (output or "").split(". ") if c.strip()]
        return chunks or [output or ""]

    def _populate_reconstruction_metrics(self, execution: AgentExecution, output: str, tool_trace: list[dict[str, Any]]) -> None:
        try:
            interaction_texts = self._extract_interaction_texts(output, tool_trace)
            execution.step_hashes = [hex(hash(t) & 0xFFFFFFFFFFFFFFFF)[2:] for t in interaction_texts if t]
            distinct = len(set(execution.step_hashes))
            total = len(execution.step_hashes)
            execution.reconstruction_variance = (distinct / total) if total else None
            execution.reasoning_step_count = total
            words = (output or "").split()
            execution.reasoning_step_density = (total / (len(words) / 100.0)) if len(words) else None
        except Exception:
            pass

    async def _run_agent(
        self,
        agent: Agent,
        request: TaskRequest,
        registry,
    ) -> tuple[AgentExecution, str]:
        """
        Execute a single agent on a task.
        Calls the configured AI provider (Ollama/OpenAI/Anthropic).

        If the agent has capabilities that grant tool reach into The Void's
        real systems (FLATSPACE, Garden, Ollama, Observability, gated external
        HTTP), it runs through the agent-runtime tool layer so it can act,
        not just talk. Otherwise it falls back to a plain model call.
        """
        from app.orchestrator.agent_runtime import (
            _system_tools_for_text,
            run_agent_with_tools,
            tools_for_agent,
        )

        started_at = datetime.now(UTC)
        t0 = time.monotonic()

        execution = AgentExecution(
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            started_at=started_at,
        )

        await registry.mark_busy(agent.agent_id)

        try:
            # An agent runs through the tool layer if it has capability-granted
            # reach, OR if the request text clearly implies one of the
            # zqm-local-tools system tools (mesh/host/disk/event/hash). The latter
            # lets a plain NLP agent ACT on system-intent asks (e.g. "mesh overview",
            # "host inventory", "disk space") instead of answering from memory —
            # run_agent_with_tools augments its tool set deterministically and runs
            # the pre-tool before the model call. Fail-soft: if the tool errors, the
            # model still answers.
            base_caps = tools_for_agent(getattr(agent, "capabilities", []))
            if base_caps or _system_tools_for_text(request.input):
                # Agent has real system reach — run with tool execution,
                # optionally gated by an explicit input schema.
                output, tool_trace, truncation_note, total_usage = await run_agent_with_tools(
                    agent=agent,
                    request_input=request.input,
                    context=request.context,
                    call_model=self._generate,
                    input_schema=getattr(request, "tool_schema", None),
                )
                execution.tool_trace = tool_trace  # type: ignore[attr-defined]
                if truncation_note:
                    trace.input_truncated = True
                    trace.input_truncation_reason = truncation_note

                # lightweight reconstruction-runtime probe:
                # populate step hashes and simple reconstruction_/reasoning metrics.
                self._populate_reconstruction_metrics(execution, output or "", tool_trace)
                execution.tokens_used = total_usage.get("total_tokens") or len((output or "").split()) * 2
            else:
                output, token_usage = await self._call_ai_provider(agent, request)
                # Ensure reconstruction metrics are populated even without tool execution.
                self._populate_reconstruction_metrics(execution, output or "", [])
                execution.tokens_used = token_usage.get("total_tokens") or len((output or "").split()) * 2

            execution.completed_at = datetime.now(UTC)
            execution.duration_ms = int((time.monotonic() - t0) * 1000)
            execution.output = output

            await registry.mark_idle(
                agent.agent_id,
                success=True,
                latency_ms=execution.duration_ms,
                tokens=execution.tokens_used,
            )

            return execution, output

        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            execution.completed_at = datetime.now(UTC)
            execution.duration_ms = latency_ms
            execution.error = str(exc)

            await registry.mark_idle(agent.agent_id, success=False, latency_ms=latency_ms)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _generate(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        params: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Call the model provider. Returns (generated_text, token_usage)."""
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        provider = agent.provider
        resolved_model = model or agent.model

        # ── Self-hosted mandate ──────────────────────────────────────────────
        if provider in ("openai", "anthropic") and not settings.allow_external_providers:
            raise RuntimeError(
                f"External AI provider '{provider}' is blocked: The Void is "
                f"self-hosted. Set ZQM_ALLOW_EXTERNAL_PROVIDERS=true to enable."
            )

        params = params or {"max_tokens": 4096, "temperature": 0.7}

        async with httpx.AsyncClient(timeout=settings.task_timeout_seconds) as client:
            if provider == "ollama":
                text = await self._call_ollama(client, resolved_model, messages, params, token_usage)
            elif provider == "openai":
                text = await self._call_openai(client, resolved_model, messages, params, token_usage)
            elif provider == "anthropic":
                text = await self._call_anthropic(client, resolved_model, messages, params, token_usage)
            elif provider == "local_deterministic":
                text = await self._call_local_deterministic(agent, messages, params, token_usage)
            else:
                raise ValueError(f"Unknown AI provider: {provider}")
            return text, token_usage

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _call_ai_provider(self, agent: Agent, request: TaskRequest) -> tuple[str, dict[str, int]]:
        """
        Call the configured AI provider for this agent.
        Supports: Ollama (local), OpenAI, Anthropic.
        """
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        provider = agent.provider
        resolved_model = request.model or agent.model

        # ── Self-hosted mandate ──────────────────────────────────────────────
        if provider in ("openai", "anthropic") and not settings.allow_external_providers:
            raise RuntimeError(
                f"External AI provider '{provider}' is blocked: The Void is "
                f"self-hosted. Set ZQM_ALLOW_EXTERNAL_PROVIDERS=true to enable."
            )

        # Build messages
        messages = []
        if agent.system_prompt:
            messages.append({"role": "system", "content": agent.system_prompt})

        if request.context and request.context.get("session_history"):
            messages.append({
                "role": "system",
                "content": f"Previous conversation:\\n{request.context['session_history']}",
            })

        messages.append({"role": "user", "content": request.input})

        params: dict[str, Any] = {
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature or 0.7,
        }

        async with httpx.AsyncClient(timeout=settings.task_timeout_seconds) as client:
            if provider == "ollama":
                text = await self._call_ollama(client, resolved_model, messages, params, token_usage)
            elif provider == "openai":
                text = await self._call_openai(client, resolved_model, messages, params, token_usage)
            elif provider == "anthropic":
                text = await self._call_anthropic(client, resolved_model, messages, params, token_usage)
            elif provider == "local_deterministic":
                text = await self._call_local_deterministic(agent, messages, params, token_usage)
            else:
                raise ValueError(f"Unknown AI provider: {provider}")
            return text, token_usage

    async def _call_ollama(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        params: dict,
        token_usage: dict[str, int],
    ) -> str:
        # Federation: route across the ZQM-MESH Ollama pool (N1/N2/N3/N4),
        # selecting the node that actually has `model`, with failover.
        # If `model` is not available anywhere, fall back to a known live
        # mesh model instead of hanging forever on dead backends.
        from app.services.mesh_ollama import router as mesh_ollama
        fallback_model = model
        try:
            catalog = await mesh_ollama.list_models()
        except Exception:
            catalog = {"backends": []}
        available = set()
        for b in catalog.get("backends", []):
            if b.get("healthy"):
                available.update(b.get("models") or [])
        if model not in available:
            for candidate in (model, "phi3:mini"):
                if candidate in available:
                    fallback_model = candidate
                    break

        try:
            data = await mesh_ollama.chat(
                model=fallback_model,
                messages=messages,
                timeout=settings.task_timeout_seconds,
                options={
                    "temperature": params.get("temperature", 0.7),
                    "num_predict": params.get("max_tokens", 4096),
                },
            )
        except Exception as exc:
            log.warning(
                "Ollama mesh fallback failed", model=fallback_model, error=str(exc)
            )
            raise
        prompt_tokens = 0
        completion_tokens = 0
        if isinstance(data, dict):
            prompt_tokens = int(data.get("prompt_eval_count") or data.get("prompt_tokens") or 0)
            completion_tokens = int(
                max(
                    data.get("eval_count") or 0,
                    data.get("completion_tokens") or 0,
                )
            )
        token_usage.update(
            {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
        )
        return data.get("message", {}).get("content", "")

    async def _call_openai(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        params: dict,
        token_usage: dict[str, int],
    ) -> str:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": params.get("max_tokens", 4096),
                "temperature": params.get("temperature", 0.7),
            },
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        token_usage.update(
            {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            }
        )
        return data["choices"][0]["message"]["content"]

    async def _call_local_deterministic(
        self,
        agent: Agent,
        messages: list[dict[str, str]],
        params: dict[str, Any],
        token_usage: dict[str, int],
    ) -> str:
        """Deterministic fallback when no LLM backend is available."""
        system_prompt = agent.system_prompt or agent.name or "ZQM Agent"
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        max_tokens = int(params.get("max_tokens", 4096))
        words = (user_text or "").split()
        if not words:
            return f"[{agent.name}] No input provided."

        budget = min(max_tokens, max(32, len(words)))
        echoed = " ".join(words[:budget])
        tool_ctx = ""
        if getattr(agent, "capabilities", None):
            caps = [c.value for c in agent.capabilities]
            tool_ctx = (
                "\n\n[Deterministic mode]\n"
                f"Agent capabilities: {', '.join(caps)}\n"
                "No LLM backend available. Returning verbatim input excerpt instead of generated text."
            )

        return (
            f"[{agent.name} | deterministic fallback]\n"
            f"Input excerpt ({budget}/{len(words)} tokens):\n{echoed}{tool_ctx}"
        )

    async def _call_anthropic(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        params: dict,
        token_usage: dict[str, int],
    ) -> str:
        # Anthropic uses separate system / messages format
        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                user_messages.append(msg)

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": params.get("max_tokens", 4096),
            "messages": user_messages,
        }
        if system_msg:
            payload["system"] = system_msg.strip()

        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        token_usage.update(
            {
                "prompt_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0),
            }
        )
        return data["content"][0]["text"]

    # ── Synthesis & evaluation ────────────────────────────────────────────────

    async def _synthesize(
        self,
        outputs: list[str],
        request: TaskRequest,
        trace: CognitiveTrace,
    ) -> str:
        """
        FlatSpaceine multiple agent outputs into a single coherent response.
        Uses a simple weighted synthesis for now; can be replaced with
        a dedicated synthesis agent call.
        """
        if len(outputs) == 1:
            return outputs[0]

        # Build synthesis prompt
        numbered = "\n\n".join(
            f"[Agent {i + 1} Response]\n{o}" for i, o in enumerate(outputs)
        )
        synthesis_prompt = (
            f"You are synthesizing multiple expert responses into one unified answer.\n\n"
            f"Original question: {request.input}\n\n"
            f"Expert responses:\n{numbered}\n\n"
            f"Provide a single, comprehensive, well-structured response that "
            f"incorporates the best insights from all agents. Resolve any conflicts "
            f"and present a unified, authoritative answer."
        )

        # Use the mesh Ollama router (federated across N1/N2/N3/N4).
        try:
            from app.services.mesh_ollama import router as mesh_ollama
            data = await mesh_ollama.chat(
                model=settings.ollama_default_model,
                messages=[{"role": "user", "content": synthesis_prompt}],
                timeout=60.0,
            )
            synthesized = data.get("message", {}).get("content", "")
            if synthesized:
                return synthesized
        except Exception as exc:
            log.warning("Synthesis call failed, using best output", error=str(exc))

        # Fallback: return the longest output (heuristic)
        return max(outputs, key=len)

    async def _evaluate_confidence(self, output: str, request: TaskRequest) -> float:
        """
        Heuristic confidence evaluation.
        In production, replace with a dedicated evaluation model call.
        """
        if not output or len(output.strip()) < 20:
            return 0.3

        # Simple heuristics
        score = 0.5
        if len(output) > 200:
            score += 0.1
        if len(output) > 500:
            score += 0.1
        if "I don't know" in output or "I'm not sure" in output:
            score -= 0.2
        if any(kw in output.lower() for kw in ["therefore", "analysis", "recommend", "conclusion"]):
            score += 0.1
        if "error" in output.lower() and "failed" in output.lower():
            score -= 0.3

        return max(0.0, min(1.0, score))

    async def _build_refinement_prompt(
        self,
        original_input: str,
        current_output: str,
        confidence: float,
    ) -> str:
        """Build a refined prompt for a second-pass autonomous refinement."""
        return (
            f"The previous response to the following question had low confidence "
            f"(score: {confidence:.2f}). Please provide a more thorough, accurate, "
            f"and comprehensive answer.\n\n"
            f"Original question: {original_input}\n\n"
            f"Previous answer (to improve upon):\n{current_output}\n\n"
            f"Please provide an improved, more confident response with clear "
            f"reasoning and specific details."
        )
