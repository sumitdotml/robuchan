#!/usr/bin/env python3
"""Autofill handoff docs (H2/H3/H4) from manifest and eval artifacts.

Examples:
  # preview generated markdown in stdout only
  uv run python scripts/fill_handoffs.py --stdout

  # write updates to docs/handoffs/H2,H3,H4
  uv run python scripts/fill_handoffs.py --write

  # write and preview, with explicit owner labels
  uv run python scripts/fill_handoffs.py \
    --write \
    --stdout \
    --prepared-by sumit \
    --reviewed-by teammate \
    --owner sumit
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_MANIFEST_PATH = Path("artifacts/ft_run_manifest.json")
DEFAULT_BASELINE_METRICS_PATH = Path("artifacts/baseline_metrics.json")
DEFAULT_EVAL_METRICS_PATH = Path("artifacts/eval_metrics.json")
DEFAULT_HARD_COMPARISON_PATH = Path("artifacts/hard_case_comparison.json")
DEFAULT_HARD_CASES_PATH = Path("eval/hard_cases.jsonl")
DEFAULT_HANDOFF_DIR = Path("docs/handoffs")
JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(timezone.utc).astimezone(JST)


def now_jst_date() -> str:
    return now_jst().strftime("%Y-%m-%d")


def now_jst_ts() -> str:
    return now_jst().strftime("%Y-%m-%d %H:%M:%S JST")


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return None
    return payload


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def nested_get(data: dict[str, Any] | None, dotted_key: str) -> Any | None:
    if not isinstance(data, dict):
        return None
    current: Any = data
    for segment in dotted_key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def to_jst_string(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "N/A"
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S JST")


def fmt_float(value: Any, digits: int = 3) -> str:
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "N/A"


def fmt_pct_delta(value: Any) -> str:
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value) * 100.0:+.2f}%"
    return "N/A"


def fmt_score_delta(value: Any) -> str:
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):+.3f}"
    return "N/A"


def fmt_money(value: Any) -> str:
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, (int, float)):
        return f"${float(value):.6f}"
    return "N/A"


def choose_judge_score(summary: dict[str, Any] | None) -> float | None:
    if not isinstance(summary, dict):
        return None
    for key in ("avg_judge_score", "avg_judge_score_scored_rows"):
        value = summary.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def bool_yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def format_json_inline(value: Any) -> str:
    if value is None:
        return "N/A"
    return json.dumps(value, ensure_ascii=True)


def has_flavor_anchor(row: dict[str, Any]) -> bool:
    anchors = row.get("flavor_anchors")
    if isinstance(anchors, list):
        return len(anchors) > 0
    anchor = row.get("flavor_anchor")
    return isinstance(anchor, str) and bool(anchor.strip())


def build_h2(
    *,
    manifest: dict[str, Any] | None,
    prepared_by: str,
    reviewed_by: str,
    owner: str,
) -> str:
    job = nested_get(manifest, "job") if manifest else None
    uploaded_training = nested_get(manifest, "uploaded_files.training.id")
    uploaded_validation = nested_get(manifest, "uploaded_files.validation.id")

    if not isinstance(job, dict):
        job = {}

    job_id = job.get("id", "N/A")
    status = job.get("status", "N/A")
    started_at = to_jst_string(job.get("started_at") or job.get("start_time") or job.get("started"))
    created_at = to_jst_string(job.get("created_at"))
    time_window = f"{created_at} -> {started_at}" if created_at != "N/A" or started_at != "N/A" else "N/A"

    integrations = job.get("integrations")
    wandb_project = job.get("wandb_project") or nested_get(manifest, "wandb_project") or "N/A"
    wandb_entity = job.get("wandb_entity") or nested_get(manifest, "wandb_entity") or "N/A"
    wandb_url = job.get("wandb_run_url") or nested_get(manifest, "wandb_run_url") or "N/A"

    created = isinstance(job_id, str) and bool(job_id and job_id != "N/A")
    started = isinstance(status, str) and status not in {"QUEUED", "VALIDATED", "N/A", ""}

    return (
        "# H2 Fine-Tune Job Launch\n\n"
        f"- Date (JST): {now_jst_date()}\n"
        f"- Time window: {time_window}\n"
        f"- Prepared by: {prepared_by}\n"
        f"- Reviewed by: {reviewed_by}\n\n"
        "## Workspace and Run Identity\n\n"
        f"- Workspace owner: {owner}\n"
        f"- Mistral job id: {job_id}\n"
        f"- W&B project/entity: {wandb_project}/{wandb_entity}\n"
        f"- W&B run URL: {wandb_url}\n\n"
        "## Launch Configuration\n\n"
        f"- Base model: {job.get('model', 'N/A')}\n"
        f"- Training file id: {uploaded_training or 'N/A'}\n"
        f"- Validation file id: {uploaded_validation or 'N/A'}\n"
        f"- Hyperparameters: {format_json_inline(job.get('hyperparameters'))}\n"
        f"- Integrations: {format_json_inline(integrations)}\n\n"
        "## Launch Verification\n\n"
        f"- Job created: `{bool_yes_no(created)}`\n"
        f"- Job started: `{bool_yes_no(started)}`\n"
        f"- Current status (`QUEUED`/`RUNNING`/etc): {status}\n"
        f"- Started at (JST): {started_at}\n\n"
        "## Blockers and Fallback\n\n"
        "- Blocker: N/A\n"
        "- Fallback action (>15 min blocked): Re-run `scripts/watch_job.py` and escalate in team channel.\n"
        f"- Owner: {owner}\n\n"
        "## Next Action\n\n"
        f"- Owner: {owner}\n"
        "- Deadline (JST): N/A\n"
        "- Command(s): `uv run python scripts/watch_job.py --manifest-path artifacts/ft_run_manifest.json`\n"
    )


def build_h3(
    *,
    baseline_metrics: dict[str, Any] | None,
    hard_cases_path: Path,
    baseline_metrics_path: Path,
    prepared_by: str,
    reviewed_by: str,
    owner: str,
) -> str:
    summary = nested_get(baseline_metrics, "summary")
    if not isinstance(summary, dict):
        summary = {}

    split_name = nested_get(baseline_metrics, "split_name") or "N/A"
    input_path = nested_get(baseline_metrics, "input_path") or "N/A"
    command = (
        f"uv run python eval/baseline.py --input {input_path} --split-name {split_name}"
        if split_name != "N/A" and input_path != "N/A"
        else "N/A"
    )

    rows = read_jsonl_rows(hard_cases_path)
    hard_case_count = len(rows)
    hard_case_exists = hard_cases_path.exists()

    flavor_anchor_present = False
    if rows:
        flavor_anchor_present = all(has_flavor_anchor(row) for row in rows)

    wandb_url = nested_get(baseline_metrics, "wandb_run_url") or "N/A"
    total_cost = nested_get(summary, "estimated_cost_usd.total_cost")

    return (
        "# H3 Baseline and Eval Readiness\n\n"
        f"- Date (JST): {now_jst_date()}\n"
        f"- Time window: {now_jst_ts()}\n"
        f"- Prepared by: {prepared_by}\n"
        f"- Reviewed by: {reviewed_by}\n\n"
        "## Baseline Run Summary\n\n"
        f"- Model id: {nested_get(baseline_metrics, 'model') or 'N/A'}\n"
        f"- Eval split: {split_name}\n"
        f"- Number of examples: {nested_get(summary, 'num_examples') or 'N/A'}\n"
        f"- Command used: `{command}`\n\n"
        "## Baseline Metrics\n\n"
        f"- `constraint_pass_rate`: {fmt_float(summary.get('constraint_pass_rate'))}\n"
        f"- `format_pass_rate`: {fmt_float(summary.get('format_pass_rate'))}\n"
        f"- `avg_judge_score`: {fmt_float(choose_judge_score(summary))}\n"
        f"- Cost estimate (credits/USD): {fmt_money(total_cost)}\n\n"
        "## Hard-Case Bank Status\n\n"
        f"- `eval/hard_cases.jsonl` created: `{bool_yes_no(hard_case_exists)}`\n"
        f"- Number of hard cases: {hard_case_count}\n"
        f"- Flavor anchors included: `{bool_yes_no(flavor_anchor_present)}`\n\n"
        "## Artifact Paths\n\n"
        f"- `{baseline_metrics_path}`: {bool_yes_no(baseline_metrics_path.exists())}\n"
        f"- `eval/hard_cases.jsonl`: {hard_cases_path}\n"
        f"- W&B run URL: {wandb_url}\n\n"
        "## Next Action\n\n"
        f"- Owner: {owner}\n"
        "- Deadline (JST): N/A\n"
        "- Command(s): `uv run python eval/evaluate.py --input eval/final150.jsonl --split-name final150`\n"
    )


def build_h4(
    *,
    manifest: dict[str, Any] | None,
    baseline_metrics: dict[str, Any] | None,
    eval_metrics: dict[str, Any] | None,
    hard_comparison: dict[str, Any] | None,
    baseline_metrics_path: Path,
    eval_metrics_path: Path,
    hard_comparison_path: Path,
    prepared_by: str,
    reviewed_by: str,
    owner: str,
) -> str:
    baseline_summary = nested_get(baseline_metrics, "summary")
    eval_summary = nested_get(eval_metrics, "summary")
    hard_summary = nested_get(hard_comparison, "summary")

    if not isinstance(baseline_summary, dict):
        baseline_summary = {}
    if not isinstance(eval_summary, dict):
        eval_summary = {}
    if not isinstance(hard_summary, dict):
        hard_summary = {}

    base_constraint = baseline_summary.get("constraint_pass_rate")
    cand_constraint = eval_summary.get("constraint_pass_rate")
    constraint_delta = None
    if isinstance(base_constraint, (int, float)) and isinstance(cand_constraint, (int, float)):
        constraint_delta = float(cand_constraint) - float(base_constraint)

    base_judge = choose_judge_score(baseline_summary)
    cand_judge = choose_judge_score(eval_summary)
    judge_delta = None
    if base_judge is not None and cand_judge is not None:
        judge_delta = cand_judge - base_judge

    hard_case_win_rate = hard_summary.get("hard_case_win_rate")
    win_rate_ok = isinstance(hard_case_win_rate, (int, float)) and float(hard_case_win_rate) >= 0.60
    constraint_ok = isinstance(constraint_delta, (int, float)) and float(constraint_delta) >= 0.05
    judge_ok = isinstance(judge_delta, (int, float)) and float(judge_delta) >= 0.5
    condition_met = bool(constraint_ok or judge_ok or win_rate_ok)
    decision = "GO_5A" if condition_met else "RUN_5B"

    baseline_cost = nested_get(baseline_summary, "estimated_cost_usd.total_cost")
    eval_cost = nested_get(eval_summary, "estimated_cost_usd.total_cost")

    return (
        "# H4 Kill-Switch Decision (Pre-Block 5A)\n\n"
        f"- Date (JST): {now_jst_date()}\n"
        f"- Decision window: {now_jst_ts()}\n"
        f"- Prepared by: {prepared_by}\n"
        f"- Reviewed by: {reviewed_by}\n\n"
        "## Inputs\n\n"
        f"- Fine-tuned model id: {nested_get(manifest, 'job.fine_tuned_model') or 'N/A'}\n"
        f"- Baseline metrics artifact: {baseline_metrics_path}\n"
        f"- Fine-tuned metrics artifact: {eval_metrics_path}\n"
        f"- Hard-case A/B artifact: {hard_comparison_path}\n\n"
        "## Decision Metrics\n\n"
        f"- `constraint_pass_rate` delta: {fmt_pct_delta(constraint_delta)}\n"
        f"- `avg_judge_score` delta: {fmt_score_delta(judge_delta)}\n"
        f"- `hard_case_win_rate`: {fmt_float(hard_case_win_rate)}\n"
        f"- Cost consumed so far (workspace A / workspace B): {fmt_money(baseline_cost)} / {fmt_money(eval_cost)}\n\n"
        "## Rule Check\n\n"
        "Kill Switch 1 condition:\n"
        "- `constraint_pass_rate` >= +5% OR\n"
        "- `avg_judge_score` >= +0.5 OR\n"
        "- `hard_case_win_rate` >= 60%\n\n"
        "Result:\n"
        f"- Condition met: `{bool_yes_no(condition_met)}`\n"
        f"- Decision: `{decision}`\n\n"
        "## Action Plan\n\n"
        f"- If `GO_5A`: {owner} + `uv run python train/finetune.py status --json`\n"
        f"- If `RUN_5B`: {owner} + `uv run python train/finetune.py create-job --auto-start` (after plan confirmation)\n"
        f"- Timestamp (JST): {now_jst_ts()}\n"
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--baseline-metrics-path", type=Path, default=DEFAULT_BASELINE_METRICS_PATH)
    parser.add_argument("--eval-metrics-path", type=Path, default=DEFAULT_EVAL_METRICS_PATH)
    parser.add_argument("--hard-comparison-path", type=Path, default=DEFAULT_HARD_COMPARISON_PATH)
    parser.add_argument("--hard-cases-path", type=Path, default=DEFAULT_HARD_CASES_PATH)
    parser.add_argument("--handoff-dir", type=Path, default=DEFAULT_HANDOFF_DIR)
    parser.add_argument("--prepared-by", type=str, default="TBD")
    parser.add_argument("--reviewed-by", type=str, default="TBD")
    parser.add_argument("--owner", type=str, default="TBD")
    parser.add_argument("--write", action="store_true", help="Write H2/H3/H4 files in-place.")
    parser.add_argument("--stdout", action="store_true", help="Print generated markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    manifest = read_json_file(args.manifest_path)
    baseline_metrics = read_json_file(args.baseline_metrics_path)
    eval_metrics = read_json_file(args.eval_metrics_path)
    hard_comparison = read_json_file(args.hard_comparison_path)

    outputs = {
        args.handoff_dir / "H2_job_launch.md": build_h2(
            manifest=manifest,
            prepared_by=args.prepared_by,
            reviewed_by=args.reviewed_by,
            owner=args.owner,
        ),
        args.handoff_dir / "H3_baseline.md": build_h3(
            baseline_metrics=baseline_metrics,
            hard_cases_path=args.hard_cases_path,
            baseline_metrics_path=args.baseline_metrics_path,
            prepared_by=args.prepared_by,
            reviewed_by=args.reviewed_by,
            owner=args.owner,
        ),
        args.handoff_dir / "H4_decision.md": build_h4(
            manifest=manifest,
            baseline_metrics=baseline_metrics,
            eval_metrics=eval_metrics,
            hard_comparison=hard_comparison,
            baseline_metrics_path=args.baseline_metrics_path,
            eval_metrics_path=args.eval_metrics_path,
            hard_comparison_path=args.hard_comparison_path,
            prepared_by=args.prepared_by,
            reviewed_by=args.reviewed_by,
            owner=args.owner,
        ),
    }

    if args.write:
        for path, text in outputs.items():
            write_text(path, text)
            print(f"wrote {path}")

    if args.stdout or not args.write:
        for path, text in outputs.items():
            print("")
            print(f"===== {path} =====")
            print("")
            print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
