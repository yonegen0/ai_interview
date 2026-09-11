/** @file PracticeForm.stories.tsx @description 回答、評価、復旧、終了を扱うForm統合Story。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { delay, http, HttpResponse } from "msw";
import { expect, fireEvent, userEvent, waitFor, within } from "storybook/test";
import { getRouter } from "@storybook/nextjs-vite/navigation.mock";
import { PracticeForm } from "@/features/interview/components/templates/PracticeForm";
import { withAppShell } from "../../test-utils/withAppShell";
import {
  createCompletedState,
  createEvaluationFixture,
  createFeedbackFixture,
  createSessionFixture,
  createStoryState,
  storyIds,
  storyTexts,
} from "../../fixtures";

const shortTiming = {
  longWaitSeconds: 0.2,
  autoPauseSeconds: 1,
  pollingIntervalMs: 50,
};
const session = createSessionFixture();
const processingEvaluation = createEvaluationFixture("processing");
const processingSession = createSessionFixture({
  activeAttempt: {
    attemptId: storyIds.currentAttempt,
    evaluationId: storyIds.evaluation,
    status: "processing",
  },
});
const processingSeed = createStoryState({
  session: processingSession,
  feedback: createFeedbackFixture(),
  evaluation: processingEvaluation,
});
const pendingAnswer = {
  version: 1,
  questionId: storyIds.question,
  context: "1:normal",
  draft: "復旧する回答です。",
  pending: {
    key: storyIds.idempotency,
    body: { questionId: storyIds.question, answer: "復旧する回答です。" },
  },
};
const meta = {
  title: "Components/Templates/PracticeForm",
  component: PracticeForm,
  parameters: { layout: "padded", mock: true, seed: createStoryState() },
  args: { session, retryFrom: null, timing: shortTiming },
} satisfies Meta<typeof PracticeForm>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Answering: Story = {};
export const Submitting: Story = {
  parameters: {
    handlers: [
      http.post("*/api/sessions/:id/answers", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByLabelText("あなたの回答");
    await userEvent.type(input, "チームで課題を整理し、改善しました。");
    await userEvent.click(canvas.getByRole("button", { name: "回答を送信" }));
    await expect(
      await canvas.findByRole("button", { name: "回答を送信しています…" }),
    ).toBeDisabled();
    await expect(input).toBeDisabled();
    expect(canvas.getByLabelText("あなたの回答")).toBe(input);
    await expect(
      canvas.getAllByRole("button", { name: "回答を送信しています…" }),
    ).toHaveLength(1);
    await expect(input).toHaveValue("チームで課題を整理し、改善しました。");
    await expect(
      canvasElement.querySelector('img[src$="mascot-thinking.webp"]'),
    ).toBeVisible();
  },
};
export const SubmittingMobile: Story = {
  ...Submitting,
  globals: { viewport: { value: "iphoneSe" } },
};
export const ResponseLostAfterSubmit: Story = {
  parameters: { mockScenario: "response_lost" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByLabelText("あなたの回答");
    await userEvent.type(input, "課題を整理してチームで改善しました。");
    await userEvent.click(canvas.getByRole("button", { name: "回答を送信" }));
    const retry = await canvas.findByRole("button", {
      name: "送信結果を再確認",
    });
    expect(canvas.getByLabelText("あなたの回答")).toBe(input);
    await expect(input).toBeDisabled();
    await expect(
      canvas.queryByRole("heading", { name: "回答を送信しています" }),
    ).toBeNull();
    await expect(
      canvasElement.querySelector('img[src$="mascot-thinking.webp"]'),
    ).toBeNull();
    for (let index = 0; index < 8 && document.activeElement !== retry; index++)
      await userEvent.tab();
    await expect(retry).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await expect(
      await canvas.findByRole("heading", { name: "回答を確認しています" }),
    ).toBeVisible();
  },
};
export const DraftRestored: Story = {
  parameters: {
    storage: {
      [`pocket:answer:${storyIds.session}`]: {
        version: 1,
        questionId: storyIds.question,
        context: "1:normal",
        draft: "復元した回答です。",
      },
    },
  },
};
export const WrongQuestionDraftIgnored: Story = {
  parameters: {
    storage: {
      [`pocket:answer:${storyIds.session}`]: {
        version: 1,
        questionId: "00000000-0000-4000-8000-000000000099",
        context: "1:normal",
        draft: "表示されない回答",
      },
    },
  },
};
export const WhitespaceValidation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("あなたの回答"), "   ");
    fireEvent.submit(
      canvas.getByRole("button", { name: "回答を送信" }).closest("form")!,
    );
    await expect(await canvas.findByText(/空白以外/)).toBeInTheDocument();
  },
};
export const MaximumLength: Story = {
  parameters: {
    storage: {
      [`pocket:answer:${storyIds.session}`]: {
        version: 1,
        questionId: storyIds.question,
        context: "1:normal",
        draft: storyTexts.text2000,
      },
    },
  },
};
export const TooLong: Story = {
  parameters: {
    storage: {
      [`pocket:answer:${storyIds.session}`]: {
        version: 1,
        questionId: storyIds.question,
        context: "1:normal",
        draft: storyTexts.text2001,
      },
    },
  },
};
export const Processing: Story = {
  args: { session: processingSession },
  parameters: { seed: processingSeed, mockScenario: "never" },
};
export const LongWait: Story = {
  ...Processing,
  args: {
    session: processingSession,
    retryFrom: null,
    timing: { ...shortTiming, longWaitSeconds: 0 },
  },
};
export const NetworkRecovery: Story = {
  parameters: {
    mockScenario: "network_error",
    storage: { [`pocket:answer:${storyIds.session}`]: pendingAnswer },
  },
};
export const ResponseLostRecovery: Story = {
  parameters: {
    mockScenario: "response_lost",
    storage: { [`pocket:answer:${storyIds.session}`]: pendingAnswer },
  },
};
export const EvaluationFailed: Story = {
  args: { session: processingSession },
  parameters: { seed: processingSeed, mockScenario: "evaluation_failed" },
};
export const RetryAfterEvaluationFailure: Story = {
  ...EvaluationFailed,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const retry = await canvas.findByRole("button", {
      name: "同じ質問に再挑戦",
    });
    await expect(
      canvasElement.querySelector('img[src$="mascot-error.webp"]'),
    ).toBeVisible();
    await userEvent.click(retry);
    await expect(canvas.getByLabelText("あなたの回答")).toBeEnabled();
    await expect(canvas.getByLabelText("あなたの回答")).toHaveValue("");
    await expect(canvasElement.querySelector("img")).toBeNull();
  },
};
export const Completed: Story = {
  args: { session: createCompletedState().sessions[storyIds.session] },
  parameters: { seed: createCompletedState() },
  play: async () => {
    await waitFor(() =>
      expect(getRouter().push).toHaveBeenCalledWith(
        `/result/?attemptId=${storyIds.currentAttempt}`,
      ),
    );
  },
};
export const ExitEmpty: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "練習を終了" }),
    );
    await expect(getRouter().push).toHaveBeenCalledWith("/practice/");
  },
};
export const ExitWithDraft: Story = {
  ...DraftRestored,
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "練習を終了" }),
    );
    await expect(within(document.body).getByRole("dialog")).toBeInTheDocument();
  },
};
export const ExitWhileProcessing: Story = {
  ...Processing,
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "練習を終了" }),
    );
    await expect(
      within(document.body).getByText(/評価は中止されません/),
    ).toBeInTheDocument();
  },
};
export const SubmitFlow: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(
      canvas.getByLabelText("あなたの回答"),
      "私の強みは継続力です。",
    );
    await userEvent.click(canvas.getByRole("button", { name: "回答を送信" }));
    await waitFor(() => expect(canvas.getByRole("status")).toBeInTheDocument());
    await waitFor(
      () =>
        expect(getRouter().push).toHaveBeenCalledWith(
          expect.stringMatching(/^\/result\/\?attemptId=/),
        ),
      { timeout: 3000 },
    );
  },
};
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const SubmittingInAppShell: Story = {
  ...Submitting,
  decorators: [withAppShell],
  parameters: { ...Submitting.parameters, layout: "fullscreen" },
};
export const EvaluationFailedInAppShell: Story = {
  ...EvaluationFailed,
  decorators: [withAppShell],
  parameters: { ...EvaluationFailed.parameters, layout: "fullscreen" },
};
