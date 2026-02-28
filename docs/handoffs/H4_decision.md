# H4 Kill-Switch Decision (Pre-Block 5A)

- Date (JST):
- Decision window:
- Prepared by:
- Reviewed by:

## Inputs

- Fine-tuned model id:
- Baseline metrics artifact:
- Fine-tuned metrics artifact:
- Hard-case A/B artifact:

## Decision Metrics

- `constraint_pass_rate` delta:
- `avg_judge_score` delta:
- `hard_case_win_rate`:
- Cost consumed so far (workspace A / workspace B):

## Rule Check

Kill Switch 1 condition:
- `constraint_pass_rate` >= +5% OR
- `avg_judge_score` >= +0.5 OR
- `hard_case_win_rate` >= 60%

Result:
- Condition met: `YES` or `NO`
- Decision: `GO_5A` or `RUN_5B`

## Action Plan

- If `GO_5A`: owner + first command
- If `RUN_5B`: owner + first command
- Timestamp (JST):

