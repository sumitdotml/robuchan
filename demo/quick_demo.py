#!/usr/bin/env python3
"""Quick side-by-side demo: base model vs fine-tuned adapter.

Loads the HF adapter locally and runs a few recipe adaptation prompts,
printing base vs finetuned output side-by-side.

Usage:
  uv run python demo/quick_demo.py
  uv run python demo/quick_demo.py --adapter sumitdotml/robuchan
  uv run python demo/quick_demo.py --prompt "Make this tonkotsu ramen vegan"
"""

from __future__ import annotations

import argparse
import os
import sys

DEFAULT_BASE_MODEL = "mistralai/Ministral-8B-Instruct-2410"
DEFAULT_ADAPTER = "sumitdotml/robuchan"
DEFAULT_MAX_TOKENS = 800

SYSTEM_PROMPT = (
    "You are a culinary adaptation assistant specializing in dietary-compliant "
    "recipe transformation. Given a recipe and a dietary constraint, replace "
    "non-compliant ingredients with appropriate substitutes, adjust cooking "
    "instructions, preserve the original dish's flavor profile, and provide "
    "clear substitution rationale."
)

DEMO_PROMPTS = [
    "Adapt this tonkotsu ramen recipe for a vegan diet:\n\n"
    "Ingredients: pork bones, pork belly, eggs, wheat noodles, soy sauce, "
    "mirin, garlic, ginger, green onions, nori, sesame oil.\n\n"
    "Instructions: Boil pork bones for 12 hours for broth. Char pork belly. "
    "Soft-boil eggs. Cook wheat noodles. Assemble with toppings.",
    "Adapt this Japanese curry recipe for gluten-free:\n\n"
    "Ingredients: curry roux (contains wheat flour), chicken thighs, potatoes, "
    "carrots, onions, rice, soy sauce, mirin, dashi stock.\n\n"
    "Instructions: Sauté onions, brown chicken, add vegetables, add water and "
    "curry roux, simmer 20 minutes. Serve over rice.",
]


def load_models(base_model: str, adapter_id: str):
    """Load base model and adapter model."""
    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoModelForCausalLM, AutoTokenizer

    token = os.environ.get("HF_TOKEN", "").strip() or None

    if torch.cuda.is_available():
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        device_map = "auto"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        dtype = torch.float32
        device_map = None
    else:
        dtype = torch.float32
        device_map = None

    print(f"loading base model: {base_model}")
    base = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=dtype, device_map=device_map, token=token,
    )
    base.eval()

    print(f"loading adapter: {adapter_id}")
    finetuned = AutoPeftModelForCausalLM.from_pretrained(
        adapter_id, torch_dtype=dtype, device_map=device_map, token=token,
    )
    finetuned.eval()

    tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return base, finetuned, tokenizer


def generate(model, tokenizer, prompt: str, max_tokens: int, temperature: float) -> str:
    """Generate a response from a model."""
    import torch

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")

    device = getattr(model, "device", None)
    if device is not None:
        inputs = {k: v.to(device) for k, v in inputs.items()}

    gen_kwargs = {
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


def print_divider(label: str = "") -> None:
    width = 80
    if label:
        print(f"\n{'=' * width}")
        print(f"  {label}")
        print(f"{'=' * width}")
    else:
        print(f"{'─' * width}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter", default=DEFAULT_ADAPTER)
    parser.add_argument("--prompt", type=str, default=None, help="Custom prompt (overrides built-in demos).")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    prompts = [args.prompt] if args.prompt else DEMO_PROMPTS

    base, finetuned, tokenizer = load_models(args.base_model, args.adapter)

    for i, prompt in enumerate(prompts, 1):
        print_divider(f"DEMO {i}/{len(prompts)}")
        print(f"\nPROMPT:\n{prompt}\n")

        print_divider()
        print("BASE MODEL:")
        base_output = generate(base, tokenizer, prompt, args.max_tokens, args.temperature)
        print(base_output)

        print_divider()
        print("FINE-TUNED MODEL:")
        ft_output = generate(finetuned, tokenizer, prompt, args.max_tokens, args.temperature)
        print(ft_output)

    print_divider("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
