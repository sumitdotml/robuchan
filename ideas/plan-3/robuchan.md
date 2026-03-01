# Proposition: Robuchan

---

## 1. Goal

Fine-tune a local Mistral model that can transform a base recipe into a compliant alternative for a target dietary constraint:

- vegan
- vegetarian
- gluten-free
- dairy-free
- nut-free
- low-sodium
- low-sugar

Target outcome: produce substitutions that are both compliant and culinarily coherent.

---

## 2. Judging criteria fit

1. Technicity (20%)
- Structured recipe transformation task with rule-based compliance scoring.

2. Creativity (20%)
- High: culinary substitutions and style-preserving adaptations are easy to show live.

3. Usefulness (20%)
- Practical for home cooks, nutrition apps, and global food localization.

4. Demo (20%)
- Very strong: "paste recipe + choose diet -> get adapted recipe."

5. Track alignment (20%)
- Theme 1 satisfied with local fine-tuning.

---

## 3. Dataset plan

Primary:

- `lishuyang/recipepairs`
- Includes paired recipe transformations for dietary constraints
- License on card: GPL-3.0

Supporting source:

- SHARE paper describing recipe personalization framework and paired adaptation setup.

Fallback/augmentation:

- `mbien/recipe_nlg` for additional base recipe diversity (if needed).

Hackathon data slice:

1. Build a 15k-30k pair subset stratified by constraint type.
2. Hold out 2k examples for validation.
3. Add 30 handpicked Japanese-friendly dishes for demo relevance.

---

## 4. Local fine-tuning plan (M5, 32 GB)

Base model:

- `mistralai/Mistral-7B-Instruct-v0.3`

Input template:

```text
You are a culinary adaptation assistant.
Constraint: <constraint>
Original recipe:
<title + ingredients + instructions>
Return:
1) adapted ingredient list
2) adapted instructions
3) substitution rationale
```

Starter hyperparameters:

- `batch_size=1`
- `num_layers=4`
- `max_seq_length=1536`
- `learning_rate=1e-5`
- `train_iters=1000`
- `steps_per_eval=100`
- `seed=42`

---

## 5. Evaluation protocol

Rule-based compliance checks (deterministic):

1. Constraint violation rate <= 5%
2. Required substitutions coverage >= 90%
3. Invalid ingredient carryover rate <= 5%

Quality checks:

1. Instruction coherence score (LLM rubric 1-5) >= 4.0
2. Taste plausibility score (LLM rubric 1-5) >= 3.8
3. Improvement vs base model >= +0.6 average rubric points

Format checks:

1. Output sections present (ingredients, instructions, rationale) >= 98%

---

## 6. Demo script

1. Input: "Classic tonkotsu ramen" with `vegan` constraint.
2. Show base output (often generic or partially non-compliant).
3. Show finetuned output:
- complete substitutions
- preserved flavor intent
- coherent steps
4. Run compliance checker live and show pass/fail.

Optional second prompt:

- "Japanese curry" with `gluten-free` constraint.

---

## 7. 13-hour execution plan

Day 1:

1. Hour 0-2: dataset subset + constraint dictionary + validators
2. Hour 2-5: first training run + baseline eval
3. Hour 5-7: second run + prompt pack for demo

Day 2:

1. Hour 0-2: evaluator UI + compliance display
2. Hour 2-4: demo scenario hardening
3. Hour 4-6: polish + reliability + backup recording

---

## 8. Risks and mitigations

Risk: license constraints for downstream reuse (GPL-3.0).
- Mitigation: keep hackathon scope clear, attribute properly, and avoid unsupported commercial claims.

Risk: model outputs compliant but bland recipes.
- Mitigation: include rationale and style-preservation signal in training template.

Risk: long recipes exceed context budget.
- Mitigation: truncate low-value narrative fields, keep ingredients and steps only.

---

## 9. References

- RecipePairs: <https://huggingface.co/datasets/lishuyang/recipepairs>
- RecipeNLG: <https://huggingface.co/datasets/mbien/recipe_nlg>
- SHARE paper: <https://aclanthology.org/2022.emnlp-main.761/>
- MLX LM: <https://github.com/ml-explore/mlx-lm>
- MLX LoRA guide: <https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md>
