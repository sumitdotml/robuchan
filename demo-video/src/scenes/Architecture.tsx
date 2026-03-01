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
// Stage data
// ---------------------------------------------------------------------------
const STAGES: {
  title: string;
  subtitle: string;
  icon: string;
  bg: string;
}[] = [
  {
    title: "Data Sources",
    subtitle: "530K recipes + ingredient rules",
    icon: "🗄️",
    bg: "#1A2D4A",
  },
  {
    title: "Data Pipeline",
    subtitle: "Ingest → Generate fine-tuning data with Mistral Large → Quality Check",
    icon: "⚙️",
    bg: "#1A2000",
  },
  {
    title: "Fine-tune",
    subtitle: "Mistral 8B Instruct",
    icon: "🧠",
    bg: "#2D1A00",
  },
  {
    title: "Evaluate",
    subtitle: "Baseline vs Robuchan",
    icon: "📊",
    bg: "#1A001A",
  },
  {
    title: "Demo",
    subtitle: "Interactive UI",
    icon: "🚀",
    bg: "#001A1A",
  },
];

// Delay in seconds per stage (original [1,3,5,7,9] * 0.85)
const STAGE_DELAYS_MULTIPLIERS = [0.85, 2.55, 4.25, 5.95, 7.65];

// ---------------------------------------------------------------------------
// Single stage box
// ---------------------------------------------------------------------------
const StageBox: React.FC<{
  stage: (typeof STAGES)[number];
  delayFrames: number;
}> = ({ stage, delayFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - delayFrames,
    fps,
    config: { damping: 14, stiffness: 160, mass: 0.9 },
    from: 0.7,
    to: 1,
  });

  const opacity = interpolate(
    frame,
    [delayFrames, delayFrames + 10],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        width: 312,
        height: 264,
        backgroundColor: stage.bg,
        borderRadius: 16,
        border: `1px solid ${COLORS.cardBorder}`,
        padding: 29,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        transform: `scale(${scale})`,
        opacity,
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 48 }}>{stage.icon}</span>
      <span
        style={{
          color: COLORS.text,
          fontSize: 33,
          fontWeight: 700,
          textAlign: "center",

        }}
      >
        {stage.title}
      </span>
      <span
        style={{
          color: COLORS.text,
          fontSize: 24,
          textAlign: "center",
          lineHeight: 1.4,
        }}
      >
        {stage.subtitle}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Arrow between stages — fades in when stage i+1 is >50% animated
// ---------------------------------------------------------------------------
const Arrow: React.FC<{ nextStageDelayFrames: number }> = ({
  nextStageDelayFrames,
}) => {
  const frame = useCurrentFrame();

  // Stage is >50% animated when the spring has run for ~half its settle time.
  // We approximate: the arrow appears ~8 frames after the next stage starts.
  const arrowStart = nextStageDelayFrames + 8;

  const opacity = interpolate(
    frame,
    [arrowStart, arrowStart + 8],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <span
      style={{
        color: COLORS.textSub,
        fontSize: 36,
        opacity,
        flexShrink: 0,
        fontFamily: "Inter, system-ui, sans-serif",
        userSelect: "none",
      }}
    >
      →
    </span>
  );
};

// ---------------------------------------------------------------------------
// Main scene
// ---------------------------------------------------------------------------
export const Architecture: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, fps * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Background>
      <SceneLabel label="Architecture" />

      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: 120,
          width: "100%",
          textAlign: "center",
          opacity: titleOpacity,

        }}
      >
        <span
          style={{
            fontSize: 52,
            fontWeight: 700,
            color: COLORS.text,
          }}
        >
          How Robuchan Works
        </span>
      </div>

      {/* Pipeline row */}
      <AbsoluteFill
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            gap: 16,
          }}
        >
          {STAGES.map((stage, i) => {
            const delayFrames = STAGE_DELAYS_MULTIPLIERS[i] * fps;
            return (
              <React.Fragment key={stage.title}>
                <StageBox stage={stage} delayFrames={delayFrames} />
                {i < STAGES.length - 1 && (
                  <Arrow
                    nextStageDelayFrames={
                      STAGE_DELAYS_MULTIPLIERS[i + 1] * fps
                    }
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </AbsoluteFill>
    </Background>
  );
};
