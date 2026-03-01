#!/usr/bin/env python3
"""Fine-tune Ministral 3B with TRL SFTTrainer + LoRA.

Designed to run on HF Jobs (T4 GPU) or any CUDA machine.

Usage:
  python train/train_trl.py
  python train/train_trl.py --num-train-epochs 5 --learning-rate 1e-4
  python train/train_trl.py --push-to-hub --hub-model-id sumitdotml/robuchan
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer


DEFAULT_BASE_MODEL = "mistralai/Ministral-8B-Instruct-2410"
DEFAULT_DATASET = "sumitdotml/robuchan-data"
DEFAULT_OUTPUT_DIR = "./output/robuchan-lora"
DEFAULT_HUB_MODEL_ID = "sumitdotml/robuchan"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--dataset", type=str, default=DEFAULT_DATASET)
    parser.add_argument(
        "--train-file",
        type=str,
        default="data/train_filtered.jsonl",
        help="Path within HF dataset repo to training JSONL.",
    )
    parser.add_argument(
        "--valid-file",
        type=str,
        default="data/valid_filtered.jsonl",
        help="Path within HF dataset repo to validation JSONL.",
    )
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--num-train-epochs", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=-1, help="Override epoch count with fixed steps.")
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--use-4bit", action="store_true", help="Use QLoRA (4-bit quantization).")
    parser.add_argument("--bf16", action="store_true", default=None, help="Use bfloat16 (auto-detected if omitted).")
    parser.add_argument("--fp16", action="store_true", default=None, help="Use float16 (auto-detected if omitted).")
    parser.add_argument("--push-to-hub", action="store_true")
    parser.add_argument("--hub-model-id", type=str, default=DEFAULT_HUB_MODEL_ID)
    parser.add_argument("--wandb-project", type=str, default=os.environ.get("WANDB_PROJECT", "robuchan"))
    parser.add_argument("--no-wandb", action="store_true", help="Disable W&B logging.")
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--save-strategy", type=str, default="epoch")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def detect_dtype() -> tuple[bool, bool]:
    """Return (bf16, fp16) based on GPU capabilities."""
    if torch.cuda.is_available():
        if torch.cuda.is_bf16_supported():
            return True, False
        return False, True
    return False, False


def load_data(args: argparse.Namespace):
    """Load train/validation splits from HF dataset repo."""
    ds = load_dataset(
        args.dataset,
        data_files={"train": args.train_file, "validation": args.valid_file},
    )
    print(f"train: {len(ds['train'])} rows, validation: {len(ds['validation'])} rows")
    return ds["train"], ds["validation"]


def main() -> int:
    args = parse_args()

    # W&B setup
    report_to = "none"
    if not args.no_wandb and os.environ.get("WANDB_API_KEY"):
        os.environ["WANDB_PROJECT"] = args.wandb_project
        report_to = "wandb"
        print(f"W&B enabled: project={args.wandb_project}")
    else:
        print("W&B disabled")

    # Detect precision
    if args.bf16 is None and args.fp16 is None:
        bf16, fp16 = detect_dtype()
    else:
        bf16 = bool(args.bf16)
        fp16 = bool(args.fp16)
    print(f"precision: bf16={bf16}, fp16={fp16}")

    # Load data
    train_dataset, eval_dataset = load_data(args)

    # Quantization config (QLoRA)
    quantization_config = None
    if args.use_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        print("QLoRA: 4-bit quantization enabled")

    # Load model
    print(f"loading model: {args.base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quantization_config,
        device_map="auto",
        torch_dtype=torch.bfloat16 if bf16 else torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # LoRA config
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    # Training config
    training_args = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.num_train_epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_length=args.max_length,
        bf16=bf16,
        fp16=fp16,
        logging_steps=args.logging_steps,
        save_strategy=args.save_strategy,
        eval_strategy="epoch",
        report_to=report_to,
        seed=args.seed,
        push_to_hub=args.push_to_hub,
        hub_model_id=args.hub_model_id if args.push_to_hub else None,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        peft_config=peft_config,
        processing_class=tokenizer,
    )

    # Train
    print("starting training")
    train_result = trainer.train()
    print(f"training complete: {train_result.metrics}")

    # Save
    trainer.save_model()
    tokenizer.save_pretrained(args.output_dir)
    print(f"adapter saved to {args.output_dir}")

    if args.push_to_hub:
        print(f"pushing to hub: {args.hub_model_id}")
        trainer.push_to_hub()
        print("push complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
