"""Robuchan - Recipe Adaptation Demo (HF Space).

Loads the fine-tuned LoRA adapter with 4-bit quantization and serves
a Gradio interface for interactive recipe adaptation.
"""

from __future__ import annotations

import gradio as gr
import torch
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer, BitsAndBytesConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADAPTER_ID = "sumitdotml/robuchan"
BASE_MODEL = "mistralai/Ministral-8B-Instruct-2410"
MAX_NEW_TOKENS = 800

SYSTEM_PROMPT = (
    "You are a culinary adaptation assistant. Priority: (1) strict dietary "
    "compliance, (2) preserve dish identity and flavor profile, (3) keep "
    "instructions practical and cookable. Never include forbidden ingredients "
    "or their derivatives (stocks, sauces, pastes, broths). If no exact "
    "compliant substitute exists, acknowledge the gap, choose the closest "
    "viable option, and state the trade-off. Output sections exactly: "
    "Substitution Plan, Adapted Ingredients, Adapted Steps, Flavor "
    "Preservation Notes, Constraint Check."
)

EXAMPLES = [
    "Adapt this tonkotsu ramen recipe for a vegan diet:\n\n"
    "Ingredients: pork bones, pork belly, eggs, wheat noodles, soy sauce, "
    "mirin, garlic, ginger, green onions, nori, sesame oil.\n\n"
    "Instructions: Boil pork bones for 12 hours for broth. Char pork belly. "
    "Soft-boil eggs. Cook wheat noodles. Assemble with toppings.",

    "Adapt this Japanese curry recipe for gluten-free:\n\n"
    "Ingredients: curry roux (contains wheat flour), chicken thighs, potatoes, "
    "carrots, onions, rice, soy sauce, mirin, dashi stock.\n\n"
    "Instructions: Saut\u00e9 onions, brown chicken, add vegetables, add water and "
    "curry roux, simmer 20 minutes. Serve over rice.",

    "I want to make mapo tofu but I'm vegetarian. Here's the original recipe:\n\n"
    "Ingredients: firm tofu, ground pork, doubanjiang, soy sauce, Sichuan "
    "peppercorns, garlic, ginger, green onions, sesame oil, chicken stock.\n\n"
    "Instructions: Fry ground pork until crispy, add doubanjiang and aromatics, "
    "add chicken stock, slide in tofu cubes, simmer 5 minutes, finish with "
    "Sichuan peppercorn oil.",
]

# ---------------------------------------------------------------------------
# Model loading (once at startup)
# ---------------------------------------------------------------------------

print("Loading model with 4-bit quantization ...")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

model = AutoPeftModelForCausalLM.from_pretrained(
    ADAPTER_ID,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Model loaded.")

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(message: str) -> str:
    """Generate an adapted recipe from the fine-tuned model."""
    if not message.strip():
        return "Please enter a recipe adaptation request."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt").to("cuda")

    gen_kwargs = {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": False,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if tokenizer.eos_token_id is not None:
        gen_kwargs["eos_token_id"] = tokenizer.eos_token_id

    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)

    prompt_len = inputs["input_ids"].shape[1]
    completion_ids = output_ids[0][prompt_len:]
    return tokenizer.decode(completion_ids, skip_special_tokens=True).strip()


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

DESCRIPTION = """\
# Robuchan - Recipe Adaptation

Fine-tuned [Ministral 8B](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410) \
adapter for dietary-compliant recipe transformation.

**How it works:** describe what you want adapted and the dietary constraint, \
and the model generates a full adapted recipe with substitution rationale, \
modified ingredients, updated steps, and a compliance check.

Adapter: [`sumitdotml/robuchan`](https://huggingface.co/sumitdotml/robuchan)
"""

demo = gr.Interface(
    fn=generate,
    inputs=gr.Textbox(
        label="Recipe Adaptation Request",
        placeholder="e.g. Adapt this tonkotsu ramen recipe for a vegan diet:\n\nIngredients: pork bones, pork belly, ...\n\nInstructions: Boil pork bones for 12 hours ...",
        lines=10,
    ),
    outputs=gr.Markdown(label="Adapted Recipe"),
    title="Robuchan",
    description=DESCRIPTION,
    examples=EXAMPLES,
    cache_examples=False,
    flagging_mode="never",
)

if __name__ == "__main__":
    demo.launch()
