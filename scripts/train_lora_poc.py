"""
Minimal LoRA proof-of-concept for CPU.

Trains a tiny adapter on local data to validate the Phase 1 pipeline.
"""
from __future__ import annotations

import argparse
import os
import time


def _available(*packages: str) -> bool:
    for pkg in packages:
        try:
            __import__(pkg)
        except Exception:
            return False
    return True


def train_cpu_poc(
    base_model: str,
    dataset_path: str,
    output_dir: str,
    epochs: int = 1,
    batch_size: int = 1,
    max_length: int = 128,
    lora_rank: int = 4,
    lora_alpha: int = 8,
) -> str:
    if not _available("torch", "transformers", "peft", "datasets"):
        return "missing_dependencies"

    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    print(f"[poc] base_model={base_model}")
    print(f"[poc] dataset={dataset_path}")
    print(f"[poc] output={output_dir}")

    model = AutoModelForCausalLM.from_pretrained(base_model)
    model = prepare_model_for_kbit_training(model)
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    lora_config = LoraConfig(
        r=lora_rank,
        lora_alpha=lora_alpha,
        target_modules=["c_attn", "c_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    dataset = load_dataset("json", data_files=dataset_path, split="train")

    def _tokenize(ex):
        text = f"Question: {ex['prompt']}\nAnswer: {ex['completion']}"
        return tokenizer(text, truncation=True, max_length=max_length)

    tokenized = dataset.map(_tokenize, remove_columns=dataset.column_names)
    data_collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

    os.makedirs(output_dir, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        num_train_epochs=epochs,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=data_collator,
    )
    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[poc] training complete in {elapsed:.1f}s")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="CPU LoRA proof-of-concept")
    parser.add_argument("--base-model", default="distilgpt2")
    parser.add_argument("--dataset", default="data/training_data_all.jsonl")
    parser.add_argument("--output-dir", default="models/poc-lora")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--lora-rank", type=int, default=4)
    parser.add_argument("--lora-alpha", type=int, default=8)
    args = parser.parse_args()

    out = train_cpu_poc(
        base_model=args.base_model,
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
    )
    print("adapter:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
