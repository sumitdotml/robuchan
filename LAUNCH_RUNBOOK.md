# Fine-Tuning Launch Runbook (Skip Quality Gate Default)

This runbook defines the operational steps to launch fine-tuning from the current repository state.

Default policy for this project:
- Use `--skip-quality-gate` for `create-job` and `start-job`.
- Do not block launch on `artifacts/quality_gate_report.json`.

Model choice policy:
- Be explicit with `--model` on every launch.
- `train/finetune.py` default is `mistral-small-latest` (more capable, higher cost).
- This runbook uses `ministral-3b-latest` by default (recommended alias for fine-tune workflow docs).
- If you want a pinned snapshot for reproducibility, use `ministral-3b-2512` (Ministral 3 3B 25.12) instead of the alias.

## 1. Preconditions

1. Work from repo root:
```bash
cd /Users/sumit/playground/hackathons/mistral-tokyo-2026
```
2. Ensure filtered datasets exist:
```bash
ls -lh data/train_filtered.jsonl data/valid_filtered.jsonl
wc -l data/train_filtered.jsonl data/valid_filtered.jsonl
```
3. Ensure required environment variables:
```bash
export MISTRAL_API_KEY=...
export WANDB_API_KEY=...          # recommended for tracking
export WANDB_PROJECT=robuchan
```

## 2. Optional: Refresh Local Data From Hugging Face

Use this only if local `data/train_filtered.jsonl` and `data/valid_filtered.jsonl` are outdated or missing.

```bash
hf download sumitdotml/robuchan-data \
  data/train_filtered.jsonl data/valid_filtered.jsonl \
  --repo-type dataset \
  --local-dir /Users/sumit/playground/hackathons/mistral-tokyo-2026 \
  --local-dir-use-symlinks False
```

## 3. Preflight Validation (No Quality Gate Dependency)

```bash
uv run python train/preflight.py \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl \
  --summary-path artifacts/preflight_summary.json
```

## 4. Upload Data Files

```bash
uv run python train/finetune.py upload \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl \
  --manifest-path artifacts/ft_run_manifest.json
```

## 5. Create Fine-Tuning Job (Skip Gate)

Recommended to create first without auto-start:

If pinning the model version, replace `ministral-3b-latest` with `ministral-3b-2512`.

```bash
uv run python train/finetune.py create-job \
  --model ministral-3b-latest \
  --training-steps 100 \
  --learning-rate 1e-4 \
  --suffix robuchan-v1 \
  --skip-quality-gate \
  --manifest-path artifacts/ft_run_manifest.json
```

Optional auto-start variant:

```bash
uv run python train/finetune.py create-job \
  --model ministral-3b-latest \
  --training-steps 100 \
  --learning-rate 1e-4 \
  --suffix robuchan-v1 \
  --auto-start \
  --skip-quality-gate \
  --manifest-path artifacts/ft_run_manifest.json
```

## 6. Start Job (If Not Auto-Started)

```bash
uv run python train/finetune.py start-job \
  --skip-quality-gate \
  --manifest-path artifacts/ft_run_manifest.json
```

## 7. Monitor Job

`wait` blocks until terminal status (`SUCCESS`, `FAILED`, `FAILED_VALIDATION`, or `CANCELLED`).
Check `status` first before committing to a blocking wait in the current shell session.

```bash
uv run python train/finetune.py status --manifest-path artifacts/ft_run_manifest.json
uv run python train/finetune.py wait --manifest-path artifacts/ft_run_manifest.json
uv run python train/finetune.py status --manifest-path artifacts/ft_run_manifest.json --json
```

## 8. Operational Controls

List recent jobs:

```bash
uv run python train/finetune.py list-jobs --model ministral-3b-latest
```

Cancel active job:

```bash
uv run python train/finetune.py cancel-job --manifest-path artifacts/ft_run_manifest.json
```

## Notes

- `scripts/prelaunch_check.py` will fail if quality-gate artifact is missing; skip that script when following this default policy.
- This document is a runbook only. It does not start jobs by itself.
