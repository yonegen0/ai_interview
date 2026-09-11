/** @file InterviewPractice.stories.tsx @description URL Query、Session取得、Reload復旧の統合Story。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { http, HttpResponse, delay } from "msw";
import { expect, within } from "storybook/test";
import { InterviewPractice } from "@/features/interview/components/pages/InterviewPractice";
import { createCompletedState, createEvaluationFixture, createFeedbackFixture, createSessionFixture, createStoryState, sessionRoute, storyIds } from "../../fixtures";

const processing = createEvaluationFixture("processing");
const processingSession = createSessionFixture({ activeAttempt: { attemptId: storyIds.currentAttempt, evaluationId: storyIds.evaluation, status: "processing" } });
const processingSeed = createStoryState({ session: processingSession, feedback: createFeedbackFixture(), evaluation: processing });
const retryRoute = `${sessionRoute}&mode=retry&fromAttemptId=${storyIds.currentAttempt}`;
const meta = { title: "Pages/Interview/InterviewPractice", component: InterviewPractice, parameters: { layout: "padded", mock: true, initialRoute: sessionRoute, seed: createStoryState() } } satisfies Meta<typeof InterviewPractice>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Loading: Story = { parameters: { handlers: [http.get("*/api/sessions/:id/question", async () => { await delay("infinite"); return HttpResponse.json({}); })] } };
export const Ready: Story = {};
export const InvalidSessionId: Story = { parameters: { initialRoute: "/practice/session/?sessionId=invalid" } };
export const MissingSessionId: Story = { parameters: { initialRoute: "/practice/session/" } };
export const SessionNotFound: Story = { parameters: { initialRoute: "/practice/session/?sessionId=10000000-0000-4000-8000-000000000099", seed: createStoryState() } };
export const SessionServerError: Story = { parameters: { handlers: [http.get("*/api/sessions/:id/question", () => HttpResponse.json({ code: "INTERNAL_SERVER_ERROR", message: "error" }, { status: 500 }))] } };
export const ActiveEvaluationRestored: Story = { parameters: { seed: processingSeed, mockScenario: "never" } };
export const CompletedEvaluationRestored: Story = { parameters: { seed: createCompletedState() } };
export const RetryMode: Story = { parameters: { initialRoute: retryRoute, seed: createCompletedState() } };
export const RetryIdMissing: Story = { parameters: { initialRoute: `${sessionRoute}&mode=retry` } };
export const RetryIdInvalid: Story = { parameters: { initialRoute: `${sessionRoute}&mode=retry&fromAttemptId=invalid` } };
export const RetryAttemptNotFound: Story = { parameters: { initialRoute: `${sessionRoute}&mode=retry&fromAttemptId=${storyIds.previousAttempt}` } };
export const RetryQuestionMismatch: Story = { parameters: { initialRoute: retryRoute, seed: createStoryState({ session: createSessionFixture({ questionNumber: 2 }), feedback: createFeedbackFixture(), evaluation: createEvaluationFixture("completed") }) }, play: async ({ canvasElement }) => { await expect(await within(canvasElement).findByRole("link", { name: "現在の練習へ戻る" })).toBeInTheDocument(); } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
