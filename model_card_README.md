---
base_model: mistralai/Ministral-8B-Instruct-2410
library_name: peft
license: apache-2.0
language:
  - en
tags:
  - recipe-adaptation
  - dietary-restrictions
  - culinary
  - sft
  - lora
  - trl
  - hf_jobs
  - mistral-hackathon
datasets:
  - sumitdotml/robuchan-data
pipeline_tag: text-generation
model-index:
  - name: robuchan
    results:
      - task:
          type: text-generation
          name: Recipe Dietary Adaptation
        metrics:
          - name: Format Compliance
            type: format_compliance
            value: 1.0
            verified: false
          - name: Dietary Constraint Compliance
            type: constraint_compliance
            value: 0.33
            verified: false
---

# Robuchan

A LoRA adapter for [Ministral-8B-Instruct-2410](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410) fine-tuned on synthetic dietary recipe adaptations.

Given a recipe and a dietary restriction (vegan, gluten-free, dairy-free, etc.), Robuchan produces a structured adaptation with ingredient substitutions, updated steps, flavor preservation notes, and a compliance self-check.

Built for the [Mistral AI Worldwide Hackathon Tokyo](https://worldwide-hackathon.mistral.ai/) (Feb 28 - Mar 1, 2026).

## Usage

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_model = AutoModelForCausalLM.from_pretrained(
    "mistralai/Ministral-8B-Instruct-2410",
    device_map="auto",
    load_in_4bit=True,
)
model = PeftModel.from_pretrained(base_model, "sumitdotml/robuchan")
tokenizer = AutoTokenizer.from_pretrained("sumitdotml/robuchan")

messages = [
    {
        "role": "system",
        "content": (
            "You are a culinary adaptation assistant. "
            "Priority: (1) strict dietary compliance, (2) preserve dish identity and flavor profile, "
            "(3) keep instructions practical and cookable. "
            "Never include forbidden ingredients or their derivatives (stocks, sauces, pastes, broths). "
            "If no exact compliant substitute exists, acknowledge the gap, choose the closest viable option, "
            "and state the trade-off. "
            "Output sections exactly: Substitution Plan, Adapted Ingredients, Adapted Steps, "
            "Flavor Preservation Notes, Constraint Check."
        ),
    },
    {
        "role": "user",
        "content": (
            "Recipe: Mapo Tofu\n"
            "Cuisine: Sichuan Chinese\n"
            "Ingredients: 400g firm tofu, 200g ground pork, 2 tbsp doubanjiang, "
            "1 tbsp oyster sauce, 3 cloves garlic, 1 inch ginger, 2 scallions, "
            "1 tbsp cornstarch, 2 tbsp neutral oil\n"
            "Steps: 1) Brown pork in oil until crispy. 2) Add minced garlic, ginger, "
            "and doubanjiang; stir-fry 30 seconds. 3) Add tofu cubes and 1 cup water; "
            "simmer 8 minutes. 4) Mix cornstarch slurry and stir in to thicken. "
            "5) Garnish with sliced scallions.\n"
            "Restrictions: vegetarian, shellfish-free\n"
            "Must Keep Flavor Notes: mala heat, savory umami, silky sauce"
        ),
    },
]

inputs = tokenizer.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True)
inputs = inputs.to(model.device)
outputs = model.generate(inputs, max_new_tokens=1024, temperature=0.7, do_sample=True)
print(tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True))
```

## Output Format

The model produces five structured sections:

| Section | Content |
|---------|---------|
| **Substitution Plan** | One row per banned ingredient: `original -> replacement (rationale)` |
| **Adapted Ingredients** | Full ingredient list with quantities — no placeholders |
| **Adapted Steps** | Complete numbered cooking steps reflecting all substitutions |
| **Flavor Preservation Notes** | 3+ notes on how taste/texture/aroma are maintained |
| **Constraint Check** | Explicit checklist confirming all violations resolved |

## Training

| Detail | Value |
|--------|-------|
| Base model | `mistralai/Ministral-8B-Instruct-2410` |
| Method | QLoRA SFT via [TRL](https://github.com/huggingface/trl) on HF Jobs (A10G) |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Training examples | 1,090 |
| Validation examples | 122 |
| Epochs completed | ~0.95 (OOM at epoch boundary eval on A10G 24GB) |
| Final train loss | 0.77 |

### Dataset

Training data was synthetically generated from [Food.com's 530K recipe corpus](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews/data):

1. Filter source recipes that violate at least one supported dietary constraint
2. Generate structured adaptations using `mistral-large-latest`
3. Score each candidate with deterministic quality checks (constraint compliance, ingredient relevance, structural completeness)
4. Keep only passing candidates — single candidate per recipe, drop on fail

The dataset covers 10 dietary categories: vegan, vegetarian, dairy-free, gluten-free, nut-free, egg-free, shellfish-free, low-sodium, low-sugar, low-fat.

Three prompt templates (labeled-block, natural-request, goal-oriented) at a 50/30/20 split prevent format overfitting.

Dataset: [`sumitdotml/robuchan-data`](https://huggingface.co/datasets/sumitdotml/robuchan-data)

## Evaluation

Three-layer evaluation: format compliance (deterministic header parsing), dietary constraint compliance (regex against banned-ingredient lists), and LLM-as-judge via `mistral-large-latest`.

| Metric | Baseline (`mistral-small-latest`, n=50) | Robuchan (n=3) | Delta |
|--------|----------------------------------------:|---------------:|------:|
| Format Compliance | 14% | 100% | **+86pp** |
| Constraint Compliance | 0% | 33% | **+33pp** |
| Judge Overall Score | 9.20/10 | — | — |

**Key findings:**
- The base model writes fluent recipe adaptations but fails at structured output (only 14% contain all 5 required sections) and completely fails dietary compliance (0% pass the banned-ingredient check).
- Robuchan fixes structured output (100%) and begins enforcing dietary constraints (33%), though more training would likely improve compliance further.
- The LLM judge overestimates compliance (9.88/10 for the base model despite 0% deterministic pass) — it measures *attempt quality*, not correctness.

W&B: [sumit-ml/robuchan](https://wandb.ai/sumit-ml/robuchan/runs/uuj6tmlo)

## Limitations

- **Small eval sample.** Only 3 rows were evaluated on the fine-tuned model before the HF Space crashed. Results are directionally strong but not statistically robust.
- **Partial training.** The adapter was saved from ~95% through epoch 1. More training would likely improve constraint compliance.
- **English only.** Training data and evaluation are English-language recipes only.
- **Not safety-tested.** This model is a hackathon prototype. Do not rely on it for medical dietary advice (severe allergies, celiac disease, etc.).

## Links

- Code: [github.com/sumitdotml/robuchan](https://github.com/sumitdotml/robuchan)
- Dataset: [sumitdotml/robuchan-data](https://huggingface.co/datasets/sumitdotml/robuchan-data)
- Demo Space: [sumitdotml/robuchan-demo](https://huggingface.co/spaces/sumitdotml/robuchan-demo)
- Demo video: [YouTube](https://www.youtube.com/watch?v=LIlsP0OqTf4)
- W&B: [sumit-ml/robuchan](https://wandb.ai/sumit-ml/robuchan)

## Authors

- [sumitdotml](https://github.com/sumitdotml)
- [Kaustubh Hiware](https://github.com/kaustubhhiware)

## Framework Versions

- PEFT: 0.18.1
- TRL: 0.29.0
- Transformers: 5.2.0
- PyTorch: 2.6.0+cu124
- Datasets: 4.6.1

## Citation

```bibtex
@misc{robuchan2026,
  title  = {Robuchan: Recipe Dietary Adaptation via Fine-Tuned Ministral-8B},
  author = {sumitdotml and Hiware, Kaustubh},
  year   = {2026},
  url    = {https://huggingface.co/sumitdotml/robuchan}
}
```
