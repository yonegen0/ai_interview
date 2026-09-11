/** @file AppShell.stories.tsx @description アプリ共通画面枠のLandmarkとResponsive表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import Alert from "@mui/material/Alert";
import { Panel } from "@/components/atoms/Panel";
import { AppShell } from "@/components/templates/AppShell";
import { Button } from "@/components/atoms/Button";
import { storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const content = <><h1>面接練習</h1><Panel><p>一問ずつ、自信を育てる。</p><Button>回答を送信</Button></Panel></>;
const meta = { title: "Components/Templates/AppShell", component: AppShell, parameters: { layout: "fullscreen" }, args: { children: content } } satisfies Meta<typeof AppShell>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const LongContent: Story = { args: { children: <><h1>フィードバック</h1><Panel><p>{storyTexts.text1000}</p></Panel></> } };
export const WithErrorAlert: Story = { args: { children: <><Alert severity="error">通信できませんでした。</Alert>{content}</> } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
export const KeyboardNavigation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole("main")).toBeInTheDocument();
    await userEvent.tab();
    await expect(canvas.getByRole("link", { name: /Interview Pocket/i })).toHaveFocus();
  },
};
export const NoHorizontalOverflow: Story = { ...LongContent, globals: { viewport: { value: "iphoneSe" } }, play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement) };
