import React from "react";
import { AbsoluteFill } from "remotion";
import { fontFamily } from "../fonts";

export const COLORS = {
  bg: "#0D1117",
  card: "#161B22",
  cardBorder: "#30363D",
  accent: "#FF6B35",
  gold: "#FFC947",
  text: "#F0F6FC",
  textSub: "#8B949E",
  green: "#3FB950",
  blue: "#58A6FF",
};

export const Background: React.FC<{ children?: React.ReactNode }> = ({
  children,
}) => (
  <AbsoluteFill
    style={{
      backgroundColor: COLORS.bg,
      fontFamily,
    }}
  >
    {children}
  </AbsoluteFill>
);
