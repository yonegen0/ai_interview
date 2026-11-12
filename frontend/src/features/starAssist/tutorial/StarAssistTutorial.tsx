/** @file StarAssistTutorial.tsx @description 練習データに接続しない単一DialogのSTAR疑似体験。 */
"use client";

import { useEffect, useRef } from "react";
import CloseIcon from "@mui/icons-material/Close";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import {
  Dialog as MuiDialog, DialogActions, DialogContent, DialogTitle, IconButton,
  LinearProgress, useMediaQuery,
} from "@mui/material";
import { alpha, styled, useTheme } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { countStarNotes, targetCategories } from "@/lib/api/schemas/star";
import { starSteps } from "../model/steps";
import { StarAssistStepper } from "../components/molecules/StarAssistStepper";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_COMPANY,
  TUTORIAL_EDIT_AFTER, TUTORIAL_EDIT_BEFORE, TUTORIAL_EDITED_A,
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
const Header = styled(DialogTitle)(({ theme }) => ({
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
const FauxButtons = styled("div")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  gap: theme.spacing(1),
  minWidth: 0,
}));
const FauxButton = styled("span", {
  shouldForwardProp: (prop) => prop !== "$emphasized",
})<{ $emphasized?: boolean }>(({ theme, $emphasized }) => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  minHeight: 44,
  minWidth: 0,
  padding: theme.spacing(1, 1.5),
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + theme.palette.primary.main,
  backgroundColor: $emphasized ? theme.palette.primary.dark : theme.palette.background.paper,
  color: $emphasized ? theme.palette.primary.contrastText : theme.palette.primary.dark,
  fontWeight: 700,
  ...theme.typography.body2,
}));
const TabsPreview = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  gap: theme.spacing(1),
}));
const AnswerTitle = styled("div")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  gap: theme.spacing(1),
  alignItems: "center",
}));
const ChangedText = styled("mark")(({ theme }) => ({
  backgroundColor: alpha(theme.palette.primary.light, 0.42),
  color: theme.palette.text.primary,
  boxDecorationBreak: "clone",
  WebkitBoxDecorationBreak: "clone",
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
    if (target) target.scrollIntoView?.({ block: "nearest" });
    else content.scrollTop = 0;
  }, [step]);

  const candidate = view.selectedCandidate
    ? TUTORIAL_CANDIDATES.find((item) => item.id === view.selectedCandidate)
    : undefined;
  const changedParts = TUTORIAL_CANDIDATES[0].text.split(TUTORIAL_EDIT_BEFORE);
  const answer = view.edited && view.selectedCandidate === "A"
    ? TUTORIAL_EDITED_A : candidate?.text ?? "";
  return (
    <TutorialDialog open onClose={close} fullWidth maxWidth="md" fullScreen={fullScreen}
      aria-labelledby="star-tutorial-title" aria-describedby="star-tutorial-description">
      <Header component="div">
        <AutoAwesomeOutlinedIcon color="primary" aria-hidden="true" />
        <div>
          <Text component="h2" variant="h2" id="star-tutorial-title">
            STARアシストの使い方を体験
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
            <StarAssistStepper activeStep={Math.min(step - 1, 4)}
              steps={starSteps} label="体験用STAR入力" />
            <FieldList aria-label="体験用STAR入力">
              {starSteps.map(({ key, label, english }) => (
                <ViewCard key={key} aria-label={key + " " + label}
                  data-tutorial-target={view.highlight === key ? "true" : undefined}
                  $emphasized={view.highlight === key}>
                  <Text component="h4" variant="h3">
                    {key} {label}（{english}）
                  </Text>
                  <ReadingText>{view.notes[key] || "未入力"}</ReadingText>
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
                <FauxButtons aria-hidden="true">
                  <FauxButton $emphasized>3案を生成（1回）</FauxButton>
                </FauxButtons>
                <Text variant="caption" color="text.secondary">
                  実際のAIは使用せず、決まった3案を表示します。
                </Text>
              </ViewCard>
            )}
          </>
        ) : (
          <>
            <Text component="h3" variant="h3">生成した3案の回答（体験用）</Text>
            <TabsPreview aria-hidden="true">
              {TUTORIAL_CANDIDATES.map((item) => (
                <FauxButton key={item.id} $emphasized={candidate?.id === item.id}>
                  {item.id} {candidateLabels[item.id]}
                </FauxButton>
              ))}
            </TabsPreview>
            <Text role="status" variant="body2" color="text.secondary">
              表示中：{candidate?.id}案（{candidate ? candidateLabels[candidate.id] : ""}）
            </Text>
            <ViewCard aria-label="体験用候補の表示" data-tutorial-target="true"
              $emphasized={view.highlight === candidate?.id || view.highlight === "edit" || view.highlight === "apply"}>
              <AnswerTitle>
                <Text component="h4" variant="h3">
                  {view.editing ? "A案の回答を編集（体験用）" :
                    candidate ? candidate.id + "案の回答（" + candidateLabels[candidate.id] + "）" : ""}
                </Text>
              </AnswerTitle>
              <ReadingText aria-label={view.editing ? "編集画面の文章" : "回答案の文章"}>
                {view.edited && view.selectedCandidate === "A"
                  ? <>{changedParts[0]}<ChangedText>{TUTORIAL_EDIT_AFTER}</ChangedText>{changedParts[1]}</>
                  : answer}
              </ReadingText>
              <Text variant="caption" color="text.secondary">
                {Array.from(answer).length} / 600文字
              </Text>
              <FauxButtons aria-hidden="true">
                <FauxButton>コピー</FauxButton>
                <FauxButton $emphasized={view.highlight === "edit"}>編集する</FauxButton>
                <FauxButton $emphasized={view.highlight === "apply"}>この回答を使う</FauxButton>
              </FauxButtons>
              {view.editing && (
                <Text variant="caption" color="text.secondary">
                  文章の編集を体験中（キーボード入力は必要ありません）
                </Text>
              )}
            </ViewCard>
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
