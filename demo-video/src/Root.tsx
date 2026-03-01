import React from "react";
import { Composition } from "remotion";
import { RobuchanVideo } from "./RobuchanVideo";

const FPS = 30;
const TOTAL_DURATION_S = 91;

export const Root: React.FC = () => {
  return (
    <Composition
      id="RobuchanVideo"
      component={RobuchanVideo}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={TOTAL_DURATION_S * FPS}
    />
  );
};
