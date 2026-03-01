# Skill: Video Generation Log

Session date: 2026-03-01
Skill used: `remotion-best-practices` (source: `remotion-dev/skills`, installed via `skills-lock.json`)

---

## Setup

- Clean-installed skill from `remotion-dev/skills` into `.agents/skills/remotion-best-practices/`
  - Fetched `SKILL.md` + 37 rule files from `rules/` in parallel
  - Previous hand-written SKILL.md replaced with canonical upstream version
- Created `demo-video/` Remotion project (1920x1080, 30fps) from scratch
- Added `Makefile` at root with `make preview` and `make render` targets

---

## Video structure

Total duration: **89s** at 30fps (under the 2-min limit)

| Scene | Duration | Key content |
| --- | --- | --- |
| Intro | 12s | robuchan-wide.png logo, tagline word-reveal, emoji row |
| Problem | 18s | 3 persona cards revealed progressively into a 3-column layout |
| Training | 10s | "We finetuned Mistral Small", 3 stat boxes (530K / 87.3% / 72.1%) |
| ResultsStats | 13s | Animated accuracy + train-loss bar charts |
| ResultsChat | 18s | Chat bubbles: Maruti → Robuchan, typing indicator, checkmark badge |
| Architecture | 10s | 5-stage pipeline boxes with spring entrance + connecting arrows |
| Outro | 8s | robuchan.png logo, "What are you hungry for?", floating emojis |

---

## Design decisions

- **Font**: Outfit (via `@remotion/google-fonts`) — Inter banned by `design-taste-frontend` skill
- **Palette**: Dark bg `#0D1117`, accent orange `#FF6B35`, gold `#FFC947`, green `#3FB950`
- **Animation rules enforced**:
  - All animations driven by `useCurrentFrame()` — no CSS transitions
  - All `interpolate` calls have `extrapolateLeft/Right: "clamp"`
  - `fps` always destructured from `useVideoConfig()` — never hardcoded
  - `spring({ damping: 200 })` for layout shifts (zero bounce), snappy config for card entrances

---

## Problem scene — progressive 3-column reveal

Cards appear one by one and all stay on screen, repositioning as each joins:

- Frame 0: Card 0 (Mario) springs in, centered
- Frame 6xfps: Card 0 shifts left, Card 1 (Maruti) slides in from right
- Frame 12xfps: Both shift left, Card 2 (Mariko) slides in from right — 3-column final state
- Frame 14xfps: "That's where we come in." fades in (4s visibility)

Layout math: `SHIFT = (CARD_W + GAP) / 2 = 280px` — uniform per-phase shift using `spring({ damping: 200 })`.

---

## Persona avatars

Replaced emoji icons with inline SVG avatar components (skin tone + hair on cultural-colour bg):

| Persona | Background | Skin | Role |
| --- | --- | --- | --- |
| Mario | `#CE2B37` (Italian red) | `#E8BF9F` | Italian man, gluten-free |
| Maruti | `#FF9933` (Indian saffron) | `#C4863A` | Indian man, vegetarian |
| Mariko | `#BC002D` (Japanese red) | `#F2D5C0` | Japanese woman, missing ingredients |

---

## Assets

| File | Used in |
|---|---|
| `public/robuchan-wide.png` | Intro — 1080px wide, springs in |
| `public/robuchan.png` | Outro — 270x270px, springs in |

---

## Pending / placeholders

- Accuracy numbers (87.3% / 72.1%) are **placeholder** — update in `Training.tsx` and `ResultsStats.tsx` once W&B results are final
- Music not yet added. To add: drop an MP3 into `public/` then add `<Audio src={staticFile("music.mp3")} volume={0.35} />` to `RobuchanVideo.tsx`. Sources: Suno, Pixabay Music, YouTube Audio Library.

---

## Key files

| Path | Purpose |
|---|---|
| `demo-video/src/Root.tsx` | Composition registry (89s, 1920x1080, 30fps) |
| `demo-video/src/RobuchanVideo.tsx` | Top-level Series of all 7 scenes |
| `demo-video/src/fonts.ts` | Outfit font loader (module-level loadFont) |
| `demo-video/src/components/Background.tsx` | Shared dark bg + COLORS palette |
| `demo-video/src/scenes/` | All 7 scene components |
| `demo-video/public/` | Static assets (logos, future music) |
| `Makefile` | `make preview` / `make render` |
