# Arena dei Poveri - Plan 1: API Model Racing

## Context

Building **"Arena dei Poveri"** (Arena of the Poor) - a real-time model comparison arena for the **Mistral AI Worldwide Hackathon Tokyo** (Feb 28 - Mar 1, 2026). The concept: race multiple Mistral models side-by-side on the same prompt, streaming responses with live metrics (TTFT, tokens/sec, cost). Includes a Budget Optimizer that recommends the best model for a given spend. This directly showcases Mistral's model lineup via their API - no GPU needed.

**Time budget**: ~7hrs Day 1 (Sat), ~6hrs Day 2 (Sun, judging at 4pm) = ~13hrs total.
**API key**: Available now - can pre-test streaming pipeline before the event.

---

## Architecture

```
Browser (React islands)        Astro Server Endpoints              Mistral API
  |                                  |                               |
  |--- POST /api/arena ------------->|                               |
  |    { prompt, models[] }          |--- stream model-1 ----------->|
  |                                  |--- stream model-2 ----------->|
  |                                  |--- stream model-3 ----------->|
  |                                  |--- stream model-4 ----------->|
  |<-- SSE: {model, type, data}      |<-- chunks interleaved --------|
```

- **Multiplexed SSE**: Single SSE connection carries tokens from all models, tagged by `model` field. Client demuxes to correct panel.
- **Why SSE over WebSockets**: Simpler, native Astro server endpoint support, one-directional flow (server→client), no extra deps.
- **Why server proxy**: Keeps Mistral API key server-side.

---

## Tech Stack

| Choice | Why |
|--------|-----|
| Astro 5 | Lightweight, server endpoints for SSE proxy, fast static shell |
| React 19 (via `@astrojs/react`) | Interactive islands for arena + charts |
| Tailwind CSS v4 | Fastest styling iteration, dark theme trivial |
| `@mistralai/mistralai` SDK | Official TS SDK with streaming support |
| React useState + hooks | No global state library needed |
| No database | All state in-memory, session-only |

---

## Models to Race

| Model ID | Display Name | Input/Output Price (per 1M tokens) | Color |
|----------|-------------|-------------------------------------|-------|
| `mistral-large-latest` | Mistral Large | $0.50 / $1.50 | Amber |
| `mistral-small-latest` | Mistral Small | $0.06 / $0.18 | Emerald |
| `ministral-8b-latest` | Ministral 8B | $0.01 / $0.01 | Violet |
| `codestral-latest` | Codestral | $0.08 / $0.24 | Cyan |
| `magistral-small-latest` | Magistral Small | $0.10 / $0.30 | Pink |

Users select 2-4 models per race from this roster.

---

## File Structure

```
/
  astro.config.mjs
  package.json
  tailwind.config.ts
  tsconfig.json
  .env                              # MISTRAL_API_KEY

  src/
    layouts/
      Layout.astro                  # Base HTML shell, fonts, dark theme

    pages/
      index.astro                   # Landing page, mounts React arena island
      api/
        arena.ts                    # POST -> multiplexed SSE stream (CORE)
        judge.ts                    # POST -> LLM-as-judge evaluation

    components/
      arena/
        ArenaView.tsx               # Main React island (client:load)
        ModelPanel.tsx              # Single model streaming panel + metrics
        StreamingText.tsx           # Animated text with cursor
        MetricsBar.tsx              # TTFT, tok/s, cost counters
      budget/
        BudgetOptimizer.tsx         # Budget slider + model comparison table
      prompt/
        PromptInput.tsx             # Textarea + model selector + "Race!" button
        PromptLibrary.tsx           # Pre-built prompt gallery
      judge/
        JudgePanel.tsx              # Quality ratings / user voting
      ui/
        Header.tsx                  # App header
        ModelBadge.tsx              # Colored model indicator

    lib/
      mistral.ts                    # Mistral client singleton
      models.ts                     # Model metadata, pricing, colors
      prompts.ts                    # Prompt library data
      arena-stream.ts               # Server-side stream multiplexer logic
      metrics.ts                    # TTFT, tok/s, cost calculation
      budget.ts                     # Budget optimizer math

    hooks/
      useArenaStream.ts             # Client SSE consumer + per-model state

    types/
      arena.ts                      # Shared TypeScript types
```

~25 files total. Deliberately flat.

---

## Day-by-Day Schedule

### DAY 1 (Saturday) - ~7 hours

**Hour 0-1: Bootstrap**
- `npm create astro@latest` with React integration and Tailwind
- Install: `@mistralai/mistralai`, `@phosphor-icons/react`
- Set up `.env` with `MISTRAL_API_KEY`
- Create folder structure, verify API connectivity
- **Checkpoint**: Project runs, can call Mistral API

**Hour 1-3: Core Streaming Pipeline**
- `lib/mistral.ts` - client singleton
- `lib/models.ts` - model metadata/pricing
- `types/arena.ts` - shared types
- `pages/api/arena.ts` - multiplexed SSE endpoint (fire N parallel Mistral streams, interleave tokens into single SSE response)
- `hooks/useArenaStream.ts` - client SSE consumer, demux by model ID
- **Checkpoint**: Can stream N models through single endpoint

**Hour 3-5: Arena UI**
- `ArenaView.tsx` - orchestrator with grid layout
- `ModelPanel.tsx` - streaming panel with text + metrics
- `StreamingText.tsx` - text renderer with blinking cursor
- `MetricsBar.tsx` - TTFT, tok/s, cost display
- `PromptInput.tsx` - textarea + model selector + "Race!" button
- Wire onto `index.astro`
- **Checkpoint**: Working arena - type prompt, click Race, see panels stream

**Hour 5-6: Metrics Polish**
- `lib/metrics.ts` - accurate TTFT, rolling tok/s, cost estimation
- Smooth animated counters for metrics
- Skeleton loaders for waiting state
- **Checkpoint**: Metrics are accurate and visually smooth

**Hour 6-7: Prompt Library**
- `lib/prompts.ts` - curated prompts by category (Creative, Code, Reasoning, Translation, Analysis)
- `PromptLibrary.tsx` - clickable prompt cards
- Include Tokyo-specific prompts for demo flavor
- **Checkpoint**: END OF DAY 1 - Fully functional arena, demo-able

### DAY 2 (Sunday) - ~6 hours (judging at 4pm)

**Hour 0-1.5: Budget Optimizer**
- `lib/budget.ts` - calculation: monthly budget + usage estimate -> model recommendations
- `BudgetOptimizer.tsx` - budget slider, comparison table, highlighted recommendation
- Tab/section toggle between Arena and Budget modes
- **Checkpoint**: Budget mode works end-to-end

**Hour 1.5-3: Quality Judge**
- `pages/api/judge.ts` - use `mistral-large-latest` to rate other models' responses (JSON scores)
- `JudgePanel.tsx` - show ratings breakdown + user thumbs up/down voting
- Summary card: "Model X won this round"
- **Checkpoint**: Quality comparison feature works

**Hour 3-4.5: Visual Polish**
- `Header.tsx` with branding
- Dark theme refinement (zinc-950 background)
- Animations: panel fade-in stagger, first-to-finish trophy indicator
- Error states: API errors, rate limits, model unavailable
- Mobile responsiveness pass
- **Checkpoint**: UI is polished and demo-worthy

**Hour 4.5-5.5: Demo Prep**
- Simple race history (last N results in state)
- Prepare 3-4 killer demo prompts per category
- End-to-end test the full demo flow
- Deploy (Vercel/Netlify/Cloudflare) as backup

**Hour 5.5-6: Buffer**
- Bug fixes only
- Record backup demo video in case of connectivity issues

---

## Key Implementation Notes

**SSE Protocol** - Each event is JSON with shape:
```typescript
| { model: string; type: "token"; data: string; timestamp: number }
| { model: string; type: "first_token"; timestamp: number }
| { model: string; type: "done"; usage: {...}; timestamp: number }
| { model: string; type: "error"; message: string; timestamp: number }
```

**Parallel streams** - Use `Promise.all()` with `for await` loops per model inside a `ReadableStream`. Streams naturally interleave.

**Budget optimizer** - Pure math, no API calls: `costPerRequest = (avgPromptTokens * inputPrice + avgCompletionTokens * outputPrice) / 1_000_000`. Recommend highest quality model where `monthlyCost <= budget`.

**LLM-as-judge** - Single non-streaming call to `mistral-large-latest` with structured prompt asking for JSON ratings on accuracy, completeness, clarity, conciseness.

---

## Risks & Fallbacks

| Risk | Fallback |
|------|----------|
| Rate limits with 4 concurrent streams | Default to 2-3 models, add 50ms stagger between launches |
| Token usage not in streaming chunks | Count tokens client-side (approximate), show "~" prefix |
| SDK issues | Fall back to raw `fetch()` with manual SSE parsing |
| Demo connectivity at venue | Deploy beforehand (Vercel/Netlify/Cloudflare), record backup video |
| Specific model unavailable | Show "Model unavailable" in that panel, others continue |

---

## Verification

1. **Streaming works**: Fire a race with 3+ models, confirm all panels stream independently
2. **Metrics accurate**: Compare TTFT/tok-s with manual stopwatch, verify cost against Mistral pricing page
3. **Budget optimizer**: Input $10/month budget, verify recommendation makes mathematical sense
4. **Judge**: Run a race, click "Judge", confirm ratings appear with reasoning
5. **Error handling**: Test with invalid model ID, confirm graceful error in that panel only
6. **Mobile**: Resize browser, confirm panels stack to single column
7. **Deploy**: Deploy succeeds and works from a different device
