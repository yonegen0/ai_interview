/**
 * @file Header.stories.tsx
 * @description Header コンポーネントの表示確認用ストーリー。
 */
import type { Meta, StoryObj } from "@storybook/react-vite";
import { Header } from "@/components/molecules/Header";

const meta: Meta<typeof Header> = {
  title: "Components/Molecules/Header",
  component: Header,
  parameters: {
    layout: "padded",
  },
  decorators: [
    (Story) => (
      <div style={{ width: 720 }}>
        <Story />
      </div>
    ),
  ],
  args: {
    eyebrow: "Ticket Issue",
    title: "受付番号発行",
    description: "受付種別を選択して、当日の受付番号を発行します。",
  },
};

export default meta;
type Story = StoryObj<typeof Header>;

/**
 * Full: Eyebrow + Title + Description のフル表示
 * 通常のパネルヘッダーの表示を確認する。
 */
export const Full: Story = {};

/**
 * NoEyebrow: eyebrow を省略した表示
 * ロール制限などで eyebrow を出さないケースのレイアウトを確認する。
 */
export const NoEyebrow: Story = {
  args: {
    eyebrow: undefined,
    title: "操作ログ",
    description: "監査用の操作履歴です。",
  },
};

/**
 * TitleOnly: タイトルのみ
 * eyebrow / description を共に省略したケースのレイアウトを確認する。
 */
export const TitleOnly: Story = {
  args: {
    eyebrow: undefined,
    title: "設定・管理",
    description: undefined,
  },
};
