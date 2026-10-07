/**
 * @file HomePage.tsx
 * @description アプリの目的と利用手順を伝えるトップページ
 */
"use client";
import { heroTypography, scaledRadius } from "@/theme/tokens";

import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";

type StepTone = "primary" | "secondary";

type GuideStep = {
  number: string;
  title: string;
  description: string;
  tone: StepTone;
};

const guideSteps: ReadonlyArray<GuideStep> = [
  {
    number: "01",
    title: "カテゴリを選ぶ",
    description: "練習したいテーマを選んで、一問から始めましょう。",
    tone: "primary",
  },
  {
    number: "02",
    title: "自分の言葉で答える",
    description: "質問を読み、経験や考えを文章にまとめましょう。",
    tone: "secondary",
  },
  {
    number: "03",
    title: "振り返って、もう一度",
    description: "フィードバックを確認して、再挑戦や次の質問へ進みましょう。",
    tone: "primary",
  },
];

const PageContent = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(4),
  minWidth: 0,
}));

const HeroPanel = styled(Panel)(({ theme }) => ({
  marginBottom: 0,
  padding: theme.spacing(2.5),
  background: `radial-gradient(circle at top right, ${alpha(
    theme.palette.primary.light,
    0.28,
  )} 0, transparent 58%), ${alpha(theme.palette.background.paper, 0.96)}`,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  boxShadow: `0 16px 48px ${alpha(theme.palette.primary.dark, 0.08)}`,
  [theme.breakpoints.up("md")]: {
    padding: theme.spacing(5),
  },
}));

const Eyebrow = styled(Text)(({ theme }) => ({
  ...theme.typography.overline,
  margin: theme.spacing(0, 0, 1.5),
  color: theme.palette.text.secondary,
  fontWeight: 700,
  lineHeight: 1.6,
  letterSpacing: "0.12em",
  overflowWrap: "anywhere",
}));

const HeroTitle = styled(Text)(({ theme }) => ({
  ...heroTypography(theme),
  margin: 0,
  color: theme.palette.primary.dark,
  fontWeight: 700,
  lineHeight: 1.3,
  letterSpacing: "-0.03em",
  overflowWrap: "anywhere",
}));

const LeadText = styled(Text)(({ theme }) => ({
  maxWidth: 560,
  ...theme.typography.body1,
  margin: theme.spacing(2.5, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
  overflowWrap: "anywhere",
}));

const StartLink = styled(Link)(({ theme }) => ({
  marginTop: theme.spacing(3),
  ...theme.typography.h3,
  fontWeight: 600,
}));

const GuideSection = styled("section")({ minWidth: 0 });

const GuideTitle = styled(Text)(({ theme }) => ({
  ...theme.typography.h2,
  margin: 0,
  color: theme.palette.text.primary,
  fontWeight: 700,
  lineHeight: 1.4,
  overflowWrap: "anywhere",
}));

const GuideDescription = styled(Text)(({ theme }) => ({
  ...theme.typography.body1,
  margin: theme.spacing(1.5, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
  overflowWrap: "anywhere",
}));

const StepsList = styled("ol")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  gap: theme.spacing(2),
  margin: theme.spacing(2.5, 0, 0),
  padding: 0,
  listStyle: "none",
  [theme.breakpoints.up("md")]: {
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  },
}));

const StepItem = styled("li", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: StepTone }>(({ theme, $tone }) => ({
  minWidth: 0,
  padding: theme.spacing(2.5),
  border: `1px solid ${alpha(
    $tone === "secondary"
      ? theme.palette.secondary.main
      : theme.palette.primary.main,
    $tone === "secondary" ? 0.22 : 0.12,
  )}`,
  borderRadius: scaledRadius(theme, 1),
  backgroundColor: alpha(
    $tone === "secondary"
      ? theme.palette.secondary.main
      : theme.palette.primary.main,
    $tone === "secondary" ? 0.08 : 0.04,
  ),
}));

const StepNumber = styled(Text)(({ theme }) => ({
  ...theme.typography.caption,
  display: "block",
  marginBottom: theme.spacing(2),
  color: theme.palette.primary.dark,
  fontWeight: 700,
  lineHeight: 1.5,
  letterSpacing: "0.1em",
  fontVariantNumeric: "tabular-nums",
}));

const StepTitle = styled(Text)(({ theme }) => ({
  ...theme.typography.h3,
  margin: 0,
  color: theme.palette.text.primary,
  fontWeight: 700,
  lineHeight: 1.5,
  overflowWrap: "anywhere",
}));

const StepDescription = styled(Text)(({ theme }) => ({
  ...theme.typography.body1,
  margin: theme.spacing(1.25, 0, 0),
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
  overflowWrap: "anywhere",
}));

/**
 * アプリの概要、開始導線、3段階の利用手順を表示する
 * @returns トップページUI
 */
export const HomePage = () => (
  <PageContent>
    <HeroPanel>
      <Eyebrow variant="overline" component="p">
        INTERVIEW POCKET · 1 QUESTION, 3 MINUTES
      </Eyebrow>
      <HeroTitle variant="h1" component="h1">
        今日の3分が、
        <br />
        面接の自信になる。
      </HeroTitle>
      <LeadText variant="body1" component="p">
        スキマ時間に、一問ずつ。自分の経験を言葉にする練習を始めましょう。
      </LeadText>
      <StartLink href="/practice/">面接練習を始める →</StartLink>
    </HeroPanel>

    <GuideSection aria-labelledby="home-guide-title">
      <GuideTitle variant="h2" component="h2" id="home-guide-title">
        あなたのペースで、伝える力を。
      </GuideTitle>
      <GuideDescription variant="body1" component="p">
        カテゴリを選び、回答を入力。フィードバックを読んで、同じ質問にも繰り返し取り組めます。
      </GuideDescription>
      <StepsList role="list">
        {guideSteps.map((step) => (
          <StepItem key={step.number} $tone={step.tone}>
            <StepNumber variant="caption" component="span" aria-hidden="true">
              {step.number}
            </StepNumber>
            <StepTitle variant="h3" component="h3">
              {step.title}
            </StepTitle>
            <StepDescription variant="body1" component="p">
              {step.description}
            </StepDescription>
          </StepItem>
        ))}
      </StepsList>
    </GuideSection>
  </PageContent>
);
