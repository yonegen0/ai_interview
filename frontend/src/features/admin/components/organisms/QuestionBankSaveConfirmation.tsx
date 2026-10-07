/** @file QuestionBankSaveConfirmation.tsx @description Presentation and composition for QuestionBankSaveConfirmation. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import type { ChangeSummary } from "../../model/editor";
export type QuestionBankSaveConfirmationProps = {
  count: number;
  summary: ChangeSummary;
  saving?: boolean;
  onPublish: () => void;
  onBack: () => void;
};
export const QuestionBankSaveConfirmation = ({
  count,
  summary,
  saving,
  onPublish,
  onBack,
}: QuestionBankSaveConfirmationProps) => (
  <Panel>
    <Text variant="h2" component="h2">
      保存内容の確認
    </Text>
    <Text>
      {count}問 · 追加{summary.added}件／削除{summary.removed}
      件／本文・カテゴリ変更{summary.edited}件／順番変更{summary.moved}件
    </Text>
    <Actions>
      <Button
        variant="contained"
        color="primary"
        type="button"
        disabled={saving}
        onClick={onPublish}
      >
        保存して反映
      </Button>
      <Button
        variant="outlined"
        color="primary"
        type="button"
        disabled={saving}
        onClick={onBack}
      >
        編集に戻る
      </Button>
    </Actions>
  </Panel>
);
