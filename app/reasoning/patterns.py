"""
Reasoning patterns for /api/rag and agent runtime.

Patterns:
- chain_of_thought
- tree_of_thought
- self_consistency
- constitutional_ai
- react
- self_reflection
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional


class ReasoningPattern:
    name = "base"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        raise NotImplementedError


class ChainOfThought(ReasoningPattern):
    name = "chain_of_thought"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        prompt = (
            "You are a careful assistant.\n"
            "Use the context below to answer the question.\n"
            "Think step by step before giving the final answer.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Step-by-step reasoning:\n"
        )
        data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
        reasoning = (data.get("message") or {}).get("content", "").strip()
        answer_prompt = (
            "Based on the following reasoning, provide a concise final answer.\n\n"
            f"Reasoning:\n{reasoning}\n\n"
            "Final Answer:"
        )
        data2 = await mesh_ollama.chat(model, [{"role": "user", "content": answer_prompt}], timeout=120)
        answer = (data2.get("message") or {}).get("content", "").strip()
        return {"reasoning": reasoning, "answer": answer, "pattern": self.name}


class TreeOfThought(ReasoningPattern):
    name = "tree_of_thought"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        branches = []
        for i in range(3):
            prompt = (
                "Use the context below to reason about the question.\n"
                "Generate one complete reasoning path.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {question}\n\n"
                "Reasoning path:"
            )
            data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
            path = (data.get("message") or {}).get("content", "").strip()
            score_prompt = f"Rate this reasoning from 0 to 10 for correctness and completeness.\n\n{path}\n\nScore:"
            data2 = await mesh_ollama.chat(model, [{"role": "user", "content": score_prompt}], timeout=120)
            score_text = (data2.get("message") or {}).get("content", "0").strip()
            try:
                score = float(score_text.split()[0])
            except Exception:
                score = 0.0
            branches.append({"path": path, "score": score})
        branches.sort(key=lambda x: x["score"], reverse=True)
        best = branches[0] if branches else {"path": "", "score": 0.0}
        return {"branches": branches, "answer": best["path"], "pattern": self.name}


class SelfConsistency(ReasoningPattern):
    name = "self_consistency"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        prompt = (
            "Use the context below to answer the question.\n"
            "Provide a direct final answer.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        completions = []
        for _ in range(3):
            data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
            completions.append((data.get("message") or {}).get("content", "").strip())
        # Simple majority by normalized string
        normed = [c.lower().strip() for c in completions]
        counts: Dict[str, int] = {}
        for c in normed:
            counts[c] = counts.get(c, 0) + 1
        best_norm = max(counts, key=counts.get)  # type: ignore
        best_idx = normed.index(best_norm)
        return {"completions": completions, "answer": completions[best_idx], "pattern": self.name}


class ConstitutionalAI(ReasoningPattern):
    name = "constitutional_ai"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        prompt = (
            "Use the context below to draft an answer.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Draft answer:"
        )
        data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
        draft = (data.get("message") or {}).get("content", "").strip()
        critique_prompt = (
            "Critique the following draft against these principles:\n"
            "1. Helpful\n"
            "2. Harmless\n"
            "3. Honest\n"
            "4. Cites uncertainty rather than hallucinates\n\n"
            f"Draft:\n{draft}\n\n"
            "Critique:"
        )
        data2 = await mesh_ollama.chat(model, [{"role": "user", "content": critique_prompt}], timeout=120)
        critique = (data2.get("message") or {}).get("content", "").strip()
        revise_prompt = (
            "Revise the draft based on the critique.\n\n"
            f"Draft:\n{draft}\n\n"
            f"Critique:\n{critique}\n\n"
            "Revised answer:"
        )
        data3 = await mesh_ollama.chat(model, [{"role": "user", "content": revise_prompt}], timeout=120)
        answer = (data3.get("message") or {}).get("content", "").strip()
        return {"draft": draft, "critique": critique, "answer": answer, "pattern": self.name}


class SelfReflection(ReasoningPattern):
    name = "self_reflection"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        prompt = (
            "Use the context below to answer the question.\n"
            "Then identify any mistakes or uncertainties.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
        answer = (data.get("message") or {}).get("content", "").strip()
        reflect_prompt = (
            "Reflect on this answer. Identify mistakes, unsupported claims, or uncertainties.\n\n"
            f"Answer:\n{answer}\n\n"
            "Reflection:"
        )
        data2 = await mesh_ollama.chat(model, [{"role": "user", "content": reflect_prompt}], timeout=120)
        reflection = (data2.get("message") or {}).get("content", "").strip()
        improve_prompt = (
            "Improve the original answer based on the reflection.\n\n"
            f"Original answer:\n{answer}\n\n"
            f"Reflection:\n{reflection}\n\n"
            "Improved answer:"
        )
        data3 = await mesh_ollama.chat(model, [{"role": "user", "content": improve_prompt}], timeout=120)
        improved = (data3.get("message") or {}).get("content", "").strip()
        return {"answer": answer, "reflection": reflection, "improved": improved, "pattern": self.name}


class ReAct(ReasoningPattern):
    name = "react"

    async def apply(self, question: str, context: str, model: str) -> Dict[str, Any]:
        from app.services.mesh_ollama import router as mesh_ollama
        tools = [
            {"name": "flatspace_search", "description": "Search local knowledge store for relevant context."},
            {"name": "web_search", "description": "Search the web for current information."},
            {"name": "calculator", "description": "Evaluate a math expression safely."},
        ]
        tool_descs = "\n".join([f"- {t['name']}: {t['description']}" for t in tools])
        prompt = (
            "Use the tools below to answer the question.\n"
            "Format:\nThought: <thought>\nAction: <tool>\nAction Input: <json>\nObservation: <result>\n... (repeat)\nFinal Answer: <answer>\n\n"
            f"Tools:\n{tool_descs}\n\n"
            f"Question: {question}\n\n"
            "Thought:"
        )
        data = await mesh_ollama.chat(model, [{"role": "user", "content": prompt}], timeout=120)
        trace = (data.get("message") or {}).get("content", "").strip()
        return {"trace": trace, "answer": trace, "pattern": self.name}


_PATTERNS = {
    "chain_of_thought": ChainOfThought(),
    "tree_of_thought": TreeOfThought(),
    "self_consistency": SelfConsistency(),
    "constitutional_ai": ConstitutionalAI(),
    "self_reflection": SelfReflection(),
    "react": ReAct(),
}


def get_pattern(name: str) -> ReasoningPattern:
    return _PATTERNS.get(name, ChainOfThought())
