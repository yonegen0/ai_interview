/** @file FeedbackResult.stories.tsx @description 結果取得、再挑戦、次問、古い結果の統合Story。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { delay, http, HttpResponse } from "msw";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { getRouter } from "@storybook/nextjs-vite/navigation.mock";
import { FeedbackResult } from "@/features/feedback/components/pages/FeedbackResult";
import { withAppShell } from "../../test-utils/withAppShell";
import {
  createCompletedState,
  createFeedbackFixture,
  createSessionFixture,
  createStoryState,
  resultRoute,
  storyIds,
  storyTexts,
} from "../../fixtures";

const completed = createCompletedState();
const stale = {
  ...completed,
  sessions: {
    [storyIds.session]: createSessionFixture({
      questionNumber: 2,
      activeAttempt: null,
    }),
  },
};
const meta = {
  title: "Pages/Feedback/FeedbackResult",
  component: FeedbackResult,
  parameters: {
    layout: "padded",
    mock: true,
    initialRoute: resultRoute,
    seed: completed,
  },
} satisfies Meta<typeof FeedbackResult>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Loading: Story = {
  parameters: {
    handlers: [
      http.get("*/api/attempts/:id/feedback", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    ],
  },
};
export const CurrentResult: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      await canvas.findByRole("heading", { name: "次の練習へ" }),
    ).toBeVisible();
    await expect(
      canvas.getAllByRole("button", { name: "次の質問へ" }),
    ).toHaveLength(1);
    await expect(
      canvas.getAllByRole("link", { name: "同じ質問に再挑戦" }),
    ).toHaveLength(1);
  },
};
export const NextQuestionPending: Story = {
  parameters: {
    handlers: [
      http.post("*/api/sessions/:id/questions/next", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: "次の質問へ" }),
    );
    await expect(
      await canvas.findByRole("button", { name: "次の質問を準備しています…" }),
    ).toBeDisabled();
    await expect(
      canvas.queryByRole("heading", { name: "次の練習へ" }),
    ).toBeNull();
    await expect(
      canvasElement.querySelector('img[src$="mascot-retry.webp"]'),
    ).toBeNull();
    await expect(
      canvas.getByRole("link", { name: "新しい練習を始める" }),
    ).toBeVisible();
  },
};
export const MissingAttemptId: Story = {
  parameters: { initialRoute: "/result/" },
};
export const InvalidAttemptId: Story = {
  parameters: { initialRoute: "/result/?attemptId=invalid" },
};
export const AttemptNotFound: Story = {
  parameters: {
    initialRoute: `/result/?attemptId=${storyIds.previousAttempt}`,
  },
};
export const FeedbackServerError: Story = {
  parameters: {
    handlers: [
      http.get("*/api/attempts/:id/feedback", () =>
        HttpResponse.json(
          { code: "INTERNAL_SERVER_ERROR", message: "error" },
          { status: 500 },
        ),
      ),
    ],
  },
};
export const InvalidFeedbackResponse: Story = {
  parameters: {
    handlers: [
      http.get("*/api/attempts/:id/feedback", () =>
        HttpResponse.json({ unexpected: true }),
      ),
    ],
  },
};
export const EvaluationNotCompleted: Story = {
  parameters: {
    seed: createStoryState({
      session: createSessionFixture(),
      feedback: createFeedbackFixture(),
      evaluation: {
        ...completed.attempts[storyIds.currentAttempt].evaluation,
        status: "processing",
      },
    }),
  },
};
export const SessionLoading: Story = {
  parameters: {
    handlers: [
      http.get("*/api/sessions/:id/question", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    ],
  },
};
export const SessionError: Story = {
  parameters: {
    handlers: [
      http.get("*/api/sessions/:id/question", () =>
        HttpResponse.json(
          { code: "INTERNAL_SERVER_ERROR", message: "error" },
          { status: 500 },
        ),
      ),
    ],
  },
};
export const StaleResult: Story = {
  parameters: { seed: stale },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      await canvas.findByRole("link", { name: "現在の練習へ戻る" }),
    ).toBeInTheDocument();
    await expect(
      canvas.queryByRole("button", { name: "次の質問へ" }),
    ).not.toBeInTheDocument();
  },
};
export const NextQuestionSuccess: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: "次の質問へ" }),
    );
    await waitFor(() =>
      expect(getRouter().push).toHaveBeenCalledWith(
        `/practice/session/?sessionId=${storyIds.session}`,
      ),
    );
  },
};
export const NextQuestionNetworkError: Story = {
  parameters: { mockScenario: "network_error" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: "次の質問へ" }),
    );
    await expect(
      await canvas.findByRole("button", { name: "次の質問の取得結果を再確認" }),
    ).toBeInTheDocument();
  },
};
export const NextQuestionResponseLost: Story = {
  parameters: { mockScenario: "response_lost" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: "次の質問へ" }),
    );
    await expect(
      await canvas.findByRole("button", { name: "次の質問の取得結果を再確認" }),
    ).toBeInTheDocument();
  },
};
export const NextQuestionConflict: Story = {
  parameters: { mockScenario: "state_conflict" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole("button", { name: "次の質問へ" }),
    );
    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "練習が更新されています",
    );
  },
};
export const RecoveredNextOperation: Story = {
  parameters: {
    storage: {
      [`pocket:next:${storyIds.currentAttempt}`]: {
        version: 1,
        key: storyIds.idempotency,
        fromAttemptId: storyIds.currentAttempt,
      },
    },
  },
};
export const RetryCurrentQuestion: Story = {
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("link", {
        name: "同じ質問に再挑戦",
      }),
    ).toHaveAttribute(
      "href",
      `/practice/session/?sessionId=${storyIds.session}&mode=retry&fromAttemptId=${storyIds.currentAttempt}`,
    );
  },
};
export const MobileLongResult: Story = {
  parameters: {
    seed: createStoryState({
      session: completed.sessions[storyIds.session],
      feedback: createFeedbackFixture({
        answer: storyTexts.text500,
        summary: storyTexts.text500,
      }),
      evaluation: completed.attempts[storyIds.currentAttempt].evaluation,
    }),
  },
  globals: { viewport: { value: "iphoneSe" } },
};
export const InAppShell: Story = {
  ...CurrentResult,
  decorators: [withAppShell],
  parameters: { layout: "fullscreen" },
};
