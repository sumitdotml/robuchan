# 2-Day Execution Plan: Food.com-First Synthetic Adaptation Fine-Tuning (Mistral API)

## Summary

- Primary strategy: use **Food.com recipes as source pool**, generate synthetic dietary adaptations with `mistral-large-latest`, and fine-tune `mistral-small-latest` on audited outputs.
- Target dataset for training: **1200 final filtered pairs**. Single candidate per recipe; failed candidates are dropped.
- Prompt policy: keep semantic payload constant while varying user phrasing/templates to avoid rigid-format overfitting.
- Evaluation structure remains: **quick50 + final150 + hard30**.
- Work is split across two separate Mistral workspaces due billing/access constraints:
  - **Workspace A**: fine-tuning, evaluation inference, demo inference
  - **Workspace B**: synthetic generation spend
- If Food.com ingest is blocked, **pause execution** (no automatic fallback).

## Architecture

```text
Local Machine                       Mistral API                          W&B
  |                                     |                                |
  |--- ingest Food.com source ----------|                                |
  |--- generate adaptive candidates ---->| (mistral-large-latest)         |
  |<-- synthetic candidates ------------|                                |
  |--- deterministic audit/filter ------|                                |
  |--- upload train/valid JSONL ------->|                                |
  |--- create FT job ------------------>| (mistral-small-latest) -------->| training metrics
  |<-- poll status ---------------------|                                |
  |--- eval + demo inference ---------->|                                |
```

## Locked Decisions

1. Primary data strategy: **Food.com + synthetic generation**.
2. Generation policy: **single candidate per recipe**: generate one candidate; drop the recipe if it fails quality triggers.
3. Synthetic target: **1200 final filtered pairs**.
4. Fallback policy: **pause if Food.com ingest fails**.
5. Command style: `uv`-based workflow in docs and scripts.
6. `kb/swaps_v0.json` is required (minimum 20-30 high-confidence swap rules).

## Collaboration Model (Separate Workspaces)

- **Workspace A (training/inference)**:
  - fine-tune job(s)
  - baseline/final eval inference
  - demo-time inference
- **Workspace B (data generation)**:
  - synthetic adaptation generation via `mistral-large-latest`
- **Shared visibility**: log all runs/artifacts to one shared W&B project.
- **Rule**: keep each run fully contained in one workspace; share only artifacts/IDs through repo + W&B.

## Budget Guardrails

- Available credits: `$15` per workspace (not pooled).
- Synthetic generation estimate (~1200-2000 generations): **~$3.30-$11.00** total (based on updated token assumptions: ~330 input, ~700 output for richer prompts/responses).
- Budget routing:
  - Workspace B should carry synthetic generation spend.
  - Workspace A should reserve budget for fine-tune + eval + demo.
- Risk note: running both synthetic generation and full training/eval in one workspace can exceed practical budget headroom.

## Creative Adaptation Objective

- Build a model that transforms a specific dish under a dietary constraint while preserving flavor intent and dish identity.
- Non-goal: tag-only recipe retrieval.

### Response Contract (training/eval/demo)

1. `Substitution Plan` — one row per detected violation: `original -> replacement (rationale)`. No missing violations.
2. `Adapted Ingredients` — full cookable ingredient list with quantities/units. No `...` or "same as original" placeholders. Standard culinary unit abbreviations (`g`, `kg`, `ml`, `l`, `tsp`, `tbsp`, `min`) are allowed.
3. `Adapted Steps` — full numbered steps reflecting replacements. No source-step leftovers mentioning removed ingredients.
4. `Flavor Preservation Notes` — at least 3 concrete mechanism notes (umami/heat/aroma/texture/fat/acid balance).
5. `Constraint Check` — explicit checklist: each source violation resolved + derivative check result.

## Data Contracts and Artifacts

### Training pair schema (synthetic-first)

Each kept example must include:

- `source_recipe_id`
- `source_recipe`:
  - `title`
  - `ingredients`
  - `steps`
- `target_restrictions`
- `detected_violations`
- `replacement_pairs` (`from`, `to`, `reason`)
- `messages` (Mistral chat format)
- `template_id` (`A`, `B`, or `C`)
- `audit_scores`:
  - `constraint_pass`
  - `relevance_score`
  - `nontriviality_score`
  - `semantic_completeness_pass`
- `kept_for_training`
- `kb_version` (must reference `swaps_v0`)

### Candidate-generation contract

- Generate one candidate per source recipe.
- If the candidate fails any quality trigger, drop the recipe and move to the next source.
- Keep one passing candidate per source/constraint pair.

### Required artifacts

- `artifacts/source_pool_summary.json`
- `artifacts/synthetic_generation_summary.json`
- `artifacts/dataset_audit_summary.json`
- `data/train_filtered.jsonl`
- `data/valid_filtered.jsonl`

## Dataset Strategy (Active)

### Source pool: Food.com recipes/reviews

Selection rules for candidate source recipes:

1. Parseable ingredients and steps.
2. Minimum completeness (non-empty title, ingredient list, instructions).
3. Prefer higher-quality recipes when rating/review metadata is available.
4. Select recipes that violate at least one supported target dietary constraint.

### Synthetic generation pipeline

1. Ingest and normalize Food.com source recipes.
2. Assign target dietary constraint per selected recipe.
3. Generate candidate using `mistral-large-latest`.
4. Score candidate with deterministic audit rules.
5. Keep the candidate if it passes; otherwise drop the recipe.
6. Continue until **1200 filtered pairs** are collected.

Target counts:

- Approximate generated candidates: **1200-2000**
- Final kept training pairs: **1200**

### Prompt semantics + template variation policy (hard requirement)

1. Build one canonical semantic payload per row:
   - recipe title, ingredients (with quantities), steps
   - target restrictions
   - optional: cuisine tag, must-keep flavor notes, pantry/time/equipment constraints
2. Render `user` message with one of 3 templates while preserving the same semantics.
3. Use deterministic template assignment from `hash(source_recipe_id + primary_restriction) % 100`:
   - `0-49`: template A (labeled block)
   - `50-79`: template B (natural request)
   - `80-99`: template C (goal-oriented)
4. Run semantic completeness check before writing each row (all required payload fields present in rendered user prompt).
5. Store template id in internal metadata; do not include QC metadata in exported `messages`.

#### Template A — Labeled Block (50%)

Structured, labeled fields. Most explicit format.

```
Recipe: {title}
Cuisine: {cuisine}
Ingredients: {ingredients_comma_separated}
Steps: {steps_numbered_inline}
Restrictions: {restrictions}
Must Keep Flavor Notes: {flavor_notes}
```

Example:
```
Recipe: Mapo Tofu
Cuisine: Sichuan Chinese
Ingredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil
Steps: 1) Brown pork in oil until crispy. 2) Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds. 3) Add tofu cubes and 1 cup water; simmer 8 minutes. 4) Mix cornstarch slurry and stir in to thicken. 5) Garnish with sliced scallions.
Restrictions: vegetarian, shellfish-free
Must Keep Flavor Notes: mala heat, savory umami, silky sauce
```

#### Template B — Natural Request (30%)

Conversational prose. Same information, no rigid labels.

```
I have a recipe for {title} ({cuisine}) that I need to make {restrictions}-friendly.

The ingredients are: {ingredients_comma_separated}.

Here's how it's made: {steps_prose}

Please adapt it while keeping the dish recognizable.
```

Example:
```
I have a recipe for Mapo Tofu (Sichuan Chinese) that I need to make vegetarian and shellfish-free.

The ingredients are: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil.

Here's how it's made: Brown the pork in oil until crispy, then add minced garlic, ginger, and doubanjiang and stir-fry for 30 seconds. Add tofu cubes with a cup of water and simmer for 8 minutes. Thicken with a cornstarch slurry and garnish with sliced scallions.

Please adapt it while keeping the dish recognizable.
```

#### Template C — Goal-Oriented (20%)

Leads with the dietary goal. Includes flavor preservation notes and optional practical constraints.

```
Goal: make {title} fully {restrictions}-compliant.

Source ingredients:
{ingredients_newline_list}

Source steps:
{steps_numbered_list}

Preserve these flavors: {flavor_notes}.
{optional_constraints}
```

Example:
```
Goal: make Mapo Tofu fully vegetarian and shellfish-free compliant.

Source ingredients:
- 400g firm tofu
- 200g ground pork
- 2 tbsp doubanjiang
- 1 tbsp oyster sauce
- 3 cloves garlic
- 1 inch ginger
- 2 scallions
- 1 tbsp cornstarch
- 2 tbsp neutral oil

Source steps:
1. Brown pork in oil until crispy.
2. Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds.
3. Add tofu cubes and 1 cup water; simmer 8 minutes.
4. Mix cornstarch slurry and stir in to thicken.
5. Garnish with sliced scallions.

Preserve these flavors: mala heat, savory umami, silky sauce.
Weeknight-friendly, under 30 minutes, no specialty equipment.
```

#### Template format variation summary

| Dimension | Template A | Template B | Template C |
|---|---|---|---|
| Structure | Rigid labeled fields | Prose paragraphs | Goal-first + lists |
| Ingredient format | Comma-separated inline | Comma-separated inline | Newline bulleted list |
| Step format | Numbered inline `1) ...` | Narrative prose | Numbered list `1. ...` |
| Tone | Neutral/structured | Conversational | Directive |
| Cuisine tag | Always present | Parenthetical | Absent |
| Flavor notes | Labeled field | Absent (implied) | Explicit "Preserve these flavors" |
| Optional constraints | Absent | Absent | Present when available |

### Rich `messages` role content contract (required)

1. `system` must include:
   - priority order: dietary compliance first, dish identity/flavor second, usability/clarity third
   - strict rule: do not include forbidden ingredients or derivatives (including stocks, sauces, pastes, and broths)
   - hard fallback rule: if no exact compliant substitute exists, acknowledge the gap, choose the closest viable option, and state the trade-off
   - required output sections: `Substitution Plan`, `Adapted Ingredients`, `Adapted Steps`, `Flavor Preservation Notes`, `Constraint Check`
2. `user` must include:
   - recipe title, ingredients, and steps
   - target restrictions/allergens
   - optional but recommended context: cuisine tag, must-keep flavor notes, pantry/time/equipment limits
3. `assistant` must include:
   - `Substitution Plan`: one row per detected violation (`from -> to -> why`). Every violation in the source must be mapped. No missing entries.
   - `Adapted Ingredients`: full cookable ingredient list with quantities and units. No `...` and no "same as original." Standard culinary unit abbreviations (`g`, `kg`, `ml`, `l`, `tsp`, `tbsp`, `min`) are allowed.
   - `Adapted Steps`: full numbered steps reflecting all replacements. No source-step leftovers that reference removed ingredients.
   - `Flavor Preservation Notes`: at least 3 concrete mechanism notes covering distinct dimensions (umami, heat, aroma, texture, fat, acid balance).
   - `Constraint Check`: explicit checklist of every resolved violation + derivative check result (stocks/sauces/pastes/broths confirmed absent).
4. Richness policy (depth tiers):
   - **concise** (`10%`): all sections fully complete, shorter rationale per substitution, minimum 3 flavor notes. Same structural requirements — only prose density shrinks.
   - **standard** (`70%`): full default detail level.
   - **rich** (`20%`): standard + deeper flavor/technique explanation + optional alternative swap suggestion per substitution.
   - All tiers must pass the same structural validation checks.
5. Never include QC metadata in `messages` (`audit_scores`, `template_id`, `kb_*`, `replacement_pairs` raw objects).

### Deterministic assistant completeness validation (reject if any fail)

These checks run on every generated assistant response before it enters `internal_master`:

1. Reject if `...` appears anywhere in assistant content.
2. Reject if adapted ingredient list is not parseable or missing quantities.
3. Reject if any entry in `detected_violations` has no corresponding row in `Substitution Plan`.
4. Reject if any removed/banned ingredient still appears in `Adapted Ingredients` or `Adapted Steps`.

### Deterministic scoring definitions (no extra judge API cost)

1. `constraint_pass` (`0/1`):
   - `1` only if all restricted ingredients/allergens in `detected_violations` are removed or replaced and no banned terms remain in adapted ingredients/steps.
2. `relevance_score` (`0-1`):
   - compare normalized ingredient names from source vs adapted, excluding restricted ingredients.
   - normalization pipeline: lowercase -> strip quantities/units -> remove parentheticals/prep adjectives -> singularize -> alias-map synonyms.
   - formula: `retained_nonrestricted_source_ingredients / total_nonrestricted_source_ingredients`.
3. `nontriviality_score` (`0-1`):
   - formula: `0.8 * (replaced_violations / max(1, total_violations)) + 0.2 * step_changed_flag`.
4. `semantic_completeness_pass` (`0/1`):
   - `1` only if user prompt contains recipe title, ingredients, steps, and restrictions fields (any of the approved templates).

### Quality gate before fine-tuning

Do not start fine-tuning until all of the following pass on generated data:

1. Constraint pass rate on kept set `>= 98%`
2. Semantic completeness check pass rate `= 100%` on kept set
3. Assistant completeness validation pass rate `= 100%` on kept set (all 4 rejection checks)
4. Mean `relevance_score` on kept set `>= 0.55`
5. Nontrivial adaptation pass rate (`nontriviality_score >= 0.5`) `>= 90%` on kept set
6. Template distribution on kept set is near target split (A/B/C = 50/30/20 with `+/-10` percentage points per bucket)
7. Manual 10-row spot-check pass `>= 80%` before launching fine-tuning

## JSONL Format (Mistral API)

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a culinary adaptation assistant. Priority: (1) strict dietary compliance, (2) preserve dish identity and flavor profile, (3) keep instructions practical and cookable. Never include forbidden ingredients or their derivatives (stocks, sauces, pastes, broths). If no exact compliant substitute exists, acknowledge the gap, choose the closest viable option, and state the trade-off. Output sections exactly: Substitution Plan, Adapted Ingredients, Adapted Steps, Flavor Preservation Notes, Constraint Check."
    },
    {
      "role": "user",
      "content": "Recipe: Mapo Tofu\nCuisine: Sichuan Chinese\nIngredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, 1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, 1 tbsp cornstarch, 2 tbsp neutral oil\nSteps: 1) Brown pork in oil until crispy. 2) Add minced garlic, ginger, and doubanjiang; stir-fry 30 seconds. 3) Add tofu cubes and 1 cup water; simmer 8 minutes. 4) Mix cornstarch slurry and stir in to thicken. 5) Garnish with sliced scallions.\nRestrictions: vegetarian, shellfish-free\nMust Keep Flavor Notes: mala heat, savory umami, silky sauce"
    },
    {
      "role": "assistant",
      "content": "Substitution Plan:\n- ground pork -> 150g finely chopped shiitake mushrooms + 50g crushed toasted walnuts (shiitake provides meaty chew and glutamate-driven umami; walnuts add fat richness and crumble texture similar to browned pork)\n- oyster sauce -> 1 tbsp mushroom soy sauce + 0.5 tsp sugar (mushroom soy supplies dark color and fermented depth; sugar compensates for the mild sweetness oyster sauce contributes)\n\nAdapted Ingredients:\n- 400g firm tofu, cut into 2cm cubes\n- 150g shiitake mushrooms, stems removed, finely chopped\n- 50g walnuts, toasted and roughly crushed\n- 2 tbsp doubanjiang\n- 1 tbsp mushroom soy sauce\n- 0.5 tsp sugar\n- 3 cloves garlic, minced\n- 1 inch ginger, minced\n- 2 scallions, sliced (white and green parts separated)\n- 1 tbsp cornstarch mixed with 2 tbsp water\n- 2 tbsp neutral oil\n\nAdapted Steps:\n1) Heat oil in a wok over high heat. Add chopped shiitake and crushed walnuts; stir-fry 3-4 minutes until mushrooms release moisture and edges brown.\n2) Add minced garlic, ginger, and scallion whites. Stir-fry 30 seconds until fragrant.\n3) Add doubanjiang and stir-fry 20 seconds to bloom in oil.\n4) Add mushroom soy sauce and sugar; toss to combine.\n5) Add tofu cubes gently and 1 cup water. Simmer 8 minutes without stirring to avoid breaking tofu.\n6) Drizzle cornstarch slurry around edges; gently fold until sauce thickens and coats tofu.\n7) Garnish with scallion greens.\n\nFlavor Preservation Notes:\n- Umami: shiitake glutamates + mushroom soy fermentation replace pork and oyster sauce umami sources. Doubanjiang (fermented bean paste) remains the primary flavor driver.\n- Heat: mala profile is fully intact — doubanjiang provides the la (numbing heat). Add Sichuan peppercorn if source recipe included it.\n- Texture: walnut crumble mimics the crispy rendered pork bits; shiitake provides chew. The sauce remains silky via the same cornstarch slurry technique.\n\nConstraint Check:\n- ground pork (meat): removed, replaced with shiitake + walnut\n- oyster sauce (shellfish-derived): removed, replaced with mushroom soy sauce + sugar\n- Derivative check: no meat stocks, fish sauces, or shellfish-derived pastes remain in adapted recipe"
    }
  ]
}
```

One JSON object per line with a `messages` array.
Only export `messages` from kept rows; internal fields (`audit_scores`, `replacement_pairs`, `template_id`, `kb_*`) stay in `internal_master`.

## Training Workflow (Mistral API)

```python
import os
from mistralai import Mistral

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

train_file = client.files.upload(
    file={"file_name": "train_filtered.jsonl", "content": open("data/train_filtered.jsonl", "rb")}
)
val_file = client.files.upload(
    file={"file_name": "valid_filtered.jsonl", "content": open("data/valid_filtered.jsonl", "rb")}
)

job = client.fine_tuning.jobs.create(
    model="mistral-small-latest",
    training_files=[{"file_id": train_file.id, "weight": 1}],
    validation_files=[val_file.id],
    hyperparameters={"training_steps": 100, "learning_rate": 1e-4},
    auto_start=False,
    integrations=[{"project": "recipe-remix", "api_key": os.environ["WANDB_API_KEY"]}],
    suffix="recipe-remix-foodcom-synth",
)

client.fine_tuning.jobs.start(job_id=job.id)
status = client.fine_tuning.jobs.get(job_id=job.id)
```

## Evaluation: Deterministic + LLM-as-Judge

- Deterministic compliance uses `eval/constraints.json`.
- LLM-as-judge (Mistral Large) rates: compliance, flavor fidelity, dish identity preservation, explanation quality.

### Evaluation stages

1. **Quick gate**: 50 held-out examples (`quick50`)
2. **Final freeze**: 150 held-out examples (`final150`)
3. **Hard-case A/B**: 30 curated cases (`hard30`)

Primary headline metrics:

- `constraint_pass_rate` delta (base vs fine-tuned)
- `avg_judge_score` delta
- `hard_case_win_rate`

## Demo (Marimo)

Run with:

```bash
uv run marimo run demo/demo.py
```

Demo must include:

1. Free-form dish input
2. Dietary requirement input
3. Optional must-keep flavor notes
4. Base vs fine-tuned side-by-side outputs
5. Judge score comparison
6. Compliance check with violation highlights

Reliability rule:

- Cache at least 5 representative examples with precomputed judge/compliance outputs.
- If live API is unstable, switch to cached mode.

## File Structure

| File | Purpose |
|---|---|
| `data/prepare.py` | Food.com ingest, source-pool curation, synthetic candidate generation hooks |
| `data/audit_dataset.py` | Deterministic scoring and keep/drop decisions |
| `train/finetune.py` | Mistral fine-tuning orchestration |
| `eval/baseline.py` | Base model eval on quick/final/hard splits |
| `eval/evaluate.py` | Fine-tuned model eval on quick/final/hard splits |
| `eval/hard_cases.jsonl` | Curated hard adaptation set |
| `eval/constraints.json` | Constraint banned-term rules |
| `kb/swaps_v0.json` | Required substitution knowledge base (20-30+ curated swap rules) |
| `scripts/log_artifacts.py` | W&B artifact/metrics logging |
| `scripts/hf_publish.py` | HF publication for dataset/results/model card |

## 2-Day Timeline

### Day 1: Saturday, February 28, 2026 (10:00-19:00 JST)

**Block 1 (10:00-12:00): Env + Food.com Ingest + Source Curation [120 min]**

- Verify env keys and `uv` tooling.
- Run Food.com ingest and source-pool selection.
- Produce `artifacts/source_pool_summary.json`.
- Run constraints coverage check: extract unique ingredients from source pool, cross-reference against `eval/constraints.json`, extend banned lists with discovered gaps. Must pass before Block 2.
- Exit gate: curated source pool exists, parse checks pass, and constraints coverage validated.

**Block 2 (12:00-14:00): Synthetic Generation + Audit Loop [120 min]**

- Generate one candidate per source recipe with `mistral-large-latest` (Workspace B).
- Drop recipe if candidate fails quality checks; move to next source.
- Run 4 deterministic assistant completeness checks on each candidate before it enters `internal_master` (reject `...`, reject unparseable ingredients, reject unmapped violations, reject banned-term leakage).
- Audit and retain one best passing candidate per source.
- Continue until `1200` filtered pairs OR stop condition.
- Produce `artifacts/synthetic_generation_summary.json` and `artifacts/dataset_audit_summary.json`.
- **Hard gate**: do not start fine-tuning until 1200-pair and quality-gate criteria are met.

**Block 3 (14:00-15:00): Upload + Launch Fine-Tuning [60 min]**

- Upload `train_filtered.jsonl` / `valid_filtered.jsonl`.
- Launch fine-tune in Workspace A.
- Confirm RUNNING status + W&B metrics.

**Block 4 (15:00-16:00): Baseline + Quick Eval [60 min]**

- Run baseline on `quick50`.
- Run fine-tuned quick eval when model is ready.
- Run `hard30` pairwise quick comparison.

**KILL SWITCH 1 (16:00)**

Proceed to demo build only if one holds:

- `constraint_pass_rate` improvement `>= +5%`, or
- `avg_judge_score` improvement `>= +0.5`, or
- `hard_case_win_rate >= 60%`

If not met: run one contingency tuning iteration within remaining budget.

### Day 2: Sunday, March 1, 2026 (09:00-16:00 JST)

**Block 5 (09:00-11:00): Final Eval Freeze [120 min]**

- Execute `final150` and `hard30` on best model.
- Run manual 30-row adaptation quality spot-check (`>= 85%`) on kept training set sample.
- Freeze metrics and artifacts.

**Block 6 (11:00-13:00): Demo Hardening [120 min]**

- Polish demo flow and fallback mode.
- Rehearse 3 full runs.

**Block 7 (13:00-14:30): Publish + Submission Prep [90 min]**

- Publish dataset summary/results/model card.
- Final W&B artifact logging.

**Block 8 (14:30-15:30): Final Dry Run [60 min]**

- Final script/pitch rehearsal.

## Team Execution Split (Up to Pre-Demo Gate)

- **Member A (Model/Infra)**:
  - Food.com ingest and source curation
  - fine-tune orchestration
  - model ID handoffs
- **Member B (Data/Eval)**:
  - synthetic generation monitoring
  - audit reporting
  - baseline/final evaluation and hard-case scoring

Required handoff artifacts remain in `docs/handoffs/H0` to `H4` with timestamps and owners.

## Fallback and Stop Policy

1. If Food.com ingest is blocked (access/tooling/legal), **pause execution** and re-evaluate strategy.
2. Do not silently switch source dataset in the active plan.
3. If quality gate fails, prioritize fixing generation/audit before spending fine-tune credits.

## Acceptance Criteria (Must-Have)

1. Synthetic dataset target met: `1200` filtered pairs (single-candidate policy, drop-on-fail).
2. Synthetic quality gates pass:
  - `constraint_pass_rate_on_kept >= 98%`
  - `semantic_completeness_pass_rate_on_kept = 100%`
  - `assistant_completeness_validation_pass_rate_on_kept = 100%`
  - `mean_relevance_score_on_kept >= 0.55`
  - nontrivial adaptation pass rate (`nontriviality_score >= 0.5`) `>= 90%`
  - template mix near `50/30/20` (`+/-10` points per bucket)
  - manual 10-row pre-FT spot-check pass `>= 80%`
  - manual 30-row final-freeze adaptation quality pass `>= 85%`

3. Fine-tuned model improves over base (`+5%` pass rate or `+0.5` judge score or `hard_case_win_rate >= 60%`).
4. W&B metrics and artifacts are complete.
5. Demo passes 3 consecutive runs (live or cached mode).

## Source References

- Mistral fine-tuning docs: <https://docs.mistral.ai/capabilities/finetuning/>
- W&B hackathon page: <https://www.notion.so/wandbai/W-B-at-Mistral-Worldwide-Hackathon-2026-311e2f5c7ef3806c8b01fc18b21757c4>
- Food.com Kaggle dataset: <https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews/data>
- Food.com paper (EMNLP 2019): <https://aclanthology.org/D19-1613/>
- Rejected baseline evidence (RecipePair): <https://huggingface.co/datasets/Sohy/RecipePair>
