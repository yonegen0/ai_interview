/** @file GuideBasic.tsx @description Mock環境の実画面画像で四つの面接練習ステップを案内する。 */
"use client";

import { useRef, useState, type TouchEvent } from "react";
import { Button } from "@mui/material";
import Image from "next/image";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import {
  GuideAction, GuideActions, GuideBack, GuideEyebrow, GuideHeading,
  GuideLead, GuidePage, GuideSubheading, GuideSurface,
} from "./GuideUI";

const StepTitle = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.5),
}));
const ScreenshotFrame = styled("figure")(({ theme }) => ({
  display: "grid", justifyItems: "center", gap: theme.spacing(1.5),
  margin: 0, padding: theme.spacing(1.5), minWidth: 0,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.25),
  borderRadius: theme.shape.borderRadius,
  backgroundColor: alpha(theme.palette.primary.main, 0.045),
}));
const ScreenshotImage = styled(Image)(({ theme }) => ({
  display: "block", width: "100%", maxWidth: 390, height: "auto",
  borderRadius: theme.shape.borderRadius, boxShadow: theme.shadows[1],
}));
const ScreenshotNote = styled("figcaption")(({ theme }) => ({
  ...theme.typography.caption, color: theme.palette.text.secondary,
  textAlign: "center", margin: 0, lineHeight: 1.6,
}));
const StepNav = styled("div")(({ theme }) => ({
  display: "flex", justifyContent: "space-between",
  alignItems: "center", gap: theme.spacing(1), flexWrap: "wrap",
}));
const Indicators = styled("div")(({ theme }) => ({
  display: "flex", gap: theme.spacing(1),
}));
const Indicator = styled("button", {
  shouldForwardProp: (prop) => prop !== "$current",
})<{ $current: boolean }>(({ theme, $current }) => ({
  width: 42, height: 42, borderRadius: "50%",
  cursor: "pointer", fontWeight: 800, border: "2px solid " + theme.palette.primary.main,
  backgroundColor: $current ? theme.palette.primary.main : theme.palette.background.paper,
  color: $current ? theme.palette.primary.contrastText : theme.palette.primary.dark,
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.dark, outlineOffset: 2 },
}));
const SwipeArea = styled("div")({
  display: "grid", gap: 16, minWidth: 0, touchAction: "pan-y",
});
const captures = [
  { src: "/guide/mock-start.jpg", alt: "Mockのホーム画面。カテゴリから選ぶ・3分から始めるの練習開始リンク" },
  { src: "/guide/mock-answer.jpg", alt: "Mockの回答作成画面。面接質問と回答の入力欄" },
  { src: "/guide/mock-feedback.jpg", alt: "Mockの評価画面。回答後のAIフィードバックと総合評価" },
  { src: "/guide/mock-progress.jpg", alt: "Mockのホーム画面。15問の進捗カードと残り質問数" },
] as const;
function StepIllustration({ step }: { step: number }) {
  const capture = captures[step] ?? captures[0];
  return (
    <ScreenshotFrame>
      <ScreenshotImage
        src={capture.src} alt={capture.alt} width={390} height={844} unoptimized
      />
      <ScreenshotNote>
        ※ Mock環境で実際に操作して撮影した画面です。回答・評価・進捗は架空のデータです。
      </ScreenshotNote>
    </ScreenshotFrame>
  );
}
const steps = [
  { title: "まずは練習を始めよう", description: "質問を自分で選ぶことも、未完了の質問から自動で1問始めることもできます。" },
  { title: "自分の言葉で回答しよう", description: "質問に答えてみましょう。文章に迷ったらAIアシストも利用できます。" },
  { title: "AIのアドバイスを確認しよう", description: "回答を送信すると、良かった点や改善ポイントをAIが教えてくれます。" },
  { title: "振り返って、次の練習へ", description: "AIの評価を確認したら、同じ質問に再挑戦したり、ホームに戻って次の練習を始めたりできます。" },
] as const;
export function GuideBasic() {
  const [step, setStep] = useState(0);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const handleStart = (event: TouchEvent<HTMLDivElement>) => {
    const first = event.changedTouches[0];
    if (first) touch.current = { x: first.clientX, y: first.clientY };
  };
  const handleEnd = (event: TouchEvent<HTMLDivElement>) => {
    const first = event.changedTouches[0];
    const start = touch.current;
    touch.current = null;
    if (!first || !start) return;
    const dx = first.clientX - start.x;
    const dy = first.clientY - start.y;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    setStep((current) => Math.max(0, Math.min(3, current + (dx < 0 ? 1 : -1))));
  };
  return (
    <GuidePage>
      <GuideBack href="/guide/">← ガイドトップへ戻る</GuideBack>
      <GuideHeading>基本ガイド</GuideHeading>
      <GuideLead>4つのステップで、面接練習の流れを確認しましょう。途中からでも練習を始められます。</GuideLead>
      <GuideSurface aria-label="基本ガイドのスライド">
        <StepNav>
          <GuideEyebrow>STEP {step + 1}　·　{step + 1} / 4</GuideEyebrow>
          <Indicators aria-label="ステップを選択">
            {steps.map((item, i) => (
              <Indicator key={item.title} type="button" $current={step === i}
                aria-label={`STEP ${i + 1}を表示`} aria-current={step === i ? "step" : undefined}
                onClick={() => setStep(i)}>{i + 1}</Indicator>
            ))}
          </Indicators>
        </StepNav>
        <SwipeArea onTouchStart={handleStart} onTouchEnd={handleEnd}>
          <StepTitle aria-live="polite">
            <GuideSubheading>{steps[step].title}</GuideSubheading>
            <GuideLead>{steps[step].description}</GuideLead>
          </StepTitle>
          <StepIllustration step={step} />
        </SwipeArea>
        {step === 0 && (
          <GuideActions aria-label="練習を選ぶ">
            <Link href="/practice/category/">カテゴリから選ぶ</Link>
            <Link href="/practice/quick/">3分から始める</Link>
          </GuideActions>
        )}
        {step === 1 && <Link href="/guide/features/#assist">6種類の回答アシストを見る</Link>}
        {step === 3 && (
          <>
            <GuideLead>練習モードによって評価後の操作は異なります。Quick Startでは「次の質問へ」が必ず表示されるわけではありません。</GuideLead>
            <GuideActions>
              <GuideAction href="/practice/quick/">面接練習を始める <ArrowForwardRoundedIcon aria-hidden="true" /></GuideAction>
              <Link href="/guide/features/">機能別ガイドを見る</Link>
              <Link href="/">ホームへ戻る</Link>
            </GuideActions>
          </>
        )}
        <StepNav>
          <Button variant="outlined" startIcon={<ArrowBackRoundedIcon />}
            disabled={step === 0} onClick={() => setStep((i) => Math.max(0, i - 1))}>
            戻る
          </Button>
          {step < 3 ? (
            <Button variant="contained" endIcon={<ArrowForwardRoundedIcon />}
              onClick={() => setStep((i) => Math.min(3, i + 1))}>次へ</Button>
          ) : <Link href="/guide/features/">機能別ガイドへ</Link>}
        </StepNav>
      </GuideSurface>
      <GuideActions><GuideAction href="/practice/quick/">練習に進む</GuideAction><Link href="/guide/">ガイドトップへ戻る</Link></GuideActions>
    </GuidePage>
  );
}
