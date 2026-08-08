"""
Model parallelism utilities for Phase 3.

Provides:
- Model sharding across devices
- Tensor parallelism helpers
- Pipeline parallelism setup
"""
from __future__ import annotations


def shard_model_layers(base_model: str, num_shards: int = 2) -> list[dict]:
    """Split model layers across shards."""
    # Placeholder: real implementation depends on model config
    return [
        {
            "shard_id": i,
            "layers": list(range(i, 100, num_shards)),
            "base_model": base_model,
        }
        for i in range(num_shards)
    ]


def tensor_parallel_config(world_size: int = 2) -> dict:
    return {
        "tensor_parallel_size": world_size,
        "pipeline_parallel_size": 1,
        "strategy": "tensor",
    }


def estimate_memory_gb(model_params_b: float, quant: str = "fp16") -> float:
    """Estimate VRAM needed for model loading."""
    bytes_per_param = {"fp32": 4, "fp16": 2, "q4": 0.5, "q8": 1}
    factor = bytes_per_param.get(quant, 2)
    return model_params_b * factor


def can_load_on_device(model_params_b: float, vram_gb: float, quant: str = "fp16") -> bool:
    needed = estimate_memory_gb(model_params_b, quant)
    return vram_gb >= needed * 1.2  # 20% headroom
