/** @file practiceProgress.ts @description 実APIと同じ質問ID集合方式のMock進捗。 */
import type { MockState } from "./store";
import { isFeedbackV2 } from "@/lib/api/schemas";

export function mockPracticeProgress(state: MockState, owner: string) {
  const ids = new Set(state.bank.questions.map((q) => q.id));
  const completed = new Set<string>();
  for (const [attemptId, attempt] of Object.entries(state.attempts)) {
    const feedback = attempt.feedback;
    if ((state.owners[feedback.sessionId] ?? "mock-user") !== owner) continue;
    if (!ids.has(feedback.question.id)) continue;
    if (isFeedbackV2(feedback)) {
      const original = state.evaluations[attempt.initialEvaluationId ?? ""];
      if (original?.evaluation.status === "completed" &&
          original.evaluation.attemptId === attemptId) {
        completed.add(feedback.question.id);
      }
      for (const record of Object.values(state.evaluations)) {
        if (record.evaluation.attemptId === attemptId &&
            record.evaluation.status === "completed" &&
            record.input?.count === 0 &&
            isFeedbackV2(record.feedback)) {
          completed.add(feedback.question.id);
        }
      }
    } else {
      const record = state.evaluations[attempt.evaluation.evaluationId] ?? attempt;
      if (record.evaluation.status === "completed") completed.add(feedback.question.id);
    }
  }
  return {
    bankVersion: state.bank.version,
    totalQuestions: ids.size,
    completedQuestions: completed.size,
  };
}
