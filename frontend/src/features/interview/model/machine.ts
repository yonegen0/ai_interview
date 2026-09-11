/** @file machine.ts @description 矛盾した操作段階を防ぐ状態遷移 */
export type Phase =
  | "answering"
  | "submitting"
  | "processing"
  | "recovery_required"
  | "completed"
  | "failed";
export type Event =
  "SUBMIT" | "ACCEPT" | "UNKNOWN" | "INVALID" | "COMPLETE" | "FAIL" | "RETRY";
const transitions: Partial<Record<Phase, Partial<Record<Event, Phase>>>> = {
  answering: { SUBMIT: "submitting" },
  submitting: {
    ACCEPT: "processing",
    UNKNOWN: "recovery_required",
    INVALID: "answering",
  },
  recovery_required: { SUBMIT: "submitting", ACCEPT: "processing" },
  processing: { COMPLETE: "completed", FAIL: "failed" },
  failed: { RETRY: "answering" },
  completed: {},
};
export const reducer = (phase: Phase, event: Event): Phase =>
  transitions[phase]?.[event] ?? phase;
