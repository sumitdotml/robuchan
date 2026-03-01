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

// ─── constants ────────────────────────────────────────────────────────────────
const HEADLINE_FADE_START = 0;
const HEADLINE_FADE_END = 20;

const MISTRAL_SPRING_START_S = 1;
const STAT_BOX_STARTS_S = [2.5, 3.0, 3.5];
const BADGE_SPRING_START_S = 7;
const SUBTITLE_FADE_START_S = 9;
const SUBTITLE_FADE_DURATION_FRAMES = 20;

const SPRING_CONFIG = { damping: 14, stiffness: 120, mass: 1 };

// ─── StatBox ──────────────────────────────────────────────────────────────────
interface StatBoxProps {
  value: string;
  valueColor: string;
  label: string;
  startFrame: number;
}

const StatBox: React.FC<StatBoxProps> = ({
  value,
  valueColor,
  label,
  startFrame,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - startFrame,
    fps,
    config: SPRING_CONFIG,
    durationInFrames: 40,
  });

  const scale = interpolate(progress, [0, 1], [0.8, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(progress, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        backgroundColor: COLORS.card,
        border: `1px solid ${COLORS.cardBorder}`,
        borderRadius: 16,
        padding: "40px 60px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        opacity,
        transform: `scale(${scale})`,

      }}
    >
      <span
        style={{
          color: valueColor,
          fontSize: 56,
          fontWeight: 800,
          lineHeight: 1,
          letterSpacing: -1,
        }}
      >
        {value}
      </span>
      <span
        style={{
          color: COLORS.textSub,
          fontSize: 18,
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: 1,
        }}
      >
        {label}
      </span>
    </div>
  );
};

// ─── Training ─────────────────────────────────────────────────────────────────
export const Training: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // "We finetuned" — fade in over 20 frames at 0s
  const headlineOpacity = interpolate(
    frame,
    [HEADLINE_FADE_START, HEADLINE_FADE_END],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // "Mistral Small" — spring in at 1s
  const mistralProgress = spring({
    frame: frame - MISTRAL_SPRING_START_S * fps,
    fps,
    config: SPRING_CONFIG,
    durationInFrames: 40,
  });
  const mistralScale = interpolate(mistralProgress, [0, 1], [0.7, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const mistralOpacity = interpolate(mistralProgress, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Stat box start frames
  const statStartFrames = STAT_BOX_STARTS_S.map((s) => Math.round(s * fps));

  // Badge spring at 7s
  const badgeProgress = spring({
    frame: frame - BADGE_SPRING_START_S * fps,
    fps,
    config: { damping: 12, stiffness: 140, mass: 1 },
    durationInFrames: 40,
  });
  const badgeScale = interpolate(badgeProgress, [0, 1], [0.7, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const badgeOpacity = interpolate(badgeProgress, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtitle fade at 9s
  const subtitleStart = Math.round(SUBTITLE_FADE_START_S * fps);
  const subtitleOpacity = interpolate(
    frame,
    [subtitleStart, subtitleStart + SUBTITLE_FADE_DURATION_FRAMES],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <Background>
      <SceneLabel label="Training" />

      {/* Main centered content */}
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 32,
          paddingTop: 40,
  
        }}
      >
        {/* "We finetuned" headline */}
        <div
          style={{
            opacity: headlineOpacity,
            color: COLORS.text,
            fontSize: 36,
            fontWeight: 500,
            letterSpacing: 0.5,
          }}
        >
          We finetuned
        </div>

        {/* "Mistral Small" — large gold bold */}
        <div
          style={{
            opacity: mistralOpacity,
            transform: `scale(${mistralScale})`,
            color: COLORS.gold,
            fontSize: 72,
            fontWeight: 800,
            letterSpacing: -2,
            lineHeight: 1,
          }}
        >
          Mistral Small
        </div>

        {/* Stat row — 3 boxes */}
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            gap: 32,
            alignItems: "center",
            marginTop: 16,
          }}
        >
          <StatBox
            value="530K"
            valueColor={COLORS.accent}
            label="training rows"
            startFrame={statStartFrames[0]}
          />
          <StatBox
            value="87.3%"
            valueColor={COLORS.green}
            label="our accuracy"
            startFrame={statStartFrames[1]}
          />
          <StatBox
            value="72.1%"
            valueColor={COLORS.textSub}
            label="baseline accuracy"
            startFrame={statStartFrames[2]}
          />
        </div>

        {/* +15.2pp badge */}
        <div
          style={{
            opacity: badgeOpacity,
            transform: `scale(${badgeScale})`,
            backgroundColor: "rgba(63, 185, 80, 0.15)",
            border: `1.5px solid ${COLORS.green}`,
            borderRadius: 100,
            padding: "12px 28px",
            color: COLORS.green,
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: 0.5,
          }}
        >
          ▲ +15.2pp improvement
        </div>

      </AbsoluteFill>
    </Background>
  );
};
