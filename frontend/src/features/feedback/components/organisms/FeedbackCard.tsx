/**
 * @file FeedbackCard.tsx
 * @description スコアと評価内容を読みやすく整理するフィードバックレポート
 */
"use client";
import { scoreTypography, scaledRadius, radiusLength } from "@/theme/tokens";

import { alpha, styled } from "@mui/material/styles";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import type { Feedback } from "@/lib/api/schemas";
import {
  isFeedbackV2,
  type LegacyFeedback,
  type FeedbackV2,
} from "@/lib/api/schemas";

type PointTone = "strength" | "improvement";

const FeedbackPanel = styled(Panel)(({ theme }) => ({
  padding: theme.spacing(2.5),
  overflow: "hidden",
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  borderRadius: scaledRadius(theme, 1.5),
  background: alpha(theme.palette.common.white, 0.94),
  boxShadow: `0 20px 60px ${alpha(theme.palette.primary.dark, 0.1)}`,
  [theme.breakpoints.up("md")]: {
    padding: theme.spacing(4),
  },
}));

const Introduction = styled(MascotCoachCard)(({ theme }) => ({
  margin: theme.spacing(-2.5, -2.5, 3),
  borderRadius: `${radiusLength(theme, 1.4375)} ${radiusLength(theme, 1.4375)} ${radiusLength(theme, 1.25)} ${radiusLength(theme, 1.25)}`,
  [theme.breakpoints.up("md")]: { margin: theme.spacing(-4, -4, 3) },
}));
const TitlePhrase = styled("span")({
  display: "inline-block",
  maxWidth: "100%",
});

const Eyebrow = styled(Text)(({ theme }) => ({
  margin: theme.spacing(0, 0, 0.75),
  ...theme.typography.overline,
  color: theme.palette.text.secondary,
  fontWeight: 700,
  letterSpacing: "0.14em",
}));

const Title = styled(Text)(({ theme }) => ({
  margin: 0,
  ...theme.typography.h1,
  color: theme.palette.text.primary,
  fontWeight: 700,
  lineHeight: 1.4,
  letterSpacing: "-0.02em",
}));

const ReportFlow = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(3),
}));

const ScoreBlock = styled("div")(({ theme }) => ({
  minWidth: 0,
  marginTop: theme.spacing(2.5),
}));

const SectionTitle = styled(Text)(({ theme }) => ({
  margin: theme.spacing(0, 0, 1.5),
  ...theme.typography.h2,
  color: theme.palette.text.primary,
  fontWeight: 700,
  lineHeight: 1.5,
}));

const ScoreLine = styled("p")(({ theme }) => ({
  display: "flex",
  alignItems: "baseline",
  gap: theme.spacing(1),
  margin: 0,
  fontVariantNumeric: "tabular-nums",
}));

const ScoreValue = styled(Text)(({ theme }) => ({
  ...scoreTypography(theme),
  color: theme.palette.primary.dark,
  fontWeight: 700,
  lineHeight: 1,
  letterSpacing: "-0.04em",
}));

const ScoreScale = styled(Text)(({ theme }) => ({
  ...theme.typography.body1,
  color: theme.palette.text.secondary,
  fontWeight: 600,
}));

const BodyText = styled(Text)(({ theme }) => ({
  minWidth: 0,
  margin: 0,
  ...theme.typography.body1,
  color: theme.palette.text.primary,
  lineHeight: 1.8,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
}));

const QuestionSection = styled("section")(({ theme }) => ({
  minWidth: 0,
  padding: theme.spacing(2.5),
  borderRadius: scaledRadius(theme, 1),
  backgroundColor: theme.palette.background.default,
}));

const AnswerSection = styled("section")(({ theme }) => ({
  minWidth: 0,
  padding: theme.spacing(0, 0.5),
}));

const AnswerText = styled(BodyText)(({ theme }) => ({
  paddingLeft: theme.spacing(2),
  borderLeft: `3px solid ${alpha(theme.palette.primary.main, 0.25)}`,
}));

const PointsGrid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  alignItems: "start",
  gap: theme.spacing(2),
  minWidth: 0,
  [theme.breakpoints.up("md")]: {
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  },
}));

const PointsSection = styled("section", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: PointTone }>(({ theme, $tone }) => ({
  minWidth: 0,
  padding: theme.spacing(2.5),
  border: `1px solid ${
    $tone === "strength"
      ? alpha(theme.palette.primary.main, 0.14)
      : alpha(theme.palette.secondary.main, 0.24)
  }`,
  borderRadius: scaledRadius(theme, 1),
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
  gap: theme.spacing(1.5),
  margin: 0,
  paddingLeft: theme.spacing(2.5),
  color: theme.palette.text.primary,
  ...theme.typography.body1,
  lineHeight: 1.8,
  "& li": {
    paddingLeft: theme.spacing(0.5),
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
  },
}));

const EmptyText = styled(BodyText)(({ theme }) => ({
  color: theme.palette.text.secondary,
}));

const ExampleSection = styled("section")(({ theme }) => ({
  minWidth: 0,
  padding: theme.spacing(2.5),
  border: `1px solid ${alpha(theme.palette.secondary.main, 0.18)}`,
  borderRadius: scaledRadius(theme, 1),
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
    <SectionTitle variant="h2" component="h2">
      {title}
    </SectionTitle>
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
const LegacyFeedbackCard = ({ feedback }: { feedback: LegacyFeedback }) => (
  <FeedbackPanel>
    <Introduction
      variant="success"
      emphasis="featured"
      heading={
        <>
          <Eyebrow variant="overline" component="p">
            FEEDBACK
          </Eyebrow>
          <Title variant="h1" component="h1" aria-label="今回のフィードバック">
            今回の<TitlePhrase>フィードバック</TitlePhrase>
          </Title>
          <ScoreBlock>
            <SectionTitle variant="h2" component="h2">
              総合評価
            </SectionTitle>
            <ScoreLine>
              <ScoreValue variant="h1" component="span">
                {feedback.score}
              </ScoreValue>
              <ScoreScale variant="body1" component="span">
                / 100
              </ScoreScale>
            </ScoreLine>
          </ScoreBlock>
        </>
      }
    >
      <Text>{feedback.summary}</Text>
    </Introduction>
    <ReportFlow>
      <QuestionSection>
        <SectionTitle variant="h2" component="h2">
          質問
        </SectionTitle>
        <BodyText variant="body1" component="p">
          {feedback.question.question}
        </BodyText>
      </QuestionSection>
      <AnswerSection>
        <SectionTitle variant="h2" component="h2">
          あなたの回答
        </SectionTitle>
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
          <SectionTitle variant="h2" component="h2">
            回答例
          </SectionTitle>
          <BodyText variant="body1" component="p">
            {feedback.exampleAnswer}
          </BodyText>
        </ExampleSection>
      )}
    </ReportFlow>
  </FeedbackPanel>
);

const CoachingFeedbackCard = ({ feedback: f }: { feedback: FeedbackV2 }) => (
  <FeedbackPanel>
    <Introduction
      variant="success"
      emphasis="featured"
      heading={
        <>
          <Eyebrow variant="overline" component="p">
            FEEDBACK
          </Eyebrow>
          <Title variant="h1" component="h1">
            今回のフィードバック
          </Title>
          <ScoreBlock>
            <SectionTitle variant="h2" component="h2">
              総合評価
            </SectionTitle>
            <ScoreLine>
              <ScoreValue component="span">{f.totalScore}</ScoreValue>
              <ScoreScale component="span">/ 30 · {f.rank}</ScoreScale>
            </ScoreLine>
          </ScoreBlock>
        </>
      }
    >
      <Text>
        {f.result.status === "coaching"
          ? "追加の情報を確認して、回答を育てましょう。"
          : "現時点の本人情報で回答をまとめました。"}
      </Text>
    </Introduction>
    <ReportFlow>
      <BodyText>
        結論 {f.result.conclusion_score} / 10 · 具体性{" "}
        {f.result.specificity_score} / 10 · 根拠 {f.result.reasoning_score} / 10
      </BodyText>
      <BodyText>
        初回回答 {f.answerLength}文字 · 合計 {f.baseScore}点 · 文字数減点{" "}
        {f.lengthPenalty}点
      </BodyText>
      <QuestionSection>
        <SectionTitle component="h2">質問</SectionTitle>
        <BodyText>{f.question.question}</BodyText>
      </QuestionSection>
      <AnswerSection>
        <SectionTitle component="h2">初回の回答</SectionTitle>
        <AnswerText>{f.answer}</AnswerText>
      </AnswerSection>
      {f.coachingHistory.length > 0 && (
        <details>
          <summary>深掘りの履歴（{f.coachingCount}回）</summary>
          {f.coachingHistory.map((h, i) => (
            <QuestionSection key={i}>
              <BodyText>{h.question}</BodyText>
              <AnswerText>{h.answer}</AnswerText>
            </QuestionSection>
          ))}
        </details>
      )}
      <PointsGrid>
        <Points
          title="良かった点"
          values={[f.result.good_point]}
          tone="strength"
        />
        <Points
          title="改善ポイント"
          values={[f.result.improvement]}
          tone="improvement"
        />
      </PointsGrid>
      {f.result.example !== null && (
        <ExampleSection>
          <SectionTitle component="h2">改善回答</SectionTitle>
          <BodyText>{f.result.example}</BodyText>
        </ExampleSection>
      )}
    </ReportFlow>
  </FeedbackPanel>
);
export const FeedbackCard = ({ feedback }: { feedback: Feedback }) =>
  isFeedbackV2(feedback) ? (
    <CoachingFeedbackCard feedback={feedback} />
  ) : (
    <LegacyFeedbackCard feedback={feedback} />
  );
