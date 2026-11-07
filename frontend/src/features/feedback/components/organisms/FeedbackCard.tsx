/**
 * @file FeedbackCard.tsx
 * @description Coaching V2と通常評価を共通のスコア表示・省略カードへ整理する。
 */
"use client";

import { useState, type ReactNode } from "react";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ThumbUpOutlinedIcon from "@mui/icons-material/ThumbUpOutlined";
import LightbulbOutlinedIcon from "@mui/icons-material/LightbulbOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import TrackChangesOutlinedIcon from "@mui/icons-material/TrackChangesOutlined";
import LayersOutlinedIcon from "@mui/icons-material/LayersOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { alpha, styled } from "@mui/material/styles";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { FullTextDialog } from "@/components/organisms/FullTextDialog";
import { FullTextPreview } from "@/components/organisms/FullTextPreview";
import { scaledRadius, radiusLength } from "@/theme/tokens";
import type { Feedback, FeedbackV2, LegacyFeedback, FollowUpReviewItem } from "@/lib/api/schemas";
import { isFeedbackV2 } from "@/lib/api/schemas";
import { FeedbackScoreSummary } from "./FeedbackScoreSummary";

type Tone = "standard" | "strength" | "improvement";
type FullTextTarget = { title: string; text: string; icon?: ReactNode };
type OpenFullText = (title: string, text: string, icon?: ReactNode) => void;

const Report = styled(Panel)(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(3),
  padding: theme.spacing(2),
  minWidth: 0,
  overflow: "hidden",
  border: "1px solid " + alpha(theme.palette.primary.main, 0.14),
  borderRadius: scaledRadius(theme, 1.5),
  backgroundColor: theme.palette.background.paper,
  boxShadow: "0 12px 38px " + alpha(theme.palette.primary.dark, 0.09),
  [theme.breakpoints.up("md")]: { padding: theme.spacing(3) },
}));

const Introduction = styled(MascotCoachCard)(({ theme }) => ({
  margin: theme.spacing(-2, -2, 0),
  borderRadius:
    radiusLength(theme, 1.4375) + " " + radiusLength(theme, 1.4375) + " " +
    radiusLength(theme, 1) + " " + radiusLength(theme, 1),
  [theme.breakpoints.up("md")]: { margin: theme.spacing(-3, -3, 0) },
}));

const Eyebrow = styled(Text)(({ theme }) => ({
  margin: theme.spacing(0, 0, 0.5),
  ...theme.typography.overline,
  fontWeight: 700,
  color: theme.palette.primary.dark,
}));

const Headline = styled(Text)(({ theme }) => ({
  margin: 0,
  ...theme.typography.h1,
  color: theme.palette.text.primary,
  lineHeight: 1.35,
}));

const ScoreStack = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  minWidth: 0,
}));

const ResultList = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.5),
  minWidth: 0,
}));

const Detail = styled("section", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: Tone }>(({ theme, $tone }) => ({
  minWidth: 0,
  display: "grid",
  gap: theme.spacing(1),
  padding: theme.spacing(2),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.12),
  borderRadius: scaledRadius(theme, 1),
  backgroundColor:
    $tone === "strength" ? alpha(theme.palette.primary.main, 0.055) :
    $tone === "improvement" ? alpha(theme.palette.secondary.main, 0.095) :
    alpha(theme.palette.primary.main, 0.025),
  [theme.breakpoints.up("md")]: {
    gridTemplateColumns: "minmax(0, 180px) minmax(0, 1fr)",
    alignItems: "start",
    gap: theme.spacing(2),
  },
}));

const DetailTitle = styled("div")(({ theme }) => ({
  display: "flex",
  minWidth: 0,
  alignItems: "center",
  gap: theme.spacing(1.25),
}));

const DetailIcon = styled("span")(({ theme }) => ({
  display: "inline-flex",
  flexShrink: 0,
  color: theme.palette.primary.dark,
}));

const DetailHeading = styled(Text)(({ theme }) => ({
  margin: 0,
  ...theme.typography.h3,
  fontWeight: 700,
  color: theme.palette.text.primary,
  overflowWrap: "anywhere",
}));

const DetailContent = styled("div")({
  minWidth: 0,
});

const PointsList = styled("ul")(({ theme }) => ({
  margin: 0,
  paddingLeft: theme.spacing(2.5),
  display: "grid",
  gap: theme.spacing(1),
  "& li": { minWidth: 0, overflowWrap: "anywhere" },
  "& li::marker": { color: theme.palette.primary.main },
}));

const Empty = styled(Text)(({ theme }) => ({
  color: theme.palette.text.secondary,
}));

const CoachingHistory = styled("details")(({ theme }) => ({
  border: "1px solid " + theme.palette.divider,
  borderRadius: scaledRadius(theme, 1),
  padding: theme.spacing(2),
  minWidth: 0,
  "& > summary": {
    cursor: "pointer",
    ...theme.typography.body1,
    fontWeight: 700,
    color: theme.palette.primary.dark,
  },
  "& > summary:focus-visible": {
    outline: "3px solid " + theme.palette.primary.main,
    outlineOffset: 3,
  },
}));

const HistoryItems = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.5),
  marginTop: theme.spacing(2),
}));


const ReviewPanel = styled(Panel, {
  shouldForwardProp: (prop) => prop !== "$compact",
})<{ $compact: boolean }>(({ theme, $compact }) => ({
  display: "grid",
  gap: theme.spacing($compact ? 1.5 : 2.5),
  padding: theme.spacing($compact ? 2 : 2.5),
  minWidth: 0,
  overflowWrap: "anywhere",
  border: "1px solid " + alpha(theme.palette.primary.main, 0.17),
  borderRadius: scaledRadius(theme, 1.5),
  backgroundColor: "#FFFEFB",
  boxShadow: "0 8px 28px " + alpha(theme.palette.text.primary, 0.07),
  [theme.breakpoints.up("md")]: {
    padding: theme.spacing($compact ? 2.5 : 3.5),
  },
}));

const ReviewHeading = styled(Text)(({ theme }) => ({
  margin: 0,
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  minWidth: 0,
  fontWeight: 700,
  color: theme.palette.text.primary,
  "&::before": {
    content: '""',
    display: "block",
    width: 6,
    height: 28,
    flexShrink: 0,
    borderRadius: 4,
    backgroundColor: theme.palette.primary.light,
  },
}));

const ReviewOverview = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: theme.spacing(1.5),
  minWidth: 0,
}));

const ReviewTotal = styled("p")(({ theme }) => ({
  display: "flex",
  alignItems: "baseline",
  gap: theme.spacing(0.75),
  margin: 0,
  lineHeight: 1.2,
  whiteSpace: "nowrap",
  fontVariantNumeric: "tabular-nums",
}));

const ReviewTotalNumber = styled("span")(({ theme }) => ({
  color: theme.palette.primary.dark,
  fontSize: "clamp(2.5rem, 9vw, 3.4rem)",
  fontWeight: 800,
  letterSpacing: "-0.045em",
}));

const ReviewTotalUnit = styled("span")(({ theme }) => ({
  color: theme.palette.text.primary,
  fontSize: "clamp(1.05rem, 4.2vw, 1.4rem)",
  fontWeight: 700,
}));

const ReviewBadge = styled("span", {
  shouldForwardProp: (prop) => prop !== "$tone",
})<{ $tone: "positive" | "caution" | "neutral" }>(({ theme, $tone }) => {
  const color =
    $tone === "caution" ? theme.palette.warning.dark :
    $tone === "neutral" ? theme.palette.text.secondary :
    theme.palette.primary.dark;
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing(0.75),
    maxWidth: "100%",
    minWidth: 0,
    padding: theme.spacing(0.75, 1.5),
    borderRadius: 999,
    backgroundColor: alpha(color, 0.09),
    color,
    fontSize: "0.875rem",
    fontWeight: 700,
    lineHeight: 1.5,
    textAlign: "center",
    "& svg": { flexShrink: 0, fontSize: "1.25rem" },
  };
});

const ReviewDivider = styled("hr")(({ theme }) => ({
  width: "100%",
  margin: 0,
  border: 0,
  borderTop: "1px solid " + alpha(theme.palette.text.secondary, 0.16),
}));

const ReviewScores = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.25),
  minWidth: 0,
}));

const ReviewScore = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr) auto",
  alignItems: "center",
  gap: theme.spacing(1.25),
  minHeight: 64,
  minWidth: 0,
  padding: theme.spacing(1, 1.5),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.18),
  borderRadius: 999,
  backgroundColor: theme.palette.background.paper,
  "@media (max-width: 359.95px)": {
    gap: theme.spacing(0.75),
    padding: theme.spacing(0.75, 1),
  },
}));

const ReviewScoreIcon = styled("span")(({ theme }) => ({
  display: "inline-grid",
  placeItems: "center",
  width: 42,
  height: 42,
  flexShrink: 0,
  borderRadius: "50%",
  backgroundColor: alpha(theme.palette.primary.main, 0.085),
  color: theme.palette.primary.dark,
  "& svg": { fontSize: "1.4rem" },
  "@media (max-width: 359.95px)": { width: 36, height: 36 },
}));

const ReviewScoreName = styled(Text)(({ theme }) => ({
  margin: 0,
  minWidth: 0,
  fontSize: "1rem",
  fontWeight: 700,
  lineHeight: 1.4,
  color: theme.palette.text.primary,
  "@media (max-width: 359.95px)": { fontSize: "0.875rem" },
}));

const ReviewScoreValue = styled("span")(({ theme }) => ({
  whiteSpace: "nowrap",
  color: theme.palette.text.primary,
  fontSize: "1rem",
  fontWeight: 600,
  fontVariantNumeric: "tabular-nums",
  "& strong": {
    color: theme.palette.primary.dark,
    fontSize: "1.2rem",
  },
  "@media (max-width: 359.95px)": {
    fontSize: "0.875rem",
    "& strong": { fontSize: "1rem" },
  },
}));

const ReviewNarrative = styled("section")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "44px minmax(0, 1fr)",
  alignItems: "start",
  gap: theme.spacing(1.25),
  minWidth: 0,
}));

const ReviewNarrativeIcon = styled("span")(({ theme }) => ({
  display: "inline-grid",
  placeItems: "center",
  width: 44,
  height: 44,
  borderRadius: "50%",
  color: theme.palette.primary.dark,
  backgroundColor: alpha(theme.palette.primary.main, 0.085),
  "& svg": { fontSize: "1.5rem" },
}));

const ReviewNarrativeBody = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.5),
  minWidth: 0,
  paddingLeft: theme.spacing(1.5),
  borderLeft: "3px solid " + alpha(theme.palette.primary.light, 0.9),
}));

const ReviewNarrativeHeading = styled(Text)(({ theme }) => ({
  margin: 0,
  fontSize: "1.0625rem",
  fontWeight: 700,
  lineHeight: 1.4,
  color: theme.palette.primary.dark,
}));

const ReviewText = styled(Text)({
  margin: 0,
  overflowWrap: "anywhere",
  whiteSpace: "pre-wrap",
});

const suitabilityLabels = {
  ready: "そのまま使える",
  minor_revision: "概ね適切・微修正",
  needs_revision: "要修正",
  needs_verification: "情報不足・要確認",
} as const;

function FollowUpReviewView({
  item, title, variant = "featured",
}: { item?: FollowUpReviewItem; title: string; variant?: "featured" | "compact" }) {
  if (!item?.review) return <ReviewText>専用評価データなし</ReviewText>;
  const review = item.review;
  const tone =
    review.suitability === "needs_revision" ? "caution" :
    review.suitability === "needs_verification" ? "neutral" : "positive";
  const badgeIcon =
    review.suitability === "ready" ? <CheckCircleOutlinedIcon /> :
    review.suitability === "minor_revision" ? <EditOutlinedIcon /> :
    review.suitability === "needs_revision" ? <LightbulbOutlinedIcon /> :
    <HelpOutlineIcon />;

  return (
    <ReviewPanel aria-label={title} $compact={variant === "compact"}>
      <ReviewHeading component="h3" variant="h3">{title}</ReviewHeading>
      <ReviewOverview>
        <ReviewTotal aria-label={review.totalScore + " / 30点"}>
          <ReviewTotalNumber>{review.totalScore}</ReviewTotalNumber>
          <ReviewTotalUnit>/ 30点</ReviewTotalUnit>
        </ReviewTotal>
        <ReviewBadge $tone={tone}>
          {badgeIcon}
          {suitabilityLabels[review.suitability]}
        </ReviewBadge>
      </ReviewOverview>
      <ReviewDivider />
      <ReviewScores aria-label="深掘り回答の採点内訳">
        <ReviewScore role="group" aria-label={"質問適合性：" + review.question_fit_score + " / 10点"}>
          <ReviewScoreIcon aria-hidden="true"><TrackChangesOutlinedIcon /></ReviewScoreIcon>
          <ReviewScoreName>質問適合性</ReviewScoreName>
          <ReviewScoreValue><strong>{review.question_fit_score}</strong> / 10点</ReviewScoreValue>
        </ReviewScore>
        <ReviewScore role="group" aria-label={"具体性・情報の充実度：" + review.detail_score + " / 10点"}>
          <ReviewScoreIcon aria-hidden="true"><LayersOutlinedIcon /></ReviewScoreIcon>
          <ReviewScoreName>具体性・情報の充実度</ReviewScoreName>
          <ReviewScoreValue><strong>{review.detail_score}</strong> / 10点</ReviewScoreValue>
        </ReviewScore>
        <ReviewScore role="group" aria-label={"一貫性・納得感：" + review.coherence_score + " / 10点"}>
          <ReviewScoreIcon aria-hidden="true"><LinkOutlinedIcon /></ReviewScoreIcon>
          <ReviewScoreName>一貫性・納得感</ReviewScoreName>
          <ReviewScoreValue><strong>{review.coherence_score}</strong> / 10点</ReviewScoreValue>
        </ReviewScore>
      </ReviewScores>
      <ReviewDivider />
      <ReviewNarrative>
        <ReviewNarrativeIcon aria-hidden="true"><ThumbUpOutlinedIcon /></ReviewNarrativeIcon>
        <ReviewNarrativeBody>
          <ReviewNarrativeHeading component="h4">良かった点</ReviewNarrativeHeading>
          <ReviewText>{review.good_point}</ReviewText>
        </ReviewNarrativeBody>
      </ReviewNarrative>
      <ReviewNarrative>
        <ReviewNarrativeIcon aria-hidden="true"><LightbulbOutlinedIcon /></ReviewNarrativeIcon>
        <ReviewNarrativeBody>
          <ReviewNarrativeHeading component="h4">改善ポイント</ReviewNarrativeHeading>
          <ReviewText>{review.improvement}</ReviewText>
        </ReviewNarrativeBody>
      </ReviewNarrative>
    </ReviewPanel>
  );
}

const JumpLink = styled("a")(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  alignSelf: "start",
  borderRadius: scaledRadius(theme, 2),
  border: "1px solid " + theme.palette.primary.main,
  color: theme.palette.primary.dark,
  ...theme.typography.button,
  padding: theme.spacing(1.25, 2.5),
  textDecoration: "none",
  "&:hover": { background: alpha(theme.palette.primary.main, 0.08) },
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.main, outlineOffset: 2 },
}));

function DetailRow({
  title,
  text,
  icon,
  tone = "standard",
  lines = 3,
  onOpen,
}: {
  title: string;
  text: string;
  icon: ReactNode;
  tone?: Tone;
  lines?: 2 | 3;
  onOpen: OpenFullText;
}) {
  return (
    <Detail $tone={tone}>
      <DetailTitle>
        <DetailIcon aria-hidden="true">{icon}</DetailIcon>
        <DetailHeading component="h2" variant="h3">{title}</DetailHeading>
      </DetailTitle>
      <DetailContent>
        <FullTextPreview title={title} text={text} icon={icon} lines={lines} onOpen={onOpen} />
      </DetailContent>
    </Detail>
  );
}

function PointRow({
  title,
  values,
  tone,
  icon,
  onOpen,
}: {
  title: string;
  values: string[];
  tone: Tone;
  icon: ReactNode;
  onOpen: OpenFullText;
}) {
  return (
    <Detail $tone={tone}>
      <DetailTitle>
        <DetailIcon aria-hidden="true">{icon}</DetailIcon>
        <DetailHeading component="h2" variant="h3">{title}</DetailHeading>
      </DetailTitle>
      <DetailContent>
        {values.length ? (
          <PointsList>
            {values.map((value, index) => (
              <li key={index}>
                <FullTextPreview title={title + " " + (index + 1)} text={value} icon={icon} onOpen={onOpen} />
              </li>
            ))}
          </PointsList>
        ) : (
          <Empty>該当する項目はありません</Empty>
        )}
      </DetailContent>
    </Detail>
  );
}

function ReportHeading() {
  return (
    <Introduction
      variant="success"
      emphasis="featured"
      heading={
        <>
          <Eyebrow variant="overline" component="p">FEEDBACK</Eyebrow>
          <Headline variant="h1" component="h1">今回のフィードバック</Headline>
        </>
      }
    >
      <Text>回答の評価と、改善に向けたアドバイスです。</Text>
    </Introduction>
  );
}

function LegacyContent({ feedback: f, onOpen }: { feedback: LegacyFeedback; onOpen: OpenFullText }) {
  return (
    <>
      <ScoreStack>
        <FeedbackScoreSummary score={f.score} maximum={100} description="今回の回答を振り返り、次の練習につなげましょう。" />
      </ScoreStack>
      <ResultList>
        <DetailRow title="質問" text={f.question.question} icon={<HelpOutlineIcon />} lines={2} onOpen={onOpen} />
        <DetailRow title="あなたの回答" text={f.answer} icon={<DescriptionOutlinedIcon />} onOpen={onOpen} />
        <DetailRow title="総評" text={f.summary} icon={<AutoAwesomeOutlinedIcon />} onOpen={onOpen} />
        <PointRow title="良かった点" values={f.strengths} tone="strength" icon={<ThumbUpOutlinedIcon />} onOpen={onOpen} />
        <PointRow title="改善ポイント" values={f.improvements} tone="improvement" icon={<LightbulbOutlinedIcon />} onOpen={onOpen} />
        {f.exampleAnswer && <DetailRow title="回答例" text={f.exampleAnswer} icon={<AutoAwesomeOutlinedIcon />} onOpen={onOpen} />}
      </ResultList>
    </>
  );
}

function CoachingContent({
  feedback: f, onOpen, canJump, followUpReviews,
}: {
  feedback: FeedbackV2; onOpen: OpenFullText; canJump: boolean;
  followUpReviews: FollowUpReviewItem[];
}) {
  return (
    <>
      <ScoreStack>
        <FeedbackScoreSummary
          score={f.totalScore}
          maximum={30}
          rank={f.rank}
          description={f.result.status === "coaching"
            ? "追加の情報を確認して、回答を育てましょう。"
            : "現時点の本人情報で回答をまとめました。"}
          breakdown={{
            conclusion: f.result.conclusion_score,
            specificity: f.result.specificity_score,
            reasoning: f.result.reasoning_score,
          }}
          answerLength={f.answerLength}
          baseScore={f.baseScore}
          lengthPenalty={f.lengthPenalty}
        />
      </ScoreStack>
      {canJump && f.result.status === "coaching" && f.coachingCount < 3 && (
        <JumpLink href="#coaching-response">深掘り質問に回答する</JumpLink>
      )}
      <ResultList>
        <DetailRow title="質問" text={f.question.question} icon={<HelpOutlineIcon />} lines={2} onOpen={onOpen} />
        <DetailRow title="初回の回答" text={f.answer} icon={<DescriptionOutlinedIcon />} onOpen={onOpen} />
        <PointRow title="良かった点" values={[f.result.good_point]} tone="strength" icon={<ThumbUpOutlinedIcon />} onOpen={onOpen} />
        <PointRow title="改善ポイント" values={[f.result.improvement]} tone="improvement" icon={<LightbulbOutlinedIcon />} onOpen={onOpen} />
        {f.result.example !== null && (
          <DetailRow title="改善回答" text={f.result.example} icon={<AutoAwesomeOutlinedIcon />} onOpen={onOpen} />
        )}
      </ResultList>
      {f.coachingHistory.length > 0 && (
        <CoachingHistory>
          <summary>深掘りの履歴（{f.coachingCount}回）</summary>
          <HistoryItems>
            {f.coachingHistory.map((history, index) => (
              <div key={index}>
                <DetailRow title={"深掘り質問 " + (index + 1)} text={history.question} icon={<HistoryOutlinedIcon />} lines={2} onOpen={onOpen} />
                <DetailRow title={"深掘り回答 " + (index + 1)} text={history.answer} icon={<DescriptionOutlinedIcon />} onOpen={onOpen} />
                <FollowUpReviewView
                  title={"深掘り " + (index + 1) + " 回目の専用採点"}
                  variant="compact"
                  item={followUpReviews.find((item) =>
                    item.roundIndex === index + 1 &&
                    item.question === history.question &&
                    item.answer === history.answer
                  )}
                />
              </div>
            ))}
          </HistoryItems>
        </CoachingHistory>
      )}
    </>
  );
}

/** 画面内の全文表示を1個のDialogへ集約し、同時表示と重複マウントを防ぐ。 */
export function FeedbackCard({
  feedback, canJumpToCoaching = false, followUpReviews = [],
}: {
  feedback: Feedback; canJumpToCoaching?: boolean;
  followUpReviews?: FollowUpReviewItem[];
}) {
  const [target, setTarget] = useState<FullTextTarget | null>(null);
  const openFullText: OpenFullText = (title, text, icon) => setTarget({ title, text, icon });
  return (
    <>
      {isFeedbackV2(feedback) && feedback.coachingCount > 0 && (
        <FollowUpReviewView
          title="今回の深掘り回答評価"
          item={followUpReviews.find((item) =>
            item.roundIndex === feedback.coachingCount &&
            item.answer === feedback.latestAnswer &&
            item.evaluationId === feedback.evaluationId
          )}
        />
      )}
      <Report>
        <ReportHeading />
        {isFeedbackV2(feedback)
          ? <CoachingContent feedback={feedback} followUpReviews={followUpReviews} onOpen={openFullText} canJump={canJumpToCoaching} />
          : <LegacyContent feedback={feedback} onOpen={openFullText} />}
      </Report>
      <FullTextDialog
        open={target !== null}
        onClose={() => setTarget(null)}
        title={target?.title ?? ""}
        text={target?.text ?? ""}
        icon={target?.icon}
      />
    </>
  );
}
