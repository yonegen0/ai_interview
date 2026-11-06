/** @file history.ts @description MSW専用の本人別履歴投影。実APIと同じ構造で返す。 */
import type { MockState } from "./store";
import { isFeedbackV2 } from "@/lib/api/schemas";
import {
  historyFilterSchema, historyPeriodSchema, type HistoryItem,
  type HistoryMode, type HistoryPeriod, type HistoryResponse,
} from "@/lib/api/schemas/history";

const DAY = 86400000;
const jstDay = (milliseconds: number) =>
  Math.floor((milliseconds + 9 * 60 * 60 * 1000) / DAY);

export function mockHistory(
  state: MockState, owner: string, params: Record<string, string>, now: number,
): HistoryResponse {
  if (Object.keys(params).some((key) => !["mode", "period", "limit", "cursor"].includes(key)))
    throw new Error("invalid_params");
  const mode: HistoryMode = historyFilterSchema.parse(params.mode ?? "all");
  const period: HistoryPeriod = historyPeriodSchema.parse(params.period ?? "all");
  const limit = params.limit ?? "5";
  if (!/^[0-9]{1,3}$/.test(limit) || Number(limit) < 1 || Number(limit) > 100)
    throw new Error("invalid_limit");
  let anchor = now;
  let after: [number, string] | null = null;
  if (params.cursor) {
    const parsed: unknown = JSON.parse(atob(params.cursor));
    if (!parsed || typeof parsed !== "object") throw new Error("invalid_cursor");
    const c = parsed as Record<string, unknown>;
    if (c.owner !== owner || c.mode !== mode || c.period !== period ||
      typeof c.anchor !== "number" || c.anchor > now || c.anchor <= 0 ||
      !Array.isArray(c.after) || c.after.length !== 2 ||
      typeof c.after[0] !== "number" || typeof c.after[1] !== "string")
      throw new Error("cursor_scope");
    anchor = c.anchor;
    after = [c.after[0], c.after[1]];
  }
  const rows: HistoryItem[] = [];
  for (const [id, value] of Object.entries(state.attempts)) {
    const feedback = value.feedback;
    if ((state.owners[feedback.sessionId] ?? "mock-user") !== owner) continue;
    const coaching = state.coachings[id];
    const selected = coaching
      ? state.evaluations[coaching.evaluationId]
      : state.evaluations[value.evaluation.evaluationId] ?? value;
    const status = coaching ? coaching.stage === "evaluating" ? "processing"
      : coaching.stage === "failed" ? "failed" : "completed"
      : selected.evaluation.status;
    const actualFeedback = selected.feedback;
    const v2 = isFeedbackV2(feedback);
    const score = status === "completed" ?
      v2 && isFeedbackV2(actualFeedback) ? actualFeedback.totalScore
      : !v2 && !isFeedbackV2(actualFeedback) ? actualFeedback.score : null
      : null;
    rows.push({
      id: `attempt:${id}`, kind: v2 ? "coaching" : "normal",
      label: feedback.question.question, category: feedback.question.category,
      createdAt: value.startedAt, status, score, scoreMax: v2 ? 30 : 100,
      attemptId: id, evaluationId: coaching?.evaluationId ?? selected.evaluation.evaluationId,
      generationId: null, assistType: null,
    });
  }
  for (const [id, generation] of Object.entries(state.star.generations)) {
    if (generation.owner !== owner) continue;
    rows.push({
      id: `assist:${id}`, kind: "assist",
      label: generation.question, category: null,
      createdAt: generation.deadlineAt - 900000,
      status: generation.status,
      score: null, scoreMax: null,
      attemptId: null, evaluationId: null, generationId: id,
      assistType: generation.input.assistType ?? "star",
    });
  }
  const filtered = rows.filter((row) => {
    if (mode !== "all" && row.kind !== mode &&
      !(row.kind === "assist" && (mode === "assist" || row.assistType === mode)))
      return false;
    if (row.createdAt > anchor) return false;
    return period === "all" ||
      jstDay(row.createdAt) >= jstDay(anchor) - ({ today: 0, "7d": 6, "30d": 29 }[period]);
  }).sort((a, b) => b.createdAt - a.createdAt || b.id.localeCompare(a.id));
  const usage = mode === "all" && period === "all" ? (() => {
    const normal = filtered.filter((r) => r.kind === "normal" && r.status === "completed");
    const coaching = filtered.filter((r) => r.kind === "coaching" && r.status === "completed");
    const average = (values: HistoryItem[]) => values.length
      ? Math.round(values.reduce((sum, item) => sum + (item.score ?? 0), 0) * 10 / values.length) / 10
      : null;
    return {
      practiceAttempts: filtered.filter((r) => r.kind !== "assist").length,
      evaluatedAttempts: normal.length + coaching.length,
      assistGenerations: filtered.filter((r) => r.kind === "assist").length,
      normalAverage: average(normal), coachingAverage: average(coaching),
    };
  })() : null;
  const result = filtered.filter((row) =>
    !after || row.createdAt < after[0] ||
    (row.createdAt === after[0] && row.id < after[1]));
  const page = result.slice(0, Number(limit));
  const last = page.at(-1);
  const nextCursor = result.length > Number(limit) && last
    ? btoa(JSON.stringify({
      owner, mode, period, anchor, after: [last.createdAt, last.id],
    })) : null;
  return { items: page, nextCursor, usage };
}
