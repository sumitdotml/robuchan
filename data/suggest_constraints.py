"""
suggest_constraints.py — review potential constraint gaps from source_pool_summary.json
and suggest terms to add to eval/constraints.json.

Usage:
    uv run python data/suggest_constraints.py [--summary PATH] [--constraints PATH]
"""

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_SUMMARY = REPO_ROOT / "artifacts" / "source_pool_summary.json"
DEFAULT_CONSTRAINTS = REPO_ROOT / "eval" / "constraints.json"

# Strips leading quantity/unit prefix before suggesting a term
_QUANTITY_RE = re.compile(
    r"^\s*"
    r"(\d+\s*/\s*\d+|\d+\.\d+|\d+)"          # fraction, decimal, or int
    r"(\s*-\s*(\d+\s*/\s*\d+|\d+\.\d+|\d+))?"  # optional range upper bound
    r"\s*"
    r"(cups?|tbsps?|tablespoons?|tsps?|teaspoons?|lbs?|pounds?|ozs?|ounces?|"
    r"g|grams?|kg|ml|liters?|litres?|quarts?|pints?|gallons?|cans?|"
    r"packages?|pkgs?|envelopes?|bunches?|heads?|cloves?|stalks?|slices?|"
    r"pieces?|sprigs?|leaves?|jars?|bottles?|bags?|boxes?|"
    r"small|medium|large|whole|fresh|dried|frozen|raw|cooked)?"
    r"\s*",
    re.IGNORECASE,
)


def strip_quantity(raw: str) -> str:
    cleaned = _QUANTITY_RE.sub("", raw.strip(), count=1).strip()
    return re.sub(r"\s{2,}", " ", cleaned) or raw.strip()


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def suggest(summary_path: Path, constraints_path: Path) -> None:
    summary = load_json(summary_path)
    constraints = load_json(constraints_path)

    coverage: dict = summary.get("constraints_coverage_check", {})
    known_fps: list[str] = [
        fp.split("(")[0].strip().lower()
        for fp in constraints.get("_meta", {}).get("known_false_positives", [])
    ]

    # Ordered exactly as they appear in constraints.json
    ordered_categories = [k for k in constraints if k != "_meta"]

    any_gaps = False

    for category in ordered_categories:
        cat_data = coverage.get(category)
        if cat_data is None:
            print(f"\n[{category}] — not found in coverage check, skipping")
            continue

        gaps_count: int = cat_data.get("potential_gaps_count", 0)
        gaps_sample: list[str] = cat_data.get("potential_gaps_sample", [])
        banned_terms = [b.lower() for b in constraints[category].get("banned", [])]

        print(f"\n{'='*60}")
        print(f"  {category.upper()}")
        print(f"  {cat_data['matched_ingredients']:,} matched | {gaps_count} potential gap(s)")
        print(f"{'='*60}")

        if not gaps_sample:
            print("  No gaps detected. OK.")
            continue

        any_gaps = True
        rows: list[tuple[str, str, str]] = []  # (cleaned, raw, tag)

        for raw in gaps_sample:
            cleaned = strip_quantity(raw)
            cleaned_lower = cleaned.lower()

            if cleaned_lower in banned_terms:
                tag = "SKIP (already banned)"
            elif any(fp in cleaned_lower for fp in known_fps):
                tag = "SKIP (known false positive)"
            else:
                tag = "SUGGEST ADD"

            rows.append((cleaned, raw, tag))

        col_w = max(len(c) for c, _, _ in rows) + 2
        print(f"  {'Cleaned term':<{col_w}}  {'Tag':<28}  Raw")
        print(f"  {'-'*col_w}  {'-'*28}  {'-'*35}")
        for cleaned, raw, tag in rows:
            print(f"  {cleaned:<{col_w}}  {tag:<28}  {raw}")

        add_these = [c for c, _, t in rows if t == "SUGGEST ADD"]
        if add_these:
            print(f"\n  Suggested additions to \"{category}\".banned:")
            for term in add_these:
                print(f'    "{term}",')

    if not any_gaps:
        print("\nAll categories: no gaps found. Constraints coverage looks complete.")
    else:
        print("\n\nVerify each SUGGEST ADD term is a genuine violation before adding to constraints.json.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest constraint additions from coverage gaps.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--constraints", type=Path, default=DEFAULT_CONSTRAINTS)
    args = parser.parse_args()

    if not args.summary.exists():
        print(f"Error: {args.summary} not found. Run `uv run python data/prepare.py ingest` first.")
        raise SystemExit(1)
    if not args.constraints.exists():
        print(f"Error: {args.constraints} not found.")
        raise SystemExit(1)

    print(f"Summary    : {args.summary}")
    print(f"Constraints: {args.constraints}")
    suggest(args.summary, args.constraints)


if __name__ == "__main__":
    main()
