"""
LoRA fine-tuning pipeline for local Ollama-compatible models.

Target: train small adapters and merge them for Ollama serving.
"""
from __future__ import annotations

import argparse
import os


def _available(package: str) -> bool:
    try:
        __import__(package)
        return True
    except Exception:
        return False


def _auto_target_modules(model):
    """Infer LoRA target modules from model architecture."""
    names = [n for n, _ in model.named_modules()]
    candidates = [
        ["q_proj", "v_proj", "k_proj", "o_proj"],
        ["c_attn", "c_proj"],
        ["qkv_proj", "out_proj"],
        ["query", "key", "value", "dense"],
    ]
    for cand in candidates:
        if all(any(c in n for n in names) for c in cand):
            return cand
    return ["c_attn", "c_proj"]

def train_lora(
    base_model: str,
    dataset_path: str,
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 4,
    lora_rank: int = 8,
    lora_alpha: int = 16,
    learning_rate: float = 2e-4,
    target_modules: list | None = None,
) -> str:
    missing = []
    for pkg in ["torch", "transformers", "peft", "bitsandbytes", "datasets"]:
        if not _available(pkg):
            missing.append(pkg)
    if missing:
        return f"missing_dependencies:{','.join(missing)}"

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    print(f"Loading base model: {base_model}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )
    model = AutoModelForCausalLM.from_pretrained(base_model, quantization_config=bnb_config)
    model = prepare_model_for_kbit_training(model)
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    lora_config = LoraConfig(
        r=lora_rank,
        lora_alpha=lora_alpha,
        target_modules=target_modules or _auto_target_modules(model),
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print(f"Loading dataset: {dataset_path}")
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    def _tokenize(ex):
        text = f"Question: {ex['prompt']}\nAnswer: {ex['completion']}"
        return tokenizer(text, truncation=True, max_length=512)

    tokenized = dataset.map(_tokenize, remove_columns=dataset.column_names)
    data_collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=8,
        num_train_epochs=epochs,
        learning_rate=learning_rate,
        fp16=torch.cuda.is_available(),
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
    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def merge_lora(base_model: str, adapter_dir: str, output_dir: str) -> str:
    if not _available("torch") or not _available("transformers") or not _available("peft"):
        return "missing_dependencies:torch,transformers,peft"
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"Merging adapter {adapter_dir} into {base_model}")
    base = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16, device_map="auto")
    model = PeftModel.from_pretrained(base, adapter_dir)
    merged = model.merge_and_unload()
    os.makedirs(output_dir, exist_ok=True)
    merged.save_pretrained(output_dir)
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    tokenizer.save_pretrained(output_dir)
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA fine-tuning pipeline")
    sub = parser.add_subparsers(dest="cmd")

    train = sub.add_parser("train")
    train.add_argument("--base-model", required=True)
    train.add_argument("--dataset", required=True)
    train.add_argument("--output-dir", required=True)
    train.add_argument("--epochs", type=int, default=3)
    train.add_argument("--batch-size", type=int, default=4)
    train.add_argument("--lora-rank", type=int, default=8)
    train.add_argument("--lora-alpha", type=int, default=16)
    train.add_argument("--learning-rate", type=float, default=2e-4)

    merge = sub.add_parser("merge")
    merge.add_argument("--base-model", required=True)
    merge.add_argument("--adapter-dir", required=True)
    merge.add_argument("--output-dir", required=True)

    args = parser.parse_args()
    if args.cmd == "train":
        out = train_lora(
            base_model=args.base_model,
            dataset_path=args.dataset,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lora_rank=args.lora_rank,
            lora_alpha=args.lora_alpha,
            learning_rate=args.learning_rate,
        )
        print("adapter:", out)
    elif args.cmd == "merge":
        out = merge_lora(args.base_model, args.adapter_dir, args.output_dir)
        print("merged:", out)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
