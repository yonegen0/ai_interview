/** @file FeedbackNavigation.stories.tsx @description Components/Organisms/Feedback/FeedbackNavigationの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { FeedbackNavigation } from "@/features/feedback/components/organisms/FeedbackNavigation";
import type { FeedbackNavigationView } from "@/features/feedback/model/navigation";
const view: FeedbackNavigationView = {
  loading: false,
  error: null,
  mutationError: null,
  canRetry: true,
  canNext: true,
  hasNext: true,
  total: 15,
  recovering: false,
  pending: false,
  sessionUrl: "/practice/session/",
  retryUrl: "/practice/session/?mode=retry",
};
const meta = {
  title: "Components/Organisms/Feedback/FeedbackNavigation",
  component: FeedbackNavigation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { view, actions: { next: fn(async () => {}), refresh: fn() } },
} satisfies Meta<typeof FeedbackNavigation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const NextAvailable: Story = {};
export const Completed: Story = {
  args: { view: { ...view, hasNext: false, canNext: false } },
};
export const Stale: Story = {
  args: { view: { ...view, canRetry: false, canNext: false } },
};
export const Pending: Story = {
  args: { view: { ...view, canRetry: false, pending: true } },
};
export const Uncertain: Story = {
  args: { view: { ...view, canRetry: false, recovering: true } },
};
export const Loading: Story = { args: { view: { ...view, loading: true } } };
export const Error: Story = {
  args: {
    view: { ...view, error: new globalThis.Error("確認できませんでした。") },
  },
};
