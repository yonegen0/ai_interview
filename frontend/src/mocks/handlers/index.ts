/** @file index.ts @description セッション・評価・復旧シナリオを実現するMSW Handler */
import { http as mswHttp, HttpResponse, delay } from "msw";
import { MockConflict as StarConflict } from "../coaching";
import { starRoute, closeStarAnswer, closeStarSession } from "../star";
import { pumpStarJobs } from "../transactions";
import { attemptSchema } from "@/lib/api/schemas";
import { z } from "zod";
import {
  createSchema,
  submitSchema,
  nextSchema,
  idSchema,
  activeCategoryIds,
  categories,
  bankSaveSchema,
  bankSaveSchemaForBaseline,
  isFeedbackV2,
  v2SubmitSchema,
  type Feedback,
  type Session,
} from "@/lib/api/schemas";
import type { Repository, MockState } from "../store";
import { acceptCoaching, pollCoaching, MockConflict } from "../coaching";
export type Scenario =
  | "star_response_lost"
  | "star_apply_delayed"
  | CoachingScenario
  | "success"
  | "slow"
  | "never"
  | "validation"
  | "unauthorized"
  | "not_found"
  | "server_error"
  | "network_error"
  | "response_lost"
  | "invalid_response"
  | "evaluation_failed"
  | "state_conflict";
// Trusted Mock scenario selection, never applicant-text magic strings.
export type CoachingScenario =
  | "coaching"
  | "coaching_max"
  | "low_score"
  | "multiline_question"
  | "contradiction"
  | "invalid_provider";
export const scenarios: Scenario[] = [
  "star_response_lost",
  "star_apply_delayed",
  "coaching",
  "coaching_max",
  "low_score",
  "multiline_question",
  "contradiction",
  "invalid_provider",
  "success",
  "slow",
  "never",
  "validation",
  "unauthorized",
  "not_found",
  "server_error",
  "network_error",
  "response_lost",
  "invalid_response",
  "evaluation_failed",
  "state_conflict",
];
const error = (code: string, status: number) =>
  HttpResponse.json({ code, message: code }, { status });
function actor(request: Request) {
  const token = request.headers.get("authorization")?.replace(/^Bearer /, "");
  const match = token?.match(/^mock:([^:]+):(USER|ADMIN)$/);
  return match
    ? { sub: decodeURIComponent(match[1]), admin: match[2] === "ADMIN" }
    : null;
}
const sessionOwner = (state: MockState, id: string) =>
  state.owners[id] || "mock-user";
export function createHandlers(
  repository: Repository,
  scenario: () => Scenario | CoachingScenario = () => "success",
  base = "*/api",
) {
  let activeRepository: Repository;
  const bodies = new WeakMap<Request, unknown>();
  let pumping = false;
  const schedule = () => {
    if (pumping) return;
    pumping = true;
    setTimeout(() => {
      void pumpStarJobs(repository)
        .catch(() => undefined)
        .finally(() => {
          pumping = false;
        });
    }, 50);
  };
  const wrap =
    (method: "get" | "post" | "put") =>
    (path: string, resolver: Parameters<typeof mswHttp.get>[1]) =>
      mswHttp[method](path, async (args) => {
        if (method !== "get") {
          try {
            bodies.set(args.request, await args.request.clone().json());
          } catch {
            bodies.set(args.request, null);
          }
        }
        if (new URL(args.request.url).pathname.includes("/evaluations/"))
          await delay(50);
        try {
          const result = await repository.transaction((snapshot) => {
            activeRepository = snapshot;
            const response = resolver(args);
            if (response instanceof Promise)
              throw new Error("AsyncMockResolverInsideTransaction");
            return response;
          });
          schedule();
          const pathname = new URL(args.request.url).pathname;
          if (
            scenario() === "star_apply_delayed" &&
            pathname.endsWith("/applications")
          )
            await delay(1000);
          if (
            scenario() === "star_response_lost" &&
            method !== "get" &&
            /\/answer-drafts(?:\/|$)/.test(pathname)
          ) {
            const lose = await repository.transaction((snapshot) => {
              const state = snapshot.read();
              if (state.consumed.includes("star_response_lost")) return false;
              state.consumed.push("star_response_lost");
              snapshot.write(state);
              return true;
            });
            if (lose) return HttpResponse.error();
          }
          return result;
        } catch (cause) {
          if (cause instanceof StarConflict)
            return error(cause.code, cause.status);
          if (cause instanceof z.ZodError)
            return error("VALIDATION_ERROR", 400);
          return error("INTERNAL_SERVER_ERROR", 500);
        }
      });
  const http = { get: wrap("get"), post: wrap("post"), put: wrap("put") };
  const fault = (state: MockState) => {
    const mode = scenario();
    if (
      [
        "validation",
        "unauthorized",
        "not_found",
        "server_error",
        "network_error",
        "invalid_response",
        "state_conflict",
      ].includes(mode) &&
      !state.consumed.includes(mode)
    ) {
      state.consumed.push(mode);
      activeRepository.write(state);
      if (mode === "network_error") return HttpResponse.error();
      if (mode === "invalid_response")
        return HttpResponse.json({ unexpected: true });
      const mapping: Record<string, [string, number]> = {
        validation: ["VALIDATION_ERROR", 400],
        unauthorized: ["UNAUTHORIZED", 401],
        not_found: ["SESSION_NOT_FOUND", 404],
        server_error: ["INTERNAL_SERVER_ERROR", 500],
        state_conflict: ["SESSION_STATE_CONFLICT", 409],
      };
      return error(...mapping[mode]);
    }
  };
  function mutate<T>(
    request: Request,
    schema: z.ZodType<T>,
    operation: (
      state: MockState,
      body: T,
    ) => { status: number; body: unknown } | Response,
  ) {
    const identity = actor(request);
    if (!identity) return error("UNAUTHORIZED", 401);
    if (
      new URL(request.url).pathname.endsWith("/admin/question-bank") &&
      !identity.admin
    )
      return error("FORBIDDEN", 403);
    const key = request.headers.get("Idempotency-Key");
    if (!idSchema.safeParse(key).success) return error("VALIDATION_ERROR", 400);
    let raw: unknown;
    try {
      raw = bodies.get(request);
    } catch {
      return error("VALIDATION_ERROR", 400);
    }
    const parsed = schema.safeParse(raw);
    if (!parsed.success) return error("VALIDATION_ERROR", 400);
    const state = structuredClone(activeRepository.read());
    const fingerprint = `${new URL(request.url).pathname}:${JSON.stringify(parsed.data)}`;
    const scoped = `${identity.sub}:${key}`;
    const previous = state.requests[scoped];
    if (previous)
      return previous.fingerprint === fingerprint
        ? HttpResponse.json(previous.body as object, {
            status: previous.status,
          })
        : error("IDEMPOTENCY_CONFLICT", 409);
    const failure = fault(state);
    if (failure) return failure;
    if (state.star.requests[scoped]) return error("IDEMPOTENCY_CONFLICT", 409);
    const before = structuredClone(state);
    const result = operation(state, parsed.data);
    if (result instanceof Response) return result;
    if (
      new URL(request.url).pathname.endsWith("/answers") &&
      result.status === 202
    ) {
      const sid = new URL(request.url).pathname.split("/").at(-2)!;
      closeStarAnswer(
        state,
        before,
        identity.sub,
        sid,
        submitSchema.parse(parsed.data),
        attemptSchema.parse(result.body).evaluationId,
        request.headers.get("X-Star-Application-Id"),
        Date.now(),
      );
    }
    if (new URL(request.url).pathname.endsWith("/questions/next"))
      closeStarSession(
        state,
        identity.sub,
        new URL(request.url).pathname.split("/").at(-3)!,
        Date.now(),
      );
    state.requests[scoped] = { fingerprint, ...result };
    activeRepository.write(state);
    if (
      scenario() === "response_lost" &&
      !state.consumed.includes("response_lost")
    ) {
      state.consumed.push("response_lost");
      activeRepository.write(state);
      return HttpResponse.error();
    }
    return HttpResponse.json(result.body as object, { status: result.status });
  }
  const helpers = [
    "/star-assist/options",
    "/star-assist/preferences",
    "/star-assist/generations",
    "/star-assist/generations/:id",
    "/star-assist/quota",
    "/star-assist/requests/:id",
    "/sessions/:id/answer-contexts",
    "/answer-contexts/:id/drafts",
    "/answer-contexts/:id/answer-drafts",
    "/answer-contexts/:id/star-drafts",
    "/answer-drafts/:id",
    "/answer-drafts/:id/discard",
    "/star-drafts/:id",
    "/star-drafts/:id/discard",
    "/star-drafts/:id/applications",
  ];
  const helperHandlers = helpers.flatMap((path) =>
    ["get", "post", "put"].map((method) =>
      http[method as "get" | "post" | "put"](
        `${base}${path}`,
        ({ request }) => {
          const identity = actor(request);
          if (!identity) return error("UNAUTHORIZED", 401);
          const state = activeRepository.read();
          const apiPath = new URL(request.url).pathname.replace(
            /.*\/api(?=\/)/,
            "",
          );
          const key = request.headers.get("Idempotency-Key");
          const result = starRoute(
            state,
            identity.sub,
            request.method,
            apiPath,
            bodies.get(request) ?? null,
            key,
          );
          activeRepository.write(state);
          if (
            scenario() === "response_lost" &&
            request.method !== "GET" &&
            !state.consumed.includes("star_response_lost")
          ) {
            state.consumed.push("star_response_lost");
            activeRepository.write(state);
            return HttpResponse.error();
          }
          return HttpResponse.json(result.body as object, {
            status: result.status,
            headers: { "Cache-Control": "no-store" },
          });
        },
      ),
    ),
  );
  return [
    ...helperHandlers,
    http.get(`${base}/practice-options`, ({ request }) => {
      if (!actor(request)) return error("UNAUTHORIZED", 401);
      const bank = activeRepository.read().bank;
      return HttpResponse.json(
        {
          bankVersion: bank.version,
          totalQuestions: bank.questions.length,
          categories: activeCategoryIds.flatMap((id) => {
            const count = bank.questions.filter(
              (q) => q.category === id,
            ).length;
            return count
              ? [{ id, label: categories[id], questionCount: count }]
              : [];
          }),
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }),
    http.get(`${base}/admin/question-bank`, ({ request }) => {
      const identity = actor(request);
      if (!identity) return error("UNAUTHORIZED", 401);
      if (!identity.admin) return error("FORBIDDEN", 403);
      return HttpResponse.json(activeRepository.read().bank, {
        headers: { "Cache-Control": "no-store" },
      });
    }),
    http.post(`${base}/admin/question-bank`, ({ request }) =>
      mutate(request, bankSaveSchema, (state, body) => {
        if (body.expectedVersion !== state.bank.version)
          return error("QUESTION_BANK_CONFLICT", 409);
        if (
          !bankSaveSchemaForBaseline(state.bank.questions).safeParse(body)
            .success
        )
          return error("VALIDATION_ERROR", 400);
        if (
          JSON.stringify(body.questions) !==
          JSON.stringify(state.bank.questions)
        )
          state.bank = {
            version: state.bank.version + 1,
            updatedAt: new Date().toISOString(),
            questions: structuredClone(body.questions),
          };
        return {
          status: 200,
          body: {
            version: state.bank.version,
            totalQuestions: state.bank.questions.length,
            updatedAt: state.bank.updatedAt,
          },
        };
      }),
    ),
    http.post(`${base}/sessions`, ({ request }) =>
      mutate(request, createSchema, (state, body) => {
        const pool = state.bank.questions.filter(
          (q) => body.mode === "full" || q.category === body.category,
        );
        if (!pool.length) return error("CATEGORY_UNAVAILABLE", 409);
        const sessionId = crypto.randomUUID();
        state.sessionQuestions[sessionId] = structuredClone(pool);
        state.owners[sessionId] = actor(request)!.sub;
        state.sessions[sessionId] = {
          sessionId,
          question: structuredClone(pool[0]),
          questionNumber: 1,
          activeAttempt: null,
          mode: body.mode || "category",
          totalQuestions: pool.length,
          hasNext: pool.length > 1,
        };
        return { status: 201, body: { sessionId } };
      }),
    ),
    http.get(`${base}/sessions/:id/question`, ({ params, request }) => {
      const identity = actor(request);
      if (!identity) return error("UNAUTHORIZED", 401);
      const state = activeRepository.read(),
        id = String(params.id);
      const value =
        sessionOwner(state, id) === identity.sub
          ? state.sessions[id]
          : undefined;
      return value ? HttpResponse.json(value) : error("SESSION_NOT_FOUND", 404);
    }),
    http.post(`${base}/sessions/:id/answers`, ({ params, request }) =>
      mutate(request, submitSchema, (state, body) => {
        const session = state.sessions[String(params.id)];
        if (
          !session ||
          sessionOwner(state, String(params.id)) !== actor(request)!.sub
        )
          return error("SESSION_NOT_FOUND", 404);
        if (body.kind !== undefined) {
          const source =
            "attemptId" in body
              ? state.attempts[body.attemptId]
              : "fromAttemptId" in body
                ? state.attempts[body.fromAttemptId]
                : undefined;
          if (
            source &&
            sessionOwner(state, source.feedback.sessionId) !==
              actor(request)!.sub
          )
            return error("ATTEMPT_NOT_FOUND", 404);
          try {
            return acceptCoaching(
              state,
              String(params.id),
              v2SubmitSchema.parse(body),
            );
          } catch (cause) {
            if (cause instanceof MockConflict)
              return error(cause.code, cause.status);
            throw cause;
          }
        }
        if (session.activeCoaching) return error("SESSION_STATE_CONFLICT", 409);
        if (
          session.question.id !== body.questionId ||
          session.activeAttempt?.status === "processing"
        )
          return error("SESSION_STATE_CONFLICT", 409);
        const attemptId = crypto.randomUUID(),
          evaluationId = crypto.randomUUID();
        const feedback: Feedback = {
          attemptId,
          sessionId: session.sessionId,
          question: session.question,
          questionNumber: session.questionNumber,
          answer: body.answer,
          score: 78,
          summary: "結論と具体例をつなげる伝え方のサンプルです。",
          strengths: ["最初に伝えたいことを示すと、話の軸が明確になります。"],
          improvements: ["実際に経験した行動と結果を一つ添えてみましょう。"],
          exampleAnswer:
            "私が大切にしているのは、課題を整理して行動に移すことです。ここにご自身の具体的な経験と学びを加えてください。",
          createdAt: new Date().toISOString(),
        };
        state.attempts[attemptId] = {
          feedback,
          evaluation: { attemptId, evaluationId, status: "processing" },
          polls: 0,
          startedAt: Date.now(),
        };
        state.evaluations[evaluationId] = structuredClone(
          state.attempts[attemptId],
        );
        session.activeAttempt = {
          attemptId,
          evaluationId,
          status: "processing",
        };
        return { status: 202, body: session.activeAttempt };
      }),
    ),
    http.get(`${base}/evaluations/:id`, ({ params, request }) => {
      const identity = actor(request);
      if (!identity) return error("UNAUTHORIZED", 401);
      const state = activeRepository.read();
      const v2 = state.evaluations[String(params.id)];
      if (v2 && isFeedbackV2(v2.feedback)) {
        if (sessionOwner(state, v2.feedback.sessionId) !== identity.sub)
          return error("ATTEMPT_NOT_FOUND", 404);
        const evaluated = pollCoaching(state, String(params.id), scenario());
        activeRepository.write(state);
        return HttpResponse.json(evaluated);
      }
      const record = Object.values(state.attempts).find(
        (a) => a.evaluation.evaluationId === params.id,
      );
      if (
        !record ||
        sessionOwner(state, record.feedback.sessionId) !== identity.sub
      )
        return error("ATTEMPT_NOT_FOUND", 404);
      if (record.evaluation.status === "processing") {
        record.polls++;
        if (
          scenario() !== "never" &&
          record.polls >= 3 &&
          (scenario() !== "slow" || Date.now() - record.startedAt > 35000)
        ) {
          record.evaluation =
            scenario() === "evaluation_failed"
              ? {
                  ...record.evaluation,
                  status: "failed",
                  error: {
                    code: "EVALUATION_FAILED",
                    message: "Mock evaluation failed",
                  },
                }
              : { ...record.evaluation, status: "completed" };
          const session = state.sessions[record.feedback.sessionId];
          if (session.activeAttempt?.attemptId === record.evaluation.attemptId)
            session.activeAttempt.status = record.evaluation.status;
        }
        state.evaluations[String(params.id)] = structuredClone(record);
        activeRepository.write(state);
      }
      return HttpResponse.json(record.evaluation);
    }),
    http.get(`${base}/attempts/:id/feedback`, ({ params, request }) => {
      const identity = actor(request);
      if (!identity) return error("UNAUTHORIZED", 401);
      const state = activeRepository.read();
      const latest = state.attempts[String(params.id)];
      const requested = new URL(request.url).searchParams.get("evaluationId");
      if (requested !== null && !idSchema.safeParse(requested).success)
        return error("VALIDATION_ERROR", 400);
      const record = requested ? state.evaluations[requested] : latest;
      if (
        !record ||
        record.feedback.attemptId !== String(params.id) ||
        sessionOwner(state, record.feedback.sessionId) !== identity.sub
      )
        return error("ATTEMPT_NOT_FOUND", 404);
      if (record.evaluation.status !== "completed")
        return error("EVALUATION_NOT_COMPLETED", 409);
      return HttpResponse.json(record.feedback);
    }),
    http.post(`${base}/sessions/:id/questions/next`, ({ params, request }) =>
      mutate(request, nextSchema, (state, body) => {
        const session = state.sessions[String(params.id)];
        if (
          !session ||
          sessionOwner(state, String(params.id)) !== actor(request)!.sub
        )
          return error("SESSION_NOT_FOUND", 404);
        if (
          session.activeAttempt?.attemptId !== body.fromAttemptId ||
          session.activeAttempt.status !== "completed"
        )
          return error("SESSION_STATE_CONFLICT", 409);
        if (
          session.activeCoaching &&
          session.activeCoaching.stage !== "completed"
        )
          return error("SESSION_STATE_CONFLICT", 409);
        const pool = state.sessionQuestions[session.sessionId] || [
          session.question,
        ];
        if (
          session.mode &&
          session.mode !== "legacy" &&
          session.questionNumber === pool.length
        )
          return error("SESSION_COMPLETED", 409);
        const next: Session = {
          ...session,
          question: pool[session.questionNumber % pool.length],
          questionNumber: session.questionNumber + 1,
          activeAttempt: null,
          hasNext:
            !session.mode ||
            session.mode === "legacy" ||
            session.questionNumber + 1 < pool.length,
          mode: session.mode || "legacy",
          totalQuestions: pool.length,
        };
        state.sessions[session.sessionId] = next;
        delete next.activeCoaching;
        return { status: 200, body: next };
      }),
    ),
  ];
}
