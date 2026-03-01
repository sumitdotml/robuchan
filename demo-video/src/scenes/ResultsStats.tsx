import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background, COLORS } from "../components/Background";
import { SceneLabel } from "../components/SceneLabel";

// ─── constants ────────────────────────────────────────────────────────────────
const TITLE_FADE_START = 0;
const TITLE_FADE_END = 20;

const BARS_START_S = 1.0;
const BARS_ANIM_FRAMES = 48;

const MAX_BAR_HEIGHT_PX = 538;
const BAR_WIDTH_PX = 134;

const WANDB_FADE_START_S = BARS_START_S;
const WANDB_FADE_DURATION_FRAMES = 20;

const SPRING_CONFIG = { damping: 14, stiffness: 120, mass: 1 };

// ─── animated bar data types ──────────────────────────────────────────────────
interface BarDef {
  modelName: string;
  color: string;
  targetFraction: number; // fraction of MAX_BAR_HEIGHT_PX
  displayLabel: string;
}

interface BarGroupProps {
  groupLabel: string;
  bars: BarDef[];
  startFrame: number;
}

// ─── AnimatedBar ──────────────────────────────────────────────────────────────
const AnimatedBar: React.FC<{
  bar: BarDef;
  startFrame: number;
}> = ({ bar, startFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const targetHeightPx = bar.targetFraction * MAX_BAR_HEIGHT_PX;

  const barsStartFrame = Math.round(BARS_START_S * fps);
  const animStart = barsStartFrame + startFrame; // startFrame is an offset per-bar (0)

  const heightPx = interpolate(
    frame,
    [animStart, animStart + BARS_ANIM_FRAMES],
    [0, targetHeightPx],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Value label floats above bar tip; appears when bar reaches 80% of target
  const labelThresholdFrame = animStart + Math.round(BARS_ANIM_FRAMES * 0.8);
  const labelOpacity = interpolate(
    frame,
    [labelThresholdFrame, labelThresholdFrame + 12],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,

      }}
    >
      {/* Container that reserves max height so bar grows from bottom */}
      <div
        style={{
          position: "relative",
          width: BAR_WIDTH_PX,
          height: MAX_BAR_HEIGHT_PX,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
        }}
      >
        {/* Value label above bar tip */}
        <div
          style={{
            position: "absolute",
            bottom: heightPx + 8,
            left: 0,
            right: 0,
            textAlign: "center",
            opacity: labelOpacity,
            color: bar.color,
            fontSize: 36,
            fontWeight: 700,
          }}
        >
          {bar.displayLabel}
        </div>

        {/* The bar itself */}
        <div
          style={{
            width: BAR_WIDTH_PX,
            height: heightPx,
            backgroundColor: bar.color,
            borderRadius: "6px 6px 0 0",
          }}
        />
      </div>

      {/* Model name below bar */}
      <span
        style={{
          color: COLORS.textSub,
          fontSize: 15,
          fontWeight: 500,
          textAlign: "center",
        }}
      >
        {bar.modelName}
      </span>
    </div>
  );
};

// ─── BarGroup ─────────────────────────────────────────────────────────────────
const BarGroup: React.FC<BarGroupProps> = ({ groupLabel, bars, startFrame }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const barsStartFrame = Math.round(BARS_START_S * fps);
  const groupOpacity = interpolate(
    frame,
    [barsStartFrame, barsStartFrame + 12],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        opacity: groupOpacity,
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.cardBorder}`,
        borderRadius: 16,
        padding: "32px 48px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 24,

      }}
    >
      {/* Group label */}
      <span
        style={{
          color: COLORS.text,
          fontSize: 20,
          fontWeight: 600,
          letterSpacing: 0.5,
        }}
      >
        {groupLabel}
      </span>

      {/* Bars side by side */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "flex-end",
          gap: 32,
        }}
      >
        {bars.map((bar) => (
          <AnimatedBar key={bar.modelName} bar={bar} startFrame={startFrame} />
        ))}
      </div>
    </div>
  );
};

// ─── ResultsStats ─────────────────────────────────────────────────────────────
export const ResultsStats: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title fade at 0s
  const titleOpacity = interpolate(
    frame,
    [TITLE_FADE_START, TITLE_FADE_END],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // W&B caption fade with bars
  const wandbStart = Math.round(WANDB_FADE_START_S * fps);
  const wandbOpacity = interpolate(
    frame,
    [wandbStart, wandbStart + WANDB_FADE_DURATION_FRAMES],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Accuracy bars
  const accuracyBars: BarDef[] = [
    {
      modelName: "Baseline",
      color: COLORS.textSub,
      targetFraction: 0.721,
      displayLabel: "72.1%",
    },
    {
      modelName: "Robuchan",
      color: COLORS.green,
      targetFraction: 0.873,
      displayLabel: "87.3%",
    },
  ];

  // Train Loss bars (inverted: lower loss = shorter bar; 1.82 → 62%, 1.12 → 38%)
  const lossBars: BarDef[] = [
    {
      modelName: "Baseline",
      color: COLORS.textSub,
      targetFraction: 0.62,
      displayLabel: "1.82",
    },
    {
      modelName: "Robuchan",
      color: COLORS.accent,
      targetFraction: 0.38,
      displayLabel: "1.12",
    },
  ];

  return (
    <Background>
      <SceneLabel label="Results" />

      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 40,
          paddingTop: 60,
  
        }}
      >
        {/* Title */}
        <div
          style={{
            opacity: titleOpacity,
            color: COLORS.text,
            fontSize: 42,
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          Baseline vs. Fine-tuned
        </div>

        {/* Two bar groups side by side */}
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            gap: 48,
            alignItems: "flex-start",
          }}
        >
          <BarGroup
            groupLabel="Accuracy"
            bars={accuracyBars}
            startFrame={0}
          />
          <BarGroup
            groupLabel="Train Loss (lower is better)"
            bars={lossBars}
            startFrame={0}
          />
        </div>

        {/* W&B caption */}
        <div
          style={{
            opacity: wandbOpacity,
            color: COLORS.text,
            fontSize: 22,
            fontWeight: 400,
          }}
        >
          Tracked with Weights &amp; Biases
        </div>
      </AbsoluteFill>
    </Background>
  );
};
