# Arena dei Poveri

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

Upload files and create/start a job:

```bash
uv run python train/finetune.py upload \
  --train-path data/train_filtered.jsonl \
  --valid-path data/valid_filtered.jsonl

uv run python train/finetune.py check-quality-gate \
  --quality-gate-path artifacts/quality_gate_report.json

uv run python train/finetune.py create-job \
  --model mistral-small-latest \
  --training-steps 100 \
  --learning-rate 1e-4 \
  --suffix recipe-remix-foodcom-synth \
  --wandb-project recipe-remix

uv run python train/finetune.py start-job
uv run python train/finetune.py wait
uv run python train/finetune.py status --json
```

Job/file IDs are saved to `artifacts/ft_run_manifest.json`.
When `WANDB_API_KEY` is set, W&B tracking is enabled automatically. The project is selected from `--wandb-project`, then `WANDB_PROJECT`, then `recipe-remix`.
W&B project does not need to be created manually beforehand in most cases; if the API key has permission, the run can create the project on first write.

## Stack

- **Fine-tuning**: Mistral API (cloud, not local)
- **Generation**: `mistral-large-latest` for synthetic training data
- **Eval**: deterministic compliance + LLM-as-judge
- **Tracking**: W&B (auto via Mistral `integrations` + manual eval logging)
- **Demo**: Marimo
- **Deps**: `uv`
