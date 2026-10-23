/** @file star.ts @description Pure STAR server transactions for shared Mock V4. */
import { z } from "zod";
import {
  targetCategories,
  preferencesSchema,
  preferencesRequestSchema,
  contextRequestSchema,
  starInputSchema,
  answerValueSchema,
  answerUpdateSchema,
  starUpdateSchema,
  generationRequestSchema,
  applyRequestSchema,
  answerDraftSchema,
  starDraftSchema,
  starResultSchema,
  generationSchema,
  starReceiptSchema,
  starValue,
} from "@/lib/api/schemas/star";
import { idSchema, type Answer } from "@/lib/api/schemas";
import { MockConflict } from "./coaching";
import type { MockState } from "./store";
import { canonical, contextUuid, sha256 } from "./starHash";
const DAY = 86400;
const contextSchema = z.object({
  id: idSchema,
  owner: z.string(),
  sessionId: idSchema,
  questionId: idSchema,
  questionNumber: z.number().int(),
  questionHash: z.string(),
  question: z.string(),
  operationKind: z.enum(["initial_answer", "coaching_answer", "retry_attempt"]),
  fromAttemptId: idSchema.nullable(),
  fromEvaluationId: idSchema.nullable(),
  status: z.enum(["ACTIVE", "COMPLETED"]),
  answerDraftId: idSchema.nullable(),
  starDraftId: idSchema.nullable(),
  activeGenerationId: idSchema.nullable(),
});
const generationRecord = generationSchema.extend({
  owner: z.string(),
  contextId: idSchema,
  starDraftId: idSchema,
  input: starInputSchema,
  question: z.string(),
  month: z.string(),
  quotaState: z.enum(["reserved", "consumed", "released"]),
  callStarted: z.boolean(),
  deadlineAt: z.number(),
  leaseUntil: z.number().nullable(),
  executionId: idSchema.nullable(),
  expiresAt: z.number().nullable(),
});
const applicationSchema = z.object({
  id: idSchema,
  owner: z.string(),
  contextId: idSchema,
  answerDraftId: idSchema,
  generationId: idSchema,
  candidateId: z.enum(["A", "B", "C"]),
  answerHash: z.string(),
  expiresAt: z.number(),
});
export const starStateSchema = z.object({
  preferences: z.record(z.string(), preferencesSchema),
  contexts: z.record(z.string(), contextSchema),
  answers: z.record(
    z.string(),
    z.object({
      owner: z.string(),
      contextId: idSchema,
      status: z.enum(["ACTIVE", "COMPLETED", "DISCARDED"]),
      value: answerDraftSchema,
    }),
  ),
  drafts: z.record(
    z.string(),
    z.object({
      owner: z.string(),
      contextId: idSchema,
      status: z.enum(["ACTIVE", "COMPLETED", "DISCARDED"]),
      value: starDraftSchema,
    }),
  ),
  generations: z.record(z.string(), generationRecord),
  applications: z.record(z.string(), applicationSchema),
  requests: z.record(
    z.string(),
    z.object({
      requestHash: z.string(),
      method: z.string(),
      path: z.string(),
      status: z.number(),
      receipt: z.record(z.string(), z.unknown()),
    }),
  ),
  quotas: z.record(
    z.string(),
    z.object({
      reserved: z.number().int().nonnegative(),
      consumed: z.number().int().nonnegative(),
    }),
  ),
  assists: z.record(
    z.string(),
    z.object({
      applicationId: idSchema,
      generationId: idSchema,
      finalHash: z.string(),
      edited: z.boolean(),
    }),
  ),
});
export type StarState = z.infer<typeof starStateSchema>;
type Context = z.infer<typeof contextSchema>;
type Job = z.infer<typeof generationRecord>;
export const emptyStarState = (): StarState => ({
  preferences: {},
  contexts: {},
  answers: {},
  drafts: {},
  generations: {},
  applications: {},
  requests: {},
  quotas: {},
  assists: {},
});
const fail = (code: string, status = 409): never => {
  throw new MockConflict(code, status);
};
const expired = (expiry: number | null, now: number) =>
  expiry !== null && expiry <= Math.floor(now / 1000);
const meta = (now: number, days: number) => ({
  id: crypto.randomUUID(),
  version: 1,
  updatedAt: now,
  expiresAt: Math.floor(now / 1000) + days * DAY,
});
const receipt = (v: z.infer<typeof starReceiptSchema>) =>
  starReceiptSchema.parse({
    id: v.id,
    version: v.version,
    updatedAt: v.updatedAt,
    expiresAt: v.expiresAt,
  });
export const jstMonth = (now: number) =>
  new Date(now + 9 * 3600000).toISOString().slice(0, 7);
const own = <T extends { owner: string }>(
  v: T | undefined,
  owner: string,
  code: string,
): T => {
  if (!v || v.owner !== owner) return fail(code, 404);
  return v;
};
function contextFor(
  state: MockState,
  owner: string,
  sessionId: string,
  input: z.infer<typeof contextRequestSchema>,
): Context {
  const session = state.sessions[sessionId];
  if (!session || (state.owners[sessionId] || "mock-user") !== owner)
    return fail("SESSION_NOT_FOUND", 404);
  const active = session.activeAttempt,
    progress = session.activeCoaching;
  if (session.question.id !== input.questionId)
    return fail("SESSION_STATE_CONFLICT");
  if (input.operationKind === "initial_answer") {
    if (active && (progress || active.status !== "failed"))
      return fail("SESSION_STATE_CONFLICT");
  } else {
    if (
      !active ||
      input.fromAttemptId !== active.attemptId ||
      input.fromEvaluationId !== active.evaluationId
    )
      return fail("SESSION_STATE_CONFLICT");
    if (
      input.operationKind === "retry_attempt"
        ? active.status !== "completed" ||
          (progress && progress.stage !== "completed")
        : progress?.stage !== "awaiting_answer"
    )
      return fail("SESSION_STATE_CONFLICT");
  }
  const spec = {
    owner,
    session_id: sessionId,
    question_number: session.questionNumber,
    question_id: session.question.id,
    question_hash: sha256(canonical(session.question)),
    question:
      input.operationKind === "coaching_answer"
        ? progress!.followUpQuestion!
        : session.question.question,
    operation_kind: input.operationKind,
    from_attempt_id: active?.attemptId ?? null,
    from_evaluation_id: active?.evaluationId ?? null,
  };
  return {
    id: contextUuid(sha256(canonical(spec))),
    owner,
    sessionId,
    questionId: session.question.id,
    questionNumber: session.questionNumber,
    questionHash: spec.question_hash,
    question: spec.question,
    operationKind: input.operationKind,
    fromAttemptId: spec.from_attempt_id,
    fromEvaluationId: spec.from_evaluation_id,
    status: "ACTIVE",
    answerDraftId: null,
    starDraftId: null,
    activeGenerationId: null,
  };
}
function activeContext(state: MockState, owner: string, id: string): Context {
  const context = own(state.star.contexts[id], owner, "STAR_CONTEXT_NOT_FOUND");
  if (context.status !== "ACTIVE") return fail("DRAFT_CLOSED");
  const current = contextFor(state, owner, context.sessionId, {
    operationKind: context.operationKind,
    questionId: context.questionId,
    ...(context.operationKind === "initial_answer"
      ? {}
      : {
          fromAttemptId: context.fromAttemptId,
          fromEvaluationId: context.fromEvaluationId,
        }),
  });
  if (current.id !== id) return fail("SESSION_STATE_CONFLICT");
  return context;
}
function draft(
  state: MockState,
  owner: string,
  id: string,
  star: boolean,
  now: number,
) {
  const row = own(
    star ? state.star.drafts[id] : state.star.answers[id],
    owner,
    "STAR_DRAFT_NOT_FOUND",
  );
  const context = activeContext(state, owner, row.contextId);
  if (
    row.status !== "ACTIVE" ||
    expired(row.value.expiresAt, now) ||
    (star ? context.starDraftId : context.answerDraftId) !== id
  )
    return fail("DRAFT_CLOSED");
  return { row, context };
}
const quota = (star: StarState, key: string) =>
  (star.quotas[key] ??= { reserved: 0, consumed: 0 });
function terminal(
  state: MockState,
  job: Job,
  status: Job["status"],
  now: number,
) {
  if (job.expiresAt !== null) return;
  if (job.quotaState === "reserved") {
    for (const key of [`u:${job.owner}:${job.month}`, `g:${job.month}`]) {
      const q = quota(state.star, key);
      if (q.reserved < 1) throw new Error("QuotaUnderflow");
      q.reserved--;
    }
    job.quotaState = "released";
  }
  job.status = status;
  job.leaseUntil = null;
  job.executionId = null;
  job.expiresAt = Math.floor(now / 1000) + 7 * DAY;
  const context = state.star.contexts[job.contextId];
  if (context?.activeGenerationId === job.generationId)
    context.activeGenerationId = null;
}
function cancel(state: MockState, context: Context, now: number) {
  const job = context.activeGenerationId
    ? state.star.generations[context.activeGenerationId]
    : undefined;
  if (job && !job.callStarted) terminal(state, job, "CANCELLED", now);
}
export function closeStarAnswer(
  state: MockState,
  before: MockState,
  owner: string,
  sessionId: string,
  body: Answer,
  evaluationId: string,
  applicationId: string | null,
  now: number,
) {
  if (body.kind === "retry_evaluation") return;
  let context: Context;
  try {
    context = contextFor(before, owner, sessionId, {
      operationKind: body.kind ?? "initial_answer",
      questionId: body.questionId,
      ...(body.kind === "coaching_answer"
        ? {
            fromAttemptId: body.attemptId,
            fromEvaluationId: body.fromEvaluationId,
          }
        : body.kind === "retry_attempt"
          ? {
              fromAttemptId: body.fromAttemptId,
              fromEvaluationId: body.fromEvaluationId,
            }
          : {}),
    });
  } catch (error) {
    if (applicationId) throw error;
    return;
  }
  if (applicationId) {
    const app = own(
      state.star.applications[applicationId],
      owner,
      "STAR_APPLICATION_NOT_FOUND",
    );
    if (app.contextId !== context.id || expired(app.expiresAt, now))
      return fail("STAR_APPLICATION_NOT_FOUND", 404);
    state.star.assists[evaluationId] = {
      applicationId: app.id,
      generationId: app.generationId,
      finalHash: sha256(body.answer),
      edited: sha256(body.answer) !== app.answerHash,
    };
  }
  const stored = state.star.contexts[context.id];
  if (!stored) return;
  stored.status = "COMPLETED";
  if (stored.answerDraftId) {
    const answer = state.star.answers[stored.answerDraftId];
    if (answer) {
      answer.status = "COMPLETED";
      answer.value.answer = "";
      answer.value.applicationId = null;
      answer.value.version++;
    }
  }
  if (stored.starDraftId) {
    const star = state.star.drafts[stored.starDraftId];
    if (star) {
      star.status = "COMPLETED";
      star.value.notes = { S: "", T: "", A: "", R: "" };
      star.value.candidates = [];
      star.value.originalCandidates = [];
      star.value.selectedCandidateId = null;
      star.value.generationId = null;
      star.value.targetCategory = null;
      star.value.industry = "";
      star.value.company = "";
      star.value.generationTargetCategory = null;
      star.value.version++;
    }
  }
  cancel(state, stored, now);
}
export function closeStarSession(
  state: MockState,
  owner: string,
  sessionId: string,
  now: number,
) {
  for (const context of Object.values(state.star.contexts))
    if (context.owner === owner && context.sessionId === sessionId) {
      cancel(state, context, now);
      context.status = "COMPLETED";
    }
}
export function startStarJob(
  state: MockState,
  id: string,
  now: number,
): Job | null {
  const job = state.star.generations[id];
  if (!job || job.expiresAt !== null) return null;
  if (job.callStarted) {
    if (now >= (job.leaseUntil ?? 0))
      terminal(state, job, "OUTCOME_UNKNOWN", now);
    return null;
  }
  if (now >= job.deadlineAt) {
    terminal(state, job, "FAILED_BEFORE_START", now);
    return null;
  }
  try {
    const context = activeContext(state, job.owner, job.contextId);
    draft(state, job.owner, job.starDraftId, true, now);
    if (context.activeGenerationId !== id) return null;
  } catch {
    terminal(state, job, "CANCELLED", now);
    return null;
  }
  for (const key of [`u:${job.owner}:${job.month}`, `g:${job.month}`]) {
    const q = quota(state.star, key);
    if (q.reserved < 1) throw new Error("QuotaUnderflow");
    q.reserved--;
    q.consumed++;
  }
  job.callStarted = true;
  job.quotaState = "consumed";
  job.status = "STARTED";
  job.executionId = crypto.randomUUID();
  job.leaseUntil = now + 60000;
  return structuredClone(job);
}
export function fakeStarResult(job: Job) {
  const facts = job.input.notes;
  const orders: Array<Array<keyof typeof facts>> = [
    ["R", "S", "T", "A"],
    ["A", "S", "T", "R"],
    ["S", "T", "A", "R"],
  ];
  const answers = orders.map((order) =>
    order
      .filter((k) => facts[k].trim())
      .map((k) => facts[k])
      .join("\n"),
  );
  return starResultSchema.parse(
    !facts.A.trim() || answers.some((v) => Array.from(v).length > 400)
      ? {
          status: "needs_information",
          candidates: [],
          missingInformation: [
            "本人が行ったことを、400文字以内にまとめられる短い事実で入力してください。",
          ],
        }
      : {
          status: "ready",
          candidates: answers.map((text, i) => ({
            id: ["A", "B", "C"][i],
            style: ["conclusion", "action", "conversational"][i],
            text,
          })),
          missingInformation: [],
        },
  );
}
export function finishStarJob(
  state: MockState,
  lease: Job,
  result: z.infer<typeof starResultSchema>,
  now: number,
) {
  const job = state.star.generations[lease.generationId];
  if (
    !job ||
    job.executionId !== lease.executionId ||
    job.expiresAt !== null ||
    now >= (job.leaseUntil ?? 0)
  )
    return;
  job.result = result;
  terminal(
    state,
    job,
    result.status === "ready" ? "SUCCEEDED" : "NEEDS_INFORMATION",
    now,
  );
}
export function starRoute(
  state: MockState,
  owner: string,
  method: string,
  path: string,
  raw: unknown,
  key: string | null,
  now = Date.now(),
): { status: number; body: unknown } {
  const patterns: [RegExp, string[]][] = [
    [/^\/star-assist\/options$/, ["GET"]],
    [/^\/star-assist\/preferences$/, ["GET", "PUT"]],
    [/^\/sessions\/[^/]+\/answer-contexts$/, ["POST"]],
    [/^\/answer-contexts\/[^/]+\/drafts$/, ["GET"]],
    [/^\/answer-contexts\/[^/]+\/(answer-drafts|star-drafts)$/, ["POST"]],
    [/^\/(answer-drafts|star-drafts)\/[^/]+$/, ["PUT"]],
    [/^\/(answer-drafts|star-drafts)\/[^/]+\/discard$/, ["POST"]],
    [/^\/star-drafts\/[^/]+\/applications$/, ["POST"]],
    [/^\/star-assist\/generations$/, ["POST"]],
    [/^\/star-assist\/(generations|requests)\/[^/]+$/, ["GET"]],
    [/^\/star-assist\/quota$/, ["GET"]],
  ];
  const allowed = patterns.find(([pattern]) => pattern.test(path));
  if (!allowed) return fail("NOT_FOUND", 404);
  if (!allowed[1].includes(method)) return fail("METHOD_NOT_ALLOWED", 405);
  const get = method === "GET";
  const previous = key ? state.star.requests[`${owner}:${key}`] : undefined;
  if (!get && !idSchema.safeParse(key).success)
    return fail("VALIDATION_ERROR", 400);
  const pathId = path.split("/")[2];
  if (
    pathId &&
    [
      "/answer-contexts/",
      "/answer-drafts/",
      "/star-drafts/",
      "/sessions/",
    ].some((p) => path.startsWith(p)) &&
    !idSchema.safeParse(pathId).success
  )
    return fail("VALIDATION_ERROR", 400);
  const requestHash = sha256(canonical([method, path, raw]));
  if (previous)
    return previous.requestHash === requestHash
      ? { status: previous.status, body: previous.receipt }
      : fail("IDEMPOTENCY_CONFLICT");
  if (!get && state.requests[`${owner}:${key}`])
    return fail("IDEMPOTENCY_CONFLICT");
  const result = route();
  if (!get)
    state.star.requests[`${owner}:${key}`] = {
      requestHash,
      method,
      path,
      status: result.status,
      receipt: result.body as Record<string, unknown>,
    };
  return result;
  function route(): { status: number; body: unknown } {
    if (path === "/star-assist/options" && get)
      return {
        status: 200,
        body: {
          categories: Object.entries(targetCategories).map(([id, label]) => ({
            id,
            label,
          })),
          userMonthlyLimit: 20,
          globalMonthlyLimit: 600,
        },
      };
    if (path === "/star-assist/preferences") {
      const prefs = Object.hasOwn(state.star.preferences, owner)
        ? state.star.preferences[owner]
        : { category: null, details: null };
      if (get)
        return {
          status: 200,
          body: {
            category:
              prefs.category && !expired(prefs.category.expiresAt, now)
                ? prefs.category
                : null,
            details:
              prefs.details && !expired(prefs.details.expiresAt, now)
                ? prefs.details
                : null,
          },
        };
      if (method !== "PUT") return fail("METHOD_NOT_ALLOWED", 405);
      const body = preferencesRequestSchema.parse(raw),
        reply: Record<string, unknown> = {};
      Object.defineProperty(state.star.preferences, owner, {
        value: prefs,
        enumerable: true,
        writable: true,
        configurable: true,
      });
      for (const name of ["category", "details"] as const) {
        const change = body[name];
        if (!change) continue;
        const current = prefs[name],
          active = current && !expired(current.expiresAt, now);
        if (
          change.expectedGeneration !==
            (active ? current.generationId : null) ||
          change.expectedVersion !== (active ? current.version : 0)
        )
          return fail("DRAFT_VERSION_CONFLICT");
        const m = active
          ? {
              ...receipt(current),
              version: current.version + 1,
              updatedAt: now,
              expiresAt: Math.floor(now / 1000) + 14 * DAY,
            }
          : meta(now, 14);
        if (name === "category" && "targetCategory" in change)
          prefs.category = {
            ...m,
            generationId: m.id,
            targetCategory: change.targetCategory,
          };
        if (name === "details" && "company" in change) {
          if (
            active &&
            prefs.details?.company === change.company &&
            prefs.details.industry === change.industry
          ) {
            reply[name] = receipt(current);
            continue;
          }
          prefs.details = {
            ...m,
            generationId: m.id,
            company: change.company,
            industry: change.industry,
          };
        }
        reply[name] = m;
      }
      return { status: 200, body: reply };
    }
    if (path.startsWith("/star-assist/requests/") && get) {
      const v = state.star.requests[`${owner}:${path.split("/")[3]}`];
      if (!v) return fail("STAR_REQUEST_NOT_FOUND", 404);
      return { status: 200, body: v };
    }
    if (path === "/star-assist/quota" && get) {
      const month = jstMonth(now),
        u = state.star.quotas[`u:${owner}:${month}`] ?? {
          reserved: 0,
          consumed: 0,
        },
        g = state.star.quotas[`g:${month}`] ?? { reserved: 0, consumed: 0 };
      return {
        status: 200,
        body: {
          month,
          user: { ...u, remaining: 20 - u.reserved - u.consumed },
          global: { ...g, remaining: 600 - g.reserved - g.consumed },
        },
      };
    }
    if (
      /^\/sessions\/[^/]+\/answer-contexts$/.test(path) &&
      method === "POST"
    ) {
      const row = contextFor(
        state,
        owner,
        pathId,
        contextRequestSchema.parse(raw),
      );
      if (state.star.contexts[row.id]?.status === "COMPLETED")
        return fail("DRAFT_CLOSED");
      state.star.contexts[row.id] ??= row;
      return {
        status: 200,
        body: { contextId: row.id, operationKind: row.operationKind },
      };
    }
    if (path.startsWith("/answer-contexts/")) {
      const context = activeContext(state, owner, pathId);
      if (path.endsWith("/drafts") && get) {
        const a = context.answerDraftId
            ? state.star.answers[context.answerDraftId]
            : null,
          s = context.starDraftId
            ? state.star.drafts[context.starDraftId]
            : null;
        return {
          status: 200,
          body: {
            answerDraft:
              a && a.status === "ACTIVE" && !expired(a.value.expiresAt, now)
                ? a.value
                : null,
            starDraft:
              s && s.status === "ACTIVE" && !expired(s.value.expiresAt, now)
                ? s.value
                : null,
          },
        };
      }
      if (method !== "POST") return fail("METHOD_NOT_ALLOWED", 405);
      const isStar = path.endsWith("/star-drafts"),
        existingId = isStar ? context.starDraftId : context.answerDraftId;
      const existing = existingId
        ? isStar
          ? state.star.drafts[existingId]
          : state.star.answers[existingId]
        : null;
      if (
        existing &&
        existing.status === "ACTIVE" &&
        !expired(existing.value.expiresAt, now)
      )
        return fail("DRAFT_VERSION_CONFLICT");
      const m = meta(now, isStar ? 7 : 14);
      if (isStar) {
        const value = starInputSchema.parse(raw);
        if (value.generationId) return fail("VALIDATION_ERROR", 400);
        cancel(state, context, now);
        context.starDraftId = m.id;
        state.star.drafts[m.id] = {
          owner,
          contextId: context.id,
          status: "ACTIVE",
          value: {
            ...m,
            ...value,
            originalCandidates: [],
            generationTargetCategory: null,
          },
        };
      } else {
        const value = answerValueSchema.parse(raw);
        if (value.applicationId) return fail("VALIDATION_ERROR", 400);
        context.answerDraftId = m.id;
        state.star.answers[m.id] = {
          owner,
          contextId: context.id,
          status: "ACTIVE",
          value: { ...m, answer: value.answer, applicationId: null },
        };
      }
      return { status: 201, body: m };
    }
    if (path === "/star-assist/generations" && method === "POST") {
      const body = generationRequestSchema.parse(raw),
        { context } = draft(state, owner, body.starDraftId, true, now),
        row = state.star.drafts[body.starDraftId];
      if (context.activeGenerationId)
        return fail("STAR_GENERATION_IN_PROGRESS");
      if (row.value.version !== body.expectedVersion)
        return fail("DRAFT_VERSION_CONFLICT");
      if (
        !row.value.targetCategory ||
        !Object.values(row.value.notes).some((v) => v.trim())
      )
        return fail("VALIDATION_ERROR", 400);
      const month = jstMonth(now),
        u = quota(state.star, `u:${owner}:${month}`),
        g = quota(state.star, `g:${month}`);
      if (u.reserved + u.consumed >= 20 || g.reserved + g.consumed >= 600)
        return fail("STAR_QUOTA_EXCEEDED", 429);
      u.reserved++;
      g.reserved++;
      const generationId = crypto.randomUUID();
      context.activeGenerationId = generationId;
      state.star.generations[generationId] = {
        generationId,
        status: "QUEUED",
        generationTargetCategory: row.value.targetCategory,
        result: null,
        owner,
        contextId: context.id,
        starDraftId: row.value.id,
        input: starValue(row.value),
        question: context.question,
        month,
        quotaState: "reserved",
        callStarted: false,
        deadlineAt: now + 900000,
        leaseUntil: null,
        executionId: null,
        expiresAt: null,
      };
      return { status: 202, body: { generationId, status: "QUEUED" } };
    }
    if (path.startsWith("/star-assist/generations/") && get) {
      const row = own(
        state.star.generations[path.split("/")[3]],
        owner,
        "STAR_GENERATION_NOT_FOUND",
      );
      if (expired(row.expiresAt, now))
        return fail("STAR_GENERATION_NOT_FOUND", 404);
      return {
        status: 200,
        body: generationSchema.parse({
          generationId: row.generationId,
          status: row.status,
          generationTargetCategory: row.generationTargetCategory,
          result: row.result,
        }),
      };
    }
    if (
      path.startsWith("/answer-drafts/") ||
      path.startsWith("/star-drafts/")
    ) {
      const isStar = path.startsWith("/star-drafts/"),
        { context } = draft(state, owner, pathId, isStar, now);
      if (path.endsWith("/applications") && method === "POST") {
        const body = applyRequestSchema.parse(raw),
          s = state.star.drafts[pathId],
          a = draft(state, owner, body.answerDraftId, false, now);
        if (a.context.id !== context.id)
          return fail("STAR_DRAFT_NOT_FOUND", 404);
        const answer = state.star.answers[body.answerDraftId];
        if (
          s.value.version !== body.expectedVersion ||
          answer.value.version !== body.expectedAnswerVersion
        )
          return fail("DRAFT_VERSION_CONFLICT");
        const selected = s.value.candidates.find(
          (c) => c.id === body.candidateId,
        );
        if (!selected || s.value.selectedCandidateId !== body.candidateId)
          return fail("VALIDATION_ERROR", 400);
        const applicationId = crypto.randomUUID(),
          expiry = Math.floor(now / 1000) + 14 * DAY;
        state.star.applications[applicationId] = {
          id: applicationId,
          owner,
          contextId: context.id,
          answerDraftId: answer.value.id,
          generationId: s.value.generationId!,
          candidateId: body.candidateId,
          answerHash: sha256(selected.text),
          expiresAt: expiry,
        };
        answer.value = {
          ...answer.value,
          answer: selected.text,
          applicationId,
          version: answer.value.version + 1,
          updatedAt: now,
          expiresAt: expiry,
        };
        return {
          status: 200,
          body: {
            ...receipt(answer.value),
            applicationId,
            answerHash: sha256(selected.text),
          },
        };
      }
      const discarded = path.endsWith("/discard");
      if (method !== (discarded ? "POST" : "PUT"))
        return fail("METHOD_NOT_ALLOWED", 405);
      const expected = z
        .object({ expectedVersion: z.number().int().positive() })
        .passthrough()
        .parse(raw).expectedVersion;
      if (isStar) {
        const row = state.star.drafts[pathId];
        if (row.value.version !== expected)
          return fail("DRAFT_VERSION_CONFLICT");
        if (discarded) {
          z.object({ expectedVersion: z.number() }).strict().parse(raw);
          cancel(state, context, now);
          row.status = "DISCARDED";
          row.value = {
            ...row.value,
            notes: { S: "", T: "", A: "", R: "" },
            targetCategory: null,
            industry: "",
            company: "",
            candidates: [],
            originalCandidates: [],
            generationId: null,
            selectedCandidateId: null,
            generationTargetCategory: null,
          };
        } else {
          const body = starUpdateSchema.parse(raw),
            value = starInputSchema.parse(
              Object.fromEntries(
                Object.entries(body).filter(([k]) => k !== "expectedVersion"),
              ),
            );
          if (
            value.generationId &&
            value.generationId !== row.value.generationId
          ) {
            const job = own(
              state.star.generations[value.generationId],
              owner,
              "STAR_GENERATION_NOT_FOUND",
            );
            if (
              job.contextId !== context.id ||
              job.starDraftId !== pathId ||
              expired(job.expiresAt, now) ||
              job.result?.status !== "ready"
            )
              return fail("STAR_GENERATION_NOT_FOUND", 404);
            row.value.originalCandidates = job.result.candidates;
            row.value.generationTargetCategory = job.generationTargetCategory;
          }
          const old = Object.fromEntries(
            Object.entries(row.value).filter(([k]) => k in value),
          );
          if (canonical(old) === canonical(value))
            return { status: 200, body: receipt(row.value) };
          row.value = {
            ...row.value,
            ...value,
            expiresAt: Math.floor(now / 1000) + 7 * DAY,
          };
        }
        row.value.version++;
        row.value.updatedAt = now;
        return { status: 200, body: receipt(row.value) };
      }
      const row = state.star.answers[pathId];
      if (row.value.version !== expected) return fail("DRAFT_VERSION_CONFLICT");
      if (discarded) {
        z.object({ expectedVersion: z.number() }).strict().parse(raw);
        row.status = "DISCARDED";
        row.value.answer = "";
        row.value.applicationId = null;
      } else {
        const value = answerUpdateSchema.parse(raw);
        if (
          row.value.answer === value.answer &&
          row.value.applicationId === (value.applicationId ?? null)
        )
          return { status: 200, body: receipt(row.value) };
        if (value.applicationId) {
          const app = own(
            state.star.applications[value.applicationId],
            owner,
            "STAR_APPLICATION_NOT_FOUND",
          );
          if (
            app.contextId !== context.id ||
            app.answerDraftId !== pathId ||
            expired(app.expiresAt, now)
          )
            return fail("STAR_APPLICATION_NOT_FOUND", 404);
          app.expiresAt = Math.floor(now / 1000) + 14 * DAY;
        }
        row.value.answer = value.answer;
        row.value.applicationId = value.applicationId ?? null;
        row.value.expiresAt = Math.floor(now / 1000) + 14 * DAY;
      }
      row.value.version++;
      row.value.updatedAt = now;
      return { status: 200, body: receipt(row.value) };
    }
    return fail("NOT_FOUND", 404);
  }
}
