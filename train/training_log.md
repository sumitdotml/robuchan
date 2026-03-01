# Training Log

## Glossary

- **train/loss**: Cross-entropy loss on training data during optimization. Measures how well the model predicts the next token on training examples. Lower = better. This is NOT validation loss.
- **eval/loss**: Cross-entropy loss on the held-out validation set (122 rows). Computed at the end of each epoch. Measures generalization — whether the model learns patterns vs just memorizing training data.
- **epoch**: One full pass through all 1,090 training rows.
- **step (global_step)**: One optimizer update. Step count depends on batch size and gradient accumulation.
- **QLoRA**: 4-bit quantized LoRA. The base model weights are frozen in 4-bit precision; only small adapter matrices (~2-8M params out of 8B) are trained.
- **mean_token_accuracy**: Fraction of next-token predictions that are exactly correct during training.

## Configuration (Common)

- **Base model**: mistralai/Ministral-8B-Instruct-2410
- **Method**: QLoRA (r=16, alpha=32, targets: q/k/v/o projections, 4-bit NF4)
- **Training data**: 1,090 rows (sumitdotml/robuchan-data)
- **Validation data**: 122 rows
- **Learning rate**: 2e-4 with cosine schedule, 3% warmup
- **Max sequence length**: 2048

---

## decent-eon-4 — H200 3-epoch (SUCCESS)

**W&B Run:** [`sumit-ml/robuchan/bwsoosim`](https://wandb.ai/sumit-ml/robuchan/runs/bwsoosim)
**Job ID:** `69a3c88fdfb316ac3f7c093d`
**GPU:** H200 (141GB VRAM)
**Batch config:** per_device_train_batch_size=8, gradient_accumulation_steps=2 (effective batch=16)
**Steps per epoch:** ~69
**Total runtime:** 849 seconds (~14 minutes)
**Outcome:** SUCCESS — adapter pushed to [`sumitdotml/robuchan`](https://huggingface.co/sumitdotml/robuchan)

| Step | Epoch | train/loss | eval/loss | accuracy | lr |
|------|-------|------------|-----------|----------|----|
| 5 | 0.073 | 1.3730 | — | 0.6724 | 0.000114 |
| 10 | 0.146 | 1.1424 | — | 0.7073 | 0.000200 |
| 15 | 0.219 | 0.9859 | — | 0.7374 | 0.000199 |
| 20 | 0.292 | 0.9135 | — | 0.7517 | 0.000198 |
| 25 | 0.365 | 0.8448 | — | 0.7656 | 0.000196 |
| 30 | 0.438 | 0.8533 | — | 0.7626 | 0.000194 |
| 35 | 0.511 | 0.8248 | — | 0.7676 | 0.000191 |
| 40 | 0.584 | 0.8031 | — | 0.7724 | 0.000188 |
| 45 | 0.657 | 0.7602 | — | 0.7816 | 0.000184 |
| 50 | 0.730 | 0.7965 | — | 0.7739 | 0.000179 |
| 55 | 0.803 | 0.7610 | — | 0.7851 | 0.000174 |
| 60 | 0.876 | 0.7475 | — | 0.7861 | 0.000168 |
| 65 | 0.949 | 0.7485 | — | 0.7850 | 0.000163 |
| 69 | 1.000 | — | **0.7395** | — | — |
| 70 | 1.015 | 0.7378 | — | 0.7854 | 0.000156 |
| 75 | 1.088 | 0.7053 | — | 0.7948 | 0.000150 |
| 80 | 1.161 | 0.6977 | — | 0.7966 | 0.000143 |
| 85 | 1.234 | 0.7039 | — | 0.7953 | 0.000135 |
| 90 | 1.307 | 0.6769 | — | 0.8001 | 0.000128 |
| 95 | 1.380 | 0.6947 | — | 0.7956 | 0.000120 |
| 100 | 1.453 | 0.6739 | — | 0.8017 | 0.000113 |
| 105 | 1.526 | 0.6912 | — | 0.8005 | 0.000105 |
| 110 | 1.599 | 0.6844 | — | 0.8006 | 0.000097 |
| 115 | 1.672 | 0.6649 | — | 0.8038 | 0.000089 |
| 120 | 1.745 | 0.6811 | — | 0.8028 | 0.000081 |
| 125 | 1.818 | 0.6551 | — | 0.8089 | 0.000074 |
| 130 | 1.891 | 0.6739 | — | 0.8035 | 0.000066 |
| 135 | 1.964 | 0.6819 | — | 0.8022 | 0.000059 |
| 138 | 2.000 | — | **0.7072** | — | — |
| 140 | 2.029 | 0.6276 | — | 0.8159 | 0.000052 |
| 145 | 2.102 | 0.6285 | — | 0.8130 | 0.000045 |
| 150 | 2.175 | 0.6142 | — | 0.8183 | 0.000039 |
| 155 | 2.248 | 0.6217 | — | 0.8159 | 0.000033 |
| 160 | 2.321 | 0.6317 | — | 0.8143 | 0.000027 |
| 165 | 2.394 | 0.6240 | — | 0.8160 | 0.000022 |
| 170 | 2.467 | 0.6028 | — | 0.8203 | 0.000017 |
| 175 | 2.540 | 0.6203 | — | 0.8176 | 0.000013 |
| 180 | 2.613 | 0.6197 | — | 0.8168 | 0.000010 |
| 185 | 2.686 | 0.6177 | — | 0.8191 | 0.000006 |
| 190 | 2.759 | 0.6202 | — | 0.8155 | 0.000004 |
| 195 | 2.832 | 0.6062 | — | 0.8215 | 0.000002 |
| 200 | 2.905 | 0.6207 | — | 0.8160 | 0.000001 |
| 205 | 2.978 | 0.6327 | — | 0.8155 | 0.000000 |
| 207 | 3.000 | — | **0.7065** | — | — |

### Summary

- **train/loss**: 1.373 → 0.603 (56% reduction over 3 epochs)
- **eval/loss**: 0.7395 (epoch 1) → 0.7072 (epoch 2) → 0.7065 (epoch 3)
- **token accuracy**: 0.672 → 0.822 (from 67% to 82% correct next-token predictions)
- **Observations**: eval/loss improved from epoch 1→2 but plateaued at epoch 3 (0.7072 → 0.7065), suggesting diminishing returns from further training. No overfitting — eval/loss never increased.

---

## lyric-snowball-5 — A10G 1-epoch backup (RUNNING)

**W&B Run:** [`sumit-ml/robuchan/p50dki7k`](https://wandb.ai/sumit-ml/robuchan/runs/p50dki7k)
**Job ID:** `69a3c8905672f7593677049b`
**GPU:** A10G-large (24GB VRAM)
**Batch config:** per_device_train_batch_size=1, gradient_accumulation_steps=16 (effective batch=16)
**Flags:** `--no-eval` (eval disabled to avoid OOM)
**Steps per epoch:** ~68

| Step | Epoch | train/loss | accuracy |
|------|-------|------------|----------|
| 5 | 0.073 | 1.3449 | — |
| 10 | 0.147 | 1.0721 | — |
| 15 | 0.220 | 0.9564 | — |
| 20 | 0.294 | 0.8990 | — |
| 25 | 0.367 | 0.8381 | — |
| 30 | 0.440 | 0.8524 | — |
| 35 | 0.514 | 0.8276 | — |
| 40 | 0.587 | 0.8087 | — |

---

## Failed Runs

| Run | Job ID | GPU | Failure | Root Cause |
|-----|--------|-----|---------|------------|
| super-hill-3 | `69a3bfdf5672f7593677048a` | A10G | OOM at epoch 0.95 | eval_strategy="epoch" caused VRAM spike at epoch boundary on 24GB GPU |
| peach-universe-2 | `69a3be8a5672f75936770486` | A10G | OOM at epoch 0.95 | Same — eval pass OOM on 24GB |
| fanciful-donkey-1 | `69a3bb6adfb316ac3f7c08ac` | T4 | Cancelled | T4 too slow; switched to A10G |
| — | `69a3b9fadfb316ac3f7c08a2` | T4 | Mistral3Config error | Dec 2025 Ministral 3B uses multimodal arch, incompatible with AutoModelForCausalLM |
| — | `69a3b7c35672f7593677046b` | T4 | git clone auth failure | GitHub repo was private |
| — | `69a3b51e5672f75936770461` | T4 | git not found | pytorch docker image has no git; fixed with apt-get install |

## Lessons Learned

1. **eval_strategy="epoch" causes OOM on tight GPUs** — the eval pass allocates extra VRAM on top of training state. Fix: use `--no-eval` on 24GB GPUs, or use 48GB+ GPU.
2. **H200 (141GB) is ideal for 8B QLoRA** — batch_size=8 with full eval, 3 epochs in 14 minutes. The extra VRAM eliminates OOM risk entirely.
3. **Dec 2025 Ministral 3B models are multimodal** — they use `Mistral3ForConditionalGeneration`, not `MistralForCausalLM`. Only the Oct 2024 8B model is compatible with standard CausalLM training.
4. **Container images need explicit deps** — `pytorch/pytorch:*-devel` images don't include git. Always install system deps before cloning.
