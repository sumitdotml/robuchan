#!/usr/bin/env python3
"""Launch TRL fine-tuning as an HF Job on a T4 GPU.

Prerequisites:
  - HF Pro account, Team/Enterprise org, or hackathon org with GPU access
  - HF_TOKEN with write access
  - WANDB_API_KEY (optional, for training curves)

Note on learning rate: TRL + LoRA defaults to 2e-4 (standard for adapter-only
training where only a small fraction of weights update). This is intentionally
higher than Mistral API's 1e-4 recommendation for their internal LoRA implementation.

Usage:
  uv run python train/launch_hf_job.py
  uv run python train/launch_hf_job.py --flavor t4-medium --timeout 2h
  uv run python train/launch_hf_job.py --status JOB_ID
  uv run python train/launch_hf_job.py --logs JOB_ID
  uv run python train/launch_hf_job.py --cancel JOB_ID
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv


def get_token() -> str:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("error: HF_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    return token


def cmd_launch(args: argparse.Namespace) -> int:
    from huggingface_hub import run_job

    token = get_token()
    wandb_key = os.environ.get("WANDB_API_KEY", "")

    secrets = {"HF_TOKEN": token}
    if wandb_key:
        secrets["WANDB_API_KEY"] = wandb_key
        print(f"W&B enabled: project={args.wandb_project}")
    else:
        print("W&B disabled (WANDB_API_KEY not set)")

    env = {
        "WANDB_PROJECT": args.wandb_project,
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
    }

    # Build the training command.
    # The stock pytorch image is bare — install git + deps, then clone and run.
    github_repo = args.github_repo
    train_cmd = [
        "bash",
        "-c",
        "apt-get update -qq && apt-get install -y -qq git > /dev/null"
        " && pip install -q git+https://github.com/huggingface/transformers trl peft wandb bitsandbytes datasets hf_transfer accelerate"
        f" && git clone https://github.com/{github_repo}.git repo && cd repo"
        " && python train/train_trl.py"
        f" --base-model {args.base_model}"
        f" --dataset {args.dataset}"
        f" --num-train-epochs {args.num_train_epochs}"
        f" --learning-rate {args.learning_rate}"
        f" --lora-r {args.lora_r}"
        " --push-to-hub"
        f" --hub-model-id {args.hub_model_id}"
        + (" --use-4bit" if args.use_4bit else ""),
    ]

    print(f"launching HF Job: flavor={args.flavor}, timeout={args.timeout}")
    print(
        f"model={args.base_model}, epochs={args.num_train_epochs}, lr={args.learning_rate}"
    )

    job = run_job(
        image="pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel",
        command=train_cmd,
        flavor=args.flavor,
        timeout=args.timeout,
        secrets=secrets,
        env=env,
        token=token,
    )

    print("\njob launched!")
    print(f"  id:  {job.id}")
    print(f"  url: {job.url}")
    print("\nmonitor with:")
    print(f"  uv run python train/launch_hf_job.py --status {job.id}")
    print(f"  uv run python train/launch_hf_job.py --logs {job.id}")
    return 0


def cmd_status(job_id: str) -> int:
    from huggingface_hub import inspect_job

    token = get_token()
    info = inspect_job(job_id=job_id, token=token)
    print(f"job:    {job_id}")
    print(f"stage:  {info.status.stage}")
    print(f"flavor: {info.flavor}")
    return 0


def cmd_logs(job_id: str) -> int:
    from huggingface_hub import fetch_job_logs

    token = get_token()
    for line in fetch_job_logs(job_id=job_id, follow=True, token=token):
        print(line, end="")
    return 0


def cmd_cancel(job_id: str) -> int:
    from huggingface_hub import cancel_job

    token = get_token()
    cancel_job(job_id=job_id, token=token)
    print(f"cancelled: {job_id}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    # Job management
    parser.add_argument(
        "--status", type=str, metavar="JOB_ID", help="Check job status."
    )
    parser.add_argument("--logs", type=str, metavar="JOB_ID", help="Stream job logs.")
    parser.add_argument("--cancel", type=str, metavar="JOB_ID", help="Cancel a job.")

    # Launch config
    parser.add_argument("--flavor", type=str, default="t4-medium")
    parser.add_argument("--timeout", type=str, default="2h")

    # Training config
    parser.add_argument(
        "--base-model", type=str, default="mistralai/Ministral-3-3B-Instruct-2512"
    )
    parser.add_argument("--dataset", type=str, default="sumitdotml/robuchan-data")
    parser.add_argument("--num-train-epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument(
        "--use-4bit", action="store_true", help="Use QLoRA (4-bit quantization)."
    )
    parser.add_argument("--hub-model-id", type=str, default="sumitdotml/robuchan")
    parser.add_argument(
        "--wandb-project", type=str, default=os.environ.get("WANDB_PROJECT", "robuchan")
    )
    parser.add_argument(
        "--github-repo",
        type=str,
        default="sumitdotml/robuchan",
        help="GitHub repo to clone into the container.",
    )

    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    if args.status:
        return cmd_status(args.status)
    if args.logs:
        return cmd_logs(args.logs)
    if args.cancel:
        return cmd_cancel(args.cancel)

    return cmd_launch(args)


if __name__ == "__main__":
    raise SystemExit(main())
