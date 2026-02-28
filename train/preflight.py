#!/usr/bin/env python3
"""Preflight validation for Mistral fine-tuning JSONL files.

Quick start:
  uv run python train/preflight.py \
    --train-path data/train_filtered.jsonl \
    --valid-path data/valid_filtered.jsonl

Write summary elsewhere:
  uv run python train/preflight.py \
    --summary-path artifacts/preflight_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_ROLES = {"system", "user", "assistant", "tool"}
DEFAULT_MAX_VALIDATION_BYTES = 1_048_576


@dataclass
class FileStats:
    path: str
    exists: bool
    size_bytes: int
    line_count: int
    record_count: int
    assistant_message_count: int
    parse_error_count: int
    schema_error_count: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_message(message: Any, line_number: int, role_index: int, file_path: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(message, dict):
        errors.append(
            f"{file_path}:{line_number} messages[{role_index}] must be an object, got {type(message).__name__}"
        )
        return errors

    role = message.get("role")
    if role not in VALID_ROLES:
        errors.append(
            f"{file_path}:{line_number} messages[{role_index}].role must be one of {sorted(VALID_ROLES)}, got {role!r}"
        )

    has_content = "content" in message
    has_tool_calls = "tool_calls" in message
    if not has_content and not has_tool_calls:
        errors.append(
            f"{file_path}:{line_number} messages[{role_index}] must include content or tool_calls"
        )

    if role != "assistant" and has_tool_calls:
        errors.append(
            f"{file_path}:{line_number} messages[{role_index}] tool_calls is only valid for assistant role"
        )

    if has_content:
        content = message["content"]
        if not isinstance(content, (str, list)):
            errors.append(
                f"{file_path}:{line_number} messages[{role_index}].content must be string or list, got {type(content).__name__}"
            )

    return errors


def validate_record(record: Any, line_number: int, file_path: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    assistant_messages = 0

    if not isinstance(record, dict):
        return [f"{file_path}:{line_number} top-level JSON must be an object"], assistant_messages

    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        return [f"{file_path}:{line_number} must contain non-empty messages list"], assistant_messages

    for i, message in enumerate(messages):
        message_errors = validate_message(message, line_number, i, file_path)
        errors.extend(message_errors)
        if isinstance(message, dict) and message.get("role") == "assistant":
            assistant_messages += 1

    if assistant_messages == 0:
        errors.append(f"{file_path}:{line_number} must include at least one assistant message")

    return errors, assistant_messages


def validate_jsonl_file(file_path: Path) -> tuple[FileStats, list[str]]:
    if not file_path.exists():
        stats = FileStats(
            path=str(file_path),
            exists=False,
            size_bytes=0,
            line_count=0,
            record_count=0,
            assistant_message_count=0,
            parse_error_count=0,
            schema_error_count=0,
        )
        return stats, [f"{file_path} does not exist"]

    parse_errors: list[str] = []
    schema_errors: list[str] = []
    line_count = 0
    record_count = 0
    assistant_message_count = 0

    with file_path.open("r", encoding="utf-8") as handle:
        for line_count, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                schema_errors.append(f"{file_path}:{line_count} empty line is not allowed in JSONL")
                continue

            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                parse_errors.append(f"{file_path}:{line_count} JSON parse error: {exc.msg}")
                continue

            record_count += 1
            errors, assistant_count = validate_record(record, line_count, file_path)
            assistant_message_count += assistant_count
            schema_errors.extend(errors)

    stats = FileStats(
        path=str(file_path),
        exists=True,
        size_bytes=file_path.stat().st_size,
        line_count=line_count,
        record_count=record_count,
        assistant_message_count=assistant_message_count,
        parse_error_count=len(parse_errors),
        schema_error_count=len(schema_errors),
    )
    return stats, parse_errors + schema_errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-path",
        type=Path,
        default=Path("data/train_filtered.jsonl"),
        help="Path to training JSONL file.",
    )
    parser.add_argument(
        "--valid-path",
        type=Path,
        default=Path("data/valid_filtered.jsonl"),
        help="Path to validation JSONL file.",
    )
    parser.add_argument(
        "--max-validation-bytes",
        type=int,
        default=DEFAULT_MAX_VALIDATION_BYTES,
        help="Maximum validation file size in bytes (default: 1 MiB).",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=Path("artifacts/preflight_summary.json"),
        help="Where to write JSON summary.",
    )
    parser.add_argument(
        "--show-errors",
        type=int,
        default=20,
        help="How many validation errors to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    train_stats, train_errors = validate_jsonl_file(args.train_path)
    valid_stats, valid_errors = validate_jsonl_file(args.valid_path)

    validation_size_ok = valid_stats.exists and valid_stats.size_bytes <= args.max_validation_bytes
    size_error = []
    if valid_stats.exists and not validation_size_ok:
        size_error.append(
            f"{args.valid_path} is {valid_stats.size_bytes} bytes, exceeds max {args.max_validation_bytes} bytes"
        )

    non_empty_errors = []
    if train_stats.exists and train_stats.record_count == 0:
        non_empty_errors.append(f"{args.train_path} has zero records; training dataset must be non-empty")
    if valid_stats.exists and valid_stats.record_count == 0:
        non_empty_errors.append(f"{args.valid_path} has zero records; validation dataset must be non-empty")

    all_errors = train_errors + valid_errors + size_error + non_empty_errors
    passed = len(all_errors) == 0

    summary = {
        "generated_at": utc_now_iso(),
        "pass": passed,
        "checks": {
            "validation_size_limit_bytes": args.max_validation_bytes,
            "validation_size_ok": validation_size_ok,
        },
        "train": asdict(train_stats),
        "validation": asdict(valid_stats),
        "error_count": len(all_errors),
        "errors": all_errors[: max(0, args.show_errors)],
    }

    args.summary_path.parent.mkdir(parents=True, exist_ok=True)
    with args.summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=True)
        handle.write("\n")

    print(f"preflight summary written to {args.summary_path}")
    print(
        f"train records={train_stats.record_count} validation records={valid_stats.record_count} errors={len(all_errors)}"
    )

    if all_errors:
        preview_count = min(len(all_errors), max(0, args.show_errors))
        print(f"showing {preview_count} error(s):", file=sys.stderr)
        for message in all_errors[:preview_count]:
            print(f"- {message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
