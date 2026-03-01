"""
Push the repo to Hugging Face dataset/model repos.

Uses upload_folder with create_pr=True to open a PR
without requiring direct push access to main.
Ignore patterns are read from .hfignore at the repo root.

Usage:
    uv run python scripts/push_to_hf.py                      # dataset -> sumitdotml/robuchan-data
    uv run python scripts/push_to_hf.py --repo-type model   # model   -> sumitdotml/robuchan
    uv run python scripts/push_to_hf.py --repo-id sumitdotml/custom-repo
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

DEFAULT_REPO_IDS = {
    "dataset": "sumitdotml/robuchan-data",
    "model": "sumitdotml/robuchan",
}
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
    parser.add_argument(
        "--repo-id",
        default=None,
        help=(
            "HF repo id override. Defaults: "
            "dataset->sumitdotml/robuchan-data, model->sumitdotml/robuchan"
        ),
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not found in .env")

    ignore_patterns = load_hfignore(REPO_ROOT)
    print(f"Loaded {len(ignore_patterns)} ignore patterns from .hfignore")

    api = HfApi(token=token)
    repo_id = args.repo_id or DEFAULT_REPO_IDS.get(args.repo_type)
    if not repo_id:
        raise RuntimeError(
            f"No default repo configured for repo_type={args.repo_type!r}; "
            "pass --repo-id explicitly."
        )

    print(f"Uploading {REPO_ROOT} → {repo_id} (type={args.repo_type})...")
    result = api.upload_folder(
        folder_path=str(REPO_ROOT),
        repo_id=repo_id,
        repo_type=args.repo_type,
        ignore_patterns=ignore_patterns,
        create_pr=True,
        commit_message="Upload from push_to_hf.py",
    )

    print(f"\nDone. PR: {result}")


if __name__ == "__main__":
    main()
