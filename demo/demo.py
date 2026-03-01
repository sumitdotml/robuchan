#!/usr/bin/env python3
"""Run a side-by-side base-vs-finetuned demo response.

Notes:
  - If `--finetuned-model` is omitted, the script resolves `job.fine_tuned_model`
    from `--manifest-path` (default: `artifacts/ft_run_manifest.json`).
  - `--system-prompt` and `--system-prompt-file` are mutually exclusive and apply
    to both base and fine-tuned generations.
  - Cache keys include `model`, `prompt`, `system_prompt`, `temperature`, and
    `max_tokens`.

Examples:
  # standard run (uses manifest fine-tuned model fallback)
  uv run python demo/demo.py \
    --prompt "Adapt this chicken tikka masala recipe for vegetarian + gluten-free."

  # include a system prompt inline
  uv run python demo/demo.py \
    --prompt "Make this pasta dish vegan." \
    --system-prompt "You are a careful dietary recipe adaptation assistant."

  # load a system prompt from file
  uv run python demo/demo.py \
    --prompt "Adapt this ramen to pescatarian." \
    --system-prompt-file prompts/demo_system.txt

  # HF local adapter inference (no Mistral API needed for finetuned)
  uv run python demo/demo.py \
    --prompt "Make this pasta dish vegan." \
    --inference-backend hf_local \
    --finetuned-model sumitdotml/robuchan

  # explicit model IDs, disable cache
  uv run python demo/demo.py \
    --prompt "Make this pasta dish vegan." \
    --base-model mistral-small-latest \
    --finetuned-model ft:your-model-id \
    --no-cache

  # dry run without API calls
  uv run python demo/demo.py \
    --prompt "Adapt this ramen to pescatarian." \
    --dry-run \
    --json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mistralai import Mistral
from mistralai.models import chatcompletionrequest
from mistralai.models.sdkerror import SDKError

DEFAULT_BASE_MODEL = "mistral-small-latest"
DEFAULT_HF_BASE_MODEL = "mistralai/Ministral-8B-Instruct-2410"
DEFAULT_FINETUNED_MODEL = "sumitdotml/robuchan"
DEFAULT_MANIFEST_PATH = Path("artifacts/ft_run_manifest.json")
DEFAULT_OUTPUT_PATH = Path("artifacts/demo_output.json")
DEFAULT_CACHE_PATH = Path("artifacts/demo_cache.json")
DEFAULT_MAX_TOKENS = 1000
ChatMessages = list[chatcompletionrequest.MessagesTypedDict]


@dataclass
class HFLocalRuntime:
    tokenizer: Any
    model: Any


def load_hf_model(model_id: str, is_adapter: bool = False) -> Any:
    """Load an HF model (base or PEFT adapter)."""
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")

    token = os.environ.get("HF_TOKEN", "").strip() or None

    if torch.cuda.is_available():
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        device_map: str | None = "auto"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        dtype = torch.float32
        device_map = None
    else:
        dtype = torch.float32
        device_map = None

    if is_adapter:
        peft = importlib.import_module("peft")
        model = peft.AutoPeftModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, device_map=device_map, token=token,
        )
    else:
        model = transformers.AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype, device_map=device_map, token=token,
        )
    model.eval()
    return model


def load_hf_tokenizer(model_id: str) -> Any:
    transformers = importlib.import_module("transformers")
    token = os.environ.get("HF_TOKEN", "").strip() or None
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_id, token=token)
    if tokenizer.pad_token is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def generate_hf(
    model: Any,
    tokenizer: Any,
    prompt: str,
    system_prompt: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    """Generate text using a local HF model."""
    torch = importlib.import_module("torch")

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")

    device = getattr(model, "device", None)
    if device is not None:
        inputs = {k: v.to(device) for k, v in inputs.items()}

    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "do_sample": temperature > 0.0,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if tokenizer.eos_token_id is not None:
        gen_kwargs["eos_token_id"] = tokenizer.eos_token_id
    if temperature > 0.0:
        gen_kwargs["temperature"] = temperature

    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)

    prompt_len = inputs["input_ids"].shape[1]
    completion_ids = output_ids[0][prompt_len:]
    return tokenizer.decode(completion_ids, skip_special_tokens=True).strip()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def normalize_response(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


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
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def resolve_finetuned_model(args: argparse.Namespace) -> str:
    if args.finetuned_model and args.finetuned_model.strip():
        return args.finetuned_model.strip()

    if not args.manifest_path.exists():
        raise ValueError(
            "fine-tuned model is missing. Pass --finetuned-model or ensure manifest exists."
        )

    manifest = read_json_file(args.manifest_path)
    job = manifest.get("job")
    if not isinstance(job, dict):
        raise ValueError("manifest missing job object")
    fine_tuned_model = job.get("fine_tuned_model")
    if not isinstance(fine_tuned_model, str) or not fine_tuned_model.strip():
        raise ValueError(
            "manifest missing job.fine_tuned_model. Pass --finetuned-model explicitly."
        )
    return fine_tuned_model.strip()


def resolve_system_prompt(args: argparse.Namespace) -> str | None:
    if args.system_prompt and args.system_prompt.strip():
        return args.system_prompt.strip()

    if args.system_prompt_file:
        with args.system_prompt_file.open("r", encoding="utf-8") as handle:
            text = handle.read().strip()
        if not text:
            raise ValueError(f"system prompt file is empty: {args.system_prompt_file}")
        return text
    return None


def load_api_key(dry_run: bool) -> str | None:
    if dry_run:
        return None
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("MISTRAL_API_KEY is required unless --dry-run is set")
    return api_key


def build_demo_prompt(prompt: str, restrictions: list[str]) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("--prompt must not be empty")
    if not restrictions:
        return cleaned
    joined = ", ".join(item.strip() for item in restrictions if item.strip())
    if not joined:
        return cleaned
    return f"{cleaned}\n\nTarget restrictions: {joined}"


def build_cache_key(
    *,
    model: str,
    prompt: str,
    system_prompt: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "system_prompt": system_prompt or "",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": {}}
    payload = read_json_file(path)
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        payload["entries"] = {}
    return payload


def infer_once(
    *,
    client: Mistral | None,
    hf_model: Any | None,
    hf_tokenizer: Any | None,
    model: str,
    prompt: str,
    system_prompt: str | None,
    max_tokens: int,
    temperature: float,
    dry_run: bool,
    backend: str = "mistral_api",
) -> tuple[str, dict[str, Any]]:
    if dry_run:
        mock = (
            f"[DRY-RUN MOCK for {model}]\n"
            "Substitution Plan:\n- mock substitution\n\n"
            "Adapted Ingredients:\n- mock ingredient\n\n"
            "Adapted Steps:\n1) mock step\n\n"
            "Flavor Preservation Notes:\n- mock notes\n\n"
            "Constraint Check:\n- mock pass\n\n"
            f"Original request:\n{prompt}"
        )
        if system_prompt:
            mock = f"System prompt:\n{system_prompt}\n\n{mock}"
        return mock, {"dry_run": True}

    if backend == "hf_local":
        if hf_model is None or hf_tokenizer is None:
            raise ValueError("hf_model and hf_tokenizer are required for hf_local backend")
        output = generate_hf(hf_model, hf_tokenizer, prompt, system_prompt, max_tokens, temperature)
        return output, {"backend": "hf_local", "model": model}

    if client is None:
        raise ValueError("client is required for mistral_api backend")

    messages: ChatMessages = []
    if system_prompt:
        system_message: chatcompletionrequest.SystemMessageTypedDict = {
            "role": "system",
            "content": system_prompt,
        }
        messages.append(system_message)

    user_message: chatcompletionrequest.UserMessageTypedDict = {
        "role": "user",
        "content": prompt,
    }
    messages.append(user_message)

    response = client.chat.complete(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    payload = normalize_response(response)
    return extract_text_from_chat_response(payload), payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument(
        "--restriction",
        action="append",
        default=[],
        help="Repeatable restriction appended to prompt context.",
    )
    parser.add_argument("--base-model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--finetuned-model", type=str, default=None)
    system_prompt_group = parser.add_mutually_exclusive_group()
    system_prompt_group.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        help="Optional system prompt applied to both base and fine-tuned generations.",
    )
    system_prompt_group.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Optional file containing system prompt text.",
    )
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--inference-backend",
        type=str,
        choices=("mistral_api", "hf_local"),
        default="mistral_api",
        help="Inference backend. hf_local loads HF adapter locally (no Mistral API for inference).",
    )
    parser.add_argument(
        "--hf-base-model",
        type=str,
        default=DEFAULT_HF_BASE_MODEL,
        help="Base model for HF local inference.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    prompt = build_demo_prompt(args.prompt, args.restriction)
    system_prompt = resolve_system_prompt(args)
    is_hf = args.inference_backend == "hf_local"

    if is_hf:
        fine_tuned_model = (
            args.finetuned_model.strip()
            if args.finetuned_model and args.finetuned_model.strip()
            else DEFAULT_FINETUNED_MODEL
        )
    else:
        fine_tuned_model = resolve_finetuned_model(args)

    cache_enabled = not args.no_cache
    cache = load_cache(args.cache_path) if cache_enabled else {"entries": {}}
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        entries = {}
        cache["entries"] = entries

    # Load models based on backend
    client: Mistral | None = None
    hf_base_model_obj: Any = None
    hf_ft_model_obj: Any = None
    hf_tokenizer: Any = None

    if is_hf and not args.dry_run:
        print(f"loading base model: {args.hf_base_model}")
        hf_base_model_obj = load_hf_model(args.hf_base_model, is_adapter=False)
        print(f"loading adapter: {fine_tuned_model}")
        hf_ft_model_obj = load_hf_model(fine_tuned_model, is_adapter=True)
        hf_tokenizer = load_hf_tokenizer(args.hf_base_model)
    elif not args.dry_run:
        api_key = load_api_key(args.dry_run)
        client = Mistral(api_key=api_key) if api_key else None

    outputs: dict[str, dict[str, Any]] = {}
    model_pairs: list[tuple[str, str, Any]] = [
        ("base", args.hf_base_model if is_hf else args.base_model.strip(), hf_base_model_obj),
        ("finetuned", fine_tuned_model, hf_ft_model_obj),
    ]
    for label, model, hf_model in model_pairs:
        cache_key = build_cache_key(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        cached = entries.get(cache_key) if cache_enabled else None
        if isinstance(cached, dict) and isinstance(cached.get("output_text"), str):
            output_text = cached["output_text"]
            cached_payload = cached.get("raw_payload")
            raw_payload = cached_payload if isinstance(cached_payload, dict) else {}
            from_cache = True
        else:
            output_text, raw_payload = infer_once(
                client=client,
                hf_model=hf_model,
                hf_tokenizer=hf_tokenizer,
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                dry_run=args.dry_run,
                backend=args.inference_backend,
            )
            from_cache = False
            if cache_enabled:
                entries[cache_key] = {
                    "model": model,
                    "prompt": prompt,
                    "system_prompt": system_prompt or "",
                    "temperature": args.temperature,
                    "max_tokens": args.max_tokens,
                    "output_text": output_text,
                    "raw_payload": raw_payload,
                    "cached_at": utc_now_iso(),
                }

        outputs[label] = {
            "model": model,
            "from_cache": from_cache,
            "output_text": output_text,
            "raw_payload": raw_payload,
        }

    result = {
        "generated_at": utc_now_iso(),
        "prompt": prompt,
        "system_prompt": system_prompt,
        "restrictions": [item for item in args.restriction if item.strip()],
        "base_model": args.base_model.strip(),
        "finetuned_model": fine_tuned_model,
        "dry_run": bool(args.dry_run),
        "cache_enabled": cache_enabled,
        "results": outputs,
    }

    write_json_file(args.output_path, result)
    if cache_enabled:
        write_json_file(args.cache_path, cache)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print("Prompt:")
        print(prompt)
        print("")
        for label in ("base", "finetuned"):
            block = outputs[label]
            source = "cache" if block["from_cache"] else "live"
            print(f"{label.upper()} ({block['model']}) [{source}]")
            print(block["output_text"])
            print("")
        print(f"wrote output: {args.output_path}")
        if cache_enabled:
            print(f"cache: {args.cache_path}")

    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except (ValueError, SDKError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
