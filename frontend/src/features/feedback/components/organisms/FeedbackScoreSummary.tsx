/**
 * @file FeedbackScoreSummary.tsx
 * @description APIが返した評価点を円形ゲージ・項目カードで可視化する。
 */
"use client";

import type { ReactNode } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import { alpha, styled } from "@mui/material/styles";
import { scaledRadius, scoreTypography } from "@/theme/tokens";
import { Text } from "@/components/atoms/Text";
import type { FeedbackV2 } from "@/lib/api/schemas";

type Breakdown = {
  conclusion: number;
  specificity: number;
  reasoning: number;
};

export type FeedbackScoreSummaryProps = {
  score: number;
  maximum: 30 | 100;
  description: string;
  rank?: FeedbackV2["rank"];
  breakdown?: Breakdown;
  answerLength?: number;
  baseScore?: number;
  lengthPenalty?: number;
};

const Summary = styled("section")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 200px) minmax(0, 1fr)",
  gap: theme.spacing(3),
  alignItems: "center",
  [theme.breakpoints.down("sm")]: {
    gridTemplateColumns: "minmax(0, 1fr)",
    justifyItems: "center",
    textAlign: "center",
  },
}));

const Gauge = styled("div")({
  position: "relative",
  width: 176,
  height: 176,
  display: "grid",
  placeItems: "center",
  flexShrink: 0,
});

const GaugeTrack = styled(CircularProgress)(({ theme }) => ({
  position: "absolute",
  inset: 0,
  color: alpha(theme.palette.primary.main, 0.12),
}));

const GaugeProgress = styled(CircularProgress)(({ theme }) => ({
  position: "absolute",
  inset: 0,
  color: theme.palette.primary.main,
  transform: "rotate(-90deg)",
  "& .MuiCircularProgress-circle": { strokeLinecap: "round" },
}));

const GaugeContent = styled("div")({
  position: "relative",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 4,
  fontVariantNumeric: "tabular-nums",
});

const Score = styled("strong")(({ theme }) => ({
  ...scoreTypography(theme),
  color: theme.palette.primary.dark,
}));

const Scale = styled("span")(({ theme }) => ({
  ...theme.typography.body2,
  color: theme.palette.text.secondary,
  fontWeight: 700,
}));

const Rank = styled("span")(({ theme }) => ({
  padding: theme.spacing(0.25, 1.5),
  borderRadius: scaledRadius(theme, 2),
  background: alpha(theme.palette.secondary.main, 0.25),
  color: theme.palette.text.primary,
  fontWeight: 700,
}));

const SummaryCopy = styled("div")(({ theme }) => ({
  minWidth: 0,
  borderLeft: "1px solid " + theme.palette.divider,
  paddingLeft: theme.spacing(3),
  [theme.breakpoints.down("sm")]: {
    borderLeft: "none",
    paddingLeft: 0,
  },
}));

const Description = styled(Text)(({ theme }) => ({
  margin: theme.spacing(1, 0, 0),
  lineHeight: 1.75,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
}));

const CriteriaGrid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: theme.spacing(1.5),
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));

const CriterionCard = styled("div")(({ theme }) => ({
  minWidth: 0,
  borderRadius: scaledRadius(theme, 1),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.12),
  backgroundColor: alpha(theme.palette.primary.main, 0.04),
  padding: theme.spacing(2),
}));

const CriterionTop = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(1),
  marginBottom: theme.spacing(1),
}));

const CriterionName = styled("span")(({ theme }) => ({
  ...theme.typography.body1,
  fontWeight: 700,
  color: theme.palette.text.primary,
}));

const CriterionValue = styled("strong")(({ theme }) => ({
  ...theme.typography.h2,
  color: theme.palette.primary.dark,
  fontVariantNumeric: "tabular-nums",
  whiteSpace: "nowrap",
}));

const Meter = styled(LinearProgress)(({ theme }) => ({
  height: 9,
  borderRadius: scaledRadius(theme, 2),
  backgroundColor: alpha(theme.palette.primary.main, 0.12),
  "& .MuiLinearProgress-bar": {
    backgroundColor: theme.palette.primary.main,
    borderRadius: scaledRadius(theme, 2),
  },
}));

const Stats = styled("dl")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: 0,
  margin: 0,
  padding: theme.spacing(1.5),
  backgroundColor: alpha(theme.palette.primary.main, 0.04),
  borderRadius: scaledRadius(theme, 1),
  [theme.breakpoints.down("sm")]: {
    gridTemplateColumns: "minmax(0, 1fr)",
    gap: theme.spacing(1),
  },
}));

const Stat = styled("div")(({ theme }) => ({
  minWidth: 0,
  textAlign: "center",
  padding: theme.spacing(1, 1.5),
  "& + &": { borderLeft: "1px solid " + theme.palette.divider },
  [theme.breakpoints.down("sm")]: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    textAlign: "left",
    "& + &": { borderLeft: 0, borderTop: "1px solid " + theme.palette.divider },
  },
}));

const StatName = styled("dt")(({ theme }) => ({
  ...theme.typography.body2,
  color: theme.palette.text.secondary,
}));

const StatValue = styled("dd")(({ theme }) => ({
  margin: 0,
  ...theme.typography.h3,
  fontWeight: 700,
  fontVariantNumeric: "tabular-nums",
  color: theme.palette.text.primary,
}));

function Criterion({ name, value }: { name: string; value: number }) {
  return (
    <CriterionCard>
      <CriterionTop>
        <CriterionName>{name}</CriterionName>
        <CriterionValue>{value} / 10</CriterionValue>
      </CriterionTop>
      <Meter variant="determinate" value={value * 10} aria-label={name + "の評価"} />
    </CriterionCard>
  );
}

/** 未提供のV1指標を補完せず、Coaching V2の内訳のみ追加表示する。 */
export function FeedbackScoreSummary({
  score,
  maximum,
  description,
  rank,
  breakdown,
  answerLength,
  baseScore,
  lengthPenalty,
}: FeedbackScoreSummaryProps) {
  return (
    <>
      <Summary aria-label="総合スコア">
        <Gauge>
          <GaugeTrack variant="determinate" value={100} size={176} thickness={5} aria-hidden="true" />
          <GaugeProgress variant="determinate" value={(score / maximum) * 100} size={176} thickness={5} aria-label={"総合評価 " + score + " / " + maximum} />
          <GaugeContent>
            <Score>{score}</Score>
            <Scale>/ {maximum}{rank ? " · " + rank : ""}</Scale>
            {rank && <Rank>{rank} 評価</Rank>}
          </GaugeContent>
        </Gauge>
        <SummaryCopy>
          <Text variant="h2" component="h2">総合評価</Text>
          <Description>{description}</Description>
        </SummaryCopy>
      </Summary>
      {breakdown && (
        <CriteriaGrid aria-label="項目別評価">
          <Criterion name="結論" value={breakdown.conclusion} />
          <Criterion name="具体性" value={breakdown.specificity} />
          <Criterion name="根拠" value={breakdown.reasoning} />
        </CriteriaGrid>
      )}
      {answerLength !== undefined && baseScore !== undefined && lengthPenalty !== undefined && (
        <Stats aria-label="採点内訳">
          <Stat><StatName>初回回答</StatName><StatValue>{answerLength} 文字</StatValue></Stat>
          <Stat><StatName>合計点</StatName><StatValue>{baseScore} 点</StatValue></Stat>
          <Stat><StatName>文字数減点</StatName><StatValue>{lengthPenalty} 点</StatValue></Stat>
        </Stats>
      )}
    </>
  );
}
