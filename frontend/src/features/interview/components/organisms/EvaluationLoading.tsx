/** @file EvaluationLoading.tsx @description 評価の長時間待機と手動確認 */
"use client";
import CircularProgress from "@mui/material/CircularProgress";
import { styled } from "@mui/material/styles";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import { Muted } from "@/components/atoms/Muted";
const EvaluationCard = styled(MascotCoachCard)(({ theme }) => ({
  marginBottom: theme.spacing(3),
}));

export const EvaluationLoading = ({
  elapsed,
  paused,
  error,
  retry,
  longWaitSeconds = 30,
}: {
  elapsed: number;
  paused: boolean;
  error?: Error | null;
  retry: () => void;
  longWaitSeconds?: number;
}) => (
  <EvaluationCard
    variant="thinking"
    heading={
      <Text variant="h2" component="h2">
        回答を確認しています
      </Text>
    }
    actions={
      paused || error ? (
        <Button variant="contained" color="primary" onClick={retry}>
          結果を再確認
        </Button>
      ) : undefined
    }
  >
    <div role="status" aria-live="polite">
      {!paused && <CircularProgress size={24} aria-label="評価処理中" />}
      <Muted>
        {elapsed >= longWaitSeconds
          ? "通常より時間がかかっています。回答は送信済みです。"
          : "あなたの回答をもとにフィードバックを作成しています。"}
      </Muted>
      {paused && (
        <Text>自動確認を停止しました。評価が失敗したわけではありません。</Text>
      )}
      {error && <Text>{error.message}</Text>}
    </div>
  </EvaluationCard>
);
