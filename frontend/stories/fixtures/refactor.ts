/** @file refactor.ts @description 表示部品と新規Sessionに使う検証済みfixture。 */
import { bankSchema, type BankSave } from "@/lib/api/schemas";
import { questions } from "@/mocks/data/questions";
import {
  createCompletedState,
  createFeedbackFixture,
  createSessionFixture,
  storyIds,
} from "./index";
export function createBankFixture(count = 15, text?: string) {
  return bankSchema.parse({
    version: 0,
    updatedAt: null,
    questions: Array.from({ length: count }, (_, i) => ({
      ...questions[i % questions.length],
      id: `f1600000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`,
      ...(text !== undefined && i === 0 ? { question: text } : {}),
    })),
  });
}
export function createDraftFixture(count = 15, text?: string): BankSave {
  return {
    expectedVersion: 0,
    questions: (count === 0 ? [] : createBankFixture(count).questions).map(
      (q, i) => (i === 0 && text !== undefined ? { ...q, question: text } : q),
    ),
  };
}
export function createNewCompletedState(count = 15, number = 1) {
  const state = createCompletedState();
  const snapshot = questions.slice(0, count);
  const feedback = createFeedbackFixture({
    question: snapshot[number - 1],
    questionNumber: number,
  });
  state.sessions[storyIds.session] = createSessionFixture({
    ...state.sessions[storyIds.session],
    mode: count === 1 ? "category" : "full",
    totalQuestions: count,
    hasNext: number < count,
    questionNumber: number,
    question: snapshot[number - 1],
  });
  state.attempts[storyIds.currentAttempt].feedback = feedback;
  state.sessionQuestions[storyIds.session] = structuredClone(snapshot);
  state.owners[storyIds.session] = "mock-user";
  return state;
}
export const practiceOptions = {
  bankVersion: 0,
  totalQuestions: 15,
  categories: [
    { id: "self_introduction" as const, label: "自己紹介", questionCount: 1 },
    { id: "company_selection" as const, label: "企業選び", questionCount: 2 },
  ],
};
