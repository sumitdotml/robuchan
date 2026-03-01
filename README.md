# Robuchan

Recipe adaptation fine-tuning for the Mistral AI Worldwide Hackathon Tokyo (Feb 28 - Mar 1, 2026).

Fine-tune `mistral-small-latest` on synthetic dietary recipe adaptations generated from Food.com recipes via `mistral-large-latest`.

## Key Files

| File | What it covers |
|---|---|
| [`PLAN.md`](PLAN.md) | Full 2-day execution plan: timeline, architecture, quality gates, templates, budget |
| [`DATASET_SCHEMA.md`](DATASET_SCHEMA.md) | Internal master format, export contract, scoring definitions, prompt templates |
| [`eval/constraints.json`](eval/constraints.json) | Banned ingredient lists per dietary constraint (9 categories) |
| [`CONSIDERING.md`](CONSIDERING.md) | Dataset strategy decision log and alternatives analysis |
| [`LOG.md`](LOG.md) | Decision audit trail |

## Quick Start

```bash
uv sync
cp .env.example .env  # add MISTRAL_API_KEY, WANDB_API_KEY, HF_TOKEN
set -a; source .env; set +a
```

## Credential Quick Check

Verify Mistral key:

```bash
curl -sS https://api.mistral.ai/v1/models \
  -H "Authorization: Bearer $MISTRAL_API_KEY"
```

Verify W&B key:

```bash
curl -sS https://api.wandb.ai/graphql \
  -u "api:$WANDB_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"query":"query { viewer { id username } }"}'
```

## Fine-tune Scripts

Run dataset preflight checks:

```bash
uv run python train/preflight.py \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl
```

Validation size note:
- Hard API limit is `1MB` for validation file size.
- Mistral FAQ rule-of-thumb max is `min(1MB, 5% of training file size)`.
- For current files (~5.18MB train, ~0.597MB valid), validation is above the rule-of-thumb max (~0.259MB) but still under the hard 1MB limit.

Upload files and create/start a job:

```bash
uv run python train/finetune.py upload \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl

uv run python train/finetune.py check-quality-gate \
  --quality-gate-path artifacts/quality_gate_report.json

uv run python train/finetune.py create-job \
  --model mistral-small-latest \
  --training-steps 40 \
  --learning-rate 1e-4 \
  --suffix robuchan-foodcom-synth \
  --wandb-project robuchan

uv run python train/finetune.py start-job
uv run python train/finetune.py wait
uv run python train/finetune.py status --json
```

Hyperparameter rationale for the default launch command:
- `training_steps=40` is dataset-sized for current train file (~5.18 MB), which is ~7.7 epochs using Mistral FAQ rule-of-thumb: `epochs ≈ steps / train_file_MB`.
- `learning_rate=1e-4` follows Mistral's recommended range for LoRA-style runs (`1e-4` or `1e-5`).
- If dataset size changes, recompute steps from the same formula instead of reusing 40 blindly.

Job/file IDs are saved to `artifacts/ft_run_manifest.json`.
When `WANDB_API_KEY` is set, W&B tracking is enabled automatically. The project is selected from `--wandb-project`, then `WANDB_PROJECT`, then `robuchan`.
W&B project does not need to be created manually beforehand in most cases; if the API key has permission, the run can create the project on first write.

## Stack

- **Fine-tuning**: Mistral API (cloud, not local)
- **Generation**: `mistral-large-latest` for synthetic training data
- **Eval**: deterministic compliance + LLM-as-judge
- **Tracking**: W&B (auto via Mistral `integrations` + manual eval logging)
- **Demo**: Marimo
- **Deps**: `uv`
