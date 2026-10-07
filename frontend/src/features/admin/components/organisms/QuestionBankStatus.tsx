/** @file QuestionBankStatus.tsx @description Presentation and composition for QuestionBankStatus. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import { ErrorView } from "@/components/organisms/ErrorView";
import type { Stage } from "../../model/editor";
export type QuestionBankStatusProps = {
  loading: boolean;
  stage: Stage;
  error: Error | null;
  message: string;
  onRefresh: () => void;
  onReconfirm: () => void;
};
export const QuestionBankStatus = ({
  loading,
  stage,
  error,
  message,
  onRefresh,
  onReconfirm,
}: QuestionBankStatusProps) => (
  <>
    {loading && <Text role="status">質問一覧を読み込んでいます…</Text>}
    {message && <Text role="status">{message}</Text>}
    {error && <ErrorView error={error} retry={onRefresh} />}{" "}
    {stage === "saving" && <Text role="status">質問一覧を保存しています…</Text>}
    {stage === "forbidden" && (
      <Text role="alert">この操作を行う権限がありません。</Text>
    )}
    {stage === "uncertain" && (
      <Panel>
        <Text role="alert">
          保存結果を確認できませんでした。同じ内容の保存結果を再確認してください。
        </Text>
        <Button variant="contained" color="primary" onClick={onReconfirm}>
          保存結果を再確認
        </Button>
      </Panel>
    )}
  </>
);
