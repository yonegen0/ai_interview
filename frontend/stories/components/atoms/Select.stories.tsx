/**
 * @file Select.stories.tsx
 * @description Select コンポーネントの代表状態（全幅 / 小 / エラー / 非活性）を確認するストーリー
 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Select } from "@/components/atoms/Select";

const OPTIONS = [
  { value: "all", label: "すべて" },
  { value: "owner", label: "オーナー" },
  { value: "staff", label: "スタッフ" },
] as const;

const meta: Meta<typeof Select> = {
  title: "Components/Atoms/Select",
  component: Select,
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof Select>;

/** 内部 state で双方向動作を確認するラッパ */
const Interactive = (props: {
  fullWidth?: boolean;
  minWidth?: number;
  size?: "small" | "medium";
  disabled?: boolean;
  error?: string;
}) => {
  const [value, setValue] = useState<string>("all");
  return (
    <div style={{ width: 360 }}>
      <Select<string>
        label="実行者"
        value={value}
        onChange={setValue}
        options={OPTIONS}
        fullWidth={props.fullWidth}
        minWidth={props.minWidth}
        size={props.size}
        disabled={props.disabled}
        error={props.error}
      />
    </div>
  );
};

/** FullWidth: 全幅（settings 系） */
export const FullWidth: Story = { render: () => <Interactive fullWidth /> };

/** Small: size=small + minWidth（filter 系） */
export const Small: Story = {
  render: () => <Interactive size="small" minWidth={160} />,
};

/** WithError: バリデーションエラー文言表示 */
export const WithError: Story = {
  render: () => <Interactive fullWidth error="選択してください" />,
};

/** Disabled: 非活性 */
export const Disabled: Story = {
  render: () => <Interactive fullWidth disabled />,
};
