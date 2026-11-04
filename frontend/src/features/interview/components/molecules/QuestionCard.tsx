/** @file QuestionCard.tsx @description 質問をPropsだけで表示する */
import { categories, type Question } from "@/lib/api/schemas";
import { Muted } from "@/components/atoms/Muted";
import { Panel } from "@/components/atoms/Panel";
import { Text } from "@/components/atoms/Text";
export const QuestionCard = ({
  question,
  number,
  total,
}: {
  question: Question;
  number: number;
  total?: number;
}) => (
  <Panel aria-label={`面接の質問 ${number}：${categories[question.category]}`}>
    <Muted>
      QUESTION {String(number).padStart(2, "0")} ·{" "}
      {categories[question.category]}
      {total && (
        <>
          {" "}
          · {number} / {total}問
        </>
      )}
    </Muted>
    <Text variant="h2" component="h2">{question.question}</Text>
  </Panel>
);
