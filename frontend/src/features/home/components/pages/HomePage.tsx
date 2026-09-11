/**
 * @file HomePage.tsx
 * @description アプリの目的と利用手順を伝えるトップページ
 */
"use client";

import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
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

const PageContent = styled("div")({
  display: "grid",
  gap: 32,
  minWidth: 0,
});

const HeroPanel = styled(Panel)(({ theme }) => ({
  marginBottom: 0,
  padding: 20,
  background: `radial-gradient(circle at top right, ${alpha(
    theme.palette.primary.light,
    0.28,
  )} 0, transparent 58%), ${alpha(theme.palette.background.paper, 0.96)}`,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  boxShadow: `0 16px 48px ${alpha(theme.palette.primary.dark, 0.08)}`,
  "@media (min-width: 768px)": {
    padding: 40,
  },
}));

const Eyebrow = styled("p")(({ theme }) => ({
  margin: "0 0 12px",
  color: theme.palette.text.secondary,
  fontSize: 12,
  fontWeight: 700,
  lineHeight: 1.6,
  letterSpacing: "0.12em",
  overflowWrap: "anywhere",
}));

const HeroTitle = styled("h1")(({ theme }) => ({
  margin: 0,
  color: theme.palette.primary.dark,
  fontSize: 32,
  fontWeight: 700,
  lineHeight: 1.3,
  letterSpacing: "-0.03em",
  overflowWrap: "anywhere",
  "@media (min-width: 768px)": {
    fontSize: 44,
  },
}));

const LeadText = styled("p")(({ theme }) => ({
  maxWidth: 560,
  margin: "20px 0 0",
  color: theme.palette.text.secondary,
  fontSize: 16,
  lineHeight: 1.8,
  overflowWrap: "anywhere",
}));

const StartLink = styled(Link)({
  marginTop: 24,
  fontSize: 18,
  fontWeight: 600,
});

const GuideSection = styled("section")({
  minWidth: 0,
});

const GuideTitle = styled("h2")(({ theme }) => ({
  margin: 0,
  color: theme.palette.text.primary,
  fontSize: 22,
  fontWeight: 700,
  lineHeight: 1.4,
  overflowWrap: "anywhere",
  "@media (min-width: 768px)": {
    fontSize: 24,
  },
}));

const GuideDescription = styled("p")(({ theme }) => ({
  margin: "12px 0 0",
  color: theme.palette.text.secondary,
  fontSize: 16,
  lineHeight: 1.8,
  overflowWrap: "anywhere",
}));

const StepsList = styled("ol")({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  gap: 16,
  margin: "20px 0 0",
  padding: 0,
  listStyle: "none",
  "@media (min-width: 768px)": {
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  },
});

const StepItem = styled("li", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: StepTone }>(({ theme, $tone }) => ({
  minWidth: 0,
  padding: 20,
  border: `1px solid ${alpha(
    $tone === "secondary"
      ? theme.palette.secondary.main
      : theme.palette.primary.main,
    $tone === "secondary" ? 0.22 : 0.12,
  )}`,
  borderRadius: 16,
  backgroundColor: alpha(
    $tone === "secondary"
      ? theme.palette.secondary.main
      : theme.palette.primary.main,
    $tone === "secondary" ? 0.08 : 0.04,
  ),
}));

const StepNumber = styled("span")(({ theme }) => ({
  display: "block",
  marginBottom: 16,
  color: theme.palette.primary.dark,
  fontSize: 13,
  fontWeight: 700,
  lineHeight: 1.5,
  letterSpacing: "0.1em",
  fontVariantNumeric: "tabular-nums",
}));

const StepTitle = styled("h3")(({ theme }) => ({
  margin: 0,
  color: theme.palette.text.primary,
  fontSize: 18,
  fontWeight: 700,
  lineHeight: 1.5,
  overflowWrap: "anywhere",
}));

const StepDescription = styled("p")(({ theme }) => ({
  margin: "10px 0 0",
  color: theme.palette.text.secondary,
  fontSize: 16,
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
      <Eyebrow>INTERVIEW POCKET · 1 QUESTION, 3 MINUTES</Eyebrow>
      <HeroTitle>
        今日の3分が、
        <br />
        面接の自信になる。
      </HeroTitle>
      <LeadText>
        スキマ時間に、一問ずつ。自分の経験を言葉にする練習を始めましょう。
      </LeadText>
      <StartLink href="/practice/">面接練習を始める →</StartLink>
    </HeroPanel>

    <GuideSection aria-labelledby="home-guide-title">
      <GuideTitle id="home-guide-title">
        あなたのペースで、伝える力を。
      </GuideTitle>
      <GuideDescription>
        カテゴリを選び、回答を入力。フィードバックを読んで、同じ質問にも繰り返し取り組めます。
      </GuideDescription>
      <StepsList role="list">
        {guideSteps.map((step) => (
          <StepItem key={step.number} $tone={step.tone}>
            <StepNumber aria-hidden="true">{step.number}</StepNumber>
            <StepTitle>{step.title}</StepTitle>
            <StepDescription>{step.description}</StepDescription>
          </StepItem>
        ))}
      </StepsList>
    </GuideSection>
  </PageContent>
);
