# Fine-Tuning Launch Runbook

This runbook defines the operational steps to launch fine-tuning from the current repository state.

## Training backend

**Active: TRL + HF Jobs** (runs on HF GPU infrastructure via `train/launch_hf_job.py`).

The Mistral fine-tuning API path (`train/finetune.py`) is blocked — their API rejects all models with "Model not available for this type of fine-tuning (completion)" despite a valid Scale plan with fine-tuning access. See [Appendix A](#appendix-a-mistral-api-path-blocked) for details.

## 1. Preconditions

1. Work from repo root:
```bash
cd /Users/sumit/playground/hackathons/mistral-tokyo-2026
```
2. Ensure filtered datasets exist on HF Hub:
```bash
uv run python -c "
from huggingface_hub import HfApi
files = HfApi().list_repo_files('sumitdotml/robuchan-data', repo_type='dataset')
print([f for f in files if 'jsonl' in f])
"
```
3. Ensure required environment variables:
```bash
export HF_TOKEN=...               # write access required (push adapter to hub)
export WANDB_API_KEY=...          # optional, for training loss curves
export WANDB_PROJECT=robuchan
export MISTRAL_API_KEY=...        # still needed for eval (judge model)
```
4. Install local eval inference deps (for HF adapter evaluation path):
```bash
uv add torch transformers peft accelerate
```

## 2. Preflight Validation

```bash
uv run python train/preflight.py \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl \
  --summary-path artifacts/preflight_summary.json
```

## 3. Push Code to GitHub

The HF Job container clones the repo at launch time. Any changes to training code **must be pushed to main** before launching.

Ensure you are on `main` (or merge your branch first), then push:

```bash
git branch --show-current   # verify you're on main
git push origin main
```

## 4. Launch Fine-Tuning Job

```bash
uv run python train/launch_hf_job.py
```

Default configuration (override via CLI args):
- **Model**: `mistralai/Ministral-8B-Instruct-2410` (open-weight, Apache 2.0) with QLoRA (4-bit)
- **Method**: QLoRA (r=16, alpha=32, targets: q/k/v/o projections, 4-bit quantization)
- **Epochs**: 3
- **Learning rate**: 2e-4 (standard for TRL + LoRA; higher than Mistral API's 1e-4 because only adapter weights update)
- **Effective batch size**: 16 (batch=1 × gradient_accumulation=16)
- **GPU**: A10G-large (24GB VRAM, 12 vCPU, 46GB RAM) at ~$1.50/hr
- **W&B**: native integration, full training loss curves (no 40-char key limitation)
- **Output**: adapter pushed to `sumitdotml/robuchan` on HF Hub

Custom run example:

```bash
uv run python train/launch_hf_job.py \
  --use-4bit \
  --num-train-epochs 5 \
  --learning-rate 1e-4 \
  --flavor a10g-large \
  --timeout 2h
```

## 5. Monitor Job

```bash
# Check status
uv run python train/launch_hf_job.py --status <JOB_ID>

# Stream logs (follows until job completes)
uv run python train/launch_hf_job.py --logs <JOB_ID>

# Cancel if needed
uv run python train/launch_hf_job.py --cancel <JOB_ID>
```

## 6. Verify Output

After the job completes, the LoRA adapter should be at `sumitdotml/robuchan` on HF Hub:

```bash
uv run python -c "
from huggingface_hub import HfApi
files = HfApi().list_repo_files('sumitdotml/robuchan')
print(files)
"
```

## 7. Run Evaluation

Run local inference against the HF adapter:

```bash
uv run python eval/evaluate.py \
  --input eval/quick50.jsonl \
  --split-name quick50 \
  --model sumitdotml/robuchan \
  --inference-backend hf_local \
  --disable-judge
```

With judge scoring enabled (requires `MISTRAL_API_KEY`):

```bash
uv run python eval/evaluate.py \
  --input eval/quick50.jsonl \
  --split-name quick50 \
  --model sumitdotml/robuchan \
  --inference-backend hf_local
```

## Cost Estimate

- A10G-large: ~$1.50/hr
- Expected training time: 30-45 min for 1090 rows, 3 epochs
- Per-run cost: ~$0.75-$1.10
- Budget: $30 credits = ~25+ runs

## Notes

- The HF Job container clones the GitHub repo (`sumitdotml/robuchan`) at launch. Changes must be on main. The repo is public; no GitHub auth needed.
- Preflight validates local `data/*.jsonl`; training loads from `sumitdotml/robuchan-data` on HF Hub. Keep both in sync.
- Runtime deps are installed via pip inside the container (unpinned — hackathon tradeoff).
- W&B integration works natively through TRL's HF Trainer. No workarounds needed.
- This document is a runbook only. It does not start jobs by itself.

---

## Appendix A: Mistral API Path (Blocked)

The Mistral fine-tuning API (`train/finetune.py`) is **not currently usable**. Issues encountered:

1. **Fine-tuning API rejects all models**: `"Model not available for this type of fine-tuning (completion). Available model(s): "` — empty list despite Scale plan with explicit "Access to the fine-tuning API" and fine-tuning limits configured (3 concurrent jobs, unlimited tokens).
2. **W&B integration broken**: Mistral validates W&B API keys as exactly 40 characters, but W&B now issues 86-character keys.

The `train/finetune.py` code remains in the repo for reference but is not part of the active launch path. All Mistral API file uploads (step 4 of the old runbook) completed successfully — only job creation is blocked.
