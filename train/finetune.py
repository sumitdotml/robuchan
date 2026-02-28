#!/usr/bin/env python3
"""Mistral fine-tuning orchestration CLI for upload/job lifecycle.

Typical flow:
  export MISTRAL_API_KEY=...
  export WANDB_API_KEY=...  # W&B integration auto-enables when set

  uv run python train/finetune.py upload \
    --train-path data/train_filtered.jsonl \
    --valid-path data/valid_filtered.jsonl

  uv run python train/finetune.py check-quality-gate \
    --quality-gate-path artifacts/dataset_audit_summary.json

  # example: fine-tune Ministral 3B
  uv run python train/finetune.py create-job \
    --model ministral-3b-latest \
    --training-steps 100 \
    --learning-rate 1e-4 \
    --suffix recipe-remix-foodcom-synth \
    --wandb-project recipe-remix

  uv run python train/finetune.py start-job
  uv run python train/finetune.py wait
  uv run python train/finetune.py status --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mistralai import Mistral
from mistralai.models.sdkerror import SDKError


DEFAULT_MANIFEST_PATH = Path("artifacts/ft_run_manifest.json")
DEFAULT_MODEL = "mistral-small-latest"
DEFAULT_SUFFIX = "recipe-remix-foodcom-synth"
DEFAULT_TRAIN_STEPS = 100
DEFAULT_LEARNING_RATE = 1e-4
DEFAULT_WANDB_PROJECT = "recipe-remix"
DEFAULT_QUALITY_GATE_PATH = Path("artifacts/dataset_audit_summary.json")
DEFAULT_TARGET_KEPT_ROWS = 1200

TERMINAL_JOB_STATUSES = {"SUCCESS", "FAILED", "FAILED_VALIDATION", "CANCELLED"}

PASS_DECISIONS = {"GO", "PASS", "READY", "READY_FOR_FT", "GO_FT"}
FAIL_DECISIONS = {"NO_GO", "FAIL", "FAILED"}

QUALITY_GATE_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "label": "constraint_pass_rate_on_kept >= 0.98",
        "keys": (
            "constraint_pass_rate_on_kept",
            "metrics.constraint_pass_rate_on_kept",
            "metrics.constraint_pass_rate",
        ),
        "min": 0.98,
    },
    {
        "label": "semantic_completeness_pass_rate_on_kept == 1.00",
        "keys": (
            "semantic_completeness_pass_rate_on_kept",
            "metrics.semantic_completeness_pass_rate_on_kept",
        ),
        "min": 1.0,
    },
    {
        "label": "assistant_completeness_validation_pass_rate_on_kept == 1.00",
        "keys": (
            "assistant_completeness_validation_pass_rate_on_kept",
            "metrics.assistant_completeness_validation_pass_rate_on_kept",
        ),
        "min": 1.0,
    },
    {
        "label": "mean_relevance_score_on_kept >= 0.55",
        "keys": (
            "mean_relevance_score_on_kept",
            "mean_relevance_on_kept",
            "metrics.mean_relevance_score_on_kept",
            "metrics.mean_relevance_on_kept",
        ),
        "min": 0.55,
    },
    {
        "label": "mean_substitution_plausibility_score_on_kept >= 0.65",
        "keys": (
            "mean_substitution_plausibility_score_on_kept",
            "mean_substitution_plausibility_on_kept",
            "metrics.mean_substitution_plausibility_score_on_kept",
            "metrics.mean_substitution_plausibility_on_kept",
        ),
        "min": 0.65,
    },
    {
        "label": "nontriviality_pass_rate_on_kept >= 0.90",
        "keys": (
            "nontriviality_pass_rate_on_kept",
            "nontrivial_adaptation_pass_rate_on_kept",
            "nontrivial_pass_rate_on_kept",
            "metrics.nontriviality_pass_rate_on_kept",
            "metrics.nontrivial_pass_rate_on_kept",
            "metrics.nontrivial_pass_rate",
        ),
        "min": 0.90,
    },
    {
        "label": "manual_10_row_pre_ft_spotcheck_pass_rate >= 0.80",
        "keys": (
            "manual_10_row_pre_ft_spotcheck_pass_rate",
            "manual_10_row_spotcheck_pass_rate",
            "metrics.manual_10_row_pre_ft_spotcheck_pass_rate",
        ),
        "min": 0.80,
    },
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def update_manifest(manifest_path: Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = read_json_file(manifest_path)
    merged = deep_merge(current, updates)
    merged["updated_at"] = utc_now_iso()
    write_json_file(manifest_path, merged)
    return merged


def load_api_key() -> str:
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("MISTRAL_API_KEY is required")
    return api_key


def create_client() -> Mistral:
    return Mistral(api_key=load_api_key())


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not path.is_file():
        raise ValueError(f"path is not a file: {path}")


def normalize_response(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
        return {"value": dumped}
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def nested_get(data: dict[str, Any], dotted_key: str) -> Any | None:
    current: Any = data
    for segment in dotted_key.split("."):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def recursive_find_key(data: Any, key: str) -> Any | None:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = recursive_find_key(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = recursive_find_key(value, key)
            if found is not None:
                return found
    return None


def find_key_prefer_top_level(data: dict[str, Any], key: str) -> Any | None:
    if key in data:
        return data[key]
    return recursive_find_key(data, key)


def first_present_value(data: dict[str, Any], candidates: tuple[str, ...]) -> tuple[str | None, Any | None]:
    for candidate in candidates:
        value = nested_get(data, candidate) if "." in candidate else find_key_prefer_top_level(data, candidate)
        if value is not None:
            return candidate, value
    return None, None


def normalize_rate(value: Any) -> float:
    numeric = float(value)
    if numeric > 1.0 and numeric <= 100.0:
        return numeric / 100.0
    return numeric


def parse_int_like(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            return None
    return None


def evaluate_template_distribution(data: dict[str, Any]) -> tuple[bool, list[str]]:
    key, distribution = first_present_value(
        data,
        (
            "template_distribution_on_kept",
            "template_distribution",
            "metrics.template_distribution_on_kept",
            "metrics.template_distribution",
        ),
    )
    if key is None or not isinstance(distribution, dict):
        return False, ["missing template distribution (expected A/B/C rates)"]

    issues: list[str] = []
    target_rates = {"A": 0.50, "B": 0.30, "C": 0.20}
    tolerance = 0.10
    for bucket, target in target_rates.items():
        raw_value = distribution.get(bucket)
        if raw_value is None:
            issues.append(f"{key}.{bucket} is missing")
            continue
        actual = normalize_rate(raw_value)
        if abs(actual - target) > tolerance:
            issues.append(
                f"{key}.{bucket}={actual:.4f} outside target {target:.2f} +/- {tolerance:.2f}"
            )
    return len(issues) == 0, issues


def evaluate_quality_gate(
    quality_gate_path: Path,
    target_kept_rows: int,
) -> tuple[bool, dict[str, Any]]:
    if not quality_gate_path.exists():
        return False, {"errors": [f"quality gate artifact not found: {quality_gate_path}"]}

    summary = read_json_file(quality_gate_path)
    report: dict[str, Any] = {
        "path": str(quality_gate_path),
        "checked_at": utc_now_iso(),
        "checks": [],
        "errors": [],
    }

    decision_key, decision_value = first_present_value(summary, ("decision", "gate_status"))
    if isinstance(decision_value, str):
        normalized_decision = decision_value.strip().upper()
        if normalized_decision in FAIL_DECISIONS:
            report["errors"].append(f"{decision_key}={decision_value!r} indicates gate failure")
            report["summary"] = summary
            return False, report
        if normalized_decision in PASS_DECISIONS:
            report["checks"].append(f"{decision_key}={decision_value!r} indicates gate pass")

    explicit_gate_flags = (
        "quality_gate_pass",
        "gate_pass",
        "quality_gate_ok",
        "all_quality_gates_passed",
    )
    explicit_outcomes: list[tuple[str, bool]] = []
    for key in explicit_gate_flags:
        value = find_key_prefer_top_level(summary, key)
        if isinstance(value, bool):
            explicit_outcomes.append((key, value))

    if any(not outcome for _, outcome in explicit_outcomes):
        for key, outcome in explicit_outcomes:
            if not outcome:
                report["errors"].append(f"{key}=false")
        report["summary"] = summary
        return False, report
    if explicit_outcomes and all(outcome for _, outcome in explicit_outcomes):
        report["checks"].append("explicit quality gate flag(s) indicate pass")

    kept_key, kept_value = first_present_value(summary, ("kept_rows", "final_kept_rows", "train_rows_kept"))
    if kept_value is None:
        report["errors"].append("missing kept_rows/final_kept_rows in quality gate summary")
    else:
        kept_rows = parse_int_like(kept_value)
        if kept_rows is None:
            report["errors"].append(f"{kept_key} has non-integer value {kept_value!r}")
        else:
            if kept_rows < target_kept_rows:
                report["errors"].append(
                    f"{kept_key}={kept_rows} below target_kept_rows={target_kept_rows}"
                )
            else:
                report["checks"].append(
                    f"{kept_key}={kept_rows} meets target_kept_rows={target_kept_rows}"
                )

    for requirement in QUALITY_GATE_REQUIREMENTS:
        key, value = first_present_value(summary, requirement["keys"])
        if value is None:
            report["errors"].append(f"missing metric for: {requirement['label']}")
            continue
        try:
            actual = normalize_rate(value)
        except (TypeError, ValueError):
            report["errors"].append(f"{key} has non-numeric value {value!r}")
            continue

        minimum = float(requirement["min"])
        if actual < minimum:
            report["errors"].append(f"{key}={actual:.4f} below required {minimum:.4f}")
        else:
            report["checks"].append(f"{key}={actual:.4f} passes {requirement['label']}")

    template_ok, template_issues = evaluate_template_distribution(summary)
    if template_ok:
        report["checks"].append("template distribution is within A/B/C target tolerance")
    else:
        report["errors"].extend(template_issues)

    report["summary"] = summary
    return len(report["errors"]) == 0, report


def enforce_quality_gate(
    quality_gate_path: Path,
    target_kept_rows: int,
    *,
    verbose: bool = True,
) -> tuple[bool, dict[str, Any]]:
    passed, report = evaluate_quality_gate(quality_gate_path, target_kept_rows)
    if verbose:
        if passed:
            print(f"quality gate passed: {quality_gate_path}")
            for message in report.get("checks", []):
                print(f"  - {message}")
        else:
            print(f"quality gate failed: {quality_gate_path}", file=sys.stderr)
            for message in report.get("errors", []):
                print(f"  - {message}", file=sys.stderr)
    return passed, report


def get_job_id(args: argparse.Namespace) -> str:
    if args.job_id:
        return args.job_id
    manifest = read_json_file(args.manifest_path)
    job_id = manifest.get("job", {}).get("id")
    if not job_id:
        raise ValueError("job ID missing. Pass --job-id or create a job first.")
    return str(job_id)


def get_training_file_id(args: argparse.Namespace) -> str:
    if args.training_file_id:
        return args.training_file_id
    manifest = read_json_file(args.manifest_path)
    file_id = manifest.get("uploaded_files", {}).get("training", {}).get("id")
    if not file_id:
        raise ValueError("training file ID missing. Pass --training-file-id or run upload first.")
    return str(file_id)


def get_validation_file_id(args: argparse.Namespace) -> str:
    if args.validation_file_id:
        return args.validation_file_id
    manifest = read_json_file(args.manifest_path)
    file_id = manifest.get("uploaded_files", {}).get("validation", {}).get("id")
    if not file_id:
        raise ValueError("validation file ID missing. Pass --validation-file-id or run upload first.")
    return str(file_id)


def resolve_wandb_project(project_arg: str | None) -> str:
    if project_arg and project_arg.strip():
        return project_arg.strip()
    env_project = os.environ.get("WANDB_PROJECT", "").strip()
    if env_project:
        return env_project
    return DEFAULT_WANDB_PROJECT


def maybe_wandb_integrations(
    args: argparse.Namespace,
) -> tuple[list[dict[str, str]] | None, str | None]:
    api_key = os.environ.get(args.wandb_api_key_env, "").strip()
    if not api_key:
        if args.wandb_project:
            raise ValueError(
                f"--wandb-project was set but {args.wandb_api_key_env} is missing or empty"
            )
        return None, None
    project = resolve_wandb_project(args.wandb_project)
    return ([{"project": project, "api_key": api_key}], project)


def print_wandb_mode(project: str | None) -> None:
    if project:
        print(f"W&B integration enabled: project={project}")
    else:
        print("W&B integration disabled: WANDB_API_KEY not set")


def print_job_summary(prefix: str, job_payload: dict[str, Any]) -> None:
    print(f"{prefix}:")
    print(f"  id: {job_payload.get('id')}")
    print(f"  model: {job_payload.get('model')}")
    print(f"  status: {job_payload.get('status')}")
    if job_payload.get("fine_tuned_model"):
        print(f"  fine_tuned_model: {job_payload.get('fine_tuned_model')}")
    if job_payload.get("suffix"):
        print(f"  suffix: {job_payload.get('suffix')}")


def cmd_upload(args: argparse.Namespace) -> int:
    require_file(args.train_path)
    require_file(args.valid_path)
    client = create_client()

    with args.train_path.open("rb") as train_handle:
        train_upload = client.files.upload(
            purpose="fine-tune",
            file={
                "file_name": args.train_path.name,
                "content": train_handle,
            },
        )

    with args.valid_path.open("rb") as valid_handle:
        valid_upload = client.files.upload(
            purpose="fine-tune",
            file={
                "file_name": args.valid_path.name,
                "content": valid_handle,
            },
        )

    train_payload = normalize_response(train_upload)
    valid_payload = normalize_response(valid_upload)
    print(f"training file uploaded: {train_payload.get('id')} ({train_payload.get('filename')})")
    print(f"validation file uploaded: {valid_payload.get('id')} ({valid_payload.get('filename')})")

    update_manifest(
        args.manifest_path,
        {
            "uploaded_files": {
                "training": {
                    "id": train_payload.get("id"),
                    "filename": train_payload.get("filename"),
                    "size_bytes": train_payload.get("size_bytes"),
                    "purpose": train_payload.get("purpose"),
                    "uploaded_at": utc_now_iso(),
                },
                "validation": {
                    "id": valid_payload.get("id"),
                    "filename": valid_payload.get("filename"),
                    "size_bytes": valid_payload.get("size_bytes"),
                    "purpose": valid_payload.get("purpose"),
                    "uploaded_at": utc_now_iso(),
                },
            },
            "dataset_paths": {
                "train": str(args.train_path),
                "validation": str(args.valid_path),
            },
        },
    )
    print(f"manifest updated: {args.manifest_path}")
    return 0


def cmd_create_job(args: argparse.Namespace) -> int:
    if args.auto_start and not args.skip_quality_gate:
        passed, report = enforce_quality_gate(args.quality_gate_path, args.target_kept_rows)
        update_manifest(
            args.manifest_path,
            {
                "quality_gate": {
                    "path": str(args.quality_gate_path),
                    "target_kept_rows": args.target_kept_rows,
                    "passed": passed,
                    "report": report,
                }
            },
        )
        if not passed:
            print("refusing create-job --auto-start because quality gate failed", file=sys.stderr)
            return 2

    training_file_id = get_training_file_id(args)
    validation_file_id = get_validation_file_id(args)
    integrations, wandb_project = maybe_wandb_integrations(args)
    print_wandb_mode(wandb_project)
    client = create_client()

    create_kwargs: dict[str, Any] = {
        "model": args.model,
        "training_files": [{"file_id": training_file_id, "weight": 1}],
        "validation_files": [validation_file_id],
        "hyperparameters": {
            "training_steps": args.training_steps,
            "learning_rate": args.learning_rate,
        },
        "auto_start": args.auto_start,
        "invalid_sample_skip_percentage": args.invalid_sample_skip_percentage,
    }
    if args.suffix:
        create_kwargs["suffix"] = args.suffix
    if integrations:
        create_kwargs["integrations"] = integrations

    try:
        created = client.fine_tuning.jobs.create(**create_kwargs)
    except SDKError as exc:
        status_code = getattr(getattr(exc, "raw_response", None), "status_code", None)
        if status_code == 409:
            print("job creation conflict (HTTP 409): similar job may already exist", file=sys.stderr)
            print(f"error: {exc}", file=sys.stderr)
            jobs = client.fine_tuning.jobs.list(
                page=0,
                page_size=20,
                created_by_me=True,
                model=args.model,
                suffix=args.suffix,
            )
            for job in jobs.data:
                print(
                    f"- existing job id={job.id} status={job.status} model={job.model} suffix={job.suffix}",
                    file=sys.stderr,
                )
            return 2
        raise

    job_payload = normalize_response(created)
    print_job_summary("job created", job_payload)

    updates = {
        "job": {
            "id": job_payload.get("id"),
            "status": job_payload.get("status"),
            "model": job_payload.get("model"),
            "suffix": job_payload.get("suffix"),
            "auto_start": args.auto_start,
            "training_file_id": training_file_id,
            "validation_file_id": validation_file_id,
            "created_at": utc_now_iso(),
            "raw": job_payload,
        },
        "hyperparameters": {
            "training_steps": args.training_steps,
            "learning_rate": args.learning_rate,
            "invalid_sample_skip_percentage": args.invalid_sample_skip_percentage,
        },
        "wandb": {
            "project": wandb_project,
            "api_key_env": args.wandb_api_key_env if wandb_project else None,
        },
    }
    update_manifest(args.manifest_path, updates)
    print(f"manifest updated: {args.manifest_path}")
    return 0


def cmd_start_job(args: argparse.Namespace) -> int:
    if not args.skip_quality_gate:
        passed, report = enforce_quality_gate(args.quality_gate_path, args.target_kept_rows)
        update_manifest(
            args.manifest_path,
            {
                "quality_gate": {
                    "path": str(args.quality_gate_path),
                    "target_kept_rows": args.target_kept_rows,
                    "passed": passed,
                    "report": report,
                }
            },
        )
        if not passed:
            print("refusing start-job because quality gate failed", file=sys.stderr)
            return 2

    job_id = get_job_id(args)
    client = create_client()
    started = client.fine_tuning.jobs.start(job_id=job_id)
    job_payload = normalize_response(started)
    print_job_summary("job start requested", job_payload)

    update_manifest(
        args.manifest_path,
        {
            "job": {
                "id": job_id,
                "status": job_payload.get("status"),
                "start_requested_at": utc_now_iso(),
                "raw": job_payload,
            }
        },
    )
    print(f"manifest updated: {args.manifest_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    job_id = get_job_id(args)
    client = create_client()
    job = client.fine_tuning.jobs.get(job_id=job_id)
    job_payload = normalize_response(job)

    if args.json:
        print(json.dumps(job_payload, indent=2, ensure_ascii=True))
    else:
        print_job_summary("job status", job_payload)
        if job_payload.get("trained_tokens") is not None:
            print(f"  trained_tokens: {job_payload.get('trained_tokens')}")
        if job_payload.get("created_at"):
            print(f"  created_at: {job_payload.get('created_at')}")
        if job_payload.get("modified_at"):
            print(f"  modified_at: {job_payload.get('modified_at')}")

    update_manifest(
        args.manifest_path,
        {
            "job": {
                "id": job_id,
                "status": job_payload.get("status"),
                "fine_tuned_model": job_payload.get("fine_tuned_model"),
                "last_status_check_at": utc_now_iso(),
                "raw": job_payload,
            }
        },
    )
    return 0


def cmd_list_jobs(args: argparse.Namespace) -> int:
    client = create_client()
    list_kwargs: dict[str, Any] = {
        "page": args.page,
        "page_size": args.page_size,
        "created_by_me": args.created_by_me,
    }
    if args.model:
        list_kwargs["model"] = args.model
    if args.status:
        list_kwargs["status"] = args.status
    if args.suffix:
        list_kwargs["suffix"] = args.suffix

    jobs = client.fine_tuning.jobs.list(**list_kwargs)

    if args.json:
        payload = normalize_response(jobs)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    print(f"jobs total={jobs.total} returned={len(jobs.data)}")
    for job in jobs.data:
        print(
            f"- id={job.id} status={job.status} model={job.model} "
            f"suffix={job.suffix or '-'} fine_tuned_model={job.fine_tuned_model or '-'}"
        )
    return 0


def cmd_cancel_job(args: argparse.Namespace) -> int:
    job_id = get_job_id(args)
    client = create_client()
    cancelled = client.fine_tuning.jobs.cancel(job_id=job_id)
    job_payload = normalize_response(cancelled)
    print_job_summary("job cancellation requested", job_payload)

    update_manifest(
        args.manifest_path,
        {
            "job": {
                "id": job_id,
                "status": job_payload.get("status"),
                "cancel_requested_at": utc_now_iso(),
                "raw": job_payload,
            }
        },
    )
    print(f"manifest updated: {args.manifest_path}")
    return 0


def cmd_check_quality_gate(args: argparse.Namespace) -> int:
    passed, report = enforce_quality_gate(
        args.quality_gate_path,
        args.target_kept_rows,
        verbose=not args.json,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    update_manifest(
        args.manifest_path,
        {
            "quality_gate": {
                "path": str(args.quality_gate_path),
                "target_kept_rows": args.target_kept_rows,
                "passed": passed,
                "report": report,
            }
        },
    )
    return 0 if passed else 2


def cmd_wait(args: argparse.Namespace) -> int:
    job_id = get_job_id(args)
    client = create_client()
    start_monotonic = time.monotonic()
    interval = max(1.0, float(args.interval_seconds))
    max_interval = max(interval, float(args.max_interval_seconds))
    backoff = max(1.0, float(args.backoff))
    last_status: str | None = None

    while True:
        job = client.fine_tuning.jobs.get(job_id=job_id)
        job_payload = normalize_response(job)
        status = str(job_payload.get("status"))

        if status != last_status:
            print(
                f"{utc_now_iso()} job={job_id} status={status} "
                f"fine_tuned_model={job_payload.get('fine_tuned_model') or '-'}"
            )
            last_status = status

        update_manifest(
            args.manifest_path,
            {
                "job": {
                    "id": job_id,
                    "status": status,
                    "fine_tuned_model": job_payload.get("fine_tuned_model"),
                    "last_status_check_at": utc_now_iso(),
                    "raw": job_payload,
                }
            },
        )

        if status in TERMINAL_JOB_STATUSES:
            if status == "SUCCESS":
                return 0
            return 2

        elapsed = time.monotonic() - start_monotonic
        if elapsed >= float(args.max_wait_seconds):
            print(
                f"timeout waiting for terminal status after {int(elapsed)} seconds",
                file=sys.stderr,
            )
            return 3

        remaining = float(args.max_wait_seconds) - elapsed
        sleep_for = min(interval, max(1.0, remaining))
        time.sleep(sleep_for)
        interval = min(max_interval, interval * backoff)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="Upload train/validation JSONL files.")
    upload.add_argument("--train-path", type=Path, default=Path("data/train_filtered.jsonl"))
    upload.add_argument("--valid-path", type=Path, default=Path("data/valid_filtered.jsonl"))
    upload.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    upload.set_defaults(func=cmd_upload)

    create_job = subparsers.add_parser("create-job", help="Create fine-tuning job.")
    create_job.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    create_job.add_argument("--training-file-id", type=str)
    create_job.add_argument("--validation-file-id", type=str)
    create_job.add_argument("--model", type=str, default=DEFAULT_MODEL)
    create_job.add_argument("--training-steps", type=int, default=DEFAULT_TRAIN_STEPS)
    create_job.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    create_job.add_argument("--invalid-sample-skip-percentage", type=float, default=0.0)
    create_job.add_argument("--suffix", type=str, default=DEFAULT_SUFFIX)
    create_job.add_argument("--auto-start", action="store_true")
    create_job.add_argument(
        "--wandb-project",
        type=str,
        default=None,
        help=(
            "W&B project override. If omitted and WANDB_API_KEY is set, "
            "uses WANDB_PROJECT or defaults to recipe-remix."
        ),
    )
    create_job.add_argument("--wandb-api-key-env", type=str, default="WANDB_API_KEY")
    create_job.add_argument(
        "--quality-gate-path",
        type=Path,
        default=DEFAULT_QUALITY_GATE_PATH,
        help="Path to dataset quality gate summary JSON.",
    )
    create_job.add_argument(
        "--target-kept-rows",
        type=int,
        default=DEFAULT_TARGET_KEPT_ROWS,
        help="Minimum kept rows required by quality gate policy.",
    )
    create_job.add_argument(
        "--skip-quality-gate",
        action="store_true",
        help="Bypass quality gate enforcement (not recommended).",
    )
    create_job.set_defaults(func=cmd_create_job)

    start_job = subparsers.add_parser("start-job", help="Start existing fine-tuning job.")
    start_job.add_argument("--job-id", type=str)
    start_job.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    start_job.add_argument(
        "--quality-gate-path",
        type=Path,
        default=DEFAULT_QUALITY_GATE_PATH,
        help="Path to dataset quality gate summary JSON.",
    )
    start_job.add_argument(
        "--target-kept-rows",
        type=int,
        default=DEFAULT_TARGET_KEPT_ROWS,
        help="Minimum kept rows required by quality gate policy.",
    )
    start_job.add_argument(
        "--skip-quality-gate",
        action="store_true",
        help="Bypass quality gate enforcement (not recommended).",
    )
    start_job.set_defaults(func=cmd_start_job)

    status = subparsers.add_parser("status", help="Fetch job status.")
    status.add_argument("--job-id", type=str)
    status.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    status.add_argument("--json", action="store_true", help="Print full job payload as JSON.")
    status.set_defaults(func=cmd_status)

    list_jobs = subparsers.add_parser("list-jobs", help="List fine-tuning jobs.")
    list_jobs.add_argument("--model", type=str, default=None)
    list_jobs.add_argument("--status", type=str, default=None)
    list_jobs.add_argument("--suffix", type=str, default=None)
    list_jobs.add_argument("--page", type=int, default=0)
    list_jobs.add_argument("--page-size", type=int, default=20)
    list_jobs.add_argument(
        "--created-by-me",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Filter jobs to current user (default: true). Use --no-created-by-me to disable.",
    )
    list_jobs.add_argument("--json", action="store_true", help="Print full list payload as JSON.")
    list_jobs.set_defaults(func=cmd_list_jobs)

    cancel = subparsers.add_parser("cancel-job", help="Cancel a fine-tuning job.")
    cancel.add_argument("--job-id", type=str)
    cancel.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    cancel.set_defaults(func=cmd_cancel_job)

    check_quality_gate = subparsers.add_parser(
        "check-quality-gate",
        help="Validate dataset quality gate summary against plan thresholds.",
    )
    check_quality_gate.add_argument(
        "--quality-gate-path",
        type=Path,
        default=DEFAULT_QUALITY_GATE_PATH,
    )
    check_quality_gate.add_argument(
        "--target-kept-rows",
        type=int,
        default=DEFAULT_TARGET_KEPT_ROWS,
    )
    check_quality_gate.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    check_quality_gate.add_argument(
        "--json",
        action="store_true",
        help="Print quality gate report as JSON.",
    )
    check_quality_gate.set_defaults(func=cmd_check_quality_gate)

    wait = subparsers.add_parser(
        "wait",
        help="Poll a fine-tuning job until it reaches terminal status.",
    )
    wait.add_argument("--job-id", type=str)
    wait.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    wait.add_argument(
        "--interval-seconds",
        type=float,
        default=20.0,
        help="Initial polling interval in seconds.",
    )
    wait.add_argument(
        "--max-interval-seconds",
        type=float,
        default=120.0,
        help="Maximum polling interval in seconds.",
    )
    wait.add_argument(
        "--backoff",
        type=float,
        default=1.2,
        help="Polling interval multiplier per iteration.",
    )
    wait.add_argument(
        "--max-wait-seconds",
        type=int,
        default=3600,
        help="Maximum total wait time before timing out.",
    )
    wait.set_defaults(func=cmd_wait)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (SDKError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
