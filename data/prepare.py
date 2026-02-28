#!/usr/bin/env python3
"""
Food.com synthetic adaptation pipeline — Block 1 (ingest) + Block 2 (generate).

Block 1 — ingest (Plan step 1):
    uv run python data/prepare.py ingest [--data-dir PATH] [--target-size N] [--seed 42]

    Downloads Food.com dataset via kagglehub (if not already cached), filters
    and selects source recipes, runs constraints coverage check, and produces
    artifacts/source_pool_summary.json.

    Exit gate:
      - artifacts/source_pool_summary.json written
      - parse_ok_rate == 100% on kept recipes
      - constraints coverage check printed

Block 2 — generate (Plan step 2):
    uv run python data/prepare.py generate [--source-pool PATH] [--target-pairs N]
                                           [--model MODEL] [--resume]

    Generates synthetic adaptation candidates using mistral-large-latest, audits
    each candidate inline, applies adaptive second-candidate policy, and writes
    data/internal_master.jsonl.

    Stop conditions:
      - target_pairs kept rows reached, OR
      - source pool exhausted
"""

import argparse
import asyncio
import hashlib
import traceback
import json
import math
import os
import random
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kagglehub
import pandas as pd
from dotenv import load_dotenv
from mistralai import Mistral
from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress,
    SpinnerColumn, TextColumn, TimeElapsedColumn,
)
from rich.table import Table

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from audit_dataset import score_candidate, check_completeness_validation, should_trigger_candidate2

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
CONSTRAINTS_PATH = ROOT / "eval" / "constraints.json"
ALIASES_PATH = ROOT / "eval" / "category_aliases.json"
KB_PATH = ROOT / "kb" / "swaps_v0.json"
SOURCE_POOL_PATH = ROOT / "artifacts" / "source_pool_summary.json"
INTERNAL_MASTER_PATH = ROOT / "data" / "internal_master.jsonl"
ARTIFACTS_DIR = ROOT / "artifacts"
KB_VERSION = "swaps_v0_2026-02-28"
DEFAULT_TARGET_PAIRS = 1200
DEFAULT_SOURCE_SIZE = 2000
DEFAULT_CONCURRENCY = 2  # Defined by how soon you get rate limited by Mistral
DEFAULT_MISTRAL_GEN_MODEL = "mistral-small-latest"
API_TIMEOUT_SECS = 120  # Max seconds per Mistral call before treating as a hung connection
KAGGLE_DATASET = "irkaal/foodcom-recipes-and-reviews"

# Token budget by richness tier — concise needs far fewer tokens than rich
MAX_TOKENS_BY_TIER: dict[str, int] = {
    "concise":  512,
    "standard": 1024,
    "rich":     2048,
}

SUPPORTED_CONSTRAINTS = [
    "vegetarian",
    "vegan",
    "dairy_free",
    "gluten_free",
    "egg_free",
    "shellfish_free",
    "nut_free",
    "low_sodium",
    "low_sugar",
    "low_fat",
]

CONSTRAINT_TARGET_FRACTION = {
    "vegetarian":     0.15,
    "vegan":          0.12,
    "dairy_free":     0.13,
    "gluten_free":    0.12,
    "egg_free":       0.10,
    "shellfish_free": 0.08,
    "nut_free":       0.08,
    "low_sodium":     0.08,
    "low_sugar":      0.07,
    "low_fat":        0.07,
}

FLAVOR_SIGNALS = {
    "spicy heat": [
        "chili", "jalapeño", "jalapeno", "cayenne", "sriracha", "hot sauce",
        "tabasco", "pepper flakes", "doubanjiang", "gochujang", "chipotle",
        "habanero", "serrano", "red pepper",
    ],
    "savory umami": [
        "soy sauce", "miso", "mushroom", "parmesan", "anchovy", "worcestershire",
        "fish sauce", "oyster sauce", "tomato paste", "dried mushroom",
        "nutritional yeast", "doenjang",
    ],
    "rich creaminess": [
        "cream", "butter", "coconut milk", "heavy cream", "sour cream",
        "cream cheese", "mascarpone", "ghee", "coconut cream",
    ],
    "smoky depth": [
        "bacon", "smoked paprika", "chipotle", "liquid smoke", "smoked",
        "chorizo", "pancetta", "andouille",
    ],
    "bright acidity": [
        "lemon", "lime", "vinegar", "lemon juice", "lime juice",
        "tamarind", "sumac",
    ],
    "sweet balance": [
        "sugar", "honey", "maple syrup", "brown sugar", "mirin",
        "molasses", "caramel", "agave",
    ],
    "herbal freshness": [
        "basil", "cilantro", "parsley", "mint", "dill", "tarragon",
        "chives", "lemongrass",
    ],
    "warm aromatics": [
        "cinnamon", "cardamom", "clove", "star anise", "allspice",
        "nutmeg", "garam masala", "five spice",
    ],
}

CATEGORY_TO_CUISINE = {
    "asian": "Asian",
    "chinese": "Chinese",
    "japanese": "Japanese",
    "thai": "Thai",
    "korean": "Korean",
    "vietnamese": "Vietnamese",
    "indian": "Indian",
    "indian subcontinent": "Indian",
    "middle eastern": "Middle Eastern",
    "turkish": "Turkish",
    "moroccan": "North African",
    "african": "African",
    "mexican": "Mexican",
    "tex mex": "Tex-Mex",
    "southwestern u.s.": "Southwestern US",
    "italian": "Italian",
    "french": "French",
    "greek": "Greek",
    "spanish": "Spanish",
    "european": "European",
    "british": "British",
    "german": "German",
    "scandinavian": "Scandinavian",
    "russian": "Russian",
    "caribbean": "Caribbean",
    "cuban": "Cuban",
    "brazilian": "Brazilian",
    "south american": "South American",
    "american": "American",
    "southern u.s.": "Southern US",
    "midwest u.s.": "Midwestern US",
    "hawaiian": "Hawaiian",
    "pasta": "Italian",
    "chicken": "American",
    "beef": "American",
    "pork": "American",
    "meat": "American",
    "poultry": "American",
    "breakfast": "American",
    "dessert": "American",
    "baking": "American",
    "bread": "American",
    "vegetable": "International",
    "vegan": "International",
    "seafood": "International",
    "fish": "International",
    "salad": "International",
    "soup": "International",
    "stew": "International",
    "rice": "International",
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_constraints() -> dict:
    with open(CONSTRAINTS_PATH) as f:
        return json.load(f)


def load_aliases() -> dict:
    with open(ALIASES_PATH) as f:
        return json.load(f)


def load_kb() -> list[dict]:
    with open(KB_PATH) as f:
        data = json.load(f)
    return data["rules"]


def _build_compiled_patterns(constraints: dict) -> dict[str, dict]:
    """Pre-compile per-constraint ban patterns (call once before hot scan loops)."""
    known_fps = set(constraints.get("_meta", {}).get("known_false_positives", []))
    result = {}
    for c in SUPPORTED_CONSTRAINTS:
        banned = constraints.get(c, {}).get("banned", [])
        # Sort longest-first so multi-word phrases match before their substrings
        sorted_terms = sorted(banned, key=len, reverse=True)
        compiled = [
            (term, re.compile(r"\b" + re.escape(term.lower()) + r"\b"))
            for term in sorted_terms
        ]
        combined = (
            re.compile(r"\b(?:" + "|".join(re.escape(t.lower()) for t in sorted_terms) + r")\b")
            if sorted_terms else None
        )
        result[c] = {
            "compiled": compiled,
            "combined": combined,
            "known_fps": known_fps,
            "reason_map": VIOLATION_REASONS.get(c, {}),
        }
    return result


# ---------------------------------------------------------------------------
# Food.com CSV parsing helpers
# ---------------------------------------------------------------------------

def parse_r_vector(s: Any) -> list[str]:
    """Parse R c("a", "b") format → Python list[str]. Handles nan and plain strings."""
    if s is None:
        return []
    if isinstance(s, float) and math.isnan(s):
        return []
    s = str(s).strip()
    if not s or s in ("NA", "character(0)", "nan"):
        return []

    if s.startswith("c("):
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', s)
        if not items:
            inner = s[2:-1]
            items = [x.strip().strip('"') for x in inner.split(",") if x.strip() not in ("", "NA")]
        return [item for item in items if item and item != "NA"]
    return [s] if s != "NA" else []


def combine_ingredients(quantities: list[str], parts: list[str]) -> list[str]:
    """Merge quantity + part lists into formatted ingredient strings."""
    result = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        qty = quantities[i].strip() if i < len(quantities) else ""
        if qty and qty not in ("NA", "nan", ""):
            result.append(f"{qty} {part}")
        else:
            result.append(part)
    return result


def infer_cuisine(category: str) -> str:
    if not category or not isinstance(category, str) or category in ("nan", "None", "NA"):
        return "International"
    lower = category.lower().strip()
    for key, cuisine in CATEGORY_TO_CUISINE.items():
        if key in lower:
            return cuisine
    return "International"


def infer_flavor_notes(ingredients: list[str]) -> list[str]:
    combined = " ".join(ingredients).lower()
    detected = []
    for label, signals in FLAVOR_SIGNALS.items():
        if any(sig in combined for sig in signals):
            detected.append(label)
        if len(detected) >= 3:
            break
    return detected or ["seasoning balance", "dish identity"]


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------

VIOLATION_REASONS: dict[str, dict[str, str]] = {
    "vegetarian": {
        "chicken": "meat_not_allowed",
        "beef": "meat_not_allowed",
        "pork": "meat_not_allowed",
        "lamb": "meat_not_allowed",
        "turkey": "meat_not_allowed",
        "duck": "meat_not_allowed",
        "veal": "meat_not_allowed",
        "venison": "meat_not_allowed",
        "rabbit": "meat_not_allowed",
        "bison": "meat_not_allowed",
        "goat": "meat_not_allowed",
        "bacon": "meat_not_allowed",
        "pancetta": "meat_not_allowed",
        "guanciale": "meat_not_allowed",
        "ham": "meat_not_allowed",
        "prosciutto": "meat_not_allowed",
        "salami": "meat_not_allowed",
        "pepperoni": "meat_not_allowed",
        "chorizo": "meat_not_allowed",
        "sausage": "meat_not_allowed",
        "ribs": "meat_not_allowed",
        "fish": "seafood_not_allowed",
        "salmon": "seafood_not_allowed",
        "tuna": "seafood_not_allowed",
        "shrimp": "seafood_not_allowed",
        "prawn": "seafood_not_allowed",
        "crab": "seafood_not_allowed",
        "lobster": "seafood_not_allowed",
        "scallop": "seafood_not_allowed",
        "clam": "seafood_not_allowed",
        "mussel": "seafood_not_allowed",
        "oyster": "seafood_not_allowed",
        "squid": "seafood_not_allowed",
        "anchovy": "seafood_not_allowed",
        "gelatin": "animal_derived",
        "lard": "animal_fat",
        "suet": "animal_fat",
        "tallow": "animal_fat",
        "oyster sauce": "animal_derived",
        "fish sauce": "seafood_derived",
        "chicken stock": "meat_derived",
        "chicken broth": "meat_derived",
        "beef stock": "meat_derived",
        "beef broth": "meat_derived",
        "fish stock": "seafood_derived",
        "dashi": "seafood_derived",
        "bonito": "seafood_not_allowed",
        "worcestershire sauce": "animal_derived",
        "shrimp paste": "seafood_derived",
    },
    "shellfish_free": {
        "shrimp": "contains_shellfish",
        "prawn": "contains_shellfish",
        "crab": "contains_shellfish",
        "lobster": "contains_shellfish",
        "scallop": "contains_shellfish",
        "clam": "contains_shellfish",
        "mussel": "contains_shellfish",
        "oyster": "contains_shellfish",
        "crawfish": "contains_shellfish",
        "oyster sauce": "shellfish_derived",
        "shrimp paste": "shellfish_derived",
    },
}
# Generic reason for constraints without specific mappings
for _c in ["vegan", "dairy_free", "gluten_free", "egg_free", "nut_free",
           "low_sodium", "low_sugar", "low_fat"]:
    VIOLATION_REASONS[_c] = {}


def detect_violations(
    ingredients: list[str],
    constraint: str,
    constraints: dict,
    precompiled: dict | None = None,
) -> list[dict]:
    """Return list of {ingredient, reason} for violations. Word-boundary matching."""
    if precompiled and constraint in precompiled:
        pc = precompiled[constraint]
        term_patterns = pc["compiled"]
        known_fps = pc["known_fps"]
        reason_map = pc["reason_map"]
        combined = pc["combined"]
    else:
        banned = constraints.get(constraint, {}).get("banned", [])
        known_fps = set(constraints.get("_meta", {}).get("known_false_positives", []))
        reason_map = VIOLATION_REASONS.get(constraint, {})
        sorted_terms = sorted(banned, key=len, reverse=True)
        term_patterns = [
            (term, re.compile(r"\b" + re.escape(term.lower()) + r"\b"))
            for term in sorted_terms
        ]
        combined = (
            re.compile(r"\b(?:" + "|".join(re.escape(t.lower()) for t in sorted_terms) + r")\b")
            if sorted_terms else None
        )

    violations = []
    seen_terms: set = set()

    for ing in ingredients:
        ing_lower = ing.lower()
        # Fast pre-check: skip ingredient entirely if combined pattern has no match
        if combined and not combined.search(ing_lower):
            continue
        for term, pattern in term_patterns:
            if term in seen_terms:
                continue
            if pattern.search(ing_lower):
                is_fp = any(
                    term in fp.lower() and fp.lower() in ing_lower for fp in known_fps
                )
                if not is_fp:
                    reason = next(
                        (r for t, r in sorted(reason_map.items(), key=lambda x: -len(x[0]))
                         if t in ing_lower),
                        f"violates_{constraint}",
                    )
                    violations.append({"ingredient": ing.strip(), "reason": reason})
                    seen_terms.add(term)
                    break

    return violations


# ---------------------------------------------------------------------------
# Template assignment (deterministic)
# ---------------------------------------------------------------------------

def assign_template(recipe_id: str, restriction: str) -> str:
    h = int(hashlib.md5(f"{recipe_id}{restriction}".encode()).hexdigest(), 16) % 100
    if h < 50:
        return "A"
    elif h < 80:
        return "B"
    return "C"


def assign_richness_tier(recipe_id: str, restriction: str) -> str:
    h = int(hashlib.md5(f"{recipe_id}{restriction}richness".encode()).hexdigest(), 16) % 10
    if h == 0:
        return "concise"
    elif h <= 7:
        return "standard"
    return "rich"


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SYSTEM_BASE = (
    "You are a culinary adaptation assistant. "
    "Priority: (1) strict dietary compliance, (2) preserve dish identity and flavor profile, "
    "(3) keep instructions practical and cookable. "
    "Never include forbidden ingredients or their derivatives "
    "(stocks, sauces, pastes, broths). "
    "If no exact compliant substitute exists, acknowledge the gap, "
    "choose the closest viable option, and state the trade-off. "
    "Output sections exactly: Substitution Plan, Adapted Ingredients, "
    "Adapted Steps, Flavor Preservation Notes, Constraint Check."
)

SYSTEM_PROMPTS = {
    "standard": _SYSTEM_BASE,
    "concise": _SYSTEM_BASE + (
        " Be concise: keep rationale to one phrase per substitution "
        "and provide exactly 3 flavor preservation notes."
    ),
    "rich": _SYSTEM_BASE + (
        " For each substitution provide deep rationale covering flavor chemistry, "
        "texture mechanics, and technique adjustments. "
        "Include one alternative swap option per substitution. "
        "Provide at least 5 concrete flavor preservation notes."
    ),
}


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _steps_to_prose(steps: list[str]) -> str:
    sentences = []
    for step in steps:
        step = step.strip()
        if step and not step.endswith("."):
            step += "."
        sentences.append(step)
    return " ".join(sentences)


def render_user_prompt(
    template_id: str,
    recipe: dict,
    restriction: str,
    cuisine: str,
    flavor_notes: list[str],
) -> str:
    title = recipe["title"]
    ingredients = recipe["ingredients"]
    steps = recipe["steps"]

    restriction_display = restriction.replace("_", "-")
    flavor_notes_str = ", ".join(flavor_notes)
    ingredients_csv = ", ".join(ingredients)
    ingredients_list = "\n".join(f"- {ing}" for ing in ingredients)
    steps_inline = " ".join(f"{i+1}) {s.strip().rstrip('.')}" for i, s in enumerate(steps))
    steps_numbered = "\n".join(f"{i+1}. {s.strip()}" for i, s in enumerate(steps))

    if template_id == "A":
        return (
            f"Recipe: {title}\n"
            f"Cuisine: {cuisine}\n"
            f"Ingredients: {ingredients_csv}\n"
            f"Steps: {steps_inline}\n"
            f"Restrictions: {restriction_display}\n"
            f"Must Keep Flavor Notes: {flavor_notes_str}"
        )
    elif template_id == "B":
        return (
            f"I have a recipe for {title} ({cuisine}) that I need to make "
            f"{restriction_display}-friendly.\n\n"
            f"The ingredients are: {ingredients_csv}.\n\n"
            f"Here's how it's made: {_steps_to_prose(steps)}\n\n"
            "Please adapt it while keeping the dish recognizable."
        )
    else:  # C
        h = int(hashlib.md5(f"{recipe.get('id','')}{restriction}opt".encode()).hexdigest(), 16) % 2
        optional = "\nWeeknight-friendly, under 45 minutes where possible." if h == 0 else ""
        return (
            f"Goal: make {title} fully {restriction_display}-compliant.\n\n"
            f"Source ingredients:\n{ingredients_list}\n\n"
            f"Source steps:\n{steps_numbered}\n\n"
            f"Preserve these flavors: {flavor_notes_str}.{optional}"
        )


# ---------------------------------------------------------------------------
# Mistral API call with retry
# ---------------------------------------------------------------------------

def _is_retryable_error(e: Exception) -> bool:
    """True for transient server/network errors worth retrying (5xx, 429, connection drops).
    False for client errors (401, 400, 404) that won't resolve on retry.
    """
    msg = str(e).lower()
    return any(token in msg for token in (
        "502", "503", "504", "429",
        "bad gateway", "service unavailable", "gateway timeout",
        "rate limit", "too many requests",
        "connection", "timeout", "reset",
    ))


def call_mistral(
    client,
    messages: list[dict],
    model: str,
    max_tokens: int = 1024,
    max_retries: int = 6,
    cancel_event: threading.Event | None = None,
) -> str:
    """Synchronous Mistral call with exponential-backoff retry.

    cancel_event — if set (by asyncio.wait_for cancellation), the thread
    stops retrying and exits early so it doesn't linger making extra requests.
    """
    for attempt in range(max_retries+1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("call cancelled by caller")
        try:
            response = client.chat.complete(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Mistral returned None content")
            return content
        except Exception as e:
            if attempt < max_retries and _is_retryable_error(e):
                # Exponential backoff capped at 60 s, plus uniform jitter so
                # concurrent workers don't all retry at exactly the same instant.
                base = min(60, 5 * (2 ** attempt))   # 5, 10, 20, 40, 60, 60 …
                wait = base + random.uniform(0, base * 0.25)
                print(
                    f"  Retryable error (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}. Retrying in {wait:.1f}s..."
                )
                # Interruptible sleep: wake every second to check cancel_event
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline:
                    if cancel_event and cancel_event.is_set():
                        raise RuntimeError("call cancelled during backoff")
                    time.sleep(min(1.0, deadline - time.monotonic()))
            else:
                raise
    raise RuntimeError(f"call_mistral: loop exited without returning (max_retries={max_retries})")


async def call_mistral_async(
    client,
    messages: list[dict],
    model: str,
    max_tokens: int = 1024,
    max_retries: int = 6,
) -> str:
    """Async wrapper: runs the synchronous Mistral call in a thread-pool worker.

    Uses asyncio.to_thread so the event loop stays free to schedule other
    concurrent API calls while this one is in-flight.

    A threading.Event is shared with the thread so that when asyncio.wait_for
    cancels this coroutine, the thread stops retrying immediately instead of
    lingering and making extra HTTP requests (which would inflate real concurrency).
    """
    cancel_event = threading.Event()
    try:
        return await asyncio.to_thread(
            call_mistral, client, messages, model, max_tokens, max_retries, cancel_event
        )
    except (asyncio.CancelledError, TimeoutError):
        cancel_event.set()   # signal the thread to stop
        raise


# ---------------------------------------------------------------------------
# Block 1: Ingest
# ---------------------------------------------------------------------------

def download_foodcom_data(data_dir: Path) -> Path:
    """Download Food.com dataset via kagglehub. Returns path to recipes CSV."""
    # Check kagglehub cache before hitting the network
    cache_base = (
        Path.home() / ".cache" / "kagglehub" / "datasets"
        / "irkaal" / "foodcom-recipes-and-reviews"
    )
    if cache_base.exists():
        candidates = list(cache_base.glob("**/*.csv"))
        recipe_files = [f for f in candidates if "recipe" in f.name.lower()]
        if not recipe_files:
            recipe_files = candidates
        if recipe_files:
            csv_path = max(recipe_files, key=lambda f: f.stat().st_size)
            print(f"Using cached dataset: {csv_path}")
            return csv_path

    print(f"Downloading {KAGGLE_DATASET} via kagglehub...")
    dataset_path = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"Dataset cached at: {dataset_path}")

    # Locate the recipes CSV
    candidates = list(dataset_path.glob("*.csv")) + list(dataset_path.glob("**/*.csv"))
    recipe_files = [f for f in candidates if "recipe" in f.name.lower()]
    if not recipe_files:
        recipe_files = candidates
    if not recipe_files:
        raise FileNotFoundError(
            f"No CSV files found in {dataset_path}. "
            "Check that the kagglehub download completed successfully."
        )

    # Use largest CSV (likely recipes.csv at ~120 MB)
    return max(recipe_files, key=lambda f: f.stat().st_size)


def load_and_parse_recipes(
    csv_path: Path, constraints: dict, target_size: int, seed: int
) -> list[dict]:
    """Load Food.com CSV, parse, filter, assign constraints. Returns source pool list."""
    rng = random.Random(seed)

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path, na_values=["NA", "N/A", "", "nan"], low_memory=False, on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    print(f"  Loaded {len(df):,} raw rows | Columns: {list(df.columns[:8])}...")

    # Resolve columns case-insensitively
    col_map = {c.lower(): c for c in df.columns}
    FIELD_CANDIDATES = {
        "id":           ["recipeid", "id", "recipe_id"],
        "name":         ["name", "title", "recipe_name"],
        "category":     ["recipecategory", "category"],
        "quantities":   ["recipeingredientquantities", "ingredientquantities"],
        "parts":        ["recipeingredientparts", "ingredientparts", "ingredients"],
        "instructions": ["recipeinstructions", "instructions", "steps"],
        "rating":       ["aggregatedrating", "rating", "avgrating"],
    }
    resolved: dict[str, str] = {}
    for field, cands in FIELD_CANDIDATES.items():
        for c in cands:
            if c in col_map:
                resolved[field] = col_map[c]
                break

    missing = [f for f in ["id", "name", "parts", "instructions"] if f not in resolved]
    if missing:
        raise ValueError(
            f"Required columns not found: {missing}. "
            f"Available columns: {list(df.columns[:20])}"
        )

    # Parse recipes — extract columns up-front to avoid iterrows() per-row boxing overhead
    valid_recipes: list[dict] = []
    skipped: Counter = Counter()

    _ids     = df[resolved["id"]].astype(str).tolist()
    _names   = df[resolved["name"]].astype(str).str.strip().tolist()
    _cats    = df[resolved["category"]].astype(str).str.strip().tolist() if "category" in resolved else [""] * len(df)
    _qtys    = df[resolved["quantities"]].tolist() if "quantities" in resolved else [None] * len(df)
    _parts   = df[resolved["parts"]].tolist()
    _instrs  = df[resolved["instructions"]].tolist()
    _ratings = df[resolved["rating"]].tolist() if "rating" in resolved else [None] * len(df)
    total_rows = len(df)

    for row_idx, (recipe_id, title, category, qty_raw, parts_raw, steps_raw, rating_raw) in enumerate(
        zip(_ids, _names, _cats, _qtys, _parts, _instrs, _ratings), start=1
    ):
        if row_idx % 10000 == 0:
            print(f"  Parsed {row_idx:,}/{total_rows:,} rows ({len(valid_recipes):,} valid so far)...")
        if not title or title in ("nan", "NA"):
            skipped["no_title"] += 1
            continue

        quantities = parse_r_vector(qty_raw)
        parts = parse_r_vector(parts_raw)
        steps = parse_r_vector(steps_raw)

        if len(parts) < 3:
            skipped["too_few_ingredients"] += 1
            continue
        if len(steps) < 2:
            skipped["too_few_steps"] += 1
            continue

        ingredients = combine_ingredients(quantities, parts)

        try:
            rating = float(rating_raw) if rating_raw and str(rating_raw) not in ("nan", "NA", "None") else 3.0
        except (ValueError, TypeError):
            rating = 3.0

        valid_recipes.append({
            "id": f"foodcom_{recipe_id}",
            "title": title,
            "ingredients": ingredients,
            "steps": steps,
            "category": category,
            "cuisine": infer_cuisine(category),
            "rating": rating,
        })

    print(f"  Parse OK: {len(valid_recipes):,} | Skipped: {dict(skipped)}")

    # Detect violations and bucket by constraint
    precompiled = _build_compiled_patterns(constraints)
    constraint_candidates: dict[str, list[dict]] = defaultdict(list)
    no_violation_count = 0

    for rec_idx, recipe in enumerate(valid_recipes, start=1):
        if rec_idx % 10000 == 0:
            print(f"  Violation scan: {rec_idx:,}/{len(valid_recipes):,} recipes...")
        found_any = False
        for constraint in SUPPORTED_CONSTRAINTS:
            violations = detect_violations(recipe["ingredients"], constraint, constraints, precompiled)
            if violations:
                constraint_candidates[constraint].append({**recipe, "_violations": violations})
                found_any = True
        if not found_any:
            no_violation_count += 1

    print(f"  Recipes with violations: "
          f"{sum(len(v) for v in constraint_candidates.values()):,} entries | "
          f"No violations: {no_violation_count:,}")
    for c in SUPPORTED_CONSTRAINTS:
        print(f"    {c}: {len(constraint_candidates[c]):,}")

    # Assign primary constraint — balance distribution
    selected: list[dict] = []
    constraint_counts: Counter = Counter()
    target_per_constraint = {
        c: max(1, int(target_size * frac))
        for c, frac in CONSTRAINT_TARGET_FRACTION.items()
    }
    used_ids: set = set()

    for constraint in SUPPORTED_CONSTRAINTS:
        rng.shuffle(constraint_candidates[constraint])
        target_n = target_per_constraint[constraint]
        added = 0
        for recipe in constraint_candidates[constraint]:
            if recipe["id"] in used_ids or added >= target_n:
                continue
            violations = recipe["_violations"]
            selected.append({
                "source_recipe_id": recipe["id"],
                "source_recipe": {
                    "title": recipe["title"],
                    "ingredients": recipe["ingredients"],
                    "steps": recipe["steps"],
                },
                "cuisine": recipe["cuisine"],
                "flavor_notes": infer_flavor_notes(recipe["ingredients"]),
                "target_restriction": constraint,
                "detected_violations": violations,
                "template_id": assign_template(recipe["id"], constraint),
                "rating": recipe["rating"],
            })
            used_ids.add(recipe["id"])
            constraint_counts[constraint] += 1
            added += 1

    # Top-up to reach target_size with overflow recipes
    if len(selected) < target_size:
        overflow: list[dict] = []
        for constraint in SUPPORTED_CONSTRAINTS:
            for recipe in constraint_candidates[constraint]:
                if recipe["id"] not in used_ids:
                    overflow.append({
                        "source_recipe_id": recipe["id"],
                        "source_recipe": {
                            "title": recipe["title"],
                            "ingredients": recipe["ingredients"],
                            "steps": recipe["steps"],
                        },
                        "cuisine": recipe["cuisine"],
                        "flavor_notes": infer_flavor_notes(recipe["ingredients"]),
                        "target_restriction": constraint,
                        "detected_violations": recipe["_violations"],
                        "template_id": assign_template(recipe["id"], constraint),
                        "rating": recipe["rating"],
                    })
                    used_ids.add(recipe["id"])
        rng.shuffle(overflow)
        needed = target_size - len(selected)
        for r in overflow[:needed]:
            selected.append(r)
            constraint_counts[r["target_restriction"]] += 1

    print(f"\n  Selected {len(selected):,} source recipes:")
    for c in SUPPORTED_CONSTRAINTS:
        print(f"    {c}: {constraint_counts[c]:,}")

    return selected


def run_constraints_coverage_check(source_pool: list[dict], constraints: dict) -> dict:
    """Cross-reference source pool ingredients against constraints.json banned terms."""
    all_ingredients: set[str] = set()
    for entry_idx, entry in enumerate(source_pool, start=1):
        if entry_idx % 1000 == 0:
            print(f"  Collecting ingredients: {entry_idx:,}/{len(source_pool):,} entries...")
        for ing in entry["source_recipe"]["ingredients"]:
            all_ingredients.add(ing.lower().strip())

    print(f"\n  Constraints coverage check ({len(all_ingredients):,} unique ingredients):")

    CATEGORY_SIGNALS = {
        "vegetarian": ["meat", "chicken", "beef", "pork", "bacon", "turkey", "lamb"],
        "dairy_free": ["milk", "cream", "butter", "cheese", "yogurt"],
        "gluten_free": ["flour", "bread", "noodle", "pasta", "wheat"],
    }

    precompiled = _build_compiled_patterns(constraints)
    stats: dict[str, dict] = {}
    for constraint in SUPPORTED_CONSTRAINTS:
        pc = precompiled[constraint]
        known_fps = pc["known_fps"]
        matched: set[str] = set()

        for ing in all_ingredients:
            # Fast pre-check via combined pattern before per-term scan
            if pc["combined"] and not pc["combined"].search(ing):
                continue
            for term, pattern in pc["compiled"]:
                if pattern.search(ing):
                    is_fp = any(term in fp.lower() and fp.lower() in ing for fp in known_fps)
                    if not is_fp:
                        matched.add(ing)
                        break

        signals = CATEGORY_SIGNALS.get(constraint, [])
        gaps = [
            ing for ing in all_ingredients
            if any(sig in ing for sig in signals) and ing not in matched
        ]

        stats[constraint] = {
            "banned_terms": len(pc["compiled"]),
            "matched_ingredients": len(matched),
            "potential_gaps_count": len(gaps),
            "potential_gaps_sample": sorted(gaps)[:5],
        }
        status = "OK" if not gaps else f"GAPS({len(gaps)})"
        print(f"    {constraint}: {len(matched):,} matched | {status}")
        if gaps:
            print(f"      sample gaps: {sorted(gaps)[:3]}")

    return stats


def run_ingest(args):
    console = Console()
    console.rule("[bold blue]Block 1: Food.com Ingest + Source Curation")

    constraints = load_constraints()

    # Download / locate data
    try:
        csv_path = download_foodcom_data(Path(args.data_dir))
    except Exception as e:
        console.print(f"[red]Failed to obtain Food.com data: {e}[/red]")
        console.print("[yellow]Per plan policy: pause execution if Food.com ingest is blocked.[/yellow]")
        sys.exit(1)

    console.print(f"[green]Data path:[/green] {csv_path}")

    source_pool = load_and_parse_recipes(csv_path, constraints, args.target_size, args.seed)

    if not source_pool:
        console.print("[red]No valid source recipes selected. Check data and constraints.[/red]")
        sys.exit(1)

    coverage_stats = run_constraints_coverage_check(source_pool, constraints)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    constraint_dist = dict(Counter(r["target_restriction"] for r in source_pool))
    template_dist = dict(Counter(r["template_id"] for r in source_pool))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "csv_source": str(csv_path),
        "total_source_recipes": len(source_pool),
        "constraint_distribution": constraint_dist,
        "template_distribution": template_dist,
        "constraints_coverage_check": coverage_stats,
        "parse_ok_rate": 1.0,
        "recipes": source_pool,
    }

    with open(SOURCE_POOL_PATH, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    console.print(f"\n[bold green]Block 1 COMPLETE[/bold green]")
    console.print(f"  Source pool:  [cyan]{len(source_pool):,}[/cyan] recipes")
    console.print(f"  Artifact:     [cyan]{SOURCE_POOL_PATH}[/cyan]")

    table = Table(title="Constraint Distribution", show_header=True)
    table.add_column("Constraint")
    table.add_column("Count", justify="right")
    table.add_column("Tmpl A", justify="right")
    table.add_column("Tmpl B", justify="right")
    table.add_column("Tmpl C", justify="right")

    per_constraint_templates: dict[str, Counter] = defaultdict(Counter)
    for r in source_pool:
        per_constraint_templates[r["target_restriction"]][r["template_id"]] += 1

    for c in SUPPORTED_CONSTRAINTS:
        n = constraint_dist.get(c, 0)
        tc = per_constraint_templates[c]
        table.add_row(c, str(n), str(tc.get("A", 0)), str(tc.get("B", 0)), str(tc.get("C", 0)))

    console.print(table)
    console.print(
        "\n[bold]Next step:[/bold] "
        "[cyan]uv run python data/prepare.py generate[/cyan]"
    )


# ---------------------------------------------------------------------------
# Block 2: Generate
# ---------------------------------------------------------------------------

def load_source_pool(pool_path: Path) -> list[dict]:
    with open(pool_path) as f:
        data = json.load(f)
    return data.get("recipes", [])


def load_processed_ids(master_path: Path) -> set[str]:
    if not master_path.exists():
        return set()
    ids: set[str] = set()
    with open(master_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["source_recipe_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def _build_export_messages(prompt_messages: list[dict], parsed: dict) -> list[dict]:
    """Build full messages list including reconstructed assistant response."""
    parts = []
    for section, key in [
        ("Substitution Plan", "substitution_plan_text"),
        ("Adapted Ingredients", "adapted_ingredients_text"),
        ("Adapted Steps", "adapted_steps_text"),
        ("Flavor Preservation Notes", "flavor_notes_text"),
        ("Constraint Check", "constraint_check_text"),
    ]:
        text = parsed.get(key, "").strip()
        if text:
            parts.append(f"{section}:\n{text}")

    assistant_content = "\n\n".join(parts)
    return prompt_messages + [{"role": "assistant", "content": assistant_content}]


def _build_master_row(
    recipe_id: str,
    recipe: dict,
    restriction: str,
    violations: list[dict],
    parsed: dict,
    prompt_messages: list[dict],
    audit_scores: dict,
    template_id: str,
    richness_tier: str,
    completeness_ok: bool,
    attempt_num: int,
) -> dict:
    return {
        "source_recipe_id": recipe_id,
        "source_recipe": recipe,
        "target_restrictions": [restriction],
        "detected_violations": violations,
        "replacement_pairs": parsed.get("replacement_pairs", []),
        "messages": _build_export_messages(prompt_messages, parsed),
        "template_id": template_id,
        "richness_tier": richness_tier,
        "audit_scores": audit_scores,
        "kept_for_training": False,  # finalized by caller
        "kb_version": KB_VERSION,
        "generation_attempt_count": attempt_num,
        "_completeness_ok": completeness_ok,  # internal flag, removed before write
    }


async def _run_generate_async(
    todo: list[dict],
    args,
    client,
    constraints: dict,
    aliases_data: dict,
    kb_rules: list,
    console,
) -> dict:
    """Async inner loop: processes todo recipes with up to args.concurrency parallel API calls.

    All mutable state is safe to modify without locks because asyncio is
    single-threaded — Python code between two `await` points runs atomically.
    Only the API call itself (call_mistral_async → asyncio.to_thread) runs in a
    thread-pool worker; everything else executes in the event loop.
    """
    state: dict = {
        "kept_count": 0,
        "gen_total": 0,
        "candidate2_count": 0,
        "reject_counts": Counter(),
    }
    stop_event = asyncio.Event()
    sem = asyncio.Semaphore(args.concurrency)

    console.print(
        f"[bold]_run_generate_async started[/bold]"
        f"  todo={len(todo)}  target={args.target_pairs}"
        f"  model={args.model}  concurrency={args.concurrency}"
        f"  timeout={API_TIMEOUT_SECS}s"
    )

    INTERNAL_MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    open_mode = "a" if args.resume else "w"

    with open(INTERNAL_MASTER_PATH, open_mode) as master_file, Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task(
            f"Generating (kept: 0/{args.target_pairs})",
            total=args.target_pairs,
        )

        async def process_one(recipe_entry: dict) -> None:
            # Fast-exit: target already reached before we even start
            if stop_event.is_set():
                return

            recipe_id = recipe_entry["source_recipe_id"]
            recipe = recipe_entry["source_recipe"]
            restriction = recipe_entry["target_restriction"]
            violations = recipe_entry["detected_violations"] or []
            cuisine = recipe_entry.get("cuisine", "International")
            flavor_notes = recipe_entry.get("flavor_notes", [])
            template_id = recipe_entry["template_id"]
            richness_tier = assign_richness_tier(recipe_id, restriction)
            max_tokens = MAX_TOKENS_BY_TIER[richness_tier]

            system_content = SYSTEM_PROMPTS[richness_tier]
            user_content = render_user_prompt(
                template_id, recipe, restriction, cuisine, flavor_notes
            )
            prompt_messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]

            progress.console.print(
                f"[dim]→ START  {recipe_id}  restriction={restriction}"
                f"  tier={richness_tier}  max_tokens={max_tokens}"
                f"  template={template_id}  violations={len(violations)}[/dim]"
            )

            best_row: dict | None = None

            for attempt_num in range(1, 3):
                if stop_event.is_set():
                    break

                # Semaphore caps concurrent in-flight API calls.
                # The await inside holds the slot until the HTTP response returns,
                # letting other coroutines proceed with CPU work in between.
                progress.console.print(
                    f"[dim]  {recipe_id}  attempt={attempt_num}  waiting for semaphore slot…[/dim]"
                )
                async with sem:
                    if stop_event.is_set():
                        break
                    state["gen_total"] += 1
                    if attempt_num == 2:
                        state["candidate2_count"] += 1
                    progress.console.print(
                        f"[cyan]  {recipe_id}  attempt={attempt_num}"
                        f"  calling {args.model}"
                        f"  (gen_total={state['gen_total']})[/cyan]"
                    )
                    t0 = time.monotonic()
                    try:
                        assistant_content = await asyncio.wait_for(
                            call_mistral_async(
                                client, prompt_messages, args.model,
                                max_tokens=max_tokens,
                                max_retries=args.num_retries,
                            ),
                            timeout=API_TIMEOUT_SECS,
                        )
                    except Exception as e:
                        elapsed = time.monotonic() - t0
                        state["reject_counts"]["api_error"] += 1
                        progress.console.print(
                            f"[red]  {recipe_id}  attempt={attempt_num}"
                            f"  API ERROR after {elapsed:.1f}s"
                            f"  (gen:{state['gen_total']} kept:{state['kept_count']}): {e}[/red]"
                        )
                        progress.update(
                            task_id,
                            description=(
                                f"gen:{state['gen_total']} "
                                f"kept:{state['kept_count']}/{args.target_pairs} "
                                f"avail:{len(todo)} "
                                f"err:{state['reject_counts']['api_error']}"
                            ),
                        )
                        return
                    elapsed = time.monotonic() - t0
                    if assistant_content is None:
                        state["reject_counts"]["api_error"] += 1
                        progress.console.print(
                            f"[red]  {recipe_id}  attempt={attempt_num}"
                            f"  API returned None content after {elapsed:.1f}s[/red]"
                        )
                        continue
                    progress.console.print(
                        f"[green]  {recipe_id}  attempt={attempt_num}"
                        f"  response received in {elapsed:.1f}s"
                        f"  chars={len(assistant_content)}[/green]"
                    )

                # CPU-bound scoring runs outside the semaphore so the slot is
                # freed for another recipe to start its API call immediately.
                progress.console.print(
                    f"[dim]  {recipe_id}  attempt={attempt_num}  scoring…[/dim]"
                )
                try:
                    scores_raw = score_candidate(
                        assistant_content=assistant_content,
                        user_content=user_content,
                        source_ingredients=recipe["ingredients"],
                        source_steps=recipe["steps"],
                        detected_violations=violations,
                        target_restriction=restriction,
                        constraints=constraints,
                        kb_rules=kb_rules,
                        aliases_data=aliases_data,
                    )
                    parsed = scores_raw.pop("_parsed")
                    audit_scores = {k: v for k, v in scores_raw.items()}
                    comp_passed, _ = check_completeness_validation(
                        assistant_content, violations, parsed
                    )
                except Exception as score_err:
                    state["reject_counts"]["scoring_error"] += 1
                    progress.console.print(
                        f"[red]  {recipe_id}  attempt={attempt_num}"
                        f"  SCORING ERROR — {type(score_err).__name__}: {score_err}[/red]"
                    )
                    return

                progress.console.print(
                    f"[dim]  {recipe_id}  attempt={attempt_num}"
                    f"  constraint_pass={audit_scores.get('constraint_pass')}"
                    f"  relevance={audit_scores.get('relevance_score', 0):.2f}"
                    f"  plausibility={audit_scores.get('substitution_plausibility_score', 0):.2f}"
                    f"  nontrivial={audit_scores.get('nontriviality_score', 0):.2f}"
                    f"  completeness_pass={audit_scores.get('semantic_completeness_pass')}"
                    f"  comp_validation={int(comp_passed)}[/dim]"
                )

                # Adaptive trigger: try candidate 2 on first failure
                if attempt_num == 1 and should_trigger_candidate2(audit_scores):
                    state["reject_counts"]["trigger_candidate2"] += 1
                    progress.console.print(
                        f"[yellow]  {recipe_id}  attempt=1  triggering candidate 2"
                        f"  (trigger_candidate2 total={state['reject_counts']['trigger_candidate2']})[/yellow]"
                    )
                    best_row = _build_master_row(
                        recipe_id, recipe, restriction, violations,
                        parsed, prompt_messages, audit_scores,
                        template_id, richness_tier, comp_passed, attempt_num,
                    )
                    continue  # re-enter loop → attempt_num == 2

                best_row = _build_master_row(
                    recipe_id, recipe, restriction, violations,
                    parsed, prompt_messages, audit_scores,
                    template_id, richness_tier, comp_passed, attempt_num,
                )
                break

            if best_row is None:
                state["reject_counts"]["no_candidate"] += 1
                progress.console.print(
                    f"[red]  {recipe_id}  no usable candidate — skipping[/red]"
                )
                return

            # Finalize kept_for_training flag
            s = best_row["audit_scores"]
            comp_ok = best_row.pop("_completeness_ok", False)
            kept = (
                s["constraint_pass"] == 1
                and s["semantic_completeness_pass"] == 1
                and comp_ok
            )
            best_row["kept_for_training"] = kept

            if kept:
                state["kept_count"] += 1
                if state["kept_count"] >= args.target_pairs:
                    stop_event.set()
                progress.console.print(
                    f"[bold green]  ✓ KEPT  {recipe_id}"
                    f"  kept={state['kept_count']}/{args.target_pairs}[/bold green]"
                )
            else:
                reject_reason = (
                    "constraint_fail" if s["constraint_pass"] != 1
                    else "semantic_fail" if s["semantic_completeness_pass"] != 1
                    else "comp_validation_fail"
                )
                state["reject_counts"][reject_reason] += 1
                progress.console.print(
                    f"[yellow]  ✗ DROPPED  {recipe_id}  reason={reject_reason}[/yellow]"
                )

            # Always refresh so gen_total is visible even when nothing is kept yet
            progress.update(
                task_id,
                completed=state["kept_count"],
                description=(
                    f"gen:{state['gen_total']} "
                    f"kept:{state['kept_count']}/{args.target_pairs}"
                ),
            )

            # Single-threaded event-loop writes are never interleaved
            master_file.write(json.dumps(best_row, ensure_ascii=False) + "\n")
            if kept or state["gen_total"] % 50 == 0:
                master_file.flush()
            progress.console.print(
                f"[dim]← DONE  {recipe_id}  written to master[/dim]"
            )

        batch_size = 100
        all_exceptions: list[Exception] = []
        for batch_start in range(0, len(todo), batch_size):
            if stop_event.is_set():
                break
            batch = todo[batch_start: batch_start + batch_size]
            console.print(
                f"[bold]Dispatching batch {batch_start // batch_size + 1}"
                f" ({batch_start + 1}–{batch_start + len(batch)} of {len(todo)})…[/bold]"
            )
            results = await asyncio.gather(
                *[process_one(entry) for entry in batch],
                return_exceptions=True,
            )
            exceptions = [r for r in results if isinstance(r, Exception)]
            all_exceptions.extend(exceptions)
            if exceptions:
                console.print(
                    f"[red]  batch had {len(exceptions)} unhandled exception(s):[/red]"
                )
                for exc in exceptions[:3]:  # show first 3 to avoid flooding
                    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                    console.print(tb, markup=False)

        console.print(
            f"[bold]all batches complete — gen_total={state['gen_total']}"
            f"  kept={state['kept_count']}"
            f"  api_errors={state['reject_counts'].get('api_error', 0)}"
            f"  candidate2={state['candidate2_count']}"
            f"  rejects={dict(state['reject_counts'])}"
            f"  unhandled_exceptions={len(all_exceptions)}[/bold]"
        )

    return state


def run_generate(args):
    console = Console()
    console.rule("[bold blue]Block 2: Synthetic Generation + Audit")

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        console.print("[red]MISTRAL_API_KEY not set. Export it in your shell or .env.[/red]")
        sys.exit(1)

    client = Mistral(api_key=api_key)

    constraints = load_constraints()
    aliases_data = load_aliases()
    kb_rules = load_kb()

    pool_path = Path(args.source_pool)
    if not pool_path.exists():
        console.print(f"[red]Source pool not found: {pool_path}[/red]")
        console.print("[yellow]Run: uv run python data/prepare.py ingest[/yellow]")
        sys.exit(1)

    source_pool = load_source_pool(pool_path)
    console.print(f"[green]Source pool:[/green] {len(source_pool):,} recipes")

    processed_ids: set[str] = set()
    if args.resume:
        processed_ids = load_processed_ids(INTERNAL_MASTER_PATH)
        console.print(f"[yellow]Resume:[/yellow] {len(processed_ids):,} already processed")

    todo = [r for r in source_pool if r["source_recipe_id"] not in processed_ids]
    console.print(
        f"  Remaining: {len(todo):,} | Target: {args.target_pairs:,} kept pairs "
        f"| Concurrency: {args.concurrency}"
    )

    state = asyncio.run(
        _run_generate_async(
            todo=todo,
            args=args,
            client=client,
            constraints=constraints,
            aliases_data=aliases_data,
            kb_rules=kb_rules,
            console=console,
        )
    )

    kept_count = state["kept_count"]
    gen_total = state["gen_total"]
    candidate2_count = state["candidate2_count"]
    reject_counts = state["reject_counts"]

    # Write generation summary artifact
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    gen_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "target_pairs": args.target_pairs,
        "kept_pairs": kept_count,
        "total_generated": gen_total,
        "candidate2_triggered": candidate2_count,
        "adaptive_rate": round(candidate2_count / max(1, gen_total), 4),
        "reject_counts": dict(reject_counts),
        "concurrency": args.concurrency,
        "internal_master_path": str(INTERNAL_MASTER_PATH),
    }
    with open(ARTIFACTS_DIR / "synthetic_generation_summary.json", "w") as f:
        json.dump(gen_summary, f, indent=2)

    color = "green" if kept_count >= args.target_pairs else "yellow"
    status = "COMPLETE" if kept_count >= args.target_pairs else "PARTIAL"
    console.print(f"\n[bold {color}]Block 2 {status}[/bold {color}]")
    console.print(f"  Kept pairs:   [cyan]{kept_count:,}[/cyan] / {args.target_pairs:,}")
    console.print(f"  Generated:    [cyan]{gen_total:,}[/cyan] total candidates")
    console.print(f"  Candidate 2:  [cyan]{candidate2_count:,}[/cyan] triggered")
    console.print(f"  Concurrency:  [cyan]{args.concurrency}[/cyan] parallel API slots")
    console.print(f"  Master JSONL: [cyan]{INTERNAL_MASTER_PATH}[/cyan]")

    if kept_count < args.target_pairs:
        console.print(
            f"\n[yellow]Warning:[/yellow] Only {kept_count:,}/{args.target_pairs:,} pairs. "
            "Increase source pool size or fix quality issues before fine-tuning."
        )
    else:
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  1. [cyan]uv run python data/audit_dataset.py gate[/cyan]")
        console.print(f"  2. [cyan]uv run python data/audit_dataset.py export[/cyan]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Food.com synthetic adaptation pipeline (Block 1 + Block 2)"
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    ingest_p = subparsers.add_parser("ingest", help="Block 1: Ingest and curate source pool")
    ingest_p.add_argument("--data-dir", default="data/raw",
                          help="Directory hint (unused by kagglehub, kept for compatibility)")
    ingest_p.add_argument("--target-size", type=int, default=DEFAULT_SOURCE_SIZE)
    ingest_p.add_argument("--seed", type=int, default=42)

    gen_p = subparsers.add_parser("generate", help="Block 2: Generate synthetic adaptations")
    gen_p.add_argument("--source-pool", default=str(SOURCE_POOL_PATH))
    gen_p.add_argument("--target-pairs", type=int, default=DEFAULT_TARGET_PAIRS)
    gen_p.add_argument("--model", default=DEFAULT_MISTRAL_GEN_MODEL)
    gen_p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                       help=f"Max parallel API calls (default: {DEFAULT_CONCURRENCY})")
    gen_p.add_argument("--num-retries", type=int, default=6,
                       help="Max retries per API call on transient errors (default: 6)")
    gen_p.add_argument("--resume", action="store_true",
                       help="Append to existing internal_master.jsonl (skip processed IDs)")

    args = parser.parse_args()
    if args.stage == "ingest":
        run_ingest(args)
    elif args.stage == "generate":
        run_generate(args)


if __name__ == "__main__":
    main()
