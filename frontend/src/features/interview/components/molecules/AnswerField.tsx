/** @file AnswerField.tsx @description 回答入力・Unicode文字数・前回回答復元操作を表示するMolecule。 */
"use client";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import { IconButton, Tooltip } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import type { UseFormRegisterReturn } from "react-hook-form";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { ANSWER_RECOMMENDATIONS, COACHING_ANSWER_MAX_LENGTH } from "@/lib/textLimits";
import type { AnswerKind } from "@/lib/textLimits";
import { scaledRadius } from "@/theme/tokens";

const FieldArea = styled("div")(({ theme }) => ({
  position: "relative",
  "& .MuiOutlinedInput-root": {
    minHeight: theme.spacing(30),
    alignItems: "flex-start",
    paddingBottom: theme.spacing(9),
    borderRadius: scaledRadius(theme, 1.5),
    "& fieldset": { borderColor: alpha(theme.palette.primary.main, 0.7) },
    "&.Mui-disabled fieldset": { borderColor: theme.palette.action.disabled },
    "&.Mui-error fieldset": { borderColor: theme.palette.error.main },
  },
  "& textarea": { overflowWrap: "anywhere" },
}));
const CopyControls = styled("div")(({ theme }) => ({
  position: "absolute",
  right: theme.spacing(1.5),
  bottom: theme.spacing(1.5),
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1),
  maxWidth: "calc(100% - " + theme.spacing(3) + ")",
}));
const CopyHint = styled("span")(({ theme }) => ({
  padding: theme.spacing(0.75, 1),
  borderRadius: theme.shape.borderRadius,
  backgroundColor: theme.palette.background.paper,
  color: theme.palette.primary.dark,
  boxShadow: theme.shadows[1],
  ...theme.typography.caption,
  fontWeight: 600,
}));
const CopyButton = styled(IconButton)(({ theme }) => ({
  width: theme.spacing(6),
  height: theme.spacing(6),
  flexShrink: 0,
  backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText,
  boxShadow: theme.shadows[2],
  "&:hover": { backgroundColor: theme.palette.primary.dark },
  "&.Mui-disabled": {
    backgroundColor: theme.palette.action.disabledBackground,
    color: theme.palette.action.disabled,
  },
  "&:focus-visible": {
    outline: "3px solid " + theme.palette.primary.main,
    outlineOffset: 3,
  },
}));
const CountRow = styled("div")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(0.5, 2),
  marginTop: theme.spacing(1.5),
  color: theme.palette.text.secondary,
}));
const FieldError = styled(Text)(({ theme }) => ({
  marginTop: theme.spacing(1),
}));

export const AnswerField = ({
  field,
  count,
  answerKind,
  disabled,
  error,
  canCopyPrevious = false,
  onCopyPrevious,
}: {
  field: UseFormRegisterReturn;
  count: number;
  answerKind: AnswerKind;
  disabled?: boolean;
  error?: string;
  canCopyPrevious?: boolean;
  onCopyPrevious?: () => void;
}) => {
  const { ref, ...registration } = field;
  const recommended = ANSWER_RECOMMENDATIONS[answerKind];
  return (
    <div>
      <FieldArea>
        <Input
          {...registration}
          inputRef={ref}
          label="あなたの回答"
          slotProps={{ inputLabel: { shrink: true } }}
          multiline
          minRows={6}
          disabled={disabled}
          error={!!error}
        />
        {canCopyPrevious && onCopyPrevious && (
          <CopyControls>
            <CopyHint aria-hidden="true">前回の回答をコピー</CopyHint>
            <Tooltip title="前回の回答をコピー">
              <span>
                <CopyButton
                  type="button"
                  aria-label="前回の回答をコピー"
                  onClick={onCopyPrevious}
                  disabled={disabled}
                >
                  <ContentCopyOutlinedIcon aria-hidden="true" />
                </CopyButton>
              </span>
            </Tooltip>
          </CopyControls>
        )}
      </FieldArea>
      <CountRow role="status" aria-live="polite">
        <Text component="span" variant="body2">
          {count} / {COACHING_ANSWER_MAX_LENGTH}文字
        </Text>
        <Text component="span" variant="body2">
          {recommended.min}〜{recommended.max}文字がおすすめです
        </Text>
      </CountRow>
      {error && (
        <FieldError component="p" variant="body2" color="error" role="alert">
          {error}
        </FieldError>
      )}
    </div>
  );
};
