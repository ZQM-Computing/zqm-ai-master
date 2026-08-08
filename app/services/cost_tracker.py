"""
Token pricing catalog for cost tracking.
Prices are per-million tokens in USD.
Source: public pricing pages as of 2025-2026.
Ollama local models: $0.00 (self-hosted).
"""
from __future__ import annotations

# Per-million-token prices, USD
_MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.00, "output": 60.00},
    "o3": {"input": 10.00, "output": 40.00},
    "o4-mini": {"input": 1.00, "output": 4.00},
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.00},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    # Ollama/local — zero marginal cost
    "ollama": {"input": 0.00, "output": 0.00},
}

# Provider-to-pricing-group mapping
_PROVIDER_DEFAULT: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "ollama": "ollama",
}


def get_model_pricing(model: str | None, provider: str | None) -> dict[str, float]:
    """Return per-million-token pricing for a model/provider pair. Defaults to $0."""
    if not model:
        return {"input": 0.0, "output": 0.0}
    
    model_lower = model.lower()
    
    # Direct match
    if model_lower in _MODEL_PRICING:
        return _MODEL_PRICING[model_lower]
    
    # Prefix match for model families
    for key, price in _MODEL_PRICING.items():
        if model_lower.startswith(key.lower()):
            return price
    
    # Provider default
    prov = (provider or "").lower()
    provider_group = _PROVIDER_DEFAULT.get(prov, "ollama")
    return _MODEL_PRICING.get(provider_group, {"input": 0.0, "output": 0.0})


def estimate_cost(
    model: str | None,
    provider: str | None,
    tokens_input: int | None,
    tokens_output: int | None,
) -> float:
    """Estimate task cost in USD from token usage."""
    pricing = get_model_pricing(model, provider)
    input_tokens = tokens_input or 0
    output_tokens = tokens_output or 0
    
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 8)
