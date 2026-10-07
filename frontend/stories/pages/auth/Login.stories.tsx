/** @file Login.stories.tsx @description メールコード認証のMock操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";
import { getRouter } from "@storybook/nextjs-vite/navigation.mock";
import { LoginPage } from "@/features/auth/components/pages/LoginPage";
const meta = {
  title: "Pages/Auth/Login",
  component: LoginPage,
  parameters: { mock: true, initialRoute: "/login/" },
} satisfies Meta<typeof LoginPage>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Initial: Story = {};
export const CodeRequested: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(
      canvas.getByLabelText("メールアドレス"),
      "user@example.invalid",
    );
    await userEvent.click(
      canvas.getByRole("button", { name: "確認コードを送る" }),
    );
    await expect(
      await canvas.findByLabelText("確認コード"),
    ).toBeInTheDocument();
  },
};

export const SuccessfulLogin: Story = {
  parameters: { initialRoute: "/login/?returnTo=%2Fadmin%2Fquestions%2F" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(
      canvas.getByLabelText("メールアドレス"),
      "admin@example.invalid",
    );
    await userEvent.click(
      canvas.getByRole("button", { name: "確認コードを送る" }),
    );
    await userEvent.type(await canvas.findByLabelText("確認コード"), "123456");
    await userEvent.click(canvas.getByRole("button", { name: "ログインする" }));
    await waitFor(() =>
      expect(getRouter().replace).toHaveBeenCalledWith("/admin/questions/"),
    );
  },
};
export const IncorrectCode: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(
      canvas.getByLabelText("メールアドレス"),
      "user@example.invalid",
    );
    await userEvent.click(
      canvas.getByRole("button", { name: "確認コードを送る" }),
    );
    await userEvent.type(await canvas.findByLabelText("確認コード"), "000000");
    await userEvent.click(canvas.getByRole("button", { name: "ログインする" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "コードまたは有効期限",
    );
  },
};
export const ChangeEmail: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(
      canvas.getByLabelText("メールアドレス"),
      "user@example.invalid",
    );
    await userEvent.click(
      canvas.getByRole("button", { name: "確認コードを送る" }),
    );
    await userEvent.click(
      await canvas.findByRole("button", { name: "メールアドレスを変更" }),
    );
    await expect(canvas.getByLabelText("メールアドレス")).toBeEnabled();
    await expect(canvas.queryByLabelText("確認コード")).toBeNull();
  },
};
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
