#!/usr/bin/env python3
"""Evaluate fine-tuned recipe adaptation outputs.

Input split creation:
  This script does not create eval splits.
  Expected files are produced by the dataset creation/export pipeline:
  - data/quick50.jsonl
  - data/final150.jsonl
  - eval/hard_cases.jsonl

Examples:
  # evaluating fine-tuned model on quick gate
  uv run python eval/evaluate.py \
    --input data/quick50.jsonl \
    --split-name quick50 \
    --model ft:...

  # evaluating fine-tuned model on final freeze set
  uv run python eval/evaluate.py \
    --input data/final150.jsonl \
    --split-name final150 \
    --model ft:...

  # evaluating hard-case bank
  uv run python eval/evaluate.py \
    --input eval/hard_cases.jsonl \
    --split-name hard30 \
    --model ft:...

  # using fine_tuned_model from artifacts/ft_run_manifest.json
  uv run python eval/evaluate.py \
    --input data/final150.jsonl \
    --split-name final150

  # deterministic-only run (no judge API calls)
  uv run python eval/evaluate.py \
    --input data/quick50.jsonl \
    --split-name quick50 \
    --model ft:... \
    --disable-judge

  # dry-run smoke test (no inference API calls)
  uv run python eval/evaluate.py \
    --input data/quick50.jsonl \
    --split-name quick50 \
    --model mistral-small-latest \
    --disable-judge \
    --dry-run

  # W&B auto-logging when WANDB_API_KEY is set
  uv run python eval/evaluate.py \
    --input data/final150.jsonl \
    --split-name final150 \
    --model ft:... \
    --wandb-project robuchan
"""

from __future__ import annotations

import sys
from pathlib import Path

from mistralai.models.sdkerror import SDKError

from eval_engine import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_ROWS_OUTPUT_PATH,
    build_parser,
    run,
)


def main() -> int:
    parser = build_parser(
        default_model=None,
        default_output_path=Path(DEFAULT_OUTPUT_PATH),
        default_rows_output_path=Path(DEFAULT_ROWS_OUTPUT_PATH),
        default_split_name="eval",
        allow_manifest_model=True,
    )
    args = parser.parse_args()
    try:
        return run(args, allow_manifest_model=True)
    except (ValueError, SDKError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
