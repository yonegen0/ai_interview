/** @file GuideBasic.tsx @description 四つの操作ステップを現行UI準拠のサンプル画面で案内する。 */
"use client";

import { useRef, useState, type TouchEvent } from "react";
import { Button, LinearProgress } from "@mui/material";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import {
  GuideAction, GuideActions, GuideBack, GuideEyebrow, GuideHeading,
  GuideLead, GuidePage, GuideSubheading, GuideSurface,
} from "./GuideUI";

const Sample = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2),
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(2.5), minWidth: 0,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.25),
  background: `linear-gradient(135deg, ${alpha(theme.palette.primary.light, 0.13)}, ${theme.palette.background.default})`,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1.5) },
}));
const SampleCard = styled("div")(({ theme }) => ({
  minWidth: 0, display: "grid", gap: theme.spacing(1),
  padding: theme.spacing(2), borderRadius: theme.shape.borderRadius,
  boxShadow: theme.shadows[1], background: theme.palette.background.paper,
}));
const Highlight = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.5), minWidth: 0,
  padding: theme.spacing(1.5),
  border: "2px solid " + theme.palette.primary.main,
  borderRadius: theme.shape.borderRadius, background: alpha(theme.palette.primary.main, 0.055),
}));
const SampleLabel = styled("strong")(({ theme }) => ({
  ...theme.typography.body1, color: theme.palette.text.primary,
}));
const SampleText = styled("span")(({ theme }) => ({
  ...theme.typography.body2, color: theme.palette.text.secondary, lineHeight: 1.65,
}));
const StepTitle = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.5),
}));
const SampleNote = styled("p")(({ theme }) => ({
  ...theme.typography.caption, color: theme.palette.text.secondary, margin: 0,
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
const SampleTwo = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1.5),
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
const SampleButton = styled("span")(({ theme }) => ({
  display: "block", textAlign: "center", padding: theme.spacing(1.25),
  borderRadius: theme.shape.borderRadius, fontWeight: 700,
  backgroundColor: theme.palette.primary.main, color: theme.palette.primary.contrastText,
}));
function StepIllustration({ step }: { step: number }) {
  return (
    <>
      <Sample aria-label={["練習開始画面の操作例", "回答作成画面の操作例", "評価画面の表示例", "進捗画面の表示例"][step]}>
        {step === 0 ? (
          <SampleTwo>
            <Highlight>
              <SampleLabel>① カテゴリから選ぶ</SampleLabel>
              <SampleText>テーマ別に質問を選んで練習</SampleText>
              <SampleNote>テーマを選びたい方</SampleNote>
            </Highlight>
            <Highlight>
              <SampleLabel>② 3分から始める</SampleLabel>
              <SampleText>未完了の質問から、自動で一問を開始</SampleText>
              <SampleNote>迷ったらこちら</SampleNote>
            </Highlight>
          </SampleTwo>
        ) : step === 1 ? (
          <>
            <SampleCard>
              <SampleNote>一問一答 · QUESTION 01</SampleNote>
              <SampleLabel>質問に回答してみましょう</SampleLabel>
            </SampleCard>
            <SampleCard>
              <SampleLabel>回答作成</SampleLabel>
              <Highlight>
                <SampleLabel>① <AutoAwesomeOutlinedIcon fontSize="small" aria-hidden="true" /> STARアシスト</SampleLabel>
                <SampleText>経験を4つのステップで整理し、A/B/Cの3案を生成します。</SampleText>
              </Highlight>
              <Highlight>
                <SampleLabel>② あなたの回答</SampleLabel>
                <SampleText>ここに自分の回答を入力します</SampleText>
              </Highlight>
              <SampleButton>回答を送信</SampleButton>
            </SampleCard>
          </>
        ) : step === 2 ? (
          <SampleCard>
            <SampleNote>AI評価のサンプル（Coaching V2の表示イメージ）</SampleNote>
            <Highlight><SampleLabel>① 総合評価　24 / 30</SampleLabel><SampleText>回答の伝わりやすさを確認</SampleText></Highlight>
            <Highlight><SampleLabel>② 良かった点</SampleLabel><SampleText>質問に沿って経験を説明できています。</SampleText></Highlight>
            <Highlight><SampleLabel>③ 改善ポイント</SampleLabel><SampleText>判断した理由を加えると伝わりやすくなります。</SampleText></Highlight>
          </SampleCard>
        ) : (
          <SampleCard>
            <SampleLabel><CheckCircleOutlineRoundedIcon fontSize="small" aria-hidden="true" /> 面接練習の進捗</SampleLabel>
            <SampleLabel>3 / 15 問完了</SampleLabel>
            <SampleText>あと12問</SampleText>
            <LinearProgress variant="determinate" value={20} aria-label="進捗の表示例" />
            <SampleText>いいスタートです。その調子！</SampleText>
            <SampleButton>練習を続ける</SampleButton>
          </SampleCard>
        )}
      </Sample>
      <SampleNote>※ 実画面の構成に合わせた説明用再現です。表示内容・数値はサンプルです。</SampleNote>
    </>
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
