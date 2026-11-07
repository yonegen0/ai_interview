/** @file GuideTop.tsx @description 初心者向けと機能別ガイドへの入り口。 */
"use client";

import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import AutoStoriesOutlinedIcon from "@mui/icons-material/AutoStoriesOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import { alpha, styled } from "@mui/material/styles";
import {
  GuideAction, GuideBack, GuideCards, GuideEyebrow, GuideHeading,
  GuideLead, GuidePage, GuideSubheading, GuideSurface,
} from "./GuideUI";

const Card = styled(GuideSurface)(({ theme }) => ({
  alignContent: "space-between", gap: theme.spacing(2),
  minHeight: 300,
  "&:first-of-type": {
    borderColor: alpha(theme.palette.primary.main, 0.5),
    background: `linear-gradient(145deg, ${alpha(theme.palette.primary.light, 0.18)}, ${theme.palette.background.paper} 65%)`,
  },
  [theme.breakpoints.down("sm")]: { minHeight: 230 },
}));
const Icon = styled("div")(({ theme }) => ({
  display: "grid", placeItems: "center", width: 56, height: 56,
  borderRadius: theme.shape.borderRadius, backgroundColor: alpha(theme.palette.primary.main, 0.12),
  color: theme.palette.primary.dark,
}));
const CardCopy = styled("div")(({ theme }) => ({
  display: "grid", alignContent: "start", gap: theme.spacing(1),
}));
const CardDescription = styled("p")(({ theme }) => ({
  ...theme.typography.body2, color: theme.palette.text.secondary, lineHeight: 1.7, margin: 0,
}));
export function GuideTop() {
  return (
    <GuidePage>
      <GuideBack href="/">← ホームへ戻る</GuideBack>
      <GuideHeading>使い方ガイド</GuideHeading>
      <GuideLead>面接練習の始め方から便利な機能まで、分かりやすくご案内します。</GuideLead>
      <GuideCards>
        <Card aria-labelledby="guide-basic-title">
          <CardCopy>
            <Icon><AutoStoriesOutlinedIcon fontSize="large" aria-hidden="true" /></Icon>
            <GuideEyebrow>はじめての方へ</GuideEyebrow>
            <GuideSubheading id="guide-basic-title">基本ガイド</GuideSubheading>
            <CardDescription>4つのステップで練習の流れを確認</CardDescription>
          </CardCopy>
          <GuideAction href="/guide/basic/">基本ガイドを見る <ArrowForwardRoundedIcon aria-hidden="true" /></GuideAction>
        </Card>
        <Card aria-labelledby="guide-features-title">
          <CardCopy>
            <Icon><TuneOutlinedIcon fontSize="large" aria-hidden="true" /></Icon>
            <GuideEyebrow>もっと便利に使いたい方へ</GuideEyebrow>
            <GuideSubheading id="guide-features-title">機能別ガイド</GuideSubheading>
            <CardDescription>知りたい機能の使い方を詳しく確認</CardDescription>
          </CardCopy>
          <GuideAction href="/guide/features/">機能別ガイドを見る <ArrowForwardRoundedIcon aria-hidden="true" /></GuideAction>
        </Card>
      </GuideCards>
    </GuidePage>
  );
}
