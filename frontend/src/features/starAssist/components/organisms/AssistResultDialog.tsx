/** @file AssistResultDialog.tsx @description 5モード共通の生成成果物・編集・反映ポップアップ。 */
"use client";

import { useEffect, useState } from "react";
import EmojiEventsOutlinedIcon from "@mui/icons-material/EmojiEventsOutlined";
import { Alert, Dialog as MuiDialog, DialogContent, DialogTitle } from "@mui/material";
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
import { CandidateTabs, CandidateTab, AnswerCard, CardHeading, AnswerText, AssistResultHeading, AssistCandidateActions, AssistCandidateNavigation, STAR_RESULT_DESCRIPTION } from "../molecules/AssistResultPresentation";

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
const styleLabels = {
  conclusion: "結論重視",
  action: "行動重視",
  conversational: "会話重視",
} as const;
const titles = {
  star: "生成した3案の回答",
  prep: "簡潔回答アシストで生成した回答",
  motivation: "生成した志望動機",
  career_change: "生成した転職理由",
  career_plan: "生成したキャリアプラン",
  follow_up: "生成した深掘り回答",
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
        <AssistResultHeading title={titles[w.mode]} onClose={onClose}
          titleId="assist-result-title" descriptionId="assist-result-description"
          description={star ? STAR_RESULT_DESCRIPTION :
            "入力した内容をもとに回答案を作成しました。ご自身の事実に合うよう確認し、必要に応じて編集してください。"} />
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
            <AssistCandidateActions editing={editingId === candidate.id}
              onCopy={() => void copy()}
              onEdit={() => setEditingId(editingId === candidate.id ? null : candidate.id)}
              onApply={() => onApply(candidate.id)}
              copyDisabled={applying} editDisabled={applying || w.busy || w.pending}
              applyDisabled={disabled} />
            {copyNotice && (
              <Alert severity={copyNotice === "success" ? "success" : "error"} role="status">
                {copyNotice === "success" ? "回答をコピーしました。" : "コピーできませんでした。"}
              </Alert>
            )}
          </AnswerCard>
        )}
        {w.error && <Alert severity="error">{w.error}</Alert>}
        <AssistCandidateNavigation ids={star && candidates.length === 3 ? candidates.map((c) => c.id) : []}
          selected={candidate?.id ?? "A"} onSelect={(id) => choose(id as CandidateId)}
          onBack={onBack} disabled={applying} />
      </Body>
    </ResultDialog>
  );
}
