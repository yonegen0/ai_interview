/** @file QuestionCard.tsx @description 質問をPropsだけで表示する */
import { categories, type Question } from "@/lib/api/schemas";
import { Muted } from "@/components/atoms/Muted";
import { Panel } from "@/components/atoms/Panel";
export const QuestionCard = ({
  question,
  number,
}: {
  question: Question;
  number: number;
}) => (
    <Panel aria-label={`面接の質問 ${number}：${categories[question.category]}`}>
    <Muted>
      QUESTION {String(number).padStart(2, "0")} ·{" "}
      {categories[question.category]}
    </Muted>
    <h2>{question.question}</h2>
  </Panel>
);
