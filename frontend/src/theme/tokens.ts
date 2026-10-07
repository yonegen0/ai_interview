/** @file tokens.ts @description 共通themeから派生する寸法とHero・スコアの専用文字スタイル。 */
import type { Theme } from "@mui/material/styles";

export const scaledRadius = (theme: Theme, ratio: number) =>
  typeof theme.shape.borderRadius === "number"
    ? theme.shape.borderRadius * ratio
    : `calc(${theme.shape.borderRadius} * ${ratio})`;

export const heroTypography = (theme: Theme) => ({
  ...theme.typography.h1,
  fontSize: 32,
  lineHeight: 1.3,
  letterSpacing: "-0.03em",
  [theme.breakpoints.up("md")]: { fontSize: 44 },
  [theme.breakpoints.down("md")]: { fontSize: 32 },
});

export const scoreTypography = (theme: Theme) => ({
  ...theme.typography.h1,
  fontSize: 48,
  lineHeight: 1,
  letterSpacing: "-0.04em",
  [theme.breakpoints.up("md")]: { fontSize: 64 },
  [theme.breakpoints.down("md")]: { fontSize: 48 },
});

/** Convert derived radii to CSS lengths for multi-corner shorthand. */
export const radiusLength = (theme: Theme, ratio: number) => {
  const value = scaledRadius(theme, ratio);
  return typeof value === "number" ? `${value}px` : value;
};
