# Plan 3 Expanded Options

This folder expands three local fine-tuning tracks for your M5 MacBook Pro (32 GB unified memory):

1. Cybersecurity Analyst
2. Robuchan
3. Science Translator

---

## 1. Why these three

All three can score both judging dimensions that you flagged:

- `Creativity (20%)`: output format and domain behavior are non-trivial and demo-friendly.
- `Usefulness (20%)`: each solves a real workflow problem with measurable outcomes.

They also preserve `Track alignment (20%)` through local fine-tuning of a Mistral model.

---

## 2. Quick comparison

| Option | Creativity | Usefulness | Data prep effort | License risk | Eval clarity | Demo strength |
|---|---:|---:|---:|---:|---:|---:|
| Cybersecurity Analyst | 4/5 | 5/5 | Low | Low | High | High |
| Robuchan | 5/5 | 4/5 | Medium | Medium | High | Very High |
| Science Translator | 4/5 | 5/5 | Low | Low | High | High |

---

## 3. Recommendation logic

If you want maximum pragmatic value and least compliance risk:

1. Primary: Science Translator
2. Backup: Cybersecurity Analyst

If you want the most memorable live demo:

1. Primary: Robuchan
2. Backup: Science Translator

---

## 4. Shared local fine-tuning assumptions

Common baseline across all three docs:

- Base model: `mistralai/Mistral-7B-Instruct-v0.3`
- Training method: `mlx_lm.lora` (LoRA/QLoRA) on Apple Silicon
- Memory-safe starter config for 32 GB machines:
  - `batch_size=1`
  - `num_layers=4`
  - `max_seq_length=1024` to `1536`
  - `grad_accumulation_steps=4`
  - `train_iters=600` to `1200`
- Optional `Theme 2` tie-in: use Mistral API for evaluation/judging.

Reference docs:

- MLX LM README: <https://github.com/ml-explore/mlx-lm>
- LoRA guide (includes 32 GB example): <https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md>

---

## 5. Sources used for propositions

- Cybersecurity dataset (Fenrir v2.0): <https://huggingface.co/datasets/AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.0>
- CTI benchmark: <https://huggingface.co/datasets/AI4Sec/cti-bench>
- RecipePairs dataset: <https://huggingface.co/datasets/lishuyang/recipepairs>
- SHARE paper (EMNLP 2022): <https://aclanthology.org/2022.emnlp-main.761/>
- Scientific lay summarisation dataset: <https://huggingface.co/datasets/tomasg25/scientific_lay_summarisation>
- Making Science Simple paper: <https://arxiv.org/abs/2210.09932>
