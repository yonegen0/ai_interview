/**
 * @file Input.tsx
 * @description 全画面で利用する共通入力コンポーネント
 */
"use client";

import { TextField } from "@mui/material";
import type { TextFieldProps } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";

/** 共通InputのProps */
export type InputProps = TextFieldProps;

/** 共通入力UI */
const StyledInput = styled(TextField)(({ theme }) => {
  return {
    width: "100%",
    "& .MuiOutlinedInput-root": {
      borderRadius: "12px",
      backgroundColor: alpha(theme.palette.common.white, 0.9),
      backdropFilter: "blur(10px)",
      transition: theme.transitions.create(["background-color", "box-shadow", "border-color"], {
        duration: 300,
      }),
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
    "& .MuiInputBase-input": {
      color: theme.palette.text.primary,
    },
    "& .MuiFormHelperText-root": {
      marginTop: "8px",
      lineHeight: 1.4,
    },
  };
});

/**
 * 共通入力コンポーネントを表示する
 * @param props 表示に必要なプロパティ
 * @returns 共通入力UI
 */
export const Input = (props: InputProps) => {
  return <StyledInput {...props} />;
};
