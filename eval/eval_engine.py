#!/usr/bin/env python3
"""Shared eval engine for deterministic checks and optional judge scoring.

Use `eval/evaluate.py` and `eval/baseline.py` as CLI entrypoints.
This module contains reusable parser and run logic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, cast

from mistralai import Mistral
from mistralai.models import chatcompletionrequest
from mistralai.models.sdkerror import SDKError


DEFAULT_CONSTRAINTS_PATH = Path("eval/constraints.json")
DEFAULT_OUTPUT_PATH = Path("artifacts/eval_metrics.json")
DEFAULT_ROWS_OUTPUT_PATH = Path("artifacts/eval_rows.jsonl")
DEFAULT_MANIFEST_PATH = Path("artifacts/ft_run_manifest.json")
DEFAULT_JUDGE_MODEL = "mistral-large-latest"
DEFAULT_EVAL_MAX_TOKENS = 1400
DEFAULT_JUDGE_MAX_TOKENS = 700
DEFAULT_WANDB_PROJECT = "recipe-remix"

SECTION_HEADERS = (
    "substitution plan",
    "adapted ingredients",
    "adapted steps",
    "flavor preservation notes",
    "constraint check",
)
SCAN_SECTION_HEADERS = ("adapted ingredients", "adapted steps")
SECTION_HEADER_PATTERN = re.compile(
    r"(?im)^\s{0,3}(?:#{1,6}\s*)?"
    r"(substitution plan|adapted ingredients|adapted steps|flavor preservation notes|constraint check)"
    r"\s*:?\s*$"
)
ChatMessages = list[chatcompletionrequest.MessagesTypedDict]


@dataclass
class EvalExample:
    row_id: str
    restrictions: list[str]
    messages: ChatMessages
    source_user_text: str
    gold_assistant: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_constraint_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


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
                raise ValueError(f"{path}:{line_number} invalid JSONL: {exc.msg}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_number} row must be a JSON object")
            rows.append(obj)
    return rows


def normalize_messages(messages: Any) -> ChatMessages:
    if not isinstance(messages, list) or not messages:
        raise ValueError("row missing non-empty messages list")
    normalized: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        normalized_item = {"role": role}
        if "content" in item:
            normalized_item["content"] = item["content"]
        if "tool_calls" in item:
            normalized_item["tool_calls"] = item["tool_calls"]
        if "tool_call_id" in item:
            normalized_item["tool_call_id"] = item["tool_call_id"]
        normalized.append(normalized_item)
    if not normalized:
        raise ValueError("messages list had no valid role/content entries")
    return cast(ChatMessages, normalized)


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts).strip()
    return ""


def extract_restrictions(row: dict[str, Any], messages: ChatMessages) -> list[str]:
    candidates: list[str] = []

    for key in ("target_restrictions", "restrictions", "target_constraints"):
        value = row.get(key)
        if isinstance(value, list):
            candidates.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            candidates.extend(part.strip() for part in value.split(",") if part.strip())

    if candidates:
        deduped = []
        seen = set()
        for item in candidates:
            norm = normalize_constraint_name(item)
            if norm and norm not in seen:
                deduped.append(item)
                seen.add(norm)
        return deduped

    user_texts = [
        content_to_text(message.get("content"))
        for message in messages
        if message.get("role") == "user"
    ]
    combined = "\n".join(text for text in user_texts if text)
    if not combined:
        return []

    restrictions_line = re.search(r"(?im)^restrictions\s*:\s*(.+)$", combined)
    if restrictions_line:
        values = [part.strip() for part in restrictions_line.group(1).split(",") if part.strip()]
        return values

    categories_match = re.search(r"(?is)categories\s*:\s*\[(.+?)\]", combined)
    if categories_match:
        quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", categories_match.group(1))
        values = [left or right for left, right in quoted]
        return [value.strip() for value in values if value.strip()]

    return []


def prepare_inference_messages(messages: ChatMessages) -> ChatMessages:
    prepared = [dict(message) for message in messages]
    if prepared and prepared[-1].get("role") == "assistant":
        prepared = prepared[:-1]
    if not any(message.get("role") == "user" for message in prepared):
        raise ValueError("inference messages must include at least one user role")
    return cast(ChatMessages, prepared)


def extract_user_text(messages: ChatMessages) -> str:
    user_blocks = []
    for message in messages:
        if message.get("role") == "user":
            block = content_to_text(message.get("content"))
            if block:
                user_blocks.append(block)
    return "\n\n".join(user_blocks).strip()


def extract_gold_assistant(messages: ChatMessages) -> str | None:
    if not messages:
        return None
    last = messages[-1]
    if last.get("role") != "assistant":
        return None
    text = content_to_text(last.get("content"))
    return text or None


def parse_examples(rows: list[dict[str, Any]]) -> list[EvalExample]:
    examples: list[EvalExample] = []
    for index, row in enumerate(rows):
        row_id = str(
            row.get("row_id")
            or row.get("source_recipe_id")
            or row.get("id")
            or f"row_{index + 1}"
        )
        messages = normalize_messages(row.get("messages"))
        restrictions = extract_restrictions(row, messages)
        source_user_text = extract_user_text(messages)
        gold_assistant = extract_gold_assistant(messages)
        inference_messages = prepare_inference_messages(messages)

        examples.append(
            EvalExample(
                row_id=row_id,
                restrictions=restrictions,
                messages=inference_messages,
                source_user_text=source_user_text,
                gold_assistant=gold_assistant,
            )
        )
    return examples


def compile_constraint_patterns(constraints_payload: dict[str, Any]) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    compiled: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    for key, value in constraints_payload.items():
        if key.startswith("_"):
            continue
        if not isinstance(value, dict):
            continue
        banned = value.get("banned")
        if not isinstance(banned, list):
            continue
        constraint_name = normalize_constraint_name(key)
        entries: list[tuple[str, re.Pattern[str]]] = []
        for raw_term in banned:
            term = str(raw_term).strip().lower()
            if not term:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.IGNORECASE)
            entries.append((term, pattern))
        compiled[constraint_name] = entries
    return compiled


def check_required_sections(output_text: str) -> tuple[bool, list[str]]:
    parsed_sections = parse_output_sections(output_text)
    present_headers = {name for name, _, _, _ in parsed_sections}
    lower = output_text.lower()
    missing = [header for header in SECTION_HEADERS if header not in present_headers]
    if "..." in output_text:
        missing.append("placeholder_ellipsis")
    if "same as original" in lower:
        missing.append("placeholder_same_as_original")
    return len(missing) == 0, missing


def parse_output_sections(output_text: str) -> list[tuple[str, int, int, str]]:
    matches = list(SECTION_HEADER_PATTERN.finditer(output_text))
    parsed: list[tuple[str, int, int, str]] = []
    for index, match in enumerate(matches):
        name = match.group(1).strip().lower()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(output_text)
        parsed.append((name, match.start(), body_end, output_text[body_start:body_end].strip()))
    return parsed


def build_constraint_scan_text(output_text: str) -> tuple[str, str]:
    sections = parse_output_sections(output_text)
    if not sections:
        return output_text, "full_output"

    section_bodies = {name: body for name, _, _, body in sections}
    adapted_only = "\n\n".join(
        section_bodies.get(header, "")
        for header in SCAN_SECTION_HEADERS
        if section_bodies.get(header, "")
    ).strip()
    if adapted_only:
        return adapted_only, "adapted_sections_only"

    constraint_span = next(
        ((start, end) for name, start, end, _ in sections if name == "constraint check"),
        None,
    )
    if constraint_span is None:
        return output_text, "full_output"

    span_start, span_end = constraint_span
    without_constraint_check = f"{output_text[:span_start]}\n{output_text[span_end:]}".strip()
    if without_constraint_check:
        return without_constraint_check, "full_output_minus_constraint_check"
    return output_text, "full_output"


def deterministic_constraint_check(
    output_text: str,
    restrictions: list[str],
    compiled_constraints: dict[str, list[tuple[str, re.Pattern[str]]]],
) -> dict[str, Any]:
    scan_text, scan_mode = build_constraint_scan_text(output_text)
    violations: list[dict[str, Any]] = []
    unknown_restrictions: list[str] = []
    checked_restrictions = 0

    for raw_restriction in restrictions:
        normalized = normalize_constraint_name(raw_restriction)
        banned_entries = compiled_constraints.get(normalized)
        if not banned_entries:
            unknown_restrictions.append(raw_restriction)
            continue
        checked_restrictions += 1
        matched_terms = sorted({term for term, pattern in banned_entries if pattern.search(scan_text)})
        if matched_terms:
            violations.append(
                {
                    "restriction": raw_restriction,
                    "normalized_restriction": normalized,
                    "matched_terms": matched_terms,
                }
            )

    constraint_pass: bool | None
    if checked_restrictions == 0:
        constraint_pass = None
    else:
        constraint_pass = len(violations) == 0

    return {
        "checked_restrictions": checked_restrictions,
        "unknown_restrictions": unknown_restrictions,
        "violations": violations,
        "constraint_pass": constraint_pass,
        "scan_mode": scan_mode,
    }


def extract_text_from_chat_response(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return content_to_text(message.get("content"))


def usage_to_tokens(response_payload: dict[str, Any]) -> tuple[int, int]:
    usage = response_payload.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return prompt_tokens, completion_tokens


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    candidates = re.findall(r"\{[\s\S]*\}", text)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def score_with_judge(
    client: Mistral | None,
    judge_model: str,
    restrictions: list[str],
    source_user_text: str,
    model_output: str,
    max_tokens: int,
    temperature: float,
    dry_run: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if dry_run:
        mock = {
            "compliance": 7,
            "flavor_fidelity": 7,
            "dish_identity_preservation": 7,
            "explanation_quality": 7,
            "overall_score": 7.0,
            "verdict": "PASS",
            "notes": "dry_run mock judge output",
        }
        return mock, {"prompt_tokens": 0, "completion_tokens": 0}

    judge_system_message: chatcompletionrequest.SystemMessageTypedDict = {
        "role": "system",
        "content": (
            "You are an expert evaluator for recipe adaptation outputs. "
            "Score strictly and return JSON only."
        ),
    }
    judge_user_message: chatcompletionrequest.UserMessageTypedDict = {
        "role": "user",
        "content": (
            "Evaluate the model output.\n\n"
            f"Restrictions: {', '.join(restrictions) if restrictions else '(not provided)'}\n\n"
            f"Original user request:\n{source_user_text}\n\n"
            f"Model output:\n{model_output}\n\n"
            "Return JSON with keys: compliance (1-10), flavor_fidelity (1-10), "
            "dish_identity_preservation (1-10), explanation_quality (1-10), "
            "overall_score (float 1-10), verdict (PASS/FAIL), notes (string)."
        ),
    }
    judge_messages: ChatMessages = [judge_system_message, judge_user_message]

    if client is None:
        raise ValueError("client is required when judge scoring is enabled")

    response = client.chat.complete(
        model=judge_model,
        messages=judge_messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    payload = response.model_dump(mode="json")
    raw_text = extract_text_from_chat_response(payload)
    parsed = extract_first_json_object(raw_text)
    prompt_tokens, completion_tokens = usage_to_tokens(payload)
    return parsed, {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}


def infer_output(
    client: Mistral | None,
    model: str,
    messages: ChatMessages,
    max_tokens: int,
    temperature: float,
    dry_run: bool,
) -> tuple[str, int, int]:
    if dry_run:
        mock = (
            "Substitution Plan:\n- mock ingredient -> mock replacement (dry run)\n\n"
            "Adapted Ingredients:\n- 200g mock ingredient\n\n"
            "Adapted Steps:\n1) Cook mock ingredient.\n\n"
            "Flavor Preservation Notes:\n- mock umami retention.\n- mock heat retention.\n- mock texture retention.\n\n"
            "Constraint Check:\n- dry run only."
        )
        return mock, 0, 0

    if client is None:
        raise ValueError("client is required for non-dry-run inference")

    response = client.chat.complete(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    payload = response.model_dump(mode="json")
    text = extract_text_from_chat_response(payload)
    prompt_tokens, completion_tokens = usage_to_tokens(payload)
    return text, prompt_tokens, completion_tokens


def read_model_from_manifest(manifest_path: Path) -> str | None:
    if not manifest_path.exists():
        return None
    data = load_json(manifest_path)
    job = data.get("job")
    if not isinstance(job, dict):
        return None
    model = job.get("fine_tuned_model")
    if not isinstance(model, str) or not model.strip():
        return None
    return model.strip()


def to_optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def compute_summary(
    row_results: list[dict[str, Any]],
    eval_prompt_tokens: int,
    eval_completion_tokens: int,
    judge_prompt_tokens: int,
    judge_completion_tokens: int,
    judge_enabled: bool,
    prompt_price_per_1m: float,
    completion_price_per_1m: float,
    judge_prompt_price_per_1m: float,
    judge_completion_price_per_1m: float,
) -> dict[str, Any]:
    format_passes = [bool(row["format_pass"]) for row in row_results]
    checked_constraints = [
        bool(row["constraint_pass"])
        for row in row_results
        if row["constraint_pass"] is not None
    ]
    judge_scores: list[float] = []
    compliance_scores: list[float] = []
    judge_overall_invalid_rows = 0
    judge_compliance_invalid_rows = 0
    for row in row_results:
        judge = row.get("judge")
        if not isinstance(judge, dict):
            continue

        overall_raw = judge.get("overall_score")
        if overall_raw is not None:
            overall = to_optional_float(overall_raw)
            if overall is None:
                judge_overall_invalid_rows += 1
            else:
                judge_scores.append(overall)

        compliance_raw = judge.get("compliance")
        if compliance_raw is not None:
            compliance = to_optional_float(compliance_raw)
            if compliance is None:
                judge_compliance_invalid_rows += 1
            else:
                compliance_scores.append(compliance)
    judge_total_rows = len(row_results) if judge_enabled else 0
    judge_scored_rows = len(judge_scores) if judge_enabled else 0
    judge_compliance_scored_rows = len(compliance_scores) if judge_enabled else 0
    judge_missing_rows = (judge_total_rows - judge_scored_rows) if judge_enabled else 0
    judge_compliance_missing_rows = (
        judge_total_rows - judge_compliance_scored_rows
    ) if judge_enabled else 0

    eval_cost = (
        (eval_prompt_tokens / 1_000_000.0) * prompt_price_per_1m
        + (eval_completion_tokens / 1_000_000.0) * completion_price_per_1m
    )
    judge_cost = (
        (judge_prompt_tokens / 1_000_000.0) * judge_prompt_price_per_1m
        + (judge_completion_tokens / 1_000_000.0) * judge_completion_price_per_1m
    )

    return {
        "num_examples": len(row_results),
        "format_pass_rate": mean(format_passes) if format_passes else 0.0,
        "constraint_checked_rows": len(checked_constraints),
        "constraint_pass_rate": mean(checked_constraints) if checked_constraints else None,
        "judge_enabled": judge_enabled,
        "judge_scored_rows": judge_scored_rows,
        "judge_missing_rows": judge_missing_rows,
        "judge_overall_invalid_rows": judge_overall_invalid_rows if judge_enabled else 0,
        "judge_score_coverage": (
            judge_scored_rows / judge_total_rows if judge_total_rows else None
        ),
        "avg_judge_score": (
            mean(judge_scores) if judge_total_rows and judge_missing_rows == 0 else None
        ),
        "avg_judge_score_scored_rows": mean(judge_scores) if judge_scores else None,
        "judge_compliance_scored_rows": judge_compliance_scored_rows,
        "judge_compliance_missing_rows": judge_compliance_missing_rows,
        "judge_compliance_invalid_rows": judge_compliance_invalid_rows if judge_enabled else 0,
        "avg_judge_compliance": (
            mean(compliance_scores)
            if judge_total_rows and judge_compliance_missing_rows == 0
            else None
        ),
        "avg_judge_compliance_scored_rows": mean(compliance_scores) if compliance_scores else None,
        "tokens": {
            "eval_prompt_tokens": eval_prompt_tokens,
            "eval_completion_tokens": eval_completion_tokens,
            "judge_prompt_tokens": judge_prompt_tokens,
            "judge_completion_tokens": judge_completion_tokens,
        },
        "estimated_cost_usd": {
            "eval_cost": round(eval_cost, 6),
            "judge_cost": round(judge_cost, 6),
            "total_cost": round(eval_cost + judge_cost, 6),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_rows_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True))
            handle.write("\n")


def resolve_wandb_project(args: argparse.Namespace) -> str | None:
    if args.wandb_project and args.wandb_project.strip():
        return args.wandb_project.strip()
    if os.environ.get("WANDB_API_KEY", "").strip():
        env_project = os.environ.get("WANDB_PROJECT", "").strip()
        if env_project:
            return env_project
        return DEFAULT_WANDB_PROJECT
    return None


def maybe_log_to_wandb(
    args: argparse.Namespace,
    summary: dict[str, Any],
    row_results: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    project = resolve_wandb_project(args)
    if not project:
        return None, None

    try:
        import wandb
    except ImportError as exc:  # pragma: no cover - env-specific dependency
        raise ValueError(
            "WANDB_API_KEY is set so W&B logging is required, but the `wandb` package is not installed."
        ) from exc

    run = wandb.init(
        project=project,
        entity=args.wandb_entity or os.environ.get("WANDB_ENTITY"),
        name=args.wandb_run_name,
        config={
            "split_name": args.split_name,
            "model": args.model,
            "judge_model": None if args.disable_judge else args.judge_model,
            "input": str(args.input),
            "constraints_path": str(args.constraints_path),
        },
    )

    numeric_log = {
        "num_examples": summary["num_examples"],
        "format_pass_rate": summary["format_pass_rate"],
        "constraint_checked_rows": summary["constraint_checked_rows"],
        "constraint_pass_rate": summary["constraint_pass_rate"] or 0.0,
        "judge_scored_rows": summary["judge_scored_rows"],
        "judge_missing_rows": summary["judge_missing_rows"],
        "judge_score_coverage": summary["judge_score_coverage"] or 0.0,
        "avg_judge_score": summary["avg_judge_score"] or 0.0,
        "avg_judge_score_scored_rows": summary["avg_judge_score_scored_rows"] or 0.0,
        "avg_judge_compliance": summary["avg_judge_compliance"] or 0.0,
        "avg_judge_compliance_scored_rows": summary["avg_judge_compliance_scored_rows"] or 0.0,
        "eval_prompt_tokens": summary["tokens"]["eval_prompt_tokens"],
        "eval_completion_tokens": summary["tokens"]["eval_completion_tokens"],
        "judge_prompt_tokens": summary["tokens"]["judge_prompt_tokens"],
        "judge_completion_tokens": summary["tokens"]["judge_completion_tokens"],
        "estimated_total_cost_usd": summary["estimated_cost_usd"]["total_cost"],
    }
    wandb.log(numeric_log)

    table = wandb.Table(
        columns=[
            "row_id",
            "constraint_pass",
            "format_pass",
            "missing_sections",
            "unknown_restrictions",
            "judge_overall_score",
        ]
    )
    for row in row_results:
        table.add_data(
            row["row_id"],
            row["constraint_pass"],
            row["format_pass"],
            ",".join(row["missing_sections"]),
            ",".join(row["deterministic"]["unknown_restrictions"]),
            (row.get("judge") or {}).get("overall_score") if isinstance(row.get("judge"), dict) else None,
        )
    wandb.log({"eval_rows": table})

    run_url = run.url
    run.finish()
    return run_url, project


def build_parser(
    *,
    default_model: str | None,
    default_output_path: Path,
    default_rows_output_path: Path,
    default_split_name: str,
    allow_manifest_model: bool,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to evaluation JSONL split.")
    parser.add_argument("--split-name", type=str, default=default_split_name)
    parser.add_argument("--model", type=str, default=default_model)
    parser.add_argument("--constraints-path", type=Path, default=DEFAULT_CONSTRAINTS_PATH)
    parser.add_argument("--output-path", type=Path, default=default_output_path)
    parser.add_argument("--rows-output-path", type=Path, default=default_rows_output_path)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_EVAL_MAX_TOKENS)
    parser.add_argument("--disable-judge", action="store_true")
    parser.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--judge-temperature", type=float, default=0.0)
    parser.add_argument("--judge-max-tokens", type=int, default=DEFAULT_JUDGE_MAX_TOKENS)
    parser.add_argument("--prompt-price-per-1m", type=float, default=0.0)
    parser.add_argument("--completion-price-per-1m", type=float, default=0.0)
    parser.add_argument("--judge-prompt-price-per-1m", type=float, default=0.0)
    parser.add_argument("--judge-completion-price-per-1m", type=float, default=0.0)
    parser.add_argument(
        "--wandb-project",
        type=str,
        default=None,
        help=(
            "W&B project override. If omitted and WANDB_API_KEY is set, "
            "uses WANDB_PROJECT or defaults to recipe-remix."
        ),
    )
    parser.add_argument("--wandb-entity", type=str, default=None)
    parser.add_argument("--wandb-run-name", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    if allow_manifest_model:
        parser.add_argument(
            "--no-manifest-model",
            action="store_true",
            help="Do not fallback to artifacts/ft_run_manifest.json when --model is omitted.",
        )
    return parser


def resolve_model(args: argparse.Namespace, allow_manifest_model: bool) -> str:
    if args.model:
        return args.model
    if allow_manifest_model and not getattr(args, "no_manifest_model", False):
        manifest_model = read_model_from_manifest(args.manifest_path)
        if manifest_model:
            return manifest_model
    raise ValueError(
        "model is required (pass --model, or store fine_tuned_model in artifacts/ft_run_manifest.json)"
    )


def run(
    args: argparse.Namespace,
    *,
    allow_manifest_model: bool,
) -> int:
    model = resolve_model(args, allow_manifest_model=allow_manifest_model)
    args.model = model

    raw_rows = load_jsonl(args.input)
    if args.limit is not None:
        raw_rows = raw_rows[: max(0, args.limit)]
    if not raw_rows:
        raise ValueError(f"no rows found in {args.input}")

    examples = parse_examples(raw_rows)
    constraints_payload = load_json(args.constraints_path)
    compiled_constraints = compile_constraint_patterns(constraints_payload)

    client: Mistral | None = None
    if not args.dry_run:
        api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is required unless --dry-run is set")
        client = Mistral(api_key=api_key)

    eval_prompt_tokens = 0
    eval_completion_tokens = 0
    judge_prompt_tokens = 0
    judge_completion_tokens = 0
    row_results: list[dict[str, Any]] = []

    print(f"evaluating {len(examples)} examples on model={model} split={args.split_name}")
    for index, example in enumerate(examples, start=1):
        print(f"[{index}/{len(examples)}] row_id={example.row_id}")
        output_text, prompt_tokens, completion_tokens = infer_output(
            client=client,
            model=model,
            messages=example.messages,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            dry_run=args.dry_run,
        )
        eval_prompt_tokens += prompt_tokens
        eval_completion_tokens += completion_tokens

        format_pass, missing_sections = check_required_sections(output_text)
        deterministic = deterministic_constraint_check(
            output_text=output_text,
            restrictions=example.restrictions,
            compiled_constraints=compiled_constraints,
        )

        judge_payload: dict[str, Any] | None = None
        if not args.disable_judge:
            judge_payload, judge_tokens = score_with_judge(
                client=client,
                judge_model=args.judge_model,
                restrictions=example.restrictions,
                source_user_text=example.source_user_text,
                model_output=output_text,
                max_tokens=args.judge_max_tokens,
                temperature=args.judge_temperature,
                dry_run=args.dry_run,
            )
            judge_prompt_tokens += int(judge_tokens["prompt_tokens"])
            judge_completion_tokens += int(judge_tokens["completion_tokens"])

        row_results.append(
            {
                "row_id": example.row_id,
                "restrictions": example.restrictions,
                "constraint_pass": deterministic["constraint_pass"],
                "format_pass": format_pass,
                "missing_sections": missing_sections,
                "deterministic": deterministic,
                "judge": judge_payload,
                "output_text": output_text,
                "gold_assistant": example.gold_assistant,
            }
        )

    summary = compute_summary(
        row_results=row_results,
        eval_prompt_tokens=eval_prompt_tokens,
        eval_completion_tokens=eval_completion_tokens,
        judge_prompt_tokens=judge_prompt_tokens,
        judge_completion_tokens=judge_completion_tokens,
        judge_enabled=not args.disable_judge,
        prompt_price_per_1m=args.prompt_price_per_1m,
        completion_price_per_1m=args.completion_price_per_1m,
        judge_prompt_price_per_1m=args.judge_prompt_price_per_1m,
        judge_completion_price_per_1m=args.judge_completion_price_per_1m,
    )

    result_payload = {
        "generated_at": utc_now_iso(),
        "split_name": args.split_name,
        "input_path": str(args.input),
        "model": model,
        "judge_model": None if args.disable_judge else args.judge_model,
        "constraints_path": str(args.constraints_path),
        "dry_run": bool(args.dry_run),
        "summary": summary,
    }

    write_json(args.output_path, result_payload)
    write_rows_jsonl(args.rows_output_path, row_results)

    wandb_run_url, wandb_project = maybe_log_to_wandb(args, summary=summary, row_results=row_results)
    if wandb_project:
        result_payload["wandb_project"] = wandb_project
    if wandb_run_url:
        result_payload["wandb_run_url"] = wandb_run_url
        write_json(args.output_path, result_payload)

    print(f"wrote metrics: {args.output_path}")
    print(f"wrote row results: {args.rows_output_path}")
    print(
        "summary:"
        f" constraint_pass_rate={summary['constraint_pass_rate']}"
        f" format_pass_rate={summary['format_pass_rate']:.3f}"
        f" avg_judge_score={summary['avg_judge_score']}"
    )
    if wandb_run_url:
        print(f"wandb run: {wandb_run_url}")
    return 0


def main() -> int:
    parser = build_parser(
        default_model=None,
        default_output_path=DEFAULT_OUTPUT_PATH,
        default_rows_output_path=DEFAULT_ROWS_OUTPUT_PATH,
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
