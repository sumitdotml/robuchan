import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background, COLORS } from "../components/Background";
import { SceneLabel } from "../components/SceneLabel";

// ---------------------------------------------------------------------------
// Typing indicator — three dots with sequential sin-phase pulse
// ---------------------------------------------------------------------------
const TypingDots: React.FC<{ visible: boolean }> = ({ visible }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const containerOpacity = interpolate(
    frame,
    [0, 6],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const pulsePeriod = fps * 0.5;

  return (
    <div
      style={{
        opacity: visible ? containerOpacity : 0,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "14px 20px",
        backgroundColor: "#1A2D4A",
        borderRadius: "18px 18px 18px 4px",
        width: "fit-content",
      }}
    >
      {[0, 1, 2].map((i) => {
        const dotStart = i * (pulsePeriod / 3);
        // Use modulo over pulsePeriod so the pulse repeats
        const phase = ((frame - dotStart) % pulsePeriod + pulsePeriod) % pulsePeriod;
        const opacity = interpolate(
          phase,
          [0, pulsePeriod * 0.5, pulsePeriod],
          [0.3, 1, 0.3],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        return (
          <div
            key={i}
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              backgroundColor: COLORS.textSub,
              opacity,
            }}
          />
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// User bubble (slides in from right)
// ---------------------------------------------------------------------------
const UserBubble: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const translateX = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 160, mass: 0.9 },
    from: 200,
    to: 0,
  });

  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${translateX}px)`,
        alignSelf: "flex-end",
        maxWidth: 480,
      }}
    >
      <div
        style={{
          textAlign: "right",
          marginBottom: 6,
          fontSize: 14,
          color: COLORS.textSub,

        }}
      >
        Maruti
      </div>
      <div
        style={{
          backgroundColor: COLORS.accent,
          color: COLORS.text,
          borderRadius: "18px 18px 4px 18px",
          padding: "14px 20px",
          fontSize: 18,
          lineHeight: 1.5,

        }}
      >
        I'd like to eat mapo tofu, but I'm a vegetarian 🍖
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Robuchan bubble (slides in from left)
// ---------------------------------------------------------------------------
const RobuchanBubble: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const translateX = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 160, mass: 0.9 },
    from: -200,
    to: 0,
  });

  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${translateX}px)`,
        alignSelf: "flex-start",
        maxWidth: 520,
      }}
    >
      <div
        style={{
          marginBottom: 6,
          fontSize: 14,
          color: COLORS.accent,

        }}
      >
        🤖 Robuchan
      </div>
      <div
        style={{
          backgroundColor: "#1A2D4A",
          color: COLORS.text,
          borderRadius: "18px 18px 18px 4px",
          padding: "14px 20px",
          fontSize: 18,
          lineHeight: 1.5,

        }}
      >
        Fear not dear, I'm here! 🍲 Here's a vegan mapo tofu — swap the pork
        for firm tofu and use vegetable broth instead.
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Checkmark badge
// ---------------------------------------------------------------------------
const CheckBadge: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 200, mass: 0.7 },
    from: 0,
    to: 1,
  });

  return (
    <div
      style={{
        transform: `scale(${scale})`,
        display: "flex",
        alignItems: "center",
        gap: 10,
        backgroundColor: "rgba(63, 185, 80, 0.12)",
        border: `1px solid ${COLORS.green}`,
        borderRadius: 12,
        padding: "10px 20px",
        color: COLORS.green,
        fontSize: 20,
        fontWeight: 600,
        fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      ✓ Allergy-safe recipe delivered
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main scene
// ---------------------------------------------------------------------------
export const ResultsChat: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title fades in at 0 s
  const titleOpacity = interpolate(frame, [0, fps * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Chat container springs in at 2 s
  const containerScale = spring({
    frame: frame - fps * 2,
    fps,
    config: { damping: 14, stiffness: 160, mass: 1 },
    from: 0.85,
    to: 1,
  });
  const containerOpacity = interpolate(
    frame,
    [fps * 2, fps * 2 + 20],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Typing indicator: visible 8 s → 11 s
  const typingVisible = frame >= fps * 8 && frame < fps * 11;

  return (
    <Background>
      <SceneLabel label="In Action" />

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
            color: COLORS.gold,
          }}
        >
          Let's get Maruti his vegan mapo tofu.
        </span>
      </div>

      {/* Chat container */}
      <AbsoluteFill
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          paddingTop: 60,
        }}
      >
        <div
          style={{
            width: 700,
            height: 600,
            backgroundColor: COLORS.card,
            borderRadius: 24,
            border: `1px solid ${COLORS.cardBorder}`,
            transform: `scale(${containerScale})`,
            opacity: containerOpacity,
            display: "flex",
            flexDirection: "column",
            padding: 32,
            gap: 20,
            overflow: "hidden",
            position: "relative",
          }}
        >
          {/* User bubble at 4 s */}
          {frame >= fps * 4 && (
            <Sequence from={fps * 4}>
              <UserBubble />
            </Sequence>
          )}

          {/* Typing indicator at 8 s */}
          {frame >= fps * 8 && (
            <Sequence from={fps * 8}>
              <TypingDots visible={typingVisible} />
            </Sequence>
          )}

          {/* Robuchan bubble at 11 s */}
          {frame >= fps * 11 && (
            <Sequence from={fps * 11}>
              <RobuchanBubble />
            </Sequence>
          )}

          {/* Checkmark badge at 17 s */}
          {frame >= fps * 15 && (
            <Sequence from={fps * 15}>
              <div
                style={{
                  position: "absolute",
                  bottom: 32,
                  left: "50%",
                  transform: "translateX(-50%)",
                }}
              >
                <CheckBadge />
              </div>
            </Sequence>
          )}
        </div>
      </AbsoluteFill>
    </Background>
  );
};
