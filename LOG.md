# LOG

for tracking changes and updates in the project.

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
