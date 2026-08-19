"""Regression test for the session-memory overwrite bug (H1).

Before the fix, CognitiveProcessor._process_neural OVERWROTE the
``session:{id}`` cache key with a single ``Q/A`` line on every call, so
prior turns were lost ("memory reverts every few calls") and the key had a
short 1h TTL.

After the fix it APPENDS new turns (capped at 20) and uses a 24h TTL, so a
multi-turn session retains its history across calls.

This test drives the REAL edited code path with a faked ``_process_advanced``
(so no live Ollama/model is required) and a real VoidCache instance.

Plain sync test functions (each runs the async path via asyncio.run) so the
suite needs no async pytest plugin.
"""
import asyncio

from app.memory.void_cache import VoidCache
from app.models.task import CognitiveTrace, TaskRequest, TaskResult
from app.orchestrator.cognitive_processor import CognitiveProcessor


def _make_request(session_id: str, inp: str) -> TaskRequest:
    return TaskRequest(
        input=inp,
        session_id=session_id,
        cognitive_level="neural",
    )


def _fake_result(task_id: str, output: str) -> TaskResult:
    return TaskResult(task_id=task_id, output=output, output_type="text", cost_usd=0.0)


def _run_neural(proc, sid, inp):
    """Drive the real (edited) _process_neural with a faked heavy step."""
    async def _go():
        return await proc._process_neural(
            _make_request(sid, inp),
            agents=[],
            trace=CognitiveTrace(level="neural"),
            registry=None,
        )
    return asyncio.run(_go())


def test_session_history_appends_across_calls():
    """Two neural calls in the same session must accumulate, not overwrite."""
    cache = VoidCache()
    proc = CognitiveProcessor()
    proc._cache = cache

    # Fake the heavy multi-agent step so we don't need a live model.
    async def fake_advanced(request, agents, trace, registry):
        return _fake_result(request.task_id, f"answer-to: {request.input}")

    proc._process_advanced = fake_advanced

    sid = "regression-session-1"
    _run_neural(proc, sid, "first question")
    _run_neural(proc, sid, "second question")

    stored = asyncio.run(cache.get(f"session:{sid}"))
    assert stored is not None, "session history should be stored"
    # Both turns must be present.
    assert "Q: first question" in stored, "first turn was lost (overwrite bug)"
    assert "Q: second question" in stored, "second turn missing"
    assert "A: answer-to: first question" in stored
    assert "A: answer-to: second question" in stored
    # Order preserved: first turn precedes second.
    assert stored.index("first question") < stored.index("second question")


def test_session_history_does_not_duplicate_on_reread():
    """Each call appends exactly one turn; reread does not mutate storage."""
    cache = VoidCache()
    proc = CognitiveProcessor()
    proc._cache = cache

    async def fake_advanced(request, agents, trace, registry):
        return _fake_result(request.task_id, "x")

    proc._process_advanced = fake_advanced

    _run_neural(proc, "sess-dup", "q1")
    stored_after_one = asyncio.run(cache.get("session:sess-dup"))
    _run_for_q2 = _run_neural
    _run_for_q2(proc, "sess-dup", "q2")  # same session, second turn
    stored_after_two = asyncio.run(cache.get("session:sess-dup"))

    assert stored_after_one.count("Q:") == 1
    assert stored_after_two.count("Q:") == 2
