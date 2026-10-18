/** @file star-assist.test.ts @description STAR contract, CAS, expiry, cancellation and real MSW APIs. */
import { beforeEach, afterEach, describe, expect, it } from "vitest";
import fixture from "../../contracts/star-v14-fixtures.json";
import { setupServer } from "msw/node";
import { createHandlers } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import {
  starRoute,
  startStarJob,
  fakeStarResult,
  finishStarJob,
} from "@/mocks/star";
import { sha256, canonical, contextUuid } from "@/lib/jsonHash";
import {
  targetCategories,
  emptyStarInput,
  starInputSchema,
  starResultSchema,
  starReceiptSchema,
  contextReceiptSchema,
  generationReceiptSchema,
  type StarOperation,
} from "@/lib/api/schemas/star";
import { createSession, getQuestion, submitAnswer } from "@/lib/api/interview";
import {
  executeStarOperation,
  getDrafts,
  getStarRequest,
  getGeneration,
  getQuota,
} from "@/lib/api/star";
const repository = createRepository();
const server = setupServer(...createHandlers(repository));
beforeEach(() => {
  repository.reset();
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => server.close());
const operation = (
  path: string,
  body: unknown,
  method: "POST" | "PUT" = "POST",
): StarOperation => ({
  version: 1,
  key: crypto.randomUUID(),
  path,
  body,
  method,
  contextId: null,
  editGeneration: 0,
});
async function start() {
  const created = await createSession(
    { mode: "category", category: "job_change", difficulty: "standard" },
    crypto.randomUUID(),
  );
  const session = await getQuestion(created.sessionId);
  const context = await executeStarOperation(
    operation(`/sessions/${session.sessionId}/answer-contexts`, {
      operationKind: "initial_answer",
      questionId: session.question.id,
    }),
    contextReceiptSchema,
  );
  const answer = await executeStarOperation(
    operation(`/answer-contexts/${context.contextId}/answer-drafts`, {
      answer: "",
      applicationId: null,
    }),
    starReceiptSchema,
  );
  const value = {
    ...emptyStarInput(),
    targetCategory: "corporate_sales" as const,
    notes: {
      S: "顧客に課題があった。",
      T: "改善を担当した。",
      A: "本人が課題を整理した。",
      R: "課題を共有した。",
    },
  };
  const star = await executeStarOperation(
    operation(`/answer-contexts/${context.contextId}/star-drafts`, value),
    starReceiptSchema,
  );
  return { session, context, answer, star, value };
}
describe("STAR v1.4", () => {
  it("T23 thirty actors concurrently create/save independent Mock contexts", async () => {
    const began = performance.now();
    const send = async (owner: string, path: string, body: unknown) => {
      const response = await fetch(`http://localhost/api${path}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer mock:${owner}:USER`,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify(body),
      });
      expect(response.ok).toBe(true);
      return response.json();
    };
    const values = await Promise.all(
      Array.from({ length: 30 }, async (_, i) => {
        const owner = `load-${i}`;
        const session = await send(owner, "/sessions", {
          mode: "category",
          category: "job_change",
          difficulty: "standard",
        });
        const response = await fetch(
          `http://localhost/api/sessions/${session.sessionId}/question`,
          { headers: { Authorization: `Bearer mock:${owner}:USER` } },
        );
        const current = await response.json();
        const context = await send(
          owner,
          `/sessions/${session.sessionId}/answer-contexts`,
          { operationKind: "initial_answer", questionId: current.question.id },
        );
        const draft = await send(
          owner,
          `/answer-contexts/${context.contextId}/answer-drafts`,
          { answer: `本人${i}の保存です。`, applicationId: null },
        );
        return { owner, draft };
      }),
    );
    expect(new Set(values.map((v) => v.draft.id)).size).toBe(30);
    expect(Object.keys(repository.read().star.answers)).toHaveLength(30);
    expect(Object.keys(repository.read().evaluations)).toHaveLength(0);
    expect(Object.keys(repository.read().star.quotas)).toHaveLength(0);
    console.info(
      `STAR_MOCK_30_ACTORS_MS=${Math.round(performance.now() - began)}`,
    );
  });
  it("T01 hash/UUID match Python and strict structured output", () => {
    expect(sha256("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    expect(contextUuid(fixture.uuid.name)).toBe(fixture.uuid.value);
    expect(targetCategories).toEqual(fixture.categories);
    expect(canonical(fixture.canonical.payload)).toBe(fixture.canonical.text);
    expect(sha256(fixture.canonical.text)).toBe(fixture.canonical.sha256);
    expect(starInputSchema.parse(fixture.input)).toEqual(fixture.input);
    expect(starResultSchema.parse(fixture.result)).toEqual(fixture.result);
    expect(canonical({ b: "😀", a: 1 })).toBe(
      '{"a": 1, "b": "\\ud83d\\ude00"}',
    );
    expect(
      starInputSchema.safeParse({ ...emptyStarInput(), owner: "other" })
        .success,
    ).toBe(false);
    expect(
      starResultSchema.safeParse({
        status: "ready",
        candidates: [],
        missingInformation: [],
      }).success,
    ).toBe(false);
  });
  it("T05/T06 exact receipt survives competing save and replay", async () => {
    const s = await start();
    const first = operation(
      `/answer-drafts/${s.answer.id}`,
      { answer: "最初", applicationId: null, expectedVersion: 1 },
      "PUT",
    );
    const receipt = await executeStarOperation(first, starReceiptSchema);
    await executeStarOperation(
      operation(
        first.path,
        { answer: "別タブ", applicationId: null, expectedVersion: 2 },
        "PUT",
      ),
      starReceiptSchema,
    );
    expect((await getStarRequest(first.key)).receipt).toEqual(receipt);
    expect(await executeStarOperation(first, starReceiptSchema)).toEqual(
      receipt,
    );
    expect((await getDrafts(s.context.contextId)).answerDraft?.answer).toBe(
      "別タブ",
    );
    await expect(
      executeStarOperation(
        { ...first, body: { answer: "改変", expectedVersion: 1 } },
        starReceiptSchema,
      ),
    ).rejects.toMatchObject({ status: 409 });
  });
  it("T08/T09 formal POST cancels a queued job and old saves", async () => {
    const s = await start();
    const queued = await executeStarOperation(
      operation("/star-assist/generations", {
        starDraftId: s.star.id,
        expectedVersion: 1,
      }),
      generationReceiptSchema,
    );
    await submitAnswer(
      s.session.sessionId,
      {
        kind: "initial_answer",
        questionId: s.session.question.id,
        answer: "正式回答",
      },
      crypto.randomUUID(),
    );
    expect((await getGeneration(queued.generationId)).status).toBe("CANCELLED");
    expect((await getQuota()).user.reserved).toBe(0);
    await expect(
      executeStarOperation(
        operation(
          `/answer-drafts/${s.answer.id}`,
          { answer: "古い保存", expectedVersion: 1 },
          "PUT",
        ),
        starReceiptSchema,
      ),
    ).rejects.toMatchObject({ status: 409 });
  });
  it("T02 foreign owner cannot read/write existing drafts", async () => {
    const s = await start(),
      state = repository.read();
    expect(() =>
      starRoute(
        state,
        "other",
        "GET",
        `/answer-contexts/${s.context.contextId}/drafts`,
        null,
        null,
      ),
    ).toThrow();
    expect(() =>
      starRoute(
        state,
        "other",
        "PUT",
        `/answer-drafts/${s.answer.id}`,
        { answer: "偽造", expectedVersion: 1 },
        crypto.randomUUID(),
      ),
    ).toThrow();
  });
  it("T03 expiry is checked while physical records remain", async () => {
    const s = await start(),
      state = repository.read(),
      expiry = state.star.drafts[s.star.id].value.expiresAt;
    const before = starRoute(
      state,
      "mock-user",
      "GET",
      `/answer-contexts/${s.context.contextId}/drafts`,
      null,
      null,
      expiry * 1000 - 1,
    ).body as { starDraft: unknown };
    const after = starRoute(
      state,
      "mock-user",
      "GET",
      `/answer-contexts/${s.context.contextId}/drafts`,
      null,
      null,
      expiry * 1000,
    ).body as { starDraft: unknown };
    expect(before.starDraft).not.toBeNull();
    expect(after.starDraft).toBeNull();
    expect(() =>
      starRoute(
        state,
        "mock-user",
        "PUT",
        `/star-drafts/${s.star.id}`,
        { ...s.value, expectedVersion: 1 },
        crypto.randomUUID(),
        expiry * 1000,
      ),
    ).toThrow();
  });
  it("T12 one context permits one reservation and duplicate calls consume once", async () => {
    const s = await start(),
      state = repository.read(),
      key = crypto.randomUUID(),
      body = { starDraftId: s.star.id, expectedVersion: 1 };
    const accepted = starRoute(
      state,
      "mock-user",
      "POST",
      "/star-assist/generations",
      body,
      key,
    ).body as { generationId: string };
    expect(
      starRoute(
        state,
        "mock-user",
        "POST",
        "/star-assist/generations",
        body,
        key,
      ).body,
    ).toEqual(accepted);
    expect(() =>
      starRoute(
        state,
        "mock-user",
        "POST",
        "/star-assist/generations",
        body,
        crypto.randomUUID(),
      ),
    ).toThrow();
    const lease = startStarJob(state, accepted.generationId, Date.now())!;
    expect(startStarJob(state, accepted.generationId, Date.now())).toBeNull();
    const result = fakeStarResult(lease);
    expect(result.candidates).toHaveLength(3);
    expect(result.candidates[0].text).not.toMatch(/100|売上|理念/);
    finishStarJob(state, lease, result, Date.now());
    expect(Object.values(state.star.quotas).map((q) => q.consumed)).toEqual([
      1, 1,
    ]);
  });
});
