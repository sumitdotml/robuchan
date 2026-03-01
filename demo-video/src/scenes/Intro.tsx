import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Background, COLORS } from "../components/Background";

// ---------------------------------------------------------------------------
// Word-by-word fade helper
// ---------------------------------------------------------------------------
const WORD_STAGGER_FRAMES = 3;
const WORD_FADE_FRAMES = 10;

const FadingWords: React.FC<{ words: string[]; startFrame: number }> = ({
  words,
  startFrame,
}) => {
  const frame = useCurrentFrame();

  return (
    <span>
      {words.map((word, i) => {
        const wordStart = startFrame + i * WORD_STAGGER_FRAMES;
        const opacity = interpolate(
          frame,
          [wordStart, wordStart + WORD_FADE_FRAMES],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        return (
          <span key={i} style={{ opacity, marginRight: "0.3em" }}>
            {word}
          </span>
        );
      })}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Emoji row item
// ---------------------------------------------------------------------------
const EMOJIS = ["🍜", "🥗", "🍱", "🍛"];

const EmojiItem: React.FC<{ emoji: string; delay: number }> = ({
  emoji,
  delay,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - delay,
    fps,
    config: { damping: 12, stiffness: 180, mass: 0.8 },
  });

  return (
    <span
      style={{
        fontSize: 56,
        display: "inline-block",
        transform: `scale(${scale})`,
        margin: "0 12px",
      }}
    >
      {emoji}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Main Intro scene (12s)
// ---------------------------------------------------------------------------
export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Logo image springs in
  const logoScale = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 160, mass: 1 },
    from: 0.88,
    to: 1,
  });
  const logoOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtitle fades in at 1.2s
  const subtitleOpacity = interpolate(
    frame,
    [fps * 1.2, fps * 1.8],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Tagline line 1: starts at 2.5s
  const tagline1StartFrame = Math.round(fps * 2.5);
  const tagline1Words =
    "We help hungry foodies decide their next meal,".split(" ");

  // Tagline line 2: starts at 4.5s
  const tagline2StartFrame = Math.round(fps * 4.5);
  const tagline2Words =
    "without worrying about allergies or dietary restrictions.".split(" ");

  // Emoji row: starts at 8s (scene is 12s)
  const emojiRowOpacity = interpolate(
    frame,
    [fps * 8, fps * 8.4],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <Background>
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 0,
        }}
      >
        {/* Wide logo image */}
        <div
          style={{
            transform: `scale(${logoScale})`,
            opacity: logoOpacity,
            textAlign: "center",
          }}
        >
          <Img
            src={staticFile("robuchan-wide.png")}
            style={{
              width: 1080,
              objectFit: "contain",
            }}
          />
        </div>

        {/* Subtitle */}
        <p
          style={{
            fontSize: 24,
            color: COLORS.textSub,
            marginTop: 20,
            opacity: subtitleOpacity,
            textAlign: "center",
          }}
        >
          No connection with Joel Robuchon
        </p>

        {/* Tagline line 1 */}
        <p
          style={{
            fontSize: 34,
            color: COLORS.text,
            marginTop: 40,
            textAlign: "center",
            maxWidth: 900,
            lineHeight: 1.5,
          }}
        >
          <FadingWords
            words={tagline1Words}
            startFrame={tagline1StartFrame}
          />
        </p>

        {/* Tagline line 2 */}
        <p
          style={{
            fontSize: 34,
            color: COLORS.text,
            marginTop: 8,
            textAlign: "center",
            maxWidth: 900,
            lineHeight: 1.5,
          }}
        >
          <FadingWords
            words={tagline2Words}
            startFrame={tagline2StartFrame}
          />
        </p>

        {/* Emoji row at 8s */}
        <div
          style={{
            marginTop: 48,
            opacity: emojiRowOpacity,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Sequence from={fps * 8} layout="none">
            {EMOJIS.map((emoji, i) => (
              <EmojiItem key={emoji} emoji={emoji} delay={i * 5} />
            ))}
          </Sequence>
        </div>
      </AbsoluteFill>
    </Background>
  );
};
