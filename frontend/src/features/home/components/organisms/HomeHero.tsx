/** @file HomeHero.tsx @description ホームの歓迎メッセージと練習開始CTA。 */
"use client";

import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { heroTypography, scaledRadius } from "@/theme/tokens";

const HeroPanel = styled(Panel)(({ theme }) => ({
  minWidth: 0,
  margin: 0,
  padding: theme.spacing(3, 2.5, 3.5),
  borderRadius: scaledRadius(theme, 1.5),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.14),
  backgroundColor: theme.palette.background.paper,
  backgroundImage: "none",
  boxShadow: theme.shadows[2],
  [theme.breakpoints.up("md")]: {
    padding: theme.spacing(5, 5, 5.5),
  },
}));

const Eyebrow = styled(Text)(({ theme }) => ({
  ...theme.typography.overline,
  margin: 0,
  color: theme.palette.primary.dark,
  fontWeight: 700,
  letterSpacing: theme.typography.overline.letterSpacing,
}));

const HeroTitle = styled(Text)(({ theme }) => ({
  ...heroTypography(theme),
  maxWidth: "100%",
  margin: theme.spacing(1.5, 0, 0),
  color: theme.palette.text.primary,
  overflowWrap: "anywhere",
  textWrap: "balance",
}));

const HeroAccent = styled("span")(({ theme }) => ({
  color: theme.palette.text.primary,
}));

const LeadText = styled(Text)(({ theme }) => ({
  ...theme.typography.body1,
  maxWidth: 550,
  margin: theme.spacing(1.75, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.7,
}));

const StartLink = styled(Link)(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr) auto",
  alignItems: "center",
  justifyItems: "center",
  gap: theme.spacing(1),
  width: "100%",
  minHeight: theme.spacing(9),
  marginTop: theme.spacing(3),
  padding: theme.spacing(1.5, 2),
  borderRadius: scaledRadius(theme, 1),
  color: theme.palette.primary.contrastText,
  backgroundColor: theme.palette.primary.main,
  fontSize: theme.typography.button.fontSize,
  fontWeight: 700,
  textAlign: "center",
  textDecoration: "none",
  boxShadow: theme.shadows[2],
  transition: theme.transitions.create(["background-color", "box-shadow"]),
  "&:visited": { color: theme.palette.primary.contrastText },
  "&:hover, &:active": {
    color: theme.palette.primary.contrastText,
    backgroundColor: theme.palette.primary.dark,
    textDecoration: "none",
    boxShadow: theme.shadows[3],
  },
  "&:focus-visible": {
    color: theme.palette.primary.contrastText,
    outline: "3px solid " + theme.palette.primary.light,
    outlineOffset: 3,
    textDecoration: "none",
  },
  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
  [theme.breakpoints.up("sm")]: { paddingInline: theme.spacing(3) },
}));

export function HomeHero() {
  return (
    <HeroPanel>
      <Eyebrow variant="overline" component="p">
        ようこそ、Interview Pocketへ
      </Eyebrow>
      <HeroTitle variant="h1" component="h1">
        面接は、練習で、<HeroAccent>もっと話しやすくなる。</HeroAccent>
      </HeroTitle>
      <LeadText variant="body1" component="p">
        一問ずつ、自分のペースで。
        <br />
        AIのフィードバックを活かして、伝える力を磨こう。
      </LeadText>
      <StartLink href="/practice/" variant="text">
        <PlayArrowRoundedIcon aria-hidden="true" />
        <span>今すぐ面接練習を始める</span>
        <ArrowForwardRoundedIcon aria-hidden="true" />
      </StartLink>
    </HeroPanel>
  );
}
