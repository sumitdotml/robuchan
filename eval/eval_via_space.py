#!/usr/bin/env python3
"""Evaluate the Robuchan HF Space endpoint on an eval split.

Calls the deployed Gradio Space via gradio_client, runs the same
deterministic checks as evaluate.py, and writes compatible output
artifacts (JSONL rows + metrics JSON).

Requires: pip install gradio_client

Examples:
  # quick smoke test (3 rows)
  uv run python eval/eval_via_space.py \
    --input eval/quick50.jsonl --limit 3

  # full quick50 eval
  uv run python eval/eval_via_space.py \
    --input eval/quick50.jsonl \
    --output-rows artifacts/space_eval_rows.jsonl \
    --output-metrics artifacts/space_eval_metrics.json

  # custom Space
  uv run python eval/eval_via_space.py \
    --input eval/quick50.jsonl \
    --space-id your-user/your-space
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------------
# Ensure sibling eval_engine is importable regardless of cwd.
# Per MISTAKE-20260228-024: standalone scripts must not assume cwd == repo root.
# ---------------------------------------------------------------------------
_EVAL_DIR = str(Path(__file__).resolve().parent)
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

from eval_engine import (
    check_required_sections,
    compile_constraint_patterns,
    compute_summary,
    content_to_text,
    deterministic_constraint_check,
    extract_restrictions,
    load_json,
    load_jsonl,
    normalize_messages,
    utc_now_iso,
    write_json,
    write_rows_jsonl,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SPACE_ID = "sumitdotml/robuchan-demo"
DEFAULT_CONSTRAINTS_PATH = Path("eval/constraints.json")
DEFAULT_OUTPUT_ROWS = Path("artifacts/space_eval_rows.jsonl")
DEFAULT_OUTPUT_METRICS = Path("artifacts/space_eval_metrics.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_space_message(recipe_text: str, restrictions: list[str]) -> str:
    """Build a single message string combining recipe and constraint for the Space."""
    if not restrictions:
        return recipe_text
    constraint_str = ", ".join(r.replace("_", " ") for r in restrictions)
    return f"Adapt this recipe for: {constraint_str}\n\n{recipe_text}"


def call_space(client: object, message: str) -> str:
    """Call the Gradio Space /predict endpoint (single message param)."""
    result = client.predict(  # type: ignore[attr-defined]
        message=message,
        api_name="/predict",
    )
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)) and result:
        return str(result[0])
    return str(result)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the Robuchan HF Space on an eval split.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to evaluation JSONL split (e.g. eval/quick50.jsonl).",
    )
    parser.add_argument(
        "--output-rows",
        type=Path,
        default=DEFAULT_OUTPUT_ROWS,
        help="Path for per-row JSONL output.",
    )
    parser.add_argument(
        "--output-metrics",
        type=Path,
        default=DEFAULT_OUTPUT_METRICS,
        help="Path for aggregate metrics JSON output.",
    )
    parser.add_argument(
        "--constraints-path",
        type=Path,
        default=DEFAULT_CONSTRAINTS_PATH,
        help="Path to constraints.json for deterministic checks.",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=DEFAULT_SPACE_ID,
        help="Gradio Space ID (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to evaluate (for quick testing).",
    )
    parser.add_argument(
        "--split-name",
        type=str,
        default="space_eval",
        help="Name tag for this eval split.",
    )
    parser.add_argument(
        "--hf-token",
        type=str,
        default=None,
        help="HF token for private Spaces (reads HF_TOKEN env var as fallback).",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = build_cli_parser()
    args = parser.parse_args()

    # --- lazy-import gradio_client so --help works without it installed ---
    try:
        from gradio_client import Client  # type: ignore[import-untyped]
    except ImportError:
        print(
            "error: gradio_client is not installed. "
            "Install with: pip install gradio_client",
            file=sys.stderr,
        )
        return 1

    # --- load input rows ---
    raw_rows = load_jsonl(args.input)
    if args.limit is not None:
        raw_rows = raw_rows[: max(0, args.limit)]
    if not raw_rows:
        print(f"error: no rows found in {args.input}", file=sys.stderr)
        return 1

    # --- load constraints for deterministic checks ---
    constraints_path = args.constraints_path
    if not constraints_path.is_absolute():
        # resolve relative to repo root (parent of eval/)
        repo_root = Path(__file__).resolve().parent.parent
        resolved = repo_root / constraints_path
        if resolved.exists():
            constraints_path = resolved
    constraints_payload = load_json(constraints_path)
    compiled_constraints = compile_constraint_patterns(constraints_payload)

    # --- connect to Space ---
    import os

    hf_token = args.hf_token or os.environ.get("HF_TOKEN", "").strip() or None
    print(f"connecting to Space: {args.space_id}")
    try:
        client = Client(args.space_id, token=hf_token)
    except Exception as exc:
        print(f"error: could not connect to Space {args.space_id}: {exc}", file=sys.stderr)
        return 1

    # --- evaluate each row ---
    row_results: list[dict] = []
    total = len(raw_rows)
    print(f"evaluating {total} rows via Space {args.space_id} split={args.split_name}")

    for index, row in enumerate(raw_rows, start=1):
        row_id = str(
            row.get("row_id")
            or row.get("source_recipe_id")
            or row.get("id")
            or f"row_{index}"
        )

        # Extract messages and restrictions using eval_engine helpers
        messages = normalize_messages(row.get("messages"))
        restrictions = extract_restrictions(row, messages)

        # Build recipe text from user message content
        user_texts = []
        for msg in messages:
            if msg.get("role") == "user":
                text = content_to_text(msg.get("content"))
                if text:
                    user_texts.append(text)
        recipe_text = "\n\n".join(user_texts).strip()

        space_message = build_space_message(recipe_text, restrictions)
        print(f"[{index}/{total}] row_id={row_id} restrictions={restrictions}")

        # Call the Space
        start_time = time.monotonic()
        try:
            output_text = call_space(client, message=space_message)
        except Exception as exc:
            print(f"  ERROR calling Space: {exc}")
            output_text = f"[space_error] {exc}"
        elapsed = time.monotonic() - start_time
        print(f"  response in {elapsed:.1f}s ({len(output_text)} chars)")

        # Deterministic checks
        format_pass, missing_sections = check_required_sections(output_text)
        deterministic = deterministic_constraint_check(
            output_text=output_text,
            restrictions=restrictions,
            compiled_constraints=compiled_constraints,
        )

        # Extract gold assistant if present (last assistant message)
        gold_assistant = None
        if messages and messages[-1].get("role") == "assistant":
            gold_assistant = content_to_text(messages[-1].get("content")) or None

        row_results.append(
            {
                "row_id": row_id,
                "restrictions": restrictions,
                "constraint_pass": deterministic["constraint_pass"],
                "format_pass": format_pass,
                "missing_sections": missing_sections,
                "deterministic": deterministic,
                "judge": None,
                "output_text": output_text,
                "gold_assistant": gold_assistant,
            }
        )

    # --- compute summary (no judge, no token costs for Space) ---
    summary = compute_summary(
        row_results=row_results,
        eval_prompt_tokens=0,
        eval_completion_tokens=0,
        judge_prompt_tokens=0,
        judge_completion_tokens=0,
        judge_enabled=False,
        prompt_price_per_1m=0.0,
        completion_price_per_1m=0.0,
        judge_prompt_price_per_1m=0.0,
        judge_completion_price_per_1m=0.0,
    )

    # --- write outputs ---
    result_payload = {
        "generated_at": utc_now_iso(),
        "split_name": args.split_name,
        "input_path": str(args.input),
        "model": f"space:{args.space_id}",
        "inference_backend": "gradio_space",
        "space_id": args.space_id,
        "judge_model": None,
        "constraints_path": str(args.constraints_path),
        "dry_run": False,
        "summary": summary,
    }

    write_json(args.output_metrics, result_payload)
    write_rows_jsonl(args.output_rows, row_results)

    print(f"wrote metrics: {args.output_metrics}")
    print(f"wrote row results: {args.output_rows}")
    print(
        "summary:"
        f" constraint_pass_rate={summary['constraint_pass_rate']}"
        f" format_pass_rate={summary['format_pass_rate']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
