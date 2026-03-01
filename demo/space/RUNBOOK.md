# Robuchan HF Space Deployment Runbook

Deploy the Gradio demo to `sumitdotml/robuchan-demo` on Hugging Face Spaces.

## Prerequisites

- `hf` CLI installed ([docs](https://huggingface.co/docs/huggingface_hub/en/guides/cli))
- Authenticated with a write-access token
- Files ready in `demo/space/`: `app.py`, `requirements.txt`, `README.md`

## Step 0: Install hf CLI (if needed)

```bash
curl -LsSf https://hf.co/cli/install.sh | bash
```

Or via uvx (no install needed):

```bash
uvx hf --help
```

## Step 1: Authenticate

```bash
hf auth login
# Paste your token when prompted (needs write access)
# Say yes to saving as git credential
```

Verify:

```bash
hf auth whoami
# Should print: sumitdotml
```

## Step 2: Create the Space

```bash
hf repos create robuchan-demo --repo-type space --space-sdk gradio
```

Expected output:

```
Successfully created sumitdotml/robuchan-demo on the Hub.
Your repo is now available at https://huggingface.co/spaces/sumitdotml/robuchan-demo
```

If the Space already exists, add `--exist-ok`:

```bash
hf repos create robuchan-demo --repo-type space --space-sdk gradio --exist-ok
```

## Step 3: Upload files

From the repo root:

```bash
hf upload sumitdotml/robuchan-demo demo/space . --repo-type space \
  --commit-message "Initial Gradio demo for robuchan recipe adapter"
```

This uploads the contents of `demo/space/` (app.py, requirements.txt, README.md) to the root of the Space repo.

Expected output:

```
https://huggingface.co/spaces/sumitdotml/robuchan-demo/tree/main/
```

## Step 4: Set hardware to T4

The `README.md` frontmatter includes `suggested_hardware: t4-small`, but you may need to set it manually in Space settings:

1. Go to https://huggingface.co/spaces/sumitdotml/robuchan-demo/settings
2. Under **Space Hardware**, select **T4 small**
3. Click **Save**

(Requires HF Pro or a hardware grant.)

## Step 5: Wait for build

The Space will auto-build on push. Monitor the build log:

1. Go to https://huggingface.co/spaces/sumitdotml/robuchan-demo
2. Click the **Logs** tab (or the "Building" badge)
3. Wait for "Running on local URL" in the logs

Build typically takes 3-5 minutes (dependency install + model download on first boot).

## Step 6: Verify

### Quick smoke test

1. Open https://huggingface.co/spaces/sumitdotml/robuchan-demo
2. Click the first example (tonkotsu ramen, vegan) and hit **Submit**
3. Wait for generation (~30-60s on T4)
4. Confirm output contains all 5 sections:
   - Substitution Plan
   - Adapted Ingredients
   - Adapted Steps
   - Flavor Preservation Notes
   - Constraint Check

### Full verification

Run both pre-loaded examples:

| Example | Constraint | Check |
|---------|-----------|-------|
| Tonkotsu ramen | vegan | No pork/eggs/animal products in adapted recipe |
| Japanese curry | gluten_free | No wheat flour/soy sauce in adapted recipe |

Also test a custom input: paste any recipe, select a constraint, verify structured output.

## Updating the Space

After editing files in `demo/space/`, re-upload:

```bash
hf upload sumitdotml/robuchan-demo demo/space . --repo-type space \
  --commit-message "description of changes"
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Build fails on `bitsandbytes` | Needs CUDA runtime. Verify hardware is set to T4, not CPU. |
| OOM during model load | T4 has 16GB VRAM. 4-bit quantization should fit 8B model. If OOM, check no other process is using GPU. Restart Space. |
| "Model not found" error | Verify `sumitdotml/robuchan` adapter is public (or set `HF_TOKEN` as a Space secret). |
| Space stuck on "Building" | Check build logs for pip install errors. May need to pin a specific torch version in requirements.txt. |
| Slow first inference | Expected. First request triggers CUDA kernel compilation. Subsequent requests are faster. |
