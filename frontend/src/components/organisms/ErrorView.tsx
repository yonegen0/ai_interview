/** @file ErrorView.tsx @description 利用者向けのエラーと復帰導線 */
"use client";
import { darken, styled } from "@mui/material/styles";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
const ErrorMessage = styled("p")(({ theme }) => ({
  // AppShellの背景グラデーション上でも4.5:1以上のコントラストを保つ。
  color: darken(theme.palette.error.dark, 0.1),
  whiteSpace: "pre-wrap",
}));
const ErrorCard = styled(MascotCoachCard)({ marginBlock: 16 });
const ErrorHeading = styled("h2")(({ theme }) => ({
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
    heading={<ErrorHeading>確認が必要です</ErrorHeading>}
    actions={
      <>
        {retry && <Button onClick={retry}>もう一度確認する</Button>}
        <Link href="/practice/">練習を始める画面へ</Link>
      </>
    }
  >
    <ErrorMessage role="alert">{error.message}</ErrorMessage>
  </ErrorCard>
);
