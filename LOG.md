# LOG

for tracking changes and updates in the project.

## 2026-03-01

### Policy Change

- Dropped adaptive second-candidate policy in favor of **single-candidate drop-on-fail**.
- Reason: if candidate 1 fails, generating a candidate 2 rarely recovers — the model tends to repeat the same failure pattern on the same recipe + constraint pair. Simpler to move to the next source recipe.

### Changes

- `data/prepare.py`:
  - Removed `should_trigger_candidate2` import and all candidate-2 trigger logic.
  - Flattened the `for candidate_num in range(1, 3)` loop to a single unconditional API call.
  - Removed `generation_candidate_num` field from master row schema.
  - Removed `candidate2_count` / `adaptive_rate` from state tracking and generation summary artifact.
- `PLAN.md`:
  - Updated summary, locked decisions, budget estimate, candidate-generation contract, pipeline steps, target counts, Block 2 timeline, and acceptance criteria to reflect single-candidate policy.

### Implications

- Source pool must be large enough that ~40-60% pass rate on candidates still yields `1200` kept pairs.
- Failed recipes simply do not contribute — no extra API spend on retry candidates.

---

## 2026-02-28

### Decision

- Switched official data strategy from RecipePair-based training to **Food.com-first synthetic adaptation generation**.
- Reason: full-corpus RecipePair audit is `NO_GO` for adaptation-quality supervision.

### Evidence

- Full `Sohy/RecipePair` train audit (`64,000` rows) from `data/audit_dataset.py`:
  - kept rows: `32` (`0.05%`)
  - constraint extraction success: `75.08%`
  - mean relevance on kept rows: `0.548` (below gate)
  - final decision: `NO_GO`
- Dominant failures: low relevance, substitution plausibility issues, and constraint violations.

### Docs Updated

- `PLAN.md`
  - Full rewrite to Food.com-first synthetic pipeline.
  - Added synthetic contracts (adaptive second-candidate policy, `1200` final filtered pairs).
  - Added artifact contract and workspace budget routing.
  - Updated timeline gates to require synthetic quality pass before fine-tune.
  - Kept eval structure: `quick50 + final150 + hard30`.
- `CONSIDERING.md`
  - Closed decision: Food.com + synthetic + strict audit.
  - Added concise "why not alternatives now" section.
  - Added execution-ready next actions.

### Operational Constraints

- Separate workspaces remain mandatory:
  - Workspace A: fine-tuning + eval + demo inference
  - Workspace B: synthetic generation spend
- If Food.com ingest is blocked, execution pauses by policy (no automatic fallback in active plan).
- One-workspace overspend risk is explicitly called out and mitigated via workspace split.

### Next Actions

1. Ingest and curate Food.com source pool.
2. Generate about `1200-2400` synthetic candidates (adaptive second-candidate policy).
3. Audit/filter to keep `1200` final pairs.
4. Fine-tune, evaluate, and demo using the updated plan.
