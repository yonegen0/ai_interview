/** @file QuestionBankPreview.tsx @description Presentation and composition for QuestionBankPreview. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
import { categories, type BankSave } from "@/lib/api/schemas";
export const QuestionBankPreview = ({
  questions,
}: {
  questions: BankSave["questions"];
}) => (
  <Panel>
    <Text variant="h2" component="h2">
      プレビュー
    </Text>
    {questions.map((q, i) => (
      <div key={q.id}>
        <Text variant="h3" component="h3">
          質問 {i + 1} · {categories[q.category]}
        </Text>
        <Text>{q.question}</Text>
      </div>
    ))}
  </Panel>
);
