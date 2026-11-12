/** @file AssistResultPresentation.tsx @description 実成果物と体験版で同じ見た目を利用する表示部品。 */
"use client";

import type { ReactNode } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import EmojiEventsOutlinedIcon from "@mui/icons-material/EmojiEventsOutlined";
import { IconButton, Tab, Tabs } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";

export const CandidateTabs = styled(Tabs)(({ theme }) => ({
  minHeight: 0,
  "& .MuiTabs-indicator": { display: "none" },
  "& .MuiTabs-flexContainer": { gap: theme.spacing(1) },
}));
export const CandidateTab = styled(Tab)(({ theme }) => ({
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
export const AnswerCard = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.75),
  padding: theme.spacing(2.5),
  minWidth: 0,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.36)}`,
  borderRadius: 20,
  background: `linear-gradient(145deg, ${alpha(theme.palette.primary.light, 0.12)}, ${alpha(theme.palette.background.paper, 0.93)})`,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1.75), borderRadius: 16 },
}));
export const CardHeading = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1),
  color: theme.palette.primary.dark, fontWeight: 700,
}));
export const AnswerText = styled("p")(({ theme }) => ({
  margin: 0,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  ...theme.typography.body1,
  lineHeight: 1.9,
  color: theme.palette.text.primary,
}));
export const ActionBar = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.spacing(1),
  "& > :last-child": { marginLeft: "auto" },
  [theme.breakpoints.down("sm")]: {
    "& > :last-child": { marginLeft: 0, width: "100%" },
    "& > :not(:last-child)": { flex: 1 },
  },
}));


const Heading = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "flex-start", gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { gap: theme.spacing(1) },
}));
const HeadingIcon = styled(AutoAwesomeOutlinedIcon)(({ theme }) => ({
  color: theme.palette.primary.main, fontSize: 44, flexShrink: 0,
  [theme.breakpoints.down("sm")]: { fontSize: 32 },
}));
const HeadingCopy = styled("div")(({ theme }) => ({
  minWidth: 0, flex: 1, display: "grid", gap: theme.spacing(0.75),
}));
const CloseButton = styled(IconButton)(({ theme }) => ({
  backgroundColor: alpha(theme.palette.background.paper, 0.8),
  boxShadow: `0 3px 14px ${alpha(theme.palette.common.black, 0.12)}`,
  "&:hover": { backgroundColor: theme.palette.background.paper },
}));

export const STAR_RESULT_DESCRIPTION =
  "入力したエピソードをもとに、A/B/Cの3案を作成しました。ご自身の事実に合うものを選び、必要に応じて編集してください。";

export function AssistResultHeading({ title, description, onClose, titleId, descriptionId }: {
  title: string; description: string; onClose: () => void;
  titleId?: string; descriptionId?: string;
}) {
  return (
    <Heading>
      <HeadingIcon aria-hidden="true" />
      <HeadingCopy>
        <Text component="h2" variant="h2" id={titleId}>{title}</Text>
        <Text variant="body2" id={descriptionId} color="text.secondary">{description}</Text>
      </HeadingCopy>
      <CloseButton size="small" onClick={onClose} aria-label="成果物を閉じる">
        <CloseIcon />
      </CloseButton>
    </Heading>
  );
}

export function AssistCandidateCard({ id, label, text, editing, length, maximum,
  editLabel, readOnly, helperText, children, target }: {
  id: string; label: string; text: string; editing: boolean; length: number; maximum: number;
  editLabel: string; readOnly?: boolean; helperText?: string; children?: ReactNode; target?: boolean;
}) {
  return (
    <AnswerCard aria-label="生成した回答アシスト" data-tutorial-target={target ? "true" : undefined}>
      <CardHeading>
        <EmojiEventsOutlinedIcon color="warning" aria-hidden="true" />
        <Text variant="h3" component="h3">{label}</Text>
      </CardHeading>
      {children}
      {editing ? (
        <Input label={editLabel} value={text} multiline minRows={5}
          slotProps={{ input: { readOnly: readOnly ?? false },
            htmlInput: readOnly ? { tabIndex: -1, "aria-label": "編集画面の文章" } : undefined }}
          helperText={helperText} error={length > maximum} />
      ) : <AnswerText aria-label="回答案の文章">{text}</AnswerText>}
      <Text variant="caption" color={length > maximum ? "error.main" : "text.secondary"}>
        {length} / {maximum}文字
      </Text>
    </AnswerCard>
  );
}

const Navigation = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.spacing(1),
}));
const Dots = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1.25),
}));
const Dot = styled("button", {
  shouldForwardProp: (prop) => prop !== "$active",
})<{ $active: boolean }>(({ theme, $active }) => ({
  width: 12, height: 12, borderRadius: "50%", border: 0,
  padding: 0, backgroundColor: $active ? theme.palette.primary.dark : theme.palette.grey[400],
  cursor: "pointer",
  "&:disabled": { cursor: "default" },
  "&:focus-visible": { outline: `3px solid ${theme.palette.primary.main}`, outlineOffset: 3 },
}));
const NavButton = styled(IconButton)(({ theme }) => ({
  border: `1px solid ${theme.palette.divider}`,
  backgroundColor: alpha(theme.palette.background.paper, 0.8),
}));
export function AssistCandidateNavigation({ ids, selected, onSelect, onBack, disabled = false, preview = false }: {
  ids: readonly string[]; selected: string;
  onSelect: (id: string) => void; onBack: () => void; disabled?: boolean; preview?: boolean;
}) {
  const index = Math.max(0, ids.indexOf(selected));
  return (
    <Navigation>
      <Button type="button" variant="text" onClick={onBack} disabled={disabled || preview}>入力画面に戻る</Button>
      {ids.length === 3 && (
        <>
          <NavButton aria-label="前の案" disabled={index === 0 || disabled || preview}
            onClick={() => onSelect(ids[index - 1])}><ArrowBackIosNewIcon /></NavButton>
          <Dots aria-label="案のページ切り替え">
            {ids.map((id) => (
              <Dot key={id} type="button" $active={id === selected}
                aria-label={`案${id}を表示`} aria-current={id === selected ? "page" : undefined}
                onClick={() => onSelect(id)} disabled={disabled || preview} />
            ))}
          </Dots>
          <NavButton aria-label="次の案" disabled={index === ids.length - 1 || disabled || preview}
            onClick={() => onSelect(ids[index + 1])}><ArrowForwardIosIcon /></NavButton>
        </>
      )}
    </Navigation>
  );
}

/** Preview controls are visibly disabled: they do not copy, mutate candidates, or adopt an answer. */
export function AssistCandidateActions({ editing, onCopy, onEdit, onApply, disabled = false, preview = false }: {
  editing: boolean; onCopy?: () => void; onEdit?: () => void; onApply?: () => void;
  disabled?: boolean; preview?: boolean;
}) {
  return (
    <ActionBar>
      <Button type="button" variant="outlined" startIcon={<ContentCopyOutlinedIcon />}
        onClick={onCopy} disabled={disabled || preview}>コピー</Button>
      <Button type="button" variant="outlined" startIcon={<EditOutlinedIcon />}
        onClick={onEdit} disabled={disabled || preview}>
        {editing ? "編集を終える" : "編集する"}
      </Button>
      <Button type="button" variant="contained" startIcon={<CheckIcon />}
        disabled={disabled || preview} onClick={onApply}>この回答を使う</Button>
    </ActionBar>
  );
}
