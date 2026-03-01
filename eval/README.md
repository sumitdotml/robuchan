# Eval Pipeline Guide

This folder contains the evaluation pipeline for recipe-adaptation models.

It starts from prepared eval JSONL splits and ends with:
- per-run metrics JSON
- per-row JSONL outputs
- W&B charts/tables when `WANDB_API_KEY` is set
- hard-case pairwise comparison (`hard_case_win_rate`)

## 1. Folder Map

- `evaluate.py`: evaluate a fine-tuned model (or manifest model fallback).
- `baseline.py`: evaluate baseline model (`mistral-small-latest`).
- `eval_engine.py`: shared logic used by both CLIs.
- `compare_hard_cases.py`: baseline-vs-candidate pairwise comparator on row outputs.
- `constraints.json`: deterministic banned-term/constraint config.
- `hard_cases.jsonl`: hard30 evaluation bank input.

## 2. Where It Begins

The pipeline begins with eval split files generated outside this folder by dataset/export scripts.

Expected inputs:
- `data/quick50.jsonl`
- `data/final150.jsonl`
- `eval/hard_cases.jsonl`

Required env var:
- `MISTRAL_API_KEY`

W&B env vars:
- `WANDB_API_KEY`
- `WANDB_PROJECT` (optional; defaults to `robuchan`)
- `WANDB_ENTITY` (optional unless your workspace setup needs it)

## 3. Step-by-Step Flow

### Step 0: Sanity check CLI access

```bash
uv run python eval/baseline.py --help
uv run python eval/evaluate.py --help
uv run python eval/compare_hard_cases.py --help
```

### Step 1: Run baseline on the target split

Quick gate:

```bash
uv run python eval/baseline.py \
  --input data/quick50.jsonl \
  --split-name quick50
```

Final gate:

```bash
uv run python eval/baseline.py \
  --input data/final150.jsonl \
  --split-name final150
```

Hard cases (recommended to keep a dedicated rows file):

```bash
uv run python eval/baseline.py \
  --input eval/hard_cases.jsonl \
  --split-name hard30 \
  --rows-output-path artifacts/baseline_hard30_rows.jsonl \
  --output-path artifacts/baseline_hard30_metrics.json
```

### Step 2: Run fine-tuned model eval

Explicit model id:

```bash
uv run python eval/evaluate.py \
  --input data/final150.jsonl \
  --split-name final150 \
  --model ft:your-model-id
```

Manifest fallback (reads `artifacts/ft_run_manifest.json` -> `job.fine_tuned_model`):

```bash
uv run python eval/evaluate.py \
  --input data/final150.jsonl \
  --split-name final150
```

Hard cases for comparator:

```bash
uv run python eval/evaluate.py \
  --input eval/hard_cases.jsonl \
  --split-name hard30 \
  --model ft:your-model-id \
  --rows-output-path artifacts/finetuned_hard30_rows.jsonl \
  --output-path artifacts/finetuned_hard30_metrics.json
```

### Step 3: Compute hard-case pairwise win rate

```bash
uv run python eval/compare_hard_cases.py \
  --baseline-rows artifacts/baseline_hard30_rows.jsonl \
  --candidate-rows artifacts/finetuned_hard30_rows.jsonl \
  --split-name hard30 \
  --output-path artifacts/hard_case_comparison.json
```

Optional strict judge-only scoring:

```bash
uv run python eval/compare_hard_cases.py \
  --baseline-rows artifacts/baseline_hard30_rows.jsonl \
  --candidate-rows artifacts/finetuned_hard30_rows.jsonl \
  --split-name hard30 \
  --strict-judge
```

### Step 4: Review outputs

Main files:
- Baseline summary: `artifacts/baseline_metrics.json`
- Baseline rows: `artifacts/baseline_rows.jsonl`
- Candidate summary: `artifacts/eval_metrics.json`
- Candidate rows: `artifacts/eval_rows.jsonl`
- Hard-case comparison: `artifacts/hard_case_comparison.json`

Most important metrics to check:
- `constraint_pass_rate`
- `format_pass_rate`
- `avg_judge_score`
- `hard_case_win_rate`
- `score_source_pair_breakdown` and `mixed_source_incomparable_rate` (to detect judge/fallback mixing excluded from pairwise math)

## 4. Optional Modes

Deterministic-only run (no judge call):

```bash
uv run python eval/evaluate.py \
  --input data/quick50.jsonl \
  --split-name quick50 \
  --model ft:your-model-id \
  --disable-judge
```

Dry run (no inference API call):

```bash
uv run python eval/evaluate.py \
  --input data/quick50.jsonl \
  --split-name quick50 \
  --model mistral-small-latest \
  --disable-judge \
  --dry-run
```

Limit rows while debugging:

```bash
uv run python eval/evaluate.py \
  --input data/final150.jsonl \
  --split-name final150 \
  --model ft:your-model-id \
  --limit 5
```

## 5. W&B Logging

W&B logging auto-enables whenever `WANDB_API_KEY` is set.

```bash
uv run python eval/evaluate.py \
  --input data/final150.jsonl \
  --split-name final150 \
  --model ft:your-model-id \
  --wandb-project robuchan
```

Optional:
- `--wandb-project <project>` to override project selection
- `--wandb-entity <entity>`
- `--wandb-run-name <name>`

When enabled, the scripts log:
- summary numeric metrics
- token/cost counters
- per-row table (`eval_rows`)

## 6. Where It Finishes

The eval lifecycle is complete when you have:
1. baseline summary + rows for the relevant split(s)
2. fine-tuned summary + rows for the same split(s)
3. hard-case pairwise comparison JSON (for `hard_case_win_rate`)
4. W&B run URL captured in the metrics JSON when logging is enabled
