# Robuchan

Recipe adaptation fine-tuning for the Mistral AI Worldwide Hackathon Tokyo (Feb 28 - Mar 1, 2026).

Fine-tune `mistral-small-latest` on synthetic dietary recipe adaptations generated from Food.com recipes via `mistral-large-latest`.

No connection to the famous chef [Joel Robuchon](https://en.wikipedia.org/wiki/Jo%C3%ABl_Robuchon).

## Key Files

| File | What it covers |
|---|---|
| [`PLAN.md`](PLAN.md) | Full 2-day execution plan: timeline, architecture, quality gates, templates, budget |
| [`DATASET_SCHEMA.md`](DATASET_SCHEMA.md) | Internal master format, export contract, scoring definitions, prompt templates |
| [`eval/constraints.json`](eval/constraints.json) | Banned ingredient lists per dietary constraint (9 categories) |
| [`CONSIDERING.md`](CONSIDERING.md) | Dataset strategy decision log and alternatives analysis |
| [`LOG.md`](LOG.md) | Decision audit trail |

## Quick Start

```bash
uv sync
cp .env.example .env  # add MISTRAL_API_KEY, WANDB_API_KEY, HF_TOKEN
```

## Stack

- **Fine-tuning**: Mistral API (cloud, not local)
- **Generation**: `mistral-large-latest` for synthetic training data
- **Eval**: deterministic compliance + LLM-as-judge
- **Tracking**: W&B (auto via Mistral `integrations` + manual eval logging)
- **Demo**: Marimo
- **Deps**: `uv`

## Agent skills usage

Under the Hugging Face Challenge, the following agent skills were used for the development of this project (& the demo video!):

- TODO: remotion agent skills

- **[mistake-memory-guardrails](.agents/skills/mistake-memory-guardrails/SKILL.md)**: Required before every repository edit (enforced in `AGENTS.md` + `CLAUDE.md`). Maintained [`AGENT_MISTAKES.md`](AGENT_MISTAKES.md) across sessions. Made data synthesis much faster, by identifying optimizations, patterns in the dataset to reduce API calls, and define static rules.

- **[coding-principles](.claude/skills/coding-principles/SKILL.md)**: Applied when writing and iterating on `data/prepare.py` and `data/audit_dataset.py`. These scripts populated the initial dataset from a Kaggle dataset, generated input data for fine-tuning Mistral models, and validated the data synthesis quality (see [data/gate.log](data/gate.log))

- **[commit](.claude/skills/commit/SKILL.md)**: Used for all git checkpoints throughout development. Enforced consistent message formatting.

- **[writing-style](.claude/skills/writing-style/SKILL.md)**: Applied to planning and decision documents (`PLAN.md`, `DATASET_SCHEMA.md`, `CONSIDERING.md`, `LOG.md`).
