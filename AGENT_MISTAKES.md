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
