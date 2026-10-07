/** @file QuestionBankConflict.tsx @description Presentation and composition for QuestionBankConflict. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import type { BankSave, QuestionBank } from "@/lib/api/schemas";
export type QuestionBankConflictProps = {
  active: boolean;
  comparison: QuestionBank | null;
  questions: BankSave["questions"];
  previousDraft: BankSave | null;
  onFetchLatest: () => void;
  onAdoptLatest: () => void;
};
const QuestionTexts = ({ questions }: { questions: BankSave["questions"] }) => (
  <>
    {questions.map((q, i) => (
      <Text key={q.id}>
        {i + 1}. {q.question}
      </Text>
    ))}
  </>
);
export function QuestionBankConflict({
  active,
  comparison,
  questions,
  previousDraft,
  onFetchLatest,
  onAdoptLatest,
}: QuestionBankConflictProps) {
  return (
    <>
      {active && (
        <Panel>
          <Text variant="h2" component="h2">
            最新版との比較
          </Text>
          <Text>別の更新が保存されています。自動上書きは行いません。</Text>
          {comparison ? (
            <>
              <Text variant="h3" component="h3">
                保存済みの最新版
              </Text>
              <QuestionTexts questions={comparison.questions} />
              <Text variant="h3" component="h3">
                今回の編集内容
              </Text>
              <QuestionTexts questions={questions} />
              <Button
                variant="contained"
                color="primary"
                onClick={onAdoptLatest}
              >
                最新版で編集し直す
              </Button>
            </>
          ) : (
            <Button variant="contained" color="primary" onClick={onFetchLatest}>
              最新版を再取得
            </Button>
          )}
        </Panel>
      )}
      {previousDraft && (
        <Panel>
          <Text variant="h2" component="h2">
            変更前の編集内容（参照用）
          </Text>
          <QuestionTexts questions={previousDraft.questions} />
        </Panel>
      )}
    </>
  );
}
