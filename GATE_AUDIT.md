# GATE AUDIT

## Generation

```sh
uv run python data/audit_dataset.py gate
```

Artifact generated at `artifacts/quality_gate_report.json`. Generate this every time when user mentions this file.

## Objective

The user wants to identify any metrics that miss the mark, and how to improve the metrics. Look at `data/prepare.py` and `data/audit_dataset.py`.
