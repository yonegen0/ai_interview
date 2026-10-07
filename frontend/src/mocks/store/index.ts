/** @file index.ts @description BrowserとNodeで共有する検証済みMock Repository */
import { z } from "zod";
import {
  sessionSchema,
  feedbackSchema,
  evaluationSchema,
  questionSchema,
  bankSchema,
  idSchema,
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
const storeSchema = legacyStoreSchema.extend({
  version: z.literal(2),
  bank: bankSchema.default({ version: 0, updatedAt: null, questions }),
  sessionQuestions: z.record(z.string(), z.array(questionSchema)).default({}),
  owners: z.record(z.string(), z.string()).default({}),
});
export type MockState = z.infer<typeof storeSchema>;
export interface Repository {
  read(): MockState;
  write(state: MockState): void;
  reset(): void;
}
const empty = (): MockState => ({
  version: 2,
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
        const current = readSaved("pocket:mock:v2", storeSchema);
        if (current) {
          memory = current;
          if (scopeLegacyRequests(memory)) save("pocket:mock:v2", memory);
        } else {
          // Read the original without deleting it, including on migration failure.
          let raw: string | null;
          try {
            raw = sessionStorage.getItem("pocket:mock:v1");
          } catch {
            markStorageUnavailable();
            return memory;
          }
          if (raw) {
            const old = legacyStoreSchema.parse(JSON.parse(raw));
            const next = { ...empty(), ...old, version: 2 as const };
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
            memory = storeSchema.parse(next);
            scopeLegacyRequests(memory);
            save("pocket:mock:v2", memory);
          }
        }
      }
      return memory;
    },
    write(state) {
      memory = storeSchema.parse(state);
      if (browser) save("pocket:mock:v2", memory);
    },
    reset() {
      memory = empty();
      if (browser) save("pocket:mock:v2", memory);
    },
  };
}
