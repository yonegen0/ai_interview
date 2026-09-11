/** @file EvaluationLoading.tsx @description 評価の長時間待機と手動確認 */
"use client";
import CircularProgress from "@mui/material/CircularProgress";
import { styled } from "@mui/material/styles";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Button } from "@/components/atoms/Button";
import { Muted } from "@/components/atoms/Muted";
const EvaluationCard = styled(MascotCoachCard)({ marginBottom: 24 });

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
    heading={<h2>回答を確認しています</h2>}
    actions={
      paused || error ? (
        <Button onClick={retry}>結果を再確認</Button>
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
        <p>自動確認を停止しました。評価が失敗したわけではありません。</p>
      )}
      {error && <p>{error.message}</p>}
    </div>
  </EvaluationCard>
);
