/** @file index.ts @description セッション・評価・復旧シナリオを実現するMSW Handler */
import { http, HttpResponse, delay } from "msw";
import { z } from "zod";
import {
  createSchema,
  submitSchema,
  nextSchema,
  idSchema,
  type Feedback,
  type Session,
} from "@/lib/api/schemas";
import { questions } from "../data/questions";
import type { Repository, MockState } from "../store";
export type Scenario =
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
export const scenarios: Scenario[] = [
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
export function createHandlers(
  repository: Repository,
  scenario: () => Scenario = () => "success",
  base = "*/api",
) {
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
      repository.write(state);
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
  async function mutate<T>(
    request: Request,
    schema: z.ZodType<T>,
    operation: (
      state: MockState,
      body: T,
    ) => { status: number; body: unknown } | Response,
  ) {
    const key = request.headers.get("Idempotency-Key");
    if (!idSchema.safeParse(key).success) return error("VALIDATION_ERROR", 400);
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      return error("VALIDATION_ERROR", 400);
    }
    const parsed = schema.safeParse(raw);
    if (!parsed.success) return error("VALIDATION_ERROR", 400);
    const state = repository.read();
    const fingerprint = `${new URL(request.url).pathname}:${JSON.stringify(parsed.data)}`;
    const previous = state.requests[key!];
    if (previous)
      return previous.fingerprint === fingerprint
        ? HttpResponse.json(previous.body as object, {
            status: previous.status,
          })
        : error("IDEMPOTENCY_CONFLICT", 409);
    const failure = fault(state);
    if (failure) return failure;
    const result = operation(state, parsed.data);
    if (result instanceof Response) return result;
    state.requests[key!] = { fingerprint, ...result };
    repository.write(state);
    if (
      scenario() === "response_lost" &&
      !state.consumed.includes("response_lost")
    ) {
      state.consumed.push("response_lost");
      repository.write(state);
      return HttpResponse.error();
    }
    return HttpResponse.json(result.body as object, { status: result.status });
  }
  return [
    http.post(`${base}/sessions`, ({ request }) =>
      mutate(request, createSchema, (state, body) => {
        const sessionId = crypto.randomUUID();
        state.sessions[sessionId] = {
          sessionId,
          question: questions.find((q) => q.category === body.category)!,
          questionNumber: 1,
          activeAttempt: null,
        };
        return { status: 201, body: { sessionId } };
      }),
    ),
    http.get(`${base}/sessions/:id/question`, ({ params }) => {
      const value = repository.read().sessions[String(params.id)];
      return value ? HttpResponse.json(value) : error("SESSION_NOT_FOUND", 404);
    }),
    http.post(`${base}/sessions/:id/answers`, ({ params, request }) =>
      mutate(
        request,
        submitSchema,
        (state, body) => {
          const session = state.sessions[String(params.id)];
          if (!session) return error("SESSION_NOT_FOUND", 404);
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
          session.activeAttempt = {
            attemptId,
            evaluationId,
            status: "processing",
          };
          return { status: 202, body: session.activeAttempt };
        },
      ),
    ),
    http.get(`${base}/evaluations/:id`, async ({ params }) => {
      await delay(50);
      const state = repository.read();
      const record = Object.values(state.attempts).find(
        (a) => a.evaluation.evaluationId === params.id,
      );
      if (!record) return error("ATTEMPT_NOT_FOUND", 404);
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
        repository.write(state);
      }
      return HttpResponse.json(record.evaluation);
    }),
    http.get(`${base}/attempts/:id/feedback`, ({ params }) => {
      const record = repository.read().attempts[String(params.id)];
      if (!record) return error("ATTEMPT_NOT_FOUND", 404);
      if (record.evaluation.status !== "completed")
        return error("EVALUATION_NOT_COMPLETED", 409);
      return HttpResponse.json(record.feedback);
    }),
    http.post(`${base}/sessions/:id/questions/next`, ({ params, request }) =>
      mutate(request, nextSchema, (state, body) => {
        const session = state.sessions[String(params.id)];
        if (!session) return error("SESSION_NOT_FOUND", 404);
        if (
          session.activeAttempt?.attemptId !== body.fromAttemptId ||
          session.activeAttempt.status !== "completed"
        )
          return error("SESSION_STATE_CONFLICT", 409);
        const pool = questions.filter(
          (q) => q.category === session.question.category,
        );
        const next: Session = {
          ...session,
          question: pool[session.questionNumber % pool.length],
          questionNumber: session.questionNumber + 1,
          activeAttempt: null,
        };
        state.sessions[session.sessionId] = next;
        return { status: 200, body: next };
      }),
    ),
  ];
}
