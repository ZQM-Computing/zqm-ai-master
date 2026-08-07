"""
Distributed training setup for Phase 3.

Provides:
- DeepSpeed ZeRO configs
- FSDP configs
- Multi-node training orchestration
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional


def deepspeed_zero3_config(
    model_params_b: float,
    batch_size: int = 4,
    lr: float = 2e-4,
) -> Dict[str, any]:
    """Generate DeepSpeed ZeRO-3 config."""
    return {
        "train_batch_size": batch_size,
        "fp16": {"enabled": True},
        "zero_optimization": {
            "stage": 3,
            "offload_optimizer": {"device": "cpu", "pin_memory": True},
            "offload_param": {"device": "cpu", "pin_memory": True},
            "overlap_comm": True,
            "contiguous_gradients": True,
            "stage3_max_live_parameters": 1e9,
            "stage3_max_reuse_distance": 1e9,
            "stage3_prefetch_bucket_size": 5e8,
            "stage3_param_persistence_threshold": 1e6,
        },
        "gradient_accumulation_steps": 8,
        "optimizer": {"type": "AdamW", "params": {"lr": lr}},
    }


def fsdp_config(
    model_params_b: float,
    world_size: int = 2,
) -> Dict[str, any]:
    """Generate FSDP config."""
    return {
        "fsdp": {
            "min_num_params": 1e6,
            "mixed_precision": True,
            "sharding_strategy": "FULL_SHARD",
            "cpu_offload": False,
            "backward_prefetch": "BACKWARD_PRE",
        },
        "train_batch_size": 4 * world_size,
        "gradient_accumulation_steps": 8,
    }


def estimate_training_time(
    model_params_b: float,
    dataset_size: int,
    world_size: int = 1,
    gpu_type: str = "a100",
) -> Dict[str, float]:
    """Estimate training time in hours."""
    throughput = {
        "a100": 50,  # it/s for 7B
        "v100": 20,
        "cpu": 1.0,
    }
    it_per_epoch = dataset_size / 4  # batch_size=4
    it_s = throughput.get(gpu_type, 1.0) * world_size
    seconds = (it_per_epoch * 3) / it_s  # 3 epochs
    return {
        "estimated_hours": round(seconds / 3600, 2),
        "model_params_b": model_params_b,
        "dataset_size": dataset_size,
        "world_size": world_size,
        "gpu_type": gpu_type,
    }
