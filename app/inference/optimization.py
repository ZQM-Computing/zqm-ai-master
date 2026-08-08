"""
Quantization and inference optimization for Phase 3.

Provides:
- 4-bit/8-bit quantization configs
- GGUF conversion helpers
- KV-cache optimization
- Batch inference
"""
from __future__ import annotations


def bitsandbytes_config(load_in_4bit: bool = True) -> dict[str, any]:
    """Generate BitsAndBytes quantization config."""
    return {
        "load_in_4bit": load_in_4bit,
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "float16",
    }


def awq_config(quant_bits: int = 4) -> dict[str, any]:
    return {"quant_bits": quant_bits, "zero_point": True}


def estimate_quantized_size(model_params_b: float, bits: int = 4) -> float:
    """Estimate quantized model size in GB."""
    bytes_per_param = {4: 0.5, 8: 1.0}
    factor = bytes_per_param.get(bits, 0.5)
    return model_params_b * factor


def inference_optimization_config() -> dict[str, any]:
    return {
        "use_kv_cache": True,
        "max_batch_size": 8,
        "max_seq_len": 2048,
        "use_fp16": True,
        "use_tensor_parallel": False,
    }
