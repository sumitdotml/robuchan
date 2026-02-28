#!/usr/bin/env python3
"""Watch fine-tuning job status and persist periodic snapshots for handoff.

Examples:
  # watch job from manifest and write snapshots
  uv run python scripts/watch_job.py

  # watch an explicit job id every 20s for up to 90 minutes
  uv run python scripts/watch_job.py \
    --job-id ftjob-xxxx \
    --interval-seconds 20 \
    --max-wait-seconds 5400

  # reset output file before watching
  uv run python scripts/watch_job.py \
    --reset-output \
    --output-path artifacts/job_status_history.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_JOB_STATUSES = {"SUCCESS", "FAILED", "FAILED_VALIDATION", "CANCELLED"}
REPO_ROOT = Path(__file__).resolve().parents[1]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", type=str, default=None, help="Optional explicit job id.")
    parser.add_argument("--manifest-path", type=Path, default=Path("artifacts/ft_run_manifest.json"))
    parser.add_argument("--output-path", type=Path, default=Path("artifacts/job_status_history.jsonl"))
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--backoff", type=float, default=1.3)
    parser.add_argument("--max-interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-wait-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--stop-on-terminal",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stop when a terminal status is observed.",
    )
    parser.add_argument("--reset-output", action="store_true", help="Remove existing output file before watching.")
    return parser.parse_args()


def fetch_status(job_id: str | None, manifest_path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "train/finetune.py"),
        "status",
        "--json",
        "--manifest-path",
        str(manifest_path),
    ]
    if job_id:
        command.extend(["--job-id", job_id])

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if completed.returncode != 0:
        details = "\n".join(part for part in (completed.stderr.strip(), completed.stdout.strip()) if part)
        raise RuntimeError(details or "status command failed")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"status output was not valid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("status payload must be a JSON object")
    return payload


def append_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=True))
        handle.write("\n")


def main() -> int:
    args = parse_args()

    if args.reset_output and args.output_path.exists():
        args.output_path.unlink()

    start_monotonic = time.monotonic()
    interval = max(1.0, float(args.interval_seconds))
    max_interval = max(1.0, float(args.max_interval_seconds))
    backoff = max(1.0, float(args.backoff))

    poll_count = 0
    while True:
        poll_count += 1
        captured_at = utc_now_iso()
        try:
            payload = fetch_status(job_id=args.job_id, manifest_path=args.manifest_path)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        status = str(payload.get("status") or "UNKNOWN")
        job_id = str(payload.get("id") or args.job_id or "")
        snapshot = {
            "captured_at": captured_at,
            "poll_index": poll_count,
            "status": status,
            "job_id": job_id or None,
            "payload": payload,
        }
        append_snapshot(args.output_path, snapshot)

        print(f"[{poll_count}] {captured_at} status={status} job_id={job_id or '-'}")

        if args.stop_on_terminal and status in TERMINAL_JOB_STATUSES:
            print(f"terminal status reached: {status}")
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


if __name__ == "__main__":
    raise SystemExit(main())
