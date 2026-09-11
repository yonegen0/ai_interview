/** @file PracticeStart.stories.tsx @description カテゴリ選択、セッション作成、復旧のFeature Story。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { getRouter } from "@storybook/nextjs-vite/navigation.mock";
import { PracticeStart } from "@/features/interview/components/pages/PracticeStart";
import { storyIds } from "../../fixtures";

const meta = { title: "Pages/Interview/PracticeStart", component: PracticeStart, parameters: { layout: "padded", mock: true, initialRoute: "/practice/" } } satisfies Meta<typeof PracticeStart>;
export default meta;
type Story = StoryObj<typeof meta>;
const submitCategory = async (canvasElement: HTMLElement) => {
  const canvas = within(canvasElement);
  await userEvent.click(canvas.getByRole("button", { name: "転職理由" }));
  await userEvent.click(canvas.getByRole("button", { name: "練習を始める" }));
  return canvas;
};
export const Initial: Story = {};
export const Selected: Story = { play: async ({ canvasElement }) => { await userEvent.click(within(canvasElement).getByRole("button", { name: "転職理由" })); } };
export const Created: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const start = canvas.getByRole("button", { name: "練習を始める" });
    await expect(start).toBeDisabled();
    await userEvent.click(canvas.getByRole("button", { name: "転職理由" }));
    await expect(start).toBeEnabled();
    await userEvent.click(start);
    await waitFor(() => expect(getRouter().push).toHaveBeenCalledWith(expect.stringMatching(/^\/practice\/session\/\?sessionId=/)));
  },
};
export const ValidationError: Story = { parameters: { mockScenario: "validation" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("alert")).toHaveTextContent("入力内容を確認してください"); } };
export const Unauthorized: Story = { parameters: { mockScenario: "unauthorized" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("alert")).toHaveTextContent("認証が必要"); } };
export const NotFound: Story = { parameters: { mockScenario: "not_found" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("alert")).toHaveTextContent("練習が見つかりません"); } };
export const ServerError: Story = { parameters: { mockScenario: "server_error" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("alert")).toHaveTextContent("サービスで問題"); } };
export const NetworkError: Story = { parameters: { mockScenario: "network_error" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("button", { name: "開始結果を再確認" })).toBeInTheDocument(); } };
export const ResponseLost: Story = { parameters: { mockScenario: "response_lost" }, play: async ({ canvasElement }) => { const canvas = await submitCategory(canvasElement); await expect(await canvas.findByRole("button", { name: "開始結果を再確認" })).toBeInTheDocument(); } };
export const RecoveredRequest: Story = { parameters: { storage: { "pocket:create": { version: 1, key: storyIds.idempotency, category: "job_change" } } } };
export const InvalidStoredRequest: Story = { parameters: { storage: { "pocket:create": { broken: true } } } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
