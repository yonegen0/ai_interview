/**
 * @file Button.stories.tsx
 * @description Button コンポーネントの表示確認用ストーリー。
 */
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "@/components/atoms/Button";

const meta: Meta<typeof Button> = {
  title: "Components/Atoms/Button",
  component: Button,
  parameters: {
    layout: "padded",
  },
  args: {
    children: "ボタン",
  },
};

export default meta;
type Story = StoryObj<typeof Button>;

/**
 * Primary: 既定の color="primary"
 * 通常操作（送信・確定など）に使う基本ボタンの表示を確認する。
 */
export const Primary: Story = {
  args: { variant: "contained", color: "primary" },
};

/**
 * Secondary: color="secondary"
 * セカンダリ操作の配色を確認する。
 */
export const Secondary: Story = {
  args: { variant: "contained", color: "secondary" },
};

/**
 * Success: color="success"
 * 完了系操作（確定など）の配色を確認する。
 */
export const Success: Story = {
  args: { variant: "contained", color: "success", children: "確定する" },
};

/**
 * Error: color="error"
 * 破壊的操作（削除など）の配色を確認する。
 */
export const Error: Story = {
  args: { variant: "contained", color: "error", children: "削除" },
};

/**
 * Outlined: variant="outlined"
 * 補助的操作で使うアウトライン表示を確認する。
 */
export const Outlined: Story = {
  args: { variant: "outlined", color: "primary" },
};

/**
 * Disabled: disabled=true
 * 非活性時の表示を確認する。
 */
export const Disabled: Story = {
  args: { variant: "contained", color: "primary", disabled: true },
};
