/** @file StarAssistPresentation.tsx @description 本番と体験に共通するSTAR入力・設定の表示。処理や保存には依存しない。 */
"use client";

import type { ReactNode } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CloseIcon from "@mui/icons-material/Close";
import FlagOutlinedIcon from "@mui/icons-material/FlagOutlined";
import { IconButton } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Text } from "@/components/atoms/Text";
import type { AssistMode } from "@/lib/api/schemas/star";
import { assistModes, type AssistStep } from "../../model/steps";

const Header = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(1),
}));
const HeaderRow = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", flexWrap: "wrap", gap: theme.spacing(1),
}));
const HeaderIcon = styled(AutoAwesomeOutlinedIcon)(({ theme }) => ({
  color: theme.palette.primary.main,
}));
const Tag = styled("span")(({ theme }) => ({
  borderRadius: theme.shape.borderRadius,
  background: alpha(theme.palette.primary.main, 0.09),
  color: theme.palette.primary.dark,
  padding: theme.spacing(0.5, 1.5),
  ...theme.typography.body2,
  fontWeight: 600,
}));
const Close = styled(IconButton)(({ theme }) => ({
  marginLeft: "auto", color: theme.palette.text.secondary,
}));

export function StarAssistHeader({ mode, onClose, titleId, closeLabel, extra }: {
  mode: AssistMode; onClose: () => void;
  titleId?: string; closeLabel?: string; extra?: ReactNode;
}) {
  const meta = assistModes[mode];
  return (
    <Header>
      <HeaderRow>
        <HeaderIcon fontSize="large" aria-hidden="true" />
        <Text variant="h2" component="h2" id={titleId}>{meta.label}</Text>
        <Tag>{meta.tag}</Tag>
        <Close aria-label={closeLabel ?? meta.label + "を閉じる"} onClick={onClose} size="small">
          <CloseIcon />
        </Close>
      </HeaderRow>
      <Text variant="body2" color="text.secondary">{meta.description}</Text>
      {extra}
    </Header>
  );
}

export const StarAssistColumns = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)",
  gap: theme.spacing(2),
  alignItems: "stretch",
  [theme.breakpoints.down("md")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
export const StarAssistSettings = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  padding: theme.spacing(2),
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
}));
export const StarAssistSettingFields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
export const StarAssistSettingActions = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.spacing(1),
}));

const FormCard = styled("section")(({ theme }) => ({
  minWidth: 0,
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(3),
  display: "grid", alignContent: "start", gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
const Heading = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1.5),
  "& svg": { color: theme.palette.primary.main, flexShrink: 0 },
}));
const Count = styled("div")({ textAlign: "right" });

export function StarAssistStepCard({ step, count, error, detail, children, tutorialTarget }: {
  step: AssistStep; count: number; error?: boolean; detail?: ReactNode;
  children: ReactNode; tutorialTarget?: boolean;
}) {
  return (
    <FormCard aria-label={step.label + "の入力"}
      data-tutorial-target={tutorialTarget ? "true" : undefined}>
      <Heading>
        <FlagOutlinedIcon fontSize="large" aria-hidden="true" />
        <Text variant="h2" component="h2">{step.label}（{step.english}）</Text>
      </Heading>
      <Text variant="body2" color="text.secondary">{step.description}</Text>
      {detail}
      {children}
      <Count>
        <Text variant="caption" color={error ? "error.main" : "text.secondary"}>
          {count}文字入力
        </Text>
      </Count>
    </FormCard>
  );
}
