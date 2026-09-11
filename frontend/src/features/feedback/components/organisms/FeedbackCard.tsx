/**
 * @file FeedbackCard.tsx
 * @description スコアと評価内容を読みやすく整理するフィードバックレポート
 */
"use client";

import { alpha, styled } from "@mui/material/styles";
import { Panel } from "@/components/atoms/Panel";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import type { Feedback } from "@/lib/api/schemas";

type PointTone = "strength" | "improvement";

const FeedbackPanel = styled(Panel)(({ theme }) => ({
  padding: 20,
  overflow: "hidden",
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  borderRadius: 24,
  background: alpha(theme.palette.common.white, 0.94),
  boxShadow: `0 20px 60px ${alpha(theme.palette.primary.dark, 0.1)}`,
  "@media (min-width: 768px)": {
    padding: 32,
  },
}));

const Introduction = styled(MascotCoachCard)({
  margin: "-20px -20px 24px",
  borderRadius: "23px 23px 20px 20px",
  "@media (min-width: 768px)": { margin: "-32px -32px 24px" },
});
const TitlePhrase = styled("span")({
  display: "inline-block",
  maxWidth: "100%",
});

const Eyebrow = styled("p")(({ theme }) => ({
  margin: "0 0 6px",
  color: theme.palette.text.secondary,
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: "0.14em",
}));

const Title = styled("h1")(({ theme }) => ({
  margin: 0,
  color: theme.palette.text.primary,
  fontSize: 24,
  fontWeight: 700,
  lineHeight: 1.4,
  letterSpacing: "-0.02em",
  "@media (min-width: 768px)": {
    fontSize: 28,
  },
}));

const ReportFlow = styled("div")({
  display: "grid",
  gap: 24,
});

const ScoreBlock = styled("div")({
  minWidth: 0,
  marginTop: 20,
});

const SectionTitle = styled("h2")(({ theme }) => ({
  margin: "0 0 12px",
  color: theme.palette.text.primary,
  fontSize: 18,
  fontWeight: 700,
  lineHeight: 1.5,
}));

const ScoreLine = styled("p")({
  display: "flex",
  alignItems: "baseline",
  gap: 8,
  margin: 0,
  fontVariantNumeric: "tabular-nums",
});

const ScoreValue = styled("span")(({ theme }) => ({
  color: theme.palette.primary.dark,
  fontSize: 48,
  fontWeight: 700,
  lineHeight: 1,
  letterSpacing: "-0.04em",
  "@media (min-width: 768px)": {
    fontSize: 64,
  },
}));

const ScoreScale = styled("span")(({ theme }) => ({
  color: theme.palette.text.secondary,
  fontSize: 16,
  fontWeight: 600,
}));

const BodyText = styled("p")(({ theme }) => ({
  minWidth: 0,
  margin: 0,
  color: theme.palette.text.primary,
  fontSize: 16,
  lineHeight: 1.8,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
}));

const QuestionSection = styled("section")(({ theme }) => ({
  minWidth: 0,
  padding: 20,
  borderRadius: 16,
  backgroundColor: theme.palette.background.default,
}));

const AnswerSection = styled("section")({
  minWidth: 0,
  padding: "0 4px",
});

const AnswerText = styled(BodyText)(({ theme }) => ({
  paddingLeft: 16,
  borderLeft: `3px solid ${alpha(theme.palette.primary.main, 0.25)}`,
}));

const PointsGrid = styled("div")({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  alignItems: "start",
  gap: 16,
  minWidth: 0,
  "@media (min-width: 768px)": {
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  },
});

const PointsSection = styled("section", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: PointTone }>(({ theme, $tone }) => ({
  minWidth: 0,
  padding: 20,
  border: `1px solid ${
    $tone === "strength"
      ? alpha(theme.palette.primary.main, 0.14)
      : alpha(theme.palette.secondary.main, 0.24)
  }`,
  borderRadius: 16,
  backgroundColor:
    $tone === "strength"
      ? alpha(theme.palette.primary.main, 0.05)
      : alpha(theme.palette.secondary.main, 0.1),
  "& h2": {
    color:
      $tone === "strength"
        ? theme.palette.primary.dark
        : theme.palette.text.primary,
  },
  "& li::marker": {
    color:
      $tone === "strength"
        ? theme.palette.primary.main
        : theme.palette.secondary.dark,
  },
}));

const PointsList = styled("ul")(({ theme }) => ({
  display: "grid",
  gap: 12,
  margin: 0,
  paddingLeft: 20,
  color: theme.palette.text.primary,
  fontSize: 16,
  lineHeight: 1.8,
  "& li": {
    paddingLeft: 4,
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
  },
}));

const EmptyText = styled(BodyText)(({ theme }) => ({
  color: theme.palette.text.secondary,
}));

const ExampleSection = styled("section")(({ theme }) => ({
  minWidth: 0,
  padding: 20,
  border: `1px solid ${alpha(theme.palette.secondary.main, 0.18)}`,
  borderRadius: 16,
  backgroundColor: alpha(theme.palette.secondary.main, 0.06),
}));

const Points = ({
  title,
  values,
  tone,
}: {
  title: string;
  values: string[];
  tone: PointTone;
}) => (
  <PointsSection $tone={tone}>
    <SectionTitle>{title}</SectionTitle>
    {values.length ? (
      <PointsList>
        {values.map((value, index) => (
          <li key={index}>{value}</li>
        ))}
      </PointsList>
    ) : (
      <EmptyText>該当する項目はありません</EmptyText>
    )}
  </PointsSection>
);

/** 評価結果をレポート形式で表示する */
export const FeedbackCard = ({ feedback }: { feedback: Feedback }) => (
  <FeedbackPanel>
    <Introduction
      variant="success"
      emphasis="featured"
      heading={
        <>
          <Eyebrow>FEEDBACK</Eyebrow>
          <Title aria-label="今回のフィードバック">
            今回の<TitlePhrase>フィードバック</TitlePhrase>
          </Title>
          <ScoreBlock>
            <SectionTitle>総合評価</SectionTitle>
            <ScoreLine>
              <ScoreValue>{feedback.score}</ScoreValue>
              <ScoreScale>/ 100</ScoreScale>
            </ScoreLine>
          </ScoreBlock>
        </>
      }
    >
      <p>{feedback.summary}</p>
    </Introduction>
    <ReportFlow>
      <QuestionSection>
        <SectionTitle>質問</SectionTitle>
        <BodyText>{feedback.question.question}</BodyText>
      </QuestionSection>
      <AnswerSection>
        <SectionTitle>あなたの回答</SectionTitle>
        <AnswerText>{feedback.answer}</AnswerText>
      </AnswerSection>
      <PointsGrid>
        <Points
          title="良かった点"
          values={feedback.strengths}
          tone="strength"
        />
        <Points
          title="改善ポイント"
          values={feedback.improvements}
          tone="improvement"
        />
      </PointsGrid>
      {feedback.exampleAnswer && (
        <ExampleSection>
          <SectionTitle>回答例</SectionTitle>
          <BodyText>{feedback.exampleAnswer}</BodyText>
        </ExampleSection>
      )}
    </ReportFlow>
  </FeedbackPanel>
);
