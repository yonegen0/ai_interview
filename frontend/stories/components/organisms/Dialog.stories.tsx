/** @file Dialog.stories.tsx @description 練習終了DialogのFocus、閉じ方、長文表示。 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { Dialog } from "@/components/organisms/Dialog";
import { Button } from "@/components/atoms/Button";
import { storyTexts } from "../../fixtures";

const confirmed = fn();
const DialogHarness = (props: { long?: boolean }) => {
  const [open, setOpen] = useState(false);
  return <><Button onClick={() => setOpen(true)}>練習を終了</Button><Dialog open={open} onClose={() => setOpen(false)} title="練習を終了しますか？" content={<p>{props.long ? storyTexts.text1000 : "入力中の下書きは破棄されます。"}</p>} actions={<><Button autoFocus onClick={() => setOpen(false)}>続ける</Button><Button color="error" onClick={confirmed}>終了する</Button></>} /></>;
};
const meta = { title: "Components/Organisms/Dialog", component: Dialog, parameters: { layout: "padded" }, args: { open: true, onClose: fn(), title: "練習を終了しますか？", content: <p>入力中の下書きは破棄されます。</p>, actions: <Button>続ける</Button> } } satisfies Meta<typeof Dialog>;
export default meta;
type Story = StoryObj<typeof meta>;
export const ExitConfirmation: Story = { render: () => <DialogHarness />, play: async ({ canvasElement }) => { await userEvent.click(within(canvasElement).getByRole("button", { name: "練習を終了" })); await expect(within(document.body).getByRole("button", { name: "続ける" })).toHaveFocus(); } };
export const Continue: Story = { render: () => <DialogHarness />, play: async ({ canvasElement }) => { const trigger = within(canvasElement).getByRole("button", { name: "練習を終了" }); await userEvent.click(trigger); await userEvent.click(within(document.body).getByRole("button", { name: "続ける" })); await expect(trigger).toHaveFocus(); } };
export const ConfirmExit: Story = { render: () => <DialogHarness />, play: async ({ canvasElement }) => { await userEvent.click(within(canvasElement).getByRole("button", { name: "練習を終了" })); await userEvent.click(within(document.body).getByRole("button", { name: "終了する" })); await expect(confirmed).toHaveBeenCalledOnce(); } };
export const EscapeClose: Story = { render: () => <DialogHarness />, play: async ({ canvasElement }) => { const trigger = within(canvasElement).getByRole("button", { name: "練習を終了" }); await userEvent.click(trigger); await userEvent.keyboard("{Escape}"); await expect(trigger).toHaveFocus(); } };
export const WithLongContent: Story = { render: () => <DialogHarness long /> };
export const Mobile: Story = { render: () => <DialogHarness />, globals: { viewport: { value: "iphoneSe" } } };
