import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background, COLORS } from "../components/Background";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Logo springs in at 0s
  const logoScale = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 140, mass: 1 },
    from: 0.8,
    to: 1,
  });
  const logoOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // "What are you hungry for?" springs in at 1.5s
  const questionScale = spring({
    frame: frame - fps * 1.5,
    fps,
    config: { damping: 12, stiffness: 140, mass: 1 },
    from: 0.85,
    to: 1,
  });
  const questionOpacity = interpolate(
    frame,
    [fps * 1.5, fps * 2],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Credit fades in at 3s
  const creditOpacity = interpolate(frame, [fps * 3, fps * 3.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Background>
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 32,

        }}
      >
        {/* Square logo */}
        <div
          style={{
            opacity: logoOpacity,
            transform: `scale(${logoScale})`,
          }}
        >
          <Img
            src={staticFile("robuchan.png")}
            style={{ width: 405, height: 405, objectFit: "contain" }}
          />
        </div>

        {/* Main CTA */}
        <div
          style={{
            opacity: questionOpacity,
            transform: `scale(${questionScale})`,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 64,
              fontWeight: 800,
              color: COLORS.text,
              letterSpacing: -2,
              lineHeight: 1.15,
            }}
          >
            What are you{" "}
            <span style={{ color: COLORS.accent }}>hungry</span> for?
          </div>
          <div style={{ marginTop: 48, display: "flex", gap: 8, justifyContent: "center" }}>
            {(["🍜", "🥗", "🍱", "🍛"] as const).map((emoji, i) => {
              const floatY = -Math.abs(Math.sin(frame * 0.065 + i * 0.9)) * 35;
              return (
                <span
                  key={i}
                  style={{
                    fontSize: 52,
                    display: "inline-block",
                    transform: `translateY(${floatY}px)`,
                  }}
                >
                  {emoji}
                </span>
              );
            })}
          </div>
        </div>

        {/* Credit */}
        <div
          style={{
            opacity: creditOpacity,
            color: COLORS.textSub,
            fontSize: 19,
            letterSpacing: 2,
            textTransform: "uppercase",
          }}
        >
          Mistral AI Hackathon · Tokyo 2026
        </div>
      </AbsoluteFill>
    </Background>
  );
};
