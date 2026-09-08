/**
 * @file Input.stories.tsx
 * @description Input コンポーネントの表示確認用ストーリー。
 */
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Input } from "@/components/atoms/Input";

const meta: Meta<typeof Input> = {
  title: "Components/Atoms/Input",
  component: Input,
  parameters: {
    layout: "padded",
  },
  decorators: [
    (Story) => (
      <div style={{ width: 360 }}>
        <Story />
      </div>
    ),
  ],
  args: {
    placeholder: "入力してください",
  },
};

export default meta;
type Story = StoryObj<typeof Input>;

/**
 * Default: 既定のプレースホルダー入力
 * 通常の入力欄の表示を確認する。
 */
export const Default: Story = {};

/**
 * WithLabel: ラベル付き
 * フォームでの一般的な使用形を確認する。
 */
export const WithLabel: Story = {
  args: { label: "店舗名" },
};

/**
 * WithHelperText: 補助テキスト付き
 * 入力ヒントを併記する場合の表示を確認する。
 */
export const WithHelperText: Story = {
  args: { label: "メールアドレス", helperText: "ログインに使用します" },
};

/**
 * ErrorState: error=true
 * バリデーションエラー時の表示を確認する。
 */
export const ErrorState: Story = {
  args: {
    label: "メールアドレス",
    error: true,
    helperText: "メールアドレスの形式で入力してください",
    defaultValue: "invalid",
  },
};

/**
 * Disabled: disabled=true
 * 非活性時の表示を確認する。
 */
export const Disabled: Story = {
  args: { label: "店舗ID", disabled: true, defaultValue: "store-001" },
};

/**
 * Multiline: 複数行入力
 * 自由記述欄での表示を確認する。
 */
export const Multiline: Story = {
  args: { label: "メモ", multiline: true, minRows: 3 },
};
