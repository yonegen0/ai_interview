/** @file StarAssistTutorial.tsx @description 練習データに接続しない単一DialogのSTAR疑似体験。 */
"use client";

import { useEffect, useRef } from "react";
import CloseIcon from "@mui/icons-material/Close";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import EmojiEventsOutlinedIcon from "@mui/icons-material/EmojiEventsOutlined";
import {
  Dialog as MuiDialog, DialogActions, DialogContent, IconButton,
  LinearProgress, useMediaQuery,
} from "@mui/material";
import { alpha, styled, useTheme } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { countStarNotes, targetCategories, STAR_OUTPUT_LIMIT, countStarText } from "@/lib/api/schemas/star";
import { starSteps } from "../model/steps";
import { StarAssistStepper } from "../components/molecules/StarAssistStepper";
import { CandidateTabs, CandidateTab, AnswerCard, CardHeading, AnswerText, ActionBar } from "../components/molecules/AssistResultPresentation";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_COMPANY,
  TUTORIAL_EDITED_A,
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
      height: "100dvh",
      maxHeight: "100dvh",
      width: "100%",
      margin: 0,
      borderRadius: 0,
    },
  },
}));
const Header = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  borderBottom: "1px solid " + theme.palette.divider,
  padding: theme.spacing(2, 2.5),
  "& > :first-of-type": { flex: 1 },
}));
const Content = styled(DialogContent)(({ theme }) => ({
  display: "grid",
  alignContent: "start",
  gap: theme.spacing(2),
  flex: 1,
  minHeight: 0,
  overflowY: "auto",
  overflowX: "hidden",
  overscrollBehavior: "contain",
  padding: theme.spacing(2.5),
  "&.MuiDialogContent-root": { paddingTop: theme.spacing(2.5) },
  [theme.breakpoints.down("sm")]: { paddingInline: theme.spacing(2) },
}));
const Footer = styled(DialogActions)(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1),
  borderTop: "1px solid " + theme.palette.divider,
  padding: theme.spacing(1.5, 2.5),
  paddingBottom: "max(12px, env(safe-area-inset-bottom))",
  backgroundColor: theme.palette.background.paper,
  [theme.breakpoints.down("sm")]: { paddingInline: theme.spacing(2) },
}));
const FooterButtons = styled("div")(({ theme }) => ({
  display: "flex",
  justifyContent: "flex-end",
  gap: theme.spacing(1),
  flexWrap: "wrap",
  "& .MuiButton-root": {
    minHeight: 44,
    minWidth: 0,
    flex: "1 1 auto",
    paddingInline: theme.spacing(1.5),
  },
}));
const FooterHeading = styled("div")(({ theme }) => ({
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: theme.spacing(1),
}));
const Question = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.75),
  padding: theme.spacing(2),
  background: alpha(theme.palette.primary.light, 0.15),
  borderRadius: theme.shape.borderRadius,
  overflowWrap: "anywhere",
}));
const ViewCard = styled("section", {
  shouldForwardProp: (prop) => prop !== "$emphasized",
})<{ $emphasized?: boolean }>(({ theme, $emphasized }) => ({
  display: "grid",
  gap: theme.spacing(1),
  minWidth: 0,
  padding: theme.spacing(2),
  border: "1px solid " + ($emphasized ? theme.palette.primary.main : theme.palette.divider),
  borderRadius: theme.shape.borderRadius,
  backgroundColor: $emphasized
    ? alpha(theme.palette.primary.light, 0.19) : theme.palette.background.paper,
  boxShadow: $emphasized ? theme.shadows[1] : "none",
  overflowWrap: "anywhere",
}));
const FieldList = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.25),
  minWidth: 0,
}));
const ReadingText = styled("p")(({ theme }) => ({
  margin: 0,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  lineHeight: 1.9,
  ...theme.typography.body1,
}));
const StepDescription = styled("div")(({ theme }) => ({
  padding: theme.spacing(1, 0),
  color: theme.palette.text.primary,
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
    // Keep scrolling inside the dialog; scrollIntoView can also move the underlying page.
    if (target) {
      const offset = target.getBoundingClientRect().top - content.getBoundingClientRect().top;
      content.scrollTop += offset - 12;
    } else content.scrollTop = 0;
  }, [step]);

  const candidate = view.selectedCandidate
    ? TUTORIAL_CANDIDATES.find((item) => item.id === view.selectedCandidate)
    : undefined;
  const answer = view.edited && view.selectedCandidate === "A"
    ? TUTORIAL_EDITED_A : candidate?.text ?? "";
  return (
    <TutorialDialog open onClose={close} fullWidth maxWidth="md" fullScreen={fullScreen}
      aria-labelledby="star-tutorial-title" aria-describedby="star-tutorial-description">
      <Header>
        <AutoAwesomeOutlinedIcon color="primary" aria-hidden="true" />
        <div>
          <Text component="h2" variant="h2" id="star-tutorial-title">
            エピソード作成アシストの使い方を体験
          </Text>
          <Text variant="caption" color="text.secondary">体験用表示・入力不要</Text>
        </div>
        <IconButton size="small" onClick={close} aria-label="チュートリアルを閉じる">
          <CloseIcon />
        </IconButton>
      </Header>
      <Content ref={contentRef}>
        <Question aria-label="体験用の質問">
          <Text component="h3" variant="h3">今回の質問</Text>
          <Text>{TUTORIAL_QUESTION}</Text>
        </Question>
        {view.completed ? (
          <>
            <Text component="h3" variant="h2">チュートリアル完了！</Text>
            <Text>
              回答を作成して、回答欄に反映するところまで体験できました。
            </Text>
            <Text>
              実際の練習でも、3つの回答案から好きなものを選び、自分の言葉に修正して使うことができます。
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
            <Text component="h3" variant="h3">エピソード作成アシスト</Text>
            <StarAssistStepper activeStep={Math.min(Math.max(0, step - 2), 3)}
              steps={starSteps} label="体験用STAR入力" />
            <FieldList aria-label="体験用STAR入力">
              {starSteps.map(({ key, label, english }) => (
                <ViewCard key={key} aria-label={key + " " + label}
                  data-tutorial-target={view.highlight === key ? "true" : undefined}
                  $emphasized={view.highlight === key}>
                  <Text component="h4" variant="h3">
                    {key} {label}（{english}）
                  </Text>
                  <Input
                    label={key === "A" ? "A 本人の行動" : key + " " + label}
                    value={view.notes[key]}
                    placeholder="未入力"
                    multiline minRows={3}
                    slotProps={{ input: { readOnly: true }, htmlInput: { tabIndex: -1 } }}
                  />
                  {!view.notes[key] && <Text variant="caption" color="text.secondary">未入力</Text>}
                </ViewCard>
              ))}
            </FieldList>
            <Text variant="caption" color="text.secondary">
              体験用の入力文字数：{countStarNotes(view.notes)} / 600文字
            </Text>
            {step >= 5 && (
              <ViewCard aria-label="体験用応募先設定"
                data-tutorial-target={view.highlight === "category" ? "true" : undefined}
                $emphasized={view.highlight === "category"}>
                <Text component="h3" variant="h3">応募先の設定</Text>
                <Text>
                  応募先カテゴリ：{view.targetCategory
                    ? targetCategories[view.targetCategory] : "未選択"}
                </Text>
                <Text variant="body2" color="text.secondary">
                  志望業界：{TUTORIAL_INDUSTRY || "空欄"} ／ 応募先企業名：{TUTORIAL_COMPANY || "空欄"}
                </Text>
              </ViewCard>
            )}
            {step === 6 && (
              <ViewCard aria-label="体験用生成操作" data-tutorial-target="true" $emphasized>
                <Text component="h3" variant="h3">回答案の生成</Text>
                <div aria-hidden="true">
                  <Button variant="contained" type="button" tabIndex={-1} sx={{ pointerEvents: "none" }}>
                    3案を生成（1回）
                  </Button>
                </div>
                <Text variant="caption" color="text.secondary">
                  実際のAIは使用せず、決まった3案を表示します。
                </Text>
              </ViewCard>
            )}
          </>
        ) : (
          <>
            <Text component="h3" variant="h3">生成した3案の回答（体験用）</Text>
            <div aria-hidden="true">
              <CandidateTabs value={candidate?.id ?? "A"} onChange={() => {}}
                aria-label="体験用回答案の表示" variant="fullWidth">
                {TUTORIAL_CANDIDATES.map((item) => (
                  <CandidateTab key={item.id} value={item.id} tabIndex={-1}
                    label={item.id + " " + candidateLabels[item.id]} />
                ))}
              </CandidateTabs>
            </div>
            <Text role="status" variant="body2" color="text.secondary">
              表示中：{candidate?.id}案（{candidate ? candidateLabels[candidate.id] : ""}）
              ・切り替え操作は下の「次へ」で体験します。
            </Text>
            <AnswerCard aria-label="体験用候補の表示" data-tutorial-target="true"
              sx={{ outline: "2px solid", outlineColor: "primary.main" }}>
              <CardHeading>
                <EmojiEventsOutlinedIcon color="warning" aria-hidden="true" />
                <Text component="h4" variant="h3">
                  {view.editing ? "A案の回答を編集（体験用）" :
                    candidate ? "案" + candidate.id + "の回答（" + candidateLabels[candidate.id] + "）" : ""}
                </Text>
              </CardHeading>
              {view.editing ? (
                <Input label="案Aの回答を編集" value={answer}
                  multiline minRows={5}
                  slotProps={{ input: { readOnly: true }, htmlInput: { tabIndex: -1, "aria-label": "編集画面の文章" } }} />
              ) : (
                <AnswerText aria-label="回答案の文章">{answer}</AnswerText>
              )}
              {view.edited && <Text variant="body2" color="text.secondary">
                編集例：説明することも心掛けました → 問い合わせを待たずに、こちらから状況を説明するようにしました
              </Text>}
              <Text variant="caption" color="text.secondary">
                {countStarText(answer)} / {STAR_OUTPUT_LIMIT}文字
              </Text>
              <ActionBar aria-hidden="true">
                <Button type="button" variant="outlined" tabIndex={-1} sx={{ pointerEvents: "none" }}>
                  コピー
                </Button>
                <Button type="button" variant="outlined" tabIndex={-1} sx={{ pointerEvents: "none" }}>
                  {view.editing ? "編集を終える" : "編集する"}
                </Button>
                <Button type="button" variant="contained" tabIndex={-1} sx={{ pointerEvents: "none" }}>
                  この回答を使う
                </Button>
              </ActionBar>
              {view.editing && (
                <Text variant="caption" color="text.secondary">
                  文章の編集を体験中（キーボード入力は必要ありません）
                </Text>
              )}
            </AnswerCard>
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
          aria-label="チュートリアルの進捗" />
        <StepDescription id="star-tutorial-description" role="status" aria-live="polite" aria-atomic="true">
          <Text variant="body2">{view.description}</Text>
        </StepDescription>
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
              <Button type="button" variant="outlined" disabled={step === 1} onClick={back}>
                戻る
              </Button>
              <Button type="button" variant="contained" onClick={next}>次へ</Button>
              <Button type="button" variant="text" onClick={close}>終了</Button>
            </>
          )}
        </FooterButtons>
      </Footer>
    </TutorialDialog>
  );
}
