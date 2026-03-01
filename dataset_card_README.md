---
dataset_info:
  features:
    - name: messages
      list:
        - name: role
          dtype: string
        - name: content
          dtype: string
  splits:
    - name: train
      num_examples: 1090
    - name: validation
      num_examples: 122
    - name: eval_quick50
      num_examples: 50
    - name: eval_final150
      num_examples: 150
    - name: eval_hard_cases
      num_examples: 30
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train_filtered.jsonl
      - split: validation
        path: data/valid_filtered.jsonl
license: apache-2.0
language:
  - en
size_categories:
  - 1K<n<10K
tags:
  - recipe-adaptation
  - dietary-restrictions
  - culinary
  - synthetic
  - mistral-hackathon
  - sft
task_categories:
  - text-generation
---

# Robuchan Dataset

Synthetic dietary recipe adaptation dataset for fine-tuning language models. Each example is a chat-format conversation where a user provides a recipe and dietary restriction, and the assistant produces a structured adaptation.

Generated for the [Mistral AI Worldwide Hackathon Tokyo](https://worldwide-hackathon.mistral.ai/) (Feb 28 - Mar 1, 2026).

Associated model: [`sumitdotml/robuchan`](https://huggingface.co/sumitdotml/robuchan)

## Dataset Structure

### Splits

| Split | Rows | Purpose |
|-------|-----:|---------|
| `train` | 1,090 | Fine-tuning training set |
| `validation` | 122 | Fine-tuning validation set |
| `eval_quick50` | 50 | Quick evaluation gate |
| `eval_final150` | 150 | Full evaluation freeze |
| `eval_hard_cases` | 30 | Curated difficult adaptations |

### Schema

Each row is a Mistral chat-format object with a `messages` array containing three roles:

- **system**: Sets the assistant's priorities (dietary compliance > dish identity > practicality) and defines the required output sections.
- **user**: Provides the recipe (title, ingredients with quantities, steps) and the target dietary restriction.
- **assistant**: Returns a structured adaptation with 5 sections.

### Output Sections

| Section | Content |
|---------|---------|
| **Substitution Plan** | One row per banned ingredient: `original -> replacement (rationale)` |
| **Adapted Ingredients** | Full ingredient list with quantities — no placeholders |
| **Adapted Steps** | Complete numbered cooking steps reflecting all substitutions |
| **Flavor Preservation Notes** | 3+ notes on how taste/texture/aroma are maintained |
| **Constraint Check** | Explicit checklist confirming all violations resolved |

### Dietary Restrictions (train split)

| Restriction | Rows |
|-------------|-----:|
| vegetarian | 791 |
| vegan | 182 |
| dairy-free | 76 |
| other | 41 |

The eval splits additionally cover gluten-free, low-sodium, low-sugar, nut-free, egg-free, shellfish-free, and low-fat.

## Generation Pipeline

1. **Source pool**: 530K recipes from [Food.com](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews/data), filtered for parseable ingredients/steps and at least one dietary violation.
2. **Synthetic generation**: Each source recipe is paired with a dietary constraint and sent to `mistral-large-latest` to produce an adapted version.
3. **Quality gate**: Deterministic checks reject candidates that fail any of:
   - Constraint compliance (all banned ingredients removed)
   - Structural completeness (all 5 sections present, no `...` placeholders)
   - Ingredient parseability (quantities and units present)
   - Violation coverage (every detected violation mapped in Substitution Plan)
4. **Single-candidate policy**: One generation attempt per recipe; drop on fail.

### Prompt Templates

Three user prompt templates with identical semantics prevent format overfitting:

| Template | Share | Style |
|----------|------:|-------|
| A — Labeled Block | 50% | Structured labeled fields |
| B — Natural Request | 30% | Conversational prose |
| C — Goal-Oriented | 20% | Goal-first with bullet lists |

Template assignment is deterministic: `hash(source_recipe_id + restriction) % 100`.

## Supporting Files

| File | Description |
|------|-------------|
| `eval/constraints.json` | Banned ingredient lists per dietary category |
| `eval/category_aliases.json` | Category name normalization |
| `kb/swaps_v0.json` | Curated ingredient swap rules (20+ rules) |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("sumitdotml/robuchan-data")
print(ds["train"][0]["messages"])
```

For fine-tuning with Mistral API, use the JSONL files directly:

```bash
# Each line is {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
head -1 data/train_filtered.jsonl | python -m json.tool
```

## Links

- Model: [sumitdotml/robuchan](https://huggingface.co/sumitdotml/robuchan)
- Code: [github.com/sumitdotml/robuchan](https://github.com/sumitdotml/robuchan)
- Demo: [sumitdotml/robuchan-demo](https://huggingface.co/spaces/sumitdotml/robuchan-demo)

## Authors

- [sumitdotml](https://github.com/sumitdotml)
- [Kaustubh Hiware](https://github.com/kaustubhhiware)

## Citation

```bibtex
@misc{robuchan2026,
  title  = {Robuchan: Recipe Dietary Adaptation via Fine-Tuned Ministral-8B},
  author = {sumitdotml and Hiware, Kaustubh},
  year   = {2026},
  url    = {https://huggingface.co/datasets/sumitdotml/robuchan-data}
}
```
