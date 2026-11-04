/** @file HomePage.tsx @description 練習への次の一歩が分かる、モバイル優先のホーム画面。 */
"use client";

import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import GridViewRoundedIcon from "@mui/icons-material/GridViewRounded";
import AccessTimeRoundedIcon from "@mui/icons-material/AccessTimeRounded";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { heroTypography, scaledRadius } from "@/theme/tokens";

const PageContent = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2.5),
  minWidth: 0,
  [theme.breakpoints.up("md")]: { gap: theme.spacing(3.5) },
}));

const HeroPanel = styled(Panel)(({ theme }) => ({
  minWidth: 0,
  margin: 0,
  padding: theme.spacing(3, 2.5, 3.5),
  borderRadius: scaledRadius(theme, 1.5),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.14),
  backgroundColor: theme.palette.background.paper,
  backgroundImage:
    "linear-gradient(135deg, " +
    theme.palette.background.paper +
    " 50%, " +
    alpha(theme.palette.primary.light, 0.15) +
    " 100%)",
  boxShadow: theme.shadows[1],
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
  color: theme.palette.primary.dark,
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
  minHeight: theme.spacing(7),
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
  [theme.breakpoints.up("sm")]: {
    width: "fit-content",
    minWidth: theme.spacing(38),
    paddingInline: theme.spacing(3),
  },
}));

const SurfaceLink = styled(Link)(({ theme }) => ({
  width: "100%",
  minWidth: 0,
  maxWidth: "none",
  padding: theme.spacing(2),
  border: "1px solid " + alpha(theme.palette.primary.main, 0.15),
  borderRadius: scaledRadius(theme, 1.25),
  color: theme.palette.text.primary,
  backgroundColor: theme.palette.background.paper,
  boxShadow: theme.shadows[1],
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
  minHeight: theme.spacing(13),
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

const CardCopy = styled("span")({
  display: "grid",
  gap: 4,
  minWidth: 0,
});

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

/** 進捗の架空表示は行わず、実際に使える画面への入口だけを提供する。 */
export const HomePage = () => (
  <PageContent>
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
      <ActionLink href="/practice/" variant="text">
        <CardIcon><GridViewRoundedIcon aria-hidden="true" /></CardIcon>
        <ActionArrow aria-hidden="true" />
        <ActionCopy>
          <CardTitle component="span" variant="h3">カテゴリから選ぶ</CardTitle>
          <CardDescription component="span" variant="body2">
            テーマ別に質問を選んで練習
          </CardDescription>
        </ActionCopy>
      </ActionLink>
      <ActionLink href="/practice/" variant="text">
        <CardIcon><AccessTimeRoundedIcon aria-hidden="true" /></CardIcon>
        <ActionArrow aria-hidden="true" />
        <ActionCopy>
          <CardTitle component="span" variant="h3">3分から始める</CardTitle>
          <CardDescription component="span" variant="body2">
            練習画面で、気軽に一問から
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
  </PageContent>
);
