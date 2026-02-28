"""
Push the repo to sumitdotml/arena-dei-poveri on Hugging Face.

Uses upload_large_folder for chunked, resumable uploads.
Note: create_pr and commit_message are not supported by upload_large_folder.

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

    api = HfApi(token=token)

    print(f"Uploading {REPO_ROOT} → {REPO_ID} (type={args.repo_type})...")
    api.upload_large_folder(
        folder_path=str(REPO_ROOT),
        repo_id=REPO_ID,
        repo_type=args.repo_type,
        ignore_patterns=[
            ".env",
            ".env.local",
            "artifacts/**",
            "data/*.jsonl",
            "eval/results_*.json",
            "train/job_result.json",
            "**/__pycache__/**",
            "**/*.pyc",
            "**/*.egg-info/**",
            "dist/**",
            "build/**",
            ".hf_cache/**",
            ".hf-cache/**",
            ".DS_Store",
            "node_modules/**",
        ],
    )

    print(f"\nDone. Check https://huggingface.co/{REPO_ID}")


if __name__ == "__main__":
    main()
