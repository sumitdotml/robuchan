# GATE AUDIT

## Generation

```sh
uv run python data/audit_dataset.py gate
```

Artifact generated at `artifacts/quality_gate_report.json`. Generate this every time when user mentions this file.

## Objective

The user wants to identify any metrics that miss the mark, and how to improve the metrics. Look at `data/prepare.py` and `data/audit_dataset.py`.

## INTERESTING CASES

### Fix 1 — Template B silently rejected at generation time (`score_semantic_completeness`)

**Metric affected:** `template_b_fraction` (was 0.0, gate [0.20, 0.40])

Template B prompts use the phrasing `"The ingredients are: ..."`. The `has_ingredients` check in `score_semantic_completeness` only matched `ingredients?:` or `source ingredients:` — the word `are` between `ingredients` and `:` broke the regex. Result: every Template B prompt received `semantic_completeness_pass = 0` and was rejected during generation. None of the 137k Template B source pool entries ever made it into `internal_master.jsonl`.

**Fix:** Added `re.search(r"the ingredients are", lower)` as a third alternative in `has_ingredients`.

---

### Fix 2 — Stale `audit_scores` in `run_quality_gate` (`relevance_score`, `nontriviality_score`)

**Metrics affected:** `mean_relevance_score` (was 0.28 → 0.51), `nontrivial_adaptation_pass_rate` (was 0.27 → 0.99)

The gate was reading `relevance_score` and `nontriviality_score` from the stored `audit_scores` field in each row. Those scores were computed inline during generation, before commit `2cbeb23` added markdown-aware parsing (`**bold**` stripping). At generation time, `parse_assistant_response` failed to extract `replacement_pairs` from `**X → Y**` arrow lines, so:

- `nontriviality_score = 0.8 * (0/n) + 0.2 * step_changed = 0.2` for most rows
- `relevance_score = 0.0` for 303/702 rows because adapted ingredient names retained bold markers and couldn't be normalized to match source ingredients

**Fix:** `run_quality_gate` now calls `parse_assistant_response` live per row and recomputes both scores from the current (correct) parser, using the source recipe data stored in each row. Stored `audit_scores` are ignored for these two metrics.

---

### Fix 3 — Check 4 false positives: word-by-word scan across adapted steps (`check_completeness_validation`)

**Metric affected:** `assistant_completeness_validation_pass_rate` (was 0.58 → 0.99)

Check 4 extracted individual words (length > 3) from each replacement pair's `from` field and scanned the full `adapted_ingredients_text + adapted_steps_text` for any match. This produced ~448 false positives per run. Root causes:

- **Common generic words:** "sauce" from "Worcestershire sauce" matched "barbecue sauce"; "light" from "Light corn syrup" matched "organic light-brown sugar".
- **Compound replacements:** "breadcrumbs" from "Breadcrumbs → Panko + crushed walnuts" matched "panko breadcrumbs" in adapted ingredients — a valid replacement, not a violation.
- **Alias normalization collapse:** "button mushrooms" and "cremini mushrooms" both aliased to "mushroom", so replacing one with the other was flagged as unchanged.
- **"No change" pairs:** model explicitly annotated ingredients as "No change", "Retained", "Already compliant", etc., but check 4 still flagged them because the ingredient word appeared in adapted content.
- **Modification pairs:** "Salt → 1 tsp salt (reduce due to...)" and "Tomato sauce → 1 cup tomato sauce (unsweetened)" — the replacement IS the same ingredient modified, not removed.

**Fix (layered):**

1. Replaced word-by-word scan with normalized ingredient equality check — only flags if a normalized adapted ingredient is identical to the normalized `from` ingredient.
2. Normalization uses the full pipeline *without* alias mapping, so different varieties (cremini ≠ button mushroom) are not collapsed.
3. Pairs where `to` matches `_NO_CHANGE_RE` (no change, no substitution, retain, retained, same, reduce, omit, etc.) or is a dash-only placeholder are skipped entirely.
4. Pairs where `norm_removed` is a substring of `norm_to` are skipped — the replacement is a modification of the same ingredient, not a removal.
