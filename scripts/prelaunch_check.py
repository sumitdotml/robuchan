#!/usr/bin/env python3
"""Prelaunch readiness checks for fine-tuning + eval handoff.

Examples:
  # baseline run (does not require eval split files or manifest)
  uv run python scripts/prelaunch_check.py

  # full launch gate (require eval splits and manifest)
  uv run python scripts/prelaunch_check.py \
    --require-eval-splits \
    --require-manifest

  # workspace split confirmation via explicit labels
  uv run python scripts/prelaunch_check.py \
    --workspace-a-label workspace-ft-eval \
    --workspace-b-label workspace-synth

  # machine-readable report
  uv run python scripts/prelaunch_check.py \
    --require-eval-splits \
    --json \
    --report-path artifacts/prelaunch_report.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"
REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def check_env_var(name: str) -> CheckResult:
    value = os.environ.get(name, "").strip()
    if value:
        return CheckResult(name=name, status=PASS, detail=f"{name} is set")
    return CheckResult(name=name, status=FAIL, detail=f"{name} is missing or empty")


def check_wandb_runtime() -> CheckResult:
    key = os.environ.get("WANDB_API_KEY", "").strip()
    if not key:
        return CheckResult(
            name="wandb_key",
            status=FAIL,
            detail="WANDB_API_KEY is missing; W&B is required for launch tracking",
        )

    if importlib.util.find_spec("wandb") is None:
        return CheckResult(
            name="wandb_package",
            status=FAIL,
            detail="WANDB_API_KEY is set but python package `wandb` is not installed",
        )
    return CheckResult(name="wandb_runtime", status=PASS, detail="WANDB_API_KEY + wandb package present")


def check_path_exists(name: str, path: Path, *, required: bool) -> CheckResult:
    if path.exists():
        return CheckResult(name=name, status=PASS, detail=f"found {path}")
    if required:
        return CheckResult(name=name, status=FAIL, detail=f"missing required path: {path}")
    return CheckResult(name=name, status=WARN, detail=f"optional path not found yet: {path}")


def check_quality_gate(quality_gate_path: Path, target_kept_rows: int) -> CheckResult:
    if not quality_gate_path.exists():
        return CheckResult(
            name="quality_gate",
            status=FAIL,
            detail=f"quality gate artifact missing: {quality_gate_path}",
        )
    with tempfile.TemporaryDirectory(prefix="prelaunch-check-") as temp_dir:
        scratch_manifest_path = Path(temp_dir) / "scratch_manifest.json"
        command = [
            sys.executable,
            str(REPO_ROOT / "train/finetune.py"),
            "check-quality-gate",
            "--quality-gate-path",
            str(quality_gate_path),
            "--target-kept-rows",
            str(target_kept_rows),
            "--manifest-path",
            str(scratch_manifest_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT)
    if completed.returncode == 0:
        first_line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else "quality gate passed"
        return CheckResult(name="quality_gate", status=PASS, detail=first_line)

    combined = "\n".join(part for part in (completed.stderr.strip(), completed.stdout.strip()) if part)
    first_error_line = combined.splitlines()[0] if combined else "quality gate check failed"
    return CheckResult(name="quality_gate", status=FAIL, detail=first_error_line)


def check_manifest(manifest_path: Path, *, required: bool) -> CheckResult:
    if not manifest_path.exists():
        if required:
            return CheckResult(name="manifest", status=FAIL, detail=f"missing required manifest: {manifest_path}")
        return CheckResult(name="manifest", status=SKIP, detail=f"manifest not required yet: {manifest_path}")

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        return CheckResult(name="manifest", status=FAIL, detail=f"invalid JSON in manifest: {exc.msg}")

    if not isinstance(payload, dict):
        return CheckResult(name="manifest", status=FAIL, detail="manifest root must be a JSON object")

    job_id = payload.get("job", {}).get("id") if isinstance(payload.get("job"), dict) else None
    if isinstance(job_id, str) and job_id.strip():
        return CheckResult(name="manifest", status=PASS, detail=f"manifest loaded; job.id={job_id}")
    return CheckResult(name="manifest", status=PASS, detail="manifest loaded")


def check_workspace_split(
    workspace_a_label: str,
    workspace_b_label: str,
    workspace_split_ack_env: str,
) -> CheckResult:
    a = workspace_a_label.strip()
    b = workspace_b_label.strip()
    if a and b:
        if a == b:
            return CheckResult(
                name="workspace_split",
                status=FAIL,
                detail="workspace labels are identical; expected separate synth vs ft/eval workspaces",
            )
        return CheckResult(
            name="workspace_split",
            status=PASS,
            detail=f"workspace labels differ ({a} vs {b})",
        )

    ack_value = os.environ.get(workspace_split_ack_env, "")
    if is_truthy(ack_value):
        return CheckResult(
            name="workspace_split",
            status=PASS,
            detail=f"{workspace_split_ack_env} confirms workspace split assumption",
        )

    return CheckResult(
        name="workspace_split",
        status=FAIL,
        detail=(
            "workspace split assumption is unconfirmed. "
            "Set --workspace-a-label/--workspace-b-label or set "
            f"{workspace_split_ack_env}=1"
        ),
    )


def summarize(results: list[CheckResult]) -> dict[str, int]:
    counts = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-path", type=Path, default=Path("data/train_filtered.jsonl"))
    parser.add_argument("--valid-path", type=Path, default=Path("data/valid_filtered.jsonl"))
    parser.add_argument("--constraints-path", type=Path, default=Path("eval/constraints.json"))
    parser.add_argument("--quality-gate-path", type=Path, default=Path("artifacts/quality_gate_report.json"))
    parser.add_argument("--target-kept-rows", type=int, default=1200)
    parser.add_argument("--manifest-path", type=Path, default=Path("artifacts/ft_run_manifest.json"))
    parser.add_argument("--require-manifest", action="store_true")
    parser.add_argument("--require-eval-splits", action="store_true")
    parser.add_argument("--quick-split-path", type=Path, default=Path("data/quick50.jsonl"))
    parser.add_argument("--final-split-path", type=Path, default=Path("data/final150.jsonl"))
    parser.add_argument("--hard-split-path", type=Path, default=Path("eval/hard_cases.jsonl"))
    parser.add_argument("--workspace-a-label", type=str, default=os.environ.get("MISTRAL_WORKSPACE_A", ""))
    parser.add_argument("--workspace-b-label", type=str, default=os.environ.get("MISTRAL_WORKSPACE_B", ""))
    parser.add_argument("--workspace-split-ack-env", type=str, default="WORKSPACE_SPLIT_CONFIRMED")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--report-path", type=Path, default=None, help="Optional JSON report output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results: list[CheckResult] = []

    results.append(check_env_var("MISTRAL_API_KEY"))
    results.append(check_wandb_runtime())

    results.append(check_path_exists("train_file", args.train_path, required=True))
    results.append(check_path_exists("valid_file", args.valid_path, required=True))
    results.append(check_path_exists("constraints_file", args.constraints_path, required=True))

    results.append(check_quality_gate(args.quality_gate_path, args.target_kept_rows))
    results.append(check_manifest(args.manifest_path, required=args.require_manifest))
    results.append(
        check_workspace_split(
            workspace_a_label=args.workspace_a_label,
            workspace_b_label=args.workspace_b_label,
            workspace_split_ack_env=args.workspace_split_ack_env,
        )
    )

    eval_split_required = bool(args.require_eval_splits)
    results.append(check_path_exists("eval_quick50", args.quick_split_path, required=eval_split_required))
    results.append(check_path_exists("eval_final150", args.final_split_path, required=eval_split_required))
    results.append(check_path_exists("eval_hard30", args.hard_split_path, required=eval_split_required))

    counts = summarize(results)
    overall_ok = counts[FAIL] == 0
    human_out = sys.stderr if args.json else sys.stdout

    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}", file=human_out)
    print(
        "summary:"
        f" pass={counts[PASS]} fail={counts[FAIL]} warn={counts[WARN]} skip={counts[SKIP]}",
        file=human_out,
    )

    payload: dict[str, Any] = {
        "ok": overall_ok,
        "counts": counts,
        "checks": [result.__dict__ for result in results],
    }

    if args.report_path:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        with args.report_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        print(f"wrote report: {args.report_path}", file=human_out)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))

    if overall_ok:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
