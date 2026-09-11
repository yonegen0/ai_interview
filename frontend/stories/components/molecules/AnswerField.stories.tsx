/** @file AnswerField.stories.tsx @description 回答欄の入力境界とReact Hook Form検証。 */
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { AnswerField } from "@/features/interview/components/molecules/AnswerField";
import { formSchema } from "@/lib/api/schemas";
import { storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const AnswerFieldHarness = (props: { initialValue?: string; disabled?: boolean; submitAttempted?: boolean }) => {
  const form = useForm<{ answer: string }>({ resolver: zodResolver(formSchema), mode: "onChange", defaultValues: { answer: props.initialValue ?? "" } });
  const answer = useWatch({ control: form.control, name: "answer" }) ?? "";
  return <form onSubmit={form.handleSubmit(() => undefined)}><AnswerField field={form.register("answer")} count={answer.length} disabled={props.disabled} error={form.formState.errors.answer?.message} /><button type="submit">検証する</button></form>;
};
const meta = { title: "Components/Molecules/AnswerField", component: AnswerField, parameters: { layout: "padded" } } satisfies Meta<typeof AnswerField>;
export default meta;
type Story = StoryObj;
export const Empty: Story = { render: () => <AnswerFieldHarness /> };
export const OneCharacter: Story = { render: () => <AnswerFieldHarness initialValue="あ" /> };
export const ShortAnswer99: Story = { render: () => <AnswerFieldHarness initialValue={"あ".repeat(99)} /> };
export const Recommended100: Story = { render: () => <AnswerFieldHarness initialValue={storyTexts.text100} /> };
export const Recommended300: Story = { render: () => <AnswerFieldHarness initialValue={"あ".repeat(300)} /> };
export const Maximum2000: Story = { render: () => <AnswerFieldHarness initialValue={storyTexts.text2000} /> };
export const TooLong2001: Story = { render: () => <AnswerFieldHarness initialValue={storyTexts.text2001} />, play: async ({ canvasElement }) => { await userEvent.click(within(canvasElement).getByRole("button", { name: "検証する" })); await expect(await within(canvasElement).findByText(/2000文字以内/)).toBeInTheDocument(); } };
export const WhitespaceOnly: Story = { render: () => <AnswerFieldHarness initialValue="   " />, play: async ({ canvasElement }) => { await userEvent.click(within(canvasElement).getByRole("button", { name: "検証する" })); await expect(await within(canvasElement).findByText(/空白以外/)).toBeInTheDocument(); } };
export const Multiline: Story = { render: () => <AnswerFieldHarness initialValue={"結論です。\n具体例です。\n成果です。"} /> };
export const Disabled: Story = { render: () => <AnswerFieldHarness initialValue="送信中です" disabled /> };
export const TypingInteraction: Story = { render: () => <AnswerFieldHarness />, play: async ({ canvasElement }) => { const canvas = within(canvasElement); await userEvent.type(canvas.getByLabelText("あなたの回答"), "回答です"); await expect(canvas.getByText(/4 \/ 2000文字/)).toBeInTheDocument(); } };
export const Mobile: Story = { render: () => <AnswerFieldHarness initialValue={storyTexts.text1000} />, globals: { viewport: { value: "iphoneSe" } }, play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement) };
