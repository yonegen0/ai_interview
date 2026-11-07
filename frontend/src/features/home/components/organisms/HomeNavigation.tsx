/** @file HomeNavigation.tsx @description 練習導線・使い方ガイド・手順案内をまとめたホーム内ナビゲーション。 */
"use client";

import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import GridViewRoundedIcon from "@mui/icons-material/GridViewRounded";
import AccessTimeRoundedIcon from "@mui/icons-material/AccessTimeRounded";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { scaledRadius } from "@/theme/tokens";

const SurfaceLink = styled(Link)(({ theme }) => ({
  width: "100%",
  minWidth: 0,
  maxWidth: "none",
  padding: theme.spacing(2),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.15),
  borderRadius: scaledRadius(theme, 1.25),
  color: theme.palette.text.primary,
  backgroundColor: theme.palette.background.paper,
  boxShadow: theme.shadows[2],
  textDecoration: "none",
  transition: theme.transitions.create(["border-color", "box-shadow"]),
  "&:visited": { color: theme.palette.text.primary },
  "&:hover, &:active": {
    color: theme.palette.text.primary,
    borderColor: theme.palette.primary.main,
    boxShadow: theme.shadows[2],
    textDecoration: "none",
  },
  "&:focus-visible": {
    color: theme.palette.text.primary,
    outline: "3px solid " + theme.palette.primary.main,
    outlineOffset: 3,
    textDecoration: "none",
  },
  "@media (prefers-reduced-motion: reduce)": { transition: "none" },
}));

const GuideLink = styled(SurfaceLink)(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr) auto",
  alignItems: "center",
  columnGap: theme.spacing(1.5),
  minHeight: theme.spacing(14),
  [theme.breakpoints.up("sm")]: { padding: theme.spacing(2.5, 3) },
}));

const CardIcon = styled("span")(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
  width: theme.spacing(5.5),
  height: theme.spacing(5.5),
  borderRadius: scaledRadius(theme, 0.8),
  color: theme.palette.primary.dark,
  backgroundColor: alpha(theme.palette.primary.main, 0.09),
}));

const CardCopy = styled("span")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.5),
  minWidth: 0,
}));

const CardEyebrow = styled(Text)(({ theme }) => ({
  ...theme.typography.caption,
  color: theme.palette.primary.dark,
  fontWeight: 700,
}));

const CardTitle = styled(Text)(({ theme }) => ({
  ...theme.typography.h3,
  margin: 0,
  fontWeight: 700,
  color: theme.palette.text.primary,
}));

const CardDescription = styled(Text)(({ theme }) => ({
  ...theme.typography.body2,
  margin: 0,
  lineHeight: 1.6,
  color: theme.palette.text.secondary,
}));

const CardArrow = styled(ArrowForwardRoundedIcon)(({ theme }) => ({
  flexShrink: 0,
  color: theme.palette.primary.dark,
}));

const ActionCards = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr)",
  gap: theme.spacing(1.5),
  [theme.breakpoints.up("sm")]: {
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  },
}));

const ActionLink = styled(SurfaceLink)(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  alignContent: "start",
  alignItems: "center",
  gap: theme.spacing(1.5),
  minHeight: theme.spacing(16),
  padding: theme.spacing(2.25),
  [theme.breakpoints.up("sm")]: { minHeight: theme.spacing(20) },
}));

const ActionCopy = styled("span")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.75),
  minWidth: 0,
  gridColumn: "1 / -1",
}));

const ActionArrow = styled(CardArrow)({
  justifySelf: "end",
});

const StepsPanel = styled(Panel)(({ theme }) => ({
  minWidth: 0,
  margin: 0,
  padding: theme.spacing(2.5),
  borderRadius: scaledRadius(theme, 1.25),
  background: theme.palette.background.paper,
  boxShadow: theme.shadows[1],
  scrollMarginTop: theme.spacing(3),
}));

const StepsHeading = styled(Text)(({ theme }) => ({
  ...theme.typography.h3,
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  margin: 0,
  color: theme.palette.text.primary,
  fontWeight: 700,
}));

const StepsList = styled("ol")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: theme.spacing(0.75, 1),
  margin: theme.spacing(1.5, 0, 0),
  padding: 0,
  listStyle: "none",
}));

const StepItem = styled("li")(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: theme.spacing(1),
  minWidth: 0,
  color: theme.palette.text.secondary,
  ...theme.typography.body2,
  "&:not(:last-child)::after": {
    content: '"→"',
    color: theme.palette.primary.main,
    fontWeight: 700,
    marginInlineStart: theme.spacing(0.5),
  },
}));

/** リンク先は実装済みの練習画面とホーム内ガイドに限定する。 */
export function HomeNavigation() {
  return (
    <>
    <GuideLink href="#home-how-it-works" variant="text">
      <CardIcon><MenuBookOutlinedIcon aria-hidden="true" /></CardIcon>
      <CardCopy>
        <CardEyebrow component="span" variant="caption">はじめての方へ</CardEyebrow>
        <CardTitle component="span" variant="h3">まずは使い方ガイド</CardTitle>
        <CardDescription component="span" variant="body2">
          練習の流れをチェック
        </CardDescription>
      </CardCopy>
      <CardArrow aria-hidden="true" />
    </GuideLink>

    <ActionCards aria-label="練習の始め方">
      <ActionLink href="/practice/category/" variant="text">
        <CardIcon><GridViewRoundedIcon aria-hidden="true" /></CardIcon>
        <ActionArrow aria-hidden="true" />
        <ActionCopy>
          <CardTitle component="span" variant="h3">カテゴリから選ぶ</CardTitle>
          <CardDescription component="span" variant="body2">
            テーマ別に質問を選んで練習
          </CardDescription>
        </ActionCopy>
      </ActionLink>
      <ActionLink href="/practice/quick/" variant="text">
        <CardIcon><AccessTimeRoundedIcon aria-hidden="true" /></CardIcon>
        <ActionArrow aria-hidden="true" />
        <ActionCopy>
          <CardTitle component="span" variant="h3">3分から始める</CardTitle>
          <CardDescription component="span" variant="body2">
            未完了の質問から、自動で一問を開始
          </CardDescription>
        </ActionCopy>
      </ActionLink>
    </ActionCards>

    <StepsPanel id="home-how-it-works" aria-labelledby="home-steps-title">
      <StepsHeading id="home-steps-title" variant="h3" component="h2">
        <CheckCircleOutlineRoundedIcon color="primary" aria-hidden="true" />
        練習を続ける3つのステップ
      </StepsHeading>
      <StepsList>
        <StepItem>質問を選ぶ</StepItem>
        <StepItem>自分の言葉で答える</StepItem>
        <StepItem>フィードバックで振り返る</StepItem>
      </StepsList>
    </StepsPanel>
    </>
  );
}
