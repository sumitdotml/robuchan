# AGENT_MISTAKES

Persistent repository memory for recurring agent/model mistakes.

Initialized on 2026-02-17.

## Usage Rules

- Read this file before any repository edit task.
- Record every detected mistake occurrence.
- Deduplicate by normalized `pattern` + `scope_tags` + `prevention_rule`.
- For repeated patterns, update existing entry fields instead of creating duplicates.

## Required Entry Fields

Every entry must include:

- `id`
- `status` (`active` or `resolved`)
- `severity` (`low`, `medium`, or `high`)
- `scope_tags` (list)
- `pattern`
- `prevention_rule`
- `validation_check`
- `first_seen` (YYYY-MM-DD)
- `last_seen` (YYYY-MM-DD)
- `occurrence_count` (integer >= 1)
- `evidence` (one or more file:line and/or commit refs)

## Entry Template

Use this exact shape for new entries.

```md
### MISTAKE-YYYYMMDD-001
- id: MISTAKE-YYYYMMDD-001
- status: active
- severity: medium
- scope_tags: [code, docs, tests, config, infra, planning]
- pattern: <normalized mistake pattern>
- prevention_rule: <specific action that prevents recurrence>
- validation_check: <deterministic pass/fail check>
- first_seen: YYYY-MM-DD
- last_seen: YYYY-MM-DD
- occurrence_count: 1
- evidence:
  - file:relative/path:line
  - commit:<hash>
```

## Entries

### MISTAKE-YYYYMMDD-001
- id:
- status: active
- severity:
- scope_tags: []
- pattern:
- prevention_rule:
- validation_check:
- first_seen:
- last_seen:
- occurrence_count:
- evidence:
  - file:
  - commit:

### MISTAKE-20260228-001
- id: MISTAKE-20260228-001
- status: active
- severity: medium
- scope_tags: [planning, docs]
- pattern: inconsistent numeric gates or step numbering across plan sections after partial edits
- prevention_rule: run a post-edit consistency pass across all thresholds, sample sizes, and pivot labels in dataset strategy, evaluation, timeline, and acceptance criteria before finalizing
- validation_check: confirm quick/final sample labels and values, Pivot B/C wording, and numbered list order are identical and sequential across sections using a final line-by-line review
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 2
- evidence:
  - file:PLAN.md:75
  - file:PLAN.md:239
  - file:PLAN.md:197

### MISTAKE-20260228-002
- id: MISTAKE-20260228-002
- status: active
- severity: medium
- scope_tags: [planning, docs]
- pattern: stale policy wording left in related docs after switching a core plan contract
- prevention_rule: after policy pivots, run a cross-file grep for old and new policy terms and update all references before finalizing
- validation_check: verify PLAN.md, CONSIDERING.md, and LOG.md consistently reference adaptive candidate policy and 1200 target with no stale fixed-policy wording
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 2
- evidence:
  - file:PLAN.md:32
  - file:CONSIDERING.md:50
  - file:LOG.md:25
  - file:PLAN.md:6
  - file:CONSIDERING.md:52
  - file:LOG.md:46

### MISTAKE-20260228-003
- id: MISTAKE-20260228-003
- status: active
- severity: medium
- scope_tags: [planning, docs]
- pattern: explicit rule text contradicts examples in the same or linked docs
- prevention_rule: after policy edits, run a rule-vs-example alignment pass and either update examples or relax the rule wording before finalizing
- validation_check: verify no hard prohibition in response/export contract is violated by the canonical examples in PLAN.md and DATASET_SCHEMA.md
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:PLAN.md:66
  - file:PLAN.md:226
  - file:DATASET_SCHEMA.md:142
  - file:DATASET_SCHEMA.md:166

### MISTAKE-20260228-004
- id: MISTAKE-20260228-004
- status: active
- severity: medium
- scope_tags: [code, planning]
- pattern: fine-tune orchestration skipped explicit enforcement of plan-level quality gate criteria before starting training
- prevention_rule: before enabling training start paths, enforce dataset quality gate checks from PLAN.md with deterministic pass/fail logic and block start on gate failure
- validation_check: run `uv run python train/finetune.py check-quality-gate` and verify `start-job` exits non-zero when gate artifact is missing or failing
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:train/finetune.py:276
  - file:PLAN.md:310

### MISTAKE-20260228-005
- id: MISTAKE-20260228-005
- status: active
- severity: medium
- scope_tags: [code]
- pattern: local script imported a sibling module name that collides with popular third-party package names
- prevention_rule: avoid ambiguous top-level imports for local scripts; use uniquely named local modules (for example `eval_engine`) for shared logic
- validation_check: run `uv run python eval/baseline.py --help` in a clean venv and verify import resolution does not depend on the absence of third-party packages with colliding names
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:eval/baseline.py:16

### MISTAKE-20260228-006
- id: MISTAKE-20260228-006
- status: active
- severity: medium
- scope_tags: [code, planning]
- pattern: evaluation implementation omitted a headline plan metric requiring pairwise model comparison
- prevention_rule: when implementing evaluation pipelines, map each plan headline metric to a concrete script output before finalizing
- validation_check: verify a comparator script produces `hard_case_win_rate` from baseline and candidate hard-case row outputs
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:PLAN.md:404
  - file:eval/compare_hard_cases.py:1

### MISTAKE-20260228-007
- id: MISTAKE-20260228-007
- status: active
- severity: medium
- scope_tags: [code]
- pattern: mistral sdk chat.complete calls accepted runtime dict messages but internal types were left as generic dicts, causing static type failures
- prevention_rule: when calling mistral chat.complete, thread mistral chatcompletionrequest message typed dicts through function signatures and message builders
- validation_check: run `uv run ty check eval/eval_engine.py eval/evaluate.py eval/baseline.py` and verify no `invalid-argument-type` diagnostics on chat.complete message arguments
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:eval/eval_engine.py:351
  - file:eval/eval_engine.py:410

### MISTAKE-20260228-008
- id: MISTAKE-20260228-008
- status: active
- severity: medium
- scope_tags: [code]
- pattern: iterative patching introduced duplicate helper definitions and temporary function shadowing in the same file
- prevention_rule: after non-trivial patches, run a duplicate-definition scan and ensure each helper has a single canonical implementation before continuing
- validation_check: run `rg \"^def (resolve_wandb_project|maybe_wandb_integrations)\\(\" train/finetune.py -n` and verify each helper appears exactly once
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:train/finetune.py:406

### MISTAKE-20260228-009
- id: MISTAKE-20260228-009
- status: active
- severity: medium
- scope_tags: [code, eval]
- pattern: deterministic banned-term validation scanned full structured output and counted self-reported banned terms in the constraint check section as violations
- prevention_rule: when deterministic checks target recipe content constraints, scope matching to adapted recipe sections and exclude self-report or audit sections from term scans
- validation_check: run deterministic check smoke cases where banned terms appear only in `Constraint Check` and verify pass, then appear in `Adapted Ingredients` and verify fail
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:eval/eval_engine.py:318

### MISTAKE-20260228-014
- id: MISTAKE-20260228-014
- status: active
- severity: medium
- scope_tags: [code]
- pattern: quality-gate field lookup recursively matched nested keys before intended top-level summary keys, causing wrong gate decisions
- prevention_rule: when reading canonical gate summary fields, always prefer top-level keys first and only fall back to recursive lookup when no top-level value exists
- validation_check: run a fixture where top-level and nested keys differ and verify decision/kept_rows resolve from top-level
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:train/finetune.py:226

### MISTAKE-20260228-015
- id: MISTAKE-20260228-015
- status: active
- severity: medium
- scope_tags: [code, eval]
- pattern: hard-case comparator reported headline win-rate metrics on row-id intersections even when baseline and candidate row sets differed
- prevention_rule: suppress or fail headline comparison metrics when row id sets do not match, and report mismatches explicitly
- validation_check: run comparator with mismatched row ids and verify `hard_case_win_rate`/`avg_score_delta` are suppressed
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:eval/compare_hard_cases.py:108

### MISTAKE-20260228-016
- id: MISTAKE-20260228-016
- status: active
- severity: medium
- scope_tags: [code, eval]
- pattern: eval summary averaged judge metrics over only parsed judge rows, silently inflating headline quality when judge outputs were missing
- prevention_rule: expose judge coverage and gate headline averages on complete judge coverage when judge scoring is enabled
- validation_check: run summary with partial judge outputs and verify `judge_missing_rows` is non-zero while headline `avg_judge_score` is null
- first_seen: 2026-02-28
- last_seen: 2026-02-28
- occurrence_count: 1
- evidence:
  - file:eval/eval_engine.py:491
