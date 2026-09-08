/**
 * @file Select.tsx
 * @description 全画面で利用する共通セレクトコンポーネント（FormControl + ラベル + 選択肢 + エラーを内包）
 */
"use client";

import { useId } from "react";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import MuiSelect from "@mui/material/Select";
import type { ReactNode } from "react";
import type { SelectChangeEvent } from "@mui/material/Select";
import { alpha, styled } from "@mui/material/styles";

/** 選択肢 1 件 */
export type SelectOption<T extends string | number> = {
  /** 選択値 */
  value: T;
  /** 表示ラベル */
  label: ReactNode;
};

/** 共通 Select の Props */
export type SelectProps<T extends string | number> = {
  /** フィールドラベル（InputLabel に表示） */
  label: string;
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
  "& .MuiOutlinedInput-root": {
    borderRadius: "12px",
    backgroundColor: alpha(theme.palette.common.white, 0.9),
    backdropFilter: "blur(10px)",
    transition: theme.transitions.create(
      ["background-color", "box-shadow", "border-color"],
      { duration: 300 },
    ),
    "& fieldset": {
      borderColor: theme.palette.grey[300],
    },
    "&:hover fieldset": {
      borderColor: theme.palette.grey[400],
    },
    "&.Mui-focused": {
      backgroundColor: theme.palette.common.white,
      boxShadow:
        `0 0 15px ${alpha(theme.palette.primary.main, 0.3)}, ` +
        `inset 0 0 10px ${alpha(theme.palette.primary.main, 0.1)}`,
      "& fieldset": {
        borderWidth: "1px",
        borderColor: theme.palette.primary.main,
      },
    },
  },
  "& .MuiInputLabel-root": {
    fontWeight: 600,
    color: theme.palette.text.secondary,
    "&.Mui-focused": {
      color: theme.palette.primary.main,
      textShadow: `0 0 5px ${theme.palette.primary.main}`,
    },
  },
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
  "& .MuiFormHelperText-root": {
    marginTop: "8px",
    lineHeight: 1.4,
  },
}));

/** ドロップダウンの glass パネル（Panel.tsx のレシピ準拠） */
const StyledMenuPaper = styled(Paper)(({ theme }) => ({
  // Popover 既定 paper（slots.paper 差し替えで失われる）位置決め・スクロールの土台を再付与
  position: "absolute",
  overflowX: "hidden",
  overflowY: "auto",
  maxHeight: "calc(100% - 32px)",
  // ---- 以下 glass 装飾 ----
  borderRadius: 14,
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
    borderRadius: 8,
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

/**
 * 共通セレクトコンポーネントを表示する
 * @param props 表示に必要なプロパティ
 * @returns 共通 Select UI
 */
export const Select = <T extends string | number>(props: SelectProps<T>) => {
  const labelId = useId();
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
        labelId={labelId}
        label={props.label}
        value={props.value}
        onChange={handleChange}
        MenuProps={{ slots: { paper: StyledMenuPaper } }}
      >
        {props.options.map((o) => (
          <MenuItem key={String(o.value)} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </MuiSelect>
      {hasError ? <FormHelperText>{props.error}</FormHelperText> : null}
    </StyledFormControl>
  );
};
