import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background, COLORS } from "../components/Background";
import { SceneLabel } from "../components/SceneLabel";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------
const CARD_W = 520;
const CARD_H = 300;
const GAP = 40;
const CARD_TOP = 380;
const SHIFT = (CARD_W + GAP) / 2; // 280px — per-phase horizontal shift

// Left-edge x positions per phase
// 1-card:  x0 = (1920 - 520) / 2 = 700
// 2-cards: x1 = (1920 - 1080) / 2 + 560 = 980
// 3-cards: x2 = (1920 - 1640) / 2 + 1120 = 1260
const X0_ONE = (1920 - CARD_W) / 2;
const X1_TWO = (1920 - (CARD_W * 2 + GAP)) / 2 + CARD_W + GAP;
const X2_THREE = (1920 - (CARD_W * 3 + GAP * 2)) / 2 + (CARD_W + GAP) * 2;

// ---------------------------------------------------------------------------
// Emoji avatar — emoji on cultural-colour circular background
// ---------------------------------------------------------------------------
const EmojiAvatar: React.FC<{ emoji: string }> = ({ emoji }) => (
  <span style={{ fontSize: 72, flexShrink: 0, lineHeight: 1 }}>{emoji}</span>
);

// ---------------------------------------------------------------------------
// Persona data (no constraint field — subtitle removed per design)
// ---------------------------------------------------------------------------
interface Persona {
  avatar: {
    emoji: string;
  };
  name: string;
  want: string;
  badge: string;
}

const PERSONAS: Persona[] = [
  {
    avatar: { emoji: "👨‍🍳" },
    name: "Mario",
    want: "🍝 Wants: Pasta",
    badge: "GLUTEN-FREE",
  },
  {
    avatar: { emoji: "👨‍🍳" },
    name: "Maruti",
    want: "🥘 Wants: Mapo Tofu",
    badge: "VEGETARIAN",
  },
  {
    avatar: { emoji: "👩‍🍳" },
    name: "Mariko",
    want: "🍱 Wants: Onigiri",
    badge: "MISSING INGREDIENTS",
  },
];

// ---------------------------------------------------------------------------
// Static card (all animation driven by parent wrapper)
// ---------------------------------------------------------------------------
const PersonaCard: React.FC<{ persona: Persona }> = ({ persona }) => (
  <div
    style={{
      width: CARD_W,
      height: CARD_H,
      backgroundColor: COLORS.card,
      border: `1px solid ${COLORS.cardBorder}`,
      borderRadius: 20,
      padding: 36,
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      gap: 18,
      boxSizing: "border-box",
    }}
  >
    {/* Avatar + name */}
    <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
      <EmojiAvatar emoji={persona.avatar.emoji} />
      <span style={{ fontSize: 38, fontWeight: 700, color: COLORS.text }}>
        {persona.name}
      </span>
    </div>

    {/* What they want */}
    <p style={{ fontSize: 24, color: COLORS.gold, fontWeight: 600, margin: 0 }}>
      {persona.want}
    </p>

    {/* Dietary badge */}
    <div
      style={{
        alignSelf: "flex-start",
        backgroundColor: COLORS.accent,
        borderRadius: 999,
        padding: "6px 18px",
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 700, color: "#fff", letterSpacing: 2 }}>
        {persona.badge}
      </span>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Main Problem scene (18s)
// Card 0 alone → Card 1 joins at 6s → Card 2 joins at 12s → closing at 14s
// ---------------------------------------------------------------------------
export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Smooth layout-shift springs (damping:200 = no bounce)
  const shift1 = spring({ frame: frame - 6 * fps, fps, config: { damping: 200 } });
  const shift2 = spring({ frame: frame - 12 * fps, fps, config: { damping: 200 } });

  // ── Card 0 ─────────────────────────────────────────────────────────────────
  const card0Entrance = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 160 },
    from: 0.88,
    to: 1,
  });
  const card0Opacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const card0Left = X0_ONE - shift1 * SHIFT - shift2 * SHIFT;

  // ── Card 1 ─────────────────────────────────────────────────────────────────
  const card1Slide = spring({
    frame: frame - 6 * fps,
    fps,
    config: { damping: 14, stiffness: 160 },
  });
  const card1BaseLeft = interpolate(card1Slide, [0, 1], [1920, X1_TWO], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const card1Left = card1BaseLeft - shift2 * SHIFT;
  const card1Opacity = interpolate(frame, [6 * fps, 6 * fps + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Card 2 ─────────────────────────────────────────────────────────────────
  const card2Slide = spring({
    frame: frame - 12 * fps,
    fps,
    config: { damping: 14, stiffness: 160 },
  });
  const card2Left = interpolate(card2Slide, [0, 1], [1920, X2_THREE], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const card2Opacity = interpolate(frame, [12 * fps, 12 * fps + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Closing line at 14s (visible for 4s until scene end at 18s) ────────────
  const closingOpacity = interpolate(
    frame,
    [14 * fps, 14 * fps + Math.round(fps * 0.6)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <Background>
      <SceneLabel label="The Problem" />

      <AbsoluteFill>
        {/* Card 0 — Mario */}
        <div
          style={{
            position: "absolute",
            top: CARD_TOP,
            left: card0Left,
            opacity: card0Opacity,
            transform: `scale(${card0Entrance})`,
          }}
        >
          <PersonaCard persona={PERSONAS[0]} />
        </div>

        {/* Card 1 — Maruti */}
        <div
          style={{
            position: "absolute",
            top: CARD_TOP,
            left: card1Left,
            opacity: card1Opacity,
          }}
        >
          <PersonaCard persona={PERSONAS[1]} />
        </div>

        {/* Card 2 — Mariko */}
        <div
          style={{
            position: "absolute",
            top: CARD_TOP,
            left: card2Left,
            opacity: card2Opacity,
          }}
        >
          <PersonaCard persona={PERSONAS[2]} />
        </div>

        {/* Closing line — 4s visibility (14s–18s) */}
        <div
          style={{
            position: "absolute",
            top: CARD_TOP + CARD_H + 72,
            width: "100%",
            textAlign: "center",
            opacity: closingOpacity,
          }}
        >
          <span style={{ fontSize: 48, fontWeight: 700, color: COLORS.text }}>
            {"That's where "}
            <span style={{ color: COLORS.accent }}>we</span>
            {" come in."}
          </span>
        </div>
      </AbsoluteFill>
    </Background>
  );
};
