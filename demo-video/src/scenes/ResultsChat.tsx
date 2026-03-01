import React from "react";
import { AbsoluteFill, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Video } from "@remotion/media";
import { Background, COLORS } from "../components/Background";
import { SceneLabel } from "../components/SceneLabel";

export const ResultsChat: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, fps * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const videoOpacity = interpolate(frame, [fps * 1, fps * 1.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Background>
      <SceneLabel label="In Action" />

      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: 60,
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

      {/* Live demo video */}
      <AbsoluteFill
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          paddingTop: 140,
          paddingBottom: 40,
          paddingLeft: 80,
          paddingRight: 80,
        }}
      >
        <div
          style={{
            opacity: videoOpacity,
            width: "100%",
            height: "100%",
            borderRadius: 24,
            overflow: "hidden",
            border: `1px solid ${COLORS.cardBorder}`,
          }}
        >
          <Video
            src={staticFile("live-demo-clip.mp4")}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
            }}
          />
        </div>
      </AbsoluteFill>
    </Background>
  );
};
