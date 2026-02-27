# Arena dei Poveri - Plan 2: Quantization Deep-Dive

## Context

A **quantization-focused** project for the Mistral AI Worldwide Hackathon Tokyo (Feb 28 - Mar 1). We take Mistral's open-weight **Ministral 8B**, quantize it ourselves to Q8, Q4, Q3, Q2, then race those quantizations side-by-side streaming in real-time. We visualize the quality vs speed vs memory tradeoff, find the "quality cliff" where quantization degrades output unacceptably, and use Mistral's API (Mistral Large) as the LLM-as-judge to score quality.

**Hackathon theme**: Satisfies Theme 2 ("API: Anything goes") via Mistral API for reference + judging. All models are Mistral's open-weight ecosystem.

**Time budget**: ~7hrs Day 1, ~6hrs Day 2 = ~13hrs total.
**Mistral API key**: Available now.

---

## Hardware Caveat

We would have loved to quantize a larger model (Mistral Small 24B or even Mistral Large 3 at 41B active params) to make the quality cliff more dramatic. However, our development hardware is a **MacBook Pro M5 with 32GB unified memory**. Since quantization requires loading the full FP16 weights into memory first:

- Ministral 8B (FP16 ~16GB) - fits comfortably in 32GB, leaves room for the quantization process
- Mistral Small 24B (FP16 ~48GB) - does not fit, cannot quantize from raw weights
- Mistral Large 3 (FP16 ~hundreds of GB) - not even close

So **Ministral 8B is the largest model we can quantize end-to-end on our hardware**. This is actually the point of the project - demonstrating what's possible when you're GPU-poor and need to find the right quality/size tradeoff.

If NVIDIA GPUs become available at the venue (they're a sponsor), we have a Path A that uses `bitsandbytes` for GPU-accelerated quantization of larger models. See the two-path strategy below.

---

## Two-Path Quantization Strategy

### Path A: GPU Available (NVIDIA CUDA)
- **Tool**: `bitsandbytes` via HuggingFace `transformers`
- **How**: Load model with `load_in_8bit=True` or `load_in_4bit=True` - quantization happens on load
- **Advantage**: Can handle larger models (24B+), faster inference, well-known in ML community
- **Model**: Could go up to Mistral Small 24B or beyond

### Path B: No GPU - Apple Silicon (our default)
- **Tool**: `MLX` + `mlx-lm` (Apple's native ML framework)
- **How**: Download FP16 weights from HuggingFace, quantize with `mlx_lm.convert --quantize --q-bits N`
- **Advantage**: We do the actual quantization ourselves (not pulling pre-quantized models), runs natively on M5 via Metal 4
- **Model**: Ministral 8B (max we can quantize with 32GB RAM)
- **Fallback**: If MLX has issues, fall back to Ollama with pre-quantized GGUF models

**We build for Path B by default** and swap to Path A if GPUs are provided at the venue.

---

## Architecture

```
Browser (React islands)        Astro Server Endpoints          MLX / Local Model     Mistral API
  |                                  |                            |                    |
  |--- POST /api/race -------------->|                            |                    |
  |    { prompt, quants[] }          |--- inference Q8 ---------->|                    |
  |                                  |--- inference Q4 ---------->|                    |
  |                                  |--- inference Q2 ---------->|                    |
  |                                  |--- stream reference -------|------------------->|
  |<-- SSE: {quant, type, data}      |<-- responses interleaved --|                    |
  |                                  |                            |                    |
  |--- POST /api/evaluate ---------->|---  judge request ---------|------------------->|
  |<-- quality scores per quant      |<-- Mistral Large scores ---|--------------------|
```

- **MLX (Path B)** or **bitsandbytes (Path A)** runs quantized Ministral 8B locally
- **Mistral API** provides: (1) gold-standard full-precision reference answer, (2) Mistral Large as LLM-as-judge
- **Astro server endpoint** multiplexes all streams into a single SSE response
- **React islands** handle the interactive arena UI

### Why MLX (Path B default)
- Apple-native, runs on Metal 4 with M5 chip
- Does real quantization (not pre-quantized downloads): `mlx_lm.convert --quantize --q-bits 4`
- Supports streaming inference via `mlx_lm.generate`
- Produces quantized model artifacts we can show as part of the demo
- Clean Python API, easy to wrap in a server

### Why Astro + React
- Astro: fast static shell, server endpoints for API proxying, lightweight
- React islands: only interactive components hydrate (arena panels, charts)
- Tailwind CSS for styling

---

## Tech Stack

| Choice | Why |
|--------|-----|
| Astro 5 | Lightweight, server endpoints, React island architecture |
| React 19 (via `@astrojs/react`) | Interactive islands for arena + charts |
| Tailwind CSS v4 | Fast styling, dark theme |
| MLX + `mlx-lm` (Python) | Quantization + local inference on Apple Silicon |
| `@mistralai/mistralai` SDK | Mistral API for reference + judging |
| Small Python server (FastAPI/Flask) | Wraps MLX inference, exposes streaming HTTP endpoint |
| No database | All state in-memory |

**Note**: Since MLX is Python and our frontend is Astro/Node, we need a thin Python server to bridge. The Astro server endpoint calls this Python server for local inference, and calls Mistral API directly for the reference/judge.

---

## Models & Quantizations

**Primary model**: Ministral 8B Instruct (open-weight, Apache 2.0)

| Quantization | Bits | Approx Size | Memory Needed | Color | Tool |
|-------------|------|-------------|---------------|-------|------|
| FP16 (base) | 16 | ~16 GB | ~18 GB | — | MLX (source for quantization) |
| Q8 | 8 | ~8.5 GB | ~10 GB | Blue | MLX `--q-bits 8` |
| Q4 | 4 | ~5 GB | ~6 GB | Emerald | MLX `--q-bits 4` |
| Q3 | 3 | ~3.5 GB | ~4.5 GB | Amber | MLX `--q-bits 3` |
| Q2 | 2 | ~3 GB | ~3.5 GB | Red | MLX `--q-bits 2` |
| Mistral API (`mistral-large-latest`) | Full | Cloud | 0 | White | API (reference + judge) |

**Quantization happens once** at startup/setup time. The quantized model directories are saved to disk and reused for all races.

**Fallback**: If MLX issues arise, pull pre-quantized GGUF models via Ollama instead.

---

## File Structure

```
/
  astro.config.mjs
  package.json
  tailwind.config.ts
  tsconfig.json
  .env                              # MISTRAL_API_KEY

  # Python inference server
  server/
    requirements.txt                # mlx-lm, fastapi, uvicorn
    app.py                          # FastAPI server wrapping MLX inference
    quantize.py                     # Script to quantize Ministral 8B to Q8/Q4/Q3/Q2

  # Astro + React frontend
  src/
    layouts/
      Layout.astro                  # Base HTML shell, fonts, dark theme

    pages/
      index.astro                   # Landing page, mounts React arena island
      api/
        race.ts                     # POST -> multiplexed SSE (local MLX + Mistral API)
        health.ts                   # GET -> check local server status + available quants
        evaluate.ts                 # POST -> Mistral Large as LLM-as-judge

    components/
      arena/
        Arena.tsx                   # Main React island (client:load)
        QuantPanel.tsx              # Single quantization streaming panel
        StreamingText.tsx           # Text renderer with blinking cursor
        MetricsBar.tsx              # TTFT, tok/s, memory, model size
        RaceControls.tsx            # Prompt input + quant selector + "Race!" button

      benchmark/
        QualityCliff.tsx            # Chart: quality vs quant level
        BenchmarkRunner.tsx         # Automated eval suite runner
        ScoreCard.tsx               # Per-quant quality breakdown

      budget/
        VramOptimizer.tsx           # Memory slider -> quant recommendation

      prompt/
        PromptLibrary.tsx           # Pre-built prompts by category

      ui/
        Header.tsx
        QuantBadge.tsx              # Colored quant level indicator

    lib/
      inference.ts                  # Client for local Python inference server
      mistral.ts                    # Mistral API client singleton
      quant-models.ts               # Quantization metadata (sizes, memory, colors)
      prompts.ts                    # Prompt library data
      metrics.ts                    # TTFT, tok/s, memory calculation
      evaluate.ts                   # Quality evaluation logic
      budget.ts                     # Memory budget optimizer math

    hooks/
      useRaceStream.ts              # Client SSE consumer, demux by quant level
      useServerStatus.ts            # Poll local inference server health

    types/
      index.ts                      # Shared TypeScript types
```

---

## Key Implementation Details

### 1. Quantization Script (`server/quantize.py`)

Run once to produce all quantization levels:

```python
# For each bit level, quantize Ministral 8B and save to disk
for bits in [8, 4, 3, 2]:
    mlx_lm.convert(
        hf_path="mistralai/Ministral-8B-Instruct-2412",
        quantize=True,
        q_bits=bits,
        output=f"./models/ministral-8b-q{bits}"
    )
```

This takes ~10-15 min per quantization on Apple Silicon. Run all 4 during setup (~45 min total, can overlap with other work).

### 2. Local Inference Server (`server/app.py`)

A FastAPI server that:
- Loads a specified quantized model on demand
- Exposes `POST /generate` with streaming response (NDJSON)
- Reports loaded model info, memory usage via `GET /health`

The Astro server endpoint calls this for local inference.

### 3. Multiplexed SSE Endpoint (`pages/api/race.ts`)

Same concept as Plan 1 but calls two backends:
- Local Python server for each quantization level
- Mistral API for the reference answer

```
SSE event shape:
  { quant: "q4", type: "token", data: "Hello", ts: 142 }
  { quant: "q4", type: "first_token", ts: 89 }
  { quant: "q4", type: "done", totalTokens: 234, totalTime: 3200, ts: 3200 }
  { quant: "reference", type: "token", data: "Hello", ts: 201 }
  { quant: "q2", type: "error", message: "Model not loaded", ts: 50 }
```

### 4. Quality Evaluation (`pages/api/evaluate.ts`)

After a race, call **Mistral Large** (`mistral-large-latest`) via API as LLM-as-judge:
- Send all quantized outputs + the reference output
- Ask for 1-10 scores on: accuracy, coherence, completeness
- Return per-quant scores
- This powers the "quality cliff" chart

### 5. Quality Cliff Visualization (`QualityCliff.tsx`)

A chart showing:
- X-axis: quantization level (Q8 → Q4 → Q3 → Q2)
- Y-axis (left): quality score (from Mistral Large judge)
- Y-axis (right): tokens/sec speed
- Highlighted "cliff" point where quality drops sharply

### 6. Memory Budget Optimizer (`budget.ts`)

```
Input:  { availableMemory: number } // in GB
Output: { recommended: "q4", fits: [...], explanation: string }
```

Pure math based on known model sizes. Visual "what fits" bar diagram.

### 7. Sequential Racing (Memory Constraint)

On 32GB M5 MacBook, we can't load all quants simultaneously. Racing is **sequential**:
- Run Q8 inference, collect result
- Unload, load Q4, run inference
- Repeat for Q3, Q2
- Mistral API reference runs in parallel with any local inference
- UI shows results appearing panel by panel (still compelling visually)

---

## Day-by-Day Schedule

### DAY 1 (Saturday) - ~7 hours

**Hour 0-1.5: Bootstrap + Quantization**
- `npm create astro@latest` with React + Tailwind
- Set up Python env: `pip install mlx-lm fastapi uvicorn`
- Install: `@mistralai/mistralai`
- **Start quantization** of Ministral 8B to Q8/Q4/Q3/Q2 (runs in background ~45 min)
- Verify Mistral API connectivity
- **Checkpoint**: Astro runs, quantization running in background

**Hour 1.5-3: Python Inference Server**
- `server/app.py` - FastAPI server wrapping MLX inference with streaming
- `server/quantize.py` - quantization script (already running)
- Test: load Q4 model, send prompt, get streaming response
- Verify quantized models are saved to disk
- **Checkpoint**: Can load any quant level and stream inference locally

**Hour 3-5: Core Streaming Pipeline + Arena UI**
- `pages/api/race.ts` - multiplexed SSE (local server + Mistral API)
- `pages/api/health.ts` - check local server + available quants
- `hooks/useRaceStream.ts` - client SSE consumer
- `Arena.tsx`, `QuantPanel.tsx`, `StreamingText.tsx`, `MetricsBar.tsx`, `RaceControls.tsx`
- Wire onto `index.astro`
- **Checkpoint**: Working arena - select quants, type prompt, see panels stream

**Hour 5-6.5: Metrics + Prompt Library**
- `lib/metrics.ts` - TTFT, tok/s, model size display
- Live metric counters in each panel
- `lib/prompts.ts` + `PromptLibrary.tsx` - pre-built prompts
- **Checkpoint**: Metrics work, prompts are clickable

**Hour 6.5-7: Error Handling + Status**
- `hooks/useServerStatus.ts` - check if local server is running
- Setup guide panel if server isn't detected
- Graceful per-panel errors
- **Checkpoint**: END OF DAY 1 - Functional arena with local quantized inference

### DAY 2 (Sunday) - ~6 hours

**Hour 0-1.5: Quality Evaluation + Cliff Chart**
- `pages/api/evaluate.ts` - Mistral Large as LLM-as-judge
- `lib/evaluate.ts` - evaluation prompt template
- `QualityCliff.tsx` - SVG chart: quality vs quant level with speed overlay
- `ScoreCard.tsx` - per-quant score breakdown
- **Checkpoint**: Quality cliff visualization works

**Hour 1.5-2.5: Memory Budget Optimizer**
- `lib/budget.ts` - memory → quant recommendation logic
- `VramOptimizer.tsx` - memory slider, visual "what fits" bar, recommendation card
- **Checkpoint**: Budget optimizer works

**Hour 2.5-3.5: Benchmark Runner**
- `BenchmarkRunner.tsx` - run 5-10 prompts across all quants automatically
- Aggregate scores into quality cliff chart
- Summary: "Q4 retains 94% of Q8 quality at 1.6x speed"
- **Checkpoint**: Automated benchmarking works

**Hour 3.5-5: Visual Polish + Demo Prep**
- `Header.tsx` with "Arena dei Poveri" branding
- Dark theme refinement (zinc-950 base)
- Panel animations, first-to-finish indicator
- Mobile responsiveness
- Prepare demo prompts that showcase the quality cliff
- End-to-end test
- **Checkpoint**: Demo-ready

**Hour 5-6: Buffer**
- Bug fixes only
- Record backup demo video

---

## Mistral Tie-In (for judges)

1. **All models are Mistral** - Ministral 8B is a Mistral open-weight model (Apache 2.0)
2. **Mistral API as gold standard** - full-precision cloud reference in every race
3. **Mistral Large as judge** - LLM-as-judge via API scores each quantization level
4. **Story**: "We quantized Mistral's Ministral 8B ourselves on a MacBook, raced Q8/Q4/Q3/Q2, and used Mistral Large via API to find exactly where quality breaks down. Here's the cliff."

---

## Risks & Fallbacks

| Risk | Fallback |
|------|----------|
| MLX quantization fails or too slow | Fall back to llama.cpp `quantize` (CPU-based, slower but reliable) |
| llama.cpp also fails | Fall back to Ollama with pre-quantized GGUF models (loses "we quantized it" angle) |
| Sequential racing feels slow to demo | Pre-run races and cache results. Live demo shows cached + one live race. |
| 32GB not enough for Q8 inference + OS | Drop Q8, race Q4/Q3/Q2 only. Q8 shown from cached result. |
| Python server unreliable | Use `mlx_lm.generate` CLI via subprocess, or swap to `llama-cpp-python` bindings |
| Quality differences too subtle | Use reasoning/math prompts that expose quality gaps. Q2 always shows visible degradation. |
| NVIDIA GPUs available at venue | Switch to Path A (bitsandbytes), can quantize larger models (24B+) |

### No-GPU Fallback Chain (Path B)

If our primary tool (MLX) has issues, we degrade through this chain:

```
MLX (mlx-lm)          ← PRIMARY: Apple-native, real quantization, Metal 4 inference
  ↓ if fails
llama.cpp              ← BACKUP 1: CPU quantization (./quantize), Metal inference. Well-tested, C++.
  ↓ if fails
llama-cpp-python       ← BACKUP 2: Python bindings for llama.cpp. Easier FastAPI integration.
  ↓ if fails
Ollama                 ← BACKUP 3: Pre-quantized GGUF pulls only. No DIY quantization. One-command setup.
  ↓ if fails
CTranslate2            ← BACKUP 4: CPU-optimized, but limited to INT8 (no Q4/Q2). Last resort.
```

All of these run on Apple Silicon without NVIDIA. The key difference is whether we do the quantization ourselves (MLX, llama.cpp) or use pre-quantized models (Ollama, llama-cpp-python with GGUF files).

---

## Verification

1. **Quantization**: Run `quantize.py`, confirm 4 model directories created (Q8/Q4/Q3/Q2) with expected sizes
2. **Local inference**: Hit Python server `/generate` with each quant, confirm streaming response
3. **Streaming**: Race Q4 + Q2 + reference, confirm all panels stream with correct labels
4. **Metrics**: TTFT should differ between Q8 (slower) and Q2 (faster)
5. **Quality cliff**: Judge a race, confirm chart shows scores decreasing Q8 → Q2
6. **Memory optimizer**: Select 8GB memory, confirm it recommends Q4 (not Q8)
7. **Error handling**: Stop Python server, confirm UI shows setup guide
8. **Benchmark**: Run automated suite, confirm aggregate chart populates
