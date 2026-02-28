#!/usr/bin/env python3
"""Compute pairwise hard-case win rate from baseline vs fine-tuned eval rows.

Examples:
  uv run python eval/compare_hard_cases.py \
    --baseline-rows artifacts/baseline_rows.jsonl \
    --candidate-rows artifacts/eval_rows.jsonl \
    --output-path artifacts/hard_case_comparison.json

  uv run python eval/compare_hard_cases.py \
    --baseline-rows artifacts/baseline_hard30_rows.jsonl \
    --candidate-rows artifacts/finetuned_hard30_rows.jsonl \
    --split-name hard30 \
    --strict-judge
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} invalid JSON: {exc.msg}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_number} row must be object")
            rows.append(obj)
    return rows


def to_index(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows, start=1):
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or not row_id.strip():
            raise ValueError(f"{label} row {i} missing row_id")
        normalized = row_id.strip()
        if normalized in indexed:
            raise ValueError(f"{label} duplicate row_id: {normalized}")
        indexed[normalized] = row
    return indexed


def score_row(row: dict[str, Any], strict_judge: bool) -> tuple[float | None, str]:
    judge = row.get("judge")
    if isinstance(judge, dict):
        overall = judge.get("overall_score")
        if isinstance(overall, (int, float)):
            return float(overall), "judge.overall_score"

    if strict_judge:
        return None, "missing_judge_score"

    constraint_pass = row.get("constraint_pass")
    format_pass = row.get("format_pass")
    if isinstance(constraint_pass, bool):
        fallback_score = (1.0 if constraint_pass else 0.0) + (0.1 if bool(format_pass) else 0.0)
        return fallback_score, "fallback_constraint_format"

    return None, "missing_score"


def source_bucket(score_source: str) -> str:
    if score_source == "judge.overall_score":
        return "judge"
    if score_source == "fallback_constraint_format":
        return "fallback"
    return "missing"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-rows", type=Path, required=True)
    parser.add_argument("--candidate-rows", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=Path("artifacts/hard_case_comparison.json"))
    parser.add_argument("--split-name", type=str, default="hard30")
    parser.add_argument("--min-win-delta", type=float, default=0.0)
    parser.add_argument(
        "--strict-judge",
        action="store_true",
        help="Require judge.overall_score on both rows; otherwise mark incomparable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_rows = load_jsonl(args.baseline_rows)
    candidate_rows = load_jsonl(args.candidate_rows)
    baseline_index = to_index(baseline_rows, "baseline")
    candidate_index = to_index(candidate_rows, "candidate")

    matched_ids = sorted(set(baseline_index).intersection(candidate_index))
    baseline_only = sorted(set(baseline_index).difference(candidate_index))
    candidate_only = sorted(set(candidate_index).difference(baseline_index))
    row_set_mismatch = bool(baseline_only or candidate_only)

    wins = 0
    losses = 0
    ties = 0
    incomparable = 0
    deltas: list[float] = []
    per_row: list[dict[str, Any]] = []
    score_source_pair_breakdown: dict[str, int] = {}
    mixed_source_incomparable_rows = 0

    for row_id in matched_ids:
        base_row = baseline_index[row_id]
        cand_row = candidate_index[row_id]
        base_score, base_source = score_row(base_row, strict_judge=args.strict_judge)
        cand_score, cand_source = score_row(cand_row, strict_judge=args.strict_judge)
        base_bucket = source_bucket(base_source)
        cand_bucket = source_bucket(cand_source)
        source_pair_key = f"{base_bucket}_vs_{cand_bucket}"
        score_source_pair_breakdown[source_pair_key] = score_source_pair_breakdown.get(source_pair_key, 0) + 1

        result = {
            "row_id": row_id,
            "baseline_score": base_score,
            "candidate_score": cand_score,
            "baseline_score_source": base_source,
            "candidate_score_source": cand_source,
            "baseline_score_bucket": base_bucket,
            "candidate_score_bucket": cand_bucket,
        }

        if base_score is None or cand_score is None:
            incomparable += 1
            result["result"] = "incomparable"
            per_row.append(result)
            continue

        if base_bucket != cand_bucket:
            mixed_source_incomparable_rows += 1
            incomparable += 1
            result["result"] = "incomparable"
            result["incomparable_reason"] = "mixed_score_source"
            per_row.append(result)
            continue

        delta = cand_score - base_score
        deltas.append(delta)
        result["score_delta"] = delta

        if delta > args.min_win_delta:
            wins += 1
            result["result"] = "win"
        elif delta < -args.min_win_delta:
            losses += 1
            result["result"] = "loss"
        else:
            ties += 1
            result["result"] = "tie"
        per_row.append(result)

    comparable = wins + losses + ties
    hard_case_win_rate = (wins / comparable) if comparable else None
    non_loss_rate = ((wins + ties) / comparable) if comparable else None
    avg_score_delta = mean(deltas) if deltas else None
    if row_set_mismatch:
        hard_case_win_rate = None
        non_loss_rate = None
        avg_score_delta = None

    output = {
        "generated_at": utc_now_iso(),
        "split_name": args.split_name,
        "baseline_rows_path": str(args.baseline_rows),
        "candidate_rows_path": str(args.candidate_rows),
        "strict_judge": bool(args.strict_judge),
        "min_win_delta": args.min_win_delta,
        "summary": {
            "matched_rows": len(matched_ids),
            "baseline_only_rows": len(baseline_only),
            "candidate_only_rows": len(candidate_only),
            "row_set_mismatch": row_set_mismatch,
            "headline_metrics_suppressed_due_to_row_set_mismatch": row_set_mismatch,
            "comparable_rows": comparable,
            "incomparable_rows": incomparable,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "hard_case_win_rate": hard_case_win_rate,
            "hard_case_non_loss_rate": non_loss_rate,
            "avg_score_delta": avg_score_delta,
            "score_source_pair_breakdown": dict(sorted(score_source_pair_breakdown.items())),
            "mixed_source_incomparable_rows": mixed_source_incomparable_rows,
            "mixed_source_incomparable_rate": (
                mixed_source_incomparable_rows / len(matched_ids) if matched_ids else None
            ),
        },
        "row_mismatches": {
            "baseline_only_row_ids": baseline_only,
            "candidate_only_row_ids": candidate_only,
        },
        "rows": per_row,
    }

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with args.output_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=True)
        handle.write("\n")

    print(f"wrote comparison: {args.output_path}")
    print(
        "summary:"
        f" matched={len(matched_ids)} comparable={comparable}"
        f" wins={wins} losses={losses} ties={ties}"
        f" hard_case_win_rate={hard_case_win_rate}"
    )
    if row_set_mismatch:
        print(
            "warning: baseline/candidate row IDs differ; headline win-rate metrics are suppressed",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
