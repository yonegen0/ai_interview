/** @file EmailOtpForm.stories.tsx @description Components/Organisms/Auth/EmailOtpFormの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { LoginPresentation } from "../../../test-utils/presentation";
const meta = {
  title: "Components/Organisms/Auth/EmailOtpForm",
  component: LoginPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {},
} satisfies Meta<typeof LoginPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Email: Story = {};
export const InvalidEmail: Story = { args: { invalid: "email" } };
export const Code: Story = { args: { stage: "code" } };
export const InvalidCode: Story = { args: { stage: "code", invalid: "code" } };
export const Pending: Story = { args: { stage: "code", pending: true } };
export const Cooldown: Story = { args: { stage: "code", cooldown: 60 } };
export const ResendAvailable: Story = { args: { stage: "code", cooldown: 0 } };
export const SendFailure: Story = {
  args: { error: "コードを送信できませんでした。" },
};
export const ConfirmFailure: Story = {
  args: { stage: "code", error: "コードまたは有効期限を確認してください。" },
};
