/** @file backend-contract.test.ts @description Backend共通fixtureを既存ZodとMSW質問で検証 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  attemptSchema, createSchema, createdSchema, errorSchema, evaluationSchema,
  feedbackSchema, nextSchema, sessionSchema, submitSchema,
} from "@/lib/api/schemas";
import { questions } from "@/mocks/data/questions";

const schemas = {
  attempt: attemptSchema, create: createSchema, created: createdSchema,
  error: errorSchema, evaluation: evaluationSchema, feedback: feedbackSchema,
  next: nextSchema, session: sessionSchema, submit: submitSchema,
};
type SchemaName = keyof typeof schemas;
const fixtures = JSON.parse(readFileSync(
  path.resolve("../contracts/backend-fixtures.json"), "utf8",
)) as {
  steps: Array<{ schema?: SchemaName; body?: unknown }>;
  cases: Array<{ schema: SchemaName; value: unknown; valid: boolean; label: string }>;
  scoreCases: Array<{ scoreJson: string; valid: boolean; label: string }>;
};

describe("Backend shared contract", () => {
  for (const fixture of fixtures.scoreCases) {
    it(`score JSON: ${fixture.label}`, () => {
      const base = fixtures.cases.find((item) => item.schema === "feedback")!.value;
      expect(feedbackSchema.safeParse({
        ...(base as Record<string, unknown>),
        score: JSON.parse(fixture.scoreJson),
      }).success).toBe(fixture.valid);
    });
  }
  for (const [index, step] of fixtures.steps.entries()) {
    if (!step.schema) continue;
    const schema = schemas[step.schema];
    it(`accepts handler response ${index}`, () => {
      expect(schema.safeParse(step.body).success).toBe(true);
    });
  }
  for (const fixture of fixtures.cases) {
    it(`${fixture.schema}: ${fixture.label}`, () => {
      expect(schemas[fixture.schema].safeParse(fixture.value).success).toBe(fixture.valid);
    });
  }
  it("preserves all 21 question IDs, texts, categories and order", () => {
    const bank: unknown = JSON.parse(readFileSync(
      path.resolve("../backend/src/interview_backend/assets/questions.json"), "utf8",
    ));
    expect(bank).toEqual(questions);
    expect(questions).toHaveLength(21);
  });
});
