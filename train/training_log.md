# Training Log

## Glossary

- **train/loss**: Cross-entropy loss on training data during optimization. Measures how well the model predicts the next token on training examples. Lower = better. This is NOT validation loss.
- **eval/loss**: Cross-entropy loss on the held-out validation set (122 rows). Computed at the end of each epoch. This measures generalization — whether the model learns patterns vs just memorizing training data.
- **epoch**: One full pass through all 1,090 training rows.
- **step**: One optimizer update. With batch_size=1 and gradient_accumulation=16, each step processes 16 training examples.
- **QLoRA**: 4-bit quantized LoRA. The base model weights are frozen in 4-bit precision; only small adapter matrices (~2-8M params out of 8B) are trained.

## What "loss going from 1.07 to 0.80" means

The model starts at ~1.07 cross-entropy loss on our recipe data — this is the base Ministral 8B's performance before any fine-tuning. As training progresses, the loss drops, meaning the model is getting better at predicting the correct recipe adaptations. By 0.80 (~half an epoch), it's already significantly better at the task.

A healthy training run shows:
- train/loss: steady decline, possibly with small fluctuations
- eval/loss: decline that tracks train/loss (good generalization) or flattens (saturation) — if it goes UP while train/loss goes down, that's overfitting

## Configuration

- **Base model**: mistralai/Ministral-8B-Instruct-2410
- **Method**: QLoRA (r=16, alpha=32, targets: q/k/v/o projections, 4-bit NF4)
- **Training data**: 1,090 rows (sumitdotml/robuchan-data)
- **Validation data**: 122 rows
- **Learning rate**: 2e-4 with cosine schedule, 3% warmup
- **Effective batch size**: 16 (batch=1 x grad_accum=16)
- **Max sequence length**: 2048
- **GPU**: A10G-large (24GB VRAM)
- **Steps per epoch**: ~68

## Active Runs

### Run: peach-universe-2 (3-epoch)
- **Job ID**: 69a3be8a5672f75936770486
- **W&B**: https://wandb.ai/sumit-ml/robuchan/runs/fqnvyepk
- **Target**: 3 epochs (~204 steps)

| Timestamp (UTC) | Step | Epoch | train/loss | eval/loss | Notes |
|---|---|---|---|---|---|
| 2026-03-01 04:23 | 0 | 0.00 | ~1.07 | — | training started |
| 2026-03-01 ~04:35 | 7 | 0.59 | 0.80 | — | steady decline |

### Run: super-hill-3 (1-epoch)
- **Job ID**: 69a3bfdf5672f7593677048a
- **W&B**: https://wandb.ai/sumit-ml/robuchan/runs/041y2omh
- **Target**: 1 epoch (~68 steps)

| Timestamp (UTC) | Step | Epoch | train/loss | eval/loss | Notes |
|---|---|---|---|---|---|
| 2026-03-01 04:29 | 0 | 0.00 | ~1.07 | — | training started |
| 2026-03-01 ~04:35 | 3 | 0.29 | 0.90 | — | declining |

## Failed/Cancelled Runs

| Run | Job ID | Reason |
|---|---|---|
| fanciful-donkey-1 | 69a3bb6adfb316ac3f7c08ac | Cancelled (T4 too slow, switched to A10G) |
| — | 69a3b9fadfb316ac3f7c08a2 | Mistral3Config error (3B model incompatible) |
| — | 69a3b7c35672f7593677046b | git clone auth failure (repo was private) |
| — | 69a3b51e5672f75936770461 | git not installed in container |
