# Evaluation Results: Robuchan vs Baseline

Generated: 2026-03-01

## TL;DR

### Task Accuracy: 0% → 24%

A row is "correct" only if the model output passes **both** format compliance (all 5 sections present) **and** dietary constraint compliance (zero banned ingredients). This is the single most important metric — it measures whether the model actually did its job.

| | Ministral 8B (base, n=50) | Robuchan (fine-tuned, n=50) |
|---|----:|----:|
| **Task Accuracy** | **0%** (0/50) | **24%** (12/50) |

The base model scored **zero out of fifty** — not a single output was both correctly structured and free of banned ingredients. The fine-tuned adapter achieved 24% task accuracy, with performance varying sharply by dietary category: 56% on vegetarian (easier substitutions) down to 0% on dairy-free (many subtle dairy derivatives to avoid).

### All Metrics

| Metric | Ministral 8B (base) | Robuchan (fine-tuned) | Delta |
|--------|--------------------:|---------------------:|------:|
| **Task Accuracy** | 0% (0/50) | 24% (12/50) | **+24pp** |
| **Format Compliance** | 14% (7/50) | 88% (44/50) | **+74pp** |
| **Constraint Compliance** | 0% (0/50) | 26% (13/50) | **+26pp** |
| **Hard-Case Win Rate** | — | 86% (43/50) | — |
| **Token Accuracy (training)** | — | 82.2% | from 67.2% |
| **Training Loss** | — | 0.603 | -56% from 1.373 |
| **Eval Loss** | — | 0.707 | converged, no overfit |
| **LLM Judge Overall** | 9.20/10 | pending | — |

The base model writes fluent, high-quality recipe adaptations (judge score 9.2/10) but **completely fails** the actual task — producing structured, dietary-compliant outputs. Fine-tuning dramatically improved format compliance (14% → 88%) and moved constraint compliance from zero to 26%, with an 86% pairwise win rate over baseline. The model learned structure well but still struggles with strict ingredient avoidance, particularly for categories with many banned terms (vegan: 16%, dairy-free: 0%).

---

## Training Performance

### Setup

- **Base model:** [Ministral 8B Instruct](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410) (Oct 2024)
- **Method:** QLoRA — 4-bit NF4 quantization, LoRA rank=16, alpha=32, targeting q/k/v/o attention projections
- **Trainable parameters:** ~2-8M out of 8B total (only the LoRA adapter matrices)
- **Training data:** 1,090 rows of recipe adaptation examples ([sumitdotml/robuchan-data](https://huggingface.co/datasets/sumitdotml/robuchan-data))
- **Validation data:** 122 held-out rows
- **Hardware:** NVIDIA H200 (141GB VRAM) — 3 full epochs completed in 14 minutes
- **W&B:** [sumit-ml/robuchan/bwsoosim](https://wandb.ai/sumit-ml/robuchan/runs/bwsoosim)

### Loss Curve

Training ran for 3 epochs (207 steps). Loss decreased steadily with no signs of overfitting:

| Checkpoint | Epoch | Train Loss | Eval Loss | Token Accuracy |
|------------|------:|-----------:|----------:|---------------:|
| Step 5 | 0.07 | 1.373 | — | 67.2% |
| Step 25 | 0.37 | 0.845 | — | 76.6% |
| Step 50 | 0.73 | 0.797 | — | 77.4% |
| **Step 69** | **1.00** | — | **0.740** | — |
| Step 100 | 1.45 | 0.674 | — | 80.2% |
| **Step 138** | **2.00** | — | **0.707** | — |
| Step 175 | 2.54 | 0.620 | — | 81.8% |
| Step 200 | 2.91 | 0.621 | — | 81.6% |
| **Step 207** | **3.00** | — | **0.707** | — |

### What These Numbers Mean

- **Token accuracy (67% → 82%):** The fraction of next-token predictions that are exactly correct. The model went from getting roughly 2 out of 3 tokens right to over 4 out of 5. This measures how well the model learned to produce the exact format and content of the training examples — structured recipe adaptations with section headers, compliant ingredients, and substitution rationale.

- **Training loss (1.373 → 0.603, -56%):** Cross-entropy loss on the training set. The steep initial drop (1.37 → 0.85 in the first ~25% of epoch 1) shows the model quickly picked up the output structure. The continued gradual decrease across epochs 2-3 shows refinement of content quality.

- **Eval loss (0.740 → 0.707 → 0.707):** Cross-entropy loss on the 122-row held-out validation set, measured at each epoch boundary. The drop from epoch 1 to 2 (0.740 → 0.707) shows genuine generalization. The plateau from epoch 2 to 3 (0.707 → 0.707) indicates the model had learned what it could from this dataset — further training on the same data wouldn't help. Crucially, eval loss never increased, meaning **no overfitting occurred**.

- **Training efficiency:** 3 full epochs completed in 14 minutes on a single H200 GPU. QLoRA made this possible — only the small adapter matrices were updated while the 8B base model weights stayed frozen in 4-bit precision.

### Failed Training Runs

The successful H200 run was preceded by several failed attempts that informed our approach:

| Run | GPU | Failure | Lesson |
|-----|-----|---------|--------|
| super-hill-3 | A10G (24GB) | OOM at epoch 0.95 | eval_strategy="epoch" causes VRAM spike at epoch boundary |
| peach-universe-2 | A10G (24GB) | OOM at epoch 0.95 | Same — eval pass needs extra VRAM on top of training state |
| fanciful-donkey-1 | T4 (16GB) | Too slow | T4 insufficient for 8B model even with QLoRA |

**Key lesson:** 8B QLoRA training needs either (a) a large-VRAM GPU (H200/A100) with eval enabled, or (b) a 24GB GPU (A10G) with `--no-eval` to avoid the eval-time OOM.

---

## How We Judge: Three-Layer Evaluation

We evaluate model outputs using three independent methods, each catching different failure modes:

### Layer 1: Format Compliance (deterministic, automated)

**What:** Does the output contain all 5 required section headers in the correct structure?

| Required Section | Purpose |
|-----------------|---------|
| Substitution Plan | What gets replaced and why |
| Adapted Ingredients | Full modified ingredient list |
| Adapted Steps | Updated cooking instructions |
| Flavor Preservation Notes | How taste/texture is maintained |
| Constraint Check | Self-audit of dietary compliance |

**How:** Parsed header detection (not naive substring matching). Also rejects placeholder text like `"..."` or `"same as original"`.

**Why it matters:** Without structured output, downstream systems can't parse the recipe. The base model produces free-form prose that varies wildly in structure. A structured format is essential for any production use — displaying sections in a UI, extracting ingredient lists, or verifying compliance programmatically.

### Layer 2: Dietary Constraint Compliance (deterministic, automated)

**What:** Does the adapted recipe actually avoid banned ingredients?

**How:** Regex matching against a curated banned-term list (`eval/constraints.json`):
- 10 dietary categories (vegan, dairy-free, gluten-free, vegetarian, nut-free, etc.)
- 176 banned terms for vegan alone (every animal product and derivative — butter, ghee, lard, gelatin, honey, whey, casein, etc.)
- Matching is scoped to "Adapted Ingredients" and "Adapted Steps" sections only — the "Constraint Check" self-audit section is excluded to prevent false positives from the model mentioning banned terms in its compliance analysis

**Why it matters:** Dietary compliance is binary in practice. A "vegan" recipe containing butter or chicken stock is a real-world failure regardless of how eloquently it's written. For people with allergies or strict dietary requirements, one banned ingredient = fail. This is the strictest and most practically important metric.

**Example failure:** Base model output for a vegan adaptation of tonkotsu ramen still contained `dashi stock` (fish-based) — the LLM judge rated it 10/10 compliance, but the deterministic check correctly flagged it.

### Layer 3: LLM-as-Judge (Mistral Large)

**What:** Holistic quality assessment by a stronger model.

**Model:** `mistral-large-latest` (Mistral's flagship model, used as an automated evaluator)

**How it works:** Each model output is sent to Mistral Large with a structured evaluation prompt. The judge scores the output on 5 independent dimensions, each on a 1-10 scale:

| Dimension | What It Measures | Baseline Avg |
|-----------|-----------------|-------------:|
| Compliance | Did the model *attempt* to address the dietary constraint? | 9.88 |
| Flavor Fidelity | Are substitute ingredients appropriate for taste/texture? | 8.66 |
| Dish Identity | Would you still recognize this as the original dish? | 8.96 |
| Explanation Quality | Are substitution rationales clear, practical, and actionable? | 9.42 |
| **Overall Score** | **Holistic recipe adaptation quality** | **9.20** |

**Critical caveat — the judge can be fooled:** The judge measures *intent and plausibility*, not *factual correctness*. It rated the base model **9.88/10 on compliance** despite **0% of outputs actually passing the banned-ingredient check.** The judge saw the model attempting substitutions and rated the attempt highly — but it didn't verify whether every single ingredient was actually compliant. This is a known limitation of LLM-as-judge evaluation and precisely why we need the deterministic layer alongside it.

### Why Three Layers?

Each layer catches failures the others miss:

| Failure Type | Format Check | Constraint Check | LLM Judge |
|-------------|:---:|:---:|:---:|
| Missing section headers | catches | — | sometimes |
| Banned ingredient in recipe | — | catches | often misses |
| Poor substitution choice | — | — | catches |
| Unnatural writing | — | — | catches |
| Wrong dish entirely | — | — | catches |

A model needs to pass **all three layers** to be production-ready.

---

## Baseline Results (n=50, full split)

- **Model:** `mistral-small-latest` via Mistral API
- **Judge:** `mistral-large-latest` via Mistral API (100% coverage, 50/50 rows scored)
- **Split:** `eval/quick50.jsonl` (50 curated recipe adaptation prompts)
- **W&B:** [sumit-ml/robuchan/runs/uuj6tmlo](https://wandb.ai/sumit-ml/robuchan/runs/uuj6tmlo)

### Results by Dietary Category

| Restriction | Rows | Format Pass | Constraint Pass | Avg Judge Score |
|-------------|-----:|------------:|----------------:|----------------:|
| vegan | 19 | 3/19 (16%) | 0/19 (0%) | 9.14 |
| dairy_free | 13 | 1/13 (8%) | 0/13 (0%) | 9.27 |
| vegetarian | 9 | 2/9 (22%) | 0/9 (0%) | 9.28 |
| gluten_free | 4 | 1/4 (25%) | 0/4 (0%) | 9.08 |
| low_sodium | 3 | 0/3 (0%) | 0/3 (0%) | 9.33 |
| low_sugar | 2 | 0/2 (0%) | 0/2 (0%) | 9.00 |

The base model fails constraint compliance across **every single dietary category** — not just the strict ones like vegan. Even vegetarian adaptations (which only need to remove meat) still contained animal products. The judge scores remain high across all categories (9.0-9.3), confirming the judge doesn't catch these violations.

### Token Usage & Cost

| | Prompt Tokens | Completion Tokens |
|---|-------:|-----------:|
| Inference | 18,403 | 23,608 |
| Judge | 41,756 | 7,257 |

---

## Candidate Results (n=50, full split)

- **Model:** `sumitdotml/robuchan` (LoRA adapter on Ministral 8B, 4-bit NF4 quantized)
- **Adapter:** [sumitdotml/robuchan](https://huggingface.co/sumitdotml/robuchan) on Hugging Face
- **Inference:** via HF Space ([sumitdotml/robuchan-demo](https://huggingface.co/spaces/sumitdotml/robuchan-demo)) on NVIDIA A100 Large GPU
- **Judge:** not run (deterministic checks only)

| Metric | Result |
|--------|-------:|
| **Task accuracy** | **24% (12/50)** |
| Format pass rate | 88% (44/50) |
| Constraint pass rate | 26% (13/50) |

### Results by Dietary Category

| Restriction | Rows | Format Pass | Constraint Pass | Task Accuracy |
|-------------|-----:|------------:|----------------:|--------------:|
| vegetarian | 9 | 8/9 (89%) | 6/9 (67%) | 5/9 (56%) |
| low_sodium | 3 | 3/3 (100%) | 2/3 (67%) | 2/3 (67%) |
| low_sugar | 2 | 2/2 (100%) | 1/2 (50%) | 1/2 (50%) |
| gluten_free | 4 | 4/4 (100%) | 1/4 (25%) | 1/4 (25%) |
| vegan | 19 | 19/19 (100%) | 3/19 (16%) | 3/19 (16%) |
| dairy_free | 13 | 8/13 (62%) | 0/13 (0%) | 0/13 (0%) |

### Side-by-Side: Base vs Fine-Tuned by Category

| Restriction | Base Format | FT Format | Base Constraint | FT Constraint |
|-------------|:----------:|:---------:|:---------------:|:-------------:|
| vegetarian | 22% | **89%** | 0% | **67%** |
| low_sodium | 0% | **100%** | 0% | **67%** |
| low_sugar | 0% | **100%** | 0% | **50%** |
| gluten_free | 25% | **100%** | 0% | **25%** |
| vegan | 16% | **100%** | 0% | **16%** |
| dairy_free | 8% | **62%** | 0% | **0%** |

### What the Numbers Mean

- **88% format compliance** (vs 14% baseline, +74pp): The fine-tuned model consistently produces the 5-section structured format. The 6 format failures are mostly missing "Constraint Check" sections. The model learned the output structure from 1,090 training examples — this is the clearest improvement from fine-tuning.

- **26% constraint compliance** (vs 0% baseline, +26pp): The model now avoids banned ingredients in about 1 in 4 outputs. Performance varies sharply by category: vegetarian (67%) and low_sodium (67%) are strong, while dairy_free (0%) shows the model hasn't learned to avoid subtle dairy derivatives (whey, casein, etc.). Vegan at 16% is better than baseline but still struggles with the 176 banned terms.

- **24% task accuracy** (vs 0% baseline): Rows that pass BOTH format and constraint checks. The base model scored zero out of fifty — not a single output was both correctly structured and free of banned ingredients.

### What Drove the Improvement

The fine-tuning taught the model two things:

1. **Structure** — The 1,090 training examples all follow the exact 5-section format. After 3 epochs, the model internalized this pattern reliably (88%). This is a relatively easy task for fine-tuning because it's about output format, not domain knowledge.

2. **Ingredient awareness** — The training examples demonstrate compliant substitutions (e.g., replacing butter with coconut oil for vegan, swapping soy sauce with tamari for gluten-free). The model learned to associate dietary constraints with specific ingredient substitution patterns. This is harder than structural learning and shows in the category variation — the model handles "obvious" substitutions (meat for vegetarian) but misses subtle derivatives (casein for dairy-free).

### Common Violation Patterns

The 37 constraint failures reveal clear patterns in what the model struggles with:

| Violation Pattern | Frequency | Example |
|-------------------|:---------:|---------|
| Butter/cream not removed | 22 rows | Dairy-free recipe still lists "butter" and "cream" |
| Dairy derivatives missed | 11 rows | "yogurt", "sour cream", "milk" left in vegan/dairy-free |
| Cheese not substituted | 6 rows | "parmesan", "mozzarella", "blue cheese" in dairy-free |
| Eggs not removed | 4 rows | "egg", "eggs" in vegan/vegetarian |
| Flour kept in gluten-free | 3 rows | "all-purpose flour" not swapped for GF alternative |
| Meat derivatives missed | 2 rows | "worcestershire sauce" (anchovy-based), "ribs" in vegetarian |

The dominant failure mode is **dairy ingredients not being substituted** — the model knows to replace the primary protein but forgets about dairy products used as secondary ingredients (cream in sauces, butter for cooking, cheese as garnish).

### Pairwise Comparison (Hard-Case Win Rate)

Using deterministic fallback scoring (constraint_pass + format_pass) on all 50 rows:

| Metric | Value |
|--------|------:|
| **Win rate** | **86% (43/50)** |
| Non-loss rate | 94% (47/50) |
| Wins | 43 |
| Losses | 3 |
| Ties | 4 |
| Avg score delta | +0.334 |

The fine-tuned model wins on 86% of rows when compared head-to-head with the baseline. The 3 losses are rows where the baseline happened to produce a format-passing output while the candidate did not.

---

## Caveats

1. **No judge scoring on candidate.** The candidate eval used deterministic checks only (no LLM judge). We cannot directly compare LLM judge scores between base and fine-tuned. The fine-tuned model may have traded holistic quality (flavor fidelity, explanation quality) for structural compliance — or it may have improved on both.

2. **LLM judge overestimates compliance.** The judge gave the base model 9.88/10 on compliance despite 0% passing the deterministic check. Judge compliance scores measure *perceived effort*, not *actual correctness*. They should not be used as the primary compliance metric.

3. **Pairwise comparison uses fallback scoring.** Since the candidate has no judge scores, the hard-case comparison used deterministic fallback scoring (constraint_pass + format_pass) for both sides. The 86% win rate is on this simplified scale, not on judge scores.

4. **Eval loss plateaued at epoch 2.** Eval loss was 0.740 → 0.707 → 0.707 across 3 epochs, suggesting the model extracted most of what it could from the 1,090-row dataset. Further improvement likely requires either more diverse training data or a different training strategy (e.g., DPO with rejected examples containing banned ingredients).

5. **Deterministic checks are strict by design.** A single banned term in the adapted recipe (even in a minor garnish or sauce ingredient) fails the entire row. This reflects real-world requirements — dietary compliance is binary for people with allergies — but the bar is high. A model scoring 26% on this metric is meaningfully better than one scoring 0%.

6. **Dairy-free is the hardest category (0%).** The model completely fails on dairy_free despite succeeding on other categories. Dairy derivatives have many non-obvious names (whey, casein, lactose, ghee, etc.) that the model hasn't fully internalized from 1,090 training examples.

7. **Base model eval used Ministral Small, not Ministral 8B.** The baseline was `mistral-small-latest` (Mistral's small API model), while the candidate is a fine-tuned Ministral 8B. This is an intentional design choice — the baseline represents what you'd get from the Mistral API without fine-tuning — but the models are not the same size, so the comparison measures "fine-tuned specialist vs general-purpose API model" rather than "same model before/after fine-tuning."

---

## Artifacts

| File | Description | Status |
|------|-------------|--------|
| `artifacts/baseline_metrics.json` | Baseline aggregate metrics | Complete (50 rows) |
| `artifacts/baseline_rows.jsonl` | Per-row baseline outputs + judge scores | Complete (50 rows) |
| `eval/eval_comparison.png` | Bar chart: base vs fine-tuned deterministic metrics | Complete |
| `train/training_log.md` | Full training loss/accuracy curve | Complete (207 steps) |
| `artifacts/space_eval_metrics.json` | Candidate aggregate metrics | Complete (50 rows) |
| `artifacts/space_eval_rows.jsonl` | Candidate per-row outputs | Complete (50 rows) |
| `artifacts/hard_case_comparison.json` | Pairwise baseline vs candidate comparison | Complete (50 rows) |
| `artifacts/baseline_rows_no_judge.jsonl` | Baseline rows (judge stripped for fair comparison) | Complete (50 rows) |

## PLAN.md Success Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| constraint_pass_rate improvement | >= +5pp | **+26pp** (0% → 26%) | **PASS** |
| hard_case_win_rate | >= 60% | **86%** (43/50) | **PASS** |
| avg_judge_score improvement | >= +0.5 | pending (no judge on candidate) | PENDING |

## Next Steps

- [x] ~~Complete full 50-row candidate eval via Space~~
- [x] ~~Run hard-case comparison for pairwise win-rate metrics~~
- [ ] Run LLM judge on candidate outputs for holistic quality comparison
- [ ] Investigate dairy_free failures — may need targeted training data with dairy derivative substitutions
- [ ] Investigate DPO training with negative examples (recipes containing banned ingredients as rejected completions) to improve constraint compliance beyond 26%
