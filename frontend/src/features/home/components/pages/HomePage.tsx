/**
 * @file HomePage.tsx
 * @description スマートフォンでもすぐ練習を始められるホーム画面
 */
"use client";

import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { heroTypography, scaledRadius } from "@/theme/tokens";

type GuideStep = {
  number: string;
  title: string;
  description: string;
};

const guideSteps: ReadonlyArray<GuideStep> = [
  {
    number: "01",
    title: "質問を選ぶ",
    description: "練習したいテーマを選択。まずは一問から。",
  },
  {
    number: "02",
    title: "自分の言葉で答える",
    description: "これまでの経験や考えを文章にまとめます。",
  },
  {
    number: "03",
    title: "振り返って磨く",
    description: "フィードバックを確認して、次の回答へ。",
  },
];

const PageContent = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(4),
  minWidth: 0,
  [theme.breakpoints.up("md")]: { gap: theme.spacing(5) },
}));

const HeroPanel = styled(Panel)(({ theme }) => ({
  position: "relative",
  isolation: "isolate",
  overflow: "hidden",
  minWidth: 0,
  marginBottom: 0,
  padding: theme.spacing(3, 2.75, 3.5),
  borderRadius: scaledRadius(theme, 1.5),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.12)}`,
  backgroundColor: theme.palette.background.paper,
  backgroundImage: `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 1)} 35%, ${alpha(theme.palette.primary.light, 0.13)} 100%)`,
  boxShadow: `0 14px 40px ${alpha(theme.palette.primary.dark, 0.07)}`,
  "&::before": {
    content: '""',
    position: "absolute",
    zIndex: -1,
    top: theme.spacing(-12),
    right: theme.spacing(-13),
    width: theme.spacing(36),
    height: theme.spacing(36),
    borderRadius: "50%",
    border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
    pointerEvents: "none",
  },
  [theme.breakpoints.up("md")]: {
    padding: theme.spacing(6, 6, 5.5),
    borderRadius: scaledRadius(theme, 1.75),
  },
}));

const Eyebrow = styled(Text)(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: theme.spacing(1),
  margin: 0,
  color: theme.palette.primary.dark,
  fontSize: theme.typography.overline.fontSize,
  fontWeight: theme.typography.overline.fontWeight,
  letterSpacing: theme.typography.overline.letterSpacing,
  lineHeight: theme.typography.overline.lineHeight,
  "&::before": {
    content: '""',
    display: "block",
    flexShrink: 0,
    width: theme.spacing(0.75),
    height: theme.spacing(0.75),
    borderRadius: "50%",
    backgroundColor: theme.palette.primary.main,
  },
}));

const HeroTitle = styled(Text)(({ theme }) => ({
  ...heroTypography(theme),
  maxWidth: "100%",
  margin: theme.spacing(2.25, 0, 0),
  color: theme.palette.text.primary,
  overflowWrap: "anywhere",
  textWrap: "balance",
  [theme.breakpoints.up("md")]: {
    marginTop: theme.spacing(3),
  },
}));

const HeroAccent = styled("span")(({ theme }) => ({
  color: theme.palette.primary.dark,
}));

const LeadText = styled(Text)(({ theme }) => ({
  ...theme.typography.body1,
  maxWidth: 530,
  margin: theme.spacing(2, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
  [theme.breakpoints.up("md")]: {
    marginTop: theme.spacing(2.5),
  },
}));

const StartLink = styled(Link)(({ theme }) => ({
  display: "inline-flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: theme.spacing(3),
  width: "100%",
  minHeight: theme.spacing(6.5),
  marginTop: theme.spacing(3),
  padding: theme.spacing(1.5, 2.5),
  borderRadius: scaledRadius(theme, 0.75),
  backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText,
  fontSize: theme.typography.body1.fontSize,
  fontWeight: 700,
  textDecoration: "none",
  boxShadow: `0 7px 18px ${alpha(theme.palette.primary.dark, 0.18)}`,
  transition: theme.transitions.create(["background-color", "box-shadow"]),
  "&:visited": {
    color: theme.palette.primary.contrastText,
  },
  "&:hover, &:active": {
    color: theme.palette.primary.contrastText,
    backgroundColor: theme.palette.primary.dark,
    textDecoration: "none",
    boxShadow: `0 9px 22px ${alpha(theme.palette.primary.dark, 0.23)}`,
  },
  "&:focus-visible": {
    color: theme.palette.primary.contrastText,
    outline: `3px solid ${theme.palette.primary.light}`,
    outlineOffset: 3,
    textDecoration: "none",
  },
  "@media (prefers-reduced-motion: reduce)": {
    transition: "none",
  },
  [theme.breakpoints.up("sm")]: {
    width: "auto",
    minWidth: theme.spacing(32),
  },
}));

const GuideSection = styled("section")({
  minWidth: 0,
});

const GuideEyebrow = styled(Text)(({ theme }) => ({
  margin: 0,
  color: theme.palette.primary.dark,
  ...theme.typography.overline,
}));

const GuideTitle = styled(Text)(({ theme }) => ({
  ...theme.typography.h2,
  margin: theme.spacing(1, 0, 0),
  fontWeight: 700,
  color: theme.palette.text.primary,
}));

const GuideDescription = styled(Text)(({ theme }) => ({
  ...theme.typography.body2,
  margin: theme.spacing(1, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.7,
}));

const StepsList = styled("ol")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  gap: theme.spacing(1.5),
  padding: 0,
  margin: theme.spacing(2.5, 0, 0),
  listStyle: "none",
  [theme.breakpoints.up("md")]: {
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  },
}));

const StepItem = styled("li")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr)",
  alignContent: "start",
  columnGap: theme.spacing(2),
  rowGap: theme.spacing(0.5),
  minWidth: 0,
  padding: theme.spacing(2),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
  borderRadius: scaledRadius(theme, 1),
  backgroundColor: alpha(theme.palette.background.paper, 0.92),
  [theme.breakpoints.up("md")]: {
    gridTemplateColumns: "minmax(0, 1fr)",
    padding: theme.spacing(2.5),
  },
}));

const StepNumber = styled(Text)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gridRow: "1 / span 2",
  width: theme.spacing(5),
  height: theme.spacing(5),
  borderRadius: scaledRadius(theme, 0.65),
  backgroundColor: alpha(theme.palette.primary.main, 0.08),
  color: theme.palette.primary.dark,
  fontSize: theme.typography.body2.fontSize,
  fontWeight: 800,
  fontVariantNumeric: "tabular-nums",
  [theme.breakpoints.up("md")]: {
    gridRow: "auto",
    marginBottom: theme.spacing(1),
  },
}));

const StepTitle = styled(Text)(({ theme }) => ({
  ...theme.typography.h3,
  minWidth: 0,
  margin: 0,
  color: theme.palette.text.primary,
  fontWeight: 700,
}));

const StepDescription = styled(Text)(({ theme }) => ({
  ...theme.typography.body2,
  minWidth: 0,
  margin: 0,
  color: theme.palette.text.secondary,
  lineHeight: 1.65,
}));

/** 主要CTAを最初の画面に置き、3ステップで利用方法を案内する。 */
export const HomePage = () => (
  <PageContent>
    <HeroPanel>
      <Eyebrow component="p">
        AI INTERVIEW PRACTICE
      </Eyebrow>
      <HeroTitle variant="h1" component="h1">
        今日の3分を、
        <br />
        <HeroAccent>面接の自信に。</HeroAccent>
      </HeroTitle>
      <LeadText variant="body1" component="p">
        一問ずつ答えて、フィードバックで磨く。
        <br />
        自分のペースで、面接の準備を始めよう。
      </LeadText>
      <StartLink href="/practice/" variant="text">
        面接練習を始める
        <span aria-hidden="true">↗</span>
      </StartLink>
    </HeroPanel>

    <GuideSection aria-labelledby="home-guide-title">
      <GuideEyebrow variant="overline" component="p">
        HOW IT WORKS
      </GuideEyebrow>
      <GuideTitle variant="h2" component="h2" id="home-guide-title">
        選んで、答えて、振り返る。
      </GuideTitle>
      <GuideDescription variant="body2" component="p">
        3つのステップで、気軽に面接練習を続けられます。
      </GuideDescription>
      <StepsList>
        {guideSteps.map((step) => (
          <StepItem key={step.number}>
            <StepNumber component="span" aria-hidden="true">
              {step.number}
            </StepNumber>
            <StepTitle variant="h3" component="h3">
              {step.title}
            </StepTitle>
            <StepDescription variant="body2" component="p">
              {step.description}
            </StepDescription>
          </StepItem>
        ))}
      </StepsList>
    </GuideSection>
  </PageContent>
);
