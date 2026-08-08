"""
The Void AI Orchestration System — Mesh Ollama Router
Version: 2.2.0 | ZQM Computing LLC

Routes inference across LOCAL + mesh backends with:
- capability ranking
- circuit-break on repeated 5xx/timeout
- hang-tolerant health probe with tags-first check
- 4xx-safe degradation (model-missing does not trip breaker)
- chat-or-generate probe/fallback per backend
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("mesh_ollama")

# Default mesh topology: N2, N3, N4 are compute nodes with Ollama.
# N1 is a management/gateway node without Ollama.
DEFAULT_BACKENDS: List[Dict[str, Any]] = [
    {"name": "N2", "url": "http://192.168.1.31:11434", "local": False},
    {"name": "N3", "url": "http://192.168.1.78:11434", "local": False},
    {"name": "N4", "url": "http://192.168.1.228:11434", "local": False},
]

_CIRCUIT_TRIP = 3
_DOWN_GRACE_S = 90.0
# Health-check timeouts.
_TAGS_TIMEOUT = 6.0
_PROBE_TIMEOUT = 8.0
_PROBE_NUM_PREDICT = 8
_PROBE_FULL_AFTER_FAILURES = 2
# Use chat/generate probe rewrite only when first backend probe is empty/500.
_PROBE_CHAT_MAX = 1
# Small-model probe preference: try tiny/cheap models first so we don't
# trigger slow generation on large quantized models during health checks.
_PROBE_CANDIDATE_PREFIXES = ("qwen2.5:0.5b", "phi3:mini", "llama3.2:3b", "llama3.1:8b", "mistral:7b", "qwen2.5:3b", "llava:7b", "moondream:latest", "deepseek-r1:1.5b")


class OllamaUnavailable(Exception):
    """No healthy mesh/local backend can serve the requested model."""


class MeshOllamaRouter:
    def __init__(self, backends: Optional[List[Dict[str, Any]]] = None) -> None:
        self.backends = backends or DEFAULT_BACKENDS
        self._health: Dict[str, bool] = {}
        self._models: Dict[str, List[str]] = {}
        self._model_index: Dict[str, List[str]] = {}
        self._last_check = 0.0
        self._down_until: Dict[str, float] = {}
        self._status_failures: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def refresh(self, force: bool = False) -> None:
        async with self._lock:
            now = time.monotonic()
            if not force and self._last_check and (now - self._last_check) < 30:
                return
            self._down_until = {k: v for k, v in self._down_until.items() if v > now}
            health: Dict[str, bool] = {}
            models: Dict[str, List[str]] = {}
            index: Dict[str, List[str]] = {}
            await asyncio.gather(
                *(self._check_one(b, health, models, index) for b in self.backends)
            )
            self._health = health
            self._models = models
            self._model_index = index
            self._last_check = time.monotonic()
        healthy = [n for n, ok in self._health.items() if ok]
        log.info("Mesh Ollama refreshed", healthy=healthy,
                 total_models=len(self._model_index))

    # ---- health check ----

    async def _check_one(
        self, b: Dict[str, str], health: Dict[str, bool], models: Dict[str, List[str]],
        index: Dict[str, List[str]],
    ) -> None:
        name = b["name"]
        headers = {}
        if settings.ollama_api_key:
            headers["Authorization"] = "Bearer " + settings.ollama_api_key
        try:
            async with httpx.AsyncClient(timeout=_TAGS_TIMEOUT) as client:
                r = await client.get(f"{b['url']}/api/tags", headers=headers)
                r.raise_for_status()
                mlist = [m["name"] for m in r.json().get("models", [])]
            probe_model = next(
                (m for m in mlist if any(m == pref or m.startswith(pref + ":") for pref in _PROBE_CANDIDATE_PREFIXES)),
                (mlist[0] if mlist else None),
            )
            if probe_model:
                async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
                    pr = await client.post(
                        f"{b['url']}/api/generate",
                        json={
                            "model": probe_model,
                            "prompt": "ping",
                            "stream": False,
                            "options": {"num_predict": _PROBE_NUM_PREDICT},
                        },
                        headers=headers,
                        timeout=_PROBE_TIMEOUT,
                    )
                    pr.raise_for_status()
            health[b["name"]] = True
            models[b["name"]] = mlist
            for m in mlist:
                index.setdefault(m, []).append(b["name"])
            self._status_failures.pop(name, None)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else 0
            if status >= 500:
                self._status_failures[name] = self._status_failures.get(name, 0) + 1
                if self._status_failures[name] >= 2:
                    self._down_until[name] = time.monotonic() + _DOWN_GRACE_S
                    log.warning("Mesh backend temp-down after repeated 5xx",
                                backend=name, status=status)
                    health[b["name"]] = False
                    models[b["name"]] = []
                    return
            health[b["name"]] = False
            models[b["name"]] = []
        except httpx.TimeoutException:
            self._status_failures[name] = self._status_failures.get(name, 0) + 1
            if self._status_failures[name] >= 2:
                self._down_until[name] = time.monotonic() + _DOWN_GRACE_S
                log.warning("Mesh backend down after repeated timeout",
                            backend=name)
            health[b["name"]] = False
            models[b["name"]] = []
        except Exception:
            self._status_failures[name] = self._status_failures.get(name, 0) + 1
            if self._status_failures[name] >= 2:
                self._down_until[name] = time.monotonic() + _DOWN_GRACE_S
                log.warning("Mesh backend down after unexpected error",
                            backend=name)
            health[b["name"]] = False
            models[b["name"]] = []
        finally:
            index.pop(b["name"], None)
            for m, lst in list(index.items()):
                if b["name"] in lst:
                    lst.remove(b["name"])

    def _is_down(self, name: str) -> bool:
        return self._down_until.get(name, 0.0) > time.monotonic()

    def _ranked_backends(self, model: str) -> List[Dict[str, str]]:
        have = self._model_index.get(model, [])
        ordered = []
        for b in self.backends:
            if b["name"] in have and not self._is_down(b["name"]):
                ordered.append(b)
        ordered.sort(key=lambda b: not b.get("local", False))
        if ordered:
            return ordered
        return [b for b in self.backends
                if self._health.get(b["name"], False) and not self._is_down(b["name"])]

    def _degraded_backends(self) -> List[Dict[str, str]]:
        out = []
        for b in self.backends:
            if self._health.get(b["name"], False) and not self._is_down(b["name"]) \
                    and self._models.get(b["name"]):
                out.append(b)
        out.sort(key=lambda b: not b.get("local", False))
        return out

    # ---- request dispatch ----

    async def _post(self, b: Dict[str, str], model: str,
                    messages: List[Dict[str, str]], timeout: float,
                    opts: Dict[str, Any]) -> Dict[str, Any]:
        last: Optional[Exception] = None
        name = b["name"]
        chat_supported: Optional[bool] = None

        def _prompt(msgs: List[Dict[str, str]]) -> str:
            return "\n".join(f"[{m.get('role','user')}] {m.get('content','')}" for m in msgs)

        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    headers = {"Content-Type": "application/json"}
                    if settings.ollama_api_key:
                        headers["Authorization"] = "Bearer " + settings.ollama_api_key
                    payload = {"model": model, "stream": False, **opts}
                    if chat_supported is not False:
                        r = await client.post(
                            f"{b['url']}/api/chat",
                            json={**payload, "messages": messages},
                            headers=headers,
                        )
                    if chat_supported is False or (chat_supported is None and r.status_code == 404):
                        chat_supported = False
                        r = await client.post(
                            f"{b['url']}/api/generate",
                            json={**payload, "prompt": _prompt(messages)},
                            headers=headers,
                        )
                    r.raise_for_status()
                    data = r.json()
                    if chat_supported is None and "message" in data:
                        chat_supported = True
                    elif chat_supported is None and "response" in data:
                        chat_supported = False
                    data["_backend"] = name
                    data["_federated"] = not b.get("local", False)
                    self._status_failures.pop(name, None)
                    return data
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else 0
                if chat_supported is None and status == 404:
                    chat_supported = False
                    if attempt < 3:
                        continue
                if status >= 500:
                    self._status_failures[name] = self._status_failures.get(name, 0) + 1
                    if self._status_failures[name] >= 2:
                        self._down_until[name] = time.monotonic() + _DOWN_GRACE_S
                        log.warning("Mesh backend temp-down after repeated 5xx",
                                    backend=name, status=status)
                        raise
                last = exc
                if attempt in (0, 1, 2, 3):
                    if attempt < 3 and status != 404:
                        await asyncio.sleep(0.5)
                        continue
                raise
            except httpx.TransportError as exc:
                last = exc
                self._status_failures.pop(name, None)
                if attempt < 3:
                    await asyncio.sleep(0.5)
                    continue
                self._down_until[name] = time.monotonic() + _DOWN_GRACE_S
                log.warning("Mesh Ollama backend down", backend=name,
                            error=str(exc))
                raise
            except Exception as exc:
                last = exc
                self._status_failures.pop(name, None)
                if attempt < 3:
                    await asyncio.sleep(0.5)
                    continue
                raise
        raise last if last else RuntimeError("unknown ollama error")

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float = 60.0,
        **opts: Any,
    ) -> Dict[str, Any]:
        await self.refresh()
        backends = self._ranked_backends(model)
        if not backends:
            await self.refresh(force=True)
            backends = self._ranked_backends(model)

        # Prefer healthier backends: sort by failure count (lower = better).
        backends = sorted(backends, key=lambda b: self._status_failures.get(b["name"], 0))

        if backends:
            for b in backends:
                try:
                    return await self._post(b, model, messages, timeout, opts)
                except Exception:
                    continue

        # LOCAL escape-hatch
        try:
            local_b = next(
                (b for b in self.backends
                 if b.get("local") and ("127.0.0.1" in b["url"] or "localhost" in b["url"])),
                None,
            ) or next((b for b in self.backends if b.get("local")), None)
            if local_b is not None:
                return await self._post(local_b, model, messages, timeout, opts)
        except Exception:
            pass

        # Degraded-model substitution
        deg = self._degraded_backends()
        if deg:
            for b in deg:
                fb = self._pick_fallback_model(self._models.get(b["name"], []))
                if not fb:
                    continue
                try:
                    data = await self._post(b, fb, messages, timeout, opts)
                    data["_degraded"] = True
                    data["_degraded_from"] = model
                    data["_degraded_to"] = fb
                    log.warning("Ollama degraded fallback",
                                requested=model, used=fb, backend=b["name"])
                    return data
                except Exception:
                    continue

        raise OllamaUnavailable(
            f"no healthy mesh/local Ollama backend can serve model '{model}'"
        )

    # ---- embeddings (full signature preserved for routers) ----

    async def embed(self, model: str, text: str, timeout: float = 60.0) -> List[float]:
        await self.refresh()
        for name in list(self._health):
            b = next((x for x in self.backends if x["name"] == name), None)
            if not b or not self._health.get(name, False) or self._is_down(name):
                continue
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    headers = {"Content-Type": "application/json"}
                    if settings.ollama_api_key:
                        headers["Authorization"] = "Bearer " + settings.ollama_api_key
                    r = await client.post(
                        f"{b['url']}/api/embeddings",
                        json={"model": model, "prompt": text},
                        headers=headers,
                    )
                    r.raise_for_status()
                    emb = r.json().get("embedding") or []
                    if emb:
                        emb["_backend"] = b["name"]
                        return emb
            except Exception:
                continue
        raise OllamaUnavailable(
            f"no healthy mesh/local Ollama backend for embeddings model '{model}'"
        )

    # ---- catalog ----

    async def list_models(self) -> Dict[str, Any]:
        await self.refresh()
        now = time.monotonic()
        catalog: Dict[str, Any] = {"backends": []}
        for b in self.backends:
            healthy = self._health.get(b["name"], False)
            down = self._is_down(b["name"])
            catalog["backends"].append({
                "name": b["name"],
                "url": b["url"],
                "local": b.get("local", False),
                "healthy": bool(healthy and not down),
                "degraded": bool(healthy and down),
                "status_failures": self._status_failures.get(b["name"], 0),
                "recovery_in_s": max(0.0, self._down_until.get(b["name"], 0.0) - now) if down else 0.0,
                "models": self._models.get(b["name"], []),
            })
        return catalog

    def any_healthy(self) -> bool:
        return any(self._health.values())

    # ---- internal helpers ----

    @staticmethod
    def _pick_fallback_model(models: List[str]) -> Optional[str]:
        if not models:
            return None
        for pref in ("qwen2.5:0.5b", "phi3:mini", "llama3.2:3b", "qwen2.5:3b", "mistral:7b", "llava:7b", "moondream:latest", "qwen3.6:latest"):
            if pref in models:
                return pref
        return models[0]


# Shared singleton used by routers+main.
router = MeshOllamaRouter()
