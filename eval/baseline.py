#!/usr/bin/env python3
"""Run baseline evaluation against the unfine-tuned model.

Input split creation:
  This script does not create eval splits.
  Expected files are produced by the dataset creation/export pipeline.

Examples:
  # baseline quick gate
  uv run python eval/baseline.py \
    --input data/quick50.jsonl \
    --split-name quick50

  # baseline final freeze
  uv run python eval/baseline.py \
    --input data/final150.jsonl \
    --split-name final150

  # baseline hard-case bank
  uv run python eval/baseline.py \
    --input eval/hard_cases.jsonl \
    --split-name hard30

  # baseline deterministic-only
  uv run python eval/baseline.py \
    --input data/quick50.jsonl \
    --split-name quick50 \
    --disable-judge

  # baseline dry-run smoke test
  uv run python eval/baseline.py \
    --input data/quick50.jsonl \
    --split-name quick50 \
    --disable-judge \
    --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

from mistralai.models.sdkerror import SDKError

from eval_engine import build_parser, run


def main() -> int:
    parser = build_parser(
        default_model="mistral-small-latest",
        default_output_path=Path("artifacts/baseline_metrics.json"),
        default_rows_output_path=Path("artifacts/baseline_rows.jsonl"),
        default_split_name="baseline",
        allow_manifest_model=False,
    )
    args = parser.parse_args()
    try:
        return run(args, allow_manifest_model=False)
    except (ValueError, RuntimeError, SDKError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
