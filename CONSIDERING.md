# Considering: Dataset Strategy Decision Closure

## Context

Our objective is not recipe retrieval by tags. We need supervised behavior for:

- dietary-compliant adaptation of a specific dish
- plausible substitutions
- flavor/dish identity preservation

## Rejected Baseline: RecipePair Family

`Sohy/RecipePair` and joined `lishuyang/recipepairs` were evaluated as baseline evidence and rejected for active training use.

### Full-corpus evidence (`Sohy/RecipePair`, train=64,000)

Artifacts:

- `artifacts/full_audit_64k/dataset_audit_summary.json`
- `artifacts/full_audit_64k/dataset_audit_rows.csv`

Key metrics:

- kept rows after gates: `32/64000` (`0.05%`)
- constraint extraction success: `75.08%`
- mean relevance on kept rows: `0.548` (below gate)
- decision: `NO_GO`

Dominant drop reasons:

- `low_relevance`: `63,937`
- `low_substitution_plausibility`: `36,982`
- `constraint_violation`: `29,680`
- `parse_or_constraint_missing`: `15,952`

### Joined-sample evidence (`lishuyang/recipepairs`)

- direct loader path is unreliable in this environment; parquet join is required
- sampled joined audit also returned `NO_GO`
- practical outcome: better metadata alignment signal does not translate to adaptation-quality supervision under our gates

## Decision

**Decided:** use **Food.com source pool + synthetic adaptations + strict audit** as the official data strategy.

### Chosen pipeline

1. ingest and curate Food.com recipes
2. assign dietary targets to violating recipes
3. generate candidate 1 per recipe via `mistral-large-latest`
4. generate candidate 2 only when candidate 1 fails quality triggers; score and keep best candidate deterministically
5. retain `1200` filtered final pairs
6. fine-tune `mistral-small-latest`

## Why Not Alternatives Now

1. `lishuyang/recipepairs`: failed joined-sample audit for adaptation supervision despite high name-overlap metadata.
2. `datahiveai/recipes-with-nutrition`: valid candidate source pool, but not selected as active primary path in this pass.
3. `RecipeNLG` in current env: dataset-script/tooling friction for this timeline.
4. substitution-only resources (e.g., MISKG) are useful as priors/validators, not standalone adaptation supervision.

## Operational Constraints

- Two separate Mistral workspaces are used:
  - Workspace A: fine-tuning + eval + demo inference
  - Workspace B: synthetic generation spend
- Fallback policy for this plan pass: if Food.com ingest is blocked, **pause** and re-evaluate (no automatic source switch).

## Execution-Ready Next Actions

1. Ingest Food.com and build curated source pool.
2. Generate about `1200-2400` synthetic candidates (adaptive second-candidate policy).
3. Audit/filter and keep `1200` final pairs.
4. Run fine-tuning and evaluate with `quick50 + final150 + hard30`.

## TODOs: Eval Input Handoff

1. In dataset prep/export, generate and store eval-ready JSONL splits:
`data/quick50.jsonl`, `data/final150.jsonl`, `eval/hard_cases.jsonl`.
2. Treat these files as required inputs to the eval pipeline (`eval/baseline.py` and `eval/evaluate.py`); eval scripts do not create splits.
3. Add a handoff check in dataset prep completion criteria: do not mark dataset prep complete until all three JSONL files exist and are readable.

## Open: Constraints Coverage Validation (Block 1 Hard Gate)

**Status:** must decide during Block 1 after Food.com ingest.

`eval/constraints.json` (v2, 607 terms, 10 categories) is a best-effort starting point. Coverage has NOT been validated against real Food.com ingredient vocabulary.

**Required action in Block 1:**

1. After Food.com ingest, extract all unique ingredient strings from the curated source pool.
2. For each supported dietary constraint, cross-reference source ingredients against the banned list.
3. Flag ingredients that a human would consider violations but are missing from the list (coverage gaps).
4. Flag banned terms that would produce false positives against real ingredient strings (e.g., "cream" matching "cream of tartar").
5. Extend `eval/constraints.json` with discovered gaps before starting synthetic generation.

**Why this matters:** if the banned list is too narrow, `constraint_pass` will report false passes — adapted recipes that still contain violating ingredients will enter the training set. The model learns to produce non-compliant output. This is the hardest quality failure to catch downstream because the audit says "pass" but the recipe is wrong.

**Decision criteria:** coverage check passes when a manual review of 50 random flagged-vs-unflagged ingredients shows <= 2 false negatives (missed violations) and <= 2 false positives (wrongly flagged compliant ingredients).

## References

- Food.com Kaggle dataset: <https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews/data>
- Food.com paper (EMNLP 2019): <https://aclanthology.org/D19-1613/>
- RecipePair baseline evidence: <https://huggingface.co/datasets/Sohy/RecipePair>
- lishuyang RecipePairs: <https://huggingface.co/datasets/lishuyang/recipepairs>
