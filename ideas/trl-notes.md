# TRL (Hugging Face) Fine-Tuning Notes

Research notes for potential future use. Not currently in our pipeline.

## What is TRL?

HF's post-training library. Despite the name ("Transformer Reinforcement Learning"), covers full post-training: SFT, DPO, GRPO, reward modeling. `SFTTrainer` is the main entry point for supervised fine-tuning — thin wrapper around HF `Trainer` with native LoRA, chat template handling, and sequence packing.

## TRL vs Mistral Fine-Tuning API

| Aspect | TRL (local) | Mistral API |
|--------|-------------|-------------|
| Hardware | Your GPU/CPU | Mistral's servers |
| Cost | Free (your hardware) | Per-job pricing |
| W&B | Native, full metrics | Broken (40-char key limit) |
| Control | Full (optimizer, scheduler, LoRA config) | Limited knobs |
| Output | LoRA adapter files you own | Hosted endpoint |
| Models | Open-weight only (Ministral 3B/8B) | Open + commercial |

## W&B Integration

TRL solves our W&B problem completely. Just set `report_to="wandb"` in SFTConfig. Logs training loss, LR schedule, grad norms, eval metrics automatically. No 40-char key nonsense.

## Apple Silicon (M5 32GB) Feasibility

- **Ministral 3B + LoRA**: ~8-10GB. Feasible.
- **Ministral 8B + LoRA**: ~16-20GB. Tight but possible with gradient checkpointing.
- PyTorch MPS backend is experimental. Need `PYTORCH_ENABLE_MPS_FALLBACK=1`.
- **MLX-LM is faster on Apple Silicon** — purpose-built for unified memory.
- `bitsandbytes` (QLoRA 4-bit) has limited MPS support.

## Minimal Example (Ministral 3B)

```python
from trl import SFTTrainer, SFTConfig
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("mistralai/Ministral-3-3B-Instruct-2512", device_map="auto")
tokenizer = AutoTokenizer.from_pretrained("mistralai/Ministral-3-3B-Instruct-2512")

peft_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    task_type="CAUSAL_LM",
)

training_args = SFTConfig(
    output_dir="./ministral-3b-lora",
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    learning_rate=2e-4,
    gradient_checkpointing=True,
    max_length=2048,
    report_to="wandb",
)

# Dataset format: {"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}
trainer = SFTTrainer(model=model, args=training_args, train_dataset=dataset, peft_config=peft_config, processing_class=tokenizer)
trainer.train()
trainer.model.save_pretrained("./adapter")
```

## Key Config Notes

- LoRA targets for Mistral: `q_proj`, `k_proj`, `v_proj`, `o_proj` (add `gate_proj`, `up_proj`, `down_proj` for more capacity)
- Dataset columns: must be `text`, `messages`, or `prompt`+`completion` — misnamed columns fail silently
- Sequence packing: `packing=True` in SFTConfig for short examples
- M5 supports bf16
- `save_pretrained()` saves adapter only (~50-200MB); merge with `model.merge_and_unload()` for full model

## Bottom Line

TRL is the right tool if we move to local fine-tuning. For our current Mistral API path, it's not needed — but it completely solves the W&B gap and gives us full control. If Mistral API hits more friction, TRL + Ministral 3B on M5 is a viable fallback.
