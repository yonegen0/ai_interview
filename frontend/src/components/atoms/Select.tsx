/**
 * @file Select.tsx
 * @description 全画面で利用する共通セレクトコンポーネント（FormControl + ラベル + 選択肢 + エラーを内包）
 */
"use client";

import { useId } from "react";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import MuiSelect from "@mui/material/Select";
import type { ReactNode, Ref } from "react";
import type { SelectChangeEvent } from "@mui/material/Select";
import { alpha, styled } from "@mui/material/styles";
import { fieldStyles } from "@/theme/fieldStyles";
import { scaledRadius } from "@/theme/tokens";

/** 選択肢 1 件 */
export type SelectOption<T extends string | number> = {
  /** 選択値 */
  value: T;
  /** 表示ラベル */
  label: ReactNode;
  /** メニュー右側の補助ラベル（category 表示時のみ使用） */
  secondaryLabel?: string;
};

/** 共通 Select の Props */
export type SelectProps<T extends string | number> = {
  /** フィールドラベル（InputLabel に表示） */
  label: string;
  name?: string;
  id?: string;
  onBlur?: () => void;
  inputRef?: Ref<HTMLInputElement>;
  describedBy?: string;
  /** 現在値 */
  value: T;
  /** 値変更ハンドラ（型付き値を直接返す） */
  onChange: (value: T) => void;
  /** 選択肢一覧（配列順が表示順） */
  options: ReadonlyArray<SelectOption<T>>;
  /** バリデーションエラー文言（あれば helper に表示） */
  error?: string;
  /** 非活性 */
  disabled?: boolean;
  /** サイズ（既定 medium） */
  size?: "small" | "medium";
  /** 全幅にする */
  fullWidth?: boolean;
  /** 最小幅 px（fullWidth と排他運用） */
  minWidth?: number;
  /** category のみ装飾付きメニューを使用（省略時は従来の表示） */
  variant?: "default" | "category";
};

/** styled 用の prop */
type StyledFormControlProps = {
  $fullWidth: boolean;
  $minWidth?: number;
};

/** ルート FormControl（Input.tsx の glass レシピを踏襲） */
const StyledFormControl = styled(FormControl, {
  shouldForwardProp: (prop) => prop !== "$fullWidth" && prop !== "$minWidth",
})<StyledFormControlProps>(({ theme, $fullWidth, $minWidth }) => ({
  width: $fullWidth ? "100%" : undefined,
  minWidth: $minWidth,
  ...fieldStyles(theme),
  "& .MuiSelect-select": {
    color: theme.palette.text.primary,
    fontWeight: 500,
  },
  "& .MuiSelect-icon": {
    color: theme.palette.text.secondary,
    transition: theme.transitions.create("color", { duration: 200 }),
  },
  "& .MuiOutlinedInput-root.Mui-focused .MuiSelect-icon": {
    color: theme.palette.primary.main,
  },
  "& .MuiOutlinedInput-root.Mui-error .MuiSelect-icon": {
    color: theme.palette.error.main,
  },
  "& .MuiOutlinedInput-root.Mui-disabled .MuiSelect-icon, & .MuiOutlinedInput-root.Mui-disabled.Mui-error .MuiSelect-icon":
    { color: theme.palette.text.disabled },
}));

/** ドロップダウンの glass パネル（Panel.tsx のレシピ準拠） */
const StyledMenuPaper = styled(Paper)(({ theme }) => ({
  // Popover 既定 paper（slots.paper 差し替えで失われる）位置決め・スクロールの土台を再付与
  position: "absolute",
  overflowX: "hidden",
  overflowY: "auto",
  maxHeight: "calc(100% - 32px)",
  // ---- 以下 glass 装飾 ----
  borderRadius: scaledRadius(theme, 0.875),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.12)}`,
  backgroundColor: alpha(theme.palette.common.white, 0.85),
  backdropFilter: "blur(12px)",
  boxShadow: `0 8px 32px ${alpha(theme.palette.primary.main, 0.16)}`,
  "& .MuiList-root": {
    paddingTop: theme.spacing(0.5),
    paddingBottom: theme.spacing(0.5),
  },
  "& .MuiMenuItem-root": {
    marginInline: theme.spacing(0.75),
    borderRadius: scaledRadius(theme, 0.5),
    paddingBlock: theme.spacing(0.75),
    transition: theme.transitions.create(["background-color", "color"], {
      duration: theme.transitions.duration.shortest,
    }),
    "&:hover": {
      backgroundColor: alpha(theme.palette.primary.main, 0.08),
    },
    "&.Mui-selected": {
      backgroundColor: alpha(theme.palette.primary.main, 0.14),
      color: theme.palette.primary.dark,
      fontWeight: 600,
      "&:hover": {
        backgroundColor: alpha(theme.palette.primary.main, 0.2),
      },
    },
  },
  [theme.breakpoints.down("md")]: {
    backdropFilter: "blur(6px)",
    boxShadow: `0 4px 12px ${alpha(theme.palette.primary.main, 0.1)}`,
  },
}));

/** カテゴリ練習でのみ使用するメニューパネル。通常の Select の見た目は変えない。 */
const StyledCategoryMenuPaper = styled(StyledMenuPaper)(({ theme }) => ({
  maxWidth: `calc(100vw - ${theme.spacing(4)})`,
  borderRadius: scaledRadius(theme, 1),
  "& .MuiList-root": {
    paddingBlock: theme.spacing(0.75),
  },
  "& .MuiMenuItem-root": {
    position: "relative",
    minHeight: theme.spacing(7),
    marginInline: theme.spacing(0.75),
    padding: theme.spacing(1, 1.5),
    borderRadius: scaledRadius(theme, 1.25),
    color: theme.palette.text.primary,
    "&:not(.Mui-selected):not(:last-child)::after": {
      content: '""',
      position: "absolute",
      left: theme.spacing(4),
      right: theme.spacing(1),
      bottom: 0,
      borderBottom: `1px solid ${alpha(theme.palette.text.secondary, 0.12)}`,
      pointerEvents: "none",
    },
    "&:hover": {
      backgroundColor: alpha(theme.palette.primary.main, 0.08),
    },
    "&.Mui-selected": {
      backgroundColor: alpha(theme.palette.primary.main, 0.12),
      color: theme.palette.text.primary,
      fontWeight: 600,
      "&:hover": {
        backgroundColor: alpha(theme.palette.primary.main, 0.18),
      },
    },
    "&.Mui-focusVisible": {
      outline: `2px solid ${theme.palette.primary.main}`,
      outlineOffset: "-2px",
    },
  },
}));

const StyledCategoryOption = styled("span")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.25),
  width: "100%",
  minWidth: 0,
  "&::before": {
    content: '""',
    display: "block",
    flex: "0 0 auto",
    width: theme.spacing(1),
    height: theme.spacing(1),
    borderRadius: "50%",
    backgroundColor: alpha(theme.palette.primary.main, 0.3),
    transition: theme.transitions.create(["height", "width", "background-color"], {
      duration: theme.transitions.duration.shortest,
    }),
  },
  ".Mui-selected &::before": {
    width: theme.spacing(0.5),
    height: theme.spacing(3),
    borderRadius: theme.spacing(1),
    backgroundColor: theme.palette.primary.main,
  },
}));

const StyledCategoryLabel = styled("span")({
  flex: "1 1 auto",
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
});

const StyledCategoryCount = styled("span")(({ theme }) => ({
  flex: "0 0 auto",
  whiteSpace: "nowrap",
  color: theme.palette.text.secondary,
  fontSize: theme.typography.body2.fontSize,
  fontWeight: 400,
}));

const StyledCategoryCheck = styled("span")(({ theme }) => ({
  display: "inline-flex",
  flex: "0 0 auto",
  alignItems: "center",
  justifyContent: "center",
  width: theme.spacing(3),
  height: theme.spacing(3),
  borderRadius: "50%",
  backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText,
  "& .MuiSvgIcon-root": {
    fontSize: theme.spacing(2),
  },
}));

const StyledClosedCategoryValue = styled("span")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  minWidth: 0,
  width: "100%",
  gap: theme.spacing(1),
}));

/**
 * 共通セレクトコンポーネントを表示する
 * @param props 表示に必要なプロパティ
 * @returns 共通 Select UI
 */
export const Select = <T extends string | number>(props: SelectProps<T>) => {
  const generatedId = useId();
  const inputId = props.id ?? generatedId;
  const labelId = `${inputId}-label`;
  const helperId = `${inputId}-helper`;
  const handleChange = (e: SelectChangeEvent<T>) => {
    props.onChange(e.target.value as T);
  };
  const hasError = !!props.error;
  return (
    <StyledFormControl
      error={hasError}
      size={props.size}
      disabled={props.disabled}
      $fullWidth={props.fullWidth ?? false}
      $minWidth={props.minWidth}
    >
      <InputLabel id={labelId}>{props.label}</InputLabel>
      <MuiSelect<T>
        id={inputId}
        name={props.name}
        inputRef={props.inputRef}
        onBlur={props.onBlur}
        aria-describedby={
          [props.describedBy, hasError ? helperId : undefined]
            .filter(Boolean)
            .join(" ") || undefined
        }
        labelId={labelId}
        label={props.label}
        value={props.value}
        onChange={handleChange}
        MenuProps={{
          slots: {
            paper:
              props.variant === "category"
                ? StyledCategoryMenuPaper
                : StyledMenuPaper,
          },
        }}
        renderValue={
          props.variant === "category"
            ? (selectedValue) => {
                const option = props.options.find(
                  (candidate) =>
                    String(candidate.value) === String(selectedValue),
                );
                return option ? (
                  <StyledClosedCategoryValue>
                    <StyledCategoryLabel>{option.label}</StyledCategoryLabel>
                    {option.secondaryLabel ? (
                      <StyledCategoryCount>
                        {option.secondaryLabel}
                      </StyledCategoryCount>
                    ) : null}
                  </StyledClosedCategoryValue>
                ) : null;
              }
            : undefined
        }
      >
        {props.options.map((o) => (
          <MenuItem
            key={String(o.value)}
            value={o.value}
            aria-label={
              props.variant === "category" && typeof o.label === "string"
                ? `${o.label}${o.secondaryLabel ?? ""}`
                : undefined
            }
          >
            {props.variant === "category" ? (
              <StyledCategoryOption>
                <StyledCategoryLabel>{o.label}</StyledCategoryLabel>
                {o.secondaryLabel ? (
                  <StyledCategoryCount>
                    {o.secondaryLabel}
                  </StyledCategoryCount>
                ) : null}
                {String(props.value) === String(o.value) ? (
                  <StyledCategoryCheck aria-hidden="true">
                    <CheckRoundedIcon />
                  </StyledCategoryCheck>
                ) : null}
              </StyledCategoryOption>
            ) : (
              o.label
            )}
          </MenuItem>
        ))}
      </MuiSelect>
      {hasError ? (
        <FormHelperText id={helperId} role="alert">
          {props.error}
        </FormHelperText>
      ) : null}
    </StyledFormControl>
  );
};
