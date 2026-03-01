import React from "react";
import { Series, useVideoConfig } from "remotion";
import { Intro } from "./scenes/Intro";
import { Problem } from "./scenes/Problem";
import { Training } from "./scenes/Training";
import { ResultsStats } from "./scenes/ResultsStats";
import { ResultsChat } from "./scenes/ResultsChat";
import { Architecture } from "./scenes/Architecture";
import { Outro } from "./scenes/Outro";

export const RobuchanVideo: React.FC = () => {
  const { fps } = useVideoConfig();

  return (
    <Series>
      <Series.Sequence durationInFrames={12 * fps} premountFor={fps}>
        <Intro />
      </Series.Sequence>
      <Series.Sequence durationInFrames={18 * fps} premountFor={fps}>
        <Problem />
      </Series.Sequence>
      <Series.Sequence durationInFrames={10 * fps} premountFor={fps}>
        <Training />
      </Series.Sequence>
      <Series.Sequence durationInFrames={13 * fps} premountFor={fps}>
        <ResultsStats />
      </Series.Sequence>
      <Series.Sequence durationInFrames={18 * fps} premountFor={fps}>
        <ResultsChat />
      </Series.Sequence>
      <Series.Sequence durationInFrames={12 * fps} premountFor={fps}>
        <Architecture />
      </Series.Sequence>
      <Series.Sequence durationInFrames={8 * fps} premountFor={fps}>
        <Outro />
      </Series.Sequence>
    </Series>
  );
};
