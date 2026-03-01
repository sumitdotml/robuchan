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

## 1.1 Logic by File

### `eval/evaluate.py`

- Thin CLI wrapper for candidate/fine-tuned evaluation.
- Uses `eval_engine.build_parser(...)` with `allow_manifest_model=True`.
- Model resolution order:
  - `--model` (explicit), else
  - `artifacts/ft_run_manifest.json -> job.fine_tuned_model` (unless `--no-manifest-model`).
- Delegates all scoring and output writing to `eval_engine.run(...)`.

### `eval/baseline.py`

- Thin CLI wrapper for baseline evaluation.
- Default model is `mistral-small-latest`.
- Uses `allow_manifest_model=False` (must use explicit/default baseline model, never manifest fallback).
- Delegates scoring/output to `eval_engine.run(...)` with different default output paths.

### `eval/eval_engine.py`

This is the core pipeline. For each row:

1. Parse row and normalize chat messages.
2. Resolve restrictions from structured fields (`target_restrictions`, `restrictions`, `target_constraints`) with user-text fallback.
3. Generate model output using selected inference backend:
   - `mistral_api`: calls Mistral Chat API.
   - `hf_local`: loads HF model/adapter locally (`transformers` + `peft`) and generates with chat template.
4. Run deterministic checks:
   - **Format check** (`format_pass`): requires all section headers:
     - Substitution Plan
     - Adapted Ingredients
     - Adapted Steps
     - Flavor Preservation Notes
     - Constraint Check
   - Also fails on placeholders (`...`, `same as original`).
   - **Constraint check** (`constraint_pass`): banned-term matching from `constraints.json` against adapted content sections.
5. Optional judge scoring (`--disable-judge` off):
   - Judge prompt returns JSON with:
     - `compliance`
     - `flavor_fidelity`
     - `dish_identity_preservation`
     - `explanation_quality`
     - `overall_score`
6. Aggregate summary metrics across rows.

Key summary fields and exact behavior:

- `format_pass_rate`: mean of boolean `format_pass` over all rows.
- `constraint_pass_rate`: mean of `constraint_pass` over rows where constraints were actually checked.
- `judge_score_coverage`: fraction of rows with parseable judge score.
- `avg_judge_score`: only populated when judge coverage is complete; otherwise `null`.
- `avg_judge_score_scored_rows`: mean on scored subset (can be non-null even with partial coverage).
- `judge_missing_rows` / `judge_overall_invalid_rows`: explicit judge completeness diagnostics.
- `tokens.*` and `estimated_cost_usd.*`: token accounting and cost estimates from provided price flags.

Outputs:

- Metrics JSON (`--output-path`).
- Per-row JSONL (`--rows-output-path`).
- Optional W&B summary + row table when `WANDB_API_KEY` is set.

### `eval/compare_hard_cases.py`

Pairwise baseline-vs-candidate comparator on row-level outputs:

1. Index both row files by `row_id`.
2. Compare only row-id intersection.
3. Score source per row:
   - Preferred: `judge.overall_score`.
   - Fallback (when not `--strict-judge`): `1.0` if `constraint_pass` else `0.0`, plus `0.1` if `format_pass`.
4. Mixed source buckets (`judge` vs `fallback`) are marked `incomparable` and excluded from win/loss/tie.
5. Headline metrics:
   - `hard_case_win_rate`
   - `hard_case_non_loss_rate`
   - `avg_score_delta`
6. If baseline/candidate row-id sets mismatch, headline metrics are suppressed (`null`) to prevent misleading comparisons.

### `eval/constraints.json`

- Canonical deterministic rules for banned-term matching by restriction.
- Loaded and compiled to regex patterns at runtime.
- Unknown restrictions in data are recorded per row as `unknown_restrictions`.

### `eval/hard_cases.jsonl`

- Curated hard30 input split (same row schema as other eval splits).
- Used for high-signal A/B comparison with `compare_hard_cases.py`.

## 2. Where It Begins

The pipeline begins with eval split files generated outside this folder by dataset/export scripts.

Expected inputs:
- `data/quick50.jsonl`
- `data/final150.jsonl`
- `eval/hard_cases.jsonl`

Inference/judge env requirements:
- `MISTRAL_API_KEY` is required when:
  - `--inference-backend mistral_api`, or
  - judge scoring is enabled (`--disable-judge` not set).
- `MISTRAL_API_KEY` is not required for fully local deterministic runs:
  - `--inference-backend hf_local --disable-judge`.
- `HF_TOKEN` may be required for `hf_local` if model/adapters are private.
- `hf_local` also requires local deps: `torch`, `transformers`, `peft` (and typically `accelerate`).

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
