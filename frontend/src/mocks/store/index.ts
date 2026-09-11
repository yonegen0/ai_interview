/** @file index.ts @description BrowserとNodeで共有する検証済みMock Repository */
import { z } from "zod";
import {
  sessionSchema,
  feedbackSchema,
  evaluationSchema,
} from "@/lib/api/schemas";
import { readSaved, save } from "@/lib/storage/recovery";
const storeSchema = z.object({
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
export type MockState = z.infer<typeof storeSchema>;
export interface Repository {
  read(): MockState;
  write(state: MockState): void;
  reset(): void;
}
const empty = (): MockState => ({
  version: 1,
  sessions: {},
  attempts: {},
  requests: {},
  consumed: [],
});
export function createRepository(browser = false): Repository {
  let memory = empty();
  return {
    read() {
      if (browser) memory = readSaved("pocket:mock:v1", storeSchema) ?? memory;
      return memory;
    },
    write(state) {
      memory = storeSchema.parse(state);
      if (browser) save("pocket:mock:v1", memory);
    },
    reset() {
      memory = empty();
      if (browser) save("pocket:mock:v1", memory);
    },
  };
}
