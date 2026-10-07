/** @file textLimits.ts @description Versioned, non-mutating Unicode text counters. */
export const QUESTION_MAX_LENGTH = 200;
export const COACHING_ANSWER_MAX_LENGTH = 400;
export const countCodePoints = (value: string) => Array.from(value).length;
export const countLegacyAnswerUnits = (value: string) => value.length;
export function scoreValues(
  answer: string,
  conclusion: number,
  specificity: number,
  reasoning: number,
) {
  const answerLength = countCodePoints(answer);
  const lengthPenalty =
    answerLength <= 300
      ? 0
      : answerLength <= 350
        ? 1
        : answerLength <= 400
          ? 2
          : 3;
  const baseScore = conclusion + specificity + reasoning;
  const totalScore = Math.max(0, baseScore - lengthPenalty);
  return {
    answerLength,
    lengthPenalty,
    baseScore,
    totalScore,
    rank:
      totalScore >= 26
        ? ("S" as const)
        : totalScore >= 21
          ? ("A" as const)
          : totalScore >= 15
            ? ("B" as const)
            : ("C" as const),
  };
}
