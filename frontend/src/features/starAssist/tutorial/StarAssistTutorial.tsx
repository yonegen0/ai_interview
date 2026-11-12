/** @file StarAssistTutorial.tsx @description 単一Dialog内に本番STARアシストの表示部品を使った固定12ステップ体験を描画する。 */
"use client";

import { useEffect, useRef } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import {
  Dialog as MuiDialog, DialogActions, DialogContent, LinearProgress, useMediaQuery,
} from "@mui/material";
import { alpha, styled, useTheme } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Select } from "@/components/atoms/Select";
import { Text } from "@/components/atoms/Text";
import { countStarNotes, targetCategories, STAR_OUTPUT_LIMIT, countStarText } from "@/lib/api/schemas/star";
import { assistModes, starSteps } from "../model/steps";
import { StarAssistStepper } from "../components/molecules/StarAssistStepper";
import { StarAssistTips } from "../components/molecules/StarAssistTips";
import {
  StarAssistHeader, StarAssistColumns, StarAssistStepCard,
  StarAssistSettings, StarAssistSettingFields, StarAssistSettingActions,
} from "../components/molecules/StarAssistPresentation";
import {
  CandidateTabs, CandidateTab, AnswerCard, CardHeading, AnswerText,
  AssistResultHeading, AssistCandidateActions, AssistCandidateNavigation,
  STAR_RESULT_DESCRIPTION,
} from "../components/molecules/AssistResultPresentation";
import EmojiEventsOutlinedIcon from "@mui/icons-material/EmojiEventsOutlined";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_COMPANY, TUTORIAL_CATEGORY,
  TUTORIAL_EDITED_A, TUTORIAL_EDIT_BEFORE, TUTORIAL_EDIT_AFTER,
  TUTORIAL_INDUSTRY, TUTORIAL_QUESTION,
} from "./tutorialData";
import { TUTORIAL_STEP_COUNT, useStarAssistTutorial } from "./useStarAssistTutorial";

const TutorialDialog = styled(MuiDialog)(({ theme }) => ({
  "& .MuiDialog-paper": {
    height: "min(760px, calc(100dvh - 32px))",
    maxHeight: "calc(100dvh - 32px)",
    margin: theme.spacing(2),
    border: "1px solid " + alpha(theme.palette.primary.main, 0.2),
    borderRadius: 24,
    boxShadow: theme.shadows[8],
    overflow: "hidden",
    [theme.breakpoints.down("sm")]: {
      height: "100dvh", maxHeight: "100dvh", width: "100%", margin: 0, borderRadius: 0,
    },
  },
}));
const Header = styled("div")(({ theme }) => ({
  borderBottom: "1px solid " + theme.palette.divider,
  padding: theme.spacing(2, 2.5),
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1.25, 2) },
}));
const Content = styled(DialogContent)(({ theme }) => ({
  display: "grid", alignContent: "start", gap: theme.spacing(2),
  flex: 1, minHeight: 0,
  overflowY: "auto", overflowX: "hidden", overscrollBehavior: "contain",
  padding: theme.spacing(2.5),
  "&.MuiDialogContent-root": { paddingTop: theme.spacing(2.5) },
  [theme.breakpoints.down("sm")]: {
    paddingInline: theme.spacing(2),
    "&.MuiDialogContent-root": { paddingTop: theme.spacing(2) },
  },
}));
const Footer = styled(DialogActions)(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.75),
  borderTop: "1px solid " + theme.palette.divider,
  padding: theme.spacing(1, 2.5),
  paddingBottom: "max(12px, env(safe-area-inset-bottom))",
  backgroundColor: theme.palette.background.paper,
  [theme.breakpoints.down("sm")]: { paddingInline: theme.spacing(2) },
}));
const FooterButtons = styled("div")(({ theme }) => ({
  display: "flex", justifyContent: "flex-end",
  gap: theme.spacing(1), flexWrap: "wrap",
  "& .MuiButton-root": {
    minHeight: 44, minWidth: 0, flex: "1 1 auto", paddingInline: theme.spacing(1.5),
  },
}));
const FooterHeading = styled("div")(({ theme }) => ({
  display: "flex", justifyContent: "space-between", alignItems: "center",
  gap: theme.spacing(1),
}));
const Question = styled("section")(({ theme }) => ({
  display: "grid", gap: theme.spacing(0.5), padding: theme.spacing(1.25, 1.5),
  background: alpha(theme.palette.primary.light, 0.10),
  borderRadius: theme.shape.borderRadius, overflowWrap: "anywhere",
}));
const ViewCard = styled("section")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1), minWidth: 0,
  padding: theme.spacing(2),
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
  backgroundColor: theme.palette.background.paper,
  overflowWrap: "anywhere",
}));
const ReadingText = styled("p")(({ theme }) => ({
  margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
  lineHeight: 1.9, ...theme.typography.body1,
}));
const StepDescription = styled("div")(({ theme }) => ({
  padding: theme.spacing(0.75, 0), color: theme.palette.text.primary,
  overflowWrap: "anywhere",
}));

const EditComparison = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1),
  minWidth: 0,
}));
const ComparisonPanel = styled("div", {
  shouldForwardProp: (prop) => prop !== "$after",
})<{ $after?: boolean }>(({ theme, $after }) => ({
  display: "grid",
  gap: theme.spacing(0.75),
  padding: theme.spacing(1.5),
  minWidth: 0,
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + ($after ? alpha(theme.palette.primary.main, 0.5) : theme.palette.divider),
  backgroundColor: $after
    ? alpha(theme.palette.primary.light, 0.12) : theme.palette.grey[100],
  overflowWrap: "anywhere",
}));


const candidateLabels = {
  A: "結論重視", B: "行動重視", C: "会話重視",
} as const;

export function StarAssistTutorial({ onClose }: { onClose: () => void }) {
  const { step, next, back, reset, close, view } = useStarAssistTutorial(onClose);
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const target = content.querySelector<HTMLElement>('[data-tutorial-target="true"]');
    // scrollIntoView could also move the background page; only scroll the dialog content.
    if (target) {
      const offset = target.getBoundingClientRect().top - content.getBoundingClientRect().top;
      content.scrollTop += offset - 12;
    } else content.scrollTop = 0;
  }, [step]);

  const inputStep = step <= 2 ? 0 : step === 3 ? 1 : step === 4 ? 2 : 3;
  const current = starSteps[inputStep];
  const candidate = view.selectedCandidate
    ? TUTORIAL_CANDIDATES.find((item) => item.id === view.selectedCandidate)
    : undefined;
  const answer = view.edited && view.selectedCandidate === "A"
    ? TUTORIAL_EDITED_A : candidate?.text ?? "";

  return (
    <TutorialDialog open onClose={close} fullWidth maxWidth="md" fullScreen={fullScreen}
      aria-label="エピソード作成アシストの使い方を体験"
      aria-describedby="star-tutorial-description">
      <Header>
        {view.candidatesVisible ? (
          <AssistResultHeading title="生成した3案の回答" description={STAR_RESULT_DESCRIPTION}
            onClose={close} titleId="star-tutorial-result-title" />
        ) : (
          <StarAssistHeader mode="star" onClose={close}
            titleId="star-tutorial-title" closeLabel="チュートリアルを閉じる"
            extra={<Text variant="caption" color="text.secondary">
              体験モード・入力不要・保存されません
            </Text>} />
        )}
      </Header>
      <Content ref={contentRef}>
        <Question aria-label="体験用の質問">
          <Text component="h3" variant="subtitle2">体験用の質問</Text>
          <Text variant="body2">{TUTORIAL_QUESTION}</Text>
          <Text variant="caption" color="text.secondary">
            実際の回答・下書きには保存されません。
          </Text>
        </Question>
        {!view.completed && (
          <StepDescription id="star-tutorial-description" role="status"
            aria-live="polite" aria-atomic="true">
            <Text variant="body2">{view.description}</Text>
          </StepDescription>
        )}
        {view.completed ? (
          <>
            <Text id="star-tutorial-description" component="h3" variant="h2"
              data-tutorial-target="true">チュートリアル完了！</Text>
            <Text>
              3つの回答案を比較し、文章を修正して、回答欄に反映するところまで体験できました。
            </Text>
            <ViewCard aria-label="体験用回答欄">
              <Text component="h3" variant="h3">あなたの回答（体験用）</Text>
              <ReadingText>{view.answer}</ReadingText>
            </ViewCard>
            <Text variant="body2" color="text.secondary">
              今回は体験用のため、実際の回答や練習履歴には保存されていません。
            </Text>
          </>
        ) : !view.candidatesVisible ? (
          <>
            <Text role="status" aria-live="polite" variant="body2" color="text.secondary">
              入力文字数：{countStarNotes(view.notes)} / 600文字
            </Text>
            <StarAssistStepper activeStep={inputStep} steps={starSteps}
              label={assistModes.star.label} />
            <StarAssistColumns>
              <StarAssistStepCard step={current} count={countStarText(view.notes[current.key])}
                tutorialTarget={step !== 6}>
                <Input label={current.key === "A" ? "A 本人の行動" : current.key + " " + current.label}
                  value={view.notes[current.key]}
                  placeholder={current.placeholder} multiline minRows={5}
                  helperText="任意。実際の経験や考えだけを箇条書きで入力してください。"
                  slotProps={{ input: { readOnly: true }, htmlInput: { tabIndex: -1 } }} />
              </StarAssistStepCard>
              <StarAssistTips step={inputStep} steps={starSteps} />
            </StarAssistColumns>
            {step === 6 && (
              <StarAssistSettings aria-label="体験用応募先設定"
                data-tutorial-target="true">
                <Text variant="h3" component="h3">応募先の設定</Text>
                <Select label="応募先カテゴリ" value={TUTORIAL_CATEGORY} fullWidth
                  disabled onChange={() => {}}
                  options={[
                    { value: "", label: "選択してください" },
                    ...Object.entries(targetCategories).map(([value, label]) => ({ value, label })),
                  ]} />
                <StarAssistSettingFields>
                  <Input label="志望業界（任意）" value={TUTORIAL_INDUSTRY}
                    slotProps={{ input: { readOnly: true }, htmlInput: { tabIndex: -1 } }} />
                  <Input label="応募先企業名（任意）" value={TUTORIAL_COMPANY}
                    slotProps={{ input: { readOnly: true }, htmlInput: { tabIndex: -1 } }} />
                </StarAssistSettingFields>
                <StarAssistSettingActions>
                  <Button type="button" size="small" disabled>このカテゴリを14日保存</Button>
                  <Button type="button" size="small" disabled>業界・企業名を14日保存</Button>
                </StarAssistSettingActions>
                <Text variant="caption" color="text.secondary">
                  設定は体験用の表示です。実際には保存されません。
                </Text>
              </StarAssistSettings>
            )}
          </>
        ) : (
          <>
            <Text variant="caption" color="text.secondary">体験モード・保存されません</Text>
            <CandidateTabs value={candidate?.id ?? "A"}
              aria-label="体験用回答案の表示" variant="fullWidth">
              {TUTORIAL_CANDIDATES.map((item) => (
                <CandidateTab key={item.id} value={item.id} disabled
                  label={item.id + " " + candidateLabels[item.id]} />
              ))}
            </CandidateTabs>
            <Text role="status" variant="body2" color="text.secondary">
              表示中：{candidate?.id}案（{candidate ? candidateLabels[candidate.id] : ""}）
              ・切り替えは「次へ」で体験します。
            </Text>
            <AnswerCard aria-label="生成した回答アシスト"
              data-tutorial-target={view.edited ? undefined : "true"}>
              <CardHeading>
                <EmojiEventsOutlinedIcon color="warning" aria-hidden="true" />
                <Text component="h3" variant="h3">
                  {candidate ? "案" + candidate.id + "の回答（" + candidateLabels[candidate.id] + "）" : ""}
                </Text>
              </CardHeading>
              {view.editing && !view.edited && (
                <Text variant="body2" color="text.secondary">
                  修正する箇所は最後の一文です。「次へ」で話しやすい表現に整えます。
                </Text>
              )}
              {view.edited && (
                <EditComparison aria-label="修正前後の比較" data-tutorial-target="true">
                  <ComparisonPanel aria-label="修正前">
                    <Text variant="subtitle2" color="text.secondary">修正前</Text>
                    <AnswerText>{TUTORIAL_EDIT_BEFORE}</AnswerText>
                  </ComparisonPanel>
                  <ArrowDownwardIcon fontSize="small" color="action" aria-hidden="true"
                    sx={{ justifySelf: "center" }} />
                  <ComparisonPanel $after aria-label="修正後">
                    <Text variant="subtitle2">修正後</Text>
                    <AnswerText>{TUTORIAL_EDIT_AFTER}</AnswerText>
                  </ComparisonPanel>
                  <Text variant="body2" color="text.secondary">
                    抽象的な表現を、学んだことが伝わる具体的な言葉に整えました。
                  </Text>
                </EditComparison>
              )}
              {view.editing ? (
                <Input label="案Aの回答を編集" value={answer} multiline minRows={5}
                  helperText={`${countStarText(answer)} / ${STAR_OUTPUT_LIMIT} 文字`}
                  slotProps={{ input: { readOnly: true },
                    htmlInput: { tabIndex: -1, "aria-label": "編集画面の文章" } }} />
              ) : <AnswerText aria-label="回答案の文章">{answer}</AnswerText>}
              <Text variant="caption" color="text.secondary">
                {countStarText(answer)} / {STAR_OUTPUT_LIMIT}文字
              </Text>
              <AssistCandidateActions preview editing={view.editing} />
              <Text variant="caption" color="text.secondary">
                コピー・編集・回答反映のボタンは体験用です。「次へ」で操作を再現します。
              </Text>
            </AnswerCard>
            <AssistCandidateNavigation preview
              ids={TUTORIAL_CANDIDATES.map((item) => item.id)}
              selected={candidate?.id ?? "A"} onSelect={() => {}} onBack={() => {}} />
          </>
        )}
      </Content>
      <Footer>
        <FooterHeading>
          <Text component="span" variant="caption" color="text.secondary">
            {view.completed ? "完了" : "STEP " + step + " / " + TUTORIAL_STEP_COUNT}
          </Text>
          <Text component="span" variant="caption" color="text.secondary">体験用・保存されません</Text>
        </FooterHeading>
        <LinearProgress variant="determinate"
          value={(view.completed ? TUTORIAL_STEP_COUNT : step - 1) / TUTORIAL_STEP_COUNT * 100}
          aria-label="チュートリアルの進捗"
          sx={{ height: 3, borderRadius: 2 }} />
        {step === 6 && (
          <div aria-label="体験用生成操作" style={{ display: "grid", gap: 4 }}>
            <Button type="button" variant="contained" endIcon={<AutoAwesomeOutlinedIcon />}
              disabled fullWidth>3案を生成（1回）</Button>
            <Text variant="caption" color="text.secondary" align="center">
              本番の生成ボタンの見本です。体験では「次へ」を押してください。
            </Text>
          </div>
        )}
        <FooterButtons>
          {view.completed ? (
            <>
              <Button type="button" variant="outlined" onClick={reset}>
                もう一度体験する
              </Button>
              <Button type="button" variant="contained" onClick={close} autoFocus>
                終了して練習に戻る
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outlined" disabled={step === 1} onClick={back}>戻る</Button>
              <Button type="button" variant="contained" onClick={next}>次へ</Button>
              <Button type="button" variant="text" onClick={close}>終了</Button>
            </>
          )}
        </FooterButtons>
      </Footer>
    </TutorialDialog>
  );
}
