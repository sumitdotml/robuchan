"""
Push the repo to sumitdotml/arena-dei-poveri on Hugging Face.

Uses upload_folder with create_pr=True to open a PR
without requiring direct push access to main.
Ignore patterns are read from .hfignore at the repo root.

Usage:
    uv run python scripts/push_to_hf.py [--repo-type dataset]
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

REPO_ID = "sumitdotml/arena-dei-poveri"
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_hfignore(repo_root: Path) -> list[str]:
    hfignore = repo_root / ".hfignore"
    if not hfignore.exists():
        return []
    patterns = []
    for line in hfignore.read_text().splitlines():
        stripped = line.strip()
        # skip blank lines, comments, and negation rules (not supported by ignore_patterns)
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            continue
        patterns.append(stripped)
    return patterns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-type",
        default="dataset",
        choices=["dataset", "model", "space"],
        help="HF repo type (default: dataset)",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not found in .env")

    ignore_patterns = load_hfignore(REPO_ROOT)
    print(f"Loaded {len(ignore_patterns)} ignore patterns from .hfignore")

    api = HfApi(token=token)

    print(f"Uploading {REPO_ROOT} → {REPO_ID} (type={args.repo_type})...")
    result = api.upload_folder(
        folder_path=str(REPO_ROOT),
        repo_id=REPO_ID,
        repo_type=args.repo_type,
        ignore_patterns=ignore_patterns,
        create_pr=True,
        commit_message="Upload from push_to_hf.py",
    )

    print(f"\nDone. PR: {result}")


if __name__ == "__main__":
    main()
