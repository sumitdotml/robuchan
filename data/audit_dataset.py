#!/usr/bin/env python3
"""
Deterministic audit and scoring for synthetic adaptation candidates.

Provides scoring functions imported by prepare.py (inline scoring during generation)
and a standalone CLI for batch audit and JSONL export.

Usage:
    uv run python data/audit_dataset.py gate    # run quality gate on internal_master.jsonl
    uv run python data/audit_dataset.py export  # produce train_filtered.jsonl + valid_filtered.jsonl
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
CONSTRAINTS_PATH = ROOT / "eval" / "constraints.json"
ALIASES_PATH = ROOT / "eval" / "category_aliases.json"
KB_PATH = ROOT / "kb" / "swaps_v0.json"
INTERNAL_MASTER_PATH = ROOT / "data" / "internal_master.jsonl"
TRAIN_PATH = ROOT / "data" / "train_filtered.jsonl"
VALID_PATH = ROOT / "data" / "valid_filtered.jsonl"
ARTIFACTS_DIR = ROOT / "artifacts"

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_constraints() -> dict:
    with open(CONSTRAINTS_PATH) as f:
        return json.load(f)


def load_aliases() -> dict:
    with open(ALIASES_PATH) as f:
        data = json.load(f)
    return data


def load_kb() -> list[dict]:
    with open(KB_PATH) as f:
        data = json.load(f)
    return data["rules"]


# ---------------------------------------------------------------------------
# Ingredient normalization
# ---------------------------------------------------------------------------

_FRACTION_RE = re.compile(r"^\d+[/\d]*$")
_LEADING_NUM_RE = re.compile(r"^\d[\d/.,]*\s*")
_UNIT_RE = None  # built lazily
_PAREN_RE = re.compile(r"\([^)]*\)")


def _build_unit_re(units: list[str]) -> re.Pattern:
    sorted_units = sorted(units, key=len, reverse=True)
    pattern = r"\b(" + "|".join(re.escape(u) for u in sorted_units) + r")\.?\b"
    return re.compile(pattern, re.IGNORECASE)


def normalize_ingredient(text: str, aliases_data: dict) -> str:
    """
    Normalize an ingredient string for relevance comparison.
    Pipeline: lowercase -> strip quantities/units -> remove parentheticals
              -> remove prep adjectives -> singularize -> alias-map
    """
    if not text:
        return ""

    global _UNIT_RE
    if _UNIT_RE is None:
        _UNIT_RE = _build_unit_re(aliases_data.get("units_to_strip", []))

    s = text.lower().strip()

    # Remove parentheticals: "(minced)", "(about 2 lbs)"
    s = _PAREN_RE.sub("", s)

    # Strip leading quantity pattern: "2 tbsp", "1/2 cup", "400g", "2-3"
    s = re.sub(r"^\d[\d/.,\-]*\s*", "", s)

    # Strip units
    s = _UNIT_RE.sub("", s)

    # Remove prep adjectives at start
    prep_adjs = aliases_data.get("prep_adjectives", [])
    # Sort longest first to catch multi-word adjectives before single-word
    prep_adjs_sorted = sorted(prep_adjs, key=len, reverse=True)
    for adj in prep_adjs_sorted:
        pattern = r"^" + re.escape(adj) + r"\s+"
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)

    # Remove trailing prep adjectives
    for adj in prep_adjs_sorted:
        pattern = r"\s+" + re.escape(adj) + r"$"
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)

    s = s.strip().strip(",").strip()

    # Simple singularization
    s = _singularize(s)

    # Alias map
    aliases = aliases_data.get("aliases", {})
    if s in aliases:
        s = aliases[s]

    return s.strip()


def _singularize(word: str) -> str:
    """Simple English singularizer for common food plurals."""
    if not word:
        return word
    rules = [
        (r"ies$", "y"),       # cherries -> cherry
        (r"oes$", "o"),       # tomatoes -> tomato
        (r"ves$", "f"),       # halves -> half
        (r"ves$", "fe"),      # knives -> knife (fallback below)
        (r"ches$", "ch"),     # peaches -> peach
        (r"shes$", "sh"),     # radishes -> radish
        (r"xes$", "x"),       # boxes -> box
        (r"ses$", "s"),       # buses -> bus
        (r"s$", ""),          # mushrooms -> mushroom
    ]
    for pattern, replacement in rules:
        if re.search(pattern, word):
            result = re.sub(pattern + "$", replacement, word)
            if result != word:
                return result
    return word


# ---------------------------------------------------------------------------
# Constraint checking
# ---------------------------------------------------------------------------

def _get_banned_terms(constraint: str, constraints: dict) -> list[str]:
    entry = constraints.get(constraint, {})
    return entry.get("banned", [])


def _word_boundary_match(text: str, term: str) -> bool:
    """Check if term appears in text using word-boundary matching."""
    pattern = r"\b" + re.escape(term.lower()) + r"\b"
    return bool(re.search(pattern, text.lower()))


def check_constraint_pass(
    adapted_ingredients_text: str,
    adapted_steps_text: str,
    restriction: str,
    constraints: dict,
) -> int:
    """
    Returns 1 if no banned terms for restriction appear in adapted content.
    Uses word-boundary matching after lowercasing.
    Known false positives (butternut squash, cream of tartar, eggplant) are skipped.
    """
    known_fps = set(constraints.get("_meta", {}).get("known_false_positives", []))
    banned = _get_banned_terms(restriction, constraints)
    combined = (adapted_ingredients_text + " " + adapted_steps_text).lower()

    for term in banned:
        if _word_boundary_match(combined, term):
            # Check false positives: if any known FP phrase contains this term and
            # the full FP phrase is present, skip it.
            is_fp = False
            for fp in known_fps:
                if term in fp.lower() and fp.lower() in combined:
                    is_fp = True
                    break
            if not is_fp:
                return 0
    return 1


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

SECTION_HEADERS = [
    "Substitution Plan",
    "Adapted Ingredients",
    "Adapted Steps",
    "Flavor Preservation Notes",
    "Constraint Check",
]


def _split_sections(content: str) -> dict[str, str]:
    """Split assistant response into named sections."""
    sections: dict[str, str] = {}
    current_key = None
    current_lines: list[str] = []

    for line in content.splitlines():
        matched = False
        for header in SECTION_HEADERS:
            # Accept "Header:" or "## Header" or "**Header**:" etc.
            if re.match(
                r"^[\*#\s]*" + re.escape(header) + r"[\*#:\s]*$",
                line.strip(),
                re.IGNORECASE,
            ):
                if current_key is not None:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = header
                current_lines = []
                matched = True
                break
        if not matched and current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def parse_assistant_response(content: str) -> dict:
    """
    Parse assistant response into structured components.

    Returns dict with keys:
      - substitution_plan_text: raw text of Substitution Plan section
      - adapted_ingredients_text: raw text of Adapted Ingredients section
      - adapted_steps_text: raw text of Adapted Steps section
      - flavor_notes_text: raw text of Flavor Preservation Notes section
      - constraint_check_text: raw text of Constraint Check section
      - replacement_pairs: list of {from, to, reason} dicts
      - adapted_ingredients: list of ingredient strings
      - adapted_steps: list of step strings
      - sections_found: list of section names found
    """
    sections = _split_sections(content)

    result = {
        "substitution_plan_text": sections.get("Substitution Plan", ""),
        "adapted_ingredients_text": sections.get("Adapted Ingredients", ""),
        "adapted_steps_text": sections.get("Adapted Steps", ""),
        "flavor_notes_text": sections.get("Flavor Preservation Notes", ""),
        "constraint_check_text": sections.get("Constraint Check", ""),
        "replacement_pairs": [],
        "adapted_ingredients": [],
        "adapted_steps": [],
        "sections_found": list(sections.keys()),
    }

    # Parse replacement pairs from Substitution Plan
    sub_text = result["substitution_plan_text"]
    for line in sub_text.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        # Match: "item -> replacement (reason)" or "item -> replacement"
        m = re.match(r"^(.+?)\s*->\s*(.+?)(?:\s+\((.+)\))?$", line)
        if m:
            result["replacement_pairs"].append({
                "from": m.group(1).strip(),
                "to": m.group(2).strip(),
                "reason": m.group(3).strip() if m.group(3) else "",
            })

    # Parse adapted ingredients (list items)
    ing_text = result["adapted_ingredients_text"]
    for line in ing_text.splitlines():
        line = line.strip().lstrip("-•*").strip()
        # Skip numbered list markers
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if line:
            result["adapted_ingredients"].append(line)

    # Parse adapted steps
    steps_text = result["adapted_steps_text"]
    for line in steps_text.splitlines():
        line = line.strip()
        # Strip step number prefix: "1)", "1.", "Step 1:", etc.
        line = re.sub(r"^\d+[.)]\s*|^[Ss]tep\s+\d+[.:)]\s*", "", line).strip()
        if line:
            result["adapted_steps"].append(line)

    return result


# ---------------------------------------------------------------------------
# Completeness validation (4 rejection checks)
# ---------------------------------------------------------------------------

def check_completeness_validation(
    assistant_content: str,
    detected_violations: list[dict],
    parsed: dict | None = None,
) -> tuple[bool, list[str]]:
    """
    Run 4 deterministic assistant completeness checks.

    Returns (passed: bool, failure_reasons: list[str])

    Reject conditions:
    1. '...' appears anywhere in assistant content
    2. Adapted ingredient list not parseable or missing quantities
    3. Any detected_violation ingredient has no row in Substitution Plan
    4. Any banned (removed) ingredient still in Adapted Ingredients or Adapted Steps
    """
    failures = []

    if parsed is None:
        parsed = parse_assistant_response(assistant_content)

    # Check 1: no ellipsis
    if "..." in assistant_content:
        failures.append("contains_ellipsis")

    # Check 2: adapted ingredients parseable with quantities
    adapted_ings = parsed["adapted_ingredients"]
    if not adapted_ings:
        failures.append("adapted_ingredients_empty")
    else:
        # Each ingredient line should contain at least one digit (quantity) or a known unit
        quantity_pattern = re.compile(
            r"\d|"
            r"\b(cup|tbsp|tsp|tablespoon|teaspoon|oz|lb|g|kg|ml|l|pinch|dash|handful|"
            r"clove|sprig|bunch|slice|piece)\b",
            re.IGNORECASE,
        )
        missing_qty = [
            ing for ing in adapted_ings if not quantity_pattern.search(ing)
        ]
        if len(missing_qty) > len(adapted_ings) * 0.5:
            failures.append(f"adapted_ingredients_missing_quantities ({len(missing_qty)}/{len(adapted_ings)} lines lack quantities)")

    # Check 3: every detected violation mapped in Substitution Plan
    sub_text = parsed["substitution_plan_text"].lower()
    for v in detected_violations:
        ingredient = v.get("ingredient", "").lower()
        if not ingredient:
            continue
        # Check if ingredient appears in the substitution plan text
        # Use a relaxed check: any word from the violation ingredient appears in sub text
        words = [w for w in re.split(r"\s+", ingredient) if len(w) > 2]
        found = any(_word_boundary_match(sub_text, w) for w in words) if words else False
        if not found:
            failures.append(f"violation_unmapped_in_substitution_plan: {ingredient}")

    # Check 4: no removed/banned ingredients appear in adapted content
    adapted_combined = (
        parsed["adapted_ingredients_text"] + " " + parsed["adapted_steps_text"]
    ).lower()
    for pair in parsed["replacement_pairs"]:
        removed = pair.get("from", "").lower()
        if not removed:
            continue
        # Check if the removed ingredient's key words still appear in adapted content
        words = [w for w in re.split(r"\s+", removed) if len(w) > 3]
        for w in words:
            if _word_boundary_match(adapted_combined, w):
                # Ignore if the word is also part of a replacement phrase
                replacement = pair.get("to", "").lower()
                if w not in replacement:
                    failures.append(f"banned_ingredient_in_adapted_content: {removed} (word: {w})")
                    break

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_relevance(
    source_ingredients: list[str],
    adapted_ingredients: list[str],
    restriction: str,
    constraints: dict,
    aliases_data: dict,
) -> float:
    """
    relevance_score = retained_nonrestricted_source_ingredients / total_nonrestricted_source_ingredients

    Compares normalized ingredient names, excluding restricted ingredients.
    """
    banned = set(_get_banned_terms(restriction, constraints))
    if not source_ingredients:
        return 0.0

    # Normalize all ingredients
    norm_source = [normalize_ingredient(ing, aliases_data) for ing in source_ingredients]
    norm_adapted = set(normalize_ingredient(ing, aliases_data) for ing in adapted_ingredients)

    # Filter out restricted (banned) source ingredients
    nonrestricted_source = []
    for norm, raw in zip(norm_source, source_ingredients):
        is_banned = any(_word_boundary_match(raw, b) for b in banned)
        if not is_banned:
            nonrestricted_source.append(norm)

    if not nonrestricted_source:
        return 1.0  # Nothing to retain — trivially perfect

    retained = sum(1 for ing in nonrestricted_source if ing in norm_adapted)
    return round(retained / len(nonrestricted_source), 4)


def score_nontriviality(
    replacement_pairs: list[dict],
    total_violations: int,
    source_steps: list[str],
    adapted_steps: list[str],
) -> float:
    """
    nontriviality_score = 0.8 * (replaced_violations / max(1, total_violations))
                        + 0.2 * step_changed_flag
    """
    replaced = len([p for p in replacement_pairs if p.get("to", "").strip()])
    violation_rate = replaced / max(1, total_violations)

    # step_changed_flag: 1 if adapted steps differ meaningfully from source steps
    if not source_steps or not adapted_steps:
        step_changed = 0
    elif len(adapted_steps) != len(source_steps):
        step_changed = 1
    else:
        # Check if step content changed by sampling a few
        changed = sum(
            1 for s, a in zip(source_steps[:3], adapted_steps[:3])
            if s.lower().strip() != a.lower().strip()
        )
        step_changed = 1 if changed >= 1 else 0

    return round(0.8 * violation_rate + 0.2 * step_changed, 4)


def predict_step_ban_exposure(
    steps: list[str],
    restriction: str,
    constraints: dict,
) -> int:
    """
    Count source step lines that mention at least one banned term for the restriction.

    High counts predict constraint_fail: the model must rewrite many step lines
    and is likely to leave at least one banned-term reference intact.  The check
    uses the same word-boundary matching as check_constraint_pass.

    Returns 0 when steps is empty or no banned terms are defined.
    """
    banned = constraints.get(restriction, {}).get("banned", [])
    if not steps or not banned:
        return 0

    sorted_terms = sorted(banned, key=len, reverse=True)
    combined = re.compile(
        r"\b(?:" + "|".join(re.escape(t.lower()) for t in sorted_terms) + r")\b"
    )
    known_fps = set(constraints.get("_meta", {}).get("known_false_positives", []))

    contaminated = 0
    for step in steps:
        step_lower = step.lower()
        if not combined.search(step_lower):
            continue
        # Exclude lines where only false-positive phrases match
        is_real = False
        for term in banned:
            if _word_boundary_match(step_lower, term):
                fp = any(term in fp_.lower() and fp_.lower() in step_lower for fp_ in known_fps)
                if not fp:
                    is_real = True
                    break
        if is_real:
            contaminated += 1

    return contaminated


def score_semantic_completeness(user_content: str) -> int:
    """
    Returns 1 if user prompt contains recipe title, ingredients, steps, and restrictions.
    Works across all three templates (A/B/C).
    """
    lower = user_content.lower()

    # Title: check for "Recipe:", "Goal: make", "I have a recipe for"
    has_title = bool(
        re.search(r"recipe\s*:", lower) or
        re.search(r"goal\s*:\s*make\s+\w", lower) or
        re.search(r"i have a recipe for\s+\w", lower)
    )

    # Ingredients: check for "Ingredients:", "ingredients are:", "Source ingredients:"
    has_ingredients = bool(
        re.search(r"ingredients?\s*:", lower) or
        re.search(r"source ingredients\s*:", lower)
    )

    # Steps: check for "Steps:", "Source steps:", "Here's how", step-numbered content
    has_steps = bool(
        re.search(r"steps?\s*:", lower) or
        re.search(r"source steps\s*:", lower) or
        re.search(r"here'?s how", lower) or
        re.search(r"\b[1-9][.)]\s+\w", lower)
    )

    # Restrictions: check for "Restrictions:", "restriction", "compliant", "-free"
    has_restrictions = bool(
        re.search(r"restrictions?\s*:", lower) or
        re.search(r"\b(vegetarian|vegan|gluten[- ]free|dairy[- ]free|nut[- ]free|"
                  r"egg[- ]free|shellfish[- ]free|low[- ]sodium|low[- ]sugar|low[- ]fat)\b", lower)
    )

    return 1 if (has_title and has_ingredients and has_steps and has_restrictions) else 0


# ---------------------------------------------------------------------------
# Master scoring entry point
# ---------------------------------------------------------------------------

def score_candidate(
    assistant_content: str,
    user_content: str,
    source_ingredients: list[str],
    source_steps: list[str],
    detected_violations: list[dict],
    target_restriction: str,
    constraints: dict,
    aliases_data: dict,
) -> dict:
    """
    Run all deterministic scoring checks on a candidate response.

    Returns audit_scores dict with keys:
      constraint_pass, relevance_score, nontriviality_score,
      semantic_completeness_pass
    """
    parsed = parse_assistant_response(assistant_content)

    constraint_pass = check_constraint_pass(
        parsed["adapted_ingredients_text"],
        parsed["adapted_steps_text"],
        target_restriction,
        constraints,
    )

    relevance = score_relevance(
        source_ingredients,
        parsed["adapted_ingredients"],
        target_restriction,
        constraints,
        aliases_data,
    )

    nontriviality = score_nontriviality(
        parsed["replacement_pairs"],
        len(detected_violations),
        source_steps,
        parsed["adapted_steps"],
    )

    semantic_pass = score_semantic_completeness(user_content)

    return {
        "constraint_pass": constraint_pass,
        "relevance_score": relevance,
        "nontriviality_score": nontriviality,
        "semantic_completeness_pass": semantic_pass,
        "_parsed": parsed,  # internal, not written to JSONL
    }


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------

QUALITY_GATE_CHECKS = {
    "constraint_pass_rate_on_kept": (">=", 0.98),
    "semantic_completeness_pass_rate_on_kept": ("==", 1.0),
    "assistant_completeness_validation_pass_rate_on_kept": ("==", 1.0),
    "mean_relevance_score_on_kept": (">=", 0.55),
    "nontrivial_adaptation_pass_rate_on_kept": (">=", 0.90),
    "template_a_fraction": ("within", (0.40, 0.60)),
    "template_b_fraction": ("within", (0.20, 0.40)),
    "template_c_fraction": ("within", (0.10, 0.30)),
}


def run_quality_gate(master_path: Path, console: Any | None = None) -> dict:
    """
    Load internal_master.jsonl, compute quality gate metrics, return report dict.
    """
    from rich.console import Console
    if console is None:
        console = Console()

    constraints = load_constraints()
    aliases_data = load_aliases()
    kb_rules = load_kb()

    rows = []
    with open(master_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    kept = [r for r in rows if r.get("kept_for_training", False)]

    if not kept:
        return {
            "total_rows": len(rows),
            "kept_rows": 0,
            "gate_passed": False,
            "failures": ["no kept rows found"],
            "metrics": {},
        }

    # Re-run completeness validation on each kept row
    completeness_passes = 0
    nontrivial_passes = 0
    template_counts: Counter = Counter()
    constraint_passes = 0
    relevance_sum = 0.0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Auditing kept rows", total=len(kept))

        for i, row in enumerate(kept, start=1):
            scores = row.get("audit_scores", {})
            messages = row.get("messages", [])
            assistant_msg = next(
                (m["content"] for m in messages if m["role"] == "assistant"), ""
            )
            detected_violations = row.get("detected_violations", [])

            comp_passed, _ = check_completeness_validation(
                assistant_msg, detected_violations
            )
            if comp_passed:
                completeness_passes += 1

            if scores.get("constraint_pass", 0) == 1:
                constraint_passes += 1
            if scores.get("nontriviality_score", 0) >= 0.5:
                nontrivial_passes += 1

            template_counts[row.get("template_id", "?")] += 1
            relevance_sum += scores.get("relevance_score", 0.0)

            progress.update(
                task_id,
                advance=1,
                description=(
                    f"Auditing kept rows  "
                    f"constraint_pass:{constraint_passes}/{i}  "
                    f"comp_ok:{completeness_passes}/{i}"
                ),
            )

    n = len(kept)
    metrics = {
        "total_rows": len(rows),
        "kept_rows": n,
        "constraint_pass_rate_on_kept": round(constraint_passes / n, 4),
        "semantic_completeness_pass_rate_on_kept": round(
            sum(1 for r in kept if r.get("audit_scores", {}).get("semantic_completeness_pass", 0)) / n, 4
        ),
        "assistant_completeness_validation_pass_rate_on_kept": round(completeness_passes / n, 4),
        "mean_relevance_score_on_kept": round(relevance_sum / n, 4),
        "nontrivial_adaptation_pass_rate_on_kept": round(nontrivial_passes / n, 4),
        "template_a_fraction": round(template_counts.get("A", 0) / n, 4),
        "template_b_fraction": round(template_counts.get("B", 0) / n, 4),
        "template_c_fraction": round(template_counts.get("C", 0) / n, 4),
        "template_distribution": dict(template_counts),
    }

    failures = []
    for check_name, (op, threshold) in QUALITY_GATE_CHECKS.items():
        val = metrics.get(check_name)
        if val is None:
            continue
        if op == ">=" and val < threshold:
            failures.append(f"{check_name}: {val} < {threshold} (gate: >=)")
        elif op == "==" and val != threshold:
            failures.append(f"{check_name}: {val} != {threshold} (gate: ==)")
        elif op == "within":
            lo, hi = threshold
            if not (lo <= val <= hi):
                failures.append(f"{check_name}: {val} not in [{lo}, {hi}]")

    return {
        "gate_passed": len(failures) == 0,
        "failures": failures,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Export to JSONL for fine-tuning
# ---------------------------------------------------------------------------

def export_to_jsonl(
    master_path: Path,
    train_path: Path,
    valid_path: Path,
    valid_fraction: float = 0.1,
    seed: int = 42,
    console: Any | None = None,
) -> dict:
    """
    Export kept rows to train_filtered.jsonl and valid_filtered.jsonl.
    Only exports the 'messages' field (no audit metadata).
    Splits 90/10 train/valid deterministically (by row index).
    Flushes to disk every 10 records.
    """
    import random
    from rich.console import Console
    if console is None:
        console = Console()

    rng = random.Random(seed)

    rows = []
    with open(master_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    kept = [r for r in rows if r.get("kept_for_training", False)]

    # Deterministic shuffle
    rng.shuffle(kept)

    split_idx = max(1, int(len(kept) * (1 - valid_fraction)))
    train_rows = kept[:split_idx]
    valid_rows = kept[split_idx:]

    train_path.parent.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        train_task = progress.add_task(
            f"Writing {train_path.name}", total=len(train_rows)
        )
        with open(train_path, "w") as f:
            for i, row in enumerate(train_rows, start=1):
                export_row = {"messages": row["messages"]}
                f.write(json.dumps(export_row, ensure_ascii=False) + "\n")
                if i % 10 == 0:
                    f.flush()
                progress.advance(train_task)

        valid_task = progress.add_task(
            f"Writing {valid_path.name}", total=len(valid_rows)
        )
        with open(valid_path, "w") as f:
            for i, row in enumerate(valid_rows, start=1):
                export_row = {"messages": row["messages"]}
                f.write(json.dumps(export_row, ensure_ascii=False) + "\n")
                if i % 10 == 0:
                    f.flush()
                progress.advance(valid_task)

    return {
        "total_kept": len(kept),
        "train_rows": len(train_rows),
        "valid_rows": len(valid_rows),
        "train_path": str(train_path),
        "valid_path": str(valid_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_gate(args):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    master = Path(args.master)
    if not master.exists():
        console.print(f"[red]Not found: {master}[/red]")
        sys.exit(1)

    console.print(f"[bold]Running quality gate on {master}...[/bold]")
    report = run_quality_gate(master, console=console)

    table = Table(title="Quality Gate Metrics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Status", style="bold")

    gate_checks = {k: v for k, v in QUALITY_GATE_CHECKS.items()}
    for k, v in report["metrics"].items():
        if k in ("total_rows", "kept_rows", "template_distribution"):
            table.add_row(k, str(v), "")
            continue
        check = gate_checks.get(k)
        if check:
            op, threshold = check
            if op == ">=":
                status = "[green]PASS[/green]" if v >= threshold else "[red]FAIL[/red]"
            elif op == "==":
                status = "[green]PASS[/green]" if v == threshold else "[red]FAIL[/red]"
            elif op == "within":
                lo, hi = threshold
                status = "[green]PASS[/green]" if lo <= v <= hi else "[red]FAIL[/red]"
            else:
                status = ""
        else:
            status = ""
        table.add_row(k, str(v), status)

    console.print(table)

    if report["gate_passed"]:
        console.print("\n[bold green]GATE PASSED[/bold green] — ready for fine-tuning.")
    else:
        console.print("\n[bold red]GATE FAILED[/bold red]")
        for f in report["failures"]:
            console.print(f"  [red]✗[/red] {f}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = ARTIFACTS_DIR / "quality_gate_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    console.print(f"\nReport saved to {report_path}")


def cmd_export(args):
    from rich.console import Console
    console = Console()
    master = Path(args.master)
    if not master.exists():
        console.print(f"[red]Not found: {master}[/red]")
        sys.exit(1)

    result = export_to_jsonl(
        master_path=master,
        train_path=TRAIN_PATH,
        valid_path=VALID_PATH,
        valid_fraction=args.valid_fraction,
        seed=args.seed,
        console=console,
    )
    console.print(f"[green]Export complete[/green]")
    console.print(f"  Total kept:  {result['total_kept']}")
    console.print(f"  Train rows:  {result['train_rows']}  → {result['train_path']}")
    console.print(f"  Valid rows:  {result['valid_rows']}  → {result['valid_path']}")


def main():
    parser = argparse.ArgumentParser(description="Audit and export pipeline for internal_master.jsonl")
    parser.add_argument("--master", default=str(INTERNAL_MASTER_PATH), help="Path to internal_master.jsonl")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    gate_parser = subparsers.add_parser("gate", help="Run quality gate checks")

    export_parser = subparsers.add_parser("export", help="Export to train/valid JSONL")
    export_parser.add_argument("--valid-fraction", type=float, default=0.1)
    export_parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()
    if args.cmd == "gate":
        cmd_gate(args)
    elif args.cmd == "export":
        cmd_export(args)


if __name__ == "__main__":
    main()
