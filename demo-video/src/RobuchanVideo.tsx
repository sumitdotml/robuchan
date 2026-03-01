import React from "react";
import { Series, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";
import { Intro } from "./scenes/Intro";
import { Problem } from "./scenes/Problem";
import { Training } from "./scenes/Training";
import { ResultsStats } from "./scenes/ResultsStats";
import { ResultsChat } from "./scenes/ResultsChat";
import { Architecture } from "./scenes/Architecture";
import { Outro } from "./scenes/Outro";

const BG_MUSIC_URL =
  "https://archive.org/download/MozartEineKleineNachtmusik_102/MozartALittleNightMusic.mp3";

// Scene durations in seconds
const INTRO_S = 7;
const PROBLEM_S = 6;
const TRAINING_S = 7;
const RESULTS_STATS_S = 6.5;
const RESULTS_CHAT_S = 16;
const ARCHITECTURE_S = 10;
const OUTRO_S = 6;

export const TOTAL_DURATION_S =
  INTRO_S +
  PROBLEM_S +
  TRAINING_S +
  RESULTS_STATS_S +
  RESULTS_CHAT_S +
  ARCHITECTURE_S +
  OUTRO_S;

export const RobuchanVideo: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();

  return (
    <>
      <Audio src={BG_MUSIC_URL} volume={0.3} trimAfter={durationInFrames} />
      <Series>
        <Series.Sequence durationInFrames={INTRO_S * fps} premountFor={fps}>
          <Intro />
        </Series.Sequence>
        <Series.Sequence durationInFrames={PROBLEM_S * fps} premountFor={fps}>
          <Problem />
        </Series.Sequence>
        <Series.Sequence durationInFrames={TRAINING_S * fps} premountFor={fps}>
          <Training />
        </Series.Sequence>
        <Series.Sequence durationInFrames={RESULTS_STATS_S * fps} premountFor={fps}>
          <ResultsStats />
        </Series.Sequence>
        <Series.Sequence durationInFrames={RESULTS_CHAT_S * fps} premountFor={fps}>
          <ResultsChat />
        </Series.Sequence>
        <Series.Sequence durationInFrames={ARCHITECTURE_S * fps} premountFor={fps}>
          <Architecture />
        </Series.Sequence>
        <Series.Sequence durationInFrames={OUTRO_S * fps} premountFor={fps}>
          <Outro />
        </Series.Sequence>
      </Series>
    </>
  );
};
