/** @file AssistResultDialog.tsx @description 5モード共通の生成成果物・編集・反映ポップアップ。 */
"use client";

import { useEffect, useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import EmojiEventsOutlinedIcon from "@mui/icons-material/EmojiEventsOutlined";
import { Alert, Dialog as MuiDialog, DialogContent, DialogTitle, IconButton, Tab, Tabs } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { COACHING_ANSWER_MAX_LENGTH, countCodePoints } from "@/lib/textLimits";
import {
  OTHER_ASSIST_OUTPUT_LIMIT, STAR_OUTPUT_LIMIT, countStarText, starInputSchema,
  type StarInput,
} from "@/lib/api/schemas/star";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";

type CandidateId = NonNullable<StarInput["selectedCandidateId"]>;
type Props = {
  open: boolean;
  workspace: StarWorkspace;
  applying: boolean;
  onClose: () => void;
  onBack: () => void;
  onApply: (id: CandidateId) => void;
};

const ResultDialog = styled(MuiDialog)(({ theme }) => ({
  "& .MuiBackdrop-root": {
    backgroundColor: alpha(theme.palette.common.black, 0.48),
    backdropFilter: "blur(5px)",
    WebkitBackdropFilter: "blur(5px)",
  },
  "& .MuiDialog-paper": {
    width: "min(880px, calc(100% - 24px))",
    maxWidth: "none",
    maxHeight: "calc(100dvh - 24px)",
    margin: theme.spacing(1.5),
    border: `1px solid ${alpha(theme.palette.primary.main, 0.18)}`,
    borderRadius: 28,
    background: `radial-gradient(ellipse at 96% 0%, ${alpha(theme.palette.primary.light, 0.32)}, transparent 49%), linear-gradient(145deg, ${alpha(theme.palette.primary.light, 0.14)}, ${theme.palette.background.paper} 43%)`,
    boxShadow: `0 24px 70px ${alpha(theme.palette.common.black, 0.22)}`,
    overflow: "hidden",
    [theme.breakpoints.down("sm")]: {
      maxHeight: "calc(100dvh - 16px)",
      borderRadius: 22,
      margin: theme.spacing(1),
    },
  },
}));
const Heading = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "flex-start",
  gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { gap: theme.spacing(1) },
}));
const HeadingIcon = styled(AutoAwesomeOutlinedIcon)(({ theme }) => ({
  color: theme.palette.primary.main,
  fontSize: 44,
  flexShrink: 0,
  [theme.breakpoints.down("sm")]: { fontSize: 32 },
}));
const HeadingCopy = styled("div")(({ theme }) => ({
  minWidth: 0,
  flex: 1,
  display: "grid",
  gap: theme.spacing(0.75),
}));
const CloseButton = styled(IconButton)(({ theme }) => ({
  backgroundColor: alpha(theme.palette.background.paper, 0.8),
  boxShadow: `0 3px 14px ${alpha(theme.palette.common.black, 0.12)}`,
  "&:hover": { backgroundColor: theme.palette.background.paper },
}));
const Body = styled(DialogContent)(({ theme }) => ({
  display: "grid",
  alignContent: "start",
  gap: theme.spacing(2),
  minHeight: 0,
  overflowY: "auto",
  padding: theme.spacing(1.5, 3, 2.5),
  paddingBottom: `max(${theme.spacing(2.5)}, env(safe-area-inset-bottom))`,
  [theme.breakpoints.down("sm")]: { paddingInline: theme.spacing(2) },
}));
const CandidateTabs = styled(Tabs)(({ theme }) => ({
  minHeight: 0,
  "& .MuiTabs-indicator": { display: "none" },
  "& .MuiTabs-flexContainer": { gap: theme.spacing(1) },
}));
const CandidateTab = styled(Tab)(({ theme }) => ({
  flex: 1,
  minWidth: 0,
  minHeight: 54,
  padding: theme.spacing(1, 0.5),
  border: `1px solid ${theme.palette.divider}`,
  borderRadius: 12,
  background: alpha(theme.palette.background.paper, 0.82),
  color: theme.palette.text.primary,
  fontWeight: 700,
  textTransform: "none",
  "&.Mui-selected": {
    color: theme.palette.primary.contrastText,
    background: theme.palette.primary.dark,
    borderColor: theme.palette.primary.dark,
    boxShadow: `0 5px 14px ${alpha(theme.palette.primary.main, 0.2)}`,
  },
  "&.Mui-focusVisible": { outline: `3px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
  [theme.breakpoints.down("sm")]: { fontSize: "0.78rem", minHeight: 48 },
}));
const AnswerCard = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.75),
  padding: theme.spacing(2.5),
  minWidth: 0,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.36)}`,
  borderRadius: 20,
  background: `linear-gradient(145deg, ${alpha(theme.palette.primary.light, 0.12)}, ${alpha(theme.palette.background.paper, 0.93)})`,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1.75), borderRadius: 16 },
}));
const CardHeading = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1),
  color: theme.palette.primary.dark, fontWeight: 700,
}));
const AnswerText = styled("p")(({ theme }) => ({
  margin: 0,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  ...theme.typography.body1,
  lineHeight: 1.9,
  color: theme.palette.text.primary,
}));
const ActionBar = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.spacing(1),
  "& > :last-child": { marginLeft: "auto" },
  [theme.breakpoints.down("sm")]: {
    "& > :last-child": { marginLeft: 0, width: "100%" },
    "& > :not(:last-child)": { flex: 1 },
  },
}));
const Navigation = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", justifyContent: "space-between",
  gap: theme.spacing(1),
}));
const Dots = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1.25),
}));
const Dot = styled("button", {
  shouldForwardProp: (prop) => prop !== "$active",
})<{ $active: boolean }>(({ theme, $active }) => ({
  width: 12, height: 12, borderRadius: "50%",
  border: 0,
  padding: 0,
  backgroundColor: $active ? theme.palette.primary.dark : theme.palette.grey[400],
  cursor: "pointer",
  "&:focus-visible": { outline: `3px solid ${theme.palette.primary.main}`, outlineOffset: 3 },
}));
const NavButton = styled(IconButton)(({ theme }) => ({
  border: `1px solid ${theme.palette.divider}`,
  backgroundColor: alpha(theme.palette.background.paper, 0.8),
}));

const styleLabels = {
  conclusion: "結論重視",
  action: "行動重視",
  conversational: "会話重視",
} as const;
const titles = {
  star: "生成した3案の回答",
  prep: "生成したPREP回答",
  motivation: "生成した志望動機",
  career_change: "生成した転職理由",
  career_plan: "生成したキャリアプラン",
} as const;

export function AssistResultDialog({ open, workspace: w, applying, onClose, onBack, onApply }: Props) {
  const [activeId, setActiveId] = useState<CandidateId>("A");
  const [editingId, setEditingId] = useState<CandidateId | null>(null);
  const [copyNotice, setCopyNotice] = useState<"success" | "error" | null>(null);
  useEffect(() => {
    setActiveId("A");
    setEditingId(null);
    setCopyNotice(null);
  }, [w.input.generationId]);

  const candidates = w.input.candidates;
  const index = Math.max(0, candidates.findIndex((c) => c.id === activeId));
  const candidate = candidates[index];
  const star = w.mode === "star";
  const maximum = star ? STAR_OUTPUT_LIMIT : OTHER_ASSIST_OUTPUT_LIMIT;
  const length = candidate ? (star ? countStarText(candidate.text) : candidate.text.length) : 0;
  const answerLength = candidate ? countCodePoints(candidate.text) : 0;
  const valid = starInputSchema.safeParse(w.input).success;
  const disabled = applying || w.busy || w.pending || !valid ||
    (w.input.assistType ?? "star") !== w.mode || !candidate?.text.trim();
  const choose = (id: CandidateId) => {
    if (!candidates.some((c) => c.id === id)) return;
    setActiveId(id);
    setCopyNotice(null);
  };
  const copy = async () => {
    if (!candidate) return;
    try {
      await navigator.clipboard.writeText(w.form.getValues(`candidates.${index}.text`));
      setCopyNotice("success");
    } catch {
      setCopyNotice("error");
    }
  };

  return (
    <ResultDialog open={open} onClose={onClose} aria-labelledby="assist-result-title"
      aria-describedby="assist-result-description" fullWidth>
      <DialogTitle component="div">
        <Heading>
          <HeadingIcon aria-hidden="true" />
          <HeadingCopy>
            <Text component="h2" variant="h2" id="assist-result-title">{titles[w.mode]}</Text>
            <Text variant="body2" id="assist-result-description" color="text.secondary">
              {star
                ? "入力したエピソードをもとに、A/B/Cの3案を作成しました。ご自身の事実に合うものを選び、必要に応じて編集してください。"
                : "入力した内容をもとに回答案を作成しました。ご自身の事実に合うよう確認し、必要に応じて編集してください。"}
            </Text>
          </HeadingCopy>
          <CloseButton size="small" onClick={onClose} aria-label="成果物を閉じる">
            <CloseIcon />
          </CloseButton>
        </Heading>
      </DialogTitle>
      <Body>
        {star && candidates.length === 3 && (
          <CandidateTabs value={candidate?.id ?? "A"}
            onChange={(_, value: CandidateId) => choose(value)}
            aria-label="生成した回答案の切り替え" variant="fullWidth">
            {candidates.map((item) => (
              <CandidateTab key={item.id} value={item.id}
                label={`${item.id} ${styleLabels[item.style]}`} />
            ))}
          </CandidateTabs>
        )}
        {candidate && (
          <AnswerCard aria-label="生成した回答アシスト">
            <CardHeading>
              <EmojiEventsOutlinedIcon color="warning" aria-hidden="true" />
              <Text variant="h3" component="h3">
                {star ? `案${candidate.id}の回答（${styleLabels[candidate.style]}）` : "生成した回答"}
              </Text>
            </CardHeading>
            {editingId === candidate.id ? (
              <Input {...w.form.register(`candidates.${index}.text`)}
                label={`案${candidate.id}の回答を編集`} multiline minRows={5}
                disabled={applying || w.busy || w.pending}
                error={length > maximum}
                helperText={`${length} / ${maximum} ${star ? "文字" : "UTF-16単位"}`}
              />
            ) : <AnswerText>{candidate.text}</AnswerText>}
            <Text variant="caption" color={length > maximum ? "error.main" : "text.secondary"}>
              {length} / {maximum} {star ? "文字" : "UTF-16単位"}
            </Text>
            {answerLength > COACHING_ANSWER_MAX_LENGTH && (
              <Alert severity="warning">
                この回答は{answerLength}文字です。正式な回答の上限は
                {COACHING_ANSWER_MAX_LENGTH}文字です。反映後に短く編集してください。
                自動では切り捨てません。
              </Alert>
            )}
            <ActionBar>
              <Button type="button" variant="outlined" startIcon={<ContentCopyOutlinedIcon />}
                onClick={() => void copy()} disabled={applying}>コピー</Button>
              <Button type="button" variant="outlined" startIcon={<EditOutlinedIcon />}
                onClick={() => setEditingId(editingId === candidate.id ? null : candidate.id)}
                disabled={applying || w.busy || w.pending}>
                {editingId === candidate.id ? "編集を終える" : "編集する"}
              </Button>
              <Button type="button" variant="contained" startIcon={<CheckCircleOutlineIcon />}
                disabled={disabled} onClick={() => onApply(candidate.id)}>
                この回答を使う
              </Button>
            </ActionBar>
            {copyNotice && (
              <Alert severity={copyNotice === "success" ? "success" : "error"} role="status">
                {copyNotice === "success" ? "回答をコピーしました。" : "コピーできませんでした。"}
              </Alert>
            )}
          </AnswerCard>
        )}
        {w.error && <Alert severity="error">{w.error}</Alert>}
        <Navigation>
          <Button type="button" variant="text" onClick={onBack} disabled={applying}>
            入力画面に戻る
          </Button>
          {star && candidates.length === 3 && (
            <>
              <NavButton aria-label="前の案" disabled={index === 0 || applying}
                onClick={() => choose(candidates[index - 1].id)}>
                <ArrowBackIosNewIcon />
              </NavButton>
              <Dots aria-label="案のページ切り替え">
                {candidates.map((item) => (
                  <Dot key={item.id} type="button" $active={item.id === candidate?.id}
                    aria-label={`案${item.id}を表示`}
                    aria-current={item.id === candidate?.id ? "page" : undefined}
                    onClick={() => choose(item.id)} disabled={applying} />
                ))}
              </Dots>
              <NavButton aria-label="次の案" disabled={index === candidates.length - 1 || applying}
                onClick={() => choose(candidates[index + 1].id)}>
                <ArrowForwardIosIcon />
              </NavButton>
            </>
          )}
        </Navigation>
      </Body>
    </ResultDialog>
  );
}
