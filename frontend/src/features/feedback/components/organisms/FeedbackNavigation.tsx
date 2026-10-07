/** @file FeedbackNavigation.tsx @description Presentation and composition for FeedbackNavigation. */
"use client";
import { Text } from "@/components/atoms/Text";
import { Link } from "@/components/atoms/Link";
import { Button } from "@/components/atoms/Button";
import { Actions } from "@/components/atoms/Actions";
import { ErrorView } from "@/components/organisms/ErrorView";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import type {
  FeedbackNavigationView,
  FeedbackNavigationActions,
} from "../../model/navigation";
export type FeedbackNavigationProps = {
  view: FeedbackNavigationView;
  actions: FeedbackNavigationActions;
};
export const FeedbackNavigation = ({
  view,
  actions,
}: FeedbackNavigationProps) => (
  <>
    {view.loading ? (
      <Text role="status">現在の練習を確認しています…</Text>
    ) : view.error ? (
      <ErrorView error={view.error} retry={actions.refresh} />
    ) : (
      <>
        {view.canRetry ? (
          <MascotCoachCard
            variant="retry"
            heading={
              <Text variant="h2" component="h2">
                {view.hasNext
                  ? "次の練習へ"
                  : `全${view.total}問の練習が完了しました`}
              </Text>
            }
            actions={
              <>
                <Link href={view.retryUrl}>同じ質問に再挑戦</Link>
                {view.hasNext && (
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={() => void actions.next()}
                  >
                    次の質問へ
                  </Button>
                )}
              </>
            }
          >
            <Text>
              {view.hasNext
                ? "改善ポイントを意識して同じ質問に再挑戦するか、次の質問へ進みましょう。"
                : "最後の質問に再挑戦するか、新しい練習を始められます。"}
            </Text>
          </MascotCoachCard>
        ) : (
          <Actions>
            {view.canNext ? (
              <Button
                variant="contained"
                color="primary"
                onClick={() => void actions.next()}
                disabled={view.pending}
              >
                {view.pending
                  ? "次の質問を準備しています…"
                  : view.recovering
                    ? "次の質問の取得結果を再確認"
                    : "次の質問へ"}
              </Button>
            ) : (
              <Link href={view.sessionUrl}>現在の練習へ戻る</Link>
            )}
          </Actions>
        )}
        <Actions>
          <Link href="/practice/">新しい練習を始める</Link>
          <Link href="/">練習を終了</Link>
        </Actions>
      </>
    )}
    {view.mutationError && <ErrorView error={view.mutationError} />}
  </>
);
