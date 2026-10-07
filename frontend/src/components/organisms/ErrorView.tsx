/** @file ErrorView.tsx @description 利用者向けのエラーと復帰導線 */
"use client";
import { darken, styled } from "@mui/material/styles";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
const ErrorMessage = styled("p")(({ theme }) => ({
  // AppShellの背景グラデーション上でも4.5:1以上のコントラストを保つ。
  color: darken(theme.palette.error.dark, 0.1),
  whiteSpace: "pre-wrap",
}));
const ErrorCard = styled(MascotCoachCard)(({ theme }) => ({
  marginBlock: theme.spacing(2),
}));
const ErrorHeading = styled(Text)(({ theme }) => ({
  color: theme.palette.error.main,
}));

export const ErrorView = ({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) => (
  <ErrorCard
    variant="error"
    tone="error"
    heading={
      <ErrorHeading variant="h2" component="h2">
        確認が必要です
      </ErrorHeading>
    }
    actions={
      <>
        {retry && (
          <Button variant="contained" color="primary" onClick={retry}>
            もう一度確認する
          </Button>
        )}
        <Link href="/practice/">練習を始める画面へ</Link>
      </>
    }
  >
    <ErrorMessage role="alert">{error.message}</ErrorMessage>
  </ErrorCard>
);
