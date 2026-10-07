/** @file index.ts @description BrowserとNodeで共有する検証済みMock Repository */
import { z } from "zod";
import {
  sessionSchema,
  feedbackSchema,
  evaluationSchema,
  questionSchema,
  bankSchema,
  idSchema,
  activeCoachingSchema,
  coachingAnswerSchema,
  coachingHistoryItemSchema,
} from "@/lib/api/schemas";
import { readSaved, save } from "@/lib/storage/recovery";
import { questions, legacyQuestions } from "../data/questions";
import { markStorageUnavailable } from "@/lib/storage/status";
const legacyStoreSchema = z.object({
  version: z.literal(1),
  sessions: z.record(z.string(), sessionSchema),
  attempts: z.record(
    z.string(),
    z.object({
      feedback: feedbackSchema,
      evaluation: evaluationSchema,
      polls: z.number(),
      startedAt: z.number(),
    }),
  ),
  requests: z.record(
    z.string(),
    z.object({
      fingerprint: z.string(),
      status: z.number(),
      body: z.unknown(),
    }),
  ),
  consumed: z.array(z.string()),
});
const v2StoreSchema = legacyStoreSchema.extend({
  version: z.literal(2),
  bank: bankSchema.default({ version: 0, updatedAt: null, questions }),
  sessionQuestions: z.record(z.string(), z.array(questionSchema)).default({}),
  owners: z.record(z.string(), z.string()).default({}),
});
export const mockInputSchema = z.object({
  initialAnswer: coachingAnswerSchema,
  history: z.array(coachingHistoryItemSchema).max(3),
  count: z.number().int().min(0).max(3),
  unavailableQuestions: z.array(z.string()),
});
const evaluationRecordSchema = z.object({
  feedback: feedbackSchema,
  evaluation: evaluationSchema,
  polls: z.number(),
  startedAt: z.number(),
  input: mockInputSchema.optional(),
});
const storeSchema = v2StoreSchema
  .extend({
    version: z.literal(3),
    attempts: z.record(
      z.string(),
      evaluationRecordSchema
        .omit({ input: true })
        .extend({ initialEvaluationId: idSchema.optional() }),
    ),
    evaluations: z.record(z.string(), evaluationRecordSchema).default({}),
    coachings: z.record(z.string(), activeCoachingSchema).default({}),
  })
  .superRefine((state, ctx) => {
    for (const [id, attempt] of Object.entries(state.attempts)) {
      if (
        "feedbackVersion" in attempt.feedback &&
        (!state.coachings[id] ||
          !attempt.initialEvaluationId ||
          !state.evaluations[attempt.initialEvaluationId])
      )
        ctx.addIssue({
          code: "custom",
          message: "Mock initial evaluation relation is invalid.",
        });
    }
    for (const [id, record] of Object.entries(state.evaluations)) {
      if (
        "feedbackVersion" in record.feedback &&
        (record.feedback.evaluationId !== id ||
          record.evaluation.evaluationId !== id ||
          !record.input ||
          !state.attempts[record.evaluation.attemptId] ||
          !state.coachings[record.evaluation.attemptId])
      )
        ctx.addIssue({
          code: "custom",
          message: "Mock evaluation relation is invalid.",
        });
    }
    for (const [id, head] of Object.entries(state.coachings)) {
      const record = state.evaluations[head.evaluationId];
      const input = record?.input;
      if (
        head.attemptId !== id ||
        !state.attempts[id] ||
        !record ||
        !input ||
        record.evaluation.attemptId !== id ||
        !("feedbackVersion" in record.feedback) ||
        input.count !== input.history.length ||
        input.count !== head.coachingCount ||
        JSON.stringify(input.history) !==
          JSON.stringify(head.coachingHistory) ||
        head.initialAnswer !== input.initialAnswer ||
        record.evaluation.status !==
          (head.stage === "evaluating"
            ? "processing"
            : head.stage === "failed"
              ? "failed"
              : "completed")
      )
        ctx.addIssue({
          code: "custom",
          message: "Mock coaching relation is invalid.",
        });
    }
    for (const session of Object.values(state.sessions)) {
      const head = session.activeCoaching;
      if (
        head &&
        (JSON.stringify(head) !==
          JSON.stringify(state.coachings[head.attemptId]) ||
          session.activeAttempt?.attemptId !== head.attemptId ||
          session.activeAttempt.evaluationId !== head.evaluationId)
      )
        ctx.addIssue({
          code: "custom",
          message: "Mock active pointer is invalid.",
        });
    }
  });
export type MockInput = z.infer<typeof mockInputSchema>;
export type MockState = z.infer<typeof storeSchema>;
export interface Repository {
  read(): MockState;
  write(state: MockState): void;
  reset(): void;
}
const empty = (): MockState => ({
  version: 3,
  evaluations: {},
  coachings: {},
  bank: { version: 0, updatedAt: null, questions: structuredClone(questions) },
  sessionQuestions: {},
  owners: {},
  sessions: {},
  attempts: {},
  requests: {},
  consumed: [],
});
/** Preserve legacy receipts, including v2 stores copied before keys were scoped. */
function scopeLegacyRequests(state: MockState) {
  let changed = false;
  for (const [key, reply] of Object.entries(state.requests)) {
    const target = `mock-user:${key}`;
    if (
      idSchema.safeParse(key).success &&
      !Object.hasOwn(state.requests, target)
    ) {
      state.requests[target] = structuredClone(reply);
      changed = true;
    }
  }
  return changed;
}
export function createRepository(browser = false): Repository {
  let memory = empty();
  return {
    read() {
      if (browser) {
        const current = readSaved(
          "pocket:mock:v3",
          storeSchema,
          undefined,
          true,
        );
        if (current) {
          memory = current;
          if (scopeLegacyRequests(memory)) save("pocket:mock:v3", memory);
        } else {
          // Read the original without deleting it, including on migration failure.
          let raw: string | null;
          try {
            if (sessionStorage.getItem("pocket:mock:v3") !== null)
              throw new Error(
                "体験版データを復元できませんでした。元のデータは保持しています。",
              );
            raw =
              sessionStorage.getItem("pocket:mock:v2") ??
              sessionStorage.getItem("pocket:mock:v1");
          } catch (cause) {
            if (
              cause instanceof Error &&
              cause.message.includes("復元できません")
            )
              throw cause;
            markStorageUnavailable();
            return memory;
          }
          if (raw) {
            const decoded: unknown = JSON.parse(raw);
            const oldV2 = v2StoreSchema.safeParse(decoded);
            const old = oldV2.success
              ? oldV2.data
              : legacyStoreSchema.parse(decoded);
            const next = { ...empty(), ...old, version: 3 as const };
            if (!oldV2.success)
              for (const [id, session] of Object.entries(old.sessions)) {
                const pool = legacyQuestions.filter(
                  (q) => q.category === session.question.category,
                );
                if (
                  !pool.length ||
                  JSON.stringify(
                    pool[(session.questionNumber - 1) % pool.length],
                  ) !== JSON.stringify(session.question)
                )
                  throw new Error(
                    "以前の体験版データを復元できませんでした。元のデータは保持しています。",
                  );
                next.sessionQuestions[id] = structuredClone(pool);
                next.owners[id] = "mock-user";
              }
            for (const record of Object.values(next.attempts)) {
              next.evaluations[record.evaluation.evaluationId] =
                structuredClone(record);
            }
            memory = storeSchema.parse(next);
            scopeLegacyRequests(memory);
            save("pocket:mock:v3", memory);
          }
        }
      }
      return memory;
    },
    write(state) {
      memory = storeSchema.parse(state);
      if (browser) save("pocket:mock:v3", memory);
    },
    reset() {
      memory = empty();
      if (browser) save("pocket:mock:v3", memory);
    },
  };
}
