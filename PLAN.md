# 2-Day Execution Plan: Recipe Remix Fine-Tuning (Mistral API)

## Summary

- Fine-tune **mistral-small-latest** via **Mistral's managed cloud fine-tuning API** for dietary recipe adaptation.
- Training runs server-side (~30-60 min) while we build eval, demo, and everything else in parallel.
- W&B integration is built-in via the `integrations` parameter — zero custom code for training metrics.
- Demo via Marimo app showing base vs fine-tuned + LLM-as-judge scores.
- Use one workspace as primary and the second as contingency (since workspaces are separate).
- Publish training data, eval results, and model card to HuggingFace.

## Architecture

```
Local Machine                     Mistral API                    W&B
  |                                  |                            |
  |--- upload train.jsonl ---------->|                            |
  |--- upload valid.jsonl ---------->|                            |
  |--- create fine-tuning job ------>|--- train server-side ----->|
  |                                  |--- log metrics ----------->|
  |<-- poll job status --------------|                            |
  |                                  |                            |
  |--- inference (fine_tuned_model)->|                            |
  |<-- response ---------------------|                            |
```

- Training happens on Mistral's servers, not locally
- W&B integration is built-in via `integrations` parameter
- Inference uses the `fine_tuned_model` ID returned by the job
- Base model: `mistral-small-latest`
- Teammates use separate Mistral Workspaces (cannot share Mistral job logs/files directly)

## Collaboration Model (Separate Workspaces)

- **Workspace A (primary)**: main fine-tune run, final model ID for demo/submission.
- **Workspace B (contingency)**: optional backup run if primary misses kill switch.
- **Shared visibility layer**: use one shared W&B project for both runs so both teammates can monitor from anywhere.
- **Rule**: do not split one experiment across two workspaces. Each run is fully contained in one workspace.

## Budget Guardrails

- Credits available: **$15 (you) + $15 (teammate), not pooled in one workspace**.
- Cap each workspace to **max 2 fine-tune jobs** for the weekend.
- Keep `mini` split as default for all runs unless a bigger run is launched before Day 1 noon.
- Reserve at least **$3/workspace** for inference, judge scoring, and demo retries.

## Priority Stack

1. **Data quality gate + pipeline** — download, parse, validate, convert to Mistral JSONL format, upload
2. **Fine-tuning via Mistral API** — create job, monitor, get fine-tuned model ID
3. **Evaluation** — deterministic compliance checks + two-stage LLM-as-judge via `mistral-large-latest`
4. **W&B experiment tracking** — automatic via Mistral API `integrations` param + manual eval logging
5. **Demo** — Marimo app showing base vs finetuned + judge scores
6. **HF publish** — training data, eval results, model card (adapter stays on Mistral's infra)
7. *(bonus, time permitting)* W&B Weave traces, W&B Report, mini challenge

## Scope Freeze

- In scope:
  1. Mistral API fine-tune for recipe adaptation under dietary constraints
  2. Deterministic evaluation + LLM-as-judge quality scoring
  3. W&B Models logging (automatic + manual eval), W&B Report
  4. HuggingFace publication with dataset/license disclosures
  5. Marimo interactive demo app
- Out of scope:
  1. Full arena UI or complex frontend
  2. Local MLX training
  3. Creating a custom dataset from scratch

## Dataset Strategy

- Primary: `Sohy/RecipePair` — `mini` split first (8K rows), `default` (64K) if Run #2 needed
- The `base` column embeds constraint as `categories: ['dairy_free']`. Parse via regex.
- Convert to chat JSONL with system prompt + user prompt + assistant response
- Split: shuffle and partition into train/valid/eval (`quick50` subset + `final120` holdout from eval pool)
- **Mandatory data quality gate before Run #1** (random 100 rows from train candidate set):
  1. Parse success rate >= 99%
  2. Constraint extraction success >= 99%
  3. Target adaptation non-triviality >= 85% (ingredient or instruction changed vs source)
  4. Duplicate pair rate <= 5%
  5. If any check fails, fix parser/filtering before any fine-tune spend

## JSONL Format (Mistral API)

```json
{"messages": [{"role": "system", "content": "You are a culinary adaptation assistant..."}, {"role": "user", "content": "Adapt this recipe for dairy free:\n\n..."}, {"role": "assistant", "content": "...adapted recipe..."}]}
```

One JSON object per line, `messages` array with `role`/`content`.

## System Prompt

```
You are a culinary adaptation assistant specializing in dietary-compliant recipe transformation.

Given a recipe and a dietary constraint, you must:
1. Replace all non-compliant ingredients with appropriate substitutes
2. Adjust cooking instructions to reflect ingredient changes
3. Preserve the original dish's flavor profile and cultural identity
4. Provide clear substitution rationale for each change
```

## Training Workflow (Mistral API)

```python
import os
from mistralai import Mistral

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

# Upload data
train_file = client.files.upload(
    file={"file_name": "train.jsonl", "content": open("data/train.jsonl", "rb")}
)
val_file = client.files.upload(
    file={"file_name": "valid.jsonl", "content": open("data/valid.jsonl", "rb")}
)

# Create fine-tuning job with W&B integration
job = client.fine_tuning.jobs.create(
    model="mistral-small-latest",
    training_files=[{"file_id": train_file.id, "weight": 1}],
    validation_files=[val_file.id],
    hyperparameters={"training_steps": 100, "learning_rate": 1e-4},
    auto_start=False,
    integrations=[{
        "project": "recipe-remix",
        "api_key": os.environ["WANDB_API_KEY"]
    }],
    suffix="recipe-remix",
)

# Start and monitor
client.fine_tuning.jobs.start(job_id=job.id)
status = client.fine_tuning.jobs.get(job_id=job.id)
# status.status: QUEUED -> STARTED -> RUNNING -> SUCCESS
# status.fine_tuned_model: use this ID for inference
```

## Inference

```python
response = client.chat.complete(
    model=status.fine_tuned_model,  # e.g. "ft:mistral-small-latest:xxxxx"
    messages=[{"role": "user", "content": prompt}]
)
```

## Evaluation: Deterministic + LLM-as-Judge

**Deterministic compliance** (`eval/constraints.json`): banned ingredient lists per dietary constraint. `constraint_pass_rate` = (examples with 0 violations) / total.

**LLM-as-Judge** (Mistral Large): rates adapted recipes on compliance, coherence, completeness, clarity (1-10 each). Returns structured JSON.

**Two-stage evaluation**:
1. **Quick gate**: 50 held-out examples for fast iterate/no-iterate decision.
2. **Final freeze**: 120 held-out examples on best run for submission metrics.

Use the same examples/prompts for base and fine-tuned runs. The score delta is the headline number.

## Demo (Marimo)

`marimo run demo/demo.py` launches an interactive web app:
1. Dropdown: select dietary constraint
2. Text area: paste a recipe OR select from pre-loaded examples
3. Button: "Remix!"
4. Side-by-side: base model vs fine-tuned model responses
5. Judge scores: Mistral Large rates both outputs live (with cached fallback)
6. Compliance check: pass/fail with violations highlighted

Demo reliability rule:
- Precompute and cache at least 5 representative examples (base output, fine-tuned output, judge scores, compliance results).
- If live API is slow/failing, switch to cached mode and continue demo.

## W&B Integration

- **Automatic**: `integrations` parameter sends training metrics to W&B. Zero custom code.
- **Manual**: Log comparison metrics (base vs fine-tuned) and artifacts after evaluation.
- **Team setup**: both workspaces log into the same W&B project/entity for shared visibility.
- **Bonus**: W&B Weave traces, Report, mini challenge.

## File Structure

| File | Purpose |
|------|---------|
| `data/prepare.py` | Dataset download, constraint parsing, JSONL conversion |
| `train/finetune.py` | Mistral API: upload data, create job, start, monitor |
| `eval/evaluate.py` | Deterministic compliance + LLM-as-judge via Mistral Large |
| `eval/baseline.py` | Base model evaluation (same harness, base model ID) |
| `eval/constraints.json` | Banned ingredient lists per dietary constraint |
| `demo/demo.py` | Marimo interactive demo app |
| `scripts/log_artifacts.py` | W&B artifact + eval metric logging |
| `scripts/hf_publish.py` | HuggingFace publication (data, eval, model card) |

## 2-Day Timeline

### Day 1: Saturday, February 28, 2026 (10:00-19:00 JST)

**Block 1 (10:00-12:00): Environment + Data Pipeline + Quality Gate [120 min]**
- Verify env: `MISTRAL_API_KEY`, add `WANDB_API_KEY`, `HF_TOKEN` to `.env`
- Install: `pip install mistralai wandb marimo datasets rich`
- Run `data/prepare.py` — download, parse, convert to JSONL
- Validate JSONL, spot-check 10 examples
- Run mandatory quality gate checks on 100 random rows
- **Exit**: quality gate passes and `data/train.jsonl`, `data/valid.jsonl`, `data/eval_holdout.jsonl` exist

**Block 2 (12:00-13:00): Upload + Launch Fine-Tuning [60 min]**
- Run `train/finetune.py` — upload files, create job, start training
- Verify job status is RUNNING and W&B dashboard shows metrics
- **Exit**: Job running server-side. Build everything else while it trains.

**Block 3 (13:00-15:00): Baseline Eval + Eval Harness (WHILE TRAINING RUNS) [120 min]**
- Run `eval/baseline.py` — 50 held-out examples through base model
- Record baseline `constraint_pass_rate`, `format_pass_rate`, avg judge scores
- Log baseline to W&B
- **Exit**: Baseline numbers recorded, eval harness ready for fine-tuned model

**Block 4 (15:00-16:00): Fine-Tuned Quick Eval + Comparison [60 min]**
- Check fine-tuning job status (should be done by now)
- Run `eval/evaluate.py --model ft:xxx --tag finetuned --split quick50`
- Run `scripts/log_artifacts.py` to log comparison to W&B

**KILL SWITCH 1 (16:00)**: `constraint_pass_rate` improved >= +5% OR avg judge score >= +0.5?
- YES → Block 5A (demo build)
- NO → Block 5B (contingency Run #2 on teammate workspace with adjusted hyperparams)

**Block 5A (16:00-18:00): Build Demo [120 min]**
- Build Marimo demo, pre-load example recipes
- Test 3 consecutive runs

**Block 5B (16:00-18:00): Run #2 + Demo [120 min]**
- Launch Run #2 in Workspace B, build demo against Run #1 model meanwhile

**Block 6 (18:00-19:00): Day 1 Gate [60 min]**
- Gate check: fine-tuned model works, measurable improvement, demo runs, W&B logs clean

**KILL SWITCH 2 (19:00)**: ANY measurable improvement?
- YES → Day 2 is polish + publish
- NO → Pivot A (honest negative result) or Pivot B/C (hyperparameter retry or more steps)

### Day 2: Sunday, March 1, 2026 (09:00-16:00 JST)

**Block 7 (09:00-11:00): Final Eval + Publish [120 min]**
- Full LLM-as-judge on best model (`final120`), freeze metrics
- Run `scripts/hf_publish.py` — publish to HuggingFace
- Log final artifacts to W&B

**Block 8 (11:00-13:00): Demo Hardening + Rehearsal [120 min]**
- Polish Marimo demo, 3 consecutive runs, record backup video

**Block 9 (13:00-14:30): Buffer + Bonus [90 min]**
- Bug fixes, prepare display materials
- *(bonus)* W&B Weave traces, Report, mini challenge
- **14:30**: Submission freeze

**Block 10 (14:30-15:30): Final Prep [60 min]**
- Final dry run, pitch talking points
- **15:30**: Hands off. **16:00**: Judging starts.

## Fallback Strategies

**Pivot A — Honest Negative Result**: Document WHY fine-tuning didn't help. Show analysis. Judges respect honest technical work.

**Pivot B — Hyperparameter Retry**: Keep same base model and adjust `training_steps` / learning rate for one backup run.

**Pivot C — More Training Steps**: Launch longer job overnight if API allows.

## Acceptance Criteria (Must-Have)

1. Fine-tuned model improves over base: `constraint_pass_rate` >= +5% or `avg_score` >= +0.5
2. W&B Models: training/eval metrics logged, artifacts logged
3. HF publication: data, eval results, model card with fine-tuned model ID
4. Live demo: Marimo app with base vs fine-tuned side-by-side + judge scores
5. Demo reliability: 3 consecutive runs without failure (live or cached mode)

## Source References

- Mistral fine-tuning docs: <https://docs.mistral.ai/capabilities/finetuning/>
- W&B hackathon page: <https://www.notion.so/wandbai/W-B-at-Mistral-Worldwide-Hackathon-2026-311e2f5c7ef3806c8b01fc18b21757c4>
- Dataset: <https://huggingface.co/datasets/Sohy/RecipePair>
